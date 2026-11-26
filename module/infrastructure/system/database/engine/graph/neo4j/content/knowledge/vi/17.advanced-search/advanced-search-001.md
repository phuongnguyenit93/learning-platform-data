# Full-text index cho tìm kiếm văn bản trên nút và quan hệ

Trong cơ sở dữ liệu đồ thị **Neo4j**, các node lưu thực thể và các relationship lưu mối liên kết. Thuộc tính của cả hai loại thực thể có thể chứa văn bản: tiêu đề bài viết, mô tả sản phẩm, nội dung đánh giá, ghi chú về một giao dịch hoặc nhận xét trên một quan hệ. Khi người dùng muốn tìm “bài viết nói về Cypher” hoặc “đánh giá nhắc đến giao hàng”, việc so sánh chính xác bằng `=` thường không đáp ứng được nhu cầu.

**Full-text index** hỗ trợ tìm theo các *từ* hoặc *cụm từ* trong văn bản đã được phân tích thành token, trả về thực thể phù hợp cùng **điểm liên quan** (`score`). Neo4j xây dựng full-text index dựa trên công nghệ tìm kiếm văn bản Lucene. Đây là một công cụ thuộc chương **Tìm kiếm nâng cao** của module **DATABASE_ENGINE_GRAPH_NEO4J**, kết hợp với mô hình property graph, Cypher, index/constraint, Java Driver, Spring Data Neo4j và vận hành hệ thống đồ thị.

Sau bài này, bạn có thể tạo full-text index cho **node lẫn relationship**, truy vấn an toàn bằng Cypher procedure, hiểu vai trò của analyzer và Lucene query, đánh giá khi nào nên dùng full-text index thay cho các loại index khác, cũng như xử lý vấn đề hiệu năng và tính nhất quán.

## 1. Full-text index giải quyết bài toán nào?

Giả sử trong dữ liệu có một node:

```text
(:Article {
  articleId: 'A-001',
  title: 'Giới thiệu truy vấn Cypher',
  body: 'Cypher giúp tìm quan hệ và đường đi trong đồ thị Neo4j.'
})
```

Người dùng có thể nhập `cypher`, `"đường đi"` hoặc một biểu thức tìm kiếm gồm nhiều từ. Họ mong đợi tìm thấy tài liệu dù chuỗi nhập không bằng nguyên vẹn `title` hay `body`.

Các mục tiêu khác nhau cần công cụ khác nhau:

| Yêu cầu | Công cụ thường phù hợp | Lý do |
| --- | --- | --- |
| Tìm bài có `articleId = 'A-001'` | Index thông thường, uniqueness constraint | So khớp định danh chính xác |
| Tìm tiêu đề bắt đầu bằng `'Cypher'` | `TEXT INDEX` hoặc index phù hợp với predicate | Tìm trên chuỗi thuộc tính |
| Tìm bài chứa từ `'Cypher'` theo token | **Full-text index** | Phân tích văn bản và tính độ liên quan |
| Tìm cụm từ theo cú pháp tìm kiếm | **Full-text index** | Hỗ trợ cú pháp truy vấn văn bản Lucene |
| Tìm mọi bài do tác giả A viết trong 2 bước quan hệ | Cypher `MATCH` và các index hỗ trợ định vị | Ràng buộc cấu trúc đồ thị |
| Tìm đánh giá trên quan hệ `:REVIEWED` nhắc tới “giao hàng” | **Full-text index trên relationship** | Trả chính quan hệ mang thuộc tính văn bản |

**Điểm phân biệt:** full-text index không thay thế khả năng duyệt đồ thị của Cypher. Một quy trình thường tìm các node/relationship phù hợp về mặt văn bản **trước**, rồi dùng `MATCH` để kiểm tra quan hệ, trạng thái, chủ sở hữu hoặc những điều kiện nghiệp vụ khác.

## 2. Cách full-text index hoạt động

Khi tạo chỉ mục cho một hoặc nhiều thuộc tính văn bản, Neo4j dùng **analyzer** để chuyển nội dung thành các token phục vụ tra cứu. Tùy analyzer, các bước có thể bao gồm tách từ, chuyển chữ thường, bỏ stop-word hoặc chuẩn hóa hình thái từ.

```text
Node/relationship có thuộc tính văn bản
                  |
                  v
        Analyzer phân tích text
                  |
                  v
      Token -> danh sách thực thể
                  |
                  v
      Full-text inverted index
                  ^
                  |
       Truy vấn văn bản Lucene
                  |
                  v
      Thực thể phù hợp + score
```

Ví dụ, một analyzer có thể biến `'Cypher và Neo4j'` thành các token gần với `cypher` và `neo4j`. Nhưng **không nên giả định mọi analyzer đều xử lý dấu tiếng Việt, cách ghép từ hoặc stop-word giống nhau**. Truy vấn thử trên dữ liệu và analyzer đang dùng mới cho biết kết quả thực tế.

Các đặc điểm chính:

- Chỉ mục full-text **không bắt buộc tất cả node hoặc relationship phải có cùng tập thuộc tính**; thực thể có ít nhất một thuộc tính văn bản được lập chỉ mục có thể tham gia.
- Full-text index có thể khai báo **nhiều label của node hoặc nhiều loại relationship**, cũng như nhiều thuộc tính văn bản.
- Chỉ những giá trị có kiểu phù hợp để lập chỉ mục văn bản, ví dụ chuỗi hoặc danh sách chuỗi, mới đóng góp vào full-text index. Giá trị số không tự biến thành chuỗi tìm kiếm.
- Điểm `score` biểu thị độ liên quan theo cơ chế tìm kiếm. Nó **không phải tỷ lệ chính xác, xác suất, độ tin cậy nghiệp vụ hay mức độ gần nhau trong đồ thị**.
- Truy vấn full-text được gọi **tường minh** bằng procedure chuyên dụng; không nên giả định rằng câu `WHERE a.title CONTAINS ...` sẽ tự chọn full-text index.

## 3. Chuẩn bị dữ liệu minh họa

Các ví dụ sau dành cho Neo4j 5 và các phiên bản có cú pháp tương ứng. Tên procedure, tùy chọn hoặc quyền thực thi có thể khác tùy phiên bản server; cần đối chiếu môi trường đang chạy trước khi đưa vào production.

Trong database thực hành, tạo một số bài viết và hai đánh giá sản phẩm:

```cypher
CREATE CONSTRAINT article_id_unique IF NOT EXISTS
FOR (a:Article)
REQUIRE a.articleId IS UNIQUE;

CREATE CONSTRAINT user_id_unique IF NOT EXISTS
FOR (u:User)
REQUIRE u.userId IS UNIQUE;

CREATE CONSTRAINT product_sku_unique IF NOT EXISTS
FOR (p:Product)
REQUIRE p.sku IS UNIQUE;
```

```cypher
MERGE (a:Article {articleId: 'A-001'})
SET a.title = 'Giới thiệu truy vấn Cypher',
    a.body = 'Cypher giúp tìm quan hệ và đường đi trong đồ thị Neo4j.',
    a.status = 'PUBLISHED',
    a.language = 'vi';

MERGE (b:Article {articleId: 'A-002'})
SET b.title = 'Tối ưu truy vấn Neo4j',
    b.body = 'Đọc execution plan để tối ưu MATCH, index và truy vấn đường đi.',
    b.status = 'PUBLISHED',
    b.language = 'vi';

MERGE (c:Article {articleId: 'A-003'})
SET c.title = 'Bản nháp giới thiệu hệ thống đồ thị',
    c.body = 'Tìm kiếm Cypher trong dữ liệu liên kết.',
    c.status = 'DRAFT',
    c.language = 'vi';

MERGE (u:User {userId: 'U-001'})
MERGE (p:Product {sku: 'P-001'})
MERGE (u)-[r:REVIEWED {reviewId: 'R-001'}]->(p)
SET r.title = 'Giao hàng nhanh',
    r.comment = 'Giao hàng đúng hẹn, đóng gói cẩn thận.',
    r.rating = 5;

MERGE (v:User {userId: 'U-002'})
MERGE (u2:Product {sku: 'P-002'})
MERGE (v)-[r2:REVIEWED {reviewId: 'R-002'}]->(u2)
SET r2.title = 'Chất lượng ổn',
    r2.comment = 'Sản phẩm tốt nhưng giao hàng khá chậm.',
    r2.rating = 3;
```

Các câu `MERGE` ở đây chỉ giúp minh họa một dữ liệu có thể chạy lại với khóa định danh đã nêu. Trong một ứng dụng thật, việc bảo đảm duy nhất cho đánh giá `reviewId` thường cần mô hình dữ liệu và ràng buộc riêng phù hợp với relationship.

## 4. Tạo full-text index trên node

### 4.1. Chỉ mục cho một label và nhiều thuộc tính

Để tìm theo cả tiêu đề lẫn nội dung bài viết:

```cypher
CREATE FULLTEXT INDEX articleFulltext IF NOT EXISTS
FOR (a:Article)
ON EACH [a.title, a.body];
```

Cú pháp gồm:

- `articleFulltext`: **tên index**, được dùng khi gọi procedure truy vấn.
- `(a:Article)`: chọn các node có label `:Article`.
- `ON EACH [a.title, a.body]`: lập chỉ mục trên hai thuộc tính văn bản.
- `IF NOT EXISTS`: tránh lỗi nếu index tương ứng đã tồn tại; câu lệnh này **không có nghĩa** index cũ sẽ tự được đổi cấu hình nếu khác mong muốn.

Với index nhiều thuộc tính, thực thể vẫn có thể xuất hiện trong kết quả nếu chỉ có `title` hoặc chỉ có `body` là văn bản được index. Không cần cả hai thuộc tính cùng tồn tại.

### 4.2. Chỉ mục cho nhiều label

Nếu hệ thống có cả bài viết và mục hỏi đáp, và hai loại thực thể sử dụng cùng trường văn bản:

```cypher
CREATE FULLTEXT INDEX knowledgeFulltext IF NOT EXISTS
FOR (n:Article|FAQ)
ON EACH [n.title, n.body];
```

Đây là **một** full-text index trên tập node có label `:Article` **hoặc** `:FAQ`, không phải điều kiện bắt buộc mỗi node có cả hai label. Sau khi tìm kiếm, nên kiểm tra label hoặc lọc nghiệp vụ nếu giao diện chỉ hiển thị một loại thực thể.

Nếu hai loại đối tượng có cấu trúc văn bản, tần suất cập nhật hoặc quy tắc tìm kiếm khác nhau, cân nhắc tách index để dễ điều chỉnh analyzer và phạm vi tìm kiếm.

## 5. Tạo full-text index trên relationship

Relationship trong Neo4j có thuộc tính như node. Một đánh giá được mô hình bằng quan hệ:

```text
(:User {userId: 'U-001'})
   -[:REVIEWED {
       title: 'Giao hàng nhanh',
       comment: 'Giao hàng đúng hẹn...',
       rating: 5
     }]->
(:Product {sku: 'P-001'})
```

Tạo index:

```cypher
CREATE FULLTEXT INDEX reviewFulltext IF NOT EXISTS
FOR ()-[r:REVIEWED]-()
ON EACH [r.title, r.comment];
```

Phần `()-[r:REVIEWED]-()` xác định **loại relationship được lập chỉ mục**, không định nghĩa đường đi cụ thể. Full-text index đọc text trong thuộc tính `title`, `comment` của quan hệ; những thuộc tính như `rating` dạng số không phải nội dung tìm kiếm toàn văn.

Khi dữ liệu có nhiều relationship type cùng mang nội dung văn bản, có thể khai báo các loại được hỗ trợ theo cú pháp hợp của loại quan hệ:

```cypher
CREATE FULLTEXT INDEX feedbackFulltext IF NOT EXISTS
FOR ()-[r:REVIEWED|COMMENTED]-()
ON EACH [r.title, r.comment];
```

Ví dụ này là một thiết kế **thay thế** cho chỉ mục chỉ gồm `:REVIEWED`. Không cần tạo tất cả index trùng phạm vi trong production, vì mỗi index làm tăng nhu cầu lưu trữ và chi phí bảo trì.

## 6. Chờ index sẵn sàng và xem trạng thái

Tạo chỉ mục trên tập dữ liệu lớn có thể cần thời gian để **populate**. Để kiểm tra trạng thái:

```cypher
SHOW FULLTEXT INDEXES
YIELD name, state, populationPercent
RETURN name, state, populationPercent
ORDER BY name;
```

Một số trạng thái quan trọng là `POPULATING` (đang xây), `ONLINE` (có thể sử dụng), `FAILED` (xây index không thành công). Ở môi trường thực hành, có thể đợi chỉ mục cụ thể hoàn tất:

```cypher
CALL db.awaitIndex('articleFulltext', 300);
```

Tham số thứ hai là thời gian chờ tính bằng giây. Nếu index không chuyển sang `ONLINE`, cần kiểm tra log và trạng thái index thay vì lặp truy vấn tìm kiếm rồi kết luận “không có dữ liệu”.

Trong các phần sau giả định `articleFulltext` và `reviewFulltext` đã ở trạng thái `ONLINE`.

## 7. Truy vấn full-text trên node bằng Cypher

### 7.1. Tìm theo từ khóa

```cypher
CALL db.index.fulltext.queryNodes(
  'articleFulltext',
  'cypher'
)
YIELD node, score
RETURN node.articleId AS id,
       node.title AS title,
       score
ORDER BY score DESC;
```

Procedure `db.index.fulltext.queryNodes` trả hai giá trị chính:

- `node`: node phù hợp với truy vấn.
- `score`: điểm liên quan do bộ máy tìm kiếm tính ra.

Kết quả mẫu sẽ bao gồm những bài có token tương ứng với “cypher”. **Không nên cố định điểm score hoặc thứ tự đồng điểm** trong tài liệu nghiệp vụ: kết quả phụ thuộc nội dung, analyzer, Lucene scoring và trạng thái chỉ mục.

### 7.2. Kết hợp tìm kiếm văn bản với điều kiện nghiệp vụ

Chỉ bài đã xuất bản mới được hiển thị cho người đọc:

```cypher
CALL db.index.fulltext.queryNodes(
  'articleFulltext',
  $luceneQuery
)
YIELD node AS a, score
WHERE a.status = 'PUBLISHED'
RETURN a.articleId AS id,
       a.title AS title,
       score
ORDER BY score DESC, a.articleId ASC
LIMIT 20;
```

Ví dụ tham số `$luceneQuery = 'cypher'`. Phần lọc `a.status = 'PUBLISHED'` là **điều kiện Cypher**, được áp dụng trên các node do full-text procedure trả về. Có thể thêm điều kiện ngôn ngữ:

```cypher
CALL db.index.fulltext.queryNodes('articleFulltext', $luceneQuery)
YIELD node AS a, score
WHERE a.status = 'PUBLISHED' AND a.language = $language
RETURN a.articleId AS id, a.title AS title, score
ORDER BY score DESC, a.articleId ASC
LIMIT $limit;
```

`$language` và `$limit` là tham số được kiểm tra ở phía ứng dụng. Nếu danh mục người dùng có quyền xem khác nhau, hệ thống phải áp dụng **lọc quyền truy cập** ở tầng thích hợp, tuyệt đối không xem việc index tìm thấy node là bằng chứng người dùng được phép đọc node đó.

### 7.3. Đi tiếp trong đồ thị sau khi tìm văn bản

Ví dụ một `:Author` viết những bài xuất bản có nhắc đến Cypher:

```cypher
CALL db.index.fulltext.queryNodes('articleFulltext', $luceneQuery)
YIELD node AS a, score
MATCH (author:Author)-[:WROTE]->(a)
WHERE a.status = 'PUBLISHED'
RETURN author.name AS author,
       a.title AS article,
       score
ORDER BY score DESC
LIMIT 20;
```

Kết quả phụ thuộc việc dữ liệu có quan hệ `:WROTE` tương ứng hay không. Trong bộ dữ liệu ví dụ ban đầu chưa tạo quan hệ `:WROTE`, vì vậy truy vấn này chưa trả hàng cho tới khi bổ sung tác giả và các quan hệ đó.

Đây là lợi thế khi kết hợp Neo4j và full-text: tìm **nội dung** bằng index, sau đó phân tích **liên kết** bằng pattern Cypher.

## 8. Truy vấn full-text trên relationship

Để tìm các đánh giá có nhắc đến “giao hàng”:

```cypher
CALL db.index.fulltext.queryRelationships(
  'reviewFulltext',
  $luceneQuery
)
YIELD relationship AS r, score
RETURN r.reviewId AS reviewId,
       r.title AS title,
       r.comment AS comment,
       startNode(r).userId AS reviewerId,
       endNode(r).sku AS productSku,
       score
ORDER BY score DESC;
```

Với `$luceneQuery = '"giao hàng"'`, kết quả tùy cách analyzer tách token và diễn giải cụm từ. Ví dụ trên áp dụng khi `:REVIEWED` đi từ `:User` sang `:Product` như dữ liệu mẫu; nếu hệ thống lưu chiều ngược lại, ý nghĩa `startNode(r)` và `endNode(r)` sẽ đổi.

Có thể nối các node đầu cuối vào một mẫu Cypher để lọc thêm:

```cypher
CALL db.index.fulltext.queryRelationships(
  'reviewFulltext',
  $luceneQuery
)
YIELD relationship AS r, score
MATCH (u:User)-[r]->(p:Product)
WHERE r.rating >= $minRating
RETURN u.userId AS userId,
       p.sku AS sku,
       r.comment AS comment,
       score
ORDER BY score DESC
LIMIT 10;
```

Chỉ mục full-text ở đây chọn ứng viên dựa trên **thuộc tính văn bản của relationship**. Các điều kiện về node người đánh giá, sản phẩm và số sao vẫn là phần logic Cypher.

## 9. Cú pháp truy vấn Lucene và analyzer

Tham số tìm kiếm của các procedure full-text là **chuỗi truy vấn theo cú pháp Lucene**, không phải biểu thức `WHERE` của Cypher. Điều này quyết định cách xử lý nhiều từ, cụm từ và ký tự đặc biệt.

| Ví dụ chuỗi truy vấn | Ý tưởng tìm kiếm | Cần lưu ý |
| --- | --- | --- |
| `cypher` | Tìm token “cypher” | Tùy analyzer phân tích token |
| `"đường đi"` | Tìm cụm từ theo thứ tự | Phụ thuộc tokenization và vị trí token |
| `cypher AND neo4j` | Yêu cầu cả hai thuật ngữ | `AND` là toán tử Lucene |
| `cypher OR neo4j` | Một trong hai thuật ngữ | Có thể trả tập kết quả rộng hơn |
| `title:cypher` | Chỉ tìm trên trường `title` của index | Tên trường phải là thuộc tính đã được index |
| `neo4*` | Ví dụ truy vấn tiền tố/wildcard | Có thể tốn chi phí; không thay cho `STARTS WITH` |
| `cypher~1` | Ví dụ tìm gần đúng theo độ lệch ký tự | Không đồng nghĩa sửa mọi lỗi chính tả |
| `title:cypher^3 OR body:cypher` | Tăng trọng số của điều kiện tiêu đề | Score vẫn là điểm tương đối của Lucene |

Các chuỗi này minh họa cú pháp. Hành vi thực tế thay đổi theo analyzer, phiên bản Lucene được Neo4j tích hợp và nội dung chỉ mục.

### 9.1. Chọn analyzer

Neo4j cung cấp danh sách analyzer qua procedure:

```cypher
CALL db.index.fulltext.listAvailableAnalyzers();
```

Một lựa chọn quen thuộc là `standard-no-stop-words`, thường dùng để tách token theo quy tắc chung mà không loại bỏ stop-word. Có thể chỉ định analyzer lúc tạo index:

```cypher
CREATE FULLTEXT INDEX articleWithAnalyzer IF NOT EXISTS
FOR (a:Article)
ON EACH [a.title, a.body]
OPTIONS {
  indexConfig: {
    'fulltext.analyzer': 'standard-no-stop-words'
  }
};
```

Ví dụ này dùng tên khác để giải thích tùy chọn analyzer. Khi triển khai thật, hãy quyết định một chiến lược index phù hợp và tránh duy trì nhiều bản sao không cần thiết.

**Với nội dung tiếng Việt**, cần thử nghiệm tối thiểu những trường hợp:

- Từ có dấu và không dấu, ví dụ `'đồ thị'` và `'do thi'`.
- Từ ghép nhiều tiếng, ví dụ `'giao hàng'` và `'giao nhanh'`.
- Chữ hoa/chữ thường và cách viết viết tắt.
- Từ tiếng Việt có trộn tên riêng tiếng Anh: `Neo4j`, `Cypher`, `Graph Data Science`.
- Cụm từ nguyên vẹn, dấu câu và văn bản chứa ký tự đặc biệt.

Không phải analyzer tổng quát nào cũng tự biến tiếng Việt có dấu thành không dấu hoặc hiểu một tổ hợp nhiều tiếng là một từ đơn. Nếu nghiệp vụ yêu cầu tìm kiếm không dấu, có thể cần xử lý chuẩn hóa và thiết kế thêm thuộc tính tìm kiếm phù hợp, đồng thời lưu nguyên văn gốc để hiển thị. Việc chuẩn hóa phải được kiểm thử nhất quán giữa dữ liệu index và truy vấn.

### 9.2. Không dùng nguyên xi nội dung người dùng như biểu thức Lucene tùy ý

Một truy vấn có thể chứa các ký tự điều khiển cú pháp Lucene như `:`, `"`, `*`, `~`, `(`, `)`, `+` hoặc `-`. Nếu giao diện là **ô tìm kiếm tự do đơn giản**, ứng dụng nên xác định quy tắc thoát ký tự đặc biệt và xây dựng chuỗi truy vấn đúng nghĩa “văn bản thuần”, thay vì vô tình coi ký tự của người dùng là toán tử.

**Tham số Cypher** như `$luceneQuery` giúp tránh ghép dữ liệu người dùng trực tiếp vào văn bản câu Cypher, nhưng **không tự động biến truy vấn Lucene thành literal an toàn về cú pháp**. Đây là hai tầng cú pháp độc lập.

Nếu sản phẩm **cố ý** hỗ trợ cú pháp nâng cao `AND`, `OR`, `title:...`, hãy thông báo rõ cho người dùng, kiểm soát độ dài/truy vấn quá rộng và xử lý lỗi cú pháp khi parser không chấp nhận đầu vào.

## 10. Full-text index khác gì TEXT, RANGE và constraint?

Cùng là “index”, nhưng các loại phục vụ mục đích khác nhau:

| Loại | Truy vấn điển hình | Ngữ nghĩa |
| --- | --- | --- |
| Uniqueness constraint / index hỗ trợ | `a.articleId = $id` | Định danh chính xác, duy nhất nếu có constraint |
| Range index | `a.createdAt >= $time`, nhiều dạng so sánh | Lọc theo giá trị và phạm vi |
| Text index | `a.title CONTAINS $fragment` hoặc predicate chuỗi được hỗ trợ | Tìm theo thao tác chuỗi trên thuộc tính |
| **Full-text index** | `db.index.fulltext.queryNodes('...', $query)` | Tìm theo token/cụm từ theo analyzer, có score |

Ví dụ tạo TEXT INDEX để hỗ trợ bài toán chuỗi trên `title`:

```cypher
CREATE TEXT INDEX articleTitleText IF NOT EXISTS
FOR (a:Article)
ON (a.title);
```

Sau đó có thể viết điều kiện theo thuộc tính:

```cypher
MATCH (a:Article)
WHERE a.title CONTAINS $fragment
RETURN a.articleId AS id, a.title AS title;
```

Việc query planner có chọn được text index hay không phụ thuộc predicate, phiên bản Neo4j, đặc điểm dữ liệu và thống kê; kiểm tra bằng `EXPLAIN` hoặc `PROFILE` trong môi trường phù hợp. `TEXT INDEX` không tự tạo `score` hay xử lý toán tử Lucene.

**Không nên thay full-text index bằng cách ép** `toLower(a.body) CONTAINS toLower($term)` trên hàng triệu node rồi kỳ vọng hệ thống vẫn nhanh. Biểu thức áp dụng lên thuộc tính có thể khiến việc sử dụng index kém hiệu quả. Chọn loại index và thiết kế dữ liệu theo chính xác chức năng tìm kiếm.

## 11. Độ mới dữ liệu: đồng bộ và eventually consistent

Với cấu hình mặc định, việc cập nhật full-text index được gắn với cập nhật dữ liệu trong giao dịch. Neo4j cũng hỗ trợ chế độ **eventually consistent**: các thay đổi của index được thực hiện bất đồng bộ sau đó. Chế độ này giảm phần công việc lập chỉ mục nằm trong giao dịch ghi, nhưng có đánh đổi là **tìm kiếm có thể tạm thời chưa thấy dữ liệu mới hoặc dữ liệu vừa sửa**.

Ví dụ cấu hình để minh họa tùy chọn:

```cypher
CREATE FULLTEXT INDEX articleAsyncFulltext IF NOT EXISTS
FOR (a:Article)
ON EACH [a.title, a.body]
OPTIONS {
  indexConfig: {
    'fulltext.analyzer': 'standard-no-stop-words',
    'fulltext.eventually_consistent': true
  }
};
```

Đây là **lựa chọn cấu hình thay thế**, không phải bước bắt buộc tiếp theo của bài thực hành. Có thể kiểm tra các chỉ mục:

```cypher
SHOW FULLTEXT INDEXES
YIELD name, state, options
RETURN name, state, options
ORDER BY name;
```

Neo4j cung cấp procedure hỗ trợ chờ các cập nhật eventual-consistent đã gửi tới hàng đợi được áp dụng, hữu ích trong kiểm thử hay tác vụ cần đồng bộ hóa rõ ràng:

```cypher
CALL db.index.fulltext.awaitEventuallyConsistentIndexRefresh();
```

Không nên gọi procedure chờ này ở mọi yêu cầu tìm kiếm trực tuyến vì có thể làm tăng độ trễ. Thay vào đó, xác định yêu cầu về độ mới dữ liệu: ví dụ “người vừa đăng bài phải lập tức thấy bài” hay “chấp nhận cập nhật kết quả tìm kiếm sau một khoảng ngắn”.

Lưu ý thêm: transaction chưa commit không nên được coi là nguồn dữ liệu đã sẵn sàng cho một truy vấn tìm kiếm độc lập. Khi kiểm thử, commit các thay đổi rồi quan sát thời điểm index phản ánh dữ liệu.

## 12. Tích hợp Java Driver và Spring Data Neo4j

Ứng dụng Java thường nhận `query` từ API, kiểm tra độ dài/quy tắc tìm kiếm, rồi truyền dưới dạng **tham số** cho Cypher. Ví dụ với Neo4j Java Driver:

```java
import org.neo4j.driver.AuthTokens;
import org.neo4j.driver.Driver;
import org.neo4j.driver.GraphDatabase;
import org.neo4j.driver.Record;
import org.neo4j.driver.Result;
import org.neo4j.driver.Session;

import java.util.Map;

public class ArticleSearchExample {
    public static void main(String[] args) {
        String uri = "neo4j://localhost:7687";
        String username = "neo4j";
        String password = System.getenv("NEO4J_PASSWORD");
        String luceneQuery = "cypher"; // Đã được xử lý theo chính sách tìm kiếm

        try (Driver driver = GraphDatabase.driver(
                 uri, AuthTokens.basic(username, password));
             Session session = driver.session()) {

            String cypher = """
                CALL db.index.fulltext.queryNodes(
                    'articleFulltext', $luceneQuery
                )
                YIELD node AS a, score
                WHERE a.status = 'PUBLISHED'
                RETURN a.articleId AS id, a.title AS title, score
                ORDER BY score DESC, a.articleId
                LIMIT $limit
                """;

            Result result = session.run(
                cypher,
                Map.of("luceneQuery", luceneQuery, "limit", 20)
            );

            while (result.hasNext()) {
                Record row = result.next();
                System.out.println(
                    row.get("id").asString() + " | " +
                    row.get("title").asString() + " | " +
                    row.get("score").asDouble()
                );
            }
        }
    }
}
```

Ví dụ sử dụng Java text block (Java 15+), cần môi trường Neo4j và Java Driver tương thích. Không đưa mật khẩu vào source code hoặc log; đoạn mã lấy mật khẩu từ biến môi trường để minh họa. Trong ứng dụng có connection pooling, nên quản lý `Driver` theo vòng đời ứng dụng thay vì mở/đóng cho từng HTTP request.

Với **Spring Data Neo4j**, có thể dùng repository/`Neo4jClient` và các truy vấn Cypher tùy biến để gọi procedure rồi ánh xạ `node` cùng `score` sang DTO. Một entity `Article` chỉ biểu diễn thuộc tính node là chưa đủ nếu API muốn trả cả điểm liên quan; DTO nên chứa thêm `score`, thông tin phân trang và metadata nghiệp vụ cần thiết.

Trong dịch vụ thực tế, nên phân tách:

1. **Chuẩn hóa và xác thực yêu cầu**: query trống, độ dài quá mức, ký tự đặc biệt, chọn index hoặc loại kết quả được phép.
2. **Thực thi tìm kiếm**: gọi full-text procedure bằng tham số và lọc quyền, trạng thái, ngôn ngữ.
3. **Tạo phản hồi**: trả ID ổn định, tiêu đề, score nếu hữu ích, kèm tiêu chí sắp xếp và giới hạn kết quả.
4. **Theo dõi hoạt động**: lưu số kết quả, độ trễ, lỗi cú pháp Lucene, thời điểm thay đổi index, tránh ghi log nguyên văn thông tin nhạy cảm.

## 13. Hiệu năng, phân trang và bảo trì

Full-text index thường giảm công việc so với quét toàn bộ thuộc tính văn bản, nhưng không bảo đảm mọi truy vấn đều nhanh. Đặc biệt cần lưu ý:

### 13.1. Giới hạn và sắp xếp kết quả

```cypher
CALL db.index.fulltext.queryNodes('articleFulltext', $luceneQuery)
YIELD node AS a, score
WHERE a.status = 'PUBLISHED'
RETURN a.articleId AS id, a.title AS title, score
ORDER BY score DESC, a.articleId ASC
SKIP $offset
LIMIT $pageSize;
```

Khi dữ liệu hoặc index thay đổi giữa các lần gọi, thứ tự tìm kiếm có thể đổi khiến phân trang bằng `SKIP` cho ra các trang không ổn định. `SKIP` lớn cũng có thể tốn chi phí. Hệ thống tìm kiếm quy mô lớn nên cân nhắc chiến lược phân trang và tính nhất quán phù hợp sản phẩm, đồng thời giới hạn `pageSize` và độ sâu truy vấn.

Điểm `score` từ **hai lần truy vấn khác nhau** hay từ **hai index khác nhau** không mặc nhiên so sánh trực tiếp được. Khi gộp kết quả bài viết và đánh giá, cần thiết kế phương thức xếp hạng liên loại riêng nếu có yêu cầu.

### 13.2. Chi phí ghi dữ liệu và dung lượng

Mỗi thay đổi ở thuộc tính được index có thể kéo theo cập nhật cấu trúc chỉ mục. Một full-text index bao phủ nhiều label/relationship type và nhiều trường văn bản sẽ cần thêm bộ nhớ đệm, dung lượng đĩa và công việc cập nhật. Nên chọn các thuộc tính thực sự được tìm kiếm.

### 13.3. Quan sát và khắc phục lỗi

- Kiểm tra `SHOW FULLTEXT INDEXES` để biết index đã `ONLINE` hay chưa.
- Khi không tìm thấy văn bản, thử truy vấn một từ đơn giản đã biết có trong dữ liệu và kiểm tra analyzer.
- Xác minh node có label, relationship có type, và thuộc tính có kiểu dữ liệu phù hợp.
- Kiểm tra xem bộ lọc `status`, `language`, quyền truy cập hoặc mẫu `MATCH` có loại hết kết quả hay không.
- Nếu dùng eventually consistent, đánh giá độ trễ cập nhật và đợi đồng bộ trong môi trường thử nghiệm nếu cần.
- Với truy vấn Cypher có nhiều bước nối quan hệ sau tìm kiếm, sử dụng `EXPLAIN` hoặc `PROFILE` để xem phần mở rộng đồ thị; khả năng tìm nhanh bằng full-text không tự bảo đảm phần `MATCH` tiếp theo rẻ.

### 13.4. Quản lý vòng đời index

Khi đổi analyzer, tập label hoặc danh sách thuộc tính được index, cần thiết kế quy trình triển khai index phù hợp, xác minh index mới đã `ONLINE` và chuyển ứng dụng sang dùng tên mới. Xóa index chỉ khi chắc chắn không có truy vấn đang phụ thuộc:

```cypher
DROP INDEX articleFulltext IF EXISTS;
```

Lệnh trên **chỉ xóa index**, không xóa node hay relationship. Tuy nhiên, ứng dụng đang gọi `db.index.fulltext.queryNodes('articleFulltext', ...)` sẽ không còn sử dụng được tên index sau khi drop. Không thực hiện lệnh này trên hệ thống dùng chung chỉ để dọn ví dụ nếu chưa xác minh ảnh hưởng.

## 14. Các lỗi phổ biến và cách sửa

| Sai lầm | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Dùng `WHERE a.title = $q` cho tìm kiếm nhiều từ | Chỉ so khớp toàn bộ chuỗi, bỏ qua tìm theo token | Tạo full-text index và gọi procedure phù hợp |
| Tạo full-text index cho node rồi gọi `queryRelationships` | Sai loại thực thể/index | Chọn `queryNodes` cho node, `queryRelationships` cho relationship |
| Lập chỉ mục trường `rating` dạng số để tìm “5 sao” | Full-text không được thiết kế cho so khớp số | Dùng điều kiện số và index phù hợp |
| Chọn analyzer không phù hợp văn bản tiếng Việt | Tách từ hoặc đối chiếu dấu không như mong đợi | Kiểm thử tokenization, lựa chọn analyzer và chuẩn hóa có kiểm soát |
| Đặt tên index đúng nhưng bỏ sót label/type | Đối tượng mong muốn không tham gia index | Đối chiếu phạm vi tạo index với mô hình dữ liệu |
| Truy vấn ngay khi index đang `POPULATING` | Có thể chưa sử dụng được index | Chờ `ONLINE` và kiểm tra trạng thái |
| Đặt `LIMIT` mà bỏ lọc quyền truy cập | Có thể lộ nội dung hoặc metadata | Bảo đảm kiểm soát quyền trước khi trả kết quả |
| Gửi raw user input vào cú pháp Lucene nâng cao | Ký tự đặc biệt đổi ý nghĩa hoặc gây lỗi parse | Có chính sách escape/validate riêng cho Lucene |
| Hiểu `score` là xác suất chính xác | Xếp hạng và giải thích kết quả sai | Chỉ dùng như độ liên quan tương đối |
| Cho rằng index eventually consistent luôn thấy ghi mới | Giao diện có thể hiển thị kết quả cũ | Chọn nhất quán phù hợp và thiết kế thông báo/trải nghiệm |
| Gộp score từ nhiều index một cách trực tiếp | Thứ tự xếp hạng liên loại thiếu cơ sở | Thiết kế chiến lược tổng hợp/reranking riêng |

## 15. Bài tập thực hành

**Bài tập 1 — Tìm bài viết theo văn bản.** Tạo index `articleFulltext` trên `:Article(title, body)`, tìm `'cypher'` và trả ID, tiêu đề, score của bài đã xuất bản. Giải thích tại sao bài nháp không nên có trong kết quả công khai.

**Bài tập 2 — Tìm đánh giá trên relationship.** Tạo `reviewFulltext` cho quan hệ `:REVIEWED(title, comment)`. Viết truy vấn tìm chuỗi `'giao hàng'` và trả ID người viết cùng SKU sản phẩm. Bổ sung điều kiện chỉ lấy đánh giá từ 4 sao trở lên.

**Bài tập 3 — So sánh hai loại index.** Viết một truy vấn dùng `title CONTAINS $fragment` và một truy vấn qua `queryNodes`. Cho biết khác nhau về ý nghĩa khớp, khả năng tính score và loại index cần cân nhắc.

**Bài tập 4 — Hỗ trợ tiếng Việt không dấu.** Người dùng nhập `'do thi'` nhưng dữ liệu lưu `'đồ thị'`. Đề xuất cách kiểm thử analyzer và phương án chuẩn hóa nếu nghiệp vụ yêu cầu hai dạng truy vấn tương đương. Nêu nguy cơ nếu chuẩn hóa làm mất nội dung gốc.

**Bài tập 5 — Độ mới và phân trang.** API vừa cập nhật tiêu đề bài viết, index bật `eventually_consistent`; kết quả ở trang 1 và 2 được lấy bằng hai request liên tiếp. Phân tích vì sao kết quả có thể thay đổi và đề xuất cách thiết kế trải nghiệm cho người dùng.

### Checklist trước khi đưa tìm kiếm toàn văn vào hệ thống

- [ ] Đã xác định loại đối tượng: **node** hay **relationship**, label/type và thuộc tính văn bản.
- [ ] Đã chọn analyzer và kiểm thử từ khóa thực tế, đặc biệt với **tiếng Việt**.
- [ ] Index đã `ONLINE`; có cơ chế quan sát và triển khai khi thay đổi index.
- [ ] Truy vấn dùng **tham số Cypher** và xử lý riêng các ký tự điều khiển Lucene.
- [ ] Đã áp dụng điều kiện **trạng thái, ngôn ngữ, quyền truy cập** và giới hạn kết quả.
- [ ] Hiểu `score` là độ liên quan tương đối, không gộp tùy tiện giữa các index.
- [ ] Đã thống nhất yêu cầu về **độ mới** nếu bật eventually consistent.
- [ ] Đã đo độ trễ tìm kiếm, chi phí duy trì index và phần duyệt đồ thị sau khi lấy kết quả.

**Ghi nhớ:** full-text index giúp tìm *nội dung văn bản* gắn với node hoặc relationship, còn Cypher giúp kiểm tra và khai thác *cấu trúc liên kết* của property graph. Chọn đúng analyzer, đúng phạm vi index, đúng procedure, và kết hợp điều kiện nghiệp vụ là nền tảng để xây dựng tìm kiếm nâng cao vừa hữu ích vừa đáng tin cậy trong Neo4j.
