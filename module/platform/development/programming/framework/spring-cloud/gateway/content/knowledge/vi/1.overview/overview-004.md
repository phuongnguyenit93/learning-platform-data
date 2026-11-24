# Luồng yêu cầu từ client qua gateway đến dịch vụ

## 1. API Gateway đứng ở đâu trong luồng xử lý?

Trong hệ thống microservices, client thường chỉ biết một điểm truy cập chung, chẳng hạn `https://api.example.test`, thay vì phải biết địa chỉ của từng dịch vụ đơn hàng, thanh toán hay người dùng. **Spring Cloud Gateway** nhận yêu cầu HTTP tại điểm truy cập này, chọn dịch vụ đích theo quy tắc định tuyến, thực hiện các bộ lọc cần thiết rồi chuyển tiếp yêu cầu. Phản hồi từ dịch vụ đi ngược qua gateway trước khi đến client.

Đây là bài trong chương **Tổng quan** về **SPRING_CLOUD_GATEWAY**, tập trung trả lời câu hỏi: **một HTTP request thực sự đi qua những thành phần nào, ở thời điểm nào và có thể bị thay đổi hoặc chặn ở đâu?** Các khái niệm route predicate, filter chain, biến đổi đường dẫn/header và khám phá dịch vụ được đặt vào cùng một luồng. Xác thực, giới hạn lưu lượng, circuit breaker, retry, TLS và quan sát request được giới thiệu tại đúng vị trí chúng tác động lên luồng đó.

Các tên thành phần nội bộ trong bài dùng **Spring Cloud Gateway Server WebFlux** (thường chạy với Reactor Netty) làm mô hình tham chiếu. Biến thể Spring Cloud Gateway Server MVC có cơ chế tích hợp với servlet khác, dù mục đích định tuyến và lọc yêu cầu tương tự.

~~~mermaid
flowchart LR
    C["Client"] -->|"HTTPS request"| G["Gateway HTTP server"]
    G --> P{"Route predicate<br/>có khớp?"}
    P -->|"Không"| N["Không có route<br/>phù hợp"]
    P -->|"Có"| F["Filter chain:<br/>pre phase"]
    F -->|"Bị từ chối"| X["Phản hồi sớm<br/>401 / 403 / 429..."]
    F --> U["Tạo URL đích;<br/>khám phá và chọn instance"]
    U --> R["Chuyển tiếp request<br/>đến microservice"]
    R --> S["Microservice xử lý"]
    S --> B["Filter chain:<br/>post phase và ghi response"]
    B -->|"HTTP response"| C
    X --> C
    N -->|"Thường là 404"| C
~~~

Điểm mấu chốt: **route predicate quyết định request đi theo route nào; filter chain xử lý request đã chọn route; routing filter thực hiện chuyển tiếp; phần xử lý phản hồi diễn ra khi kết quả đi về.** Gateway có thể trả lời client ngay mà không gọi dịch vụ đích.

## 2. Sáu giai đoạn của một request

| Giai đoạn | Thành phần hoặc cơ chế | Điều xảy ra |
| --- | --- | --- |
| **1. Tiếp nhận** | HTTP server, WebFlux `WebFilter` (nếu cấu hình) | Nhận kết nối, xử lý HTTP/TLS ở lớp tương ứng và chạy các xử lý WebFlux như Spring Security. Một `WebFilter` có thể từ chối request ngay trước khi chọn route. |
| **2. Tìm route** | `RoutePredicateHandlerMapping` | Đánh giá các predicate của những route đã khai báo; chọn route phù hợp và gắn thông tin route vào request exchange. |
| **3. Chạy pre-filter** | `FilteringWebHandler`, `GlobalFilter`, `GatewayFilter` | Ghép và sắp xếp filter, sau đó xử lý logic trước khi gửi đi: xác thực hoặc kiểm tra policy, giới hạn lưu lượng, chỉnh path/header, ghi thông tin theo dõi. |
| **4. Xác định và gọi đích** | `RouteToRequestUrlFilter`, `ReactiveLoadBalancerClientFilter`, `NettyRoutingFilter` | Tạo URL gửi đi; nếu URI là `lb://...` thì chọn instance; cuối cùng gửi yêu cầu HTTP đến dịch vụ đích. |
| **5. Nhận kết quả** | Dịch vụ đích và gateway HTTP client | Dịch vụ trả status, headers và body; lỗi kết nối, timeout hoặc chính sách chịu lỗi có thể làm thay đổi kết quả. |
| **6. Xử lý sau và phản hồi** | Post-filter, `NettyWriteResponseFilter` | Chỉnh headers/status theo cấu hình, ghi metrics/log và chuyển response trở lại client. |

### 2.1. Route predicate được kiểm tra trước khi chạy gateway filter

Một **route** gồm tối thiểu ID, URI đích và các predicate; có thể có các filter riêng. Predicate là điều kiện chọn route theo đường dẫn, phương thức HTTP, host, header, query, thời gian... Với một route chứa nhiều predicate, các điều kiện phải cùng thỏa để route đó được chọn.

Ví dụ, `Path=/api/orders/**` và `Method=GET` chọn `GET /api/orders/42`, nhưng không chọn `POST /api/orders/42`. Việc `StripPrefix` thay đổi đường dẫn **xảy ra sau** lúc xác định route; nó không thay đổi đường dẫn đã được dùng để đối chiếu `Path`.

Nếu không có route nào khớp và cũng không có handler WebFlux khác xử lý, client thường nhận **404 Not Found**. Không nên vội kết luận rằng dịch vụ backend trả 404: request có thể chưa hề được chuyển tiếp.

### 2.2. Filter chain có hai chiều thực thi

Sau khi khớp route, `FilteringWebHandler` kết hợp hai nhóm filter:

- **`GlobalFilter`:** áp dụng cho mọi request đã được gateway gán route, ví dụ ghi thời gian xử lý hoặc quản lý correlation ID.
- **`GatewayFilter`:** gắn vào một route cụ thể, ví dụ `StripPrefix`, `SetRequestHeader`, `RequestRateLimiter` hoặc `CircuitBreaker`. Có thể có default filters áp dụng cho nhiều route.

Các filter được sắp xếp theo **order**. Trong một chuỗi gọi điển hình, filter có order thấp hơn chạy logic **pre** sớm hơn và hoàn tất logic **post** muộn hơn. Một filter có thể gọi `chain.filter(exchange)` để tiếp tục, hoặc hoàn tất response ngay để dừng chuỗi. Vì vậy, cùng một request có thể được xác thực, thêm header, định tuyến, đo độ trễ và chỉnh response tại các thời điểm khác nhau.

Phần **post** không phải một lượt gọi mới từ client. Nó là phần còn lại của cùng chuỗi reactive, được thực thi khi lời gọi xuống dưới hoàn tất (hoặc kết thúc bằng lỗi/hủy, tùy toán tử và filter).

### 2.3. `lb://` là bước tìm địa chỉ đích, không phải địa chỉ HTTP

URI `lb://orders-service` biểu thị **service ID**. Spring Cloud LoadBalancer cần danh sách instance từ cơ chế khám phá dịch vụ, ví dụ Eureka, Consul hoặc một nguồn `ServiceInstance` khác. Sau khi chọn một instance, gateway mới có địa chỉ cụ thể để gửi request, chẳng hạn `http://10.0.2.15:8080`. Muốn sử dụng `lb://`, ứng dụng cần cấu hình khám phá dịch vụ phù hợp và thành phần Spring Cloud LoadBalancer.

Nếu dùng URI tĩnh như `http://localhost:8081` thì bỏ qua bước chọn instance bằng `lb://`. Nếu không tìm được instance cho dịch vụ, gateway WebFlux thường trả **503 Service Unavailable** theo mặc định (có thể cấu hình thành 404); đó là lỗi xảy ra trước khi backend xử lý request.

## 3. Theo dấu một request cụ thể

Giả sử client gọi:

~~~http
GET /api/orders/42?expand=items HTTP/1.1
Host: api.example.test
Authorization: Bearer <access-token>
Accept: application/json
~~~

Gateway có route minh họa:

~~~yaml
spring:
  cloud:
    gateway:
      routes:
        - id: orders-api
          uri: lb://orders-service
          predicates:
            - Path=/api/orders/**
            - Method=GET
          filters:
            - StripPrefix=1
            - SetRequestHeader=X-Edge-Source, spring-cloud-gateway
~~~

> Cấu hình trên minh họa namespace `spring.cloud.gateway.routes` quen thuộc của nhiều phiên bản Spring Cloud Gateway WebFlux. Một số phiên bản mới tổ chức properties dưới `spring.cloud.gateway.server.webflux`. Cần dùng khóa cấu hình tương ứng với phiên bản Spring Cloud đang chạy; semantics của route và filter trong ví dụ vẫn như nhau.

Diễn tiến giả định:

1. **Client → gateway:** Gateway nhận `GET /api/orders/42?expand=items`. Kết nối HTTPS có thể được kết thúc TLS tại gateway hoặc tại reverse proxy phía trước, tùy cách triển khai.
2. **Chọn route:** `Path=/api/orders/**` và `Method=GET` cùng khớp. Route được chọn có ID `orders-api` và URI logic `lb://orders-service`.
3. **Pre-filter:** `StripPrefix=1` bỏ phân đoạn `api` đầu tiên, đổi đường dẫn thành `/orders/42`. Query `?expand=items` được giữ lại. `SetRequestHeader` đặt `X-Edge-Source: spring-cloud-gateway` trên request chuyển tiếp.
4. **Khám phá dịch vụ:** Gateway hỏi LoadBalancer để chọn một instance của `orders-service`. Giả sử instance được chọn có địa chỉ `10.0.2.15:8080`.
5. **Chuyển tiếp:** Gateway gửi request tương ứng với `GET http://10.0.2.15:8080/orders/42?expand=items`; service nhận path đã được biến đổi. Host, connection headers và các header forwarding thực tế phụ thuộc cấu hình proxy. Không nên giả định mọi header nhận từ client đều được chuyển nguyên xi.
6. **Service → gateway → client:** Service trả, chẳng hạn, `200 OK` cùng JSON đơn hàng. Gateway chạy các xử lý post thích hợp rồi ghi response cho client.

Có thể hình dung ranh giới trước/sau phép biến đổi như sau:

| Quan sát | Giá trị minh họa |
| --- | --- |
| URL client gọi | `https://api.example.test/api/orders/42?expand=items` |
| Route được chọn | `orders-api` |
| URI logic của route | `lb://orders-service` |
| Đường dẫn sau `StripPrefix=1` | `/orders/42` |
| Instance được chọn | `10.0.2.15:8080` |
| URL gửi xuống service | `http://10.0.2.15:8080/orders/42?expand=items` |
| Header được đặt ở gateway | `X-Edge-Source: spring-cloud-gateway` |

Địa chỉ IP và phản hồi ở đây chỉ là **ví dụ**, không phải kết quả đo được từ một hệ thống thật.

## 4. Những điểm có thể làm request dừng hoặc chuyển hướng

Luồng xử lý không luôn kết thúc bằng một cuộc gọi thành công đến backend. Cùng một request có thể đi theo các nhánh sau:

| Điểm xảy ra | Điều kiện minh họa | Kết quả thường thấy |
| --- | --- | --- |
| Trước định tuyến | Spring Security `WebFilter` không xác thực được token | **401 Unauthorized**, không cần gọi backend |
| Trong chính sách truy cập | Danh tính hợp lệ nhưng không đủ quyền | **403 Forbidden** theo chính sách được áp dụng |
| Chọn route | Không route nào khớp path/method/host | **404 Not Found** nếu không có handler khác |
| Pre-filter | `RequestRateLimiter` từ chối vì vượt hạn mức | **429 Too Many Requests** theo mặc định |
| Load balancing | Không còn instance khả dụng | Thường **503 Service Unavailable** |
| Gọi backend | Kết nối lỗi, backend lỗi hoặc quá hạn timeout | Có thể là **5xx** hoặc response fallback, tùy chính sách |
| Xử lý thông thường | Backend trả `4xx` hoặc `5xx` hợp lệ | Gateway thường chuyển response đó về; filter vẫn có thể điều chỉnh |

Các mã trạng thái là trường hợp thường gặp, không phải cam kết bất biến: filter tự viết, exception handler, cấu hình timeout/circuit breaker hoặc fallback có thể thay đổi chúng.

### Xác thực và phân quyền

Gateway là nơi thuận tiện để kiểm tra access token, chặn request không hợp lệ và áp dụng chính sách dùng chung. Tuy nhiên, **dịch vụ đích vẫn phải kiểm tra quyền đối với tài nguyên hoặc hành động thuộc sở hữu của nó**; chỉ kiểm tra token ở cổng vào không thay thế được phân quyền nghiệp vụ. Không sử dụng một header do client tự khai báo (ví dụ `X-User-Id`) làm bằng chứng danh tính nếu chưa có cơ chế xác thực và bảo vệ đường đi phù hợp.

### Giới hạn lưu lượng

Rate limiter thường chạy trước phần routing. Khi vượt ngưỡng, request bị trả về ngay, giúp backend không tốn công xử lý. Với cấu hình dùng Redis, bộ đếm/hạn mức phụ thuộc việc gateway kết nối được Redis và cách xác định khóa (người dùng, API key hoặc địa chỉ IP tin cậy). Cần nghĩ rõ hành vi khi hạ tầng rate limiter gặp lỗi.

### Circuit breaker, retry và timeout

Khi service chậm hoặc không khỏe, circuit breaker có thể từ chối một số lời gọi hoặc chuyển sang fallback nếu được cấu hình. Timeout giới hạn thời gian chờ; retry có thể khiến **một request từ client tạo ra nhiều lần gọi tới backend**. Chỉ bật retry khi hiểu tính idempotent của thao tác và khả năng đọc lại body: retry tùy tiện đối với tạo đơn hàng hay thanh toán có thể gây tác dụng phụ trùng lặp. Quan sát timeout/circuit breaker ở gateway cùng với log backend để xác định request đã được gửi đi hay chưa.

### TLS và các header từ reverse proxy

Kết nối **client → gateway** và **gateway → service** là hai chặng riêng; mỗi chặng có thể dùng HTTP, HTTPS hoặc mTLS tùy kiến trúc. Nếu có load balancer/reverse proxy phía trước, các header `Forwarded` và `X-Forwarded-*` chỉ đáng tin khi proxy gửi chúng được xác định rõ và gateway cấu hình xử lý phù hợp. Các header mô tả IP gốc, scheme hoặc danh tính không nên được chấp nhận mù quáng từ Internet.

## 5. Viết một GlobalFilter để thấy rõ pre/post

Ví dụ dưới đây đo thời gian đi qua phần còn lại của chain. Filter bắt đầu trước lời gọi xuống dưới và ghi log khi pipeline hoàn tất, lỗi hoặc bị hủy.

~~~java
import java.util.concurrent.TimeUnit;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.cloud.gateway.filter.GatewayFilterChain;
import org.springframework.cloud.gateway.filter.GlobalFilter;
import org.springframework.core.Ordered;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

@Component
public class RequestTimingFilter implements GlobalFilter, Ordered {
    private static final Logger log =
            LoggerFactory.getLogger(RequestTimingFilter.class);

    @Override
    public int getOrder() {
        return -100;
    }

    @Override
    public Mono<Void> filter(ServerWebExchange exchange,
                             GatewayFilterChain chain) {
        long start = System.nanoTime(); // pre

        return chain.filter(exchange)
                .doFinally(signal -> { // sau khi chain kết thúc
                    long ms = TimeUnit.NANOSECONDS.toMillis(
                            System.nanoTime() - start);
                    log.info("method={} path={} status={} durationMs={} signal={}",
                            exchange.getRequest().getMethod(),
                            exchange.getRequest().getURI().getPath(),
                            exchange.getResponse().getStatusCode(),
                            ms,
                            signal);
                });
    }
}
~~~

`return chain.filter(exchange)` là thao tác tiếp tục chuỗi. Trong một filter kiểm tra quyền, nếu chính sách từ chối thì filter có thể đặt status và hoàn tất response thay cho việc gọi chain. Ví dụ đo thời gian này **không làm xác thực** và không cần tự gọi `subscribe()` hay `block()`; blocking I/O trong luồng xử lý reactive có thể khiến gateway giảm khả năng phục vụ đồng thời.

Order `-100` khiến phần pre của filter này đi trước nhiều filter có order lớn hơn, còn `doFinally` chạy khi phần downstream của nó kết thúc. Thời gian đo là thời gian quan sát được tại filter, bao gồm phần chuyển tiếp và xử lý bên dưới, không phải riêng thời gian thực thi của microservice. Nếu request bị chặn ở một WebFlux `WebFilter` trước khi chọn route, `GlobalFilter` trên có thể không chạy.

## 6. Quan sát và tìm lỗi theo từng giai đoạn

Để theo dõi request xuyên nhiều dịch vụ, nên truyền **trace context** như `traceparent` và dùng Micrometer Observation/Tracing cùng cơ chế log tương ứng. Khi điều tra, dữ liệu hữu ích gồm thời điểm nhận, method/path, **route ID**, mã phản hồi, thời gian xử lý, đích đã chọn, trace ID và nguyên nhân lỗi. Tránh log access token, cookie, dữ liệu cá nhân hay nguyên body chứa thông tin nhạy cảm.

Spring Cloud Gateway có thể cung cấp metrics cho request và các endpoint Actuator hỗ trợ xem route nếu đã bật đúng thành phần và cấu hình. Ví dụ, danh sách route từ endpoint gateway của Actuator có ích để xác nhận ứng dụng đã nạp cấu hình; endpoint vận hành cần được bảo vệ, không công khai trên Internet.

Khi gặp lỗi, lần theo thứ tự:

1. **Request đã tới gateway chưa?** Kiểm tra TLS, DNS, reverse proxy phía trước và access log. Nếu lỗi xảy ra trước khi vào gateway thì route/filter không thể sửa được.
2. **Route có khớp không?** So sánh request ban đầu với predicate `Path`, `Method`, `Host` và thứ tự/độ ưu tiên của các route có khả năng cùng khớp.
3. **Pre-filter có chặn không?** Kiểm tra security, rate limiter, biến đổi đường dẫn và header; phân biệt status trả tại gateway với status từ service.
4. **URI đích có giải được không?** Với `lb://`, kiểm tra service ID, registry, các instance và trạng thái của LoadBalancer.
5. **Backend đã nhận request với path/header nào?** So sánh dữ liệu ở gateway với request thực tế tại service để phát hiện lỗi `StripPrefix`, `RewritePath` hoặc header forwarding.
6. **Response bị thay đổi ở đâu?** Đối chiếu status/body phía service với kết quả client, kết hợp post-filter, timeout, retry, circuit breaker và trace.

Ví dụ, client gọi `/api/orders/42` nhưng service chỉ khai báo `/orders/{id}`: nếu thiếu `StripPrefix=1`, route vẫn có thể **khớp thành công**, gateway vẫn **gửi request thành công**, nhưng **backend trả 404** vì nhận nhầm đường dẫn. Việc phân biệt hai kiểu 404 giúp khoanh vùng lỗi nhanh hơn.

## 7. Bài thực hành nhỏ: kiểm chứng đường đi

Có thể dựng một `orders-service` giả lập chạy tại `http://localhost:8081`, trả JSON từ endpoint `GET /orders/42`. Để thử luồng mà chưa cần service discovery, tạm thay URI của route ví dụ thành `http://localhost:8081`; giữ nguyên predicate và `StripPrefix=1`.

~~~bash
# Khớp route, service nhận GET /orders/42?expand=items
curl -i "http://localhost:8080/api/orders/42?expand=items"

# Không khớp Method=GET của route ví dụ
curl -i -X POST "http://localhost:8080/api/orders/42"

# Không khớp Path=/api/orders/**
curl -i "http://localhost:8080/api/customers/42"
~~~

Giả sử gateway lắng nghe ở cổng `8080` và không có route/handler khác cho hai request cuối, chỉ request đầu được chuyển tiếp; hai request sau nhận 404. Log từ `RequestTimingFilter` giúp quan sát các yêu cầu **đã khớp route**, còn log trên service xác nhận đường dẫn thực tế và header `X-Edge-Source`. Sau đó đổi lại `lb://orders-service` và bật discovery/LoadBalancer để thấy bước chọn instance xuất hiện giữa filter chain và backend.

**Ghi nhớ luồng chính:** client → WebFlux/TLS → chọn route bằng predicate → chạy pre-filter → xác định URL/instance → gửi đến microservice → nhận response → chạy post-filter/ghi response → client. Những cơ chế như bảo mật, rate limiting, retry, circuit breaker và observability đều gắn với một hoặc nhiều bước của chuỗi này; hiểu đúng vị trí của chúng là nền tảng để thiết kế và vận hành API Gateway an toàn.
