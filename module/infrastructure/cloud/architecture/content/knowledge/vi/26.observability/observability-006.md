# Dashboard theo hành trình người dùng và mục tiêu dịch vụ

## 1. Dashboard cần trả lời câu hỏi của người dùng và người vận hành

Một dashboard hạ tầng có thể cho biết CPU, memory, số pod và database connection đang ở mức nào. Những chỉ số đó hữu ích, nhưng không trực tiếp trả lời câu hỏi quan trọng nhất: **người dùng có hoàn thành được công việc họ đến để làm hay không?** CPU thấp không chứng minh quy trình đặt phòng hoạt động; tất cả pod có thể healthy trong khi API thanh toán timeout hoặc booking bị mắc kẹt ở một trạng thái trung gian.

Dashboard theo hành trình người dùng (user-journey dashboard) tổ chức dữ liệu quan sát quanh một mục tiêu nghiệp vụ, ví dụ tìm phòng, xem chi tiết, giữ phòng, thanh toán và nhận xác nhận. Nó kết nối:

- Kết quả người dùng nhìn thấy: tỷ lệ hoàn thành, lỗi, thời gian và các bước bỏ dở.
- Mục tiêu dịch vụ: SLI/SLO, error budget và mức độ ảnh hưởng.
- Tín hiệu kỹ thuật: latency, traffic, errors, saturation, queue, dependency và trace.
- Hành động vận hành: owner, runbook, phiên bản triển khai, vùng ảnh hưởng và liên kết điều tra.

Trong module **CLOUD_ARCHITECTURE**, thiết kế dashboard là một phần của kiến trúc quan sát. Nó liên hệ compute, network, database, API, event và external provider với trải nghiệm thực tế; qua đó hỗ trợ độ tin cậy, hiệu năng, bảo mật, khả năng mở rộng, chi phí và vận hành theo tư duy Well-Architected.

Ví dụ xuyên suốt: nền tảng đặt chỗ có hành trình từ tìm kiếm đến xác nhận booking. Search có thể trả về kết quả nhanh nhưng kết quả hết khả dụng; Booking API có thể tạo booking nhưng payment provider không phản hồi; payment đã thành công nhưng notification chưa được gửi. Chỉ dashboard thể hiện toàn hành trình mới giúp nhìn thấy trải nghiệm đầu-cuối.

## 2. Từ capability tới hành trình người dùng

Một journey mô tả chuỗi bước mà người dùng hoặc hệ thống đối tác thực hiện để đạt mục tiêu. Mỗi bước có thể đi qua nhiều frontend, API, service, database và nhà cung cấp bên ngoài.

Ví dụ journey đặt chỗ:

~~~mermaid
flowchart LR
    A["Search property"] --> B["View details"]
    B --> C["Check availability"]
    C --> D["Create booking hold"]
    D --> E["Authorize payment"]
    E --> F["Confirm booking"]
    F --> G["Send confirmation"]
~~~

Không phải mọi người dùng đều đi đúng một đường. Họ có thể thay đổi ngày, quay lại tìm kiếm, thử phương thức thanh toán khác hoặc hủy. Dashboard cần phân biệt nhánh hợp lệ, hành vi retry, lỗi kỹ thuật và việc người dùng chủ động rời đi.

### 2.1. Xác định ranh giới hành trình

Với mỗi journey, xác định:

1. **Actor:** người dùng, nhân viên, đối tác hay workload tự động?
2. **Trigger:** người dùng bắt đầu bằng hành động nào; event nào đánh dấu bắt đầu?
3. **Success outcome:** điều kiện nào chứng minh mục tiêu thực sự hoàn thành?
4. **Steps:** những bước quan trọng và trạng thái trung gian nào?
5. **Failure outcome:** lỗi, timeout, từ chối nghiệp vụ, abandon và trạng thái chưa rõ được phân biệt ra sao?
6. **Time boundary:** đo từ lúc nào tới lúc nào; có tính thời gian người dùng suy nghĩ hay chờ ngoài hệ thống không?
7. **Owner:** team nào chịu trách nhiệm cho từng bước và cho outcome tổng thể?

Ví dụ, tạo booking record chưa chắc là thành công nếu payment chưa được xác nhận và booking chưa được commit. Định nghĩa success cần phản ánh trạng thái nghiệp vụ cuối cùng mà sản phẩm cam kết với người dùng.

### 2.2. Journey map và service map không giống nhau

Journey map mô tả trải nghiệm theo bước nghiệp vụ. Service map mô tả các thành phần kỹ thuật, giao tiếp và dependency. Cần nối hai bản đồ này để đi từ triệu chứng người dùng tới nguyên nhân có thể xảy ra.

| Bước journey | Thành phần kỹ thuật có thể liên quan | Tín hiệu cần quan sát |
| --- | --- | --- |
| Search | Web/mobile, CDN, Search API, search cluster | Search success, latency, zero-result rate, timeout |
| View details | Property API, cache, object storage/CDN | Detail load time, cache hit, media failure |
| Availability | Inventory API, database, cache | Availability check success, stale data, DB latency |
| Booking hold | Booking API, DB, lock/queue | Hold success, conflict, transaction latency |
| Payment | Payment API/provider, event handler | Authorization success, timeout, unknown state, reconciliation backlog |
| Confirm | Booking DB, outbox/event broker | Confirmed booking rate, event lag, duplicate/retry |
| Notification | Notification worker, email/SMS provider | Delivery enqueue, delivery latency, provider error |

## 3. Phân biệt SLI, SLO, SLA và KPI

Dashboard có giá trị khi phân biệt mục tiêu đo lường với mục tiêu kinh doanh và cam kết hợp đồng.

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| SLI (Service Level Indicator) | Chỉ số đo một khía cạnh chất lượng dịch vụ | Tỷ lệ request search thành công dưới 800 ms |
| SLO (Service Level Objective) | Mục tiêu nội bộ cho SLI trong một cửa sổ thời gian | 99,9% search request hợp lệ đạt ngưỡng latency/error trong 30 ngày |
| SLA (Service Level Agreement) | Cam kết dịch vụ với khách hàng/đối tác, có thể gắn điều khoản và biện pháp khắc phục | Availability cam kết theo hợp đồng |
| KPI (Key Performance Indicator) | Chỉ số hiệu quả nghiệp vụ | Tỷ lệ chuyển đổi từ search sang booking |

KPI không thay thế SLI. Conversion rate giảm có thể do mùa vụ, giá, marketing hoặc sản phẩm; SLI search latency giúp đánh giá một nguyên nhân kỹ thuật khả dĩ. Ngược lại, SLI kỹ thuật tốt không chứng minh trải nghiệm hay conversion tốt.

### 3.1. Thiết kế SLI theo outcome

Một SLI tốt có định nghĩa đo rõ ràng:

- **Event nào được tính vào mẫu số?** Ví dụ request search hợp lệ, không tính health check hay traffic bot đã xác định.
- **Event nào được tính là tốt?** HTTP response thành công chưa đủ nếu payload trả về sai hoặc người dùng không thể tiếp tục.
- **Đo ở đâu?** Browser, API gateway, service hay database; mỗi vị trí phản ánh góc nhìn khác nhau.
- **Lọc theo điều kiện nào?** Region, platform, API version, tenant tier hoặc journey.
- **Cửa sổ đo:** phút, giờ, ngày, rolling 7/30 ngày?
- **Nguồn sự thật:** metric, event log, trace hoặc analytics pipeline nào?

Ví dụ availability SLI ở cấp API:

~~~text
availability SLI = good eligible requests / all eligible requests
~~~

Ví dụ latency SLI:

~~~text
latency SLI = eligible requests completed within threshold / all eligible requests
~~~

Tỷ lệ có thể được tính trên request, phiên người dùng hoặc journey attempt. Không trộn các đơn vị khác nhau trong cùng một mẫu số.

### 3.2. SLO cần có ngưỡng và cửa sổ

Ví dụ minh họa cho search:

- Availability SLO: 99,9% request hợp lệ trong rolling 30 ngày trả về phản hồi có thể sử dụng.
- Latency SLO: 99% request hợp lệ hoàn thành trong 800 ms trong rolling 30 ngày.
- Error budget tương ứng với phần không đạt mục tiêu trong cửa sổ.

Các ngưỡng trên chỉ là ví dụ, không phải chuẩn chung. Chọn mục tiêu từ yêu cầu người dùng, tác động kinh doanh, khả năng kỹ thuật và chi phí duy trì.

## 4. Đo hành trình bằng funnel và step-level SLI

Funnel giúp thấy người dùng rời khỏi journey ở bước nào. Nhưng không phải mọi lần rời đều là lỗi. Người dùng có thể tìm kiếm rồi quyết định không đặt; đó là abandonment tự nhiên. Dashboard phải tách abandonment dự kiến khỏi failure kỹ thuật.

Ví dụ:

| Bước | Attempts | Success | Error/timeout | Abandon/other | Success rate |
| --- | ---: | ---: | ---: | ---: | ---: |
| Search | 100.000 | 98.500 | 1.500 | 0 | 98,5% |
| View details | 70.000 | 68.600 | 700 | 700 | 98,0% |
| Availability | 42.000 | 40.740 | 840 | 420 | 97,0% |
| Booking hold | 12.000 | 11.640 | 240 | 120 | 97,0% |
| Payment | 11.640 | 11.058 | 466 | 116 | 95,0% |
| Confirmation | 11.058 | 10.947 | 55 | 56 | 99,0% |

Số liệu giả định. Cột abandon/other phải được định nghĩa cụ thể; không nên gán toàn bộ request không thành công là abandonment hoặc lỗi hệ thống. Nếu mỗi bước có nhiều lần retry, dashboard cần phân biệt attempt với unique journey.

### 4.1. Tỷ lệ hoàn thành end-to-end

Một tỷ lệ đơn giản:

~~~text
journey completion rate = completed journeys / eligible started journeys
~~~

Đây không phải lúc nào cũng bằng tích success rate từng bước. Người dùng có thể bỏ qua bước, thử lại, quay về hoặc đi theo nhánh khác. Nếu tính theo cohort journey ID và terminal state rõ ràng, dashboard sẽ phản ánh đúng outcome hơn.

### 4.2. Step latency và end-to-end latency

Đo thời gian cho từng bước để tìm bottleneck, đồng thời đo tổng thời gian từ trigger tới outcome. Tổng journey latency có thể bao gồm thời gian người dùng suy nghĩ hoặc chờ xác nhận bên ngoài; cần phân biệt:

- **System processing time:** thời gian backend/frontend xử lý.
- **Dependency wait time:** thời gian chờ database, queue hoặc provider.
- **User think time:** khoảng thời gian người dùng tương tác ngoài xử lý hệ thống.
- **End-to-end elapsed time:** toàn bộ khoảng từ bắt đầu đến kết thúc hành trình.

Không dùng end-to-end elapsed time làm API latency SLI nếu nó bao gồm thời gian người dùng không hoạt động.

## 5. Các tín hiệu kỹ thuật bổ trợ: RED và USE

Dashboard journey cho biết điều gì đang hỏng từ góc nhìn người dùng; các phương pháp RED/USE giúp định vị nguồn gây ra vấn đề.

### 5.1. RED cho service/request

| Tín hiệu | Câu hỏi | Ví dụ metric |
| --- | --- | --- |
| Rate | Service đang xử lý bao nhiêu request? | requests/sec, request theo route |
| Errors | Có bao nhiêu request lỗi? | error ratio, timeout, status code |
| Duration | Request mất bao lâu? | latency histogram, p50/p95/p99 |

### 5.2. USE cho resource

| Tín hiệu | Câu hỏi | Ví dụ metric |
| --- | --- | --- |
| Utilization | Tài nguyên được sử dụng bao nhiêu? | CPU, memory, disk, network utilization |
| Saturation | Có hàng đợi hoặc nhu cầu chưa được đáp ứng không? | CPU throttling, queue depth, connection wait |
| Errors | Tài nguyên phát sinh lỗi nào? | disk error, network drop, throttling |

RED phù hợp để quan sát service; USE phù hợp để quan sát tài nguyên. Không chỉ nhìn CPU utilization: queue depth và connection wait có thể cho thấy saturation trước khi CPU đạt 100%.

## 6. Distributed tracing và correlation xuyên journey

Để điều tra một journey chậm hoặc lỗi, cần liên kết các span ở nhiều service. Distributed tracing ghi nhận quan hệ cha/con giữa các operation, thời gian, status và một số attribute có kiểm soát.

~~~mermaid
flowchart LR
    B["Browser span"] --> G["API Gateway span"]
    G --> S["Search API span"]
    S --> C["Cache span"]
    S --> DB["Search DB/cluster span"]
    G --> BK["Booking API span"]
    BK --> SQL["Booking DB span"]
    BK --> P["Payment provider span"]
    BK --> Q["Outbox / broker span"]
    Q --> N["Notification worker span"]
~~~

Trace ID giúp nối các span; journey ID/business correlation ID giúp nhóm nhiều request và event thuộc cùng một hành trình. Cần xác định rõ semantics: trace ID thường theo một trace/transaction context; journey ID có thể tồn tại qua nhiều trace, retry hoặc thao tác kéo dài.

### 6.1. Context propagation

Khi service gọi service khác hoặc phát message, trace context cần được truyền theo chuẩn đã chọn, thường qua W3C Trace Context hoặc cơ chế tương thích. Consumer tạo span liên kết với message context; nếu message batch hoặc nhiều parent, có thể cần link thay vì ép một quan hệ cha/con đơn giản.

Context không được phép chứa access token, mật khẩu hoặc dữ liệu cá nhân. Baggage cần giới hạn kích thước và chỉ truyền attribute có ích, đã được kiểm duyệt.

### 6.2. Instrumentation tối thiểu

Mỗi span quan trọng nên có:

- Service name và operation/route chuẩn hóa.
- Environment, region, deployment version.
- Status/error classification.
- Duration và dependency name.
- Resource/workload identity ở mức an toàn.
- Journey step/business operation nếu có ý nghĩa.
- Sampling decision và trace links khi cần.

Không đưa raw URL chứa email, booking token hoặc query string nhạy cảm vào span. Chuẩn hóa route thành template như /bookings/{bookingId} thay vì lưu mọi ID thành tên operation riêng.

## 7. Liên kết metric, log và trace

Ba loại telemetry trả lời các câu hỏi khác nhau:

| Telemetry | Trả lời | Dùng trong dashboard |
| --- | --- | --- |
| Metrics | Điều gì đang tăng/giảm và ở phạm vi nào? | SLO, latency, error rate, queue, saturation và trend |
| Logs | Một sự kiện cụ thể đã xảy ra với chi tiết nào? | Error category, business state transition, audit và diagnostic context |
| Traces | Một request/journey đi qua những thành phần nào và mất thời gian ở đâu? | Critical path, dependency latency, retry và call graph |

Dashboard nên bắt đầu bằng metric tổng hợp, sau đó cung cấp drill-down sang trace và log có cùng trace ID/correlation ID. Không nên nhúng hàng nghìn log line hoặc trace đầy đủ vào một panel tổng quan.

### 7.1. Event trạng thái nghiệp vụ

Với hành trình nhiều bước hoặc asynchronous, cần event rõ ràng như:

- SearchStarted / SearchCompleted.
- AvailabilityChecked.
- BookingHoldCreated / BookingHoldExpired.
- PaymentAuthorized / PaymentFailed / PaymentUnknown.
- BookingConfirmed / BookingCancelled.
- NotificationQueued / NotificationDelivered.

Event cần schema, timestamp, source, version và correlation context. Event quan sát không nên làm thay đổi semantics của transaction nghiệp vụ; nếu phát event trực tiếp từ application, cần bảo đảm không bỏ sót giữa commit và publish, ví dụ transactional outbox.

## 8. Thiết kế dashboard theo câu hỏi và vai trò

Một dashboard lớn với mọi metric thường khó đọc và khó sử dụng khi incident. Tổ chức dashboard theo audience và luồng điều tra:

| Dashboard | Người dùng chính | Câu hỏi |
| --- | --- | --- |
| Executive/service health | Business owner, service owner | Người dùng có hoàn thành journey? SLO và xu hướng ra sao? |
| Journey overview | Product, SRE, support | Bước nào có lỗi, chậm hoặc abandonment tăng? |
| Service drill-down | Service team | Service nào gây lỗi/latency? Phiên bản nào? |
| Dependency/infrastructure | Platform/SRE | Database, cache, queue, network hoặc provider nào bão hòa? |
| Tenant/region view | Operations, customer success có quyền | Sự cố ảnh hưởng nhóm tenant/region nào? |
| Security/audit view | Security/compliance | Có truy cập bất thường hoặc lộ dữ liệu không? |

### 8.1. Bố cục journey overview

Một bố cục hữu ích có thể gồm:

1. **Top row:** journey completion, availability SLI, latency SLI, error budget còn lại.
2. **Journey funnel:** attempts/success/failure/abandon theo từng bước.
3. **Step latency:** p50/p95/p99 và tỷ lệ timeout.
4. **Impact breakdown:** region, platform, API version và tenant segment được phép.
5. **Dependency health:** service, database, cache, queue và external provider.
6. **Recent changes:** deploy, config/policy change và incident annotation.
7. **Drill-down:** trace, log, runbook và owner.

Dashboard nên có timestamp cập nhật cuối, timezone, bộ lọc mặc định và định nghĩa metric. Một panel không nói rõ cửa sổ dữ liệu hoặc đơn vị có thể khiến người vận hành ra quyết định sai.

## 9. Error budget và cảnh báo gắn với SLO

Error budget là phần lỗi cho phép tương ứng với SLO trong cửa sổ đánh giá. Với availability SLO 99,9%, budget theo tỷ lệ là 0,1% eligible events trong cửa sổ đó. Nếu traffic tăng, số lỗi tuyệt đối được phép cũng tăng theo mẫu số; nếu traffic thấp, một số lỗi có thể tạo tỷ lệ lớn.

### 9.1. Burn rate

Burn rate biểu thị tốc độ tiêu thụ error budget so với tốc độ cần thiết để dùng hết budget trong cửa sổ SLO.

~~~text
burn rate = observed error rate / allowed error rate
~~~

Ví dụ allowed error rate 0,1% và observed error rate 1% thì burn rate bằng 10. Nếu tốc độ đó kéo dài, budget sẽ cạn nhanh hơn kế hoạch mười lần.

### 9.2. Multi-window alert

Thay vì cảnh báo chỉ vì một spike ngắn, có thể kết hợp cửa sổ ngắn và dài để phát hiện burn nhanh có ý nghĩa:

- Cửa sổ ngắn: phát hiện sự cố đang diễn ra và cần phản ứng ngay.
- Cửa sổ dài: xác nhận ảnh hưởng kéo dài, tránh alert do spike rất ngắn.
- Cảnh báo theo SLO: ưu tiên những triệu chứng trực tiếp tiêu thụ error budget.
- Cảnh báo saturation: phát hiện sớm nguy cơ trước khi SLO bị vi phạm.

Ngưỡng chính xác cần hiệu chỉnh theo SLO window, độ nhạy và khả năng on-call. Không sao chép threshold từ một dịch vụ khác mà không hiểu traffic và error budget của service hiện tại.

### 9.3. Phân biệt alert và dashboard signal

Dashboard có thể hiển thị nhiều tín hiệu phục vụ điều tra; alert chỉ nên kích hoạt khi cần hành động. Alert cần có severity, owner, runbook, điều kiện clear và thông tin tác động. Tránh alert cho từng metric thấp/cao nếu không có hành động tương ứng.

## 10. Phân đoạn dữ liệu nhưng tránh cardinality bùng nổ

Phân tích theo region, platform, version hoặc tenant tier giúp xác định blast radius. Tuy nhiên, mỗi label có hàng triệu giá trị duy nhất có thể làm số time series tăng quá lớn.

Các nguyên tắc:

- Dùng label có cardinality thấp và giá trị được chuẩn hóa.
- Không đưa user ID, booking ID, session ID, email hoặc URL đầy đủ vào metric label.
- ID duy nhất nên nằm trong trace/log/event ở nơi có kiểm soát, không phải label metric mặc định.
- Dashboard tenant-specific có thể truy vấn từ analytics/log store có kiểm soát thay vì tạo metric series cho từng tenant.
- Giới hạn số chiều filter và số panel query nặng.
- Theo dõi series count, ingestion volume, query cost và retention.

Nếu cần phân tích top tenant, có thể dùng aggregation có giới hạn hoặc báo cáo định kỳ; không mặc định xuất mọi tenant thành label trên mọi metric.

## 11. Bảo vệ quyền riêng tư và phân quyền dashboard

Observability data có thể chứa thông tin khách hàng: URL, query, địa chỉ IP, lỗi chứa payload, email, booking ID hoặc trace attribute. Dashboard phải tuân theo data classification và access control như các hệ thống dữ liệu khác.

- Mask/redact thông tin cá nhân và secret ngay tại instrumentation/collector khi có thể.
- Không đưa payment data, access token, session cookie hoặc full payload vào logs/traces.
- Tách dashboard kỹ thuật nội bộ khỏi dashboard hỗ trợ khách hàng.
- Tenant chỉ được xem dữ liệu của tenant mình nếu sản phẩm có portal quan sát cho khách hàng.
- Hỗ trợ viên chỉ được truy cập thông tin cần cho case được giao, có audit.
- Giới hạn retention và quyền export/download.
- Bảo vệ telemetry backend bằng identity và network policy.

Không giả định dashboard là nội bộ nên mọi dữ liệu đều an toàn. Một screenshot hoặc link dashboard chia sẻ sai có thể tạo đường rò dữ liệu thứ cấp.

## 12. Dashboard cho đa vùng và đa tenant

Hành trình toàn cầu cần có cái nhìn tổng hợp và phân rã theo region/edge, bởi một khu vực có thể lỗi trong khi tổng thể vẫn xanh. Tương tự, tenant lớn có thể gặp sự cố dù latency trung bình của hệ thống tốt.

Nên cung cấp:

- Tổng thể toàn hệ thống và panel so sánh region.
- Availability/latency theo region và platform.
- Tenant tier/segment ở mức cardinality quản lý được.
- Correlation giữa deploy/version với SLO regression.
- Phân biệt lỗi do service nội bộ và external provider.
- Hiển thị traffic volume cùng error ratio để tránh tỷ lệ thấp từ mẫu số rất nhỏ gây hiểu nhầm.

Không lấy trung bình p95 của các region để ra p95 toàn hệ thống. Percentile không thể tổng hợp chính xác theo cách đó; hãy tính từ histogram/bucket hoặc query trên raw distribution đã được hỗ trợ.

## 13. Dashboard và kiến trúc observability pipeline

~~~mermaid
flowchart LR
    FE["Browser / Mobile telemetry"]
    API["Services / Workers"]
    INF["Infra / Cloud metrics"]
    COL["Collectors / OpenTelemetry"]
    M["Metrics backend"]
    L["Log backend"]
    T["Trace backend"]
    EVT["Business event store"]
    DASH["Journey dashboards"]
    ALERT["Alerting / SLO engine"]
    FE --> COL
    API --> COL
    INF --> M
    COL --> M
    COL --> L
    COL --> T
    API --> EVT
    M --> DASH
    L --> DASH
    T --> DASH
    EVT --> DASH
    M --> ALERT
~~~

Pipeline cần chú ý sampling, buffering, backpressure, network cost, regional routing, retention và quyền truy cập. Khi hệ thống gặp sự cố lớn, telemetry không được làm quá tải chính workload đang cần quan sát. Có thể ưu tiên metric/SLO và error log, giảm sampling cho trace bình thường nhưng giữ trace lỗi hoặc tail-based sampling khi nền tảng hỗ trợ.

### 13.1. OpenTelemetry và semantic conventions

OpenTelemetry cung cấp API/SDK và protocol để instrument, collect và export metrics, logs, traces. Dùng semantic conventions và resource attributes nhất quán giúp dashboard liên kết service, deployment, cloud region và operation mà không phải viết mapping riêng cho từng team.

Tổ chức nên chuẩn hóa service.name, deployment.environment, cloud.region, service.version và các attribute phù hợp. Tránh cho mỗi nhóm tự đặt tên metric/label khác nhau; naming không thống nhất khiến dashboard khó tổng hợp và alert dễ sai.

## 14. Điều tra từ triệu chứng tới nguyên nhân

Một flow điều tra có thể như sau:

1. Xác nhận journey completion hoặc SLO nào suy giảm và từ thời điểm nào.
2. Xem bước nào có error/latency tăng, region/platform/tenant segment nào bị ảnh hưởng.
3. Kiểm tra traffic volume, deploy/change annotation và các sự cố dependency.
4. Mở trace mẫu để xác định span chậm/lỗi trên critical path.
5. Đối chiếu log có correlation ID để hiểu error classification và business state.
6. Xem RED/USE của service/resource liên quan: saturation, queue, DB, cache, network.
7. Kiểm tra trạng thái cuối trong database/event để xác định giao dịch hoàn tất, thất bại hay chưa rõ.
8. Áp dụng mitigation theo runbook và theo dõi SLO phục hồi.
9. Sau incident, ghi lại nguyên nhân, thời gian phát hiện, thời gian khắc phục và thay đổi cần thiết.

Không suy luận root cause chỉ từ tương quan. Ví dụ CPU tăng cùng lúc với lỗi có thể là nguyên nhân hoặc hệ quả của retry storm; trace và dependency signals cần xác nhận.

## 15. Chất lượng dashboard và anti-pattern

| Anti-pattern | Vì sao gây khó | Cách cải thiện |
| --- | --- | --- |
| Dashboard chỉ có CPU/memory | Không cho biết journey có thành công không | Bổ sung outcome và SLI cấp người dùng |
| Chỉ nhìn average latency | Che giấu tail latency | Hiển thị histogram/p50/p95/p99 đúng cách |
| Trộn user abandon vào server error | Làm SLI sai và dẫn tới ưu tiên sai | Phân loại terminal outcome và eligibility |
| Metric label chứa ID duy nhất | Cardinality/cost tăng đột biến | Đưa ID vào trace/log có kiểm soát |
| Một dashboard cho mọi audience | Quá tải thông tin, khó hành động | Tách overview và drill-down theo vai trò |
| Alert cho mọi panel | Alert fatigue | Alert theo SLO, impact và hành động cụ thể |
| Không hiển thị deploy/version | Khó liên kết regression với change | Thêm annotation và filter version |
| Không có owner/runbook | Phát hiện nhưng không biết xử lý | Gắn service owner, severity và runbook |
| Trung bình percentile giữa region | Kết quả thống kê sai | Tổng hợp histogram/distribution phù hợp |
| Dashboard không có timezone/freshness | Đọc sai cửa sổ dữ liệu | Hiển thị time range, timezone và last update |

## 16. Bài thực hành: thiết kế journey dashboard cho booking platform

**Bối cảnh giả định:** nền tảng có web/mobile, API gateway, Search Service, Booking Service, Payment integration, PostgreSQL, Redis, event broker và Notification Worker. Người dùng báo rằng tỷ lệ hoàn thành booking giảm, nhưng dashboard hiện tại chỉ hiển thị CPU và HTTP 5xx ở gateway.

### Nhiệm vụ

1. Vẽ journey từ search đến booking confirmation và liệt kê nhánh success, business rejection, user abandon, timeout, retry và unknown state.
2. Chọn ít nhất ba SLI outcome/end-to-end và ba SLI kỹ thuật theo bước; định nghĩa mẫu số, điều kiện tốt, cửa sổ và nguồn dữ liệu.
3. Đề xuất SLO availability/latency theo capability, giải thích business impact và error budget.
4. Thiết kế event/correlation schema để nối browser, API, worker, payment provider và database state.
5. Xây dashboard overview với funnel, completion rate, step latency, region/platform và dependency health.
6. Xây service drill-down dùng RED/USE và trace để tìm critical path.
7. Thiết kế burn-rate alert nhiều cửa sổ, severity, owner và runbook.
8. Xác định label nào có cardinality cao/nhạy cảm; lập quy tắc redaction và access control.
9. Mô phỏng ba tình huống: Search latency tăng, payment provider timeout, notification backlog; mô tả dashboard sẽ chỉ ra điều gì.
10. Viết ADR về telemetry pipeline, sampling, retention, chi phí và SLO ownership.

### Mẫu SLI catalog

| Journey/capability | SLI | Good event | Eligible event | Dimension |
| --- | --- | --- | --- | --- |
| Search | Search availability | Kết quả hợp lệ được trả trong timeout | Search request hợp lệ | Region, app version |
| Search | Search latency | Hoàn thành dưới threshold | Search request hợp lệ | Query class, region |
| Booking | Hold success | Hold được tạo hợp lệ | Hold attempt đủ điều kiện | Region, booking path |
| Payment | Authorization outcome | Được provider xác nhận theo semantics | Payment attempt, phân loại unknown riêng | Provider, method, region |
| Journey | Booking completion | Booking ở terminal confirmed state | Journey attempt hợp lệ | Platform, region |
| Notification | Delivery latency | Notification được provider nhận trong ngưỡng | Notification event | Channel, provider |

### Tiêu chí hoàn thành

- Journey có trigger, step, terminal outcome và owner rõ.
- SLI/SLO phản ánh outcome thực, có numerator/denominator và cửa sổ đo.
- Dashboard tách business rejection, user abandon và technical failure.
- Trace/log/event có correlation nhưng không lộ secret/PII.
- Có drill-down từ SLO tới step, service, dependency và trace.
- Alert theo burn rate và có owner/runbook.
- Có phân tích region/tenant an toàn, kiểm soát cardinality và chi phí.
- Dashboard có thể hỗ trợ điều tra sự cố mà không chỉ hiển thị trạng thái hạ tầng.

## 17. Checklist Well-Architected trước khi phát hành journey dashboard

- [ ] Journey gắn với mục tiêu người dùng và business owner.
- [ ] Trigger, step, terminal state, retry và abandonment được định nghĩa.
- [ ] Service map/dependency map liên kết với journey map.
- [ ] Mỗi SLI có good event, eligible event, nguồn dữ liệu và cửa sổ đo rõ ràng.
- [ ] SLO bắt nguồn từ tác động nghiệp vụ và có error budget.
- [ ] Funnel phân biệt success, business rejection, user abandon, technical failure và unknown state.
- [ ] Có end-to-end latency và step latency; không trộn user think time với system processing time.
- [ ] RED/USE hỗ trợ drill-down tới service và resource saturation.
- [ ] Distributed tracing/context propagation nối các service và asynchronous event.
- [ ] Metrics, logs, traces và business events có correlation và retention phù hợp.
- [ ] Alert có severity, owner, runbook, action và burn-rate semantics.
- [ ] Dashboard hiển thị time range, timezone, freshness, definition và deployment annotation.
- [ ] Region/tenant dimension có cardinality được kiểm soát; không dùng ID duy nhất làm metric label.
- [ ] PII, token, secret và payload nhạy cảm được loại bỏ/mask.
- [ ] Dashboard/query/export được phân quyền và audit.
- [ ] Sampling, backpressure, pipeline HA, retention và telemetry cost được đánh giá.
- [ ] Có bài tập incident để chứng minh dashboard hỗ trợ tìm nguyên nhân và quyết định mitigation.
- [ ] ADR xác định owner, SLO review cadence và vòng đời dashboard.

**Điểm cốt lõi:** dashboard theo hành trình người dùng bắt đầu từ outcome, chuyển outcome thành SLI/SLO có định nghĩa rõ, rồi nối với step, service, dependency và resource telemetry. Khi funnel, metric, log, trace, alert và runbook được liên kết, đội ngũ có thể nhận biết tác động thực, tìm đúng bottleneck và ưu tiên phục hồi theo trải nghiệm người dùng thay vì chỉ dựa vào trạng thái máy chủ.
