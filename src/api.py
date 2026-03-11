from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

try:
    from .engine import executar_automacao_por_payload
    from .google_drive import (
        GoogleDriveConfigError,
        GoogleDriveUploadError,
        enviar_resultado_para_google_drive,
        google_drive_esta_configurado,
    )
    from .schemas import ConsultaRequest, ConsultaResponse
except ImportError:
    from engine import executar_automacao_por_payload
    from google_drive import (
        GoogleDriveConfigError,
        GoogleDriveUploadError,
        enviar_resultado_para_google_drive,
        google_drive_esta_configurado,
    )
    from schemas import ConsultaRequest, ConsultaResponse


app = FastAPI(
    title="Desafio Hiperautomacao API",
    version="1.0.0",
    description="API HTTP para executar o robo da Parte 1 e retornar o resultado estruturado em JSON.",
)


@app.exception_handler(RequestValidationError)
async def handle_validation_error(_, exc: RequestValidationError):
    return JSONResponse(
        status_code=400,
        content={
            "detail": "Payload invalido.",
            "errors": exc.errors(),
        },
    )


@app.get("/health")
def healthcheck():
    return {"status": "ok"}


def registrar_aviso_armazenamento(resultado, mensagem):
    mensagem_atual = resultado.get("mensagem")
    if mensagem_atual:
        resultado["mensagem"] = f"{mensagem_atual} | {mensagem}"
    else:
        resultado["mensagem"] = mensagem
    return resultado


@app.post("/api/v1/consultas", response_model=ConsultaResponse, status_code=200)
def criar_consulta(payload: ConsultaRequest):
    try:
        resultado = executar_automacao_por_payload(payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Falha interna na API: {exc}") from exc

    if not resultado.get("sucesso"):
        return resultado

    if not google_drive_esta_configurado():
        return registrar_aviso_armazenamento(
            resultado,
            "Armazenamento Google ignorado: configure o arquivo .env e um credentials.json valido para habilitar Drive e Sheets.",
        )

    try:
        resultado = enviar_resultado_para_google_drive(resultado)
    except (GoogleDriveConfigError, GoogleDriveUploadError) as exc:
        resultado = registrar_aviso_armazenamento(resultado, str(exc))
        return resultado

    return resultado


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("src.api:app", host="127.0.0.1", port=8000, reload=False)
