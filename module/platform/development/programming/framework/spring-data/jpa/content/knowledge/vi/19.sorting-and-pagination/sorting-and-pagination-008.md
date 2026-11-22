# Vì sao phân trang với collection fetch join dễ sai hoặc tốn bộ nhớ trong Spring Data JPA

Phân trang thường được dùng để chỉ tải một phần dữ liệu, ví dụ 20 bài viết mỗi trang. Nhưng nếu query đồng thời fetch một collection như comments, orders hoặc lineItems, số dòng SQL có thể lớn hơn nhiều số entity gốc. Một bài viết có 10 comment tạo ra 10 dòng kết quả sau JOIN. Database áp dụng LIMIT/OFFSET trên các dòng đó, trong khi ứng dụng lại mong muốn giới hạn số Post.

Sự khác biệt giữa số dòng SQL và số entity gốc khiến phân trang với collection fetch join trở nên khó dự đoán. Hibernate thường phải bỏ phân trang ở database và phân trang trong bộ nhớ để không cắt mất collection; điều này có thể tải lượng dữ liệu rất lớn. Một số provider hoặc cấu hình có thể báo lỗi thay vì âm thầm thực hiện. Bài học này giải thích cơ chế, cách nhận diện rủi ro và các mẫu triển khai an toàn trong Spring Data JPA.

## 1. Fetch join khác JOIN thông thường thế nào?

JPQL JOIN dùng để kết hợp dữ liệu và lọc kết quả. JOIN FETCH còn yêu cầu JPA provider tải association cùng entity gốc trong truy vấn đó.

Ví dụ entity Post có nhiều Comment:

~~~java
@Entity
@Table(name = "posts")
public class Post {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String title;

    @OneToMany(mappedBy = "post", fetch = FetchType.LAZY)
    private List<Comment> comments = new ArrayList<>();
}
~~~

~~~java
@Entity
@Table(name = "comments")
public class Comment {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "post_id")
    private Post post;

    private String body;
}
~~~

Truy vấn JOIN thông thường:

~~~java
@Query("""
       select p
       from Post p
       join p.comments c
       where c.body like :keyword
       """)
List<Post> findPostsWithMatchingComments(
        @Param("keyword") String keyword);
~~~

Truy vấn này dùng comment để lọc Post. Nó không yêu cầu collection comments phải được khởi tạo đầy đủ trong kết quả.

Truy vấn fetch join:

~~~java
@Query("""
       select p
       from Post p
       left join fetch p.comments
       where p.status = :status
       """)
List<Post> findPostsWithComments(
        @Param("status") PostStatus status);
~~~

Ở đây Hibernate tải Post và collection comments cùng lúc. Sau khi truy vấn hoàn tất, collection của từng Post đã được khởi tạo trong persistence context.

Fetch join đặc biệt hữu ích để tránh N+1 khi biết chắc cần dùng association. Vấn đề xuất hiện khi kết hợp collection fetch join với setFirstResult/maxResults hoặc Pageable.

## 2. Vì sao JOIN collection làm nhân số dòng?

Giả sử có ba Post:

| Post | Số Comment |
|---|---:|
| Post A | 5 |
| Post B | 2 |
| Post C | 4 |

SQL JOIN tạo ra số dòng tương ứng với số phần tử collection:

~~~sql
SELECT p.id, p.title, c.id, c.body
FROM posts p
LEFT JOIN comments c ON c.post_id = p.id
ORDER BY p.id;
~~~

Kết quả có 11 dòng, dù chỉ có 3 Post. Post A lặp lại 5 lần, Post B lặp 2 lần và Post C lặp 4 lần.

Có thể hình dung:

~~~text
Post A + Comment 1
Post A + Comment 2
Post A + Comment 3
Post A + Comment 4
Post A + Comment 5
Post B + Comment 1
Post B + Comment 2
Post C + Comment 1
Post C + Comment 2
Post C + Comment 3
Post C + Comment 4
~~~

Đây là row multiplication: một entity gốc xuất hiện trên nhiều dòng kết quả SQL vì có nhiều phần tử ở collection được JOIN.

Nếu dùng JOIN nhiều collection, số dòng có thể tăng theo tích số phần tử. Ví dụ một Post có 5 comments và 3 tags có thể tạo 15 tổ hợp dòng cho Post đó. Điều này làm tăng dữ liệu truyền qua JDBC, thời gian hydrate entity và bộ nhớ.

## 3. LIMIT/OFFSET giới hạn dòng SQL, không phải số entity gốc

Khi repository nhận Pageable, Hibernate/JPA thường cần chuyển page size và offset thành giới hạn truy vấn database.

Giả sử query fetch Post và comments, page size là 3:

~~~sql
SELECT p.*, c.*
FROM posts p
LEFT JOIN comments c ON c.post_id = p.id
ORDER BY p.created_at DESC
LIMIT 3 OFFSET 0;
~~~

LIMIT 3 ở mức SQL chỉ lấy ba dòng JOIN. Nếu Post đầu tiên có ba comments, kết quả có thể chỉ chứa một Post. Nếu Post đầu tiên có năm comments, database chỉ trả một phần collection của Post đó.

Provider không thể coi ba dòng này là ba Post độc lập. Nếu chỉ trả một Post với một phần collection đã bị cắt, dữ liệu trong persistence context sẽ không phản ánh collection đầy đủ.

Do đó, phân trang collection fetch join có một vấn đề căn bản: page size được định nghĩa theo entity gốc, nhưng SQL row limit được áp dụng trên kết quả JOIN đã nhân dòng.

## 4. Hibernate có thể phân trang trong bộ nhớ

Với collection fetch join kết hợp giới hạn kết quả, Hibernate thường phát hiện rằng phân trang SQL có thể làm collection bị cắt. Để giữ collection đầy đủ, Hibernate có thể:

1. Chạy truy vấn JOIN mà không áp dụng LIMIT/OFFSET ở database.
2. Đọc và hydrate tất cả các dòng phù hợp.
3. Xây dựng các entity gốc và collection tương ứng trong persistence context.
4. Áp dụng offset/page size trong bộ nhớ.
5. Trả về các entity thuộc trang được yêu cầu.

Kết quả có thể đúng về mặt entity/collection nhưng chi phí rất lớn. Ví dụ query chỉ yêu cầu 20 Post có thể tải 200.000 dòng JOIN nếu dữ liệu phù hợp quá nhiều.

Hibernate 6 thường ghi cảnh báo có mã HHH90003004 khi gặp tình huống này, với thông điệp cho biết firstResult/maxResults được áp dụng trong bộ nhớ do collection fetch. Nội dung log cụ thể có thể thay đổi theo phiên bản.

Điều này gây ra:

- Tăng lượng dữ liệu truyền từ database tới ứng dụng.
- Tăng CPU để hydrate và khử trùng entity.
- Tăng heap usage và nguy cơ OutOfMemoryError.
- Thời gian phản hồi tăng theo tổng dữ liệu phù hợp, không chỉ theo page size.
- Pagination có vẻ chạy đúng ở dữ liệu nhỏ nhưng chậm rõ rệt khi production lớn.

Không nên suy luận rằng query an toàn chỉ vì kết quả trả về có đúng page size. Cần kiểm tra SQL, log Hibernate và số dòng thực sự được đọc.

## 5. JPA specification và tính không xác định

Jakarta Persistence specification quy định rằng việc dùng setFirstResult() hoặc setMaxResults() với truy vấn có collection fetch join có hành vi không được xác định (undefined).

Vì vậy, không nên dựa vào một kết quả cụ thể của provider khi phân trang collection fetch join. Hibernate có thể chọn in-memory pagination để bảo toàn collection; provider khác có thể có hành vi khác.

Spring Data JPA chỉ chuyển Pageable xuống tầng JPA. Pageable không tự giải quyết được vấn đề row multiplication của collection fetch join. Việc khai báo Page<T>, Slice<T> hay countQuery riêng cũng không làm cho content query trở nên an toàn nếu nó vẫn fetch collection trong cùng truy vấn phân trang.

## 6. Vì sao DISTINCT không giải quyết được vấn đề?

Một cách thường thử là thêm DISTINCT:

~~~java
@Query("""
       select distinct p
       from Post p
       left join fetch p.comments
       where p.status = :status
       """)
Page<Post> findDistinctPostsWithComments(
        @Param("status") PostStatus status,
        Pageable pageable);
~~~

DISTINCT có thể giúp kết quả entity không lặp lại cùng một Post ở tầng kết quả JPQL. Nhưng nó không đảm bảo SQL row limit tương ứng với số Post.

Khi các dòng chứa cột Comment khác nhau, database vẫn cần giữ các dòng đó để hydrate collection. DISTINCT trên toàn bộ cột được chọn không thể gộp các comment khác nhau thành một dòng mà vẫn giữ đầy đủ dữ liệu collection.

Do đó:

- DISTINCT có thể xử lý duplicate root trong kết quả query.
- DISTINCT không biến collection join thành quan hệ một-một.
- DISTINCT không bảo đảm database LIMIT/OFFSET giới hạn đúng số root entity.
- Hibernate vẫn có thể phải dùng in-memory pagination.

Đừng xem DISTINCT là giải pháp sửa collection fetch join với Pageable.

## 7. countQuery riêng cũng không sửa content query

Spring Data JPA cho phép khai báo countQuery:

~~~java
@Query(
    value = """
            select distinct p
            from Post p
            left join fetch p.comments
            where p.status = :status
            """,
    countQuery = """
            select count(p)
            from Post p
            where p.status = :status
            """
)
Page<Post> findPosts(
        @Param("status") PostStatus status,
        Pageable pageable);
~~~

countQuery riêng có thể giúp tính tổng số Post đúng và tránh count bị nhân dòng do JOIN. Tuy nhiên, content query vẫn là collection fetch join kết hợp Pageable, vì vậy rủi ro in-memory pagination vẫn còn.

Cần phân biệt hai vấn đề:

- Count query: tính tổng số entity phù hợp.
- Content query: lấy dữ liệu cho trang hiện tại.

Sửa countQuery chỉ xử lý vấn đề đếm. Muốn phân trang hiệu quả, content query cũng phải tránh giới hạn trực tiếp trên collection fetch join.

## 8. Cách an toàn: phân trang ID trước, fetch collection sau

Một mẫu phổ biến và dễ kiểm soát là chia thành hai truy vấn:

1. Query đầu chỉ chọn ID của các entity gốc và phân trang trên ID.
2. Query thứ hai fetch collection cho đúng tập ID của trang đó, không dùng Pageable.
3. Sắp xếp lại kết quả theo thứ tự ID của query đầu vì IN không bảo đảm thứ tự.

Luồng:

~~~mermaid
flowchart TD
    A[Nhận Pageable] --> B[Query 1: chọn Page ID của Post]
    B --> C[Database áp dụng LIMIT/OFFSET trên Post]
    C --> D[Query 2: fetch Post và comments theo ID]
    D --> E[Khôi phục thứ tự ID của trang]
    E --> F[Trả Page<Post> với total từ query 1]
~~~

### Repository

Query đầu không JOIN fetch collection:

~~~java
public interface PostRepository extends JpaRepository<Post, Long> {

    @Query(
        value = """
                select p.id
                from Post p
                where p.status = :status
                """,
        countQuery = """
                select count(p)
                from Post p
                where p.status = :status
                """
    )
    Page<Long> findPageIdsByStatus(
            @Param("status") PostStatus status,
            Pageable pageable);

    @Query("""
           select distinct p
           from Post p
           left join fetch p.comments
           where p.id in :ids
           """)
    List<Post> findAllWithCommentsByIdIn(
            @Param("ids") Collection<Long> ids);
}
~~~

Query đầu trả Page<Long>, vì vậy mỗi kết quả là một ID Post. Pageable áp dụng lên một dòng cho mỗi Post, không có collection join để nhân số dòng.

Query thứ hai lấy Post cùng comments cho các ID đã chọn. Truy vấn này không nhận Pageable nên không có giới hạn SQL cắt collection.

### Service giữ thứ tự trang

~~~java
@Service
public class PostQueryService {

    private final PostRepository repository;

    public PostQueryService(PostRepository repository) {
        this.repository = repository;
    }

    @Transactional(readOnly = true)
    public Page<Post> findPostsWithComments(
            PostStatus status,
            int pageNumber,
            int pageSize) {

        Pageable pageable = PageRequest.of(
                pageNumber,
                pageSize,
                Sort.by(Sort.Direction.DESC, "createdAt")
                        .and(Sort.by(Sort.Direction.DESC, "id"))
        );

        Page<Long> idPage =
                repository.findPageIdsByStatus(status, pageable);

        if (idPage.isEmpty()) {
            return new PageImpl<>(
                    List.of(),
                    pageable,
                    idPage.getTotalElements()
            );
        }

        List<Post> fetched =
                repository.findAllWithCommentsByIdIn(idPage.getContent());

        Map<Long, Post> byId = fetched.stream()
                .collect(Collectors.toMap(Post::getId, Function.identity()));

        List<Post> ordered = idPage.getContent().stream()
                .map(byId::get)
                .filter(Objects::nonNull)
                .toList();

        return new PageImpl<>(
                ordered,
                pageable,
                idPage.getTotalElements()
        );
    }
}
~~~

Các import chính của service:

~~~java
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.function.Function;
import java.util.stream.Collectors;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageImpl;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
~~~

Giải thích:

- Query đầu lấy đúng ID của trang và tổng số Post phù hợp.
- Query thứ hai fetch collection cho các ID đó.
- IN (:ids) không đảm bảo thứ tự kết quả, nên service dùng ID list ban đầu để khôi phục thứ tự.
- PageImpl nhận content đã sắp xếp, pageable và totalElements từ query đầu.
- @Transactional giữ cùng persistence context trong suốt hai truy vấn và quá trình xử lý association.
- page size nên được giới hạn hợp lý để tránh IN list quá lớn.

Trong ví dụ, Pageable dùng sort theo createdAt và id. ID là tie-breaker giúp thứ tự ổn định khi nhiều Post có cùng createdAt. Nếu ứng dụng nhận sort từ client, hãy whitelist các thuộc tính được phép và bảo đảm thứ tự có thêm khóa duy nhất.

Nếu một Post bị xóa giữa hai truy vấn bởi transaction khác, query thứ hai có thể không trả đủ ID. Ví dụ lọc null khi khôi phục thứ tự để tránh NullPointerException; nếu nghiệp vụ yêu cầu snapshot nhất quán tuyệt đối, cần cân nhắc isolation level hoặc cơ chế snapshot phù hợp với database.

## 9. Dùng Slice khi không cần tổng số bản ghi

Nếu UI chỉ cần nút "Trang tiếp theo" mà không cần tổng số trang, có thể phân trang ID bằng Slice:

~~~java
Slice<Long> findIdsByStatus(
        PostStatus status,
        Pageable pageable);
~~~

Spring Data có thể lấy thêm một phần tử để xác định hasNext(). Service thực hiện query fetch collection cho các ID trong content rồi khôi phục thứ tự tương tự ví dụ Page.

Slice không cần truy vấn tổng số bản ghi như Page trong nhiều trường hợp, nhưng vẫn phải tránh collection fetch join trong truy vấn content có Pageable. Đổi Page thành Slice không tự sửa row multiplication.

## 10. Lọc theo collection mà vẫn phân trang root entity

Đôi khi điều kiện lọc dựa trên collection, ví dụ tìm Post có ít nhất một Comment chứa từ khóa. Nếu JOIN collection trong query phân trang, root ID có thể bị lặp.

Có thể dùng EXISTS để lọc mà không đưa collection vào SELECT row set:

~~~java
@Query(
    value = """
            select p.id
            from Post p
            where p.status = :status
              and exists (
                  select c.id
                  from Comment c
                  where c.post = p
                    and lower(c.body) like lower(concat('%', :keyword, '%'))
              )
            """,
    countQuery = """
            select count(p)
            from Post p
            where p.status = :status
              and exists (
                  select c.id
                  from Comment c
                  where c.post = p
                    and lower(c.body) like lower(concat('%', :keyword, '%'))
              )
            """
)
Page<Long> findPageIdsWithMatchingComment(
        @Param("status") PostStatus status,
        @Param("keyword") String keyword,
        Pageable pageable);
~~~

EXISTS chỉ kiểm tra có ít nhất một comment phù hợp; nó không nhân một Post thành nhiều dòng trong kết quả ngoài. Sau đó vẫn dùng query thứ hai để fetch collection nếu cần.

Nếu query lọc bằng JOIN là cần thiết, dùng select distinct p.id và count(distinct p.id) khi phù hợp, nhưng phải kiểm tra query plan. EXISTS thường thể hiện đúng ý nghĩa "có ít nhất một phần tử" rõ hơn.

## 11. Batch fetching: giảm N+1 mà không fetch join toàn bộ collection

Một lựa chọn khác là để collection LAZY và cấu hình batch fetching. Khi truy cập collection của một nhóm Post, Hibernate tải nhiều collection bằng một số truy vấn IN thay vì một truy vấn cho mỗi Post.

Dùng annotation Hibernate:

~~~java
@OneToMany(mappedBy = "post", fetch = FetchType.LAZY)
@BatchSize(size = 50)
private List<Comment> comments = new ArrayList<>();
~~~

Hoặc cấu hình mặc định:

~~~properties
spring.jpa.properties.hibernate.default_batch_fetch_size=50
~~~

Batch size là số association/entity Hibernate cố gắng gom vào một batch; giá trị phù hợp cần đo theo page size, kích thước collection, giới hạn bind parameter và database.

Ưu điểm:

- Truy vấn phân trang root không cần fetch collection.
- Giảm số lượng query so với N+1.
- Không nhân dòng root trong truy vấn lấy trang.
- Chỉ tải collection khi ứng dụng thực sự truy cập.

Nhược điểm:

- Có thể phát sinh thêm query khi collection được truy cập.
- Nếu truy cập rất nhiều collection lớn, tổng dữ liệu vẫn có thể cao.
- Cần đo số batch và SQL thực tế.

Batch fetching là tính năng Hibernate; annotation @BatchSize và property cấu hình không thuộc JPA chuẩn.

## 12. SUBSELECT fetching và các giới hạn

Hibernate có chiến lược SUBSELECT cho collection:

~~~java
@OneToMany(mappedBy = "post", fetch = FetchType.LAZY)
@Fetch(FetchMode.SUBSELECT)
private List<Comment> comments = new ArrayList<>();
~~~

Khi collection được khởi tạo cho một nhóm owner đã tải, Hibernate có thể dùng một truy vấn phụ dựa trên tập owner để tải collection tương ứng.

Cách này có thể giảm N+1 khi một page chứa nhiều Post. Tuy nhiên:

- Đây là tính năng riêng của Hibernate.
- Query phụ có thể tải nhiều collection hơn dự kiến tùy cách owner được tải trong persistence context.
- Collection rất lớn vẫn tốn bộ nhớ.
- Cần kiểm tra SQL thực tế và tránh giả định nó luôn tối ưu.

Không dùng SUBSELECT như cách thay thế tự động cho thiết kế phân trang hai giai đoạn. Chọn chiến lược theo kích thước dữ liệu và pattern truy cập.

## 13. EntityGraph không tự động loại bỏ rủi ro

Spring Data JPA hỗ trợ @EntityGraph để chỉ định association cần tải:

~~~java
@EntityGraph(attributePaths = "comments")
Page<Post> findByStatus(PostStatus status, Pageable pageable);
~~~

EntityGraph mô tả fetch plan, nhưng provider quyết định cách thực hiện. Nếu Hibernate triển khai collection fetch bằng JOIN trong cùng truy vấn phân trang, vấn đề row multiplication vẫn xuất hiện.

Vì vậy:

- EntityGraph cho quan hệ to-one thường phù hợp với phân trang root hơn vì không làm nhân số root theo collection.
- EntityGraph có collection cần kiểm tra SQL và cảnh báo pagination.
- Không giả định EntityGraph là giải pháp an toàn cho collection fetch join.
- Với collection lớn, ưu tiên page ID rồi fetch riêng hoặc dùng batch fetching.

## 14. Fetch join to-one thường an toàn hơn

Quan hệ to-one như ManyToOne hoặc OneToOne có tối đa một đích cho mỗi entity gốc. Fetch join to-one thường không nhân số dòng root như collection.

Ví dụ:

~~~java
@Query("""
       select p
       from Post p
       join fetch p.author
       where p.status = :status
       """)
Page<Post> findPageWithAuthor(
        @Param("status") PostStatus status,
        Pageable pageable);
~~~

Nếu author là quan hệ to-one thực sự và mapping/database bảo đảm cardinality, mỗi Post vẫn tạo tối đa một dòng JOIN. Vì vậy, phân trang root thường có thể được thực hiện ở database.

Dù vậy, cần xem xét join type, dữ liệu và mapping thật. Nếu quan hệ được mô hình hóa sai cardinality hoặc query còn join collection khác, rủi ro vẫn có thể xuất hiện.

## 15. Khi chỉ cần dữ liệu tổng hợp, hãy dùng DTO projection

Không phải màn hình nào cũng cần tải toàn bộ collection. Nếu UI chỉ hiển thị Post cùng số comment, có thể query DTO và COUNT:

~~~java
public record PostCommentCount(
        Long postId,
        String title,
        Long commentCount
) {
}
~~~

~~~java
@Query(
    value = """
            select new com.example.post.PostCommentCount(
                p.id,
                p.title,
                count(c)
            )
            from Post p
            left join p.comments c
            where p.status = :status
            group by p.id, p.title
            order by p.id desc
            """,
    countQuery = """
            select count(p)
            from Post p
            where p.status = :status
            """
)
Page<PostCommentCount> findPostCommentCounts(
        @Param("status") PostStatus status,
        Pageable pageable);
~~~

Query này không fetch entity collection; database tổng hợp comment count theo Post. Vì SELECT trả một dòng nhóm cho mỗi Post, Pageable có thể giới hạn các nhóm theo page. Cần đảm bảo GROUP BY chứa các biểu thức không tổng hợp trong SELECT và countQuery đếm đúng số Post gốc.

DTO projection phù hợp với danh sách, dashboard hoặc API chỉ cần số liệu tóm tắt. Nếu sau đó người dùng mở chi tiết một Post, tải collection ở endpoint riêng.

## 16. Nhiều collection fetch join có thể còn tốn kém hơn

Fetch nhiều collection trong một query có thể tạo tích số dòng. Ví dụ:

~~~java
select distinct p
from Post p
left join fetch p.comments
left join fetch p.tags
~~~

Nếu một Post có 10 comments và 5 tags, query có thể tạo 50 tổ hợp dòng cho một Post. Điều này làm tăng dữ liệu lặp và chi phí hydrate.

Với nhiều bag collection (thường là List không có @OrderColumn), Hibernate còn có thể ném MultipleBagFetchException vì không thể fetch đồng thời nhiều bag theo cách đó.

Cách xử lý:

- Chỉ fetch collection cần thiết cho use case.
- Fetch một collection trong mỗi query và dùng persistence context để hợp nhất entity.
- Dùng batch fetching cho collection còn lại.
- Dùng DTO projection nếu chỉ cần tổng hợp.
- Tránh đổi List thành Set chỉ để né exception nếu điều đó làm sai semantics của domain.

## 17. Cấu hình Hibernate để phát hiện lỗi sớm

Hibernate có thể cảnh báo khi collection fetch join kết hợp pagination khiến nó phải phân trang trong bộ nhớ. Với phiên bản hỗ trợ, có thể yêu cầu fail thay vì chỉ cảnh báo:

~~~properties
spring.jpa.properties.hibernate.query.fail_on_pagination_over_collection_fetch=true
~~~

Khi bật, Hibernate ném exception nếu phát hiện pagination trên collection fetch. Điều này giúp lỗi được phát hiện trong development/test thay vì âm thầm gây tải lớn ở production.

Hãy xác minh property với phiên bản Hibernate đang dùng. Nếu ứng dụng nâng cấp Spring Boot/Hibernate, chạy lại integration test để xác nhận hành vi cảnh báo hoặc fail vẫn như mong đợi.

Có thể bật log SQL để kiểm tra:

~~~properties
spring.jpa.show-sql=true
spring.jpa.properties.hibernate.format_sql=true
logging.level.org.hibernate.SQL=DEBUG
~~~

Trong môi trường production, không nên bật log SQL chứa dữ liệu nhạy cảm một cách tùy tiện. Dùng logging có kiểm soát, metrics hoặc APM để quan sát số câu query và thời gian thực thi.

## 18. Kiểm thử hai giai đoạn phân trang

Một integration test nên tạo nhiều Post với số comments khác nhau, rồi xác nhận:

1. Query ID trả đúng số Post của trang.
2. Mỗi ID xuất hiện một lần.
3. Query fetch thứ hai tải đủ comments cho những Post được chọn.
4. Thứ tự trả về giữ đúng thứ tự của trang ID.
5. totalElements và totalPages vẫn lấy từ truy vấn đếm root.

Ví dụ test repository/service ở mức khái niệm:

~~~java
@DataJpaTest
class PostPaginationTest {

    @Autowired
    private PostRepository repository;

    @Autowired
    private TestEntityManager entityManager;

    @Test
    void pagesPostIdsBeforeFetchingComments() {
        Post first = persistPostWithComments("First", 5);
        Post second = persistPostWithComments("Second", 2);
        Post third = persistPostWithComments("Third", 4);

        entityManager.flush();
        entityManager.clear();

        Pageable pageable = PageRequest.of(
                0,
                2,
                Sort.by(Sort.Direction.DESC, "createdAt")
                        .and(Sort.by(Sort.Direction.DESC, "id"))
        );

        Page<Long> idPage =
                repository.findPageIdsByStatus(PostStatus.PUBLISHED, pageable);

        assertThat(idPage.getContent()).hasSize(2);
        assertThat(idPage.getTotalElements()).isEqualTo(3);

        List<Post> posts =
                repository.findAllWithCommentsByIdIn(idPage.getContent());

        assertThat(posts).hasSize(2);
        assertThat(posts)
                .allSatisfy(post ->
                        assertThat(post.getComments()).isNotNull());
    }

    private Post persistPostWithComments(String title, int count) {
        Post post = new Post(title, PostStatus.PUBLISHED, Instant.now());
        entityManager.persist(post);

        for (int i = 0; i < count; i++) {
            entityManager.persist(new Comment(post, "Comment " + i));
        }

        return post;
    }
}
~~~

Đây là khung test minh họa; constructor Post/Comment, repository mapping và import cần khớp với entity thực tế. Để kiểm tra collection đã được khởi tạo, có thể dùng PersistenceUnitUtil.isLoaded(post, "comments") hoặc Hibernate.isInitialized(post.getComments()) trước khi đóng persistence context.

Nếu cần xác nhận query đầu thực sự dùng LIMIT/OFFSET ở database và query thứ hai không có giới hạn, bật SQL logging trong test hoặc kiểm tra statement bằng datasource proxy. Chỉ kiểm tra kích thước List không chứng minh được SQL được tối ưu.

## 19. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Page chỉ có ít Post dù page size lớn | SQL LIMIT áp dụng trên dòng JOIN, không phải root entity | Phân trang ID trước rồi fetch collection |
| Hibernate log cảnh báo pagination trong memory | Collection fetch join đi cùng Pageable | Loại collection fetch khỏi query phân trang |
| Query chậm dù page size nhỏ | Hibernate phải tải toàn bộ dòng JOIN phù hợp | Dùng hai giai đoạn, batch fetching hoặc DTO |
| Heap tăng mạnh | Collection lớn và nhiều root được hydrate trước khi phân trang | Giới hạn truy vấn, batch và theo dõi heap |
| DISTINCT không giải quyết được cảnh báo | Child columns vẫn khác nhau và row multiplication còn nguyên | Không dựa vào DISTINCT để sửa pagination |
| countQuery đúng nhưng query vẫn chậm | Chỉ count query được sửa, content query vẫn fetch collection | Thiết kế lại content query |
| EntityGraph vẫn có cảnh báo | Provider thực hiện fetch collection bằng JOIN | Kiểm tra SQL, dùng batch hoặc hai query |
| Mất thứ tự sau query IN | SQL IN không bảo đảm thứ tự theo danh sách ID | Khôi phục thứ tự theo ID page |
| Nhiều collection làm số dòng tăng mạnh | Tích số giữa các collection | Fetch từng collection hoặc dùng batch/DTO |
| MultipleBagFetchException | Fetch đồng thời nhiều bag collection | Tách query hoặc thay chiến lược fetch |
| N+1 sau khi bỏ fetch join | Collection LAZY được truy cập từng entity | Dùng batch fetching hoặc fetch theo use case |
| Trang thay đổi giữa hai truy vấn | Dữ liệu bị sửa/xóa đồng thời | Chọn isolation và chính sách nhất quán phù hợp |

## 20. Nguyên tắc thiết kế thực tế

- Không kết hợp Pageable trực tiếp với collection fetch join khi cần phân trang entity gốc.
- Nhớ rằng SQL giới hạn dòng JOIN, không hiểu khái niệm page của root entity.
- Không coi DISTINCT hoặc countQuery riêng là cách khắc phục đầy đủ.
- Dùng query đầu phân trang ID/root entity, query sau fetch collection theo ID.
- Khôi phục thứ tự theo ID page vì IN không bảo đảm thứ tự.
- Giữ hai truy vấn trong transaction khi cần persistence context thống nhất.
- Thêm tie-breaker duy nhất vào sort để phân trang ổn định.
- Dùng EXISTS khi cần lọc root theo sự tồn tại của phần tử collection.
- Dùng batch fetching nếu muốn tránh N+1 mà không join toàn bộ collection.
- Dùng DTO projection khi chỉ cần số liệu tổng hợp.
- Fetch join to-one thường an toàn hơn collection fetch join, nhưng vẫn phải kiểm tra mapping.
- Bật fail_on_pagination_over_collection_fetch trong môi trường phát triển/test nếu Hibernate hỗ trợ.
- Đo SQL, số dòng, thời gian query và heap trên dữ liệu gần production.

## 21. Checklist tự đánh giá

- [ ] Phân biệt JOIN và JOIN FETCH.
- [ ] Giải thích được row multiplication khi fetch collection.
- [ ] Hiểu vì sao LIMIT/OFFSET ở SQL không tương ứng số root entity.
- [ ] Giải thích được vì sao Hibernate có thể phân trang trong bộ nhớ.
- [ ] Nhận biết cảnh báo HHH90003004 và property fail_on_pagination_over_collection_fetch.
- [ ] Hiểu vì sao JPA xem pagination với collection fetch join là undefined.
- [ ] Biết DISTINCT không loại bỏ vấn đề row limit.
- [ ] Biết countQuery riêng chỉ sửa việc đếm, không sửa content query.
- [ ] Triển khai được hai giai đoạn page ID rồi fetch collection.
- [ ] Khôi phục thứ tự kết quả sau truy vấn IN.
- [ ] Dùng EXISTS để lọc root theo collection mà không nhân dòng.
- [ ] Phân biệt batch fetching, SUBSELECT và EntityGraph.
- [ ] Biết khi nào DTO projection phù hợp hơn entity collection.
- [ ] Nhận diện tích số dòng khi fetch nhiều collection.
- [ ] Kiểm thử số entity, collection đầy đủ, thứ tự và SQL thực tế.

## 22. Kết luận

Collection fetch join nhân một entity gốc thành nhiều dòng SQL. Khi database áp dụng LIMIT/OFFSET trên các dòng đó, page size không còn tương ứng với số entity gốc và collection có nguy cơ bị cắt. Hibernate thường tránh kết quả sai bằng cách tải toàn bộ kết quả phù hợp rồi phân trang trong bộ nhớ, dẫn tới tiêu tốn thời gian và heap.

Cách an toàn phổ biến là phân trang ID của entity gốc trước, sau đó fetch collection cho đúng tập ID và khôi phục thứ tự trang. Với use case khác, batch fetching, EXISTS hoặc DTO projection có thể phù hợp hơn. Hãy kiểm tra SQL và bật cảnh báo/fail sớm để phát hiện collection fetch pagination trước khi dữ liệu lớn làm lộ vấn đề.
