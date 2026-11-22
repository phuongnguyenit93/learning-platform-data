# WebGraphQlHandler trong Spring for GraphQL

`WebGraphQlHandler` là điểm điều phối chung cho một GraphQL request đi vào từ tầng web của Spring for GraphQL. Nó nhận một `WebGraphQlRequest`, chạy chuỗi `WebGraphQlInterceptor`, chuyển request đến `ExecutionGraphQlService` để thực thi GraphQL và trả về `Mono<WebGraphQlResponse>`.

Hiểu `WebGraphQlHandler` giúp ta biết nên đặt logic kiểm tra request, truyền thông tin từ HTTP vào GraphQL context, bổ sung response header, chuẩn hóa lỗi và kiểm thử ở đâu. Đây là một phần của kiến trúc server-side của Spring for GraphQL, bên cạnh schema SDL, resolver, DataLoader và các transport HTTP hoặc WebSocket.

## 1. Vị trí của WebGraphQlHandler trong kiến trúc

Một ứng dụng Spring for GraphQL có thể nhận GraphQL request qua nhiều transport. Tầng transport chuyển dữ liệu trên giao thức thành đối tượng request của Spring; `WebGraphQlHandler` đảm nhiệm phần xử lý chung trước khi gọi GraphQL engine.

~~~mermaid
flowchart TD
    A[GraphQL client] --> B{Transport}
    B --> C[HTTP handler]
    B --> D[WebSocket handler]
    C --> E[WebGraphQlHandler]
    D --> E
    E --> F[WebGraphQlInterceptor chain]
    F --> G[ExecutionGraphQlService]
    G --> H[GraphQL Java engine]
    H --> I[Resolver / DataFetcher]
    I --> J[Service / Repository / DataLoader]
    J --> H
    H --> G
    G --> F
    F --> E
    E --> B
    B --> A
~~~

Các thành phần có trách nhiệm khác nhau:

| Thành phần | Trách nhiệm |
| --- | --- |
| `GraphQlHttpHandler` | Nhận GraphQL request qua HTTP, chuyển payload và response giữa HTTP với mô hình GraphQL của Spring |
| `GraphQlWebSocketHandler` | Quản lý GraphQL request qua WebSocket, bao gồm vòng đời kết nối và luồng subscription |
| `WebGraphQlHandler` | Chạy chuỗi interceptor dùng chung và chuyển request đến dịch vụ thực thi GraphQL |
| `WebGraphQlInterceptor` | Can thiệp request trước khi thực thi và response sau khi thực thi |
| `ExecutionGraphQlService` | Thực thi request theo cách độc lập với transport bằng GraphQL Java |
| `GraphQlSource` | Cung cấp cấu hình và GraphQL schema/runtime dùng cho việc thực thi |

`WebGraphQlHandler` không tự mở cổng HTTP, không tự tạo URL `/graphql` và không thay thế GraphQL engine. Nó là lớp nối giữa transport web và `ExecutionGraphQlService`. Trong ứng dụng Spring Boot, starter thường cấu hình các thành phần transport và handler tự động. Khi tích hợp độc lập hoặc cần tự xây dựng pipeline, ta có thể tạo handler bằng builder.

## 2. API chính của WebGraphQlHandler

`WebGraphQlHandler` thuộc package `org.springframework.graphql.server` và là một interface. API quan trọng nhất gồm:

- `builder(ExecutionGraphQlService)`: tạo builder gắn với dịch vụ thực thi GraphQL.
- `handleRequest(WebGraphQlRequest)`: xử lý một request và trả về `Mono<WebGraphQlResponse>`.
- `getWebSocketInterceptor()`: lấy interceptor kiểu `WebSocketGraphQlInterceptor` duy nhất trong chuỗi nếu có.

Builder cung cấp hai cách đăng ký interceptor:

- `interceptor(WebGraphQlInterceptor...)`: thêm một hoặc nhiều interceptor.
- `interceptors(List<WebGraphQlInterceptor>)`: đăng ký một danh sách interceptor.
- `build()`: tạo instance `WebGraphQlHandler`.

Ví dụ khởi tạo handler:

~~~java
import org.springframework.graphql.ExecutionGraphQlService;
import org.springframework.graphql.server.WebGraphQlHandler;
import org.springframework.graphql.server.WebGraphQlInterceptor;

import java.util.List;

public class GraphQlHandlerConfiguration {

    public WebGraphQlHandler webGraphQlHandler(
            ExecutionGraphQlService executionGraphQlService,
            WebGraphQlInterceptor tenantInterceptor,
            WebGraphQlInterceptor responseHeaderInterceptor
    ) {
        return WebGraphQlHandler.builder(executionGraphQlService)
                .interceptors(List.of(
                        tenantInterceptor,
                        responseHeaderInterceptor
                ))
                .build();
    }
}
~~~

Đoạn code trên minh họa cách tạo handler thủ công. Trong ứng dụng thực tế, method cấu hình thường được khai báo bằng `@Bean` trong một class `@Configuration`. Nếu đang dùng Spring Boot starter, hãy ưu tiên cơ chế auto-configuration và khai báo các `WebGraphQlInterceptor` dưới dạng Spring bean; starter có thể phát hiện và đưa chúng vào pipeline theo thứ tự bean đã cấu hình.

## 3. WebGraphQlRequest và WebGraphQlResponse

### 3.1. Đọc thông tin request

`WebGraphQlRequest` là đối tượng request phía server cho GraphQL qua HTTP hoặc WebSocket. Ngoài document, operation name, variables và extensions được kế thừa từ `GraphQlRequest`, nó còn cung cấp thông tin của request web:

| API | Ý nghĩa |
| --- | --- |
| `getHeaders()` | HTTP headers của request hoặc của WebSocket handshake |
| `getCookies()` | Cookies của HTTP request hoặc WebSocket handshake |
| `getUri()` | URL của HTTP request hoặc WebSocket handshake |
| `getRemoteAddress()` | Địa chỉ client nếu transport cung cấp |
| `getAttributes()` | Request attributes hoặc WebSocket session attributes |
| `getDocument()` | Nội dung GraphQL document |
| `getOperationName()` | Tên operation được client chọn, nếu có |
| `getVariables()` | Các biến đầu vào của operation |
| `getExtensions()` | Phần mở rộng của GraphQL request |

Với WebSocket, headers và URI ở đây là thông tin của lần HTTP handshake mở kết nối. Những message GraphQL tiếp theo được truyền bên trong kết nối WebSocket, không phải các HTTP request độc lập.

`WebGraphQlRequest` cũng cho phép bổ sung cấu hình vào `ExecutionInput` thông qua `configureExecutionInput(...)`. Đây là điểm quan trọng để đưa metadata từ tầng web vào `GraphQLContext`, gắn execution ID hoặc tùy chỉnh thông tin thực thi trước khi GraphQL Java xử lý request.

### 3.2. Đọc và thay đổi response

`WebGraphQlResponse` bọc kết quả thực thi GraphQL và cung cấp các thông tin quen thuộc như data, errors, extensions và execution input. Một số API thường dùng:

- `getData()` và `getErrors()` để đọc dữ liệu và lỗi trả về.
- `isValid()` để kiểm tra response có phần `data` hợp lệ theo mô hình response của GraphQL hay không. Response vẫn có thể chứa lỗi của một field trong khi các field khác trả về dữ liệu thành công.
- `getExecutionInput()` để truy cập `ExecutionInput` đã được dùng khi thực thi.
- `getResponseHeaders()` để bổ sung HTTP response headers.
- `transform(...)` để tạo response mới với `ExecutionResult` đã được điều chỉnh.

`getResponseHeaders()` phục vụ GraphQL qua HTTP. Với WebSocket, HTTP handshake đã hoàn tất trước khi các GraphQL operation được gửi, do đó không thể dùng response headers để thêm HTTP header riêng cho từng message GraphQL.

## 4. WebGraphQlInterceptor: mở rộng pipeline xử lý

`WebGraphQlInterceptor` là cơ chế mở rộng chính được `WebGraphQlHandler` điều phối. Interface có method:

~~~java
Mono<WebGraphQlResponse> intercept(
        WebGraphQlRequest request,
        WebGraphQlInterceptor.Chain chain
);
~~~

`Chain` đại diện cho phần pipeline còn lại, bao gồm các interceptor tiếp theo và `ExecutionGraphQlService`. Gọi `chain.next(request)` để chuyển request đi tiếp. Interceptor có thể thực hiện công việc trước lời gọi đó, xử lý response sau khi publisher hoàn tất, hoặc kết thúc sớm nếu request không được phép đi tiếp.

Một interceptor có thể dùng cho các việc như:

- Đọc headers, cookies, URI hoặc attributes để lấy metadata của request.
- Bổ sung thông tin vào `ExecutionInput` và `GraphQLContext`.
- Ghi nhận thời gian xử lý, correlation ID hoặc thông tin quan sát hệ thống.
- Thêm HTTP response header hoặc cookie.
- Kiểm tra và chuẩn hóa lỗi request-level trong `ExecutionResult`.
- Áp dụng timeout hoặc quy tắc giới hạn xử lý ở tầng request.

### 4.1. Đưa request metadata vào GraphQLContext

Giả sử mỗi request có header `X-Tenant-Id` để xác định tenant. Resolver cần nhận tenant ID mà không phải đọc trực tiếp đối tượng HTTP request. Interceptor có thể đưa giá trị này vào `GraphQLContext`:

~~~java
import org.springframework.graphql.server.WebGraphQlInterceptor;
import org.springframework.graphql.server.WebGraphQlRequest;
import org.springframework.graphql.server.WebGraphQlResponse;
import reactor.core.publisher.Mono;

public class TenantContextInterceptor implements WebGraphQlInterceptor {

    @Override
    public Mono<WebGraphQlResponse> intercept(
            WebGraphQlRequest request,
            Chain chain
    ) {
        String tenantId = request.getHeaders().getFirst("X-Tenant-Id");

        if (tenantId != null && !tenantId.isBlank()) {
            request.configureExecutionInput((input, builder) ->
                    builder.graphQLContext(context ->
                            context.put("tenantId", tenantId)
                    ).build()
            );
        }

        return chain.next(request);
    }
}
~~~

Resolver có thể đọc giá trị đã đưa vào context bằng `@ContextValue`:

~~~java
@Controller
public class BookController {

    private final BookService bookService;

    public BookController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    public List<Book> books(@ContextValue("tenantId") String tenantId) {
        return bookService.findAllByTenant(tenantId);
    }
}
~~~

Ví dụ này cho thấy controller chỉ nhận context cần thiết, không phụ thuộc vào API của Servlet hay WebFlux. Trong hệ thống nhiều tenant, tenant ID phải được xác minh từ danh tính hoặc phạm vi truy cập đã xác thực. Không được coi một header do client tự gửi là bằng chứng người dùng có quyền truy cập tenant tương ứng. Interceptor chỉ truyền dữ liệu vào GraphQL context; nó không tự tạo ra một ranh giới phân quyền an toàn.

### 4.2. Bổ sung HTTP response header

Interceptor cũng có thể xử lý response sau khi GraphQL engine hoàn tất. Ví dụ sau bổ sung `Cache-Control` cho response HTTP:

~~~java
import org.springframework.graphql.server.WebGraphQlInterceptor;
import org.springframework.graphql.server.WebGraphQlRequest;
import org.springframework.graphql.server.WebGraphQlResponse;
import org.springframework.http.HttpHeaders;
import reactor.core.publisher.Mono;

public class NoStoreResponseInterceptor implements WebGraphQlInterceptor {

    @Override
    public Mono<WebGraphQlResponse> intercept(
            WebGraphQlRequest request,
            Chain chain
    ) {
        return chain.next(request).doOnNext(response ->
                response.getResponseHeaders().add(
                        HttpHeaders.CACHE_CONTROL,
                        "no-store"
                )
        );
    }
}
~~~

`chain.next(request)` trả về `Mono`, vì vậy ta có thể dùng các toán tử Reactor như `map`, `flatMap` hoặc `doOnNext` để xử lý kết quả mà không chặn thread bằng `block()`. Hãy chọn header theo chính sách cache thực tế của API; dữ liệu cá nhân hoặc response phụ thuộc quyền truy cập thường không nên được cache công khai.

### 4.3. Chuẩn hóa lỗi ở cấp request

GraphQL có nhiều giai đoạn có thể phát sinh lỗi. Lỗi trong một data fetcher xảy ra sau khi thực thi field bắt đầu và thường được xử lý bằng `DataFetcherExceptionResolver`. Trong khi đó, lỗi cú pháp hoặc lỗi validation của GraphQL document có thể xảy ra trước khi data fetcher được gọi.

`DataFetcherExceptionResolver` không xử lý được các lỗi request-level xảy ra trước giai đoạn thực thi field. Khi cần kiểm tra hoặc biến đổi các lỗi này, interceptor có thể đọc `response.isValid()`, xem `response.getErrors()` rồi dùng `response.transform(...)` để xây dựng response mới. Khi chuẩn hóa, cần giữ lại thông tin vị trí, path và extensions hữu ích; tránh xóa nguyên nhân lỗi hoặc làm lộ stack trace nội bộ.

Không nên dùng interceptor để biến mọi lỗi thành một response thành công. Việc thay đổi lỗi phải giữ đúng ngữ nghĩa GraphQL để client biết request không hợp lệ hay chỉ một field trong response gặp sự cố.

## 5. Cấu hình interceptor trong Spring Boot và cấu hình độc lập

### 5.1. Dùng Spring Boot starter

Với ứng dụng Spring Boot đã dùng Spring for GraphQL starter, có thể khai báo interceptor thành bean:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.graphql.server.WebGraphQlInterceptor;

@Configuration(proxyBeanMethods = false)
public class GraphQlWebConfiguration {

    @Bean
    WebGraphQlInterceptor tenantContextInterceptor() {
        return new TenantContextInterceptor();
    }

    @Bean
    WebGraphQlInterceptor noStoreResponseInterceptor() {
        return new NoStoreResponseInterceptor();
    }
}
~~~

Starter phát hiện các bean `WebGraphQlInterceptor` và đưa chúng vào chuỗi xử lý web GraphQL. Có thể dùng `@Order` hoặc cơ chế sắp xếp bean của Spring để xác định thứ tự. Nếu thứ tự ảnh hưởng đến xác thực, ghi log hoặc xử lý response, hãy khai báo rõ và kiểm thử hành vi của toàn chuỗi.

### 5.2. Tự tạo handler khi không dùng Spring Boot

Trong cấu hình độc lập, ứng dụng phải tự tạo `ExecutionGraphQlService`, `WebGraphQlHandler` và transport handler. Phần dưới minh họa phần tạo handler; `executionGraphQlService` cần được cấu hình trước với `GraphQlSource` và runtime wiring tương ứng:

~~~java
@Configuration(proxyBeanMethods = false)
public class GraphQlServerConfiguration {

    @Bean
    WebGraphQlHandler webGraphQlHandler(
            ExecutionGraphQlService executionGraphQlService,
            TenantContextInterceptor tenantInterceptor,
            NoStoreResponseInterceptor responseInterceptor
    ) {
        return WebGraphQlHandler.builder(executionGraphQlService)
                .interceptor(tenantInterceptor, responseInterceptor)
                .build();
    }
}
~~~

Sau đó tạo transport adapter thích hợp. Với Spring MVC, lớp HTTP handler nằm trong package `org.springframework.graphql.server.webmvc`; với WebFlux, dùng biến thể trong package `org.springframework.graphql.server.webflux`. Adapter nhận request HTTP, chuyển nó thành `WebGraphQlRequest`, gọi `WebGraphQlHandler` rồi ghi response về HTTP. Nếu dùng WebSocket, cần cấu hình `GraphQlWebSocketHandler` và endpoint WebSocket tương ứng.

Việc tạo `WebGraphQlHandler` chưa đủ để client gọi được API. Ứng dụng vẫn phải đăng ký route hoặc endpoint transport, cấu hình schema, và bảo đảm dependency của stack MVC/WebFlux đang dùng có mặt.

## 6. WebSocketGraphQlInterceptor và xử lý kết nối

`WebSocketGraphQlInterceptor` mở rộng `WebGraphQlInterceptor` để xử lý vòng đời kết nối WebSocket. Ngoài việc intercept từng GraphQL request trên kết nối, nó còn có các callback liên quan đến lúc kết nối bắt đầu, kết thúc và lúc client hủy subscription.

Điểm cần nhớ:

- `WebGraphQlInterceptor` xử lý request GraphQL qua HTTP hoặc WebSocket.
- `WebSocketGraphQlInterceptor` bổ sung khả năng xử lý sự kiện ở cấp kết nối WebSocket.
- Một chuỗi interceptor chỉ được có tối đa một `WebSocketGraphQlInterceptor`.
- Spring for GraphQL có các triển khai `AuthenticationWebSocketInterceptor` cho WebMVC và WebFlux để trích xuất thông tin xác thực từ message `connection_init` và truyền `SecurityContext` sang các request tiếp theo trên kết nối.

Kết nối WebSocket có thể tồn tại lâu và mang nhiều subscription đồng thời. Vì vậy, cần quản lý số kết nối, số subscription, kích thước message, xác thực và quyền truy cập trong suốt vòng đời kết nối. Việc xác thực thành công ở thời điểm handshake không có nghĩa mọi operation sau đó đều được phép đọc mọi dữ liệu.

## 7. Timeout và hủy xử lý request

Một GraphQL request có thể tốn nhiều thời gian do truy vấn phức tạp, gọi dịch vụ bên ngoài hoặc data fetcher bị chậm. Spring for GraphQL cung cấp `TimeoutWebGraphQlInterceptor` để đặt giới hạn thời gian cho request qua web transport.

Ví dụ tạo interceptor với timeout năm giây:

~~~java
import java.time.Duration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.graphql.server.TimeoutWebGraphQlInterceptor;

@Configuration(proxyBeanMethods = false)
public class GraphQlTimeoutConfiguration {

    @Bean
    TimeoutWebGraphQlInterceptor timeoutWebGraphQlInterceptor() {
        return new TimeoutWebGraphQlInterceptor(Duration.ofSeconds(5));
    }
}
~~~

Khi timeout xảy ra, interceptor phát tín hiệu hủy lên pipeline. Các tác vụ reactive hỗ trợ cancellation có thể dừng công việc đang chạy, giúp tránh tiếp tục tiêu tốn tài nguyên cho request đã hết thời gian chờ. Tuy nhiên, hủy một publisher không tự động đảo ngược side effect đã được ghi vào cơ sở dữ liệu hoặc hệ thống bên ngoài. Các thao tác ghi vẫn cần transaction, idempotency và chính sách timeout riêng ở tầng nghiệp vụ khi cần.

Timeout ở cấp request cũng cần được cân nhắc theo loại operation. Một query thông thường có thể có giới hạn ngắn; subscription là luồng dài hạn nên không nên áp dụng một timeout tổng thể như một request HTTP đơn lẻ. Với WebSocket hoặc SSE, hãy cấu hình timeout và giới hạn kết nối theo đặc điểm của transport.

## 8. Kiểm thử WebGraphQlHandler và interceptor chain

Spring for GraphQL cung cấp `WebGraphQlTester` để kiểm thử phía server thông qua `WebGraphQlHandler`. Cách này hữu ích khi cần kiểm tra interceptor chain và thông tin HTTP giả lập mà không phải khởi chạy một HTTP server thật.

Ví dụ tạo tester từ handler:

~~~java
WebGraphQlTester tester = WebGraphQlTester.builder(webGraphQlHandler)
        .headers(headers -> headers.set("X-Tenant-Id", "tenant-42"))
        .build();

tester.document("""
        query {
            books {
                id
                title
            }
        }
        """)
    .execute()
    .path("books")
    .entityList(Book.class)
    .hasSize(2);
~~~

Test trên có thể xác nhận request header được interceptor đưa vào context và resolver trả về dữ liệu của tenant tương ứng. Cần tạo `ExecutionGraphQlService` và controller/service test fixture phù hợp trước khi tạo handler.

Nên có các nhóm kiểm thử sau:

1. Handler gọi `ExecutionGraphQlService` và trả response đúng với một request hợp lệ.
2. Interceptor đọc header hoặc attribute và truyền đúng giá trị vào `GraphQLContext`.
3. Interceptor xử lý response đúng cách, bao gồm HTTP response header nếu transport là HTTP.
4. Các interceptor chạy theo thứ tự đã cấu hình; trường hợp interceptor từ chối request không gọi phần pipeline phía sau.
5. Request lỗi cú pháp hoặc validation được nhận diện đúng; lỗi field-level vẫn giữ được data hợp lệ của những field khác.
6. Timeout phát tín hiệu cancellation và không để các tác vụ reactive tiếp tục chạy vô ích.
7. Với WebSocket, kiểm thử riêng xác thực `connection_init`, kết thúc kết nối, hủy subscription và giới hạn số subscription.

`WebGraphQlTester` không thay thế kiểm thử transport thật. Khi cần xác nhận routing, HTTP status, codec, WebSocket protocol hoặc cấu hình security filter chain, hãy bổ sung kiểm thử bằng `HttpGraphQlTester`, `WebSocketGraphQlTester` hoặc integration test phù hợp với stack đang chạy.

## 9. Những lưu ý khi thiết kế interceptor

**Giữ interceptor ngắn và tập trung.** Interceptor phù hợp với logic xuyên suốt request như context propagation, correlation ID, header và timeout. Quy tắc nghiệp vụ riêng của một field nên nằm trong resolver hoặc service.

**Không chặn luồng reactive.** `intercept` trả về `Mono<WebGraphQlResponse>`. Tránh gọi `block()`, chờ đồng bộ hoặc thực hiện I/O blocking trên event-loop của WebFlux. Nếu phải gọi API bên ngoài, dùng client reactive hoặc chuyển tác vụ blocking sang scheduler phù hợp.

**Không tin metadata chưa xác thực.** Header, cookie và request attributes là dữ liệu đầu vào. Chỉ đưa danh tính hoặc tenant vào context sau khi đã xác thực và kiểm tra quyền. Resolver/service vẫn phải áp dụng authorization theo tài nguyên và field.

**Không lạm dụng response transformation.** Việc thay đổi `ExecutionResult` có thể ảnh hưởng đến data, errors, path, locations và extensions mà client dựa vào. Chỉ thay đổi phần cần thiết và giữ ngữ nghĩa GraphQL.

**Theo dõi thứ tự interceptor.** Một interceptor có thể bổ sung context mà interceptor khác hoặc resolver cần dùng. Hãy sắp xếp thứ tự bean rõ ràng và kiểm thử cả pipeline, thay vì chỉ kiểm thử từng interceptor độc lập.

**Tách transport concern khỏi nghiệp vụ.** Không để controller hoặc service phụ thuộc vào `HttpServletRequest`, `ServerWebExchange` hay WebSocket session nếu chỉ cần tenant, locale hoặc principal. Truyền dữ liệu cần thiết qua `GraphQLContext` giúp resolver độc lập với transport hơn.

## 10. Quy trình áp dụng WebGraphQlHandler

Khi cần thêm xử lý chung cho GraphQL request, có thể thực hiện theo trình tự:

1. Xác định logic thuộc tầng web request hay thuộc nghiệp vụ của resolver/service.
2. Chọn `WebGraphQlInterceptor` cho xử lý trước/sau từng request; chọn `WebSocketGraphQlInterceptor` khi cần callback vòng đời kết nối.
3. Đọc thông tin cần thiết từ `WebGraphQlRequest` và chỉ truyền dữ liệu đã được xác thực vào `GraphQLContext`.
4. Đăng ký interceptor bằng Spring Boot bean hoặc `WebGraphQlHandler.builder(...).interceptor(...)` trong cấu hình độc lập.
5. Kiểm tra cách interceptor xử lý response, lỗi, cancellation và HTTP headers.
6. Dùng `WebGraphQlTester` kiểm thử chuỗi handler; dùng tester theo transport cho các hành vi chỉ có thể xác minh qua HTTP hoặc WebSocket thật.

Khi phân biệt rõ trách nhiệm của transport handler, `WebGraphQlHandler`, interceptor và `ExecutionGraphQlService`, ta có thể mở rộng xử lý request tập trung mà vẫn giữ resolver và service dễ kiểm thử, ít phụ thuộc vào giao thức truyền tải.

## Tài liệu tham khảo

- [Spring for GraphQL — Server Transports](https://docs.spring.io/spring-graphql/reference/transports.html)
- [Spring for GraphQL — Request Execution](https://docs.spring.io/spring-graphql/reference/request-execution.html)
- [Spring for GraphQL — Standalone Setup](https://docs.spring.io/spring-graphql/reference/standalone-setup.html)
- [Spring for GraphQL — Testing](https://docs.spring.io/spring-graphql/reference/testing.html)
- [WebGraphQlHandler API](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/server/WebGraphQlHandler.html)
