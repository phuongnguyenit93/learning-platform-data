# Quản lý cập nhật chỉ mục và tính nhất quán theo loại chỉ mục trong Neo4j

## 1. Đặt vấn đề: vì sao graph đã đổi nhưng kết quả tìm kiếm chưa như mong đợi?

Neo4j lưu dữ liệu liên kết dưới dạng **property graph**: node, relationship và các thuộc tính. Khi ứng dụng thêm một bài viết, sửa tiêu đề, xóa thẻ phân loại hoặc cập nhật vector embedding, dữ liệu gốc (*graph store*) thay đổi; đồng thời các **index** liên quan cần phản ánh thay đổi đó để truy vấn vẫn tìm đúng thực thể.

Giả sử một hệ thống quản lý tri thức có:

- Node `Article` với `id`, `title`, `body`, `category`, `location` và `embedding`.
- Relationship `(:Article)-[:CITES]->(:Article)` để biểu diễn trích dẫn.
- Tìm kiếm theo mã và danh mục; tìm chứa chuỗi, tìm trong nội dung, tìm theo vị trí và tìm ngữ nghĩa bằng vector.

Câu hỏi vận hành không chỉ là **“Có index chưa?”** mà còn là:

1. Khi node/relationship thay đổi, **index nào được cập nhật**, theo cơ chế nào?
2. Ngay sau khi transaction commit, **truy vấn loại nào có thể đọc thay đổi**?
3. Khi tạo index mới, làm sao biết nó đã **được xây dựng xong**?
4. Khi kết quả tìm kiếm sai hoặc thiếu, đó là lỗi **đồng bộ index**, **điều kiện truy vấn**, **analyzer**, hay **độ xấp xỉ của vector search**?

Ba khái niệm cần tách biệt ngay từ đầu:

| Khái niệm | Câu hỏi cần trả lời | Ví dụ |
| --- | --- | --- |
| **Nhất quán transaction của dữ liệu** | Thay đổi trong một transaction đã commit hay rollback? | `SET a.title = 'Mới'` commit thành công |
| **Tính kịp thời của bản sao index** | Khi nào index phản ánh thay đổi đã commit? | Full-text cấu hình eventual có thể chậm một khoảng |
| **Ngữ nghĩa/độ chính xác tìm kiếm** | Index trả kết quả theo quy tắc nào? | Vector k-NN trả hàng xóm gần nhất **xấp xỉ**; full-text tách từ theo analyzer |

Không nên xem **“không thấy một kết quả trong top-k vector”** là bằng chứng index bị trễ: k-NN xấp xỉ và độ bao phủ của top-k là vấn đề khác với commit và đồng bộ.

## 2. So sánh tính nhất quán theo từng loại index

Neo4j phân biệt **performance index** được Cypher planner lựa chọn và **search index** được gọi trực tiếp để lấy kết quả có điểm xếp hạng.

| Loại index | Cập nhật khi dữ liệu đổi | Điểm cần lưu ý về tính nhất quán | Truy vấn sử dụng |
| --- | --- | --- | --- |
| **Token lookup** (`LOOKUP`) | Tự cập nhật theo thay đổi label node/type relationship trong transaction | Được quản lý cùng transaction; không phải index thuộc tính | `MATCH (a:Article)`, `MATCH ()-[:CITES]->()` |
| **Range** (`RANGE`) | Tự cập nhật theo thêm, sửa, xóa thuộc tính và thay đổi label/type có liên quan | Index hiệu năng được duy trì cùng commit; constraint duy nhất dùng range index để kiểm soát dữ liệu | `a.id = $id`, `a.createdAt >= $from` |
| **Text** (`TEXT`) | Tự cập nhật khi giá trị `STRING` hợp lệ thay đổi | Chỉ mục hiệu năng đồng bộ với commit, khác full-text index | `a.title CONTAINS 'graph'` |
| **Point** (`POINT`) | Tự cập nhật khi thuộc tính vị trí `POINT` đổi | Duy trì cùng commit, nhưng phải dùng đúng CRS và kiểu dữ liệu | `point.distance(...)`, `point.withinBBox(...)` |
| **Full-text** (`FULLTEXT`) mặc định | Tự cập nhật khi `STRING`/`LIST<STRING>` được thêm, sửa, xóa | **Mặc định cập nhật trong quá trình commit** (`eventually_consistent = false`) | Tìm theo token/analyzer, có `score` |
| **Full-text** cấu hình eventual | Các thay đổi đã commit được đưa vào hàng đợi và áp dụng ở luồng nền | **Có thể thấy kết quả tìm kiếm cũ trong một thời gian ngắn sau commit** | Cùng kiểu truy vấn full-text; có thao tác chờ refresh |
| **Vector** (`VECTOR`) | Tự quản lý khi embedding hợp lệ được thêm, sửa hoặc xóa | Thay đổi **trong chính transaction đang ghi** không xuất hiện qua vector index; tìm kiếm k-NN là **xấp xỉ** | Vector `SEARCH` hoặc thủ tục k-NN tùy phiên bản |

**Quan trọng:** Chế độ `fulltext.eventually_consistent` là cấu hình **riêng của full-text index**, không phải một công tắc biến tất cả index trong Neo4j thành bất đồng bộ. Vector có các giới hạn truy vấn riêng; không suy rằng vector cũng dùng hàng đợi full-text hoặc có cùng thủ tục `await`.

Tài liệu và API thay đổi qua các phiên bản. Ví dụ bên dưới ưu tiên cú pháp `CREATE ... INDEX` dùng được trên nhiều phiên bản Neo4j 5.x và chỉ rõ chỗ cần Cypher 25/Neo4j 2026.

## 3. Index được cập nhật như thế nào?

### 3.1. Một thay đổi trong transaction ảnh hưởng đến index

Giả sử `Article` có range index cho `category`, text index cho `title` và full-text index cho `title`/`body`:

```cypher
MATCH (a:Article {id: 'A001'})
SET a.title = 'Tối ưu truy vấn Cypher',
    a.category = 'DATABASE'
REMOVE a.legacyTag;
```

Khi transaction commit thành công:

- Range index trên `category` bỏ giá trị cũ (nếu có) và phản ánh giá trị `DATABASE`.
- Text index trên `title` phản ánh chuỗi tiêu đề mới.
- Full-text index cập nhật các token liên quan tới tiêu đề, **ngay trong commit** nếu dùng chế độ mặc định, hoặc **sau commit qua luồng nền** nếu chọn eventual.
- Index của thuộc tính `legacyTag` (nếu tồn tại) không còn entry tương ứng cho giá trị đã bị xóa.
- Mọi sửa đổi thuộc một transaction lỗi và rollback **không được coi là dữ liệu đã commit**, nên không xuất hiện như thay đổi đã xác nhận trong index.

```text
                  GHI DỮ LIỆU
                         |
                  Transaction
                         |
              +----------+----------+
              |                     |
           ROLLBACK               COMMIT
              |                     |
       Không giữ thay đổi    Graph store xác nhận
                                    |
                 +------------------+---------------------+
                 |                                        |
       Index đồng bộ theo commit             Full-text eventual (nếu bật)
       LOOKUP / RANGE / TEXT / POINT         Đưa công việc vào hàng đợi
       và full-text mặc định                   |
                                            Luồng nền
                                                |
                                         Index được refresh
```

Hình minh họa thể hiện **thời điểm cập nhật**; không phải cơ chế triển khai nội bộ đầy đủ của engine.

### 3.2. Những thao tác nào làm thay đổi nội dung index?

| Thao tác ghi | Hệ quả thường gặp |
| --- | --- |
| `CREATE` node có label và thuộc tính phù hợp | Thêm entry vào lookup index và các property index tương ứng |
| `SET a.title = '...'` | Thay entry cũ bằng entry mới trên index của `title` |
| `REMOVE a.title` hoặc `SET a.title = null` | Bỏ entry thuộc tính đó khỏi index; Neo4j không lưu một giá trị thuộc tính `null` |
| `SET a:Published` / `REMOVE a:Published` | Cập nhật tra cứu label; các property index gắn label `Published` được xem xét lại |
| `CREATE` / `DELETE` relationship | Cập nhật lookup index của relationship type và property index liên quan |
| `DELETE a` | Loại node khỏi các index liên quan khi transaction thành công |
| Sửa `a.embedding` | Vector index xử lý vector mới nếu giá trị đủ điều kiện theo schema/cấu hình |

Relationship type không được đổi trực tiếp như sửa một thuộc tính: để thay type, ứng dụng thường tạo relationship mới, chuyển dữ liệu cần thiết rồi xóa relationship cũ trong transaction thích hợp.

Index chỉ chứa những thực thể có **label/type và giá trị thuộc tính phù hợp** với schema và kiểu dữ liệu mà index đó hỗ trợ. Ví dụ, text index không nhận một `INTEGER` như chuỗi; vector index cấu hình 3 chiều không nhận embedding 4 chiều như một vector phù hợp với cấu hình đó. Hãy kiểm tra giá trị trong graph store trước khi nghi ngờ index bị lỗi.

### 3.3. Không nhầm index với ràng buộc dữ liệu

```cypher
CREATE CONSTRAINT article_id_unique IF NOT EXISTS
FOR (a:Article) REQUIRE a.id IS UNIQUE;
```

Uniqueness constraint tạo **range index sở hữu bởi constraint** để kiểm tra trùng khóa. Một `CREATE RANGE INDEX` thông thường giúp truy vấn nhanh hơn nhưng **không tự cấm** tạo hai node cùng `id`. Nếu transaction vi phạm uniqueness constraint, transaction thất bại; không có trạng thái “graph ghi trùng nhưng index chưa kịp sửa”.

Index được constraint sở hữu không thể xóa trực tiếp bằng `DROP INDEX`; xóa constraint cũng xóa backing index. Khi xây dựng hệ thống tìm kiếm và nhập dữ liệu, cần phân biệt rõ **tối ưu truy cập** và **bảo đảm toàn vẹn khóa**.

## 4. Thực hành: tạo bộ index cho một graph tri thức

### 4.1. Tạo schema

Chạy từng lệnh độc lập trên cơ sở dữ liệu thử nghiệm:

```cypher
CREATE CONSTRAINT article_id_unique IF NOT EXISTS
FOR (a:Article) REQUIRE a.id IS UNIQUE;
```

```cypher
CREATE RANGE INDEX idx_article_category IF NOT EXISTS
FOR (a:Article) ON (a.category);
```

```cypher
CREATE TEXT INDEX idx_article_title_text IF NOT EXISTS
FOR (a:Article) ON (a.title);
```

```cypher
CREATE POINT INDEX idx_article_location IF NOT EXISTS
FOR (a:Article) ON (a.location);
```

```cypher
CREATE FULLTEXT INDEX idx_article_fulltext IF NOT EXISTS
FOR (a:Article) ON EACH [a.title, a.body]
OPTIONS {
  indexConfig: {
    `fulltext.analyzer`: 'standard-no-stop-words',
    `fulltext.eventually_consistent`: true
  }
};
```

```cypher
CREATE VECTOR INDEX idx_article_embedding IF NOT EXISTS
FOR (a:Article) ON (a.embedding)
OPTIONS {
  indexConfig: {
    `vector.dimensions`: 3,
    `vector.similarity_function`: 'cosine'
  }
};
```

Trong ví dụ trên, embedding có **3 chiều chỉ để minh họa**; ứng dụng thực tế phải dùng đúng số chiều của mô hình embedding, chẳng hạn 768 hoặc 1536. Chỉ mục vector với cosine cần vector hợp lệ, không dùng vector toàn số 0. `IF NOT EXISTS` không so sánh cấu hình cũ với cấu hình mới để tự cập nhật index hiện có.

Token lookup index cho node label và relationship type thường đã được Neo4j tạo sẵn khi khởi tạo database, vì thế không cần tạo thêm trong ví dụ.

### 4.2. Tạo dữ liệu thử nghiệm

```cypher
MERGE (a:Article {id: 'A001'})
SET a.title = 'Graph và Cypher',
    a.body = 'Neo4j truy vấn quan hệ bằng Cypher.',
    a.category = 'DATABASE',
    a.location = point({longitude: 106.7000, latitude: 10.7800}),
    a.embedding = [1.0, 0.0, 0.0];
```

```cypher
MERGE (a:Article {id: 'A002'})
SET a.title = 'Java Driver cho Neo4j',
    a.body = 'Java kết nối graph và thực thi truy vấn.',
    a.category = 'JAVA',
    a.location = point({longitude: 106.7200, latitude: 10.7950}),
    a.embedding = [0.8, 0.6, 0.0];
```

```cypher
MERGE (a:Article {id: 'A003'})
SET a.title = 'Đường đi trong property graph',
    a.body = 'Các relationship nối những node trong graph.',
    a.category = 'DATABASE',
    a.location = point({longitude: 106.6900, latitude: 10.7750}),
    a.embedding = [0.0, 1.0, 0.0];
```

Để tạo quan hệ phục vụ tìm kiếm kết hợp traversal:

```cypher
MATCH (a:Article {id: 'A001'})
MATCH (b:Article {id: 'A002'})
MERGE (a)-[:CITES]->(b);
```

### 4.3. Chờ index được xây dựng xong

Tạo index và làm index phản ánh **thay đổi mới** là hai vấn đề khác nhau. Ngay sau `CREATE ... INDEX`, index có thể ở trạng thái `POPULATING` khi Neo4j quét dữ liệu đã có để tạo cấu trúc truy cập. Chỉ khi `ONLINE`, index mới sẵn sàng để truy vấn.

```cypher
SHOW INDEXES
YIELD name, type, state, populationPercent, labelsOrTypes, properties
RETURN name, type, state, populationPercent, labelsOrTypes, properties
ORDER BY type, name;
```

Có thể chờ một index cụ thể hoặc tất cả index:

```cypher
CALL db.awaitIndex('idx_article_fulltext', 300);
```

```cypher
CALL db.awaitIndexes(300);
```

Giá trị `300` là thời gian chờ tối đa (giây), không phải một yêu cầu Neo4j phải mất 300 giây. Nếu index ở trạng thái `FAILED`, cần xem nguyên nhân; không nên gọi `await` liên tục để che vấn đề.

**`db.awaitIndexes()` chỉ chờ giai đoạn tạo/populate trở thành `ONLINE`. Nó không có nghĩa mọi thay đổi đang đợi trong hàng đợi full-text eventual đã được áp dụng.** Việc chờ refresh sau commit được xử lý riêng ở phần tiếp theo.

## 5. Thử cập nhật và quan sát từng loại index

### 5.1. Range, text và token lookup

Đổi tiêu đề, danh mục và label:

```cypher
MATCH (a:Article {id: 'A001'})
SET a.title = 'Hướng dẫn Neo4j nâng cao',
    a.category = 'TUTORIAL',
    a:Reviewed;
```

Kiểm tra kết quả trong **transaction đọc sau khi lệnh ghi đã commit**:

```cypher
MATCH (a:Article)
WHERE a.category = 'TUTORIAL'
  AND a.title CONTAINS 'Neo4j'
  AND a:Reviewed
RETURN a.id, a.title, a.category, labels(a);
```

Range index, text index và lookup index được tự động duy trì cùng commit, để planner có thể dùng dữ liệu đã xác nhận. Câu lệnh trên **không bảo đảm planner dùng đồng thời cả ba index**: với dữ liệu nhỏ, planner có thể chọn scan rồi lọc. Dùng `EXPLAIN` hoặc `PROFILE` để xem kế hoạch cụ thể.

### 5.2. Point

Đổi vị trí của node:

```cypher
MATCH (a:Article {id: 'A001'})
SET a.location = point({longitude: 106.7100, latitude: 10.7850});
```

Tìm theo bán kính:

```cypher
MATCH (a:Article)
WHERE point.distance(
  a.location,
  point({longitude: 106.7100, latitude: 10.7850})
) <= 1000
RETURN a.id, a.location;
```

Không cần lệnh `REINDEX` sau `SET`. Nếu không thấy kết quả như dự kiến, kiểm tra **CRS**, tọa độ `longitude`/`latitude`, đơn vị bán kính (mét với WGS 84) và predicate trước khi quy lỗi cho index.

## 6. Full-text: cập nhật đồng bộ và eventual consistency

### 6.1. Hai chế độ vận hành

Full-text index phân tích chuỗi thành token để tìm kiếm theo từ, đánh điểm liên quan. Nó **khác text index** chuyên xử lý `CONTAINS`, `ENDS WITH`, `STARTS WITH` trong điều kiện Cypher thông thường.

Với cấu hình mặc định `fulltext.eventually_consistent: false`, cập nhật full-text được xử lý trong đường commit của transaction. Với `true`, Neo4j đưa công việc cập nhật vào hàng đợi để áp dụng ở nền, giúp giảm chi phí commit trong trường hợp có nhiều ghi.

| Tiêu chí | Full-text mặc định | Full-text eventual |
| --- | --- | --- |
| `fulltext.eventually_consistent` | `false` | `true` |
| Thời điểm xử lý thay đổi index | Trong quá trình commit | Sau commit, qua hàng đợi và luồng nền |
| Hiện tượng ngay sau commit | Index được cập nhật theo chế độ đồng bộ | Truy vấn có thể thấy token cũ hoặc chưa thấy token mới |
| Đổi lại | Commit phải chịu chi phí cập nhật index | Tăng thông lượng ghi trong một số tải; phải chấp nhận trễ |
| Khi nào phù hợp | Tìm kiếm cần phản ánh ngay dữ liệu đã commit | Search nội dung có thể chấp nhận độ trễ ngắn |

Ví dụ đổi nội dung:

```cypher
MATCH (a:Article {id: 'A001'})
SET a.title = 'Tối ưu hóa chỉ mục Neo4j',
    a.body = 'Hướng dẫn quản lý index và truy vấn tìm kiếm.';
```

Trong môi trường Cypher 5 hoặc Neo4j 5.x, có thể truy vấn full-text bằng thủ tục:

```cypher
CALL db.index.fulltext.queryNodes('idx_article_fulltext', 'Neo4j')
YIELD node, score
RETURN node.id AS articleId, node.title AS title, score
ORDER BY score DESC;
```

Vì ví dụ đã bật eventual, truy vấn này thực thi **ngay sau khi commit** có thể chưa thấy toàn bộ token mới. Bước đảm bảo cập nhật hàng đợi:

```cypher
CALL db.index.fulltext.awaitEventuallyConsistentIndexRefresh();
```

**Thứ tự thao tác đúng:** (1) hoàn tất và commit lệnh `SET`; (2) gọi `awaitEventuallyConsistentIndexRefresh()` trong lệnh/transaction tiếp theo; (3) mới chạy truy vấn full-text cần đối soát. Thủ tục này chờ các cập nhật của **full-text eventual** đã commit gần đây; **không** phải lệnh tạo lại toàn bộ index, không dành cho vector/range/text/point.

Nếu ứng dụng yêu cầu *read-your-write* ngay lập tức cho tìm kiếm văn bản quan trọng, chế độ đồng bộ thường dễ đáp ứng hơn. Khi chọn eventual, có thể áp dụng chờ refresh ở những luồng đặc biệt (ví dụ xác nhận nội dung vừa xuất bản) thay vì ép tất cả yêu cầu tìm kiếm chờ.

### 6.2. Cú pháp tìm kiếm mới theo phiên bản

Kể từ **Neo4j 2026.09 với Cypher 25**, full-text index có thể được truy vấn bằng mệnh đề `SEARCH` và đây là hướng dùng được ưu tiên trong tài liệu mới:

```cypher
CYPHER 25
MATCH (a:Article)
SEARCH a IN (
  FULLTEXT INDEX idx_article_fulltext
  FOR 'Neo4j'
  LIMIT 10
) SCORE AS score
RETURN a.id AS articleId, a.title AS title, score;
```

Thủ tục `db.index.fulltext.queryNodes()` vẫn hữu ích cho tương thích phiên bản cũ và Cypher 5, nhưng **đã được đánh dấu deprecated trong Cypher 25 kể từ Neo4j 2026.10**. Khi phát triển mới, xác nhận phiên bản Neo4j và Cypher của hệ thống trước khi chọn API.

### 6.3. Analyzer không phải lỗi nhất quán

Full-text dùng analyzer để tách từ, chuẩn hóa chữ hoa/chữ thường, và có thể xử lý stopwords. Khi tìm `graph` mà không thấy một chuỗi bất kỳ có chứa `graph`, nguyên nhân có thể là quy tắc token/analyzer, **không phải index chưa cập nhật**.

```cypher
CALL db.index.fulltext.listAvailableAnalyzers()
YIELD analyzer, description
RETURN analyzer, description
ORDER BY analyzer;
```

Giá trị `fulltext.analyzer` và `fulltext.eventually_consistent` được xác định khi tạo index. Thay đổi cấu hình mặc định của DBMS **không làm thay đổi một full-text index đã tạo**. Muốn đổi analyzer hoặc eventual mode, cần kế hoạch tạo lại index với cấu hình mới và chờ nó `ONLINE`.

## 7. Vector: cập nhật embedding và giới hạn nhất quán

Vector index dùng embedding số để tìm những node/relationship có nội dung gần nhau trong không gian vector. Nó hỗ trợ **approximate nearest neighbor** (ANN), nên kết quả không bảo đảm là tập k láng giềng chính xác tuyệt đối.

Ba khía cạnh cần kiểm tra độc lập:

1. **Dữ liệu gốc:** `a.embedding` đã được ghi và commit đúng số chiều, đúng thứ tự thành phần và mô hình embedding chưa?
2. **Trạng thái index:** `idx_article_embedding` đã `ONLINE`, cấu hình `vector.dimensions`/`vector.similarity_function` phù hợp chưa?
3. **Truy vấn ANN:** `k` có đủ lớn, score có hợp lý và yêu cầu *recall* có phù hợp đặc tính tìm kiếm xấp xỉ không?

Ví dụ cập nhật embedding:

```cypher
MATCH (a:Article {id: 'A001'})
SET a.embedding = [0.6, 0.8, 0.0];
```

Xác nhận dữ liệu gốc đã commit:

```cypher
MATCH (a:Article {id: 'A001'})
RETURN a.id, a.embedding;
```

Truy vấn vector theo thủ tục tương thích Neo4j 5.x:

```cypher
CALL db.index.vector.queryNodes(
  'idx_article_embedding', 3, [0.6, 0.8, 0.0]
)
YIELD node, score
RETURN node.id AS articleId, score
ORDER BY score DESC;
```

Từ **Neo4j 2026.01 (Cypher 25)**, `SEARCH` là cú pháp được ưu tiên để truy vấn vector:

```cypher
CYPHER 25
MATCH (a:Article)
SEARCH a IN (
  VECTOR INDEX idx_article_embedding
  FOR [0.6, 0.8, 0.0]
  LIMIT 3
) SCORE AS score
RETURN a.id AS articleId, score;
```

`db.index.vector.queryNodes()` được đánh dấu deprecated kể từ Neo4j 2026.04; vẫn có thể gặp trong hệ thống dùng Cypher 5 hoặc phiên bản cũ. Quan trọng hơn, **thay đổi ghi trong cùng transaction không được vector index nhìn thấy qua truy vấn index của chính transaction đó**. Hãy hoàn tất commit rồi tìm trong một transaction đọc tiếp theo; không thiết kế luồng “vừa `SET embedding` vừa vector search trong cùng transaction” với kỳ vọng node mới luôn có mặt.

**Không áp dụng** `db.index.fulltext.awaitEventuallyConsistentIndexRefresh()` để chờ vector. Thủ tục đó chỉ dành cho full-text eventual. Ngoài ra, việc ANN trả thiếu một ứng viên top-k có thể do tính xấp xỉ, lượng dữ liệu hoặc tham số tìm kiếm, dù embedding trong graph store đúng.

**Thay đổi mô hình embedding:** khi chuyển từ mô hình 3 chiều sang mô hình 768 chiều chẳng hạn, không ghi chồng vector mới vào thuộc tính cũ rồi giữ nguyên index 3 chiều. Một lộ trình an toàn hơn là tạo thuộc tính `embeddingV2`, tạo vector index mới có dimensions tương ứng, nạp lại dữ liệu, chờ `ONLINE`, kiểm thử chất lượng truy vấn rồi chuyển ứng dụng sang index mới.

## 8. Theo dõi trạng thái và chẩn đoán index

### 8.1. Kiểm tra schema và trạng thái

```cypher
SHOW INDEXES
YIELD name, type, entityType, labelsOrTypes, properties,
      state, populationPercent, owningConstraint,
      options, failureMessage
RETURN name, type, entityType, labelsOrTypes, properties,
       state, populationPercent, owningConstraint,
       options, failureMessage
ORDER BY type, name;
```

Những trường quan trọng:

- **`state`**: `POPULATING` đang xây; `ONLINE` đã sẵn sàng; `FAILED` cần kiểm tra lỗi.
- **`populationPercent`**: tiến độ tạo index ban đầu, **không phải tỷ lệ hàng đợi full-text eventual đã refresh**.
- **`labelsOrTypes`, `properties`**: xác minh index đang bao phủ đúng label/relationship type và thuộc tính.
- **`options`**: kiểm tra analyzer, eventual consistency, dimensions hoặc similarity function của loại index hỗ trợ cấu hình.
- **`owningConstraint`**: xác định range index được sở hữu bởi uniqueness/key constraint, không được xóa độc lập.
- **`failureMessage`**: thông tin nguyên nhân nếu index bị lỗi khi tạo/khởi động.

Để xem nhanh các index chưa hoạt động:

```cypher
SHOW INDEXES
YIELD name, type, state, populationPercent, failureMessage
WHERE state <> 'ONLINE'
RETURN name, type, state, populationPercent, failureMessage;
```

Để kiểm tra chỉ mục có được planner dùng trong truy vấn thông thường:

```cypher
EXPLAIN
MATCH (a:Article)
WHERE a.category = 'DATABASE'
RETURN a.id, a.title;
```

Hoặc thực thi có thu thập số liệu:

```cypher
PROFILE
MATCH (a:Article)
WHERE a.title CONTAINS 'Neo4j'
RETURN a.id;
```

Quan sát operator truy cập index, `Rows`, `DB Hits` và thời gian thực tế. Graph thử nghiệm chỉ có vài node có thể được planner quét trực tiếp vì rẻ hơn dùng index. Truy vấn full-text/vector được gọi tường minh qua `SEARCH` hoặc thủ tục tương ứng, không mong planner tự đổi `CONTAINS` thành full-text search.

### 8.2. Hiểu đúng thao tác resampling

Neo4j có thủ tục:

```cypher
CALL db.resampleIndex('idx_article_category');
```

Resampling cập nhật **thống kê hỗ trợ query planner** và có thể làm planner chọn kế hoạch tốt hơn khi phân bố dữ liệu thay đổi. Nó **không phải** công cụ ép full-text eventual áp dụng hàng đợi, không tái tạo embedding và không thay thế việc xử lý một index ở trạng thái `FAILED`.

### 8.3. Nếu index báo `FAILED`

1. Đọc `failureMessage`, log Neo4j và xem đó là lỗi cấu hình, thuộc tính không hợp lệ, giới hạn kích thước khóa, thiếu tài nguyên hay vấn đề lưu trữ.
2. Sửa nguyên nhân gốc; nếu bắt buộc tạo lại một index thông thường, chuẩn bị migration để xóa index theo tên và tạo lại, đồng thời chờ `ONLINE`.
3. Nếu là **index thuộc constraint**, xử lý theo đường quản lý constraint: không dùng `DROP INDEX` trên backing index.
4. Nếu nghi ngờ hỏng dữ liệu/index trên đĩa, dùng công cụ kiểm tra nhất quán của phiên bản Neo4j và quy trình sao lưu/bảo trì thích hợp; không xóa dữ liệu chỉ để index hiện `ONLINE`.

Không nên dùng `DROP INDEX` ngay trên production chỉ vì truy vấn chậm một lần. Xóa index có thể làm các truy vấn phụ thuộc chậm mạnh và giai đoạn tạo lại phải populate từ dữ liệu hiện có.

## 9. Thay đổi cấu hình và triển khai index an toàn

Quản lý index là một phần của quản lý schema. Một quy trình migration hợp lý:

1. **Đo hiện trạng:** ghi nhận loại index, tên, schema, cấu hình, `ONLINE` và kế hoạch truy vấn đại diện.
2. **Xác định mục tiêu:** thay analyzer, cấu hình vector, bổ sung thuộc tính index, hoặc bỏ index không còn được dùng.
3. **Thử trên dữ liệu tương đương production:** đo chi phí ghi, thời gian populate, bộ nhớ, độ trễ tìm kiếm và độ chính xác kết quả.
4. **Triển khai migration có kiểm soát:** tạo index mới phù hợp hoặc thay thế index cũ theo kế hoạch; cân nhắc khoảng thời gian chưa có index tương đương.
5. **Chờ `ONLINE` rồi chuyển traffic truy vấn:** kiểm tra `SHOW INDEXES`, `EXPLAIN`/`PROFILE` hoặc chất lượng kết quả search.
6. **Theo dõi sau triển khai:** lỗi, tải ghi, độ trễ cập nhật full-text eventual, hit rate và dung lượng.

Không thể tạo hai index **cùng loại trên đúng cùng schema** chỉ bằng cách thay tên. Khi chỉ muốn đổi cấu hình full-text trên schema cũ, cần kế hoạch thay index; khi nâng cấp embeddings, có thể dùng **thuộc tính mới và schema mới** để chạy song song trong quá trình chuyển đổi.

**Chú ý `IF NOT EXISTS`:**

```cypher
CREATE FULLTEXT INDEX idx_article_fulltext IF NOT EXISTS
FOR (a:Article) ON EACH [a.title, a.body]
OPTIONS {
  indexConfig: {
    `fulltext.eventually_consistent`: false
  }
};
```

Nếu tên/schema index đã tồn tại với `eventually_consistent: true`, lệnh trên **không chỉnh sửa cấu hình index cũ**. Phải kiểm tra `SHOW INDEXES ... options` và thực hiện migration thực sự nếu mục tiêu là đổi chế độ.

## 10. Tích hợp Java Driver, Spring Data Neo4j và cluster

### 10.1. Java Driver: commit trước rồi chờ full-text eventual

Ví dụ Java Driver (giả sử có `Driver driver`) sử dụng **session chung** để thực hiện write, chờ refresh và search theo trình tự:

```java
import java.util.List;
import java.util.Map;
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;

try (Session session = driver.session(
        SessionConfig.forDatabase("neo4j"))) {

    // Transaction ghi: phải commit xong trước khi chờ refresh.
    session.executeWriteWithoutResult(tx ->
        tx.run(
            """
            MATCH (a:Article {id: $id})
            SET a.title = $title
            """,
            Map.of(
                "id", "A001",
                "title", "Neo4j full-text đã cập nhật"
            )
        ).consume()
    );

    // Chạy thành một lệnh riêng, sau khi write đã commit.
    session.run(
        "CALL db.index.fulltext.awaitEventuallyConsistentIndexRefresh()"
    ).consume();

    List<String> ids = session.executeRead(tx ->
        tx.run(
            """
            CALL db.index.fulltext.queryNodes(
              'idx_article_fulltext', $term
            )
            YIELD node, score
            RETURN node.id AS id
            """,
            Map.of("term", "Neo4j")
        ).list(record -> record.get("id").asString())
    );

    System.out.println(ids);
}
```

Thủ tục query full-text trong ví dụ phục vụ tương thích Cypher 5; với Neo4j 2026.09+/Cypher 25, ưu tiên chuyển phần đọc sang `SEARCH` theo cú pháp phiên bản đang triển khai.

Các lời gọi trong cùng `Session` được driver nối chuỗi theo bookmark, giúp duy trì **causal consistency** giữa các transaction trong cluster. Bookmark giải quyết thứ tự và khả năng thấy **transaction graph đã commit**; không mặc nhiên thay cho thủ tục chờ **hàng đợi full-text eventual** trên bản sao phục vụ search. Với cụm nhiều máy, cần kiểm thử luồng ghi/đọc thực tế và mức độ trễ từng nơi phục vụ truy vấn.

### 10.2. Spring Data Neo4j

Với Spring Data Neo4j, lưu ý:

- Các lệnh `save(...)`, `@Query` cập nhật node hoặc relationship vẫn phải hoàn tất transaction (`@Transactional`) trước khi yêu cầu search eventual kiểm chứng dữ liệu mới.
- Đặt `awaitEventuallyConsistentIndexRefresh()` **sau ranh giới commit**, không gọi ngay trước khi `@Transactional` kết thúc rồi giả định thay đổi đã được đưa vào hàng đợi.
- Khi thực thi raw Cypher cho full-text/vector search, kiểm tra mapping của `score` và dữ liệu trả về bằng `Neo4jClient`, projection hoặc DTO phù hợp.
- Không nhầm quản lý entity/index trong code với việc DBMS đã tạo đúng schema: quản lý `CREATE ... INDEX` bằng migration và xác minh qua `SHOW INDEXES`.

Việc update một thuộc tính Java liên quan `embedding` không tự làm mới embedding dựa trên nội dung văn bản. Nếu nội dung `body` đổi, ứng dụng phải **chủ động tạo embedding mới bằng mô hình tương ứng** rồi ghi giá trị đó để vector index cập nhật.

## 11. Những chẩn đoán sai thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách kiểm chứng |
| --- | --- | --- |
| Vừa tạo index nhưng truy vấn không dùng được | `POPULATING` hoặc `FAILED` | `SHOW INDEXES`, `db.awaitIndex(...)`, xem `failureMessage` |
| Full-text vừa ghi xong chưa tìm ra | `eventually_consistent: true`, đang chờ refresh | Kiểm tra `options`, commit, gọi thủ tục chờ refresh |
| Full-text không khớp chuỗi con bất kỳ | Token/analyzer khác kỳ vọng | Kiểm tra analyzer; so sánh với text index và `CONTAINS` |
| Query `CONTAINS` không sử dụng full-text index | Full-text chỉ truy vấn tường minh | Sử dụng `SEARCH`/thủ tục full-text nếu muốn lexical search |
| Vector tìm ngay trong transaction vừa ghi không có node mới | Vector index không thấy thay đổi cùng transaction | Commit rồi mở transaction đọc khác |
| Vector top-k không trả đúng “k kết quả gần nhất” | ANN là xấp xỉ; `k`/phân bố dữ liệu/cấu hình ảnh hưởng | Kiểm tra embedding trong store và đánh giá recall trên tập chuẩn |
| Tọa độ không được point index chọn | Giá trị không phải `POINT` hoặc sai CRS | `RETURN a.location`, kiểm tra schema, CRS và predicate |
| `MERGE` sinh trùng khi ghi đồng thời | Có index nhưng không có uniqueness constraint | Kiểm tra constraint theo khóa nghiệp vụ |
| Đổi `OPTIONS` trong `CREATE ... IF NOT EXISTS` nhưng không có tác dụng | Index đã tồn tại | `SHOW INDEXES ... options`, thực hiện migration cấu hình |
| `RESAMPLE` xong vẫn không có kết quả mới | Resample chỉ cập nhật thống kê planner | Kiểm tra giá trị gốc, index state, eventual refresh, query semantics |
| Query chậm dù index `ONLINE` | Planner chọn scan, độ chọn lọc kém, hoặc nhiều traversal | `EXPLAIN`/`PROFILE`, `Rows`, `DB Hits`, điều kiện truy vấn |

## 12. Bài tập thực hành

1. Tạo hai full-text index **trên các schema khác nhau**: một mặc định đồng bộ (ví dụ trên `Article.summary`) và một eventual (ví dụ trên `Article.title`, `Article.body`). Sau khi cập nhật dữ liệu và commit, quan sát sự khác biệt về thời điểm search phản ánh thay đổi.
2. Dùng `SHOW INDEXES` tìm index thuộc constraint. Giải thích vì sao `DROP INDEX` không được dùng để xóa backing index đó.
3. Cập nhật `A001.location`, kiểm tra truy vấn bán kính và dùng `EXPLAIN` xem planner có chọn point index không.
4. Sửa `A002.body` nhưng **chưa sửa `A002.embedding`**. Giải thích vì sao kết quả tìm kiếm full-text và vector có thể không tương ứng về ngữ nghĩa ngay cả khi cả hai index đã được cập nhật đúng.
5. Viết checklist triển khai từ embedding 3 chiều sang 768 chiều mà không làm sai dữ liệu đang phục vụ. Nêu cách tạo thuộc tính/index mới, nạp lại vector, chờ `ONLINE` và chuyển ứng dụng.
6. Phân biệt mục đích của `db.awaitIndexes()`, `db.index.fulltext.awaitEventuallyConsistentIndexRefresh()` và `db.resampleIndex(...)`.

## 13. Ghi nhớ

- Neo4j **tự động duy trì index** khi graph thay đổi; ứng dụng không cần sửa thủ công từng entry của range, text, point, token lookup, full-text hoặc vector index.
- **Transaction consistency**, **độ trễ refresh của index** và **độ chính xác tìm kiếm** là ba câu hỏi khác nhau.
- **Range, text, point và token lookup** thuộc nhóm performance index được cập nhật với transaction. **Full-text mặc định đồng bộ**, có thể **eventual** nếu bật `fulltext.eventually_consistent`.
- **Vector index** có giới hạn nhìn thấy các thay đổi trong cùng transaction và trả kết quả **k-NN xấp xỉ**; đừng áp dụng thủ tục chờ full-text cho vector.
- Luôn phân biệt **index `ONLINE`** với **full-text eventual đã refresh xong**, và **resampling statistics** với **rebuild index**.
- Dùng **uniqueness constraint** để giữ dữ liệu không trùng; index thường chỉ tăng tốc tìm kiếm. Khi vận hành, theo dõi `SHOW INDEXES`, `EXPLAIN`/`PROFILE`, cấu hình index, log và quy trình migration.

### Tài liệu tham khảo chính thức

- [Neo4j Cypher Manual — Indexes](https://neo4j.com/docs/cypher-manual/current/indexes/)
- [Neo4j Cypher Manual — Performance indexes](https://neo4j.com/docs/cypher-manual/current/indexes/performance-indexes/)
- [Neo4j Cypher Manual — Full-text indexes](https://neo4j.com/docs/cypher-manual/current/indexes/search-indexes/full-text-indexes/)
- [Neo4j Cypher Manual — Vector indexes](https://neo4j.com/docs/cypher-manual/current/indexes/search-indexes/vector-indexes/)
- [Neo4j Cypher Manual — Show indexes](https://neo4j.com/docs/cypher-manual/current/indexes/performance-indexes/list-indexes/)
- [Neo4j Operations Manual — Index configuration](https://neo4j.com/docs/operations-manual/current/performance/index-configuration/)
- [Neo4j Operations Manual — Built-in procedures](https://neo4j.com/docs/operations-manual/current/procedures/built-in-procedures/)
- [Neo4j Java Driver Manual — Bookmarks and causal consistency](https://neo4j.com/docs/java-manual/current/bookmarks/)
