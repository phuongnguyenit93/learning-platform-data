# Log Analytics và phân tích nhật ký

## 1. Vì sao cần phân tích nhật ký?

Một ứng dụng Google Cloud tạo ra nhiều loại sự kiện trong suốt vòng đời hoạt động: request đến dịch vụ, lỗi trong mã nguồn, thay đổi cấu hình, thao tác IAM, truy cập cơ sở dữ liệu, sự kiện của VM hoặc container. Mỗi log entry ghi lại một sự kiện tại một thời điểm. Khi được thu thập và phân tích đúng cách, các sự kiện này giúp đội ngũ trả lời những câu hỏi vận hành quan trọng:

- Lỗi bắt đầu xuất hiện từ thời điểm nào và tập trung ở dịch vụ hoặc phiên bản nào?
- Tỷ lệ request lỗi có tăng sau một lần triển khai không?
- Tài nguyên nào tạo ra nhiều cảnh báo nhất?
- Ai đã thay đổi IAM, firewall hoặc cấu hình lưu trữ?
- Một request chậm đi qua những thành phần nào và có trace tương ứng hay không?
- Nhật ký cần được lưu ở khu vực nào và trong bao lâu để đáp ứng yêu cầu vận hành, điều tra và tuân thủ?

Trong module `CLOUD_PROVIDERS_GCP`, **Log Analytics và phân tích nhật ký** nối các dịch vụ hạ tầng với hoạt động quan sát hệ thống. Người học cần biết cách thu thập log từ Compute Engine, GKE, Cloud Run, các dịch vụ lưu trữ và cơ sở dữ liệu; định tuyến log đến nơi lưu trữ phù hợp; tìm kiếm sự kiện; dùng SQL để tổng hợp dữ liệu; và kiểm soát quyền truy cập, thời gian lưu giữ cùng chi phí.

Google Cloud cung cấp **Cloud Logging** để tiếp nhận, định tuyến, lưu trữ và truy vấn log. Trong tài liệu và giao diện Console hiện hành, giao diện phân tích log bằng SQL được gọi là **Observability Analytics**. Tên **Log Analytics** vẫn xuất hiện trong nhiều tài liệu, cách gọi quen thuộc và ngữ cảnh quản trị. Trong bài này, Log Analytics được dùng để chỉ khả năng phân tích log bằng SQL trong Cloud Logging; khi thao tác trên Console, hãy tìm trang Observability Analytics.

## 2. Kiến trúc xử lý nhật ký trong Cloud Logging

Một luồng log thường đi qua các thành phần sau:

1. **Nguồn phát sinh:** Google Cloud services, ứng dụng, VM, container, Cloud Audit Logs hoặc hệ thống bên ngoài.
2. **Cloud Logging API và Log Router:** tiếp nhận log entry, áp dụng sink và exclusion để quyết định nơi lưu trữ hoặc chuyển tiếp.
3. **Log bucket:** lưu trữ log theo khu vực, thời gian lưu giữ và cấu hình mã hóa.
4. **Log view:** cung cấp một góc nhìn có bộ lọc trên dữ liệu của bucket và hỗ trợ kiểm soát quyền truy cập.
5. **Logs Explorer:** tìm kiếm và điều tra log entry bằng Logging query language.
6. **Observability Analytics:** phân tích log bằng SQL, tổng hợp xu hướng, tạo biểu đồ và kết hợp log với trace.
7. **Đích phân tích bên ngoài:** BigQuery, Cloud Storage hoặc Pub/Sub khi cần lưu trữ, tích hợp hay xử lý tiếp.

~~~mermaid
flowchart TD
    A[Cloud Run / GKE / Compute Engine] --> D[Cloud Logging API]
    B[Cloud Audit Logs / Google Cloud services] --> D
    C[Ứng dụng / Ops Agent / hệ thống ngoài] --> D
    D --> E[Log Router]
    E --> F[Log bucket]
    E --> G[Sink đến BigQuery / Cloud Storage / Pub/Sub / project khác]
    E --> H[Exclusion]
    F --> I[Log views]
    I --> J[Logs Explorer]
    I --> K[Observability Analytics / SQL]
    K --> L[Biểu đồ và custom dashboard]
    K --> M[Linked BigQuery dataset]
~~~

Log Router xử lý log được ghi vào Cloud Logging API. Một **sink** là quy tắc định tuyến có bộ lọc và đích nhận. Sink có thể được cấu hình ở project, folder hoặc organization tùy loại tài nguyên và phạm vi quản trị. Nhờ đó, tổ chức có thể gom nhật ký từ nhiều project về một nơi lưu trữ tập trung, chuyển một nhóm log sang BigQuery hoặc Pub/Sub, hay tách log bảo mật khỏi log ứng dụng thông thường.

Một sink có thể có **exclusion** để bỏ qua những log entry không cần gửi đến đích của sink đó. Exclusion cần được thiết kế thận trọng: nếu loại bỏ audit log hoặc sự kiện quan trọng, đội ngũ có thể mất dữ liệu phục vụ điều tra. Hãy kiểm tra rõ log nào bị loại, ở phạm vi nào và liệu log đó còn được lưu tại một bucket hoặc đích khác hay không.

### Các nguồn log phổ biến

| Nguồn | Ví dụ | Giá trị khi phân tích |
|---|---|---|
| Cloud Run | Request log, container stdout/stderr, lỗi ứng dụng | Theo dõi mã HTTP, revision, lỗi và thời điểm phát hành |
| Compute Engine | System log, ứng dụng, Ops Agent, startup script | Điều tra lỗi VM, tài nguyên máy và dịch vụ chạy trên máy |
| GKE | Container log, node log, Kubernetes events, control-plane audit log | Theo dõi pod, deployment, node và hoạt động quản trị cluster |
| Cloud SQL | Database logs, kết nối, lỗi và audit log được cấu hình | Phát hiện kết nối bất thường, lỗi truy vấn và vấn đề vận hành |
| Cloud Storage | Audit log và sự kiện truy cập được ghi nhận | Điều tra quyền truy cập bucket và thao tác với object |
| Cloud Audit Logs | Admin Activity, Data Access, System Event, Policy Denied | Truy vết thao tác quản trị, truy cập dữ liệu và quyết định chính sách |
| Ứng dụng riêng | JSON log, exception, request ID, trace ID | Kết nối sự kiện nghiệp vụ với request và trace |

Với VM, **Ops Agent** có thể thu thập log hệ điều hành và log ứng dụng theo cấu hình. Với container và dịch vụ managed, nhiều loại log được tích hợp trực tiếp hoặc được thu thập từ stdout/stderr. Ứng dụng riêng có thể ghi log có cấu trúc để Cloud Logging hiểu được các trường như severity, request, trace và payload.

## 3. Cấu trúc của một log entry

Một log entry có thể chứa nhiều trường. Khi phân tích, hãy hiểu ý nghĩa của các trường chính trước khi viết bộ lọc hoặc truy vấn.

| Trường | Ý nghĩa | Cách sử dụng |
|---|---|---|
| `logName` / `log_name` | Tên log và đường dẫn log trong project | Phân biệt log ứng dụng, audit log hoặc log của dịch vụ |
| `timestamp` | Thời điểm sự kiện xảy ra theo nguồn phát sinh | Xây dựng dòng thời gian và lọc theo thời gian |
| `receiveTimestamp` / `receive_timestamp` | Thời điểm Cloud Logging nhận log | Phân tích độ trễ giữa lúc phát sinh và lúc tiếp nhận |
| `severity` | Mức độ của sự kiện | Lọc `WARNING`, `ERROR`, `CRITICAL` và các mức khác |
| `resource` | Loại tài nguyên và nhãn định danh tài nguyên | Nhóm log theo VM, container, project, zone hoặc service |
| `textPayload` / `text_payload` | Nội dung văn bản | Đọc thông báo dạng text |
| `jsonPayload` / `json_payload` | Nội dung JSON có cấu trúc | Trích xuất field như `request_id`, `status`, `user_id` |
| `protoPayload` / `proto_payload` | Payload theo Protocol Buffers, thường gặp trong audit log | Phân tích method, principal và thông tin sự kiện có kiểu |
| `labels` | Nhãn bổ sung do dịch vụ hoặc ứng dụng cung cấp | Phân nhóm theo môi trường, component hoặc thuộc tính tùy chỉnh |
| `httpRequest` / `http_request` | Thông tin request HTTP nếu có | Phân tích method, URL, status và latency |
| `trace`, `spanId` / `span_id` | Định danh trace và span | Liên kết log với distributed trace |
| `insertId` / `insert_id` | Định danh log entry do nguồn cung cấp | Hỗ trợ nhận diện entry trùng trong một số ngữ cảnh |

Tên trường trong cấu trúc API thường dùng camelCase; schema SQL trong Observability Analytics hiển thị các tên dạng snake_case. Ví dụ `jsonPayload` trở thành `json_payload`, `httpRequest` trở thành `http_request`.

Ví dụ một log entry dạng JSON có cấu trúc:

~~~json
{
  "severity": "ERROR",
  "message": "Payment request failed",
  "service": "checkout",
  "environment": "production",
  "request_id": "req-7f31",
  "http_status": 503,
  "trace_id": "projects/demo-project/traces/4bf92f3577b34da6a3ce929d0e0e4736",
  "timestamp": "2026-11-19T07:30:00Z"
}
~~~

Ví dụ này minh họa payload do ứng dụng tạo. Khi ghi log thực tế, cần dùng đúng định dạng mà thư viện hoặc API Cloud Logging hỗ trợ; các trường được đặt trong `jsonPayload` và metadata như severity, timestamp, trace có thể được ánh xạ vào trường cấp cao của `LogEntry`.

### Chọn severity nhất quán

Các mức severity thường dùng gồm `DEFAULT`, `DEBUG`, `INFO`, `NOTICE`, `WARNING`, `ERROR`, `CRITICAL`, `ALERT` và `EMERGENCY`.

- `DEBUG`: thông tin phục vụ gỡ lỗi, thường không cần giữ ở mức chi tiết trong mọi môi trường production.
- `INFO`: sự kiện bình thường có ích cho vận hành.
- `NOTICE`: sự kiện đáng chú ý nhưng chưa phải cảnh báo.
- `WARNING`: tình huống bất thường cần theo dõi.
- `ERROR`: thao tác hoặc request thất bại.
- `CRITICAL`, `ALERT`, `EMERGENCY`: sự cố nghiêm trọng cần phản ứng nhanh theo quy trình của tổ chức.

Không gán mọi log thành `ERROR`. Nếu ứng dụng ghi tất cả sự kiện ở cùng một severity, truy vấn và cảnh báo sẽ khó phân biệt lỗi thực sự với hoạt động bình thường.

## 4. Lưu trữ log bằng log bucket

**Log bucket** là nơi Cloud Logging lưu trữ, lập chỉ mục và cho phép truy vấn log. Bucket có thể thuộc project, billing account, folder hoặc organization theo mô hình tài nguyên được hỗ trợ. Bucket do người dùng tạo được tạo ở cấp project.

Khi tạo một project, billing account, folder hoặc organization, Cloud Logging tự tạo hai bucket hệ thống:

| Bucket | Nội dung điển hình | Retention mặc định |
|---|---|---|
| `_Required` | Admin Activity, System Event và một số audit log bắt buộc khác | 400 ngày, cố định |
| `_Default` | Data Access audit logs, log ứng dụng và log dịch vụ không thuộc `_Required` | 30 ngày, có thể tùy chỉnh |

Bucket `_Required` không thể xóa và không thể thay đổi thời gian lưu giữ. Bucket `_Default` cũng không thể xóa, nhưng có thể điều chỉnh các quy tắc lưu log và retention theo nhu cầu. Khi tổ chức cần lưu dữ liệu lâu hơn, tách log theo nhóm hoặc đáp ứng yêu cầu lưu trữ riêng, có thể tạo user-defined log bucket và định tuyến log bằng sink.

### Những thuộc tính cần quyết định khi tạo bucket

- **Location:** khu vực lưu trữ log. Log bucket là tài nguyên theo vùng. Chọn vùng theo yêu cầu độ trễ, khả dụng, nơi đặt workload và data residency.
- **Retention:** số ngày lưu log. Bucket do người dùng tạo có thể cấu hình từ 1 đến 3650 ngày theo tài liệu hiện hành; xác minh giới hạn và chính sách áp dụng trước khi triển khai.
- **Encryption:** mặc định dùng Google-owned and Google-managed encryption keys; có thể cấu hình CMEK cho bucket đáp ứng điều kiện.
- **Lock:** khóa bucket để ngăn cập nhật hoặc xóa. Việc khóa là không thể đảo ngược và khóa cả retention policy; chỉ thực hiện khi đã phê duyệt chính sách lưu trữ.
- **Log views:** xác định nhóm log mà người dùng được phép xem trong bucket.

Vị trí của bucket không thể thay đổi sau khi tạo. Nếu cần chuyển dữ liệu sang vùng khác, tạo bucket mới ở vùng đích, điều chỉnh sink để định tuyến log phù hợp và xử lý bucket cũ theo chính sách lưu giữ. Không xem `global` là lựa chọn có thêm khả năng chịu lỗi: tài liệu Cloud Logging nêu rõ bucket `global` hoặc multi-region không có thêm bảo đảm dự phòng so với bucket ở một vùng đơn như `us-west1`.

Log Router xử lý log ở vùng mà log được tiếp nhận. Sink có thể chuyển log sang một đích khác, vì vậy việc chọn vùng của bucket chưa đủ để chứng minh toàn bộ luồng dữ liệu luôn nằm trong một khu vực. Khi có yêu cầu data residency, cần rà soát cả bucket, sink, đích nhận và dịch vụ phân tích. Bucket ở vùng `global` không hỗ trợ CMEK.

## 5. Logs Explorer và Log Analytics khác nhau thế nào?

Cloud Logging có hai giao diện truy vấn chính. Chúng phục vụ những công việc khác nhau và sử dụng ngôn ngữ truy vấn khác nhau.

| Tiêu chí | Logs Explorer | Log Analytics / Observability Analytics |
|---|---|---|
| Mục tiêu | Tìm kiếm, xem và điều tra log entry | Phân tích, tổng hợp, nhận diện xu hướng và kết hợp dữ liệu |
| Ngôn ngữ | Logging query language (LQL) | SQL dựa trên GoogleSQL, có một số giới hạn |
| Kết quả | Danh sách log entry, histogram và chi tiết từng entry | Bảng, phép tổng hợp, biểu đồ và kết quả SQL |
| Thao tác thường dùng | Lọc theo resource, log name, severity, timestamp | `SELECT`, `WHERE`, `GROUP BY`, `JOIN`, hàm thời gian và JSON |
| Tình huống phù hợp | Tìm một request lỗi, kiểm tra một lần thay đổi IAM | Đếm lỗi theo giờ, so sánh dịch vụ, tính latency trung bình |
| Điều kiện | Có quyền xem log và phạm vi dữ liệu phù hợp | Log bucket cần được nâng cấp để dùng Observability Analytics |

### Logs Explorer: tìm đúng sự kiện

Logging query language là biểu thức Boolean dùng để chọn log entry trong phạm vi tài nguyên hoặc log view đã chọn. Ví dụ:

~~~text
resource.type="cloud_run_revision"
severity>=ERROR
timestamp >= "2026-11-19T06:00:00Z"
logName:"run.googleapis.com"
~~~

Bộ lọc trên tìm log của Cloud Run revision có severity từ ERROR trở lên, trong khoảng thời gian xác định và có log name chứa chuỗi chỉ định. Khi điều tra, hãy bắt đầu bằng phạm vi thời gian hẹp, resource type và severity; sau đó mở log entry để xem payload, trace và metadata.

Logs Explorer phù hợp khi cần trả lời câu hỏi về một sự kiện cụ thể. Ví dụ: request nào trả về HTTP 503, service account nào thực hiện thao tác, hoặc VM nào ghi lỗi khởi động.

### Log Analytics: tìm xu hướng bằng SQL

Observability Analytics cung cấp SQL editor và Query Builder. Người dùng có thể truy vấn log view hoặc analytics view, hiển thị kết quả dạng bảng, tạo biểu đồ và lưu biểu đồ vào custom dashboard.

Để truy vấn log bucket bằng SQL, bucket cần được nâng cấp để dùng Observability Analytics. Sau khi nâng cấp, người dùng vẫn có thể tiếp tục xem log bằng Logs Explorer.

SQL đặc biệt hữu ích khi cần:
- Đếm log theo severity, resource type hoặc khoảng thời gian.
- Tính số lỗi theo giờ hoặc theo revision.
- Trích xuất field trong JSON payload.
- Tính latency trung bình theo URL hoặc service.
- Kết hợp log với trace để điều tra request qua nhiều thành phần.
- Chuẩn hóa dữ liệu bằng analytics view để tái sử dụng truy vấn.

Không dùng một giao diện thay cho mọi mục tiêu. Nếu đang tìm một log entry cụ thể, Logs Explorer thường giúp điều tra nhanh hơn. Nếu cần tổng hợp hàng nghìn sự kiện thành xu hướng, SQL phù hợp hơn.

## 6. Bật Log Analytics cho log bucket

Trên giao diện hiện hành, thao tác nâng cấp bucket được thực hiện từ trang **Logs Storage**.

1. Mở Google Cloud Console và chọn đúng project.
2. Vào **Logging → Logs Storage**.
3. Tìm bucket cần phân tích và kiểm tra cột **Observability Analytics available**.
4. Nếu trạng thái hiển thị **Upgrade**, chọn **Upgrade** và xác nhận.
5. Chờ thao tác hoàn tất; quá trình nâng cấp có thể mất vài phút.
6. Mở **Observability Analytics**, chọn log view thuộc bucket vừa nâng cấp và bắt đầu truy vấn SQL.

Một số điều kiện cần kiểm tra trước khi nâng cấp:

- Bucket phải được tạo ở cấp project.
- Bucket do người dùng tạo phải ở trạng thái unlocked; `_Required` có ngoại lệ riêng.
- Bucket không có thao tác cập nhật đang chờ.
- Nếu project nằm trong VPC Service Controls perimeter, cần kiểm tra các dịch vụ Logging và Cloud KMS có bị perimeter hạn chế hay không, đặc biệt khi bucket sử dụng CMEK.
- Cần xác minh tính năng và giới hạn đang áp dụng cho môi trường cụ thể.

**Nâng cấp là thao tác không thể hoàn tác.** Sau khi bật Observability Analytics cho bucket, bạn không thể tắt lại tính năng này hoặc đưa bucket về cấu hình trước đó. Vì vậy, hãy xác định mục đích phân tích, quyền truy cập, khu vực lưu trữ và yêu cầu tuân thủ trước khi nâng cấp. Tài liệu hiện hành nêu rằng log entry mới đến sau khi nâng cấp sẽ có thể được phân tích bằng Observability Analytics; hãy kiểm tra khả năng truy vấn dữ liệu lịch sử của bucket trong môi trường thực tế trước khi lập kế hoạch dựa trên toàn bộ lịch sử.

### Nâng cấp bằng gcloud

Với bucket đã tồn tại, có thể dùng lệnh:

~~~bash
gcloud logging buckets update BUCKET_ID \
  --location=LOCATION \
  --enable-analytics \
  --async
~~~

Thay `BUCKET_ID` và `LOCATION` bằng giá trị thực tế. Cờ `--async` trả về một long-running operation. Theo dõi operation đến khi hoàn tất và kiểm tra kết quả thành công hoặc lỗi. Khi nâng cấp, không gộp thay đổi retention hoặc thuộc tính bucket khác vào cùng lệnh cập nhật.

## 7. Truy vấn log bằng SQL

### Cấu trúc nguồn dữ liệu

Khi truy vấn một log view trong Observability Analytics, đường dẫn nguồn có dạng:

~~~sql
FROM `PROJECT_ID`.`LOCATION`.`BUCKET_ID`.`LOG_VIEW_ID`
~~~

Mỗi thành phần có ý nghĩa:

- `PROJECT_ID`: ID của project chứa bucket.
- `LOCATION`: vùng của log bucket.
- `BUCKET_ID`: tên bucket.
- `LOG_VIEW_ID`: ID của log view trong bucket.

Các tên trên là placeholder; thay bằng tài nguyên thực tế. Nếu project ID có dấu chấm, dùng cách trích dẫn identifier theo hướng dẫn SQL của Google Cloud. Trong Observability Analytics, schema của log view dựa trên cấu trúc `LogEntry`.

### Ví dụ 1: Đếm log lỗi theo giờ và loại tài nguyên

~~~sql
SELECT
  TIMESTAMP_TRUNC(timestamp, HOUR) AS hour,
  resource.type AS resource_type,
  COUNT(*) AS error_count
FROM
  `PROJECT_ID`.`LOCATION`.`BUCKET_ID`.`LOG_VIEW_ID`
WHERE
  timestamp >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 24 HOUR)
  AND severity IN ('ERROR', 'CRITICAL')
GROUP BY
  hour,
  resource_type
ORDER BY
  hour DESC
LIMIT 500
~~~

Truy vấn này tổng hợp số log lỗi theo giờ và loại tài nguyên trong 24 giờ gần nhất. Nhóm vận hành có thể dùng kết quả để xác định khoảng thời gian mà lỗi tăng mạnh và dịch vụ cần điều tra.

### Ví dụ 2: Trích xuất trạng thái từ JSON payload

Giả sử ứng dụng ghi `status` và `request_id` vào `jsonPayload`:

~~~sql
SELECT
  timestamp,
  severity,
  JSON_VALUE(json_payload.request_id) AS request_id,
  JSON_VALUE(json_payload.status) AS status
FROM
  `PROJECT_ID`.`LOCATION`.`BUCKET_ID`.`LOG_VIEW_ID`
WHERE
  json_payload IS NOT NULL
  AND JSON_VALUE(json_payload.status) = 'FAILED'
ORDER BY
  timestamp DESC
LIMIT 100
~~~

`JSON_VALUE` lấy giá trị scalar từ một field JSON. Hãy kiểm tra schema trước khi viết truy vấn vì payload có thể thay đổi theo loại log. `json_payload.status IS NOT NULL` kiểm tra field tồn tại; `JSON_VALUE(json_payload.status) IS NOT NULL` kiểm tra giá trị scalar được trích xuất không phải NULL. Hai điều kiện này không luôn tương đương.

### Ví dụ 3: Tính latency trung bình theo URL

~~~sql
SELECT
  http_request.request_url AS request_url,
  AVG(http_request.latency.seconds) AS average_latency_seconds,
  COUNT(*) AS request_count
FROM
  `PROJECT_ID`.`LOCATION`.`BUCKET_ID`.`LOG_VIEW_ID`
WHERE
  http_request IS NOT NULL
  AND http_request.request_method = 'GET'
GROUP BY
  request_url
ORDER BY
  average_latency_seconds DESC
LIMIT 20
~~~

Truy vấn này nhóm request GET theo URL và xếp các URL có latency trung bình cao nhất lên đầu. Kết quả giúp xác định endpoint cần kiểm tra thêm. Khi cần phân tích sâu, kết hợp với trace, log ứng dụng và dữ liệu của phiên bản dịch vụ tại thời điểm request.

### Ví dụ 4: Nhóm log theo severity

~~~sql
SELECT
  severity,
  COUNT(*) AS entry_count
FROM
  `PROJECT_ID`.`LOCATION`.`BUCKET_ID`.`LOG_VIEW_ID`
WHERE
  severity IS NOT NULL
GROUP BY
  severity
ORDER BY
  entry_count DESC
LIMIT 100
~~~

Truy vấn này cung cấp phân bố log theo severity. Nếu số lượng `ERROR` hoặc `CRITICAL` tăng đột ngột, cần lọc tiếp theo resource type, log ID và thời gian để tìm nguyên nhân.

### Lưu ý khi dùng SQL

- Observability Analytics hỗ trợ các hàm GoogleSQL với một số ngoại lệ. DDL, DML, JavaScript UDF, BigQuery ML functions và SQL variables không được hỗ trợ trong SQL editor của trang này.
- Dùng time-range selector để chọn khoảng thời gian. Nếu truy vấn có điều kiện `timestamp` trong `WHERE`, thiết lập time-range selector sẽ không được sử dụng.
- Trường có kiểu JSON cần được truy cập qua hàm JSON phù hợp như `JSON_VALUE`.
- Trường dạng RECORD như `http_request` cần kiểm tra subfield; ví dụ `http_request.request_method IS NOT NULL`.
- Khi dùng `GROUP BY`, mọi biểu thức trong `SELECT` phải nằm trong nhóm hoặc được tổng hợp bằng hàm như `COUNT`, `AVG`, `MAX`.
- Chỉ lấy các cột cần thiết và giới hạn khoảng thời gian để kết quả dễ đọc và giảm lượng dữ liệu phải xử lý.
- Không mặc định rằng mỗi log entry là một request duy nhất. Một request có thể tạo nhiều log entry ở các thành phần khác nhau.

Observability Analytics không tự loại bỏ log entry trùng lặp trước khi chạy truy vấn. Logs Explorer có hành vi loại bỏ một số entry trùng dựa trên `log_name`, `timestamp` và `insert_id`. Nếu phép đếm yêu cầu loại trùng, hãy thiết kế logic kiểm tra theo các định danh phù hợp và cân nhắc chi phí hiệu năng; truy vấn loại trùng thường chậm hơn.

## 8. Analytics views: chuẩn hóa truy vấn để tái sử dụng

**Analytics view** là một tài nguyên được tạo từ câu SQL để định nghĩa schema tùy chỉnh trên dữ liệu quan sát. Thay vì lặp lại nhiều phép chuyển đổi trong từng truy vấn, nhóm có thể tạo một view chứa các trường chuẩn hóa như service name, environment, request ID, severity và latency.

Ví dụ, log gốc có thể chứa nhiều kiểu payload khác nhau. Một analytics view có thể trích xuất các trường chung để nhóm ứng dụng dùng lại:

~~~sql
SELECT
  timestamp,
  severity,
  resource.type AS resource_type,
  JSON_VALUE(json_payload.service) AS service_name,
  JSON_VALUE(json_payload.environment) AS environment,
  JSON_VALUE(json_payload.request_id) AS request_id,
  JSON_VALUE(json_payload.message) AS message
FROM
  `PROJECT_ID`.`LOCATION`.`BUCKET_ID`.`LOG_VIEW_ID`
WHERE
  json_payload IS NOT NULL
~~~

Sau khi lưu analytics view, có thể dùng view này trong mệnh đề `FROM` của truy vấn khác. Tên analytics view và schema do người tạo xác định; thay đổi query của view có thể ảnh hưởng các truy vấn đang dùng view đó. Vì vậy, cần có chủ sở hữu, mô tả, quy ước tên và quy trình review.

Quy trình tạo view trên Console:

1. Mở **Observability Analytics**.
2. Chọn log view làm nguồn.
3. Chọn SQL editor và chạy thử truy vấn.
4. Kiểm tra kết quả, tên cột và kiểu dữ liệu.
5. Chọn **Save → Save as analytics view**.
6. Đặt tên và mô tả, sau đó lưu.

Analytics views hiện được tài liệu Google Cloud đánh dấu là **Public Preview**. Trước khi dùng trong quy trình vận hành quan trọng, hãy kiểm tra trạng thái phát hành và điều khoản áp dụng tại thời điểm triển khai. Không thể tạo linked BigQuery dataset trực tiếp cho analytics view.

## 9. Kết hợp Log Analytics với BigQuery

Observability Analytics có thể truy vấn log và trace ngay trong giao diện Cloud Logging. Bạn **không cần** linked BigQuery dataset nếu mục tiêu chỉ là truy vấn log, phân tích log/trace, lưu truy vấn hoặc tạo biểu đồ trên dashboard.

Một **linked BigQuery dataset** cần thiết khi muốn:

- JOIN log entry với các dataset nghiệp vụ khác trong BigQuery.
- Truy vấn log từ BigQuery Studio, Looker Studio hoặc công cụ tương thích.
- Dùng BigQuery engine và các khả năng xử lý của BigQuery.
- Tạo SQL-based alerting policy theo kết quả truy vấn.

Linked dataset là một con trỏ chỉ đọc đến log bucket. Cloud Logging tiếp tục lưu log; BigQuery có thể đọc dữ liệu qua dataset liên kết mà không cần tạo bản sao dữ liệu riêng trong một bảng BigQuery thông thường.

### Quyền truy cập và ranh giới bảo mật

Khi truy vấn linked dataset, quyền được kiểm tra qua lớp quyền BigQuery thay vì lớp quyền Cloud Logging. Điều đó có nghĩa là việc cấp quyền truy cập dataset sẽ mở rộng ranh giới bảo mật của log sang BigQuery.

Một principal được cấp quyền vào linked dataset có thể truy vấn tất cả virtual view trong dataset đó; không thể giới hạn principal chỉ vào một virtual view cụ thể bên trong linked dataset. Vì vậy:

- Chỉ tạo linked dataset khi có nhu cầu phân tích thực sự.
- Rà soát quyền BigQuery dataset và project trước khi cấp truy cập.
- Không đưa log chứa secret, token hoặc dữ liệu cá nhân không cần thiết vào nhóm người dùng rộng.
- Dùng log view để giới hạn dữ liệu có thể truy vấn trong Cloud Logging, đồng thời hiểu rằng quyền dataset BigQuery có phạm vi riêng.
- Kiểm tra audit log và quy trình cấp quyền sau khi tạo liên kết.

Một log bucket có thể được liên kết với tối đa một BigQuery dataset. Để tạo liên kết, bucket cần được nâng cấp để dùng Observability Analytics và người thực hiện cần quyền cấu hình Logging phù hợp, thường là `roles/logging.configWriter`.

## 10. Tạo cảnh báo từ truy vấn SQL

SQL-based alerting policy chạy truy vấn định kỳ trên log data và gửi thông báo khi kết quả thỏa điều kiện. Ví dụ, nhóm có thể đặt cảnh báo khi tỷ lệ log request có severity `ERROR` đạt một ngưỡng trong khoảng thời gian xác định.

Các chính sách cảnh báo SQL tạo từ Observability Analytics chạy trên BigQuery engine. Vì vậy, log view được truy vấn phải có linked BigQuery dataset. Loại cảnh báo này chỉ truy vấn **log view**, không truy vấn analytics view.

Trước khi tạo cảnh báo, xác định:

1. **Tín hiệu:** số lượng lỗi, tỷ lệ lỗi, latency hoặc một điều kiện nghiệp vụ.
2. **Cửa sổ thời gian:** khoảng thời gian mà truy vấn đánh giá.
3. **Ngưỡng:** mức độ vượt ngưỡng đủ để cần hành động.
4. **Tần suất:** chu kỳ đánh giá và thời gian duy trì điều kiện.
5. **Người nhận:** nhóm trực tiếp chịu trách nhiệm xử lý.
6. **Runbook:** bước kiểm tra đầu tiên và cách xác minh cảnh báo đã được giải quyết.

Không cảnh báo cho mọi log `ERROR` nếu hệ thống có lỗi đã biết hoặc lỗi có thể tự phục hồi. Ngưỡng, thời gian duy trì và nội dung thông báo cần phản ánh mức độ ảnh hưởng đến người dùng. Cảnh báo tốt phải chỉ ra dịch vụ, khoảng thời gian, truy vấn liên quan và hướng điều tra ban đầu.

## 11. IAM và phân quyền truy vấn log

Log thường chứa dữ liệu nhạy cảm như email, IP, ID người dùng, thông tin request hoặc metadata hạ tầng. Phân quyền phải được thiết kế cùng với lưu trữ và phân tích.

Một số predefined role thường gặp:

| Role | Mục đích |
|---|---|
| `roles/logging.viewer` | Xem log và truy vấn các bucket `_Required`, `_Default` theo phạm vi được cấp |
| `roles/logging.viewAccessor` | Truy cập log views trong project; có thể giới hạn view bằng IAM condition hoặc policy của log view |
| `roles/observability.analyticsUser` | Sử dụng và truy vấn analytics views theo quyền được cấp |
| `roles/logging.configWriter` | Cấu hình Logging, ví dụ tạo linked BigQuery dataset khi có đủ quyền cần thiết |
| BigQuery dataset roles | Truy vấn linked dataset theo quyền BigQuery, độc lập với quyền Cloud Logging |

Người chỉ cần điều tra log không nên được cấp quyền sửa sink, bucket, retention hoặc IAM policy. Tách vai trò người xem, người cấu hình và người quản trị dữ liệu. Với log view, cấp quyền theo nhóm người dùng và phạm vi log cần thiết. Khi tạo linked BigQuery dataset, phải đánh giá lại ai có thể truy vấn dữ liệu thông qua BigQuery.

## 12. Phân tích log trong một tình huống thực tế

Một dịch vụ checkout chạy trên Cloud Run bắt đầu trả về nhiều HTTP 5xx sau khi phát hành revision mới. Người dùng báo thanh toán thất bại, nhưng dịch vụ vẫn có lúc hoạt động bình thường.

### Bước 1: Xác định thời điểm và phạm vi

Mở Logs Explorer, chọn project chứa dịch vụ, đặt time range từ trước thời điểm phát hành đến hiện tại và lọc resource type `cloud_run_revision`. Tìm request log có HTTP status từ 500 trở lên. So sánh thời điểm tăng lỗi với thời điểm triển khai revision.

### Bước 2: Đếm request lỗi theo phút

Trong Observability Analytics, chọn log view có request log và chạy truy vấn:

~~~sql
SELECT
  TIMESTAMP_TRUNC(timestamp, MINUTE) AS minute,
  JSON_VALUE(resource.labels.service_name) AS service_name,
  COUNT(*) AS failed_requests
FROM
  `PROJECT_ID`.`LOCATION`.`BUCKET_ID`.`LOG_VIEW_ID`
WHERE
  resource.type = 'cloud_run_revision'
  AND http_request.status >= 500
  AND timestamp >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 2 HOUR)
GROUP BY
  minute,
  service_name
ORDER BY
  minute DESC
LIMIT 120
~~~

Kết quả cho biết số request lỗi theo phút và service. Nếu một khoảng thời gian có số lỗi tăng đột ngột, mở rộng điều tra vào revision, URL và log ứng dụng tương ứng. Kiểm tra schema của `resource.labels.service_name` trước khi dùng truy vấn; nếu field không có trong log view, thay bằng field đúng theo schema thực tế.

### Bước 3: Đối chiếu log ứng dụng và trace

Từ request log, lấy `trace` và `span_id` nếu có. Mở trace tương ứng để xem request đi qua Cloud Run, API hoặc dịch vụ phụ trợ nào. Khi kết hợp nhiều bảng log/trace, dùng cả trace ID và span ID khi cần xác định span; không JOIN chỉ bằng span ID vì span ID không nhất thiết duy nhất trên toàn hệ thống.

Tìm log ứng dụng theo `request_id` để xem exception hoặc mã lỗi từ dịch vụ phụ thuộc. Nếu lỗi bắt nguồn từ database, đối chiếu thời điểm với log kết nối và trạng thái tài nguyên Cloud SQL.

### Bước 4: Khắc phục và xác minh

Nếu lỗi bắt đầu sau revision mới, nhóm phát triển kiểm tra thay đổi mã nguồn, cấu hình môi trường, quyền service account và kết nối dịch vụ phụ trợ. Sau khi rollback hoặc triển khai bản sửa, chạy lại truy vấn với cùng time window để so sánh tỷ lệ lỗi. Lưu truy vấn và biểu đồ vào dashboard để theo dõi sau phát hành.

**Kết quả mong đợi:** đội ngũ xác định được khoảng thời gian lỗi tăng, dịch vụ/revision liên quan, request và trace cần điều tra; sau khi sửa, dữ liệu mới cho thấy tỷ lệ lỗi trở về mức bình thường.

## 13. Thực hành tốt khi thiết kế hệ thống log

### Ghi log có cấu trúc

- Ưu tiên JSON payload cho ứng dụng để có thể lọc và tổng hợp theo field.
- Dùng tên field nhất quán giữa các service, ví dụ `service`, `environment`, `request_id`, `trace_id`, `user_action`.
- Đặt severity đúng ngữ nghĩa và tránh ghi một sự kiện ở nhiều mức không cần thiết.
- Ghi `trace` và request ID để kết nối log với trace và các service khác.
- Không ghi password, access token, private key, session cookie hoặc dữ liệu cá nhân không cần thiết.

### Tổ chức lưu trữ và định tuyến

- Chọn bucket theo mục đích, quyền truy cập, retention và data residency.
- Dùng sink cấp organization hoặc folder khi cần tập trung log nhiều project.
- Tạo log view để giới hạn dữ liệu theo nhóm người dùng.
- Kiểm tra exclusion để tránh loại bỏ audit log hoặc log phục vụ điều tra.
- Không khóa bucket khi chưa xác nhận retention, sink và quy trình lưu trữ; lock là thao tác không thể đảo ngược.
- Kiểm tra vị trí đích của sink để bảo đảm phù hợp với yêu cầu khu vực lưu trữ.

### Viết truy vấn hiệu quả

- Bắt đầu bằng khoảng thời gian nhỏ và resource type cụ thể.
- Chỉ chọn field cần thiết thay vì lấy toàn bộ payload.
- Dùng `WHERE` để lọc trước khi tổng hợp.
- Dùng `TIMESTAMP_TRUNC` để gom dữ liệu theo phút, giờ hoặc ngày.
- Dùng `JSON_VALUE` khi truy cập giá trị trong JSON.
- Dùng `LIMIT` để giới hạn số dòng kết quả.
- Dùng `CONTAINS_SUBSTR` cho tìm kiếm chuỗi con khi phù hợp; regex extraction phù hợp hơn khi cần trích xuất mẫu phức tạp.
- Kiểm tra trùng lặp nếu đang đếm sự kiện hoặc request.

### Kiểm soát chi phí

Nâng cấp bucket và chạy SQL từ trang Observability Analytics không phát sinh phí riêng cho thao tác nâng cấp hoặc truy vấn Log Analytics theo mô hình giá Cloud Logging được công bố. Tuy nhiên, toàn bộ pipeline log vẫn có thể tạo chi phí:

- Phí tiếp nhận hoặc lưu trữ log theo loại log và mức sử dụng.
- Phí retention khi lưu log lâu hơn thời gian mặc định.
- Chi phí của dịch vụ đích khi định tuyến sang BigQuery, Cloud Storage hoặc Pub/Sub.
- Chi phí BigQuery khi dùng linked dataset và truy vấn bằng BigQuery engine.
- Chi phí log mạng do các dịch vụ tạo ra, ví dụ VPC Flow Logs, Firewall Rules Logging hoặc Cloud NAT logs.

Giảm chi phí bằng cách chọn đúng log cần lưu, cấu hình retention theo yêu cầu, dùng exclusion có kiểm soát và tránh tạo log lặp hoặc payload quá lớn. Không cắt giảm audit log bắt buộc chỉ để giảm chi phí nếu điều đó làm mất khả năng điều tra hoặc vi phạm yêu cầu tuân thủ.

## 14. Xử lý các lỗi thường gặp

| Hiện tượng | Nguyên nhân cần kiểm tra | Hướng xử lý |
|---|---|---|
| Logs Explorer không có kết quả | Sai project, resource, time range, log view hoặc filter | Mở rộng time range, bỏ bớt điều kiện, xác nhận nguồn log và scope |
| Logs Explorer có log nhưng SQL không có dữ liệu | Bucket chưa được nâng cấp, chọn nhầm log view hoặc quyền chưa đủ | Kiểm tra trạng thái Observability Analytics, bucket và IAM |
| SQL báo không tìm thấy field | Schema khác với dự kiến hoặc payload có kiểu JSON | Mở Schema pane, dùng đúng tên field và `JSON_VALUE` |
| SQL trả kết quả trùng | Observability Analytics không tự loại bỏ log entry trùng | Kiểm tra `log_name`, `timestamp`, `insert_id` và chỉ loại trùng khi truy vấn yêu cầu |
| Không nâng cấp được bucket | Bucket không ở cấp project, bị khóa, có pending update hoặc VPC-SC hạn chế API | Kiểm tra điều kiện nâng cấp, quyền và cấu hình perimeter |
| Không truy vấn được linked dataset | Thiếu quyền BigQuery hoặc dataset link chưa sẵn sàng | Kiểm tra quyền dataset, liên kết bucket và quyền tạo liên kết |
| SQL alert không tạo được | Log view chưa có linked dataset hoặc đang truy vấn analytics view | Tạo linked dataset và dùng log view trong truy vấn cảnh báo |
| Kết quả phân tích không khớp Logs Explorer | Khác ngôn ngữ truy vấn, khác scope hoặc cách xử lý duplicate | Đối chiếu cùng bucket/view, thời gian và điều kiện; kiểm tra logic loại trùng |

Khi nâng cấp bucket bằng gcloud, thao tác có thể trả về long-running operation. Hãy kiểm tra trạng thái operation thay vì chạy lệnh nâng cấp lặp lại. Nếu operation lỗi, đọc thông tin lỗi và giải quyết nguyên nhân trước khi thử lại.

## 15. Những giới hạn cần ghi nhớ

- Logs Explorer và Observability Analytics sử dụng ngôn ngữ truy vấn khác nhau; không thể sao chép nguyên một bộ lọc LQL vào SQL mà không chuyển đổi.
- Chỉ bucket được nâng cấp mới có thể được truy vấn bằng Observability Analytics. Việc nâng cấp không thể hoàn tác.
- Analytics views hiện ở giai đoạn Public Preview theo tài liệu được tham chiếu; kiểm tra điều khoản và trạng thái phát hành trước khi phụ thuộc vào tính năng trong production.
- Observability Analytics không tự khử trùng log entry; phép đếm có thể khác Logs Explorer.
- Linked BigQuery dataset mở rộng quyền truy cập dữ liệu sang lớp BigQuery; cần kiểm soát quyền dataset.
- SQL-based alerting policy yêu cầu linked BigQuery dataset và chỉ truy vấn log views.
- Bucket location không thể thay đổi sau khi tạo; cần thiết kế vùng lưu trữ từ đầu.
- Không có log hoặc không thấy finding trong truy vấn không chứng minh hệ thống không có sự cố. Có thể nguồn log chưa được bật, sink đã loại log, retention đã hết hoặc người dùng không có quyền xem.
- Log Analytics hỗ trợ điều tra và phân tích; nó không tự sửa ứng dụng, cấu hình IAM hoặc tài nguyên cloud.

## 16. Câu hỏi tự kiểm tra

1. Khi nào nên dùng Logs Explorer và khi nào nên dùng Observability Analytics?
2. Vì sao cần nâng cấp log bucket trước khi truy vấn bằng SQL?
3. Một log entry có `timestamp` và `receive_timestamp`. Hai trường này giúp điều tra độ trễ tiếp nhận như thế nào?
4. Khi một field nằm trong JSON payload, vì sao cần kiểm tra schema và dùng `JSON_VALUE`?
5. Vì sao nâng cấp bucket cần được phê duyệt trước khi thực hiện?
6. Khi nào cần tạo linked BigQuery dataset? Việc này làm thay đổi ranh giới bảo mật như thế nào?
7. Vì sao SQL-based alerting policy không thể truy vấn analytics view?
8. Một truy vấn Observability Analytics trả nhiều dòng hơn Logs Explorer. Bạn sẽ kiểm tra những yếu tố nào?
9. Khi tổ chức có yêu cầu data residency, cần kiểm tra những thành phần nào ngoài location của log bucket?
10. Làm thế nào để giảm chi phí log mà vẫn giữ đủ dữ liệu cho vận hành và điều tra?

## Tài liệu tham khảo

- [Cloud Logging overview](https://docs.cloud.google.com/logging/docs/overview)
- [Analyze logs using Logs Explorer and Observability Analytics](https://docs.cloud.google.com/logging/docs/log-analytics)
- [Query and analyze logs with Observability Analytics](https://docs.cloud.google.com/logging/docs/analyze/query-and-view)
- [Sample SQL queries](https://docs.cloud.google.com/logging/docs/analyze/examples)
- [Configure log buckets](https://docs.cloud.google.com/logging/docs/buckets)
- [Store log entries](https://docs.cloud.google.com/logging/docs/store-log-entries)
- [Cloud Logging locations and regionality](https://docs.cloud.google.com/logging/docs/region-support)
- [Create a linked BigQuery dataset on a log bucket](https://docs.cloud.google.com/logging/docs/analyze/query-linked-dataset)
- [Monitor SQL query results with an alerting policy](https://docs.cloud.google.com/logging/docs/analyze/sql-in-alerting)
- [Create, query, and manage analytics views](https://docs.cloud.google.com/logging/docs/analyze/create-and-manage-analytics-views)

