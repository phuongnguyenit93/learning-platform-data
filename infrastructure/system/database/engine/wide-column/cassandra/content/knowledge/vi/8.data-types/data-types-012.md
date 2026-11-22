# vector hoặc kiểu bổ sung theo phiên bản trong Apache Cassandra

Kiểu dữ liệu của **Apache Cassandra** không phải một danh sách bất biến qua mọi bản phát hành. Một câu lệnh CQL hợp lệ trên Cassandra 5.0 có thể không được parser của Cassandra 4.1 hiểu, hoặc được một bản phân phối khác triển khai với giới hạn khác. Ví dụ nổi bật là **`vector`**: một kiểu dữ liệu có **số chiều cố định**, được bổ sung trong dòng **Apache Cassandra 5.0** để lưu vector số và hỗ trợ tìm kiếm tương tự (*vector similarity search*) khi kết hợp với **Storage-Attached Index (SAI)**.

Bài thuộc chương **Kiểu dữ liệu** của module **DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA**. Trong hệ thống wide-column phân tán, cần phân biệt rõ ba tầng: **kiểu dữ liệu CQL có được phiên bản cluster hỗ trợ không**, **truy vấn có đường truy cập phù hợp không**, và **ứng dụng Java Driver có codec/API tương thích không**. Với vector, sự phân biệt này đặc biệt quan trọng: lưu được một vector **không đồng nghĩa** có thể truy vấn hàng triệu vector theo độ tương tự, và ANN không có cùng tính chất với tra cứu chính xác qua partition key.

## 1. Vì sao phải kiểm tra phiên bản trước khi chọn kiểu?

Một thiết kế dữ liệu được triển khai đồng thời trên nhiều nơi: cluster Cassandra, driver Java, công cụ migration, cqlsh, hệ tạo embeddings, thư viện index và quy trình vận hành. Chỉ cần một thành phần chưa hỗ trợ kiểu mới, hành trình triển khai có thể dừng ngay tại `CREATE TABLE`, hoặc ứng dụng gặp lỗi codec khi bind dữ liệu.

Bảng định hướng:

| Môi trường | Khả năng liên quan đến vector | Quyết định thực tế |
|---|---|---|
| **Apache Cassandra 3.x / 4.0 / 4.1** | Không có kiểu CQL `vector` và ANN/SAI vector như Cassandra 5.0 | Không dùng trực tiếp schema `vector<float,n>`; nâng cấp hoặc chọn phương án riêng |
| **Apache Cassandra 5.0** | Có CQL `vector`, SAI và cú pháp ANN theo khả năng bản phát hành | Xác minh patch release, giới hạn chiều, chỉ mục và ràng buộc truy vấn |
| **Bản phân phối/managed service tương thích CQL** | Có thể hỗ trợ vector nhưng cú pháp, giới hạn, metric, lifecycle khác | Đọc tài liệu của **sản phẩm và phiên bản thực tế**, không suy từ tên Cassandra |
| **Java Driver 4.x đời cũ** | Có thể không có API `CqlVector`/codec phù hợp hoặc API khác | Kiểm tra dependency; nâng driver khi tính năng yêu cầu |
| **Apache Cassandra Java Driver 4.17+**, ví dụ 4.19.x | Có API `CqlVector`, `setVector`, `getVector` theo phiên bản | Dùng đúng artifact/version và kiểm thử với cluster đích |

Lệnh kiểm tra phiên bản server khi có quyền truy vấn hệ thống:

~~~cql
SELECT release_version
FROM system.local;
~~~

Kết quả này phản ánh **node trả lời câu truy vấn**. Trong cluster đa node đang nâng cấp cuốn chiếu, phải xác minh khả năng và trạng thái **toàn bộ cluster** trước khi chạy schema migration có kiểu mới. Có thể dùng công cụ quản trị theo triển khai, nhưng không coi một node báo “5.0” là bảo đảm tất cả node đã sẵn sàng.

Để kiểm tra client Java, đọc **dependency thực sự được đóng gói và chạy**, thay vì chỉ nhìn phiên bản khai báo trong ví dụ. Nếu nhiều dịch vụ Java cùng truy cập keyspace, mọi dịch vụ đọc/ghi cột mới phải có chiến lược tương thích và rollout.

**Nguyên tắc:** không viết một schema “đúng trong tài liệu mới nhất” rồi triển khai mù trên cluster cũ. Khóa phiên bản tối thiểu, giới hạn và hành vi được kiểm chứng vào thiết kế, test và migration plan.

## 2. Vector CQL là gì?

CQL `vector<T, N>` biểu diễn một **dãy cố định đúng N phần tử**, tất cả đều có **kiểu T**, và **không cho phép phần tử NULL**. Một vector có thể được ghi/đọc như một **giá trị nguyên khối**; nó không phải collection non-frozen cho phép cập nhật phần tử riêng lẻ.

Ví dụ:

~~~cql
CREATE TABLE sample_vectors_by_id (
    sample_id uuid PRIMARY KEY,
    sensor_values vector<int, 3>,
    embedding vector<float, 3>
);
~~~

Ở đây:

- `sensor_values vector<int,3>` lưu ba số nguyên. Theo tài liệu kiểu vector Apache Cassandra 5.0, kiểu `vector` còn có thể dùng để lưu các loại phần tử khác, nhưng **vector search SAI/ANN dành cho vector phần tử `float`**.
- `embedding vector<float,3>` chứa đúng **ba số thực 32 bit** trong mỗi hàng. Đây là ví dụ để thực hành; các mô hình embedding thực tế thường có **nhiều chiều** hơn.
- `sample_id uuid` vẫn là **partition key**, giúp truy vấn chính xác bằng ID. Thêm cột vector không đổi cách Cassandra băm partition key hay nhân bản dữ liệu.

~~~cql
INSERT INTO sample_vectors_by_id (sample_id, sensor_values, embedding)
VALUES (
    11111111-1111-4111-8111-111111111111,
    [10, 20, 30],
    [0.12, 0.34, 0.56]
);

SELECT sensor_values, embedding
FROM sample_vectors_by_id
WHERE sample_id = 11111111-1111-4111-8111-111111111111;
~~~

Giống list literal, **vector literal** viết trong dấu ngoặc vuông, ví dụ `[0.12, 0.34, 0.56]`. Tuy nhiên **`vector<float,3>` không phải alias của `list<float>`**.

### 2.1. So sánh vector với list, tuple và blob

| Đặc điểm | `vector<float,3>` | `list<float>` | `tuple<float,float,float>` | `blob` |
|---|---|---|---|---|
| Số phần tử | **Cố định bằng 3** | Có thể thay đổi | Cố định theo schema tuple | Không có số phần tử CQL |
| Phần tử NULL | **Không** | Không dùng NULL làm phần tử hợp lệ | Có thể có vị trí NULL phù hợp | Byte tùy ý |
| Cập nhật vị trí riêng | **Không** | Có một số mutation theo index | Không, tuple luôn frozen | Không, ghi bytes mới |
| Ngữ nghĩa số chiều | **Được kiểm tra bởi kiểu** | Không có ràng buộc N từ kiểu | Có số vị trí nhưng không dành cho ANN | Ứng dụng tự định nghĩa |
| Dùng cho vector search SAI/ANN | **Có**, khi phần tử là float và bản triển khai hỗ trợ | Không phải cột vector ANN | Không phải cột vector ANN | Không phải cột vector ANN |
| Java Driver | `CqlVector<Float>` | `List<Float>` | `TupleValue` | `ByteBuffer` |

Vector hỗ trợ **đúng kích thước và đúng kiểu**, chứ không tự chứng minh tọa độ số học có nghĩa. Một vector `[0.12,0.34,0.56]` hoàn toàn vô nghĩa nếu không biết nó được sinh bởi mô hình nào, trong không gian nào và dùng metric gì.

### 2.2. Dữ liệu sai chiều và cập nhật nguyên khối

Giả sử cột là `vector<float,3>`:

~~~cql
-- Đúng số chiều:
UPDATE sample_vectors_by_id
SET embedding = [0.10, 0.20, 0.30]
WHERE sample_id = 11111111-1111-4111-8111-111111111111;
~~~

Những trường hợp sau không phù hợp kiểu:

~~~cql
-- Sai: thiếu một chiều.
-- UPDATE sample_vectors_by_id
-- SET embedding = [0.10, 0.20]
-- WHERE sample_id = 11111111-1111-4111-8111-111111111111;

-- Sai: phần tử null.
-- UPDATE sample_vectors_by_id
-- SET embedding = [0.10, null, 0.30]
-- WHERE sample_id = 11111111-1111-4111-8111-111111111111;

-- Không phải mutation vector hợp lệ:
-- UPDATE sample_vectors_by_id
-- SET embedding[0] = 0.10
-- WHERE sample_id = 11111111-1111-4111-8111-111111111111;
~~~

Muốn thay một chiều, ứng dụng tạo **giá trị vector hoàn chỉnh** rồi cập nhật cả cột. Không dùng `vector` như một log biến động từng thành phần hoặc một list để append thêm chiều.

Cột vector **có thể chưa được ghi** hoặc được xóa như một cột dữ liệu khi thao tác CQL cho phép; điều cấm là **NULL bên trong từng phần tử**. Hãy phân biệt “cột embedding chưa có giá trị” với “một embedding có phần tử null”.

### 2.3. Giới hạn số chiều phụ thuộc phiên bản/bản phân phối

Tài liệu **Apache Cassandra 5.0** về vector mô tả giới hạn **8K (2¹³ = 8192) chiều** cho kiểu vector. Một số tài liệu sản phẩm/bản phân phối tương thích CQL mô tả giới hạn khác. Vì vậy:

- Ghi rõ **Apache Cassandra 5.0, bản build, patch** hoặc sản phẩm cụ thể trong thiết kế.
- Không suy ra “mọi Cassandra đều hỗ trợ 65.535 chiều” hay “mọi dịch vụ đều giới hạn đúng 8.192” từ một tài liệu của bản khác.
- Chọn kích thước thực tế dựa trên **mô hình embedding** và khả năng index/runtime, không chỉ giới hạn parser của kiểu.
- Với `vector<float,1536>`, phần dữ liệu float thô có cỡ **1536 × 4 = 6144 byte** trước metadata, index, compression và chi phí sao chép; số chiều tăng làm tăng chi phí mạng, disk, RAM và ANN.

Một câu `CREATE TABLE` thành công không chứng minh workload 1 triệu vector × 8.192 chiều sẽ chạy đáp ứng SLA.

## 3. Embedding: vector có nghĩa khi gắn với mô hình

**Embedding** là một vector số do mô hình máy học biến đổi văn bản, ảnh, đoạn âm thanh hoặc thực thể thành biểu diễn trong một không gian đặc trưng. Các vector gần nhau theo metric được chọn thường biểu thị mức tương tự hữu ích cho bài toán đã huấn luyện.

Ví dụ thực tế:

- Ứng dụng học tập: tìm đoạn tài liệu có ngữ nghĩa liên quan đến câu hỏi người dùng.
- Sản phẩm thương mại: gợi ý sản phẩm dựa trên nội dung mô tả tương tự.
- Hệ thống ảnh: tìm những ảnh có đặc điểm thị giác tương đồng.
- Phân tích sự cố: tìm báo cáo lỗi có nội dung gần giống các trường hợp đã xử lý.

**CQL không sinh embedding.** Cassandra lưu và tìm kiếm các vector **do ứng dụng hoặc hệ thống AI tạo ra**. Việc chọn mô hình, tiền xử lý, ngôn ngữ, phân đoạn tài liệu, chuẩn hóa vector và đánh giá chất lượng nằm ở ứng dụng.

### 3.1. Cùng số chiều không đồng nghĩa cùng không gian vector

Hai mô hình khác nhau đều có thể tạo vector 768 chiều nhưng giá trị **không thể so sánh có ý nghĩa** nếu học trên hai không gian khác nhau. Một vector từ model A không tự tương thích với vector từ model B chỉ vì cùng `vector<float,768>`.

Hợp đồng embedding nên ghi rõ:

| Metadata | Ví dụ | Lý do |
|---|---|---|
| `embedding_model` | `edu-embedding-v1` | Phân biệt mô hình đã tạo vector |
| `model_revision` | `2026-10` | Đảm bảo có thể tạo lại/cập nhật |
| `embedding_dim` | 1536 (cố định ở schema) | Bắt lỗi sai chiều |
| `normalization` | `unit_l2` hoặc `none` | Phù hợp metric dot/cosine |
| `content_hash` | Digest của văn bản đầu vào | Phát hiện văn bản đổi nhưng vector cũ |
| `chunker_version` | `chunks-v2` | Biết cách tạo đoạn văn bản |
| `created_at` | `timestamp` | Đối soát và kiểm soát vòng đời |

Có thể lưu metadata ở cùng bảng hoặc ở bảng quản lý model/chunk; **đừng chỉ lưu vector** rồi mất nguồn dữ liệu và phiên bản mô hình.

### 3.2. float có sai số số học

`vector<float,n>` dùng **float 32 bit (IEEE 754)** cho ANN. Đây không phải `decimal` và không lưu chính xác mọi số thập phân. Khi dữ liệu nguồn dùng `double`, việc chuyển sang `float` có thể làm tròn; nhiều giá trị rất gần nhau có thể thành một giá trị float.

Không dùng vector float cho **tiền tệ, định danh tuyệt đối hoặc dữ liệu cần đối soát chính xác**. Nó phục vụ phép so sánh số học gần đúng/tính tương tự theo mô hình.

Ứng dụng nên kiểm tra:

1. Số chiều đúng schema.
2. Không có phần tử null.
3. Mọi float là số **hữu hạn** (không `NaN`, `+Infinity`, `-Infinity`) trước khi gửi đến dịch vụ ANN.
4. Vector không có norm bằng 0 nếu metric cosine cần định hướng vector.
5. Đầu vào truy vấn được sinh bằng **cùng mô hình và cách normalization** với các vector đã index.

Một vector có số chiều đúng nhưng gồm toàn số 0 hoặc giá trị khác chuẩn vẫn có thể làm kết quả tìm kiếm vô nghĩa; validation số học cần nằm ở biên ingest và query.

## 4. Vector Search, SAI và ANN khác tra cứu theo khóa như thế nào?

Cassandra có hai dạng truy vấn rất khác nhau:

**Tra cứu chính xác**:

~~~cql
SELECT *
FROM sample_vectors_by_id
WHERE sample_id = 11111111-1111-4111-8111-111111111111;
~~~

Cassandra dùng **partition key** để xác định token và các replica phù hợp. Kết quả gắn với **một ID cụ thể**.

**Tìm vector gần nhất**:

~~~cql
-- Yêu cầu cột embedding của bảng truy vấn có SAI vector index.
SELECT chunk_id, content_preview
FROM document_chunks_by_id
ORDER BY embedding ANN OF [0.10, 0.20, 0.30]
LIMIT 5;
~~~

Cassandra dùng **chỉ mục SAI vector** để tìm các ứng viên gần vector truy vấn. Đây là **Approximate Nearest Neighbor (ANN)**: trả lời câu hỏi “những điểm nào *gần* điểm truy vấn?” theo metric, không phải equality lookup.

### 4.1. ANN là gần đúng, không phải truy vấn top-k chính xác tuyệt đối

Trong một tập dữ liệu có hàng triệu vector, so sánh khoảng cách tới **từng vector** sẽ tốn chi phí cao. ANN dùng chỉ mục để thu hẹp vùng tìm kiếm và đánh đổi một phần **recall** lấy tốc độ/khả năng mở rộng. Kết quả:

- Có thể **không trùng hoàn toàn** với top-k tính bằng brute force.
- Thứ tự và tập ứng viên có thể khác khi dữ liệu/index thay đổi, cấu hình thuật toán hoặc môi trường thay đổi.
- `LIMIT 5` yêu cầu một lượng kết quả nhỏ, không phải bằng chứng Cassandra đã chứng minh 5 kết quả đó tốt nhất tuyệt đối.
- Vector “gần nhau” theo metric không đồng nghĩa tài liệu **đúng sự thật**, có quyền truy cập, hoặc phù hợp nghiệp vụ.

Một hệ RAG (retrieval-augmented generation) nên có các bước **lọc tenant/quyền**, đánh giá kết quả, có thể **rerank**, và trích nguồn thay vì coi ANN là cơ chế chứng minh tính đúng.

### 4.2. Tại sao cần SAI?

Trong Apache Cassandra 5.0, vector search sử dụng **Storage-Attached Index** để lập cấu trúc tra cứu embedding. Bảng có cột `vector<float,3>` **mà chưa tạo SAI vector index** vẫn có thể lưu và đọc embedding theo primary key, nhưng không tự cung cấp đường tìm ANN như ví dụ.

Một SAI vector index là một thành phần có chi phí:

- Ghi thêm dữ liệu và index structures.
- Tăng nhu cầu RAM/disk và chi phí build/backfill khi tạo index trên dữ liệu đã có.
- Tác động tới compaction và vận hành SSTable/index.
- Có giới hạn truy vấn, metric và tính tương thích theo bản phát hành.

**SAI không thay thế partition key.** Bảng vẫn có primary key để phân phối và cập nhật row; ANN là một **đường truy vấn bổ sung** phục vụ similarity search.

## 5. Thực hành CQL: bảng embedding và tìm ANN

Ví dụ dưới đây dùng **3 chiều** để người học có thể nhập giá trị thủ công. Đây **không phải embedding từ một model thật**; các con số chỉ minh họa cú pháp CQL trên một cluster **Apache Cassandra 5.0 có hỗ trợ SAI vector index**.

### 5.1. Tạo bảng theo ID

~~~cql
CREATE TABLE document_chunks_by_id (
    chunk_id uuid PRIMARY KEY,
    tenant_id uuid,
    document_id uuid,
    chunk_no int,
    embedding_model text,
    content_preview text,
    embedding vector<float, 3>,
    created_at timestamp
);
~~~

Giải thích:

- `chunk_id` làm **partition key**, phục vụ tra cứu chính xác và update/delete từng chunk.
- `tenant_id` dùng để nhận diện chủ sở hữu và quyền truy cập. **Chỉ có cột này chưa tự bảo đảm truy vấn ANN đã được cô lập theo tenant.**
- `document_id`, `chunk_no` liên kết chunk với tài liệu nguồn.
- `embedding_model` ghi danh tính model tạo vector; không so sánh vector từ các model khác nhau một cách tùy tiện.
- `content_preview` chỉ chứa một đoạn ngắn để hiển thị; nội dung lớn có thể lưu ở bảng khác hoặc object storage.
- `embedding` là **cột số fixed-dimension**, không phải ID và không phải clustering key.

### 5.2. Tạo SAI vector index

Theo cú pháp Apache Cassandra 5.0:

~~~cql
CREATE INDEX IF NOT EXISTS chunk_embedding_ann_idx
ON document_chunks_by_id (embedding)
USING 'sai';
~~~

Một cú pháp được tài liệu/driver dùng trong các bản triển khai tương thích là:

~~~cql
-- Phương án cú pháp SAI khác; chọn cú pháp cluster của bạn hỗ trợ.
-- CREATE CUSTOM INDEX chunk_embedding_ann_idx
-- ON document_chunks_by_id (embedding)
-- USING 'StorageAttachedIndex';
~~~

**Không chạy cả hai lệnh cho cùng một cột chỉ để “an toàn”.** Chọn **một cách tạo SAI** theo phiên bản/triển khai. `IF NOT EXISTS` giúp không tạo trùng theo tên, nhưng không tự chứng minh index hiện có đúng metric/options mà ứng dụng mong muốn.

**Mặc định similarity metric là cosine** theo tài liệu Apache Cassandra 5.0. Nếu cần metric khác, tạo index với `WITH OPTIONS` có cấu hình được hỗ trợ, ví dụ:

~~~cql
-- Chỉ là phương án thay thế khi tạo index, không chạy
-- đồng thời với index cosine ở trên.
-- CREATE INDEX chunk_embedding_dot_idx
-- ON document_chunks_by_id (embedding) USING 'sai'
-- WITH OPTIONS = {'similarity_function': 'DOT_PRODUCT'};
~~~

Metric được chọn tại **index**, không thể giả định thay đổi mỗi request truy vấn sẽ tự đổi cách index tìm neighbor. Để đổi metric, cần xem quy trình **rebuild/drop-recreate index** và đánh giá dữ liệu/model.

### 5.3. Ghi vector có ID ổn định

~~~cql
INSERT INTO document_chunks_by_id (
    chunk_id, tenant_id, document_id, chunk_no,
    embedding_model, content_preview, embedding, created_at
) VALUES (
    11111111-1111-4111-8111-111111111111,
    99999999-9999-4999-8999-999999999999,
    22222222-2222-4222-8222-222222222222,
    0,
    'demo-3d-v1',
    'Cassandra chia dữ liệu theo partition key',
    [0.90, 0.10, 0.05],
    '2026-11-21T08:00:00Z'
);

INSERT INTO document_chunks_by_id (
    chunk_id, tenant_id, document_id, chunk_no,
    embedding_model, content_preview, embedding, created_at
) VALUES (
    33333333-3333-4333-8333-333333333333,
    99999999-9999-4999-8999-999999999999,
    22222222-2222-4222-8222-222222222222,
    1,
    'demo-3d-v1',
    'SAI hỗ trợ tìm các vector tương tự',
    [0.75, 0.20, 0.10],
    '2026-11-21T08:01:00Z'
);

INSERT INTO document_chunks_by_id (
    chunk_id, tenant_id, document_id, chunk_no,
    embedding_model, content_preview, embedding, created_at
) VALUES (
    44444444-4444-4444-8444-444444444444,
    99999999-9999-4999-8999-999999999999,
    55555555-5555-4555-8555-555555555555,
    0,
    'demo-3d-v1',
    'Độ trễ mạng ảnh hưởng hệ thống phân tán',
    [0.05, 0.80, 0.55],
    '2026-11-21T08:02:00Z'
);
~~~

Các UUID minh họa được chọn cố định. Trong ứng dụng thực tế, cấp `chunk_id` **một lần** trước khi ghi và dùng lại khi retry; nếu sinh lại ID sau timeout, cùng một đoạn có thể trở thành **hai row**, ảnh hưởng cả độ chính xác tìm kiếm và dung lượng index.

### 5.4. Truy vấn ANN

~~~cql
SELECT chunk_id, document_id, content_preview
FROM document_chunks_by_id
ORDER BY embedding ANN OF [0.85, 0.15, 0.10]
LIMIT 3;
~~~

Cú pháp quan trọng:

- `ORDER BY embedding ANN OF [...]` yêu cầu tìm vector **gần vector truy vấn** theo index/metric.
- `LIMIT 3` giới hạn số kết quả yêu cầu; **Apache Cassandra 5.0** mô tả **`LIMIT` tối đa 1000** cho ANN trong tài liệu hướng dẫn.
- Không cần biết `chunk_id` để thực hiện dạng ANN toàn index; khác với tra cứu partition key.
- Thứ tự ANN **không** là `CLUSTERING ORDER BY` của primary key. Đây là cú pháp tìm kiếm chuyên biệt dựa trên SAI.

Truy vấn sau vẫn hữu ích cho lookup chính xác:

~~~cql
SELECT embedding_model, embedding, content_preview
FROM document_chunks_by_id
WHERE chunk_id = 11111111-1111-4111-8111-111111111111;
~~~

Hai đường truy cập có mục tiêu khác nhau; nên giữ cả hai trong thiết kế khi nghiệp vụ cần **đọc đúng chunk** và **tìm chunk tương tự**.

### 5.5. Tính điểm similarity khi cần giải thích kết quả

Apache Cassandra 5.0 có các hàm số học trên float vector:

~~~cql
SELECT chunk_id,
       content_preview,
       similarity_cosine(embedding, [0.85, 0.15, 0.10]) AS score
FROM document_chunks_by_id
ORDER BY embedding ANN OF [0.85, 0.15, 0.10]
LIMIT 3;
~~~

Những hàm được tài liệu Cassandra nêu gồm:

- `similarity_cosine(vector, vector)`
- `similarity_dot_product(vector, vector)`
- `similarity_euclidean(vector, vector)`

**Không giả định mọi điểm score là cùng một khoảng thang hoặc có thể so sánh trực tiếp giữa các metric.** Các hàm `similarity_...` của Cassandra có quy ước trả về **điểm similarity** theo cách triển khai, không nhất thiết là công thức khoảng cách Euclidean thô mà ứng dụng tự tính. Để đánh giá chất lượng tìm kiếm, phải định nghĩa metric và cách diễn giải score rõ ràng.

## 6. Metric: cosine, dot product hay Euclidean?

Ba metric phổ biến có vai trò khác nhau:

| Metric trong index | Ý nghĩa trực giác | Khi phù hợp | Cần lưu ý |
|---|---|---|---|
| **COSINE** | Ưu tiên các vector có **hướng** giống nhau | Embedding ngôn ngữ/ngữ nghĩa, nếu norm có thể khác | Norm 0 không phù hợp cho cosine; kết quả gần đúng |
| **DOT_PRODUCT** | Tích vô hướng của các thành phần | Khi embedding đã được **chuẩn hóa L2** và mô hình/metric yêu cầu | Với vector không chuẩn hóa, độ dài vector làm lệch xếp hạng |
| **EUCLIDEAN** | Khoảng cách hình học trong không gian vector | Khi khoảng cách tuyệt đối có ý nghĩa | Kết quả nhạy với scale/chuẩn hóa từng chiều |

Với hai vector đơn vị, **cosine similarity và dot product** dẫn tới thứ tự tương tự nhau trong các bài toán thông thường. Nhưng nếu một vector có norm lớn hơn, dot product không còn phản ánh riêng góc giữa hai vector.

Định nghĩa L2-normalization:

\[
\hat{\mathbf v} = \frac{\mathbf v}{\|\mathbf v\|_2},
\qquad
\|\mathbf v\|_2 = \sqrt{\sum_i v_i^2}
\]

Khi \(\|\mathbf v\|_2 = 0\), phép chia không xác định; cần xử lý vector 0 trước khi lưu/truy vấn. Số thực float còn có lỗi làm tròn và rủi ro overflow/underflow, nên ứng dụng cần validation.

Ví dụ Java normalize đơn giản một vector:

~~~java
import java.util.ArrayList;
import java.util.List;

static List<Float> unitVector(List<Float> values) {
    double sumSquares = 0.0;
    for (Float value : values) {
        if (value == null || !Float.isFinite(value)) {
            throw new IllegalArgumentException("Embedding có giá trị không hợp lệ");
        }
        sumSquares += (double) value * value;
    }
    double norm = Math.sqrt(sumSquares);
    if (!(norm > 0.0) || !Double.isFinite(norm)) {
        throw new IllegalArgumentException("Không thể chuẩn hóa vector 0");
    }
    List<Float> result = new ArrayList<>(values.size());
    for (float value : values) {
        result.add((float) (value / norm));
    }
    return result;
}
~~~

Đây là ví dụ **quy tắc số học**, không phải yêu cầu mọi embedding đều phải được normalization. Chỉ normalize theo đúng hợp đồng mô hình và metric đã chọn. Nếu mô hình trả vector đã được chuẩn hóa, cần tránh biến đổi lần nữa khi điều đó làm sai pipeline/độ chính xác.

## 7. Java Driver 4.17+/4.19: CqlVector<Float>

### 7.1. Vector không phải List<Float> trong driver

Ở Java Driver có hỗ trợ CQL vector, kiểu ánh xạ mặc định là **`com.datastax.oss.driver.api.core.data.CqlVector<T>`**. Đối với `vector<float,3>`, dùng **`CqlVector<Float>`**.

Các API cần biết:

| Thao tác | Java Driver có hỗ trợ vector |
|---|---|
| Tạo giá trị 3 chiều | `CqlVector.newInstance(0.90f, 0.10f, 0.05f)` |
| Tạo từ danh sách | `CqlVector.newInstance(List<Float>)` |
| Ghi một cột vector | `setVector(index, value, Float.class)` |
| Đọc vector | `row.getVector("embedding", Float.class)` |
| Kiểm tra số chiều | `vector.size()` |
| Lấy tọa độ một chiều | `vector.get(index)` |
| Codec cho `float[]` | `ExtraTypeCodecs.floatVectorToArray(dim)` nếu được đăng ký/dùng tường minh |

**Cảnh báo phiên bản:** tài liệu driver 4.17 mô tả việc cập nhật API vector; các ví dụ dùng `CqlVector.newInstance` cần dependency có phương thức đó. Đừng copy đoạn code sang một driver 4.x cũ rồi cho rằng mọi nhánh 4.x có cùng API.

`CqlVector.newInstance(List)` có thể **bọc trực tiếp** một `ArrayList` mà không copy phần tử, và `CqlVector` có khả năng thay đổi qua `set(index, value)`. Nếu ứng dụng gửi statement bất đồng bộ, tránh sửa list/vector sau khi bind; tạo bản sao ổn định nếu dữ liệu có vòng đời chia sẻ giữa các thread.

### 7.2. Ghi vector bằng prepared statement

Giả sử `session` là `CqlSession` đã kết nối tới cluster/keyspace chứa bảng `document_chunks_by_id`:

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.data.CqlVector;

import java.time.Instant;
import java.util.UUID;

// CqlSession session = ...; // Khởi tạo theo cấu hình môi trường.

UUID chunkId =
    UUID.fromString("11111111-1111-4111-8111-111111111111");
UUID tenantId =
    UUID.fromString("99999999-9999-4999-8999-999999999999");
UUID documentId =
    UUID.fromString("22222222-2222-4222-8222-222222222222");

CqlVector<Float> embedding =
    CqlVector.newInstance(0.90f, 0.10f, 0.05f);

if (embedding.size() != 3) {
    throw new IllegalArgumentException("Vector phải có 3 chiều");
}

PreparedStatement insert = session.prepare(
    "INSERT INTO document_chunks_by_id "
  + "(chunk_id, tenant_id, document_id, chunk_no, "
  + " embedding_model, content_preview, embedding, created_at) "
  + "VALUES (?, ?, ?, ?, ?, ?, ?, ?)");

BoundStatement bound = insert.boundStatementBuilder()
    .setUuid(0, chunkId)
    .setUuid(1, tenantId)
    .setUuid(2, documentId)
    .setInt(3, 0)
    .setString(4, "demo-3d-v1")
    .setString(5, "Cassandra chia dữ liệu theo partition key")
    .setVector(6, embedding, Float.class)
    .setInstant(7, Instant.parse("2026-11-21T08:00:00Z"))
    .build();

session.execute(bound);
~~~

Dùng prepared statement giúp driver bind giá trị theo codec của **cột `vector<float,3>`**. Trên đường ghi thực tế, thực hiện validation trước: model name, dimension, finite floats, norm nếu có, quyền tenant, giới hạn kích thước payload và ID ổn định.

### 7.3. Đọc CqlVector từ Row

~~~java
import com.datastax.oss.driver.api.core.cql.Row;
import com.datastax.oss.driver.api.core.data.CqlVector;

PreparedStatement byId = session.prepare(
    "SELECT embedding_model, embedding, content_preview "
  + "FROM document_chunks_by_id WHERE chunk_id = ?");

Row row = session.execute(byId.bind(chunkId)).one();
if (row != null && !row.isNull("embedding")) {
    CqlVector<Float> stored = row.getVector("embedding", Float.class);
    int dimension = stored.size();
    float first = stored.get(0);
    String model = row.getString("embedding_model");
}
~~~

Một row có thể tồn tại nhưng **chưa được ghi cột embedding**. Điều này khác với **vector chứa phần tử NULL** (không hợp lệ). Khi chỉ ingest metadata trước, có thể để cột embedding chưa được lưu và bổ sung bằng UPDATE sau; nhưng khi index/search, các row không có vector sống **không cung cấp một điểm số ANN hữu ích**.

### 7.4. Truy vấn ANN qua Java

Prepared statement cho truy vấn dùng một **bind marker** cho vector ANN. Cần xác nhận driver/cluster đang dùng hỗ trợ parser và codec phù hợp:

~~~java
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;
import com.datastax.oss.driver.api.core.data.CqlVector;
import java.util.UUID;

CqlVector<Float> queryVector =
    CqlVector.newInstance(0.85f, 0.15f, 0.10f);

PreparedStatement ann = session.prepare(
    "SELECT chunk_id, document_id, content_preview "
  + "FROM document_chunks_by_id "
  + "ORDER BY embedding ANN OF ? LIMIT 3");

for (Row hit : session.execute(
        ann.boundStatementBuilder()
           .setVector(0, queryVector, Float.class)
           .build())) {

    UUID matchedId = hit.getUuid("chunk_id");
    String preview = hit.getString("content_preview");
}
~~~

**Lưu ý vận hành:** ANN trên Cassandra 5.0 có các ràng buộc riêng về consistency level, paging và các điều kiện lọc ở một số bản build. Không mặc định một đoạn code truy vấn ANN chạy được với **cấu hình paging hoặc `LOCAL_QUORUM` giống các câu SELECT theo partition key khác**. Thử đúng phiên bản đang dùng và cấu hình CL được hỗ trợ; khi đưa vào production phải đánh giá trạng thái hỗ trợ của bản phân phối, thay vì chỉ coi truy vấn trả về 3 dòng là xong.

### 7.5. Truyền float[] có được không?

Theo tài liệu Java Driver 4.18+/4.19, có codec `ExtraTypeCodecs.floatVectorToArray(int dimensions)` cho trường hợp Java thích làm việc với **`float[]`**. Nhưng đây là **codec sử dụng tường minh**, không có nghĩa `setList` với một `float[]` sẽ tự động biến thành CQL vector.

Với ví dụ học tập, `CqlVector<Float>` rõ ràng nhất; với pipeline ML/hiệu năng lớn, có thể cân nhắc codec mảng float và kiểm thử việc copy dữ liệu, heap/off-heap, GC và tương thích phiên bản.

## 8. Không trộn các mô hình embeddings bằng một index tùy tiện

Giả sử một hệ thống có hai mô hình:

- `model-v1` tạo vector 384 chiều.
- `model-v2` tạo vector 768 chiều.

Không thể lưu cả hai vào **cùng một cột `vector<float,384>`**. Đổi model có số chiều khác nghĩa là **đổi schema/đường truy vấn**, không phải chỉ đổi metadata.

Ngay cả khi hai model đều tạo 384 chiều, chúng có thể **không nằm cùng không gian vector**. Nếu index trộn vector v1/v2, top-k gần đúng có thể không phản ánh đúng ngữ nghĩa. Những phương án thực tế:

1. **Bảng/index riêng theo model version**, ví dụ `chunks_embedding_v1_by_id` và `chunks_embedding_v2_by_id`.
2. **Cột vector mới + index mới** trong cùng bảng nếu việc migration và truy vấn có thể quản trị rõ ràng, nhưng không dùng một index để trộn các không gian embedding khác nhau.
3. **Dual-write/dual-read có thời hạn** trong giai đoạn chuyển đổi: ứng dụng biết truy vấn dùng model nào và chọn index nào.
4. **Backfill từ nội dung nguồn** bằng đúng model/phiên bản, kiểm tra `content_hash` và snapshot nguồn.
5. **Dừng query đường cũ và dọn dẹp** khi dữ liệu, index và độ chính xác của đường mới đã được xác minh.

**Không kỳ vọng `ALTER TABLE ... ALTER embedding TYPE vector<float,768>` là một migration in-place an toàn**. Thay đổi kích thước kiểu vector cần kế hoạch tạo schema/index mới và chuyển dữ liệu tương ứng theo khả năng thực tế của cluster.

### 8.1. Thiết kế ID cho chunk và idempotency

Một document có thể được chia nhiều chunk. Hãy dùng khóa ổn định:

~~~text
tenant_id
document_id
source_revision
chunk_no / chunk_id
embedding_model_version
~~~

Nếu worker embedding timeout rồi chạy lại, **giữ cùng chunk ID cho cùng bản nội dung và model**. Nếu mỗi retry tạo một UUID mới, cùng đoạn có thể xuất hiện nhiều lần trong ANN results, ảnh hưởng recall/precision và chi phí index.

Với dữ liệu được chỉnh sửa, thay nội dung nguồn cần kéo theo **re-embedding**. Không để text đã đổi nhưng embedding vẫn là bản cũ, vì kết quả ANN sẽ trỏ tới mô tả không còn đại diện cho vector.

## 9. Thiết kế bảng theo truy vấn: vector không thay partition key

Một ứng dụng tìm kiếm tài liệu thường có **ít nhất hai đường đọc**:

1. **Tra cứu chính xác và liệt kê chunk của một tài liệu**: biết `tenant_id` và `document_id`.
2. **Tìm những chunk tương tự với một câu hỏi**: dùng ANN index và quyền tenant.

Hai đường có thể cần hai bảng/loại index khác nhau.

### 9.1. Bảng duyệt chunk theo tài liệu

~~~cql
CREATE TABLE document_chunks_by_document (
    tenant_id uuid,
    document_id uuid,
    chunk_no int,
    chunk_id uuid,
    source_revision text,
    content_preview text,
    PRIMARY KEY ((tenant_id, document_id), chunk_no)
) WITH CLUSTERING ORDER BY (chunk_no ASC);
~~~

Truy vấn để tái dựng thứ tự chunk của một tài liệu:

~~~cql
SELECT chunk_no, chunk_id, content_preview
FROM document_chunks_by_document
WHERE tenant_id = 99999999-9999-4999-8999-999999999999
  AND document_id = 22222222-2222-4222-8222-222222222222;
~~~

Bảng này **không có vector index**, vì nó chỉ phục vụ đọc chính xác theo partition. Bảng `document_chunks_by_id` có vector/SAI phục vụ lookup theo ID và ANN; nếu cùng dữ liệu xuất hiện trong hai bảng, ứng dụng cần quy trình **đồng bộ, retry, đối soát**.

### 9.2. Ranh giới tenant và ACL phải được thực thi

Ví dụ ANN đơn giản ở phần 5 tìm kiếm trên dữ liệu được index trong bảng. Nếu có nhiều tenant:

- Không đưa kết quả từ tenant khác vào UI chỉ vì ANN tìm thấy vector gần.
- Kiểm tra khả năng **lọc theo tenant trong ANN query** của đúng Cassandra 5.0 patch/bản phân phối. Điều kiện `WHERE` có thể yêu cầu partition key hoặc index thích hợp.
- Nếu cơ chế filter được hỗ trợ, cần đo recall/latency khi filter có độ chọn lọc cao hoặc thấp.
- Nếu không hỗ trợ bộ lọc cần thiết, cân nhắc kiến trúc **phân tách dữ liệu/index** hoặc công cụ search đáp ứng điều kiện; **không** coi lọc kết quả sau `LIMIT k` là tương đương tìm top-k trong riêng tenant.

Ví dụ: ANN toàn bảng trả top 5 nhưng 4 kết quả thuộc tenant khác. Loại 4 kết quả đó sau khi truy vấn chỉ còn 1, dù có thể còn nhiều kết quả tốt thuộc tenant hợp lệ ở hạng 6–50. Đó là khác biệt giữa **lọc trước/đồng thời với tìm kiếm** và **lọc sau top-k**.

Với hệ RAG, ngoài tenant còn có ACL theo document, classification, retention và quyền người dùng. Vector index không tự là một hệ thống quản lý quyền truy cập.

### 9.3. Search không đồng nghĩa fact lookup

Khi câu hỏi là “lấy đúng văn bản điều khoản của hợp đồng X”, dùng **primary key/ID của hợp đồng** và phiên bản đã xác minh. ANN phù hợp cho “tìm đoạn liên quan”, nhưng không thay cho nguồn sự thật để tính tiền, cấp quyền hay quyết định tuân thủ.

Một luồng RAG an toàn hơn:

~~~text
Câu hỏi người dùng
  -> Kiểm tra tenant/ACL/quyền dữ liệu
  -> Chuẩn hóa/chunk/embedding theo model đã đăng ký
  -> Truy vấn ANN theo phạm vi được phép
  -> Kiểm tra/rerank kết quả và lấy nội dung nguồn theo ID
  -> Gắn nguồn, phiên bản và đánh giá tính phù hợp
  -> Tạo câu trả lời từ ngữ cảnh được phép
~~~

Quá trình này cần tách rõ **model search score** với **kết luận thực tế**. Top-k ANN chỉ là ứng viên, không phải xác nhận nội dung đúng.

## 10. ANN có các giới hạn khác SELECT theo partition key

Trong tài liệu **Apache Cassandra 5.0**, ANN có các lưu ý:

- **Phải có SAI index** trên cột vector float được truy vấn.
- **`LIMIT` là bắt buộc** và tài liệu working-with vector search mô tả mức giới hạn tối đa **1000**.
- ANN là **approximate nearest neighbors**, không phải exact KNN toàn bộ dữ liệu.
- Không hỗ trợ kiểu truy vấn “least similar” như một biến thể đối xứng mặc định.
- Thao tác **overwrite/delete vector thường xuyên** có thể làm tìm kiếm chậm hơn so với workload thêm dữ liệu tương đối ổn định.
- **Những tổ hợp filter, consistency, paging, grouping** phụ thuộc giới hạn của bản build. Một số mã nguồn Apache Cassandra 5.0 còn cảnh báo tính năng ANN/SAI vector **experimental** và hạn chế consistency cao hơn `ONE/LOCAL_ONE`, paging và các dạng truy vấn bổ sung. Phải xác minh bản build cụ thể **trước khi dùng production**.

Vì vậy, không áp dụng máy móc các thói quen sau vào ANN:

~~~cql
-- Không suy rằng mọi kiểu truy vấn phổ biến đều chạy với ANN:
-- SELECT ... FROM ... ORDER BY embedding ANN OF [..];
-- SELECT ... FROM ... ORDER BY embedding ANN OF [..] LIMIT 100000;
-- SELECT ... FROM ... ORDER BY embedding ANN OF [..]
--   PER PARTITION LIMIT 10;
~~~

Một câu truy vấn không được parser hỗ trợ **không nên** được “sửa” bằng `ALLOW FILTERING` trong production. `ALLOW FILTERING` không cấp thêm index ANN và có thể phát sinh chi phí không dự đoán được ở những truy vấn khác.

Trước khi triển khai, tạo một **bộ acceptance tests** cho toàn bộ truy vấn ANN thực tế: có/không có `WHERE`, metric, `LIMIT`, CL, paging, schema/index lifecycle, dữ liệu bị delete/TTL và khả năng phục hồi sau node failure.

## 11. Replication, consistency, tombstone, compaction và repair với vector

### 11.1. Replication không làm ANN trở thành giao dịch ACID

Cassandra vẫn phân phối row theo **partition key** và sao chép theo replication strategy. Một embedding trong cột `vector` là **dữ liệu được replica lưu trữ**. SAI tạo thêm các cấu trúc index phục vụ ANN, nhưng không thay thế quy tắc consistency, primary key hay mô hình cập nhật cell.

Các câu hỏi cần thiết:

- Ghi thành công tại bao nhiêu replica trước khi client xác nhận?
- Truy vấn ANN chạy với **consistency level nào được phiên bản hỗ trợ**?
- Thời điểm vừa ghi xong, chỉ mục đã sẵn sàng/hiển thị kết quả ở mọi đường đọc hay chưa?
- Khi một node hoặc index bị rebuild, số lượng/kết quả ANN thay đổi như thế nào?

**Không mặc định rằng truy vấn ANN có cùng các bảo đảm đọc/ghi như `SELECT ... WHERE primary_key=?` ở `LOCAL_QUORUM`.** Đối với yêu cầu read-your-writes và quan trọng về độ chính xác, phải benchmark và kiểm thử consistency trên chính cluster.

### 11.2. Update/delete vector và tombstone

Một `UPDATE ... SET embedding = [ ... ]` thay **toàn bộ vector**; nó không thay từng chiều. Xóa cột hoặc xóa row có thể tạo tombstone; TTL hết hạn cũng có thể làm dữ liệu biến mất theo quy tắc Cassandra.

Chỉ mục cần phản ánh các phiên bản vector đang sống và các xóa/ghi mới. Workload viết lại embedding hàng loạt có thể tăng chi phí index, SSTable và compaction. Nếu ứng dụng thường xuyên đổi model, nên cân nhắc **bảng/index theo model version** và chuyển luồng truy vấn có kiểm soát hơn là overwrite liên tục trên một cột.

### 11.3. Compaction, repair và giới hạn bộ nhớ

- **Compaction** tổ chức lại SSTable và các dữ liệu/index liên quan, có chi phí CPU, disk I/O và ghi thêm dữ liệu; cần quan sát khi vừa backfill hàng triệu embedding.
- **Repair** giúp replica hội tụ trạng thái dữ liệu, nhưng không tự sửa embedding được tạo bằng sai model hoặc sai preprocessing.
- **Replication factor** tăng bản sao dữ liệu và tổng chi phí lưu vector/index; quy hoạch dung lượng theo từng replica, disk tier, RAM và tốc độ index build.
- **GC/heap/off-heap** của client Java và node Cassandra có thể chịu áp lực nếu mỗi query hoặc batch mang vector rất nhiều chiều; cần đo p95/p99 latency, QPS, bộ nhớ và kích thước payload.

Không dùng một giới hạn hard-coded tùy tiện cho batch như “ghi 10.000 vector trong một BATCH” với kỳ vọng nhanh hơn. Cassandra `BATCH` không phải bulk loader tổng quát; nên chọn tốc độ ingest, concurrency và backpressure phù hợp cluster.

### 11.4. Monitoring riêng cho search quality

Ngoài metric cơ sở dữ liệu (latency, throughput, disk, tombstone, compaction, repair), ứng dụng search cần thêm:

- **Recall@k** so với một tập ground-truth/brute force kiểm thử.
- **Precision@k** hoặc tỷ lệ đánh giá relevance của người dùng.
- **Latency p50/p95/p99** cho từng bộ lọc tenant/metric.
- **Tỷ lệ kết quả rỗng, timeout, dimension errors** và lỗi codec.
- **Drift theo phiên bản model** và độ phủ embeddings: số chunk có/không có vector.
- **Chất lượng index sau reindex/compaction** và khi node bị sự cố.

Một search pipeline có thể có latency tốt nhưng trả kết quả sai ngữ nghĩa nếu model hoặc preprocessing không khớp. Kiểm thử tính đúng ở tầng ứng dụng không thể bị thay bằng việc “query CQL chạy thành công”.

## 12. Hỗ trợ tương thích khi cluster chưa có vector

Nếu cluster là Cassandra 4.x hoặc một bản phân phối chưa cung cấp `vector`/SAI ANN, có một số hướng thực hiện khác. **Đừng coi chúng tương đương toàn bộ**.

| Phương án | Lợi thế | Giới hạn |
|---|---|---|
| **Nâng lên Cassandra hỗ trợ vector** | Giữ dữ liệu và truy vấn ANN trong công nghệ Cassandra nếu tính năng đáp ứng SLA | Cần migration/rolling upgrade, tương thích driver và đánh giá ANN production |
| **Lưu `list<float>`** | Có thể lưu một dãy số trên cluster cũ | Không có ràng buộc fixed-dimension từ kiểu; **không tự có ANN index** |
| **Lưu `blob`** chứa bytes float | Gọn theo định dạng riêng, có thể dùng codec ngoài | Phải định nghĩa endian/schema/normalization; **không tự có ANN search** |
| **Tách vector sang hệ vector search chuyên biệt** | Có thể có ANN/filter/index lifecycle phù hợp hơn | Đồng bộ ID, version và dữ liệu giữa hệ thống |
| **Brute force ở ứng dụng** cho dataset nhỏ | Dễ kiểm chứng kết quả exact trên tập nhỏ | Chi phí tăng tuyến tính theo số vector; không phù hợp tập lớn nếu không giới hạn |

Ví dụ lưu raw vector dạng `blob` cần quy định **float32**, **thứ tự byte**, **chiều N**, **model version**, **endianness** và cách đọc. Nhưng Cassandra không thể tự diễn giải bytes đó thành cột `vector<float,N>` hoặc SAI vector index trước khi bạn **migrate/schema đổi**.

Nếu dùng `list<float>`, nó cũng không tự trở thành ANN index khi nâng cấp. Chuyển sang kiểu vector cần **tạo cột/bảng mới, validate N, convert và backfill**. Đây là migration thực sự, không phải đổi tên kiểu trong code Java.

## 13. Kế hoạch migration vector an toàn theo phiên bản

Một quy trình triển khai nên theo nhiều giai đoạn:

### Giai đoạn 1 — Kiểm kê và thử trong môi trường phù hợp

Xác nhận:

- Phiên bản Apache Cassandra của **mọi node** và trạng thái schema agreement.
- Bản phân phối/managed service có thực sự hỗ trợ `vector`, `SAI`, `ANN OF` và metric cần dùng?
- Bản Java Driver có `CqlVector` và codec tương thích?
- Số chiều, model, phân phối giá trị/norm, kích thước dữ liệu, mục tiêu recall/latency.

Tạo **bảng thử riêng** trên môi trường tương thích và chạy một bộ ví dụ vector 3 chiều. Đừng đưa cú pháp mới vào một migration chạy chung cho cả cluster cũ.

### Giai đoạn 2 — Tạo schema/index mới

Tạo cột/bảng vector cùng **phiên bản model**. Chọn khóa tra cứu chính xác, kiểm soát quyền tenant, kiểu metadata và index. Chỉ tạo index sau khi xác nhận các giới hạn tương thích và metric cần dùng.

Nếu tạo index trên bảng đã có dữ liệu, chuẩn bị tài nguyên cho **index build/backfill**. Có cơ chế rollback ở tầng ứng dụng; không mặc định drop index là tác động bằng không.

### Giai đoạn 3 — Backfill có giới hạn và chống ghi trùng

- Sinh embedding từ nguồn nội dung đáng tin cậy.
- Gắn `chunk_id`, `source_revision`, `embedding_model` và content hash ổn định.
- Kiểm tra đúng số chiều, dữ liệu hữu hạn, normalization.
- Ghi theo throughput có giới hạn, backpressure và retry bằng cùng ID.
- Đếm số chunk nguồn so với số chunk đã có embedding; phân loại lỗi không thể recover.

Nếu model đã đổi, không tráo vector cùng số chiều mà bỏ phiên bản, vì chất lượng search không còn kiểm chứng được.

### Giai đoạn 4 — Dual-read/đánh giá

Trong một thời gian có thể cần giữ đường tìm kiếm cũ và mới:

- Chạy cùng query set để so chất lượng top-k.
- Kiểm tra ACL, filter theo tenant, kết quả trống, timeout.
- Đo read/write p95/p99, index build/compaction và ảnh hưởng tới các bảng Cassandra khác.
- Đánh giá đồng bộ nội dung ↔ embedding khi người dùng cập nhật/xóa dữ liệu.
- Xác nhận đường fallback khi ANN hoặc index unavailable.

### Giai đoạn 5 — Chuyển và dọn dữ liệu

Chỉ chuyển truy vấn production khi đạt các tiêu chí chất lượng và vận hành. Sau đó lên lịch dọn cột/index/bảng cũ theo retention và audit. Các tombstone và tài nguyên index không biến mất tức thì chỉ vì đã ngừng query đường cũ.

Nếu cluster không đáp ứng yêu cầu consistency/query của ANN, cân nhắc giữ Cassandra cho dữ liệu nghiệp vụ và dùng một hệ tìm kiếm phù hợp hơn. Không bắt buộc sử dụng vector chỉ vì phiên bản mới có kiểu đó.

## 14. Các lỗi thường gặp

| Sai lầm | Hậu quả | Cách sửa |
|---|---|---|
| Chạy `CREATE TABLE ... vector<float,n>` trên Cassandra 4.1 | Lỗi cú pháp/unsupported type | Kiểm tra version, nâng cấp hoặc thiết kế thay thế |
| Nghĩ `list<float>` tương đương `vector<float,n>` | Không kiểm soát N và không có index ANN | Dùng vector đúng schema khi phiên bản hỗ trợ |
| Lưu vector sai chiều | Ghi/bind lỗi | Validate kích thước trước khi gửi |
| Cho phép null trong vector | Không hợp lệ ở cấp phần tử | Loại dữ liệu thiếu hoặc tính embedding hoàn chỉnh |
| Dùng `vector<int,n>` rồi tạo ANN index | Vector search yêu cầu float vector | Dùng `vector<float,n>` cho embedding ANN |
| Trộn embeddings từ hai model cùng số chiều | Search gần về số nhưng sai ngữ nghĩa | Tách index theo model/version |
| Chọn dot product cho vector chưa chuẩn hóa | Norm làm lệch xếp hạng | Normalize hoặc chọn metric phù hợp |
| Coi ANN là exact top-k | Thiếu ứng viên đúng do approximate retrieval | Đánh giá recall@k, rerank khi cần |
| Tìm ANN nhưng chưa tạo SAI | Không có đường vector search hợp lệ | Tạo SAI theo phiên bản/metric |
| Query ANN không LIMIT hoặc LIMIT rất lớn | Không phù hợp giới hạn truy vấn | Dùng giới hạn được hỗ trợ và benchmark |
| Lấy ANN toàn tenant rồi lọc quyền sau `LIMIT` | Có thể thiếu kết quả hợp lệ, nguy cơ lộ dữ liệu | Thiết kế lọc trước/trong search và kiểm soát ACL |
| Dùng CL/paging của SELECT thường cho ANN không kiểm tra | Có thể bị từ chối hoặc sai giả định | Test giới hạn đúng bản build |
| Ghi đè vector nhiều lần trong ingest/rebuild | Chi phí index/compaction tăng | Bảng/index theo version, backfill theo luồng |
| Sinh chunk UUID mới mỗi retry | Trùng đoạn trong ANN và tăng index | ID ổn định theo chunk/revision/model |
| Coi float embedding là phép đối soát chính xác | Sai số IEEE 754 và semantic | Dữ liệu tiền dùng decimal/bigint, embedding dùng float |
| Nâng model mới rồi chỉ đổi metadata | Vector cũ vẫn ở không gian model cũ | Re-embedding và chuyển index có kiểm chứng |
| Quên phiên bản driver | Không có codec/API `CqlVector` | Test dependency thực tế, upgrade driver |
| Đọc tài liệu vendor rồi áp giới hạn cho Apache Cassandra | Giới hạn/cú pháp khác nhau | Kiểm tra tài liệu server/bản phân phối cụ thể |

## 15. Bài tập thực hành

### Bài 1 — Chọn kiểu phù hợp

Một hệ thống cần lưu 5 thuộc tính float và so sánh theo ANN trên Cassandra 5.0; hệ thống khác chỉ cần một list điểm kiểm tra độ dài thay đổi.

**Đáp án:** với trường hợp thứ nhất, dùng `vector<float,5>` kèm SAI vector index nếu ANN được bản triển khai hỗ trợ; trường hợp thứ hai có thể dùng `list<float>` nếu số phần tử nhỏ và có biên, hoặc bảng nhiều hàng nếu tăng vô hạn. Không dùng `list<float>` để giả lập vector search.

### Bài 2 — Vì sao sai chiều?

Schema:

~~~cql
CREATE TABLE exercise_embeddings (
    id uuid PRIMARY KEY,
    embedding vector<float, 3>
);
~~~

Một service gửi `[0.1, 0.2]` còn service khác gửi `[0.1, 0.2, null]`. Trường hợp nào ghi hợp lệ?

**Đáp án:** **không trường hợp nào**. Vector phải có **đúng 3 phần tử** và các phần tử **không được NULL**.

### Bài 3 — Query ANN

Bảng `exercise_embeddings` đã có SAI vector index. Viết câu truy vấn tìm ba điểm gần `[0.2, 0.4, 0.6]`:

~~~cql
SELECT id, embedding
FROM exercise_embeddings
ORDER BY embedding ANN OF [0.2, 0.4, 0.6]
LIMIT 3;
~~~

**Giải thích:** có `ORDER BY ... ANN OF` và `LIMIT`. Đây là **approximate similarity search**, không phải clustering order thông thường.

### Bài 4 — Không gian embedding

Model A và B đều tạo 768 chiều. Đội kỹ thuật đang thay model A bằng B, nhưng vẫn dùng một bảng/index chung và ghi `embedding_model='B'` cho những dòng chưa hề được re-embed.

**Câu hỏi:** vì sao đây là lỗi?

**Đáp án:** vector từ A và B không tự nằm trong cùng một không gian. Đổi metadata không đổi dữ liệu số. Cần backfill/re-embed bằng model B, version và đánh giá index/truy vấn riêng.

### Bài 5 — Tenant filter

ANN toàn bảng trả top 5, có 4 dòng thuộc tenant B và 1 dòng thuộc tenant A. Ứng dụng lọc bỏ tenant B sau truy vấn, rồi kết luận tenant A chỉ có 1 kết quả liên quan.

**Đáp án:** kết luận không đúng: các kết quả của A ở hạng 6 trở đi có thể vẫn liên quan. Cần thiết kế lọc tenant phù hợp **trước hoặc trong** search (theo khả năng phiên bản), đồng thời kiểm soát ACL trước khi trả nội dung.

### Bài 6 — Java Driver

Ứng dụng Java cần bind vector ba chiều vào cột `embedding vector<float,3>`. Dùng `List<Double>` và `setList()` được không?

**Đáp án:** không phải ánh xạ mặc định phù hợp. Dùng `CqlVector<Float>`, ví dụ `CqlVector.newInstance(0.1f,0.2f,0.3f)`, bind với `setVector(index, vector, Float.class)` trên driver hỗ trợ. Kiểm tra dependency, dimension, null và finite values trước khi ghi.

## 16. Checklist triển khai kiểu mới/vector

- [ ] Đã kiểm tra **phiên bản tất cả node** và bản phân phối có hỗ trợ kiểu/tính năng?
- [ ] Java Driver và các dịch vụ liên quan có codec/API `CqlVector` tương thích?
- [ ] Đã phân biệt **lưu vector** với **SAI index + ANN search**?
- [ ] Cột vector có **số chiều cố định** phù hợp model, phần tử không NULL?
- [ ] Pipeline kiểm tra `NaN`, infinity, vector zero và normalization theo metric?
- [ ] Chỉ dùng `vector<float,n>` cho ANN theo hỗ trợ; không dùng `vector<int,n>` như embedding ANN?
- [ ] Có lưu `embedding_model`, revision, source hash và thông tin chunking?
- [ ] Chọn metric **COSINE/DOT_PRODUCT/EUCLIDEAN** phù hợp với mô hình/normalization?
- [ ] ANN có **LIMIT** đúng mức; query/CL/paging/filter được kiểm tra trên đúng bản build?
- [ ] Nếu nhiều tenant, **quyền và filter** được xử lý trước/trong search, không chỉ post-filter top-k?
- [ ] Partition key phục vụ tra ID; đã thiết kế bảng bổ sung nếu cần duyệt chunk theo document?
- [ ] Có bộ benchmark **recall@k, relevance, p95/p99**, không chỉ đo số dòng trả về?
- [ ] Retry ingest giữ cùng `chunk_id`, không tạo duplicate vector vì timeout?
- [ ] Nếu model đổi, có **schema/index versioning, re-embedding, backfill và rollback**?
- [ ] Đã dự toán chi phí SAI, replication, compaction, repair, disk/RAM và retention?
- [ ] Các tính năng đánh dấu experimental/giới hạn trong bản build có được đánh giá trước production?

## Tài liệu tham khảo

- [Apache Cassandra 5.0 — Vector CQL data type](https://cassandra.apache.org/doc/latest/cassandra/reference/vector-data-type.html).
- [Apache Cassandra 5.0 — Working with Vector Search (SAI, ANN, LIMIT, metrics)](https://cassandra.apache.org/doc/latest/cassandra/vector-search/vector-search-working-with.html).
- [Apache Cassandra 5.0 — Vector Search Data Modeling](https://cassandra.apache.org/doc/latest/cassandra/vector-search/data-modeling.html).
- [Apache Cassandra — Working with vectors in CQL](https://cassandra.apache.org/doc/latest/cassandra/developing/cql/types.html).
- [Apache Cassandra Java Driver 4.19 — CqlVector API](https://apache.github.io/cassandra-java-driver/4.19.0/api/com/datastax/oss/driver/api/core/data/CqlVector.html).
- [Apache Cassandra Java Driver 4.19 — Upgrade Guide / vector API](https://apache.github.io/cassandra-java-driver/4.19.0/upgrade-README/).
- [Apache Cassandra Java Driver 4.19 — Custom codecs](https://apache.github.io/cassandra-java-driver/4.19.0/core/custom_codecs/).

**Ghi nhớ:** một kiểu mới như **`vector` phải được chọn theo phiên bản Cassandra, phiên bản Java Driver và tính năng index thực tế**. **`vector<T,N>`** lưu dãy cố định N phần tử không NULL; **`vector<float,N>` kết hợp SAI** phục vụ tìm **ANN gần đúng** khi server hỗ trợ. Nó không thay thế khóa phân vùng, không tạo thứ tự clustering, không chứng minh tính đúng của nội dung và không tự cách ly tenant. Thiết kế tốt cần gắn **model/version, metadata, index, quyền truy cập, retry idempotent và quy trình migration** vào cùng một hợp đồng dữ liệu.

