from pathlib import Path

from django.db import migrations

PASTA_SQL = Path(__file__).resolve().parents[2] / "db" / "sql"


def arquivo_sql(nome: str) -> migrations.RunSQL:
    return migrations.RunSQL(sql=[(PASTA_SQL / nome).read_text(encoding="utf-8")], reverse_sql=migrations.RunSQL.noop)
