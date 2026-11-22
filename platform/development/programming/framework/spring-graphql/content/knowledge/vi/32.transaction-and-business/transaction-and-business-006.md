# Persistence context và nested field

Trong ứng dụng Spring for GraphQL dùng Spring Data JPA, một root resolver có thể tải entity rồi trả entity đó cho GraphQL. Sau đó GraphQL tiếp tục gọi các resolver của field lồng nhau như author, reviews hoặc category. Nếu các field con truy cập lazy association sau khi transaction của root service đã kết thúc, ứng dụng có thể gặp LazyInitializationException. Nếu Open EntityManager in View đang bật, lỗi có thể biến mất nhưng các truy vấn SQL lại phát sinh âm thầm trong lúc GraphQL phân giải từng field, dẫn đến N+1 và thời gian truy cập database khó kiểm soát.

Để xử lý đúng, cần hiểu ba khái niệm:

- Persistence context là phạm vi EntityManager quản lý các entity đang được theo dõi.
- Transaction là phạm vi commit/rollback và isolation của thao tác database.
- Nested GraphQL field là một lần phân giải field dựa trên source object do field cha trả về.

Ba phạm vi này có liên quan nhưng không đồng nhất. Một entity có thể vẫn nằm trong persistence context sau khi transaction đã kết thúc nếu ứng dụng dùng Open EntityManager in View. Ngược lại, transaction có thể kết thúc và persistence context cũng đóng ngay khi service method trả về. Thiết kế resolver cần chủ động xác định dữ liệu nào phải được tải trước, dữ liệu nào được tải qua service riêng và dữ liệu nào nên được batch bằng DataLoader.

## Persistence context là gì?

Persistence context là tập hợp các entity instance được một EntityManager quản lý. Trong một persistence context, JPA duy trì identity của entity: cùng một entity type và primary key được tham chiếu tới cùng một managed instance.

Persistence context đảm nhiệm:

- Theo dõi entity mới, entity đã tải và entity bị đánh dấu xóa.
- Phát hiện thay đổi trên managed entity để đồng bộ với database.
- Duy trì identity map, tránh tạo nhiều managed instance cho cùng một bản ghi trong cùng context.
- Quản lý lazy proxy và persistent collection.
- Đồng bộ thay đổi xuống database khi flush hoặc commit.

Persistence context thường được gọi là first-level cache. Nó gắn với EntityManager, không phải cache dùng chung toàn ứng dụng. Khi EntityManager kết thúc hoặc entity bị detach, entity không còn được persistence context theo dõi.

## Vòng đời entity trong JPA

Một entity có thể đi qua các trạng thái:

| Trạng thái | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| New / transient | Object Java mới, chưa được persistence context quản lý | new BookEntity(...) |
| Managed | Entity đang được EntityManager theo dõi | find(), getReference(), persist() |
| Detached | Entity từng được quản lý nhưng đã tách khỏi persistence context | Entity sau khi EntityManager đóng hoặc detach() |
| Removed | Entity managed đã được đánh dấu xóa | remove(entity) |

Sơ đồ vòng đời đơn giản:

~~~mermaid
stateDiagram-v2
    [*] --> Transient
    Transient --> Managed: persist()
    Managed --> Detached: detach() / clear() / close()
    Detached --> Managed: merge() returns managed copy
    Managed --> Removed: remove()
    Removed --> [*]: commit
~~~

Các thao tác thường gặp:

- persist(entity): đưa entity mới vào trạng thái managed; câu lệnh INSERT có thể được thực thi khi flush hoặc commit.
- find(...): tìm entity; nếu entity đã có trong persistence context thì có thể trả lại managed instance đang được theo dõi.
- detach(entity): tách một entity khỏi persistence context.
- clear(): detach toàn bộ entity đang được quản lý.
- close(): đóng EntityManager và kết thúc persistence context.
- remove(entity): đánh dấu entity managed để xóa khi flush/commit.
- merge(detached): sao chép trạng thái từ object detached sang một managed instance và trả về managed instance đó.

Điểm dễ nhầm là merge() không biến object detached ban đầu thành managed. Hãy dùng object được trả về:

~~~java
BookEntity managedBook = entityManager.merge(detachedBook);
managedBook.setTitle("New title");
~~~

Nếu tiếp tục thay đổi detachedBook, các thay đổi đó không được persistence context theo dõi.

## EntityManager và transaction

EntityManager là API làm việc với persistence context. EntityManagerFactory có thể được chia sẻ giữa nhiều thread, nhưng một EntityManager thực tế không thread-safe và không được dùng đồng thời từ nhiều thread.

Trong Spring, cách inject phổ biến:

~~~java
@Repository
public class BookDao {

    @PersistenceContext
    private EntityManager entityManager;

    public BookEntity findById(String id) {
        return entityManager.find(BookEntity.class, id);
    }
}
~~~

Với PersistenceContextType.TRANSACTION mặc định, Spring inject một shared EntityManager proxy. Proxy này ủy quyền cho EntityManager gắn với transaction hiện tại. Nó không có nghĩa một EntityManager thực tế được chia sẻ đồng thời giữa tất cả request.

Khi service method có @Transactional chạy, Spring transaction manager mở hoặc tham gia transaction và gắn EntityManager tương ứng vào execution context. Khi transaction kết thúc, EntityManager transaction-scoped thường được đóng hoặc trả về quản lý của provider; entity được trả ra ngoài trở thành detached nếu không còn persistence context khác giữ nó.

Không lưu EntityManager thực tế vào static field, singleton state hoặc chia sẻ nó giữa các resolver chạy song song. Hãy inject shared proxy qua @PersistenceContext hoặc dùng Spring Data repository để Spring chọn đúng EntityManager theo transaction hiện hành.

## Flush không phải commit

Persistence context có thể giữ các thay đổi trong bộ nhớ trước khi gửi SQL xuống database. Flush đồng bộ trạng thái managed entity với database connection hiện tại:

~~~java
entityManager.flush();
~~~

Flush không kết thúc transaction và không đồng nghĩa dữ liệu đã commit. Transaction có thể tiếp tục, sau đó rollback toàn bộ thay đổi đã flush. Commit là bước hoàn tất transaction theo quy tắc database.

Với query chỉ đọc, Hibernate có thể tối ưu dirty checking hoặc flush behavior khi transaction được đánh dấu read-only. Tuy nhiên, read-only không thay thế persistence context và không làm entity tự động detached.

## Nested GraphQL field sử dụng source object như thế nào?

GraphQL thực thi field cha trước khi phân giải các field con cần dữ liệu từ kết quả đó. Giá trị mà resolver cha trả về trở thành source object của nested resolver.

Ví dụ schema:

~~~graphql
type Query {
  book(id: ID!): Book
}

type Book {
  id: ID!
  title: String!
  author: Author
  reviews: [Review!]!
}

type Author {
  id: ID!
  name: String!
}

type Review {
  id: ID!
  rating: Int!
}
~~~

Root resolver:

~~~java
@Controller
public class BookController {

    private final BookQueryService bookQueryService;

    public BookController(BookQueryService bookQueryService) {
        this.bookQueryService = bookQueryService;
    }

    @QueryMapping
    public BookEntity book(@Argument String id) {
        return bookQueryService.findEntity(id);
    }
}
~~~

Nested resolver:

~~~java
@Controller
public class BookFieldController {

    @SchemaMapping(typeName = "Book", field = "author")
    public AuthorEntity author(BookEntity book) {
        return book.getAuthor();
    }
}
~~~

Tham số BookEntity book là source object do field cha trả về. Nếu author là lazy association, việc gọi book.getAuthor() có thể cần truy vấn database.

Điều quan trọng: transaction của service method findEntity() thường kết thúc khi method trả về. Việc GraphQL tiếp tục phân giải author là một bước khác. Không giả định transaction của service root vẫn mở cho đến khi toàn bộ GraphQL response được tạo.

## Lazy association và lỗi LazyInitializationException

JPA cho phép trì hoãn tải association. Với LAZY, entity giữ proxy hoặc persistent collection và chỉ truy vấn database khi code truy cập dữ liệu đó.

Ví dụ entity:

~~~java
@Entity
public class BookEntity {

    @Id
    private String id;

    private String title;

    @ManyToOne(fetch = FetchType.LAZY)
    private AuthorEntity author;

    @OneToMany(mappedBy = "book", fetch = FetchType.LAZY)
    private List<ReviewEntity> reviews = new ArrayList<>();

    // getters
}
~~~

Theo mặc định của JPA, quan hệ to-one như @ManyToOne và @OneToOne là EAGER, còn quan hệ to-many như @OneToMany và @ManyToMany là LAZY. Có thể chỉ định fetch mode rõ ràng trong mapping; với GraphQL, nên cân nhắc LAZY cho association không phải lúc nào cũng được chọn và xác định fetch plan theo từng use case.

Service chỉ tải Book:

~~~java
@Service
public class BookQueryService {

    private final BookRepository bookRepository;

    public BookQueryService(BookRepository bookRepository) {
        this.bookRepository = bookRepository;
    }

    @Transactional(readOnly = true)
    public BookEntity findEntity(String id) {
        return bookRepository.findById(id)
                .orElseThrow(() -> new BookNotFoundException(id));
    }
}
~~~

Nếu transaction kết thúc và persistence context đóng trước khi nested resolver truy cập book.getAuthor().getName(), Hibernate không thể tải proxy nữa và có thể ném LazyInitializationException.

Lỗi này thường cho thấy ứng dụng đang truy cập lazy state của entity detached. Không giải quyết nó bằng cách đổi tất cả association sang EAGER. EAGER có thể khiến dữ liệu được tải thừa, tạo thêm truy vấn hoặc làm query plan khó dự đoán.

## EAGER không bảo đảm một SQL join

FetchType.EAGER chỉ yêu cầu provider phải tải association khi entity được lấy. Nó không bảo đảm association được tải bằng một câu SQL JOIN duy nhất.

Với nhiều entity trong danh sách, EAGER có thể tạo nhiều truy vấn phụ. Ngược lại, LAZY giúp trì hoãn tải nhưng cần fetch plan rõ ràng khi biết GraphQL selection set cần dữ liệu nào.

Hướng thiết kế thường dùng:

- Giữ association ở LAZY nếu không phải lúc nào cũng cần.
- Chọn fetch plan theo use case hoặc GraphQL field.
- Dùng DTO projection khi response chỉ cần một phần dữ liệu.
- Dùng EntityGraph hoặc fetch join khi cần tải association cụ thể.
- Dùng DataLoader/@BatchMapping cho quan hệ cần tải theo nhiều parent.

## Open EntityManager in View (OSIV)

Open EntityManager in View giữ một EntityManager mở và gắn với request thread trong suốt quá trình xử lý web request. Mục đích ban đầu là cho phép lazy loading khi render view dù service transaction đã kết thúc.

Trong ứng dụng web Servlet, Spring Boot mặc định đăng ký OpenEntityManagerInViewInterceptor khi JPA được cấu hình. Có thể tắt bằng:

~~~yaml
spring:
  jpa:
    open-in-view: false
~~~

OSIV giữ persistence context mở theo request, nhưng không giữ transaction service mở xuyên suốt request. Khi service transaction kết thúc, entity có thể vẫn managed trong EntityManager do OSIV giữ. Nếu GraphQL nested resolver truy cập lazy association trong cùng request thread, provider có thể thực hiện thêm SQL dù transaction nghiệp vụ ban đầu đã hoàn tất.

Vì vậy, bật OSIV có thể làm LazyInitializationException biến mất nhưng vẫn còn các vấn đề:

- SQL phát sinh muộn ở nested resolver, khó xác định từ service method.
- Mỗi parent entity có thể kích hoạt một query lazy riêng, tạo N+1.
- Các truy vấn lazy có thể chạy ngoài transaction nghiệp vụ ban đầu, nên không chia sẻ cùng snapshot/isolation với dữ liệu root.
- GraphQL response phụ thuộc vào số field và số phần tử mà client yêu cầu.
- Persistence context và trạng thái entity bị giữ lâu hơn. Thời điểm acquire/release database connection còn phụ thuộc provider và transaction configuration.

OSIV không phải transaction boundary và không nên được dùng làm chiến lược tải dữ liệu cho GraphQL.

### Tắt OSIV để phát hiện lỗi sớm

Trong môi trường phát triển và integration test, có thể tắt OSIV:

~~~yaml
spring:
  jpa:
    open-in-view: false
~~~

Khi đó, nếu resolver cố truy cập lazy association sau transaction, lỗi xuất hiện ngay tại test. Đây là cách hữu ích để phát hiện code đang phụ thuộc ngầm vào persistence context mở suốt request.

Tắt OSIV không bắt buộc mọi ứng dụng phải trả DTO cho tất cả field. Tuy nhiên, nó buộc mỗi service/resolver xác định rõ cách tải dữ liệu và transaction boundary.

### OSIV và GraphQL execution bất đồng bộ

OSIV gắn EntityManager với request thread và có cơ chế xử lý async dispatch của Servlet. Tuy nhiên, GraphQL Java có thể thực thi data fetcher trên executor khác, hoặc ứng dụng có thể chuyển công việc sang CompletableFuture/executor riêng.

EntityManager thực tế không thread-safe. Không chia sẻ entity manager hoặc persistence context giữa các resolver chạy song song. Cũng không giả định một EntityManager gắn với request thread tự động có mặt trên mọi thread do ứng dụng tạo ra.

Nếu nested resolver chạy trên thread khác, hãy tải dữ liệu qua service method riêng với transaction phù hợp hoặc dùng DataLoader để batch. Với JPA, mỗi service invocation cần sử dụng EntityManager được Spring quản lý trong execution context của nó.

## Thiết kế nested field bằng DTO

Cách dễ kiểm soát nhất là service tải đủ dữ liệu cho use case và chuyển thành DTO trước khi transaction kết thúc.

DTO:

~~~java
public record AuthorView(String id, String name) {
}

public record BookDetailsView(
        String id,
        String title,
        AuthorView author) {
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
    public BookDetailsView findDetails(String id) {
        BookEntity book = bookRepository.findWithAuthorById(id)
                .orElseThrow(() -> new BookNotFoundException(id));

        AuthorEntity author = book.getAuthor();

        return new BookDetailsView(
                book.getId(),
                book.getTitle(),
                new AuthorView(author.getId(), author.getName()));
    }
}
~~~

Repository:

~~~java
import org.springframework.data.jpa.repository.EntityGraph;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface BookRepository
        extends JpaRepository<BookEntity, String> {

    @EntityGraph(attributePaths = "author")
    Optional<BookEntity> findWithAuthorById(String id);
}
~~~

Root resolver trả DTO:

~~~java
@QueryMapping
public BookDetailsView book(@Argument String id) {
    return bookQueryService.findDetails(id);
}
~~~

GraphQL có thể đọc author từ BookDetailsView như một property. Không còn lazy proxy trong response path và không cần giữ persistence context mở khi GraphQL xử lý field author.

DTO cũng giúp kiểm soát dữ liệu nào được expose ra GraphQL, tránh vô tình trả thêm field nội bộ của entity.

## Dùng projection để chỉ tải field cần thiết

Nếu GraphQL response chỉ cần một số scalar field, projection có thể tránh tải toàn bộ entity.

Interface projection:

~~~java
public interface BookSummary {
    String getId();
    String getTitle();
    String getAuthorName();
}
~~~

Repository:

~~~java
public interface BookRepository
        extends JpaRepository<BookEntity, String> {

    @Query("""
            select b.id as id,
                   b.title as title,
                   a.name as authorName
            from BookEntity b
            join b.author a
            where b.id = :id
            """)
    Optional<BookSummary> findSummaryById(@Param("id") String id);
}
~~~

Projection chỉ đưa ra các thuộc tính cần thiết. Spring Data JPA có thể tạo proxy projection hoặc thực hiện DTO projection tùy loại projection và query. Không cần expose entity hoặc truy cập lazy collection nếu GraphQL chỉ chọn ba field trên.

Với DTO class/record projection, khai báo constructor phù hợp với select clause:

~~~java
public record BookSummaryView(
        String id,
        String title,
        String authorName) {
}
~~~

~~~java
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

@Query("""
        select new com.example.graphql.BookSummaryView(
            b.id, b.title, a.name)
        from BookEntity b
        join b.author a
        where b.id = :id
        """)
Optional<BookSummaryView> findSummaryViewById(@Param("id") String id);
~~~

Tên class trong JPQL constructor expression phải là fully qualified class name.

## Dùng fetch join có kiểm soát

Fetch join tải association cùng với entity trong một truy vấn:

~~~java
@Query("""
        select b
        from BookEntity b
        join fetch b.author
        where b.id = :id
        """)
Optional<BookEntity> findWithAuthor(String id);
~~~

Sau khi service lấy Book và map sang DTO trong transaction, nested GraphQL field không cần truy cập lazy association.

Fetch join phù hợp cho quan hệ to-one hoặc một collection nhỏ được kiểm soát. Tránh fetch join đồng thời nhiều collection to-many trong cùng query vì có thể nhân số dòng kết quả, tạo Cartesian multiplication và làm pagination sai hoặc không được provider hỗ trợ.

Nếu cần phân trang Book và tải thêm reviews, hãy phân trang Book trước rồi batch tải reviews cho danh sách ID. Không fetch join collection lớn vào query phân trang chỉ để tránh LazyInitializationException.

## EntityGraph cho fetch plan theo use case

EntityGraph mô tả association cần tải cho một query mà không phải viết fetch join trong JPQL:

~~~java
public interface BookRepository
        extends JpaRepository<BookEntity, String> {

    @EntityGraph(attributePaths = {"author"})
    Optional<BookEntity> findWithAuthorById(String id);
}
~~~

Có thể dùng nested path:

~~~java
@EntityGraph(attributePaths = {
        "author",
        "publisher.address"
})
Optional<BookEntity> findDetailedById(String id);
~~~

EntityGraph là fetch plan, không phải cam kết rằng provider luôn tạo đúng một SQL statement. Hãy kiểm tra SQL thực tế và execution plan khi tối ưu hiệu năng.

EntityGraph hữu ích khi một use case cần một tập association ổn định. Nếu GraphQL query có nhiều tổ hợp field tùy client, không nên tạo một EntityGraph khổng lồ cho mọi trường hợp; hãy dùng projection, query service riêng hoặc DataLoader theo field.

## Dùng DataLoader hoặc @BatchMapping cho nested collection

Một danh sách Book có thể yêu cầu reviews cho từng Book:

~~~graphql
query Books {
  books {
    id
    title
    reviews {
      id
      rating
    }
  }
}
~~~

Nếu resolver reviews gọi repository một lần cho mỗi Book, số truy vấn tăng theo số parent:

~~~java
@SchemaMapping(typeName = "Book", field = "reviews")
public List<ReviewView> reviews(BookView book) {
    return reviewQueryService.findByBookId(book.id());
}
~~~

Với N Book, cách này có thể tạo N truy vấn reviews. DataLoader/@BatchMapping gom các ID thành một batch.

Batch service:

~~~java
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ReviewQueryService {

    private final ReviewRepository reviewRepository;

    public ReviewQueryService(ReviewRepository reviewRepository) {
        this.reviewRepository = reviewRepository;
    }

    @Transactional(readOnly = true)
    public Map<String, List<ReviewView>> findByBookIds(
            Set<String> bookIds) {

        return reviewRepository.findByBookIdIn(bookIds).stream()
                .map(ReviewView::from)
                .collect(Collectors.groupingBy(ReviewView::bookId));
    }
}
~~~

Batch mapping:

~~~java
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;

import org.springframework.graphql.data.method.annotation.BatchMapping;
import org.springframework.stereotype.Controller;

@Controller
public class BookReviewController {

    private final ReviewQueryService reviewQueryService;

    public BookReviewController(ReviewQueryService reviewQueryService) {
        this.reviewQueryService = reviewQueryService;
    }

    @BatchMapping(typeName = "Book", field = "reviews")
    public Map<BookView, List<ReviewView>> reviews(List<BookView> books) {
        Set<String> ids = books.stream()
                .map(BookView::id)
                .collect(Collectors.toSet());

        Map<String, List<ReviewView>> byBook =
                reviewQueryService.findByBookIds(ids);

        Map<BookView, List<ReviewView>> result = new HashMap<>();
        for (BookView book : books) {
            result.put(
                    book,
                    byBook.getOrDefault(book.id(), List.of()));
        }
        return result;
    }
}
~~~

Batch service mở một transaction read-only cho lần truy vấn theo tập ID. Kết quả được chuyển thành DTO trước khi method kết thúc. DataLoader cache là cache theo GraphQL request; nó không phải persistence context và không cung cấp transaction isolation.

Ví dụ trả Map đồng bộ phù hợp với Servlet stack hoặc executor đã dành riêng cho blocking data fetcher. Với WebFlux, có thể trả Mono và offload lời gọi JPA sang boundedElastic:

~~~java
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;

import org.springframework.graphql.data.method.annotation.BatchMapping;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

@BatchMapping(typeName = "Book", field = "reviews")
public Mono<Map<BookView, List<ReviewView>>> reviews(
        List<BookView> books) {

    Set<String> ids = books.stream()
            .map(BookView::id)
            .collect(Collectors.toSet());

    return Mono.fromCallable(() -> reviewQueryService.findByBookIds(ids))
            .subscribeOn(Schedulers.boundedElastic())
            .map(byBook -> {
                Map<BookView, List<ReviewView>> result = new HashMap<>();
                for (BookView book : books) {
                    result.put(
                            book,
                            byBook.getOrDefault(book.id(), List.of()));
                }
                return result;
            });
}
~~~

Transaction JPA được mở bên trong service method khi callable chạy trên worker thread. Không giữ EntityManager từ request thread rồi truyền sang boundedElastic; để Spring transaction manager cung cấp persistence context cho service invocation đó.

Nếu dùng entity làm key của Map trả về từ @BatchMapping, hãy bảo đảm equals/hashCode ổn định. DTO record thường có equality theo giá trị; với entity có equals/hashCode phụ thuộc field mutable hoặc lazy association, có thể dùng một source DTO ổn định hoặc DataLoader key theo ID.

## Dùng DataLoader theo ID để tránh phụ thuộc entity key

Một cách khác là root resolver trả DTO có authorId, sau đó nested resolver dùng DataLoader theo ID:

~~~java
public record BookView(
        String id,
        String title,
        String authorId) {
}
~~~

~~~java
import java.util.concurrent.CompletableFuture;

import org.dataloader.DataLoader;
import org.springframework.graphql.data.method.annotation.SchemaMapping;

@SchemaMapping(typeName = "Book", field = "author")
public CompletableFuture<AuthorView> author(
        BookView book,
        DataLoader<String, AuthorView> authorLoader) {
    return authorLoader.load(book.authorId());
}
~~~

Batch loader đăng ký bằng BatchLoaderRegistry:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.graphql.execution.BatchLoaderRegistry;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

@Configuration
public class AuthorDataLoaderConfiguration {

    public AuthorDataLoaderConfiguration(
            BatchLoaderRegistry registry,
            AuthorQueryService authorQueryService) {

        registry.forTypePair(String.class, AuthorView.class)
                .registerMappedBatchLoader((authorIds, environment) ->
                        Mono.fromCallable(() ->
                                        authorQueryService.findViewsByIds(authorIds))
                                .subscribeOn(Schedulers.boundedElastic()));
    }
}
~~~

Service:

~~~java
import java.util.Map;
import java.util.Set;
import java.util.function.Function;
import java.util.stream.Collectors;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class AuthorQueryService {

    private final AuthorRepository authorRepository;

    public AuthorQueryService(AuthorRepository authorRepository) {
        this.authorRepository = authorRepository;
    }

    @Transactional(readOnly = true)
    public Map<String, AuthorView> findViewsByIds(Set<String> ids) {
        return authorRepository.findAllById(ids).stream()
                .map(AuthorView::from)
                .collect(Collectors.toMap(
                        AuthorView::id,
                        Function.identity()));
    }
}
~~~

DataLoader chỉ giữ author ID và kết quả DTO. JPA entity được tải và map bên trong service transaction. Không để entity detached mang lazy association đi qua nhiều resolver.

## Persistence context không phải DataLoader cache

Hai cơ chế này có mục đích khác nhau:

| Cơ chế | Phạm vi | Mục tiêu |
| --- | --- | --- |
| Persistence context | EntityManager | Theo dõi entity state, identity và dirty checking |
| DataLoader cache | Thường theo GraphQL request | Gộp và cache kết quả tải dữ liệu theo key |
| Second-level cache | Theo EntityManagerFactory/provider | Cache entity/query giữa nhiều persistence context |
| Application cache | Theo cấu hình ứng dụng | Cache DTO hoặc dữ liệu nghiệp vụ theo key |

DataLoader có thể tránh gọi batch service nhiều lần cho cùng key trong một GraphQL request. Nhưng DataLoader không làm entity trở thành managed và không kéo dài EntityManager lifecycle.

Second-level cache cũng không thay thế persistence context. Nó là cache cấp provider, còn mỗi transaction vẫn có persistence context riêng.

## Nested resolver chạy song song và giới hạn EntityManager

GraphQL có thể phân giải các field độc lập song song. Ví dụ, một query lấy nhiều Book và yêu cầu author cùng reviews cho từng Book. Resolver của các field có thể được thực thi bằng executor hoặc asynchronous data fetcher.

EntityManager thực tế không thread-safe. Vì vậy:

- Không truyền một EntityManager thực tế vào nhiều resolver chạy đồng thời.
- Không chia sẻ một persistence context thủ công giữa các thread.
- Không giữ managed entity rồi truy cập lazy collection tùy ý từ callback chạy trên thread khác.
- Dùng service method có transaction riêng để tải dữ liệu cần thiết.
- Dùng DataLoader để gom các yêu cầu tương tự và trả DTO.

Shared EntityManager proxy của Spring giúp bean singleton có thể inject EntityManager an toàn theo cách Spring quản lý. Điều đó không làm cho entity manager thực tế bên dưới trở thành thread-safe.

Với WebFlux, JPA vẫn là blocking persistence API. Không gọi JPA blocking trực tiếp trên event-loop thread. Nếu ứng dụng cần reactive end-to-end, cân nhắc R2DBC và thiết kế data access theo reactive transaction/context; R2DBC không dùng JPA EntityManager hoặc JPA persistence context.

## Đọc dữ liệu và consistency giữa các nested field

Nếu root service tải Book trong transaction A, còn nested resolver gọi Author service trong transaction B, hai truy vấn có thể nhìn thấy dữ liệu ở hai thời điểm khác nhau.

Ví dụ:

1. Transaction A đọc Book và authorId.
2. Một transaction khác cập nhật Author.
3. Transaction B đọc Author sau khi cập nhật.
4. GraphQL response chứa Book từ thời điểm trước và Author từ thời điểm sau.

Điều này có thể chấp nhận với màn hình thông tin thông thường. Nếu nghiệp vụ yêu cầu snapshot nhất quán, hãy gom dữ liệu liên quan vào cùng service use case và transaction với isolation phù hợp, rồi trả DTO tổng hợp.

Không cố giữ một EntityManager mở cho toàn bộ GraphQL operation để giải quyết consistency. Persistence context mở lâu không tự tạo một database snapshot nhất quán; transaction isolation mới quyết định mức độ nhìn thấy thay đổi đồng thời.

## Kiểm thử nested field khi tắt OSIV

Integration test nên chạy với:

~~~yaml
spring:
  jpa:
    open-in-view: false
~~~

Điều này giúp phát hiện resolver đang truy cập lazy association ngoài transaction.

Các tình huống nên kiểm tra:

| Kịch bản | Điều cần xác minh |
| --- | --- |
| Root query trả Book DTO | GraphQL đọc scalar field mà không cần EntityManager mở |
| Nested author dùng projection | Field author trả đúng dữ liệu, không lazy load |
| Nested field truy cập lazy association sau transaction | Test phát hiện lỗi và buộc sửa fetch plan |
| @EntityGraph/fetch join | Association cần thiết đã được tải trước khi service trả DTO |
| Danh sách Book có reviews | Batch loader chạy một batch hoặc số batch dự kiến |
| DataLoader cùng key | Kết quả được cache trong request theo đúng semantics |
| Hai request song song | Không chia sẻ EntityManager hoặc state persistence context |
| WebFlux và JPA | Không chạy blocking JPA trên event loop |

Ví dụ GraphQL test:

Dependency kiểm thử cần có spring-graphql-test. Với test HTTP client, thêm Spring WebFlux test support nếu ứng dụng chưa có WebFlux trên classpath:

~~~kotlin
dependencies {
    testImplementation("org.springframework.graphql:spring-graphql-test")
    testImplementation("org.springframework.boot:spring-boot-starter-webflux")
}
~~~

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.graphql.test.tester.HttpGraphQlTester;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class BookNestedFieldTests {

    @Autowired
    private HttpGraphQlTester graphQlTester;

    @Test
    void shouldResolveAuthorWithoutOpenEntityManagerInView() {
        graphQlTester.document("""
                query {
                    book(id: "book-42") {
                        id
                        title
                        author {
                            id
                            name
                        }
                    }
                }
                """)
                .execute()
                .path("book.author.name")
                .entity(String.class)
                .isEqualTo("Ada Lovelace");
    }
}
~~~

Test cần dữ liệu seed có book-42 và author tương ứng. Mục tiêu là chạy toàn bộ GraphQL execution với OSIV tắt và xác minh nested field vẫn hoạt động nhờ fetch plan/DTO hoặc batch service.

Với Spring Boot và RANDOM_PORT, HttpGraphQlTester được auto-configure cho live server khi có spring-graphql-test. Nếu dùng mock web environment, thêm @AutoConfigureHttpGraphQlTester; package của annotation khác nhau giữa các dòng Spring Boot.

Ví dụ package của annotation:

- Spring Boot 4.x: org.springframework.boot.graphql.test.autoconfigure.tester.AutoConfigureHttpGraphQlTester.
- Spring Boot 3.5: org.springframework.boot.test.autoconfigure.graphql.tester.AutoConfigureHttpGraphQlTester.

Để phát hiện N+1, có thể đếm SQL statement trong test bằng datasource proxy hoặc Hibernate statistics. Ví dụ với 20 Book, kiểm tra số query reviews không tăng thành 20. Đừng chỉ xác minh response đúng vì N+1 vẫn có thể trả dữ liệu chính xác.

## Lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| LazyInitializationException ở nested field | Persistence context đã đóng trước khi field con truy cập lazy association | Tải association trong service hoặc trả DTO/projection |
| Tắt OSIV thì GraphQL lỗi | Code đang dựa vào EntityManager mở suốt HTTP request | Thiết kế fetch plan hoặc batch resolver rõ ràng |
| Bật OSIV nhưng query chậm | Lazy load phát sinh trong từng nested resolver | Dùng DataLoader/@BatchMapping và đo SQL count |
| EAGER vẫn có nhiều SQL | EAGER không bảo đảm một join duy nhất | Dùng EntityGraph, fetch join hoặc projection phù hợp |
| Entity bị stale hoặc không cập nhật | Đang dùng detached object hoặc nhầm object sau merge | Dùng managed instance do merge trả về và kiểm soát transaction |
| Nested resolver chạy trên thread khác | Thread-bound persistence context không được chia sẻ | Gọi service riêng hoặc DataLoader; không chia sẻ EntityManager |
| Concurrent resolver lỗi khi dùng EntityManager | EntityManager thực tế bị dùng đồng thời | Không chia sẻ persistence context giữa thread |
| @BatchMapping không tìm được kết quả | Map key không khớp source object hoặc equals/hashCode không ổn định | Dùng DTO key ổn định hoặc DataLoader theo ID |
| N+1 dù đã có transaction | Transaction không tự batch SQL | Dùng DataLoader, @BatchMapping hoặc query theo tập ID |
| Fetch join pagination trả kết quả sai | Fetch join collection làm nhân dòng và ảnh hưởng pagination | Phân trang parent trước, batch tải collection sau |
| WebFlux bị nghẽn | JPA blocking chạy trên event-loop thread | Chuyển blocking work sang scheduler phù hợp hoặc dùng R2DBC |
| Response đọc dữ liệu ở thời điểm khác nhau | Root và nested service chạy transaction riêng | Gom dữ liệu vào một use case nếu cần snapshot nhất quán |

## Nguyên tắc thiết kế persistence context cho nested field

Khi triển khai GraphQL với JPA, hãy nhớ:

1. **Hiểu vòng đời entity.** Managed entity chỉ được theo dõi trong persistence context; entity detached không còn lazy loading đáng tin cậy.
2. **Phân biệt transaction và persistence context.** OSIV có thể giữ EntityManager mở sau khi transaction service đã kết thúc.
3. **Đặt transaction tại service.** Mỗi service method xác định rõ phạm vi truy cập database và mapping DTO.
4. **Không trả entity có lazy association tùy tiện.** GraphQL có thể gọi nested resolver sau khi transaction của root service kết thúc.
5. **Ưu tiên DTO/projection.** Chỉ tải và expose dữ liệu mà GraphQL field cần.
6. **Chọn fetch plan rõ ràng.** Dùng EntityGraph hoặc fetch join có kiểm soát, tránh EAGER đại trà.
7. **Batch quan hệ lặp lại.** Dùng DataLoader/@BatchMapping cho nested field của danh sách.
8. **Không chia sẻ EntityManager giữa thread.** Shared proxy của Spring không làm EntityManager thực tế thread-safe.
9. **Không dựa vào OSIV để che N+1.** Tắt OSIV trong test giúp phát hiện lazy access ngoài transaction.
10. **Chọn consistency theo nghiệp vụ.** Nếu cần một snapshot, gom truy vấn vào cùng transaction và isolation phù hợp.
11. **Đo SQL thực tế.** Response đúng không có nghĩa query plan hiệu quả.
12. **Tôn trọng web stack.** JPA là blocking; WebFlux reactive cần xử lý persistence theo đúng execution model.

Persistence context quản lý vòng đời và trạng thái của entity, còn nested GraphQL field tiếp tục phân giải dữ liệu từ source object mà field cha trả về. Khi root service transaction kết thúc, entity có thể trở thành detached và lazy association không còn tải được. Open EntityManager in View có thể giữ persistence context mở trong request nhưng không giữ transaction nghiệp vụ mở, vì vậy dễ che giấu N+1 và truy vấn phát sinh muộn. Thiết kế ổn định là tải dữ liệu bằng DTO/projection hoặc fetch plan trong service transaction, dùng DataLoader/@BatchMapping cho nested field lặp lại, và không chia sẻ EntityManager giữa các thread. Tắt OSIV trong integration test giúp phát hiện sớm các dependency ngầm vào persistence context.

## Tài liệu tham khảo

- [Spring Framework - JPA and EntityManager](https://docs.spring.io/spring-framework/reference/data-access/orm/jpa.html)
- [Spring Boot - Open EntityManager in View](https://docs.spring.io/spring-boot/reference/data/sql.html)
- [Spring Data JPA - Query Methods and EntityGraph](https://docs.spring.io/spring-data/jpa/reference/jpa/query-methods.html)
- [Spring Data JPA - Projections](https://docs.spring.io/spring-data/jpa/reference/repositories/projections.html)
- [Spring for GraphQL - Annotated Controllers](https://docs.spring.io/spring-graphql/reference/controllers.html)
- [Spring for GraphQL - Request Execution and DataLoader](https://docs.spring.io/spring-graphql/reference/request-execution.html)
- [Hibernate ORM - An Introduction to Hibernate 6](https://docs.hibernate.org/orm/6.6/introduction/html_single/)
