# Checklist de Publicação Segura

## Obrigatórios

- [ ] Não há `.env` versionado.
- [ ] Não há tokens, senhas ou credenciais.
- [ ] Não há CPF, e-mail, telefone ou PII real.
- [ ] Não há connection string.
- [ ] Não há banco SQLite, dump SQL ou CSV real.
- [ ] Não há endpoint interno corporativo.
- [ ] Não há URL de ambiente restrito.
- [ ] O projeto executa sem backend real.
- [ ] O build passa no GitHub Actions.
- [ ] A publicação é somente estática.
- [ ] O README informa que se trata de demo pública.

## Recomendados

- [ ] Existe `SECURITY.md`.
- [ ] Existe `CHANGELOG.md`.
- [ ] Existe licença definida.
- [ ] Existe fluxo de rollback.
- [ ] Existe rastreabilidade por PR.
- [ ] Existe versão/tag de release.
