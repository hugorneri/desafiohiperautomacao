import io
import json
import os

from dotenv import load_dotenv
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload


GOOGLE_DRIVE_SCOPE = "https://www.googleapis.com/auth/drive.file"


load_dotenv()


class GoogleDriveConfigError(RuntimeError):
    pass


class GoogleDriveUploadError(RuntimeError):
    pass


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


def criar_servico_google_drive(configuracao):
    credenciais = Credentials.from_service_account_file(
        configuracao["service_account_file"],
        scopes=[GOOGLE_DRIVE_SCOPE],
    )
    return build("drive", "v3", credentials=credenciais, cache_discovery=False)


def serializar_resultado_json(resultado):
    conteudo_json = json.dumps(resultado, ensure_ascii=False, indent=2)
    return io.BytesIO(conteudo_json.encode("utf-8"))


def montar_link_drive(file_id, web_view_link=None):
    if web_view_link:
        return web_view_link
    return f"https://drive.google.com/file/d/{file_id}/view?usp=drive_link"


def enviar_resultado_para_google_drive(resultado):
    configuracao = carregar_configuracao_google_drive()
    servico = criar_servico_google_drive(configuracao)

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
    return resultado
