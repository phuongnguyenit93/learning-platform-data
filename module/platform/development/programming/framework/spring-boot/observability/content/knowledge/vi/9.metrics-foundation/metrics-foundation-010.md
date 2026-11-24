# Metric name

> **Chương:** Metrics nền tảng  
> **Module:** `SPRING_BOOT_OBSERVABILITY` — quan sát ứng dụng Spring Boot bằng Micrometer Observation, metrics, logs và distributed tracing; sử dụng tên metric nhất quán để điều tra lỗi, độ trễ và hành vi ứng dụng cùng các thông tin về context propagation, tags/cardinality, exporter và sampling.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích **metric name** định danh điều gì và tại sao tên cần ổn định theo thời gian.
- Phân biệt **tên metric**, **tags/labels**, **meter type**, **base unit**, **description** và **observation name**.
- Đặt tên cho counter, gauge, timer, distribution summary theo quy ước Micrometer trong Spring Boot; hiểu vì sao tên ở backend Prometheus có thể khác tên trong Java.
- Nhận diện các tên gây cardinality cao, nhập nhằng đơn vị hoặc làm hỏng dashboard và cảnh báo.
- Tạo và kiểm tra meter thực tế với `MeterRegistry`, Spring Boot Actuator và một exporter phù hợp.
- Liên kết metric với logs/traces bằng ngữ cảnh phù hợp mà không biến request ID, trace ID hoặc tenant ID thành một phần của tên metric.

## 1. Vì sao tên metric quan trọng?

Giả sử một hệ thống thương mại điện tử có hai dịch vụ Spring Boot. Dịch vụ thứ nhất ghi số lần đặt hàng bằng `orders.created`; dịch vụ thứ hai dùng `orderCreateCount`. Một phiên bản mới lại ghi `order_created_success_count_v2`. Ba tên có thể đang đo cùng một hành vi nhưng không thể tự động gộp thành một chuỗi thời gian nhất quán.

Khi đội vận hành hỏi “sau đợt triển khai này, tỷ lệ đơn hàng thất bại có tăng không?”, vấn đề không chỉ là **có dữ liệu**. Các phép đo phải có **hợp đồng đặt tên và ý nghĩa** để truy vấn, cảnh báo và so sánh qua nhiều phiên bản vẫn đúng.

**Metric name** là tên logic của phép đo. Trong Micrometer, tên được kết hợp với loại meter và tập tags để mô tả phép đo cần thu thập. Tên tốt thường là một chuỗi **ngắn, ổn định, có nghĩa và nhất quán** giữa các dịch vụ.

Ví dụ:

```text
orders.created
checkout.duration
payment.requests
payment.queue.depth
inventory.reserved.items
```

Những tên này mô tả **loại hiện tượng**, thay vì mô tả một lần xử lý riêng lẻ.

Một câu hỏi thiết kế hữu ích: **“Sau 6 tháng và 20 lần triển khai, metric cùng tên này có còn cùng định nghĩa không?”** Nếu câu trả lời không chắc chắn, cần làm rõ ý nghĩa trước khi đưa tên vào dashboard và alert.

## 2. Metric name không phải toàn bộ danh tính của time series

Một điểm quan trọng: **tên metric không đại diện cho một chuỗi thời gian duy nhất** nếu metric có labels/tags.

Ví dụ meter logic:

```text
name = http.server.requests
type = TIMER
tags = {
  method: "POST",
  uri: "/orders",
  status: "500"
}
```

Trong cùng metric name có thể có các tổ hợp khác:

```text
http.server.requests {method=GET,  uri=/orders, status=200}
http.server.requests {method=POST, uri=/orders, status=200}
http.server.requests {method=POST, uri=/orders, status=500}
```

Từng tổ hợp tags có thể đóng góp các time series riêng trong backend. Với timer/histogram, một meter logic có thể được xuất thành **nhiều chuỗi số** như count, sum và các buckets. Vì vậy thiết kế tên phải gắn với việc chọn **meter type, unit và cardinality của tags**.

| Thành phần | Dùng để diễn đạt | Ví dụ |
| --- | --- | --- |
| **Metric name** | Hiện tượng được đo | `checkout.duration` |
| **Meter type** | Cách giá trị được thu thập | `Timer`, `Counter`, `Gauge`, `DistributionSummary` |
| **Tags/labels** | Các chiều phân nhóm hữu hạn | `channel=web`, `outcome=success` |
| **Base unit** | Đơn vị đo, nếu áp dụng | `bytes`, `requests`, `items` |
| **Description** | Giải nghĩa phép đo cho người đọc | “Thời gian xử lý thao tác checkout” |
| **Recorded value** | Giá trị đo được | `0.42 s` hoặc `120 requests` |

Trong Micrometer, `Meter.Id` chứa các thông tin như tên, tags, base unit, description và type. Ở các registry khác nhau, **naming convention** có thể chuyển đổi tên/tags/đơn vị trước khi xuất.

Đừng nhầm **tên một phép đo** với **định danh một request**. Các giá trị như `orderId`, `traceId` hoặc `userId` không nên là phần đuôi của metric name và thường cũng không phù hợp làm metric labels.

## 3. Cách đặt tên metric trong Micrometer

Micrometer khuyến khích tên theo dạng các thành phần phân tách bởi dấu chấm:

```text
<domain>.<operation>.<measurement>
```

Đây là **mẫu thiết kế minh họa**, không phải cú pháp bắt buộc của API. Cần chọn mức chi tiết vừa đủ để diễn đạt một phép đo cụ thể.

Ví dụ:

| Nhu cầu | Tên logic gợi ý | Meter type | Lý do |
| --- | --- | --- | --- |
| Đếm số đơn được tạo thành công | `orders.created` | Counter | Sự kiện tích lũy; không cần ghi `success` trong tên nếu định nghĩa chỉ đếm đơn đã tạo. |
| Đo thời gian thực thi checkout | `checkout.duration` | Timer | Cần count và tổng thời gian, có thể xem histogram/phân vị nếu cấu hình. |
| Đo số tác vụ đang chờ xử lý | `payment.queue.depth` | Gauge | Giá trị hiện tại có thể tăng hoặc giảm. |
| Đếm lần thử gọi đối tác | `payment.requests` | Counter | Có thể phân nhóm bằng tag `outcome` hoặc `provider` đã chuẩn hóa. |
| Đo kích thước payload | `message.payload.size` | DistributionSummary | Phân bố kích thước từng thông điệp. |
| Đếm số lần thử lại | `payment.retries` | Counter | Một retry là một sự kiện tăng. |

Các nguyên tắc thiết kế:

1. **Tên diễn tả đối tượng và đại lượng:** `payment.queue.depth` dễ hiểu hơn `data1` hoặc `processMetric`.
2. **Không nhúng giá trị động:** `orders.created.123456` khiến mỗi order tạo một tên mới.
3. **Không nhúng những nhãn đã là chiều phân nhóm:** thay vì `checkout.duration.mobile` và `checkout.duration.web`, ưu tiên `checkout.duration` với tag `channel=mobile|web`.
4. **Tránh quy ước xung đột:** không dùng cùng một metric name cho những phép đo mang ý nghĩa hoặc kiểu dữ liệu khác nhau.
5. **Quy ước thống nhất theo hệ thống:** dùng nhất quán `orders` hoặc `order`, `latency` hoặc `duration`; nếu đã có chuẩn của tổ chức hoặc framework, ưu tiên chuẩn đó.

Đặt tên chỉ là một nửa hợp đồng. Mỗi metric cần được mô tả **khi nào được ghi**, **giá trị có ý nghĩa gì**, **đơn vị**, **các tags được phép** và **khi nào được xem là lỗi/thành công**.

### 3.1. Tên metric nên ổn định đến mức nào?

Hãy giữ tên giống nhau nếu phép đo giữ nguyên ngữ nghĩa. Ví dụ số lượt gọi thanh toán được đếm ở điểm bắt đầu lời gọi: mọi lần thử đều tăng counter dù kết quả thành công hay lỗi. Khi đó có thể dùng `payment.requests` và tag `outcome` hữu hạn để phân nhóm.

Nếu đổi từ “đếm số lần thử” sang “đếm số thanh toán đã được ghi sổ thành công”, **định nghĩa đã thay đổi**. Không nên giữ tên cũ một cách âm thầm vì chuỗi thời gian trước và sau sẽ không còn so sánh được. Cần có metric mới hoặc một kế hoạch chuyển đổi và tài liệu hóa rõ.

## 4. Tên, kiểu meter và đơn vị phải khớp nhau

Các loại meter không chỉ có API khác nhau; chúng tạo dữ liệu có ngữ nghĩa khác nhau. Không nên gắn nhãn “latency” cho một gauge số request, hay đặt tên `requests.total` cho một giá trị có thể giảm.

| Loại meter | Ý nghĩa | Ví dụ Java | Diễn giải |
| --- | --- | --- | --- |
| **Counter** | Giá trị tích lũy, thường chỉ tăng khi có sự kiện | `Counter.builder("orders.created")` | Số lần sự kiện tạo đơn được ghi nhận. |
| **Timer** | Số lần và thời lượng hoạt động | `Timer.builder("checkout.duration")` | Đo duration; registry có thể xuất count, sum và histogram. |
| **Gauge** | Giá trị hiện tại tại thời điểm được đọc | `Gauge.builder("payment.queue.depth", ...)` | Độ sâu hàng đợi hiện tại. |
| **DistributionSummary** | Phân bố giá trị không nhất thiết là thời gian | `DistributionSummary.builder("message.payload.size")` | Kích thước thông điệp, số lượng item mỗi lô... |
| **LongTaskTimer** | Theo dõi tác vụ đang chạy lâu | `LongTaskTimer.builder("batch.running.duration")` | Số tác vụ đang hoạt động và thời gian của chúng. |

**Lưu ý về đơn vị:**

- Với `Timer`, truyền `Duration` hoặc đơn vị thời gian qua API tương ứng. Registry thường chuẩn hóa thời gian sang đơn vị mà backend yêu cầu, ví dụ giây trong Prometheus.
- Với `DistributionSummary` hoặc `Gauge`, mô tả đơn vị rõ ràng; `baseUnit("bytes")` hoặc một đơn vị phù hợp có thể giúp người dùng hiểu giá trị.
- Không tự thêm `.milliseconds` vào tên timer rồi giả định backend sẽ xuất milliseconds. Nếu backend hiển thị giây, tên như vậy gây hiểu lầm.
- Tên và unit phải đủ rõ để dashboard không tự đổi đơn vị hai lần.

Ví dụ về metric hợp lý:

```text
message.payload.size     type=DistributionSummary, unit=bytes
checkout.duration        type=Timer, unit=time
orders.created           type=Counter, unit=orders/events (theo định nghĩa)
```

Việc backend thêm hậu tố đơn vị hay counter suffix là vấn đề của **registry naming convention**. Không nên trộn tên nội bộ với hậu tố do exporter tự sinh khi thiết kế tên logic.

## 5. Từ tên Micrometer sang tên ở Prometheus

Spring Boot thường dùng Micrometer Metrics và có thể xuất sang Prometheus. Micrometer sử dụng tên logic dạng dấu chấm, trong khi Prometheus metric names thường sử dụng dấu gạch dưới và các hậu tố phản ánh kiểu phép đo.

Các ví dụ **mang tính định hướng**, phải kiểm tra output thật vì phiên bản Micrometer/Prometheus registry, cấu hình distribution và naming convention có thể làm tên cuối khác đi.

| Tên trong Java/Micrometer | Kiểu | Ví dụ có thể thấy ở Prometheus |
| --- | --- | --- |
| `orders.created` | Counter | `orders_created_total` |
| `payment.queue.depth` | Gauge | `payment_queue_depth` |
| `checkout.duration` | Timer | `checkout_duration_seconds_count`, `checkout_duration_seconds_sum` |
| `checkout.duration` với histogram phù hợp | Timer | Có thể có `checkout_duration_seconds_bucket` cùng count/sum |
| `message.payload.size`, đơn vị bytes | DistributionSummary | Các series tương ứng count/sum, có thể có buckets tùy cấu hình |

Từ đây rút ra ba điều:

1. **Tên logic khác tên vật lý xuất ra.** Khi viết code, dùng `checkout.duration`; khi viết PromQL, phải dựa trên tên series thật mà registry đã xuất, ví dụ `checkout_duration_seconds_count`.
2. **Hậu tố có ý nghĩa:** `_count` thể hiện số observation trong timer/summary; `_sum` là tổng giá trị; `_bucket` liên quan histogram; counter thường có `_total` theo quy ước Prometheus.
3. **Không tự đoán histogram tồn tại:** muốn có buckets để tính phân vị có thể cần cấu hình distribution/statistics hoặc `publishPercentileHistogram()`, và còn phụ thuộc backend.

Ví dụ một truy vấn PromQL khi các series tương ứng có tồn tại:

```promql
sum(rate(orders_created_total[5m]))
```

Đây là tốc độ tăng trung bình của counter trong khoảng 5 phút; **không phải** tổng số đơn từ đầu thời gian. Nếu có tags hữu hạn, có thể nhóm:

```promql
sum by (channel) (rate(orders_created_total[5m]))
```

Với duration có `_sum` và `_count`, một ước tính **thời gian trung bình** trong cửa sổ truy vấn là:

```promql
sum(rate(checkout_duration_seconds_sum[5m]))
/
sum(rate(checkout_duration_seconds_count[5m]))
```

Kết quả thường có đơn vị **giây mỗi lần đo**. Để tính p95 từ histogram, cần buckets tương ứng và dùng `histogram_quantile()`; nếu không có `_bucket` thì không thể suy ra p95 histogram bằng công thức này.

```promql
histogram_quantile(
  0.95,
  sum by (le) (rate(checkout_duration_seconds_bucket[5m]))
)
```

Công thức minh họa cho **classic histogram buckets**; cách xuất native histogram hoặc cấu hình phân phối khác có thể yêu cầu truy vấn khác. Kiểm tra tên series và phiên bản backend trước khi áp dụng vào production.

## 6. Tạo metric với `MeterRegistry` trong Spring Boot

Ví dụ sau tạo một counter và một timer bằng tên logic ổn định. Channel từ bên ngoài được chuẩn hóa thành `web`, `mobile` hoặc `other` để tránh cardinality tăng do giá trị tùy ý.

```java
package example.metrics;

import java.util.function.Supplier;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.springframework.stereotype.Service;

@Service
public class CheckoutMetrics {
    private final MeterRegistry registry;

    public CheckoutMetrics(MeterRegistry registry) {
        this.registry = registry;
    }

    public void orderCreated(String channel) {
        Counter.builder("orders.created")
                .description("Number of successfully created orders")
                .tag("channel", normalizeChannel(channel))
                .register(registry)
                .increment();
    }

    public <T> T measureCheckout(String channel, Supplier<T> operation) {
        return Timer.builder("checkout.duration")
                .description("Duration of a checkout operation")
                .tag("channel", normalizeChannel(channel))
                .register(registry)
                .record(operation);
    }

    private static String normalizeChannel(String value) {
        if ("web".equals(value) || "mobile".equals(value)) {
            return value;
        }
        return "other";
    }
}
```

Cách sử dụng trong service nghiệp vụ (biến `checkoutService` và `request` chỉ là ví dụ):

```java
Order order = checkoutMetrics.measureCheckout(
        request.channel(),
        () -> checkoutService.createOrder(request)
);
checkoutMetrics.orderCreated(request.channel());
```

Trong ví dụ, `orders.created` chỉ tăng **sau khi tạo đơn thành công và trả kết quả**. Nếu hệ thống có transaction cần commit, hãy quyết định chính xác lúc nào việc tạo đơn thực sự được xem là hoàn tất; nếu tăng counter trước khi transaction rollback, metric sẽ không còn khớp định nghĩa.

Một số đặc điểm quan trọng:

- `MeterRegistry` quản lý meters; khi đăng ký lại **cùng một name/tags tương thích**, registry có thể trả về meter đã tồn tại. Điều này giúp tránh tạo một meter mới cho mỗi request có tags giống nhau.
- Dữ liệu có độ phân nhóm được quyết định bởi **tags**, không bởi tên metric riêng của từng channel.
- `Timer.record(operation)` đo thời gian của thao tác **đồng bộ** được thực thi trong supplier; nếu supplier trả về future trước khi tác vụ hoàn thành, duration không bao gồm phần công việc async sau đó.
- `Counter` dùng khi số sự kiện tích lũy là điều cần quan sát; không dùng counter để biểu diễn số đơn **đang chờ** vì giá trị đó có thể giảm, phù hợp hơn với gauge.
- Một `Timer` cũng có count của những lần đo thời lượng. Không cần tạo thêm counter cùng nghĩa cho “số lần checkout được đo” nếu count của timer đã đáp ứng nhu cầu.

**Đừng thêm `orderId`, `traceId`, `userId` hay URL chứa ID cụ thể vào tên metric hoặc tags** chỉ để hỗ trợ điều tra một request. Dùng logs/traces với chính sách dữ liệu phù hợp.

### 6.1. Meter type hoặc tags bị xung đột

Giả sử ban đầu code tạo một `Counter` tên `orders.created` nhưng phiên bản khác lại tạo `Timer` cùng tên và tập tags. Điều đó tạo ra xung đột ý nghĩa ở registry/exporter; tùy triển khai, meter có thể không được đăng ký như mong đợi hoặc bị lỗi.

Một vấn đề khác: hai nhóm code tạo cùng tên metric nhưng khác **tập tag keys** hoặc cùng key với ngữ nghĩa khác nhau. Một số backend yêu cầu mọi series trong một họ metric có cấu trúc nhất quán; thiếu tag ở một nhánh có thể làm việc xuất dữ liệu bị từ chối hoặc khó truy vấn.

Để tránh sai lệch:

1. Thống nhất **tên, type, description, unit và tập tag keys** cho mỗi loại metric.
2. Dùng hằng số hoặc abstraction chung nếu nhiều nơi cùng instrument một nghiệp vụ.
3. Khi một tag không có dữ liệu, dùng giá trị mặc định cố định như `unknown` nếu hợp đồng metric yêu cầu tag đó.
4. Kiểm tra registry và endpoint đã xuất, vì code compile thành công không chứng minh metric đã được đăng ký đúng.

## 7. Metric name trong `Micrometer Observation`

Một dự án Spring Boot có thể dùng **Micrometer Observation** để đo thao tác và kết nối nó với metrics lẫn distributed tracing:

```java
import java.util.function.Supplier;
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;

public class CheckoutObservations {
    private final ObservationRegistry registry;

    public CheckoutObservations(ObservationRegistry registry) {
        this.registry = registry;
    }

    public <T> T submit(Supplier<T> action) {
        return Observation.createNotStarted("checkout.submit", registry)
                .contextualName("submit checkout")
                .lowCardinalityKeyValue("channel", "web")
                .observe(action);
    }
}
```

Ở đây có các khái niệm khác nhau:

| Thuộc tính | Vai trò |
| --- | --- |
| `checkout.submit` | **Observation name**, tên ổn định của loại công việc. Handler metrics phù hợp có thể dùng tên này để tạo metric. |
| `submit checkout` | **Contextual name**, mô tả thao tác theo ngữ cảnh; tracing handler có thể dùng cho tên span. |
| `channel=web` | **Low-cardinality key-value**, thích hợp làm chiều phân nhóm trên metrics. |
| `ObservationRegistry` | Quản lý callbacks/handlers; quyết định observation có tạo ra metrics, spans hay không thông qua tích hợp. |

**Observation name không đồng nghĩa 1:1 với chuỗi Prometheus.** Handler metrics, conventions và registry naming conventions tham gia quyết định tên meter vật lý. Nếu handler tracing được cấu hình, span có thể được đặt tên theo contextual name; logs vẫn phải được ghi qua logging framework.

`ObservationConvention` có thể giúp chuẩn hóa tên và key-values cho một họ observations. Khi thiết kế tên dùng chung giữa các dịch vụ, nên kiểm tra convention của instrumentation/framework trước khi tự ghi đè. Chẳng hạn tên `http.server.requests` do framework phát ra có ngữ nghĩa xác định; tùy ý đổi hoặc tái sử dụng cùng tên cho phép đo nghiệp vụ khác có thể làm hỏng dashboard và SLO.

### 7.1. Metric name không phải correlation ID

`traceId` là định danh của **một distributed trace**, còn `spanId` định danh một span. Chúng hữu ích trong logs và tracing backend, nhưng có cardinality rất cao.

Một luồng điều tra nên là:

**Metric `checkout.submit` báo latency tăng** → lọc theo `channel`, route hoặc môi trường triển khai → tìm trace chậm theo thời gian/tín hiệu hoặc exemplar nếu backend hỗ trợ → mở logs bằng `traceId` hoặc correlation ID.

Không tạo các tên như:

```text
checkout.submit.trace-91be...
checkout.submit.order-004921...
http.requests.user-18491
```

Không gắn những ID này làm metric tags. Tên và tags metric phục vụ đo xu hướng; logs và traces phục vụ truy tìm một lần xử lý cụ thể.

## 8. Tên metric từ instrumentation tự động

Ngoài các meter tự tạo, Spring Boot Actuator/Micrometer có thể tạo metrics cho HTTP, JVM, process, datasources và những thành phần framework được hỗ trợ.

Các tên logic thường gặp, tùy phiên bản/cấu hình:

| Tên logic minh họa | Nhóm tín hiệu | Ý nghĩa |
| --- | --- | --- |
| `http.server.requests` | HTTP | Độ trễ/count của requests server đã được instrument. |
| `http.client.requests` | HTTP client | Độ trễ/count của các lời gọi HTTP client đã instrument. |
| `jvm.memory.used` | JVM | Lượng bộ nhớ đang dùng. |
| `jvm.threads.live` | JVM | Số luồng sống hiện tại. |
| `process.cpu.usage` | Process | Mức sử dụng CPU của process. |

Tên hoặc tag keys thực tế cần được kiểm tra trong phiên bản Spring Boot đang dùng. Một số stack chuyển sang semantic conventions khác theo phiên bản hoặc instrumentation tương ứng; không dựa vào ví dụ mà giả định toàn bộ những meter này chắc chắn xuất hiện.

Khi đã có HTTP server timer, trước khi tạo `api.requests.duration` thủ công với ý nghĩa tương tự, hãy xem có thật sự cần thêm metric hay chỉ cần thêm một **observation nghiệp vụ** để đo phần xử lý còn thiếu. Đo lặp làm tăng chi phí và khiến việc tính rate/latency dễ bị nhầm.

### 8.1. Xem tên meter qua Spring Boot Actuator

Khi ứng dụng có Actuator và endpoint được expose theo chính sách môi trường:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus
```

Có thể truy vấn các metric names logic:

```http
GET /actuator/metrics
```

Kiểm tra một meter cụ thể:

```http
GET /actuator/metrics/checkout.duration
```

Với một số tag key/value đã ghi nhận, Actuator Metrics endpoint hỗ trợ lọc bằng query parameter:

```http
GET /actuator/metrics/checkout.duration?tag=channel:web
```

Endpoint chỉ hiển thị meter và số đo **đã được đăng ký/ghi nhận**; nếu thao tác chưa chạy, có thể chưa thấy meter tương ứng.

Để xem tên mà Prometheus exporter công bố, dùng:

```http
GET /actuator/prometheus
```

Endpoint `prometheus` yêu cầu Prometheus registry phù hợp và được expose. Nó có thể không có nếu chỉ thêm Actuator. Một dự án sử dụng OTLP hoặc backend khác có thể xuất tên và attributes theo quy ước riêng.

**Bảo mật:** endpoint Actuator có thể tiết lộ thông tin hệ thống. Chỉ mở các endpoint cần thiết, cấu hình quyền truy cập và giới hạn mạng thích hợp; không đưa thông tin cá nhân vào metric names/tags.

## 9. Metric name và cardinality của tags

Một metric name ổn định chưa đủ nếu tags chứa giá trị động. Ngược lại, cố “giảm tags” bằng cách nhúng giá trị động vào tên chỉ làm vấn đề nghiêm trọng hơn.

Ví dụ sai:

```java
// Sai: mỗi user tạo một metric name mới.
registry.counter("orders.created.user." + userId).increment();

// Sai: tên ổn định nhưng nhãn vẫn có cardinality rất cao.
registry.counter("orders.created", "user.id", userId).increment();
```

Ví dụ đúng khi cần so sánh channel:

```java
String normalized = "web".equals(channel) || "mobile".equals(channel)
        ? channel : "other";

registry.counter("orders.created", "channel", normalized).increment();
```

Giả sử có 8 routes, 5 nhóm status, 3 channels và 4 vùng triển khai, số tổ hợp nhãn tiềm năng là:

\[
8 \times 5 \times 3 \times 4 = 480
\]

Đây là **cận theo các tổ hợp giả định**, không phải số series chắc chắn xuất hiện. Timer và histogram có thể xuất nhiều time series cho một tổ hợp, và các labels instance/pod còn tăng số series. Nếu thêm một `tenant.id` có 10.000 giá trị, số tổ hợp lý thuyết có thể tăng lên `4.800.000`.

Các câu hỏi cần kiểm tra khi duyệt một metric:

- Tên có chứa giá trị riêng của request, tenant, user, order, URL hoặc timestamp không?
- Tập tag keys đã được chuẩn hóa giữa các chỗ phát ra cùng tên metric chưa?
- Giá trị tags có hữu hạn và biết trước không?
- Trong 12 tháng tới, số lượng tên/tags sẽ tăng theo lượng người dùng hay chỉ theo số loại nghiệp vụ?
- Nếu tên bị thay đổi, những dashboard, recording rules và alerts nào phụ thuộc vào nó?

## 10. Đổi tên metric trong một hệ thống đang chạy

Tên metric là một **hợp đồng quan sát**. Đổi tên metric có thể làm biểu đồ trống, cảnh báo không chạy, truy vấn SLO sai hoặc tạo một chuỗi lịch sử mới không nối liền với dữ liệu cũ.

Ví dụ đổi `orders.created` thành `checkout.orders.created` là một thay đổi đáng kể đối với những hệ thống đang truy vấn tên cũ. Cần xử lý tương tự việc thay đổi hợp đồng API:

1. **Kiểm kê nơi sử dụng:** dashboard, alerts, recording rules, báo cáo SLO, tài liệu và tích hợp bên ngoài.
2. **Xác định có đổi ngữ nghĩa không:** chỉ chuẩn hóa tên hay thay đổi thời điểm đếm, đơn vị, tags, type? Nếu thay đổi định nghĩa, cần mô tả khác biệt dữ liệu.
3. **Lập kế hoạch chuyển tiếp:** tùy khả năng, tạm phát tên cũ và tên mới song song hoặc hỗ trợ chuyển đổi tại tầng truy vấn/recording rules. Tránh vô tình đếm gấp đôi khi tổng hợp hai tên.
4. **Cập nhật người tiêu thụ:** chuyển dashboard và alerts sang tên mới; kiểm chứng dữ liệu và threshold thực tế.
5. **Theo dõi và bỏ tên cũ:** chỉ loại bỏ sau khi đã xác minh không còn người tiêu thụ phụ thuộc.

Không nên thêm hậu tố `.v2` chỉ vì thay đổi cách triển khai code nếu phép đo vẫn cùng ngữ nghĩa. Ngược lại, nếu định nghĩa được thay đổi đáng kể, dùng tên mới hoặc version rõ ràng có thể cần thiết để tránh nối hai tập số liệu không tương đương.

## 11. Đo lường thực tế: trường hợp checkout chậm

**Tình huống:** Khách hàng báo checkout chậm vào giờ cao điểm. Ứng dụng đang có:

```text
checkout.duration {channel=web}
checkout.duration {channel=mobile}
orders.created     {channel=web}
orders.created     {channel=mobile}
```

Quy trình điều tra:

1. **Xác minh tên và loại meter:** `checkout.duration` là timer hay gauge? Nó đo toàn bộ checkout hay chỉ bước lưu DB? Đối chiếu code instrumentation và mô tả.
2. **Kiểm tra rate/thời lượng:** xem count, sum, các phân phối phù hợp theo channel; so sánh thời gian trước và sau bất thường. Nếu không có histogram, đừng vẽ p95 từ series không tồn tại.
3. **Kiểm tra tác động:** nếu duration tăng nhưng `orders.created` giảm, có thể một phần request không hoàn tất hoặc thất bại; không suy ra trực tiếp nguyên nhân khi chưa có outcome/error metrics.
4. **Khoanh vùng qua traces:** nếu tracing đã được bật, chọn trace chậm được lấy mẫu, xem spans HTTP/DB/payment để xác định bước nào tốn thời gian.
5. **Đối chiếu logs:** tìm exception/timeout theo `traceId` hoặc correlation ID. Tags metric như `channel` dùng để lọc nhóm; logs/traces hỗ trợ tìm request cụ thể.
6. **Kiểm tra exporter và sampling:** metrics có thể không được scrape đúng lúc, traces có thể bị sampling, hoặc collector có thể mất tín hiệu.
7. **Xác nhận sau sửa:** đảm bảo tên/tags của các metrics giữ nguyên ngữ nghĩa, error rate và latency trở lại mức chấp nhận được, và dữ liệu được thu liên tục.

Nếu lúc điều tra nhận thấy `checkout.duration` của một service chỉ đo bước enqueue, còn service khác đo đến lúc nhận phản hồi thanh toán, dù **cùng tên**, các số liệu không thể so sánh trực tiếp. Lúc đó cần sửa ranh giới instrumentation và chuẩn hóa lại hợp đồng đo.

## 12. Lỗi thường gặp về metric name

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra và khắc phục |
| --- | --- | --- |
| Không thấy `checkout.duration` trong Prometheus | Registry đổi thành các series có suffix/đơn vị, hoặc meter chưa có dữ liệu | Xem `/actuator/metrics` và `/actuator/prometheus`; kiểm tra naming convention. |
| Truy vấn PromQL không có `_bucket` | Chưa bật histogram hoặc loại xuất histogram không phù hợp | Kiểm tra distribution settings, registry và các series thực tế. |
| Dashboard mất dữ liệu sau deploy | Đổi tên metric hoặc label key | So sánh tên/tags trước và sau; thực hiện migration có kiểm soát. |
| Cùng tên nhưng đơn vị khác nhau | Một service đo milliseconds, service khác đo seconds ngoài API chuẩn | Quy định type/unit, dùng Timer API và kiểm tra output. |
| Backend báo xung đột metric | Cùng tên với type hoặc tập tag keys không tương thích | Chuẩn hóa định nghĩa, sửa meter bị trùng hoặc sai type. |
| Số series tăng theo traffic/tenant | Nhúng ID động vào tên hoặc tags | Loại bỏ ID, dùng tags hữu hạn; truy tìm chi tiết bằng logs/traces. |
| Metrics bị đếm trùng | Tạo counter mới trùng count của timer hoặc instrument lại cùng ranh giới | Chọn nguồn đo chính thức, kiểm tra mục đích từng meter. |
| `orders.created` tăng dù đơn được rollback | Increment trước thời điểm giao dịch được xác nhận | Chuyển điểm đếm đến mốc nghiệp vụ đã thống nhất. |
| Kết quả p95 mâu thuẫn với thời gian trung bình | Hiểu sai phân vị/histogram, thiếu buckets hoặc sample count nhỏ | Kiểm tra dữ liệu phân phối, các tags và lượng mẫu. |
| Metrics có tag nhưng logs thiếu trace ID | Logging chưa tích hợp MDC hoặc context bị mất qua async boundary | Kiểm tra logging pattern, scope và context propagation. |

## 13. Bài thực hành: kiểm tra tên từ Java đến backend

Trên một ứng dụng Spring Boot thử nghiệm có Micrometer/Actuator phù hợp, thực hiện:

1. Tạo `CheckoutMetrics` như ví dụ phần 6. Thực thi một số request `web` và `mobile`, bảo đảm cả counter và timer đã được ghi.
2. Kiểm tra `/actuator/metrics`, ghi lại **tên logic** của các meter thực sự xuất hiện. Truy vấn `/actuator/metrics/checkout.duration` và lọc `tag=channel:web`.
3. Nếu có Prometheus registry, mở `/actuator/prometheus`, tìm các tên series tương ứng. So sánh tên logic `checkout.duration` với tên vật lý có `_seconds_count`, `_seconds_sum` hoặc hậu tố khác.
4. Bật histogram cho timer trong môi trường thử nghiệm rồi kiểm tra xem buckets có xuất hiện hay không. Tính average latency từ count/sum và p95 từ buckets khi có dữ liệu phù hợp.
5. Thử gửi channel tùy ý `"partner-42"`; xác nhận code chuẩn hóa nó về `other` và số tag values không tăng.
6. Thử một tên sai như `orders.created.<requestId>` trong một đoạn code **chỉ dùng ở môi trường thử nghiệm**, quan sát số lượng meter IDs tăng và loại bỏ đoạn code sau khi hiểu hậu quả.
7. Bật tracing nếu đã có bridge/exporter, ghi một log trong xử lý checkout và so sánh metric name với span name và trace ID. Giải thích vì sao chúng có vai trò khác nhau.
8. Mô phỏng đổi tên meter trong một bản chạy thử, xác định các biểu đồ/truy vấn nào bị ảnh hưởng và lên kế hoạch chuyển đổi.

**Tiêu chí đạt:** người học chỉ ra được metric name trong `MeterRegistry`, tên thực tế ở exporter, type và unit, tags có giới hạn, thời điểm ghi và sự liên kết (hoặc giới hạn liên kết) với tracing/logging. Việc đọc kết quả phải dựa trên dữ liệu thực tế của ứng dụng, không chỉ dựa vào chuỗi tên ví dụ.

## 14. Câu hỏi tự kiểm tra

**Câu 1.** `checkout.duration` và `checkout.duration.web` có phải hai cách tương đương để phân nhóm channel không?  
**Gợi ý:** Không. Cách thứ hai nhúng giá trị nhóm vào tên. Ưu tiên một tên ổn định với tag `channel=web|mobile|other` khi phù hợp.

**Câu 2.** Trong Java, đăng ký `Counter.builder("orders.created")` có bảo đảm Prometheus hiển thị đúng nguyên văn `orders.created` không?  
**Gợi ý:** Không. Registry áp dụng naming convention, suffix và đơn vị; xem output của exporter để biết tên vật lý.

**Câu 3.** Có thể tính p95 từ `checkout_duration_seconds_count` và `checkout_duration_seconds_sum` không?  
**Gợi ý:** Không. Hai series này đủ để tính trung bình trên khoảng thời gian, chưa thể xác định p95; cần histogram buckets hoặc cơ chế phân phối/phân vị thích hợp.

**Câu 4.** Có nên dùng `traceId` như một đoạn của metric name để đi từ metric sang trace?  
**Gợi ý:** Không. Nó tạo tên động với cardinality cực cao; dùng logs/traces/exemplars khi được hỗ trợ.

**Câu 5.** Vì sao type/unit phải là một phần của hợp đồng metric?  
**Gợi ý:** Chúng quyết định cách giá trị được ghi và đọc. Cùng một tên nhưng meter type hay đơn vị khác nhau có thể làm hỏng truy vấn hoặc khiến số liệu bị diễn giải sai.

**Câu 6.** Nếu `Timer.record()` bọc một hàm trả `CompletableFuture` chưa hoàn thành, timer đo thời gian nào?  
**Gợi ý:** Nó chỉ bao quanh thời gian thực thi đồng bộ của lời gọi tạo/nhận future, không tự đo tới khi future hoàn tất.

**Câu 7.** Vì sao đổi tên metric phải có kế hoạch?  
**Gợi ý:** Dashboard, alerts, recording rules và dữ liệu lịch sử có thể phụ thuộc tên cũ; đổi tên không kiểm soát tạo khoảng trống số liệu.

**Câu 8.** Observation name và contextual name có thể khác nhau không?  
**Gợi ý:** Có. Observation name là tên ổn định của loại hoạt động; contextual name có thể mô tả span/hoạt động theo ngữ cảnh. Metric vật lý còn phụ thuộc handler và exporter.

**Điểm cần nhớ:** **Metric name là hợp đồng định nghĩa phép đo**, còn tags là các chiều phân nhóm và meter type/unit cho biết cách hiểu giá trị. Trong Spring Boot/Micrometer, ưu tiên tên ổn định dạng dấu chấm, tránh nhúng ID hoặc giá trị động, kiểm tra tên sau khi exporter chuyển đổi và quản lý thay đổi tên như thay đổi API. Chất lượng observability còn phụ thuộc đúng ranh giới đo, cardinality, context propagation và cách kết nối metrics với logs/traces qua backend, exporter và sampling.
