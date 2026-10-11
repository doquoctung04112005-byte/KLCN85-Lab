from django.db import migrations, models
import django.db.models.deletion


def create_lab_references(apps, schema_editor):
    Document = apps.get_model("documents", "Document")
    LabDocumentReference = apps.get_model("documents", "LabDocumentReference")
    database = schema_editor.connection.alias

    for document_id in (
        Document.objects.using(database)
        .order_by("pk")
        .values_list("pk", flat=True)
        .iterator()
    ):
        LabDocumentReference.objects.using(database).create(document_id=document_id)


class Migration(migrations.Migration):
    dependencies = [
        ("documents", "0002_alter_document_content_documentattachment_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="LabDocumentReference",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                (
                    "document",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="lab_reference",
                        to="documents.document",
                    ),
                ),
            ],
            options={"ordering": ["id"]},
        ),
        migrations.RunPython(create_lab_references, migrations.RunPython.noop),
    ]
