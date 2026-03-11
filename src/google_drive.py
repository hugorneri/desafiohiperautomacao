import io
import json
import os
import re

from dotenv import load_dotenv
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload


GOOGLE_DRIVE_SCOPE = "https://www.googleapis.com/auth/drive.file"
GOOGLE_SHEETS_SCOPE = "https://www.googleapis.com/auth/spreadsheets"


load_dotenv()


class GoogleDriveConfigError(RuntimeError):
    pass


class GoogleDriveUploadError(RuntimeError):
    pass


def google_drive_esta_configurado():
    service_account_file = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE")
    drive_folder_id = os.getenv("GOOGLE_DRIVE_FOLDER_ID")

    return bool(service_account_file and drive_folder_id and os.path.exists(service_account_file))


def carregar_configuracao_google_drive():
    service_account_file = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE")
    drive_folder_id = os.getenv("GOOGLE_DRIVE_FOLDER_ID")

    if not service_account_file:
        raise GoogleDriveConfigError("A variavel de ambiente GOOGLE_SERVICE_ACCOUNT_FILE nao foi configurada.")

    if not drive_folder_id:
        raise GoogleDriveConfigError("A variavel de ambiente GOOGLE_DRIVE_FOLDER_ID nao foi configurada.")

    if not os.path.exists(service_account_file):
        raise GoogleDriveConfigError(
            "O arquivo informado em GOOGLE_SERVICE_ACCOUNT_FILE nao foi encontrado."
        )

    return {
        "service_account_file": service_account_file,
        "drive_folder_id": drive_folder_id,
    }


def carregar_configuracao_google_sheets():
    spreadsheet_id = os.getenv("GOOGLE_SPREADSHEET_ID")
    if not spreadsheet_id:
        return None

    return {
        "spreadsheet_id": spreadsheet_id,
        "sheet_name": os.getenv("GOOGLE_SHEETS_TAB_NAME", "Consultas"),
    }


def criar_credenciais_google(configuracao, scopes):
    return Credentials.from_service_account_file(
        configuracao["service_account_file"],
        scopes=scopes,
    )


def criar_servico_google_drive(credenciais):
    return build("drive", "v3", credentials=credenciais, cache_discovery=False)


def criar_servico_google_sheets(credenciais):
    return build("sheets", "v4", credentials=credenciais, cache_discovery=False)


def serializar_resultado_json(resultado):
    conteudo_json = json.dumps(resultado, ensure_ascii=False, indent=2)
    return io.BytesIO(conteudo_json.encode("utf-8"))


def montar_link_drive(file_id, web_view_link=None):
    if web_view_link:
        return web_view_link
    return f"https://drive.google.com/file/d/{file_id}/view?usp=drive_link"


def montar_linha_google_sheets(resultado):
    consulta = resultado.get("consulta") or {}
    pessoa = resultado.get("pessoa") or {}
    armazenamento = resultado.get("armazenamento") or {}

    return [
        consulta.get("id") or "",
        pessoa.get("Nome") or "",
        pessoa.get("CPF") or "",
        consulta.get("executado_em") or "",
        armazenamento.get("drive_link") or "",
    ]


def extrair_sheet_row_id(updated_range):
    if not updated_range:
        return None

    correspondencia = re.search(r"![A-Z]+(\d+)(?::[A-Z]+\d+)?$", updated_range)
    if not correspondencia:
        return None

    return correspondencia.group(1)


def registrar_consulta_no_google_sheets(resultado, credenciais):
    configuracao_sheets = carregar_configuracao_google_sheets()
    if not configuracao_sheets:
        return resultado

    servico = criar_servico_google_sheets(credenciais)
    intervalo = f"{configuracao_sheets['sheet_name']}!A:E"
    corpo = {"values": [montar_linha_google_sheets(resultado)]}

    try:
        resposta = (
            servico.spreadsheets()
            .values()
            .append(
                spreadsheetId=configuracao_sheets["spreadsheet_id"],
                range=intervalo,
                valueInputOption="RAW",
                insertDataOption="INSERT_ROWS",
                body=corpo,
            )
            .execute()
        )
    except Exception as exc:
        raise GoogleDriveUploadError(f"Falha ao registrar consulta no Google Sheets: {exc}") from exc

    updated_range = (resposta.get("updates") or {}).get("updatedRange")
    resultado["armazenamento"]["sheet_row_id"] = extrair_sheet_row_id(updated_range) or updated_range
    return resultado


def enviar_resultado_para_google_drive(resultado):
    configuracao = carregar_configuracao_google_drive()
    credenciais = criar_credenciais_google(
        configuracao,
        scopes=[GOOGLE_DRIVE_SCOPE, GOOGLE_SHEETS_SCOPE],
    )
    servico = criar_servico_google_drive(credenciais)

    nome_arquivo = resultado["armazenamento"]["arquivo_json"]
    if not nome_arquivo:
        raise GoogleDriveUploadError("O nome do arquivo JSON nao foi gerado antes do upload.")

    metadata = {
        "name": nome_arquivo,
        "parents": [configuracao["drive_folder_id"]],
    }
    media = MediaIoBaseUpload(
        serializar_resultado_json(resultado),
        mimetype="application/json",
        resumable=False,
    )

    try:
        arquivo = (
            servico.files()
            .create(
                body=metadata,
                media_body=media,
                fields="id, webViewLink",
            )
            .execute()
        )
    except Exception as exc:
        raise GoogleDriveUploadError(f"Falha ao enviar JSON para o Google Drive: {exc}") from exc

    file_id = arquivo["id"]
    drive_link = montar_link_drive(file_id, arquivo.get("webViewLink"))

    resultado["armazenamento"]["drive_file_id"] = file_id
    resultado["armazenamento"]["drive_link"] = drive_link
    resultado = registrar_consulta_no_google_sheets(resultado, credenciais)
    return resultado
