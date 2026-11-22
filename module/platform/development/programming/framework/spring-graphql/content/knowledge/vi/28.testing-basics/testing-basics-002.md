# HttpGraphQlTester trong Spring for GraphQL

## Mục tiêu

Sau bài học này, bạn có thể:

- Giải thích vai trò của `HttpGraphQlTester` trong kiểm thử Spring for GraphQL.
- Phân biệt kiểm thử GraphQL execution với kiểm thử qua HTTP transport.
- Cấu hình `HttpGraphQlTester` từ `WebTestClient`.
- Viết integration test gửi GraphQL document và variables qua HTTP.
- Kiểm tra dữ liệu trả về bằng `path`, `entity` và `entityList`.
- Xác minh GraphQL errors, error path và mã lỗi.
- Gửi authentication headers và kiểm tra authorization qua HTTP.
- Phân biệt GraphQL response assertions với HTTP status/header assertions.
- Kiểm thử validation, input binding và các trường hợp lỗi.
- Hiểu giới hạn của `HttpGraphQlTester` với Subscription và WebSocket.

## 1. HttpGraphQlTester dùng để làm gì?

`HttpGraphQlTester` là công cụ kiểm thử GraphQL client của Spring for GraphQL dành cho HTTP transport. Nó gửi GraphQL operation qua HTTP tới endpoint của ứng dụng, sau đó cung cấp API để kiểm tra `data` và `errors` trong GraphQL response.

Công cụ này phù hợp khi cần xác minh toàn bộ đường đi từ HTTP request tới resolver:

- HTTP endpoint có được cấu hình đúng không?
- GraphQL document có được parse và validate không?
- Variables có được bind vào argument và input DTO không?
- Resolver có trả dữ liệu đúng không?
- Security filter có xác thực và áp dụng quyền không?
- Exception có được chuyển thành GraphQL error theo contract không?

Ví dụ, thay vì gọi trực tiếp method `BookController.book(...)`, test gửi operation `query { book(id: ...) { ... } }` tới `/graphql`. Request đi qua web server, GraphQL HTTP handler, interceptor, execution engine và resolver như một client thật.

`HttpGraphQlTester` giúp viết assertion ở cấp GraphQL response, tránh phải tự parse JSON response trong từng test.

## 2. Phân biệt các loại GraphQlTester

Spring for GraphQL có nhiều cách kiểm thử tùy ranh giới cần xác minh:

| Tester | Ranh giới kiểm thử | Khi nên dùng |
| --- | --- | --- |
| `ExecutionGraphQlServiceTester` | GraphQL execution service | Kiểm thử execution và resolver mà không cần HTTP transport |
| `HttpGraphQlTester` | HTTP GraphQL endpoint | Kiểm thử request/response qua HTTP, headers và web security |
| `WebSocketGraphQlTester` | WebSocket GraphQL transport | Kiểm thử subscription và luồng response qua WebSocket |
| `RSocketGraphQlTester` | RSocket transport | Kiểm thử ứng dụng dùng RSocket |

Nếu mục tiêu là xác minh `@QueryMapping`, `@MutationMapping` hoặc `@SchemaMapping` trong execution layer, tester ở execution boundary có thể đủ.

Nếu cần xác minh URL, HTTP headers, filter chain, CORS integration hoặc request thực sự tới endpoint, hãy dùng `HttpGraphQlTester`.

Không dùng `HttpGraphQlTester` để kết luận Subscription hoạt động qua WebSocket. HTTP request/response và WebSocket subscription là hai transport khác nhau.

## 3. Chuẩn bị dependency kiểm thử

Trong Maven project, cần dependency kiểm thử của Spring GraphQL:

~~~xml
<dependency>
    <groupId>org.springframework.graphql</groupId>
    <artifactId>spring-graphql-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

Nếu dự án dùng Spring Boot dependency management, version của `spring-graphql-test` nên được quản lý đồng bộ với Spring GraphQL mà Boot cung cấp. Không tự chọn một version khác với dependency runtime.

Các dependency test thường dùng cùng:

- `spring-boot-starter-test` cho JUnit Jupiter, AssertJ và Spring Test.
- `spring-test` cung cấp `WebTestClient`.
- `spring-graphql-test` cung cấp `HttpGraphQlTester` và các GraphQL tester API.

Kiểm tra test scope để dependency hỗ trợ kiểm thử không bị đóng gói vào runtime artifact nếu ứng dụng không cần chúng lúc chạy.

## 4. Tạo HttpGraphQlTester từ WebTestClient

`HttpGraphQlTester` nhận một `WebTestClient` đã được cấu hình để truy cập GraphQL endpoint.

Ví dụ kết nối tới server đang chạy:

~~~java
import org.springframework.graphql.test.tester.HttpGraphQlTester;
import org.springframework.test.web.reactive.server.WebTestClient;

WebTestClient webTestClient = WebTestClient.bindToServer()
        .baseUrl("http://localhost:8080")
        .build();

HttpGraphQlTester graphQlTester =
        HttpGraphQlTester.create(webTestClient);
~~~

Trong cấu hình Spring Boot mặc định, GraphQL HTTP endpoint thường là `/graphql`. `HttpGraphQlTester` sử dụng endpoint GraphQL mặc định của tester; nếu ứng dụng đổi path, hãy cấu hình URL của tester tương ứng với path thực tế theo API của phiên bản Spring GraphQL đang dùng.

`WebTestClient.bindToServer()` kết nối tới một server qua HTTP. Vì vậy, server phải được khởi động trước khi test gửi request.

Đối với integration test, thường dùng server port ngẫu nhiên để tránh xung đột cổng giữa các lần chạy test.

## 5. Tạo tester trong Spring Boot integration test

Có thể dùng `@SpringBootTest` với random port, sau đó tạo `WebTestClient` và `HttpGraphQlTester` trong test fixture.

~~~java
import org.junit.jupiter.api.BeforeEach;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.graphql.test.tester.HttpGraphQlTester;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class BookHttpGraphQlTests {

    @LocalServerPort
    int port;

    HttpGraphQlTester graphQlTester;

    @BeforeEach
    void setUp() {
        WebTestClient webTestClient = WebTestClient.bindToServer()
                .baseUrl("http://localhost:" + port)
                .build();

        graphQlTester = HttpGraphQlTester.create(webTestClient);
    }
}
~~~

Trong test:

- `RANDOM_PORT` khởi động ứng dụng trên cổng khả dụng do test environment chọn.
- `@LocalServerPort` cung cấp cổng thực tế.
- `WebTestClient.bindToServer()` kết nối tới server đang chạy.
- `HttpGraphQlTester.create(...)` tạo GraphQL tester dùng HTTP.

Cách này kiểm thử HTTP transport thật của ứng dụng. Đổi lại, test khởi động nhiều thành phần hơn và thường chậm hơn test chỉ kiểm tra GraphQL execution.

## 6. Gửi GraphQL document và variables

API của `HttpGraphQlTester` dùng cùng kiểu request fluent với các GraphQL tester khác.

Ví dụ test Query:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.graphql.test.tester.GraphQlTester;

@Test
void shouldReturnBook() {
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
            .isEqualTo("Spring for GraphQL");
}
~~~

`document(...)` chứa GraphQL operation. `variable(...)` gán giá trị cho variable đã khai báo trong document. `execute()` gửi operation qua HTTP và trả về đối tượng response để kiểm tra.

Nên dùng variables thay vì nối dữ liệu vào query string. Cách này làm document ổn định, dễ đọc và giúp test bao phủ nhiều bộ input khác nhau.

Nếu document có nhiều operation, cần chọn operation phù hợp theo API request builder của phiên bản đang dùng. Trong đa số test, mỗi document nên chứa một operation có tên rõ ràng để kết quả dễ hiểu.

## 7. Kiểm tra object và scalar bằng path

Sau khi thực thi, `GraphQlTester.Response` cho phép truy cập field trong `data` bằng `path(...)`.

Ví dụ:

~~~java
GraphQlTester.Response response = graphQlTester.document("""
        query {
            book(id: "book-42") {
                id
                title
                published
            }
        }
        """)
        .execute();

response.path("book.id")
        .entity(String.class)
        .isEqualTo("book-42");

response.path("book.title")
        .entity(String.class)
        .isEqualTo("Spring for GraphQL");

response.path("book.published")
        .entity(Boolean.class)
        .isEqualTo(true);
~~~

Các path trong ví dụ được tính từ nội dung GraphQL `data`, không cần thêm tiền tố `data.`.

`entity(Class<T>)` chuyển giá trị tại path thành kiểu Java mong muốn. Dùng kiểu rõ ràng giúp test phát hiện sai khác giữa schema, serialization và DTO.

Với field nullable, cần viết assertion cho cả trường hợp có giá trị và `null` theo contract. Không mặc định rằng mọi field trả `null` đều là lỗi; có thể đó là kết quả hợp lệ của schema.

## 8. Kiểm tra danh sách và nested object

Có thể dùng `entityList(...)` để kiểm tra danh sách:

~~~java
GraphQlTester.Response response = graphQlTester.document("""
        query {
            books {
                id
                title
            }
        }
        """)
        .execute();

response.path("books[*].id")
        .entityList(String.class)
        .contains("book-42", "book-99");
~~~

Ký hiệu `[*]` chọn field tương ứng trên các phần tử của list.

Với nested object, có thể đi sâu theo path:

~~~java
response.path("books[0].title")
        .entity(String.class)
        .isEqualTo("Spring for GraphQL");
~~~

Nếu thứ tự list không phải một phần của API contract, tránh assertion dựa vào index. Hãy kiểm tra tập ID hoặc thuộc tính có ý nghĩa để test không phụ thuộc thứ tự không được bảo đảm.

Nếu list có pagination, kiểm tra riêng:

- Các phần tử trong trang.
- Cursor hoặc page information.
- Tổng số bản ghi nếu API cung cấp.
- Hành vi khi page size vượt giới hạn.

## 9. Kiểm tra GraphQL errors

GraphQL response có thể chứa `data`, `errors` hoặc cả hai. Vì vậy, test cần chủ động xác định operation mong đợi thành công hay mong đợi lỗi.

Với operation thành công, có thể dùng:

~~~java
graphQlTester.document("""
        query {
            book(id: "book-42") {
                id
                title
            }
        }
        """)
        .execute()
        .errors()
        .verify();
~~~

`verify()` xác minh response không có GraphQL errors. Nếu có lỗi, assertion sẽ thất bại và test chỉ ra response chứa lỗi.

Với trường hợp mong đợi lỗi, hãy kiểm tra error contract:

~~~java
GraphQlTester.Response response = graphQlTester.document("""
        query {
            book(id: "missing-book") {
                id
                title
            }
        }
        """)
        .execute();

response.errors().satisfy(errors -> {
    assertThat(errors).hasSize(1);
    assertThat(errors.get(0).getMessage())
            .isEqualTo("Không tìm thấy sách được yêu cầu.");
    assertThat(errors.get(0).getExtensions())
            .containsEntry("code", "BOOK_NOT_FOUND");
});
~~~

Không chỉ kiểm tra rằng có một error. Nên kiểm tra message đã chuẩn hóa, mã lỗi và path khi chúng thuộc API contract.

Không so sánh toàn bộ error object nếu những phần như `locations` hoặc thông tin nội bộ của runtime có thể thay đổi giữa phiên bản GraphQL. Chỉ assertion các thuộc tính có ý nghĩa với client.

## 10. Kiểm tra partial data và error path

Một nested field có thể lỗi trong khi các field khác vẫn trả dữ liệu.

Ví dụ:

~~~graphql
type Book {
    id: ID!
    title: String!
    internalNotes: String
}
~~~

Nếu `internalNotes` lỗi nhưng field cha còn hợp lệ, response có thể chứa `book.id`, `book.title` cùng error path `["book", "internalNotes"]`.

Test có thể kiểm tra cả phần dữ liệu thành công và error:

~~~java
GraphQlTester.Response response = graphQlTester.document("""
        query {
            book(id: "book-42") {
                id
                title
                internalNotes
            }
        }
        """)
        .execute();

response.path("book.id")
        .entity(String.class)
        .isEqualTo("book-42");

response.errors().satisfy(errors -> {
    assertThat(errors).anySatisfy(error ->
            assertThat(error.getPath())
                    .contains("book", "internalNotes")
    );
});
~~~

Kiểm thử như vậy xác minh GraphQL partial response, nullability và error mapping cùng lúc.

Nếu schema khai báo field là non-null, GraphQL có thể truyền `null` lên parent gần nhất cho phép null. Test cần phản ánh đúng null propagation của SDL, không giả định field lỗi luôn chỉ ảnh hưởng chính field đó.

## 11. Kiểm thử Mutation và input binding

`HttpGraphQlTester` cũng phù hợp để kiểm tra Mutation qua HTTP.

Ví dụ:

~~~java
GraphQlTester.Response response = graphQlTester.document("""
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
        .execute();

response.path("createBook.title")
        .entity(String.class)
        .isEqualTo("Spring for GraphQL");
~~~

Test này kiểm tra nhiều bước:

1. Document khai báo input variable đúng kiểu.
2. Tester serialize object variables thành JSON.
3. GraphQL validate input theo schema.
4. Spring bind input thành argument/DTO của resolver.
5. Mutation thực thi nghiệp vụ và trả payload.

Ngoài kết quả trả về, test Mutation nên xác minh side effect cần thiết qua repository hoặc service test fixture. Không chỉ kiểm tra response nếu nghiệp vụ yêu cầu dữ liệu được lưu bền vững.

Với test có ghi database, cần chuẩn bị dữ liệu riêng cho từng test và dọn dữ liệu theo chiến lược transaction/fixture của integration test. Không để test phụ thuộc thứ tự chạy.

## 12. Kiểm tra authentication và HTTP headers

Một lợi ích của `HttpGraphQlTester` là có thể gửi request qua HTTP với các header như client thật.

Ví dụ tạo `WebTestClient` có Bearer token:

~~~java
import org.springframework.http.HttpHeaders;

WebTestClient webTestClient = WebTestClient.bindToServer()
        .baseUrl("http://localhost:" + port)
        .defaultHeader(
                HttpHeaders.AUTHORIZATION,
                "Bearer " + testAccessToken
        )
        .build();

HttpGraphQlTester authenticatedTester =
        HttpGraphQlTester.create(webTestClient);
~~~

Sau đó dùng `authenticatedTester` để kiểm tra operation cần đăng nhập.

Nên có các trường hợp:

- Request có token hợp lệ được phép gọi operation.
- Request thiếu token bị từ chối theo security configuration.
- Token hợp lệ nhưng thiếu authority không đọc được field nhạy cảm.
- Người dùng thuộc tenant khác không truy cập được object.
- Error response không làm lộ token hoặc chi tiết xác thực.

Không dùng `@WithMockUser` trên test chạy tới server port ngẫu nhiên rồi giả định Authentication tự truyền sang server thread. Với HTTP integration test, hãy gửi credential qua cơ chế transport thật hoặc cấu hình test security filter chain tương ứng. `@WithMockUser` phù hợp hơn với test chạy trong cùng test application context và security context được tích hợp đúng cách.

Không ghi token thật vào source code hoặc log. Dùng token test ngắn hạn hoặc cơ chế authentication giả lập chỉ tồn tại trong test profile.

## 13. Khi cần kiểm tra HTTP status và response headers

`HttpGraphQlTester` tập trung vào GraphQL response. Khi cần kiểm tra chi tiết HTTP transport như status code, response headers hoặc content type, có thể dùng `WebTestClient` trực tiếp.

Ví dụ:

~~~java
import java.util.Map;

import org.springframework.http.MediaType;

webTestClient.post()
        .uri("/graphql")
        .contentType(MediaType.APPLICATION_JSON)
        .accept(MediaType.APPLICATION_JSON)
        .bodyValue(Map.of(
                "query", "query { book(id: \"book-42\") { id title } }"
        ))
        .exchange()
        .expectStatus().isOk()
        .expectHeader()
        .contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
        .expectBody()
        .jsonPath("$.data.book.id")
        .isEqualTo("book-42");
~~~

Cách phân chia:

- Dùng `HttpGraphQlTester` cho assertion có ngữ nghĩa GraphQL: data path, entity, error code và error path.
- Dùng `WebTestClient` trực tiếp cho assertion HTTP: status, header, content type, cookie và transport-level behavior.

Không giả định mọi GraphQL error đều phải có HTTP status 4xx hoặc 5xx. HTTP status còn phụ thuộc GraphQL over HTTP media type, phiên bản và cấu hình transport. Test nên xác minh hành vi mà API thực sự cam kết.

## 14. Kiểm tra CORS và request transport

Nếu frontend gọi GraphQL từ origin khác, CORS preflight có thể là một phần của yêu cầu tích hợp.

`HttpGraphQlTester` phù hợp với GraphQL POST nhưng không phải công cụ duy nhất để kiểm tra toàn bộ CORS handshake. Có thể dùng `WebTestClient` gửi `OPTIONS` request và kiểm tra các response header CORS.

Ví dụ:

~~~java
import org.springframework.http.HttpHeaders;

webTestClient.options()
        .uri("/graphql")
        .header(HttpHeaders.ORIGIN, "https://app.example.com")
        .header(
                HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD,
                "POST"
        )
        .header(
                HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS,
                "authorization,content-type"
        )
        .exchange()
        .expectStatus().isOk()
        .expectHeader()
        .valueEquals(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN,
                "https://app.example.com"
        );
~~~

Test cần khớp CORS policy của ứng dụng, bao gồm origin, method và allowed headers. Không dùng wildcard trong assertion nếu production policy yêu cầu origin cụ thể.

CORS chỉ kiểm soát browser cross-origin access. Nó không thay thế authentication hoặc authorization; test security vẫn cần kiểm tra các request có và không có credential.

## 15. Kiểm thử lỗi validation và argument binding

GraphQL parse và validation xảy ra trước khi resolver chạy. Test nên xác minh operation sai schema bị từ chối và không thực hiện side effect.

Ví dụ document dùng field không tồn tại:

~~~java
GraphQlTester.Response response = graphQlTester.document("""
        query {
            book(id: "book-42") {
                unknownField
            }
        }
        """)
        .execute();

response.errors().satisfy(errors ->
        assertThat(errors).isNotEmpty()
);
~~~

Với argument bắt buộc, có thể bỏ variable:

~~~java
GraphQlTester.Response response = graphQlTester.document("""
        query FindBook($id: ID!) {
            book(id: $id) {
                id
            }
        }
        """)
        .execute();

response.errors().satisfy(errors ->
        assertThat(errors).isNotEmpty()
);
~~~

Đối với input object, test thêm các trường hợp:

- Thiếu field non-null.
- Scalar sai kiểu.
- Enum value không tồn tại.
- Input object có field không được schema khai báo.
- Giá trị hợp lệ nhưng vi phạm business validation.

Validation error và business error là hai lớp khác nhau. Test nên xác minh resolver không bị gọi khi document không qua validation, và business error có mã riêng khi operation hợp lệ về schema nhưng vi phạm quy tắc nghiệp vụ.

## 16. Tái sử dụng tester và cấu hình headers

Nếu nhiều test cần cùng base URL hoặc authentication header, có thể tạo helper để khởi tạo `HttpGraphQlTester`.

Ví dụ:

~~~java
HttpGraphQlTester createTester(String token) {
    WebTestClient webTestClient = WebTestClient.bindToServer()
            .baseUrl("http://localhost:" + port)
            .defaultHeader(
                    HttpHeaders.AUTHORIZATION,
                    "Bearer " + token
            )
            .build();

    return HttpGraphQlTester.create(webTestClient);
}
~~~

Helper nên giữ cấu hình test tập trung:

- Base URL và GraphQL path.
- Authentication headers.
- Default headers cần thiết.
- Timeout phù hợp với test environment.
- Các giá trị cấu hình không nhạy cảm.

Không chia sẻ tester có token của user A cho test user B. Tạo tester riêng cho mỗi identity hoặc tạo client builder theo test case để tránh rò rỉ authentication state.

Nếu cần thay đổi cấu hình từ một tester đã tạo, dùng API mutate/builder được cung cấp bởi phiên bản Spring GraphQL thay vì thay đổi một `WebTestClient` đang được chia sẻ ngoài ý muốn.

## 17. Những giới hạn cần biết

`HttpGraphQlTester` rất hữu ích nhưng không thay thế mọi loại test:

- Nó không kiểm thử WebSocket handshake hoặc subscription stream.
- Nó không kiểm thử RSocket transport.
- Nó không tự xác minh database transaction nếu test không kiểm tra side effect.
- Nó không tự chứng minh authorization đúng cho mọi field và mọi tenant; cần tạo test cases phù hợp.
- Nó không thay thế unit test cho service logic.
- Nó không tự xác minh HTTP status/header nếu test chỉ dùng GraphQL response API.
- Nó không kiểm tra performance hoặc tải đồng thời chỉ bằng một request assertion.

Nên kết hợp nhiều tầng:

| Mục tiêu | Loại test phù hợp |
| --- | --- |
| Quy tắc service | Unit test hoặc method-level integration test |
| Resolver và schema mapping | GraphQL execution tester |
| HTTP endpoint, headers, security filters | `HttpGraphQlTester` và `WebTestClient` |
| Subscription | `WebSocketGraphQlTester` |
| Database query và transaction | Repository/integration test |
| Performance và load | Performance/load test riêng |

## 18. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Không kết nối được server | Server chưa chạy hoặc base URL sai | Dùng random port và kiểm tra lifecycle |
| Tester gọi sai endpoint | Ứng dụng đổi GraphQL path nhưng tester vẫn dùng path mặc định | Cấu hình URL tester theo path thực tế |
| `HttpGraphQlTester` không tìm thấy class | Thiếu `spring-graphql-test` ở test scope | Thêm dependency tương ứng |
| Assertion không tìm thấy field | Path không khớp cấu trúc `data` | Kiểm tra GraphQL response và path |
| Test pass dù response có lỗi | Chưa gọi `errors().verify()` hoặc chưa assert errors | Xác minh error contract tường minh |
| Error assertion quá mong manh | So sánh toàn bộ error object hoặc locations | Chỉ kiểm tra message/code/path thuộc contract |
| Test auth luôn bị anonymous | Token/header chưa gửi hoặc test dùng `@WithMockUser` sai boundary | Gửi credential qua HTTP hoặc cấu hình test security đúng |
| CORS test thất bại | Origin/header/method không khớp policy | Kiểm tra preflight request và CORS config |
| Test subscription không nhận event | Dùng HTTP tester cho WebSocket operation | Dùng WebSocket tester |
| Test phụ thuộc dữ liệu cũ | Fixture dùng chung hoặc không dọn database | Tạo dữ liệu cô lập và cleanup |
| HTTP status assertion không khớp | Giả định GraphQL error luôn ánh xạ thành một status cố định | Kiểm tra contract transport của phiên bản đang chạy |

## 19. Quy trình xây dựng test với HttpGraphQlTester

Khi thêm HTTP GraphQL integration test, hãy thực hiện theo trình tự:

1. **Chọn đúng ranh giới.** Xác định cần test HTTP transport hay chỉ GraphQL execution.
2. **Thêm dependency.** Đưa `spring-graphql-test` vào test scope và dùng version đồng bộ.
3. **Khởi động server test.** Dùng random port hoặc test web environment phù hợp.
4. **Tạo WebTestClient.** Cấu hình base URL và các HTTP headers cần thiết.
5. **Tạo HttpGraphQlTester.** Dùng `HttpGraphQlTester.create(webTestClient)`.
6. **Gửi operation.** Dùng `document(...)`, `variable(...)` và `execute()`.
7. **Kiểm tra data.** Dùng `path(...)`, `entity(...)` và `entityList(...)`.
8. **Kiểm tra errors.** Assert message, code và path khi chúng thuộc API contract.
9. **Kiểm tra HTTP riêng.** Dùng `WebTestClient` trực tiếp cho status, headers, CORS và transport.
10. **Bao phủ negative cases.** Kiểm tra validation, authentication, authorization, input binding và partial data.

## 20. Tổng kết

`HttpGraphQlTester` là công cụ kiểm thử GraphQL qua HTTP trong Spring for GraphQL. Nó được tạo từ `WebTestClient`, gửi GraphQL document và variables tới endpoint rồi cung cấp API kiểm tra response bằng `path`, `entity`, `entityList` và `errors`.

Dùng `HttpGraphQlTester` khi cần xác minh đường đi từ HTTP transport tới GraphQL resolver, bao gồm request binding, headers và security filters. Với HTTP status, response headers hoặc CORS preflight, dùng `WebTestClient` trực tiếp để kiểm tra tầng transport. Với Subscription, cần tester dành cho WebSocket. Kết hợp các loại test theo đúng ranh giới giúp kiểm tra API rõ ràng, ổn định và tránh nhầm GraphQL execution với HTTP transport behavior.

