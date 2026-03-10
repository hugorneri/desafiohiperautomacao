URL = "https://portaldatransparencia.gov.br/pessoa-fisica/busca/lista?pagina=1&tamanhoPagina=10"

TIMEOUT = 20

XPATHS_BUSCA = {
    "input_termo": "//input[@type='search']",
    "bt_refine_busca": "//span[normalize-space()='Refine a Busca']",
    "bt_consultar": "//button[@id='btnConsultarPF']",
    "mensagem_alerta": "//*[contains(@class,'alert') or contains(@class,'mensagem') or contains(@class,'message')]",
    "resultado_primeiro_link": "(//a[contains(@class,'link-busca-nome')])[1]",
}

XPATHS_CHECKBOX = {
    "beneficiario_programa_social": "//label[@for='beneficiarioProgramaSocial']",
    "sancao_vigente": "//label[@for='sancaoVigente']",
    "ocupante_imovel_funcional": "//label[@for='ocupanteImovelFuncional']",
    "possui_contrato": "//label[@for='possuiContrato']",
    "favorecido_recurso_publico": "//label[@for='favorecidoRecurso']",
    "emitente_nfe": "//label[@for='emitenteNfe']",
}

XPATHS_RESULTADO = {
    "nome": "//div[.//strong[normalize-space(.)='Nome']]/span",
    "cpf": "//div[.//strong[normalize-space(.)='CPF']]/span",
    "nis": "//div[.//strong[normalize-space(.)='NIS']]/span",
    "localidade": "//div[.//strong[normalize-space(.)='Localidade']]/span",
    "titulo_relacao": (
        "//*[contains(normalize-space(.),'Panorama da relacao da pessoa com o Governo Federal') "
        "or contains(normalize-space(.),'Panorama da relacao da pessoa com o Governo Federal')]"
    ),
    "recebimentos_recursos": (
        "//button[@aria-controls='accordion-recebimentos-recursos' "
        "and .//span[normalize-space(.)='Recebimentos de recursos']]"
    ),
    "painel_recebimentos_recursos": "//*[@id='accordion-recebimentos-recursos']",
    "blocos_detalhe": "//div[./strong and ./span]",
}

XPATHS_BENEFICIOS = {
    "botoes_detalhe": {
        "Auxílio Brasil": "//*[@id='btnDetalharAuxilioBrasil']",
        "Auxílio Emergencial": "//*[@id='btnDetalharBpc']",
        "Beneficiário de Bolsa Família": "//*[@id='btnDetalharBolsaFamilia']",
        "Novo Bolsa Família": "//*[@id='btnDetalharNovoBolsaFamilia']",
    },
    "containers_detalhe": {
        "Auxílio Emergencial": "//*[@id='detalhe-disponibilizado']",
        "Auxílio Brasil": "//*[@id='detalhe-valores-sacados']",
        "Beneficiário de Bolsa Família": "//*[@id='accordion1']",
        "Novo Bolsa Família": "//*[@id='detalhe']",
    },
    "modal_detalhe": "//*[@role='dialog' or contains(@class,'modal') or contains(@class,'br-modal')]",
    "botao_fechar_modal": ".//button[contains(@aria-label,'Fechar') or contains(., 'Fechar') or contains(., 'Voltar')]",
    "blocos_detalhe": ".//div[./strong and ./span]",
    "tabelas": ".//table[.//tr]",
    "linhas_tabela": ".//tr",
    "celulas_tabela": "./th|./td",
}
