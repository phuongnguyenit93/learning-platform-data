# @GraphQlTest

Trong Spring Boot, `@GraphQlTest` là test slice dành cho phần GraphQL của ứng dụng. Annotation này tạo một Spring test context có hạ tầng GraphQL cần thiết, nạp schema và các GraphQL controller được chọn, đồng thời cấu hình sẵn `GraphQlTester` để gửi document và kiểm tra response.

Mục tiêu của `@GraphQlTest` là kiểm tra việc một GraphQL operation được xử lý như thế nào ở lớp controller và GraphQL runtime: field có được ánh xạ đúng không, argument có được bind đúng không, response có đúng cấu trúc không, lỗi có được chuyển thành GraphQL error theo hợp đồng hay không. Các service và repository thường được thay bằng mock để test tập trung vào ranh giới GraphQL.

`@GraphQlTest` không khởi động HTTP server và không kiểm thử HTTP transport. Khi cần xác minh endpoint, filter bảo mật, header, status code hoặc kết nối thật, hãy dùng integration test với `@SpringBootTest` và tester phù hợp.

## 1. Test slice là gì?

Một test thông thường dùng `@SpringBootTest` có thể tải gần như toàn bộ application context: controller, service, repository, database configuration, security, transport và nhiều bean khác. Điều này hữu ích cho integration test nhưng làm test controller chậm và phụ thuộc nhiều thành phần.

Test slice chỉ tải một phần ứng dụng phù hợp với mục tiêu kiểm thử. `@GraphQlTest` tập trung vào GraphQL infrastructure và các thành phần liên quan đến việc thực thi GraphQL request.

~~~mermaid
flowchart TD
    A[Test class có @GraphQlTest] --> B[Spring test context]
    B --> C[GraphQL auto-configuration]
    B --> D[GraphQL schema và runtime wiring]
    B --> E[GraphQL controller được chọn]
    B --> F[GraphQlTester]
    E --> G[Mock service / imported test bean]
    F --> H[GraphQL document]
    H --> I[GraphQL execution]
    I --> J[Response: data và errors]
~~~

Cách này giúp kiểm tra contract giữa GraphQL schema và controller mà không cần khởi chạy server hoặc kết nối database thật.

## 2. Dependency cần thiết

Spring GraphQL cung cấp module test chứa `GraphQlTester`. Với Spring Boot 3.x, có thể thêm dependency sau vào Maven:

~~~xml
<dependency>
    <groupId>org.springframework.graphql</groupId>
    <artifactId>spring-graphql-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

Hoặc Gradle:

~~~gradle
dependencies {
    // Spring Boot 3.x
    testImplementation("org.springframework.graphql:spring-graphql-test")

    // Spring Boot 4.x: use the Boot test starter instead
    // testImplementation("org.springframework.boot:spring-boot-starter-graphql-test")
}
~~~

Nếu dùng `HttpGraphQlTester` với `WebTestClient` trong test HTTP, cần có WebFlux test client trên test classpath khi ứng dụng chưa có dependency tương ứng.

Spring Boot 4 tách test support thành các module theo công nghệ. Có thể dùng starter `spring-boot-starter-graphql-test` trong test scope; starter này đưa GraphQL test support của Spring vào classpath. Khi dùng dependency management của Spring Boot, không cần tự đặt version cho dependency được quản lý.

Tên package của annotation cũng thay đổi theo major version:

| Phiên bản | Import `@GraphQlTest` |
| --- | --- |
| Spring Boot 3.x | `org.springframework.boot.test.autoconfigure.graphql.GraphQlTest` |
| Spring Boot 4.x | `org.springframework.boot.graphql.test.autoconfigure.GraphQlTest` |

Kiểm tra phiên bản Spring Boot của dự án trước khi sao chép import. `GraphQlTester` vẫn thuộc package `org.springframework.graphql.test.tester`.

## 3. @GraphQlTest tự cấu hình những gì?

`@GraphQlTest` tự cấu hình Spring GraphQL infrastructure và tester cần cho test. Các bean được đưa vào context thường gồm:

- `@Controller` và các GraphQL controller được chỉ định.
- `@ControllerAdvice` để xử lý exception của controller.
- `RuntimeWiringConfigurer` để đăng ký runtime wiring.
- Các converter và JSON component liên quan.
- `DataFetcherExceptionResolver`.
- `Instrumentation`.
- `GraphQlSourceBuilderCustomizer`.
- GraphQL schema/runtime và `GraphQlTester`.

Danh sách cụ thể phụ thuộc Spring Boot version. Các bean thông thường như `@Service`, `@Repository` và `@Component` không tự động được quét trong test slice này. Đây là lý do một controller cần service thường được kết hợp với `@MockitoBean` hoặc import test configuration.

`@GraphQlTest` cũng không tự tạo một HTTP server. GraphQL request được gửi trực tiếp vào GraphQL execution infrastructure trong test context.

## 4. Chỉ định controller cần kiểm thử

Nên chỉ định rõ controller trong annotation để context chỉ tải phần GraphQL cần thiết:

~~~java
import org.springframework.boot.test.autoconfigure.graphql.GraphQlTest;

@GraphQlTest(BookController.class)
class BookControllerTests {
    // tests
}
~~~

Đối với Spring Boot 4, thay import bằng package mới:

~~~java
import org.springframework.boot.graphql.test.autoconfigure.GraphQlTest;
~~~

Nếu bỏ danh sách controller, test slice có thể đưa tất cả GraphQL controller được phát hiện vào context. Điều này tiện khi test nhiều resolver phối hợp, nhưng có thể làm test context lớn hơn và tạo thêm dependency không liên quan.

Có thể chỉ định nhiều controller:

~~~java
@GraphQlTest({
    BookController.class,
    AuthorController.class
})
class BookAndAuthorGraphQlTests {
}
~~~

Chọn controller theo một nhóm hành vi có liên quan. Nếu test chỉ nhắm vào query sách, không cần tải thêm controller cho account hoặc payment.

## 5. Ví dụ schema và controller

Giả sử ứng dụng có schema SDL sau trong thư mục resource GraphQL:

Schema mặc định thường được đặt dưới `src/main/resources/graphql/`, ví dụ `src/main/resources/graphql/schema.graphqls`. Nếu ứng dụng tùy chỉnh schema locations, test context cần dùng đúng cấu hình đó.

~~~graphql
type Query {
    book(id: ID!): Book
}

type Book {
    id: ID!
    title: String!
}
~~~

Controller xử lý query:

~~~java
package com.example.graphql.book;

import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.stereotype.Controller;

@Controller
public class BookController {

    private final BookService bookService;

    public BookController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    public BookView book(@Argument("id") String id) {
        return bookService.findById(id);
    }
}
~~~

DTO trả về:

~~~java
package com.example.graphql.book;

public record BookView(String id, String title) {
}
~~~

Service là collaborator của controller:

~~~java
package com.example.graphql.book;

public interface BookService {
    BookView findById(String id);
}
~~~

Trong bài test slice, mục tiêu là xác minh GraphQL field `book` gọi đúng controller method, argument `id` được bind chính xác và dữ liệu trả về được chuyển thành response theo schema.

## 6. Viết test đầu tiên với @GraphQlTest

Ví dụ test query bằng `GraphQlTester` và mock service bằng `@MockitoBean`:

~~~java
package com.example.graphql.book;

import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.graphql.GraphQlTest;
import org.springframework.graphql.test.tester.GraphQlTester;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

@GraphQlTest(BookController.class)
class BookControllerTests {

    @Autowired
    GraphQlTester graphQlTester;

    @MockitoBean
    BookService bookService;

    @Test
    void returnsBookById() {
        when(bookService.findById("book-42"))
            .thenReturn(new BookView("book-42", "Spring GraphQL"));

        GraphQlTester.Response response = graphQlTester.document("""
                query FindBook($id: ID!) {
                    book(id: $id) {
                        id
                        title
                    }
                }
                """)
            .variable("id", "book-42")
            .execute();

        response.path("book.id")
            .entity(String.class)
            .isEqualTo("book-42");

        response.path("book.title")
            .entity(String.class)
            .isEqualTo("Spring GraphQL");

        verify(bookService).findById("book-42");
    }
}
~~~

Trong test:

1. `@GraphQlTest(BookController.class)` tạo GraphQL test context chỉ tập trung vào controller được chọn.
2. `@MockitoBean` thay bean `BookService` bằng Mockito mock trong context.
3. `GraphQlTester` gửi GraphQL document như một operation thực.
4. `variable("id", "book-42")` truyền variable cho document.
5. `path("book.id")` đọc field tương ứng trong phần `data` của GraphQL response.
6. `verify` xác nhận controller gọi service với đúng ID.

Ví dụ dùng `@MockitoBean` của Spring Framework 6.2 trở lên (Spring Boot 3.4+). Với dự án cũ hơn, có thể dùng `@MockBean` của Spring Boot; annotation này đã được thay thế và deprecated trong các phiên bản mới.

## 7. GraphQlTester hoạt động như thế nào?

`GraphQlTester` cung cấp workflow thống nhất để gửi request và kiểm tra response. Các bước thường gặp:

~~~java
graphQlTester.document("""
        query {
            books {
                id
                title
            }
        }
        """)
    .execute()
    .path("books")
    .entityList(BookView.class)
    .hasSize(2);
~~~

Các thao tác quan trọng:

| API | Mục đích |
| --- | --- |
| `document(String)` | Cung cấp GraphQL document trực tiếp |
| `documentName(String)` | Tải document từ resource theo tên |
| `variable(name, value)` | Gán giá trị cho GraphQL variable |
| `operationName(String)` | Chọn operation trong document có nhiều operation |
| `execute()` | Thực thi query/mutation và nhận response |
| `executeAndVerify()` | Thực thi và xác minh response không có GraphQL errors |
| `path(String)` | Chọn đường dẫn trong phần data |
| `entity(Class)` | Chuyển node thành Java entity để assert |
| `entityList(Class)` | Chuyển danh sách node thành danh sách Java |
| `errors()` | Kiểm tra lỗi trong GraphQL response |

Đường dẫn trong `path` mặc định tính từ phần `data` của response, không cần thêm prefix `data.`. Có thể dùng JsonPath như `books[*].title` để kiểm tra nhiều phần tử.

## 8. Truyền variables và kiểm tra argument

Nên dùng GraphQL variables khi kiểm thử argument, đặc biệt với input object hoặc document dài:

~~~java
@Test
void findsBookUsingVariable() {
    when(bookService.findById("book-7"))
        .thenReturn(new BookView("book-7", "GraphQL in Practice"));

    graphQlTester.document("""
            query FindBook($id: ID!) {
                book(id: $id) {
                    id
                    title
                }
            }
            """)
        .variable("id", "book-7")
        .execute()
        .path("book.title")
        .entity(String.class)
        .isEqualTo("GraphQL in Practice");
}
~~~

Nếu variable thiếu, sai kiểu hoặc vi phạm nullability trong SDL, GraphQL engine có thể từ chối request trước khi resolver chạy. Test có thể xác minh lỗi coercion/validation mà không cần gọi service.

Đối với mutation input object, truyền map tương ứng:

~~~java
import java.util.Map;

graphQlTester.document("""
        mutation CreateBook($input: CreateBookInput!) {
            createBook(input: $input) {
                id
                title
            }
        }
        """)
    .variable("input", Map.of(
        "title", "Spring for GraphQL",
        "isbn", "9780000000000"
    ))
    .execute()
    .path("createBook.title")
    .entity(String.class)
    .isEqualTo("Spring for GraphQL");
~~~

Test cần mock hoặc import collaborator được controller sử dụng. Nếu mutation có side effect, hãy xác minh service nhận đúng command và chỉ được gọi theo số lần mong muốn.

## 9. Kiểm thử mutation

Ví dụ controller có mutation tạo sách:

~~~java
@MutationMapping
public BookView createBook(@Argument("input") CreateBookInput input) {
    return bookService.create(input);
}
~~~

Test có thể xác minh input binding và kết quả:

~~~java
import java.util.Map;

@Test
void createsBook() {
    CreateBookInput input =
        new CreateBookInput("Spring for GraphQL", "9780000000000");

    when(bookService.create(input))
        .thenReturn(new BookView("book-99", "Spring for GraphQL"));

    graphQlTester.document("""
            mutation CreateBook($input: CreateBookInput!) {
                createBook(input: $input) {
                    id
                    title
                }
            }
            """)
        .variable("input", Map.of(
            "title", "Spring for GraphQL",
            "isbn", "9780000000000"
        ))
        .execute()
        .path("createBook.id")
        .entity(String.class)
        .isEqualTo("book-99");

    verify(bookService).create(input);
}
~~~

Ví dụ giả định `CreateBookInput` là record có hai field và controller nhận DTO tương ứng. Mockito so sánh record theo giá trị; nếu dùng class mutable không có equals phù hợp, có thể dùng `argThat` hoặc `ArgumentCaptor` để kiểm tra các field.

Nếu mutation không trả data hữu ích và chỉ cần xác minh operation không có lỗi, dùng `executeAndVerify()`. Nếu cần kiểm tra payload hoặc errors, dùng `execute()` rồi kiểm tra từng path.

## 10. Kiểm tra GraphQL errors

GraphQL execution có thể trả response gồm `data` một phần và `errors`. Khi muốn xác minh lỗi là kết quả mong đợi, dùng `errors().expect(...)`:

~~~java
@Test
void returnsGraphQlErrorWhenBookDoesNotExist() {
    when(bookService.findById("missing"))
        .thenThrow(new BookNotFoundException("missing"));

    graphQlTester.document("""
            query {
                book(id: "missing") {
                    id
                    title
                }
            }
            """)
        .execute()
        .errors()
        .expect(error -> error.getMessage().contains("Book not found"))
        .verify();
}
~~~

Ví dụ giả định test context có `@ControllerAdvice` hoặc `DataFetcherExceptionResolver` ánh xạ `BookNotFoundException` thành message `Book not found`. Nếu ứng dụng không có handler như vậy, hãy assert mã/phân loại lỗi thực tế thay vì giả định exception message luôn được gửi nguyên văn cho client.

Có thể kiểm tra mã lỗi trong `extensions` hoặc path nếu error handler của ứng dụng cung cấp chúng. Không nên chỉ so sánh toàn bộ message nếu message có thể thay đổi theo locale hoặc cách diễn đạt; mã lỗi ổn định thường phù hợp hơn cho hợp đồng client.

Nếu response có lỗi dự kiến nhưng vẫn cần kiểm tra partial data, hãy lọc hoặc xác nhận lỗi trước khi đọc path:

~~~java
graphQlTester.document(query)
    .execute()
    .errors()
    .expect(error -> error.getMessage().contains("Author unavailable"))
    .verify()
    .path("book.title")
    .entity(String.class)
    .isEqualTo("Spring GraphQL");
~~~

`verify()` xác nhận các lỗi chưa được xử lý không còn. Nếu muốn kiểm tra nhiều lỗi bằng một consumer, có thể dùng `errors().satisfy(...)` để assert danh sách và đánh dấu chúng đã được xử lý.

## 11. Tải GraphQL document từ file

Khi query dài hoặc được dùng trong nhiều test, đặt document trong resource test thay vì viết inline.

Ví dụ cấu trúc:

~~~text
src
└── test
    └── resources
        └── graphql-test
            ├── findBook.graphql
            └── createBook.graphql
~~~

Nội dung `findBook.graphql`:

~~~graphql
query FindBook($id: ID!) {
    book(id: $id) {
        id
        title
    }
}
~~~

Dùng `documentName` để tải file:

~~~java
graphQlTester.documentName("findBook")
    .variable("id", "book-42")
    .execute()
    .path("book.id")
    .entity(String.class)
    .isEqualTo("book-42");
~~~

Mặc định, `GraphQlTester` tìm document trong thư mục `graphql-test/` trên classpath với phần mở rộng `.graphql` hoặc `.gql`. Cách này giúp test dễ đọc, tách biệt query fixture khỏi assertion và có thể tái sử dụng fragment.

Khi dùng fragment file riêng, có thể thêm fragment bằng API tương ứng của request spec. Đảm bảo fragment được khai báo đúng type condition và tên không trùng với fragment khác trong document.

## 12. Import thêm bean và cấu hình test

Nếu controller cần một bean không được test slice tự động nạp, có thể dùng `@Import`:

~~~java
@GraphQlTest(BookController.class)
@Import(BookTestConfiguration.class)
class BookControllerTests {
}
~~~

`BookTestConfiguration` có thể cung cấp một test bean, `RuntimeWiringConfigurer` hoặc cấu hình bổ sung cần cho GraphQL runtime.

Nếu cần cấu hình thuộc tính, dùng thuộc tính `properties` của annotation:

~~~java
@GraphQlTest(
    controllers = BookController.class,
    properties = {
        "app.graphql.feature-enabled=true"
    }
)
class BookControllerTests {
}
~~~

Nếu ứng dụng dùng `@ConfigurationProperties`, test slice không tự quét mọi bean cấu hình. Có thể dùng `@EnableConfigurationProperties` cho class cần thiết hoặc import cấu hình tương ứng.

Không import toàn bộ application configuration chỉ để làm một service mock xuất hiện. Điều đó có thể biến slice test thành một context lớn khó kiểm soát. Dùng `@MockitoBean` cho collaborator cần thay thế và `@Import` cho cấu hình GraphQL thật sự cần thiết.

## 13. Kiểm thử nested field và resolver mapping

`@GraphQlTest` phù hợp để kiểm tra nested field resolver, ví dụ query sách kèm tác giả:

~~~graphql
type Query {
    book(id: ID!): Book
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

Controller có thể xử lý root query và field tác giả:

~~~java
@Controller
public class BookController {

    @QueryMapping
    public Book book(@Argument String id) {
        return bookService.findById(id);
    }

    @SchemaMapping(typeName = "Book", field = "author")
    public Author author(Book book) {
        return authorService.findByBookId(book.id());
    }
}
~~~

Một test GraphQL document có thể chọn cả `book` và `author` để xác minh GraphQL runtime gọi đúng resolver cho từng field:

~~~java
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
~~~

Mock cả service được sử dụng bởi root query và nested resolver. Phần khai báo field, constructor và dependency injection của controller được lược bỏ để tập trung vào resolver. Test này kiểm tra GraphQL mapping giữa nhiều field; nó không chứng minh hiệu năng truy vấn database hoặc DataLoader batching ở môi trường thật. Với batching, có thể xác minh batch loader được gọi với tập key mong đợi bằng mock/spy hoặc viết test chuyên biệt cho DataLoader.

## 14. Những gì @GraphQlTest không kiểm thử

`@GraphQlTest` không tạo HTTP server hoặc WebSocket connection. Do đó, nó không phù hợp để xác minh:

- HTTP route như `/graphql` có được đăng ký đúng không.
- HTTP status code, request header hoặc response header.
- CORS, CSRF, servlet filter hoặc WebFlux security filter chain.
- WebSocket handshake, `connection_init` hoặc lifecycle transport thật.
- RSocket route, metadata và kết nối TCP/WebSocket.
- Reverse proxy, TLS hoặc cấu hình mạng.
- Database query thật nếu service/repository đã được mock.
- Tích hợp đầy đủ giữa toàn bộ bean production.

Một GraphQL operation chạy thành công trong slice test không chứng minh endpoint HTTP có thể truy cập từ client. Nó chỉ chứng minh GraphQL execution trong test context hoạt động theo cách đã cấu hình.

## 15. Khi nào dùng @SpringBootTest thay cho @GraphQlTest?

Dùng `@SpringBootTest` khi cần kiểm tra nhiều lớp cùng hoạt động hoặc muốn xác minh transport. Với HTTP integration test, có thể khởi chạy server trên cổng ngẫu nhiên và dùng `HttpGraphQlTester`:

~~~java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureHttpGraphQlTester
class BookGraphQlIntegrationTests {

    @Test
    void queriesBook(@Autowired HttpGraphQlTester graphQlTester) {
        graphQlTester.document("""
                query {
                    book(id: "book-42") {
                        id
                        title
                    }
                }
                """)
            .execute()
            .path("book.id")
            .entity(String.class)
            .isEqualTo("book-42");
    }
}
~~~

Import của `@AutoConfigureHttpGraphQlTester` cũng thay đổi package giữa Spring Boot major versions. Hãy dùng package tương ứng với Boot version của dự án.

Với test mock web environment, có thể dùng `@AutoConfigureHttpGraphQlTester` cùng `@SpringBootTest(webEnvironment = MOCK)` nếu muốn kiểm tra HTTP handler nhưng không mở cổng thật. Với live server, `RANDOM_PORT` kiểm tra cả server và transport qua cổng được cấp.

Chọn phạm vi theo mục tiêu:

| Mục tiêu | Cách test phù hợp |
| --- | --- |
| GraphQL field mapping và argument binding | `@GraphQlTest` |
| GraphQL errors và controller advice | `@GraphQlTest` |
| Input coercion, schema validation và response shape | `@GraphQlTest` |
| Controller gọi đúng service | `@GraphQlTest` + `@MockitoBean` |
| HTTP route, headers và status | `@SpringBootTest` + `HttpGraphQlTester` |
| Security filter chain và authentication HTTP | `@SpringBootTest` với cấu hình security |
| WebSocket subscription transport | `WebSocketGraphQlTester` với WebSocket server/handler phù hợp |
| Database và repository thật | Integration test với cấu hình persistence phù hợp |

## 16. Lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Không tìm thấy service khi tạo test context | `@Service` không được quét trong GraphQL slice | Dùng `@MockitoBean` hoặc `@Import` |
| Không inject được `GraphQlTester` | Thiếu GraphQL test dependency hoặc test auto-configuration | Thêm test module phù hợp và kiểm tra Boot version |
| `@GraphQlTest` không nhận controller | Controller không được chỉ định hoặc nằm ngoài phạm vi scan | Truyền class vào annotation |
| Schema không tìm thấy field | Schema resource không nằm ở vị trí được cấu hình hoặc SDL sai | Kiểm tra schema resource và GraphQL field definition |
| Query trả lỗi trước khi vào resolver | Document validation hoặc variable coercion thất bại | Kiểm tra tên field, argument, scalar và nullability |
| Mock service không được gọi | Query sai field, resolver không được nạp hoặc response lỗi trước execution | Kiểm tra schema, controller selection và `errors()` |
| Test HTTP mong đợi nhưng không có status code | `@GraphQlTest` không chạy HTTP transport | Dùng `@SpringBootTest` với HTTP tester |
| Lỗi GraphQL làm assertion thất bại | Test chưa xác nhận hoặc lọc lỗi dự kiến | Dùng `errors().expect(...)` hoặc `satisfy(...)` |
| Test context tải quá nhiều bean | Không giới hạn controller hoặc import cấu hình quá rộng | Chỉ định controller và mock collaborator |
| Import `@GraphQlTest` không đúng | Package thay đổi giữa Boot 3 và Boot 4 | Kiểm tra package theo major version |
| Test mutation gọi service nhiều lần | Operation hoặc test setup gây nhiều execution | Xác minh document và số lần gọi bằng Mockito |

## 17. Checklist viết test với @GraphQlTest

- Đã chọn đúng controller cần kiểm thử?
- Schema SDL được nạp trong test context và field/argument khớp controller?
- Collaborator như service đã được thay bằng `@MockitoBean` hoặc import phù hợp?
- `GraphQlTester` được inject và dùng để gửi document?
- Test có xác minh cả dữ liệu trả về lẫn lời gọi service cần thiết?
- Variables và input object có được truyền theo đúng GraphQL type?
- GraphQL errors được xác nhận rõ ràng thay vì bỏ qua?
- Nested field resolver và controller advice đã được kiểm tra nếu thuộc phạm vi?
- Test không giả định rằng HTTP transport, security filter hoặc database thật đã chạy?
- Các yêu cầu HTTP/WebSocket/RSocket đã có integration test riêng?
- Import và test dependency có khớp Spring Boot major version?

`@GraphQlTest` giúp kiểm thử GraphQL controller trong một Spring context gọn, có schema/runtime và `GraphQlTester` nhưng không cần khởi chạy server. Chỉ định controller, mock collaborator bằng `@MockitoBean` và gửi document qua `GraphQlTester` để kiểm tra field mapping, argument binding, response và errors. Khi cần xác minh HTTP transport, security, WebSocket hoặc database thật, chuyển sang integration test với tester và môi trường phù hợp.

## Tài liệu tham khảo

- [Spring Boot — Auto-configured Spring GraphQL Tests](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html)
- [Spring Boot 3 — GraphQlTest API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/autoconfigure/graphql/GraphQlTest.html)
- [Spring Boot 4 — GraphQlTest API](https://docs.spring.io/spring-boot/4.2/api/java/org/springframework/boot/graphql/test/autoconfigure/GraphQlTest.html)
- [Spring for GraphQL — Testing](https://docs.spring.io/spring-graphql/reference/testing.html)




