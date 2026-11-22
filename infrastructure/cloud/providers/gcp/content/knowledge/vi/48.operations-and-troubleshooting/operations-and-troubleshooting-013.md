# Theo dõi Service Health và làm việc với Google Cloud Support

Khi API trên Cloud Run tăng lỗi 5xx, database Cloud SQL mất kết nối hoặc nhiều VM không tạo mới được, đội vận hành phải trả lời hai câu hỏi song song: **dịch vụ của chính mình đang bị ảnh hưởng ở mức nào?** và **có sự cố hạ tầng Google Cloud liên quan hay không?** Google Cloud Service Health, Personalized Service Health, Cloud Monitoring và Cloud Customer Care cung cấp những góc nhìn khác nhau để trả lời câu hỏi đó. Dùng đúng nguồn, đúng mức ưu tiên và đúng quy trình trao đổi với Support giúp giảm thời gian phát hiện, giảm tác động tới người dùng và tránh quy kết sai nguyên nhân.

Bài học thuộc chương **Vận hành và xử lý sự cố** của module **CLOUD_PROVIDERS_GCP**. Trong bối cảnh vận hành Google Cloud từ project, IAM, VPC đến Compute Engine, GKE, Cloud Run, lưu trữ và cơ sở dữ liệu, người học sẽ kết nối dữ liệu Service Health với log, metric, trace, SLO, cơ chế khắc phục và quy trình hỗ trợ của Google. Những ví dụ dùng workload Java/Spring Boot đa tầng nhưng nguyên tắc cũng áp dụng cho các ứng dụng khác.

Sau bài học, người học có thể:

- Phân biệt public Service Health, Personalized Service Health, trạng thái tài nguyên trong Cloud Monitoring và support case.
- Tra cứu sự kiện theo project, product, region, thời gian, relevance, event state và lịch sử cập nhật.
- Cấu hình IAM tối thiểu để đọc Service Health và quản lý support case.
- Tạo cảnh báo chủ động bằng Service Health logs và Cloud Monitoring notification channels.
- Triage sự cố theo tác động người dùng, kiểm chứng giả thuyết lỗi hạ tầng và lựa chọn mitigation.
- Thu thập thông tin để tạo case Customer Care đầy đủ, chọn mức ưu tiên phù hợp và theo dõi phản hồi.
- Phân biệt tăng mức ưu tiên với escalation, biết khi nào cần bàn giao 24/7 và khi nào cần tập trung sửa lỗi nội bộ.
- Xây runbook, timeline, handoff, incident review và diễn tập khi dashboard/service API không khả dụng.

## 1. Bốn lớp thông tin cần kết hợp

| Nguồn | Câu hỏi được trả lời | Giới hạn quan trọng |
|---|---|---|
| **Google Cloud Service Health** công khai | Có sự cố Google Cloud phạm vi rộng đã được công bố hay không? | Không phải danh sách đầy đủ mọi sự cố ảnh hưởng riêng một project |
| **Personalized Service Health (PSH)** | Sự kiện Google Cloud nào có thể liên quan đến project/organization của mình? | Relevance là tín hiệu hỗ trợ triage, không thay phép đo tác động thực tế |
| **Cloud Monitoring, Logging, Trace và SLO** | Ứng dụng và người dùng của mình đang chịu tác động gì? | Có thể phát hiện triệu chứng nhưng không tự chứng minh nguyên nhân thuộc Google |
| **Cloud Customer Care/Support case** | Làm thế nào gửi bằng chứng, yêu cầu hỗ trợ và theo dõi phối hợp xử lý? | Phụ thuộc support offering, quyền IAM và mức ảnh hưởng/priority |

Một SRE không nên chỉ mở public status page và kết luận “Google Cloud bình thường” nếu không có incident lớn. Sự cố khu vực hẹp hoặc chỉ liên quan một nhóm project có thể hiển thị trong Personalized Service Health; đồng thời, cũng có các lỗi do cấu hình của khách hàng mà Service Health không ghi nhận.

### 1.1. Public Service Health

Trang công khai: **https://status.cloud.google.com/**. Đây là điểm kiểm tra nhanh các sự cố Google Cloud phạm vi rộng, sản phẩm và location liên quan. Có thể xem product/region, lịch sử các sự kiện được công bố và kênh RSS phục vụ fallback.

Đặc điểm:

- Truy cập không cần quyền IAM của project.
- Hữu ích khi Google Cloud Console/IAM gặp sự cố diện rộng.
- Thông tin có thể được phát hành và cập nhật theo tiến độ điều tra.
- Không đảm bảo mỗi lỗi riêng lẻ, mọi project hay mọi khoảng thời gian đều có incident công khai.
- Nên lưu incident URL/event ID và thời điểm kiểm tra vào hồ sơ sự cố.

### 1.2. Personalized Service Health

Personalized Service Health cung cấp danh sách sự kiện theo project hoặc organization, tập trung vào mức liên quan, product và location. Giao diện, Service Health API và các bản ghi Cloud Logging có thể phục vụ dashboard nội bộ, alert và quy trình phản ứng.

PSH là kênh chính để theo dõi sự kiện Google Cloud có liên quan đến môi trường của tổ chức; public status page là đường kiểm tra bổ sung và fallback.

### 1.3. Tín hiệu ứng dụng không thay thế được

Ứng dụng Spring Boot có thể trả 500 vì connection pool cạn dù Cloud SQL healthy. Ngược lại, Cloud SQL có sự cố nhưng API vẫn duy trì thành công nhờ caching hoặc failover. Cần có cả:

- Request rate, error rate, p95/p99 latency.
- Cloud Run revision/instance errors, GKE pod restarts, Compute Engine instance health.
- Cloud SQL connection errors, query latency, replication lag hoặc database status.
- Cloud Storage/Pub/Sub error và backlog nếu workload phụ thuộc.
- Log/trace có correlation ID, thời điểm và region.
- Business SLI như đơn hàng thất bại, giao dịch chậm hoặc dữ liệu xử lý bị tồn đọng.

**Định nghĩa incident nội bộ dựa trên tác động/SLO**, không chỉ dựa vào việc Google có đăng sự kiện hay chưa.

## 2. Hiểu một Service Health event

Sự kiện Service Health phản ánh disruption đối với một sản phẩm Google Cloud. Nội dung thường có:

| Thành phần | Cách sử dụng |
|---|---|
| Event ID | Khóa tham chiếu khi ghi incident timeline và liên hệ Support |
| Title/description | Tóm tắt triệu chứng đã được Google công bố |
| Category | Phân loại loại sự kiện theo API hiện hành, ví dụ incident |
| Event state | Trạng thái tổng thể, thường **Active** hoặc **Closed** |
| Product(s) | Dịch vụ Google Cloud có thể bị ảnh hưởng |
| Location(s) | Region/zone hoặc phạm vi liên quan |
| Relevance | Mức độ liên quan tới project theo dữ liệu Google có |
| Start/update/end time | Mốc bắt đầu, cập nhật, khắc phục theo timeline |
| Workaround/diagnosis | Giải thích hoặc giải pháp tạm do Google công bố nếu có |
| Full history/report | Chuỗi cập nhật và incident report nếu được phát hành |

Không phải event nào cũng lập tức có root cause hoặc ước tính phục hồi. Khi chưa có dữ kiện, ghi **“Google đang điều tra/chưa công bố”**, không suy diễn một nguyên nhân kỹ thuật.

### 2.1. Event state và granular status

- **Active:** sự kiện tổng thể vẫn được theo dõi, có thể còn một hoặc nhiều product/location chưa phục hồi.
- **Closed:** sự kiện tổng thể đã kết thúc theo đánh giá của Google hoặc được gộp vào event khác.
- **Affected/Resolved** ở cấp product-location: có thể thể hiện từng khu vực đã phục hồi trong khi event tổng thể còn Active.

Nếu Cloud SQL ở region A đã được đánh dấu Resolved nhưng một region B vẫn Affected, không tự kết luận mọi region đều đã phục hồi. Ngược lại, event đã Closed cũng chưa đảm bảo ứng dụng tự động phục hồi các hàng đợi, connection pool, cache hoặc transaction bị lỗi trước đó.

### 2.2. Relevance không phải bằng chứng tuyệt đối

Relevance thể hiện mức liên quan ước tính giữa sự kiện và project; tài liệu/biểu diễn có thể dùng các giá trị như **IMPACTED** hoặc **RELATED**. Khi gặp event:

1. Kiểm tra project nào đang sử dụng product/location liên quan.
2. Đối chiếu thời gian sự kiện với thời điểm SLI giảm.
3. Đối chiếu mã lỗi và triệu chứng thực.
4. Kiểm tra networking, IAM, quota, deployment và dependency riêng.
5. Xem event có workaround hay cập nhật mới không.

Một event RELATED không có nghĩa 100% resource của project bị lỗi. Không có event phù hợp cũng không chứng minh lỗi chắc chắn do code của mình.

### 2.3. Thời gian và múi giờ

Ghi thời điểm theo **ISO 8601 có UTC offset**, ưu tiên UTC khi cộng tác nhiều múi giờ. Ví dụ: `2026-11-19T08:15:00Z` hoặc `2026-11-19T15:15:00+07:00`. Phân biệt:

- Thời điểm người dùng bắt đầu bị ảnh hưởng.
- Thời điểm monitoring phát cảnh báo.
- Thời gian sự kiện Google Cloud được công bố.
- Thời điểm mitigation triển khai và SLI phục hồi.
- Thời điểm Google đóng sự kiện/công bố incident report.

Không coi thời gian Google công bố là lúc sự cố bắt đầu ở ứng dụng mình.

## 3. Truy cập Service Health theo project

### 3.1. Điều kiện và IAM

Với project có billing và quyền phù hợp, để xem Service Health dashboard/API, nhóm vận hành có thể được cấp:

| Mục đích | Role/permission |
|---|---|
| Xem project events | `roles/servicehealth.viewer` |
| Đọc sự kiện qua API | `servicehealth.events.list` và `servicehealth.events.get`, cùng quyền location cần thiết |
| Quản trị Service Health | `roles/servicehealth.admin` khi thực sự cần |
| Đọc log Service Health | Quyền Cloud Logging thích hợp |
| Tạo log-based alert và notification channel | Các role Cloud Monitoring/Logging phù hợp với policy/channel |

Role Viewer của Personalized Service Health là read-only. **Không cấp Project Owner/Editor chỉ để đọc tình trạng dịch vụ.** Nếu chỉ cần xem sự kiện nhưng không muốn người dùng xem tên resource bị ảnh hưởng ở tính năng Preview, có thể dùng custom role loại bỏ quyền đọc resource-level impacts theo tài liệu Google.

Ví dụ IAM binding do quản trị viên thực hiện (thay placeholder):

~~~bash
gcloud projects add-iam-policy-binding PROJECT_ID \
  --member="group:oncall@example.com" \
  --role="roles/servicehealth.viewer"
~~~

Ví dụ không phải lệnh chạy mặc định trong môi trường thật; quản trị viên phải kiểm tra danh tính nhóm, scope và chính sách IAM trước khi cấp.

### 3.2. Xem trên Console

1. Mở Google Cloud Console, chọn **đúng project** đang chịu ảnh hưởng.
2. Vào **Tools → Service Health**.
3. Xem danh sách event Active và Closed liên quan đến project.
4. Lọc/tập trung vào product, location và relevance đang điều tra.
5. Mở event: đọc Overview, Full Incident History, các mốc start/update/end, workaround và trạng thái từng location.
6. Nếu có incident report sau sự cố, xem nguyên nhân/biện pháp phòng ngừa được công bố.
7. Lưu event ID, URL và mốc thời gian trong incident nội bộ.

Với organization nhiều project, cần quan sát cả đường phụ thuộc của workload, không chỉ project chứa Cloud Run: database, shared VPC, networking và data platform có thể nằm ở project khác.

### 3.3. Dùng Service Health API

Service Health API cho phép liệt kê/get sự kiện theo project hoặc organization và dùng thông tin có cấu trúc cho hệ thống vận hành. Cần:

- Bật **Service Health API** ở project dùng để truy vấn theo hướng dẫn.
- Danh tính có quyền `roles/servicehealth.viewer` hoặc custom role tương đương.
- Trong một số ngữ cảnh API, cần quyền gọi dịch vụ và cấu hình billing/project theo tài liệu.
- Xử lý pagination, lọc, backoff khi gọi API.
- Giữ event ID và version/update time để tránh tạo nhiều incident cho cùng sự kiện.

Tham khảo phương thức API/CLI trực tiếp ở tài liệu chính thức, vì surface và field có thể thay đổi theo phiên bản v1/v1beta. Tính năng tra cứu impacted resources ở cấp resource có thể thuộc **Preview**, nên không được coi là đầy đủ cho mọi sản phẩm.

## 4. Theo dõi Service Health chủ động bằng Cloud Logging

Việc đợi SRE đăng nhập Console mới xem tình trạng cloud làm tăng thời gian phát hiện. Personalized Service Health có thể phát sinh log khi event được tạo hoặc thay đổi và tích hợp Cloud Monitoring log-based alerts.

### 4.1. Đường đi cảnh báo

~~~mermaid
flowchart LR
    G[Google Cloud service event] --> PSH[Personalized Service Health]
    PSH --> L[Cloud Logging EventLog]
    L --> AP[Cloud Monitoring alert policy]
    AP --> CH[Notification channel]
    CH --> OC[On-call / ticket / incident]
    OC --> TRI[Triage impact + mitigation]
~~~

Notification channel có thể là email, Slack, PagerDuty, webhook, Pub/Sub hoặc kênh được Cloud Monitoring hỗ trợ theo cấu hình tổ chức. Khi alert chạy, Monitoring tạo một incident của **cảnh báo Monitoring**, khác với **Google Service Health event** và khác với **Cloud Support case**; cần liên kết IDs thay vì nhầm chúng là một bản ghi.

### 4.2. Tra cứu log

Service Health logs dùng loại payload:

~~~text
type.googleapis.com/google.cloud.servicehealth.logging.v1.EventLog
~~~

Log name trong project có cấu trúc tương tự:

~~~text
projects/PROJECT_ID/logs/servicehealth.googleapis.com%2Factivity
~~~

Ví dụ bộ lọc Logs Explorer:

~~~text
logName="projects/PROJECT_ID/logs/servicehealth.googleapis.com%2Factivity"
jsonPayload.category="INCIDENT"
jsonPayload.state="ACTIVE"
jsonPayload.relevance=("IMPACTED" OR "RELATED")
~~~

Thay PROJECT_ID; kiểm tra log thực có field/value phù hợp trước khi lưu alert. Nếu filter quá chặt, một event được cập nhật có thể không đi qua chính sách. Nếu quá rộng, nhóm trực sẽ bị spam khi nhiều dịch vụ không liên quan có sự kiện.

### 4.3. Thiết kế alert không gây nhiễu

Nên cấu hình alert theo các lớp:

| Loại cảnh báo | Điều kiện ví dụ | Kênh đề xuất |
|---|---|---|
| Google event quan trọng | Event mới của Cloud SQL/GKE/Cloud Run tại region đang dùng, relevance cao | On-call |
| Event update | Workaround/impact/state thay đổi | Cập nhật incident hiện tại |
| Sự kiện không khẩn | Product không nằm trên request path | Slack/channel theo dõi |
| Ứng dụng vi phạm SLO | Error rate/latency/burn rate vượt ngưỡng | Pager trực ngay, không chờ Service Health |
| Service Health data flow lỗi | Không nhận log/API khi đáng lẽ phải có | Health check cho pipeline cảnh báo |

**Không chỉ page dựa trên một Service Health event.** Với tác động thực, ưu tiên cảnh báo SLO và dùng event làm ngữ cảnh. Đồng thời, sự kiện liên quan hệ thống quan trọng có thể đáng page ngay dù SLO chưa giảm, ví dụ rủi ro failover và sắp cạn năng lực dự phòng.

### 4.4. Kiểm thử alert

Thực hiện ở project thử nghiệm hoặc với cấu hình cảnh báo có thể phân biệt test và production:

1. Tạo notification channel thử nghiệm.
2. Đặt policy lọc Service Health EventLog.
3. Sử dụng quy trình test notification/log-based alert được Google hướng dẫn.
4. Kiểm tra notification thực đến đúng người/kênh.
5. Đối chiếu link event và project trong thông báo.
6. Xác nhận event update không tạo duplicate ticket không kiểm soát.
7. Ghi lại cách tắt test alert và cleanup cấu hình test.

Không tự giả mạo incident khẩn trên project production để thử pager. Với kiểm thử end-to-end, dùng một luồng test được nhóm trực phê duyệt để tránh incident giả.

## 5. Kế hoạch dự phòng khi chính Service Health bị ảnh hưởng

Các hệ thống theo dõi cũng phụ thuộc Google Cloud IAM, Console, Logging và API. Trong sự cố diện rộng, người vận hành có thể không đăng nhập được PSH hoặc cảnh báo có thể bị trễ.

Thiết lập đường dự phòng:

1. Tra cứu trang công khai **https://status.cloud.google.com/** từ thiết bị/network độc lập.
2. Xem các kênh công khai bổ sung như RSS nếu tổ chức đã tích hợp.
3. Giữ runbook và danh bạ on-call ngoài hạ tầng đang hỏng (theo chính sách bảo mật).
4. Dùng telemetry hoặc synthetic probes từ một failure domain khác khi có thể.
5. Kiểm tra các hệ thống ứng dụng và dependency; không trì hoãn mitigation chỉ vì trang tình trạng không tải.
6. Khi PSH phục hồi, đối chiếu lịch sử event và hoàn thiện incident timeline.

Google có **Status API** của Service Health để kiểm tra trạng thái tính năng; hệ thống tự động có thể sử dụng nó kết hợp fallback public status/RSS. Xác minh khả năng truy cập, phạm vi báo cáo và chính sách rate-limit trước khi dùng cho mission-critical automation.

## 6. Triage: xác nhận tác động thực trước khi kết luận nguyên nhân

Mục đích của triage là xác định mức ảnh hưởng, ranh giới sự cố và hành động an toàn để giảm tác động, không phải lập tức tìm ai có lỗi.

### 6.1. Quy trình 10 bước

1. **Xác nhận:** cảnh báo có thật hay false positive? Có request người dùng lỗi không?
2. **Phân loại mức ảnh hưởng:** số khách hàng, chức năng, doanh thu, tính toàn vẹn dữ liệu, mức vi phạm SLO.
3. **Xác định phạm vi:** project, region/zone, product, revision, cluster, database instance, traffic route.
4. **Lập timeline:** thời gian bắt đầu, deploy/config change mới nhất, spike, quota, network events.
5. **Kiểm tra PSH/public status:** có event theo product/location trùng triệu chứng không?
6. **Đối chiếu log/metric/trace:** tìm lỗi thực như timeout, connection refused, 429, 5xx, dependency latency.
7. **Kiểm tra thay đổi do mình thực hiện:** rollout, firewall, IAM, schema migration, credential rotation.
8. **Mitigate:** rollback revision, giảm tải, failover hoặc degrade có kiểm soát nếu runbook cho phép.
9. **Quyết định support:** sự cố có cần Google điều tra hay hỗ trợ tính năng/giới hạn?
10. **Duy trì nhịp cập nhật:** incident commander, tình trạng xử lý, ETA nếu có bằng chứng, người chịu trách nhiệm.

### 6.2. Bảng phân biệt lỗi nền tảng và lỗi cấu hình

| Triệu chứng | Có thể do Google Cloud | Có thể do ứng dụng/cấu hình | Cần kiểm tra |
|---|---|---|---|
| Cloud Run 503 tăng | Regional platform disruption | Startup chậm, max instances, CPU/memory, downstream timeout | Cloud Run request logs, revision, PSH, DB |
| Cloud SQL connect timeout | Cloud SQL/network region incident | IP/firewall/connector, pool exhausted, instance unavailable | Cloud SQL metrics, VPC logs, PSH |
| GKE Pods Pending | Compute capacity/quota issue | Requests/limits, taints, IP range, node policy | Scheduler events, nodes, Compute quota |
| Pub/Sub backlog tăng | Delivery/region disruption | Consumer lỗi, ack deadline, quota, retry storm | Subscription metrics, consumer logs, PSH |
| GCS 403 | IAM/platform authorization issue | Principal thiếu quyền, org policy, token sai | Principal, resource IAM, audit logs |
| Nhiều project cùng 5xx | Shared regional failure | Shared library/config, DNS, release chung | So sánh control group, network, PSH |

Đừng tắt IAM kiểm soát, mở firewall toàn mạng hoặc để public endpoint chỉ vì chưa xác định được nguyên nhân. Mitigation phải nằm trong phạm vi thay đổi được phê duyệt và có rollback.

### 6.3. Tương quan không đồng nghĩa nguyên nhân

Nếu event Google Cloud bắt đầu cùng thời điểm latency tăng, có thể có liên quan nhưng chưa đủ kết luận. Kiểm tra:

- Error message/HTTP status/trace match triệu chứng được công bố?
- Chỉ region/product liên quan mới lỗi hay cả nơi khác?
- Không có deploy lớn/quota exhaustion đúng thời điểm?
- SLI có cải thiện sau workaround hoặc khi event Resolved?
- Có tài liệu hoặc phản hồi Support xác nhận tác động cụ thể?

Trong incident report, dùng ngôn ngữ phân biệt **observed**, **suspected** và **confirmed**. Không viết “Google gây outage” khi chỉ có phỏng đoán.

## 7. Mitigation và quyết định kỹ thuật

Service Health có thể công bố workaround, nhưng đội SRE vẫn phải đánh giá rủi ro của cách áp dụng cho workload thật.

| Workload | Phương án mitigation | Rủi ro/điều kiện |
|---|---|---|
| Cloud Run API | Rollback revision, chuyển traffic, tăng min instances có kiểm soát | Không hiệu quả nếu dependency ở cùng region đang lỗi |
| Cloud SQL | Chuyển read traffic, kích hoạt DR/failover theo runbook | Replica có lag, single-writer, RPO, DNS và app reconnection |
| GKE | Dồn workload sang zone/region khác khi còn capacity | Quota, cluster/namespace config, network dependency |
| Pub/Sub | Giảm producer rate, tăng consumer sau phục hồi, giữ backlog | Retention, duplicate, DLQ, idempotency |
| Storage | Dùng backup/replica đã thiết kế | Consistency, object version và residency |
| Java/Spring Boot | Circuit breaker, bounded retry, degrade non-critical features | Retry storm, mất trạng thái, dữ liệu chưa đồng bộ |

**Không thực hiện failover database chỉ vì public status page hiển thị vấn đề.** Xác nhận ngưỡng SLO, tình trạng replica, RPO/RTO, đường quay về và thẩm quyền ra quyết định.

### 7.1. Giảm retry storm

Khi backend timeout, các client Java có thể retry nhiều lần, làm tình trạng nặng hơn. Thiết kế:

- Timeout ngắn nhưng hợp lý theo request budget.
- Exponential backoff với jitter.
- Giới hạn số lần retry và tổng deadline.
- Circuit breaker/bulkhead để bảo vệ thread/connection pools.
- Idempotency key cho thao tác tạo/thanh toán khi retry.
- Queue/backpressure thay cho tăng traffic vô hạn.

### 7.2. Quy trình ra quyết định

Mỗi phương án nên ghi: **tác động sẽ giảm**, **nguy cơ mất dữ liệu/gián đoạn**, **chi phí vận hành**, **rollback path**, **người duyệt** và **tín hiệu để dừng**. Nếu chưa đủ dữ liệu, chọn bước giảm rủi ro thấp trước, song song mở case nếu cần thông tin Google.

## 8. Cloud Customer Care: vai trò và gói hỗ trợ

Google Cloud Customer Care cung cấp kênh hỗ trợ billing và kỹ thuật theo gói support được tổ chức sử dụng. Quyền truy cập case không đồng nghĩa quyền thay đổi tài nguyên production; đây là các role riêng.

### 8.1. Các loại hỗ trợ

| Gói | Phạm vi điển hình | Cần biết |
|---|---|---|
| Basic Support | Hỗ trợ billing và tài nguyên self-service/community theo chính sách | Không giả định có case technical support trả lời theo SLA |
| Standard Support | Technical support theo phạm vi/giờ làm việc được quy định | Phù hợp ứng dụng chưa cần hỗ trợ sự cố 24/7 ở mọi priority |
| Enhanced Support | Technical support và hỗ trợ ưu tiên cao hơn, một số priority 24/7 theo ngôn ngữ | Có thể dùng escalation và các tiện ích bổ sung |
| Premium Support | Hỗ trợ cho workload quan trọng, TAM và quy trình phối hợp sâu hơn theo hợp đồng | Có thể có follow-the-sun và dịch vụ bổ sung theo điều khoản |

Gói, ngôn ngữ, khu vực, giờ làm việc và thời gian phản hồi cam kết thay đổi theo điều khoản dịch vụ. Không hard-code “P1 chắc chắn được trả lời sau 15 phút” cho mọi tài khoản. Kiểm tra **Technical Support Services Guidelines** và trạng thái support offering thực tế.

### 8.2. IAM cho case

| Mục đích | Role |
|---|---|
| Xem support cases | `roles/cloudsupport.techSupportViewer` |
| Tạo/cập nhật/quản lý support cases | `roles/cloudsupport.techSupportEditor` |
| Quản lý support account và cài đặt chia sẻ | `roles/cloudsupport.admin` khi thật sự cần |

Roles có thể cấp trên organization, folder hoặc project theo phạm vi hỗ trợ. Nếu on-call chỉ cần đọc trường hợp đang mở, không cấp Editor. Đội trưởng ca trực và support liaison có thể có quyền quản lý ở project sản xuất, nhưng việc cấp rộng toàn organization phải được xét kỹ.

### 8.3. Có nên mở case khi đã thấy Google incident?

Có thể **không cần mở case mới** nếu công bố đã nêu rõ triệu chứng, phạm vi phù hợp, đội SRE đã có workaround và không cần câu trả lời riêng. Tuy nhiên, nên cân nhắc case nếu:

- Workload có business impact lớn, cần điều tra ảnh hưởng riêng.
- Triệu chứng khác hoặc nghiêm trọng hơn thông tin đã công bố.
- Cần xác nhận workaround/ETA hoặc hỗ trợ recovery.
- Có rủi ro mất dữ liệu và cần phối hợp điều tra.
- Incident chưa được công bố hoặc không thấy event phù hợp.

Nếu mở case cho known issue, hãy **liên kết case với known issue/event** nếu giao diện hỗ trợ và trình bày khác biệt cụ thể; tránh tạo nhiều case trùng nội dung cho cùng một sự cố.

## 9. Mức ưu tiên case: P1, P2, P3, P4

Mức ưu tiên Google Support là thước đo **tác động kinh doanh và tính khẩn cấp**, không nhất thiết trùng severity SEV1/SEV2 nội bộ hoặc severity của Cloud Monitoring alert.

| Priority trong Console | Mức tác động tham khảo | Ví dụ |
|---|---|---|
| **P1 — Critical** | Production không sử dụng được hoặc ảnh hưởng nghiêm trọng, không có workaround nhanh, cần xử lý ngay | Nhiều thanh toán thất bại, rủi ro dữ liệu quan trọng |
| **P2 — High** | Production suy giảm rõ, có thể có workaround giảm tác động | Một region bị chậm/lỗi, đã chuyển bớt traffic |
| **P3 — Medium** | Phạm vi hạn chế, ít/không tác động trực tiếp người dùng | Lỗi intermittent ở môi trường phát triển, nghi vấn cấu hình |
| **P4 — Low** | Câu hỏi kỹ thuật hoặc vấn đề nhỏ, dịch vụ vẫn dùng tốt | Tư vấn triển khai, tối ưu cấu hình |

Trong Cloud Support API có thể xuất hiện thêm giá trị enum ưu tiên khác tùy phiên bản/gói, vì vậy không suy từ API enum rằng tất cả khách hàng có quyền chọn mọi mức trong Console. Phần trên theo cách phân loại P1–P4 của quy trình Customer Care thông thường.

### 9.1. Chọn đúng mức theo bằng chứng

Đội trực nên ghi:

- Số lượng người dùng/đơn hàng/transaction bị ảnh hưởng.
- Chức năng production bị mất hoặc suy giảm.
- Phần trăm lỗi và so sánh SLO.
- Mất dữ liệu, data corruption hoặc rủi ro integrity.
- Có workaround không; cần bao lâu để triển khai.
- Tại sao cần hỗ trợ ngay thay vì ở giờ làm việc tiếp theo.

Không nâng ưu tiên chỉ để yêu cầu câu trả lời nhanh cho vấn đề không khẩn. Khi tác động production thay đổi, **cập nhật priority của case hiện có** và ghi lý do.

### 9.2. P1 và nghĩa vụ phối hợp

P1 thường yêu cầu mức hợp tác cao từ phía khách hàng: người có thẩm quyền và kỹ sư liên quan tham gia troubleshooting bridge, cung cấp log/timeline, trả lời câu hỏi trong suốt thời gian xử lý. Hãy bố trí người trực và người bàn giao trước khi nâng P1; không mở P1 rồi rời hệ thống nhiều giờ.

Thời gian phản hồi ban đầu là **mục tiêu hỗ trợ**, không phải thời hạn Google cam kết sửa xong nguyên nhân. SLA vận hành ứng dụng của khách hàng và mục tiêu phản hồi Customer Care là hai khái niệm khác nhau.

## 10. Chuẩn bị hồ sơ kỹ thuật trước khi mở case

Một case tốt giúp Support không phải hỏi đi hỏi lại những thông tin cơ bản. Không cần chờ biết root cause mới mở case P1, nhưng phải có mức tác động và các thông tin tối thiểu.

### 10.1. Checklist bằng chứng

| Nhóm | Thông tin hữu ích |
|---|---|
| Business impact | Số người dùng lỗi, doanh thu/hành động bị chặn, SLO breach |
| Timestamp | Bắt đầu/kết thúc, UTC ISO 8601, recurrence, duration |
| Environment | Organization/project ID, số project, region/zone, product/version |
| Resource identifiers | Cloud Run service/revision, Cloud SQL instance, GKE cluster, VM name, Pub/Sub subscription |
| Symptoms | HTTP/gRPC status, error code, message, latency, frequency |
| Reproduction | Bước tái hiện tối thiểu, expected vs actual |
| Recent changes | Deploy, config, IAM, quota, schema, network, rotation |
| Diagnostics | Cloud Logging query, Monitoring chart URL, trace ID, API request ID |
| Actions attempted | Mitigation, rollback, restart, kết quả và tác động |
| Service Health | Event ID/link, relevance, product/location |
| Request to Google | Câu hỏi cụ thể, xác nhận scope, diagnosis, workaround, ETA hoặc next step |

Không cần đính kèm toàn bộ log nếu 10 dòng đã tái hiện được vấn đề. Chọn đúng khung thời gian và dữ liệu đủ để điều tra, giữ lại bản gốc trong hệ thống log theo retention policy.

### 10.2. Bảo mật dữ liệu gửi Support

Được phép chia sẻ những gì theo chính sách nội bộ và hợp đồng hỗ trợ. Trước khi gửi:

- Xóa hoặc che access token, API key, secret, private key, password.
- Tránh gửi dữ liệu cá nhân/tài chính chưa được phê duyệt.
- Nếu cần ảnh hoặc dữ liệu nhạy cảm, dùng kênh bảo mật được Google và tổ chức hướng dẫn.
- Không dán service account JSON key vào mô tả hoặc file đính kèm.
- Dùng test data và tài nguyên test để tái hiện nếu có thể.
- Giới hạn quyền xem case cho nhóm có nhu cầu thực.

Google có thể yêu cầu log hoặc diagnostic cụ thể; luôn đánh giá data classification và tối thiểu hóa dữ liệu trước khi cung cấp.

## 11. Tạo và theo dõi case trong Google Cloud Console

### 11.1. Tạo case

1. Vào **Support → Cases** trong Google Cloud Console.
2. Chọn đúng **project hoặc organization** quản lý trường hợp.
3. Xem **Known issues** và tìm case trùng đang mở.
4. Chọn **Get help**, hoặc công cụ tạo case đang được Console hỗ trợ.
5. Chọn product và tính năng cụ thể, mô tả expected/actual, lỗi quan sát được.
6. Chọn priority theo business impact; đặt support channel được offering cho phép.
7. Gửi case; lưu case ID và link vào incident nội bộ.
8. Theo dõi phản hồi, cung cấp thêm bằng chứng, thực hiện workaround khi an toàn.

Giao diện có thể thay đổi theo gói và phiên bản Console. Bước chọn ngôn ngữ/kênh chat/phone/email phụ thuộc offering; không giả định mọi account có tất cả.

### 11.2. Trạng thái case

Support case có trạng thái như mới tạo, đang được chuyên gia xử lý, chờ khách hàng phản hồi, solution provided hoặc closed (tên hiển thị có thể khác với enum API). Khi cần trả lời Google:

- Nhắc lại case ID để tránh mở thêm ticket trùng.
- Gửi phần bổ sung theo mốc thời gian và bằng chứng cụ thể.
- Xác nhận đã thử workaround và kết quả.
- Cập nhật tác động nếu sự cố nặng lên/giảm đi.
- Ghi quyết định của incident commander vào nhật ký nội bộ.

Nếu đề xuất của Support không giải quyết được vấn đề, cập nhật lại case hoặc reopen theo quy trình; không đánh dấu incident nội bộ resolved chỉ vì case có trạng thái solution provided.

### 11.3. Một case cho một vấn đề

Không gom nhiều vấn đề độc lập vào một case quá dài; cũng không tạo nhiều case trùng cho cùng một lỗi với hy vọng được xử lý nhanh hơn. Mỗi vấn đề nên có một case có owner, update cadence và link trong incident tracker. Khi một lỗi phát sinh từ nhiều project có chung root symptom, liên kết các project/resource trong một case nếu Support scope cho phép.

## 12. Mẫu mô tả case kỹ thuật

Ví dụ minh họa cho Spring Boot API trên Cloud Run phụ thuộc Cloud SQL. Các ID là giả định, không phản ánh sự cố thật:

~~~text
Subject: [Production impact] Cloud SQL connection timeouts affecting orders API

Priority: P2 (high impact; partial workaround active)
Project: commerce-prod-example
Products: Cloud SQL for PostgreSQL; Cloud Run
Region: asia-southeast1
Start time: 2026-11-19T08:15:00Z
Current state: Ongoing; mitigated by reducing traffic and concurrency

Business impact:
- Approximately 14% of order submissions fail or exceed 5 seconds.
- p99 latency rose from 650 ms to 7 seconds.
- Payment confirmation is deferred; no confirmed data loss so far.

Expected:
- Cloud Run service connects to Cloud SQL under normal load.

Observed:
- Intermittent connection timeout and JDBC pool acquisition timeout.
- Error spikes across two Cloud Run revisions with no new release.

Evidence:
- Request log query/link: [internal sanitized URL]
- Monitoring chart: [internal sanitized URL]
- Example trace ID: [redacted/approved ID]
- Cloud SQL instance identifier: orders-db-test-placeholder
- Personalized Service Health event: [link if applicable]

Changes and mitigation:
- No schema migration or IAM change during the observed window.
- Reduced max instances and enabled temporary backpressure.
- Existing connections recover intermittently.

Request:
- Please confirm whether a service-side incident affects this region/instance.
- Recommend safe diagnostic steps and any available workaround.
- Advise when additional information or coordinated troubleshooting is needed.

Technical contact:
- On-call engineering team, available via support case/bridge.
~~~

Ví dụ trên dùng các con số giả lập để minh họa cách viết. Với P1 phải mô tả rõ sự cố production nghiêm trọng và không có workaround nhanh; nếu đã giảm tác động đáng kể, mức ưu tiên có thể khác. Không tự tạo link hay trace ID giả trong case thật.

### 12.1. Mẫu trao đổi cập nhật

~~~text
Case update — 2026-11-19T09:05:00Z
Observed change: Error rate decreased from 14% to 2% after routing adjustment.
Still impacted: API latency and a subset of payment confirmations.
Mitigation: Holding max concurrency at approved temporary value.
New evidence: Trace IDs and region-scoped charts attached (sanitized).
Request: Please confirm whether the suspected Cloud SQL disruption remains active.
Next internal checkpoint: 2026-11-19T09:20:00Z.
~~~

Thông tin nên ngắn, theo timeline, có những điều đã thử và câu hỏi cần Google trả lời. Không spam case bằng các log trùng nếu chưa có phát hiện mới.

## 13. Escalation, priority change và bàn giao follow-the-sun

**Tăng mức ưu tiên** khi tác động lớn hơn ban đầu, ví dụ P3 chuyển P1 vì production không thể phục vụ. **Escalate case** khi cần can thiệp quản lý vì việc phối hợp, tiến độ hoặc phạm vi xử lý đang không đáp ứng tình huống. Đây là hai hành động khác nhau.

| Tình huống | Hành động cân nhắc |
|---|---|
| P2 trở thành outage production nghiêm trọng | Cập nhật priority (ví dụ lên P1) và giải thích tác động |
| Chưa có đủ bằng chứng, case mới mở | Tiếp tục triage, cập nhật case, không vội escalate vô lý |
| Đã có phản hồi nhưng giải pháp không xử lý vấn đề | Cung cấp test result, yêu cầu tiếp tục điều tra |
| Chậm trễ nghiêm trọng trong phối hợp/không tìm được owner | Xem quy trình case escalation của offering |
| Sự cố cần theo dõi qua các múi giờ | Dùng chế độ follow-the-sun khi gói và priority hỗ trợ |

Một số tính năng escalation, đổi priority và follow-the-sun phụ thuộc Enhanced/Premium hoặc điều khoản hiện hành. Trong nhiều quy trình, P1 mặc định được xử lý liên tục và có cầu nối kỹ thuật. Với P2, khả năng yêu cầu theo dõi 24/7 có thể cần Premium Support.

### 13.1. Vai trò trong phối hợp

- **Incident Commander (IC):** điều phối tác động, quyết định mitigation/cutover.
- **Technical Lead:** phân tích log/metric/trace, thử nghiệm cách khắc phục.
- **Support Liaison:** giữ liên hệ Customer Care, case ID, cam kết trao đổi.
- **Communications Lead:** cập nhật stakeholders/trạng thái khách hàng.
- **Scribe:** ghi timeline, quyết định, evidence, next action.

Một người có thể kiêm vai trò trong đội nhỏ, nhưng phải rõ ai giữ quyền quyết định về thay đổi production. Google Support là đối tác điều tra, không thay thế quyền chịu trách nhiệm vận hành của chủ workload.

### 13.2. Handoff giữa các ca trực

Handoff tối thiểu gồm: current impact, severity, open cases và priority, Service Health event IDs, mitigation đang áp dụng, những gì không được làm, current hypothesis, Google last update, next expected update, next technical step, rollback status và người trực tiếp nhận ca.

Không chuyển case sang ca khác chỉ bằng câu “Google đang xem”; cần cho người mới đủ thông tin để tiếp tục mà không làm lại triage từ đầu.

## 14. Runbook sự cố kết hợp Service Health và Support

Runbook có thể dùng cho sự cố latency Cloud SQL làm Cloud Run API lỗi. Tất cả khoảng thời gian dưới đây là **ví dụ điều phối nội bộ**, không phải SLA của Google.

| Mốc từ khi phát hiện | Việc đội SRE làm | Bằng chứng/đầu ra |
|---|---|---|
| T+0–5 phút | Validate alert, mở incident nội bộ, gán IC | SLI, tác động, start time |
| T+5–10 phút | Xác định project/region/product, xem PSH và public status | Event ID/link, status, relevance |
| T+10–15 phút | Xem recent deploy, DB metrics, trace, quota/IAM | Giả thuyết và scope |
| T+15–25 phút | Mitigate an toàn: backpressure/rollback/reroute theo runbook | SLI trước/sau, quyết định |
| Khi có tác động cần hỗ trợ | Mở/update support case phù hợp priority | Case ID, evidence, business impact |
| Trong sự cố | Giám sát cập nhật Google, giữ bridge, cập nhật stakeholders | Timeline, status mỗi checkpoint |
| Khi platform phục hồi | Kiểm tra database, backlog, failover, dữ liệu, latency | Validation và data reconciliation |
| Sau sự cố | Restore config, đóng alert/incident, postmortem | Action items và ownership |

### 14.1. Decision points

Trước khi failover database hoặc chuyển traffic region:

1. Có thể gây mất dữ liệu hay split-brain không?
2. RPO/RTO cho phép mức mất dữ liệu và downtime nào?
3. Replica đã bắt kịp chưa? Có quyền truy cập network/secrets ở region đích không?
4. Có đủ quota/capacity không? Dependency nào vẫn nằm region cũ?
5. Ai có thẩm quyền chấp thuận và điểm không thể rollback?
6. Cách đo kết quả sau switch để chứng minh phục hồi?

Không tự động chuyển một hệ thống stateful chỉ vì nhận một log Service Health event. Automation nên dừng ở tạo alert/đề xuất khi chưa chứng minh được an toàn của cutover.

### 14.2. Khi sự cố đã được Google đánh dấu Resolved

Thực hiện ứng dụng-level recovery:

- Xác nhận request success rate và latency đạt ngưỡng ổn định.
- Dọn connection pool lỗi, restart chỉ khi cần.
- Xử lý Pub/Sub backlog có giới hạn và idempotency.
- Kiểm tra transaction bị treo, order status, reconciliation.
- Thu hồi mitigation tạm theo change control.
- Giữ heightened monitoring trong khoảng soak period đã định.
- Hoàn tất postmortem sau khi có đủ dữ liệu, kể cả khi Google report xuất hiện muộn.

## 15. Kịch bản thực hành: Java API gián đoạn phụ thuộc Cloud SQL

Ứng dụng Spring Boot chạy trên Cloud Run ở region Singapore, kết nối Cloud SQL PostgreSQL trong cùng region, ghi sự kiện đơn hàng vào Pub/Sub. Một buổi chiều tỷ lệ timeout tăng.

### Bước 1: nhận biết và đo tác động

Cloud Monitoring ghi nhận:

- Số request/giây vẫn tương đương baseline.
- Tỷ lệ lỗi 5xx tăng; p99 latency vượt SLO.
- HikariCP pending connections tăng; nhiều connection timeout.
- Database query latency/connection errors tăng gần cùng thời điểm.

**Không vội kết luận Cloud SQL lỗi phía Google**. Cần kiểm tra max instances, pool size, quota, deploy và network.

### Bước 2: kiểm tra Service Health

Mở PSH cho project chứa Cloud SQL và Cloud Run; chọn event liên quan ở region và product nếu có. Ghi eventId, state/relevance, startTime, latest update và workaround. Kiểm tra trang công khai khi cần.

Nếu chưa có event, giữ hướng điều tra tất cả nguyên nhân khả dĩ. Nếu có event, vẫn phải đối chiếu dữ liệu ứng dụng trước khi quyết định mitigation.

### Bước 3: giảm tác động

Trong phạm vi runbook được duyệt:

- Giới hạn concurrency hoặc max instances nhằm bảo vệ DB connections.
- Bật backpressure và giảm retry storm.
- Chuyển đọc sang cache/read replica nếu thiết kế hỗ trợ.
- Chỉ failover khi DR đã được thử và dữ liệu/recovery gates đạt.
- Giữ idempotency cho tác vụ đặt hàng và publish event.

### Bước 4: mở case nếu cần

Nếu error rate khiến người dùng gặp khó khăn đáng kể, chọn P1/P2 tùy tác động, khả năng workaround và support offering. Gửi:

- Project ID, instance, region, thời gian theo UTC.
- Mã lỗi JDBC/Cloud SQL, biểu đồ connection/query latency.
- Cloud Run request/traces, phiên bản container, recent changes.
- Sự kiện Service Health liên quan (nếu có).
- Chi tiết mitigation, ảnh hưởng còn lại và câu hỏi cụ thể.

### Bước 5: hoàn tất và học lại

Khi SLO phục hồi, xác nhận những đơn hàng đang pending, Pub/Sub backlog và database integrity. Lưu hồ sơ Support, incident report nếu có và bổ sung action items: cảnh báo pool saturation, test DR, dashboard PSH, quyền hỗ trợ cho ca trực và template case.

## 16. Phân biệt Service Health, Cloud Monitoring và SLO khi báo cáo

Một báo cáo điều hành thường cần ba tầng:

| Tầng | Câu hỏi | Chỉ số/bằng chứng |
|---|---|---|
| Provider event | Google Cloud thông báo sự kiện gì? | PSH event state, product/location, timeline |
| Customer technical impact | Workload bị ảnh hưởng thế nào? | 5xx, latency, DB errors, quota, traces |
| Business impact | Người dùng và nghiệp vụ chịu hậu quả gì? | Failed orders, conversion, support tickets, data integrity |

Ví dụ: “PSH báo Cloud SQL incident liên quan region A từ 08:10 UTC; API của chúng tôi bắt đầu tăng timeout 08:14 UTC; khoảng 11% đơn hàng cần retry, không xác nhận mất dữ liệu; mitigation lúc 08:30 UTC; SLI ổn định từ 09:05 UTC.” Đây là báo cáo có độ chính xác cao hơn câu “Google Cloud down 55 phút”.

### 16.1. SLI và incident detection

Đặt alert theo burn rate của error budget hoặc threshold được nhóm SRE phê duyệt. PSH event là tín hiệu phân loại nguyên nhân và dự báo phạm vi, không phải nguồn duy nhất quyết định mức nghiêm trọng của incident nội bộ.

Đối với môi trường multi-region/hybrid, tổng hợp Service Health events theo organization/folder nhưng giới hạn quyền xem và dữ liệu tài nguyên, đồng thời phát hiện nhiều project dùng chung Shared VPC/Cloud SQL/Artifact Registry.

### 16.2. Đừng nhầm timeline provider và application

Sự cố có thể còn tác động sau khi Google tuyên bố nền tảng đã resolved do backlog, cache, replica lag, ứng dụng chưa restart hoặc client còn giữ connection lỗi. Ngược lại, ứng dụng có thể phục hồi sớm nhờ failover trước khi event Google đóng. Báo cáo hai đường thời gian song song.

## 17. Quản trị, bảo mật và chi phí

### 17.1. Phân quyền theo vai trò

- Team SRE/on-call: Service Health Viewer, đọc metric/log/trace theo project.
- Support Liaison: Tech Support Editor trong phạm vi case cần xử lý.
- Nhóm kỹ thuật ngoài giờ: quyền emergency access có kiểm soát, audit.
- Security: phê duyệt loại log/attachment được phép gửi Customer Care.
- Platform team: tạo alert policy/notification channels, log sinks và org-level integration.

Không cấp quyền xem toàn organization cho một vendor/on-call ngoài phạm vi cần thiết. Với tổ chức có nhiều team, group-based IAM, least privilege và review định kỳ giảm nguy cơ lộ thông tin resource.

### 17.2. Lưu trữ dữ liệu sự cố

Ghi event/case IDs, chat timeline, trace samples và runbook execution vào incident system. Quy định retention, phân quyền, redaction và nơi lưu evidence. Nếu dùng Cloud Logging sink/BigQuery để lưu Service Health logs nhiều project, tính chi phí ingest/storage/query và quyền của sink writer.

Service Health logs chỉ là phần thông tin do provider gửi; nếu cần RCA cho application, kết hợp change log, audit log, deployment events, SLI và business metrics.

### 17.3. Kết nối với FinOps và availability

Trong sự cố, thêm region dự phòng hoặc tăng replica có thể tăng chi phí. Ưu tiên reliability và an toàn theo SLO/DR policy, sau đó tính cost. Không trì hoãn mitigation nghiêm trọng chỉ vì Cloud Billing forecast tăng tạm thời nếu hành động đã được phê duyệt trong continuity plan.

## 18. Sau sự cố: postmortem và cải tiến

Một retrospective không tập trung quy lỗi cá nhân mà nhằm xác định điều kiện hệ thống, tín hiệu bị bỏ lỡ và cách giảm tác động lần sau.

### 18.1. Nội dung postmortem

1. **Summary:** mô tả sự cố và phạm vi người dùng.
2. **Timeline:** thứ tự thời gian từ phát hiện đến phục hồi, gồm Google event updates và customer actions.
3. **Impact:** số request/giao dịch lỗi, latency, dữ liệu, duration, SLO/error budget.
4. **Contributing factors:** single-region dependency, connection pool, thiếu backpressure, alert blind spot...
5. **What worked:** detection, rollback, contact Support, workaround.
6. **What did not work:** thiếu case template, quyền IAM không đủ, pipeline alert trễ...
7. **Action items:** owner, deadline, tiêu chí nghiệm thu và cách kiểm thử.
8. **References:** incident ID, PSH event ID, support case, chart, logs và report.

Nếu Google công bố incident report muộn hơn, cập nhật phần nguyên nhân đã xác nhận; không tự viết nội dung như thể đó là kết luận chính thức của Google.

### 18.2. Các cải tiến thường có giá trị

- Cấu hình PSH alerts theo product/location đang dùng.
- Tập trung SLO alert và giảm paging không liên quan.
- Thiết lập support IAM/training cho ca trực.
- Làm sẵn template case và evidence collection.
- Diễn tập failover/restore và recovery của client Java.
- Thử fallback khi Console/PSH/API không khả dụng.
- Bổ sung customer impact model và business dashboard.
- Làm rõ ownership của shared VPC, database và platform project.

## 19. Troubleshooting khi không xem hoặc không nhận thông tin

**Không mở được Service Health dashboard.** Kiểm tra đang chọn đúng project, có billing và role `roles/servicehealth.viewer`. Nếu IAM/Console đang bị gián đoạn, dùng public status page để tiếp tục triage.

**Không thấy event dù ứng dụng bị lỗi.** Có thể là lỗi riêng project hoặc sự kiện chưa được xác nhận/công bố; cũng có thể do service/region không khớp. Kiểm tra application telemetry, recent changes và mở case khi ảnh hưởng cần hỗ trợ.

**Không nhận Service Health log.** Xác nhận Service Health API đã bật theo hướng dẫn, quyền Logging, product/event thực tế và filter. Không coi việc không có log trong một khoảng ngắn là bằng chứng không có sự cố.

**Log-based alert không bắn.** Kiểm tra policy enabled, notification channel, Logs Explorer filter, permission và trạng thái incident của Monitoring. Tránh dùng filter state=ACTIVE khi chỉ muốn nhận một số cập nhật đóng event.

**Thông báo trùng nhiều lần.** Event update có thể tạo log mới; deduplicate theo event ID và update time, liên kết với cùng incident nội bộ.

**Support Cases page trống.** Xác minh organization/project selector và role `roles/cloudsupport.techSupportViewer`; case ở project khác sẽ không hiện nếu chỉ có quyền trên project hiện tại.

**Không tạo được technical support case.** Kiểm tra support offering của tổ chức và role `roles/cloudsupport.techSupportEditor`; Basic thường chỉ cung cấp billing support, không phải entitlement technical case như gói trả phí.

**Mức ưu tiên phản ánh sai tác động.** Ghi lại business impact và cập nhật case priority theo điều kiện offering; không mở case thứ hai thay cho việc nâng priority của case hiện có.

**Google đánh dấu Resolved nhưng API vẫn lỗi.** Kiểm tra recovery ở tầng app, backlog, stale connection, data integrity và SLO. Nếu triệu chứng còn, cập nhật case với evidence mới.

**Không biết có nên escalate.** Đánh giá tác động hiện tại, lịch sử phản hồi, tình huống phối hợp và quyền theo support package; thay đổi priority khi impact đổi trước khi escalation chỉ để thúc giục.

## 20. Checklist cho đội vận hành

### Trước sự cố

- [ ] Inventory project, region, product và dependency của ứng dụng rõ ràng.
- [ ] On-call có Service Health Viewer, quyền Logs/Monitoring phù hợp.
- [ ] Có người được phân quyền xem/tạo support case theo offering.
- [ ] PSH alerts được lọc theo dịch vụ/region/relevance quan trọng.
- [ ] SLO và synthetic probes hoạt động độc lập với status page.
- [ ] Có fallback public status/RSS, runbook và danh bạ ngoài failure domain chính.
- [ ] Có template case, hướng dẫn redaction và support contacts.
- [ ] Đã diễn tập DR/rollback và cảnh báo Service Health.

### Trong sự cố

- [ ] Ghi timestamp UTC và business impact, xác định incident commander.
- [ ] Đối chiếu PSH/public events với SLI, log, trace và change timeline.
- [ ] Không xác định nguyên nhân theo suy đoán thiếu bằng chứng.
- [ ] Mitigation đã qua risk gate, phù hợp SLO/RTO/RPO và có rollback.
- [ ] Case đúng priority, product/project/region, symptoms và evidence.
- [ ] Support liaison cập nhật case/timeline, không tạo duplicate.
- [ ] Có kế hoạch handoff, communication và next check time.

### Sau sự cố

- [ ] SLI ổn định; dữ liệu, backlog và transactions được đối soát.
- [ ] Mitigation tạm được thu hồi có kiểm soát.
- [ ] Service Health/Support event IDs lưu trong incident record.
- [ ] Postmortem tách confirmed root cause khỏi hypothesis.
- [ ] Action items có owner, hạn và validation/test.
- [ ] Quyền hỗ trợ, alert noise và fallback được cải tiến.

## 21. Bài tập tình huống

**Tình huống A — Google event không có tác động trực tiếp.** PSH báo một sự kiện RELATED tới BigQuery ở region dùng cho báo cáo nội bộ. Không có request lỗi, nhưng dashboard cuối ngày bị trễ. Hãy phân loại internal severity, xác minh SLA của báo cáo, chọn alert channel và quyết định có cần case riêng hay chỉ theo dõi event đã công bố.

**Tình huống B — Không có event nhưng người dùng bị ảnh hưởng.** Spring Boot API lỗi 20% request sau thay IAM của service account. Public status “healthy”, PSH không có event tương ứng. Hãy mô tả quy trình triage, logs/IAM evidence, rollback và điều kiện mở Google case nếu chưa xử lý được.

**Tình huống C — Event Resolved nhưng ứng dụng chưa phục hồi.** Pub/Sub subscription backlog tồn đọng 2 triệu messages sau regional disruption. Hãy thiết kế backpressure, consumer scaling, dedup, DLQ, SLO phục hồi và lời cập nhật gửi stakeholder. Vì sao không nên đóng incident ngay khi event của Google chuyển Closed?

**Tình huống D — Đang có P2 case, production suy sụp.** Workload chuyển từ lỗi một phần sang hoàn toàn không sử dụng được, không còn workaround. Hãy trình bày bằng chứng business impact cần bổ sung, cách đổi priority, trách nhiệm tham gia bridge và khi nào cần escalation.

## 22. Tài liệu tham khảo chính thức

- [Google Cloud Service Health công khai](https://status.cloud.google.com/)
- [Personalized Service Health — Overview](https://cloud.google.com/service-health/docs/overview)
- [Service Health events và incident concepts](https://cloud.google.com/service-health/docs/concepts)
- [Cách Google Cloud công bố các sự cố](https://cloud.google.com/service-health/docs/incident-communication)
- [Xem Service Health dashboard](https://cloud.google.com/service-health/docs/view-events)
- [Quản lý quyền Personalized Service Health](https://cloud.google.com/service-health/docs/manage-access)
- [Service Health API](https://cloud.google.com/service-health/docs/list-events)
- [Service Health logs và export](https://cloud.google.com/service-health/docs/logs)
- [Cảnh báo từ Cloud Logging](https://cloud.google.com/service-health/docs/configure-alerts-cloud-logging)
- [Kiểm tra khi Personalized Service Health bị gián đoạn](https://cloud.google.com/service-health/docs/service-health-disruption)
- [Tích hợp Service Health với hệ thống vận hành](https://cloud.google.com/service-health/docs/how-to-integrate)
- [Cloud Customer Care — Create and manage support cases](https://cloud.google.com/support/docs/customer-care-procedures)
- [Cloud Customer Care — Best practices](https://cloud.google.com/support/docs/best-practices)
- [Cloud Customer Care — IAM access control](https://cloud.google.com/support/docs/access-control)
- [Cloud Customer Care — Language and working hours](https://cloud.google.com/support/docs/language-working-hours)
- [Enhanced Support overview](https://cloud.google.com/support/docs/enhanced)
- [Google Cloud Technical Support Services Guidelines](https://cloud.google.com/terms/tssg)
- [Cloud Monitoring documentation](https://cloud.google.com/monitoring/docs)
- [Cloud Logging documentation](https://cloud.google.com/logging/docs)
- [Cloud Trace documentation](https://cloud.google.com/trace/docs)

## 23. Tổng kết

**Service Health nói về tình trạng của Google Cloud, còn SLI/SLO nói về tình trạng ứng dụng và người dùng của mình.** Đội SRE cần theo dõi cả hai, đối chiếu product/location/timeline, triển khai mitigation theo runbook và liên hệ Customer Care bằng support case có bằng chứng, mức ưu tiên đúng và người phụ trách rõ ràng. Personalized Service Health giúp phát hiện những sự kiện liên quan đến project, trang công khai cung cấp fallback trong sự cố diện rộng, còn Cloud Monitoring/Logging/Trace cho biết mức ảnh hưởng thực.

Vận hành tốt không dừng ở việc nhận thông báo hay mở ticket. Kết quả cần đạt là giảm tác động cho người dùng, bảo vệ dữ liệu, xác nhận dịch vụ phục hồi, lưu lịch sử sự cố và chuyển bài học thành alert, runbook, test DR và quy trình phối hợp với Google Cloud Support có thể lặp lại.
