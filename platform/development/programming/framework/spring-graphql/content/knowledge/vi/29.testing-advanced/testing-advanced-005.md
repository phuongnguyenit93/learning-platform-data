# Test WebGraphQlInterceptor

## Mục tiêu

Sau bài học này, bạn có thể:

- Giải thích vị trí của `WebGraphQlInterceptor` trong request pipeline của Spring for GraphQL.
- Phân biệt unit test interceptor với integration test qua `WebGraphQlHandler`.
- Kiểm tra interceptor có gọi tiếp `Chain.next(request)` và giữ nguyên response.
- Kiểm thử việc đọc HTTP headers và truyền metadata vào `GraphQLContext`.
- Xác minh response headers được bổ sung đúng cách.
- Dùng `WebGraphQlTester` để chạy request qua interceptor chain mà không cần mở HTTP server.
- Dùng `WebTestClient` để kiểm tra interceptor khi đi qua HTTP transport thực tế.
- Kiểm thử lỗi, thứ tự interceptor và các trường hợp request không hợp lệ.
- Kiểm soát side effect, cancellation và lỗi trong reactive pipeline.
- Xây dựng test bảo đảm interceptor không làm lộ dữ liệu nhạy cảm.

## 1. Vì sao cần kiểm thử WebGraphQlInterceptor?

`WebGraphQlInterceptor` cho phép xử lý request trước và sau khi GraphQL Java thực thi operation. Interceptor thường được dùng để đọc request metadata, bổ sung dữ liệu vào `GraphQLContext`, ghi nhận thời gian, thêm response headers hoặc chuẩn hóa một số lỗi ở tầng web GraphQL.

Một interceptor có thể ảnh hưởng đến mọi Query, Mutation và subscription đi qua web GraphQL handler. Nếu xử lý sai, nó có thể làm mất request metadata, bỏ qua bước thực thi GraphQL, thay đổi response không mong muốn hoặc làm gián đoạn reactive stream.

Kiểm thử interceptor cần xác minh các hành vi ở đúng ranh giới:

- Request được chuyển tiếp tới interceptor tiếp theo.
- Metadata được đọc và truyền vào execution input đúng cách.
- Response từ GraphQL được giữ nguyên khi interceptor chỉ quan sát.
- Response headers được bổ sung đúng khi có yêu cầu.
- Exception và cancellation được truyền qua pipeline theo đúng semantics.
- Dữ liệu nhạy cảm không bị ghi log hoặc trả về client.

Không nên chỉ kiểm tra method interceptor được gọi. Cần kiểm tra cả kết quả quan sát được ở request, execution context và response.

## 2. Vị trí của interceptor trong request pipeline

HTTP và WebSocket transports của Spring for GraphQL sử dụng chuỗi `WebGraphQlInterceptor` trước khi chuyển request tới `ExecutionGraphQlService`.

~~~mermaid
flowchart TD
    A["HTTP hoặc WebSocket request"] --> B["Web transport handler"]
    B --> C["WebGraphQlInterceptor thứ nhất"]
    C --> D["Các interceptor tiếp theo"]
    D --> E["ExecutionGraphQlService"]
    E --> F["GraphQL Java execution"]
    F --> G["WebGraphQlResponse"]
    G --> H["Interceptor xử lý response"]
    H --> I["Transport gửi response"]
~~~

Interceptor có thể thực hiện công việc trước khi gọi `chain.next(request)`, sau khi nhận response từ chain, hoặc cả hai.

Ví dụ:

~~~java
@Override
public Mono<WebGraphQlResponse> intercept(
        WebGraphQlRequest request,
        Chain chain) {

    // Xử lý request trước GraphQL execution.
    return chain.next(request)
            .doOnNext(response -> {
                // Quan sát response sau GraphQL execution.
            });
}
~~~

`chain.next(request)` chuyển request tới bước tiếp theo. Kết quả là `Mono<WebGraphQlResponse>`, vì một GraphQL request thông thường tạo một response web GraphQL.

Một interceptor có thể được kiểm thử riêng bằng mock chain. Khi cần xác minh toàn bộ interceptor chain và GraphQL execution, dùng `WebGraphQlHandler` kết hợp `WebGraphQlTester`.

## 3. Hợp đồng của WebGraphQlInterceptor

Interface có method chính:

~~~java
Mono<WebGraphQlResponse> intercept(
        WebGraphQlRequest request,
        WebGraphQlInterceptor.Chain chain);
~~~

Hai thành phần quan trọng:

| Thành phần | Trách nhiệm |
| --- | --- |
| `WebGraphQlRequest` | Cung cấp request ID, headers, URI, attributes và khả năng tùy chỉnh execution input |
| `Chain` | Chuyển request tới interceptor tiếp theo hoặc GraphQL execution |
| `WebGraphQlResponse` | Chứa GraphQL response, execution result và response headers |

Một interceptor thường cần trả về publisher từ `chain.next(request)` hoặc một publisher thay thế khi có chủ đích từ chối request trước execution.

Không gọi `subscribe()` bên trong interceptor rồi trả về một `Mono` khác. Việc tự subscribe sẽ tách công việc khỏi lifecycle mà framework quản lý, khiến lỗi và cancellation khó được truyền đúng.

Cũng không gọi `block()` trong interceptor. Hãy giữ toàn bộ xử lý theo reactive pipeline.

## 4. Chuẩn bị dependency kiểm thử

Trong Maven project, thêm `spring-graphql-test` ở test scope:

~~~xml
<dependency>
    <groupId>org.springframework.graphql</groupId>
    <artifactId>spring-graphql-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

Spring Boot dependency management thường quản lý version tương thích. Nếu dự án không dùng BOM của Spring Boot, hãy chọn version `spring-graphql-test` đồng bộ với Spring GraphQL runtime.

Các dependency kiểm thử thường dùng cùng:

- `spring-boot-starter-test` cho JUnit Jupiter, Mockito và AssertJ.
- `spring-graphql-test` cho `WebGraphQlTester`.
- `spring-test` cho `WebTestClient`.
- Reactor Test cho `StepVerifier` khi cần kiểm tra reactive publisher.

Không cần HTTP server cho unit test interceptor hoặc test chạy trực tiếp qua `WebGraphQlHandler`. Chỉ khởi động server khi cần xác minh tích hợp transport HTTP thật.

## 5. Xây dựng interceptor mẫu có thể kiểm thử

Ví dụ sau đọc `X-Request-Id`, kiểm tra định dạng, tạo ID mới nếu giá trị không hợp lệ, đưa ID vào `GraphQLContext` và trả ID trong response header.

~~~java
import java.util.UUID;
import java.util.regex.Pattern;

import org.springframework.graphql.server.WebGraphQlInterceptor;
import org.springframework.graphql.server.WebGraphQlRequest;
import org.springframework.graphql.server.WebGraphQlResponse;
import org.springframework.http.HttpHeaders;

import reactor.core.publisher.Mono;

class RequestIdInterceptor implements WebGraphQlInterceptor {

    private static final Pattern SAFE_ID =
            Pattern.compile("[A-Za-z0-9._-]{1,64}");

    @Override
    public Mono<WebGraphQlResponse> intercept(
            WebGraphQlRequest request,
            Chain chain) {

        String requestId = resolveRequestId(request.getHeaders());

        request.configureExecutionInput((input, builder) ->
                builder.graphQLContext(context ->
                        context.put("requestId", requestId)
                ).build()
        );

        return chain.next(request)
                .doOnNext(response ->
                        response.getResponseHeaders()
                                .set("X-Request-Id", requestId)
                );
    }

    private String resolveRequestId(HttpHeaders headers) {
        String supplied = headers.getFirst("X-Request-Id");

        if (supplied != null && SAFE_ID.matcher(supplied).matches()) {
            return supplied;
        }

        return UUID.randomUUID().toString();
    }
}
~~~

Ví dụ này thể hiện ba hành vi có thể kiểm thử độc lập:

1. Header đầu vào hợp lệ được giữ làm request ID.
2. Header thiếu hoặc sai định dạng được thay bằng UUID do server tạo.
3. Request ID được truyền vào `GraphQLContext` và được trả lại trong response header.

Request ID do client cung cấp chỉ là correlation metadata. Không dùng nó làm danh tính, quyền truy cập hoặc bằng chứng xác thực.

## 6. Unit test với mock request và chain

Unit test giúp cô lập interceptor khỏi GraphQL schema, resolver và web server. Dùng Mockito để tạo `WebGraphQlRequest`, `Chain` và `WebGraphQlResponse` giả.

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import org.junit.jupiter.api.Test;
import org.springframework.graphql.server.WebGraphQlInterceptor;
import org.springframework.graphql.server.WebGraphQlRequest;
import org.springframework.graphql.server.WebGraphQlResponse;
import org.springframework.http.HttpHeaders;

import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class RequestIdInterceptorTests {

    @Test
    void shouldForwardRequestAndAddResponseHeader() {
        RequestIdInterceptor interceptor = new RequestIdInterceptor();

        WebGraphQlRequest request = mock(WebGraphQlRequest.class);
        WebGraphQlInterceptor.Chain chain =
                mock(WebGraphQlInterceptor.Chain.class);
        WebGraphQlResponse response = mock(WebGraphQlResponse.class);

        HttpHeaders requestHeaders = new HttpHeaders();
        requestHeaders.set("X-Request-Id", "req-test-123");

        HttpHeaders responseHeaders = new HttpHeaders();

        when(request.getHeaders()).thenReturn(requestHeaders);
        when(response.getResponseHeaders()).thenReturn(responseHeaders);
        when(chain.next(request)).thenReturn(Mono.just(response));

        StepVerifier.create(interceptor.intercept(request, chain))
                .expectNext(response)
                .verifyComplete();

        verify(chain).next(request);
        assertThat(responseHeaders.getFirst("X-Request-Id"))
                .isEqualTo("req-test-123");
    }
}
~~~

Test này xác minh:

- Interceptor gọi `chain.next(request)`.
- Publisher hoàn tất với chính response do chain trả về.
- Response header `X-Request-Id` được thiết lập.

Mock chain trả về `Mono.just(response)` nên test tập trung vào hành vi của interceptor. Nó chưa chứng minh GraphQL execution thật nhận được request ID; phần đó cần integration test ở các mục tiếp theo.

## 7. Kiểm tra request ID không hợp lệ

Không nên chấp nhận tùy ý giá trị header do client gửi. Giá trị chứa newline hoặc chuỗi quá dài có thể gây vấn đề khi ghi log hoặc khi dùng làm response header.

Có thể kiểm tra trường hợp header không hợp lệ:

~~~java
@Test
void shouldReplaceInvalidRequestId() {
    RequestIdInterceptor interceptor = new RequestIdInterceptor();

    WebGraphQlRequest request = mock(WebGraphQlRequest.class);
    WebGraphQlInterceptor.Chain chain =
            mock(WebGraphQlInterceptor.Chain.class);
    WebGraphQlResponse response = mock(WebGraphQlResponse.class);

    HttpHeaders requestHeaders = new HttpHeaders();
    requestHeaders.set("X-Request-Id", "invalid id with spaces");

    HttpHeaders responseHeaders = new HttpHeaders();

    when(request.getHeaders()).thenReturn(requestHeaders);
    when(response.getResponseHeaders()).thenReturn(responseHeaders);
    when(chain.next(request)).thenReturn(Mono.just(response));

    StepVerifier.create(interceptor.intercept(request, chain))
            .expectNext(response)
            .verifyComplete();

    String requestId = responseHeaders.getFirst("X-Request-Id");

    assertThat(requestId).isNotNull();
    assertThat(requestId).matches(
            "[0-9a-fA-F-]{36}"
    );
}
~~~

Assertion kiểm tra interceptor tạo ID mới theo định dạng UUID. Không kiểm tra UUID bằng một giá trị cố định vì nó được sinh ngẫu nhiên.

Nên bổ sung test cho header bị thiếu và header dài hơn giới hạn. Mục tiêu là xác minh mọi đường đi đều tạo request ID an toàn trước khi dùng nó trong log hoặc response header.

## 8. Kiểm tra interceptor không làm mất response

Với interceptor chỉ bổ sung metadata, response từ `chain.next(request)` cần được giữ nguyên. Test ở mục 6 dùng `expectNext(response)` để xác minh đúng object response được chuyển tiếp.

Nếu interceptor dùng `map` để thay đổi response, hãy kiểm tra rõ phần nào được phép thay đổi:

- `data` có giữ nguyên không?
- `errors` có giữ nguyên không?
- `extensions` có bị thay đổi không?
- Response headers có chứa header mới không?
- Có vô tình xóa header đã được interceptor trước đó thêm vào không?

Ví dụ khi chỉ thêm một header, dùng `set` hoặc `add` theo semantics mong muốn. Nếu nhiều interceptor cùng thêm header có thể có nhiều giá trị, hãy xác định rõ có cần append hay thay thế.

Không tạo một `WebGraphQlResponse` mới chỉ để thêm header nếu API có phương thức cập nhật response headers phù hợp. Thay đổi tối thiểu giúp giảm nguy cơ làm mất execution result.

## 9. Kiểm tra truyền dữ liệu vào GraphQLContext

Unit test có thể xác minh method `configureExecutionInput` được gọi, nhưng integration test mới chứng minh resolver thực sự đọc được metadata.

Một resolver kiểm thử có thể trả về request ID trong context:

~~~java
import graphql.GraphQLContext;

import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.stereotype.Controller;

@Controller
class RequestMetadataController {

    @QueryMapping
    String currentRequestId(GraphQLContext context) {
        return context.get("requestId");
    }
}
~~~

Interceptor đã đặt `requestId` vào GraphQL context trước khi execution. Khi resolver chạy, giá trị đó có thể được đọc từ `GraphQLContext`.

Không truyền metadata qua static field hoặc biến mutable dùng chung. GraphQL request có thể chạy đồng thời; context phải thuộc về execution tương ứng để tránh request này nhìn thấy dữ liệu của request khác.

## 10. Dùng WebGraphQlHandler để tạo interceptor chain

`WebGraphQlHandler` là điểm kết nối giữa interceptor chain và `ExecutionGraphQlService`. Có thể tạo handler trong test bằng service của ứng dụng:

~~~java
WebGraphQlHandler handler = WebGraphQlHandler.builder(executionGraphQlService)
        .interceptor(new RequestIdInterceptor())
        .build();
~~~

Sau đó dùng `WebGraphQlTester` để gửi request qua web GraphQL layer:

~~~java
WebGraphQlTester tester = WebGraphQlTester.create(handler);
~~~

Cách này kiểm tra interceptor chain mà không cần mở HTTP server. Nó phù hợp để xác minh request headers, GraphQL context, response errors và subscription execution ở server-side web layer.

Trong ứng dụng Spring Boot, `WebGraphQlHandler` được cấu hình từ các interceptor bean của application context. Integration test có thể inject handler đã được cấu hình để kiểm tra đúng chain của ứng dụng.

Không dùng `ExecutionGraphQlServiceTester` nếu mục tiêu chính là kiểm tra `WebGraphQlInterceptor`, vì tester đó gọi execution service mà không đi qua web interceptor chain.

## 11. Integration test bằng WebGraphQlTester

Ví dụ dưới đây giả định Spring application context đã có schema, `RequestMetadataController` và `RequestIdInterceptor` được đăng ký thành bean.

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.graphql.server.WebGraphQlHandler;
import org.springframework.graphql.test.tester.WebGraphQlTester;

@SpringBootTest
class RequestIdInterceptorIntegrationTests {

    @Autowired
    WebGraphQlHandler handler;

    @Test
    void shouldPropagateRequestIdToGraphQlContext() {
        WebGraphQlTester tester = WebGraphQlTester.builder(handler)
                .headers(headers ->
                        headers.set("X-Request-Id", "req-test-123")
                )
                .build();

        tester.document("{ currentRequestId }")
                .execute()
                .path("currentRequestId")
                .entity(String.class)
                .isEqualTo("req-test-123");
    }
}
~~~

Test này đi qua `WebGraphQlHandler`, vì vậy interceptor chain được thực thi trước GraphQL resolver. Header được đưa vào request mock của tester, interceptor chuyển nó sang context và resolver trả giá trị đó.

Nếu test thất bại, kiểm tra lần lượt:

1. Interceptor có được đăng ký trong handler không?
2. Header có được gắn vào request của tester không?
3. `configureExecutionInput` có đặt đúng context key không?
4. Resolver có đọc cùng key `requestId` không?
5. Schema có khai báo field `currentRequestId` không?

## 12. Đăng ký interceptor trong Spring Boot và kiểm tra chain thật

Trong Spring Boot, có thể đăng ký interceptor dưới dạng bean:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.graphql.server.WebGraphQlInterceptor;

@Configuration
class GraphQlInterceptorConfiguration {

    @Bean
    WebGraphQlInterceptor requestIdInterceptor() {
        return new RequestIdInterceptor();
    }
}
~~~

Boot dùng interceptor bean để cấu hình web GraphQL handler. Khi test inject `WebGraphQlHandler`, test có thể xác minh interceptor đã được đưa vào chain do ứng dụng cấu hình.

Nếu ứng dụng chỉ cần sao chép một số HTTP headers vào `GraphQLContext`, Spring có sẵn `HttpRequestHeaderInterceptor`. Có thể dùng interceptor tích hợp này thay cho một implementation tự viết:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.graphql.server.support.HttpRequestHeaderInterceptor;

@Bean
HttpRequestHeaderInterceptor requestHeaderInterceptor() {
    return HttpRequestHeaderInterceptor.builder()
            .mapHeader("X-Correlation-Id")
            .build();
}
~~~

Test của interceptor tích hợp cũng có thể dùng `WebGraphQlTester` và một resolver đọc giá trị từ `GraphQLContext` hoặc `@ContextValue`.

Nếu ứng dụng có nhiều interceptor, hãy xác định thứ tự bằng cơ chế ordering đang dùng. Spring lấy interceptor bean theo `ObjectProvider.orderedStream()`, vì vậy có thể dùng `Ordered` hoặc `@Order`. Test thứ tự khi có phụ thuộc thật giữa chúng, ví dụ interceptor xác thực phải chạy trước interceptor đọc principal.

Không dựa vào thứ tự ngẫu nhiên của component scan. Nếu thứ tự ảnh hưởng kết quả, khai báo nó rõ ràng và viết test xác minh.

## 13. Kiểm tra response header qua HTTP transport

`WebGraphQlTester` chạy qua `WebGraphQlHandler` nhưng không thay thế toàn bộ HTTP transport. Nếu cần xác minh response header thực sự được gửi ra HTTP client, dùng `WebTestClient` hoặc `HttpGraphQlTester`.

Ví dụ kiểm tra header:

~~~java
import java.util.Map;

import org.springframework.http.MediaType;

webTestClient.post()
        .uri("/graphql")
        .header("X-Request-Id", "req-http-123")
        .contentType(MediaType.APPLICATION_JSON)
        .accept(MediaType.APPLICATION_JSON)
        .bodyValue(Map.of(
                "query", "{ book(id: \"book-42\") { id title } }"
        ))
        .exchange()
        .expectStatus().isOk()
        .expectHeader()
        .valueEquals("X-Request-Id", "req-http-123");
~~~

Test này cần ứng dụng đang chạy hoặc `WebTestClient` được bind vào web application context. Interceptor phải được đăng ký trong cùng application context mà test đang dùng.

Sự phân biệt quan trọng:

- `WebGraphQlTester` kiểm tra web GraphQL interceptor chain mà không cần transport server.
- `HttpGraphQlTester` kiểm tra GraphQL request/response qua HTTP.
- `WebTestClient` trực tiếp kiểm tra status, headers, cookie, content type và chi tiết HTTP transport.

Chọn tester theo ranh giới cần xác minh, không dùng một tester để suy ra hành vi của tầng khác.

## 14. Kiểm tra lỗi từ interceptor và GraphQL execution

Interceptor có thể quan sát response sau execution và xử lý lỗi nếu ứng dụng có yêu cầu. Khi test, cần phân biệt:

- Exception xảy ra trước khi `chain.next(request)` được gọi.
- Exception phát sinh trong interceptor tiếp theo.
- GraphQL errors nằm trong `WebGraphQlResponse`.
- Reactive publisher phát error signal.

GraphQL errors không nhất thiết làm `Mono<WebGraphQlResponse>` phát error. Một response hợp lệ về transport vẫn có thể chứa `errors`. Test cần kiểm tra cả `response.getErrors()` và publisher signal.

Ví dụ kiểm tra response GraphQL có lỗi bằng `WebGraphQlTester`:

~~~java
tester.document("""
        query {
            book(id: "missing-book") {
                id
            }
        }
        """)
        .execute()
        .errors()
        .expect(error ->
                error.getMessage().contains("Không tìm thấy")
        )
        .verify();
~~~

Nếu interceptor chuyển đổi error, hãy kiểm tra đúng phần được phép thay đổi và bảo đảm error path cùng mã lỗi công khai vẫn phù hợp với contract.

Không bắt mọi exception rồi trả một response rỗng. Nếu chuyển đổi lỗi, cần giữ diagnostics ở server và không đưa stack trace hoặc thông tin nội bộ vào client response.

## 15. Kiểm tra cancellation và reactive lifecycle

Interceptor nên trả publisher do chain tạo ra để framework kiểm soát subscription và cancellation.

Có thể kiểm tra việc truyền lỗi hoặc cancellation bằng mock publisher trong unit test. Ví dụ với publisher phát lỗi:

~~~java
RuntimeException failure =
        new IllegalStateException("downstream unavailable");

when(chain.next(request)).thenReturn(Mono.error(failure));

StepVerifier.create(interceptor.intercept(request, chain))
        .expectErrorMatches(error -> error == failure)
        .verify();
~~~

Test này xác minh interceptor không vô tình nuốt lỗi từ chain. Nếu interceptor có `onErrorResume`, hãy kiểm tra rõ điều kiện chuyển lỗi và loại response được tạo ra.

Với subscription operation, cancellation có thể xảy ra khi client đóng operation hoặc connection. Interceptor không nên giữ tài nguyên riêng mà không có cleanup. Nếu cần theo dõi lifecycle, gắn cleanup bằng operator như `doFinally` và kiểm thử signal `CANCEL`.

Không dùng `doOnCancel` để thay thế việc quản lý tài nguyên phức tạp nếu publisher cần giải phóng nhiều tài nguyên; hãy bảo đảm cleanup an toàn khi cancel, error và complete.

## 16. Kiểm tra metadata và bảo mật

Interceptor thường có quyền truy cập headers và request metadata. Đây là vị trí dễ vô tình làm lộ dữ liệu nếu log toàn bộ request.

Các test bảo mật nên xác minh:

- Không ghi `Authorization`, cookie, session ID hoặc token vào log.
- Request ID được giới hạn độ dài và loại bỏ ký tự điều khiển.
- Header do client gửi không được dùng làm principal hoặc tenant đã xác thực.
- Context key không ghi đè dữ liệu security context quan trọng.
- Response header không chứa token hoặc thông tin nội bộ.
- Error response không chứa stack trace hoặc exception message chưa kiểm duyệt.

Nếu interceptor cần đọc thông tin người dùng, lấy danh tính từ Spring Security context theo cơ chế phù hợp với servlet hoặc reactive stack. Không tin `username`, `role` hay `tenantId` chỉ vì chúng xuất hiện trong HTTP header tùy ý.

Test bảo mật nên kiểm tra cả dữ liệu đầu vào độc hại và response cuối cùng, thay vì chỉ kiểm tra method sanitize được gọi.

## 17. Kiểm thử nhiều interceptor và thứ tự xử lý

Khi có nhiều interceptor, mỗi interceptor có thể sửa request trước khi gọi chain và sửa response sau khi chain trả về.

Ví dụ chuỗi A rồi B có dạng lồng nhau:

~~~text
A before
  B before
    GraphQL execution
  B after
A after
~~~

Thứ tự này ảnh hưởng nếu một interceptor thêm metadata mà interceptor tiếp theo sử dụng.

Có thể dùng interceptor ghi lại thứ tự vào một danh sách test:

~~~java
import java.util.List;

import org.springframework.graphql.server.WebGraphQlInterceptor;
import org.springframework.graphql.server.WebGraphQlRequest;
import org.springframework.graphql.server.WebGraphQlResponse;

import reactor.core.publisher.Mono;

class RecordingInterceptor implements WebGraphQlInterceptor {

    private final String name;
    private final List<String> events;

    RecordingInterceptor(String name, List<String> events) {
        this.name = name;
        this.events = events;
    }

    @Override
    public Mono<WebGraphQlResponse> intercept(
            WebGraphQlRequest request,
            Chain chain) {

        events.add(name + ":before");

        return chain.next(request)
                .doOnNext(response -> events.add(name + ":after"));
    }
}
~~~

Trong test, đăng ký hai interceptor theo thứ tự dự kiến và xác minh danh sách event. Dùng `List` riêng cho từng test để tránh state dùng chung giữa các test chạy song song.

Nếu test dựa trên ordering của Spring bean, hãy cấu hình `@Order` hoặc `Ordered` rõ ràng. Không suy ra thứ tự từ tên class hoặc thứ tự file.

## 18. Test matrix cho WebGraphQlInterceptor

Một bộ test thực tế có thể được tổ chức như sau:

| Nhóm | Trường hợp | Kết quả mong đợi |
| --- | --- | --- |
| Chain | Request hợp lệ | `chain.next(request)` được gọi đúng một lần |
| Pass-through | Chain trả response thành công | Interceptor trả cùng response |
| Request metadata | Header hợp lệ | Context nhận đúng request ID |
| Header validation | Header thiếu hoặc sai định dạng | Server tạo ID mới an toàn |
| Response | Interceptor thêm header | Response có header theo contract |
| GraphQL error | Resolver trả GraphQL errors | Errors được giữ hoặc chuyển đổi đúng quy tắc |
| Reactive error | Chain phát error signal | Error được truyền tiếp nếu không có policy xử lý |
| Cancellation | Subscriber hủy publisher | Cleanup được thực hiện |
| Ordering | Có nhiều interceptor | Thứ tự before/after đúng cấu hình |
| Security | Header chứa token hoặc dữ liệu giả mạo | Không log hoặc tin cậy dữ liệu tùy tiện |
| Integration | WebGraphQlTester chạy qua handler | Resolver nhận được context do interceptor thêm |
| HTTP | Request qua endpoint thật | Response headers và status đúng contract |

Không cần nhồi tất cả trường hợp vào một test lớn. Mỗi test nên xác minh một hành vi chính để khi thất bại dễ tìm nguyên nhân.

## 19. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Interceptor không chạy trong test | Dùng `ExecutionGraphQlServiceTester` thay vì web tester | Dùng `WebGraphQlTester` với `WebGraphQlHandler` |
| `chain.next` không được gọi | Interceptor trả publisher khác hoặc kết thúc sớm | Kiểm tra nhánh xử lý trước execution |
| GraphQLContext không có request ID | Cấu hình sai execution input hoặc sai context key | Kiểm tra `configureExecutionInput` và resolver |
| Response header không xuất hiện | Chỉ kiểm tra bằng tester không quan sát HTTP headers | Dùng `WebTestClient` qua HTTP transport |
| Test không phát hiện GraphQL errors | Chỉ kiểm tra publisher hoàn tất | Assert `response.errors()` hoặc dùng tester errors API |
| Exception bị mất | Interceptor bắt lỗi nhưng không truyền tiếp hoặc không map rõ | Kiểm tra `onErrorResume` và error contract |
| Cancellation không cleanup | Tài nguyên không gắn với lifecycle publisher | Dùng cleanup cho cancel/error/complete |
| Thứ tự interceptor không ổn định | Không khai báo ordering | Dùng `@Order` hoặc `Ordered` và test chain |
| Request ID chứa newline | Tin nguyên header từ client | Validate định dạng và sinh ID mới khi sai |
| Test context bị nhiễm dữ liệu | Dùng danh sách hoặc state mutable dùng chung | Tạo fixture riêng cho từng test |
| Interceptor log token | Ghi toàn bộ headers | Allowlist metadata và redact credential |

## 20. Quy trình kiểm thử WebGraphQlInterceptor

Khi thêm hoặc thay đổi interceptor, hãy thực hiện theo trình tự:

1. **Xác định trách nhiệm.** Ghi rõ interceptor thay đổi request, execution input hay response.
2. **Viết unit test.** Mock `WebGraphQlRequest`, `Chain` và `WebGraphQlResponse` để kiểm tra pass-through.
3. **Kiểm tra metadata.** Xác minh header hợp lệ, header thiếu và header sai định dạng.
4. **Kiểm tra context.** Dùng resolver đọc `GraphQLContext` để chứng minh dữ liệu tới execution.
5. **Tạo web handler test.** Dùng `WebGraphQlHandler` và `WebGraphQlTester` để chạy qua interceptor chain.
6. **Kiểm tra errors.** Phân biệt GraphQL errors với reactive error signal.
7. **Kiểm tra lifecycle.** Xác minh cancellation và cleanup khi có tài nguyên riêng.
8. **Kiểm tra ordering.** Test thứ tự khi nhiều interceptor phụ thuộc nhau.
9. **Kiểm tra HTTP thật.** Dùng `WebTestClient` hoặc `HttpGraphQlTester` khi cần xác minh status và response headers.
10. **Rà soát bảo mật.** Đảm bảo không log token, không tin header tùy ý và không làm lộ exception nội bộ.

## 21. Tổng kết

`WebGraphQlInterceptor` nằm giữa web transport và `ExecutionGraphQlService`, cho phép xử lý request trước GraphQL execution và response sau execution. Kiểm thử interceptor cần xác minh `chain.next(request)`, request metadata, `GraphQLContext`, response headers, error propagation và reactive lifecycle.

Unit test với mock chain giúp kiểm tra logic cục bộ. `WebGraphQlTester` kết hợp `WebGraphQlHandler` kiểm tra interceptor chain ở server-side mà không cần HTTP server; `WebTestClient` hoặc `HttpGraphQlTester` phù hợp khi cần xác minh HTTP transport thật. Kết hợp các mức kiểm thử này giúp phát hiện lỗi ở đúng ranh giới và bảo đảm interceptor không làm mất response, metadata hoặc thông tin bảo mật.

