# `WebGraphQlInterceptor` trong Spring for GraphQL

`WebGraphQlInterceptor` là điểm mở rộng ở tầng transport của Spring for GraphQL, cho phép ứng dụng can thiệp vào một GraphQL request trước khi GraphQL Java thực thi và xử lý response sau khi quá trình thực thi hoàn tất. Interceptor có thể đọc thông tin HTTP request hoặc WebSocket handshake, bổ sung dữ liệu vào `ExecutionInput`, đưa metadata vào `GraphQLContext`, thêm HTTP response header và quan sát hoặc biến đổi GraphQL result.

Trong một ứng dụng Spring for GraphQL, controller như `@QueryMapping`, `@MutationMapping` và `@SchemaMapping` tập trung vào từng field. `WebGraphQlInterceptor` xử lý những mối quan tâm xuyên suốt nhiều field và operation, ví dụ correlation ID, metadata request, ghi nhận thời gian, truyền header cần thiết vào context hoặc chuẩn hóa một số lỗi ở cấp request.

## 1. Interceptor nằm ở đâu trong vòng đời GraphQL request?

Với HTTP và WebSocket, Spring for GraphQL gọi một chuỗi gồm không hoặc nhiều `WebGraphQlInterceptor`, sau đó chuyển request đến `ExecutionGraphQlService`. Service này gọi GraphQL Java để phân tích, kiểm tra và thực thi document.

```text
HTTP request / WebSocket message
              |
              v
      WebGraphQlInterceptor A
              |
              v
      WebGraphQlInterceptor B
              |
              v
       ExecutionGraphQlService
              |
              v
           GraphQL Java
              |
              v
      WebGraphQlResponse
              |
       response processing
              |
              v
        HTTP / WebSocket
```

Interceptor có thể thực hiện công việc trước và sau `chain.next(request)`:

- Trước `chain.next`: đọc header, cookie, URI, request attribute hoặc bổ sung context cho lần thực thi.
- Sau `chain.next`: đọc `WebGraphQlResponse`, ghi nhận kết quả, thêm HTTP response header hoặc biến đổi execution result khi có lý do rõ ràng.

`WebGraphQlInterceptor` áp dụng cho GraphQL qua HTTP và WebSocket. RSocket có interceptor riêng là `RSocketQlInterceptor`. Với WebSocket, `WebGraphQlInterceptor` được gọi cho từng GraphQL request trên kết nối; xử lý vòng đời kết nối và các sự kiện như connection initialization cần xem xét `WebSocketGraphQlInterceptor`.

## 2. Cấu trúc của `WebGraphQlInterceptor`

Interface có phương thức chính:

```java
Mono<WebGraphQlResponse> intercept(
    WebGraphQlRequest request,
    WebGraphQlInterceptor.Chain chain
);
```

Hai tham số có vai trò:

| Tham số | Vai trò |
|---|---|
| `WebGraphQlRequest request` | Đại diện request GraphQL ở tầng web; cung cấp GraphQL document, variables và thông tin transport như headers, cookies, URI, remote address, attributes. |
| `Chain chain` | Đại diện phần còn lại của interceptor chain và `ExecutionGraphQlService`; gọi `chain.next(request)` để chuyển request đi tiếp. |

Kết quả là `Mono<WebGraphQlResponse>` vì quá trình xử lý GraphQL có thể bất đồng bộ. Interceptor nên giữ nguyên reactive flow và không gọi `block()` hoặc tự subscribe.

Ví dụ interceptor tối thiểu:

```java
@Component
class LoggingGraphQlInterceptor implements WebGraphQlInterceptor {

    private static final Logger log =
        LoggerFactory.getLogger(LoggingGraphQlInterceptor.class);

    @Override
    public Mono<WebGraphQlResponse> intercept(
            WebGraphQlRequest request,
            Chain chain) {

        log.debug("GraphQL request id={}", request.getId());

        return chain.next(request)
            .doOnNext(response ->
                log.debug("GraphQL response id={}, errors={}",
                    request.getId(), response.getErrors().size())
            );
    }
}
```

Đây là cách đặt logging ở ranh giới request/response. Trong ứng dụng thực tế, nên dùng logger có cấu trúc và tránh ghi toàn bộ GraphQL document, variables hoặc dữ liệu nhạy cảm vào log.

## 3. Đọc thông tin từ `WebGraphQlRequest`

`WebGraphQlRequest` cung cấp các thông tin transport thường cần dùng:

| API | Thông tin |
|---|---|
| `getHeaders()` | HTTP headers của request hoặc WebSocket handshake. |
| `getCookies()` | Cookie của HTTP request hoặc WebSocket handshake. |
| `getUri()` | URI của HTTP request hoặc WebSocket handshake. |
| `getRemoteAddress()` | Địa chỉ remote nếu transport cung cấp; có thể không có. |
| `getAttributes()` | Request attributes hoặc WebSocket session attributes. |
| `getId()` | Request ID do transport gán. |
| `getLocale()` | Locale nếu request transport cung cấp. |
| `getDocument()` | GraphQL document được gửi lên. |
| `getVariables()` | Variables của operation. |
| `getOperationName()` | Tên operation nếu có. |

Ví dụ đọc header:

```java
String clientVersion = request.getHeaders().getFirst("X-Client-Version");
String language = request.getHeaders().getFirst("Accept-Language");
```

Header có thể thiếu hoặc chứa dữ liệu không hợp lệ. Hãy kiểm tra null, định dạng và độ dài trước khi sử dụng. Không mặc định tin cậy `X-Forwarded-For`, `X-User-Id` hoặc header do client tự gửi nếu proxy và lớp bảo mật chưa xác thực nguồn dữ liệu đó.

## 4. Đưa metadata vào `GraphQLContext`

Một công dụng phổ biến của interceptor là chuyển một số thông tin transport vào `GraphQLContext`, nơi data fetcher và annotated controller có thể truy cập.

`WebGraphQlRequest` kế thừa `ExecutionGraphQlRequest`, cung cấp `configureExecutionInput(...)`. Phương thức này nhận một `BiFunction<ExecutionInput, ExecutionInput.Builder, ExecutionInput>` để bổ sung cấu hình cho `ExecutionInput` trước khi GraphQL Java thực thi.

Ví dụ tạo correlation ID, đưa vào context và thêm response header cho HTTP:

```java
@Component
@Order(10)
class CorrelationIdInterceptor implements WebGraphQlInterceptor {

    @Override
    public Mono<WebGraphQlResponse> intercept(
            WebGraphQlRequest request,
            Chain chain) {

        String suppliedId = request.getHeaders().getFirst("X-Correlation-Id");
        String correlationId = isValid(suppliedId)
            ? suppliedId
            : UUID.randomUUID().toString();

        request.configureExecutionInput((input, builder) ->
            builder.graphQLContext(context ->
                context.put("correlationId", correlationId)
            ).build()
        );

        return chain.next(request).doOnNext(response -> {
            if (!(request instanceof WebSocketGraphQlRequest)) {
                response.getResponseHeaders()
                    .set("X-Correlation-Id", correlationId);
            }
        });
    }

    private boolean isValid(String value) {
        return value != null && value.matches("[A-Za-z0-9._-]{1,64}");
    }
}
```

Các import chính:

```java
import org.springframework.core.annotation.Order;
import org.springframework.graphql.server.WebGraphQlInterceptor;
import org.springframework.graphql.server.WebGraphQlRequest;
import org.springframework.graphql.server.WebGraphQlResponse;
import org.springframework.graphql.server.WebSocketGraphQlRequest;
import org.springframework.stereotype.Component;
import reactor.core.publisher.Mono;

import java.util.UUID;
```

`configureExecutionInput` bổ sung `correlationId` vào GraphQL context của execution hiện tại. `WebGraphQlResponse.getResponseHeaders()` cho phép thêm header vào HTTP response. Với WebSocket, HTTP handshake đã hoàn tất trước khi các GraphQL operation được gửi, nên response header của từng operation không thể trở thành HTTP response header mới; ví dụ bỏ qua bước này cho `WebSocketGraphQlRequest`.

Correlation ID từ client cần được xác thực định dạng và giới hạn độ dài trước khi ghi log hoặc trả lại. Nếu không có giá trị hợp lệ, server tạo ID mới. ID này phục vụ theo dõi request, không phải bằng chứng xác thực danh tính.

## 5. Đọc context trong annotated controller

Sau khi interceptor đưa dữ liệu vào `GraphQLContext`, resolver có thể nhận `GraphQLContext` làm tham số:

```java
@Controller
class ProjectController {

    @QueryMapping
    Project project(@Argument("id") String id, GraphQLContext context) {
        String correlationId = context.get("correlationId");
        return projectService.findById(id, correlationId);
    }
}
```

Có thể dùng `@ContextValue` để bind trực tiếp một giá trị context vào tham số method:

```java
@QueryMapping
Project project(
        @Argument("id") String id,
        @ContextValue("correlationId") String correlationId) {

    return projectService.findById(id, correlationId);
}
```

Chọn cách nhận context theo nhu cầu. `GraphQLContext` phù hợp khi resolver cần nhiều giá trị hoặc muốn tự kiểm soát việc đọc; `@ContextValue` tiện hơn cho một giá trị cụ thể.

Không nên đưa toàn bộ HTTP request, headers hoặc object transport lớn vào GraphQL context. Chỉ chuyển những giá trị cần thiết cho GraphQL execution, ví dụ correlation ID, tenant đã được xác minh, locale hoặc principal đã được xác thực.

## 6. Phân biệt interceptor với authentication và authorization

`WebGraphQlInterceptor` có thể đọc `Authorization` header và chuyển thông tin cần thiết vào `GraphQLContext`. Tuy nhiên, đọc header không đồng nghĩa xác thực token thành công.

Một kiến trúc thường dùng:

1. Spring Security filter chain xử lý authentication, kiểm tra token/session và tạo `Authentication` đã xác minh.
2. `WebGraphQlInterceptor` bổ sung metadata phục vụ GraphQL execution nếu cần.
3. Resolver hoặc service thực hiện authorization theo quyền và tài nguyên cụ thể.

Không nên tự giải mã một JWT chưa kiểm tra chữ ký trong interceptor rồi coi claim là danh tính đáng tin cậy. Cũng không nên dùng một header tùy ý như `X-User-Id` để quyết định quyền truy cập.

Nếu chỉ cần sao chép một số HTTP header vào GraphQL context, Spring for GraphQL cung cấp sẵn `HttpRequestHeaderInterceptor`:

```java
@Configuration
class GraphQlHeaderConfiguration {

    @Bean
    HttpRequestHeaderInterceptor headerInterceptor() {
        return HttpRequestHeaderInterceptor.builder()
            .mapHeader("X-Client-Version")
            .mapHeader("Accept-Language")
            .build();
    }
}
```

Controller có thể đọc các giá trị đã được map qua `@ContextValue`. Với metadata cần kiểm tra, chuẩn hóa hoặc lấy từ principal đã xác thực, viết interceptor riêng hoặc tích hợp với Spring Security phù hợp hơn.

## 7. Xử lý response sau `chain.next(request)`

`chain.next(request)` trả về `Mono<WebGraphQlResponse>`. Dùng các toán tử Reactor để thực hiện công việc sau khi GraphQL xử lý xong:

- `doOnNext`: ghi log, cập nhật metric hoặc thêm response header mà không thay đổi response body.
- `map`: biến đổi response và trả về một response mới.
- `onErrorResume`: xử lý lỗi phát sinh trong chính reactive chain của interceptor khi có phương án phù hợp.

Ví dụ thêm header thời gian xử lý:

```java
@Component
class ProcessingTimeInterceptor implements WebGraphQlInterceptor {

    @Override
    public Mono<WebGraphQlResponse> intercept(
            WebGraphQlRequest request,
            Chain chain) {

        long startedAt = System.nanoTime();

        return chain.next(request).doOnNext(response -> {
            long elapsedMillis =
                (System.nanoTime() - startedAt) / 1_000_000;

            if (!(request instanceof WebSocketGraphQlRequest)) {
                response.getResponseHeaders().set(
                    "X-GraphQL-Duration-Ms",
                    Long.toString(elapsedMillis)
                );
            }
        });
    }
}
```

Trong production, metric thường nên được ghi qua Micrometer/Observation thay vì chỉ trả thời gian xử lý trong response header. Header trên chủ yếu minh họa cách bổ sung thông tin vào HTTP response.

## 8. Kiểm tra và biến đổi GraphQL errors

Interceptor có thể đọc `response.getErrors()` sau khi GraphQL Java xử lý request. Điều này hữu ích với lỗi ở cấp request như parse hoặc validation error, xảy ra trước khi data fetcher được gọi.

`DataFetcherExceptionResolver` xử lý exception phát sinh từ data fetcher trong quá trình thực thi. Nó không xử lý được những request-level error xảy ra trước khi execution bắt đầu. Trong trường hợp cần quan sát hoặc chuẩn hóa những lỗi đó, `WebGraphQlInterceptor` có thể kiểm tra `WebGraphQlResponse`.

Ví dụ ghi nhận các GraphQL error có trong response, bao gồm request-level error hoặc execution error:

```java
@Component
class InvalidRequestLoggingInterceptor implements WebGraphQlInterceptor {

    private static final Logger log =
        LoggerFactory.getLogger(InvalidRequestLoggingInterceptor.class);

    @Override
    public Mono<WebGraphQlResponse> intercept(
            WebGraphQlRequest request,
            Chain chain) {

        return chain.next(request).doOnNext(response -> {
            if (!response.getErrors().isEmpty()) {
                log.debug("GraphQL request {} returned errors: {}",
                    request.getId(), response.getErrors().size());
            }
        });
    }
}
```

Nếu cần biến đổi error list, có thể dùng `response.transform(builder -> builder.errors(newErrors).build())`. Khi làm vậy, hãy giữ các metadata cần thiết như message, locations, path và extensions; không xóa lỗi chỉ để response trông như thành công. Việc thay đổi error contract ảnh hưởng trực tiếp đến client và cần được kiểm thử.

## 9. Thứ tự của nhiều interceptor

Interceptors thường được khai báo dưới dạng Spring beans. Spring for GraphQL lấy chúng theo thứ tự từ `ObjectProvider.orderedStream()`, vì vậy có thể dùng `@Order` hoặc `Ordered` để xác định thứ tự.

Ví dụ:

```java
@Component
@Order(10)
class CorrelationIdInterceptor implements WebGraphQlInterceptor {
    // ...
}

@Component
@Order(20)
class ProcessingTimeInterceptor implements WebGraphQlInterceptor {
    // ...
}
```

Với hai interceptor trên:

- Request đi qua `CorrelationIdInterceptor` trước, sau đó đến `ProcessingTimeInterceptor`.
- Response quay ngược qua các interceptor sau khi phần chain bên trong hoàn tất.

Thứ tự rất quan trọng nếu interceptor sau phụ thuộc context mà interceptor trước đã thêm. Hãy đặt interceptor tạo correlation ID hoặc tenant context trước các interceptor cần đọc những giá trị đó.

Nếu một interceptor không cần thứ tự đặc biệt, có thể để Spring dùng thứ tự mặc định. Tránh dùng cùng một giá trị order cho các interceptor có phụ thuộc thứ tự nếu không có quy tắc bổ sung.

## 10. Đăng ký interceptor trong Spring Boot

Trong ứng dụng Spring Boot dùng Spring for GraphQL Starter, khai báo interceptor như một bean là cách thông thường:

```java
@Configuration(proxyBeanMethods = false)
class GraphQlInterceptorConfiguration {

    @Bean
    @Order(10)
    WebGraphQlInterceptor correlationIdInterceptor() {
        return new CorrelationIdInterceptor();
    }
}
```

Hoặc đánh dấu class triển khai bằng `@Component` như các ví dụ trước. Boot Starter phát hiện các bean interceptor và cấu hình chúng vào `WebGraphQlHandler` chain.

Nếu tự tạo `WebGraphQlHandler`, có thể cấu hình chain bằng builder:

```java
WebGraphQlHandler handler = WebGraphQlHandler
    .builder(executionGraphQlService)
    .interceptor(correlationIdInterceptor)
    .build();
```

Khi dùng Spring Boot auto-configuration, thường không cần tự tạo handler chỉ để đăng ký interceptor. Hãy chọn một cách cấu hình thống nhất để tránh vô tình tạo hai GraphQL handler hoặc bỏ qua interceptor bean.

## 11. Phân biệt `WebGraphQlInterceptor` với các extension khác

| Thành phần | Phạm vi | Mục đích |
|---|---|---|
| `WebGraphQlInterceptor` | GraphQL qua HTTP và từng GraphQL request qua WebSocket | Đọc transport request, sửa `ExecutionInput`, xử lý response và thêm HTTP response header. |
| `WebSocketGraphQlInterceptor` | WebSocket connection và request | Mở rộng `WebGraphQlInterceptor` với callback vòng đời kết nối và cancellation. |
| `RSocketQlInterceptor` | GraphQL qua RSocket | Intercept request/response của RSocket transport. |
| `DataFetcherExceptionResolver` | Lỗi từ data fetcher | Chuyển exception trong quá trình field execution thành GraphQL errors. |
| GraphQL Java `Instrumentation` | Các giai đoạn thực thi GraphQL Java | Quan sát hoặc can thiệp sâu hơn vào execution, validation, data fetcher và metrics. |
| Spring Security filter chain | Tầng HTTP/security trước GraphQL handler | Authentication, authorization ở tầng web, CSRF và các chính sách HTTP. |

Chọn extension theo đúng ranh giới cần can thiệp. Không dùng interceptor để thay thế resolver cho một field cụ thể; cũng không dùng `DataFetcherExceptionResolver` để xử lý lỗi parse/validation trước execution.

## 12. Kiểm thử interceptor bằng `WebGraphQlTester`

`WebGraphQlTester` cho phép gửi request qua `WebGraphQlHandler`, nghĩa là request đi qua cả interceptor chain trước khi tới `ExecutionGraphQlService`. Đây là cách phù hợp để kiểm tra việc đọc header và truyền context.

Giả sử controller đọc correlation ID từ context:

```java
@Controller
class DiagnosticsController {

    @QueryMapping
    String correlationId(GraphQLContext context) {
        return context.get("correlationId");
    }
}
```

Trong test, tạo handler có interceptor và dùng `WebGraphQlTester` với header giả lập:

```java
WebGraphQlHandler handler = WebGraphQlHandler
    .builder(executionGraphQlService)
    .interceptor(new CorrelationIdInterceptor())
    .build();

WebGraphQlTester tester = WebGraphQlTester.builder(handler)
    .headers(headers -> headers.set("X-Correlation-Id", "test-123"))
    .build();

tester.document("""
        query {
            correlationId
        }
        """)
    .execute()
    .path("correlationId")
    .entity(String.class)
    .isEqualTo("test-123");
```

Ví dụ minh họa; `executionGraphQlService` cần được tạo từ schema và runtime wiring của ứng dụng. Test này xác minh header được đọc, đưa vào `GraphQLContext` và có thể được resolver sử dụng.

Các tình huống nên kiểm thử:

- Header có giá trị hợp lệ được chuyển vào context.
- Header thiếu hoặc sai định dạng khiến server tạo correlation ID mới.
- Interceptor vẫn truyền tiếp request và không chặn reactive chain ngoài ý muốn.
- Response HTTP có header được thêm sau khi GraphQL xử lý xong.
- Request-level validation error được quan sát đúng.
- Nhiều interceptor chạy đúng thứ tự và context đã thêm được interceptor sau sử dụng.
- WebSocket request không dựa vào HTTP response header cho từng operation.

## 13. Lưu ý bảo mật và hiệu năng

Interceptor chạy trên đường đi của mọi request thuộc transport được cấu hình. Vì vậy, logic ở đây cần ngắn gọn và có giới hạn.

1. Không ghi Authorization header, cookie, access token hoặc toàn bộ variables vào log.
2. Không tin cậy user ID, role hoặc tenant ID do client gửi trong header nếu chưa được xác thực.
3. Chỉ thêm dữ liệu cần thiết vào `GraphQLContext`; tránh đưa object request lớn hoặc mutable không cần thiết.
4. Tránh gọi database hoặc remote service đồng bộ trong interceptor. Nếu cần tải dữ liệu, dùng API bất đồng bộ và cân nhắc đưa logic vào service/resolver phù hợp.
5. Không gọi `block()` hoặc tự subscribe trong `intercept`; trả `Mono` được tạo từ `chain.next(request)`.
6. Giới hạn kích thước, định dạng và nguồn của correlation ID hoặc metadata do client gửi.
7. Không sửa GraphQL errors một cách tổng quát nếu chưa xác định rõ tác động tới client.
8. Với HTTP response header, cân nhắc CORS và không đưa dữ liệu nhạy cảm vào header.

Nếu cần giới hạn thời gian xử lý request, Spring for GraphQL còn có `TimeoutWebGraphQlInterceptor`. Có thể đăng ký interceptor này như bean để áp dụng timeout cho web transports; khi timeout, request bị hủy và reactive work có thể nhận tín hiệu cancellation.

## 14. Lỗi thường gặp

**Quên gọi `chain.next(request)`.** Nếu interceptor không chuyển request đi tiếp và cũng không chủ động tạo response phù hợp, GraphQL execution không diễn ra. Với interceptor thông thường, hãy trả về `chain.next(request)`.

**Gọi `chain.next(request)` nhiều lần.** Điều này có thể khiến cùng một GraphQL request được thực thi nhiều lần. Chỉ gọi chain một lần cho một lần intercept thông thường.

**Gọi `block()` hoặc `subscribe()` trong interceptor.** Việc này phá vỡ reactive flow, làm chặn thread hoặc tách lỗi khỏi GraphQL execution. Hãy compose bằng `map`, `doOnNext` và các toán tử Reactor phù hợp.

**Nhầm HTTP response header với GraphQL response data.** `getResponseHeaders()` là header transport; nó không thêm field vào phần `data` của GraphQL. Với WebSocket, HTTP handshake đã hoàn tất nên không thể thêm header mới cho từng operation.

**Dùng interceptor để xác thực token thủ công.** Đọc header không xác thực chữ ký, issuer, audience hoặc thời hạn token. Dùng Spring Security hoặc cơ chế authentication chuyên biệt.

**Đặt context sau khi chain đã chạy.** `ExecutionInput` cần được cấu hình trước `chain.next(request)` để resolver có thể đọc giá trị.

**Dùng interceptor cho lỗi của một field cụ thể.** Lỗi từ data fetcher nên được xử lý bằng `DataFetcherExceptionResolver` hoặc handler phù hợp; interceptor phù hợp hơn với request-level concern và response transport.

**Không quy định thứ tự interceptor.** Interceptor phụ thuộc context của interceptor khác có thể chạy trước khi giá trị được thêm. Dùng `@Order`/`Ordered` khi cần thứ tự rõ ràng.

## Kết luận

`WebGraphQlInterceptor` tạo một điểm mở rộng trước và sau GraphQL execution cho các transport HTTP và WebSocket. Triển khai `intercept(request, chain)`, đọc thông tin transport, dùng `configureExecutionInput` để bổ sung `GraphQLContext`, gọi `chain.next(request)` và xử lý response trong reactive pipeline. Đăng ký interceptor dưới dạng Spring bean, quy định thứ tự khi có phụ thuộc và kiểm thử qua `WebGraphQlTester`. Hãy giữ interceptor tập trung vào concern xuyên suốt request, để authentication, authorization và xử lý lỗi field vẫn nằm ở đúng lớp của ứng dụng.

## Tài liệu tham khảo

- [Spring for GraphQL — Server Transports and Web Interception](https://docs.spring.io/spring-graphql/reference/transports.html)
- [Spring for GraphQL API — `WebGraphQlInterceptor`](https://docs.spring.io/spring-graphql/docs/1.4.x/api/org/springframework/graphql/server/WebGraphQlInterceptor.html)
- [Spring for GraphQL API — `WebGraphQlRequest`](https://docs.spring.io/spring-graphql/docs/1.4.x/api/org/springframework/graphql/server/WebGraphQlRequest.html)
- [Spring for GraphQL — Testing `WebGraphQlHandler`](https://docs.spring.io/spring-graphql/reference/testing.html)
