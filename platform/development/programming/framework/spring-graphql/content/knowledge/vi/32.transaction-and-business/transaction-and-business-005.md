# Lazy loading trong resolver

Lazy loading là cơ chế ORM trì hoãn việc tải association cho đến khi ứng dụng thật sự truy cập association đó. Với JPA/Hibernate, một resolver GraphQL có thể nhận entity đã được tải từ database, sau đó đọc quan hệ LAZY như author, category hoặc reviews. Lúc này Hibernate có thể phát sinh thêm SQL để khởi tạo proxy hoặc collection.

Trong GraphQL, client tự chọn các field cần đọc và có thể yêu cầu association lồng nhau trên nhiều node. Vì vậy, lazy loading trong resolver rất dễ tạo N+1 query: một truy vấn lấy danh sách cha, sau đó mỗi resolver con lại phát một truy vấn riêng cho từng cha. Nếu persistence context đã đóng, cùng thao tác đó có thể ném LazyInitializationException. Nếu persistence context vẫn mở nhờ Open Session in View, lỗi có thể bị che đi nhưng chi phí truy vấn vẫn tồn tại.

Thiết kế tốt cần xác định dữ liệu nào phải được tải cho từng GraphQL operation, đặt transaction ở application service phù hợp và dùng fetch plan, projection hoặc DataLoader/@BatchMapping để gom truy vấn. Lazy loading vẫn hữu ích, nhưng không nên để một lần gọi getter trong resolver quyết định ngẫu nhiên số lượng SQL của request.

## 1. Lazy loading trong JPA/Hibernate

Entity thường mô tả quan hệ với entity khác:

~~~java
@Entity
public class Book {

    @Id
    private UUID id;

    private String title;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "author_id")
    private Author author;

    @OneToMany(mappedBy = "book", fetch = FetchType.LAZY)
    private List<Review> reviews = new ArrayList<>();

    // getters
}
~~~

Khi truy vấn Book, Hibernate có thể chỉ tải các cột của bảng book. Quan hệ author và reviews chưa nhất thiết được tải. Tùy mapping và provider, Hibernate giữ proxy hoặc persistent collection để biết cách tải dữ liệu khi cần.

~~~java
Book book = bookRepository.findById(bookId).orElseThrow();

// Có thể kích hoạt một truy vấn bổ sung để tải Author.
String authorName = book.getAuthor().getName();

// Có thể kích hoạt truy vấn khác để tải toàn bộ Review.
int reviewCount = book.getReviews().size();
~~~

Lazy loading giúp tránh tải những association không được sử dụng. Nhưng nó chuyển quyết định tải dữ liệu sang thời điểm truy cập. Trong một request GraphQL có nhiều parent object, việc truy cập cùng một association ở từng parent có thể phát sinh nhiều truy vấn nhỏ.

## 2. FetchType LAZY và EAGER

JPA định nghĩa hai fetch type chính:

| Fetch type | Hành vi khái quát | Lưu ý |
| --- | --- | --- |
| LAZY | Provider trì hoãn việc tải association cho đến khi cần | Với một số quan hệ, LAZY là yêu cầu/hint; provider vẫn có thể tải sớm |
| EAGER | Association phải được tải khi entity được lấy | Không đồng nghĩa luôn dùng SQL JOIN; provider có thể phát sinh truy vấn riêng |

Theo mapping mặc định của JPA, to-one như ManyToOne và OneToOne thường là EAGER; to-many như OneToMany và ManyToMany thường là LAZY. Có thể khai báo LAZY tường minh cho to-one để tránh tải rộng ngoài ý muốn, nhưng cần kiểm tra hành vi provider và cấu hình bytecode enhancement nếu ứng dụng dựa vào nó.

Không nên đổi tất cả quan hệ sang EAGER để sửa LazyInitializationException. EAGER có thể tải nhiều dữ liệu không cần thiết, tạo thêm truy vấn hoặc làm đồ thị object quá lớn. Cũng không nên đặt mọi thứ LAZY rồi dựa vào Open Session in View để resolver tùy ý truy cập. Hãy quyết định fetch plan theo use case.

## 3. Resolver GraphQL có thể kích hoạt lazy loading như thế nào?

Giả sử schema:

~~~graphql
type Query {
    books: [Book!]!
}

type Book {
    id: ID!
    title: String!
    author: Author
}

type Author {
    id: ID!
    name: String!
}
~~~

Root resolver tải danh sách Book:

~~~java
@QueryMapping
public List<Book> books() {
    return bookRepository.findAll();
}
~~~

Resolver field author:

~~~java
@SchemaMapping(typeName = "Book", field = "author")
public Author author(Book book) {
    return book.getAuthor();
}
~~~

Khi client chỉ query id và title, field author không được chọn nên resolver author không cần chạy. Khi client query author.name, GraphQL gọi resolver cho từng Book. Mỗi lần gọi book.getAuthor() có thể kích hoạt một lần tải association nếu association chưa được khởi tạo.

GraphQL selection set quyết định resolver nào được gọi. Tuy nhiên, nếu mỗi resolver con truy cập một lazy association riêng trên từng parent, database workload có thể tăng theo số parent trong trang.

## 4. N+1 query do lazy loading

Giả sử query:

~~~graphql
query {
    books {
        id
        title
        author {
            id
            name
        }
    }
}
~~~

Với 50 quyển sách, luồng truy vấn có thể là:

1. Một SQL lấy 50 Book.
2. Resolver author chạy cho Book thứ nhất và tải Author.
3. Resolver author chạy cho Book thứ hai và tải Author.
4. Lặp lại cho các Book còn lại.

Nếu association chưa được cache hoặc các Book có author khác nhau, tổng số truy vấn có thể gần 1 + 50. Đây là N+1 query.

Ví dụ log SQL minh họa:

~~~sql
SELECT id, title, author_id FROM book;
SELECT id, name FROM author WHERE id = ?;
SELECT id, name FROM author WHERE id = ?;
SELECT id, name FROM author WHERE id = ?;
-- lặp lại cho nhiều Book
~~~

Nếu nhiều Book cùng tham chiếu một Author và persistence context đã quản lý Author đó, Hibernate có thể tái sử dụng entity đã tải. Nhưng không nên dựa vào trùng lặp dữ liệu để coi N+1 đã được giải quyết; số query vẫn có thể tăng theo số author duy nhất.

Với collection như reviews, rủi ro còn lớn hơn: mỗi Book có thể kích hoạt một query tải danh sách Review, khiến tổng số row và thời gian xử lý tăng mạnh.

## 5. LazyInitializationException

Hibernate cần một persistence context đang mở để khởi tạo proxy hoặc persistent collection chưa tải. Nếu entity được trả ra ngoài transaction và association được truy cập sau khi EntityManager/Session đã đóng, Hibernate không còn nơi thực hiện SQL.

~~~java
public Book findBook(UUID id) {
    return bookRepository.findById(id).orElseThrow();
}
~~~

Nếu repository method kết thúc transaction và persistence context bị đóng, resolver gọi:

~~~java
@SchemaMapping(typeName = "Book", field = "author")
public Author author(Book book) {
    return book.getAuthor();
}
~~~

có thể gặp:

~~~text
org.hibernate.LazyInitializationException:
could not initialize proxy - no Session
~~~

Lỗi không có nghĩa dữ liệu liên quan không tồn tại. Nó cho biết Hibernate cần tải association nhưng không còn Session phù hợp.

Không nên chữa lỗi bằng cách gọi getter trong một transaction tùy tiện rồi trả entity ra ngoài nếu nested resolver vẫn truy cập association khác sau khi transaction kết thúc. Hãy tải và chuyển dữ liệu cần thiết thành DTO trong ranh giới transaction, hoặc để một service/batch loader chuyên trách tải association trong transaction riêng.

## 6. Transaction boundary và persistence context

Trong ứng dụng Spring, EntityManager thường được gắn với transaction hoặc request theo cơ chế cấu hình. Transaction boundary nên bao quanh một use case dữ liệu cụ thể:

~~~java
@Service
public class BookQueryService {

    private final BookRepository repository;

    public BookQueryService(BookRepository repository) {
        this.repository = repository;
    }

    @Transactional(readOnly = true)
    public BookDetails findDetails(UUID id) {
        Book book = repository.findById(id).orElseThrow();
        return new BookDetails(
            book.getId(),
            book.getTitle(),
            book.getAuthor().getName());
    }
}
~~~

Ở đây, DTO được dựng khi transaction còn hoạt động. Resolver chỉ trả dữ liệu đã được chuẩn bị:

~~~java
@QueryMapping
public BookDetails bookDetails(@Argument UUID id) {
    return bookQueryService.findDetails(id);
}
~~~

Nếu service trả entity chưa khởi tạo association, transaction method có thể kết thúc trước khi GraphQL thực thi các nested resolver. Khi đó, việc lazy load tiếp theo phụ thuộc persistence context khác có còn mở hay không.

Không giả định một transaction trên root resolver tự động bao trùm toàn bộ quá trình GraphQL hoàn tất mọi field con. GraphQL có thể thực thi field theo chiến lược async, DataLoader có thể chạy ở giai đoạn dispatch riêng và publisher có lifecycle khác. Đặt transaction rõ ràng tại service method thực hiện query/batch cần thiết.

EntityManager không thread-safe. Không truyền một persistence context đang mở sang nhiều thread hoặc dùng một EntityManager mutable chung cho các resolver chạy song song.

## 7. Open Session in View không phải cách tối ưu N+1

Open Session in View (OSIV) giữ EntityManager/Session mở trong vòng đời HTTP request để view hoặc code chạy sau service layer có thể lazy load association.

Trong một số cấu hình Spring Boot servlet, OSIV có thể được bật mặc định. Khi đó resolver có thể truy cập association sau khi service method kết thúc mà không gặp LazyInitializationException ngay lập tức.

Tuy nhiên OSIV không giải quyết N+1:

- Getter trong từng resolver vẫn có thể phát SQL riêng.
- Query count có thể phụ thuộc selection set và số node.
- Database access có thể xảy ra ở tầng presentation/resolver ngoài ranh giới service rõ ràng.
- GraphQL async execution có thể dùng thread khác; persistence context gắn với thread không thể được xem là context dùng chung an toàn.
- Request kéo dài có thể giữ persistence context lâu hơn dự kiến.

Có thể cân nhắc tắt OSIV để phát hiện sớm việc truy cập lazy association ngoài transaction:

~~~properties
spring.jpa.open-in-view=false
~~~

Đây là lựa chọn kiến trúc cần kiểm tra với toàn bộ ứng dụng. Nếu tắt OSIV, các use case phải có fetch plan hoặc transaction service rõ ràng. Không bật/tắt OSIV chỉ để làm một test cụ thể xanh mà không hiểu tác động lên các endpoint khác.

## 8. Giải pháp 1: Fetch join cho association cần thiết

Nếu một operation gần như luôn cần author cùng Book, có thể tải bằng fetch join:

~~~java
public interface BookRepository extends JpaRepository<Book, UUID> {

    @Query("""
        select b
        from Book b
        join fetch b.author
        where b.id = :id
        """)
    Optional<Book> findWithAuthorById(UUID id);
}
~~~

Service:

~~~java
@Transactional(readOnly = true)
public BookDetails findDetails(UUID id) {
    Book book = repository.findWithAuthorById(id).orElseThrow();
    return new BookDetails(
        book.getId(),
        book.getTitle(),
        book.getAuthor().getName());
}
~~~

Fetch join phù hợp khi fetch graph nhỏ, xác định và cần thiết cho use case. Nó giúp tránh query bổ sung cho association được join.

Không fetch join mọi quan hệ trong mọi query. Join nhiều collection có thể nhân bản row, tăng dữ liệu truyền từ database và làm sai kết quả phân trang. Với collection to-many, cần đặc biệt cẩn thận khi kết hợp pagination.

## 9. Giải pháp 2: @EntityGraph

Spring Data JPA hỗ trợ @EntityGraph để chỉ định association cần fetch cho một repository method:

~~~java
public interface BookRepository extends JpaRepository<Book, UUID> {

    @EntityGraph(attributePaths = {"author"})
    Optional<Book> findById(UUID id);
}
~~~

Có thể dùng entity graph cho một tập query cụ thể mà không phải viết fetch join trong JPQL. Entity graph có thể được định nghĩa tĩnh trên entity hoặc chỉ định động tại repository method.

~~~java
@EntityGraph(attributePaths = {"author", "category"})
List<Book> findByStatus(BookStatus status);
~~~

Entity graph chỉ là fetch plan. Provider vẫn quyết định cách thực hiện SQL và có thể dùng join hoặc query bổ sung. Hãy kiểm tra SQL thực tế và query count; không kết luận N+1 đã biến mất chỉ vì đã thêm @EntityGraph.

## 10. Giải pháp 3: DTO projection

Nếu GraphQL operation chỉ cần một số field, DTO projection thường rõ ràng và tiết kiệm hơn trả entity:

~~~java
public record BookSummary(
        UUID id,
        String title,
        String authorName) {
}
~~~

JPQL projection:

~~~java
@Query("""
    select new com.example.graphql.BookSummary(
        b.id, b.title, a.name)
    from Book b
    left join b.author a
    where b.status = :status
    order by b.createdAt desc, b.id desc
    """)
List<BookSummary> findSummaries(BookStatus status);
~~~

DTO được tạo từ một query có join rõ ràng. Resolver không còn truy cập proxy của association:

~~~java
@QueryMapping
public List<BookSummary> books(@Argument BookStatus status) {
    return bookQueryService.findSummaries(status);
}
~~~

Projection phù hợp với read model có cấu trúc ổn định. Nếu nhiều GraphQL selection set khác nhau yêu cầu các field khác nhau, có thể tạo các projection/use case phù hợp thay vì tải toàn bộ entity graph cho mọi request.

## 11. Giải pháp 4: DataLoader cho nested association

GraphQL cho phép client chọn field author bên trong từng Book. DataLoader gom các author ID từ nhiều parent object thành một batch:

~~~java
@SchemaMapping(typeName = "Book", field = "author")
public CompletableFuture<Author> author(
        Book book,
        DataLoader<UUID, Author> authorLoader) {

    return authorLoader.load(book.getAuthorId());
}
~~~

Với Spring for GraphQL, đăng ký batch loader qua BatchLoaderRegistry:

~~~java
@Component
public class AuthorBatchLoader {

    public AuthorBatchLoader(
            BatchLoaderRegistry registry,
            AuthorQueryService authorQueryService) {

        registry.forTypePair(UUID.class, Author.class)
            .registerMappedBatchLoader((authorIds, environment) ->
                Mono.fromCallable(() ->
                    authorQueryService.findByIds(authorIds)));
    }
}
~~~

Service tải tất cả author trong một transaction:

~~~java
@Service
public class AuthorQueryService {

    private final AuthorRepository repository;

    public AuthorQueryService(AuthorRepository repository) {
        this.repository = repository;
    }

    @Transactional(readOnly = true)
    public Map<UUID, Author> findByIds(Set<UUID> ids) {
        return repository.findAllById(ids).stream()
            .collect(Collectors.toMap(
                Author::getId,
                Function.identity()));
    }
}
~~~

Ví dụ minh họa mapped batch loader trả về Map theo key. Khi triển khai với JPA blocking trên WebFlux, cần offload truy vấn sang scheduler dành cho blocking I/O và bảo đảm transaction được mở bên trong thread thực hiện truy vấn. Với ứng dụng MVC/imperative, có thể dùng batch method đồng bộ theo execution model của ứng dụng.

DataLoader giữ cache theo GraphQL execution/request. Nhiều resolver gọi load cùng key có thể được gom và dùng chung kết quả. Không chia sẻ DataLoader instance giữa các request hoặc principal; kết quả phụ thuộc tenant/authorization cần có scope phù hợp.

## 12. Giải pháp 5: @BatchMapping

Với trường hợp nested field ánh xạ trực tiếp từ parent object sang related object, @BatchMapping giúp viết batch resolver ngắn hơn:

~~~java
@Controller
public class BookController {

    private final AuthorQueryService authorService;

    public BookController(AuthorQueryService authorService) {
        this.authorService = authorService;
    }

    @BatchMapping(typeName = "Book", field = "author")
    public Map<Book, Author> author(List<Book> books) {
        Set<UUID> authorIds = books.stream()
            .map(Book::getAuthorId)
            .filter(Objects::nonNull)
            .collect(Collectors.toSet());

        Map<UUID, Author> authors = authorService.findByIds(authorIds);

        return books.stream().collect(Collectors.toMap(
            Function.identity(),
            book -> authors.get(book.getAuthorId())));
    }
}
~~~

@BatchMapping tự đăng ký DataLoader cho field tương ứng. Nó phù hợp khi batch function nhận danh sách source object và trả Map từ source sang value. Khi cần key phức tạp, custom cache key hoặc nhiều consumer dùng chung loader, đăng ký DataLoader tường minh có thể linh hoạt hơn.

Nếu JPA chạy blocking trong WebFlux, không thực hiện repository call trực tiếp trên event-loop. Dùng reactive persistence hoặc offload toàn bộ batch operation sang scheduler phù hợp; transaction phải bắt đầu trong execution thread đó.

## 13. Hibernate batch fetching

Hibernate hỗ trợ batch fetching để gom việc khởi tạo nhiều proxy/collection thành ít truy vấn hơn:

~~~java
@BatchSize(size = 32)
@ManyToOne(fetch = FetchType.LAZY)
private Author author;
~~~

Hoặc cấu hình mặc định:

~~~properties
spring.jpa.properties.hibernate.default_batch_fetch_size=32
~~~

Khi một số proxy cùng loại được truy cập trong persistence context, Hibernate có thể tải nhiều association trong một query dùng IN. Đây là tối ưu ở tầng ORM, giúp giảm số query so với N+1 thuần.

Batch fetching không đồng nghĩa với một query duy nhất cho mọi dữ liệu. Số batch còn phụ thuộc số association, batch size, số key và persistence context. Nó cũng không thay thế việc thiết kế fetch plan rõ ràng. Hãy đo query count và latency trước/sau khi cấu hình.

## 14. Cẩn thận với fetch join và pagination collection

Fetch join to-one thường dễ kiểm soát hơn fetch join to-many. Nếu query Book và join fetch reviews, một Book có nhiều Review sẽ tạo nhiều SQL row cho cùng Book.

Khi kết hợp LIMIT/OFFSET hoặc pagination với collection fetch join, database giới hạn row sau join chứ không nhất thiết giới hạn số Book. Hibernate có thể phải thực hiện pagination trong memory hoặc phát cảnh báo; kết quả có thể rất tốn tài nguyên.

Không dùng một query fetch join nhiều collection để tải toàn bộ GraphQL response. Một cách an toàn hơn:

1. Query trang ID của parent theo sort ổn định.
2. Query dữ liệu parent/to-one cần thiết cho các ID đó.
3. Dùng DataLoader hoặc @BatchMapping để tải association to-many theo batch.
4. Giữ nguyên thứ tự ID của trang đầu khi ghép kết quả.

Với collection cần phân trang riêng, thiết kế connection cho collection đó và query theo parent ID cùng cursor. Không tải toàn bộ reviews rồi mới cắt danh sách trong Java.

## 15. Chọn giải pháp theo use case

| Tình huống | Giải pháp phù hợp |
| --- | --- |
| Một query luôn cần một association to-one | Fetch join hoặc @EntityGraph |
| Read API chỉ trả vài field cố định | DTO projection |
| Nhiều Book cùng yêu cầu author | DataLoader hoặc @BatchMapping |
| Nhiều proxy cùng loại được truy cập trong một persistence context | Hibernate batch fetching |
| Collection to-many lớn | Batch loading hoặc connection riêng cho collection |
| Query có pagination và collection association | Page parent trước, batch association sau |
| Nhiều GraphQL selection set khác nhau | Fetch plan theo use case, DTO/read model hoặc DataLoader |

Có thể kết hợp nhiều cách. Ví dụ root query dùng projection cho Book summary, DataLoader tải Author cho các field được chọn và một field reviews dùng connection riêng. Không có một fetch strategy tối ưu cho mọi GraphQL operation.

## 16. Kiểm thử lazy loading và N+1

Test chỉ xác nhận JSON response đúng chưa đủ để chứng minh truy vấn hiệu quả. Cần kiểm tra số lượng SQL hoặc query behavior.

Với Hibernate, có thể bật statistics trong test:

~~~properties
spring.jpa.properties.hibernate.generate_statistics=true
~~~

Sau khi thực thi GraphQL operation, lấy Hibernate Statistics và kiểm tra số prepared statement/query theo fixture. Cần reset statistics trước mỗi test và tránh chạy test song song trên cùng SessionFactory khi assertion phụ thuộc counter toàn cục.

Ví dụ ý tưởng kiểm tra:

~~~java
Statistics statistics = sessionFactory.getStatistics();
statistics.clear();

graphQlTester.document("""
        query {
            books {
                id
                author {
                    name
                }
            }
        }
        """)
    .execute()
    .errors()
    .verify();

long queryCount = statistics.getPrepareStatementCount();
assertThat(queryCount).isLessThanOrEqualTo(3);
~~~

Con số cụ thể phụ thuộc schema, setup test, transaction, cache và query phụ trợ. Không sao chép ngưỡng 3 một cách máy móc; hãy xác định baseline từ test fixture nhỏ, sau đó kiểm tra số query không tăng tuyến tính theo số Book.

Một phép so sánh hữu ích:

- Chạy query với 2 Book và ghi số SQL.
- Chạy cùng query với 20 Book.
- Nếu query count tăng gần 18 lần, có dấu hiệu N+1.
- Nếu query count gần như cố định hoặc tăng theo số batch, batch loading đang hoạt động như mong đợi.

Đối với test repository, dùng database integration test để xác nhận fetch join, entity graph, keyset query và index. Với test GraphQL, dùng GraphQlTester để xác nhận resolver chỉ tải association khi field được chọn.

## 17. Quan sát SQL và hiệu năng

Các công cụ có thể hỗ trợ:

- Hibernate SQL logging trong môi trường phát triển.
- Hibernate Statistics để đếm prepared statements, entity fetch và collection fetch.
- Datasource proxy hoặc JDBC instrumentation để quan sát query count/latency.
- Micrometer Observation và tracing để nối GraphQL field với thời gian xử lý.
- Database slow query log và EXPLAIN ANALYZE để xác định query plan.

Không bật log SQL chi tiết trong production một cách tùy tiện vì có thể làm lộ bind values hoặc tăng I/O. Dùng logging có kiểm soát và mask dữ liệu nhạy cảm.

GraphQL field observation giúp thấy field nào tốn thời gian, nhưng không tự chứng minh có N+1. Cần kết hợp trace, SQL metrics và số lượng parent object. Một field chậm có thể do query scan lớn, network dependency hoặc serialization, không chỉ do lazy loading.

## 18. Kiểm soát selection set và kích thước dữ liệu

GraphQL cho phép client chọn field tùy ý trong giới hạn schema. Một query có thể chọn nhiều association lồng nhau:

~~~graphql
query {
    books {
        author {
            books {
                author {
                    books {
                        id
                    }
                }
            }
        }
    }
}
~~~

Ngay cả khi DataLoader giảm số query, một selection set sâu hoặc rộng vẫn có thể tải lượng dữ liệu rất lớn. Cần cân nhắc depth limit, query complexity/cost limit, page size cap và field-level authorization.

Không tự động fetch toàn bộ entity graph chỉ vì một field được chọn. Hãy giới hạn association theo use case, phân trang collection lớn và chỉ chọn cột cần thiết.

## 19. Lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| LazyInitializationException trong nested resolver | Persistence context đã đóng trước khi association được truy cập | Dùng service transaction, fetch plan hoặc batch loader |
| Response đúng nhưng query rất nhiều | OSIV cho phép lazy load từng parent | Đếm SQL và dùng DataLoader/@BatchMapping |
| Chuyển tất cả quan hệ sang EAGER | Tải thừa dữ liệu và có thể phát sinh query phụ | Fetch theo use case |
| Fetch join collection làm pagination sai/chậm | Join nhân bản row và database limit áp dụng lên row join | Page parent trước, batch collection sau |
| Transaction root resolver không đủ | Nested resolver/async loader chạy sau boundary | Đặt transaction trong service thực hiện batch query |
| Entity trả ra GraphQL có nhiều proxy | Presentation layer phụ thuộc persistence model | Dùng DTO/projection |
| Hibernate batch size không giảm đủ query | Batch fetching chỉ gom proxy trong context và theo batch size | Đo SQL, chọn fetch plan hoặc DataLoader |
| @BatchMapping vẫn query từng item | Batch method gọi repository trong vòng lặp | Thu thập keys rồi query một lần |
| Dùng JPA blocking trên event-loop | Thread bị block và transaction context không phù hợp | Dùng scheduler phù hợp hoặc reactive persistence |
| GraphQL query sâu làm tải quá nhiều dữ liệu | Không giới hạn depth/cost/page size | Áp dụng query complexity và pagination |

## 20. Nguyên tắc thiết kế lazy loading trong resolver

Lazy loading giúp tránh tải association không được sử dụng, nhưng resolver GraphQL có thể kích hoạt nó nhiều lần theo từng parent object. Điều này tạo N+1 hoặc LazyInitializationException tùy persistence context còn mở hay không. Open Session in View có thể che lỗi session đóng, nhưng không phải giải pháp cho số lượng query.

Hãy xác định fetch plan theo operation: dùng fetch join hoặc @EntityGraph cho association nhỏ và luôn cần; dùng DTO projection cho read model ổn định; dùng DataLoader hoặc @BatchMapping cho nested association cần gom theo nhiều parent; cân nhắc Hibernate batch fetching như tối ưu bổ sung. Tránh fetch join collection lớn cùng pagination và không truyền entity có proxy chưa khởi tạo ra ngoài transaction nếu resolver sau đó cần truy cập chúng.

Đặt transaction read-only tại application service thực hiện query hoặc batch load, không chia sẻ EntityManager qua thread và không dựa vào một transaction ở root resolver để bao trùm mọi field GraphQL. Kiểm thử bằng GraphQlTester cùng Hibernate Statistics/SQL instrumentation để xác nhận query count không tăng tuyến tính theo số parent. Lazy loading chỉ an toàn về hiệu năng khi thời điểm và phạm vi tải dữ liệu được kiểm soát.
