# Error Reporting và tổng hợp lỗi ứng dụng

Khi một ứng dụng chạy trên Google Cloud gặp exception, lỗi có thể xuất hiện trong log của Cloud Run, GKE, Compute Engine hoặc một dịch vụ khác. Nếu chỉ đọc từng dòng log riêng lẻ, đội vận hành khó biết lỗi nào lặp lại, lỗi nào mới xuất hiện và lỗi nào cần xử lý trước. **Error Reporting** giải quyết vấn đề này bằng cách nhận diện các error event và nhóm chúng thành error group theo những dấu hiệu gần với nguyên nhân gốc.

Trong module **CLOUD_PROVIDERS_GCP**, Error Reporting là một phần của năng lực quan sát và vận hành các dịch vụ cloud. Công cụ giúp đội phát triển và SRE nhận biết lỗi ứng dụng, theo dõi xu hướng tái diễn, liên kết lỗi với log và thông báo cho người phụ trách. Error Reporting hoạt động cùng Cloud Logging và Cloud Monitoring; mỗi dịch vụ cung cấp một góc nhìn khác nhau về tình trạng hệ thống.

Sau bài học, bạn có thể:

- Phân biệt error event, error group và error group stats.
- Chọn cách thu thập lỗi phù hợp với môi trường triển khai.
- Định dạng log để Error Reporting nhận diện exception và stack trace.
- Giải thích cách Error Reporting gom nhóm và ước lượng số lần xảy ra.
- Tổ chức quy trình xem xét, phân công, xử lý và theo dõi lỗi tái diễn.
- Cấu hình quyền truy cập, thông báo và kiểm tra các giới hạn khi dùng nhiều project.

## 1. Error Reporting trong kiến trúc Cloud Observability

Error Reporting là dịch vụ tổng hợp và hiển thị lỗi ứng dụng trong các workload cloud. Dữ liệu có thể đi vào theo hai đường:

1. **Phân tích log**: ứng dụng ghi exception hoặc stack trace vào Cloud Logging. Error Reporting quét những log entry phù hợp để suy ra error event.
2. **Gửi trực tiếp**: ứng dụng hoặc thư viện client gọi Error Reporting API để báo cáo error event.

Mô hình dữ liệu gồm ba thành phần:

| Thành phần | Ý nghĩa | Ví dụ |
|---|---|---|
| Error event | Một lần lỗi xảy ra, gồm thời điểm, ngữ cảnh thực thi và thông điệp lỗi | Một request checkout ném `NullPointerException` |
| Error group | Nhóm các event có dấu hiệu cùng nguyên nhân | Các lần `NullPointerException` tại cùng đường gọi trong `CartService` |
| Error group stats | Thống kê của nhóm lỗi theo thời gian | Thời điểm đầu/cuối, số lần xảy ra, số người dùng bị ảnh hưởng |

Luồng xử lý khái quát:

~~~mermaid
flowchart TD
    A["Ứng dụng trên Cloud Run, GKE, Compute Engine..."] --> B{"Cách gửi lỗi"}
    B --> C["Ghi exception / stack trace"]
    B --> D["Client library hoặc Error Reporting API"]
    C --> E["Cloud Logging"]
    D --> E
    E --> F["Error Reporting phân tích error event"]
    F --> G["Nhóm theo dấu hiệu nguyên nhân"]
    G --> H["Error Reporting: xem, lọc, triage"]
    H --> I["Liên kết issue và theo dõi sửa lỗi"]
    H --> J["Cloud Monitoring notification channels"]
    E --> K["Logs Explorer: điều tra từng log entry"]
~~~

Error Reporting không thay thế Cloud Logging hoặc Cloud Monitoring:

- **Error Reporting** giúp trả lời: lỗi ứng dụng nào đang lặp lại, nhóm nào mới xuất hiện, nhóm nào đã xử lý nhưng tái diễn?
- **Cloud Logging** lưu và truy vấn log entry chi tiết, gồm request, trace, payload và thông tin vận hành.
- **Cloud Monitoring** theo dõi metric, uptime, SLO và alerting policy. Có thể cảnh báo khi tỷ lệ lỗi, latency hoặc một metric vượt ngưỡng.

Một error group có thể giúp tìm ra vấn đề, còn log và trace cung cấp ngữ cảnh để xác định nguyên nhân. Với ứng dụng Android và iOS, Google khuyến nghị dùng Firebase Crashlytics để theo dõi crash phía thiết bị.

## 2. Thu thập error event

### 2.1. Thu thập tự động qua Cloud Logging

Đây thường là lựa chọn đơn giản nhất nếu môi trường chạy đã gửi log về Cloud Logging:

- Cloud Run tự gửi exception và stack trace được ghi ra `stdout` hoặc `stderr` vào Cloud Logging. Error Reporting nhận diện các stack trace phù hợp.
- Cloud Run functions ghi unhandled exception vào Cloud Logging; Error Reporting có thể nhận diện stack trace từ các log entry này.
- Với GKE và Compute Engine, ứng dụng cần ghi log theo định dạng được hỗ trợ và môi trường phải chuyển log vào Cloud Logging, chẳng hạn thông qua logging agent phù hợp hoặc tích hợp sẵn của nền tảng.
- App Engine có tích hợp thu thập riêng theo từng môi trường standard và flexible.

Không nên giả định mọi dòng log có chữ `ERROR` đều tự trở thành error event. Error Reporting cần stack trace theo định dạng ngôn ngữ được hỗ trợ hoặc một payload được định dạng như `ReportedErrorEvent`.

### 2.2. Instrument ứng dụng bằng client library

Client library hữu ích khi:

- Ứng dụng bắt exception và xử lý nó trước khi runtime ghi stack trace.
- Bạn cần bổ sung service name, version hoặc thông tin request.
- Log hiện tại không có định dạng mà Error Reporting có thể nhận diện.
- Bạn muốn chủ động gửi error event từ một thành phần dùng chung.

Google Cloud cung cấp hướng dẫn và thư viện theo ngôn ngữ như Java, Go, Node.js, Python, .NET, PHP và Ruby. Hãy dùng thư viện tương ứng với runtime và cấu hình xác thực bằng service account hoặc Application Default Credentials. Không nhúng service account key vào source code hay image container.

### 2.3. Gửi trực tiếp bằng Error Reporting API

Ứng dụng có thể gọi phương thức `report` của Error Reporting API và gửi một đối tượng `ReportedErrorEvent`. Cách này phù hợp khi ứng dụng cần kiểm soát việc tạo event hoặc khi không thể dựa vào log tự động.

Bật API trong project:

~~~bash
gcloud services enable clouderrorreporting.googleapis.com \
  --project=PROJECT_ID
~~~

Quyền bật API yêu cầu `serviceusage.services.enable`. Khi dùng Error Reporting API, các log entry có định dạng phù hợp cũng được ghi vào Cloud Logging với log name dạng:

~~~text
projects/PROJECT_ID/clouderrorreporting.googleapis.com%2Freported_errors
~~~

Các log entry được tạo từ API có thể phát sinh chi phí ingestion của Cloud Logging. Có thể kiểm soát lượng log được ingest bằng log exclusion filter theo chính sách lưu trữ và điều tra của tổ chức.

Lưu ý: API bị tắt không có nghĩa Error Reporting sẽ ngừng hiển thị mọi lỗi. Error Reporting vẫn có thể suy ra error event từ log entry nếu log đáp ứng các điều kiện phân tích. API cần được bật khi ứng dụng gọi trực tiếp endpoint báo cáo.

## 3. Định dạng log để Error Reporting nhận diện lỗi

Khi ghi log qua Cloud Logging, `LogEntry` cần chứa stack trace hoặc payload có cấu trúc `ReportedErrorEvent`.

### 3.1. Ghi stack trace

Error Reporting có thể nhận diện stack trace từ:

- `textPayload` nhiều dòng.
- `jsonPayload` có một trong các trường `message`, `stack_trace` hoặc `exception`.
- Một trường khác trong `jsonPayload` chứa stack trace theo định dạng của ngôn ngữ được hỗ trợ.

Nếu payload có nhiều trường, thứ tự ưu tiên phân tích là `stack_trace`, sau đó `exception`, rồi `message`. Khi phải phân tích trường `message`, nội dung cần chứa stack trace theo định dạng được hỗ trợ. Stack trace sai định dạng có thể không được nhận diện.

Ví dụ một payload JSON cho ứng dụng Java:

~~~json
{
  "serviceContext": {
    "service": "checkout-api",
    "version": "2026.11.19"
  },
  "message": "java.lang.IllegalStateException: Cannot complete checkout\n\tat com.example.checkout.OrderService.submit(OrderService.java:84)\n\tat com.example.checkout.CheckoutController.create(CheckoutController.java:51)",
  "context": {
    "httpRequest": {
      "method": "POST",
      "url": "/v1/checkout",
      "responseStatusCode": 500
    }
  }
}
~~~

`serviceContext.service` là trường bắt buộc của `ReportedErrorEvent`; `version` giúp xác định bản phát hành liên quan. Thông tin HTTP giúp đội vận hành hiểu request gây lỗi. Nếu log chứa stack trace hợp lệ trong `message`, không cần thêm `@type`.

### 3.2. Ghi thông điệp lỗi không có stack trace

Nếu chỉ có một thông điệp lỗi, hãy đánh dấu payload là `ReportedErrorEvent` bằng giá trị `@type` chính xác:

~~~json
{
  "@type": "type.googleapis.com/google.devtools.clouderrorreporting.v1beta1.ReportedErrorEvent",
  "serviceContext": {
    "service": "inventory-worker",
    "version": "2026.11.19"
  },
  "message": "Inventory reservation failed: warehouse is unavailable",
  "context": {
    "reportLocation": {
      "filePath": "src/inventory/reservation.ts",
      "lineNumber": 42,
      "functionName": "reserveInventory"
    }
  }
}
~~~

Khi không có stack trace, `context.reportLocation` cung cấp vị trí phát sinh lỗi. Với payload chỉ chứa một thông điệp văn bản, `@type` giúp Cloud Logging xử lý log entry như một error event. Nếu `@type` có giá trị khác hoặc không có, Cloud Logging tìm trường `serviceContext` để xác định payload có phải `ReportedErrorEvent` hay không.

Đặt severity của log là `ERROR` cho các exception cần điều tra. Chọn monitored resource type phù hợp với môi trường, ví dụ `cloud_run_revision`, `k8s_container`, `k8s_pod` hoặc `gce_instance`. Một số resource type có yêu cầu riêng; chẳng hạn `global` không hỗ trợ `textPayload`.

### 3.3. Giữ thông tin ổn định và an toàn

Chất lượng dữ liệu quyết định khả năng tổng hợp lỗi:

- Dùng tên service ổn định như `checkout-api`, không tạo service name mới cho từng request.
- Ghi version hoặc revision để so sánh lỗi trước và sau khi phát hành.
- Giữ stack trace nguyên vẹn, bao gồm exception type và các frame thuộc code của ứng dụng.
- Tránh chèn request ID, timestamp, email, mã đơn hàng hoặc giá trị ngẫu nhiên vào phần đầu của message. Các giá trị biến thiên làm lỗi tương tự bị chia thành nhiều nhóm.
- Không ghi access token, session cookie, mật khẩu, dữ liệu thanh toán hoặc thông tin cá nhân không cần thiết vào log và error event.
- Gắn trace ID hoặc request ID ở trường ngữ cảnh phù hợp để tìm log liên quan; không dùng các giá trị này làm tên service hoặc thông điệp lỗi chính.

## 4. Cách Error Reporting tổng hợp lỗi

Error Reporting áp dụng quy tắc gom nhóm theo thứ tự. Cách nhóm phụ thuộc vào nội dung error event:

| Loại event | Cách gom nhóm |
|---|---|
| Lỗi môi trường hoặc một số exception đặc thù | Theo exception type |
| Event có stack trace | Theo exception type và năm stack frame trên cùng; với nested exception, xét exception trong cùng |
| Event không có stack trace nhưng có message | Theo message và function name nếu có; chỉ ba token literal đầu tiên của message được xét |

Trước khi nhóm, Error Reporting có thể rút gọn chuỗi stack frame lặp lại và loại bỏ method hoặc symbol do compiler sinh ra. Các frame thuộc thư viện công khai, không thuộc code của người dùng, có thể bị bỏ qua khi phân tích.

Ví dụ: nhiều request gây `java.lang.NullPointerException` tại cùng đường gọi `CartService.loadCart()` và `CheckoutController.create()`. Dù mỗi request có request ID và timestamp khác nhau, exception type cùng các frame đầu vẫn tương tự nên các event có thể được gom vào một error group. Nhóm lỗi giúp tập trung vào nguyên nhân chung thay vì tạo một mục cho mỗi request.

Nếu message không có stack trace, chỉ ba token đầu được dùng cho quy tắc nhóm. Ví dụ:

- `Payment gateway unavailable for order 123` và `Payment gateway unavailable for order 456` có phần đầu giống nhau, nên có thể được gom chung.
- `Order 123 payment gateway unavailable` và `Order 456 payment gateway unavailable` bắt đầu bằng các token khác nhau, nên có thể bị chia thành các nhóm riêng.

Vì vậy, hãy đặt phần mô tả ổn định của lỗi ở đầu message, đưa dữ liệu biến thiên vào context hoặc trường riêng. Không chỉnh sửa stack trace để cố ép các lỗi khác nguyên nhân vào cùng một nhóm.

### Lấy mẫu và số lượng hiển thị

Để tối ưu hiệu năng, Error Reporting lấy mẫu tối đa 1.000 lỗi mỗi giờ và ước lượng số lượng khi đạt ngưỡng. Khi lượng event vượt khả năng xử lý, hệ thống lấy mẫu tối đa 100 lỗi mỗi giờ và tiếp tục ngoại suy số lượng hiển thị. Error group giữ tối đa 1.000 event mẫu; để kiểm tra các lần xuất hiện riêng lẻ, hãy truy vấn log liên quan trong Logs Explorer.

Do có lấy mẫu, số lần xảy ra trên trang Error Reporting có thể là ước lượng. Khi cần điều tra chính xác một request, đối chiếu log entry, trace và metric của dịch vụ. Error event qua API được bảo đảm có thể truy cập ít nhất 30 ngày kể từ khi được tạo.

## 5. Xem và quản lý error group

Trong Google Cloud Console, mở **Error Reporting** và chọn project cần điều tra. Trang tổng quan cho phép sắp xếp, lọc và xem các error group theo tên lỗi, trạng thái xử lý, HTTP response code và số lần xuất hiện theo thời gian.

Khi mở một error group, bạn có thể xem:

- Lịch sử các error event và thời điểm xảy ra.
- Số lần xuất hiện và trạng thái xử lý.
- Các event mẫu, message và stack trace nếu có.
- Liên kết đến log entry liên quan trong Logs Explorer.
- Liên kết đến issue tracker hoặc tài liệu hướng dẫn xử lý.

Logs Explorer cho phép lọc theo ID của error group, ví dụ:

~~~text
errorGroups.id="ERROR_GROUP_ID"
~~~

Trường `errorGroups` chỉ xuất hiện trong log entry được lưu trong log bucket và được bucket destination bổ sung. Không nên giả định mọi log entry gửi vào project hoặc đi qua log sink đều có trường này.

### Trạng thái xử lý

| Trạng thái | Ý nghĩa | Khi nào dùng |
|---|---|---|
| Open | Trạng thái mặc định, đang chờ xử lý | Lỗi mới hoặc lỗi cần điều tra |
| Acknowledged | Đã có người tiếp nhận | Đội trực đã xác nhận và đang triage |
| Resolved | Đã sửa và không dự kiến tái diễn | Sau khi xác minh bản sửa |
| Muted | Ẩn nhóm lỗi khỏi danh sách | Nhóm đã được đánh giá là không cần theo dõi tại đây |

Nếu một error group ở trạng thái Resolved lại phát sinh event, Error Reporting chuyển nhóm về Open. Với nhóm Muted, event mới không được ghi nhận và không tạo notification. Vì vậy, cần cân nhắc kỹ trước khi mute lỗi; mute có thể làm mất tín hiệu tái diễn khỏi quy trình theo dõi.

## 6. Cấu hình thông báo và quy trình xử lý

Error Reporting có thể gửi notification qua các notification channel của Cloud Monitoring, gồm email, ứng dụng Google Cloud trên thiết bị di động, Slack và webhook. Các channel được tạo trong Monitoring rồi chọn trong cấu hình notification của Error Reporting.

Thông báo được gửi trong hai trường hợp:

1. Có error event không khớp với error group hiện có, nghĩa là một nhóm lỗi mới xuất hiện.
2. Một error group đang Resolved phát sinh lỗi trở lại, nghĩa là có regression.

Error Reporting không gửi notification cho mọi event lặp lại trong một nhóm đang Open hoặc Acknowledged. Hệ thống cũng áp dụng giới hạn notification: tối đa 20 notification mỗi project trong một cửa sổ 60 phút. Nếu vượt giới hạn, nhóm vận hành nhận thông báo rằng notification bị tạm ngưng trong sáu giờ và một log entry mức `WARNING` được ghi lại. Khi vừa resolve một nhóm, notification cho nhóm đó được tạm ngưng trong năm phút.

Quy trình triage đề xuất:

1. **Nhận diện**: kiểm tra nhóm lỗi mới, mức độ ảnh hưởng, thời điểm bắt đầu và service/version liên quan.
2. **Xác định phạm vi**: xem số lần xuất hiện, xu hướng tăng, HTTP status code và các workload bị ảnh hưởng.
3. **Điều tra**: mở event mẫu, stack trace, log entry và trace của request liên quan.
4. **Phân công**: chuyển trạng thái sang Acknowledged, gắn link issue tracker và chỉ định đội phụ trách.
5. **Khắc phục**: sửa code hoặc cấu hình, kiểm thử và phát hành bản sửa.
6. **Xác minh**: kiểm tra log và metric sau phát hành; khi lỗi không còn tái diễn, chuyển sang Resolved.
7. **Theo dõi regression**: nếu lỗi quay lại, Error Reporting mở lại nhóm và gửi notification theo cấu hình.

Notification của Error Reporting giúp phát hiện nhóm lỗi mới hoặc lỗi tái diễn. Để cảnh báo theo tỷ lệ lỗi, số request thất bại, latency hay SLO, hãy tạo alerting policy riêng trong Cloud Monitoring.

## 7. IAM và kiến trúc nhiều project

Phân quyền theo vai trò thực tế, tránh cấp quyền quản trị rộng cho mọi người:

| Vai trò | Mục đích |
|---|---|
| `roles/errorreporting.viewer` | Xem error group và event ở chế độ chỉ đọc |
| `roles/errorreporting.user` | Đọc, cập nhật metadata và quản lý error group; không bao gồm quyền gửi event mới |
| `roles/errorreporting.writer` | Cho service account quyền gửi error event qua API |

Tài liệu IAM hiện đánh dấu các vai trò Error Reporting này là Beta. Quyền bật API yêu cầu `serviceusage.services.enable`. Khi cấu hình notification, người thực hiện cần `roles/errorreporting.user`, `roles/monitoring.viewer` để xem channel và `roles/monitoring.editor` để tạo channel nếu chưa có. Hãy kiểm tra quyền theo project và dùng custom role khi cần giới hạn phạm vi.

### Tổng hợp lỗi trong mô hình nhiều project

Một tổ chức có thể tách project theo môi trường hoặc domain:

- `app-dev`: môi trường phát triển.
- `app-staging`: môi trường kiểm thử tích hợp.
- `app-prod`: môi trường sản xuất.
- `observability-prod`: project tập trung log và công cụ quan sát.

Mỗi ứng dụng cần service context rõ ràng, ví dụ `checkout-api` và version phát hành. Có thể dùng Cloud Logging sink để định tuyến log đến project tập trung. Để Error Reporting phân tích log, log bucket phải thuộc project nơi log phát sinh hoặc project nhận log sau khi định tuyến và lưu log vào bucket do chính project nhận đó sở hữu. Nếu sink chuyển log sang một project khác nhưng log được lưu trong bucket do project khác thứ ba sở hữu, Error Reporting có thể không phân tích được log đó.

Hãy xác định rõ project sở hữu log bucket, quyền ghi log của sink, quyền đọc log và nơi đội trực mở Error Reporting. Không mặc định rằng một trang Error Reporting tự động gộp mọi lỗi từ tất cả project trong tổ chức; cần thiết kế đường đi của log và project đích có chủ đích.

### Giới hạn về CMEK, Assured Workloads và khu vực

Error Reporting là dịch vụ global xây dựng trên Cloud Logging. Đối với log-based collection, các điều kiện sau phải được đáp ứng:

- Assured Workloads không được bật cho workload liên quan. Khi cấu hình Assured Workloads cho data residency hoặc Impact Level 4, Google Cloud tự động tắt Error Reporting.
- Các log bucket lưu log entry cần phân tích không được bật customer-managed encryption key (CMEK). Error Reporting không thể lưu log entry trong bucket có CMEK.
- Log bucket phải nằm trong project phát sinh log hoặc project nhận log sau khi định tuyến và lưu log trong bucket do project đó sở hữu.

VPC Service Controls hỗ trợ Error Reporting. Nếu tổ chức có yêu cầu kiểm soát luồng dữ liệu, hãy đưa Error Reporting vào thiết kế service perimeter phù hợp. Log bucket có thể được regionalize; Error Reporting hiển thị nhóm lỗi theo region của bucket, nhưng bản thân Error Reporting là dịch vụ global và error group có thể được truy cập từ mọi region. Nếu yêu cầu residency không cho phép hành vi này, hãy đánh giá việc sử dụng Error Reporting trước khi triển khai.

## 8. Tình huống thực tế: lỗi checkout tăng sau khi phát hành

Một dịch vụ `checkout-api` chạy trên Cloud Run vừa phát hành version `2026.11.19`. Sau vài phút, tỷ lệ HTTP 500 tăng. Đội trực mở Error Reporting và thấy một nhóm `IllegalStateException` mới có số lần xuất hiện tăng nhanh.

Quy trình xử lý:

1. Mở error group và xác định version phát sinh lỗi. Nếu lỗi chỉ xuất hiện trên version mới, ưu tiên so sánh thay đổi của bản phát hành đó.
2. Mở stack trace và chọn log entry liên quan trong Logs Explorer. Dùng trace ID hoặc request ID để tìm các log trước và sau request thất bại.
3. Kiểm tra metric request count, HTTP 5xx và latency trong Cloud Monitoring để xác định mức ảnh hưởng.
4. Liên kết error group với issue tracker, chuyển trạng thái sang Acknowledged và giao cho nhóm checkout.
5. Nếu nguyên nhân là thay đổi xử lý giỏ hàng, phát hành bản sửa hoặc rollback theo quy trình release.
6. Theo dõi error group và metric sau thay đổi. Khi lỗi không còn xuất hiện trong khoảng thời gian đủ đại diện cho tải thực tế, chuyển nhóm sang Resolved.
7. Nếu lỗi quay lại, notification sẽ báo regression và nhóm chuyển về Open.

Sơ đồ xử lý:

~~~mermaid
flowchart TD
    A["Phát hành version mới"] --> B["HTTP 500 tăng"]
    B --> C["Error Reporting tạo / cập nhật error group"]
    C --> D["Đọc stack trace và log liên quan"]
    D --> E["Đối chiếu metric, trace và thay đổi release"]
    E --> F["Sửa lỗi hoặc rollback"]
    F --> G["Xác minh bằng log và metric"]
    G --> H{"Lỗi còn tái diễn?"}
    H -->|Có| D
    H -->|Không| I["Đánh dấu Resolved"]
    I --> J["Theo dõi notification regression"]
~~~

### Kiểm tra nhanh trong môi trường thử nghiệm

Có thể gửi một lỗi thử nghiệm bằng Google Cloud CLI để xác nhận đường đi đến Error Reporting:

~~~bash
gcloud beta error-reporting events report \
  --service checkout-api \
  --service-version test-1 \
  --message="java.lang.IllegalStateException: Test checkout failure
    at com.example.checkout.OrderService.submit(OrderService.java:84)
    at com.example.checkout.CheckoutController.create(CheckoutController.java:51)"
~~~

Mở Error Reporting của project tương ứng và tìm nhóm lỗi `IllegalStateException: Test checkout failure`. Kiểm tra Logs Explorer để xác nhận log entry đã được tạo. Chỉ chạy lệnh này trong project thử nghiệm hoặc theo quy trình kiểm thử được phê duyệt; không tạo error giả trong môi trường production để thử notification.

## 9. Khắc phục lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| Trang Error Reporting trống | Chưa có error group hoặc chưa có log phù hợp | Gửi một error event thử nghiệm; kiểm tra project đang chọn |
| Gọi API nhưng không thấy event | API chưa bật, thiếu quyền hoặc payload sai | Kiểm tra `clouderrorreporting.googleapis.com`, quyền gửi event và định dạng `ReportedErrorEvent` |
| Log có stack trace nhưng không được nhóm | Stack trace sai định dạng hoặc nằm ở field không được ưu tiên | Kiểm tra `message`, `stack_trace`, `exception`; dùng stack trace theo format được hỗ trợ |
| Log có message nhưng không có stack trace | Payload chỉ có văn bản thường, thiếu `@type` hoặc `serviceContext` phù hợp | Định dạng payload thành `ReportedErrorEvent`; nếu không có stack trace, cung cấp `reportLocation` |
| Lỗi từ Cloud Run không xuất hiện | Exception không được ghi ra `stdout`/`stderr` hoặc log không có stack trace | Kiểm tra log runtime; cân nhắc client library hoặc structured log |
| Lỗi từ project khác không được phân tích | Log sink định tuyến đến bucket không thuộc project nhận log hoặc bucket bật CMEK | Kiểm tra sink destination, project sở hữu bucket và cấu hình CMEK |
| Số lần xuất hiện không khớp số log | Error Reporting lấy mẫu và ngoại suy count | Dùng Logs Explorer để kiểm tra các log entry riêng lẻ |
| Không nhận notification | Nhóm đang Open/Acknowledged, Muted hoặc vượt rate limit | Kiểm tra trạng thái group, notification channel và log cảnh báo giới hạn |

Khi debug log-based collection, kiểm tra thêm:

1. Log entry có được ghi vào Cloud Logging hay chưa.
2. Severity và monitored resource type có phù hợp không.
3. Nếu `jsonPayload` có `stack_trace`, `exception` và `message`, trường nào đang được phân tích theo thứ tự ưu tiên.
4. Project sở hữu log bucket có đúng với project phát sinh hoặc project nhận log sau khi routing không.
5. Có bật CMEK trên bất kỳ bucket nào lưu log entry đó không.
6. Workload có nằm trong Assured Workloads không.
7. Dùng `gcloud logging sinks list` để kiểm tra nơi log được định tuyến.

## 10. Nguyên tắc vận hành tốt

- Chuẩn hóa service name, version và cấu trúc log trên các dịch vụ.
- Ghi exception có stack trace và context cần thiết; không gửi message chung chung như `Something went wrong`.
- Giữ message ổn định để lỗi cùng nguyên nhân được gom vào cùng nhóm.
- Không log bí mật, token hoặc dữ liệu cá nhân không cần thiết.
- Kết hợp Error Reporting với Logs Explorer, Cloud Trace và Cloud Monitoring để xác định nguyên nhân và mức độ ảnh hưởng.
- Thiết lập notification cho nhóm mới và regression; dùng alerting policy cho tỷ lệ lỗi và SLO.
- Gắn link issue tracker vào error group để lưu lịch sử xử lý và trách nhiệm.
- Đánh dấu Resolved sau khi xác minh; chỉ Muted khi đã hiểu rõ tác động của việc không ghi nhận event mới trong nhóm đó.
- Trong kiến trúc nhiều project, kiểm thử log routing, quyền IAM, bucket ownership và điều kiện CMEK trước khi đưa vào vận hành.
- Theo dõi chi phí Cloud Logging khi gửi event qua API và điều chỉnh log exclusion filter theo nhu cầu điều tra.

## 11. Tự kiểm tra

1. Phân biệt error event và error group. Vì sao một error group có thể chứa nhiều event?
2. Có những cách nào để đưa lỗi ứng dụng vào Error Reporting?
3. Với một `jsonPayload` chứa cả `stack_trace`, `exception` và `message`, Error Reporting ưu tiên trường nào?
4. Vì sao message nên bắt đầu bằng phần mô tả ổn định của lỗi?
5. Khi một nhóm lỗi được đánh dấu Resolved rồi tái xuất hiện, Error Reporting xử lý thế nào?
6. Tại sao Error Reporting có thể không phân tích được log trong một log bucket bật CMEK?
7. Khi số lần xuất hiện trên Error Reporting khác với số log entry, cần dùng công cụ nào để kiểm tra chi tiết?

**Gợi ý đáp án**

1. Error event là một lần lỗi; error group gom các event có dấu hiệu cùng nguyên nhân để hỗ trợ điều tra.
2. Thu thập tự động qua Cloud Logging, client library, Error Reporting API hoặc ghi log theo định dạng được hỗ trợ qua Cloud Logging API.
3. `stack_trace`, sau đó `exception`, rồi `message`.
4. Quy tắc nhóm message không có stack trace chỉ xét ba token literal đầu tiên; dữ liệu biến thiên ở đầu message có thể tạo nhiều nhóm khác nhau.
5. Nhóm chuyển về Open và có thể tạo notification regression theo cấu hình.
6. Error Reporting không thể lưu log entry trong log bucket có CMEK; log-based collection không phân tích được log entry đó.
7. Dùng Logs Explorer để truy vấn các log entry riêng lẻ và đối chiếu thời điểm, request hoặc trace.

## Tài liệu tham khảo

- [Google Cloud: Error Reporting overview and grouping](https://docs.cloud.google.com/error-reporting/docs/grouping-errors)
- [Google Cloud: Collect error data](https://docs.cloud.google.com/error-reporting/docs/setup)
- [Google Cloud: Format a log entry to report error events](https://docs.cloud.google.com/error-reporting/docs/formatting-error-messages)
- [Google Cloud: View and filter error groups](https://docs.cloud.google.com/error-reporting/docs/viewing-errors)
- [Google Cloud: Manage error groups](https://docs.cloud.google.com/error-reporting/docs/managing-errors)
- [Google Cloud: Configure and manage notifications](https://docs.cloud.google.com/error-reporting/docs/notifications)
- [Google Cloud: Troubleshoot Error Reporting](https://docs.cloud.google.com/error-reporting/docs/troubleshooting)
- [Google Cloud: Error Reporting roles and permissions](https://docs.cloud.google.com/iam/docs/roles-permissions/errorreporting)
