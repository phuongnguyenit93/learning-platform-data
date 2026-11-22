# WebGraphQlTester

## Mục tiêu

Sau bài học này, bạn có thể:

- Giải thích vai trò của WebGraphQlTester trong kiểm thử ứng dụng Spring for GraphQL.
- Phân biệt WebGraphQlTester với GraphQlTester, HttpGraphQlTester và các tester theo transport khác.
- Tạo WebGraphQlTester từ WebGraphQlHandler.
- Gửi query và mutation bằng document, variables và operation name.
- Kiểm tra data, field path, GraphQL errors và partial response.
- Kiểm thử web interceptor và request context ở tầng WebGraphQlHandler.
- Chọn đúng tester theo lớp cần kiểm thử và thiết kế test độc lập, dễ bảo trì.

## WebGraphQlTester là gì?

Spring for GraphQL cung cấp GraphQlTester như một API kiểm thử thống nhất cho GraphQL request và response. WebGraphQlTester là biến thể dành cho web layer: nó gửi request qua WebGraphQlHandler và nhận kết quả sau khi request đi qua chuỗi WebGraphQlInterceptor cùng GraphQL execution.

WebGraphQlTester hữu ích khi muốn kiểm tra cách các thành phần web GraphQL phối hợp với nhau mà không cần khởi động HTTP server thật. Ví dụ:

- Một query được ánh xạ tới annotated controller đúng cách.
- Variables được bind vào tham số controller.
- WebGraphQlInterceptor bổ sung metadata vào request context.
- Exception từ resolver trở thành GraphQL error.
- Một field bị lỗi nhưng các field độc lập vẫn trả partial data.

WebGraphQlTester không gửi HTTP request qua socket. Vì vậy, nó không kiểm tra HTTP routing, servlet filter chain, HTTP status, TLS, proxy hoặc WebSocket handshake. Khi cần kiểm tra những thành phần đó, hãy dùng tester phù hợp với transport, chẳng hạn HttpGraphQlTester.

## Vị trí của WebGraphQlTester trong hệ thống tester

GraphQlTester là contract chung cho các loại tester. Mỗi implementation chọn một lớp xử lý khác nhau:

| Tester | Lớp được kiểm thử | Khi nên dùng |
| --- | --- | --- |
| ExecutionGraphQlServiceTester | GraphQlService và GraphQL execution | Kiểm tra resolver, schema và execution mà không cần web layer |
| WebGraphQlTester | WebGraphQlHandler và WebGraphQlInterceptor | Kiểm tra web GraphQL layer, request context và interceptor |
| HttpGraphQlTester | HTTP GraphQL endpoint qua WebTestClient | Kiểm tra HTTP request/response và tích hợp web server |
| WebSocketGraphQlTester | WebSocket GraphQL transport | Kiểm tra subscription và vòng đời connection |
| RSocketGraphQlTester | RSocket transport | Kiểm tra request và streaming qua RSocket |

Chọn tester theo ranh giới cần xác minh. Nếu test chỉ cần kiểm tra một service method, không cần tạo GraphQL tester. Nếu cần xác minh controller mapping và interceptor, WebGraphQlTester phù hợp. Nếu cần xác minh request thực sự đi qua HTTP stack, WebGraphQlTester chưa đủ.

## Thêm dependency kiểm thử

Với Gradle, thêm Spring GraphQL Test và Spring Boot Test vào test configuration:

~~~groovy
dependencies {
    testImplementation 'org.springframework.graphql:spring-graphql-test'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Spring Boot dependency management nên quản lý phiên bản tương thích cho các artifact Spring. Không tự thêm phiên bản Spring GraphQL khác với phiên bản mà Spring Boot BOM đang quản lý nếu không có lý do cụ thể.

spring-graphql-test cung cấp GraphQlTester và các implementation test như WebGraphQlTester. spring-boot-starter-test cung cấp JUnit Jupiter, AssertJ và các công cụ kiểm thử Spring Boot thường dùng.

## Tạo WebGraphQlTester từ WebGraphQlHandler

WebGraphQlHandler là entry point của web GraphQL layer. Nó kết hợp GraphQL execution với các WebGraphQlInterceptor đã được cấu hình.

Trong Spring Boot integration test, có thể inject handler do application context tạo:

~~~java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.graphql.server.WebGraphQlHandler;
import org.springframework.graphql.test.tester.WebGraphQlTester;

@SpringBootTest
class BookWebGraphQlTests {

    @Autowired
    WebGraphQlHandler handler;

    WebGraphQlTester graphQlTester;

    @BeforeEach
    void setUp() {
        graphQlTester = WebGraphQlTester.builder(handler).build();
    }
}
~~~

WebGraphQlTester.builder(handler) tạo tester sử dụng chính handler trong application context. Vì vậy, test đi qua web GraphQL handler và interceptor chain đã đăng ký cho handler đó.

Nếu ứng dụng tự cấu hình WebGraphQlHandler, hãy bảo đảm test sử dụng đúng bean đã được cấu hình. Nếu tự tạo một handler mới trong test, các interceptor hoặc customizer của production có thể không được đưa vào; khi đó test không còn đại diện cho web layer thật.

Có thể tạo tester một lần cho mỗi test class nếu handler và cấu hình là bất biến. Nếu mỗi test cần cấu hình request khác nhau, dùng mutate() hoặc tạo tester riêng theo builder thay vì thay đổi state dùng chung giữa các test.

## Gửi query và kiểm tra response

WebGraphQlTester sử dụng cùng fluent API với GraphQlTester. Bắt đầu bằng document, truyền variables rồi gọi execute():

~~~java
@Test
void findsBookById() {
    graphQlTester.document("""
            query BookById($id: ID!) {
                bookById(id: $id) {
                    id
                    title
                }
            }
            """)
            .variable("id", "book-101")
            .execute()
            .errors()
            .verify();
}
~~~

Ví dụ trên chỉ xác minh operation không có GraphQL errors. Để kiểm tra dữ liệu, giữ response rồi truy cập field path:

~~~java
@Test
void returnsBookTitle() {
    graphQlTester.document("""
            query BookById($id: ID!) {
                bookById(id: $id) {
                    id
                    title
                }
            }
            """)
            .variable("id", "book-101")
            .execute()
            .path("bookById.title")
            .entity(String.class)
            .isEqualTo("Spring for GraphQL");
}
~~~

path() nhận đường dẫn tương đối với phần data của GraphQL response. entity(String.class) chuyển giá trị tại path thành kiểu Java và cho phép kiểm tra kết quả bằng assertion.

Có thể kiểm tra object đầy đủ:

~~~java
Book book = graphQlTester.document("""
        query BookById($id: ID!) {
            bookById(id: $id) {
                id
                title
            }
        }
        """)
        .variable("id", "book-101")
        .execute()
        .path("bookById")
        .entity(Book.class)
        .get();

assertThat(book.id()).isEqualTo("book-101");
assertThat(book.title()).isEqualTo("Spring for GraphQL");
~~~

Khi test một collection, dùng entityList():

~~~java
graphQlTester.document("""
        query {
            recentBooks(first: 2) {
                id
                title
            }
        }
        """)
        .execute()
        .path("recentBooks")
        .entityList(Book.class)
        .hasSize(2);
~~~

Test nên xác minh các giá trị có ý nghĩa với hành vi cần bảo vệ. Không cần assert mọi field trong response nếu thay đổi của field đó không ảnh hưởng mục tiêu test.

## Truyền variables và chọn operation

Có thể truyền variables riêng lẻ:

~~~java
graphQlTester.document("""
        query SearchBooks($keyword: String!, $first: Int!) {
            searchBooks(keyword: $keyword, first: $first) {
                id
                title
            }
        }
        """)
        .variable("keyword", "Spring")
        .variable("first", 5)
        .execute()
        .path("searchBooks")
        .entityList(Book.class)
        .hasSize(5);
~~~

Hoặc truyền một map:

~~~java
Map<String, Object> variables = Map.of(
        "keyword", "Spring",
        "first", 5);

graphQlTester.document(searchBooksDocument)
        .variables(variables)
        .execute()
        .path("searchBooks")
        .entityList(Book.class)
        .hasSize(5);
~~~

Nếu một document chứa nhiều operation, chỉ rõ operation cần chạy:

~~~java
graphQlTester.document(multiOperationDocument)
        .operationName("RecentBooks")
        .variable("first", 5)
        .execute()
        .path("recentBooks")
        .entityList(Book.class)
        .hasSize(5);
~~~

Tên variable phải khớp với document và không có ký tự $ ở đầu. operationName() chọn operation trong document; path() chọn field trong response. Hai thao tác phục vụ hai giai đoạn khác nhau.

## Kiểm thử Mutation

WebGraphQlTester có thể kiểm tra mutation giống query:

~~~java
@Test
void createsBook() {
    Map<String, Object> input = Map.of(
            "title", "Spring for GraphQL",
            "authorId", "author-12");

    graphQlTester.document("""
            mutation CreateBook($input: CreateBookInput!) {
                createBook(input: $input) {
                    id
                    title
                }
            }
            """)
            .variable("input", input)
            .execute()
            .path("createBook.title")
            .entity(String.class)
            .isEqualTo("Spring for GraphQL");
}
~~~

Mutation có side effect nên cần quản lý dữ liệu test. Có thể dùng database test, transaction rollback nếu phù hợp với đường thực thi, hoặc fixture riêng cho từng test. Không để test phụ thuộc thứ tự chạy hay dữ liệu được tạo bởi test khác.

Nếu mục tiêu là xác minh mutation gọi đúng service, có thể dùng mock hoặc spy cho service. Tuy nhiên, một test chỉ verify mock invocation không chứng minh database, transaction hoặc GraphQL response hoạt động đúng; hãy chọn mức test phù hợp với rủi ro cần kiểm tra.

## Kiểm tra GraphQL errors

GraphQlTester mặc định giúp test dễ đọc bằng cách yêu cầu kiểm tra errors. Nếu response không được phép có lỗi, gọi:

~~~java
response.errors().verify();
~~~

Khi test đang kiểm tra một lỗi có chủ đích, hãy lấy danh sách errors và xác minh message, path hoặc extensions:

~~~java
@Test
void reportsBookNotFound() {
    GraphQlTester.Response response = graphQlTester.document("""
            query BookById($id: ID!) {
                bookById(id: $id) {
                    id
                    title
                }
            }
            """)
            .variable("id", "missing-book")
            .execute();

    response.errors().satisfy(errors -> {
        assertThat(errors).hasSize(1);
        assertThat(errors.get(0).getMessage())
                .contains("Không tìm thấy sách");
        assertThat(errors.get(0).getPath())
                .containsExactly("bookById");
    });
}
~~~

Đường dẫn error là response path, có thể chứa alias và index của list. Vì vậy, nếu operation dùng alias, assertion cần kiểm tra path theo tên alias trong response thay vì tên field gốc của schema.

Nếu ứng dụng có error contract trong extensions, kiểm tra mã ổn định thay vì chỉ kiểm tra message:

~~~java
response.errors().satisfy(errors -> {
    assertThat(errors).hasSize(1);
    assertThat(errors.get(0).getExtensions())
            .containsEntry("code", "BOOK_NOT_FOUND");
});
~~~

Không nên assert toàn bộ nội dung message nếu message có thể được bản địa hóa hoặc biên tập. Error code và path thường là contract ổn định hơn.

## Kiểm tra partial data

GraphQL execution có thể trả một phần data cùng errors. Ví dụ field title đọc được nhưng internalNotes bị từ chối:

~~~graphql
query {
  bookById(id: "book-101") {
    title
    internalNotes
  }
}
~~~

Test có thể xác minh cả dữ liệu và lỗi:

~~~java
@Test
void keepsPublicFieldWhenInternalFieldIsForbidden() {
    GraphQlTester.Response response = graphQlTester.document("""
            query {
                bookById(id: "book-101") {
                    title
                    internalNotes
                }
            }
            """)
            .execute();

    response.path("bookById.title")
            .entity(String.class)
            .isEqualTo("Spring for GraphQL");

    response.errors().satisfy(errors -> {
        assertThat(errors).hasSize(1);
        assertThat(errors.get(0).getPath())
                .containsExactly("bookById", "internalNotes");
    });
}
~~~

Khi test partial data, không gọi errors().verify() vì test đang mong đợi một lỗi. Thay vào đó, xác minh cả field data còn hợp lệ và error path cụ thể.

Nullability trong SDL ảnh hưởng kết quả. Nếu field bị lỗi là non-null, null có thể lan truyền lên parent hoặc root. Test nên kiểm tra đúng contract nullability thay vì mặc định chỉ field con trở thành null.

## Kiểm thử WebGraphQlInterceptor

WebGraphQlTester gửi request qua WebGraphQlHandler nên có thể kiểm tra các WebGraphQlInterceptor đã được đăng ký trên handler. Ví dụ một interceptor thêm correlation ID vào GraphQLContext:

~~~java
@Component
public class CorrelationIdInterceptor implements WebGraphQlInterceptor {

    @Override
    public Mono<WebGraphQlResponse> intercept(
            WebGraphQlRequest request,
            Chain chain) {

        request.configureExecutionInput((input, builder) ->
                builder.graphQLContext(context ->
                        context.put("correlationId", "test-correlation-id"))
                        .build());

        return chain.next(request);
    }
}
~~~

Resolver có thể đọc context:

~~~java
@QueryMapping
public String currentCorrelationId(
        @ContextValue("correlationId") String correlationId) {
    return correlationId;
}
~~~

Test qua handler:

~~~java
@Test
void interceptorAddsCorrelationId() {
    graphQlTester.document("""
            query {
                currentCorrelationId
            }
            """)
            .execute()
            .path("currentCorrelationId")
            .entity(String.class)
            .isEqualTo("test-correlation-id");
}
~~~

Ví dụ dùng correlation ID cố định để test dễ lặp lại. Trong ứng dụng thật, interceptor có thể lấy ID từ request header hoặc tạo ID mới. Nếu cần xác minh header thực sự được truyền từ HTTP request, hãy dùng HttpGraphQlTester qua WebTestClient; WebGraphQlTester chỉ kiểm tra handler layer và các request customizer mà nó cung cấp.

Khi tạo tester từ một handler tự dựng, phải bảo đảm handler đó có interceptor cần test. Nếu không, test có thể pass trong khi application handler thực tế không được cấu hình interceptor như mong đợi.

## Kiểm thử validation và authorization

WebGraphQlTester hữu ích để xác minh lỗi do annotated controller và method security tạo ra, miễn là test cung cấp security context phù hợp với cấu hình ứng dụng.

Với validation:

- Gửi input không hợp lệ.
- Xác minh mutation trả GraphQL error theo error contract.
- Xác minh service không được gọi nếu validation phải chặn trước controller.

Với authorization:

- Kiểm tra principal có authority phù hợp.
- Kiểm tra principal thiếu authority bị từ chối.
- Kiểm tra nested field bị từ chối trong khi field công khai vẫn có dữ liệu.
- Kiểm tra tenant hoặc owner khác không thể đọc dữ liệu.

WebGraphQlTester không tự tạo authentication cho test. Cách cung cấp security context phụ thuộc cách ứng dụng cấu hình Spring Security và web handler. Nếu cần xác minh security filter chain, authentication từ HTTP header hoặc session/cookie, hãy test qua HTTP transport với WebTestClient và Spring Security test support.

## Tùy chỉnh tester và request

GraphQlTester hỗ trợ tạo tester mới từ tester hiện tại thông qua mutate(). Điều này hữu ích khi muốn giữ cấu hình chung nhưng thay đổi cấu hình riêng cho một nhóm test.

Ví dụ minh họa:

~~~java
WebGraphQlTester adminTester = graphQlTester.mutate()
        .build();
~~~

Đoạn code trên tạo tester mới từ cấu hình hiện có. Authentication không tự thay đổi chỉ vì tạo tester mới; cần thiết lập security context theo cơ chế test của ứng dụng.

Nếu test cần request-specific context hoặc metadata, hãy dùng khả năng cấu hình request của WebGraphQlTester builder theo API của phiên bản Spring for GraphQL đang dùng. Tránh lưu trạng thái của một test trong singleton interceptor hoặc mutable field dùng chung giữa nhiều request.

## Phân biệt WebGraphQlTester và HttpGraphQlTester

Hai tester thường bị nhầm vì đều liên quan tới web:

| Tiêu chí | WebGraphQlTester | HttpGraphQlTester |
| --- | --- | --- |
| Đầu vào | WebGraphQlHandler | WebTestClient |
| HTTP server thật | Không cần | Có thể dùng server đang chạy hoặc mock web server |
| WebGraphQlInterceptor | Có | Có, qua web handler |
| HTTP routing/filter | Không kiểm tra | Có thể kiểm tra |
| HTTP status và headers | Không phải mục tiêu | Có thể kiểm tra qua WebTestClient |
| TLS, proxy, network | Không kiểm tra | Chỉ kiểm tra khi test setup có các thành phần đó |
| Phù hợp nhất | Web GraphQL handler và interceptor | HTTP GraphQL endpoint |

Nếu muốn test endpoint qua HTTP với Spring Boot:

~~~java
HttpGraphQlTester tester =
        HttpGraphQlTester.create(webTestClient);
~~~

WebTestClient có thể được cấu hình để kết nối tới application context hoặc server đang chạy. Đây là test khác ranh giới với WebGraphQlTester và nên được đặt tên rõ trong test suite.

## Chiến lược tổ chức test

Một test suite GraphQL dễ bảo trì thường chia theo ranh giới:

1. Unit test: kiểm tra business service, mapper và policy không cần GraphQL.
2. Execution test: dùng ExecutionGraphQlServiceTester khi cần kiểm tra schema và resolver.
3. Web layer test: dùng WebGraphQlTester để kiểm tra handler, interceptor và context propagation.
4. HTTP integration test: dùng HttpGraphQlTester để kiểm tra endpoint và HTTP integration.
5. Streaming test: dùng WebSocketGraphQlTester hoặc RSocketGraphQlTester cho subscription.

Không cần dùng WebGraphQlTester cho mọi test. Chọn tester nhẹ nhất có thể chứng minh hành vi cần thiết; bổ sung integration test ở ranh giới ngoài khi có rủi ro về transport, security filter hoặc serialization.

## Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Không tạo được WebGraphQlTester | Chưa có WebGraphQlHandler hoặc spring-graphql-test | Kiểm tra application context và test dependency |
| Interceptor không chạy trong test | Tester dùng handler không chứa interceptor | Inject handler production hoặc cấu hình interceptor vào handler test |
| Test không thấy HTTP header | WebGraphQlTester không kiểm tra HTTP request thật | Dùng HttpGraphQlTester và WebTestClient |
| Assertion báo còn GraphQL errors | Test không xử lý errors hoặc response có lỗi ngoài dự kiến | Gọi errors().verify() cho success case hoặc assert errors cụ thể |
| Không lấy được field path | Path sai, alias khác tên field hoặc field null do error | Kiểm tra response data và error path |
| Test partial data thất bại | Gọi errors().verify() trong test mong đợi lỗi | Assert data và errors riêng |
| Security test luôn anonymous | Chưa thiết lập security context hoặc test sai transport layer | Dùng Spring Security test support phù hợp |
| Test mutation phụ thuộc thứ tự | Dùng chung database state | Dùng fixture, cleanup hoặc transaction isolation |
| Test handler pass nhưng HTTP endpoint fail | Chưa kiểm tra filter, routing hoặc codec | Bổ sung HttpGraphQlTester integration test |
| Test chỉ kiểm tra mock service | Chưa xác minh schema, binding hoặc response | Thêm test qua WebGraphQlTester hoặc tester phù hợp |

## Thực hành tổng hợp

Xây dựng test suite cho API thư viện:

1. Thêm spring-graphql-test và spring-boot-starter-test.
2. Inject WebGraphQlHandler vào test class.
3. Tạo WebGraphQlTester trong @BeforeEach.
4. Viết query BookById, truyền variable id và kiểm tra title.
5. Viết mutation CreateBook với input object và kiểm tra response.
6. Gửi ID không tồn tại và xác minh GraphQL error message, path hoặc extensions code.
7. Tạo query lấy cả title và internalNotes; xác minh partial data khi internalNotes bị từ chối.
8. Đăng ký một WebGraphQlInterceptor thêm correlation ID và kiểm tra resolver đọc được context.
9. Viết test validation và xác minh service không được gọi khi input sai.
10. Bổ sung một HttpGraphQlTester test nếu cần kiểm tra HTTP headers, status hoặc security filter chain.

Sau khi hoàn thành, hãy giải thích vì sao WebGraphQlTester không thay thế HttpGraphQlTester, vì sao cần assert cả data và errors trong partial response, và khi nào nên test interceptor qua handler.

## Ghi nhớ

WebGraphQlTester kiểm thử web GraphQL layer bằng cách gửi request qua WebGraphQlHandler. Nó phù hợp để kiểm tra annotated controller, WebGraphQlInterceptor, variables, field path, errors và partial data mà không cần HTTP server thật. Dùng document(), variable(), execute(), path() và errors() để xây dựng assertion rõ ràng. Với response thành công, xác minh không có errors; với lỗi có chủ đích, kiểm tra path và extensions thay vì chỉ dựa vào message. WebGraphQlTester không kiểm tra HTTP routing, filter chain, status hoặc network; hãy dùng HttpGraphQlTester qua WebTestClient cho các yêu cầu đó. Chia test theo ranh giới giúp bộ kiểm thử nhanh, dễ hiểu và phát hiện đúng loại lỗi.

## Tài liệu tham khảo

- [Spring for GraphQL – Testing](https://docs.spring.io/spring-graphql/reference/testing.html)
- [Spring for GraphQL – GraphQlTester API](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/test/tester/GraphQlTester.html)
- [Spring for GraphQL – WebGraphQlTester API](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/test/tester/WebGraphQlTester.html)
- [Spring Boot – Testing](https://docs.spring.io/spring-boot/reference/testing/index.html)
