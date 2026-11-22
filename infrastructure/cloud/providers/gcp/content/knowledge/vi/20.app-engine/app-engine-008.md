# Logs, chẩn đoán và kiểm soát chi phí App Engine

Sau khi triển khai phiên bản `v2` của ứng dụng Java `orders-api` lên App Engine, nhóm vận hành nhận hai cảnh báo: tỷ lệ lỗi HTTP 5xx tăng và hóa đơn cuối ngày cao hơn dự kiến. Nhìn tổng số request chưa đủ để kết luận vì lỗi có thể chỉ xảy ra ở một **version**, trong khi chi phí có thể đến từ **instance chạy nhàn rỗi, version cũ, log ingestion, network egress hoặc Cloud SQL**.

Bài này xây dựng quy trình **quan sát → chẩn đoán → sửa lỗi → kiểm chứng → tối ưu chi phí** cho cả **App Engine standard environment** và **flexible environment**. Đây là một phần của chương **App Engine** trong mô-đun `CLOUD_PROVIDERS_GCP`: người học vận dụng kiến thức project/IAM/VPC, Compute Engine, GKE, Cloud Run, lưu trữ và cơ sở dữ liệu để phát hành ứng dụng, bảo vệ tài nguyên, theo dõi độ tin cậy và quản lý ngân sách.

**Ví dụ:** ứng dụng Java 21, service `orders-api`, versions `v1` và `v2`, project `PROJECT_ID`. Tên và số liệu là giả định; các lệnh thay traffic/xóa version chỉ dùng khi có quyền và phê duyệt. Nội dung ưu tiên cô đọng, tự chứa và có thể dùng làm runbook.

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt request logs, application logs, structured logs và resource labels của App Engine.
2. Truy vấn logs theo service/version bằng Logs Explorer, `gcloud app logs` và `gcloud logging read`.
3. Liên kết một request lỗi với log Java, trace và dữ liệu Monitoring.
4. Chẩn đoán tăng 5xx, p95/p99 latency, lỗi khởi động, quá tải và lỗi dependency.
5. Phân biệt **pricing, scaling và free tier** của App Engine standard/flexible.
6. Giới hạn chi phí bằng sizing, cấu hình scaling, quản lý versions và logs.
7. Đặt Billing budgets, biết rằng **alert-only budget không khóa cứng chi tiêu**.
8. Thiết kế cảnh báo theo SLO, diễn tập xử lý sự cố và kiểm chứng sau thay đổi.
9. Hoàn thành bài thực hành đọc-only và bài tập tình huống có đáp án.

## 1. Kiến trúc quan sát App Engine

App Engine tổ chức ứng dụng theo **application → service → version → instances**. Mỗi version có cấu hình runtime/scaling riêng và có thể nhận một phần traffic hoặc được gọi trực tiếp qua URL version.

~~~mermaid
flowchart TD
    U["HTTP clients"] --> ROUTE["App Engine routing"]
    ROUTE -->|"90%"| V1["orders-api / v1"]
    ROUTE -->|"10%"| V2["orders-api / v2"]
    V1 --> L["Request + application logs"]
    V2 --> L
    V1 --> M["Metrics: request, latency, instances"]
    V2 --> M
    L --> LOG["Cloud Logging / Error Reporting"]
    M --> MON["Cloud Monitoring / Trace"]
    V1 --> DB["Cloud SQL, Storage, network"]
    V2 --> DB
    DB --> BILL["Cloud Billing"]
    LOG --> BILL
~~~

Khi phân tích lỗi, luôn ghi **project, service, version, khoảng thời gian và môi trường Standard/Flexible**. Nếu chỉ xem tổng project, traffic của `v1` có thể che lỗi ở `v2`.

| Thành phần | Câu hỏi cần trả lời |
| --- | --- |
| **App Engine versions** | Version nào đang nhận traffic? Có version cũ còn hoạt động không? |
| **Cloud Logging** | Request nào lỗi và ứng dụng đã ghi nguyên nhân gì? |
| **Error Reporting** | Nhóm stack trace/lỗi lặp lại nào xuất hiện sau deploy? |
| **Cloud Monitoring** | 5xx, p95 latency, CPU, memory, instance count biến đổi thế nào? |
| **Cloud Trace** | Độ trễ nằm ở Java app, network hay lệnh gọi downstream? |
| **Cloud Billing** | SKU nào tăng: instances, network, Cloud SQL hay Logging? |

## 2. Standard và Flexible khác nhau về vận hành/chi phí

| Tiêu chí | Standard environment | Flexible environment |
| --- | --- | --- |
| Năng lực chạy | Instance classes `F1/F2/F4...`, runtime hỗ trợ | Compute Engine VMs được App Engine quản lý |
| Mô hình scaling | Automatic, basic, manual | Automatic hoặc manual |
| Scale về 0 khi ít request | **Có thể**, thường với automatic scaling và `min_instances: 0` | **Không**, automatic scaling có `min_num_instances >= 1` |
| Default min instances | Tùy cấu hình scaling/version | Thường **2** với automatic |
| Free tier App Engine | **Có**, theo loại resource và quota hằng ngày | **Không có free tier App Engine** |
| Tính phí | Instance class/hours và tài nguyên sau free tier, network, dịch vụ liên quan | vCPU, memory, persistent disk/network theo loại resource và thời gian dùng; tối thiểu theo quy tắc billing |
| Log request phổ biến | `request_log` | `nginx.request` |
| Hệ quả để version cũ | Có thể phát sinh instance hours tùy scaling/traffic | Có thể tiếp tục có VM và phí ngay cả khi traffic thấp |

App Engine flexible dùng VM và có thể tính phí theo giây với **mức tối thiểu một phút**, không phải “chỉ tính khi có HTTP request”. Phần lớn ứng dụng Java có thể chọn Standard khi tính năng/runtime phù hợp, nhưng quyết định phải dựa vào giới hạn kỹ thuật, workload và giá ở **region thực tế**, không chỉ free tier.

## 3. Request logs và application logs

Cloud Logging nhận hai nhóm thông tin chính:

- **Request logs:** App Engine tự tạo cho HTTP requests, thường bao gồm thời gian, HTTP method/path/status, latency và thông tin tài nguyên.
- **Application logs:** do Java/framework ghi để mô tả xử lý, warning, exception hoặc sự kiện nghiệp vụ.

Ví dụ:

~~~text
Request: GET /api/orders/123 → HTTP 500, latency 1.8s
App:     order_query_failed errorCode=DB_TIMEOUT requestId=req-123
Trace:   request → Java handler → Cloud SQL connection timeout
~~~

Request log chỉ cho biết **triệu chứng**. Application log giải thích **bối cảnh**. Trace giúp xác định bước chậm; Monitoring xác nhận mức ảnh hưởng trên toàn service.

### 3.1. Những trường log nên có

| Field | Mục đích |
| --- | --- |
| `timestamp`, `severity` | Phân loại và tìm theo thời điểm |
| `message/event`, `errorCode` | Nhận diện loại lỗi ổn định |
| `service`, `version` | Gắn lỗi với bản phát hành |
| `requestId` và Cloud Trace ID | Liên kết nhiều dòng log cho cùng request |
| `latencyMs`, `dependency` | Phân tích bước gây chậm |
| `resource.type=gae_app` | Lọc tài nguyên App Engine |

Không ghi **Authorization header, access token, password, session cookie, dữ liệu thanh toán/PII** hoặc toàn bộ request body vào log để “debug nhanh”.

## 4. Đọc logs: CLI và Logs Explorer

### 4.1. Preflight chỉ đọc

~~~bash
gcloud auth list
gcloud config get-value project

gcloud app describe --project=PROJECT_ID
gcloud app services list --project=PROJECT_ID
gcloud app versions list \
  --service=orders-api --project=PROJECT_ID
~~~

Với quyền xem phù hợp, các lệnh trên **không đổi production state**. Xác nhận version đang chạy và tỷ lệ phân phối trước khi điều tra.

### 4.2. Lấy logs gần nhất

~~~bash
# 50 bản ghi từ service orders-api:
gcloud app logs read \
  --service=orders-api --limit=50 \
  --project=PROJECT_ID

# Chỉ xem mức warning trở lên, version v2:
gcloud app logs read \
  --service=orders-api --version=v2 \
  --level=warning --limit=100 \
  --project=PROJECT_ID

# Theo dõi real time (Ctrl+C để kết thúc):
gcloud app logs tail \
  --service=orders-api --version=v2 \
  --level=error --project=PROJECT_ID
~~~

Cờ `--level` nhận `critical/error/warning/info/debug/any`; cần `logging.logEntries.list` hoặc vai trò IAM phù hợp. Với logs cụ thể:

~~~bash
# App Engine Standard request logs:
gcloud app logs read \
  --service=orders-api --logs=request_log \
  --limit=30 --project=PROJECT_ID

# App Engine Flexible request logs:
gcloud app logs read \
  --service=orders-api --logs=nginx.request \
  --limit=30 --project=PROJECT_ID
~~~

### 4.3. Logs Explorer query theo version

Trong Console, chọn **Logging → Logs Explorer**, project đúng, resource **GAE Application**. Bắt đầu bằng query:

~~~text
resource.type="gae_app"
resource.labels.module_id="orders-api"
resource.labels.version_id="v2"
severity>=ERROR
~~~

Resource label `module_id` là **service name** theo monitored resource `gae_app`. `version_id` là tên version, không phải release tag trong Git.

Để tìm HTTP lỗi:

~~~text
resource.type="gae_app"
resource.labels.module_id="orders-api"
resource.labels.version_id="v2"
httpRequest.status>=500
~~~

Khi không thấy kết quả, thử bỏ lần lượt filter version, severity và status; kiểm tra khoảng thời gian, log name/request log và quyền đọc. Với app logs dạng `textPayload`, một số trường sẽ không tồn tại như `jsonPayload.errorCode`.

### 4.4. Đọc query bằng gcloud logging

~~~bash
gcloud logging read \
  'resource.type="gae_app" AND resource.labels.module_id="orders-api" AND severity>=ERROR' \
  --project=PROJECT_ID --limit=50 \
  --freshness=1h --format=json
~~~

Có thể thêm `resource.labels.version_id="v2"` và `httpRequest.status>=500` để khoanh vùng, nhưng **không giả định mọi application log có field HTTP status**.

## 5. Ghi logs Java rõ ràng và có cấu trúc

Trong Spring Boot, có thể dùng SLF4J/Logback hoặc Java Util Logging. Ví dụ tối giản:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import java.util.Map;

@RestController
class HealthController {
    private static final Logger LOG =
            LoggerFactory.getLogger(HealthController.class);

    @GetMapping("/healthz")
    ResponseEntity<Map<String, String>> health() {
        LOG.info("event=healthcheck status=ok");
        return ResponseEntity.ok(Map.of("status", "ok"));
    }
}
~~~

Giả định project dùng Spring Boot Web và logging dependencies thông thường. Endpoint demo không kiểm tra Cloud SQL; **200 ở /healthz không chứng minh toàn hệ thống khỏe**.

### 5.1. Structured log JSON

Khi cần query `jsonPayload.errorCode`, ứng dụng có thể serialize một JSON object **trên một dòng** ra `stdout` hoặc dùng Cloud Logging client phù hợp:

~~~json
{
  "severity": "ERROR",
  "message": "order_query_failed",
  "event": "dependency_timeout",
  "errorCode": "DB_TIMEOUT",
  "requestId": "req-123",
  "dependency": "cloudsql",
  "latencyMs": 1800,
  "logging.googleapis.com/trace":
    "projects/PROJECT_ID/traces/0123456789abcdef0123456789abcdef"
}
~~~

Đây là **một log record minh họa**; khi xuất ra stdout phải serialize thành **một dòng JSON hợp lệ**, không in đẹp nhiều dòng như ví dụ. Cloud Logging nhận những trường đặc biệt như `severity` và `logging.googleapis.com/trace` để hỗ trợ lọc/correlation. Tên project và trace ID phải lấy từ request/runtime thật; không tự bịa giá trị vào production.

Với App Engine, `X-Cloud-Trace-Context` giúp liên hệ request với trace. Chỉ lấy trace ID đúng định dạng, không log header nguyên văn nếu chứa dữ liệu không cần thiết. Dữ liệu log nên dùng **mã lỗi ổn định và request ID**, không đưa bí mật vào message.

### 5.2. Vì sao log đôi khi không có severity hoặc không tương quan?

Text thông thường từ `stdout/stderr` có thể xuất hiện ở `textPayload`, không có field để truy vấn theo errorCode; mức severity cũng có thể không như dự kiến. Request log và app log chỉ hiển thị theo nhóm khi **trace metadata được liên kết đúng**, một số thời điểm first request/startup có thể không tương quan hoàn chỉnh.

**Giới hạn cần nhớ:** tài liệu Cloud Logging App Engine cảnh báo app log entry vượt khoảng **16 KiB** có thể không hiển thị đúng trong Logs Explorer. Tránh log toàn bộ exception payload/response body lớn; thay bằng correlation ID và stack trace cần thiết.

## 6. Chẩn đoán tỷ lệ lỗi HTTP 5xx tăng sau deploy

Runbook nên đi theo thứ tự:

~~~mermaid
flowchart TD
    A["Alert: 5xx tăng"] --> B["Chốt project, service, time window"]
    B --> C["So sánh versions v1/v2"]
    C --> D["Request logs: path, status, latency"]
    D --> E["App logs: exception/errorCode/trace"]
    E --> F{"Lỗi ứng dụng hay dependency?"}
    F -->|"Ứng dụng v2"| G["Rollback traffic có kiểm soát"]
    F -->|"DB/network/IAM"| H["Điều tra Cloud SQL/VPC/quota/identity"]
    G --> I["Xác minh 5xx và business metrics"]
    H --> I
~~~

**Bước 1 – Khoanh vùng:** so 5xx rate của `v1` và `v2`, chọn 10–20 requests đại diện. Chú ý deployment time, traffic split, URL version-specific và correlation ID.

**Bước 2 – Xác định nguyên nhân:** đọc stack traces, `errorCode`, request path, latency. Kiểm tra Cloud SQL connection pool, database locks, Cloud Storage permissions, Secret Manager và network. HTTP 500 có thể đến từ ứng dụng; 503 có thể liên quan thiếu năng lực phục vụ/khởi động hoặc downstream.

**Bước 3 – Kiểm chứng:** nếu chỉ `v2` lỗi, có thể đưa traffic về `v1` theo quy trình change/rollback. Nếu cả hai lỗi, rollback code đơn thuần có thể không giúp; xem phụ thuộc dùng chung.

**Bước 4 – Sau can thiệp:** xác nhận request count, 5xx, p95 latency, tỷ lệ đặt hàng thành công và Cloud SQL connections đều ổn định. Tránh kết luận chỉ từ một phút số liệu.

### 6.1. Chỉ dùng Error Reporting có đủ không?

**Error Reporting** nhóm các exception/stack trace phù hợp để theo dõi lỗi lặp, nhưng **không phải mọi request 500 đều tạo một error group**. Nếu ứng dụng trả 500 mà không log exception ở dạng có thể nhận diện, Error Reporting có thể không phát hiện đầy đủ. Phối hợp với request logs và Monitoring.

## 7. Phân tích latency: p50, p95, p99 và Cloud Trace

| Chỉ số | Ý nghĩa | Cảnh báo khi |
| --- | --- | --- |
| `p50` | Một nửa request nhanh hơn ngưỡng | Nhiều người dùng bị chậm |
| `p95` | 95% request nhanh hơn ngưỡng | Nhóm request chậm đáng kể |
| `p99` | 99% request nhanh hơn ngưỡng | Tail latency/SLO bị ảnh hưởng |
| Instance count | Số instance đang chạy | Scale-out bất thường hay không đủ năng lực |
| CPU/memory | Tài nguyên bị đẩy sát giới hạn? | JVM GC, thiếu memory hoặc nghẽn CPU |
| Downstream duration | Cloud SQL/Storage/external API chậm? | Latency tăng nhưng CPU app bình thường |

**Phân tích theo version**, không chỉ service aggregate. Nếu `p50` bình thường nhưng `p99` rất cao, một nhóm nhỏ requests có thể chịu cold start, GC pause hoặc connection pool wait.

**Cloud Trace** hỗ trợ xác định thời gian request và downstream spans **nếu ứng dụng đã bật instrumentation/sampling phù hợp**; không giả định mọi request tự xuất hiện đầy đủ span từ code Java. Với Spring Boot, có thể dùng OpenTelemetry/Cloud Trace exporters được phê duyệt, bảo đảm không xuất PII trong span attributes.

### 7.1. Chẩn đoán cold start Java

App Engine Standard automatic có thể scale về 0, khiến request đầu sau thời gian nhàn rỗi phải khởi tạo instance và JVM. Kiểm tra:

- Thời gian tạo instance và init của Spring Boot.
- Class loading, dependency injection và kết nối Cloud SQL khi startup.
- `instance_class` có đủ memory/CPU; tránh tăng class mà không có số liệu.
- `min_instances`/warmup requests nếu SLA yêu cầu latency ổn định, đồng thời tính **phí instance luôn sẵn sàng**.

App Engine Flexible thường duy trì min instances nên không scale về 0 như Standard automatic, nhưng vẫn có restart/redeploy/health events tạo startup latency.

## 8. Logs không được làm tăng rủi ro và hóa đơn

**Logging nhiều hơn** không đồng nghĩa chẩn đoán hiệu quả hơn. Một dòng log cho từng object/item trong batch có thể tạo hàng triệu records, tăng chi phí ingestion và che lỗi quan trọng.

| Cách làm | Lợi ích | Cảnh báo |
| --- | --- | --- |
| Ưu tiên structured logs | Lọc theo `errorCode`, `version`, `requestId` | Tránh field cardinality cao khi làm metrics |
| Giảm DEBUG/INFO lặp lại | Giảm volume và noise | Giữ log đủ truy vết incident |
| Sampling request success logs | Giảm dữ liệu ở traffic lớn | Không sample mất những lỗi quan trọng |
| Cloud Logging exclusion filters | Giảm log ingestion vào bucket được chọn | Có thể mất khả năng điều tra hoặc vi phạm retention policy |
| Log sinks tới Cloud Storage/BigQuery | Lưu dài hạn hoặc phân tích riêng | Có phí storage/queries/egress riêng |
| Retention phù hợp | Tối ưu lưu trữ và tuân thủ | Không xóa audit logs cần giữ |

**Không loại bỏ audit/security logs hay request errors chỉ để giảm phí** khi chưa có đánh giá Security/SRE. Không đưa secrets vào logs ngay từ nguồn; exclusion filter không phải biện pháp che dữ liệu đã rò.

## 9. Những khoản có thể làm App Engine tốn tiền

| Nguồn phí | Standard | Flexible | Ghi chú |
| --- | --- | --- | --- |
| Instances | Instance class/hours, có free quotas theo loại | vCPU/memory/disk tài nguyên VM, không free tier App Engine | Các versions có thể cùng tạo tải tính phí |
| Network egress | Theo network pricing/quota | Theo network pricing | Không nhầm ingress với egress |
| Cloud SQL | Tách khỏi App Engine | Tách khỏi App Engine | Pool, connections và instance DB |
| Cloud Storage | Lưu trữ/operations/egress | Tương tự | Tệp ứng dụng trên bucket không tự miễn phí |
| Cloud Logging | Ingestion/storage theo chính sách giá | Tương tự | Debug spam và sinks có thể tạo phí |
| Trace/Monitoring | Theo tính năng/volume | Theo tính năng/volume | Kiểm tra observability pricing |
| Extra services/versions | Có thể phát sinh instance costs | Có thể duy trì VM tối thiểu | Version 0% traffic không đồng nghĩa 0 chi phí |

**Standard có free tier, Flexible không có.** Các quota/free tier có thể thay đổi theo region, resource và gói giá; không dùng một giá F1/CPU-hour từ vùng khác làm dự báo chắc chắn. Luôn tra [App Engine pricing](https://cloud.google.com/appengine/pricing) và Cloud Billing SKUs thực tế.

### 9.1. Ước lượng chi phí theo giả định

Giả sử **một service Flexible** giữ hai instances trong 30 ngày, cả khi không có request:

~~~text
Instance-hours nền = 2 instances × 24 giờ × 30 ngày
                     = 1.440 instance-hours
~~~

Với Flexible, bill thực được cấu thành theo **vCPU, memory, disk và networking** của VM; không lấy 1.440 nhân bừa với “một đơn giá instance” chung. Nếu giữ **hai versions** độc lập, mỗi version có tối thiểu 2 instances, năng lực nền có thể tương đương **4 instances**, chưa kể canary/rollout và các dịch vụ phụ trợ.

Ví dụ chỉ giải thích **tác động của min instances**, không phải báo giá Google Cloud.

## 10. Standard: cấu hình automatic scaling cân bằng chi phí/SLO

Ví dụ `app.yaml` cho ứng dụng Java 21 chạy **Standard**:

~~~yaml
runtime: java21
service: orders-api
instance_class: F2

automatic_scaling:
  min_instances: 0
  max_instances: 5
  target_cpu_utilization: 0.65
  max_concurrent_requests: 20
~~~

Giải thích:

- `min_instances: 0`: cho phép giảm instance nền khi không có request; **cold start có thể tăng**.
- `max_instances: 5`: hạn chế scale-out và phần chi phí liên quan, nhưng nếu traffic vượt năng lực sẽ tăng latency hoặc lỗi.
- `target_cpu_utilization`: ngưỡng cân bằng CPU và số instances; không phải giới hạn cứng CPU.
- `max_concurrent_requests`: số requests tối đa trên mỗi instance trong cơ chế automatic scaling; nên load test với Java thread pools và DB connections.
- `F2`: tài nguyên lớn hơn `F1`, không mặc định rẻ hơn; so p95/error rate, không chỉ instance count.

**Điểm dễ nhầm:** `max_instances: 0` **không có nghĩa chạy 0 instances**; trong cấu hình Standard hiện hành, 0 có thể mang nghĩa vô hiệu hóa giá trị cấu hình max, còn khi bỏ field thì hệ thống dùng mặc định tương ứng. Từ **tháng 3/2025**, App Engine áp giới hạn mặc định **20 max instances** cho **ứng dụng Standard mới**, không tự áp thay đổi giống vậy lên ứng dụng cũ. Hãy **khai báo max hợp lý** và kiểm tra quota/Direct VPC egress nếu dùng.

### 10.1. Min instances có tác động tiền bạc

Tăng `min_instances` giúp giảm cold start nhưng giữ instances chạy, **có thể phát sinh phí dù không có request**. Theo tài liệu Standard, để min instances hoạt động đúng với traffic cần cân nhắc cấu hình **warmup requests**; riêng các versions không nhận traffic có quy tắc min_instances khác. Không tăng min chỉ để chữa một request chậm trước khi xác định nguyên nhân là cold start hay database.

## 11. Flexible: chú ý VM nền và min instances

Ví dụ **đoạn scaling** trong `app.yaml` của Flexible (không phải file runtime đầy đủ):

~~~yaml
automatic_scaling:
  min_num_instances: 2
  max_num_instances: 4
  cool_down_period_sec: 180
  cpu_utilization:
    target_utilization: 0.6
~~~

Đối với Flexible:

- `min_num_instances` tối thiểu **1**, mặc định thường **2** để giảm latency; đây là nguồn phí nền kể cả ít traffic.
- `max_num_instances` giới hạn khả năng mở rộng, nhưng không nên nhỏ hơn nhu cầu SLA.
- `cool_down_period_sec` tránh dùng số liệu CPU trong thời gian khởi tạo instance; tăng quá cao làm autoscaling phản ứng chậm.
- Chọn vCPU/memory/disk theo hiệu năng JVM, Cloud SQL connection pool và vùng chạy.

Không áp khóa `min_instances/max_instances` của Standard vào Flexible; Flexible dùng `min_num_instances/max_num_instances`. Để deploy Java Flexible còn phải có cấu hình **runtime, env: flex, runtime_config/resources** tương thích phiên bản được hỗ trợ. Vì bài tập trung vào logs và cost, không dùng fragment này như một manifest hoàn chỉnh để deploy.

## 12. Quản lý versions: traffic và chi phí không luôn đi cùng

Một ứng dụng có `v1` ổn định và `v2` canary. Nếu `v2` lỗi, có thể đưa traffic về `v1`:

~~~bash
# Lệnh thay đổi traffic THẬT: chỉ chạy sau change approval.
gcloud app services set-traffic orders-api \
  --splits=v1=1 \
  --project=PROJECT_ID
~~~

Đây là **App Engine traffic**, khác lệnh `gcloud run services update-traffic` của Cloud Run. App Engine hỗ trợ `--split-by=ip|cookie|random` (mặc định thường là `ip`), nên tỷ lệ split không đồng nghĩa đúng tỷ lệ từng request hoặc từng user.

**Các lưu ý quan trọng:**

- Version-specific URL có thể được gọi trực tiếp, bypass traffic split; kiểm tra access/traffic thực.
- Đưa version về 0% traffic **không bảo đảm dừng toàn bộ chi phí**; với Flexible hoặc manual scaling, instances/VM có thể vẫn hoạt động.
- `gcloud app versions stop` theo tham chiếu CLI hiện tại **chỉ dùng được cho version có manual scaling**; không hướng dẫn dùng nó như công tắc tắt mọi version.
- Chỉ xóa version không còn cần sau khi biết **traffic, dependency, rollback và dữ liệu liên quan**. Không xóa version đang phục vụ hoặc version duy nhất cần thiết cho ứng dụng.

Để kiểm tra trước khi dọn:

~~~bash
gcloud app versions list \
  --service=orders-api \
  --project=PROJECT_ID

gcloud app versions describe v2 \
  --service=orders-api \
  --project=PROJECT_ID
~~~

Nếu có nhu cầu xóa **version lab** đã dừng sử dụng:

~~~bash
# CẢNH BÁO: xóa version thật, không có undo đơn giản.
gcloud app versions delete v2 \
  --service=orders-api \
  --project=PROJECT_ID
~~~

**Không tự xóa version production chỉ vì traffic = 0%**: nó có thể cần cho rollback, URL trực tiếp, background services hoặc giao tiếp giữa services. Xem trong Billing Reports liệu phí thật đến từ version đó hay là Cloud SQL/network/logging.

## 13. Billing Reports, budgets và cảnh báo bất thường

### 13.1. Định vị SKU tốn phí

Trong Console:

1. Vào **Billing → Reports**, chọn billing account và khoảng ngày trước/sau sự cố.
2. Lọc **Project**, sau đó group theo **Service/SKU** để biết phần tăng đến từ App Engine, Cloud SQL, Network hay Logging.
3. So sánh ngày bình thường với ngày deploy `v2`; ghi tổng cost, xu hướng và chênh lệch.
4. Đối chiếu với **instance count, request rate, egress bytes, log volume** trong Cloud Monitoring.

Không suy ra toàn bộ hóa đơn tăng là do App Engine nếu Cloud SQL đang auto scale/tăng storage hoặc logs bị nhân nhiều lần.

### 13.2. Budget alert không phải hard cap

Tạo **Cloud Billing budget dạng cảnh báo** cho project/phần dịch vụ được phép, đặt ngưỡng ví dụ 50%, 80%, 100% và forecast. **Alert-only budget chỉ thông báo**, không tự ngăn App Engine tiếp tục hoạt động và tính phí; báo cáo billing có thể trễ.

Tại thời điểm tài liệu được kiểm tra, **spend cap budgets** của Cloud Billing có danh sách dịch vụ đủ điều kiện riêng và **không liệt kê App Engine** trong các dịch vụ được hỗ trợ. Vì vậy, không hứa người học đã có “hard cap App Engine” chỉ vì tạo budget.

### 13.3. Khi chi phí bất thường vượt ngưỡng

- Cảnh báo FinOps và on-call; xác minh số liệu và nguồn phí.
- Hạn chế `max_instances` hoặc giảm tài nguyên **chỉ khi load test/SLO cho phép**.
- Xử lý log spam, lỗi retry và vòng lặp requests.
- Đánh giá version cũ/VM nền, nhưng giữ rollback target cần thiết.
- **Disable App Engine application** là biện pháp khẩn cấp có thể làm **toàn bộ requests thất bại**; chỉ thực hiện theo quy trình được duyệt. Dữ liệu/config App Engine có thể còn, nhưng các sản phẩm Google Cloud khác **vẫn tiếp tục tính phí**.

Không tự động disable billing/toàn project khi nhận budget Pub/Sub event mà chưa đánh giá phạm vi ảnh hưởng và tính không tức thời của dữ liệu billing.

## 14. Lab an toàn: điều tra giả lập mà không thay production

**Bối cảnh giả định:** `orders-api` có `v1` 90% request, `v2` 10%; v2 báo HTTP 5xx tăng và hóa đơn tăng.

### Bước 1 – Xác nhận phiên bản và logs

~~~bash
gcloud app versions list \
  --service=orders-api --project=PROJECT_ID

gcloud app logs read \
  --service=orders-api --version=v2 \
  --level=error --limit=50 \
  --project=PROJECT_ID
~~~

### Bước 2 – Lọc request lỗi

Dán vào Logs Explorer, thay version nếu cần:

~~~text
resource.type="gae_app"
resource.labels.module_id="orders-api"
resource.labels.version_id="v2"
httpRequest.status>=500
~~~

Ghi lại **5 request IDs/trace IDs**, status, path và latency; không sao chép PII.

### Bước 3 – Đối chiếu metrics

Trong **Monitoring/App Engine dashboard**, so p95 latency, HTTP 5xx, request count và số instances của **v1/v2** cùng khoảng thời gian. Kiểm tra Cloud SQL connections, CPU, memory và startup errors nếu có.

### Bước 4 – Kiểm tra Billing

Dùng Billing Reports lọc project, service và SKU để xác định phần tăng do **instance hours, network, Logging hay Cloud SQL**. Nếu có bản ghi cost trong quá trình điều tra, lưu **số liệu, khung giờ và giả thuyết**, không tự kết luận nguyên nhân chỉ từ một biểu đồ.

### Bước 5 – Viết đề xuất thay đổi

Ví dụ:

~~~text
Issue: v2 5xx tăng sau deploy 09:00 UTC
Evidence: request logs + app errorCode + p95 + Cloud SQL pool
Cost source: Flex instance baseline hoặc logs tăng
Proposed mitigation: giảm traffic v2 / sửa connection pool / log sampling
Risk: giữ khả năng rollback và business continuity
Verify: 5xx, p95, order success, instance count, daily cost trend
Owner: SRE + backend + FinOps
~~~

**Mặc định lab này chỉ đọc.** Không chạy `gcloud app deploy`, `set-traffic`, `versions delete` hoặc thay `app.yaml` trên production để hoàn thành bài tập. Nếu có môi trường lab riêng, thực hiện thay đổi dưới sự giám sát và dùng runbook rollback đã chuẩn bị.

## 15. Bảng xử lý lỗi và tín hiệu thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| 5xx chỉ ở `v2` | Code/config mới, secret, schema không tương thích | Logs theo version, deployment diff, rollback plan |
| 5xx ở cả v1/v2 | Cloud SQL, network, IAM, dependency chung | Trace, downstream metrics, quota |
| `429` hoặc timeout tăng khi giới hạn instances | `max_instances` quá thấp, request backlog | Instance count, queue/latency, sizing |
| p99 cao nhưng p50 bình thường | Cold start, JVM GC, slow tail requests | Trace, JVM metrics, startup logs |
| Logs Explorer không thấy request | Sai project/time/resource/version/log type | `gae_app`, `request_log` vs `nginx.request` |
| Có app logs nhưng không nhóm dưới request | Thiếu trace correlation | `X-Cloud-Trace-Context`, trace field |
| Không tìm được error group | Log exception không nhận diện, lỗi chỉ ở HTTP status | Request logs + Error Reporting + stack trace |
| Chi phí tăng khi traffic giảm | Min/manual/Flex instances hoặc version cũ | Scaling config, version list, SKU |
| Chi phí Cloud Logging tăng | DEBUG logs, retries/loops, stdout spam | Log volume by source, exclusions có kiểm soát |
| App Engine Standard khởi động chậm | Instance scale-to-zero, JVM startup | Startup logs, warmup/min instances, SLO |
| App Engine Flexible không scale về 0 | Có min instances ≥ 1 | Mô hình tính phí Flex, min_num_instances |
| Sau rollback vẫn có request ở v2 | Version URL trực tiếp, propagation, sessions | Traffic split, URLs, timestamps |

## 16. Tình huống tổng hợp: vừa giảm lỗi vừa giảm phí

Nhóm Commerce triển khai Java `orders-api v2` trên Flexible. Sau hai ngày, 5xx tăng từ **0,2% lên 2,1%** và bill cao hơn. Điều tra cho thấy v2 đã tăng connection pool tới Cloud SQL, đồng thời rollout giữ cả v1 và v2 với **min 2 instances mỗi version**. Việc logging từng attempt vào database cũng làm log ingestion tăng.

**Kế hoạch có căn cứ:**

1. Đọc request logs v2 và trace: xác nhận 5xx tập trung ở lỗi timeout kết nối Cloud SQL.
2. Xem số instances, Cloud SQL connection count và log volume theo thời điểm.
3. Với lỗi chỉ ở v2, chuyển traffic về v1 theo runbook; kiểm tra schema/data tương thích trước.
4. Sửa pool settings, bounded retry, giảm duplicate DEBUG logs và kiểm thử staging.
5. Khi phát hành lại v2, rollout từng phần; đo 5xx, p95, business success rate và pool saturation.
6. Sau cửa sổ rollback, quản trị version cũ để không tiếp tục giữ VM nền không cần.
7. Kiểm tra Billing Reports sau khi cập nhật; không kỳ vọng bill giảm tức thời do độ trễ báo cáo.

**Tách hai đích:** giảm instances/logs không được đánh đổi mất dữ liệu đơn hàng hoặc vượt SLO. Quyết định cost chỉ hợp lệ khi metrics chứng minh hệ thống vẫn tin cậy.

## 17. Bài tập tự kiểm tra

**Câu 1.** Request log trả HTTP 500, app log `DB_TIMEOUT`. Nên điều tra tiếp ở đâu?

*Đáp án:* Trace và Cloud SQL connection/pool/latency; status 500 chỉ là triệu chứng.

**Câu 2.** Vì sao cần lọc `resource.labels.version_id` khi v2 mới rollout 5%?

*Đáp án:* Tổng service có thể che lỗi của v2 vì v1 nhận phần lớn request.

**Câu 3.** `resource.type` của App Engine là gì, label service name tên nào?

*Đáp án:* `gae_app`; service nằm ở `resource.labels.module_id`.

**Câu 4.** Standard và Flexible có free tier App Engine giống nhau không?

*Đáp án:* Không. Standard có free tier theo quota; Flexible không có free tier App Engine.

**Câu 5.** `min_instances: 0` trong Standard có bảo đảm không có cold start?

*Đáp án:* Không. Scale về 0 có thể dẫn đến khởi tạo JVM khi request mới đến.

**Câu 6.** Tăng `min_num_instances` Flexible từ 2 lên 4 có thể làm chi phí nền đổi thế nào?

*Đáp án:* Có thể tăng gần gấp đôi lượng VM tối thiểu, tùy cấu hình/tài nguyên/thời gian chạy.

**Câu 7.** Vì sao không đặt `max_instances: 1` cho mọi production app để tiết kiệm?

*Đáp án:* Giới hạn quá thấp có thể tăng latency, làm rớt request hoặc vi phạm SLO.

**Câu 8.** `max_instances: 0` Standard có nghĩa tắt service không?

*Đáp án:* Không; đây không phải cơ chế tắt mọi instances.

**Câu 9.** Version Flexible nhận 0% traffic có chắc miễn phí không?

*Đáp án:* Không. Min/manual instances và tài nguyên liên quan có thể còn tính phí.

**Câu 10.** Tạo Billing budget cảnh báo 100% có chặn App Engine sử dụng thêm không?

*Đáp án:* Không. Alert-only budgets không tự giới hạn spending; cần phản ứng/kiểm soát vận hành phù hợp.

**Câu 11.** Vì sao không nên xóa tất cả `request_log` để giảm Logging cost?

*Đáp án:* Mất bằng chứng debug/SLO/audit; cần chọn sampling/exclusion có trách nhiệm.

**Câu 12.** `gcloud app versions stop` có phải cách chung để dừng mọi version auto-scaling không?

*Đáp án:* Không. CLI stop hiện áp dụng với manual scaling; cần xem loại version/cấu hình và giải pháp hợp lệ.

**Câu 13.** p99 tăng nhưng p50 không đổi gợi ý điều gì?

*Đáp án:* Một nhóm nhỏ requests chậm do cold start, GC pause, pool wait hoặc external dependency.

**Câu 14.** Sau rollback v2, vì sao vẫn cần đo Cloud SQL và business errors?

*Đáp án:* Migration/data/external state không tự rollback cùng App Engine traffic; lỗi có thể tồn tại ở dependency.

## 18. Checklist production

- [ ] Biết project, App Engine service, version và Standard/Flexible trước khi debug.
- [ ] Request logs và app logs có severity, errorCode, trace/request correlation.
- [ ] Logs không chứa PII, tokens hoặc bí mật; logging volume có owner.
- [ ] Có dashboard 5xx, p95/p99, traffic, instance count, CPU/memory và dependency metrics.
- [ ] Cảnh báo theo SLO và version canary, không chỉ tổng service.
- [ ] Error Reporting/Trace có instrumentation và permissions phù hợp.
- [ ] Standard có `instance_class`, `min_instances`, `max_instances` và concurrency đã load test.
- [ ] Flexible có `min_num_instances` và sizing CPU/memory/VM nền rõ ràng.
- [ ] Có kiểm kê versions, URL trực tiếp, traffic split và rollback plan.
- [ ] Phân biệt phí App Engine với Cloud SQL, Storage, Network, Logging.
- [ ] Có Billing Reports, alert-only budgets, alert owner và quy trình phản ứng.
- [ ] Không coi budget là hard cap App Engine hoặc đổi max_instances là tối ưu vô hại.
- [ ] Log exclusions/sinks/retention được Security/SRE duyệt.
- [ ] Mọi thay đổi traffic, scaling, disable app hoặc delete version đều được phê duyệt.
- [ ] Đã diễn tập 5xx incident, kiểm chứng rollback và đo cost sau thay đổi.

## 19. Kết luận

**Quan sát App Engine đúng cách cần ghép request logs, app logs, version labels, metrics và traces; kiểm soát chi phí cần đọc Billing SKUs trước khi chỉnh scaling.** Standard và Flexible có cơ chế tính phí khác nhau; version 0% traffic không đồng nghĩa 0 chi phí, và Billing alerts không phải phanh khẩn cấp tự động. Quy trình đáng tin cậy là **đo – khoanh vùng – sửa – xác minh – theo dõi chi phí**, thay vì xóa log hoặc hạ instances một cách cảm tính.

## Tài liệu tham khảo chính thức

- [App Engine overview](https://cloud.google.com/appengine/docs/an-overview-of-app-engine)
- [App Engine Standard: Write and view logs](https://cloud.google.com/appengine/docs/standard/writing-application-logs)
- [App Engine Flexible: Write and view logs](https://cloud.google.com/appengine/docs/flexible/writing-application-logs)
- [Troubleshoot App Engine Standard](https://cloud.google.com/appengine/docs/standard/troubleshooting)
- [App Engine Standard: How instances are managed](https://cloud.google.com/appengine/docs/standard/how-instances-are-managed)
- [App Engine Standard: app.yaml reference](https://cloud.google.com/appengine/docs/standard/reference/app-yaml)
- [App Engine Flexible: app.yaml reference](https://cloud.google.com/appengine/docs/flexible/reference/app-yaml)
- [Manage App Engine costs](https://cloud.google.com/appengine/docs/standard/managing-costs)
- [App Engine pricing](https://cloud.google.com/appengine/pricing)
- [Cloud Logging monitored resource types](https://cloud.google.com/logging/docs/api/v2/resource-list)
- [gcloud app logs read](https://cloud.google.com/sdk/gcloud/reference/app/logs/read)
- [gcloud app logs tail](https://cloud.google.com/sdk/gcloud/reference/app/logs/tail)
- [gcloud app services set-traffic](https://cloud.google.com/sdk/gcloud/reference/app/services/set-traffic)
- [gcloud app versions stop](https://cloud.google.com/sdk/gcloud/reference/app/versions/stop)
- [Cloud Billing budgets and alerts](https://cloud.google.com/billing/docs/how-to/budgets)
- [Cloud Billing spend cap eligible services](https://cloud.google.com/billing/docs/how-to/budgets-spend-caps)

