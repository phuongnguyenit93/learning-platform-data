# Text index và các mẫu tìm kiếm chuỗi được hỗ trợ

## 1. Text index giải quyết bài toán gì trong Neo4j?

Trong mô hình **property graph** của Neo4j, node và relationship đều có thể mang các thuộc tính kiểu chuỗi (`STRING`): tên bài viết, tiêu đề phim, mã sản phẩm, email, mô tả mối quan hệ, v.v. Khi truy vấn Cypher phải lọc chuỗi theo tiền tố, hậu tố hoặc chuỗi con trên nhiều phần tử đồ thị, đọc tất cả node/relationship rồi kiểm tra từng giá trị có thể tốn kém.

**TEXT index** là một loại *performance index* trên **một thuộc tính chuỗi**, giúp bộ lập kế hoạch truy vấn (Cypher planner) tìm ứng viên hiệu quả hơn. Nó đặc biệt hữu ích với `CONTAINS` và `ENDS WITH`. Người lập trình vẫn viết `MATCH ... WHERE ...` bình thường; planner quyết định có sử dụng chỉ mục hay không dựa trên kiểu predicate, chỉ mục sẵn có và chi phí ước tính.

Trong chương **Chỉ mục tra cứu**, cần phân biệt bốn khái niệm thường bị gọi chung là "index":

| Loại index | Dữ liệu được lập chỉ mục | Trường hợp điển hình | Cách sử dụng |
|---|---|---|---|
| **Token lookup** (`LOOKUP`) | Nhãn node hoặc loại relationship | Tìm node theo nhãn, relationship theo loại | Planner dùng cho `MATCH (n:Label)` hay `MATCH ()-[r:TYPE]->()` |
| **Text** (`TEXT`) | Một thuộc tính `STRING` của node/relationship | Chuỗi con `CONTAINS`, hậu tố `ENDS WITH` | Planner dùng cho predicate chuỗi |
| **Range** (`RANGE`) | Thuộc tính dùng cho so sánh, sắp xếp | `=`, `IN`, khoảng giá trị, tiền tố `STARTS WITH` | Planner dùng cho predicate phù hợp |
| **Full-text** (`FULLTEXT`) | Một hoặc nhiều thuộc tính văn bản | Tìm từ/ngữ, phân tích văn bản, chấm điểm độ liên quan | Truy vấn full-text tường minh theo API/cú pháp của phiên bản Neo4j |

Tên chương "Chỉ mục tra cứu" **không có nghĩa TEXT index là token lookup index**. Token lookup không index nội dung thuộc tính; còn TEXT index không thay thế tìm kiếm từ khóa có xếp hạng của FULLTEXT.

### Kết quả học tập

Sau bài này, bạn có thể:

1. Tạo, kiểm tra trạng thái và xóa TEXT index cho thuộc tính node hoặc relationship.
2. Viết đúng các predicate `STARTS WITH`, `ENDS WITH`, `CONTAINS`, `=` và `IN`; dự đoán kết quả theo dữ liệu ví dụ.
3. Phân biệt điều kiện *được TEXT index hỗ trợ* với tình huống *planner thực sự chọn TEXT index*.
4. Dùng `EXPLAIN`/`PROFILE` để xem kế hoạch, nhận biết giới hạn về kiểu dữ liệu, chữ hoa/chữ thường và tìm kiếm không dấu.

## 2. Cơ chế và giới hạn của TEXT index

Neo4j dùng kỹ thuật **trigram** cho TEXT index: tách chuỗi thành các đoạn liên tiếp gồm ba Unicode code point. Ví dụ chuỗi `developer` tạo các trigram:

```text
developer
dev | eve | vel | elo | lop | ope | per
```

Các đoạn này tạo đường truy cập hữu ích cho tìm kiếm chuỗi nằm **ở giữa** (`CONTAINS`) hoặc **cuối** (`ENDS WITH`) của giá trị. RANGE index sắp xếp giá trị chuỗi theo thứ tự từ điển, nên thường phù hợp hơn với so sánh chính xác và tìm theo **đầu chuỗi** (`STARTS WITH`). Trigram giúp giải thích lợi thế của TEXT index nhưng không bảo đảm mọi truy vấn chứa chuỗi ngắn đều nhanh: planner còn xét độ chọn lọc và kích thước dữ liệu.

Các ràng buộc quan trọng:

- TEXT index dành cho **một thuộc tính** của **một nhãn node hoặc một loại relationship**; không tạo TEXT index tổng hợp trên nhiều thuộc tính.
- Chỉ các giá trị thuộc tính có kiểu `STRING` được lập chỉ mục; thuộc tính thiếu, `null`, số hoặc giá trị kiểu khác không trở thành mục chuỗi trong index.
- TEXT index **không tạo ràng buộc duy nhất**. Muốn cấm trùng mã định danh phải thiết kế constraint thích hợp, không chỉ tạo TEXT index.
- Một tên index phải duy nhất trong schema; dùng `IF NOT EXISTS` để việc tạo lại cùng index không gây lỗi trong điều kiện thông thường.
- Index được xây dựng ở nền; chỉ đo hiệu năng sau khi trạng thái báo `ONLINE`.
- TEXT index có giới hạn kích thước khóa chuỗi xấp xỉ **32 KiB** (tùy phiên bản/provider). Với văn bản cực dài, cần xem giới hạn vận hành; không nên mặc định có thể index mọi nội dung.

## 3. Dữ liệu thực hành: danh mục bài viết về cơ sở dữ liệu đồ thị

Ví dụ dùng nhãn `LI004Article` và các tên riêng có tiền tố `li004_` để dễ nhận diện, hạn chế ảnh hưởng dữ liệu khác. Nên chạy trong database thực hành. Lệnh dưới đây tạo tám node và có thể chạy lại để cập nhật các giá trị mẫu theo `code`:

```cypher
UNWIND [
  {code: 'a01', title: 'Neo4j Graph Database',
   slug: 'neo4j-graph-database'},
  {code: 'a02', title: 'Cypher Query Language',
   slug: 'cypher-query-language'},
  {code: 'a03', title: 'Spring Data Neo4j',
   slug: 'spring-data-neo4j'},
  {code: 'a04', title: 'Graph Analytics with Cypher',
   slug: 'graph-analytics-cypher'},
  {code: 'a05', title: 'Database Index Design',
   slug: 'database-index-design'},
  {code: 'a06', title: 'neo4j for beginners',
   slug: 'neo4j-for-beginners'},
  {code: 'a07', title: 'Đồ thị tri thức',
   slug: 'do-thi-tri-thuc'},
  {code: 'a08', title: 'Neo4j',
   slug: 'neo4j'}
] AS row
MERGE (a:LI004Article {code: row.code})
SET a.title = row.title,
    a.slug = row.slug;
```

Xem lại dữ liệu:

```cypher
MATCH (a:LI004Article)
RETURN a.code AS code, a.title AS title, a.slug AS slug
ORDER BY code;
```

Kỳ vọng nhận tám dòng `a01` đến `a08`. Nếu cơ sở dữ liệu thực hành đã có những node khác mang nhãn `LI004Article`, cần kiểm tra trước khi dựa vào số lượng kỳ vọng bên dưới.

### 3.1. Tạo TEXT index trên thuộc tính của node

```cypher
CREATE TEXT INDEX li004_article_title_text IF NOT EXISTS
FOR (a:LI004Article)
ON (a.title);
```

Lệnh này tạo index cho riêng thuộc tính `title` của node có nhãn `LI004Article`. Nó **không** tự tạo index cho `slug` hoặc các nhãn khác. Lệnh `IF NOT EXISTS` hữu ích khi khởi tạo schema nhiều lần; nếu tên index đã được dùng cho schema khác, cần kiểm tra schema thay vì giả định đã tạo được index như mong muốn.

Đọc trạng thái:

```cypher
SHOW TEXT INDEXES
YIELD name, type, state, populationPercent, labelsOrTypes, properties
WHERE name = 'li004_article_title_text'
RETURN name, type, state, populationPercent, labelsOrTypes, properties;
```

Khi index đã sẵn sàng, `type = 'TEXT'`, `state = 'ONLINE'`, `labelsOrTypes = ['LI004Article']` và `properties = ['title']`. Nếu còn `POPULATING`, hãy kiểm tra lại trạng thái trước khi so sánh kế hoạch thực thi.

## 4. Năm mẫu tìm kiếm chuỗi được TEXT index hỗ trợ

Các toán tử `STARTS WITH`, `ENDS WITH` và `CONTAINS` trong Cypher **phân biệt hoa/thường**. Tìm `Neo4j` sẽ không tự động khớp `neo4j`. Hai biểu thức khác, dù diễn đạt gần nhau trong ngôn ngữ tự nhiên, có thể trả tập kết quả khác nhau.

| Mẫu | Điều kiện Cypher | Ý nghĩa | Kết quả kỳ vọng trên dữ liệu mẫu |
|---|---|---|---|
| Tiền tố | `a.title STARTS WITH 'Neo4j'` | Tiêu đề bắt đầu bằng `Neo4j` | `a01`, `a08` |
| Hậu tố | `a.title ENDS WITH 'Neo4j'` | Tiêu đề kết thúc bằng `Neo4j` | `a03`, `a08` |
| Chuỗi con | `a.title CONTAINS 'Graph'` | Có chuỗi `Graph` ở vị trí bất kỳ | `a01`, `a04` |
| So khớp chính xác | `a.title = 'Neo4j'` | Toàn bộ tiêu đề bằng `Neo4j` | `a08` |
| Trong tập chuỗi | `a.title IN ['Neo4j', 'Cypher Query Language']` | Tiêu đề trùng một giá trị trong danh sách | `a02`, `a08` |

### 4.1. `STARTS WITH`: tìm tiền tố

```cypher
MATCH (a:LI004Article)
WHERE a.title STARTS WITH 'Neo4j'
RETURN a.code AS code, a.title AS title
ORDER BY code;
```

Trả `a01` và `a08`. `a06` không khớp do chữ `n` thường. TEXT index **có thể** giải điều kiện này, nhưng nếu có RANGE index trên cùng thuộc tính, planner thường ưu tiên RANGE index nhờ cách sắp xếp chuỗi của nó.

### 4.2. `ENDS WITH`: tìm hậu tố

```cypher
MATCH (a:LI004Article)
WHERE a.title ENDS WITH 'Neo4j'
RETURN a.code AS code, a.title AS title
ORDER BY code;
```

Trả `a03` và `a08`. Đây là một trong hai dạng tìm kiếm TEXT index thường có lợi thế rõ hơn RANGE index.

### 4.3. `CONTAINS`: tìm chuỗi con

```cypher
MATCH (a:LI004Article)
WHERE a.title CONTAINS 'Graph'
RETURN a.code AS code, a.title AS title
ORDER BY code;
```

Trả `a01` và `a04`. Thử thay `'Graph'` bằng `'neo4j'`, kết quả là `a06`; `'Neo4j'` và `'neo4j'` không tương đương.

### 4.4. `=` và `IN`: so sánh chuỗi chính xác

```cypher
MATCH (a:LI004Article)
WHERE a.title = 'Neo4j'
RETURN a.code AS code, a.title AS title;
```

Kết quả: `a08`.

```cypher
MATCH (a:LI004Article)
WHERE a.title IN ['Neo4j', 'Cypher Query Language']
RETURN a.code AS code, a.title AS title
ORDER BY code;
```

Kết quả: `a02`, `a08`. TEXT index có thể hỗ trợ `=` và `IN` **khi planner xác định biểu thức so sánh là chuỗi**. Nếu bên phải là giá trị từ property có kiểu không biết trước, điều kiện có thể không đủ thông tin để tận dụng TEXT index.

### 4.5. Kiểm chứng dữ liệu và kết quả bằng một truy vấn

```cypher
MATCH (a:LI004Article)
WITH collect({code: a.code, title: a.title}) AS rows
RETURN
  size(rows) = 8
  AND size([x IN rows WHERE x.title STARTS WITH 'Neo4j']) = 2
  AND size([x IN rows WHERE x.title ENDS WITH 'Neo4j']) = 2
  AND size([x IN rows WHERE x.title CONTAINS 'Graph']) = 2
  AND size([x IN rows WHERE x.title = 'Neo4j']) = 1
  AND size([x IN rows WHERE
    x.title IN ['Neo4j', 'Cypher Query Language']]) = 2
  AS passed;
```

Trên bộ dữ liệu mẫu đầy đủ, `passed` phải là `true`. Đây là kiểm thử **tính đúng đắn của predicate**, không phải kiểm thử tốc độ hoặc bằng chứng planner đã dùng index.

## 5. Khi nào Cypher planner thực sự dùng TEXT index?

**Được hỗ trợ không đồng nghĩa chắc chắn được chọn.** Với tám node, quét theo nhãn có thể rẻ hơn truy cập index; trên tập dữ liệu lớn, bộ lập kế hoạch thường có cơ sở tốt hơn để chọn chỉ mục phù hợp.

Dùng `EXPLAIN` để xem kế hoạch **mà chưa chạy truy vấn**:

```cypher
EXPLAIN
MATCH (a:LI004Article)
WHERE a.title CONTAINS 'Graph'
RETURN a.code AS code, a.title AS title;
```

Dùng `PROFILE` để vừa chạy câu lệnh đọc vừa thu thập số dòng thực tế, số lần truy cập cơ sở dữ liệu (`DB Hits`) và chi phí của từng toán tử:

```cypher
PROFILE
MATCH (a:LI004Article)
WHERE a.title ENDS WITH 'Neo4j'
RETURN a.code AS code, a.title AS title;
```

Trong kế hoạch, tìm toán tử truy cập index và phần mô tả `TEXT INDEX ... LI004Article(title)`. Tên toán tử cụ thể có thể thay đổi theo phiên bản và predicate; nếu thấy quét theo nhãn, không kết luận rằng cú pháp index bị sai khi chưa xem trạng thái `ONLINE`, thống kê và độ chọn lọc.

### 5.1. So sánh với RANGE index trên cùng thuộc tính

Có thể tạo thêm index dưới đây **chỉ để thử nghiệm**:

```cypher
CREATE RANGE INDEX li004_article_title_range IF NOT EXISTS
FOR (a:LI004Article)
ON (a.title);
```

Khi cả TEXT và RANGE index đều tồn tại trên `title`:

| Predicate | Loại index planner thường ưu tiên | Giải thích |
|---|---|---|
| `CONTAINS` | TEXT | Tìm chuỗi con phù hợp với trigram |
| `ENDS WITH` | TEXT | Tìm hậu tố phù hợp với trigram |
| `STARTS WITH` | RANGE | Tìm tiền tố theo thứ tự từ điển |
| `=`, `IN` với chuỗi | RANGE | Truy cập theo giá trị chính xác |

Đây là **xu hướng lựa chọn khi cả hai index đều khả dụng**, không phải cam kết rằng truy vấn nhỏ nào cũng sử dụng index. Khi *chỉ có* TEXT index, nó vẫn có thể giải `STARTS WITH`, `=` và `IN` nếu đáp ứng điều kiện kiểu dữ liệu.

Để minh họa khả năng ép một loại index trong lúc học, có thể dùng index hint:

```cypher
EXPLAIN
MATCH (a:LI004Article)
USING TEXT INDEX a:LI004Article(title)
WHERE a.title CONTAINS 'Graph'
RETURN a.code, a.title;
```

`USING TEXT INDEX` chỉ nên dùng có chủ đích khi phân tích kế hoạch; hint sai hoặc index không có/không tương thích có thể làm truy vấn không lập được kế hoạch hoặc chạy chậm. Trong phần lớn ứng dụng, nên để planner chọn tự động trước.

### 5.2. Dùng tham số cho truy vấn từ ứng dụng Java

Đối với Java Driver hoặc Spring Data Neo4j, truyền điều kiện tìm kiếm thành **tham số**; không ghép chuỗi do người dùng nhập vào mã Cypher:

```cypher
MATCH (a:LI004Article)
WHERE a.title CONTAINS $fragment
RETURN a.code AS code, a.title AS title
ORDER BY code;
```

Giả sử `fragment = "Graph"`, kỳ vọng `a01` và `a04`. Truy vấn dùng tham số vẫn có thể tận dụng index tương ứng. Một ví dụ Java Driver với đối tượng `driver` đã được cấu hình:

```java
String cypher = """
    MATCH (a:LI004Article)
    WHERE a.title CONTAINS $fragment
    RETURN a.code AS code, a.title AS title
    ORDER BY code
    """;

try (var session = driver.session()) {
    var rows = session.executeRead(tx ->
        tx.run(cypher, java.util.Map.of("fragment", "Graph")).list()
    );
    rows.forEach(row ->
        System.out.println(row.get("code").asString() + ": "
            + row.get("title").asString())
    );
}
```

Đoạn Java minh họa phần **gọi truy vấn**; dự án vẫn cần thiết lập driver, xác thực và quản lý kết nối theo cấu hình riêng. Với nhu cầu không phân biệt hoa/thường, chuẩn hóa dữ liệu và tham số nhất quán thay vì nối chuỗi động vào Cypher.

## 6. TEXT index cho thuộc tính của relationship

Index không giới hạn ở node. Chẳng hạn trong đồ thị tài liệu, relationship `LI004_REFERENCES` lưu `context` để giải thích vì sao bài viết này dẫn sang bài khác.

Tạo hai relationship mẫu:

```cypher
MATCH (a:LI004Article {code: 'a01'})
MATCH (b:LI004Article {code: 'a02'})
MERGE (a)-[r:LI004_REFERENCES]->(b)
SET r.context = 'cypher-guide';
```

```cypher
MATCH (a:LI004Article {code: 'a03'})
MATCH (b:LI004Article {code: 'a01'})
MERGE (a)-[r:LI004_REFERENCES]->(b)
SET r.context = 'neo4j-guide';
```

Tạo TEXT index riêng cho thuộc tính relationship:

```cypher
CREATE TEXT INDEX li004_relation_context_text IF NOT EXISTS
FOR ()-[r:LI004_REFERENCES]-()
ON (r.context);
```

Ví dụ tìm các liên kết có ngữ cảnh kết thúc bằng `guide`:

```cypher
MATCH (source:LI004Article)-[r:LI004_REFERENCES]->(target:LI004Article)
WHERE r.context ENDS WITH 'guide'
RETURN source.code AS sourceCode,
       target.code AS targetCode,
       r.context AS context
ORDER BY sourceCode;
```

Trả hai quan hệ `a01 → a02` (`cypher-guide`) và `a03 → a01` (`neo4j-guide`). Index này áp dụng cho **relationship type + một thuộc tính**; nó không index chuỗi `context` của relationship loại khác.

## 7. Các trường hợp TEXT index không giải quyết trực tiếp

### 7.1. Tìm kiếm không phân biệt hoa/thường và dấu tiếng Việt

`STARTS WITH`, `ENDS WITH`, `CONTAINS` mặc định **phân biệt hoa/thường**. Chúng cũng không tự bỏ dấu tiếng Việt; `'Đồ thị'` không tương đương `'Do thi'`. Cách viết sau có thể tạo kết quả không phân biệt chữ hoa/thường:

```cypher
MATCH (a:LI004Article)
WHERE toLower(a.title) CONTAINS 'neo4j'
RETURN a.code AS code, a.title AS title
ORDER BY code;
```

Kết quả dự kiến: `a01`, `a03`, `a06` và `a08`. Tuy nhiên, **đưa hàm `toLower()` lên thuộc tính đang lập chỉ mục** có thể khiến planner không tận dụng TEXT index trên `title`.

Nếu tìm kiếm không phân biệt hoa/thường là nhu cầu thường xuyên, cân nhắc **lưu sẵn trường chuẩn hóa** (ví dụ `titleSearch`), tạo TEXT index riêng trên trường đó và chuẩn hóa *cả dữ liệu lẫn đầu vào* theo cùng một quy tắc. Đối với tiếng Việt, cần quyết định nghiệp vụ có bỏ dấu hay không; chuyển chữ thường không đồng nghĩa chuẩn hóa dấu hoặc Unicode.

### 7.2. Regex hoặc tìm từ khóa có xếp hạng

Biểu thức chính quy dùng toán tử `=~`:

```cypher
MATCH (a:LI004Article)
WHERE a.title =~ '(?i).*neo4j.*'
RETURN a.code AS code, a.title AS title
ORDER BY code;
```

`(?i)` cho phép tìm không phân biệt hoa/thường trong regex, nhưng **không nên kỳ vọng regex sẽ được tăng tốc như `CONTAINS` bằng TEXT index**. Khi cần tách từ, phân tích ngôn ngữ, truy vấn thuật ngữ và xếp hạng kết quả theo độ liên quan, hãy xét **FULLTEXT index**; cách truy vấn FULLTEXT phụ thuộc phiên bản Neo4j đang chạy.

TEXT index trả các giá trị **thỏa predicate**; nó không tính *relevance score* hay tìm gần đúng theo ngữ nghĩa. Với tìm kiếm ngữ nghĩa (semantic similarity), có thể cần vector index và một quy trình khác.

### 7.3. Sai kiểu dữ liệu hoặc biểu thức che mất thuộc tính

Đoạn sau có thể không tận dụng TEXT index nếu planner không biết trước kiểu của `input.value`:

```cypher
WITH {value: 'Graph'} AS input
MATCH (a:LI004Article)
WHERE a.title CONTAINS input.value
RETURN a.code, a.title;
```

Có thể làm rõ kiểu **ở phía giá trị truy vấn**, giữ nguyên thuộc tính đã index:

```cypher
WITH {value: 'Graph'} AS input
MATCH (a:LI004Article)
WHERE a.title CONTAINS toString(input.value)
RETURN a.code, a.title;
```

Lưu ý: điều kiện **dùng được index** còn phụ thuộc kiểu dữ liệu và kế hoạch cụ thể; hãy kiểm tra bằng `EXPLAIN`. Tránh tùy tiện đổi thành `toString(a.title)` hoặc biến đổi `a.title` ngay trong `WHERE`, bởi phép biến đổi trên vế thuộc tính có thể ngăn index được sử dụng.

### 7.4. Chỉ mục không tự thay thế thiết kế dữ liệu

- TEXT index không giúp trả lời phép duyệt đường đi (`shortest path`, mở rộng nhiều hop) nếu truy vấn không có predicate thuộc tính chuỗi tương ứng.
- Không tạo một TEXT index cho mọi trường chuỗi theo thói quen: mỗi index tốn dung lượng và chi phí bảo trì khi ghi. Chọn thuộc tính có truy vấn thực tế cần `CONTAINS`/`ENDS WITH`.
- Không nhầm index với constraint: TEXT index không bảo đảm `code` hoặc `email` duy nhất.
- Với nhiều điều kiện lọc, số dòng trung gian và mức độ chọn lọc cũng có thể quan trọng hơn việc một index cụ thể có tồn tại hay không.

## 8. Kiểm tra trạng thái, dọn dữ liệu và bài tập

Để liệt kê các index của bài thực hành:

```cypher
SHOW INDEXES
YIELD name, type, state, entityType, labelsOrTypes, properties
WHERE name STARTS WITH 'li004_'
RETURN name, type, state, entityType, labelsOrTypes, properties
ORDER BY name;
```

Khi hoàn tất, **chỉ trong database thực hành**, có thể dọn ba index đã tạo và các node mẫu (lệnh `DETACH DELETE` cũng xóa relationship gắn với các node đó):

```cypher
DROP INDEX li004_article_title_text IF EXISTS;
```

```cypher
DROP INDEX li004_article_title_range IF EXISTS;
```

```cypher
DROP INDEX li004_relation_context_text IF EXISTS;
```

```cypher
MATCH (a:LI004Article)
DETACH DELETE a;
```

### Bài tập tự luyện

1. Tạo TEXT index cho `LI004Article(slug)`. Viết truy vấn tìm các `slug` kết thúc bằng `'neo4j'`; xác định mã bài viết và kiểm tra `EXPLAIN`.
2. So sánh `a.title CONTAINS 'Neo4j'` với `a.title CONTAINS 'neo4j'`. Vì sao hai truy vấn trả tập kết quả khác nhau? Muốn tìm cả hai, bạn sẽ thiết kế `titleSearch` như thế nào?
3. Giữ cả TEXT và RANGE index trên `title`; chạy `EXPLAIN` cho `STARTS WITH`, `ENDS WITH`, `CONTAINS`. Ghi lại toán tử, loại index thực tế và giải thích trường hợp planner chọn quét nhãn.
4. Thử thuộc tính `slug` của một bài viết có giá trị `null`/không tồn tại. Vì sao không thể dùng TEXT index để tìm trực tiếp một giá trị chuỗi chưa được lưu?
5. Mở rộng hai relationship mẫu và thêm truy vấn `r.context CONTAINS 'neo4j'`. Giải thích vì sao TEXT index trên node `title` không tăng tốc predicate ở relationship `context`.

**Tự kiểm tra sau bài học:** Bạn cần nêu đúng năm nhóm predicate TEXT index hỗ trợ, hiểu lý do `CONTAINS`/`ENDS WITH` là trường hợp nổi bật, phân biệt TEXT với RANGE/LOOKUP/FULLTEXT, đọc được trạng thái `ONLINE` và phân tích kế hoạch truy vấn mà không mặc định index luôn được chọn.

## 9. Tài liệu đối chiếu

- [Neo4j Cypher Manual — Create indexes](https://neo4j.com/docs/cypher-manual/current/indexes/performance-indexes/create-indexes/): cú pháp, predicate hỗ trợ và trigram.
- [Neo4j Cypher Manual — The impact of indexes on query performance](https://neo4j.com/docs/cypher-manual/current/indexes/performance-indexes/using-indexes/): chọn TEXT/RANGE index và đọc kế hoạch.
- [Neo4j Cypher Manual — Show indexes](https://neo4j.com/docs/cypher-manual/current/indexes/performance-indexes/list-indexes/): kiểm tra trạng thái và thống kê.
- [Neo4j Cypher Manual — Index hints](https://neo4j.com/docs/cypher-manual/current/indexes/performance-indexes/index-hints/): `USING TEXT INDEX` và các lưu ý về ép kế hoạch.
