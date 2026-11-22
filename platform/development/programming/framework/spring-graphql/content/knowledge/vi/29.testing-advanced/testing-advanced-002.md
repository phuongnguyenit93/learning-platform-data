# Test controller slice

## 1. Controller slice test là gì?

Trong Spring for GraphQL, controller nhận GraphQL operation thông qua các annotation như `@QueryMapping`, `@MutationMapping`, `@SubscriptionMapping` và `@SchemaMapping`. Một controller thường gọi service để lấy dữ liệu, kiểm tra nghiệp vụ hoặc lưu thay đổi.

Khi kiểm thử controller, không phải lúc nào cũng cần khởi động toàn bộ ứng dụng, database, message broker và HTTP server. Controller slice test chỉ nạp phần cấu hình cần thiết để thực thi GraphQL operation và gọi controller đang kiểm tra. Các service hoặc collaborator bên ngoài được thay bằng mock.

Spring Boot cung cấp annotation `@GraphQlTest` cho mục đích này. Annotation cấu hình GraphQL infrastructure, schema và `GraphQlTester`, sau đó giới hạn component scan vào các thành phần liên quan đến GraphQL controller. Test có thể gửi document, variables, kiểm tra data và errors mà không cần mở HTTP endpoint hoặc khởi động server.

Đây là cách phù hợp để kiểm tra:

- GraphQL field được ánh xạ đúng vào controller method.
- Argument và variables được bind đúng kiểu.
- Nested field mapping như `@SchemaMapping` hoạt động đúng.
- Controller gọi đúng service với dữ liệu đã nhận.
- GraphQL schema validation từ chối operation không hợp lệ.
- Exception được chuyển thành GraphQL error theo cấu hình của controller.

## 2. Phân biệt controller slice với các loại test khác

Các loại test có phạm vi khác nhau. Chọn đúng loại giúp test tập trung và không khởi động nhiều thành phần hơn cần thiết.

| Loại test | Thành phần được kiểm tra | Có transport/server không? | Công cụ thường dùng |
| --- | --- | --- | --- |
| Unit test controller | Java method và logic trực tiếp | Không | JUnit, Mockito |
| `@GraphQlTest` | GraphQL schema, controller, argument binding, field mapping, GraphQL errors | Không | `GraphQlTester` |
| `ExecutionGraphQlServiceTester` | GraphQL execution service ở server side | Không | `GraphQlTester` |
| `WebGraphQlTester` | `WebGraphQlHandler`, `WebGraphQlInterceptor` và request metadata mô phỏng | Không cần HTTP server thật | `GraphQlTester` |
| `HttpGraphQlTester` | GraphQL HTTP transport và server handler | Có thể dùng mock web environment hoặc server thật | `WebTestClient` |
| `WebSocketGraphQlTester` | WebSocket protocol và Subscription | Có WebSocket connection | `WebSocketClient`, Reactor Test |
| `@SpringBootTest` | Toàn bộ application context và tích hợp giữa các tầng | Tùy web environment | `GraphQlTester` hoặc tester theo transport |

`@GraphQlTest` không kiểm tra HTTP route, WebSocket handshake, filter chain của web server hoặc cấu hình reverse proxy. Khi cần xác nhận những thành phần đó, hãy bổ sung integration test qua `HttpGraphQlTester`, `WebSocketGraphQlTester` hoặc `@SpringBootTest`.

## 3. `@GraphQlTest` nạp những thành phần nào?

`@GraphQlTest` tắt full auto-configuration và chỉ nạp một tập hợp bean phù hợp với GraphQL test. Theo Spring Boot hiện hành, các thành phần được nhận diện gồm:

- `@Controller` — controller xử lý GraphQL field.
- `@ControllerAdvice` — exception handler dùng chung.
- `RuntimeWiringConfigurer` — đăng ký scalar, directive hoặc DataFetcher tùy chỉnh.
- `@JacksonComponent` và `@JsonComponent` (loại sau đã deprecated) — hỗ trợ Jackson.
- `Converter` và `GenericConverter` — chuyển đổi argument hoặc dữ liệu.
- `DataFetcherExceptionResolver` — xử lý exception từ GraphQL data fetcher.
- `Instrumentation` — instrumentation của GraphQL Java.
- `GraphQlSourceBuilderCustomizer` — tùy chỉnh quá trình tạo GraphQL source.

Các bean nghiệp vụ thông thường như `@Service`, `@Repository` và `@Component` không được tự động scan. Đây là chủ ý của slice test: controller được kiểm tra trong khi các collaborator được thay thế bằng mock hoặc được import có chọn lọc.

Nếu không chỉ định controller trong `@GraphQlTest`, Spring Boot có thể thêm tất cả controller phù hợp vào context. Với bài test tập trung, nên khai báo rõ controller cần kiểm tra:

```java
@GraphQlTest(BookController.class)
class BookControllerTests {
    // ...
}
```

## 4. Dependency và khác biệt package giữa Spring Boot 3 và 4

Để dùng `GraphQlTester`, thêm module kiểm thử của Spring for GraphQL:

```kotlin
dependencies {
    testImplementation("org.springframework.graphql:spring-graphql-test")
}
```

Với Spring Boot 4, `@GraphQlTest` nằm trong module `spring-boot-graphql-test`. Dự án cũng cần test support của Spring Boot, chẳng hạn:

```kotlin
dependencies {
    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("org.springframework.boot:spring-boot-graphql-test")
    testImplementation("org.springframework.graphql:spring-graphql-test")
}
```

Spring Boot quản lý phiên bản dependency thông qua dependency management/BOM. Không cần tự đặt version riêng nếu dự án đã dùng Spring Boot dependency management.

Package của annotation thay đổi giữa các major version:

| Phiên bản | Import `@GraphQlTest` |
| --- | --- |
| Spring Boot 4.x | `org.springframework.boot.graphql.test.autoconfigure.GraphQlTest` |
| Spring Boot 3.x | `org.springframework.boot.test.autoconfigure.graphql.GraphQlTest` |

Trong Spring Framework 6.2 trở lên, có thể dùng `@MockitoBean` từ package `org.springframework.test.context.bean.override.mockito.MockitoBean` để tạo mock trong `ApplicationContext`. Với Spring Boot 3.3 trở xuống, dự án thường dùng `@MockBean`; `@MockBean` đã deprecated trong Spring Boot 3.4 và được thay thế bằng `@MockitoBean` ở các phiên bản mới.

## 5. Chuẩn bị schema và controller mẫu

Ví dụ sử dụng API quản lý sách. Schema đặt trong `src/main/resources/graphql/schema.graphqls`:

```graphql
type Query {
    bookById(id: ID!): Book
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
```

Domain model:

```java
public record Book(String id, String title, String authorId) {
}

public record Author(String id, String name) {
}
```

Các service được controller sử dụng:

```java
public interface BookQueryService {
    Book findById(String id);
}

public interface AuthorQueryService {
    Author findById(String id);
}
```

Controller ánh xạ root Query field và nested `Book.author`:

```java
import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.graphql.data.method.annotation.SchemaMapping;
import org.springframework.stereotype.Controller;

@Controller
public class BookController {

    private final BookQueryService bookQueryService;
    private final AuthorQueryService authorQueryService;

    public BookController(
            BookQueryService bookQueryService,
            AuthorQueryService authorQueryService) {
        this.bookQueryService = bookQueryService;
        this.authorQueryService = authorQueryService;
    }

    @QueryMapping
    public Book bookById(@Argument String id) {
        return bookQueryService.findById(id);
    }

    @SchemaMapping(typeName = "Book", field = "author")
    public Author author(Book book) {
        return authorQueryService.findById(book.authorId());
    }
}
```

Trong test slice, `BookController` được tạo thật. Hai service sẽ được thay bằng Mockito mock để test không truy cập database hoặc dịch vụ bên ngoài.

## 6. Viết controller slice test đầu tiên

Với Spring Boot 4, import annotation từ package mới. `@GraphQlTest` tự cấu hình `GraphQlTester`, nên chỉ cần inject tester và khai báo mock cho các collaborator:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.graphql.test.autoconfigure.GraphQlTest;
import org.springframework.graphql.test.tester.GraphQlTester;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

import static org.mockito.BDDMockito.given;
import static org.mockito.BDDMockito.then;

@GraphQlTest(BookController.class)
class BookControllerTests {

    @Autowired
    GraphQlTester graphQlTester;

    @MockitoBean
    BookQueryService bookQueryService;

    @MockitoBean
    AuthorQueryService authorQueryService;

    @Test
    void returnsBookById() {
        given(bookQueryService.findById("book-1"))
            .willReturn(new Book("book-1", "GraphQL in Action", "author-1"));

        graphQlTester.document("""
                query BookById($id: ID!) {
                    bookById(id: $id) {
                        id
                        title
                    }
                }
                """)
            .variable("id", "book-1")
            .execute()
            .errors()
            .verify()
            .path("bookById.id")
            .entity(String.class)
            .isEqualTo("book-1");

        then(bookQueryService).should().findById("book-1");
    }
}
```

Luồng test:

1. `@GraphQlTest(BookController.class)` nạp GraphQL infrastructure, schema và controller được chọn.
2. `@MockitoBean` đăng ký mock `BookQueryService` trong application context.
3. `given(...).willReturn(...)` chuẩn bị kết quả cho service.
4. `document(...)` cung cấp GraphQL operation.
5. `variable(...)` truyền giá trị cho `$id`.
6. `execute()` chạy operation qua GraphQL execution pipeline.
7. `errors().verify()` xác nhận response không chứa GraphQL errors.
8. `path(...)` chọn field trong phần `data` của response để kiểm tra.
9. `then(...).should()` xác nhận controller gọi đúng service.

Đường dẫn `bookById.id` được tính tương đối từ `data`, không cần thêm tiền tố `data.`.

## 7. Kiểm tra nested field với `@SchemaMapping`

GraphQL có thể gọi nhiều resolver trong cùng operation. Controller slice test nên xác nhận cả root field và field mapping lồng nhau hoạt động đúng.

```java
@Test
void resolvesNestedAuthorField() {
    given(bookQueryService.findById("book-1"))
        .willReturn(new Book("book-1", "GraphQL in Action", "author-1"));
    given(authorQueryService.findById("author-1"))
        .willReturn(new Author("author-1", "Sam"));

    graphQlTester.document("""
            query BookDetails($id: ID!) {
                bookById(id: $id) {
                    id
                    title
                    author {
                        id
                        name
                    }
                }
            }
            """)
        .variable("id", "book-1")
        .execute()
        .errors()
        .verify()
        .path("bookById.author.name")
        .entity(String.class)
        .isEqualTo("Sam");

    then(bookQueryService).should().findById("book-1");
    then(authorQueryService).should().findById("author-1");
}
```

Test này xác nhận:

- `@QueryMapping` ánh xạ `bookById` đúng.
- Kết quả `Book` trở thành source object của nested field.
- `@SchemaMapping(typeName = "Book", field = "author")` được gọi.
- Giá trị `authorId` của source object được truyền vào service.
- GraphQL response chứa dữ liệu nested đúng với selection set.

Nếu test chỉ kiểm tra `bookById.id`, một lỗi ở resolver `author` có thể chưa được phát hiện. Hãy chọn đầy đủ nested field mà client thực sự sử dụng.

## 8. Kiểm tra argument binding và GraphQL variables

`@Argument` bind một argument trong SDL vào method parameter. Controller slice test có thể xác nhận giá trị được bind đúng bằng cách truyền variable thay vì nối chuỗi trực tiếp vào query.

```java
@Test
void bindsGraphQlVariableToArgument() {
    given(bookQueryService.findById("book-42"))
        .willReturn(new Book("book-42", "Spring GraphQL", "author-7"));

    graphQlTester.document("""
            query FindBook($bookId: ID!) {
                bookById(id: $bookId) {
                    id
                }
            }
            """)
        .variable("bookId", "book-42")
        .execute()
        .errors()
        .verify()
        .path("bookById.id")
        .entity(String.class)
        .isEqualTo("book-42");

    then(bookQueryService).should().findById("book-42");
}
```

Dùng variable giúp test gần với cách client thực tế gọi API, đồng thời tránh phải dựng document mới cho từng giá trị. Có thể kiểm tra thêm `@Arguments`, input object, enum, custom scalar và các kiểu dữ liệu nullable theo schema của ứng dụng.

## 9. Kiểm tra GraphQL schema validation

Một lợi ích quan trọng của controller slice là schema được nạp cùng GraphQL infrastructure. Vì vậy, test có thể xác nhận operation không hợp lệ bị từ chối trước khi controller gọi service.

Ví dụ field `bookById` yêu cầu argument `id: ID!`. Query thiếu argument:

```java
import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.verifyNoInteractions;

@Test
void rejectsMissingRequiredArgument() {
    graphQlTester.document("""
            query {
                bookById {
                    id
                }
            }
            """)
        .execute()
        .errors()
        .satisfy(errors -> assertThat(errors).isNotEmpty());

    verifyNoInteractions(bookQueryService);
}
```

Test không phụ thuộc vào nội dung message validation cụ thể, vì message có thể thay đổi theo phiên bản GraphQL Java. Nó xác nhận có lỗi và service không bị gọi.

Có thể áp dụng cùng cách này để kiểm tra:

- Field không tồn tại trong schema.
- Argument bắt buộc bị thiếu.
- Scalar nhận giá trị sai kiểu.
- Enum nhận giá trị không được khai báo.
- Operation có selection set không hợp lệ.
- Operation name không tồn tại trong document nhiều operation.

Đây là schema validation trước execution. Nó khác với validation nghiệp vụ trong service, ví dụ kiểm tra sách có tồn tại hay người dùng có quyền đọc sách đó.

## 10. Kiểm tra GraphQL errors từ resolver

Nếu resolver hoặc service ném exception, Spring for GraphQL có thể chuyển exception thành `GraphQLError` thông qua `@GraphQlExceptionHandler`, `@ControllerAdvice` hoặc `DataFetcherExceptionResolver`.

Khi test một response dự kiến có lỗi, không gọi `errors().verify()` vì phương thức này yêu cầu không có lỗi. Thay vào đó, dùng `errors().satisfy(...)` hoặc `errors().expect(...)`:

Ví dụ dưới đây giả định ứng dụng có exception handler ánh xạ `BookNotFoundException` thành GraphQL error có message phù hợp; phần tiếp theo trình bày một handler cụ thể.

```java
@Test
void exposesExpectedGraphQlError() {
    given(bookQueryService.findById("missing"))
        .willThrow(new BookNotFoundException("Book not found"));

    graphQlTester.document("""
            query {
                bookById(id: "missing") {
                    id
                }
            }
            """)
        .execute()
        .errors()
        .satisfy(errors -> assertThat(errors)
            .anySatisfy(error ->
                assertThat(error.getMessage()).contains("Book not found")
            )
        );
}
```

`errors().satisfy(...)` cho phép kiểm tra danh sách lỗi và đánh dấu lỗi đã được xử lý trong test. Nếu muốn xác nhận một lỗi cụ thể tồn tại, có thể dùng `errors().expect(predicate).verify()`.

Trong production, không nên phụ thuộc vào stack trace hoặc message nội bộ của exception. Tốt hơn là kiểm tra error code trong `extensions`, classification hoặc field path mà exception handler đã chuẩn hóa.

## 11. Kiểm tra `@ControllerAdvice` và exception handler

Spring Boot hiện hành đưa `@ControllerAdvice` liên quan đến GraphQL vào slice test. Nếu ứng dụng có exception handler dùng chung, hãy xác nhận handler được áp dụng và trả đúng error contract.

Ví dụ handler:

```java
import java.util.Map;

import graphql.GraphQLError;
import graphql.GraphqlErrorBuilder;
import graphql.schema.DataFetchingEnvironment;
import org.springframework.graphql.data.method.annotation.GraphQlExceptionHandler;
import org.springframework.web.bind.annotation.ControllerAdvice;

@ControllerAdvice
public class GraphQlErrorAdvice {

    @GraphQlExceptionHandler
    public GraphQLError handleBookNotFound(
            BookNotFoundException exception,
            DataFetchingEnvironment environment) {

        return GraphqlErrorBuilder.newError(environment)
            .message("Book not found")
            .extensions(Map.of("code", "BOOK_NOT_FOUND"))
            .build();
    }
}
```

Exception nghiệp vụ trong ví dụ có thể là một runtime exception đơn giản:

```java
public class BookNotFoundException extends RuntimeException {

    public BookNotFoundException(String message) {
        super(message);
    }
}
```

Test nên kiểm tra error code:

```java
@Test
void mapsBookNotFoundToStableErrorCode() {
    given(bookQueryService.findById("missing"))
        .willThrow(new BookNotFoundException("internal detail"));

    graphQlTester.document("{ bookById(id: \"missing\") { id } }")
        .execute()
        .errors()
        .satisfy(errors -> assertThat(errors).anySatisfy(error ->
            assertThat(error.getExtensions())
                .containsEntry("code", "BOOK_NOT_FOUND")
        ));
}
```

Nếu handler không được nạp, hãy kiểm tra phiên bản Spring Boot, component filter của `@GraphQlTest` và cách đăng ký advice. Với test slice cũ hoặc cấu hình tùy chỉnh, có thể dùng `@Import(GraphQlErrorAdvice.class)` để đưa advice vào context một cách tường minh.

## 12. Tổ chức GraphQL document trong file riêng

Query dài nên được đặt trong file `.graphql` hoặc `.gql` để test dễ đọc và tái sử dụng. Spring GraphQL hỗ trợ tải document từ thư mục classpath `graphql-test/` bằng `documentName(...)`.

Ví dụ file `src/test/resources/graphql-test/book-details.graphql`:

```graphql
query BookDetails($id: ID!) {
    bookById(id: $id) {
        id
        title
        author {
            id
            name
        }
    }
}
```

Test:

```java
@Test
void loadsNamedDocument() {
    given(bookQueryService.findById("book-1"))
        .willReturn(new Book("book-1", "GraphQL in Action", "author-1"));
    given(authorQueryService.findById("author-1"))
        .willReturn(new Author("author-1", "Sam"));

    graphQlTester.documentName("book-details")
        .variable("id", "book-1")
        .execute()
        .errors()
        .verify()
        .path("bookById.author.name")
        .entity(String.class)
        .isEqualTo("Sam");
}
```

`documentName("book-details")` tham chiếu file `book-details.graphql`; không cần ghi phần mở rộng. Có thể đặt fragment trong file riêng và thêm bằng `fragmentName(...)` nếu nhiều operation dùng chung selection set.

## 13. Khi cần import component hoặc cấu hình bổ sung

`@GraphQlTest` chỉ nạp các loại bean trong component filter. Nếu controller phụ thuộc một converter, scalar, configuration hoặc helper không nằm trong filter, hãy import rõ ràng thay vì mở rộng toàn bộ component scan.

Ví dụ:

```java
import org.springframework.context.annotation.Import;

@GraphQlTest(BookController.class)
@Import(BookGraphQlTestConfiguration.class)
class BookControllerTests {
    // ...
}
```

`BookGraphQlTestConfiguration` có thể khai báo `RuntimeWiringConfigurer`, custom scalar, Jackson module hoặc bean hỗ trợ riêng cho test. Không nên import cả cấu hình production lớn nếu nó kéo theo database, message broker hoặc nhiều integration không liên quan.

Nếu cần một `@ConfigurationProperties` bean trong slice, dùng `@EnableConfigurationProperties(...)` hoặc import cấu hình thích hợp. Các property của test có thể được đặt qua thuộc tính `properties` của `@GraphQlTest`:

```java
@GraphQlTest(
    controllers = BookController.class,
    properties = "catalog.feature.enabled=true"
)
class BookControllerTests {
    // ...
}
```

## 14. Kiểm tra controller gọi service đúng cách

Chỉ xác nhận response đúng chưa đủ để biết controller đã truyền argument chính xác đến service hay chưa. Mockito có thể xác nhận lời gọi và số lần gọi:

```java
import static org.mockito.Mockito.times;

then(bookQueryService).should().findById("book-1");
then(authorQueryService).should(times(1)).findById("author-1");
```

Hoặc xác nhận service không bị gọi khi GraphQL validation thất bại:

```java
verifyNoInteractions(bookQueryService);
```

Nên ưu tiên kiểm tra hành vi có ý nghĩa đối với hợp đồng của controller: argument đúng, collaborator được gọi đúng khi cần và không bị gọi khi operation không hợp lệ. Tránh verify mọi lời gọi nội bộ nếu chúng không phải một phần của hành vi cần bảo vệ.

Với controller có nhiều service, chỉ mock các collaborator trực tiếp của controller. Nếu cần kiểm tra business rule bên trong service, hãy viết unit test riêng cho service hoặc integration test phù hợp.

## 15. Các thao tác thường dùng của `GraphQlTester`

`GraphQlTester` cung cấp API thống nhất cho các loại transport và server-side tester. Những thao tác thường gặp:

| API | Công dụng |
| --- | --- |
| `document(String)` | Gửi GraphQL document trực tiếp từ chuỗi |
| `documentName(String)` | Tải document từ classpath `graphql-test/` |
| `variable(name, value)` | Gán giá trị cho GraphQL variable |
| `fragmentName(name)` | Nạp fragment từ document file |
| `execute()` | Thực thi operation và nhận response để kiểm tra |
| `executeAndVerify()` | Thực thi và xác nhận response không có GraphQL errors |
| `executeSubscription()` | Thực thi Subscription và nhận stream kết quả |
| `path(path)` | Chọn field bằng JsonPath tương đối với `data` |
| `entity(Class)` | Decode một giá trị thành Java type |
| `entityList(Class)` | Decode danh sách thành Java type |
| `matchesJson(String)` | So sánh dữ liệu tại path với JSON mong đợi |
| `errors().verify()` | Xác nhận không còn GraphQL errors chưa được xử lý |
| `errors().expect(...)` | Xác nhận có lỗi phù hợp predicate |
| `errors().satisfy(...)` | Kiểm tra toàn bộ danh sách lỗi bằng assertion |

Nếu test một Mutation không có response data cần kiểm tra, `executeAndVerify()` là lựa chọn gọn để xác nhận không có lỗi. Nếu response có data cần so sánh, dùng `execute()` rồi kiểm tra các path cần thiết.

## 16. Khi nào nên chuyển sang `HttpGraphQlTester` hoặc `@SpringBootTest`?

`@GraphQlTest` không chạy HTTP server. Nếu test cần xác nhận endpoint `/graphql`, HTTP headers, authentication filter hoặc `WebGraphQlInterceptor`, cần mở rộng phạm vi test.

Với Spring Boot, một lựa chọn là:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.graphql.test.autoconfigure.tester.AutoConfigureHttpGraphQlTester;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.graphql.test.tester.HttpGraphQlTester;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureHttpGraphQlTester
class BookGraphQlIntegrationTests {

    @Test
    void executesThroughHttp(@Autowired HttpGraphQlTester graphQlTester) {
        graphQlTester.document("{ bookById(id: \"book-1\") { id } }")
            .execute()
            .errors()
            .verify()
            .path("bookById.id")
            .entity(String.class)
            .isEqualTo("book-1");
    }
}
```

Với `RANDOM_PORT`, Spring Boot khởi động server thật trên port ngẫu nhiên. `HttpGraphQlTester` gửi request qua HTTP transport đến server đó. Cách này phù hợp cho một số integration test, nhưng chậm hơn controller slice và có thể cần database/test fixture thật.

Nếu chỉ cần kiểm tra `WebGraphQlInterceptor` mà không cần HTTP server, có thể dùng `WebGraphQlTester` với `WebGraphQlHandler`. Nếu cần kiểm tra WebSocket Subscription, dùng `WebSocketGraphQlTester` và quản lý vòng đời connection trong test.

## 17. Lỗi thường gặp khi viết controller slice test

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Không tìm thấy bean service khi khởi tạo context | `@Service` không được scan trong slice | Dùng `@MockitoBean` hoặc `@Import` collaborator cần thiết |
| Không inject được `GraphQlTester` | Thiếu `spring-graphql-test` hoặc dùng sai Boot test module | Kiểm tra test dependencies và auto-configuration |
| Không tìm thấy `@GraphQlTest` | Import sai package theo phiên bản Boot | Boot 4 dùng `org.springframework.boot.graphql.test.autoconfigure`; Boot 3 dùng package cũ |
| Schema không có field trong test | SDL không nằm trong vị trí schema được cấu hình hoặc schema sai | Kiểm tra `src/main/resources/graphql` và GraphQL schema location |
| Controller không được gọi | Chưa chỉ định controller hoặc method mapping không khớp SDL | Kiểm tra `@GraphQlTest(Controller.class)`, root type và field name |
| Nested field trả null | Thiếu `@SchemaMapping` hoặc source object không có property phù hợp | Kiểm tra field mapping và dữ liệu source |
| Test thành công dù response có lỗi | Dùng `execute()` nhưng không kiểm tra errors | Thêm `.errors().verify()` hoặc `.executeAndVerify()` |
| Test lỗi nhưng assertion báo lỗi ngoài dự kiến | Gọi `errors().verify()` trong ca mong đợi có lỗi | Dùng `errors().expect(...)` hoặc `errors().satisfy(...)` |
| Mockito không ghi nhận lời gọi | Query không chọn field, schema validation thất bại hoặc stub sai argument | Kiểm tra document, variables và mock setup |
| `@ControllerAdvice` không được áp dụng | Advice không được scan/import trong slice của phiên bản đang dùng | Kiểm tra component filter hoặc dùng `@Import` |
| Cấu hình production kéo database vào test | Import toàn bộ cấu hình hoặc mở rộng component scan | Chỉ import config cần thiết và mock collaborator |
| Mong đợi test HTTP nhưng chỉ có GraphQL execution | `@GraphQlTest` không dựng transport/server | Dùng `HttpGraphQlTester` và `@SpringBootTest` khi cần |

## 18. Checklist cho controller slice test

- [ ] Thêm `spring-graphql-test` vào test dependencies.
- [ ] Dùng `@GraphQlTest` với đúng controller cần kiểm tra.
- [ ] Dùng đúng package `@GraphQlTest` theo Spring Boot version.
- [ ] Inject `GraphQlTester` được auto-configure.
- [ ] Thay service/repository phụ thuộc bằng `@MockitoBean` hoặc import có chọn lọc.
- [ ] Chuẩn bị schema SDL trong vị trí được Spring Boot cấu hình.
- [ ] Gửi operation với `document(...)` hoặc `documentName(...)`.
- [ ] Dùng GraphQL variables để kiểm tra argument binding.
- [ ] Kiểm tra cả root field và nested field nếu controller có `@SchemaMapping`.
- [ ] Dùng `errors().verify()` cho response mong đợi không có lỗi.
- [ ] Dùng `errors().expect(...)` hoặc `errors().satisfy(...)` cho response mong đợi có lỗi.
- [ ] Kiểm tra service được gọi đúng hoặc không được gọi khi validation thất bại.
- [ ] Import advice, converter, scalar hoặc configuration cần thiết một cách tường minh.
- [ ] Chuyển sang HTTP/WebSocket integration test nếu cần xác nhận transport.

## Kết luận

`@GraphQlTest` là công cụ của Spring Boot để kiểm thử GraphQL controller trong một ApplicationContext giới hạn. Nó nạp GraphQL infrastructure, schema, controller và các thành phần mở rộng phù hợp, đồng thời tự cấu hình `GraphQlTester`. Các service và repository thông thường không được scan, vì vậy nên thay chúng bằng `@MockitoBean` hoặc import riêng khi thực sự cần.

Một controller slice test có thể kiểm tra mapping từ SDL đến `@QueryMapping`/`@SchemaMapping`, argument binding, nested selection set, schema validation, service interaction và GraphQL errors mà không cần HTTP server. Hãy dùng `GraphQlTester` để kiểm tra data và errors, giữ test tập trung vào hợp đồng GraphQL của controller, rồi bổ sung integration test qua `HttpGraphQlTester` hoặc `WebSocketGraphQlTester` cho những phần liên quan đến transport.

## Tài liệu tham khảo

- [Spring Boot 4.2 — Auto-configured Spring GraphQL Tests](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html#testing.spring-boot-applications.autoconfigured-spring-graphql-tests)
- [Spring Boot — `@GraphQlTest` API](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/graphql/test/autoconfigure/GraphQlTest.html)
- [Spring for GraphQL — Testing](https://docs.spring.io/spring-graphql/reference/testing.html)
- [Spring for GraphQL — Annotated Controllers](https://docs.spring.io/spring-graphql/reference/controllers.html)
- [Spring Framework — Mockito Bean Overrides](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/bean-overriding.html)
- [Spring Getting Started — Building a GraphQL service](https://spring.io/guides/gs/graphql-server)
