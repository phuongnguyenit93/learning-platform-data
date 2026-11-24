# Giới hạn số giá trị nhãn metric và chi phí dữ liệu quan sát

## 1. Bối cảnh và mục tiêu

Trong module **SPRING_CLOUD_PROVIDER_INTEGRATION**, chúng ta thực hành tích hợp Spring Boot với các dịch vụ managed của **AWS, Azure và Google Cloud** qua các thư viện Spring Cloud và SDK tương ứng. Khi đưa metrics, logs và traces lên hệ thống quan sát, một vấn đề thường xuất hiện sau khi ứng dụng bắt đầu có traffic thật: số lượng time series và lượng dữ liệu tăng nhanh hơn dự kiến, kéo theo chi phí lưu trữ, ingestion và truy vấn.

Ví dụ, một developer thêm tag `customerId` vào metric `http.server.requests` để xem latency theo từng khách hàng. Trong môi trường test chỉ có vài khách hàng nên dashboard vẫn chạy tốt. Khi production có 80.000 khách hàng, mỗi khách hàng tạo một tập time series riêng cho method, URI, status và instance. Nếu metric còn có histogram buckets, số series có thể tăng lên hàng triệu hoặc lớn hơn.

Bài học này giải thích cách giới hạn cardinality và quản lý chi phí dữ liệu quan sát khi Spring Boot gửi telemetry tới Prometheus, Amazon CloudWatch, Azure Monitor hoặc Google Cloud Monitoring.

Sau bài này, bạn có thể:

- Phân biệt metric name, label, dimension, time series và sample.
- Ước lượng số time series từ tổ hợp nhãn và histogram buckets.
- Thiết kế bộ nhãn có tập giá trị hữu hạn, ổn định.
- Dùng Micrometer MeterFilter để chặn hoặc giới hạn meter/tag.
- Kiểm soát cardinality ở Prometheus, CloudWatch, Azure Monitor và Google Cloud Monitoring.
- Tách dữ liệu phù hợp cho metrics, logs và traces.
- Giảm chi phí bằng aggregation, sampling, retention, filtering và batch.
- Xây dựng ngân sách cardinality và kiểm tra trước khi triển khai production.

## 2. Cardinality là gì?

Trong hệ thống metrics, **cardinality** là số lượng giá trị khác nhau mà một nhãn có thể nhận, hoặc số lượng chuỗi thời gian riêng biệt được tạo bởi các tổ hợp nhãn.

Một metric thường gồm:

- **Metric name:** tên đại lượng được đo, ví dụ `http.server.requests`.
- **Label/tag/dimension:** thuộc tính dùng để phân nhóm, ví dụ `method`, `status`, `provider`.
- **Time series:** một metric name cùng một tập label-value cụ thể.
- **Sample:** một giá trị được ghi tại một thời điểm của time series.

Ví dụ:

~~~text
http_server_requests_seconds_count{
  method="GET",
  uri="/documents",
  status="200",
  instance="api-1"
}
~~~

Nếu method có 4 giá trị, uri có 20 giá trị, status có 5 giá trị và instance có 6 giá trị, số tổ hợp tối đa là:

\[
4 \times 20 \times 5 \times 6 = 12.000
\]

Đây là giới hạn tổ hợp lý thuyết. Số time series thực tế phụ thuộc những tổ hợp có phát sinh dữ liệu.

**Cardinality không phải số sample.** Một time series được scrape mỗi 15 giây trong một ngày có thể tạo 5.760 samples, nhưng cardinality của nó vẫn là một time series. Cardinality cao làm tăng số series phải quản lý; scrape frequency cao làm tăng số samples/ingestion trong cùng khoảng thời gian.

## 3. Vì sao cardinality cao gây vấn đề?

Mỗi time series có metadata, index, state và dữ liệu cần lưu trữ. Khi số series tăng:

- Prometheus cần nhiều RAM và disk hơn để giữ head series, index và chunks.
- Backend metrics cần quản lý nhiều stream hơn và có thể tăng chi phí ingestion/retention.
- Dashboard và query phải xử lý nhiều series, làm truy vấn chậm hoặc timeout.
- Alert rule tạo nhiều alert instances, gây nhiễu và tăng tải evaluation.
- Collector/exporter có thể dùng thêm CPU, memory và network.
- Một thay đổi nhỏ trong code có thể tạo hàng chục nghìn series mới mà không dễ nhận ra khi review.

Một số ví dụ về tag có cardinality cao:

| Tag | Vì sao nguy hiểm? | Nơi nên lưu |
|---|---|---|
| `user_id` / `customer_id` | Mỗi người dùng có thể là một giá trị | Log/traces có kiểm soát |
| `request_id` | Hầu hết request có ID riêng | Log và trace |
| `trace_id` / `span_id` | Gần như duy nhất cho mỗi trace/span | Trace backend/log correlation |
| `order_id` / `job_id` | Số lượng tăng theo nghiệp vụ | Log/traces |
| `file_name` / `object_key` | Có thể có hàng triệu giá trị | Log/traces |
| `url` đầy đủ | Path/query có thể chứa ID và tham số | Dùng route template |
| `exception_message` | Nội dung tự do, thường thay đổi liên tục | Log có redaction |
| `pod_uid` | Mỗi lần tạo Pod có UID mới | Resource metadata; cân nhắc instance label |

Không phải mọi dimension có nhiều giá trị đều sai. Một số hệ thống cần phân tích theo region hoặc queue. Điều quan trọng là hiểu chi phí của tổ hợp nhãn, giữ tập giá trị có giới hạn và chỉ thêm dimension khi có câu hỏi vận hành cụ thể.

## 4. Tính số time series trước khi thêm tag

Với metric có các nhãn độc lập, có thể ước lượng:

\[
N_{series} \approx \prod_{i=1}^{n} C_i
\]

Trong đó `C_i` là số giá trị dự kiến của nhãn thứ i. Công thức này là upper bound đơn giản; các tổ hợp không tồn tại sẽ làm số series thực tế thấp hơn.

Ví dụ một metric dependency:

| Label | Cardinality dự kiến |
|---|---:|
| provider: aws, azure, gcp | 3 |
| service: s3, blob, pubsub, rds, sqs | 5 |
| operation: upload, download, read, write, send, receive, ack, query | 8 |
| outcome: success, error, timeout | 3 |
| region: 4 region triển khai | 4 |
| **Tổ hợp tối đa** | **1.440** |

Nếu cùng metric này là classic histogram với 10 bucket boundaries hữu hạn, mỗi label set có thể tạo 13 series: 11 bucket series (10 bucket + +Inf), cộng `_sum` và `_count`.

\[
1.440 \times 13 = 18.720 \text{ time series}
\]

Nếu thêm `customer_id` với 10.000 giá trị:

\[
18.720 \times 10.000 = 187.200.000 \text{ time series}
\]

Đây là lý do một tag tưởng như hữu ích có thể làm chi phí tăng đột biến. Histogram tạo nhiều series hơn Counter/Gauge cùng label set; native histogram có mô hình lưu trữ khác, nên không áp dụng máy móc hệ số bucket cổ điển cho mọi backend.

### 4.1. Cardinality budget

Trước khi thêm tag, ghi lại:

- Metric name và loại meter.
- Các label dự kiến.
- Số giá trị tối đa cho từng label.
- Số instance/region/cluster.
- Số bucket nếu là histogram.
- Số time series ước lượng.
- Câu hỏi vận hành mà dimension đó giúp trả lời.
- Người sở hữu metric và thời hạn review.

Một nhóm có thể đặt ngân sách ví dụ: một metric nghiệp vụ không quá 500 series trên mỗi môi trường, histogram không quá 5.000 series toàn service. Đây là ngưỡng nội bộ minh họa, không phải giới hạn mặc định của Prometheus hay cloud provider.

## 5. Chọn label có tập giá trị hữu hạn

Label tốt thường mô tả một thuộc tính ổn định và có số giá trị nhỏ:

- `provider`: aws, azure, gcp.
- `operation`: upload, download, send_message, receive_message.
- `outcome`: success, error, timeout.
- `error_type`: throttled, timeout, authorization, not_found, server, other.
- `environment`: dev, staging, production.
- `region`: một danh sách region triển khai đã biết.

Label xấu thường chứa định danh hoặc nội dung tự do:

- `customer_id=tenant-93821`.
- `request_id=8d9...`.
- `path=/documents/849201/download`.
- `exception_message=Connection reset by peer at 10:15:...`.

Nếu muốn phân tích HTTP theo endpoint, dùng route template như `/documents/{documentId}` thay vì URL thực tế `/documents/849201`. Nếu muốn phân tích lỗi theo exception, chuẩn hóa thành enum hữu hạn như `timeout`, `permission_denied` hoặc `other`.

### 5.1. Chuẩn hóa giá trị đầu vào

Không truyền thẳng dữ liệu từ request hoặc SDK vào metric tag. Hãy map về một nhóm hữu hạn:

~~~java
public enum Operation {
    UPLOAD,
    DOWNLOAD,
    SEND_MESSAGE,
    RECEIVE_MESSAGE,
    OTHER
}

public static Operation normalizeOperation(String raw) {
    if (raw == null) {
        return Operation.OTHER;
    }

    return switch (raw) {
        case "upload", "put_object" -> Operation.UPLOAD;
        case "download", "get_object" -> Operation.DOWNLOAD;
        case "send", "send_message" -> Operation.SEND_MESSAGE;
        case "receive", "receive_message" -> Operation.RECEIVE_MESSAGE;
        default -> Operation.OTHER;
    };
}
~~~

Metric tag dùng enum name hoặc một string mapping ổn định. Raw value có thể ghi vào log khi cần điều tra, sau khi kiểm tra dữ liệu nhạy cảm.

### 5.2. Không dùng URL hoặc resource ID làm label

Với HTTP server metrics, dùng URI template do framework cung cấp. Tránh tag URL đầy đủ, query string hoặc path chưa được chuẩn hóa. Với cloud storage, tag `container` hoặc `bucket` chỉ khi danh sách nhỏ và thực sự cần so sánh; không tag object key.

Với queue, `destination` có thể hợp lý nếu số queue/topic cố định. Nếu destination chứa tenant hoặc dynamic queue name, hãy map sang loại queue như `document-jobs`, `billing-events` hoặc `other`.

## 6. Micrometer: giới hạn meter và tag

Micrometer cho phép lọc meter trước khi registry ghi nhận chúng. `MeterFilter` là lớp bảo vệ hữu ích để ngăn một meter không mong muốn hoặc giới hạn số giá trị tag.

### 6.1. Giới hạn số meter và tag values

Ví dụ:

~~~java
import io.micrometer.core.instrument.config.MeterFilter;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class MetricsCardinalityConfiguration {

    @Bean
    MeterFilter limitCloudMetricTags() {
        return MeterFilter.maximumAllowableTags(
                "cloud.dependency",
                "operation",
                20,
                MeterFilter.deny());
    }

    @Bean
    MeterFilter limitTotalMeters() {
        return MeterFilter.maximumAllowableMetrics(500);
    }
}
~~~

`maximumAllowableTags` giới hạn số giá trị khác nhau của một tag key trên các meter khớp prefix. Khi vượt giới hạn, meter mới bị từ chối theo filter được truyền vào; trong ví dụ này là `MeterFilter.deny()`.

`maximumAllowableMetrics` giới hạn số meter ID được registry chấp nhận. Đây là hàng rào cuối cùng; nó không thay thế thiết kế label tốt. Nếu giới hạn bị chạm, một số metric mới có thể không được ghi, vì vậy cần kiểm tra và cảnh báo khi filter bắt đầu từ chối meter.

Lưu ý: một MeterFilter áp dụng ở cấp registry có thể ảnh hưởng nhiều backend trong cùng ứng dụng. Nếu chỉ muốn giới hạn CloudWatch hoặc một registry cụ thể, gắn filter vào registry tương ứng theo cách cấu hình của phiên bản Micrometer/Spring Boot đang dùng.

### 6.2. Chặn metric không cần thiết

Có thể dùng allow-list:

~~~java
import io.micrometer.core.instrument.config.MeterFilter;
import java.util.Set;
import org.springframework.context.annotation.Bean;

@Bean
MeterFilter applicationMetricAllowList() {
    Set<String> allowed = Set.of(
            "http.server.requests",
            "jvm.memory.used",
            "jvm.gc.pause",
            "cloud.dependency.duration",
            "cloud.dependency.errors",
            "messaging.process.duration");

    return MeterFilter.denyUnless(
            id -> allowed.contains(id.getName()));
}
~~~

Allow-list cần dựa trên meter thực sự được ứng dụng đăng ký. Khi bật filter, những meter không nằm trong danh sách sẽ không xuất hiện ở registry áp dụng filter. Kiểm thử profile local/staging trước khi bật production để tránh vô tình chặn health hoặc metric quan trọng.

### 6.3. Đặt common tags có kiểm soát

Common tags giúp thêm metadata ổn định cho mọi meter:

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.boot.actuate.autoconfigure.metrics.MeterRegistryCustomizer;
import org.springframework.context.annotation.Bean;

@Bean
MeterRegistryCustomizer<MeterRegistry> commonTags() {
    return registry -> registry.config().commonTags(
            "application", "provider-integration",
            "environment", "production");
}
~~~

Không thêm instance UUID, request ID hoặc deployment timestamp làm common tag. Với Kubernetes, cần cân nhắc Pod/instance label: nó có thể hữu ích cho debug nhưng làm series churn tăng khi Pod liên tục được tạo mới.

## 7. Prometheus: time series, histogram và scrape volume

Prometheus nhận metric theo chuỗi thời gian, trong đó mỗi tổ hợp metric name và label set là một series. Cardinality tăng khi:

- Thêm label mới.
- Một label có thêm nhiều giá trị.
- Instance/pod/endpoint thay đổi liên tục.
- Histogram có nhiều bucket và nhiều label combinations.

### 7.1. Classic histogram

Với classic histogram, mỗi label set tạo các bucket counter, cộng thêm `_sum` và `_count`. Ví dụ 8 bucket boundaries có thể tạo 11 series cho mỗi label set: 9 bucket (8 bucket + +Inf), 1 sum và 1 count.

Nếu 2.000 label sets được tạo, metric histogram này có thể tạo khoảng 22.000 series.

Không tăng số bucket chỉ vì muốn percentile mịn hơn. Chọn bucket theo SLO/latency range có ý nghĩa, ví dụ 50 ms, 100 ms, 250 ms, 500 ms, 1 s và 2 s.

### 7.2. Scrape interval và samples

Scrape interval không làm thay đổi số series đang active, nhưng ảnh hưởng số samples:

\[
SamplesPerDay = ActiveSeries \times \frac{86.400}{ScrapeIntervalSeconds}
\]

Ví dụ 10.000 active series, scrape mỗi 15 giây:

\[
10.000 \times \frac{86.400}{15}=57.600.000
\]

Hệ thống thu khoảng 57,6 triệu samples/ngày nếu tất cả series đều có mặt ở mọi lần scrape. Giảm scrape interval có thể tăng độ phân giải và khả năng phát hiện spike, nhưng cũng tăng ingestion, storage và query cost.

### 7.3. Relabeling chỉ là lớp bảo vệ bổ sung

Prometheus có thể dùng metric relabeling để drop metric hoặc label trước khi ingest. Ví dụ loại bỏ một metric debug:

~~~yaml
scrape_configs:
  - job_name: provider-integration
    static_configs:
      - targets: ["provider-integration:8080"]
    metrics_path: /actuator/prometheus
    metric_relabel_configs:
      - source_labels: [__name__]
        regex: "debug_.*"
        action: drop
~~~

Relabeling giảm số series được lưu trong Prometheus, nhưng exporter vẫn phải tạo và scrape dữ liệu trước khi drop. Vì vậy, chặn cardinality ngay trong ứng dụng bằng Micrometer và chuẩn hóa label vẫn là lớp kiểm soát chính.

## 8. CloudWatch: dimension tạo custom metric

Trong Amazon CloudWatch, một custom metric được xác định bởi namespace, metric name và tổ hợp dimensions. Mỗi tổ hợp dimension values có thể được tính là một custom metric riêng.

Ví dụ:

~~~text
Namespace: ProviderIntegration
MetricName: CloudDependencyLatency
Dimensions:
  Provider = aws
  Service = s3
  Operation = get_object
  Environment = production
~~~

Nếu thêm dimension `CustomerId` với hàng nghìn giá trị, CloudWatch sẽ nhận nhiều metric identity khác nhau. Một dimension có thể làm số custom metrics tăng theo tích của các giá trị dimension còn lại.

### 8.1. Quy tắc cho CloudWatch

- Dùng namespace theo service/domain, ví dụ `ProviderIntegration`.
- Chỉ thêm dimension có giá trị nhỏ và cần cho dashboard/alert.
- Không đưa request ID, trace ID, user ID, object key hoặc exception message vào dimension.
- Dùng metric filter/allow-list trong Micrometer registry.
- Chọn export step và resolution theo nhu cầu vận hành.
- Kiểm tra số custom metrics và chi phí trong Cost Explorer/CloudWatch usage.

CloudWatch hỗ trợ standard-resolution và high-resolution custom metrics; high-resolution có thể tăng chi phí và không phải metric nào cũng cần cập nhật từng giây. Đừng dùng high-resolution cho mọi meter chỉ vì có thể.

### 8.2. Metric math không thay thế dimension design

Metric math và dashboard có thể tổng hợp nhiều metric, nhưng không làm giảm số custom metric đã được publish. Muốn giảm chi phí, cần giảm số tổ hợp dimension ngay từ ứng dụng hoặc exporter.

## 9. Azure Monitor: metric dimensions và custom telemetry

Azure Monitor có platform metrics và custom metrics. Platform metrics do Azure resource phát ra; custom metrics do ứng dụng hoặc agent gửi. Với Application Insights, custom metrics và telemetry dimensions cũng có thể làm tăng ingestion và số time series cần truy vấn.

### 9.1. Chọn dimensions có ích

Ví dụ custom metric:

~~~text
Metric: cloud_dependency_duration
Dimensions:
  cloud.provider = azure
  cloud.service = blob
  operation = upload
  outcome = success
  cloud.region = southeastasia
~~~

Những dimension này có thể giúp nhóm theo provider, operation và outcome. Tránh thêm documentId, tenantId hoặc blobName.

### 9.2. Giới hạn và phân biệt metric với log

- Dùng metric dimensions để phân nhóm xu hướng có cardinality giới hạn.
- Ghi request ID, correlation ID và resource path vào structured logs/traces theo chính sách.
- Với Application Insights, kiểm soát custom dimensions và sampling để tránh ingestion volume ngoài dự kiến.
- Kiểm tra giới hạn dimensions/cardinality của loại metric và workspace đang dùng; Azure Monitor platform metrics, custom metrics và Application Insights không có cùng semantics hoặc pricing model.
- Không giả định mọi custom dimension đều được lưu/hiển thị như nhau trong Metrics Explorer và Logs.

Chi phí Azure Monitor phụ thuộc loại dữ liệu, vùng, ingestion, retention, export và gói/commitment đang áp dụng. Hãy xem pricing của workspace/resource thực tế trước khi chọn sampling và retention.

## 10. Google Cloud Monitoring: metric labels và monitored resource

Cloud Monitoring xác định time series dựa trên metric type, monitored resource và các label values. Vì vậy, số tổ hợp metric labels cộng resource labels ảnh hưởng trực tiếp số series.

Ví dụ metric:

~~~text
custom.googleapis.com/cloud/dependency/duration
Resource:
  service_name = provider-integration
  location = asia-southeast1
Metric labels:
  provider = azure
  operation = upload
  outcome = success
~~~

### 10.1. Thiết kế labels

- Dùng resource labels chuẩn để mô tả service, location và workload.
- Dùng metric labels cho provider, operation, outcome hoặc error class có tập giá trị nhỏ.
- Không đưa request ID, trace ID, user ID, tenant ID hoặc object key vào metric labels.
- Hạn chế tạo metric descriptor mới cho từng business object.
- Theo dõi số active time series và ingestion volume theo metric type.

Google Cloud Monitoring có giới hạn trên số labels/descriptor và cách tính giá dựa trên loại metric, samples/time series và sản phẩm đang dùng. Kiểm tra tài liệu limits và pricing hiện hành; không lấy một con số quota của project khác làm mặc định cho mọi môi trường.

### 10.2. Aggregation trước khi export

Nếu ứng dụng cần số liệu theo tenant, hãy cân nhắc tổng hợp ở tầng nghiệp vụ:

- Đếm tổng request theo plan/tier thay vì theo tenant ID.
- Tính p95 latency theo service/operation thay vì theo từng customer.
- Ghi chi tiết một số request vào log/trace có sampling và quyền truy cập.
- Chỉ tạo metric per-tenant khi có yêu cầu sản phẩm rõ ràng, số tenant được giới hạn và đã đánh giá chi phí.

## 11. Metrics, logs và traces có vai trò khác nhau

Không nên cố nhồi mọi thuộc tính vào metric label. Chọn loại telemetry theo câu hỏi cần trả lời:

| Câu hỏi | Loại telemetry | Ví dụ field |
|---|---|---|
| Có bao nhiêu upload lỗi trong 5 phút? | Metric | operation, outcome, provider |
| Upload của khách hàng nào gặp lỗi? | Log có cấu trúc | correlation_id, job_id, tenant theo policy |
| Request đã đi qua service nào? | Trace | trace_id, span_id, service, dependency |
| Một lần gọi S3 trả request ID nào? | Log/trace | provider_request_id |
| p95 latency của Blob upload là bao nhiêu? | Histogram metric | provider, service, operation |
| Một message cụ thể đã retry mấy lần? | Log/trace/event | message_id, delivery_attempt |

Log có thể chứa ID duy nhất để điều tra, nhưng vẫn có chi phí ingestion, indexing, storage và query. Trace có thể chứa nhiều span và attributes; sampling giảm volume nhưng cần giữ trace quan trọng. Metric cần dimensions ổn định để tổng hợp nhanh.

**Không chuyển một tag cardinality cao từ metric sang log mà không đánh giá privacy/retention/index cost.** Hãy chọn nơi lưu và chính sách truy cập phù hợp.

## 12. Giảm chi phí metrics

Các biện pháp phổ biến:

1. **Giảm label cardinality:** loại ID và raw strings; chuẩn hóa enum.
2. **Giảm số meter:** chỉ publish meter có câu hỏi vận hành rõ ràng.
3. **Giảm histogram buckets:** chọn bucket theo SLO thay vì quá dày.
4. **Aggregation:** tổng hợp theo service/operation trước khi export.
5. **Sampling hoặc downsampling:** áp dụng với hệ thống hỗ trợ và hiểu ảnh hưởng tới độ chính xác.
6. **Điều chỉnh export/scrape interval:** chọn độ phân giải phù hợp.
7. **Giảm retention cho dữ liệu chi tiết:** giữ dữ liệu dài hạn ở mức aggregate nếu phù hợp.
8. **Xóa meter cũ:** ngừng publish metric không còn được dashboard/alert sử dụng.

Không giảm sampling hoặc scrape interval một cách mù quáng. Metric dùng cho SLO, alert hoặc phát hiện sự cố nhanh cần độ phân giải đủ để nhận biết vấn đề.

## 13. Giảm chi phí logs

Log cost thường chịu ảnh hưởng bởi:

- Số bytes được ingest.
- Số event mỗi giây.
- Retention và archive.
- Indexing/analytics/query.
- Export sang nhiều workspace hoặc region.
- Mức độ verbose của log và stack trace.

Các cách giảm:

- Dùng INFO cho sự kiện bình thường, WARN/ERROR cho bất thường; tránh DEBUG/HTTP wire logging thường trực.
- Không log toàn bộ request/response body.
- Giới hạn stack trace và exception message.
- Dùng sampling cho access log thành công nếu nền tảng và yêu cầu audit cho phép; giữ log lỗi và security events theo policy.
- Loại bỏ field lặp lại hoặc payload không cần thiết.
- Đặt retention theo loại log: security/audit, application, debug.
- Dùng structured JSON nhưng tránh lặp cùng thông tin ở cả message string và field.

Không sampling hoặc drop security/audit logs nếu chính sách yêu cầu phải lưu đầy đủ. Cần phân biệt log phục vụ debug với log phục vụ audit/compliance.

## 14. Giảm chi phí traces

Trace volume thường phụ thuộc:

- Số request/operation.
- Số span trên mỗi trace.
- Sampling probability.
- Số attributes/events trên mỗi span.
- Kích thước exception/stack trace.
- Retention và query.

Ví dụ một request qua API, storage, queue producer, worker, database và HTTP dependency có thể tạo 8–15 spans. Nếu 100.000 request/giờ và lấy mẫu 100%, số spans có thể lên đến hàng triệu mỗi giờ.

Các biện pháp:

- Dùng parent-based sampling để giữ tính nhất quán trong một trace.
- Sampling thấp hơn cho traffic thành công có volume lớn; giữ tỷ lệ phù hợp cho lỗi/latency cao bằng tail sampling nếu collector/backend hỗ trợ.
- Không tạo span cho mọi dòng code hoặc getter nhỏ.
- Giới hạn span attributes và events.
- Không gắn payload lớn hoặc PII vào span.
- Dùng metric để theo dõi toàn bộ traffic; dùng trace để điều tra một mẫu đại diện.

Tail sampling cần collector có đủ tài nguyên và thời gian chờ để gom spans của trace trước khi ra quyết định. Nếu cấu hình không đúng, một số spans có thể bị mất hoặc trace bị tách.

## 15. Ngân sách và quy trình review metric mới

Trước khi merge một metric mới, reviewer có thể yêu cầu bảng sau:

| Hạng mục | Câu hỏi cần trả lời |
|---|---|
| Purpose | Metric trả lời câu hỏi vận hành nào? |
| Name/type | Counter, Gauge, Timer hay DistributionSummary? |
| Labels | Những label nào thực sự cần? |
| Cardinality | Số giá trị tối đa của từng label? |
| Series estimate | Tổ hợp label và histogram buckets tạo bao nhiêu series? |
| Scope | Mỗi instance, service, cluster hay region? |
| Backend | Prometheus, CloudWatch, Azure Monitor hay Cloud Monitoring? |
| Cost | Ingestion, custom metric, retention, query có ảnh hưởng gì? |
| Owner | Ai chịu trách nhiệm khi cardinality tăng? |
| Lifecycle | Khi nào metric được loại bỏ hoặc đổi schema? |

Không đổi tên metric hoặc label tùy tiện sau khi đã có dashboard/alert. Việc đổi label key tạo một tập time series mới và có thể làm dashboard cũ không còn dữ liệu.

## 16. Theo dõi cardinality trong production

### 16.1. Prometheus

Prometheus cung cấp metric nội bộ về số series và dung lượng TSDB, ví dụ:

- `prometheus_tsdb_head_series`: số series trong head block.
- `prometheus_tsdb_head_samples_appended_total`: số samples được append.
- `prometheus_tsdb_head_series_created_total`: số series mới được tạo.
- `scrape_samples_post_metric_relabeling`: số samples sau metric relabeling theo target.

Tên metric có thể thay đổi theo version/build và cách triển khai; kiểm tra `/metrics` của Prometheus trước khi tạo dashboard.

### 16.2. Cloud provider

- **CloudWatch:** theo dõi custom metrics/dimensions, usage và chi phí theo namespace/account.
- **Azure Monitor:** theo dõi ingestion, custom metrics, workspace usage và retention.
- **Google Cloud Monitoring:** theo dõi active time series, metric descriptors, samples và usage.

Đặt alert khi cardinality hoặc ingestion tăng nhanh so với baseline, ví dụ tăng gấp đôi trong một ngày. Ngưỡng phải phù hợp với traffic và chu kỳ deployment; tránh dùng một threshold cố định cho mọi service.

## 17. Kiểm thử và kiểm soát cardinality trong Spring Boot

Có thể test số meter và tag values bằng `SimpleMeterRegistry`:

~~~java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.config.MeterFilter;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;

class MetricCardinalityTest {
    @Test
    void deniesNewOperationValuesAfterLimit() {
        SimpleMeterRegistry registry = new SimpleMeterRegistry();
        registry.config().meterFilter(
                MeterFilter.maximumAllowableTags(
                        "cloud.dependency",
                        "operation",
                        2,
                        MeterFilter.deny()));

        Counter.builder("cloud.dependency.calls")
                .tag("operation", "upload")
                .register(registry)
                .increment();

        Counter.builder("cloud.dependency.calls")
                .tag("operation", "download")
                .register(registry)
                .increment();

        Counter.builder("cloud.dependency.calls")
                .tag("operation", "dynamic-operation-123")
                .register(registry)
                .increment();

        assertEquals(2, registry.getMeters().size());
        assertEquals(
                0,
                registry.find("cloud.dependency.calls")
                        .tag("operation", "dynamic-operation-123")
                        .counters()
                        .size());
    }
}
~~~

Test trên minh họa giới hạn hai giá trị operation. Trong dự án thực, thêm test cho:

- Raw URL được chuẩn hóa về route template.
- Customer/request/object ID không xuất hiện trong metric tags.
- Error type chỉ nhận enum hữu hạn.
- Histogram bucket count nằm trong ngân sách.
- MeterFilter không chặn metric SLO/health quan trọng.
- Exported metric tại `/actuator/prometheus` không chứa tag ngoài allow-list.

Lưu ý: test filter chỉ chứng minh registry từ chối meter vượt ngưỡng. Nó không chứng minh CloudWatch/Azure/Google billing đã giảm; cần kiểm tra backend sau khi deploy.

## 18. Troubleshooting

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Prometheus RAM tăng nhanh | Nhiều series hoặc label có giá trị động | Dùng cardinality analysis, loại ID và chuẩn hóa route |
| Histogram tạo quá nhiều series | Quá nhiều buckets kết hợp nhiều labels | Giảm buckets, labels hoặc tách metric |
| Dashboard query chậm | Query trả về hàng trăm nghìn series | Giảm dimensions, aggregate trước và giới hạn time range |
| CloudWatch custom metric bill tăng | Thêm dimension có cardinality cao | Bỏ dimension, dùng MeterFilter và kiểm tra metric identity |
| Azure Monitor ingestion tăng | Custom metrics/logs nhiều hoặc dimensions thay đổi | Kiểm tra workspace usage, sampling và field schema |
| Google Monitoring active time series tăng | Nhiều metric label/resource label combinations | Chuẩn hóa labels và aggregation |
| Meter mới không xuất hiện | MeterFilter deny hoặc allow-list thiếu tên | Kiểm tra filter và registry thực tế |
| Metrics biến mất sau khi đặt limit | MeterFilter từ chối giá trị mới | Xác định label gây tăng cardinality và map về nhóm hữu hạn |
| Series churn cao dù cardinality không lớn | Pod/instance ID thay đổi liên tục | Dùng resource labels có kiểm soát và giảm churn |
| Logs chi phí cao | DEBUG, body hoặc stack trace lớn | Giảm verbosity, giới hạn payload và retention |
| Trace backend tăng ingestion | Sampling cao, spans/attributes quá nhiều | Điều chỉnh sampling, span boundaries và tail sampling |
| Relabeling không giảm app memory | Drop xảy ra sau scrape | Chặn meter/tag ngay trong ứng dụng |

## 19. Bài tập thực hành và câu hỏi tự kiểm tra

**Tình huống A — Tag customerId:** Một metric `document.preview.duration` có provider, operation, outcome và customerId. Hãy tính số series khi có 3 provider, 8 operation, 3 outcome và 20.000 customer. Đề xuất thay thế customerId bằng nhóm plan/tier hoặc chuyển chi tiết sang logs.

**Tình huống B — Histogram:** Một metric HTTP có 12 bucket boundaries, 5 route templates, 4 methods, 5 status classes và 6 instances. Hãy ước lượng số series classic histogram và đề xuất giảm buckets/labels.

**Tình huống C — CloudWatch bill:** Sau khi thêm dimension `objectKey`, custom metric tăng mạnh. Hãy giải thích metric identity theo namespace/name/dimensions và thiết kế lại dimension set.

**Tình huống D — Azure Monitor:** Workspace ingestion tăng sau khi thêm custom properties và log request/response body. Hãy phân biệt metric dimensions với log custom dimensions và đưa ra chính sách sampling/retention phù hợp.

**Tình huống E — Google Cloud Monitoring:** Một custom metric có labels region, tenant, orderId và operation. Hãy tính upper bound, xác định label nào cần loại bỏ và đề xuất aggregation trước export.

**Tình huống F — Micrometer:** Hãy thêm `MeterFilter.maximumAllowableTags` cho metric dependency, viết unit test xác minh tag thứ ba bị từ chối và kiểm tra `/actuator/prometheus`.

**Tình huống G — Telemetry cost:** Một service có metrics, logs và traces tăng gấp đôi. Hãy xác định cần xem active time series, samples/day, bytes ingested, spans/request, sampling rate và retention để tìm nguồn chi phí.

### Câu hỏi tự kiểm tra

1. **Cardinality của một time series là gì?** Một tổ hợp metric name và label values xác định một series riêng.
2. **Cardinality khác sample count thế nào?** Cardinality là số series; sample count là số điểm dữ liệu theo thời gian.
3. **Vì sao customerId không phù hợp làm metric label?** Số giá trị tăng theo số khách hàng và nhân với mọi label khác.
4. **Histogram classic làm tăng series ra sao?** Mỗi label set tạo bucket series cộng `_sum` và `_count`.
5. **Micrometer MeterFilter dùng để làm gì?** Cho phép chặn meter, giới hạn số meter hoặc số tag values.
6. **CloudWatch custom metric identity phụ thuộc gì?** Namespace, metric name và tổ hợp dimensions.
7. **Azure Monitor platform metrics và custom metrics có cùng semantics không?** Không; giới hạn và pricing phụ thuộc loại dữ liệu/resource.
8. **Google Cloud Monitoring time series phụ thuộc gì?** Metric type, monitored resource và label values.
9. **Có nên chuyển request ID từ metric sang log không?** Có thể, nếu cần điều tra và đã kiểm soát privacy, indexing và retention.
10. **Scrape interval có làm tăng active series không?** Không trực tiếp; nó làm tăng số samples/ingestion theo thời gian.
11. **Relabeling có thay thế giới hạn cardinality trong ứng dụng không?** Không; nó drop sau scrape, nên exporter vẫn tạo dữ liệu.
12. **Ba nhóm chi phí observability cần theo dõi là gì?** Metrics ingestion/time series, log bytes/retention/query và trace spans/sampling/retention.

## 20. Tổng kết

Cardinality tăng khi metric có nhiều nhãn hoặc một nhãn nhận quá nhiều giá trị. Số series có thể ước lượng bằng tích cardinality của các label; classic histogram còn nhân thêm bucket, sum và count. Vì vậy, cần thiết kế label hữu hạn trước khi instrument và review mọi dimension mới.

Trong Spring Boot, dùng Micrometer MeterFilter để giới hạn meter/tag, chuẩn hóa operation và error type, giữ request/customer/object IDs ở logs/traces có kiểm soát. Prometheus cần quản lý series, bucket và scrape volume; CloudWatch tính custom metric theo namespace/name/dimensions; Azure Monitor cần phân biệt platform/custom metrics và log ingestion; Google Cloud Monitoring cần quản lý metric labels cùng monitored resource labels.

Chi phí observability không chỉ đến từ metrics. Logs chịu ảnh hưởng bởi bytes ingestion, indexing và retention; traces chịu ảnh hưởng bởi số spans, attributes và sampling. Kết hợp cardinality budget, aggregation, sampling, retention, dashboard usage và kiểm thử trước khi release để giữ dữ liệu quan sát hữu ích mà vẫn kiểm soát được chi phí.

### Tài liệu tham khảo chính thức

- [Micrometer — Meter Filters](https://docs.micrometer.io/micrometer/reference/concepts/meter-filters.html)
- [Micrometer — Histograms and Percentiles](https://docs.micrometer.io/micrometer/reference/concepts/histogram-quantiles.html)
- [Prometheus — Instrumentation practices](https://prometheus.io/docs/practices/instrumentation/)
- [Prometheus — Metric and label naming](https://prometheus.io/docs/practices/naming/)
- [Prometheus — Configuration and metric relabeling](https://prometheus.io/docs/prometheus/latest/configuration/configuration/)
- [Amazon CloudWatch — Dimensions](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/cloudwatch_concepts.html#Dimension)
- [Amazon CloudWatch — Pricing](https://aws.amazon.com/cloudwatch/pricing/)
- [Azure Monitor — Metrics overview](https://learn.microsoft.com/azure/azure-monitor/metrics/data-platform-metrics)
- [Azure Monitor — Usage and estimated costs](https://learn.microsoft.com/azure/azure-monitor/fundamentals/cost-usage)
- [Azure Monitor — Pricing](https://azure.microsoft.com/pricing/details/monitor/)
- [Google Cloud Monitoring — Metrics model](https://docs.cloud.google.com/monitoring/api/v3/metrics)
- [Google Cloud Monitoring — Quotas and limits](https://docs.cloud.google.com/monitoring/quotas)
- [Google Cloud Observability — Pricing](https://cloud.google.com/stackdriver/pricing)
- [OpenTelemetry — Metrics SDK cardinality limits](https://opentelemetry.io/docs/specs/otel/metrics/sdk/)
