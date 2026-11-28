# Full-text search qua Cypher và ánh xạ kết quả cùng điểm số

Ứng dụng thường cần tìm nội dung theo từ khóa trong tiêu đề, mô tả hoặc văn bản dài. Truy vấn `CONTAINS` hay so khớp chuỗi thông thường phù hợp với một số điều kiện đơn giản, nhưng không phân tích văn bản thành token và không xếp hạng kết quả theo mức độ liên quan. Neo4j cung cấp **full-text index** dựa trên Apache Lucene để tìm kiếm từ đã được phân tích và trả về `score` cho từng kết quả.

Trong Spring Data Neo4j, có thể gọi full-text search bằng Cypher rồi ánh xạ cả node và điểm số thành DTO. Bài học này sử dụng `SEARCH` clause của Cypher 25 làm cú pháp hiện hành, đồng thời trình bày procedure cũ để tương thích với Neo4j trước 2026.09 hoặc ứng dụng vẫn dùng Cypher 5.

## 1. Full-text index giải quyết vấn đề gì?

Full-text index lập chỉ mục các property kiểu `STRING` hoặc danh sách `STRING` trên node và relationship. Nếu property là danh sách chuỗi, từng phần tử được phân tích riêng và token vẫn gắn với property đó. Lucene phân tích nội dung thành token, nhờ đó truy vấn có thể tìm từ xuất hiện bên trong văn bản thay vì yêu cầu toàn bộ property bằng chuỗi đầu vào.

Ví dụ một bài viết có tiêu đề `Graph databases for recommendation systems` có thể được tìm bằng từ khóa `recommendation`, dù từ khóa không phải toàn bộ giá trị của `title`.

Phân biệt một số kiểu index:

| Kiểu index | Mục đích | Ví dụ phù hợp |
|---|---|---|
| Range index | Tìm theo giá trị, so sánh, prefix hoặc sắp xếp theo property | `status = 'PUBLISHED'`, `createdAt > ...` |
| Text index | Một số phép so khớp chuỗi như exact, prefix, contains hoặc suffix | Tìm chuỗi con theo property |
| Full-text index | Tìm kiếm từ đã tokenize, hỗ trợ cú pháp truy vấn Lucene và relevance score | Tìm bài viết theo từ khóa trong title, summary và content |

Full-text index không được Cypher planner tự động chọn như range index. Truy vấn phải chỉ rõ index thông qua `SEARCH` hoặc procedure full-text tương ứng. Kết quả có thêm điểm số liên quan để xếp hạng.

## 2. Tạo full-text index cho node

Giả sử ứng dụng có node `Article` với các property `title`, `summary` và `content`. Tạo một index có tên ổn định:

```cypher
CREATE FULLTEXT INDEX articleSearch IF NOT EXISTS
FOR (article:Article)
ON EACH [article.title, article.summary, article.content];
```

`ON EACH` cho phép một full-text index lập chỉ mục nhiều property. Node `Article` có ít nhất một property được lập chỉ mục sẽ tham gia index theo quy tắc của full-text index.

Tên index `articleSearch` sẽ được dùng khi truy vấn. Hãy đặt tên theo chức năng và quản lý câu lệnh tạo index trong migration/schema deployment của dự án. SDN không tự tạo full-text index chỉ vì entity có `@Node` hoặc một property dạng `String`.

Có thể cấu hình analyzer trong `OPTIONS`:

```cypher
CREATE FULLTEXT INDEX articleSearch IF NOT EXISTS
FOR (article:Article)
ON EACH [article.title, article.summary, article.content]
OPTIONS {
    indexConfig: {
        `fulltext.analyzer`: 'english'
    }
};
```

Ví dụ dùng analyzer `english` phù hợp khi văn bản chủ yếu là tiếng Anh và muốn analyzer xử lý stop words/ngôn ngữ đó. Nếu dữ liệu đa ngôn ngữ, cần chọn analyzer phù hợp với ngôn ngữ thực tế; không mặc định analyzer tiếng Anh cho nội dung tiếng Việt. Khi không chỉ định, Neo4j dùng analyzer mặc định `standard-no-stop-words`.

Danh sách analyzer có thể xem bằng:

```cypher
CALL db.index.fulltext.listAvailableAnalyzers();
```

Analyzer được áp dụng cho cả nội dung lúc lập chỉ mục và query string. Vì vậy, cùng một từ có thể được chuẩn hóa hoặc tách token theo quy tắc của analyzer.

## 3. Tạo full-text index cho relationship

Full-text search cũng áp dụng cho property trên relationship. Ví dụ ứng dụng lưu nội dung bình luận trong relationship `COMMENTED`:

```cypher
CREATE FULLTEXT INDEX commentMessageSearch IF NOT EXISTS
FOR ()-[comment:COMMENTED]-()
ON EACH [comment.message];
```

Index này tìm trong property `message` của relationship `COMMENTED`. Khi truy vấn, kết quả có thể gồm relationship và score:

```cypher
MATCH ()-[comment:COMMENTED]-()
SEARCH comment IN (
    FULLTEXT INDEX commentMessageSearch
    FOR $term
    LIMIT $limit
)
SCORE AS score
RETURN type(comment) AS relationshipType,
       comment.message AS message,
       score
ORDER BY score DESC;
```

Full-text node index và relationship index có cùng ý tưởng về tokenization và scoring, nhưng index name phải trỏ đúng loại entity đã được lập chỉ mục.

## 4. Kiểm tra trạng thái index trước khi truy vấn

Sau khi tạo, full-text index cần thời gian để populate. Trong lúc trạng thái là `POPULATING`, index chưa sẵn sàng để sử dụng. Kiểm tra bằng:

```cypher
SHOW FULLTEXT INDEXES;
```

Các cột hữu ích gồm `name`, `state`, `populationPercent`, `entityType`, `labelsOrTypes` và `properties`. Chỉ đưa truy vấn vào luồng sử dụng khi index có trạng thái `ONLINE`.

Nếu index chưa `ONLINE`, kiểm tra lỗi populate và quyền tạo index. Đừng nhầm việc câu lệnh `CREATE FULLTEXT INDEX` trả về thành công với việc index đã hoàn tất populate.

## 5. Truy vấn bằng SEARCH clause trong Cypher 25

Từ Neo4j 2026.09, cách được ưu tiên để truy vấn full-text index là `SEARCH` clause của Cypher 25:

```cypher
MATCH (article:Article)
SEARCH article IN (
    FULLTEXT INDEX articleSearch
    FOR $term
    LIMIT $limit
)
SCORE AS score
RETURN article, score
ORDER BY score DESC, article.slug ASC;
```

Các thành phần chính:

1. `MATCH (article:Article)` khai báo node variable sẽ được tìm kiếm.
2. `SEARCH article IN (...)` yêu cầu Neo4j tìm node qua full-text index.
3. `FULLTEXT INDEX articleSearch` chọn index đã tạo.
4. `FOR $term` truyền query string vào index.
5. `LIMIT $limit` giới hạn số kết quả được lấy từ full-text search.
6. `SCORE AS score` đặt tên cho điểm số liên quan được trả về.
7. `RETURN article, score` trả node cùng score để tầng ứng dụng ánh xạ.

Full-text index trả kết quả theo thứ tự score giảm dần. `ORDER BY score DESC` làm thứ tự rõ ràng trong query; thêm `article.slug` làm tiêu chí phụ để thứ tự ổn định khi hai kết quả có score bằng nhau.

Tham số `$term` và `$limit` cần được bind như tham số Cypher. Tên full-text index là thành phần schema trong câu lệnh và nên được giữ cố định trong query, không nối trực tiếp một chuỗi tùy ý từ request vào cú pháp Cypher.

## 6. Cú pháp tìm kiếm Lucene

Full-text query string được phân tích theo cú pháp Lucene. Một vài dạng phổ biến:

| Query string | Ý nghĩa |
|---|---|
| `graph database` | Tìm các token tương ứng với những từ trong query |
| `"graph database"` | Tìm cụm từ theo thứ tự token đã chỉ định |
| `graph AND database` | Yêu cầu cả hai term |
| `graph OR database` | Chấp nhận một trong hai term |
| `graph NOT legacy` | Loại kết quả chứa term bị phủ định theo cú pháp Lucene |
| `title:recommendation` | Giới hạn tìm kiếm vào property `title` nếu property đó thuộc index |
| `title:"graph database"` | Tìm cụm từ trong property `title` |

Ví dụ truy vấn cụm từ:

```cypher
MATCH (article:Article)
SEARCH article IN (
    FULLTEXT INDEX articleSearch
    FOR '"graph database"'
    LIMIT 20
)
SCORE AS score
RETURN article.title AS title, score;
```

Các analyzer phổ biến, bao gồm analyzer mặc định, thường chuẩn hóa token về chữ thường. Vì vậy, tìm kiếm full-text thường không phân biệt hoa/thường. Đây là tìm kiếm theo token đã phân tích, không phải so sánh chính xác toàn bộ property.

Nếu ứng dụng chỉ muốn ô tìm kiếm văn bản thông thường, hãy quyết định rõ có cho phép người dùng nhập cú pháp Lucene như `AND`, `OR`, dấu ngoặc kép và tiền tố property hay không. Parameter binding ngăn dữ liệu đầu vào trở thành cú pháp Cypher, nhưng query string vẫn được diễn giải theo ngôn ngữ Lucene.

## 7. Procedure cũ cho Neo4j trước 2026.09 hoặc Cypher 5

Với Neo4j trước 2026.09 hoặc ứng dụng dùng Cypher 5, có thể truy vấn bằng procedure:

```cypher
CALL db.index.fulltext.queryNodes(
    'articleSearch',
    $term,
    {limit: $limit}
)
YIELD node, score
RETURN node AS article, score
ORDER BY score DESC;
```

Procedure trả hai cột chính:

- `node`: node khớp truy vấn full-text.
- `score`: điểm số Lucene thể hiện mức độ liên quan của node với query string.

Có thể dùng procedure tương ứng cho relationship index:

```cypher
CALL db.index.fulltext.queryRelationships(
    'commentMessageSearch',
    $term,
    {limit: $limit}
)
YIELD relationship, score
RETURN relationship.message AS message, score
ORDER BY score DESC;
```

Lưu ý phiên bản: trong Cypher 25, `db.index.fulltext.queryNodes()` và `db.index.fulltext.queryRelationships()` đã bị deprecated từ Neo4j 2026.10 để chuyển sang `SEARCH`. Chúng vẫn là lựa chọn tương thích cho các phiên bản cũ và Cypher 5; với triển khai mới trên Cypher 25, ưu tiên `SEARCH`.

## 8. Entity Article trong Spring Data Neo4j

Tạo entity có các property được lập chỉ mục:

```java
import org.springframework.data.annotation.Version;
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;

@Node("Article")
public class Article {

    @Id
    private String slug;

    @Version
    private Long version;

    private String title;
    private String summary;
    private String content;

    protected Article() {
    }

    public Article(String slug, String title, String summary, String content) {
        this.slug = slug;
        this.title = title;
        this.summary = summary;
        this.content = content;
    }

    public String getSlug() {
        return slug;
    }

    public String getTitle() {
        return title;
    }

    public String getSummary() {
        return summary;
    }

    public String getContent() {
        return content;
    }
}
```

Ví dụ dùng `slug` làm ID do ứng dụng cấp. `@Version` kiểu `Long` giúp SDN nhận diện entity mới và kiểm soát cập nhật cạnh tranh. Field version để `null` trên object mới và do SDN quản lý; không tự gán version trong service.

## 9. Ánh xạ node và score bằng DTO projection

Kết quả full-text search có hai phần khác bản chất: entity `Article` và score được tính trong lúc truy vấn. Không nên thêm `score` thành property lưu trữ của entity chỉ để nhận kết quả tìm kiếm. Hãy dùng DTO riêng:

```java
public record ArticleSearchHit(
    String slug,
    String title,
    String summary,
    Double score
) {}
```

DTO giữ các trường cần hiển thị và score của lần tìm kiếm. Với DTO projection của Spring Data Neo4j, các property domain được lấy từ node; các property bổ sung như `score` được lấy từ record truy vấn. Tên property/alias phải khớp chính xác.

Khai báo repository:

```java
import java.util.List;

import org.springframework.data.neo4j.repository.Neo4jRepository;
import org.springframework.data.neo4j.repository.query.Query;
import org.springframework.data.repository.query.Param;
import org.springframework.transaction.annotation.Transactional;

public interface ArticleRepository extends Neo4jRepository<Article, String> {

    @Transactional(readOnly = true)
    @Query("""
        MATCH (article:Article)
        SEARCH article IN (
            FULLTEXT INDEX articleSearch
            FOR $term
            LIMIT $limit
        )
        SCORE AS score
        RETURN article, score
        ORDER BY score DESC, article.slug ASC
        """)
    List<ArticleSearchHit> searchByFullText(
        @Param("term") String term,
        @Param("limit") int limit
    );
}
```

`ArticleRepository` có domain type là `Article`, còn phương thức tìm kiếm trả về `ArticleSearchHit`. SDN dùng node `article` để ánh xạ các property domain và lấy `score` từ cột bổ sung trong record. Đặt tên `score` trong `SCORE AS score` trùng với component `score` của record.

Nếu repository cần tương thích Neo4j cũ/Cypher 5, thay phần query bằng procedure `db.index.fulltext.queryNodes(...) YIELD node, score` và trả `node AS article, score`. DTO projection vẫn theo nguyên tắc tên property và alias tương ứng.

## 10. Tự ánh xạ record bằng Neo4jClient

Khi muốn kiểm soát rõ từng cột kết quả hoặc không cần hydrate entity đầy đủ, có thể dùng `Neo4jClient`. Ví dụ này trả các trường phẳng thay vì trả node:

```java
import java.util.Collection;

import org.springframework.data.neo4j.core.Neo4jClient;
import org.springframework.stereotype.Repository;

@Repository
public class ArticleSearchDao {

    private final Neo4jClient neo4jClient;

    public ArticleSearchDao(Neo4jClient neo4jClient) {
        this.neo4jClient = neo4jClient;
    }

    public Collection<ArticleSearchHit> search(String term, int limit) {
        return neo4jClient.query("""
            MATCH (article:Article)
            SEARCH article IN (
                FULLTEXT INDEX articleSearch
                FOR $term
                LIMIT $limit
            )
            SCORE AS score
            RETURN article.slug AS slug,
                   article.title AS title,
                   article.summary AS summary,
                   score
            ORDER BY score DESC, slug ASC
            """)
            .bind(term).to("term")
            .bind(limit).to("limit")
            .fetchAs(ArticleSearchHit.class)
            .mappedBy((typeSystem, record) -> new ArticleSearchHit(
                record.get("slug").asString(),
                record.get("title").asString(),
                record.get("summary").isNull()
                    ? null
                    : record.get("summary").asString(),
                record.get("score").asDouble()
            ))
            .all();
    }
}
```

Ở cách này:

1. Cypher trả các cột `slug`, `title`, `summary` và `score`.
2. `.bind(...).to(...)` truyền tham số riêng khỏi chuỗi query.
3. `fetchAs(ArticleSearchHit.class)` khai báo kiểu kết quả.
4. `mappedBy(...)` đọc từng `Record` và tạo DTO.
5. `all()` thực thi query và trả collection kết quả.

`Neo4jClient` không tự biến các cột phẳng này thành entity graph. Ứng dụng chịu trách nhiệm ánh xạ alias, kiểu dữ liệu và null. Đây là lựa chọn phù hợp cho read model hoặc kết quả tổng hợp cần cấu trúc riêng.

## 11. Chọn DTO projection hay Neo4jClient?

| Nhu cầu | Lựa chọn phù hợp | Lý do |
|---|---|---|
| Trả entity cùng một vài giá trị tính toán như score | Repository `@Query` + DTO projection | SDN dùng domain mapping và lấy property bổ sung từ record |
| Chỉ trả một số cột cho màn hình tìm kiếm | `Neo4jClient` + DTO mapper | Kiểm soát chính xác cột, alias và null |
| Cần xử lý record phức tạp hoặc kết hợp nhiều loại dữ liệu | `Neo4jClient` | Tự kiểm soát toàn bộ mapping |
| Query trả entity đầy đủ theo domain model | Repository hoặc `Neo4jTemplate` | Tận dụng mapping metadata của SDN |

Không nên dùng `score` như một property của `Article` vì score phụ thuộc query string và index tại thời điểm tìm kiếm. Một article có thể có score khác nhau ở hai truy vấn khác nhau.

## 12. Phân trang và giới hạn kết quả

Full-text search thường cần trả về top kết quả thay vì toàn bộ node phù hợp. `SEARCH` clause hỗ trợ `SKIP`/`OFFSET` và `LIMIT` ngay trong phần chọn kết quả:

```cypher
MATCH (article:Article)
SEARCH article IN (
    FULLTEXT INDEX articleSearch
    FOR $term
    SKIP $offset
    LIMIT $pageSize
)
SCORE AS score
RETURN article, score
ORDER BY score DESC, article.slug ASC;
```

Với procedure cũ, truyền `skip` và `limit` trong options map:

```cypher
CALL db.index.fulltext.queryNodes(
    'articleSearch',
    $term,
    {skip: $offset, limit: $pageSize}
)
YIELD node, score
RETURN node AS article, score
ORDER BY score DESC;
```

Giới hạn kết quả ở phía full-text search giúp tránh tải một tập node quá lớn về ứng dụng. Khi phân trang sâu, cân nhắc chi phí của `SKIP` và yêu cầu ổn định thứ tự. Nếu nhiều kết quả có cùng score, thêm một property ổn định như `slug` vào `ORDER BY`.

## 13. Hiểu đúng relevance score

`score` là điểm liên quan do Lucene tính dựa trên query và nội dung đã được analyzer xử lý. Giá trị càng cao thường biểu thị kết quả phù hợp hơn trong tập kết quả của lần tìm kiếm đó.

Không diễn giải score như xác suất đúng hoặc phần trăm tương đồng. Score không bị giới hạn trong khoảng 0 đến 1 và không phải điểm chất lượng nghiệp vụ đã được chuẩn hóa.

Một số nguyên tắc khi sử dụng:

- Dùng score để sắp xếp kết quả trong cùng truy vấn full-text.
- Không so sánh trực tiếp score giữa hai query string khác nhau.
- Không mặc định score của hai index/analyzer khác nhau có cùng thang đo.
- Không so sánh raw full-text score với vector similarity score nếu chưa có bước chuẩn hóa/ranking riêng.
- Nếu kết hợp nhiều nguồn kết quả, hãy xếp hạng từng nguồn độc lập hoặc dùng thuật toán hợp nhất thứ hạng phù hợp.

Score hữu ích để xếp thứ tự và hiển thị mức độ phù hợp tương đối. Nếu giao diện cần nhãn như “rất phù hợp” hoặc “có thể liên quan”, hãy hiệu chỉnh ngưỡng dựa trên dữ liệu thực tế thay vì chọn ngưỡng tùy ý.

## 14. Cập nhật dữ liệu và eventual consistency

Mặc định, cập nhật full-text index được thực hiện đồng bộ trong quá trình commit transaction. Có thể cấu hình:

```cypher
CREATE FULLTEXT INDEX articleSearch IF NOT EXISTS
FOR (article:Article)
ON EACH [article.title, article.summary, article.content]
OPTIONS {
    indexConfig: {
        `fulltext.eventually_consistent`: true
    }
};
```

Khi `fulltext.eventually_consistent` bật, thay đổi index được áp dụng ở background thread sớm nhất có thể thay vì trong đường commit. Điều này có thể giảm chi phí cập nhật index trong transaction ghi, nhưng một tìm kiếm ngay sau khi ghi có thể chưa thấy nội dung vừa thay đổi.

Nếu cần chờ index cập nhật trong tác vụ kiểm thử hoặc quy trình đặc biệt, Neo4j cung cấp procedure `db.index.fulltext.awaitEventuallyConsistentIndexRefresh()`. Không gọi procedure này cho mọi request tìm kiếm thông thường; nó có thể chờ các cập nhật index đang pending.

Chỉ bật eventual consistency khi nghiệp vụ chấp nhận độ trễ tìm kiếm sau ghi. Nếu yêu cầu read-after-write nghiêm ngặt đối với kết quả full-text, giữ chế độ cập nhật đồng bộ mặc định hoặc thiết kế luồng chờ phù hợp.

## 15. Kiểm thử full-text search và mapping score

Integration test nên chạy trên Neo4j tương thích với cú pháp Cypher đang sử dụng và xác nhận index đã `ONLINE` trước khi kiểm tra kết quả.

Các trường hợp nên kiểm tra:

1. Tạo một số `Article` có title, summary và content khác nhau.
2. Tạo full-text index và chờ trạng thái `ONLINE`.
3. Tìm bằng một term có trong title và xác nhận article phù hợp xuất hiện.
4. Tìm bằng term chỉ có trong content để xác nhận tất cả property đã khai báo được lập chỉ mục.
5. Tìm bằng cụm từ có dấu ngoặc kép và kiểm tra hành vi phrase search.
6. Xác nhận kết quả được sắp xếp theo score giảm dần.
7. Xác nhận DTO nhận đúng `slug`, `title`, `summary` và `score`.
8. Kiểm tra property nullable được ánh xạ an toàn trong `Neo4jClient` mapper.
9. Kiểm tra `limit` và `skip` không trả quá số phần tử yêu cầu.
10. Nếu bật eventual consistency, kiểm tra độ trễ cập nhật index và chỉ chờ refresh trong test khi cần.
11. Nếu hỗ trợ procedure cũ, chạy riêng integration test trên phiên bản Neo4j/Cypher 5 tương ứng.

Không chỉ kiểm tra danh sách có phần tử. Hãy xác nhận node đúng, score là số hữu hạn, thứ tự xếp hạng đúng và DTO nhận đủ các trường mà API cần.

## 16. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Query không tìm thấy kết quả | Index chưa `ONLINE`, sai tên index hoặc property chưa được lập chỉ mục | Kiểm tra `SHOW FULLTEXT INDEXES`, label/type và danh sách property. |
| Nghĩ Cypher tự dùng full-text index | Full-text index không được planner tự động chọn | Gọi rõ `SEARCH` hoặc procedure full-text phù hợp phiên bản. |
| `SEARCH` không được nhận diện | Server/Cypher version chưa hỗ trợ Cypher 25 SEARCH | Dùng procedure tương thích với phiên bản cũ hoặc nâng cấp server/cấu hình Cypher. |
| Procedure full-text báo deprecated | Đang dùng Cypher 25 trên Neo4j 2026.10 trở lên | Chuyển sang `SEARCH ... FULLTEXT INDEX ... SCORE`. |
| DTO có score bằng null | Query không trả `score`, alias khác tên component hoặc DTO không khớp record | Dùng `SCORE AS score` và giữ alias `score` nhất quán. |
| DTO không nhận property node | Tên property trong DTO không khớp domain property hoặc query không trả node phù hợp | Trả node trong `RETURN` và đối chiếu tên property/alias. |
| Score bị hiểu như phần trăm | Diễn giải sai Lucene relevance score | Xem score là thứ hạng tương đối trong cùng kết quả tìm kiếm. |
| Search vừa ghi xong chưa thấy kết quả | Index cấu hình eventual consistency hoặc chưa populate xong | Kiểm tra cấu hình index và chờ refresh khi nghiệp vụ/test yêu cầu. |
| Kết quả phân trang thay đổi thứ tự khi score bằng nhau | Chỉ sort theo score | Thêm property ổn định làm tiêu chí phụ trong `ORDER BY`. |
| Query string làm tìm kiếm khác dự kiến | Người dùng nhập cú pháp Lucene như `AND`, dấu ngoặc kép hoặc property prefix | Quy định rõ chế độ tìm kiếm đơn giản hay cú pháp nâng cao; xử lý query string theo chính sách đó. |

## 17. Quy trình triển khai full-text search

1. Xác định label/type và các property văn bản cần tìm.
2. Tạo full-text index có tên ổn định bằng migration/schema deployment.
3. Chọn analyzer theo ngôn ngữ và đặc điểm nội dung; không mặc định dùng analyzer tiếng Anh cho mọi dữ liệu.
4. Kiểm tra index đã `ONLINE` bằng `SHOW FULLTEXT INDEXES`.
5. Với Neo4j 2026.09+ và Cypher 25, dùng `SEARCH ... FULLTEXT INDEX ... SCORE`; với phiên bản cũ/Cypher 5, dùng procedure tương thích.
6. Trả node cùng score trong Cypher để SDN có thể ánh xạ entity và DTO projection.
7. Dùng repository `@Query` + DTO projection khi cần entity properties cùng score; dùng `Neo4jClient` khi muốn map từng record thủ công.
8. Bind query string và limit bằng parameter; không nối đầu vào vào câu Cypher.
9. Giới hạn kết quả, sắp xếp score giảm dần và thêm tiêu chí phụ ổn định nếu cần.
10. Đánh giá score theo thứ hạng tương đối; không xem là xác suất và không so sánh trực tiếp với điểm của nguồn tìm kiếm khác.
11. Chỉ bật eventual consistency khi chấp nhận độ trễ cập nhật index.
12. Kiểm thử index state, kết quả, score, mapping, null và tương thích phiên bản Neo4j.

## 18. Ghi nhớ

Full-text index của Neo4j dùng Lucene để tìm kiếm token trong property `STRING` của node hoặc relationship và trả về relevance `score`. Index phải được tạo rõ ràng và được gọi tường minh trong Cypher. Với Neo4j 2026.09 trở lên sử dụng Cypher 25, ưu tiên `SEARCH ... FULLTEXT INDEX ... SCORE`; procedure `db.index.fulltext.queryNodes()` và `queryRelationships()` dành cho phiên bản trước hoặc Cypher 5 và đã deprecated trong Cypher 25 từ 2026.10.

Trong Spring Data Neo4j, có thể trả node cùng score rồi dùng DTO projection của repository để SDN ánh xạ property domain và cột bổ sung. Nếu cần kiểm soát từng cột, dùng `Neo4jClient.fetchAs(...).mappedBy(...)`. Giữ alias trùng tên component DTO, bind tham số riêng, giới hạn số kết quả và hiểu score là mức liên quan tương đối của cùng truy vấn. Hãy kiểm tra index đã `ONLINE`, lựa chọn analyzer phù hợp và cân nhắc eventual consistency trước khi đưa tìm kiếm vào production.

## Tài liệu tham khảo

- [Neo4j Cypher Manual – Full-text indexes](https://neo4j.com/docs/cypher-manual/current/indexes/search-indexes/full-text-indexes/)
- [Neo4j Cypher Manual – Search index syntax](https://neo4j.com/docs/cypher-manual/current/indexes/syntax/)
- [Neo4j Operations Manual – Built-in full-text procedures](https://neo4j.com/docs/operations-manual/current/procedures/built-in-procedures/)
- [Spring Data Neo4j – Projections](https://docs.spring.io/spring-data/neo4j/reference/projections/sdn-projections.html)
- [Spring Data Neo4j – Neo4jClient FAQ](https://docs.spring.io/spring-data/neo4j/reference/faq.html)
