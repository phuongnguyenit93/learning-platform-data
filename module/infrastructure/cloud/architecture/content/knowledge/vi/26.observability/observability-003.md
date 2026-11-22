# Đo chỉ số nghiệp vụ cùng chỉ số hạ tầng và ứng dụng

## 1. Vì sao cần nhìn cả ba lớp chỉ số?

Một hệ thống có thể có CPU thấp, memory ổn định và tất cả instance đều healthy nhưng khách hàng vẫn không đặt được phòng. Ngược lại, CPU có thể tăng cao trong một đợt xử lý batch nhưng người dùng vẫn nhận kết quả đúng hạn. Nếu chỉ theo dõi hạ tầng, đội vận hành có thể bỏ lỡ lỗi nghiệp vụ; nếu chỉ nhìn dashboard doanh thu hoặc conversion, họ có thể biết kết quả đã giảm nhưng không tìm được nguyên nhân kỹ thuật.

**Observability (khả năng quan sát)** là khả năng suy luận trạng thái bên trong hệ thống từ các tín hiệu mà hệ thống phát ra. Metric, log và distributed trace là ba dạng telemetry phổ biến; chúng cần được liên kết với ngữ cảnh nghiệp vụ để giải thích điều gì xảy ra và tác động tới ai.

Ba lớp quan sát cần được kết nối:

- **Business metrics:** hệ thống có tạo ra kết quả mà doanh nghiệp và người dùng cần không? Ví dụ booking thành công, tỷ lệ thanh toán thành công, doanh thu đã capture, thời gian xác nhận.
- **Application metrics:** request và service có xử lý đúng, nhanh và ổn định không? Ví dụ request rate, error rate, latency, retry, queue age, dependency timeout.
- **Infrastructure metrics:** compute, network, storage và data platform có đủ tài nguyên và hoạt động đúng không? Ví dụ CPU, memory, disk I/O, connection, packet loss, node readiness.

Mục tiêu là nối một biến động kinh doanh với đường đi kỹ thuật có liên quan. Khi tỷ lệ booking giảm, đội vận hành có thể kiểm tra request error, payment dependency, database saturation và queue lag trong cùng khoảng thời gian, tenant hoặc luồng xử lý.

Trong module **CLOUD_ARCHITECTURE**, khả năng quan sát hỗ trợ thiết kế độ tin cậy, hiệu năng, khả năng mở rộng, bảo mật, chi phí và vận hành. Telemetry cần phản ánh cả SLO của người dùng lẫn giới hạn của nền tảng, đồng thời tránh thu thập dư thừa dữ liệu nhạy cảm.

### Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt business metric, application metric và infrastructure metric.
2. Xác định KPI, SLI, SLO và error budget cho một luồng nghiệp vụ.
3. Dùng RED và USE để quan sát service và tài nguyên.
4. Thiết kế telemetry có label/correlation phù hợp để truy nguyên sự cố.
5. Xây dựng dashboard liên kết funnel nghiệp vụ, request path và hạ tầng.
6. Đặt alert theo tác động và tốc độ tiêu hao error budget.
7. Tránh cardinality cao, số liệu gây hiểu nhầm và thu thập PII/secret.
8. Thiết kế case study và runbook từ tín hiệu tới hành động.

## 2. Ba lớp chỉ số và quan hệ giữa chúng

| Lớp | Câu hỏi chính | Ví dụ metric | Người sử dụng |
|---|---|---|---|
| **Business** | Người dùng có hoàn thành mục tiêu? Kết quả kinh doanh có đạt? | Booking conversion, payment success, net revenue, cancellation rate | Product, business owner, operations |
| **Application** | Service có xử lý request/job đúng và nhanh? | Request rate, error rate, latency p95, retry count, queue age | Engineering, SRE, service owner |
| **Infrastructure** | Tài nguyên và nền tảng có đủ capacity, healthy? | CPU, memory, disk latency, DB connections, node pressure | Platform, cloud operations, SRE |

Ba lớp có quan hệ nhân quả nhưng không phải lúc nào cũng tương quan trực tiếp:

- CPU tăng có thể do traffic tăng, query kém hiệu quả hoặc leak; không nhất thiết business outcome tốt hơn.
- Payment success giảm có thể do provider từ chối thẻ, cấu hình auth sai hoặc request timeout; CPU của API vẫn bình thường.
- Conversion giảm có thể do UX, pricing, marketing audience hoặc availability; không phải mọi biến động business đều là incident kỹ thuật.
- Số request tăng có thể là retry storm hoặc bot traffic chứ không phải số khách hàng thực tăng.

Vì vậy dashboard cần cho thấy metric ở cả ba lớp, định nghĩa đo lường và đường liên hệ để điều tra.

### 2.1. Mô hình liên kết tín hiệu

~~~mermaid
flowchart TD
    Business["Business outcomes<br/>Booking, payment, revenue"] --> App["Application signals<br/>RED, queue, dependency"]
    App --> Infra["Infrastructure signals<br/>CPU, memory, DB, network"]
    Infra --> Capacity["Capacity / bottleneck"]
    Capacity --> App
    App --> Business
    Trace["Trace / logs / correlation IDs"] -. "connect events across layers" .-> Business
    Trace -.-> App
    Trace -.-> Infra
~~~

Telemetry giúp liên kết các lớp nhưng không tự chứng minh nhân quả. Muốn kết luận CPU cao gây conversion giảm, cần xem đúng request path, thời gian, cohort và các biến số khác.

## 3. Tách KPI, metric, SLI và SLO

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| **KPI** | Chỉ số thể hiện kết quả hoặc mục tiêu quản trị | Doanh thu đặt phòng theo tháng |
| **Metric** | Một phép đo có giá trị theo thời gian hoặc tập hợp | Số request lỗi mỗi phút |
| **SLI (Service Level Indicator)** | Phép đo phản ánh chất lượng dịch vụ mà người dùng nhận | Tỷ lệ request đặt phòng hoàn tất thành công trong latency mục tiêu |
| **SLO (Service Level Objective)** | Mục tiêu định lượng cho SLI trong một cửa sổ thời gian | 99,9% request booking đạt điều kiện thành công trong 30 ngày |
| **SLA (Service Level Agreement)** | Cam kết dịch vụ với khách hàng/đối tác, có thể kèm hậu quả hoặc service credit | Cam kết availability theo hợp đồng |
| **Error budget** | Phần không đạt SLO được phép trong cửa sổ | 0,1% request không đạt điều kiện |

KPI có thể hướng tới doanh thu hoặc tăng trưởng; SLI/SLO tập trung vào chất lượng dịch vụ mà team có thể tác động. Một KPI giảm không tự động có nghĩa SLO vi phạm.

### 3.1. SLO cần đo điều người dùng cảm nhận

Ví dụ SLI cho API booking:

- **Availability:** tỷ lệ request hợp lệ nhận kết quả thành công hoặc trạng thái nghiệp vụ được định nghĩa là chấp nhận được.
- **Latency:** tỷ lệ request hoàn tất dưới ngưỡng latency đã chọn.
- **Correctness:** tỷ lệ thao tác tạo booking không vi phạm invariant hoặc trả sai trạng thái.
- **Freshness:** độ mới của dữ liệu được hiển thị, ví dụ availability snapshot.
- **Durability/completion:** tỷ lệ operation đã accepted cuối cùng đi tới trạng thái terminal hợp lệ trong deadline.

Không nên tính một HTTP 200 là thành công nếu response chứa trạng thái nghiệp vụ thất bại. Ngược lại, một HTTP 202 Accepted có thể là thành công ở API boundary nếu hợp đồng nói công việc đã được nhận; cần SLI riêng để theo dõi completion end-to-end.

### 3.2. Công thức SLI ví dụ

Nếu có 100.000 request booking hợp lệ trong cửa sổ và 99.920 request đạt điều kiện thành công:

\[
SLI = \frac{99,920}{100,000} \times 100\% = 99.92\%
\]

Nếu SLO là 99,9%, SLI trong ví dụ đang vượt mục tiêu. Nhưng cần kiểm tra các request bị loại trừ có hợp lý không; loại bỏ quá nhiều lỗi client, timeout hoặc dependency có thể làm SLI đẹp giả tạo.

## 4. Chọn business metric theo hành trình người dùng

Business metric tốt bắt đầu từ mục tiêu của người dùng và funnel nghiệp vụ. Không nên đặt metric chỉ vì dễ đếm.

### 4.1. Ví dụ funnel đặt phòng

~~~mermaid
flowchart LR
    Visit["Visit / search"] --> View["View property"]
    View --> Select["Select dates / room"]
    Select --> Checkout["Start checkout"]
    Checkout --> Pay["Payment authorized/captured"]
    Pay --> Confirm["Booking confirmed"]
    Confirm --> Complete["Stay completed"]
    Checkout --> Drop["Abandoned"]
    Pay --> Fail["Payment failed"]
    Confirm --> Cancel["Cancelled / refunded"]
~~~

Mỗi bước nên có định nghĩa event và trạng thái rõ:

| Metric | Định nghĩa cần thống nhất |
|---|---|
| Search-to-view rate | Session tìm kiếm có ít nhất một property view / session search hợp lệ |
| Checkout-start rate | Session hoặc user bắt đầu checkout / nhóm đủ điều kiện theo funnel |
| Payment authorization rate | Authorization thành công / payment attempt hợp lệ |
| Booking confirmation rate | Booking được xác nhận / booking request hợp lệ |
| Cancellation rate | Booking bị hủy / booking trong cohort và giai đoạn được định nghĩa |
| Net booking value | Giá trị booking sau điều chỉnh/cancel/refund theo quy tắc kế toán nghiệp vụ |
| Time to confirmation | Thời gian từ khi user gửi yêu cầu tới trạng thái confirmed |

Mẫu số và cohort phải nhất quán. Không chia số booking confirm hôm nay cho số session hôm nay nếu booking có thể được tạo từ session ngày trước hoặc flow có độ trễ.

### 4.2. Event semantics và trạng thái nghiệp vụ

Một booking có thể đi qua REQUESTED, INVENTORY_HELD, PAYMENT_PENDING, CONFIRMED, CANCELLED hoặc REFUNDED. Business metrics phải phân biệt request mới được nhận; chỗ được giữ tạm; payment được authorize hay capture; booking được xác nhận; booking bị hủy và tiền đã được refund hay chưa.

Đếm payment_requested như doanh thu sẽ làm số liệu sai khi payment bị decline hoặc timeout. Đếm booking_created như booking confirmed cũng có thể làm conversion cao giả tạo.

### 4.3. Business dimensions

Có thể phân tích theo tenant, property region, channel, platform version, payment method, customer segment hoặc campaign. Chỉ dùng dimension có định nghĩa và quyền truy cập rõ ràng; tránh đưa email, phone, tên người dùng hoặc ID cá nhân không cần thiết vào metric label.

## 5. Application metrics: RED và golden signals

Mô hình RED phù hợp với service xử lý request:

- **Rate:** số request mỗi giây/phút.
- **Errors:** tỷ lệ hoặc số request lỗi, phân theo loại.
- **Duration:** phân phối thời gian xử lý, thường xem p50/p95/p99.

Một số hệ thống bổ sung saturation và queue metrics để hiểu service đã chạm giới hạn hay chưa.

| Metric | Định nghĩa | Cách dùng |
|---|---|---|
| http_requests_total | Counter số request theo route/method/status class | Rate và error ratio |
| http_request_duration_seconds | Histogram thời gian request | p50/p95/p99 |
| inflight_requests | Số request đang xử lý | Concurrency và saturation |
| request_retries_total | Số lần retry | Phát hiện retry amplification |
| dependency_duration_seconds | Thời gian gọi DB/provider/queue | Xác định bottleneck |
| queue_oldest_message_age_seconds | Tuổi message cũ nhất | Freshness và worker capacity |

### 5.1. Golden signals

| Signal | Câu hỏi |
|---|---|
| Latency | Người dùng phải chờ bao lâu? |
| Traffic | Hệ thống nhận bao nhiêu demand? |
| Errors | Bao nhiêu request/job không thành công? |
| Saturation | Thành phần gần cạn tài nguyên nào? |

RED và golden signals không thay thế business metrics. Chúng giúp hiểu sức khỏe service, còn business metrics cho biết service đang tạo ra kết quả đúng hay không.

### 5.2. Phân loại lỗi

Không gom tất cả lỗi thành một con số:

- 4xx do input không hợp lệ hoặc policy từ chối.
- 429 do rate limit/throttling.
- 5xx do lỗi service hoặc upstream.
- Timeout và connection reset.
- Business rejection như không còn chỗ, payment decline.
- Retry exhaustion và dead-letter.

Định nghĩa SLI phải quyết định rõ loại nào được tính là service failure và loại nào là kết quả nghiệp vụ hợp lệ. Ví dụ payment decline là thất bại với conversion funnel nhưng không nhất thiết là lỗi availability của payment API.

## 6. Infrastructure metrics: USE và capacity

USE là cách xem từng resource:

- **Utilization:** tài nguyên bận ở mức nào?
- **Saturation:** có hàng đợi hoặc công việc chờ do tài nguyên bị nghẽn không?
- **Errors:** tài nguyên có phát sinh lỗi không?

| Resource | Utilization | Saturation | Errors |
|---|---|---|---|
| CPU | CPU usage/time | Run queue, throttling | CPU steal/throttling events tùy nền tảng |
| Memory | Working set/used memory | Swap, reclaim, OOM risk | OOM kill/page faults bất thường |
| Disk/storage | IOPS/throughput/capacity | Queue depth, latency | Read/write errors |
| Network | Throughput | Queue/drop/congestion | Packet loss, retransmits, connection reset |
| Database | CPU, connections, storage | Lock wait, connection wait, replication lag | Query errors, failover, deadlocks |
| Queue/broker | Throughput, storage | Consumer lag, oldest message age | Publish/consume failures, redelivery |
| Node/cluster | CPU/memory allocatable | Pending pod, scheduling wait | Node not ready, eviction |

### 6.1. Hạ tầng có thể healthy trong khi app đã bão hòa

CPU chỉ 40% nhưng thread pool đã hết; DB connection pool cạn; một hot partition bị nghẽn; external API quota bị chạm. Vì vậy saturation nên đo ở nơi công việc thực sự xếp hàng, không chỉ ở CPU và memory.

### 6.2. Hạ tầng tăng capacity có thể làm business xấu hơn

Scale thêm API replica có thể tăng connection đến database và payment provider. Nếu dependency đã gần chạm giới hạn, request timeout và payment failure có thể tăng. Dashboard nên hiển thị đồng thời app replica count, DB connections, dependency latency và business success.

## 7. Liên kết business event với request và trace

Muốn biết một booking thất bại vì đâu, cần liên kết event nghiệp vụ với request và các service tham gia.

### 7.1. Correlation context

Một flow có thể mang các định danh:

- trace_id: định danh distributed trace.
- span_id: một operation trong trace.
- request_id: định danh request ở boundary nếu dùng riêng.
- booking_id/operation_id: định danh nghiệp vụ, chỉ log khi policy cho phép.
- tenant_id: tenant scope đã được kiểm soát.
- deployment_version: phiên bản code xử lý.
- data_interval hoặc partition: với tác vụ dữ liệu.

Không đưa mọi identifier vào metric label. Trace/log có thể chứa một số high-cardinality context nếu hệ thống lưu trữ và quyền truy cập cho phép; metric nên giữ dimensions có cardinality được kiểm soát.

### 7.2. Trace một booking

~~~mermaid
sequenceDiagram
    participant C as Client
    participant API as Booking API
    participant DB as Database
    participant P as Payment service
    participant Q as Notification queue
    C->>API: POST /bookings (trace_id)
    API->>DB: Check and hold inventory
    DB-->>API: Hold result
    API->>P: Authorize payment
    P-->>API: Payment result
    API->>DB: Confirm booking + outbox
    DB-->>API: Commit
    API->>Q: Publish confirmation event
    API-->>C: Response
~~~

Trace giúp xác định span chậm hoặc lỗi. Business event xác định booking cuối cùng thành công hay thất bại. Một HTTP request có thể thành công nhưng queue consumer gửi email lỗi sau đó; trace và operation state cần liên kết qua event/correlation ID để thấy toàn bộ quy trình bất đồng bộ.

### 7.3. Instrumentation ở boundary

Tạo trace ở edge/API gateway; propagate context qua HTTP/gRPC/message headers theo chuẩn hỗ trợ; ghi span cho DB/HTTP/queue operation; tạo event nghiệp vụ tại trạng thái commit; ghi deployment/version và error classification. Với asynchronous workflow, liên kết trace context qua message hoặc dùng span link khi một event tiếp nối từ nhiều trace.

## 8. Metric design: tên, đơn vị, label và cardinality

Metric cần có định nghĩa để hai dashboard không đo cùng tên nhưng mang mẫu số khác nhau.

### 8.1. Metric contract

| Trường | Ví dụ |
|---|---|
| Name | booking_confirmations_total |
| Type | Counter |
| Unit | Booking |
| Description | Số booking chuyển sang trạng thái CONFIRMED |
| Start/end semantics | Ghi sau transaction commit |
| Labels | channel, region, payment_method (giới hạn tập giá trị) |
| Owner | Booking service team |
| Cardinality budget | Giới hạn label combinations |
| SLI/KPI mapping | Booking confirmation rate |
| Retention | Theo telemetry policy |

### 8.2. Counter, gauge và histogram

- **Counter:** chỉ tăng, ví dụ tổng request hoặc booking confirmation.
- **Gauge:** giá trị có thể tăng/giảm, ví dụ queue depth, active connection.
- **Histogram:** phân phối giá trị theo bucket, ví dụ request latency hoặc job duration.
- **Summary:** phép tổng hợp phân vị tùy client/implementation; cần cân nhắc khả năng aggregate giữa replica.

Đối với latency toàn hệ thống, histogram thường thuận tiện hơn để tổng hợp từ nhiều instance nếu bucket được thiết kế nhất quán.

### 8.3. Cardinality cao

Nếu label chứa user_id, booking_id, raw URL, email hoặc exception message, mỗi giá trị mới có thể tạo time series mới. Hệ quả là chi phí storage/query tăng, dashboard chậm và telemetry backend bị quá tải.

Thực hành tốt:

- Dùng route template như /bookings/{id}, không dùng URL raw chứa ID.
- Dùng status class hoặc error category, không dùng thông điệp exception tự do.
- Không gắn user/booking ID vào metric label.
- Dùng trace/log để drill down vào một request cụ thể.
- Giới hạn các label như region, channel, outcome, service version.
- Theo dõi số time series và đặt budget/cardinality alert.

## 9. Dashboard đa lớp

Một dashboard điều hành nên có tổng quan và đường drill-down. Không nên nhồi hàng trăm biểu đồ không có câu hỏi cần trả lời.

| Khu vực | Nội dung | Câu hỏi |
|---|---|---|
| Business outcome | Booking conversion, confirmation, payment success, net value | Khách hàng có hoàn tất mục tiêu? |
| Experience/SLO | Availability, latency p95/p99, error budget burn | Chất lượng dịch vụ có đạt cam kết? |
| Application path | Request rate, error class, dependency latency, retries, queue age | Thành phần nào làm luồng chậm/lỗi? |
| Infrastructure | CPU, memory, DB connection/lock, I/O, network, node readiness | Tài nguyên nào là bottleneck? |
| Change context | Deployment, config, schema, provider incident | Điều gì vừa thay đổi? |
| Data quality | Freshness, reconciliation, duplicate, missing event | Số liệu business có đáng tin? |

### 9.1. Dashboard không thay thế điều tra

Khi thấy một điểm bất thường, cần drill-down: chọn thời gian bắt đầu và scope ảnh hưởng; so sánh business funnel theo channel/region/platform; mở application RED metrics và error breakdown; theo trace tới dependency span chậm/lỗi; kiểm tra infrastructure saturation, recent deployment và provider status; xác định business event cuối cùng và số khách hàng/transaction bị ảnh hưởng.

## 10. Alert theo tác động, không theo mọi metric

Alert tốt cần actionable, gắn owner và báo đủ sớm. CPU 80% có thể là thông tin quan sát; nếu hệ thống vẫn đạt latency và không saturation, chưa chắc cần page người trực.

### 10.1. Alert theo SLO/error budget

Giả sử SLO availability là 99,9% trong 30 ngày. Error budget theo tỷ lệ là 0,1% request trong cửa sổ. Nếu error rate tăng nhanh, cần alert theo burn rate: tốc độ tiêu hao error budget so với mức cho phép.

Alert có thể kết hợp cửa sổ ngắn và dài:

- Burn nhanh trong vài phút: có thể là outage cần page ngay.
- Burn chậm kéo dài: tạo ticket hoặc cảnh báo team.
- Business conversion giảm nhưng SLO kỹ thuật vẫn đạt: gửi product/business alert để điều tra funnel.
- DB saturation tăng nhưng chưa ảnh hưởng SLO: cảnh báo sớm theo ngưỡng capacity để chủ động xử lý.

### 10.2. Ví dụ alert matrix

| Tín hiệu | Điều kiện minh họa | Hành động |
|---|---|---|
| Booking SLI | Tỷ lệ xác nhận giảm nhanh dưới SLO | Page booking on-call, kiểm tra funnel/trace |
| Payment success | Giảm theo provider/method | Kiểm tra provider, auth config và retry |
| API latency | p95 vượt SLO liên tục | Kiểm tra RED, deployment và dependency |
| Queue age | Oldest message vượt processing SLA | Kiểm tra worker capacity và provider throttle |
| DB connections | Gần giới hạn đồng thời pool wait tăng | Kiểm tra leak, autoscaling và query |
| Disk capacity | Tốc độ tăng dự báo chạm đầy trước khi xử lý | Mở rộng/dọn theo policy có kiểm soát |
| Data freshness | Dashboard partition cũ hơn SLA | Kiểm tra orchestration, source watermark và quality gate |
| Cardinality | Time series tăng bất thường | Tìm label mới/high-cardinality và giới hạn |

Ngưỡng trong bảng chỉ minh họa. Nên chọn dựa trên baseline, SLO, error budget, capacity test và khả năng xử lý của on-call.

## 11. Định nghĩa business success và tránh metric gây hiểu nhầm

Một business metric thường có nhiều biến thể; phải định nghĩa quy tắc trước khi dùng làm KPI hoặc alert.

### 11.1. Gross và net

Ví dụ doanh thu:

- Gross booking value: tổng giá trị booking được tạo theo một định nghĩa.
- Captured payment: tiền đã capture từ payment provider.
- Refund: khoản tiền đã hoàn lại.
- Net revenue/value: kết quả sau các điều chỉnh theo quy tắc kế toán và kỳ ghi nhận.

Không lấy tổng booking amount làm cash collected. Payment authorization không nhất thiết đã capture; refund có thể diễn ra nhiều ngày sau booking. Phải thống nhất timestamp, currency, timezone và cohort.

### 11.2. Tỷ lệ conversion

Conversion nên dùng cùng một cohort và cửa sổ:

\[
Conversion = \frac{Eligible\ users\ completing\ goal}{Eligible\ users\ entering\ funnel}
\]

Nếu mẫu số thay đổi do bot, campaign hoặc event tracking lỗi, conversion có thể biến động dù trải nghiệm thực tế không đổi. Theo dõi event completeness và data quality cùng business metric.

### 11.3. Guardrail metrics

Một KPI tăng có thể che rủi ro khác. Khi tối ưu conversion, nên theo dõi cancellation/refund rate; fraud/chargeback signal; booking duplicate hoặc inventory conflict; support contact rate; latency/error rate và data freshness.

Tăng số booking nhưng tăng đặt trùng, hoàn tiền và support ticket không phải thành công bền vững.

## 12. Telemetry cho hệ thống bất đồng bộ và data platform

Với queue và pipeline, request latency không thể đại diện toàn bộ trải nghiệm.

### 12.1. Queue/worker

Đo message published/consumed/acked; queue depth và oldest message age; consumer lag và processing duration; retry, redelivery, dead-letter count; success theo business operation sau cùng.

Message được ack không nhất thiết đồng nghĩa business operation thành công nếu consumer ack quá sớm. Event nên gắn operation ID và trạng thái nghiệp vụ được commit.

### 12.2. Data pipeline

Đo pipeline/run success rate; data freshness lag so với source watermark; rows/files read và written; quality failure, missing/duplicate và reconciliation delta; task retry, duration, queue/scheduler delay; cost per successful partition/dataset.

Một pipeline exit code 0 nhưng dữ liệu trống hoặc thiếu partition vẫn là lỗi chất lượng. Quality gate cần được phản ánh trên dashboard cùng job health.

## 13. Telemetry security và privacy

Logs, metrics và traces có thể chứa dữ liệu nhạy cảm. Observability platform thường tập trung dữ liệu từ nhiều service nên trở thành mục tiêu có giá trị.

Thực hành:

- Không log password, access token, refresh token, private key, card security code hoặc secret.
- Mask/redact PII trước khi gửi telemetry.
- Không dùng email, phone, booking ID hoặc customer ID làm metric label.
- Giới hạn quyền truy cập trace/log theo team và data classification.
- Dùng retention theo mục đích; log debug không nhất thiết giữ như audit log.
- Mã hóa in transit/at rest và audit việc tìm kiếm/export dữ liệu.
- Cẩn trọng sampling: không sample mất toàn bộ các lỗi hiếm/transaction quan trọng; có tail sampling hoặc error-aware sampling nếu hệ thống hỗ trợ.
- Bảo vệ telemetry ingestion endpoint bằng identity, TLS và quota.

Trace/log không nên bị xem là nơi lưu trữ dữ liệu giao dịch chính thức. Nếu cần audit hoặc ledger, dùng hệ thống lưu trữ được thiết kế cho tính toàn vẹn và retention tương ứng.

## 14. Sampling, retention và chi phí quan sát

Thu thập toàn bộ log/trace/metric ở độ chi tiết cao có thể làm observability bill vượt chi phí ứng dụng.

Các chiến lược:

1. Giữ metric tổng hợp đủ dài để phân tích trend và capacity.
2. Dùng sampling cho trace traffic bình thường, ưu tiên giữ error/slow trace theo policy.
3. Dùng structured log và mức log phù hợp; không log mỗi dòng dữ liệu trong vòng lặp lớn.
4. Tách debug log ngắn hạn khỏi security/audit log.
5. Giảm label cardinality và loại bỏ metric không còn người dùng.
6. Đo ingestion volume, query cost, retention bytes và cost per service.
7. Có thể dùng exemplars/trace link để chuyển từ metric spike sang một số trace đại diện.

Sampling cần được ghi rõ trong dashboard. Một tỷ lệ error hiếm có thể biến mất trong sample ngẫu nhiên; không dùng sampled trace làm mẫu số chính cho SLI availability nếu không có phép đo counter chính xác.

## 15. Case study: quan sát end-to-end nền tảng đặt phòng

**Bối cảnh:** nền tảng cho thuê chỗ ở có Search API, Booking API, Inventory service, Payment service, Notification worker và data pipeline tổng hợp doanh thu. Người dùng báo rằng checkout thỉnh thoảng thất bại. CPU cluster không cao, nhưng business owner thấy số booking confirmed giảm.

### 15.1. Bộ chỉ số đề xuất

| Lớp | Metric | Định nghĩa |
|---|---|---|
| Business | booking_confirmation_rate | Booking confirmed / booking request hợp lệ theo cohort |
| Business | payment_authorization_rate | Payment authorized / attempt hợp lệ theo provider/method |
| Business | checkout_abandonment_rate | Checkout không đi tới trạng thái terminal thành công trong cửa sổ |
| Business | net_booking_value | Giá trị sau cancellation/refund theo quy tắc đã duyệt |
| Application | booking_request_duration | Latency của Booking API p50/p95/p99 |
| Application | inventory_conflict_total | Số request không giữ được inventory do conflict |
| Application | payment_dependency_errors | Lỗi/timeout theo provider và error category |
| Application | notification_queue_age | Tuổi message cũ nhất |
| Infrastructure | db_connection_pool_wait | Thời gian chờ connection ở app |
| Infrastructure | db_lock_wait | Thời gian chờ lock ở database |
| Infrastructure | node_cpu_throttling | CPU bị throttle ở compute |
| Data | revenue_model_freshness | Độ trễ dữ liệu báo cáo so với source watermark |

### 15.2. Luồng điều tra

1. Business dashboard cho thấy confirmation rate giảm 8% ở checkout trên mobile; search-to-view vẫn bình thường.
2. Application dashboard cho thấy payment dependency timeout tăng ở một provider; inventory conflict không tăng.
3. Trace mẫu của checkout chậm cho thấy thời gian chờ nằm ở span gọi provider, không phải DB.
4. Infrastructure dashboard cho thấy CPU và DB connection bình thường; dependency timeout là tín hiệu chính.
5. Payment team kiểm tra provider quota/latency và config retry; retry storm được giới hạn bằng backoff/circuit breaker.
6. Booking API giữ operation ở trạng thái pending/unknown thay vì đánh dấu thất bại ngay khi timeout.
7. Dashboard business theo dõi confirmation/reconciliation sau khi provider trả kết quả; data pipeline chỉ publish revenue sau quality gate.

Con số giảm 8% là tình huống minh họa. Kết luận điều tra phải dựa trên dữ liệu thực, không suy ra nguyên nhân chỉ từ tương quan.

### 15.3. Dashboard bố trí

~~~mermaid
flowchart TD
    Overview["Executive / business overview"] --> Funnel["Funnel and payment outcomes"]
    Overview --> SLO["SLO and error budget"]
    SLO --> RED["Service RED metrics"]
    RED --> Trace["Trace by operation / provider"]
    Trace --> Infra["DB, compute, network and queue"]
    Overview --> Data["Data freshness and quality"]
    Data --> Pipeline["Pipeline run / reconciliation"]
~~~

### 15.4. Tiêu chí nghiệm thu

- Booking confirmation và payment outcome có định nghĩa event/state rõ.
- Business metric nối được với request/trace mà không dùng PII làm metric label.
- Trace có thể xác định span dependency chậm ở checkout.
- Infrastructure metric thể hiện DB connection/lock, node saturation và queue age.
- SLO availability/latency có cửa sổ và error budget được duyệt.
- Revenue dashboard hiển thị freshness và quality status.
- Alert có owner, severity, runbook và phân biệt business degradation với technical outage.

## 16. Quy trình xây dựng observability từ đầu

1. **Chọn user journey:** xác định các luồng tạo giá trị và trạng thái nghiệp vụ quan trọng.
2. **Định nghĩa event:** tên, thời điểm phát, business key, source of truth và trạng thái terminal.
3. **Chọn SLI/SLO:** availability, latency, completion, freshness hoặc correctness.
4. **Instrument application:** RED metrics, dependency spans, structured logs và correlation context.
5. **Instrument infrastructure:** USE metrics và resource saturation.
6. **Thiết kế metric contract:** type, unit, labels, owner, cardinality và retention.
7. **Tạo dashboard:** business → SLO → service → dependency → infrastructure.
8. **Thiết lập alert:** burn rate, business anomaly, saturation và data freshness.
9. **Viết runbook:** mỗi alert chỉ ra truy vấn, owner, quyết định và recovery action.
10. **Kiểm thử:** inject lỗi, tạo traffic mẫu, xác minh dashboard và alert có phát đúng.
11. **Rà soát:** loại metric không dùng, sửa label cardinality, điều chỉnh SLO và cost.

## 17. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách cải thiện |
|---|---|---|
| Chỉ giám sát CPU/memory | Không biết người dùng có hoàn thành nghiệp vụ | Thêm business outcome và application SLI |
| Chỉ theo dõi doanh thu/conversion | Không tìm được nguyên nhân kỹ thuật | Nối business event với request, trace và dependency |
| Đếm HTTP 200 là booking thành công | Số liệu đẹp giả tạo khi nghiệp vụ thất bại | Đo trạng thái nghiệp vụ sau commit |
| Dùng payment requested làm doanh thu | Tính cả giao dịch decline/timeout | Phân biệt authorized, captured, refunded |
| Mẫu số conversion không cùng cohort | Tỷ lệ không có ý nghĩa | Định nghĩa cohort, time window và eligibility |
| Chỉ alert CPU threshold | Nhiều false positive hoặc bỏ lỡ bottleneck | Alert theo SLO, saturation và impact |
| Label chứa user/booking ID | Cardinality và chi phí tăng mạnh | Dùng metric dimensions hữu hạn; trace/log để drill-down |
| Trace/log không có correlation context | Không nối được async flow | Propagate trace context và operation ID |
| Dashboard không có data freshness | Báo cáo cũ bị hiểu là kết quả hiện tại | Hiển thị source watermark và quality status |
| Sample trace dùng làm mẫu số SLI | Sai lệch tỷ lệ lỗi/availability | Dùng counter/histogram đầy đủ cho SLI |
| Thu thập telemetry không giới hạn | Tốn chi phí và có thể lộ PII | Sampling, retention, redaction và access control |
| Alert không có owner/runbook | On-call nhận tín hiệu nhưng không biết hành động | Gắn severity, owner, query và recovery step |

## 18. Checklist review observability

### Business metrics

- [ ] Các user journey và trạng thái nghiệp vụ được định nghĩa.
- [ ] KPI có công thức, cohort, timezone, currency và mẫu số rõ.
- [ ] Phân biệt accepted, completed, authorized, captured, confirmed, cancelled và refunded.
- [ ] Có guardrail metrics như cancellation, duplicate, fraud và support contact.
- [ ] Business metric có owner và nguồn dữ liệu có thẩm quyền.

### Application và infrastructure

- [ ] Service có RED metrics và dependency latency/error.
- [ ] Queue/worker có backlog, oldest age, retry và DLQ.
- [ ] Hạ tầng có USE metrics cho CPU, memory, disk, network, database và node.
- [ ] Desired/running/ready capacity và saturation được hiển thị.
- [ ] Có deploy/config/provider change context.

### Correlation và chất lượng telemetry

- [ ] Trace context được propagate qua HTTP/RPC/message.
- [ ] Business operation có correlation ID phù hợp và policy cho phép.
- [ ] Metric có type, unit, description, owner và cardinality budget.
- [ ] Metric label không chứa PII/high-cardinality identifiers.
- [ ] Sampling không làm sai SLI; log/trace có retention phù hợp.
- [ ] Data freshness và quality status hiển thị cùng business dashboard.

### SLO, alert và vận hành

- [ ] SLI/SLO đo điều người dùng cảm nhận, có cửa sổ và error budget.
- [ ] Alert theo burn rate/impact và có owner/severity.
- [ ] Business anomaly và technical incident được phân biệt.
- [ ] Mỗi alert có runbook, truy vấn và recovery action.
- [ ] Dashboard đã được kiểm thử bằng failure injection và dữ liệu đại diện.
- [ ] Chi phí telemetry, retention và query được theo dõi.

## 19. Bài tập thực hành

**Bối cảnh:** một nền tảng đặt phòng có Search, Booking, Inventory, Payment và Notification service. Product team nói conversion giảm trong hai ngày gần đây; đội vận hành báo CPU và memory đều bình thường. Dashboard hiện tại chỉ có tổng HTTP request và CPU theo cluster.

Hãy thiết kế observability:

1. Vẽ funnel từ search tới booking confirmed và định nghĩa event/terminal state.
2. Viết công thức booking conversion, payment authorization rate và cancellation rate với cohort/mẫu số rõ.
3. Chọn ít nhất hai SLI và SLO cho booking API; giải thích request nào tính là success.
4. Thiết kế RED metrics cho Booking/Payment service và USE metrics cho DB/compute/queue.
5. Đề xuất trace/span và correlation context để nối một checkout với payment provider.
6. Chọn label có cardinality kiểm soát; xác định dữ liệu không được đưa vào metric.
7. Thiết kế dashboard business → SLO → application → infrastructure → data freshness.
8. Đề xuất alert theo error budget burn, payment degradation, DB saturation và queue age.
9. Viết runbook điều tra conversion giảm khi CPU vẫn bình thường.
10. Thiết kế failure-injection test và xác nhận dashboard/alert hoạt động.

**Gợi ý tự kiểm tra:** Conversion giảm không chứng minh service hỏng; CPU bình thường không chứng minh request path khỏe. Payment decline cần phân biệt với provider timeout. Một booking chỉ được tính confirmed theo trạng thái nguồn sự thật sau commit, không theo số HTTP response thành công.

## 20. Ghi nhớ

Observability có giá trị khi nối được kết quả nghiệp vụ với trải nghiệm request và trạng thái tài nguyên. Business metrics cho biết người dùng/doanh nghiệp đạt mục tiêu hay chưa; application metrics chỉ ra request, dependency và queue hoạt động thế nào; infrastructure metrics giải thích capacity và saturation. Không lớp nào đủ nếu đứng riêng.

Hãy định nghĩa KPI/SLI/SLO với mẫu số và trạng thái rõ, instrument RED/USE, propagate trace context, quản lý cardinality và dữ liệu nhạy cảm, rồi xây dashboard theo đường business → SLO → service → dependency → infrastructure. Alert nên dựa trên impact/error budget, có owner và runbook. Một hệ thống có khả năng quan sát tốt không chỉ nói “cái gì đang đỏ”, mà giúp đội ngũ xác định luồng nghiệp vụ nào bị ảnh hưởng, nguyên nhân nằm ở đâu và cần hành động nào.
