"""ResgataJá — fila inteligente e priorizada de denúncias de resgate de animais.

Aplicação Streamlit de arquivo único (Requisito 9). Todo o código reside neste
`app.py`, organizado nas seções comentadas exigidas pelo Requisito 9.5.

Execução:
    pip install -r requirements.txt
    streamlit run app.py

Testes do motor de priorização, sem subir o Streamlit:
    python app.py --self-test
"""

from __future__ import annotations

import sys

# ── Configuração ──────────────────────────────────────────────────────────────
# Centraliza constantes de cidade, regras do motor de priorização (pesos,
# palavras-chave, limites, limiares e cores) e os conjuntos de domínio
# (tipos de situação, espécies, status e transições). Ajustar a lógica de
# urgência é, por design, editar dados aqui — não código (Requisito 2.12).

# Coordenadas padrão da cidade de demonstração (ajuste manual permitido — Req. 1.7).
CIDADE_PADRAO: dict[str, object] = {
    "nome": "São Paulo",
    "lat": -23.5505,
    "lon": -46.6333,
}

# Dicionário central de regras do Motor de Priorização (Requisito 2.12).
Dicionario_de_Configuracao: dict[str, dict] = {
    # Pesos por tipo de situação, em ordem decrescente de peso (Req. 2.4).
    "pesos_situacao": {
        "ferido/atropelado": 40,
        "preso/encurralado": 34,
        "maus-tratos": 30,
        "emergencias ambientais": 26,
        "filhotes orfãos": 22,
        "animal doente": 18,
        "abandonado": 12,
        "animal perdido": 8,
        "outros": 4,
    },
    # Pontos por palavra-chave encontrada na descrição (Req. 2.5).
    # As chaves estão na forma canônica (minúsculas, sem acento) usada após
    # a normalização aplicada pelo motor (Req. 2.6).
    "palavras_chave": {
        "sangrando": 12,
        "nao se mexe": 12,
        "convulsao": 12,
        "atropelado": 10,
        "filhote": 6,
        "recem nascido": 8,
        "chuva": 5,
        "frio": 5,
        "amarrado": 6,
        "sem agua": 6,
        "agressao": 8,
        "outros": 2,
    },
    # Componente de quantidade de animais (Req. 2.7).
    "quantidade": {
        "pontos_por_animal": 2,
        "contribuicao_maxima": 10,
    },
    # Componente de tempo de espera (Req. 2.8 / 2.9).
    "tempo_espera": {
        "pontos_por_hora": 1,
        "contribuicao_maxima": 20,
    },
    # Faixas de Nível de Urgência por Score (Req. 2.10).
    "limiares_urgencia": {
        "CRÍTICO": (80, 100),
        "ALTO": (60, 79),
        "MÉDIO": (40, 59),
        "BAIXO": (0, 39),
    },
    # Cor associada a cada Nível de Urgência (Req. 2.10 / 4.2).
    "cores_urgencia": {
        "CRÍTICO": "#C62828",
        "ALTO": "#EF6C00",
        "MÉDIO": "#F9A825",
        "BAIXO": "#2E7D32",
    },
}

# Tipos de situação oferecidos no registro, em seleção única (Req. 1.2).
TIPOS_SITUACAO: list[str] = [
    "ferido/atropelado",
    "abandonado",
    "maus-tratos",
    "animal doente",
    "preso/encurralado",
    "filhotes orfãos",
    "emergencias ambientais",
    "animal perdido",
    "outros",
]

# Espécies oferecidas no registro, em seleção única (Req. 1.3).
ESPECIES: list[str] = [
    "cão",
    "gato",
    "silvestres",
    "outros",
]

# Conjunto de valores válidos de Status_da_Denuncia.
STATUS: set[str] = {
    "ABERTA",
    "EM ATENDIMENTO",
    "RESGATADO",
    "NÃO LOCALIZADO",
    "ENCERRADA",
}

# Máquina de estados: transições permitidas por status (Req. 5.1–5.4).
# Estados finais não possuem transição de saída (Req. 5.3).
TRANSICOES: dict[str, set[str]] = {
    "ABERTA": {"EM ATENDIMENTO"},
    "EM ATENDIMENTO": {"RESGATADO", "NÃO LOCALIZADO", "ENCERRADA"},
    "RESGATADO": set(),
    "NÃO LOCALIZADO": set(),
    "ENCERRADA": set(),
}


# ── Banco ─────────────────────────────────────────────────────────────────────
# Conexão SQLite, criação de schema, CRUD de denúncias e transições de status
# atômicas com histórico. A implementar nas tarefas 2.x e 10.1.

import sqlite3
from datetime import datetime
from typing import NamedTuple

# Nome do arquivo de banco SQLite gerado em tempo de execução (Req. 9.3).
BANCO_ARQUIVO: str = "resgata_ja.db"

# Prefixo e formato do Protocolo legível gerado para cada denúncia (Req. 1.11).
# Formato: RJ-AAAAMMDD-NNNN, onde AAAAMMDD é a data do registro e NNNN é um
# sufixo numérico que garante unicidade dentro do dia.
PROTOCOLO_PREFIXO: str = "RJ"

# Número máximo de tentativas de geração de Protocolo antes de desistir, usado
# como salvaguarda contra um loop infinito em caso de colisões persistentes.
_MAX_TENTATIVAS_PROTOCOLO: int = 10000

# Campos da denúncia persistidos a partir do dicionário do formulário. O
# Protocolo, o status e o `criado_em` são definidos pela própria
# `inserir_denuncia` e, por isso, não aparecem aqui.
_CAMPOS_DENUNCIA: tuple[str, ...] = (
    "tipo_situacao",
    "especie",
    "quantidade",
    "descricao",
    "endereco",
    "bairro",
    "latitude",
    "longitude",
    "foto",
    "nome_denunciante",
    "telefone_denunciante",
)


def conectar(arquivo: str = BANCO_ARQUIVO) -> sqlite3.Connection:
    """Abre conexão SQLite com row_factory e foreign_keys habilitado (Req. 9.3).

    Define `sqlite3.Row` como `row_factory` para acesso às colunas por nome e
    ativa a verificação de chaves estrangeiras via `PRAGMA foreign_keys = ON`
    (desligada por padrão no SQLite), garantindo a integridade da FK
    `historico.protocolo → denuncias.protocolo`.

    Args:
        arquivo: Caminho do arquivo de banco. Usa `BANCO_ARQUIVO` por padrão.

    Returns:
        Conexão SQLite configurada e pronta para uso.
    """
    con = sqlite3.connect(arquivo)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con


def criar_schema(con: sqlite3.Connection) -> None:
    """Cria as tabelas `denuncias` e `historico` se não existirem (Req. 5.8).

    O schema reproduz os Data Models do design: `denuncias` guarda cada
    ocorrência registrada (com status, responsável e marcos temporais) e
    `historico` registra, em ordem cronológica, cada mudança de status com
    autor e observação. A FK de `historico` referencia `denuncias.protocolo`.

    Args:
        con: Conexão SQLite aberta por `conectar`.
    """
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS denuncias (
            protocolo TEXT PRIMARY KEY,
            tipo_situacao TEXT NOT NULL,
            especie TEXT NOT NULL,
            quantidade INTEGER NOT NULL,
            descricao TEXT,
            endereco TEXT NOT NULL,
            bairro TEXT NOT NULL,
            latitude REAL NOT NULL,
            longitude REAL NOT NULL,
            foto BLOB,
            nome_denunciante TEXT,
            telefone_denunciante TEXT,
            status TEXT NOT NULL DEFAULT 'ABERTA',
            voluntario_responsavel TEXT,
            associacao_resgate TEXT,
            criado_em TEXT NOT NULL,
            primeiro_atendimento_em TEXT
        )
        """
    )
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS historico (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            protocolo TEXT NOT NULL,
            data_hora TEXT NOT NULL,
            autor TEXT NOT NULL,
            status_anterior TEXT,
            status_novo TEXT NOT NULL,
            observacao TEXT,
            FOREIGN KEY (protocolo) REFERENCES denuncias (protocolo)
        )
        """
    )
    con.commit()


def _gerar_protocolo(con: sqlite3.Connection, agora: datetime) -> str:
    """Gera um Protocolo único e legível no formato `RJ-AAAAMMDD-NNNN` (Req. 1.11).

    `AAAAMMDD` é a data de `agora`; `NNNN` é um sufixo numérico de 4 dígitos
    (zero-preenchido) que sequencia os protocolos do dia. A sequência é derivada
    da contagem de protocolos já existentes para o dia (``COUNT`` com prefixo
    ``RJ-AAAAMMDD-``), começando em 1; em caso de colisão — por exemplo, por
    remoções anteriores ou geração concorrente — incrementa e tenta o próximo
    sufixo até encontrar um protocolo inexistente.

    A verificação de existência é feita contra a tabela `denuncias`, de modo que
    o protocolo retornado é garantidamente ausente no banco no momento da
    checagem; o `INSERT` subsequente, feito na mesma transação de
    `inserir_denuncia`, consolida a unicidade (a PK `protocolo` rejeitaria
    qualquer duplicata com `IntegrityError`).

    Args:
        con: Conexão SQLite (dentro da transação de `inserir_denuncia`).
        agora: Instante do registro, base da porção de data do protocolo.

    Returns:
        Protocolo único no formato `RJ-AAAAMMDD-NNNN`.

    Raises:
        RuntimeError: Se não for possível encontrar um sufixo livre dentro do
            limite de tentativas (`_MAX_TENTATIVAS_PROTOCOLO`), situação que só
            ocorreria com um volume irrealista de protocolos no mesmo dia.
    """
    data = agora.strftime("%Y%m%d")
    prefixo_dia = f"{PROTOCOLO_PREFIXO}-{data}-"

    # Ponto de partida da sequência: quantidade de protocolos já emitidos no dia
    # mais um. Evita varrer desde 1 quando o dia já tem muitos registros.
    linha = con.execute(
        "SELECT COUNT(*) AS total FROM denuncias WHERE protocolo LIKE ?",
        (f"{prefixo_dia}%",),
    ).fetchone()
    sequencia = int(linha["total"]) + 1

    for _ in range(_MAX_TENTATIVAS_PROTOCOLO):
        protocolo = f"{prefixo_dia}{sequencia:04d}"
        existe = con.execute(
            "SELECT 1 FROM denuncias WHERE protocolo = ? LIMIT 1",
            (protocolo,),
        ).fetchone()
        if existe is None:
            return protocolo
        sequencia += 1

    raise RuntimeError(
        "Não foi possível gerar um Protocolo único para o dia "
        f"{data} após {_MAX_TENTATIVAS_PROTOCOLO} tentativas."
    )


def inserir_denuncia(con: sqlite3.Connection, dados: dict) -> str:
    """Insere uma denúncia com status ABERTA em transação e retorna o Protocolo.

    Executa dentro de `with con:` (transação): gera um Protocolo único legível
    via `_gerar_protocolo`, persiste a denúncia com ``status = 'ABERTA'`` e
    ``criado_em`` no instante corrente em ISO-8601, e retorna o Protocolo
    gerado (Req. 1.11).

    Os campos de conteúdo vêm de `dados` (ver `_CAMPOS_DENUNCIA`): entre eles
    ``tipo_situacao``, ``especie`` e ``quantidade`` (obrigatórios no formulário),
    além de ``descricao``, ``endereco``, ``bairro``, ``latitude``, ``longitude``
    e os opcionais ``foto``, ``nome_denunciante`` e ``telefone_denunciante``.
    Campos ausentes em `dados` são persistidos como ``NULL``. O Protocolo, o
    ``status`` e o ``criado_em`` são definidos por esta função e não são lidos de
    `dados`. A validação dos campos é responsabilidade da camada de interface
    (`validar_denuncia`), executada antes desta chamada.

    Comportamento em falha (Req. 1.12): o bloco `with con:` faz *commit* ao sair
    sem exceção e *rollback* automático se qualquer exceção ocorrer dentro dele.
    Em erro de `sqlite3` (ou em `RuntimeError` por esgotamento de tentativas de
    protocolo), a transação sofre rollback e a exceção **propaga** para o
    chamador — nenhum Protocolo definitivo é retornado. Assim, o chamador sabe
    que a persistência falhou e pode exibir a mensagem de falha e preservar os
    valores do formulário para nova tentativa, sem nenhum registro parcial no
    banco.

    Args:
        con: Conexão SQLite aberta por `conectar`.
        dados: Dicionário com os campos da denúncia (ver `_CAMPOS_DENUNCIA`).

    Returns:
        O Protocolo único gerado, no formato `RJ-AAAAMMDD-NNNN`.

    Raises:
        sqlite3.Error: Em qualquer falha de persistência; a transação é
            revertida antes da propagação (nenhum Protocolo definitivo).
        RuntimeError: Se não for possível gerar um Protocolo único (vindo de
            `_gerar_protocolo`); a transação também é revertida.
    """
    agora = datetime.now()
    criado_em = agora.isoformat()

    # `with con:` abre uma transação: faz commit no sucesso e rollback se
    # qualquer exceção escapar do bloco (Req. 1.12). A geração do Protocolo fica
    # dentro da transação para que a checagem de unicidade e o INSERT sejam
    # consistentes entre si.
    with con:
        protocolo = _gerar_protocolo(con, agora)

        colunas = ("protocolo", *_CAMPOS_DENUNCIA, "status", "criado_em")
        valores = (
            protocolo,
            *(dados.get(campo) for campo in _CAMPOS_DENUNCIA),
            "ABERTA",
            criado_em,
        )
        marcadores = ", ".join("?" for _ in colunas)
        nomes_colunas = ", ".join(colunas)
        con.execute(
            f"INSERT INTO denuncias ({nomes_colunas}) VALUES ({marcadores})",
            valores,
        )

    # Só alcançado quando o bloco `with con:` fez commit sem exceção: o
    # Protocolo é definitivo e está persistido.
    return protocolo


# Mapeamento entre a chave do filtro recebida da interface e a coluna persistida
# correspondente em `denuncias`, usada por `listar_denuncias` (Req. 3.2). Apenas
# filtros que mapeiam para colunas reais aparecem aqui. O filtro de Nível de
# Urgência ('nivel') NÃO consta: Nível não é uma coluna armazenada, e sim um
# valor derivado do Score em tempo de execução pelo Motor de Priorização; por
# isso o filtro de 'nivel' é aplicado na camada de lógica pura/interface (ver
# `fila_priorizada`, que já trata 'nivel'), a jusante desta consulta ao banco.
_COLUNA_POR_FILTRO_DENUNCIA: dict[str, str] = {
    "tipo": "tipo_situacao",
    "especie": "especie",
    "bairro": "bairro",
    "status": "status",
}


def listar_denuncias(
    con: sqlite3.Connection, filtros: dict | None = None
) -> list[dict]:
    """Lista denúncias aplicando filtros opcionais sobre colunas persistidas (Req. 3.2, 3.3).

    Monta um ``SELECT * FROM denuncias`` acrescido de uma cláusula ``WHERE``
    construída a partir dos filtros ativos, combinados por ``AND`` (Req. 3.3).
    Cada filtro ativo vira uma condição ``coluna = ?`` com placeholder
    parametrizado — os valores nunca são interpolados na string SQL, evitando
    injeção. Filtros ausentes ou com valor ``None`` são ignorados.

    Esta camada filtra apenas sobre as colunas efetivamente persistidas, dadas
    por `_COLUNA_POR_FILTRO_DENUNCIA`: ``tipo`` → ``tipo_situacao``,
    ``especie``, ``bairro`` e ``status``. O filtro de Nível de Urgência
    (``nivel``) NÃO é tratado aqui, pois Nível não é armazenado: ele é derivado
    do Score em tempo de execução pelo Motor de Priorização. O filtro de
    ``nivel`` é, portanto, aplicado a jusante, na camada de lógica pura/interface
    (ver `fila_priorizada`, que já trata ``nivel``). Chaves de filtro
    desconhecidas são ignoradas.

    Args:
        con: Conexão SQLite aberta por `conectar`.
        filtros: Dicionário opcional de filtros ativos. Reconhece as chaves
            ``tipo``, ``especie``, ``bairro`` e ``status`` (a chave ``nivel``,
            se presente, é ignorada aqui e aplicada a jusante). ``None`` ou
            dicionário vazio retorna todas as denúncias.

    Returns:
        Lista de denúncias, cada uma como `dict` simples (conversão de
        `sqlite3.Row`). Vazia quando nenhuma denúncia satisfaz os filtros.
    """
    filtros = filtros or {}

    condicoes: list[str] = []
    parametros: list[object] = []
    for chave_filtro, coluna in _COLUNA_POR_FILTRO_DENUNCIA.items():
        valor_filtro = filtros.get(chave_filtro)
        if valor_filtro is None:
            continue  # filtro ausente/None: não restringe esta coluna
        condicoes.append(f"{coluna} = ?")
        parametros.append(valor_filtro)

    sql = "SELECT * FROM denuncias"
    if condicoes:
        sql += " WHERE " + " AND ".join(condicoes)

    linhas = con.execute(sql, parametros).fetchall()
    return [dict(linha) for linha in linhas]


def obter_denuncia(con: sqlite3.Connection, protocolo: str) -> dict | None:
    """Retorna a denúncia de um Protocolo como `dict`, ou None se não existir.

    Consulta a tabela `denuncias` pela chave primária ``protocolo`` com
    placeholder parametrizado (sem interpolação de valores). Converte a
    `sqlite3.Row` resultante em um `dict` simples.

    Args:
        con: Conexão SQLite aberta por `conectar`.
        protocolo: Protocolo legível da denúncia (ex.: ``RJ-AAAAMMDD-NNNN``).

    Returns:
        A denúncia como `dict`, ou ``None`` quando o Protocolo não existe.
    """
    linha = con.execute(
        "SELECT * FROM denuncias WHERE protocolo = ?",
        (protocolo,),
    ).fetchone()
    return dict(linha) if linha is not None else None


def listar_historico(con: sqlite3.Connection, protocolo: str) -> list[dict]:
    """Lista o histórico de uma denúncia em ordem cronológica crescente (Req. 5.10).

    Seleciona os itens de `historico` associados ao ``protocolo`` informado,
    ordenados do mais antigo para o mais recente por ``data_hora`` ascendente
    e, em desempate, por ``id`` ascendente (o ``id`` AUTOINCREMENT reflete a
    ordem de inserção, garantindo ordenação estável para itens com o mesmo
    carimbo de tempo). O valor é passado por placeholder parametrizado.

    Args:
        con: Conexão SQLite aberta por `conectar`.
        protocolo: Protocolo da denúncia cujo histórico se deseja listar.

    Returns:
        Lista de itens de histórico como `dict`, em ordem cronológica
        crescente. Vazia quando o Protocolo não possui histórico.
    """
    linhas = con.execute(
        """
        SELECT * FROM historico
        WHERE protocolo = ?
        ORDER BY data_hora ASC, id ASC
        """,
        (protocolo,),
    ).fetchall()
    return [dict(linha) for linha in linhas]


class Resultado(NamedTuple):
    """Resultado de uma operação de transição de status (Req. 5.4, 5.7).

    Estrutura imutável devolvida por `transicionar_status`, indicando se a
    operação foi efetivada e carregando uma mensagem em pt-BR adequada para
    exibição ao usuário (seja de sucesso ou de recusa).

    Attributes:
        ok: ``True`` quando a transição foi efetivada e persistida; ``False``
            quando foi recusada (transição fora da máquina de estados ou
            denúncia que já saiu do estado esperado).
        mensagem: Texto em português do Brasil descrevendo o desfecho.
    """

    ok: bool
    mensagem: str


def transicionar_status(
    con: sqlite3.Connection,
    protocolo: str,
    novo_status: str,
    autor: str,
    observacao: str,
    associacao: str | None = None,
) -> Resultado:
    """Aplica uma transição de status com histórico, de forma atômica (Req. 5).

    Implementa a máquina de estados de `TRANSICOES` (Req. 5.1–5.4) e a regra de
    concorrência do Req. 5.7. O fluxo é:

    1. Lê a denúncia por `obter_denuncia` para descobrir o ``status_anterior``.
       Se o Protocolo não existe, recusa sem tocar o banco.
    2. Valida ``novo_status`` contra ``TRANSICOES[status_anterior]``. Se a
       transição não é prevista pela máquina de estados, **recusa sem tocar o
       banco** (Req. 5.4) e, portanto, sem gravar histórico (Req. 5.9).
    3. Aplica a mudança via ``UPDATE ... WHERE protocolo = ? AND status = ?``,
       usando o ``status_anterior`` esperado como guarda de concorrência: se
       outra parte já alterou o status entre a leitura e o ``UPDATE``, o
       ``rowcount`` é 0 e a ação é recusada (Req. 5.7), também sem histórico.
    4. No mesmo ``with con:`` (uma única transação — Req. 5.8), grava o item de
       `historico` com data/hora (ISO-8601), autor, status anterior, novo
       status e observação. Status e histórico são aplicados juntos ou nenhum.

    Para a tomada (ABERTA → EM ATENDIMENTO), o ``UPDATE`` também grava
    ``voluntario_responsavel`` (o ``autor``), ``associacao_resgate`` e define
    ``primeiro_atendimento_em`` apenas na primeira vez, sem sobrescrever um
    valor já presente, via ``COALESCE(primeiro_atendimento_em, ?)`` (Req. 5.6,
    6.4). Nas demais transições válidas (EM ATENDIMENTO → RESGATADO / NÃO
    LOCALIZADO / ENCERRADA), apenas o ``status`` é alterado, com a mesma guarda
    de concorrência no ``WHERE``.

    A guarda autoritativa de concorrência é a cláusula ``WHERE`` do ``UPDATE``;
    a leitura inicial serve para calcular o ``status_anterior`` e validar contra
    a máquina de estados antes de qualquer escrita.

    Args:
        con: Conexão SQLite aberta por `conectar`.
        protocolo: Protocolo da denúncia a transicionar.
        novo_status: Status de destino pretendido (ex.: ``EM ATENDIMENTO``).
        autor: Autor da mudança; na tomada, também o voluntário responsável.
        observacao: Observação livre registrada no histórico.
        associacao: Associação de resgate (nome/CNPJ), usada apenas na tomada.

    Returns:
        `Resultado` com ``ok=True`` e mensagem de sucesso quando a transição é
        efetivada; ``ok=False`` e mensagem de recusa em pt-BR quando a denúncia
        não existe, a transição é inválida (Req. 5.4) ou a denúncia já saiu do
        estado esperado (Req. 5.7). Em recusa, nada é escrito no banco (Req. 5.9).
    """
    denuncia = obter_denuncia(con, protocolo)
    if denuncia is None:
        return Resultado(False, f"Denúncia {protocolo} não encontrada.")

    status_anterior = denuncia["status"]

    # Validação contra a máquina de estados ANTES de qualquer escrita (Req. 5.4):
    # transições fora de TRANSICOES são recusadas sem tocar o banco, logo sem
    # gravar histórico (Req. 5.9).
    if novo_status not in TRANSICOES.get(status_anterior, set()):
        return Resultado(
            False,
            f"Transição de '{status_anterior}' para '{novo_status}' não é "
            "permitida.",
        )

    agora_iso = datetime.now().isoformat()
    tomada = status_anterior == "ABERTA" and novo_status == "EM ATENDIMENTO"

    # Tudo na mesma transação: ou status + histórico são aplicados juntos, ou
    # nada é persistido (atomicidade — Req. 5.8).
    with con:
        if tomada:
            # Tomada: grava responsável/associação e define o primeiro
            # atendimento apenas na primeira vez (COALESCE não sobrescreve um
            # valor já presente — Req. 6.4). A guarda WHERE status = 'ABERTA'
            # garante a regra de concorrência (Req. 5.7).
            cursor = con.execute(
                """
                UPDATE denuncias
                SET status = ?,
                    voluntario_responsavel = ?,
                    associacao_resgate = ?,
                    primeiro_atendimento_em = COALESCE(primeiro_atendimento_em, ?)
                WHERE protocolo = ? AND status = 'ABERTA'
                """,
                (novo_status, autor, associacao, agora_iso, protocolo),
            )
        else:
            # Demais transições válidas: só o status muda, com guarda de
            # concorrência pelo status esperado (Req. 5.7).
            cursor = con.execute(
                """
                UPDATE denuncias
                SET status = ?
                WHERE protocolo = ? AND status = ?
                """,
                (novo_status, protocolo, status_anterior),
            )

        if cursor.rowcount == 0:
            # Outra parte já alterou o status entre a leitura e o UPDATE: a ação
            # é recusada. O `with con:` ainda fará commit, mas nada foi alterado
            # (nenhuma linha afetada) e nenhum histórico foi inserido (Req. 5.7,
            # 5.9). O estado atual da denúncia é preservado.
            return Resultado(
                False,
                "A denúncia já está sendo atendida por outro voluntário ou já "
                "foi encerrada.",
            )

        # Histórico gravado na MESMA transação do UPDATE (Req. 5.8).
        con.execute(
            """
            INSERT INTO historico
                (protocolo, data_hora, autor, status_anterior, status_novo,
                 observacao)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (protocolo, agora_iso, autor, status_anterior, novo_status, observacao),
        )

    return Resultado(
        True,
        f"Status atualizado de '{status_anterior}' para '{novo_status}'.",
    )


# ── Dados de Exemplo ───────────────────────────────────────────────────────────
# Geração e seeding de ~30 denúncias fictícias e reset dos dados de demonstração
# (Req. 7.1–7.5). As funções desta seção escrevem diretamente via SQL, pois as
# linhas de demonstração precisam de `status`, `criado_em`,
# `primeiro_atendimento_em`, `voluntario_responsavel` e `associacao_resgate`
# customizados — algo que `inserir_denuncia` (que fixa status=ABERTA e
# criado_em=agora) não oferece. O seeding só popula o banco vazio; o reset
# remove tudo e recria.

import random
from datetime import timedelta

# Semente fixa para que a geração dos dados de demonstração seja determinística
# entre execuções (mesmos bairros, tipos, horários e protocolos), facilitando a
# demonstração e os testes de integração (Req. 7.1–7.3).
_SEMENTE_DEMO: int = 20240101

# Quantidade alvo de denúncias fictícias geradas no seeding (~30 — Req. 7.1).
_QTD_DEMO: int = 30

# Bairros de São Paulo com coordenadas (lat, lon) plausíveis para cada um
# (Req. 7.2). A distribuição das denúncias percorre esta lista, garantindo
# cobertura geográfica variada no Mapa de Ocorrências.
_BAIRROS_SP: list[tuple[str, float, float]] = [
    ("Vila Mariana", -23.5890, -46.6340),
    ("Pinheiros", -23.5670, -46.7020),
    ("Mooca", -23.5580, -46.6000),
    ("Santana", -23.5040, -46.6290),
    ("Tatuapé", -23.5400, -46.5760),
    ("Lapa", -23.5280, -46.7050),
    ("Butantã", -23.5710, -46.7230),
    ("Itaquera", -23.5410, -46.4710),
    ("Jardim Paulista", -23.5680, -46.6560),
    ("Moema", -23.6000, -46.6640),
    ("Vila Madalena", -23.5540, -46.6900),
    ("Ipiranga", -23.5920, -46.6090),
    ("Perdizes", -23.5370, -46.6770),
    ("Santo Amaro", -23.6540, -46.7080),
    ("Penha", -23.5270, -46.5420),
]

# Catálogo de descrições fictícias agrupadas por tipo de situação. Cada
# descrição inclui palavras-chave do `Dicionario_de_Configuracao` (sangrando,
# filhote, atropelado, chuva, frio, amarrado, sem água, convulsão, agressão,
# etc.) para que os Scores variem entre os níveis de urgência e a demonstração
# fique rica (Req. 7.3). As chaves cobrem todos os `TIPOS_SITUACAO`.
_DESCRICOES_POR_TIPO: dict[str, list[str]] = {
    "ferido/atropelado": [
        "Cachorro atropelado na avenida, está sangrando e não se mexe.",
        "Gato atropelado perto do mercado, sangrando bastante na pata.",
        "Animal atropelado com convulsão, precisa de socorro urgente.",
    ],
    "abandonado": [
        "Filhote abandonado em caixa de papelão na calçada, sem água.",
        "Cão abandonado amarrado no poste há dias, sem comida nem água.",
        "Gato abandonado no terreno baldio, bem magro e assustado.",
    ],
    "maus-tratos": [
        "Cachorro amarrado curto no quintal sofrendo agressão do dono.",
        "Denúncia de agressão a animal, aparenta estar ferido e sangrando.",
        "Animal mantido sem água e sem comida, sinais de maus-tratos.",
    ],
    "animal doente": [
        "Gato muito doente, apático, não se mexe há horas.",
        "Cão com ferida infeccionada, parece estar com muita dor.",
        "Animal doente tremendo de frio na chuva, precisa de ajuda.",
    ],
    "preso/encurralado": [
        "Gato preso no telhado há dois dias, não consegue descer.",
        "Cão encurralado dentro de bueiro, está sangrando na cabeça.",
        "Filhote preso na grade do portão, chorando muito.",
    ],
    "filhotes orfãos": [
        "Ninhada de filhotes recém-nascidos sem a mãe, sentindo frio.",
        "Filhote órfão recém-nascido encontrado na chuva, muito fraco.",
        "Três filhotes órfãos abandonados, sem água e com fome.",
    ],
    "emergencias ambientais": [
        "Animais em área de enchente após a chuva forte, ilhados.",
        "Pássaro silvestre coberto de óleo, não consegue voar.",
        "Vários animais encurralados por incêndio em área de mata.",
    ],
    "animal perdido": [
        "Cachorro perdido vagando assustado perto da praça.",
        "Gato perdido na vizinhança, parece bem mas está sumido faz dias.",
        "Animal perdido com coleira, aparenta estar sem água e cansado.",
    ],
    "outros": [
        "Situação diversa envolvendo um animal na rua, sem detalhes claros.",
        "Morador relata animal estranho no quintal, pede orientação.",
        "Ocorrência não especificada envolvendo um filhote na calçada.",
    ],
}

# Associações de resgate fictícias usadas ao marcar denúncias como atendidas /
# RESGATADO nos dados de demonstração (Req. 7.3).
_ASSOCIACOES_DEMO: list[str] = [
    "ONG Patas Unidas",
    "Resgate Animal SP",
    "Instituto Amigo dos Bichos — CNPJ 12.345.678/0001-90",
    "Protetores da Zona Leste",
]

# Nomes fictícios de voluntários responsáveis pelas denúncias já atendidas.
_VOLUNTARIOS_DEMO: list[str] = [
    "Ana Souza",
    "Carlos Pereira",
    "Mariana Lima",
    "João Alves",
]


def gerar_dados_demo(
    quantidade: int = _QTD_DEMO, agora: datetime | None = None
) -> list[dict]:
    """Gera ~30 denúncias fictícias para a demonstração (Req. 7.1–7.3).

    Produz, de forma determinística (semente fixa `_SEMENTE_DEMO`), uma lista de
    dicionários prontos para inserção direta via SQL em `denuncias`. As
    denúncias são distribuídas pelos bairros de São Paulo em `_BAIRROS_SP` com
    coordenadas plausíveis (com pequeno jitter por denúncia), cobrem todos os
    `TIPOS_SITUACAO` com descrições ricas em palavras-chave (para variar os
    Scores), usam espécies variadas e têm `criado_em` espalhado pelas últimas
    horas/dias. Algumas denúncias já saem com status `RESGATADO` (com
    `voluntario_responsavel`, `associacao_resgate` e `primeiro_atendimento_em`
    preenchidos), e outras como `EM ATENDIMENTO`, deixando a maioria `ABERTA`.

    Cada dicionário contém todas as colunas de `denuncias` exceto `protocolo`
    (atribuído na inserção, ver `_inserir_demo`): `tipo_situacao`, `especie`,
    `quantidade`, `descricao`, `endereco`, `bairro`, `latitude`, `longitude`,
    `foto`, `nome_denunciante`, `telefone_denunciante`, `status`,
    `voluntario_responsavel`, `associacao_resgate`, `criado_em` (ISO-8601) e
    `primeiro_atendimento_em` (ISO-8601 ou ``None``).

    Args:
        quantidade: Número de denúncias a gerar (padrão `_QTD_DEMO`, ~30).
        agora: Instante de referência para espalhar `criado_em` para trás no
            tempo. Usa `datetime.now()` quando ``None``.

    Returns:
        Lista de dicionários de denúncia prontos para persistência.
    """
    if agora is None:
        agora = datetime.now()
    # Gerador local com semente fixa: não altera o estado global do `random`,
    # mantendo a geração determinística e isolada (pureza prática).
    rnd = random.Random(_SEMENTE_DEMO)

    tipos = list(_DESCRICOES_POR_TIPO.keys())
    denuncias: list[dict] = []

    for indice in range(quantidade):
        bairro, lat_base, lon_base = _BAIRROS_SP[indice % len(_BAIRROS_SP)]
        # Pequeno deslocamento (~até ~500 m) para espalhar os marcadores dentro
        # do bairro em vez de empilhá-los no mesmo ponto.
        latitude = round(lat_base + rnd.uniform(-0.004, 0.004), 6)
        longitude = round(lon_base + rnd.uniform(-0.004, 0.004), 6)

        tipo = tipos[indice % len(tipos)]
        descricao = rnd.choice(_DESCRICOES_POR_TIPO[tipo])
        especie = rnd.choice(ESPECIES)
        quantidade_animais = rnd.randint(1, 8)

        # `criado_em` espalhado pelas últimas ~10 dias e 24 horas, dando tempos
        # de espera variados para o componente de tempo do motor (Req. 7.3).
        horas_atras = rnd.randint(1, 10 * 24)
        criado = agora - timedelta(hours=horas_atras, minutes=rnd.randint(0, 59))

        endereco = f"Rua {bairro} {rnd.randint(1, 1500)}"
        # Contato opcional preenchido na maioria dos casos, alguns sem contato.
        if rnd.random() < 0.75:
            nome_denunciante = rnd.choice(
                ["Pedro", "Juliana", "Marcos", "Beatriz", "Rafael", "Camila"]
            )
            telefone = f"(11) 9{rnd.randint(1000, 9999)}-{rnd.randint(1000, 9999)}"
        else:
            nome_denunciante = None
            telefone = None

        # Distribuição de status: ~20% RESGATADO, ~15% EM ATENDIMENTO, restante
        # ABERTA — garantindo "ao menos algumas RESGATADO" (Req. 7.3) e material
        # para o Painel da Coordenação (atendimentos e resgates).
        sorteio = rnd.random()
        voluntario = None
        associacao = None
        primeiro_atendimento = None
        if sorteio < 0.20:
            status = "RESGATADO"
        elif sorteio < 0.35:
            status = "EM ATENDIMENTO"
        else:
            status = "ABERTA"

        if status in ("EM ATENDIMENTO", "RESGATADO"):
            voluntario = rnd.choice(_VOLUNTARIOS_DEMO)
            associacao = rnd.choice(_ASSOCIACOES_DEMO)
            # Primeiro atendimento ocorre algum tempo após a abertura e antes
            # de `agora`, mantendo coerência temporal para a métrica de tempo
            # médio até o primeiro atendimento (Req. 6.4).
            atraso_maximo = max((agora - criado).total_seconds() / 3600 - 0.5, 0.5)
            atraso_horas = rnd.uniform(0.5, max(atraso_maximo, 0.5))
            primeiro_atendimento = (criado + timedelta(hours=atraso_horas)).isoformat()

        denuncias.append(
            {
                "tipo_situacao": tipo,
                "especie": especie,
                "quantidade": quantidade_animais,
                "descricao": descricao,
                "endereco": endereco,
                "bairro": bairro,
                "latitude": latitude,
                "longitude": longitude,
                "foto": None,
                "nome_denunciante": nome_denunciante,
                "telefone_denunciante": telefone,
                "status": status,
                "voluntario_responsavel": voluntario,
                "associacao_resgate": associacao,
                "criado_em": criado.isoformat(),
                "primeiro_atendimento_em": primeiro_atendimento,
            }
        )

    return denuncias


# Colunas de `denuncias` escritas pelas inserções de demonstração, na ordem usada
# pelo INSERT de `_inserir_demo`. Inclui `protocolo` (gerado na inserção) e os
# campos customizados de status/responsável/tempos que `inserir_denuncia` não
# define.
_COLUNAS_DEMO: tuple[str, ...] = (
    "protocolo",
    "tipo_situacao",
    "especie",
    "quantidade",
    "descricao",
    "endereco",
    "bairro",
    "latitude",
    "longitude",
    "foto",
    "nome_denunciante",
    "telefone_denunciante",
    "status",
    "voluntario_responsavel",
    "associacao_resgate",
    "criado_em",
    "primeiro_atendimento_em",
)


def _protocolo_demo(criado_em_iso: str, sequencia: int) -> str:
    """Monta um Protocolo legível `RJ-AAAAMMDD-NNNN` para uma denúncia demo.

    Usa a data do `criado_em` (ISO-8601) na porção `AAAAMMDD` — consistente com
    o formato de `_gerar_protocolo` — e `sequencia` (1-based) como sufixo de 4
    dígitos. A unicidade é garantida ao combinar a data com o índice global da
    denúncia na geração (ver `_inserir_demo`).

    Args:
        criado_em_iso: Instante de criação da denúncia em ISO-8601.
        sequencia: Número sequencial 1-based da denúncia no lote.

    Returns:
        Protocolo no formato `RJ-AAAAMMDD-NNNN`.
    """
    data = datetime.fromisoformat(criado_em_iso).strftime("%Y%m%d")
    return f"{PROTOCOLO_PREFIXO}-{data}-{sequencia:04d}"


def _inserir_demo(con: sqlite3.Connection, denuncias: list[dict]) -> None:
    """Insere, em uma única transação, as denúncias de demonstração via SQL.

    Escreve diretamente em `denuncias` (sem reutilizar `inserir_denuncia`), pois
    as linhas de demonstração definem `status`, `criado_em`,
    `primeiro_atendimento_em`, `voluntario_responsavel` e `associacao_resgate`
    próprios. O Protocolo de cada denúncia é gerado por `_protocolo_demo` a
    partir da data de `criado_em` e de um sufixo sequencial único no lote,
    evitando colisões mesmo quando várias denúncias compartilham a mesma data.

    Args:
        con: Conexão SQLite aberta por `conectar`.
        denuncias: Denúncias geradas por `gerar_dados_demo`.
    """
    marcadores = ", ".join("?" for _ in _COLUNAS_DEMO)
    nomes_colunas = ", ".join(_COLUNAS_DEMO)
    sql = f"INSERT INTO denuncias ({nomes_colunas}) VALUES ({marcadores})"

    with con:
        for indice, denuncia in enumerate(denuncias, start=1):
            protocolo = _protocolo_demo(denuncia["criado_em"], indice)
            valores = (
                protocolo,
                *(denuncia.get(coluna) for coluna in _COLUNAS_DEMO[1:]),
            )
            con.execute(sql, valores)


def _contar_denuncias(con: sqlite3.Connection) -> int:
    """Retorna a quantidade de denúncias persistidas (`SELECT COUNT(*)`).

    Usado para decidir se o seeding deve rodar: o banco é considerado vazio
    quando a contagem é zero (Req. 7.1).
    """
    linha = con.execute("SELECT COUNT(*) AS total FROM denuncias").fetchone()
    return int(linha["total"])


def semear_dados_demo(con: sqlite3.Connection) -> int:
    """Popula o banco com dados de demonstração apenas quando ele está vazio (Req. 7.1).

    Verifica a contagem de denúncias via `_contar_denuncias`; se houver qualquer
    denúncia, não faz nada (seeding idempotente). Com o banco vazio, gera as
    denúncias fictícias com `gerar_dados_demo` e as insere com `_inserir_demo`.

    Args:
        con: Conexão SQLite aberta por `conectar` (schema já criado).

    Returns:
        O número de denúncias inseridas (0 quando o banco já tinha dados).
    """
    if _contar_denuncias(con) > 0:
        return 0
    denuncias = gerar_dados_demo()
    _inserir_demo(con, denuncias)
    return len(denuncias)


def resetar_dados_demo(con: sqlite3.Connection) -> int:
    """Remove todas as denúncias e o histórico e recria os dados de demonstração (Req. 7.4, 7.5).

    Apaga primeiro `historico` e depois `denuncias` (respeitando a FK
    `historico.protocolo → denuncias.protocolo`), tudo em uma transação, e em
    seguida regenera os dados de demonstração com `gerar_dados_demo` /
    `_inserir_demo`. Diferente de `semear_dados_demo`, o reset recria os dados
    independentemente de o banco estar vazio.

    Args:
        con: Conexão SQLite aberta por `conectar` (schema já criado).

    Returns:
        O número de denúncias recriadas.
    """
    with con:
        # Remove o histórico antes das denúncias para não violar a FK.
        con.execute("DELETE FROM historico")
        con.execute("DELETE FROM denuncias")
    denuncias = gerar_dados_demo()
    _inserir_demo(con, denuncias)
    return len(denuncias)


# ── Motor de Priorização ────────────────────────────────────────────────────────
# Função pura `calcular_prioridade` e auxiliares (normalização, estruturas de
# resultado). Sem Streamlit e sem banco — testável via run_self_tests.
# A função pura `calcular_prioridade` é implementada na tarefa 4.2.

import unicodedata
from datetime import datetime
from typing import NamedTuple


def normalizar(texto: str | None) -> str:
    """Normaliza texto para comparação de palavras-chave (Req. 2.6).

    Converte para minúsculas, remove acentos via decomposição NFKD e colapsa
    sequências de espaços em branco em um único espaço, removendo também os
    espaços nas extremidades. Trata `None` como string vazia, evitando
    `AttributeError` em descrições ausentes.
    """
    if texto is None:
        texto = ""
    # Decompõe caracteres acentuados (ex.: "á" → "a" + acento combinante) e
    # descarta os diacríticos (categoria Unicode "Mn" — Mark, nonspacing).
    decomposto = unicodedata.normalize("NFKD", texto)
    sem_acento = "".join(
        caractere for caractere in decomposto
        if not unicodedata.combining(caractere)
    )
    # Minúsculas e colapso de qualquer espaço em branco em um único espaço.
    return " ".join(sem_acento.lower().split())


class FatorExplicado(NamedTuple):
    """Fator que contribuiu para o Score, de forma imutável (Req. 2.11).

    Attributes:
        fator: Nome do fator considerado (ex.: "tipo de situação",
            "palavras-chave", "quantidade", "tempo de espera").
        pontos: Pontos atribuídos por este fator ao Score bruto.
        palavras_chave: Palavras-chave encontradas e associadas a este fator
            (vazio para fatores que não dependem de palavras-chave).
    """

    fator: str
    pontos: int
    palavras_chave: tuple[str, ...] = ()


class ResultadoPrioridade(NamedTuple):
    """Resultado imutável do Motor de Priorização (Req. 2.1, 2.10, 2.11).

    Attributes:
        score: Score inteiro no intervalo 0–100 após o recorte (clamp).
        nivel: Nível de Urgência derivado do Score
            (CRÍTICO, ALTO, MÉDIO ou BAIXO).
        cor: Cor associada ao Nível de Urgência.
        explicacao: Lista de fatores considerados, cada um com seus pontos
            e as palavras-chave encontradas.
    """

    score: int
    nivel: str
    cor: str
    explicacao: list[FatorExplicado]


def _componente_situacao(tipo_situacao: object) -> int:
    """Pontos do fator tipo de situação (Req. 2.4).

    Usa o peso configurado em ``pesos_situacao`` para o tipo informado. Tipos
    desconhecidos (ausentes, ``None`` ou fora do dicionário) caem no peso de
    ``"outros"`` (0 se nem ``"outros"`` estiver configurado), garantindo que o
    motor seja total. A ordem decrescente de pesos é definida na configuração,
    o que torna este componente monotônico na posição do tipo.
    """
    pesos = Dicionario_de_Configuracao["pesos_situacao"]
    if isinstance(tipo_situacao, str) and tipo_situacao in pesos:
        return int(pesos[tipo_situacao])
    return int(pesos.get("outros", 0))


def _componente_palavras_chave(
    descricao: object,
) -> tuple[int, tuple[str, ...]]:
    """Pontos e palavras-chave encontradas na descrição (Req. 2.5, 2.6).

    Normaliza a descrição e cada palavra-chave configurada com `normalizar`
    (minúsculas, sem acento, espaços colapsados) e verifica, por substring, se
    a forma canônica da palavra-chave ocorre na descrição normalizada. Essa
    dupla normalização torna o reconhecimento invariante a acentos, caixa e
    espaços adjacentes (Req. 2.6). Cada palavra-chave encontrada contribui com
    seus pontos uma única vez.

    Returns:
        Par ``(pontos, palavras_chave)``, onde ``pontos`` é a soma dos pontos
        das palavras-chave encontradas e ``palavras_chave`` é a tupla das
        chaves (forma canônica configurada) encontradas, na ordem do
        dicionário de configuração.
    """
    descricao_normalizada = normalizar(descricao if isinstance(descricao, str) else "")
    pontos = 0
    encontradas: list[str] = []
    for palavra, valor in Dicionario_de_Configuracao["palavras_chave"].items():
        if normalizar(palavra) in descricao_normalizada:
            pontos += int(valor)
            encontradas.append(palavra)
    return pontos, tuple(encontradas)


def _componente_quantidade(quantidade: object) -> int:
    """Pontos do fator quantidade de animais, monotônico e limitado (Req. 2.7).

    Calcula ``pontos_por_animal * quantidade`` e satura em
    ``contribuicao_maxima``: quantidades acima do limiar de saturação não
    aumentam o componente. Quantidades ausentes ou não inteiras são tratadas
    como 1 (mínimo do domínio, Req. 1.4), mantendo o motor total. Valores
    negativos são tratados como 0 para não reduzir o Score abaixo do esperado.
    """
    config = Dicionario_de_Configuracao["quantidade"]
    if isinstance(quantidade, bool) or not isinstance(quantidade, int):
        quantidade_valida = 1
    else:
        quantidade_valida = max(quantidade, 0)
    bruto = int(config["pontos_por_animal"]) * quantidade_valida
    return min(bruto, int(config["contribuicao_maxima"]))


def _componente_tempo_espera(
    tipo_situacao: object, criado_em: object, instante: datetime
) -> int:
    """Pontos do fator tempo de espera, monotônico e limitado (Req. 2.8, 2.9).

    Para o tipo de situação ``abandonado``, o componente é sempre zero
    (Req. 2.9). Para os demais tipos, cresce com o tempo de espera decorrido
    entre ``criado_em`` e ``instante``: calcula as horas fracionárias via
    ``total_seconds() / 3600`` (nunca negativas — esperas negativas são tratadas
    como zero), multiplica por ``pontos_por_hora`` e trunca para inteiro com
    ``int()`` antes de saturar em ``contribuicao_maxima``.

    Decisão de unidade (documentada para alinhar run_self_tests e testes de
    propriedade): as horas são fracionárias e o componente usa truncação por
    ``int()`` do produto ``pontos_por_hora * horas``. A truncação preserva a
    monotonicidade não decrescente em função da espera e mantém a função
    determinística.

    Quando ``criado_em`` ou ``instante`` não são `datetime`, o componente é
    zero (sem base temporal mensurável), mantendo o motor total.
    """
    if normalizar(tipo_situacao if isinstance(tipo_situacao, str) else "") == "abandonado":
        return 0
    if not isinstance(criado_em, datetime) or not isinstance(instante, datetime):
        return 0
    config = Dicionario_de_Configuracao["tempo_espera"]
    segundos = (instante - criado_em).total_seconds()
    horas = max(segundos / 3600, 0.0)
    bruto = int(int(config["pontos_por_hora"]) * horas)
    return min(bruto, int(config["contribuicao_maxima"]))


def _nivel_e_cor(score: int) -> tuple[str, str]:
    """Deriva o Nível de Urgência e sua cor a partir do Score (Req. 2.10).

    Percorre ``limiares_urgencia`` e devolve o nível cujo intervalo fechado
    ``[minimo, maximo]`` contém o Score (que já está recortado em 0–100,
    garantindo que exatamente um nível corresponda). A cor é obtida de
    ``cores_urgencia[nivel]``.

    Returns:
        Par ``(nivel, cor)``.
    """
    config = Dicionario_de_Configuracao
    for nivel, (minimo, maximo) in config["limiares_urgencia"].items():
        if minimo <= score <= maximo:
            return nivel, config["cores_urgencia"][nivel]
    # Defesa: Score sempre está em 0–100 após o clamp, então um dos intervalos
    # casa. Este retorno nunca é alcançado para Scores válidos.
    return "BAIXO", config["cores_urgencia"]["BAIXO"]


def calcular_prioridade(denuncia: dict, instante: datetime) -> ResultadoPrioridade:
    """Calcula o Score, o Nível de Urgência e a explicação de uma denúncia.

    Função PURA (Req. 2.13, 11.4): não lê o relógio (recebe ``instante`` como
    parâmetro), não causa efeitos colaterais e não muta o dicionário de
    entrada. Para entradas iguais produz sempre o mesmo resultado.

    Soma os quatro componentes definidos no `Dicionario_de_Configuracao`:

    1. **Situação** — peso de ``pesos_situacao[tipo_situacao]`` (``outros``/0
       para tipos desconhecidos) — Req. 2.4.
    2. **Palavras-chave** — pontos das palavras-chave configuradas encontradas
       na descrição, com reconhecimento invariante a acento/caixa/espaço — Req.
       2.5, 2.6.
    3. **Quantidade** — ``pontos_por_animal * quantidade`` saturado em
       ``contribuicao_maxima`` (monotônico e limitado) — Req. 2.7.
    4. **Tempo de espera** — zero para ``abandonado`` (Req. 2.9); caso
       contrário cresce com as horas decorridas entre ``criado_em`` e
       ``instante``, saturado em ``contribuicao_maxima`` (Req. 2.8).

    O Score bruto é a soma dos quatro componentes; o Score final é esse bruto
    recortado para o intervalo [0, 100] (Req. 2.2, 2.3) e convertido em inteiro.
    A soma dos pontos dos fatores na explicação é exatamente o Score bruto
    (antes do recorte), satisfazendo a consistência da explicação (Property 8 /
    Req. 2.11). O Nível de Urgência e a cor derivam do Score recortado via
    `_nivel_e_cor` (Req. 2.10).

    Args:
        denuncia: Dicionário com ao menos ``tipo_situacao``, ``descricao``,
            ``quantidade`` e ``criado_em`` (``datetime``). Não é modificado.
        instante: Instante de cálculo (``datetime``), base do tempo de espera.

    Returns:
        `ResultadoPrioridade` imutável com ``score`` (0–100), ``nivel``,
        ``cor`` e ``explicacao`` (um `FatorExplicado` por fator, com os pontos
        efetivamente contribuídos e as palavras-chave encontradas).
    """
    # Leitura sem mutação da entrada: apenas acessos via `.get`.
    tipo_situacao = denuncia.get("tipo_situacao")
    descricao = denuncia.get("descricao")
    quantidade = denuncia.get("quantidade")
    criado_em = denuncia.get("criado_em")

    pontos_situacao = _componente_situacao(tipo_situacao)
    pontos_palavras, palavras_encontradas = _componente_palavras_chave(descricao)
    pontos_quantidade = _componente_quantidade(quantidade)
    pontos_tempo = _componente_tempo_espera(tipo_situacao, criado_em, instante)

    # Score bruto é a soma dos quatro componentes; a explicação registra
    # exatamente esses pontos, de modo que sua soma iguala o bruto (Property 8).
    bruto = pontos_situacao + pontos_palavras + pontos_quantidade + pontos_tempo

    # Clamp para [0, 100] (Req. 2.2 / 2.3). Score é inteiro (Req. 2.1).
    score = int(max(0, min(bruto, 100)))

    nivel, cor = _nivel_e_cor(score)

    explicacao = [
        FatorExplicado("tipo de situação", pontos_situacao),
        FatorExplicado("palavras-chave", pontos_palavras, palavras_encontradas),
        FatorExplicado("quantidade", pontos_quantidade),
        FatorExplicado("tempo de espera", pontos_tempo),
    ]

    return ResultadoPrioridade(score=score, nivel=nivel, cor=cor, explicacao=explicacao)


# ── Componentes de Interface ─────────────────────────────────────────────────────
# Widgets reutilizáveis do Streamlit (selo de urgência, cartão de denúncia,
# painel de explicação, barra de filtros) e a validação pura do formulário.
# A validação pura (tarefa 6.1) não importa Streamlit: recebe um dict de dados
# do formulário e devolve o conjunto de pendências. Os widgets ficam nas
# tarefas 7.3.

import re

# Caracteres aceitos no telefone, além dos dígitos: espaços e "+", "-", "(", ")"
# (Req. 1.9). Usado para rejeitar telefones com qualquer outro caractere.
_TELEFONE_PERMITIDO = re.compile(r"^[0-9+\-() ]*$")

# Tamanho máximo do nome do denunciante, em caracteres (Req. 1.9).
NOME_MAX_CARACTERES: int = 120


def validar_denuncia(dados: dict) -> list[str]:
    """Valida os campos de uma denúncia e retorna as pendências (Req. 1.6, 1.7, 1.9, 1.10).

    Função pura, sem Streamlit nem efeitos colaterais. Aceita a denúncia se, e
    somente se, todas as condições abaixo forem satisfeitas; caso contrário,
    retorna exatamente o conjunto das chaves dos campos pendentes/inválidos,
    de forma determinística (lista ordenada), de modo que uma lista vazia
    significa que a denúncia é válida.

    Condições de aceitação:
        - ``tipo_situacao`` informado (não vazio após `strip`);
        - ``especie`` informada (não vazia após `strip`);
        - ``quantidade`` informada (presente e não ``None``);
        - ``endereco`` não vazio após `strip`;
        - ``bairro`` não vazio após `strip`;
        - ``latitude`` numérica no intervalo [-90, 90];
        - ``longitude`` numérica no intervalo [-180, 180];
        - ``telefone`` (quando informado) contém apenas dígitos, espaços e os
          caracteres ``+ - ( )``;
        - ``nome`` (quando informado) com no máximo 120 caracteres.

    Args:
        dados: Dicionário do formulário com as chaves ``tipo_situacao``,
            ``especie``, ``quantidade``, ``endereco``, ``bairro``,
            ``latitude``, ``longitude`` e, opcionalmente, ``telefone`` e
            ``nome``.

    Returns:
        Lista ordenada e sem repetições das chaves dos campos pendentes ou
        inválidos. Vazia quando a denúncia é válida.
    """
    pendencias: set[str] = set()

    # Campos obrigatórios de texto: ausentes, vazios ou só com espaços (Req. 1.6, 1.10).
    for campo in ("tipo_situacao", "especie", "endereco", "bairro"):
        valor = dados.get(campo)
        if not isinstance(valor, str) or not valor.strip():
            pendencias.add(campo)

    # Quantidade obrigatória: basta estar informada (presente e não None) — Req. 1.10.
    if dados.get("quantidade") is None:
        pendencias.add("quantidade")

    # Latitude obrigatória e no intervalo [-90, 90] (Req. 1.7).
    latitude = dados.get("latitude")
    if not _numero_no_intervalo(latitude, -90, 90):
        pendencias.add("latitude")

    # Longitude obrigatória e no intervalo [-180, 180] (Req. 1.7).
    longitude = dados.get("longitude")
    if not _numero_no_intervalo(longitude, -180, 180):
        pendencias.add("longitude")

    # Telefone opcional: quando informado, apenas dígitos/espaços/"+ - ( )" (Req. 1.9).
    telefone = dados.get("telefone")
    if telefone not in (None, ""):
        if not isinstance(telefone, str) or not _TELEFONE_PERMITIDO.fullmatch(telefone):
            pendencias.add("telefone")

    # Nome opcional: quando informado, no máximo 120 caracteres (Req. 1.9).
    nome = dados.get("nome")
    if nome not in (None, ""):
        if not isinstance(nome, str) or len(nome) > NOME_MAX_CARACTERES:
            pendencias.add("nome")

    return sorted(pendencias)


def _numero_no_intervalo(valor: object, minimo: float, maximo: float) -> bool:
    """Retorna True se `valor` é um número real dentro de [minimo, maximo].

    Trata valores ausentes, não numéricos ou booleanos como fora do intervalo.
    `bool` é rejeitado explicitamente porque é subtipo de `int` em Python e não
    representa uma coordenada válida.
    """
    if isinstance(valor, bool) or not isinstance(valor, (int, float)):
        return False
    return minimo <= valor <= maximo


# Status visíveis na Fila Priorizada e no Mapa de Ocorrências (Req. 3.1 / 4.1).
STATUS_VISIVEIS: frozenset[str] = frozenset({"ABERTA", "EM ATENDIMENTO"})

# Mapeamento entre a chave do filtro e o campo correspondente na denúncia.
# Cada filtro é aplicado por igualdade exata sobre o campo indicado (Req. 3.2).
_CAMPO_POR_FILTRO: dict[str, str] = {
    "nivel": "nivel",
    "tipo": "tipo_situacao",
    "especie": "especie",
    "bairro": "bairro",
    "status": "status",
}


def fila_priorizada(
    denuncias: list[dict], filtros: dict | None = None
) -> list[dict]:
    """Monta a fila priorizada de denúncias visíveis, aplicando filtros (Req. 3.1–3.3).

    Função pura, sem Streamlit nem banco: recebe denúncias que já carregam um
    Score calculado (chave ``score``) e os filtros ativos, e devolve exatamente
    as denúncias com status ABERTA ou EM ATENDIMENTO que satisfazem todos os
    filtros ativos, ordenadas por Score em ordem decrescente. A ordenação é
    estável: denúncias com o mesmo Score preservam a ordem relativa de entrada.

    Cada denúncia é um dicionário que carrega ao menos ``score`` e os campos
    filtráveis: ``status``, ``tipo_situacao``, ``especie``, ``bairro`` e
    ``nivel``. Os filtros são aceitos pelas chaves ``nivel``, ``tipo``,
    ``especie``, ``bairro`` e ``status``; um filtro ausente ou com valor
    ``None`` significa "sem filtragem naquele campo". O filtro de ``status``,
    quando informado, é aplicado dentro do conjunto visível — valores fora de
    ABERTA/EM ATENDIMENTO nunca retornam denúncias, pois os demais status não
    entram na fila (Req. 3.1).

    Args:
        denuncias: Lista de denúncias, cada uma com ``score`` (int) e os campos
            filtráveis. Denúncias com status fora do conjunto visível são
            descartadas.
        filtros: Dicionário opcional de filtros ativos (``nivel``, ``tipo``,
            ``especie``, ``bairro``, ``status``). ``None`` ou dicionário vazio
            não filtra nada além da restrição de status visível.

    Returns:
        Lista das denúncias qualificáveis, ordenada por ``score`` decrescente
        (ordenação estável). Vazia quando nenhuma denúncia se qualifica.
    """
    filtros = filtros or {}

    selecionadas: list[dict] = []
    for denuncia in denuncias:
        # Restrição base: apenas ABERTA ou EM ATENDIMENTO entram na fila (Req. 3.1).
        if denuncia.get("status") not in STATUS_VISIVEIS:
            continue
        # Todos os filtros ativos devem casar por igualdade exata (Req. 3.2/3.3).
        if _satisfaz_filtros(denuncia, filtros):
            selecionadas.append(denuncia)

    # Ordenação estável por Score decrescente (Req. 3.1/3.3). `sorted` em Python
    # é estável, preservando a ordem de entrada em caso de empate de Score.
    selecionadas.sort(key=lambda d: d.get("score", 0), reverse=True)
    return selecionadas


def _satisfaz_filtros(denuncia: dict, filtros: dict) -> bool:
    """Retorna True se a denúncia satisfaz todos os filtros ativos (Req. 3.3).

    Um filtro é "ativo" quando sua chave está presente em `filtros` com valor
    diferente de ``None``. Filtros com chave desconhecida são ignorados. Cada
    filtro ativo exige igualdade exata entre o valor do filtro e o campo
    correspondente da denúncia.
    """
    for chave_filtro, campo in _CAMPO_POR_FILTRO.items():
        valor_filtro = filtros.get(chave_filtro)
        if valor_filtro is None:
            continue  # filtro ausente/None: não filtra este campo
        if denuncia.get(campo) != valor_filtro:
            return False
    return True


# --- Agregações puras do Painel da Coordenação (Req. 6.1–6.5) ---------------------
# Funções puras, sem Streamlit nem banco, que resumem um conjunto de denúncias em
# contagens, tempo médio até o primeiro atendimento e distribuições. Implementam a
# Property 15 (correção das agregações). O instante de referência (`agora`) é um
# parâmetro explícito para preservar a pureza e a testabilidade: a lógica nunca lê
# o relógio internamente.

from datetime import datetime

# Rótulo usado quando um campo de partição (nível/tipo/bairro) está ausente ou
# vazio, de modo que toda denúncia caia em exatamente um balde e as contagens
# das distribuições somem o total do conjunto considerado (partição — Req. 6.5).
ROTULO_SEM_VALOR: str = "(sem informação)"

# Ordem de preferência dos campos que marcam o instante do resgate, usada por
# "resgatadas no dia". O campo `primeiro_atendimento_em` é o único marco temporal
# de atendimento presente no modelo em memória da denúncia; um `resgatado_em`
# opcional, quando fornecido, tem precedência por ser mais específico.
_CAMPOS_INSTANTE_RESGATE: tuple[str, ...] = ("resgatado_em", "primeiro_atendimento_em")


def _parse_iso(valor: object) -> datetime | None:
    """Converte uma string ISO-8601 em `datetime`, ou retorna None se inválida.

    Aceita diretamente um `datetime` já parseado (retornando-o inalterado) e
    trata `None`, strings vazias ou mal formadas como ausência de valor,
    retornando ``None`` em vez de propagar exceção. Mantém a função chamadora
    pura e tolerante a dados incompletos.
    """
    if isinstance(valor, datetime):
        return valor
    if not isinstance(valor, str) or not valor.strip():
        return None
    try:
        return datetime.fromisoformat(valor)
    except ValueError:
        return None


def _instante_resgate(denuncia: dict) -> datetime | None:
    """Retorna o instante de resgate da denúncia, se disponível.

    Usa o primeiro campo preenchido na ordem de `_CAMPOS_INSTANTE_RESGATE`
    (``resgatado_em`` tem precedência sobre ``primeiro_atendimento_em``),
    parseando strings ISO-8601. Retorna ``None`` quando nenhum campo está
    preenchido ou é parseável.
    """
    for campo in _CAMPOS_INSTANTE_RESGATE:
        instante = _parse_iso(denuncia.get(campo))
        if instante is not None:
            return instante
    return None


def contar_por_status(denuncias: list[dict], status: str) -> int:
    """Conta as denúncias cujo `status` é exatamente `status` (Req. 6.1, 6.2).

    Args:
        denuncias: Conjunto de denúncias (dicts com a chave ``status``).
        status: Valor de status procurado, por igualdade exata.

    Returns:
        Número de denúncias com o status informado.
    """
    return sum(1 for d in denuncias if d.get("status") == status)


def contar_resgatadas_total(denuncias: list[dict]) -> int:
    """Conta todas as denúncias com status RESGATADO (Req. 6.3).

    Returns:
        Total de denúncias resgatadas, independentemente da data do resgate.
    """
    return contar_por_status(denuncias, "RESGATADO")


def contar_resgatadas_no_dia(denuncias: list[dict], agora: datetime) -> int:
    """Conta as denúncias RESGATADO cujo resgate ocorreu no dia de `agora` (Req. 6.3).

    Uma denúncia conta para o dia corrente quando tem status RESGATADO e seu
    instante de resgate cai na mesma data (ano, mês e dia) de `agora`. O instante
    de resgate é obtido de `_instante_resgate` — isto é, de ``resgatado_em`` ou,
    na sua ausência, de ``primeiro_atendimento_em`` (documentado em
    `_CAMPOS_INSTANTE_RESGATE`). Denúncias RESGATADO sem qualquer marco temporal
    parseável não são contadas, pois não é possível atribuí-las a um dia.

    Args:
        denuncias: Conjunto de denúncias.
        agora: Instante de referência que define o "dia corrente" (parâmetro
            explícito para manter a função pura e testável).

    Returns:
        Número de denúncias resgatadas na data de `agora`.
    """
    dia = agora.date()
    total = 0
    for d in denuncias:
        if d.get("status") != "RESGATADO":
            continue
        instante = _instante_resgate(d)
        if instante is not None and instante.date() == dia:
            total += 1
    return total


def tempo_medio_primeiro_atendimento(denuncias: list[dict]) -> float | None:
    """Tempo médio, em horas, entre abertura e primeiro atendimento (Req. 6.4).

    Considera apenas o subconjunto de denúncias já atendidas — aquelas com
    ``primeiro_atendimento_em`` preenchido e parseável e com ``criado_em``
    igualmente parseável. Para cada uma, calcula a diferença
    ``primeiro_atendimento_em - criado_em`` e retorna a média aritmética dessas
    diferenças, expressa em horas (float).

    Unidade e caso vazio (decisões documentadas):
        - A média é retornada em **horas** (`timedelta.total_seconds() / 3600`).
        - Quando o subconjunto já atendido é **vazio**, retorna ``None`` (ausência
          de dado), e não ``0``, para distinguir "nenhum atendimento ainda" de
          "atendimento instantâneo".

    Args:
        denuncias: Conjunto de denúncias (dicts com ``criado_em`` e,
            opcionalmente, ``primeiro_atendimento_em``, como strings ISO-8601).

    Returns:
        Média em horas das esperas até o primeiro atendimento, ou ``None`` se
        nenhuma denúncia tiver primeiro atendimento registrado.
    """
    esperas_horas: list[float] = []
    for d in denuncias:
        atendimento = _parse_iso(d.get("primeiro_atendimento_em"))
        if atendimento is None:
            continue  # ainda sem primeiro atendimento: fora do subconjunto
        abertura = _parse_iso(d.get("criado_em"))
        if abertura is None:
            continue  # sem abertura parseável: não há como medir a espera
        delta = atendimento - abertura
        esperas_horas.append(delta.total_seconds() / 3600)
    if not esperas_horas:
        return None
    return sum(esperas_horas) / len(esperas_horas)


def _distribuir_por(denuncias: list[dict], campo: str) -> dict[str, int]:
    """Conta as denúncias agrupando pelo valor de `campo` (partição — Req. 6.5).

    Cada denúncia cai em exatamente um balde: o valor de `campo` quando presente
    e não vazio, ou `ROTULO_SEM_VALOR` caso contrário. Por isso a soma das
    contagens retornadas é sempre igual ao total de denúncias consideradas, o que
    caracteriza uma partição.

    Args:
        denuncias: Conjunto de denúncias.
        campo: Nome do campo usado como chave de agrupamento.

    Returns:
        Dicionário {valor_do_campo: contagem}.
    """
    distribuicao: dict[str, int] = {}
    for d in denuncias:
        valor = d.get(campo)
        if not isinstance(valor, str) or not valor.strip():
            chave = ROTULO_SEM_VALOR
        else:
            chave = valor
        distribuicao[chave] = distribuicao.get(chave, 0) + 1
    return distribuicao


def distribuicao_por_nivel(denuncias: list[dict]) -> dict[str, int]:
    """Distribui as denúncias por Nível de Urgência (partição — Req. 6.5)."""
    return _distribuir_por(denuncias, "nivel")


def distribuicao_por_tipo(denuncias: list[dict]) -> dict[str, int]:
    """Distribui as denúncias por tipo de situação (partição — Req. 6.5)."""
    return _distribuir_por(denuncias, "tipo_situacao")


def distribuicao_por_bairro(denuncias: list[dict]) -> dict[str, int]:
    """Distribui as denúncias por bairro (partição — Req. 6.5)."""
    return _distribuir_por(denuncias, "bairro")


def agregacoes_coordenacao(denuncias: list[dict], agora: datetime) -> dict:
    """Resume um conjunto de denúncias para o Painel da Coordenação (Req. 6.1–6.5).

    Função pura que reúne, em um único dicionário estruturado, todos os
    indicadores do painel: contagens por status, resgates do dia e totais, tempo
    médio até o primeiro atendimento e as distribuições por nível, tipo e bairro.
    Implementa a Property 15 (correção das agregações da coordenação).

    O instante de referência `agora` é recebido como parâmetro — a função nunca
    chama `datetime.now()` internamente — de modo a permanecer determinística e
    testável.

    Args:
        denuncias: Conjunto de denúncias (dicts com ao menos ``status``,
            ``nivel``, ``tipo_situacao``, ``bairro``, ``criado_em`` e
            ``primeiro_atendimento_em``; opcionalmente ``resgatado_em``).
        agora: Instante de referência que define o "dia corrente" para a
            contagem de resgates do dia.

    Returns:
        Dicionário com as chaves:
            - ``abertas`` (int): denúncias com status ABERTA — Req. 6.1.
            - ``em_atendimento`` (int): denúncias EM ATENDIMENTO — Req. 6.2.
            - ``resgatadas_no_dia`` (int): resgatadas na data de `agora` — Req. 6.3.
            - ``resgatadas_total`` (int): total resgatadas — Req. 6.3.
            - ``tempo_medio_primeiro_atendimento_horas`` (float | None): média em
              horas até o primeiro atendimento, ou ``None`` se não houver
              atendimentos — Req. 6.4.
            - ``distribuicao_nivel`` / ``distribuicao_tipo`` /
              ``distribuicao_bairro`` (dict[str, int]): partições cujas contagens
              somam o total do conjunto — Req. 6.5.
    """
    return {
        "abertas": contar_por_status(denuncias, "ABERTA"),
        "em_atendimento": contar_por_status(denuncias, "EM ATENDIMENTO"),
        "resgatadas_no_dia": contar_resgatadas_no_dia(denuncias, agora),
        "resgatadas_total": contar_resgatadas_total(denuncias),
        "tempo_medio_primeiro_atendimento_horas": (
            tempo_medio_primeiro_atendimento(denuncias)
        ),
        "distribuicao_nivel": distribuicao_por_nivel(denuncias),
        "distribuicao_tipo": distribuicao_por_tipo(denuncias),
        "distribuicao_bairro": distribuicao_por_bairro(denuncias),
    }


# Rótulo da opção neutra ("sem filtro") usada nos seletores da barra de filtros.
# Ao retornar o dicionário de filtros, este rótulo é convertido em ``None`` para
# que `fila_priorizada` e `listar_denuncias` tratem o campo como não filtrado.
_FILTRO_TODOS: str = "Todos"

# Tamanho máximo do resumo da descrição exibido no cartão da fila (Req. 3.4),
# para manter os cartões legíveis quando a descrição é longa.
_RESUMO_MAX: int = 160


def selo_urgencia(nivel: str, cor: str) -> None:
    """Renderiza um selo colorido com o Nível de Urgência (Req. 2.10, 3.4, 10.1).

    Usa `st.markdown` com um `<span>` HTML inline (``unsafe_allow_html=True``)
    para exibir o `nivel` sobre um fundo na `cor` informada, mantendo a cor
    consistente com `cores_urgencia`.

    Args:
        nivel: Nível de Urgência a exibir (ex.: ``CRÍTICO``, ``ALTO``).
        cor: Cor de fundo do selo, em formato CSS (ex.: ``#C62828``).
    """
    import streamlit as st

    st.markdown(
        f"<span style='background-color:{cor};color:#FFFFFF;"
        "padding:2px 10px;border-radius:12px;font-weight:600;"
        f"font-size:0.85rem;white-space:nowrap;'>{nivel}</span>",
        unsafe_allow_html=True,
    )


def _tempo_decorrido(criado_em: object, agora: datetime | None = None) -> str:
    """Formata o tempo decorrido desde a abertura em pt-BR (Req. 3.4).

    Converte `criado_em` (string ISO-8601 ou `datetime`) em um texto humano
    relativo a `agora`, como ``"há 3 h"`` ou ``"há 2 dias"``. Trata valores
    ausentes ou não parseáveis devolvendo ``"tempo indisponível"``.

    Args:
        criado_em: Instante de abertura da denúncia (ISO-8601 ou `datetime`).
        agora: Instante de referência; usa `datetime.now()` quando omitido.

    Returns:
        Texto em pt-BR do tempo decorrido, ou ``"tempo indisponível"``.
    """
    if agora is None:
        agora = datetime.now()

    if isinstance(criado_em, datetime):
        aberto = criado_em
    else:
        aberto = _parse_iso(criado_em)

    if aberto is None:
        return "tempo indisponível"

    segundos = (agora - aberto).total_seconds()
    if segundos < 0:
        segundos = 0

    minutos = int(segundos // 60)
    if minutos < 1:
        return "há menos de 1 min"
    if minutos < 60:
        return f"há {minutos} min"

    horas = minutos // 60
    if horas < 24:
        return f"há {horas} h"

    dias = horas // 24
    return f"há {dias} dia" if dias == 1 else f"há {dias} dias"


def cartao_denuncia(d: dict, resultado: ResultadoPrioridade) -> None:
    """Renderiza um cartão de denúncia da Fila Priorizada (Req. 3.4).

    Exibe o Protocolo, o Nível de Urgência (via `selo_urgencia`), o Score, um
    resumo da descrição (truncado quando longa), o bairro e o tempo decorrido
    desde a abertura, calculado a partir de ``d['criado_em']``. Campos ausentes
    são exibidos com um marcador neutro em pt-BR.

    Args:
        d: Denúncia como `dict`, com ao menos ``protocolo``, ``descricao``,
            ``bairro`` e ``criado_em``.
        resultado: `ResultadoPrioridade` da denúncia, fonte do Score, do Nível
            e da cor exibidos no cartão.
    """
    import streamlit as st

    protocolo = d.get("protocolo") or "—"
    bairro = d.get("bairro") or "—"

    descricao = (d.get("descricao") or "").strip()
    if len(descricao) > _RESUMO_MAX:
        resumo = descricao[:_RESUMO_MAX].rstrip() + "…"
    else:
        resumo = descricao or "Sem descrição."

    with st.container(border=True):
        cabecalho, selo = st.columns([3, 1])
        with cabecalho:
            st.markdown(f"**Protocolo:** {protocolo}")
            # Score destacado na cor do Nível de Urgência para leitura rápida,
            # mantendo a cor consistente com `cores_urgencia` (via resultado.cor).
            st.markdown(
                f"<span style='font-size:1.4rem;font-weight:700;"
                f"color:{resultado.cor};'>Score {resultado.score}</span>",
                unsafe_allow_html=True,
            )
        with selo:
            selo_urgencia(resultado.nivel, resultado.cor)

        st.write(resumo)
        st.caption(f"Bairro: {bairro} · Aberta {_tempo_decorrido(d.get('criado_em'))}")


def painel_explicacao(resultado: ResultadoPrioridade) -> None:
    """Lista os fatores que compõem o Score, em pt-BR (Req. 2.11, 3.5).

    Para cada fator da explicação, exibe o nome do fator e os pontos atribuídos
    e, quando houver, as palavras-chave encontradas que contribuíram para o
    Score. Exibe também o total de pontos, correspondente ao Score bruto.

    Args:
        resultado: `ResultadoPrioridade` com a explicação a detalhar.
    """
    import streamlit as st

    st.markdown("**Como o Score foi calculado**")
    for fator in resultado.explicacao:
        st.markdown(f"- {fator.fator}: {fator.pontos} ponto(s)")
        if fator.palavras_chave:
            encontradas = ", ".join(fator.palavras_chave)
            st.caption(f"    Palavras-chave encontradas: {encontradas}")
    # Total dos fatores, correspondente ao Score, para fechar a explicação.
    st.markdown(f"**Total:** {resultado.score} ponto(s) · Nível {resultado.nivel}")


def barra_filtros() -> dict:
    """Renderiza os controles de filtro da Fila Priorizada (Req. 3.2).

    Apresenta, na barra lateral, seletores para Nível de Urgência, tipo de
    situação, espécie, status e um campo de texto para o bairro. A opção neutra
    ``"Todos"`` (ou um bairro em branco) é convertida em ``None`` no dicionário
    retornado, de modo que `fila_priorizada` e `listar_denuncias` tratem o campo
    como não filtrado. As chaves do dicionário são consistentes com essas
    funções: ``nivel``, ``tipo``, ``especie``, ``bairro`` e ``status``.

    Returns:
        Dicionário de filtros com as chaves ``nivel``, ``tipo``, ``especie``,
        ``bairro`` e ``status``; cada valor é o selecionado ou ``None`` quando
        a opção neutra foi escolhida.
    """
    import streamlit as st

    niveis = list(Dicionario_de_Configuracao["cores_urgencia"].keys())
    # Status visíveis na fila (ABERTA, EM ATENDIMENTO) em ordem estável.
    status_visiveis = [s for s in ("ABERTA", "EM ATENDIMENTO") if s in STATUS]

    with st.sidebar:
        st.markdown("### Filtros")
        nivel = st.selectbox("Nível de urgência", [_FILTRO_TODOS, *niveis])
        tipo = st.selectbox("Tipo de situação", [_FILTRO_TODOS, *TIPOS_SITUACAO])
        especie = st.selectbox("Espécie", [_FILTRO_TODOS, *ESPECIES])
        status = st.selectbox("Status", [_FILTRO_TODOS, *status_visiveis])
        bairro = st.text_input("Bairro", value="")

    bairro_limpo = bairro.strip()

    return {
        "nivel": None if nivel == _FILTRO_TODOS else nivel,
        "tipo": None if tipo == _FILTRO_TODOS else tipo,
        "especie": None if especie == _FILTRO_TODOS else especie,
        "bairro": bairro_limpo or None,
        "status": None if status == _FILTRO_TODOS else status,
    }


# ── Páginas ──────────────────────────────────────────────────────────────────────
# pagina_registro, pagina_fila_e_mapa e pagina_coordenacao.
# A implementar nas tarefas 6.3, 7.4, 8.1, 10.5 e 11.3.

# Tamanho máximo da foto anexada ao registro: 10 MB (Req. 1.8).
_FOTO_TAMANHO_MAXIMO: int = 10 * 1024 * 1024

# Rótulos em pt-BR das pendências retornadas por `validar_denuncia`, usados para
# montar as mensagens de campos obrigatórios/inválidos no envio (Req. 1.10).
_ROTULOS_PENDENCIA: dict[str, str] = {
    "tipo_situacao": "Tipo de situação",
    "especie": "Espécie",
    "quantidade": "Quantidade de animais",
    "endereco": "Endereço",
    "bairro": "Bairro",
    "latitude": "Latitude",
    "longitude": "Longitude",
    "telefone": "Telefone",
    "nome": "Nome",
}


def pagina_registro(con: sqlite3.Connection) -> None:
    """Renderiza o formulário de registro de denúncia sem autenticação (Req. 1.1–1.13, 8.2).

    Apresenta ao Cidadão Denunciante um `st.form` em pt-BR com seleção única de
    tipo de situação e espécie, quantidade (1–999), descrição (≤ 2000), endereço
    e bairro obrigatórios, latitude/longitude pré-preenchidas pela cidade padrão
    e ajustáveis dentro dos limites, upload opcional de foto JPG/PNG ≤ 10 MB e
    nome (≤ 120) e telefone opcionais.

    Ao enviar: monta o dicionário de dados e chama `validar_denuncia`. Havendo
    pendências, exibe uma mensagem por campo pendente e preserva os valores já
    digitados (os widgets usam `key`, de modo que o `st.session_state` mantém os
    valores entre reexecuções — Req. 1.10). Sendo válida, chama `inserir_denuncia`
    em `try/except`; no sucesso, calcula Score/Nível via `calcular_prioridade` e
    exibe o Protocolo e o Nível de Urgência com a cor; em falha de persistência,
    exibe mensagem de falha e preserva os valores, sem gerar Protocolo (Req. 1.12).

    Args:
        con: Conexão SQLite aberta por `conectar`.
    """
    import streamlit as st

    st.header("🐾 Registrar denúncia")
    st.caption(
        "Relate um animal em risco. Não é necessário cadastro nem login. "
        "Os campos marcados com * são obrigatórios."
    )

    with st.form("form_registro", clear_on_submit=False):
        tipo_situacao = st.selectbox(
            "Tipo de situação *", TIPOS_SITUACAO, key="reg_tipo_situacao"
        )
        especie = st.selectbox("Espécie *", ESPECIES, key="reg_especie")
        quantidade = st.number_input(
            "Quantidade de animais *",
            min_value=1,
            max_value=999,
            step=1,
            value=1,
            key="reg_quantidade",
        )
        descricao = st.text_area(
            "Descrição da ocorrência",
            max_chars=2000,
            placeholder="Descreva a situação do animal (ex.: está sangrando, não se mexe...).",
            key="reg_descricao",
        )
        endereco = st.text_input(
            "Endereço * (não é necessário o número)", key="reg_endereco"
        )
        bairro = st.text_input("Bairro *", key="reg_bairro")

        col_lat, col_lon = st.columns(2)
        with col_lat:
            latitude = st.number_input(
                "Latitude",
                min_value=-90.0,
                max_value=90.0,
                value=float(CIDADE_PADRAO["lat"]),
                format="%.6f",
                key="reg_latitude",
            )
        with col_lon:
            longitude = st.number_input(
                "Longitude",
                min_value=-180.0,
                max_value=180.0,
                value=float(CIDADE_PADRAO["lon"]),
                format="%.6f",
                key="reg_longitude",
            )

        foto_arquivo = st.file_uploader(
            "Foto da ocorrência (opcional, JPG ou PNG, até 10 MB)",
            type=["jpg", "jpeg", "png"],
            accept_multiple_files=False,
            key="reg_foto",
        )

        st.markdown("**Seus dados (opcionais)**")
        nome = st.text_input("Nome", max_chars=120, key="reg_nome")
        telefone = st.text_input(
            "Telefone", placeholder="(11) 99999-9999", key="reg_telefone"
        )

        enviado = st.form_submit_button("Registrar denúncia")

    if not enviado:
        return

    # Validação da foto opcional: verifica o tamanho antes de ler os bytes (Req. 1.8).
    # Foto inválida não bloqueia o registro — apenas é descartada com aviso.
    foto_bytes: bytes | None = None
    if foto_arquivo is not None:
        if foto_arquivo.size > _FOTO_TAMANHO_MAXIMO:
            st.warning(
                "A foto excede o tamanho máximo de 10 MB e não será anexada. "
                "A denúncia pode ser registrada mesmo assim."
            )
        else:
            foto_bytes = foto_arquivo.getvalue()

    # Monta o dicionário com as chaves esperadas tanto pela validação pura
    # (`nome`, `telefone`) quanto pela persistência (`nome_denunciante`,
    # `telefone_denunciante`, `foto`), além do `criado_em` usado pelo motor.
    agora = datetime.now()
    nome_limpo = nome.strip() if isinstance(nome, str) else nome
    telefone_limpo = telefone.strip() if isinstance(telefone, str) else telefone
    dados: dict = {
        "tipo_situacao": tipo_situacao,
        "especie": especie,
        "quantidade": int(quantidade),
        "descricao": descricao.strip() if isinstance(descricao, str) else descricao,
        "endereco": endereco,
        "bairro": bairro,
        "latitude": float(latitude),
        "longitude": float(longitude),
        "foto": foto_bytes,
        "nome": nome_limpo or None,
        "telefone": telefone_limpo or None,
        "nome_denunciante": nome_limpo or None,
        "telefone_denunciante": telefone_limpo or None,
    }

    pendencias = validar_denuncia(dados)
    if pendencias:
        st.error("Corrija os campos abaixo para registrar a denúncia:")
        for campo in pendencias:
            rotulo = _ROTULOS_PENDENCIA.get(campo, campo)
            st.error(f"• {rotulo}")
        # Os valores digitados são preservados automaticamente pelos widgets
        # com `key` em `st.session_state` na reexecução (Req. 1.10).
        return

    # Denúncia válida: persiste em try/except para tratar falha de persistência
    # sem gerar Protocolo definitivo (Req. 1.11, 1.12).
    try:
        protocolo = inserir_denuncia(con, dados)
    except sqlite3.Error:
        st.error(
            "Não foi possível registrar a denúncia agora devido a uma falha no "
            "sistema. Nenhum protocolo foi gerado. Seus dados foram preservados — "
            "tente enviar novamente."
        )
        return

    # Sucesso: calcula Score/Nível e exibe Protocolo e Nível de Urgência (Req. 1.13).
    denuncia_motor = {
        "tipo_situacao": dados["tipo_situacao"],
        "descricao": dados["descricao"],
        "quantidade": dados["quantidade"],
        "status": "ABERTA",
        "criado_em": agora,
    }
    resultado = calcular_prioridade(denuncia_motor, agora)

    st.success("Denúncia registrada com sucesso!")
    st.markdown(f"**Protocolo:** `{protocolo}`")
    st.markdown(
        f"**Nível de Urgência:** "
        f"<span style='color:{resultado.cor};font-weight:bold'>"
        f"{resultado.nivel}</span> (Score {resultado.score})",
        unsafe_allow_html=True,
    )
    st.info("Guarde o número do protocolo para acompanhar o andamento da ocorrência.")


def pagina_fila_e_mapa(con: sqlite3.Connection) -> None:
    """Renderiza a Fila Priorizada e (nas próximas tarefas) o mapa e as ações (Req. 3, 4, 5, 8.3).

    Monta a página do perfil Voluntário. Carrega todas as denúncias do banco,
    calcula para cada uma o Score, o Nível de Urgência e a explicação via
    `calcular_prioridade` (com ``instante=datetime.now()``), anexa ``score`` e
    ``nivel`` a cada dicionário e guarda um mapa de ``protocolo`` para o
    respectivo `ResultadoPrioridade`, de modo que cartões e detalhes reutilizem
    o mesmo resultado sem recalcular. Em seguida chama `fila_priorizada`, que
    aplica a restrição de status visível (ABERTA / EM ATENDIMENTO) e todos os
    filtros ativos — inclusive o de ``nivel``, que não é coluna persistida — e
    ordena por Score decrescente (Req. 3.1–3.3).

    Renderiza a fila como cartões (`cartao_denuncia`) na ordem de prioridade e
    permite selecionar uma denúncia pelo Protocolo para ver os detalhes com a
    explicação do Score (`painel_explicacao`) — Req. 3.4, 3.5.

    O mapa de ocorrências (tarefa 8.1) e as ações de atendimento e mudança de
    status (tarefa 10.5) serão acrescentados a esta mesma função, nos pontos
    marcados abaixo, reaproveitando ``denuncias_visiveis`` e ``resultados``.

    Args:
        con: Conexão SQLite aberta por `conectar`.
    """
    import streamlit as st

    st.header("🚑 Fila de atendimento")
    st.caption(
        "Denúncias abertas e em atendimento, ordenadas por urgência. "
        "Use os filtros na barra lateral para refinar a lista."
    )

    # Filtros ativos vindos da barra lateral (nível, tipo, espécie, bairro, status).
    filtros = barra_filtros()

    agora = datetime.now()

    # Carrega todas as denúncias. `listar_denuncias` filtra apenas colunas
    # persistidas; o filtro de 'nivel' (derivado do Score) é aplicado a jusante
    # por `fila_priorizada`. Por isso carregamos tudo aqui e deixamos a
    # filtragem completa (incluindo 'nivel' e a restrição de status visível)
    # para `fila_priorizada`.
    denuncias = listar_denuncias(con)

    # Calcula o Score/Nível de cada denúncia e anexa 'score' e 'nivel' ao dict,
    # guardando o ResultadoPrioridade por protocolo para reuso em cartão/detalhe.
    resultados: dict[str, ResultadoPrioridade] = {}
    for d in denuncias:
        resultado = calcular_prioridade(d, agora)
        d["score"] = resultado.score
        d["nivel"] = resultado.nivel
        protocolo = d.get("protocolo")
        if protocolo is not None:
            resultados[protocolo] = resultado

    # Aplica status visível + todos os filtros (inclusive 'nivel') e ordena por
    # Score decrescente (Req. 3.1–3.3).
    denuncias_visiveis = fila_priorizada(denuncias, filtros)

    # (8.1) Mapa de ocorrências (Req. 4.1, 4.2, 4.3, 10.3). Reaproveita
    # `denuncias_visiveis` (já com status ABERTA/EM ATENDIMENTO e todos os
    # filtros ativos aplicados) e colore cada marcador pela cor do seu Nível de
    # Urgência. Usa recursos nativos do Streamlit (pydeck, que acompanha o
    # Streamlit) para permitir cor por ponto, com fallback para `st.map`.
    st.subheader("Mapa de ocorrências")

    def _hex_para_rgb(cor_hex: str) -> list[int]:
        """Converte uma cor hexadecimal ('#RRGGBB') em uma lista [r, g, b].

        Aceita a cor com ou sem o prefixo '#'. Em qualquer entrada inesperada,
        retorna um cinza neutro para não quebrar a renderização do mapa.
        """
        texto = (cor_hex or "").lstrip("#")
        if len(texto) == 6:
            try:
                return [int(texto[i : i + 2], 16) for i in (0, 2, 4)]
            except ValueError:
                pass
        return [120, 120, 120]

    # Monta os pontos do mapa somente a partir de denúncias com coordenadas
    # numéricas válidas (latitude/longitude são colunas REAL, mas podem vir
    # nulas). A cor vem do ResultadoPrioridade (mesma de `cores_urgencia`).
    pontos_mapa: list[dict] = []
    for d in denuncias_visiveis:
        lat = d.get("latitude")
        lon = d.get("longitude")
        if lat is None or lon is None:
            continue
        try:
            lat_f = float(lat)
            lon_f = float(lon)
        except (TypeError, ValueError):
            continue

        protocolo = d.get("protocolo")
        resultado = resultados.get(protocolo)
        nivel = d.get("nivel") or (resultado.nivel if resultado else "")
        cor_hex = (
            resultado.cor
            if resultado is not None
            else Dicionario_de_Configuracao["cores_urgencia"].get(nivel, "#787878")
        )
        pontos_mapa.append(
            {
                "lat": lat_f,
                "lon": lon_f,
                "protocolo": protocolo or "—",
                "nivel": nivel or "—",
                "cor": _hex_para_rgb(cor_hex),
            }
        )

    if not pontos_mapa:
        st.info(
            "Nenhuma denúncia com coordenadas válidas para exibir no mapa "
            "com os filtros selecionados."
        )
    else:
        # Centro da visualização: média dos pontos (fallback para a cidade padrão).
        lat_centro = sum(p["lat"] for p in pontos_mapa) / len(pontos_mapa)
        lon_centro = sum(p["lon"] for p in pontos_mapa) / len(pontos_mapa)

        try:
            import pydeck as pdk

            camada = pdk.Layer(
                "ScatterplotLayer",
                data=pontos_mapa,
                get_position="[lon, lat]",
                get_fill_color="cor",
                get_radius=120,
                radius_min_pixels=6,
                radius_max_pixels=30,
                pickable=True,
                opacity=0.85,
            )
            vista = pdk.ViewState(
                latitude=lat_centro,
                longitude=lon_centro,
                zoom=11,
                pitch=0,
            )
            st.pydeck_chart(
                pdk.Deck(
                    layers=[camada],
                    initial_view_state=vista,
                    tooltip={"text": "{protocolo}\n{nivel}"},
                )
            )
        except Exception:
            # Falha de mapa/tiles ou do pydeck não deve quebrar a página
            # (Req. 10.2): cai para o `st.map` nativo, sem cor por ponto.
            st.map(
                [{"lat": p["lat"], "lon": p["lon"]} for p in pontos_mapa],
                latitude="lat",
                longitude="lon",
            )

        # Legenda simples de nível → cor, consistente com `cores_urgencia`.
        itens_legenda = " &nbsp; ".join(
            f"<span style='display:inline-block;width:12px;height:12px;"
            f"background:{cor};border-radius:2px;margin-right:4px;"
            f"vertical-align:middle;'></span>{nivel}"
            for nivel, cor in Dicionario_de_Configuracao["cores_urgencia"].items()
        )
        st.markdown(itens_legenda, unsafe_allow_html=True)

    st.subheader(f"Fila priorizada ({len(denuncias_visiveis)})")
    if not denuncias_visiveis:
        st.info("Nenhuma denúncia corresponde aos filtros selecionados.")
        return

    # Renderiza os cartões na ordem de prioridade (Req. 3.4).
    for d in denuncias_visiveis:
        protocolo = d.get("protocolo")
        resultado = resultados.get(protocolo)
        if resultado is None:
            # Salvaguarda defensiva: recalcula caso o protocolo não esteja no
            # mapa (ex.: denúncia sem protocolo). Mantém a renderização robusta.
            resultado = calcular_prioridade(d, agora)
        cartao_denuncia(d, resultado)

    # Seleção de uma denúncia para ver os detalhes com a explicação do Score
    # (Req. 3.5). Usa o Protocolo como chave de seleção, estável e legível.
    st.subheader("Detalhes da denúncia")
    protocolos_visiveis = [
        d.get("protocolo") for d in denuncias_visiveis if d.get("protocolo")
    ]
    protocolo_sel = st.selectbox(
        "Selecione o protocolo para ver os detalhes",
        protocolos_visiveis,
        key="fila_protocolo_detalhe",
    )

    denuncia_sel = next(
        (d for d in denuncias_visiveis if d.get("protocolo") == protocolo_sel),
        None,
    )
    if denuncia_sel is not None:
        resultado_sel = resultados.get(protocolo_sel) or calcular_prioridade(
            denuncia_sel, agora
        )

        st.markdown(f"**Protocolo:** `{protocolo_sel}`")
        col_selo, col_score = st.columns([1, 3])
        with col_selo:
            selo_urgencia(resultado_sel.nivel, resultado_sel.cor)
        with col_score:
            st.markdown(
                f"<span style='font-size:1.3rem;font-weight:700;"
                f"color:{resultado_sel.cor};'>Score {resultado_sel.score}</span>",
                unsafe_allow_html=True,
            )
        st.markdown(f"**Tipo de situação:** {denuncia_sel.get('tipo_situacao') or '—'}")
        st.markdown(f"**Espécie:** {denuncia_sel.get('especie') or '—'}")
        st.markdown(f"**Quantidade:** {denuncia_sel.get('quantidade') or '—'}")
        st.markdown(f"**Bairro:** {denuncia_sel.get('bairro') or '—'}")
        st.markdown(f"**Endereço:** {denuncia_sel.get('endereco') or '—'}")
        st.markdown(f"**Status:** {denuncia_sel.get('status') or '—'}")
        st.write(denuncia_sel.get("descricao") or "Sem descrição.")

        painel_explicacao(resultado_sel)

        # (10.5) Ações de atendimento (Req. 5.5, 5.6, 5.7, 5.8, 5.10, 8.3).
        # Oferece, conforme o status atual da denúncia selecionada:
        #   - ABERTA: formulário para assumir (nome do voluntário obrigatório +
        #     associação de resgate — nome/CNPJ da ONG), transicionando para
        #     EM ATENDIMENTO (Req. 5.5, 5.6).
        #   - EM ATENDIMENTO: controle para mudar o status para um dos estados
        #     finais (RESGATADO / NÃO LOCALIZADO / ENCERRADA) com observação
        #     (Req. 5.2).
        #   - Estados finais: apenas informa que não há mais transições (Req. 5.3).
        # As transições permitidas são derivadas de `TRANSICOES[status]`; a
        # chamada a `transicionar_status` já valida a máquina de estados e a
        # concorrência (Req. 5.4, 5.7), gravando status + histórico de forma
        # atômica (Req. 5.8). Em sucesso, invalida o cache de leitura (defensivo)
        # e refaz a página com `st.rerun()` para refletir o novo estado.
        def _invalidar_e_recarregar() -> None:
            """Invalida o cache de leitura (se houver) e refaz a página.

            A leitura hoje é direta (`listar_denuncias`), mas, caso passe a usar
            `st.cache_data`, limpamos o cache antes do rerun para evitar exibir
            dados desatualizados após a mutação. A limpeza é defensiva: qualquer
            falha não deve impedir o rerun.
            """
            try:
                st.cache_data.clear()
            except Exception:
                pass
            st.rerun()

        status_atual = denuncia_sel.get("status") or ""
        transicoes_possiveis = sorted(TRANSICOES.get(status_atual, set()))

        st.subheader("Ações de atendimento")

        if status_atual == "ABERTA":
            # Tomada da denúncia: nome do voluntário obrigatório e associação de
            # resgate opcional (nome da ONG ou CNPJ) — Req. 5.5.
            with st.form(key=f"form_assumir_{protocolo_sel}"):
                st.markdown(
                    "Assuma esta denúncia para iniciar o atendimento. "
                    "O nome do voluntário é obrigatório."
                )
                nome_voluntario = st.text_input(
                    "Nome do voluntário *",
                    key=f"assumir_nome_{protocolo_sel}",
                )
                associacao_resgate = st.text_input(
                    "Associação de resgate (nome da ONG ou CNPJ)",
                    key=f"assumir_associacao_{protocolo_sel}",
                )
                observacao_assumir = st.text_area(
                    "Observação (opcional)",
                    key=f"assumir_observacao_{protocolo_sel}",
                )
                assumir = st.form_submit_button("Assumir denúncia")

            if assumir:
                nome = (nome_voluntario or "").strip()
                if not nome:
                    st.error("Informe o nome do voluntário para assumir a denúncia.")
                else:
                    associacao = (associacao_resgate or "").strip() or None
                    observacao = (observacao_assumir or "").strip() or (
                        f"Denúncia assumida por {nome}."
                    )
                    resultado_acao = transicionar_status(
                        con,
                        protocolo_sel,
                        "EM ATENDIMENTO",
                        autor=nome,
                        observacao=observacao,
                        associacao=associacao,
                    )
                    if resultado_acao.ok:
                        st.success(resultado_acao.mensagem)
                        _invalidar_e_recarregar()
                    else:
                        st.error(resultado_acao.mensagem)

        elif status_atual == "EM ATENDIMENTO":
            # Mostra o responsável atual, quando houver (Req. 5.6).
            responsavel = denuncia_sel.get("voluntario_responsavel")
            associacao_atual = denuncia_sel.get("associacao_resgate")
            if responsavel:
                st.markdown(f"**Responsável:** {responsavel}")
            if associacao_atual:
                st.markdown(f"**Associação de resgate:** {associacao_atual}")

            # Mudança para um dos estados finais com observação (Req. 5.2, 5.8).
            with st.form(key=f"form_status_{protocolo_sel}"):
                st.markdown(
                    "Atualize o status desta denúncia em atendimento. "
                    "Informe o nome de quem realiza a mudança."
                )
                novo_status = st.selectbox(
                    "Novo status",
                    transicoes_possiveis,
                    key=f"mudar_status_{protocolo_sel}",
                )
                autor_mudanca = st.text_input(
                    "Nome de quem muda o status *",
                    value=responsavel or "",
                    key=f"mudar_autor_{protocolo_sel}",
                )
                observacao_mudanca = st.text_area(
                    "Observação",
                    key=f"mudar_observacao_{protocolo_sel}",
                )
                mudar = st.form_submit_button("Atualizar status")

            if mudar:
                autor = (autor_mudanca or "").strip()
                if not autor:
                    st.error("Informe o nome de quem realiza a mudança de status.")
                else:
                    observacao = (observacao_mudanca or "").strip() or (
                        f"Status alterado para {novo_status} por {autor}."
                    )
                    resultado_acao = transicionar_status(
                        con,
                        protocolo_sel,
                        novo_status,
                        autor=autor,
                        observacao=observacao,
                    )
                    if resultado_acao.ok:
                        st.success(resultado_acao.mensagem)
                        _invalidar_e_recarregar()
                    else:
                        st.error(resultado_acao.mensagem)

        else:
            # Estados finais (RESGATADO / NÃO LOCALIZADO / ENCERRADA): sem
            # transições de saída (Req. 5.3). Apenas informa a situação.
            st.info(
                f"Esta denúncia está em um estado final ('{status_atual}'). "
                "Não há ações de atendimento disponíveis."
            )

        # Histórico completo da denúncia em ordem cronológica crescente, do item
        # mais antigo para o mais recente (Req. 5.10). `listar_historico` já
        # devolve os itens ordenados por data/hora e id.
        st.subheader("Histórico")
        historico = listar_historico(con, protocolo_sel)
        if not historico:
            st.caption("Nenhuma movimentação registrada para esta denúncia.")
        else:
            for item in historico:
                data_hora = item.get("data_hora") or "—"
                autor_hist = item.get("autor") or "—"
                status_anterior = item.get("status_anterior") or "—"
                status_novo = item.get("status_novo") or "—"
                observacao_hist = item.get("observacao") or ""
                st.markdown(
                    f"- **{data_hora}** — {autor_hist}: "
                    f"{status_anterior} → {status_novo}"
                )
                if observacao_hist:
                    st.caption(observacao_hist)


def _formatar_horas(horas: float | None) -> str:
    """Formata o tempo médio até o primeiro atendimento em pt-BR (Req. 6.4).

    Converte um número de horas em um texto curto no padrão brasileiro (vírgula
    como separador decimal e uma casa, ex.: ``"12,3 h"``). Quando não há dados
    (``None``, caso em que nenhuma denúncia chegou a ser atendida), devolve o
    marcador neutro ``"—"``.

    Args:
        horas: Média em horas até o primeiro atendimento, ou ``None``.

    Returns:
        Texto em pt-BR com a média formatada, ou ``"—"`` quando não há dados.
    """
    if horas is None:
        return "—"
    return f"{horas:.1f}".replace(".", ",") + " h"


def _distribuicao_para_dataframe(distribuicao: dict, rotulo_indice: str) -> "object":
    """Converte uma distribuição em um DataFrame para `st.bar_chart` (Req. 6.5).

    Monta um `pandas.DataFrame` com o rótulo de cada categoria no índice e uma
    única coluna ``contagem``, formato que `st.bar_chart` renderiza como barras
    limpas (uma barra por categoria). Distribuições vazias produzem um DataFrame
    vazio com as mesmas colunas, de modo que a página possa decidir exibir uma
    mensagem de "sem dados" em vez do gráfico.

    Args:
        distribuicao: Mapa ``{rótulo: contagem}`` de uma das distribuições
            devolvidas por `agregacoes_coordenacao`.
        rotulo_indice: Nome do índice do DataFrame (ex.: ``"Nível"``), usado
            como rótulo do eixo das categorias.

    Returns:
        Um `pandas.DataFrame` com índice nomeado e a coluna ``contagem``.
    """
    import pandas as pd

    itens = list(distribuicao.items())
    indice = pd.Index([rotulo for rotulo, _ in itens], name=rotulo_indice)
    contagens = [contagem for _, contagem in itens]
    return pd.DataFrame({"contagem": contagens}, index=indice)


def pagina_coordenacao(con: sqlite3.Connection) -> None:
    """Renderiza o Painel da Coordenação com indicadores e distribuições (Req. 6, 8.4).

    Monta a página do perfil Coordenação. Carrega todas as denúncias do banco e,
    como o Nível de Urgência não é coluna persistida, calcula para cada uma o
    resultado de `calcular_prioridade` (com ``instante=datetime.now()``) e anexa
    ``d['nivel']`` ao dicionário — passo necessário para que a distribuição por
    nível fique correta. Em seguida chama `agregacoes_coordenacao`, que resume o
    conjunto em contagens, tempo médio até o primeiro atendimento e distribuições
    por nível, tipo e bairro (Req. 6.1–6.5).

    Os indicadores são exibidos com `st.metric` em colunas e as distribuições com
    gráficos nativos (`st.bar_chart`), um para cada partição.

    Args:
        con: Conexão SQLite aberta por `conectar`.
    """
    import streamlit as st

    st.header("📊 Painel da coordenação")
    st.caption(
        "Visão geral das denúncias: indicadores de atendimento e distribuições "
        "por nível de urgência, tipo de situação e bairro."
    )

    agora = datetime.now()

    # Carrega todas as denúncias e anexa o Nível de Urgência a cada uma. O nível
    # é derivado do Score (não é coluna persistida), então precisa ser calculado
    # aqui para que `distribuicao_por_nivel` — que agrupa por ``d['nivel']`` —
    # produza a distribuição correta (Req. 6.5).
    denuncias = listar_denuncias(con)
    for d in denuncias:
        d["nivel"] = calcular_prioridade(d, agora).nivel

    resumo = agregacoes_coordenacao(denuncias, agora)

    # Indicadores agregados (Req. 6.1–6.4) em duas linhas de colunas.
    st.subheader("Indicadores")
    linha1 = st.columns(3)
    linha1[0].metric("Abertas", resumo["abertas"])
    linha1[1].metric("Em atendimento", resumo["em_atendimento"])
    linha1[2].metric("Resgatadas no dia", resumo["resgatadas_no_dia"])

    linha2 = st.columns(2)
    linha2[0].metric("Resgatadas no total", resumo["resgatadas_total"])
    linha2[1].metric(
        "Tempo médio até 1º atendimento",
        _formatar_horas(resumo["tempo_medio_primeiro_atendimento_horas"]),
    )

    # Distribuições (Req. 6.5): cada uma é uma partição cujas contagens somam o
    # total do conjunto. São exibidas como gráficos de barras nativos; quando
    # vazias (nenhuma denúncia), mostra-se uma mensagem neutra em pt-BR.
    st.subheader("Distribuições")

    distribuicoes = (
        ("Por nível de urgência", resumo["distribuicao_nivel"], "Nível"),
        ("Por tipo de situação", resumo["distribuicao_tipo"], "Tipo"),
        ("Por bairro", resumo["distribuicao_bairro"], "Bairro"),
    )
    for titulo, distribuicao, rotulo_indice in distribuicoes:
        st.markdown(f"**{titulo}**")
        if not distribuicao:
            st.caption("Sem dados para exibir.")
            continue
        dados = _distribuicao_para_dataframe(distribuicao, rotulo_indice)
        st.bar_chart(dados)


# ── run_self_tests ───────────────────────────────────────────────────────────────
# Testes com `assert` sobre o Motor de Priorização, executáveis sem subir o
# Streamlit (Requisito 11.2 / 11.3). A implementar na tarefa 4.12.

def run_self_tests() -> None:
    """Exercita o Motor de Priorização com asserts determinísticos (Req. 11.2, 11.3, 11.4).

    Executa `calcular_prioridade` sobre denúncias construídas a partir dos
    próprios valores do `Dicionario_de_Configuracao`, de modo que as faixas
    asseridas acompanhem eventuais ajustes da configuração em vez de depender de
    números mágicos. Cobre, de forma determinística (instantes e `criado_em`
    fixos):

    - um caso por Nível de Urgência (CRÍTICO, ALTO, MÉDIO, BAIXO), verificando
      nível e cor (`cores_urgencia[nivel]`);
    - saturação do componente de quantidade na `contribuicao_maxima`;
    - saturação do componente de tempo de espera na `contribuicao_maxima`;
    - tipo `abandonado` zerando o tempo e tornando o Score independente do
      instante de cálculo;
    - normalização de palavras-chave (acentos/caixa/espaços) produzindo o mesmo
      Score que a forma canônica e aparecendo na explicação;
    - consistência da explicação (soma dos pontos dos fatores == Score bruto num
      caso sem recorte);
    - determinismo (duas chamadas idênticas produzem resultados idênticos).

    Conclui sem `AssertionError` quando o motor está correto (Req. 11.3).
    Invocável via `python app.py --self-test`, sem subir o Streamlit.
    """
    cfg = Dicionario_de_Configuracao
    pesos = cfg["pesos_situacao"]
    palavras = cfg["palavras_chave"]
    qtd_cfg = cfg["quantidade"]
    tempo_cfg = cfg["tempo_espera"]
    cores = cfg["cores_urgencia"]

    # Instante de cálculo fixo e `criado_em` derivados dele: tudo determinístico.
    instante = datetime(2024, 6, 1, 12, 0, 0)

    def _criado_horas_antes(horas: float) -> datetime:
        """Retorna um `criado_em` fixo, `horas` antes do instante de cálculo."""
        return instante - timedelta(hours=horas)

    def _pontos_fator(resultado: ResultadoPrioridade, nome_fator: str) -> int:
        """Pontos atribuídos a um fator nomeado na explicação do resultado."""
        for fator in resultado.explicacao:
            if fator.fator == nome_fator:
                return fator.pontos
        raise AssertionError(f"Fator '{nome_fator}' ausente na explicação.")

    # Componentes de quantidade esperados para q=1 (mínimo do domínio) e para o
    # teto de contribuição, computados a partir da configuração.
    qtd_min = min(int(qtd_cfg["pontos_por_animal"]) * 1, int(qtd_cfg["contribuicao_maxima"]))
    qtd_max = int(qtd_cfg["contribuicao_maxima"])
    tempo_max = int(tempo_cfg["contribuicao_maxima"])

    # ── Caso CRÍTICO (80–100) ───────────────────────────────────────────────
    # situação ferido/atropelado + "sangrando" + "atropelado" + q=1 + tempo no teto.
    bruto_critico = (
        pesos["ferido/atropelado"]
        + palavras["sangrando"]
        + palavras["atropelado"]
        + qtd_min
        + tempo_max
    )
    d_critico = {
        "tipo_situacao": "ferido/atropelado",
        "descricao": "Cachorro sangrando após ser atropelado na avenida.",
        "quantidade": 1,
        "criado_em": _criado_horas_antes(tempo_max + 10),  # espera > teto ⇒ satura
    }
    r_critico = calcular_prioridade(d_critico, instante)
    assert r_critico.score == bruto_critico, (
        f"CRÍTICO: score {r_critico.score} != bruto esperado {bruto_critico}"
    )
    assert 80 <= r_critico.score <= 100, (
        f"CRÍTICO: score {r_critico.score} fora da faixa 80–100"
    )
    assert r_critico.nivel == "CRÍTICO", f"Esperado nível CRÍTICO, veio {r_critico.nivel}"
    assert r_critico.cor == cores["CRÍTICO"], "Cor do nível CRÍTICO inconsistente"

    # ── Caso ALTO (60–79) ─────────────────────────────────────────────────────
    # situação maus-tratos + "amarrado" + "agressao" + q=1 + tempo no teto.
    bruto_alto = (
        pesos["maus-tratos"]
        + palavras["amarrado"]
        + palavras["agressao"]
        + qtd_min
        + tempo_max
    )
    d_alto = {
        "tipo_situacao": "maus-tratos",
        "descricao": "Cão amarrado curto sofrendo agressao do dono.",
        "quantidade": 1,
        "criado_em": _criado_horas_antes(tempo_max + 5),
    }
    r_alto = calcular_prioridade(d_alto, instante)
    assert r_alto.score == bruto_alto, (
        f"ALTO: score {r_alto.score} != bruto esperado {bruto_alto}"
    )
    assert 60 <= r_alto.score <= 79, f"ALTO: score {r_alto.score} fora da faixa 60–79"
    assert r_alto.nivel == "ALTO", f"Esperado nível ALTO, veio {r_alto.nivel}"
    assert r_alto.cor == cores["ALTO"], "Cor do nível ALTO inconsistente"

    # ── Caso MÉDIO (40–59) ─────────────────────────────────────────────────────
    # situação animal doente + "frio" + q=1 + tempo no teto.
    bruto_medio = pesos["animal doente"] + palavras["frio"] + qtd_min + tempo_max
    d_medio = {
        "tipo_situacao": "animal doente",
        "descricao": "Animal doente tremendo de frio, precisa de ajuda.",
        "quantidade": 1,
        "criado_em": _criado_horas_antes(tempo_max + 2),
    }
    r_medio = calcular_prioridade(d_medio, instante)
    assert r_medio.score == bruto_medio, (
        f"MÉDIO: score {r_medio.score} != bruto esperado {bruto_medio}"
    )
    assert 40 <= r_medio.score <= 59, f"MÉDIO: score {r_medio.score} fora da faixa 40–59"
    assert r_medio.nivel == "MÉDIO", f"Esperado nível MÉDIO, veio {r_medio.nivel}"
    assert r_medio.cor == cores["MÉDIO"], "Cor do nível MÉDIO inconsistente"

    # ── Caso BAIXO (0–39) ──────────────────────────────────────────────────────
    # situação animal perdido, sem palavras-chave, q=1, espera pequena.
    horas_baixo = 5
    tempo_baixo = min(int(tempo_cfg["pontos_por_hora"]) * horas_baixo, tempo_max)
    bruto_baixo = pesos["animal perdido"] + 0 + qtd_min + tempo_baixo
    d_baixo = {
        "tipo_situacao": "animal perdido",
        "descricao": "Cachorro perdido vagando assustado perto da praca.",
        "quantidade": 1,
        "criado_em": _criado_horas_antes(horas_baixo),
    }
    r_baixo = calcular_prioridade(d_baixo, instante)
    assert r_baixo.score == bruto_baixo, (
        f"BAIXO: score {r_baixo.score} != bruto esperado {bruto_baixo}"
    )
    assert 0 <= r_baixo.score <= 39, f"BAIXO: score {r_baixo.score} fora da faixa 0–39"
    assert r_baixo.nivel == "BAIXO", f"Esperado nível BAIXO, veio {r_baixo.nivel}"
    assert r_baixo.cor == cores["BAIXO"], "Cor do nível BAIXO inconsistente"
    # Sanidade: a descrição BAIXO não contém palavras-chave configuradas.
    assert _pontos_fator(r_baixo, "palavras-chave") == 0, (
        "Caso BAIXO não deveria ter pontos de palavras-chave"
    )

    # ── Saturação de quantidade ─────────────────────────────────────────────────
    # Quantidade muito acima do limiar de saturação ⇒ componente == contribuicao_maxima.
    limiar_qtd = qtd_max // max(int(qtd_cfg["pontos_por_animal"]), 1)
    d_qtd_satura = {
        "tipo_situacao": "animal perdido",
        "descricao": "Vários animais perdidos no mesmo local.",
        "quantidade": limiar_qtd + 50,  # bem acima do ponto de saturação
        "criado_em": _criado_horas_antes(1),
    }
    r_qtd_satura = calcular_prioridade(d_qtd_satura, instante)
    assert _pontos_fator(r_qtd_satura, "quantidade") == qtd_max, (
        "Componente de quantidade deveria saturar em contribuicao_maxima"
    )

    # ── Saturação de tempo de espera ────────────────────────────────────────────
    # Denúncia não-abandonado muito antiga ⇒ componente de tempo == contribuicao_maxima.
    d_tempo_satura = {
        "tipo_situacao": "animal perdido",
        "descricao": "Animal perdido ha muito tempo sem atendimento.",
        "quantidade": 1,
        "criado_em": _criado_horas_antes(tempo_max * 10 + 100),  # espera enorme
    }
    r_tempo_satura = calcular_prioridade(d_tempo_satura, instante)
    assert _pontos_fator(r_tempo_satura, "tempo de espera") == tempo_max, (
        "Componente de tempo deveria saturar em contribuicao_maxima"
    )

    # ── Abandono zera o tempo e torna o Score independente do instante ──────────
    d_abandono = {
        "tipo_situacao": "abandonado",
        "descricao": "Cão abandonado no terreno baldio.",
        "quantidade": 1,
        "criado_em": _criado_horas_antes(tempo_max * 10 + 100),  # bem antigo
    }
    instante_2 = instante + timedelta(days=15)  # instante bem diferente
    r_abandono_1 = calcular_prioridade(d_abandono, instante)
    r_abandono_2 = calcular_prioridade(d_abandono, instante_2)
    assert _pontos_fator(r_abandono_1, "tempo de espera") == 0, (
        "Tipo 'abandonado' deveria zerar o componente de tempo"
    )
    assert r_abandono_1.score == r_abandono_2.score, (
        "Score de 'abandonado' deveria independer do instante de cálculo"
    )
    assert r_abandono_1.explicacao == r_abandono_2.explicacao, (
        "Explicação de 'abandonado' deveria independer do instante de cálculo"
    )

    # ── Normalização de palavras-chave ─────────────────────────────────────────
    # Forma canônica x variante com acento/caixa/espaços: mesmo Score; a
    # palavra-chave aparece na explicação em ambas.
    base_kw = {
        "tipo_situacao": "ferido/atropelado",
        "quantidade": 1,
        "criado_em": _criado_horas_antes(3),
    }
    d_canonico = {**base_kw, "descricao": "animal sangrando, nao se mexe"}
    d_variante = {**base_kw, "descricao": "Animal SANGRANDO, não  se   mexe"}
    r_canonico = calcular_prioridade(d_canonico, instante)
    r_variante = calcular_prioridade(d_variante, instante)
    assert r_canonico.score == r_variante.score, (
        "Variação de acento/caixa/espaço deveria produzir o mesmo Score"
    )
    palavras_canonico = _pontos_fator_palavras(r_canonico)
    palavras_variante = _pontos_fator_palavras(r_variante)
    assert "sangrando" in palavras_canonico and "sangrando" in palavras_variante, (
        "Palavra-chave 'sangrando' deveria aparecer na explicação (canônico e variante)"
    )
    assert "nao se mexe" in palavras_canonico and "nao se mexe" in palavras_variante, (
        "Palavra-chave 'nao se mexe' deveria aparecer na explicação (canônico e variante)"
    )

    # ── Consistência da explicação ──────────────────────────────────────────────
    # Caso sem recorte (bruto <= 100): soma dos pontos dos fatores == Score.
    soma_fatores_medio = sum(fator.pontos for fator in r_medio.explicacao)
    assert soma_fatores_medio == r_medio.score, (
        "Soma dos pontos dos fatores deveria igualar o Score (caso sem recorte)"
    )

    # ── Determinismo ────────────────────────────────────────────────────────────
    # Duas chamadas com entradas idênticas produzem resultados idênticos.
    r_det_1 = calcular_prioridade(d_critico, instante)
    r_det_2 = calcular_prioridade(d_critico, instante)
    assert r_det_1.score == r_det_2.score, "Score não determinístico entre chamadas"
    assert r_det_1.nivel == r_det_2.nivel, "Nível não determinístico entre chamadas"
    assert r_det_1.cor == r_det_2.cor, "Cor não determinística entre chamadas"
    assert r_det_1.explicacao == r_det_2.explicacao, (
        "Explicação não determinística entre chamadas"
    )

    print("run_self_tests: todos os asserts do motor passaram.")


def _pontos_fator_palavras(resultado: ResultadoPrioridade) -> tuple[str, ...]:
    """Retorna as palavras-chave listadas no fator 'palavras-chave' da explicação."""
    for fator in resultado.explicacao:
        if fator.fator == "palavras-chave":
            return fator.palavras_chave
    raise AssertionError("Fator 'palavras-chave' ausente na explicação.")


# ── main ─────────────────────────────────────────────────────────────────────────
# Inicializa o banco (seed quando vazio), renderiza o seletor de perfil na barra
# lateral e roteia para a página adequada. A implementar na tarefa 12.1.

def main() -> None:
    """Ponto de entrada da interface Streamlit: inicializa o banco e roteia por perfil.

    Fluxo a cada execução (rerun) do script Streamlit:

    1. Configura a página (título, ícone e layout amplo).
    2. Abre uma conexão nova com `conectar`, garante o schema com `criar_schema`
       e popula o banco com dados de demonstração apenas quando ele está vazio,
       via `semear_dados_demo` (Req. 7.4). A conexão é por execução — robusto e
       suficiente para esta aplicação de hackathon, pois `sqlite3` roda na mesma
       thread de script do Streamlit.
    3. Renderiza, na barra lateral, o seletor de perfil (Cidadão Denunciante,
       Voluntário, Coordenação — Req. 8.1) e o controle de reset dos dados de
       demonstração (Req. 7.5). Não há autenticação em nenhuma etapa (Req. 8.5).
    4. Roteia para a página correspondente ao perfil selecionado (Req. 8.2–8.4).

    Toda a interface é apresentada em português do Brasil (Req. 10.1) e opera
    localmente (Req. 10.2).
    """
    import streamlit as st

    st.set_page_config(
        page_title="ResgataJá",
        page_icon="🐾",
        layout="wide",
    )

    # Conexão por execução: simples e correta para o modelo de thread do
    # Streamlit (sqlite3 com check_same_thread=True roda na thread de script).
    con = conectar()
    criar_schema(con)
    semear_dados_demo(con)  # idempotente: só popula quando o banco está vazio.

    # Barra lateral: identidade da aplicação, seletor de perfil e reset. O
    # seletor aparece primeiro; a barra de filtros da página de Voluntário
    # (`barra_filtros`) também renderiza na sidebar, logo abaixo (Req. 8.1).
    st.sidebar.title("🐾 ResgataJá")
    st.sidebar.caption("Fila inteligente de denúncias de resgate de animais.")

    perfil = st.sidebar.radio(
        "Perfil de acesso",
        ("Cidadão Denunciante", "Voluntário", "Coordenação"),
        help="Troque de perfil para acessar as telas do sistema (sem login).",
    )

    st.sidebar.divider()
    if st.sidebar.button(
        "Resetar dados de demonstração",
        help="Remove as denúncias atuais e recria os dados de exemplo.",
    ):
        total = resetar_dados_demo(con)
        st.sidebar.success(
            f"Dados de demonstração recriados: {total} denúncias."
        )
        st.rerun()

    # Roteamento por perfil, sem autenticação (Req. 8.2–8.5).
    if perfil == "Cidadão Denunciante":
        pagina_registro(con)
    elif perfil == "Voluntário":
        pagina_fila_e_mapa(con)
    else:  # "Coordenação"
        pagina_coordenacao(con)


if __name__ == "__main__":
    if "--self-test" in sys.argv[1:]:
        run_self_tests()
    else:
        main()
