# ServerWebExchange, ServerHttpRequest và ServerHttpResponse

## 1. Vì sao ba kiểu này quan trọng với Spring Cloud Gateway?

Trong **Spring WebFlux**, một HTTP request đi vào ứng dụng không được xử lý qua cặp `HttpServletRequest`/`HttpServletResponse` của Servlet API. WebFlux dùng các đối tượng HTTP phía server được thiết kế để kết hợp với luồng xử lý bất đồng bộ và reactive:

- **`ServerHttpRequest`** biểu diễn yêu cầu client gửi đến: method, URI, path, headers, cookies, query parameters và luồng body.
- **`ServerHttpResponse`** biểu diễn phản hồi server chuẩn bị trả: status, headers, cookies và cách ghi body.
- **`ServerWebExchange`** là ngữ cảnh của **một lượt trao đổi HTTP**, nối request, response và thông tin xử lý liên quan với nhau.

Trong chương **Nền tảng WebFlux** của **SPRING_CLOUD_GATEWAY**, hiểu ba kiểu này là điều kiện để viết gateway filter đúng cách. Spring Cloud Gateway dùng route predicate để chọn tuyến, filter chain để xác thực hoặc giới hạn lưu lượng, thay đổi đường dẫn/header, khám phá instance dịch vụ rồi chuyển tiếp request. Những thao tác đó đều cần đọc hoặc cập nhật dữ liệu trong exchange; các cơ chế circuit breaker, retry, TLS và quan sát request cũng được nối vào các giai đoạn tương ứng.

> **Phạm vi:** Bài này nói về **Spring Cloud Gateway Server WebFlux** (thường dùng Reactor Netty). Biến thể Gateway Server MVC dùng mô hình Servlet/MVC nên API và filter không hoàn toàn giống.

### Mục tiêu sau bài

Sau khi học, bạn có thể giải thích quan hệ giữa ba đối tượng, biết khi nào đọc hay thay đổi request/response, dùng `exchange.mutate()` và `request.mutate()` trong `GlobalFilter`, nhận ra thời điểm response được **commit**, đồng thời tránh những lỗi phổ biến với body reactive và header bảo mật.

## 2. Một exchange gắn request với response như thế nào?

Khi WebFlux tiếp nhận một yêu cầu, framework cung cấp một `ServerWebExchange` cho các thành phần xử lý. Exchange tồn tại trong phạm vi lượt xử lý đó, cho phép các filter cùng truy cập request hiện hành, response và attributes dùng để trao đổi metadata.

~~~mermaid
flowchart TD
    C["Client"] -->|"HTTP request"| W["WebFlux WebFilter chain"]
    W --> E["ServerWebExchange"]
    E --> Q["ServerHttpRequest<br/>method, path, headers, body"]
    E --> R["ServerHttpResponse<br/>status, headers, body writer"]
    E --> A["Exchange attributes<br/>route, URL đích, thông tin nội bộ"]
    E --> G["Gateway route matching<br/>và gateway filter chain"]
    G --> S["Backend microservice"]
    S -->|"HTTP response"| R
    R -->|"Commit và ghi response"| C
~~~

Sơ đồ minh họa **quan hệ dữ liệu**, không ngụ ý backend thao tác trực tiếp lên đối tượng response trong JVM của gateway: gateway nhận HTTP response từ backend rồi ghi dữ liệu tương ứng lên `ServerHttpResponse` của chính nó.

| Đối tượng | Trả lời câu hỏi | Cách lấy từ exchange | Đặc điểm |
| --- | --- | --- | --- |
| `ServerHttpRequest` | “Client vừa gửi gì?” | `exchange.getRequest()` | API đọc thông tin request; muốn đổi đường dẫn/header thì tạo request mới bằng builder/decorator. |
| `ServerHttpResponse` | “Server sẽ trả gì?” | `exchange.getResponse()` | Có thể thiết lập status/header, đăng ký xử lý trước commit và ghi body dạng reactive. |
| `ServerWebExchange` | “Toàn bộ lượt trao đổi đang diễn ra ra sao?” | Được truyền vào filter/handler | Chứa request, response, attributes, thông tin session/principal, và khả năng tạo exchange đã thay request/response. |

Luồng request và response cùng nằm trong **một exchange**, nhưng hai chiều xử lý thường chạy tại các thời điểm khác nhau: pre-filter xử lý trước lời gọi xuống dưới; post-filter xử lý sau khi chuỗi downstream hoàn tất.

## 3. ServerHttpRequest: đọc yêu cầu đến

`ServerHttpRequest` là giao diện WebFlux biểu diễn request server nhận được. Một số phương thức thường gặp:

| API | Giá trị hoặc ý nghĩa |
| --- | --- |
| `getMethod()` | HTTP method như `GET`, `POST`, `PUT` |
| `getURI()` | URI của request theo ngữ cảnh hiện tại |
| `getPath()` | `RequestPath`: đường dẫn đã được phân tích thành các thành phần |
| `getHeaders()` | Các HTTP request headers dưới dạng `HttpHeaders` |
| `getQueryParams()` | Tham số query dạng `MultiValueMap<String, String>` |
| `getCookies()` | Cookies gửi từ client |
| `getRemoteAddress()` | Địa chỉ của peer kết nối (có thể là reverse proxy) |
| `getBody()` | `Flux<DataBuffer>` chứa dữ liệu body theo luồng |
| `mutate()` | Tạo builder để biến đổi request mà không phải sửa trực tiếp đối tượng gốc |

Ví dụ đọc thông tin trong một gateway filter:

~~~java
ServerHttpRequest request = exchange.getRequest();

HttpMethod method = request.getMethod();
String path = request.getPath().value();
String clientRequestId = request.getHeaders().getFirst("X-Request-Id");
String expand = request.getQueryParams().getFirst("expand");
~~~

Đoạn trên chỉ **đọc metadata**. Nó không kích hoạt xử lý body và không tự gửi request đến backend.

### 3.1. Request được xem như bất biến

Không nên giả định có thể lấy `request.getHeaders()` rồi tùy ý sửa header trên request gốc. Để biến đổi thông tin HTTP, dùng builder:

~~~java
ServerHttpRequest updatedRequest = exchange.getRequest()
        .mutate()
        .path("/orders/42")
        .headers(headers -> headers.set("X-Edge-Source", "gateway"))
        .build();

ServerWebExchange updatedExchange = exchange.mutate()
        .request(updatedRequest)
        .build();

return chain.filter(updatedExchange);
~~~

Những filter ở phía sau `chain.filter(updatedExchange)` nhìn thấy request đã biến đổi. Các thành phần đã chạy trước đó **không tự chạy lại** và không tự nhận một request mới. Điều này đặc biệt quan trọng với **route predicates**: Spring Cloud Gateway thường chọn route bằng request hiện tại **trước** khi thực hiện các gateway filter như `StripPrefix`, `RewritePath`.

Trong ứng dụng thực tế, nếu chỉ cần sửa path/header thì ưu tiên filter có sẵn (`StripPrefix`, `RewritePath`, `SetRequestHeader`...) để cấu hình ngắn gọn và dễ kiểm soát thứ tự.

### 3.2. Path và URI có thể khác nhau theo thời điểm

Ví dụ client gọi:

~~~http
GET /api/orders/42?expand=items HTTP/1.1
Host: api.example.test
~~~

Nếu route áp dụng `StripPrefix=1`, path ở bước chuyển tiếp trở thành `/orders/42`, trong khi query `expand=items` vẫn được giữ. Filter chạy **trước** phép biến đổi có thể đọc path `/api/orders/42`; filter chạy **sau** có thể thấy path `/orders/42`. URI đích cuối cùng được gateway lưu trong attribute nội bộ và thường còn phụ thuộc vào kết quả service discovery/load balancing.

Không thể suy luận chính xác URL backend chỉ từ `getURI()` tại mọi thời điểm. Khi điều tra lỗi, cần phân biệt **URI client yêu cầu**, **request đã được filter biến đổi** và **URL backend thực sự nhận**.

### 3.3. Body là Publisher, không phải String sẵn có

`getBody()` trả về `Flux<DataBuffer>`. Body có thể đến qua nhiều buffer, được tiêu thụ bất đồng bộ và thường **không thể đọc tùy ý nhiều lần** như một chuỗi đã nằm trong bộ nhớ. Một filter đọc hết body rồi không phát lại cho chain có thể khiến backend nhận body rỗng hoặc request bị lỗi.

Vì vậy:

- Với routing, logging hoặc auth chỉ cần method/path/header, **không đọc body**.
- Khi buộc phải biến đổi JSON body, ưu tiên cơ chế `ModifyRequestBody` tương ứng với phiên bản Spring Cloud Gateway, hoặc dùng decorator/caching với xử lý `DataBuffer` đúng chuẩn.
- Tránh `block()`, `subscribe()` tự phát trong filter; chuỗi reactive cần được **trả về** cho framework đăng ký thực thi.
- Không nối toàn bộ body lớn thành `String` chỉ để log; dữ liệu lớn gây áp lực bộ nhớ, còn nội dung nhạy cảm có thể bị ghi lộ.
- Khi tự giữ, thay thế hoặc giải phóng `DataBuffer`, phải hiểu quy tắc sở hữu và release buffer; dùng sai có thể rò rỉ bộ nhớ, nhất là với Netty pooled buffers.

## 4. ServerHttpResponse: chuẩn bị, commit và ghi phản hồi

`ServerHttpResponse` đại diện cho phản hồi HTTP mà gateway gửi đến client. API điển hình:

| API | Mục đích |
| --- | --- |
| `setStatusCode(HttpStatusCode)` | Đặt HTTP status trước khi response được commit |
| `getStatusCode()` | Lấy status đang được thiết lập, có thể chưa có giá trị tường minh |
| `getHeaders()` | Đọc/cập nhật HTTP response headers trước commit |
| `addCookie(...)` | Đăng ký cookie phản hồi |
| `beforeCommit(Supplier<Mono<Void>>)` | Đăng ký thao tác sẽ chạy trước khi headers/status được ghi ra kết nối |
| `isCommitted()` | Kiểm tra response đã commit hay chưa |
| `setComplete()` | Hoàn tất response bất đồng bộ; thường dùng để chặn request với response không body |
| `writeWith(Publisher<? extends DataBuffer>)` | Ghi body từ luồng dữ liệu reactive |
| `bufferFactory()` | Cấp factory tạo `DataBuffer` khi cần tự ghi dữ liệu |

Ví dụ từ chối một yêu cầu đã vượt giới hạn lưu lượng, tại filter **đã xác định chắc điều kiện từ chối**:

~~~java
ServerHttpResponse response = exchange.getResponse();
response.setStatusCode(HttpStatus.TOO_MANY_REQUESTS);
return response.setComplete();
~~~

Ở đây filter **không gọi** `chain.filter(exchange)` nữa, nên request không tiếp tục qua chuỗi gateway filter còn lại hoặc đến backend. Điều này khác với backend tự trả 429: vị trí phát sinh status ảnh hưởng trực tiếp tới cách chẩn đoán.

### 4.1. “Commit” nghĩa là gì?

Trước khi commit, gateway có thể thiết lập status và headers. Khi response bắt đầu được gửi (hoặc khi gọi một thao tác làm response hoàn tất), framework áp dụng các callback `beforeCommit` rồi ghi metadata HTTP ra kết nối. **Sau thời điểm commit**, việc sửa status/header thường không còn hiệu lực hoặc không được phép.

Ví dụ đăng ký header trước khi response được ghi:

~~~java
exchange.getResponse().beforeCommit(() -> {
    exchange.getResponse().getHeaders()
            .set("X-Gateway", "spring-cloud-gateway");
    return Mono.empty();
});

return chain.filter(exchange);
~~~

Callback phải được đăng ký **trước** khi response bị commit; bản thân lời gọi `beforeCommit(...)` không có nghĩa body đã được gửi. Cũng không nên tự gọi `setComplete()` sau khi backend đã bắt đầu streaming response.

### 4.2. Response body vẫn là luồng reactive

Khi proxy trả tệp lớn hoặc Server-Sent Events (SSE), gateway có thể chuyển tiếp các buffer dần dần thay vì gom toàn bộ response vào bộ nhớ. Muốn xem hay biến đổi body trả về thường cần `ServerHttpResponseDecorator` hoặc filter chuyên dụng, phải tuân thủ backpressure và giải phóng buffer đúng cách. Thêm header bằng `beforeCommit` đơn giản và ít rủi ro hơn nhiều so với tự can thiệp vào body.

Nếu backend đã stream một phần dữ liệu rồi kết nối bị ngắt, gateway không thể lúc nào cũng đổi lại response thành JSON lỗi với status 500, vì HTTP status có thể đã được gửi. Đây là một lý do nên quan sát cả lỗi kết nối và trạng thái commit khi vận hành gateway.

## 5. ServerWebExchange: ngữ cảnh kết nối các bước

`ServerWebExchange` được truyền vào `WebFilter`, `GlobalFilter`, `GatewayFilter` và nhiều API WebFlux khác. Ngoài `getRequest()`/`getResponse()`, exchange còn có:

| Thành phần | Cách dùng |
| --- | --- |
| `getAttributes()`, `getAttribute(name)` | Lưu metadata **nội bộ theo request** giữa các bộ lọc, chẳng hạn ID xử lý hoặc route đã được chọn |
| `mutate()` | Tạo exchange decorator với request/response đã được thay thế |
| `getPrincipal()` | Trả về `Mono<Principal>`, nếu có danh tính từ cơ chế xác thực |
| `getSession()` | Truy cập `WebSession` bất đồng bộ khi cần |
| `getLocaleContext()` | Truy cập thông tin locale |
| `getFormData()`, `getMultipartData()` | API phân tích dữ liệu form/multipart khi thực sự cần; có tác động đến cách tiêu thụ body |

Ví dụ lưu metadata cho filter chạy sau:

~~~java
exchange.getAttributes().put("demo.startNanos", System.nanoTime());

Long started = exchange.getAttribute("demo.startNanos");
~~~

**Exchange attribute không phải HTTP header.** Attribute sống trong quá trình xử lý request bên trong gateway; backend và client sẽ không tự nhận được nó. Ngược lại, header là một phần thông điệp HTTP và có thể được chuyển tiếp qua mạng. Đừng đưa thông tin bí mật từ attributes sang header nếu không có yêu cầu và cơ chế bảo vệ phù hợp.

Spring Cloud Gateway cũng lưu dữ liệu định tuyến vào exchange, ví dụ:

~~~java
import java.net.URI;
import org.springframework.cloud.gateway.route.Route;
import static org.springframework.cloud.gateway.support.ServerWebExchangeUtils.GATEWAY_ROUTE_ATTR;
import static org.springframework.cloud.gateway.support.ServerWebExchangeUtils.GATEWAY_REQUEST_URL_ATTR;

Route selectedRoute = exchange.getAttribute(GATEWAY_ROUTE_ATTR);
URI targetUri = exchange.getAttribute(GATEWAY_REQUEST_URL_ATTR);
~~~

`GATEWAY_ROUTE_ATTR` có thể hiện diện sau khi route được chọn; `GATEWAY_REQUEST_URL_ATTR` thường chỉ có sau khi gateway xác định URL định tuyến. Trước các bước tương ứng, giá trị có thể là `null`. Đây là **metadata nội bộ**; không nên tự ghi đè các attribute đặc biệt của gateway nếu chưa hiểu tác động tới routing, load balancing và retry.

### Mutation không có nghĩa là tạo request mạng mới

Hai phép biến đổi dưới đây có vai trò khác nhau:

~~~java
ServerHttpRequest newRequest = exchange.getRequest()
        .mutate()
        .headers(h -> h.set("X-Trace-Source", "edge"))
        .build();

ServerWebExchange newExchange = exchange.mutate()
        .request(newRequest)
        .build();
~~~

`newRequest` và `newExchange` là những **đối tượng nhìn nhận mới** phục vụ phần chain phía sau, vẫn thuộc cùng lượt HTTP mà client gửi lên. Chúng không tự gọi backend; gateway chỉ chuyển tiếp khi execution đi tới routing filter tương ứng. Do đó, sau khi mutate vẫn phải chuyển `newExchange` cho `chain.filter(newExchange)`.

## 6. Áp dụng trong Spring Cloud Gateway

Xét gateway lắng nghe ở `http://localhost:8080` và một dịch vụ catalog ở `http://localhost:9001`. Cấu hình minh họa:

~~~yaml
spring:
  cloud:
    gateway:
      routes:
        - id: catalog-route
          uri: http://localhost:9001
          predicates:
            - Path=/api/catalog/**
          filters:
            - StripPrefix=1
            - AddRequestHeader=X-Gateway-Route, catalog-route
~~~

> Khóa `spring.cloud.gateway.routes` áp dụng cho nhiều bản Spring Cloud Gateway WebFlux đã phát hành; các dòng mới có thể sử dụng tiền tố `spring.cloud.gateway.server.webflux.routes`. Hãy chọn namespace phù hợp với phiên bản đang chạy. Ở đây URI tĩnh được dùng để tập trung vào request/exchange; khi chuyển sang `lb://catalog-service` thì gateway cần discovery và LoadBalancer để tìm instance.

Với request:

~~~http
GET /api/catalog/items/42?locale=vi HTTP/1.1
Host: localhost:8080
Accept: application/json
~~~

Luồng diễn ra như sau:

1. WebFlux tạo ngữ cảnh trao đổi qua `ServerWebExchange`, gắn `ServerHttpRequest` chứa path ban đầu `/api/catalog/items/42`.
2. `RoutePredicateHandlerMapping` chọn `catalog-route` vì `Path=/api/catalog/**` khớp; route được lưu vào exchange attribute.
3. `FilteringWebHandler` tổ chức các `GlobalFilter` và `GatewayFilter` theo thứ tự. `StripPrefix=1` tạo request có path `/catalog/items/42`; `AddRequestHeader` thêm `X-Gateway-Route: catalog-route`.
4. Gateway xây dựng URI đích và routing filter gửi request HTTP tương ứng tới `http://localhost:9001/catalog/items/42?locale=vi`.
5. Service trả status, headers, body; gateway ghi thông tin đó lên `ServerHttpResponse` cho client, đồng thời thực thi post-filter phù hợp.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant W as WebFlux
    participant F as Gateway filters
    participant B as Catalog service
    C->>W: GET /api/catalog/items/42?locale=vi
    W->>F: ServerWebExchange(request, response)
    F->>F: Path predicate match
    F->>F: StripPrefix và AddRequestHeader
    F->>B: GET /catalog/items/42?locale=vi
    B-->>F: 200 + JSON
    F->>W: Post-filter, xử lý response
    W-->>C: HTTP 200 + JSON
~~~

Đặc biệt, `ServerWebExchange` thuộc về xử lý HTTP **tại gateway**. Backend có request/response riêng trong ứng dụng của nó, không dùng chung object Java với gateway.

## 7. Ví dụ hoàn chỉnh: GlobalFilter gắn request ID

Filter sau minh họa ba đối tượng trong một luồng: lấy request từ exchange, tạo request có header mới, đăng ký callback cập nhật response, rồi gọi chain với exchange đã thay request. Request ID được tạo **tại gateway** để dễ liên kết log giữa các bước, không mặc nhiên tin vào header do client tự gửi.

~~~java
package example.gateway;

import java.util.UUID;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.cloud.gateway.filter.GatewayFilterChain;
import org.springframework.cloud.gateway.filter.GlobalFilter;
import org.springframework.core.Ordered;
import org.springframework.http.server.reactive.ServerHttpRequest;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

@Component
public class RequestIdFilter implements GlobalFilter, Ordered {
    private static final Logger log =
            LoggerFactory.getLogger(RequestIdFilter.class);

    @Override
    public int getOrder() {
        return -100;
    }

    @Override
    public Mono<Void> filter(ServerWebExchange exchange,
                             GatewayFilterChain chain) {
        String requestId = UUID.randomUUID().toString();
        long started = System.nanoTime();

        // Attribute: chỉ dùng trong quá trình xử lý nội bộ.
        exchange.getAttributes().put("demo.requestId", requestId);

        // Request: tạo bản biến đổi để downstream nhìn thấy header mới.
        ServerHttpRequest changedRequest = exchange.getRequest()
                .mutate()
                .headers(headers -> {
                    // Không để client giả mạo header danh tính do hệ thống tin cậy cấp.
                    headers.remove("X-Trusted-User");
                    headers.set("X-Request-Id", requestId);
                })
                .build();

        // Response: đặt header trước khi response commit.
        exchange.getResponse().beforeCommit(() -> {
            exchange.getResponse().getHeaders()
                    .set("X-Request-Id", requestId);
            return Mono.empty();
        });

        ServerWebExchange changedExchange = exchange.mutate()
                .request(changedRequest)
                .build();

        // Trả về Mono, không tự subscribe/block.
        return chain.filter(changedExchange)
                .doFinally(signal -> {
                    long durationMs =
                            (System.nanoTime() - started) / 1_000_000;
                    log.info("requestId={} method={} path={} status={} " +
                                    "durationMs={} signal={}",
                            requestId,
                            exchange.getRequest().getMethod(),
                            exchange.getRequest().getPath().value(),
                            exchange.getResponse().getStatusCode(),
                            durationMs,
                            signal);
                });
    }
}
~~~

Các điểm cần chú ý:

- **`getOrder() = -100`** chỉ là ví dụ thứ tự. Filter có order nhỏ thường chạy logic **pre** sớm hơn và phần sau chain muộn hơn filter có order lớn; kết quả còn phụ thuộc các filter khác đang cấu hình.
- `exchange.getRequest()` trong phần log dùng request ban đầu, còn `changedExchange.getRequest()` đi tiếp trong chain có header `X-Request-Id`. Điều đó giúp tách thông tin client gửi ban đầu và thông tin gateway thêm vào.
- `beforeCommit` giúp đặt header ngay trước khi response commit, kể cả khi backend trả lỗi; nếu một thành phần hoàn tất request **trước khi filter này được gọi** thì callback không được đăng ký.
- `doFinally` chạy khi publisher hoàn tất, lỗi hoặc bị hủy, nên phù hợp để ghi thời gian quan sát. Nó không có nghĩa backend luôn đã trả response đầy đủ.
- Filter minh họa chỉ **loại bỏ header `X-Trusted-User` do client gửi**, không gán một danh tính đã xác minh. Việc xác thực/phân quyền thực tế cần cơ chế Spring Security và chính sách rõ ràng.
- Request ID ở ví dụ khác với distributed trace ID. Trong hệ thống nhiều service nên dùng thêm Micrometer Tracing và chuẩn W3C `traceparent` để liên kết đầy đủ các chặng.

### Tại sao không sửa request trực tiếp?

Trong WebFlux, request có thể được bọc bằng decorator; việc dùng builder rồi truyền exchange mới là cơ chế được framework hỗ trợ để phần xử lý tiếp theo thấy thay đổi. Còn `ServerHttpResponse` có các phương thức ghi status, headers, cookie và body trước khi commit nên việc cập nhật response có mô hình khác request. **Đừng đánh đồng tính bất biến của request với trạng thái commit của response.**

## 8. Các tình huống dễ nhầm khi viết filter

| Tình huống | Cách hiểu đúng / cách xử lý |
| --- | --- |
| Sửa request header bằng `request.getHeaders().set(...)` | Có thể gặp headers chỉ đọc hoặc tạo thay đổi không nằm trong contract cần dùng. Hãy dùng `request.mutate().headers(...)` và truyền exchange mới vào chain. |
| Tạo request mới nhưng gọi `chain.filter(exchange)` | Chain tiếp tục nhận exchange cũ nên thay đổi không đến downstream. Gọi `chain.filter(updatedExchange)`. |
| Đọc body để log rồi chuyển tiếp body “như cũ” | Body có thể đã được tiêu thụ, dẫn đến request downstream rỗng/lỗi. Dùng cơ chế cache/decorator hoặc filter chuyên dụng nếu thật sự cần. |
| Gọi `subscribe()` bên trong filter | Tạo một subscription tách rời khỏi lifecycle gateway, dễ gây race, lỗi không được quản lý hoặc gửi response sai. Trả về `Mono<Void>` của chain. |
| Gọi `block()` để lấy principal, body hay service response | Có thể chặn event loop của Netty và làm giảm thông lượng. Phối hợp bằng `flatMap`, `then`, `map` hoặc operator reactive phù hợp. |
| Sửa status/header trong post-filter khi response đã commit | Thay đổi có thể bị từ chối hoặc không có tác dụng. Đặt sớm hoặc đăng ký `beforeCommit` đúng thời điểm. |
| Đọc `getAttribute(GATEWAY_REQUEST_URL_ATTR)` từ filter chạy rất sớm | Attribute có thể chưa được thiết lập. Kiểm tra `null` và hiểu thứ tự router/load balancer. |
| Lấy `getRemoteAddress()` làm IP gốc tuyệt đối | Có thể chỉ là địa chỉ proxy gần gateway. Xử lý `Forwarded`/`X-Forwarded-*` theo danh sách proxy tin cậy. |
| Cho rằng `GlobalFilter` chạy với mọi HTTP request vào server | Nó nằm trong chuỗi gateway filter của route được chọn. Request bị chặn bởi WebFlux `WebFilter` hoặc không khớp route có thể không chạy `GlobalFilter`. |

### WebFilter và GlobalFilter khác nhau thế nào?

`WebFilter` là thành phần của **WebFlux** và chạy quanh việc chọn handler; các kiểm tra Spring Security thường diễn ra ở đây. `GlobalFilter` là thành phần của **Spring Cloud Gateway**, được thực thi khi request đã được mapping tới gateway handler/filter chain. Nếu token bị từ chối ngay trong security `WebFilter`, một `GlobalFilter` ghi log có thể không quan sát được request đó. Muốn có số liệu đầy đủ tại cổng vào, cần đặt công cụ đo tại lớp phù hợp và kết hợp log từ reverse proxy/HTTP server nếu cần.

## 9. Tự kiểm chứng bằng HTTP client và log

Chuẩn bị gateway ở `localhost:8080` với route catalog ở mục 6 và một backend trả JSON khi nhận `GET /catalog/items/42` tại `localhost:9001`. Khi ứng dụng có `RequestIdFilter` ở mục 7, chạy:

~~~bash
curl -i "http://localhost:8080/api/catalog/items/42?locale=vi"
~~~

Quan sát:

1. Backend nhận path `/catalog/items/42`, query `locale=vi` và header `X-Gateway-Route: catalog-route` do route filter thêm.
2. Backend cũng nhận `X-Request-Id` do `RequestIdFilter` thêm. Response gửi cho client có `X-Request-Id` cùng giá trị khi filter chạy và response commit bình thường.
3. Log của filter ghi method, path ban đầu, status và thời gian xử lý. Path ghi ở ví dụ là `/api/catalog/items/42` vì lấy từ exchange ban đầu.

Thử thêm:

~~~bash
# Client thử tự gửi request ID và header giả mạo:
curl -i "http://localhost:8080/api/catalog/items/42" \
  -H "X-Request-Id: fake-from-client" \
  -H "X-Trusted-User: admin"

# Nếu không có route khác, path này sẽ không khớp route catalog:
curl -i "http://localhost:8080/api/orders/42"
~~~

Trong request đầu, gateway thay request ID bằng ID mới và loại header `X-Trusted-User` trước khi chuyển đến backend. Với request sau, nếu không có route/handler khác, client thường nhận `404` và `GlobalFilter` có thể không chạy. Khi thay backend tĩnh bằng `lb://catalog-service`, thứ tự xử lý thêm bước chọn instance dựa vào service discovery/load balancing.

Để luyện tư duy chẩn đoán, so sánh ba tình huống:

- **404 tại gateway:** route predicate không khớp, không có request nào đến backend.
- **404 từ backend:** route khớp và đã forward nhưng path sau `StripPrefix`/`RewritePath` không đúng endpoint backend.
- **503 khi dùng `lb://`:** Gateway có thể không tìm được instance phù hợp của service ID (mặc định là 503 với WebFlux LoadBalancer, có cấu hình cho phép trả 404); backend có thể chưa nhận request.

Các phân biệt này đều bắt đầu từ việc biết **exchange có request nào**, **request được biến đổi lúc nào** và **response được tạo tại đâu**.

## 10. Checklist áp dụng thực tế

Trước khi đưa một gateway filter vào hệ thống microservices, tự kiểm tra:

1. Filter cần **đọc** request, **biến đổi** request hay **thay đổi** response? Chọn đúng API và thời điểm xử lý.
2. Nếu biến đổi request, đã truyền **exchange mới** cho downstream chưa? Predicate chọn route có chạy trước phép biến đổi không?
3. Có đọc hoặc cache body không? Đã xem xét streaming, dung lượng lớn, backpressure và vòng đời `DataBuffer` chưa?
4. Response có thể đã **commit** trước khi đặt status/header không? Có dùng `beforeCommit` khi phù hợp?
5. Nếu filter chặn request, đã hoàn tất response và dừng chain đúng cách chưa?
6. Metadata cần chia sẻ là **exchange attribute nội bộ** hay **HTTP header** để gửi sang service? Header đó có thể bị client giả mạo không?
7. Trên thực tế, request có thể bị chặn tại TLS, WebFlux security, rate limiter, circuit breaker, timeout hoặc discovery trước khi backend xử lý. Có log/metrics/trace đủ để phân biệt các điểm này không?

**Ghi nhớ:** `ServerHttpRequest` cho biết yêu cầu đang được xử lý; `ServerHttpResponse` quản lý phản hồi và thời điểm commit; `ServerWebExchange` nối chúng với dữ liệu và vòng đời của một request. Viết filter đúng ba khái niệm này giúp định tuyến, xác thực, rate limiting, retry, circuit breaker, TLS và observability trong **Spring Cloud Gateway** hoạt động dễ kiểm soát hơn.
