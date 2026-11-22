# Kết hợp tìm kiếm từ khóa, vector và bước xếp hạng lại

Một công cụ tìm kiếm tốt không chỉ cần trả về document **có từ khóa giống câu hỏi**, mà còn phải tìm được document **có ý nghĩa liên quan** dù từ ngữ khác nhau, giữ được **mã sản phẩm/tên API/điều khoản chính xác**, rồi sắp xếp những kết quả hữu ích nhất lên trên. Trong MongoDB, cách tiếp cận này thường được gọi là **hybrid search**: kết hợp **tìm kiếm từ khóa (lexical/full-text search)**, **tìm kiếm vector (semantic/vector search)** và, khi cần, **reranking** trên một tập ứng viên nhỏ.

Ví dụ người dùng tìm: **“cách sửa lỗi E11000 khi thêm tài khoản”**. Tìm kiếm từ khóa rất mạnh với chuỗi chính xác `E11000`, nhưng một tài liệu có tiêu đề **“Xử lý trùng unique index”** có thể không dùng nguyên câu hỏi. Embedding search có thể tìm tài liệu cùng ý nghĩa, còn một **reranker** có thể ưu tiên đoạn mô tả đúng thao tác xử lý lỗi thay vì một trang chỉ nhắc đến lỗi trong danh sách thuật ngữ.

Tại sao không dùng một cách tìm duy nhất?

- **Chỉ keyword:** dễ bỏ sót đồng nghĩa, câu diễn đạt khác, truy vấn bằng ngôn ngữ khác; nhưng rất tốt cho mã lỗi, tên người, mã SKU và thuật ngữ chính xác.
- **Chỉ vector:** dễ tìm đúng ý tổng quát nhưng có thể nhầm mã phiên bản, ký hiệu ngắn, phủ định hoặc điều kiện chính xác; còn phải tốn chi phí tạo embeddings/index/ANN.
- **Kết hợp hai danh sách:** tăng khả năng có **candidate đúng** nhưng thứ tự top 5 vẫn có thể chưa tối ưu.
- **Reranking:** xem xét sâu hơn mối quan hệ giữa câu hỏi và các candidate texts để **sắp lại thứ tự**; không cứu được document đúng nếu nó chưa bao giờ lọt vào danh sách ứng viên.

Bài thuộc chương **Tìm kiếm vector** của module *Database Engine Document MongoDB*. Các ví dụ dùng MongoDB Search (`$search`), MongoDB Vector Search (`$vectorSearch`), `$rankFusion`, `$scoreFusion` và một tầng reranker ở ứng dụng hoặc MongoDB `$rerank` khi môi trường hỗ trợ. Đây là bài về **thiết kế pipeline tìm kiếm, cú pháp, điều kiện tương thích, đánh giá relevance và vận hành**, không chỉ là ví dụ gọi một API.

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt lexical retrieval, vector retrieval, rank/score fusion và semantic reranking.
2. Giải thích điểm mạnh/yếu của BM25/Atlas Search và embedding similarity trong các query có mã, tên riêng, tiếng Việt, từ đồng nghĩa hay câu dài.
3. Tạo schema MongoDB cho tài liệu tìm kiếm với `title`, `body`, `embedding`, `tenantId`, `visibility`, `version`.
4. Tạo index MongoDB Search và Vector Search với vector dimension/similarity và indexed filter fields phù hợp.
5. Viết các pipeline `$search`, `$vectorSearch` và hybrid `$rankFusion` với các giới hạn thực tế.
6. Sử dụng hoặc phân biệt `$scoreFusion`, ứng dụng RRF và biết khi nào phải chuẩn hóa raw scores.
7. Thiết kế **bước rerank** (cross-encoder/model relevance) sau fusion, tính chi phí/latency/độ dài đầu vào.
8. Đảm bảo **authorization, tenant isolation, document status, freshness** ở cả lexical và vector branches.
9. Đánh giá Recall@K, Precision@K, MRR, nDCG, query subsets và latency/cost; tránh tối ưu chỉ dựa trên điểm số kỹ thuật.
10. Xử lý failure modes như index chưa sẵn sàng, embedding sai chiều, empty branch, duplicate chunks, kết quả bất ổn và fallback.

> **Điều kiện chạy:** MongoDB Search và MongoDB Vector Search phải được hỗ trợ trên deployment (ví dụ Atlas hoặc deployment local/self-managed có search service tương thích). `$vectorSearch` ANN trên Atlas có các mốc server như **6.0.11/7.0.2+**, ENN từ các patch phù hợp; hybrid `$rankFusion` yêu cầu **MongoDB 8.0+**, `$scoreFusion` yêu cầu **8.3+**. `$rerank` là một tính năng **Native Reranking** riêng, cần đáp ứng phiên bản/feature toggle/model availability của MongoDB hiện hành; tài liệu `$rerank` mới đang nêu **9.0+** và có model/tier restrictions. Không suy rằng bất kỳ cluster có `aggregate()` đều chạy toàn bộ các stages. Đối chiếu tài liệu đúng server version, FCV, Atlas project/cluster tier và region.

## 1. Bản đồ toàn bộ pipeline hybrid retrieval

~~~text
User query: "tài liệu xử lý lỗi E11000"
                        |
                        v
             Normalize / identify intent
                        |
             +----------+----------+
             |                     |
             v                     v
     Keyword / BM25 search    Embedding model
      $search (top L)         Query vector
             |                     |
             |                     v
             |                $vectorSearch
             |                  (top V)
             |                     |
             +----------+----------+
                        |
                        v
               Merge + deduplicate
              RRF / score fusion
                        |
                        v
              Candidate list top M
                        |
                        v
           Optional semantic reranker
              (query + each text)
                        |
                        v
             Business / safety rules
             tenant, ACL, status, time
                        |
                        v
              Top K with snippets
                (e.g. top 5/10)
~~~

**Cẩn trọng với sơ đồ:** ACL/tenant filtering **phải được áp dụng ngay trong từng nhánh truy hồi**, không chỉ ở cuối. Nhánh cuối chỉ là lớp **kiểm tra lại/định dạng**; nếu filter sau khi chỉ chọn top M, kết quả được phép có thể đã bị loại khỏi candidate pool. Thêm nữa, không gửi tài liệu trái quyền truy cập của người dùng tới reranker hoặc external model.

### 1.1. Các giai đoạn có mục tiêu khác nhau

| Giai đoạn | Đầu vào | Đầu ra | Câu hỏi |
|---|---|---|---|
| Lexical retrieval | Query text + inverted index | Top L tài liệu theo token/relevance | Có đúng thuật ngữ, tên, mã không? |
| Vector retrieval | Embedding(query) + vector index | Top V neighbors | Ý nghĩa gần câu hỏi đến mức nào? |
| Fusion | Hai hoặc nhiều ranked lists | Danh sách duy nhất và điểm kết hợp | Document nào có tín hiệu tốt trên nhiều nguồn? |
| Rerank | Query + top M document texts | Thứ tự mới trên chính M documents | Document nào giải quyết ý định cụ thể tốt nhất? |
| Final presentation | Top K + metadata | Tiêu đề, snippet, đường dẫn, provenance | Người dùng có dùng/kiểm tra kết quả được không? |

Các chữ L, V, M, K là **candidate budgets**, không phải con số bắt buộc. Một cấu hình thử nghiệm có thể lấy 40 lexical + 40 vector → hợp nhất tối đa 80 unique docs → rerank 20–40 → trả 10. Cấu hình thực tế cần đo theo chất lượng và latency.

### 1.2. Ba câu hỏi đặt trước khi viết code

1. **Dữ liệu nào phải được tìm?** Một collection tài liệu hay nhiều nguồn; nguyên tài liệu hay chia thành chunks; đa tenant hay công khai?
2. **Query nào là quan trọng nhất?** Tên API/mã lỗi, ngôn ngữ tự nhiên, tiếng Việt/Anh, lọc thời gian/phiên bản, câu hỏi đòi chính xác?
3. **Mức bảo đảm là gì?** Tìm nhanh, không rò rỉ ACL, trả nguồn đáng tin, có cần freshness và định dạng đoạn trích, ngân sách model inference?

Hybrid search tốt là một **hệ thống retrieval end-to-end**, không chỉ thêm một operator vào pipeline.

## 2. Keyword search: tín hiệu từ vựng không thể bỏ

Tìm kiếm từ khóa thường dùng hệ thống inverted index của **MongoDB Search** qua stage `$search`. Hệ thống phân tích các terms, có thể xử lý stemming/language analyzer, synonyms, fuzzy matching, phrase, wildcard, autocomplete và scoring theo cấu hình.

### 2.1. Khi lexical mạnh hơn vector

- **Mã lỗi:** `E11000`, `HTTP 429`, `ORA-00001`.
- **Tên chính xác:** `MongoBulkWriteException`, `TransactionOptions`, `$setOnInsert`.
- **Mã định danh:** SKU, mã căn hộ, tên model, ticket ID, mã điều khoản.
- **Từ phủ định/ký hiệu:** `NOT NULL`, `TLS 1.3`, `v8.0.10`.
- **Câu trích dẫn cần y nguyên** hoặc truy vấn phrase.

Một embedding model có thể biểu diễn `MongoDB 8.0` và `MongoDB 8.3` khá gần, dù khác biệt phiên bản quyết định lệnh `$scoreFusion` chạy được hay không. Lexical matching cho phép đặt trọng số cao lên chuỗi phiên bản chính xác.

### 2.2. Scoring BM25 và analyzer

MongoDB Search thường có relevance scoring dựa vào tín hiệu lexical như BM25; điểm chịu ảnh hưởng tần suất term, độ hiếm term trong corpus, độ dài field và cấu hình analyzer/boost. **BM25 không phải xác suất** và không cùng thang đo cố định với cosine similarity.

Ví dụ:

~~~text
Query: "duplicate key E11000"

Doc A title: "Xử lý lỗi duplicate key E11000"
Doc B title: "Giải thích chỉ mục duy nhất"
Doc C title: "Khái niệm index trong MongoDB"
~~~

Lexical có thể đẩy A lên cao vì khớp chuỗi chính xác; vector có thể đưa B lên vì ý nghĩa gần. Cả hai là tín hiệu có ích.

### 2.3. `$search` khác với `$text`

`$text` là cơ chế text index truyền thống của MongoDB với tính năng/hạn chế riêng. MongoDB Search (`$search`) dùng search index, query operators/analyzers và scoring riêng. Không hoán đổi syntax:

~~~javascript
// MongoDB Search:
{ $search: { index: "kb_text_v1", text: { query: "E11000", path: "body" } } }

// Truy vấn $text của regular text index, không tương đương:
{ $match: { $text: { $search: "E11000" } } }
~~~

Trong bài này, “keyword search” mặc định là **MongoDB Search** để tích hợp trực tiếp với `$rankFusion`/`$scoreFusion`. Có thể dùng lexical engine khác rồi fusion ở ứng dụng nếu kiến trúc yêu cầu.

## 3. Vector search: tín hiệu ngữ nghĩa dựa trên embeddings

Embedding model biến văn bản thành một vector số có nhiều chiều. Các văn bản gần nhau về ngữ nghĩa thường có vector gần nhau theo một similarity metric được chọn khi lập index.

Ví dụ, ba câu:

~~~text
Q: "khắc phục lỗi trùng dữ liệu lúc tạo user"
D1: "Cách xử lý duplicate key từ unique index"
D2: "Lập chỉ mục cho truy vấn theo ngày"
~~~

Embedding của Q có thể gần D1 dù từ vựng khác nhau. Tuy nhiên điều này **không đảm bảo** mọi mã phiên bản, tên method hoặc từ phủ định được phân biệt đúng.

### 3.1. Query embedding phải tương thích document embeddings

Một collection có thể lưu:

~~~javascript
{
  _id: "KB-001",
  title: "Xử lý duplicate key",
  body: "Nếu insert vi phạm unique index, server trả lỗi E11000...",
  embedding: [0.12, 0.48, -0.23, 0.09]
}
~~~

Bốn số chỉ là **vector đồ chơi để minh họa code**, không phải output của một embedding model được đánh giá chất lượng. Production thường dùng vector hàng trăm/hàng nghìn chiều; **query vector phải có đúng numDimensions** và được tạo bởi **cùng phiên bản model/preprocessing** với document vectors.

### 3.2. ANN và ENN

- **ANN (Approximate Nearest Neighbors):** dùng index/thuật toán gần đúng để giảm latency, có thể bỏ sót vài neighbors so với phép so chính xác.
- **ENN (Exact Nearest Neighbors):** tìm neighbors chính xác trên tập được xét, hữu ích làm ground truth cho kiểm tra ANN recall hoặc khi dữ liệu/filter đủ nhỏ.

Trong `$vectorSearch`, ANN thường dùng `numCandidates` và `limit`; tăng `numCandidates` có thể cải thiện recall nhưng tăng CPU/latency. ENN dùng `exact:true` và có các yêu cầu phiên bản riêng.

### 3.3. Similarity metric và score

Vector index có các metric như `cosine`, `dotProduct`, `euclidean`. Không tự coi mọi điểm vector bằng cosine similarity nguyên bản hay xác suất “document đúng 87%”. MongoDB có thể chuẩn hóa score từ metric theo cách riêng. Dùng score để **xếp hạng tương đối trong một nhánh**; khi kết hợp với lexical BM25 cần RRF hoặc score normalization phù hợp.

### 3.4. Vector search không tự hiểu business filters

Document rất gần về ngữ nghĩa có thể thuộc tenant khác, bị thu hồi, đã hết hiệu lực hoặc sai product version. **Embedding không mã hóa đầy đủ quyền truy cập hay policy**. Phải gắn metadata với dữ liệu và áp dụng **filter trước khi chọn nearest neighbors**.

## 4. Bộ dữ liệu thực hành: knowledge base nhiều tenant

Giả sử ứng dụng tìm trong collection `search315_lab.kb_docs`. Mỗi document có `_id`, `title`, `body`, `tenantId`, `visibility`, `status`, `sourceUrl` và `embedding`. Một ví dụ:

~~~javascript
{
  _id: "DOC-001",
  tenantId: "tenant-a",
  visibility: "PUBLIC",
  status: "PUBLISHED",
  title: "Khắc phục lỗi duplicate key E11000",
  body: "MongoDB trả lỗi E11000 khi insert vi phạm unique index...",
  language: "vi",
  sourceUrl: "/kb/duplicate-key",
  updatedAt: ISODate("2026-10-10T00:00:00Z"),
  embeddingModel: "demo-4d-v1",
  embedding: [0.86, 0.32, 0.01, 0.07]
}
~~~

### 4.1. Tạo fixture nhỏ cho lab

~~~javascript
const lab = db.getSiblingDB("search315_lab")

lab.kb_docs.insertMany([
  {
    _id: "DOC-001", tenantId: "tenant-a",
    visibility: "PUBLIC", status: "PUBLISHED",
    title: "Khắc phục lỗi duplicate key E11000",
    body: "MongoDB trả lỗi E11000 khi insert trùng khóa của unique index. Cần kiểm tra dữ liệu và idempotency.",
    language: "vi", sourceUrl: "/kb/duplicate-key",
    updatedAt: ISODate("2026-10-10T00:00:00Z"),
    embeddingModel: "demo-4d-v1",
    embedding: [0.86, 0.32, 0.01, 0.07]
  },
  {
    _id: "DOC-002", tenantId: "tenant-a",
    visibility: "PUBLIC", status: "PUBLISHED",
    title: "Unique index và dữ liệu trùng",
    body: "Chỉ mục unique từ chối hai documents trùng giá trị. Xử lý duplicate key và null/missing.",
    language: "vi", sourceUrl: "/kb/unique-index",
    updatedAt: ISODate("2026-10-08T00:00:00Z"),
    embeddingModel: "demo-4d-v1",
    embedding: [0.78, 0.40, 0.03, 0.01]
  },
  {
    _id: "DOC-003", tenantId: "tenant-a",
    visibility: "PUBLIC", status: "PUBLISHED",
    title: "Cấu hình connection pool",
    body: "Điều chỉnh maxPoolSize, timeout và giám sát số lượng connections trong Java Driver.",
    language: "vi", sourceUrl: "/kb/pool",
    updatedAt: ISODate("2026-10-09T00:00:00Z"),
    embeddingModel: "demo-4d-v1",
    embedding: [0.02, 0.01, 0.95, 0.17]
  },
  {
    _id: "DOC-004", tenantId: "tenant-a",
    visibility: "PUBLIC", status: "PUBLISHED",
    title: "Sao lưu và phục hồi MongoDB",
    body: "Hướng dẫn backup, restore, kiểm chứng snapshot và chuẩn bị rollback.",
    language: "vi", sourceUrl: "/kb/backup",
    updatedAt: ISODate("2026-09-01T00:00:00Z"),
    embeddingModel: "demo-4d-v1",
    embedding: [0.05, 0.05, 0.25, 0.92]
  },
  {
    _id: "DOC-005", tenantId: "tenant-b",
    visibility: "PRIVATE", status: "PUBLISHED",
    title: "Đối soát khóa nội bộ của tenant B",
    body: "Thông tin vận hành riêng, không được hiển thị cho tenant khác.",
    language: "vi", sourceUrl: "/private/tenant-b/keys",
    updatedAt: ISODate("2026-11-01T00:00:00Z"),
    embeddingModel: "demo-4d-v1",
    embedding: [0.93, 0.26, 0.02, 0.03]
  },
  {
    _id: "DOC-006", tenantId: "tenant-a",
    visibility: "PUBLIC", status: "DRAFT",
    title: "Bản thảo xử lý E11000",
    body: "Tài liệu chưa được duyệt công khai về duplicate key.",
    language: "vi", sourceUrl: "/drafts/e11000",
    updatedAt: ISODate("2026-11-10T00:00:00Z"),
    embeddingModel: "demo-4d-v1",
    embedding: [0.91, 0.31, 0.00, 0.02]
  }
])
~~~

**Lưu ý lab:** Chạy script một lần trong database thực hành; chạy lại có duplicate `_id`. Các vectors **4 chiều là số minh họa**, không được sinh từ model thật, nên không lấy thứ tự kết quả tìm được để kết luận chất lượng semantic search. Trong production, sinh vectors cho **cùng model, cùng chiều** rồi mới xây index.

### 4.2. Metadata và quyền truy cập là một phần của retrieval

Query `"khóa trùng nội bộ"` có thể cho DOC-005 của tenant-b điểm vector rất cao và DOC-006 đang DRAFT điểm cao. **Phải lọc từ từng nhánh retrieval**; không dựa vào reranker để loại documents trái quyền. Một filter ví dụ:

~~~javascript
const auth = {
  tenantId: "tenant-a",
  visibility: "PUBLIC",
  status: "PUBLISHED"
}
~~~

Trong sản phẩm, `tenantId`/`visibility`/`roles` phải được xác định từ **server-side authorization context đáng tin**, không lấy nguyên giá trị do client tự nhập.

## 5. Tạo index cho keyword và vector

MongoDB Search và MongoDB Vector Search sử dụng **search indexes riêng**, khác regular B-tree index. `db.kb_docs.createIndex({embedding:1})` không tự tạo ANN index.

### 5.1. Search index cho từ khóa

~~~javascript
const lab = db.getSiblingDB("search315_lab")

lab.kb_docs.createSearchIndex("kb_text_v1", {
  mappings: {
    dynamic: false,
    fields: {
      title: { type: "string" },
      body: { type: "string" },
      tenantId: { type: "token" },
      visibility: { type: "token" },
      status: { type: "token" },
      language: { type: "token" }
    }
  }
})
~~~

Đây là **index mẫu** cho MongoDB Search với các trường chuỗi và exact-token filter ở phiên bản hỗ trợ kiểu `token`. Các analyzers, stemming, synonyms tiếng Việt/Anh, phân tách dấu câu và case folding cần cấu hình và đánh giá theo corpus. Không suy rằng một index `dynamic:true` sẽ tự tối ưu cho mọi query.

### 5.2. Vector Search index và các filter fields

~~~javascript
lab.kb_docs.createSearchIndex("kb_vec_v1", {
  type: "vectorSearch",
  fields: [
    {
      type: "vector",
      path: "embedding",
      numDimensions: 4,
      similarity: "cosine"
    },
    { type: "filter", path: "tenantId" },
    { type: "filter", path: "visibility" },
    { type: "filter", path: "status" },
    { type: "filter", path: "language" }
  ]
})
~~~

**numDimensions=4 chỉ dành cho lab.** Nếu production model sinh vector 768/1024/1536 chiều, index và query vector phải dùng chiều đó. Filter fields cần được index bằng `type:"filter"` trong **Vector Search index**, không chỉ trong keyword index. MongoDB Search `equals` và vector `filter` không có cùng syntax, dù cùng business condition.

### 5.3. Search indexes xây dựng bất đồng bộ

`createSearchIndex()` khởi động quá trình build; method trả về không đồng nghĩa index đã **READY**. Kiểm tra:

~~~javascript
lab.kb_docs.aggregate([
  { $listSearchIndexes: {} }
])
~~~

Rollout thực tế: tạo index tên `kb_vec_v2`, chờ hoàn tất, chạy benchmark/shadow queries, chuyển feature flag sang v2, giữ v1 để rollback một thời gian rồi mới xóa. Đừng cập nhật embedding model mà vẫn search lẫn các vectors được sinh từ model cũ và mới mà không có version partition.

### 5.4. Ai tạo query embeddings?

- **BYO embeddings:** ingest pipeline tính vector cho từng document bằng model v1, lưu vào `embedding`; query service cũng gọi **model v1** để tạo `queryVector`.
- **Managed/automated embedding:** có thể xuất hiện trên deployment tương thích; kiểm tra release/version, cost và quyền dữ liệu trước khi dùng.

Trong các ví dụ tiếp theo, `queryEmbedding` được **truyền từ bước embedding trước đó**. `$vectorSearch` không mặc định nhận một câu tiếng Việt và tự nhúng thành vector trên mọi MongoDB cluster.

## 6. Chạy hai truy vấn độc lập

Đừng ghép kết quả khi bạn chưa kiểm chứng **mỗi nhánh riêng**. Nếu vector chiều sai hoặc lexical index chưa index title, fusion không sửa được lỗi nguồn.

### 6.1. `$search`: keyword + boost title + filter

~~~javascript
const lab = db.getSiblingDB("search315_lab")
const q = "xử lý lỗi E11000"

const lexical = lab.kb_docs.aggregate([
  {
    $search: {
      index: "kb_text_v1",
      compound: {
        should: [
          {
            text: {
              query: q,
              path: "title",
              score: { boost: { value: 3 } }
            }
          },
          { text: { query: q, path: "body" } }
        ],
        minimumShouldMatch: 1,
        filter: [
          { equals: { path: "tenantId", value: "tenant-a" } },
          { equals: { path: "visibility", value: "PUBLIC" } },
          { equals: { path: "status", value: "PUBLISHED" } }
        ]
      }
    }
  },
  { $limit: 20 },
  {
    $project: {
      title: 1, body: 1, sourceUrl: 1,
      lexicalScore: { $meta: "searchScore" }
    }
  }
]).toArray()

printjson(lexical)
~~~

`compound.should` cho phép khớp title hoặc body, `minimumShouldMatch:1` yêu cầu ít nhất một clause. `score.boost` ở title có thể hợp lý với knowledge base, nhưng phải tune bằng judgment set. `$meta:"searchScore"` là lexical score của nhánh Search; nó **không cùng thang đo** với vector score.

### 6.2. `$vectorSearch`: ANN + pre-filter

~~~javascript
const queryEmbedding = [0.82, 0.39, 0.02, 0.03]

const semantic = lab.kb_docs.aggregate([
  {
    $vectorSearch: {
      index: "kb_vec_v1",
      path: "embedding",
      queryVector: queryEmbedding,
      numCandidates: 100,
      limit: 20,
      filter: {
        tenantId: "tenant-a",
        visibility: "PUBLIC",
        status: "PUBLISHED"
      }
    }
  },
  {
    $project: {
      title: 1, body: 1, sourceUrl: 1,
      vectorScore: { $meta: "vectorSearchScore" }
    }
  }
]).toArray()

printjson(semantic)
~~~

`numCandidates` của ANN là số hàng xóm được xem xét ở mức retrieval; `limit` là số kết quả nhánh trả ra. Chọn `numCandidates >= limit` và thường lớn hơn nhiều để cải thiện recall, đánh đổi latency. Cấu hình `100/20` chỉ là ví dụ, không phải tối ưu mặc định cho collection lớn.

### 6.3. ENN để đánh giá ANN recall

~~~javascript
// Trên deployment hỗ trợ exact vector search:
lab.kb_docs.aggregate([
  {
    $vectorSearch: {
      index: "kb_vec_v1",
      path: "embedding",
      queryVector: queryEmbedding,
      exact: true,
      limit: 20,
      filter: {
        tenantId: "tenant-a",
        visibility: "PUBLIC",
        status: "PUBLISHED"
      }
    }
  },
  { $project: { title: 1, vectorScore: { $meta: "vectorSearchScore" } } }
])
~~~

ENN có thể dùng làm tham chiếu top neighbors cho cùng query/filter. ANN nhanh hơn trên workload lớn nhưng cần đo **recall so với ENN**; không tự dùng ENN trên đường chạy có SLA thấp mà chưa benchmark.

### 6.4. Sai: post-filter sau khi ANN lấy top 20

~~~javascript
// KHÔNG NÊN: ANN xem tất cả tenants/trạng thái trước rồi mới lọc.
[
  {
    $vectorSearch: {
      index: "kb_vec_v1", path: "embedding",
      queryVector: queryEmbedding, numCandidates: 100, limit: 20
    }
  },
  { $match: { tenantId: "tenant-a", visibility: "PUBLIC" } }
]
~~~

Nếu 18/20 neighbors đầu thuộc tenant khác, việc lọc sau chỉ còn hai kết quả, dù những neighbors hợp lệ hạng 21–40 chưa được xét. Đó là **mất recall do post-filter**. Hơn nữa, không đưa nội dung trái quyền tới reranker/external model. **Áp dụng indexed filters ở cả hai nhánh trước khi fusion.**

## 7. Rank fusion: kết hợp danh sách bằng Reciprocal Rank Fusion (RRF)

Hai nhánh trả **hai thang điểm khác nhau**. Một tài liệu có `lexicalScore:12.4` và `vectorScore:0.82` không nghĩa tín hiệu lexical mạnh gấp 15 lần. Cộng thẳng raw scores có thể khiến lexical thắng chỉ vì thang đo.

**Reciprocal Rank Fusion (RRF)** giải quyết bằng cách dùng **thứ hạng trong từng danh sách**, không dùng điểm gốc:

\[
\mathrm{RRF}(d)=\sum_{i:\,d\in L_i}
\frac{w_i}{k+\operatorname{rank}_i(d)}
\]

Trong đó:

- \(d\): document cần xếp hạng.
- \(L_i\): danh sách kết quả từ retriever \(i\).
- \(\operatorname{rank}_i(d)\): thứ hạng **bắt đầu từ 1** trong danh sách \(i\).
- \(w_i\): trọng số của nhánh.
- \(k\): hằng số làm mượt; **MongoDB `$rankFusion` dùng k=60 và không cho chỉnh** theo API hiện hành.

### 7.1. Ví dụ tính tay

~~~text
Lexical:               Vector:
  1. DOC-A               1. DOC-B
  2. DOC-B               2. DOC-D
  3. DOC-C               3. DOC-A
~~~

Với trọng số mỗi nhánh bằng 1 và \(k=60\):

| Document | Lexical rank | Vector rank | Tổng RRF (xấp xỉ) |
|---|---:|---:|---:|
| DOC-A | 1 | 3 | \(1/61+1/63\approx0.03227\) |
| DOC-B | 2 | 1 | \(1/62+1/61\approx0.03252\) |
| DOC-C | 3 | Không có | \(1/63\approx0.01587\) |
| DOC-D | Không có | 2 | \(1/62\approx0.01613\) |

RRF ưu tiên B và A vì có tín hiệu ở **cả hai nhánh**, trong khi vẫn giữ DOC-C/DOC-D làm ứng viên. Một tài liệu chỉ xuất hiện trong một nhánh **không bị loại**.

### 7.2. Điểm mạnh và giới hạn

**Ưu điểm:** Không phải calibrate BM25 và cosine, ít phụ thuộc thang điểm của model/index, dễ giải thích bằng ranks, hợp nhất nhiều signals và dedupe.

**Giới hạn:** Rank 1 hơn rank 2 về score rất ít hoặc rất nhiều đều phản ánh bằng khoảng cách rank giống nhau. RRF không tự hiểu câu hỏi, không phát hiện document sai phiên bản hay lỗi authorization. Với query đòi mã chính xác, có thể tăng lexical weight hoặc đặt hard lexical filter khi cần.

### 7.3. RRF không phải semantic reranking

`$rankFusion` **không đọc hiểu lại title/body bằng mô hình ngữ nghĩa**. Nó dùng ranks do retrievers tạo ra. Một **cross-encoder reranker** xem xét **query và candidate text cùng lúc** để chấm độ phù hợp sâu hơn; đó là bước **sau fusion** và tốn thêm latency/cost.

### 7.4. Dedupe theo identity đúng

DOC-A có lexical rank 1 và vector rank 3 phải xuất hiện **một lần** với điểm gộp, không trả hai bản. Với tài liệu được chia thành chunks:

- Dedupe theo `chunkId` nếu ứng dụng trả các đoạn cho RAG.
- Dedupe/group theo `parentDocumentId` nếu giao diện cần một bài viết.
- Tránh gộp chunks khác nhau quá sớm vì chúng có thể trả lời các ý độc lập.

Chọn identity ảnh hưởng cả **Recall@K** (theo chunk hay parent).

### 7.5. Weighted RRF theo loại query

~~~text
Query: "E11000 MongoDB v8.0.10"
  lexical weight = 0.70
  semantic weight = 0.30

Query: "làm sao tránh dữ liệu trùng khi nhiều người cùng tạo user"
  lexical weight = 0.35
  semantic weight = 0.65
~~~

Các weights là **giả định minh họa**, phải tune bằng judgment set và A/B test. Một intent classifier nhận dạng error codes, versions, SKUs có thể giúp, nhưng bản thân classifier cũng có thể nhầm.

### 7.6. Candidate cut-off và recall

Nếu lexical và vector chỉ trả top 3, một tài liệu phù hợp đứng thứ 4 ở cả hai nhánh **không được fusion xét**. Tăng top-L/top-V lên 20/50 có thể cải thiện recall nhưng tăng runtime/reranking. **Final K=5 không có nghĩa mỗi nhánh cũng lấy đúng 5**.

## 8. MongoDB `$rankFusion`: hybrid trong một aggregation

Từ **MongoDB 8.0** trên deployment hỗ trợ các search stages, có thể kết hợp `$search` và `$vectorSearch` bằng `$rankFusion` ngay trong MongoDB. Stage này nhận các **sub-pipelines đặt tên**, thực thi độc lập trên **cùng collection**, de-duplicate rồi tính RRF.

### 8.1. Ví dụ đầy đủ keyword + vector + RRF

~~~javascript
const lab = db.getSiblingDB("search315_lab")
const q = "khắc phục lỗi E11000 khi đăng ký"
const queryEmbedding = [0.82, 0.39, 0.02, 0.03]

const hybridResults = lab.kb_docs.aggregate([
  {
    $rankFusion: {
      input: {
        pipelines: {
          lexical: [
            {
              $search: {
                index: "kb_text_v1",
                compound: {
                  should: [
                    {
                      text: {
                        query: q,
                        path: "title",
                        score: { boost: { value: 3 } }
                      }
                    },
                    { text: { query: q, path: "body" } }
                  ],
                  minimumShouldMatch: 1,
                  filter: [
                    { equals: { path: "tenantId", value: "tenant-a" } },
                    { equals: { path: "visibility", value: "PUBLIC" } },
                    { equals: { path: "status", value: "PUBLISHED" } }
                  ]
                }
              }
            },
            { $limit: 30 }
          ],
          semantic: [
            {
              $vectorSearch: {
                index: "kb_vec_v1",
                path: "embedding",
                queryVector: queryEmbedding,
                numCandidates: 200,
                limit: 30,
                filter: {
                  tenantId: "tenant-a",
                  visibility: "PUBLIC",
                  status: "PUBLISHED"
                }
              }
            }
          ]
        }
      },
      combination: {
        weights: {
          lexical: 0.45,
          semantic: 0.55
        }
      },
      scoreDetails: true
    }
  },
  {
    $project: {
      _id: 1, title: 1, body: 1, sourceUrl: 1,
      fusionScore: { $meta: "score" },
      fusionDetails: { $meta: "scoreDetails" }
    }
  },
  { $limit: 10 }
]).toArray()

printjson(hybridResults)
~~~

**Cách đọc:** lexical lấy tối đa 30, semantic lấy tối đa 30; MongoDB hợp nhất và dedupe, tính weighted RRF, rồi mới project/giới hạn top 10. Khi document xuất hiện ở cả hai branches, điểm góp từ cả hai. `scoreDetails:true` hữu ích để debug các thành phần score.

### 8.2. Vì sao `$project` nằm **sau** `$rankFusion`?

`$rankFusion` cần mỗi input pipeline trả **cùng document gốc không bị thay đổi** để đối chiếu/dedupe. Thêm `$project`/`$addFields` bên trong input pipeline không thuộc tập stage được hỗ trợ:

~~~javascript
// Sai: làm biến đổi document trong input pipeline.
{
  $rankFusion: {
    input: {
      pipelines: {
        lexical: [
          { $search: { /* ... */ } },
          { $project: { title: 1 } } // Không hỗ trợ ở đây.
        ]
      }
    }
  }
}
~~~

**Đặt projection sau fusion** rồi mới lấy `$meta:"score"`/`$meta:"scoreDetails"`. Các sub-pipelines chấp nhận tập stages giới hạn (như `$search`, `$vectorSearch`, `$match`, `$sort`, `$limit` theo version); không đặt `$facet` hay `$lookup` tùy ý bên trong.

### 8.3. Tên pipelines và weights

~~~javascript
input: {
  pipelines: {
    lexical: [/* ... */],
    semantic: [/* ... */]
  }
},
combination: {
  weights: {
    lexical: 0.45,
    semantic: 0.55
  }
}
~~~

`lexical` và `semantic` là **tên bạn tự đặt** và phải khớp với các keys trong `weights`. Không đặt tên trống, có dấu `.`, bắt đầu bằng `$` hoặc chứa ký tự cấm. Nếu một nhánh không được gán weight, default thường là 1, không mặc định tổng weights được normalize theo business intent.

### 8.4. `scoreDetails` không tự hiển thị

`scoreDetails:true` tạo **metadata**, chưa chắc tự xuất ra field trong document. Dùng:

~~~javascript
{ $project: {
    title: 1,
    fusionScore: { $meta: "score" },
    fusionDetails: { $meta: "scoreDetails" }
}}
~~~

Chi tiết cấu trúc metadata có thể thay đổi theo MongoDB version; không parse sâu `fusionDetails.details[0]` như business contract ổn định. Dùng `scoreDetails` để debug khi triển khai.

### 8.5. Các giới hạn thực tế

- `$rankFusion` chỉ kết hợp pipelines trên **một collection**; không tự JOIN documents từ nhiều collections.
- Input pipelines cần trả **document gốc**; projection sau fusion.
- Theo MongoDB Manual hiện hành, input pipelines chạy **tuần tự**, không song song; latency hybrid không nhất thiết bằng max(latency lexical, vector).
- Hỗ trợ **pagination** của fusion stage có giới hạn; đừng thiết kế deep paging bằng `skip`/`limit` lớn mà không xét tính ổn định thứ hạng và cost.
- Giới hạn candidate pool ảnh hưởng recall, CPU/memory và thời gian.
- Không trộn documents trái quyền rồi dùng `$match` sau fusion để lọc.
- Views, time-series collections và một số tính năng triển khai có hạn chế riêng theo version.

### 8.6. Query embedding được tính bên ngoài stage

`queryEmbedding` là array có sẵn. Production service phải gọi embedding model đúng version trước aggregation. Khi embedding service timeout, có thể degrade sang **lexical-only**, không gửi random/empty vector “để MongoDB tự tính”.

### 8.7. Gộp hơn hai nguồn

~~~text
lexical_title      - chính xác tên, mã
lexical_body       - body + synonyms
semantic_body      - embedding nội dung
semantic_title     - embedding tiêu đề
~~~

Thêm nhiều branches không luôn cải thiện search: title được boost trong lexical và thêm một nhánh title riêng có thể **đếm cùng tín hiệu hai lần**. Mỗi nhánh mới nên chứng minh có lợi ích trên tập đánh giá.

## 9. `$scoreFusion`: kết hợp các điểm số đã chuẩn hóa

**MongoDB 8.3+** bổ sung `$scoreFusion` để gộp các truy vấn theo **score**, không chỉ rank. Nếu `$rankFusion` bỏ qua khoảng cách giữa rank 1 và rank 2, `$scoreFusion` có thể sử dụng chênh lệch về độ phù hợp sau khi **normalize** hai nhánh.

### 9.1. Vì sao cần normalization?

Giả sử kết quả:

~~~text
Lexical BM25: 13.2, 8.5, 3.1
Vector score:  0.89, 0.82, 0.77
~~~

Cộng raw scores sẽ làm lexical chiếm ưu thế vì giá trị lớn hơn về mặt số học. Không có ý nghĩa toán học khi coi `13.2 + 0.89` là một xác suất. MongoDB `$scoreFusion` hỗ trợ các lựa chọn:

| Normalization | Ý tưởng | Lưu ý |
|---|---|---|
| `none` | Giữ nguyên raw score. | Chỉ dùng khi hai scores đã có cùng thang/đã được calibrate. |
| `sigmoid` | \(s'=1/(1+e^{-s})\). | Nén về (0,1), không phụ thuộc min/max của current candidate list; các điểm rất lớn có thể cùng tiến sát 1. |
| `minMaxScaler` | \(s'=(s-\min)/(\max-\min)\). | Phụ thuộc phân phối scores trong danh sách hiện tại; outlier có thể kéo khoảng giá trị. |

Không có normalization mặc định tốt nhất cho mọi corpus. Sau normalization, weights cho phép tăng/giảm đóng góp của keyword/vector. Khi result sets chỉ overlap một phần, cần hiểu cách hệ thống tính điểm tổng và trường hợp document thiếu một nhánh.

### 9.2. Ví dụ MongoDB 8.3+ dùng `$scoreFusion`

~~~javascript
const lab = db.getSiblingDB("search315_lab")
const q = "xử lý trùng khóa lúc đăng ký tài khoản"
const queryEmbedding = [0.82, 0.39, 0.02, 0.03]

lab.kb_docs.aggregate([
  {
    $scoreFusion: {
      input: {
        pipelines: {
          lexical: [
            {
              $search: {
                index: "kb_text_v1",
                compound: {
                  must: [
                    { text: { query: q, path: ["title", "body"] } }
                  ],
                  filter: [
                    { equals: { path: "tenantId", value: "tenant-a" } },
                    { equals: { path: "visibility", value: "PUBLIC" } },
                    { equals: { path: "status", value: "PUBLISHED" } }
                  ]
                }
              }
            },
            { $limit: 30 }
          ],
          semantic: [
            {
              $vectorSearch: {
                index: "kb_vec_v1",
                path: "embedding",
                queryVector: queryEmbedding,
                numCandidates: 200,
                limit: 30,
                filter: {
                  tenantId: "tenant-a",
                  visibility: "PUBLIC",
                  status: "PUBLISHED"
                }
              }
            }
          ]
        },
        normalization: "sigmoid"
      },
      combination: {
        method: "avg",
        weights: { lexical: 0.45, semantic: 0.55 }
      },
      scoreDetails: true
    }
  },
  {
    $project: {
      _id: 1, title: 1, sourceUrl: 1,
      score: { $meta: "score" },
      details: { $meta: "scoreDetails" }
    }
  },
  { $limit: 10 }
])
~~~

Ở đây, `normalization:"sigmoid"` áp dụng từng nhánh, `method:"avg"` kết hợp, `weights` điều khiển tỷ lệ. `scoreDetails:true` phục vụ quan sát. **Không đổi stage từ `$rankFusion` thành `$scoreFusion` mà giữ y nguyên syntax weights**: `$scoreFusion` đặt normalization trong `input`, còn combination có `method`/`weights` hoặc một expression.

### 9.3. Khi nào `$scoreFusion` tốt hơn RRF?

- Cần phân biệt document có score cao vượt trội so với các documents gần nhau trong **cùng retriever**.
- Đã xây calibration/normalization phù hợp giữa retrievers.
- Muốn thử thuật toán weighted score blending với judgment set có đủ mức relevance.
- Corpus và models ổn định, đã đo rằng score magnitudes mang thêm thông tin so với ranks.

Khi điểm từ các models không ổn định hoặc data phân bố khác nhau giữa queries, **RRF là baseline đơn giản, dễ bảo trì hơn**. Đừng giả định score fusion sẽ tốt hơn chỉ vì API mới hơn.

### 9.4. `$scoreFusion` không giải quyết thiếu candidate

Nếu tài liệu đúng không xuất hiện ở cả hai input pipelines, score fusion không thể tạo ra nó. Giới hạn topL/topV, ANN recall, index coverage và filter semantics vẫn quyết định **candidate recall** trước bước fusion.

### 9.5. Expression scoring nâng cao

`$scoreFusion` có thể dùng `combination.method:"expression"` để định nghĩa arithmetic expression riêng, tham chiếu normalized scores của các pipeline theo tên. Không dùng `weights` đồng thời với `expression` nếu syntax quy định mutual exclusion. Cách này hữu ích để học-to-rank nhẹ, nhưng tăng độ khó debug và nguy cơ overfit query set.

Một nhóm triển khai nên bắt đầu bằng:

1. Lexical-only baseline.
2. Vector-only baseline.
3. RRF weights mặc định.
4. Weights theo query category.
5. `$scoreFusion` với các normalization choices.
6. Reranker trên top-M.

Mỗi thay đổi cần đánh giá quality/latency/cost, không so sánh bằng những điểm raw không cùng thang.

## 10. Reranking: xem xét lại top-M tài liệu

**Reranker** là một mô hình chấm mức liên quan giữa **câu hỏi và từng tài liệu/đoạn** đã được truy hồi. Một **cross-encoder** có thể đọc cặp `(query,text)` cùng lúc, nhận biết từ phủ định, ý định sửa lỗi, quy tắc phiên bản hay ngữ cảnh tốt hơn một phép nearest-neighbor trong embedding space.

~~~text
Lexical top 40 + Vector top 40
             |
             v
    RRF union (tối đa 80)
             |
          Top M=25
             |
             v
  Reranker nhận 25 cặp (query, candidate)
             |
             v
   Sắp thứ tự lại 25 docs đó
             |
          Top K=10
~~~

Reranker **không tìm mới** những documents ở ngoài 25 candidates. Vì thế retrieval/fusion cần **candidate recall tốt**, còn reranker tập trung **precision/quality top positions**.

### 10.1. Reranking có thể cải thiện điểm gì?

| Tình huống | Reranking có thể giúp |
|---|---|
| Query hỏi “cách sửa”, tài liệu chỉ giải thích định nghĩa | Đẩy hướng dẫn khắc phục lên trên trang giới thiệu chung. |
| Query yêu cầu phiên bản 8.3 | Phân biệt đoạn nói `8.3` với `8.0` nếu model/corpus đủ rõ. |
| Câu có phủ định “không dùng transaction” | Ưu tiên tài liệu nói về ngoại lệ/thay thế, không chỉ nhắc transaction. |
| Một tài liệu dài chỉ chứa đúng một câu liên quan | Có thể chọn chunk/đoạn phù hợp hơn trong top candidates. |
| Nhiều tài liệu cùng từ khóa | Đọc ngữ cảnh để phân biệt use cases. |

**Giới hạn:** Reranker vẫn có thể sai, đặc biệt với identifiers hiếm, chuỗi chính xác, tiếng Việt ít dữ liệu, thông tin stale hoặc tài liệu dài bị cắt. Nếu query đòi `MongoDB 8.0.10`, vẫn cần **version filters / exact lexical signals**, không phó mặc cho model.

### 10.2. Reranker khác “LLM trả lời câu hỏi”

Reranker thường trả **relevance score hoặc thứ tự** cho mỗi candidate, chứ không tổng hợp câu trả lời. Trong RAG pipeline:

~~~text
Retrieval / Fusion -> Rerank -> Evidence top K -> Answer LLM -> Citations
~~~

Không nhầm câu trả lời trôi chảy của LLM với retrieval chất lượng cao. Nếu tài liệu sai lọt top-K, LLM vẫn có thể viết câu sai rất thuyết phục. Đánh giá retrieval/reranking **riêng** trước khi đánh giá câu trả lời cuối.

### 10.3. Native `$rerank` trong MongoDB khi đủ điều kiện

MongoDB có stage `$rerank` để xếp hạng lại theo mô hình Voyage AI. **Lưu ý version/availability:** trang `$rerank Aggregation Pipeline Stage` hiện hành (kiểm tra tháng 11/2026) nêu cluster **MongoDB 9.0+**, bật **Native Reranking** trong Atlas Project Settings, và **không dùng cho self-managed/Atlas Local**; một số model cần dedicated tier. Các trang overview cũ/được cập nhật khác thời điểm có thể nêu mốc 8.3; khi triển khai, dùng **trang Requirements dành riêng cho `$rerank` và cluster của bạn**, không lấy một mốc chung cho mọi tính năng hybrid.

Ví dụ nối ngay sau `$rankFusion` (trên cluster **đã bật rerank**):

~~~javascript
const q = "khắc phục lỗi E11000 khi đăng ký"

lab.kb_docs.aggregate([
  {
    $rankFusion: {
      input: {
        pipelines: {
          // Thay bằng hai sub-pipelines thực ở mục 8.1.
          lexical: [
            { $search: {
                index: "kb_text_v1",
                compound: {
                  must: [
                    { text: { query: q, path: ["title", "body"] } }
                  ],
                  filter: [
                    { equals: { path: "tenantId", value: "tenant-a" } },
                    { equals: { path: "visibility", value: "PUBLIC" } },
                    { equals: { path: "status", value: "PUBLISHED" } }
                  ]
                }
            }},
            { $limit: 30 }
          ],
          semantic: [
            { $vectorSearch: {
                index: "kb_vec_v1",
                path: "embedding",
                queryVector: [0.82, 0.39, 0.02, 0.03],
                numCandidates: 200,
                limit: 30,
                filter: {
                  tenantId: "tenant-a",
                  visibility: "PUBLIC",
                  status: "PUBLISHED"
                }
            }}
          ]
        }
      }
    }
  },
  { $addFields: { fusionScore: { $meta: "score" } } },
  {
    $rerank: {
      query: { text: q },
      path: ["title", "body"],
      numDocsToRerank: 20,
      model: "rerank-2.5-lite"
    }
  },
  { $addFields: { rerankScore: { $meta: "score" } } },
  { $project: {
      title: 1, body: 1, sourceUrl: 1,
      fusionScore: 1, rerankScore: 1
  }},
  { $limit: 10 }
])
~~~

**Phải phân biệt:** `$rerank` được đặt **sau fusion**, không nằm trong input pipeline của `$rankFusion`. `$rerank` thay `$meta:"score"` bằng điểm mới; nếu muốn giữ score trước rerank, **materialize vào field `fusionScore` trước** như mẫu. `numDocsToRerank` giới hạn số documents đầu vào được đánh giá; hãy đảm bảo pipeline trước đã tạo **thứ tự đáng tin**.

### 10.4. Điều kiện và chi phí của Native Reranking

Theo docs hiện hành:

- Bật tính năng Native Reranking trong dự án Atlas, được phép dùng model và chịu **usage-based cost**.
- `path` phải có trong tất cả input documents; nếu thiếu thì query có thể lỗi. Có thể filter loại docs thiếu field hoặc set giá trị fallback trước rerank.
- `numDocsToRerank` có giá trị tối đa theo docs (hiện là 1000), nhưng không nên gửi 1000 nếu chỉ cần top 10 và latency thấp.
- Có **giới hạn bộ nhớ per-request/per-node**; tài liệu troubleshooting đang nêu 30 MiB cho một request và 128 MiB tổng buffer trên node trong một số deployment.
- Một số models/tier/region bị giới hạn hoặc mới preview; phải đối chiếu quyền dữ liệu được xử lý bởi dịch vụ reranking.
- Trường `model`/models có thể đổi theo release; cần configuration flag và fallback.

### 10.5. Nếu cluster chưa có `$rerank`

Ứng dụng có thể lấy top M từ `$rankFusion` (8.0+) hoặc application RRF rồi **gọi external cross-encoder/reranking service** trên danh sách candidates:

~~~text
MongoDB -> top 25 allowed documents
   |
   v
Application strips PII/unneeded fields
   |
   v
Reranker API: query + [candidateId, text]
   |
   v
Sorted scores -> application applies final ACL/status check
   |
   v
Return top 10
~~~

Ưu điểm là model/tuning/caching linh hoạt. Đổi lại phải xử lý **latency, chi phí, mạng, timeout, rate limit, privacy, provenance**. Không gửi tài liệu nhạy cảm cho provider chưa được cho phép.

### 10.6. Khi nào bỏ qua reranking?

- Query chỉ có **một mã chính xác** và lexical/exact match đủ tốt.
- SLA p95 rất thấp, network/model inference không phù hợp.
- Số candidate ít, corpus rất đồng nhất.
- Reranker chưa có model phù hợp ngôn ngữ/domain.
- Chi phí rerank cao hơn phần relevance gain đo được.

Một pipeline có **hybrid fusion nhưng không reranker** vẫn là hybrid search hợp lệ. Reranking là bước **tùy chọn theo KPI**, không phải bắt buộc chỉ vì có vector.

## 11. Khi chưa có `$rankFusion`: hợp nhất ở tầng ứng dụng

Nếu deployment hỗ trợ MongoDB Search/Vector Search nhưng server chưa hỗ trợ `$rankFusion`, ứng dụng có thể chạy **hai queries** độc lập, nhận hai ranked lists, hợp nhất bằng RRF. Cách này cũng hợp lý khi muốn kết hợp kết quả từ **nhiều collections** hoặc một external search service, miễn có identity/dedupe/ACL rõ ràng.

### 11.1. Hàm RRF thuần JavaScript

~~~javascript
// Node.js/service code, KHÔNG phải mongosh pipeline.
function reciprocalRankFusion(
  pipelines,
  weights = { lexical: 0.5, semantic: 0.5 },
  k = 60
) {
  const rows = new Map()

  for (const [name, docs] of Object.entries(pipelines)) {
    const weight = weights[name] ?? 1
    if (!Number.isFinite(weight) || weight < 0) {
      throw new Error("Invalid weight: " + name)
    }

    docs.forEach((doc, index) => {
      // Stable identity; production cần bao cả tenant/source nếu ID không global.
      const id = String(doc._id)
      const current = rows.get(id) ?? {
        ...doc,
        rrfScore: 0,
        contributions: []
      }

      const rank = index + 1 // Ranks bắt đầu tại 1.
      const contribution = weight / (k + rank)
      current.rrfScore += contribution
      current.contributions.push({
        pipeline: name,
        rank,
        contribution
      })
      rows.set(id, current)
    })
  }

  return [...rows.values()].sort((a, b) =>
    b.rrfScore - a.rrfScore ||
    String(a._id).localeCompare(String(b._id))
  )
}

const lexicalResults = [
  { _id: "DOC-A", title: "Bài A" },
  { _id: "DOC-B", title: "Bài B" },
  { _id: "DOC-C", title: "Bài C" }
]

const vectorResults = [
  { _id: "DOC-B", title: "Bài B" },
  { _id: "DOC-D", title: "Bài D" },
  { _id: "DOC-A", title: "Bài A" }
]

const ranked = reciprocalRankFusion(
  { lexical: lexicalResults, semantic: vectorResults },
  { lexical: 1, semantic: 1 },
  60
)
console.table(ranked.map(d => ({
  id: d._id, rrf: d.rrfScore
})))
~~~

Kết quả kỳ vọng về **thứ tự theo điểm** là B, A, D, C như bảng mục 7.1. Đây là code để **minh họa thuật toán**, không phải thư viện xử lý mọi error/failure. Với raw results lớn, chuẩn hóa `_id` kiểu ObjectId/UUID nhất quán và không tin title/body từ hai nguồn không đồng nhất nếu chúng có revision khác nhau.

### 11.2. Bảo vệ trường hợp xuất hiện trùng trong một nhánh

Một retriever bình thường nên trả mỗi document một lần. Nếu adapter vô tình trả một `_id` lặp hai lần **trong cùng pipeline**, hàm đơn giản phía trên có thể cộng contribution hai lần. Production code nên **dedupe trong từng branch trước khi tính rank** (giữ thứ hạng xuất hiện đầu tiên), sau đó mới hợp nhất các branches.

Ngoài ra, khi cùng một bài được chunk thành nhiều tài liệu, việc xác định rank theo `chunkId` hay `parentDocId` phải thống nhất với mục tiêu trả lời.

### 11.3. Bảo vệ query shape trước khi chạy song song

Với app-side fusion, có thể thực hiện hai requests bằng `Promise.all`:

~~~javascript
// Pseudocode: lexicalQuery() và vectorQuery() là các hàm đã xây.
const [lexicalRows, vectorRows] = await Promise.all([
  lexicalQuery({ q, tenantId, visibility: "PUBLIC", status: "PUBLISHED" }),
  vectorQuery({ queryEmbedding, tenantId, visibility: "PUBLIC", status: "PUBLISHED" })
])

const top = reciprocalRankFusion(
  { lexical: lexicalRows, semantic: vectorRows },
  { lexical: 0.5, semantic: 0.5 }
).slice(0, 10)
~~~

Nếu queries chạy trên **khác collection hoặc index revision**, hai nhánh có thể thấy những phiên bản document khác nhau. Cần versioning, consistent ACL filters và stable IDs khi reconcile. Nếu một branch lỗi, áp dụng fallback policy có log/metrics rõ ràng, không âm thầm trả empty success không dấu vết.

### 11.4. Khi nào app-side fusion tốt hơn database-side?

| Khía cạnh | `$rankFusion` trong MongoDB | RRF trong ứng dụng |
|---|---|---|
| Server version | Cần MongoDB 8.0+. | Có thể dùng với deployment chỉ có hai retrievers riêng. |
| Số collections | Một collection trong stage. | Có thể gộp nhiều sources khi IDs/ACL có thiết kế. |
| Network | Một aggregate request. | Thường hai requests + dữ liệu candidate trả về. |
| Concurrency | Stage inputs theo docs có thể chạy tuần tự. | Ứng dụng có thể song song, tùy resource/connections. |
| Tuning | Built-in weighted RRF, scoreDetails. | Tự kiểm soát k, tie-break, dedupe, fallback. |
| Complexity | Ít code fusion. | Phải giữ logic/test/monitoring riêng. |
| Security | Từng sub-pipeline vẫn phải pre-filter. | Từng query và outbound data đều phải kiểm soát. |

Chọn giải pháp theo **deployment constraints, latency, reliability và chi phí vận hành**, không mặc định một hướng luôn nhanh hơn hướng kia.

### 11.5. Không hòa trộn raw scores tùy tiện trong app

~~~javascript
// Không nên làm khi lexicalScore và vectorScore chưa cùng thang:
combined = 0.5 * lexicalScore + 0.5 * vectorScore
~~~

Nếu chọn score fusion ở ứng dụng, hãy xác định normalization (per-query min-max/sigmoid hoặc calibration từ training set), xử lý missing-score documents, tie-breaks và đánh giá độ ổn định khi model/index thay đổi. App-side RRF thường là baseline tốt hơn để bắt đầu.

## 12. Java Sync Driver: xây pipeline hybrid bằng `Document`

Java Sync Driver nhận MongoDB aggregation pipeline dưới dạng danh sách các `Bson` stages. Không bắt buộc phải dùng Java wrapper chuyên dụng cho mọi stage mới: có thể dựng `org.bson.Document` để gửi đúng MongoDB query syntax, miễn driver/server hỗ trợ và đầu vào được kiểm tra.

### 12.1. Một phương thức tìm hybrid

Đoạn sau minh họa cấu trúc. Các `queryEmbedding` phải được tính bằng **cùng embedding model với dữ liệu đã index**; ứng dụng quản lý MongoClient, timeout và auth context bên ngoài.

~~~java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import org.bson.Document;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

public final class HybridKnowledgeSearch {

    private final MongoCollection<Document> docs;

    public HybridKnowledgeSearch(MongoDatabase db) {
        this.docs = db.getCollection("kb_docs");
    }

    public List<Document> search(
        String authorizedTenantId,
        String text,
        List<Double> queryEmbedding
    ) {
        // Validate nonblank text, tenant from authenticated context,
        // embedding dimensions/model version at service boundary.

        Document lexicalSearch = new Document(
            "$search",
            new Document("index", "kb_text_v1")
                .append("compound",
                    new Document("must", List.of(
                        new Document("text",
                            new Document("query", text)
                                .append("path", List.of("title", "body"))
                        )
                    ))
                    .append("filter", List.of(
                        new Document("equals",
                            new Document("path", "tenantId")
                                .append("value", authorizedTenantId)),
                        new Document("equals",
                            new Document("path", "visibility")
                                .append("value", "PUBLIC")),
                        new Document("equals",
                            new Document("path", "status")
                                .append("value", "PUBLISHED"))
                    ))
                )
        );

        Document vectorSearch = new Document(
            "$vectorSearch",
            new Document("index", "kb_vec_v1")
                .append("path", "embedding")
                .append("queryVector", queryEmbedding)
                .append("numCandidates", 200)
                .append("limit", 30)
                .append("filter",
                    new Document("tenantId", authorizedTenantId)
                        .append("visibility", "PUBLIC")
                        .append("status", "PUBLISHED"))
        );

        Document fusion = new Document(
            "$rankFusion",
            new Document("input",
                new Document("pipelines",
                    new Document("lexical",
                        List.of(lexicalSearch, new Document("$limit", 30)))
                        .append("semantic", List.of(vectorSearch))
                ))
                .append("combination",
                    new Document("weights",
                        new Document("lexical", 0.45)
                            .append("semantic", 0.55)))
                .append("scoreDetails", true)
        );

        Document projection = new Document(
            "$project",
            new Document("_id", 1)
                .append("title", 1)
                .append("body", 1)
                .append("sourceUrl", 1)
                .append("score", new Document("$meta", "score"))
        );

        List<Document> stages = Arrays.asList(
            fusion,
            projection,
            new Document("$limit", 10)
        );

        return docs.aggregate(stages)
            .into(new ArrayList<>());
    }
}
~~~

**Tiền điều kiện:** Cluster hỗ trợ `$rankFusion` (8.0+), indexes `kb_text_v1`/`kb_vec_v1` đã READY, `queryEmbedding` đúng 4 chiều cho lab và tất cả filter values hợp lệ. Driver mới có thể serialize một `Document` stage nhưng **server version cũ vẫn sẽ báo unsupported stage**.

### 12.2. Không ghép query text thành JSON tùy tiện

Đừng tạo query string bằng cách nối nguyên văn input người dùng vào JSON/JavaScript rồi parse. Dùng BSON constructors/builders và **parameter values** như ví dụ; validate max query length, vector values hữu hạn và dimension, tenant/role scope từ auth context. Nếu người dùng gõ `"$ne"` hoặc `{"$gt":0}`, nó phải là **text để search**, không được biến thành filter operator.

### 12.3. Timeout và fallback theo stage

Một service thực tế nên có:

~~~text
Generate query embedding
  |
  +-- success --> hybrid aggregate
  |                  |
  |                  +-- success --> optional rerank --> result
  |                  |
  |                  +-- timeout --> lexical-only fallback (if policy allows)
  |
  +-- timeout/fail --> lexical-only fallback
~~~

Cần log **degraded mode** và expose reliability metrics, không giấu mọi exception bằng `return List.of()`. Với query chứa mã lỗi, lexical-only có thể là fallback chấp nhận được; với câu hỏi dài diễn giải ý nghĩa, chất lượng sẽ giảm đáng kể nếu mất vector branch.

### 12.4. Tách responsibility trong Java

Nên tổ chức các interface:

- `EmbeddingProvider`: `embed(query,modelVersion)`.
- `LexicalRetriever`: `search(query,scope,limit)`.
- `VectorRetriever`: `search(vector,scope,limit)`.
- `FusionStrategy`: RRF/score fusion theo feature flags.
- `Reranker`: `rerank(query,candidates)` với deadline/budget.
- `SearchPolicy`: tenant ACL, status, version, permitted fields.
- `SearchEvaluation`: query logs, feedback, judgments.

Tách như vậy cho phép **A/B test** và fallback sang app-side fusion mà không đổi controller API.

## 13. Quyền truy cập, version và metadata filters trong hybrid search

**Relevance không được thắng authorization.** Một vector score 0.99 của document tenant khác vẫn phải bị loại. Đây là nguyên tắc không thương lượng của semantic search trên dữ liệu nhiều tenants.

### 13.1. Điểm kiểm soát ở từng nhánh

| Nhánh/bước | Điều kiện bắt buộc |
|---|---|
| `$search.compound.filter` | Tenant, visibility, status và ACL được index đúng kiểu. |
| `$vectorSearch.filter` | Tương đương business scope, fields khai báo kiểu filter trong vector index. |
| Fusion | Chỉ hợp nhất candidates đã được phép; không lấy tenant khác vào danh sách chung. |
| Reranker | Chỉ gửi allowed candidate texts, hạn chế PII và tokens. |
| Final output | Kiểm tra lại quyền/status/freshness khi cần và loại fields không được công bố. |
| Logs/analytics | Không ghi full private body hoặc query nhạy cảm ngoài policy. |

### 13.2. Why both branches?

Giả sử query semantic đưa DOC-005 private tenant-b vào top 1; lexical chỉ trả tài liệu tenant-a. Nếu chỉ lexical filter tenant thì **fusion có thể đưa DOC-005 lên đầu**, rồi reranker đọc nội dung riêng của tenant-b. Việc che kết quả cuối **không sửa được data exposure ở bước trung gian**.

### 13.3. Document version và trạng thái xuất bản

Knowledge base có thể chứa:

~~~javascript
{
  tenantId: "tenant-a",
  status: "PUBLISHED",
  product: "MongoDB",
  version: "8.0",
  effectiveFrom: ISODate("2026-01-01T00:00:00Z"),
  effectiveTo: null
}
~~~

Một câu hỏi `"MongoDB 8.0 hỗ trợ scoreFusion chưa?"` không được trả một trang 8.3 chỉ vì gần nghĩa. Có thể dùng exact/keyword match + metadata filter `version:"8.0"`, có chiến lược version range khi phù hợp, và đưa version/updatedAt vào final result để người dùng kiểm tra.

### 13.4. Filter theo khoảng thời gian và ACL thay đổi

Một tài liệu vừa bị chuyển từ PUBLIC sang PRIVATE có thể vẫn tồn tại trong search index một thời gian do **index propagation/index lag**. Search index không phải cơ chế authorization duy nhất: service nên kiểm tra permissions mạnh khi trả dữ liệu nhạy cảm, và có chính sách **revocation latency**. Với yêu cầu bí mật nghiêm ngặt, không gửi sensitive content tới reranker trước khi xác minh.

### 13.5. Filter nâng cao: lexical filter và vector filter không giống nhau

`$search.compound.filter` có các search operators như `equals`, `range`, `in`, v.v. Còn `$vectorSearch.filter` là bộ **pre-filter operators và field types được hỗ trợ** của Vector Search; không mặc nhiên có fuzzy/phrase trong filter của `$vectorSearch`.

Nếu cần **fuzzy text** làm **prefilter trước semantic vector search**, MongoDB còn có `vectorSearch` operator **bên trong `$search`** trên một số deployment/version, hỗ trợ filter theo MongoDB Search operators. Đừng nhầm:

~~~javascript
// Hai APIs khác nhau:
{ $vectorSearch: { /* aggregation stage */ } }

{ $search: {
    index: "some_search_index",
    vectorSearch: { /* Search operator */ }
} }
~~~

Chọn đúng index type, syntax và version theo docs; không copy vector stage parameters vào search operator rồi trông chờ chúng là một.

## 14. Chunking: kết hợp tài liệu dài mà không làm kết quả trùng lặp

Trong RAG/knowledge search, một tài liệu 15 trang chứa nhiều chủ đề. Embed toàn bộ thành một vector có thể làm nhòe câu trả lời chính; semantic search thường hiệu quả hơn trên **chunks** có độ dài vừa đủ.

### 14.1. Schema chunk

~~~javascript
{
  _id: "DOC-001#CHUNK-03",
  parentDocumentId: "DOC-001",
  chunkOrdinal: 3,
  tenantId: "tenant-a",
  visibility: "PUBLIC",
  status: "PUBLISHED",
  title: "Khắc phục lỗi duplicate key E11000",
  body: "Trường hợp upsert concurrent: dùng unique index và xử lý E11000...",
  section: "Xử lý concurrency",
  sourceUrl: "/kb/duplicate-key#concurrency",
  embeddingModel: "embed-v2",
  embedding: [/* vector thật, đúng số chiều */]
}
~~~

Ứng dụng tạo Search và Vector Search indexes trên **cùng chunks collection** khi dùng `$rankFusion`. Nếu một nhánh query `kb_docs` còn nhánh kia query `kb_chunks`, không thể đặt cả hai trực tiếp vào một `$rankFusion` vì hai sub-pipelines cần đọc **cùng collection**.

### 14.2. Chunk size và overlap

- Chunk quá ngắn: thiếu ngữ cảnh, mất định nghĩa ở đoạn kề, quá nhiều snippets.
- Chunk quá dài: embedding kém tập trung, reranker tốn tokens hoặc truncate.
- Overlap quá ít: câu trả lời đúng ở ranh giới hai chunks bị cắt.
- Overlap quá nhiều: nhiều chunks gần giống nhau chiếm toàn top-K, giảm **diversity**.

Độ dài chunk phải chọn bằng đánh giá trên dữ liệu thật. Ưu tiên chia theo **headings, đoạn văn, code fences, bảng và semantic boundaries** trong tài liệu kỹ thuật, rồi mới áp giới hạn token/overlap.

### 14.3. Phân biệt chunk-level và parent-level dedupe

~~~text
Lexical:
  DOC-001#CHUNK-03
  DOC-001#CHUNK-04

Vector:
  DOC-001#CHUNK-03
  DOC-002#CHUNK-01
~~~

Fusion theo `chunkId` cho DOC-001#CHUNK-03 đóng góp từ hai nguồn, còn DOC-001#CHUNK-04 là ứng viên khác. Nếu UI trả danh sách **bài viết**, có thể group theo `parentDocumentId` **sau** khi đã chọn các đoạn phù hợp, nhưng vẫn lưu vị trí chính xác để trích nguồn.

### 14.4. Parent fetch phải kiểm tra lại ACL

Sau khi truy hồi chunks, ứng dụng có thể lấy parent titles/metadata từ collection khác. Không tin rằng “chunk đã được phép ⇒ mọi trường parent đều được phép”: parent có thể đã đổi trạng thái PRIVATE, REVOKED, deleted hoặc thay revision. Kiểm tra quyền theo **server-side user context** ở thời điểm xuất kết quả.

### 14.5. Rerank với context vừa đủ

Reranker xem `query + text`. Nếu body quá dài, hãy gửi chunk liên quan, tiêu đề và section ngắn; giảm fields không cần thiết. Nếu cắt văn bản giữa câu, có thể mất chữ “không” hoặc mã phiên bản và làm đảo ngược ý nghĩa. Đo chất lượng với và không có truncation thay vì tự cho rằng phần đầu luôn quan trọng.

## 15. Query understanding: trọng số theo ý định

Query `"E11000"` khác `"tại sao insert trùng khóa khi hai người cùng gửi request"`. Một classifier/heuristic nhẹ có thể nhận diện:

- **Exact code/identifier:** error codes, class names, API paths, SKUs, version strings.
- **Natural-language question:** câu dài, đồng nghĩa, tiếng Việt diễn giải.
- **Navigation:** tìm tiêu đề/tài liệu đã biết.
- **Comparison:** “khác nhau giữa sparse và partial unique index”.
- **Multi-intent:** câu gồm nhiều câu hỏi cần nhiều evidence chunks.
- **Version/entity constraints:** MongoDB 7.0 so với 8.3, release notes, khu vực hoặc thời điểm có hiệu lực.

### 15.1. Ma trận chọn trọng số

| Loại query | Lexical | Vector | Rerank | Lưu ý |
|---|---|---|---|---|
| Mã lỗi `E11000` | Ưu tiên exact terms. | Bổ trợ giải thích. | Có thể bỏ nếu match đã chuẩn. | Giữ nguyên mã. |
| “Làm sao tránh dữ liệu trùng?” | Terms/synonyms. | Unique index/idempotency concepts. | Có ích để chọn hướng dẫn. | Không trả lời thiếu evidence. |
| Tên Java class | Ưu tiên exact/phrase. | Bổ trợ docs liên quan. | Tùy SLA. | Analyzer giữ dấu câu/case khi cần. |
| Query đa ngôn ngữ | Analyzer theo ngôn ngữ. | Multilingual embedding. | Multilingual reranker. | Đo Việt/Anh/có/không dấu. |
| “MongoDB 8.0 scoreFusion” | Exact version/name. | Ngữ cảnh khái niệm. | Có thể giúp. | Bắt buộc xác minh version. |
| “hướng dẫn mới nhất” | Terms + freshness filter. | Search theo chủ đề. | Chọn evidence. | Relevance khác freshness. |

### 15.2. Viết tắt, đồng nghĩa và dấu tiếng Việt

~~~text
TTL             <-> time-to-live
unique index    <-> chỉ mục duy nhất
duplicate key   <-> trùng khóa
retryable write <-> ghi có thể thử lại
~~~

Đây là nơi **synonyms/analyzers** của MongoDB Search giúp lexical, còn embedding hỗ trợ những cách diễn đạt dài hơn. Nhưng synonyms phải có domain context: cùng chữ viết tắt có thể mang nghĩa khác nhau ở các ngành. Mở rộng đồng nghĩa không kiểm soát có thể tăng false positives.

### 15.3. Phủ định và phiên bản

~~~text
"không cho phép update time-series"
"cho phép delete time-series từ 7.0"
~~~

Hai câu chia sẻ nhiều tokens nhưng **khác predicate**. Reranker có thể giúp phân biệt, nhưng cần kết hợp **metadata version/exact phrases/sections**. Không dùng heuristic intent làm thay thế hard business filter.

### 15.4. Multi-query expansion

~~~text
Q gốc: "cách xử lý lỗi trùng khi upsert"
Q1: "duplicate key E11000 upsert"
Q2: "MongoDB unique index concurrent upsert"
~~~

Chạy nhiều query variants có thể tăng recall nhưng tăng latency/cost, dễ **double-count** cùng evidence, và có nguy cơ thêm entity/version không có trong ý định. Với error codes/identifiers, không để paraphrase làm mất token quan trọng. Chỉ mở rộng khi baseline thực sự bỏ sót tài liệu do cách diễn đạt.

## 16. Đo chất lượng: retrieval tốt nghĩa là gì?

Không nên khẳng định pipeline “tốt hơn” chỉ vì thêm vector và reranker. Cần **bộ query test có nhãn relevance**, bao phủ các use cases thực tế, và metrics có thể so sánh giữa phiên bản.

### 16.1. Tạo judgment set

Mỗi query test có thể có:

~~~javascript
{
  queryId: "Q-001",
  query: "khắc phục lỗi E11000 khi upsert",
  tenantId: "tenant-a",
  language: "vi",
  intent: "troubleshooting",
  productVersion: "8.0",
  relevance: {
    "DOC-001#CHUNK-03": 3,
    "DOC-002#CHUNK-01": 2,
    "DOC-003#CHUNK-01": 0
  }
}
~~~

Chẳng hạn **0 = không liên quan**, **1 = hơi liên quan**, **2 = hữu ích**, **3 = trả lời trực tiếp**. Cần hướng dẫn labeling và reviewer độc lập khi có thể. Tập đánh giá phải gồm **queries không có đáp án**, truy vấn chứa phủ định, mã lỗi/phiên bản, tiếng Việt có dấu/không dấu và truy vấn nhạy cảm ACL.

### 16.2. Metrics quan trọng

| Metric | Ý nghĩa | Mục tiêu |
|---|---|---|
| **Recall@K** | Tỷ lệ relevant documents lọt top K trên tổng relevant docs đã biết. | Candidate coverage; đặc biệt trước rerank. |
| **Precision@K** | Tỷ lệ top K đủ ngưỡng relevance. | Độ sạch của kết quả đầu. |
| **MRR@K** | Mean reciprocal rank của kết quả relevant đầu tiên. | Tốt cho exact/navigation queries. |
| **nDCG@K** | Graded ranking quality, chiết khấu vị trí thấp. | Phù hợp nhãn relevance 0–3. |
| **Hit Rate@K** | Có ít nhất một relevant document trong top K. | RAG evidence retrieval. |
| **ANN Recall@K vs ENN** | Tỷ lệ nearest neighbors chính xác được ANN tìm lại. | Tune `numCandidates`. |
| **p95/p99 latency** | Độ trễ phần đuôi của query pipeline. | SLO của người dùng. |
| **Cost/query** | Embeddings, search/vector index, reranker calls. | Ngân sách và quy mô. |
| **Unauthorized exposure count** | Candidates/results trái ACL được xử lý ngoài scope. | Phải **bằng 0** theo policy. |
| **Freshness lag** | Chậm giữa cập nhật tài liệu/embedding/index và kết quả search. | Chính sách tài liệu mới/cũ. |

### 16.3. MRR và nDCG minh họa

Nếu hệ thống trả [DOC-X, DOC-B, DOC-A] và tài liệu relevant đầu tiên là DOC-B ở rank 2, **reciprocal rank của query** là \(1/2\). MRR là trung bình trên nhiều queries, **không** là relevance probability.

Với graded relevance \(rel_i\):

\[
\mathrm{DCG@K}=
\sum_{i=1}^{K}\frac{2^{rel_i}-1}{\log_2(i+1)}
\]

\(\mathrm{nDCG@K}=\mathrm{DCG@K}/\mathrm{IDCG@K}\), với IDCG là điểm lý tưởng khi documents được sắp theo relevance giảm dần. Cần định nghĩa cách xử lý queries không có positive judgment để không đưa denominator bằng 0 vào báo cáo.

### 16.4. Thử nghiệm từng thành phần

| Baseline | Retrieval | Fusion | Rerank |
|---|---|---|---|
| A | Keyword only | Không | Không |
| B | Vector only | Không | Không |
| C | Keyword + vector | RRF 0.5/0.5 | Không |
| D | Keyword + vector | RRF tuned | Không |
| E | Keyword + vector | `$scoreFusion` normalized | Không |
| F | Keyword + vector | RRF tuned | Rerank top 20 |

So sánh trên **cùng corpus/index/model state, query sets, ACL conditions và candidate budgets**. Nếu baseline A lấy top100 nhưng C mỗi nhánh chỉ top5, kết luận chất lượng sẽ lệch.

### 16.5. Tránh overfit và đánh giá theo nhóm

Tách **development set** để tune weights/chunk size/top M và **holdout test set** để đánh giá khách quan. Theo dõi:

- Exact identifiers vs natural language.
- Tiếng Việt có/không dấu và tiếng Anh.
- Tenant lớn/nhỏ, tài liệu công khai/riêng.
- Tài liệu mới/cũ, product versions.
- Query ngắn/dài, có phủ định, nhiều ý.
- Query có evidence và query không có answer.

Tối ưu nDCG trung bình nhưng làm nhóm `E11000` mất exact correctness có thể khiến sản phẩm tệ hơn dù score tổng tăng.

### 16.6. Online evaluation

Trong sản phẩm có thể A/B test CTR, time-to-answer, useful click, support ticket deflection và human ratings. Tuy nhiên **click-through rate có positional bias**, không chứng minh kết quả đúng. Kết hợp online metrics với relevance judgments và policy checks.

## 17. Tuning theo ba budget: truy hồi, fusion, rerank

Một pipeline có những tham số:

~~~text
Lexical candidate limit L = 40
Vector candidate limit V = 40
ANN numCandidates         = 400
Fusion output for rerank M = 30
Final results K           = 10
~~~

Đây là **cấu hình tham khảo để thử**, không phải giá trị tối ưu có sẵn. Thay đổi một tham số ảnh hưởng nhiều tầng.

### 17.1. Các tác động cơ bản

| Tham số tăng | Lợi ích có thể có | Chi phí/rủi ro |
|---|---|---|
| `numCandidates` | ANN recall tăng. | Tăng latency/compute. |
| Lexical top L | Thêm các exact-term docs ở rank sâu. | Tăng fusion set/memory. |
| Vector top V | Thêm semantic candidates. | Tăng ANN/fusion workload. |
| Fusion top M | Reranker có thêm cơ hội tìm đúng doc. | Tăng inference tokens/latency/cost. |
| Final top K | Người dùng nhìn nhiều evidence. | Nhiễu, UX khó, context window RAG phình. |
| Title boost | Nâng navigational/exact title match. | SEO/keyword-stuffed titles có thể vượt body hữu ích. |
| Semantic weight | Hữu ích cho synonyms/paraphrase. | Có thể làm sai version/code queries. |
| Lexical weight | Hữu ích cho IDs/mã/ngôn ngữ chính xác. | Có thể bỏ sót tài liệu liên quan bằng diễn đạt khác. |

### 17.2. Rerank chỉ có ích khi candidate recall đủ tốt

Nếu relevant doc không lọt top M sau fusion, reranker dù mạnh tới đâu cũng **không thể sửa**. Khi nDCG thấp, hãy phân biệt:

- **Retrieval miss:** tài liệu đúng không xuất hiện trong union top L/V.
- **Fusion miss:** có trong union nhưng bị xếp sau cutoff M.
- **Rerank miss:** có trong top M nhưng model đẩy xuống.
- **Presentation miss:** có trong top K nhưng snippet/link/version gây hiểu nhầm.

Phân loại lỗi này giúp biết nên sửa **index/analyzer/embedding**, **weights**, **reranker** hay **UI**.

### 17.3. Tính tổng latency thay vì nhìn riêng database

~~~text
T_total =
  T_query_normalization
  + T_embed_query
  + T_lexical/vector_retrieval_and_fusion
  + T_rerank
  + T_format
  + T_network
~~~

Đây là **mô hình cộng các công đoạn tuần tự** để lập ngân sách. Nếu app chạy lexical và vector **song song**, thời gian retrieval có thể gần giá trị lớn hơn giữa hai nhánh cộng overhead; nếu dùng MongoDB `$rankFusion` sub-pipelines theo docs hiện hành chạy **tuần tự**, không mặc định trừ được thời gian như gọi song song. Đo traces thật và tail latency.

### 17.4. Latency budget theo tầng

Ví dụ SLO giả định p95 dưới 300 ms:

| Công đoạn | Budget giả định |
|---|---:|
| Query pre-process + auth | 10 ms |
| Query embedding | 40 ms |
| Search/vector + fusion | 120 ms |
| Rerank | 100 ms |
| Format/network | 30 ms |

Tổng bằng 300 ms **chỉ là budget minh họa, không phải benchmark MongoDB/Voyage/model**. P95 của tổng không bằng tổng các p95 một cách máy móc; cần trace các requests end-to-end và đánh giá workload/concurrency thực.

### 17.5. Adaptive reranking

Có thể chọn rerank top M theo:

- **Query type:** câu hỏi dài/comparison rerank nhiều hơn exact ID.
- **Confidence:** lexical exact title match mạnh có thể bỏ rerank; nhưng phải đo precision.
- **SLA/tier:** background research cho phép rerank nhiều; autocomplete cần rất nhanh.
- **Cache hit:** query embedding/rerank result cache hợp lệ khi không trái ACL/version.

Khi adaptive policy làm thay đổi chất lượng theo nhóm người dùng, phải kiểm tra fairness/coverage và không dùng segmentation để bỏ qua ACL.

## 18. Vận hành production: index, model, chi phí và quan sát

Hybrid search là sự kết hợp của **database, search index, embedding model, reranker và quyền truy cập**. Một lần đổi model có thể làm thứ tự kết quả thay đổi dù query code MongoDB không hề đổi.

### 18.1. Embedding model version là dữ liệu, không chỉ config

Schema production nên lưu:

~~~javascript
{
  _id: "DOC-100#CHUNK-02",
  embeddingModel: "embed-model-v2",
  embeddingVersion: 2,
  embeddingDim: 768,
  embedding: [/* 768 numeric values */],
  sourceRevision: 17,
  indexedAt: ISODate("2026-11-14T00:00:00Z")
}
~~~

Với upgrade model v1 → v2:

1. Tạo fields/index v2 riêng (ví dụ `embeddingV2`, `kb_vec_v2`).
2. Backfill vectors bằng model v2, có checkpoint/idempotency.
3. Chờ index READY và xác minh vector dimensions/type.
4. Shadow query cả v1/v2, đánh giá Recall/nDCG/latency/cost.
5. Chuyển query embedding sang model v2 **đồng bộ** với v2 index.
6. Giữ rollback policy và chỉ xóa v1 khi đạt SLO.

**Không** mix query embedding v2 với document vectors v1 chỉ vì chúng có số chiều giống nhau; embedding spaces của hai models có thể khác hoàn toàn.

### 18.2. Freshness và index propagation

Khi `body` được sửa, text index, embedding field và search index có thể cập nhật không đồng bộ ở các điểm khác nhau. Một query có thể thấy lexical match theo revision mới nhưng vector semantic signal còn từ revision cũ.

Giải pháp:

- Ingest/update tài liệu theo **revision ID**.
- Regenerate embedding khi content thay đổi (hoặc theo field changed).
- Chỉ công bố `status:"PUBLISHED"` khi các điều kiện index/embedding phù hợp; hoặc chấp nhận và đo lag theo SLO.
- Có workflow reindex/retry/dead-letter cho lỗi embedding.
- Xác minh final document status/ACL khi cần.

Không cam kết “realtime search” chỉ dựa vào ACK của document update; kiểm tra **Search/Vector index synchronization semantics** của deployment.

### 18.3. Monitor theo từng stage

| Metric | Tại sao quan trọng |
|---|---|
| Lexical zero-result rate | Analyzer/keyword index/query mismatch hoặc dữ liệu thiếu. |
| Vector zero-result rate | Query embedding/filter/index lỗi, candidate pool quá nhỏ. |
| Two-branch overlap | Hai nhánh bổ trợ hay chỉ trùng nhiều? |
| Candidate unique count | Dedupe có làm mất đa dạng hay không? |
| ANN recall vs ENN | Tuning `numCandidates` và index config. |
| Rerank inversion rate | Reranker có đảo quá nhiều tài liệu tốt lên/xuống? |
| Query distribution by intent | Query có mã/tiếng Việt/chuyên ngành đang tăng? |
| P50/P95/P99 stage latency | Reranker hoặc embedding endpoint nào đang chậm? |
| Index build/status | Search indexes có READY và healthy? |
| Embedding error/timeout rate | Fallback thường xuyên hay không? |
| Returned stale/removed docs | Index lag, ACL revocation/freshness issue. |
| Tokens/cost per rerank | Budget usage theo top M/text length. |
| User feedback/relevance judgments | Chất lượng trải nghiệm thực. |

### 18.4. Logging có ranh giới bảo mật

Nên ghi:

~~~javascript
{
  requestId: "SRCH-1001",
  tenantIdHash: "redacted",
  queryClass: "technical_error_code",
  pipeline: "hybrid-rrf-rerank",
  lexicalCount: 30,
  vectorCount: 30,
  uniqueCandidates: 44,
  rerankedCount: 20,
  finalCount: 10,
  embeddingModel: "embed-v2",
  vectorIndex: "kb_vec_v2",
  latencyMs: {
    embedding: 32,
    fusion: 73,
    rerank: 98
  },
  degradedMode: false
}
~~~

Các con số là **giả định**. Không cần log nguyên `query` hoặc full private `body` nếu policy không cho phép. Nếu buộc lưu text cho quality review, cần opt-in/consent, retention, encryption, access control và xóa dữ liệu đúng chính sách.

### 18.5. Caching

Các cache có thể hữu ích:

- **Query embedding cache** theo normalized query, embedding model version, ngôn ngữ/normalization config.
- **Lexical/vector result cache** có key theo tenant/ACL scope, index revision, filters và query.
- **Rerank cache** theo model version, query, candidate IDs **và content revision**.

Không cache kết quả public rồi trả cho tenant khác chỉ vì query text giống nhau. Nếu quyền thay đổi/revocation, phải có invalidation hoặc TTL bảo đảm policy; với dữ liệu nhạy cảm, **không dùng cache làm authority**.

### 18.6. Quản lý dịch vụ reranking ngoài cluster

Nếu reranker gọi model service:

- Xác định **region/data residency** và thỏa thuận xử lý dữ liệu.
- Có timeout riêng, max concurrent requests, retry/backoff có giới hạn.
- Tránh gửi raw secrets/PII, cắt tài liệu theo policy.
- Có circuit breaker và fallback **fusion-only**.
- Cân nhắc replay/duplicate requests và chi phí per call.
- Theo dõi model version/model drift và chất lượng tiếng Việt.

Trong trường hợp Native Reranking, cũng phải xem provider/model và cơ chế xử lý dữ liệu do MongoDB/Atlas công bố, không suy rằng mọi model inference diễn ra trong cùng một replica set với application DB.

## 19. Kịch bản thiết kế: knowledge search cho trợ lý kỹ thuật

Giả sử hệ thống tìm tài liệu MongoDB cho developer, chia thành **public docs**, **internal team docs** và **tenant-specific docs**; mỗi doc có product version và timestamp.

### 19.1. Truy vấn mã lỗi

~~~text
Query: "E11000 duplicate key on upsert"

Lexical:
  title/body exact tokens -> có khả năng tìm tài liệu đúng mã

Vector:
  "unique index conflict in concurrent inserts"

Fusion:
  DOC giải thích E11000 + unique index có tín hiệu cả hai nhánh

Rerank:
  đưa đoạn xử lý upsert/retry lên hơn một trang lý thuyết chung
~~~

**Những constraints không được bỏ:** database/version, xử lý error code chính xác, document status và sourceUrl.

### 19.2. Truy vấn diễn giải ý nghĩa

~~~text
Query: "Vì sao thêm máy vào cluster mà tất cả ghi vẫn chậm?"

Lexical:
  tìm "sharding", "hotspot", "monotonic shard key"

Vector:
  có thể tìm các đoạn "new inserts target edge chunk"

RRF:
  kết hợp tài liệu chuyên môn và bài hướng dẫn thực hành

Rerank:
  ưu tiên giải thích root cause thay vì trang liệt kê tham số
~~~

Ở đây semantic search có thể đóng góp nhiều hơn vì query không dùng đúng cụm `"monotonic shard key"`. Nhưng không kết luận trọng số tối ưu nếu chưa có judgments.

### 19.3. Truy vấn phiên bản

~~~text
Query: "MongoDB 8.0 đã dùng $scoreFusion chưa?"

Rủi ro:
  một tài liệu MongoDB 8.3+ rất gần về ngữ nghĩa.

Cần:
  exact version metadata/lexical signal + source status.
  Kết quả phải làm rõ $scoreFusion yêu cầu 8.3+,
  không trả một ví dụ 8.3 như thể áp dụng được trên 8.0.
~~~

Nếu hệ thống chỉ dựa vào vector, dễ bỏ sót sự khác biệt mỏng về số phiên bản. Đây là use case tiêu biểu cần **hybrid + exact constraints**.

### 19.4. Một query đa tenant

~~~text
User tenant-a:
  "cấu hình billing secret E11000"

Private document tenant-b:
  semantic score 0.99

Public doc tenant-a:
  semantic score 0.83
~~~

**Kết quả đúng:** Private tenant-b không bao giờ được chọn làm candidate cho user tenant-a. Không được đưa nó vào reranker rồi che khi trả lời. Relevance và authorization là hai trục độc lập, trong đó **authorization có ưu tiên tuyệt đối**.

### 19.5. Query không có câu trả lời

Nếu người dùng hỏi một tính năng **chưa có** trong phiên bản đang chạy, các retrievers có thể vẫn trả một số tài liệu “gần gần”. Reranker chỉ **sắp xếp candidates**, không chứng minh câu hỏi được trả lời.

Cần **no-answer detection**/threshold policy được hiệu chỉnh theo judgments, UI “không tìm thấy tài liệu xác nhận”, và hiển thị nguồn/version. Không lấy `vectorScore>0.7` hoặc `RRF>0.03` làm bằng chứng có câu trả lời đúng mà chưa calibrate; scores không phải xác suất đúng.

## 20. Những lỗi thường gặp và hướng khắc phục

| Triệu chứng | Nguyên nhân khả dĩ | Hướng điều tra |
|---|---|---|
| `$rankFusion` báo unrecognized stage | Server chưa ≥ 8.0 hoặc deployment không hỗ trợ. | Xác minh server/FCV/topology và feature support. |
| `$scoreFusion` báo unrecognized stage | Chưa ≥ 8.3. | Dùng RRF/ứng dụng fallback. |
| `$rerank` không hoạt động | Server/feature toggle/tier/model không hỗ trợ. | Xem trang Requirements riêng, bật Native Reranking khi đủ điều kiện. |
| Vector query báo dimension mismatch | Query model/index field khác chiều. | Version hóa model/index, validate vector length. |
| Query trả tài liệu tenant khác | Missing pre-filter/ACL propagation. | Chặn ngay cả lexical và vector branches. |
| Hybrid trả rất ít kết quả sau lọc | Post-filter top candidates hoặc filter quá chặt. | Indexed pre-filter, điều chỉnh candidate limits. |
| Lexical score lớn hơn vector quá nhiều | Hai scales khác nhau. | Dùng RRF hoặc normalized `$scoreFusion`. |
| Rerank trả sai code/version | Model nhầm identifiers. | Exact lexical, hard version filters, evaluate segment. |
| Index vừa tạo nhưng search lỗi | Index chưa READY hoặc mapping sai. | `$listSearchIndexes`, status và path/field types. |
| Vector trả nội dung không liên quan | Model mismatch, chunking kém, ANN thấp. | Kiểm tra embedding versions, ENN, relevance judgments. |
| Reranker không cải thiện top-K | Candidate recall thấp hoặc model không hợp domain. | Kiểm tra retrieval/fusion trước, rerank diagnostics. |
| Top-K toàn chunks cùng một bài | Overlap/grouping chưa phù hợp. | Diversity, parent grouping, chunk size. |
| Tài liệu mới không được tìm | Embedding/index lag hoặc status filter. | Theo dõi reindex/backfill/READY. |
| P99 latency tăng mạnh | Too many candidates, rerank inference/network. | Stage traces, tune L/V/M, timeout/cache. |
| `$rankFusion` input có `$project` lỗi | Sub-pipeline chỉ nhận selection/ranking stages. | Chuyển projection ra sau fusion. |
| Hai sources khác collection không fusion được | `$rankFusion` chỉ một collection. | App-side RRF, read model chung hoặc strategy khác. |
| ScoreDetails không xuất hiện | Metadata chưa được project. | `{$meta:"scoreDetails"}` sau fusion. |
| Cache trả tài liệu revoked | Cache không theo quyền/revision. | Key theo ACL, invalidation, final auth validation. |
| Rerank thiếu field text | Path không tồn tại trên một số docs. | Đảm bảo schema hoặc filter/set fallback trước stage. |
| Vector-only trả sai mã `E11000` | Embedding gần nghĩa nhưng thiếu exact identifier. | Hybrid lexical và exact-match policy. |

### 20.1. Cách debug bằng trace một query

~~~text
Query: "E11000 retry"
Auth scope: tenant-a PUBLIC PUBLISHED

Lexical top 30:
  15 documents, 10 relevant

Vector top 30:
  30 documents, 12 relevant

Union:
  39 unique candidates, 17 relevant

Fusion top 20:
  14 relevant

Rerank top 10:
  8 relevant
~~~

Số liệu **giả định để minh họa phân tích lỗi**. Cần kiểm tra document IDs và relevance labels, không chỉ dựa vào số lượng matches. Một model có thể nâng precision nhưng làm mất một evidence bắt buộc; đánh giá nhiều KPI và các query segments.

### 20.2. Bốn loại lỗi khác nhau

1. **Retrieval miss:** tài liệu đúng không có trong union lexical/vector.
2. **Fusion miss:** tài liệu đúng có trong union nhưng rơi khỏi top M.
3. **Rerank miss:** có trong top M nhưng bị reranker đẩy xuống.
4. **Output/presentation miss:** top K đúng nhưng thiếu snippet, link, version hoặc sai authorization.

Hãy sửa **đúng tầng** thay vì luôn tăng `numCandidates` hoặc chuyển model lớn hơn.

## 21. Bài tập thực hành và đáp án

Mỗi bài độc lập, dùng dữ liệu/tình huống giả định và các điều kiện đã nêu. Khi ví dụ gọi MongoDB Search/Vector Search, phải có deployment và indexes phù hợp; tài liệu **không khẳng định đã chạy các lệnh** trên một cluster thực tế.

### Bài 1 — Vì sao chỉ dùng keyword có thể bỏ sót?

**Đề:** Người dùng tìm “cách tránh ghi trùng khi nhiều clients gọi đồng thời”. Tài liệu đúng có title “Unique index và idempotency”, không chứa từ “ghi trùng”. Keyword-only có nguy cơ gì?

**Đáp án:** Có thể bỏ sót do diễn đạt khác nhau. Vector search có thể phát hiện gần nghĩa; lexical với synonyms cũng có thể giúp. Hybrid tăng **candidate recall**, sau đó rerank chọn tài liệu chứa giải pháp cụ thể.

### Bài 2 — Khi nào keyword quan trọng hơn vector?

**Đề:** Query chỉ là `"E11000"`, còn một tài liệu khác nhắc `"E11001"`. Nên ưu tiên tín hiệu nào?

**Đáp án:** **Lexical/exact identifier** là tín hiệu bắt buộc để không nhầm mã. Vector có thể hỗ trợ ngữ nghĩa nhưng không thay exact constraints. Có thể tăng lexical weight hoặc lọc/boost exact code.

### Bài 3 — Cộng raw scores?

**Đề:** Lexical score 13.2, vector score 0.84. Có thể kết luận lexical mạnh hơn vector vì 13.2 lớn hơn 0.84 không?

**Đáp án:** Không. Hai retrievers có thang đo và scoring semantics khác. Dùng **RRF trên ranks** hoặc score fusion có normalization/calibration. Các điểm không phải xác suất.

### Bài 4 — ANN và ENN khác gì?

**Đề:** Một model trả vector 768 chiều, collection có 10 triệu documents. Tại sao thường chọn ANN trên đường truy vấn realtime và ENN để đánh giá?

**Đáp án:** ANN hy sinh một phần neighbor recall để giảm latency/compute; ENN dùng tìm chính xác (trong phạm vi filter), hữu ích làm baseline. Tune `numCandidates` dựa trên ANN recall vs ENN và latency.

### Bài 5 — Vector dimension mismatch

**Đề:** Index `numDimensions:1536` nhưng query vector chỉ có 768 numbers. Chuyện gì xảy ra và sửa thế nào?

**Đáp án:** Vector không khớp chiều, query không hợp lệ. Xác minh embedding model và index dimension; dùng cùng model/version ở ingest và query, hoặc tạo field/index mới cho model mới. Không pad bằng zeros tùy tiện để “chạy được”.

### Bài 6 — Hashed identifiers vs embeddings

**Đề:** Người dùng nhập mã sản phẩm `SKU-001`. Embedding trả rất gần SKU-002. Có nên dùng cosine score cao làm kết quả quyết định?

**Đáp án:** Không. Mã định danh cần exact lookup/lexical matching, có thể là hard filter hoặc query path riêng. Hybrid phải giữ **định danh chính xác**, không để semantic similarity thay unique identity.

### Bài 7 — RRF tính điểm

**Đề:** DOC-A đứng thứ 1 lexical và thứ 3 vector, weights đều 1, k=60. Tính RRF.

**Đáp án:** \(1/(60+1)+1/(60+3)=1/61+1/63\approx0.03227\). Đây là rank-based score, không là xác suất đúng.

### Bài 8 — RRF với missing branch

**Đề:** DOC-B chỉ có rank 2 ở vector, không có lexical hit. Nó có bị loại khỏi RRF không?

**Đáp án:** Không. DOC-B nhận \(w_{\text{vector}}/(60+2)\); lexical không góp điểm. Nếu DOC-B rất liên quan theo semantic search, nó vẫn có cơ hội ở danh sách chung.

### Bài 9 — Weighted RRF

**Đề:** Query `"MongoDB 8.0.10 E11000"` có hai trọng số lexical=0.8, semantic=0.2. DOC-A có lexical rank1, vector rank3. Điểm là gì?

**Đáp án:** \(0.8/61 + 0.2/63 \approx 0.01629\). Tăng lexical weight làm exact token đóng góp nhiều hơn, nhưng phải đo tác động lên các query dạng khác.

### Bài 10 — Candidate K không đủ

**Đề:** Tài liệu đúng đứng thứ 12 lexical, thứ 15 vector, còn mỗi nhánh chỉ trả top 10. Reranker có cứu được không?

**Đáp án:** Không, vì relevant doc **không vào candidate union**. Cần tăng lexical/vector limits, sửa index/analyzer/embedding hoặc query expansion trước; reranker chỉ sắp xếp các candidates đã nhận.

### Bài 11 — MongoDB 7.0 có `$rankFusion` không?

**Đề:** Cluster hỗ trợ `$search` và `$vectorSearch` nhưng server 7.0. Có thể dùng stage `$rankFusion` không?

**Đáp án:** Không theo điều kiện MongoDB Manual: `$rankFusion` yêu cầu **8.0+**. Có thể chạy hai retrieval queries rồi **RRF ở ứng dụng**, hoặc nâng cấp theo quy trình phù hợp.

### Bài 12 — MongoDB 8.0 có `$scoreFusion` không?

**Đề:** Cluster MongoDB 8.0 chạy `$rankFusion` tốt, muốn chuyển sang `$scoreFusion`. Có chạy ngay được không?

**Đáp án:** Không. `$scoreFusion` cần **MongoDB 8.3+**. Tiếp tục dùng RRF hoặc app-side normalized score fusion khi có kiểm soát, rồi đánh giá nâng cấp.

### Bài 13 — `$rerank` không nhận stage

**Đề:** Cluster Atlas chưa bật Native Reranking báo “unrecognized `$rerank`”. Bạn có nên đổi query thành `$scoreFusion` để có semantic reranking không?

**Đáp án:** Không tương đương. `$scoreFusion` là **score blending**, không có model rerank query-document. Kiểm tra requirements/tier/version/feature toggle của `$rerank`; nếu chưa đủ, dùng **external reranker** trên allowed top-M hoặc chỉ trả fusion results.

### Bài 14 — Dùng `$project` trong input pipeline của RRF

**Đề:** Một sub-pipeline:

~~~javascript
[
  { $search: { index: "kb_text_v1", text: { query: "E11000", path: "body" } } },
  { $project: { title: 1 } },
  { $limit: 20 }
]
~~~

Đặt nó bên trong `$rankFusion.input.pipelines.lexical` được không?

**Đáp án:** Không theo các stage restrictions hiện hành. `$project` làm thay đổi document trong input selection pipeline. Đặt `$project` **sau `$rankFusion`**.

### Bài 15 — Cần hiển thị `scoreDetails`

**Đề:** Đặt `scoreDetails:true` nhưng output không có trường scoreDetails. Lỗi ở đâu?

**Đáp án:** Stage tạo **metadata**, không nhất thiết tự hiển thị. Project/addFields sau fusion:

~~~javascript
{ $project: {
    title: 1,
    score: { $meta: "score" },
    details: { $meta: "scoreDetails" }
}}
~~~

### Bài 16 — Dedupe documents trên hai branches

**Đề:** DOC-1 đứng rank 1 lexical và rank 5 vector. API đang trả hai bản DOC-1. Sửa thế nào?

**Đáp án:** Dedupe theo stable document ID, **cộng contributions của cả hai ranks** vào một record. Không bỏ điểm semantic hoặc giữ hai records chỉ vì hai nhánh đã trả riêng.

### Bài 17 — Index vector thiếu filter field

**Đề:** Pipeline `$vectorSearch` có `filter:{tenantId:"T-A"}` nhưng Vector Search index chỉ index embedding, không index tenantId dạng filter. Cần làm gì?

**Đáp án:** Tạo/cập nhật **Vector Search index** với `{type:"filter",path:"tenantId"}` và các filter fields khác; chờ READY. Không nhầm với Search index đang có token field hoặc B-tree index.

### Bài 18 — Post-filter gây thiếu kết quả

**Đề:** ANN lấy top20 tất cả tenants, sau đó `$match` tenant-a chỉ còn 2 documents, trong khi tenant-a có nhiều tài liệu liên quan. Vì sao?

**Đáp án:** Candidate budget đã bị các tenants khác chiếm trước filter. Chuyển filter vào **`$vectorSearch.filter`** và lexical Search filter; giữ final ACL check để phòng index lag.

### Bài 19 — Rerank path bị thiếu

**Đề:** Một số documents không có `body`. `$rerank` dùng `path:"body"` và báo lỗi. Tại sao và giải quyết ra sao?

**Đáp án:** Reranker yêu cầu field được chỉ định tồn tại trong input documents. Có thể loại documents thiếu body bằng `$match` hoặc điền text fallback bằng `$set` trước rerank, nếu đúng policy. Đừng gửi null/objects vào trường model kỳ vọng là text và bỏ qua cảnh báo schema.

### Bài 20 — Rerank có thể xóa điểm fusion?

**Đề:** Sau `$rerank`, `{$meta:"score"}` hiển thị điểm reranker chứ không phải RRF. Muốn thấy cả hai?

**Đáp án:** Lưu score trước rerank vào field:

~~~javascript
{ $addFields: { fusionScore: { $meta: "score" } } },
{ $rerank: {
    query: { text: "E11000" },
    path: ["title", "body"],
    numDocsToRerank: 20,
    model: "rerank-2.5-lite"
}},
{ $addFields: { rerankScore: { $meta: "score" } } }
~~~

Yêu cầu MongoDB/feature toggle/model hỗ trợ. `fusionScore` được materialize trước khi rerank ghi đè metadata `score`.

### Bài 21 — Gửi tài liệu private sang external reranker

**Đề:** Service trộn DOC-005 tenant-b private vào candidate list, gọi external model rồi loại ở output. Có an toàn không?

**Đáp án:** **Không.** Dù user không nhìn thấy output, private content đã rời phạm vi được phép. Pre-filter trong cả hai branches, verify authorization và chỉ gửi allowed content sang provider được duyệt. Không lấy downstream filtering làm thay thế ACL.

### Bài 22 — Một document có nhiều chunks

**Đề:** UI cần hiển thị tối đa 5 **bài viết**, nhưng top5 hybrid có 4 chunks của cùng DOC-1. Bạn nên làm gì?

**Đáp án:** Cân nhắc **group theo parentDocumentId sau retrieval/rerank**, chọn representative chunk(s), đảm bảo diversity và giữ link đúng phần. Không bỏ mọi chunk cùng parent ngay trước fusion nếu mất evidence cần thiết; đánh giá theo parent-level relevance.

### Bài 23 — Rerank model có hỗ trợ tiếng Việt?

**Đề:** Hệ thống chủ yếu tiếng Việt, model rerank được tối ưu cho English. Có nên mặc định nó cải thiện top10 không?

**Đáp án:** Không. Tạo judgments tiếng Việt có/không dấu, từ viết tắt kỹ thuật và query đa ngôn ngữ; so sánh rerank vs RRF-only. Nếu không cải thiện hoặc latency quá cao, dùng model hỗ trợ multilingual hoặc tắt rerank cho nhóm query phù hợp.

### Bài 24 — Exact version query

**Đề:** User hỏi `"MongoDB 8.0 hỗ trợ scoreFusion chưa?"`. Vector trả trang hướng dẫn `$scoreFusion` 8.3. Làm sao ngăn câu trả lời sai?

**Đáp án:** Đưa **version metadata/exact lexical evidence** vào retrieval/rerank, kiểm tra tài liệu release requirements; `$scoreFusion` cần 8.3+, không phải 8.0. Không để semantic similarity lấn át constraint phiên bản.

### Bài 25 — Query không có kết quả đúng

**Đề:** Cả lexical và vector luôn trả một vài tài liệu gần nghĩa, dù hỏi một API không tồn tại. Có nên buộc LLM trả lời từ kết quả đó?

**Đáp án:** Không. Thiết kế **no-answer/insufficient-evidence policy** được hiệu chỉnh bằng judgments; hiển thị “chưa tìm thấy nguồn xác nhận” và tài liệu gần nghĩa kèm caveat. Raw `vectorScore`/RRF không phải xác suất answer đúng.

### Bài 26 — Chọn `numCandidates`

**Đề:** ANN recall thấp hơn ENN; `numCandidates:40` với `limit:20`. Nên thử gì?

**Đáp án:** Tăng numCandidates có kiểm soát, đo ANN Recall@20 và p95 latency; đồng thời kiểm tra filter selectivity, index health, embeddings và candidate limits. Không cho rằng tăng tới 1000 luôn tốt nếu latency/cost vượt SLO.

### Bài 27 — `$rankFusion` trên hai collections khác nhau

**Đề:** Keyword search trả từ `kb_articles`, vector search từ `kb_chunks`; muốn dùng một `$rankFusion` trực tiếp. Có được không?

**Đáp án:** Không, `$rankFusion` cần các pipelines cùng **một collection**. Có thể tạo normalized search collection/index chung, hoặc chạy hai retrieval requests rồi app-side RRF với mapping chunk↔parent và ACL tương thích.

### Bài 28 — Điểm số và hiệu suất

**Đề:** Trước reranking, p95 là 120 ms; thêm model rerank làm p95 lên 450 ms nhưng nDCG@10 chỉ tăng 0.2 điểm phần trăm. Nên làm gì?

**Đáp án:** Đánh giá lợi ích so với SLO/cost: giảm M, dùng model nhẹ, cache, selective reranking cho khó queries, hoặc tắt rerank. Không kết luận reranking phải luôn bật vì đây là bước “nâng cao”.

### Bài 29 — Cải thiện chất lượng sau model upgrade

**Đề:** Team đổi embedding model từ 768 sang 1024 chiều. Query code vẫn dùng index 768 và bắt đầu lỗi. Quy trình sửa?

**Đáp án:** Tạo **embedding field/index mới 1024 chiều**, backfill corpus và chờ READY, dùng query embedding từ đúng model mới, shadow evaluate, rollout bằng feature flag rồi giữ rollback. Không resize raw vector bằng pad/truncate cho vừa index.

### Bài 30 — `scoreFusion` và normalization

**Đề:** Hai nhánh có BM25 từ 2–50 và vector scores 0.7–0.9. Chọn `normalization:"none"` rồi average có rủi ro gì?

**Đáp án:** Lexical raw scores có thể thống trị vì thang lớn. Dùng `sigmoid`/`minMaxScaler` hoặc calibration phù hợp, đánh giá score distribution và relevance; RRF có thể là baseline dễ kiểm soát hơn.

### Bài 31 — Query chỉ theo exact ID

**Đề:** Một API có `GET /docs/DOC-001` nhưng developer dùng vector search query `"DOC-001"` để tìm đúng tài liệu. Có hợp lý không?

**Đáp án:** Không. Đây là **point lookup** theo primary ID, nên dùng `findOne({_id:"DOC-001"})` và authorization. Hybrid search dành cho discovery/relevance, không thay thế exact key lookup.

### Bài 32 — Input pipeline có stage không cho phép

**Đề:** Trong `$rankFusion.input.pipelines.lexical`, developer chèn `$lookup` để join owner table trước fusion. Vì sao có thể lỗi?

**Đáp án:** `$rankFusion` chỉ hỗ trợ tập selection/ranking stages giới hạn, không phải toàn bộ aggregation pipeline. Join/enrichment nên làm sau fusion hoặc trong application, với kiểm tra ACL/tenant và giới hạn top-K.

### Bài 33 — Index vừa tạo có thể query ngay?

**Đề:** `createSearchIndex` trả về index name; query tiếp theo báo index không sẵn sàng. Có phải createIndex thất bại?

**Đáp án:** Không nhất thiết. Search index build/index sync **bất đồng bộ**. Kiểm tra `$listSearchIndexes` trạng thái READY, path definitions và errors; không mở feature flag cho traffic trước khi index đã sẵn sàng.

### Bài 34 — Tính Recall@K

**Đề:** Bộ judgments xác định 5 documents relevant cho Q1. Hybrid top10 chứa đúng 4 documents đó. Recall@10 bằng bao nhiêu?

**Đáp án:** \(4/5=0.8\). Nếu top10 có 4 relevant trên 10 results, Precision@10 = \(4/10=0.4\). Hai metrics trả lời câu hỏi khác nhau: **bao phủ** và **độ sạch top results**.

### Bài 35 — MRR khi relevant đầu tiên đứng thứ 4

**Đề:** Với một query, relevant document đầu tiên đứng ở rank4. Reciprocal rank là bao nhiêu?

**Đáp án:** \(1/4=0.25\). **MRR** được tính bằng trung bình reciprocal rank trên **nhiều queries**, không chỉ Q1.

### Bài 36 — Cùng query, khác tenant

**Đề:** Tenant-a và tenant-b tìm cùng chuỗi `"E11000"`. Hệ thống cache chung kết quả chỉ theo query text. Rủi ro?

**Đáp án:** Cache có thể trả documents trái quyền hoặc sai corpus. Cache key phải tính **authorization scope, tenant, filters, index/model version và data revision**; với dữ liệu nhạy cảm, cần kiểm tra quyền lại trước trả output, không dùng cache làm authority.

### Bài 37 — Tài liệu stale nhưng score cao

**Đề:** Một bài MongoDB 6.0 được lexical/vector/rerank xếp đầu cho câu hỏi 8.3. Nên giải quyết bằng tăng topM không?

**Đáp án:** Không chỉ tăng topM. Thêm **productVersion/effectiveDate/status filters**, kiểm soát freshness/rerank evidence, và hiển thị provenance. Scores chỉ đo relevance tương đối, không xác nhận tài liệu áp dụng đúng release.

### Bài 38 — Hai signal giống nhau

**Đề:** Một pipeline có lexical title boost, một branch lexical riêng chỉ tìm title, và một branch semantic title embedding. nDCG không cải thiện. Nguyên nhân có thể?

**Đáp án:** Nhiều branches có thể đang **double-count** cùng tín hiệu title, làm body evidence kém cơ hội. Làm ablation từng branch, kiểm tra overlap và query segments, bỏ nguồn không tăng chất lượng thực.

### Bài 39 — Kết hợp lexical, vector và rerank cho RAG

**Đề:** Thiết kế pipeline trả 5 chunks có nguồn cho câu hỏi `"phân biệt updateOne và transaction khi giữ nhiều SKU"` trên một knowledge base nhiều tenant.

**Đáp án gợi ý:**

1. Lấy tenant/ACL từ auth context và query intent.
2. Tạo embedding query bằng model/index đúng version.
3. `$search` title/body lấy top40 với tenant/status/version filters.
4. `$vectorSearch` lấy top40 với **cùng** policy filter.
5. `$rankFusion` RRF (8.0+) hoặc app-side RRF trên stable chunk IDs.
6. Lấy top20–30 candidate chunks; semantic rerank nếu model/latency cho phép.
7. Group/diversify theo parent, giữ đoạn chứng cứ và `sourceUrl`.
8. Final ACL/authorization check và trả top5 chunks + provenance.
9. Đo Recall@40, nDCG@5, latency p95, no-answer quality và exposure=0.

### Bài 40 — Một kế hoạch rollout production

**Đề:** Team đã có keyword search ổn định, muốn thêm vector + reranker trong 2 lần phát hành. Hãy mô tả các bước sao cho đo được lợi ích và có rollback.

**Đáp án gợi ý:**

1. Tạo judgment set theo exact IDs, natural queries, tiếng Việt, versions và ACL.
2. Chọn embedding model, sinh vectors cho tài liệu/chunks, lưu model/version.
3. Tạo Vector Search index và filter fields, chờ READY, đo ANN recall vs ENN.
4. Shadow compare keyword-only vs vector-only vs RRF, không đổi user results ngay.
5. Phát hành hybrid fusion theo feature flag/canary, xem p95/p99 và error rate.
6. Đánh giá rerank trên topM đã được phép, privacy/cost, native feature support.
7. Bật rerank có chọn lọc, A/B test top-K relevance và SLO.
8. Giữ fallback lexical-only/fusion-only và khả năng quay về index/model cũ.
9. Monitor index freshness, embedding failures, ACL exposure, online feedback.
10. Không gọi rollout là thành công chỉ vì thấy score tăng; cần KPI chất lượng và độ tin cậy.

## 22. Tài liệu MongoDB chính thức và nguồn học tiếp

Khi làm việc với hybrid search, **cú pháp và giới hạn thay đổi theo MongoDB Server version, search deployment type, Atlas feature flags và model availability**. Các trang dưới đây là điểm tra cứu chính thức; hãy chọn branch tương thích với cluster đang chạy. Bài này mô tả tính năng tính đến tháng 11/2026, không thay thế kiểm chứng trên deployment thực tế.

### 22.1. Hybrid retrieval và fusion

1. [How to Perform Hybrid Search — MongoDB Vector Search](https://www.mongodb.com/docs/vector-search/hybrid-search/hybrid-search-overview/) — giải thích RRF, relative score fusion, weights và các giới hạn của hybrid sub-pipelines.
2. [`$rankFusion` (aggregation)](https://www.mongodb.com/docs/manual/reference/operator/aggregation/rankfusion/) — syntax `input.pipelines`, `combination.weights`, RRF \(k=60\), `scoreDetails` và các stage restrictions; MongoDB 8.0+.
3. [`$scoreFusion` (aggregation)](https://www.mongodb.com/docs/manual/reference/operator/aggregation/scorefusion/) — normalization `none`/`sigmoid`/`minMaxScaler`, weights/combination, score metadata; MongoDB 8.3+.
4. [Combine Multiple `$vectorSearch` Queries](https://www.mongodb.com/docs/vector-search/hybrid-search/vector-search-with-rankfusion/) — kết hợp nhiều vector pipelines, ví dụ weights và scoreDetails.
5. [`$score` Aggregation Stage](https://www.mongodb.com/docs/manual/reference/operator/aggregation/score/) — tính/normalize score trong một số trường hợp sử dụng `$scoreFusion` và các pipeline không tự có score.

### 22.2. Lexical Search và Vector Search

6. [MongoDB Search Overview](https://www.mongodb.com/docs/atlas/atlas-search/) — inverted-index search, analyzers, operators và scoring.
7. [`$search` Aggregation Stage](https://www.mongodb.com/docs/atlas/atlas-search/aggregation-stages/search/) — syntax Search stage.
8. [MongoDB Search `text` Operator](https://www.mongodb.com/docs/atlas/atlas-search/text/) — cách tìm văn bản, matching/analyzer và scoring.
9. [MongoDB Search `compound` Operator](https://www.mongodb.com/docs/atlas/atlas-search/compound/) — `must`/`should`/`filter` và boost.
10. [Run ANN and ENN Vector Search Queries](https://www.mongodb.com/docs/vector-search/query/aggregation-stages/vector-search-stage/) — `$vectorSearch`, `numCandidates`, `limit`, `exact`, `filter` và version requirements.
11. [`vectorSearch` MongoDB Search Operator](https://www.mongodb.com/docs/atlas/atlas-search/operators-collectors/vectorsearch/) — tìm vector bên trong `$search` với advanced Search prefilters.
12. [Create Search Indexes with `createSearchIndex`](https://www.mongodb.com/docs/manual/reference/method/db.collection.createsearchindex/) — Search index và vectorSearch index definitions.
13. [`updateSearchIndex`](https://www.mongodb.com/docs/manual/reference/method/db.collection.updatesearchindex/) — xây lại index, readiness và đổi definition.
14. [Improve Vector Search Accuracy](https://www.mongodb.com/docs/vector-search/query/improve-accuracy/) — ANN vs ENN, recall và reranking.

### 22.3. Reranking và vận hành

15. [`$rerank` Aggregation Pipeline Stage](https://www.mongodb.com/docs/vector-search/query/aggregation-stages/rerank/) — syntax, native models, deployment requirements, semantic rerank score và giới hạn.
16. [MongoDB Vector Search Troubleshooting](https://www.mongodb.com/docs/vector-search/troubleshooting/) — vector query errors, rerank memory limits và operational diagnostics.
17. [Atlas Project Settings — Native Reranking](https://www.mongodb.com/docs/atlas/tutorial/manage-project-settings/) — bật/tắt và kiểm soát Native Reranking trên Atlas.
18. [Java Sync Driver — MongoDB Search](https://www.mongodb.com/docs/drivers/java/sync/current/atlas-search/) — `Aggregate`/Search/Vector examples và API Java.
19. [`$listSearchIndexes`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/listSearchIndexes/) — kiểm tra index definitions/trạng thái Search indexes.
20. [MongoDB 8.2 Compatibility Changes](https://www.mongodb.com/docs/manual/release-notes/8.2-compatibility/) — thay đổi khi nâng cấp, ví dụ `$rankFusion` trên views.

**Lưu ý quan trọng khi tra cứu:** Một trang overview có thể nêu milestone availability chung khác với **trang Requirements của một stage mới** vì docs/model/tier thay đổi theo release. Với `$rerank`, luôn kiểm tra **trang stage-specific Requirements** và Atlas project model status trước khi triển khai; không suy rằng chỉ cần MongoDB 8.3 vì `$scoreFusion` đã có từ phiên bản đó.

### 22.4. Mẫu câu hỏi khi tra docs

Trước khi copy một pipeline:

1. Cluster đang chạy version nào và có hỗ trợ MongoDB Search/Vector Search không?
2. Tên index có đúng và index đã READY chưa?
3. `$rankFusion`, `$scoreFusion`, `$rerank` có được hỗ trợ trong deployment này không?
4. Operator bạn dùng là `$vectorSearch` aggregation stage hay `vectorSearch` operator bên trong `$search`?
5. Các input pipelines có nằm trong tập stages hợp lệ và cùng collection không?
6. Sub-pipeline có giữ nguyên documents đến khi fusion không?
7. Filter tenant/ACL/status có nằm **trước retrieval cutoff** ở cả hai nhánh không?
8. Raw scores đã được normalize nếu dùng score fusion chưa?
9. Query embedding có đúng model version/numDimensions không?
10. Rerank model có hỗ trợ ngôn ngữ, cost và data residency yêu cầu không?

## 23. Kết luận

**Kết hợp tìm kiếm từ khóa, vector và bước xếp hạng lại** là một chiến lược phối hợp nhiều tín hiệu, không phải một phép tìm kiếm duy nhất. **Keyword search** giữ thông tin chính xác về tên, mã lỗi, phiên bản và cụm từ; **vector search** tăng khả năng tìm các cách diễn đạt gần nghĩa; **fusion** hợp nhất và xếp hạng candidate lists; còn **reranker** có thể nâng chất lượng top results bằng việc đọc lại mối quan hệ query–document.

Trong MongoDB, `$search` và `$vectorSearch` tạo hai nhánh. **`$rankFusion` từ 8.0** là baseline RRF đáng thử; **`$scoreFusion` từ 8.3** hỗ trợ trộn normalized scores; **`$rerank`** là khả năng riêng cần kiểm tra version, feature toggle, model/tier/region theo trang Requirements. Nếu deployment chưa có fusion/rerank native, ứng dụng vẫn có thể thực hiện **RRF và reranking** với điều kiện quản lý đúng danh sách, scores, ACL và latency.

Thiết kế tốt phải cân bằng ba nguyên tắc: **tìm được evidence đúng** (candidate recall), **đặt evidence hữu ích lên đầu** (ranking quality) và **không vi phạm quyền truy cập/freshness/SLO**. Hãy bắt đầu từ keyword/vector baselines, đo Recall@K, MRR/nDCG và p95/p99, rồi tăng độ phức tạp chỉ khi chứng minh được giá trị. **Không một điểm BM25, cosine, RRF hay reranker nào tự thay thế được nguồn tài liệu đúng, filter được ủy quyền và đánh giá với nhu cầu người dùng thật.**
