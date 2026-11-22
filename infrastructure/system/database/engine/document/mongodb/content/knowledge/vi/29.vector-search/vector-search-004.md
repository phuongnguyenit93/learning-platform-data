# Vector index, độ tương đồng và lựa chọn tham số tìm kiếm trong MongoDB

## 1. Mục tiêu và bối cảnh

Một người dùng đặt câu hỏi: **“Làm thế nào để lấy lại tài khoản khi mất thiết bị xác thực?”**. Tài liệu đúng có thể mang tiêu đề **“Khôi phục xác thực hai yếu tố”**, dù câu hỏi không trùng hoàn toàn các từ trong tiêu đề. Tìm kiếm từ khóa chỉ giải quyết được một phần vấn đề này; tìm kiếm vector cho phép truy xuất những nội dung **gần nhau về cách biểu diễn ngữ nghĩa**.

MongoDB Vector Search dùng **embedding vectors** — những mảng số biểu diễn văn bản, hình ảnh hoặc những đối tượng khác. MongoDB lập chỉ mục vector rồi tìm những vectors gần query vector theo một **similarity metric** đã chọn.

Bài học thuộc chương **Tìm kiếm vector**, module **Database Engine Document MongoDB**, với đề bài **Vector index, độ tương đồng và lựa chọn tham số tìm kiếm**.

Sau khi học, bạn có thể:

1. Giải thích embedding, vector dimensions và sự tương thích của embedding model.
2. Tạo MongoDB Vector Search index loại `vectorSearch`.
3. So sánh `cosine`, `dotProduct` và `euclidean`.
4. Chạy truy vấn với aggregation stage `$vectorSearch`.
5. Phân biệt ANN (*Approximate Nearest Neighbors*) và ENN (*Exact Nearest Neighbors*).
6. Chọn `limit` và `numCandidates` theo trade-off recall–latency.
7. Khai báo metadata `filter` fields và dùng pre-filter theo tenant/quyền.
8. Đọc `vectorSearchScore`, không nhầm điểm số với xác suất chính xác.
9. Hiểu dimension limit, quantization và chỉ mục HNSW/flat.
10. Đánh giá ANN so với ENN bằng recall@k và đo p95 latency.
11. Tổ chức dữ liệu chunks, embeddings version và index lifecycle.
12. Viết ví dụ mongosh và Java Sync Driver cho một hệ thống retrieval/RAG.

**Nguyên tắc trung tâm:** Cùng embedding space, cùng vector dimensions, metric phù hợp, filter đúng quyền và tham số ANN được benchmark là điều kiện để vector search đáng tin cậy. Không nên lấy một con số `score` cao làm bằng chứng tài liệu đúng hay người dùng đã được phân quyền đọc.

> **Phạm vi bài:** Các ví dụ dùng **BYO embeddings** (*Bring Your Own Embeddings*): ứng dụng tự tạo hoặc cung cấp vectors, lưu chúng vào MongoDB và tạo index với field type `vector`. Các chế độ MongoDB tự tạo embeddings (*Automated Embedding*) có cú pháp index/query khác và sẽ được phân biệt để tránh nhầm lẫn.

## 2. Từ dữ liệu gốc đến embedding vector

Một embedding là mảng các con số:

~~~javascript
[0.12, -0.43, 0.08, 0.95]
~~~

Đây là vector 4 chiều; embedding thật thường có hàng trăm hoặc hàng nghìn chiều. Các tọa độ được mô hình học ra, không mặc nhiên biểu diễn các nhãn cụ thể như “giá” hay “mật khẩu”.

~~~text
Nội dung tài liệu                Câu hỏi người dùng
      |                                  |
      v                                  v
Embedding model M                 Embedding model M
      |                                  |
      v                                  v
Document embedding                 Query embedding
      |                                  |
      v                                  |
 MongoDB collection                     |
      |                                  |
      v                                  v
 Vector Search index  ------>  $vectorSearch
                                        |
                                        v
                                 Top-k tài liệu
~~~

### 2.1. Cùng model là yêu cầu quan trọng

Nếu documents được embed bằng model M1 còn query bằng model M2 không tương thích, khoảng cách vector không còn mô tả đúng sự tương đồng. Thậm chí M1 và M2 có cùng 1.536 chiều, hệ tọa độ cũng có thể hoàn toàn khác.

Một vector query phải được tạo bằng cùng model/version hoặc một cơ chế tương thích đã được kiểm chứng với những vectors lưu trong index.

### 2.2. Dùng một collection chứa embedding

~~~javascript
{
  _id: "doc-001",
  tenantId: "tenant-A",
  title: "Khôi phục mật khẩu",
  content: "Sử dụng mã dự phòng hoặc quy trình xác minh...",
  embedding: [0.96, 0.17, 0.04],
  embeddingModel: "toy-3d-v1",
  published: true
}
~~~

Ưu điểm là metadata, text và vector được lưu theo cùng một document. Nhược điểm là embedding lớn làm tăng dung lượng và băng thông nếu trả nguyên document.

### 2.3. Một document dài nên chia chunks khi nào?

Đối với tài liệu nhiều trang, một vector cho cả tài liệu dễ trộn nhiều ý. Có thể chia thành những **chunks**:

~~~javascript
{
  _id: "doc-001:chunk-03",
  documentId: "doc-001",
  chunkIndex: 3,
  tenantId: "tenant-A",
  content: "Cách cấp lại mã dự phòng...",
  embedding: [/* ... */],
  embeddingModel: "embedding-v1"
}
~~~

Chunking giúp truy xuất chính xác đoạn văn nhưng tăng số vectors, index size và chi phí. Cần cân bằng giữa chunk size, overlap và mức mất ngữ cảnh.

### 2.4. Vector ví dụ 3 chiều trong bài chỉ là dữ liệu giả lập

Để dễ hiểu, ta quy ước ba trục **minh họa**:

~~~text
Chiều 1: tài khoản / đăng nhập
Chiều 2: thanh toán
Chiều 3: thiết bị
~~~

Ví dụ:

~~~javascript
[0.99, 0.08, 0.03] // Chủ yếu liên quan tài khoản.
[0.02, 0.99, 0.02] // Chủ yếu liên quan thanh toán.
[0.04, 0.08, 0.99] // Chủ yếu liên quan thiết bị.
~~~

Đây không phải output của một embedding model đã huấn luyện và không chứng minh hệ thống hiểu tiếng Việt. Production phải sử dụng embeddings thật được đánh giá riêng.

## 3. Vector Search index khác chỉ mục B-tree

Trong MongoDB, cần phân biệt:

| Loại index | Cách tạo/định nghĩa | Dùng cho |
|---|---|---|
| Ordinary B-tree | `createIndex({tenantId:1})` | Equality, range, sort |
| Native text index | `createIndex({content:"text"})` | `$text` và textScore |
| MongoDB Search index | `createSearchIndex(...,"search",...)` | `$search` lexical/advanced |
| MongoDB Vector Search index | `createSearchIndex(...,"vectorSearch",...)` | `$vectorSearch` nearest neighbor |

Một lệnh:

~~~javascript
db.knowledgeChunks.createIndex({ embedding: 1 });
~~~

**không** tạo Vector Search index. Đây là chỉ mục MongoDB thường, không phải cấu trúc nearest-neighbor được `$vectorSearch` sử dụng.

### 3.1. Search index là một cấu phần riêng

MongoDB Vector Search index được quản lý và đồng bộ theo hạ tầng search của deployment. Vì vậy có thể có một khoảng trễ giữa:

~~~text
insertOne thành công
        |
        v
document đọc được bằng find()
        |
        v
Search index tiếp nhận/đồng bộ document
        |
        v
document có thể được trả bởi $vectorSearch
~~~

Không nên hứa `$vectorSearch` lập tức thấy mọi write ngay sau khi `insertOne` trả thành công.

### 3.2. Yêu cầu môi trường

Bạn cần deployment MongoDB có **Vector Search** được bật và hỗ trợ loại chỉ mục này, chẳng hạn Atlas phù hợp. MongoDB cũng có hỗ trợ các cấu hình local/self-managed riêng ở những phiên bản mới, nhưng không thể giả định mọi standalone Community MongoDB cài mặc định đều có search services đầy đủ.

Trước khi thực hành:

1. Xác nhận deployment hỗ trợ Vector Search.
2. Đảm bảo quyền tạo search indexes.
3. Dùng mongosh/driver phù hợp.
4. Tạo index đúng type và đợi index queryable/READY.
5. Không chạy DDL trên production chỉ để làm demo.

## 4. Ba thước đo tương đồng quan trọng

MongoDB Vector Search hỗ trợ:

~~~text
cosine
dotProduct
euclidean
~~~

Mỗi metric có cách đo khác nhau.

### 4.1. Cosine similarity

Cosine đo **góc** giữa hai vector khác vector 0:

\[
\operatorname{cosine}(a,b)=
\frac{\sum_{i=1}^{d}a_i b_i}
{\sqrt{\sum_{i=1}^{d}a_i^2}
 \sqrt{\sum_{i=1}^{d}b_i^2}}
\]

Ví dụ:

~~~text
a = [1,0]
b = [2,0]

cosine(a,b)=1 vì chúng cùng hướng.
~~~

Cosine thường phù hợp khi hướng của embedding là tín hiệu ngữ nghĩa chính và magnitude không cần quyết định mức độ giống nhau.

**Không dùng vector zero** với cosine vì norm bằng 0 làm mẫu số không xác định.

### 4.2. Dot product

Dot product:

\[
a\cdot b=\sum_{i=1}^{d}a_i b_i
\]

Ví dụ:

~~~text
a = [1,0]
b = [2,0]
dotProduct(a,b) = 2
~~~

Dot product chịu ảnh hưởng magnitude. Nếu hai vectors được chuẩn hóa về độ dài 1 (*unit-normalized*), dot product bằng cosine về mặt toán học.

Với embeddings **BYO**, tài liệu MongoDB yêu cầu vectors được chuẩn hóa unit length ở **index time** và **query time** khi chọn `dotProduct`. Đừng trộn vectors chưa normalize với metric này.

### 4.3. Euclidean distance

Euclidean là khoảng cách hình học:

\[
d(a,b)=\sqrt{\sum_{i=1}^{d}(a_i-b_i)^2}
\]

Ví dụ:

~~~text
a = [1,0]
b = [2,0]
euclidean(a,b)=1
~~~

Khoảng cách càng **nhỏ** thì hai vectors càng gần theo Euclidean.

### 4.4. Bảng so sánh

| Metric | Ý nghĩa | Magnitude | Điều kiện đáng chú ý |
|---|---|---|---|
| `cosine` | Góc giữa vectors | Không ảnh hưởng khi cùng hướng | Không có zero vector |
| `dotProduct` | Tích vô hướng | Có ảnh hưởng nếu không normalize | BYO phải unit-normalized |
| `euclidean` | Khoảng cách hình học | Có ảnh hưởng | Nhỏ hơn là gần hơn |

Không có metric tốt nhất cho mọi hệ thống. Chọn theo embedding model và đánh giá thực tế. Một số model khuyến nghị dot product, một số khuyến nghị cosine.

### 4.5. Cùng hướng nhưng khác khoảng cách

~~~text
O ---> A=[1,0] ----> B=[2,0]

Cosine:     A và B có cùng hướng.
DotProduct: phụ thuộc độ dài.
Euclidean:  khoảng cách A-B khác 0.
~~~

## 5. vectorSearchScore được MongoDB chuẩn hóa

Trong `$vectorSearch`, MongoDB trả metadata `vectorSearchScore` trong khoảng **0 đến 1**; giá trị lớn hơn biểu thị độ tương đồng cao hơn trong phạm vi metric/query.

~~~javascript
{
  $project: {
    title: 1,
    score: { $meta: "vectorSearchScore" }
  }
}
~~~

**Điểm 0.93 không có nghĩa xác suất 93% câu trả lời đúng.** Nó là điểm ranking, phụ thuộc metric, embedding model, index và query.

### 5.1. Công thức chuẩn hóa cosine

\[
score_{cosine}=\frac{1+\operatorname{cosine}(a,b)}{2}
\]

| Cosine thô | Score |
|---:|---:|
| -1 | 0 |
| 0 | 0.5 |
| 0.6 | 0.8 |
| 1 | 1 |

### 5.2. Công thức chuẩn hóa Euclidean

\[
score_{euclidean}=\frac{1}{1+d(a,b)}
\]

Nếu distance=0 thì score=1. Nếu distance=3 thì score=0.25.

### 5.3. Dot product normalized score

Với vectors đã chuẩn hóa, dot product nằm trong [-1,1]:

\[
score_{dot}=\frac{1+\operatorname{dotProduct}(a,b)}{2}
\]

Vì vậy, yêu cầu normalize unit length không chỉ liên quan hiệu năng mà còn liên quan ngữ nghĩa của điểm số.

### 5.4. Không so điểm giữa hai index/model tùy tiện

Score 0.86 từ model A/index cosine không mặc nhiên tương đương score 0.86 từ model B/index Euclidean hoặc một reranker. Muốn threshold, hãy hiệu chỉnh trên tập queries và ground truth của chính ứng dụng.

## 6. Chọn numDimensions

Index vector cần biết số chiều:

~~~javascript
{
  type: "vector",
  path: "embedding",
  numDimensions: 3,
  similarity: "cosine"
}
~~~

Nếu index có `numDimensions:3`, thì:

~~~javascript
queryVector: [1, 0, 0]   // Hợp lệ.
queryVector: [1, 0]      // Sai số chiều.
queryVector: [1, 0, 0, 0] // Sai số chiều.
~~~

Cần kiểm tra:

- Mọi document có vector đúng chiều không?
- Query vector có đúng chiều không?
- Có document nào dùng model version mới với dimension khác không?
- Có vector NaN/Infinity hoặc zero vector không?
- Kiểu BSON/numeric có phù hợp không?

### 6.1. Giới hạn 8.192 chiều

MongoDB Vector Search hiện hỗ trợ tới **8.192 dimensions** cho những kiểu vectors/quantization tương ứng. Với một số kiểu BinData int1 hoặc binary quantization, dimensions phải là **bội số của 8**. Automated Embedding có những mức dimensions hỗ trợ riêng.

Không lấy một giới hạn duy nhất áp cho mọi kiểu ingest/indexing method mà không xem tài liệu đúng version.

### 6.2. Chọn model và dimension theo chất lượng, không theo số lớn nhất

Vector 3.072 chiều không mặc nhiên tìm kiếm tốt hơn vector 1.024 chiều. Cần đánh giá quality, chi phí embedding, index RAM/storage và latency.

## 7. Dữ liệu thực hành: tám document giả lập

Các vectors 3 chiều dưới đây được tạo thủ công để dễ quan sát; **không đại diện embeddings ngữ nghĩa thật**.

Chạy trên deployment có MongoDB Vector Search:

~~~javascript
use vector_search_lab
~~~

Tạo tài liệu thử nghiệm:

~~~javascript
const sampleDocuments = [
  {
    _id: "A-001",
    tenantId: "tenant-A",
    published: true,
    category: "account",
    title: "Khôi phục mật khẩu tài khoản",
    content: "Các bước lấy lại quyền truy cập tài khoản.",
    embedding: [0.99, 0.08, 0.03],
    embeddingModel: "toy-3d-v1"
  },
  {
    _id: "A-002",
    tenantId: "tenant-A",
    published: true,
    category: "account",
    title: "Bật xác thực hai yếu tố",
    content: "Ứng dụng xác thực và mã khôi phục dự phòng.",
    embedding: [0.93, 0.30, 0.03],
    embeddingModel: "toy-3d-v1"
  },
  {
    _id: "A-003",
    tenantId: "tenant-A",
    published: true,
    category: "billing",
    title: "Thanh toán hóa đơn",
    content: "Thông tin về các phương thức thanh toán.",
    embedding: [0.02, 0.99, 0.02],
    embeddingModel: "toy-3d-v1"
  },
  {
    _id: "A-004",
    tenantId: "tenant-A",
    published: true,
    category: "device",
    title: "Kết nối cảm biến",
    content: "Cách đăng ký thiết bị IoT mới.",
    embedding: [0.04, 0.08, 0.99],
    embeddingModel: "toy-3d-v1"
  },
  {
    _id: "B-001",
    tenantId: "tenant-B",
    published: true,
    category: "account",
    title: "Lấy lại tài khoản tenant B",
    content: "Cấp lại quyền truy cập cho tenant B.",
    embedding: [0.98, 0.12, 0.03],
    embeddingModel: "toy-3d-v1"
  },
  {
    _id: "A-005",
    tenantId: "tenant-A",
    published: false,
    category: "account",
    title: "Khóa tài khoản - bản nháp",
    content: "Tài liệu chưa phát hành.",
    embedding: [0.92, 0.20, 0.10],
    embeddingModel: "toy-3d-v1"
  },
  {
    _id: "A-006",
    tenantId: "tenant-A",
    published: true,
    category: "billing",
    title: "Đổi phương thức thanh toán",
    content: "Cập nhật thẻ thanh toán.",
    embedding: [0.16, 0.96, 0.09],
    embeddingModel: "toy-3d-v1"
  },
  {
    _id: "A-007",
    tenantId: "tenant-A",
    published: true,
    category: "account",
    title: "Quản lý token truy cập",
    content: "Tạo, vô hiệu hóa và thay mới token.",
    embedding: [0.80, 0.51, 0.08],
    embeddingModel: "toy-3d-v1"
  }
];

db.knowledgeChunks.insertMany(sampleDocuments);
~~~

Khi collection mới và rỗng:

- Có 8 documents.
- Tenant-A có 7 documents (6 published và 1 unpublished).
- Tenant-B có 1 document.
- Mọi embedding có 3 chiều và khác vector zero.
- Mọi document có `embeddingModel:"toy-3d-v1"`.

Kiểm tra:

~~~javascript
db.knowledgeChunks.countDocuments({});
db.knowledgeChunks.find(
  {},
  { _id: 1, tenantId: 1, published: 1, title: 1 }
).sort({ _id: 1 });
~~~

**Không** chạy lại insert trên collection đã nạp nếu muốn tránh duplicate `_id`. Những kết quả kỳ vọng trong bài giả định không có dữ liệu từ lần thực hành trước hoặc các writes ngoài mô tả.

## 8. Tạo Vector Search index

Tạo một index với field vector và metadata filters:

~~~javascript
db.knowledgeChunks.createSearchIndex(
  "embedding_v1",
  "vectorSearch",
  {
    fields: [
      {
        type: "vector",
        path: "embedding",
        numDimensions: 3,
        similarity: "cosine"
      },
      { type: "filter", path: "tenantId" },
      { type: "filter", path: "published" },
      { type: "filter", path: "category" },
      { type: "filter", path: "embeddingModel" }
    ]
  }
);
~~~

| Field | Vai trò |
|---|---|
| `"embedding_v1"` | Tên search index để query tham chiếu |
| `"vectorSearch"` | Loại search index |
| `type:"vector"` | Định nghĩa field chứa vector |
| `path:"embedding"` | Field vector trong document |
| `numDimensions:3` | Kích thước vector |
| `similarity:"cosine"` | Metric tương đồng |
| `type:"filter"` | Metadata field để lọc trước vector retrieval |

### 8.1. Index filter khác index B-tree

Một index ordinary:

~~~javascript
db.knowledgeChunks.createIndex({ tenantId: 1 });
~~~

có thể tốt cho truy vấn `find()`, nhưng **không tự thay thế** `type:"filter",path:"tenantId"` trong Vector Search index. Query `$vectorSearch.filter` cần metadata field được index theo cơ chế Vector Search.

### 8.2. Index build bất đồng bộ

Sau khi tạo search index, đợi trạng thái sẵn sàng:

~~~javascript
db.knowledgeChunks.getSearchIndexes();
~~~

Hoặc:

~~~javascript
db.knowledgeChunks.getSearchIndexes("embedding_v1");
~~~

Theo version, kết quả có thể chứa `status:"READY"` hoặc `queryable:true`. Không tự giả định `createSearchIndex()` trả thành công nghĩa index lập tức hoàn tất mọi công việc.

### 8.3. Tên index khác path

~~~javascript
index: "embedding_v1"  // Tên search index.
path: "embedding"      // Field mảng vector.
~~~

Không nhầm hai giá trị này.

### 8.4. Một document không có vector hợp lệ

Nếu document thiếu `embedding` hoặc sai số chiều, nó không thể tham gia retrieval như một vector 3 chiều hợp lệ. Cần giám sát độ đầy đủ của embedding ingest thay vì xem insert thành công là đã được index.

## 9. Chạy $vectorSearch đầu tiên

Khi `embedding_v1` sẵn sàng:

~~~javascript
const q = [1.0, 0.0, 0.0];

db.knowledgeChunks.aggregate([
  {
    $vectorSearch: {
      index: "embedding_v1",
      path: "embedding",
      queryVector: q,
      numCandidates: 100,
      limit: 3
    }
  },
  {
    $project: {
      _id: 1,
      title: 1,
      category: 1,
      tenantId: 1,
      score: { $meta: "vectorSearchScore" }
    }
  }
]);
~~~

Đây là **ANN search** khi không đặt `exact:true`.

### 9.1. Giải thích các tham số

| Thuộc tính | Ý nghĩa |
|---|---|
| `index` | Tên Vector Search index |
| `path` | Indexed vector field |
| `queryVector` | Vector query cùng embedding space |
| `numCandidates` | Mức tìm ứng viên của ANN |
| `limit` | Tối đa số documents từ vector retrieval |
| `$meta:"vectorSearchScore"` | Điểm xếp hạng tương đồng |

### 9.2. Ý nghĩa kết quả

Query `[1,0,0]` hướng về chủ đề tài khoản nên những documents account thường có cosine score cao hơn billing/device theo vectors giả lập.

Do ANN có tính xấp xỉ, không tuyên bố tất cả cluster/index sẽ trả cùng một thứ tự IDs trong mọi tình huống.

### 9.3. Stage bắt buộc đứng đầu

`$vectorSearch` phải là **stage đầu tiên** của pipeline chứa nó. Không đặt `$match` trước:

~~~javascript
// Sai:
db.knowledgeChunks.aggregate([
  { $match: { tenantId: "tenant-A" } },
  {
    $vectorSearch: {
      index: "embedding_v1",
      path: "embedding",
      queryVector: q,
      numCandidates: 100,
      limit: 3
    }
  }
]);
~~~

Để giới hạn corpus trước retrieval, dùng `filter` **bên trong** `$vectorSearch`.

## 10. ANN: nhanh nhưng xấp xỉ

Approximate Nearest Neighbors tìm các điểm gần query mà **không so sánh hết** các indexed embeddings.

MongoDB dùng **HNSW (Hierarchical Navigable Small Worlds)** làm thuật toán đồ thị cho ANN. Đồ thị kết nối các vectors gần nhau để traversal tìm những vùng phù hợp.

~~~text
Query embedding
      |
      v
Đi trong HNSW graph
      |
      v
Thu thập candidates gần query
      |
      v
Rank theo similarity
      |
      v
Trả top-k
~~~

### 10.1. Vì sao ANN có thể bỏ sót hàng xóm thực sự gần nhất?

Giả sử ENN tìm chính xác top-5:

~~~text
[A, B, C, D, E]
~~~

ANN có thể trả:

~~~text
[A, B, C, D, F]
~~~

ANN thiếu E và đưa F vào top-k, dù khoảng cách của E tốt hơn. Đây là trade-off giữa tốc độ và recall.

### 10.2. Vai trò của numCandidates

`numCandidates` điều chỉnh mức khám phá ứng viên trong ANN:

- **Nhỏ hơn:** thường tìm nhanh hơn nhưng tăng nguy cơ bỏ sót.
- **Lớn hơn:** thường tăng recall, có thể tăng latency/CPU.
- Không được nhỏ hơn `limit`.
- Theo tài liệu hiện hành, giá trị tối đa là **10.000**.

Nó **không phải** số kết quả trả cho người dùng; `limit` mới xác định số lượng kết quả tối đa.

### 10.3. Heuristic 20 × limit

MongoDB khuyến nghị bắt đầu bằng:

~~~text
numCandidates >= 20 * limit
~~~

Ví dụ:

| limit | numCandidates khởi đầu |
|---:|---:|
| 5 | 100 |
| 10 | 200 |
| 20 | 400 |
| 50 | 1.000 |

Đây là **điểm khởi đầu**, không phải bảo đảm đạt 95% recall. Cần kiểm tra với corpus và query thật.

### 10.4. Khi nào tăng numCandidates?

- ANN thiếu true-nearest neighbors so với ENN.
- Có nhiều vectors rất gần nhau.
- Index có quantization làm giảm precision.
- Filter có độ chọn lọc cao.
- Search corpus tăng lớn.
- Có yêu cầu recall cao hơn latency hiện tại.

Đo chất lượng và độ trễ sau mỗi bước; không tăng lên 10.000 chỉ vì “số lớn là tốt”.

## 11. ENN: tìm hàng xóm gần chính xác

Exact Nearest Neighbors tính nearest neighbors qua so sánh exhaustive các indexed vectors phù hợp, thay vì ANN traversal xấp xỉ.

~~~javascript
db.knowledgeChunks.aggregate([
  {
    $vectorSearch: {
      index: "embedding_v1",
      path: "embedding",
      queryVector: [1, 0, 0],
      exact: true,
      limit: 3
    }
  },
  {
    $project: {
      title: 1,
      score: { $meta: "vectorSearchScore" }
    }
  }
]);
~~~

### 11.1. ANN và ENN khác nhau ở đâu?

| Tiêu chí | ANN | ENN |
|---|---|---|
| Query config | `numCandidates`, `limit` | `exact:true`, `limit` |
| Phương thức | Graph traversal xấp xỉ | Exhaustive nearest neighbor |
| Recall so với true top-k | Có thể thấp hơn 100% | Ground truth theo indexed vectors/metric |
| Chi phí tập lớn | Thường thấp hơn | Thường cao hơn |
| Vai trò | Truy vấn realtime corpus lớn | Benchmark/nhỏ/chọn lọc cao |

### 11.2. Không truyền numCandidates trong ví dụ ENN

`numCandidates` điều khiển ANN; ENN sử dụng `exact:true` và không cần tham số candidate budget.

### 11.3. ENN không bảo đảm tài liệu “đúng nghĩa”

ENN chính xác **về khoảng cách vector**, chứ không chứng minh embedding model hiểu đúng câu hỏi. Nếu model kém hoặc data có sai lệch, ENN vẫn trả nearest neighbor không hữu ích.

## 12. Pre-filter theo metadata

Một hệ thống nhiều tenant cần đảm bảo chỉ tìm trên documents mà người dùng được phép xem.

~~~javascript
db.knowledgeChunks.aggregate([
  {
    $vectorSearch: {
      index: "embedding_v1",
      path: "embedding",
      queryVector: [1, 0, 0],
      numCandidates: 100,
      limit: 3,
      filter: {
        tenantId: "tenant-A",
        published: true
      }
    }
  },
  {
    $project: {
      title: 1,
      tenantId: 1,
      published: 1,
      score: { $meta: "vectorSearchScore" }
    }
  }
]);
~~~

Ở đây tenant-B và unpublished documents bị loại khỏi tập ứng viên mà ứng dụng muốn truy xuất.

### 12.1. Filter fields phải được index trước

Trong Vector Search index có:

~~~javascript
{ type: "filter", path: "tenantId" }
{ type: "filter", path: "published" }
~~~

Nếu thiếu, query `filter:{tenantId:...}` có thể không hợp lệ.

### 12.2. Pre-filter và post-filter không tương đương

Pre-filter:

~~~javascript
{
  $vectorSearch: {
    // Những fields khác giữ nguyên.
    filter: {
      tenantId: "tenant-A",
      published: true
    }
  }
}
~~~

Post-filter:

~~~javascript
[
  { $vectorSearch: { /* các tham số */ } },
  { $match: { tenantId: "tenant-A", published: true } }
]
~~~

Nếu vector retrieval lấy top-10 **toàn corpus**, rồi post-filter chỉ còn một kết quả tenant-A, ứng dụng không biết những tài liệu tenant-A khác ở vị trí 11, 12, ... Việc lọc sau có thể làm kết quả ít hơn `limit` và bỏ sót những hàng xóm phù hợp trong phạm vi người dùng.

### 12.3. Pre-filter vẫn có chi phí

Filter rất chọn lọc có thể làm ANN traversal tốn chi phí và giảm recall nếu candidates quá ít. Cần benchmark ENN/flat khi tập sau filter nhỏ.

### 12.4. Các loại filter dữ liệu

MongoDB Vector Search hỗ trợ pre-filter các field có kiểu như Boolean, Date, ObjectId, numeric, String, UUID và arrays của các kiểu được hỗ trợ. Chỉ một **tập con** các toán tử MQL hoạt động với `filter`, ví dụ equality, `$in` và range phù hợp.

Không cho rằng `$regex` hoặc mọi aggregation expression đều dùng được bên trong `filter`.

### 12.5. Thêm category

~~~javascript
filter: {
  tenantId: "tenant-A",
  published: true,
  category: { $in: ["account", "billing"] }
}
~~~

Nhớ khai báo `category` là type `filter` trong index, như dataset đã chuẩn bị.

## 13. Tenant và ACL là ranh giới bảo mật

Ứng dụng không được tin `tenantId` người dùng tự gửi:

~~~javascript
// Không đủ an toàn:
const tenantId = request.query.tenantId;
~~~

Tầng API phải lấy tenant/role/ACL từ identity đã xác thực và đưa chúng vào query restriction trước khi retrieval.

~~~text
User request
      |
      v
Authentication + Authorization
      |
      v
Resolve allowed tenant / ACL
      |
      v
$vectorSearch.filter
      |
      v
Only authorized documents
      |
      v
Optional reranker / LLM
~~~

Không chỉ lọc tenant sau khi đã gửi kết quả trái quyền đến reranker hoặc LLM. Nếu quyền của một tài liệu thay đổi, cần xem lại đồng bộ search index, cache và bước lấy tài liệu nguồn.

### 13.1. Vì sao retrieval có thể làm lộ dữ liệu?

Một LLM có thể đưa nội dung tài liệu trái quyền vào câu trả lời nếu retrieval đã cung cấp nội dung đó. Điểm tương đồng không thay thế phân quyền.

### 13.2. Filter theo quyền cũng cần truy vấn tài liệu gốc

Nếu vector result chứa `documentId` và ứng dụng fetch tài liệu ở collection khác, bước fetch cũng phải kiểm tra quyền; không tin hoàn toàn rằng một vector result là bằng chứng quyền luôn còn hợp lệ.

## 14. Hiển thị và lọc vectorSearchScore

Để lấy score:

~~~javascript
db.knowledgeChunks.aggregate([
  {
    $vectorSearch: {
      index: "embedding_v1",
      path: "embedding",
      queryVector: [1, 0, 0],
      numCandidates: 100,
      limit: 10
    }
  },
  {
    $project: {
      title: 1,
      score: { $meta: "vectorSearchScore" }
    }
  }
]);
~~~

Score là metadata **của query**, không phải field persisted trong document.

### 14.1. Post-filter theo score

~~~javascript
db.knowledgeChunks.aggregate([
  {
    $vectorSearch: {
      index: "embedding_v1",
      path: "embedding",
      queryVector: [1, 0, 0],
      numCandidates: 100,
      limit: 20,
      filter: {
        tenantId: "tenant-A",
        published: true
      }
    }
  },
  {
    $addFields: {
      score: { $meta: "vectorSearchScore" }
    }
  },
  {
    $match: {
      score: { $gte: 0.85 }
    }
  },
  {
    $project: {
      embedding: 0
    }
  }
]);
~~~

Giá trị `0.85` **chỉ minh họa**. Đừng đặt một threshold phổ quát cho mọi model/index vì normalized score không phải xác suất.

### 14.2. Không có score khi chưa chạy vector search

~~~javascript
db.knowledgeChunks.find({
  score: { $gte: 0.85 }
});
~~~

không có ý nghĩa retrieval cho query vector mới, trừ khi bạn đã chủ động lưu score cho một query cố định vào document. Score thay đổi khi query vector thay đổi.

## 15. Tuning numCandidates: recall và latency

Giả sử endpoint trả **10 kết quả**:

~~~text
Target SLO ví dụ:
p95 latency < 250ms
recall@10 >= 0.92 so với ENN
~~~

Đây là yêu cầu ứng dụng ví dụ, không phải mức chất lượng MongoDB tự cam kết.

Thử các cấu hình:

| Cấu hình | limit | numCandidates |
|---|---:|---:|
| Nhanh | 10 | 50 |
| Trung bình | 10 | 100 |
| Khởi đầu 20× | 10 | 200 |
| Rộng hơn | 10 | 400 |
| Rất rộng | 10 | 1.000 |

Chạy cùng query/filter trên corpus đại diện:

~~~javascript
const q = [1, 0, 0];

function searchWithCandidates(n) {
  return db.knowledgeChunks.aggregate([
    {
      $vectorSearch: {
        index: "embedding_v1",
        path: "embedding",
        queryVector: q,
        numCandidates: n,
        limit: 5,
        filter: {
          tenantId: "tenant-A",
          published: true
        }
      }
    },
    {
      $project: {
        _id: 1,
        title: 1,
        score: { $meta: "vectorSearchScore" }
      }
    }
  ]).toArray();
}

printjson(searchWithCandidates(100));
~~~

Trên lab 8 documents, thay đổi candidates không đủ để đánh giá latency/recall production. Cần corpus lớn và query distribution thực tế.

### 15.1. Tăng candidates không luôn mang lại lợi ích tương xứng

Từ 50 lên 200 có thể cải thiện recall rõ, nhưng từ 2.000 lên 4.000 có thể tăng latency nhiều hơn phần recall được cải thiện. Chọn điểm cân bằng bằng biểu đồ benchmark.

### 15.2. Có filter thì cần benchmark riêng

ANN top-k với filter tenant-A có thể có behavior khác với ANN top-k toàn corpus. Đo theo các nhóm độ chọn lọc khác nhau, không chỉ một query không filter.

### 15.3. Số lượng kết quả có thể ít hơn limit

Có thể do documents sau filter ít, vectors thiếu/sai, index chưa đồng bộ hoặc post-filter loại bớt. `limit` là **số tối đa**, không phải cam kết luôn có đủ kết quả.

## 16. Recall@k: đo chất lượng ANN so với ENN

Cho ENN top-5:

~~~text
[A, B, C, D, E]
~~~

và ANN top-5:

~~~text
[A, B, C, F, G]
~~~

Có 3 IDs giao nhau nên:

\[
recall@5=\frac{|ANN@5\cap ENN@5|}{5}=\frac35=0.6
\]

Đây là **recall theo hàng xóm gần chính xác**, không đồng nghĩa precision về mặt nội dung với con người.

### 16.1. Mẫu mongosh

~~~javascript
const q = [1, 0, 0];

function searchIds(exact, candidates, limit) {
  const stage = {
    index: "embedding_v1",
    path: "embedding",
    queryVector: q,
    limit: limit,
    filter: {
      tenantId: "tenant-A",
      published: true
    }
  };

  if (exact) {
    stage.exact = true;
  } else {
    stage.numCandidates = candidates;
  }

  return db.knowledgeChunks.aggregate([
    { $vectorSearch: stage },
    { $project: { _id: 1 } }
  ]).toArray().map(item => String(item._id));
}

const exactIds = searchIds(true, null, 5);
const annIds = searchIds(false, 100, 5);

const groundTruth = new Set(exactIds);
const hits = annIds.filter(id => groundTruth.has(id)).length;

printjson({
  exactIds,
  annIds,
  hits,
  recallAt5: hits / exactIds.length
});
~~~

Nếu ENN chỉ trả 0 documents, cần xử lý trường hợp denominator=0 trong một benchmark tổng quát.

### 16.2. Điều kiện so sánh công bằng

- Query vector giống nhau.
- Cùng filter/tenant/ACL.
- Cùng indexed corpus và embedding version.
- Cùng metric.
- Cùng `limit`.
- Dữ liệu/index không thay đổi đáng kể giữa hai queries.

### 16.3. Metrics bổ sung

| Metric | Dùng để đánh giá |
|---|---|
| Recall@k so ENN | ANN có bỏ sót true-nearest neighbors không |
| Precision@k theo labels | Bao nhiêu kết quả hữu ích |
| NDCG@k | Chất lượng thứ tự xếp hạng |
| MRR | Vị trí kết quả hữu ích đầu tiên |
| p50/p95/p99 latency | Trải nghiệm tốc độ |
| Cost/query | CPU/RAM/chi phí Search Nodes |
| Freshness lag | Dữ liệu mới xuất hiện trong index chậm bao lâu |

ANN có recall so ENN cao nhưng embedding model không hiểu câu hỏi thì sản phẩm vẫn có thể thất bại. Cần đánh giá retrieval relevance bằng nhãn thực.

## 17. Quantization và trade-off tài nguyên

Một vector float32 1.536 chiều cần khoảng:

~~~text
1536 * 4 bytes = 6144 bytes
~~~

cho phần dữ liệu số thô, chưa tính BSON overhead hoặc cấu trúc index.

MongoDB Vector Search có các cách giảm precision/index RAM tùy mode/version:

- **float:** độ trung thực cao, chi phí RAM/storage cao hơn.
- **scalar quantization:** dùng biểu diễn ít bit hơn (thường tương đương int8) cho chỉ mục.
- **binary quantization:** nén còn một số bit rất nhỏ, có thể rescoring bằng vector đầy đủ theo mode.
- **binaryNoRescore:** một option ở chế độ Automated Embedding trong các deployment hỗ trợ; đổi lấy tốc độ/tài nguyên bằng khả năng giảm chính xác.

### 17.1. Ví dụ scalar quantization

Có thể thử index khác tên:

~~~javascript
db.knowledgeChunks.createSearchIndex(
  "embedding_scalar_v1",
  "vectorSearch",
  {
    fields: [
      {
        type: "vector",
        path: "embedding",
        numDimensions: 3,
        similarity: "cosine",
        quantization: "scalar"
      },
      { type: "filter", path: "tenantId" },
      { type: "filter", path: "published" }
    ]
  }
);
~~~

Kiểm tra compatibility của driver/server và kiểu vectors. Với binary quantization, các điều kiện dimension như **bội số của 8** có thể áp dụng.

### 17.2. Vì sao quantization có thể giảm recall?

Giảm precision khiến hai vectors ban đầu khác nhau trở nên khó phân biệt hơn, đặc biệt ở những trường hợp điểm gần sát. So sánh trên một bộ dữ liệu đại diện với **float ENN baseline**.

### 17.3. Đánh giá đúng

Cùng query/filter và cùng corpus:

1. Float ENN làm ground truth.
2. Float ANN với numCandidates đã tune.
3. Scalar ANN.
4. Binary ANN nếu hỗ trợ.
5. So recall, p95, index size/RAM và build time.

**Lưu ý:** Nén search index không mặc nhiên làm giảm độ dài field embedding đã lưu trong BSON document. Muốn tối ưu storage toàn diện, phải đánh giá format/kiểu lưu riêng.

## 18. HNSW, flat indexing và lựa chọn

HNSW phù hợp cho ANN corpus lớn, dùng graph của các điểm gần nhau.

Trong các phiên bản mới có hỗ trợ `indexingMethod`:

~~~javascript
{
  type: "vector",
  path: "embedding",
  numDimensions: 3,
  similarity: "cosine",
  indexingMethod: "hnsw"
}
~~~

Một số deployment còn có `"flat"`.

### 18.1. Khi chọn HNSW?

- Corpus lớn.
- Các queries không bị pre-filter quá hẹp.
- Cần latency thấp với recall đủ cao.
- Có thể chi trả index graph build/maintenance.

### 18.2. Khi thử flat hoặc ENN?

- Tập kết quả sau pre-filter rất nhỏ, ví dụ một user chỉ có 100 chunks.
- Nghiệp vụ ưu tiên full recall.
- Data nhỏ/trung bình.
- HNSW ANN traversal khi filter chặt không còn hiệu quả.

Flat indexing được giới thiệu ở các deployment mới, nên phải kiểm tra availability. Không khẳng định mọi MongoDB version hỗ trợ mọi value `indexingMethod`.

### 18.3. Có nên chỉnh HNSW graph parameters?

Những tùy chọn như `hnswOptions.maxEdges` và `hnswOptions.numEdgeCandidates` ảnh hưởng xây dựng graph và tài nguyên. Bắt đầu bằng defaults; sau khi tune query numCandidates và vẫn gặp recall kém trên index lớn thì mới thử chỉnh graph settings.

## 19. Tối ưu pre-filter và partition theo tenant

Một index filter có thể khai báo:

~~~javascript
{ type: "filter", path: "tenantId" }
{ type: "filter", path: "published" }
{ type: "filter", path: "category" }
~~~

Truy vấn:

~~~javascript
filter: {
  tenantId: "tenant-A",
  published: true,
  category: "account"
}
~~~

Nếu một ứng dụng có 10 triệu vectors nhưng mỗi tenant chỉ có vài trăm documents, **selectivity rất cao**. ANN graph traversal có thể không phải lựa chọn tốt nhất, cần thử ENN hoặc flat và đo thực tế.

### 19.1. Thêm date range

Nếu document có `createdAt` kiểu Date, khai báo:

~~~javascript
{ type: "filter", path: "createdAt" }
~~~

Rồi:

~~~javascript
filter: {
  tenantId: "tenant-A",
  createdAt: {
    $gte: ISODate("2026-01-01T00:00:00Z")
  }
}
~~~

Chỉ áp dụng nếu field tồn tại với kiểu dữ liệu phù hợp và filter operators đó được version hỗ trợ.

### 19.2. Filter quá nhiều cũng có giá

Mỗi indexed filter field tiêu tốn tài nguyên index. Chỉ thêm các trường có giá trị nghiệp vụ/query thực; không đưa toàn bộ document schema vào filter index không có lý do.

## 20. Quản lý score threshold và ranking

Một endpoint có thể lấy top-20 rồi chỉ giữ những chunks score >= 0.85, nhưng **0.85 không phải ngưỡng phổ quát**.

Cần điều chỉnh theo:

- Embedding model và distribution score.
- Cosine/dotProduct/Euclidean.
- Loại query và corpus.
- Quantization.
- Yêu cầu precision/recall.
- Hành vi người dùng thực.

### 20.1. Không cộng thẳng lexical score và vector score

Nếu có text search score=8.3 và vectorSearchScore=0.86, phép cộng thô là không hợp lệ về ý nghĩa vì thang điểm khác.

### 20.2. RRF — Reciprocal Rank Fusion

Một hướng hybrid search dùng thứ hạng:

\[
RRF(d)=\sum_{r \in rankers}\frac{1}{k+rank_r(d)}
\]

với `k` là hằng số làm mượt của RRF, không phải `limit` của Vector Search.

RRF kết hợp thứ hạng từ nhánh lexical và vector mà không cần giả định hai score có cùng đơn vị.

### 20.3. Reranking

Có thể truy xuất 50 chunks, dùng reranker đánh giá query + content rồi chọn 8 chunks cho LLM. Cách này tăng khả năng precision nhưng cũng tăng latency/cost và có yêu cầu bảo mật dữ liệu.

## 21. Hybrid Search: khi semantic chưa đủ

Vector search có thể trả nội dung đúng chủ đề nhưng bỏ qua ký tự chính xác trong:

- Mã lỗi `ERR-4012`.
- SKU `INV-1234`.
- Tên người/tên công ty.
- Số hợp đồng.
- Một cụm từ cần trùng gần nguyên văn.

Sơ đồ:

~~~text
                 Query
                   |
            +------+------+
            |             |
            v             v
         Lexical        Vector
          Search         Search
            |             |
            +------+------+
                   |
              Rank fusion
                   |
                   v
               Top results
~~~

Native `$text`, MongoDB Search `$search` và `$vectorSearch` là những cơ chế khác nhau. Không coi chúng cùng dùng một index hoặc cùng có similarity score có thể cộng trực tiếp.

## 22. RAG — Retrieval-Augmented Generation

Một RAG pipeline phổ biến:

~~~text
User question
     |
     v
Xác thực / xác định tenant và ACL
     |
     v
Embedding model tạo query vector
     |
     v
$vectorSearch + pre-filter
     |
     v
Top-k chunks + scores
     |
     v
Optional rerank / dedup / fetch nguồn
     |
     v
LLM nhận đúng context được phép
     |
     v
Answer + nguồn tham khảo
~~~

### 22.1. Top-k của search và top-k của context khác nhau

Ví dụ:

~~~text
Vector search limit: 40
Reranker giữ: 10
LLM sử dụng: 6
~~~

Không có `limit` hoàn hảo cho mọi ứng dụng. Query ngắn, dài, có nhiều tài liệu trùng hay cần câu trả lời tổng hợp sẽ có recall/cost khác nhau.

### 22.2. Vector score cao không bảo đảm answer grounded

Một chunk score cao có thể đúng chủ đề nhưng không chứa dữ kiện cần trả lời. Cần đánh giá khả năng trích dẫn nguồn, mức trả lời sai/hallucination và điều kiện “không đủ thông tin”.

### 22.3. RAG vẫn có vấn đề injection/authorization

Không tự thực hiện lệnh từ văn bản được retrieval. Nội dung nguồn chỉ là dữ liệu, không được xem là instruction của hệ thống. Chỉ gửi context mà người dùng được phép xem.

## 23. Embedding migration và index version

Model mới có thể thay đổi:

- Số chiều.
- Normalization.
- Metric phù hợp.
- Chất lượng tiếng Việt/đa ngôn ngữ.
- Chi phí/latency embedding.
- Distribution score.

Nên lưu:

~~~javascript
{
  _id: "doc-001",
  embedding: [/* vector */],
  embeddingModel: "model-v1",
  embeddingVersion: 1,
  updatedAt: ISODate("2026-11-14T08:00:00Z")
}
~~~

### 23.1. Không trộn hai model trong cùng embedding field

Nếu nửa corpus dùng M1, nửa còn lại M2 nhưng query luôn từ M2, ranking có thể sai dù cùng dimension.

### 23.2. Phương án dual embeddings

~~~javascript
{
  embeddingV1: [/* vector M1 */],
  embeddingV2: [/* vector M2 */]
}
~~~

Tạo hai indexes theo hai paths. Sau đó:

1. Backfill embeddingV2.
2. Đợi indexV2 READY.
3. Query bằng model M2 trên indexV2.
4. So recall/relevance và p95 với pipeline M1.
5. Chuyển traffic từng phần.
6. Giữ rollback plan trước khi xóa M1.

### 23.3. Model mới đổi dimension?

Tạo path/index mới với numDimensions đúng model. Không thay index dimension rồi để dữ liệu cũ và mới hỗn hợp không kiểm soát.

## 24. Freshness, index readiness và sự cố

Một document có thể được `find()` nhìn thấy nhưng chưa xuất hiện trong `$vectorSearch` vì index sync bất đồng bộ.

### 24.1. Quy trình ingest thực tế

1. Validate nội dung/tenant/ACL.
2. Chia chunks nếu cần.
3. Sinh embedding cùng model/version.
4. Kiểm tra dimensions và numeric validity.
5. Insert/upsert tài liệu/chunks.
6. Theo dõi search index trạng thái đồng bộ.
7. Chỉ đánh dấu searchable nếu cần một hợp đồng nhất quán rõ.
8. Có retry/backoff khi search index chưa sẵn sàng.
9. Khi xóa/sửa nguồn, cập nhật chunks và quyền tương ứng.

### 24.2. Tại sao không retry vô hạn?

Nếu index đang build, spam `$vectorSearch` với tốc độ cao chỉ tăng tải. API nên trả trạng thái indexing, retry giới hạn, backoff, circuit breaker hoặc fallback theo SLA.

### 24.3. Error categories nên phân biệt

| Tình huống | Cách xử lý |
|---|---|
| Index không tồn tại | Kiểm tra tên/type/index rollout |
| Index chưa queryable | Theo dõi build/READY |
| Vector sai dimensions | Validation error, không retry mù |
| Filter field chưa index | Sửa định nghĩa index |
| Query timeout | Giới hạn tải, kiểm tra candidates và performance |
| Search overload | Backpressure và retry có giới hạn |
| Không có kết quả sau filter | Có thể là kết quả hợp lệ |
| Kết quả thiếu document vừa ghi | Kiểm tra index freshness |
| Ranking không liên quan | Đánh giá model/metric/chunking |
| Trả tài liệu sai tenant | Sự cố authorization cần xử lý nghiêm túc |

## 25. Tối ưu băng thông bằng projection

Đa số API chỉ cần title, content, ID, score, không cần trả vector dài:

~~~javascript
db.knowledgeChunks.aggregate([
  {
    $vectorSearch: {
      index: "embedding_v1",
      path: "embedding",
      queryVector: [1, 0, 0],
      numCandidates: 100,
      limit: 5,
      filter: {
        tenantId: "tenant-A",
        published: true
      }
    }
  },
  {
    $project: {
      _id: 1,
      title: 1,
      content: 1,
      category: 1,
      score: { $meta: "vectorSearchScore" }
    }
  }
]);
~~~

Projection dạng inclusion này không trả field `embedding`. Đây là cách giảm băng thông và tránh tiết lộ dữ liệu không cần thiết cho client.

### 25.1. Ước lượng dung lượng thô

Với 1 triệu embeddings có 1.536 chiều ở float32:

~~~text
1,000,000 * 1536 * 4 = 6,144,000,000 bytes
~~~

Đây chỉ là **dung lượng số thô**, chưa tính BSON, index graph, redundancy, các search index khác hay cache. Không dùng phép tính này thay báo giá hạ tầng thực.

### 25.2. Nhiều chunks làm số vectors tăng

100.000 tài liệu, mỗi tài liệu 30 chunks:

~~~text
100000 * 30 = 3,000,000 vectors
~~~

Việc chia nhỏ giúp retrieval chi tiết nhưng tăng chi phí. Nên có cơ chế dedup những chunks lặp và xóa các phiên bản cũ khi tài liệu cập nhật.

## 26. Java Sync Driver: truy vấn ANN

Java Sync Driver có thể gửi raw `$vectorSearch` aggregation stage bằng `Document`, phù hợp minh họa rõ syntax và không phụ thuộc vào một helper builder cụ thể.

Giả định `client` là `MongoClient` đã kết nối cluster có Vector Search và index đã READY:

~~~java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import org.bson.Document;
import org.bson.conversions.Bson;

import java.util.Arrays;
import java.util.List;

MongoDatabase database =
    client.getDatabase("vector_search_lab");

MongoCollection<Document> chunks =
    database.getCollection("knowledgeChunks");

List<Double> queryVector = Arrays.asList(
    1.0, 0.0, 0.0
);

Bson searchStage = new Document("$vectorSearch",
    new Document("index", "embedding_v1")
        .append("path", "embedding")
        .append("queryVector", queryVector)
        .append("numCandidates", 100)
        .append("limit", 5)
        .append("filter",
            new Document("tenantId", "tenant-A")
                .append("published", true)
        )
);

Bson projectionStage = new Document("$project",
    new Document("_id", 1)
        .append("title", 1)
        .append("category", 1)
        .append("score",
            new Document("$meta", "vectorSearchScore")
        )
);

for (Document doc : chunks.aggregate(
        Arrays.asList(searchStage, projectionStage))) {
    System.out.println(doc.toJson());
}
~~~

### 26.1. Query vector là mảng số

Dùng `List<Double>` thay vì một chuỗi text `"[1,0,0]"`. Với định dạng BSON vector subtype/BinData, phải dùng đúng APIs codec/driver tương thích, không tự nén mảng thành bytes tùy ý.

### 26.2. Dùng embeddings thật trong production

Ở ứng dụng thật, không dùng vector thủ công `[1,0,0]`. Backend cần tạo query embedding bằng cùng model với corpus, kiểm tra dimensions và chỉ đưa vector hợp lệ cho MongoDB.

### 26.3. ENN trong Java

~~~java
Bson exactStage = new Document("$vectorSearch",
    new Document("index", "embedding_v1")
        .append("path", "embedding")
        .append("queryVector", queryVector)
        .append("exact", true)
        .append("limit", 5)
);
~~~

ENN dùng `exact:true`, không cần `numCandidates`.

### 26.4. Deadline và lỗi

Ở production, đặt timeouts/deadlines phù hợp với `AggregateIterable`/driver và có metrics. Không tự chuyển mọi exception thành danh sách rỗng; phân biệt index missing, invalid dimension, timeout và overload.

## 27. Java tạo Vector Search index

Có thể dùng driver helper quản lý search indexes nếu phiên bản hỗ trợ, hoặc dùng raw command `createSearchIndexes`.

Ví dụ raw BSON command:

~~~java
import org.bson.Document;
import java.util.Arrays;

Document definition = new Document("fields",
    Arrays.asList(
        new Document("type", "vector")
            .append("path", "embedding")
            .append("numDimensions", 3)
            .append("similarity", "cosine"),
        new Document("type", "filter")
            .append("path", "tenantId"),
        new Document("type", "filter")
            .append("path", "published")
    )
);

Document command = new Document(
        "createSearchIndexes", "knowledgeChunks")
    .append("indexes", Arrays.asList(
        new Document("name", "embedding_v1")
            .append("type", "vectorSearch")
            .append("definition", definition)
    ));

database.runCommand(command);
~~~

Chỉ chạy khi deployment/driver hỗ trợ command, index chưa tồn tại và có quyền. Index được tạo bất đồng bộ, phải kiểm tra READY trước truy vấn.

**Đừng nhầm:** `chunks.createIndex(new Document("embedding",1))` tạo ordinary index, không phải Vector Search index.

## 28. Compass và Atlas UI

Quy trình quan sát:

1. Kết nối vào Atlas cluster hoặc deployment có Vector Search.
2. Mở database `vector_search_lab`.
3. Mở collection `knowledgeChunks`.
4. Tạo index `embedding_v1` loại Vector Search.
5. Chọn path `embedding`, numDimensions 3, similarity cosine.
6. Thêm filter fields tenantId, published.
7. Đợi index READY/queryable.
8. Mở Aggregations, đặt `$vectorSearch` ở stage đầu.
9. Thử ANN numCandidates=100/limit=3.
10. Thử ENN exact=true/limit=3.
11. Project `vectorSearchScore` và đối chiếu kết quả.
12. Dùng filter tenant-A/published, so số docs còn lại.

UI thay đổi theo phiên bản; nếu Compass không expose một option mới, dùng mongosh hoặc JSON editor tương ứng. Đừng dựa vào ảnh chụp UI cũ để khẳng định API không hỗ trợ.

## 29. Giới hạn của $vectorSearch trong aggregation

- `$vectorSearch` phải là stage **đầu tiên** trong pipeline mà nó xuất hiện.
- Không đặt trong `$facet` pipeline.
- Không dùng trong `$lookup` sub-pipeline; nếu môi trường hỗ trợ, có thể join **sau** khi vector search trả kết quả.
- Filter bên trong `$vectorSearch` chỉ hỗ trợ operators/data types được tài liệu chỉ định.
- Tên `index` phải khớp index loại `vectorSearch`, `path` phải là indexed vector field.
- Không dùng `$meta:"textScore"` thay cho `"vectorSearchScore"`.
- Giới hạn với views phụ thuộc server version; không áp dụng lệnh trên những deployment chưa hỗ trợ.
- Các tính năng nested vectors, flat indexing và Automated Embedding cần đối chiếu docs đúng phiên bản.

Ví dụ không hợp lệ:

~~~javascript
db.knowledgeChunks.aggregate([
  {
    $facet: {
      semantic: [
        {
          $vectorSearch: {
            index: "embedding_v1",
            path: "embedding",
            queryVector: [1, 0, 0],
            numCandidates: 100,
            limit: 3
          }
        }
      ]
    }
  }
]);
~~~

Muốn hybrid/multiple searches, cân nhắc các pipelines riêng, fusion stages được version hỗ trợ hoặc hợp nhất ở application layer.

## 30. Ví dụ thiết kế theo workload

### 30.1. Search tri thức nội bộ

~~~text
Corpus: 2 triệu chunks
Filter: tenant + published
limit: 10
SLO: latency thấp, recall đủ cao
~~~

Bắt đầu HNSW ANN `numCandidates:200` rồi so 100, 400, 800 bằng ENN baseline và p95 latency.

### 30.2. Query trên tập nhỏ sau ACL

~~~text
Corpus toàn cluster: 5 triệu vectors
Sau filter user: 120 vectors
limit: 10
~~~

ENN hoặc flat index (nếu version hỗ trợ) đáng thử vì subset nhỏ, nhưng vẫn phải đo thực tế.

### 30.3. Legal review

Yêu cầu tránh bỏ sót cao: tăng retrieval breadth, thử ENN, kết hợp keyword exact và manual review. Không dựa vào vector score để chứng nhận tài liệu “không liên quan pháp lý”.

### 30.4. Ecommerce

Filter cần inStock/category/store, vector search xếp thứ tự semantic trong tập hợp sản phẩm hợp lệ. Kiểm tra stock/price và quyền trước khi hiển thị hoặc mua, vì search index có thể có độ trễ.

### 30.5. RAG hỗ trợ khách hàng

ANN limit=30–50, reranker giữ 5–10 chunks, LLM có nguồn tham chiếu. Benchmark end-to-end latency gồm embedding time + retrieval + reranking + generation.

## 31. Hiểu nhầm và lỗi phổ biến

| Hiện tượng | Nguyên nhân | Hướng xử lý |
|---|---|---|
| `$vectorSearch` không hoạt động | Deployment chưa hỗ trợ | Kiểm tra Search/Vector Search service |
| “Index not found” | Sai tên, type hoặc chưa build | Kiểm tra getSearchIndexes |
| `find` thấy nhưng vector search chưa thấy | Search index sync lag | Chờ READY/sync, fallback phù hợp |
| Query vector 2 chiều, index 3 chiều | Sai numDimensions | Validate trước gửi |
| Cosine và zero vector | Norm bằng 0 | Chặn zero vectors |
| DotProduct với BYO chưa normalize | Sai contract/similarity | Chuẩn hóa unit length |
| ANN thiếu numCandidates | Thiếu trường bắt buộc | Chỉ định numCandidates |
| numCandidates < limit | Không hợp lệ | Điều chỉnh |
| numCandidates > 10000 | Vượt giới hạn | Điều chỉnh/tách trang |
| `exact:true` kèm logic ANN | Nhầm ENN/ANN | Bỏ candidate tuning |
| `$match` trước `$vectorSearch` | Sai vị trí stage | Dùng pre-filter |
| Filter tenant không được index | Thiếu type filter | Bổ sung index field |
| Kết quả ít hơn limit | Tập lọc ít, thiếu vectors, post-filter | Kiểm tra completeness/filter |
| Post-filter mất nhiều kết quả | Top-k đã được chọn toàn corpus | Pre-filter đúng scope |
| Score 0.9 nhưng trả lời sai | Score không là xác suất | Human eval/rerank |
| Một model bị lẫn versions | Vectors khác space | Dual indexing/versioning |
| Quantization làm tụt recall | Mất precision | So float ENN baseline |
| p95 tăng | Candidates lớn, filter chặt, load | Benchmark, flat/ENN, scale |
| Index quá lớn | Chiều lớn, nhiều chunks, HNSW overhead | Quantization, data lifecycle |
| API lộ dữ liệu tenant khác | ACL thiếu | Kiểm tra trước retrieval/LLM |
| So score vector với text trực tiếp | Không cùng thang | Rank fusion/normalization |
| Lỗi overload | Hạ tầng quá tải | Backpressure, retry giới hạn |
| Không lấy được score | Dùng textScore hoặc không project | Dùng vectorSearchScore |
| Tạo B-tree index trên embedding | Sai loại index | Dùng vectorSearch search index |
| Query embedding từ model mới | Không cùng space index | Giữ model version nhất quán |
| Trả cả vector field về client | Không project | Chỉ trả fields cần thiết |

## 32. Bài tập thực hành

Các bài dùng collection `vector_search_lab.knowledgeChunks` và index `embedding_v1` khi không ghi rõ khác. Không dùng production để tạo/xóa index theo bài.

### Bài 1 — Vector dimensions

Index `numDimensions:3`. Query nào hợp lệ?

~~~javascript
[1,0,0]
[1,0]
[1,0,0,0]
~~~

**Đáp án:** Chỉ vector 3 chiều.

### Bài 2 — Khác biệt cosine/dot/Euclidean

Cho a=[1,0], b=[2,0]. Tính cả ba metric và giải thích khác nhau về magnitude.

### Bài 3 — Vector zero

Vì sao [0,0,0] không phù hợp với cosine?

### Bài 4 — Tạo index

Tạo `vectorSearch` index 3 chiều, path embedding, similarity cosine, có filter tenantId/published.

### Bài 5 — ANN

Viết `$vectorSearch` với q=[1,0,0], limit=5, numCandidates=100 và projection title/score.

### Bài 6 — ENN

Viết query `exact:true`, limit=5. Vì sao không cần numCandidates?

### Bài 7 — Giới hạn numCandidates

Nếu `limit:10,numCandidates:8` thì có hợp lệ không? Vì sao?

### Bài 8 — Heuristic 20×

Cho limit=20, đề xuất numCandidates ban đầu và giải thích vì sao phải benchmark.

### Bài 9 — Pre-filter

Chỉ trả tài liệu tenant-A đã published. Filter nào phải xuất hiện và index cần khai báo gì?

### Bài 10 — Post-filter mất top-k

ANN toàn corpus trả 10, sau lọc tenant-A còn 1. Vì sao không đơn giản chạy `limit:10` là đủ?

### Bài 11 — vectorSearchScore

Score 0.85 có phải xác suất 85% đúng không? Vì sao?

### Bài 12 — Cosine normalization

Cosine=0.6 cho normalized score bao nhiêu?

**Đáp án:** 0.8.

### Bài 13 — Euclidean normalization

Distance=3 cho score bao nhiêu?

**Đáp án:** 0.25.

### Bài 14 — Dot product

Tại sao BYO vectors dùng dotProduct phải normalize? Nếu norm 1 thì dot product liên hệ thế nào với cosine?

### Bài 15 — Recall@5

ENN trả [A,B,C,D,E], ANN trả [A,C,E,F,G]. Recall@5 bằng bao nhiêu?

**Đáp án:** 0.6.

### Bài 16 — Benchmark ANN

Với corpus lớn, chạy numCandidates=50/100/200/400. So recall@k với ENN và p95 latency.

### Bài 17 — Quantization

Vì sao scalar quantization giảm RAM nhưng có thể đổi top-k? Baseline phù hợp là gì?

### Bài 18 — 8.192 dimensions

Nếu model tạo 10.000 chiều, có thể lưu vector đó vào index với limit 8.192 không? Phải thay đổi lựa chọn nào?

### Bài 19 — Model version

Hai models cùng 1.536 chiều nhưng khác training. Vì sao không được tự trộn vectors?

### Bài 20 — Chunking

Khi nào nên chia tài liệu dài? Trade-off giữa retrieval precision, context loss và index size?

### Bài 21 — Freshness

Vì sao `find()` đọc được document mới nhưng `$vectorSearch` chưa thấy? Nên thông báo gì trong UI?

### Bài 22 — Java ANN

Dùng `new Document("$vectorSearch",...)` với numCandidates/limit và `$project` score.

### Bài 23 — Java ENN

Đổi ví dụ Java ANN sang exact=true. Trường nào cần bỏ?

### Bài 24 — Flat vs HNSW

5 triệu vectors, mỗi user chỉ nhìn 100 vectors. Vì sao flat/ENN có thể đáng thử, nhưng không phải lựa chọn luôn đúng?

### Bài 25 — Hybrid

Mã lỗi `ERR-4012` cần khớp chính xác. Vì sao vector-only có thể bỏ sót? Đề xuất lexical+vector+RRF.

### Bài 26 — ACL

User tenant-A hỏi về chủ đề mà tenant-B có tài liệu score cao. Query phải làm gì trước khi trả chunk cho LLM?

### Bài 27 — Threshold

Tại sao threshold 0.85 không dùng chung cho mọi model và mọi metric?

### Bài 28 — Chi phí

Tính dung lượng số thô của 100.000 vectors có 1.536 chiều float32.

**Gợi ý:** 100000 × 1536 × 4 bytes.

### Bài 29 — Index not ready

Một request timeout trong khi index build. Nên retry vô hạn hay có chiến lược status/backoff? Vì sao?

### Bài 30 — Thiết kế end-to-end

Thiết kế RAG đa tenant có source docs, chunks, embeddings version, vector index/filter, ANN/ENN tuning, score threshold, hybrid/reranking, ACL, index freshness và recall evaluation.

## 33. Bảng quyết định nhanh

| Mục tiêu | Lựa chọn ban đầu | Cần xác minh |
|---|---|---|
| Semantic search corpus lớn | HNSW ANN | Recall, latency |
| Rất ít vectors sau filter | ENN/flat nếu hỗ trợ | Query performance |
| Kết quả top-10 | `limit:10` | Filter scope |
| Candidates thử đầu | `numCandidates:200` | Recall@10 |
| Benchmark ground truth | `exact:true` | Cùng corpus/filter |
| Model unit-normalized | DotProduct/cosine theo model | Metric training |
| Vectors không normalize | Cosine/Euclidean theo model | Không dùng dot sai yêu cầu |
| Multi-tenant security | Pre-filter tenant/ACL | Indexed filter fields |
| Tiết kiệm RAM | Scalar/binary quantization | Recall và index size |
| Cần khớp mã chính xác | Hybrid lexical+vector | Fusion quality |
| Model mới | Dual fields/indexes | Dimension và rollback |
| Vừa insert chưa thấy | Theo dõi Search index sync | Index readiness |
| RAG đa ngôn ngữ | Model embeddings đa ngôn ngữ | Relevance tiếng Việt |
| Score threshold | Hiệu chỉnh theo dữ liệu | Precision/recall |

## 34. Checklist production

### Embeddings và dữ liệu

- [ ] Document/query embeddings cùng model và version tương thích.
- [ ] Mọi vector đúng dimensions và numeric type.
- [ ] Không có NaN/Infinity/zero vector khi metric không cho phép.
- [ ] Nếu dotProduct BYO, đã normalize unit length.
- [ ] Có dữ liệu mẫu kiểm thử tiếng Việt hoặc đa ngôn ngữ thực tế.
- [ ] Có chunking/dedup/versioning lifecycle.
- [ ] Không trộn hai embedding spaces một cách âm thầm.

### Index

- [ ] Đúng loại index `vectorSearch`, không phải B-tree.
- [ ] `path`, `numDimensions`, `similarity` đúng.
- [ ] Index READY/queryable.
- [ ] Fields lọc tenant/ACL/status đã được index `type:"filter"`.
- [ ] Đã benchmark quantization/indexingMethod nếu có.
- [ ] Có metrics index size, sync lag, load và build time.
- [ ] Có rollback plan khi đổi model/index.

### Truy vấn

- [ ] `$vectorSearch` là stage đầu tiên.
- [ ] ANN có `numCandidates >= limit` và không quá giới hạn.
- [ ] ENN dùng `exact:true`.
- [ ] `limit` phù hợp dữ liệu và UX.
- [ ] Pre-filter quyền được lấy từ identity đã xác thực.
- [ ] Chỉ project các fields cần thiết, không trả embedding mặc định.
- [ ] Dùng `vectorSearchScore` đúng tên.
- [ ] Không hiểu score là xác suất hoặc thang chung mọi model.
- [ ] Có recall@k vs ENN, precision/NDCG và p95 latency.
- [ ] Có maxTime/backpressure và xử lý lỗi phân loại.

### Vận hành/RAG

- [ ] Không gửi dữ liệu trái quyền đến reranker hoặc LLM.
- [ ] Có kiểm tra quyền lại khi fetch tài liệu gốc.
- [ ] Có cơ chế xử lý document bị xóa/đổi quyền.
- [ ] Có trạng thái indexing lag cho dữ liệu mới.
- [ ] Có limits cho query size/candidates/page size.
- [ ] Có giám sát Search Node load và lỗi overload.
- [ ] Có đánh giá hybrid search khi chứa mã/tên chính xác.
- [ ] Có kiểm tra hallucination và nguồn dẫn trong câu trả lời RAG.
- [ ] Deployment/version hỗ trợ Vector Search được xác minh.
- [ ] Đã benchmark trên workload representative, không chỉ 8 vectors lab.

## 35. Tổng kết

Tìm kiếm vector trong MongoDB là chuỗi quyết định kỹ thuật liên kết với nhau:

1. **Embedding space:** vectors của documents và queries phải đến từ model/version tương thích.
2. **Vector index:** dùng loại `vectorSearch`, khai báo path, numDimensions, similarity và filter fields.
3. **Similarity metric:** cosine đo góc; dotProduct đo tích vô hướng và yêu cầu normalize BYO vectors; Euclidean đo khoảng cách.
4. **ANN:** HNSW tìm xấp xỉ và dùng `numCandidates` đánh đổi latency/recall; 20×limit là heuristic ban đầu, không phải lời bảo đảm.
5. **ENN:** `exact:true` giúp tìm hàng xóm gần chính xác theo indexed vectors và là baseline để đo ANN.
6. **Score:** `vectorSearchScore` trong khoảng 0–1 là tín hiệu xếp hạng, không phải xác suất trả lời đúng.
7. **Filter:** tenant/ACL/status nên được áp trước retrieval và phải có filter fields tương ứng trong index.
8. **Hiệu năng:** dimension, số chunks, quantization, HNSW/flat, index freshness và concurrency quyết định chi phí thực.
9. **Chất lượng sản phẩm:** đánh giá recall, precision, latency, dữ liệu tiếng Việt/đa ngôn ngữ và grounding của RAG.

Chọn đúng **embedding → index → metric → filter → ANN/ENN parameters → đánh giá thực nghiệm** giúp hệ thống MongoDB Vector Search vừa hữu ích vừa có thể kiểm soát chi phí, bảo mật và chất lượng.

## Tài liệu tham khảo chính thức

- [MongoDB Vector Search Overview](https://www.mongodb.com/docs/vector-search/)
- [MongoDB — How to Index Fields for Vector Search](https://www.mongodb.com/docs/vector-search/indexes/vector-search-type/)
- [MongoDB — Run Vector Search ANN and ENN Queries](https://www.mongodb.com/docs/vector-search/query/aggregation-stages/vector-search-stage/)
- [MongoDB — Vector Search Query Accuracy](https://www.mongodb.com/docs/vector-search/query/measure-accuracy/)
- [MongoDB — Vector Quantization](https://www.mongodb.com/docs/vector-search/about/vector-quantization/)
- [MongoDB — Explain Vector Search Results](https://www.mongodb.com/docs/vector-search/query/explain/)
- [MongoDB Manual — createSearchIndex](https://www.mongodb.com/docs/manual/reference/method/db.collection.createsearchindex/)
- [MongoDB Manual — getSearchIndexes](https://www.mongodb.com/docs/manual/reference/method/db.collection.getsearchindexes/)
- [MongoDB — Benchmark Overview](https://www.mongodb.com/docs/vector-search/benchmark/overview/)
- [MongoDB Search and Vector Search Changelog](https://www.mongodb.com/docs/atlas/search-changelog/)
- [MongoDB — Hybrid Search](https://www.mongodb.com/docs/vector-search/tutorials/reciprocal-rank-fusion/)
- [MongoDB Java Sync Driver — Aggregation](https://www.mongodb.com/docs/drivers/java/sync/current/aggregation/)
