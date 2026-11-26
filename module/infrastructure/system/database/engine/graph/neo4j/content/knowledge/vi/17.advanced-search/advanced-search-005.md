# Vector index: cấu hình, truy vấn và khả năng theo phiên bản

## 1. Vector index giải quyết bài toán nào?

Trong Neo4j, các node và relationship biểu diễn đối tượng cùng những liên kết của chúng. Index thông thường giúp tìm theo giá trị property hoặc nhãn/loại quan hệ, còn **vector index** hỗ trợ tìm các đối tượng có **embedding gần với vector truy vấn**. Đây là một kỹ thuật quan trọng trong tìm kiếm ngữ nghĩa, gợi ý nội dung và ứng dụng GraphRAG, khi người dùng có thể đặt câu hỏi bằng từ ngữ khác với văn bản đang lưu.

Ví dụ: người học hỏi “Làm sao tìm quan hệ bằng Cypher?” trong khi một tài liệu mang tiêu đề “Truy vấn cạnh trong property graph”. Nếu cùng mô hình embedding biểu diễn hai nội dung tương tự bằng các vector gần nhau, vector search có thể đưa tài liệu đó vào danh sách ứng viên, dù không có chuỗi từ khóa trùng chính xác.

Trong mô-đun `DATABASE_ENGINE_GRAPH_NEO4J`, bài này nằm ở phần **Tìm kiếm nâng cao** và nối tiếp các kiến thức về node, relationship, index và truy vấn Cypher. Mục tiêu là hiểu cách **tạo, cấu hình, truy vấn, kiểm tra và vận hành vector index**, đặc biệt là sự khác biệt giữa các thế hệ Neo4j. Phần minh họa sử dụng vector số học nhỏ có sẵn; không yêu cầu API tạo embedding, LLM, APOC hoặc Graph Data Science.

Sau bài học, bạn có thể:

- Phân biệt embedding, phép đo tương đồng và vector index xấp xỉ.
- Tạo vector index cho node, kiểm tra cấu hình `dimensions`, `similarity_function` và trạng thái `ONLINE`.
- Truy vấn bằng `db.index.vector.queryNodes()` và bằng `SEARCH` khi phiên bản hỗ trợ.
- Giải thích vì sao cùng một bài toán có thể cần cú pháp khác nhau trên Neo4j 5.x và Neo4j 2025–2026.
- Nhận diện các giới hạn của ANN, dữ liệu vector không hợp lệ, sai số chiều, tác động của bộ lọc và thay đổi mô hình embedding.

> **Phạm vi phiên bản:** Bảng tương thích ở mục 3 dựa trên tài liệu Neo4j 5 và tài liệu Cypher hiện hành, đối chiếu đến **25/11/2026**. Các tính năng mới của Cypher 25 và các cấu hình mới phải được kiểm tra với phiên bản Neo4j thực đang chạy, thay vì sao chép toàn bộ ví dụ vào mọi máy chủ.

## 2. Embedding, độ tương đồng và ANN

### 2.1. Embedding là dữ liệu, vector index là cấu trúc tìm kiếm

**Embedding** là dãy số biểu diễn một đối tượng như đoạn văn, ảnh, sản phẩm hoặc cấu trúc đồ thị. Ví dụ dưới đây mô tả hình dạng một node (không phải câu lệnh Cypher chạy độc lập):

~~~text
(:Document {
  id: 'DOC-01',
  title: 'Nhập môn đồ thị',
  embedding: [1.0, 0.0, 0.0]
})
~~~

Trong ứng dụng thật, embedding thường có hàng trăm đến hàng nghìn chiều. Bộ dữ liệu ví dụ dùng **3 chiều** để người học dễ đối chiếu bằng tay; các số này không phải embedding do mô hình AI sinh ra.

**Vector index** nhận vector làm tín hiệu để trả về các node/relationship có vector gần nhất theo một độ đo tương đồng. Neo4j dùng cấu trúc tìm kiếm lân cận gần đúng (ANN, *approximate nearest neighbor*) dựa trên HNSW (*Hierarchical Navigable Small Worlds*). Việc dùng chỉ mục có thể tăng tốc trên tập dữ liệu lớn, đổi lại không bảo đảm luôn trả về đúng tập `k` láng giềng gần nhất theo phép tính chính xác.

### 2.2. Hai hàm tương đồng cơ bản

| Hàm cấu hình index | Ý tưởng | Điểm cần chú ý |
|---|---|---|
| `'cosine'` | So sánh **hướng** của hai vector | Hay dùng cho embedding văn bản; vector không được có độ dài bằng 0 |
| `'euclidean'` | Đánh giá độ gần theo **khoảng cách Euclid** | Độ lớn của vector có ảnh hưởng đến độ gần |

Với vector `a`, `b`, cosine hình học được tính theo:

\[
\cos(\theta)=\frac{a \cdot b}{\|a\|\,\|b\|}
\]

Đây là công thức giải thích **hướng** của hai vector. Điểm `score` do Neo4j trả về sau tìm kiếm được chuẩn hóa theo hàm tương đồng của index, nằm trong khoảng **0 đến 1** và điểm càng lớn biểu thị càng giống; **không phải xác suất** tài liệu có đáp án đúng.

Một ví dụ dễ hình dung với truy vấn `q = [1, 0, 0]`:

| Vector tài liệu | Cosine hình học với q | Diễn giải |
|---|---:|---|
| `[1.0, 0.0, 0.0]` | 1.0 | Cùng hướng |
| `[0.8, 0.6, 0.0]` | 0.8 | Tương tự nhiều |
| `[0.0, 1.0, 0.0]` | 0.0 | Vuông góc |

Thứ tự tương đồng theo cosine là hàng 1, hàng 2, hàng 3. Trong truy vấn index, thứ tự thực tế là **kết quả ANN**, nên có thể khác ở tập lớn hoặc khi `k` gần số lượng vector được index.

### 2.3. Vector index khác gì index và tìm kiếm toàn văn?

| Cơ chế | Tín hiệu chính | Ví dụ |
|---|---|---|
| `RANGE INDEX` | So sánh giá trị property | `WHERE d.id = 'DOC-01'` |
| `TEXT INDEX` | Một số phép lọc chuỗi | `WHERE d.title CONTAINS 'đồ thị'` |
| `FULLTEXT INDEX` | Độ liên quan của từ khóa/chữ viết | Tìm từ “Cypher” trong tiêu đề, nội dung |
| `VECTOR INDEX` | Độ gần giữa các vector | Tìm tài liệu có embedding gần vector câu hỏi |

Vector search **không tự suy luận quan hệ trên đồ thị**. Cách kết hợp thường là tìm nhóm node ứng viên theo vector, sau đó mở rộng `MATCH` theo các relationship, lọc quyền truy cập hoặc áp quy tắc nghiệp vụ.

## 3. Khả năng theo phiên bản: chọn cú pháp trước khi chạy

Neo4j có các mốc quan trọng sau:

| Phiên bản | Thay đổi liên quan đến vector index |
|---|---|
| **5.11–5.12** | Node vector index xuất hiện ở mức **public beta**; tạo node index bằng procedure `db.index.vector.createNodeIndex()`. |
| **5.13–5.14** | Node vector index đạt mức **GA**; vẫn dùng procedure tạo index do cú pháp `CREATE VECTOR INDEX` chưa có. |
| **5.15–5.17** | Có cú pháp Cypher `CREATE VECTOR INDEX` cho node; truy vấn qua `db.index.vector.queryNodes()`. |
| **5.18–5.22** | Thêm vector index cho **relationship** và `db.index.vector.queryRelationships()`; có các hàm `vector.similarity.*` để tính trực tiếp. |
| **5.23 trở đi (nhánh 5.x)** | Có thể bỏ qua `vector.dimensions` và `vector.similarity_function` khi tạo index; hỗ trợ cấu hình HNSW và lượng tử hóa theo khả năng provider. Nên **khai báo dimensions rõ ràng** trong ứng dụng. |
| **2025.10 (Cypher 25)** | Có kiểu property `VECTOR` bên cạnh các property dạng danh sách số `LIST`, tùy edition và định dạng lưu trữ. |
| **2026.01 (Cypher 25)** | Thêm `SEARCH` để truy vấn vector index; hỗ trợ vector index nhiều label/nhiều relationship type và các property bổ sung cho bộ lọc. |
| **2026.04** | `db.index.vector.queryNodes()` và `db.index.vector.queryRelationships()` được đánh dấu **deprecated**; chuyển sang `SEARCH` trên hệ thống hỗ trợ. |
| **2026.06** | Thêm `vector.quantization.type` (`'none'`, `'scalar'`, `'binary'`); `vector.quantization.enabled` được đánh dấu deprecated. |
| **2026.07** | Thêm khả năng tìm kiếm **High Fidelity Quantized** (HFQ) và tùy chọn `vector.default_search_expansion_factor`. |
| **2026.08** | Provider mới tiếp tục phát triển chức năng lượng tử hóa; mặc định `vector.quantization.type` đổi sang `'binary'`. |

**Đọc bảng đúng cách:**

- Cú pháp `CREATE VECTOR INDEX` ở các ví dụ chính phía dưới hướng tới **Neo4j 5.15+**. Nếu đang ở 5.11–5.14, xem mục 10 trước khi tạo.
- Cú pháp `SEARCH` chỉ dùng khi cả **Neo4j 2026.01+** và **Cypher 25** khả dụng; không dùng nó trong môi trường chỉ hỗ trợ Cypher 5.
- Procedure queryNodes/queryRelationships vẫn hữu ích cho dự án cần tương thích phiên bản cũ, nhưng đã bị deprecated trên bản mới. *Deprecated* nghĩa là nên lập kế hoạch chuyển đổi, không đồng nghĩa procedure lập tức biến mất.
- Tên `indexProvider` như `vector-1.0`, `vector-2.0` hay `vector-2026.08` là thông tin về **provider thực tế**; index đã tạo ở bản cũ có thể giữ provider cũ sau nâng cấp. Đừng suy tính năng index chỉ từ phiên bản server.

> **Edition:** Vector index trên các property dạng `LIST<INTEGER | FLOAT>` có thể dùng ở cả Community và Enterprise Edition. Kiểu `VECTOR` native cần định dạng lưu trữ **block**, có trên Enterprise/Aura. Nếu mục tiêu là một bài tập tương thích rộng, dùng danh sách số như ví dụ dưới đây.

## 4. Các tham số cấu hình quan trọng

Cú pháp cơ bản:

~~~cypher
CREATE VECTOR INDEX ten_index IF NOT EXISTS
FOR (d:TenLabel) ON (d.embedding)
OPTIONS { indexConfig: {
  `vector.dimensions`: 1536,
  `vector.similarity_function`: 'cosine'
}};
~~~

Hai property trong `OPTIONS` được bao trong dấu backtick vì tên có dấu chấm. Ví dụ trên giả định embedding thực có **1536 chiều**; bài thực hành mục 5 sẽ dùng `dimensions = 3`.

### 4.1. Chiều vector và hàm tương đồng

| Tham số | Công dụng | Giá trị/lưu ý |
|---|---|---|
| `vector.dimensions` | Chiều vector mà index mong đợi | **1–4096**. Khai báo đúng bằng chiều embedding; trước 5.23 là bắt buộc. |
| `vector.similarity_function` | Cách so sánh vector | `'cosine'` hoặc `'euclidean'`; trước 5.23 là bắt buộc, từ 5.23 mặc định là `'cosine'`. |

Nếu đặt chiều là 3, danh sách 2 hoặc 4 số **không phù hợp với index**. Ở các phiên bản cho phép dimension cố định, query dùng vector khác chiều sẽ phát sinh lỗi; dữ liệu property lệch chiều không được index theo schema đó. Vector index không phải constraint bắt buộc mọi node đều có một embedding đúng chiều.

Không đưa các giá trị `null`, `NaN`, vô cực hoặc vector zero-norm vào các phép tìm kiếm yêu cầu cosine. Khi thiết kế pipeline nạp embedding, nên kiểm tra kiểu số, chiều và tính hữu hạn **trước khi ghi**.

### 4.2. HNSW: đánh đổi độ chính xác và tài nguyên

| Tùy chọn | Tác dụng | Mặc định tài liệu hiện hành |
|---|---|---|
| `vector.hnsw.m` | Số liên kết tối đa của một phần tử trong đồ thị HNSW; tăng có thể tăng recall nhưng tốn bộ nhớ và thời gian xây dựng | **16** |
| `vector.hnsw.ef_construction` | Số láng giềng được theo dõi khi thêm phần tử; tăng có thể cải thiện chất lượng đồ thị HNSW với chi phí xây dựng cao hơn | **100** |

Đây là những tham số **nâng cao**; không cần chỉnh cho bộ dữ liệu nhỏ. Khi tối ưu hệ thống, đo đồng thời độ trễ tìm kiếm, tốc độ tạo index, dung lượng/bộ nhớ và **recall@k** trên tập truy vấn có đáp án đã biết.

### 4.3. Quantization: tiết kiệm tài nguyên nhưng cần đo recall

Lượng tử hóa nén biểu diễn vector bên trong index. Nó có thể giảm chi phí bộ nhớ và tăng hiệu năng, nhưng cũng có thể làm suy giảm độ chính xác gần đúng.

- Với các bản **5.23 đến trước 2026.06**, tài liệu nêu tùy chọn `vector.quantization.enabled` dạng boolean.
- Từ **2026.06**, `vector.quantization.type` hỗ trợ `'none'`, `'scalar'` và `'binary'`; tùy chọn `vector.quantization.enabled` được đánh dấu deprecated.
- Từ **2026.07**, `vector.default_search_expansion_factor` cho phép mở rộng tập ứng viên để cải thiện chất lượng tìm kiếm; HFQ giúp tính lại điểm theo vector không lượng tử hóa trong một số cấu hình.
- Đến **2026.08**, mặc định kiểu lượng tử hóa đã đổi sang `'binary'`. Không giả định index cũ tự chuyển provider hoặc tự nhận mặc định mới.

Ví dụ **chỉ dành cho phiên bản đã hỗ trợ tùy chọn này**:

~~~cypher
// Tham khảo cho Neo4j 2026.06+; không cần chạy trong bài thực hành.
CREATE VECTOR INDEX demoVectorNewOptions IF NOT EXISTS
FOR (d:DemoVectorNew) ON (d.embedding)
OPTIONS { indexConfig: {
  `vector.dimensions`: 1536,
  `vector.similarity_function`: 'cosine',
  `vector.quantization.type`: 'scalar',
  `vector.hnsw.m`: 16,
  `vector.hnsw.ef_construction`: 100
}};
~~~

Nếu chưa có một nhu cầu đo đạc cụ thể, dùng cấu hình mặc định của provider và khai báo chiều + similarity rõ ràng thường là điểm khởi đầu dễ vận hành.

## 5. Thực hành: tạo fixture và vector index trên node

### 5.1. Bộ dữ liệu 5 tài liệu

Bài sử dụng label riêng `QA005Doc` và tên index `qa005_doc_embedding`. Mỗi embedding có 3 phần tử, các số đều hữu hạn và vector có norm khác 0.

| docId | Tiêu đề | topic | embedding |
|---|---|---|---|
| D01 | Nhập môn đồ thị | graph | `[1.0, 0.0, 0.0]` |
| D02 | Cypher và quan hệ | graph | `[0.8, 0.6, 0.0]` |
| D03 | Driver Java cho Neo4j | java | `[0.6, 0.8, 0.0]` |
| D04 | Thiết kế giao diện | ui | `[0.0, 1.0, 0.0]` |
| D05 | Phân loại ảnh | ai | `[0.0, 0.0, 1.0]` |

Dùng **database thực hành riêng** và chạy từng khối Cypher thành giao dịch riêng. Nếu đã thực hiện bài này trước đó, xóa index thử nghiệm và node thử nghiệm:

~~~cypher
DROP INDEX qa005_doc_embedding IF EXISTS;
~~~

~~~cypher
MATCH (d:QA005Doc)
DETACH DELETE d;
~~~

Tạo dữ liệu:

~~~cypher
CREATE
  (:QA005Doc {
    docId: 'D01', title: 'Nhập môn đồ thị',
    topic: 'graph', embedding: [1.0, 0.0, 0.0]
  }),
  (:QA005Doc {
    docId: 'D02', title: 'Cypher và quan hệ',
    topic: 'graph', embedding: [0.8, 0.6, 0.0]
  }),
  (:QA005Doc {
    docId: 'D03', title: 'Driver Java cho Neo4j',
    topic: 'java', embedding: [0.6, 0.8, 0.0]
  }),
  (:QA005Doc {
    docId: 'D04', title: 'Thiết kế giao diện',
    topic: 'ui', embedding: [0.0, 1.0, 0.0]
  }),
  (:QA005Doc {
    docId: 'D05', title: 'Phân loại ảnh',
    topic: 'ai', embedding: [0.0, 0.0, 1.0]
  });
~~~

Kiểm tra trước khi tạo index:

~~~cypher
MATCH (d:QA005Doc)
RETURN count(d) AS totalDocs,
       count(d.embedding) AS withEmbeddings,
       collect(DISTINCT size(d.embedding)) AS dimensions;
~~~

Đáp án: `totalDocs = 5`, `withEmbeddings = 5`, `dimensions = [3]`. Bộ dữ liệu này chỉ dùng để học truy vấn; tiêu đề và vector không được sinh từ cùng một mô hình embedding.

### 5.2. Tạo index

Dùng Neo4j **5.15+**:

~~~cypher
CREATE VECTOR INDEX qa005_doc_embedding IF NOT EXISTS
FOR (d:QA005Doc) ON (d.embedding)
OPTIONS { indexConfig: {
  `vector.dimensions`: 3,
  `vector.similarity_function`: 'cosine'
}};
~~~

Không cần tạo node index độc lập trên `embedding`; `VECTOR INDEX` phục vụ truy vấn độ tương đồng, không phải RANGE index cho so sánh từng phần tử.

### 5.3. Quan sát trạng thái và metadata

~~~cypher
SHOW VECTOR INDEXES
YIELD name, type, state, populationPercent,
      entityType, labelsOrTypes, properties, indexProvider, options
WHERE name = 'qa005_doc_embedding'
RETURN name, type, state, populationPercent,
       entityType, labelsOrTypes, properties, indexProvider, options;
~~~

Đối chiếu các trường quan trọng:

| Trường | Kỳ vọng |
|---|---|
| `name` | `qa005_doc_embedding` |
| `type` | `VECTOR` |
| `entityType` | `NODE` |
| `labelsOrTypes` | `['QA005Doc']` |
| `properties` | `['embedding']` |
| `state` | `ONLINE` khi đã sẵn sàng, hoặc `POPULATING` trong khi xây dựng |
| `populationPercent` | Thường là `100.0` sau khi xây dựng xong |
| `indexProvider` | Phụ thuộc phiên bản/provider; không kiểm tra theo tên cố định |
| `options` | Có `vector.dimensions = 3` và `vector.similarity_function = 'cosine'`, cùng các tùy chọn mặc định theo provider |

**Chỉ chạy truy vấn tìm kiếm khi index đã `ONLINE`**. Quá trình tạo index chạy nền; index đang `POPULATING` chưa dùng được. Nếu không có dòng nào, kiểm tra database hiện hành, quyền xem index và lỗi từ lệnh tạo.

Trên Neo4j 5.11–5.14, việc lọc `SHOW INDEXES WHERE type = 'VECTOR'` có thể là lựa chọn tương thích tốt hơn `SHOW VECTOR INDEXES`, tùy bản cụ thể.

## 6. Truy vấn vector index bằng procedure tương thích Neo4j 5.x

Lệnh sau yêu cầu ba node có embedding gần nhất với `[1.0, 0.0, 0.0]`:

~~~cypher
CALL db.index.vector.queryNodes(
  'qa005_doc_embedding',
  3,
  [1.0, 0.0, 0.0]
)
YIELD node, score
RETURN node.docId AS docId, node.title AS title, score
ORDER BY score DESC, docId;
~~~

Ba đối số lần lượt là:

1. Tên vector index.
2. `k` — số láng giềng gần nhất yêu cầu.
3. Vector truy vấn, phải tương thích chiều và hàm similarity với index.

Procedure trả về cặp `node` và `score`. Với fixture chuẩn và truy vấn trên, **về mặt cosine chính xác**, thứ tự mong đợi ở ba vị trí đầu là **D01, D02, D03**. D01 có hướng trùng vector truy vấn. Tuy nhiên, vì đây là tìm kiếm **ANN**, không nên biến một thứ tự cụ thể hay số lượng `k` thành cam kết tuyệt đối cho mọi bộ dữ liệu hoặc provider.

### Truy vấn có tham số từ ứng dụng

Đừng nối chuỗi vector người dùng trực tiếp vào Cypher. Truy vấn có tham số:

~~~cypher
CALL db.index.vector.queryNodes(
  'qa005_doc_embedding', $topK, $queryEmbedding
)
YIELD node, score
RETURN node.docId AS docId,
       node.title AS title,
       score
ORDER BY score DESC, docId;
~~~

Ví dụ tham số truyền qua Neo4j Java Driver hoặc tầng repository:

~~~json
{
  "topK": 3,
  "queryEmbedding": [1.0, 0.0, 0.0]
}
~~~

Với ứng dụng Java/Spring Data Neo4j, lớp service nên kiểm tra trước rằng `topK` là số nguyên dương hợp lý và embedding là danh sách số hữu hạn, đúng 3 chiều (hoặc chiều của mô hình thực tế). Driver gửi tham số kiểu dữ liệu phù hợp; kết quả có thể ánh xạ về DTO gồm `docId`, `title`, `score`. Các ví dụ procedure vẫn hoạt động trong nhiều dự án dùng Cypher 5, nhưng trên Neo4j 2026.04+ nên chuẩn bị chuyển sang `SEARCH`.

## 7. Truy vấn bằng SEARCH trong Neo4j 2026.01+ và Cypher 25

Đây là cách được Neo4j khuyến nghị cho vector search ở phiên bản mới:

~~~cypher
CYPHER 25
MATCH (d:QA005Doc)
SEARCH d IN (
  VECTOR INDEX qa005_doc_embedding
  FOR [1.0, 0.0, 0.0]
  LIMIT 3
) SCORE AS score
RETURN d.docId AS docId, d.title AS title, score
ORDER BY score DESC, docId;
~~~

Giải thích từng phần:

- `MATCH (d:QA005Doc)` khai báo biến node cần tìm.
- `SEARCH d IN (...)` yêu cầu tìm trong index mang tên `qa005_doc_embedding`.
- `FOR [1.0, 0.0, 0.0]` là vector truy vấn; trong ứng dụng có thể thay bằng `$queryEmbedding`.
- `LIMIT 3` là số kết quả ANN mong muốn trong chính phép tìm kiếm.
- `SCORE AS score` đưa điểm tương đồng ra biến `score` để dùng ở `RETURN` hoặc sắp xếp.

`SEARCH` là **mệnh đề con của `MATCH` hoặc `OPTIONAL MATCH`**, không phải một phép tìm kiếm tự động cho mọi điều kiện `WHERE`. Không thể thay phần `SEARCH` bằng `MATCH (d) WHERE d.embedding = $queryEmbedding` để đạt chức năng tương đương: phép so sánh bằng kiểm tra giá trị bằng nhau, không tìm hàng xóm gần nhất.

### 7.1. Lọc trước top-k và lọc sau top-k là hai bài toán khác nhau

Giả sử chỉ tìm tài liệu chủ đề `'java'`. Trên dữ liệu mẫu, D03 thuộc chủ đề đó, nhưng D01 và D02 có cosine với vector truy vấn cao hơn D03. Nếu lấy `k = 2` rồi mới lọc:

~~~cypher
CALL db.index.vector.queryNodes(
  'qa005_doc_embedding', 2, [1.0, 0.0, 0.0]
)
YIELD node, score
WITH node, score
WHERE node.topic = 'java'
RETURN node.docId AS docId, score;
~~~

Truy vấn có thể **không còn kết quả** vì hai ứng viên gần nhất bị loại. Tăng `k` để rồi lọc sau là cách làm tương thích phiên bản cũ, nhưng không bảo đảm nhận đủ top-k **bên trong tập đã lọc**.

### 7.2. Bộ lọc tích hợp trong vector index (2026.01+)

Từ Neo4j 2026.01, có thể bổ sung property dùng cho bộ lọc vào index. **Không tạo thêm vector index cùng schema đang tồn tại**. Để thử trên chính dữ liệu bài học, đầu tiên xóa index cũ, sau đó tạo lại với `WITH [d.topic]`:

~~~cypher
DROP INDEX qa005_doc_embedding IF EXISTS;
~~~

~~~cypher
CYPHER 25
CREATE VECTOR INDEX qa005_doc_embedding IF NOT EXISTS
FOR (d:QA005Doc) ON (d.embedding)
WITH [d.topic]
OPTIONS { indexConfig: {
  `vector.dimensions`: 3,
  `vector.similarity_function`: 'cosine'
}};
~~~

Kiểm tra lại `SHOW VECTOR INDEXES` và chờ `ONLINE`. Sau đó:

~~~cypher
CYPHER 25
MATCH (d:QA005Doc)
SEARCH d IN (
  VECTOR INDEX qa005_doc_embedding
  FOR [1.0, 0.0, 0.0]
  WHERE d.topic = 'java'
  LIMIT 2
) SCORE AS score
RETURN d.docId AS docId, d.title AS title, score
ORDER BY score DESC;
~~~

Ở đây `WHERE` nằm **bên trong `SEARCH`**, nên index xét điều kiện `topic = 'java'` trong quá trình tìm ứng viên; với fixture chuẩn, **D03** là tài liệu phù hợp. Khả năng tìm kiếm vẫn là ANN. Index chỉ có **một property vector** (`embedding`); `WITH [d.topic]` thêm metadata để lọc, không tạo vector đa chiều từ nhiều trường.

Điều kiện được hỗ trợ trong `SEARCH … WHERE` có giới hạn so với `WHERE` Cypher thông thường. Kiểm tra đúng mục *Predicates for vector search with filters* của bản server trước khi đưa các biểu thức phức tạp vào index filter.

## 8. Vector index trên relationship

Không chỉ node có thể chứa embedding. Từ **Neo4j 5.18**, quan hệ cũng có vector index. Ví dụ một hệ thống gợi ý lưu đặc trưng của tương tác giữa người dùng và nội dung trên relationship:

~~~cypher
CREATE VECTOR INDEX qa005_link_embedding IF NOT EXISTS
FOR ()-[r:QA005_RELATED]-() ON (r.embedding)
OPTIONS { indexConfig: {
  `vector.dimensions`: 3,
  `vector.similarity_function`: 'cosine'
}};
~~~

Ví dụ tạo hai quan hệ trong database thực hành, sử dụng hai node đã có:

~~~cypher
MATCH (a:QA005Doc {docId: 'D01'}),
      (b:QA005Doc {docId: 'D02'}),
      (c:QA005Doc {docId: 'D03'})
CREATE (a)-[:QA005_RELATED {embedding: [1.0, 0.0, 0.0]}]->(b),
       (a)-[:QA005_RELATED {embedding: [0.7, 0.7, 0.0]}]->(c);
~~~

Khi index `ONLINE`, truy vấn trên bản 5.18+:

~~~cypher
CALL db.index.vector.queryRelationships(
  'qa005_link_embedding', 2, [1.0, 0.0, 0.0]
)
YIELD relationship, score
RETURN startNode(relationship).docId AS fromDoc,
       endNode(relationship).docId AS toDoc,
       score
ORDER BY score DESC;
~~~

Trong Cypher 25 từ Neo4j 2026.01, có thể thay procedure bằng:

~~~cypher
CYPHER 25
MATCH ()-[r:QA005_RELATED]->()
SEARCH r IN (
  VECTOR INDEX qa005_link_embedding
  FOR [1.0, 0.0, 0.0]
  LIMIT 2
) SCORE AS score
RETURN startNode(r).docId AS fromDoc,
       endNode(r).docId AS toDoc,
       score;
~~~

Node index **không dùng để tìm relationship** và ngược lại. Tham số index phải trỏ đúng loại entity và property đã cấu hình. Vì số quan hệ ở fixture nhỏ, kết quả ANN có thể trả ít hơn yêu cầu `k`; xem mục 9.

## 9. Kiểm chứng kết quả và hiểu giới hạn của ANN

### 9.1. Tính chính xác cho bộ dữ liệu nhỏ (Neo4j 5.18+)

Trên bộ 5 node, có thể tính điểm cosine **không qua vector index** để có chuẩn đối chiếu:

~~~cypher
MATCH (d:QA005Doc)
RETURN
  d.docId AS docId,
  vector.similarity.cosine(
    d.embedding, [1.0, 0.0, 0.0]
  ) AS exactScore
ORDER BY exactScore DESC, docId;
~~~

Đáp án về **thứ tự**: D01, D02, D03, sau đó D04 và D05 có độ tương đồng cosine hình học bằng nhau với vector truy vấn. Không nên kiểm thử bằng cách ép mọi số thực phải trùng từng chữ số thập phân; có thể có khác biệt biểu diễn dấu phẩy động giữa phương pháp tính điểm và provider.

Với tập lớn hơn, nên đo **recall@k**:

\[
\operatorname{recall@k}
=\frac{\left|\operatorname{ANNTopK}\cap\operatorname{ExactTopK}\right|}{k}
\]

Ví dụ, nếu bộ kết quả chính xác có 10 node và ANN thu hồi đúng 9 trong số đó, recall@10 là `0.9`. Kiểm tra đồng thời **latency**, `k`, số bản ghi hợp lệ, kích thước vector và các tham số HNSW/lượng tử hóa.

### 9.2. Các giới hạn vận hành quan trọng

1. **Xấp xỉ:** `k` chỉ là số kết quả yêu cầu; có trường hợp trả ít hơn `k`, nhất là khi `k` lớn gần tổng số vector được index.
2. **Tính nhất quán giao dịch:** thay đổi vector **trong cùng transaction** không được phản ánh ngay vào truy vấn vector index của transaction đó. Nên ghi rồi commit, sau đó tìm trong transaction đọc riêng.
3. **Sẵn sàng:** index ở trạng thái `POPULATING` không thể dùng; phải đợi `ONLINE` trước khi kiểm thử truy vấn.
4. **Một schema vector index:** không thể tạo đồng thời hai vector index khác nhau trên cùng schema để dùng một cái `cosine` và một cái `euclidean`. Hãy chọn phép đo theo embedding và mục tiêu nghiệp vụ.
5. **Bất tương thích embedding:** không so sánh tùy tiện vector sinh từ hai mô hình/phiên bản khác nhau, ngay cả khi số chiều trùng nhau. Khi nâng cấp embedding model, nên thiết kế kế hoạch tái tạo dữ liệu và index tương ứng.
6. **Điểm không phải độ tin cậy:** `score` cao không chứng minh câu trả lời là chính xác hoặc an toàn. Ứng dụng còn cần lọc quyền truy cập, kiểm chứng nguồn và quy tắc nghiệp vụ.
7. **Hybrid search:** khi kết hợp full-text và vector, điểm của hai cơ chế không cùng thang ý nghĩa. Xếp hạng/chuẩn hóa từng nguồn trước khi phối hợp, ví dụ bằng rank fusion, thay vì cộng trực tiếp `score` chưa xử lý.

### 9.3. Index không thay thế ràng buộc dữ liệu

Vector index không bảo đảm node bắt buộc có `embedding` đúng chiều hay đúng mô hình. Ví dụ, một node không có property `embedding` vẫn có thể tồn tại trong graph nhưng không tham gia tìm kiếm vector. Vì vậy lớp nạp dữ liệu nên kiểm tra:

- Độ dài và kiểu của từng phần tử embedding.
- Vector hữu hạn; với cosine tránh vector độ dài 0.
- Version/model tạo embedding, thời điểm cập nhật và cách xử lý khi mô hình thay đổi.
- Các quyền của người dùng được phép xem tài liệu sau truy vấn.

Trong Neo4j, `UNIQUE` hoặc key constraint cho `docId` vẫn là vấn đề riêng; chúng không biến vector index thành cơ chế kiểm tra định danh.

## 10. Tương thích Neo4j 5.11–5.14: tạo index bằng procedure cũ

Nếu đang chạy một bản hỗ trợ vector index nhưng **chưa có** cú pháp `CREATE VECTOR INDEX` (trước 5.15), có thể gặp ví dụ:

~~~cypher
// Chỉ dùng với Neo4j 5.11–5.14 có hỗ trợ procedure này.
// Không chạy đồng thời với index cùng tên đã tạo ở mục 5.
CALL db.index.vector.createNodeIndex(
  'qa005_doc_embedding',
  'QA005Doc',
  'embedding',
  3,
  'cosine'
);
~~~

Hạn chế của cách làm cũ:

- Chỉ tạo **node** vector index và cần chỉ rõ dimension + similarity.
- Không sử dụng cú pháp hiện đại `SEARCH` hay filtered vector index.
- Sau nâng cấp, nên sử dụng `CREATE VECTOR INDEX` nếu cần tạo index mới; Neo4j ghi nhận một vấn đề tương thích ở một số bản 5.18+ khi gọi procedure tạo index cũ trên database vừa được nâng cấp từ bản trước 5.11.

Nếu truy vấn lỗi cú pháp, trước tiên kiểm tra **version server**, **phiên bản Cypher**, khả năng `CREATE VECTOR INDEX` và các procedure hiện có. Không tự thêm cấu hình 2026.x vào một hệ thống 5.x rồi giả định nó sẽ bị bỏ qua.

## 11. Ứng dụng với Neo4j Java Driver và Spring Data Neo4j

Một quy trình thực tế:

~~~mermaid
flowchart LR
  A["Văn bản / đối tượng"] --> B["Mô hình embedding"]
  B --> C["Kiểm tra dimension, kiểu số, model version"]
  C --> D["Ghi node/relationship + embedding vào Neo4j"]
  D --> E["Vector index cập nhật sau commit"]
  F["Câu hỏi người dùng"] --> G["Embedding bằng cùng mô hình"]
  G --> H["SEARCH hoặc queryNodes"]
  E --> H
  H --> I["Lọc quyền / nối quan hệ / xếp hạng"]
  I --> J["Trả tài liệu và nguồn"]
~~~

Trong Java Driver, dùng truy vấn **tham số hóa** để truyền `$queryEmbedding` và `$topK` dưới dạng danh sách số và số nguyên. Tách việc ghi embedding với truy vấn tìm kiếm sang giao dịch khác; ánh xạ mỗi record trả về thành DTO, chẳng hạn `DocumentHit(docId, title, score)`.

Nếu dùng Spring Data Neo4j, có thể đặt lệnh truy vấn vào phương thức repository với `@Query` hoặc một service gọi driver. Quan trọng là tên index trỏ đúng schema được triển khai, còn model embedding và dimension phải thống nhất giữa pipeline ghi và tìm kiếm.

Các quyết định vận hành cần ghi lại trong cấu hình ứng dụng: tên index, label/relationship type, tên property embedding, số chiều, cosine/euclidean, phiên bản mô hình và chiến lược lọc dữ liệu. Tránh đặt các giá trị này rải rác trong nhiều lớp Java vì khi đổi mô hình sẽ dễ sinh kết quả sai.

## 12. Chẩn đoán lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| `CREATE VECTOR INDEX` bị báo lỗi cú pháp | Server trước 5.15 hoặc cú pháp không phù hợp | Kiểm tra bản Neo4j; 5.11–5.14 có procedure cũ |
| `SEARCH` bị báo không hợp lệ | Neo4j trước 2026.01 hoặc chưa dùng Cypher 25 | Dùng procedure queryNodes/queryRelationships, hoặc nâng cấp đúng phiên bản |
| Query index khi vừa tạo không chạy | `state = 'POPULATING'` | Xem `SHOW VECTOR INDEXES`, chờ `ONLINE` |
| Truy vấn báo vector khác số chiều | Query khác `vector.dimensions` | Tạo embedding đúng số chiều, giữ một mô hình nhất quán |
| Vector không xuất hiện trong kết quả | Thiếu embedding, sai chiều/kiểu, vector cosine không hợp lệ | Kiểm tra property và đầu vào, rồi xác nhận node đủ điều kiện để index |
| Có index nhưng `MATCH ... WHERE` không làm tìm kiếm ngữ nghĩa | Vector index là search index gọi tường minh | Sử dụng `SEARCH` hoặc procedure vector query |
| Lấy top-2 rồi `WHERE topic` trả rỗng | Lọc sau top-k làm mất ứng viên cần thiết | Với bản mới, đưa property vào vector index và lọc trong `SEARCH … WHERE` |
| Thêm vector rồi truy vấn trong cùng transaction không thấy | Index không phản ánh các thay đổi cùng transaction | Commit ghi, mở giao dịch đọc mới |
| Điểm và thứ tự khác sau khi nâng cấp | Provider, lượng tử hóa, ANN và dữ liệu thay đổi | Đo recall@k, kiểm tra `indexProvider` và `options`, đánh giá lại cấu hình |
| `CREATE` cấu hình lượng tử hóa không được công nhận | Dùng tùy chọn mới trên bản cũ | Đối chiếu bảng version, bỏ tùy chọn chưa hỗ trợ hoặc nâng cấp |

## 13. Bài tập củng cố có đáp án

**Bài 1 — Dự đoán thứ tự.** Với `q = [1.0, 0.0, 0.0]` và năm vector mục 5, ba tài liệu nào gần nhất theo cosine **chính xác**?

**Đáp án:** D01, D02, D03. Trong môi trường ANN, hãy chạy truy vấn và so sánh thay vì khẳng định luôn nhận đủ ba tài liệu.

**Bài 2 — Chọn cú pháp.** Một hệ thống Neo4j 5.16 cần index embedding trên `(:Article)` và truy vấn top-5. Có dùng `SEARCH` không?

**Đáp án:** chưa. Có thể tạo index bằng `CREATE VECTOR INDEX`, nhưng dùng `db.index.vector.queryNodes()` để truy vấn. `SEARCH` cho vector index xuất hiện từ Neo4j 2026.01 và yêu cầu Cypher 25.

**Bài 3 — Phân biệt lọc trước và lọc sau.** Khi chỉ muốn `topic = 'java'` mà truy vấn ANN ban đầu lấy top-2 toàn bộ dữ liệu, có rủi ro gì?

**Đáp án:** top-2 toàn cục có thể là D01 và D02, khiến lọc sau trả rỗng dù D03 hợp lệ. Dùng bộ lọc ngay trong `SEARCH` với metadata đã được index ở bản 2026.01+, hoặc đánh giá chiến lược lấy ứng viên rộng hơn ở bản cũ.

**Bài 4 — Chọn vector storage.** Ứng dụng chạy Community Edition và cần tương thích Neo4j 5.x. Nên bắt đầu bằng kiểu property nào?

**Đáp án:** `LIST<INTEGER | FLOAT>`. Kiểu native `VECTOR` chỉ khả dụng từ Neo4j 2025.10 với Cypher 25 và yêu cầu block format thích hợp.

**Bài 5 — Thay model embedding.** Mô hình A cho 768 chiều, mô hình B cho 1536 chiều. Có thể giữ cấu hình index 768 chiều và ghi vector của B vào cùng property rồi tiếp tục truy vấn ổn định không?

**Đáp án:** không. Dữ liệu mới không cùng chiều với schema index; cần quản lý phiên bản mô hình, chọn property/index mới hoặc tái tạo dữ liệu và index có kế hoạch.

## 14. Dọn dữ liệu thử nghiệm

Chỉ chạy trên database thực hành, sau khi đã hoàn thành các phép kiểm tra:

~~~cypher
DROP INDEX qa005_doc_embedding IF EXISTS;
~~~

Nếu đã làm mục relationship:

~~~cypher
DROP INDEX qa005_link_embedding IF EXISTS;
~~~

Xóa các node thử nghiệm và quan hệ gắn với chúng:

~~~cypher
MATCH (d:QA005Doc)
DETACH DELETE d;
~~~

Xác nhận không còn node:

~~~cypher
MATCH (d:QA005Doc)
RETURN count(d) AS remain;
~~~

Kết quả mong đợi: `remain = 0`. Các index minh họa riêng biệt khác như `demoVectorNewOptions` chỉ được xóa nếu bạn đã chủ động tạo chúng.

## 15. Tài liệu chính thức để đối chiếu phiên bản

- [Neo4j Cypher Manual 5 — Vector indexes](https://neo4j.com/docs/cypher-manual/5/indexes/search-indexes/vector-indexes/): mốc 5.11–5.23, cú pháp `CREATE VECTOR INDEX`, các procedure.
- [Neo4j Cypher Manual — Vector indexes (current)](https://neo4j.com/docs/cypher-manual/current/indexes/search-indexes/vector-indexes/): cấu hình, index provider, giới hạn và các thay đổi đến nhánh 2026.
- [Neo4j Cypher Manual — SEARCH](https://neo4j.com/docs/cypher-manual/current/clauses/search/): cú pháp `SEARCH` trong Cypher 25 và bộ lọc trên vector index.
- [Neo4j Cypher Manual — Vector functions](https://neo4j.com/docs/cypher-manual/current/functions/vector/): tính điểm cosine/euclidean trực tiếp và kiểu `VECTOR`.
- [Neo4j Cypher Manual — Additions, deprecations and compatibility](https://neo4j.com/docs/cypher-manual/current/deprecations-additions-removals-compatibility/): thay đổi cú pháp và tham số theo release.

Với vector index, cách làm an toàn là **kiểm tra phiên bản trước, chuẩn hóa embedding đầu vào, tạo index với dimension rõ ràng, đợi `ONLINE`, truy vấn bằng API phù hợp và đo chất lượng ANN trên dữ liệu có đáp án**. Khi kết hợp với các đường đi và ràng buộc của property graph, kết quả tìm kiếm ngữ nghĩa mới trở thành một phần có thể kiểm chứng của ứng dụng Neo4j.
