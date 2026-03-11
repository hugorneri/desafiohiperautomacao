import argparse
import base64
import json
import logging
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from selenium import webdriver
from selenium.common.exceptions import (
    ElementClickInterceptedException,
    SessionNotCreatedException,
    StaleElementReferenceException,
    TimeoutException,
)
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

try:
    from .map import TIMEOUT, URL, XPATHS_BENEFICIOS, XPATHS_BUSCA, XPATHS_CHECKBOX, XPATHS_RESULTADO
    from .google_drive import (
        GoogleDriveConfigError,
        GoogleDriveUploadError,
        enviar_resultado_para_google_drive,
        google_drive_esta_configurado,
    )
except ImportError:
    from map import TIMEOUT, URL, XPATHS_BENEFICIOS, XPATHS_BUSCA, XPATHS_CHECKBOX, XPATHS_RESULTADO
    from google_drive import (
        GoogleDriveConfigError,
        GoogleDriveUploadError,
        enviar_resultado_para_google_drive,
        google_drive_esta_configurado,
    )


ARGUMENTOS_CHECKBOX = {
    "beneficiario_programa_social": "beneficiario-programa-social",
    "sancao_vigente": "sancao-vigente",
    "ocupante_imovel_funcional": "ocupante-imovel-funcional",
    "possui_contrato": "possui-contrato",
    "favorecido_recurso_publico": "favorecido-recurso-publico",
    "emitente_nfe": "emitente-nfe",
}


def gerar_identificador_consulta():
    return str(uuid4())


def filtros_padrao():
    return {nome_checkbox: False for nome_checkbox in XPATHS_CHECKBOX}


def normalizar_filtros_checkbox(filtros_checkbox=None):
    filtros_normalizados = filtros_padrao()

    if not filtros_checkbox:
        return filtros_normalizados

    if isinstance(filtros_checkbox, dict):
        for nome_checkbox, habilitado in filtros_checkbox.items():
            if nome_checkbox not in XPATHS_CHECKBOX:
                raise ValueError(f"Filtro invalido informado: {nome_checkbox}")
            filtros_normalizados[nome_checkbox] = bool(habilitado)
        return filtros_normalizados

    for nome_checkbox in filtros_checkbox:
        if nome_checkbox not in XPATHS_CHECKBOX:
            raise ValueError(f"Filtro invalido informado: {nome_checkbox}")
        filtros_normalizados[nome_checkbox] = True

    return filtros_normalizados


def filtros_marcados(filtros_checkbox=None):
    filtros_normalizados = normalizar_filtros_checkbox(filtros_checkbox)
    return [nome_checkbox for nome_checkbox, habilitado in filtros_normalizados.items() if habilitado]


def validar_termo_consulta(termo_consulta):
    if termo_consulta is None:
        raise ValueError("O parametro query e obrigatorio.")

    termo_normalizado = termo_consulta.strip()
    if not termo_normalizado:
        raise ValueError("O parametro query deve conter ao menos um caractere valido.")

    return termo_normalizado


def montar_metadados_consulta(termo_consulta, filtros_checkbox=None, consulta_id=None):
    return {
        "id": consulta_id or gerar_identificador_consulta(),
        "termo": validar_termo_consulta(termo_consulta),
        "executado_em": datetime.now(UTC).isoformat(),
        "filtros": normalizar_filtros_checkbox(filtros_checkbox),
    }


def gerar_data_hora_arquivo(executado_em):
    instante = datetime.fromisoformat(executado_em)
    instante_utc = instante.astimezone(UTC)
    return instante_utc.strftime("%Y%m%dT%H%M%SZ")


def gerar_nome_arquivo_json(consulta):
    identificador_unico = consulta["id"]
    data_hora_arquivo = gerar_data_hora_arquivo(consulta["executado_em"])
    return f"{identificador_unico}_{data_hora_arquivo}.json"


def montar_metadados_armazenamento(consulta):
    return {
        "arquivo_json": gerar_nome_arquivo_json(consulta),
        "drive_file_id": None,
        "drive_link": None,
        "sheet_row_id": None,
    }


def configurar_logging():
    diretorio_logs = Path.cwd() / "logs"
    diretorio_logs.mkdir(exist_ok=True)
    arquivo_log = diretorio_logs / "automacao.log"

    logger = logging.getLogger(__name__)
    logger.setLevel(logging.INFO)
    logger.propagate = False

    if logger.handlers:
        return logger

    formatador = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")

    manipulador_arquivo = logging.FileHandler(arquivo_log, encoding="utf-8")
    manipulador_arquivo.setLevel(logging.INFO)
    manipulador_arquivo.setFormatter(formatador)
    logger.addHandler(manipulador_arquivo)

    return logger


LOGGER = configurar_logging()
USER_AGENT_DESKTOP = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/145.0.0.0 Safari/537.36"
)


def configurar_driver(headless=False):
    diretorio_perfil = Path.cwd() / ".chrome-profile" / str(uuid4())
    diretorio_perfil.mkdir(parents=True, exist_ok=True)

    opcoes = Options()
    if headless:
        opcoes.add_argument("--headless=new")
    else:
        opcoes.add_argument("--start-maximized")
    opcoes.add_argument("--window-size=1920,1080")
    opcoes.add_argument("--disable-dev-shm-usage")
    opcoes.add_argument("--disable-extensions")
    opcoes.add_argument("--disable-popup-blocking")
    opcoes.add_argument("--no-first-run")
    opcoes.add_argument("--no-default-browser-check")
    opcoes.add_argument("--disable-gpu")
    opcoes.add_argument("--disable-blink-features=AutomationControlled")
    opcoes.add_argument("--lang=pt-BR")
    opcoes.add_argument(f"--user-agent={USER_AGENT_DESKTOP}")
    opcoes.add_argument("--log-level=3")
    opcoes.add_argument("--disable-logging")
    opcoes.add_experimental_option("excludeSwitches", ["enable-logging"])
    opcoes.add_experimental_option("useAutomationExtension", False)
    opcoes.add_argument(f"--user-data-dir={diretorio_perfil}")

    servico = Service(log_output=subprocess.DEVNULL)
    navegador = webdriver.Chrome(service=servico, options=opcoes)
    navegador.execute_cdp_cmd(
        "Page.addScriptToEvaluateOnNewDocument",
        {
            "source": """
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                });
                Object.defineProperty(navigator, 'language', {
                    get: () => 'pt-BR'
                });
                Object.defineProperty(navigator, 'languages', {
                    get: () => ['pt-BR', 'pt']
                });
            """,
        },
    )
    navegador.execute_cdp_cmd(
        "Network.setUserAgentOverride",
        {
            "userAgent": USER_AGENT_DESKTOP,
            "acceptLanguage": "pt-BR,pt;q=0.9",
            "platform": "Windows",
        },
    )

    if headless:
        LOGGER.info("Driver iniciado em modo headless.")
    else:
        LOGGER.info("Driver iniciado em modo com interface visual.")

    navegador.set_window_size(1920, 1080)
    navegador.get(URL)
    aguardar_pagina_pronta(navegador)
    return navegador


def aguardar_clicavel(navegador, xpath, timeout=TIMEOUT):
    return WebDriverWait(navegador, timeout).until(EC.element_to_be_clickable((By.XPATH, xpath)))


def aguardar_presente(navegador, xpath, timeout=TIMEOUT):
    return WebDriverWait(navegador, timeout).until(EC.presence_of_element_located((By.XPATH, xpath)))


def aguardar_visivel(navegador, xpath, timeout=TIMEOUT):
    return WebDriverWait(navegador, timeout).until(EC.visibility_of_element_located((By.XPATH, xpath)))


def localizar_opcional(navegador, xpath):
    elementos = navegador.find_elements(By.XPATH, xpath)
    if not elementos:
        return None
    return elementos[0]


def localizar_visivel_opcional(navegador, xpath):
    for elemento in navegador.find_elements(By.XPATH, xpath):
        if elemento.is_displayed():
            return elemento
    return None


def clicar_elemento(navegador, descricao, elemento=None, xpath=None, tentativas=3):
    if elemento is None and xpath is None:
        raise ValueError("Informe elemento ou xpath para clicar.")

    for tentativa in range(1, tentativas + 1):
        try:
            elemento_atual = elemento
            if xpath is not None:
                elemento_atual = aguardar_clicavel(navegador, xpath)

            LOGGER.info("Clique iniciado: %s", descricao)
            navegador.execute_script("arguments[0].scrollIntoView({block: 'center'});", elemento_atual)

            try:
                elemento_atual.click()
                LOGGER.info("Clique realizado com sucesso: %s", descricao)
                return elemento_atual
            except ElementClickInterceptedException:
                LOGGER.warning("Clique interceptado, tentando JavaScript: %s", descricao)
                navegador.execute_script("arguments[0].click();", elemento_atual)
                LOGGER.info("Clique via JavaScript realizado com sucesso: %s", descricao)
                return elemento_atual
        except StaleElementReferenceException:
            LOGGER.warning(
                "Elemento ficou stale ao clicar: %s | tentativa %s de %s",
                descricao,
                tentativa,
                tentativas,
            )
            elemento = None
            if tentativa == tentativas:
                LOGGER.exception("Erro ao clicar: %s", descricao)
                raise
        except Exception:
            LOGGER.exception("Erro ao clicar: %s", descricao)
            raise


def clicar(navegador, xpath, descricao):
    return clicar_elemento(navegador, descricao, xpath=xpath)


def aguardar_condicao(navegador, condicao, timeout=TIMEOUT):
    return WebDriverWait(navegador, timeout).until(condicao)


def aguardar_pagina_pronta(navegador, timeout=TIMEOUT):
    WebDriverWait(navegador, timeout).until(
        lambda driver: driver.execute_script("return document.readyState") == "complete"
    )


def obter_texto_ou_nulo(navegador, xpath):
    elemento = localizar_opcional(navegador, xpath)
    if elemento is None:
        return None
    texto = elemento.text.strip()
    return texto or None


def capturar_evidencia_base64(navegador):
    imagem = navegador.get_screenshot_as_png()
    return base64.b64encode(imagem).decode("utf-8")


def registrar_dados_pessoa(dados_pessoa):
    LOGGER.info(
        "Dados principais extraidos: %s",
        json.dumps(dados_pessoa, ensure_ascii=False, sort_keys=True),
    )


def registrar_beneficios(beneficios):
    LOGGER.info("Total de programas encontrados: %s", len(beneficios))

    for beneficio in beneficios:
        LOGGER.info(
            "Programa encontrado: %s | campos: %s | tabelas: %s",
            beneficio["programa"],
            len(beneficio.get("detalhes", {})),
            len(beneficio.get("tabelas", [])),
        )
        LOGGER.info(
            "Detalhes do programa %s: %s",
            beneficio["programa"],
            json.dumps(
                {
                    "detalhes": beneficio.get("detalhes", {}),
                    "tabelas": beneficio.get("tabelas", []),
                },
                ensure_ascii=False,
            ),
        )


def registrar_resultado_execucao(resultado):
    LOGGER.info(
        "Resultado final da execucao: %s",
        json.dumps(
            {
                "sucesso": resultado["sucesso"],
                "consulta": resultado["consulta"],
                "mensagem": resultado.get("mensagem"),
                "pessoa": resultado.get("pessoa"),
                "total_programas": len(resultado.get("beneficios", [])),
                "armazenamento": resultado.get("armazenamento"),
            },
            ensure_ascii=False,
        ),
    )


def registrar_aviso_armazenamento(resultado, mensagem):
    mensagem_atual = resultado.get("mensagem")
    if mensagem_atual:
        resultado["mensagem"] = f"{mensagem_atual} | {mensagem}"
    else:
        resultado["mensagem"] = mensagem
    return resultado


def enviar_resultado_google_se_configurado(resultado):
    if not resultado.get("sucesso"):
        return resultado

    if not google_drive_esta_configurado():
        return registrar_aviso_armazenamento(
            resultado,
            "Armazenamento Google ignorado: configure o arquivo .env e um credentials.json valido para habilitar Drive e Sheets.",
        )

    try:
        return enviar_resultado_para_google_drive(resultado)
    except (GoogleDriveConfigError, GoogleDriveUploadError) as exc:
        return registrar_aviso_armazenamento(resultado, str(exc))


def preencher_formulario_busca(navegador, termo, filtros_checkbox=None):
    LOGGER.info("Preenchendo formulario de busca.")
    campo_termo = aguardar_presente(navegador, XPATHS_BUSCA["input_termo"])
    aguardar_visivel(navegador, XPATHS_BUSCA["input_termo"])
    navegador.execute_script("arguments[0].scrollIntoView({block: 'center'});", campo_termo)
    campo_termo.clear()
    campo_termo.send_keys(termo)
    LOGGER.info("Campo de busca preenchido com o termo informado.")

    clicar(navegador, XPATHS_BUSCA["bt_refine_busca"], "botao Refine a Busca")

    if not filtros_checkbox:
        return

    for nome_checkbox in filtros_checkbox:
        clicar(navegador, XPATHS_CHECKBOX[nome_checkbox], f"checkbox {nome_checkbox}")


def consultar_busca(navegador):
    LOGGER.info("Executando consulta.")
    clicar(navegador, XPATHS_BUSCA["bt_consultar"], "botao Consultar")


def extrair_mensagem_alerta(navegador):
    elemento = localizar_opcional(navegador, XPATHS_BUSCA["mensagem_alerta"])
    if elemento is None:
        return None
    mensagem = elemento.text.strip()
    return mensagem or None


def abrir_primeiro_resultado(navegador):
    LOGGER.info("Abrindo o primeiro resultado.")
    href_resultado = None

    for tentativa in range(1, 4):
        try:
            primeiro_resultado = aguardar_visivel(navegador, XPATHS_BUSCA["resultado_primeiro_link"])
            href_resultado = primeiro_resultado.get_attribute("href")
            LOGGER.info(
                "Primeiro resultado localizado: texto='%s' | href='%s' | tentativa=%s",
                normalizar_espacos(primeiro_resultado.text),
                href_resultado,
                tentativa,
            )
            clicar_elemento(
                navegador,
                f"primeiro resultado da busca (tentativa {tentativa})",
                xpath=XPATHS_BUSCA["resultado_primeiro_link"],
            )
            aguardar_clicavel(navegador, XPATHS_RESULTADO["recebimentos_recursos"])
            LOGGER.info("Primeiro resultado aberto com sucesso.")
            return
        except StaleElementReferenceException:
            LOGGER.warning(
                "Primeiro resultado ficou stale antes de abrir | tentativa %s de 3",
                tentativa,
            )
        except TimeoutException:
            LOGGER.warning(
                "Pagina de detalhe nao ficou pronta apos abrir o primeiro resultado | tentativa %s de 3",
                tentativa,
            )

    if href_resultado:
        LOGGER.warning(
            "Clique no primeiro resultado nao estabilizou. Abrindo a pagina diretamente pela URL do resultado."
        )
        navegador.get(href_resultado)
        aguardar_clicavel(navegador, XPATHS_RESULTADO["recebimentos_recursos"])
        LOGGER.info("Primeiro resultado aberto com sucesso via URL.")
        return

    raise TimeoutException("Nao foi possivel abrir o primeiro resultado da busca")


def painel_recebimentos_aberto(navegador):
    try:
        botao = navegador.find_element(By.XPATH, XPATHS_RESULTADO["recebimentos_recursos"])
        if botao.get_attribute("aria-expanded") == "true":
            return True
    except StaleElementReferenceException:
        return False

    for xpath_botao in XPATHS_BENEFICIOS["botoes_detalhe"].values():
        botao_detalhe = localizar_opcional(navegador, xpath_botao)
        if botao_detalhe is not None and botao_detalhe.is_displayed():
            return True

    return False


def abrir_secao_recebimentos(navegador):
    LOGGER.info("Expandindo secao de recebimentos de recursos.")
    for tentativa in range(1, 4):
        botao = aguardar_clicavel(navegador, XPATHS_RESULTADO["recebimentos_recursos"])
        descricao = f"botao Recebimentos de recursos (tentativa {tentativa})"

        try:
            clicar_elemento(navegador, descricao, elemento=botao, xpath=XPATHS_RESULTADO["recebimentos_recursos"])
        except Exception:
            LOGGER.exception("Falha na tentativa de clique da secao de recebimentos.")
            raise

        try:
            aguardar_condicao(navegador, painel_recebimentos_aberto, timeout=5)
            LOGGER.info("Secao de recebimentos aberta com sucesso.")
            return
        except TimeoutException:
            LOGGER.warning(
                "Tentativa %s sem confirmacao de abertura da secao de recebimentos.",
                tentativa,
            )

    raise TimeoutException("Nao foi possivel abrir a secao de recebimentos de recursos")


def extrair_blocos_detalhe(navegador):
    dados = {}
    blocos = navegador.find_elements(By.XPATH, XPATHS_RESULTADO["blocos_detalhe"])

    for bloco in blocos:
        rotulos = bloco.find_elements(By.TAG_NAME, "strong")
        valores = bloco.find_elements(By.TAG_NAME, "span")
        if not rotulos or not valores:
            continue

        chave = rotulos[0].text.strip().rstrip(":")
        valor = valores[0].text.strip()
        if chave and valor:
            dados[chave] = valor

    return dados


def extrair_dados_principais(navegador):
    LOGGER.info("Capturando campos principais da pessoa.")
    dados_pessoa = extrair_blocos_detalhe(navegador)
    dados_pessoa["Nome"] = obter_texto_ou_nulo(navegador, XPATHS_RESULTADO["nome"])
    dados_pessoa["CPF"] = obter_texto_ou_nulo(navegador, XPATHS_RESULTADO["cpf"])
    dados_pessoa["NIS"] = obter_texto_ou_nulo(navegador, XPATHS_RESULTADO["nis"])
    dados_pessoa["Localidade"] = obter_texto_ou_nulo(navegador, XPATHS_RESULTADO["localidade"])
    dados_filtrados = {chave: valor for chave, valor in dados_pessoa.items() if valor}
    registrar_dados_pessoa(dados_filtrados)
    return dados_filtrados


def normalizar_espacos(valor):
    return " ".join(valor.split())


def contar_janelas(navegador):
    return len(navegador.window_handles)


def contar_modais_visiveis(navegador):
    return len(
        [
            modal
            for modal in navegador.find_elements(By.XPATH, XPATHS_BENEFICIOS["modal_detalhe"])
            if modal.is_displayed()
        ]
    )


def localizar_modal_visivel(navegador):
    modais_visiveis = [
        modal
        for modal in navegador.find_elements(By.XPATH, XPATHS_BENEFICIOS["modal_detalhe"])
        if modal.is_displayed()
    ]
    if not modais_visiveis:
        return None
    return modais_visiveis[-1]


def extrair_campos_dt_dd(elemento: WebElement):
    detalhes = {}
    descricoes = elemento.find_elements(By.XPATH, ".//dt")

    for descricao in descricoes:
        rotulo = normalizar_espacos(descricao.text.strip().rstrip(":"))
        valor = descricao.find_elements(By.XPATH, "./following-sibling::dd[1]")
        if not rotulo or not valor:
            continue

        texto_valor = normalizar_espacos(valor[0].text.strip())
        if texto_valor:
            detalhes[rotulo] = texto_valor

    return detalhes


def extrair_campos_detalhe(elemento: WebElement):
    detalhes = {}
    detalhes.update(extrair_campos_dt_dd(elemento))

    blocos = elemento.find_elements(By.XPATH, XPATHS_BENEFICIOS["blocos_detalhe"])

    for bloco in blocos:
        rotulos = bloco.find_elements(By.TAG_NAME, "strong")
        valores = bloco.find_elements(By.TAG_NAME, "span")
        if not rotulos or not valores:
            continue

        chave = normalizar_espacos(rotulos[0].text.strip().rstrip(":"))
        valor = normalizar_espacos(valores[0].text.strip())
        if chave and valor:
            detalhes[chave] = valor

    return detalhes


def extrair_tabelas_detalhe(elemento: WebElement):
    tabelas = []

    for indice, tabela in enumerate(elemento.find_elements(By.XPATH, XPATHS_BENEFICIOS["tabelas"]), start=1):
        linhas_extraidas = []

        for linha in tabela.find_elements(By.XPATH, XPATHS_BENEFICIOS["linhas_tabela"]):
            celulas = [
                normalizar_espacos(celula.text.strip())
                for celula in linha.find_elements(By.XPATH, XPATHS_BENEFICIOS["celulas_tabela"])
                if celula.text.strip()
            ]
            if celulas:
                linhas_extraidas.append(celulas)

        if linhas_extraidas:
            tabelas.append(
                {
                    "indice": indice,
                    "linhas": linhas_extraidas,
                }
            )

    return tabelas


def container_tem_conteudo_detalhe(elemento: WebElement):
    return bool(extrair_campos_detalhe(elemento) or extrair_tabelas_detalhe(elemento))


def aguardar_abertura_detalhe_beneficio(
    navegador,
    xpath_container,
    url_anterior,
    quantidade_modais_antes,
    quantidade_janelas_antes,
):
    def detalhe_aberto(driver):
        if localizar_visivel_opcional(driver, xpath_container) is not None:
            return True
        if contar_janelas(driver) > quantidade_janelas_antes:
            return True
        if driver.current_url != url_anterior:
            return True
        if contar_modais_visiveis(driver) > quantidade_modais_antes:
            return True
        return False

    aguardar_condicao(navegador, detalhe_aberto, timeout=TIMEOUT)


def localizar_container_detalhe(navegador, xpath_container, url_anterior, janela_original):
    container = localizar_visivel_opcional(navegador, xpath_container)
    if container is not None:
        return container, "container_especifico"

    if contar_janelas(navegador) > 1:
        for identificador_janela in navegador.window_handles:
            if identificador_janela != janela_original:
                navegador.switch_to.window(identificador_janela)
                aguardar_pagina_pronta(navegador)
                container = localizar_visivel_opcional(navegador, xpath_container)
                if container is not None:
                    return container, "nova_janela"
                return navegador.find_element(By.TAG_NAME, "body"), "nova_janela"

    modal = localizar_modal_visivel(navegador)
    if modal is not None:
        container = localizar_visivel_opcional(modal, xpath_container.replace("//*", ".//*", 1))
        if container is not None:
            return container, "modal"
        return modal, "modal"

    if navegador.current_url != url_anterior:
        aguardar_pagina_pronta(navegador)
        container = localizar_visivel_opcional(navegador, xpath_container)
        if container is not None:
            return container, "navegacao"
        return navegador.find_element(By.TAG_NAME, "body"), "navegacao"

    return navegador.find_element(By.TAG_NAME, "body"), "body"


def aguardar_conteudo_detalhe(navegador, xpath_container, url_anterior, janela_original):
    def conteudo_pronto(driver):
        container, _ = localizar_container_detalhe(driver, xpath_container, url_anterior, janela_original)
        return container_tem_conteudo_detalhe(container)

    aguardar_condicao(navegador, conteudo_pronto, timeout=TIMEOUT)
    return localizar_container_detalhe(navegador, xpath_container, url_anterior, janela_original)


def fechar_detalhe_beneficio(navegador, url_anterior, janela_original, contexto):
    if contexto == "modal":
        modal = localizar_modal_visivel(navegador)
        if modal is not None:
            botoes_fechar = [
                botao
                for botao in modal.find_elements(By.XPATH, XPATHS_BENEFICIOS["botao_fechar_modal"])
                if botao.is_displayed()
            ]
            if botoes_fechar:
                clicar_elemento(navegador, "botao Fechar detalhe do beneficio", elemento=botoes_fechar[0])
                aguardar_condicao(
                    navegador,
                    lambda driver: localizar_modal_visivel(driver) is None,
                    timeout=TIMEOUT,
                )
                return

    if contexto == "nova_janela":
        navegador.close()
        navegador.switch_to.window(janela_original)
        aguardar_pagina_pronta(navegador)
        return

    if navegador.current_url != url_anterior:
        navegador.back()
        aguardar_condicao(navegador, lambda driver: driver.current_url == url_anterior, timeout=TIMEOUT)
        aguardar_pagina_pronta(navegador)
        aguardar_clicavel(navegador, XPATHS_RESULTADO["recebimentos_recursos"])


def extrair_detalhe_beneficio(navegador, programa, xpath_botao, xpath_container):
    LOGGER.info("Abrindo detalhe do beneficio: %s", programa)
    url_anterior = navegador.current_url
    janela_original = navegador.current_window_handle
    quantidade_modais_antes = contar_modais_visiveis(navegador)
    quantidade_janelas_antes = contar_janelas(navegador)
    clicar(navegador, xpath_botao, f"botao Detalhar {programa}")
    aguardar_abertura_detalhe_beneficio(
        navegador,
        xpath_container,
        url_anterior,
        quantidade_modais_antes,
        quantidade_janelas_antes,
    )
    container, contexto = aguardar_conteudo_detalhe(
        navegador,
        xpath_container,
        url_anterior,
        janela_original,
    )
    LOGGER.info(
        "Contexto do detalhe %s: tipo=%s | url_atual=%s",
        programa,
        contexto,
        navegador.current_url,
    )
    detalhes = extrair_campos_detalhe(container)
    tabelas = extrair_tabelas_detalhe(container)

    fechar_detalhe_beneficio(navegador, url_anterior, janela_original, contexto)
    if navegador.current_url == url_anterior and not painel_recebimentos_aberto(navegador):
        abrir_secao_recebimentos(navegador)

    return {
        "programa": programa,
        "detalhes": detalhes,
        "tabelas": tabelas,
    }


def extrair_beneficios(navegador):
    LOGGER.info("Extraindo detalhes dos beneficios.")
    beneficios = []

    for programa, xpath_botao in XPATHS_BENEFICIOS["botoes_detalhe"].items():
        xpath_container = XPATHS_BENEFICIOS["containers_detalhe"][programa]
        botao = localizar_opcional(navegador, xpath_botao)
        if botao is None or not botao.is_displayed():
            continue
        beneficios.append(extrair_detalhe_beneficio(navegador, programa, xpath_botao, xpath_container))

    registrar_beneficios(beneficios)
    return beneficios


def montar_resposta_sucesso(consulta, dados_pessoa, evidencia_base64, beneficios):
    return {
        "sucesso": True,
        "consulta": consulta,
        "pessoa": dados_pessoa,
        "beneficios": beneficios,
        "evidencia_base64": evidencia_base64,
        "armazenamento": montar_metadados_armazenamento(consulta),
        "mensagem": None,
    }


def montar_resposta_erro(consulta, mensagem, evidencia_base64=None):
    return {
        "sucesso": False,
        "consulta": consulta,
        "mensagem": mensagem,
        "evidencia_base64": evidencia_base64,
        "armazenamento": montar_metadados_armazenamento(consulta),
    }


def normalizar_mensagem_erro_interno(exc: Exception) -> str:
    if isinstance(exc, SessionNotCreatedException):
        texto = str(exc)
        if "DevToolsActivePort" in texto or "Chrome failed to start" in texto:
            return (
                "Nao foi possivel iniciar o Chrome neste contexto de execucao. "
                "Execute a automacao em uma sessao interativa do Windows ou revise as permissoes do ambiente."
            )
    return f"Erro interno na automacao: {exc}"


def executar_automacao(termo_consulta, filtros_checkbox=None, headless=True, consulta_id=None):
    consulta = montar_metadados_consulta(
        termo_consulta=termo_consulta,
        filtros_checkbox=filtros_checkbox,
        consulta_id=consulta_id,
    )
    filtros_selecionados = filtros_marcados(consulta["filtros"])
    navegador = None
    try:
        navegador = configurar_driver(headless=headless)
        preencher_formulario_busca(
            navegador,
            consulta["termo"],
            filtros_checkbox=filtros_selecionados,
        )
        consultar_busca(navegador)
        abrir_primeiro_resultado(navegador)
        abrir_secao_recebimentos(navegador)
        dados_pessoa = extrair_dados_principais(navegador)
        beneficios = extrair_beneficios(navegador)
        evidencia = capturar_evidencia_base64(navegador)
        resultado = montar_resposta_sucesso(consulta, dados_pessoa, evidencia, beneficios)
        registrar_resultado_execucao(resultado)
        return resultado
    except TimeoutException:
        evidencia = capturar_evidencia_base64(navegador) if navegador else None
        mensagem = extrair_mensagem_alerta(navegador) if navegador else None
        if not mensagem:
            mensagem = "Nao foi possivel retornar os dados no tempo de resposta solicitado"
        resultado = montar_resposta_erro(
            consulta,
            mensagem,
            evidencia,
        )
        registrar_resultado_execucao(resultado)
        return resultado
    except ValueError as exc:
        LOGGER.warning("Falha de validacao da automacao: %s", exc)
        resultado = montar_resposta_erro(
            consulta,
            str(exc),
            None,
        )
        registrar_resultado_execucao(resultado)
        return resultado
    except Exception as exc:
        LOGGER.exception("Erro no processamento da automacao.")
        evidencia = capturar_evidencia_base64(navegador) if navegador else None
        resultado = montar_resposta_erro(
            consulta,
            normalizar_mensagem_erro_interno(exc),
            evidencia,
        )
        registrar_resultado_execucao(resultado)
        return resultado
    finally:
        fechar_driver(navegador)


def fechar_driver(navegador):
    if navegador is not None:
        navegador.quit()


def parse_args():
    parser = argparse.ArgumentParser(description="Automacao do Portal da Transparencia")
    parser.add_argument("--query", required=True, help="Nome, CPF ou NIS da pessoa consultada")

    for nome_checkbox, argumento_checkbox in ARGUMENTOS_CHECKBOX.items():
        parser.add_argument(
            f"--{argumento_checkbox}",
            action="store_true",
            dest=nome_checkbox,
            help=f"Aplica o filtro {nome_checkbox.replace('_', ' ')}",
        )

    parser.add_argument(
        "--headed",
        action="store_true",
        help="Executa o navegador com interface visual",
    )
    parser.add_argument(
        "--upload-google",
        action="store_true",
        help="Envia o resultado JSON para Google Drive e Google Sheets quando configurados no .env",
    )
    return parser.parse_args()


def montar_payload_automacao(args):
    filtros = {
        nome_checkbox: bool(getattr(args, nome_checkbox, False))
        for nome_checkbox in XPATHS_CHECKBOX
    }
    return {
        "query": args.query,
        "filters": filtros,
        "options": {
            "headed": bool(args.headed),
        },
    }


def executar_automacao_por_payload(payload):
    query = payload.get("query")
    filters = payload.get("filters")
    options = payload.get("options") or {}

    return executar_automacao(
        termo_consulta=query,
        filtros_checkbox=filters,
        headless=not bool(options.get("headed", False)),
    )


def main():
    args = parse_args()
    payload = montar_payload_automacao(args)
    resultado = executar_automacao_por_payload(payload)
    if args.upload_google:
        resultado = enviar_resultado_google_se_configurado(resultado)
    print(json.dumps(resultado, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
