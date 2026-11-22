# Lựa chọn LAZY hoặc EAGER cho quan hệ đơn

Trong JPA, quan hệ đơn (to-one association) là quan hệ mà một entity tham chiếu tối đa một entity khác. Hai annotation thường dùng là **@ManyToOne** và **@OneToOne**. Khi tải entity, JPA cần quyết định lúc nào dữ liệu của entity được tham chiếu sẽ được tải. Quyết định đó được điều khiển bởi fetch type **LAZY** hoặc **EAGER**.

- **LAZY**: trì hoãn việc tải association cho đến khi ứng dụng cần truy cập nó, nếu provider hỗ trợ cách tải trì hoãn đó.
- **EAGER**: yêu cầu provider tải association cùng với entity trước khi entity được trả về cho ứng dụng.

Với quan hệ đơn, mặc định của JPA là **EAGER** cho cả **@ManyToOne** và **@OneToOne**. Vì vậy, nếu không khai báo fetch type, association có thể được tải sớm dù màn hình hoặc nghiệp vụ hiện tại chưa cần đến nó. Chọn fetch type phù hợp và thiết kế fetch plan theo từng truy vấn giúp kiểm soát số câu SQL, tránh N+1 và hạn chế tải dữ liệu không cần thiết.

**Điều kiện của ví dụ:** các đoạn mã dùng Spring Boot 3.x, Java 17 trở lên, Jakarta Persistence và Spring Data JPA. Ứng dụng cần **spring-boot-starter-data-jpa**, JDBC driver, DataSource và schema tương ứng. Đây là các tệp nguồn trong ứng dụng Spring Boot, không phải chương trình độc lập có thể chạy chỉ bằng **javac**.

## 1. Quan hệ đơn trong JPA là gì?

Quan hệ đơn là association mà một entity giữ tham chiếu tới tối đa một entity khác:

- **@ManyToOne**: nhiều entity phía sở hữu có thể tham chiếu cùng một entity đích. Ví dụ nhiều cuốn sách thuộc về một tác giả.
- **@OneToOne**: một entity liên kết với tối đa một entity ở phía bên kia. Ví dụ một tài khoản có một hồ sơ cá nhân.

Ví dụ quan hệ sách và tác giả:

~~~text
Author
  id
  name
    ^
    | nhiều Book có thể cùng tham chiếu
    |
Book
  id
  title
  author_id
~~~

Ở database, quan hệ **ManyToOne** thường được biểu diễn bằng foreign key **author_id** trong bảng **books**. Trong Java, thuộc tính **author** có kiểu **Author**.

## 2. LAZY và EAGER khác nhau thế nào?

| Đặc điểm | LAZY | EAGER |
|---|---|---|
| Ý định | Trì hoãn tải association | Tải association trước khi trả entity cho ứng dụng |
| Khi truy cập association | Provider có thể thực hiện truy vấn bổ sung | Dữ liệu đã được tải theo fetch plan của provider |
| SQL | Có thể phát sinh khi truy cập | Có thể JOIN hoặc SELECT riêng |
| Tải dữ liệu không cần thiết | Giảm nếu association không được dùng | Có thể tải dư dữ liệu |
| Rủi ro thường gặp | Truy cập sau khi persistence context đóng | Tải quá nhiều và phát sinh N+1 |

Điểm quan trọng: **EAGER không đồng nghĩa với JOIN**. Provider có thể dùng JOIN trong câu SQL ban đầu hoặc thực hiện một hay nhiều câu SELECT bổ sung để đáp ứng yêu cầu EAGER. Cách thực hiện phụ thuộc provider, mapping, truy vấn và dialect.

Ngược lại, **LAZY không có nghĩa là chắc chắn không có SQL bổ sung**. Khi code truy cập association, provider có thể tải dữ liệu bằng một truy vấn khác. Mục tiêu của LAZY là trì hoãn việc tải cho đến khi cần, chứ không tự động tối ưu toàn bộ truy vấn.

### Quy định mặc định của JPA cho quan hệ đơn

| Annotation | Fetch mặc định |
|---|---|
| **@ManyToOne** | **FetchType.EAGER** |
| **@OneToOne** | **FetchType.EAGER** |

Đối với quan hệ collection, mặc định của **@OneToMany** và **@ManyToMany** là **LAZY**. Bài này tập trung vào quan hệ đơn, nhưng cần nhớ sự khác nhau để tránh suy luận rằng mọi association đều có cùng mặc định.

JPA định nghĩa **EAGER** là yêu cầu provider phải fetch association theo fetch plan trước khi trả kết quả cho ứng dụng. **LAZY** là một hint (gợi ý) cho provider. Provider có thể không hỗ trợ trì hoãn trong một số trường hợp và vẫn tải sớm. Vì vậy, hãy kiểm tra hành vi thực tế của provider thay vì chỉ nhìn annotation.

## 3. Ví dụ @ManyToOne với LAZY

Giả sử mỗi cuốn sách có một tác giả và nhiều cuốn sách có thể thuộc cùng một tác giả.

Entity Author:

~~~java
package com.example.catalog.domain;

import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "authors")
public class Author {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String name;

    protected Author() {
    }

    public Author(String name) {
        this.name = name;
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }
}
~~~

Entity Book:

~~~java
package com.example.catalog.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.Table;

@Entity
@Table(name = "books")
public class Book {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private String title;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "author_id", nullable = false)
    private Author author;

    protected Book() {
    }

    public Book(String title, Author author) {
        this.title = title;
        this.author = author;
    }

    public Long getId() {
        return id;
    }

    public String getTitle() {
        return title;
    }

    public Author getAuthor() {
        return author;
    }
}
~~~

Các điểm cần hiểu:

- **@ManyToOne** mô tả nhiều sách có thể tham chiếu một tác giả.
- **fetch = FetchType.LAZY** yêu cầu trì hoãn tải tác giả cho đến khi được truy cập, nếu provider hỗ trợ.
- **optional = false** mô tả quan hệ bắt buộc ở mức mapping.
- **@JoinColumn(name = "author_id")** xác định cột foreign key.
- **nullable = false** mô tả cột foreign key không cho null khi provider tạo schema.

Với Hibernate, quan hệ **ManyToOne LAZY** thường được triển khai bằng proxy hoặc cơ chế enhancement phù hợp. Khi tải Book, Hibernate có thể chỉ tải dữ liệu của sách và giữ một tham chiếu trì hoãn tới Author. Khi code gọi **book.getAuthor().getName()**, association mới được khởi tạo nếu nó chưa được tải.

Ví dụ đọc sách mà không cần thông tin tác giả:

~~~java
Book book = bookRepository.findById(id).orElseThrow();
String title = book.getTitle();
// Không truy cập book.getAuthor(), nên association có thể vẫn chưa được tải.
~~~

Nếu nghiệp vụ cần tên tác giả, hãy chọn fetch plan phù hợp cho truy vấn đó thay vì giả định mọi truy vấn đọc Book đều cần Author.

## 4. Ví dụ @OneToOne với LAZY

Giả sử một tài khoản có một hồ sơ cá nhân. Có thể đặt foreign key ở bảng tài khoản:

~~~java
@Entity
@Table(name = "user_accounts")
public class UserAccount {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @OneToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "profile_id", nullable = false, unique = true)
    private Profile profile;

    protected UserAccount() {
    }

    public Profile getProfile() {
        return profile;
    }
}
~~~

Entity Profile:

~~~java
@Entity
@Table(name = "profiles")
public class Profile {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String displayName;

    protected Profile() {
    }

    public String getDisplayName() {
        return displayName;
    }
}
~~~

Ở đây **UserAccount** là phía sở hữu quan hệ vì nó chứa **@JoinColumn**. Cột **profile_id** là foreign key và **unique = true** giúp một profile không bị nhiều tài khoản cùng tham chiếu nếu schema thực sự có unique constraint tương ứng.

Nếu mô hình dùng quan hệ hai chiều, phía còn lại có thể khai báo:

~~~java
@OneToOne(mappedBy = "profile", fetch = FetchType.LAZY)
private UserAccount account;
~~~

Phía có **mappedBy** là inverse side, không sở hữu foreign key. Với inverse one-to-one, provider cần xác định association có tồn tại hay không. Trong một số cách triển khai, điều này khiến provider phải truy vấn sớm hoặc không thể trì hoãn hoàn toàn nếu thiếu thông tin. Hibernate có thể cần bytecode enhancement để hỗ trợ lazy loading hiệu quả cho một số inverse one-to-one mapping.

Vì vậy, **fetch = LAZY** trên **@OneToOne** là yêu cầu cần kiểm tra với provider và chiều quan hệ cụ thể. Hãy xem SQL thực tế để xác nhận association có thật sự được trì hoãn. Không nên kết luận rằng mọi one-to-one đều lazy chỉ vì annotation đã ghi LAZY.

## 5. Nên chọn LAZY hay EAGER cho quan hệ đơn?

Một hướng thiết kế thường hữu ích là khai báo quan hệ đơn với **LAZY** và chọn dữ liệu cần tải tại từng truy vấn. Ví dụ:

~~~java
@ManyToOne(fetch = FetchType.LAZY)
@JoinColumn(name = "author_id")
private Author author;
~~~

Lý do:

1. Một truy vấn có thể chỉ cần dữ liệu của entity chính.
2. Nhiều màn hình hoặc use case chỉ cần một phần association.
3. Fetch plan theo truy vấn cho phép chọn chính xác association cần tải.
4. Tránh việc một association EAGER kéo theo dữ liệu không cần thiết ở tất cả nơi sử dụng entity.

Tuy nhiên, LAZY không phải quy tắc tuyệt đối. Nếu một association luôn cần thiết trong hầu hết các use case và việc tải sớm được đo đạc là phù hợp, EAGER có thể là lựa chọn hợp lý. Quyết định nên dựa trên access pattern và SQL thực tế.

Không nên đặt tất cả quan hệ thành EAGER để tránh lỗi lazy loading. Cách đó có thể làm một truy vấn đơn giản tải cả đồ thị entity lớn, tăng số SQL, bộ nhớ và thời gian xử lý.

## 6. N+1 query có thể xảy ra như thế nào?

N+1 là tình huống ứng dụng chạy một truy vấn lấy danh sách entity chính, rồi tiếp tục chạy thêm một truy vấn cho từng entity khi truy cập association.

Ví dụ:

~~~java
List<Book> books = bookRepository.findAll();

for (Book book : books) {
    System.out.println(book.getAuthor().getName());
}
~~~

Nếu có N sách và tác giả chưa được tải, SQL có thể có dạng:

~~~sql
SELECT id, title, author_id
FROM books;

SELECT id, name FROM authors WHERE id = ?;
SELECT id, name FROM authors WHERE id = ?;
SELECT id, name FROM authors WHERE id = ?;
-- ... các lần tải tác giả tiếp theo
~~~

Tổng số truy vấn có thể là một truy vấn lấy danh sách sách cộng với tối đa N lần tải association. Nếu nhiều sách cùng tham chiếu một tác giả và persistence context/cache đã giữ tác giả đó, số SELECT bổ sung có thể thấp hơn N. Nhưng với nhiều tác giả khác nhau, N+1 là nguy cơ rõ ràng.

N+1 không chỉ xuất hiện với LAZY. EAGER cũng có thể tạo SELECT riêng cho từng association tùy provider và fetch plan. Vì thế, đổi LAZY thành EAGER không phải cách sửa N+1 đáng tin cậy.

Cần xác định truy vấn nào thực sự cần association, sau đó thiết kế fetch plan cho đúng use case.

## 7. Dùng JOIN FETCH để tải association trong một truy vấn

JPQL hỗ trợ **JOIN FETCH** để lấy entity chính và association cần thiết trong cùng truy vấn.

Repository:

~~~java
package com.example.catalog.repository;

import com.example.catalog.domain.Book;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

import java.util.Optional;

public interface BookRepository extends JpaRepository<Book, Long> {

    @Query("""
        select b
        from Book b
        join fetch b.author
        where b.id = :id
        """)
    Optional<Book> findByIdWithAuthor(@Param("id") Long id);
}
~~~

Service:

~~~java
@Service
public class BookQueryService {

    private final BookRepository bookRepository;

    public BookQueryService(BookRepository bookRepository) {
        this.bookRepository = bookRepository;
    }

    @Transactional(readOnly = true)
    public BookDetails getDetails(Long id) {
        Book book = bookRepository.findByIdWithAuthor(id)
            .orElseThrow();

        return new BookDetails(
            book.getId(),
            book.getTitle(),
            book.getAuthor().getName()
        );
    }
}
~~~

DTO:

~~~java
public record BookDetails(
    Long id,
    String title,
    String authorName
) {
}
~~~

Trong ví dụ, **JOIN FETCH** yêu cầu JPA tải Author cùng Book. Khi service chuyển entity sang DTO, việc gọi **getAuthor().getName()** không cần một truy vấn lazy riêng cho association này.

Nếu association có thể null, dùng **LEFT JOIN FETCH** để giữ lại entity chính ngay cả khi không có entity liên quan:

~~~java
@Query("""
    select b
    from Book b
    left join fetch b.author
    where b.id = :id
    """)
Optional<Book> findByIdWithOptionalAuthor(@Param("id") Long id);
~~~

Dùng JOIN FETCH theo nhu cầu truy vấn, không biến mọi truy vấn trong repository thành truy vấn fetch toàn bộ association.

## 8. Dùng @EntityGraph để mô tả fetch plan

JPA EntityGraph cho phép khai báo association cần tải cho một truy vấn mà không phải viết JPQL JOIN FETCH thủ công.

Ví dụ:

~~~java
package com.example.catalog.repository;

import com.example.catalog.domain.Book;
import org.springframework.data.jpa.repository.EntityGraph;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.Optional;

public interface BookRepository extends JpaRepository<Book, Long> {

    @EntityGraph(attributePaths = "author")
    Optional<Book> findByIsbn(String isbn);
}
~~~

**attributePaths = "author"** yêu cầu truy vấn này tải association Author. Spring Data JPA chuyển EntityGraph thành fetch plan phù hợp với provider.

Có thể khai báo nhiều đường dẫn:

~~~java
@EntityGraph(attributePaths = {
    "author",
    "publisher"
})
Optional<Book> findDetailedById(Long id);
~~~

Ví dụ này giả định entity Book có các thuộc tính association **author** và **publisher**.

Một số khác biệt:

- **JOIN FETCH** viết rõ join trong JPQL, phù hợp khi truy vấn có logic join riêng.
- **@EntityGraph** tách fetch plan khỏi phần điều kiện truy vấn, giúp tái sử dụng method query rõ ràng.
- Cả hai đều yêu cầu kiểm tra SQL thực tế; provider có thể thực thi fetch plan bằng cách khác nhau.
- EntityGraph không có nghĩa là mọi quan hệ trong entity đều được tải.

JPA hỗ trợ hai kiểu graph thường gặp:

- **FETCH graph**: các thuộc tính được chỉ định là eager trong fetch plan của truy vấn; thuộc tính không được chỉ định được xử lý theo quy tắc graph.
- **LOAD graph**: các thuộc tính được chỉ định là eager; các thuộc tính khác giữ fetch semantics mapping mặc định.

Trong Spring Data JPA, **@EntityGraph** mặc định dùng kiểu FETCH nếu không khai báo type. Chọn graph type theo mục tiêu truy vấn và kiểm tra kết quả trên provider đang dùng.

## 9. Dùng DTO projection khi chỉ cần một phần dữ liệu

Nếu màn hình chỉ cần ID sách, tiêu đề và tên tác giả, không nhất thiết phải tải toàn bộ entity graph. DTO projection cho phép chọn đúng cột cần dùng:

~~~java
package com.example.catalog.dto;

public record BookListItem(
    Long id,
    String title,
    String authorName
) {
}
~~~

Repository:

~~~java
@Query("""
    select new com.example.catalog.dto.BookListItem(
        b.id,
        b.title,
        a.name
    )
    from Book b
    join b.author a
    where b.title like concat('%', :keyword, '%')
    """)
List<BookListItem> searchBookItems(@Param("keyword") String keyword);
~~~

Truy vấn chỉ lấy các giá trị cần cho DTO. Kết quả không phải entity Book managed, vì vậy persistence context không theo dõi DTO như một entity.

DTO projection hữu ích cho danh sách, báo cáo và API read model. Nếu cần sửa entity, hãy tải entity phù hợp trong transaction và thực hiện thay đổi theo nghiệp vụ.

## 10. LazyInitializationException và ranh giới transaction

Với LAZY, association có thể chưa được tải khi service trả entity về controller. Nếu persistence context đã đóng, việc truy cập association có thể phát sinh **LazyInitializationException** trong Hibernate.

Ví dụ nguy hiểm:

~~~java
public Book getBook(Long id) {
    return bookRepository.findById(id).orElseThrow();
}
~~~

Sau khi method trả về, transaction hoặc persistence context có thể đã kết thúc. Controller tiếp tục gọi:

~~~java
book.getAuthor().getName();
~~~

Nếu association vẫn chưa được khởi tạo, Hibernate không còn persistence context để tải dữ liệu.

Cách xử lý nên là xác định dữ liệu cần trả về và tải/map trong transaction:

~~~java
@Transactional(readOnly = true)
public BookDetails getBookDetails(Long id) {
    Book book = bookRepository.findByIdWithAuthor(id).orElseThrow();

    return new BookDetails(
        book.getId(),
        book.getTitle(),
        book.getAuthor().getName()
    );
}
~~~

Không nên đổi mọi association thành EAGER chỉ để tránh LazyInitializationException. Cũng không nên dựa vào Open Session in View như giải pháp fetch plan tổng quát; việc truy cập association trong quá trình render response có thể tạo truy vấn ngoài dự kiến và khiến hiệu năng khó kiểm soát.

Một nguyên tắc hữu ích: entity được tải và chuyển thành DTO ở ranh giới service transaction; controller nhận dữ liệu đã sẵn sàng để trả về.

## 11. Một số cách tối ưu tải LAZY khi có danh sách

Ngoài JOIN FETCH, EntityGraph và DTO projection, Hibernate có một số cơ chế hỗ trợ giảm số truy vấn.

### Batch fetching

Khi nhiều entity cần khởi tạo cùng loại association, Hibernate có thể gom nhiều ID vào một truy vấn IN thay vì chạy từng SELECT riêng.

Có thể cấu hình ở mức entity:

~~~java
@Entity
@BatchSize(size = 32)
public class Author {
    // ...
}
~~~

Hoặc cấu hình mặc định:

~~~yaml
spring:
  jpa:
    properties:
      hibernate:
        default_batch_fetch_size: 32
~~~

Batch fetching có thể giảm N+1 thành một số ít truy vấn theo lô. Đây là tính năng của Hibernate, không phải bảo đảm chung của mọi JPA provider. Kích thước batch cần được đo đạc theo database và kích thước dữ liệu.

### DTO projection

Nếu chỉ cần một vài trường, DTO projection thường tiết kiệm hơn việc tải entity và association rồi bỏ phần lớn dữ liệu.

### EntityGraph hoặc JOIN FETCH

Nếu use case cần entity cùng một số association, dùng fetch plan rõ ràng để tải đúng dữ liệu.

Không có một chiến lược tối ưu cho mọi truy vấn. Hãy dựa trên số hàng, số association, cardinality, phân trang và SQL thực tế.

## 12. Cascade, optional và fetch là các khái niệm khác nhau

Ba thuộc tính thường bị nhầm:

| Khái niệm | Câu hỏi |
|---|---|
| Fetch type | Khi tải entity, association được tải lúc nào? |
| Cascade | Thao tác persist/merge/remove có được truyền sang entity liên quan không? |
| Optional/nullability | Association có bắt buộc tồn tại hay có thể null? |

Ví dụ:

~~~java
@ManyToOne(
    fetch = FetchType.LAZY,
    optional = false
)
@JoinColumn(name = "author_id", nullable = false)
private Author author;
~~~

Ở đây:

- **LAZY** điều khiển thời điểm tải Author.
- **optional = false** biểu thị quan hệ bắt buộc ở mức JPA.
- **nullable = false** mô tả cột foreign key không nullable trong mapping.

Nếu thêm **cascade = CascadeType.PERSIST**, thao tác persist Book có thể được truyền sang Author theo cascade rule. Điều đó không làm association trở thành EAGER.

Không nên thêm **CascadeType.REMOVE** cho quan hệ ManyToOne một cách tùy tiện. Xóa một Book thường không có nghĩa là xóa Author, vì Author có thể được nhiều Book khác tham chiếu.

## 13. Kiểm tra SQL và đo hiệu năng

Đừng chỉ nhìn annotation để kết luận truy vấn tối ưu. Hãy quan sát SQL do provider phát ra.

Trong môi trường development, có thể bật:

~~~yaml
logging:
  level:
    org.hibernate.SQL: DEBUG
~~~

Nếu cần xem giá trị bind parameter, Hibernate có logger riêng cho JDBC bind. Chỉ bật ở môi trường kiểm thử phù hợp vì giá trị truy vấn có thể chứa dữ liệu nhạy cảm.

Khi kiểm tra một use case, ghi nhận:

1. Số câu SELECT trước khi truy cập association.
2. Số câu SELECT sau khi truy cập association.
3. Association nào được tải dù use case không dùng.
4. Số hàng và kích thước dữ liệu trả về.
5. Kết quả khi chạy với số lượng entity gần với dữ liệu thực tế.

Ví dụ kiểm thử hành vi truy vấn:

~~~java
@DataJpaTest
class BookFetchTest {

    @Autowired
    private BookRepository bookRepository;

    @Test
    void fetchesAuthorForDetailsQuery() {
        Book book = bookRepository.findByIdWithAuthor(1L).orElseThrow();

        assertThat(book.getAuthor().getName()).isNotBlank();
    }
}
~~~

Bài test trên kiểm tra truy vấn trả về dữ liệu association. Nếu cần xác nhận số SQL, có thể dùng Hibernate Statistics hoặc datasource proxy trong test. Chỉ assert kết quả cuối cùng chưa chứng minh không có N+1.

## 14. Lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| **LazyInitializationException** | Truy cập association sau khi persistence context đóng | Tải bằng fetch plan phù hợp và map DTO trong transaction |
| N+1 query | Duyệt danh sách rồi truy cập từng association LAZY | Dùng JOIN FETCH, EntityGraph, projection hoặc batch fetching |
| Tải quá nhiều dữ liệu | Dùng EAGER trên association không cần ở mọi use case | Chọn LAZY và fetch plan theo truy vấn |
| EAGER vẫn phát nhiều SELECT | EAGER không bắt buộc phải dùng JOIN | Kiểm tra SQL và thiết kế fetch plan tường minh |
| One-to-one LAZY vẫn tải sớm | Provider cần xác định association hoặc thiếu hỗ trợ lazy ở chiều inverse | Kiểm tra chiều sở hữu, bytecode enhancement và SQL |
| API phát sinh SQL khi serialize entity | Trả entity trực tiếp và serializer truy cập association | Trả DTO đã được dựng trong transaction |
| Thay LAZY bằng EAGER làm chậm ứng dụng | Entity graph lớn và truy vấn không còn kiểm soát | Tối ưu từng use case thay vì đổi toàn bộ mapping |
| Fetch plan không như mong đợi | Query, EntityGraph và provider có semantics riêng | Kiểm tra SQL thực tế và integration test |

## 15. Checklist lựa chọn fetch type

- [ ] Xác định association là **@ManyToOne** hay **@OneToOne**.
- [ ] Nhớ mặc định của cả hai quan hệ đơn là **EAGER**.
- [ ] Cân nhắc khai báo **LAZY** để trì hoãn dữ liệu chưa cần, nhưng nhớ đây là hint của JPA.
- [ ] Kiểm tra hỗ trợ LAZY của provider, nhất là inverse **@OneToOne**.
- [ ] Xác định use case nào cần association và chọn JOIN FETCH, EntityGraph hoặc DTO projection.
- [ ] Không đổi tất cả association thành EAGER để xử lý lỗi lazy loading.
- [ ] Tránh truy cập association ngoài persistence context.
- [ ] Đếm SQL và kiểm tra N+1 bằng dữ liệu đủ lớn.
- [ ] Giữ fetch type, cascade và optionality thành các quyết định riêng.
- [ ] Trả DTO từ service khi xây dựng API read response.

## 16. Kết luận

Với quan hệ đơn, JPA mặc định dùng EAGER cho **@ManyToOne** và **@OneToOne**, trong khi LAZY là một hint yêu cầu provider trì hoãn tải association. EAGER không đảm bảo JOIN; LAZY cũng không đảm bảo không có truy vấn bổ sung. Cả hai cần được đánh giá qua SQL thực tế.

Một thiết kế thường dễ kiểm soát là khai báo association LAZY khi phù hợp, sau đó dùng JOIN FETCH, **@EntityGraph**, DTO projection hoặc batch fetching cho từng use case. Tải dữ liệu đúng thời điểm, map DTO trong transaction và kiểm tra số truy vấn giúp tránh cả LazyInitializationException lẫn N+1.