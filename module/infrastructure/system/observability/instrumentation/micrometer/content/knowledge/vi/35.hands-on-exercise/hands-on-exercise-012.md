# Hoàn thiện kiểm thử, ngân sách tài nguyên và danh mục phép đo của ứng dụng

Bài thực hành tổng hợp này hoàn thiện instrumentation cho một ứng dụng bán hàng Spring Boot. Bạn sẽ lập danh mục phép đo có owner và semantics rõ ràng, triển khai Counter, Gauge, Timer và DistributionSummary, nối Observation với tracing, viết test ở cả tầng registry lẫn scrape, rồi tính ngân sách cardinality và tài nguyên cho môi trường triển khai.

Mục tiêu là tạo ra một bộ metrics có thể vận hành lâu dài: số liệu có ý nghĩa, tag có giới hạn, output tương thích với backend, test bảo vệ contract và ngân sách đủ rõ để phát hiện khi instrumentation bắt đầu gây tải quá mức.

Phạm vi module OBSERVABILITY_INSTRUMENTATION_MICROMETER là: Sử dụng Micrometer để đo lường ứng dụng Java bằng counter, gauge, timer, distribution summary và nhãn có kiểm soát. Học tích hợp Spring Boot, xuất metrics đến hệ giám sát, kiểm soát cardinality, kiểm thử instrumentation và diễn giải số đo vận hành. Chương Thực hành tổng hợp kết nối các kỹ năng đó thành một ứng dụng có inventory, test suite và ngân sách tài nguyên được nghiệm thu.

## 1. Bối cảnh bài lab

Ứng dụng mẫu là shop-api, một Spring Boot service nhận đơn hàng, xử lý checkout, gọi payment provider và đưa công việc phụ vào queue. Ứng dụng chạy nhiều replica và được Prometheus scrape qua Spring Boot Actuator.

Các luồng nghiệp vụ chính:

1. API nhận yêu cầu tạo đơn.
2. Ứng dụng xác thực và ghi nhận đơn được tạo.
3. Checkout gọi inventory và payment.
4. Tác vụ receipt/email được đưa vào queue để worker xử lý.
5. Ứng dụng xuất metrics và trace để theo dõi độ tin cậy, latency, throughput và tình trạng quá tải.

Giả định triển khai cho bài lab:

| Thành phần | Giá trị mẫu |
| --- | --- |
| Framework | Spring Boot 3.x |
| Metrics facade | Micrometer |
| Metrics backend | Prometheus |
| Trace bridge | Brave hoặc OpenTelemetry, chọn một |
| Scrape interval | 15 giây |
| Số replica dự kiến | 10 |
| HTTP metrics | Actuator |
| Metric tags | Chỉ dùng tập giá trị hữu hạn |
| Queue | Một queue logic trong bài lab: checkout |

Phiên bản Spring Boot/Micrometer cụ thể phải được quản lý đồng bộ bằng dependency management của dự án. Package Prometheus registry và một số property export có thể khác giữa các dòng Micrometer; khi triển khai, hãy dùng đúng artifact và API của phiên bản đang chạy.

## 2. Kết quả cần hoàn thành

Sau bài lab, ứng dụng cần đáp ứng các kết quả sau:

- Có metric inventory ghi rõ tên, type, unit, tag, semantics, owner và consumer.
- Counter chỉ đếm sự kiện tích lũy; Gauge chỉ phản ánh trạng thái hiện tại; Timer đo thời lượng; DistributionSummary đo đại lượng số.
- Observation name và low-cardinality key-value được đặt ổn định.
- Không dùng trace ID, user ID, order ID hoặc URL động làm metric tag.
- Unit test xác minh logic ghi nhận trong registry.
- Export test xác minh tên, type, unit, labels và histogram sample.
- Integration test xác minh endpoint Actuator thực sự xuất metric.
- Có ngân sách series, scrape payload, scrape duration, CPU và memory.
- Có dashboard/alert query mẫu và checklist nghiệm thu.

## 3. Lập metric inventory trước khi viết code

Metric inventory là danh mục phép đo của service. Đây là nơi thống nhất metric dùng để trả lời câu hỏi vận hành nào, ai sở hữu và có giới hạn tài nguyên ra sao.

### 3.1. Danh mục phép đo đề xuất

| Metric name trong Micrometer | Type | Unit | Tags có giới hạn | Câu hỏi vận hành |
| --- | --- | --- | --- | --- |
| shop.orders.created | Counter | orders | channel: web/mobile | Tốc độ tạo đơn theo kênh? |
| shop.checkout.duration | Timer + histogram | seconds khi export Prometheus | operation: checkout; outcome: success/error | Checkout chậm hoặc lỗi ở mức nào? |
| shop.queue.depth | Gauge | tasks | queue: checkout | Queue checkout đang tích tụ? |
| shop.payload.size | DistributionSummary + histogram | bytes | route: create | Payload tạo đơn có tăng kích thước bất thường? |
| shop.worker.active | Gauge | workers | pool: checkout/notification | Bao nhiêu worker đang bận? |
| shop.worker.completed | FunctionCounter | tasks | pool: checkout/notification | Bao nhiêu task đã hoàn tất trong vòng đời process? |
| shop.payment.calls | Counter | calls | provider: provider-a/provider-b; outcome: success/error | Provider nào lỗi hoặc bị gọi nhiều? |

Không thêm tag vào inventory nếu chưa có câu hỏi vận hành cụ thể cần tag đó trả lời. Mỗi tag làm tăng số tổ hợp series. Nếu muốn điều tra theo một request riêng lẻ, hãy dùng trace/log correlation.

### 3.2. Ghi rõ contract cho từng metric

Mỗi dòng inventory nên có thêm các trường quản trị:

| Trường | Nội dung |
| --- | --- |
| Owner | Team chịu trách nhiệm về instrumentation và query. |
| Update point | Vị trí nghiệp vụ làm thay đổi meter. |
| Reset behavior | Counter reset theo process restart; Gauge phản ánh state hiện tại. |
| Label cardinality | Số giá trị tối đa của từng tag. |
| Histogram config | Bucket/SLO boundaries được export. |
| Dashboard | Panel sử dụng metric. |
| Alert | Rule phụ thuộc metric và điều kiện no-data. |
| Deprecation | Quy tắc thay đổi tên/tag/unit khi nâng cấp. |

Metric không có owner hoặc không có consumer thường khó duy trì. Trước khi thêm metric mới, xác định ai sẽ dùng và ai sẽ chịu trách nhiệm khi semantics thay đổi.

## 4. Thiết lập dependency và endpoint metrics

Với Maven, ứng dụng cần Actuator và Prometheus registry. Phiên bản cụ thể được quản lý qua Spring Boot BOM:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
<dependency>
    <groupId>io.micrometer</groupId>
    <artifactId>micrometer-registry-prometheus</artifactId>
</dependency>
```

Expose các endpoint cần dùng trong môi trường lab:

```yaml
spring:
  application:
    name: shop-api

management:
  endpoints:
    web:
      exposure:
        include: health,metrics,prometheus
  metrics:
    tags:
      application: shop-api
```

Trong production, chỉ expose endpoint phù hợp với chính sách mạng và bảo mật. Endpoint metrics thường nên được giới hạn ở mạng monitoring hoặc management interface.

## 5. Xây dựng instrumentation component

Đăng ký meter một lần trong constructor/bean và tái sử dụng. Không tạo meter theo request hoặc dùng ID động làm tag.

Ví dụ dưới đây minh họa một component tập trung quản lý các phép đo chính. Các enum giúp giới hạn tag value ngay tại API của instrumentation:

```java
public enum OrderChannel {
    WEB("web"),
    MOBILE("mobile");

    private final String tagValue;

    OrderChannel(String tagValue) {
        this.tagValue = tagValue;
    }

    public String tagValue() {
        return tagValue;
    }
}
```

Component metrics:

```java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.DistributionSummary;
import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import java.time.Duration;
import java.util.concurrent.BlockingQueue;
import java.util.function.Supplier;

public final class ShopMetrics {
    private final MeterRegistry registry;
    private final Counter webOrdersCreated;
    private final Counter mobileOrdersCreated;
    private final Timer checkoutSuccess;
    private final Timer checkoutError;
    private final DistributionSummary createPayloadBytes;
    private final BlockingQueue<?> checkoutQueue;

    public ShopMetrics(
            MeterRegistry registry,
            BlockingQueue<?> checkoutQueue) {
        this.registry = registry;
        this.checkoutQueue = checkoutQueue;

        this.webOrdersCreated = Counter.builder("shop.orders.created")
                .tag("channel", "web")
                .description("Orders created through web channel")
                .register(registry);

        this.mobileOrdersCreated = Counter.builder("shop.orders.created")
                .tag("channel", "mobile")
                .description("Orders created through mobile channel")
                .register(registry);

        this.checkoutSuccess = Timer.builder("shop.checkout.duration")
                .tag("operation", "checkout")
                .tag("outcome", "success")
                .serviceLevelObjectives(
                        Duration.ofMillis(50),
                        Duration.ofMillis(100),
                        Duration.ofMillis(300),
                        Duration.ofMillis(500),
                        Duration.ofSeconds(1))
                .register(registry);

        this.checkoutError = Timer.builder("shop.checkout.duration")
                .tag("operation", "checkout")
                .tag("outcome", "error")
                .serviceLevelObjectives(
                        Duration.ofMillis(50),
                        Duration.ofMillis(100),
                        Duration.ofMillis(300),
                        Duration.ofMillis(500),
                        Duration.ofSeconds(1))
                .register(registry);

        this.createPayloadBytes =
                DistributionSummary.builder("shop.payload.size")
                        .baseUnit("bytes")
                        .tag("route", "create")
                        .serviceLevelObjectives(1024, 4096, 8192, 65536)
                        .register(registry);

        Gauge.builder(
                        "shop.queue.depth",
                        checkoutQueue,
                        queue -> queue.size())
                .tag("queue", "checkout")
                .description("Tasks waiting in checkout queue")
                .register(registry);
    }

    public void orderCreated(OrderChannel channel) {
        switch (channel) {
            case WEB -> webOrdersCreated.increment();
            case MOBILE -> mobileOrdersCreated.increment();
        }
    }

    public <T> T measureCheckout(Supplier<T> action) {
        Timer.Sample sample = Timer.start(registry);
        String outcome = "success";

        try {
            return action.get();
        } catch (RuntimeException | Error error) {
            outcome = "error";
            throw error;
        } finally {
            sample.stop("success".equals(outcome)
                    ? checkoutSuccess
                    : checkoutError);
        }
    }

    public void recordCreatePayloadBytes(long bytes) {
        if (bytes < 0) {
            throw new IllegalArgumentException("bytes must be non-negative");
        }
        createPayloadBytes.record(bytes);
    }
}
```

Điểm cần lưu ý:

- Hai Counter dùng cùng tên nhưng có hai tag value cố định.
- Timer dùng hai outcome cố định; không lấy exception message làm tag.
- Gauge đọc queue thật. Component giữ strong reference đến queue và callback chỉ đọc size().
- DistributionSummary ghi byte, không ghi thời gian.
- Timer.Sample đo từ lúc bắt đầu đến lúc action kết thúc và ghi vào timer tương ứng.
- Nếu cần phân biệt validate/reserve/authorize, hãy tạo meter theo enum operation có tập giá trị cố định thay vì nhận chuỗi tự do.
- Ví dụ dùng switch expression của Java 17; với Java cũ hơn, thay bằng switch statement tương ứng.

Timer.start(registry) tạo sample theo clock của registry. Khi stop, sample ghi thời lượng vào Timer đích; cách này giữ unit conversion của Timer và tránh tự tính thời gian bằng phép trừ thủ công.

## 6. Mở rộng worker và payment metrics

Với ThreadPoolExecutor, có thể quan sát số worker đang hoạt động và số task hoàn tất từ chính executor. Giữ strong reference đến executor trong bean sở hữu pool:

```java
import io.micrometer.core.instrument.FunctionCounter;
import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.MeterRegistry;
import java.util.concurrent.ThreadPoolExecutor;

public final class WorkerPoolMetrics {
    private final ThreadPoolExecutor executor;

    public WorkerPoolMetrics(
            MeterRegistry registry,
            ThreadPoolExecutor executor,
            String poolName) {
        this.executor = executor;

        Gauge.builder(
                        "shop.worker.active",
                        executor,
                        ThreadPoolExecutor::getActiveCount)
                .tag("pool", poolName)
                .register(registry);

        FunctionCounter.builder(
                        "shop.worker.completed",
                        executor,
                        ThreadPoolExecutor::getCompletedTaskCount)
                .tag("pool", poolName)
                .register(registry);
    }
}
```

FunctionCounter đọc một giá trị tích lũy do executor quản lý; nó không tự tăng count. Nếu cần tách outcome success/error, hãy instrument wrapper task và tăng hai Counter có tag outcome hữu hạn tại điểm hoàn tất tương ứng.

Chỉ truyền poolName từ tập tên cấu hình cố định như checkout hoặc notification. Không lấy tên pool từ request hay dữ liệu người dùng.

Payment metrics nên giới hạn provider và outcome bằng enum hoặc các meter đăng ký trước. Không truyền provider name tự do từ request vào tag.

Ví dụ đăng ký trước bốn tổ hợp provider/outcome hợp lệ:

```java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;

public final class PaymentMetrics {
    private final Counter providerASuccess;
    private final Counter providerAError;
    private final Counter providerBSuccess;
    private final Counter providerBError;

    public PaymentMetrics(MeterRegistry registry) {
        this.providerASuccess = counter(registry, "provider-a", "success");
        this.providerAError = counter(registry, "provider-a", "error");
        this.providerBSuccess = counter(registry, "provider-b", "success");
        this.providerBError = counter(registry, "provider-b", "error");
    }

    private Counter counter(
            MeterRegistry registry, String provider, String outcome) {
        return Counter.builder("shop.payment.calls")
                .tag("provider", provider)
                .tag("outcome", outcome)
                .register(registry);
    }

    public void record(PaymentProvider provider, boolean success) {
        switch (provider) {
            case PROVIDER_A -> {
                if (success) providerASuccess.increment();
                else providerAError.increment();
            }
            case PROVIDER_B -> {
                if (success) providerBSuccess.increment();
                else providerBError.increment();
            }
        }
    }
}
```

Enum PaymentProvider trong ví dụ phải chỉ có PROVIDER_A và PROVIDER_B như phần chuẩn hóa tag ở trên. Nếu thêm provider mới, cập nhật inventory, ngân sách series và test cùng một thay đổi.

## 7. Đặt Observation quanh thao tác nghiệp vụ

Observation giúp một thao tác có thể được xử lý bởi nhiều handler, chẳng hạn metrics và tracing. Hãy dùng tên ổn định và low-cardinality key-value:

```java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;

public final class OrderService {
    private final ObservationRegistry observations;
    private final CheckoutProcessor checkoutProcessor;

    public OrderService(
            ObservationRegistry observations,
            CheckoutProcessor checkoutProcessor) {
        this.observations = observations;
        this.checkoutProcessor = checkoutProcessor;
    }

    public CheckoutResult checkout(Order order, OrderChannel channel) {
        return Observation.createNotStarted(
                        "shop.order.checkout", observations)
                .contextualName("checkout-order")
                .lowCardinalityKeyValue("channel", channel.tagValue())
                .observe(() -> checkoutProcessor.process(order));
    }
}
```

Không đồng thời ghi hai Timer cho cùng một khoảng thời gian mà không có mục đích rõ ràng. Nếu Observation handler đã tạo metric cho thao tác checkout, metric thủ công nên đo một boundary khác hoặc dùng để bổ sung chiều mà convention chung không cung cấp.

Trace ID, span ID và order ID không phải low-cardinality key-value. Nếu cần các ID này để điều tra, hãy dùng high-cardinality trace attribute theo chính sách tracing hoặc log correlation, không chuyển chúng thành metric label.

## 8. Tích hợp metrics vào luồng xử lý

Đặt lệnh ghi metric tại điểm sự kiện thực sự xảy ra:

| Điểm trong luồng | Metric | Khi cập nhật |
| --- | --- | --- |
| Đơn được tạo thành công | shop.orders.created | Sau khi nghiệp vụ xác nhận tạo đơn thành công. |
| Checkout hoàn tất | shop.checkout.duration | Bao quanh toàn bộ boundary checkout đã định nghĩa. |
| Task được đưa vào queue | shop.queue.depth | Gauge tự đọc queue; không increment thủ công song song nếu queue đã là nguồn state. |
| Payload được nhận | shop.payload.size | Ghi số byte sau khi xác định đúng kích thước payload. |
| Worker chạy task | shop.worker.active | Gauge đọc pool/executor state. |
| Worker hoàn tất | shop.worker.completed | FunctionCounter đọc completed task count hoặc Counter tăng một lần sau mỗi task. |
| Payment provider trả kết quả | shop.payment.calls | Counter tăng theo provider và outcome hữu hạn. |

Không đặt orderCreated() trước khi transaction commit nếu metric mang nghĩa “đơn đã tạo bền vững”. Nếu chỉ muốn đo số yêu cầu nhận vào, hãy dùng một metric khác như shop.orders.requests và mô tả semantics riêng.

## 9. Thiết kế tag có cardinality hữu hạn

Chuẩn hóa dữ liệu đầu vào trước khi gọi meter:

```java
public enum PaymentProvider {
    PROVIDER_A("provider-a"),
    PROVIDER_B("provider-b");

    private final String tagValue;

    PaymentProvider(String tagValue) {
        this.tagValue = tagValue;
    }

    public String tagValue() {
        return tagValue;
    }
}
```

Không viết:

```java
Counter.builder("shop.payment.calls")
        .tag("provider", request.providerName())
        .tag("order_id", order.id())
        .tag("trace_id", currentTraceId)
        .register(registry)
        .increment();
```

Đoạn code trên có thể tạo series mới cho từng provider string, order ID hoặc trace ID. Hãy chuyển provider về enum/allowlist và để trace/order ID trong log hoặc trace.

Với route HTTP, dùng URI template như /orders/{id} thay cho /orders/938271. Với outcome, dùng các giá trị success, error, rejected đã quy ước. Không dùng exception message hoặc response body làm tag.

## 10. Tính ngân sách series trước khi bật histogram

Cardinality là số tổ hợp label có thể xuất hiện. Với metric không phải histogram, số series xấp xỉ tích số cardinality của các tag. Với histogram Prometheus dạng classic, mỗi tổ hợp label tạo nhiều sample series: các bucket, _sum và _count.

Công thức lập ngân sách:

```text
Series per metric family
  = product(cardinality of each tag)

Histogram series per family
  ≈ label combinations × (emitted bucket count + 2)
```

Trong công thức histogram, emitted bucket count tính cả bucket +Inf; hai series bổ sung là _sum và _count. Tùy registry/version, Timer hoặc DistributionSummary còn có thể xuất sample phụ như _max hoặc _created. Bảng dưới đây là ước lượng core bucket/sum/count; hãy đếm toàn bộ sample trong scrape output thực tế để chốt ngân sách.

### 10.1. Ước lượng cho danh mục mẫu

Giả định cấu hình histogram có số bucket được export như bảng sau:

| Metric | Label combinations | Bucket count gồm +Inf | Ước lượng series |
| --- | ---: | ---: | ---: |
| shop.orders.created | 2 channel | — | 2 |
| shop.checkout.duration | 1 operation × 2 outcome = 2 | 6 (5 SLO boundaries + +Inf) | 2 × (6 + 2) = 16 |
| shop.queue.depth | 1 queue | — | 1 |
| shop.payload.size | 1 route | 5 (4 SLO boundaries + +Inf) | 1 × (5 + 2) = 7 |
| shop.worker.active | 2 pool | — | 2 |
| shop.worker.completed | 2 pool | — | 2 |
| shop.payment.calls | 2 provider × 2 outcome = 4 | — | 4 |
| **Tổng** | | | **34** |

Đây là ví dụ nhỏ để minh họa phép tính. Nếu thêm operation, outcome, region hoặc pool tag, hãy tính lại. Nếu bật percentile histogram tự động, số bucket phụ thuộc registry và cấu hình; không mặc định chỉ có các SLO boundary đã khai báo.

Với ứng dụng có nhiều route, instance và built-in metrics, series thực tế sẽ lớn hơn. Hãy lấy output scrape ở môi trường staging để đếm series thay vì dùng ước lượng trên làm số production cuối cùng.

### 10.2. Nhân với số replica và headroom

Nếu ước lượng 34 custom series mỗi replica và triển khai 10 replica:

```text
34 series/replica × 10 replicas = 340 custom series
```

Dành thêm headroom cho thay đổi có kiểm soát, ví dụ 25%:

```text
340 × 1.25 = 425 custom series budget
```

Headroom không phải lý do để thêm tag tùy ý. Nó là khoảng dự phòng cho thay đổi đã được review.

## 11. Đặt ngân sách tài nguyên mẫu

Ngân sách cần có số đo kiểm chứng và ngưỡng cảnh báo. Bảng dưới đây là mục tiêu tham khảo cho bài lab với 10 replica; hãy điều chỉnh theo backend, scrape interval, tải và giới hạn hạ tầng thực tế.

| Hạng mục | Ngân sách lab mẫu | Cách đo |
| --- | ---: | --- |
| Custom series | ≤ 50/replica | Đếm series từ scrape output theo metric inventory. |
| Built-in series | ≤ 250/replica | Đếm JVM, process, HTTP và executor metrics. |
| Tổng series | ≤ 300/replica | Tổng hợp toàn bộ exposition của một replica. |
| Tổng series cho 10 replica | ≤ 3.000 | Nhân series/replica với replica count. |
| Scrape interval | 15 giây | Cấu hình Prometheus target. |
| Scrape response size | ≤ 256 KiB/replica | Đo kích thước body exposition. |
| Scrape duration p95 | ≤ 100 ms | Theo dõi scrape duration hoặc đo integration/load test. |
| CPU overhead instrumentation | Mục tiêu ≤ 1% CPU của service ở tải chuẩn | So sánh cùng workload khi instrumentation bật/tắt. |
| Memory overhead instrumentation | Mục tiêu ≤ 32 MiB/replica | So sánh heap/RSS và số meter ở cùng workload. |

Các giá trị CPU/memory là mục tiêu lab, không phải cam kết chung của Micrometer. Hãy ghi lại baseline và phép đo thực tế. Nếu ngân sách không đạt, giảm meter/tag/bucket hoặc điều chỉnh scrape/export trước khi tăng giới hạn.

### 11.1. Ước lượng ingestion rate

Với 3.000 series tổng cộng và scrape mỗi 15 giây, tốc độ sample trung bình xấp xỉ:

```text
3.000 / 15 = 200 samples/second
```

Ước lượng này chưa tính scrape thất bại, jitter, recording rules hoặc các target khác. Nó giúp hình dung chi phí ingest nhưng không thay thế số liệu từ Prometheus.

Nếu mỗi replica trả về tối đa 256 KiB và có 10 replica, lượng exposition tối đa mỗi vòng scrape là khoảng 2,5 MiB. Với 15 giây một lần, băng thông trung bình khoảng 171 KiB/s trước overhead HTTP. Payload lớn bất thường thường là dấu hiệu tag cardinality hoặc histogram bucket tăng.

## 12. Xây dựng test ở nhiều tầng

Một test đọc counter.count() chỉ kiểm tra meter trong bộ nhớ. Bộ test hoàn chỉnh cần kiểm tra logic, export format, HTTP endpoint, cardinality và tài nguyên.

| Tầng | Công cụ | Điều cần chứng minh |
| --- | --- | --- |
| Unit | SimpleMeterRegistry | Counter, Timer, Gauge và Summary nhận đúng sự kiện. |
| Concurrency | ExecutorService, CountDownLatch | Ghi nhận đồng thời không mất cập nhật và Gauge về đúng trạng thái. |
| Registry export | Prometheus registry scrape() | Name, type, unit, tag và histogram được serialize đúng. |
| HTTP integration | @SpringBootTest, MockMvc/WebTestClient | Actuator endpoint expose đúng nội dung. |
| Cardinality | Registry meter IDs và scrape output | Tag value nằm trong allowlist, series không vượt budget. |
| Resource/load | Load test và scrape measurements | CPU, memory, scrape duration và payload nằm trong ngân sách. |

## 13. Unit test cho logic meter

Ví dụ kiểm tra Counter, Timer, Summary và Gauge bằng SimpleMeterRegistry:

```java
import static org.assertj.core.api.Assertions.assertThat;

import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import java.util.concurrent.LinkedBlockingQueue;
import org.junit.jupiter.api.Test;

class ShopMetricsTest {
    @Test
    void recordsOrdersCheckoutPayloadAndQueueDepth() {
        try (SimpleMeterRegistry registry = new SimpleMeterRegistry()) {
            var queue = new LinkedBlockingQueue<String>();
            ShopMetrics metrics = new ShopMetrics(registry, queue);

            metrics.orderCreated(OrderChannel.WEB);
            metrics.recordCreatePayloadBytes(4096);
            metrics.measureCheckout(() -> "accepted");
            queue.add("task-1");

            assertThat(registry.get("shop.orders.created")
                    .tag("channel", "web")
                    .counter().count()).isEqualTo(1.0);

            assertThat(registry.get("shop.checkout.duration")
                    .tag("operation", "checkout")
                    .tag("outcome", "success")
                    .timer().count()).isEqualTo(1);

            assertThat(registry.get("shop.payload.size")
                    .summary().count()).isEqualTo(1);

            assertThat(registry.get("shop.queue.depth")
                    .tag("queue", "checkout")
                    .gauge().value()).isEqualTo(1.0);
        }
    }
}
```

Test này xác minh đường ghi nhận trong registry. Nó chưa kiểm tra tên Prometheus, unit sau export, endpoint HTTP hoặc backend scrape.

Bổ sung test cho exception path để xác minh Timer outcome error tăng đúng một lần và exception vẫn được ném lại. Không bắt exception rồi âm thầm biến thao tác thất bại thành thành công chỉ để test xanh.

## 14. Test concurrency và trạng thái Gauge

Nếu nhiều worker cùng thay đổi queue hoặc active task, hãy dùng nguồn state an toàn luồng như BlockingQueue, AtomicInteger hoặc executor state được cung cấp bởi API thread-safe.

Bài lab cần xác minh:

- Counter count bằng số sự kiện thực tế sau khi mọi task hoàn tất.
- Timer count bằng số lần task được đo.
- Gauge queue depth phản ánh queue hiện tại.
- Gauge active worker trở về 0 sau khi task hoàn tất.
- Không có task bị bỏ lại khi test kết thúc.
- Executor được shutdown trong finally.

Dùng CountDownLatch hoặc Future.get() để chờ task hoàn tất. Không assert một giá trị Gauge giữa lúc worker còn cập nhật nếu test đang kỳ vọng một snapshot chính xác tại một thời điểm.

Ví dụ stress test nhỏ cho Counter và Gauge source:

```java
import static org.assertj.core.api.Assertions.assertThat;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;

class ConcurrentMeterTest {
    @Test
    void recordsConcurrentUpdatesAndRestoresActiveState() throws Exception {
        try (SimpleMeterRegistry registry = new SimpleMeterRegistry()) {
            Counter completed = registry.counter("test.tasks.completed");
            AtomicInteger active = new AtomicInteger();
            Gauge.builder("test.tasks.active", active, AtomicInteger::get)
                    .register(registry);

            int workers = 8;
            int incrementsPerWorker = 10_000;
            CountDownLatch ready = new CountDownLatch(workers);
            CountDownLatch start = new CountDownLatch(1);
            CountDownLatch done = new CountDownLatch(workers);
            ExecutorService pool = Executors.newFixedThreadPool(workers);

            try {
                for (int i = 0; i < workers; i++) {
                    pool.execute(() -> {
                        ready.countDown();
                        try {
                            start.await();
                            for (int j = 0; j < incrementsPerWorker; j++) {
                                active.incrementAndGet();
                                try {
                                    completed.increment();
                                } finally {
                                    active.decrementAndGet();
                                }
                            }
                        } catch (InterruptedException error) {
                            Thread.currentThread().interrupt();
                        } finally {
                            done.countDown();
                        }
                    });
                }

                assertThat(ready.await(5, TimeUnit.SECONDS)).isTrue();
                start.countDown();
                assertThat(done.await(10, TimeUnit.SECONDS)).isTrue();
                assertThat(completed.count()).isEqualTo(80_000.0);
                assertThat(registry.get("test.tasks.active")
                        .gauge().value()).isEqualTo(0.0);
            } finally {
                pool.shutdownNow();
                pool.awaitTermination(5, TimeUnit.SECONDS);
            }
        }
    }
}
```

Test này kiểm tra thao tác ghi meter được chia sẻ giữa các worker và source state dùng AtomicInteger. Trong test thực tế, hãy bảo đảm mọi worker đã hoàn tất trước khi assert; nếu timeout, báo test thất bại thay vì tiếp tục kiểm tra một snapshot chưa ổn định.

## 15. Export test với Prometheus registry

Dùng registry đúng backend để kiểm tra exposition. Với Micrometer Prometheus mới, package thường là io.micrometer.prometheusmetrics; một số phiên bản cũ dùng package khác.

```java
import static org.assertj.core.api.Assertions.assertThat;

import io.micrometer.core.instrument.Counter;
import io.micrometer.prometheusmetrics.PrometheusConfig;
import io.micrometer.prometheusmetrics.PrometheusMeterRegistry;
import org.junit.jupiter.api.Test;

class ShopPrometheusExportTest {
    @Test
    void exportsCounterNameTypeAndLabels() {
        try (PrometheusMeterRegistry registry =
                     new PrometheusMeterRegistry(PrometheusConfig.DEFAULT)) {
            Counter.builder("shop.orders.created")
                    .tag("channel", "web")
                    .register(registry)
                    .increment(2.0);

            String exposition = registry.scrape();

            assertThat(exposition)
                    .contains("# TYPE shop_orders_created_total counter")
                    .contains("channel=\"web\"");
        }
    }
}
```

Đừng snapshot toàn bộ exposition nếu thứ tự sample hoặc HELP text không phải hợp đồng. Assert các phần quan trọng: tên đã chuẩn hóa, type, tag và sample value.

Với Timer histogram, kiểm tra _count, _sum, bucket cần cho SLO và unit seconds. Với DistributionSummary, xác minh unit là bytes theo convention đã chọn.

Các bucket SLO trong ví dụ được chọn để kiểm tra ngưỡng vận hành với ngân sách có thể tính trước. P95 từ số bucket ít sẽ là ước lượng thô; nếu dashboard cần percentile chính xác hơn, bật percentile histogram, đếm số bucket thực tế từ exposition và cập nhật lại series budget.

## 16. Integration test cho Actuator endpoint

Một integration test cần chứng minh metric được đăng ký vào registry mà Spring Boot export:

```java
import static org.hamcrest.Matchers.containsString;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import io.micrometer.core.instrument.MeterRegistry;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest(properties = {
    "management.endpoints.web.exposure.include=health,metrics,prometheus"
})
@AutoConfigureMockMvc
class MetricsEndpointTest {
    @Autowired
    MockMvc mockMvc;

    @Autowired
    MeterRegistry registry;

    @Test
    void exposesApplicationMetric() throws Exception {
        registry.counter("test.shop.visible").increment();

        mockMvc.perform(get("/actuator/prometheus"))
                .andExpect(status().isOk())
                .andExpect(content().string(
                        containsString("test_shop_visible_total")));
    }
}
```

Các static import và dependency test của Spring cần được thêm theo stack đang dùng. Nếu ứng dụng bật security, cấu hình authentication/authorization trong test. Nếu management server dùng port hoặc base path riêng, kiểm tra đúng endpoint triển khai.

HTTP 200 chưa đủ; body phải có metric mong đợi. Ngược lại, metric trong SimpleMeterRegistry không chứng minh Prometheus registry production có nhận dữ liệu.

## 17. Test cardinality và tag policy

Kiểm thử input được chuẩn hóa trước khi trở thành tag. Ví dụ, provider không nằm trong enum/allowlist phải được quy về other hoặc bị từ chối ở tầng validation; không đăng ký một meter mới cho mỗi chuỗi tự do.

Bộ test nên tạo nhiều request với order ID khác nhau nhưng xác minh:

- Không có tag order_id.
- Không có trace_id hoặc span_id trong meter ID.
- Route được chuẩn hóa thành URI template.
- Provider/outcome chỉ có các value đã định nghĩa.
- Tổng meter/series không vượt ngân sách mẫu.
- MeterFilter giới hạn cardinality không âm thầm làm mất metric quan trọng.

Nếu dùng maximumAllowableTags, hãy test cả trường hợp trong giới hạn và vượt giới hạn. Ghi nhận rõ meter nào bị deny và có cảnh báo vận hành phù hợp.

## 18. Dashboard và alert tối thiểu

Metric inventory chỉ hữu ích khi có query trả lời câu hỏi vận hành.

### 18.1. Tốc độ tạo đơn

```promql
sum by (channel) (
  rate(shop_orders_created_total[5m])
)
```

### 18.2. P95 checkout latency

```promql
histogram_quantile(
  0.95,
  sum by (le) (
    rate(shop_checkout_duration_seconds_bucket[5m])
  )
)
```

### 18.3. Queue đang tích tụ

```promql
max by (queue) (shop_queue_depth)
```

### 18.4. Payment error ratio

```promql
sum(rate(shop_payment_calls_total{outcome="error"}[5m]))
/
sum(rate(shop_payment_calls_total[5m]))
```

Query này đo tỷ lệ payment call lỗi theo provider đã được đăng ký. Trong production, hãy xác định hành vi no-traffic/no-data cho ratio và tạo alert riêng nếu service không scrape được. Không dùng phép chia với denominator bị ép thành hằng số để che tình trạng không có dữ liệu.

Dashboard nên hiển thị unit đúng, legend theo tag hữu ích và không tạo một panel cho từng ID động. Alert nên có for duration, severity, runbook và label grouping ổn định.

## 19. Đo ngân sách trong staging

Chạy cùng một workload với hai cấu hình: instrumentation bật đầy đủ và cấu hình baseline tối thiểu. Giữ nguyên số request, payload, concurrency, JVM flags và thời gian chạy để so sánh công bằng.

Thu thập:

- CPU usage và process CPU time.
- Heap/RSS và GC activity.
- Số meter/series theo registry.
- Kích thước body /actuator/prometheus.
- Scrape duration.
- Request latency p50/p95/p99.
- Exporter/Collector queue hoặc lỗi gửi nếu dùng push.
- Số tag value thực tế theo inventory.

So sánh chênh lệch giữa hai lần chạy. Nếu instrumentation làm tăng CPU hoặc memory vượt budget, kiểm tra số meter, histogram, tag cardinality và callback Gauge trước khi tăng tài nguyên service.

Không benchmark chỉ một lần. Chạy đủ thời gian để warm-up JVM và quan sát steady state. Dùng cùng tải và lặp lại để giảm nhiễu.

## 20. Troubleshooting khi vượt ngân sách

| Triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| Series tăng nhanh sau deploy | Tag động hoặc route không chuẩn hóa | Dùng enum/allowlist và URI template. |
| Scrape body quá lớn | Histogram quá nhiều bucket hoặc nhiều tổ hợp tag | Giảm tag, giới hạn bucket và chỉ bật histogram cho metric cần quantile. |
| Scrape duration tăng | Nhiều meter hoặc callback Gauge chậm | Đếm series, làm callback chỉ đọc state trong memory. |
| CPU tăng | Ghi quá nhiều meter, nhiều tag combination hoặc instrumentation lặp | Đo overhead, bỏ phép đo trùng và giảm cardinality. |
| Heap tăng | Quá nhiều meter identity và object tag | Xác định meter name/tag tạo ra series mới; không tạo meter theo request. |
| Dashboard p95 sai | Unit hoặc bucket config thay đổi | Kiểm tra exposition và SLO boundaries. |
| Queue Gauge âm hoặc không khớp | Source state cập nhật sai hoặc đo trùng | Dùng queue/executor làm nguồn sự thật; kiểm tra enqueue/dequeue path. |
| Alert ratio NaN/no data | Không có denominator hoặc thiếu series | Định nghĩa no-traffic behavior và alert absent riêng. |

## 21. Bàn giao metric inventory

Kết thúc bài lab bằng một file inventory do team duy trì. Mỗi metric phải có:

- Tên Micrometer và tên export dự kiến.
- Type, unit và semantics.
- Tag keys cùng tập value tối đa.
- Histogram/SLO configuration nếu có.
- Owner và service.
- Code update point.
- Dashboard panel, PromQL query và alert rule.
- Series budget theo replica và toàn cluster.
- Ngày thêm, thay đổi hoặc deprecate.

Khi đổi metric name, type, unit, tag hoặc semantics, cập nhật inventory và kiểm thử exposition trước khi deploy. Nếu là breaking change, dùng dual-publish trong thời gian chuyển tiếp, chuyển dashboard/alert rồi mới ngừng metric cũ.

## 22. Tiêu chí nghiệm thu

Bài lab được xem là hoàn tất khi tất cả điều kiện sau đạt:

- [ ] Metric inventory bao phủ các luồng order, checkout, queue, worker và payment.
- [ ] Mỗi metric có owner, type, unit, semantics và update point.
- [ ] Tag values được giới hạn bằng enum/allowlist hoặc normalization.
- [ ] Không có trace ID, span ID, user ID hoặc order ID trong metric labels.
- [ ] Counter, Gauge, Timer và DistributionSummary được dùng đúng semantics.
- [ ] Gauge source sống đủ lâu và an toàn khi đọc đồng thời.
- [ ] Observation có tên ổn định và low-cardinality key-value.
- [ ] Unit test kiểm tra giá trị meter và cả success/error path.
- [ ] Concurrency test xác minh cập nhật và trạng thái sau khi hoàn tất.
- [ ] Prometheus scrape test xác minh name/type/unit/labels/histogram.
- [ ] Actuator integration test xác minh endpoint và response body.
- [ ] Cardinality estimate có tính replica multiplier và histogram series.
- [ ] Scrape payload/duration, CPU và memory được đo so với budget.
- [ ] Dashboard query và alert rule có test hoặc bước xác minh.
- [ ] Có owner, deprecation policy và quy trình migration metric.

## 23. Kết quả cần bàn giao

Sau khi hoàn tất, nhóm phát triển nên có bốn đầu ra:

1. **Metric inventory:** danh mục phép đo có contract và owner.
2. **Instrumentation code:** component đo lường, Observation convention và cấu hình registry.
3. **Test suite:** unit, concurrency, exposition, Actuator và cardinality/resource checks.
4. **Operations note:** ngân sách series/tài nguyên, dashboard query, alert, runbook và chính sách nâng cấp metric.

Bài thực hành tổng hợp kết nối instrumentation với chất lượng vận hành. Một metric chỉ hữu ích khi có semantics rõ, tag có giới hạn, output đúng contract và ngân sách tài nguyên được đo. Hoàn thiện inventory trước, kiểm thử từ registry đến scrape/export, rồi xác minh cardinality, CPU, memory và dashboard/alert dưới tải thực tế. Khi những điều kiện đó được ghi lại và có owner, bộ phép đo Micrometer có thể tiếp tục phát triển mà vẫn kiểm soát được chi phí và giữ được niềm tin vào số liệu vận hành.
