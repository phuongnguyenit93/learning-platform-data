# Vai trò circuit breaker trong chuỗi gọi qua gateway

## 1. Vì sao API Gateway cần circuit breaker?

Trong kiến trúc microservices, một request từ client có thể đi qua **Spring Cloud Gateway** rồi tới Order service, Inventory service hoặc Payment service. Gateway chọn route bằng predicate, áp dụng filter chain, biến đổi path/header và phân giải `lb://service-id` thành một backend cụ thể. Khi một backend mất kết nối hoặc xử lý rất chậm, request đi qua Gateway có nguy cơ phải chờ, thất bại hoặc chiếm tài nguyên quá lâu.

**Circuit breaker** (bộ ngắt mạch) là một cơ chế bảo vệ ở ranh giới gọi dịch vụ: nó quan sát kết quả những lời gọi, **tạm thời từ chối lời gọi mới** nếu tỷ lệ lỗi hoặc tỷ lệ lời gọi chậm vượt ngưỡng, rồi cho thử một số lời gọi để đánh giá khả năng phục hồi. Thay vì để mọi request tiếp tục đổ vào một dependency đang suy giảm, Gateway có thể **fail fast** và sử dụng fallback có kiểm soát.

Ví dụ:

~~~text
Client -> Gateway -> Orders service
            |
            +-- bình thường: proxy request đến Orders
            |
            +-- Orders lỗi liên tiếp:
                  Circuit breaker OPEN
                  -> bỏ qua lời gọi Orders mới
                  -> trả lỗi phù hợp hoặc fallback
~~~

Circuit breaker rất hữu ích trong **Spring Cloud Gateway** vì Gateway thường là cổng dùng chung cho nhiều route và nhiều client. Tuy nhiên nó **không phải giải pháp chữa lành backend**, không thay thế authentication, rate limiting, timeout, retry, service discovery hay giám sát request.

### Sau bài học, bạn có thể

1. Trình bày vai trò của circuit breaker trong **filter chain** và các trạng thái **CLOSED, OPEN, HALF_OPEN**.
2. Phân biệt lỗi upstream với lỗi người dùng, và hiểu **những kết quả nào được tính là thất bại**.
3. Cấu hình **CircuitBreaker GatewayFilter Factory** với **Spring Cloud CircuitBreaker + Resilience4j** trên Gateway Server WebFlux.
4. Tạo fallback nội bộ bằng `fallbackUri: forward:/...` và giữ nhất quán status, header và body.
5. Giải thích quan hệ giữa circuit breaker, timeout, retry, load balancing, TLS và connection pool.
6. Chọn cấu hình phù hợp với một dependency; tránh gộp lỗi của nhiều service vào cùng một bộ ngắt mạch.
7. Kiểm chứng OPEN/HALF_OPEN, request bị chặn không đến upstream, recovery và tác động tới người dùng.
8. Đọc metrics/events một cách an toàn để chẩn đoán sự cố thay vì chỉ nhìn mã HTTP cuối.

> **Phạm vi:** Bài thuộc chương **Ngắt mạch và dự phòng**, dùng **Spring Cloud Gateway Server WebFlux**, Spring Cloud CircuitBreaker và Reactor/Resilience4j. Server Web MVC có cơ chế khác. Tên starter, namespace YAML, property và khả năng hỗ trợ chi tiết phụ thuộc phiên bản; cần đối chiếu dependency BOM đã dùng.

## 2. Một lời gọi đi qua những lớp nào?

Trong Gateway Server WebFlux, một request được chọn route rồi đi qua các **GlobalFilter** và **GatewayFilter**. Khi route gắn `CircuitBreaker`, filter bao bọc phần xử lý downstream thuộc chuỗi mà nó điều khiển.

~~~mermaid
flowchart TD
    C[Client request] --> S[Spring Security / WebFlux filters]
    S --> M[RoutePredicateHandlerMapping]
    M --> H[FilteringWebHandler]
    H --> P[Path, header filters]
    P --> B[CircuitBreaker GatewayFilter]
    B --> Q{Circuit permits call?}
    Q -->|CLOSED or permitted probe| D[Downstream filter chain]
    D --> L[LoadBalancer if lb scheme]
    L --> N[Netty HTTP routing]
    N --> U[Orders upstream]
    U --> R[Gateway response]
    Q -->|OPEN, call denied| F[Short-circuit / fallback]
    F --> R
~~~

Sơ đồ minh họa quan hệ logic, **không thay thế thứ tự filter cụ thể** trong ứng dụng. Gateway có các thành phần như `RouteToRequestUrlFilter`, `ReactiveLoadBalancerClientFilter`, `NettyRoutingFilter` và `NettyWriteResponseFilter`. Một số filter có thể chạy pre/post khác nhau theo order; muốn hiểu lời gọi nào được breaker theo dõi, phải kiểm tra **thứ tự filter** và loại lỗi thực sự phát sinh.

### Cơ chế bao bọc một Publisher reactive

Trong WebFlux, `GatewayFilter.filter(exchange, chain)` trả về `Mono<Void>`. Publisher này biểu diễn tiến trình bất đồng bộ của request, không có nghĩa response không có body.

~~~java
// Mã khái niệm, không phải implementation của CircuitBreaker GatewayFilter:
Mono<Void> downstream = chain.filter(exchange);
return protectWithCircuitBreaker(downstream);
~~~

Lớp bảo vệ theo dõi **tín hiệu hoàn tất/lỗi** hoặc kết quả HTTP được cấu hình để tính là thất bại. Nếu breaker đang OPEN, nó có thể không cho tiến trình downstream tương ứng bắt đầu và chuyển ngay sang nhánh fallback. Không nên tự `subscribe()` hay `block()` trong một GatewayFilter, vì làm như vậy có thể phá lifecycle, backpressure và cancellation.

### Ba quyết định độc lập trong request

| Thành phần | Câu hỏi nó trả lời | Điều nó không tự làm |
| --- | --- | --- |
| Route predicate | Request khớp route nào? | Không xác thực danh tính hay bảo đảm backend khỏe |
| Authentication/authorization | Caller có quyền tới API này không? | Không bảo vệ kết nối chậm hoặc backend đang lỗi |
| Circuit breaker | Có nên tiếp tục gọi dependency này ngay lúc này? | Không cấp quyền, không sửa request và không tự tạo response nghiệp vụ đúng |

**Bộ ngắt mạch phải bổ sung cho chính sách bảo mật**, không mở đường vòng. Ví dụ, một fallback không được trả thông tin đơn hàng nhạy cảm cho người dùng chưa được xác thực chỉ vì backend Orders không có sẵn.

## 3. Các trạng thái CLOSED, OPEN và HALF_OPEN

Mô hình phổ biến của circuit breaker gồm ba trạng thái:

~~~mermaid
stateDiagram-v2
    [*] --> CLOSED
    CLOSED --> OPEN: Failure rate / slow-call rate vượt ngưỡng sau đủ mẫu
    OPEN --> HALF_OPEN: Hết thời gian chờ, có attempt thăm dò
    HALF_OPEN --> CLOSED: Các probe đáp ứng điều kiện phục hồi
    HALF_OPEN --> OPEN: Probe cho thấy dependency vẫn suy giảm
~~~

| Trạng thái | Request mới | Điều được ghi nhận |
| --- | --- | --- |
| **CLOSED** | Thông thường được cho đi tới downstream | Thành công, thất bại và có thể cả slow call trong sliding window |
| **OPEN** | Lời gọi được bảo vệ thường bị từ chối ngay | Số lời gọi không được phép, thời gian chờ đến giai đoạn phục hồi |
| **HALF_OPEN** | Chỉ một số lời gọi thăm dò được cho qua | Kết quả probe quyết định chuyển về CLOSED hay trở lại OPEN |

**CLOSED không có nghĩa backend luôn tốt.** Nó chỉ cho biết breaker vẫn cho phép gọi dựa trên số liệu và điều kiện hiện tại. Một lỗi đơn lẻ không nhất thiết mở mạch. Khi chưa đạt `minimumNumberOfCalls`, bộ ngắt mạch thường chưa đủ mẫu để áp ngưỡng failure rate.

**OPEN không có nghĩa Gateway trả về HTTP 503 trong mọi cấu hình.** Kết quả phụ thuộc có `fallbackUri` không, cách fallback tạo status/body và error handler. Lời gọi bị chặn thường được biểu diễn bằng một loại exception như `CallNotPermittedException` ở lớp Resilience4j; status cuối cùng phải được thiết kế, không suy diễn chỉ từ trạng thái OPEN.

**HALF_OPEN không có nghĩa mở hoàn toàn lưu lượng.** Chỉ một số request được cho đi thăm dò; request khác có thể tiếp tục bị từ chối. Khi đủ kết quả, breaker quyết định quay về CLOSED hay OPEN theo chính sách.

### Dòng thời gian minh họa

~~~text
00:00  CLOSED      Các request Orders đi qua
00:10  CLOSED      Tỷ lệ lỗi tăng, nhưng chưa đủ mẫu
00:15  OPEN        Đã đủ mẫu và vượt ngưỡng lỗi
00:16  OPEN        Request mới fail fast / fallback; không gọi Orders
00:45  HALF_OPEN   Cho một số lời gọi thăm dò
00:46  CLOSED      Thăm dò đủ tốt, tiếp tục nhận lưu lượng
~~~

Các mốc trên **chỉ minh họa**, không phải hành vi mặc định theo từng giây. Thời điểm chuyển trạng thái, lịch thăm dò và cách tính tỷ lệ phụ thuộc cấu hình như `slidingWindowSize`, `minimumNumberOfCalls`, `failureRateThreshold`, `waitDurationInOpenState` và `permittedNumberOfCallsInHalfOpenState`. Một số triển khai chuyển OPEN → HALF_OPEN **khi có lời gọi đến sau thời gian chờ**, không nhất thiết chủ động bằng timer.

### Các trạng thái đặc biệt

Resilience4j còn có các trạng thái đặc biệt như `DISABLED`, `FORCED_OPEN` và `METRICS_ONLY` tùy API/version và thao tác quản lý. Chúng có ý nghĩa khác chu kỳ CLOSED/OPEN/HALF_OPEN thông thường; chỉ dùng khi có quy trình vận hành, phân quyền và giám sát phù hợp. **Đừng xem FORCED_OPEN là công cụ bảo trì không có hệ quả đối với client**.

## 4. Khi nào một cuộc gọi được tính là lỗi?

Một điểm dễ sai là nghĩ rằng “cứ HTTP 4xx/5xx đều làm breaker mở”. **Các tín hiệu được breaker tính là thất bại phụ thuộc vào lớp GatewayFilter, ngoại lệ và cấu hình**.

Ví dụ:

| Kết quả | Có nên coi là lỗi dependency? | Lý do |
| --- | --- | --- |
| Kết nối bị từ chối | Thường có | Dependency không truy cập được |
| TCP connect / TLS handshake lỗi | Thường có | Gateway không thiết lập được kết nối hợp lệ |
| HTTP client response timeout | Thường có khi nó phát exception được breaker theo dõi | Upstream không phản hồi đúng deadline |
| HTTP 503 do backend trả | Có thể, nếu cấu hình nhận status này là failure | Backend báo không sẵn sàng |
| HTTP 502 do proxy/backend trả | Có thể, tùy contract/statusCodes | Lỗi gateway/upstream chain |
| HTTP 500 của backend | Có thể, nếu lỗi thuộc loại cần bảo vệ | Internal server error cần điều tra |
| HTTP 404 vì order không tồn tại | **Thường không** | Kết quả nghiệp vụ bình thường của API tìm kiếm tài nguyên |
| HTTP 400 do request không hợp lệ | **Thường không** | Caller cần sửa input, không phải backend hỏng |
| HTTP 401/403 do thiếu quyền | **Không nên** | AuthN/AuthZ là ranh giới bảo mật; không biến thành fallback thành công |
| HTTP 429 do Gateway rate limit | **Không nên** | Bảo vệ lưu lượng tại biên, không chứng minh upstream lỗi |
| Client tự hủy request | Phụ thuộc cấu hình và nguyên nhân | Không mặc định là lỗi backend; cần quan sát cancellation |

Với **CircuitBreaker GatewayFilter**, các exception phát ra khi downstream xử lý thường có thể bị tính là thất bại. Nếu backend trả **một HTTP response bình thường với status 500**, nó có thể vẫn là một luồng reactive hoàn tất thành công về mặt signal; muốn breaker phân loại một số status, các phiên bản Gateway hỗ trợ đối số `statusCodes` ở filter để kích hoạt xử lý tương ứng.

Vì vậy, không thể chỉ nhìn client nhận 500 rồi kết luận failure count của Resilience4j đã tăng. Hãy cấu hình **những mã nào thật sự cần tính**, xác minh bằng metrics/events, và tránh gom mọi 4xx vào ngắt mạch.

### Vì sao không “bắt tất cả” làm fallback?

Nếu circuit breaker bọc cả exception từ logic xác thực hoặc kiểm tra request trong filter chain, một lỗi do caller gây ra có thể bị biến thành lỗi upstream và fallback. Điều đó làm sai status, làm mờ audit và có nguy cơ che lấp lỗi bảo mật. Hãy giới hạn phạm vi filter, quyết định loại exception/status cần ghi nhận, và để Spring Security xử lý 401/403 ở đúng lớp.

## 5. Circuit breaker khác timeout, retry, rate limiter và load balancer

Nhiều cơ chế cùng xử lý độ tin cậy, nhưng chúng trả lời những câu hỏi khác nhau:

| Cơ chế | Mục tiêu chính | Nếu thiếu hoặc dùng sai |
| --- | --- | --- |
| **Connect/response timeout** | Giới hạn một thao tác có thể chờ bao lâu | Request có thể giữ connection và tài nguyên quá lâu |
| **Retry** | Thử lại một lỗi tạm thời theo điều kiện | Có thể tăng tải, tạo request trùng hoặc lặp side effect |
| **Circuit breaker** | Ngừng gọi tạm thời khi dependency suy giảm | Không tự đặt timeout hoặc sửa backend lỗi |
| **Rate limiter** | Giới hạn lưu lượng client gửi vào Gateway | Không tự nhận biết service đang hỏng |
| **Load balancer** | Chọn một ServiceInstance | Không bảo đảm instance được chọn khỏe mạnh |
| **Bulkhead** | Giới hạn tài nguyên/concurrency theo nhóm | Circuit breaker không thay thế isolation |
| **Fallback** | Tạo kết quả thay thế có hợp đồng rõ | Có thể che lỗi hoặc trả dữ liệu không hợp lệ |
| **Health/readiness** | Phản ánh khả năng sẵn sàng của một instance/service | Registry có thể còn stale trong ngắn hạn |

### Không có timeout thì mạch có thể mở rất chậm

Giả sử nhiều request gửi tới một backend **treo vô hạn** mà không phát lỗi. Nếu không có timeout, các cuộc gọi chờ lâu có thể chưa tạo kết quả thất bại cho bộ ngắt mạch đánh giá. Circuit breaker **không tự động biến mọi lời gọi thành một lời gọi có deadline**. Với một số cấu hình Resilience4j, slow-call threshold đo thời lượng đã hoàn tất, còn một lời gọi đang treo không tự trở thành lỗi chỉ vì nó “chậm”.

Một giải pháp thường cần **response timeout/TimeLimiter phù hợp** bên cạnh circuit breaker. Phải hiểu timeout do HTTP client, Gateway route, proxy, TimeLimiter hay client đặt; chúng có thể có ngữ nghĩa khác nhau về thời điểm bắt đầu đếm và phản ứng với stream.

### Retry có thể làm quá tải backend đang yếu

Nếu một request đi qua Retry filter và được gửi 3 lần, một đợt 1.000 request từ client có thể tạo tối đa hàng nghìn lượt gọi backend bổ sung. Circuit breaker có thể ngăn dồn tải khi dependency hỏng, nhưng **thứ tự Retry và CircuitBreaker trong filter chain** quyết định breaker nhìn thấy từng attempt hay một kết quả tổng. Phải kiểm chứng theo order của ứng dụng, không suy đoán từ thứ tự chữ trong YAML.

**Không retry tùy tiện POST thanh toán/đặt đơn hàng.** Nếu backend đã xử lý request nhưng response mất, retry có thể tạo side effect lặp. Cần idempotency key, deadline, chính sách retry hạn chế và kiểm thử.

## 6. Công nghệ nền: Spring Cloud CircuitBreaker và Resilience4j

Trong Spring Cloud Gateway Server WebFlux, **CircuitBreaker GatewayFilter Factory** dựa trên abstraction **Spring Cloud CircuitBreaker**. Một implementation phổ biến là **Resilience4j**, cung cấp state machine, sliding window, thresholds và metrics/events.

~~~mermaid
flowchart LR
    G[Gateway CircuitBreaker filter] --> A[Spring Cloud CircuitBreaker abstraction]
    A --> R[Resilience4j reactive implementation]
    R --> W[Sliding window + thresholds]
    W --> S[CLOSED / OPEN / HALF_OPEN]
    R --> M[Events / metrics]
~~~

Một dependency Maven thường dùng khi dự án đã quản lý phiên bản bằng Spring Cloud BOM:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-circuitbreaker-reactor-resilience4j</artifactId>
</dependency>
~~~

Ngoài dependency đó, ứng dụng cần **starter Spring Cloud Gateway Server WebFlux**, Spring Boot tương thích và cơ chế proxy HTTP phù hợp. Tên các starter Gateway có thể thay đổi theo dòng phát hành; không tự gắn một version Resilience4j bất kỳ tách khỏi dependency management của dự án.

### Những khái niệm phải phân biệt

| Tên | Vai trò |
| --- | --- |
| **Spring Cloud Gateway CircuitBreaker filter** | Bao bọc lời gọi downstream thuộc route |
| **Spring Cloud CircuitBreaker** | API abstraction để dùng backend resiliency implementation |
| **Resilience4j CircuitBreaker** | State machine + điều kiện cho phép/từ chối cuộc gọi |
| **Resilience4j TimeLimiter** | Có thể giới hạn thời gian một operation khi được tích hợp đúng |
| **Micrometer/Actuator** | Thu thập, công bố metrics/events phù hợp khi được bật |

Circuit breaker không **tự biết** trạng thái của toàn bộ cluster. Những thống kê thường gắn với **instance/application process** hoặc circuit được tạo trong nó. Nếu Gateway có 5 replica, cùng tên breaker trên 5 replica không mặc nhiên chia sẻ một bộ đếm phân tán. Điều đó ảnh hưởng thời điểm mở mạch khi mỗi replica quan sát lưu lượng khác nhau.

## 7. Khai báo CircuitBreaker GatewayFilter cho một route

Ví dụ Orders service được đăng ký trong service discovery với service ID `orders-service`. Client gọi `GET /api/orders/42`, còn backend có endpoint `GET /orders/42`. Gateway dùng `StripPrefix=1` để bỏ `api` trước khi proxy:

~~~yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: orders-read
              uri: lb://orders-service
              predicates:
                - Path=/api/orders/**
                - Method=GET
              filters:
                - StripPrefix=1
                - name: CircuitBreaker
                  args:
                    name: ordersCircuitBreaker
                    fallbackUri: forward:/internal/fallback/orders
                    statusCodes:
                      - 500
                      - 502
                      - 503
~~~

**Các thành phần:**

- `id: orders-read` là tên route để theo dõi lưu lượng và cấu hình; nó không phải tên breaker.
- `uri: lb://orders-service` dùng **Spring Cloud LoadBalancer** cùng nguồn ServiceInstance để chọn instance. Cần dependency load balancer và discovery/supplier thích hợp.
- `Path=/api/orders/**` và `Method=GET` xác định nhóm request đi qua route. Giới hạn GET trong ví dụ giúp fallback dễ có hợp đồng rõ ràng.
- `StripPrefix=1` làm backend nhận `/orders/42` thay vì `/api/orders/42`. Nó không tự quyết định lỗi hay fallback.
- `name: ordersCircuitBreaker` định danh breaker để áp dụng cấu hình Resilience4j tương ứng.
- `fallbackUri: forward:/internal/fallback/orders` chỉ tới **handler nội bộ** trong ứng dụng Gateway theo cơ chế `forward:`; không phải gọi một URL Internet bất kỳ.
- `statusCodes` chỉ ra một số status của upstream mà Gateway có thể coi là lỗi để kích hoạt cơ chế breaker/fallback, nếu phiên bản CircuitBreaker GatewayFilter đang dùng hỗ trợ cú pháp này.

**Điểm đặc biệt về status:** Một HTTP response 500 hoặc 503 từ backend không nhất thiết tạo reactive `onError`. `statusCodes` giúp nối cách hiểu HTTP status với cơ chế breaker. Nhưng không phải mọi lỗi, ví dụ 404 hợp lệ hoặc 401/403 từ Spring Security, đều nên đưa vào danh sách này.

### Tương thích phiên bản và môi trường

Ở một số phiên bản **Gateway Server WebFlux** trước, routes nằm dưới:

~~~yaml
spring:
  cloud:
    gateway:
      routes:
        # các route definitions của phiên bản tương ứng
~~~

Trong những dòng mới có thể là `spring.cloud.gateway.server.webflux.routes`. **Không chép đồng thời hai namespace để mong tự động hoạt động ở mọi release.** Kiểm tra starter, metadata cấu hình và thực tế route được nạp. Cũng cần kiểm tra API CircuitBreaker/statusCodes của phiên bản đang dùng. Ví dụ là thiết kế thực hành, **không phải cấu hình đã được chạy và chứng nhận trên mọi bản Spring Cloud Gateway**.

### Nếu cần một fallback ở service khác

`fallbackUri` của Gateway CircuitBreaker trong các dòng WebFlux thường yêu cầu scheme `forward:` để chuyển đến **handler trong ứng dụng Gateway**. Nếu muốn gọi một fallback service khác, cần thiết kế route/forward handler trung gian phù hợp, xác thực và phân quyền outbound, đồng thời bảo vệ việc fallback tiếp tục thất bại. Không tự đổi `fallbackUri` thành `http://other-service` rồi mặc định factory sẽ hỗ trợ.

## 8. Cấu hình Resilience4j cho tên breaker đã khai báo

Resilience4j có thể khai báo ngưỡng và sliding window qua cấu hình. Ví dụ:

~~~yaml
resilience4j:
  circuitbreaker:
    instances:
      ordersCircuitBreaker:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        slowCallRateThreshold: 70
        slowCallDurationThreshold: 2s
        waitDurationInOpenState: 30s
        permittedNumberOfCallsInHalfOpenState: 3
~~~

Các giá trị trên là **số liệu minh họa**, không phải default thích hợp cho mọi service:

| Tham số | Ý nghĩa trong ví dụ |
| --- | --- |
| `slidingWindowType: COUNT_BASED` | Đánh giá số cuộc gọi gần nhất, thay vì cửa sổ tính theo thời gian |
| `slidingWindowSize: 20` | Xem tối đa 20 kết quả lời gọi gần nhất trong cửa sổ |
| `minimumNumberOfCalls: 10` | Chờ ít nhất 10 cuộc gọi được ghi nhận trước khi đánh giá ngưỡng |
| `failureRateThreshold: 50` | Ngưỡng tỷ lệ cuộc gọi bị coi là thất bại, theo phần trăm |
| `slowCallRateThreshold: 70` | Ngưỡng tỷ lệ lời gọi chậm, theo phần trăm |
| `slowCallDurationThreshold: 2s` | Lời gọi hoàn tất lâu hơn ngưỡng được xem là chậm |
| `waitDurationInOpenState: 30s` | Khoảng thời gian OPEN trước khi có thể chuyển sang thử hồi phục |
| `permittedNumberOfCallsInHalfOpenState: 3` | Giới hạn số lượt thăm dò trong HALF_OPEN |

### Cách đọc threshold qua số liệu

Giả sử có 10 lời gọi được ghi nhận, 6 lỗi phù hợp với failure policy:

~~~text
Số gọi được ghi nhận : 10
Số lỗi được tính      :  6
Failure rate         : 60%
Threshold minh họa   : 50%
Kết quả              : Đủ điều kiện mở mạch
~~~

Nếu chỉ 4/10 lỗi (40%), cấu hình minh họa chưa đạt **failure-rate threshold**; nhưng vẫn có thể đạt **slow-call-rate threshold** nếu nhiều request hoàn tất chậm hơn 2 giây. Một request có thể vừa chậm vừa thất bại; cách thống kê và cửa sổ do Resilience4j điều khiển.

**Đừng nhầm minimumNumberOfCalls với maxConcurrency.** Breaker không phải semaphore bulkhead; `minimumNumberOfCalls` là số mẫu tối thiểu phục vụ đánh giá tỷ lệ, **không** phải giới hạn 10 request đồng thời.

### Một số câu hỏi trước khi chọn ngưỡng

1. Service nhận bao nhiêu request mỗi giây và có burst lớn không?
2. Lỗi đích thực của dependency gồm những exception và status nào?
3. Latency SLO là bao nhiêu? Ngưỡng slow call nên phản ánh hành vi phục vụ thực, không chỉ tùy ý chọn 2 giây.
4. Một khi OPEN, có fallback nào **thực sự an toàn** để trả cho client không?
5. HALF_OPEN được phép bao nhiêu probe mà không tạo tải tăng đột ngột?
6. Có nhiều Gateway replica không? Mỗi replica có thể mở mạch ở thời điểm khác nhau.
7. Có dependency nào cần breaker riêng theo tenant/service operation không?

Khi số lượng request thấp, một breaker dùng cửa sổ rất ngắn có thể mở vì vài lỗi cá biệt, còn cửa sổ rất dài có thể chậm phản ứng. Cần thử theo lưu lượng thực tế và quan sát false positives/false negatives.

## 9. Viết fallback nội bộ đúng hợp đồng HTTP

Nếu route `orders-read` không thể gọi Orders, Gateway có thể forward đến một WebFlux handler cục bộ và gửi phản hồi dễ hiểu, nhất quán:

~~~java
import java.util.Map;

import org.springframework.http.CacheControl;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
class OrdersFallbackController {

    @GetMapping(
            path = "/internal/fallback/orders",
            produces = MediaType.APPLICATION_JSON_VALUE
    )
    Mono<ResponseEntity<Map<String, Object>>> ordersUnavailable() {
        Map<String, Object> payload = Map.of(
                "code", "ORDERS_TEMPORARILY_UNAVAILABLE",
                "message", "Không thể lấy đơn hàng lúc này",
                "retryable", true
        );

        return Mono.just(
                ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
                        .contentType(MediaType.APPLICATION_JSON)
                        .cacheControl(CacheControl.noStore())
                        .body(payload)
        );
    }
}
~~~

Đoạn trên trả **503 Service Unavailable**, body JSON và `Cache-Control: no-store`. Nó không giả vờ đơn hàng đã được truy vấn thành công và không xuất stack trace hoặc token. `Content-Length` có thể được framework tính/điều chỉnh khi serialize body; không tự đặt theo số ký tự tiếng Việt.

**Quan trọng:** Đây là controller **chỉ nên được gọi thông qua luồng fallback được kiểm soát**. Vì một endpoint WebFlux cục bộ cũng có thể được gọi trực tiếp nếu ứng dụng mở đường vào, phải hạn chế truy cập HTTP ngoài tới `/internal/fallback/orders` bằng bảo vệ routing/security thích hợp. Không cho phép ai gọi trực tiếp fallback để lấy dữ liệu nhạy cảm. Khi dùng `forward:`, cách WebFilter/security được kích hoạt lại khi dispatch nội bộ có thể khác request HTTP mới; cần kiểm tra cả nhánh **gọi trực tiếp** và **forward nội bộ**.

### Fallback không phải lúc nào cũng nên trả dữ liệu giả

| API hoặc tình huống | Fallback có thể phù hợp | Điều không nên làm |
| --- | --- | --- |
| Danh sách sản phẩm public | Trả dữ liệu cache còn hợp lệ, có ghi rõ tính stale nếu contract cho phép | Trả hàng tồn kho hiện tại từ cache cũ rồi khẳng định chắc chắn |
| Đọc đơn hàng cá nhân | 503 + thông báo thử lại hoặc dữ liệu đã xác thực từ nguồn dự phòng đáng tin | Tạo đơn hàng “không tồn tại” để che lỗi upstream |
| Giá/ưu đãi | Dữ liệu dự phòng đã được xác minh theo chính sách | Gửi giá sai dẫn tới quyết định mua hàng sai |
| Đặt đơn, thanh toán | Thường trả lỗi tạm thời hoặc trạng thái pending đã có hệ thống xác nhận | Trả 200/201 thành công khi thao tác thực tế chưa được xác nhận |
| Authentication/authorization | Giữ mô hình fail closed khi nguồn quyền không sẵn sàng | Dùng fallback mở quyền truy cập hoặc bỏ qua JWT verification |

**Fallback là một phần của API contract.** Nó phải nói đúng “request chưa được xử lý”, “dữ liệu tạm thời không có sẵn”, hoặc “dữ liệu cache có thể cũ” theo tình huống. Không biến các thao tác ghi thành “thành công” chỉ để client không thấy 5xx.

### Có cần Retry-After?

Với 503, có thể gửi `Retry-After` nếu có **cơ sở hợp lý** để hướng dẫn client. Không đặt `Retry-After: 30` chỉ vì `waitDurationInOpenState=30s`: mốc OPEN của breaker là cơ chế nội bộ, **không bảo đảm** Orders sẽ phục hồi đúng 30 giây hoặc mọi Gateway replica có cùng trạng thái.

## 10. Chuỗi request thành công, lỗi và mạch OPEN

Với route và fallback ở trên, có ba nhánh quan trọng.

### 10.1. CLOSED và upstream hoạt động

~~~mermaid
sequenceDiagram
    participant C as Client
    participant G as Gateway
    participant CB as CircuitBreaker
    participant O as Orders
    C->>G: GET /api/orders/42
    G->>CB: Protected downstream call
    CB-->>G: Permit call (CLOSED)
    G->>O: GET /orders/42
    O-->>G: 200 order JSON
    G-->>C: 200 order JSON
~~~

Một 200 ở client không tự khẳng định breaker đã ghi nhận thành công cho backend: cần xem status/error classification và timing. Nhưng trong trường hợp phổ biến, downstream hoàn tất bình thường sẽ được breaker ghi là thành công.

### 10.2. CLOSED nhưng upstream trả lỗi được cấu hình

~~~mermaid
sequenceDiagram
    participant C as Client
    participant G as Gateway
    participant CB as CircuitBreaker
    participant O as Orders
    participant F as Local fallback
    C->>G: GET /api/orders/42
    G->>CB: Protected call
    CB-->>G: Permit
    G->>O: GET /orders/42
    O-->>G: 503 Service Unavailable
    G->>CB: Classified failure (configured 503)
    CB-->>G: Fallback path
    G->>F: forward:/internal/fallback/orders
    F-->>C: 503 JSON fallback
~~~

Khi status được cấu hình là lỗi của breaker, lời gọi có thể tăng failure metric và đi vào fallback. Cách chuyển status thành lỗi và chuyển đến fallback phụ thuộc Gateway filter implementation/version; **kiểm thử bằng backend stub thay vì chỉ nhìn sơ đồ**.

### 10.3. OPEN: chặn trước khi gọi Orders

~~~mermaid
sequenceDiagram
    participant C as Client
    participant G as Gateway
    participant CB as CircuitBreaker
    participant O as Orders
    participant F as Local fallback
    C->>G: GET /api/orders/42
    G->>CB: Request permit
    CB-->>G: Denied (OPEN)
    Note over G,O: Không thực hiện HTTP call Orders
    G->>F: forward:/internal/fallback/orders
    F-->>C: 503 JSON fallback
~~~

**Giá trị cốt lõi:** khi OPEN, request được bảo vệ **không tiếp tục tới dependency** trên nhánh đó. Như vậy Gateway có thể giảm chờ đợi và giảm lưu lượng vào service đang suy giảm. Điều đó không có nghĩa tất cả request vào Gateway bị chặn: các route khác, thậm chí các breaker khác, vẫn có thể hoạt động bình thường.

## 11. Fallback trong Gateway khác fallback tại backend

Một service có thể có logic dự phòng riêng, chẳng hạn Orders gọi Inventory rồi thay dữ liệu tồn kho bằng cache. Nếu Gateway lại có một circuit breaker của route Orders, phải hiểu hai vòng bảo vệ:

~~~mermaid
flowchart LR
    Client --> GatewayCB[Gateway breaker: Orders API]
    GatewayCB --> Orders[Orders service]
    Orders --> ServiceCB[Orders breaker: Inventory dependency]
    ServiceCB --> Inventory[Inventory service]
    ServiceCB --> LocalCache[Approved local fallback]
    GatewayCB --> GatewayFallback[Gateway fallback: 503 / safe degraded response]
~~~

- **Breaker tại Gateway** quan sát lời gọi **Gateway → Orders** và giảm tác động lên client, connection pool và Gateway khi Orders mất khả năng phục vụ.
- **Breaker tại Orders** quan sát lời gọi **Orders → Inventory**, có thông tin nghiệp vụ chi tiết hơn và có thể dùng cache/nguồn thay thế phù hợp.
- Nếu Orders trả **200 với dữ liệu degraded** do fallback nội bộ, breaker tại Gateway có thể xem request đó thành công. Do vậy cần **metric/tag riêng cho degraded/fallback**, không chỉ dựa vào HTTP status.
- Một circuit breaker tại Gateway không thể biết giao dịch trong Orders đã commit DB hay chưa nếu response bị mất. Không dùng fallback để kết luận một thao tác ghi đã thất bại hoàn toàn.

**Chọn vị trí đặt breaker theo dependency boundary.** Gateway phù hợp với bảo vệ lớp proxy và API route; service thường phù hợp với fallback gắn nghiệp vụ và kiểm soát tính nhất quán dữ liệu.

## 12. Kết hợp circuit breaker với timeout

Một breaker hoạt động hiệu quả hơn khi mỗi lời gọi có **giới hạn thời gian phù hợp**. Trong Spring Cloud Gateway Server WebFlux, HTTP client thường được cấu hình qua các property của Gateway/Reactor Netty:

~~~yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          httpclient:
            connect-timeout: 3000
            response-timeout: 5s
~~~

Ví dụ trên minh họa **TCP connect timeout** và **HTTP client response timeout** ở lớp gọi backend. Cách hiểu chính xác `response-timeout` và đơn vị của `connect-timeout` phụ thuộc phiên bản. Với các phiên bản Gateway cũ, prefix có thể là `spring.cloud.gateway.httpclient`. Đừng suy diễn rằng `response-timeout: 5s` là tổng deadline từ khi client bắt đầu gửi request đến khi hoàn tất body trong mọi loại traffic.

### Tại sao timeout giúp circuit breaker?

Giả sử Orders trả bình thường trong 150 ms nhưng khi suy giảm có thể không gửi byte nào trong hàng phút:

~~~text
Không có timeout:
Gateway -> Orders -> chờ rất lâu...
                  -> ít lỗi hoàn tất để breaker đo
                  -> resource bị giữ

Có timeout phù hợp:
Gateway -> Orders -> hết response deadline
                  -> lỗi timeout
                  -> breaker ghi nhận thất bại (nếu rule tính loại lỗi đó)
                  -> có thể OPEN khi đạt ngưỡng
~~~

**Không phải cứ có circuit breaker là Gateway tự tạo timeout.** Cũng không nên đặt timeout quá ngắn đến mức request hợp lệ bị cắt, làm tăng false failure và khiến breaker mở không cần thiết.

### Những timeout khác nhau

| Timeout | Chặn sự cố ở giai đoạn nào? | Lưu ý |
| --- | --- | --- |
| Pool acquire | Chờ kết nối còn trống trong pool Reactor Netty | Không phải TCP connect |
| TCP connect | Tạo socket mới tới instance | Có thể lỗi trước HTTP request |
| TLS handshake | Đàm phán TLS với upstream HTTPS | Lỗi chứng chỉ/hostname không khắc phục bằng retry vô hạn |
| HTTP response | Chờ response hoặc tiến triển nhận dữ liệu theo API/version | Không tự đồng nghĩa deadline toàn request |
| TimeLimiter | Giới hạn thời lượng một publisher/operation khi tích hợp | Cần cấu hình phù hợp, không mặc định mọi breaker đều có |
| Client deadline | Giới hạn end-to-end do client áp | Gateway không kiểm soát toàn bộ |
| Ingress/mesh timeout | Giới hạn do proxy trung gian áp | Có thể trả lỗi trước Gateway hoặc backend |

**Streaming là ngoại lệ quan trọng:** SSE, WebSocket, NDJSON và tải xuống lớn có thể tồn tại rất lâu. Một response timeout tối ưu cho JSON API ngắn có thể cắt stream đang hoạt động hợp lệ. Tách route/policy theo workload và kiểm thử cả khi stream **ngừng gửi dữ liệu trong một khoảng**.

### Định nghĩa failure cho timeout

Timeout do HTTP client phát ra có thể được chuyển thành exception trong pipeline; Resilience4j thường có thể ghi nhận đó là thất bại khi exception thuộc nhóm được tính. Nhưng timeout xảy ra **trước breaker**, **ngoài phạm vi filter** hoặc bị filter khác chuyển thành response có status không được tính có thể làm breaker không nhìn thấy lỗi. Hãy kiểm chứng bằng event/metric thật.

## 13. Kết hợp circuit breaker và retry mà không tạo retry storm

Trong Gateway Server WebFlux, một route có thể khai báo thêm **Retry GatewayFilter Factory** để xử lý lỗi tạm thời. Tuy nhiên, sự phối hợp giữa Retry và CircuitBreaker cần được thiết kế rõ ràng.

~~~mermaid
flowchart TD
    A[Client request] --> R{Retry policy}
    R --> CB[Circuit breaker]
    CB --> L[Load balancer / HTTP upstream]
    L --> X{Kết quả}
    X -->|Success| S[Return response]
    X -->|Transient retryable failure| T{Còn budget retry?}
    T -->|Có| R
    T -->|Không| F[Error / fallback]
    CB -->|OPEN| F
~~~

Sơ đồ thể hiện **một phương án logic**, không khẳng định tất cả filter order hoặc implementation luôn giống vậy. Hai cách bao bọc có kết quả thống kê khác nhau:

1. **Retry bên ngoài breaker:** Mỗi lần thử lại có thể đi qua breaker và được ghi nhận là một lời gọi riêng; breaker có thể mở nhanh hơn nếu nhiều attempts thất bại.
2. **Breaker bên ngoài retry:** Breaker có thể thấy **kết quả tổng** của một operation đã retry; backend vẫn có thể nhận nhiều attempts trước khi operation được coi là thất bại.

Thứ tự filter do Gateway quyết định qua order của `GatewayFilter`/`GlobalFilter`, không phải lúc nào cũng đơn giản bằng vị trí người đọc nhìn thấy trong file. Cần đo **số lần upstream được gọi**, trạng thái breaker và metrics khi test cấu hình thực.

### Chỉ retry khi đảm bảo tính đúng đắn

| Request | Có thể cân nhắc retry? | Điều kiện |
| --- | --- | --- |
| `GET /catalog/products/42` | Thường có thể, với giới hạn | GET không có side effect; cần timeout/deadline |
| `GET /orders/42` | Có thể với giới hạn | Không lộ dữ liệu stale/sai tenant, giảm tải cho backend |
| `PUT /preferences` | Phụ thuộc API contract | Bảo đảm idempotency theo nghiệp vụ, kiểm tra điều kiện cập nhật |
| `POST /orders` | **Không mặc định** | Cần idempotency key và semantics xử lý đúng một lần về mặt nghiệp vụ |
| `POST /payments` | **Rủi ro cao** | Chỉ dùng chính sách được hệ thống thanh toán cho phép, có deduplication |
| WebSocket/SSE đã mở | Không retry như request ngắn | Cần reconnect/resume ở cấp protocol/ứng dụng |

Nếu đã OPEN, một retry vô ích có thể liên tục tạo `CallNotPermittedException` và làm tăng log/CPU dù không gọi upstream. Nên tránh retry exception “call not permitted”, đặt backoff, deadline và giới hạn tổng số attempts.

### Ví dụ hệ quả của retry

Giả sử client gửi 500 GET/s, lỗi xuất hiện liên tục và mỗi request được phép thử tối đa 3 lần. Trước khi breaker mở hoặc trước khi hết budget, backend có thể nhận tới:

~~~text
500 request/s × 3 attempts = 1.500 upstream attempts/s
~~~

Con số chỉ minh họa **giới hạn lý thuyết của policy**, chưa tính breaker OPEN, throttling, concurrency và timeout. Với backend đã suy giảm, tăng tải lên gấp ba có thể làm outage tệ hơn. Nên theo dõi **tỷ lệ request từ client** và **tỷ lệ attempts đến upstream** riêng biệt.

## 14. Load balancing: breaker đang theo dõi một service hay một instance?

Khi URI route là `lb://orders-service`, **ReactiveLoadBalancerClientFilter** chọn một ServiceInstance cụ thể rồi routing filter gọi host/port. Nhưng tên circuit breaker trong ví dụ là `ordersCircuitBreaker` gắn với route:

~~~text
Route orders-read
  Circuit name = ordersCircuitBreaker
  lb://orders-service
       |-- instance A (healthy)
       |-- instance B (unavailable)
       +-- instance C (healthy)
~~~

Với cách khai báo thông thường, breaker có thể **gom kết quả các lần gọi đi qua route/circuit name**, không tự tạo một breaker riêng cho A, B và C. Nếu B lỗi nhiều, breaker của route có thể OPEN, khiến **cả request đáng lẽ chọn A/C khỏe** cũng bị chặn.

Điều này không phải luôn sai: một circuit bảo vệ cả **dependency Orders** ở cấp service có thể là chủ đích. Tuy nhiên khi chỉ một instance hỏng, nên bổ sung **readiness, health filtering, service discovery, load balancing và connection management** để loại instance đó khỏi danh sách, thay vì chỉ để breaker chặn cả service.

### Chọn granularity hợp lý

| Granularity | Điểm mạnh | Rủi ro |
| --- | --- | --- |
| Một breaker cho mỗi route/service | Đơn giản, dễ quan sát và phản ứng với dependency tổng thể | Lỗi của một operation/instance có thể ảnh hưởng toàn nhóm |
| Một breaker cho mỗi nhóm operation | Phân biệt GET đọc và POST ghi hoặc các đường truy cập có SLO khác | Nhiều cấu hình và metrics hơn |
| Một breaker cho mỗi upstream instance | Cô lập lỗi từng instance nếu triển khai thật sự hỗ trợ | Cardinality cao, scale/registry thay đổi, cần quản lý lifecycle |
| Một breaker chung cho mọi service | Ít config lúc đầu | **Không khuyến nghị:** một service lỗi có thể khóa mọi API khác |

Đừng đặt cùng tên `sharedCircuitBreaker` lên toàn bộ routes chỉ vì tiện. Khi các route không cùng dependency/trust/SLI, việc dùng chung breaker làm sai phạm vi ảnh hưởng và gây **cascading degradation**.

### Nhiều Gateway replica

Giả sử Gateway chạy ba replica G1/G2/G3. Thống kê breaker thông thường ở **từng tiến trình**:

~~~mermaid
flowchart LR
    LB[Ingress] --> G1[Gateway G1: CLOSED]
    LB --> G2[Gateway G2: OPEN]
    LB --> G3[Gateway G3: HALF_OPEN]
    G1 --> Orders[Orders service]
    G2 -. Fallback .-> F[Local response]
    G3 --> Orders
~~~

Ở cùng một thời điểm, client đi qua G1 có thể nhận response thật, còn client đi qua G2 được fallback. Cần metrics theo **gateway instance và route/circuit** để phân biệt hành vi; không tự giả định trạng thái breaker được đồng bộ qua Redis hay service discovery.

## 15. Phản hồi fallback: status, header, body và bảo mật

Circuit breaker thường là cơ chế hạ tầng, nhưng **fallback là giao diện HTTP mà người dùng thấy**. Một phản hồi tốt phải rõ ràng về nội dung và không vô tình chuyển thành thành công giả.

### Bảng quyết định response

| Tình huống | Hướng xử lý thường hợp lý | Vì sao |
| --- | --- | --- |
| Orders ngừng hoạt động | 503, body lỗi gọn, cache-control phù hợp | Không thể cung cấp trạng thái đơn hàng đúng |
| Catalog lỗi nhưng có cache được phép | Trả dữ liệu cache kèm metadata stale đúng hợp đồng, hoặc 503 | Chỉ dùng cache nếu tuổi dữ liệu và quyền truy cập được kiểm soát |
| Payment timeout | Trả trạng thái không xác định/đang xử lý theo contract, tránh cam kết đã thanh toán | Backend có thể đã xử lý trước khi mất response |
| Một request gửi token hết hạn | 401 từ authentication layer, không fallback kiểu 200 | Không để lỗi auth mở đường cho request |
| User thiếu quyền admin | 403, không gọi backend admin | Circuit breaker không thay thế authorization |
| Client gửi dữ liệu không hợp lệ | 400 theo validation contract | Không tính là dependency unavailable |
| Gateway bị rate limit | 429 và Retry-After nếu policy có cơ sở | 429 không chứng minh upstream lỗi |

### Response đã commit thì không thể đổi status

Với JSON response ngắn, breaker có thể bắt lỗi trước khi Gateway gửi status/body. Nhưng với **SSE, NDJSON hoặc tải xuống lớn**, Gateway có thể đã gửi HTTP 200 và một phần dữ liệu:

~~~text
HTTP/1.1 200 OK
Content-Type: text/event-stream

event: progress
data: 10

<upstream disconnected>
~~~

Tại thời điểm response đã commit, Gateway **không thể quay lại thay status thành 503 và bắt đầu body JSON khác**. Cần định nghĩa reconnect/resume và xử lý partial stream; không dùng fallback để nối một JSON error vào giữa một stream SSE rồi tuyên bố response vẫn hợp lệ.

### Không để fallback lộ dữ liệu nhạy cảm

Fallback không nên:

- Echo `Authorization`, `Cookie` hoặc query có token vào response/log.
- Gửi stack trace/exception class chứa URI nội bộ hoặc credential về client.
- Trả dữ liệu cache của **người dùng khác** nếu tầng xác thực không đủ thông tin.
- Forward token từ request gốc tới fallback service không có audience hợp lệ.
- Đổi 401/403 thành 200 rồi vô tình cho phép truy cập không được ủy quyền.

Nếu cần chẩn đoán exception ở fallback, hãy **ghi log an toàn** với route ID, loại lỗi đã chuẩn hóa và trace ID được kiểm soát, không ghi toàn bộ headers/body. Một số cơ chế của Gateway có thể đặt exception vào exchange attribute hoặc chuyển thông tin exception qua `FallbackHeaders`; nếu dùng, tuyệt đối không expose nội dung raw exception chứa URL, token hoặc dữ liệu nhạy cảm ra bên ngoài.

## 16. Quan sát các trạng thái và tình trạng suy giảm

HTTP status 200/503 từ client **không đủ** để biết breaker có đang hoạt động hay không. Một fallback có thể trả 200 do cache, còn service vẫn lỗi; một response 503 cũng có thể do không có ServiceInstance chứ không phải breaker OPEN.

Các tín hiệu nên theo dõi:

| Tín hiệu | Câu hỏi |
| --- | --- |
| Circuit state (CLOSED/OPEN/HALF_OPEN) | Breaker của route/dependency có đang từ chối gọi không? |
| Failure rate và slow-call rate | Tỷ lệ lỗi/chậm trong cửa sổ hiện tại là bao nhiêu? |
| Calls permitted / not permitted | Bao nhiêu request đã được gọi upstream, bao nhiêu bị OPEN từ chối? |
| Fallback invocations | Có bao nhiêu response được tạo từ nhánh fallback? |
| Upstream HTTP status | Backend đang trả 5xx hay 4xx? |
| Connection/timeout/TLS failures | Lỗi kết nối hay chờ response xảy ra ở hop nào? |
| Gateway route request rate | Tuyến nào đang nhận tăng tải hoặc bị ảnh hưởng? |
| Retry attempts | Mỗi client request tạo bao nhiêu upstream attempts? |
| End-to-end latency p95/p99 | Fail fast có giảm thời gian chờ của client không? |
| Availability và SLO | Client có thực nhận được kết quả theo contract đã cam kết không? |

Spring Cloud Gateway, Spring Cloud CircuitBreaker và Resilience4j có thể tích hợp **Micrometer/Actuator** khi dependency và cấu hình phù hợp. Tên metric, tags và khả năng expose events cụ thể **phụ thuộc phiên bản**; hãy kiểm tra metric thực tế của phiên bản đang chạy.

### Gợi ý cách đọc các dấu hiệu

| Quan sát | Khả năng cần điều tra |
| --- | --- |
| Failure rate tăng, breaker vẫn CLOSED | Chưa đủ `minimumNumberOfCalls`, cấu hình threshold hoặc lỗi không nằm trong phạm vi |
| Backend trả 500 nhưng failure metric không tăng | Chưa khai báo `statusCodes` phù hợp hoặc status không được chuyển thành failure |
| OPEN tăng, backend attempts giảm | Breaker đang thực hiện tác dụng giảm tải |
| OPEN liên tục dù upstream đã phục hồi | HALF_OPEN probes không được phép/không thành công, chính sách hoặc nguồn instance khác nhau |
| Gateway vẫn chậm khi breaker OPEN | Fallback chậm/treo, filter khác blocking, pool/ingress khác gây độ trễ |
| HTTP 200 cao nhưng degraded traffic tăng | Fallback trả dữ liệu thay thế, cần metric riêng để tránh che outage |
| G1 OPEN, G2 CLOSED | Các Gateway replica có số liệu/trạng thái breaker khác nhau |
| 503 tăng nhưng breaker không đổi | Không có instance, HTTP routing failure hoặc error handler khác |

**Tránh metrics có cardinality quá lớn** như raw URL, user ID, token, session ID hoặc dynamic upstream IP làm tag. Route ID, breaker name và status thường hữu ích hơn, miễn tên route/circuit được quản lý có giới hạn. Tắt hoặc bảo vệ các Actuator endpoint quản trị; không để người dùng Internet đọc/điều khiển trạng thái breaker tùy ý.

### Quan sát khi breaker mở là một sự kiện quan trọng

Một alert hữu ích có thể kết hợp **breaker state OPEN kéo dài**, tỷ lệ request bị từ chối, upstream availability và kết quả fallback. Không chỉ alert cho từng error log của `CallNotPermittedException`, vì khi OPEN, từng request mới bị từ chối có thể tạo rất nhiều log giống nhau dù cơ chế đang làm đúng công việc bảo vệ.

## 17. Kiểm thử circuit breaker bằng backend giả lập

Để kiểm chứng circuit breaker, không nên chỉ nhìn application startup báo “route loaded”. Cần mô phỏng những kết quả upstream được tính là lỗi và **đếm request thực sự đến backend**.

### Môi trường thử nghiệm

Giả sử có ba tiến trình:

~~~text
Client test / WebTestClient
          |
          v
Gateway :8080
  GET /api/orders/42
  CircuitBreaker = ordersCircuitBreaker
          |
          +--> Orders stub :9001
          |      Chế độ 200 / 503 / delayed / connection reset
          |
          +--> Local fallback
                 GET /internal/fallback/orders
~~~

Trong lab đơn giản, thay `uri: lb://orders-service` bằng `uri: http://localhost:9001` để cô lập phần load balancing, hoặc cấu hình một ServiceInstance duy nhất cho `orders-service`. **Không cần registry để hiểu state machine**, nhưng phải có HTTP stub cho phép kiểm soát lỗi và đếm request.

Để dễ quan sát, có thể bắt đầu từ cấu hình `minimumNumberOfCalls: 10`, `failureRateThreshold: 50`, `waitDurationInOpenState: 30s` và `permittedNumberOfCallsInHalfOpenState: 3` ở phần 8. Trong thực tế, thời điểm OPEN còn phụ thuộc số mẫu đã có trong sliding window, các request đồng thời và chính sách slow-call.

### Kiểm thử các tình huống cơ bản

| Bài kiểm thử | Stub/backend | Điều cần quan sát |
| --- | --- | --- |
| **A. Thành công bình thường** | Trả 200 JSON nhanh | Client nhận 200, breaker CLOSED, request đến backend |
| **B. Một vài lỗi ít mẫu** | Trả 503 vài lần | Không tự khẳng định OPEN trước khi đạt minimum calls |
| **C. Lỗi đạt ngưỡng** | Trả 503 đủ số lần theo cấu hình | Failure metric tăng; breaker có thể chuyển OPEN |
| **D. OPEN từ chối lời gọi** | Giữ stub ở chế độ lỗi | Request tiếp theo không tăng backend request counter; client nhận fallback đã thiết kế |
| **E. HALF_OPEN thăm dò** | Chờ OPEN wait và chuyển stub về 200 | Chỉ một số cuộc gọi được phép tới backend; kết quả quyết định CLOSED |
| **F. Backend vẫn lỗi khi thăm dò** | Vẫn trả 503 | Breaker trở lại OPEN nếu probe không đạt điều kiện |
| **G. Lỗi 404 hợp lệ** | Trả 404 cho order không tồn tại | Không nên tăng failure metric nếu 404 không cấu hình là lỗi |
| **H. Timeout** | Delay quá response deadline | Exception timeout thuộc policy phải được ghi nhận; fallback đúng status |
| **I. Anonymous/không đủ quyền** | Không cần gọi stub | Security 401/403, request không tới upstream |
| **J. Streaming dở dang** | Gửi vài event rồi ngắt | Không cố đổi response đã commit thành một JSON 503 |

### Dùng curl trong môi trường lab

~~~bash
# Khi stub trả 200:
curl -i 'http://localhost:8080/api/orders/42'

# Sau khi đổi stub sang trả 503:
curl -i 'http://localhost:8080/api/orders/42'
curl -i 'http://localhost:8080/api/orders/42'
curl -i 'http://localhost:8080/api/orders/42'

# Kiểm tra route khác không dùng breaker Orders:
curl -i 'http://localhost:8080/api/public/products/42'
~~~

Các lệnh trên là **hướng dẫn thao tác**, không phải kết quả đã chạy. Ba request lỗi **không đủ** để đảm bảo breaker sẽ mở nếu `minimumNumberOfCalls` là 10. Hãy dùng stub có request counter và gửi số lượng đủ theo cấu hình trong một test tự động; tránh gõ tay với timing khó kiểm soát rồi suy diễn kết quả.

### WebTestClient kiểm tra hợp đồng fallback

Giả sử Gateway và stub đã được khởi chạy trong integration test, một assertion HTTP có thể có dạng:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.test.web.reactive.server.WebTestClient;

class OrdersGatewayFallbackHttpTest {

    private final WebTestClient client = WebTestClient.bindToServer()
            .baseUrl("http://localhost:8080")
            .build();

    @Test
    void returnsSafeFallbackWhenOrdersIsUnavailable() {
        // Điều kiện test: stub Orders đang trả lỗi được breaker/fallback xử lý.
        client.get()
                .uri("/api/orders/42")
                .exchange()
                .expectStatus().isEqualTo(503)
                .expectHeader().valueEquals("Cache-Control", "no-store")
                .expectBody()
                .jsonPath("$.code")
                .isEqualTo("ORDERS_TEMPORARILY_UNAVAILABLE");
    }
}
~~~

Đây là **ví dụ assertion**, không phải integration test hoàn chỉnh có thể chạy ngay. Nó cần Gateway hoạt động ở cổng 8080, stub tạo đúng điều kiện lỗi, dependency Spring Test/JUnit và cấu hình CircuitBreaker tương ứng. Tùy cách serialize/framework, `Cache-Control` có thể chứa directive bổ sung; khi đó assertion cần điều chỉnh theo contract thay vì buộc một chuỗi không cần thiết.

**Test quan trọng hơn:** Khi breaker đã OPEN, ghi lại counter của stub trước và sau một loạt request; nếu không có probe được cho phép, **counter phải giữ nguyên**. Test chỉ thấy JSON 503 mà không đo counter không chứng minh breaker đã short-circuit: backend cũng có thể đang trả 503 cho từng lần gọi.

### Làm sao kiểm thử trạng thái một cách có tính quyết định?

Có hai lớp kiểm thử bổ sung:

1. **Unit test Resilience4j:** Dùng clock/state/circuit configuration có thể kiểm soát để xác minh state transition và call permission, không cần HTTP.
2. **Integration test Gateway:** Dùng HTTP stub, response delay, fixed test configuration, kiểm soát số request và metrics/state; tránh phụ thuộc thứ tự những request đồng thời không dự đoán trước.

Một số thư viện cho phép điều khiển state trong test để tập trung kiểm thử nhánh OPEN/HALF_OPEN, nhưng **không sử dụng lệnh ép state hoặc management endpoint đó trên production** nếu không có quy trình vận hành và phân quyền. Test e2e vẫn phải xác nhận đúng kết quả khi backend lỗi thật.

## 18. Các phản mẫu thường gặp và cách sửa

| Phản mẫu | Hệ quả | Cách làm đúng hơn |
| --- | --- | --- |
| Cùng một breaker name cho Catalog, Orders và Payments | Một service lỗi làm các service khác bị chặn | Tách breaker theo dependency/nhóm operation |
| Tính mọi HTTP 4xx là failure | 400/401/403/404 từ client làm breaker mở | Chỉ định exception/status phản ánh suy giảm upstream |
| Fallback mọi exception thành HTTP 200 | Che lỗi, khiến client hiểu nhầm | Giữ status và body đúng nghiệp vụ, đo degraded riêng |
| Trả dữ liệu cache không kiểm soát cho Orders cá nhân | Dữ liệu stale hoặc sai người dùng | Xác thực quyền và chính sách cache rõ; ưu tiên 503 khi không chắc |
| Dùng breaker thay timeout | Operation treo, tài nguyên vẫn bị giữ | Bổ sung connect/response timeout hoặc TimeLimiter thích hợp |
| Retry vô hạn sau khi OPEN | Log/CPU tăng và vẫn không gọi được backend | Có retry budget/backoff, loại call-not-permitted khỏi retry |
| Retry POST thanh toán không có idempotency | Giao dịch có thể bị lặp | Idempotency key, backend dedupe, policy riêng |
| Dựa vào `SetStatus=200` để sửa fallback | Status và body mất nhất quán | Trả response thống nhất từ handler và contract |
| Coi mọi 503 đều là breaker OPEN | Bỏ sót no-instance, backend 503, timeout | Tách metric route, circuit, load-balancer và HTTP errors |
| Mở circuit vì một instance lỗi trong cluster | Chặn cả instance khỏe | Kết hợp readiness/registry filtering và chọn granularity |
| Để fallback công khai dữ liệu nhạy cảm | Tạo đường vòng không qua auth | Bảo vệ handler/đường vào và không trả secrets |
| Log nguyên exception/Authorization | Lộ JWT, URL nội bộ hoặc session | Log metadata được chuẩn hóa và trace ID an toàn |
| Dùng một response timeout ngắn cho SSE | Stream bị cắt, breaker có thể mở vô lý | Chính sách riêng cho streaming và heartbeat/reconnect |
| Không đo request counter của upstream | Không chứng minh short-circuit | Dùng stub/metrics cho số attempts và state |
| Ngưỡng rất thấp ngay trên traffic ít | Breaker dao động vì mẫu nhỏ | Đặt minimum samples/window dựa trên traffic |
| Forced OPEN/RESET từ endpoint Internet | Người ngoài có thể phá vận hành | Bảo vệ management plane và audit thay đổi |

### Tình huống: 503 tăng nhưng circuit breaker không OPEN

Có thể xảy ra ít nhất bốn nguyên nhân:

1. 503 là response bình thường, chưa được `statusCodes` coi là failure.
2. `minimumNumberOfCalls` chưa đạt hoặc cửa sổ chỉ có ít mẫu.
3. 503 phát sinh từ lớp khác ngoài phạm vi publisher được breaker theo dõi.
4. Có nhiều Gateway replica, mỗi replica có thống kê khác nhau.

**Cách điều tra:** xác định route, breaker name, statusCodes và timeout; sau đó xem failure/slow-call metrics, state, request count tới stub/backend và số replica. Không “sửa” bằng cách giảm threshold xuống gần 0 khi chưa biết nguyên nhân.

## 19. Quy trình vận hành khi breaker mở liên tục

Khi circuit breaker của Orders chuyển OPEN và giữ trạng thái đó trong thời gian dài, đừng chỉ ép breaker CLOSED. Nguyên nhân thường nằm ở dependency hoặc cấu hình phát hiện sự cố:

1. **Xác định phạm vi ảnh hưởng:** Chỉ `orders-read` hay mọi route? Có breaker nào dùng chung name không?
2. **Kiểm tra upstream:** Instance có healthy/readiness? Có sự cố DB, DNS, TLS, connection pool, timeout hoặc deployment không?
3. **Xem trạng thái và failure rate:** Do exceptions, HTTP 5xx được cấu hình hay slow-call threshold?
4. **Kiểm tra retry:** Có retry storm làm latency/lỗi tăng và khiến breaker liên tục tái mở không?
5. **Đánh giá fallback:** Client nhận 503 đúng ngữ nghĩa chưa, cache/stale data có gây hiểu nhầm không?
6. **Quan sát HALF_OPEN:** Các probe có vào được instance khỏe? Có bị rate limit, timeout hoặc service discovery cũ làm lỗi lại không?
7. **Sửa dependency hoặc điều chỉnh chính sách có cơ sở:** Recovery phải được xác minh bằng health/traffic thật, không bằng một lệnh reset trạng thái đơn độc.
8. **Rút kinh nghiệm:** Bổ sung alert, runbook, test chaos an toàn và SLO cho degraded response.

### Chiến lược lựa chọn fallback khi service thiết yếu lỗi

Không phải API nào cũng cần một fallback body phức tạp. Với Orders, 503 có thể là phản hồi đúng. Với Catalog, một snapshot cache đã được phê duyệt có thể hữu ích. Với Payment, không nên tự suy diễn trạng thái thanh toán; có thể cần trả kết quả `pending` nếu backend có cơ chế tracking/idempotency thật, hoặc yêu cầu client tra cứu trạng thái qua một endpoint đáng tin sau đó.

**Đúng nghiệp vụ quan trọng hơn tỷ lệ HTTP 200.** Một fallback thành công về mặt HTTP nhưng sai trạng thái giao dịch có thể tệ hơn việc trả lỗi tạm thời rõ ràng.

### Bảo vệ management plane

Các Actuator endpoint, registry, route-definition APIs và cơ chế reset/force circuit state phải có xác thực và phân quyền chặt chẽ. Không đưa route admin, breaker control hoặc endpoint trả environment/secrets lên một `Path=/**` công khai. Việc thay đổi breaker policy giữa sự cố cần có owner, audit và rollback.

## 20. Bài thực hành tổng hợp: Orders API chịu lỗi upstream

**Bối cảnh:** Một hệ thống bán hàng có Catalog, Orders và Payment service. Client truy cập qua Spring Cloud Gateway. Route Orders dùng service discovery, JWT, rate limiting và CircuitBreaker; backend đôi khi trả 503 hoặc timeout trong lúc rollout.

### Phần A — Lập hợp đồng bảo vệ

1. Chọn một **GET đọc đơn hàng** làm tình huống chính, vì dễ xác định hành vi retry/fallback không tạo side effect.
2. Viết rõ tên route, service ID, timeout, statusCodes, breakpoint failure/slow-call, mẫu tối thiểu và thời gian OPEN.
3. Quyết định lỗi nào **không** được tính: 400, 401, 403, 404 hợp lệ của ứng dụng.
4. Thiết kế fallback 503 trả JSON ngắn, không lộ thông tin đơn hàng hoặc token, với cache policy thích hợp.
5. Giữ Spring Security xử lý 401/403 trước khi cho phép proxy request và fallback.

### Phần B — Cấu hình Gateway

1. Thêm dependency **Spring Cloud CircuitBreaker Reactor Resilience4j** tương thích.
2. Khai báo route `orders-read` với `CircuitBreaker`, `name: ordersCircuitBreaker` và `fallbackUri: forward:/internal/fallback/orders`.
3. Cấu hình Resilience4j theo ví dụ phần 8, nhưng chọn ngưỡng thích hợp với lab.
4. Thêm handler cục bộ trả 503 và thông báo JSON trong phần 9; bảo vệ endpoint nội bộ khỏi gọi trực tiếp ngoài ý muốn.
5. Cấu hình HTTP client timeout phù hợp; xác nhận namespace thuộc phiên bản đang dùng.
6. Bật metrics/trace an toàn và xác minh route được nạp, dependency đã có.

### Phần C — Mô phỏng vòng đời circuit

| Giai đoạn | Hành động | Bằng chứng cần lưu |
| --- | --- | --- |
| 1. Healthy | Stub trả 200 nhanh | Status 200, breaker CLOSED |
| 2. Degraded | Stub trả 503 theo `statusCodes` | Failure metric tăng, fallback đúng contract |
| 3. Threshold | Gửi đủ mẫu lỗi | Breaker chuyển OPEN theo chính sách |
| 4. Fail fast | Tiếp tục gửi GET trong thời gian OPEN | Backend counter không tăng; fallback nhanh |
| 5. Recovery | Đổi stub về 200; chờ đủ thời gian | HALF_OPEN cho số probe có giới hạn |
| 6. Restore | Các probe thành công | Breaker về CLOSED; request tới upstream lại |
| 7. No recovery | Thử cho stub tiếp tục lỗi | Breaker trở lại OPEN |

Không giả lập failure bằng cách tấn công một hệ thống production; chỉ dùng backend stub, môi trường thử nghiệm hoặc một kịch bản chaos có giới hạn, được tổ chức cho phép.

### Phần D — Kiểm chứng không che sai lỗi

1. Trả 404 cho một order không tồn tại; xác nhận không vô tình kích hoạt fallback 503 nếu 404 không nằm trong policy.
2. Gửi request anonymous và user không đủ quyền; kiểm tra 401/403 không đến backend Orders.
3. Cố tình gây timeout GET trong lab; kiểm tra lỗi được phân loại ở đúng lớp và trạng thái response hợp lệ.
4. Bật retry GET tối đa vài lần với backoff phù hợp; đo **backend attempts so với client requests** và so sánh state breaker.
5. Thử lỗi sau khi backend đã stream một phần; xác nhận không thể thay HTTP status đã commit.
6. Nếu dùng nhiều Gateway replica, xem state và metrics theo từng replica, tránh suy diễn chúng đồng bộ.
7. Kiểm tra 503 fallback không ghi Authorization, Cookie, raw query hoặc toàn exception vào logs/traces.

### Tiêu chí đánh giá

Một bài thực hành đạt yêu cầu khi chứng minh được:

- Breaker **chỉ đo đúng nhóm lỗi đã định nghĩa**, không mở vì caller gửi 400/401/403/404 hợp lệ.
- Khi CLOSED, request được đi qua và client nhận response backend bình thường.
- Khi OPEN, request không tới backend trên nhánh được bảo vệ; client nhận lỗi/fallback đúng hợp đồng.
- Khi HALF_OPEN, một số probe được chọn và trạng thái phục hồi theo kết quả.
- Timeout, retry, load balancing và SecurityWebFilterChain **không phá tính đúng đắn** của flow.
- Metrics, logs và stub counters cho phép phân biệt **upstream outage, no-instance, breaker rejection và fallback** mà không lộ dữ liệu nhạy cảm.

## 21. Tổng kết

- **Circuit breaker trong Spring Cloud Gateway là cơ chế bảo vệ tại ranh giới gọi backend.** Nó không chữa lỗi service mà tạm ngừng những lời gọi có khả năng tiếp tục thất bại, giảm thời gian chờ và giảm áp lực lên dependency.
- Ba trạng thái chính là **CLOSED** (cho phép và đo), **OPEN** (từ chối phần lớn lời gọi được bảo vệ) và **HALF_OPEN** (cho probe có giới hạn để xác định phục hồi).
- CircuitBreaker GatewayFilter của **Gateway Server WebFlux** kết hợp **Spring Cloud CircuitBreaker** và implementation như **Resilience4j**; cấu hình route, breaker name và threshold phải tương thích phiên bản.
- **Không phải mọi HTTP status đều được tính là lỗi.** Chọn đúng exception/statusCodes; không gộp 400/401/403/404 hợp lệ vào lỗi dependency.
- **Circuit breaker không thay thế timeout, retry, load balancing hay bulkhead**. Kết hợp đúng order, deadline và retry budget; không retry các thao tác có side effect khi thiếu idempotency.
- **Fallback phải giữ đúng ngữ nghĩa HTTP và dữ liệu**: thường là 503 cho service không sẵn sàng, hoặc dữ liệu dự phòng có contract rõ. Không trả 200 thành công giả hoặc lộ thông tin nhạy cảm.
- Breaker theo **route/dependency** có thể gom lỗi nhiều ServiceInstance và mỗi Gateway replica có trạng thái riêng. Kết hợp health, readiness, discovery và metrics để không chặn quá mức.
- **Test OPEN bằng upstream counter và metrics**, không chỉ nhìn response 503. Kiểm thử HALF_OPEN/recovery, timeout, Security 401/403, lỗi streaming sau commit và trace/log an toàn.

Một API Gateway có khả năng chịu lỗi tốt là Gateway **biết khi nào cần ngừng gọi dependency**, **thông báo kết quả trung thực cho client**, và **phục hồi có kiểm chứng** khi service hoạt động trở lại.
