# 🐾 ResgataJá

**Fila inteligente de denúncias de resgate de animais.**

O ResgataJá centraliza denúncias de animais feridos, abandonados ou em situação de maus-tratos, calcula automaticamente a urgência de cada caso com um motor de priorização explicável e organiza tudo em uma fila e um mapa para que voluntários e ONGs atendam primeiro quem mais precisa.

Projeto desenvolvido para o hackathon com o tema **Resgate de Pets**.

---

## O problema

ONGs e protetores independentes recebem denúncias por WhatsApp, Instagram, telefone e boca a boca, sem um lugar único. Na prática:

- **Casos graves se perdem** entre pedidos menos urgentes: um animal atropelado espera na mesma fila que um caso que pode aguardar.
- **Ninguém sabe quem está atendendo**, então casos são duplicados ou esquecidos.
- **Não há dados** para a coordenação saber onde e como agir.

## A solução

| Etapa | O que acontece |
|---|---|
| 1. Denúncia | Qualquer pessoa registra a ocorrência, sem login. |
| 2. Priorização | O motor calcula um score de 0 a 100 e explica cada ponto. |
| 3. Fila e mapa | Os casos aparecem ordenados por urgência e no mapa, com cores por nível. |
| 4. Atendimento | Um voluntário assume o caso, que fica bloqueado para os demais, e atualiza o status. |
| 5. Coordenação | Um painel mostra indicadores e a distribuição das ocorrências. |

---

## Funcionalidades

### 👤 Cidadão denunciante
- Formulário sem login: tipo de situação, espécie, quantidade de animais, descrição livre, endereço e bairro (obrigatórios), coordenadas ajustáveis, foto e contato opcionais.
- Ao enviar, recebe na hora o **protocolo** (ex.: `RJ-20261029-0031`) e o **nível de urgência** calculado.

### 🙋 Voluntário
- **Fila priorizada** com as denúncias abertas e em atendimento, ordenadas por score.
- **Filtros** por nível de urgência, tipo de situação, espécie, bairro e status.
- **Detalhe do caso** com a explicação do score: cada fator e cada palavra-chave, com os pontos que somou.
- **Mapa de ocorrências** com cores por nível, respeitando os mesmos filtros da fila.
- **Assumir atendimento** informando nome (obrigatório) e ONG ou CNPJ (opcional). Um caso já em atendimento não pode ser assumido por outra pessoa.
- **Histórico** completo de cada denúncia, em ordem cronológica.

### 📊 Coordenação
- Quantidade de denúncias abertas, em atendimento e resgatadas (no dia e no total).
- Tempo médio entre a abertura e o primeiro atendimento.
- Distribuição por nível de urgência, tipo de situação e bairro.

---

## Motor de priorização

O score é calculado por **regras explícitas**, sem modelos de IA externos. Ele soma quatro componentes e é limitado ao intervalo de 0 a 100:

1. **Tipo de situação**, em ordem decrescente de peso: ferido/atropelado, preso/encurralado, maus-tratos, emergências ambientais, filhotes órfãos, animal doente, abandonado, animal perdido e outros.
2. **Palavras-chave na descrição**, como *sangrando*, *não se mexe*, *convulsão*, *atropelado*, *filhote*, *recém-nascido*, *chuva*, *frio*, *amarrado*, *sem água* e *agressão*. O reconhecimento ignora acentos e maiúsculas/minúsculas.
3. **Quantidade de animais**, com contribuição limitada.
4. **Tempo de espera**: enquanto a denúncia estiver aberta, ela ganha pontos com o tempo, para que nenhum caso fique esquecido no fim da fila.

| Nível | Score | Cor |
|---|---|---|
| CRÍTICO | 75 a 100 | 🔴 vermelho |
| ALTO | 50 a 74 | 🟠 laranja |
| MÉDIO | 25 a 49 | 🟡 amarelo |
| BAIXO | 0 a 24 | 🟢 verde |

Todos os pesos, palavras-chave e limites ficam em um **dicionário de configuração no topo do `app.py`**, e podem ser ajustados sem mexer na lógica.

O motor é uma **função pura**: recebe os dados da denúncia e o instante de referência e devolve score, nível e explicação. Para as mesmas entradas, o resultado é sempre o mesmo.

### Fluxo de status

```
ABERTA ──► EM ATENDIMENTO ──► RESGATADO
                         ├──► NÃO LOCALIZADO
                         └──► ENCERRADA
```

Toda mudança de status gera um registro no histórico com data e hora, autor e observação.

---

## Como executar

**Pré-requisitos:** Python 3.11 ou superior.

```bash
pip install -r requirements.txt
streamlit run app.py
```

O app abre em `http://localhost:8501`. Na primeira execução, o banco SQLite é criado e populado com cerca de 30 denúncias de demonstração.

### Navegação
Use o **seletor de perfil** na barra lateral para alternar entre Cidadão, Voluntário e Coordenação. O botão **Resetar demo**, também na barra lateral, apaga as denúncias e recria os dados de demonstração.

### Testes do motor
Os testes do motor de priorização ficam na função `run_self_tests()`, dentro do próprio `app.py`:

```bash
python app.py --self-test
```

---

## Estrutura do projeto

A entrega segue a regra do hackathon: **todo o código em um único arquivo `app.py`**.

```
.
├── app.py             # aplicação completa
├── requirements.txt   # dependências
└── README.md
```

O banco SQLite é gerado automaticamente em tempo de execução.

O `app.py` está organizado em seções comentadas:

| Seção | Conteúdo |
|---|---|
| Configuração | Dicionário de pesos, palavras-chave, níveis, cores, listas de opções e transições de status |
| Banco | Conexão SQLite, schema, inserção, consultas e transições de status |
| Dados de exemplo | Geração, carga inicial e reset das denúncias de demonstração |
| Motor de priorização | Normalização de texto e cálculo do score com explicação |
| Componentes de interface | Selos de urgência, cartões, filtros e painel de explicação |
| Páginas | Registro, fila e mapa, painel da coordenação |
| `run_self_tests` | Testes do motor com `assert` |
| main | Seletor de perfil, roteamento e inicialização |

---

## Tecnologias

- **Python + Streamlit**: interface web completa em um único arquivo.
- **SQLite** (`sqlite3` nativo): persistência sem servidor.
- **Mapa nativo do Streamlit**: sem dependências extras.
- **Kiro (spec-driven development)**: requisitos, design e tarefas definidos antes do código.

Depois de instaladas as dependências, o app roda localmente sem internet, exceto pelo carregamento do mapa.

---

## Fora do escopo desta versão

- Autenticação de usuários
- Integração real com WhatsApp ou SMS
- Deploy em nuvem
- Modelos de IA externos ou APIs pagas

## Próximos passos

- Receber denúncias diretamente pelo WhatsApp
- Parcerias com ONGs, prefeituras e serviços de disque-denúncia
- App para voluntários em campo
- Mapa de calor para apoiar políticas públicas

---

## Time ResgataJá

- Diogo Bassalobre
- João Victor Haleplian
- Lucas Vadenal
