# Alerting policies, notification channels và uptime checks

Một hệ thống có thể vẫn chạy nhưng đã bắt đầu suy giảm: CPU liên tục cao, API trả lỗi, hàng đợi tăng, chứng thư TLS sắp hết hạn hoặc endpoint không còn phản hồi. Nếu đội vận hành chỉ phát hiện qua phản ánh của người dùng, thời gian gián đoạn sẽ kéo dài. Cloud Monitoring giúp phát hiện những dấu hiệu này bằng alerting policies, gửi thông báo qua notification channels và kiểm tra tính sẵn sàng từ nhiều vị trí bằng uptime checks.

Trong Google Cloud, ba thành phần này phối hợp với nhau. Alerting policy xác định điều kiện cần chú ý; notification channel chuyển cảnh báo tới người hoặc hệ thống chịu trách nhiệm; uptime check chủ động gửi yêu cầu định kỳ tới endpoint để xác nhận dịch vụ có thể truy cập và trả về nội dung mong đợi hay không.

Bài học đặt các thành phần trong bối cảnh Cloud Observability: theo dõi độ tin cậy của Compute Engine, GKE, Cloud Run, cơ sở dữ liệu, API và các dịch vụ kết nối với nhau. Bạn sẽ học cách thiết kế điều kiện cảnh báo có ý nghĩa, chọn kênh thông báo phù hợp và kiểm tra endpoint công khai hoặc nội bộ.

Trong module CLOUD_PROVIDERS_GCP, người học khám phá Google Cloud từ tổ chức project, IAM và VPC đến Compute Engine, GKE, Cloud Run, dịch vụ lưu trữ và cơ sở dữ liệu. Qua các tình huống triển khai, người học thực hành lựa chọn dịch vụ, bảo vệ tài nguyên, tự động hóa phát hành và theo dõi độ tin cậy cùng chi phí. Alerting policies, notification channels và uptime checks là lớp vận hành giúp biến dữ liệu quan sát thành hành động kịp thời.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích quan hệ giữa alerting policy, alert/incident và notification channel.
- Phân biệt metric-based, log-based và SQL-based alerting policies.
- Thiết kế threshold, retest window, alignment period, trigger và cách xử lý missing data.
- Tạo policy bằng Google Cloud Console hoặc Google Cloud CLI.
- Chọn, xác minh và bảo vệ notification channels.
- Phân biệt public uptime check với private uptime check.
- Cấu hình HTTP, HTTPS hoặc TCP check, response validation và alert khi endpoint không hoạt động.
- Điều tra cảnh báo, xử lý false positive và xây dựng quy trình on-call đáng tin cậy.

## 1. Ba thành phần của hệ thống cảnh báo

Cloud Monitoring sử dụng ba thành phần chính:

| Thành phần | Vai trò | Câu hỏi được trả lời |
|---|---|---|
| Alerting policy | Định nghĩa điều kiện và cách đánh giá dữ liệu | Khi nào cần cảnh báo? |
| Alert hoặc incident | Ghi nhận lần điều kiện của policy được đáp ứng | Sự kiện nào đã xảy ra, vào lúc nào và liên quan tài nguyên nào? |
| Notification channel | Định nghĩa nơi nhận thông báo | Ai hoặc hệ thống nào cần biết? |

Một alerting policy có thể theo dõi metric, log entry hoặc kết quả truy vấn SQL. Khi điều kiện được đáp ứng, Cloud Monitoring mở alert và gửi thông báo tới các notification channels được gắn với policy. Một policy có thể gắn nhiều channel, ví dụ email cho nhóm trực và Pub/Sub cho hệ thống tự động hóa.

Uptime check là một nguồn dữ liệu khác trong Cloud Monitoring. Nó gửi request HTTP, HTTPS hoặc TCP định kỳ từ nhiều checker locations. Kết quả của các lần kiểm tra được lưu thành time series; alerting policy có thể dùng time series đó để cảnh báo khi endpoint thất bại.

### Luồng hoạt động

~~~mermaid
flowchart TD
    A[Ứng dụng và hạ tầng] --> B[Cloud Monitoring metrics]
    A --> C[Cloud Logging entries]
    D[Uptime check: HTTP / HTTPS / TCP] --> B
    B --> E[Alerting policy]
    C --> E
    E --> F{Điều kiện được đáp ứng?}
    F -->|Chưa| G[Tiếp tục đánh giá]
    F -->|Có| H[Open alert / incident]
    H --> I[Notification channels]
    I --> J[Email / SMS / Slack / PagerDuty]
    I --> K[Webhook / Pub/Sub]
    J --> L[On-call engineer]
    K --> M[Ticketing / automation / SOC]
~~~

Một notification channel chỉ chuyển thông báo. Nó không tự sửa lỗi ứng dụng. Một uptime check chỉ xác minh khả năng phản hồi theo cấu hình; nó không kiểm thử toàn bộ trải nghiệm người dùng hoặc mọi nghiệp vụ bên trong ứng dụng.

## 2. Alerting policy hoạt động như thế nào?

Một alerting policy là cấu hình mô tả điều kiện cho biết hệ thống có thể đang ở trạng thái không khỏe mạnh. Policy thường có:

- **Display name:** tên dễ nhận biết, ví dụ `API latency above 2 seconds`.
- **Conditions:** một hoặc nhiều điều kiện cần đánh giá.
- **Combiner:** cách kết hợp nhiều condition.
- **Notification channels:** danh sách kênh gửi thông báo.
- **Severity:** mức độ ưu tiên, ví dụ WARNING, ERROR hoặc CRITICAL.
- **Documentation:** hướng dẫn xử lý được đính kèm notification.
- **User labels:** nhãn giúp lọc, phân nhóm và định tuyến trong hệ thống vận hành.
- **Alert strategy:** các tùy chọn về auto-close, thông báo khi đóng và lặp lại thông báo đối với policy metric-based.

Một alert có thể đại diện cho một time series vi phạm điều kiện. Nếu policy theo dõi nhiều VM, nhiều series có thể tạo nhiều alert riêng. Do đó, cần quyết định liệu muốn cảnh báo từng instance hay tổng hợp dữ liệu theo zone, service hoặc application.

### Các loại dữ liệu có thể giám sát

| Loại policy | Nguồn dữ liệu | Ví dụ |
|---|---|---|
| Metric-based | Time series trong Cloud Monitoring | CPU vượt 80% trong 5 phút |
| Log-based | Log entry trong Cloud Logging | Có log ERROR khớp bộ lọc |
| SQL-based | Kết quả truy vấn SQL trong Observability Analytics | Truy vấn đếm số lỗi theo service vượt ngưỡng |
| PromQL-based | Biểu thức PromQL trên time series | Tỷ lệ lỗi HTTP 5xx trên tổng request vượt 5% |
| Metric absence | Không có dữ liệu metric trong khoảng thời gian định nghĩa | Pipeline không phát heartbeat trong 30 phút |
| Forecasted metric value | Dự báo time series | Dung lượng disk được dự báo sẽ vượt 80% trong ngày tới |

Các loại condition và khả năng cấu hình có thể khác nhau giữa Console, API và từng loại policy. Đặc biệt, log-based alerting policy theo dõi log entry trực tiếp khác với policy metric-based theo dõi log-based metric. Nếu cần cảnh báo khi một bản ghi cụ thể xuất hiện, dùng log-based alert. Nếu cần cảnh báo theo số lượng hoặc tỷ lệ log trong một khoảng thời gian, tạo log-based metric rồi dùng metric-threshold policy.

### Metric threshold và metric absence

**Metric threshold** mở alert khi giá trị metric vượt hoặc thấp hơn ngưỡng trong retest window. Ví dụ, CPU utilization lớn hơn 0.8 trong 300 giây.

**Metric absence** mở alert khi metric vốn có dữ liệu trước đó nhưng không còn xuất hiện trong khoảng thời gian được cấu hình. Ví dụ, một job định kỳ gửi heartbeat mỗi 10 phút nhưng không gửi dữ liệu trong 30 phút.

Metric absence cần có dữ liệu được ghi nhận trước đó để xác định time series đang được theo dõi. Nếu resource bị xóa hoặc tắt, Monitoring có thể không tạo alert absence như mong đợi; cần xác định trạng thái resource và semantics của metric.

## 3. Thiết kế điều kiện: threshold, alignment và retest window

Một policy có thể cảnh báo quá sớm nếu điều kiện chỉ dựa trên một mẫu dữ liệu. Ngược lại, policy có thể cảnh báo quá muộn nếu khoảng thời gian đánh giá quá dài. Ba khái niệm quan trọng giúp kiểm soát hành vi đó.

### Alignment period

Alignment period (rolling window trong Console) là khoảng thời gian dùng để chuẩn hóa các điểm dữ liệu của một time series thành điểm đã được tổng hợp. Ví dụ, nếu chọn 60 giây và aligner là mean, Monitoring tính giá trị trung bình của các điểm trong mỗi khoảng 60 giây.

Một số aligner thường gặp:

| Aligner | Ý nghĩa | Tình huống sử dụng |
|---|---|---|
| ALIGN_MEAN | Trung bình trong alignment period | CPU utilization hoặc latency |
| ALIGN_MAX | Giá trị lớn nhất | Phát hiện spike |
| ALIGN_MIN | Giá trị nhỏ nhất | Theo dõi dung lượng trống |
| ALIGN_SUM | Tổng các giá trị | Số lượng request hoặc byte theo khoảng |
| ALIGN_DELTA | Chênh lệch giữa giá trị đầu và cuối | Counter hoặc metric dạng DELTA |
| ALIGN_RATE | Tốc độ thay đổi theo thời gian | Throughput hoặc tốc độ phát sinh lỗi |

Việc chọn aligner phải phù hợp với metric kind và value type. Ví dụ, dùng mean cho metric DELTA có thể không mang ý nghĩa như mong đợi; khi theo dõi tổng lượng hoặc tốc độ, hãy chọn aligner phù hợp với kiểu dữ liệu.

### Retest window

Retest window (duration của condition) là khoảng thời gian điều kiện phải liên tục được đáp ứng trước khi policy mở alert. Nếu CPU vượt 80% trong một mẫu duy nhất nhưng sau đó giảm ngay, policy có retest window 5 phút sẽ tránh cảnh báo cho spike ngắn.

- Không retest: một mẫu vi phạm có thể mở alert ngay.
- Retest 5 phút: dữ liệu phải tiếp tục vi phạm trong toàn bộ khoảng đánh giá.
- Retest dài hơn: giảm cảnh báo do dao động ngắn, nhưng tăng thời gian phát hiện.

Alignment period và retest window giải quyết hai việc khác nhau: alignment tổng hợp dữ liệu trong từng time series; retest xác định thời gian điều kiện cần duy trì.

### Trigger và aggregation

Trigger xác định có bao nhiêu time series phải vi phạm để condition được đáp ứng:

- **Any time series violates:** chỉ cần một time series vi phạm.
- **Number of time series violates:** một số lượng cụ thể time series phải vi phạm.
- **Percent of time series violates:** một tỷ lệ phần trăm time series phải vi phạm.
- **All time series violate:** tất cả time series phải vi phạm.

Cross-series aggregation có thể gộp nhiều time series thành một hoặc chia nhóm theo label. Ví dụ, tính CPU trung bình theo zone sẽ giảm số alert nhưng có thể che khuất một VM riêng lẻ đang quá tải. Nếu mục tiêu là phát hiện một instance có vấn đề, hãy giữ từng time series hoặc nhóm theo instance. Nếu mục tiêu là phát hiện một service tổng thể suy giảm, hãy nhóm theo service hoặc zone.

### Combiner khi có nhiều conditions

Một policy có thể có nhiều conditions. Combiner xác định logic giữa chúng:

- **OR:** bất kỳ condition nào được đáp ứng thì policy có thể mở alert.
- **AND:** tất cả conditions phải được đáp ứng.
- **AND_WITH_MATCHING_RESOURCE:** tất cả conditions phải được đáp ứng trên cùng một monitored resource.

Ví dụ, một policy có thể theo dõi CPU cao và disk gần đầy. Dùng OR nếu mỗi vấn đề đều cần được xử lý độc lập. Dùng AND nếu chỉ muốn cảnh báo khi hai dấu hiệu cùng xảy ra trên một tài nguyên.

Không nên gom các vấn đề không liên quan vào một policy chỉ để giảm số lượng policy. Mỗi alert nên có một mục tiêu điều tra và hướng xử lý rõ ràng.

### Missing data

Khi metric ngừng gửi dữ liệu, Monitoring phải quyết định coi điều kiện vẫn đang được đáp ứng, không được đáp ứng hay chuyển sang trạng thái thiếu dữ liệu. Cấu hình missing-data có thể ảnh hưởng đến việc mở và đóng alert.

Ví dụ:

- Với policy CPU, VM tắt có thể không còn gửi metric; việc coi thiếu dữ liệu là vi phạm có thể tạo cảnh báo không cần thiết.
- Với policy heartbeat, thiếu dữ liệu chính là điều cần phát hiện; nên dùng metric absence hoặc cấu hình missing-data phù hợp.
- Với policy theo dõi latency, dữ liệu ngừng đến có thể là lỗi telemetry hoặc lỗi ứng dụng; nên có một policy riêng theo dõi tính đầy đủ của dữ liệu.

Đừng mặc định missing data có nghĩa là hệ thống khỏe mạnh. Hãy xác định nguồn dữ liệu nào phải luôn xuất hiện và nguồn nào có thể biến mất hợp lệ.

### Auto-close, acknowledgement và snooze

- **Auto-close:** Monitoring đóng alert khi condition không còn được đáp ứng hoặc khi không có dữ liệu mới trong khoảng auto-close được cấu hình. Giá trị mặc định cho metric-based policy là 7 ngày; thời gian tối thiểu là 30 phút.
- **Notify on alert closure:** tùy chọn gửi thông báo khi alert đóng. Với policy tạo qua Console, mặc định chỉ gửi thông báo khi alert mở.
- **Acknowledge:** người trực xác nhận đã nhận và bắt đầu điều tra alert.
- **Snooze:** tạm ngừng thông báo từ policy trong một khoảng thời gian, ví dụ khi đội vận hành đang xử lý outage. Snooze không sửa điều kiện và không tự giải quyết sự cố.

Khi alert đóng, điều đó có thể chỉ có nghĩa condition đã trở lại bình thường hoặc auto-close đã hết hạn. Hãy kiểm tra dữ liệu metric và trạng thái ứng dụng trước khi kết luận sự cố đã được khắc phục.

## 4. Tạo alerting policy theo metric

Ví dụ: cảnh báo khi CPU utilization của bất kỳ Compute Engine VM nào vượt 80% liên tục trong 5 phút.

### Chuẩn bị

- Chọn project chứa VM cần theo dõi.
- Bật Cloud Monitoring API nếu chưa bật.
- Xác nhận metric `compute.googleapis.com/instance/cpu/utilization` có dữ liệu.
- Chuẩn bị notification channel.
- Cấp vai trò Monitoring Editor (`roles/monitoring.editor`) cho người tạo hoặc sửa policy trong Console. Với API, có thể dùng các vai trò chuyên biệt như Monitoring AlertPolicy Editor (`roles/monitoring.alertPolicyEditor`).

### Tạo trong Google Cloud Console

1. Mở Google Cloud Console và chọn project.
2. Vào Monitoring > Alerting.
3. Chọn Create policy.
4. Chọn metric `CPU utilization` của resource type `VM instance`.
5. Thêm filter nếu chỉ theo dõi một zone, instance hoặc nhóm workload.
6. Trong Transform data, chọn rolling window 60 giây và function mean.
7. Trong Configure alert trigger, chọn Threshold, Above threshold và giá trị 0.8.
8. Đặt Retest window thành 5 phút.
9. Chọn trigger Any time series violates nếu muốn cảnh báo khi một VM bất kỳ vượt ngưỡng.
10. Chọn notification channels, severity và bật Notify on alert closure nếu đội vận hành cần nhận thông báo khi tình trạng được giải quyết.
11. Đặt tên, thêm Documentation hướng dẫn kiểm tra VM, rồi tạo policy.

### Tạo bằng JSON và gcloud

Một policy có thể được lưu trong file JSON rồi tạo bằng Google Cloud CLI. Ví dụ sau dùng một notification channel đã tồn tại. Thay các placeholder bằng project ID và channel ID thực tế:

~~~json
{
  "displayName": "VM CPU above 80 percent for 5 minutes",
  "combiner": "OR",
  "enabled": true,
  "severity": "WARNING",
  "conditions": [
    {
      "displayName": "CPU utilization above 80 percent",
      "conditionThreshold": {
        "filter": "metric.type=\"compute.googleapis.com/instance/cpu/utilization\" AND resource.type=\"gce_instance\"",
        "comparison": "COMPARISON_GT",
        "thresholdValue": 0.8,
        "duration": "300s",
        "aggregations": [
          {
            "alignmentPeriod": "60s",
            "perSeriesAligner": "ALIGN_MEAN"
          }
        ],
        "trigger": {
          "count": 1
        }
      }
    }
  ],
  "notificationChannels": [
    "projects/PROJECT_ID/notificationChannels/CHANNEL_ID"
  ],
  "alertStrategy": {
    "autoClose": "604800s"
  },
  "documentation": {
    "mimeType": "text/markdown",
    "content": "CPU utilization has exceeded 80 percent for 5 minutes. Check the VM workload, recent deployments, CPU throttling, and request volume. Follow the service runbook before resizing or restarting the instance."
  }
}
~~~

Lưu nội dung thành `cpu-alert-policy.json`, sau đó chạy:

~~~bash
gcloud monitoring policies create \
  --policy-from-file="cpu-alert-policy.json" \
  --project=PROJECT_ID
~~~

Để xem các policy đã có:

~~~bash
gcloud monitoring policies list --project=PROJECT_ID
~~~

Để xem chi tiết một policy:

~~~bash
gcloud monitoring policies describe POLICY_ID \
  --project=PROJECT_ID
~~~

Trong JSON, `notificationChannels` chứa resource name đầy đủ của channel. Lấy ID bằng cách liệt kê notification channels trong project; không tự đoán channel ID.

### Kiểm tra policy

Sau khi tạo:

- Xem policy trong Monitoring > Alerting.
- Xác nhận metric có dữ liệu và filter chọn đúng resource.
- Kiểm tra threshold, alignment period, retest window và trigger.
- Kiểm tra channel có trong policy.
- Kiểm tra Documentation có hướng dẫn hành động.
- Tạo một tình huống kiểm thử an toàn trong môi trường thử nghiệm để xác minh alert và notification.

Không tăng tải CPU trên production chỉ để thử policy. Nếu không thể tạo điều kiện thử nghiệm, dùng dữ liệu lịch sử, metric test hoặc một VM lab riêng.

## 5. Notification channels

Notification channel xác định nơi Cloud Monitoring gửi thông báo khi policy mở alert. Channel được tạo trong một Google Cloud project và có thể được gắn vào một hoặc nhiều alerting policies trong phạm vi hỗ trợ.

Các loại channel phổ biến:

| Channel | Cách sử dụng | Lưu ý vận hành |
|---|---|---|
| Email | Gửi cho cá nhân hoặc nhóm trực | Group cần chấp nhận email từ `alerting-noreply@google.com` |
| SMS | Gửi tin nhắn tới số điện thoại đã xác minh | Không nên dùng làm kênh duy nhất; khả năng nhận tin phụ thuộc khu vực và nhà mạng |
| Google Cloud console Mobile App | Gửi thông báo tới thiết bị hoặc người dùng app | Phạm vi channel được xác định khi tạo |
| Slack | Gửi thông báo vào Slack channel | Cần OAuth; private channel phải mời Google Cloud Monitoring app |
| PagerDuty | Tích hợp hệ thống on-call và escalation | Có đồng bộ hai chiều một phần; resolve ở PagerDuty không đóng alert trong Monitoring |
| Webhook | Gửi HTTP request tới endpoint bên ngoài | Endpoint phải truy cập công khai; HTTPS cần chứng thư hợp lệ |
| Pub/Sub | Đưa notification vào topic để hệ thống khác xử lý | Cần service account có quyền publish và subscription để nhận message |
| Google Chat | Gửi thông báo tới Chat space | Tính năng Preview/Pre-GA; kiểm tra điều kiện tổ chức trước khi dùng |

### Chọn channel theo mục đích

- Email phù hợp với thông báo dài, lịch sử và nhóm nhận rộng.
- SMS hoặc mobile app phù hợp để đánh thức người trực trong tình huống cần chú ý nhanh; cần kênh dự phòng.
- Slack, Google Chat hoặc PagerDuty phù hợp với quy trình on-call và phối hợp nhóm.
- Webhook hoặc Pub/Sub phù hợp với tích hợp tự động, ví dụ tạo ticket, enrichment hoặc kích hoạt workflow.
- Pub/Sub phù hợp khi hệ thống nhận thông báo nằm trong mạng riêng hoặc cần xử lý bất đồng bộ.

Google khuyến nghị dùng nhiều loại channel để dự phòng. Cloud Mobile App, PagerDuty, webhook và Slack cùng dựa vào một dịch vụ nội bộ của Google Cloud, do đó có chung một điểm phụ thuộc. Nếu dùng một trong các channel này, hãy kết hợp email hoặc Pub/Sub làm kênh dự phòng. SMS cũng không nên được dùng đơn lẻ.

### Tạo channel trong Console

1. Mở Monitoring > Alerting.
2. Chọn Edit notification channels hoặc Manage notification channels.
3. Chọn loại channel cần tạo.
4. Nhập thông tin đích và display name.
5. Hoàn tất bước xác thực hoặc cấp quyền của nhà cung cấp nếu được yêu cầu.
6. Dùng Send test notification nếu channel hỗ trợ.
7. Lưu channel và kiểm tra trạng thái.
8. Quay lại alerting policy, refresh danh sách channels và gắn channel vào policy.

### Các lưu ý theo từng channel

**Email**

Nhập một email address cho mỗi channel. Nếu dùng Google Group, cấu hình group chấp nhận thư từ `alerting-noreply@google.com`. Kiểm tra spam/quarantine và quy tắc lọc thư của tổ chức.

**SMS**

Nhập số điện thoại, gửi verification code và xác minh mã. Chỉ chọn số điện thoại đã được xác minh trong policy. SMS có thể không khả dụng tại một số vùng và không được xem là kênh truyền tin đảm bảo.

**Slack**

Đăng nhập vào workspace và cấp quyền cho Cloud Monitoring. Nếu dùng private channel, mời ứng dụng bằng lệnh sau trong Slack:

~~~text
/invite @Google Cloud Monitoring
~~~

Gửi test notification và xác nhận tin nhắn xuất hiện đúng channel.

**PagerDuty**

Tạo hoặc chọn service trong PagerDuty, thêm integration Events API v1 và sao chép integration key vào notification channel của Cloud Monitoring. Monitoring mở alert trong PagerDuty khi alert được tạo. Nếu resolve alert trong PagerDuty trong khi alert của Monitoring vẫn mở, PagerDuty có thể mở lại alert. Không giả định trạng thái đóng đã đồng bộ hoàn toàn giữa hai hệ thống.

**Webhook**

Webhook notification chỉ hỗ trợ public endpoint có thể được dịch vụ thông báo truy cập qua Internet. Với HTTPS, endpoint phải có chứng thư TLS mà dịch vụ có thể xác minh. Có thể dùng Basic Authentication hoặc token trong URL theo hướng dẫn tích hợp. Bảo vệ endpoint, xoay vòng token và không ghi secret vào log. Nếu endpoint chỉ truy cập được trong private network, hãy dùng Pub/Sub rồi đặt subscriber trong mạng phù hợp.

**Pub/Sub**

Khi tạo channel Pub/Sub lần đầu trong project, Cloud Monitoring tạo notification service account theo dạng:

~~~text
service-PROJECT_NUMBER@gcp-sa-monitoring-notification.iam.gserviceaccount.com
~~~

Service account này cần quyền `roles/pubsub.publisher` trên topic. Nên cấp quyền ở topic cụ thể thay vì toàn project nếu có thể. Tạo subscription kiểu pull, push hoặc BigQuery để nhận thông báo. Nếu topic ở project khác, cần bật API và cấu hình IAM ở đúng project.

Ví dụ cấp quyền publish vào một topic:

~~~bash
gcloud pubsub topics add-iam-policy-binding notification-topic \
  --project=PUBSUB_PROJECT_ID \
  --member="serviceAccount:service-PROJECT_NUMBER@gcp-sa-monitoring-notification.iam.gserviceaccount.com" \
  --role="roles/pubsub.publisher"
~~~

Nếu topic có message storage policy hoặc data residency restrictions, Monitoring có thể không publish được do yêu cầu location không tương thích. Kiểm tra lỗi `FAILED_PRECONDITION` và chính sách topic trước khi triển khai.

### Bảo vệ nội dung notification

Notification có thể chứa tên tài nguyên, project, thông tin metric, nhãn, log context và liên kết nội bộ. Vì vậy:

- Không đưa password, API key, access token hoặc dữ liệu cá nhân vào policy documentation.
- Chỉ gửi thông báo tới nhóm và channel có quyền truy cập phù hợp.
- Với webhook, xác thực request và bảo vệ secret.
- Với Pub/Sub, giới hạn subscriber và quyền đọc topic.
- Kiểm tra yêu cầu lưu trữ dữ liệu, retention và compliance của tổ chức.
- Không coi notification là kho lưu bằng chứng lâu dài; giữ log và incident record theo chính sách riêng.

## 6. Uptime checks

Uptime check là phép kiểm tra chủ động: Cloud Monitoring gửi request định kỳ tới endpoint từ nhiều checker locations và đánh giá kết quả. Nó trả lời câu hỏi “endpoint có phản hồi theo tiêu chí đã đặt không?” chứ không chỉ “máy chủ có đang chạy không?”.

Uptime check có thể kiểm tra:

- URL công khai.
- Compute Engine instance.
- App Engine application.
- Kubernetes Service kiểu LoadBalancer.
- Cloud Run revision.
- Một số tài nguyên AWS như EC2 instance và Elastic Load Balancer.

Uptime check sử dụng HTTP GET, HTTP POST, HTTPS hoặc TCP. Nó không tải ảnh, CSS, JavaScript hay chạy JavaScript trên trang. Cấu hình mặc định không có authentication.

### Public uptime check

Public uptime check kiểm tra endpoint có thể truy cập qua Internet. Có thể dùng URL, hostname hoặc địa chỉ IP công khai; với VM hoặc load balancer nằm sau firewall, cần cho phép traffic từ các IP của uptime checker.

Các checker được phân bố ở nhiều vị trí. Một uptime check cần ít nhất ba checkers. Khu vực USA có ba checker riêng tại Oregon, Iowa và Virginia; các vùng Europe, South America và Asia Pacific có một checker mỗi vùng. Chọn Global sẽ dùng tất cả vùng có sẵn.

Nếu chỉ một checker thất bại do mạng tạm thời, policy mặc định không gửi cảnh báo. Khi tạo alert policy từ uptime check, mặc định ít nhất hai vùng phải báo thất bại liên tục ít nhất một phút mới kích hoạt notification.

Public uptime checks không được hỗ trợ bên trong VPC Service Controls perimeter. Nếu endpoint nằm trong mạng riêng hoặc bị giới hạn bởi perimeter, hãy dùng private uptime check.

### Private uptime check

Private uptime check kiểm tra tài nguyên nội bộ như VM hoặc internal load balancer mà không phải mở endpoint ra Internet. Private checks dùng Service Directory để tra cứu địa chỉ IP nội bộ và gửi HTTP, HTTPS hoặc TCP request tới endpoint trong VPC.

Điều kiện chính:

- Cấu hình Service Directory service có private network access.
- Bật các API cần thiết như Cloud Monitoring, Service Directory, Service Networking và Compute Engine theo hướng dẫn.
- Xác định project chứa uptime check, project chứa Service Directory service và metrics scope nếu các tài nguyên nằm ở nhiều project.
- Cấu hình quyền IAM và VPC Service Controls phù hợp.
- Đảm bảo endpoint nội bộ thực sự trả lời đúng request và port.

Private uptime checks có thể hoạt động trong VPC Service Controls perimeter. Chúng không hỗ trợ ICMP pings. Nếu cần kiểm tra endpoint công khai, dùng public check.

### HTTP, HTTPS và TCP

| Giao thức | Điều kiểm tra | Ví dụ |
|---|---|---|
| HTTP | Gửi GET hoặc POST và kiểm tra status/content | `https://api.example.com/health` qua HTTPS hoặc URL HTTP |
| HTTPS | Kiểm tra HTTP response và chứng thư TLS | API gateway hoặc website có chứng thư TLS |
| TCP | Kiểm tra có thể mở kết nối tới port | Cổng dịch vụ TCP, load balancer hoặc endpoint database được phép |

Với HTTP/HTTPS, các redirect được theo tới response cuối cùng rồi mới đánh giá tiêu chí thành công. Mặc định, status code thuộc nhóm 2xx được xem là thành công. Có thể thay đổi status codes được chấp nhận nếu ứng dụng có quy ước khác.

HTTPS check xác minh SSL certificate theo cấu hình. Chứng thư hết hạn, self-signed hoặc sai hostname có thể làm check thất bại. Một chứng thư bị thu hồi không được đánh giá giống như chứng thư không hợp lệ trong mọi trường hợp; hãy kiểm tra hành vi hiện hành của checker. Metric `monitoring.googleapis.com/uptime_check/time_until_ssl_cert_expires` có thể dùng để cảnh báo trước khi chứng thư hết hạn.

Content matching giúp xác minh response có nội dung mong đợi. Ví dụ, endpoint `/health` cần trả về chuỗi `ok`; check chỉ thành công nếu response chứa chuỗi đó theo matcher đã chọn. Nội dung match có giới hạn 1.024 byte. Với TCP check, content matching cần được bật nếu muốn xác minh nội dung response.

### Các tham số quan trọng

| Tham số | Ý nghĩa | Gợi ý |
|---|---|---|
| Check frequency | Khoảng cách giữa các lần chạy | 1, 5, 10 hoặc 15 phút; mặc định 1 phút |
| Checker regions | Vị trí phát request | Chọn ít nhất 3 checker locations; Global dùng tất cả |
| Response timeout | Thời gian chờ response | Đặt phù hợp latency thực tế; tăng lên 30 giây hoặc hơn nếu kiểm tra redirect phức tạp |
| Path | Đường dẫn HTTP/HTTPS | Ưu tiên health endpoint ổn định, nhẹ |
| Port | Cổng kết nối | HTTP mặc định 80, HTTPS mặc định 443; TCP phải chỉ định |
| Authentication | Thông tin xác thực cho HTTP/HTTPS | Basic Auth hoặc Service Agent Authentication qua HTTPS |
| Custom headers | Header tùy chỉnh | Dùng khi endpoint cần header; có thể mask/encrypt giá trị |
| Content matcher | Kiểm tra body response | Chọn chuỗi hoặc matcher phù hợp với response ổn định |

Uptime check có thể mất tới 5 phút để kết quả đầu tiên xuất hiện trong Monitoring sau khi tạo cấu hình. Trong thời gian đó, dashboard có thể hiển thị no data available.

## 7. Tạo uptime check và alert cho endpoint

Ví dụ kiểm tra endpoint HTTPS công khai của một API có health route. Thay `YOUR_PUBLIC_HOST` bằng hostname của ứng dụng đã được cấu hình để phản hồi từ Internet.

### Tạo bằng Google Cloud Console

1. Chọn project lưu uptime check.
2. Mở Monitoring > Uptime checks.
3. Chọn Create Uptime Check.
4. Chọn protocol HTTPS và resource type URL.
5. Nhập hostname và path `/health`.
6. Chọn Global hoặc ít nhất ba checker locations.
7. Xác nhận SSL certificate validation được bật.
8. Chọn response status 2xx và content matching nếu endpoint có response body ổn định.
9. Chọn response timeout phù hợp.
10. Dùng Test để kiểm tra cấu hình trước khi lưu.
11. Bật tùy chọn tạo alerting policy và chọn notification channels.
12. Đặt tên uptime check và tạo.

### Tạo bằng gcloud

Lệnh sau tạo public HTTPS uptime check chạy mỗi phút, kiểm tra path `/health` và xác minh chứng thư TLS:

~~~bash
gcloud monitoring uptime create "api-health-check" \
  --resource-type=uptime-url \
  --resource-labels=host=YOUR_PUBLIC_HOST,project_id=PROJECT_ID \
  --protocol=https \
  --path=/health \
  --period=1 \
  --timeout=10 \
  --validate-ssl \
  --project=PROJECT_ID
~~~

Nếu endpoint yêu cầu HTTP header, có thể thêm `--headers` và bật `--mask-headers` để ẩn giá trị nhạy cảm trong cấu hình. Không đặt secret thật trực tiếp trong command line của shell dùng chung hoặc history không được bảo vệ. Nếu endpoint yêu cầu authentication, cân nhắc Service Agent Authentication bằng OIDC token cho HTTPS hoặc cấu hình Basic Authentication theo chính sách của tổ chức.

Sau khi tạo, liệt kê check để lấy ID:

~~~bash
gcloud monitoring uptime list --project=PROJECT_ID
~~~

ID của check là phần cuối resource name trong cấu hình. Alert policy sử dụng metric `monitoring.googleapis.com/uptime_check/check_passed` và label `check_id` để chọn đúng check.

### Tạo alert cho uptime check

Khi tạo uptime check qua Console, có thể bật tạo alerting policy ngay trong wizard. Mặc định, policy thông báo khi ít nhất hai vùng báo check thất bại liên tục ít nhất một phút.

Nếu tạo policy riêng, có thể dùng metric `monitoring.googleapis.com/uptime_check/check_passed` để theo dõi trạng thái. Giá trị 1 biểu thị check thành công; giá trị 0 biểu thị thất bại. Dùng filter theo `metric.label.check_id` để tránh gom nhầm nhiều uptime checks vào một condition.

Ví dụ filter cho check có ID `api-health-check`:

~~~text
metric.type="monitoring.googleapis.com/uptime_check/check_passed"
AND metric.label.check_id="api-health-check"
AND resource.type="uptime_url"
~~~

Để cảnh báo chứng thư sắp hết hạn, tạo policy riêng dùng metric `monitoring.googleapis.com/uptime_check/time_until_ssl_cert_expires` và đặt threshold theo số ngày còn lại. Policy availability và policy certificate expiry có mục tiêu khác nhau, nên nên có tên, severity và runbook riêng.

## 8. Quy trình điều tra alert và uptime failure

Khi notification tới, người trực nên xác định nhanh alert đang phản ánh lỗi dịch vụ, lỗi telemetry hay lỗi của checker.

### Điều tra alert metric

1. Mở liên kết incident trong notification.
2. Xem policy, condition, severity, thời điểm mở và trạng thái.
3. Xem time series trong Alert details hoặc Metrics Explorer.
4. Xác định monitored resource và label, ví dụ project, zone, instance ID hoặc service.
5. Kiểm tra deployment, traffic, error rate, latency, CPU, memory, disk và dependency gần thời điểm alert.
6. Đối chiếu với log và trace để xác định nguyên nhân.
7. Cập nhật incident, ghi nhận owner và hành động khắc phục.

Nếu biểu đồ không hiển thị điểm dữ liệu gây alert, hãy kiểm tra ingestion delay, alignment period và missing-data behavior. Dữ liệu log-based metric có thể tới trễ hoặc được backfill; vì vậy retest window quá ngắn có thể gây cảnh báo bất thường.

### Điều tra uptime failure

| Kết quả | Nguyên nhân có thể | Việc kiểm tra |
|---|---|---|
| Connection refused | Web server chưa chạy hoặc port sai | Kiểm tra service process, port và listener |
| Name or service not found | Hostname hoặc DNS sai | Kiểm tra DNS record và resolver |
| HTTP 403 | Endpoint yêu cầu quyền hoặc từ chối checker | Kiểm tra auth, IAM và access policy |
| HTTP 404 | Path sai hoặc route không tồn tại | Kiểm tra `/health` và routing |
| HTTP 5xx | Ứng dụng hoặc dependency gặp lỗi | Xem log ứng dụng, backend và load balancer |
| Timeout | Service chậm, firewall chặn hoặc timeout quá ngắn | Kiểm tra latency, firewall và checker IP |
| TLS/SSL error | Chứng thư hết hạn, self-signed hoặc hostname mismatch | Kiểm tra chain, hostname, expiry và cấu hình SSL |
| Chỉ một vùng checker thất bại | Mạng tạm thời hoặc sự cố định tuyến theo vùng | So sánh kết quả từ các vùng khác trước khi kết luận outage toàn cầu |

Nếu endpoint đứng sau firewall, cho phép traffic từ dải IP uptime-check servers theo tài liệu Google. Không mở firewall rộng hơn yêu cầu. Nếu dùng Cloud Run, đảm bảo principal hoặc service agent được dùng cho check có quyền `run.routes.invoke` khi cấu hình yêu cầu.

### Acknowledge, close và snooze

- Acknowledge khi người trực bắt đầu điều tra.
- Close alert sau khi condition không còn được đáp ứng hoặc sau khi đã xác minh và xử lý.
- Snooze policy khi cần tạm dừng thông báo lặp trong một cửa sổ bảo trì hoặc khi đang xử lý sự cố.
- Không mute hoặc snooze để che giấu một lỗi chưa được hiểu rõ.
- Ghi lại thời điểm, nguyên nhân, tác động, hành động và kết quả khôi phục trong incident record.

## 9. Ví dụ thiết kế cho một ứng dụng Cloud Run

Giả sử ứng dụng thương mại điện tử chạy trên Cloud Run, có endpoint `/health` công khai và API phụ thuộc vào Cloud SQL. Một thiết kế cảnh báo có thể gồm:

| Tín hiệu | Policy | Severity | Kênh |
|---|---|---|---|
| Uptime check thất bại ở nhiều vùng | Check không thành công liên tục ít nhất 1 phút | CRITICAL | PagerDuty + email |
| HTTP 5xx tăng | Error rate vượt ngưỡng trong 5 phút | ERROR | PagerDuty + Pub/Sub |
| Request latency cao | P95 latency vượt SLO trong 10 phút | WARNING | Slack + email |
| CPU hoặc instance pressure | Metric workload vượt ngưỡng | WARNING | Slack |
| Cloud SQL connection errors | Số lỗi kết nối tăng liên tục | ERROR | PagerDuty + Pub/Sub |
| TLS certificate sắp hết hạn | Còn dưới 15 ngày | WARNING | Email + ticket |

Thiết kế này tách cảnh báo availability, latency, error rate và certificate expiry. Mỗi policy có owner và runbook riêng. Uptime check giúp xác nhận người dùng có thể truy cập endpoint từ bên ngoài; metric và log giúp giải thích vì sao request thất bại.

Nếu API có endpoint nội bộ chỉ truy cập qua VPC, tạo private uptime check cho endpoint đó. Không dùng public uptime check để kiểm tra một IP nội bộ. Với Cloud Run yêu cầu authentication, dùng service agent authentication qua HTTPS và cấp quyền invoke cần thiết.

## 10. Thực hành kiểm thử và dọn dẹp

Một lab nhỏ giúp xác minh toàn bộ luồng từ dữ liệu đến notification.

### Phần A: Metric alert

1. Dùng một VM lab có metric CPU.
2. Tạo notification channel email hoặc Slack.
3. Tạo policy CPU threshold thấp trong thời gian ngắn chỉ trên VM lab.
4. Quan sát time series và alert state.
5. Xác nhận notification được nhận.
6. Khôi phục threshold về mức vận hành phù hợp hoặc xóa policy lab.

Không tạo tải bất thường trên VM production để kích hoạt cảnh báo.

### Phần B: Uptime check

1. Chọn một endpoint thử nghiệm có public access và health route.
2. Tạo HTTPS uptime check từ ít nhất ba checker locations.
3. Kiểm tra response status và content matcher.
4. Tạo alert policy cho uptime check và gắn channel.
5. Xác nhận notification khi endpoint thử nghiệm không còn phản hồi, nếu có thể thực hiện trong lab.
6. Khôi phục endpoint và xác nhận alert đóng.
7. Xóa uptime check, policy và channel nếu chỉ dùng cho lab.

### Phần C: Pub/Sub

1. Tạo topic và subscription trong project thử nghiệm.
2. Tạo Pub/Sub notification channel.
3. Cấp `roles/pubsub.publisher` cho Monitoring notification service account trên topic.
4. Gắn channel vào policy lab.
5. Gửi test notification hoặc kích hoạt condition trong lab.
6. Xác nhận message đến subscription và kiểm tra payload.
7. Xóa tài nguyên lab sau khi hoàn tất.

## 11. Lỗi cấu hình thường gặp

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Policy không mở alert | Metric filter sai hoặc không có dữ liệu | Kiểm tra metric type, resource type và labels |
| Alert mở quá sớm | Retest window không có hoặc quá ngắn | Chọn retest window phù hợp chu kỳ metric |
| Alert bị lặp nhiều | Nhiều time series vi phạm hoặc policy có nhiều condition | Kiểm tra aggregation, trigger và combiner |
| Alert không đóng | Missing-data behavior hoặc auto-close không phù hợp | Kiểm tra condition state, dữ liệu mới và auto-close |
| Notification không tới email | Group chặn người gửi hoặc mail vào spam | Cho phép `alerting-noreply@google.com` và kiểm tra mail routing |
| SMS không gửi | Số chưa xác minh hoặc khu vực không hỗ trợ | Xác minh số và dùng channel dự phòng |
| Slack channel không nhận tin | App chưa được cài hoặc chưa được mời vào private channel | Kiểm tra OAuth và mời Google Cloud Monitoring app |
| PagerDuty severity không đúng | Mapping mặc định không tương ứng với severity Monitoring | Cấu hình Event Orchestration rules |
| Webhook lỗi kết nối | Endpoint private hoặc TLS certificate không hợp lệ | Dùng public HTTPS endpoint hoặc chuyển sang Pub/Sub |
| Pub/Sub không nhận message | Thiếu Pub/Sub Publisher hoặc sai topic/project | Kiểm tra service account, IAM và subscription |
| Uptime check thất bại nhưng website vẫn mở | Checker không được phép truy cập, path/auth sai hoặc chỉ một vùng lỗi | So sánh checker locations, firewall và response criteria |
| Uptime check không có dữ liệu | Check mới tạo hoặc sai target | Chờ tối đa vài phút và kiểm tra cấu hình |
| Private check không hoạt động | Service Directory chưa bật private network access hoặc thiếu API/IAM | Kiểm tra Service Directory, VPC và metrics scope |
| TLS check thất bại | Certificate hết hạn, self-signed hoặc mismatch hostname | Kiểm tra certificate chain và DNS name |

## 12. Thực hành tốt khi thiết kế alerting

- **Cảnh báo theo tác động người dùng:** ưu tiên availability, latency, error rate và saturation thay vì chỉ cảnh báo tài nguyên cao.
- **Gắn severity theo hành động:** CRITICAL cần đánh thức on-call; WARNING có thể đưa vào kênh nhóm hoặc ticket.
- **Viết documentation có thể hành động:** nêu symptom, dashboard, log query, owner và runbook.
- **Dùng retest window có chủ đích:** cân bằng tốc độ phát hiện và false positive.
- **Giám sát dữ liệu telemetry:** một policy cần có dữ liệu đầu vào; theo dõi riêng khi metric hoặc log ngừng đến.
- **Tách alert theo service:** tránh policy quá rộng và khó xác định owner.
- **Dùng channel dự phòng:** kết hợp kênh có cơ chế giao nhận khác nhau.
- **Kiểm thử channel:** gửi test notification và xác nhận người trực thực sự nhận được.
- **Bảo vệ notification payload:** không đưa secret hoặc thông tin nhạy cảm vào nội dung thông báo.
- **Kiểm tra public/private boundary:** chỉ dùng public uptime check cho endpoint công khai; dùng private check cho tài nguyên nội bộ.
- **Không biến mọi cảnh báo thành tự động remediation:** bắt đầu với enrichment, ticket và thông báo; chỉ tự động thay đổi hạ tầng khi đã có guardrail, phê duyệt và rollback.
- **Rà soát định kỳ:** loại bỏ policy không còn dùng, channel hỏng, người nhận cũ và ngưỡng không còn phù hợp.

## Kết luận

Alerting policies biến metric, log và kết quả truy vấn thành điều kiện phát hiện sự cố. Notification channels đưa alert tới người trực hoặc hệ thống xử lý. Uptime checks chủ động xác minh endpoint có phản hồi từ nhiều vị trí và có thể kết hợp với alert policy để cảnh báo khi dịch vụ mất khả năng truy cập.

Một hệ thống cảnh báo hữu ích cần có dữ liệu đáng tin cậy, điều kiện phù hợp với hành vi của ứng dụng, kênh thông báo có dự phòng và runbook rõ ràng. Hãy bắt đầu từ các chỉ số ảnh hưởng trực tiếp tới người dùng, kiểm thử toàn bộ luồng notification trong môi trường riêng và thường xuyên rà soát để mỗi alert đều có người chịu trách nhiệm.

## Tài liệu tham khảo

- [Cloud Monitoring alerting overview](https://cloud.google.com/monitoring/alerts)
- [Create metric-threshold alerting policies](https://cloud.google.com/monitoring/alerts/using-alerting-ui)
- [Create alerting policies by using the API](https://cloud.google.com/monitoring/alerts/policies-in-api)
- [Sample alerting policies in JSON](https://cloud.google.com/monitoring/alerts/policies-in-json)
- [Create and manage notification channels](https://cloud.google.com/monitoring/support/notification-options)
- [Control access with IAM](https://cloud.google.com/monitoring/access-control)
- [Create public uptime checks](https://cloud.google.com/monitoring/uptime-checks)
- [Create private uptime checks](https://cloud.google.com/monitoring/uptime-checks/private-checks)
- [gcloud monitoring uptime create](https://cloud.google.com/sdk/gcloud/reference/monitoring/uptime/create)
- [Troubleshoot alerting policies](https://cloud.google.com/monitoring/alerts/troubleshooting-alerts)

