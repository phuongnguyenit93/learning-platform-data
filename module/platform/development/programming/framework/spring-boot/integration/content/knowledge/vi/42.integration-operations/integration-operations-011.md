# Cảnh báo dựa trên lỗi kéo dài, độ trễ và tồn đọng công việc

## 1. Bài toán vận hành tích hợp: ứng dụng còn sống nhưng công việc không tiến triển

Trong một dịch vụ **Spring Boot Integration**, một request HTTP có thể tạo đơn hàng, ghi dữ liệu vào PostgreSQL, lưu outbox, phát thông điệp tới Kafka và chờ một consumer ở dịch vụ khác xử lý. Một adapter khác có thể gọi API đối tác, làm mới Redis hoặc xử lý tác vụ định kỳ. Mỗi bước có cơ chế lỗi, retry, timeout và giao dịch riêng.

Một ứng dụng báo `/actuator/health = UP` vẫn có thể gặp những tình huống nghiêm trọng:

- Kafka consumer còn kết nối nhưng **không xử lý được** record vì lỗi database lặp lại.
- HTTP client thất bại 20 phút liên tục; retry diễn ra đúng thiết kế nhưng kết quả nghiệp vụ không có.
- Relay outbox vẫn chạy nhưng tốc độ phát chậm hơn tốc độ ghi, làm **hàng đợi tăng và tuổi công việc cũ nhất kéo dài**.
- Một partition Kafka bị kẹt; độ trễ trung bình của những record đã hoàn thành vẫn đẹp.
- Một scheduler không tạo việc mới sau đợt triển khai; queue rỗng không có nghĩa hệ thống đang làm đủ việc.

Vì vậy, **cảnh báo vận hành phải nhìn vào kết quả của luồng tích hợp theo thời gian**, đặc biệt là ba nhóm tín hiệu: **lỗi kéo dài**, **độ trễ vượt ngưỡng** và **tồn đọng công việc**. Một lỗi thoáng qua chưa chắc cần đánh thức người trực; một chuỗi retry làm mất thời hạn xử lý hoặc lượng tồn đọng tăng liên tục thì cần được phát hiện sớm.

~~~mermaid
flowchart LR
    HTTP["HTTP / scheduler"] --> DB[("Database")]
    DB --> Outbox[("Outbox PENDING")]
    Outbox --> Relay["Outbox relay"]
    Relay --> Kafka[("Kafka topic")]
    Kafka --> Consumer["Consumer / worker"]
    Consumer --> Target["HTTP đối tác / DB / cache"]
    DB -. "Lỗi / thời điểm tạo" .-> Observe["Metrics + logs + traces"]
    Outbox -. "Backlog + tuổi bản ghi" .-> Observe
    Relay -. "Retry + thời gian phát" .-> Observe
    Consumer -. "Lag + tiến độ + kết quả" .-> Observe
    Observe --> Rules["Prometheus / alert rules"]
    Rules --> Oncall["On-call / runbook"]
~~~

**Mục tiêu bài học:** xác định sự cố theo tác động nghiệp vụ; thiết kế metric và ngưỡng phản ánh tác động; viết cảnh báo có điều kiện kéo dài, tránh nhiễu; phân biệt lag, backlog và latency; xây runbook, kiểm thử cảnh báo và quan sát được đường đi qua nhiều adapter.

## 2. Từ triệu chứng kỹ thuật đến mức độ ảnh hưởng nghiệp vụ

Trước khi đặt ngưỡng, cần định nghĩa **thành công của một đơn vị công việc**. Với luồng đơn hàng, có thể chọn:

- **Đã nhận:** request được xác thực và lưu bền vững vào database/outbox.
- **Đã chuyển:** message đã được broker chấp nhận.
- **Đã xử lý:** consumer đã cập nhật dữ liệu đích thành công và commit trạng thái/offset theo thiết kế.
- **Đã hoàn tất nghiệp vụ:** trạng thái cuối cùng đáp ứng hợp đồng với người dùng hoặc đối tác.

Các mốc không tương đương nhau. Response HTTP 202 cho biết ứng dụng **đã nhận công việc** nếu contract quy định như vậy, không chứng minh downstream đã hoàn tất. Kafka producer nhận ack không có nghĩa consumer đã xử lý; commit offset không chứng minh mọi tác dụng phụ ngoài Kafka đều đã thực hiện đúng một lần.

Ví dụ SLO (Service Level Objective) cho một luồng cụ thể:

> Trong một cửa sổ đánh giá, ít nhất **99,5% công việc hợp lệ** được hoàn tất đúng trạng thái nghiệp vụ trong **5 phút** kể từ thời điểm được nhận bền vững.

Đây là **SLO minh họa**, không phải ngưỡng mặc định cho mọi hệ thống. Muốn đo đúng, phải xác định các điểm sau:

| Thành phần SLO | Cần định nghĩa rõ |
|---|---|
| Đơn vị đếm | Một `businessOperationId`/event hợp lệ, không đếm mỗi retry là công việc mới |
| Điểm bắt đầu | Thời điểm công việc được lưu bền vững vào outbox/job store |
| Điểm kết thúc | Trạng thái đích đã commit và được phép coi là hoàn tất |
| Deadline | 5 phút tính từ điểm bắt đầu, có chủ đích kinh doanh |
| Thành công | Kết quả cuối theo contract, gồm quy tắc xử lý lỗi nghiệp vụ |
| Thất bại | Hết deadline hoặc trạng thái cuối không đạt, kể cả khi retry vẫn đang chạy |
| Ngoại lệ | Công việc bị hủy đúng quy trình, cửa sổ bảo trì, thông điệp không hợp lệ... phải có quy tắc nhất quán |

**Quan trọng:** nếu chỉ đếm record đã hoàn thành, các record đang kẹt trong queue sẽ *không* xuất hiện ở mẫu số và percentile có thể rất tốt dù khách hàng đang chờ. Vì vậy SLO cuối cần đo cả **công việc quá deadline**, còn latency và backlog là các tín hiệu chẩn đoán bổ sung.

## 3. Ba nhóm cảnh báo cốt lõi

| Nhóm | Câu hỏi vận hành | Chỉ số điển hình | Lý do không cảnh báo theo một mẫu tức thời |
|---|---|---|---|
| **Lỗi kéo dài** | Nhiều thao tác đang thất bại liên tiếp hoặc tỷ lệ lỗi có ý nghĩa cao? | Tỷ lệ lỗi terminal, lỗi attempt, số lần retry, DLQ | Một lần timeout có thể tự phục hồi; lượng traffic nhỏ làm tỷ lệ nhiễu |
| **Độ trễ** | Công việc thành công có chậm hơn mục tiêu? Có công việc quá hạn? | p95/p99 end-to-end, thời gian ở từng hop, số quá deadline | Spike ngắn chưa chắc ảnh hưởng SLO; completion-only latency bỏ sót việc kẹt |
| **Tồn đọng** | Công việc tới nhanh hơn tốc độ xử lý hay không còn tiến triển? | Queue depth, oldest pending age, consumer lag, inflight, last progress | Queue tăng khi burst có thể bình thường; queue thấp khi nguồn dừng lại có thể là lỗi |

Một bộ cảnh báo tốt kết hợp **mức độ nghiêm trọng**, **thời gian kéo dài** và **khả năng hành động**. Chỉ số giúp phát hiện “có chuyện gì”; log, trace và runbook hỗ trợ trả lời “vì sao” và “làm gì”.

## 4. Thiết kế metric theo vòng đời một công việc

### 4.1. Chọn tên và nhãn hữu hạn

Ví dụ hệ thống dùng Micrometer và Prometheus, đặt ra những series minh họa:

| Metric dự kiến | Loại | Ý nghĩa |
|---|---|---|
| `integration_operation_completed_total{integration,result}` | Counter | Tổng công việc **đã vào trạng thái cuối**, `result=success/failed`; mỗi business operation đếm một lần |
| `integration_operation_attempts_total{integration,outcome}` | Counter | Mỗi lần thực hiện HTTP/broker/DB attempt, gồm retry |
| `integration_operation_duration_seconds_bucket{integration,le}` | Histogram | Thời gian end-to-end từ khi nhận bền vững đến khi hoàn tất thành công |
| `integration_pending_items{integration}` | Gauge | Số công việc đang chờ xử lý hoặc retry theo snapshot hiện tại |
| `integration_oldest_pending_age_seconds{integration}` | Gauge | Tuổi của công việc pending lâu nhất theo thời điểm hiện tại |
| `integration_inflight_items{integration}` | Gauge | Số công việc đang được worker giữ/đang xử lý |
| `integration_last_progress_timestamp_seconds{integration}` | Gauge | Thời điểm cuối cùng có tiến triển được commit, ở dạng Unix epoch |
| `integration_dead_letter_events_total{integration}` | Counter | Số sự kiện được chuyển tới DLQ/DLT |
| `integration_dead_letter_items{integration}` | Gauge tùy hệ thống | Số công việc chưa được xử lý trong hàng đợi lỗi |

Các tên là **hợp đồng quan sát do ứng dụng chủ động triển khai**, không phải metric tự động luôn có từ Spring Boot. Trong Micrometer thường khai báo tên kiểu `integration.operation.completed`; Prometheus sẽ hiển thị counter dạng `integration_operation_completed_total`. Khi dùng `Timer`, exporter Prometheus có thể xuất `_count`, `_sum`, `_bucket` nếu bật histogram và dùng registry tương ứng.

Giữ label ở tập giá trị có **cardinality thấp**:

~~~text
Nên dùng:
  integration = partner-order-sync | outbox-publish | inventory-consume
  result      = success | failed
  outcome     = success | timeout | rate_limited | server_error

Không đưa vào metric label:
  orderId, eventId, userId, email, requestId,
  URL có tham số động, message payload, SQL statement.
~~~

`traceId`, `businessOperationId` và `eventId` có ích trong **log/trace** để truy vết từng sự kiện; đưa hàng triệu giá trị như vậy vào metric label có thể làm Prometheus quá tải và chi phí observability tăng mạnh.

### 4.2. Phân biệt lỗi attempt và lỗi terminal

Giả sử một công việc gọi API đối tác bốn lần: ba lần trả HTTP 503, lần thứ tư thành công.

- `integration_operation_attempts_total`: tăng **4**, gồm 3 attempt thất bại và 1 thành công.
- `integration_operation_completed_total{result="success"}`: tăng **1**.
- `integration_operation_completed_total{result="failed"}`: **không tăng**.

Nếu cảnh báo dựa trên tỷ lệ lỗi attempt, nó phản ánh **chất lượng dependency** và chi phí retry; nếu dựa trên tỷ lệ lỗi terminal, nó phản ánh **kết quả cuối** mà người dùng nhận được. Hai loại metric phục vụ hai mục tiêu khác nhau. Một consumer retry mãi nhưng chưa vào trạng thái failed sẽ **không tăng lỗi terminal**, vì vậy vẫn cần cảnh báo oldest age và stall.

### 4.3. Phân biệt latency xử lý và latency end-to-end

~~~text
T0:   HTTP nhận, ghi công việc vào DB/outbox
T1:   Worker bắt đầu xử lý
T2:   HTTP đối tác trả kết quả
T3:   DB commit trạng thái thành công

Queue wait       = T1 - T0
Processing time  = T3 - T1
End-to-end delay = T3 - T0
~~~

Nếu chỉ đo `T3 - T1`, API đối tác có thể trả nhanh trong 100 ms, nhưng công việc mất 40 phút chờ trong queue; biểu đồ latency vẫn “xanh” dù SLO 5 phút đã vi phạm. Với giao dịch xuyên nhiều adapter, **end-to-end latency** và **tuổi công việc chưa hoàn thành** thường có ý nghĩa gần hơn với nghiệp vụ.

Chọn đồng hồ và timestamp cẩn thận. Với thời gian trong một process, dùng monotonic clock nếu thư viện hỗ trợ; với end-to-end timestamp lưu qua DB/message, cần đồng hồ được đồng bộ, timezone/UTC nhất quán và kiểm tra dữ liệu timestamp sai. Không âm thầm ghi duration âm vào histogram.

## 5. Thu thập metric với Spring Boot Actuator và Micrometer

### 5.1. Dependency và cấu hình ví dụ

Với dự án Spring Boot quản lý version qua BOM, thêm:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>
    <dependency>
        <groupId>io.micrometer</groupId>
        <artifactId>micrometer-registry-prometheus</artifactId>
        <scope>runtime</scope>
    </dependency>
</dependencies>
~~~

Ví dụ `application.yml` cho môi trường có Prometheus scrape:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,prometheus
  endpoint:
    health:
      probes:
        enabled: true
  metrics:
    tags:
      application: integration-service
~~~

Endpoint `/actuator/prometheus` cần được **bảo vệ bằng network policy/authentication phù hợp** với cách triển khai; không mặc định công khai metric ra Internet. Version Spring Boot và registry có thể thay đổi tên/chi tiết autoconfiguration; cần xem output scrape **thực tế** trước khi đưa tên metric vào alert.

Spring Boot Actuator có metric JVM, HTTP server, connection pool và nhiều thành phần framework. Những metric này hữu ích để giải thích sự cố, nhưng **không thay thế** metric nghiệp vụ như tuổi bản ghi outbox, số job chưa hoàn thành hoặc thời điểm xử lý thành công cuối cùng.

### 5.2. Ghi nhận kết quả từ nghiệp vụ

Ví dụ một adapter chuyên ghi metric sau khi business operation đã chuyển sang trạng thái cuối và **giao dịch lưu trạng thái đã commit**:

~~~java
package example.integration.operations;

import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import java.time.Duration;
import java.time.Instant;
import java.util.Set;
import org.springframework.stereotype.Component;

@Component
public class IntegrationOutcomeMetrics {

    private static final Set<String> KNOWN_INTEGRATIONS =
            Set.of("partner-order-sync", "outbox-publish", "inventory-consume");

    private final MeterRegistry registry;

    public IntegrationOutcomeMetrics(MeterRegistry registry) {
        this.registry = registry;
    }

    public void completedSuccessfully(String integration, Instant acceptedAt) {
        validate(integration);
        registry.counter("integration.operation.completed",
                "integration", integration, "result", "success").increment();

        Duration elapsed = Duration.between(acceptedAt, Instant.now());
        if (!elapsed.isNegative()) {
            Timer.builder("integration.operation.duration")
                    .description("Accepted-to-successful-completion delay")
                    .tag("integration", integration)
                    .publishPercentileHistogram()
                    .register(registry)
                    .record(elapsed);
        }
    }

    public void completedWithFailure(String integration) {
        validate(integration);
        registry.counter("integration.operation.completed",
                "integration", integration, "result", "failed").increment();
    }

    private void validate(String integration) {
        if (!KNOWN_INTEGRATIONS.contains(integration)) {
            throw new IllegalArgumentException("Unknown integration name");
        }
    }
}
~~~

Đây là **minh họa ghi metric**, không phải cơ chế xử lý công việc hoàn chỉnh. Trong hệ thống có retry hoặc nhiều replica, việc đánh dấu hoàn tất phải được điều kiện hóa bằng một chuyển trạng thái **nguyên tử trong DB** (ví dụ `PENDING → SUCCEEDED` hoặc `RUNNING → FAILED`), tránh đếm hai lần khi event được xử lý lại. Nên gọi recorder **sau khi commit thành công** (hoặc phát sự kiện domain sau commit và tiêu thụ an toàn); nếu ghi counter trước commit rồi transaction rollback, metric sẽ báo thành công giả.

Timer thành công không tự đo những operation **vẫn pending** hoặc failed. Vì thế không thể dùng nó làm nguồn duy nhất cho cảnh báo SLO; cần tính công việc quá hạn từ kho trạng thái bền vững. Ở production có thể điều chỉnh histogram buckets theo deadline thực tế; nếu chưa bật histogram hoặc không có bucket phù hợp, `histogram_quantile` sẽ không đo đúng như ví dụ.

### 5.3. Đo backlog và tuổi bản ghi

Với outbox PostgreSQL giả định có `state IN ('PENDING', 'RETRY', 'SENT')` và `created_at`:

~~~sql
SELECT
    COUNT(*) AS pending_items,
    COALESCE(
        EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - MIN(created_at))),
        0
    ) AS oldest_pending_age_seconds
FROM integration_outbox
WHERE state IN ('PENDING', 'RETRY');
~~~

Ý nghĩa:

- `pending_items`: backlog chưa hoàn tất ở snapshot đó.
- `oldest_pending_age_seconds`: công việc cũ nhất đã chờ bao lâu; `0` khi không có bản ghi pending.

Ở hệ thống lớn, truy vấn toàn bảng `COUNT(*)` mỗi lần Prometheus scrape có thể tốn chi phí. Nên **lấy snapshot định kỳ ở worker có giới hạn tần suất**, tối ưu index/truy vấn hoặc dùng nguồn thống kê riêng, rồi cập nhật gauge đã đăng ký. Không chạy blocking SQL trực tiếp từ callback scrape/HTTP event loop; không dùng “giá trị gauge cuối cùng” vô hạn khi lần lấy mẫu đang thất bại. Theo dõi **thời điểm snapshot gần nhất**, báo stale telemetry và không diễn giải gauge cũ như trạng thái hiện tại.

Đối với Kafka, **consumer lag** là số offset chưa được commit/tiến tới tương ứng theo cách exporter tính; nó không tự phản ánh tuổi của message hay số business operation còn thiếu. Có thể lấy metric từ Kafka consumer/client, Spring Kafka/Micrometer hoặc exporter khác, nhưng **tên metric cụ thể tùy nguồn**. Không sao chép một PromQL dùng tên metric của exporter A sang exporter B mà chưa kiểm tra label, semantics, partition và phạm vi group.

## 6. Cảnh báo lỗi kéo dài

### 6.1. Vì sao cần “kéo dài”?

Trong tích hợp HTTP và message broker, timeout ngắn, rebalance, lỗi mạng hoặc HTTP 429 có thể tự phục hồi. Nếu alert mỗi lần có một request thất bại, on-call sẽ nhận nhiều cảnh báo không có hành động cần thiết.

Một quy tắc đáng tin hơn kết hợp:

1. **Tỷ lệ lỗi** trong một cửa sổ thời gian có ý nghĩa.
2. **Mức tải tối thiểu** để tránh 1/1 request thất bại tạo cảnh báo 100%.
3. **Thời gian vi phạm liên tục** qua `for:` trong Prometheus.
4. **Phân loại mức độ ảnh hưởng**: lỗi retry đã tự phục hồi có thể là warning; terminal failures hoặc vi phạm deadline có thể cần page.

Ví dụ: “Tỷ lệ thất bại cuối cùng trên 5% trong cửa sổ 10 phút, có ít nhất 50 operation hoàn tất trong cửa sổ đó, và điều kiện tồn tại thêm 5 phút”. Các con số sau chỉ là **ngưỡng minh họa**; cần điều chỉnh từ SLO, traffic và đặc điểm retry thật.

### 6.2. Quy tắc Prometheus

Các quy tắc dưới đây giả định ứng dụng có xuất đúng series được định nghĩa ở phần 4:

~~~yaml
groups:
  - name: integration-operations
    rules:
      - alert: IntegrationSustainedTerminalFailures
        expr: |
          (
            sum by (integration) (
              rate(integration_operation_completed_total{result="failed"}[10m])
            )
            /
            clamp_min(
              sum by (integration) (
                rate(integration_operation_completed_total[10m])
              ), 1e-9
            )
          ) > 0.05
          and on (integration)
          sum by (integration) (
            increase(integration_operation_completed_total[10m])
          ) >= 50
        for: 5m
        labels:
          severity: page
          team: integrations
        annotations:
          summary: "Tỷ lệ thất bại kéo dài: {{ $labels.integration }}"
          description: "Kiểm tra lỗi terminal, retry, dependency và backlog."
~~~

Diễn giải:

- `rate(...[10m])` lấy tốc độ counter trong 10 phút; tỷ lệ numerator/denominator biểu thị phần công việc hoàn tất với kết quả failed.
- `clamp_min(..., 1e-9)` tránh mẫu số bằng 0; **không** biến việc không có traffic thành lỗi.
- `increase(...[10m]) >= 50` giảm nhiễu ở integration rất ít việc.
- `for: 5m` yêu cầu biểu thức tiếp tục đúng trong thời gian theo chu kỳ evaluation của hệ thống giám sát.

Quy tắc này **không bắt được** luồng không có công việc hoàn tất vì tất cả bị kẹt; lúc đó cần cảnh báo **oldest pending age**, **không có tiến triển** hoặc **mất telemetry**. Với luồng traffic rất thấp, dùng cảnh báo theo “công việc quá deadline” hoặc heartbeat business thay vì bắt buộc có 50 operation.

Đừng lấy `rate(errors)` làm mẫu số nếu chỉ muốn tỷ lệ lỗi; mẫu số phải là **toàn bộ operation hoàn tất** cùng phạm vi integration, contract và thời gian. Nếu các label `integration`, `result`, `environment` không đồng nhất giữa metric, PromQL có thể trả rỗng hoặc gộp nhầm môi trường. Phân tách môi trường qua datasource, label hoặc rule filter rõ ràng.

### 6.3. Lỗi tạm thời và retry storm

Một API đối tác trả 503 nhưng tất cả operation sau đó thành công trước deadline có thể chưa làm hỏng SLO, song retry storm làm quá tải DB, thread pool và đối tác. Cần metric riêng cho **attempt error rate**, số lần retry mỗi job, `429` và circuit breaker open state; có thể tạo warning về lỗi dependency kéo dài hoặc throughput giảm trước khi thành terminal failure.

Một thông điệp không hợp lệ liên tục vào Dead Letter Topic cần thông báo xử lý theo mức độ. Thêm `integration_dead_letter_events_total` và số lượng công việc DLQ chưa được giải quyết; không tự retry vô hạn một payload sai schema mà không có khả năng phục hồi.

## 7. Cảnh báo độ trễ

### 7.1. Độ trễ ở từng hop và end-to-end

Trong chuỗi HTTP → DB → outbox → Kafka → consumer → external HTTP, cần theo dõi:

| Độ trễ | Được đo từ đâu đến đâu | Gợi ý chẩn đoán |
|---|---|---|
| HTTP server | Request đến response | CPU/thread pool, xác thực, DB, timeout |
| JDBC/R2DBC | Bắt đầu truy vấn đến khi có kết quả/commit theo instrument | Lock, connection pool, query chậm |
| Outbox waiting | `created_at` đến thời điểm relay claim | Relay không chạy hoặc worker thiếu năng lực |
| Kafka produce | Bắt đầu gửi đến broker ack | Broker, batch, quota, network, timeout |
| Consumer processing | Nhận record đến trạng thái xử lý/commit | Serialization, DB, API đối tác, retry |
| End-to-end | Nhận bền vững đến kết quả nghiệp vụ cuối | Tổng chờ queue, xử lý, retry và thời gian của các hop |

Đừng cộng các percentile `p95` của từng hop rồi kết luận đó là `p95` end-to-end; percentile không cộng tuyến tính. Cần đo end-to-end trực tiếp và dùng các span/metric theo hop để xác định nguyên nhân.

### 7.2. Ví dụ cảnh báo p95 latency

~~~yaml
groups:
  - name: integration-latency
    rules:
      - alert: IntegrationEndToEndP95High
        expr: |
          histogram_quantile(
            0.95,
            sum by (le, integration) (
              rate(integration_operation_duration_seconds_bucket[10m])
            )
          ) > 120
          and on (integration)
          sum by (integration) (
            increase(integration_operation_duration_seconds_count[10m])
          ) >= 50
        for: 10m
        labels:
          severity: warning
        annotations:
          summary: "Độ trễ p95 cao: {{ $labels.integration }}"
          description: "Kiểm tra thời gian chờ queue, retry và dependency chậm."
~~~

Điều kiện minh họa: **p95 trên 120 giây**, có đủ sample và kéo dài thêm 10 phút. `histogram_quantile` dùng bucket histogram được **cộng theo `le` và `integration`**. Cần giữ `le` khi tổng hợp histogram cổ điển; nếu metric dùng native histogram, cách truy vấn khác.

Hai lưu ý:

1. Histogram từ code ở phần 5 ghi **những operation hoàn tất thành công**. Nếu toàn bộ công việc kẹt, mẫu có thể ít hoặc không có — lúc này phải dựa vào oldest pending age/overdue operations. Không hiểu p95 thấp là bằng chứng mọi công việc đều kịp hạn.
2. Bucket boundary và cửa sổ `rate` phải phù hợp deadline và traffic; ở luồng ít công việc, percentile thường không ổn định. Đối với một hạn xử lý cứng, tỷ lệ **operation quá deadline** có thể sát SLO hơn percentile.

### 7.3. Cảnh báo SLO theo deadline

Giả sử luật nghiệp vụ là hoàn tất trong 5 phút. Nếu mỗi công việc có `accepted_at`, `deadline_at` và trạng thái bền vững, có thể tính **số công việc đang quá hạn**:

~~~sql
SELECT COUNT(*) AS overdue_items
FROM integration_jobs
WHERE state IN ('PENDING', 'RUNNING', 'RETRY')
  AND deadline_at < CURRENT_TIMESTAMP;
~~~

Xuất gauge `integration_overdue_items{integration}` và đặt cảnh báo khi vượt ngưỡng qua nhiều lần lấy mẫu. Đây là tín hiệu trực tiếp hơn cho rủi ro SLO vì bao gồm **công việc chưa hoàn thành**. Nếu cần tính tỉ lệ đạt deadline theo cửa sổ, mẫu số phải dựa trên cohort công việc đã **đến hạn đánh giá**, tránh đếm các job vừa nhận và chưa đủ 5 phút như thất bại.

## 8. Cảnh báo backlog, tuổi công việc và mất tiến triển

### 8.1. Queue depth không đủ

Ví dụ hai thời điểm:

~~~text
12:00  pending = 600, oldest_age = 20 giây
12:05  pending = 700, oldest_age = 8 phút
12:10  pending = 850, oldest_age = 13 phút
~~~

Queue depth tăng là một dấu hiệu, nhưng **oldest age tăng liên tục** chỉ ra rằng một số công việc không được phục vụ trong thời gian dài. Ngược lại, 600 công việc mới tới sau một đợt burst có thể hoàn tất trong vài giây và không đe dọa SLO.

Một quy tắc có thể cảnh báo khi công việc lâu nhất vượt 10 phút:

~~~yaml
groups:
  - name: integration-backlog
    rules:
      - alert: IntegrationPendingWorkTooOld
        expr: |
          (integration_oldest_pending_age_seconds > 600)
          and on (integration)
          (integration_pending_items > 0)
        for: 5m
        labels:
          severity: page
        annotations:
          summary: "Công việc tồn đọng quá lâu: {{ $labels.integration }}"
          description: "Kiểm tra outbox/job store, retry và worker progress."

      - alert: IntegrationBacklogGrowing
        expr: |
          (delta(integration_pending_items[15m]) > 300)
          and on (integration)
          (integration_pending_items > 500)
        for: 10m
        labels:
          severity: warning
        annotations:
          summary: "Backlog tăng liên tục: {{ $labels.integration }}"
          description: "So sánh tốc độ ingress và throughput xử lý."
~~~

`delta` chỉ phù hợp với **gauge**, không dùng cho monotonic counter. Các ngưỡng 600 giây, 300 item/15 phút và 500 item chỉ để minh họa. Điều kiện `for` giảm báo động khi burst ngắn. Nếu application scrape bị mất hoặc gauge không được cập nhật, biểu thức có thể không đánh giá được; cần giám sát **freshness của telemetry** và tính sẵn sàng của nguồn metric.

### 8.2. Không có tiến triển dù backlog tồn tại

Một worker có thể còn process sống, vẫn heartbeat, nhưng không commit được kết quả. Có thể lưu thời điểm cuối cùng **một business operation thật sự được hoàn tất**:

~~~yaml
groups:
  - name: integration-progress
    rules:
      - alert: IntegrationNoProgressWithBacklog
        expr: |
          (integration_pending_items > 0)
          and on (integration)
          (integration_oldest_pending_age_seconds > 900)
          and on (integration)
          (time() - integration_last_progress_timestamp_seconds > 900)
        for: 5m
        labels:
          severity: page
        annotations:
          summary: "Worker không tiến triển: {{ $labels.integration }}"
~~~

**Điều kiện áp dụng:** `integration_last_progress_timestamp_seconds` phải được khởi tạo và cập nhật theo **cùng nguồn trạng thái bền vững**; nếu metric chưa xuất hiện, phép `and` có thể không tạo kết quả. Khi chưa từng có operation thành công, cần một trạng thái khởi tạo hợp lệ hoặc bổ sung cảnh báo quá deadline/missing telemetry. Không dùng thời điểm `@Scheduled` thức dậy làm `last_progress`: một scheduler vẫn thức dậy khi công việc hoàn toàn kẹt.

### 8.3. Kafka lag, consumer group và partition

Kafka consumer lag cần được đọc theo **consumer group + topic + partition**. Chỉ nhìn số lag tổng có thể che mất một partition bị kẹt trong khi các partition khác vẫn xử lý. Đối với một consumer group:

- **Lag count**: khoảng cách giữa offset đã commit/vị trí consumer và head theo định nghĩa cụ thể của exporter; đơn vị là offset, không phải giây.
- **Rate ingress so với rate processing**: backlog tăng khi lượng event mới lớn hơn throughput xử lý.
- **Age of oldest unprocessed**: hữu ích nếu xác định được thời điểm event và offset còn chờ; cần cơ chế đo phù hợp, không suy trực tiếp từ lag count.
- **Last committed progress**: có hay không thay đổi offset/đầu ra nghiệp vụ trong khi partition đang có dữ liệu.
- **Consumer group state/rebalance**: giúp giải thích gián đoạn tạm thời hoặc lỗi phân phối partition.

Đặt ngưỡng khác nhau cho topic thời gian thực, topic batch và topic ít traffic. Với Kafka, số partition, tốc độ producer và đặc điểm message size làm một giá trị lag tuyệt đối khó dùng chung cho mọi integration.

### 8.4. Outbox, DLQ và retry backlog

Một luồng tích hợp có thể có **nhiều hàng đợi liên tiếp**: outbox SQL, Kafka topic, bảng retry, dead-letter queue và công việc chờ đối soát. Nếu dashboard chỉ theo dõi Kafka lag mà outbox relay chưa gửi được message lên broker, Kafka lag vẫn có thể gần **0** trong khi nghiệp vụ đã bị kẹt ở database.

Theo dõi từng ranh giới:

| Ranh giới | Backlog/age cần xem | Lỗi liên quan |
|---|---|---|
| Database outbox → broker | `PENDING` count, oldest age, thời điểm relay publish | Broker unavailable, retry loop, khóa/lease lỗi |
| Broker → consumer | Lag theo group/partition, thời gian chưa có progress | Rebalance, deserialize lỗi, offset không commit |
| Consumer → HTTP đối tác | Số job retry, oldest retry age, 429/5xx/timeout | Rate limit, circuit breaker open, credential lỗi |
| Consumer → database | Inflight, retry, DB connection pool wait | Lock, deadlock, migration không tương thích |
| Consumer → DLQ | Tổng event vào DLQ, số event chưa xử lý, tuổi event | Poison message, contract version sai |
| Scheduler → job store | Slot chưa tạo, job `READY/RUNNING` quá hạn | Scheduler down, claim lease kẹt, nhiều replica |

Một hệ thống cần đánh giá **toàn bộ đường đi** thay vì chỉ một số liệu hạ tầng.

## 9. Alert theo SLO và error budget

Ngưỡng tĩnh như “HTTP 5xx > 5% trong 10 phút” dễ hiểu nhưng không luôn phản ánh tác động đến SLO. Nếu có SLO 99,5% thành công đúng hạn, **error budget** là 0,5% công việc được phép vi phạm trong cửa sổ đánh giá đã định.

**Burn rate** so sánh tốc độ tiêu thụ error budget hiện tại với tốc độ cho phép:

\[
\text{burn rate} =
\frac{\text{tỷ lệ vi phạm SLO quan sát được}}
     {\text{tỷ lệ vi phạm được phép theo SLO}}
\]

Ví dụ minh họa: SLO 99,5% cho phép 0,5% lỗi; nếu tỷ lệ vi phạm quan sát là 5% thì burn rate = 10. Đây là tín hiệu mức độ khẩn cấp: với cùng SLO, tốc độ tiêu thụ budget cao trong cửa sổ ngắn có thể cần page nhanh; tỷ lệ nhỏ nhưng kéo dài nhiều giờ có thể cần điều tra theo mức độ thấp hơn.

Với hệ thống bất đồng bộ, chỉ tính “failed terminal” có thể **đánh giá thấp** vi phạm SLO vì pending quá hạn chưa kết thúc. Để triển khai burn-rate alert, cần xây một **SLI đúng cohort**: mỗi operation được đưa vào mẫu số khi đã đến deadline đánh giá, và có kết quả `within_deadline` hoặc `violated`; retry/duplicate không tăng mẫu số. Sau đó mới tạo các cửa sổ nhanh/chậm phù hợp.

Mẫu cảnh báo multi-window thường có hai cấp:

- **Cấp page:** budget đang bị tiêu thụ nhanh ở **cả cửa sổ ngắn lẫn dài**, khả năng ảnh hưởng lớn và cần hành động sớm.
- **Cấp ticket/warning:** budget tiêu thụ chậm nhưng kéo dài; có thể xử lý trong giờ làm nếu không có ảnh hưởng cấp bách.

Không đưa một công thức burn-rate bất kỳ vào production khi chưa xác định SLI, cửa sổ đánh giá và chi phí cảnh báo. Cần backtest trên lịch sử metric và kiểm tra các trường hợp traffic thấp, downtime, retry, thiếu telemetry.

## 10. Phân cấp cảnh báo và chống nhiễu

| Mức | Khi nào dùng | Ví dụ |
|---|---|---|
| **Page / critical** | Khách hàng đang hoặc sắp chịu tác động nghiêm trọng; cần thao tác ngay | Công việc quá deadline kéo dài, queue rất cũ, không còn progress, lỗi terminal cao |
| **Warning / ticket** | Tín hiệu xấu sớm, cần theo dõi hoặc xử lý theo kế hoạch | Backlog tăng nhưng chưa sát deadline, attempt error rate tăng, DLQ mới có ít message |
| **Dashboard / thông tin** | Dùng chẩn đoán và lập xu hướng; chưa cần tạo alert riêng | Số lần retry ít, dao động p50, CPU/ngắn hạn bình thường |

Để alert có thể hành động:

1. **Có `for` phù hợp:** không đánh thức on-call với spike chỉ kéo dài vài chu kỳ scrape.
2. **Có điều kiện traffic:** rate theo số mẫu hoặc cảnh báo theo deadline cho luồng ít traffic.
3. **Có grouping và dedup:** gom alert theo `environment`, `integration`, mức độ lỗi thay vì một page cho mỗi pod.
4. **Có inhibition/phụ thuộc:** nếu cả broker down, các alert consumer liên quan có thể được nhóm hoặc giảm trùng; vẫn cần giữ tín hiệu về impact nghiệp vụ.
5. **Có silence theo bảo trì đã phê duyệt:** không che sự cố mới vô hạn; rõ phạm vi và thời gian kết thúc.
6. **Có runbook:** định nghĩa ý nghĩa, dashboard/trace liên quan, thao tác khôi phục an toàn và người phụ trách.
7. **Có kiểm tra đường chuyển cảnh báo:** rule đúng nhưng Alertmanager/PagerDuty/nhóm trực không nhận được thì hệ thống vẫn không được bảo vệ.

Phân biệt **alert được resolve** và **sự cố nghiệp vụ đã phục hồi**: tỷ lệ lỗi có thể giảm khi traffic ngừng hẳn, trong khi những job cũ vẫn bị mắc kẹt. Vì vậy các runbook cần kiểm tra số job quá hạn và xác nhận progress thực sự trước khi đóng incident.

## 11. Runbook điều tra khi cảnh báo kích hoạt

Một runbook nên giúp người trực trả lời nhanh ba câu hỏi: **ảnh hưởng đến ai, đang kẹt ở đâu, và bước khôi phục nào an toàn**.

### 11.1. Quy trình điều tra

1. **Xác nhận tác động:** integration nào, môi trường nào, số operation quá hạn, khách hàng/hệ thống liên quan và SLO đang vi phạm.
2. **Xem xu hướng:** biểu đồ lỗi terminal và attempt, p95, pending count, oldest age, ingress/egress rate trước/sau deploy.
3. **Khoanh vùng hop:** outbox SQL có tăng không, Kafka lag theo partition ra sao, consumer commit offset không, HTTP đối tác trả mã gì, DB pool/lock có bất thường không.
4. **Lấy mẫu có tương quan:** dùng `traceId`, `eventId` hoặc `businessOperationId` truy log/trace từ lúc enqueue đến bước cuối; không dựa vào một log error rời rạc.
5. **Kiểm tra bản thay đổi gần nhất:** release, schema migration, credential/token, ACL broker, cấu hình retry/timeout, scale worker và scheduled job.
6. **Khôi phục theo ranh giới an toàn:** sửa credential/route, điều chỉnh capacity, tạm giảm ingress, khôi phục dependency hoặc replay công việc đã được xác minh idempotent.
7. **Xác nhận hồi phục:** oldest age giảm, backlog được tiêu, terminal success tăng, SLO cải thiện và các công việc bị ảnh hưởng được đối soát.

### 11.2. Bảng triệu chứng và cách phân biệt

| Triệu chứng | Nguyên nhân thường gặp | Kiểm tra ưu tiên | Hướng xử lý có kiểm soát |
|---|---|---|---|
| Lỗi attempt tăng, terminal error chưa tăng | API đối tác 429/503, retry hiệu quả một phần | HTTP status, retry count, breaker, deadline | Backoff/jitter, giới hạn concurrency, liên hệ đối tác nếu kéo dài |
| Pending tăng, oldest age tăng | Relay/worker chậm hoặc ngừng | Worker progress, lock, broker ack, DB query | Khôi phục worker/dependency, tăng capacity sau khi xác định bottleneck |
| Kafka lag tăng, outbox thấp | Consumer đang chậm hoặc lỗi | Group/partition lag, rebalance, deserialize, downstream DB/HTTP | Sửa consumer/dependency, điều chỉnh partition/concurrency phù hợp |
| Kafka lag thấp, outbox tăng | Message chưa được publish từ DB | Trạng thái relay, retry, lỗi producer | Khôi phục relay, replay bằng outbox key ổn định |
| p95 tăng, queue ổn định | Xử lý/DB/HTTP chậm | Span theo hop, connection pool, lock, timeout | Tối ưu điểm nghẽn, giữ giới hạn tải |
| p95 đẹp, backlog cũ vẫn tăng | Chỉ job nhanh hoàn tất; job khó bị kẹt | Oldest pending, failed keys, poison message | Tách xử lý poison job, đưa vào quarantine/DLQ hợp lệ |
| Không có metric hoặc không có traffic bất thường | App down, exporter/scrape lỗi, scheduler không tạo việc | `up`, scrape targets, heartbeat nguồn, ingest rate | Khôi phục telemetry; xác minh hệ thống nghiệp vụ riêng |
| DLQ tăng liên tục | Schema contract sai, dữ liệu độc, permission | Exception theo loại, schema version, payload đã ẩn danh | Chặn nguồn lỗi, sửa converter/contract, replay có kiểm soát |

### 11.3. Retry và replay cần idempotency

Khi một consumer chết sau khi đã ghi DB nhưng trước khi commit offset, Kafka có thể phát lại message. Khi relay outbox chết sau khi broker đã ack nhưng trước khi đánh dấu `SENT`, relay có thể gửi lại. **Cảnh báo tồn đọng thường dẫn tới thao tác replay**, vì vậy runbook cần xác minh khả năng xử lý trùng:

- Dùng `eventId`/`operationId` bất biến qua retry; hạn chế phát UUID mới cho cùng ý định nghiệp vụ.
- Ghi dấu xử lý vào database cùng transaction với thay đổi nghiệp vụ; dùng unique constraint hoặc upsert có điều kiện.
- Với HTTP đối tác, sử dụng idempotency key nếu API hỗ trợ; phân biệt timeout “chưa gửi” với timeout “đã được xử lý nhưng chưa nhận response”.
- Không xóa/replay toàn bộ DLQ hoặc tăng concurrency vô hạn chỉ để làm giảm metric backlog, vì có thể tạo tác dụng phụ trùng, tăng tải hoặc mất dấu nguyên nhân.

## 12. Dashboard và truy vết xuyên adapter

Một dashboard vận hành theo **integration**, không chỉ theo pod, có thể bố trí:

| Vùng | Nội dung |
|---|---|
| Tình trạng SLO | Số operation đến hạn, tỷ lệ đúng hạn, error budget, terminal failures |
| Throughput | Ingress per second, completed per second, retry rate, reject rate |
| Thời gian | p50/p95/p99 end-to-end, xử lý HTTP/DB/Kafka, oldest pending age |
| Tồn đọng | Outbox pending, retry backlog, Kafka lag theo group/partition, DLQ |
| Phụ thuộc | HTTP status/timeout theo đối tác, DB pool wait/locks, broker ack latency |
| Worker | Inflight, throughput, last committed progress, restart/rebalance, lease expiry |
| Chẩn đoán | Recent deploy/config changes, trace mẫu, link runbook và trạng thái alert |

Một đường truy vết tốt nối các mốc:

~~~text
HTTP request
  traceId = a1...
  businessOperationId = order-42
    -> DB transaction commits order + outbox(eventId=e-42)
    -> Relay sends Kafka record(key=order-42, eventId=e-42)
    -> Consumer records processing state
    -> External HTTP call / final DB commit
    -> business completion / SLO outcome
~~~

Truyền correlation ID qua message headers khi phù hợp, lưu business ID trong bảng và log, nhưng **không đưa các ID biến thiên vào metric labels**. Khi ghi log, tránh token, credential, email, payload nhạy cảm và thông tin cá nhân. Với tracing, phải hiểu khoảng đứt quãng giữa việc tạo message và consumer xử lý sau nhiều phút; có thể dùng trace links hoặc business correlation để truy vết các giai đoạn bất đồng bộ.

## 13. Kiểm thử các quy tắc cảnh báo trước khi production

Để alert thực sự phát hiện lỗi, chỉ kiểm tra PromQL không có lỗi cú pháp là chưa đủ. Cần thử các mô hình dữ liệu mô phỏng hoặc chạy integration test có gây lỗi và đo metric thật.

### 13.1. Các tình huống nên bao phủ

| Ca kiểm thử | Tình huống đưa vào hệ thống | Kỳ vọng cảnh báo |
|---|---|---|
| Lỗi thoáng qua | HTTP 503 trong vài giây rồi bình thường | Không page; có dữ liệu để chẩn đoán |
| Lỗi kéo dài | Tỷ lệ terminal failed > ngưỡng qua nhiều cửa sổ | Alert fire sau thời gian `for` |
| Traffic rất thấp | 1 trong 1 request thất bại | Không fire rule tỷ lệ có mẫu tối thiểu; theo dõi deadline riêng |
| Retry cuối cùng thành công | Một operation 4 attempt, 3 lỗi, 1 success | Attempt failure tăng, terminal success chỉ +1 |
| Tất cả công việc kẹt | Không có completed, pending age tăng | Backlog/overdue alert fire dù completed error rate bằng 0 |
| Burst lớn nhưng xử lý nhanh | Pending tăng cao trong 1-2 phút rồi giảm | Rule có `for` thích hợp không báo giả |
| Poison message | Một event sai schema lặp lại | Retry hữu hạn, DLQ tăng và có signal để triage |
| Kafka partition kẹt | Một partition không commit, các partition khác vẫn tiến triển | Dashboard phân vùng phơi bày điểm nghẽn |
| Scrape/metrics hỏng | Exporter biến mất hoặc gauge ngừng cập nhật | Có alert riêng về `up`/metric freshness |
| Downstream recovery | HTTP đối tác phục hồi, worker catch-up | Lỗi giảm, oldest age và backlog giảm trước khi đóng incident |
| Duplicate delivery | Replay cùng event ID | Counter operation cuối không đếm lặp, dữ liệu nghiệp vụ không nhân đôi |
| Rolling deployment | Các phiên bản cùng chạy trong lúc deploy | Label ổn định, alert không reset ngoài dự kiến, runbook biết release |

Với Prometheus, có thể dùng **unit test cho alert rules** bằng `promtool test rules` và dữ liệu time series giả lập, kết hợp test thật cho metric exporter/Micrometer. Bài học này chỉ mô tả quy trình kiểm thử; không giả định các quy tắc YAML minh họa đã được cài và chạy trong một hệ thống cụ thể.

### 13.2. Ngữ nghĩa `for`, không có dữ liệu và lần lấy mẫu

`for: 10m` nghĩa là biểu thức phải giữ trạng thái vi phạm qua các lần đánh giá đủ lâu để trở thành firing; nó **không** tự tạo metric nếu exporter im lặng. Nếu integration không phát sinh công việc, `rate` có thể không có mẫu phù hợp. Cần phân biệt:

- **Zero:** có metric được scrape và giá trị thực sự bằng 0.
- **No data:** metric không xuất hiện; có thể do không instrument, target down hoặc quá ít sample.
- **Stale:** metric có nhưng snapshot quá cũ; có thể do sampler kẹt trong khi exporter vẫn sống.

Nên kiểm tra scrape target `up`, timestamp của snapshot backlog, và heartbeat của tác vụ tạo việc khi nguồn dự kiến hoạt động liên tục. Một alert chỉ dựa vào `rate(success)` không fire khi không còn traffic có thể che lỗi scheduler ngừng tạo job.

## 14. Một bộ ngưỡng minh họa cho outbox → Kafka → consumer

Giả sử luồng có mục tiêu hoàn tất trong 5 phút, công việc mới đến đều đặn trong giờ cao điểm và đội trực có thể xử lý sự cố:

| Signal | Ngưỡng khởi đầu minh họa | Mức | Cách xác minh sau kích hoạt |
|---|---|---|---|
| Terminal failure ratio | > 5% trên 10m, ≥50 completed, kéo dài 5m | Page | Lỗi theo integration, dependency và số job quá deadline |
| End-to-end p95 success | > 120s trên 10m có đủ mẫu, kéo dài 10m | Warning | Queue wait vs xử lý và tình trạng pending |
| Oldest pending | > 600s kéo dài 5m | Page | Slot/event cũ nhất, relay/consumer có progress không |
| Pending tăng | +300 item/15m và depth > 500, kéo dài 10m | Warning | Ingress vs throughput, scale/giới hạn đối tác |
| No progress | Pending > 0, oldest > 900s và không có success > 900s | Page | Worker state, DB lock, retry và message poison |
| DLQ newly added | Có message mới vào DLQ trong 15m | Ticket/Warning | Schema contract, lỗi deserialize, poison event |
| Telemetry missing | Target down hoặc snapshot age quá ngưỡng | Alert hạ tầng | Scrape, collector và trạng thái nghiệp vụ |

**Không áp dụng nguyên xi các số trên.** Nếu SLO là 5 phút, đợi oldest 10 phút mới page có thể đã quá muộn; cần calibrate cảnh báo dựa trên **thời gian còn lại để can thiệp**, thời gian hồi phục của dependency và error budget. Phần latency p95 có thể được dùng để phát hiện sớm trước khi job vi phạm deadline, trong khi overdue và oldest age xác nhận ảnh hưởng rõ ràng.

## 15. Những sai lầm vận hành thường gặp

1. **“Health UP nghĩa là tích hợp hoạt động tốt.”** Ứng dụng có thể sống nhưng consumer kẹt, job không tạo hoặc outbox không phát.
2. **“Chỉ cần cảnh báo HTTP 5xx.”** Nhiều luồng trả 202 rồi thất bại bất đồng bộ; status HTTP không phản ánh kết quả cuối.
3. **“Kafka lag bằng 0 nghĩa là không có tồn đọng.”** Công việc có thể kẹt trước Kafka trong database outbox, hoặc ở hàng đợi retry sau consumer.
4. **“p95 thấp chứng minh mọi request đúng hạn.”** Percentile từ job hoàn tất bỏ sót job pending hoặc job ở một partition kẹt.
5. **“Tỷ lệ lỗi 100% luôn phải page.”** Một request lỗi trong hệ thống traffic thấp cần chính sách khác với 10.000 request lỗi.
6. **“Đặt `for: 5m` là giải quyết mọi cảnh báo nhiễu.”** Nếu metric bị mất hoặc rule không có traffic, nó có thể không fire khi sự cố thật xảy ra.
7. **“Counter tăng mỗi retry chính là số khách hàng thất bại.”** Attempt và business operation là hai đơn vị đo khác nhau.
8. **“Tăng concurrency luôn giải quyết backlog.”** Nếu downstream đang 429, DB lock hoặc broker quá tải, tăng worker có thể làm tình hình xấu hơn.
9. **“Replay để xóa backlog là thao tác vô hại.”** HTTP, DB và Kafka có thể tạo tác dụng phụ trùng nếu thiếu idempotency.
10. **“Cảnh báo hết firing nghĩa là incident đã xong.”** Cần kiểm tra công việc quá deadline đã được khôi phục hoặc đối soát.

## 16. Câu hỏi tự kiểm tra

1. Một HTTP endpoint trả 202 nhanh nhưng sau 20 phút consumer chưa cập nhật đơn hàng: signal nào phát hiện đúng vấn đề?
2. Vì sao tỷ lệ lỗi attempt và tỷ lệ lỗi terminal có thể rất khác nhau? Mỗi tỷ lệ phục vụ quyết định nào?
3. Khi pending count tăng từ 600 lên 900 nhưng oldest age luôn dưới 10 giây, bạn có page ngay không? Cần dữ kiện gì?
4. Nếu `histogram_quantile` đẹp trong khi có một Kafka partition kẹt, cần bổ sung chỉ số và tracing nào?
5. Khi thêm `for: 10m` trong Prometheus, điều gì xảy ra nếu exporter biến mất giữa lúc vi phạm?
6. Làm sao tính đúng tỷ lệ đạt deadline của công việc bất đồng bộ mà không bỏ quên job còn pending?
7. Khi một relay outbox đã gửi Kafka rồi chết trước khi đánh dấu hoàn tất, hành động replay cần những bảo đảm chống trùng nào?
8. Nên đặt `eventId` trong metric label hay log/trace? Tại sao?
9. Tại sao ngưỡng Kafka consumer lag cần xét cả số partition, tốc độ ingress và deadline nghiệp vụ?
10. Một runbook tốt cần xác nhận điều gì trước khi đóng incident sau khi broker hoạt động trở lại?

**Kết luận kỹ thuật:** Cảnh báo hữu ích cho Spring Boot Integration phải phát hiện **tác động kéo dài lên tiến độ nghiệp vụ**, không chỉ báo có exception. Kết hợp **terminal failures**, **độ trễ end-to-end**, **oldest pending age**, **backlog growth** và **last committed progress** giúp thấy cả lỗi rõ ràng lẫn công việc âm thầm bị kẹt. Các rule cần có ngữ nghĩa đếm đúng, cửa sổ thời gian phù hợp, chống nhiễu, nguồn telemetry tin cậy, runbook khôi phục an toàn và kiểm thử các kịch bản lỗi/replay thực tế.

### Tài liệu tham khảo

- [Spring Boot — Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html): Actuator, Micrometer, meter registry và exporter.
- [Spring Boot — Monitoring and Management over HTTP](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html): endpoint health/metrics và cấu hình exposure.
- [Micrometer — Timers](https://docs.micrometer.io/micrometer/reference/concepts/timers.html): đo duration và histogram.
- [Prometheus — Alerting Rules](https://prometheus.io/docs/prometheus/latest/configuration/alerting_rules/): biểu thức và `for`.
- [Prometheus — Histograms and Summaries](https://prometheus.io/docs/practices/histograms/): `histogram_quantile`, bucket và tổng hợp histogram.
- [Google SRE Workbook — Alerting on SLOs](https://sre.google/workbook/alerting-on-slos/): burn rate và cảnh báo nhiều cửa sổ.
- [Apache Kafka — Monitoring](https://kafka.apache.org/documentation/#monitoring): metric Kafka, consumer và producer.
