# Truyền dữ liệu qua exchange attributes và Reactor Context

## 1. Vì sao custom filter cần truyền dữ liệu qua nhiều bước?

Trong **Spring Cloud Gateway**, một request đi qua route predicate, filter chain, các bước biến đổi header/path, khám phá dịch vụ, load balancing và bộ định tuyến HTTP(S) để đến microservice. Gateway còn thường áp dụng xác thực, giới hạn lưu lượng, circuit breaker, retry, TLS và observability.

Khi tự viết `GlobalFilter` hoặc `GatewayFilter`, bạn có thể cần chia sẻ một thông tin giữa các bước:

- Filter A sinh mã tương quan `requestId`, filter B dùng mã đó để ghi log.
- Filter A xác định một nhãn tenant **đã được xác minh**, filter B chọn rate-limit key hoặc policy.
- Filter đầu đọc route metadata, filter sau thêm header quan sát vào request đi tới upstream.
- Một operator Reactor cần biết trace information sau khi pipeline chuyển scheduler/thread.

**Hai công cụ khác nhau** thường xuất hiện trong thiết kế:

1. `ServerWebExchange.getAttributes()`: vùng thuộc tính **gắn với HTTP exchange**, cho phép filter/handler trên cùng request lấy dữ liệu theo key.
2. **Reactor `Context`**: vùng dữ liệu **gắn với reactive subscriber/subscription**, được truyền qua chuỗi Reactor theo phạm vi của operator `contextWrite`.

Hai công cụ không tự đồng bộ với nhau. Chọn sai chỗ lưu hoặc sai vị trí ghi context có thể khiến filter sau đọc được `null`, request bị mất correlation ID, log bị gán nhầm hoặc một đoạn code phụ thuộc `ThreadLocal` thất bại khi chuyển thread.

Bài thuộc chương **Bộ lọc tùy biến** của module **SPRING_CLOUD_GATEWAY**. Nội dung tập trung vào cách dùng `exchange attributes` và `Reactor Context` đúng vòng đời, đúng filter order, tránh lộ dữ liệu bảo mật và kiểm thử có thể lặp lại.

> **Phạm vi:** ví dụ dùng **Spring Cloud Gateway Server WebFlux** và Project Reactor. Các API `GlobalFilter`, `GatewayFilterChain`, `ServerWebExchange`, `Mono.deferContextual`, `contextWrite` được minh họa ở Java. Gateway Server MVC có kiến trúc khác; không bê nguyên Reactor Context vào MVC/Servlet.

## 2. Bức tranh tổng quan về các vùng dữ liệu

| Cơ chế | Được gắn với | Đọc/ghi bằng | Dùng cho | Không dùng thay cho |
| --- | --- | --- | --- | --- |
| Exchange attributes | Một `ServerWebExchange` | `exchange.getAttributes().put(...)`, `getAttribute(...)` | Chia sẻ dữ liệu giữa WebFlux/Gateway filters và các bước routing | HTTP headers, database/session, bảo mật token |
| Reactor Context | Một reactive subscription theo phạm vi operator | `contextWrite(...)`, `Mono.deferContextual(...)` | Propagate dữ liệu qua async operators, cả khi chuyển scheduler | Exchange attributes hoặc `ThreadLocal` tự động |
| HTTP request headers | Message được gửi trên mạng | `ServerHttpRequest.mutate()` | Truyền thông tin sang **upstream service** theo contract | Vùng lưu nội bộ riêng tư |
| Security principal | Authentication trong Spring Security reactive | `exchange.getPrincipal()`, Security context APIs | Nhận biết danh tính đã xác thực | Header tự khai báo của client |
| Session/data store | Request xuyên nhiều lần gọi hoặc phiên | Spring Session/Redis/database | Trạng thái cần tồn tại qua nhiều requests | Attributes hoặc Context chỉ có vòng đời ngắn |
| `ThreadLocal` / MDC | Một thread tại một thời điểm | `MDC.put(...)`, `MDC.get(...)` | Một số thư viện logging đồng bộ | Reactive context khi execution đổi thread |

**Câu hỏi chọn cơ chế:** dữ liệu cần tồn tại **trên cùng HTTP request**, **trong chuỗi Reactor hiện tại**, **ở microservice khác**, hay **qua nhiều request**? Mỗi mục tiêu có một đường truyền riêng.

~~~mermaid
flowchart LR
    C["HTTP client"] --> W["Spring WebFlux WebFilter"]
    W --> G["Gateway filter chain"]
    G --> A["GlobalFilter A<br/>exchange attributes"]
    A --> B["GlobalFilter B<br/>Reactor Context"]
    B --> N["Netty routing"]
    N --> S["Upstream service"]
    A -. "Map attributes cùng exchange" .-> B
    B -. "Reactor Context theo subscription" .-> N
    N -. "HTTP headers đi trên mạng" .-> S
~~~

Sơ đồ chỉ mô tả các luồng logic. **Reactor Context không được gửi qua mạng như HTTP header**; nếu cần upstream nhận request ID, phải chủ động ghi header/metadata phù hợp. **Attributes cũng không được serialize tự động** sang backend.

## 3. Vòng đời của filter chain và vai trò của Ordered

Trong Gateway Server WebFlux:

- **`GlobalFilter`** là filter áp dụng cho các request đã chọn route Gateway.
- **`GatewayFilter`** là filter được gắn vào một route cụ thể hoặc do `GatewayFilterFactory` sinh ra.
- Các filter được gom thành một chuỗi và sắp thứ tự theo `Ordered`.
- **Pre-phase** đi theo chiều order tăng dần; **post-phase** của các publisher được lồng nhau thường diễn ra theo chiều ngược lại.
- **`WebFilter`** của Spring WebFlux/Security nằm ở tầng ngoài, không phải một `GlobalFilter` và không dùng chung cơ chế sắp thứ tự của Gateway.

Ví dụ hai filter:

~~~text
Filter A: order = -100
Filter B: order = -90

Pre:
  A -> B -> routing

Post:
  routing -> B -> A
~~~

Nếu A đặt một attribute **trước** khi gọi `chain.filter(exchange)`, B có thể đọc nó. Nếu A chỉ ghi attribute **sau** khi `chain.filter(...)` hoàn tất, B ở pre-phase đã chạy và không thể thấy giá trị ở thời điểm đó.

Điều này còn quan trọng khi chọn thời điểm đặt `contextWrite`. Reactor Context được truyền qua operator ở **thời điểm subscription**, không phải một global map có thể sửa tùy ý trong mọi thread.

### 3.1. Filter có thể không chạy với mọi response

Một response `401` hoặc `403` do `SecurityWebFilterChain` chặn **trước khi Gateway chọn route** có thể không chạy GlobalFilter A/B. Một request không khớp route có thể được xử lý ở tầng khác, cũng không chạy những route filters đã khai báo.

Nếu bắt buộc tạo correlation ID cho **cả response bị chặn trước route**, hãy cân nhắc đặt logic tương ứng trong một **WebFilter** có vị trí phù hợp, rồi truyền dữ liệu xuống Gateway qua exchange/Context. Không kỳ vọng `GlobalFilter` quan sát mọi 401/404.

## 4. ServerWebExchange attributes: dữ liệu của một HTTP exchange

`ServerWebExchange` đại diện request, response và các thông tin phụ trợ trong xử lý WebFlux. `getAttributes()` trả một map chứa dữ liệu theo key (thường dùng `String` key). Gateway cũng có các attributes nội bộ để điều phối route.

Ví dụ ghi và đọc:

~~~java
String key = "example.gateway.requestId";

// Filter ở đầu pipeline:
exchange.getAttributes().put(key, "req-abc-123");

// Filter chạy sau trên cùng exchange:
String requestId = exchange.getAttribute(key);
if (requestId != null) {
    // Dùng requestId cho logic an toàn trong request này.
}
~~~

Đặc điểm:

- **Vòng đời:** thuộc một HTTP exchange; không phải nơi lưu lâu dài.
- **Khả năng quan sát:** các filter/handler dùng cùng exchange (hoặc decorator ủy quyền thuộc tính tới exchange gốc) có thể truy cập dữ liệu.
- **Mutability:** map cho phép thay giá trị theo key; cần thiết kế **ai sở hữu quyền ghi** để tránh ghi đè ngẫu nhiên.
- **Không vượt mạng:** upstream không thấy attribute, trừ khi filter chuyển nó thành header/body/message theo hợp đồng.
- **Không tự vào Reactor Context:** gọi `put` không làm `Mono.deferContextual` đọc được key đó.

### 4.1. Dùng namespace cho key

Tránh key quá phổ biến:

~~~java
exchange.getAttributes().put("id", "123");
~~~

Một custom filter khác hoặc framework có thể sử dụng cùng tên. Dùng key có namespace:

~~~java
public static final String REQUEST_ID_ATTRIBUTE =
        "example.gateway.request-context.requestId";
~~~

Nếu một filter cần đọc key bắt buộc, hãy dùng cách lấy typed/validated; đừng ép kiểu một attribute không rõ nguồn. Sai kiểu có thể gây `ClassCastException` trong reactive pipeline, đôi khi chỉ xảy ra ở production.

### 4.2. Khi có các attributes nội bộ của Gateway

Spring Cloud Gateway sử dụng những tên hằng trong `ServerWebExchangeUtils`, ví dụ:

| Hằng | Ý nghĩa khái quát | Thời điểm có thể tồn tại |
| --- | --- | --- |
| `GATEWAY_ROUTE_ATTR` | Route đã được chọn | Sau khi Gateway khớp route |
| `GATEWAY_REQUEST_URL_ATTR` | URI mục tiêu cho routing | Sau bước xây dựng URL đến upstream |
| `GATEWAY_ORIGINAL_REQUEST_URL_ATTR` | Các URI gốc trong quá trình biến đổi | Khi filter routing/path rewrite lưu lại |
| `GATEWAY_SCHEME_PREFIX_ATTR` | Scheme prefix như `lb` trong route đặc biệt | Sau khi Gateway phân tích URL |
| `CACHED_REQUEST_BODY_ATTR` | Body đã được cache trong một số quy trình | Chỉ khi một filter có chủ đích cache body |

Không kết luận `GATEWAY_REQUEST_URL_ATTR` **luôn** tồn tại ở một GlobalFilter có order âm; nó có thể chỉ được tạo sau `RouteToRequestUrlFilter`. Cũng không tự ghi đè những hằng nội bộ này để “đổi route” nếu chưa hiểu hợp đồng và các bước routing: sửa sai có thể dẫn đến chuyển tiếp tới URL không mong muốn.

### 4.3. Ghi trước khi gọi chain, đọc sau khi gọi chain

Một filter có thể đặt metadata cho filter sau đọc ở pre-phase:

~~~java
@Override
public Mono<Void> filter(ServerWebExchange exchange, GatewayFilterChain chain) {
    exchange.getAttributes().put("example.gateway.startNanos", System.nanoTime());

    return chain.filter(exchange)
        .doFinally(signal -> {
            Long start = exchange.getAttribute("example.gateway.startNanos");
            if (start != null) {
                long elapsedNanos = System.nanoTime() - start;
                // Ghi metric đã được làm sạch, không log raw token.
            }
        });
}
~~~

`doFinally` được gọi cả khi complete, error hoặc cancel. Đây là một ví dụ về **dùng attribute cho timing** trong một request; không nên dựa vào `doOnSuccess` nếu muốn tính cả lỗi/cancellation.

**Lưu ý về concurrency:** đừng tạo nhiều luồng đua nhau cập nhật cùng một object mutable trong attributes mà không có đồng bộ hóa thích hợp. Map attribute không phải cơ chế transaction, lock hoặc event bus.

## 5. Reactor Context: dữ liệu theo subscriber, không phải ThreadLocal

Project Reactor cung cấp `Context` bất biến về mặt thao tác (mỗi lần `put` tạo một phiên bản context mới), và `ContextView` chỉ đọc. Nguồn dữ liệu được truyền **từ phía subscriber lên các operator upstream tại thời điểm subscribe**, không theo cách một biến toàn cục được sửa tại runtime.

Các API thường dùng:

- `contextWrite(ctx -> ctx.put(KEY, value))`: tạo context mới cho **phần upstream** tương ứng.
- `Mono.deferContextual(contextView -> ...)`: trì hoãn việc đọc context tới lúc subscription.
- `Flux.deferContextual(...)`: tương tự cho publisher có nhiều phần tử.
- `ContextView.hasKey(KEY)`, `get(KEY)`, `getOrDefault(KEY, defaultValue)`: đọc giá trị với mức độ an toàn phù hợp.

### 5.1. Ví dụ nhỏ nhất có thể chạy cùng Reactor

~~~java
import reactor.core.publisher.Mono;

public class ReactorContextDemo {
    static final String KEY = "example.requestId";

    static Mono<String> readRequestId() {
        return Mono.deferContextual(context ->
                Mono.just(context.getOrDefault(KEY, "missing")));
    }

    public static void main(String[] args) {
        String result = readRequestId()
                .contextWrite(context -> context.put(KEY, "req-123"))
                .block();

        System.out.println(result); // req-123
    }
}
~~~

`block()` ở ví dụ **chỉ để demo trong hàm main độc lập**. **Không gọi `block()` trong GlobalFilter/GatewayFilter chạy trên Reactor Netty event loop**, vì sẽ chặn thread bất đồng bộ, gây tăng latency hoặc lỗi.

### 5.2. Vì sao vị trí contextWrite quan trọng?

Một cách tư duy:

~~~text
Subscriber
  |
  v
contextWrite(put requestId)
  |
  v
deferContextual(read requestId)    <-- upstream có thể đọc
~~~

Với Reactor, `contextWrite` ảnh hưởng những operator **ở phía upstream của chính nó** trong chuỗi reactive. Không được giả định mọi operator được gắn sau `contextWrite` ở phía downstream đều nhìn thấy context mới.

Ví dụ:

~~~java
Mono<String> observed = Mono.deferContextual(ctx ->
        Mono.just(ctx.getOrDefault("requestId", "missing")))
    .contextWrite(ctx -> ctx.put("requestId", "req-123"));

// Mono phía trên đọc được req-123.
~~~

Cần phân biệt **operator được assembly** và **thời điểm subscription**. Một đoạn Java đọc context theo kiểu biến `ThreadLocal` ngay khi tạo `Mono` sẽ không có tính chất propagation này.

### 5.3. Context khác MDC trong logging

`org.slf4j.MDC` thường dựa vào `ThreadLocal`. Reactive pipeline có thể dùng `publishOn`, `subscribeOn` hoặc thư viện tự đổi thread; khi đó `MDC.put("requestId", ...)` ở thread A không bảo đảm log ở thread B đọc được.

`Reactor Context` được Reactor propagate trong reactive chain đúng cách, **nhưng nó không tự động chép tất cả dữ liệu vào MDC**. Nếu cần MDC/log correlation tự động, phải dùng Micrometer Context Propagation, Reactor integration, framework tracing hoặc một bridge được cấu hình, và kiểm thử theo phiên bản. Không bật hook context propagation mà không xem overhead và phạm vi ThreadLocal được đăng ký.

## 6. Khi nào dùng exchange attributes, khi nào dùng Context?

| Tình huống | Lựa chọn đầu tiên | Lý do |
| --- | --- | --- |
| Filter A chọn route tag, filter B cùng Gateway đọc tag | Exchange attribute | Có sẵn cùng `ServerWebExchange` |
| Muốn custom operator truy cập request ID sau `publishOn` | Reactor Context | Đúng lifecycle reactive subscriber |
| Cần truyền request ID đến microservice bên ngoài | HTTP header/trace propagation | Attributes/Context không vượt qua HTTP tự động |
| Cần lưu kết quả login cho request ngày mai | Session/data store | Cả hai cơ chế trên chỉ thuộc vòng đời ngắn |
| Backend phải kiểm tra user/tenant | Security principal/token/identity assertion đã xác minh | Không tin attribute tự phát từ header client |
| Cần metrics theo route | Exchange attributes hoặc observation APIs | Quan sát route ID, latency với cardinality hợp lý |
| Thư viện reactive chỉ nhận `Mono`, không nhận exchange | Reactor Context | Tránh ép truyền `ServerWebExchange` xuống mọi tầng |
| Unit test một phép tính không dùng HTTP | `Context` hoặc tham số tường minh | Không cần giả lập toàn bộ Gateway |

**Không cần cố “dùng cả hai cho mọi dữ liệu”.** Nếu filter chỉ cần đọc một giá trị từ exchange, attributes là đủ. Nếu truyền qua operator reactive, Context giúp tách dữ liệu khỏi chữ ký hàm. Nếu giá trị là tham số nghiệp vụ cốt lõi, **truyền tường minh trong method argument** có thể rõ ràng hơn cả hai.

## 7. Ví dụ hoàn chỉnh: bridge một request ID qua hai cơ chế

Mục tiêu của ví dụ:

1. Gateway tự tạo `requestId` khó đoán cho mỗi request đã khớp route.
2. Filter đầu lưu nó vào **exchange attribute**.
3. Filter đầu ghi `X-Request-Id` vào **HTTP request outbound**.
4. Filter đầu đưa nó vào **Reactor Context** cho chuỗi filter phía sau.
5. Filter thứ hai đọc và đối chiếu hai nguồn trong **reactive subscription**.
6. Gateway phản hồi `X-Request-Id` để client đối chiếu log mà không lộ thông tin riêng tư.

Đây là mô hình thực hành, không thay thế hệ thống distributed tracing tiêu chuẩn như Micrometer Tracing/OpenTelemetry.

### 7.1. Khai báo các key dùng chung

~~~java
package example.gateway.filter;

public final class GatewayContextKeys {
    public static final String REQUEST_ID_ATTRIBUTE =
            GatewayContextKeys.class.getName() + ".requestId";

    // Object key duy nhất giúp hạn chế va chạm giữa Reactor Context keys.
    public static final Object REQUEST_ID_REACTOR_CONTEXT = new Object();

    private GatewayContextKeys() {
    }
}
~~~

Sử dụng `String` có namespace cho exchange map và một `Object` key riêng cho Reactor Context. Key phải là **cùng một object tham chiếu** giữa filter ghi và filter đọc, do đó đặt trong lớp hằng dùng chung.

### 7.2. GlobalFilter ghi exchange attribute và Reactor Context

~~~java
package example.gateway.filter;

import java.util.UUID;

import org.springframework.cloud.gateway.filter.GatewayFilterChain;
import org.springframework.cloud.gateway.filter.GlobalFilter;
import org.springframework.core.Ordered;
import org.springframework.http.server.reactive.ServerHttpRequest;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;

import reactor.core.publisher.Mono;

@Component
public class RequestContextBridgeFilter implements GlobalFilter, Ordered {

    @Override
    public int getOrder() {
        return -100;
    }

    @Override
    public Mono<Void> filter(ServerWebExchange exchange,
                             GatewayFilterChain chain) {
        // Ví dụ cố tình tạo ID mới, không tin header do client tự khai báo.
        String requestId = UUID.randomUUID().toString();

        // (1) Gắn metadata theo HTTP exchange cho filter khác.
        exchange.getAttributes().put(
                GatewayContextKeys.REQUEST_ID_ATTRIBUTE, requestId);

        // (2) Chuyển thông tin qua HTTP header khi cần upstream nhận.
        ServerHttpRequest outboundRequest = exchange.getRequest()
                .mutate()
                .headers(headers -> headers.set("X-Request-Id", requestId))
                .build();

        ServerWebExchange forwardedExchange = exchange
                .mutate()
                .request(outboundRequest)
                .build();

        // (3) Phát correlation header khi response sắp được commit.
        exchange.getResponse().beforeCommit(() -> {
            exchange.getResponse().getHeaders()
                    .set("X-Request-Id", requestId);
            return Mono.empty();
        });

        // (4) contextWrite đặt phía downstream của publisher chain.filter;
        // các operator trong chain bên trong có thể đọc Context tại subscribe.
        return chain.filter(forwardedExchange)
                .contextWrite(ctx -> ctx.put(
                        GatewayContextKeys.REQUEST_ID_REACTOR_CONTEXT,
                        requestId));
    }
}
~~~

**Giải thích từng bước:**

- `UUID.randomUUID()` phục vụ correlation ID demo; không dùng nó làm access token, mã reset mật khẩu hoặc security credential.
- `exchange.getAttributes().put(...)` thực hiện trước khi gọi chain; filter sau có thể đọc attribute.
- `mutate().headers(...)` tạo request decorator có header mới, không sửa trực tiếp request immutable gốc.
- `exchange.mutate().request(...).build()` tạo exchange decorator; trong WebFlux thông thường nó ủy quyền attributes/response tới exchange nền. Nếu dùng custom decorator khác, cần kiểm tra cách ủy quyền.
- `beforeCommit` ghi response header **trước khi commit**. Nếu response đã bị xử lý ở WebFilter trước Gateway, filter này chưa chắc chạy.
- `contextWrite` bổ sung ID vào Context **phạm vi publisher mà `chain.filter` trả về**. Nó không làm ID tự động xuất hiện trong mọi publisher khác hoặc mọi HTTP request khác.
- `getOrder()=-100` nhằm cho filter quan sát ở mục sau (order -90) chạy sau khi metadata đã được đặt. Không xem hai con số này là một quy ước bắt buộc trên mọi project.

### 7.3. GlobalFilter đọc từ cả hai cơ chế

~~~java
package example.gateway.filter;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import org.springframework.cloud.gateway.filter.GatewayFilterChain;
import org.springframework.cloud.gateway.filter.GlobalFilter;
import org.springframework.core.Ordered;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;

import reactor.core.publisher.Mono;

@Component
public class RequestContextAuditFilter implements GlobalFilter, Ordered {
    private static final Logger log =
            LoggerFactory.getLogger(RequestContextAuditFilter.class);

    @Override
    public int getOrder() {
        return -90;
    }

    @Override
    public Mono<Void> filter(ServerWebExchange exchange,
                             GatewayFilterChain chain) {
        return Mono.deferContextual(contextView -> {
            String fromContext = contextView.getOrDefault(
                    GatewayContextKeys.REQUEST_ID_REACTOR_CONTEXT, "missing");

            String fromAttribute = exchange.getAttribute(
                    GatewayContextKeys.REQUEST_ID_ATTRIBUTE);

            // Metadata đủ để correlation, không đưa token/body vào log.
            log.debug("Gateway requestId: exchange={}, reactor={}",
                    fromAttribute, fromContext);

            return chain.filter(exchange)
                    .doFinally(signal -> log.debug(
                            "Gateway requestId={} signal={}",
                            fromAttribute, signal));
        });
    }
}
~~~

`Mono.deferContextual(...)` rất quan trọng: nó đọc Context **khi được subscribe** bên trong chuỗi có `contextWrite` của filter trước. Nếu đọc bằng một đoạn code đồng bộ được gọi bên ngoài reactive chain, bạn sẽ không có bảo đảm nhìn thấy context.

Filter audit vẫn xử lý request ngay cả khi Context không có key; nó in `missing` để dễ kiểm chứng. Trong production, policy có thể cần cảnh báo sự cố propagation. Không nên cho phép logic **authorization** phụ thuộc một chuỗi `missing` rồi mặc nhiên cấp quyền.

### 7.4. Cấu hình route tối thiểu để chạy ví dụ

Server WebFlux 5.x thường dùng:

~~~yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: catalog-api
              uri: http://localhost:8081
              predicates:
                - Path=/api/catalog/**
              filters:
                - StripPrefix=1
~~~

Với Gateway WebFlux 4.x phổ biến, route tương tự nằm dưới `spring.cloud.gateway.routes`:

~~~yaml
spring:
  cloud:
    gateway:
      routes:
        - id: catalog-api
          uri: http://localhost:8081
          predicates:
            - Path=/api/catalog/**
          filters:
            - StripPrefix=1
~~~

**Hai YAML này là lựa chọn theo phiên bản**, không nên khai báo đồng thời. Vì hai filter Java được đánh dấu `@Component` và implement `GlobalFilter`, chúng có thể tham gia chain của route đã khớp mà không cần thêm `name: RequestContextBridge` trong danh sách `filters`.

Đảm bảo upstream thực sự chạy và chấp nhận `GET /catalog/products/42`. Địa chỉ `localhost` chỉ dùng cho demo khi các tiến trình nằm trên cùng host; trong container, cần DNS/service name phù hợp.

## 8. ContextWrite có thể bị đặt sai ở vị trí nào?

### 8.1. Đặt contextWrite quanh đúng publisher

Ví dụ nên hiểu:

~~~java
return chain.filter(exchange)
        .contextWrite(ctx -> ctx.put(KEY, requestId));
~~~

Ở đây, `chain.filter(exchange)` là **publisher upstream** của `contextWrite`; các operator được gọi trong publisher đó có thể nhìn thấy key khi subscribe.

Ví dụ đối lập:

~~~java
return Mono.deferContextual(ctx ->
        Mono.just(ctx.getOrDefault(KEY, "missing")))
    .contextWrite(ctx -> ctx.put(KEY, requestId))
    .flatMap(value -> {
        // Phần flatMap phía sau contextWrite về mặt operator
        // không được mặc định nhận cùng Context sửa ở đoạn trước.
        return Mono.deferContextual(ctx -> Mono.just(
                ctx.getOrDefault(KEY, "missing")));
    })
    .then();
~~~

Tình huống này cho thấy **vị trí operator** quyết định phạm vi context. Không lấy một ví dụ đơn giản `contextWrite` thành quy tắc rằng mọi operator trong cùng method luôn nhìn thấy giá trị đó.

### 8.2. contextWrite không sửa biến toàn cục

~~~java
Context updated = Context.empty().put("requestId", "req-123");
~~~

`updated` là một instance context mới; không có chuyện mọi `Mono` trong JVM đều đọc được `requestId`. Nếu không gắn `updated` vào **subscription tương ứng**, những publisher khác vẫn không thấy nó.

### 8.3. Không dùng subscribe() riêng để “chuyển dữ liệu”

Một anti-pattern trong filter:

~~~java
// SAI về mặt thiết kế reactive filter:
Mono.deferContextual(ctx -> {
    // Xử lý phụ và đọc Context.
    return Mono.empty();
}).subscribe();

return chain.filter(exchange);
~~~

Việc gọi `subscribe()` thủ công tạo **một subscription khác**, khó quản lý context, cancellation, error, backpressure và lifecycle response. Hãy **compose** publisher bằng `then`, `flatMap`, `deferContextual` hoặc operator phù hợp để nằm trong chính request chain.

Không dùng `block()` trên Reactor Netty event loop hoặc biến `ServerWebExchange` thành static/global variable để “truyền” sang một luồng khác.

## 9. Custom GatewayFilterFactory theo route có dùng được hai cơ chế không?

Có. Nếu một thông tin chỉ cần cho một route, một `GatewayFilterFactory` có thể lưu metadata vào exchange attribute hoặc bổ sung Reactor Context. Ý tưởng:

~~~java
package example.gateway.filter;

import org.springframework.cloud.gateway.filter.GatewayFilter;
import org.springframework.cloud.gateway.filter.factory.AbstractGatewayFilterFactory;
import org.springframework.stereotype.Component;

@Component
public class RouteLabelGatewayFilterFactory
        extends AbstractGatewayFilterFactory<RouteLabelGatewayFilterFactory.Config> {

    public RouteLabelGatewayFilterFactory() {
        super(Config.class);
    }

    @Override
    public GatewayFilter apply(Config config) {
        return (exchange, chain) -> {
            String label = config.getLabel();
            exchange.getAttributes().put("example.gateway.routeLabel", label);

            return chain.filter(exchange)
                    .contextWrite(ctx -> ctx.put("example.gateway.routeLabel", label));
        };
    }

    public static class Config {
        private String label;

        public String getLabel() {
            return label;
        }

        public void setLabel(String label) {
            this.label = label;
        }
    }
}
~~~

Route dùng factory:

~~~yaml
filters:
  - name: RouteLabel
    args:
      label: catalog-read
~~~

Giá trị `catalog-read` là **metadata cấu hình của route** dùng cho demo, không phải danh tính hoặc quyền của người dùng.

**Chú ý:** tên mặc định của filter factory lấy từ tên class kết thúc bằng `GatewayFilterFactory`, do đó `RouteLabelGatewayFilterFactory` được khai báo với `name: RouteLabel`. Route-specific filter này chỉ chạy khi route khớp và được gắn vào route.

Nếu một filter khác cần đọc label, hãy thống nhất key và order. Không dùng cùng key cho một giá trị String trong route A nhưng Object khác ở route B; các downstream readers có thể ép kiểu sai.

### 9.1. Khi nào nên dùng GlobalFilter thay vì factory?

| Nhu cầu | Cách phù hợp |
| --- | --- |
| Request ID/trace được tạo cho mọi route Gateway | `GlobalFilter` |
| Policy chỉ dành cho route upload | Route `GatewayFilterFactory` |
| Cấu hình label/behavior riêng theo route | Factory với `Config` |
| Cần bắt cả response 401 trước route matching | `WebFilter` ở tầng WebFlux |
| Muốn log principal đã được xác thực trên route | `GlobalFilter` đọc principal một cách reactive |

Factory giúp cấu hình theo route nhưng **không tự tạo một Reactor Context toàn cục**. Context vẫn cần được ghi qua publisher/phạm vi phù hợp.

## 10. Bảo mật dữ liệu trong exchange và Context

### 10.1. Đừng coi attribute là dữ liệu đã được xác thực

Ví dụ không an toàn:

~~~java
String tenantId = exchange.getRequest()
        .getHeaders()
        .getFirst("X-Tenant-Id");

exchange.getAttributes().put("tenantId", tenantId);
~~~

Nếu client được phép tự gửi `X-Tenant-Id`, dữ liệu trong attribute **vẫn không đáng tin**. Chép một header vào map không biến header thành authenticated principal.

Với quota hoặc phân quyền, tenant ID nên xuất phát từ:

- Spring Security principal/JWT claims đã được xác minh và kiểm tra audience/issuer.
- Dịch vụ định danh hoặc policy engine tin cậy.
- Metadata nội bộ được bảo vệ bằng mTLS/chữ ký/trust boundary thích hợp.

Tương tự, `Reactor Context` chỉ là **cơ chế truyền dữ liệu**, không tự chứng thực giá trị. Không cấp quyền admin chỉ vì có `contextView.get("role") == "admin"` nếu không biết ai đặt dữ liệu và bằng chứng xác thực là gì.

### 10.2. Không đưa bí mật vào log/response header

Không log hoặc phản hồi:

- `Authorization: Bearer ...`, session cookie, refresh token.
- Password, API secret, private key, payload chứa PII.
- Mã OTP, link reset password hoặc thông tin thanh toán.
- Identity metadata chưa qua validation.

Request ID ngẫu nhiên thường phù hợp để correlation, nhưng vẫn có thể trở thành một **tracking identifier** nếu lưu dài hạn hay gắn với user. Cần retention, access control và redaction phù hợp. Không dùng request ID làm credential.

### 10.3. Scope và xóa dữ liệu

Attributes và Context thường chỉ sống trong vòng đời request/subscription, nhưng nếu bạn lưu tham chiếu của chúng vào static map, cache không có TTL hoặc một task độc lập không được quản lý, dữ liệu có thể tồn tại lâu hơn dự kiến. Điều này gây rò rỉ bộ nhớ hoặc thông tin người dùng.

Khi cần duy trì dữ liệu giữa requests, hãy dùng **session store, cache có chính sách hoặc database**, không “giữ tạm” `ServerWebExchange` hay `ContextView` trong singleton.

## 11. Thread switching, cancellation và backpressure

### 11.1. Scheduler thay đổi không có nghĩa Context biến mất

Một pipeline có thể dùng `publishOn(Schedulers.boundedElastic())` cho tác vụ phù hợp. Reactor Context vẫn thuộc subscriber chain khi operator được compose đúng. Nhưng `ThreadLocal` tự tạo không tự đi theo mọi hop.

~~~java
Mono<String> work = Mono.deferContextual(ctx ->
        Mono.just(ctx.getOrDefault("requestId", "missing")))
    .publishOn(reactor.core.scheduler.Schedulers.boundedElastic())
    .map(id -> id + "-processed")
    .contextWrite(ctx -> ctx.put("requestId", "req-123"));
~~~

Publisher này vẫn có thể trả `req-123-processed` dù scheduler thay đổi. Đừng dùng `boundedElastic` như cách “chữa” mã blocking trong filter nếu không đánh giá tác vụ và throughput; càng không gọi `block()` ngay trong event loop.

### 11.2. Cancellation và doFinally

Client có thể đóng kết nối, timeout hoặc hủy subscription. Khi ghi metrics, `doFinally` có thể thấy `SignalType.CANCEL`, bên cạnh `ON_COMPLETE` và `ON_ERROR`.

~~~java
return chain.filter(exchange)
        .doFinally(signal -> {
            // Đếm complete/error/cancel theo policy.
        });
~~~

Không suy luận `doFinally` chạy sau khi **toàn bộ backend nghiệp vụ** đã hoàn tất hoặc HTTP response đến client thành công: cancellation có thể xảy ra giữa chừng, và side effect ở backend có thể vẫn tiếp tục.

**Cảnh báo:** đừng ghi dữ liệu vào response headers trong `doFinally`; response có thể đã commit. Nếu cần response metadata, dùng `beforeCommit` hoặc pha xử lý phù hợp trước khi response viết ra.

### 11.3. Khi có Retry GatewayFilter

Với `Retry`, phần chain nằm phía sau Retry có thể được **subscribe/chạy lại**. Điều này ảnh hưởng:

- Attribute được viết lại ở mỗi attempt, nhất là counter hoặc timestamp.
- Context ở mỗi subscription được tái thiết lập qua `contextWrite`; không coi nó là mutable cache dùng chung mọi attempts.
- Log và metrics có thể đếm **số lần upstream attempt**, không phải số request client.
- Các filter nằm trước Retry có thể chỉ chạy một lần cho client request.
- Body có thể được cache khi retry request ghi, gây memory pressure.

Nếu cần một request ID **bất biến trên mọi attempts**, nên tạo nó ở filter **bên ngoài Retry** và không sinh lại ở từng attempt. Nếu cần attempt ID riêng, đặt trong phần retry-aware pipeline và ghi nhận sự khác nhau.

## 12. Các ranh giới không tự được propagate

| Ranh giới | Exchange attributes | Reactor Context | Cách truyền khi cần |
| --- | --- | --- | --- |
| Cùng Gateway filter chain | Có thể đọc cùng exchange | Có thể nếu nằm đúng Context scope | Đặt key trước khi chain, `contextWrite` đúng vị trí |
| `publishOn`/chuyển scheduler | Exchange vẫn là object được truyền tường minh | Reactor tự propagate theo chain | Không dùng ThreadLocal trực tiếp |
| New `subscribe()` độc lập | Không tự nhận, trừ khi bạn truyền exchange | Context có thể khác/không có | Compose cùng publisher; hạn chế subscription mới |
| HTTP request Gateway → upstream | **Không** | **Không** | `X-Request-Id`, W3C Trace Context theo contract |
| Nhiều HTTP requests từ một client | **Không** | **Không** | Session/token/store |
| Khác JVM/microservice | **Không** | **Không** | Protocol headers, messaging metadata, tracing |
| Spring Security WebFilter trước route | Attribute đặt sau route chưa tồn tại | Context đặt trong GlobalFilter chưa tồn tại | Đặt bridge ở WebFilter ngoài nếu cần |

Bảng giúp tránh lỗi thường gặp: một `GlobalFilter` đặt `contextWrite` không thể quay ngược thời gian để khiến Spring Security filter đã chạy trước đó đọc được giá trị.

## 13. Kiểm thử đơn vị Reactor Context

### 13.1. StepVerifier kiểm tra propagation

Ví dụ test độc lập với Gateway:

~~~java
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class ReactorContextTest {
    private static final String KEY = "example.requestId";

    @Test
    void readsContextFromSubscription() {
        Mono<String> publisher = Mono.deferContextual(context ->
                Mono.just(context.getOrDefault(KEY, "missing")));

        StepVerifier.create(
                publisher.contextWrite(ctx -> ctx.put(KEY, "req-test-42")))
            .expectNext("req-test-42")
            .verifyComplete();
    }

    @Test
    void showsMissingWithoutContextWrite() {
        Mono<String> publisher = Mono.deferContextual(context ->
                Mono.just(context.getOrDefault(KEY, "missing")));

        StepVerifier.create(publisher)
            .expectNext("missing")
            .verifyComplete();
    }
}
~~~

Đây là test cần dependency `reactor-test` và JUnit tương ứng, **không phải kết quả đã chạy**. Mục đích là chứng minh `Context` gắn với subscription và không tự có key nếu không viết vào.

### 13.2. Test exchange attribute

Với Gateway test, có thể tạo `MockServerWebExchange` và `MockServerHttpRequest` rồi kiểm tra:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.mock.http.server.reactive.MockServerHttpRequest;
import org.springframework.mock.web.server.MockServerWebExchange;

import static org.assertj.core.api.Assertions.assertThat;

class ExchangeAttributesTest {
    @Test
    void attributesBelongToExchange() {
        var request = MockServerHttpRequest.get("/api/catalog/items").build();
        var exchange = MockServerWebExchange.from(request);

        exchange.getAttributes().put(
                GatewayContextKeys.REQUEST_ID_ATTRIBUTE, "req-test-42");

        assertThat(exchange.getAttribute(
                GatewayContextKeys.REQUEST_ID_ATTRIBUTE))
            .isEqualTo("req-test-42");
    }
}
~~~

Test này cần `spring-test` và AssertJ/JUnit trên classpath phù hợp. Việc test get/put chỉ kiểm tra attributes, **chưa chứng minh Context propagation**, filter order hoặc request header được gửi đến upstream.

## 14. Kiểm thử tích hợp hai GlobalFilter

Để biết filter chạy đúng, tạo môi trường test:

- Gateway tại `http://localhost:8080`.
- Upstream mock tại `http://localhost:8081`.
- Route `GET /api/catalog/**` với `StripPrefix=1`.
- `RequestContextBridgeFilter` order -100.
- `RequestContextAuditFilter` order -90.

Gửi:

~~~bash
curl -i http://localhost:8080/api/catalog/products/42
~~~

Kỳ vọng khi upstream mock nhận được request:

~~~text
Client -> Gateway:
  GET /api/catalog/products/42

Gateway filter:
  X-Request-Id được sinh mới
  attribute requestId được ghi
  Context requestId được thêm cho chain phía trong

Gateway -> upstream mock:
  GET /catalog/products/42
  X-Request-Id: <uuid-mới>

Upstream -> Gateway -> Client:
  Response status/body theo mock
  X-Request-Id: <cùng uuid>
~~~

Kết quả là **mô tả kỳ vọng**, không phải output đã thực thi. Để assert chính xác, upstream mock cần lưu request headers và path; test nên bắt response `X-Request-Id` rồi so sánh với header upstream nhận, đồng thời đọc log/filter test hook xem `fromContext` và `fromAttribute` có giống nhau.

### 14.1. Ma trận kiểm thử

| Ca | Thay đổi | Kỳ vọng |
| --- | --- | --- |
| A1 | Gọi route khớp bình thường | Có request ID trong attributes/Context, response và upstream header |
| A2 | Gọi lại route lần thứ hai | Mã ID mới; không dùng lại state giữa requests |
| A3 | Đảo order reader thành -110 | Reader có thể chưa thấy attr/Context; test phát hiện lỗi order |
| A4 | Bỏ `contextWrite` ở filter đầu | Attribute vẫn có; `deferContextual` trả missing |
| A5 | Bỏ `exchange.getAttributes().put` | Context vẫn có; attribute thiếu |
| A6 | Header client gửi `X-Request-Id: attacker` | Filter thay bằng ID do Gateway cấp, không tin client |
| A7 | Upstream trả 503 | ID vẫn có khi chain đi qua filter; status theo upstream |
| A8 | Client đóng kết nối giữa chừng | `doFinally` có thể thấy CANCEL; không ghi response sau commit |
| A9 | Thêm Retry cho GET | Kiểm tra request ID giữ nguyên và attempt metrics đúng |
| A10 | Spring Security chặn 401 trước route | GlobalFilters có thể không chạy; xem cần WebFilter không |
| A11 | Không có route khớp | Không mặc định mong có ID từ GlobalFilter |
| A12 | Đổi scheduler bằng `publishOn` | Context vẫn hoạt động nếu nằm cùng reactive chain |
| A13 | Gọi một publisher bằng `subscribe()` riêng | Context có thể thiếu; test chỉ ra anti-pattern |

### 14.2. Cẩn thận khi đo số lần filter chạy

Khi có Retry, một request client có thể tạo nhiều upstream attempts. Nếu log chỉ in một request ID nhưng backend counter tăng 3, đó là hành vi có thể đúng của retry.

Với metrics, cần tách **client request count** khỏi **upstream attempt count**. Tránh gắn giá trị request ID vào **metric label**, vì mỗi request sinh một label mới làm cardinality tăng vô hạn. Dùng trace/log correlation cho request ID; metrics nên group theo route ID, status và loại lỗi.

## 15. Những lỗi phổ biến và cách chẩn đoán

| Triệu chứng | Nguyên nhân thường gặp | Hướng kiểm tra |
| --- | --- | --- |
| Filter B đọc attribute là `null` | A ghi sau khi gọi chain, order sai hoặc exchange khác | Kiểm tra pre-phase, `Ordered`, vị trí ghi |
| `deferContextual` trả missing | `contextWrite` sai vị trí hoặc subscription khác | Kiểm tra operator graph, key identity |
| Đọc Context bằng `ThreadLocal` trả `null` sau publishOn | Reactor Context không tự đồng bộ vào ThreadLocal | Dùng `deferContextual`, tracing bridge |
| Upstream không có X-Request-Id | Chỉ ghi attribute/Context, chưa mutate HTTP request | Kiểm tra `ServerHttpRequest.mutate().headers` |
| Client không nhận X-Request-Id khi 401 | Spring Security chặn trước Gateway GlobalFilter | Đặt logic cần thiết vào WebFilter |
| Client không nhận response header sau lỗi | Thêm header quá muộn, response đã commit | Dùng `beforeCommit` đúng thời điểm |
| Có request ID từ request khác | Lưu request state trong field singleton/static | Dùng scope request/subscription |
| Log token bị lộ qua Context | Context chứa secret rồi bị dump/log | Chỉ đưa metadata cần thiết, redact |
| Retry làm counter tăng gấp ba | Filter nằm sau Retry nên chạy lại | Kiểm tra ordering, phân biệt attempts |
| `GATEWAY_REQUEST_URL_ATTR` null | Đọc trước bước RouteToRequestUrl | Kiểm tra phase/order, không giả định tồn tại |
| Body được cache quá nhiều | Custom filter/Retry cache body không giới hạn | Limit size, concurrency, memory/backpressure |
| Context xuất hiện trong filter nhưng không tới service khác | Reactor Context không vượt network | Dùng HTTP trace headers/metadata theo contract |
| CORS/forwarded header bị nhầm với context | HTTP headers có ngữ nghĩa mạng riêng | Không xem `X-Forwarded-*` như bảo mật Context |
| Test chạy riêng thành công nhưng qua Gateway sai | Filter order, route match hoặc security layer | Integration test đầy đủ và log route ID |

### Quy trình debug ngắn

1. Request có khớp **route** không, hay bị Security chặn trước?
2. Filter nào **ghi** key, ở pre-phase hay post-phase? Order bao nhiêu?
3. Filter nào **đọc** key? Có đang dùng cùng exchange/decorator và key không?
4. Đoạn đọc Reactor Context có nằm **upstream của contextWrite** trong subscription không?
5. Có `subscribe()` độc lập, manual thread hoặc `ThreadLocal` không?
6. Header outbound được tạo bằng request decorator chưa? Backend có nhận không?
7. Response đã commit trước khi filter cố set header chưa?
8. Có Retry, timeout, cancellation hay multiple subscriptions làm thay đổi số lần chạy không?
9. Dữ liệu trong attribute/Context có phải từ principal đã xác thực hay header chưa tin cậy?
10. Có log/metric labels chứa token, cookie hoặc request ID high-cardinality không?

## 16. Bài thực hành: thêm correlation và tenant policy

**Bối cảnh:** Gateway có hai route `/api/catalog/**` và `/api/orders/**`, cả hai đi qua Spring Security và `RequestRateLimiter` theo user/tenant.

Yêu cầu:

1. Tạo `GlobalFilter` có order sớm để sinh **correlation ID**, đặt vào exchange attribute và Reactor Context.
2. Thêm `X-Request-Id` vào request gửi upstream và response về client, không tin ID client chưa được xác minh.
3. Tạo GlobalFilter khác dùng `Mono.deferContextual` đọc ID và đối chiếu attribute.
4. Nếu cần tenant ID, lấy từ **authenticated principal**, không lấy `X-Tenant-Id` do client tự gửi.
5. Quyết định tenant policy được dùng bởi rate limiter ở dạng exchange attribute, Context hay tham số tường minh; ghi lý do lựa chọn.
6. Dùng `RouteLabelGatewayFilterFactory` nếu muốn gắn nhãn route cho metrics.
7. Tạo unit test StepVerifier cho Reactor Context và MockServerWebExchange cho attributes.
8. Tạo integration test với mock upstream, assert `X-Request-Id` đi xuyên Gateway đúng một giá trị.
9. Thêm Retry **chỉ cho GET** rồi đo request ID không đổi giữa attempts; attempt counter tăng đúng.
10. Thử request bị 401 trước route; giải thích vì sao GlobalFilter không tạo header và cách WebFilter có thể giải quyết.
11. Thử client disconnect hoặc timeout; xác nhận không ghi response sau commit.
12. Quan sát p95/p99 latency, route ID, status và retry count; **không** cho request ID vào metric label.

### Checklist production

- [ ] Đã xác định rõ dữ liệu thuộc **exchange**, **reactive subscription** hay **HTTP protocol**.
- [ ] Các exchange attribute keys có namespace, không đè hằng nội bộ của Gateway.
- [ ] Dùng `contextWrite` đúng phía publisher, đọc bằng `deferContextual`.
- [ ] Không dùng `ThreadLocal`/MDC trực tiếp để thay Reactor Context nếu không có bridge.
- [ ] Không gọi `block()` hoặc `subscribe()` rời trong Gateway filter.
- [ ] Order của filter ghi/đọc dữ liệu đã được kiểm thử theo pre/post.
- [ ] Không giữ `ServerWebExchange`/ContextView ở singleton/static map sau request.
- [ ] Security principal/tenant được xác minh, không tin header client tự khai báo.
- [ ] Header gửi upstream được mutate rõ ràng, không nghĩ attribute tự vượt mạng.
- [ ] Header response được đặt trước commit, kể cả các nhánh error phù hợp.
- [ ] Có xử lý cancellation/error và đo latency bằng hook phù hợp.
- [ ] Test khi có Retry, circuit breaker, rate limiter và service discovery.
- [ ] Tránh cache body lớn, race condition khi mutate shared objects và rò rỉ DataBuffer.
- [ ] Log/tracing đã redact credential; metric labels có cardinality hữu hạn.
- [ ] Đã kiểm thử response 401/403/404 từ tầng ngoài Gateway route.
- [ ] Chỉ dùng API và namespace phù hợp phiên bản Spring Cloud Gateway WebFlux.

## 17. Tổng kết và tài liệu tham khảo

**`ServerWebExchange.getAttributes()`** phù hợp để các filter cùng một HTTP exchange chia sẻ metadata ngắn hạn, còn **Reactor `Context`** phù hợp để reactive operators mang dữ liệu qua subscription, kể cả khi thay đổi scheduler. Chúng **không tự đồng bộ**, không vượt qua HTTP network và không thay thế Spring Security principal hoặc session store.

Một custom `GlobalFilter` có thể ghi cả hai: đặt attribute trước khi gọi `chain.filter`, rồi dùng `contextWrite` để filter/reactive operator phía trong đọc bằng `Mono.deferContextual`. Khi cần service khác nhận request ID, phải chủ động mutate **HTTP header**; khi cần client nhìn thấy ID, phải đặt response header trước commit.

Để vận hành Gateway an toàn, hãy kết hợp filter order, route predicate, authentication/authorization, rate limiting, retry, circuit breaker, TLS và observability, nhưng giữ ranh giới rõ giữa request state, reactive subscriber state và network metadata.

### Tài liệu tham khảo

- [Spring Cloud Gateway Server WebFlux — Global Filters](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/global-filters.html).
- [Spring Cloud Gateway Server WebFlux — Custom GatewayFilter Factories](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/gatewayfilter-factories.html).
- [Spring Framework — ServerWebExchange API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/server/ServerWebExchange.html).
- [Project Reactor — Context, Adding a Context to a Reactive Sequence](https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html).
- [Project Reactor — Context-Propagation Support](https://projectreactor.io/docs/core/release/reference/advanced-contextPropagation.html).
