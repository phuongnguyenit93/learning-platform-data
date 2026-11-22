# Logs Explorer và ngôn ngữ truy vấn nhật ký

Cloud Logging thu thập log từ dịch vụ Google Cloud, ứng dụng và hạ tầng mà tổ chức kết nối vào hệ thống. Khi một request lỗi, một workload khởi động lại hoặc một thay đổi IAM bất thường xuất hiện, người vận hành cần tìm đúng bản ghi, thu hẹp theo tài nguyên và thời gian, rồi lần theo danh tính, request hoặc trace liên quan. Logs Explorer cung cấp giao diện để thực hiện công việc đó; Logging query language (LQL) giúp diễn đạt bộ lọc chính xác và có thể lưu lại để dùng nhiều lần.

Trong phạm vi **CLOUD_PROVIDERS_GCP**, kỹ năng đọc log gắn với vận hành project, IAM, VPC, Compute Engine, GKE, Cloud Run, lưu trữ và cơ sở dữ liệu. Log là bằng chứng để hiểu hành vi của các dịch vụ này, xác định nguyên nhân lỗi, kiểm tra thay đổi cấu hình, theo dõi độ tin cậy và hỗ trợ kiểm soát chi phí.

Sau bài học, người học có thể:

- Chọn đúng project, phạm vi tài nguyên, log view và khoảng thời gian trong Logs Explorer.
- Nhận biết các trường quan trọng của một LogEntry và phân biệt log dạng text, JSON và audit.
- Viết truy vấn LQL bằng phép so sánh, điều kiện logic, tìm kiếm chuỗi và biểu thức chính quy.
- Tạo bộ lọc cho Compute Engine, GKE, Cloud Run, Cloud Audit Logs và request cụ thể.
- Dùng kết quả để lần theo lỗi, danh tính thực hiện thao tác và trace của request.
- Lưu truy vấn hữu ích, chia sẻ đúng phạm vi và chuyển tín hiệu quan trọng thành metric hoặc cảnh báo.

## 1. Logs Explorer nằm ở đâu trong Cloud Logging?

Cloud Logging nhận log từ nhiều nguồn, chuẩn hóa chúng thành log entry rồi lưu theo cấu hình của log bucket và log view. Logs Explorer là giao diện để khám phá và truy vấn các entry mà người dùng được phép xem. Nó không phải nơi duy nhất tạo ra log và cũng không tự động bảo đảm mọi loại sự kiện đều đã được ghi lại.

Một luồng tổng quát:

~~~mermaid
flowchart LR
    A[VM, GKE, Cloud Run, Cloud SQL] --> C[Cloud Logging]
    B[Cloud Audit Logs và ứng dụng] --> C
    C --> D[Log Router]
    D --> E[Log buckets]
    D --> F[Log sinks và đích lưu trữ khác]
    E --> G[Logs Explorer]
    G --> H[LQL query]
    G --> I[Điều tra và đối chiếu]
    I --> J[Metric, alert và xử lý sự cố]
~~~

Các khái niệm cần phân biệt:

- **Log entry** là một bản ghi sự kiện. Nó có thời gian, tài nguyên phát sinh, mức độ nghiêm trọng và payload chứa thông tin cụ thể.
- **Log Router** tiếp nhận log và áp dụng inclusion filter/exclusion filter để quyết định log được lưu ở bucket nào hoặc chuyển tới sink nào.
- **Log bucket** là nơi lưu log trong Cloud Logging, có cấu hình vị trí và thời hạn lưu giữ.
- **Log view** là góc nhìn giới hạn tập log trong bucket; quyền truy cập vào view có thể được cấp riêng.
- **Logs Explorer** truy vấn log entry trong phạm vi người dùng đã chọn và được cấp quyền.

Nếu một sự kiện không xuất hiện, nguyên nhân có thể là ứng dụng chưa ghi log, dịch vụ chưa bật loại audit log cần thiết, Log Router loại trừ entry, log đã hết thời hạn lưu giữ, phạm vi truy vấn không đúng hoặc người dùng thiếu quyền. Viết lại truy vấn không thể khôi phục một log chưa từng được thu thập.

### 1.1. Logs Explorer và Logs Analytics

Hai công cụ có mục đích gần nhau nhưng dùng ngôn ngữ khác nhau:

| Công cụ | Ngôn ngữ | Công việc phù hợp |
|---|---|---|
| Logs Explorer | Logging query language (LQL) | Tìm entry, lọc theo resource, severity, payload, thời gian và điều tra một sự kiện |
| Logs Analytics | SQL trên log bucket đã bật phân tích | Tổng hợp, nhóm, tính toán và phân tích tập log theo dạng bảng |

Ví dụ, LQL dùng `severity >= ERROR` để lọc entry có mức lỗi trở lên. Trong Logs Analytics, người dùng viết câu lệnh SQL với `SELECT`, `WHERE`, `GROUP BY` và các hàm tổng hợp. Không dán truy vấn LQL vào trình soạn SQL hoặc ngược lại.

## 2. Bắt đầu với giao diện Logs Explorer

Tên và vị trí một số điều khiển có thể thay đổi theo phiên bản giao diện, nhưng quy trình tìm log vẫn gồm các bước chính.

### 2.1. Chọn phạm vi và thời gian

1. Mở Logs Explorer trong Google Cloud Console.
2. Chọn project, resource scope hoặc log view phù hợp với nơi log được lưu.
3. Chọn khoảng thời gian cần điều tra. Có thể dùng khoảng thời gian có sẵn hoặc đặt thời điểm bắt đầu/kết thúc.
4. Xác định dịch vụ và loại tài nguyên phát sinh log, ví dụ `gce_instance`, `k8s_container` hoặc `cloud_run_revision`.
5. Chạy truy vấn rồi quan sát histogram và danh sách entry trả về.

Khoảng thời gian trên giao diện là một giới hạn quan trọng của kết quả. Nếu truy vấn có thêm điều kiện `timestamp`, điều kiện đó sẽ kết hợp với khoảng thời gian đang chọn. Khi kết quả rỗng, kiểm tra cả hai nơi. Thời gian trong log entry thường được biểu diễn theo UTC; hãy quy đổi múi giờ khi đối chiếu với thời điểm người dùng báo lỗi.

### 2.2. Query Builder và Query language

**Query Builder** phù hợp khi mới bắt đầu hoặc cần thêm điều kiện bằng các trường có sẵn. Người dùng chọn resource, log name, severity và một số thuộc tính; giao diện tạo bộ lọc tương ứng.

**Query language** phù hợp khi cần điều kiện lồng nhau, tìm kiếm trong payload, biểu thức chính quy, truy vấn audit log hoặc tái sử dụng một bộ lọc dài. Có thể chuyển từ bộ lọc trực quan sang truy vấn LQL để xem cú pháp được tạo ra, sau đó chỉnh sửa trực tiếp.

Khi một entry được mở rộng, hãy kiểm tra resource, timestamp, severity và payload. Với log có cấu trúc, mở rộng `jsonPayload` để xem tên trường thực tế; với audit log, xem `protoPayload`; với log text, xem `textPayload`. Có thể dùng thao tác thêm trường vào truy vấn từ giao diện nếu muốn lọc tiếp theo một giá trị đang thấy.

### 2.3. Đọc kết quả

- **Histogram** cho thấy mật độ entry theo thời gian. Một đỉnh tăng đột ngột có thể trùng với thời điểm phát hành hoặc sự cố.
- **Danh sách log** cho thấy các entry khớp điều kiện, thường được sắp xếp theo thời gian.
- **Chi tiết entry** cho phép xem các trường đầy đủ, resource labels và payload.
- **Liên kết trace** nếu có giúp chuyển từ log sang các span liên quan trong Cloud Trace.
- **Trường resource** cho biết log đến từ loại tài nguyên nào và thuộc project, cluster, instance, service hoặc namespace nào.

Không kết luận hệ thống không có lỗi chỉ vì không thấy entry `ERROR`. Một ứng dụng có thể ghi lỗi ở `WARNING`, dùng payload riêng, hoặc không ghi log khi request thất bại. Hãy hiểu cách ứng dụng phát log trước khi chọn bộ lọc.

## 3. Cấu trúc một LogEntry

Cloud Logging biểu diễn sự kiện dưới dạng `LogEntry`. Các trường phổ biến:

| Trường | Ý nghĩa | Khi nào dùng |
|---|---|---|
| `logName` | Tên log, bao gồm project và log ID | Chỉ lấy audit log, log ứng dụng hoặc một log cụ thể |
| `resource.type` | Loại monitored resource | Phân biệt VM, container, Cloud Run, database |
| `resource.labels` | Nhãn định danh resource | Lọc theo instance, cluster, namespace, service hoặc location |
| `timestamp` | Thời điểm sự kiện xảy ra | Điều tra theo thời gian thực tế |
| `receiveTimestamp` | Thời điểm Cloud Logging nhận entry | Đối chiếu độ trễ gửi log |
| `severity` | Mức độ nghiêm trọng | Tập trung vào WARNING, ERROR hoặc cao hơn |
| `insertId` | Định danh entry trong log | Đối chiếu hoặc loại trùng trong một số luồng xử lý |
| `textPayload` | Nội dung dạng văn bản | Tìm thông báo do ứng dụng hoặc hệ điều hành ghi |
| `jsonPayload` | Nội dung có cấu trúc JSON | Lọc theo request ID, status code, tên module hoặc trường tùy chỉnh |
| `protoPayload` | Nội dung protobuf, thường gặp trong audit log | Tìm principal, method, resource và trạng thái thao tác |
| `labels` | Nhãn do hệ thống hoặc người phát log gắn vào | Phân nhóm hoặc lọc theo ngữ cảnh bổ sung |
| `httpRequest` | Thông tin request HTTP nếu có | Tìm method, URL, status hoặc latency |
| `trace`, `spanId` | Định danh trace và span | Liên kết log với request phân tán |
| `operation` | Thông tin nhóm các entry thuộc một operation | Theo dõi operation nhiều bước |

`logName` thường có dạng:

~~~text
projects/PROJECT_ID/logs/LOG_ID
~~~

Trong đường dẫn resource, tên trường được phân tách bằng dấu chấm. Ví dụ `resource.labels.cluster_name` hoặc `jsonPayload.requestId`. Tên trường cần khớp chính xác với cấu trúc entry thực tế; không tự suy ra tên JSON từ nội dung thông báo.

### 3.1. Ba kiểu payload thường gặp

**Text payload** lưu một chuỗi:

~~~text
textPayload: "upstream connection timed out"
~~~

**JSON payload** lưu dữ liệu có cấu trúc:

~~~json
{
  "severity": "ERROR",
  "message": "payment request failed",
  "requestId": "req-82f1",
  "httpStatus": 502,
  "durationMs": 3100
}
~~~

Trong Logs Explorer, các trường này có thể được truy vấn như `jsonPayload.requestId`, `jsonPayload.httpStatus` và `jsonPayload.durationMs`.

**Proto payload** xuất hiện trong các log có cấu trúc protobuf, đặc biệt Cloud Audit Logs. Ví dụ, `protoPayload.authenticationInfo.principalEmail` có thể cho biết principal thực hiện một thao tác.

### 3.2. Severity

Các mức severity chuẩn thường gặp theo thứ tự tăng dần:

`DEFAULT`, `DEBUG`, `INFO`, `NOTICE`, `WARNING`, `ERROR`, `CRITICAL`, `ALERT`, `EMERGENCY`.

Điều kiện `severity >= ERROR` lấy ERROR và các mức nghiêm trọng hơn. Không phải mọi ứng dụng đều gán severity nhất quán; nếu ứng dụng ghi chuỗi `"ERROR"` bên trong `jsonPayload.message` nhưng không đặt trường `severity`, điều kiện trên có thể không trả về entry đó.

## 4. Cú pháp cơ bản của Logging query language

LQL là ngôn ngữ biểu thức dùng để chọn log entry. Một truy vấn thường kết hợp nhiều điều kiện về resource, log name, thời gian, severity và payload.

Ví dụ:

~~~text
resource.type = "cloud_run_revision"
resource.labels.service_name = "orders-api"
severity >= ERROR
timestamp >= "2026-11-19T00:00:00Z"
~~~

Các điều kiện trên được kết hợp theo logic AND: entry phải thỏa tất cả điều kiện. Có thể viết rõ `AND` để dễ đọc khi biểu thức phức tạp.

### 4.1. So sánh và tìm kiếm

| Toán tử | Ý nghĩa | Ví dụ |
|---|---|---|
| `=` | Bằng | `severity = ERROR` |
| `!=` | Khác | `resource.type != "gce_instance"` |
| `>` / `>=` | Lớn hơn / lớn hơn hoặc bằng | `httpRequest.status >= 500` |
| `<` / `<=` | Nhỏ hơn / nhỏ hơn hoặc bằng | `jsonPayload.durationMs < 100` |
| `:` | Kiểm tra chuỗi/giá trị có chứa nội dung phù hợp | `textPayload : "timeout"` |
| `=~` | Khớp biểu thức chính quy | `textPayload =~ "timeout|deadline"` |
| `!~` | Không khớp biểu thức chính quy | `textPayload !~ "healthcheck"` |

Với trường số, dùng phép so sánh số thay vì tìm chuỗi. Ví dụ `httpRequest.status >= 500` diễn đạt đúng ý nghĩa hơn việc tìm chữ `"500"` trong toàn bộ payload.

### 4.2. Kết hợp điều kiện logic

- `AND`: tất cả điều kiện phải đúng.
- `OR`: chỉ cần một nhánh đúng.
- `NOT`: phủ định một điều kiện.
- Dấu ngoặc `(...)`: làm rõ nhóm điều kiện và thứ tự đánh giá.

Ví dụ lấy lỗi nghiêm trọng của hai dịch vụ:

~~~text
severity >= ERROR
(
  resource.labels.service_name = "orders-api"
  OR resource.labels.service_name = "payments-api"
)
~~~

Ví dụ loại bỏ log kiểm tra sức khỏe:

~~~text
resource.type = "cloud_run_revision"
severity >= WARNING
NOT textPayload : "healthcheck"
~~~

Khi kết hợp AND và OR, luôn dùng dấu ngoặc để người đọc hiểu đúng ý định và tránh truy vấn rộng hơn dự kiến.

### 4.3. Lọc trường lồng nhau và kiểm tra sự tồn tại

Dùng đường dẫn trường để đi sâu vào payload:

~~~text
jsonPayload.requestId = "req-82f1"
jsonPayload.httpStatus >= 500
protoPayload.authenticationInfo.principalEmail = "deployer@example.com"
~~~

Có thể kiểm tra một trường có tồn tại bằng toán tử `:*`:

~~~text
jsonPayload.stackTrace:*
~~~

Điều này hữu ích khi muốn tìm entry có trường stack trace mà không cần biết trước nội dung của trường đó.

### 4.4. Tìm kiếm toàn văn và biểu thức chính quy

`SEARCH("...")` tìm chuỗi trên các trường có thể tìm kiếm của entry. Đây là cách nhanh để dò từ khóa khi chưa biết thông báo nằm trong `textPayload`, `jsonPayload` hay trường khác:

~~~text
resource.type = "k8s_container"
SEARCH("connection refused")
~~~

Khi đã biết trường, nên lọc trực tiếp trường đó để truy vấn dễ hiểu và có mục tiêu hơn:

~~~text
jsonPayload.message : "connection refused"
~~~

Toán tử `=~` và `!~` dùng biểu thức chính quy theo RE2. Ví dụ:

~~~text
textPayload =~ "timeout|deadline exceeded"
~~~

RE2 không hỗ trợ mọi tính năng của các engine regex khác. Nếu biểu thức phức tạp không chạy như mong đợi, hãy giản lược mẫu hoặc kiểm tra cú pháp RE2.

### 4.5. Lọc theo thời gian và log ID

Có thể lọc thời gian ngay trong truy vấn:

~~~text
timestamp >= "2026-11-19T08:00:00Z"
timestamp < "2026-11-19T09:00:00Z"
~~~

Hai điều kiện này tạo một khoảng thời gian nửa mở, thuận tiện khi chia log theo giờ. Dùng định dạng thời gian RFC 3339/ISO 8601 có múi giờ rõ ràng; ký tự `Z` biểu thị UTC.

Hàm `log_id()` lọc theo log ID:

~~~text
log_id("cloudaudit.googleapis.com/activity")
~~~

Có thể kết hợp với điều kiện payload để tìm một thao tác quản trị cụ thể. Ví dụ trên chỉ định log Admin Activity; tên log ID phải đúng với loại audit log cần xem.

## 5. Mẫu truy vấn thực tế theo dịch vụ GCP

Các mẫu dưới đây là điểm bắt đầu. Thay project, service, cluster, namespace, instance và tên trường bằng giá trị thực tế trong môi trường đang điều tra.

### 5.1. Cloud Run: lỗi của một service

~~~text
resource.type = "cloud_run_revision"
resource.labels.service_name = "orders-api"
severity >= ERROR
~~~

Để tìm request HTTP trả về 5xx:

~~~text
resource.type = "cloud_run_revision"
resource.labels.service_name = "orders-api"
httpRequest.status >= 500
~~~

Log ứng dụng và request log có thể có cấu trúc khác nhau. Nếu truy vấn theo `httpRequest.status` không trả kết quả, mở một entry thực tế để xác định status code đang nằm trong `httpRequest`, `jsonPayload` hay thông điệp text.

### 5.2. GKE: log của namespace và container

~~~text
resource.type = "k8s_container"
resource.labels.namespace_name = "production"
resource.labels.container_name = "checkout"
severity >= WARNING
~~~

Tìm lỗi có nội dung cụ thể:

~~~text
resource.type = "k8s_container"
resource.labels.namespace_name = "production"
SEARCH("connection refused")
~~~

Khi một pod liên tục khởi động lại, log ứng dụng có thể cho biết nguyên nhân trước khi container thoát. Kết hợp log container với sự kiện Kubernetes hoặc metric về restart count để phân biệt lỗi ứng dụng, thiếu tài nguyên, lỗi probe và sự cố node.

### 5.3. Compute Engine: log theo instance

~~~text
resource.type = "gce_instance"
resource.labels.instance_id = "INSTANCE_ID"
severity >= ERROR
~~~

Nếu chưa biết instance ID, lọc theo project và vùng hoặc dùng các resource labels có sẵn trong entry. Log hệ điều hành có thể được gửi bởi Ops Agent; cần xác nhận agent và pipeline thu thập đã được cài đặt, cấu hình.

### 5.4. Cloud Audit Logs: ai đã thay đổi IAM?

~~~text
log_id("cloudaudit.googleapis.com/activity")
protoPayload.methodName : "SetIamPolicy"
~~~

Để tìm các thao tác do một principal thực hiện:

~~~text
log_id("cloudaudit.googleapis.com/activity")
protoPayload.authenticationInfo.principalEmail = "deployer@example.com"
~~~

Khi tìm thấy entry, kiểm tra thêm `protoPayload.serviceName`, `protoPayload.methodName`, `protoPayload.resourceName`, `protoPayload.request` và `protoPayload.status`. Một số trường request có thể bị lược bỏ hoặc che theo chính sách bảo vệ dữ liệu.

### 5.5. Cloud Audit Logs: request bị từ chối

~~~text
log_id("cloudaudit.googleapis.com/policy")
protoPayload.status.code = 7
~~~

Mã trạng thái `7` tương ứng `PERMISSION_DENIED` theo mã status phổ biến của Google APIs. Đọc `principalEmail`, `resourceName`, `methodName` và thông tin request để xác định principal nào bị từ chối, đang thao tác trên tài nguyên nào và bằng API nào. Không phải mọi lỗi quyền đều xuất hiện trong cùng một log ID; cần mở rộng phạm vi nếu dịch vụ ghi sự kiện ở log khác.

### 5.6. Cloud Audit Logs: truy cập dữ liệu

~~~text
log_id("cloudaudit.googleapis.com/data_access")
protoPayload.authenticationInfo.principalEmail = "analyst@example.com"
~~~

Data Access audit logs ghi nhận một số thao tác đọc/ghi dữ liệu, nhưng nhiều loại log này cần được bật rõ ràng theo dịch vụ và cấu hình tổ chức. Nếu không có entry, hãy xác minh loại audit log đã bật, phạm vi áp dụng, quyền xem private logs và thời gian lưu giữ.

### 5.7. Tìm request bằng request ID hoặc trace

Nếu ứng dụng ghi `requestId` vào JSON payload:

~~~text
jsonPayload.requestId = "req-82f1"
~~~

Nếu log có trace ID:

~~~text
trace = "projects/PROJECT_ID/traces/TRACE_ID"
~~~

Trace giúp nối các log và span của một request đi qua nhiều dịch vụ. Khi request đi qua gateway, Cloud Run, GKE và database, một trace ID nhất quán giúp giảm thời gian tìm kiếm. Việc liên kết chỉ hiệu quả khi ứng dụng và thư viện tracing truyền context đúng cách.

## 6. Quy trình điều tra một sự cố bằng Logs Explorer

Giả sử người dùng báo API thanh toán thỉnh thoảng trả HTTP 502 sau một lần phát hành. Có thể thực hiện theo quy trình sau:

1. **Chốt phạm vi:** xác nhận project production, tên service, khu vực và khoảng thời gian xảy ra lỗi. Chọn đúng resource scope và log view.
2. **Lọc tín hiệu chính:** bắt đầu bằng resource type, service name và `httpRequest.status >= 500`.
3. **Xác định thời điểm:** quan sát histogram để xem lỗi tập trung vào một khoảng ngắn hay kéo dài. Đối chiếu thời điểm phát hành.
4. **Mở entry đại diện:** đọc timestamp, revision, request URL, latency, trace và payload. Ghi lại request ID hoặc trace ID.
5. **Lần theo request:** tìm các log khác có cùng request ID hoặc trace ID ở gateway, service phụ thuộc và database.
6. **Kiểm tra thay đổi:** truy vấn Admin Activity quanh thời điểm đó để tìm thay đổi IAM, cấu hình service, network hoặc tài nguyên phụ thuộc.
7. **Đối chiếu metric:** xem request count, error rate, latency, CPU, memory, instance count và database connections trong Cloud Monitoring.
8. **Ghi nhận kết luận:** lưu truy vấn, thời điểm, resource, trace, giả thuyết, bằng chứng và hành động khắc phục.

Truy vấn khởi đầu cho ví dụ:

~~~text
resource.type = "cloud_run_revision"
resource.labels.service_name = "payments-api"
httpRequest.status >= 500
timestamp >= "2026-11-19T08:00:00Z"
timestamp < "2026-11-19T09:00:00Z"
~~~

Nếu log cho thấy lỗi chỉ xuất hiện trên revision mới, hãy so sánh log của revision cũ và mới. Nếu tất cả revision cùng lỗi, kiểm tra dịch vụ phụ thuộc như database, secret, DNS và mạng. Nếu chỉ một nhóm request lỗi, dùng request ID và trace để xác định đường xử lý khác biệt.

Log cung cấp bằng chứng về sự kiện đã được ghi nhận; nó không tự chứng minh nguyên nhân gốc. Hãy đối chiếu log với metric, trace, thay đổi triển khai và trạng thái phụ thuộc trước khi kết luận.

## 7. Lưu, tái sử dụng và chia sẻ truy vấn

Một truy vấn tốt có thể trở thành công cụ vận hành dùng lại. Trong Logs Explorer, người dùng có thể lưu truy vấn để tránh viết lại bộ lọc dài.

Khi lưu truy vấn:

- Đặt tên theo mục đích, ví dụ `prod-cloud-run-5xx` hoặc `audit-iam-policy-changes`.
- Ghi mô tả về project/resource dự kiến, khoảng thời gian và ý nghĩa của điều kiện.
- Dùng placeholder rõ ràng cho service, namespace hoặc principal cần thay đổi.
- Kiểm tra lại truy vấn sau khi đổi project hoặc log view; một truy vấn hợp lệ ở project này có thể không có kết quả ở project khác.
- Nếu chia sẻ truy vấn, xác nhận người nhận có quyền xem log và log view tương ứng. Chia sẻ câu truy vấn không tự cấp quyền đọc dữ liệu.

Tránh lưu nhiều truy vấn trùng nhau với tên không thể phân biệt. Một bộ truy vấn nhỏ, có owner và mô tả rõ ràng sẽ hữu ích hơn một danh sách dài không ai bảo trì.

## 8. Từ truy vấn đến metric và cảnh báo

Logs Explorer phù hợp để tìm và hiểu entry. Khi cần theo dõi xu hướng liên tục hoặc thông báo khi điều kiện xảy ra, hãy chuyển tín hiệu phù hợp sang Cloud Monitoring.

- **Log-based counter metric** đếm số entry khớp bộ lọc, ví dụ số lần xuất hiện một lỗi cụ thể.
- **Log-based distribution metric** trích xuất giá trị số từ payload để phân tích phân phối, ví dụ thời lượng xử lý được ứng dụng ghi lại.
- **Alerting policy** đánh giá metric hoặc điều kiện log theo chu kỳ và thông báo tới kênh trực ca.
- **Dashboard** kết hợp metric, biểu đồ và thông tin vận hành để theo dõi service.

Ví dụ, truy vấn log lỗi 5xx có thể giúp tìm các entry cụ thể. Để theo dõi error rate theo thời gian, cần metric phù hợp và mẫu số là tổng request; chỉ đếm số lỗi mà không biết tổng request có thể làm sai lệch đánh giá khi lưu lượng tăng hoặc giảm mạnh.

Khi tạo log-based metric, chọn bộ lọc ổn định, tránh nhúng request ID duy nhất vào nhãn metric vì cardinality cao có thể làm metric khó quản lý và tăng chi phí. Dùng metric cho xu hướng tổng hợp; dùng log entry để điều tra từng sự kiện.

## 9. Quyền truy cập và bảo vệ dữ liệu log

Logs Explorer chỉ hiển thị những log mà principal có quyền xem trong phạm vi đã chọn. Một số role thường gặp:

| Role | Mục đích |
|---|---|
| `roles/logging.viewer` | Xem log thông thường trong phạm vi được cấp |
| `roles/logging.privateLogViewer` | Xem thêm private logs, bao gồm nhiều Data Access audit logs |
| `roles/logging.viewAccessor` | Truy cập log view được cấp quyền |
| `roles/logging.admin` | Quản trị cấu hình Cloud Logging; quyền rộng, cần giới hạn người được cấp |

Role thực tế cần thiết còn phụ thuộc cách tổ chức cấp quyền, log scope và dịch vụ. Ưu tiên cấp quyền ở phạm vi project hoặc log view phù hợp; không cấp quyền quản trị Logging chỉ để người dùng đọc log.

Log có thể chứa email, IP, token, thông tin request hoặc dữ liệu cá nhân. Vì vậy:

- Không ghi password, access token, private key hoặc dữ liệu nhạy cảm không cần thiết vào log.
- Mask hoặc loại bỏ trường nhạy cảm trước khi ghi log.
- Giới hạn người đọc log và thời hạn lưu giữ theo yêu cầu nghiệp vụ/pháp lý.
- Kiểm soát ai được tạo sink, thay đổi exclusion filter hoặc xóa log bucket.
- Rà soát log sink để biết dữ liệu được chuyển tới project, bucket hoặc hệ thống bên ngoài nào.
- Không đưa nguyên văn log có dữ liệu nhạy cảm vào ticket hoặc trao đổi công khai.

## 10. Lỗi thường gặp khi truy vấn

**Không có kết quả.** Kiểm tra project/resource scope, log view, thời gian, resource type và tên trường. Sau đó xác minh log có được tạo, được route vào bucket đang xem và còn trong thời hạn lưu giữ hay không.

**Lọc `severity >= ERROR` nhưng không thấy lỗi.** Ứng dụng có thể ghi nội dung lỗi ở `jsonPayload.message` nhưng không đặt severity. Hãy mở entry mẫu và kiểm tra trường thực tế.

**Dùng sai tên trường.** `jsonPayload.statusCode` khác `jsonPayload.status_code`. Lấy đúng tên trường từ một entry mẫu hoặc schema của ứng dụng.

**Dùng toán tử sai kiểu.** So sánh số bằng `>=` thay vì tìm chuỗi; dùng dấu ngoặc khi kết hợp OR; kiểm tra regex theo RE2.

**Truy vấn quá rộng.** Bắt đầu bằng `SEARCH("error")` trên mọi resource có thể tạo ra nhiều kết quả nhiễu. Hãy giới hạn thời gian, resource type và service trước.

**Không thấy Data Access audit logs.** Kiểm tra audit configuration, quyền `roles/logging.privateLogViewer`, log view, phạm vi resource và retention.

**Không thấy log của workload.** Xác minh ứng dụng ghi ra stdout/stderr hoặc dùng logging client phù hợp; kiểm tra agent/collector, quyền ghi và cấu hình route.

**Nhầm Logs Explorer với Logs Analytics.** LQL dùng để lọc log entry trong Explorer; SQL dùng để phân tích bảng trong Logs Analytics. Chọn đúng công cụ trước khi viết truy vấn.

**Kết luận từ một entry đơn lẻ.** Một log có thể thiếu ngữ cảnh hoặc bị ghi trễ. Đối chiếu nhiều entry cùng request, trace, metric và audit event trước khi kết luận.

## 11. Thực hành: điều tra thay đổi IAM và lỗi API

### Tình huống A: phát hiện ai thay đổi quyền IAM

Một service production bất ngờ mất quyền đọc bucket. Nhóm vận hành cần xác định có thao tác thay đổi IAM nào xảy ra gần thời điểm bắt đầu lỗi hay không.

1. Chọn project chứa bucket hoặc project nơi policy được thay đổi.
2. Mở Logs Explorer và chọn khoảng thời gian trước/sau thời điểm lỗi.
3. Chạy truy vấn:

~~~text
log_id("cloudaudit.googleapis.com/activity")
protoPayload.methodName : "SetIamPolicy"
~~~

4. Mở entry phù hợp và ghi nhận `principalEmail`, `methodName`, `resourceName`, `timestamp` và `status`.
5. Kiểm tra request/policy delta nếu entry có cung cấp; đối chiếu với thay đổi được phê duyệt.
6. Nếu xác định thay đổi ngoài dự kiến, thực hiện quy trình ứng phó và khôi phục policy qua người có thẩm quyền.

### Tình huống B: tìm nguyên nhân API trả 5xx

Một API trên Cloud Run có tỷ lệ lỗi tăng sau khi triển khai.

1. Lọc `cloud_run_revision`, service name và `httpRequest.status >= 500`.
2. So sánh revision trong các entry lỗi.
3. Lấy trace hoặc request ID của một request đại diện.
4. Tìm các log liên quan trong cùng trace ở service phụ thuộc.
5. Đối chiếu latency, database connection, secret access và thời điểm deploy.
6. Xác định thay đổi có tương quan với lỗi, thử biện pháp khắc phục và theo dõi error rate sau thay đổi.

Hai tình huống cho thấy LQL không chỉ giúp tìm thông báo lỗi. Khi lọc đúng resource, principal, method và thời gian, log trở thành bằng chứng để kiểm tra thay đổi và lần theo đường đi của request.

## 12. Checklist truy vấn có thể vận hành lâu dài

### Trước khi chạy

- [ ] Đã chọn đúng project, resource scope hoặc log view.
- [ ] Khoảng thời gian phù hợp và múi giờ đã được xác định.
- [ ] Đã biết resource type và loại log cần tìm.
- [ ] Có quyền xem loại log tương ứng.

### Khi viết LQL

- [ ] Dùng resource và thời gian để thu hẹp trước.
- [ ] Dùng đúng tên trường từ entry mẫu.
- [ ] Dùng phép so sánh đúng kiểu dữ liệu.
- [ ] Dùng ngoặc cho biểu thức có AND/OR phức tạp.
- [ ] Regex tuân theo RE2 và được thử với entry mẫu.
- [ ] Truy vấn tìm kiếm toàn văn được giới hạn khi có thể.

### Sau khi có kết quả

- [ ] Đã mở entry và đọc payload đầy đủ.
- [ ] Đã kiểm tra principal, resource, timestamp và trace/request ID khi cần.
- [ ] Đã đối chiếu với metric, trace hoặc audit event liên quan.
- [ ] Truy vấn hữu ích đã được lưu với tên và mô tả rõ ràng.
- [ ] Cảnh báo/metric có owner và cách xử lý cụ thể.
- [ ] Log không bị chia sẻ vượt phạm vi cần thiết.

## 13. Tài liệu tham khảo chính thức

- [Logs Explorer overview and interface](https://cloud.google.com/logging/docs/view/logs-explorer-interface)
- [Logging query language](https://cloud.google.com/logging/docs/view/logging-query-language)
- [Structured logging](https://cloud.google.com/logging/docs/structured-logging)
- [Cloud Audit Logs overview](https://cloud.google.com/logging/docs/audit)
- [Routing and storage overview](https://cloud.google.com/logging/docs/routing/overview)
- [Log buckets and views](https://cloud.google.com/logging/docs/buckets)
- [Cloud Logging access control](https://cloud.google.com/logging/docs/access-control)
- [Logs Analytics overview](https://cloud.google.com/logging/docs/analyze)
- [Log-based metrics](https://cloud.google.com/logging/docs/logs-based-metrics)

Khi điều tra trên môi trường thực tế, hãy bắt đầu từ một entry mẫu để xác nhận resource type và cấu trúc payload, rồi mở rộng truy vấn từng bước. Một truy vấn có mục tiêu, có thể giải thích và tái sử dụng sẽ giúp nhóm vận hành tìm bằng chứng nhanh hơn, giảm nhiễu và đưa ra quyết định dựa trên dữ liệu.
