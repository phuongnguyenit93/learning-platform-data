# Không coi Actuator metrics endpoint là time-series backend

Trong chương **Actuator metrics endpoint** của module **SPRING_BOOT_OBSERVABILITY**, cần phân biệt hai việc rất khác nhau: **quan sát các meter hiện có trong một tiến trình Spring Boot** và **lưu trữ, truy vấn lịch sử metrics của cả hệ thống**. Spring Boot Actuator cung cấp các endpoint hữu ích để kiểm tra ứng dụng đang ghi những số đo nào. Tuy nhiên, endpoint `/actuator/metrics` không phải một cơ sở dữ liệu time series, còn `/actuator/prometheus` là nơi **công bố mẫu metrics để hệ thống khác thu thập**, không phải nơi lưu lịch sử và chạy PromQL.

Đây là kiến thức nền tảng để thiết lập observability bằng **Micrometer Observation, metrics, logs và distributed tracing**, kiểm soát tags/cardinality, exporter và sampling. Nếu nhầm endpoint với backend, nhóm vận hành có thể có dashboard thiếu dữ liệu, tính sai tỷ lệ lỗi và p95, hoặc mất lịch sử sau khi container khởi động lại.

**Mục tiêu học tập:** sau bài này, người học có thể giải thích vai trò của Actuator, `MeterRegistry`, exporter/scraper và time-series backend; dùng endpoint để chẩn đoán tại chỗ; dùng Prometheus/PromQL để phân tích theo thời gian; và biết cách đối chiếu metrics với logs/traces khi điều tra sự cố.

## 1. Ba tầng cần phân biệt

Giả sử ứng dụng nhận request, thực hiện thao tác nghiệp vụ và ghi số liệu bằng Micrometer. Dữ liệu thường đi qua các tầng:

```text
Spring Boot application (mỗi instance)
    |
    +-- HTTP/JVM/DataSource/custom Observation
    |              |
    |              v
    |         Micrometer MeterRegistry
    |              |
    |              +-- /actuator/metrics       JSON để xem meter tại instance
    |              |
    |              +-- /actuator/prometheus    Exposition cho Prometheus scrape
    |              |                |
    |              |                v
    |              |         Prometheus server / TSDB
    |              |           |    |      |
    |              |           |    |      +-- Retention / series history
    |              |           |    +--------- PromQL / query_range
    |              |           +-------------- Alert / dashboard
    |              |
    |              +-- OTLP/khác (nếu cấu hình) --> telemetry backend phù hợp
    |
    +-- Logs ----------------------------------> log backend
    +-- Tracing instrumentation --------------> trace backend
                            (các đường này có cấu hình riêng)
```

| Thành phần | Nhiệm vụ | Điều nó không làm |
| --- | --- | --- |
| **`MeterRegistry`** | Đăng ký meter, giữ trạng thái và xuất các phép đo theo implementation | Không mặc định là kho lịch sử tập trung qua nhiều instance |
| **`/actuator/metrics`** | Liệt kê meter, xem phép đo và tags của registry trong instance | Không lưu và truy vấn dữ liệu nhiều giờ/ngày bằng time range |
| **`/actuator/prometheus`** | Công bố dữ liệu ở định dạng exposition cho Prometheus khi registry phù hợp được cấu hình | Không chạy PromQL hoặc duy trì retention/time-series database |
| **Prometheus / TSDB** | Thu thập mẫu định kỳ, lưu chuỗi có nhãn và timestamp, cho phép PromQL, alert và retention | Không tự đọc được metric của ứng dụng nếu scrape/export chưa hoạt động |
| **Dashboard (ví dụ Grafana)** | Hiển thị và so sánh dữ liệu từ datasource/backend | Thường không thay backend lưu metrics |

Có hệ thống sử dụng exporter dạng push (chẳng hạn OTLP) thay vì cho Prometheus scrape. Điều này thay đổi cách **đưa dữ liệu ra ngoài**, nhưng không biến `/actuator/metrics` thành kho lịch sử. Cần xác định chính xác registry và exporter đang dùng.

## 2. `/actuator/metrics` cho biết điều gì?

Actuator metrics endpoint có thể:

- Liệt kê tên các meter hiện có trong `MeterRegistry` của ứng dụng.
- Cho biết phép đo như `COUNT`, `TOTAL_TIME`, `MAX` hoặc `VALUE` theo loại meter và cấu hình.
- Cho biết các giá trị tag đang có; hỗ trợ lọc một metric bằng tag.
- Giúp kiểm tra một custom counter/timer đã được ghi nhận hay chưa, hoặc một DataSource/JVM meter có xuất hiện không.

Ví dụ sau khi khởi động ứng dụng đã cấu hình Actuator:

```bash
curl -s http://localhost:8080/actuator/metrics

curl -s http://localhost:8080/actuator/metrics/http.server.requests

# Chỉ xem metric có tag cụ thể; -G giúp encode tham số URL:
curl -sG http://localhost:8080/actuator/metrics/http.server.requests \
  --data-urlencode 'tag=method:GET' \
  --data-urlencode 'tag=status:200'
```

Một phản hồi **minh họa cấu trúc**, không phải số đo từ ứng dụng đang chạy:

```json
{
  "name": "http.server.requests",
  "baseUnit": "seconds",
  "measurements": [
    { "statistic": "COUNT", "value": 120.0 },
    { "statistic": "TOTAL_TIME", "value": 7.2 },
    { "statistic": "MAX", "value": 0.45 }
  ],
  "availableTags": [
    { "tag": "method", "values": ["GET", "POST"] },
    { "tag": "status", "values": ["200", "500"] },
    { "tag": "uri", "values": ["/orders", "/checkout"] }
  ]
}
```

Tùy phiên bản và instrumentation, tên, đơn vị, nhãn, measurements hoặc chính meter này có thể khác. Một timer thường có **số lần ghi**, **tổng thời gian** và một phép đo **max**. Giá trị `MAX` của timer có thể là maximum trên cửa sổ thời gian của cơ chế đo, **không phải maximum toàn bộ lịch sử**. Không suy một quy luật lịch sử chỉ từ một phản hồi.

### Tại sao đây không phải time-series backend?

Giả sử gọi endpoint ở ba thời điểm. Bạn có thể nhận ba JSON với giá trị khác nhau, nhưng chính endpoint **không tự giữ cả ba giá trị và timestamp của chúng để trả lời**:

- “Trong 24 giờ qua, RPS mỗi phút biến động thế nào?”
- “p95 latency của `/checkout` tăng vào thời điểm triển khai nào?”
- “Bao nhiêu instance có error rate cao nhất trong 7 ngày?”
- “Tỷ lệ 5xx tăng liên tục bao lâu trước khi cảnh báo phát ra?”

Muốn trả lời, phải có một hệ thống thu thập định kỳ, lưu timestamps/labels và chạy truy vấn theo cửa sổ thời gian. Việc tự lưu thủ công các JSON có thể tạo lịch sử riêng, nhưng **lúc đó chính công cụ lưu/đọc lịch sử mới đảm nhiệm phần việc của backend**, không phải Actuator endpoint.

Quan sát trong registry còn có thể bị reset khi tiến trình khởi động lại. Meter cũng có thể chỉ xuất hiện sau khi đoạn code liên quan đã chạy; chẳng hạn HTTP request meter của một route chưa được truy cập hoặc custom counter chưa được đăng ký.

## 3. Một endpoint khác: `/actuator/prometheus`

Khi ứng dụng có Prometheus registry và endpoint được expose, `/actuator/prometheus` công bố các mẫu ở định dạng phù hợp để **Prometheus server scrape**. Một ví dụ rút gọn:

```text
# HELP orders_completed_total ...
# TYPE orders_completed_total counter
orders_completed_total{application="orders-service",outcome="success"} 150
orders_completed_total{application="orders-service",outcome="error"} 5
```

*Đây là mẫu minh họa tên và số liệu, không phải cam kết về tên backend mà mọi Micrometer version sẽ xuất.*

Dù đầu ra có vẻ giống “các time series”, endpoint chỉ cung cấp mẫu **ở thời điểm đọc**. Một lần `curl` không mang về toàn bộ lịch sử 24 giờ hay 7 ngày. Prometheus cần truy cập endpoint theo chu kỳ scrape để gắn timestamp, lưu kết quả và hỗ trợ truy vấn/alert. Trong hệ thống có OTLP push, một exporter khác gửi số đo ra collector/backend theo lịch push tương ứng; cách đưa dữ liệu đi vẫn khác việc lưu lịch sử.

| Câu hỏi | Dùng ở đâu? |
| --- | --- |
| “Meter `orders.completed` có được đăng ký trong instance này chưa?” | `/actuator/metrics` |
| “Tên/labels chính xác sau khi Micrometer chuyển sang Prometheus là gì?” | `/actuator/prometheus` |
| “Trong 30 phút, rate lỗi thay đổi thế nào?” | Prometheus/TSDB qua truy vấn thời gian |
| “p95 latency 1 giờ qua của cả 10 replica là bao nhiêu?” | Backend có histogram/time series thích hợp |
| “Vì sao request cụ thể lỗi?” | Kết hợp metric backend với trace và log |

## 4. Cấu hình ứng dụng mẫu

Ví dụ Maven cho Spring Boot dùng Actuator và Prometheus. Dự án giả định dùng Spring Boot parent hoặc BOM để quản lý phiên bản:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
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
```

Ví dụ `application.yml`:

```yaml
spring:
  application:
    name: orders-service

management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus
  metrics:
    tags:
      application: orders-service
```

Một số lưu ý:

1. `spring-boot-starter-actuator` cung cấp các endpoint được framework hỗ trợ; việc expose endpoint qua HTTP phụ thuộc cấu hình endpoint access và security của phiên bản Spring Boot.
2. `micrometer-registry-prometheus` cung cấp backend registry để tạo Prometheus exposition. Chỉ bật HTTP endpoint mà không có registry phù hợp không bảo đảm đường `/actuator/prometheus` sẵn sàng.
3. Nhãn `application` giúp phân biệt service khi truy vấn. Khi có nhiều instance, backend thường thêm nhãn target như `job`, `instance` từ scrape. Không gắn request ID/user ID vào các nhãn metric.
4. Trong production, endpoint quản trị phải được giới hạn truy cập: management port riêng, internal network, authentication/authorization hoặc proxy phù hợp. **Không expose tùy tiện Actuator trên Internet**, đặc biệt các endpoint có thông tin vận hành.
5. Có thể có phiên bản Spring Boot khác nhau về tên property, metric mặc định hoặc cơ chế phân quyền. Hãy xác minh kết quả trên ứng dụng đang dùng.

Sau khi chạy app, kiểm tra:

```bash
curl -s http://localhost:8080/actuator/metrics
curl -s http://localhost:8080/actuator/metrics/jvm.memory.used
curl -s http://localhost:8080/actuator/prometheus
```

Nếu một endpoint trả 404/403, cần phân biệt **chưa có endpoint, chưa expose, bị chặn bởi security hoặc sai path/port**; không kết luận ngay meter không được tạo.

## 5. Cấu hình Prometheus mới tạo ra lịch sử

Một cấu hình scrape **minh họa** cho Prometheus server:

```yaml
global:
  scrape_interval: 15s

scrape_configs:
  - job_name: spring-boot-orders
    metrics_path: /actuator/prometheus
    static_configs:
      - targets:
          - localhost:8080
```

Đây là **cấu hình của Prometheus**, không phải cấu hình đặt trong `application.yml` của Spring Boot. Khi Prometheus chạy ở container khác, `localhost:8080` có thể trỏ đến chính container đó, **không phải** ứng dụng Spring Boot; cần dùng DNS/hostname và networking thực tế. Trong Kubernetes, thường dùng service discovery/operator phù hợp.

Sau khi cấu hình đúng, chu trình thường là:

1. Prometheus gọi `/actuator/prometheus` khoảng mỗi 15 giây.
2. Từng mẫu được gắn timestamp và labels nhận diện target/service.
3. Time-series database lưu dữ liệu theo retention được cấu hình.
4. PromQL tính rate, aggregation, histogram quantiles và truy vấn theo thời gian.
5. Alerting hoặc dashboard đọc kết quả từ backend.

Một scrape thất bại tạo khoảng trống dữ liệu; điều đó không có nghĩa ứng dụng không xử lý request. Ngược lại, ứng dụng chạy tốt không bảo đảm scrape đang thành công.

Trên Prometheus có thể kiểm tra:

```promql
up{job="spring-boot-orders"}
```

Giá trị `up=1` cho biết Prometheus **scrape được target** ở lần đánh giá tương ứng; nó **không chứng minh** chức năng đặt hàng hoạt động chính xác hoặc database đang khỏe. `up=0` có thể do network, authentication, endpoint, TLS hay lỗi scrape, không nhất thiết là process chết.

## 6. Vì sao một giá trị COUNT chưa phải request rate?

Một `Counter` hoặc `Timer.count` phổ biến phản ánh tổng số lần xảy ra kể từ khi meter/process được tạo, tùy loại registry. Từ một con số như “12.300 request” không thể biết hệ thống đang nhận 1 hay 1.000 request mỗi giây.

Giả sử cùng một series có các mẫu:

| Thời điểm | Counter tích lũy |
| --- | ---: |
| 10:00:00 | 100 |
| 10:01:00 | 160 |
| 10:02:00 | 220 |

Nếu không reset và hai mẫu có cùng labels, mức tăng trong mỗi phút là **60 request**, tương ứng khoảng **1 request/giây**. Nhưng khi process restart, counter có thể quay về 0. Việc lấy hiệu hai giá trị thủ công sẽ thành số âm, không phản ánh traffic.

Time-series backend có timestamps và các hàm xử lý reset/biến động thích hợp. Với counter kiểu Prometheus, dùng:

```promql
rate(http_server_requests_seconds_count[5m])
```

Trong ví dụ này, `http_server_requests_seconds_count` giả định là tên series counter được export từ timer HTTP `http.server.requests`. Cần kiểm tra tên thực tế, vì naming convention và version có thể khác. `rate(...[5m])` ước lượng mức tăng trung bình mỗi giây trên cửa sổ 5 phút và xử lý các counter reset theo ngữ nghĩa Prometheus.

Muốn tổng request rate của mọi instance:

```promql
sum(rate(http_server_requests_seconds_count[5m]))
```

Muốn rate theo URI route template nếu nhãn `uri` tồn tại:

```promql
sum by (uri) (
  rate(http_server_requests_seconds_count[5m])
)
```

Không dùng `rate()` cho gauge như `jvm_memory_used_bytes` hay `jdbc_connections_active` khi mục đích chỉ là xem mức sử dụng hiện tại; gauge có thể tăng/giảm tùy ý và cách phân tích khác counter.

### Điều gì xảy ra nếu service có 10 replicas?

Endpoint `/actuator/metrics` trên một pod thông thường chỉ nói về số liệu của **pod đó**. Một lần curl không cung cấp lịch sử toàn cụm. Prometheus scrape mỗi target riêng, gắn nhãn nhận diện và có thể:

- Cộng request rate của các instance.
- So sánh instance có lỗi cao.
- Tìm pool database connection bị nghẽn ở một replica.
- Nhìn xu hướng trước/sau rolling deployment.

Các nhãn như `instance`, `pod`, `job` do scrape/relabeling và tài nguyên hạ tầng quyết định. Trước khi cộng, phải bảo đảm không scrape cùng một target hai lần khiến dữ liệu bị **đếm trùng**.

## 7. p95 latency cần histogram hoặc nguồn phân phối phù hợp

Một JSON tại `/actuator/metrics/http.server.requests` với `COUNT`, `TOTAL_TIME` và `MAX` không đủ để tái dựng chính xác **p95 latency trong một khoảng thời gian qua nhiều instance**. Từ tổng thời gian và count chỉ có thể tính **mean** nếu semantics phù hợp; từ max cũng không suy ra p95.

Để tính p95 từ Prometheus classic histogram, cần bật và export các bucket cho timer phù hợp. Ví dụ cấu hình **có thể áp dụng trong các phiên bản Spring Boot hỗ trợ property này**:

```properties
management.metrics.distribution.percentiles-histogram.http.server.requests=true
```

Việc bật histogram có thể tăng số time series theo tổ hợp tags và số buckets; cần đo ngân sách cardinality, đánh giá URI/status/method và không bật vô điều kiện cho mọi meter. Có registry hoặc hệ metrics khác sử dụng cách phân phối/aggregation khác; hãy xác minh trên backend.

Khi series `http_server_requests_seconds_bucket` và label `uri` thật sự tồn tại, truy vấn minh họa cho endpoint checkout:

```promql
histogram_quantile(
  0.95,
  sum by (le) (
    rate(http_server_requests_seconds_bucket{uri="/checkout"}[5m])
  )
)
```

Lệnh trên chỉ hoạt động đúng khi tên bucket, nhãn, đơn vị giây và histogram phù hợp với exporter đang dùng. `sum by (le)` gộp các instance và các nhãn khác đã lọc; nếu muốn p95 theo từng instance/service/status, cần giữ lại những nhãn nhóm tương ứng. Quantile từ histogram là **ước lượng phụ thuộc buckets**, không phải giá trị chính xác từ mọi request.

**Không tính trung bình p95 của từng pod để ra p95 toàn hệ thống.** Quantile không có tính chất cộng/trung bình như counter. Phải gộp dữ liệu phân phối phù hợp ở backend rồi mới tính quantile.

## 8. Phân biệt metric tag, trace attribute và log field

Micrometer Observation cho phép một hoạt động nghiệp vụ cung cấp metadata và các observation handlers có thể ghi thành metric/tín hiệu tracing tùy cấu hình. Nhưng **không phải mọi metadata thích hợp để dùng làm metric label**.

| Metadata | Metric label | Trace/log detail |
| --- | --- | --- |
| `outcome=success/error` | Phù hợp khi tập giá trị hữu hạn | Cũng hữu ích |
| `payment.provider=bank_a/bank_b` | Phù hợp khi số provider được quản lý | Cũng hữu ích |
| `uri=/orders/{id}` (route template) | Thường phù hợp | Có thể dùng |
| `orderId=...` | **Tránh**: cardinality cao | Chỉ dùng khi cần và được phép theo chính sách dữ liệu |
| Raw URL chứa query string | Tránh làm label | Cần lọc thông tin nhạy cảm nếu ghi |
| Exception message nguyên văn | Tránh làm label | Dùng log chẩn đoán có kiểm soát, tránh secrets |

Một metric với 3 values `provider`, 4 values `outcome` và 100.000 order IDs có thể sinh đến **1.200.000 tổ hợp labels** trước khi tính nhãn khác. Dù endpoint `/actuator/metrics` vẫn trả JSON, backend có thể chịu tải và chi phí lớn. **Cardinality là rủi ro của metric identity, không phải sự cố do endpoint trở thành TSDB.**

Đối với traces, sampling có thể giữ một phần các request; logs với `traceId`/`spanId` cần MDC/logging correlation được cấu hình thích hợp; context propagation phải hoạt động khi qua thread, executor và service. Một trace không được lấy mẫu **không đồng nghĩa** counter/timer cũng bị bỏ nếu metric observation handler vẫn ghi dữ liệu.

## 9. Bổ sung một custom business metric và kiểm tra đường xuất

Giả sử có service xác thực thanh toán với outcome đã được phân loại. Một custom counter chỉ ghi sự kiện nghiệp vụ riêng, không dùng order ID làm tag:

```java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.stereotype.Service;

@Service
public class PaymentMetrics {
    private final MeterRegistry registry;

    public PaymentMetrics(MeterRegistry registry) {
        this.registry = registry;
    }

    public void recordAuthorization(boolean approved) {
        String outcome = approved ? "approved" : "declined";
        Counter.builder("payment.authorizations")
                .description("Authorization decisions")
                .tag("outcome", outcome)
                .register(registry)
                .increment();
    }
}
```

Giả định ứng dụng gọi method đúng **một lần cho mỗi quyết định**, metric `payment.authorizations` đo số quyết định nghiệp vụ; nó khác thời lượng HTTP client. Với Prometheus registry, counter có thể được export dưới tên có hậu tố như `payment_authorizations_total`. Kiểm tra thực tế thay vì viết query theo một tên đoán trước.

Quy trình kiểm chứng:

1. Gọi nghiệp vụ vài lần với `approved` và `declined`.
2. Kiểm tra `/actuator/metrics/payment.authorizations`: tên, measurements và available tags đã xuất hiện đúng chưa?
3. Kiểm tra `/actuator/prometheus`: tên backend và labels thực tế là gì?
4. Kiểm tra target trong Prometheus: scrape có thành công và samples có được lưu không?
5. Chạy PromQL trên khoảng đủ dài: rate/tổng số quyết định theo `outcome` có hợp lý không?
6. So sánh với log/trace của một giao dịch lỗi khi hệ thống cần điều tra chi tiết. Không thêm `orderId` vào counter để truy vết một đơn.

Nếu cùng một sự kiện bị ghi ở service và cả adapter HTTP/queue, count có thể bị tăng hai lần dù registry chỉ dùng một meter. Khi đó sửa điểm ghi, không phải chỉ sửa endpoint.

## 10. Những lỗi nhận thức phổ biến

**“Tôi thấy `COUNT=500` ở `/actuator/metrics`, vậy backend đã lưu 500 điểm lịch sử.”** Sai. Count có thể là một giá trị tích lũy của meter; không phải 500 mẫu theo thời gian. Backend lưu số mẫu phụ thuộc scrape/step/export/retention.

**“`/actuator/prometheus` trả về dữ liệu, vậy Prometheus đã scrape thành công.”** Chưa chắc. Bạn chỉ chứng minh endpoint có trả exposition cho **client đang gọi**. Cần kiểm tra target, network, authentication, scrape errors và query ở Prometheus server.

**“Có `MAX` nên đủ tính p99 cho 30 ngày.”** Sai. Max của timer có thể mang semantics cửa sổ thời gian; không thay thế phân phối/histogram và lịch sử.

**“Counter tăng khi app chạy, chỉ cần lấy hai snapshot rồi trừ là chính xác.”** Chỉ là phép xấp xỉ với các giả định rất chặt: cùng instance/series, không reset, không thiếu mẫu, không thay labels. Backend với `rate()`/`increase()` phù hợp hơn cho vận hành thường xuyên.

**“Có `/actuator/metrics` là chắc chắn có tracing.”** Không đúng. Metrics, tracing bridge, exporter và log correlation là các thành phần có cấu hình riêng.

**“Không thấy meter trong JSON nghĩa là code không chạy.”** Chưa chắc. Meter có thể chưa đăng ký, bị `MeterFilter` từ chối, observation bị `ObservationPredicate` loại, instrumentation chưa bật hoặc registry khác đang dùng.

**“Prometheus đã có dữ liệu nên cứ thêm order ID vào tag để điều tra.”** Việc này làm tăng số series, chi phí và rủi ro riêng tư. Dùng tags low-cardinality; dùng trace/log được bảo vệ để tra cứu giao dịch cụ thể.

**“Tôi chỉ cần tăng trace sampling để phục hồi dữ liệu metrics.”** Sampling là quyết định của tracing; thiếu metric thường cần kiểm tra meter/handler/registry/exporter/scrape. Hai vấn đề có thể độc lập.

## 11. Tình huống vận hành: request chậm sau một đợt triển khai

Giả sử ứng dụng `orders-service` có 6 replicas. Sau khi deploy, người dùng báo checkout chậm. Một kỹ sư gọi `/actuator/metrics/http.server.requests` trên một pod và thấy `MAX` cao. Đây là **dấu hiệu ban đầu**, chưa đủ để kết luận toàn hệ thống.

Cách điều tra:

1. **Xác định đường thu dữ liệu:** Prometheus target có scrape đủ 6 replicas không? Có target mất kết nối không? `up` có phản ánh lỗi scrape không?
2. **Xác định mức độ:** chạy query rate HTTP và 5xx theo service/URI, xem thời điểm bắt đầu thay đổi. Không chỉ dựa vào counter snapshot của một pod.
3. **Xác định latency:** dùng histogram phù hợp để tính p95/p99 theo khoảng trước và sau deploy; phân biệt lỗi ở một instance với toàn cụm.
4. **Khoanh vùng dependency:** đối chiếu pool metrics, external client metrics, CPU/GC, database server metrics. Một endpoint chậm có thể do connection pool hoặc provider thanh toán.
5. **Điều tra giao dịch:** từ khoảng thời gian xấu, mở một trace được lấy mẫu, kiểm tra business observations và span con. Dùng correlated logs để xem loại lỗi và quyết định nghiệp vụ.
6. **Kiểm tra propagation và sampling:** nếu trace bị đứt qua executor/queue/service, sửa context propagation; nếu không thấy span do sampling, không suy ra bước nghiệp vụ chưa chạy.
7. **Đánh giá cảnh báo:** alert dựa trên rate/p95 có cửa sổ và mức tải phù hợp; nhận diện khoảng thiếu scrape để tránh kết luận sai.

Ví dụ PromQL tổng tỷ lệ 5xx, khi các nhãn `status` và tên meter phù hợp:

```promql
sum(rate(http_server_requests_seconds_count{status=~"5.."}[5m]))
/
clamp_min(
  sum(rate(http_server_requests_seconds_count[5m])),
  1e-9
)
```

Truy vấn minh họa này cần lọc đúng service/job/URI trong hệ thống nhiều ứng dụng; không có traffic có thể tạo kết quả rỗng tùy series tồn tại và PromQL matching. Tỷ lệ lỗi và thời lượng cần được phân tích cùng lưu lượng request để tránh cảnh báo nhiễu khi hệ thống gần như không có tải.

## 12. Bảng quyết định nhanh: dùng endpoint hay backend?

| Mục tiêu | Công cụ phù hợp | Lý do |
| --- | --- | --- |
| Tìm tên meter và tag ngay trên một instance | `/actuator/metrics` | Thấy được trạng thái/metadata registry tại thời điểm kiểm tra |
| Kiểm tra tên Prometheus sau conversion | `/actuator/prometheus` | Nhìn exposition thực tế mà scraper cần đọc |
| Xác nhận target được thu thập | Prometheus targets và `up` | Phân biệt app chạy với đường scrape có hoạt động |
| Vẽ RPS theo phút trong 7 ngày | TSDB + PromQL/dashboard | Cần timestamps, range query và retention |
| Tính p95 qua nhiều replicas | TSDB với histogram/summary phù hợp | Cần dữ liệu phân phối và aggregation đúng ngữ nghĩa |
| Đặt alert error rate trong 10 phút | Backend alerting/query | Cần truy vấn theo thời gian và lịch đánh giá |
| Tìm nguyên nhân một giao dịch lỗi | Trace backend + structured logs | Metrics không giữ chi tiết từng request |
| Giảm số series bùng nổ | Chỉnh tags tại nguồn và meter policy | Endpoint không giải quyết cardinality |

## 13. Bài tập kiểm chứng

Một nhóm triển khai Spring Boot có Actuator và Prometheus registry. Họ chạy:

```bash
curl -s http://localhost:8080/actuator/metrics/http.server.requests
curl -s http://localhost:8080/actuator/prometheus
```

Hai lệnh trả dữ liệu. Tuy nhiên dashboard Grafana vẫn trống. Nhóm kết luận rằng “Actuator chưa lưu đủ lịch sử” và định tự gọi endpoint mỗi giây để lưu JSON trong một bảng SQL.

**Câu hỏi:** nhóm đã suy luận sai ở đâu, và bước điều tra phù hợp là gì?

Một đáp án tham khảo:

1. Hai endpoint chỉ chứng minh **ứng dụng hiện có dữ liệu và có khả năng công bố exposition**, chưa chứng minh Prometheus server thu thập được.
2. Kiểm tra Prometheus `scrape_configs` hoặc service discovery, target host/port, `metrics_path`, network và security. Lưu ý `localhost` khác nhau giữa container.
3. Kiểm tra target health và `up`, sau đó query tên series thật trong Prometheus. So nhãn `job`/`instance`/`application` với query mà dashboard sử dụng.
4. Kiểm tra time range, retention, scrape interval và thiết lập datasource của Grafana. Grafana cần trỏ đúng backend và dùng query khớp metric name/labels.
5. Chỉ khi hệ thống đã có các samples theo thời gian mới xây rate, histogram quantile và alert một cách đáng tin cậy.
6. Nếu dùng kiến trúc OTLP push, xác minh exporter → collector → metrics backend theo luồng đó; không ép dùng Prometheus scrape khi thiết kế đã chọn push.

### Tiêu chí hoàn thành bài

Người học nên tự kiểm tra được các tình huống sau:

| Thử nghiệm | Kỳ vọng |
| --- | --- |
| Gọi `/actuator/metrics` trước/sau khi thực hiện nghiệp vụ | Nhìn được meter và số đo thay đổi nếu registry đang ghi đúng |
| Restart ứng dụng | Nhận ra count trong process có thể reset; lịch sử backend có thể còn theo retention |
| Tắt đường scrape nhưng app vẫn chạy | Endpoint có thể còn truy cập trực tiếp, nhưng Prometheus mất các samples mới |
| Gọi `/actuator/prometheus` trực tiếp | Thấy tên/labels exposition, không có API truy vấn lịch sử tại endpoint |
| Khôi phục scrape | Có samples theo thời gian, query `rate()` hoạt động sau khi có đủ mẫu |
| Bật histogram phù hợp | Có bucket series để tính p95 theo PromQL nếu exporter hỗ trợ |
| Tăng cardinality tag quá cao | Nhận ra nguyên nhân là thiết kế nhãn và số series, cần sửa nguồn telemetry |
| Trace bị sampled out | Metric có thể vẫn hiện; logs/tracing cần cấu hình và propagation riêng |

**Ghi nhớ:** `/actuator/metrics` là công cụ **chẩn đoán meter tại ứng dụng**; `/actuator/prometheus` là công cụ **công bố mẫu cho scraper**; **time-series backend** mới là nơi thu thập, lưu trữ và truy vấn lịch sử theo timestamp/labels. Sử dụng đúng từng tầng, chuẩn hóa tag/cardinality và liên kết với logs/traces sẽ giúp đánh giá chính xác lỗi, độ trễ và hành vi Spring Boot trên môi trường thực.
