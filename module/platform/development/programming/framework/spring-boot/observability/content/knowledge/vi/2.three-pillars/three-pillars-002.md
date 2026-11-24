# Metrics: đo lường hành vi và sức khỏe ứng dụng Spring Boot

> **Chương:** Ba trụ cột · **Bài:** Metrics  
> **Module:** SPRING_BOOT_OBSERVABILITY — Thiết lập observability cho Spring Boot bằng Micrometer Observation, metrics, logs và distributed tracing. Học propagation ngữ cảnh, tag/cardinality, exporter, sampling và liên kết tín hiệu để điều tra lỗi, độ trễ và hành vi ứng dụng trên môi trường thực.

## 1. Metrics là gì và trả lời được câu hỏi nào?

**Metric** là phép đo định lượng được thu thập theo thời gian, thường dưới dạng chuỗi thời gian (*time series*). Một điểm dữ liệu điển hình gồm tên phép đo, giá trị, thời điểm và tập nhãn (*tags/labels*) để phân chia theo các chiều như phương thức HTTP, mã trạng thái hoặc dịch vụ.

Ví dụ, thay vì chỉ biết một yêu cầu `POST /api/orders` bị chậm, metrics cho biết **toàn bộ hệ thống** đang xử lý bao nhiêu yêu cầu mỗi giây, tỉ lệ lỗi 5xx có tăng hay không và phân phối thời gian đáp ứng biến đổi ra sao trong 15 phút gần nhất.

Trong ba trụ cột observability:

| Tín hiệu | Câu hỏi nổi bật | Ví dụ |
| --- | --- | --- |
| **Metrics** | *Bao nhiêu? Nhanh/chậm đến mức nào? Xu hướng ra sao?* | Lưu lượng, tỉ lệ lỗi, p95 latency, mức dùng heap |
| **Logs** | *Sự kiện cụ thể nào đã xảy ra?* | Ngoại lệ, quyết định xử lý, thông tin nghiệp vụ đã lọc dữ liệu nhạy cảm |
| **Traces** | *Yêu cầu đi qua những bước nào và bị chậm ở đâu?* | Span gọi cơ sở dữ liệu, HTTP client, hàng đợi, các dịch vụ liên quan |

Metrics đặc biệt phù hợp với dashboard, cảnh báo và theo dõi mục tiêu mức dịch vụ (SLO), vì có thể tổng hợp nhiều triệu sự kiện thành số liệu tương đối gọn. Đổi lại, metric tổng hợp **không tự chỉ ra** chính xác yêu cầu nào bị lỗi; khi cần điều tra từng trường hợp, chuyển sang log và trace có tương quan.

### Tình huống minh họa

Một API tạo đơn hàng bình thường có 30 yêu cầu/giây, tỉ lệ lỗi 0,2%, p95 khoảng 180 ms. Sau triển khai, dashboard hiển thị 30 yêu cầu/giây, tỉ lệ lỗi 3% và p95 900 ms. Ta biết hệ thống **đang suy giảm**, dù lưu lượng không tăng. Bước tiếp theo là chia metric theo `uri`, `status` hoặc thành phần phụ thuộc, rồi dùng logs/traces tìm nguyên nhân cụ thể.

## 2. Các loại metric cần phân biệt

Micrometer cung cấp API đo lường độc lập với hệ thống lưu trữ đích. Những instrument thường dùng là:

| Loại | Cách hoạt động | Dùng khi | Lưu ý |
| --- | --- | --- | --- |
| **Counter** | Chỉ tăng trong vòng đời tiến trình | Số yêu cầu, số lần retry, số sự kiện thất bại | Dùng `rate()`/`increase()` trên chuỗi được scrape; restart có thể đưa counter về 0 |
| **Gauge** | Đọc giá trị tại thời điểm đo | Số job trong hàng đợi, bộ nhớ đang dùng, số kết nối hoạt động | Không cộng dồn gauge qua thời gian như counter |
| **Timer** | Ghi thời lượng và số lần thực thi | Latency của request, truy vấn, thao tác nghiệp vụ | Thường xuất ra `count`, `sum` và có thể có histogram |
| **DistributionSummary** | Ghi phân phối của giá trị không nhất thiết là thời gian | Kích thước payload, số phần tử mỗi batch | Khác Timer ở đơn vị và ý nghĩa giá trị |
| **LongTaskTimer** | Theo dõi các tác vụ vẫn đang chạy | Tác vụ batch kéo dài, đồng bộ dữ liệu | Cho biết số tác vụ đang hoạt động và tổng thời gian đang chạy |

Chọn đúng instrument theo ý nghĩa phép đo. Ví dụ, `queue.depth` nên là Gauge; `orders.created` nên là Counter; `orders.processing.duration` nên là Timer. Không dùng Gauge cho số sự kiện đã xảy ra nếu muốn tính tốc độ và tăng trưởng chính xác.

### Latency trung bình không đại diện cho đuôi phân phối

Giả sử 95 request hoàn thành trong 50 ms, còn 5 request mất 3 giây. Trung bình khoảng 198 ms, nhưng nhóm người dùng chậm nhất lại phải chờ 3 giây. Vì vậy hãy theo dõi thêm **p95/p99 latency** và phân phối histogram, nhất là ở API có yêu cầu về độ trễ.

**Percentile cục bộ** được tính riêng trên từng instance không thể lấy trung bình để suy ra percentile của toàn hệ thống. Nếu cần p95 toàn cụm trong Prometheus, ưu tiên histogram có ranh giới bucket tương thích giữa các instance, rồi tổng hợp số lượng mẫu trên từng bucket trước khi dùng `histogram_quantile()`.

## 3. Luồng thu thập trong Spring Boot

`Spring Boot Actuator` tích hợp với **Micrometer**, cung cấp nhiều metric mặc định và hỗ trợ tự đăng ký metric nghiệp vụ. Với Prometheus, luồng phổ biến là:

~~~mermaid
flowchart LR
    A["HTTP, JVM, pool kết nối, tác vụ nghiệp vụ"] --> B["Micrometer MeterRegistry"]
    B --> C["Actuator /actuator/prometheus"]
    C -->|scrape định kỳ| D["Prometheus"]
    D --> E["Dashboard Grafana"]
    D --> F["Alerting"]
    F --> G["Điều tra qua logs và traces"]
~~~

- `MeterRegistry` giữ và xuất các meter. Registry cụ thể quyết định cách biểu diễn trên backend (Prometheus, OTLP, ...).
- Spring Boot tự instrument một số thành phần khi dependency và auto-configuration phù hợp: HTTP server, JVM, system, datasource/pool kết nối... Các metric hiện có phụ thuộc thư viện đang chạy.
- `/actuator/metrics` chủ yếu giúp **kiểm tra tên metric và các tag**; đây không phải định dạng Prometheus scrape.
- `/actuator/prometheus` xuất chuỗi cho Prometheus nếu có registry tương ứng và endpoint được expose.
- Prometheus chủ động **scrape** theo chu kỳ, lưu time series và phục vụ PromQL. Interval scrape quyết định mức chi tiết quan sát; scrape không có nghĩa là ứng dụng chỉ xử lý một request mỗi interval.

Tên metric theo Micrometer thường có dấu chấm, chẳng hạn `http.server.requests`. Khi xuất sang Prometheus, tên được chuẩn hóa theo convention và đơn vị: một Timer như vậy thường xuất những chuỗi như `http_server_requests_seconds_count`, `http_server_requests_seconds_sum`, và `http_server_requests_seconds_bucket` nếu bật histogram. Không nên viết rule chỉ dựa trên phỏng đoán tên: hãy xem đầu ra exporter thực tế.

## 4. Thực hành: bật Actuator và Prometheus

Ví dụ dưới đây dùng cách cấu hình quen thuộc của **Spring Boot 3.x + Micrometer**. Với dự án dùng phiên bản khác, cần đối chiếu dependency và property tương ứng.

### 4.1. Dependency Maven

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>
    <dependency>
        <groupId>io.micrometer</groupId>
        <artifactId>micrometer-registry-prometheus</artifactId>
    </dependency>
</dependencies>
~~~

Khi quản lý dependency bằng Spring Boot BOM/parent, thông thường không cần khai báo version riêng cho hai dependency trên. Nếu dự án dùng Gradle, cần khai báo hai module tương đương.

### 4.2. Cấu hình `application.yml`

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus
  metrics:
    tags:
      application: order-service
    distribution:
      percentiles-histogram:
        "http.server.requests": true
      slo:
        "http.server.requests": 100ms,300ms,1s
~~~

Trong ví dụ này:

1. Expose `metrics` để tra cứu và `prometheus` để hệ thống giám sát scrape; `health` và `info` phục vụ kiểm tra vận hành.
2. Thêm tag `application=order-service` giúp phân biệt dịch vụ khi nhiều ứng dụng cùng gửi về một backend.
3. Bật histogram và các ranh giới latency phục vụ truy vấn phân phối theo nhiều instance. Đây là **cấu hình minh họa**: mỗi bucket kết hợp cùng tập tags sẽ tạo thêm time series, nên chỉ bật histogram ở các phép đo thực sự cần thiết trong production.

Đảm bảo cổng quản trị/Actuator có kiểm soát truy cập ở môi trường thực tế; không công bố endpoint giám sát ra Internet chỉ vì muốn scrape dễ dàng.

### 4.3. Xác minh tại ứng dụng

Sau khi chạy ứng dụng và gọi thử một vài API:

~~~bash
curl http://localhost:8080/actuator/metrics
curl http://localhost:8080/actuator/metrics/http.server.requests
curl http://localhost:8080/actuator/prometheus
~~~

Ở endpoint `metrics`, tìm tên metric và danh sách `availableTags`. Ở `prometheus`, kiểm tra các chuỗi `..._count`, `..._sum` và `..._bucket` (khi có histogram). Nếu metric HTTP chưa xuất hiện, thử gửi request thật trước; một số meter chỉ xuất hiện sau khi có mẫu đo.

Ví dụ cấu hình scrape của Prometheus khi chạy **cùng máy và cùng không gian mạng** với ứng dụng:

~~~yaml
scrape_configs:
  - job_name: spring-boot-orders
    scrape_interval: 15s
    metrics_path: /actuator/prometheus
    static_configs:
      - targets: ["localhost:8080"]
~~~

Nếu Prometheus chạy trong container riêng, `localhost` bên trong container là chính container đó. Hãy thay `targets` bằng tên host hoặc tên dịch vụ có thể kết nối được từ container Prometheus.

## 5. Tạo metrics nghiệp vụ với MeterRegistry

Metrics mặc định cho biết tình trạng kỹ thuật của ứng dụng, nhưng đôi khi chưa trả lời được câu hỏi nghiệp vụ như “bao nhiêu thao tác xử lý đơn hàng thành công hoặc lỗi”. Đo ngay tại vị trí thực hiện nghiệp vụ, đặt tên và tags có ý nghĩa ổn định.

Ví dụ sau đo **số lần thử xử lý** và **thời lượng thực thi** của một thao tác đồng bộ:

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.springframework.stereotype.Service;

@Service
public class OrderMetricsService {
    private final MeterRegistry meterRegistry;

    public OrderMetricsService(MeterRegistry meterRegistry) {
        this.meterRegistry = meterRegistry;
    }

    public void execute(Runnable operation) {
        Timer.Sample sample = Timer.start(meterRegistry);
        String result = "success";

        try {
            operation.run();
        } catch (RuntimeException | Error ex) {
            result = "error";
            throw ex;
        } finally {
            sample.stop(
                Timer.builder("orders.processing.duration")
                    .description("Duration of an order processing attempt")
                    .tag("result", result)
                    .register(meterRegistry)
            );

            meterRegistry.counter("orders.processed", "result", result)
                .increment();
        }
    }
}
~~~

Diễn giải:

- `orders.processed` tăng một đơn vị **mỗi lần thử**, kể cả thất bại; nó không đồng nghĩa số đơn hàng tạo thành công. Nếu cần hai ý nghĩa khác nhau, dùng tên metric thể hiện rõ định nghĩa.
- `orders.processing.duration` là Timer ghi thời gian xử lý; số lần ghi của Timer cũng có thể dùng để đếm các lần thử. Counter bổ sung ở đây nhằm minh họa phép đo nghiệp vụ tách biệt.
- `result` chỉ có hai giá trị `success` và `error` nên an toàn hơn một tag lấy từ thông báo lỗi tùy ý.
- Khối `finally` giúp ghi thời lượng cả khi thao tác ném lỗi. Với luồng bất đồng bộ, phải đo đến khi tác vụ thực sự hoàn tất, không dừng Timer ngay sau khi khởi tạo công việc.

**Không** đưa `userId`, `orderId`, `requestId`, URL đầy đủ hoặc nội dung exception vào tags metric. Những thông tin theo từng request nên nằm trong log/tracing có chính sách phù hợp; metrics cần chiều giá trị hữu hạn.

## 6. Tags và cardinality: giới hạn chi phí ngay từ thiết kế

Một time series trong Prometheus được phân biệt bởi **tên metric và tổ hợp nhãn**. Cardinality là số tổ hợp nhãn khác nhau. Đây là một trong những rủi ro lớn nhất khi thiết kế metrics.

Ví dụ giả định một metric có 20 mẫu URI, 4 HTTP method, 5 nhóm status và 10 instance thì đã có tới **20 × 4 × 5 × 10 = 4.000 chuỗi**. Nếu bật histogram với nhiều bucket, số chuỗi có thể tăng đáng kể. Thêm `userId` với hàng trăm nghìn giá trị sẽ làm chi phí lưu trữ và truy vấn tăng vọt.

| Tag nên cân nhắc | Tag cần tránh | Lý do |
| --- | --- | --- |
| `method=GET/POST` | `requestId=...` | Request ID gần như luôn duy nhất |
| `status=200/404/500` hoặc `outcome` | `exceptionMessage=...` | Nội dung lỗi có thể vô hạn và chứa dữ liệu nhạy cảm |
| `uri=/api/orders/{id}` (mẫu route) | `uri=/api/orders/12345` (URL thực) | ID tạo ra giá trị mới cho mỗi bản ghi |
| `region`, `service`, `result` có tập giá trị giới hạn | `email`, `sessionId`, `userId` | Chiều phân biệt người dùng không thích hợp cho metric |

Nguyên tắc thực hành:

1. Xác định câu hỏi vận hành trước khi thêm một metric hoặc tag. Mỗi chiều phải có cách sử dụng rõ ràng trong truy vấn hoặc cảnh báo.
2. Dùng **route template** thay cho URL chứa ID; giới hạn các giá trị tag bằng danh mục có kiểm soát.
3. Đánh giá tổng số chuỗi sau khi thêm tags, sau khi nhân với số instance, bucket và môi trường chạy.
4. Theo dõi chính backend metrics (số series, chi phí lưu trữ, thời gian scrape, độ trễ truy vấn). Cấu hình lọc/đổi tên meter có thể dùng khi buộc phải kiểm soát dữ liệu phát sinh.

Với Micrometer Observation, key-value **low cardinality** có thể phục vụ metrics; thông tin **high cardinality** thích hợp hơn cho span của trace. Dù dùng Observation hay MeterRegistry trực tiếp, vẫn phải kiểm soát số giá trị của từng nhãn.

## 7. Đọc và truy vấn metrics với PromQL

Các truy vấn dưới đây giả định đầu ra Prometheus của metric HTTP server mặc định và tag `application="order-service"`. Tên chính xác có thể khác theo version, instrumentation và registry. Xác minh chúng bằng `/actuator/prometheus` trước khi dùng.

### 7.1. Request rate (RPS)

~~~promql
sum(
  rate(http_server_requests_seconds_count{application="order-service"}[5m])
)
~~~

`rate(counter[5m])` ước tính tốc độ tăng mỗi giây trong cửa sổ 5 phút và xử lý việc counter reset do tiến trình restart. `sum` cộng kết quả của các series, ví dụ từ nhiều instance.

### 7.2. Tỉ lệ request 5xx

~~~promql
sum(
  rate(http_server_requests_seconds_count{
    application="order-service",status=~"5.."
  }[5m])
)
/
sum(
  rate(http_server_requests_seconds_count{
    application="order-service"
  }[5m])
)
~~~

Kết quả là tỉ lệ 0–1 (nhân 100 khi muốn phần trăm). Khi không có traffic, mẫu số có thể bằng 0 và truy vấn không trả về tỉ lệ hữu ích; dashboard/alert cần xét riêng trường hợp không có mẫu hoặc lưu lượng quá thấp. Nếu hệ thống dùng `status` dạng khác, điều chỉnh bộ lọc theo nhãn thật.

### 7.3. p95 latency của API tạo đơn

~~~promql
histogram_quantile(
  0.95,
  sum by (le) (
    rate(http_server_requests_seconds_bucket{
      application="order-service",uri="/api/orders"
    }[5m])
  )
)
~~~

Histogram timer xuất đơn vị **giây** cho Prometheus, vì vậy nhân kết quả với 1000 nếu cần hiển thị ms. Truy vấn này chỉ có ý nghĩa khi metric tương ứng thực sự xuất các series `_bucket`. Nếu muốn xem độ trễ riêng từng route hoặc method, giữ lại nhãn đó trong phép `sum by (le, uri)` hay `sum by (le, method)`, nhưng cân nhắc cardinality.

### 7.4. Thông lượng xử lý nghiệp vụ

~~~promql
sum by (result) (
  rate(orders_processed_total{application="order-service"}[5m])
)
~~~

Đây là ví dụ cho Counter `orders.processed` sau khi Prometheus chuẩn hóa thành `orders_processed_total`; hãy kiểm tra tên series thực tế của registry. Metric này thể hiện số *lần thử* mỗi giây theo kết quả, nên có thể khác số request HTTP do một request có thể thực hiện nhiều thao tác hoặc bị retry.

## 8. Từ metrics đến SLI, SLO và cảnh báo

**SLI (Service Level Indicator)** là phép đo phản ánh chất lượng dịch vụ. **SLO (Service Level Objective)** là mục tiêu định lượng đặt cho SLI trong một khoảng thời gian.

Ví dụ cho API đặt hàng:

| SLI | Cách đo | SLO minh họa |
| --- | --- | --- |
| Tính sẵn sàng theo request | Tỉ lệ request thành công theo quy ước của hệ thống | ≥ 99,9% trong 30 ngày |
| Độ trễ | Phần trăm request kết thúc trong 300 ms | ≥ 95% trong 30 ngày |
| Độ đúng nghiệp vụ | Tỉ lệ xử lý đơn thành công, loại trừ yêu cầu không hợp lệ theo định nghĩa | ≥ 99,5% trong 30 ngày |

Các mục tiêu trên chỉ là **ví dụ**, không phải ngưỡng mặc định của Spring Boot. Phải thống nhất mẫu số, sự kiện loại trừ, khoảng đo và nguồn metric trước khi tạo cảnh báo.

Các hướng thực hành thường dùng:

- **RED** cho dịch vụ phục vụ request: *Rate* (lưu lượng), *Errors* (lỗi), *Duration* (độ trễ).
- **USE** cho tài nguyên: *Utilization* (mức dùng), *Saturation* (mức bão hòa), *Errors* (lỗi tài nguyên).
- Quan sát thêm độ trễ, lưu lượng, lỗi, saturation theo bốn tín hiệu vàng, rồi chọn SLI phản ánh trải nghiệm người dùng.

Một cảnh báo có ích cần điều kiện đo ổn định, tránh kích hoạt bởi một lần lỗi đơn lẻ trong hệ thống ít traffic. Ví dụ quy tắc Prometheus sau chỉ cảnh báo khi tỉ lệ 5xx vượt 2% và RPS lớn hơn 1 liên tục 10 phút:

~~~yaml
groups:
  - name: spring-boot-service
    rules:
      - alert: HighHttp5xxRate
        expr: |
          (
            sum(rate(http_server_requests_seconds_count{
              application="order-service",status=~"5.."
            }[5m]))
            /
            sum(rate(http_server_requests_seconds_count{
              application="order-service"
            }[5m]))
          ) > 0.02
          and
          sum(rate(http_server_requests_seconds_count{
            application="order-service"
          }[5m])) > 1
        for: 10m
        labels:
          severity: warning
        annotations:
          summary: "Tỷ lệ HTTP 5xx của order-service tăng"
~~~

Trong production, ngưỡng nên xuất phát từ SLO và đặc tính traffic; với dịch vụ có SLO, có thể thiết kế cảnh báo theo **error-budget burn rate** để cân đối phát hiện nhanh và hạn chế cảnh báo nhiễu.

## 9. Kết hợp Metrics, Logs và Traces khi điều tra sự cố

Xét tình huống đơn hàng có p95 tăng từ 180 ms lên 900 ms và 5xx tăng lên 3% sau khi deploy:

1. **Phát hiện (Metrics):** dashboard cho thấy request rate ổn định, lỗi và latency tăng. Chia theo `uri`, `status`, instance, version triển khai hoặc dependency có sẵn tag.
2. **Khoanh vùng (Metrics):** so sánh thời gian chờ kết nối DB, số kết nối đang dùng, thời gian JVM GC và mức tải CPU. Nếu tăng cùng thời điểm, hình thành giả thuyết về nghẽn pool, database hoặc CPU.
3. **Tìm sự kiện (Logs):** lọc log theo khoảng thời gian, endpoint và dấu hiệu timeout. Log dạng cấu trúc có `traceId`/`spanId` giúp tra cứu nhất quán hơn khi tracing được bật.
4. **Phân rã độ trễ (Traces):** mở trace của một request chậm để xem span DB, HTTP client hoặc xử lý ứng dụng chiếm thời gian. Tracing có thể được **sampling**, vì vậy không phải request nào cũng có trace.
5. **Xác nhận và theo dõi (Metrics):** sau khi sửa, kiểm tra p95/p99, RPS, error rate và tài nguyên quay về ngưỡng kỳ vọng trong đủ khoảng thời gian.

**Không đặt `traceId` làm label metric** để “liên kết” ba tín hiệu. Tương quan thường thực hiện qua khoảng thời gian, tên dịch vụ/route, log có trace ID và trace context được truyền giữa các thành phần. Một số backend hỗ trợ **exemplars** để gắn mẫu đo với trace cụ thể; khả năng này phụ thuộc registry, exporter và cấu hình tracing, không mặc định tồn tại ở mọi dự án.

## 10. Lỗi thường gặp và cách kiểm tra

| Hiện tượng | Khả năng thường gặp | Kiểm tra |
| --- | --- | --- |
| `/actuator/prometheus` trả 404 | Thiếu registry, chưa expose endpoint hoặc path quản trị khác | Kiểm tra dependency, cấu hình management và đường dẫn thật |
| Prometheus báo target DOWN | Sai host/port, container không truy cập được, TLS/auth hoặc firewall | Xem Targets của Prometheus và thử HTTP từ mạng nơi Prometheus chạy |
| Có endpoint nhưng không có metric mong đợi | Chưa có sự kiện, metric có tên khác hoặc instrumentation chưa bật | Tạo request mẫu và đối chiếu `/actuator/metrics` với đầu ra exporter |
| Không có `_bucket` để tính p95 | Histogram chưa bật cho meter cần đo | Kiểm tra distribution config và metric thực tế sau khi phát sinh request |
| Dashboard nhiều series hoặc scrape chậm | Tag chứa giá trị biến thiên vô hạn, quá nhiều bucket/instance | Rà soát tags, route template và số series |
| Rate/latency khác số liệu ứng dụng | Cửa sổ truy vấn, đơn vị, reset counter, aggregation hoặc filters sai | Kiểm tra loại meter, nhãn và điều kiện truy vấn |

Không suy luận nguyên nhân từ một biểu đồ đơn lẻ. Khi metrics cho thấy độ trễ tăng, trace và log giúp xác nhận có thật sự do database, downstream, thread pool hay code path cụ thể.

## 11. Bài thực hành tự kiểm tra

Một dịch vụ Spring Boot triển khai 3 instance, có API `POST /api/orders` và `GET /api/orders/{id}`. Hãy thực hiện các bước:

1. Bật Actuator và Prometheus registry; tạo request để xác nhận HTTP server metrics xuất hiện.
2. Thêm phép đo thời gian xử lý đơn hàng và số lần thử theo hai kết quả `success`/`error`.
3. Thiết kế dashboard gồm RPS, tỉ lệ 5xx, p95 latency và số lượng thử xử lý đơn mỗi giây; so sánh theo instance khi cần.
4. Giả lập một số request lỗi hoặc chậm, rồi quan sát sự thay đổi ở cửa sổ 5 phút. Kiểm tra xem dữ liệu PromQL khớp với số sự kiện đã tạo hay không.
5. Thử định nghĩa tag `orderId`, ước tính số series phát sinh nếu có 100.000 đơn hàng, sau đó thay nó bằng một tag có tập giá trị hữu hạn như `result`.

**Tiêu chí hoàn thành:** giải thích được Counter/Gauge/Timer, đọc đúng đơn vị và time window, viết được ít nhất một truy vấn rate và một truy vấn histogram p95, đồng thời lý giải tại sao ID riêng lẻ không được làm label cho metric.

## Ghi nhớ

- Metrics mô tả **xu hướng và mức độ** của hệ thống; logs mô tả sự kiện, traces mô tả đường đi và thời gian của từng yêu cầu.
- Trong Spring Boot, **Actuator + Micrometer registry + exporter** tạo đường đi từ instrument đến backend giám sát.
- Chọn instrument phù hợp, định nghĩa rõ ý nghĩa phép đo và dùng `rate()` cho Counter.
- **Cardinality là một phần của thiết kế**: giữ tag ít giá trị, kiểm soát histogram và kiểm tra series thực tế.
- Tính p95 toàn cụm bằng histogram có bucket thống nhất; kết hợp metrics với logs/traces để điều tra nguyên nhân và xác nhận hiệu quả khắc phục.

