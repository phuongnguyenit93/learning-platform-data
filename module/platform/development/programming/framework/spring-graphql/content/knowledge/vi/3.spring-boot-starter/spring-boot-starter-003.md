# Starter cho Spring WebFlux

Trong một ứng dụng Spring for GraphQL, GraphQL starter cung cấp phần tích hợp GraphQL, còn web starter quyết định nền tảng HTTP mà ứng dụng sử dụng. Khi muốn phục vụ GraphQL trên reactive web stack, ứng dụng có thể dùng **spring-boot-starter-webflux**. Starter này đưa Spring WebFlux vào ứng dụng Spring Boot và thường sử dụng Reactor Netty làm web server mặc định.

Spring WebFlux phù hợp với ứng dụng có nhiều tác vụ I/O đồng thời, cần xử lý request theo mô hình non-blocking hoặc đã sử dụng Reactor ở tầng service và truy cập dữ liệu. Khi kết hợp với Spring for GraphQL, các resolver có thể trả về những kiểu reactive như **Mono** và **Flux**, giúp kết quả từ các service bất đồng bộ đi xuyên suốt qua lớp GraphQL.

Điểm cần nhớ là GraphQL và WebFlux giải quyết hai vấn đề khác nhau. GraphQL định nghĩa cách client yêu cầu dữ liệu và cách server phân giải các field. WebFlux là nền tảng web reactive để nhận và xử lý request. Chọn WebFlux không thay đổi schema GraphQL hay cách client viết query; nó thay đổi runtime web và cách ứng dụng xử lý I/O.

## Vai trò của spring-boot-starter-webflux

Spring Boot cung cấp các starter để gom nhóm dependency theo mục đích. **spring-boot-starter-webflux** giúp ứng dụng sử dụng Spring WebFlux mà không cần tự khai báo từng thư viện nền tảng. Starter thường đưa vào:

- Spring WebFlux để xây dựng ứng dụng web theo mô hình reactive.
- Project Reactor với các kiểu publisher như Mono và Flux.
- Cấu hình web server reactive mặc định, thường là Reactor Netty.
- Các tích hợp Spring Boot cần thiết để tự động cấu hình ứng dụng WebFlux.

Trong một ứng dụng GraphQL, hai starter thường được sử dụng cùng nhau:

| Dependency | Trách nhiệm |
| --- | --- |
| **spring-boot-starter-graphql** | Tích hợp GraphQL Java với Spring, đọc schema, ánh xạ resolver, thực thi operation và xử lý kết quả GraphQL |
| **spring-boot-starter-webflux** | Cung cấp reactive web runtime để nhận GraphQL request qua HTTP và xử lý request theo mô hình WebFlux |

GraphQL starter không tự quyết định ứng dụng chạy trên Spring MVC hay Spring WebFlux. Web starter được đưa vào classpath sẽ ảnh hưởng đến web application type mà Spring Boot lựa chọn. Vì vậy, khi chủ đích xây dựng reactive server, hãy dùng WebFlux starter cùng GraphQL starter.

## Khai báo dependency

Với Gradle, cấu hình tối thiểu có thể như sau:

~~~groovy
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-graphql")
    implementation("org.springframework.boot:spring-boot-starter-webflux")
}
~~~

Với Maven, khai báo hai dependency tương ứng trong phần dependencies:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-graphql</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-webflux</artifactId>
    </dependency>
</dependencies>
~~~

Khi dự án sử dụng Spring Boot dependency management hoặc parent của Spring Boot, không cần tự chỉ định phiên bản riêng cho từng starter. Nên để Spring Boot quản lý các phiên bản tương thích của Spring Framework, Spring for GraphQL, Reactor và những thư viện liên quan.

Không thêm **spring-boot-starter-web** nếu mục tiêu là chạy server WebFlux. Khi cả starter MVC và WebFlux cùng có mặt, Spring Boot thường ưu tiên cấu hình Spring MVC cho ứng dụng web. Trường hợp cần dùng WebClient trong một ứng dụng MVC là tình huống khác: WebClient có thể được dùng độc lập mà không cần chuyển web server sang WebFlux.

## Cấu trúc ứng dụng và endpoint GraphQL

Sau khi thêm dependency, ứng dụng Spring Boot có thể giữ cấu trúc đơn giản:

~~~text
src/main/
├── java/
│   └── com/example/catalog/
│       ├── CatalogApplication.java
│       ├── graphql/
│       │   └── BookGraphQlController.java
│       └── service/
│           └── BookService.java
└── resources/
    ├── application.yml
    └── graphql/
        └── schema.graphqls
~~~

Schema có thể khai báo các field cần cung cấp:

~~~graphql
type Query {
  book(id: ID!): Book
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

Spring Boot tự động tìm schema trong thư mục **src/main/resources/graphql** và cấu hình HTTP GraphQL endpoint mặc định tại **/graphql**. Có thể thay đổi đường dẫn bằng thuộc tính **spring.graphql.path**:

~~~yaml
spring:
  graphql:
    path: /graphql
~~~

Client vẫn gửi GraphQL operation tới endpoint đó như khi dùng Spring MVC. Điểm khác biệt nằm ở phía server: request được tiếp nhận bởi reactive web stack của WebFlux.

## Resolver trả về Mono và Flux

Project Reactor cung cấp hai kiểu publisher thường gặp:

- **Mono<T>** biểu diễn một kết quả bất đồng bộ có thể có hoặc không có giá trị.
- **Flux<T>** biểu diễn một chuỗi từ không đến nhiều phần tử được phát ra theo thời gian.

Spring for GraphQL hỗ trợ controller method trả về kiểu reactive. Ví dụ:

~~~java
@Controller
public class BookGraphQlController {

    private final BookService bookService;

    public BookGraphQlController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    public Mono<Book> book(@Argument String id) {
        return bookService.findById(id);
    }

    @QueryMapping
    public Flux<Book> books() {
        return bookService.findAll();
    }

    @SchemaMapping(typeName = "Book", field = "author")
    public Mono<Author> author(Book book) {
        return bookService.findAuthor(book.authorId());
    }
}
~~~

Resolver của field **book** trả về Mono vì một ID tương ứng với tối đa một quyển sách. Resolver **books** trả về Flux vì có thể có nhiều quyển sách. Field **author** cũng trả về Mono vì một quyển sách liên kết tới tối đa một tác giả trong ví dụ này.

Một service reactive có thể định nghĩa hợp đồng như sau:

~~~java
public interface BookService {

    Mono<Book> findById(String id);

    Flux<Book> findAll();

    Mono<Author> findAuthor(String authorId);
}
~~~

Các kiểu trả về này cho phép resolver chuyển tiếp publisher từ service mà không cần tự chờ kết quả. Spring for GraphQL phối hợp với GraphQL Java để xử lý kết quả bất đồng bộ trong quá trình thực thi field.

Lưu ý rằng **Flux<Book>** trong một Query thường được thu thập để tạo giá trị danh sách cho response GraphQL. Nó không có nghĩa HTTP response tự động gửi từng phần tử của danh sách thành một luồng dữ liệu liên tục. Nếu nghiệp vụ cần nhận sự kiện mới liên tục, hãy thiết kế GraphQL Subscription và cấu hình transport tương ứng.

## Luồng xử lý request với WebFlux

Khi client gửi HTTP request tới **/graphql**, WebFlux tiếp nhận request bằng reactive HTTP runtime. Spring for GraphQL chuyển operation, variables và context vào dịch vụ thực thi GraphQL. GraphQL Java kiểm tra operation theo schema và gọi resolver cho các field được yêu cầu. Resolver trả kết quả đồng bộ hoặc bất đồng bộ; các publisher reactive được phối hợp để tạo GraphQL response.

~~~mermaid
flowchart TD
    A["GraphQL client"] -->|"HTTP request"| B["Reactor Netty"]
    B --> C["Spring WebFlux"]
    C --> D["Spring for GraphQL"]
    D --> E["GraphQL Java"]
    E --> F["@QueryMapping / @SchemaMapping"]
    F --> G["Reactive service"]
    G --> H["Reactive repository / WebClient"]
    H --> G
    G --> F
    F --> E
    E --> I["GraphQL response"]
    I --> A
~~~

Mô hình này hữu ích khi các thao tác chờ I/O có thể diễn ra non-blocking, chẳng hạn truy vấn bằng R2DBC, gọi dịch vụ khác bằng WebClient hoặc đọc dữ liệu từ một reactive message source. Trong lúc chờ I/O, runtime có thể sử dụng tài nguyên thread hiệu quả hơn so với việc giữ một thread bị chặn cho từng request.

## Muốn reactive end-to-end, các tầng phải tương thích

Chỉ thêm WebFlux starter và đổi kiểu trả về của controller sang Mono hoặc Flux chưa đủ để hệ thống trở thành non-blocking. Nếu resolver gọi một service blocking, rồi service dùng JDBC hoặc JPA đồng bộ, thread xử lý vẫn có thể bị chặn.

Một luồng reactive nên giữ publisher xuyên suốt các tầng:

~~~text
WebFlux request
    -> GraphQL resolver trả Mono / Flux
        -> service trả Mono / Flux
            -> reactive repository hoặc WebClient
                -> non-blocking I/O
~~~

Ví dụ, Spring Data R2DBC cung cấp repository reactive. Dependency R2DBC chỉ cần thêm khi ứng dụng thực sự truy cập cơ sở dữ liệu qua R2DBC; nó không phải dependency bắt buộc của WebFlux hoặc GraphQL:

~~~groovy
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-data-r2dbc")
    runtimeOnly("io.r2dbc:r2dbc-postgresql")
}
~~~

Repository có thể trả về publisher:

~~~java
public interface BookRepository
        extends ReactiveCrudRepository<BookEntity, String> {
}
~~~

Một repository tương ứng có thể dùng cho tác giả:

~~~
public interface AuthorRepository
        extends ReactiveCrudRepository<AuthorEntity, String> {
}
~~~

Service có thể chuyển đổi entity sang model GraphQL mà không chặn luồng:

~~~java
@Service
public class ReactiveBookService implements BookService {

    private final BookRepository repository;
    private final AuthorRepository authorRepository;

    public ReactiveBookService(
            BookRepository repository,
            AuthorRepository authorRepository) {
        this.repository = repository;
        this.authorRepository = authorRepository;
    }

    @Override
    public Mono<Book> findById(String id) {
        return repository.findById(id)
                .map(this::toBook);
    }

    @Override
    public Flux<Book> findAll() {
        return repository.findAll()
                .map(this::toBook);
    }

    @Override
    public Mono<Author> findAuthor(String authorId) {
        return authorRepository.findById(authorId)
                .map(this::toAuthor);
    }

    private Book toBook(BookEntity entity) {
        return new Book(entity.getId(), entity.getTitle());
    }

    private Author toAuthor(AuthorEntity entity) {
        return new Author(entity.getId(), entity.getName());
    }
}
~~~

Đây là ví dụ minh họa cách giữ kiểu reactive qua tầng repository và service; ứng dụng thực tế cần bổ sung mapping, quan hệ dữ liệu và xử lý lỗi theo domain của mình.

Nếu phải tích hợp một thư viện blocking chưa thể thay thế, hãy cô lập thao tác blocking trên scheduler phù hợp, chẳng hạn **Schedulers.boundedElastic()**, thay vì thực thi nó trực tiếp trên event-loop thread. Không gọi **block()** trong resolver hoặc trên luồng xử lý request WebFlux để chờ publisher hoàn tất. Việc chặn event loop có thể làm giảm thông lượng của nhiều request cùng lúc.

## Gọi dịch vụ ngoài bằng WebClient

WebClient là HTTP client reactive của Spring. Khi GraphQL resolver cần lấy thông tin từ một service khác, WebClient có thể trả về Mono hoặc Flux để service tiếp tục xử lý bất đồng bộ:

~~~java
@Service
public class AuthorClient {

    private final WebClient webClient;

    public AuthorClient(WebClient.Builder builder) {
        this.webClient = builder
                .baseUrl("http://author-service")
                .build();
    }

    public Mono<Author> findById(String authorId) {
        return webClient.get()
                .uri("/authors/{id}", authorId)
                .retrieve()
                .bodyToMono(Author.class);
    }
}
~~~

Resolver có thể trả trực tiếp kết quả từ client:

~~~java
@SchemaMapping(typeName = "Book", field = "author")
public Mono<Author> author(Book book) {
    return authorClient.findById(book.authorId());
}
~~~

Trong ứng dụng thật, cần cấu hình timeout, retry có giới hạn khi phù hợp, xử lý HTTP status và quan sát lỗi từ service ngoài. Không nên retry mọi lỗi một cách vô điều kiện vì điều đó có thể làm tăng tải khi hệ thống đích đang gặp sự cố.

## Subscription và luồng sự kiện

Query và Mutation thường tạo một response cho mỗi operation. Subscription được dùng khi client cần nhận nhiều sự kiện theo thời gian. Trong Spring for GraphQL, resolver subscription thường trả về **Flux<T>**:

~~~graphql
type Subscription {
  bookCreated: Book!
}
~~~

~~~java
@Controller
public class BookSubscriptionController {

    private final BookEventService eventService;

    public BookSubscriptionController(BookEventService eventService) {
        this.eventService = eventService;
    }

    @SubscriptionMapping
    public Flux<Book> bookCreated() {
        return eventService.bookCreated();
    }
}
~~~

WebFlux hỗ trợ mô hình reactive, nhưng việc khai báo Subscription trong schema và trả về Flux chưa tự tạo kết nối cho client. Ứng dụng còn phải bật và cấu hình transport hỗ trợ subscription, thường là WebSocket hoặc một transport phù hợp khác. Với Spring Boot, có thể cấu hình endpoint WebSocket bằng thuộc tính **spring.graphql.websocket.path** khi ứng dụng sử dụng WebSocket transport được hỗ trợ.

## DataLoader, @BatchMapping và hiệu năng

Reactive không tự loại bỏ vấn đề N+1. Nếu một query lấy danh sách sách và mỗi field author gọi riêng một request tới author service, server vẫn có thể tạo ra nhiều lần gọi I/O. Những lời gọi đó có thể non-blocking nhưng tổng số lời gọi vẫn lớn và gây tải không cần thiết.

Spring for GraphQL cung cấp **@BatchMapping** và hỗ trợ DataLoader để gom các lần phân giải field. Thay vì tải tác giả riêng cho từng quyển sách, resolver batch nhận nhiều object nguồn và tải dữ liệu theo lô. Khi nguồn dữ liệu hỗ trợ batch API, cách này có thể giảm số lần truy vấn database hoặc gọi service ngoài.

Trong thiết kế reactive, batch loader có thể trả về kiểu reactive phù hợp với nguồn dữ liệu. Cần bảo đảm kết quả được ghép đúng với từng key hoặc source object, xử lý trường hợp thiếu dữ liệu và tránh chia sẻ cache giữa các request của những người dùng khác nhau. DataLoader thường được tổ chức theo phạm vi thực thi request để tránh rò rỉ dữ liệu hoặc quyền truy cập giữa các request.

Ngoài batching, hãy cân nhắc phân trang, giới hạn kích thước danh sách, giới hạn độ sâu hoặc độ phức tạp của operation, timeout và giới hạn concurrency. Một operation GraphQL có thể yêu cầu nhiều nhánh dữ liệu; non-blocking giúp quản lý tài nguyên I/O tốt hơn nhưng không làm cho query tốn kém trở nên miễn phí.

## Cấu hình và kiểm thử

Cấu hình tối thiểu cho endpoint có thể giữ ở file **application.yml**:

~~~yaml
spring:
  graphql:
    path: /graphql
~~~

Các thuộc tính khác như CORS, WebSocket, schema locations hoặc bật GraphiQL cần được cấu hình theo môi trường và yêu cầu triển khai. Không nên bật công cụ giao diện phát triển công khai trong môi trường production nếu chưa có kiểm soát truy cập phù hợp.

Có thể kiểm thử HTTP GraphQL endpoint bằng **WebTestClient** kết hợp với **HttpGraphQlTester**. Cách kiểm thử này xác minh cả đường đi HTTP của WebFlux lẫn kết quả operation:

Trong test scope, bổ sung thư viện **spring-graphql-test** để sử dụng GraphQlTester:

~~~groovy
dependencies {
    testImplementation("org.springframework.graphql:spring-graphql-test")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
}
~~~

~~~java
WebTestClient webTestClient = WebTestClient
        .bindToServer()
        .baseUrl("http://localhost:8080")
        .build();

HttpGraphQlTester graphQlTester =
        HttpGraphQlTester.create(webTestClient);

graphQlTester.document("""
        query FindBook($id: ID!) {
            book(id: $id) {
                id
                title
            }
        }
        """)
    .variable("id", "book-101")
    .execute()
    .path("book.title")
    .entity(String.class)
    .isEqualTo("Spring in Action");
~~~

Nên kiểm tra thêm trường hợp không tìm thấy dữ liệu, lỗi từ service ngoài, timeout, input sai, người dùng thiếu quyền và query có nhiều field lồng nhau. Với Subscription, cần kiểm tra cả publisher phát sự kiện và transport mà client sử dụng.

## Khi nào nên chọn WebFlux cho GraphQL?

WebFlux là lựa chọn phù hợp khi ứng dụng có nhiều request đồng thời chờ I/O, các service và repository đã hỗ trợ reactive, hoặc cần phối hợp nhiều lời gọi bất đồng bộ trong một GraphQL operation. Nó cũng phù hợp với ứng dụng sử dụng Reactor hoặc cần xây dựng luồng sự kiện reactive.

Spring MVC vẫn là lựa chọn hợp lý cho ứng dụng dùng thư viện blocking như JDBC/JPA, có lưu lượng vừa phải và không cần mô hình reactive xuyên suốt. WebFlux làm tăng yêu cầu về cách tổ chức code, xử lý lỗi, context, debugging và kiểm soát scheduler. Chọn reactive stack chỉ vì GraphQL có Subscription thường chưa đủ lý do; cần đánh giá toàn bộ workload và hệ sinh thái dependency.

Khi chọn **spring-boot-starter-webflux**, hãy xác định rõ các tầng I/O, tránh trộn lẫn blocking và non-blocking không kiểm soát, đo độ trễ và mức sử dụng tài nguyên dưới tải thực tế. Kết hợp đúng GraphQL starter, WebFlux starter, resolver reactive và nguồn dữ liệu phù hợp sẽ giúp ứng dụng phục vụ GraphQL API theo mô hình non-blocking một cách nhất quán.
