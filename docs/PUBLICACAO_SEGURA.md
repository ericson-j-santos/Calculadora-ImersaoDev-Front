# Publicação Segura no GitHub Pages

## Objetivo

Publicar uma versão estática e segura do projeto usando GitHub Pages, sem expor dados sensíveis, credenciais, endpoints internos ou integrações reais.

## Arquitetura

```text
GitHub Repository
  -> GitHub Actions
  -> validação de segurança
  -> artifact
  -> GitHub Pages
```

## Restrições

GitHub Pages deve hospedar somente HTML, CSS, JavaScript, imagens, assets públicos e dados fictícios.

Não deve hospedar backend, banco de dados, credenciais, integrações reais, APIs internas ou dados pessoais reais.

## Estratégia de rollback

1. Identificar commit problemático.
2. Reverter por novo commit ou Pull Request.
3. Aguardar novo deploy automático.
4. Validar URL pública.
5. Registrar no changelog.

## Critério de aceite

A publicação só é considerada válida quando:

- O workflow finaliza com sucesso;
- A URL pública abre corretamente;
- Não há erro de assets;
- Não há vazamento de dados sensíveis;
- O projeto informa claramente que é uma demo pública.
