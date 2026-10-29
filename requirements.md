# Requirements Document

## Introduction

O **ResgataJá** é uma fila inteligente de denúncias de resgate de animais, construída como aplicação Streamlit de arquivo único (`app.py`). ONGs e protetores independentes recebem denúncias de animais feridos, abandonados ou em situação de maus-tratos por canais desorganizados (WhatsApp, Instagram, telefone), o que faz casos graves se perderem entre casos menos urgentes e dificulta saber quem atende cada ocorrência.

O ResgataJá centraliza as denúncias em um único ponto, classifica automaticamente a urgência por meio de um motor de priorização explicável baseado em regras, monta uma fila priorizada, exibe as ocorrências em um mapa e oferece um painel de acompanhamento para a coordenação. O sistema atende três perfis de uso (cidadão denunciante, voluntário/protetor e coordenação), sem autenticação, com troca de perfil por seletor na barra lateral.

Esta é uma entrega de hackathon com restrição rígida de empacotamento: todo o código reside em um único arquivo `app.py`, acompanhado apenas de `requirements.txt` e do banco SQLite gerado em tempo de execução.

## Glossary

- **Sistema**: A aplicação ResgataJá como um todo, executada via `streamlit run app.py`.
- **Denuncia**: Registro de uma ocorrência de animal em risco, com dados da situação, localização, mídia e contato opcionais.
- **Protocolo**: Identificador único legível gerado para cada Denuncia no momento do registro.
- **Motor_de_Priorizacao**: Função pura que calcula o score de urgência (0 a 100) de uma Denuncia a partir de regras explícitas.
- **Score**: Valor numérico inteiro de 0 a 100 que representa a urgência de uma Denuncia.
- **Nivel_de_Urgencia**: Classificação textual derivada do Score, com valores CRÍTICO, ALTO, MÉDIO ou BAIXO, cada um associado a uma cor.
- **Fila_Priorizada**: Lista ordenada de Denuncias abertas, da maior para a menor urgência.
- **Mapa_de_Ocorrencias**: Visualização geográfica das Denuncias abertas, com marcadores coloridos por Nivel_de_Urgencia.
- **Painel_da_Coordenacao**: Tela com indicadores agregados e gráficos para acompanhamento geral.
- **Historico**: Conjunto de registros das mudanças de status de uma Denuncia, com data/hora, autor e observação.
- **Cidadao_Denunciante**: Perfil de usuário que relata um animal em risco, sem login.
- **Voluntario**: Perfil de usuário (voluntário ou protetor) que visualiza a fila, assume ocorrências e atualiza status.
- **Associacao_de_Resgate**: Nome da empresa/ONG ou CNPJ informado pelo Voluntario ao assumir uma Denuncia.
- **Coordenacao**: Perfil de usuário que acompanha o painel geral da ONG.
- **Status_da_Denuncia**: Estado atual da Denuncia, entre ABERTA, EM ATENDIMENTO, RESGATADO, NÃO LOCALIZADO e ENCERRADA.
- **Dicionario_de_Configuracao**: Estrutura de dados definida no topo do `app.py` contendo pesos de tipos de situação e palavras-chave com seus pontos.
- **Dados_de_Demonstracao**: Conjunto de Denuncias fictícias realistas usadas para popular o banco vazio na primeira execução.
- **Banco_de_Dados**: Banco SQLite acessado via `sqlite3` nativo, gerado em tempo de execução.
- **run_self_tests**: Função dentro do `app.py` que executa testes com `assert` sobre o Motor_de_Priorizacao.

## Requirements

### Requisito 1: Registro de Denúncia

**História de Usuário:** Como Cidadão Denunciante, quero relatar um animal em risco informando a situação e a localização, para que o caso entre na fila de atendimento com uma urgência calculada.

#### Critérios de Aceitação

1. THE Sistema SHALL apresentar ao Cidadao_Denunciante um formulário de registro de Denuncia sem exigir login e sem qualquer mecanismo de autenticação.
2. THE Sistema SHALL oferecer a seleção do tipo de situação, em campo de seleção única, entre os valores: ferido/atropelado, abandonado, maus-tratos, animal doente, preso/encurralado, filhotes orfãos, emergencias ambientais, animal perdido e outros.
3. THE Sistema SHALL oferecer a seleção da espécie, em campo de seleção única, entre os valores: cão, gato, silvestres e outros.
4. THE Sistema SHALL permitir a informação da quantidade de animais como número inteiro entre 1 e 999 inclusive.
5. THE Sistema SHALL permitir a informação de uma descrição livre em texto com no máximo 2000 caracteres.
6. THE Sistema SHALL exigir a informação de endereço e bairro da ocorrência, sem exigir número da edificação, e impedir o envio enquanto endereço ou bairro estiverem vazios.
7. THE Sistema SHALL preencher a latitude e a longitude com as coordenadas padrão da cidade e permitir o ajuste manual desses valores pelo Cidadao_Denunciante, restringindo a latitude ao intervalo de -90 a 90 e a longitude ao intervalo de -180 a 180.
8. THE Sistema SHALL permitir o anexo opcional de uma única foto da ocorrência em formato de imagem (JPG ou PNG) com tamanho máximo de 10 MB.
9. THE Sistema SHALL permitir a informação opcional do nome, com no máximo 120 caracteres, e do telefone do Cidadao_Denunciante, aceitando no telefone somente dígitos, espaços e os caracteres "+", "-", "(" e ")".
10. IF o tipo de situação, a espécie ou a quantidade de animais não forem informados, THEN THE Sistema SHALL impedir o envio e apresentar mensagem indicando cada campo obrigatório pendente, preservando os demais valores já preenchidos no formulário.
11. WHEN o Cidadao_Denunciante envia uma Denuncia válida, THE Sistema SHALL gerar um Protocolo único e persistir a Denuncia no Banco_de_Dados com Status_da_Denuncia igual a ABERTA.
12. IF a persistência da Denuncia no Banco_de_Dados falha após um envio válido, THEN THE Sistema SHALL não gerar Protocolo definitivo, apresentar mensagem indicando a falha no registro e preservar os valores preenchidos no formulário para nova tentativa.
13. WHEN uma Denuncia é registrada com sucesso, THE Sistema SHALL calcular o Score e o Nivel_de_Urgencia por meio do Motor_de_Priorizacao e apresentar ao Cidadao_Denunciante o Protocolo gerado e o Nivel_de_Urgencia calculado em até 5 segundos após o envio.

### Requisito 2: Motor de Priorização Explicável

**História de Usuário:** Como Voluntário, quero que cada denúncia receba um score de urgência calculado por regras explícitas e explicáveis, para que eu confie na ordem de atendimento e entenda o motivo da classificação.

#### Critérios de Aceitação

1. THE Motor_de_Priorizacao SHALL calcular um Score inteiro para cada Denuncia, resultante da soma dos componentes de tipo de situação, palavras-chave, quantidade de animais e tempo de espera.
2. IF a soma dos componentes do Score é menor que 0, THEN THE Motor_de_Priorizacao SHALL fixar o Score em 0.
3. IF a soma dos componentes do Score é maior que 100, THEN THE Motor_de_Priorizacao SHALL fixar o Score em 100.
4. THE Motor_de_Priorizacao SHALL atribuir ao Score um componente baseado no peso do tipo de situação, obedecendo à ordem decrescente de peso: ferido/atropelado, preso/encurralado, maus-tratos, emergencias ambientais, filhotes orfãos, animal doente, abandonado, animal perdido e outros.
5. THE Motor_de_Priorizacao SHALL atribuir ao Score um componente baseado em palavras-chave presentes na descrição, incluindo ao menos: sangrando, não se mexe, convulsão, atropelado, filhote, recém-nascido, chuva, frio, amarrado, sem água, agressão e outros.
6. WHEN a descrição contém palavras-chave com variações de acentuação, de maiúsculas e minúsculas ou de espaços em branco adjacentes, THE Motor_de_Priorizacao SHALL reconhecer essas palavras-chave independentemente de acentos, de caixa e desses espaços.
7. THE Motor_de_Priorizacao SHALL atribuir ao Score um componente baseado na quantidade de animais informada, limitado a um valor máximo de contribuição definido no Dicionario_de_Configuracao, de modo que quantidades acima do limite não aumentem esse componente.
8. WHILE uma Denuncia com tipo de situação diferente de abandonado permanece sem atendimento, THE Motor_de_Priorizacao SHALL atribuir ao Score um componente que cresce em função do tempo de espera decorrido entre a abertura e o instante de cálculo, limitado a um valor máximo de contribuição definido no Dicionario_de_Configuracao.
9. WHERE o tipo de situação é abandonado, THE Motor_de_Priorizacao SHALL atribuir ao componente de tempo de espera o valor zero.
10. THE Motor_de_Priorizacao SHALL converter o Score em um Nivel_de_Urgencia e associar uma cor a cada nível, classificando como CRÍTICO quando o Score for de 80 a 100, ALTO quando for de 60 a 79, MÉDIO quando for de 40 a 59 e BAIXO quando for de 0 a 39.
11. WHEN o Score de uma Denuncia é calculado, THE Motor_de_Priorizacao SHALL produzir uma explicação que lista cada fator considerado, as palavras-chave encontradas e os pontos atribuídos a cada fator e a cada palavra-chave.
12. THE Sistema SHALL definir os pesos dos tipos de situação, as palavras-chave com seus pontos, os limites máximos de contribuição dos componentes de quantidade e de tempo de espera e os limiares de Nivel_de_Urgencia em um Dicionario_de_Configuracao localizado no topo do arquivo `app.py`.
13. THE Motor_de_Priorizacao SHALL ser implementado como função pura, sem efeitos colaterais, recebendo os dados da Denuncia e o instante de cálculo como entrada e retornando o Score, o Nivel_de_Urgencia e a explicação.

### Requisito 3: Fila Priorizada

**História de Usuário:** Como Voluntário, quero ver as denúncias abertas ordenadas por urgência e filtrá-las, para que eu possa escolher qual ocorrência atender primeiro.

#### Critérios de Aceitação

1. THE Sistema SHALL apresentar na Fila_Priorizada as Denuncias cujo Status_da_Denuncia seja ABERTA ou EM ATENDIMENTO, ordenadas pelo Score em ordem decrescente.
2. THE Sistema SHALL oferecer filtros da Fila_Priorizada por Nivel_de_Urgencia, por tipo de situação, por espécie, por bairro e por Status_da_Denuncia.
3. WHEN o Voluntario aplica um ou mais filtros, THE Sistema SHALL exibir apenas as Denuncias que atendem a todos os filtros selecionados, mantendo a ordenação por Score decrescente.
4. THE Sistema SHALL exibir, para cada item da Fila_Priorizada, o Protocolo, o Nivel_de_Urgencia, o Score, um resumo da descrição, o bairro e o tempo decorrido desde a abertura.
5. WHEN o Voluntario seleciona uma Denuncia na Fila_Priorizada, THE Sistema SHALL exibir os detalhes da Denuncia, incluindo a explicação do Score com cada fator e os pontos atribuídos.

### Requisito 4: Mapa de Ocorrências

**História de Usuário:** Como Voluntário, quero ver as denúncias abertas em um mapa com cores por urgência, para que eu entenda a distribuição geográfica das ocorrências.

#### Critérios de Aceitação

1. THE Mapa_de_Ocorrencias SHALL exibir as Denuncias cujo Status_da_Denuncia seja ABERTA ou EM ATENDIMENTO, posicionadas pela latitude e longitude de cada Denuncia.
2. THE Mapa_de_Ocorrencias SHALL representar cada Denuncia com a cor correspondente ao seu Nivel_de_Urgencia.
3. WHEN o Voluntario aplica filtros por Nivel_de_Urgencia, tipo de situação, espécie, bairro ou Status_da_Denuncia, THE Mapa_de_Ocorrencias SHALL exibir apenas as Denuncias que atendem a todos os filtros selecionados.

### Requisito 5: Atendimento e Mudança de Status

**História de Usuário:** Como Voluntário, quero assumir uma denúncia e atualizar seu status com registro de histórico, para que a equipe saiba quem atende cada caso e qual é o andamento. Com preenchimento só de nome e associação a empresas de resgate, cnpj ou nome da empresa/ong.

#### Critérios de Aceitação

1. THE Sistema SHALL permitir, a partir do Status_da_Denuncia ABERTA, exclusivamente a transição para EM ATENDIMENTO.
2. THE Sistema SHALL permitir, a partir do Status_da_Denuncia EM ATENDIMENTO, exclusivamente as transições para RESGATADO, para NÃO LOCALIZADO e para ENCERRADA.
3. THE Sistema SHALL tratar os valores de Status_da_Denuncia RESGATADO, NÃO LOCALIZADO e ENCERRADA como estados finais, sem nenhuma transição de saída permitida.
4. IF for solicitada uma mudança de Status_da_Denuncia não prevista nos critérios 1 e 2, THEN THE Sistema SHALL recusar a mudança, preservar o Status_da_Denuncia atual e apresentar mensagem indicando que a transição não é permitida.
5. WHEN o Voluntario assume uma Denuncia cujo Status_da_Denuncia é ABERTA, THE Sistema SHALL solicitar o nome do Voluntario e a Associacao_de_Resgate (nome da empresa/ONG ou CNPJ) e exigir o preenchimento do nome do Voluntario para concluir a ação.
6. WHEN o Voluntario confirma a tomada de uma Denuncia cujo Status_da_Denuncia é ABERTA com o nome do Voluntario preenchido, THE Sistema SHALL registrar de forma atômica o Voluntario responsável e sua Associacao_de_Resgate, alterar o Status_da_Denuncia para EM ATENDIMENTO e persistir essa atribuição no Banco_de_Dados.
7. IF um Voluntario tenta assumir uma Denuncia cujo Status_da_Denuncia não é mais ABERTA, THEN THE Sistema SHALL recusar a ação, preservar o Voluntario responsável e o Status_da_Denuncia atuais e informar que a Denuncia já está sendo atendida por outro Voluntario ou já foi encerrada.
8. WHEN qualquer mudança de Status_da_Denuncia é efetivada, THE Sistema SHALL registrar no Historico, de forma atômica com a mudança, um item contendo data e hora, autor da mudança, o Status_da_Denuncia anterior, o novo Status_da_Denuncia e a observação informada.
9. IF uma mudança de Status_da_Denuncia é recusada, THEN THE Sistema SHALL não registrar nenhum item no Historico referente a essa tentativa.
10. THE Sistema SHALL apresentar o Historico completo de cada Denuncia em ordem cronológica crescente, do item mais antigo para o mais recente.

### Requisito 6: Painel da Coordenação

**História de Usuário:** Como Coordenação da ONG, quero acompanhar indicadores agregados das denúncias, para que eu monitore o desempenho do atendimento e a distribuição das ocorrências.

#### Critérios de Aceitação

1. THE Painel_da_Coordenacao SHALL exibir a quantidade de Denuncias com Status_da_Denuncia igual a ABERTA.
2. THE Painel_da_Coordenacao SHALL exibir a quantidade de Denuncias com Status_da_Denuncia igual a EM ATENDIMENTO.
3. THE Painel_da_Coordenacao SHALL exibir a quantidade de Denuncias com Status_da_Denuncia igual a RESGATADO no dia corrente e a quantidade total de Denuncias com Status_da_Denuncia igual a RESGATADO.
4. THE Painel_da_Coordenacao SHALL exibir o tempo médio decorrido entre a abertura e o primeiro atendimento das Denuncias que já tiveram ao menos um atendimento.
5. THE Painel_da_Coordenacao SHALL exibir a distribuição de Denuncias por Nivel_de_Urgencia, por tipo de situação e por bairro, utilizando gráficos nativos do Streamlit.

### Requisito 7: Dados de Demonstração e Reinicialização

**História de Usuário:** Como usuário avaliando o sistema, quero que a aplicação já tenha dados realistas na primeira execução e possa ser reiniciada, para que eu explore as funcionalidades sem precisar cadastrar denúncias manualmente.

#### Critérios de Aceitação

1. WHEN a aplicação é executada e o Banco_de_Dados está vazio, THE Sistema SHALL popular o Banco_de_Dados com aproximadamente 30 Dados_de_Demonstracao representando Denuncias fictícias.
2. THE Dados_de_Demonstracao SHALL distribuir as Denuncias entre bairros de uma cidade brasileira, com coordenadas de latitude e longitude plausíveis para cada bairro.
3. THE Dados_de_Demonstracao SHALL incluir tipos de situação variados, horários de abertura diferentes e ao menos algumas Denuncias com Status_da_Denuncia igual a RESGATADO.
4. THE Sistema SHALL oferecer na barra lateral um controle para resetar o Banco_de_Dados e recriar os Dados_de_Demonstracao.
5. WHEN o usuário aciona o controle de reset, THE Sistema SHALL remover as Denuncias existentes e recriar os Dados_de_Demonstracao.

### Requisito 8: Perfis de Usuário e Navegação

**História de Usuário:** Como usuário do sistema, quero alternar entre os perfis de cidadão, voluntário e coordenação por um seletor simples, para que eu acesse as telas adequadas ao meu papel sem autenticação.

#### Critérios de Aceitação

1. THE Sistema SHALL apresentar na barra lateral um seletor de perfil entre Cidadao_Denunciante, Voluntario e Coordenacao.
2. WHILE o perfil selecionado é Cidadao_Denunciante, THE Sistema SHALL apresentar a tela de Registro de Denuncia.
3. WHILE o perfil selecionado é Voluntario, THE Sistema SHALL apresentar a Fila_Priorizada, o Mapa_de_Ocorrencias e as ações de atendimento e mudança de status.
4. WHILE o perfil selecionado é Coordenacao, THE Sistema SHALL apresentar o Painel_da_Coordenacao.
5. THE Sistema SHALL operar sem qualquer mecanismo de autenticação.

### Requisito 9: Empacotamento em Arquivo Único

**História de Usuário:** Como organizador do hackathon, quero que toda a solução esteja em um único arquivo `app.py` executável de forma simples, para que a entrega atenda à restrição obrigatória.

#### Critérios de Aceitação

1. THE Sistema SHALL conter todo o código-fonte da aplicação em um único arquivo denominado `app.py`.
2. THE Sistema SHALL dispensar a criação de módulos, pacotes, templates ou arquivos `.py` auxiliares.
3. WHERE forem necessárias dependências ou persistência, THE Sistema SHALL permitir a existência apenas de um arquivo `requirements.txt` e do Banco_de_Dados SQLite gerado em tempo de execução.
4. THE Sistema SHALL ser executável com os comandos `pip install -r requirements.txt` e `streamlit run app.py`.
5. THE Sistema SHALL organizar o conteúdo de `app.py` em seções comentadas: configuração, banco, dados de exemplo, motor de priorização, componentes de interface, páginas e main.

### Requisito 10: Requisitos Não Funcionais de Interface e Execução

**História de Usuário:** Como usuário brasileiro executando a solução localmente, quero a interface em português e o funcionamento offline após a instalação, para que eu use o sistema sem barreiras de idioma ou de conectividade.

#### Critérios de Aceitação

1. THE Sistema SHALL apresentar toda a interface em português do Brasil.
2. WHERE já instaladas as dependências, THE Sistema SHALL executar localmente sem acesso à internet, exceto para o carregamento dos tiles do Mapa_de_Ocorrencias.
3. THE Sistema SHALL exibir o Mapa_de_Ocorrencias utilizando recursos nativos do Streamlit ou pydeck, sem dependências adicionais além das declaradas em `requirements.txt`.

### Requisito 11: Qualidade de Código e Testes do Motor de Priorização

**História de Usuário:** Como pessoa desenvolvedora mantendo a solução, quero código legível e um motor de priorização testável isoladamente, para que eu valide a lógica de urgência sem executar a interface.

#### Critérios de Aceitação

1. THE Sistema SHALL organizar o código em funções pequenas, com type hints e docstrings curtas.
2. THE Sistema SHALL fornecer uma função `run_self_tests` que exercita o Motor_de_Priorizacao por meio de instruções `assert`.
3. WHEN `run_self_tests` é executada sobre um Motor_de_Priorizacao correto, THE Sistema SHALL concluir a execução sem disparar falhas de `assert`.
4. FOR ALL dados de entrada e instante de referência iguais, THE Motor_de_Priorizacao SHALL produzir o mesmo Score, Nivel_de_Urgencia e explicação.
