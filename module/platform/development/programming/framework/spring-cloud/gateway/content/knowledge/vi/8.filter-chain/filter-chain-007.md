# Thao tác trước khi response được commit trong Spring Cloud Gateway

Trong **SPRING_CLOUD_GATEWAY**, nhiều bộ lọc cần sửa **HTTP response** trước khi gửi về client: thêm header truy vết, đặt chính sách cache, loại header không mong muốn, gắn thông tin phiên bản hoặc chuẩn hóa thông báo lỗi. Thời điểm thực hiện rất quan trọng. Khi response đã **commit**, status và headers về cơ bản đã được chốt để gửi qua kết nối; một thao tác sửa chúng trong filter chạy quá muộn có thể không có hiệu lực hoặc gây lỗi.

Bài thuộc chương **Chuỗi bộ lọc** và tập trung vào cơ chế **`ServerHttpResponse.beforeCommit(...)`** trong Spring WebFlux, mối quan hệ với `GlobalFilter`/`GatewayFilter`, thứ tự xử lý trước–sau (`pre`/`post`), phản hồi streaming và cách kiểm thử. Đây là nền tảng khi triển khai một cổng vào microservices sử dụng route predicate, filter chain, biến đổi path/header, khám phá dịch vụ, xác thực, rate limiting, circuit breaker, retry, TLS và quan sát request.

> **Phạm vi:** Phần Java sử dụng API reactive của **Spring Cloud Gateway Server WebFlux** và **Spring Framework WebFlux**, minh họa cho những phiên bản có các interface `GlobalFilter`, `GatewayFilterChain`, `ServerWebExchange`, `ServerHttpResponse`. **Gateway Server MVC** dùng Servlet stack và có API/vòng đời response khác; không sao chép nguyên lớp `GlobalFilter` WebFlux sang ứng dụng MVC. Tên starter/namespace YAML phải được đối chiếu với dòng Gateway đang dùng.

## 1. Response được commit nghĩa là gì?

HTTP response có ba nhóm thông tin cần phân biệt:

| Thành phần | Ví dụ | Khi nào phải quyết định? |
|---|---|---|
| **Status** | `200 OK`, `401 Unauthorized`, `429 Too Many Requests` | Trước khi response commit |
| **Headers và cookies** | `Cache-Control`, `X-Request-Id`, `Set-Cookie` | Trước khi response commit |
| **Body** | JSON, HTML, byte stream, Server-Sent Events | Được ghi theo cơ chế response; có thể bắt đầu làm response commit |

**Commit** là bước đưa trạng thái response vào quá trình ghi ra mạng, trong đó framework áp dụng status/headers/cookies và bắt đầu hoặc hoàn tất việc gửi dữ liệu. Sau điểm commit, những thông tin ở phần đầu response không thể được thay đổi như khi chưa gửi.

Một số tình huống làm response bước vào quá trình commit:

- Handler hoặc filter gọi `response.setComplete()` để kết thúc response, kể cả khi không có body.
- Framework thực hiện `response.writeWith(...)` hoặc `writeAndFlushWith(...)` để ghi body.
- Bộ lọc routing/response của Gateway chuyển body từ downstream về client.
- Một thành phần gửi lỗi, redirect hoặc response rỗng và kết thúc quá trình xử lý.

`isCommitted()` của `ServerHttpResponse` giúp quan sát trạng thái hiện tại, nhưng **không phải cơ chế đồng bộ an toàn để đọc `false` rồi chắc chắn được phép sửa header sau đó**. Khi quá trình commit diễn ra bất đồng bộ, trạng thái có thể đổi giữa hai thao tác. Cách phù hợp là **đăng ký hành động trước commit từ sớm**, hoặc hoàn tất thay đổi ngay trước khi bắt đầu ghi response nếu bạn đang kiểm soát chính bước đó.

### Ba thời điểm khác nhau

~~~mermaid
sequenceDiagram
    participant C as Client
    participant G as GlobalFilter / GatewayFilter
    participant D as Downstream
    participant R as ServerHttpResponse
    C->>G: Request
    G->>R: Đăng ký beforeCommit (trước khi ghi)
    G->>D: Forward request
    D-->>G: Status, headers, body
    G->>R: Gửi response qua writeWith / setComplete
    Note over R: Bắt đầu commit
    R->>R: Chạy callbacks beforeCommit
    R-->>C: Status + headers + body
    Note over R: Sau commit: không còn thời điểm sửa header an toàn
~~~

Sơ đồ lược giản: trên thực tế Netty routing, Netty write response filter, Reactor và các filter khác phối hợp thực hiện. Nội dung chính cần nhớ là **`beforeCommit` chạy trong quá trình commit, trước khi framework áp dụng các thay đổi đầu response**.

## 2. Pre-filter, post-filter và beforeCommit không đồng nghĩa

Ở Gateway Server WebFlux, sau khi route match, `FilteringWebHandler` kết hợp `GlobalFilter` với `GatewayFilter` của route và sắp xếp chúng theo order. Thông thường:

- **Pre**: phần code trước `chain.filter(exchange)` chạy khi request đi vào chuỗi filter.
- **Post**: thao tác reactive được xâu vào sau `chain.filter(exchange)` chạy khi phần downstream của chain phát tín hiệu hoàn thành tương ứng.
- **beforeCommit**: callback đăng ký lên **response**, được gọi khi response thực sự bước vào commit, nếu đăng ký kịp thời và commit có xảy ra.

Ví dụ về cách nhìn một filter:

~~~java
@Override
public Mono<Void> filter(ServerWebExchange exchange, GatewayFilterChain chain) {
    // Pre: nhận request, có thể đăng ký beforeCommit tại đây.
    return chain.filter(exchange)
        .then(Mono.fromRunnable(() -> {
            // Post theo tín hiệu hoàn thành của chain.
            // KHÔNG mặc định rằng response còn chưa commit.
        }));
}
~~~

Phần `then(...)` **không bảo đảm** vẫn có thể sửa HTTP headers. Trong Gateway WebFlux, filter viết response có thể chạy ở giai đoạn post của một filter khác. Tùy order, lúc Mono `then` của bạn được thực thi, bytes đầu response có thể đã gửi.

~~~mermaid
flowchart TD
    A["Pre-filter: đăng ký beforeCommit"] --> B["chain.filter(exchange)"]
    B --> C["Routing đến downstream"]
    C --> D["Chuẩn bị ghi response"]
    D --> E["ServerHttpResponse bắt đầu commit"]
    E --> F["Thực thi callbacks beforeCommit"]
    F --> G["Áp dụng status, headers, cookies"]
    G --> H["Ghi response về client"]
    H --> I["Một số post-filter có thể chạy sau khi response đã commit"]
~~~

**Thứ tự route** (`Route.order`) chỉ ảnh hưởng việc chọn route. **Thứ tự filter** (`Ordered`/wrapped filter order) quyết định vị trí chạy trong chain; nó không thay thế cơ chế `beforeCommit` khi cần tác động đúng tại thời điểm commit.

## 3. API `ServerHttpResponse.beforeCommit`

Spring WebFlux cung cấp API theo ý nghĩa sau:

~~~java
void beforeCommit(Supplier<? extends Mono<Void>> action);
~~~

Để sử dụng, lấy response từ `ServerWebExchange`:

~~~java
ServerHttpResponse response = exchange.getResponse();

response.beforeCommit(() -> Mono.defer(() -> {
    response.getHeaders().set("X-Edge-Processed", "true");
    return Mono.empty();
}));
~~~

**Ba điểm quan trọng:**

1. **Đăng ký sớm:** gọi `beforeCommit(...)` trong phần pre của filter, trước khi gọi `chain.filter(exchange)`, để callback có cơ hội được đăng ký trước bất kỳ thành phần nào commit response.
2. **Trì hoãn side effect:** trả về `Mono<Void>` được tạo theo cách **deferred** như `Mono.defer(...)`. Việc sửa header nằm trong lúc Mono thực sự được subscribe khi commit; không sửa header ngay lúc tạo callback nếu mục tiêu là thao tác sát commit.
3. **Hoàn tất bất đồng bộ:** callback có thể trả về một `Mono<Void>` để framework đợi hoàn thành trước khi ghi status/headers. Tránh `block()`, I/O chặn luồng, tính toán nặng, truy vấn remote không cần thiết hoặc callback có thể không bao giờ hoàn thành.

### Phân biệt code chạy ngay và code chạy lúc commit

**Ví dụ thiếu trì hoãn:**

~~~java
// Không dùng cấu trúc này nếu cần đảm bảo side effect xảy ra khi commit.
response.beforeCommit(() -> {
    response.getHeaders().set("X-Edge-Processed", "true");
    return Mono.empty();
});
~~~

Dù phần lambda này được gọi khi commit, nguyên tắc làm việc với Reactor là trả về **một publisher deferred** cho hành động bất đồng bộ, phù hợp với hợp đồng `beforeCommit` và tránh nhầm lẫn khi mở rộng thêm xử lý. Chọn dạng `Mono.defer` trong ví dụ chuẩn:

~~~java
response.beforeCommit(() -> Mono.defer(() -> {
    response.getHeaders().set("X-Edge-Processed", "true");
    return Mono.empty();
}));
~~~

Sự khác biệt đáng chú ý hơn xuất hiện nếu tạo `Mono` nhưng thực hiện side effect **trước** thời điểm subscribe:

~~~java
// Sai kỳ vọng: sửa header ở pre-filter ngay lập tức.
response.getHeaders().set("X-Edge-Processed", "true");
response.beforeCommit(() -> Mono.empty());
~~~

Đặt header sớm có thể **hoàn toàn hợp lệ** nếu bạn cố ý gắn giá trị cố định ngay khi nhận request. Nhưng cách đó không kiểm tra trạng thái cuối cùng của downstream response hoặc các filter khác và dễ bị filter chạy sau ghi đè. `beforeCommit` thích hợp khi cần quyết định gần lúc commit.

### `beforeCommit` có cam kết chạy trong mọi request không?

Không. Callback chỉ có ý nghĩa với **response mà nó đã được đăng ký** và **đi vào quá trình commit**. Những trường hợp cần chú ý:

- Nếu request không match một route Gateway, `GlobalFilter` của Gateway thường không được gọi; do đó callback đăng ký bên trong nó cũng không xuất hiện.
- Nếu thành phần khác đã commit response **trước khi bạn đăng ký**, callback không thể quay ngược thời gian để sửa header đã gửi.
- Nếu request bị hủy, gặp lỗi trước khi đường đi commit hoàn tất hoặc xảy ra trường hợp kết nối ngắt, không nên suy đoán callback luôn chạy như một hook dọn dẹp tổng quát.
- Callback không chứng minh body đã chuyển hết tới client; **commit đầu response** khác với **hoàn tất ghi body**.

Muốn đo kết thúc request, dùng cơ chế metrics/tracing hoặc operator quan sát tín hiệu terminal thích hợp, thay vì coi `beforeCommit` là sự kiện “response đã gửi thành công”.

## 4. Ví dụ hoàn chỉnh: GlobalFilter thêm header trước commit

Giả sử Gateway cần gắn header `X-Edge-Processed: true` cho **những response đi qua Gateway route**, kể cả khi backend trả HTTP 4xx/5xx, miễn request đã đi qua filter và response đi đến commit.

~~~java
package example.gateway;

import org.springframework.cloud.gateway.filter.GatewayFilterChain;
import org.springframework.cloud.gateway.filter.GlobalFilter;
import org.springframework.core.Ordered;
import org.springframework.http.server.reactive.ServerHttpResponse;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

@Component
public class EdgeResponseHeaderFilter implements GlobalFilter, Ordered {

    @Override
    public Mono<Void> filter(ServerWebExchange exchange,
                             GatewayFilterChain chain) {
        ServerHttpResponse response = exchange.getResponse();

        // Pre: đăng ký callback trước khi cho chain tiếp tục.
        response.beforeCommit(() -> Mono.defer(() -> {
            response.getHeaders().set("X-Edge-Processed", "true");
            return Mono.empty();
        }));

        return chain.filter(exchange);
    }

    @Override
    public int getOrder() {
        return -100;
    }
}
~~~

Điểm cần đọc trong đoạn code:

- `GlobalFilter` tham gia vào pipeline của Gateway Server WebFlux **sau khi chọn route**. Đây không phải Spring Security `WebFilter`.
- `beforeCommit` được **đăng ký ở nhánh pre**, không phụ thuộc vào việc post-filter của lớp này chạy trước hay sau bộ lọc ghi response.
- `Mono.defer` đặt thao tác sửa header vào thời điểm publisher được chạy trong quá trình commit.
- `getHeaders().set(...)` chọn **một giá trị**; `add(...)` sẽ thêm giá trị và có thể tạo header lặp. Chọn đúng semantics với nghiệp vụ.
- `getOrder() = -100` chỉ là một ví dụ giúp filter được gọi sớm trong nhiều cấu hình; không phải “số chuẩn” bắt buộc. Order và sự có mặt của các filter phải đối chiếu thực tế. **Đăng ký trước commit** mới là yếu tố chính.
- Không thêm xử lý blocking vào callback, kể cả khi cần kiểm tra trạng thái service, tìm token hoặc gọi API bên ngoài.

Nếu Gateway còn một filter khác **đặt lại** cùng header trong một callback trước commit, kết quả phụ thuộc thứ tự callbacks và cơ chế header. Vì vậy, tránh để nhiều filter tranh quyền sở hữu cùng một header; đặt quy ước ai quản lý `X-Edge-Processed` hoặc `Cache-Control`.

### Route thử nghiệm cho GlobalFilter

Một route WebFlux minh họa (một số dòng Gateway 4.x):

~~~yaml
spring:
  cloud:
    gateway:
      routes:
        - id: orders
          uri: http://localhost:9090
          predicates:
            - Path=/api/orders/**
          filters:
            - StripPrefix=1
~~~

Giả sử ứng dụng Gateway chạy ở `localhost:8080`, backend echo chạy ở `localhost:9090` và phục vụ `GET /orders/42`.

~~~bash
curl -i http://localhost:8080/api/orders/42
~~~

Khi route khớp và request được xử lý thành công, response client nhận dự kiến có:

~~~http
HTTP/1.1 200 OK
X-Edge-Processed: true
Content-Type: application/json
~~~

Đây là **minh họa phần header**, không phải response đầy đủ. Status/body phụ thuộc backend và các filter khác. Nếu request không match route nào, `GlobalFilter` này có thể không chạy và header `X-Edge-Processed` có thể không xuất hiện.

## 5. Khi nào dùng built-in GatewayFilter thay vì code Java?

Không phải mọi thao tác cần `beforeCommit` tùy biến. Khi chỉ cần chỉnh header theo một cấu hình đơn giản, nên cân nhắc **GatewayFilter factory có sẵn** trong đúng phiên bản.

Ví dụ:

~~~yaml
spring:
  cloud:
    gateway:
      routes:
        - id: catalog
          uri: http://localhost:9091
          predicates:
            - Path=/api/catalog/**
          filters:
            - SetResponseHeader=X-Edge-Service,catalog
            - AddResponseHeader=X-Processed-By,gateway
~~~

| Factory | Tác dụng | Cần lưu ý |
|---|---|---|
| `AddResponseHeader` | Bổ sung giá trị vào response header | Có thể tạo nhiều giá trị cùng tên |
| `SetResponseHeader` | Đặt/thay thế giá trị response header | Có thể ghi đè giá trị từ downstream |
| `RemoveResponseHeader` | Loại header theo tên | Tùy filter order, header có thể lại được thêm bởi thành phần khác |
| `DedupeResponseHeader` | Loại bớt header lặp theo chiến lược được hỗ trợ | Hữu ích khi Gateway và downstream đều thêm CORS header |

Bộ lọc built-in có API/cách hoạt động riêng để thay đổi response trong pipeline. **Không tự động kết luận tất cả chúng được hiện thực bằng `beforeCommit`**; điều quan trọng là chọn factory đúng phiên bản và xác minh header ở response thật.

Nên viết `GlobalFilter` hoặc `GatewayFilter` tùy biến khi cần logic theo ngữ cảnh: chọn header dựa vào route ID, status downstream, môi trường thử nghiệm, metadata hoặc một chính sách không được factory có sẵn hỗ trợ.

## 6. Trường hợp thay đổi theo status downstream

Giả sử cần gắn header `Cache-Control: no-store` cho response lỗi, tránh cache một payload lỗi của backend. Có thể đọc status **gần thời điểm commit** nếu response chưa được ghi:

~~~java
import org.springframework.http.HttpStatusCode;
import org.springframework.http.server.reactive.ServerHttpResponse;
import reactor.core.publisher.Mono;

// Đoạn mã đặt bên trong filter, trước chain.filter(exchange).
ServerHttpResponse response = exchange.getResponse();

response.beforeCommit(() -> Mono.defer(() -> {
    HttpStatusCode status = response.getStatusCode();
    if (status != null && status.isError()) {
        response.getHeaders().set("Cache-Control", "no-store");
    }
    return Mono.empty();
}));

return chain.filter(exchange);
~~~

Ví dụ này minh họa tác dụng của **thời điểm**: status có thể chưa được xác định tại lúc pre-filter, nhưng thường đã được thiết lập trước khi response commit. Dù vậy, status do gateway tạo, bộ lọc lỗi, fallback hay downstream đều có thể thay đổi theo cấu hình; hãy test cả các nhánh lỗi thật.

**Giới hạn về chính sách cache:** `Cache-Control: no-store` là chỉ thị HTTP với hành vi tùy cache/client; nó không bảo đảm dữ liệu nhạy cảm không bị lưu ở mọi lớp. Nếu áp dụng một chính sách bảo mật bắt buộc cho tất cả response, hãy bảo đảm callback được đăng ký trên **mọi đường đi liên quan**; một `GlobalFilter` chỉ chạy sau khi route match không đủ để bao phủ mọi response từ ứng dụng.

### Tránh làm rối quá trình xác định status

Nếu muốn **từ chối request ngay tại Gateway**, đừng đợi đến `beforeCommit` mới đổi `200` thành `401`. Hãy quyết định ở giai đoạn trước routing và chủ động kết thúc response:

~~~java
import org.springframework.http.HttpStatus;
import reactor.core.publisher.Mono;

// Ví dụ nằm trong một filter, sau khi đã có kết quả kiểm tra quyền.
// Điều kiện denied chỉ minh họa; việc xác thực thật nên dùng Spring Security.
if (denied) {
    exchange.getResponse().setStatusCode(HttpStatus.FORBIDDEN);
    return exchange.getResponse().setComplete();
}

return chain.filter(exchange);
~~~

Khi `return setComplete()`, chain downstream không còn được gọi trong nhánh bị từ chối. `beforeCommit` phù hợp để **hoàn thiện metadata của response**; nó không thay thế cơ chế authentication/authorization.

## 7. Vì sao sửa response trong post-filter thường thất bại?

Xem ví dụ dưới đây:

~~~java
@Override
public Mono<Void> filter(ServerWebExchange exchange, GatewayFilterChain chain) {
    return chain.filter(exchange)
        .then(Mono.fromRunnable(() -> {
            // Có thể đã quá muộn tùy order và quá trình ghi response.
            exchange.getResponse()
                .getHeaders()
                .set("X-Edge-Processed", "true");
        }));
}
~~~

Đây không phải cú pháp Java sai. Vấn đề là **thời điểm thực thi**: `then` chờ completion của chain phía sau nó; một filter ghi response ở downstream của chain có thể đã commit trước lúc `then` chạy. Hậu quả có thể là:

- Header không xuất hiện ở client.
- Exception do header map không còn được phép thay đổi.
- Hành vi khác nhau giữa response có body, không body hoặc streaming.
- Test với backend phản hồi nhanh có kết quả khác với môi trường thật, tùy filter order.

Trong Spring Cloud Gateway Server WebFlux, các thành phần routing và ghi response có vai trò khác nhau. Ví dụ `NettyRoutingFilter` gửi request đến downstream bằng HTTP client, còn `NettyWriteResponseFilter` ghi body trả về ở nhánh hậu xử lý. Thứ tự `Ordered` quyết định việc filter tùy biến của bạn quay lại **trước hay sau** bước ghi.

**Cách sửa thường dùng:** đăng ký callback `beforeCommit` ngay trong pre-filter:

~~~java
@Override
public Mono<Void> filter(ServerWebExchange exchange, GatewayFilterChain chain) {
    ServerHttpResponse response = exchange.getResponse();

    response.beforeCommit(() -> Mono.defer(() -> {
        response.getHeaders().set("X-Edge-Processed", "true");
        return Mono.empty();
    }));

    return chain.filter(exchange);
}
~~~

Nếu vẫn có lỗi, kiểm tra callback có được đăng ký **trước khi response đã commit** hay không, filter nào đang kết thúc request sớm, và có filter khác thay cùng header hay không.

### Thứ tự callback `beforeCommit` có thể là một phần nghiệp vụ

Nếu nhiều thành phần đăng ký callbacks để thay đổi cùng `Content-Type`, `Cache-Control` hoặc `Set-Cookie`, kết quả có thể khó đoán chỉ bằng nhìn route YAML. Hãy tổ chức một nơi sở hữu mỗi header quan trọng; nếu cần composition, quy định thứ tự và xác minh bằng integration test.

Không dùng `beforeCommit` để ghi lại body hoặc tạo một response thứ hai. Khi phải biến đổi body, cần thao tác trong pipeline ghi body với response decorator/cơ chế lọc body được hỗ trợ.

## 8. Response streaming và body làm thời điểm commit sớm hơn

HTTP response có thể chứa:

- Body JSON nhỏ, hoàn thành trong một lần ghi.
- Tệp lớn hoặc download theo nhiều khối dữ liệu.
- **Server-Sent Events (SSE)** hoặc nội dung streaming lâu dài.
- Response không body như `204 No Content`, `304 Not Modified` hoặc một số phản hồi HEAD.

Với streaming, status và headers phải được chốt **trước khi phần dữ liệu đầu tiên bắt đầu đi ra**, nhưng body có thể tiếp tục truyền thêm nhiều phút. Đến khi `doFinally` hoặc đoạn post-filter cuối cùng chạy thì header đã commit từ lâu.

~~~mermaid
sequenceDiagram
    participant GW as Gateway filter
    participant R as Reactive response
    participant CL as Client
    GW->>R: beforeCommit(callback) đăng ký từ pre
    R->>R: Bắt đầu quy trình commit
    R->>R: Thực hiện callback trước commit
    R-->>CL: HTTP status + headers
    loop Streaming
        R-->>CL: Chunk dữ liệu tiếp theo
    end
    Note over R,CL: Không thể đổi headers đã gửi giữa các chunks
~~~

Trong ví dụ này, callback được chạy **trước** bước áp dụng status/headers; sơ đồ thể hiện quá trình commit ở mức tổng quát, không áp đặt tên sự kiện nội bộ của server.

### Nếu thực sự cần thay đổi body?

Có thể dùng một `ServerHttpResponseDecorator` hoặc một filter built-in chuyên biến đổi body nếu phiên bản hỗ trợ. Khi viết decorator, phải xử lý đúng:

- **Reactive backpressure** và vòng đời của `Flux<DataBuffer>`.
- **Giải phóng/tái sử dụng DataBuffer** đúng cơ chế; tránh rò rỉ bộ nhớ.
- **Content-Length** khi kích thước body thay đổi, hoặc cơ chế chunked transfer thích hợp.
- **Content-Encoding** như gzip, và quy tắc không đọc/sửa nội dung nhị phân tùy tiện.
- Các mã HTTP không có body; SSE hoặc streaming không thể tùy tiện gom toàn bộ payload vào RAM.

`beforeCommit` **không phải API để đọc toàn bộ body rồi sửa**. Nó được thiết kế cho hành động thực hiện ngay trước khi commit response. Nếu phải viết lại JSON, cần hướng xử lý body chuyên dụng và integration test riêng.

## 9. Cấu hình route, security và phạm vi filter

Một ứng dụng Gateway thường có nhiều tầng xử lý HTTP:

~~~mermaid
flowchart TD
    C["Client"] --> W["Spring WebFlux: WebFilter / Spring Security"]
    W --> H["RoutePredicateHandlerMapping"]
    H -->|"Route khớp"| F["FilteringWebHandler"]
    F --> GF["GlobalFilter + GatewayFilter"]
    GF --> R["Routing / downstream"]
    R --> RESP["ServerHttpResponse beforeCommit + ghi response"]
    H -->|"Không route khớp"| NF["Handler lỗi / phản hồi từ web layer"]
    W -->|"Từ chối sớm"| DENY["401/403 từ security layer"]
~~~

Từ đó suy ra:

| Mục tiêu | Vị trí thường phù hợp | Vì sao? |
|---|---|---|
| Gắn header cho **mọi route Gateway** đã được chọn | `GlobalFilter` và `beforeCommit` | Dễ dùng metadata route, không phải lặp cấu hình route |
| Gắn header riêng cho **một route** | `GatewayFilter` hoặc `SetResponseHeader` | Phạm vi rõ theo ID/URI/predicate |
| Gắn header bắt buộc cho **mọi HTTP response**, kể cả 404 không route và lỗi security | `WebFilter`/thành phần response ở tầng bao trùm phù hợp | `GlobalFilter` Gateway có thể không chạy khi chưa chọn route |
| Chặn request không có quyền | Spring Security hoặc policy filter chạy trước khi routing | Tránh chuyển request trái phép tới backend |
| Rate limit theo route | Filter có key resolver/backend limiter phù hợp | Giới hạn trước khi forward; cần xét cả route fallback |
| Thu thập metrics và trace kết thúc request | Hạ tầng observability / Reactor signals phù hợp | `beforeCommit` không phải tín hiệu truyền xong body |

**Bảo mật:** không dùng header do client cung cấp như bằng chứng rằng request đã được xác thực. Nếu muốn thêm header nội bộ `X-Authenticated-User`, phải lấy danh tính từ security context đáng tin cậy, loại header giả mạo đầu vào và cân nhắc không làm lộ thông tin nhạy cảm ra response.

**TLS:** `beforeCommit` chỉ thao tác HTTP response metadata. Nó không thay thế cấu hình TLS của listener, trust store, kiểm chứng certificate hoặc kết nối HTTPS tới downstream.

## 10. Các lỗi khó gặp khi callback đã đăng ký nhưng header không xuất hiện

| Triệu chứng | Nguyên nhân đáng kiểm tra | Cách xác minh |
|---|---|---|
| Response 200 không có header mới | Filter không chạy, callback đăng ký muộn, header bị ghi đè | Log route ID/filter, thử một route khớp; xem tất cả filter quản lý header |
| Request không match route bị thiếu header | `GlobalFilter` Gateway chưa tham gia | Nếu chính sách cần bao phủ cả 404, kiểm tra tầng `WebFilter`/web server |
| Header xuất hiện với 200 nhưng không có ở 401/403 | Spring Security chặn trước `FilteringWebHandler` | Kiểm tra security filter chain; đặt logic ở đúng tầng |
| Không sửa được header, xuất hiện exception | Đã commit hoặc cố mutate headers ở post-filter quá muộn | Đăng ký `beforeCommit` trong pre; xác minh có early response không |
| Callback thực thi nhưng status không như ý | Filter lỗi/fallback ghi lại status hoặc status quyết định muộn | Theo dõi chỗ đặt status; test response downstream và Gateway |
| Response streaming không đổi header | Dữ liệu đã bắt đầu gửi; callback đăng ký sau commit | Đăng ký trước lúc stream đầu tiên được ghi |
| Response có nhiều giá trị cùng header | Dùng `add` ở nhiều filter, downstream cũng thêm | Xác định owner; dùng `set` hoặc filter dedupe phù hợp |
| Sau khi sửa body client treo hoặc nhận dữ liệu hỏng | Sai `DataBuffer`, `Content-Length`, compression hoặc backpressure | Dùng body filter/decorator đúng; kiểm thử streaming và payload lớn |
| Khác nhau giữa các Gateway instance | Có instance chạy code/config cũ hoặc route/order khác | Gắn instance ID trong log, kiểm tra rollout và cache |
| Header mất sau reverse proxy hoặc CDN | Proxy phía sau Gateway có thể lọc/ghi đè headers | So sánh response trực tiếp tại Gateway và ở phía client |

Có thể bật log có kiểm soát cho thành phần Gateway cần chẩn đoán và xem trace/metrics khi đã cấu hình observability. Tránh ghi body, token, Cookie hoặc dữ liệu riêng tư vào log chỉ để xác nhận `beforeCommit`.

### `isCommitted()` chỉ nên dùng để quan sát

~~~java
boolean committed = exchange.getResponse().isCommitted();
~~~

Giá trị này giúp xác định một response **đã/đang** bước qua điểm commit tại thời điểm quan sát, nhưng không làm thao tác sửa header kế tiếp trở nên an toàn theo kiểu `if (!committed)`. Đặc biệt, trong chính callback `beforeCommit`, framework đã bắt đầu quy trình commit; không dùng `isCommitted()` như điều kiện để bỏ qua mọi thao tác được callback đăng ký hợp lệ.

## 11. Bài thực hành: chứng minh thời điểm commit

**Chuẩn bị:** một ứng dụng Gateway Server WebFlux theo phiên bản phù hợp, backend echo HTTP trên `localhost:9090`, Gateway lắng nghe cổng `8080`, và route `/api/orders/**` như phần 4.

### Bước 1 — Gắn header từ `beforeCommit`

Thêm lớp `EdgeResponseHeaderFilter` ở phần 4 vào source của ứng dụng Gateway, khởi động lại và gọi:

~~~bash
curl -i http://localhost:8080/api/orders/42
~~~

Quan sát header `X-Edge-Processed: true`, status thực tế và path backend nhận được (`/orders/42` khi `StripPrefix=1`). Điều này xác nhận callback đã chạy trên một response đi qua route.

### Bước 2 — Đổi backend trả status lỗi

Cho backend trả một response lỗi, ví dụ HTTP 503 cho `GET /orders/fail` mà vẫn hoàn tất response bình thường. Gửi:

~~~bash
curl -i http://localhost:8080/api/orders/fail
~~~

Xác minh `X-Edge-Processed` được gắn trên response nếu request đi qua filter và response commit, đồng thời mã lỗi từ downstream được trả đúng với chính sách Gateway. Nếu Gateway có `Retry` hoặc `CircuitBreaker`, thử nghiệm có thể cho kết quả khác do retry/fallback; ghi lại cấu hình ấy.

### Bước 3 — Thử request không khớp route

~~~bash
curl -i http://localhost:8080/not-configured
~~~

Nếu không có route hay handler khác, ứng dụng thường trả 404. Với filter `GlobalFilter` hiện tại, **không yêu cầu** header `X-Edge-Processed` xuất hiện trong response này, vì callback của filter có thể chưa bao giờ được đăng ký.

### Bước 4 — So sánh với post-filter

Trong một nhánh thử nghiệm, thay đoạn `beforeCommit` bằng `.then(Mono.fromRunnable(...))` như phần 7 và đo kết quả trên response body, response rỗng và response lỗi. Không cố ý đưa phiên bản thử nghiệm dễ lỗi đó vào production. Phân tích bằng filter order và thời điểm commit; **đừng kết luận rằng post-filter luôn sai**, vì vẫn có những order/tác vụ hậu xử lý hợp lệ.

### Bước 5 — Kiểm chứng response streaming

Nếu backend có endpoint SSE hoặc streaming, thử với `curl -i -N`:

~~~bash
curl -i -N http://localhost:8080/api/orders/events
~~~

Đảm bảo route khớp và backend thực sự gửi stream. Response phải có header phù hợp **trước dữ liệu stream đầu tiên**; lúc stream còn mở, không thể gửi một bản header HTTP khác giữa chừng. Không dùng endpoint giả định này nếu backend chưa triển khai.

### Ghi kết quả

| Trường hợp | Điều cần ghi nhận | Ý nghĩa |
|---|---|---|
| GET 200 có body | Status, header mới, body | beforeCommit hoạt động với route thông thường |
| GET trả 503 | Header còn không, retry/fallback ra sao | Hành vi trên response lỗi đã đi qua route |
| Path không có route | Có/không có header | Phân biệt Gateway `GlobalFilter` và tầng web bao trùm |
| Response 204/rỗng | Header có được commit khi không có body? | Phân biệt body với việc commit status/headers |
| SSE/streaming | Header xuất hiện trước chunk đầu | Commit xảy ra sớm dù body còn truyền |
| Phiên bản post-filter | Header có hiện diện? Có exception? | Tác động của order và thời điểm thay đổi |

Không cần làm chậm backend thật hoặc thay đổi đồng hồ hệ thống để kiểm tra cơ chế response commit. Dùng backend echo trong môi trường thử nghiệm, kết hợp log/trace và kiểm tra byte/header client nhận.

## 12. Nguyên tắc thiết kế filter trước commit

1. **Chọn đúng tầng:** `GlobalFilter` cho response của Gateway routes, `GatewayFilter` cho một route, `WebFilter` hoặc thành phần ngoài Gateway route để bao phủ cả lỗi không match/security.
2. **Đăng ký trước khi gọi chain** nếu cần chắc chắn thao tác nằm trong cơ hội commit; tránh đăng ký trong `doFinally` hoặc `then` quá muộn.
3. **Giữ callback ngắn, non-blocking, deferred** và trả về `Mono<Void>` hoàn thành. Không đặt remote call không được kiểm soát trong đường commit của mọi request.
4. **Chỉ thay đổi thông tin response còn hợp lệ:** headers/status/cookies theo lifecycle; nếu cần biến đổi body, dùng pipeline body chuyên dụng.
5. **Phân quyền sở hữu header:** tránh nhiều filter cùng `set`/`add` một tên mà không có quy ước thứ tự; không rò rỉ thông tin nội bộ hoặc token.
6. **Test đủ các đường đi:** response có body, response rỗng, error, security reject, không có route, retry/fallback và streaming nếu được dùng.
7. **Bảo vệ khả năng vận hành:** không để callback lỗi/treo làm nghẽn mọi response; ghi metrics, log có giới hạn và kết quả thực tế tại client.

## 13. Checklist tự kiểm tra

- [ ] Tôi phân biệt được **pre-filter**, **post-filter** và **`beforeCommit`**.
- [ ] Tôi hiểu status/headers/cookies phải được xác định trước lúc HTTP response commit.
- [ ] Tôi biết lấy `ServerHttpResponse` từ `ServerWebExchange`.
- [ ] Tôi đăng ký `response.beforeCommit(...)` ở pre-filter và dùng publisher deferred như `Mono.defer`.
- [ ] Tôi không dùng `isCommitted() == false` như một khóa bảo đảm không có race condition.
- [ ] Tôi đã xác minh phạm vi của `GlobalFilter` khác `WebFilter` và route-specific `GatewayFilter`.
- [ ] Tôi dùng `AddResponseHeader`/`SetResponseHeader` hoặc filter built-in phù hợp khi không cần logic Java tùy biến.
- [ ] Tôi không dùng `beforeCommit` để xử lý authorization hay sửa toàn bộ body.
- [ ] Tôi có quy tắc rõ ràng cho các header nhạy cảm, tránh `add` lặp và ghi đè không kiểm soát.
- [ ] Tôi đã thử response bình thường, lỗi, không route, không body và streaming nếu liên quan.
- [ ] Tôi đã xem order của filters và những thành phần ghi response khi debug lỗi header không xuất hiện.
- [ ] Tôi giữ khả năng quan sát request, TLS, retry/circuit breaker và rate limiting đúng tầng ứng dụng.

## Tài liệu tham khảo chính thức

- [Spring Framework — ServerHttpResponse](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/server/reactive/ServerHttpResponse.html) — API `beforeCommit`, `setComplete`, `isCommitted` và quản lý response.
- [Spring Cloud Gateway Reference](https://docs.spring.io/spring-cloud-gateway/reference/) — GlobalFilter, filter order, GatewayFilter factories, Netty routing/write response và route lifecycle; chọn đúng phiên bản.
- [Spring Framework WebFlux Reference](https://docs.spring.io/spring-framework/reference/web/webflux.html) — `ServerWebExchange`, `WebFilter` và pipeline phản hồi reactive.
- [Project Reactor Reference](https://projectreactor.io/docs/core/release/reference/) — `Mono.defer`, chuỗi tín hiệu reactive, cancellation và non-blocking.
- [Spring Boot Actuator](https://docs.spring.io/spring-boot/reference/actuator/) — observability, metrics và endpoint quản trị cần được bảo vệ.

**Ghi nhớ:** Để chỉnh sửa headers/cookies ngay trước khi Gateway trả response, hãy **đăng ký `ServerHttpResponse.beforeCommit` từ sớm trong pre-filter và trả về một `Mono<Void>` deferred**. Code chạy trong `then` sau `chain.filter(exchange)` có thể đã quá muộn để thay đổi status/headers, đặc biệt khi downstream response đã được ghi hoặc là stream lâu dài. Việc chọn đúng tầng filter và kiểm chứng response thực tế quan trọng không kém cú pháp Java.
