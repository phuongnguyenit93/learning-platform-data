# Theo dõi tỷ lệ lỗi, lời gọi chậm và thời gian thực thi

Circuit breaker chỉ giúp bảo vệ hệ thống khi nhóm vận hành quan sát được nó đang ở trạng thái nào, dependency trả kết quả ra sao và lời gọi mất bao lâu. Với Spring Cloud CircuitBreaker dùng Resilience4j, có thể xuất số liệu qua Micrometer, Spring Boot Actuator và hệ thống thu thập như Prometheus. Các số liệu quan trọng gồm failure rate, slow-call rate, số lời gọi thành công/thất bại/bị từ chối và thời gian thực thi của lời gọi được bảo vệ.

Khi theo dõi, cần tách ba góc nhìn: **sức khỏe của dependency**, **hành vi của circuit breaker** và **trải nghiệm của request nghiệp vụ**. Failure rate của circuit breaker không nhất thiết bằng tỷ lệ HTTP 5xx của toàn ứng dụng; timer của supplier cũng không nhất thiết bao gồm thời gian fallback hoặc xử lý ở controller. Đo đúng ranh giới giúp dashboard phản ánh nguyên nhân thay vì chỉ cho thấy một con số tổng hợp.

## 1. Những câu hỏi cần trả lời khi quan sát

Một dashboard circuit breaker nên giúp trả lời:

- Breaker theo từng dependency đang ở `CLOSED`, `OPEN`, `HALF_OPEN` hay trạng thái đặc biệt?
- Bao nhiêu lời gọi đã thực sự chạy và bao nhiêu lời gọi bị từ chối trước khi chạm dependency?
- Failure rate và slow-call rate trong sliding window hiện tại là bao nhiêu?
- Thời gian thực thi của các lời gọi thành công và thất bại đang tăng hay giảm?
- Fallback có được sử dụng thường xuyên không, và fallback có hoàn tất thành công không?
- Request nghiệp vụ có đang chậm hoặc trả lỗi cho người dùng dù circuit breaker đã chặn dependency?

Không nên chỉ hiển thị trạng thái `OPEN`. Trạng thái cho biết breaker đang chặn lời gọi; tỷ lệ lỗi, độ trễ và số lần bị từ chối giúp giải thích vì sao nó mở và mức độ ảnh hưởng tới luồng nghiệp vụ.

## 2. Phân biệt các chỉ số chính

| Chỉ số | Ý nghĩa | Cách đọc |
| --- | --- | --- |
| `failureRate` | Tỷ lệ lời gọi được ghi nhận là thất bại trong sliding window | Tăng khi dependency trả exception được cấu hình ghi nhận |
| `slowCallRate` | Tỷ lệ lời gọi vượt `slowCallDurationThreshold` trong sliding window | Có thể tăng dù lời gọi cuối cùng vẫn thành công |
| `numberOfSuccessfulCalls` | Số lời gọi được ghi nhận thành công | Cho biết số mẫu thành công trong cửa sổ |
| `numberOfFailedCalls` | Số lời gọi được ghi nhận thất bại | Không bao gồm exception bị ignore theo cấu hình |
| `numberOfBufferedCalls` | Tổng số kết quả được lưu trong cửa sổ | Dùng để biết đã có đủ mẫu so với `minimumNumberOfCalls` chưa |
| `numberOfNotPermittedCalls` | Số lời gọi bị breaker từ chối | Cho biết lượng request bị chặn khi breaker không cho phép |
| `state` | Trạng thái hiện tại của breaker | Đối chiếu với tỷ lệ và số lần từ chối |
| Call duration | Thời gian thực thi của lời gọi được bảo vệ | Phân tích độ trễ trung bình, p95/p99 nếu đã bật histogram |

Failure rate thường được hiểu theo công thức:

\[
\text{failureRate} = \frac{\text{failed calls}}{\text{successful calls} + \text{failed calls}} \times 100\%
\]

Các exception được cấu hình ignore không được tính là thành công hay thất bại. Lời gọi bị từ chối khi breaker `OPEN` cũng không phải một lần gọi dependency thất bại vì supplier không chạy. Vì vậy, không cộng `not permitted` vào mẫu số của failure rate.

`slowCallRate` được tính riêng:

\[
\text{slowCallRate} = \frac{\text{slow calls}}{\text{successful calls} + \text{failed calls}} \times 100\%
\]

Một lời gọi có thể vừa chậm vừa thất bại. Khi đó nó góp phần vào cả hai thống kê; không cộng hai tỷ lệ với nhau. Các tỷ lệ được dùng để ra quyết định chỉ khi đã đạt `minimumNumberOfCalls`.

Trước khi có đủ số mẫu tối thiểu, Resilience4j có thể trả tỷ lệ là `-1` để biểu thị chưa có đủ dữ liệu đánh giá. Dashboard nên hiển thị trạng thái “chưa đủ mẫu” thay vì diễn giải `-1` thành tỷ lệ lỗi âm hoặc thay bằng `0%`.

## 3. Bật Micrometer và Spring Boot Actuator

Với Spring Boot, thêm Actuator, module Micrometer của Resilience4j và registry cho hệ thống giám sát. Ví dụ Maven:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>
    <dependency>
        <groupId>io.github.resilience4j</groupId>
        <artifactId>resilience4j-micrometer</artifactId>
    </dependency>
    <dependency>
        <groupId>io.micrometer</groupId>
        <artifactId>micrometer-registry-prometheus</artifactId>
    </dependency>
</dependencies>
```

Quản lý phiên bản Spring Boot, Spring Cloud và Resilience4j bằng BOM hoặc dependency management tương thích với dự án. Không tự ghép các phiên bản khác release train chỉ để lấy một phiên bản Micrometer mới hơn.

Resilience4j tích hợp với Micrometer để đăng ký các meter cho circuit breaker. Với Spring Boot integration, cấu hình backend và registry theo ID instance. Ví dụ:

```yaml
spring:
  application:
    name: order-service

resilience4j:
  circuitbreaker:
    instances:
      inventory:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        slowCallDurationThreshold: 800ms
        slowCallRateThreshold: 60
        waitDurationInOpenState: 15s
        permittedNumberOfCallsInHalfOpenState: 3

management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus
  endpoint:
    health:
      show-details: when_authorized
  metrics:
    tags:
      application: ${spring.application.name}
    distribution:
      percentiles-histogram:
        resilience4j.circuitbreaker.calls: true
```

`resilience4j.circuitbreaker.instances.inventory` định nghĩa breaker được theo dõi. `management.metrics.tags.application` thêm nhãn ứng dụng để phân biệt instance trong hệ thống giám sát. Histogram cho timer giúp hệ thống thu thập phân phối thời gian thay vì chỉ có tổng và số lượng; cần kiểm tra cấu hình phân phối của Micrometer và backend để bảo đảm các bucket được xuất ra.

Sau khi ứng dụng khởi động, có thể kiểm tra các meter bằng endpoint Actuator `GET /actuator/metrics` và xem một meter cụ thể bằng `GET /actuator/metrics/{metric-name}`. Prometheus scrape endpoint `/actuator/prometheus` khi registry tương ứng đã được thêm. Tên meter và tag cụ thể phụ thuộc phiên bản Micrometer/Resilience4j; dùng danh sách meter thực tế của ứng dụng làm nguồn đối chiếu khi viết dashboard.

## 4. Các meter Resilience4j cần quan sát

Với Micrometer integration, các meter circuit breaker thường có dạng:

| Meter | Loại | Mục đích |
| --- | --- | --- |
| `resilience4j.circuitbreaker.calls` | Timer | Đếm lời gọi theo loại kết quả và ghi nhận thời gian thực thi |
| `resilience4j.circuitbreaker.state` | Gauge | Biểu diễn trạng thái hiện tại theo tag state |
| `resilience4j.circuitbreaker.failure.rate` | Gauge | Tỷ lệ lỗi hiện tại trong cửa sổ |
| `resilience4j.circuitbreaker.slow.call.rate` | Gauge | Tỷ lệ lời gọi chậm hiện tại trong cửa sổ |
| `resilience4j.circuitbreaker.buffered.calls` | Gauge | Số mẫu hiện có trong cửa sổ |
| `resilience4j.circuitbreaker.slow.calls` | Gauge | Số lời gọi chậm theo nhóm kết quả |

Timer `resilience4j.circuitbreaker.calls` thường có tag `name` để nhận diện breaker và tag `kind` để phân biệt `successful`, `failed` hoặc `not_permitted`. Các meter gauge có tag `name`; meter trạng thái có tag biểu diễn trạng thái. Tên metric được chuyển đổi theo quy tắc của registry, ví dụ dấu chấm có thể thành dấu gạch dưới trong Prometheus.

Hãy kiểm tra tag có thực sự được xuất ra ở phiên bản đang dùng. Không hardcode một giả định về tên metric đã chuyển đổi nếu ứng dụng có custom naming convention hoặc registry khác.

## 5. Đo thời gian thực thi và phân vị độ trễ

Timer của circuit breaker giúp phân tích thời gian thực thi ở ranh giới lời gọi được bảo vệ. Tổng thời gian chia cho số mẫu cho biết độ trễ trung bình, nhưng trung bình có thể che khuất một nhóm request rất chậm. Khi đã bật histogram, nên theo dõi thêm p50, p95 và p99.

Ví dụ diễn giải:

| Quan sát | Ý nghĩa có thể có |
| --- | --- |
| p50 ổn định, p95 tăng mạnh | Một phần request gặp tail latency, có thể do pool, mạng hoặc dependency quá tải |
| p50 và p95 cùng tăng | Phần lớn lời gọi đều chậm; dependency có thể đang suy giảm diện rộng |
| p95 tăng nhưng failure rate chưa tăng | Dependency vẫn trả kết quả nhưng chậm; slow-call rate có thể mở breaker trước khi lỗi xuất hiện |
| Thời gian supplier thấp nhưng request HTTP cao | Thời gian nằm ngoài supplier, ví dụ queue, fallback, serialize hoặc xử lý ứng dụng |

Timer của circuit breaker thường đo phần thực thi được bọc. Nếu fallback chạy sau khi supplier ném lỗi hoặc breaker từ chối, thời gian fallback không nên được hiểu là thời gian dependency phản hồi. Để đo trải nghiệm đầu-cuối, dùng thêm metric request ở tầng web như `http.server.requests` hoặc metric nghiệp vụ riêng.

## 6. Ví dụ truy vấn Prometheus

Micrometer Timer thường được xuất thành các chuỗi như `resilience4j_circuitbreaker_calls_seconds_count`, `_sum` và `_bucket`. Tên chính xác cần được xác minh tại `/actuator/prometheus`.

Tỷ lệ lỗi của lời gọi đã thực thi trong năm phút gần nhất có thể được tính theo số lời gọi thất bại chia cho tổng lời gọi thành công và thất bại:

```promql
sum by (name) (
  rate(resilience4j_circuitbreaker_calls_seconds_count{kind="failed"}[5m])
)
/
sum by (name) (
  rate(resilience4j_circuitbreaker_calls_seconds_count{kind=~"successful|failed"}[5m])
)
```

Truy vấn trên là tỷ lệ theo lưu lượng trong khoảng năm phút. Nó không nhất thiết trùng với `failureRate` mà breaker dùng để ra quyết định vì breaker tính trên sliding window có kích thước và kiểu thời gian riêng. Khi lưu lượng bằng 0, phép chia có thể không có mẫu hoặc tạo giá trị không xác định; dashboard nên xử lý trường hợp không có request.

Độ trễ trung bình của các lời gọi thành công và thất bại:

```promql
sum by (name) (
  rate(resilience4j_circuitbreaker_calls_seconds_sum{kind=~"successful|failed"}[5m])
)
/
sum by (name) (
  rate(resilience4j_circuitbreaker_calls_seconds_count{kind=~"successful|failed"}[5m])
)
```

Nếu histogram được bật và bucket được xuất, p95 có thể được tính như sau:

```promql
histogram_quantile(
  0.95,
  sum by (le, name) (
    rate(resilience4j_circuitbreaker_calls_seconds_bucket{kind=~"successful|failed"}[5m])
  )
)
```

Không lấy `not_permitted` làm mẫu đo độ trễ của dependency vì supplier không chạy trong trường hợp đó. Có thể tạo một biểu đồ riêng cho số lần bị từ chối bằng cách đếm hoặc lấy rate của meter có `kind="not_permitted"`, sau khi xác minh metric được xuất như thế nào trong phiên bản đang dùng.

## 7. Phân biệt metric dependency, fallback và request đầu-cuối

Một request nghiệp vụ có thể đi qua nhiều bước: controller, validation, circuit breaker, client, fallback, mapping response và serialization. Một metric duy nhất không thể giải thích tất cả.

Nên có ít nhất ba nhóm số liệu:

| Nhóm | Đo ở đâu | Câu hỏi được trả lời |
| --- | --- | --- |
| Circuit breaker/dependency | Supplier được bọc bởi breaker | Dependency phản hồi thành công, thất bại hay chậm? Breaker có đang chặn request? |
| Fallback | Hàm fallback hoặc lớp xử lý dự phòng | Có bao nhiêu request dùng fallback? Fallback có hoàn tất thành công không? |
| Request nghiệp vụ | Web server hoặc tầng API | Người dùng chờ bao lâu và nhận bao nhiêu response lỗi? |

Ví dụ, breaker đang `OPEN` có thể khiến failure rate của dependency không tăng thêm vì supplier không chạy, trong khi số lần `not_permitted` tăng. Nếu fallback trả dữ liệu cache nhanh, request đầu-cuối vẫn có thể thành công. Dashboard nên thể hiện cả ba sự kiện: dependency trước đó suy giảm, breaker đang chặn và ứng dụng đang phục vụ qua fallback.

Có thể dùng Micrometer `Counter` riêng để ghi nhận fallback. Ví dụ:

```java
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.stereotype.Component;

@Component
public class FallbackMetrics {

    private final MeterRegistry meterRegistry;

    public FallbackMetrics(MeterRegistry meterRegistry) {
        this.meterRegistry = meterRegistry;
    }

    public void recordInventoryFallback(String reason) {
        meterRegistry.counter(
            "application.fallback.calls",
            "dependency", "inventory",
            "reason", reason
        ).increment();
    }
}
```

Chỉ dùng các giá trị tag có tập hữu hạn như `open`, `timeout`, `dependency_error`. Không đưa user ID, order ID, URL đầy đủ hoặc exception message làm tag vì mỗi giá trị mới có thể tạo một time series riêng và làm tăng cardinality. Thông tin chi tiết nên nằm trong log có cấu trúc và trace, không nằm trong label metric.

## 8. Ghi nhận state transition và sự kiện

Metric thể hiện xu hướng; event giải thích một lần chuyển trạng thái cụ thể. Resilience4j cung cấp event publisher cho từng circuit breaker:

```java
import io.github.resilience4j.circuitbreaker.CircuitBreaker;
import io.github.resilience4j.circuitbreaker.CircuitBreakerRegistry;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

@Component
public class InventoryCircuitBreakerEvents {

    private static final Logger log =
        LoggerFactory.getLogger(InventoryCircuitBreakerEvents.class);

    public InventoryCircuitBreakerEvents(CircuitBreakerRegistry registry) {
        CircuitBreaker breaker = registry.circuitBreaker("inventory");

        breaker.getEventPublisher()
            .onStateTransition(event ->
                log.info("inventory circuit breaker state transition: {}", event))
            .onCallNotPermitted(event ->
                log.warn("inventory call not permitted: {}", event))
            .onError(event ->
                log.warn("inventory call failed: {}", event));
    }
}
```

Đăng ký listener một lần trong vòng đời ứng dụng, không đăng ký ở mỗi request. Nếu instance được tạo bởi một Spring Cloud factory riêng, xác minh registry ở ví dụ có quản lý đúng breaker đang được gọi; không tạo registry độc lập rồi tưởng rằng event phản ánh trạng thái của factory. Có thể dùng customizer hoặc cơ chế tích hợp của phiên bản Spring Cloud CircuitBreaker để gắn listener vào backend instance.

Log state transition nên có breaker ID, trạng thái trước/sau và timestamp. Khi có thể, gắn trace ID hoặc correlation ID ở log request thay vì biến các ID đó thành tag metric. Event listener không nên ghi payload nhạy cảm hoặc exception message chứa dữ liệu cá nhân.

## 9. Dashboard nên tổ chức theo dependency

Một dashboard thực dụng có thể chia thành các hàng:

1. **Trạng thái:** state hiện tại, số lần chuyển `CLOSED` → `OPEN`, thời gian ở `OPEN` và số lần `not_permitted`.
2. **Độ tin cậy:** failure rate, slow-call rate, số lời gọi thành công/thất bại và số mẫu trong cửa sổ.
3. **Độ trễ:** p50/p95/p99 của lời gọi được bảo vệ, so sánh với `slowCallDurationThreshold` và timeout client.
4. **Khả năng phục hồi:** số lần fallback, tỷ lệ fallback hoàn tất, số probe trong `HALF_OPEN`.
5. **Tác động người dùng:** request rate, latency và response code của API gọi dependency.

Giữ một panel hoặc dashboard cho mỗi dependency quan trọng, nhưng dùng cùng quy ước tên và đơn vị. Hiển thị ngưỡng cấu hình cùng đường metric để người xem hiểu vì sao tỷ lệ hiện tại dẫn tới chuyển trạng thái.

## 10. Cảnh báo theo triệu chứng, không chỉ theo trạng thái

Một số cảnh báo hữu ích:

- Breaker ở `OPEN` lâu hơn khoảng thời gian vận hành dự kiến.
- `not_permitted` tăng đột ngột, cho thấy nhiều request đang bị chặn.
- Failure rate vượt ngưỡng trong một khoảng thời gian và có đủ lưu lượng.
- Slow-call rate hoặc p95 vượt mục tiêu độ trễ liên tục.
- Fallback rate tăng mạnh hoặc fallback cũng bắt đầu thất bại.
- Request đầu-cuối tăng latency hoặc 5xx dù breaker đang bảo vệ dependency.

Tránh cảnh báo chỉ dựa trên một mẫu lỗi đơn lẻ. Với lưu lượng thấp, một lỗi có thể tạo tỷ lệ 100% trong cửa sổ nhỏ nhưng không đại diện cho sự cố diện rộng. Kết hợp số lượng mẫu, thời gian duy trì, trạng thái breaker và tác động tới request nghiệp vụ. Dùng khoảng thời gian đánh giá phù hợp với `slidingWindowType`, `slidingWindowSize` và mục tiêu SLO.

## 11. Bảo vệ endpoint quan sát

Actuator `metrics` và `prometheus` có thể tiết lộ tên dependency nội bộ, cấu trúc ứng dụng và lưu lượng. Chỉ expose endpoint cần thiết, giới hạn truy cập trong mạng giám sát và áp dụng xác thực/phân quyền nếu có thể truy cập từ bên ngoài mạng tin cậy. Không expose `env` hoặc `configprops` công khai chỉ để tiện debug.

Nếu dùng Prometheus, cấu hình scrape endpoint qua mạng nội bộ và không đưa credential vào label. Với hệ thống đa instance, gắn nhãn application, environment và instance theo quy ước vận hành; tránh thêm nhãn có cardinality cao như request ID.

## 12. Quy trình điều tra khi metric bất thường

Khi failure rate hoặc slow-call rate tăng, có thể đi theo trình tự:

1. Xác định breaker ID và trạng thái hiện tại.
2. Kiểm tra số mẫu trong sliding window và `minimumNumberOfCalls`.
3. So sánh failure rate với slow-call rate để biết dependency lỗi hay chỉ chậm.
4. Xem call duration p95/p99 và log/trace tại thời điểm bất thường.
5. Kiểm tra số lần `not_permitted` để biết breaker đang chặn bao nhiêu request.
6. Đối chiếu fallback metrics với request latency và response code đầu-cuối.
7. Kiểm tra timeout, exception classification, client pool, network và trạng thái dependency.

Nếu breaker `OPEN` nhưng failure rate không tăng, đó có thể là hành vi đúng: supplier đã bị chặn nên không phát sinh thêm kết quả dependency để cập nhật tỷ lệ. Nếu fallback rate cao nhưng request API vẫn thành công, hệ thống có thể đang duy trì phục vụ nhờ dữ liệu dự phòng; cần đánh giá tuổi dữ liệu và mức chấp nhận của nghiệp vụ.

## 13. Kiểm thử metric và event

Trong integration test, xác minh các meter xuất hiện sau khi thực thi lời gọi thành công, thất bại, chậm và bị từ chối. Với `SimpleMeterRegistry`, có thể kiểm tra meter mà không cần chạy Prometheus:

```java
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import io.github.resilience4j.circuitbreaker.CircuitBreaker;
import io.github.resilience4j.circuitbreaker.CircuitBreakerRegistry;
import io.github.resilience4j.micrometer.tagged.TaggedCircuitBreakerMetrics;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

class CircuitBreakerMetricsTest {

    @Test
    void recordsCallsAndStateMetrics() {
        SimpleMeterRegistry meterRegistry = new SimpleMeterRegistry();
        CircuitBreakerRegistry registry = CircuitBreakerRegistry.ofDefaults();
        CircuitBreaker breaker = registry.circuitBreaker("inventory");

        TaggedCircuitBreakerMetrics.ofCircuitBreakerRegistry(registry)
            .bindTo(meterRegistry);

        breaker.executeRunnable(() -> { });

        assertThat(meterRegistry.find("resilience4j.circuitbreaker.calls")
            .tag("name", "inventory")
            .timer()).isNotNull();
        assertThat(meterRegistry.find("resilience4j.circuitbreaker.state")
            .tag("name", "inventory")
            .gauges()).isNotEmpty();
    }
}
```

Đây là ví dụ kiểm tra ý tưởng; cách bind metric và tag được xuất có thể khác giữa các phiên bản Resilience4j. Trong dự án, dùng API tương ứng với phiên bản đang quản lý và kiểm tra tag thực tế của meter. Ngoài meter, nên kiểm thử event state transition khi đủ điều kiện mở breaker và event call-not-permitted khi gọi trong trạng thái `OPEN`.

## 14. Quy tắc quan sát

- Theo dõi failure rate và slow-call rate riêng biệt; không gộp chúng thành một tỷ lệ lỗi duy nhất.
- Theo dõi số mẫu và trạng thái breaker cùng các tỷ lệ để tránh kết luận từ lưu lượng quá thấp.
- Đo call duration ở breaker và latency đầu-cuối ở tầng API bằng các metric riêng.
- Theo dõi `not_permitted` riêng vì lời gọi bị chặn không phải lời gọi dependency thất bại.
- Đo fallback rate và fallback outcome để biết ứng dụng đang duy trì phục vụ bằng cách nào.
- Bật histogram khi cần p95/p99 và kiểm tra bucket thực tế ở Prometheus.
- Dùng tag có cardinality thấp; đưa chi tiết request vào log/trace.
- Bảo vệ endpoint Actuator và ghi event state transition có cấu trúc.

Khi kết hợp metric, event, log và trace, nhóm phát triển có thể xác định dependency đang lỗi, đang chậm hay đã bị circuit breaker chặn; đồng thời biết fallback và request nghiệp vụ có giữ được chất lượng phục vụ hay không. Đây là cơ sở để điều chỉnh sliding window, ngưỡng lỗi, timeout và chính sách fallback dựa trên hành vi thực tế của hệ thống Spring Cloud.
