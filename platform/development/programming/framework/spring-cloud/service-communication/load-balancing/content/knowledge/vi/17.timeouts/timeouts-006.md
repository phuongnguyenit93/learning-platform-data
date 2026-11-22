# Thiết kế timeout cho chuỗi nhiều dịch vụ gọi nhau

Trong kiến trúc microservices, một request từ người dùng có thể đi qua API Gateway, `order-service`, `inventory-service`, `pricing-service` và nhiều dịch vụ khác. Mỗi lời gọi có thể dùng RestClient, WebClient hoặc OpenFeign kết hợp **Spring Cloud LoadBalancer** để chọn một `ServiceInstance` theo service ID. Nếu mỗi dịch vụ tự đặt một timeout mà không tính đến thời gian các bước trước đã tiêu tốn, request tổng có thể chờ rất lâu, giữ tài nguyên của nhiều dịch vụ, hoặc thất bại dù từng lời gọi riêng lẻ vẫn tuân thủ timeout.

Bài học thuộc chương **Thời gian chờ** tập trung vào cách thiết kế một **ngân sách thời gian đầu-cuối (end-to-end time budget)**: xác định deadline của request, phân bổ cho từng chặng, giữ phần dự phòng, hạn chế retry, đồng bộ thời gian chờ với hạ tầng và theo dõi nơi ngân sách bị tiêu hao. Mục tiêu là **giao tiếp giữa các dịch vụ ổn định**, không chỉ là thêm một giá trị `readTimeout` vào `application.yml`.

## 1. Vấn đề: timeout đúng ở từng hop nhưng sai ở toàn chuỗi

Xét một request:

~~~mermaid
flowchart LR
    U["Người dùng"] --> G["API Gateway"]
    G --> O["order-service"]
    O --> I["inventory-service"]
    I --> P["pricing-service"]
    P --> D["price database"]
~~~

Giả sử các client đều đặt read timeout 2 giây:

~~~text
Gateway -> Order:     tối đa 2 giây
Order   -> Inventory: tối đa 2 giây
Inventory -> Pricing: tối đa 2 giây
Pricing -> Database:  tối đa 2 giây
~~~

Không thể kết luận response của người dùng luôn có trong 2 giây. Nếu các lời gọi diễn ra nối tiếp và có công việc tại mỗi chặng, tổng độ trễ có thể lớn hơn đáng kể. Hơn nữa, `read timeout` của một transport không phải lúc nào cũng là deadline bao trùm toàn bộ request. Nó có thể không tính thời gian chờ connection pool, service discovery, token acquisition, hàng đợi executor, mã hóa dữ liệu, backoff hay số lần retry.

Còn một tình huống nguy hiểm: gateway đã ngừng đợi ở giây thứ hai nhưng các downstream vẫn tiếp tục công việc đắt tiền đến giây thứ bảy, dù không còn ai cần kết quả.

**Nguyên tắc:** timeout từng hop là cơ chế bảo vệ tài nguyên cục bộ; **deadline tổng** mới thể hiện người gọi còn sẵn sàng đợi bao lâu cho cả nghiệp vụ.

## 2. Phân biệt các loại timeout

| Loại | Phạm vi | Ví dụ tình huống |
|---|---|---|
| **Connection acquisition timeout** | Đợi lấy một kết nối có sẵn từ pool | Pool cạn, request xếp hàng trước network I/O |
| **Connect timeout** | Thiết lập kết nối TCP tới instance | Một địa chỉ instance không mở cổng |
| **TLS handshake timeout** | Hoàn tất handshake TLS khi được cấu hình | Kết nối mạng có nhưng handshake treo |
| **Response/read timeout** | Đợi dữ liệu phản hồi theo semantics của HTTP transport | Backend nhận request nhưng không trả response |
| **Write timeout** | Thời gian ghi request body nếu client hỗ trợ | Upload payload lớn bị nghẽn |
| **Discovery timeout** | Tra cứu danh sách `ServiceInstance` từ service discovery | Registry chậm trả lời |
| **LoadBalancer selection time** | Thời gian lấy danh sách/lọc/chọn instance | Supplier/caching/health filtering chậm |
| **Retry backoff** | Đợi trước khi thực hiện attempt tiếp theo | Lỗi tạm thời, chờ 100–300 ms |
| **Request/operation deadline** | Tổng thời gian chấp nhận cho toàn bộ một nghiệp vụ | Gateway muốn response trước 1.200 ms |
| **Server execution timeout** | Giới hạn xử lý ở phía server/framework khi được hỗ trợ | Server không muốn giữ request quá lâu |

Không có một thuộc tính cấu hình Spring Cloud duy nhất tự động áp dụng tất cả các giới hạn này cho mọi RestClient, WebClient và OpenFeign.

Một số phân biệt quan trọng:

- `spring.cloud.loadbalancer.health-check.interval` điều khiển chu kỳ kiểm tra sức khỏe instance, **không** phải HTTP read timeout.
- `spring.cloud.loadbalancer.cache.ttl` điều khiển tuổi dữ liệu cache instance, **không** phải hạn chót của request.
- `spring.cloud.loadbalancer.service-discovery.timeout`, ở release train có hỗ trợ, liên quan truy xuất discovery, **không** thay thế timeout của HTTP transport.
- Một server trả `504 Gateway Timeout` thường nói rằng gateway/proxy đã hết thời gian đợi upstream, không bảo đảm downstream đã ngừng xử lý.
- `503 Service Unavailable` có thể do không còn instance được LoadBalancer chọn, do backend hoặc do proxy, cần nhìn log/tracing để phân biệt.

## 3. Deadline đầu-cuối là gì?

Giả sử người dùng chấp nhận tối đa 1.200 ms từ lúc request đến gateway đến khi nhận kết quả. Khi bắt đầu, hệ thống tạo **deadline**:

\[
D = t_{\text{start}} + B
\]

trong đó:

- `B` là ngân sách tối đa, ví dụ 1.200 ms.
- `D` là thời điểm phải kết thúc.
- `t_{\text{start}}` là thời điểm bắt đầu đo.

Tại một thời điểm `t`, ngân sách còn lại:

\[
R(t) = \max(0, D - t)
\]

Nếu một chặng đã mất 350 ms, ngân sách còn lại không còn là 1.200 ms mà xấp xỉ 850 ms, chưa tính các phần dự phòng cần giữ.

Một HTTP client tại hop tiếp theo nên dùng giới hạn hiệu lực:

\[
T_{\text{hop}} =
\min\big(T_{\text{cap, hop}},\;\max(0, R-\Delta_{\text{reserve}})\big)
\]

Ở đây `T_cap, hop` là giới hạn riêng của dịch vụ đích, còn `Δ_reserve` là phần thời gian dành cho công việc còn lại, trả response, serialization và network overhead.

**Không đặt mọi hop thành đúng 1.200 ms** rồi giả định các lớp tự biết request đã đi qua bao nhiêu công đoạn.

### Ví dụ phân bổ ngân sách 1.200 ms

Giả sử chuỗi tuần tự: Gateway → Order → Inventory → Pricing.

| Hoạt động | Ngân sách dự kiến |
|---|---:|
| Gateway + network ingress/egress | 100 ms |
| Xử lý cục bộ ở order | 180 ms |
| Gọi inventory và xử lý response | 350 ms |
| Gọi pricing và xử lý response | 300 ms |
| Dự phòng cho jitter, serialization và thất bại ngắn | 270 ms |
| **Tổng** | **1.200 ms** |

Đây là **ví dụ thiết kế**, không phải số đo mặc định của Spring Cloud. Các giới hạn được phân bổ cần dựa vào phân phối latency thực tế, SLA/SLO và các phụ thuộc. Không nên đặt một cách máy móc khi inventory có p99 = 600 ms mà business vẫn yêu cầu deadline 1.200 ms.

Dự phòng còn cần xét các bước **chưa chạy**. Nếu order đã tiêu tốn 550 ms cho thao tác đầu tiên, không hợp lý để gửi một request mới với timeout 800 ms khi toàn bộ ngân sách chỉ còn 650 ms và vẫn phải serialize response.

## 4. Timeout và deadline: cục bộ hay xuyên dịch vụ?

**Timeout tương đối** như 300 ms trả lời câu hỏi: “Từ bây giờ, tôi có thể chờ thêm bao lâu?”. **Deadline tuyệt đối** trả lời: “Tôi phải hoàn tất trước thời điểm nào?”.

Trong cùng một JVM, có thể dùng đồng hồ đơn điệu `System.nanoTime()` để tính thời gian còn lại. Nó phù hợp với đo elapsed time và không bị đồng hồ hệ thống nhảy do NTP.

Giữa nhiều máy, **không truyền nguyên `System.nanoTime()`**: mốc thời gian này không có ý nghĩa giữa hai JVM. Nếu truyền deadline tuyệt đối theo wall clock, cần xét lệch đồng hồ, NTP và network delay. Một chiến lược đơn giản là chuyển **ngân sách còn lại đã giới hạn** đến hop kế tiếp qua trusted internal context, và trừ thời gian đã tiêu hao trước khi gửi đi. Một chiến lược chuẩn hơn là dùng deadline propagation được hỗ trợ bởi RPC/tracing stack nếu dự án có.

Ví dụ header nội bộ có tính minh họa:

~~~http
X-Request-Timeout-Ms: 620
~~~

**Không xem header này là chuẩn Spring Cloud hay một cơ chế tự động.** Nếu ứng dụng muốn dùng, phải tự xây dựng chính sách rõ ràng ở gateway/caller. Không tin vô điều kiện giá trị do người dùng Internet gửi; áp dụng giới hạn min/max và xác thực provenance ở boundary tin cậy. Nếu caller gửi header sau 100 ms chuẩn bị request, ngân sách phải phản ánh thời gian đã mất, không được truyền lại số cũ.

## 5. Mô hình deadline cục bộ bằng Java

Mục tiêu của class sau là quản lý **thời gian còn lại trong một JVM**, không thay thế HTTP client timeout:

~~~java
import java.time.Duration;

public final class DeadlineBudget {

    private final long deadlineNanos;

    private DeadlineBudget(Duration total) {
        if (total.isZero() || total.isNegative()) {
            throw new IllegalArgumentException("Budget must be positive");
        }

        // Phù hợp với ngân sách request ngắn, có giới hạn.
        this.deadlineNanos = System.nanoTime() + total.toNanos();
    }

    public static DeadlineBudget start(Duration total) {
        return new DeadlineBudget(total);
    }

    public Duration remaining() {
        long nanosLeft = deadlineNanos - System.nanoTime();
        return Duration.ofNanos(Math.max(0L, nanosLeft));
    }

    public Duration allowanceForHop(
            Duration hopMaximum,
            Duration reservedForLater) {

        Duration available = remaining().minus(reservedForLater);

        if (available.isNegative() || available.isZero()) {
            throw new IllegalStateException("Request deadline exhausted");
        }

        return available.compareTo(hopMaximum) < 0
                ? available
                : hopMaximum;
    }
}
~~~

Ví dụ:

~~~java
DeadlineBudget budget =
        DeadlineBudget.start(Duration.ofMillis(1200));

// Sau khi thực hiện một số việc ở caller:
Duration inventoryAllowance = budget.allowanceForHop(
        Duration.ofMillis(350),
        Duration.ofMillis(250)
);
~~~

Giá trị trả về là **ngân sách được phép** cho inventory ở thời điểm đó. Cần đưa giá trị này vào cơ chế timeout thực tế của HTTP client, vốn không có một API thống nhất cho mọi RestClient/WebClient/OpenFeign. Đoạn class chỉ minh họa, chưa có cơ chế tự động hủy request hoặc truyền deadline xuyên mạng.

Khi ngân sách đã cạn, nên **fail fast** theo contract nghiệp vụ thay vì gửi request mới chỉ để “thử may”. Trong production, có thể định nghĩa exception/response riêng và kết hợp tracing để phân biệt deadline exhausted với backend 500.

## 6. Chuỗi tuần tự: tổng độ trễ cộng dồn

Ví dụ `order-service` gọi inventory rồi pricing, bước pricing cần dữ liệu tồn kho vừa nhận:

~~~mermaid
sequenceDiagram
    participant G as Gateway
    participant O as order-service
    participant I as inventory-service
    participant P as pricing-service

    G->>O: GET /quote
    O->>I: GET /stock
    I-->>O: Stock result
    O->>P: GET /price
    P-->>O: Price result
    O-->>G: Quote
~~~

Với ba công đoạn tuần tự có latency `L1`, `L2`, `L3`:

\[
L_{\text{total}} \approx L_1 + L_2 + L_3 + L_{\text{overhead}}
\]

Trong đó overhead gồm network, serialization, scheduling, chọn instance và các phần công việc không nằm trong ba công đoạn. Retry làm tổng thời gian lớn hơn.

Ví dụ nếu inventory mất 400 ms trong khi ngân sách toàn request 1.000 ms, pricing không nên tự đặt timeout 900 ms cho dù cấu hình mặc định của nó là 900 ms. Hop pricing phải tính trên số thời gian thực sự còn lại sau inventory.

**Chiến thuật phù hợp:**

1. Bắt đầu deadline ở ranh giới tin cậy, ví dụ gateway hoặc service xử lý request.
2. Ghi nhận thời gian trước/sau từng công đoạn.
3. Trước mỗi outbound call, tính lại ngân sách còn lại và giữ phần dự phòng.
4. Nếu không đủ thời gian cho nghiệp vụ tiếp theo, trả lỗi timeout/degraded response theo chính sách.
5. Nếu được phép retry, tính cả backoff và mọi attempt bên trong deadline **cũ**, không bắt đầu deadline mới.

## 7. Fan-out song song: không đơn giản cộng mọi timeout

Giả sử `order-service` gọi inventory, pricing và promotions **song song**:

~~~mermaid
flowchart TB
    O["order-service"] --> I["inventory-service"]
    O --> P["pricing-service"]
    O --> M["promotion-service"]
    I --> J["Join kết quả"]
    P --> J
    M --> J
    J --> R["Response"]
~~~

Nếu tất cả bắt đầu gần cùng lúc và order cần đợi đủ ba kết quả, latency phần fan-out thường gần:

\[
L_{\text{fanout}} \approx \max(L_I,L_P,L_M) + L_{\text{join}}
\]

Không phải `L_I + L_P + L_M` như chuỗi tuần tự. Tuy nhiên, mỗi nhánh vẫn phải dùng **deadline chung**, không được tự tăng ngân sách sau khi một nhánh khác đã chậm.

Ví dụ với WebClient:

~~~java
Mono<Inventory> inventory = inventoryClient.getInventory(sku);
Mono<Price> price = pricingClient.getPrice(sku);
Mono<Promotion> promotion = promotionClient.getPromotion(sku);

return Mono.zip(inventory, price, promotion)
        .map(tuple -> new Quote(
                tuple.getT1(),
                tuple.getT2(),
                tuple.getT3()
        ))
        .timeout(Duration.ofMillis(900));
~~~

Đây là mã minh họa; các class `Inventory`, `Price`, `Promotion`, `Quote` cần được định nghĩa theo model dự án. Toán tử `Mono.zip` phát kết quả khi đủ ba nhánh, và `timeout` ở ngoài đặt giới hạn cho **phần pipeline được bao**. Nếu một nhánh lỗi, zip thường kết thúc lỗi và có thể hủy subscription các nhánh còn lại.

Hủy subscription **không bảo đảm** backend đã dừng xử lý. Downstream cần chính sách deadline/cancellation riêng nếu thao tác đắt tiền hoặc có side effect.

### Fan-out làm tăng xác suất gặp tail latency

Nếu tám dịch vụ độc lập, mỗi dịch vụ có 99% xác suất hoàn tất trước ngưỡng thời gian, xác suất **tất cả tám** cùng hoàn tất trước ngưỡng chỉ khoảng:

\[
0.99^8 \approx 0.9227 \;(92.27\%)
\]

Đây là mô hình đơn giản với giả định độc lập; trong thực tế, các dịch vụ có thể cùng phụ thuộc một database/network nên sự cố còn có tương quan. Đừng lấy p99 từng downstream rồi suy ra p99 của chuỗi nhiều nhánh sẽ giống hệt. Khi fan-out lớn, cần cân nhắc loại dữ liệu bắt buộc, degradation hợp lý, caching và tránh các lời gọi không thiết yếu.

## 8. Retry có thể nhân chi phí và phá vỡ deadline

Retry là cơ chế khắc phục lỗi tạm thời, nhưng mỗi attempt tốn thời gian, tài nguyên và đôi khi gây side effect. Nếu một request có ba lần thử (lần đầu + hai retry), và các tầng A→B→C đều tự thử lại ba lần, số attempt sâu nhất có thể tăng theo tích các retry budgets trong các kịch bản lỗi phù hợp:

\[
3 \times 3 \times 3 = 27
\]

Con số 27 chỉ minh họa **trường hợp nhân retry ở ba tầng**, không phải số attempt cố định của Spring Cloud. Cơ chế retry thực tế phụ thuộc cấu hình, vị trí retry, lỗi và các điều kiện dừng. Nhưng bài học rất rõ: **đừng cấu hình nhiều tầng retry vô hạn hoặc không phối hợp**.

Một chính sách an toàn hơn là:

- Chọn một tầng chịu trách nhiệm retry khi có thể.
- Chỉ retry lỗi có tính tạm thời và thao tác có thể lặp lại an toàn.
- Đặt tổng số attempt, backoff, jitter và deadline đầu-cuối.
- Sau mỗi attempt, đo `remaining budget` rồi quyết định có đủ thời gian cho attempt tiếp theo không.
- Tránh retry nếu chi phí xử lý lớn hoặc hệ thống đích đang quá tải.
- Phân biệt lỗi connect, read timeout, HTTP 429/503 và lỗi nghiệp vụ; không retry mọi status 4xx/5xx.
- Với POST/PUT có tác dụng phụ, dùng idempotency key và chính sách nhất quán giữa services.

Một timeline dễ mắc lỗi:

~~~text
Total budget: 1200 ms
Attempt #1: 500 ms -> timeout
Backoff #1: 200 ms
Attempt #2: 500 ms -> timeout
Backoff #2: 200 ms
Attempt #3: còn muốn chạy 500 ms
           -> vượt deadline từ trước khi attempt #3 hoàn thành
~~~

Ngay cả một attempt có timeout 500 ms vẫn không bảo đảm chuỗi retry hoàn tất trong 1.200 ms.

## 9. Phân bổ timeout theo loại phụ thuộc

Không phải downstream nào cũng cần cùng timeout.

| Phụ thuộc | Đặc điểm | Gợi ý thiết kế |
|---|---|---|
| Inventory đọc tồn kho | Nhiều bản sao, thường idempotent với GET | Timeout ngắn phù hợp p99, có thể retry có giới hạn |
| Payment tạo giao dịch | Có side effect, không thể lặp tùy tiện | Deadline rõ, idempotency key, hạn chế retry |
| Pricing tính giá | Có thể cần nhiều nguồn dữ liệu | Tối ưu dependencies, budget riêng trong deadline tổng |
| Recommendation | Thường không thiết yếu cho đặt hàng | Timeout ngắn và fallback bỏ recommendations |
| Reporting ngoài luồng | Không cần giữ HTTP request mở | Hàng đợi/event, deadline/TTL khác cho xử lý nền |
| Identity provider | Cấp token cho service client | Timeout và connection pool riêng, cache token hợp lệ |

Khi thiết kế SLO, dùng histogram latency thực tế của từng service (p50, p95, p99, p99.9), tỷ lệ timeout sai và mục tiêu kinh doanh. Chọn timeout bằng cách cân bằng giữa **false timeout** (cắt một request đáng lẽ thành công) và **wasted work** (chờ quá lâu một request khó thành công).

Đừng tự động đặt timeout đúng bằng p99 rồi cho rằng luôn đạt SLO. p99 của một phụ thuộc có thể cao hơn ngưỡng deadline toàn nghiệp vụ; khi ấy phải tối ưu kiến trúc hoặc chấp nhận fallback/degradation, không chỉ tăng một con số cấu hình.

## 10. LoadBalancer chọn instance; deadline vẫn thuộc caller

Spring Cloud LoadBalancer có trách nhiệm chọn một `ServiceInstance` từ danh sách do `ServiceInstanceListSupplier` cung cấp, có thể qua discovery, cache, health check, zone/hint filtering và retry-aware logic. Nó **không phải hệ thống deadline đầu-cuối**.

~~~text
Caller với remaining budget
  -> service ID: inventory-service
      -> DiscoveryClient / ServiceInstanceListSupplier
      -> (cache / health / zone / hint nếu bật)
      -> RoundRobin / Random / custom algorithm
      -> chọn ServiceInstance
      -> HTTP transport
      -> response / timeout / retry
  -> cập nhật remaining budget trước bước nghiệp vụ kế
~~~

Không dùng thời gian kiểm tra health endpoint làm giới hạn request nghiệp vụ:

~~~yaml
spring:
  cloud:
    loadbalancer:
      health-check:
        interval: 25s
~~~

`25s` ở đây là chu kỳ health check, **không phải** giới hạn thời gian WebClient hoặc OpenFeign có thể đợi inventory.

Tương tự, TTL cache có thể khiến danh sách instance thay đổi chậm; một replica vừa mất kết nối vẫn có thể được chọn cho đến khi discovery/health supplier cập nhật. Timeout transport và retry có kiểm soát giúp xử lý việc chọn phải instance không còn hoạt động, nhưng phải nằm trong deadline còn lại.

Nếu cả hai dịch vụ đều có nhiều instance, tải có thể không cân bằng theo thời gian hoàn thành: thuật toán Round Robin phân phối lần chọn tương đối đều, không bảo đảm từng backend cùng độ trễ. Vì vậy, việc chọn timeout nên dựa trên SLO và phân phối latency của service ID, không kỳ vọng chính sách LoadBalancer thay thế performance engineering.


## 11. Cấu hình connect/read timeout cho RestClient

`RestClient` là HTTP client đồng bộ của Spring Framework. Khi dùng `@LoadBalanced RestClient.Builder`, Spring Cloud LoadBalancer giải quyết URI theo service ID rồi request factory gửi HTTP request tới instance được chọn.

Ví dụ một RestClient dành cho inventory:

~~~java
package com.example.order.http;

import java.time.Duration;
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.web.client.RestClient;

@Configuration(proxyBeanMethods = false)
public class InventoryRestClientConfiguration {

    @Bean
    @LoadBalanced
    RestClient.Builder loadBalancedRestClientBuilder() {
        return RestClient.builder();
    }

    @Bean
    RestClient inventoryRestClient(
            @LoadBalanced RestClient.Builder builder) {

        SimpleClientHttpRequestFactory requestFactory =
                new SimpleClientHttpRequestFactory();

        requestFactory.setConnectTimeout(Duration.ofMillis(250));
        requestFactory.setReadTimeout(Duration.ofMillis(700));

        return builder
                .requestFactory(requestFactory)
                .baseUrl("http://inventory-service")
                .build();
    }
}
~~~

- `@LoadBalanced` khiến `inventory-service` được hiểu là service ID.
- `connectTimeout` áp dụng cho thiết lập kết nối theo request factory này.
- `readTimeout` giới hạn việc đọc theo semantics của transport, **không phải** deadline của toàn bộ nghiệp vụ.
- `SimpleClientHttpRequestFactory` minh họa API. Production thường cần HTTP transport có connection pool, pool acquire timeout, TLS, reuse connections và metric phù hợp.
- Nếu dùng cùng builder cho nhiều clients, quản lý scope hoặc clone builder để thay đổi base URL/request factory không ảnh hưởng client khác.

Gọi inventory:

~~~java
public InventoryResponse getStock(
        RestClient inventoryRestClient,
        String sku) {

    return inventoryRestClient.get()
            .uri("/api/items/{sku}", sku)
            .retrieve()
            .body(InventoryResponse.class);
}
~~~

Nếu deadline tổng của request chỉ còn 300 ms, read timeout 700 ms chưa đủ để buộc caller ngừng đợi sau 300 ms. Cần quản lý ngân sách còn lại và cấu hình timeout/cancellation ở tầng transport hoặc execution phù hợp. Chỉ bọc một lời gọi blocking trong `CompletableFuture.orTimeout` không bảo đảm HTTP request hoặc backend work đã bị hủy sau khi future hết hạn.

## 12. WebClient: timeout transport và timeout toàn reactive pipeline

Với Reactor Netty làm transport, WebClient có thể cấu hình connect timeout và response timeout:

~~~java
package com.example.order.http;

import java.time.Duration;
import io.netty.channel.ChannelOption;
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.netty.http.client.HttpClient;

@Configuration(proxyBeanMethods = false)
public class InventoryWebClientConfiguration {

    @Bean
    @LoadBalanced
    WebClient.Builder loadBalancedWebClientBuilder() {
        return WebClient.builder();
    }

    @Bean
    WebClient inventoryWebClient(
            @LoadBalanced WebClient.Builder builder) {

        HttpClient transport = HttpClient.create()
                .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 250)
                .responseTimeout(Duration.ofMillis(700));

        return builder.clone()
                .clientConnector(new ReactorClientHttpConnector(transport))
                .baseUrl("http://inventory-service")
                .build();
    }
}
~~~

Hai giới hạn này điều khiển HTTP transport theo semantics của Reactor Netty. Chúng không nhất thiết bao gồm thời gian đợi pool, chọn instance, tạo access token hay các bước xử lý trước khi gọi HTTP.

### Đặt timeout ở ngoài retry

Nếu một GET inventory được phép retry một lần khi gặp lỗi mạng tạm thời:

~~~java
import java.time.Duration;
import org.springframework.web.reactive.function.client.WebClientRequestException;
import reactor.core.publisher.Mono;
import reactor.util.retry.Retry;

public Mono<InventoryResponse> getWithinDeadline(
        String sku,
        DeadlineBudget budget) {

    return Mono.defer(() -> {
        Duration allowance = budget.allowanceForHop(
                Duration.ofMillis(800),
                Duration.ofMillis(150)
        );

        return inventoryWebClient.get()
                .uri("/api/items/{sku}", sku)
                .retrieve()
                .bodyToMono(InventoryResponse.class)
                .retryWhen(
                        Retry.backoff(1, Duration.ofMillis(100))
                                .filter(error ->
                                        error instanceof WebClientRequestException)
                )
                .timeout(allowance);
    });
}
~~~

`InventoryResponse` là DTO ứng dụng; `inventoryWebClient` là field đã inject. `Mono.defer` tính allowance tại subscription, tránh chụp ngân sách quá sớm khi chỉ mới assemble reactive pipeline.

Ở đây, tối đa một retry, filter chỉ chọn `WebClientRequestException` chứ không tự retry mọi HTTP 503. `timeout(allowance)` nằm **ngoài** `retryWhen` nên bao trùm các attempts và backoff bên trong publisher. Nếu đảo thứ tự timeout/retry, timeout có thể được áp dụng cho từng subscription riêng, kéo dài thời gian tổng.

Reactive cancellation không bảo đảm backend đã dừng xử lý. Nếu một thao tác có side effect, phải dùng idempotency hoặc cơ chế xác nhận kết quả sau timeout.

Nếu ngân sách đã cạn sau một bước trước đó, `allowanceForHop` fail fast, thay vì bắt đầu GET mới với timeout mặc định.

## 13. OpenFeign: cấu hình connectTimeout và readTimeout

Với Spring Cloud OpenFeign, có thể khai báo timeout theo Feign client/service ID:

~~~yaml
spring:
  cloud:
    openfeign:
      client:
        config:
          inventory-service:
            connectTimeout: 250
            readTimeout: 700
          payment-service:
            connectTimeout: 350
            readTimeout: 1100
~~~

Các giá trị ví dụ dùng đơn vị **mili giây** theo cấu hình OpenFeign thông dụng. Chúng phải được hiệu chỉnh bằng latency/SLO thực tế của hệ thống, không coi là giá trị chung cho mọi service.

Các giới hạn trên không tự bao trùm thời gian xin access token, đợi connection pool, discovery, backoff, retry và xử lý business trước/sau Feign call. Feign có `Request.Options` và các cách tùy chỉnh HTTP transport, nhưng không có thuộc tính Spring Cloud OpenFeign phổ quát để mọi lời gọi tự nhận deadline end-to-end còn lại. Nếu cần timeout **động cho mỗi invocation**, phải thiết kế một abstraction/client customization theo transport và phiên bản đang sử dụng.

Chỉ gắn `X-Request-Timeout-Ms` qua `RequestInterceptor` cũng **không** làm HTTP client tuân thủ giá trị đó. Header mới chỉ là giao ước; server và caller phải thực thi deadline.

Cẩn trọng với payment: backend có thể đã commit giao dịch rồi caller mới gặp read timeout. Không retry POST một cách mù quáng; dùng idempotency key, kiểm tra trạng thái và reconciliation.

## 14. Chuyển ngân sách xuyên hop là một thiết kế ứng dụng

Khi order gọi inventory, rồi inventory lại gọi pricing, pricing không biết deadline người dùng nếu upstream chỉ chuyển URI và JSON.

~~~text
Gateway: tạo ngân sách 1200 ms tại ranh giới tin cậy

Order: đã mất 150 ms
       -> remaining khoảng 1050 ms
       -> gửi inventory với remaining đã giới hạn

Inventory: xử lý thêm 250 ms
       -> remaining khoảng 800 ms
       -> gửi pricing với remaining mới

Pricing: chọn timeout database từ số thời gian còn lại
       -> không tự reset budget về 1200 ms
~~~

Một header nội bộ có thể dùng làm giao ước:

~~~http
X-Request-Timeout-Ms: 800
~~~

Đây **không phải header tiêu chuẩn tự động của Spring Cloud LoadBalancer**. Nếu tự thiết kế, cần tuân thủ:

1. Gateway không tin header tùy ý từ Internet client; xóa/ghi đè ở trust boundary.
2. Parse và clamp giá trị vào min/max cho phép; từ chối/giới hạn giá trị âm, quá lớn hoặc không hợp lệ.
3. Trừ thời gian đã tiêu tốn trong hop trước khi gửi onward; không copy con số cũ.
4. Giữ phần reserve để trả response và làm những công việc còn lại.
5. Nhận header không có nghĩa transport/server đã tự áp timeout.
6. Không truyền `System.nanoTime()` giữa các máy; timestamp monotonic chỉ có ý nghĩa cục bộ.
7. Deadline wall clock giữa các host cần xét clock skew và xử lý đúng NTP.

Nếu dùng RPC stack có deadline propagation chính thức, nên ưu tiên sử dụng thay vì tự tạo giao ước riêng. Với RestClient, WebClient và Feign HTTP, giải pháp cần có integration ở tầng ứng dụng.

## 15. Phối hợp timeout gateway, caller và downstream

Một nguyên tắc là **tầng gần người dùng cần có thời gian tạo response lỗi có kiểm soát** trước khi reverse proxy/gateway tự chấm dứt việc chờ.

Ví dụ:

~~~text
External client timeout:                1600 ms
Gateway upstream timeout:               1450 ms
Order end-to-end processing budget:     1250 ms
Inventory per-hop timeout cap:           450 ms
Pricing per-hop timeout cap:             350 ms
Reserve cho response/jitter:             phần còn lại
~~~

Đây chỉ là số minh họa. Nếu gateway chờ ngắn hơn budget xử lý nội bộ, gateway có thể trả 504 trong khi order vẫn giữ thread/connection và gọi xuống các service khác.

Những chỗ cần kiểm soát thêm:

- Server-side timeout không phải lúc nào cũng hủy business code đồng bộ; một thuộc tính Spring MVC async timeout không tự cắt mọi lời gọi blocking.
- Client timeout đóng kết nối hoặc trả exception không đồng nghĩa downstream ngừng xử lý.
- Connection pool acquire timeout và queueing time có thể làm deadline cạn trước khi network I/O bắt đầu.
- Executor saturation và thời gian xếp hàng cũng phải được tính vào deadline.
- Gateway và service có thể đều retry, nên cần kiểm kê toàn bộ số lần thử.

Nếu một phần dữ liệu không thiết yếu, ví dụ recommendations, hãy ưu tiên timeout ngắn và trả partial result/fallback được cho phép, thay vì kéo dài toàn bộ nghiệp vụ.


## 16. Cancellation không đồng nghĩa rollback

Timeout không bảo đảm mọi tài nguyên và tác dụng phụ đã được giải phóng. Một payment request có thể đã commit giao dịch dù caller không nhận được response:

~~~mermaid
sequenceDiagram
    participant U as User
    participant O as order-service
    participant P as payment-service
    participant D as Payment database

    U->>O: POST /orders (deadline 1200 ms)
    O->>P: POST /payments
    P->>D: Begin transaction
    Note over O: Deadline exhausted
    O-->>U: Timeout response
    P->>D: Commit transaction
    D-->>P: Commit OK
    Note over P: Side effect có thể đã xảy ra
~~~

Khi WebClient publisher bị cancel hoặc RestClient/OpenFeign ném timeout, backend **có thể vẫn tiếp tục** thực thi; không nên giả định network cancellation tự rollback database.

Đối với thao tác ghi:

- Dùng **idempotency key** để nhận diện yêu cầu trùng lặp.
- Lưu trạng thái giao dịch đủ để truy vấn lại kết quả sau timeout.
- Không retry mù POST thanh toán, tạo đơn hoặc cập nhật kho.
- Cân nhắc saga/compensation hoặc cơ chế reconciliation.
- Nếu công việc dài hơn khả năng chờ HTTP, có thể trả `202 Accepted` cùng job ID, sau đó polling/webhook hoặc xử lý bất đồng bộ.
- Server có thể xử lý cancellation một cách có chủ đích, nhưng chỉ dừng ở điểm an toàn.

## 17. Timeout kết hợp circuit breaker, bulkhead và load shedding

Timeout giới hạn **thời gian chờ**, còn các cơ chế khác giải quyết những vấn đề bổ sung:

| Cơ chế | Câu hỏi chính |
|---|---|
| Deadline/timeout | Còn được phép đợi bao lâu? |
| Circuit breaker | Có nên tiếp tục gọi phụ thuộc đang lỗi nhiều không? |
| Bulkhead/semaphore | Được phép có bao nhiêu lời gọi đồng thời? |
| Rate limiting/load shedding | Có nên nhận thêm tải khi đã bão hòa? |
| Retry/backoff | Có nên thử lại? Số lần và khoảng cách bao nhiêu? |
| Spring Cloud LoadBalancer | Chọn instance nào từ tập ứng viên? |
| Health-check supplier | Instance nào hiện được đánh giá đủ khỏe? |
| Idempotency | Gửi cùng yêu cầu nhiều lần có an toàn không? |

Ví dụ pricing chậm và có 200 requests đồng thời: đặt read timeout 10 giây có thể vẫn giữ số lượng lớn threads/connections tới pricing. Kết hợp timeout ngắn, bulkhead và circuit breaker có thể giới hạn tình trạng cạn pool, khiến order-service cũng ngừng phục vụ các nghiệp vụ khác.

Không mặc định bật retry + circuit breaker ở nhiều tầng mà không quan sát. Một circuit breaker mở có thể fail fast dù còn deadline; đó có thể là kết quả đúng nhằm bảo vệ hệ thống.

## 18. Quan sát latency, retry và thời gian còn lại

Nếu log chỉ có dòng “request timed out”, không thể biết lỗi nằm ở discovery, pool, connect, TLS, backend, token server hay backoff. Một hệ thống quan sát tốt có thể thu thập:

| Nhóm dữ liệu | Câu hỏi cần trả lời |
|---|---|
| End-to-end latency histogram | Người dùng chờ bao lâu, p95/p99 có đạt SLO? |
| Remaining budget ở từng hop | Chặng nào tiêu hao quá nhiều thời gian? |
| Connection pool acquire latency | Pool có cạn, request xếp hàng lâu không? |
| Connect/TLS duration | Có chậm thiết lập kết nối không? |
| Time to first byte/response latency | Backend xử lý chậm hay network chậm? |
| Service discovery/selection latency | Registry hoặc LoadBalancer supplier có chậm không? |
| Retry count, backoff | Một nghiệp vụ thực sự gửi bao nhiêu attempts? |
| Error category | Connect timeout, read timeout, total deadline, HTTP 503/504 khác nhau thế nào? |
| Service ID/instance ID | Lỗi tập trung ở một replica hay tất cả instance? |
| Canceled/late work | Backend có tiếp tục sau khi caller đã từ bỏ kết quả? |

Dùng Micrometer Observation/Tracing, Spring Cloud LoadBalancer lifecycle metrics và HTTP-client instrumentation theo phiên bản đang dùng. Không đưa bearer token, query có dữ liệu nhạy cảm hay ID người dùng thô vào metric labels hoặc log không kiểm soát.

Phải phân biệt **logical request** với **HTTP attempt**:

~~~text
1 logical quote request
   -> inventory logical call
        -> attempt 1: connect timeout
        -> attempt 2: 200 OK
   -> pricing logical call
        -> attempt 1: 200 OK

Logical quote requests:       1
Downstream HTTP attempts:     3
~~~

Nếu order chỉ đếm logical calls còn inventory backend đếm mỗi attempt, số liệu có thể không khớp mà không có bug. Hãy đặt tên metric và logging nhất quán, tương quan bằng trace/correlation ID, nhưng không dùng trace context như dữ liệu phân quyền.

## 19. Bài thực hành: một backend chậm trong chuỗi request

Dùng `SimpleDiscoveryClient` trong order-service để có hai replica inventory:

~~~yaml
server:
  port: 8080

spring:
  application:
    name: order-service
  cloud:
    discovery:
      client:
        simple:
          instances:
            inventory-service:
              - uri: http://localhost:8081
              - uri: http://localhost:8082
~~~

Ở inventory-service, thêm endpoint mô phỏng độ trễ, **chỉ dành cho môi trường thử nghiệm**:

~~~java
package com.example.inventory;

import java.util.Map;
import org.springframework.core.env.Environment;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DelayController {

    private final Environment environment;

    public DelayController(Environment environment) {
        this.environment = environment;
    }

    @GetMapping("/demo/delay")
    public Map<String, Object> delay(
            @RequestParam(defaultValue = "100") long delayMs)
            throws InterruptedException {

        // Chỉ cho phép dải nhỏ trong lab; không công khai endpoint.
        long boundedDelay = Math.max(0L, Math.min(delayMs, 1500L));
        Thread.sleep(boundedDelay);

        return Map.of(
                "instance", environment.getProperty(
                        "server.port", "unknown"),
                "delayMs", boundedDelay
        );
    }
}
~~~

Chạy cùng artifact inventory trên hai cổng 8081 và 8082. Trong order-service, dùng RestClient/WebClient có load balancing hoặc OpenFeign gọi `http://inventory-service/demo/delay?delayMs=...`, đồng thời tạo một endpoint `GET /orders/demo-delay?ms=...` làm proxy. Đây là endpoint **cần triển khai** trong lab, không phải tính năng có sẵn của Spring Cloud.

Thử ba kịch bản:

1. **Bình thường:** inventory trì hoãn 100 ms, deadline caller 900 ms, request hoàn thành, còn thời gian dự phòng.
2. **Backend chậm:** inventory trì hoãn 1.100 ms, caller giới hạn hop 450 ms. Quan sát connect/read/response/total timeout và backend có thể tiếp tục xử lý sau khi caller hết thời gian.
3. **Một replica chết:** dừng cổng 8082; discovery tĩnh vẫn có thể trả địa chỉ này. Quan sát connect failure, retry có giới hạn và health supplier nếu được cấu hình.

PowerShell minh họa đo thời gian bên ngoài:

~~~powershell
Measure-Command { try { Invoke-RestMethod -Uri "http://localhost:8080/orders/demo-delay?ms=1100" -TimeoutSec 3 | Out-Null } catch { Write-Host $_.Exception.Message } }
~~~

`-TimeoutSec 3` chỉ điều khiển timeout của **PowerShell client**, không tự đặt timeout cho RestClient, WebClient hoặc Feign trong order-service.

Ghi lại số liệu:

| Case | Deadline tổng | Hop cap | Backend delay | Attempts | Latency thực | Kết quả |
|---|---:|---:|---:|---:|---:|---|
| Bình thường | 900 ms | 450 ms | 100 ms | Đo | Đo | Thành công dự kiến |
| Backend chậm | 900 ms | 450 ms | 1.100 ms | Đo | Đo | Timeout dự kiến |
| Một replica chết | 900 ms | 450 ms | — | Đo | Đo | Phụ thuộc discovery/retry |

Không điền latency hoặc attempts giả khi chưa chạy lab. Hãy đo cả caller và backend để so sánh số attempts với số logical requests.

## 20. Những lỗi thiết kế timeout thường gặp

| Hiện tượng | Sai lầm phổ biến | Hướng khắc phục |
|---|---|---|
| Gateway trả 504, order vẫn chạy | Gateway timeout ngắn hơn budget nội bộ | Phối hợp deadline, xử lý cancellation và late work |
| Mỗi hop timeout 2 giây, request tổng mất 6 giây | Không có end-to-end budget | Tạo deadline tổng và tính remaining trước mỗi hop |
| WebClient retry kéo dài quá deadline | Đặt `timeout` bên trong retry hoặc reset deadline | Bao toàn bộ retry với deadline cũ |
| OpenFeign readTimeout không chặn token server treo | Token acquisition ở ngoài Feign transport | Đặt token endpoint timeout và deadline tổng |
| Pool chờ lâu dù connect timeout ngắn | Không giới hạn acquisition từ connection pool | Cấu hình pool/acquire timeout và concurrency |
| HTTP 503 bị hiểu thành read timeout | Không có instance/proxy/backend trả status | Phân loại lỗi selection/status/transport |
| Health-check interval bị dùng như request timeout | Nhầm lịch probe với HTTP timeout | Cấu hình transport timeout riêng |
| Tạo giao dịch hai lần | Retry POST sau response timeout | Idempotency key, kiểm tra kết quả và reconciliation |
| Mọi service đều retry nhiều lần | Retry amplification giữa các tầng | Chỉ định tầng retry và tổng attempt budget |
| Backend nhận nhiều request hơn metric caller | Một logical call có nhiều HTTP attempts | Tách chỉ số logical và attempt |
| Ngân sách tăng qua từng hop | Reset budget hoặc copy header cũ | Decrement remaining, clamp header và giữ reserve |
| Payment vẫn commit sau timeout | Timeout caller không rollback transaction | Thiết kế cancellation/side effect riêng |
| p99 fan-out kém hơn từng service | Nhiều nhánh phải cùng hoàn thành | Giảm fan-out, fallback cho nhánh không thiết yếu |

## 21. Checklist trước khi release

- [ ] Có SLO/deadline đầu-cuối rõ ràng cho mỗi API.
- [ ] Phân biệt chuỗi tuần tự, fan-out song song và job bất đồng bộ.
- [ ] Mỗi hop dùng budget còn lại, không reset từ timeout mặc định.
- [ ] Giữ dự phòng cho công việc còn lại và trả response.
- [ ] Tách connection pool acquire, connect, TLS, response/read, discovery và total timeout.
- [ ] RestClient/WebClient/OpenFeign có cấu hình transport timeout đúng nhu cầu.
- [ ] Retry có giới hạn attempt, backoff và nằm trong deadline cũ.
- [ ] Không retry side effects khi chưa có idempotency/reconciliation.
- [ ] Gateway, caller và downstream có các giới hạn phù hợp.
- [ ] Server không giả định timeout caller đồng nghĩa backend work đã hủy.
- [ ] Nếu dùng deadline header, validate, clamp, giảm theo elapsed time.
- [ ] Không truyền `System.nanoTime()` trực tiếp xuyên máy.
- [ ] Có timeout riêng cho token server, database, queues và pool.
- [ ] Xem xét bulkhead/circuit breaker/load shedding để tránh cascading failure.
- [ ] Có metrics phân biệt logical calls, attempts và từng loại timeout.
- [ ] Thử backend chậm, replica chết, pool cạn, token server chậm và retry chồng tầng.
- [ ] Kiểm chứng kết quả bằng p95/p99 end-to-end load testing, không chỉ đọc YAML.

## Tài liệu tham khảo

- [Spring Cloud Commons — Spring Cloud LoadBalancer](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html): `ServiceInstance`, discovery, caching, health check và retry.
- [Spring Framework — REST Clients](https://docs.spring.io/spring-framework/reference/integration/rest-clients.html): RestClient và request factory.
- [Spring Framework — WebClient](https://docs.spring.io/spring-framework/reference/web/webflux-webclient.html): client reactive, status, filters và timeout.
- [Spring Cloud OpenFeign — Reference](https://docs.spring.io/spring-cloud-openfeign/reference/spring-cloud-openfeign.html): Feign client, connect/read timeout và LoadBalancer.
- [Reactor Core — Reference](https://projectreactor.io/docs/core/release/reference/): `Mono.timeout`, retry, cancellation và composition.
- [Spring Boot — Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html): metrics và distributed tracing.

**Kết luận:** trong chuỗi nhiều dịch vụ, câu hỏi không chỉ là “`readTimeout` nên là bao nhiêu?” mà là “mỗi chặng được phép tiêu bao nhiêu **ngân sách còn lại** của request có deadline chung?”. Timeout transport bảo vệ tài nguyên cục bộ; deadline đầu-cuối bảo vệ SLO; retry, LoadBalancer, health check, circuit breaker và observability phải phối hợp trong ngân sách đó. Tính remaining đúng thời điểm, không reset deadline và kiểm soát tác dụng phụ sau timeout sẽ giúp giảm tail latency, retry amplification và cascading failure.
