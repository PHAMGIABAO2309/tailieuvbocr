// app.js
import express from 'express';
import cors from 'cors';
import { Client } from '@elastic/elasticsearch';
import mysql from 'mysql2/promise';

const app = express();
app.use(cors());

// ================= Elasticsearch client =================
const esClient = new Client({
  node: 'https://localhost:9200',
  auth: { username: 'elastic', password: 'xlhuHK-gHz+O8O1W0CWV' },
  tls: { rejectUnauthorized: false }
});

// ================= 1. Create index =================
async function createIndex() {
  await esClient.indices.create(
    {
      index: 'vanban',
      body: {
        settings: {
          analysis: {
            analyzer: {
              vietnamese_analyzer: {
                tokenizer: 'icu_tokenizer',
                filter: ['lowercase', 'icu_folding']
              }
            }
          }
        },
        mappings: {
          properties: {
            filecode: { type: 'keyword' },
            title: { type: 'text', analyzer: 'vietnamese_analyzer' },
            subject: { type: 'text', analyzer: 'vietnamese_analyzer' },
            startdate: { type: 'date' },
            dateupdate: { type: 'date' },
            path: { type: 'keyword' }
          }
        }
      }
    },
    { ignore: [400] }
  );

  console.log('✅ Index created or exists');
}

// ================= 2. Import MySQL =================
async function importFromMySQL(batchSize = 500) {
  const connection = await mysql.createConnection({
    host: 'localhost',
    user: 'root',
    password: '',
    database: 'storages_documents_3'
  });

  const [rows] = await connection.execute(`
    SELECT 
      ido.FileCode AS filecode,
      ido.Subject  AS subject,
      Title        AS title,
      StartDate    AS startdate,
      dateupdate,
      path
    FROM files f
    JOIN infomation_documents_out ido 
      ON f.FileCode = ido.FileCode
  `);

  console.log(`📦 Importing ${rows.length} documents...`);

  for (let i = 0; i < rows.length; i += batchSize) {
    const batch = rows.slice(i, i + batchSize);
    const body = batch.flatMap(doc => [
      { index: { _index: 'vanban', _id: doc.filecode } },
      doc
    ]);

    await esClient.bulk({ refresh: true, body });
    console.log(`✅ Imported batch ${i / batchSize + 1}`);
  }

  await connection.end();
  console.log('✅ Import completed');
}

// ================= 3. Search Suggest API (TỐI ƯU) =================
app.get('/api/search_suggest', async (req, res) => {
  const q = (req.query.subject || '').trim();
  if (!q) return res.json([]);

  try {
    const response = await esClient.search({
      index: 'vanban',
      size: 20,
      _source: ['filecode', 'subject'],
      query: {
        bool: {
          should: [
            {
              // ✅ Tìm từ rời rạc (KHÔNG cần liền nhau)
              match: {
                subject: {
                  query: q,
                  operator: 'OR',
                  minimum_should_match: '60%',
                  boost: 2
                }
              }
            },
            {
              // ✅ Ưu tiên nếu gõ đúng cụm
              match_phrase_prefix: {
                subject: {
                  query: q,
                  boost: 3
                }
              }
            }
          ]
        }
      },
      highlight: {
        fields: {
          subject: {}
        },
        pre_tags: ['<em>'],
        post_tags: ['</em>']
      }
    });

    const results = response.hits.hits.map(hit => ({
      filecode: hit._source.filecode,
      subject: hit.highlight?.subject?.[0] || hit._source.subject
    }));

    res.setHeader('Content-Type', 'application/json; charset=utf-8');
    res.json(results);
  } catch (err) {
    console.error(err);
    res.status(500).json({ error: err.message });
  }
});

// ================= 4. Start server =================
(async () => {
  await createIndex();
  await importFromMySQL();
  app.listen(5000, () =>
    console.log('🚀 Server running at http://localhost:5000')
  );
})();
