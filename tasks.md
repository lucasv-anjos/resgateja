# Implementation Plan: ResgataJá

## Overview

Este plano converte o design do ResgataJá em uma sequência de tarefas de codificação incrementais. **Todo o código da aplicação reside em um único arquivo `app.py`** (Requisito 9.1–9.3); os únicos outros arquivos permitidos são `requirements.txt` e o banco SQLite gerado em tempo de execução. Os testes baseados em propriedades usam [Hypothesis](https://hypothesis.readthedocs.io/) e, por preferência de empacotamento, os testes com `assert` do motor ficam na função `run_self_tests` dentro de `app.py` (Requisito 11.2). Os testes de propriedade e de integração são declarados como sub-tarefas opcionais (`*`); quando implementados, residem em um único arquivo de testes auxiliar — o único `.py` adicional permitido.

A ordem das tarefas segue estritamente a ordem de implementação exigida: (1) Banco + dados de demonstração, (2) Motor de priorização + testes, (3) Formulário de denúncia, (4) Fila priorizada com filtros, (5) Mapa, (6) Fluxo de atendimento e histórico, (7) Painel da coordenação, (8) Polimento visual para a demo. O scaffolding do arquivo único precede tudo.

## Tasks

- [x] 1. Preparar scaffolding do arquivo único e dependências
  - Criar `requirements.txt` declarando `streamlit` e `hypothesis`.
  - Criar `app.py` com o esqueleto organizado nas seções comentadas exigidas, nesta ordem: `# ── Configuração`, `# ── Banco`, `# ── Dados de Exemplo`, `# ── Motor de Priorização`, `# ── Componentes de Interface`, `# ── Páginas`, `# ── run_self_tests` e `# ── main` (Requisito 9.5).
  - Preencher a seção Configuração com `CIDADE_PADRAO`, `Dicionario_de_Configuracao` (pesos de situação em ordem decrescente, palavras-chave com pontos, limites de quantidade e de tempo de espera, limiares e cores de urgência), `TIPOS_SITUACAO`, `ESPECIES`, `STATUS` e `TRANSICOES`, com type hints (Requisitos 2.12, 1.2, 1.3, 5.1–5.4, 11.1).
  - Adicionar um `main()` mínimo e o guard `if __name__ == "__main__"`, incluindo suporte a `--self-test` para invocar `run_self_tests` sem subir o Streamlit.
  - _Requisitos: 9.1, 9.2, 9.3, 9.4, 9.5, 2.12, 11.1_

- [x] 2. Implementar camada de banco e dados de demonstração
  - [x] 2.1 Implementar conexão e schema SQLite
    - Em `app.py`, seção Banco: `conectar()` (abre SQLite com `row_factory` e `foreign_keys` habilitado) e `criar_schema(con)` criando as tabelas `denuncias` e `historico` conforme os Data Models (colunas, tipos, PK e FK), com type hints e docstrings curtas.
    - _Requisitos: 9.3, 11.1, 5.8_

  - [x] 2.2 Implementar inserção de denúncia e geração de protocolo
    - Em `app.py`, seção Banco: `inserir_denuncia(con, dados)` executando dentro de transação (`with con:`), gerando um Protocolo único legível (ex.: `RJ-AAAAMMDD-NNNN`), persistindo com `status = ABERTA` e retornando o Protocolo; em exceção de `sqlite3`, garantir rollback e não retornar Protocolo definitivo.
    - _Requisitos: 1.11, 1.12_

  - [x] 2.3 Implementar leitura de denúncias com filtros e histórico
    - Em `app.py`, seção Banco: `listar_denuncias(con, filtros)` aplicando filtros opcionais (nível, tipo, espécie, bairro, status), `obter_denuncia(con, protocolo)` e `listar_historico(con, protocolo)` retornando itens em ordem cronológica crescente (por `data_hora` e `id`).
    - _Requisitos: 3.2, 3.3, 5.10_

  - [x] 2.4 Implementar geração e seeding dos dados de demonstração
    - Em `app.py`, seção Dados de Exemplo: função que gera ~30 denúncias fictícias distribuídas por bairros de uma cidade brasileira com coordenadas plausíveis, tipos de situação variados, horários de abertura diferentes e algumas com status `RESGATADO`; função de seeding que popula apenas quando o banco está vazio; função de reset que remove e recria os dados.
    - _Requisitos: 7.1, 7.2, 7.3, 7.4, 7.5_

  - [ ]* 2.5 Escrever testes de integração de persistência, seeding e reset
    - Contra banco temporário/`:memory:`: registro válido persiste com status ABERTA e protocolos únicos em lote (Req. 1.11); falha de persistência via mock não gera protocolo (Req. 1.12); seeding gera ~30 denúncias com bairros/coordenadas plausíveis e alguns RESGATADO, e reset remove/recria (Req. 7.1–7.5).
    - _Requisitos: 1.11, 1.12, 7.1, 7.2, 7.3, 7.4, 7.5_

- [x] 3. Checkpoint — Garantir que os testes passem
  - Garanta que todos os testes passem; pergunte ao usuário em caso de dúvidas.

- [x] 4. Implementar o motor de priorização explicável
  - [x] 4.1 Implementar normalização de texto e estruturas de resultado
    - Em `app.py`, seção Motor de Priorização: `normalizar(texto)` (minúsculas, remoção de acentos via NFKD, colapso de espaços, tratando `None` como string vazia) e as estruturas imutáveis `ResultadoPrioridade` (NamedTuple ou dataclass frozen) e `FatorExplicado`.
    - _Requisitos: 2.6, 2.11, 11.1_

  - [x] 4.2 Implementar `calcular_prioridade` como função pura
    - Em `app.py`, seção Motor de Priorização: `calcular_prioridade(denuncia, instante)` somando os quatro componentes (situação, palavras-chave, quantidade, tempo de espera) a partir do `Dicionario_de_Configuracao`, aplicando clamp 0–100, derivando Nível de Urgência e cor, e montando a explicação (cada fator com pontos e palavras-chave encontradas). Sem efeitos colaterais, sem ler o relógio internamente, sem mutar a entrada.
    - Garantir: componente de quantidade limitado pela `contribuicao_maxima`; componente de tempo limitado e crescente com a espera.
    - _Requisitos: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8, 2.9, 2.10, 2.11, 2.13, 11.4_

  - [ ]* 4.3 Escrever propriedade de composição e limitação do Score
    - **Property 1: Composição e limitação do Score** — `score == clamp(soma_componentes, 0, 100)` e `0 ≤ score ≤ 100` para toda entrada.
    - **Validates: Requisitos 2.1, 2.2, 2.3** (Hypothesis, mínimo 100 iterações)

  - [ ]* 4.4 Escrever propriedade de ordenação monotônica do componente de situação
    - **Property 2: Ordenação monotônica do componente de situação** — tipo A anterior a B na ordem decrescente de peso ⇒ Score(A) ≥ Score(B), demais fatores fixos.
    - **Validates: Requisitos 2.4** (Hypothesis, mínimo 100 iterações)

  - [ ]* 4.5 Escrever propriedade de invariância de normalização de palavras-chave
    - **Property 3: Invariância de normalização de palavras-chave** — variações de acento/caixa/espaço produzem o mesmo Score que a forma canônica, e a palavra-chave aparece na explicação.
    - **Validates: Requisitos 2.5, 2.6** (Hypothesis, mínimo 100 iterações)

  - [ ]* 4.6 Escrever propriedade do componente de quantidade (monotônico e limitado)
    - **Property 4: Componente de quantidade é monotônico e limitado** — q1 ≤ q2 ⇒ componente(q1) ≤ componente(q2), nunca excede `contribuicao_maxima`, satura acima do limiar.
    - **Validates: Requisitos 2.7** (Hypothesis, mínimo 100 iterações)

  - [ ]* 4.7 Escrever propriedade do componente de tempo de espera (monotônico e limitado)
    - **Property 5: Componente de tempo de espera é monotônico e limitado** — para tipo ≠ `abandonado`, t1 ≤ t2 ⇒ componente(t1) ≤ componente(t2), nunca excede `contribuicao_maxima`.
    - **Validates: Requisitos 2.8** (Hypothesis, mínimo 100 iterações)

  - [ ]* 4.9 Escrever propriedade de classificação total e exclusiva do Nível de Urgência
    - **Property 7: Classificação total e exclusiva do Nível de Urgência** — todo Score 0–100 mapeia para exatamente um nível conforme as faixas, com cor igual a `cores_urgencia[nivel]`.
    - **Validates: Requisitos 2.10** (Hypothesis, mínimo 100 iterações)

  - [ ]* 4.10 Escrever propriedade de consistência da explicação
    - **Property 8: Consistência da explicação** — soma dos pontos dos fatores da explicação == Score bruto; toda palavra-chave presente (normalizada) está listada e nenhuma ausente é listada.
    - **Validates: Requisitos 2.11** (Hypothesis, mínimo 100 iterações)

  - [ ]* 4.11 Escrever propriedade de determinismo e pureza do motor
    - **Property 9: Determinismo e pureza do motor** — duas chamadas sucessivas produzem Score, Nível e explicação idênticos e não mutam o dicionário de entrada.
    - **Validates: Requisitos 2.13, 11.4** (Hypothesis, mínimo 100 iterações)

  - [x] 4.12 Implementar `run_self_tests` com asserts do motor
    - Em `app.py`, seção run_self_tests: função que exercita `calcular_prioridade` com casos determinísticos (um caso por nível de urgência, saturação de quantidade e de tempo, normalização de palavras-chave), concluindo sem `AssertionError` quando o motor está correto. Invocável via `--self-test` sem subir o Streamlit.
    - _Requisitos: 11.2, 11.3, 11.4_

- [x] 5. Checkpoint — Garantir que os testes passem
  - Garanta que todos os testes passem; pergunte ao usuário em caso de dúvidas.

- [x] 6. Implementar o formulário de registro de denúncia
  - [x] 6.1 Implementar validação pura do formulário
    - Em `app.py`, seção Componentes de Interface (ou utilitários puros próximos ao motor): função pura de validação que aceita se e somente se tipo de situação, espécie e quantidade estão informados, endereço e bairro não vazios (após `strip`), latitude em [−90, 90], longitude em [−180, 180], telefone (quando informado) apenas com dígitos/espaços/`+ - ( )`, e nome (quando informado) ≤ 120 caracteres; ao rejeitar, retorna exatamente o conjunto de pendências.
    - _Requisitos: 1.6, 1.7, 1.9, 1.10_

  - [ ]* 6.2 Escrever propriedade de validação de campos obrigatórios e limites
    - **Property 11: Validação de campos obrigatórios e limites** — aceita sse e somente se todas as condições são satisfeitas; o conjunto de pendências reportadas é exatamente o conjunto de campos obrigatórios/invalidados.
    - **Validates: Requisitos 1.6, 1.7, 1.9, 1.10** (Hypothesis, mínimo 100 iterações)

  - [x] 6.3 Implementar a página de registro
    - Em `app.py`, seção Páginas: `pagina_registro(con)` renderizando o formulário sem autenticação, com seleção única de tipo de situação e espécie, quantidade (1–999), descrição (≤ 2000), endereço e bairro obrigatórios, latitude/longitude pré-preenchidas pela cidade e ajustáveis dentro dos limites, upload opcional de foto JPG/PNG ≤ 10 MB, nome (≤ 120) e telefone opcionais.
    - Ao enviar: validar; em erro, listar pendências preservando os valores em `st.session_state`; em sucesso, chamar `inserir_denuncia`, calcular Score/Nível via `calcular_prioridade` e exibir Protocolo e Nível de Urgência; em falha de persistência, exibir mensagem e preservar valores sem gerar Protocolo.
    - _Requisitos: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 1.9, 1.10, 1.11, 1.12, 1.13, 8.2_

  - [ ]* 6.4 Escrever testes por exemplo das listas de opções e upload de foto
    - Verificar `TIPOS_SITUACAO` e `ESPECIES` iguais aos conjuntos exigidos (Req. 1.2, 1.3) e validação de foto (JPG/PNG aceitos; tipo/tamanho rejeitados) (Req. 1.8).
    - _Requisitos: 1.2, 1.3, 1.8_

- [x] 7. Implementar a fila priorizada com filtros
  - [x] 7.1 Implementar lógica pura de fila e filtros
    - Em `app.py`: função pura que, dado um conjunto de denúncias (com Score calculado) e filtros ativos (nível, tipo, espécie, bairro, status), retorna exatamente as denúncias com status ABERTA ou EM ATENDIMENTO que satisfazem todos os filtros, ordenadas por Score decrescente.
    - _Requisitos: 3.1, 3.2, 3.3_

  - [ ]* 7.2 Escrever propriedade de fila priorizada e filtros
    - **Property 10: Fila priorizada e filtros** — resultado contém exatamente os itens ABERTA/EM ATENDIMENTO que satisfazem todos os filtros, ordenados por Score decrescente.
    - **Validates: Requisitos 3.1, 3.2, 3.3, 4.3** (Hypothesis, mínimo 100 iterações)

  - [x] 7.3 Implementar componentes de interface da fila e a barra de filtros
    - Em `app.py`, seção Componentes de Interface: `selo_urgencia(nivel, cor)`, `cartao_denuncia(d, resultado)` exibindo Protocolo, Nível, Score, resumo da descrição, bairro e tempo decorrido, `painel_explicacao(resultado)` listando cada fator e pontos, e `barra_filtros()` retornando o dict de filtros (nível, tipo, espécie, bairro, status).
    - _Requisitos: 3.2, 3.4, 3.5, 2.11_

  - [x] 7.4 Integrar a fila à página de fila e mapa
    - Em `app.py`, seção Páginas: iniciar `pagina_fila_e_mapa(con)` renderizando a barra de filtros e a fila priorizada (cartões ordenados por Score), e exibir, ao selecionar uma denúncia, os detalhes com a explicação do Score.
    - _Requisitos: 3.1, 3.4, 3.5, 8.3_

- [x] 8. Implementar o mapa de ocorrências
  - [x] 8.1 Implementar a renderização do mapa com cores por urgência
    - Em `app.py`, dentro de `pagina_fila_e_mapa(con)`: exibir no mapa (via `st.map`/`pydeck`, recursos nativos) as denúncias ABERTA ou EM ATENDIMENTO posicionadas por latitude/longitude, cada marcador com a cor do seu Nível de Urgência, aplicando os mesmos filtros ativos da fila.
    - _Requisitos: 4.1, 4.2, 4.3, 10.3_

- [x] 9. Checkpoint — Garantir que os testes passem
  - Garanta que todos os testes passem; pergunte ao usuário em caso de dúvidas.

- [x] 10. Implementar o fluxo de atendimento e histórico
  - [x] 10.1 Implementar a máquina de estados e transição atômica no banco
    - Em `app.py`, seção Banco: `transicionar_status(con, protocolo, novo_status, autor, observacao, associacao=None)` validando contra `TRANSICOES` (recusa transições fora da máquina sem tocar o banco); para tomada de ABERTA, usar `UPDATE ... WHERE protocolo = ? AND status = 'ABERTA'` e recusar quando `rowcount == 0`; gravar a atualização de status e o item de `historico` (data/hora, autor, status anterior, novo status, observação) na mesma transação; gravar `primeiro_atendimento_em` apenas na primeira transição ABERTA → EM ATENDIMENTO, sem sobrescrever.
    - _Requisitos: 5.1, 5.2, 5.3, 5.4, 5.6, 5.7, 5.8, 5.9, 6.4_

  - [ ]* 10.2 Escrever propriedade de aceitação da máquina de estados
    - **Property 12: Aceitação da máquina de estados** — transição aceita sse novo status ∈ `TRANSICOES[atual]`; estados finais sem saída; tomada aceita sse status atual é ABERTA.
    - **Validates: Requisitos 5.1, 5.2, 5.3, 5.4, 5.7** (Hypothesis, mínimo 100 iterações)

  - [ ]* 10.3 Escrever propriedade de transição recusada não alterar estado nem histórico
    - **Property 13: Transição recusada não altera estado nem histórico** — solicitação inválida mantém o status e não acrescenta item ao Histórico.
    - **Validates: Requisitos 5.4, 5.9** (Hypothesis, mínimo 100 iterações)

  - [ ]* 10.4 Escrever propriedade de histórico em ordem cronológica crescente
    - **Property 14: Histórico em ordem cronológica crescente** — `listar_historico` retorna itens em ordem não decrescente de data/hora e `id`.
    - **Validates: Requisitos 5.10** (Hypothesis, mínimo 100 iterações)

  - [x] 10.5 Integrar as ações de atendimento à página de fila e mapa
    - Em `app.py`, dentro de `pagina_fila_e_mapa(con)`: ações para assumir denúncia (solicitar nome do voluntário obrigatório e associação de resgate — nome/CNPJ da ONG) e para mudar status (RESGATADO, NÃO LOCALIZADO, ENCERRADA) com observação; exibir mensagens de recusa para transições inválidas ou denúncia já atendida; exibir o Histórico completo em ordem cronológica crescente. Invalidar o cache de leitura após mutações.
    - _Requisitos: 5.5, 5.6, 5.7, 5.8, 5.10, 8.3_

  - [ ]* 10.6 Escrever testes de integração de atendimento e histórico
    - Tomada vira EM ATENDIMENTO com responsável e associação gravados na mesma transação; segunda tomada concorrente recusada (Req. 5.6, 5.7); transição efetivada grava exatamente um item de histórico correto; transição recusada não grava (Req. 5.8, 5.9).
    - _Requisitos: 5.6, 5.7, 5.8, 5.9_

- [x] 11. Implementar o painel da coordenação
  - [x] 11.1 Implementar lógica pura de agregações
    - Em `app.py`: funções puras que, dado um conjunto de denúncias, calculam contagens (abertas, em atendimento, resgatadas no dia, resgatadas no total), tempo médio até o primeiro atendimento sobre o subconjunto já atendido, e distribuições por nível, por tipo e por bairro (partições cujas contagens somam o total).
    - _Requisitos: 6.1, 6.2, 6.3, 6.4, 6.5_

  - [ ]* 11.2 Escrever propriedade de correção das agregações da coordenação
    - **Property 15: Correção das agregações da coordenação** — cada contagem iguala o número de denúncias que satisfazem o predicado; a média iguala a média dos tempos até o primeiro atendimento; cada distribuição é uma partição cujas contagens somam o total.
    - **Validates: Requisitos 6.1, 6.2, 6.3, 6.4, 6.5** (Hypothesis, mínimo 100 iterações)

  - [x] 11.3 Implementar a página da coordenação
    - Em `app.py`, seção Páginas: `pagina_coordenacao(con)` exibindo os indicadores agregados (abertas, em atendimento, resgatadas no dia e no total, tempo médio até o primeiro atendimento) e as distribuições por nível, tipo e bairro usando gráficos nativos do Streamlit.
    - _Requisitos: 6.1, 6.2, 6.3, 6.4, 6.5, 8.4_

- [x] 12. Wiring final e navegação por perfis
  - [x] 12.1 Implementar `main`, seletor de perfil e roteamento
    - Em `app.py`, seção main: `main()` inicializando o banco (seed quando vazio), renderizando na barra lateral o seletor de perfil (Cidadão Denunciante, Voluntário, Coordenação) e o controle de reset dos dados de demonstração, e roteando para `pagina_registro`, `pagina_fila_e_mapa` ou `pagina_coordenacao` conforme o perfil. Garantir interface integralmente em pt-BR.
    - _Requisitos: 7.4, 7.5, 8.1, 8.2, 8.3, 8.4, 8.5, 10.1, 10.2_

  - [ ]* 12.2 Escrever testes de roteamento por perfil e smoke estruturais
    - Cada valor do seletor aciona a página correta (Req. 8.1–8.4); verificações smoke de configuração presente, existência de `run_self_tests`, arquivo único e interface em pt-BR.
    - _Requisitos: 8.1, 8.2, 8.3, 8.4, 9.5, 11.2_

- [x] 13. Polimento visual para a demo
  - [x] 13.1 Ajustar apresentação e consistência visual
    - Em `app.py`: aplicar título e ícone da aplicação, cabeçalhos de página em pt-BR, selos de urgência coloridos consistentes com `cores_urgencia`, layout dos cartões e do painel para legibilidade na demonstração, e mensagens de sucesso/erro claras. Sem criar novos arquivos além de `app.py`.
    - _Requisitos: 10.1, 2.10, 3.4_

- [x] 14. Checkpoint final — Garantir que os testes passem
  - Garanta que todos os testes passem; pergunte ao usuário em caso de dúvidas.

## Notes

- Tarefas marcadas com `*` são opcionais (testes de propriedade, integração, exemplo e smoke) e podem ser puladas para um MVP mais rápido.
- Restrição de arquivo único: todas as tarefas de código da aplicação editam `app.py`. Os testes com `assert` do motor ficam em `run_self_tests` dentro de `app.py` (Requisito 11.2); se um arquivo de testes separado for usado para os testes de propriedade/integração com Hypothesis, ele é o único `.py` auxiliar permitido.
- Cada tarefa referencia requisitos específicos para rastreabilidade; as sub-tarefas de teste referenciam as propriedades de correção do design.
- Os testes de propriedade usam Hypothesis com no mínimo 100 iterações (`@settings(max_examples=100)` ou superior) e incluem um comentário de rastreabilidade no formato `# Feature: resgata-ja, Property N: ...`.
- Os checkpoints garantem validação incremental ao longo da ordem de implementação exigida.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["2.1", "4.1", "6.1", "7.1", "11.1"] },
    { "id": 2, "tasks": ["2.2", "2.3", "4.2", "6.2", "7.2", "11.2"] },
    { "id": 3, "tasks": ["2.4", "4.3", "4.4", "4.5", "4.6", "4.7", "4.8", "4.9", "4.10", "4.11", "4.12", "10.1"] },
    { "id": 4, "tasks": ["2.5", "6.3", "7.3", "10.2", "10.3", "10.4", "10.6"] },
    { "id": 5, "tasks": ["6.4", "7.4"] },
    { "id": 6, "tasks": ["8.1", "10.5"] },
    { "id": 7, "tasks": ["11.3"] },
    { "id": 8, "tasks": ["12.1"] },
    { "id": 9, "tasks": ["12.2", "13.1"] }
  ]
}
```
