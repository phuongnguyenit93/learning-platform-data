# Kết hợp kết quả tìm kiếm với điều kiện và quan hệ trong đồ thị

Trong Neo4j, tìm được một bài viết “khớp từ khóa” chưa đủ để trả kết quả. Ứng dụng còn cần biết bài **đã xuất bản chưa**, **gắn chủ đề nào**, **do ai viết**, **người tìm có theo dõi tác giả không** và **có quyền xem không**. Với mô hình **property graph**, Cypher có thể nhận các node ứng viên từ chỉ mục tìm kiếm, sau đó kiểm tra thuộc tính và relationship để quyết định bài nào thật sự phù hợp.

Bài thuộc chương **Tìm kiếm nâng cao** của module `DATABASE_ENGINE_GRAPH_NEO4J`. Ta sẽ kết hợp **full-text search**, điều kiện `WHERE`, truy vấn quan hệ `MATCH`/`EXISTS`, xếp hạng, phân trang và phân quyền. Phần mở rộng giới thiệu **vector search** và cách tích hợp truy vấn bằng Java Driver hoặc Spring Data Neo4j.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **truy xuất ứng viên** từ chỉ mục tìm kiếm với **lọc ứng viên** theo thuộc tính và quan hệ đồ thị.
2. Tạo full-text index và dùng `db.index.fulltext.queryNodes` để lấy các node kèm điểm liên quan `score`.
3. Áp dụng `EXISTS { MATCH ... }` cho chủ đề, người theo dõi và quyền truy cập mà không vô tình nhân số hàng kết quả.
4. Xếp hạng và phân trang đúng; giải thích vì sao `LIMIT` sớm có thể làm thiếu kết quả hợp lệ.
5. Kết hợp tín hiệu đồ thị vào thứ hạng, nhận biết giới hạn của vector top-k, và kiểm tra hiệu năng bằng `EXPLAIN`/`PROFILE`.

## 2. Bài toán: tìm bài viết phù hợp với người dùng

Xét đồ thị kiến thức:

~~~text
(:User)-[:FOLLOWS]->(:Author)-[:WROTE]->(:Article)
   |                                        |
   +--[:MEMBER_OF]->(:Workspace)<-[:VISIBLE_IN]-+
                                            |
                                            +--[:TAGGED_WITH]->(:Tag)
~~~

- `Article` có `articleId`, `title`, `body`, `status` và `publishedAt`.
- `User` là người tìm; `Author` là tác giả; `FOLLOWS` biểu diễn người dùng theo dõi tác giả.
- `TAGGED_WITH` liên kết bài với chủ đề; `MEMBER_OF` và `VISIBLE_IN` liên kết quyền xem qua workspace.

Yêu cầu nghiệp vụ:

> Tìm bài chứa nội dung về “Neo4j”, đã xuất bản từ tháng 3/2026, gắn tag `neo4j`, do tác giả tôi theo dõi viết, và thuộc workspace tôi tham gia. Sắp xếp theo độ liên quan.

| Tiêu chí | Phép xử lý tương ứng |
|---|---|
| Nội dung khớp từ khóa | Full-text index trên `title` và `body` |
| Đã xuất bản, đúng khoảng ngày | `WHERE a.status = ... AND a.publishedAt >= ...` |
| Bài có tag yêu cầu | `EXISTS { MATCH (a)-[:TAGGED_WITH]->(:Tag) }` |
| Tác giả được người dùng theo dõi | `EXISTS { MATCH (me)-[:FOLLOWS]->(:Author)-[:WROTE]->(a) }` |
| Người dùng có quyền xem bài | `EXISTS { MATCH (me)-[:MEMBER_OF]->(w)<-[:VISIBLE_IN]-(a) }` |
| Xếp kết quả hữu ích lên trước | `ORDER BY score DESC`, có khóa phụ phá hòa |

**Nguyên tắc:** tìm kiếm cung cấp các **ứng viên có liên quan**; điều kiện trên đồ thị xác định **ứng viên đủ điều kiện**. Điểm tìm kiếm `score` cao không bao giờ thay thế điều kiện quyền truy cập.

~~~mermaid
flowchart TD
    A["Nhập từ khóa"] --> B["Full-text index: node, score"]
    B --> C["Lọc trạng thái và ngày"]
    C --> D["Kiểm tra tag, tác giả, quyền bằng EXISTS"]
    D --> E["Xếp hạng với khóa phụ"]
    E --> F["LIMIT và phân trang"]
    F --> G["Trả nội dung được phép xem"]
~~~

## 3. Chuẩn bị đồ thị thực hành

Các ví dụ sử dụng cú pháp của **Neo4j 5** trên một database thực hành riêng. Trong ứng dụng thật, nên dùng uniqueness constraint cho các định danh như `userId`, `articleId` và `workspaceId`. `MERGE` trong ví dụ giúp hạn chế tạo trùng khi thử lại, nhưng không thay thế việc thiết kế toàn vẹn dữ liệu.

Tạo người dùng và quan hệ theo dõi, thành viên workspace:

~~~cypher
MERGE (me:User {userId: 'u1'})
MERGE (alice:Author {authorId: 'alice'})
MERGE (engineering:Workspace {workspaceId: 'engineering'})
MERGE (me)-[:FOLLOWS]->(alice)
MERGE (me)-[:MEMBER_OF]->(engineering);
~~~

Tạo năm bài viết và các relationship tương ứng:

~~~cypher
UNWIND [
  {
    articleId: 'A01', title: 'Tìm kiếm Neo4j bằng Cypher',
    body: 'Kết hợp full-text index với quan hệ đồ thị',
    authorId: 'alice', workspaceId: 'engineering',
    tag: 'neo4j', status: 'PUBLISHED',
    publishedAt: date('2026-03-10')
  },
  {
    articleId: 'A02', title: 'Neo4j và vector search',
    body: 'Tìm kiếm embedding trong cơ sở dữ liệu đồ thị',
    authorId: 'alice', workspaceId: 'engineering',
    tag: 'neo4j', status: 'DRAFT',
    publishedAt: date('2026-03-11')
  },
  {
    articleId: 'A03', title: 'Neo4j tối ưu truy vấn',
    body: 'Dùng PROFILE để đo chi phí Cypher',
    authorId: 'bob', workspaceId: 'engineering',
    tag: 'neo4j', status: 'PUBLISHED',
    publishedAt: date('2026-03-12')
  },
  {
    articleId: 'A04', title: 'Neo4j và bảo mật dữ liệu',
    body: 'Phân quyền tìm kiếm theo workspace',
    authorId: 'alice', workspaceId: 'confidential',
    tag: 'neo4j', status: 'PUBLISHED',
    publishedAt: date('2026-03-13')
  },
  {
    articleId: 'A05', title: 'Neo4j tích hợp Java Driver',
    body: 'Ứng dụng kết nối Cypher trong Java',
    authorId: 'alice', workspaceId: 'engineering',
    tag: 'java', status: 'PUBLISHED',
    publishedAt: date('2026-03-14')
  }
] AS row
MERGE (a:Article {articleId: row.articleId})
SET a.title = row.title,
    a.body = row.body,
    a.status = row.status,
    a.publishedAt = row.publishedAt
MERGE (author:Author {authorId: row.authorId})
MERGE (w:Workspace {workspaceId: row.workspaceId})
MERGE (tag:Tag {name: row.tag})
MERGE (author)-[:WROTE]->(a)
MERGE (a)-[:VISIBLE_IN]->(w)
MERGE (a)-[:TAGGED_WITH]->(tag)
RETURN a.articleId AS articleId
ORDER BY articleId;
~~~

| Bài | Tác giả | Trạng thái | Workspace | Tag |
|---|---|---|---|---|
| A01 | alice | PUBLISHED | engineering | neo4j |
| A02 | alice | DRAFT | engineering | neo4j |
| A03 | bob | PUBLISHED | engineering | neo4j |
| A04 | alice | PUBLISHED | confidential | neo4j |
| A05 | alice | PUBLISHED | engineering | java |

Người dùng `u1` theo dõi `alice` và chỉ tham gia `engineering`. Theo yêu cầu ở mục 2, kết quả sau khi lọc đầy đủ phải là **A01**. Các bài còn lại đều chứa “Neo4j” nhưng thiếu ít nhất một điều kiện.

## 4. Truy xuất ứng viên từ full-text index

### 4.1. Tạo chỉ mục và kiểm tra trạng thái

~~~cypher
CREATE FULLTEXT INDEX article_text_search IF NOT EXISTS
FOR (a:Article) ON EACH [a.title, a.body];
~~~

Full-text index dùng analyzer để xử lý văn bản và tính độ liên quan. Nó khác với range index/text index dành cho các điều kiện thuộc tính. Trong Neo4j 5, việc dùng full-text index và lấy `score` thường được thực hiện bằng thủ tục; `WHERE a.body CONTAINS 'Neo4j'` có ngữ nghĩa so khớp chuỗi riêng, không tự trả `score` của full-text index.

~~~cypher
SHOW INDEXES
YIELD name, type, state, labelsOrTypes, properties
WHERE name = 'article_text_search'
RETURN name, type, state, labelsOrTypes, properties;
~~~

Index mới tạo có thể ở trạng thái `POPULATING`. Cần chờ `ONLINE` để truy vấn sử dụng; với `FAILED`, hãy xem thông tin lỗi và cấu hình trước khi đo hiệu năng.

### 4.2. Truy vấn full-text

~~~cypher
CALL db.index.fulltext.queryNodes(
  'article_text_search',
  'Neo4j'
)
YIELD node, score
RETURN node.articleId AS articleId,
       node.title AS title,
       score AS textScore
ORDER BY textScore DESC, articleId ASC;
~~~

`node` là node khớp; `score` là mức liên quan do cơ chế full-text tính. Giá trị phụ thuộc văn bản, analyzer, cú pháp truy vấn và thống kê index: **không dự đoán số điểm cố định** cho từng bài. Cú pháp tìm kiếm có thể hỗ trợ các toán tử Lucene, dấu ngoặc, cụm từ và ký tự đặc biệt; do đó, chuỗi nhập từ người dùng cần được xử lý phù hợp với tính năng tìm kiếm mà ứng dụng cho phép.

Lưu ý:

- Full-text search phân tích từ/ngữ; không đồng nghĩa với so sánh chuỗi bằng `=` hay tìm chuỗi con `CONTAINS`.
- Điểm của các từ khóa hoặc các index khác nhau không mặc nhiên chung một thang đo để cộng/trừ trực tiếp.
- Nếu cấu hình index ở chế độ cập nhật **eventually consistent**, dữ liệu vừa ghi có thể chưa xuất hiện ngay trong tìm kiếm. Kiểm tra chế độ cập nhật khi cần kết quả mới nhất.

## 5. Truy vấn hoàn chỉnh: kết hợp thuộc tính và quan hệ

Các tham số:

| Tham số | Ví dụ | Kiểu |
|---|---|---|
| `$userId` | `'u1'` | String |
| `$searchText` | `'Neo4j'` | String |
| `$fromDate` | `'2026-03-01'` | Chuỗi ngày ISO |
| `$tagName` | `'neo4j'` | String |
| `$pageSize` | `20` | Integer |

~~~cypher
MATCH (me:User {userId: $userId})
CALL db.index.fulltext.queryNodes(
  'article_text_search',
  $searchText
)
YIELD node, score
WITH me, node AS a, score
WHERE a.status = 'PUBLISHED'
  AND a.publishedAt >= date($fromDate)
  AND EXISTS {
    MATCH (a)-[:TAGGED_WITH]->(:Tag {name: $tagName})
  }
  AND EXISTS {
    MATCH (me)-[:FOLLOWS]->(:Author)-[:WROTE]->(a)
  }
  AND EXISTS {
    MATCH (me)-[:MEMBER_OF]->(w:Workspace)<-[:VISIBLE_IN]-(a)
  }
RETURN a.articleId AS articleId,
       a.title AS title,
       a.publishedAt AS publishedAt,
       score AS textScore
ORDER BY textScore DESC, articleId ASC
LIMIT $pageSize;
~~~

Với dữ liệu và tham số mẫu, truy vấn trả **A01**:

| Bài | Vì sao giữ hoặc loại |
|---|---|
| A01 | Giữ: xuất bản, đúng tag, tác giả được theo dõi, workspace hợp lệ |
| A02 | Loại: `status = 'DRAFT'` |
| A03 | Loại: tác giả `bob` không được `u1` theo dõi |
| A04 | Loại: `u1` không tham gia `confidential` |
| A05 | Loại: tag là `java`, khác `neo4j` |

`MATCH` đầu tìm đúng người đang yêu cầu; thủ tục full-text trả ứng viên; `WITH` đưa `node` thành `a` và chuyển `score` qua giai đoạn sau; các điều kiện kiểm tra thuộc tính và quan hệ trước khi sắp xếp và giới hạn.

### Vì sao dùng `EXISTS { MATCH ... }`?

`EXISTS` trả boolean: **có ít nhất một đường quan hệ đúng mẫu không?** Vì chỉ dùng để lọc, mỗi ứng viên full-text không bị nhân hàng khi có nhiều relationship thỏa điều kiện.

Ví dụ một bài có 4 tag và hiển thị trong 3 workspace. Nếu dùng hai lệnh `MATCH` để mở tất cả tag và workspace, có thể tạo `4 × 3 = 12` hàng cho cùng một bài, gây trùng kết quả hoặc làm sai phân trang. Hai `EXISTS` độc lập cho câu hỏi “có tag phù hợp?” và “có workspace chung?” vẫn chỉ để lại một hàng của ứng viên khi cả hai đúng.

~~~cypher
// Có thể tạo nhiều hàng / Article.
CALL db.index.fulltext.queryNodes(
  'article_text_search', $searchText
) YIELD node, score
MATCH (node)-[:TAGGED_WITH]->(tag:Tag)
RETURN node.articleId AS articleId, tag.name AS tag, score;
~~~

~~~cypher
// Kiểm tra điều kiện, không mở rộng hàng vì các tag.
CALL db.index.fulltext.queryNodes(
  'article_text_search', $searchText
) YIELD node, score
WHERE EXISTS {
  MATCH (node)-[:TAGGED_WITH]->(:Tag {name: $tagName})
}
RETURN node.articleId AS articleId, score;
~~~

Nếu cần **hiển thị danh sách tag**, có thể tổng hợp `collect(DISTINCT tag.name)` sau khi xác định các bài được phép xem, thay vì mở rộng tag trước khi phân trang.

### Quyền truy cập là điều kiện bắt buộc

Quy tắc minh họa trong bài là: người dùng có quyền xem Article nếu tồn tại **ít nhất một workspace chung** với Article đó.

~~~cypher
EXISTS {
  MATCH (me)-[:MEMBER_OF]->(w:Workspace)<-[:VISIBLE_IN]-(a)
}
~~~

Hệ thống thật có thể có role, nhóm, quyền phủ định, trạng thái thành viên, hiệu lực theo thời gian hoặc cấp tổ chức. Khi đó phải mô tả **đúng toàn bộ chính sách quyền** trong truy vấn phía server. Không được trả node không được phép về API rồi chỉ ẩn ở frontend; dữ liệu đã bị gửi cho người dùng.

## 6. Thứ tự lọc, xếp hạng và `LIMIT`

Một lỗi phổ biến: lấy 10 bài full-text liên quan nhất **trước**, rồi mới kiểm tra trạng thái, tag hoặc quyền:

~~~cypher
CALL db.index.fulltext.queryNodes(
  'article_text_search',
  $searchText,
  {limit: 10}
)
YIELD node, score
WITH node AS a, score
WHERE a.status = 'PUBLISHED'
  AND EXISTS {
    MATCH (a)-[:TAGGED_WITH]->(:Tag {name: $tagName})
  }
RETURN a.articleId AS articleId, score
ORDER BY score DESC;
~~~

Trong 10 ứng viên đầu có thể có nhiều bản nháp, bài sai tag hoặc bài người dùng không được phép xem. Sau khi lọc, kết quả có thể còn ít hơn 10 **dù phía sau còn bài hợp lệ**. Đoạn minh họa trên cũng chưa kiểm tra quyền và tác giả, nên không được dùng để đáp ứng yêu cầu ở mục 2.

Khi yêu cầu là “tối đa 10 bài **hợp lệ** có `score` cao nhất”, hãy áp dụng tất cả điều kiện bắt buộc rồi mới `LIMIT`:

~~~cypher
MATCH (me:User {userId: $userId})
CALL db.index.fulltext.queryNodes(
  'article_text_search', $searchText
)
YIELD node, score
WITH me, node AS a, score
WHERE a.status = 'PUBLISHED'
  AND a.publishedAt >= date($fromDate)
  AND EXISTS {
    MATCH (a)-[:TAGGED_WITH]->(:Tag {name: $tagName})
  }
  AND EXISTS {
    MATCH (me)-[:FOLLOWS]->(:Author)-[:WROTE]->(a)
  }
  AND EXISTS {
    MATCH (me)-[:MEMBER_OF]->(w:Workspace)<-[:VISIBLE_IN]-(a)
  }
RETURN a.articleId AS articleId, score
ORDER BY score DESC, articleId ASC
LIMIT 10;
~~~

**Đánh đổi hiệu năng:** nếu từ khóa rất phổ biến, full-text index có thể tạo nhiều ứng viên để Cypher kiểm tra quan hệ. Việc lấy dư ứng viên (*over-fetch*) rồi lọc có thể giảm độ trễ ở quy mô lớn, nhưng **không bảo đảm** tìm đủ top-k hợp lệ nếu cắt tập ứng viên quá sớm. Thiết kế cần đo cả **độ phủ sau lọc** và chi phí thực thi; mọi phương án đều phải giữ kiểm tra quyền ở server.

## 7. Tín hiệu đồ thị có thể tham gia xếp hạng

Trong một tính năng khác, “theo dõi tác giả” có thể là **ưu tiên mềm** chứ không phải điều kiện bắt buộc. Ví dụ dưới đây giữ các bài được phép xem và tăng điểm cho bài của tác giả người dùng theo dõi:

~~~cypher
MATCH (me:User {userId: $userId})
CALL db.index.fulltext.queryNodes(
  'article_text_search', $searchText
)
YIELD node, score
WITH me, node AS a, score
WHERE a.status = 'PUBLISHED'
  AND EXISTS {
    MATCH (me)-[:MEMBER_OF]->(w:Workspace)<-[:VISIBLE_IN]-(a)
  }
WITH a, me, score,
     CASE
       WHEN EXISTS {
         MATCH (me)-[:FOLLOWS]->(:Author)-[:WROTE]->(a)
       }
       THEN 0.2
       ELSE 0.0
     END AS followBoost
WITH a, score, followBoost,
     score + followBoost AS finalScore
RETURN a.articleId AS articleId,
       score AS textScore,
       followBoost,
       finalScore
ORDER BY finalScore DESC, articleId ASC
LIMIT 20;
~~~

Truy vấn này có thể hiển thị bài của tác giả **không** được theo dõi nếu đủ quyền. Ngược lại, khi sản phẩm yêu cầu **chỉ** bài của tác giả đã theo dõi, phải dùng `EXISTS` cho `FOLLOWS` trong `WHERE` như mục 5.

Mức cộng `0.2` chỉ là ví dụ. `score` full-text không nhất thiết ở khoảng `[0,1]`, vì vậy cần đánh giá phân bố điểm, chất lượng thứ hạng và tham số nghiệp vụ trước khi chọn trọng số thực tế. Tín hiệu tương tác hay lượt thích cũng cần được tổng hợp theo **đúng đơn vị Article**, tránh mở rộng quan hệ làm nhân hàng.

### Hiển thị tag sau khi xác định trang

Khi muốn trả cả danh sách tag, có thể tổng hợp **sau khi đã giới hạn danh sách Article hợp lệ**:

~~~cypher
MATCH (me:User {userId: $userId})
CALL db.index.fulltext.queryNodes(
  'article_text_search', $searchText
)
YIELD node, score
WITH me, node AS a, score
WHERE a.status = 'PUBLISHED'
  AND EXISTS {
    MATCH (me)-[:MEMBER_OF]->(w:Workspace)<-[:VISIBLE_IN]-(a)
  }
WITH a, score
ORDER BY score DESC, a.articleId ASC
LIMIT 10
CALL (a) {
  OPTIONAL MATCH (a)-[:TAGGED_WITH]->(tag:Tag)
  RETURN collect(DISTINCT tag.name) AS tags
}
RETURN a.articleId AS articleId,
       a.title AS title,
       score, tags
ORDER BY score DESC, articleId ASC;
~~~

Subquery `CALL (a) { ... }` sử dụng cú pháp nhập biến từ **Neo4j 5.23+**. Các phiên bản Neo4j 5 cũ có thể dùng `CALL { WITH a ... }` nếu hỗ trợ subquery. `OPTIONAL MATCH` và `collect(...)` trả danh sách tag mà vẫn giữ một hàng cho mỗi Article. Ví dụ này chỉ lọc **trạng thái và quyền** để làm rõ thao tác lấy thêm tag; muốn giữ yêu cầu của mục 2, bổ sung tag, tác giả và ngày **trước `LIMIT`**.

## 8. Phân trang và thứ tự ổn định

Nhiều bài có thể cùng `score`. Chỉ `ORDER BY score DESC` không xác định thứ tự giữa các bài bằng điểm; cần khóa phụ ổn định, chẳng hạn `articleId` đã có **uniqueness constraint**.

~~~cypher
// Phần cuối một pipeline đã có a và score.
RETURN a.articleId AS articleId,
       a.title AS title,
       score
ORDER BY score DESC, articleId ASC
SKIP $offset
LIMIT $pageSize;
~~~

`$offset` và `$pageSize` cần là số nguyên không âm, đồng thời ứng dụng nên giới hạn kích thước trang. Dù có khóa phụ, kết quả các trang ở **những thời điểm khác nhau** vẫn có thể dịch chuyển khi bài, quan hệ hoặc điểm tìm kiếm thay đổi. `SKIP` sâu cũng phải bỏ qua nhiều hàng; hệ thống lớn cần cân nhắc cursor, kết quả tìm kiếm theo phiên hoặc cơ chế phân trang phù hợp với yêu cầu nhất quán.

## 9. Mở rộng: vector search với quan hệ đồ thị

Neo4j 5 hỗ trợ **vector index** ở các phiên bản thích hợp để tìm các node có embedding gần vector truy vấn. Full-text search dựa trên từ/ngữ; vector search phục vụ tính tương tự **ngữ nghĩa** từ một mô hình embedding. Cả hai trả ứng viên và **đều phải được kiểm tra trạng thái, quan hệ và quyền** trước khi đưa ra API.

Ví dụ tạo index cho vector **3 chiều** dùng trong thực hành (không phải embedding production):

~~~cypher
CREATE VECTOR INDEX article_embedding_idx IF NOT EXISTS
FOR (a:Article) ON (a.embedding)
OPTIONS {indexConfig: {
  `vector.dimensions`: 3,
  `vector.similarity_function`: 'cosine'
}};
~~~

Hai khóa cấu hình ở trên có dấu backtick đúng cú pháp Cypher. Kích thước index phải khớp với chiều embedding đang dùng.

~~~cypher
UNWIND [
  {id: 'A01', v: [1.0, 0.1, 0.0]},
  {id: 'A02', v: [0.9, 0.2, 0.0]},
  {id: 'A03', v: [0.8, 0.1, 0.3]},
  {id: 'A04', v: [0.7, 0.1, 0.4]},
  {id: 'A05', v: [0.6, 0.5, 0.1]}
] AS row
MATCH (a:Article {articleId: row.id})
SET a.embedding = row.v;
~~~

Khi index đã `ONLINE`, truy vấn vector gần nhất:

~~~cypher
MATCH (me:User {userId: $userId})
CALL db.index.vector.queryNodes(
  'article_embedding_idx',
  $k,
  $queryEmbedding
)
YIELD node, score
WITH me, node AS a, score
WHERE a.status = 'PUBLISHED'
  AND EXISTS {
    MATCH (me)-[:MEMBER_OF]->(w:Workspace)<-[:VISIBLE_IN]-(a)
  }
RETURN a.articleId AS articleId,
       a.title AS title,
       score AS vectorScore
ORDER BY vectorScore DESC, articleId ASC;
~~~

Với dữ liệu mẫu, `$queryEmbedding = [1.0, 0.0, 0.0]` và `$k = 5` chỉ để thử cơ chế; chúng không đại diện cho embedding được học từ văn bản. Vector phải là số có đúng số chiều và phù hợp với độ đo tương tự của index.

**Bẫy top-k:** thủ tục vector lấy `k` ứng viên lân cận **trước khi** Cypher kiểm tra workspace. Sau lọc có thể còn ít hơn `k` bài, dù những bài hợp lệ khác nằm ngoài tập ứng viên. Tăng `k` có thể giúp tăng độ phủ, nhưng làm tăng chi phí và không bảo đảm top-k chính xác trên toàn bộ tập được phân quyền; tìm kiếm vector có thể là gần đúng.

Với **hybrid search** (full-text + vector), có thể kết hợp hai danh sách xếp hạng bằng kỹ thuật như *reciprocal rank fusion* hoặc chuẩn hóa điểm đã được kiểm chứng. Không cộng thẳng `textScore + vectorScore` nếu chưa hiểu hai thang điểm. Trong mọi trường hợp, không tiết lộ dữ liệu, số đếm hay trích đoạn nhạy cảm từ ứng viên không qua kiểm tra quyền.

## 10. Kiểm chứng index và hiệu năng

### 10.1. Chọn cấu trúc tương ứng truy vấn

| Nhu cầu | Lựa chọn |
|---|---|
| Tìm từ/ngữ trong tiêu đề và nội dung | **Full-text index** với thủ tục truy vấn |
| Lọc trạng thái, thời gian hoặc giá trị thuộc tính | **Range index** nếu mẫu lọc phù hợp |
| Tìm `User` theo `userId` hay `Article` theo `articleId` | Uniqueness constraint/index phù hợp |
| Lần theo tác giả, tag, workspace | Relationship traversal và `EXISTS` |
| Tìm sự gần nhau của embedding | **Vector index** |
| Sắp xếp theo score và phân trang | `ORDER BY`, khóa phá hòa, kiểm tra `Sort`/`Top` |

Index không thay thế việc thiết kế hướng quan hệ và cardinality của truy vấn. Một full-text index tốt có thể vẫn chậm nếu mỗi ứng viên phải mở hàng nghìn nhánh không cần thiết; một range index trên `status` cũng không tự giải quyết bài toán xếp hạng nội dung.

### 10.2. `EXPLAIN` và `PROFILE`

~~~cypher
EXPLAIN
MATCH (me:User {userId: $userId})
CALL db.index.fulltext.queryNodes(
  'article_text_search', $searchText
)
YIELD node, score
WITH me, node AS a, score
WHERE a.status = 'PUBLISHED'
  AND EXISTS {
    MATCH (me)-[:MEMBER_OF]->(w:Workspace)<-[:VISIBLE_IN]-(a)
  }
RETURN a.articleId AS articleId, score
ORDER BY score DESC, articleId ASC
LIMIT 20;
~~~

~~~cypher
PROFILE
MATCH (me:User {userId: $userId})
CALL db.index.fulltext.queryNodes(
  'article_text_search', $searchText
)
YIELD node, score
WITH me, node AS a, score
WHERE a.status = 'PUBLISHED'
  AND EXISTS {
    MATCH (me)-[:MEMBER_OF]->(w:Workspace)<-[:VISIBLE_IN]-(a)
  }
RETURN a.articleId AS articleId, score
ORDER BY score DESC, articleId ASC
LIMIT 20;
~~~

Khi xem kế hoạch, chú ý:

1. **Rows**: có bao nhiêu ứng viên từ full-text và còn bao nhiêu sau khi lọc? Có bước `MATCH` nào làm tăng số hàng ngoài ý muốn?
2. **DB Hits**: có phải kiểm tra quá nhiều node/relationship cho từng ứng viên?
3. **Các toán tử áp dụng subquery/điều kiện tồn tại**: số hàng và chi phí ở nơi kiểm tra workspace, tác giả, tag.
4. **Sort/Top**: việc sắp theo `score`, tín hiệu graph và khóa phụ có thêm chi phí nào?

`EXPLAIN` chỉ hiển thị kế hoạch dự kiến; `PROFILE` chạy truy vấn để đo số liệu. Tên toán tử và chiến lược tối ưu khác nhau giữa phiên bản Neo4j. Đừng kết luận từ vài node thử nghiệm: hãy đo trên dữ liệu đại diện, nhiều loại từ khóa, nhiều workspace và các phân bố quan hệ khác nhau.

### 10.3. Những nguyên tắc giúp tối ưu đúng

- **Lọc bằng `EXISTS` khi chỉ cần kiểm tra tồn tại**; dùng `MATCH` mở rộng khi thật sự cần các node/relationship bổ sung.
- **Trả ít thuộc tính cần thiết** cho danh sách kết quả; tránh gửi toàn bộ `body` hoặc `embedding` nếu giao diện không cần.
- **Bảo đảm định danh duy nhất** bằng constraint; tránh giả định dữ liệu đã sạch chỉ vì truy vấn mẫu không có trùng.
- **Xác định tiêu chí đúng đắn trước khi cắt ứng viên**: top-k sau lọc quyền có thể khác top-k của index.
- **Đo trên dữ liệu thật**: 5 bài thực hành không phản ánh được chi phí khi số lượng bài và quan hệ lớn.
- **Giữ kiểm tra quyền phía server** trong mọi trường hợp, kể cả khi tối ưu truy vấn và cache kết quả.

## 11. Tích hợp với Java Driver và Spring Data Neo4j

Ứng dụng có thể truyền `userId`, từ khóa, ngày và tag bằng tham số **Neo4j Java Driver**, tránh ghép trực tiếp chúng vào cú pháp Cypher:

~~~java
import java.util.Map;
import org.neo4j.driver.Driver;
import org.neo4j.driver.Record;
import org.neo4j.driver.Session;

// Driver đã được ứng dụng khởi tạo và quản lý vòng đời.
String cypher = """
    MATCH (me:User {userId: $userId})
    CALL db.index.fulltext.queryNodes('article_text_search', $searchText)
    YIELD node, score
    WITH me, node AS a, score
    WHERE a.status = 'PUBLISHED'
      AND a.publishedAt >= date($fromDate)
      AND EXISTS {
        MATCH (a)-[:TAGGED_WITH]->(:Tag {name: $tagName})
      }
      AND EXISTS {
        MATCH (me)-[:FOLLOWS]->(:Author)-[:WROTE]->(a)
      }
      AND EXISTS {
        MATCH (me)-[:MEMBER_OF]->(w:Workspace)<-[:VISIBLE_IN]-(a)
      }
    RETURN a.articleId AS id, a.title AS title, score
    ORDER BY score DESC, id ASC
    LIMIT $pageSize
    """;

Map<String, Object> params = Map.of(
    "userId", "u1",
    "searchText", "Neo4j",
    "fromDate", "2026-03-01",
    "tagName", "neo4j",
    "pageSize", 20
);

try (Session session = driver.session()) {
    var articles = session.executeRead(tx ->
        tx.run(cypher, params)
          .list((Record row) -> Map.of(
              "id", row.get("id").asString(),
              "title", row.get("title").asString(),
              "score", row.get("score").asDouble()
          ))
    );
    articles.forEach(System.out::println);
}
~~~

Ví dụ dùng Java text block (Java 15+) và `Driver` đã tồn tại. Trong hệ thống thật, cần cấu hình database đích, transaction timeout và cơ chế quản lý connection/session theo kiến trúc. `executeRead` phù hợp với truy vấn đọc. Với **Spring Data Neo4j**, có thể viết cùng Cypher trong `@Query` của repository hoặc dùng `Neo4jClient` để bind tham số.

**Phân biệt hai lớp an toàn truy vấn:** truyền `$searchText` dưới dạng tham số giúp tránh chèn cú pháp **Cypher**, nhưng nội dung đó vẫn được trình phân tích **Lucene** diễn giải như truy vấn full-text. Nếu ứng dụng chỉ cho phép từ khóa đơn giản, cần quy định xử lý/escape ký tự đặc biệt; nếu cho phép toán tử nâng cao, phải giới hạn độ dài và độ phức tạp. User hiện hành phải được xác thực ở server; không lấy `userId` tự khai báo từ request chưa tin cậy làm căn cứ duy nhất để phân quyền.

## 12. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Hướng xử lý |
|---|---|---|
| Trả bài không được phép xem | Chỉ lọc ở frontend hoặc tin vào `score` | Kiểm tra quyền theo relationship trong Cypher server |
| Cùng Article xuất hiện nhiều lần | Mở rộng nhiều tag/workspace bằng `MATCH` | Dùng `EXISTS` để lọc hoặc tổng hợp theo Article |
| Trang trả ít bài dù còn bài hợp lệ | Giới hạn ứng viên quá sớm | Đưa `LIMIT` sau điều kiện bắt buộc; đo độ phủ |
| Truy vấn `CONTAINS` không có `score` | Không gọi thủ tục full-text | Dùng full-text khi cần thứ hạng văn bản |
| Bài mới chưa xuất hiện | Index chưa `ONLINE` hoặc eventual consistency | Kiểm tra trạng thái/cấu hình index |
| Phân trang không ổn định | Trùng `score` hoặc dữ liệu thay đổi | Thêm khóa phụ và chiến lược nhất quán |
| Kết hợp vector và text cho điểm khó giải thích | Hai điểm có thang đo khác nhau | Dùng chuẩn hóa hoặc trộn thứ hạng |
| Độ trễ cao | Quá nhiều ứng viên và traversal | `PROFILE`, giảm nhân hàng, cân nhắc mô hình |

## 13. Bài tập

### Bài 1: Chỉ lọc trạng thái và quyền

Hãy tìm bài chứa “Neo4j”, đã xuất bản và hiển thị trong workspace người dùng tham gia, **không bắt buộc** tag hoặc tác giả được theo dõi.

**Lời giải tham khảo:**

~~~cypher
MATCH (me:User {userId: $userId})
CALL db.index.fulltext.queryNodes('article_text_search', $query)
YIELD node, score
WITH me, node AS a, score
WHERE a.status = 'PUBLISHED'
  AND EXISTS {
    MATCH (me)-[:MEMBER_OF]->(w:Workspace)<-[:VISIBLE_IN]-(a)
  }
RETURN a.articleId AS articleId, a.title AS title, score
ORDER BY score DESC, articleId ASC;
~~~

Với `$userId = 'u1'` và `$query = 'Neo4j'`, dữ liệu mẫu cho A01, A03 và A05 (theo thứ tự điểm thực tế).

### Bài 2: Giới hạn quá sớm

Một vector query lấy top-5, sau đó lọc quyền và chỉ còn 2 bài. Có thể kết luận chỉ có 2 bài hợp lệ không?

**Gợi ý:** Không. Hai kết quả chỉ đến từ **5 ứng viên đầu**. Các bài hợp lệ khác có thể nằm ngoài tập vector top-5. Thử tăng số ứng viên và đánh giá độ phủ; không được bỏ kiểm tra quyền.

### Bài 3: Đếm số hàng

Một Article có 4 tag và nằm trong 3 workspace. Truy vấn mở cả hai nhánh trước khi `RETURN a, score` có thể tạo bao nhiêu hàng cho cùng Article?

**Đáp án:** `4 × 3 = 12` hàng nếu cả hai nhánh khớp đầy đủ. Với mục đích lọc, dùng `EXISTS`; khi cần thông tin danh sách, tổng hợp riêng theo Article.

### Bài 4: Phân biệt lọc bắt buộc và tín hiệu ưu tiên

Thiết kế tìm kiếm với điều kiện “user phải có quyền xem; ưu tiên bài của tác giả được theo dõi nhưng vẫn cho phép bài khác”.

**Gợi ý:** Quyền là `WHERE EXISTS` bắt buộc; `FOLLOWS` đóng vai trò tăng điểm trong `CASE WHEN EXISTS`. Xếp hạng theo điểm cuối, có khóa phụ, rồi mới `LIMIT`. Nếu thay yêu cầu thành “chỉ bài của tác giả đã theo dõi”, chuyển `FOLLOWS` thành điều kiện lọc.

## 14. Ghi nhớ

- **Full-text hoặc vector search tìm ứng viên; Cypher kết hợp thuộc tính và quan hệ để quyết định kết quả hợp lệ.**
- **Kiểm tra quyền là điều kiện bắt buộc tại server**, không phải tín hiệu xếp hạng hay logic chỉ chạy ở giao diện.
- **`EXISTS { MATCH ... }` lọc theo sự tồn tại của quan hệ**, tránh nhân hàng do nhiều đường liên kết.
- **`LIMIT` quá sớm có thể làm mất các bài hợp lệ nằm ngoài tập ứng viên đã cắt.**
- **Điểm tìm kiếm có thể kết hợp tín hiệu đồ thị**, nhưng phải kiểm soát thang điểm, thứ tự ổn định và thay đổi giữa các trang.
- **Dùng `SHOW INDEXES`, `EXPLAIN` và `PROFILE`** để đánh giá kế hoạch, số hàng trung gian, chi phí và độ phủ trên dữ liệu đại diện.
