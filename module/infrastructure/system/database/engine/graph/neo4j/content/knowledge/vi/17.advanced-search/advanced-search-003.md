# Phân biệt chỉ mục văn bản thông thường với chỉ mục toàn văn trong Neo4j

Trong Neo4j, cùng là tìm trên dữ liệu `STRING` nhưng hai nhu cầu sau **không giống nhau**:

- **Lọc theo điều kiện chuỗi chính xác:** “Lấy bài có tiêu đề chứa đúng chuỗi `Graph`”, “Mã bài bắt đầu bằng `G-`”, “Tên tài liệu kết thúc bằng `Guide`”.
- **Tìm kiếm theo nội dung:** “Tìm các bài nói về `graph` dù từ đó xuất hiện ở tiêu đề hay phần mô tả; xếp kết quả theo mức độ liên quan”, “Tìm cụm từ `graph modeling`”.

Với nhu cầu thứ nhất, Neo4j có **text index** — một loại *performance index* hỗ trợ điều kiện chuỗi trong Cypher. Với nhu cầu thứ hai, Neo4j có **full-text index** — một loại *search index* dựa trên Apache Lucene, phân tích nội dung thành các token và trả thêm điểm liên quan.

Bài học thuộc chương **Tìm kiếm nâng cao** trong module `DATABASE_ENGINE_GRAPH_NEO4J`. Kiến thức này giúp lựa chọn chỉ mục phù hợp cho property graph gồm node, relationship và các thuộc tính văn bản, đồng thời thiết kế truy vấn đúng trong Cypher, Neo4j Java Driver và Spring Data Neo4j.

## 1. Hai loại index phục vụ hai cách đặt câu hỏi

| Tiêu chí | Text index: `CREATE TEXT INDEX` | Full-text index: `CREATE FULLTEXT INDEX` |
| --- | --- | --- |
| Nhóm | *Performance index*: tăng tốc các điều kiện lọc | *Search index*: tìm kiếm từ ngữ và xếp hạng |
| Cách truy vấn | `MATCH ... WHERE`; Cypher planner tự quyết định sử dụng | Gọi tường minh `SEARCH` (Cypher 25 mới) hoặc procedure full-text |
| Đơn vị so khớp | Giá trị chuỗi, tiền tố, hậu tố, chuỗi con theo toán tử Cypher | Các **token** được analyzer tách từ nội dung |
| Toán tử/cú pháp | `=`, `IN`, `STARTS WITH`, `ENDS WITH`, `CONTAINS` | Truy vấn Lucene: từ khóa, cụm từ, `AND`/`OR`, ... |
| Phân tích ngôn ngữ | Không có analyzer cấu hình cho text index | Có tokenizer/analyzer, có thể điều chỉnh xử lý từ |
| Hoa/thường | Kết quả tuân theo phép so chuỗi của Cypher; phân biệt hoa/thường với điều kiện thông thường | Analyzer mặc định chuyển chữ về dạng thường, nên truy vấn thường không phân biệt hoa/thường |
| Độ liên quan | Không trả điểm tìm kiếm | Trả `score` để xếp hạng các kết quả khớp |
| Phạm vi tạo chỉ mục | **Một** property chuỗi trên **một** node label hoặc relationship type | Có thể bao gồm **nhiều** label/type và **nhiều** property |
| Giá trị được index | Property dạng `STRING` | `STRING` và danh sách `LIST<STRING>` |
| Vai trò với nghiệp vụ | Lọc chính xác theo điều kiện, giữ ngữ nghĩa câu lệnh Cypher | Khám phá tài liệu/bản ghi có nội dung phù hợp, trả kết quả theo relevance |

**Không nên hiểu “text index” là tên gọi ngắn của “full-text index”.** Hai loại có cấu trúc, ngữ nghĩa tìm kiếm và cách kích hoạt khác nhau. Cũng không nên lẫn `TEXT INDEX` với `RANGE INDEX`: range index thường phù hợp cho tra cứu bằng, theo khoảng giá trị và tìm tiền tố; text index đặc biệt hữu ích cho `CONTAINS` và `ENDS WITH`. Cả range và text đều thuộc nhóm performance index.

## 2. Dựng dữ liệu mẫu và nêu mục tiêu tìm kiếm

Để tự kiểm chứng, chạy dữ liệu sau **một lần trên database thử nghiệm**. Các label/type có tiền tố `SearchDemo` giúp phân biệt với dữ liệu ứng dụng. Không chạy `CREATE` lặp lại nếu muốn đối chiếu số lượng ví dụ.

```cypher
CREATE
  (a:SearchDemoArticle {
    code: 'G-101',
    title: 'Neo4j Graph Modeling',
    body: 'Learn nodes and relationships with Cypher'
  }),
  (b:SearchDemoArticle {
    code: 'G-102',
    title: 'Graph Queries in Cypher',
    body: 'Cypher matches connected data and graph paths'
  }),
  (c:SearchDemoArticle {
    code: 'J-201',
    title: 'Java Driver Guide',
    body: 'Build Java applications with the Neo4j driver'
  }),
  (d:SearchDemoArticle {
    code: 'N-301',
    title: 'Introduction to Neo4j',
    body: 'Install a graph database and learn Cypher basics'
  }),
  (a)-[:SEARCH_DEMO_RELATED {note: 'Graph patterns for Cypher readers'}]->(b),
  (d)-[:SEARCH_DEMO_RELATED {note: 'Graph database setup guide'}]->(a);
```

Hình dung đồ thị:

```text
G-101 "Neo4j Graph Modeling" ──SEARCH_DEMO_RELATED──► G-102 "Graph Queries in Cypher"

N-301 "Introduction to Neo4j" ──SEARCH_DEMO_RELATED──► G-101

J-201 "Java Driver Guide" (không có quan hệ SEARCH_DEMO_RELATED)
```

Trong bộ dữ liệu:

- Hai tiêu đề G-101 và G-102 chứa chính xác `Graph`.
- Ba bài G-101, G-102, N-301 có từ `graph` trong ít nhất một property `title` hoặc `body`.
- Bài J-201 không có từ `graph` trong hai property này, dù dùng Neo4j.
- Chỉ G-101 có cụm từ `Graph Modeling` liên tiếp trong tiêu đề.

Các ví dụ cố ý dùng từ tiếng Anh đơn giản để dễ kiểm tra tokenizer. Khi xử lý nội dung tiếng Việt có dấu, cần kiểm tra analyzer riêng (mục 7).

## 3. Text index: tăng tốc điều kiện chuỗi của Cypher

Tạo text index trên **một property** `title` của label `SearchDemoArticle`:

```cypher
CREATE TEXT INDEX search_demo_title_text IF NOT EXISTS
FOR (a:SearchDemoArticle)
ON (a.title);
```

Một vài truy vấn Cypher có thể được text index hỗ trợ:

```cypher
// Giá trị title phải bằng chính xác chuỗi được cung cấp
MATCH (a:SearchDemoArticle)
WHERE a.title = 'Neo4j Graph Modeling'
RETURN a.code AS code, a.title AS title;
```

```cypher
// Tiền tố của toàn bộ chuỗi title
MATCH (a:SearchDemoArticle)
WHERE a.title STARTS WITH 'Graph'
RETURN a.code AS code, a.title AS title;
```

```cypher
// Hậu tố của toàn bộ chuỗi title
MATCH (a:SearchDemoArticle)
WHERE a.title ENDS WITH 'Guide'
RETURN a.code AS code, a.title AS title;
```

```cypher
// Chuỗi con liên tiếp, kể cả khi không nằm ở đầu một từ
MATCH (a:SearchDemoArticle)
WHERE a.title CONTAINS 'Graph'
RETURN a.code AS code, a.title AS title
ORDER BY code;
```

Truy vấn cuối trả **G-101** và **G-102**; câu `ENDS WITH 'Guide'` trả **J-201**. Các kết quả xuất phát từ **ý nghĩa của điều kiện `WHERE`**, không thay đổi chỉ vì có hoặc không có index. Index chỉ cung cấp đường truy cập để có thể thực thi nhanh hơn.

### 3.1. Vì sao `CONTAINS` khác việc tìm một từ?

`CONTAINS` hỏi liệu **một chuỗi ký tự liên tiếp** có xuất hiện trong một giá trị property hay không. Nó không hiểu từ ghép, dấu câu, từ dừng hay độ liên quan.

```cypher
MATCH (a:SearchDemoArticle)
WHERE a.title CONTAINS 'graph'
RETURN a.code;
```

Ví dụ trên không trả G-101 hoặc G-102 vì tiêu đề chứa `Graph` viết hoa, không chứa chuỗi con `graph` viết thường. Neo4j không tự biến phép so khớp này thành tìm kiếm không phân biệt hoa/thường.

Nếu dùng `toLower(a.title) CONTAINS 'graph'`, ý nghĩa so khớp thay đổi nhưng phép biến đổi đặt trực tiếp lên property có thể khiến planner không dùng text index tương ứng. Với nhu cầu đó, cân nhắc lưu **một thuộc tính chuẩn hóa** riêng và tạo index trên thuộc tính đó, hoặc chọn full-text search nếu mục đích là tìm theo token.

### 3.2. Tại sao text index thích hợp cho chuỗi con?

Ở các phiên bản Neo4j hiện hành, text index dùng kỹ thuật **trigram**: phân rã chuỗi thành những đoạn chồng lấn gồm ba Unicode code point. Chẳng hạn `developer` tạo các đoạn như `dev`, `eve`, `vel`, ... Nhờ đó, planner có thể khai thác text index cho `CONTAINS` hoặc `ENDS WITH`, là các phép tìm thường kém thuận lợi với range index.

Text index hỗ trợ `STARTS WITH`, `ENDS WITH`, `CONTAINS` và, khi kiểu dữ liệu cho phép xác định, cả `=`, `IN`. Tuy nhiên, **hỗ trợ không có nghĩa là luôn được chọn**. Nếu tồn tại cả range index và text index trên cùng thuộc tính `STRING`, planner thường ưu tiên text index cho `CONTAINS`/`ENDS WITH`, còn range index cho các bộ lọc khác. Kết quả chọn phụ thuộc thống kê, biểu thức và môi trường thực tế.

### 3.3. Không dùng text index để tạo relevance ranking

Hai kết quả có `title CONTAINS 'Graph'` đều thỏa một điều kiện Boolean. Không có `score` biểu thị mức độ liên quan đến `Graph`. Muốn xếp theo độ mới, tên hay mã bài, phải chỉ định tiêu chí rõ ràng, ví dụ:

```cypher
MATCH (a:SearchDemoArticle)
WHERE a.title CONTAINS 'Graph'
RETURN a.code AS code, a.title AS title
ORDER BY code ASC;
```

Ở đây `ORDER BY code` là sắp xếp theo mã, không phải mức độ khớp nội dung.

## 4. Full-text index: phân tích token, tìm từ và xếp hạng

Tạo full-text index trên **hai property** `title` và `body` của label `SearchDemoArticle`:

```cypher
CREATE FULLTEXT INDEX search_demo_article_fulltext IF NOT EXISTS
FOR (a:SearchDemoArticle)
ON EACH [a.title, a.body];
```

Full-text index sử dụng Apache Lucene. Analyzer xử lý nội dung để thu được các token có thể tìm kiếm. Với analyzer mặc định `standard-no-stop-words`, các từ thường được chuẩn hóa về chữ thường, nên truy vấn `graph` có thể khớp `Graph`. Bản chất thao tác là **tìm từ ngữ đã phân tích**, không phải tìm chuỗi con liên tiếp theo `CONTAINS`.

Full-text index có thể tìm trong **bất kỳ property nào** đã được liệt kê. Nó không đòi mỗi node phải có đủ mọi property trong danh sách: một node có label phù hợp và **ít nhất một** property được index với kiểu dữ liệu được hỗ trợ vẫn có thể được đưa vào chỉ mục.

### 4.1. Dùng procedure với Neo4j 5 / Cypher 5

```cypher
CALL db.index.fulltext.queryNodes(
  'search_demo_article_fulltext', 'graph'
)
YIELD node, score
RETURN node.code AS code,
       node.title AS title,
       score
ORDER BY score DESC;
```

Kết quả dự kiến gồm **G-101, G-102, N-301** vì mỗi bài có token `graph` ở tiêu đề hoặc body. `score` là mức liên quan do Lucene tính; không nên ghi cứng con số vì còn phụ thuộc dữ liệu, cấu hình analyzer, phiên bản và thống kê index. Thứ tự các bài có thể thay đổi khi nội dung đổi.

Procedure trả `node` và `score`; khi cần truy vấn quan hệ của node tìm được, có thể tiếp tục `MATCH` hoặc `OPTIONAL MATCH` trong cùng Cypher:

```cypher
CALL db.index.fulltext.queryNodes(
  'search_demo_article_fulltext', 'graph'
)
YIELD node AS article, score
WITH article, score
ORDER BY score DESC
LIMIT 5
OPTIONAL MATCH (article)-[:SEARCH_DEMO_RELATED]->(related:SearchDemoArticle)
RETURN article.code AS code,
       article.title AS title,
       score,
       collect(related.code) AS relatedCodes
ORDER BY score DESC;
```

Việc nối sang property graph sau tìm kiếm là lợi thế thực tế của Neo4j. Lưu ý mỗi `MATCH` có thể nhân số hàng nếu node có nhiều relationship; dùng `collect()` hoặc `DISTINCT` khi cần một hàng cho mỗi tài liệu.

### 4.2. Dùng `SEARCH` với Cypher 25 mới

Từ **Neo4j 2026.09**, Cypher 25 hỗ trợ `SEARCH` cho full-text index. Với Neo4j hiện hành và phiên Cypher 25, đây là lựa chọn được khuyến nghị:

```cypher
MATCH (article)
SEARCH article IN (
  FULLTEXT INDEX search_demo_article_fulltext
  FOR 'graph'
  LIMIT 10
)
SCORE AS score
RETURN article.code AS code, article.title AS title, score
ORDER BY score DESC;
```

**Giới hạn phiên bản cần nhớ:** `SEARCH` ở ví dụ này yêu cầu **Cypher 25 và Neo4j 2026.09 trở lên**. `db.index.fulltext.queryNodes()` vẫn là lựa chọn tương thích cho Neo4j 5 hoặc truy vấn Cypher 5; procedure này đã được đánh dấu **deprecated trong Cypher 25 từ Neo4j 2026.10**. Vì vậy, khi bảo trì ứng dụng Java/Spring Data, cần kiểm tra phiên bản server **và** phiên bản Cypher đang chạy trước khi đổi cú pháp.

Không nên kỳ vọng một câu `MATCH ... WHERE article.body CONTAINS 'graph'` tự sử dụng full-text index. Đó là điều kiện chuỗi thông thường; **full-text search phải được gọi tường minh** qua `SEARCH` hoặc procedure phù hợp.

## 5. Cùng từ khóa, hai phép tìm mang ý nghĩa khác nhau

So sánh ba truy vấn có vẻ giống nhau:

```cypher
// A. Chuỗi con chính xác trong title, phân biệt hoa/thường
MATCH (a:SearchDemoArticle)
WHERE a.title CONTAINS 'Graph'
RETURN a.code AS code;
```

```cypher
// B. Chuỗi con trong title, viết thường: không khớp 'Graph'
MATCH (a:SearchDemoArticle)
WHERE a.title CONTAINS 'graph'
RETURN a.code AS code;
```

```cypher
// C. Token 'graph' trong title HOẶC body, qua full-text
CALL db.index.fulltext.queryNodes(
  'search_demo_article_fulltext', 'graph'
)
YIELD node, score
RETURN node.code AS code, score
ORDER BY score DESC;
```

| Truy vấn | Kết quả dự kiến | Lý do |
| --- | --- | --- |
| A: `title CONTAINS 'Graph'` | G-101, G-102 | Hai tiêu đề chứa chuỗi con `Graph` viết hoa |
| B: `title CONTAINS 'graph'` | Không có hàng | Không tiêu đề nào chứa đúng chuỗi viết thường |
| C: full-text `graph` | G-101, G-102, N-301 | Analyzer mặc định nhận token `graph` ở `title` hoặc `body` |

Nội dung này dẫn tới hai nguyên tắc:

1. **Index không “biến” ngữ nghĩa của một điều kiện Cypher.** `TEXT INDEX` làm điều kiện `CONTAINS` có cơ hội nhanh hơn, nhưng không làm nó thành tìm từ hay tìm gần đúng.
2. **Full-text search là phép tìm khác.** Nó dùng analyzer, truy vấn Lucene và tính điểm; kết quả có thể khác cả về phạm vi khớp lẫn thứ tự.

## 6. Từ, cụm từ, điều kiện Boolean và score trong full-text

Ở full-text search, chuỗi đầu vào là **biểu thức tìm kiếm Lucene**. Các ví dụ sau dùng procedure để chạy được trên Neo4j 5; với Cypher 25 mới có thể đặt biểu thức tương đương ở phần `FOR` của `SEARCH`.

### 6.1. Tìm một token

```cypher
CALL db.index.fulltext.queryNodes(
  'search_demo_article_fulltext', 'cypher'
)
YIELD node, score
RETURN node.code AS code, score
ORDER BY score DESC;
```

Trả các bài chứa token `cypher` ở title hoặc body. Mục tiêu là tìm nội dung có từ này, không phải so toàn bộ property bằng `'cypher'`.

### 6.2. Tìm cụm từ theo thứ tự

Bọc cụm từ trong **dấu ngoặc kép của cú pháp Lucene**, rồi đặt toàn bộ biểu thức vào chuỗi Cypher:

```cypher
CALL db.index.fulltext.queryNodes(
  'search_demo_article_fulltext', '"graph modeling"'
)
YIELD node, score
RETURN node.code AS code, node.title AS title, score;
```

Với dữ liệu mẫu, G-101 khớp vì tiêu đề chứa hai token kế tiếp nhau `Graph Modeling`. Tìm cụm từ **không** đồng nghĩa với so toàn bộ `title` bằng `'graph modeling'`; chuỗi gốc có thể chứa các từ khác.

### 6.3. Điều kiện Boolean

```cypher
CALL db.index.fulltext.queryNodes(
  'search_demo_article_fulltext', 'graph AND cypher'
)
YIELD node, score
RETURN node.code AS code, score
ORDER BY score DESC;
```

`AND` yêu cầu các token cùng khớp theo cách hiểu của Lucene trên nội dung được index. Ngoài ra có `OR`, `NOT`, toán tử bắt buộc `+` và loại trừ `-`. Không nên áp dụng cú pháp này như thể đó là `WHERE` của Cypher.

Nếu đầu vào đến từ người dùng, cần phân biệt **từ khóa văn bản thuần** và **cú pháp truy vấn Lucene**. Dù truyền bằng parameter để tránh ghép chuỗi Cypher, các ký tự đặc biệt của Lucene vẫn có ý nghĩa tìm kiếm. Ứng dụng phải quyết định có cho phép người dùng nhập toán tử hay cần escape/chuẩn hóa đầu vào để chỉ tìm từ khóa thuần.

### 6.4. Hiểu đúng relevance score

`score` giúp sắp thứ tự các bản ghi **trong cùng một truy vấn full-text**. Điểm này không phải tỷ lệ phần trăm đúng, không phải độ tin cậy xác suất và không nên dùng trực tiếp để so với điểm vector search hoặc những hệ thống scoring khác.

Một hệ thống tìm kiếm thường áp dụng: lấy số lượng kết quả hợp lý, sắp theo `score`, sau đó lọc quyền truy cập, loại nội dung không phù hợp và hiển thị tiêu đề/đoạn tóm tắt. Điểm liên quan không tự thay thế các quy tắc nghiệp vụ.

## 7. Analyzer, tiếng Việt và chuẩn hóa văn bản

Khác với text index, full-text index cho phép chọn **analyzer**. Analyzer quyết định cách tách token, xử lý chữ hoa/thường và có thể loại stop words hoặc áp dụng quy tắc ngôn ngữ. Chọn không đúng analyzer có thể gây khác biệt lớn giữa những gì người dùng nhập và các token thực sự được index.

Xem các analyzer có sẵn trên server:

```cypher
CALL db.index.fulltext.listAvailableAnalyzers()
YIELD analyzer, description
RETURN analyzer, description
ORDER BY analyzer;
```

Ví dụ cấu hình analyzer khi tạo một full-text index khác:

```cypher
CREATE FULLTEXT INDEX search_demo_article_english IF NOT EXISTS
FOR (a:SearchDemoArticle)
ON EACH [a.title, a.body]
OPTIONS {
  indexConfig: {
    `fulltext.analyzer`: 'english'
  }
};
```

Analyzer `english` có thể xử lý stop words/stemming theo tiếng Anh; không nên mặc định dùng nó cho tài liệu tiếng Việt. Đối với nội dung như `hệ thống đồ thị`, `mô hình hóa dữ liệu`, `truy vấn đường đi`, cần kiểm tra trực tiếp:

- Dấu tiếng Việt có được giữ hay chuyển đổi theo đúng yêu cầu không?
- Từ ghép nhiều âm tiết có bị tách thành các token gây khớp rộng hoặc bỏ sót không?
- Người dùng tìm không dấu có cần khớp dữ liệu có dấu không?
- Từ viết tắt như `SDN`, `Cypher`, `Neo4j` cần tìm chính xác đến mức nào?

**Không nên khẳng định analyzer mặc định tự hiểu tiếng Việt hoặc tự bỏ dấu.** Có thể cần analyzer tùy chỉnh, thuộc tính tìm kiếm đã chuẩn hóa, hoặc kết hợp bộ lọc chính xác với full-text. Phải thống nhất chuẩn hóa ở cả lúc ghi dữ liệu và lúc tạo truy vấn.

Để tìm **một mã định danh** hoặc token nghiệp vụ không được phép mơ hồ, nên dùng lookup chính xác có constraint/index thích hợp. Full-text analyzer có thể thay đổi cách so khớp và không nên dùng thay cho uniqueness constraint.

## 8. Số label/type, số property và relationship index

Text index giới hạn ở một label/type và một property `STRING` cho mỗi index. Full-text index có thể bao phủ nhiều property và nhiều label/type:

```cypher
// Ví dụ thay thế trên mô hình có cả Article và Guide
CREATE FULLTEXT INDEX docs_all_fulltext IF NOT EXISTS
FOR (d:SearchDemoArticle|SearchDemoGuide)
ON EACH [d.title, d.body, d.summary];
```

Đây là ví dụ lược đồ mở rộng; dữ liệu mẫu mục 2 mới chỉ có `SearchDemoArticle`. Với full-text index như trên, một node chỉ cần thuộc **ít nhất một label** chỉ định và có **ít nhất một property** hợp lệ được index để có thể được tìm thấy. Khác với *composite range index* vốn thường yêu cầu có đủ các property thành phần, full-text ở đây gộp nguồn văn bản để tìm kiếm.

Cả hai loại đều hỗ trợ chỉ mục cho **relationship property**. Ví dụ tạo text index trên `note`:

```cypher
CREATE TEXT INDEX search_demo_note_text IF NOT EXISTS
FOR ()-[r:SEARCH_DEMO_RELATED]-()
ON (r.note);
```

```cypher
MATCH ()-[r:SEARCH_DEMO_RELATED]->()
WHERE r.note CONTAINS 'Graph'
RETURN r.note AS note;
```

Nếu cần tìm theo token ở các ghi chú quan hệ và lấy `score`, sử dụng full-text index trên relationship:

```cypher
CREATE FULLTEXT INDEX search_demo_relation_fulltext IF NOT EXISTS
FOR ()-[r:SEARCH_DEMO_RELATED]-()
ON EACH [r.note];
```

```cypher
// Neo4j 5 / Cypher 5
CALL db.index.fulltext.queryRelationships(
  'search_demo_relation_fulltext', 'graph'
)
YIELD relationship, score
RETURN relationship.note AS note, score
ORDER BY score DESC;
```

Bài toán có thể chỉ cần tìm đoạn mô tả nằm trên relationship, chưa cần truy vấn toàn bộ đường đi. Nếu cần mở rộng đồ thị, lấy các node đầu mút bằng `startNode(relationship)` và `endNode(relationship)` hoặc nối mẫu có biến relationship tương ứng.

## 9. Theo dõi trạng thái index và xem execution plan

Sau `CREATE INDEX`, Neo4j cần thời gian **POPULATING** để xây dựng chỉ mục từ dữ liệu hiện có. Chỉ dùng khi index đã `ONLINE`.

```cypher
SHOW INDEXES
YIELD name, type, state, populationPercent, labelsOrTypes, properties
RETURN name, type, state, populationPercent, labelsOrTypes, properties
ORDER BY name;
```

Muốn lọc riêng loại index:

```cypher
SHOW TEXT INDEXES;
```

```cypher
SHOW FULLTEXT INDEXES;
```

Khi tìm hiểu lý do truy vấn Cypher có hay không dùng text index:

```cypher
EXPLAIN
MATCH (a:SearchDemoArticle)
WHERE a.title CONTAINS 'Graph'
RETURN a.code, a.title;
```

`EXPLAIN` cho kế hoạch ước tính mà không chạy truy vấn. `PROFILE` thực thi truy vấn và cung cấp chỉ số Rows/DB Hits thực tế:

```cypher
PROFILE
MATCH (a:SearchDemoArticle)
WHERE a.title CONTAINS 'Graph'
RETURN a.code, a.title;
```

Ở kế hoạch thực tế, kiểm tra operator truy cập index, tên index được dùng, số Rows và chi phí. Với bốn node mẫu, planner có thể chọn phương án khác dự đoán; không nên lấy dữ liệu quá nhỏ để khẳng định index sẽ luôn tăng tốc. Khi đo hiệu quả cần so sánh trên khối lượng và phân bố dữ liệu đại diện.

**Trường hợp có cả RANGE và TEXT:** cùng một property `title` có thể có cả hai loại index, nhưng tạo thêm index tăng chi phí lưu trữ và cập nhật. Không nên nhân đôi chỉ mục chỉ vì tên gọi khác; hãy nhìn vào các câu truy vấn thực tế (`CONTAINS`, `ENDS WITH`, equality, prefix, sort) và kế hoạch của planner.

## 10. Tính nhất quán khi ghi và giới hạn vận hành

Full-text index cập nhật theo thay đổi node/relationship. Với cấu hình thông thường, quá trình cập nhật chỉ mục gắn với giao dịch. Có thể **tùy chọn eventual consistency** cho full-text index, đưa tác vụ cập nhật index sang luồng nền:

```cypher
CREATE FULLTEXT INDEX search_demo_eventual_fulltext IF NOT EXISTS
FOR (a:SearchDemoArticle)
ON EACH [a.title, a.body]
OPTIONS {
  indexConfig: {
    `fulltext.eventually_consistent`: true
  }
};
```

Đổi lại, một bản ghi vừa commit có thể chưa xuất hiện ngay trong kết quả full-text. Nếu luồng ứng dụng cần **ghi xong tìm thấy ngay**, cần cân nhắc kỹ cấu hình này. Neo4j cung cấp procedure để đợi các cập nhật full-text eventual được áp dụng:

```cypher
CALL db.index.fulltext.awaitEventuallyConsistentIndexRefresh();
```

Đừng đồng nhất “index eventual” với việc giao dịch dữ liệu đồ thị chưa commit: đây là vấn đề **thời điểm đồng bộ nội dung index tìm kiếm**, không phải thay thế cơ chế transaction của Neo4j.

Text index và full-text index đều có chi phí lưu trữ và cập nhật khi property thay đổi. Full-text còn có chi phí analyzer, index hóa nhiều token và có thể sử dụng thêm tài nguyên khi tìm/sắp theo `score`. Cần đo hiệu năng bằng dữ liệu thực, giám sát dung lượng, lưu lượng ghi và độ trễ tìm kiếm trước khi đưa vào production.

## 11. Áp dụng trong Java Driver và Spring Data Neo4j

Phần chọn index thuộc về **mục đích truy vấn**, không phụ thuộc framework gọi Cypher:

- **Tra cứu khóa chính xác hoặc lọc chuỗi con:** dùng Cypher `MATCH ... WHERE`, truyền tham số `$term`; planner quyết định index phù hợp. Các trường `code`, ID người dùng hoặc mã đơn hàng thường phù hợp với range index/constraint hơn.
- **Tìm bài viết theo nội dung:** dùng `SEARCH` ở môi trường hỗ trợ Cypher 25 hoặc procedure full-text trên Neo4j 5/Cypher 5; truyền từ khóa bằng tham số, lấy thêm `score` và ánh xạ kết quả trả về.
- **Kết hợp tìm nội dung với quan hệ:** nhận node khớp từ full-text rồi traversing relationships và gom nhóm trước khi trả DTO nếu một tài liệu có nhiều đường đi.

Ví dụ truy vấn dùng tham số trong Neo4j Java Driver (phần Cypher):

```cypher
MATCH (a:SearchDemoArticle)
WHERE a.title CONTAINS $term
RETURN a.code AS code, a.title AS title
ORDER BY code;
```

```cypher
CALL db.index.fulltext.queryNodes(
  'search_demo_article_fulltext', $query
)
YIELD node, score
RETURN node.code AS code, node.title AS title, score
ORDER BY score DESC
LIMIT $limit;
```

Ở lớp Java, bind `term` hoặc `query` bằng parameter của Driver; với Spring Data Neo4j có thể dùng `@Query` và ánh xạ projection `code`, `title`, `score`. Truyền tham số giúp tránh ghép chuỗi thành Cypher tùy tiện, **nhưng** `$query` vẫn được full-text parser hiểu là truy vấn Lucene; cần kiểm soát đặc biệt nếu ứng dụng cho phép người dùng nhập ký tự như `:`, `*`, `"`, `AND`, `OR`.

Với API tìm kiếm, thiết kế hai loại tham số rõ ràng thường hữu ích: `exactText` cho so khớp chuỗi đúng nghĩa và `searchQuery` cho tìm nội dung. Trộn hai mục đích vào một cờ `contains` có thể gây khó giải thích kết quả cho người dùng.

## 12. Cách quyết định trong một dự án Neo4j

| Câu hỏi nghiệp vụ | Khuyến nghị | Vì sao |
| --- | --- | --- |
| Tìm sản phẩm có mã chính xác `P-004` | Range index hoặc uniqueness constraint phù hợp | Khóa định danh cần so chính xác và đảm bảo tính duy nhất |
| Tìm tài liệu có tiêu đề chứa chuỗi `Graph` | Text index trên `title` | Phù hợp toán tử `CONTAINS` |
| Tìm tài liệu có hậu tố tiêu đề `Guide` | Text index trên `title` | `ENDS WITH` là trường hợp text index được tối ưu |
| Tìm tất cả bài bàn về `graph` ở title/body, xếp theo độ liên quan | Full-text index trên `title`, `body` | Tokenization, tìm nhiều thuộc tính, relevance `score` |
| Tìm cụm từ `graph modeling` | Full-text index + truy vấn phrase | So token theo thứ tự, không yêu cầu chuỗi property bằng toàn bộ cụm |
| Tìm theo ngữ nghĩa “đoạn văn gần nghĩa, dùng từ khác” | Xem xét vector search/thiết kế hybrid riêng | Full-text là tìm kiếm **từ vựng**, không tự hiểu embedding/ý nghĩa như vector search |
| Cần bản ghi mới xuất hiện ngay sau khi lưu | Tránh bật eventual consistency của full-text nếu không có cơ chế xử lý | Index nền có thể cập nhật chậm so với transaction |

### Tự kiểm tra

1. Vì sao `CONTAINS 'graph'` trên `title` có thể trả rỗng, còn full-text query `graph` lại tìm thấy bài chứa `Graph`?
2. Vì sao không thể chỉ tạo một text index trên `title` rồi mong nó tự tìm cả `body` và trả `score`?
3. Nếu cần tìm mã tài khoản `USR-0001` tuyệt đối chính xác, nên chọn index/constraint nào?
4. Sau khi tạo full-text index, vì sao `SHOW FULLTEXT INDEXES` có thể cho biết `POPULATING` thay vì `ONLINE`?
5. Vì sao phải xem lại cách tách từ và dấu khi triển khai tìm kiếm tiếng Việt?
6. Nếu hệ thống dùng Cypher 5, vì sao ví dụ `SEARCH` mới có thể không chạy được?

**Đáp án ngắn:** (1) `CONTAINS` so chuỗi con và phân biệt hoa/thường; full-text analyzer tìm token, thường chuẩn hóa chữ thường. (2) Text index chỉ hỗ trợ lọc điều kiện Cypher cho một property; không tạo relevance. (3) Range index/uniqueness constraint phù hợp khóa chính xác. (4) Index đang xây dựng từ dữ liệu hiện có. (5) Analyzer mặc định không đảm bảo các quy tắc tìm kiếm tiếng Việt của sản phẩm. (6) Full-text `SEARCH` cần Cypher 25 và Neo4j từ 2026.09; Cypher 5 dùng procedure.

## 13. Tài liệu tham khảo

- [Neo4j Cypher Manual — Create performance indexes](https://neo4j.com/docs/cypher-manual/current/indexes/performance-indexes/create-indexes/): cú pháp text index, phạm vi và các predicate được hỗ trợ.
- [Neo4j Cypher Manual — Full-text indexes](https://neo4j.com/docs/cypher-manual/current/indexes/search-indexes/full-text-indexes/): analyzer, Lucene query, `SEARCH`/procedure, `score` và eventual consistency.
- [Neo4j Cypher Manual — The impact of indexes on query performance](https://neo4j.com/docs/cypher-manual/current/indexes/performance-indexes/using-indexes/): khi nào planner chọn text hay range index, cách đọc kế hoạch.

**Ghi nhớ:** **text index trả lời “property có thỏa điều kiện chuỗi này không?”**, còn **full-text index trả lời “nội dung nào có những token phù hợp nhất với biểu thức tìm kiếm?”**. Chọn đúng loại chỉ mục quyết định cả ý nghĩa kết quả, cách viết Cypher và chi phí vận hành hệ thống đồ thị.
