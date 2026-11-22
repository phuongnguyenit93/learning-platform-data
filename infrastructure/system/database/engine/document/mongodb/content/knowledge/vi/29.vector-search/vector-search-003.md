# Thiết kế trường vector, số chiều và metadata đi kèm trong MongoDB Vector Search

**Tìm kiếm vector (vector search)** cho phép ứng dụng tìm nội dung có ý nghĩa tương tự nhau dù cách dùng từ khác nhau. Mỗi đoạn văn, sản phẩm hoặc đối tượng được biến thành một **embedding**: dãy số do mô hình học máy tạo ra. MongoDB có thể lập chỉ mục vector và tìm những vector gần query vector theo metric tương đồng đã chọn.

Thiết kế vector search bền vững không chỉ là thêm một field embedding vào document. Cần đảm bảo **số chiều đúng, giá trị số hợp lệ, model nhất quán, metadata đủ để lọc đúng quyền và trạng thái**, cùng quy trình cập nhật khi nội dung hoặc model thay đổi. Một hệ thống có vector index hoạt động nhưng metadata tenant thiếu có thể trả dữ liệu ngoài phạm vi; một embedding 768 chiều của model A không tự tương thích với embedding 768 chiều của model B.

Bài học trong chương **Tìm kiếm vector**, module **Database Engine Document MongoDB**, tập trung vào:

1. Cấu trúc field vector trong MongoDB, các kiểu dữ liệu/encoding và kích thước vector.
2. Vai trò của số chiều (dimensions), embedding model, preprocessing, normalization và similarity metric.
3. Metadata phục vụ filtering, phân quyền, nguồn tài liệu, chunking, model version, freshness và re-embedding.
4. Khai báo Atlas Vector Search index có vector field và filter fields; truy vấn bằng $vectorSearch.
5. Ingestion, idempotency, migration model, theo dõi chất lượng và ví dụ MongoDB Java Sync Driver.
6. Bài tập thực hành và checklist thiết kế.

**Phạm vi:** Ví dụ sử dụng mô hình cú pháp **MongoDB Atlas Vector Search** phổ biến. Khả năng hỗ trợ của $vectorSearch, kiểu lưu vector, quantization, operators và cách tạo search index phụ thuộc sản phẩm và phiên bản đang chạy. Kiểm tra tài liệu release/triển khai trước khi áp dụng cho production. Những vector ngắn bốn chiều trong bài chỉ để minh họa cấu trúc, **không phải embedding ngữ nghĩa thật**.

## 1. Luồng xử lý vector search

Một hệ thống có hai luồng riêng.

~~~text
INDEXING

Document / Product / Image
        |
        v
  Clean and normalize
        |
        v
  Chunk (nếu cần)
        |
        v
  Embedding model
        |
        v
  Numeric vector
        |
        v
  Validate dimensions
        |
        v
  Save vector + metadata
        |
        v
  Vector Search index


QUERYING

User query
        |
        v
  Same preprocessing contract
        |
        v
  Same compatible embedding model
        |
        v
  Query vector
        |
        v
  $vectorSearch + trusted filters
        |
        v
  Top-k candidates + scores
        |
        v
  Authorization check / reranking
        |
        v
  Display answer and citations
~~~

Ví dụ câu hỏi:

~~~text
"Tôi muốn đổi giờ nhận xe"
~~~

và một tài liệu:

~~~text
"Hướng dẫn thay đổi thời gian nhận xe sau khi đặt"
~~~

có thể có embeddings gần nhau nếu model học được quan hệ ngữ nghĩa đó.

### 1.1. Vector khác keyword

Một embedding thường là dãy:

~~~text
[0.12, -0.08, 0.35, 0.04, ...]
~~~

Dấu ba chấm chỉ biểu diễn những thành phần bị lược đi khi trình bày. Vector lưu thật không được chứa dấu ba chấm hoặc string thay số.

Các chiều không tương ứng trực tiếp với từng thuộc tính tường minh như:

~~~text
dimension 0 = loại xe
dimension 1 = tên khách
dimension 2 = ngày đặt
~~~

Thông tin ngữ nghĩa thường được phân bố trên toàn bộ không gian vector.

### 1.2. Vector search không thay lookup ID

Tìm mã đơn hàng, số hợp đồng hoặc ID khách hàng thường cần exact match hoặc index thông thường. Embedding không được xem là biện pháp so khớp chính xác với những mã định danh.

### 1.3. Retrieval không đồng nghĩa xác minh nội dung

Một tài liệu có score cao có thể lỗi thời, ngoài quyền người dùng hoặc chứa thông tin sai. Search score đánh giá liên quan vector; nguồn và chính sách nghiệp vụ vẫn phải được kiểm tra.

## 2. Các thuật ngữ chính

| Thuật ngữ | Ý nghĩa |
| --- | --- |
| Embedding | Vector số mô tả một đầu vào |
| Embedding model | Mô hình sinh vector |
| Dimensions | Số thành phần của vector |
| Embedding space | Hệ biểu diễn vector của model và pipeline |
| Normalization | Chuyển đổi vector theo quy tắc về độ dài |
| Similarity metric | Cách so sánh hai vectors |
| ANN | Approximate Nearest Neighbor |
| Top-k | Số kết quả ứng viên được yêu cầu |
| numCandidates | Độ rộng tập ứng viên trong ANN search |
| Metadata | Field thông thường về quyền, nguồn, version và trạng thái |
| Pre-filter | Filter được áp dụng trong bước vector retrieval khi được hỗ trợ |
| Chunk | Đoạn tài liệu tạo một embedding |
| Re-embedding | Tạo vector lại do thay nội dung hoặc model |
| Retrieval score | Điểm xếp hạng do search engine cung cấp |

Một document MongoDB có thể chứa một vector hoặc nhiều vector fields. Một tài liệu nguồn cũng có thể được tách thành nhiều documents, mỗi document chứa embedding của một chunk.

## 3. Schema đơn giản nhất

Ví dụ field vector:

~~~javascript
{
  _id: "article-001",
  title: "Đổi giờ nhận xe",
  content: "Khách có thể điều chỉnh lịch nhận xe...",
  embedding: [0.12, -0.08, 0.35, 0.04]
}
~~~

Đây là vector **4 chiều**.

### 3.1. Vì sao schema này chưa đủ?

Khi tìm được một vector gần query, ứng dụng cần biết:

- Vector được tạo từ model nào?
- Tài liệu thuộc tenant nào?
- Người dùng có quyền xem không?
- Bài viết đã published chưa?
- Nội dung hiện tại có giống nội dung lúc tạo embedding không?
- Nguồn tài liệu có thể mở ở đâu?
- Nếu tài liệu dài, hit thuộc trang/chunk nào?

Không có những metadata này, vector search khó vận hành ở quy mô production.

### 3.2. Schema dành cho từng chunk

~~~javascript
{
  _id: "tenant-a:doc-001:v3:chunk-0001",
  tenantId: "tenant-a",
  documentId: "doc-001",
  documentVersion: 3,
  chunkId: "chunk-0001",
  chunkIndex: 1,
  title: "Quy trình đổi lịch",
  content: "Khách hàng có thể chuyển lịch nhận xe...",
  sourceType: "help_article",
  sourceUri: "/help/change-booking",
  language: "vi",
  category: "booking",
  status: "published",
  accessLevel: "public",
  embedding: [0.12, -0.08, 0.35, 0.04],
  embeddingInfo: {
    provider: "example-provider",
    model: "demo-model",
    modelVersion: "v1",
    dimensions: 4,
    normalized: false,
    preprocessingVersion: 2,
    chunkingVersion: 1,
    contentHash: "sha256:..."
  },
  createdAt: ISODate("2026-11-01T09:00:00Z"),
  updatedAt: ISODate("2026-11-14T09:00:00Z")
}
~~~

Các giá trị là dữ liệu minh họa. Trong môi trường thật, embedding phải được tạo từ model được chọn và metadata phải khớp output/pipeline thực tế.

## 4. Chia metadata thành các nhóm

| Nhóm | Field ví dụ | Công dụng |
| --- | --- | --- |
| Identity | _id, documentId, chunkId | Định danh, upsert, dedup |
| Source | sourceUri, title, section, page | Tìm lại tài liệu và trích dẫn |
| Content | content | Hiển thị hoặc reranking |
| Scope | tenantId, projectId | Giới hạn nguồn dữ liệu |
| Authorization | accessLevel, allowedGroups | Chặn dữ liệu ngoài quyền |
| Publishing | status, publishedAt | Chỉ trả nội dung hợp lệ |
| Classification | language, category, sourceType | Lọc corpus |
| Embedding | embedding | Vector search |
| Model | model, modelVersion, dimensions | Tương thích embedding space |
| Pipeline | preprocessingVersion, chunkingVersion | Tái lập và backfill |
| Freshness | sourceUpdatedAt, indexedAt, contentHash | Phát hiện dữ liệu stale |
| Operations | embeddingStatus, retryCount | Giám sát ingestion |

Không phải hệ thống nào cũng cần mọi field. Nhưng identity, tenant/access, source traceability, model/version và trạng thái thường là các nhóm quan trọng nhất.

## 5. Đặt tên và vị trí field vector

Tên thường gặp:

~~~text
embedding
vector
textEmbedding
titleEmbedding
descriptionEmbedding
imageEmbedding
~~~

Nếu mỗi document chỉ có một embedding nội dung, **embedding** là tên dễ hiểu.

### 5.1. Root field

~~~javascript
{
  _id: "chunk-001",
  embedding: [0.12, -0.08, 0.35, 0.04]
}
~~~

Vector index path là **embedding**.

### 5.2. Nested field

~~~javascript
{
  _id: "chunk-001",
  vectors: {
    content: [0.12, -0.08, 0.35, 0.04]
  }
}
~~~

Index path phải là **vectors.content**. Nếu index tìm embedding ở root, nó không tự theo dõi path lồng này.

### 5.3. Nhiều vector fields

~~~javascript
{
  _id: "product-001",
  title: "Máy ảnh du lịch",
  description: "Máy ảnh nhỏ gọn...",
  titleEmbedding: [0.2, -0.1, 0.3, 0.1],
  descriptionEmbedding: [0.1, 0.4, -0.1, 0.3]
}
~~~

Cần xác định mỗi field dùng model nào, dimensions nào, metric nào và query nào. Không dùng một query vector với mọi field nếu những field đó ở các embedding spaces khác nhau.

### 5.4. Không lưu numeric array thành string

Sai:

~~~javascript
embedding: "[0.12,-0.08,0.35,0.04]"
~~~

Đây là string. Khi nhận JSON từ API cần parse thành các thành phần numeric theo định dạng index/driver hỗ trợ.

## 6. Dimensions là gì?

Một vector:

~~~text
[0.12, -0.08, 0.35, 0.04]
~~~

có **4 chiều** vì có bốn phần tử.

Một model tạo 768 số sẽ có output vector 768 chiều. Một model tạo 1.536 số sẽ có output 1.536 chiều.

### 6.1. Các nơi phải khớp số chiều

~~~text
Embedding model output:  D chiều
Stored vector:           D chiều
Vector index:            numDimensions = D
Query vector:            D chiều
~~~

Bất kỳ thành phần nào không khớp đều có thể khiến indexing/query lỗi hoặc dữ liệu không hợp lệ.

### 6.2. Ví dụ sai số chiều

Index:

~~~javascript
{
  type: "vector",
  path: "embedding",
  numDimensions: 4,
  similarity: "cosine"
}
~~~

Vector đúng chiều:

~~~javascript
[0.1, 0.2, 0.3, 0.4]
~~~

Vector thiếu chiều:

~~~javascript
[0.1, 0.2, 0.3]
~~~

Query vector thừa chiều:

~~~javascript
[0.1, 0.2, 0.3, 0.4, 0.5]
~~~

Đừng suy rằng document đã insert thành công là vector chắc chắn được search index chấp nhận. Cần validation tại ingestion.

### 6.3. Có nên pad số 0?

Không tự nối zeros để đạt numDimensions:

~~~text
Model trả 3 chiều -> [0.1,0.2,0.3]
Tự pad thành 4    -> [0.1,0.2,0.3,0.0]
~~~

Điều đó không tạo ra một embedding đúng từ model bốn chiều. Nếu dùng kỹ thuật biến đổi vector hợp lệ do model cung cấp, phải áp dụng nhất quán cả indexing và query, có version riêng.

### 6.4. Có nên cắt chiều?

Không tự cắt 768 chiều xuống 512 rồi nghĩ rằng model sẽ giữ nguyên quality. Chỉ dùng kỹ thuật dimensionality reduction/rút ngắn embedding khi model và pipeline đã được thiết kế, đánh giá và kiểm soát rõ.

## 7. Model ID quan trọng không kém dimensions

Hai model có thể đều trả vector 768 chiều nhưng ở **hai embedding spaces khác nhau**.

~~~text
Embedding X: 768 values từ model A
Embedding Y: 768 values từ model B

Cùng số chiều ≠ cùng ý nghĩa hệ tọa độ
~~~

### 7.1. Vì sao trộn model nguy hiểm?

- Similarity score giữa A và B có thể vô nghĩa.
- Top-k ranking khó giải thích.
- Một nhóm tài liệu có thể bị ưu tiên hoặc bị bỏ qua.
- Re-ranking không sửa được một tập ứng viên đầu vào thiếu thông tin.
- Không thể quy trách nhiệm khi chất lượng retrieval giảm.

### 7.2. Những chiến lược tách biệt

- Một model/version cho một vector field và index.
- Hai collections riêng khi migration lớn.
- Hai fields embeddingV1 và embeddingV2.
- Hai indices ứng với paths tương ứng.
- Query bằng model/version phù hợp với index đang được chọn.

Có thể lưu modelVersion làm metadata filter, nhưng **filter không tự biến embeddings từ hai model thành cùng một không gian so sánh**.

### 7.3. Pin model version

Nếu provider hỗ trợ model revision hoặc deployment ID, lưu thông tin đó. Một tên endpoint chung có thể thay đổi implementation theo thời gian nếu không được pin.

## 8. Lựa chọn số chiều theo chất lượng và chi phí

Dimensions ảnh hưởng:

- Storage BSON/vector.
- Search index footprint.
- Network payload.
- Tốc độ embedding inference.
- Search compute/latency.
- Khả năng giữ dữ liệu trong memory.
- Chi phí re-embedding khi thay model.

### 8.1. Ước tính dung lượng thô

Nếu float32 dùng 4 byte/số:

\[
\text{rawBytesPerVector} \approx 4 \times D
\]

| Số chiều | Float32 raw bytes mỗi vector |
| ---: | ---: |
| 384 | 1.536 |
| 768 | 3.072 |
| 1.536 | 6.144 |
| 3.072 | 12.288 |

Đây **không phải dung lượng BSON hoặc Atlas Vector Search index thực tế**; chưa tính encoding, metadata, ANN structure, replication, backup và index overhead.

### 8.2. Số chunks nhân số vector

Nếu 500.000 tài liệu, trung bình 8 chunks/tài liệu:

~~~text
500.000 documents
x 8 chunks/document
= 4.000.000 vectors
~~~

Tổng chi phí phụ thuộc số vectors thực, không chỉ số tài liệu nguồn.

### 8.3. Model nhiều chiều không luôn tốt hơn

Một model 384 chiều có thể phù hợp hơn một model 1.536 chiều nếu nó tốt hơn trên dữ liệu chuyên ngành, hỗ trợ ngôn ngữ, hoặc có latency/cost tốt hơn.

Hãy đánh giá theo tập câu hỏi thật và metrics như recall@k, MRR, nDCG, latency, cost.

### 8.4. Giới hạn dịch vụ

Mỗi phiên bản/loại MongoDB Vector Search index có giới hạn về dimensions, loại vector, quantization và cấu hình. Không mặc định một model có số chiều bất kỳ sẽ được hỗ trợ.

## 9. Kiểu số và lưu vector

Một embedding có thể được lưu như numeric array:

~~~javascript
{
  embedding: [0.12, -0.08, 0.35, 0.04]
}
~~~

Tùy driver, các giá trị có thể được serialize thành BSON doubles hoặc kiểu numeric khác. Một số MongoDB releases có thêm BSON vector representation/quantization.

### 9.1. Những dữ liệu cần từ chối

~~~javascript
[0.1, null, 0.3, 0.4]        // có null
[0.1, NaN, 0.3, 0.4]         // NaN
[0.1, Infinity, 0.3, 0.4]    // không hữu hạn
["0.1", "0.2", "0.3", "0.4"] // strings
[0.1, 0.2, 0.3]              // thiếu chiều
~~~

Một ingestion pipeline không nên tạo zero vector để thay lỗi embedding, rồi đánh dấu ready.

### 9.2. Float32 và double

- Float32: 4 byte/số trong biểu diễn float.
- Double: 8 byte/số.
- Int8/quantized/binary representations: có thể giảm footprint nhưng phụ thuộc tính năng hỗ trợ.

Khi dùng kiểu vector BSON hoặc quantization, kiểm tra đúng format, driver codec, subtype và index configuration. Không tự thay float[] bằng bytes và kỳ vọng index hiểu ngay.

### 9.3. Kiểm tra toàn chuỗi encoding

~~~text
Embedding SDK output
   -> conversion
   -> BSON serialization
   -> document field
   -> Vector Search index
   -> queryVector encoding
~~~

Phải thống nhất kiểu dữ liệu và số chiều.

## 10. Normalization và norm của vector

Với vector \(\mathbf{v}\) có D chiều:

\[
\|\mathbf{v}\|_2=\sqrt{\sum_{i=1}^{D} v_i^2}
\]

L2 normalization:

\[
\hat{\mathbf{v}}=\frac{\mathbf{v}}{\|\mathbf{v}\|_2}
\]

được định nghĩa khi norm khác zero.

### 10.1. Ví dụ

~~~text
v = [3,4]
norm = 5
L2 normalized = [0.6,0.8]
~~~

### 10.2. Model contract quyết định normalization

Có model đã trả unit vectors. Có model khuyến nghị normalize trước khi dùng dotProduct; có model không yêu cầu. Không nên chuẩn hóa mọi embedding thiếu cân nhắc.

### 10.3. Indexing và query phải giống nhau

Nếu dữ liệu lưu đã normalize còn query vector không normalize, mức ảnh hưởng tùy metric nhưng dễ làm scoring/behavior khó đoán. Cần một hợp đồng preprocessing/normalization duy nhất.

### 10.4. Zero vector

Zero vector có norm bằng 0. Không chia cho zero khi normalize. Nếu model trả zero vector bất thường, báo lỗi ingestion và giữ trạng thái pending/failed thay vì đưa vào index.

## 11. Cosine, dotProduct và Euclidean

Ba metric phổ biến:

### 11.1. Cosine similarity

\[
\operatorname{cosine}(\mathbf{a},\mathbf{b})=
\frac{\mathbf{a}\cdot\mathbf{b}}
{\|\mathbf{a}\|_2\|\mathbf{b}\|_2}
\]

So hướng tương đối của hai vector khác zero.

### 11.2. Dot product

\[
\mathbf{a}\cdot\mathbf{b}=\sum_{i=1}^{D}a_i b_i
\]

Phụ thuộc cả hướng và độ lớn, trừ khi vectors đã normalized theo cùng quy tắc.

### 11.3. Euclidean distance

\[
d(\mathbf{a},\mathbf{b})=
\sqrt{\sum_{i=1}^{D}(a_i-b_i)^2}
\]

Đo khoảng cách hình học.

### 11.4. Ví dụ về magnitude

~~~text
A = [1,0]
B = [2,0]
C = [0,1]
~~~

A và B cùng hướng nên cosine cao. Nhưng Euclidean A-B khác zero vì B lớn gấp đôi A. DotProduct cũng thay đổi khi scale vectors.

### 11.5. Không dùng score như xác suất

Điểm mà $vectorSearch trả về có thể được biến đổi theo scoring của công cụ. Score 0.8 không có nghĩa xác suất đúng 80%, và không mặc định bằng cosine gốc. Ngưỡng và cách giải thích phải được đánh giá với corpus/model cụ thể.

## 12. Thiết kế metadata để lọc đúng đối tượng

Giả sử các chunks có:

~~~javascript
{
  tenantId: "tenant-a",
  language: "vi",
  status: "published",
  accessLevel: "internal",
  category: "billing",
  embedding: [0.12, -0.08, 0.35, 0.04]
}
~~~

Truy vấn của một người dùng có thể cần:

- Chỉ tenant-a.
- Chỉ published.
- Chỉ language vi.
- Chỉ nội dung user được phép xem.

### 12.1. Metadata khác nội dung embedding

Không chỉ thêm dòng “tenantId: tenant-a” vào text trước khi embedding rồi kỳ vọng model sẽ xử lý phân quyền.

Tenant và authorization phải là **structured fields** được filter/kiểm tra bởi backend đáng tin cậy.

### 12.2. Field filter nên ổn định

Nếu service A ghi language="vi", service B ghi lang="vi-VN", filter có thể bỏ sót chunks. Cần chuẩn schema và enum/canonicalization.

### 12.3. Không lập chỉ mục metadata không dùng

Mỗi filter field có chi phí index và maintenance. Nên chọn các fields phục vụ truy vấn thực tế, không khai báo bừa tất cả metadata.

## 13. Tenant isolation và phân quyền

Một search service multi-tenant không được để user tự chỉ định tenant tùy ý rồi truy vấn mọi corpus.

Quy trình:

~~~text
Authenticate request
   |
   v
Resolve trusted tenant and permissions
   |
   v
Build vectorSearch pre-filter
   |
   v
Retrieve permitted candidates
   |
   v
Final authorization check
   |
   v
Send content to UI/LLM
~~~

### 13.1. Nguy cơ post-filter đơn thuần

Sai về an toàn:

~~~text
Search trên toàn cluster
   |
   v
Top-k có dữ liệu tenant khác
   |
   v
Gửi top-k vào LLM
   |
   v
UI mới lọc tenant
~~~

Ở bước lọc UI thì dữ liệu ngoài quyền đã đi vào tầng xử lý trước đó.

### 13.2. Pre-filter và final authorization

Pre-filter giúp giảm candidate set và rủi ro lộ dữ liệu. Nếu ACL phức tạp hoặc quyền thay đổi nhanh, vẫn cần final authorization check từ nguồn dữ liệu đủ nhất quán trước khi hiển thị.

### 13.3. Quy tắc filter có giới hạn

Atlas Vector Search pre-filter hỗ trợ tập operators/kiểu dữ liệu nhất định. Không được mặc định mọi MongoDB find() operator và mọi nested-array ACL structure đều hỗ trợ như nhau.

## 14. Metadata về nguồn và trích dẫn

Một chunk có thể có:

~~~javascript
{
  documentId: "doc-123",
  documentVersion: 7,
  chunkId: "chunk-004",
  chunkIndex: 4,
  sourceType: "knowledge_base",
  sourceUri: "/docs/change-booking",
  title: "Hướng dẫn đổi lịch",
  sectionPath: ["Đặt xe", "Đổi lịch"],
  pageNumber: 5,
  charStart: 1300,
  charEnd: 1950
}
~~~

### 14.1. documentId khác chunkId

Một tài liệu có thể tạo nhiều chunks. Nếu mọi chunk dùng _id bằng documentId, sẽ đụng unique key.

### 14.2. ID ổn định

Có thể chọn:

~~~text
tenantId:documentId:documentVersion:chunkIndex
~~~

để ingestion retry cùng nội dung/version không tạo duplicate.

### 14.3. Offset và version

Khi nguồn được sửa, charStart/charEnd hoặc pageNumber có thể lệch. Gắn offset với documentVersion và đảm bảo citation trỏ về đúng tài liệu/version.

### 14.4. URI không thay quyền

Một sourceUri có thể giúp mở nguồn, nhưng cần auth. Không tự trả nội dung nhạy cảm chỉ vì link tồn tại.

## 15. Metadata về model và preprocessing

Embedding có thể được tạo qua:

~~~text
Raw source
   |
   v
Parse HTML/PDF
   |
   v
Normalize text
   |
   v
Chunk
   |
   v
Embedding model
   |
   v
Validate and store
~~~

Mỗi bước ảnh hưởng vector.

Nên lưu:

~~~javascript
embeddingInfo: {
  provider: "provider-x",
  model: "embedding-model-v3",
  modelVersion: "2026-10",
  dimensions: 768,
  normalized: true,
  preprocessingVersion: 4,
  chunkingVersion: 2,
  contentHash: "sha256:...",
  generatedAt: ISODate("2026-11-14T09:00:00Z")
}
~~~

### 15.1. Vì sao modelVersion quan trọng?

Cùng tên endpoint chưa chắc cùng model artifact qua thời gian. Pin version hoặc deployment ID nếu được hỗ trợ.

### 15.2. Vì sao preprocessingVersion quan trọng?

Thay cách loại HTML tags, gộp title hoặc xử lý khoảng trắng có thể tạo embeddings khác dù source file không đổi.

### 15.3. Vì sao chunkingVersion quan trọng?

Thay kích thước đoạn hoặc overlap có thể thay số chunks, vị trí và nội dung vector.

### 15.4. Hash có thể giảm re-embedding

Nếu normalized content hash, model version và preprocessing version đều không đổi, có thể tránh tạo lại vector không cần thiết.

Chỉ so contentHash mà bỏ qua modelVersion là không đủ.

## 16. Chunking cho tài liệu dài

Một bài viết dài nên cân nhắc nhiều chunks:

~~~text
Document: "Hướng dẫn thuê xe"
  |
  +--- Chunk 0: Điều kiện thuê
  +--- Chunk 1: Thanh toán
  +--- Chunk 2: Đổi lịch
  +--- Chunk 3: Hủy và hoàn tiền
~~~

Mỗi chunk có một embedding cùng dimensions nếu dùng cùng model.

### 16.1. Chunk size khác vector dimensions

- **Chunk size:** số ký tự/token của đoạn text.
- **Vector dimensions:** số phần tử model output.

Đoạn 100 token và 400 token đều có thể sinh vector 768 chiều từ cùng model.

### 16.2. Chunk overlap

~~~text
Chunk 0: A B C D
Chunk 1:     C D E F
Chunk 2:         E F G H
~~~

Overlap có thể giữ ngữ cảnh ở ranh giới, nhưng làm tăng số vector, storage và duplicate hits.

### 16.3. Metadata cho chunk

~~~javascript
{
  documentId: "doc-123",
  chunkId: "chunk-004",
  chunkIndex: 4,
  sectionTitle: "Đổi lịch",
  documentVersion: 7,
  sourceUri: "/docs/change-booking"
}
~~~

Giúp lấy chunk trước/sau, sắp đúng thứ tự và hiển thị citation.

### 16.4. Không cắt vô tội vạ

Cắt giữa bảng, đoạn code hoặc câu có điều kiện có thể khiến embedding mất ngữ nghĩa. Nên cân nhắc heading, sentence, Markdown/PDF structure và giới hạn token của model.

## 17. Lưu vector ở document nguồn hay collection riêng?

### 17.1. Vector trong document nguồn

~~~javascript
{
  _id: "article-001",
  title: "Hướng dẫn đổi lịch",
  content: "...",
  embedding: [0.12, -0.08, 0.35, 0.04]
}
~~~

Hợp với tài liệu ngắn, một vector cho một document.

### 17.2. Collection chunks riêng

~~~text
knowledgeDocuments
  doc-001
  doc-002

knowledgeChunks
  doc-001:v1:chunk-000
  doc-001:v1:chunk-001
  doc-002:v2:chunk-000
~~~

Phù hợp tài liệu dài, nhiều chunks và migration độc lập.

### 17.3. Đánh đổi

| Tiêu chí | Vector trong document | Chunk collection riêng |
| --- | --- | --- |
| Model đơn giản | Cao | Cần đồng bộ |
| Nhiều chunks | Khó hơn | Tự nhiên |
| Metadata ACL | Có sẵn | Cần bản sao/kiểm tra |
| Re-embedding | Gắn vào source | Tách pipeline |
| Trích dẫn theo đoạn | Có thể phức tạp | Dễ hơn |
| Xóa document | Một record | Phải cleanup chunks |

Không có mô hình duy nhất đúng cho mọi workload.

## 18. Vector của nhiều modality

Một sản phẩm có thể lưu:

~~~javascript
{
  _id: "product-001",
  titleVector: [0.12, 0.20, -0.11, 0.08],
  imageVector: [-0.12, 0.15, 0.29, 0.31]
}
~~~

Nếu hai fields từ model khác nhau, đừng dùng một query vector chung để so sánh nếu chúng không nằm trong **một multimodal embedding space được model hỗ trợ**.

### 18.1. Model metadata theo field

~~~javascript
vectorInfo: {
  title: {
    model: "text-model-v1",
    dimensions: 768
  },
  image: {
    model: "image-model-v2",
    dimensions: 512
  }
}
~~~

### 18.2. Không ghép vector tùy ý

Nối vector 768 chiều với vector 512 chiều thành 1.280 chiều không tạo ra embedding liên modality hợp lệ trừ khi có mô hình hoặc phép biến đổi được thiết kế và đánh giá rõ.

## 19. Atlas Vector Search index

Một cấu hình vector field phổ biến:

~~~javascript
{
  type: "vector",
  path: "embedding",
  numDimensions: 768,
  similarity: "cosine"
}
~~~

Ý nghĩa:

- **type: vector**: field vector.
- **path: embedding**: field thực trong document.
- **numDimensions**: số chiều bắt buộc.
- **similarity**: metric của index.

### 19.1. Tạo index qua MongoDB command

Ví dụ bốn chiều cho lab:

~~~javascript
use vector_lab

db.runCommand({
  createSearchIndexes: "knowledgeChunks",
  indexes: [
    {
      name: "vector_demo",
      type: "vectorSearch",
      definition: {
        fields: [
          {
            type: "vector",
            path: "embedding",
            numDimensions: 4,
            similarity: "cosine"
          }
        ]
      }
    }
  ]
});
~~~

**Điều kiện:** cần deployment/version hỗ trợ Atlas Vector Search và API createSearchIndexes tương ứng. Đây là cấu hình lab dùng vector bốn chiều, không phải production embedding model.

### 19.2. Vector Search index khác B-tree

Không dùng:

~~~javascript
db.knowledgeChunks.createIndex({
  embedding: 1
});
~~~

rồi kỳ vọng đó là một vector similarity index.

### 19.3. Index build không luôn tức thời

Lệnh tạo index có thể trả thành công trước khi mọi dữ liệu đã sẵn sàng phục vụ search. Theo dõi trạng thái index theo API deployment trước khi chạy kiểm chứng.

## 20. Khai báo filter fields

Một index dùng vector 768 chiều và filter metadata:

~~~javascript
db.runCommand({
  createSearchIndexes: "knowledgeChunks",
  indexes: [
    {
      name: "knowledge_vector_v1",
      type: "vectorSearch",
      definition: {
        fields: [
          {
            type: "vector",
            path: "embedding",
            numDimensions: 768,
            similarity: "cosine"
          },
          { type: "filter", path: "tenantId" },
          { type: "filter", path: "status" },
          { type: "filter", path: "language" },
          { type: "filter", path: "sourceType" }
        ]
      }
    }
  ]
});
~~~

### 20.1. Vì sao cần type filter?

Metadata có mặt trong document không tự có nghĩa nó đã được khai báo cho **$vectorSearch.filter**. Field mà ứng dụng muốn tiền lọc cần được index theo cách tương ứng.

### 20.2. Nested path

Nếu field là:

~~~javascript
{
  search: {
    status: "published"
  }
}
~~~

thì index path cần là **search.status**, không phải status ở root.

### 20.3. Chỉ khai báo trường được dùng

Một field sourceUri dùng cho citation không nhất thiết là filter field. Tránh lập index cho tất cả metadata mà không có query thực.

### 20.4. Chú ý kiểu dữ liệu

Pre-filter trong Vector Search có những kiểu và operators được hỗ trợ riêng. Không tự chuyển mọi MongoDB find() expression phức tạp vào $vectorSearch.filter.

## 21. Dữ liệu thử với bốn chiều

~~~javascript
use vector_lab

db.knowledgeChunks.insertMany([
  {
    _id: "v1:doc-a:chunk-0",
    tenantId: "tenant-a",
    documentId: "doc-a",
    chunkId: "chunk-0",
    content: "Có thể thay đổi thời gian nhận xe.",
    status: "published",
    language: "vi",
    embedding: [0.1, 0.3, 0.5, 0.2],
    embeddingInfo: {
      model: "demo-model",
      modelVersion: "v1",
      dimensions: 4
    }
  },
  {
    _id: "v1:doc-b:chunk-0",
    tenantId: "tenant-a",
    documentId: "doc-b",
    chunkId: "chunk-0",
    content: "Quy trình hoàn tiền và hủy chuyến.",
    status: "published",
    language: "vi",
    embedding: [0.4, 0.2, 0.1, 0.7],
    embeddingInfo: {
      model: "demo-model",
      modelVersion: "v1",
      dimensions: 4
    }
  },
  {
    _id: "v1:doc-c:chunk-0",
    tenantId: "tenant-b",
    documentId: "doc-c",
    chunkId: "chunk-0",
    content: "Tài liệu nội bộ chưa xuất bản.",
    status: "draft",
    language: "vi",
    embedding: [0.2, 0.2, 0.4, 0.1],
    embeddingInfo: {
      model: "demo-model",
      modelVersion: "v1",
      dimensions: 4
    }
  }
]);
~~~

Các vector ở đây là dãy số mẫu, không được tạo bởi embedding model thật; chỉ dùng để thử index, filter và API shape.

Index demo có filter fields:

~~~javascript
db.runCommand({
  createSearchIndexes: "knowledgeChunks",
  indexes: [
    {
      name: "vector_demo",
      type: "vectorSearch",
      definition: {
        fields: [
          {
            type: "vector",
            path: "embedding",
            numDimensions: 4,
            similarity: "cosine"
          },
          { type: "filter", path: "tenantId" },
          { type: "filter", path: "status" },
          { type: "filter", path: "language" }
        ]
      }
    }
  ]
});
~~~

Chỉ tạo cùng tên index một lần trên collection; nếu index đã tồn tại, dùng quy trình quản trị/update tương ứng thay vì tạo trùng.

## 22. Truy vấn $vectorSearch

~~~javascript
db.knowledgeChunks.aggregate([
  {
    $vectorSearch: {
      index: "vector_demo",
      path: "embedding",
      queryVector: [0.11, 0.28, 0.51, 0.19],
      numCandidates: 100,
      limit: 5,
      filter: {
        tenantId: "tenant-a",
        status: "published",
        language: "vi"
      }
    }
  },
  {
    $project: {
      documentId: 1,
      chunkId: 1,
      content: 1,
      tenantId: 1,
      score: {
        $meta: "vectorSearchScore"
      }
    }
  }
]);
~~~

### 22.1. index và path

Index name phải tồn tại và ready; path phải đúng field vector được định nghĩa trong index.

### 22.2. queryVector

Query vector cần cùng số chiều và embedding space với documents. Không dùng vector toy trong production và mong đợi kết quả semantic search thực.

### 22.3. numCandidates

Điều chỉnh độ rộng ANN candidate search. Giá trị lớn hơn có thể tăng recall và tăng compute/latency. Phải benchmark, không chọn tỷ lệ cứng cho mọi corpus.

### 22.4. limit

Giới hạn số hits mong muốn. Nếu filter chỉ còn ít documents, số kết quả có thể ít hơn limit.

### 22.5. score

Projection dùng **$meta: "vectorSearchScore"** để lấy score phục vụ ranking/quan sát. Score không phải xác suất kết quả đúng.

## 23. Targeted retrieval bằng pre-filter

Một corpus có nhiều tenants và statuses:

~~~text
10.000.000 chunks
    tenant-a: 20.000 published chunks
    tenant-b: nhiều chunks khác
    draft/retracted chunks
~~~

Search filter:

~~~javascript
filter: {
  tenantId: "tenant-a",
  status: "published"
}
~~~

giúp giới hạn phạm vi candidates theo khả năng filter index.

### 23.1. Post-filter có thể mất recall

Nếu tìm top-10 trên tất cả tenants rồi mới lọc tenant-a, 10 ứng viên đầu có thể hầu hết thuộc tenant khác, khiến application nhận rất ít kết quả dù corpus tenant-a có nhiều nội dung liên quan.

### 23.2. Post-filter không nên là lớp phân quyền duy nhất

Nếu đưa top-k toàn cluster tới LLM trước khi lọc, dữ liệu ngoài quyền đã bị truyền vào tầng xử lý. Backend cần lọc và kiểm tra quyền trước khi sử dụng hits.

### 23.3. Filter selectivity ảnh hưởng hiệu năng

Một tenant có 50 documents và tenant khác có một triệu documents có thể cần tuning khác cho ANN. Đo theo workload thật.

## 24. Score không phải phần trăm chính xác

Một hit có:

~~~javascript
{
  documentId: "doc-a",
  score: 0.84
}
~~~

Không kết luận có 84% xác suất trả lời đúng.

### 24.1. Score phụ thuộc metric

Cosine, dotProduct và Euclidean có cách so khác nhau. MongoDB có thể biểu diễn score theo công thức ranking của engine.

### 24.2. Ngưỡng phải hiệu chỉnh

Không dùng mặc định:

~~~text
score >= 0.8 -> chắc chắn đúng
~~~

Hãy đánh giá precision/recall theo corpus và chọn threshold từ gold labels, thay vì cảm tính.

### 24.3. Không so raw scores khác models

Score 0.9 của model A và 0.8 của model B không tự cho biết A tốt hơn B nếu thang score và embeddings khác nhau.

### 24.4. Hybrid search

Nếu kết hợp keyword và vector, cần ranking fusion hoặc reranking phù hợp. Không cộng raw keyword score và vector score khi chưa có quy tắc/normalization.

## 25. Freshness và trạng thái xuất bản

Document nguồn có thể được sửa hoặc thu hồi trong khi vector search index chưa cập nhật ngay.

Các mốc:

~~~text
T1: source document updated
T2: embedding generated
T3: MongoDB chunk document written
T4: Search index reflects new data
T5: Application query sees current result
~~~

### 25.1. Search index có thể đồng bộ bất đồng bộ

Không mặc định MongoDB write acknowledgment đồng nghĩa vector search đã thấy thay đổi tại thời điểm đó. Cần theo dõi index lag/freshness.

### 25.2. Thu hồi tài liệu

Nếu status đổi published → retracted, nên update metadata và thực hiện final authorization/status check trước khi hiển thị nếu yêu cầu thu hồi là tức thời.

### 25.3. Nguồn bị xóa

Chunks vector của tài liệu đã xóa cũng cần được retire/delete. Nếu bỏ qua cleanup, retrieval có thể trả nội dung đã không còn ở nguồn.

### 25.4. Timestamp phân biệt nhau

~~~javascript
{
  sourceUpdatedAt: ISODate("2026-11-14T08:00:00Z"),
  embeddingGeneratedAt: ISODate("2026-11-14T08:04:00Z"),
  mongoUpdatedAt: ISODate("2026-11-14T08:05:00Z")
}
~~~

Không tự ghi một field searchVisibleAt bằng mongoUpdatedAt nếu chưa có cơ chế xác minh search readiness.

## 26. Trạng thái ingestion

Một vector pipeline có thể đi qua:

~~~text
RECEIVED
  |
  v
PARSED
  |
  v
CHUNKED
  |
  v
EMBEDDING_REQUESTED
  |
  v
EMBEDDING_VALIDATED
  |
  v
MONGO_WRITTEN
  |
  v
INDEX_READY
  |
  v
PUBLISHED
~~~

Metadata:

~~~javascript
{
  embeddingStatus: "ready",
  lastEmbeddingAttemptAt: ISODate("2026-11-14T09:00:00Z"),
  embeddingError: null,
  retryCount: 0
}
~~~

### 26.1. Khi model call lỗi

Không ghi zero vector và đánh dấu ready. Lưu pending/failed, thông tin lỗi phù hợp và retry có kiểm soát.

### 26.2. Runtime validation

Kiểm tra:

1. Đúng model/version.
2. Đúng số chiều.
3. Không null/NaN/Infinity.
4. Encoding được hỗ trợ.
5. Nguồn còn đúng documentVersion.
6. Metadata tenant/source/status không thiếu.
7. Content hash/preprocessing khớp.

### 26.3. Không publish sớm

Nếu cần cam kết tài liệu mới đã có thể search, đừng đánh dấu published về nghĩa “search-ready” chỉ vì insert đã thành công. Phải phân biệt business publication và search-index readiness.

## 27. Idempotent upsert

Ingestion có thể retry sau network timeout.

### 27.1. Stable chunk ID

Một quy tắc:

~~~text
tenantId:documentId:documentVersion:chunkIndex
~~~

Ví dụ:

~~~javascript
_id: "tenant-a:doc-123:v7:chunk-004"
~~~

Retry cùng logical chunk target đúng record.

### 27.2. Ví dụ MongoDB upsert

~~~javascript
db.knowledgeChunks.updateOne(
  {
    _id: "tenant-a:doc-123:v7:chunk-004"
  },
  {
    $set: {
      tenantId: "tenant-a",
      documentId: "doc-123",
      documentVersion: 7,
      chunkIndex: 4,
      content: "Hướng dẫn thay đổi lịch nhận xe...",
      embedding: [0.12, -0.08, 0.35, 0.04],
      status: "published",
      updatedAt: new Date()
    }
  },
  { upsert: true }
);
~~~

### 27.3. Retry không tạo ID mới

Nếu mỗi retry tạo UUID khác, một chunk có thể bị lưu nhiều lần và xuất hiện lặp trong kết quả search.

### 27.4. Source version

Nếu source version 8 đã xuất hiện khi embedding version 7 trả về, không ghi đè v8 bằng vector v7. Dùng conditional update hoặc versioned document IDs rồi cutover có kiểm soát.

## 28. Re-embedding khi dữ liệu thay đổi

Một đoạn nội dung đổi có thể cần tạo lại embedding. Mức độ ảnh hưởng tùy pipeline:

- Chỉ chunk thay đổi.
- Nhiều chunks nếu ranh giới chunking thay.
- Toàn bộ document nếu preprocessing thay đổi.
- Toàn corpus nếu model bị thay.

### 28.1. Content hash

Nếu normalized chunk text, modelVersion và preprocessingVersion đều không đổi, có thể dùng cache vector hoặc skip re-embedding theo policy.

### 28.2. Không chỉ dựa vào chunkIndex

Thêm một đoạn ở đầu tài liệu có thể làm mọi chunkIndex dịch chuyển, dù một số nội dung cũ vẫn tồn tại. Cần kết hợp documentVersion, chunking version, anchor hoặc hash.

### 28.3. Chunks cũ phải được retire

Nếu v7 có 8 chunks còn v8 chỉ có 6 chunks, cần xóa/hide các chunks version cũ ở thời điểm phù hợp. Không để stale results cùng xuất hiện nếu hệ thống chỉ muốn version mới nhất.

## 29. Migration embedding model

Ví dụ:

~~~text
Model A: 768 dims
Model B: 1024 dims
~~~

Không thể đổi numDimensions từ 768 sang 1024 trên index rồi coi vector cũ được chuyển đổi.

### 29.1. Chiến lược fields song song

~~~javascript
{
  _id: "chunk-001",
  embeddingV1: [/* 768 giá trị */],
  embeddingV2: [/* 1024 giá trị */]
}
~~~

Lập hai indexes với path/dimensions/metric tương ứng. Trong giai đoạn migration, query A bằng model A và query B bằng model B.

### 29.2. Collection riêng

~~~text
knowledgeChunksV1 -> model A
knowledgeChunksV2 -> model B
~~~

Ưu điểm: tách schema rõ, dễ rollback. Nhược điểm: tốn thêm storage/index, phải đồng bộ ACL và source changes.

### 29.3. Quy trình cutover

1. Chọn và pin model B.
2. Tạo index B.
3. Re-embed/backfill dữ liệu.
4. Theo dõi coverage và readiness.
5. Đánh giá retrieval B với gold queries.
6. Canary traffic theo tỷ lệ nhỏ.
7. Theo dõi latency, errors và quality.
8. Chuyển traffic toàn bộ nếu đạt tiêu chí.
9. Giữ rollback path đến khi ổn định.
10. Xóa version cũ theo kế hoạch.

### 29.4. Cùng số chiều vẫn cần tách

Model A và B cùng 768 chiều không có nghĩa vectors trộn được. Embedding space có thể hoàn toàn khác.

## 30. Java Sync Driver: kiểm tra dimensions

Một helper Java validate numeric vector:

~~~java
import java.util.ArrayList;
import java.util.List;

public final class EmbeddingValidator {

    private EmbeddingValidator() {}

    public static List<Double> validate(
            List<Double> input,
            int expectedDimensions
    ) {
        if (input == null) {
            throw new IllegalArgumentException(
                    "Embedding không được null"
            );
        }

        if (expectedDimensions <= 0) {
            throw new IllegalArgumentException(
                    "Dimensions phải dương"
            );
        }

        if (input.size() != expectedDimensions) {
            throw new IllegalArgumentException(
                    "Expected " + expectedDimensions
                    + " dimensions, got " + input.size()
            );
        }

        List<Double> result =
                new ArrayList<>(input.size());

        for (Double value : input) {
            if (value == null ||
                    !Double.isFinite(value)) {
                throw new IllegalArgumentException(
                        "Embedding chứa giá trị không hợp lệ"
                );
            }
            result.add(value);
        }

        return result;
    }
}
~~~

### 30.1. Reject thay vì pad

Helper cố ý reject vector sai chiều. Không âm thầm nối zeros hoặc cắt vector.

### 30.2. Kiểm tra version cùng dimensions

Một vector có đúng size nhưng sai model vẫn cần bị từ chối theo application contract.

### 30.3. Float32 trong SDK

Nếu embedding service trả float[], chuyển sang representation được MongoDB/driver/index hỗ trợ. Không tự ép thành int hoặc string.

## 31. Java Sync Driver: lưu vector và metadata

~~~java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.UpdateOptions;
import org.bson.Document;

import java.util.Arrays;
import java.util.Date;
import java.util.List;

public class SaveKnowledgeChunk {

    public static void main(String[] args) {
        String uri = System.getenv("MONGODB_URI");

        if (uri == null || uri.isBlank()) {
            throw new IllegalArgumentException(
                    "Thiếu MONGODB_URI"
            );
        }

        List<Double> vector =
                EmbeddingValidator.validate(
                        Arrays.asList(
                                0.12, -0.08, 0.35, 0.04
                        ),
                        4
                );

        String id = "tenant-a:doc-001:v1:chunk-000";

        Document modelInfo = new Document(
                "model", "demo-model"
        ).append("modelVersion", "v1")
         .append("dimensions", 4)
         .append("preprocessingVersion", 1);

        Document fields = new Document(
                "tenantId", "tenant-a"
        ).append("documentId", "doc-001")
         .append("documentVersion", 1)
         .append("chunkId", "chunk-000")
         .append("language", "vi")
         .append("status", "published")
         .append("content", "Hướng dẫn đổi lịch nhận xe")
         .append("embedding", vector)
         .append("embeddingInfo", modelInfo)
         .append("updatedAt", new Date());

        try (MongoClient client = MongoClients.create(uri)) {
            MongoCollection<Document> chunks =
                    client.getDatabase("vector_lab")
                          .getCollection("knowledgeChunks");

            chunks.updateOne(
                    Filters.eq("_id", id),
                    new Document("$set", fields),
                    new UpdateOptions().upsert(true)
            );
        }
    }
}
~~~

### 31.1. Ví dụ dùng vector toy

Không có embedding model thật trong code này. Các số demo chỉ để minh họa kiểu dữ liệu và upsert.

### 31.2. Write concern và concurrency

Production cần chọn write concern đúng yêu cầu và tránh job từ source version cũ ghi đè version mới. Dùng conditional updates/versioned IDs khi cần.

### 31.3. Ngoại lệ khi gọi model

Service gọi embedding API cần timeout, backoff, rate-limit, privacy policy và cost monitoring, không chỉ thao tác database.

## 32. Java Sync Driver: truy vấn $vectorSearch

~~~java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import org.bson.Document;

import java.util.Arrays;
import java.util.List;

public class SearchKnowledge {

    public static void main(String[] args) {
        String uri = System.getenv("MONGODB_URI");

        if (uri == null || uri.isBlank()) {
            throw new IllegalArgumentException(
                    "Thiếu MONGODB_URI"
            );
        }

        List<Double> queryVector =
                EmbeddingValidator.validate(
                        Arrays.asList(
                                0.11, 0.28, 0.51, 0.19
                        ),
                        4
                );

        String trustedTenantId = "tenant-a";

        Document filter = new Document(
                "tenantId", trustedTenantId
        ).append("status", "published");

        Document vectorSearch = new Document(
                "index", "vector_demo"
        ).append("path", "embedding")
         .append("queryVector", queryVector)
         .append("numCandidates", 100)
         .append("limit", 5)
         .append("filter", filter);

        Document project = new Document(
                "documentId", 1
        ).append("chunkId", 1)
         .append("content", 1)
         .append("tenantId", 1)
         .append(
                 "score",
                 new Document(
                         "$meta",
                         "vectorSearchScore"
                 )
         );

        List<Document> pipeline = Arrays.asList(
                new Document("$vectorSearch", vectorSearch),
                new Document("$project", project)
        );

        try (MongoClient client = MongoClients.create(uri)) {
            MongoCollection<Document> chunks =
                    client.getDatabase("vector_lab")
                          .getCollection("knowledgeChunks");

            chunks.aggregate(pipeline).forEach(
                    hit -> System.out.println(hit.toJson())
            );
        }
    }
}
~~~

### 32.1. Index name/path/size khớp

Code đòi index vector_demo với embedding 4 chiều và các filter fields đã khai báo.

### 32.2. Query embedding từ model thật

Trong production, queryVector được tạo từ **cùng embedding model/version** của corpus, không phải các số demo.

### 32.3. Tenant ID phải đến từ auth context

Không lấy tenant ID tùy ý từ request rồi tin rằng filter đã an toàn.

## 33. Cấu hình embedding profile tập trung

Một profile Java:

~~~java
public record EmbeddingProfile(
        String modelId,
        int dimensions,
        String similarity,
        int preprocessingVersion,
        String indexName
) {}
~~~

Ví dụ:

~~~java
EmbeddingProfile profile = new EmbeddingProfile(
        "embedding-model-v3",
        768,
        "cosine",
        2,
        "knowledge_vector_v3"
);
~~~

Các bước model call, validate, ghi metadata và chọn index nên cùng dùng profile.

### 33.1. Tránh hard-code dimensions ở nhiều services

Nếu một service đổi thành 1024 nhưng search vẫn gửi 768, lỗi có thể xảy ra khi deploy. Cấu hình có version giúp phát hiện.

### 33.2. Vẫn validate runtime

Model provider có thể trả số chiều khác do lỗi cấu hình hoặc thay revision; config dự kiến không thay thế kiểm tra vector thực.

## 34. Metadata trích dẫn trong RAG

Một hit hữu ích:

~~~javascript
{
  documentId: "doc-123",
  documentVersion: 7,
  chunkId: "chunk-004",
  content: "Khách hàng có thể đổi giờ nhận xe...",
  title: "Quy trình đổi lịch",
  sourceUri: "/knowledge/change-booking",
  section: "Điều kiện đổi",
  score: 0.83
}
~~~

### 34.1. Score chỉ là liên quan

Không dùng score để khẳng định câu trong chunk là sự thật. Cần nguồn đáng tin, quyền truy cập và freshness.

### 34.2. Phiên bản nguồn

Nếu sourceUri hiện mở version 8 nhưng vector lấy từ version 7, citation có thể lệch. Cần gắn source version hoặc đảm bảo old hits được retire.

### 34.3. Nội dung retrieval không phải instruction đáng tin

Tài liệu được tìm thấy có thể chứa chỉ dẫn độc hại hoặc thông tin sai. Ứng dụng RAG phải coi content như dữ liệu nguồn và giữ ranh giới giữa câu hỏi, tài liệu và chỉ dẫn hệ thống.

## 35. Đánh giá chất lượng tìm kiếm

Một tập evaluation:

~~~javascript
{
  query: "Tôi cần chuyển thời gian nhận xe",
  tenantId: "tenant-a",
  language: "vi",
  relevantChunkIds: [
    "doc-123:v7:chunk-004",
    "doc-456:v2:chunk-001"
  ]
}
~~~

### 35.1. Recall@k

Trong các chunks thật sự liên quan, bao nhiêu được trả trong top-k?

### 35.2. Precision@k

Trong top-k, bao nhiêu thực sự liên quan?

### 35.3. MRR và nDCG

Đánh giá vị trí của kết quả đúng và thứ tự xếp hạng.

### 35.4. Đo theo nhóm

Kiểm tra tiếng Việt, nội dung ngắn/dài, tenant lớn/nhỏ, nội dung gần trùng và truy vấn có thuật ngữ đặc thù.

### 35.5. Filter correctness là yêu cầu chất lượng

- Không trả tenant khác.
- Không trả draft/retracted.
- Không trả document đã xóa.
- Không trả nội dung ngoài ACL.
- Không trích version sai.

## 36. ANN và numCandidates

Approximate search đánh đổi recall với latency.

~~~javascript
{
  $vectorSearch: {
    index: "knowledge_vector_v1",
    path: "embedding",
    queryVector: queryEmbedding,
    numCandidates: 200,
    limit: 10,
    filter: {
      tenantId: "tenant-a"
    }
  }
}
~~~

### 36.1. numCandidates lớn

Thường có cơ hội tăng recall nhưng tăng compute/latency.

### 36.2. numCandidates nhỏ

Có thể giảm latency nhưng bỏ lỡ ứng viên gần nhất.

### 36.3. Không có tỷ lệ cố định

Đo trên gold queries và nhiều corpus sizes. Nếu có lựa chọn exact nearest neighbors trong phiên bản triển khai, dùng làm baseline để ước lượng ANN recall.

## 37. Storage planning

Giả sử:

~~~text
200.000 source documents
10 chunks / document
768 dimensions / vector
~~~

Có xấp xỉ:

~~~text
2.000.000 vectors
~~~

Float32 raw bytes xấp xỉ:

\[
2{,}000{,}000 \times 768 \times 4
= 6{,}144{,}000{,}000 \text{ bytes}
\]

Chưa tính MongoDB document overhead, index/ANN structure, replication, backup, metadata, văn bản chunks và storage headroom.

### 37.1. Metadata lặp theo số chunks

Một field lớn 1 KB nhân hai triệu chunks đã tiêu tốn đáng kể storage. Chỉ lặp những metadata cần retrieval/filter, còn metadata chi tiết có thể nằm ở source collection.

### 37.2. Dự phòng migration

Khi chạy model A/B side by side, có thể cần cả hai indices/collections một thời gian. Budget phải tính giai đoạn peak migration, không chỉ steady state.

### 37.3. Quantization

Các kỹ thuật quantization có thể giảm footprint, nhưng có trade-off precision/recall và yêu cầu tương thích API/index. Cần benchmark trước khi chọn.

## 38. Quyền riêng tư và Embedding API

Nếu embedding model được gọi qua dịch vụ ngoài, tài liệu có thể rời hạ tầng MongoDB để đi qua model provider.

Cần kiểm tra:

- Loại dữ liệu được gửi.
- PII, secrets, hợp đồng nhạy cảm.
- Quy định retention/region.
- Cơ chế redaction.
- Quản lý credentials.
- Log request và tracing.
- Chính sách lưu embeddings.

Vector không tự trở thành dữ liệu công khai hay vô hại chỉ vì người dùng không đọc được trực tiếp từng chiều số.

## 39. Những lỗi thường gặp

| Lỗi | Hậu quả |
| --- | --- |
| Chỉ lưu vector không documentId | Không truy vết nguồn |
| Không lưu modelVersion | Không xác định embedding space |
| Trộn hai models cùng dimensions | Similarity không đáng tin |
| Pad/truncate vector để khớp | Sai contract model |
| Query bằng model khác indexing | Ranking sai |
| Chứa NaN/null/Infinity | Lỗi indexing hoặc dữ liệu không hợp lệ |
| Lưu embedding như string | Không đúng numeric representation |
| Dùng zero vector cho lỗi model | Kết quả giả |
| Không thống nhất normalization | Score không nhất quán |
| Chọn nhiều chiều vì nghĩ luôn tốt | Tốn chi phí, chưa chắc quality |
| Một vector cho tài liệu cực dài | Mất chi tiết |
| Không lưu chunkIndex/version | Khó hiển thị/trích dẫn |
| Source đổi nhưng không re-embed | Stale vectors |
| Source xóa nhưng chunks còn | Trả dữ liệu đã xóa |
| Thiếu tenantId | Khó lọc chính xác |
| Chỉ lọc tenant ở UI | Có thể lộ nội dung |
| Tin tenant ID do caller truyền | Vượt tenant |
| Thiếu filter index fields | Pre-filter không hoạt động như kỳ vọng |
| Dùng B-tree index cho cosine | Không có vector index |
| Index field path sai | Không tìm đúng vector |
| numDimensions sai | Index/query lỗi |
| Không chờ index readiness | Kết quả không ổn định |
| Coi score là xác suất đúng | Threshold sai |
| Không đánh giá ANN recall | Bỏ ứng viên |
| Chỉ tăng numCandidates vô hạn | Latency/compute tăng |
| Đổi model bằng cách sửa numDimensions | Không chuyển embeddings cũ |
| Ingestion job cũ ghi đè version mới | Stale data |
| Retry với random chunk ID | Duplicate |
| Không có reconciliation | Drift nguồn/chunks |
| Tin search index cập nhật tức thời | Freshness gap |
| Bỏ authorization check | Rủi ro dữ liệu |
| Không lưu sourceUri/section | Không trích dẫn tin cậy |

## 40. Bài tập: dimensions và model

### Bài 1

Cho A=[0.1,0.2,-0.3], B=[0.1,0.2,-0.3,0.4], C=[0.1,null,-0.3]. Nếu index numDimensions=4, vector nào có số chiều phù hợp? Vector nào phải reject vì numeric value?

### Bài 2

Model trả 768 chiều, index khai báo 512. Vì sao không nên cắt 256 chiều? Hãy đề xuất cách sửa.

### Bài 3

Hai models đều trả 768 chiều. Có thể dùng chung một index và query bằng bất kỳ model nào không? Giải thích embedding space.

### Bài 4

Thiết kế schema của một chunk gồm content, embedding, source IDs, modelVersion, dimensions, preprocessingVersion, contentHash và tenantId.

### Bài 5

Sản phẩm có titleEmbedding và imageEmbedding với model/chiều khác nhau. Thiết kế index paths và metadata.

## 41. Bài tập: metric và storage

### Bài 6

Cho A=[1,0], B=[2,0], C=[0,1]. So sánh cosine, dot product và Euclidean theo hướng và magnitude.

### Bài 7

Tính L2 norm của [3,4] và normalize thành unit vector. Điều gì xảy ra với [0,0]?

### Bài 8

Ước lượng raw float32 bytes cho một triệu vectors 768 chiều. Vì sao kết quả không phải dung lượng Atlas index cuối cùng?

### Bài 9

Có 100.000 tài liệu, trung bình 7 chunks/tài liệu. Có bao nhiêu vectors? Nếu tăng chunk overlap, chi phí thay đổi thế nào?

### Bài 10

Model 384 chiều có thể tốt hơn model 1.536 chiều không? Thiết kế gold query set để đánh giá.

## 42. Bài tập: metadata và quyền

### Bài 11

Thiết kế vector search filter theo tenant-a và published. Vì sao backend phải lấy tenant từ authenticated context?

### Bài 12

Collection có field language nhưng vector index chưa khai báo type filter cho language. Cần làm gì?

### Bài 13

Một bài chuyển published → retracted. Nội dung không đổi. Có cần re-embed không? Làm sao ngăn stale search result bị hiển thị?

### Bài 14

User chỉ xem project P1. Thiết kế pre-filter và final authorization check khi ACL có thể thay đổi.

### Bài 15

Một hit có score cao nhưng không có sourceUri/documentVersion. Rủi ro gì đối với RAG có citations?

## 43. Bài tập: ingestion và migration

### Bài 16

Document version 7 đang được embed; trước khi model trả, source thành version 8. Làm thế nào để không ghi vector cũ lên nội dung mới?

### Bài 17

Tạo contentHash cho normalized chunk. Điều kiện gì cho phép skip re-embedding an toàn?

### Bài 18

Chuyển model 768 chiều sang 1.024 chiều. Lập kế hoạch index, backfill, canary, rollback và cleanup.

### Bài 19

Thay chunking từ 300 token sang 500 token có overlap. Vì sao chunkIndex cũ không đủ nhận dạng nội dung mới?

### Bài 20

Ingestion retry sau timeout nhưng MongoDB đã ghi thành công. Dùng deterministic _id để tránh duplicate như thế nào?

## 44. Bài tập: MongoDB và Java

### Bài 21

Tạo một vectorSearch index demo có vector field embedding, numDimensions=4 và similarity=cosine, kèm filter tenantId/status.

### Bài 22

Viết $vectorSearch với queryVector bốn chiều, numCandidates=100, limit=5, tenantId pre-filter và project score.

### Bài 23

Một hit có score 0.84. Vì sao không thể coi đó là xác suất 84% đúng? Hãy nêu quy trình chọn threshold bằng evaluation data.

### Bài 24

Viết Java EmbeddingValidator kiểm tra số chiều, null, NaN và Infinity. Vì sao phải validate runtime?

### Bài 25

Dùng Java Sync Driver lưu chunk bằng upsert với stable ID và model metadata, rồi truy vấn qua $vectorSearch.

### Bài 26

So sánh truy vấn numCandidates=50/100/300 trên cùng tập câu hỏi. Ghi recall@10 và p95 latency. Vì sao không chọn chỉ theo một câu truy vấn demo?

### Bài 27

Một document đã xóa nhưng index còn trả trong một khoảng ngắn. Đề xuất final check và ingestion reconciliation.

## 45. Checklist trước production

1. Model và version được pin/ghi nhận.
2. Dimensions lấy từ model và được validate runtime.
3. Mọi vector value numeric finite.
4. Encoding BSON/quantization khớp index/driver.
5. Metric cosine/dotProduct/euclidean được chọn có cơ sở.
6. Normalization thống nhất giữa indexing và query.
7. Vector field path ổn định.
8. Không trộn embedding spaces không tương thích.
9. documentId/chunkId/source version đủ để truy vết.
10. TenantId, status và ACL được mô hình hóa rõ.
11. Filter fields được khai báo đúng trong vector index.
12. SourceUri/title/section/offset đủ cho citations.
13. ModelVersion/preprocessingVersion/chunkingVersion được lưu.
14. ContentHash cho update/re-embedding.
15. Chunk strategy được đánh giá.
16. Index type, path, dimensions và similarity đúng.
17. Index readiness/freshness được theo dõi.
18. Query vector cùng model và đúng dimensions.
19. numCandidates/limit được tuning trên gold dataset.
20. Tenant filter lấy từ backend auth context.
21. Có final authorization check khi quyền có thể đổi nhanh.
22. Không trả draft/retracted/stale chunks.
23. Ingestion dùng stable IDs/idempotent retries.
24. Source version cũ không ghi đè version mới.
25. Model migration có backfill/canary/rollback.
26. Đo retrieval quality theo ngôn ngữ/tenant.
27. Monitoring có dimension mismatch, indexing errors và lag.
28. Chi phí tính theo số chunks, dimensions, index và backup.
29. Dữ liệu nhạy cảm được kiểm soát trước khi gửi embedding model.
30. Có quy trình reconcile source documents với chunks.

## 46. Kết luận

Một hệ thống MongoDB Vector Search đáng tin bắt đầu bằng **hợp đồng dữ liệu rõ ràng giữa embedding model, field vector, index và query**. Field embedding phải đúng kiểu số, số chiều, định dạng và metric. Query vector phải được tạo bằng model/preprocessing tương thích với corpus. Hai models cùng 768 chiều không mặc nhiên chia sẻ một không gian ngữ nghĩa.

Metadata quyết định khả năng đưa hệ thống vào production:

- **documentId/chunkId/version** bảo đảm truy vết và cập nhật idempotent.
- **tenantId/status/ACL** giúp filter hợp lệ và bảo vệ quyền.
- **language/category/sourceType** nâng chất lượng retrieval theo phạm vi.
- **modelVersion/dimensions/preprocessingVersion/contentHash** hỗ trợ kiểm tra tương thích, re-embedding và migration.
- **sourceUri/section/offset** cho citations.
- **timestamps/embeddingStatus** cho freshness và monitoring.

Đừng chỉ chọn số chiều lớn hoặc một index chạy được trên dữ liệu demo. Cần đánh giá retrieval, quyền truy cập, chi phí, độ trễ search và quy trình thay đổi model. **Schema vector là một phần của kiến trúc dữ liệu, không phải một array số được thêm vào cuối document.**

## Tài liệu tham khảo

- [MongoDB Atlas Vector Search — Overview](https://www.mongodb.com/docs/atlas/atlas-vector-search/vector-search-overview/)
- [MongoDB Atlas Vector Search — Index Definition](https://www.mongodb.com/docs/atlas/atlas-vector-search/vector-search-type/)
- [MongoDB Atlas Vector Search — Create Index](https://www.mongodb.com/docs/atlas/atlas-vector-search/create-index/)
- [MongoDB Atlas Vector Search — Query](https://www.mongodb.com/docs/atlas/atlas-vector-search/vector-search-stage/)
- [MongoDB Manual — $vectorSearch](https://www.mongodb.com/docs/manual/reference/operator/aggregation/vectorsearch/)
- [MongoDB Manual — Search Indexes](https://www.mongodb.com/docs/manual/reference/method/db.collection.createSearchIndex/)
- [MongoDB Manual — Aggregation Pipeline](https://www.mongodb.com/docs/manual/core/aggregation-pipeline/)
- [MongoDB Manual — Data Modeling](https://www.mongodb.com/docs/manual/data-modeling/)
- [MongoDB Java Sync Driver Documentation](https://www.mongodb.com/docs/drivers/java/sync/current/)
