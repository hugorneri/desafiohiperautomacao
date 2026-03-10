from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class FiltersPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    beneficiario_programa_social: bool = False
    sancao_vigente: bool = False
    ocupante_imovel_funcional: bool = False
    possui_contrato: bool = False
    favorecido_recurso_publico: bool = False
    emitente_nfe: bool = False


class OptionsPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    headed: bool = False


class ConsultaRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(..., description="Nome, CPF ou NIS da pessoa consultada")
    filters: FiltersPayload = Field(default_factory=FiltersPayload)
    options: OptionsPayload = Field(default_factory=OptionsPayload)

    @field_validator("query")
    @classmethod
    def validar_query(cls, value: str) -> str:
        query = value.strip()
        if not query:
            raise ValueError("O campo query deve conter ao menos um caractere valido.")
        return query


class ConsultaMetadata(BaseModel):
    id: str
    termo: str
    executado_em: str
    filtros: FiltersPayload


class ArmazenamentoMetadata(BaseModel):
    arquivo_json: str | None = None
    drive_file_id: str | None = None
    drive_link: str | None = None
    sheet_row_id: str | None = None


class ConsultaResponse(BaseModel):
    sucesso: bool
    consulta: ConsultaMetadata
    pessoa: dict[str, Any] | None = None
    beneficios: list[dict[str, Any]] = Field(default_factory=list)
    evidencia_base64: str | None = None
    armazenamento: ArmazenamentoMetadata
    mensagem: str | None = None
