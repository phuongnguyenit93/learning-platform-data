# WebTestClient với GraphQL

GraphQL endpoint trong Spring for GraphQL thường được expose qua HTTP tại đường dẫn /graphql. Khi kiểm thử endpoint này, cần xác minh cả nội dung GraphQL lẫn hành vi HTTP bao quanh nó: method, URL, request headers, content type, status code, response headers và JSON body.

WebTestClient là HTTP client do Spring cung cấp để kiểm thử web endpoint. Nó có thể gửi request tới ứng dụng WebFlux trong môi trường mock, đi qua MockMvc với ứng dụng Spring MVC, hoặc gọi một server đang chạy thật. Với GraphQL, có thể dùng WebTestClient trực tiếp để kiểm tra HTTP transport hoặc kết hợp nó với HttpGraphQlTester để có các assertion chuyên biệt cho GraphQL.

## Vì sao cần kiểm thử ở tầng HTTP?

Kiểm thử resolver trực tiếp giúp xác minh logic GraphQL, nhưng không chứng minh HTTP endpoint đã được cấu hình đúng. Một request có thể chạy tốt trong ExecutionGraphQlServiceTester nhưng vẫn thất bại khi đi qua HTTP do sai path, content type, security filter, CORS hoặc JSON codec.

WebTestClient giúp kiểm tra các phần sau:

- GraphQL endpoint nhận đúng HTTP method và URL.
- Request body chứa query, operationName, variables và extensions được bind đúng.
- Content-Type và Accept được xử lý đúng.
- HTTP status phản ánh đúng lỗi transport hoặc lỗi giao thức.
- GraphQL response có data và errors đúng cấu trúc.
- Security, CORS, cookie và custom response headers hoạt động qua web stack.
- Ứng dụng xử lý request trong mock web environment và server thật.

## WebTestClient và HttpGraphQlTester

HttpGraphQlTester sử dụng WebTestClient ở bên dưới. Hai công cụ phục vụ hai góc nhìn:

| Công cụ | Phù hợp để kiểm tra |
| --- | --- |
| WebTestClient | HTTP method, path, headers, status, content type, JSON body và hành vi web stack |
| HttpGraphQlTester | GraphQL document, variables, operationName, data paths, GraphQL errors và typed entity |
| ExecutionGraphQlServiceTester | GraphQL execution trực tiếp, không đi qua HTTP transport |
| WebGraphQlTester | WebGraphQlHandler và WebGraphQlInterceptor chain với mock request |

Nếu test cần xác minh endpoint HTTP thật sự nhận POST /graphql và trả header/status đúng, hãy dùng WebTestClient. Nếu mục tiêu là xác minh field, nested data hoặc GraphQL errors, HttpGraphQlTester giúp test ngắn gọn và dễ đọc hơn.

Hai cách có thể dùng trong cùng một test suite. Không cần viết lại toàn bộ assertion GraphQL bằng JSONPath nếu HttpGraphQlTester đã đáp ứng mục đích.

## Dependency kiểm thử

Để dùng GraphQlTester và HttpGraphQlTester, thêm module kiểm thử Spring for GraphQL:

~~~kotlin
dependencies {
    testImplementation("org.springframework.graphql:spring-graphql-test")
}
~~~

WebTestClient thuộc hệ sinh thái Spring WebFlux/Spring Test. Nếu ứng dụng đã có WebFlux trên classpath, thường đã có các kiểu cần thiết. Với ứng dụng Spring MVC, có thể dùng MockMvcWebTestClient để chạy WebTestClient trên MockMvc. Với test gọi server thật, cần có HTTP connector phù hợp và server được khởi động.

Trong Spring Boot, các dependency test có thể được cung cấp qua starter hoặc test modules tùy phiên bản Boot và web stack. Dùng dependency management của Spring Boot để đồng bộ version; không tự đặt một version Spring GraphQL test khác với version Spring GraphQL đang dùng.

## GraphQL HTTP request có cấu trúc gì?

Theo HTTP transport mặc định của Spring for GraphQL, endpoint nhận POST với Content-Type application/json. Body là một JSON object có thể chứa:

| Property | Ý nghĩa |
| --- | --- |
| query | GraphQL document |
| operationName | Tên operation cần chạy nếu document có nhiều operation |
| variables | Map các biến đầu vào của operation |
| extensions | Metadata mở rộng, ví dụ persisted query nếu ứng dụng hỗ trợ |

Ví dụ request:

~~~json
{
  "operationName": "BookById",
  "query": "query BookById($id: ID!) { book(id: $id) { id title } }",
  "variables": {
    "id": "book-42"
  }
}
~~~

Trong ví dụ tiếp theo, giả sử ứng dụng có GraphQL schema:

~~~graphql
type Query {
  book(id: ID!): Book
}

type Book {
  id: ID!
  title: String!
}
~~~

## Gửi GraphQL POST bằng WebTestClient

Test trực tiếp endpoint HTTP bằng cách tạo payload JSON rồi gửi POST:

~~~java
import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webtestclient.autoconfigure.AutoConfigureWebTestClient;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class GraphQlHttpEndpointTests {

    @Autowired
    private WebTestClient webTestClient;

    @Test
    void shouldReturnBookForValidQuery() {
        Map<String, Object> request = Map.of(
                "operationName", "BookById",
                "query", """
                        query BookById($id: ID!) {
                            book(id: $id) {
                                id
                                title
                            }
                        }
                        """,
                "variables", Map.of("id", "book-42"));

        webTestClient.post()
                .uri("/graphql")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.APPLICATION_JSON)
                .bodyValue(request)
                .exchange()
                .expectStatus().isOk()
                .expectHeader()
                    .contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
                .expectBody()
                    .jsonPath("$.data.book.id").isEqualTo("book-42")
                    .jsonPath("$.data.book.title").isEqualTo("Spring GraphQL");
    }
}
~~~

Các điểm cần chú ý:

1. post() chọn HTTP POST.
2. uri("/graphql") trỏ tới GraphQL endpoint; nếu ứng dụng đổi spring.graphql.path, test phải dùng path tương ứng.
3. contentType(APPLICATION_JSON) mô tả định dạng request body.
4. accept(APPLICATION_JSON) chọn định dạng response tương thích cũ.
5. bodyValue(request) gửi map được serialize thành JSON.
6. exchange() thực thi request; các lệnh expect... xác minh response.

JSONPath trong expectBody() trỏ vào toàn bộ HTTP response body, vì vậy phải bắt đầu bằng $.data hoặc $.errors. Điều này khác với GraphQlTester.path(), nơi path mặc định đã tương đối với phần data.

## Cấu hình WebTestClient cho từng môi trường

WebTestClient có thể gắn vào nhiều loại server. Chọn cách setup theo mục tiêu test.

### WebFlux với ApplicationContext mock

Với ứng dụng Spring WebFlux, có thể bind client trực tiếp vào ApplicationContext mà không cần mở port:

~~~java
WebTestClient webTestClient =
        WebTestClient.bindToApplicationContext(context)
                .configureClient()
                .build();
~~~

Sau đó gửi request tới /graphql như ví dụ trước. Cách này đi qua web infrastructure của WebFlux trong môi trường test, phù hợp để kiểm tra route và filter mà không khởi động server thật.

Nếu dùng Spring Boot, @SpringBootTest kết hợp @AutoConfigureWebTestClient có thể cung cấp WebTestClient được cấu hình sẵn cho mock web environment. @WebFluxTest cũng tự cấu hình WebTestClient, nhưng slice này chỉ load một phần bean; cần import các cấu hình hoặc thành phần GraphQL cần thiết nếu muốn kiểm tra GraphQL endpoint.

Import của AutoConfigureWebTestClient thay đổi theo dòng Spring Boot:

- Spring Boot 4: org.springframework.boot.webtestclient.autoconfigure.AutoConfigureWebTestClient.
- Spring Boot 3: org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient.

Ở Spring Boot 3, auto-configured WebTestClient chủ yếu dành cho ứng dụng WebFlux. Với ứng dụng Spring MVC, dùng MockMvcWebTestClient hoặc WebTestClient.bindToServer() khi cần gọi server thật.

### Spring MVC với MockMvcWebTestClient

Spring MVC dùng Servlet stack. Để giữ API kiểm thử của WebTestClient mà vẫn chạy trên MockMvc, dùng MockMvcWebTestClient:

~~~java
import org.springframework.test.web.servlet.client.MockMvcWebTestClient;
import org.springframework.test.web.reactive.server.WebTestClient;

WebTestClient webTestClient =
        MockMvcWebTestClient.bindToApplicationContext(context)
                .configureClient()
                .build();
~~~

Client vẫn gửi POST tới /graphql và có thể dùng các assertion của WebTestClient. Cách này kiểm tra MVC handler, filter và interceptor mà không cần mở cổng TCP.

### Gọi server đang chạy thật

Khi cần kiểm tra embedded server, HTTP connector, port mapping hoặc một số hành vi không có trong mock environment, bind client tới server:

~~~java
WebTestClient webTestClient =
        WebTestClient.bindToServer()
                .baseUrl("http://localhost:8080")
                .build();
~~~

Request vẫn dùng uri("/graphql"). Trong test suite, nên dùng port ngẫu nhiên để tránh xung đột với ứng dụng đang chạy trên máy:

~~~java
@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class GraphQlLiveHttpTests {

    @Autowired
    private WebTestClient webTestClient;

    // Test methods use webTestClient.post().uri("/graphql") ...
}
~~~

Với server thật, test bao gồm network stack và embedded server. Đổi lại, test chạy chậm hơn và cần quản lý dữ liệu test, port, timeout cùng trạng thái ứng dụng.

## Kiểm tra HTTP status và GraphQL errors

Một trong những điểm dễ nhầm nhất khi test GraphQL là HTTP status không đại diện trực tiếp cho việc resolver thành công hay thất bại.

Spring for GraphQL xử lý theo hai giai đoạn:

1. Lỗi ở tầng HTTP hoặc request transport, chẳng hạn server không khả dụng, thiếu thông tin xác thực, JSON không hợp lệ hoặc content type không được hỗ trợ, có thể tạo HTTP 4xx/5xx.
2. Khi GraphQL request đã được chấp nhận và thực thi, lỗi từ resolver được đưa vào mảng errors của GraphQL response. HTTP status thường vẫn là 200 OK.

Ví dụ resolver phát sinh lỗi nghiệp vụ:

~~~json
{
  "data": {
    "book": null
  },
  "errors": [
    {
      "message": "Không tìm thấy sách",
      "path": ["book"]
    }
  ]
}
~~~

Test phải xác minh cả status lẫn body:

~~~java
webTestClient.post()
        .uri("/graphql")
        .contentType(MediaType.APPLICATION_JSON)
        .accept(MediaType.APPLICATION_JSON)
        .bodyValue(Map.of(
                "query",
                "{ book(id: \"missing\") { id title } }"))
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .jsonPath("$.data.book").isEqualTo(null)
        .jsonPath("$.errors[0].message")
            .isEqualTo("Không tìm thấy sách")
        .jsonPath("$.errors[0].path[0]").isEqualTo("book");
~~~

Không chỉ viết expectStatus().isOk() rồi kết luận test thành công. Một GraphQL response có thể trả HTTP 200 nhưng chứa lỗi trong errors.

## Content negotiation và GraphQL response media type

Spring for GraphQL hỗ trợ hai kiểu Accept phổ biến:

| Accept | Hành vi |
| --- | --- |
| application/json | Chế độ tương thích cũ; các lỗi parse hoặc validation GraphQL vẫn có thể được trả với HTTP 200 |
| application/graphql-response+json | Theo GraphQL over HTTP; lỗi parse hoặc validation có thể dùng HTTP 4xx |

Sau khi request được validate thành công, lỗi phát sinh trong quá trình thực thi resolver vẫn được trả trong phần errors và HTTP status là 200.

Ví dụ test lỗi GraphQL document trong chế độ tương thích cũ:

~~~java
webTestClient.post()
        .uri("/graphql")
        .contentType(MediaType.APPLICATION_JSON)
        .accept(MediaType.APPLICATION_JSON)
        .bodyValue(Map.of(
                "query", "{ fieldDoesNotExist }"))
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .jsonPath("$.errors").isArray();
~~~

Ví dụ test cùng loại lỗi khi client chọn GraphQL response media type:

~~~java
MediaType graphQlResponseJson =
        MediaType.parseMediaType("application/graphql-response+json");

webTestClient.post()
        .uri("/graphql")
        .contentType(MediaType.APPLICATION_JSON)
        .accept(graphQlResponseJson)
        .bodyValue(Map.of(
                "query", "{ fieldDoesNotExist }"))
        .exchange()
        .expectStatus().is4xxClientError()
        .expectBody()
        .jsonPath("$.errors").isArray();
~~~

Hai test trên chỉ khác Accept header. Khi kiểm thử API, hãy xác định media type client thực tế dùng để tránh kỳ vọng status sai. Nếu ứng dụng hỗ trợ cả hai media type, nên có test cho cả hai.

## Kiểm tra lỗi request HTTP

Ngoài lỗi GraphQL, nên xác minh endpoint phản hồi đúng khi request HTTP sai:

~~~java
import java.nio.charset.StandardCharsets;

@Test
void shouldRejectInvalidJson() {
    webTestClient.post()
            .uri("/graphql")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue("{ invalid json".getBytes(StandardCharsets.UTF_8))
            .exchange()
            .expectStatus().is4xxClientError();
}
~~~

~~~java
@Test
void shouldRejectUnsupportedContentType() {
    webTestClient.post()
            .uri("/graphql")
            .contentType(MediaType.TEXT_PLAIN)
            .bodyValue("query { book { id } }")
            .exchange()
            .expectStatus().is4xxClientError();
}
~~~

GraphQL HTTP endpoint mặc định nhận POST. GET không được bật mặc định trong Spring for GraphQL; nếu ứng dụng bật GET, handler và route predicate phải cùng cho phép method đó. GET chỉ dành cho Query vì đây là HTTP safe method; Mutation phải dùng POST.

## Dùng HttpGraphQlTester trên WebTestClient

Khi cần assertion theo GraphQL thay vì tự viết JSONPath, tạo HttpGraphQlTester từ WebTestClient:

~~~java
import org.springframework.graphql.test.tester.HttpGraphQlTester;

HttpGraphQlTester graphQlTester =
        HttpGraphQlTester.create(webTestClient);
~~~

Sau đó test query bằng GraphQL document và variables:

~~~java
graphQlTester.document("""
        query BookById($id: ID!) {
            book(id: $id) {
                id
                title
            }
        }
        """)
        .variable("id", "book-42")
        .execute()
        .path("book.id")
            .entity(String.class).isEqualTo("book-42")
        .path("book.title")
            .entity(String.class).isEqualTo("Spring GraphQL");
~~~

HttpGraphQlTester thực hiện request qua cùng WebTestClient nhưng hiểu cấu trúc GraphQL response. path() mặc định tương đối với phần data, do đó không cần viết data.book.title.

Với mutation hoặc request mà test không cần đọc field cụ thể, có thể dùng executeAndVerify() để xác minh response không có GraphQL errors:

~~~java
graphQlTester.document("""
        mutation DeleteBook($id: ID!) {
            deleteBook(id: $id)
        }
        """)
        .variable("id", "book-42")
        .executeAndVerify();
~~~

Nếu mutation trả về dữ liệu, dùng execute() và kiểm tra field như query.

## Kiểm tra GraphQL errors với HttpGraphQlTester

GraphQlTester cung cấp API để xác minh lỗi có xuất hiện, lọc lỗi đã biết hoặc kiểm tra toàn bộ danh sách:

~~~java
graphQlTester.document("""
        query BookById($id: ID!) {
            book(id: $id) {
                id
                title
            }
        }
        """)
        .variable("id", "missing")
        .execute()
        .errors()
        .expect(error ->
                error.getMessage().contains("Không tìm thấy sách"))
        .verify();
~~~

Nếu muốn kiểm tra nhiều lỗi:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

graphQlTester.document("""
        query {
            first: book(id: "missing-1") { id }
            second: book(id: "missing-2") { id }
        }
        """)
        .execute()
        .errors()
        .satisfy(errors ->
                assertThat(errors).hasSize(2));
~~~

satisfy() cho phép dùng AssertJ hoặc assertion library khác để kiểm tra danh sách ResponseError. Việc xử lý errors qua API này cũng đánh dấu chúng đã được kiểm tra, giúp test có thể tiếp tục đọc phần data nếu response có partial data.

Không lọc tất cả lỗi bằng errorFilter chỉ để test luôn xanh. Chỉ lọc lỗi được kỳ vọng và kiểm tra rõ nội dung, path hoặc extension của lỗi đó.

## Kiểm tra operationName và variables

Khi GraphQL document có nhiều operation, phải gửi đúng operationName:

~~~graphql
query BookById($id: ID!) {
  book(id: $id) {
    id
    title
  }
}

query BookCount {
  bookCount
}
~~~

Với WebTestClient, đưa operationName vào JSON request:

~~~java
Map<String, Object> request = Map.of(
        "query", document,
        "operationName", "BookCount");
~~~

Với HttpGraphQlTester, có thể dùng operationName() cùng variable():

~~~java
graphQlTester.document(document)
        .operationName("BookCount")
        .execute()
        .path("bookCount")
        .entity(Integer.class)
        .isEqualTo(12);
~~~

Kiểm thử variables riêng giúp xác minh server nhận đúng kiểu dữ liệu, giá trị null và nested input object. Tránh nối chuỗi input trực tiếp vào GraphQL document nếu mục tiêu là kiểm tra cơ chế variables.

## Tải GraphQL document từ file

Với query dài hoặc dùng fragment, lưu document trong file .graphql hoặc .gql để tránh chuỗi Java khó đọc. HttpGraphQlTester có thể sử dụng documentName() và fragmentName() với DocumentSource mặc định trong thư mục graphql-test/ trên classpath.

Ví dụ cấu trúc:

~~~text
src/test/resources/
  graphql-test/
    bookById.graphql
    bookFields.graphql
~~~

Nội dung bookById.graphql:

~~~graphql
query BookById($id: ID!) {
  book(id: $id) {
    ...bookFields
  }
}
~~~

Nội dung bookFields.graphql:

~~~graphql
fragment bookFields on Book {
  id
  title
}
~~~

Test:

~~~java
graphQlTester.documentName("bookById")
        .fragmentName("bookFields")
        .variable("id", "book-42")
        .execute()
        .path("book.title")
        .entity(String.class)
        .isEqualTo("Spring GraphQL");
~~~

Với WebTestClient raw, request body vẫn cần trường query chứa document hoàn chỉnh. Nếu dùng file, test có thể đọc file thành String rồi đặt vào payload.

## Kiểm tra headers, cookie và authentication

WebTestClient cho phép gửi header giống client thật:

~~~java
webTestClient.post()
        .uri("/graphql")
        .contentType(MediaType.APPLICATION_JSON)
        .headers(headers -> headers.setBearerAuth(accessToken))
        .bodyValue(Map.of(
                "query", "{ currentUser { id username } }"))
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .jsonPath("$.data.currentUser.username")
            .isEqualTo("alice");
~~~

Nếu dùng Basic Authentication:

~~~java
.headers(headers -> headers.setBasicAuth("alice", "password"))
~~~

Nếu ứng dụng dùng cookie session, có thể gửi cookie bằng cookie() hoặc cookies() trên request. Với Spring Security bật CSRF protection cho POST, test cần gửi CSRF token theo cơ chế test support của Spring Security; không tắt CSRF trong production chỉ để test dễ hơn.

Phân biệt hai kiểu authorization:

- HTTP security chặn request trước GraphQL, ví dụ chưa đăng nhập: test HTTP status 401 hoặc 403 theo cấu hình.
- Field-level authorization trong GraphQL: request có thể đi vào GraphQL execution và trả lỗi trong errors với HTTP 200.

Test cả hai trường hợp để xác nhận security filter và authorization tại resolver/service hoạt động đúng.

## Kiểm tra custom response headers

Nếu ứng dụng dùng WebGraphQlInterceptor để thêm correlation ID hoặc metadata vào HTTP response, WebTestClient có thể xác minh header:

~~~java
webTestClient.post()
        .uri("/graphql")
        .contentType(MediaType.APPLICATION_JSON)
        .bodyValue(Map.of("query", "{ greeting }"))
        .exchange()
        .expectStatus().isOk()
        .expectHeader().exists("X-Request-Id")
        .expectBody()
        .jsonPath("$.data.greeting").isEqualTo("Hello");
~~~

Để kiểm tra giá trị cụ thể:

~~~java
webTestClient.post()
        .uri("/graphql")
        .contentType(MediaType.APPLICATION_JSON)
        .bodyValue(Map.of("query", "{ greeting }"))
        .exchange()
        .expectHeader()
        .valueEquals("X-Request-Id", "test-request-123");
~~~

Nếu header chỉ được browser JavaScript đọc trong cross-origin request, cần kiểm tra thêm Access-Control-Expose-Headers trong response.

## Kiểm tra CORS preflight

Trình duyệt có thể gửi OPTIONS preflight trước GraphQL POST khi request cross-origin có header hoặc content type yêu cầu preflight. Có thể kiểm tra response CORS:

~~~java
import org.springframework.http.HttpHeaders;

webTestClient.options()
        .uri("/graphql")
        .header(HttpHeaders.ORIGIN, "https://app.example.com")
        .header(
                HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD,
                "POST")
        .header(
                HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS,
                "content-type,authorization")
        .exchange()
        .expectHeader()
        .valueEquals(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN,
                "https://app.example.com");
~~~

Không nhất thiết cố định status 200 hay 204 vì kết quả phụ thuộc CORS configuration và web stack. Điều quan trọng là response có các header cho phép origin, method và request headers đúng chính sách.

CORS không thay thế authentication hoặc authorization. Test cần xác minh origin lạ không được cấp quyền truy cập và credential không được bật cùng wildcard origin.

## Kiểm tra GraphQL response headers và content type

Một số ứng dụng có thể trả application/graphql-response+json. Có thể xác minh media type:

~~~java
webTestClient.post()
        .uri("/graphql")
        .contentType(MediaType.APPLICATION_JSON)
        .accept(MediaType.parseMediaType(
                "application/graphql-response+json"))
        .bodyValue(Map.of("query", "{ greeting }"))
        .exchange()
        .expectStatus().isOk()
        .expectHeader()
        .contentTypeCompatibleWith(
                MediaType.parseMediaType(
                        "application/graphql-response+json"));
~~~

Nếu ứng dụng chỉ hỗ trợ legacy application/json, hãy dùng Accept phù hợp và kiểm thử theo cấu hình thực tế. Không hard-code một response media type khi API được cấu hình content negotiation khác.

## WebTestClient và @GraphQlTest có mục đích khác nhau

@GraphQlTest của Spring Boot tập trung vào GraphQL controller và GraphQL infrastructure. Slice này không tạo HTTP transport hoặc server. Vì vậy, @GraphQlTest phù hợp để test mapping, argument binding và GraphQL execution với mock collaborator, nhưng không thể thay thế test HTTP endpoint bằng WebTestClient.

Chọn cách test:

| Mục tiêu | Cách phù hợp |
| --- | --- |
| Test resolver/controller mapping | @GraphQlTest hoặc ExecutionGraphQlServiceTester |
| Test interceptor chain của WebGraphQlHandler | WebGraphQlTester |
| Test HTTP path, method, headers, content negotiation | WebTestClient |
| Test GraphQL data/errors qua HTTP | HttpGraphQlTester trên WebTestClient |
| Test server thật, connector và port | @SpringBootTest(RANDOM_PORT) với WebTestClient |
| Test WebSocket subscription | WebSocketGraphQlTester |

Một test suite cân bằng nên có unit/slice tests cho logic GraphQL và một số integration tests qua HTTP để xác minh toàn bộ đường request.

## Timeout và kiểm soát dữ liệu test

WebTestClient gửi request reactive nhưng API assertion được thiết kế để chờ response trong giới hạn timeout. Khi GraphQL resolver gọi database hoặc service bên ngoài, hãy cấu hình timeout hợp lý để test không treo vô hạn.

Với HttpGraphQlTester, có thể cấu hình response timeout:

~~~java
import java.time.Duration;

HttpGraphQlTester tester =
        HttpGraphQlTester.builder(webTestClient.mutate())
                .responseTimeout(Duration.ofSeconds(5))
                .build();
~~~

Test data nên độc lập giữa các test:

- Seed dữ liệu có ID rõ ràng và có thể tái tạo.
- Dọn dữ liệu sau test nếu dùng database thật.
- Không phụ thuộc thứ tự chạy test.
- Với RANDOM_PORT, lưu ý client và server chạy ở thread/transaction khác nhau; transaction rollback phía test không tự rollback transaction đã chạy ở server.
- Mock external service khi mục tiêu là kiểm tra HTTP/GraphQL mapping; dùng integration test riêng khi cần xác minh database hoặc service thật.

Nếu test song song, không dùng chung dữ liệu mutable hoặc một account duy nhất cho nhiều test nếu điều đó có thể tạo race condition.

## Lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| 404 khi gửi tới GraphQL | Sai endpoint path hoặc GraphQL endpoint chưa được expose | Kiểm tra spring.graphql.path và web configuration |
| 405 khi gọi POST | Route hoặc security/proxy chỉ cho phép method khác | Kiểm tra GraphQlHttpHandler và route predicate |
| 415 Unsupported Media Type | Content-Type không phải JSON được hỗ trợ | Gửi Content-Type application/json |
| HTTP 200 nhưng test vẫn phải fail | GraphQL response chứa errors | Kiểm tra $.errors hoặc dùng HttpGraphQlTester.errors() |
| Mong 400 nhưng nhận 200 cho invalid document | Client dùng Accept application/json legacy mode | Kiểm tra Accept và dùng application/graphql-response+json nếu muốn semantics theo GraphQL over HTTP |
| JSONPath không tìm thấy data | Path đang thiếu hoặc sai phần data | WebTestClient dùng $.data...; GraphQlTester.path() tương đối với data |
| Variables không được bind | Sai tên biến, thiếu variables object hoặc sai kiểu | So sánh GraphQL declaration với key trong JSON variables |
| WebTestClient không được inject | Thiếu WebFlux test support hoặc cấu hình auto-configuration | Kiểm tra web stack và test dependencies |
| MockMvc test không chạy qua WebTestClient | Dùng bindToApplicationContext cho MVC context | Dùng MockMvcWebTestClient |
| Security test nhận 403 ngoài dự kiến | CSRF hoặc authentication filter chặn trước GraphQL | Gửi credential/CSRF token đúng chính sách |
| CORS preflight thất bại | Origin, method hoặc request header chưa được allow | Kiểm tra CORS configuration |
| Test chạy local được nhưng lỗi ở server thật | Khác biệt connector, proxy, port hoặc TLS | Thêm integration test với RANDOM_PORT và môi trường tương đương |
| Test GraphQL subscription bằng HTTP không nhận stream | Subscription cần transport streaming | Dùng WebSocketGraphQlTester hoặc transport SSE được cấu hình |

## Nguyên tắc kiểm thử WebTestClient với GraphQL

Khi kiểm thử GraphQL HTTP endpoint, hãy nhớ:

1. Gửi request đúng giao thức. Dùng POST, path GraphQL và JSON body gồm query cùng variables khi cần.
2. Xác minh cả HTTP và GraphQL. Kiểm tra status, headers, content type và data/errors.
3. Hiểu content negotiation. application/json legacy và application/graphql-response+json có semantics status khác nhau với lỗi parse/validation.
4. Chọn đúng môi trường bind. WebFlux dùng bindToApplicationContext; MVC dùng MockMvcWebTestClient; live server dùng bindToServer hoặc Boot RANDOM_PORT.
5. Dùng HttpGraphQlTester cho assertion GraphQL. WebTestClient vẫn hữu ích khi cần kiểm tra chi tiết HTTP transport.
6. Kiểm tra security và CORS. Xác minh cả HTTP filter và lỗi authorization ở field.
7. Kiểm tra headers tùy chỉnh. Correlation ID, cookie và exposed headers cần được xác minh qua response thực.
8. Giữ test data độc lập. Tránh phụ thuộc thứ tự, trạng thái dùng chung hoặc transaction rollback giả định.
9. Không dùng @GraphQlTest để thay thế transport test. Slice đó không expose HTTP endpoint.
10. Dùng WebSocketGraphQlTester cho subscription. WebTestClient HTTP thông thường không kiểm tra vòng đời WebSocket.

WebTestClient giúp kiểm thử GraphQL qua đúng HTTP boundary mà client bên ngoài sử dụng. Khi kết hợp với HttpGraphQlTester, test có thể vừa xác minh method, path, headers, content negotiation và status, vừa kiểm tra data, variables và GraphQL errors theo cấu trúc. Phân biệt lỗi HTTP với lỗi trong GraphQL response, chọn đúng mock/live server và kiểm tra security/CORS sẽ giúp phát hiện sớm lỗi cấu hình transport mà test resolver đơn lẻ không thể nhìn thấy.

## Tài liệu tham khảo

- [Spring for GraphQL - Testing và HttpGraphQlTester](https://docs.spring.io/spring-graphql/reference/testing.html)
- [Spring for GraphQL - HTTP Server Transport](https://docs.spring.io/spring-graphql/reference/transports.html)
- [Spring Boot - Auto-configured Spring GraphQL Tests](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html)
- [Spring Boot 3.5 - AutoConfigureWebTestClient package and testing](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html)
- [Spring Framework - WebTestClient](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html)
