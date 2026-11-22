# Thực hành xây dashboard SLO cho API Java

Một API Java có thể trả về HTTP 200 trong phần lớn thời gian nhưng vẫn làm người dùng thất vọng vì độ trễ cao, lỗi tăng theo từng đợt hoặc một dependency thường xuyên timeout. Dashboard hạ tầng cho biết CPU, memory và số instance; dashboard SLO bổ sung góc nhìn quan trọng hơn: dịch vụ có đáp ứng cam kết về chất lượng mà người dùng thực sự trải nghiệm hay không, và còn bao nhiêu error budget để tiếp tục phát hành thay đổi.

Trong Google Cloud, Cloud Monitoring cung cấp Service Monitoring (hiện được tổ chức trong tài liệu SLO monitoring) để định nghĩa Service Level Indicator (SLI), Service Level Objective (SLO), error budget và cảnh báo burn rate. Bạn có thể đưa các chỉ số này vào custom dashboard, kết hợp với metric, log, trace và incident để đội phát triển, SRE và người trực cùng nhìn vào một bức tranh vận hành.

Bài thực hành xây dashboard cho một API Java chạy trên Cloud Run hoặc GKE. Ví dụ sử dụng OpenTelemetry để thu thập request count và latency, tạo custom service, định nghĩa SLO availability và latency, rồi đưa trạng thái SLO cùng các chỉ số vận hành vào Cloud Monitoring dashboard.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt SLI, SLO, SLA và error budget trong vận hành API.
- Chọn request-based SLI cho availability và latency SLI phù hợp với API Java.
- Thiết kế metric có metric kind, value type và labels phù hợp với Cloud Monitoring SLO.
- Instrument ứng dụng Java bằng OpenTelemetry để ghi request count, outcome và latency.
- Tạo custom service và SLO trong Cloud Monitoring.
- Xây dashboard hiển thị SLO health, compliance, error budget, traffic, lỗi và latency.
- Tạo fast-burn và slow-burn alert để phát hiện tiêu thụ error budget quá nhanh.
- Kiểm chứng dữ liệu, xử lý thiếu metric và tránh dashboard gây hiểu nhầm.

## 1. Bài toán và kiến trúc thực hành

Giả sử nhóm phát triển vận hành API `orders-api` để tạo và tra cứu đơn hàng. API chạy trên Cloud Run hoặc GKE, nhận request từ ứng dụng web và các dịch vụ nội bộ. Nhóm muốn theo dõi hai mục tiêu:

1. **Availability:** ít nhất 99,9% request hợp lệ được xử lý thành công trong cửa sổ 30 ngày.
2. **Latency:** ít nhất 99% request hợp lệ hoàn tất trong tối đa 300 ms trong cửa sổ 30 ngày.

Các mục tiêu này là ví dụ ban đầu để thực hành. Khi áp dụng cho production, nhóm sản phẩm và SRE cần chọn ngưỡng dựa trên trải nghiệm người dùng, traffic thực tế, đặc điểm endpoint và lịch sử độ tin cậy.

### Kiến trúc tổng thể

~~~mermaid
flowchart LR
    A[Client] --> B[Java API: Cloud Run / GKE]
    B --> C[OpenTelemetry SDK]
    C --> D[OTLP]
    D --> E[OpenTelemetry Collector]
    E --> F[Cloud Monitoring metrics]
    B --> G[Structured logs]
    G --> H[Cloud Logging]
    B --> I[Trace spans]
    I --> J[Cloud Trace]
    F --> K[Custom Service và SLO]
    K --> L[SLO dashboard]
    K --> M[Burn-rate alert policies]
    F --> L
    H --> L
    J --> L
    M --> N[Notification channels / on-call]
~~~

Các thành phần đảm nhiệm vai trò khác nhau:

| Thành phần | Vai trò trong bài thực hành |
|---|---|
| Java API | Phát sinh request, response status và latency |
| OpenTelemetry SDK | Thu thập metric và trace trong ứng dụng |
| OpenTelemetry Collector | Nhận OTLP và xuất telemetry tới Google Cloud |
| Cloud Monitoring | Lưu metric, tính SLI/SLO, hiển thị dashboard và alert |
| Cloud Logging | Lưu log ứng dụng và sự kiện lỗi |
| Cloud Trace | Điều tra độ trễ qua các span và dependency |
| Notification channel | Gửi cảnh báo tới người trực hoặc hệ thống xử lý |

Cloud Monitoring không tự suy ra mọi SLI từ mã Java. Với custom service, bạn cần chọn metric và định nghĩa cách phân loại request tốt, request xấu và tổng request. Việc instrument đúng từ ứng dụng là nền tảng để dashboard phản ánh chính xác chất lượng dịch vụ.

## 2. Phân biệt SLI, SLO, SLA và error budget

Các khái niệm này liên quan nhưng có ý nghĩa riêng:

| Khái niệm | Ý nghĩa | Ví dụ cho orders-api |
|---|---|---|
| SLI (Service Level Indicator) | Chỉ số đo chất lượng thực tế | Tỷ lệ request thành công hoặc tỷ lệ request dưới 300 ms |
| SLO (Service Level Objective) | Mục tiêu định lượng cho SLI trong một khoảng thời gian | 99,9% request thành công trong 30 ngày |
| SLA (Service Level Agreement) | Cam kết dịch vụ với khách hàng, thường gắn với điều khoản và biện pháp xử lý | Cam kết availability có điều khoản service credit |
| Error budget | Phần chất lượng được phép không đạt mà vẫn còn trong SLO | Với SLO 99,9%, tối đa 0,1% request đủ điều kiện có thể thất bại |

Một SLI mô tả cách đo; SLO mô tả mức cần đạt; SLA là cam kết bên ngoài có hệ quả hợp đồng. Không nên xem SLO nội bộ là SLA nếu chưa có điều khoản và phạm vi cam kết tương ứng.

### Công thức error budget

Với SLO goal (G), error budget fraction là:

$$
B = 1-G
$$

Nếu SLO là 99,9%:

$$
B = 1-0.999 = 0.001 = 0.1%
$$

Với 1.000.000 request đủ điều kiện trong compliance period:

1.000.000 x 0.001 = 1.000 request

Nhóm có thể có tối đa 1.000 request xấu trước khi không còn đạt mục tiêu availability của kỳ đó. Đây là budget tính theo số request, không phải số phút downtime. Với request-based SLO, lượng request thực tế quyết định quy mô error budget.

Với SLO 99% cho latency, 1% request có thể vượt ngưỡng 300 ms trong kỳ. Error budget của latency SLO được tính riêng; không cộng chung với error budget availability vì hai SLI đo hai khía cạnh chất lượng khác nhau.

### Chọn compliance period

Cloud Monitoring hỗ trợ hai cách đánh giá:

- **Rolling window:** luôn đánh giá trên khoảng thời gian trượt, ví dụ 30 ngày gần nhất. Khi sang ngày mới, hệ thống tính lại dựa trên 30 ngày trước đó.
- **Calendar period:** đánh giá từ đầu một kỳ lịch như ngày, tuần, hai tuần hoặc tháng. Khi kỳ kết thúc, error budget được đặt lại cho kỳ tiếp theo.

Bài thực hành dùng rolling window 30 ngày để nhóm luôn quan sát chất lượng gần đây. Nếu tổ chức cần báo cáo theo tháng tài chính hoặc kỳ hợp đồng, có thể cân nhắc calendar period.

## 3. Thiết kế SLI cho API Java

Trước khi tạo service trong Cloud Monitoring, hãy thống nhất request nào được tính vào SLI và request nào được xem là tốt.

### Xác định request đủ điều kiện

Ví dụ cho API HTTP:

- Request tới route nghiệp vụ như `/v1/orders` hoặc `/v1/orders/{orderId}` được tính.
- Request tới health endpoint, metrics endpoint và probe nội bộ không được tính vào SLI nghiệp vụ.
- Request bị từ chối vì dữ liệu đầu vào không hợp lệ (một số mã 4xx) có thể được xem là lỗi phía client và không tính là request xấu.
- HTTP 5xx, timeout do server, lỗi xử lý nội bộ và HTTP 429 do dịch vụ throttling có thể được phân loại là request xấu.
- Quy tắc phân loại phải được thống nhất giữa đội sản phẩm, backend và SRE. Không thay đổi quy tắc chỉ để làm đẹp số liệu.

Trong ví dụ này, request đủ điều kiện được phân loại:

| Kết quả | outcome | Cách tính |
|---|---|---|
| HTTP 2xx | `good` | Request tốt |
| HTTP 3xx được API chủ động hỗ trợ | `good` | Request tốt nếu là hành vi hợp lệ của API |
| HTTP 4xx do dữ liệu hoặc quyền của client | Không ghi vào request SLI hoặc được phân loại theo chính sách | Không tự động coi mọi 4xx là lỗi dịch vụ |
| HTTP 429 do rate limit của dịch vụ | `bad` | Request xấu trong ví dụ này |
| HTTP 5xx | `bad` | Request xấu |
| Timeout hoặc exception trước khi có response | `bad` | Request xấu |

Nếu muốn 4xx được tính vào tổng request, hãy quyết định rõ cách phân loại. Điều quan trọng là metric numerator và denominator phải dùng cùng định nghĩa request đủ điều kiện.

### Availability SLI

Request-based availability SLI được tính bằng:

SLI_availability = good requests / eligible total requests

Với custom service, bạn có thể sử dụng `TimeSeriesRatio` để lọc metric tốt và metric tổng. Metric cần có kind là `DELTA` hoặc `CUMULATIVE`; `GAUGE` không dùng được cho request-based SLI.

### Latency SLI

Latency SLI đo tỷ lệ request hoàn tất trong ngưỡng thời gian:

SLI_latency = requests with latency <= 300 ms / eligible total requests

Với custom SLI, Cloud Monitoring có thể sử dụng `DistributionCut`: một distribution metric và khoảng giá trị được xem là tốt. Metric phải có value type `DISTRIBUTION` và metric kind `DELTA` hoặc `CUMULATIVE`.

### Metric cần thu thập

Một thiết kế metric đơn giản:

| Metric type minh họa | Kind / Value type | Labels | Mục đích |
|---|---|---|---|
| `custom.googleapis.com/java_api/request_count` | CUMULATIVE / INT64 | `outcome`, `route` | Đếm request đủ điều kiện, phân biệt good và bad |
| `custom.googleapis.com/java_api/request_latency` | CUMULATIVE / DISTRIBUTION | `route` | Đo phân phối latency theo giây |

Các metric type trên là tên mục tiêu để minh họa. Nếu Collector hoặc exporter tạo tên khác, hãy dùng đúng metric type trong Metric Explorer và thay tên đó trong bộ lọc SLI. Luôn kiểm tra metric descriptor thực tế sau khi export.

### Tránh cardinality quá cao

Không đưa các giá trị thay đổi theo từng request vào metric labels:

- Không dùng `request_id`, `trace_id`, `user_id`, email, order ID hoặc raw URL.
- Dùng route template như `/v1/orders/{orderId}`, không dùng đường dẫn có ID thật.
- Dùng số lượng outcome nhỏ và ổn định như `good`, `bad`.
- Chỉ thêm region, service hoặc version khi có nhu cầu phân tích và cardinality vẫn kiểm soát được.

Metric có cardinality cao làm tăng số time series, chi phí và độ phức tạp khi truy vấn; chúng cũng không phù hợp để làm SLI.

## 4. Instrument ứng dụng Java bằng OpenTelemetry

Ví dụ dưới đây dùng OpenTelemetry API để tạo counter và histogram. Ứng dụng ghi một điểm cho mỗi request đủ điều kiện, đồng thời ghi latency của request đó.

### Khởi tạo instrument

~~~java
import io.opentelemetry.api.common.AttributeKey;
import io.opentelemetry.api.common.Attributes;
import io.opentelemetry.api.metrics.DoubleHistogram;
import io.opentelemetry.api.metrics.LongCounter;
import io.opentelemetry.api.metrics.Meter;

public final class ApiMetrics {
    private static final AttributeKey<String> OUTCOME =
        AttributeKey.stringKey("outcome");
    private static final AttributeKey<String> ROUTE =
        AttributeKey.stringKey("route");

    private final LongCounter requestCount;
    private final DoubleHistogram requestLatency;

    public ApiMetrics(Meter meter) {
        this.requestCount = meter.counterBuilder("api.request.count")
            .setDescription("Eligible API requests by outcome")
            .setUnit("{request}")
            .build();

        this.requestLatency = meter.histogramBuilder("api.request.duration")
            .setDescription("Eligible API request duration")
            .setUnit("s")
            .build();
    }

    public void record(
        String routeTemplate,
        int statusCode,
        long elapsedNanos,
        boolean timedOut
    ) {
        // Loại 4xx do client khỏi SLI; 429 vẫn là lỗi phía dịch vụ.
        boolean clientError = statusCode >= 400
            && statusCode < 500
            && statusCode != 429;
        if (!timedOut && clientError) {
            return;
        }

        boolean good = !timedOut
            && statusCode >= 200
            && statusCode < 400;

        String outcome = good ? "good" : "bad";

        Attributes requestAttributes = Attributes.of(
            ROUTE, routeTemplate,
            OUTCOME, outcome
        );

        requestCount.add(1, requestAttributes);

        // Latency SLI chỉ dùng request đủ điều kiện.
        requestLatency.record(
            elapsedNanos / 1_000_000_000.0,
            Attributes.of(ROUTE, routeTemplate)
        );
    }
}
~~~

Đoạn mã là ví dụ về cách đặt instrument và phân loại request. Trong ứng dụng thực tế, hãy gọi `record` ở điểm đã xác định được kết quả cuối cùng của request, bao gồm cả timeout và exception. Không ghi metric hai lần khi request được retry hoặc đi qua nhiều filter/interceptor.

Trong ví dụ này, 4xx do client (ngoại trừ 429) được bỏ qua khỏi SLI; 429, 5xx và timeout được ghi là `bad`. Nếu chính sách của nhóm muốn tính mọi 4xx vào mẫu số, hãy bỏ nhánh `return` và thống nhất lại tiêu chí good/bad với nhóm sản phẩm.

### Xuất telemetry tới Google Cloud

Có thể sử dụng OpenTelemetry Collector để nhận OTLP từ Java SDK và xuất metric, trace tới Google Cloud. Với môi trường hỗ trợ Collector, Google khuyến nghị kiến trúc collector-based để tách instrumentation khỏi backend đích.

Các bước tổng quát:

1. Khởi tạo OpenTelemetry SDK trong Java app.
2. Cấu hình OTLP exporter tới Collector.
3. Cấu hình Collector nhận OTLP và export metric/trace tới Google Cloud.
4. Cấp quyền ghi telemetry cho service account chạy Collector hoặc workload.
5. Kiểm tra metric và trace trong đúng project.
6. Xem metric descriptor để xác nhận metric kind, value type, resource type và labels.

Nếu dùng Google-Built OpenTelemetry Collector hoặc Telemetry API, metric name và resource mapping phụ thuộc cấu hình exporter. Không giả định rằng tên instrument `api.request.count` tự động trở thành `custom.googleapis.com/java_api/request_count`. Hãy đối chiếu metric type thực tế rồi mới tạo SLI.

### Bật API và cấp IAM

Trong project chứa workload hoặc telemetry destination, bật các API cần thiết:

~~~bash
gcloud services enable \
  monitoring.googleapis.com \
  logging.googleapis.com \
  cloudtrace.googleapis.com \
  telemetry.googleapis.com \
  --project=PROJECT_ID
~~~

Các quyền tham khảo:

| Danh tính | Role | Mục đích |
|---|---|---|
| Service account ghi metric | `roles/monitoring.metricWriter` | Ghi metric vào Cloud Monitoring |
| Service account ghi log | `roles/logging.logWriter` | Ghi log ứng dụng |
| Service account ghi trace qua Telemetry API | `roles/telemetry.tracesWriter` | Ghi trace |
| Người tạo service/SLO/dashboard | `roles/monitoring.editor` | Quản lý Monitoring và SLO |
| Người xem dashboard | `roles/monitoring.viewer` | Xem metric và dashboard |
| Người điều tra trace | `roles/cloudtrace.user` | Truy cập trace theo quyền được cấp |

Nếu dùng quota project cho telemetry, danh tính có thể cần `roles/serviceusage.serviceUsageConsumer` trên quota project. Với production, cấp quyền cho service account của workload/Collector, không dùng user credential cá nhân.

## 5. Kiểm tra metric trước khi tạo SLO

Đừng bắt đầu tạo SLO khi metric chưa có dữ liệu hoặc có schema sai.

### Kiểm tra trong Metrics Explorer

1. Mở Monitoring > Metrics Explorer.
2. Chọn metric request count mà Java app hoặc Collector đã export.
3. Kiểm tra metric type và monitored resource type.
4. Xác nhận metric có dữ liệu theo thời gian và các label `outcome`, `route` có giá trị dự kiến.
5. Lọc `outcome="good"` để xác nhận numerator có dữ liệu.
6. Kiểm tra tổng request có bao gồm cả good và bad.
7. Chọn latency distribution và xem phân phối theo route.
8. Xác nhận đơn vị là giây và histogram không chứa các request bị loại khỏi SLI.

### Kiểm tra metric descriptor

Với request-based SLI, metric cần `CUMULATIVE` hoặc `DELTA`; value type phải là `INT64` hoặc `DOUBLE`. Với distribution-cut latency SLI, metric cần value type `DISTRIBUTION` và kind `CUMULATIVE` hoặc `DELTA`. Riêng metric tự tạo dưới prefix `custom.googleapis.com`, dùng `GAUGE` hoặc `CUMULATIVE`; ví dụ này chọn `CUMULATIVE` cho cả counter và histogram.

Nếu metric đang là GAUGE, không thể dùng trực tiếp cho request-based SLI. Hãy thay đổi cách instrument/export để biểu diễn số request như counter tích lũy hoặc delta phù hợp.

### Bộ lọc SLI minh họa

Giả sử metric descriptor thực tế đúng với tên mẫu và resource type là `cloud_run_revision`.

Bộ lọc request tốt:

~~~text
metric.type="custom.googleapis.com/java_api/request_count"
AND resource.type="cloud_run_revision"
AND metric.label.outcome="good"
~~~

Bộ lọc tổng request:

~~~text
metric.type="custom.googleapis.com/java_api/request_count"
AND resource.type="cloud_run_revision"
~~~

Bộ lọc latency distribution:

~~~text
metric.type="custom.googleapis.com/java_api/request_latency"
AND resource.type="cloud_run_revision"
~~~

Nếu API chạy trên GKE, Compute Engine hoặc một resource type khác, hãy thay `resource.type` bằng monitored resource thực tế và bảo đảm cả numerator, denominator cùng chọn đúng tập request.

## 6. Tạo custom service và SLO trong Cloud Monitoring

Với custom service, Cloud Monitoring không có predefined SLO phù hợp cho API của bạn. Bạn phải tạo service, chọn metric làm SLI và xác định mục tiêu.

### Tạo custom service

1. Mở Google Cloud Console và chọn project chứa telemetry.
2. Vào Monitoring > Services hoặc SLO monitoring.
3. Mở Services Overview.
4. Chọn Define service.
5. Chọn custom service nếu API chưa được tự động nhận diện.
6. Đặt tên hiển thị `orders-api`.
7. Chọn resource hoặc phạm vi phù hợp với workload; với Cloud Run, xác nhận các revision thuộc service cần theo dõi.
8. Lưu service.

Tên service là định danh logic để nhóm SLO và dashboard. Nếu API có nhiều phiên bản hoặc deployment region, hãy quyết định chúng là một service hay các service riêng dựa trên cách đội vận hành chịu trách nhiệm và cách muốn xem error budget.

### Tạo availability SLO

1. Mở service `orders-api`.
2. Chọn Create SLO.
3. Ở bước Set your SLI, chọn metric type `Other` vì custom service cần custom SLI.
4. Chọn Request-based evaluation.
5. Chọn Time-series ratio indicator.
6. Đặt good numerator bằng bộ lọc `outcome="good"`.
7. Đặt total denominator bằng bộ lọc tổng request.
8. Xem preview để xác nhận ratio nằm trong khoảng 0 đến 1 và có dữ liệu.
9. Đặt compliance period là Rolling window 30 days.
10. Đặt performance goal là 99.9% (0.999).
11. Đặt tên SLO `Availability 99.9% - 30d`.
12. Review và Create SLO.

Request-based SLI tính số request tốt chia cho tổng request đủ điều kiện. TimeSeriesRatio yêu cầu chỉ định đúng hai trong ba trường good, bad và total; nếu cung cấp good và total, Cloud Monitoring suy ra bad từ quan hệ giữa chúng.

### Tạo latency SLO

Lặp lại quy trình tạo SLO cho cùng service:

1. Chọn metric type `Other`.
2. Chọn Request-based evaluation.
3. Chọn Distribution-cut indicator.
4. Chọn latency distribution metric.
5. Đặt range có `min=0`, `max=0.3` (giây).
6. Đặt compliance period Rolling window 30 days.
7. Đặt performance goal 99% (0.99).
8. Đặt tên `Latency under 300ms - 99% - 30d`.
9. Review preview và lưu.

DistributionCut đếm số quan sát trong distribution nằm trong khoảng được xem là tốt. Với ví dụ này, request có latency không vượt 300 ms được tính là tốt. Hãy xác nhận đơn vị của metric trước khi đặt range; nếu metric được ghi bằng milliseconds, ngưỡng phải là 300 thay vì 0.3.

### Ví dụ SLO resource qua API

Sau khi tạo service, có thể dùng Cloud Monitoring API để tạo SLO. Ví dụ body dưới đây mô tả availability SLO; thay metric type và resource type bằng giá trị đã xác minh trong Metrics Explorer:

~~~json
{
  "displayName": "Availability 99.9% - 30d",
  "goal": 0.999,
  "rollingPeriod": "2592000s",
  "serviceLevelIndicator": {
    "requestBased": {
      "goodTotalRatio": {
        "goodServiceFilter": "metric.type=\"custom.googleapis.com/java_api/request_count\" AND resource.type=\"cloud_run_revision\" AND metric.label.outcome=\"good\"",
        "totalServiceFilter": "metric.type=\"custom.googleapis.com/java_api/request_count\" AND resource.type=\"cloud_run_revision\""
      }
    }
  }
}
~~~

Gửi request tới resource path:

~~~bash
ACCESS_TOKEN=$(gcloud auth print-access-token)

curl -X POST \
  "https://monitoring.googleapis.com/v3/projects/PROJECT_ID/services/SERVICE_ID/serviceLevelObjectives" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  --data-binary @availability-slo.json
~~~

Với latency SLO, phần `serviceLevelIndicator` có thể dùng cấu trúc sau:

~~~json
{
  "serviceLevelIndicator": {
    "requestBased": {
      "distributionCut": {
        "distributionFilter": "metric.type=\"custom.googleapis.com/java_api/request_latency\" AND resource.type=\"cloud_run_revision\"",
        "range": {
          "min": 0,
          "max": 0.3
        }
      }
    }
  }
}
~~~

Trong SLO API, `rollingPeriod` phải là bội số nguyên của một ngày và không vượt quá 30 ngày. `goal` là tỷ lệ từ lớn hơn 0 tới tối đa 0.9999. Ví dụ 99.9% được biểu diễn là 0.999.

## 7. Tạo dashboard SLO trong Cloud Monitoring

Dashboard nên trả lời nhanh bốn câu hỏi:

1. API hiện có đạt mục tiêu SLO không?
2. Error budget còn bao nhiêu?
3. Tín hiệu nào đang làm chất lượng giảm: traffic, lỗi hay latency?
4. Người trực nên mở log, trace hoặc incident nào để điều tra?

### Bố cục dashboard đề xuất

| Vị trí | Widget | Nội dung | Mục đích |
|---|---|---|---|
| Hàng 1 | SLO health | Availability và latency health | Nhìn nhanh trạng thái mục tiêu |
| Hàng 1 | Error budget | Budget còn lại dạng % hoặc giá trị tuyệt đối | Biết mức độ rủi ro phát hành |
| Hàng 2 | Request volume | Tổng request, good và bad theo thời gian | Nhận biết traffic và lỗi |
| Hàng 2 | Latency | Phân phối latency hoặc p50/p95/p99 | Xác định API chậm |
| Hàng 3 | Burn-rate alerts | Alert đang mở và tốc độ tiêu thụ budget | Ưu tiên xử lý |
| Hàng 3 | Logs / traces | Log ERROR và trace liên quan | Tìm nguyên nhân |

### Thêm SLO widget

1. Mở Monitoring > Dashboards.
2. Chọn Create dashboard.
3. Đặt tên `orders-api-slo-dashboard`.
4. Chọn Add widget.
5. Chọn loại widget SLO.
6. Chọn service `orders-api`.
7. Chọn SLO `Availability 99.9% - 30d`.
8. Chọn chart type Health hoặc Compliance.
9. Thêm một SLO widget khác cho `Latency under 300ms - 99% - 30d`.
10. Thêm widget hiển thị absolute hoặc fractional error budget cho từng SLO.
11. Apply và lưu dashboard.

SLO widget hiển thị sức khỏe, compliance và error budget của SLO. Một dashboard có thể có nhiều widget, tối đa 100 widgets. Dashboard SLO widget hỗ trợ Google Cloud projects; với App Hub configuration, chọn host project hoặc management project phù hợp.

### Thêm chart metric

Thêm chart thông thường để giải thích nguyên nhân:

**Request volume**

- Metric: `custom.googleapis.com/java_api/request_count`.
- Group by: `outcome` hoặc `route`.
- Vì counter là CUMULATIVE, dùng `ALIGN_DELTA` để hiển thị số request trong mỗi interval hoặc `ALIGN_RATE` để hiển thị request/giây; không chart trực tiếp giá trị cumulative.
- Hiển thị good và bad để so sánh với traffic.

**Latency**

- Metric: `custom.googleapis.com/java_api/request_latency`.
- Chuyển cumulative distribution thành delta theo interval (ví dụ `ALIGN_DELTA`) rồi chọn distribution/percentile view phù hợp.
- Group by route template.
- Đánh dấu ngưỡng 300 ms để nhìn thấy endpoint vượt mục tiêu.

**Error rate**

- Dùng good và total request để biểu diễn tỷ lệ tốt hoặc bad.
- Nếu chart tỷ lệ lỗi, xác nhận numerator là request bad và denominator là total request.
- Tránh cộng các phần trăm của nhiều route mà không cân theo lượng request.

**Application logs**

- Thêm log widget hoặc liên kết Logs Explorer.
- Lọc log theo service, severity ERROR và thời gian của incident.
- Bảo đảm log có trace ID để chuyển sang Cloud Trace.

**Trace data**

- Thêm trace widget hoặc liên kết Trace Explorer.
- Dùng trace để xem span của API và dependency chậm.
- So sánh latency tổng của request với thời gian từng dependency.

### Dashboard variables và bộ lọc

Nếu API có nhiều route hoặc region, tạo dashboard filter cho `route`, `location` hoặc `service_name`. Người xem có thể tập trung vào endpoint bị ảnh hưởng mà không cần tạo dashboard riêng cho từng route.

Không dùng ID request hoặc user ID làm dashboard variable. Chúng không phải chiều phân tích ổn định và có thể làm cardinality tăng mạnh.

### Phân biệt dashboard time range và SLO compliance period

Time range của dashboard điều khiển khoảng thời gian hiển thị của các chart metric, log và trace. SLO widget lại thể hiện SLO theo compliance period đã cấu hình, ví dụ rolling 30 ngày. Vì vậy, khi dashboard đang xem 1 giờ gần nhất, SLO vẫn có thể đang đánh giá trên rolling 30 ngày. Ghi rõ điều này trong phần mô tả dashboard để người xem không nhầm hai khoảng thời gian.

## 8. Tạo alert theo error-budget burn rate

SLO dashboard cho biết budget còn lại; burn-rate alert giúp phát hiện tốc độ tiêu thụ budget bất thường trước khi SLO bị vi phạm.

Burn rate được chuẩn hóa theo tốc độ tiêu thụ budget. Burn rate bằng 1 có nghĩa dịch vụ đang tiêu thụ budget đúng tốc độ cho phép để vừa hết budget vào cuối compliance period. Burn rate lớn hơn 1 cho biết nếu tốc độ lỗi hiện tại tiếp tục trong kỳ, dịch vụ sẽ vượt SLO.

### Fast burn và slow burn

| Loại alert | Lookback tham khảo | Threshold tham khảo | Ý nghĩa |
|---|---:|---:|---|
| Fast burn | 1–2 giờ | 10x | Lỗi tăng mạnh, có nguy cơ tiêu thụ nhanh toàn bộ budget |
| Slow burn | 24 giờ | 2x | Chất lượng giảm kéo dài, có thể làm cạn budget trước cuối kỳ |

Các giá trị 10x và 2x là điểm khởi đầu để hiệu chỉnh, không phải ngưỡng bắt buộc cho mọi API. Traffic thấp và biến động theo giờ có thể làm burn rate nhạy hơn; hãy xem lượng request, mức độ ảnh hưởng và thời gian duy trì trước khi chọn ngưỡng cuối cùng.

### Tạo alert từ giao diện

1. Mở Monitoring > Services Overview.
2. Chọn service `orders-api`.
3. Trong Current status, tìm availability SLO.
4. Chọn Create SLO alert.
5. Đặt lookback duration 1 giờ và burn rate threshold 10 cho fast-burn.
6. Chọn notification channel của nhóm on-call.
7. Viết documentation gồm symptom, dashboard link, log query và runbook.
8. Lưu policy.
9. Tạo policy thứ hai với lookback 24 giờ và threshold 2 cho slow-burn.

Cloud Monitoring cung cấp giá trị gợi ý khi tạo alert từ một SLO cụ thể. Hãy kiểm tra lookback, threshold và notification channel trước khi lưu.

### Ví dụ condition bằng Cloud Monitoring API

SLO burn-rate alert sử dụng time-series selector `select_slo_burn_rate`. Ví dụ dưới đây tạo fast-burn condition cho availability SLO:

~~~json
{
  "displayName": "orders-api availability fast burn",
  "combiner": "OR",
  "conditions": [
    {
      "displayName": "Availability SLO burn rate above 10 over 1 hour",
      "conditionThreshold": {
        "filter": "select_slo_burn_rate(\"projects/PROJECT_ID/services/SERVICE_ID/serviceLevelObjectives/AVAILABILITY_SLO_ID\", \"60m\")",
        "comparison": "COMPARISON_GT",
        "thresholdValue": 10,
        "duration": "0s"
      }
    }
  ],
  "notificationChannels": [
    "projects/PROJECT_ID/notificationChannels/CHANNEL_ID"
  ],
  "documentation": {
    "mimeType": "text/markdown",
    "content": "orders-api is consuming its availability error budget at more than 10x the sustainable rate. Check the SLO dashboard, recent releases, HTTP 5xx, dependency latency, and traces. Follow the incident runbook."
  }
}
~~~

Thay `PROJECT_ID`, `SERVICE_ID`, `AVAILABILITY_SLO_ID` và `CHANNEL_ID` bằng resource name thật. Slow-burn policy dùng selector tương tự nhưng lookback `24h` và threshold `2`.

Cloud Monitoring không hỗ trợ truy vấn burn-rate alert với compliance period lớn hơn 24 giờ. Vì vậy, dù SLO mục tiêu có rolling window 30 ngày, alert vẫn dùng lookback ngắn hơn để phản ứng vận hành. Điều này không làm thay đổi compliance period của SLO; nó chỉ xác định khoảng dữ liệu dùng để tính burn rate cho alert.

## 9. Đọc dashboard và xử lý tình huống

Khi dashboard cho thấy availability SLO đang giảm, hãy kết hợp SLO widget với traffic, lỗi, log và trace.

### Tình huống A: availability giảm nhanh

Dấu hiệu:

- SLO health chuyển sang trạng thái không đạt.
- Error budget còn lại giảm nhanh.
- Request volume không giảm nhưng bad request tăng.
- Fast-burn alert được kích hoạt.

Cách điều tra:

1. Xác định route và region bị ảnh hưởng.
2. Xem thời điểm lỗi bắt đầu so với lần deploy gần nhất.
3. Lọc Cloud Logging theo severity ERROR và service.
4. Mở trace mẫu để xác định lỗi ở API handler hay dependency.
5. Kiểm tra Cloud SQL, Pub/Sub hoặc dịch vụ downstream nếu span cho thấy timeout.
6. Nếu liên quan release, thực hiện rollback theo runbook đã phê duyệt.
7. Theo dõi SLI và burn rate sau khi khắc phục.

### Tình huống B: latency SLO giảm nhưng availability vẫn tốt

Dấu hiệu:

- Availability SLO vẫn đạt mục tiêu.
- Latency SLO giảm.
- p95/p99 tăng nhưng HTTP 5xx chưa tăng đáng kể.
- Error budget latency đang bị tiêu thụ.

Cách điều tra:

1. Xác định route có p95/p99 cao nhất.
2. So sánh request latency với thời gian span của từng dependency.
3. Kiểm tra connection pool, query database, cache miss và external API.
4. Xem CPU, memory, instance count và concurrency của workload.
5. Kiểm tra thay đổi payload hoặc kích thước response.
6. Đánh giá tối ưu code, query hoặc capacity trước khi tăng tài nguyên.

### Tình huống C: Dashboard không có dữ liệu

Dấu hiệu:

- SLO widget hiển thị no data hoặc preview không có lịch sử.
- Metric chart trống.
- Service vừa mới tạo hoặc workload vừa triển khai.

Cách điều tra:

1. Kiểm tra service account có quyền Monitoring Metric Writer.
2. Xác nhận Collector đang export telemetry và không có lỗi export.
3. Kiểm tra project, monitored resource và metric type.
4. Xác nhận numerator và denominator đều có time series.
5. Kiểm tra metric kind và value type có phù hợp SLI.
6. Chờ dữ liệu mới được ingest rồi refresh Metrics Explorer và SLO preview.
7. Kiểm tra filter route/outcome có loại bỏ toàn bộ dữ liệu hay không.

Một service mới có thể tạo SLO trước khi có dữ liệu lịch sử, nhưng preview chart sẽ chưa có góc nhìn quá khứ. Dashboard cần ghi nhận trạng thái thiếu dữ liệu thay vì tự suy ra rằng dịch vụ đang đạt 100%.

## 10. Quy trình kiểm chứng end-to-end

Thực hiện trong project thử nghiệm hoặc môi trường staging trước khi đưa dashboard vào production.

### Bước 1: Sinh traffic hợp lệ

Gửi request tới một số route API:

~~~bash
curl -i https://YOUR_API_HOST/health
curl -i https://YOUR_API_HOST/v1/orders
~~~

Health endpoint không nên được tính vào request SLI nghiệp vụ. Gửi request nghiệp vụ với dữ liệu hợp lệ và một số tình huống kiểm thử lỗi trong staging để tạo cả outcome good và bad.

### Bước 2: Xác nhận metric

Trong Metrics Explorer, kiểm tra:

- Request counter tăng khi API nhận request.
- Label `outcome` có cả `good` và `bad` khi đã tạo đủ tình huống.
- Latency distribution có dữ liệu và đơn vị đúng.
- Route label dùng template, không chứa ID thực.
- Metric descriptor có kind/value type phù hợp.

### Bước 3: Xác nhận SLO

Mở service details và xem từng SLO:

- Availability SLI có numerator, denominator hợp lệ.
- Latency SLI dùng distribution metric và range 300 ms.
- Goal đúng 99.9% và 99%.
- Compliance period là rolling 30 ngày.
- Preview chart thay đổi khi có dữ liệu mới.

### Bước 4: Xác nhận dashboard

- SLO widgets hiển thị đúng service và SLO.
- Error budget thể hiện đúng tỷ lệ còn lại.
- Request chart phân biệt good và bad.
- Latency chart thể hiện phân phối và ngưỡng.
- Logs/trace giúp mở rộng điều tra.
- Time range và compliance period được ghi rõ.

### Bước 5: Kiểm tra alert

Không cố tình gây outage production để thử burn-rate alert. Dùng môi trường staging hoặc policy test với metric đã kiểm soát. Xác nhận notification tới đúng channel và nội dung có runbook.

### Bước 6: Lưu lại cấu hình và ownership

Ghi lại:

- Service owner và nhóm on-call.
- Định nghĩa request đủ điều kiện.
- Metric type và labels dùng làm SLI.
- SLO goal và compliance period.
- Dashboard link.
- Fast/slow burn policy và notification channel.
- Ngày rà soát mục tiêu tiếp theo.

## 11. Lỗi thường gặp khi xây dashboard SLO

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Không chọn được metric cho request-based SLI | Metric là GAUGE hoặc value type không hợp lệ | Với `custom.googleapis.com`, dùng counter CUMULATIVE INT64; chỉ dùng DELTA khi nguồn metric hỗ trợ |
| Availability SLI luôn gần 100% | Bad request không được ghi hoặc filter numerator quá rộng | Kiểm tra phân loại outcome và numerator/denominator |
| Error budget giảm bất thường | 4xx, health checks hoặc probe bị tính vào request SLI | Rà soát eligibility và chính sách phân loại |
| Latency SLO không có dữ liệu | Histogram không phải DISTRIBUTION hoặc metric kind không phù hợp | Kiểm tra metric descriptor và exporter |
| Latency SLI luôn thấp | Unit không khớp ngưỡng | Chuẩn hóa giây/millisecond và sửa range |
| SLO preview không có lịch sử | Service mới hoặc metric chưa được ingest | Kiểm tra Collector và chờ dữ liệu |
| Dashboard không hiển thị SLO | Chưa có service/SLO hoặc đang chọn sai project | Tạo SLO và chọn đúng project/service |
| Dashboard có nhiều chart nhưng khó đọc | Trộn metric không cùng đơn vị hoặc không có filter | Tách chart, group theo route và ghi rõ unit |
| Burn-rate alert không kích hoạt | Lookback/filter sai hoặc chưa có dữ liệu | Kiểm tra SLO resource name và selector |
| Burn-rate alert quá nhạy khi traffic thấp | Threshold thấp hoặc traffic thay đổi mạnh | Dùng fast/slow burn, xem số request và hiệu chỉnh |
| Metric có cardinality tăng mạnh | Label chứa request ID, user ID hoặc raw URL | Thay bằng route template và label ổn định |
| SLO không phản ánh trải nghiệm người dùng | Chỉ đo status code, bỏ qua latency hoặc dependency | Tạo SLO riêng cho availability và latency |

## 12. Thực hành tốt và quản trị SLO

- **Chọn mục tiêu theo trải nghiệm người dùng:** tránh chọn 99.99% chỉ vì nghe có vẻ tốt; cân nhắc khả năng vận hành và chi phí.
- **Định nghĩa eligibility rõ ràng:** xác định request nào được tính và cách xử lý 4xx, 429, timeout, retry và health checks.
- **Tách SLI theo khía cạnh chất lượng:** availability và latency nên có SLO riêng để error budget có ý nghĩa.
- **Đo request thực:** dùng counter và histogram từ ứng dụng, không lấy CPU hoặc số instance thay cho chất lượng API.
- **Kiểm soát cardinality:** giữ label ở route template, outcome, region hoặc service cần thiết.
- **Đặt alert theo burn rate:** fast burn để phản ứng outage lớn; slow burn để nhận ra suy giảm kéo dài.
- **Đặt owner cho từng SLO:** mỗi mục tiêu cần nhóm chịu trách nhiệm, dashboard và runbook.
- **Dùng error budget trong quyết định release:** khi budget bị tiêu thụ nhanh, ưu tiên reliability work trước khi tiếp tục thay đổi rủi ro.
- **Không coi dashboard là bằng chứng duy nhất:** đối chiếu metric, log, trace và dữ liệu từ phía client.
- **Rà soát định kỳ:** điều chỉnh mục tiêu khi hành vi người dùng, traffic và kiến trúc API thay đổi.
- **Bảo vệ telemetry:** tránh đưa dữ liệu cá nhân, token, URL nhạy cảm hoặc thông tin đơn hàng vào metric labels và log không được kiểm soát.

## Kết luận

Dashboard SLO giúp đội vận hành nhìn thấy API đang đáp ứng mục tiêu chất lượng đến đâu và error budget còn lại bao nhiêu. Với API Java, nền tảng của dashboard là instrumentation đúng: request counter phân loại good/bad, latency distribution có đơn vị rõ ràng và labels đủ thấp về cardinality.

Cloud Monitoring dùng các metric đó để tạo custom service, request-based availability SLO và latency SLO. SLO widgets hiển thị health, compliance và error budget; các chart metric, log và trace giúp giải thích nguyên nhân. Fast-burn và slow-burn alert đưa tín hiệu tới người trực trước khi budget cạn. Khi các thành phần này có owner, định nghĩa SLI nhất quán và runbook rõ ràng, dashboard trở thành công cụ hỗ trợ quyết định phát hành và cải thiện độ tin cậy của API.

## Tài liệu tham khảo

- [SLO monitoring overview](https://cloud.google.com/monitoring/slo-monitoring)
- [Creating an SLO](https://cloud.google.com/stackdriver/docs/solutions/slo-monitoring/ui/create-slo)
- [Creating a service-level indicator](https://cloud.google.com/stackdriver/docs/solutions/slo-monitoring/api/identifying-custom-sli)
- [Cloud Monitoring ServiceLevelObjective API](https://cloud.google.com/monitoring/api/ref_v3/rest/v3/services.serviceLevelObjectives)
- [Display SLOs on a custom dashboard](https://cloud.google.com/monitoring/dashboards/slos)
- [Alerting on your burn rate](https://cloud.google.com/stackdriver/docs/solutions/slo-monitoring/alerting-on-budget-burn-rate)
- [Create an SLO alerting policy](https://cloud.google.com/stackdriver/docs/solutions/slo-monitoring/ui/create-alert)
- [Working with the SLO API](https://cloud.google.com/stackdriver/docs/solutions/slo-monitoring/api/using-api)
- [Java instrumentation sample with OpenTelemetry](https://cloud.google.com/trace/docs/setup/java-ot)
- [Enable telemetry signals in Cloud Client Libraries for Java](https://cloud.google.com/java/docs/observability)
- [User-defined metrics overview](https://cloud.google.com/monitoring/custom-metrics)
- [Value types and metric kinds](https://cloud.google.com/monitoring/api/v3/kinds-and-types)
- [Create and manage dashboards by API](https://cloud.google.com/monitoring/dashboards/api-dashboard)

