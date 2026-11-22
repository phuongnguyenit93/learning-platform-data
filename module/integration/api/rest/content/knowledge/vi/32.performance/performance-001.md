# Đặt ngân sách độ trễ và xác định đường xử lý quan trọng

## 1. Bài toán: API nhanh trung bình nhưng người dùng vẫn phải chờ

Orders API trả **GET /api/orders/{id}** với thời gian trung bình **85 ms**, nhưng đôi khi mất **1,5 giây** khi dịch vụ tồn kho chậm. Dashboard chỉ hiển thị trung bình nên báo “ổn”; nhân viên bán hàng lại than trang chi tiết đơn thỉnh thoảng treo. Nhóm phát triển tăng số thread ở Spring Boot nhưng không xác định request đang chờ **database, downstream hay hàng đợi kết nối**. Kết quả: CPU tăng, độ trễ đuôi (*tail latency*) vẫn xấu.

Để cải thiện có căn cứ, cần trả lời:

1. **Đo từ đâu đến đâu?** Độ trễ tại client, gateway hay tại server?
2. **Nhanh đến mức nào là đạt?** Ngân sách và SLO của từng operation là gì?
3. **Đường xử lý nào quyết định tổng thời gian?** Phần nào chạy tuần tự, phần nào có thể song song?
4. **Khi phụ thuộc chậm hoặc quá tải, ai dừng trước?** Deadline, timeout, retry, queue và fallback phối hợp ra sao?
5. **Đo bằng dữ liệu nào để xác nhận?** Metrics phân vị, tracing và kiểm thử tải có điều kiện tái lập.

Bài thuộc chương **Hiệu năng** của module **INTEGRATION_API_REST**: thiết kế REST dựa trên resource, URI, HTTP method/status và hợp đồng dữ liệu; cùng phân trang, cache, idempotency, OpenAPI, xác thực, phân quyền, xử lý lỗi và kiểm thử bằng Java/Spring hoặc công nghệ tương đương. Trọng tâm là **lập ngân sách độ trễ (latency budget) và xác định critical path**, không phải tối ưu mọi dòng Java hay viết lại bài về cache, pagination.

**Kết quả học tập:** định nghĩa SLI/SLO có mẫu đo rõ, phân rã request thành các bước và nhánh song song, đặt timeout theo deadline còn lại, dùng metrics/tracing tìm bottleneck, thiết kế graceful degradation không phá quyền/nghiệp vụ và kiểm thử tải lẫn fault injection.

## 2. Định nghĩa độ trễ trước khi phân bổ ngân sách

**Latency** là thời gian hoàn thành một operation theo điểm quan sát đã xác định. Một request có nhiều mốc:

~~~text
Client                  Gateway                  Spring API            DB/Downstream
  |-- DNS/TLS/RTT -------->|-- routing ------------>|-- auth, handler ---->|-- query/call --|
  |                       |                        |<------ response ------|                |
  |<------- response -----|<------------------------|                                        |
~~~

| Phép đo | Bắt đầu / kết thúc | Phù hợp với |
| --- | --- | --- |
| **Client-perceived latency** | Trước khi client gửi đến lúc nhận đủ response. | SLO trải nghiệm thực, gồm mạng và buffering. |
| **Edge/gateway latency** | Gateway nhận request đến lúc phát xong response. | SLO server-side xuyên tầng proxy/API. |
| **Application handler latency** | Spring bắt đầu xử lý đến lúc kết thúc tại điểm instrument. | Đánh giá ứng dụng, không bao hàm toàn bộ mạng. |
| **Dependency latency** | Bắt đầu gọi DB/HTTP đến lúc nhận kết quả. | Tìm phụ thuộc chậm, gồm đợi connection nếu có đo. |
| **Queue wait** | Request/task xếp hàng đến khi bắt đầu phục vụ. | Phát hiện bão hòa pool, backlog, connection acquisition. |

Nếu SLO đo tại gateway nhưng dashboard lấy timer controller, **không được xem là cùng chỉ số**. Ghi rõ tuyến API, method, loại client, region, kích thước payload, status, điều kiện tải, cửa sổ thời gian và vị trí đặt đồng hồ.

### 2.1. SLI, SLO và error budget khác latency budget

- **SLI (Service Level Indicator):** phép đo cụ thể, ví dụ phân phối độ trễ GET một order ở gateway hoặc tỷ lệ request dưới ngưỡng.
- **SLO (Service Level Objective):** mục tiêu, ví dụ trong 28 ngày, ít nhất **95%** GET hợp lệ hoàn thành dưới **300 ms** tại gateway. Có thể thêm **p99 < 700 ms**; đây là **mục tiêu minh họa**, không phải chuẩn bắt buộc của REST.
- **Latency budget:** tổng thời gian muốn phân bổ cho các bước và khoảng dự phòng, chẳng hạn **300 ms** cho GET.
- **Error budget:** tỷ lệ request được phép không đạt SLO trong cửa sổ, **không phải số milliseconds còn lại của request**.

Không lấy p95 từ 5 request rồi kết luận đạt SLO tháng: cần lưu lượng đủ, cửa sổ đo và số mẫu. Với lưu lượng thấp, trình bày mức độ không chắc chắn.

### 2.2. Trung bình, p50, p95, p99 khác nhau

Giả sử 100 GET: **95 request mất 60 ms**, còn **5 request mất 1.000 ms**. Trung bình **107 ms** nhưng người dùng trong nhóm chậm vẫn chờ một giây. Phân vị p95/p99 giúp thấy phần đuôi (giá trị cụ thể phụ thuộc định nghĩa/nội suy quantile):

- **p50** mô tả trải nghiệm điển hình; **p95/p99** phản ánh đuôi chậm do queue, GC, contention, downstream hoặc retry.
- **Mean** hữu ích cho một số phân tích workload nhưng dễ che tỷ lệ nhỏ request rất chậm.
- **Không cộng p95 của từng bước để suy ra p95 end-to-end**: phân vị không có tính cộng tuyến tính. Tương tự, **max(p95 của A, p95 của B)** không chính xác là p95 của max(A,B) khi chạy song song.

Ngân sách bước là **mục tiêu thiết kế có khoảng đệm**; phải xác nhận bằng phân phối end-to-end đo thật.

## 3. Xác định đường xử lý quan trọng (critical path)

Một request có thể biểu diễn thành đồ thị phụ thuộc (DAG). **Critical path** là đường có tổng thời gian dài nhất trong các nhánh bắt buộc hoàn thành **trước** khi API trả response. Việc chạy sau response (audit async hợp lệ, indexing bất đồng bộ) không nằm trên critical path trực tiếp, nhưng vẫn có SLO và side effects cần theo dõi.

Ví dụ **GET /api/orders/{id}** cần:

~~~mermaid
flowchart LR
    A["Ingress + authentication 20 ms"] --> B["DB đọc order 65 ms"]
    B --> C["Pricing service 80 ms"]
    B --> D["Inventory service 110 ms"]
    C --> E["Ghép DTO + serialize 20 ms"]
    D --> E
    E --> F["Response/edge 15 ms"]
~~~

Giả sử các số là **thời gian minh họa của một request**, không phải p95 độc lập. Nếu Pricing và Inventory chạy **tuần tự**, critical path bằng **20 + 65 + 80 + 110 + 20 + 15 = 310 ms**. Nếu hai lời gọi **độc lập và thực sự chạy đồng thời**, đường dài đi qua Inventory: **20 + 65 + max(80, 110) + 20 + 15 = 230 ms**. Nhánh Pricing kết thúc sớm hơn nhưng vẫn tiêu thụ connection/CPU/quota và có rủi ro lỗi riêng.

**Song song không miễn phí:** nếu hai phụ thuộc độc lập có xác suất 95% hoàn thành trước ngưỡng của từng cái, xác suất cả hai đều nhanh chỉ khoảng **0,95 × 0,95 = 90,25%**. Fan-out lớn có thể làm **tail latency và failure rate** xấu đi dù thời gian trung bình giảm. Đừng mở vô hạn request/thread để “đi song song”.

### 3.1. Cách nhận diện critical path từ trace

1. Chọn **trace hoàn chỉnh** cùng route/status/traffic shape; tìm root server span và child spans.
2. So **start/end time**: DB query, connection acquisition, outbound HTTP, JSON encode, security filters, queue/task scheduling.
3. Tính **đoạn nối tiếp và nhánh cuối cùng hoàn thành**. Cộng tất cả child span durations dễ **đếm trùng đoạn đồng thời**.
4. Phân biệt **self-time** và đợi downstream/lock/pool. Method có span 200 ms không nhất thiết dùng CPU 200 ms.
5. Lặp trên nhiều traces của **p95/p99 và khi tải cao**; critical path có thể đổi theo loại request.

Metrics toàn luồng cho biết phân phối; tracing giúp giải thích. Tail-based sampling có thể giữ trace chậm/lỗi nhưng phải kiểm chi phí và dữ liệu nhạy cảm.

### 3.2. Các đường xử lý đặc biệt

| Operation | Critical path thường có | Không nên cưỡng ép vào đường đồng bộ |
| --- | --- | --- |
| **GET /orders/{id}** | Auth → DB/cache → enrichment cần thiết → serialize. | Search reindex, email notification. |
| **GET /orders?status=...** | Auth/tenant filter → DB/search query → pagination/serialize. | N+1 fetch không giới hạn. |
| **POST /orders** | Validate/auth → transaction/constraint/idempotency → commit → response. | Email/analytics đối tác trong transaction. |
| **POST /exports** | Validate/authorize → ghi job bền vững → 202 monitor. | Tạo file lớn trước khi trả ACK. |

Không tối ưu bằng cách bỏ validation, tenant authorization, idempotency hoặc DB constraints. Nếu chuyển bước sang async, phải thay đổi **hợp đồng HTTP và trạng thái** tương ứng, không trả 201 khi tài nguyên chưa được tạo.

## 4. Phân bổ budget có slack, không biến nó thành phép cộng p95

Giả sử mục tiêu **gateway-to-response p95 ≤ 300 ms** cho GET một order trong một region, payload tối đa 25 KiB, ở mức tải dự kiến. Bảng là **mục tiêu bước để lập kế hoạch**, không phải cộng các p95 thống kê:

| Bước nằm trên critical path | Mục tiêu thiết kế |
| --- | ---: |
| Gateway/edge overhead | 20 ms |
| Authentication + authorization | 20 ms |
| DB đọc order (gồm chờ connection) | 65 ms |
| Nhánh dài nhất trong Pricing/Inventory chạy song song | 110 ms |
| Mapping/serialization/response hoàn tất | 25 ms |
| **Slack** cho scheduling, GC và biến động khác | **60 ms** |
| **Tổng kế hoạch** | **300 ms** |

Slack **không phải thời gian được phép tiêu lãng phí**: nó hấp thụ biến động mà bảng mục tiêu không giải thích hết. Các ngưỡng phải điều chỉnh từ trace thực tế và **kiểm lại bằng SLI end-to-end**.

### 4.1. Deadline khác timeout

- **Deadline:** mốc cuối cùng mà toàn bộ operation còn giá trị; mỗi bước tính **remaining time**.
- **Connect timeout:** giới hạn chờ thiết lập connection.
- **Read/response timeout:** giới hạn chờ server gửi/đọc response.
- **Queue/acquisition timeout:** giới hạn chờ thread, HTTP connection pool hoặc DB connection.
- **Retry budget:** thời gian và số attempts được phép trong deadline còn lại.

**Không đặt mỗi downstream timeout 300 ms rồi kỳ vọng API 300 ms**. Nếu DB đã dùng 80 ms, còn serialization và slack, inventory được phép dùng ít hơn 300 ms. Phải giới hạn tổng theo remaining deadline.

### 4.2. Dùng đồng hồ đơn điệu để tính elapsed

Trong Java, **System.nanoTime()** phù hợp đo khoảng thời gian trong cùng process, không dùng **Instant.now()** để đo elapsed vì wall clock có thể điều chỉnh. Qua service/process khác, truyền timeout hoặc deadline đã định nghĩa theo protocol/library; đồng hồ các máy có thể lệch. Không tin một header deadline do caller tự gửi để mở rộng quota vô hạn.

## 5. Java/Spring: giới hạn mỗi bước theo thời gian còn lại

### 5.1. Deadline helper cho một request đồng bộ

Trong một service Java, có thể tính deadline một lần khi bắt đầu operation rồi truyền object này đến các lời gọi cần giới hạn. Ví dụ Java 17+:

~~~java
import java.time.Duration;

final class Deadline {
    private final long endNanos;

    private Deadline(long endNanos) {
        this.endNanos = endNanos;
    }

    static Deadline after(Duration totalBudget) {
        if (totalBudget.isZero() || totalBudget.isNegative()) {
            throw new IllegalArgumentException("Budget must be positive");
        }
        return new Deadline(System.nanoTime() + totalBudget.toNanos());
    }

    Duration remainingCapped(Duration localCap) {
        long remaining = endNanos - System.nanoTime();
        if (remaining <= 0) {
            throw new DeadlineExceededException();
        }
        long capped = Math.min(remaining, localCap.toNanos());
        if (capped <= 0) {
            throw new DeadlineExceededException();
        }
        return Duration.ofNanos(capped);
    }
}

class DeadlineExceededException extends RuntimeException {}
~~~

**Giới hạn:** deadline này là **in-process**, không phải timestamp gửi cho hệ thống khác; chỉ dùng ngân sách có giới hạn thực tế để tránh overflow không cần thiết. Với API gateway có deadline riêng, ứng dụng cần trừ phần đã tiêu và reserve thời gian hoàn tất response. Khi hết thời gian, phải **dừng bắt đầu công việc mới**, không chỉ trả lỗi ở cuối sau khi mọi thứ vẫn tiếp tục chạy.

### 5.2. HTTP downstream có cả connect và request timeout

Ví dụ JDK HttpClient được một Spring service sử dụng để gọi inventory; URI đích cố định, item ID dạng UUID, không nhận URL từ người dùng:

~~~java
import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.UUID;

final class InventoryHttpClient {
    private final HttpClient client = HttpClient.newBuilder()
            .connectTimeout(Duration.ofMillis(50))
            .followRedirects(HttpClient.Redirect.NEVER)
            .build();

    String readInventory(
            UUID itemId, String serviceAccessToken, Deadline deadline)
            throws IOException, InterruptedException {
        Duration timeout = deadline.remainingCapped(
                Duration.ofMillis(120));

        HttpRequest request = HttpRequest.newBuilder(
                URI.create("https://inventory.internal.example/api/items/"
                        + itemId))
                .timeout(timeout)
                .header("Accept", "application/json")
                .header("Authorization",
                        "Bearer " + serviceAccessToken)
                .GET()
                .build();

        HttpResponse<String> response = client.send(
                request, HttpResponse.BodyHandlers.ofString(
                        StandardCharsets.UTF_8));

        if (response.statusCode() != 200) {
            throw new IllegalStateException(
                    "Inventory response status " + response.statusCode());
        }
        return response.body(); // Ví dụ: deserialize DTO JSON có giới hạn.
    }
}
~~~

**Bản mẫu chưa phải client production:** caller phải xử lý timeout, InterruptedException (phục hồi interrupt flag nếu bắt để xử lý), status 401/403/404/429/5xx khác nhau, response size, token provider, circuit breaker và các retry có kiểm soát. **HttpRequest.timeout** không thay toàn bộ request deadline ở gateway: thời gian queue trong ứng dụng và serialize vẫn tiêu budget; **connectTimeout** không thay read/request timeout. Gọi HTTP có thể kết thúc muộn hơn thời điểm client bỏ chờ nếu tầng thấp không hỗ trợ hủy; không được giả định timeout là rollback side effect ở downstream.

### 5.3. Spring RestClient: timeout theo factory, không chỉ ở controller

Với **Spring Framework 6.1+**, ví dụ tạo một client có transport và timeout tường minh:

~~~java
import java.net.http.HttpClient;
import java.time.Duration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.JdkClientHttpRequestFactory;
import org.springframework.web.client.RestClient;

@Configuration
class DownstreamClientConfig {
    @Bean
    RestClient pricingClient(RestClient.Builder builder) {
        HttpClient jdk = HttpClient.newBuilder()
                .connectTimeout(Duration.ofMillis(50))
                .followRedirects(HttpClient.Redirect.NEVER)
                .build();

        JdkClientHttpRequestFactory transport =
                new JdkClientHttpRequestFactory(jdk);
        transport.setReadTimeout(Duration.ofMillis(110));

        return builder
                .baseUrl("https://pricing.internal.example")
                .requestFactory(transport)
                .build();
    }
}
~~~

**Read timeout của request factory và connect timeout không tự giới hạn tổng end-to-end** (queue, retry, xử lý trước/sau call); API cần quản lý deadline tổng ở service/orchestrator. Tùy HTTP engine và phiên bản Spring, thuộc tính timeout cụ thể và hành vi connection pool khác nhau, nên **kiểm thử transport thực tế** thay vì chỉ thấy property đã được cấu hình. Không tạo HttpClient mới cho mỗi request; tái sử dụng client/pool.

### 5.4. Mapping timeout sang HTTP phải đúng ngữ nghĩa

**Timeout outbound không đồng nghĩa HTTP 504 trong mọi tình huống.** Gateway/proxy có thể trả **504 Gateway Timeout** khi không nhận upstream response kịp; một backend ứng dụng gọi dependency mà timeout có thể trả **503 Service Unavailable**, 502/504 theo kiến trúc proxy hoặc Problem Details do contract định nghĩa. Phân loại theo vị trí lỗi, retriability và khả năng fallback; không đổi mọi exception thành **408 Request Timeout** (408 nói về server chờ nhận request từ client).

Không retry **POST có side effect** chỉ vì timeout: downstream có thể đã commit. Nếu API dùng idempotency key, retry phải **cùng key/cùng logical command** theo hợp đồng; với GET an toàn, vẫn cần giới hạn attempt và deadline còn lại.

## 6. Tìm chi phí thực: CPU, database, pool, serialization và hàng đợi

Critical path không chỉ gồm những span có tên HTTP call. Một request có thể chậm vì **đợi tài nguyên** trước khi thực hiện công việc:

| Dấu hiệu | Nguyên nhân có thể | Dữ liệu để phân biệt |
| --- | --- | --- |
| p99 tăng khi QPS tăng, CPU vẫn thấp | DB/HTTP pool chờ, lock, downstream saturation. | Connection acquisition wait, active/idle/pending, DB lock wait. |
| CPU cao, runnable threads nhiều | JSON serialization nặng, regex, crypto, GC pressure, quá nhiều concurrent requests. | CPU profile, allocation/GC, thread dump, JFR. |
| Một GET tạo hàng trăm SQL calls | **N+1 queries** khi ORM duyệt collection. | Query count per request, SQL spans, batch/fetch plan. |
| Response lớn tăng tail | Payload/serialization, nén dữ liệu, client/network throughput. | Bytes response, serialization time, outbound bytes/TTFB. |
| p95 thấp nhưng p99 có spike theo chu kỳ | GC pause, cache expiry, batch job, connection churn. | GC pause timeline, cache misses, scheduler activity. |
| CPU bình thường nhưng queue depth tăng liên tục | Arrival rate > service capacity hoặc bottleneck chung. | Incoming RPS, throughput, queue latency, rejection metrics. |

### 6.1. N+1 trên endpoint collection

Ví dụ một **GET /api/orders?limit=50** trả 50 orders, mỗi order lại gọi DB lấy customer và inventory: số round trips có thể lên đến **1 + 50 + 50**, dù SQL từng query chạy vài ms. Sửa bằng DTO projection, batch lookup/IN có giới hạn, join/fetch plan có kiểm soát hoặc denormalized read model phù hợp. Đừng tự động join mọi collection trong JPA để tránh N+1: có thể gây row multiplication và phá pagination.

**Chọn query plan theo dữ liệu thật**: index đúng filter/sort, unique tie-breaker cho pagination, truy vấn parameterized và kiểm tenant scope. Tối ưu bằng cách bỏ tenant predicate hay cache chung dữ liệu riêng tư là sai về bảo mật.

### 6.2. Hàng đợi có thể phá latency trước khi CPU lên 100%

Quan hệ **Little's Law** ở trạng thái ổn định: số request đang ở trong hệ thống **L ≈ λ × W**, với λ là throughput (request/giây) và W là thời gian trung bình (giây). Nếu 150 req/s, W=0,2 s thì trung bình có khoảng **30 request** trong hệ thống; khi W tăng lên 1 s, con số khoảng **150** dù lượng request vào không đổi. Đây là **quan hệ trung bình khi hệ thống ổn định**, không phải công thức dự đoán chính xác p99 hoặc hàng đợi ở thời điểm bất kỳ.

Khi tiến gần năng lực xử lý tối đa, queue time thường tăng mạnh. Tăng số thread mà không tăng DB pool/downstream capacity có thể làm **nhiều request cùng chờ hơn**, tăng memory, timeouts và retry storms. Cần đo **arrival rate, service rate, concurrency, queue depth, drops/rejections** và giới hạn intake.

### 6.3. Hạn chế fan-out và chọn công việc phải đồng bộ

- Chỉ gọi các phụ thuộc **thực sự cần cho representation hiện tại**; một trường phụ có thể tải theo yêu cầu hoặc phục vụ từ projection đã chấp nhận eventual consistency.
- Khi parallelize, giới hạn **số kết nối, số task, số downstream in-flight**; dùng bulkhead/circuit breaker khi phù hợp.
- Nếu inventory là dữ liệu quyết định **cho phép bán hay không**, không được dùng giá trị stale vô điều kiện để giảm độ trễ. Nếu pricing không có kết quả, chọn lỗi rõ ràng hoặc fallback đã được product/business chấp thuận.
- Không chạy external HTTP bên trong DB transaction dài; dễ giữ lock khi network timeout và làm xấu mọi request khác.

## 7. Song song hóa đúng cách: WebFlux và deadline toàn pipeline

Ở Spring WebFlux, **Mono.zip** đợi nhiều publisher độc lập và trả khi đủ kết quả. Ví dụ dưới đây minh họa chỉ về pipeline, giả định database driver/repository và HTTP client là **reactive/non-blocking**:

~~~java
import java.time.Duration;
import java.util.UUID;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

record OrderRecord(UUID id, UUID itemId, String status) {}
record Price(long amountMinorUnit) {}
record Availability(boolean inStock) {}
record OrderDetails(UUID id, String status,
                    long amountMinorUnit, boolean inStock) {}

interface ReactiveOrderRepository {
    Mono<OrderRecord> findAuthorized(String actor, UUID id);
}
interface PricingGateway {
    Mono<Price> getPrice(UUID itemId);
}
interface InventoryGateway {
    Mono<Availability> getAvailability(UUID itemId);
}

@Service
class OrderDetailsService {
    private final ReactiveOrderRepository orders;
    private final PricingGateway pricing;
    private final InventoryGateway inventory;

    OrderDetailsService(ReactiveOrderRepository orders,
                        PricingGateway pricing,
                        InventoryGateway inventory) {
        this.orders = orders;
        this.pricing = pricing;
        this.inventory = inventory;
    }

    Mono<OrderDetails> getAuthorized(UUID id, String actor) {
        return orders.findAuthorized(actor, id)
                .switchIfEmpty(Mono.error(new OrderNotFoundException()))
                .flatMap(order -> Mono.zip(
                        pricing.getPrice(order.itemId()),
                        inventory.getAvailability(order.itemId()))
                    .map(tuple -> new OrderDetails(
                            order.id(), order.status(),
                            tuple.getT1().amountMinorUnit(),
                            tuple.getT2().inStock())))
                .timeout(Duration.ofMillis(240));
    }
}

class OrderNotFoundException extends RuntimeException {}
~~~

**Lưu ý:** Mono.zip bắt đầu cả hai nhánh khi được subscribe, không block trong WebFlux handler. Timeout **240 ms bao trùm pipeline này**, chưa tính một phần ingress/serialization/gateway; mục tiêu gateway 300 ms cần reserve phần còn lại. Timeout Reactor gửi tín hiệu cancel tới upstream, **không chứng minh downstream đã dừng tính toán hoặc rollback tác dụng**. Cấu hình timeout, connection pool, concurrency limit và circuit breaker **riêng từng WebClient/gateway**, không chỉ một timeout ở Mono ngoài.

Nếu DB access là **blocking JPA/JDBC**, không gọi trực tiếp trên event loop rồi xem như non-blocking. Dùng mô hình Spring MVC hoặc đẩy blocking work sang scheduler bounded thích hợp, tính cả queue wait và giới hạn tài nguyên. Không chuyển sang reactive chỉ để “mặc định nhanh hơn”.

### 7.1. Không phải lúc nào cũng nên chờ cả hai

**Mono.zip** thất bại nếu một nhánh lỗi (trừ khi xử lý lỗi có chủ đích), nên dependency nào có thể thiếu cần business contract riêng. Với trường tồn kho bắt buộc để chấp nhận đặt hàng, phải **fail safely** khi không chắc chắn. Với recommendation phụ trợ trên trang chi tiết đơn, có thể bỏ enrichment nếu chậm rồi trả representation tối giản **đúng schema**; đo tỷ lệ degraded responses, không trả dữ liệu giả thành số liệu chính thức.

## 8. Quan sát hiệu năng bằng Micrometer/Tracing

**Metrics** trả lời “bao nhiêu request chậm và chậm ở đâu theo phân vị”; **tracing** trả lời “request cụ thể mất thời gian ở chuỗi nào”; **profiling** giúp xác định CPU/allocations. Kết hợp cả ba, không đánh giá theo một trace đại diện.

### 8.1. Metric ở ranh giới HTTP

Spring Boot Actuator/Micrometer có thể thu thập request metrics/observations, với tên và labels phụ thuộc phiên bản/registry:

- **Route template** như **/api/orders/{id}**, không phải mỗi order ID làm label.
- **Method, status, outcome** và nhóm client/downstream được kiểm soát cardinality.
- **Histogram buckets** nếu muốn tính p95/p99 từ Prometheus; counters cho RPS/errors và gauges/timers cho pool/queue.
- **Payload size, DB count, GC và external HTTP duration** để phân biệt bottleneck.

Ví dụ truy vấn **PromQL minh họa** khi registry đã bật histogram tương ứng (tên labels cần đối chiếu môi trường thật):

~~~promql
histogram_quantile(
  0.95,
  sum by (le) (
    rate(http_server_requests_seconds_bucket{
      uri="/api/orders/{id}", method="GET"
    }[5m])
  )
)
~~~

Bucket histogram tính quantile **xấp xỉ** và có thể bị ảnh hưởng bởi boundaries/low samples. **Không lấy trung bình p95 giữa các instances**: gộp bucket counts trước rồi tính quantile. Tách GET với POST, successful với error flows nếu SLO định nghĩa như vậy; đừng làm chậm 5xx “biến mất” khỏi dashboard tổng mà không báo riêng.

### 8.2. Instrument một đoạn service có tên và low-cardinality tags

~~~java
import java.util.UUID;
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import org.springframework.stereotype.Service;

interface AuthorizedOrderRepository {
    OrderRecord findAuthorized(String actor, UUID id);
}

@Service
class ObservedOrderLookup {
    private final AuthorizedOrderRepository repository;
    private final ObservationRegistry registry;

    ObservedOrderLookup(AuthorizedOrderRepository repository,
                        ObservationRegistry registry) {
        this.repository = repository;
        this.registry = registry;
    }

    OrderRecord load(UUID id, String actor) {
        return Observation.createNotStarted("orders.lookup", registry)
                .lowCardinalityKeyValue("operation", "get-one")
                .observe(() -> repository.findAuthorized(actor, id));
    }
}
~~~

**Không đặt orderId, email, token hoặc userId thành low-cardinality metric tags** vì làm nổ số chuỗi thời gian, tốn tiền và có thể lộ dữ liệu. Với tracing, ID có thể nằm trong context đã kiểm soát retention/quyền truy cập nhưng vẫn cần tránh secrets/PII. Instrument từng dependency đúng điểm và tránh **double-count timing** do hai lớp auto/manual trùng nhau.

### 8.3. Tracing end-to-end và overhead

Với Micrometer Tracing/OpenTelemetry, cần propagation context qua HTTP clients, DB calls, async tasks và messaging theo khả năng framework. Mỗi span nên có tên ổn định như **orders.get**, **orders.db.read**, **inventory.get**, **pricing.get** và trạng thái lỗi; dùng route template thay URI có ID cụ thể. Bật sampling có ngân sách; **đừng gửi Authorization, request body nhạy cảm, SQL bind params hoặc cookie** vào span attributes. Instrumentation có overhead, nên thử nghiệm khi tăng tỷ lệ sampling.

Với Spring MVC, đo **response completion thực tế** nếu streaming/async: một timer kết thúc khi controller return có thể bỏ sót thời gian viết body ra socket. Hãy đối chiếu metrics server, proxy và client theo cùng request ID/trace.

## 9. Kiểm thử tải để xác nhận budget, không chỉ chạy một request nhanh

**Một lần curl 50 ms không chứng minh p95 300 ms khi hệ thống có 150 request đồng thời.** Kiểm thử tải cần xác định arrival rate, request mix, dữ liệu, điều kiện cache và downstream, thời gian warm-up và ngưỡng đánh giá trước khi chạy. Không kiểm thử đột ngột trên production khi chưa có quyền và kế hoạch kiểm soát tải.

### 9.1. Các loại thử nghiệm

| Bài thử | Mục tiêu | Dấu hiệu cần tìm |
| --- | --- | --- |
| **Baseline** (lưu lượng nhỏ) | Biết chi phí không tải. | DB, serialization, network base overhead. |
| **Steady load** ở mức dự báo | Kiểm SLO và độ ổn định. | p50/p95/p99, RPS, errors, pool wait. |
| **Step/ramp load** | Tìm điểm bão hòa. | Throughput không tăng nhưng p99/queue tăng. |
| **Spike** | Kiểm autoscale/load shedding và timeout. | 429/503, backlog, hồi phục sau spike. |
| **Soak** trong thời gian đủ dài | Tìm memory leak/GC/connection leak. | GC trend, pool exhausted, lag tích lũy. |
| **Fault injection** | Một dependency chậm, timeout, 429 hoặc mất kết nối. | Deadline/abort/retry/circuit breaker đúng, không cascading failure. |

**Giữ dữ liệu đại diện:** số lượng order trong DB, phân bố khách hàng/tenant, cache hit/miss, JSON payload, tỷ lệ GET/POST và số trang được phân trang. Một benchmark chỉ GET cùng một order đã nóng cache không thể đại diện cho truy vấn collection có filter phức tạp.

### 9.2. Ví dụ k6: constant arrival rate và threshold

Ví dụ chạy trong **môi trường staging được phép**, một script duy nhất chỉ đo GET order để phân tích tuyến này:

~~~javascript
import http from "k6/http";
import { check } from "k6";

export const options = {
  scenarios: {
    readOrders: {
      executor: "constant-arrival-rate",
      rate: 50,
      timeUnit: "1s",
      duration: "2m",
      preAllocatedVUs: 100,
      maxVUs: 200
    }
  },
  thresholds: {
    http_req_duration: ["p(95)<300", "p(99)<700"],
    http_req_failed: ["rate<0.005"]
  }
};

export default function () {
  const base = __ENV.BASE_URL;
  const id = __ENV.ORDER_ID;
  const token = __ENV.ACCESS_TOKEN;
  if (!base || !id || !token) {
    throw new Error("Missing test-only configuration");
  }
  const result = http.get(
    base + "/api/orders/" + encodeURIComponent(id),
    {
      headers: {
        Accept: "application/json",
        Authorization: "Bearer " + token
      },
      timeout: "1s",
      tags: { route: "GET /api/orders/{id}" }
    }
  );
  check(result, { "returns 200": r => r.status === 200 });
}
~~~

**Lưu ý đo:** k6 **http_req_duration** đo phần HTTP exchange theo định nghĩa công cụ (thường gửi/chờ/nhận, không bao gồm mọi giai đoạn DNS/connect/blocked), nên **khác SLI tại gateway**. Sử dụng script để làm performance regression ở phía load generator, sau đó đối chiếu gateway/client metrics để kết luận về SLO thật. Threshold trong ví dụ áp cho toàn bộ traffic của script; khi có nhiều routes, hãy phân nhóm tags và thresholds theo route/status thay vì gộp tất cả request.

**Kịch bản arrival rate** duy trì nỗ lực khởi tạo 50 iterations/s; nếu số VU không đủ, k6 ghi nhận **dropped_iterations**, cần báo cùng kết quả. Không giả rằng hệ thống xử lý đủ 50 req/s chỉ vì test cấu hình 50. Bắt buộc giám sát **achieved RPS, 4xx/5xx, duration, queue wait, database pool, downstream**, không chỉ nhìn ngưỡng p95.

Token chỉ dành cho môi trường thử nghiệm, có quyền đọc đúng dữ liệu fixture; không ghi vào báo cáo/CI logs. Chạy nhiều loại ID và dữ liệu để tránh cache 100% hit nếu workload thực tế có cả cache miss. Không để kiểm thử load tạo đơn thật hoặc phát webhook/email ra bên ngoài.

### 9.3. Ma trận kiểm thử critical path

| ID | Tiêm điều kiện | Điều cần khẳng định |
| --- | --- | --- |
| P01 | DB phản hồi chậm thêm 80 ms | Trace chỉ ra DB trên critical path; end-to-end tăng theo quan hệ có thể giải thích. |
| P02 | Inventory chậm 200 ms | Deadline/downstream timeout chặn request kéo dài; báo lỗi/fallback đúng contract. |
| P03 | Pricing và Inventory chạy đồng thời | Thời gian hai nhánh chồng lấp trong trace, nhưng concurrency có giới hạn. |
| P04 | DB pool hết connection | Thời gian acquisition hiển thị, app từ chối/timeout có kiểm soát thay vì queue vô hạn. |
| P05 | Broker/email/downstream phụ không cần thiết hỏng | Lệnh nghiệp vụ cốt lõi vẫn commit đúng nếu thiết kế outbox/async; lỗi phụ được theo dõi. |
| P06 | Request client hủy hoặc timeout | Công việc tiếp theo không bắt đầu không cần thiết; pool/threads được giải phóng theo khả năng. |
| P07 | Retryable 503 và Retry-After | Không retry vượt deadline; attempt/circuit breaker/retry budget có giới hạn. |
| P08 | POST có side effect đã commit rồi mất ACK | Không sinh hai đơn khi retry cùng idempotency key. |
| P09 | N+1 queries khi limit tăng từ 10 lên 100 | Query count/latency tăng được phát hiện; cải thiện bằng batch/DTO projection. |
| P10 | Endpoint chậm nhưng trả lỗi sớm cho 50% request | Dashboard không báo “nhanh hơn” chỉ vì lỗi được trả nhanh; theo dõi success/error separately. |
| P11 | Tenant dữ liệu lớn hoặc payload lớn | Giới hạn filter, paging, response size và quyền không bị bỏ để đạt ngưỡng. |

**Kiểm thử với DB/downstream thực hoặc fake có kiểm soát**, không chỉ mock trả kết quả tức thì. Một unit test dùng Thread.sleep để giả lập latency có ích kiểm logic deadline nhưng không mô phỏng connection acquisition, TLS, pooled connections hay GC. Dùng fault injection tại network/test server và test hệ thống dưới mức tải dự báo để thấy critical path thật.

## 10. Overload, retry và HTTP status: nhanh nhưng phải đúng

### 10.1. Deadline kết hợp load shedding

Nếu số request đến vượt khả năng xử lý, queue không giới hạn chỉ trì hoãn lỗi và có thể làm hết memory. Thiết kế cần có giới hạn:

1. **Ingress concurrency/rate limit**: theo tenant/API key/route hoặc identity với chính sách công bằng.
2. **DB/HTTP connection pools**: đặt max in-flight, acquisition timeout và quan sát pending queue.
3. **Bulkhead**: không để một downstream chậm chiếm mọi worker/connection của những endpoint khác.
4. **Deadline-aware fail fast**: từ chối sớm request không còn đủ thời gian để hoàn thành hợp lệ.
5. **Circuit breaker/health-based routing**: hạn chế khuếch đại sự cố, có probes và phục hồi có kiểm soát.

Lỗi overload có thể trả **429 Too Many Requests** khi quota/rate limit của caller bị vượt hoặc **503 Service Unavailable** khi service tạm quá tải. **Retry-After** có thể hướng dẫn client chờ, nhưng chỉ dùng khi có cơ sở để đưa ra đề xuất phù hợp:

~~~http
HTTP/1.1 429 Too Many Requests
Retry-After: 2
Content-Type: application/problem+json
Cache-Control: no-store

{
  "type": "https://api.example.com/problems/rate-limited",
  "title": "Rate limit exceeded",
  "status": 429
}
~~~

**Retry-After: 2** là số giây, không phải mili giây; header cũng có thể chứa HTTP-date. Client cần **exponential backoff + jitter**, số lần thử tối đa, **total deadline** và tôn trọng idempotency. Không retry 400/401/403/validation errors như lỗi tạm thời; 409/412 cần xử lý xung đột nghiệp vụ chứ không gửi lại mù quáng.

### 10.2. Tail latency bị khuếch đại bởi retry

Một request đã chậm 200 ms và bắt đầu retry dependency ở giây cuối cùng có thể phá deadline, tạo thêm tải lên chính service đang quá tải. **Retry không miễn phí**: nó tiêu capacity, connection, thread và có thể tạo **retry storm**. Cân nhắc chỉ retry GET hoặc thao tác ghi có idempotency được server hỗ trợ, ở lỗi có khả năng transient, khi remaining budget đủ. Hedged requests có thể giảm latency đuôi trong vài workload đọc, nhưng **tăng traffic** và đòi idempotency/resource limits; không dùng cho giao dịch side effect tùy tiện.

### 10.3. Fallback, cache và sự đúng đắn

Nếu response cần trạng thái tồn kho thời gian thực để chấp nhận thanh toán, trả **giá trị cache stale như sự thật mới nhất** có thể vi phạm nghiệp vụ. Nếu service enrichment không quan trọng, có thể trả phần dữ liệu cốt lõi và đánh dấu trường phụ không có sẵn theo **OpenAPI/schema đã thống nhất**. Không thêm fallback làm lộ dữ liệu tenant khác, bỏ validation hoặc sử dụng credential của caller để truy cập downstream sai audience. Tốc độ đạt SLO nhưng trả sai thông tin không phải thành công.

**HTTP cache/Redis** có thể làm giảm đường đọc DB, nhưng phải tôn trọng **ETag, Cache-Control, Vary, authorization scope, invalidation và freshness contract**. Chỉ so sánh cache-hit p95 với no-cache p95 mà không tính miss rate và biến động TTL sẽ cho kết luận sai.

### 10.4. Không chuyển mọi việc chậm thành 202 Accepted

**202 Accepted** hợp lý khi API thật sự nhận **operation bất đồng bộ** và công bố cách theo dõi:

~~~http
POST /api/exports HTTP/1.1
Content-Type: application/json
Authorization: Bearer <access-token>

{"status":"PAID"}

HTTP/1.1 202 Accepted
Location: /api/operations/op-42
Retry-After: 3
Content-Type: application/json

{"operationId":"op-42","status":"PENDING"}
~~~

Ví dụ đặt hai message HTTP liên tiếp để minh họa. Việc **enqueue job bền vững** là điều kiện trước khi trả 202; có API monitor, trạng thái FAILED/SUCCEEDED, retry và quyền truy cập riêng. Không trả 202 cho một cập nhật đã commit rồi viện cớ search index đang chậm; không chuyển job sang queue trong RAM rồi trả 202 như thể durable.

## 11. Quy trình điều tra khi p99 tăng đột biến

Đừng tối ưu “endpoint chậm” bằng cảm giác. Một quy trình ngắn nhưng có thể lặp lại:

1. **Khoanh đúng vấn đề:** GET hay POST? region/tenant, payload, cache hit/miss, status? Độ trễ p95/p99 của **successes và failures** đang thay đổi thế nào?
2. **Kiểm lượng tải và hàng đợi:** arrival/achieved RPS, concurrency, max threads, DB/HTTP connection pool pending, rejected tasks, GC pauses.
3. **Chọn trace chậm có dữ liệu đầy đủ:** xác định thời gian trước root service span (gateway), thời gian queue và **critical path thực tế** thay vì cộng child durations.
4. **Kiểm downstream:** latency tại service đích, timeout/retry attempts, connection reuse, saturation; đối chiếu trace IDs với logs đã redacted.
5. **Đặt giả thuyết có thể bác bỏ:** ví dụ “DB connection acquisition tăng từ 5 lên 120 ms”, hoặc “50 orders làm phát sinh 101 SQL calls”.
6. **Thay đổi một biến có kiểm soát:** tạo index, giảm query count, giới hạn fan-out, tăng pool nếu downstream đủ năng lực, sửa timeout hoặc tách bước phụ sang async.
7. **Chạy lại cùng workload và kiểm correctness:** p95/p99, error rate, achieved throughput, CPU/memory, tenant isolation, dữ liệu response, side effects.
8. **Ghi kết luận và rollback plan:** việc thay đổi pool/thread/cache có thể chuyển bottleneck sang hệ khác; luôn đo lại dưới traffic mix thực.

### 11.1. Một bảng phân tích ba request chậm

| Trace | Điểm nghẽn có bằng chứng | Hành động ưu tiên |
| --- | --- | --- |
| A | DB query 15 ms, nhưng đợi DB connection 180 ms. | Xác minh pool saturation/transaction dài, không vội tạo index. |
| B | DB 25 ms; Pricing 80 ms, Inventory 240 ms chạy song song. | Inventory nằm trên critical path; xem timeout, downstream capacity, fallback hợp lệ. |
| C | GET list có 1 + 100 queries, serialization 35 ms. | Loại N+1, batch/DTO projection, kiểm pagination. |

**Một “span dài nhất” không luôn là “mục tiêu tối ưu tốt nhất”**: nếu nó nằm trên nhánh không quyết định thời gian hoàn thành hoặc chỉ có 1% request gặp phải, lợi ích khác việc sửa một đoạn queue chung tác động 90% request. Ưu tiên theo **tần suất × tác động người dùng × độ an toàn × chi phí thực hiện**, không chỉ độ dài tuyệt đối.

## 12. Bài tập tình huống: chốt budget cho Orders API

**Đề bài.** API **GET /api/orders/{id}** có mục tiêu gateway p95 không quá **300 ms** và p99 không quá **700 ms** tại tải dự báo. Một trace minh họa cho thấy:

| Bước | Thời gian của trace mẫu |
| --- | ---: |
| Gateway + authentication | 20 ms |
| DB lấy order | 85 ms |
| Pricing gọi HTTP | 95 ms |
| Inventory gọi HTTP | 150 ms |
| DTO + serialization + response | 40 ms |

Hiện tại Pricing được gọi xong mới gọi Inventory. Đội phát triển muốn dùng 2 thread để chạy song song và tăng pool từ 20 lên 200; đội sản phẩm muốn bỏ Inventory khỏi response để GET nhanh hơn. Nhưng nếu thiếu tồn kho mà hệ thống hiển thị “còn hàng” giả, người dùng có thể đặt đơn sai.

**Hãy thực hiện:**

1. Tính critical path của trace khi hai downstream **tuần tự** và khi chạy **song song thực sự**, giả sử số đo từng nhánh không đổi.
2. Cho biết còn bao nhiêu slack trong budget 300 ms ở hai phương án, và vì sao phép tính này **không chứng minh p95**.
3. Nếu tối ưu DB từ 85 xuống 55 ms thì đường song song còn bao nhiêu ms? Inventory đôi khi mất 200 ms thì điều gì xảy ra?
4. Chọn dữ liệu cần thu thập trước khi tăng số thread/pool và thiết kế retry/deadline cho Inventory.
5. Quyết định nên late-load Inventory hay trả fallback như thế nào để **không phá nghiệp vụ**, và nêu ít nhất sáu test cần bổ sung.

### 12.1. Hướng giải có kiểm chứng

- **Tuần tự:** 20 + 85 + 95 + 150 + 40 = **390 ms**, vượt budget 90 ms.
- **Song song:** 20 + 85 + max(95,150) + 40 = **295 ms**, còn **5 ms slack**. Dù trace mẫu đạt, slack quá mỏng và các tail dependencies có thể đồng thời chậm; **không thể suy p95 từ phép cộng này**.
- **DB còn 55 ms:** 20 + 55 + 150 + 40 = **265 ms**, có **35 ms slack**. Nếu Inventory trong một trace khác mất 200 ms thì tổng thành **315 ms**; chưa kể queue/fan-out overhead.
- **Trước khi tăng pool:** đo queue wait, thread utilization, DB connection acquisition, downstream capacity, in-flight requests, memory và retry count. Tăng concurrency khi Inventory đã bão hòa có thể làm **p99 và error rate xấu đi**.
- **Timeout:** đặt limit Inventory nằm trong remaining deadline, reserve thời gian serialize/response, giới hạn retry và dùng bulkhead. Trả **503/contractual degradation** nếu Inventory bắt buộc nhưng không xác minh được; chỉ late-load nếu UI/REST schema phân biệt **“chưa biết”** với **“còn hàng”** và tác vụ đặt hàng cuối cùng vẫn kiểm tồn kho chính xác.
- **Test:** tuần tự/parallel trace overlap; Inventory delay/timeout; DB pool wait; k6 steady/spike; cache hit/miss; client cancel; fallback không giả dữ liệu; tenant authorization và lỗi 429/503 không retry storm.

**Bài tập mở rộng:** nếu p95 tăng mạnh vào tối thứ Sáu nhưng p50 không đổi, hãy xem time-series queue, downstream saturation, GC, số lượng order mỗi response và N+1 trước khi kết luận cần tăng CPU. Thiết kế một thí nghiệm A/B trên staging giữ nguyên request mix để phân biệt nguyên nhân.

## 13. Checklist áp dụng cho một REST endpoint

- [ ] Định nghĩa **SLI/SLO theo method + route template + nơi đo + cửa sổ + tải + payload**; có p95 và p99 khi phù hợp.
- [ ] Vẽ **critical-path DAG** với nhánh nối tiếp/song song, biết phần nào nằm ngoài request completion.
- [ ] Đặt budget cho gateway/auth, DB/pool, downstream, serialization và **slack**; không cộng p95 như các số đo của một request.
- [ ] Tính **deadline còn lại** và dùng connect/read/request/acquisition timeout, retry budget nhất quán.
- [ ] Có giới hạn **in-flight concurrency**, connection pools, queue depth và load shedding; không mở fan-out vô hạn.
- [ ] Dùng metrics histogram và tracing, phân biệt **self-time, waiting/queue time và overlapping child spans**.
- [ ] Khi collection chậm, kiểm **N+1, filter/index, limit, cursor pagination, response size**.
- [ ] Không tối ưu bằng cách bỏ **authentication, authorization, tenant checks, input validation, idempotency**.
- [ ] Khi fallback/cache, kiểm **freshness, quyền dữ liệu, schema và nghiệp vụ**; trả đúng 202/429/503 khi cần.
- [ ] Chạy baseline, steady, spike/soak và fault injection; báo cả achieved RPS, errors, p95/p99, dropped iterations.
- [ ] Test timeout/cancel/retry trên HTTP transport thật; không suy ra fail-safe từ unit test dùng mock tức thì.
- [ ] Sau khi đổi pool/DB/query/async, kiểm **độ đúng dữ liệu, side effects, availability và rollback plan**, không chỉ latency.

**Kết luận:** ngân sách độ trễ giúp biến mong muốn “API nhanh” thành **cam kết có cách đo và ranh giới rõ**. Critical path cho biết **chuỗi công việc đang quyết định thời gian trả response**; timeout/deadline và giới hạn concurrency ngăn một dependency chậm kéo sập toàn hệ thống. Tối ưu chỉ được coi là thành công khi **phân phối latency end-to-end, độ tin cậy và tính đúng đắn của REST contract** cùng được kiểm chứng bằng metrics, traces và kiểm thử tải.
