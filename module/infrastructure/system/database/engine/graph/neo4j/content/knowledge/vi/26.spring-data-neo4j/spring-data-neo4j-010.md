# Phân trang, tải dữ liệu và nhận diện truy vấn lặp không cần thiết

## 1. Vì sao phân trang một đồ thị khác phân trang bảng dữ liệu?

Một API viết bằng Spring Data Neo4j (SDN) thường phải trả danh sách đối tượng như bài viết, khách hàng, sản phẩm hoặc đơn hàng. Trên property graph, mỗi node gốc có thể nối với nhiều node khác bằng relationship: một `Article` có nhiều `Tag`, một `Customer` có nhiều `Order`, một `Product` có nhiều đánh giá. Nếu nạp toàn bộ quan hệ cho từng kết quả, response và số lượng dữ liệu trung gian có thể tăng rất nhanh.

Ví dụ màn hình quản trị muốn hiển thị **10 bài viết mỗi trang**, mỗi bài có tiêu đề, ngày đăng và số lượng tag. Có ba bẫy:

- Câu Cypher phân trang **dòng sau khi mở rộng relationship** có thể trả ít hơn 10 bài viết duy nhất.
- Truy vấn lấy toàn bộ entity và nhiều quan hệ có thể đem về hàng nghìn node/relationship dù màn hình chỉ cần vài trường.
- Service gọi repository tìm tag riêng **cho từng bài** có thể phát sinh dạng truy vấn lặp `1 + N` (thường gọi là *N+1 query problem*).

Bài này thuộc chương **Spring Data Neo4j** của mô-đun `DATABASE_ENGINE_GRAPH_NEO4J`. Chúng ta sẽ dùng `Pageable`, `Page`, `Slice`, truy vấn Cypher, `Neo4jClient`, `EXPLAIN` và `PROFILE` để phân trang đúng **node gốc**, chọn đúng dữ liệu cần tải, phát hiện truy vấn trùng lặp và cân bằng số round trip với chi phí xử lý graph.

**Sau bài học, bạn có thể:**

1. Chọn giữa `Page<T>`, `Slice<T>` và `List<T>` theo nhu cầu API.
2. Bảo đảm phân trang ổn định bằng `ORDER BY` và khóa phân biệt các node.
3. Hiểu giới hạn của `@Relationship` và cách custom query ảnh hưởng đến entity mapping.
4. Nhận diện N+1 do code service/repository, query hydrating graph và Cartesian product.
5. Viết truy vấn có `WITH … SKIP … LIMIT` **trước** khi mở rộng quan hệ.
6. Đo số câu Cypher, `Rows`, `DB Hits`, memory, query latency và tính đúng đắn trên dữ liệu nhỏ có đáp án.

> **Phạm vi công nghệ:** Các ví dụ dùng Neo4j 5+ và Spring Data Neo4j 7.x/8.x theo API Spring Data Commons. Chữ ký annotation và khả năng mapping cần được đối chiếu với version Spring Boot/SDN thực đang dùng. Các con số thực hành là **đáp án logic**, không phải kết quả benchmark hiệu năng đã chạy trên Neo4j.

## 2. Ba câu hỏi phải trả lời trước khi viết repository

| Câu hỏi | Lựa chọn tốt khi | Rủi ro nếu bỏ qua |
|---|---|---|
| **Phân trang cái gì?** | Mỗi phần tử API là một node gốc, ví dụ một `Article` | Phân trang dòng quan hệ khiến một bài chiếm nhiều vị trí |
| **Màn hình cần trường gì?** | Chỉ lấy `id`, `title`, `publishedAt`, tag count cho trang danh sách | Fetch cả graph và map entity dù không hiển thị |
| **Có cần tổng chính xác?** | Dùng `Page` khi UI bắt buộc hiện `totalElements`/`totalPages` | COUNT bổ sung làm tăng chi phí và độ trễ |

Không nên chọn `findAll()` rồi `stream().skip(...).limit(...)` phía Java để làm phân trang. Cách đó có thể phải tải tất cả đối tượng/relationship và lọc **sau khi trả dữ liệu từ server**. Phân trang phải được thực hiện trong Cypher/database, hoặc bằng truy vấn do SDN tạo ra với `Pageable`.

### 2.1. Cấu trúc tải một trang

~~~mermaid
flowchart TD
  A["HTTP GET /articles?page=0&size=2"] --> B["Service kiểm tra page/size/sort"]
  B --> C["Repository / Neo4jClient"]
  C --> D["Cypher: lọc và sắp xếp node gốc"]
  D --> E["SKIP / LIMIT trên danh sách gốc"]
  E --> F["Chỉ lấy thuộc tính / relationship cần cho trang"]
  F --> G["DTO + metadata Page/Slice"]
  G --> H["Trả response giới hạn"]
~~~

Điểm cần nhớ: **thứ tự lọc → sắp xếp → giới hạn node gốc → tải quan hệ** tạo ra kết quả khác với **mở rộng quan hệ → sắp xếp → giới hạn dòng**.

## 3. Page, Slice, List và Pageable

Spring Data Commons cung cấp các kiểu phổ biến:

| Kiểu trả về | Có gì? | Khi thích hợp | Chi phí cần chú ý |
|---|---|---|---|
| `Page<T>` | Content, trang hiện tại, total elements/pages, hasNext | Màn hình cần số trang/tổng bản ghi chính xác | Thường cần **count query** bổ sung; framework có thể tối ưu bỏ qua trong vài trường hợp |
| `Slice<T>` | Content, số trang và hasNext, **không có tổng chính xác** | “Xem thêm”, infinite scroll | Thường tránh count; cơ chế có thể đọc thêm một phần tử để biết có trang kế |
| `List<T>` với `Pageable` | Chỉ danh sách trong phạm vi trang | API tự quản lý thông tin phân trang hoặc chỉ cần top-N | Không có metadata đầy đủ, không tự trả total |
| `Stream<T>` | Đọc kết quả dần theo cơ chế hỗ trợ | Xử lý nhiều bản ghi tuần tự | Phải đóng stream/transaction đúng vòng đời, không biến thành API không giới hạn |

`PageRequest.of(0, 20)` lấy **trang đầu tiên** vì chỉ số page bắt đầu từ 0. `size` là số phần tử tối đa trên một trang; không phải độ sâu relationship hay số dòng sau expand.

Ví dụ:

~~~java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;

Pageable pageable = PageRequest.of(
    0, 2,
    Sort.by(Sort.Order.desc("publishedAt"),
            Sort.Order.asc("articleId"))
);

Page<Article> page = articleRepository.findByStatus(
    "PUBLISHED", pageable
);
~~~

Giả sử repository và entity `Article` được khai báo ở mục 6. Đây là *derived query*: SDN sinh Cypher tương ứng với phương thức repository. Để so sánh hiệu năng, cần xem **câu Cypher thực được sinh**, không chỉ nhìn chữ ký phương thức Java.

**Phân biệt count:** Khi dùng `Page`, infrastructure có thể cần câu `COUNT` để biết tổng số phần tử. Nếu API chỉ trả nút “Tải thêm”, `Slice` thường tránh nhu cầu COUNT. Không giả định mỗi lời gọi `Page` luôn chạy đúng hai câu truy vấn: SDN/Spring Data có tối ưu và cách hydrate entity có thể thay đổi số lượt truy vấn.

## 4. Sắp xếp phải ổn định, nếu không sẽ trùng hoặc mất phần tử

Cypher **không bảo đảm thứ tự** nếu thiếu `ORDER BY`. Ngay cả `ORDER BY publishedAt DESC` vẫn có thể không ổn định khi nhiều bài có cùng ngày đăng. Vì vậy cần một **tie-breaker**, ví dụ `articleId ASC` có unique constraint.

~~~cypher
MATCH (a:QA010Article {status: 'PUBLISHED'})
RETURN a.articleId AS articleId,
       a.title AS title,
       a.publishedAt AS publishedAt
ORDER BY publishedAt DESC, articleId ASC
SKIP 0 LIMIT 2;
~~~

Để lấy trang kế:

~~~cypher
MATCH (a:QA010Article {status: 'PUBLISHED'})
RETURN a.articleId AS articleId,
       a.title AS title,
       a.publishedAt AS publishedAt
ORDER BY publishedAt DESC, articleId ASC
SKIP 2 LIMIT 2;
~~~

Không có khóa phân biệt, những node có cùng `publishedAt` có thể đổi chỗ giữa các lần chạy và gây trùng hoặc thiếu bản ghi giữa hai page.

**Quan trọng:** `ORDER BY` ổn định không tạo snapshot xuyên nhiều request. Nếu có bài mới được thêm hoặc `publishedAt`/`status` thay đổi giữa hai lần phân trang, offset có thể dịch chuyển. Trường hợp cần duyệt dữ liệu nhất quán trong một khoảng thời gian dài nên cân nhắc cursor/keyset hoặc snapshot ở tầng ứng dụng.

## 5. Fixture: sáu bài viết, ba tác giả và các tag

Dùng **database thử nghiệm riêng**. Bài đặt tên label và relationship với tiền tố `QA010` để tránh ảnh hưởng bài khác.

### 5.1. Bảng đáp án

| ID bài | Tiêu đề | Ngày đăng | Status | Tag |
|---|---|---|---|---|
| A001 | Neo4j Index | 2026-10-06 | PUBLISHED | java, neo4j |
| A002 | Cypher Basics | 2026-10-05 | PUBLISHED | neo4j |
| A003 | Java Driver | 2026-10-05 | PUBLISHED | java, performance |
| A004 | Tuning Graph | 2026-10-04 | PUBLISHED | performance |
| A005 | Spring Data Neo4j | 2026-10-03 | PUBLISHED | *(không có)* |
| A006 | Internal Draft | 2026-10-07 | DRAFT | java |

Năm bài `PUBLISHED` phải trả về theo thứ tự **A001, A002, A003, A004, A005**. A002 và A003 có **cùng ngày**, giúp kiểm tra tie-breaker. A006 có ngày mới hơn nhưng không được trả về vì `DRAFT`.

### 5.2. Tạo dữ liệu trong Neo4j Browser/cypher-shell

Chỉ xóa dữ liệu của fixture nếu chắc chắn đây là database test, không có hệ thống khác dùng nhãn đó:

~~~cypher
DROP CONSTRAINT qa010_article_id_unique IF EXISTS;
~~~

~~~cypher
MATCH (n)
WHERE n:QA010Article OR n:QA010Author OR n:QA010Tag
DETACH DELETE n;
~~~

Tạo unique constraint cho khóa định danh:

~~~cypher
CREATE CONSTRAINT qa010_article_id_unique IF NOT EXISTS
FOR (a:QA010Article)
REQUIRE a.articleId IS UNIQUE;
~~~

Tạo sáu bài:

~~~cypher
UNWIND [
  {id:'A001', title:'Neo4j Index',
   published:'2026-10-06', state:'PUBLISHED'},
  {id:'A002', title:'Cypher Basics',
   published:'2026-10-05', state:'PUBLISHED'},
  {id:'A003', title:'Java Driver',
   published:'2026-10-05', state:'PUBLISHED'},
  {id:'A004', title:'Tuning Graph',
   published:'2026-10-04', state:'PUBLISHED'},
  {id:'A005', title:'Spring Data Neo4j',
   published:'2026-10-03', state:'PUBLISHED'},
  {id:'A006', title:'Internal Draft',
   published:'2026-10-07', state:'DRAFT'}
] AS row
CREATE (:QA010Article {
  articleId: row.id,
  title: row.title,
  publishedAt: date(row.published),
  status: row.state
});
~~~

Tạo ba tác giả và ba tag:

~~~cypher
UNWIND [
  {id:'U01', name:'An'},
  {id:'U02', name:'Binh'},
  {id:'U03', name:'Chi'}
] AS row
CREATE (:QA010Author {authorId:row.id, displayName:row.name});
~~~

~~~cypher
UNWIND ['java','neo4j','performance'] AS tagName
CREATE (:QA010Tag {name:tagName});
~~~

Nối tag:

~~~cypher
UNWIND [
  {article:'A001', tag:'java'},
  {article:'A001', tag:'neo4j'},
  {article:'A002', tag:'neo4j'},
  {article:'A003', tag:'java'},
  {article:'A003', tag:'performance'},
  {article:'A004', tag:'performance'},
  {article:'A006', tag:'java'}
] AS link
MATCH (a:QA010Article {articleId:link.article})
MATCH (t:QA010Tag {name:link.tag})
CREATE (a)-[:QA010_HAS_TAG]->(t);
~~~

Nối tác giả:

~~~cypher
UNWIND [
  {article:'A001', author:'U01'},
  {article:'A002', author:'U02'},
  {article:'A003', author:'U01'},
  {article:'A004', author:'U03'},
  {article:'A005', author:'U02'}
] AS link
MATCH (a:QA010Article {articleId:link.article})
MATCH (u:QA010Author {authorId:link.author})
CREATE (a)-[:QA010_WRITTEN_BY]->(u);
~~~

Kiểm tra số lượng:

~~~cypher
MATCH (a:QA010Article)
RETURN count(a) AS allArticles,
       count(CASE WHEN a.status='PUBLISHED' THEN 1 END)
         AS publishedArticles;
~~~

**Đáp án:** `allArticles = 6` và `publishedArticles = 5`. Ngoài ra có 3 tác giả, 3 tag, 7 relationship `QA010_HAS_TAG` và 5 relationship `QA010_WRITTEN_BY`.

## 6. Dùng repository với Page và Slice

Để minh họa phân trang node gốc **nhẹ**, lớp `Article` bên dưới chỉ chứa các field cần cho màn hình danh sách và **không ánh xạ relationship**. Đây là một read model đơn giản; trong ứng dụng thật có thể có domain entity đầy đủ ở lớp khác hoặc dùng `Neo4jClient` trả DTO.

~~~java
import java.time.LocalDate;
import org.springframework.data.annotation.Id;
import org.springframework.data.neo4j.core.schema.Node;

@Node("QA010Article")
public class Article {
    @Id
    private String articleId;
    private String title;
    private String status;
    private LocalDate publishedAt;

    public Article() {} // Ví dụ đơn giản cho cơ chế mapping.

    public String getArticleId() { return articleId; }
    public String getTitle() { return title; }
    public String getStatus() { return status; }
    public LocalDate getPublishedAt() { return publishedAt; }
}
~~~

~~~java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Slice;
import org.springframework.data.neo4j.repository.Neo4jRepository;

public interface ArticleRepository
        extends Neo4jRepository<Article, String> {

    Page<Article> findByStatus(String status, Pageable pageable);

    Slice<Article> findSliceByStatus(
        String status, Pageable pageable
    );
}
~~~

Sử dụng:

~~~java
var sorted = PageRequest.of(
    0, 2,
    Sort.by(Sort.Order.desc("publishedAt"),
            Sort.Order.asc("articleId"))
);

Page<Article> firstPage = articleRepository.findByStatus(
    "PUBLISHED", sorted
);

// Với fixture: content A001, A002 và totalElements = 5.
System.out.println(firstPage.getTotalElements());
System.out.println(firstPage.hasNext());
~~~

**Kỳ vọng logic:** trang số 0 chứa A001, A002; `getTotalElements() = 5`; `hasNext() = true`. Trang số 1 chứa A003, A004; trang số 2 chứa A005 và `hasNext() = false`.

Tên phương thức `findSliceByStatus` là derived finder có chủ đích minh họa; nếu phiên bản Spring Data cụ thể không suy diễn tên đó như mong muốn, có thể dùng `Slice<Article> findByStatus(String, Pageable)` trong một repository riêng hoặc đặt một tên finder được Spring Data hỗ trợ và kiểm tra câu query sinh ra. Trong cùng interface, Java không cho phép overload **chỉ khác kiểu trả về**, nên ví dụ dùng tên khác.

### Lưu ý khi entity có @Relationship

Nếu lớp `Article` trong ứng dụng thật có:

~~~java
import java.util.Set;
import org.springframework.data.neo4j.core.schema.Relationship;

// Bổ sung vào entity Article nếu nghiệp vụ quản lý quan hệ này:
@Relationship(type = "QA010_HAS_TAG",
              direction = Relationship.Direction.OUTGOING)
private Set<Tag> tags;
~~~

Thì chi phí của repository finder có thể thay đổi lớn: SDN cần dựng tập quan hệ cho entity theo mô hình ánh xạ. **Không mặc định rằng SDN sẽ dùng cơ chế lazy-loading proxy giống Hibernate/JPA.** SDN có khả năng sinh các truy vấn chứa pattern comprehension, map projection, hoặc thêm các lượt truy vấn khi có quan hệ vòng/lược đồ phức tạp; hành vi cụ thể phụ thuộc model và phiên bản.

Do đó, trên endpoint danh sách chỉ cần vài trường, đừng tự động trả entity graph đầy đủ. Dùng **projection/read DTO hoặc Cypher tùy biến** và đo số liệu trước khi kết luận việc phân trang đã giảm tải thực sự.

## 7. Custom @Query: người viết phải kiểm soát paging và count

Khi điều kiện phức tạp hơn derived query, có thể dùng `@Query`.

~~~java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.neo4j.repository.query.Query;
import org.springframework.data.repository.query.Param;

public interface ArticleCustomRepository
        extends Neo4jRepository<Article, String> {

    @Query(
      value = """
        MATCH (a:QA010Article)
        WHERE a.status = $status
        RETURN a
        ORDER BY a.publishedAt DESC, a.articleId ASC
        SKIP $skip LIMIT $limit
        """,
      countQuery = """
        MATCH (a:QA010Article)
        WHERE a.status = $status
        RETURN count(a)
        """
    )
    Page<Article> findPageWithQuery(
        @Param("status") String status, Pageable pageable
    );
}
~~~

Ở những thế hệ SDN có hỗ trợ custom page query theo mẫu này, `$skip` và `$limit` là tham số mà framework cung cấp từ `Pageable`. **Không tự động giả định** việc thêm tham số `Pageable` khiến mọi truy vấn Cypher tùy chỉnh đều được giới hạn đúng nếu câu query không có `SKIP/LIMIT`.

Vì thứ tự đã được viết trong Cypher, nên gọi:

~~~java
var page = PageRequest.of(0, 2); // Pageable unsorted
var result = customRepository.findPageWithQuery(
    "PUBLISHED", page
);
~~~

`countQuery` phải chứa **cùng điều kiện lọc theo node gốc** với query lấy dữ liệu. Nếu query lấy dữ liệu chỉ trả bài đã xuất bản nhưng count đếm cả `DRAFT`, `totalElements` và `totalPages` sẽ sai.

Nếu dùng `@Query` để trả `Slice`, thường không cần `countQuery` nhưng vẫn phải dùng `SKIP/LIMIT` và logic thứ tự rõ ràng. Cần kiểm tra phiên bản SDN của dự án và câu Cypher thực tế qua logging vì hỗ trợ paging tùy chỉnh khác nhau giữa các thế hệ.

> **Quy tắc:** Trên custom `@Query`, không cho rằng `Sort` trong `Pageable` luôn được ghép an toàn vào mọi đoạn Cypher tùy ý. Nếu đã dùng `ORDER BY` cố định trong query, truyền một `Pageable` không sắp xếp và kiểm thử thực tế.

## 8. Bẫy lớn: phân trang các dòng đã nở vì relationship

Với fixture, A001 có 2 tag, A002 có 1 tag, A003 có 2 tag, A004 có 1 tag, A005 không có tag.

### 8.1. Query dễ viết nhưng sai ý nghĩa

~~~cypher
MATCH (a:QA010Article {status:'PUBLISHED'})
OPTIONAL MATCH (a)-[:QA010_HAS_TAG]->(t:QA010Tag)
RETURN a.articleId AS articleId,
       a.publishedAt AS publishedAt,
       t.name AS tag
ORDER BY publishedAt DESC, articleId ASC, tag ASC
SKIP 0 LIMIT 2;
~~~

**Kết quả dự kiến ở trang đầu:**

| articleId | tag |
|---|---|
| A001 | java |
| A001 | neo4j |

Query trả **hai dòng**, nhưng chỉ có **một bài viết duy nhất**. A002 bị đẩy sang trang sau vì A001 chiếm hai dòng do quan hệ một-nhiều. Nếu API yêu cầu “2 bài/trang”, đây là kết quả sai về phân trang dù câu Cypher chạy hợp lệ.

Thử đếm:

~~~cypher
MATCH (a:QA010Article {status:'PUBLISHED'})
OPTIONAL MATCH (a)-[:QA010_HAS_TAG]->(t:QA010Tag)
RETURN count(*) AS expandedRows,
       count(DISTINCT a) AS uniqueArticles,
       count(t) AS tagMatches;
~~~

**Đáp án:** `expandedRows = 7`, `uniqueArticles = 5`, `tagMatches = 6`. A005 không có tag nhưng vẫn tạo **một dòng** với `t = null` do `OPTIONAL MATCH`.

Nếu count query dùng `count(*)` sau mở rộng mà Page hiển thị 7 phần tử, trong khi content được kỳ vọng có 5 article, đó là lỗi đếm phạm vi **dòng** thay vì **node gốc**.

### 8.2. Đúng: page node gốc trước, mở rộng quan hệ sau

~~~cypher
MATCH (a:QA010Article {status:'PUBLISHED'})
WITH a
ORDER BY a.publishedAt DESC, a.articleId ASC
SKIP 0 LIMIT 2
OPTIONAL MATCH (a)-[:QA010_HAS_TAG]->(t:QA010Tag)
RETURN
  a.articleId AS articleId,
  a.title AS title,
  a.publishedAt AS publishedAt,
  collect(DISTINCT t.name) AS tags
ORDER BY publishedAt DESC, articleId ASC;
~~~

**Đáp án:**

| articleId | tags (không phụ thuộc thứ tự trong list) |
|---|---|
| A001 | java, neo4j |
| A002 | neo4j |

Ở đây `WITH a ORDER BY ... SKIP ... LIMIT ...` chọn đúng **2 bài** trước. `OPTIONAL MATCH` chỉ mở quan hệ cho hai bài đó. `collect(DISTINCT t.name)` gom tag lại để mỗi bài xuất hiện **một record**.

Không có tag thì `collect(t.name)` bỏ qua null và cho danh sách rỗng. Để làm entity mapping đầy đủ bằng SDN, chỉ gom *giá trị tên tag* như trên chưa đủ để hydrate mọi relationship; mẫu này thích hợp nhất cho **DTO đọc**.

### 8.3. Custom query hydrating entity cần một record mỗi root

Khi cố tình load relationship vào entity SDN, ví dụ:

~~~cypher
MATCH (a:QA010Article {status:'PUBLISHED'})
WITH a
ORDER BY a.publishedAt DESC, a.articleId ASC
SKIP $skip LIMIT $limit
OPTIONAL MATCH (a)-[rel:QA010_HAS_TAG]->(t:QA010Tag)
RETURN a, collect(rel) AS relationships,
          collect(t) AS relatedNodes;
~~~

Tập kết quả sau `RETURN` có **một record cho mỗi node gốc** và mang node/relationship cần cho mapping. Đây là hình dạng mà tài liệu SDN custom query nhấn mạnh, nhưng **đúng shape không đồng nghĩa query tự động cấp đầy đủ mọi quan hệ** khi entity có nhiều loại `@Relationship` hoặc đường đi sâu. Khi query trả entity nhưng bỏ các quan hệ mà mapper kỳ vọng, có nguy cơ entity không đầy đủ; tuyệt đối không ghi/sửa lại entity bị tải thiếu với giả định rằng nó chứa toàn bộ graph.

**Kết luận thực hành:** endpoint danh sách nên ưu tiên DTO tách khỏi entity dùng để ghi, và chỉ nạp quan hệ cần hiển thị.

## 9. Tải dữ liệu theo ba chiến lược

| Chiến lược | Số query điển hình | Điểm mạnh | Rủi ro |
|---|---|---|---|
| **Một query DTO** | 1 query lấy trang, có thể thêm count | Số round trip ít, chọn đúng field, dễ kiểm soát | Aggregation hoặc expand lớn có thể chiếm RAM server |
| **Hai pha theo batch** | 1 query lấy trang + 1 query lấy quan hệ cho **tập ID** (+ count nếu cần) | Page root đúng, giảm lặp truy vấn, dễ tách nội dung | Phải ghép kết quả theo ID và giữ thứ tự trang |
| **Một query mỗi root** | 1 query lấy trang + N query riêng (+ count) | Code service dễ viết | N+1 round trip, độ trễ tăng theo kích thước page |

Một query không phải lúc nào cũng nhanh nhất nếu nó tạo Cartesian product rất lớn. Một vài query batched có thể tốt hơn khi số loại quan hệ nhiều, cần giới hạn quyền dữ liệu hoặc muốn lấy summaries trước rồi chỉ hydrate chi tiết theo nhu cầu.

### 9.1. Một query DTO kèm tag cho cả trang

Có thể dùng query mục 8.2 cùng `Neo4jClient` và map result sang read DTO:

~~~java
import java.time.LocalDate;
import java.util.List;

public record ArticleRow(
    String articleId,
    String title,
    LocalDate publishedAt,
    List<String> tags
) {}
~~~

~~~java
import java.util.List;
import org.neo4j.driver.Value;
import org.springframework.data.neo4j.core.Neo4jClient;

public List<ArticleRow> loadSummaries(Neo4jClient client) {
    String cypher = """
        MATCH (a:QA010Article {status:$status})
        WITH a
        ORDER BY a.publishedAt DESC, a.articleId ASC
        SKIP $skip LIMIT $limit
        OPTIONAL MATCH (a)-[:QA010_HAS_TAG]->(t:QA010Tag)
        RETURN a.articleId AS articleId,
               a.title AS title,
               a.publishedAt AS publishedAt,
               collect(DISTINCT t.name) AS tags
        ORDER BY publishedAt DESC, articleId ASC
        """;

    var rows = client.query(cypher)
        .bind("PUBLISHED").to("status")
        .bind(0L).to("skip")
        .bind(2L).to("limit")
        .fetchAs(ArticleRow.class)
        .mappedBy((typeSystem, record) ->
            new ArticleRow(
                record.get("articleId").asString(),
                record.get("title").asString(),
                record.get("publishedAt").asLocalDate(),
                record.get("tags").asList(Value::asString)
            )
        )
        .all();

    return List.copyOf(rows);
}
~~~

Ví dụ dùng Java 17 record. `Neo4jClient` tích hợp với transaction management của Spring Data Neo4j; việc bind tham số giúp tránh nối chuỗi từ request trực tiếp vào Cypher. Với ứng dụng thực tế, đưa `status`/offset/limit từ tham số service sau khi kiểm tra giới hạn.

Nếu trả `Page<ArticleRow>` với tổng chính xác, cần một count query cùng filter `status` và tạo metadata trang tương ứng, ví dụ qua `PageImpl` trong service; hoặc trả `Slice` để không tốn count khi UI không cần.

### 9.2. Hai pha: trả root IDs rồi lấy quan hệ cho cả danh sách

**Pha 1** lấy ID đúng trang:

~~~cypher
MATCH (a:QA010Article {status:'PUBLISHED'})
RETURN a.articleId AS articleId
ORDER BY a.publishedAt DESC, a.articleId ASC
SKIP 0 LIMIT 2;
~~~

Đáp án: `['A001', 'A002']` theo thứ tự.

**Pha 2** nhận tham số `$ids = ['A001','A002']`:

~~~cypher
UNWIND $ids AS articleId
MATCH (a:QA010Article {articleId:articleId})
OPTIONAL MATCH (a)-[:QA010_HAS_TAG]->(t:QA010Tag)
RETURN articleId, collect(DISTINCT t.name) AS tags;
~~~

Kết quả là một record cho mỗi bài trong `$ids`, kèm tập tag. **Không phụ thuộc thứ tự trả về của `UNWIND` hoặc aggregation**: trong Java, dựng `Map<String,List<String>>` theo `articleId` rồi duyệt lại danh sách ID **từ pha 1** để giữ đúng thứ tự trang.

Nếu câu query pha 1 đã trả cả `articleId,title,publishedAt`, pha 2 chỉ cần trả thông tin quan hệ, không phải nạp lại toàn bộ node gốc. Với nhiều loại relationship, cân nhắc query batched riêng cho từng loại hoặc một Cypher được nhóm có kiểm soát.

## 10. N+1: không chỉ xảy ra trong ORM quan hệ

Trong ORM kiểu Hibernate, người học quen với N+1 từ lazy loading. Với Spring Data Neo4j, **không được suy luận rằng SDN luôn lazy-load từng relationship**. Cơ chế mapping dựa trên Cypher/record và có thể lấy quan hệ theo một truy vấn hoặc thực hiện nhiều query khi model có vòng và chiều sâu phức tạp. Tuy nhiên N+1 **vẫn có thể** xuất hiện nếu code service tự gọi query phụ cho từng root.

### 10.1. Ví dụ một service tạo N+1

~~~java
Page<Article> page = articleRepository.findByStatus(
    "PUBLISHED", PageRequest.of(
        0, 2,
        Sort.by(Sort.Order.desc("publishedAt"),
                Sort.Order.asc("articleId"))
    )
);

var summaries = page.getContent().stream()
    .map(article -> new ArticleWithTags(
        article.getArticleId(),
        article.getTitle(),
        tagRepository.findNamesByArticleId(
            article.getArticleId()
        )
    ))
    .toList();
~~~

Với repository phụ có query:

~~~java
@Query("""
    MATCH (a:QA010Article {articleId:$articleId})
          -[:QA010_HAS_TAG]->(t:QA010Tag)
    RETURN t.name AS name
    ORDER BY name
    """)
List<String> findNamesByArticleId(
    @Param("articleId") String articleId
);
~~~

Có thể có **một query lấy trang + N query đọc tag**, và thêm **count query** nếu dùng `Page`. Với N=2 ở fixture, code gọi riêng hai lần cho A001 và A002; với `size=100`, có thể là 100 truy vấn tag.

Giả sử round trip/overhead query phụ trung bình là 5 ms khi chạy tuần tự, **100 query phụ** đã có thể tạo khoảng 500 ms chỉ ở phần cộng dồn, chưa tính thời gian thực thi, transfer và mapping. Đây là ví dụ **ước lượng**, không phải kết quả thực của Neo4j.

### 10.2. Vì sao một số thiết kế SDN vẫn có nhiều query?

- Service/mapper gọi repository hoặc `Neo4jClient` trong vòng lặp.
- Graph model tự tham chiếu hoặc có relationship vòng, khiến cơ chế mapping SDN của một phiên bản phải nạp bổ sung qua nhiều query.
- Một serializer truy cập property được viết như hàm tính toán, mỗi lần gọi truy vấn riêng.
- Endpoint trả entity có nhiều quan hệ không cần thiết, gây “over-fetch” dù **không** có N+1.

Hai vấn đề **N+1** và **over-fetch** khác nhau: một là **số round trip tăng theo N**, hai là **mỗi query tải quá nhiều dữ liệu**. Một endpoint có thể mắc cả hai.

### 10.3. Cách phát hiện bằng quan sát

1. Bật logging query/counter ở môi trường test hoặc theo dõi query log/tracing của Neo4j.
2. Gọi API với `size=1,2,5,10` trên cùng dataset đủ lớn.
3. Ghi **số câu Cypher**, câu nào lặp theo mẫu, tổng records/bytes và latency p50/p95.
4. Phân loại query: lấy root, count, nạp quan hệ, kiểm tra quyền, truy vấn riêng ở service.
5. Nếu số query phụ tăng xấp xỉ theo số root và chúng giống nhau chỉ khác `articleId`, đó là dấu hiệu mạnh của N+1.
6. Thay bằng truy vấn **`UNWIND $ids` theo batch** hoặc DTO một query, sau đó đo lại trên cùng data và concurrency.

**Không chỉ đếm query:** nếu chuyển từ 101 query nhỏ sang 1 query có Cartesian product hàng triệu dòng, bạn có thể làm latency và RAM server tệ hơn. So cả `Rows`, `DB Hits`, `Memory (Bytes)`, response bytes và p95.

## 11. Tránh Cartesian product khi có nhiều quan hệ một-nhiều

Giả sử mỗi `Article` có 20 tag và 30 phản hồi; query sai:

~~~cypher
MATCH (a:Article {articleId:$id})
OPTIONAL MATCH (a)-[:HAS_TAG]->(t:Tag)
OPTIONAL MATCH (a)-[:HAS_COMMENT]->(c:Comment)
RETURN a, t, c;
~~~

Với một bài có 20 tag và 30 comment, hai `OPTIONAL MATCH` có thể tạo **20 × 30 = 600 dòng** trung gian. Kết quả còn có các cặp tag-comment lặp dù API chỉ cần hai danh sách độc lập.

Một cách tránh nhân chéo là **gom từng nhóm trước khi mở rộng nhóm tiếp theo**:

~~~cypher
MATCH (a:Article {articleId:$id})
OPTIONAL MATCH (a)-[:HAS_TAG]->(t:Tag)
WITH a, collect(DISTINCT t.name) AS tagNames
OPTIONAL MATCH (a)-[:HAS_COMMENT]->(c:Comment)
RETURN a.articleId AS articleId,
       tagNames,
       collect(DISTINCT c.commentId) AS commentIds;
~~~

Đây là **mẫu khái niệm** cho schema `Article/Tag/Comment` giả định, không phải fixture `QA010`. Nếu chỉ cần count các quan hệ, dùng `count` hoặc subquery aggregation thay vì tải toàn bộ node/phản hồi.

Việc `collect` nhiều bản ghi cũng tiêu thụ memory. Khi một bài có hàng trăm nghìn quan hệ, nên cân nhắc **phân trang riêng danh sách con** (ví dụ comments), giới hạn hiển thị và tách endpoint chi tiết. Đừng trả toàn bộ graph sâu chỉ vì có khả năng viết một query.

## 12. Phân trang sâu: SKIP/OFFSET và keyset

Offset pagination:

~~~cypher
MATCH (a:QA010Article {status:'PUBLISHED'})
RETURN a.articleId AS articleId,
       a.publishedAt AS publishedAt
ORDER BY publishedAt DESC, articleId ASC
SKIP $skip LIMIT $limit;
~~~

Với `page=1000`, `size=20`, `skip=20000`. Để chọn trang sâu, database vẫn phải tìm/sắp xếp và bỏ qua nhiều bản ghi phù hợp, dù cuối cùng chỉ trả 20. Trên tập dữ liệu lớn, latency thường tăng theo offset và cách planner/index phục vụ thứ tự.

**Keyset/cursor pagination** dựa vào khóa sắp xếp cuối trang trước. Với `ORDER BY publishedAt DESC, articleId ASC`, trang sau con trỏ `($lastDate, $lastId)` có thể dùng:

~~~cypher
MATCH (a:QA010Article {status:'PUBLISHED'})
WHERE a.publishedAt < date($lastDate)
   OR (a.publishedAt = date($lastDate)
       AND a.articleId > $lastId)
RETURN a.articleId AS articleId,
       a.title AS title,
       a.publishedAt AS publishedAt
ORDER BY publishedAt DESC, articleId ASC
LIMIT $limit;
~~~

Ví dụ trang đầu là A001, A002. Con trỏ cuối trang `lastDate='2026-10-05'`, `lastId='A002'`. Trang tiếp theo bắt đầu bằng **A003**, rồi **A004** (với `limit=2`). Tie-breaker là bắt buộc để không bỏ mất A003 có cùng ngày A002.

Chú ý:

- Lượt đầu không có cursor: bỏ điều kiện WHERE của cursor, giữ filter `status` và `ORDER BY`.
- Sắp xếp phải cố định, khóa cursor ổn định và có thể so sánh. Dữ liệu thay đổi trong lúc lật trang vẫn cần quy tắc nhất quán nghiệp vụ.
- Keyset không mặc nhiên trả được số trang/tổng chính xác. Nó hợp với feed vô hạn và tập kết quả lớn hơn là UI nhảy tới trang số 500 tùy ý.
- Chọn index phù hợp cho filter/thứ tự và đo `PROFILE` để biết liệu planner tận dụng được nó; không suy rằng có index luôn làm mọi đoạn `OR` tối ưu.

## 13. Index, count query và kế hoạch thực thi

### 13.1. Index cho bộ lọc và sắp xếp

Từ fixture, có thể cân nhắc một RANGE index phục vụ status/date theo thứ tự:

~~~cypher
CREATE RANGE INDEX qa010_article_feed IF NOT EXISTS
FOR (a:QA010Article) ON (a.status, a.publishedAt);
~~~

Đây là **cấu hình minh họa**. Index có thứ tự khóa và khả năng sử dụng phụ thuộc predicate, ORDER BY, cardinality và kế hoạch; không chắc query đồng thời tránh được sort chỉ vì đã tạo index này. `articleId` có unique constraint riêng cho định danh; cần đo kế hoạch trên dataset đủ lớn để đánh giá index composite hoặc cách thiết kế khác.

Kiểm tra:

~~~cypher
SHOW INDEXES
YIELD name, type, state, labelsOrTypes, properties
WHERE name IN ['qa010_article_feed',
               'qa010_article_id_unique']
RETURN name, type, state, labelsOrTypes, properties;
~~~

Chỉ benchmark sau khi index `ONLINE`. Có thể không tạo index này cho fixture sáu node vì số lượng quá nhỏ không có ý nghĩa hiệu năng.

### 13.2. EXPLAIN không chạy, PROFILE có chạy

~~~cypher
EXPLAIN
MATCH (a:QA010Article {status:'PUBLISHED'})
RETURN a.articleId AS articleId,
       a.publishedAt AS publishedAt
ORDER BY publishedAt DESC, articleId ASC
SKIP 0 LIMIT 2;
~~~

~~~cypher
PROFILE
MATCH (a:QA010Article {status:'PUBLISHED'})
RETURN a.articleId AS articleId,
       a.publishedAt AS publishedAt
ORDER BY publishedAt DESC, articleId ASC
SKIP 0 LIMIT 2;
~~~

Ghi các thông số:

| Thuộc tính plan | Diễn giải |
|---|---|
| `Rows` | Dòng thực từng operator, dễ phát hiện nở vì `OPTIONAL MATCH` |
| `Estimated Rows` | Dự báo cardinality; sai nhiều có thể chọn kế hoạch kém |
| `DB Hits` | Công việc truy cập tầng lưu trữ, không đồng nghĩa số disk reads |
| `Memory (Bytes)` | Bộ nhớ trung gian, đặc biệt `Sort`, `Aggregation`, `collect` |
| `Page Cache Hits/Misses` | Tình trạng dữ liệu/index trong cache nếu edition/runtime có |
| `NodeIndexSeek`/`NodeByLabelScan`/`Sort` | Gợi ý index/scan/sort được dùng, nhưng không tự kết luận tốc độ từ tên |

Khi phân tích count query, kiểm tra riêng:

~~~cypher
PROFILE
MATCH (a:QA010Article {status:'PUBLISHED'})
RETURN count(a) AS total;
~~~

Count đúng là **5**. Một count query lọc theo tag hoặc expand quan hệ cần dùng `count(DISTINCT a)` khi mỗi root có thể xuất hiện nhiều lần, đồng thời phải phản ánh đúng điều kiện của data query.

## 14. Quy trình benchmark tìm N+1 và over-fetch

### 14.1. Giữ workload công bằng

- Cùng database, schema, dataset, phiên bản SDN/Neo4j, topology và pool.
- Cùng endpoint và số trường cần hiển thị; không so một API trả 2 field với API trả toàn bộ graph rồi gọi là “nhanh gấp đôi”.
- Cùng kích thước trang, thứ tự, filter, tình trạng index và trạng thái warmup.
- Thu thập query count, p50/p95, total bytes/records, `DB Hits`, memory và GC ở app nếu có.
- Ghi lại số query do `Page COUNT` và số query do hydrator/service riêng biệt; không quy mọi câu query phụ là N+1.

### 14.2. Ba phép thử đối chứng

| Phương án | Dự kiến số query cho trang N=20 | Điều cần kiểm tra |
|---|---:|---|
| Service đọc tags cho từng article | ~1 root + 20 tag (+count) | Query tag lặp, round trip và latency tăng theo N |
| Một Cypher DTO đúng root | ~1 data (+count nếu cần) | Rows sau expand, memory, kết quả gồm đúng 20 root |
| Hai pha root + batch tags | ~2 data (+count nếu cần) | Không lặp N query, đảm bảo thứ tự trang và dữ liệu tag đầy đủ |

Con số ở cột giữa là **mô hình giả định**, không phải cam kết SDN thực sự chạy đúng từng ấy câu. SDN có thể sinh query phụ khi mapper xử lý relationship phức tạp hoặc tối ưu count. Phải xác minh trên log/tracing.

### 14.3. Cấu hình quan sát

Có thể tăng mức log của SDN trong **staging/test**:

~~~properties
logging.level.org.springframework.data.neo4j=DEBUG
~~~

Đây là điểm bắt đầu để quan sát, **không bảo đảm** version nào cũng log đầy đủ câu Cypher cùng số truy vấn. Tùy Driver/SDN/runtime, cấu hình tracing, query logging hoặc instrumentation riêng sẽ hữu ích hơn. Khi bật debug, kiểm soát dữ liệu nhạy cảm trong statement/parameters và chi phí I/O của log; không bật tràn lan trên production.

Một kịch bản test tích hợp với `@DataNeo4jTest` hoặc Testcontainers có thể: seed dữ liệu → gọi endpoint `size=1,2,5` → xác minh ID, tag đúng → đếm statement truy cập `QA010_HAS_TAG`. Test **kết quả và số lượng truy vấn** giúp phát hiện regression sau khi nâng cấp SDN hoặc đổi model `@Relationship`.

## 15. Lỗi thường gặp và hướng sửa

| Triệu chứng | Nguyên nhân có thể | Hướng sửa |
|---|---|---|
| Mỗi page yêu cầu 10 bài nhưng chỉ có 3 bài duy nhất | `LIMIT` áp lên dòng đã expand quan hệ | Page node gốc bằng `WITH ... SKIP ... LIMIT` trước `OPTIONAL MATCH` |
| Dùng `Page` chậm hơn `Slice` | Có thể phải COUNT tổng phần tử | Dùng Slice nếu UI chỉ cần hasNext |
| Bài trùng giữa hai page dù data không đổi | Thiếu `ORDER BY` hoặc tie-breaker | Sắp xếp ổn định theo ngày và unique ID |
| A003 mất khỏi page khi có cùng ngày A002 | Keyset cursor không xét khóa thứ hai | Điều kiện cursor theo cặp ngày, ID |
| Query count tăng gần tuyến tính với page size | Service gọi repository quan hệ trong vòng lặp | Batch bằng `UNWIND $ids` hoặc một query DTO |
| Query count thấp nhưng memory/Rows cao | Một Cypher mở nhiều collection độc lập | Gom từng quan hệ; tránh Cartesian product |
| Trả entity đầy đủ gây payload lớn | Domain `@Relationship` nạp dữ liệu không cần | Read DTO/projection chỉ gồm trường cần |
| Custom `@Query` Page trả tổng sai | `countQuery` khác điều kiện lọc/root semantics | Count đúng `DISTINCT` root, cùng WHERE |
| `@Query` có Pageable nhưng trả cả dataset | Thiếu/không đúng `$skip`, `$limit` theo SDN version | Kiểm tra template, log câu query sinh ra |
| `PROFILE` nhanh nhưng API chậm | Client mapping/JSON/network/N+1 ngoài query | Đo end-to-end với tracing cả Java và Neo4j |
| Query sau nâng cấp SDN tăng số lượt | Thuật toán hydrate/mapping/cyclic graph thay đổi | Dùng integration test + logs, cân nhắc read DTO |
| Dùng `findAll()` và `subList()` | Tải toàn bộ dữ liệu về JVM | Phân trang tại database hoặc cursor streaming có giới hạn |

## 16. Bài tập có đáp án

### Bài 1 — Page hay Slice?

Một màn hình feed chỉ cần nút “Tải thêm” và tối đa 20 bài mỗi lượt, không hiển thị tổng số bài viết. Nên chọn gì?

**Đáp án:** `Slice<Article>` hoặc cursor DTO thích hợp hơn `Page<Article>` vì không cần count tổng chính xác. Vẫn cần order ổn định và kiểm tra hasNext.

### Bài 2 — Tính đúng fixture

Với `size=2`, sort ngày giảm dần rồi `articleId` tăng dần, liệt kê ba trang bài PUBLISHED.

**Đáp án:** trang 0: A001, A002; trang 1: A003, A004; trang 2: A005. A006 là DRAFT nên bị loại.

### Bài 3 — Hiểu expanded rows

Năm bài PUBLISHED có số tag lần lượt là 2,1,2,1,0. `OPTIONAL MATCH` từ article sang tag cho bao nhiêu dòng? `count(DISTINCT a)` bằng bao nhiêu?

**Đáp án:** 7 dòng vì bài không có tag vẫn có 1 dòng null; `count(DISTINCT a) = 5`. Có 6 quan hệ tag được match.

### Bài 4 — N+1

Service lấy 30 bài bằng một query rồi trong vòng lặp gọi query lấy tag của mỗi bài. Có bao nhiêu query theo cách đếm đơn giản, chưa tính COUNT?

**Đáp án:** **31 query**. Nếu dùng `Page` với count riêng có thể nhiều hơn; SDN có các query bổ sung tùy cách hydrate. Cách giảm N+1 là load tags cho toàn bộ 30 ID bằng một query batched.

### Bài 5 — Vì sao LIMIT sai?

Query `MATCH (a)-[:HAS_TAG]->(t) RETURN a,t LIMIT 10` có đảm bảo 10 bài khác nhau không?

**Đáp án:** không. LIMIT giới hạn **dòng**, không giới hạn số root `a` duy nhất; node có nhiều tag có thể lặp. Chọn root trước rồi mở rộng quan hệ và `collect`.

### Bài 6 — Cursor với ngày trùng

Trang đầu là A001/A002; cursor cuối trang là ngày 2026-10-05 và ID A002. Bài tiếp theo là gì?

**Đáp án:** A003 (cùng ngày nhưng ID lớn hơn A002), sau đó A004. Điều kiện phải kết hợp `publishedAt < lastDate` **hoặc** `publishedAt = lastDate AND articleId > lastId`.

### Bài 7 — Over-fetch không phải N+1

Một endpoint chỉ chạy một query nhưng trả 15.000 relationship cho 10 bài, dù API chỉ dùng tên và số tag. Đây có chắc là N+1?

**Đáp án:** không. Đây là **over-fetch**, dù query count thấp. Chọn scalar aggregation, DTO, hạn chế collection hoặc tách endpoint.

### Bài 8 — Count query sai

Data query chỉ trả 5 bài PUBLISHED, nhưng countQuery trả 6 vì đếm cả DRAFT. Có hợp lệ khi hiển thị totalElements = 6 không?

**Đáp án:** không. Count phải áp cùng điều kiện của data query, và khi mở rộng quan hệ phải đếm đúng node gốc. Với fixture, tổng PUBLISHED đúng là **5**.

## 17. Dọn dữ liệu thực hành

Chỉ chạy trên **database test** có chứa đúng fixture `QA010`:

~~~cypher
DROP INDEX qa010_article_feed IF EXISTS;
~~~

~~~cypher
DROP CONSTRAINT qa010_article_id_unique IF EXISTS;
~~~

~~~cypher
MATCH (n)
WHERE n:QA010Article OR n:QA010Tag OR n:QA010Author
DETACH DELETE n;
~~~

Kiểm tra:

~~~cypher
MATCH (n)
WHERE n:QA010Article OR n:QA010Tag OR n:QA010Author
RETURN count(n) AS remaining;
~~~

Đáp án: `remaining = 0`. Không chạy cleanup nếu các nhãn `QA010` bị dùng chung với dữ liệu thật. `DETACH DELETE` xóa cả relationship nối với node test.

## 18. Tài liệu tham khảo chính thức

- [Spring Data Neo4j — Reference](https://docs.spring.io/spring-data/neo4j/reference/): entity mapping, repositories, derived finders, projections và các phiên bản SDN.
- [Spring Data Neo4j — Custom queries](https://docs.spring.io/spring-data/neo4j/reference/appendix/custom-queries.html): record-per-root, `collect` các node/relationship, giới hạn ánh xạ path và shape của query.
- [Spring Data Neo4j — FAQ: custom mappings](https://docs.spring.io/spring-data/neo4j/reference/faq.html): sử dụng `Neo4jClient` và `mappedBy` cho read DTO không phải entity.
- [Spring Data Neo4j — Query Methods](https://docs.spring.io/spring-data/neo4j/reference/repositories/query-methods-details.html): `Pageable`, `Page`, `Slice`, sorting và chi phí count.
- [Neo4j Cypher Manual — ORDER BY](https://neo4j.com/docs/cypher-manual/current/clauses/order-by/): yêu cầu về thứ tự kết quả.
- [Neo4j Cypher Manual — SKIP](https://neo4j.com/docs/cypher-manual/current/clauses/skip/): offset pagination và giới hạn `SKIP`.
- [Neo4j Cypher Manual — Execution Plans](https://neo4j.com/docs/cypher-manual/current/planning-and-tuning/execution-plans/): `EXPLAIN`, `PROFILE`, Rows, DB Hits và bộ nhớ.
- [Neo4j Java Driver Manual — Performance](https://neo4j.com/docs/java-manual/current/performance/): connection pool, tham số hóa, đo latency và batch.

**Ghi nhớ:** trong Spring Data Neo4j, phân trang phải giới hạn **node gốc** với thứ tự ổn định trước khi mở rộng relationship. `Page` đem lại tổng chính xác khi cần, còn `Slice` giảm nhu cầu COUNT. Khi ứng dụng trả chậm, hãy phân biệt **N+1 query**, **mở rộng quan hệ tạo nhiều dòng** và **over-fetch graph**, rồi chọn DTO một query hoặc fetch hai pha theo batch thay vì truy vấn riêng từng node.
