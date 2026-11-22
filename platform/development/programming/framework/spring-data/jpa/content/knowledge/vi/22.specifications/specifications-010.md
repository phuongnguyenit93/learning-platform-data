# Tách điều kiện lọc khỏi fetch join và logic count query trong Spring Data JPA

Khi xây dựng danh sách có phân trang, một truy vấn thường phải giải quyết ba việc khác nhau: xác định entity nào phù hợp, tải những association nào để hiển thị và đếm tổng số entity phù hợp. Nếu gộp cả ba việc vào một JPQL query có collection fetch join, kết quả SQL có thể nhân dòng, count bị sai hoặc Hibernate phải phân trang trong bộ nhớ.

Thiết kế ổn định cần tách rõ:

- **Filter predicate:** quyết định entity gốc nào được chọn.
- **Fetch plan:** quyết định association nào cần tải cùng entity.
- **Count query:** đếm số entity gốc phù hợp với cùng điều kiện lọc.

Bài học này giải thích cách tách ba trách nhiệm đó bằng JPQL, @Query, countQuery, EXISTS, Specification và chiến lược tải dữ liệu hai giai đoạn. Ví dụ dùng Post và Comment, trong đó một Post có nhiều Comment.

## 1. Ba trách nhiệm của một truy vấn phân trang

Giả sử màn hình cần hiển thị các bài viết đã xuất bản, có ít nhất một bình luận được duyệt, sắp xếp theo thời điểm tạo mới nhất và hiển thị toàn bộ bình luận của từng bài.

Có ba câu hỏi độc lập:

1. **Lọc:** Post nào có status = PUBLISHED và có ít nhất một Comment approved?
2. **Tải dữ liệu:** Màn hình cần Post cùng comments, hay chỉ cần Post và số lượng comments?
3. **Đếm:** Tổng số Post thỏa điều kiện lọc là bao nhiêu?

Không nên nhầm JOIN dùng để lọc với JOIN FETCH dùng để tải association. JOIN tham gia biểu thức truy vấn và có thể tạo predicate; JOIN FETCH yêu cầu provider khởi tạo association của entity được chọn.

Một truy vấn phân trang có thể được Spring Data thực thi bằng hai SQL statement:

- Content query lấy dữ liệu của trang.
- Count query tính tổng số kết quả để tạo Page.

Count query phải giữ đúng ý nghĩa lọc của content query, nhưng không cần tải entity hoặc collection.

~~~mermaid
flowchart TD
    A[Pageable request] --> B[Filter predicate]
    B --> C[Content query: chọn root entity]
    B --> D[Count query: đếm root entity]
    C --> E[Fetch plan: tải association cần thiết]
    D --> F[totalElements]
    E --> G[Page response]
    F --> G
~~~

Nếu ba phần được thiết kế riêng, có thể tối ưu từng phần mà vẫn giữ kết quả nhất quán về mặt nghiệp vụ.

## 2. Mô hình ví dụ Post và Comment

Post có nhiều Comment. Đây là quan hệ to-many, vì vậy JOIN từ Post sang Comment có thể tạo nhiều dòng cho một Post.

Enum trạng thái:

~~~java
package com.example.post;

public enum PostStatus {
    DRAFT,
    PUBLISHED,
    ARCHIVED
}
~~~

Entity Post:

~~~java
package com.example.post;

import java.time.Instant;
import java.util.ArrayList;
import java.util.List;

import jakarta.persistence.*;

@Entity
@Table(name = "posts")
public class Post {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 200)
    private String title;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 20)
    private PostStatus status;

    @Column(nullable = false)
    private Instant createdAt;

    @OneToMany(mappedBy = "post", fetch = FetchType.LAZY)
    private List<Comment> comments = new ArrayList<>();

    protected Post() {
    }

    public Post(String title, PostStatus status, Instant createdAt) {
        this.title = title;
        this.status = status;
        this.createdAt = createdAt;
    }

    public Long getId() {
        return id;
    }

    public String getTitle() {
        return title;
    }

    public PostStatus getStatus() {
        return status;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }

    public List<Comment> getComments() {
        return comments;
    }
}
~~~

Entity Comment:

~~~java
package com.example.post;

import jakarta.persistence.*;

@Entity
@Table(name = "comments")
public class Comment {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "post_id", nullable = false)
    private Post post;

    @Column(nullable = false, length = 2000)
    private String body;

    @Column(nullable = false)
    private boolean approved;

    protected Comment() {
    }

    public Comment(Post post, String body, boolean approved) {
        this.post = post;
        this.body = body;
        this.approved = approved;
    }

    public Long getId() {
        return id;
    }

    public Post getPost() {
        return post;
    }

    public String getBody() {
        return body;
    }

    public boolean isApproved() {
        return approved;
    }
}
~~~

Các association comments được để LAZY. Entity không tự động tải toàn bộ bình luận mỗi khi truy vấn Post; repository/service chọn fetch plan theo use case.

## 3. Vì sao không nên gộp filter và collection fetch join?

Một truy vấn thường thấy:

~~~java
@Query("""
       select distinct p
       from Post p
       join fetch p.comments c
       where p.status = :status
         and c.approved = true
       """)
Page<Post> findPublishedPostsWithApprovedComments(
        @Param("status") PostStatus status,
        Pageable pageable);
~~~

Truy vấn này có nhiều vấn đề về ý nghĩa:

- JOIN FETCH vừa dùng để lọc Comment, vừa yêu cầu tải association.
- Điều kiện c.approved = true giới hạn các dòng Comment tham gia JOIN.
- Collection được khởi tạo có thể chỉ chứa các Comment khớp điều kiện, trong khi nghiệp vụ có thể muốn hiển thị toàn bộ comments của Post.
- Một Post có nhiều Comment approved tạo nhiều dòng SQL cho cùng Post.
- Pageable áp dụng trên query có collection fetch join có thể khiến Hibernate phân trang trong bộ nhớ hoặc provider xử lý không như mong đợi.

Nếu mục tiêu chỉ là chọn Post có ít nhất một Comment approved, hãy dùng EXISTS để lọc. Sau đó chọn riêng cách tải comments.

Một nguyên tắc quan trọng: điều kiện xác định entity gốc không nhất thiết phải dùng chính association được fetch. Có thể dùng subquery để lọc root entity, rồi tải toàn bộ association trong truy vấn khác.

## 4. Dùng EXISTS để lọc theo collection mà không nhân dòng root

EXISTS kiểm tra có ít nhất một dòng con thỏa điều kiện. Nó không đưa từng Comment vào tập kết quả ngoài, vì vậy mỗi Post vẫn được xét như một root entity.

JPQL:

~~~java
@Query("""
       select p
       from Post p
       where p.status = :status
         and exists (
             select c.id
             from Comment c
             where c.post = p
               and c.approved = true
         )
       """)
List<Post> findPostsWithAtLeastOneApprovedComment(
        @Param("status") PostStatus status);
~~~

Cách đọc:

1. Chọn Post.
2. Chỉ giữ Post có status bằng tham số.
3. Với mỗi Post, kiểm tra subquery có Comment liên kết và approved = true hay không.
4. EXISTS trả true khi tìm được ít nhất một dòng phù hợp.

Một Post có 1 hoặc 100 Comment approved vẫn chỉ tạo một kết quả Post trong query ngoài. Không cần DISTINCT để khử duplicate do collection join vì query ngoài không JOIN collection.

Có thể hình dung SQL tương đương:

~~~sql
SELECT p.*
FROM posts p
WHERE p.status = ?
  AND EXISTS (
      SELECT 1
      FROM comments c
      WHERE c.post_id = p.id
        AND c.approved = true
  );
~~~

EXISTS đặc biệt phù hợp với yêu cầu "có ít nhất một", "không có phần tử nào" hoặc "có phần tử thỏa điều kiện". Với yêu cầu phủ định, có thể dùng NOT EXISTS.

## 5. Content query và countQuery phải dùng cùng điều kiện lọc

Khi repository trả Page<T>, Spring Data cần tổng số kết quả. Với query phức tạp, khai báo countQuery tường minh để tránh framework suy luận sai từ content query.

~~~java
public interface PostRepository extends JpaRepository<Post, Long> {

    @Query(
        value = """
                select p
                from Post p
                where p.status = :status
                  and exists (
                      select c.id
                      from Comment c
                      where c.post = p
                        and c.approved = true
                  )
                order by p.createdAt desc, p.id desc
                """,
        countQuery = """
                select count(p)
                from Post p
                where p.status = :status
                  and exists (
                      select c.id
                      from Comment c
                      where c.post = p
                        and c.approved = true
                  )
                """
    )
    Page<Post> findPageWithApprovedComment(
            @Param("status") PostStatus status,
            Pageable pageable);
}
~~~

Hai query có cùng predicate:

- p.status = :status
- EXISTS Comment liên kết với p và approved = true

Content query chọn Post và sắp xếp; countQuery đếm Post phù hợp. Count query không có JOIN FETCH, không cần SELECT collection và không cần ORDER BY.

Nếu content query lọc thêm ngày, tenant, quyền truy cập, từ khóa hoặc trạng thái, countQuery phải phản ánh cùng các điều kiện đó. Nếu bỏ sót một predicate, Page có thể hiển thị đúng content nhưng totalElements sai.

### Count query không phải bản sao nguyên xi của content query

Count query có mục tiêu khác nên chỉ giữ phần cần để xác định tập root entity:

| Thành phần | Content query | Count query |
|---|---|---|
| SELECT | Entity, ID hoặc DTO | COUNT root |
| WHERE | Điều kiện lọc đầy đủ | Cùng điều kiện lọc |
| JOIN để lọc | Có nếu cần | Giữ nếu cần cho predicate |
| EXISTS | Có nếu cần | Giữ nếu cần cho predicate |
| JOIN FETCH | Có thể có với to-one hoặc query không phân trang | Không dùng |
| ORDER BY | Có khi cần thứ tự | Thường bỏ |
| Pageable limit/offset | Có | Không áp dụng như content |

Count query không cần tải association. Mục tiêu của nó là đếm số entity gốc thỏa điều kiện.

## 6. Vì sao count(p) có thể sai khi JOIN collection?

Xét truy vấn:

~~~java
select p
from Post p
join p.comments c
where c.approved = true
~~~

Nếu một Post có ba Comment approved, JOIN tạo ba dòng cho Post đó. Nếu dùng:

~~~java
select count(p)
from Post p
join p.comments c
where c.approved = true
~~~

kết quả đếm có thể là số dòng JOIN, không phải số Post duy nhất.

Có hai cách xử lý:

**Cách 1: EXISTS.** Nếu chỉ cần kiểm tra có Comment phù hợp, dùng EXISTS như phần trước. Khi đó query ngoài không nhân dòng, count(p) đếm đúng root.

**Cách 2: COUNT DISTINCT.** Nếu cần JOIN để lọc hoặc kết hợp điều kiện khác, đếm ID root khác nhau:

~~~java
@Query(
    value = """
            select distinct p
            from Post p
            join p.comments c
            where p.status = :status
              and c.approved = true
            """,
    countQuery = """
            select count(distinct p.id)
            from Post p
            join p.comments c
            where p.status = :status
              and c.approved = true
            """
)
Page<Post> findPageUsingCommentJoin(
        @Param("status") PostStatus status,
        Pageable pageable);
~~~

COUNT(DISTINCT p.id) đếm mỗi Post một lần. Content query dùng DISTINCT để kết quả root không lặp. Dù vậy, query này không fetch comments và vẫn có thể cần xử lý join cost; EXISTS thường rõ hơn khi mục tiêu chỉ là kiểm tra sự tồn tại.

Đừng dùng count(distinct p.id) một cách máy móc. Chọn count theo cardinality thực tế và predicate của truy vấn.

## 7. Tách filter predicate khỏi fetch plan

Filter predicate xác định Post nào được chọn. Fetch plan xác định association nào cần tải để sử dụng sau truy vấn.

Ví dụ một danh sách chỉ hiển thị title và tên tác giả có thể dùng projection; không cần tải comments. Một trang chi tiết Post có thể cần comments, nhưng chỉ tải sau khi người dùng mở chi tiết.

Các chiến lược:

- Query root không fetch collection: an toàn cho phân trang.
- Fetch join to-one: thường không nhân dòng root nếu mapping cardinality đúng.
- Fetch collection riêng sau khi đã phân trang ID: tải đúng association cần thiết.
- Batch fetching: giữ collection LAZY và tải theo nhóm khi truy cập.
- DTO projection: chỉ lấy dữ liệu màn hình cần, có thể tính count bằng aggregate.

Không nên đặt mọi association thành EAGER để tránh lazy loading. EAGER có thể làm nhiều query không cần thiết trở nên nặng và khó kiểm soát.

## 8. Phân trang ID trước, tải collection sau

Khi trang cần Post cùng toàn bộ comments, có thể dùng hai truy vấn:

1. Lấy Page<Long> ID của Post theo filter và sort.
2. Fetch Post cùng comments cho đúng tập ID đó, không dùng Pageable trong query fetch collection.
3. Khôi phục thứ tự ban đầu vì IN không đảm bảo thứ tự.

Repository:

~~~java
package com.example.post;

import java.util.Collection;
import java.util.List;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface PostRepository extends JpaRepository<Post, Long> {

    @Query(
        value = """
                select p.id
                from Post p
                where p.status = :status
                  and exists (
                      select c.id
                      from Comment c
                      where c.post = p
                        and c.approved = true
                  )
                order by p.createdAt desc, p.id desc
                """,
        countQuery = """
                select count(p)
                from Post p
                where p.status = :status
                  and exists (
                      select c.id
                      from Comment c
                      where c.post = p
                        and c.approved = true
                  )
                """
    )
    Page<Long> findPageIdsWithApprovedComment(
            @Param("status") PostStatus status,
            Pageable pageable);

    @Query("""
           select distinct p
           from Post p
           left join fetch p.comments
           where p.id in :ids
           """)
    List<Post> fetchPostsWithCommentsByIdIn(
            @Param("ids") Collection<Long> ids);
}
~~~

Query đầu chỉ chọn ID của root Post. Pageable giới hạn các Post trước khi collection được tải. Count query đếm Post theo cùng điều kiện EXISTS.

Query thứ hai fetch collection cho ID đã chọn. Không truyền Pageable vào method này; collection fetch join không bị SQL LIMIT/OFFSET cắt giữa các comment.

Service giữ thứ tự:

~~~java
package com.example.post;

import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.function.Function;
import java.util.stream.Collectors;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageImpl;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class PostQueryService {

    private final PostRepository repository;

    public PostQueryService(PostRepository repository) {
        this.repository = repository;
    }

    @Transactional(readOnly = true)
    public Page<Post> findPageWithComments(
            PostStatus status,
            int pageNumber,
            int pageSize) {

        Pageable pageable = PageRequest.of(pageNumber, pageSize);

        Page<Long> idPage =
                repository.findPageIdsWithApprovedComment(status, pageable);

        if (idPage.isEmpty()) {
            return new PageImpl<>(
                    List.of(),
                    pageable,
                    idPage.getTotalElements()
            );
        }

        List<Post> fetched =
                repository.fetchPostsWithCommentsByIdIn(idPage.getContent());

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

Vì query ID có ORDER BY p.createdAt desc, p.id desc, thứ tự ID của trang đã xác định. Query IN không đảm bảo giữ thứ tự đó; service dựng Map theo ID rồi tạo lại danh sách theo idPage.getContent().

Hai truy vấn chạy trong cùng transaction readOnly để giữ persistence context trong suốt quá trình tải và xử lý. readOnly = true là gợi ý tối ưu cho transaction đọc; nó không tự tạo snapshot nhất quán tuyệt đối ở mọi isolation level.

Nếu Post bị xóa giữa hai truy vấn bởi transaction khác, danh sách fetch có thể ít hơn ID page. Ví dụ lọc null giúp tránh lỗi khi dựng thứ tự, nhưng totalElements vẫn phản ánh kết quả count ở truy vấn đầu. Nếu nghiệp vụ cần snapshot nhất quán, phải chọn isolation level hoặc chiến lược khóa phù hợp database.

## 9. Tại sao cần thứ tự ổn định khi phân trang?

Phân trang dựa trên offset cần một thứ tự xác định. Nếu chỉ ORDER BY createdAt và nhiều Post có cùng thời điểm, database có thể trả các dòng cùng giá trị theo thứ tự khác nhau giữa các lần gọi.

Nên thêm khóa duy nhất làm tie-breaker:

~~~java
order by p.createdAt desc, p.id desc
~~~

Điều này giúp các trang ít bị trùng hoặc bỏ sót do thứ tự không xác định. Tuy nhiên, offset pagination vẫn có thể dịch chuyển khi dữ liệu mới được thêm hoặc xóa ở đầu danh sách giữa hai lần tải trang.

Nếu dữ liệu thay đổi liên tục và cần duyệt ổn định, cân nhắc keyset scrolling hoặc cursor pagination. Khi đó điều kiện tiếp theo dựa trên cặp sort key cuối cùng, ví dụ createdAt và id, thay vì offset.

## 10. Specification: tái sử dụng filter mà không nhét fetch join vào đó

Spring Data JPA Specification phù hợp với điều kiện lọc động. Có thể tạo Specification cho status và điều kiện EXISTS, rồi dùng nó để lấy Page root entity.

Ví dụ filter theo status:

~~~java
package com.example.post;

import org.springframework.data.jpa.domain.Specification;

public final class PostSpecifications {

    private PostSpecifications() {
    }

    public static Specification<Post> hasStatus(PostStatus status) {
        return (root, query, cb) ->
                status == null
                        ? cb.conjunction()
                        : cb.equal(root.get("status"), status);
    }
}
~~~

Specification trên chỉ tạo predicate, không gọi root.fetch(). Có thể kết hợp:

~~~java
Specification<Post> spec =
        PostSpecifications.hasStatus(PostStatus.PUBLISHED);

Page<Post> page = repository.findAll(
        spec,
        PageRequest.of(0, 20)
);
~~~

Repository cần kế thừa JpaSpecificationExecutor:

~~~java
public interface PostRepository
        extends JpaRepository<Post, Long>,
                JpaSpecificationExecutor<Post> {
}
~~~

Khi dùng Specification với Page, Spring Data dùng predicate để tạo content query và count query. Nếu Specification chứa fetch join collection, count query có thể bị lỗi hoặc tạo SQL không phù hợp vì count query không phải truy vấn tải entity graph.

Giữ Specification tập trung vào filter predicate. Fetch association ở query riêng hoặc dùng cơ chế fetch plan phù hợp sau khi đã xác định root page.

### EXISTS trong Specification

Có thể tạo predicate EXISTS bằng Criteria API:

~~~java
public static Specification<Post> hasApprovedComment() {
    return (root, query, cb) -> {
        var subquery = query.subquery(Long.class);
        var comment = subquery.from(Comment.class);

        subquery.select(comment.get("id"))
                .where(
                    cb.equal(comment.get("post"), root),
                    cb.isTrue(comment.get("approved"))
                );

        return cb.exists(subquery);
    };
}
~~~

Kết hợp:

~~~java
Specification<Post> spec = Specification
        .where(PostSpecifications.hasStatus(PostStatus.PUBLISHED))
        .and(PostSpecifications.hasApprovedComment());
~~~

Đây là filter-only Specification. Không thêm root.fetch("comments") vào cùng Specification dùng cho Page.

## 11. Không dùng một Specification fetch join cho cả content và count

Một anti-pattern là thêm fetch vào Specification:

~~~java
// Không nên dùng chung cho Page nếu fetch collection.
return (root, query, cb) -> {
    root.fetch("comments", JoinType.LEFT);
    return cb.equal(root.get("status"), status);
};
~~~

Lý do:

- Specification có thể được gọi cho content query và count query.
- Count query chọn COUNT, không cần collection.
- Fetch join không hợp lệ trong nhiều count query và có thể làm Hibernate báo lỗi.
- Nếu provider cho phép, fetch collection có thể nhân dòng và khiến pagination phải xử lý trong bộ nhớ.
- Cùng một Specification bị gắn cả điều kiện lọc lẫn chiến lược tải dữ liệu, khó tái sử dụng.

Một số đội dùng kiểm tra query.getResultType() để chỉ thêm fetch khi result type không phải Long. Cách này phụ thuộc cách Spring Data/provider tạo count query và dễ mong manh khi thay đổi phiên bản. Thiết kế filter Specification riêng, fetch riêng thường rõ ràng hơn.

## 12. JOIN to-one và collection có tác động khác nhau

Quan hệ to-one như ManyToOne hoặc OneToOne có tối đa một đối tượng liên quan cho mỗi root entity. Fetch join to-one thường không nhân số dòng root nếu mapping và constraint phản ánh đúng cardinality.

Ví dụ Post có Author:

~~~java
@ManyToOne(fetch = FetchType.LAZY)
@JoinColumn(name = "author_id")
private Author author;
~~~

Query phân trang có thể fetch author:

~~~java
@Query(
    value = """
            select p
            from Post p
            join fetch p.author
            where p.status = :status
            order by p.createdAt desc, p.id desc
            """,
    countQuery = """
            select count(p)
            from Post p
            where p.status = :status
            """
)
Page<Post> findPageWithAuthor(
        @Param("status") PostStatus status,
        Pageable pageable);
~~~

Count query bỏ fetch join vì author không tham gia điều kiện lọc. Nếu filter theo thuộc tính author, count query cần giữ predicate tương ứng, nhưng không cần fetch author.

Ngược lại, collection như comments có nhiều phần tử và làm nhân dòng. Vì vậy, không áp dụng cùng một quyết định fetch cho to-one và to-many.

## 13. @EntityGraph không tự giải quyết count query

Spring Data JPA hỗ trợ @EntityGraph để khai báo association cần tải:

~~~java
@EntityGraph(attributePaths = "comments")
Page<Post> findByStatus(PostStatus status, Pageable pageable);
~~~

EntityGraph mô tả fetch plan, nhưng provider quyết định cách tải association. Nếu collection được tải bằng JOIN trong content query phân trang, row multiplication và in-memory pagination vẫn có thể xảy ra.

Cần nhớ:

- EntityGraph to-one thường ít rủi ro hơn.
- EntityGraph collection cần kiểm tra SQL và cảnh báo Hibernate.
- Count query không cần tải collection.
- Không coi EntityGraph là cách thay thế cho tách filter và fetch.
- Nếu collection lớn, dùng ID page rồi fetch riêng hoặc batch fetching.

Với Page query có EntityGraph, hãy bật SQL logging trong test để kiểm tra content query và count query được thực hiện như thế nào.

## 14. Batch fetching khi không muốn query fetch collection riêng

Một cách khác là để collection LAZY và cấu hình Hibernate tải theo batch khi code truy cập collection.

~~~java
@OneToMany(mappedBy = "post", fetch = FetchType.LAZY)
@BatchSize(size = 32)
private List<Comment> comments = new ArrayList<>();
~~~

Hoặc cấu hình mặc định:

~~~properties
spring.jpa.properties.hibernate.default_batch_fetch_size=32
~~~

Khi một nhóm Post đã được tải, Hibernate có thể gom các collection cần khởi tạo vào một số truy vấn IN thay vì phát sinh một query cho từng Post.

Ưu điểm:

- Query phân trang root không fetch collection.
- Giảm N+1 khi nhiều collection được truy cập.
- Không cần viết truy vấn fetch collection thủ công cho mọi use case.

Giới hạn:

- @BatchSize và default_batch_fetch_size là tính năng Hibernate, không phải JPA chuẩn.
- Collection rất lớn vẫn có thể tốn bộ nhớ.
- Batch size phù hợp phụ thuộc page size, số bind parameter và database.
- Cần đo SQL và số query thực tế.

Batch fetching là fetch strategy; nó không thay đổi điều kiện lọc hoặc logic count query.

## 15. Khi chỉ cần số lượng association, dùng aggregate projection

Nếu màn hình chỉ cần tiêu đề Post và số lượng Comment, không cần tải toàn bộ collection.

DTO:

~~~java
package com.example.post;

public record PostCommentCount(
        Long postId,
        String title,
        Long commentCount
) {
}
~~~

Repository:

~~~java
@Query(
    value = """
            select new com.example.post.PostCommentCount(
                p.id,
                p.title,
                count(c.id)
            )
            from Post p
            left join p.comments c
            where p.status = :status
            group by p.id, p.title
            order by p.createdAt desc, p.id desc
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

LEFT JOIN giữ Post không có Comment; count(c.id) bằng 0 cho nhóm không có Comment. Query tạo một nhóm cho mỗi Post, nên content page trả DTO thay vì entity có collection fetch.

Count query đếm Post theo status, không JOIN comments. Không cần COUNT DISTINCT vì count query không có join to-many.

Nếu lọc theo Comment, thêm cùng predicate vào cả content query và count query. Nếu dùng JOIN to-many trong content query, hãy cân nhắc EXISTS hoặc count distinct root để không đếm dòng join.

## 16. Page, Slice và count query

Page<T> cung cấp:

- Content của trang hiện tại.
- Số phần tử tổng cộng.
- Tổng số trang.
- Thông tin trang và kích thước.

Để biết tổng số, Spring Data thường cần count query. Framework có thể tối ưu một số trường hợp khi có thể suy ra tổng số từ content, nhưng không nên dựa vào điều đó để bỏ qua thiết kế count query chính xác.

Slice<T> cung cấp content và thông tin có trang tiếp theo hay không; thường không cần đếm toàn bộ kết quả. Nếu giao diện không cần totalElements/totalPages, Slice có thể giảm chi phí.

Tuy nhiên, đổi Page thành Slice không tự sửa collection fetch join với Pageable. Content query vẫn cần tránh phân trang trực tiếp trên collection fetch.

Với truy vấn ID hai giai đoạn, Page<Long> dùng count query để biết tổng root entity. Nếu chỉ cần Slice<Long>, có thể tránh count; query fetch collection thứ hai vẫn lấy đúng ID của window hiện tại.

## 17. Optional filter và count query

Một query có nhiều bộ lọc tùy chọn phải giữ cùng logic trong content và count.

Ví dụ tìm Post theo status và keyword có thể null:

~~~java
@Query(
    value = """
            select p
            from Post p
            where (:status is null or p.status = :status)
              and (:keyword is null
                   or lower(p.title) like lower(concat('%', :keyword, '%')))
            order by p.createdAt desc, p.id desc
            """,
    countQuery = """
            select count(p)
            from Post p
            where (:status is null or p.status = :status)
              and (:keyword is null
                   or lower(p.title) like lower(concat('%', :keyword, '%')))
            """
)
Page<Post> search(
        @Param("status") PostStatus status,
        @Param("keyword") String keyword,
        Pageable pageable);
~~~

Hai query có cùng điều kiện optional. Nếu content query có keyword nhưng count query quên keyword, Page.totalElements sẽ lớn hơn số bản ghi thực sự khớp.

Cũng cần định nghĩa rõ null và chuỗi rỗng. Với biểu thức :keyword is null or ..., chuỗi rỗng không null và tạo mẫu %%, thường khớp mọi title không null. Có thể chuẩn hóa blank thành null ở service nếu đó là hợp đồng API.

Nếu LIKE cho phép người dùng tìm ký tự % hoặc _, cần escape wildcard theo quy tắc của Spring Data/database. Việc bind parameter chống SQL injection nhưng không tự biến wildcard thành ký tự literal.

## 18. Count query với DISTINCT và GROUP BY

Khi content query có JOIN to-many, cần đếm root entity duy nhất:

~~~java
@Query(
    value = """
            select distinct p
            from Post p
            join p.comments c
            where c.approved = true
            """,
    countQuery = """
            select count(distinct p.id)
            from Post p
            join p.comments c
            where c.approved = true
            """
)
Page<Post> findDistinctPostsWithApprovedComments(Pageable pageable);
~~~

Nếu content query GROUP BY để trả DTO, count query không nhất thiết phải sao chép toàn bộ phép tổng hợp. Nó phải đếm số nhóm kết quả tương ứng. Với nhóm theo một root entity, có thể đếm root thỏa điều kiện bằng query riêng đơn giản hơn. Với nhóm phức tạp theo nhiều dimension, cần thiết kế count query tương ứng hoặc dùng Slice nếu không cần tổng số.

Không dùng count(p) khi JOIN tạo nhiều dòng cho cùng p. Không dùng count(distinct p.id) nếu query ngoài không có join nhân dòng và count(p) đã diễn đạt đúng; chọn biểu thức đơn giản nhất vẫn đúng cardinality.

## 19. Native query và countQuery

Với native SQL, Spring Data thường cần countQuery riêng cho Page nếu không thể suy ra an toàn từ câu SQL gốc.

~~~java
@Query(
    value = """
            select p.*
            from posts p
            where p.status = :status
            order by p.created_at desc, p.id desc
            """,
    countQuery = """
            select count(*)
            from posts p
            where p.status = :status
            """,
    nativeQuery = true
)
Page<Post> findNativePageByStatus(
        @Param("status") String status,
        Pageable pageable);
~~~

Native query dùng tên bảng và cột vật lý, không dùng entity property. Count query phải dùng cùng filter và trả một giá trị đếm phù hợp. Nếu native content query join collection, count query cần đếm root ID distinct hoặc dùng EXISTS.

Cú pháp native pagination và cách bind sort phụ thuộc database/provider và phiên bản Spring Data. Kiểm thử trên hệ quản trị thật; không giả định H2 sẽ tái hiện mọi hành vi production.

## 20. Kiểm thử content và count query cùng nhau

Một test cần xác nhận cả content lẫn totalElements. Nếu chỉ kiểm tra content, lỗi count query có thể không được phát hiện.

Ví dụ repository test:

~~~java
package com.example.post;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.Instant;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;

@DataJpaTest
class PostRepositoryTest {

    @Autowired
    private PostRepository repository;

    @Autowired
    private TestEntityManager entityManager;

    @Test
    void contentAndCountUseTheSameFilter() {
        Post first = new Post(
                "First", PostStatus.PUBLISHED,
                Instant.parse("2026-01-03T10:00:00Z"));
        Post second = new Post(
                "Second", PostStatus.PUBLISHED,
                Instant.parse("2026-01-02T10:00:00Z"));
        Post draft = new Post(
                "Draft", PostStatus.DRAFT,
                Instant.parse("2026-01-01T10:00:00Z"));

        entityManager.persist(first);
        entityManager.persist(second);
        entityManager.persist(draft);

        entityManager.persist(new Comment(first, "Approved", true));
        entityManager.persist(new Comment(first, "Another approved", true));
        entityManager.persist(new Comment(second, "Approved", true));
        entityManager.persist(new Comment(draft, "Approved", true));

        entityManager.flush();
        entityManager.clear();

        Page<Post> page = repository.findPageWithApprovedComment(
                PostStatus.PUBLISHED,
                PageRequest.of(0, 1));

        assertThat(page.getContent()).hasSize(1);
        assertThat(page.getTotalElements()).isEqualTo(2);
        assertThat(page.getTotalPages()).isEqualTo(2);
    }
}
~~~

Test có hai Post PUBLISHED phù hợp nhưng một Post có hai Comment approved. Kết quả mong đợi là totalElements bằng 2, không phải 3. Draft có Comment approved nhưng không được tính vì status không phù hợp.

Để xác minh fetch plan, thêm test cho query fetch riêng và kiểm tra collection đã được tải trước khi persistence context đóng. Có thể dùng PersistenceUnitUtil.isLoaded(post, "comments") hoặc Hibernate.isInitialized(post.getComments()).

Nếu muốn xác nhận count query thực sự chạy và SQL không có fetch join, bật SQL logging trong test hoặc dùng datasource proxy để đếm statement. Không chỉ suy luận từ kết quả Java.

## 21. Quan sát SQL và cảnh báo Hibernate

Khi tối ưu query phân trang, cần kiểm tra SQL thực tế thay vì chỉ nhìn JPQL.

Có thể bật log trong môi trường phát triển/test:

~~~properties
spring.jpa.show-sql=true
spring.jpa.properties.hibernate.format_sql=true
logging.level.org.hibernate.SQL=DEBUG
~~~

Kiểm tra:

- Content query có LIMIT/OFFSET ở database hay không.
- Có collection JOIN/FETCH trong query phân trang không.
- Count query có cùng WHERE predicate không.
- Count query có JOIN to-many gây nhân dòng không.
- Có DISTINCT cần thiết không.
- Query có ORDER BY ổn định không.
- Query thứ hai của chiến lược ID có tải đúng collection không.
- Số dòng trả về và số entity root có chênh lệch lớn không.

Hibernate có thể cảnh báo khi phải phân trang trong bộ nhớ do collection fetch. Với phiên bản hỗ trợ, cấu hình sau yêu cầu fail thay vì chỉ cảnh báo:

~~~properties
spring.jpa.properties.hibernate.query.fail_on_pagination_over_collection_fetch=true
~~~

Property này hữu ích để phát hiện sớm query collection fetch kết hợp pagination. Hãy xác minh theo phiên bản Hibernate trong dự án. Không bật SQL logging chứa dữ liệu nhạy cảm một cách tùy tiện ở production.

## 22. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| totalElements lớn hơn số root entity | Count query đếm dòng JOIN to-many | Dùng EXISTS hoặc count distinct root ID |
| Content đúng nhưng totalElements sai | Content và count có predicate khác nhau | Đồng bộ WHERE giữa hai query |
| Count query lỗi khi có fetch join | Count query không được phép tải association như content | Loại FETCH khỏi countQuery |
| Page nhỏ nhưng query rất chậm | Hibernate phân trang trong bộ nhớ do collection fetch | Phân trang ID trước rồi fetch collection |
| Collection chỉ chứa phần tử thỏa filter | Alias collection vừa lọc vừa fetch | Dùng EXISTS để lọc root, fetch toàn bộ collection riêng |
| DISTINCT không giảm chi phí như mong đợi | Child columns vẫn tạo nhiều dòng SQL | Không dùng DISTINCT thay cho tách fetch |
| @EntityGraph vẫn tạo join collection | Provider thực thi fetch plan bằng JOIN | Kiểm tra SQL, batch fetch hoặc hai query |
| Specification count query bị lỗi | Specification chứa root.fetch() | Giữ Specification chỉ có predicate |
| Count query quên filter optional | Chỉ sửa content query | Duy trì cùng predicate hoặc tái sử dụng filter logic |
| Page sort không ổn định | Sort thiếu tie-breaker duy nhất | Thêm ID vào ORDER BY |
| Query IN trả sai thứ tự mong muốn | IN không đảm bảo thứ tự | Khôi phục thứ tự theo danh sách ID |
| Count query native sai dialect | Dùng tên property thay tên cột hoặc SQL không tương thích | Viết theo schema/dialect và test database thật |

## 23. Nguyên tắc thiết kế thực tế

- Tách điều kiện lọc khỏi fetch plan và count query.
- Dùng EXISTS khi chỉ cần kiểm tra sự tồn tại của phần tử collection.
- Nếu JOIN to-many tạo nhiều dòng root, dùng DISTINCT ở content khi phù hợp và COUNT DISTINCT root ID ở count query.
- Count query phải giữ cùng điều kiện lọc nhưng không fetch association.
- Không đặt collection fetch join trong query nhận Pageable.
- Dùng hai giai đoạn page ID rồi fetch collection khi trang cần toàn bộ association.
- Khôi phục thứ tự sau query IN và thêm tie-breaker duy nhất vào sort.
- Giữ Specification tập trung vào predicate; không nhúng collection fetch vào Specification dùng cho Page.
- Fetch join to-one thường ít rủi ro nhân dòng hơn collection.
- Dùng batch fetching hoặc DTO projection nếu không cần tải toàn bộ collection.
- Dùng Slice khi không cần tổng số; đổi Page thành Slice không tự sửa collection fetch pagination.
- Kiểm tra content query, count query, SQL và execution plan trên database mục tiêu.
- Kiểm thử cả content, totalElements, duplicate root, collection completeness và sort stability.

## 24. Checklist tự đánh giá

- [ ] Phân biệt filter predicate, fetch plan và count query.
- [ ] Giải thích được JOIN khác JOIN FETCH.
- [ ] Hiểu vì sao JOIN collection làm nhân dòng root.
- [ ] Dùng EXISTS để lọc root theo điều kiện collection.
- [ ] Viết @Query với countQuery có cùng predicate.
- [ ] Biết khi nào count(p) đúng và khi nào cần count(distinct p.id).
- [ ] Không đặt collection fetch join trong content query phân trang.
- [ ] Phân trang ID trước rồi fetch collection ở query riêng.
- [ ] Khôi phục thứ tự kết quả sau truy vấn IN.
- [ ] Thêm tie-breaker duy nhất vào ORDER BY.
- [ ] Giữ Specification chỉ chứa filter predicate khi dùng Page.
- [ ] Hiểu giới hạn của @EntityGraph và batch fetching.
- [ ] Chọn DTO projection khi chỉ cần dữ liệu tổng hợp.
- [ ] Phân biệt Page và Slice về nhu cầu count.
- [ ] Viết test xác nhận cả content và totalElements.
- [ ] Đọc SQL để phát hiện in-memory pagination và count sai.

## 25. Kết luận

Một truy vấn phân trang tốt cần chọn đúng root entity, tải association phù hợp và đếm đúng số root. JOIN/FETCH collection có thể nhân dòng; vì vậy filter theo collection nên ưu tiên EXISTS khi chỉ cần kiểm tra có phần tử phù hợp. Count query giữ cùng predicate nhưng chỉ đếm root entity, không fetch association.

Nếu trang cần collection đầy đủ, hãy phân trang ID trước rồi fetch collection trong truy vấn thứ hai và khôi phục thứ tự. Với điều kiện động, Specification nên tập trung vào predicate; với màn hình chỉ cần số liệu, DTO projection thường hiệu quả hơn tải entity graph. Kiểm thử cả content lẫn totalElements và quan sát SQL thực tế để bảo đảm logic phân trang đúng khi dữ liệu tăng.
