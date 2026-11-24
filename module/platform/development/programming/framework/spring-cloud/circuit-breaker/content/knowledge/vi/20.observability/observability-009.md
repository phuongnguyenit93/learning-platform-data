# Dashboard và cảnh báo dựa trên tác động phục vụ thực tế

Dashboard Circuit Breaker cần trả lời hai câu hỏi khác nhau: người dùng có đang nhận dịch vụ đúng chất lượng hay không, và cơ chế bảo vệ dependency đang hoạt động như thế nào? Trạng thái `OPEN` là một tín hiệu chẩn đoán quan trọng, nhưng tự nó chưa chứng minh người dùng đang gặp sự cố. Nếu fallback vẫn trả dữ liệu phù hợp và API giữ được SLO, mạch mở có thể đang bảo vệ hệ thống đúng như thiết kế. Ngược lại, breaker vẫn `CLOSED` trong khi độ trễ hoặc tỷ lệ lỗi của API tăng cao cũng là một sự cố cần phát hiện.

Vì vậy, dashboard nên đặt lưu lượng, tỷ lệ request thành công, độ trễ và SLO ở vị trí đầu tiên. Các biểu đồ Circuit Breaker, TimeLimiter, fallback và Bulkhead giúp giải thích nguyên nhân và cách hệ thống phản ứng. Cảnh báo cần ưu tiên tác động phục vụ thực tế, sau đó mới cảnh báo các dấu hiệu nội bộ cần điều tra.

## 1. Xác định SLI và SLO trước khi dựng dashboard

SLI (Service Level Indicator) là chỉ số đo chất lượng phục vụ; SLO (Service Level Objective) là mục tiêu đã thống nhất cho chỉ số đó trong một cửa sổ thời gian. Với một API dùng Circuit Breaker để gọi `inventory-service`, có thể bắt đầu từ các SLI sau:

| SLI | Cách đo | Câu hỏi vận hành |
| --- | --- | --- |
| Tỷ lệ request thành công | Số request hoàn tất theo hợp đồng chia cho tổng request đủ điều kiện | Người dùng có nhận được phản hồi sử dụng được không? |
| Tỷ lệ lỗi phía server | Request 5xx hoặc lỗi phục vụ được định nghĩa trong SLO chia cho tổng request | Bao nhiêu request bị lỗi do hệ thống? |
| Độ trễ | p50, p95, p99 của thời gian xử lý request | Người dùng phải chờ bao lâu? |
| Tỷ lệ request bị timeout | Request hết deadline ở API hoặc dependency | Hệ thống có phản hồi trước thời hạn không? |
| Tỷ lệ fallback | Số lần fallback theo dependency và nguyên nhân | Hệ thống đang dùng dữ liệu thay thế thường xuyên đến mức nào? |

Ví dụ, API đặt mục tiêu 99,9% request đủ điều kiện thành công trong 30 ngày và p95 dưới 800 ms. Đây chỉ là mục tiêu minh họa. Hãy thống nhất cách tính request đủ điều kiện, cách phân loại lỗi nghiệp vụ 4xx, timeout và phản hồi fallback trước khi tạo dashboard. Một phản hồi fallback có thể là thành công theo hợp đồng của API hoặc có thể là phản hồi suy giảm; đừng mặc định mọi fallback đều là thành công hay đều là lỗi.

Với luồng tồn kho, nếu cache trả dữ liệu cũ nhưng vẫn được nghiệp vụ chấp nhận trong tối đa 60 giây, SLI có thể tính phản hồi đó là thành công có điều kiện và dashboard phải hiển thị riêng tỷ lệ dữ liệu stale. Nếu dữ liệu cũ không an toàn, phản hồi `unavailable` cần được tính vào lỗi phục vụ hoặc một SLI suy giảm riêng. Quy tắc phải xuất phát từ hợp đồng nghiệp vụ.

## 2. Thu thập metrics từ Spring Boot và Resilience4j

Spring Boot Actuator tích hợp Micrometer và có thể xuất metrics tới nhiều hệ thống. Với Spring Cloud CircuitBreaker dùng Resilience4j, cần Actuator và module `resilience4j-micrometer` để bật auto-configuration cho metrics Resilience4j. Nếu Prometheus scrape trực tiếp ứng dụng, thêm registry Prometheus:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    implementation 'io.github.resilience4j:resilience4j-micrometer'
    runtimeOnly 'io.micrometer:micrometer-registry-prometheus'
}
```

Để expose các endpoint cần thiết trong môi trường quan sát nội bộ:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus
  endpoint:
    health:
      show-details: when_authorized
```

Prometheus đọc dữ liệu tại `/actuator/prometheus`. Endpoint `metrics` hữu ích để kiểm tra tên meter và tag trong quá trình phát triển; endpoint `prometheus` cung cấp định dạng scrape. Chỉ expose các endpoint cần thiết và bảo vệ chúng bằng xác thực, phân quyền và mạng quản trị. Không đưa endpoint quản trị ra Internet công khai.

Spring MVC và Spring WebFlux có metric request server mặc định tên `http.server.requests`. Micrometer chuẩn hóa tên khi xuất Prometheus, thường thành `http_server_requests_seconds_*`. Metric client HTTP có tên `http.client.requests`; nó giúp phân biệt độ trễ request đến API với thời gian gọi dịch vụ phụ thuộc.

Resilience4j Micrometer cung cấp các meter quan trọng sau (tên Micrometer trước khi chuẩn hóa sang Prometheus):

| Meter | Thông tin | Cách dùng trên dashboard |
| --- | --- | --- |
| `resilience4j.circuitbreaker.calls` | Timer cho lời gọi thành công, thất bại và bị bỏ qua; có tag `name` và `kind` | Tốc độ và thời gian lời gọi theo dependency, tách success/failure |
| `resilience4j.circuitbreaker.state` | Gauge trạng thái với tag `state` và `name` | Timeline `CLOSED`, `OPEN`, `HALF_OPEN` theo breaker ID |
| `resilience4j.circuitbreaker.failure.rate` | Gauge tỷ lệ lỗi trong cửa sổ | So sánh với `failureRateThreshold` |
| `resilience4j.circuitbreaker.slow.call.rate` | Gauge tỷ lệ lời gọi chậm | Nhận diện dependency suy giảm trước khi lỗi tăng |
| `resilience4j.circuitbreaker.not.permitted.calls` | Counter lời gọi bị từ chối | Xem số request bị breaker chặn |
| `resilience4j.timelimiter.calls` | Counter theo kết quả, gồm `successful`, `failed`, `timeout` | Phân biệt timeout với lỗi khác |
| `resilience4j.bulkhead.*` | Gauge concurrency, queue, capacity và thread pool tùy loại Bulkhead | Phát hiện cạn sức chứa và hàng đợi tăng |

Prometheus đổi tên meter theo quy ước của registry, ví dụ dấu chấm thành dấu gạch dưới và timer có hậu tố đơn vị. Tên cụ thể còn phụ thuộc phiên bản Micrometer/Resilience4j và loại registry. Trước khi viết PromQL, mở `/actuator/prometheus` hoặc `/actuator/metrics` để xác nhận tên, tag và kiểu metric thực tế của ứng dụng.

## 3. Bật histogram để đo p95 và p99

Để tính percentile có thể tổng hợp giữa nhiều instance trong Prometheus, cần histogram bucket. Có thể bật histogram và đặt các bucket SLO cho request server:

```yaml
management:
  metrics:
    distribution:
      percentiles-histogram:
        http.server.requests: true
      slo:
        http.server.requests: 100ms, 300ms, 500ms, 800ms, 1s, 2s
```

`percentiles-histogram` tạo bucket có thể tổng hợp giữa các instance; `slo` thêm các bucket ở ranh giới mục tiêu đã chọn. Histogram có chi phí lưu trữ và số chuỗi metric tăng theo số tag, nên chỉ bật cho các meter thực sự cần và giữ tag có cardinality thấp.

Ví dụ PromQL tính p95 trên request server:

```promql
histogram_quantile(
  0.95,
  sum by (le) (
    rate(http_server_requests_seconds_bucket{job="order-service", uri!~"/actuator.*"}[5m])
  )
)
```

Query trên minh họa cách tính p95 tổng hợp. Có thể thêm `uri`, `method`, `region` hoặc `status` vào `by (...)` khi cần phân rã. Hãy dùng URI template như `/orders/{id}` thay vì URL chứa ID thực tế. Nếu histogram chưa được bật hoặc tên metric khác, query sẽ không có dữ liệu; xác minh scrape trước khi dùng nó làm cảnh báo.

## 4. Bố cục dashboard theo thứ tự điều tra

Một dashboard hữu ích dẫn người trực từ tác động của khách hàng tới nguyên nhân kỹ thuật. Nên chia thành các hàng sau:

### Hàng 1 — Sức khỏe phục vụ người dùng

- Request rate theo giây, tách theo route quan trọng.
- Tỷ lệ 2xx/3xx, 4xx và 5xx theo cách phân loại của sản phẩm.
- p50, p95 và p99 latency của API; đánh dấu ngưỡng SLO.
- Tỷ lệ request timeout hoặc deadline bị vi phạm.
- SLO attainment và error budget còn lại trong cửa sổ 7/30 ngày.

Đây là hàng mặc định khi mở dashboard. Người trực phải thấy ngay có sự cố ảnh hưởng khách hàng hay không, phạm vi endpoint nào và bắt đầu từ lúc nào.

### Hàng 2 — Tác động của fallback

- Số lần fallback theo dependency và reason: `dependency_error`, `timeout`, `circuit_open`, `bulkhead_full`.
- Tỷ lệ phản hồi dùng cache hoặc dữ liệu stale; tuổi dữ liệu cache p95/max.
- Số fallback thất bại hoặc không có dữ liệu dự phòng.
- Số request bị trả `503`, `504` hoặc trạng thái suy giảm theo hợp đồng API.

Fallback có thể giữ API hoạt động trong lúc dependency lỗi. Dashboard cần cho thấy fallback có đang bảo vệ khách hàng thành công hay chỉ che một lỗi bằng dữ liệu không còn đáng tin cậy.

### Hàng 3 — Circuit Breaker theo dependency

- Trạng thái `CLOSED`, `OPEN`, `HALF_OPEN` theo breaker ID, hiển thị dưới dạng timeline.
- Failure rate và slow-call rate so với ngưỡng cấu hình.
- Lời gọi thành công/thất bại theo phút và latency của từng dependency.
- Số lời gọi bị từ chối (`not permitted`) và thời điểm chuyển trạng thái.
- Thời gian ở `OPEN`, số lần mở lại sau `HALF_OPEN` và kết quả probe.

Đặt tên breaker có ý nghĩa như `inventory`, `payment` hoặc `profile`, thống nhất với ID trong cấu hình và mã nguồn. Không gộp tất cả dependency vào một đường tổng nếu cần điều tra một dịch vụ cụ thể.

### Hàng 4 — Timeout, Retry và Bulkhead

- Timeout count và timeout rate theo dependency.
- Retry attempts, retry exhaustion và tổng số request phát sinh do retry.
- Semaphore đang sử dụng so với giới hạn concurrency.
- Thread-pool Bulkhead: active threads, queue depth, queue capacity và rejection.
- HTTP client connection pool: connection đang dùng, chờ, timeout và lỗi kết nối nếu client cung cấp metrics.

Những biểu đồ này giúp phân biệt dependency chậm, pool cạn, timeout quá ngắn và retry khuếch đại tải. Nếu queue tăng trong khi p95 tăng, tăng queue capacity có thể làm request chờ lâu hơn thay vì giải quyết nguyên nhân.

### Hàng 5 — Tài nguyên và thay đổi triển khai

- JVM heap, GC pause, thread count và CPU.
- Connection pool, executor pool và event-loop saturation nếu có.
- Phiên bản ứng dụng, vùng triển khai và annotation thời điểm deploy.
- Lỗi theo instance/pod để phát hiện một node bất thường.

Đặt annotation deployment, cấu hình hoặc sự cố dependency trên cùng trục thời gian với latency và error rate. Điều này giúp xác định sự cố bắt đầu sau một thay đổi cụ thể.

## 5. Ví dụ PromQL cho các panel chính

Ví dụ dưới đây giả định Prometheus scrape ứng dụng với `job="order-service"`, Spring Boot xuất metric HTTP chuẩn và tag `status` có mặt. Thay label bằng label thực tế của môi trường.

**Tốc độ request:**

```promql
sum(rate(http_server_requests_seconds_count{job="order-service", uri!~"/actuator.*"}[5m]))
```

**Tỷ lệ 5xx:**

```promql
sum(rate(http_server_requests_seconds_count{job="order-service", status=~"5..", uri!~"/actuator.*"}[5m]))
/
clamp_min(sum(rate(http_server_requests_seconds_count{job="order-service", uri!~"/actuator.*"}[5m])), 0.001)
```

**Số lời gọi Circuit Breaker thất bại theo ID:**

```promql
sum by (name) (rate(resilience4j_circuitbreaker_calls_seconds_count{kind="failed"}[5m]))
```

**Tỷ lệ lỗi Circuit Breaker theo ID:**

```promql
sum by (name) (rate(resilience4j_circuitbreaker_calls_seconds_count{kind="failed"}[5m]))
/
clamp_min(
  sum by (name) (rate(resilience4j_circuitbreaker_calls_seconds_count{kind=~"failed|successful"}[5m])),
  0.001
)
```

**Breaker đang OPEN:**

```promql
max by (name) (resilience4j_circuitbreaker_state{state="open"})
```

Với gauge trạng thái Resilience4j, giá trị `1` biểu thị trạng thái có hiệu lực và các state còn lại có thể là `0`. Hãy xác nhận semantics của metric trong phiên bản đang dùng. Đừng cộng các gauge state với nhau rồi diễn giải thành số request.

**Request p95:** dùng query `histogram_quantile` ở phần histogram. Khi cần phân rã theo route, thêm `uri` vào cả `sum by (le, uri)` và giữ cùng bộ lọc giữa các panel.

Metric Resilience4j `calls` là timer và Prometheus thường xuất các chuỗi `_count`, `_sum`, `_max` hoặc histogram bucket tùy cấu hình. Nếu tên `resilience4j_circuitbreaker_calls_seconds_count` không tồn tại, tra meter gốc tại Actuator và xem scrape output; không tạo cảnh báo dựa trên một tên đoán.

## 6. Ghi nhận fallback bằng custom metric

Resilience4j cung cấp metrics cho trạng thái và kết quả lời gọi, nhưng ứng dụng thường cần biết fallback đã được dùng vì lý do nào và kết quả đó có được nghiệp vụ chấp nhận hay không. Có thể thêm Counter với các tag có tập giá trị hữu hạn:

```java
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.stereotype.Component;

@Component
public class FallbackMetrics {
    private final MeterRegistry meterRegistry;

    public FallbackMetrics(MeterRegistry meterRegistry) {
        this.meterRegistry = meterRegistry;
    }

    public void record(String dependency, String reason) {
        meterRegistry.counter(
                "app.fallback.calls",
                "dependency", dependency,
                "reason", reason
        ).increment();
    }
}
```

Gọi `record("inventory", "circuit_open")` tại nhánh fallback tương ứng. Có thể bổ sung counter riêng cho fallback thất bại, cache hit/stale hoặc dữ liệu bị từ chối do quá cũ. Không đưa `sku`, user ID, request ID, exception message hoặc URL chứa ID vào metric tag; các giá trị này tạo cardinality rất lớn và có thể làm hệ thống monitoring quá tải. Dùng log hoặc trace để tra cứu từng request.

## 7. Thiết kế cảnh báo theo mức tác động

Phân chia cảnh báo theo hành động cần thực hiện:

| Mức | Điều kiện ví dụ | Hành động |
| --- | --- | --- |
| Page / Critical | Tỷ lệ lỗi API vượt ngưỡng SLO liên tục; p95/p99 vi phạm mục tiêu và có đủ lưu lượng; error-budget burn nhanh | Đánh thức người trực, bắt đầu runbook sự cố phục vụ |
| Warning | Breaker của dependency quan trọng mở kéo dài; fallback tăng mạnh; timeout hoặc Bulkhead rejection tăng nhưng API vẫn giữ SLO | Điều tra trong giờ làm việc hoặc theo lịch trực |
| Info | Một lần chuyển `OPEN` ngắn, breaker tự phục hồi, fallback giữ được phản hồi và SLI không suy giảm | Ghi nhận trong dashboard/event log, chưa cần page |

Không page chỉ vì một lần chuyển sang `OPEN`. Breaker mở có thể là hành vi bảo vệ mong muốn; nếu fallback đang phục vụ tốt, page ngay có thể tạo cảnh báo nhiễu. Ngược lại, nếu API trả 5xx hoặc latency vượt SLO, phải cảnh báo dù breaker vẫn `CLOSED`.

Đặt `for` để điều kiện tồn tại đủ lâu trước khi alert firing. Với lỗi phục vụ, dùng cửa sổ ngắn để phát hiện nhanh nhưng thêm điều kiện lưu lượng tối thiểu để tránh báo động do một request đơn lẻ. Ngưỡng bên dưới chỉ là ví dụ; hiệu chỉnh theo SLO, baseline và mức độ quan trọng của endpoint.

## 8. Ví dụ Prometheus alert rules

Ví dụ rule group sau cảnh báo lỗi phía server kéo dài và breaker mở. Cảnh báo `CustomerFacing5xxRateHigh` có severity `page`; cảnh báo breaker chỉ có severity `warning` để người trực kiểm tra tương quan với tác động người dùng:

```yaml
groups:
  - name: order-service-circuit-breaker
    rules:
      - alert: CustomerFacing5xxRateHigh
        expr: |
          (
            sum(rate(http_server_requests_seconds_count{job="order-service",status=~"5..",uri!~"/actuator.*"}[5m]))
            /
            clamp_min(sum(rate(http_server_requests_seconds_count{job="order-service",uri!~"/actuator.*"}[5m])), 0.001)
          ) > 0.05
          and
          sum(rate(http_server_requests_seconds_count{job="order-service",uri!~"/actuator.*"}[5m])) > 1
        for: 10m
        labels:
          severity: page
        annotations:
          summary: "Tỷ lệ HTTP 5xx của order-service tăng cao"
          description: "Hơn 5% request lỗi trong 10 phút và lưu lượng vượt 1 request/giây. Kiểm tra SLI, dependency và fallback."

      - alert: CustomerLatencyP95High
        expr: |
          histogram_quantile(
            0.95,
            sum by (le) (
              rate(http_server_requests_seconds_bucket{job="order-service",uri!~"/actuator.*"}[5m])
            )
          ) > 0.8
        for: 10m
        labels:
          severity: page
        annotations:
          summary: "p95 latency của order-service vượt mục tiêu"
          description: "p95 lớn hơn 800 ms trong 10 phút. Kiểm tra route chậm và thời gian gọi dependency."

      - alert: InventoryCircuitBreakerOpen
        expr: max by (name) (resilience4j_circuitbreaker_state{name="inventory",state="open"}) == 1
        for: 2m
        labels:
          severity: warning
        annotations:
          summary: "Circuit Breaker inventory đang OPEN"
          description: "Kiểm tra failure rate, slow-call rate, timeout, fallback và SLI của order-service."
```

Trong ví dụ, 5% lỗi, 1 request/giây, 800 ms và các khoảng `for` là ngưỡng minh họa. Cảnh báo p95 yêu cầu histogram bucket đã được bật. Nếu endpoint có lượng request rất thấp, điều kiện lưu lượng tối thiểu nên được thiết kế riêng cho endpoint đó; nếu SLO dùng latency theo từng route, phân nhóm query theo `uri` thay vì gộp toàn ứng dụng.

Alert `InventoryCircuitBreakerOpen` chỉ báo tình trạng nội bộ. Người trực cần mở dashboard để kiểm tra tỷ lệ lỗi API, latency, fallback và dữ liệu cache trước khi quyết định page. Có thể đổi severity hoặc thêm routing theo chính sách vận hành của tổ chức.

## 9. Cảnh báo theo error budget và burn rate

Nếu tổ chức quản lý SLO theo error budget, nên bổ sung cảnh báo burn rate thay vì chỉ dùng một ngưỡng 5xx cố định. Với SLO availability 99,9%, error budget là 0,1% request đủ điều kiện. Burn rate cho biết tốc độ tiêu thụ budget so với tốc độ cho phép:

```text
burn_rate = observed_error_ratio / allowed_error_ratio
```

Ví dụ, error ratio 1,44% với budget 0,1% tương ứng burn rate 14,4 lần. Nếu tốc độ này duy trì, budget sẽ cạn nhanh hơn nhiều so với kế hoạch. Thực tế nên dùng nhiều cửa sổ thời gian: cửa sổ ngắn để phát hiện sự cố lớn và cửa sổ dài để tránh page vì một đợt nhiễu ngắn.

```promql
(
  sum(rate(http_server_requests_seconds_count{job="order-service",status=~"5.."}[5m]))
  /
  clamp_min(sum(rate(http_server_requests_seconds_count{job="order-service"}[5m])), 0.001)
) / 0.001 > 14.4
```

Query minh họa burn rate tức thời với SLO 99,9%; cần ghép thêm cửa sổ dài, điều kiện lưu lượng và bộ lọc request đủ điều kiện trước khi dùng làm page rule. Không sao chép ngưỡng này nếu SLO, loại lỗi hoặc cửa sổ đánh giá của sản phẩm khác.

## 10. Cardinality, sampling và chất lượng dữ liệu

Dashboard có thể sai hoặc tốn kém nếu metrics được gắn tag thiếu kiểm soát:

- Dùng `uri` theo route template, không dùng URL thực có ID.
- Dùng breaker ID, dependency, region, environment và version là các tag có tập giá trị hữu hạn.
- Không gắn user ID, order ID, token, query string hoặc exception message vào tag.
- Không tạo meter name mới cho mỗi request; dùng một meter ổn định với tag có giới hạn.
- Kiểm tra scrape target đang up, timestamp cập nhật, số sample và missing series trước khi kết luận dịch vụ không có lỗi.
- Nếu histogram quá lớn, giới hạn số route quan trọng hoặc chỉ bật bucket cho các meter cần tính SLO.

Metrics là dữ liệu tổng hợp. Khi cần điều tra một request cụ thể, dùng distributed trace và log có correlation ID. Không thay metrics bằng log event; metrics phù hợp để phát hiện xu hướng và cảnh báo, trace/log phù hợp để tìm nguyên nhân một request.

## 11. Runbook khi cảnh báo kích hoạt

Khi nhận page về lỗi phục vụ:

1. Xác nhận phạm vi: endpoint nào, vùng nào, tỷ lệ request lỗi/latency và thời điểm bắt đầu.
2. So sánh với SLO và error budget; kiểm tra có đủ traffic hay cảnh báo phát sinh từ một số ít request.
3. Mở hàng fallback và Circuit Breaker để xem dependency nào đang `OPEN`, tỷ lệ not-permitted, timeout, slow call và fallback reason.
4. Kiểm tra dữ liệu fallback có còn mới và đúng hợp đồng nghiệp vụ không; xem cache hit, tuổi dữ liệu và số fallback thất bại.
5. Kiểm tra Bulkhead queue, thread pool, HTTP connection pool, JVM, GC và CPU để phát hiện nghẽn ở ứng dụng.
6. Đối chiếu thời điểm deploy, thay đổi cấu hình, lỗi mạng hoặc sự cố của dependency.
7. Áp dụng hành động theo runbook của dịch vụ: giảm tải, rollback, điều chỉnh traffic, phục hồi dependency hoặc chuyển sang nguồn dữ liệu dự phòng đã được phê duyệt.
8. Sau khi phục hồi, xác nhận SLI trở lại mục tiêu, breaker đóng ổn định, fallback giảm và không còn queue/tác vụ tồn đọng.

Với cảnh báo breaker mở nhưng SLI vẫn tốt, kiểm tra fallback và theo dõi dependency; không tự động đóng cưỡng bức Circuit Breaker chỉ để làm dashboard xanh. Việc ép đóng mạch có thể đưa tải trở lại một dependency chưa phục hồi.

## 12. Checklist nghiệm thu dashboard và cảnh báo

- Dashboard mặc định hiển thị request rate, error ratio, p95/p99 và SLO trước trạng thái breaker.
- Có thể drill down từ API tới dependency và breaker ID.
- Hiển thị riêng `OPEN`, `HALF_OPEN`, not-permitted, timeout, fallback và Bulkhead rejection.
- Có dữ liệu về chất lượng và tuổi của fallback/cache.
- Histogram được bật cho các route cần percentile/SLO; PromQL trả dữ liệu có ý nghĩa.
- Alert page gắn với tác động người dùng hoặc burn rate; alert breaker đơn lẻ ở mức warning/info.
- Rule có `for`, điều kiện traffic phù hợp, summary, description và hướng dẫn runbook.
- Endpoint Actuator được expose có kiểm soát và bảo vệ.
- Metric tags không chứa ID người dùng hoặc giá trị có cardinality cao.
- Đã thử tạo lỗi, timeout, breaker OPEN, fallback và phục hồi để xác nhận dashboard/alert hoạt động.

## Tài liệu tham khảo

- [Spring Cloud CircuitBreaker – Collecting Metrics](https://docs.spring.io/spring-cloud-circuitbreaker/reference/spring-cloud-circuitbreaker-resilience4j/collecting-metrics.html): dependency Actuator, `resilience4j-micrometer` và auto-configuration metrics.
- [Resilience4j – Micrometer](https://resilience4j.readme.io/docs/micrometer): meter Circuit Breaker, TimeLimiter, Bulkhead và Prometheus export.
- [Spring Boot – Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html): Micrometer, HTTP server metrics, histogram, SLO buckets và Prometheus endpoint.
- [Spring Boot – Actuator Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html): exposure và kiểm soát truy cập endpoint.
- [Prometheus – Alerting Rules](https://prometheus.io/docs/prometheus/latest/configuration/alerting_rules/): PromQL alert expression, `for`, labels và annotations.
