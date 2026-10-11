from django.db import migrations, models


CONVERT_IDS = """
-- Preserve the seed command's stable document identity before replacing UUID keys.
UPDATE documents_document SET demo_code = 'demo_a1'
WHERE id = '11111111-1111-4111-8111-111111111111'::uuid;
UPDATE documents_document SET demo_code = 'demo_a2'
WHERE id = '22222222-2222-4222-8222-222222222222'::uuid;
UPDATE documents_document SET demo_code = 'demo_b1'
WHERE id = '33333333-3333-4333-8333-333333333333'::uuid;

-- The existing lab reference is a complete, stable UUID-to-number mapping.
INSERT INTO documents_labdocumentreference (document_id)
SELECT d.id FROM documents_document d
WHERE NOT EXISTS (
    SELECT 1 FROM documents_labdocumentreference r WHERE r.document_id = d.id
);

CREATE TEMP TABLE klcn85_folder_id_map ON COMMIT DROP AS
SELECT id AS old_id, row_number() OVER (ORDER BY id)::bigint AS new_id
FROM documents_documentfolder;
CREATE UNIQUE INDEX ON klcn85_folder_id_map (old_id);

CREATE FUNCTION pg_temp.klcn85_document_id(old_id uuid)
RETURNS bigint LANGUAGE sql STABLE AS $$
    SELECT id FROM documents_labdocumentreference WHERE document_id = $1
$$;
CREATE FUNCTION pg_temp.klcn85_folder_id(old_id uuid)
RETURNS bigint LANGUAGE sql STABLE AS $$
    SELECT new_id FROM klcn85_folder_id_map WHERE old_id = $1
$$;

-- Release UUID foreign keys before changing their columns. Unique constraints
-- and indexes on the referencing columns remain in place and are rebuilt.
ALTER TABLE documents_document DROP CONSTRAINT documents_document_folder_id_f2e8c7fd_fk_documents;
ALTER TABLE documents_documentattachment DROP CONSTRAINT documents_documentat_document_id_d235dfef_fk_documents;
ALTER TABLE documents_documentfolder DROP CONSTRAINT documents_documentfo_parent_id_24780762_fk_documents;
ALTER TABLE documents_labdocumentreference DROP CONSTRAINT documents_labdocumen_document_id_c2b86635_fk_documents;
ALTER TABLE sharing_documentshare DROP CONSTRAINT sharing_documentshar_document_id_391f5ca7_fk_documents;
ALTER TABLE documents_document DROP CONSTRAINT documents_document_pkey;
ALTER TABLE documents_documentfolder DROP CONSTRAINT documents_documentfolder_pkey;

ALTER TABLE documents_document ALTER COLUMN id TYPE bigint
USING pg_temp.klcn85_document_id(id);
ALTER TABLE documents_documentfolder ALTER COLUMN id TYPE bigint
USING pg_temp.klcn85_folder_id(id);
ALTER TABLE documents_documentfolder ALTER COLUMN parent_id TYPE bigint
USING pg_temp.klcn85_folder_id(parent_id);
ALTER TABLE documents_document ALTER COLUMN folder_id TYPE bigint
USING pg_temp.klcn85_folder_id(folder_id);
ALTER TABLE documents_documentattachment ALTER COLUMN document_id TYPE bigint
USING pg_temp.klcn85_document_id(document_id);
ALTER TABLE sharing_documentshare ALTER COLUMN document_id TYPE bigint
USING pg_temp.klcn85_document_id(document_id);

ALTER TABLE documents_document ADD CONSTRAINT documents_document_pkey PRIMARY KEY (id);
ALTER TABLE documents_documentfolder ADD CONSTRAINT documents_documentfolder_pkey PRIMARY KEY (id);

CREATE SEQUENCE documents_document_id_seq AS bigint;
ALTER SEQUENCE documents_document_id_seq OWNED BY documents_document.id;
ALTER TABLE documents_document ALTER COLUMN id
SET DEFAULT nextval('documents_document_id_seq'::regclass);
SELECT setval('documents_document_id_seq', COALESCE(MAX(id), 1), COUNT(*) > 0)
FROM documents_document;

CREATE SEQUENCE documents_documentfolder_id_seq AS bigint;
ALTER SEQUENCE documents_documentfolder_id_seq OWNED BY documents_documentfolder.id;
ALTER TABLE documents_documentfolder ALTER COLUMN id
SET DEFAULT nextval('documents_documentfolder_id_seq'::regclass);
SELECT setval('documents_documentfolder_id_seq', COALESCE(MAX(id), 1), COUNT(*) > 0)
FROM documents_documentfolder;

ALTER TABLE documents_documentfolder ADD CONSTRAINT klcn85_folder_parent_fk
FOREIGN KEY (parent_id) REFERENCES documents_documentfolder (id)
DEFERRABLE INITIALLY DEFERRED;
ALTER TABLE documents_document ADD CONSTRAINT klcn85_document_folder_fk
FOREIGN KEY (folder_id) REFERENCES documents_documentfolder (id)
DEFERRABLE INITIALLY DEFERRED;
ALTER TABLE documents_documentattachment ADD CONSTRAINT klcn85_attachment_document_fk
FOREIGN KEY (document_id) REFERENCES documents_document (id)
DEFERRABLE INITIALLY DEFERRED;
ALTER TABLE sharing_documentshare ADD CONSTRAINT klcn85_share_document_fk
FOREIGN KEY (document_id) REFERENCES documents_document (id)
DEFERRABLE INITIALLY DEFERRED;

DROP TABLE documents_labdocumentreference;
"""


class Migration(migrations.Migration):
    dependencies = [
        ("documents", "0003_labdocumentreference"),
        ("sharing", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="document",
            name="demo_code",
            field=models.CharField(
                max_length=32, unique=True, null=True, blank=True, editable=False
            ),
        ),
        migrations.SeparateDatabaseAndState(
            database_operations=[migrations.RunSQL(CONVERT_IDS)],
            state_operations=[
                migrations.DeleteModel(name="LabDocumentReference"),
                migrations.AlterField(
                    model_name="document",
                    name="id",
                    field=models.BigAutoField(primary_key=True, serialize=False),
                ),
                migrations.AlterField(
                    model_name="documentfolder",
                    name="id",
                    field=models.BigAutoField(primary_key=True, serialize=False),
                ),
            ],
        ),
    ]
