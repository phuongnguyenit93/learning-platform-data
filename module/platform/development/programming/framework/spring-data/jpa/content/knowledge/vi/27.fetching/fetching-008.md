# LazyInitializationException và thiết kế ranh giới đọc dữ liệu

Hibernate dùng lazy loading để trì hoãn việc tải association cho tới khi ứng dụng thật sự truy cập dữ liệu đó. Cách này giúp tránh tải những quan hệ không cần thiết, nhưng entity phải còn gắn với một persistence context đang hoạt động khi Hibernate cần truy vấn database.

**LazyInitializationException** thường xuất hiện khi code truy cập một proxy hoặc collection LAZY sau khi persistence context/Session đã đóng. Một tình huống phổ biến là service trả entity về controller, transaction kết thúc, rồi JSON serializer truy cập collection trong lúc tạo response.

Cách xử lý bền vững là thiết kế rõ **ranh giới đọc dữ liệu**: xác định use case cần những field và association nào, tải chúng trong transaction bằng fetch plan phù hợp, rồi chuyển sang DTO trước khi rời service. Bài này giải thích cơ chế lỗi, vai trò của transaction và OSIV, cách dùng EntityGraph, JOIN FETCH, DTO projection, batch fetching và cách kiểm thử để tránh N+1.

**Điều kiện của ví dụ:** các đoạn mã dùng Java 17 trở lên, Spring Boot 3.x, Spring Data JPA, Hibernate và Spring MVC. Ứng dụng cần **spring-boot-starter-data-jpa**, **spring-boot-starter-web**, JDBC driver, DataSource và schema phù hợp. Đây là các phần của ứng dụng Spring Boot, không phải chương trình độc lập có thể chạy chỉ bằng javac.

## 1. Lazy loading và persistence context

Một association LAZY được tải khi ứng dụng truy cập nó, thay vì tải ngay cùng entity cha.

Ví dụ Author có nhiều Book:

~~~java
@Entity
@Table(name = "authors")
public class Author {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String name;

    @OneToMany(
        mappedBy = "author",
        fetch = FetchType.LAZY,
        cascade = CascadeType.PERSIST
    )
    private List<Book> books = new ArrayList<>();

    protected Author() {
    }

    public Author(String name) {
        this.name = name;
    }

    public void addBook(Book book) {
        books.add(book);
        book.assignAuthor(this);
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public List<Book> getBooks() {
        return books;
    }
}
~~~

Phía Book:

~~~java
@Entity
@Table(name = "books")
public class Book {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String title;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "author_id")
    private Author author;

    protected Book() {
    }

    public Book(String title) {
        this.title = title;
    }

    void assignAuthor(Author author) {
        this.author = author;
    }

    public Long getId() {
        return id;
    }

    public String getTitle() {
        return title;
    }
}
~~~

Khi gọi:

~~~java
Author author = entityManager.find(Author.class, 1L);
~~~

Hibernate có thể chỉ truy vấn bảng authors. Collection books được đại diện bởi một persistent collection chưa khởi tạo. Khi gọi:

~~~java
int count = author.getBooks().size();
~~~

nếu persistence context còn mở, Hibernate thực hiện truy vấn để tải các Book liên quan.

Persistence context là vùng quản lý entity của JPA, thường được Spring gắn với transaction trong ứng dụng service. Hibernate Session là API cụ thể của Hibernate đứng sau persistence context trong cấu hình phổ biến.

## 2. LazyInitializationException xảy ra khi nào?

Nếu association LAZY chưa được khởi tạo mà entity đã detached, Hibernate không còn Session để chạy truy vấn bổ sung.

Luồng gây lỗi thường gặp:

~~~text
Controller
    |
    v
Gọi service
    |
    v
@Transactional service
    |
    +--> repository tải Author
    |
    +--> books vẫn LAZY, chưa khởi tạo
    |
    v
Service kết thúc, transaction/persistence context đóng
    |
    v
Controller nhận Author detached
    |
    v
JSON serializer gọi author.getBooks()
    |
    v
Hibernate cần Session để tải books
    |
    v
LazyInitializationException
~~~

Ví dụ:

~~~java
@Service
public class AuthorService {

    private final AuthorRepository repository;

    public AuthorService(AuthorRepository repository) {
        this.repository = repository;
    }

    @Transactional(readOnly = true)
    public Author findEntity(Long id) {
        return repository.findById(id).orElseThrow();
    }
}
~~~

Controller trả trực tiếp entity:

~~~java
@GetMapping("/authors/{id}")
public Author getAuthor(@PathVariable Long id) {
    return authorService.findEntity(id);
}
~~~

Khi service kết thúc, transaction-scoped persistence context thường được đóng. Nếu không có persistence context khác giữ entity, Author trở thành detached. Nếu serializer truy cập books chưa khởi tạo, Hibernate có thể ném LazyInitializationException.

Lưu ý:

- Lỗi thường xảy ra khi truy cập proxy hoặc collection chưa khởi tạo, không phải cứ dùng LAZY là lỗi.
- Nếu association đã được tải trước khi context đóng, đọc nó sau đó không gây lỗi này.
- Nếu association không còn cần thiết, đừng truy cập nó chỉ để phục vụ serialization.
- LazyInitializationException là exception đặc thù của Hibernate; provider JPA khác có thể biểu hiện lỗi lazy access theo cách khác.

## 3. @Transactional không tự tải mọi association

Một hiểu nhầm phổ biến là thêm **@Transactional** vào service sẽ giải quyết mọi LazyInitializationException.

Transaction giữ persistence context hoạt động trong phạm vi xử lý, nhưng không tự động tải tất cả association LAZY. Nếu code truy cập association trong transaction, Hibernate có thể tải nó. Nếu code không truy cập, association vẫn có thể chưa khởi tạo khi transaction kết thúc.

Ví dụ:

~~~java
@Transactional(readOnly = true)
public AuthorDetailDto getDetail(Long id) {
    Author author = repository.findById(id).orElseThrow();

    // Truy cập trong transaction nên collection có thể được tải tại đây.
    List<String> titles = author.getBooks().stream()
        .map(Book::getTitle)
        .toList();

    return new AuthorDetailDto(author.getId(), author.getName(), titles);
}
~~~

Đoạn code này chuyển dữ liệu cần thiết thành DTO khi persistence context còn hoạt động. Tuy nhiên, nếu trang có nhiều Author và mapper truy cập books của từng người, code vẫn có thể tạo N+1 query. Cần kết hợp transaction boundary với fetch plan phù hợp.

Một số điểm về Spring transaction:

- Spring thường áp dụng @Transactional thông qua proxy.
- Gọi một method transactional từ method khác trong cùng object (self-invocation) thường không đi qua proxy, nên annotation có thể không tạo transaction mới như mong đợi.
- Transaction của service nên bao trùm toàn bộ thao tác đọc và chuyển DTO.
- @Transactional(readOnly = true) thể hiện ý định đọc và có thể giúp provider tối ưu, nhưng không tự biến entity thành read-only tuyệt đối và không tự fetch association.

## 4. Ranh giới đọc dữ liệu: trả DTO trước khi rời service

Một thiết kế dễ kiểm soát là service trả về DTO thay vì entity. Service chịu trách nhiệm lấy đúng dữ liệu và chuyển đổi trong transaction.

DTO:

~~~java
package com.example.author.dto;

import java.util.List;

public record AuthorDetailDto(
    Long id,
    String name,
    List<BookSummaryDto> books
) {
}

public record BookSummaryDto(
    Long id,
    String title
) {
}
~~~

Service:

~~~java
@Service
public class AuthorService {

    private final AuthorRepository repository;

    public AuthorService(AuthorRepository repository) {
        this.repository = repository;
    }

    @Transactional(readOnly = true)
    public AuthorDetailDto getDetail(Long id) {
        Author author = repository.findWithBooksById(id)
            .orElseThrow();

        List<BookSummaryDto> books = author.getBooks().stream()
            .map(book -> new BookSummaryDto(
                book.getId(),
                book.getTitle()
            ))
            .toList();

        return new AuthorDetailDto(
            author.getId(),
            author.getName(),
            books
        );
    }
}
~~~

Sau khi method trả về, DTO đã chứa dữ liệu cần thiết và không phụ thuộc Hibernate Session. Controller chỉ trả DTO:

~~~java
@GetMapping("/authors/{id}")
public AuthorDetailDto getAuthor(@PathVariable Long id) {
    return authorService.getDetail(id);
}
~~~

Đây là ranh giới rõ ràng: repository/service làm việc với entity trong persistence context; controller và serializer làm việc với DTO độc lập.

## 5. Dùng @EntityGraph để khai báo fetch plan

**@EntityGraph** cho phép chỉ định association cần được tải cùng truy vấn repository. Đây là cách khai báo fetch plan theo use case mà không phải thay đổi fetch type mặc định của entity.

Repository:

~~~java
public interface AuthorRepository
        extends JpaRepository<Author, Long> {

    @EntityGraph(attributePaths = "books")
    @Query("select a from Author a where a.id = :id")
    Optional<Author> findWithBooksById(@Param("id") Long id);
}
~~~

Khi gọi method này, Spring Data yêu cầu JPA provider tải Author cùng association books theo entity graph. Sau khi truy vấn hoàn tất, service có thể duyệt books trong transaction để tạo DTO.

Ưu điểm:

- Fetch plan nằm gần repository method của use case.
- Không cần đổi mọi truy vấn của Author thành EAGER.
- Có thể liệt kê nhiều association bằng attributePaths.
- Có thể dùng named entity graph được khai báo trên entity.

Ví dụ tải cả books và thông tin publisher:

~~~java
@EntityGraph(attributePaths = {"books", "books.publisher"})
@Query("select a from Author a where a.id = :id")
Optional<Author> findDetailById(@Param("id") Long id);
~~~

Đường dẫn phải khớp association trong entity. Hành vi SQL cuối cùng phụ thuộc provider và loại graph; hãy kiểm tra SQL thực tế.

EntityGraph là hướng dẫn fetch plan, không phải bảo đảm một câu SQL duy nhất trong mọi trường hợp. Nếu graph chứa nhiều collection, provider có thể tạo nhiều truy vấn hoặc join phức tạp; cần đo hiệu năng và kiểm tra số dòng.

## 6. Dùng JOIN FETCH trong JPQL

Một cách khác là khai báo fetch join ngay trong JPQL:

~~~java
public interface AuthorRepository
        extends JpaRepository<Author, Long> {

    @Query("""
        select distinct a
        from Author a
        left join fetch a.books
        where a.id = :id
        """)
    Optional<Author> findDetailById(@Param("id") Long id);
}
~~~

**JOIN FETCH** vừa join association vừa yêu cầu provider khởi tạo association trong kết quả. Dùng LEFT JOIN FETCH khi vẫn muốn lấy Author kể cả khi không có Book nào.

Từ khóa **distinct** diễn đạt mong muốn mỗi Author xuất hiện một lần trong kết quả logic dù join collection tạo nhiều dòng SQL cho cùng Author. Cách xử lý trùng cụ thể có thể khác theo provider/version; luôn kiểm tra kết quả và SQL.

Có thể fetch join quan hệ to-one:

~~~java
@Query("""
    select b
    from Book b
    join fetch b.author
    where b.id = :id
    """)
Optional<Book> findWithAuthorById(@Param("id") Long id);
~~~

Fetch join phù hợp khi fetch plan của truy vấn cụ thể đã rõ. Không nên thêm fetch join mọi association vào mọi query vì có thể tải quá nhiều dữ liệu và nhân số dòng.

## 7. Cẩn thận khi phân trang với collection fetch join

Phân trang cùng collection fetch join là trường hợp cần đặc biệt chú ý:

~~~java
@Query("""
    select distinct a
    from Author a
    left join fetch a.books
    """)
Page<Author> findAuthorsWithBooks(Pageable pageable);
~~~

Một Author có nhiều Book sẽ tạo nhiều dòng ở mức SQL. Việc áp dụng limit/offset lên các dòng join có thể không tương ứng với số Author mong muốn. Hibernate có thể phải xử lý phân trang trong bộ nhớ hoặc phát cảnh báo/lỗi tùy cấu hình.

Các cách xử lý thường dùng:

1. Phân trang ID của Author trước, sau đó truy vấn fetch dữ liệu chi tiết cho danh sách ID đó.
2. Dùng DTO projection để chỉ lấy các cột cần thiết.
3. Dùng EntityGraph/to-one fetch phù hợp và tránh fetch collection trong truy vấn phân trang.
4. Với màn hình cần danh sách con, tải collection trong một bước tiếp theo có kiểm soát.

Ví dụ hai bước:

~~~java
Page<Long> authorIds = repository.findIdsByActiveTrue(pageable);

List<Author> authors =
    repository.findWithBooksByIdIn(authorIds.getContent());
~~~

Repository:

~~~java
@Query(
    value = "select a.id from Author a where a.active = true",
    countQuery = "select count(a) from Author a where a.active = true"
)
Page<Long> findIdsByActiveTrue(Pageable pageable);

@Query("""
    select distinct a
    from Author a
    left join fetch a.books
    where a.id in :ids
    """)
List<Author> findWithBooksByIdIn(@Param("ids") Collection<Long> ids);
~~~

Hai bước cần nằm trong transaction phù hợp nếu muốn đọc nhất quán theo cùng persistence context. Kết quả bước hai có thể không giữ thứ tự của danh sách ID; nếu thứ tự quan trọng, sắp xếp lại theo thứ tự ID hoặc thêm ORDER BY phù hợp.

## 8. DTO projection trực tiếp từ query

Nếu use case chỉ cần dữ liệu đọc, repository có thể trả DTO trực tiếp thay vì tải entity rồi map.

DTO:

~~~java
public record BookListItemDto(
    Long id,
    String title,
    String authorName
) {
}
~~~

Repository:

~~~java
@Query("""
    select new com.example.catalog.dto.BookListItemDto(
        b.id,
        b.title,
        a.name
    )
    from Book b
    join b.author a
    where b.status = :status
    order by b.title
    """)
List<BookListItemDto> findBookList(
    @Param("status") BookStatus status
);
~~~

JPQL constructor expression chọn rõ ba giá trị cần thiết. Kết quả DTO không phải entity managed và không có association LAZY để serializer truy cập.

DTO projection thường phù hợp với:

- API danh sách hoặc báo cáo.
- Màn hình chỉ đọc cần một số field từ nhiều bảng.
- Truy vấn có join nhưng không cần cập nhật entity.
- Use case cần kiểm soát chính xác cột và tránh materialize entity đầy đủ.

Nếu cần phân trang, method có thể trả Page<DTO>, nhưng phải bảo đảm count query phù hợp với logic join/filter.

## 9. N+1 và cách batch fetching giúp giảm truy vấn

N+1 xảy ra khi một truy vấn tải danh sách entity cha, sau đó mỗi entity kích hoạt một truy vấn riêng để tải association LAZY.

Ví dụ:

~~~java
List<Author> authors = authorRepository.findAll();

for (Author author : authors) {
    System.out.println(author.getBooks().size());
}
~~~

Nếu có 100 Author, Hibernate có thể phát một query lấy Author và thêm 100 query lấy books. Đây là N+1.

### Dùng batch fetching

Hibernate có thể gom nhiều association chưa khởi tạo vào một số truy vấn theo lô.

Đặt trên collection:

~~~java
@BatchSize(size = 32)
@OneToMany(mappedBy = "author", fetch = FetchType.LAZY)
private List<Book> books = new ArrayList<>();
~~~

Hoặc cấu hình mặc định:

~~~yaml
spring:
  jpa:
    properties:
      hibernate:
        default_batch_fetch_size: 32
~~~

Khi code truy cập collection của nhiều Author trong cùng Session, Hibernate có thể tải association cho nhiều Author bằng một truy vấn IN thay vì một truy vấn cho mỗi Author.

Batch fetching giảm số round-trip nhưng không loại bỏ nhu cầu Session còn mở. Nó cũng không bảo đảm chỉ có đúng một truy vấn; số batch phụ thuộc số entity, kích thước batch, provider và database.

### Khi nào dùng EntityGraph, JOIN FETCH hay batch fetching?

| Cách | Phù hợp khi | Đánh đổi |
|---|---|---|
| EntityGraph | Fetch plan thay đổi theo use case repository | SQL cụ thể do provider quyết định |
| JOIN FETCH | Muốn truy vấn rõ association cần fetch | Join collection có thể nhân dòng và gây khó phân trang |
| DTO projection | Chỉ cần dữ liệu đọc, muốn chọn cột rõ ràng | Cần định nghĩa DTO/query cho từng read model |
| Batch fetching | Nhiều association LAZY được truy cập theo nhóm | Vẫn có truy vấn bổ sung và cần Session mở |
| Hibernate.initialize | Cần khởi tạo một association cụ thể trong Session | Phụ thuộc Hibernate và dễ che giấu fetch plan nếu lạm dụng |

## 10. OSIV là gì và vì sao không nên phụ thuộc vào nó?

**Open EntityManager in View (OSIV)** giữ EntityManager mở trong suốt vòng đời HTTP request. Nhờ đó, một số association LAZY vẫn có thể được tải khi controller hoặc JSON serializer truy cập sau khi service transaction đã kết thúc.

Trong Spring Boot web application, OSIV có thể được bật mặc định tùy cấu hình. Có thể tắt rõ ràng:

~~~yaml
spring:
  jpa:
    open-in-view: false
~~~

Khi OSIV tắt, việc truy cập association chưa khởi tạo sau transaction thường bộc lộ ngay bằng LazyInitializationException. Đây là tín hiệu hữu ích để phát hiện API đang phụ thuộc vào lazy loading ngoài ranh giới service.

OSIV có thể che giấu vấn đề:

- SQL có thể được phát trong lúc serializer tạo JSON.
- N+1 query dễ xuất hiện mà service code không thể hiện rõ.
- Database access bị kéo dài tới cuối HTTP request.
- Controller/serializer vô tình quyết định fetch plan.
- Hiệu năng API khó dự đoán và khó kiểm thử ở tầng service.

OSIV không phải lúc nào cũng sai, nhưng không nên dùng nó như cách chữa mặc định cho LazyInitializationException. Thiết kế service trả DTO với dữ liệu được tải có chủ đích thường dễ kiểm soát hơn.

## 11. Không đổi mọi association sang EAGER để chữa lỗi

Một phản ứng thường gặp là đổi LAZY thành EAGER để tránh exception. Điều này có thể khiến query tải dữ liệu quá mức ở mọi use case.

Ví dụ, nếu Author.books được EAGER, mọi truy vấn Author có thể phải tải cả collection books dù màn hình chỉ cần tên tác giả. Điều đó có thể:

- Tăng số hàng join và lượng dữ liệu truyền.
- Gây truy vấn bổ sung tùy provider.
- Tạo N+1 ở các association EAGER không được fetch cùng query.
- Làm pagination khó dự đoán.
- Tăng bộ nhớ và chi phí materialize entity.

Theo JPA, EAGER là yêu cầu fetch, còn LAZY là một gợi ý mà provider có thể xử lý linh hoạt. Với quan hệ to-one, mặc định JPA thường là EAGER; với to-many, mặc định là LAZY. Trong ứng dụng Hibernate, nhiều nhóm chọn LAZY cho association và xác định fetch plan theo từng use case.

Không nên coi LAZY là bảo đảm tuyệt đối provider sẽ không tải sớm, hoặc coi EAGER là bảo đảm mọi dữ liệu được lấy bằng một JOIN. Hãy xem SQL thực tế.

## 12. Explicit initialization: chỉ dùng khi có lý do rõ ràng

Hibernate cung cấp:

~~~java
Hibernate.initialize(author.getBooks());
~~~

Lệnh này khởi tạo proxy hoặc collection nếu Session còn hoạt động. Có thể hữu ích trong một số code Hibernate-specific, nhưng service nên ưu tiên khai báo fetch plan qua EntityGraph, JOIN FETCH hoặc DTO query.

Không gọi Hibernate.initialize sau khi entity đã detached; khi đó không còn Session phù hợp để tải dữ liệu và lỗi lazy access vẫn có thể xảy ra.

Có thể kiểm tra trạng thái tải mà không chủ động khởi tạo bằng JPA PersistenceUtil:

~~~java
boolean loaded = Persistence
    .getPersistenceUtil()
    .isLoaded(author, "books");
~~~

Với Hibernate, cũng có thể dùng **Hibernate.isInitialized(...)**. Các API kiểm tra này hữu ích trong test hoặc chẩn đoán, không nên biến thành nhánh điều khiển chính của nghiệp vụ.

## 13. Đừng để JSON serializer điều khiển việc tải dữ liệu

Nếu controller trả entity, Jackson có thể gọi getter để tạo JSON. Khi getter truy cập proxy/collection LAZY, serializer vô tình kích hoạt truy vấn database.

Quan hệ hai chiều còn có thể tạo vòng lặp:

~~~text
Author
  -> books
       -> author
            -> books
                 -> ...
~~~

Các annotation Jackson như **@JsonIgnore** hoặc **@JsonManagedReference/@JsonBackReference** có thể xử lý một số vòng lặp serialization, nhưng không giải quyết tận gốc việc entity persistence bị dùng làm response contract.

Cách rõ ràng hơn:

1. Service xác định dữ liệu endpoint cần.
2. Repository tải dữ liệu theo fetch plan.
3. Service chuyển entity thành DTO trong transaction.
4. Controller serialize DTO, không truy cập entity/proxy.

Nếu API có nhiều dạng response khác nhau, tạo DTO tương ứng cho từng use case thay vì dùng một entity với nhiều annotation serialization.

## 14. Phân biệt lỗi lazy access với lỗi transaction

Không phải mọi lỗi truy cập entity ngoài transaction đều là LazyInitializationException.

| Tình huống | Hành vi có thể gặp |
|---|---|
| Đọc field cơ bản đã được tải trên detached entity | Thường đọc được vì giá trị nằm trong object |
| Đọc collection LAZY chưa khởi tạo sau khi Session đóng | Hibernate có thể ném LazyInitializationException |
| Gọi persist/remove khi không có transaction phù hợp | Có thể gặp TransactionRequiredException hoặc lỗi transaction |
| Truy cập association LAZY trong transaction đang hoạt động | Provider có thể tải association |
| Dùng entity đã bị detach rồi gọi merge | Merge tạo/trả về managed copy theo JPA semantics |

Transaction, persistence context và trạng thái entity liên quan nhưng không phải một khái niệm. Transaction quản lý đơn vị commit/rollback; persistence context theo dõi entity; detached entity không còn được context đó quản lý.

## 15. Kiểm thử LazyInitializationException và cách sửa

Để tái hiện lỗi một cách đáng tin cậy, cần để transaction service kết thúc trước khi truy cập association. Tắt OSIV trong test để HTTP request không giữ EntityManager mở.

Service cố ý trả entity:

~~~java
@Transactional(readOnly = true)
public Author findEntity(Long id) {
    return authorRepository.findById(id).orElseThrow();
}
~~~

Test tích hợp:

~~~java
@SpringBootTest(properties = "spring.jpa.open-in-view=false")
class AuthorLazyLoadingTest {

    @Autowired
    private AuthorService authorService;

    @Test
    void accessingUninitializedCollectionAfterServiceReturnsFails() {
        Author author = authorService.findEntity(existingAuthorId);

        assertThatThrownBy(() -> author.getBooks().size())
            .isInstanceOf(LazyInitializationException.class);
    }
}
~~~

Test giả định dữ liệu Author đã tồn tại và books chưa được khởi tạo. Test không được đánh dấu @Transactional ở cấp lớp hoặc method, nếu không transaction test có thể giữ persistence context mở và che mất lỗi.

Test cho cách sửa:

~~~java
@Test
void dtoContainsBooksLoadedInsideServiceTransaction() {
    AuthorDetailDto detail = authorService.getDetail(existingAuthorId);

    assertThat(detail.books()).isNotEmpty();
}
~~~

Method getDetail dùng EntityGraph hoặc JOIN FETCH để tải books rồi map sang DTO trong transaction. Sau khi trả về, DTO vẫn đọc được vì nó không phụ thuộc Hibernate Session.

Khi kiểm thử N+1, tạo nhiều Author với nhiều Book, bật SQL logging hoặc Hibernate Statistics, rồi xác nhận số truy vấn không tăng tuyến tính theo số Author. Kiểm tra cả trường hợp collection rỗng và association có nhiều phần tử.

## 16. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| LazyInitializationException khi serialize JSON | Controller trả entity có association chưa tải | Map sang DTO trong transaction |
| Thêm @Transactional nhưng vẫn lỗi | Association không được truy cập trong transaction hoặc transaction proxy không hoạt động | Kiểm tra call path, fetch plan và self-invocation |
| Đổi sang EAGER làm query chậm | Tất cả use case tải dữ liệu không cần thiết | Giữ fetch plan theo use case |
| OSIV tắt thì API lỗi | API phụ thuộc lazy loading trong serialization | Tải dữ liệu cần thiết trong service |
| Có N+1 dù không còn exception | Mapper/serializer truy cập collection của từng entity | EntityGraph, DTO query hoặc batch fetching |
| Page bị sai/đắt khi fetch collection | Join collection nhân dòng khi phân trang | Phân trang ID trước rồi tải chi tiết |
| Hibernate.initialize vẫn lỗi | Gọi sau khi Session đã đóng | Khởi tạo trong transaction hoặc đổi fetch plan |
| DTO mapper gây nhiều SQL | Mapper đọc association LAZY chưa được fetch | Chọn query/fetch plan trước khi map |
| JSON có vòng lặp Author-Book | Serialize quan hệ hai chiều trực tiếp | Dùng DTO cho response |
| Test không tái hiện lỗi | Test transaction hoặc OSIV giữ context mở | Test ngoài transaction và tắt OSIV |

## 17. Checklist thiết kế ranh giới đọc dữ liệu

- [ ] Xác định endpoint/use case cần những field và association nào.
- [ ] Giữ association LAZY khi phù hợp; không đổi toàn bộ sang EAGER để chữa exception.
- [ ] Dùng transaction service bao trùm việc đọc và map DTO.
- [ ] Kiểm tra @Transactional có thực sự đi qua Spring proxy.
- [ ] Dùng EntityGraph hoặc JOIN FETCH cho association cần thiết.
- [ ] Dùng DTO projection trực tiếp khi chỉ cần dữ liệu đọc.
- [ ] Tránh fetch collection cùng pagination nếu chưa xử lý cardinality.
- [ ] Dùng batch fetching khi nhiều collection LAZY được truy cập theo nhóm.
- [ ] Không để JSON serializer quyết định fetch plan.
- [ ] Đánh giá OSIV có phù hợp; ưu tiên response DTO độc lập persistence context.
- [ ] Kiểm tra SQL để phát hiện N+1 và tải thừa.
- [ ] Kiểm thử cả trường hợp Session đóng và association chưa khởi tạo.

## 18. Kết luận

**LazyInitializationException** thường xuất hiện khi Hibernate cần tải một proxy hoặc collection LAZY nhưng entity đã detached và Session đã đóng. @Transactional chỉ giữ persistence context trong phạm vi transaction; nó không tự tải mọi association.

Hãy thiết kế ranh giới đọc dữ liệu theo từng use case: tải association cần thiết bằng EntityGraph hoặc JOIN FETCH, hoặc truy vấn thẳng DTO; map dữ liệu trong transaction rồi trả DTO qua controller. Kiểm tra OSIV, N+1, phân trang collection và SQL thực tế để API không phụ thuộc vào việc serializer vô tình truy cập entity sau khi transaction kết thúc.