# Histogram trong Micrometer và Spring Boot

Một API `POST /orders` có thời gian xử lý trung bình 180 ms có vẻ nhanh, nhưng trung bình này có thể che giấu việc một số khách hàng phải chờ 2–3 giây. Để biết **phân bố độ trễ**, cần quan sát không chỉ một con số trung bình mà cả tỷ lệ request rơi vào các khoảng thời gian khác nhau. **Histogram** là công cụ phù hợp cho nhu cầu đó.

Trong module **SPRING_BOOT_OBSERVABILITY**, histogram là một phần của **metrics nền tảng** khi thiết lập observability cho Spring Boot bằng Micrometer Observation, metrics, logs và distributed tracing. Từ histogram, đội vận hành có thể ước lượng p95/p99, đo tỷ lệ đáp ứng ngưỡng thời gian, đánh giá SLO và phát hiện hiện tượng chậm ở phần đuôi phân bố (*tail latency*). Kết hợp metrics với logs và traces giúp chuyển từ câu hỏi “bao nhiêu request bị chậm?” đến “request chậm đi qua thành phần nào và vì sao?”.

## Mục tiêu học tập

Sau bài học này, bạn có thể:

1. Giải thích histogram, bucket, số lượng mẫu và ý nghĩa của bucket tích lũy trong Prometheus.
2. Phân biệt histogram với average, percentile tính tại client và các cách đo bằng `Timer`, `DistributionSummary`.
3. Bật histogram cho HTTP và metric nghiệp vụ trong Spring Boot/Micrometer.
4. Dùng PromQL để tính p95/p99, request rate và tỷ lệ request đáp ứng ngưỡng SLO.
5. Chọn ranh giới bucket hợp lý, kiểm soát số series và nhận biết giới hạn độ chính xác.
6. Đọc đúng dữ liệu khi sampling tracing, exporter hoặc context propagation có vấn đề.
7. Kiểm thử, triển khai và sử dụng histogram để điều tra độ trễ ứng dụng thực tế.

## 1. Histogram diễn tả điều gì?

Giả sử đo thời gian của 10 request tạo đơn (mỗi số là một mẫu, đơn vị ms):

~~~text
40, 55, 80, 90, 120, 150, 200, 270, 420, 1800
~~~

Trung bình là **322,5 ms**, nhưng có 9 request dưới 500 ms và một request rất chậm ở 1.800 ms. Nếu chỉ theo dõi average, đội vận hành khó biết phần đuôi phân bố đã thay đổi thế nào.

Histogram chia trục giá trị thành các **bucket** có ranh giới xác định. Với các mốc 100, 300 và 500 ms:

| Khoảng không chồng lấn | Số request trong khoảng | Số tích lũy đến mốc |
| --- | ---: | ---: |
| ≤ 100 ms | 4 | 4 |
| (100, 300] ms | 4 | 8 |
| (300, 500] ms | 1 | 9 |
| > 500 ms | 1 | 10 |

Các giá trị ở đây là dữ liệu giả định được dùng xuyên suốt phần lý thuyết. Một công cụ khác có thể chọn ranh giới bucket khác, làm thay đổi chi tiết phân bố được quan sát.

**Bucket tích lũy** có nghĩa là bucket ≤ 300 ms đã **bao gồm cả** những request ≤ 100 ms. Vì vậy các giá trị tích lũy luôn không giảm khi ranh giới tăng. Không được cộng tất cả các bucket tích lũy để tính tổng số request, vì như vậy sẽ đếm một request nhiều lần.

~~~mermaid
flowchart LR
    A["10 lần đo thời gian"] --> B["≤ 100 ms: 4"]
    A --> C["≤ 300 ms: 8"]
    A --> D["≤ 500 ms: 9"]
    A --> E["+Inf: 10"]
    B -. "Có trong" .-> C
    C -. "Có trong" .-> D
    D -. "Có trong" .-> E
~~~

Trong **classic histogram của Prometheus**, mỗi bucket có nhãn `le` (*less than or equal*): `le="0.1"` nghĩa là giá trị không vượt quá **0,1 giây**. Bucket `le="+Inf"` chứa tổng số mẫu của toàn phân bố, tương đương bộ đếm `_count` trong điều kiện dữ liệu nhất quán. Đối với timer, Micrometer thường xuất đơn vị thời gian cơ sở của Prometheus là **giây**, dù trong mã Java ta có thể ghi nhận `Duration.ofMillis(100)`.

### 1.1. Những thành phần thường có trong một classic histogram

Với metric thời gian `http.server.requests` được xuất sang Prometheus, một lần scrape có thể có dạng minh họa:

~~~text
http_server_requests_seconds_bucket{method="POST",uri="/orders",le="0.1"} 4
http_server_requests_seconds_bucket{method="POST",uri="/orders",le="0.3"} 8
http_server_requests_seconds_bucket{method="POST",uri="/orders",le="0.5"} 9
http_server_requests_seconds_bucket{method="POST",uri="/orders",le="+Inf"} 10
http_server_requests_seconds_count{method="POST",uri="/orders"} 10
http_server_requests_seconds_sum{method="POST",uri="/orders"} 3.225
~~~

Đây là **đầu ra giả lập** đã giản lược nhãn và ranh giới để dễ đọc; nó không phải bản scrape nguyên văn của Spring Boot. Trong thực tế còn có thể có status, outcome, instance, application và nhiều bucket khác. Tổng thời gian `_sum` bằng **3,225 giây** vì 10 mẫu cộng lại là 3.225 ms.

- `_bucket{le="..."}`: bộ đếm số quan sát có giá trị không vượt ngưỡng đó.
- `_count`: tổng số lần quan sát.
- `_sum`: tổng các giá trị, đơn vị tương ứng; với timer Prometheus thường là giây.
- `+Inf`: bucket không giới hạn trên, bảo đảm giá trị lớn hơn mốc cao nhất vẫn được đếm.

Bucket, count và sum thường là các bộ đếm tích lũy theo thời gian của một process. Khi phân tích tỷ lệ trong một cửa sổ như 5 phút, dùng `rate(...)` hoặc `increase(...)`, không lấy các giá trị thô từ những process có thời điểm khởi động khác nhau để so sánh.

> Phần này nói về **classic histogram với chuỗi `_bucket`**. Prometheus còn hỗ trợ **native histogram** với biểu diễn và cách truy vấn khác. Không áp dụng nguyên xi mọi câu lệnh dành cho classic histogram nếu hệ thống đang xuất hoặc lưu native histogram.

## 2. Histogram khác average, percentile và summary như thế nào?

| Cách biểu diễn | Trả lời tốt câu hỏi | Khả năng cộng gộp giữa instance | Hạn chế |
| --- | --- | --- | --- |
| **Count / Sum / Average** | Có bao nhiêu lần, tổng thời gian và trung bình? | Có thể cộng count/sum rồi tính trung bình | Che giấu phần đuôi phân bố |
| **Percentile tính tại client** | p95 của từng instance là bao nhiêu? | Không thể lấy trung bình p95 các instance để có p95 toàn cụm | Phụ thuộc cửa sổ và dữ liệu từng instance |
| **Classic histogram** | Bao nhiêu mẫu nằm dưới các mốc? p95 xấp xỉ là bao nhiêu? | Có thể cộng bucket tương ứng nếu ranh giới bucket tương thích | Phân vị được nội suy, chịu sai số do bucket |
| **Distributed trace** | Một request cụ thể chậm ở bước nào? | Không thay thế thống kê toàn bộ traffic | Trace có thể bị sampling loại bỏ |

**Percentile** (phân vị) được hiểu trực quan như sau: p95 là mốc mà khoảng 95% mẫu không lớn hơn mốc đó. p99 nằm sâu hơn ở phần đuôi. Phân vị hữu ích cho trải nghiệm của nhóm request chậm nhưng **không phải tỷ lệ lỗi** và không tự đo được mục tiêu SLO.

Trong Micrometer:

- `publishPercentiles(0.95, 0.99)` yêu cầu xuất các percentile được tính ở phía ứng dụng theo cơ chế của registry/meter; không nên cộng hoặc lấy trung bình các percentile từ nhiều instance.
- `publishPercentileHistogram()` yêu cầu xuất histogram percentile để backend hỗ trợ (chẳng hạn Prometheus) có thể ước lượng phân vị sau khi cộng gộp bucket.
- `serviceLevelObjectives(...)` tạo thêm bucket tại các ngưỡng nghiệp vụ cần đo; có thể có ích **ngay cả khi không bật toàn bộ percentile histogram**, tùy registry hỗ trợ.

Ví dụ, p95 của instance A bằng 100 ms và p95 của instance B bằng 500 ms **không có nghĩa** p95 toàn cụm bằng 300 ms. Số request và hình dạng phân bố của từng instance có thể rất khác nhau. Để lấy p95 toàn cụm với classic histogram, cộng **tốc độ tăng của từng bucket** có cùng `le` trước, sau đó đưa vào `histogram_quantile`.

### 2.1. Percentile được ước lượng, không phải số đo từng request

Hãy hình dung một histogram chỉ có bucket 100 ms và 1.000 ms. Nếu p95 nằm ở bucket thứ hai, backend biết nó nằm trong khoảng nhưng không biết chính xác các request phân bố thế nào trong khoảng đó; một số hàm như `histogram_quantile` thực hiện **nội suy** để ước lượng giá trị.

Vì vậy:

- Ranh giới càng thưa quanh vùng quan tâm, ước lượng p95/p99 càng kém chi tiết.
- Ranh giới càng dày, số series và chi phí lưu trữ/truy vấn càng tăng.
- Một ngưỡng SLO chính xác, như “không quá 500 ms”, thường nên có **bucket đúng mốc 500 ms** để đo tỷ lệ request đáp ứng mục tiêu thay vì suy đoán từ một percentile.

## 3. Histogram trong Micrometer: Timer và DistributionSummary

Micrometer cung cấp nhiều kiểu `Meter`. Hai kiểu thường liên quan đến histogram là:

| Meter | Đo cái gì | Đơn vị và ví dụ |
| --- | --- | --- |
| `Timer` | Khoảng thời gian của các thao tác **đã hoàn tất** | `http.server.requests`, `orders.checkout.duration` |
| `DistributionSummary` | Phân bố của các giá trị số không nhất thiết là thời gian | Kích thước payload (byte), số item mỗi đơn |

Một `Timer` ghi nhận thời lượng và số lần hoàn tất. Một `LongTaskTimer` phục vụ quan sát số tác vụ đang chạy lâu và thời lượng hiện tại của chúng, phù hợp cho công việc kéo dài nhiều phút/giờ; **đừng thay `Timer` thông thường bằng `LongTaskTimer` chỉ để bật histogram p95**.

### 3.1. Quan hệ với Micrometer Observation

Trong Spring Boot, **Micrometer Observation** có thể kết nối với metrics qua `MeterObservationHandler`. Một Observation quanh thao tác nghiệp vụ có thể tạo Timer phù hợp theo cấu hình convention/handler. Khi đó cấu hình histogram cần nhắm đúng **tên meter** do Observation tạo.

~~~mermaid
flowchart TD
    Request["HTTP request hoặc thao tác nghiệp vụ"] --> Obs["Observation + Convention"]
    Obs --> MeterHandler["MeterObservationHandler / MeterRegistry"]
    MeterHandler --> Timer["Timer: count, sum, buckets"]
    Timer --> Prom["Prometheus scrape hoặc metrics exporter"]
    Prom --> Dashboard["PromQL / SLO dashboard"]
    Obs --> TraceHandler["Tracing handler: spans"]
    TraceHandler --> OTLP["OTLP exporter → Trace backend"]
    Request --> Log["Application logs"]
    OTLP -. "Trace ID" .-> Log
~~~

Đừng đồng thời tạo **manual Timer** và **Observation Timer** cho chính **cùng thao tác, cùng tên và cùng ngữ nghĩa** mà không chủ đích: dữ liệu có thể bị đếm hai lần. Hãy xác định một đường instrumentation làm nguồn đo chính và dùng traces/logs để bổ sung ngữ cảnh.

## 4. Bật histogram cho HTTP trong Spring Boot

Với dòng **Spring Boot 3.x** được quản lý dependency tương thích, có thể dùng Actuator và Prometheus registry:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    runtimeOnly 'io.micrometer:micrometer-registry-prometheus'
}
~~~

Ví dụ cấu hình `application.yml` cho môi trường thử nghiệm:

~~~yaml
spring:
  application:
    name: order-service

management:
  endpoints:
    web:
      exposure:
        include: "health,prometheus"
  metrics:
    distribution:
      percentiles-histogram:
        http.server.requests: true
      slo:
        http.server.requests: 100ms, 300ms, 500ms, 1s
      minimum-expected-value:
        http.server.requests: 1ms
      maximum-expected-value:
        http.server.requests: 5s
~~~

Các thuộc tính trên có vai trò riêng:

- **`percentiles-histogram`:** bật các bucket hỗ trợ backend ước lượng phân vị. Histogram chỉ xuất khi registry hỗ trợ.
- **`slo`:** bổ sung ranh giới 100, 300, **500 ms**, 1 giây để đo trực tiếp số request đáp ứng các mốc quan trọng. Với một số phiên bản/registry, cấu hình cũng có thể được gọi là service-level-objective boundaries.
- **`minimum-expected-value` / `maximum-expected-value`:** định hướng dải ranh giới bucket được sinh ra cho histogram percentile, tránh tạo quá nhiều mốc vô ích. Chúng không phải một quy tắc tự động bỏ request chậm vượt max; `_count` và bucket `+Inf` vẫn phải được hiểu trong ngữ cảnh exporter.
- **`exposure`:** cho phép truy cập `/actuator/prometheus`. Ở production, endpoint này cần được giới hạn mạng và quyền truy cập.

Với dữ liệu HTTP server, tên meter Micrometer thường là `http.server.requests`; Prometheus thường chuẩn hóa thành `http_server_requests_seconds_*`. **Tên chính xác phụ thuộc Spring Boot/Micrometer và cấu hình đang chạy**. Trước khi viết dashboard, xác minh thật ở `/actuator/prometheus`.

### 4.1. Các bước xác minh local

1. Khởi động ứng dụng cùng Prometheus registry.
2. Gửi nhiều request đến `POST /orders` với cả thời gian nhanh và chậm (có thể giả lập bằng một dependency đã stub).
3. Mở `http://localhost:8080/actuator/prometheus`; tìm các series tương ứng `http_server_requests_seconds_bucket`, `_count` và `_sum`.
4. Kiểm tra có bucket `le="0.5"` tương ứng mốc 500 ms đã cấu hình hay không.
5. Xem nhãn `method`, `uri`, `status`, `outcome` thực tế để biết cách lọc truy vấn.

Một lệnh minh họa:

~~~bash
curl -s http://localhost:8080/actuator/prometheus
~~~

Nếu không thấy series của route mong đợi, hãy chắc chắn request đã được gửi, instrumentation HTTP còn bật, meter không bị filter loại bỏ và registry/exporter thực sự hỗ trợ histogram. Việc endpoint trả dữ liệu chưa chứng minh một Prometheus server ở ngoài đã scrape thành công.

### 4.2. Có cần bật histogram cho mọi metric?

Thông thường **không**. Mỗi histogram có nhiều bucket và mỗi bucket lại nhân với mọi tổ hợp tags. Nếu bật toàn cục cho một hệ thống lớn, chi phí metrics có thể tăng mạnh.

Ưu tiên các thao tác ảnh hưởng trải nghiệm người dùng: request HTTP quan trọng, lời gọi dependency có SLO rõ, xử lý message hoặc bước nghiệp vụ cần theo dõi đuôi phân bố. Với các phép đo chỉ cần count hoặc average, một histogram có thể không tạo thêm giá trị.

## 5. Tạo histogram cho một Timer nghiệp vụ

Khi một thao tác không được instrumentation tự động đo theo đúng ranh giới mong muốn, có thể tạo Timer riêng. Ví dụ sau đo **thời gian xác nhận đơn hàng**, không bao gồm toàn bộ request HTTP.

~~~java
package com.example.orders.metrics;

import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.springframework.stereotype.Service;

import java.time.Duration;

@Service
public class CheckoutService {
    private final Timer checkoutTimer;
    private final CheckoutGateway gateway;

    public CheckoutService(MeterRegistry registry, CheckoutGateway gateway) {
        this.gateway = gateway;
        this.checkoutTimer = Timer.builder("orders.checkout.duration")
                .description("Time to confirm an order")
                .tag("operation", "checkout")
                .publishPercentileHistogram()
                .serviceLevelObjectives(
                        Duration.ofMillis(250),
                        Duration.ofMillis(500),
                        Duration.ofSeconds(1))
                .minimumExpectedValue(Duration.ofMillis(1))
                .maximumExpectedValue(Duration.ofSeconds(5))
                .register(registry);
    }

    public void checkout(String checkoutReference) {
        // checkoutReference tuyệt đối không được gắn làm metric tag.
        checkoutTimer.record(() -> gateway.confirm(checkoutReference));
    }
}

interface CheckoutGateway {
    void confirm(String checkoutReference);
}
~~~

Những điểm cần hiểu:

1. `orders.checkout.duration` là tên ổn định cho thao tác nghiệp vụ. Dữ liệu định danh của từng lần gọi không nằm trong tên.
2. `publishPercentileHistogram()` yêu cầu xuất histogram phù hợp với backend; `serviceLevelObjectives(...)` cung cấp các mốc nghiệp vụ.
3. `minimumExpectedValue(...)` và `maximumExpectedValue(...)` định hướng dải bucket của histogram; chọn theo độ trễ dự kiến.
4. `Timer.record(Runnable)` đo thời gian chạy callback; nếu callback ném exception, exception vẫn được truyền ra ngoài sau khi Timer ghi nhận thời lượng.
5. Timer **không tự cung cấp tỷ lệ lỗi** chỉ từ một callback ném exception. Muốn đo lỗi hãy dùng tín hiệu HTTP outcome, counter riêng, observation/tracing error hoặc một cách phân loại outcome phù hợp.

Đây là ví dụ về **manual Timer**. Nếu ứng dụng đã có custom `Observation` với metrics handler cho chính `orders.checkout.duration`, hãy chọn một cơ chế đo thống nhất để tránh đếm hai lần. Với ứng dụng nhiều thao tác, tạo `Timer` và tags một cách nhất quán qua `MeterRegistry` hoặc `MeterBinder` có thể thuận tiện hơn.

### 5.1. Khi nào dùng DistributionSummary?

Đối với một giá trị số như kích thước payload tính bằng byte, dùng `DistributionSummary`:

~~~java
import io.micrometer.core.instrument.DistributionSummary;
import io.micrometer.core.instrument.MeterRegistry;

DistributionSummary payloadSize = DistributionSummary
        .builder("orders.request.payload")
        .baseUnit("bytes")
        .description("Incoming order payload size in bytes")
        .publishPercentileHistogram()
        .serviceLevelObjectives(1024, 4096, 16384)
        .register(registry);

payloadSize.record(2048);
~~~

Ở đây `registry` là một `MeterRegistry` được inject hoặc cung cấp từ ứng dụng. Giá trị `2048` có nghĩa 2.048 byte. Đừng dùng Timer để đo byte, hoặc dùng DistributionSummary để đo thời gian khi Timer là lựa chọn phù hợp hơn. Đối với những con số rất lớn hoặc rất nhỏ, có thể cần cấu hình `scale`, expected-value range và bucket phù hợp để tối ưu histogram.

## 6. Đọc histogram bằng PromQL

Các ví dụ dưới đây dành cho **Prometheus classic histogram** được xuất từ HTTP timer. Giả định:

- Meter HTTP có tên Prometheus `http_server_requests_seconds`.
- Route cần đo được chuẩn hóa thành `uri="/orders"` và có `method="POST"`.
- Histogram đã được bật; hệ thống có đủ request để ước lượng phân vị.
- Có bucket ở `le="0.5"` vì đã cấu hình mốc 500 ms.

Luôn điều chỉnh label theo dữ liệu thật, và dùng **cùng phạm vi request** khi tính tử số/mẫu số của SLI.

### 6.1. Lưu lượng request mỗi giây

~~~promql
sum(
  rate(http_server_requests_seconds_count{
    method="POST", uri="/orders"
  }[5m])
)
~~~

`_count` tăng khi có thêm request được ghi nhận. `rate(...[5m])` tính tốc độ tăng trung bình mỗi giây trong 5 phút, có xét trường hợp bộ đếm reset sau restart. Có thể dùng `increase(...[5m])` khi cần ước lượng số lần trong một cửa sổ.

### 6.2. Độ trễ trung bình

~~~promql
sum(rate(http_server_requests_seconds_sum{
  method="POST", uri="/orders"
}[5m]))
/
sum(rate(http_server_requests_seconds_count{
  method="POST", uri="/orders"
}[5m]))
~~~

Đầu ra là **giây**. Cần xử lý trường hợp mẫu số bằng 0 trên các dashboard ít lưu lượng. Average hữu ích để theo dõi tổng thời gian phục vụ, nhưng không thay thế phân vị và tỷ lệ request dưới ngưỡng.

### 6.3. p95 toàn bộ instance

~~~promql
histogram_quantile(
  0.95,
  sum by (le) (
    rate(http_server_requests_seconds_bucket{
      method="POST", uri="/orders"
    }[5m])
  )
)
~~~

Diễn giải:

1. `rate(..._bucket[5m])` lấy tốc độ tăng ở **mỗi bucket** của mỗi series.
2. `sum by (le)` cộng các bucket cùng ranh giới trên các instance/status còn trong phạm vi lọc.
3. `histogram_quantile(0.95, ...)` ước lượng p95 bằng các bucket đã cộng.

Muốn p99, thay `0.95` bằng `0.99`. Không tính `avg(p95_instance)` để suy ra p95 toàn cụm. Nếu cần p95 theo route, hãy giữ `uri` khi cộng:

~~~promql
histogram_quantile(
  0.95,
  sum by (le, uri) (
    rate(http_server_requests_seconds_bucket{method="POST"}[5m])
  )
)
~~~

Truy vấn theo route yêu cầu nhãn `uri` có tập giá trị hữu hạn, thường là route template (ví dụ `/orders/{id}`), không phải URL thô có ID động.

### 6.4. Tỷ lệ request hoàn thành trong 500 ms

Giả sử SLI là **tỷ lệ toàn bộ request POST /orders được instrument hoàn thành trong không quá 500 ms**, chưa loại trừ lỗi HTTP theo status. Khi có bucket chính xác `le="0.5"`:

~~~promql
sum(
  rate(http_server_requests_seconds_bucket{
    method="POST", uri="/orders", le="0.5"
  }[30m])
)
/
sum(
  rate(http_server_requests_seconds_count{
    method="POST", uri="/orders"
  }[30m])
)
~~~

Ví dụ kết quả `0.992` tương đương **99,2%** request đáp ứng mốc trong cửa sổ đó. Nếu SLO đặt 99% request ≤ 500 ms, phân số này có thể làm SLI để đánh giá mục tiêu độ trễ.

Nếu SLI chỉ tính request hợp lệ hoặc tách request thành công/thất bại, cần định nghĩa cụ thể rồi **áp dụng cùng bộ lọc** ở tử và mẫu. Nếu muốn kết hợp cả thành công và đúng hạn, một histogram có nhãn outcome/status phù hợp hoặc quy tắc đếm sự kiện riêng cần được thiết kế; không được mặc nhiên coi “nhanh” là “thành công”.

### 6.5. Tại sao không nên dùng p95 một mình để tính SLO?

“p95 dưới 500 ms” và “99% request dưới 500 ms” là **hai cam kết khác nhau**. Một p95 là mốc phân vị; nó không đo chính xác tỷ lệ đạt ngưỡng cố định nếu ranh giới bucket thưa. Với SLO dựa trên tỷ lệ đạt hạn 500 ms, bucket đúng ngưỡng 500 ms thường phù hợp hơn.

Trong thực tế cần quy định cách tính theo cửa sổ 7/28/30 ngày, lưu lượng hợp lệ và phương pháp cảnh báo tiêu thụ error budget. Truy vấn 5 phút hữu ích để chẩn đoán nhưng có thể nhiễu ở dịch vụ ít traffic.

## 7. Chọn bucket như thế nào?

Bucket là một **quyết định thiết kế kỹ thuật** gắn trực tiếp với ngưỡng mà đội vận hành cần trả lời. Có hai tình huống:

1. **SLO cố định:** “99% request hoàn tất trong ≤ 500 ms”. Hãy có bucket **500 ms** chính xác, để đo tỷ lệ đạt ngưỡng.
2. **Phân vị linh hoạt:** cần xem p50, p90, p95, p99 hoặc so sánh nhiều loại request. Bật percentile histogram với dải thời gian phù hợp để backend ước lượng các phân vị.

Ví dụ API dự kiến đa số request từ 20–400 ms nhưng có thể chậm vài giây:

| Vùng thời gian | Mục tiêu | Gợi ý |
| --- | --- | --- |
| 1–20 ms | Phát hiện hoạt động cực nhanh | Chỉ giữ đủ độ phân giải nếu có giá trị |
| 50–300 ms | Phân tích độ trễ thông thường | Bucket dày hơn khi đây là vùng quan tâm |
| 500 ms | SLO nghiệp vụ | Thêm bucket đúng 500 ms |
| 1–5 giây | Phát hiện timeout/retry | Giữ bucket bao phủ phần đuôi |
| > 5 giây | Phát hiện sự kiện cực chậm | Bucket cao nhất và +Inf; xem lại dải nếu thường xuyên xuất hiện |

Với `maximumExpectedValue=5s`, dữ liệu rất chậm vẫn có thể xuất hiện ở `_count`, `_sum` và `+Inf`, nhưng độ phân giải phía đuôi có thể không đủ để tính p99 có ý nghĩa. Không dùng expected-value range như một ngưỡng timeout hay cơ chế loại bỏ request.

### 7.1. Cardinality của histogram

Mỗi bộ nhãn thường tương ứng với **nhiều series**, mỗi ranh giới bucket là một series khác; còn có `_sum` và `_count`. Giả sử:

- 10 route đã chuẩn hóa,
- 3 phương thức HTTP,
- 5 nhóm status/outcome,
- 20 ranh giới bucket,
- 30 instance.

Số **bucket series** theo phép tính sơ bộ có thể là **10 × 3 × 5 × 20 × 30 = 90.000**, trước khi cộng series count/sum và nhãn khác. Đây là mô hình ước lượng, không phải số series cố định Micrometer sẽ tạo trong mọi ứng dụng.

Nếu mỗi route còn chứa order ID hoặc user ID, số tổ hợp có thể tăng theo số request. Vì vậy:

- Dùng route template như `/orders/{id}` thay URL thô.
- Giới hạn nhãn theo tập giá trị nhỏ, có ý nghĩa để phân tích.
- Không đưa email, token, request ID, trace ID, exception message vào low-cardinality labels.
- Chỉ bật histogram cho các meter thực sự cần quan sát phân bố.
- Ước lượng chi phí và đo số series thực tế sau thay đổi cấu hình.

**High-cardinality metadata** có thể hữu ích trong span của distributed trace, nhưng không nên trở thành metric label. Nó vẫn phải tuân thủ bảo mật và chính sách lưu trữ vì có thể được lưu ở trace backend.

## 8. Từ histogram sang traces và logs khi điều tra lỗi

Histogram cho biết một thao tác đang chậm ở mức độ nào, nhưng **không cho biết request cụ thể chậm tại bước nào**. Trong Spring Boot, cần kết hợp metrics với Micrometer Observation, logging tương quan và distributed tracing.

~~~mermaid
sequenceDiagram
    participant Client
    participant Order as order-service
    participant Inventory as inventory-service
    participant Metrics as Metrics backend
    participant Trace as Trace backend
    Client->>Order: POST /orders
    Note over Order: HTTP timer ghi thời lượng
    Order->>Inventory: reserve + traceparent
    Inventory-->>Order: timeout sau 2,4 giây
    Note over Order: Observation và log ghi lỗi
    Order-->>Client: HTTP 503
    Order-->>Metrics: Bucket, count, sum cập nhật
    Order-->>Trace: Gửi spans nếu được sampling giữ
~~~

Giả sử p95 trong 5 phút tăng từ 350 ms lên 1,2 giây:

1. **Xác minh bằng histogram:** xem p95/p99, request rate, tỷ lệ ≤ 500 ms, các route và các phiên bản triển khai. Điều này cho biết mức độ và phạm vi suy giảm.
2. **Tìm dấu vết cụ thể:** mở trace chậm đã được lấy mẫu, xem span HTTP, bước nghiệp vụ và cuộc gọi inventory-service để xác định đâu là đoạn tốn thời gian.
3. **Tra logs:** dùng trace ID/span ID (nếu được logging configuration ghi lại) để tìm nguyên nhân gần như timeout, retry, pool cạn hoặc trạng thái nghiệp vụ.
4. **Kiểm tra phụ thuộc:** so sánh histogram/thời gian gọi downstream, saturation và số lần retry để xác minh đó là xu hướng chứ không chỉ một trace ngoại lệ.
5. **Khắc phục và đo lại:** thay đổi cấu hình, rollback hoặc sửa upstream rồi kiểm tra SLI/SLO quay về phạm vi chấp nhận được.

**Exemplars** là một khả năng của một số backend/registry cho phép gắn tham chiếu trace vào mẫu metric, tạo lối đi từ điểm đo histogram tới trace phù hợp. Tuy nhiên, exemplar không mặc nhiên tồn tại; cần hỗ trợ từ Micrometer registry, tracing, exporter, Prometheus và hệ thống dashboard. Nếu không có exemplar, vẫn có thể tìm trace theo khoảng thời gian, service, route và lỗi, trong giới hạn dữ liệu đã được giữ.

### 8.1. Vì sao có metrics nhưng không có trace?

Tracing có thể lấy mẫu. Với xác suất sampling 10%, phần lớn request sẽ **không được lưu trace**, trong khi metrics vẫn có thể được tổng hợp từ những request được instrument. Ngoài sampling:

- HTTP client hoặc executor không truyền `traceparent`/context khiến trace bị đứt.
- Tracing handler/bridge chưa được cấu hình nên không có span.
- OTLP exporter, Collector hoặc backend lỗi khiến spans không được lưu.
- Dashboard đang tìm sai service name, môi trường hoặc khoảng thời gian.
- Policy lưu trữ khiến trace cũ đã hết hạn.

Đăng ký histogram không tự thiết lập tracing, và tracing không tự thay thế histogram. **Metrics cho xu hướng, traces cho đường đi của từng request, logs cho sự kiện cụ thể.**

## 9. Kiểm thử histogram trong ứng dụng

Kiểm thử nên tập trung vào kết quả có ý nghĩa: Timer ghi đúng số lần, bucket SLO xuất hiện ở exporter, và truy vấn dashboard trả kết quả hợp lý. Không nên viết test chỉ lặp lại implementation của phương thức cấu hình.

### 9.1. Unit test cho Timer với registry trong bộ nhớ

~~~java
import io.micrometer.core.instrument.Timer;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;

import java.time.Duration;
import java.util.concurrent.TimeUnit;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class CheckoutHistogramTest {

    @Test
    void recordsCountAndDuration() {
        try (SimpleMeterRegistry registry = new SimpleMeterRegistry()) {
            Timer timer = Timer.builder("orders.checkout.duration")
                    .tag("operation", "checkout")
                    .publishPercentileHistogram()
                    .serviceLevelObjectives(Duration.ofMillis(100),
                            Duration.ofMillis(500))
                    .register(registry);

            timer.record(Duration.ofMillis(80));
            timer.record(Duration.ofMillis(200));
            timer.record(Duration.ofMillis(800));

            assertEquals(3L, timer.count());
            assertEquals(1080.0,
                    timer.totalTime(TimeUnit.MILLISECONDS), 0.01);
            assertTrue(timer.max(TimeUnit.MILLISECONDS) >= 800.0);
        }
    }
}
~~~

Test này bảo đảm ba mẫu được ghi nhận với tổng 1.080 ms và max ít nhất 800 ms. **SimpleMeterRegistry không phải Prometheus**, vì vậy không dùng test này để khẳng định các series `_bucket` đã được xuất đúng. Để kiểm tra **ranh giới bucket và tên metric xuất ra**, dùng integration test hoặc môi trường có Prometheus registry thực sự và xem kết quả scrape.

### 9.2. Kiểm thử tích hợp trên Spring Boot

Một kịch bản có ích:

1. Cấu hình histogram cho `http.server.requests` và mốc SLO 500 ms.
2. Gửi một tập request nhanh/chậm có kiểm soát tới route được instrument, tránh phụ thuộc vào độ trễ mạng không đoán trước.
3. Xem `/actuator/prometheus` có `_bucket`, `_count`, `_sum` và bucket 0,5 giây với nhãn route chuẩn hóa.
4. So sánh count tăng với số request đã tạo; với nhiều instance, kiểm tra query cộng gộp.
5. Bảo đảm metric label **không chứa** request ID, user ID, trace ID hay dữ liệu nhạy cảm.
6. Trong staging, kiểm tra Prometheus thực sự scrape và dashboard tính được p95 hoặc tỷ lệ ≤ 500 ms.

Nếu dùng Observation để tạo Timer nghiệp vụ, cần xác minh handler đã đăng ký và meter đúng tên. Với phân tích lỗi, kiểm tra riêng rằng HTTP outcome hoặc metric lỗi có được thu thập, vì histogram độ trễ không tự thay thế error-rate metric.

## 10. Những lỗi thường gặp

| Dấu hiệu hoặc sai lầm | Vì sao sai | Hướng xử lý |
| --- | --- | --- |
| Tính trung bình p95 từ các instance | Percentile không cộng gộp theo cách này | Cộng bucket theo `le` rồi dùng `histogram_quantile` |
| Dùng `_bucket` thô làm số request 5 phút | Bucket là counter tích lũy từ lúc khởi động | Dùng `rate` hoặc `increase` theo cửa sổ |
| Cộng các bucket cumulative | Một request bị đếm nhiều lần | Dùng `_count` để lấy tổng, hoặc tính hiệu giữa các bucket |
| Tính p95 nhưng chưa bật histogram | Không có `_bucket` phù hợp | Bật `percentiles-histogram` hoặc cấu hình bucket SLO |
| Đặt ngưỡng 500 ms nhưng không có bucket 0,5 s | Không đo trực tiếp tỷ lệ đạt SLO | Thêm bucket tại ngưỡng SLO |
| Quên đơn vị Prometheus là giây | Ngưỡng SLO bị lệch ×1.000 | Dùng `0.5` cho 500 ms trong truy vấn |
| Tính p95 trên quá ít request | Phân vị biến động và khó diễn giải | Dùng cửa sổ dài hơn, hiển thị request rate cùng p95 |
| Bật histogram cho mọi timer | Nhiều time series, tăng chi phí | Chọn meter cần phân bố và ước lượng cardinality |
| Gắn URL thô hoặc ID vào label | Series tăng theo request | Chuẩn hóa route và giới hạn tập giá trị |
| Bật manual Timer và Observation Timer trùng ngữ nghĩa | Đếm hai lần cùng một thao tác | Chỉ định một nguồn đo chính |
| Có histogram nhưng không thấy trace | Histogram không quyết định sampling/exporter | Kiểm tra tracing bridge, propagation và OTLP pipeline |
| Dùng `maximumExpectedValue` như timeout | Expected range không dừng request | Dùng timeout ở HTTP client/ứng dụng và đo kết quả |
| Áp classic histogram query lên native histogram | Kiểu dữ liệu/truy vấn không tương thích | Xác minh biểu diễn histogram ở backend |

### 10.1. Cẩn thận khi so sánh p95 của hai lần phát hành

Một bản canary nhận ít request hoặc loại request khác có thể có p95 khác biệt dù không có lỗi. Khi so sánh, hãy quan sát request rate, route, loại người dùng (nếu được phân nhóm an toàn), khoảng đo và cấu hình bucket. Hai histogram chỉ nên được cộng khi **ranh giới bucket tương thích**, và một thay đổi bucket giữa các phiên bản cần được đánh giá trước khi triển khai đồng thời.

## 11. Checklist trước khi lên production

| Câu hỏi | Bằng chứng cần có |
| --- | --- |
| Histogram phục vụ quyết định nào? | Đã xác định SLI/SLO hoặc bài toán p95/p99 |
| Ranh giới SLO chính xác chưa? | Có bucket ở ngưỡng mong muốn, ví dụ 500 ms |
| Dải giá trị có phù hợp không? | min/max expected bao phủ độ trễ thực tế quan trọng |
| Cardinality có chấp nhận được không? | Route/tag chuẩn hóa, có ước lượng chi phí |
| Có tránh double instrumentation không? | Không đếm cùng một thao tác hai lần ngoài ý muốn |
| Metric đã xuất đúng chưa? | Thấy bucket/count/sum tại exporter hoặc backend |
| PromQL đã đúng đơn vị và cách cộng chưa? | `rate` trước `sum by(le)`, phân biệt giây/ms |
| SLI có phạm vi request rõ không? | Tử/mẫu lọc nhất quán, có xử lý traffic thấp |
| Logs và traces có hỗ trợ điều tra không? | Có trace ID và span theo cách cấu hình |
| Có hiểu giới hạn sampling không? | Không coi trace vắng mặt là request không chạy |
| Có giám sát exporter và retention không? | Pipeline telemetry có tín hiệu lỗi, quota và cấu hình lưu trữ |

## 12. Bài thực hành: đo độ trễ tạo đơn

**Bối cảnh:** `order-service` (Spring Boot) có `POST /orders`, gọi `inventory-service` và lưu cơ sở dữ liệu. Mục tiêu vận hành là: **ít nhất 99% request hợp lệ hoàn thành trong tối đa 500 ms** trong cửa sổ SLO đã định nghĩa.

**Nhiệm vụ:**

1. Cài Actuator và Prometheus registry, cấu hình histogram cho HTTP server requests với bucket SLO 500 ms.
2. Phát sinh 10 request với thời gian mô phỏng: 40, 55, 80, 90, 120, 150, 200, 270, 420 và 1.800 ms.
3. Tính thủ công số request tích lũy ≤ 100 ms, ≤ 300 ms, ≤ 500 ms và +Inf; giải thích tại sao không cộng các bộ đếm bucket.
4. Xem metric được xuất ở `/actuator/prometheus`; ghi lại tên và các nhãn thật sự của route.
5. Viết PromQL tính request rate, p95 và tỷ lệ request ≤ 500 ms, đảm bảo các truy vấn chỉ xét phạm vi request hợp lệ theo định nghĩa SLI của bạn.
6. Thêm `Timer` cho bước nghiệp vụ không được HTTP timer phản ánh, so sánh thời gian của HTTP server với thời gian của bước đó; tránh đếm trùng.
7. Giả lập `inventory-service` timeout. Xem histogram thay đổi ra sao, tìm trace chậm nếu sampling giữ lại và tra log bằng trace ID.
8. Ước lượng số series tăng khi thêm 2 region, 3 outcome và 10 bucket cho 20 instance. Giải thích tại sao không gắn order ID vào metric label.
9. Đề xuất một dashboard có request rate, p95, tỷ lệ đạt 500 ms, error rate và một liên kết sang traces/logs.

**Gợi ý đối chiếu:** với bộ 10 mẫu ở bước 2, có **4 request ≤ 100 ms**, **8 request ≤ 300 ms**, **9 request ≤ 500 ms**, và **10 request trong +Inf**; tỷ lệ hoàn thành ≤ 500 ms là **90%**. Bộ mẫu nhỏ này chỉ giúp kiểm tra logic, không đại diện cho SLO production. Để đánh giá SLO cần traffic thực, cửa sổ đo đúng và chính sách xử lý request hợp lệ.

## 13. Ghi nhớ

**Histogram** biến một chuỗi giá trị đo thành phân bố theo bucket. Với **Micrometer Timer** hoặc **DistributionSummary**, nó giúp Spring Boot xuất thông tin về độ trễ hoặc giá trị số; Prometheus có thể cộng các classic bucket tương thích rồi tính p95/p99 hay tỷ lệ đáp ứng một ngưỡng SLO.

Ba nguyên tắc quan trọng là **đúng ranh giới bucket**, **đúng cách tính PromQL** và **đúng ngân sách cardinality**. Khi điều tra production, histogram cho biết phạm vi và mức độ chậm, còn traces và logs giúp tìm đường đi và nguyên nhân cụ thể; sự liên kết phụ thuộc context propagation, sampling, exporter và cách cấu hình pipeline quan sát.

**Tài liệu tham khảo:**

- [Micrometer — Histograms and Percentiles](https://docs.micrometer.io/micrometer/reference/concepts/histogram-quantiles.html)
- [Micrometer — Timers](https://docs.micrometer.io/micrometer/reference/concepts/timers.html)
- [Micrometer — Distribution Summaries](https://docs.micrometer.io/micrometer/reference/concepts/distribution-summaries.html)
- [Spring Boot — Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html)
- [Prometheus — Histograms and Summaries](https://prometheus.io/docs/practices/histograms/)
