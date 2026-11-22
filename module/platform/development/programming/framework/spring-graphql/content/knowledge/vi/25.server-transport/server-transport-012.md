# Transport và execution service

Spring for GraphQL tách việc nhận GraphQL request qua mạng khỏi việc thực thi operation. HTTP, WebSocket, Server-Sent Events (SSE) và RSocket là các transport khác nhau; chúng chuyển request vào cùng một lớp thực thi GraphQL để schema, resolver, DataLoader và quy tắc xử lý lỗi có thể dùng chung.

Hai thành phần quan trọng trong kiến trúc này là **ExecutionGraphQlService** và **WebGraphQlHandler**. ExecutionGraphQlService gọi GraphQL Java để thực thi request theo cách không phụ thuộc transport. WebGraphQlHandler đứng ở tầng web, chạy chuỗi interceptor cho HTTP và WebSocket rồi chuyển request đến execution service. Hiểu ranh giới này giúp chọn đúng transport, đặt logic xác thực và context ở đúng tầng, đồng thời kiểm thử execution mà không cần khởi chạy server.

## 1. Luồng xử lý GraphQL request ở server

Một request đi từ client đến resolver qua nhiều lớp:

~~~mermaid
flowchart TD
    A["GraphQL client"] --> B{"Transport"}
    B --> C["HTTP handler"]
    B --> D["WebSocket handler"]
    B --> E["SSE handler"]
    B --> F["RSocket handler"]
    C --> G["WebGraphQlHandler"]
    D --> G
    E --> G
    G --> H["WebGraphQlInterceptor chain"]
    H --> I["ExecutionGraphQlService"]
    F --> J["RSocketQlInterceptor chain"]
    J --> I
    I --> K["GraphQlSource / GraphQL Java"]
    K --> L["Parse, validate, coerce"]
    L --> M["Execute DataFetcher / controller"]
    M --> N["ExecutionResult"]
    N --> O["Transport response"]
~~~

Có thể đọc luồng này theo ba nhóm trách nhiệm:

- **Transport layer:** nhận dữ liệu trên HTTP, WebSocket, SSE hoặc RSocket; giải mã request; áp dụng quy tắc giao thức; ghi response hoặc stream về client.
- **Request interception:** kiểm tra thông tin của transport, bổ sung context, correlation ID, header hoặc metadata; có thể điều chỉnh execution input và response.
- **Execution layer:** dùng schema và runtime wiring để parse, validate và thực thi query, mutation hoặc subscription; gọi các DataFetcher và tổng hợp kết quả.

Transport không quyết định cách resolver truy vấn database. Resolver cũng không nên tự đọc HTTP request hoặc biết client đang dùng WebSocket hay RSocket nếu nghiệp vụ không cần thông tin đó.

## 2. GraphQlSource và ExecutionGraphQlService

### GraphQlSource

`GraphQlSource` là abstraction cung cấp đối tượng `graphql.GraphQL` mà server sẽ gọi. Nó có builder để tạo GraphQL schema và cấu hình runtime wiring.

Trong Spring Boot, schema thường được đặt tại:

~~~text
src/main/resources/graphql/
~~~

Các file có phần mở rộng `.graphqls` hoặc `.gqls` trong `classpath:graphql/**` được tự động tìm và ghép thành schema. `GraphQlSource.Builder` cũng nhận schema resources từ những vị trí khác nếu ứng dụng cần cấu hình riêng.

Builder còn là nơi kết nối các thành phần runtime:

- `RuntimeWiringConfigurer` đăng ký custom scalar, directive, type resolver hoặc DataFetcher.
- `AnnotatedControllerConfigurer` phát hiện các method có `@QueryMapping`, `@MutationMapping`, `@SubscriptionMapping`, `@SchemaMapping` và đăng ký chúng thành DataFetcher.
- `Instrumentation` hỗ trợ theo dõi và can thiệp vào quá trình thực thi.
- `DataFetcherExceptionResolver` xử lý exception phát sinh khi một field được fetch.
- `SubscriptionExceptionResolver` xử lý lỗi xảy ra sau khi Publisher của subscription đã bắt đầu phát dữ liệu.

Spring Boot tự phát hiện các bean cấu hình phù hợp và đưa chúng vào quá trình tạo `GraphQlSource`. Phần lớn ứng dụng dùng Boot không cần tự tạo `GraphQL` instance.

### ExecutionGraphQlService

`ExecutionGraphQlService` là abstraction trung tâm để thực thi GraphQL request bằng GraphQL Java. Interface này không gắn với HTTP, WebSocket hoặc RSocket.

Implementation mặc định là `DefaultExecutionGraphQlService`. Nó nhận `GraphQlSource`, lấy `GraphQL` instance từ source và thực hiện request. Spring Boot tự cấu hình service này cùng các thành phần liên quan.

Có thể phân biệt trách nhiệm:

| Thành phần | Trách nhiệm |
| --- | --- |
| `GraphQlSource` | Cung cấp GraphQL schema và GraphQL runtime đã cấu hình |
| `ExecutionGraphQlService` | Nhận execution request và gọi GraphQL Java |
| `DefaultExecutionGraphQlService` | Implementation mặc định của execution service |
| `WebGraphQlHandler` | Chạy interceptor chain cho HTTP/WebSocket rồi gọi execution service |
| HTTP/WebSocket/SSE handler | Chuyển đổi request/response theo transport |
| `GraphQlRSocketHandler` | Chuyển request RSocket thành GraphQL execution và trả kết quả theo interaction model |

Điểm quan trọng: cùng một `ExecutionGraphQlService` có thể được nhiều transport sử dụng. Khi thêm WebSocket hoặc SSE, ứng dụng không phải viết lại resolver hay schema.

## 3. Cấu hình transport với Spring Boot

Một ứng dụng cần `spring-boot-starter-graphql` và ít nhất một starter cung cấp server transport. Lựa chọn phổ biến:

| Dependency | Transport được cung cấp | Nền tảng |
| --- | --- | --- |
| `spring-boot-starter-graphql` | GraphQL schema và execution | Spring for GraphQL |
| `spring-boot-starter-web` | HTTP | Spring MVC |
| `spring-boot-starter-websocket` | WebSocket | Servlet application |
| `spring-boot-starter-webflux` | HTTP và WebSocket | Spring WebFlux |
| `spring-boot-starter-rsocket` | RSocket qua TCP hoặc WebSocket | Reactor Netty / Spring Messaging |

Ví dụ ứng dụng dùng Spring MVC qua HTTP:

~~~groovy
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-graphql")
    implementation("org.springframework.boot:spring-boot-starter-web")
}
~~~

Nếu ứng dụng dùng WebFlux, thay starter MVC bằng `spring-boot-starter-webflux`. Chỉ thêm transport mà hệ thống thực sự cần; không cần cài mọi starter chỉ vì GraphQL hỗ trợ nhiều giao thức.

Với Boot, endpoint HTTP mặc định là `POST /graphql`. Có thể đổi đường dẫn bằng `spring.graphql.http.path`. HTTP endpoint được auto-configuration cung cấp thông qua `RouterFunction`.

Cấu hình ví dụ:

~~~yaml
spring:
  graphql:
    http:
      path: /graphql
    websocket:
      path: /graphql
    rsocket:
      mapping: graphql
~~~

Các thuộc tính trên phục vụ những transport tương ứng. WebSocket endpoint mặc định không được bật chỉ vì ứng dụng đã có GraphQL. Cần cấu hình `spring.graphql.websocket.path`; với Servlet application còn cần `spring-boot-starter-websocket`. Với WebFlux, không cần thêm starter WebSocket riêng.

RSocket cần server RSocket được cấu hình và route GraphQL được chỉ định bằng `spring.graphql.rsocket.mapping`.

## 4. HTTP transport

HTTP phù hợp với request có một response, đặc biệt là query và mutation. `GraphQlHttpHandler` nhận HTTP request, chuyển payload thành GraphQL request rồi ủy quyền cho interceptor chain.

Spring for GraphQL có hai implementation HTTP handler: một cho Spring MVC và một cho Spring WebFlux. Chúng có hành vi GraphQL tương đương; khác biệt nằm ở cách ghi response, với MVC dựa trên I/O của Servlet và WebFlux dùng non-blocking I/O.

Mặc định, endpoint HTTP chấp nhận `POST` với:

- `Content-Type: application/json`
- Body JSON chứa GraphQL document và các thông tin request.

Ví dụ request:

~~~http
POST /graphql
Content-Type: application/json
Accept: application/graphql-response+json
~~~

~~~json
{
  "query": "query GetBook($id: ID!) { book(id: $id) { id title } }",
  "operationName": "GetBook",
  "variables": {
    "id": "book-42"
  }
}
~~~

Các thuộc tính chính:

| Thuộc tính | Ý nghĩa |
| --- | --- |
| `query` | GraphQL document dưới dạng chuỗi |
| `operationName` | Tên operation cần thực thi khi document có nhiều operation |
| `variables` | Giá trị cho các variable được khai báo trong document |
| `extensions` | Metadata mở rộng, ví dụ persisted query nếu server hỗ trợ |

Response là GraphQL response JSON, thường có `data` và có thể có `errors`:

~~~json
{
  "data": {
    "book": {
      "id": "book-42",
      "title": "Spring GraphQL"
    }
  }
}
~~~

HTTP transport hỗ trợ hai kiểu media type đáng chú ý:

- `application/graphql-response+json`: media type theo GraphQL over HTTP specification.
- `application/json`: kiểu tương thích cũ được nhiều client sử dụng.

Nếu request đã qua parse và validation, lỗi xảy ra trong quá trình thực thi field được biểu diễn trong phần `errors` của GraphQL response. Với `application/graphql-response+json`, các lỗi parse hoặc validation có thể được phản ánh bằng HTTP 4xx; với media type `application/json` cũ, các trường hợp đó thường vẫn trả HTTP 200. Lỗi transport như server không khả dụng, xác thực HTTP thất bại hoặc body không phải JSON hợp lệ vẫn có thể trả 4xx/5xx.

HTTP POST không phải cách truyền stream subscription. Dùng WebSocket hoặc SSE khi client cần nhận nhiều event từ một subscription.

## 5. HTTP GET và giới hạn an toàn

Spring for GraphQL có thể bật HTTP GET theo GraphQL over HTTP specification, nhưng GET bị tắt mặc định. Muốn bật, phải cấu hình đồng thời handler và request predicate của endpoint.

Ví dụ ở mức handler:

~~~java
GraphQlHttpHandler httpHandler = GraphQlHttpHandler
        .builder(webGraphQlHandler)
        .httpMethods(HttpMethod.GET, HttpMethod.POST)
        .build();
~~~

Với GET, request body không được dùng. Các tham số được truyền qua query string:

- `query` và `operationName` là chuỗi thông thường.
- `variables` và `extensions`, nếu có, phải là JSON được mã hóa thành chuỗi.

GET chỉ phù hợp với operation an toàn như query. Nếu client gửi mutation qua GET, server từ chối bằng `405 Method Not Allowed`, kể cả khi mutation document hợp lệ.

Trước khi bật GET, cần cân nhắc:

- Query string có thể xuất hiện trong access log, browser history, `Referer` header, proxy hoặc cache.
- Không nên đưa token, thông tin cá nhân hoặc dữ liệu nhạy cảm vào variables qua GET.
- GET là CORS simple request trong nhiều trường hợp và được xem là HTTP safe method bởi Spring Security CSRF filter.
- Resolver của query vẫn có thể tạo tải, ghi audit log hoặc gây side effect nếu thiết kế sai. Query nên giữ đúng semantics chỉ đọc.

Nếu request URI quá dài, client nên chuyển sang POST.

## 6. Server-Sent Events (SSE)

`GraphQlSseHandler` cung cấp subscription qua HTTP Server-Sent Events. Client gửi GraphQL request bằng HTTP POST với JSON body như HTTP transport, nhưng đặt header:

~~~http
Accept: text/event-stream
~~~

Server gửi kết quả thành một hoặc nhiều Server-Sent Event. Đây là cách thay thế WebSocket khi ứng dụng chỉ cần server đẩy dữ liệu một chiều đến client.

SSE phù hợp với subscription mà client chỉ cần nhận event. Nó không phù hợp để thực hiện query hoặc mutation; hai loại operation đó nên dùng HTTP JSON thông thường.

Mặc định SSE dùng POST. Có thể bật GET nếu client là browser `EventSource`, nhưng phải cấu hình cả handler và request predicate. Các lưu ý bảo mật của GET cũng áp dụng cho SSE GET.

Spring for GraphQL triển khai chế độ distinct connections cho SSE. Khi triển khai nhiều client subscription, cần tính toán số kết nối đồng thời, giới hạn tài nguyên và tác động của HTTP version. HTTP/2 có thể giúp giảm chi phí kết nối trong một số kiến trúc.

## 7. WebSocket transport

WebSocket giữ kết nối hai chiều mở giữa client và server. GraphQL over WebSocket thường được chọn cho subscription vì server có thể gửi nhiều kết quả trên cùng một kết nối. Protocol được Spring for GraphQL hỗ trợ là `graphql-ws`.

`GraphQlWebSocketHandler` xử lý protocol này. Có implementation cho Spring MVC và Spring WebFlux. Cả hai đều hỗ trợ request bất đồng bộ; WebFlux dùng I/O non-blocking và back pressure để truyền stream.

WebSocket cũng có thể chạy query hoặc mutation với một response, nhưng lợi ích chính là subscription và khả năng dùng lại kết nối cho nhiều request.

### Bật endpoint WebSocket

Với Spring Boot:

1. Thêm `spring-boot-starter-websocket` nếu ứng dụng chạy trên Servlet/Spring MVC.
2. Với Spring WebFlux, không cần dependency WebSocket riêng.
3. Đặt `spring.graphql.websocket.path` để bật endpoint.

Ví dụ:

~~~yaml
spring:
  graphql:
    websocket:
      path: /graphql
~~~

### Authentication trên WebSocket

WebSocket có vòng đời kết nối riêng. Client có thể gửi thông tin xác thực trong payload của message `connection_init`. `WebSocketGraphQlInterceptor` cho phép xử lý lúc kết nối bắt đầu, kết thúc và khi client hủy subscription.

Spring for GraphQL có `AuthenticationWebSocketInterceptor` cho WebMVC và WebFlux để lấy thông tin từ `connection_init`, xác thực và truyền `SecurityContext` cho các request tiếp theo trên cùng connection.

Một interceptor loại `WebSocketGraphQlInterceptor` có thể được đăng ký trong một chain. Khi thiết kế authentication, hãy xác định rõ thời điểm token được kiểm tra, cách xử lý token hết hạn và việc thu hồi quyền trên một kết nối sống lâu.

### Quản lý tài nguyên

Một WebSocket session có thể duy trì nhiều subscription cùng lúc. Cần giới hạn:

- Số kết nối WebSocket tối đa ở server/connector.
- Kích thước tối đa của message buffer.
- Số subscription đồng thời trên một session.

`GraphQlWebSocketHandler` có tùy chọn `maxSubscriptionsPerSession`. Mặc định không giới hạn; khi chạm giới hạn đã cấu hình, session bị đóng. Hãy đặt ngưỡng phù hợp với CPU, bộ nhớ và tải thực tế của server.

## 8. RSocket transport

RSocket hỗ trợ GraphQL qua TCP hoặc WebSocket. Khác biệt chính nằm ở interaction model:

| GraphQL operation | RSocket interaction |
| --- | --- |
| Query | `request-response` |
| Mutation | `request-response` |
| Subscription | `request-stream` |

`GraphQlRSocketHandler` nhận payload và chuyển nó vào GraphQL execution. Ứng dụng có thể ủy quyền cho handler từ một Spring Messaging controller:

~~~java
import java.util.Map;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

import org.springframework.graphql.server.GraphQlRSocketHandler;
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.stereotype.Controller;

@Controller
public class GraphQlRSocketController {

    private final GraphQlRSocketHandler handler;

    public GraphQlRSocketController(GraphQlRSocketHandler handler) {
        this.handler = handler;
    }

    @MessageMapping("graphql")
    public Mono<Map<String, Object>> handle(Map<String, Object> payload) {
        return handler.handle(payload);
    }

    @MessageMapping("graphql")
    public Flux<Map<String, Object>> handleSubscription(Map<String, Object> payload) {
        return handler.handleSubscription(payload);
    }
}
~~~

Trong Spring Boot, route tương ứng có thể cấu hình bằng `spring.graphql.rsocket.mapping`. RSocket phù hợp với hệ thống cần giao tiếp message-oriented và reactive giữa các service hoặc giữa client với server. Nếu hệ thống chỉ cần request-response HTTP đơn giản, RSocket không tự động làm GraphQL query nhanh hơn; cần chọn theo yêu cầu kết nối và giao thức.

## 9. WebGraphQlHandler và interceptor chain

`WebGraphQlHandler` là lớp điều phối cho các web transport. HTTP và WebSocket handler không gọi resolver trực tiếp; chúng chuyển request vào `WebGraphQlHandler`. Handler chạy một chuỗi `WebGraphQlInterceptor`, sau đó gọi `ExecutionGraphQlService`.

`WebGraphQlInterceptor` có thể:

- Đọc thông tin HTTP request như header, URI hoặc principal.
- Bổ sung giá trị vào `ExecutionInput` và `GraphQLContext`.
- Thêm response header.
- Kiểm tra hoặc điều chỉnh `ExecutionResult`.
- Ghi log và đo thời gian request.

Ví dụ thêm correlation ID từ header vào GraphQL context:

~~~java
import org.springframework.graphql.server.WebGraphQlInterceptor;
import org.springframework.graphql.server.WebGraphQlRequest;
import org.springframework.graphql.server.WebGraphQlResponse;
import org.springframework.stereotype.Component;
import reactor.core.publisher.Mono;

@Component
public class CorrelationIdInterceptor implements WebGraphQlInterceptor {

    @Override
    public Mono<WebGraphQlResponse> intercept(
            WebGraphQlRequest request,
            Chain chain) {

        String correlationId =
                request.getHeaders().getFirst("X-Correlation-Id");

        if (correlationId != null && !correlationId.isBlank()) {
            request.configureExecutionInput((input, builder) ->
                    builder.graphQLContext(context ->
                            context.put("correlationId", correlationId)
                    ).build()
            );
        }

        return chain.next(request).doOnNext(response -> {
            if (correlationId != null && !correlationId.isBlank()) {
                response.getResponseHeaders()
                        .set("X-Correlation-Id", correlationId);
            }
        });
    }
}
~~~

Resolver có thể đọc giá trị này từ context:

~~~java
import org.springframework.graphql.data.method.annotation.ContextValue;
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.stereotype.Controller;

@Controller
public class TraceController {

    @QueryMapping
    public String traceId(@ContextValue("correlationId") String correlationId) {
        return correlationId;
    }
}
~~~

Ví dụ trên dùng header cho mục đích correlation. Không dùng một header do client tự gửi làm bằng chứng xác thực hoặc quyền truy cập tenant. Thông tin principal và quyền phải được xác thực ở Spring Security hoặc cơ chế bảo mật đáng tin cậy trước khi đưa vào GraphQL context.

Spring for GraphQL cũng có `HttpRequestHeaderInterceptor` để sao chép những HTTP header được chọn vào GraphQL context. Nếu chỉ cần truyền một số header, có thể dùng interceptor dựng sẵn thay vì tự viết.

## 10. Context và request metadata

Mỗi GraphQL operation có thể cần metadata như:

- Correlation ID hoặc trace ID.
- Locale của request.
- Thông tin principal đã được xác thực.
- Tenant hoặc phạm vi dữ liệu được phép truy cập.
- Feature flag hoặc request-scoped configuration.

`ExecutionGraphQlRequest` cung cấp dữ liệu để tạo `ExecutionInput`, bao gồm document, operation name, variables, extensions, locale và execution ID. Nó cũng cho phép tùy chỉnh `ExecutionInput` trước khi gọi GraphQL Java.

Dùng `GraphQLContext` cho dữ liệu cần truy cập từ DataFetcher, controller method, instrumentation hoặc batch loader. Với annotated controller, có thể nhận `GraphQLContext` trực tiếp hoặc dùng `@ContextValue` để đọc một giá trị theo key.

Context thuộc về từng request/execution. Không lưu principal, tenant hoặc request metadata vào field mutable của singleton controller, vì nhiều request có thể chạy đồng thời và làm rò rỉ dữ liệu giữa người dùng.

Với WebFlux, Spring for GraphQL hỗ trợ truyền Reactor Context từ pipeline transport đến reactive DataFetcher. Với Spring MVC, các DataFetcher có thể chạy trên thread khác thread xử lý HTTP ban đầu khi có xử lý bất đồng bộ; nếu cần truyền ThreadLocal tùy chỉnh, phải đăng ký cơ chế context propagation phù hợp, chẳng hạn Micrometer `ThreadLocalAccessor`.

## 11. Transport quyết định operation nào được phép chạy

Không phải transport nào cũng hỗ trợ mọi loại operation:

| Transport | Query | Mutation | Subscription |
| --- | --- | --- | --- |
| HTTP POST | Có | Có | Không stream trực tiếp |
| HTTP GET | Có | Không | Không |
| HTTP SSE | Không dùng cho operation một response | Không | Có |
| WebSocket | Có | Có | Có |
| RSocket | Request-response | Request-response | Request-stream |

Các giới hạn này là một phần của giao thức. Spring for GraphQL gắn danh sách operation type được phép vào execution request; trước khi thực thi, GraphQL Java kiểm tra operation có phù hợp transport hay không. Nếu không phù hợp, request bị từ chối với lỗi operation không được hỗ trợ.

Đừng cố thực hiện mutation qua GET. GET là safe method theo HTTP semantics và không được dùng cho operation có side effect. Tương tự, không gửi subscription qua HTTP POST thông thường rồi mong server giữ response mở thành stream; hãy chọn WebSocket hoặc SSE.

## 12. Execution bất đồng bộ và reactive return types

GraphQL thường cần fetch nhiều field lồng nhau. GraphQL Java dùng `AsyncExecutionStrategy` để cho phép các DataFetcher chạy đồng thời thay vì tuần tự khi có thể.

Spring for GraphQL hỗ trợ DataFetcher và controller method trả về:

- `CompletionStage` hoặc `CompletableFuture`.
- Reactor `Mono` hoặc `Flux`.
- Kotlin coroutine.
- `Callable` ở các method `@SchemaMapping` và `@BatchMapping` khi đã cấu hình Executor phù hợp.

Ví dụ resolver trả về `Mono`:

~~~java
@QueryMapping
public Mono<Book> book(@Argument String id) {
    return bookService.findById(id);
}
~~~

Trong execution thông thường, `Mono` được chuyển thành kết quả bất đồng bộ tương thích với GraphQL Java. `Flux` được tổng hợp thành danh sách cho field trả collection. Riêng subscription, publisher được giữ để phát nhiều kết quả theo thời gian.

Sự khác nhau giữa MVC và WebFlux:

- Spring MVC hỗ trợ asynchronous request execution; response có thể hoàn tất đồng bộ nếu operation đơn giản, hoặc bất đồng bộ khi có fetcher trả future/reactive type.
- Spring WebFlux dùng non-blocking I/O và Reactor pipeline. Với subscription stream, back pressure giúp điều tiết việc truyền dữ liệu.

Không gọi `block()` hoặc thực hiện I/O blocking lâu trên event-loop của WebFlux. Nếu phải gọi thư viện blocking, hãy đưa nó sang executor phù hợp. Reactive transport không tự biến một lời gọi blocking thành non-blocking.

## 13. Timeout và hủy request

GraphQL operation có thể tiêu thụ nhiều tài nguyên nếu query sâu, trả quá nhiều dữ liệu hoặc chờ dependency quá lâu. Với web transport, Spring for GraphQL cung cấp `TimeoutWebGraphQlInterceptor`.

Ví dụ cấu hình timeout 5 giây trong Spring Boot:

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

Khi timeout, interceptor gửi tín hiệu cancel lên chuỗi xử lý. Reactive DataFetcher có thể nhận tín hiệu hủy để dừng công việc đang chạy nếu nguồn dữ liệu hỗ trợ cancellation.

Timeout ở tầng GraphQL không thay thế timeout của HTTP client, database, HTTP client gọi service khác hoặc timeout riêng của WebSocket/SSE handler. Cần đặt giới hạn ở các dependency để một request bị hủy không tiếp tục giữ tài nguyên ở phía sau.

Với WebSocket, ngoài timeout request, cần quản lý thời gian sống của connection, số subscription đồng thời và tốc độ phát event. Một kết nối mở lâu không đồng nghĩa mỗi subscription nên chạy vô hạn.

## 14. Xử lý lỗi ở đúng tầng

Các loại lỗi khác nhau được phát sinh ở các giai đoạn khác nhau:

| Loại lỗi | Thời điểm | Cơ chế phù hợp |
| --- | --- | --- |
| Invalid JSON, thiếu credential, server không khả dụng | Transport trước GraphQL execution | HTTP/WebSocket/RSocket server và Spring Security |
| Parse, schema validation, input coercion | GraphQL engine trước khi gọi DataFetcher | Request-level handling; web interceptor có thể kiểm tra response |
| Exception trong DataFetcher/resolver | Khi thực thi field | `DataFetcherExceptionResolver` hoặc `@GraphQlExceptionHandler` |
| Publisher của subscription kết thúc bằng lỗi | Sau khi subscription đã bắt đầu stream | `SubscriptionExceptionResolver` và transport stream |

`DataFetcherExceptionResolver` chỉ xử lý exception phát sinh từ DataFetcher. Nó không xử lý lỗi parse hoặc validation của document vì lúc đó chưa có DataFetcher nào được gọi.

Với web transport, `WebGraphQlInterceptor` có thể kiểm tra `WebGraphQlResponse` sau khi `chain.next(request)` hoàn tất. Đây là nơi phù hợp nếu cần điều chỉnh request-level errors mà resolver không thể nhìn thấy.

Subscription có thêm một giai đoạn bất đồng bộ: DataFetcher trả về Publisher trước, rồi transport subscribe vào Publisher đó. Nếu Publisher phát error sau đó, `DataFetcherExceptionResolver` không còn ở trong luồng để xử lý; dùng `SubscriptionExceptionResolver` cho trường hợp này.

Tách rõ các tầng giúp tránh đặt mọi exception vào một handler tổng quát và trả cùng một response cho những lỗi có nguyên nhân khác nhau.

## 15. Tự cấu hình khi không dùng Spring Boot

Spring Boot tự tạo nhiều thành phần: GraphQlSource, ExecutionGraphQlService, BatchLoaderRegistry, web handler và endpoint. Nếu ứng dụng không dùng Boot, cần tự đăng ký các bean cần thiết.

Ví dụ phần execution service:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.graphql.ExecutionGraphQlService;
import org.springframework.graphql.execution.BatchLoaderRegistry;
import org.springframework.graphql.execution.DefaultBatchLoaderRegistry;
import org.springframework.graphql.execution.DefaultExecutionGraphQlService;
import org.springframework.graphql.execution.GraphQlSource;

@Configuration(proxyBeanMethods = false)
public class GraphQlExecutionConfiguration {

    @Bean
    BatchLoaderRegistry batchLoaderRegistry() {
        return new DefaultBatchLoaderRegistry();
    }

    @Bean
    ExecutionGraphQlService executionGraphQlService(
            GraphQlSource graphQlSource,
            BatchLoaderRegistry batchLoaderRegistry) {

        DefaultExecutionGraphQlService service =
                new DefaultExecutionGraphQlService(graphQlSource);

        service.addDataLoaderRegistrar(batchLoaderRegistry);
        return service;
    }
}
~~~

Sau đó tạo web handler:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.graphql.ExecutionGraphQlService;
import org.springframework.graphql.server.WebGraphQlHandler;
import org.springframework.graphql.server.WebGraphQlInterceptor;

@Configuration(proxyBeanMethods = false)
public class GraphQlWebConfiguration {

    @Bean
    WebGraphQlHandler webGraphQlHandler(
            ExecutionGraphQlService executionGraphQlService,
            WebGraphQlInterceptor interceptor) {

        return WebGraphQlHandler.builder(executionGraphQlService)
                .interceptor(interceptor)
                .build();
    }
}
~~~

`GraphQlSource` vẫn cần schema resources và runtime wiring phù hợp. Nếu dùng annotated controller, cần cấu hình `AnnotatedControllerConfigurer` làm `RuntimeWiringConfigurer` và đăng ký exception resolver tương ứng. Khi tự dựng toàn bộ stack, cũng phải tạo endpoint transport cụ thể, ví dụ HTTP RouterFunction hoặc WebSocket mapping.

Đây là phần cấu hình nâng cao. Với ứng dụng Spring Boot thông thường, nên dùng auto-configuration và chỉ tùy chỉnh qua bean/property khi có yêu cầu cụ thể.

## 16. Kiểm thử execution service và transport

Spring for GraphQL cung cấp `GraphQlTester` với API kiểm thử thống nhất. Có thể kiểm thử ở các mức khác nhau:

Thêm dependency `spring-graphql-test` trong test scope nếu dự án chưa có sẵn qua cấu hình dependency management:

~~~groovy
dependencies {
    testImplementation("org.springframework.graphql:spring-graphql-test")
}
~~~

| Tester | Phạm vi kiểm thử |
| --- | --- |
| `ExecutionGraphQlServiceTester` | Gọi trực tiếp execution service, không cần network |
| `WebGraphQlTester` | Kiểm thử server-side web handler và interceptor chain |
| `HttpGraphQlTester` | Gửi request qua HTTP, có thể dùng WebTestClient với server thật hoặc mock |
| `WebSocketGraphQlTester` | Kiểm thử protocol và connection WebSocket |
| `RSocketGraphQlTester` | Kiểm thử RSocket transport |

Ví dụ kiểm thử trực tiếp execution service:

~~~java
import org.springframework.graphql.test.tester.ExecutionGraphQlServiceTester;

ExecutionGraphQlServiceTester tester =
        ExecutionGraphQlServiceTester.create(executionGraphQlService);

tester.document("""
        query {
            greeting
        }
        """)
        .execute()
        .path("greeting")
        .entity(String.class)
        .isEqualTo("Hello");
~~~

Kiểu kiểm thử này nhanh và hữu ích để xác nhận schema, resolver và execution. Nó không kiểm tra HTTP route, JSON codec, CORS, WebSocket handshake hoặc cấu hình RSocket.

Khi kiểm thử transport, dùng tester tương ứng. Với HTTP, `HttpGraphQlTester` dùng `WebTestClient`. Có thể bind WebTestClient vào application context để không cần mở cổng thật, hoặc bind vào server đang chạy để kiểm thử end-to-end.

Với WebSocket và RSocket, nhớ đóng tester/connection sau test nếu tester cung cấp `stop()`. Đối với subscription, kiểm tra cả dữ liệu phát ra, việc client hủy subscription và hành vi khi publisher kết thúc bằng lỗi.

## 17. Chọn transport theo nhu cầu

| Nhu cầu | Lựa chọn phù hợp | Lý do |
| --- | --- | --- |
| Query/mutation từ browser hoặc ứng dụng thông thường | HTTP POST | Dễ tích hợp, một request một response |
| Query có thể cache và không chứa dữ liệu nhạy cảm | HTTP GET đã bật rõ ràng | Có thể dùng cache/proxy; chỉ cho operation an toàn |
| Theo dõi event server-to-client đơn giản | SSE | Một chiều, dùng HTTP và dễ tích hợp với EventSource |
| Subscription hai chiều, nhiều operation trên một connection | WebSocket | Connection lâu dài, hỗ trợ multiplex nhiều subscription |
| Giao tiếp message-oriented giữa các service hoặc client reactive | RSocket | Request-response và request-stream trên TCP/WebSocket |

Không có transport nào thay thế được việc thiết kế query hợp lý, phân trang, giới hạn độ sâu, giới hạn số lượng kết quả và tối ưu DataFetcher. Transport chỉ quyết định cách request/response đi qua mạng.

## 18. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| `/graphql` trả 404 | Thiếu transport starter hoặc endpoint path đã đổi | Kiểm tra starter MVC/WebFlux và `spring.graphql.http.path` |
| WebSocket handshake thất bại | Chưa bật `spring.graphql.websocket.path` hoặc thiếu WebSocket starter cho Servlet | Kiểm tra dependency và cấu hình endpoint |
| Subscription qua HTTP POST không phát stream | HTTP JSON handler trả một response | Chuyển sang WebSocket hoặc SSE |
| GET mutation bị từ chối | GET là safe method và không được chạy mutation | Dùng POST |
| Interceptor không được gọi | Bean không được phát hiện hoặc request không đi qua web handler mong muốn | Kiểm tra component scan và cấu hình transport |
| DataFetcherExceptionResolver không bắt parse error | Lỗi xảy ra trước khi DataFetcher được gọi | Xử lý request-level error qua interceptor phù hợp |
| Subscription kết thúc bằng lỗi không được chuẩn hóa | Lỗi phát sinh sau khi Publisher đã được trả về | Đăng ký SubscriptionExceptionResolver |
| Context bị null trong resolver | Giá trị chưa được thêm vào GraphQLContext hoặc key không khớp | Kiểm tra interceptor và `@ContextValue` |
| Request chậm dù dùng WebFlux | Có thao tác blocking trên event-loop hoặc dependency không có timeout | Chuyển blocking I/O sang executor và đặt timeout |
| WebSocket server dùng quá nhiều bộ nhớ | Quá nhiều connection/subscription hoặc message buffer lớn | Giới hạn connection, message size và subscription per session |
| Test service pass nhưng HTTP endpoint lỗi | Test bỏ qua transport layer | Bổ sung `HttpGraphQlTester` hoặc tester phù hợp |

## 19. Quy trình thiết kế server transport

Khi triển khai Spring for GraphQL server, có thể đi theo trình tự:

1. Chọn Spring MVC hoặc WebFlux dựa trên mô hình I/O của ứng dụng.
2. Thêm `spring-boot-starter-graphql` và starter transport cần thiết.
3. Đặt schema resources trong `classpath:graphql/**` hoặc cấu hình vị trí riêng.
4. Đăng ký controller và RuntimeWiringConfigurer để tạo DataFetcher.
5. Để Spring Boot cấu hình GraphQlSource và ExecutionGraphQlService nếu có thể.
6. Chọn HTTP cho query/mutation; bật WebSocket hoặc SSE nếu cần subscription.
7. Bổ sung interceptor để đưa metadata an toàn vào GraphQLContext.
8. Cấu hình authentication, authorization, CORS và CSRF theo transport.
9. Đặt timeout, giới hạn connection, message size và subscription count.
10. Kiểm thử trực tiếp execution service, sau đó kiểm thử transport thực tế.

## 20. Những điểm cần ghi nhớ

- Transport nhận và trả GraphQL request/response theo giao thức; execution service thực thi operation bằng GraphQL Java.
- `GraphQlSource` cung cấp schema và GraphQL runtime đã cấu hình.
- `DefaultExecutionGraphQlService` là implementation mặc định của `ExecutionGraphQlService`.
- HTTP POST phù hợp với query và mutation có một response; HTTP GET chỉ dành cho operation an toàn.
- SSE và WebSocket hỗ trợ subscription stream; RSocket dùng request-stream cho subscription.
- `WebGraphQlHandler` chạy `WebGraphQlInterceptor` chain trước execution service.
- Dùng GraphQLContext cho metadata theo request; không lưu request state trong field mutable của singleton controller.
- `DataFetcherExceptionResolver` xử lý lỗi trong field execution; request errors và subscription publisher errors cần cơ chế phù hợp riêng.
- WebFlux hỗ trợ non-blocking I/O và back pressure; tránh blocking trên event-loop.
- Kiểm thử `ExecutionGraphQlService` không thay thế kiểm thử HTTP, WebSocket hoặc RSocket transport.

Tách transport khỏi execution service giúp Spring for GraphQL hỗ trợ nhiều giao thức mà vẫn giữ chung schema, controller, DataLoader và logic nghiệp vụ. Khi chọn transport theo kiểu tương tác, cấu hình interceptor đúng tầng và kiểm thử cả execution lẫn network boundary, server sẽ dễ mở rộng và vận hành hơn.

## Tài liệu tham khảo

- [Spring for GraphQL — Server Transports](https://docs.spring.io/spring-graphql/reference/transports.html)
- [Spring for GraphQL — Request Execution](https://docs.spring.io/spring-graphql/reference/request-execution.html)
- [Spring for GraphQL — Standalone Setup](https://docs.spring.io/spring-graphql/reference/standalone-setup.html)
- [Spring for GraphQL — Testing](https://docs.spring.io/spring-graphql/reference/testing.html)
- [Spring Boot — Spring for GraphQL](https://docs.spring.io/spring-boot/reference/web/spring-graphql.html)

