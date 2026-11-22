# Dashboard, Azure Monitor Workbook và báo cáo vận hành

Trong module **CLOUD_PROVIDERS_AZURE**, người học khám phá hệ sinh thái Microsoft Azure từ subscription, resource group và Microsoft Entra ID đến mạng ảo, dịch vụ tính toán, lưu trữ và dữ liệu; học cách triển khai, giám sát, bảo vệ và kiểm soát chi phí kiến trúc ứng dụng trên Azure. Thuộc chương **Giám sát và quan sát hệ thống**, bài học này tập trung vào ba sản phẩm đầu ra của hoạt động observability: **dashboard theo dõi**, **Azure Monitor Workbook tương tác** và **báo cáo vận hành có ngữ cảnh, người chịu trách nhiệm và hành động**.

Ví dụ xuyên suốt: nhóm vận hành một nền tảng đặt hàng gồm ứng dụng Java trên Azure App Service hoặc AKS, Azure SQL Database, Azure Service Bus và Key Vault. Trong ca trực, họ cần biết ngay **đơn hàng có xử lý được không, lỗi ở đâu và nên làm gì**. Ban quản lý lại muốn bản tổng hợp tuần: mức độ đạt SLO, sự cố ảnh hưởng khách hàng, chi phí và hành động khắc phục. Một trang biểu đồ đơn thuần không đáp ứng được cả hai việc.

Sau khi học xong, bạn có thể:

- Phân biệt **Azure portal dashboard**, **Azure Monitor Workbook**, **Azure Managed Grafana**, **Power BI** và **báo cáo vận hành** theo mục đích.
- Chọn nguồn **Azure Monitor Metrics, Log Analytics/KQL, Application Insights, resource diagnostics, Activity Log và Azure Resource Graph** một cách đúng ngữ nghĩa.
- Thiết kế các chỉ số **SLI/SLO, error rate, availability, latency p95/p99, saturation, freshness, queue backlog và cost** có denominator, cửa sổ thời gian và owner rõ.
- Tạo Workbook có **time range, resource/subscription/environment parameters**, biểu đồ, bảng drill-down, liên kết điều tra và chú thích hữu ích.
- Viết các truy vấn **KQL có giới hạn thời gian, hiệu quả chi phí và an toàn dữ liệu**; phân biệt workspace-based schema với legacy tables.
- Xây báo cáo **hằng ngày/hằng tuần, incident review và executive summary** dựa trên cùng định nghĩa metrics với dashboard.
- Quản lý Workbook dưới **RBAC/IaC/version control**, thiết kế alert/action group riêng, tránh nhầm dashboard với hệ thống cảnh báo.
- Kiểm thử dữ liệu và kết quả, thiết lập runbooks cho các sự cố phổ biến: bảng rỗng, dữ liệu trễ, bất thường chi phí hoặc dashboard “xanh” giả.

## 1. Dashboard, Workbook và báo cáo vận hành giải quyết việc gì?

Một hệ thống có thể sinh hàng triệu điểm telemetry mỗi ngày nhưng vẫn không giúp được người trực khi không có **bức tranh vận hành được tổ chức theo câu hỏi**.

```text
Java applications + Azure resources
             |
      metrics / logs / traces / events
             |
             v
 Azure Monitor / Log Analytics / Application Insights
             |
      Query + aggregation + context
             |
       +-----+---------------+-----------------+
       |                     |                 |
       v                     v                 v
   Dashboard              Workbook        Report / Review
   "Now" view             "Investigate"   "What happened,
   service health         interactive     why, what next?"
       |                     |                 |
       +-----------+---------+-----------------+
                   |
             Owner / action
                   |
        Incident response + learning
```

### 1.1. Ba lớp đầu ra

| Đầu ra | Câu hỏi chính | Đối tượng | Chu kỳ | Ví dụ |
|---|---|---|---|---|
| **Dashboard vận hành** | *Có vấn đề cần hành động ngay không?* | On-call, SRE, NOC | Phút/giờ | Error rate, p95 latency, queue backlog, tình trạng alerts |
| **Azure Monitor Workbook** | *Phần nào đang lỗi, từ khi nào, trên tài nguyên nào?* | Engineer, incident commander, platform | Tương tác, điều tra | Chọn cluster/namespace, drill-down KQL, bảng tài nguyên |
| **Báo cáo vận hành** | *Đã đạt mục tiêu chưa, nguyên nhân và ai sửa?* | Engineering managers, product, security, FinOps | Ngày/tuần/tháng | SLO đạt 99,94%, 2 incidents, ngân sách, action items |

Một Workbook có thể dùng làm dashboard trực ca, và portal dashboard có thể chứa một số visualizations của Workbook. Tuy nhiên nên **thiết kế theo công việc của người dùng**, không ép mọi biểu đồ và báo cáo vào một trang duy nhất.

### 1.2. Nguyên tắc “từ tín hiệu đến quyết định”

Mỗi panel quan trọng nên trả lời đủ:

1. Đang đo **điều gì** và phục vụ **mục tiêu nào**?
2. Dữ liệu đến từ **nguồn nào**, thuộc service/region nào?
3. Khoảng thời gian, múi giờ, aggregation và đơn vị là gì?
4. Thế nào là **bình thường/cảnh báo/nguy cấp** theo SLO hoặc capacity?
5. Nếu bất thường, **drill-down ở đâu** và **runbook/owner là ai**?
6. Nếu dữ liệu biến mất, panel có hiển thị **no data** rõ ràng không?

Một đồ thị “CPU 80%” không đủ nếu workload luôn chạy tốt tại CPU 80%. Ngược lại, 0 lỗi hiển thị khi log ingestion ngừng có thể đánh lừa operator.

## 2. Vị trí của các công cụ Azure trong kiến trúc observability

| Công cụ | Đặc điểm | Dùng tốt khi | Không nên giả định |
|---|---|---|---|
| **Azure portal Dashboard** | Các tiles được pin/compose từ những views được hỗ trợ, có cơ chế chia sẻ/quản lý | Wallboard và health overview gọn | Tự là alert engine hoặc báo cáo lịch sử bất biến |
| **Azure Monitor Workbook** | Interactive canvas gồm parameters, text, queries, charts, tables và links | Điều tra nhiều tài nguyên, dashboard theo ngữ cảnh | Cùng mọi tính năng/UX với Power BI hoặc Grafana |
| **Azure Monitor Metrics** | Time-series platform/custom metrics theo resource/namespace | Latency, CPU, request rate, saturation với độ trễ thấp | Mọi log đều truy vấn được như metric |
| **Log Analytics** | KQL trên logs trong workspace/tables có dữ liệu | Error detail, joins, traces, điều tra và trend | Table tên giống nhau trên mọi workspace/schema |
| **Application Insights** | Telemetry app: requests, dependencies, exceptions, traces | Java API performance, distributed traces | Sampling không làm sai raw-count-based SLI |
| **Azure Managed Grafana** | Dashboards dựa trên nhiều data sources theo connectors | Nhiều series/teams, Kubernetes/Prometheus và tương tác Grafana | Tự được cấp mọi Azure RBAC permissions |
| **Power BI** | Mô hình báo cáo phân tích/kinh doanh, chia sẻ & governance | Executive reporting và xu hướng nhiều kỳ | Live operational alert hoặc near-real-time query mặc định |
| **Azure Monitor Alerts** | Rules, evaluation, action groups, action/response | Thông báo sự cố có SLA/owner | Cần người mở dashboard thì mới gửi cảnh báo |

### 2.1. “Dashboard” không phải hệ thống cảnh báo

Một dashboard chỉ hiển thị dữ liệu khi có người nhìn vào. **Alert rules** đánh giá tín hiệu theo schedule/query/metric, có threshold, action group và routing. Khi metric vượt ngưỡng, **incident system** tạo ticket/page; dashboard giúp xác định tác động và điều tra. Không dùng màu đỏ trên Workbook như phương án duy nhất để đánh thức on-call.

### 2.2. “Workbook” không phải kho lưu telemetry

Workbook **lưu định nghĩa visualizations, queries, parameters và layout**. Dữ liệu gốc nằm trong Log Analytics, Azure Monitor Metrics, Resource Graph hoặc nguồn được hỗ trợ. Nếu log retention hết hạn, một Workbook được lưu từ năm trước cũng **không tự giữ dữ liệu năm trước**.

### 2.3. “Báo cáo” không phải ảnh chụp dashboard tùy tiện

Báo cáo có **thời kỳ đóng số liệu**, người/nhóm sở hữu, định nghĩa KPI, nguồn tham chiếu, caveat về dữ liệu chưa đầy đủ và hành động được giao. Ảnh dashboard không có timestamp, query/filter và sample completeness không đủ cho audit.

## 3. Luồng dữ liệu từ ứng dụng Java và Azure resources

Một stack tham chiếu:

```text
Java API / Spring Boot (App Service or AKS)
       |
       +--> OpenTelemetry / Application Insights instrumentation
       |       requests, exceptions, dependencies, traces
       |
       +--> application structured logs
       |
Azure SQL / Service Bus / Key Vault / App Service / AKS
       |
       +--> Azure Monitor platform metrics
       +--> Diagnostic settings -> Log Analytics / other destinations
       +--> Activity Log (control-plane events)
       |
       v
Azure Monitor / Log Analytics workspaces
       |
       +--> Metrics Explorer -> chart / alert
       +--> Logs (KQL) -> Workbook / scheduled query alert
       +--> Workbooks -> interactive incident view
       +--> dashboards -> operations overview
       |
       v
Daily/weekly reporting pipeline (approved query/export)
       |
       v
Operations review + incident action tracker
```

### 3.1. Không phải mọi telemetry tự vào cùng một workspace

Mỗi Azure resource có **metric namespaces và diagnostic settings** khác nhau. Một số logs được định tuyến vào **resource-specific tables**, số khác vào **AzureDiagnostics** (legacy), còn Application Insights dùng các tables/schema riêng tùy workspace-based hoặc model cũ. Nếu một KQL query không thấy kết quả, kiểm tra **resource scope, table name, ingestion và retention**, đừng tự đoán rằng tài nguyên không phát sinh lỗi.

### 3.2. Metrics và logs có độ tươi khác nhau

- **Metrics:** thường được tối ưu cho numerical time series và alert/chart với aggregation định nghĩa sẵn.
- **Logs:** hữu ích cho event-level details, correlation, filtering và joins; ingest latency phụ thuộc nguồn/pipeline và có thể có sampling/transformations.
- **Traces:** cho thấy quan hệ request → dependency → exception; sampling có thể làm thiếu những request chi tiết.
- **Activity Log:** ghi thay đổi management plane và service health/control events, không thay log xử lý đơn hàng.

Không đặt một ngưỡng “last 5 min no errors” trên logs mà không giám sát **ingestion freshness**, bởi không có events có thể là không có traffic hoặc pipeline telemetry đã đứt.

### 3.3. Telemetry nào cần bật trong Java?

Một Java API nên gửi:

- Request count, duration, result, route template, HTTP status.
- Dependency time/duration/error (SQL, Service Bus, Key Vault) theo instrumentation hỗ trợ.
- Exceptions với stack context được **redact**.
- Trace/span IDs để nối logs; không đưa passwords, access tokens, customer PII vào attributes.
- Business metrics như **orders accepted, payment confirmed, backlog age**, định nghĩa rõ đơn vị.

Nếu dùng OpenTelemetry/Java agent hay Azure Monitor OpenTelemetry distribution, phải kiểm tra **version, exporters, sampling và SDK compatibility**. Không coi “SDK gửi thành công” đồng nghĩa panel đã có mọi loại telemetry; cần thử end-to-end trên workspace thật.

## 4. Từ mục tiêu vận hành đến SLI/SLO

Một dashboard tốt bắt đầu từ **khách hàng trải nghiệm gì**, không bắt đầu từ “có sẵn metric CPU nào”.

### 4.1. SLI là gì?

**Service-Level Indicator (SLI)** là chỉ số đo chất lượng dịch vụ thực sự, ví dụ:

- **Availability SLI:** tỷ lệ request hợp lệ hoàn tất thành công.
- **Latency SLI:** tỷ lệ requests được phục vụ trong một ngưỡng thời gian.
- **Freshness SLI:** tỷ lệ đơn hàng xử lý/ghi nhận trước deadline.
- **Correctness SLI:** tỷ lệ giao dịch không cần manual reconciliation/rollback.

**Service-Level Objective (SLO)** là mục tiêu đặt cho SLI trong một khoảng thời gian. Một SLO có thể là “99,9% requests đủ điều kiện thành công trong rolling 30 ngày” hoặc “99% đơn hàng hoàn tất trong 2 phút”.

### 4.2. Availability không bằng “HTTP 200 trên health endpoint”

Ví dụ API trả HTTP 200 cho `/health` nhưng thanh toán luôn 500 hoặc xử lý đơn bị kẹt. Health probe availability là tín hiệu **thành phần**, không thể thay **end-user request SLI**. Cần phân loại:

- Requests **đủ điều kiện** trong denominator là gì? Có loại bỏ bad requests (4xx) của client không?
- Failures gồm những gì: 5xx, timeout, business error, 429 do overload?
- Có phân biệt API không nhận traffic, blackhole hoặc mất telemetry không?
- Time window là rolling 1h/24h/30d hay calendar month?

### 4.3. Công thức cơ bản

Với `eligibleRequests` là tổng requests đủ điều kiện và `goodRequests` là số thành công theo hợp đồng:

```text
Availability (%) = 100 * goodRequests / eligibleRequests
Error rate (%)   = 100 * badRequests  / eligibleRequests
```

Giả sử trong một ngày có 100.000 requests đủ điều kiện, 99.920 requests đạt tiêu chí: availability **99,92%**. Nếu SLO là **99,9%**, ngày đó đạt SLO; nhưng không thể suy rằng rolling 30 ngày cũng đạt khi chưa xem cả 30 ngày.

### 4.4. Percentile latency

`p95 = 800 ms` nghĩa là **xấp xỉ 95% mẫu có thời gian không quá 800 ms** trong tập/window được tính, không phải “95% requests nhanh hơn trung bình 800 ms”. **Không lấy trung bình của p95 từng node** rồi gọi đó là p95 toàn dịch vụ; phải tính percentile trên phân phối/mẫu/metric aggregation phù hợp.

### 4.5. Error budget

SLO 99,9% cho phép khoảng **0,1% bad events** trong denominator đã định nghĩa. Với SLO đo theo thời gian luôn-available trong một tháng 30 ngày, 0,1% thời gian tương đương **43,2 phút** — nhưng đây là *time-based budget*; không được áp con số phút đó trực tiếp cho request-based SLO mà không có giả định traffic phân bố đều.

### 4.6. KPI dictionary có owner

| KPI | Định nghĩa tối thiểu | Mục đích | Chủ sở hữu |
|---|---|---|---|
| Availability | Good/eligible requests; window 30 ngày | SLO | API owner/SRE |
| API p95 | Percentile latency; 5 phút/1 giờ | User experience | Backend |
| API error rate | 5xx + timeouts theo contract, chia eligible | Alert | On-call |
| Queue oldest message age | Thời gian chờ của thông điệp cũ nhất theo nguồn đo hỗ trợ | Backlog | Worker owner |
| Database connections | Active/limit; unit/count | Saturation | Data owner |
| Job completion | Completed jobs / eligible jobs | Business workflow | Operations |
| Telemetry freshness | Now - last confirmed event ingestion | Data quality | Platform |
| Cost per transaction | Phân bổ cost / completed transactions | FinOps | Service owner |

Viết rõ nguồn, truy vấn, độ trễ, retention, đơn vị, excluded cases và owner **trước** khi xây panel. Khi định nghĩa thay đổi, version dashboard/report.

## 5. Lựa chọn tín hiệu theo RED, USE và golden signals

### 5.1. RED cho dịch vụ request/response

**RED = Rate, Errors, Duration.**

| Tín hiệu | Ví dụ | Mục tiêu |
|---|---|---|
| Rate | Requests/second của Java API | Phát hiện mất traffic/burst |
| Errors | 5xx ratio/timeout rate | User impact |
| Duration | p50/p95/p99 latency | Slowdowns và tail latency |

Không chỉ chọn các metric dễ hiển thị; với workload đồng bộ, RED là một khởi điểm hữu ích.

### 5.2. USE cho tài nguyên

**USE = Utilization, Saturation, Errors.** Ví dụ:

| Thành phần | Utilization | Saturation | Errors |
|---|---|---|---|
| AKS node | CPU/memory utilization | CPU throttling, pod scheduling pressure | Node NotReady, OOMKill |
| App Service Plan | CPU/memory theo metric được hỗ trợ | Queue/concurrent requests theo nguồn thích hợp | App restarts, HTTP errors |
| Azure SQL | CPU/DTU/vCore/memory theo tier | Connections, waits, storage pressure | Connection failures, deadlocks |
| Service Bus | Message/throughput/capacity metrics | Backlog, active messages, age theo instrumentation | Dead-letter, send/receive failures |

Một service có CPU thấp vẫn có thể lỗi vì database locks hoặc queue consumer ngừng. **Saturation và user-impact SLI** nên được đặt cạnh resource utilization.

### 5.3. Các tín hiệu “business”

Ở hệ thống đơn hàng, “API request thành công” không đủ nếu đơn không được giao cho worker. Cần thêm:

```text
orders_accepted
orders_persisted
orders_published_to_queue
orders_completed
orders_failed
oldest_unprocessed_order_age
```

Các tên trên là **metric/event names mẫu**, không phải các Azure built-in metrics. Triển khai chúng qua OpenTelemetry/custom metrics/logs có dimension cardinality và quyền phù hợp. Dashboard nên cho thấy **hành trình đơn hàng**, không chỉ độ khỏe container.

## 6. Thiết kế một Operations Overview dashboard

### 6.1. Sơ đồ bố cục đề xuất

```text
+---------------------------------------------------------------------+
| ORDERS PLATFORM — PROD / Southeast Asia — Last 60 min              |
| Owner: Orders SRE | Last telemetry: 11:25 UTC | Runbook | On-call  |
+--------------------+-------------------+----------------------------+
| Availability SLI   | Failed orders     | Critical open incidents    |
| 99.94%             | 87                | 1                          |
+--------------------+-------------------+----------------------------+
| Requests/s                    | API p95 & p99 latency                |
| Errors / good traffic         | Target p95 < 800ms                   |
+-------------------------------+-------------------------------------+
| Queue backlog / oldest age    | Worker throughput and failures       |
+-------------------------------+-------------------------------------+
| SQL saturation / connections  | AKS/App Service capacity            |
+-------------------------------+-------------------------------------+
| Deployment annotations        | Data freshness / missing telemetry  |
+-------------------------------+-------------------------------------+
| Drill-down: Workbook / Traces / Logs / Incident board / Cost       |
+---------------------------------------------------------------------+
```

Đây là bố cục **minh họa**, không phải screenshot Azure Portal. Hãy điều chỉnh theo màn hình và đối tượng: wallboard chỉ cần signals và links; Workbook điều tra có nhiều bảng chi tiết hơn.

### 6.2. Panel đầu phải trả lời “cần page ai?”

Ưu tiên **business SLI, critical incidents và data freshness**, tiếp theo là dependency indicators. Đừng để 20 biểu đồ CPU chiếm nửa màn hình trước khi hiển thị error rate. Mỗi panel có tên ngắn, đơn vị, target line và link runbook nếu có.

### 6.3. Màu sắc có nghĩa

- **Bình thường:** mục tiêu đạt, dữ liệu đủ tươi.
- **Cảnh báo:** tăng rủi ro, cần quan sát/triage.
- **Nguy cấp:** SLO/error budget hoặc user impact vi phạm.
- **No data / unknown:** không được tô xanh hoặc ép thành 0.

Dùng **text labels, icon hoặc ngưỡng** bên cạnh màu để người xem không phụ thuộc chỉ vào phân biệt màu sắc; cân nhắc accessibility.

### 6.4. Context không được ẩn

Một chart “p95 = 1.200” cần hiển thị **ms**, **range last 1h**, **environment production**, **region**, **aggregation**, **last refresh**. Không trộn data của dev và prod khi filter rỗng hoặc time range lẫn timezone.

## 7. Azure Monitor Metrics Explorer và portal dashboard

### 7.1. Khi nào dùng Metrics Explorer?

Để xem platform metrics của một hoặc nhiều Azure resources theo khả năng, chọn namespace/metric, aggregation, time range, dimension split và chart type. Metrics Explorer giúp xây nhanh một visualization rồi **pin** lên Azure portal dashboard khi tính năng hiện tại hỗ trợ.

### 7.2. Quy trình Portal

1. Vào **Azure Monitor → Metrics**, hoặc mở resource → **Monitoring → Metrics**.
2. Chọn đúng subscription/resource scope, **metric namespace** và metric name.
3. Chọn aggregation **Avg/Sum/Count/Min/Max** theo meaning của metric, không tự chọn Avg cho counter khi cần sum.
4. Chọn time range và granularity phù hợp tần suất thu thập.
5. Dùng dimensions để split theo instance/region/status nếu metric hỗ trợ.
6. Kiểm tra biểu đồ có dữ liệu và đơn vị đúng.
7. Pin visualization lên **Azure portal dashboard** nếu UI/metric supports.
8. Chia sẻ dashboard với nhóm vận hành theo RBAC và quyền nguồn dữ liệu.

### 7.3. Sum khác Average như thế nào?

Nếu một metric biểu diễn số requests mỗi khoảng, **Sum** qua nhiều time bins có thể có nghĩa tổng requests; **Average** biểu diễn mức trung bình của các samples đã tập hợp. Với CPU percentage, **Average** thường có ích hơn Sum; nhưng p95 latency không được tính bằng việc lấy Average của các percentile. Đọc **metric definition/unit/aggregation supported** trước khi dùng.

### 7.4. Resource-specific schema

Một resource có thể có metric `Requests`, tài nguyên khác có `TotalRequests` hoặc namespace khác nhau. **Không hard-code tên metric theo trí nhớ** cho mọi dịch vụ. Dùng Portal Metrics Explorer hoặc CLI `az monitor metrics list-definitions` để lấy tên chính xác từ resource đang giám sát.

### 7.5. Dashboard sharing

Dashboard cá nhân và dashboard được chia sẻ có cách lưu/phân quyền khác nhau. Dashboard được chia sẻ có thể được quản lý như Azure resource và chịu quyền truy cập của người dùng; ngoài quyền đọc dashboard, người xem **còn cần quyền đọc những Azure resources/queries đằng sau tiles**. Thấy layout không đồng nghĩa thấy dữ liệu.

## 8. Azure Monitor Workbook là gì?

**Azure Monitor Workbooks** cung cấp không gian làm việc tương tác để ghép **text hướng dẫn, parameters, queries, charts, grids, metrics và links** thành một trang điều tra vận hành. Workbook phù hợp khi operator cần chuyển **environment → service → resource → thời gian → error detail**, không phải mở hàng chục tab rời rạc.

### 8.1. Những khối xây dựng thường dùng

| Khối | Vai trò | Ví dụ |
|---|---|---|
| **Text/Markdown** | Hướng dẫn, assumptions, links runbook | “Nguồn dữ liệu trễ tối đa 5 phút” |
| **Parameters** | Time range, resource, environment, region, service | Chọn `prod` và `last 1h` |
| **Metrics** | Azure Monitor metrics từ resources được phép | CPU % theo App Service Plan |
| **Logs queries** | KQL trong Log Analytics/Application Insights | Request failure và p95 latency |
| **Resource Graph** | Liệt kê/kiểm tra thông tin resources ở scope được phép | Kết nối resource IDs với subscriptions |
| **Grid / chart / tiles** | Trình bày dữ liệu dễ đọc | Top 10 failing routes, trend theo thời gian |
| **Links / drill-down** | Dẫn đến chi tiết truy vết, Portal, tickets | Link Application Insights transaction search |
| **Conditional visibility/formatting** | Chỉ hiển thị thông tin phù hợp theo params/kết quả | Runbook cảnh báo khi thiếu data |

Khả năng của từng data source, visualization và parameter type phụ thuộc **Azure Monitor Workbook editor/region/version**. Không nên khẳng định mọi tile ngoài Portal đều pin được hoặc mọi chart type có cùng options.

### 8.2. Workbook khác dashboard tile ở điểm nào?

Workbook có thể chứa một **flow điều tra nhiều bước**: time picker thay các queries, resource picker định scope, bảng top errors dẫn tới drill-down. Portal dashboard phù hợp **overview cố định** và thường chọn vài signals cốt lõi. Khi cần cả hai, **pin hoặc dẫn liên kết đến Workbook** từ dashboard theo chức năng được hỗ trợ, không copy 30 queries chạy riêng trên wallboard.

### 8.3. Workbook không có dữ liệu thì không phải luôn do Workbook lỗi

Người xem có thể không có quyền đọc workspace, chọn nhầm resource hoặc time range không có telemetry, KQL đã sai schema, hoặc Log Analytics chưa ingest. Workbooks không lưu telemetry. Vì vậy phần đầu trang nên có **data source status/freshness** và ghi rõ required access.

## 9. Tạo một Azure Monitor Workbook từ Portal

Ví dụ xây Workbook tên **Orders Platform — Operations & Troubleshooting**.

### 9.1. Tạo Workbook

1. Vào **Azure Portal → Monitor → Workbooks** hoặc vào resource Application Insights/Log Analytics → **Workbooks**.
2. Chọn **New** hoặc template được tổ chức phê duyệt.
3. Thêm một đoạn **Text** mô tả phạm vi, SLO, owner, runbook URL và caveat.
4. Thêm **Time range parameter** cho toàn Workbook hoặc từng bước.
5. Thêm **Resource/Subscription/Environment parameters**.
6. Thêm Logs query lấy request rate, error rate và p95 từ đúng Application Insights/Log Analytics scope.
7. Chọn visualization **time chart** hoặc **tiles/grid** phù hợp.
8. Thêm bảng top failing routes và drill-down cho trace/exception.
9. Thêm các metrics SQL/Service Bus/AKS theo resource scopes tương ứng.
10. Xem trước với nhiều params, kiểm tra no-data và quyền của người xem.
11. **Save/Save as** vào subscription/resource group/vị trí có governance phù hợp, chọn sharing model.
12. Cấp quyền cho operator, lưu version/source JSON template trong repository nếu quy trình hỗ trợ.

Tên menu có thể thay đổi theo Portal. Các thao tác là **logic thiết kế**, không phải bản hướng dẫn pixel-by-pixel cố định cho mọi tài khoản.

### 9.2. Đặt metadata Workbook

Một Workbook dễ vận hành cần:

```text
Title       : Orders Platform — Operations & Troubleshooting
Environment : production
Owner       : orders-sre
Revision    : 2026-11-20.1
Data source : workspace-app-prod and selected Azure resources
Scope       : subscriptions/resource group IDs governed by team
Time zone   : UTC for queries; user-local rendering documented
SLO         : 99.9% availability / 30 days (example)
Runbook     : internal approved documentation link
Last review : date when queries and permissions were revalidated
```

Đây là **mẫu mô tả**, không phải JSON object Workbooks API. **Workspace name và SLO chỉ là ví dụ**, cần thay bằng nguồn thực tế.

### 9.3. Một Workbook nên có ít panel hữu ích trước

Khởi đầu với **6–10 panels** liên kết nhau sẽ dễ kiểm tra hơn 40 panels không có owner. Tách **Overview**, **Requests & Latency**, **Dependencies**, **Queues & Data**, **Deployments & Changes** và **Troubleshooting** bằng section/text hoặc cách bố trí editor hỗ trợ.

### 9.4. Save vs template

Một Workbook đã lưu có thể hoạt động như dashboard riêng/chia sẻ. **Workbook templates** hữu ích để chuẩn hóa và tái sử dụng khi teams/tài nguyên khác nhau. Tránh sửa trực tiếp một shared Workbook production trong lúc incident nếu chưa có phiên bản/rollback; quản lý layout/queries như code, review trước khi deploy.

## 10. Parameters: chìa khóa của một Workbook tương tác

### 10.1. Ba parameters tối thiểu

| Parameter | Type gợi ý | Giá trị mẫu | Tác dụng |
|---|---|---|---|
| `TimeRange` | Time range | Last 60 minutes | Đồng bộ các queries |
| `Environment` | Dropdown | dev, staging, prod | Lọc logs/metric resource |
| `Resource` | Resource picker | App Insights resource hoặc workspace | Chọn nguồn đúng |

Có thể thêm **Subscription**, **Region**, **Service**, **AKS cluster**, **Namespace**, **ErrorCode**, **Application version**. Cần giới hạn số parameters và giá trị hợp lệ để không làm Workbook khó sử dụng.

### 10.2. Phân biệt resource scope và filter trong KQL

Resource picker có thể chọn dữ liệu ở scope mà query engine có quyền, trong khi `Environment` có thể là **dimension/column filter** của telemetry. Đừng chỉ lọc `AppRoleName contains "prod"` như một biện pháp bảo mật; tên telemetry có thể sai hoặc bị thay. **Quyền đọc workspace/resource** phải thực thi ở Azure IAM/data access layer.

### 10.3. Truyền parameter vào query

Workbook editor hỗ trợ cú pháp tham chiếu parameters theo loại nguồn và control; ví dụ ở mức ý tưởng:

```kusto
// Minh họa KQL dùng placeholder sau khi Workbook editor thay thế.
AppRequests
| where TimeGenerated between (datetime({TimeRange:start})
                               .. datetime({TimeRange:end}))
| where AppRoleName == '{ServiceName}'
| summarize RequestCount=count()
    by bin(TimeGenerated, 5m)
```

**Đây là mẫu biểu diễn parameter binding**, không phải query KQL độc lập có thể paste thẳng trong Log Analytics. Với Workbook, cú pháp substitution và **kiểu dữ liệu của parameter/time range** cần kiểm tra trong editor (nhiều queries có thể dùng **Time Range** configuration của query step thay vì tự chèn datetime literals). Không chèn raw user input tùy ý vào KQL vì **query injection, escaping và syntax errors**.

### 10.4. Dùng UI time range khi có thể

Một cách ít lỗi hơn là đặt **Time range** của query step tham chiếu parameter, để editor áp query scope; trong KQL chỉ cần:

```kusto
AppRequests
| summarize Requests=count()
    by bin(TimeGenerated, 5m)
| order by TimeGenerated asc
```

Tuy nhiên, khi query step tự quản time range, kiểm tra kết quả **không vô tình đọc toàn retention**; KQL tốt vẫn nên có giới hạn `TimeGenerated` phù hợp, nhất là khi chạy Logs trực tiếp hoặc lịch tính báo cáo.

### 10.5. Thời gian và timezone

KQL `TimeGenerated` thường được lưu bằng **UTC**; Portal có thể hiển thị theo timezone trình duyệt hoặc setting. Báo cáo có business date Asia/Ho_Chi_Minh nên **quy đổi rõ ràng tại ranh giới ngày**, không lấy nhãn trục chart local thành bộ lọc query UTC một cách mơ hồ.

### 10.6. Parameter default không được gây truy vấn quá lớn

Default `Last 1h`/`Last 24h` thường tốt hơn `All time`. Một Workbook mở ra tự chạy nhiều queries toàn bộ 2 năm logs có thể chậm và tăng chi phí. Bắt đầu từ **scope hẹp**, mở rộng theo nhu cầu điều tra.

## 11. KQL cho overview: request rate, error rate và p95

Các ví dụ dưới đây giả định **workspace-based Application Insights** có table **`AppRequests`** trong Log Analytics và các cột `TimeGenerated`, `Success`, `DurationMs`, `AppRoleName`, `ResultCode`. Đây là schema phổ biến, **không** mặc định tồn tại trên mọi Application Insights deployment. Trong Logs, kiểm tra table/column names bằng schema explorer trước khi copy.

### 11.1. Trend theo 5 phút

```kusto
let startTime = ago(24h);
let endTime = now();
AppRequests
| where TimeGenerated between (startTime .. endTime)
| where AppRoleName == "orders-api"
| summarize
    Requests = count(),
    Failed = countif(Success == false),
    P50_ms = percentile(DurationMs, 50),
    P95_ms = percentile(DurationMs, 95),
    P99_ms = percentile(DurationMs, 99)
    by bin(TimeGenerated, 5m)
| extend ErrorRatePct =
    iff(Requests > 0, 100.0 * todouble(Failed) / Requests, real(null))
| order by TimeGenerated asc
| render timechart
```

**Quan trọng:** `Success` là cờ telemetry instrumentation, có thể không trùng business definition của **good/eligible requests**. Nếu user SLO loại trừ client 4xx hoặc có timeouts không được ghi nhận, hãy xây SLI query riêng thay vì coi `countif(Success == false)` là chính sách SLO vĩnh viễn.

### 11.2. Một số chi tiết KQL

- `bin(TimeGenerated, 5m)` gom events thành 5-minute buckets; buckets không có dữ liệu có thể **không xuất hiện**.
- `percentile(DurationMs, 95)` tính trên những samples có trong table/window, có thể chịu **sampling/ingestion**.
- `render timechart` có thể được dùng trong Logs; trong Workbook, bạn cũng có thể chọn chart visualization trong editor thay vì khóa chart logic vào KQL.
- `real(null)` để biểu diễn **không có denominator**, không gán “0% lỗi” khi không có request.

### 11.3. SLI gần đúng cho server errors

```kusto
AppRequests
| where TimeGenerated >= ago(1h)
| where AppRoleName == "orders-api"
| extend StatusCode = toint(ResultCode)
| where isnotnull(StatusCode)
| summarize
    Eligible = countif(StatusCode < 400 or StatusCode >= 500),
    Bad = countif(StatusCode >= 500)
| extend AvailabilityPct =
    iff(Eligible > 0,
        100.0 * (Eligible - Bad) / todouble(Eligible),
        real(null))
```

**Đây là SLI ví dụ, không phải chuẩn áp dụng mọi dịch vụ**: các request 4xx bị loại trừ, 429 vẫn là 4xx và sẽ bị loại, 408/timeouts không có response có thể chưa được đếm; phải điều chỉnh theo service contract. Nếu hệ thống sử dụng sampling, số lượng events thô có thể không phản ánh tổng requests; xem xét metrics không sampled, `ItemCount`/trọng số và hiệu chuẩn dữ liệu theo instrumentation.

### 11.4. Top endpoints lỗi

```kusto
AppRequests
| where TimeGenerated >= ago(1h)
| where AppRoleName == "orders-api"
| summarize
    Requests = count(),
    Failures = countif(Success == false),
    P95_ms = percentile(DurationMs, 95)
    by Name
| extend ErrorRatePct =
    iff(Requests > 0, 100.0 * todouble(Failures) / Requests, real(null))
| where Requests >= 20
| top 15 by Failures desc
```

`Name` nên là **route template** (ví dụ `POST /orders/{id}`) do instrumentation chuẩn hóa, không phải URI với hàng triệu order IDs. Nếu không, cardinality tăng và top-N bị loãng.

## 12. KQL phân tích dependency, exceptions và traces

### 12.1. Dependency failures

```kusto
AppDependencies
| where TimeGenerated >= ago(2h)
| where AppRoleName == "orders-api"
| summarize
    Calls = count(),
    Failed = countif(Success == false),
    P95_ms = percentile(DurationMs, 95)
    by Target, Type
| extend FailurePct =
    iff(Calls > 0, 100.0 * todouble(Failed) / Calls, real(null))
| order by Failed desc
```

Từ đó có thể phát hiện SQL connection errors hoặc Key Vault latency. Nhưng dependency telemetry có thể thiếu nếu SDK/client chưa được instrument; **không xuất hiện không có nghĩa dependency khỏe**.

### 12.2. Exception trends

```kusto
AppExceptions
| where TimeGenerated >= ago(24h)
| where AppRoleName == "orders-api"
| summarize
    Occurrences = count(),
    FirstSeen = min(TimeGenerated),
    LastSeen = max(TimeGenerated)
    by ExceptionType, ProblemId
| top 20 by Occurrences desc
```

Tránh gửi **raw stack traces chứa secret/PII** vào Workbook chia sẻ rộng. Có thể hiển thị exception type, problem ID và link drill-down cho đội có quyền.

### 12.3. Truy vết theo OperationId

```kusto
let op = "trace-id-from-approved-incident";
union isfuzzy=true AppRequests, AppDependencies, AppTraces, AppExceptions
| where TimeGenerated >= ago(2h)
| where OperationId == op
| project TimeGenerated, Type, OperationId, AppRoleName,
          _ResourceId
| order by TimeGenerated asc
```

**Đây là query phác họa**: khi dùng `union` nhiều tables, một số schema có thể không đồng nhất; trong thực tế `Type` là tên table cho union trong nhiều contexts nhưng có thể cần `withsource=SourceTable` để xác định nguồn, và các cột `OperationId` có thể thiếu trong một số table versions. Nên sửa thành:

```kusto
let op = "trace-id-from-approved-incident";
union isfuzzy=true withsource=SourceTable
    AppRequests, AppDependencies, AppTraces, AppExceptions
| where TimeGenerated >= ago(2h)
| where OperationId == op
| project TimeGenerated, SourceTable, OperationId,
          AppRoleName, _ResourceId
| order by TimeGenerated asc
```

Nếu trace ID không xuất hiện, kiểm tra sampling, cross-component correlation, resource scopes và whether trace context was propagated. Một trace thiếu spans chưa chứng minh request không chạy qua dependency đó.

### 12.4. Chọn columns theo nhu cầu

`project` các trường cần thiết, tránh `project *` trên logs rộng. KQL query cho Workbook có thể trả tối đa số hàng/giới hạn được service/UI hỗ trợ; dùng **summarize → top N → drill-down** thay vì tải 100.000 exception rows lên trình duyệt.

## 13. KQL cho số liệu vận hành và dữ liệu đến trễ

### 13.1. Dữ liệu nghiệp vụ phải có nguồn được instrument

Nếu ứng dụng ghi một custom table `OrderWorkflow_CL` (ví dụ được ingest vào Log Analytics), có thể truy vấn:

```kusto
OrderWorkflow_CL
| where TimeGenerated >= ago(24h)
| summarize
    Accepted = countif(State_s == "ACCEPTED"),
    Completed = countif(State_s == "COMPLETED"),
    Failed = countif(State_s == "FAILED")
    by bin(TimeGenerated, 1h)
| order by TimeGenerated asc
```

**`OrderWorkflow_CL` và `State_s` là schema giả định do tổ chức tự tạo**, không phải table Azure Monitor mặc định. Nếu mỗi trạng thái tạo một event, `Accepted` và `Completed` trong cùng một giờ không nhất thiết thuộc cùng cohort, nên **không chia trực tiếp Completed/Accepted để gọi là conversion rate**. Để tính completion SLI theo cohort, cần business key, start time, cutoff/watermark và dedup.

### 13.2. Backlog và thông điệp lâu nhất

Azure Service Bus có những platform metrics như active/dead-letter message counts theo namespace/entity/metric definitions được hỗ trợ. **Oldest-message age** có thể cần custom telemetry hoặc query từ ứng dụng/work queue, không mặc định platform có sẵn metric tên như vậy. Phân biệt:

```text
Backlog count = số message đang chờ theo metric snapshot
Oldest age    = now - enqueue timestamp của work item cũ nhất
Drain rate    = messages processed/second theo nghiệp vụ
```

Backlog count giảm có thể do **expired/dead-letter** chứ không phải xử lý thành công; đặt cùng business completion/error signals.

### 13.3. Log ingestion freshness

Với nguồn custom logs có event đều đặn:

```kusto
OrderWorkflow_CL
| where TimeGenerated > ago(2h)
| summarize LastSeen=max(TimeGenerated), Records=count()
| extend
    LagMinutes = iff(isnotnull(LastSeen),
                     datetime_diff('minute', now(), LastSeen),
                     long(null))
```

Vì `datetime_diff('minute', now(), LastSeen)` lấy thời điểm hiện tại trừ event time, kết quả dương nếu LastSeen trong quá khứ. Nếu nguồn có **legitimate idle periods**, không đặt alert chỉ vì không có orders; hãy dùng một **heartbeat** độc lập hoặc pipeline freshness SLO.

### 13.4. Ingestion time khác event time

`TimeGenerated` trong Log Analytics có thể phản ánh timestamp event mà collector cung cấp, không nhất thiết là thời điểm dữ liệu đến workspace. KQL có hàm `ingestion_time()` trong những điều kiện/tables hỗ trợ để đánh giá ingest latency, nhưng dữ liệu ingestion metadata có đặc tính/giới hạn riêng. Cần **so `event timestamp`, `ingestion time` và `now()`** khi xác định “dashboard trễ”.

### 13.5. Không đồng nhất missing data và zero

| Tình huống | Diễn giải đúng |
|---|---|
| Có 1.000 requests, 0 failures | Có bằng chứng zero errors trong nguồn |
| Không có request rows | Có thể không có traffic hoặc instrumentation/ingestion lỗi |
| Không có metric samples | Data unavailable/metric unsupported/resource stopped |
| Bảng có row nhưng nhiều cột null | Schema/transform/dimension mismatch |
| Query result rỗng do permissions | Không được suy là hệ thống khỏe |

## 14. Azure Monitor Metrics: truy vấn và kết hợp với logs

### 14.1. Khám phá metric definitions bằng CLI

```bash
az login
az account set --subscription "<approved-subscription-id>"

RESOURCE_ID="<full-azure-resource-id>"

az monitor metrics list-definitions \
  --resource "$RESOURCE_ID" \
  --output table
```

Sau khi xác minh metric name/namespace/aggregations, xem dữ liệu:

```bash
METRIC_NAME="<name-listed-by-definition>"
az monitor metrics list \
  --resource "$RESOURCE_ID" \
  --metric "$METRIC_NAME" \
  --output json
```

Chọn `--interval`/`--aggregation`/`--dimension` theo CLI version và metric definition. **Không tự bịa metric names hoặc giả định mọi metric có granular 1 phút**.

### 14.2. Metrics không tự thành KQL tables

Azure Monitor Metrics API/metric database và Log Analytics tables là những nguồn dữ liệu **khác nhau**. Muốn query metrics bằng KQL phải có đường dữ liệu **xuất/ingest đến logs** hoặc dùng đúng metrics data source trong Workbook. Một resource có metric CPU trong Metrics Explorer không có nghĩa Log Analytics tự có table `CPU_CL`.

### 14.3. Chọn Metrics hay Logs trong Workbook?

- Dùng **Metrics** cho CPU%, memory, capacity, transactions, throttles, theo nguồn của resource.
- Dùng **Logs** cho route breakdown, exception, dependency, user-impact events, joins và triage.
- Dùng **Azure Resource Graph** để liệt kê context quản trị như resource IDs/tags/locations khi nguồn hỗ trợ.
- Dùng **dashboard summary** lấy số liệu đã tổng hợp, tránh hàng chục raw KQL queries.

Không chia một metric `Requests` theo user email/customer ID nếu service dimension không hỗ trợ hoặc tạo cardinality/PII quá lớn.

## 15. Workbook visualizations: tiles, charts, grids và drill-down

### 15.1. Overview tiles

Một row có các **tiles**:

```text
Availability: 99.94% / target 99.9%
Error rate:   0.06% (last 1h)
p95 latency:  740 ms / target 800 ms
Queue age:    91 sec / target 120 sec
Telemetry:    fresh (last 2 min)
```

**Các con số chỉ là ví dụ.** Hãy gắn đơn vị, time range và source, không trộn SLI 30-day với error rate last 1h mà không ghi nhãn.

### 15.2. Time charts và annotations

Đường p95 theo 5 phút cạnh deployment marker cho biết **sau release nào latency tăng**. Deployment events có thể đến từ CI/CD logs, Application Insights/custom events, Activity Log hoặc hệ thống release records. **Không mặc định portal dashboard đã biết lịch deploy của mọi app** nếu bạn chưa instrument/ingest.

### 15.3. Grid top errors

Một bảng cần cột:

| Route/Dependency | Request count | Failure count | Rate | p95 | Drill-down |
|---|---:|---:|---:|---:|---|
| POST /orders | 12.500 | 180 | 1,44% | 920 ms | Traces |
| GET /orders/{id} | 48.000 | 24 | 0,05% | 140 ms | Logs |
| ServiceBus send | 12.100 | 60 | 0,50% | 180 ms | Dependency events |

**Số liệu là minh họa**. Với `top N`, hiển thị số mẫu/denominator; một route có 1 lỗi/1 request có tỷ lệ 100% nhưng tác động tuyệt đối khác 1.000 lỗi/100.000 requests.

### 15.4. Drilling từ summary tới incident

Một trải nghiệm tốt:

```text
Error rate increased
       |
       v
Select service, region and last 30 minutes
       |
       v
Top failing route/dependency table
       |
       v
Click request/operation ID
       |
       v
Application Insights transaction details / traces / logs
       |
       v
Incident runbook + mitigation action
```

Các links được xây theo context cần **URL encoding, permission kiểm tra và tránh lộ sensitive query fragments**. Không đặt bearer token hoặc secret vào URL query string.

### 15.5. Giới hạn số lượng panels và queries

Mở Workbook đồng thời chạy 30 KQL queries mỗi lần chọn parameter có thể làm chậm cả trang và tăng query/ingestion-related cost. Gom panels theo tab/section/conditional display nếu editor hỗ trợ, dùng queries hiệu quả, cache/refresh policy có chủ đích và test trên dữ liệu thật.

## 16. Azure Resource Graph trong Workbook: inventory và ngữ cảnh

**Azure Resource Graph** truy vấn metadata Azure resources trên các subscriptions mà principal có quyền, giúp trả lời “cluster nào thuộc team nào?”, “bao nhiêu Key Vault đang dùng?” hoặc “resource này ở region nào?”. Nó không phải kho application requests, và cú pháp KQL của **Resource Graph** có tập chức năng/hạn chế khác Log Analytics.

### 16.1. Resource Graph query minh họa

```kusto
Resources
| where type =~ 'microsoft.insights/components'
| project
    id,
    name,
    resourceGroup,
    subscriptionId,
    location,
    tags
| order by name asc
```

Truy vấn này hướng đến resource type **Application Insights**. Nó chỉ hiển thị tài nguyên mà identity có quyền và resource graph đã index; **không chứng minh có telemetry trong Log Analytics**. Với query như “all production resources”, lọc tags như `tags.environment` chỉ hữu ích khi metadata tagging của tổ chức được quản trị chuẩn.

### 16.2. Kết hợp inventory với tín hiệu

Một Workbook có thể dùng resource picker/inventory query để hiển thị danh sách App Insights resources, sau đó lấy metrics/logs từ resource được chọn. Đừng giả định **join trực tiếp Resource Graph `Resources` với Log Analytics `AppRequests`** trong cùng một KQL query luôn hợp lệ; đây là **hai data sources/query engines**. Hãy dùng parameter plumbing/cross-resource features được Workbook hỗ trợ và kiểm tra quyền từng nguồn.

### 16.3. Owner/criticality dùng tags

Một asset record lý tưởng có:

```text
service=orders-api
environment=production
owner=orders-team
criticality=tier-1
costCenter=commerce
runbook=internal-link
```

Tags là **metadata quản trị**, không phải bằng chứng workload tự khỏe hoặc dữ liệu bảo mật đúng. Không đưa account number/PII vào tags; giới hạn ai có quyền sửa tags vì dashboard có thể dùng chúng để routing/ownership.

## 17. Chia sẻ Workbook và Azure RBAC

Một Workbook chỉ có giá trị khi đúng đội có thể mở và xem **đúng dữ liệu**, nhưng không có quyền cao hơn cần thiết.

### 17.1. Ba lớp permission

| Lớp | Cần quyền gì? | Sai lầm phổ biến |
|---|---|---|
| **Workbook definition/resource** | Read resource và scope được chia sẻ | Cho rằng có link URL là đủ |
| **Data source** | Đọc Application Insights/Log Analytics/metrics/resources theo data access model | Gán Viewer trên Workbook nhưng không cho đọc workspace |
| **Edit/deploy Workbook** | Quyền write phù hợp trên Workbook/resource group | Cho toàn on-call Contributor trên subscription chỉ để sửa layout |

Một user có quyền đọc Workbook nhưng thiếu **Log Analytics workspace permission** có thể thấy layout mà query panels báo access denied/no data. Một người có quyền query logs không tự có quyền lưu thay đổi lên shared Workbook.

### 17.2. Phạm vi dữ liệu và cross-tenant/cross-subscription

Nếu Workbook có parameter cho nhiều subscriptions, chỉ cung cấp những nguồn được phê duyệt. **Không coi dropdown filter là rào chắn an ninh**: user vẫn có thể sửa query hoặc vào nguồn trực tiếp nếu IAM cấp quyền rộng. Cần phân tách **Azure tenant, data source RBAC, resource context** và thông tin nhạy cảm trong tables.

### 17.3. Application Insights/Log Analytics data access

Application Insights có thể dùng **workspace-based resource**, còn Log Analytics cho phép access theo workspace/resource context theo cơ chế hỗ trợ. Kiểm tra mô hình cụ thể, cross-resource query, table-level data access/granular RBAC khi yêu cầu. Đừng dùng một blanket Log Analytics Contributor role cho mọi người chỉ để xem lỗi; người trực thường chỉ cần quyền **đọc** logs của các services được phân công.

### 17.4. Chia sẻ không đồng nghĩa tự động phát báo cáo

Một Workbook được chia sẻ cho nhóm có URL cố định, nhưng không **tự gửi email báo cáo tuần** hoặc lưu bản snapshot đúng thời điểm nếu chưa có workflow riêng. Việc phát hành báo cáo qua Teams/email/Power BI/Storage có governance và permission riêng.

### 17.5. Secret và PII trong dashboard

Không đưa vào:

- SQL connection strings, SAS tokens, bearer tokens, database credentials.
- Plaintext customer email/phone/order data không cần cho on-call.
- Full exception payload có request headers nhạy cảm.
- Resource connection metadata không nên chia sẻ ra ngoài nhóm.

Chọn **route template, anonymized identifiers, sanitized error code và aggregate counts** làm mặc định. Drill-down chi tiết yêu cầu quyền kiểm soát tốt hơn.

## 18. Lưu Workbook như một tài nguyên, template và version control

Workbook được lưu có phần **định nghĩa truy vấn/layout** mà đội muốn xem như một artifact cấu hình. Với Azure resource model, có các resource types như **`Microsoft.Insights/workbooks`** và **`Microsoft.Insights/workbooktemplates`** trong những API/versions hỗ trợ; khả năng tạo/deploy cụ thể phụ thuộc công cụ và API.

### 18.1. Những gì nên đưa vào repository

```text
workbook/
  # Mô tả cấu trúc repository tham khảo, không phải file được tạo ở task này.
  orders-operations.workbook.json
  orders-operations.parameters.json
  README-for-operators.md
  CHANGELOG.md
  tests/
    query-contracts.md
```

Khi lưu file template/export từ Portal, phải **redact** resource IDs nhạy cảm, tenant IDs, query literals có token/PII và thay environment-specific scopes bằng parameters/IaC substitutions. Không commit secret value vào JSON.

### 18.2. Pseudo IaC, không phải Bicep thực thi

```yaml
# Logical deployment contract; không phải schema ARM/Bicep/Terraform.
workbook:
  name: orders-platform-operations
  owner: orders-sre
  scope:
    subscription: non-production-or-production-approved
    resourceGroup: rg-observability
  source:
    applicationInsights: appinsights-orders-prod
    logAnalytics: law-orders-prod
  parameters:
    timeRange: last-1h
    environment: production
    service: orders-api
  sections:
    - service-health
    - latency-and-requests
    - dependencies
    - queues-and-database
    - deployments-and-incidents
  access:
    readers: operations-oncall
    editors: observability-maintainers
  review:
    queryTests: required
    approvedBy: service-owner
```

Khi triển khai thật, dùng resource provider API và serialized Workbook JSON **đúng phiên bản**, có GUID/name, `serializedData`/template fields và required metadata theo hướng dẫn provider. Không tự coi pseudo YAML là tài liệu deployable.

### 18.3. Version một Workbook

Quy trình tối thiểu:

1. Export định nghĩa Workbook đang hoạt động.
2. Chỉnh KQL/layout trong branch riêng.
3. Test query trên **workspace staging hoặc test resource** với fixture.
4. Kiểm tra permission, time range, no-data và chi phí.
5. Review bởi service owner/on-call.
6. Deploy thành bản mới, xác minh result.
7. Giữ cách rollback đến định nghĩa trước.

Đổi một KQL filter có thể khiến dashboard hiển thị “100% healthy” dù thực tế đã bỏ một service. Hãy review **ngữ nghĩa dữ liệu**, không chỉ JSON diff.

### 18.4. Workbook template chuẩn hóa nhiều môi trường

Một template có thể được dùng cho dev/staging/prod với parameters khác nhau. **Template chỉ có ích khi telemetry schemas/metric definitions đã chuẩn**, nếu các teams dùng table names khác nhau thì nhân bản template sẽ tạo các panel rỗng. Nên có **telemetry contract** dùng chung: field names, units, service identity, trace IDs và retention.

## 19. KQL tối ưu cho Workbook và kiểm soát chi phí truy vấn

### 19.1. Năm nguyên tắc

1. Lọc `TimeGenerated` **sớm** để giảm scan.
2. Lọc theo service/resource/tenant được phép trước `summarize` và `join` lớn.
3. Chỉ `project` các cột cần hiển thị, bỏ PII.
4. `summarize` rồi `top N` trước khi trả dữ liệu lớn.
5. Test query duration, bytes scanned/cost và kết quả trên nhiều time ranges.

### 19.2. Tránh truy vấn toàn retention khi mở trang

Không viết:

```kusto
AppRequests
| summarize count() by Name
```

trong một Workbook luôn tự chạy và không có time scope; nó có thể đọc nhiều dữ liệu hơn cần. Nên viết:

```kusto
AppRequests
| where TimeGenerated >= ago(1h)
| where AppRoleName == "orders-api"
| summarize Requests=count() by Name
| top 20 by Requests desc
```

Với Workbook thực, đồng bộ window này với time range parameter thay vì giữ cứng 1 giờ nếu người dùng cần chọn ngày/tuần.

### 19.3. Join và high cardinality

Một KQL `join` theo raw customer ID/operation ID trên hàng chục triệu records có thể làm query nặng, nhất là cross-workspace. Ưu tiên pre-aggregate hoặc filter service + time + operation ID trước, và kiểm tra join cardinality. Tránh dùng **raw user identifiers** như visualization series; nguy cơ PII và nổ số series.

### 19.4. Query logging và workbooks không miễn phí

Workbook được lưu thường không tốn storage tương đương log lake, nhưng mỗi lần chạy query có thể dùng khả năng truy vấn và chịu **chi phí gián tiếp hoặc trực tiếp tùy Log Analytics plan, query features, data retention, ingestion và pricing**. Auto-refresh với nhiều heavy queries làm tăng tải. Dùng **query optimization/refresh interval phù hợp**, không ép refresh 5 giây cho báo cáo xu hướng 30 ngày.

### 19.5. Aggregation không phá semantics

Nếu muốn error rate toàn ngày, không nên lấy **trung bình số học của 24 error rates giờ** khi traffic mỗi giờ khác nhau. Hãy dùng:

```text
Daily error rate =
  sum(failed eligible requests across hours)
  / sum(all eligible requests across hours)
```

Tương tự, không lấy average của các p95 từ mỗi node. Với SLO tổng, tính lại từ đủ dữ liệu/weighted distributions được mô hình hỗ trợ.

## 20. Tách dashboard, alert và báo cáo thành những vòng đời riêng

### 20.1. Một tín hiệu có thể dùng ba mục đích

Ví dụ `orders_completed`:

- **Dashboard:** completion count và trend 5 phút.
- **Alert:** completion rate giảm trong 15 phút ở volume đủ lớn, theo rule đã kiểm thử.
- **Báo cáo tuần:** completed/accepted theo cohort, đối chiếu source ledger và business SLA.

Cùng tên metric không có nghĩa cùng **cửa sổ thời gian/aggregation/denominator**.

### 20.2. Alert rule cần thiết kế riêng

| Thành phần alert | Ví dụ |
|---|---|
| Signal | Error rate 5xx cho orders-api |
| Window | Rolling 10 phút |
| Minimum volume | Ít nhất 100 eligible requests trong window |
| Threshold | Error rate > 2% |
| Evaluation | Mỗi 5 phút theo khả năng alert rule |
| Severity | Sev2 nếu user impact; thay theo policy |
| Action | Action group → incident routing/on-call |
| Suppression | Maintenance/scheduled mute có audit |
| Owner | Orders SRE |
| Runbook | Link vào Workbook tab “Errors” |

Đây là cấu hình **minh họa**, cần được hiệu chuẩn theo SLO/volume. Việc “chọn ngưỡng 2%” không phải mặc định của Azure Monitor.

### 20.3. Missing-data alert

Ví dụ không có orders D2C logs trong 15 phút có thể do traffic thấp hoặc ingestion bị ngừng. Cần heartbeat từ worker/ingestion pipeline và alert về **data availability/freshness**, tránh để panel rỗng bị hiển thị xanh. Metric alerts và log alerts có semantics khác về **no data**, “fired/resolved” và query evaluation; phải kiểm thử khi nguồn đứt.

### 20.4. Action group và người nhận

Azure Monitor action groups có thể thông báo hoặc gọi các endpoints/workflows được hỗ trợ, nhưng **không mặc định thay hệ thống incident management**. Cần:

- Đúng người/on-call rotation và severity.
- Chống paging storm với dedup/suppression policy.
- Alert payload có service, environment, region, symptom, chart/runbook link.
- Escalation khi owner không phản hồi.
- Post-incident feedback để tối ưu threshold.

### 20.5. Dashboard không thay Service Health

Khi có outage phạm vi region/platform, kết hợp application SLIs, **Azure Resource Health/Service Health** và các thông báo chính thức. Một resource CPU chart bình thường không chứng minh mọi dependent Azure service khỏe.

## 21. Xây báo cáo vận hành hằng ngày

### 21.1. Mục tiêu

Báo cáo hằng ngày dành cho ca trực bàn giao, trả lời:

- Nền tảng có vi phạm SLO hoặc incident nào trong 24 giờ?
- Người dùng bị ảnh hưởng bao nhiêu, khoảng thời gian và services nào?
- Những cảnh báo/ticket nào chưa xử lý?
- Có thay đổi deployment/capacity/traffic đáng chú ý không?
- Có resource cost anomaly, quota/certificate/secret expiry không?
- Cần ca tiếp theo làm gì, ai chịu trách nhiệm, deadline nào?

### 21.2. Template ngắn

```markdown
# Daily Operations Handover — Orders Platform

**Period:** 2026-11-19 00:00–23:59 Asia/Ho_Chi_Minh
**Prepared at:** 2026-11-20 08:30 +07:00
**Telemetry cutoff:** 2026-11-20 08:15 +07:00
**Owner:** Orders on-call
**Sources:** App Insights, Log Analytics, Azure Monitor, incidents

## Health and SLO
- Availability (24h): 99.94% (target 99.9%, example)
- API p95: 720 ms (target 800 ms, example)
- Failed orders: 87 (source reconciled: pending)
- Critical active incidents: 1

## Significant events
| Time | Event | Customer impact | Owner |
|---|---|---|---|
| 14:12 | SQL connection errors after deployment | Checkout delay | API lead |

## Outstanding risks
- Queue backlog age peaked at 4m; watch worker scaling.
- Nightly order reconciliation not yet finalized.

## Actions for next shift
- [ ] Validate SQL connection pool rollback — API lead — 10:00
- [ ] Reconcile 87 failed orders — Data ops — 12:00
```

**Toàn bộ số liệu/thời gian trong mẫu là giả định.** Không gửi báo cáo này như dữ liệu vận hành thật. Ghi rõ nguồn, query/window, dữ liệu còn trễ và người xác nhận.

### 21.3. “Snapshot” hằng ngày khác Workbook live

Báo cáo bàn giao phải **đóng cửa sổ thời gian**: 00:00–23:59 theo timezone đã thống nhất, thêm cutoff để tránh late logs. Một Workbook live với filter “last 24 hours” sẽ thay dữ liệu mỗi lần mở; không nên dùng URL live như một bản lưu bất biến nếu mục tiêu audit đòi snapshot.

### 21.4. Dữ liệu chưa hoàn chỉnh

Nếu telemetry ingest chậm hoặc worker backfill, báo cáo có thể ghi:

```text
Reconciliation status: PRELIMINARY
Latest source watermark: 2026-11-19 23:40 +07:00
Missing data window: 20 minutes
Expected finalization: after source backfill
```

Không đưa 0 failed orders cho window chưa ingest xong. Khi số liệu được restate, lưu **phiên bản báo cáo và lý do thay đổi**.

## 22. Báo cáo vận hành hằng tuần và hằng tháng

### 22.1. Các nhóm thông tin

| Nhóm | Chỉ số | Câu hỏi quyết định |
|---|---|---|
| Reliability | SLO, error budget consumed, incident minutes | Cần giảm feature rollout để ổn định không? |
| Performance | p95/p99 latency, top slow dependencies | Có cần tối ưu SQL/scale không? |
| Capacity | CPU/memory, queue backlog, DB utilization | Dự báo scale và quota |
| Changes | Releases, config drift, deployment failures | Release process có an toàn? |
| Security | High-severity alerts, cert expiry, access anomalies | Có rủi ro chưa khắc phục? |
| Cost | Budget variance, cost/service and cost/transaction | Tối ưu phần nào trước? |
| Delivery/operations | Open action items, overdue incidents, toil | Ai cần làm gì tuần tới? |

### 22.2. Chỉ chọn các KPI có thể hành động

Một bảng 100 metrics làm người đọc mất hướng. Báo cáo tuần nên có **5–10 KPI cốt lõi**, diễn biến so kỳ trước, giải thích những thay đổi lớn, **owner/ETA** và link evidence. Không chỉ kể “CPU giảm 10%” khi không có mục tiêu hoặc tác động gì.

### 22.3. Format executive summary mẫu

```text
Overall service status: At risk
SLO 30-day rolling: 99.86% (target 99.9%)
Customer impact: checkout API errors in Region A, 42 minutes
Root cause: connection pool exhaustion after release
Mitigation: rollback and temporary pool limit
Corrective action: load-test and connection metrics
Owner / deadline: Payments & Platform teams / next sprint
Cost trend: +8% vs baseline (driven by SQL scaling)
Data quality: finalized through specified UTC cutoff
```

Các giá trị giả định phục vụ **thực hành viết báo cáo**. Khi báo cáo thật, phải gắn incident IDs và query links có quyền truy cập phù hợp, đồng thời nêu rõ **mức độ tin cậy và dữ liệu chưa chốt**.

### 22.4. Không ép tất cả audience vào một trang

On-call cần latency, errors, traces. CTO cần SLO trends, risk/cost và cam kết cải thiện. Security cần access anomalies. FinOps cần capacity/cost attribution. Dùng **một KPI dictionary** nhưng tạo các views khác nhau; như vậy tránh 5 nhóm báo cáo 5 cách tính availability khác nhau.

## 23. Gắn báo cáo với sự cố và post-incident review

### 23.1. Báo cáo không được chỉ nói “lỗi xảy ra”

Một incident review có:

1. **Impact:** ai bị ảnh hưởng, số giao dịch và thời gian.
2. **Detection:** tín hiệu nào phát hiện, alert nhanh/chậm bao lâu.
3. **Timeline:** UTC hoặc timezone cụ thể, deployment/change liên quan.
4. **Root cause:** nguyên nhân có bằng chứng, phân biệt symptom.
5. **Mitigation/Recovery:** hành động và thời điểm hệ thống phục hồi.
6. **Contributing factors:** thiếu alert, dashboard, runbook, rollback, tests.
7. **Actions:** owner, priority, deadline, link issue.
8. **Validation:** sau fix đã test/monitor gì.

### 23.2. Kết nối Workbook với incident timeline

Lưu **time window UTC, query text/links, resource IDs và phiên bản Workbook** sử dụng lúc điều tra. Nếu tuần sau Workbook query bị sửa, kết quả live có thể không trùng thời điểm incident do dữ liệu đã retention/backfill; với yêu cầu audit cần lưu **snapshot aggregates và evidence artifacts được cấp quyền**, không chỉ URL.

### 23.3. MTTD, MTTA, MTTR

| Metric | Ý nghĩa |
|---|---|
| **MTTD** | Mean Time To Detect – từ khi sự cố bắt đầu đến lúc phát hiện |
| **MTTA** | Mean Time To Acknowledge – từ alert đến lúc owner xác nhận |
| **MTTR** | Mean Time To Restore/Recover – theo định nghĩa tổ chức |

Các acronym có nhiều biến thể (MTTR có thể mang nghĩa “Repair” hoặc “Resolve”); **định nghĩa rõ** trước khi so sánh theo tháng. Không lấy thời gian đóng ticket làm thời điểm dịch vụ phục hồi nếu khách hàng đã hết ảnh hưởng từ trước.

### 23.4. Continuous improvement

Nếu một incident không được alert phát hiện, bổ sung **SLI/alert** trước khi thêm 10 CPU charts. Nếu alert có nhưng operator không hiểu, thêm **drill-down, runbook và owner**. Nếu dashboard hiển thị sai, sửa **telemetry contract** thay vì chỉ đổi màu bảng.

## 24. Quy trình xuất và phát hành báo cáo vận hành

**Workbook live** và **báo cáo đã chốt kỳ** cần được quản lý khác nhau. Một pipeline báo cáo có thể dùng Log Analytics query/approved exports, hệ thống tổng hợp dữ liệu, artifact storage và công cụ chia sẻ của tổ chức. Azure Monitor Workbook **không mặc định là scheduler gửi PDF/email** mỗi tuần, và một subscription tới URL Workbook không tự tạo snapshot.

### 24.1. Luồng tạo báo cáo

```text
Scheduled run after agreed data cutoff
          |
          v
Validate data source freshness and coverage
          |
          v
Execute versioned KPI queries (Azure Monitor/other source)
          |
          v
Reconcile business figures and SLO denominators
          |
          v
Assemble Markdown/HTML/PDF/BI report (approved workflow)
          |
          v
Review exceptions, incidents, owners and action items
          |
          v
Publish to access-controlled destination
          |
          v
Record report version, generatedAt and query/model revision
```

### 24.2. Những metadata phải đi cùng bản báo cáo

```yaml
# Metadata mẫu cho report; không phải API schema Azure.
reportId: orders-platform-weekly-2026w47
periodStartUtc: "2026-11-16T00:00:00Z"
periodEndUtc: "2026-11-23T00:00:00Z"
generatedAtUtc: "2026-11-23T02:15:00Z"
dataCutoffUtc: "2026-11-23T02:00:00Z"
status: preliminary
metricsDefinitionRevision: "slo-orders-4"
queryRevision: "kql-ops-16"
workbookRevision: "workbook-2026-11-20.1"
sources:
  - azure-monitor-apprequests
  - operations-incident-system
owner: orders-sre
approver: operations-lead
```

Đây là **mẫu ví dụ**, không phải báo cáo đã tạo cho người dùng hay số liệu thực tế. Các mốc trong tương lai chỉ minh họa cách xác định kỳ; trong một hệ thống thật, lịch và kỳ báo cáo phải dựa trên timezone/billing calendar của tổ chức.

### 24.3. Báo cáo muộn vẫn phải có trạng thái

Nếu log ingestion hoặc billing export chậm, publish `PRELIMINARY` kèm caveat và thời điểm finalization hoặc **không publish** nếu quality gate critical. Đừng dùng im lặng hoặc 0 thay cho dữ liệu thiếu. Nếu phải sửa lại dữ liệu, tạo **report revision** với diff/sự giải thích, không âm thầm ghi đè artifact mà không để dấu.

### 24.4. Phân quyền phát hành

Report về incident/security có thể chứa tên người dùng/tài nguyên, thông tin mạng hoặc sự cố. Chia sẻ qua kênh có **RBAC/retention** phù hợp; báo cáo executive thường nên dùng aggregations/anonymization. Nếu lưu report PDF/CSV trong Blob Storage, dùng identity, encryption, private access và lifecycle policies; không phát public SAS URL không giới hạn.

### 24.5. Phê duyệt và chất lượng

Không cho một job tự động kết luận “Root cause = SQL” chỉ vì phụ thuộc SQL có nhiều errors. Machine-produced metrics có thể là **facts**, root cause và quyết định cần **human review** khi thiếu bằng chứng. Bản tuần cần owner xác nhận những thay đổi quan trọng trước khi gửi lãnh đạo.

## 25. Dashboard/Báo cáo FinOps: chi phí và năng lực phục vụ

Mục tiêu không phải chỉ giám sát bill tổng, mà hiểu **mỗi đơn hàng hoặc giao dịch thành công cần bao nhiêu tài nguyên** và khi nào tăng phí là hợp lý.

### 25.1. Các chỉ số

| Nhóm | Chỉ số | Cách đọc |
|---|---|---|
| Chi phí | Actual cost theo subscription/resource group/tag | Ngân sách đã dùng |
| Đơn vị | Cost/1.000 completed orders | Unit economics vận hành |
| Khả năng | AKS/App Service CPU & memory, DB capacity | Tài nguyên có đáp ứng traffic? |
| Thông điệp | Service Bus operations/backlog/dead letters | Queue efficiency và lỗi |
| Monitoring | Log ingestion/retention, query volume, sampling | Observability cost |
| Sự kiện | Deployments/scale events | Giải thích cost spikes |

### 25.2. Dữ liệu chi phí không cùng nhịp với metrics

Azure Cost Management/Exports có **data freshness và billing adjustments** khác Azure Monitor Metrics. Cost data có thể chưa chốt, có reservations/savings plans/tags/attribution issues. **Không vẽ cùng trục thời gian “current minute” rồi giả vờ cost là realtime**. Trong báo cáo, ghi khoảng tính phí và ngày dữ liệu cập nhật; so theo vùng/cost center có cùng định nghĩa.

### 25.3. Không tự suy metrics từ Cost Management

Workbook có thể dùng một số data sources/links hỗ trợ nhưng **không mặc định có query connector đọc trực tiếp mọi bảng Cost Management**. Muốn kết hợp cost và SLI, sử dụng **Cost Management exports/API** hoặc data pipeline được phê duyệt, ingest vào nơi phù hợp (và tính retention/billing), hoặc link sang Cost Analysis. Không viết `AzureCosts_CL` rồi cho rằng table đó được tạo sẵn.

### 25.4. Cost per completed order

```text
Cost per completed order =
  total attributable service cost in period
  / number of completed orders in same period
```

Phải thống nhất **cost allocation, timezone/kỳ chốt, workload boundary, credits/discounts và denominator**. Nếu completed orders giảm mạnh do outage, cost/order tăng dù hạ tầng không scale; đó là tín hiệu vận hành cần giải thích, không chỉ là “chi phí cloud tăng”.

### 25.5. Alert bất thường chi phí

Budget alerts, cost anomaly alerts và các cơ chế theo Cost Management khả dụng hỗ trợ FinOps; chúng **không thay** SLO/error alerts và có latency dữ liệu khác. Người trực không nên bị page mỗi phút vì biến động hóa đơn dự kiến của một batch job đã được phê duyệt. Gán owner và threshold theo sản phẩm.

## 26. Bảo mật và data governance của Workbook/report

### 26.1. Dữ liệu nhạy cảm trong queries

Application logs có thể chứa email, IP, order IDs, exception bodies, query parameters. Workbooks có thể ghép các tables và hiển thị qua links. Vì thế:

- Dùng **structured logging có redact** tại nguồn.
- Chỉ truy vấn những trường cần hiển thị, `project-away` PII nếu không cần.
- Tách dashboard aggregate công khai trong nội bộ và incident drill-down có scope hẹp.
- Hạn chế quyền đọc workspace/table theo Azure IAM/data access features được hỗ trợ.
- Quản lý snapshot/exports theo classification/retention.
- Audit người sửa Workbook và role assignments quan trọng.

### 26.2. Parameter injection

Nếu Workbook cho nhập string free text rồi chèn trực tiếp vào query, có thể tạo **KQL syntax lỗi hoặc mở rộng scope ngoài dự kiến**. Dùng parameter types/quoting được hỗ trợ, allowlist service/environment/region values và kiểm tra queries với giá trị chứa quote/slash. **Không xem parameter filter là cơ chế authorization**; IAM phải quyết định truy cập dữ liệu.

### 26.3. Cardinality và PII trong metrics

Một metric gắn dimension `customerEmail`/`orderId` có thể tạo hàng triệu series, tăng cost/overhead và rò rỉ PII qua dashboards. Dùng **service, region, route template, status class, deployment ring** như dimensions thường hữu ích hơn; trace/order ID để trong logs bảo vệ theo role.

### 26.4. Audit việc thay đổi Workbook

Workbook production bị chỉnh query lọc bỏ lỗi `5xx` có thể tạo health report sai. Hãy:

1. Version control serialized definitions.
2. Review thay đổi query logic/KPI dictionary.
3. Phân quyền editor riêng operator viewer.
4. Thiết lập Azure Activity Log/resource change audit khi thích hợp.
5. Dùng deployment approval và rollback.
6. Test snapshot expected query results sau change.

### 26.5. Không nhúng access tokens trong Workbook URL

Links drill-down không được chứa secret query strings, SAS token rộng, access token hoặc private internal resource metadata vượt policy. Link nên trỏ tới resource/query theo **Azure identity access** của người mở. Nếu user thiếu quyền, cần cấp đúng scope theo governance, không gửi screenshot chứa dữ liệu nhạy cảm thay thế.

## 27. Thiết kế data quality cho observability

**Telemetry cũng là dữ liệu**, có thể thiếu, trùng, sai timestamp hoặc đổi schema. Dashboard nên có chất lượng dữ liệu riêng, đặc biệt khi dùng để đánh giá SLO/billing.

### 27.1. Năm kiểm tra cơ bản

| Chất lượng | Câu hỏi | Cách kiểm |
|---|---|---|
| **Freshness** | Dữ liệu mới nhất cách hiện tại bao lâu? | LastSeen và ingest lag |
| **Completeness** | Có mất cluster/route/region nào không? | Resource inventory vs reporting sources |
| **Schema** | Các fields DurationMs, ResultCode, AppRoleName có còn không? | Schema validation/query contract |
| **Consistency** | Request totals có khớp platform ingress? | Đối chiếu trong tolerance do sampling |
| **Correctness** | KPI có cùng good/bad definition không? | Unit tests cho aggregation/KQL |

### 27.2. Sampling và mẫu thống kê

Application Insights/OTel có thể sampling traces/requests; khi đó `count()` raw rows không nhất thiết là số requests thật. Có những schema hỗ trợ trường trọng số `ItemCount` hoặc metrics pre-aggregated; việc dùng chúng phải theo **semantics của loại telemetry và instrumentation**. Không nhân đại mọi row với một hệ số cố định nếu sampling rates thay đổi.

### 27.3. Timestamp và dữ liệu đến trễ

Một lỗi xảy ra lúc 23:58 local, log ingest lúc 00:08 hôm sau. Báo cáo ngày cũ cần **event-time cutoff và allowed lateness**, hoặc ghi status preliminary/restate. Không gán lỗi sang ngày hôm sau chỉ vì nhận log hôm sau khi KPI dựa trên event time.

### 27.4. Query đúng nhưng scope sai vẫn là dữ liệu sai

Một Workbook ở workspace `law-dev` có queries hoàn toàn hợp lệ nhưng SLO production sẽ không có nghĩa. Trước khi chấp nhận report, kiểm tra **subscription/resource IDs, environment filter, region, telemetry schema version và query revision**.

### 27.5. No data là một trạng thái được quản lý

Với SLO:

```text
RequestCount == 0:
  show NO_DATA / NOT_APPLICABLE as agreed
  do not show availability 100%

LogIngestionLate == true:
  show DATA_DELAYED with last watermark
  do not finalize incident statistics
```

Đây là quy tắc business/reporting mẫu; mỗi service có thể có **idle periods hợp lệ** hoặc phụ thuộc traffic baselines khác nhau.

## 28. Validation: kiểm thử Workbook trước khi chia sẻ

### 28.1. Các trường hợp phải thử

| Test | Expected |
|---|---|
| Time range 1h/24h/7d | Query hoạt động, time bins/labels đúng |
| Chọn environment dev/prod | Không lẫn dữ liệu |
| Chọn resource không có quyền | Hiển thị access denied rõ, không tô xanh |
| Nguồn logs không có events | NO_DATA chứ không Success=100% |
| Dữ liệu 5xx cao | Error-rate/SLI đúng với formula |
| Query bị sampling | Caveat/weights phù hợp |
| Một region mất telemetry | Freshness/completeness báo bất thường |
| Người xem chỉ có read role | Xem đúng data; không edit Workbook |
| Người edit sửa KQL | Có version review/rollback |
| Workbook đặt time range lớn | Query không timeout vô lý/cost bất thường |
| Mobile/large wallboard layout | Labels/units không bị cắt, accessible |

### 28.2. Golden dataset

Tạo một bộ fixture nhỏ:

```text
100 eligible requests
96 good
4 bad (HTTP 5xx)
latencies: known sorted values
2 simulated dependency errors
1 simulated missing telemetry window
```

Tính expected availability = **96%** bằng tay rồi kiểm tra KQL/dashboard/report. Không dùng dữ liệu thật có PII để test query nghĩa vụ báo cáo. Với p95, định nghĩa **percentile algorithm/interpolation** của query engine; không tự khẳng định một giá trị khi sample nhỏ mà chưa kiểm tra phương pháp.

### 28.3. So sánh dashboard với report

Tạo cùng một fixed time range/filters ở Workbook và pipeline report. **Good/bad counts, request totals và date boundaries** cần trùng trong tolerance; nếu lệch, tìm nguyên nhân: sampling, ingestion lateness, timezone conversion, query definitions hoặc scope.

### 28.4. Kiểm thử sau SDK/agent upgrade

Nâng Java Azure Monitor OpenTelemetry agent/SDK có thể đổi span attributes, operation names, service IDs hoặc sampling. KQL hard-code `AppRoleName == "orders-api"` có thể trở về rỗng nếu new deployment dùng tên khác. Sau nâng SDK/agent phải **smoke test actual telemetry table/schema** và dashboard critical panels.

## 29. Thiết kế báo cáo không gây alert fatigue

### 29.1. Biến alert thành quy tắc hành động

Một signal được đưa vào alert khi **có người và hành động khắc phục** tương ứng; nếu chỉ để theo dõi trend, để trong dashboard/report. Chọn alert based on customer impact, SLO/error budget hoặc resource saturation dự báo outage, tránh page vì mọi thay đổi vô hại.

### 29.2. SLO burn rate

Với request-based SLO 99,9%, error budget fraction là 0,001. Có thể định nghĩa một **burn rate** khái niệm:

```text
burn rate = observed bad fraction / allowed bad fraction

Example:
  observed bad fraction = 0.004 (0.4%)
  allowed bad fraction  = 0.001 (0.1%)
  burn rate = 4x
```

Một burn-rate alert nên dùng **nhiều cửa sổ thời gian** để giảm nhiễu, theo volume và SLA. Ngưỡng/window phải được tuning theo SLO; không áp một cặp threshold mặc định cho mọi service.

### 29.3. Có người xử lý và có đường thoát

Mỗi alert nên có:

- Service/owner và escalation routing.
- Tín hiệu/đơn vị/cửa sổ, link Workbook đúng time context.
- Hướng triage 3–5 bước trong runbook.
- Cách xác định user impact, rollback hoặc mitigation.
- Cách biết đã **phục hồi**, không chỉ “alert resolved”.
- Cách rà soát false positives sau incident.

### 29.4. Báo cáo false positives

Theo dõi **page volume, actionable rate, false positives, MTTD/MTTA** trong báo cáo tháng; nếu một alert liên tục đánh thức người nhưng không hành động được, sửa signal/threshold hoặc chuyển thành non-paging notification.

## 30. Phối hợp dashboard với hệ thống thay đổi và vận hành

### 30.1. Deployment và incidents trong cùng timeline

Khi p95 tăng đột ngột lúc 10:15, cần biết có release, scale event, config change, RBAC drift hoặc database migration nào quanh 10:00. Kết hợp:

- Application Insights/AppTraces hoặc custom deployment events.
- Azure Activity Log cho resource/control plane changes.
- CI/CD deployment history với release ID/commit SHA được ghi an toàn.
- Incident tracker và maintenance window.

### 30.2. Không suy causation chỉ từ tương quan

“Latency tăng sau deploy” là một **hypothesis**, không phải root cause. Workbook nên cho phép drill-down: route/region, SQL dependency, exception type, saturation và tracing. Báo cáo root cause phải dựa bằng chứng đủ mạnh.

### 30.3. Release annotation yêu cầu schema

```json
{
  "eventType": "deployment",
  "service": "orders-api",
  "environment": "production",
  "region": "southeastasia",
  "releaseId": "release-20261120-3",
  "commit": "example-sha",
  "startedAtUtc": "2026-11-20T10:00:00Z",
  "completedAtUtc": "2026-11-20T10:05:00Z",
  "result": "SUCCEEDED"
}
```

Đây là **application/CI event contract minh họa**; Azure Monitor không tự tạo đúng JSON đó. Một release có status SUCCEEDED của pipeline không tự chứng minh application healthy; cần post-deploy SLI/health gates.

### 30.4. Change calendar và maintenance

Một dashboard có thể ghi banner planned maintenance/deployment window; alert suppression/muting phải có owner, thời hạn và audit. Không tắt toàn bộ alerts vô hạn chỉ vì có một lần database migration.

## 31. Case study: Workbook cho nền tảng Java + Azure

### 31.1. Bối cảnh

Hệ thống **Orders Platform** gồm:

- **Azure Front Door/Application Gateway** trước API, tùy kiến trúc.
- **Java 21/Spring Boot** trên AKS hoặc Azure App Service.
- **Azure SQL Database** lưu đơn hàng.
- **Azure Service Bus** cho jobs hậu xử lý và retry.
- **Azure Key Vault** cấp cấu hình bí mật bằng managed/workload identity.
- **Application Insights + Log Analytics** theo dõi requests, dependencies, exceptions và structured logs.
- **Azure Monitor Metrics/Alerts** cho infrastructure, DB, queues, saturation.
- **Azure Cost Management** cho chi phí vận hành theo giai đoạn.

Business yêu cầu:

1. API đủ điều kiện có **99,9% good requests / rolling 30 days**.
2. 95% requests phải có latency không quá **800 ms** (chỉ là mục tiêu giả định).
3. 99% orders xử lý hoàn tất trong **120 giây** từ lúc chấp nhận.
4. P1/P2 incidents được phát hiện trong khoảng thời gian trực ca phù hợp policy.
5. Báo cáo tuần có số liệu có thể truy nguyên, không lẫn staging và production.

### 31.2. Sơ đồ workbook vận hành

```text
                            Azure Monitor Workbook
                  Parameters: time / env / region / role
                                   |
        +--------------------------+--------------------------+
        |                          |                          |
        v                          v                          v
   Java API panel             Dependency panel           Backlog panel
   AppRequests                AppDependencies            Service Bus metrics
   requests/errors/p95        SQL/Key Vault/HTTP         and worker telemetry
        |                          |                          |
        +--------------------------+--------------------------+
                                   |
                            Drill-down links
                                   |
                  Traces / Logs / Alerts / Runbook
                                   |
                                   v
                      Daily / Weekly Ops Review
                  (approved aggregation + snapshots)
```

### 31.3. Thiết kế 7 panels

| Panel | Nguồn | Query/aggregation | Ý nghĩa |
|---|---|---|---|
| 1. Availability | AppRequests hoặc SLI source | Good/eligible over selected period | SLO |
| 2. Request throughput | AppRequests | Requests/min, trend | Traffic |
| 3. p95 latency | AppRequests/latency metric | Percentile on requests | Tail latency |
| 4. Dependencies | AppDependencies | Failure count/p95 by target | Bottlenecks |
| 5. Queue backlog | Service Bus Metrics + worker event | Active/dead-letter, oldest age | Async pressure |
| 6. DB health | Azure SQL Metrics | CPU/DTU/vCore/connection/wait signals | Saturation |
| 7. Data quality | Instrumentation heartbeat/source reconciliation | Last event and freshness | Avoid green-with-no-data |

Để tránh một trang quá tải, các bảng top exceptions, slow queries, pod restarts và release history ở **drill-down sections**.

### 31.4. KQL summary cho ca trực

Một query **truy vấn số requests, failures và p95 theo role trong last 24h**:

```kusto
AppRequests
| where TimeGenerated >= ago(24h)
| where AppRoleName in ("orders-api", "orders-worker")
| summarize
    Requests=count(),
    Failures=countif(Success == false),
    P95_ms=percentile(DurationMs, 95),
    FirstSeen=min(TimeGenerated),
    LastSeen=max(TimeGenerated)
    by AppRoleName
| extend ErrorRatePct =
    iff(Requests > 0, 100.0 * todouble(Failures) / Requests, real(null))
| order by AppRoleName asc
```

**Cảnh báo:** không gọi `orders-worker` “availability” nếu nó chủ yếu chạy queue jobs chứ không phải HTTP server. Worker SLI phải dựa vào business job events/lag; query trên chỉ là bảng request telemetry nếu worker có request instrumentation.

### 31.5. Bổ sung bảng mối liên hệ release và lỗi

Thiết kế workbook hiển thị deployment annotations khi có schema/log source release events; nếu không có, link tới CI history với time context. Một bản báo cáo sự cố nên ghi **trước/sau release**:

- Traffic và error rate có denominator.
- p95 latency và dependencies.
- Queue depth/lag, worker completion.
- SQL saturation.
- Rollback time và user-impact duration.

Không chốt root cause chỉ từ thời điểm gần nhau.

### 31.6. Khi Service Bus backlog tăng

Ví dụ:

```text
12:00 orders accepted ~300/min
12:00 orders completed ~290/min
12:15 orders accepted ~300/min
12:15 orders completed ~120/min
12:20 queue backlog = 5,000 messages
12:20 oldest message age = 11 min
```

Đây là **số liệu minh họa**. Dashboard phải thể hiện **incoming rate vs processing rate** và saturation/worker failures; chỉ xem backlog count không phân biệt surge hợp lệ với worker crash.

### 31.7. Điều kiện nghiệm thu

- On-call từ dashboard xác định **có user impact hay không trong khoảng 30 giây** (mục tiêu UX, không phải Azure SLA).
- Workbook cho phép chọn production/region/time và thấy top errors + trace details.
- Panel no-data hiển thị rõ khi telemetry mất.
- Operator chỉ có read quyền, Workbook editor có quyền riêng.
- KQL queries có time filter và p95/availability semantics được kiểm thử.
- SLO/report dùng cùng KPI dictionary và query revision.
- Alert có action group, runbook, owner, threshold và thử nghiệm.
- Report tuần có source cutoff, incidents, action items và cost context.

## 32. Runbook 1: Workbook rỗng hoặc “No data”

**Triệu chứng:** bảng request chart rỗng, nhưng ứng dụng vẫn có traffic thực.

### 32.1. Phân loại trước

1. **Không có dữ liệu do không có traffic:** service thực sự idle/paused.
2. **Telemetry không được instrument:** Java agent/SDK/log exporter lỗi.
3. **Dữ liệu chưa ingest:** delay, DCR/transformation/diagnostic issue.
4. **Query sai:** time range, table, AppRoleName, schema/column không đúng.
5. **Scope sai:** Workbook đang chọn workspace/dev resource khác.
6. **Quyền sai:** user viewer thiếu đọc workspace hoặc Azure resource.
7. **Retention hết hạn:** truy vấn ngoài khoảng lưu.

### 32.2. Quy trình

1. Ghi lại Workbook URL/version, parameters, time range và affected panels.
2. Xác minh **Application Insights resource và Log Analytics workspace** đang được query.
3. Chạy KQL nhỏ nhất trên đúng workspace:

   ```kusto
   AppRequests
   | where TimeGenerated > ago(2h)
   | summarize Rows=count(), LastSeen=max(TimeGenerated)
   ```

4. Nếu có rows, kiểm tra `AppRoleName` values, filtering và timestamp.
5. Nếu không có, kiểm tra app instrumentation/exporter, sampling và ingestion health.
6. Xem permissions của user; thử bằng test reader có scope dự kiến.
7. Với cross-resource query, kiểm tra source parameters/resource IDs.
8. Thử lại chart với selected scope/time; không đổi thành giá trị 0 để “đỡ trống”.
9. Ghi root cause và bổ sung freshness alert nếu thiếu.

### 32.3. Điều không nên làm

- Không nâng mọi người lên subscription Contributor vì một Workbook panel access denied.
- Không kéo time range thành All time để che lỗi instrument.
- Không thay `null`/empty thành 0% failure nếu business đã quy định no-data.
- Không copy logs production ra một workspace public để “dễ xem”.

### 32.4. Kết quả khôi phục

Query trả event counts và timestamps như mong đợi, charts có units/time range đúng, data freshness trong ngưỡng và người xem được cấp read permissions thích hợp.

## 33. Runbook 2: Dashboard xanh nhưng khách hàng đang lỗi

**Triệu chứng:** support báo không đặt được đơn; dashboard hiển thị availability 100% và không có critical alert.

### 33.1. Những nguyên nhân thường gặp

- Dashboard chỉ đo API `/health` chứ không đo end-user orders.
- Sai environment/resource scope; đang hiển thị staging.
- KQL lọc mất 5xx hoặc chỉ đếm successful requests.
- Sampling/dropped telemetry/empty source bị ép thành good.
- Service bị blackhole nên **không có requests** để tính rate.
- Async queue/worker fail nhưng API vẫn trả 202 accepted.
- Aggregation quá dài làm che một incident ngắn.

### 33.2. Quy trình

1. Mở user-impact signals từ ingress/client-side logs và business events.
2. Kiểm tra traffic numerator/denominator, no-data signal và last ingestion.
3. Truy vấn logs có **time range cố định bao gồm incident**, không dựa last 5 min hiện tại.
4. Kiểm tra live dependency SQL/Service Bus và worker completion/lag.
5. Xem deployment timeline và recent config changes.
6. So KPI contract với KQL đã deploy, tìm filter bị loại sai.
7. Thiết lập một SLI business hợp lệ (ví dụ orders completed within 2 min).
8. Sửa alert threshold/evaluation nếu chưa phát hiện impact.
9. Kiểm thử giả lập failure/no-traffic scenario trước khi phát hành Workbook.
10. Báo cáo incident gồm detection gap và action owner.

### 33.3. Bài học

Một hệ thống giám sát cần **đo cả việc người dùng hoàn tất hành trình**, không chỉ từng API liveness. “Không có error logs” không đồng nghĩa “không có lỗi” nếu log exporter đã mất kết nối.

## 34. Runbook 3: Workbook chậm và chi phí Logs tăng

**Triệu chứng:** mở Workbook mất hàng chục giây; chi phí Log Analytics hoặc compute tăng sau khi thêm nhiều panels.

### 34.1. Đánh giá

1. Ghi **Workbook revision**, time range mặc định, số queries/panels và số người dùng.
2. Xác định queries nào scan nhiều logs, trả nhiều rows hoặc dùng cross-workspace `join`.
3. Kiểm tra có filter `TimeGenerated` và resource/service scope sớm chưa.
4. Kiểm tra query có trả raw logs 100.000 rows thay vì aggregation/top N.
5. Xem auto-refresh, query frequency, parameter change behavior.
6. Kiểm tra log ingestion growth, retention, table plan và pricing thay đổi.
7. Kiểm tra resource quotas/service performance; đừng chỉ đổ lỗi Workbook.

### 34.2. Khắc phục

- Đặt default time range hẹp, ví dụ 1h/24h.
- Tách overview từ deep-dive, chỉ chạy heavy queries khi cần.
- Pre-aggregate metrics có ý nghĩa khi pattern dùng nhiều.
- Giảm high-cardinality dimensions/PII.
- Hạn chế cross-resource joins, dùng query result size hợp lý.
- Giãn refresh interval theo nhu cầu và freshness SLO.
- Thực hiện performance benchmark trước/sau trên cùng time range/workspace.
- Gắn regression test cho query duration và bảng nào đang dùng.

### 34.3. Không sửa bằng cách xóa logs có ích

Giảm retention hoặc tắt audit logs bừa bãi có thể phá yêu cầu incident/security/compliance. Đánh giá **value of logs, sampling, table plan, archive, retention và cost** theo governance, không đánh đổi khả năng điều tra để dashboard mở nhanh hơn.

## 35. Runbook 4: Báo cáo tuần lệch số liệu dashboard

**Triệu chứng:** báo cáo tuần ghi availability 99,6% nhưng Workbook khi chọn cùng tuần hiện 99,9%.

### 35.1. So sánh từng chiều

| Kiểm tra | Nguồn lệch có thể |
|---|---|
| Kỳ thời gian | Rolling 7d vs calendar week; timezone UTC/local |
| Data cutoff | Báo cáo chốt trước khi late events ingest |
| Resource scope | Dashboard prod region A, report toàn region |
| Business eligibility | 4xx/429/timeouts tính khác nhau |
| Sampling | Query weighted và raw counts khác |
| Aggregation | Average of hourly rates vs ratio of sums |
| Denominator | API requests vs completed orders |
| Query revision | Workbook query mới nhưng report dùng version cũ |
| Retention/reprocessing | Dữ liệu đã restated hoặc expired |

### 35.2. Quy trình đối soát

1. Khóa **start/end UTC, workspace/resource IDs, service list** của cả hai bên.
2. Lấy **numerator/denominator thô** theo ngày/hour, không so chỉ percentage.
3. Kiểm tra sampling weights/telemetry completeness.
4. So query text, revision và filters.
5. Tính lại `sum(good)/sum(eligible)` trên cùng period.
6. Đối chiếu late arrival/backfill và cutoff.
7. Xác định version đúng, lưu reconciliation evidence.
8. Phát hành bản corrected/report revision có giải thích và owner.

### 35.3. Không “chọn số đẹp hơn”

Nếu hai nguồn khác nhau, không tùy ý chọn số cao hơn để báo cáo. Phải quyết định KPI chuẩn từ **data contract và business owner**, rồi sửa hai outputs cho thống nhất.

## 36. Bài tập thực hành

### Bài tập A — Thiết kế Operations Overview

Một ứng dụng Java trên Azure App Service có 2 triệu requests/ngày, Azure SQL database và Service Bus worker. Hãy phác thảo dashboard tối đa **8 panels** cho ca trực, gồm:

- Tín hiệu user-impact và SLO.
- Latency/errors/traffic.
- SQL và queue saturation.
- Telemetry freshness.
- Drill-down link + owner.

**Hướng giải:** đặt availability/error budget, error rate và p95 ở đầu; sau đó backlog/worker completion/SQL saturation; có no-data status, filter environment/time và link runbook. Không để CPU chiếm toàn trang.

### Bài tập B — Chọn dashboard hay Workbook

Ba nhóm: NOC muốn wallboard, SRE muốn điều tra theo Pod/region, CTO muốn weekly summary.

**Nhiệm vụ:** chọn Azure portal dashboard, Monitor Workbook và báo cáo tuần cho từng nhóm; giải thích sự khác nhau giữa live view và bản báo cáo đã chốt.

**Hướng giải:** NOC = dashboard overview, SRE = Workbook drill-down, CTO = report theo kỳ có review/snapshot. Có thể liên kết, không đồng nhất chức năng.

### Bài tập C — Viết KQL request trend

Giả sử table `AppRequests` có 10.000 rows trong 1 giờ, trong đó 300 rows có `Success == false`. Hãy viết KQL tổng hợp `Requests`, `Failed` và `ErrorRatePct` theo 5 phút cho `orders-api`; nêu ý nghĩa của `bin` và xử lý bucket không có data.

**Hướng giải:** dùng `where TimeGenerated >= ago(1h)`, `where AppRoleName == "orders-api"`, `summarize count()/countif() by bin`, `extend ErrorRatePct`. Nếu denominator bằng 0, hiển thị no-data/null; không chia cho 0.

### Bài tập D — SLO với denominator

Trong 30 ngày có 10.000.000 eligible requests, 9.992.000 good requests. SLO là 99,9%.

**Nhiệm vụ:** tính availability và lượng bad events so với budget. Giải thích vì sao 0,1% budget không nhất thiết tương đương một số phút outage cụ thể.

**Hướng giải:** availability = 99,92%; bad requests = 8.000; budget = 10.000; còn 2.000 bad requests có thể tiêu trước khi vi phạm SLO. Request-based budget không tự bằng time-based budget.

### Bài tập E — Weighted error rate

Giờ 1: 10 requests, 5 failures → 50%. Giờ 2: 9.990 requests, 5 failures → khoảng 0,05%.

**Nhiệm vụ:** tính error rate toàn 2 giờ. Vì sao không lấy trung bình `(50% + 0,05%)/2`?

**Hướng giải:** failures = 10 / total = 10.000 → **0,1%**. Bình quân tỷ lệ theo giờ coi mỗi giờ trọng số bằng nhau dù traffic khác.

### Bài tập F — Application Insights sampling

Java instrumentation chỉ gửi một phần request events; dashboard dùng raw `count()` như tổng requests.

**Nhiệm vụ:** mô tả sai lệch có thể có, cách kiểm tra sampling mode/`ItemCount` hoặc metrics nguồn thích hợp, và dữ liệu nào cần cho SLO.

**Hướng giải:** không coi raw sampled rows là traffic total; dùng metrics/weighted events được định nghĩa đúng, có test đối chiếu với ingress/known workload.

### Bài tập G — Workbook parameters

Thiết kế `TimeRange`, `Environment`, `Resource`, `Region` cho một Workbook dùng chung dev/staging/prod.

**Nhiệm vụ:** ghi default values, giới hạn allowed values, query scope, quyền người xem và trường hợp no data.

**Hướng giải:** time default hẹp; prod filter phải dựa nguồn đã gắn resource, không chỉ string; không dùng dropdown như IAM; unauthorized resource phải báo access denied.

### Bài tập H — KQL exceptions/dependencies

Viết KQL tìm top 10 `Target` có failures trong `AppDependencies` trong 2 giờ và top 10 `ExceptionType` trong `AppExceptions`. Hãy nêu cách kiểm tra table schema và sampling trước khi tin kết quả.

**Hướng giải:** time filter sớm, `summarize countif(Success == false)` và `top 10`, không trả raw stack traces nhạy cảm. Với AppExceptions dùng `summarize count() by ExceptionType`.

### Bài tập I — Missing telemetry

Một service chưa nhận request nào trong 15 phút. Dashboard hiển thị error rate 0% và operator kết luận hệ thống khỏe.

**Nhiệm vụ:** thiết kế state **NO_DATA**, heartbeat source, independent platform ingress signal và alert khi log ingestion ngừng.

**Hướng giải:** nếu eligible count = 0, availability/error rate theo contract có thể null/not applicable; cần phân biệt idle và telemetry outage.

### Bài tập J — Chia sẻ Workbook đúng quyền

Operator có quyền đọc Workbook nhưng charts báo forbidden. Developer muốn cấp subscription Contributor.

**Nhiệm vụ:** xác định ba lớp quyền Workbook definition, data sources, edit. Đề xuất least privilege.

**Hướng giải:** cấp read permissions đúng Log Analytics/Application Insights/metrics source, không cấp quyền sửa tài nguyên Azure rộng chỉ để đọc charts.

### Bài tập K — Workbook chậm sau release

Sau khi thêm 20 raw KQL queries tự refresh mỗi 10 giây, Workbook mở mất 40 giây và chi phí query tăng.

**Nhiệm vụ:** thiết kế tối ưu time range, summarization, query scope, conditional panels và refresh interval. Nêu metrics đo trước/sau.

**Hướng giải:** giảm queries toàn retention, trả summaries/top N, dùng drill-down theo nhu cầu và không refresh 30-day report mỗi vài giây.

### Bài tập L — Báo cáo vận hành tuần

Giả sử tuần có 2 incidents, một lần rollback sau deploy và cost tăng 12% do SQL scaling. Hãy viết report gồm:

- Executive summary và kỳ UTC/local.
- SLO/error budget và user impact.
- Incident timeline/root cause đang xác minh.
- Capacity/cost trend.
- Data freshness/cutoff.
- Action items có owner/ETA.

**Hướng giải:** không chỉ copy chart, phải có tiêu chí/denominator, nguồn, kết luận có caveat và hành động rõ.

### Bài tập M — So sánh Workbook với report

Workbook last 7 days cho availability 99,90%, report calendar week cho 99,86%.

**Nhiệm vụ:** đối chiếu start/end UTC, business timezone, ingestion cutoff, eligible/bad counts, sampling, scope và query revision.

**Hướng giải:** lấy cùng numerator/denominator và cùng time range; nếu có late logs, phát hành report revision với giải thích.

### Bài tập N — Dashboard cho queue worker

Service Bus queue có backlog 8.000 messages; biểu đồ active message count giảm mạnh sau một giờ.

**Nhiệm vụ:** chỉ ra lý do đây **không tự** là thành công, và đề xuất các metric bổ sung.

**Hướng giải:** có thể messages expired/dead-letter hoặc consumer complete; cần incoming/outgoing rate, dead-letter, successful business completion, oldest age và worker errors.

### Bài tập O — Incident postmortem

Một application outage 20 phút không kích hoạt alert vì Workbook đang filter sai `AppRoleName`.

**Nhiệm vụ:** lập timeline, customer impact, detection gap, root cause hypothesis, corrective actions và integration tests cho dashboard.

**Hướng giải:** viết tests theo schema agent/telemetry, monitor missing data, version KQL/Workbook, thêm production smoke validation sau deploy.

## 37. Câu hỏi tự kiểm tra

**1. Azure portal dashboard dùng tốt nhất cho việc gì?** Health overview gọn và wallboard; không tự là hệ thống gửi alert hoặc lưu report snapshot.

**2. Azure Monitor Workbook dùng tốt nhất cho việc gì?** Trang điều tra tương tác có parameters, queries, charts và drill-down đa nguồn.

**3. Báo cáo vận hành khác dashboard thế nào?** Báo cáo có kỳ, cutoff, owner, review, diễn giải và action items; dashboard thường hiển thị dữ liệu live.

**4. Workbook có lưu raw logs không?** Không, nó lưu định nghĩa/queries/layout và đọc dữ liệu từ nguồn.

**5. Metrics và Log Analytics logs giống nhau không?** Không; time-series metrics và log tables có schemas, query APIs và behavior khác nhau.

**6. KQL `AppRequests` có sẵn trong mọi Azure workspace không?** Không; phụ thuộc workspace-based Application Insights và instrumentation/schema.

**7. Activity Log thay thế application request logs được không?** Không; Activity Log chủ yếu control-plane/resource activity.

**8. SLI khác SLO ở điểm nào?** SLI là chỉ số thực tế đo được; SLO là mục tiêu cho chỉ số trong window.

**9. Availability 99,9% có nhất thiết là 43,2 phút mất dịch vụ mỗi 30 ngày?** Chỉ trong mô hình time-based; không suy tương đương request-based SLO.

**10. Vì sao cần denominator?** Không thể diễn giải failure rate nếu thiếu số requests đủ điều kiện và quy tắc phân loại.

**11. p95 latency là gì?** Giá trị percentile 95 của các request durations trong tập/window được đo, không phải trung bình latency.

**12. Có nên lấy trung bình p95 của nhiều instances?** Không nếu muốn p95 toàn hệ thống; cần phân phối/histogram hoặc raw samples/aggregation phù hợp.

**13. RED là gì?** Rate, Errors, Duration cho workload xử lý requests.

**14. USE là gì?** Utilization, Saturation, Errors cho resources.

**15. Một Pod CPU thấp có nghĩa hệ thống không nghẽn?** Không; DB locks, queue lag, I/O, thread pool hoặc dependency errors vẫn có thể gây outage.

**16. Vì sao có thể dashboard 0 lỗi nhưng vẫn có incident?** Thiếu telemetry, sai scope, no traffic, sai SLI hoặc async failure.

**17. Vì sao không hiển thị no data thành 100% availability?** Không có denominator/bằng chứng; null/unknown cần trạng thái riêng.

**18. Vì sao time range của Workbook quan trọng?** Quyết định scope dữ liệu, ý nghĩa của metrics và chi phí truy vấn.

**19. Resource picker có phải lớp bảo mật?** Không. Quyền truy cập data source/Workbook vẫn do Azure IAM và data permissions kiểm soát.

**20. Tại sao một người thấy Workbook nhưng charts báo 403?** Có quyền đọc layout nhưng thiếu quyền đọc Log Analytics/Application Insights/resource.

**21. `render timechart` có bắt buộc trong Workbook không?** Không; có thể chọn visualization trong editor, tùy query step/data source.

**22. `bin(TimeGenerated, 5m)` làm gì?** Nhóm timestamps thành buckets 5 phút để summarize.

**23. `countif(Success == false)` có tự là SLO bad request count không?** Không; business SLI và sampling có thể khác.

**24. Vì sao `AppRoleName` cần được chuẩn hóa?** Để filter không bỏ sót services sau deployment/agent upgrade.

**25. Traces có thể thiếu spans vì sao?** Sampling, instrumentation/propagation lỗi hoặc resource query scope không đầy đủ.

**26. Một Service Bus queue giảm backlog có chứng minh worker xử lý thành công?** Không; messages có thể expired/dead-letter.

**27. Azure Monitor Metrics Explorer có thể tự tạo `CPU_CL` trong Log Analytics không?** Không; chỉ có nếu ingest/export thành logs theo pipeline phù hợp.

**28. Resource Graph dùng cho cái gì?** Truy vấn metadata của Azure resources, không phải log request payload.

**29. Azure Resource Graph và Log Analytics chạy cùng một KQL engine đầy đủ không?** Không; hai nguồn/query contexts có khác biệt.

**30. Workbook query chạy chậm nên tối ưu gì đầu tiên?** Time filter, scope, summarize/top N, số panels và auto-refresh.

**31. Vì sao không trung bình tỷ lệ lỗi theo từng giờ để có ngày?** Traffic mỗi giờ khác; cần tỷ lệ của tổng numerators/denominators.

**32. Sampling có thể ảnh hưởng dashboard thế nào?** Counts/percentiles từ raw sampled events có thể lệch; cần trọng số/metrics nguồn thích hợp.

**33. Báo cáo ngày cần ghi timezone và cutoff vì sao?** Để phân biệt window, late events và lịch sử điều chỉnh số liệu.

**34. Báo cáo tuần có thể dùng link Workbook live như snapshot không?** Không nếu cần bản có thể tái hiện; live query có thể thay đổi.

**35. Cost data có luôn real-time như Metrics không?** Không; Cost Management/billing exports có latency và adjustments riêng.

**36. Có nên dùng customer email làm metric dimension?** Không; tăng cardinality và nguy cơ PII.

**37. Alert có cần Action Group không?** Với routing thông báo/automation phù hợp, Action Group là cơ chế phổ biến được hỗ trợ; phải thiết kế owner/escalation.

**38. Dashboard có thay alert rule không?** Không. Dashboard hiển thị, alert đánh giá và thông báo khi quy tắc thỏa.

**39. MTTD và MTTR là gì?** Thời gian phát hiện và khôi phục/sửa chữa sự cố, cần định nghĩa chính xác theo tổ chức.

**40. Tiêu chí cuối cùng của một Workbook tốt?** Giúp người có quyền đúng xác định impact và nguồn sự cố, thấy data freshness, dùng KPI nhất quán, có drill-down/runbook và không tạo rủi ro chi phí/bảo mật.

## 38. Checklist triển khai production

### 38.1. Mục tiêu/KPI và dữ liệu nguồn

- [ ] Có owner, service boundary và audience cho từng dashboard/Workbook/report.
- [ ] Mỗi KPI có **định nghĩa, nguồn, đơn vị, denominator, aggregation và thời gian**.
- [ ] SLI/SLO được business/service owner phê duyệt, có eligibility rules.
- [ ] Có error budget hoặc tiêu chí performance đủ rõ để đánh giá.
- [ ] Không dùng CPU/health endpoint thay end-user/business SLIs.
- [ ] Có RED cho user-facing API và USE cho resource saturation khi phù hợp.
- [ ] Có event/metric phản ánh business workflow async (accepted/completed/failed).
- [ ] Java OpenTelemetry/Application Insights instrumentation được smoke test end-to-end.
- [ ] Log Analytics tables và metric definitions được khám phá từ đúng resources.
- [ ] Diagnostic settings đã bật đúng log categories và destination cần dùng.
- [ ] Có đánh giá sampling/ingestion latency/retention.
- [ ] Không suy rằng Azure Monitor Metrics tự hiện thành KQL table.

### 38.2. Dashboard overview

- [ ] Panel đầu thể hiện **availability, errors, p95 và critical incident/data status**.
- [ ] Traffic, errors, latency có units, time window và source rõ.
- [ ] Có label environment, region, resource/service scope và last refresh.
- [ ] Không trộn dev/staging/prod hoặc các regions không intended.
- [ ] No-data/unknown khác 0 errors/success.
- [ ] Targets/baselines được vẽ/ghi chú theo SLO, không dùng màu trang trí.
- [ ] Có drill-down links từ overview sang Workbook/traces/logs.
- [ ] Owner/on-call/runbook hiển thị, không phụ thuộc chỉ vào màu sắc.
- [ ] Dashboard viewer có quyền read đúng nguồn mà không được quyền edit không cần.
- [ ] Có kiểm tra layout trên màn hình vận hành và accessibility.

### 38.3. Azure Monitor Workbook

- [ ] Workbook có `TimeRange`, `Environment`, `Resource` parameters hữu ích.
- [ ] Default time window hẹp, tránh auto-query toàn retention.
- [ ] Parameters được allowlist/escape đúng, không làm cơ chế authorization.
- [ ] Query resource scope chính xác và dùng fields/schema đang tồn tại.
- [ ] KQL có time filter, resource filter và `summarize/top N` hợp lý.
- [ ] Request/availability query có denominator và xử lý sampling.
- [ ] Percentile tính trên phân phối đúng, không average p95.
- [ ] Charts/tables có units, số mẫu và drill-down path.
- [ ] Critical panels có no-data/freshness checks hoặc companion telemetry.
- [ ] Có section cho dependencies, queue/DB, deployment/change và incident details.
- [ ] Workbook source/template đã được version control với query tests.
- [ ] Có role tách viewer/editor/deployer và quy trình rollback definition.
- [ ] Cross-subscription/resource queries tuân thủ IAM/data classifications.

### 38.4. Alerts và vận hành trực ca

- [ ] Alerts được tạo **riêng**, không chỉ dùng Workbook màu đỏ.
- [ ] Threshold/window/severity/action group có nguồn gốc từ SLO/risk.
- [ ] Có minimum traffic threshold/no-data behavior khi phù hợp.
- [ ] Alerts có owner/on-call escalation, suppression policy có audit.
- [ ] Incident links dẫn đến đúng Workbook/tab/time context.
- [ ] Đã kiểm thử alert fired/resolved và notification routing.
- [ ] Có phân biệt external user impact với infrastructure warning.
- [ ] Có release/deployment annotations và change history đủ điều tra.
- [ ] Có runbooks cho missing data, false green dashboard và cost regression.
- [ ] Alert fatigue/MTTD/MTTA/MTTR được review định kỳ.

### 38.5. Báo cáo ca/ngày/tuần

- [ ] Báo cáo có fixed period start/end, timezone và **data cutoff**.
- [ ] Report ID, owner, approver, query revision và nguồn được ghi rõ.
- [ ] Có trạng thái **PRELIMINARY/FINAL/RESTATED** khi dữ liệu chưa chốt.
- [ ] SLO numerator/denominator được đối chiếu với Workbook trên cùng kỳ.
- [ ] Incident summary có impact, timeline, evidence, mitigation và root cause status.
- [ ] Có deployment/capacity/traffic changes và business workflow health.
- [ ] Chi phí có billing period/attribution và caveat data freshness.
- [ ] Action items có owner, priority, ETA và link tracking.
- [ ] Báo cáo nhạy cảm được chia sẻ trong kênh có RBAC/retention phù hợp.
- [ ] Snapshot/evidence được lưu khi audit yêu cầu, không chỉ live Workbook URL.
- [ ] Khi cập nhật số liệu đã công bố có version và giải thích restatement.

### 38.6. Dữ liệu, bảo mật và chi phí

- [ ] Synthetic tests kiểm tra KQL và expected aggregates.
- [ ] Có golden dataset cho error rate/percentile/empty windows khi cần.
- [ ] Dữ liệu missing/stale không bị biến thành 0 good/failure sai.
- [ ] Có monitoring cho completeness theo cluster/region và ingest delay.
- [ ] Queries không trả PII/token/connection string ra dashboard shared.
- [ ] Log ingestion/export query cost được theo dõi và gắn budget.
- [ ] Không dùng high-cardinality customer/order IDs làm metric labels.
- [ ] Workbook revision thay đổi qua PR/review/deploy approval.
- [ ] Dashboard/alert/report có regression test sau agent/SDK update.
- [ ] Azure RBAC/workspace access và query source đều được kiểm tra bằng principal thực.
- [ ] Có retention/archival policy đáp ứng incident/legal requirements.
- [ ] Có runbook và owner cho cost anomaly, report mismatch, missing telemetry.

## 39. Kết luận

**Dashboard, Azure Monitor Workbook và báo cáo vận hành** là ba cách nhìn bổ sung cho cùng hệ thống, không phải ba tên khác nhau của một biểu đồ. **Dashboard** giúp người trực nhận biết nhanh tình trạng dịch vụ; **Workbook** giúp chọn thời gian/tài nguyên, truy vấn **Azure Monitor Metrics, Log Analytics/KQL, Application Insights** và drill-down để tìm nguyên nhân; **báo cáo vận hành** chốt kỳ số liệu, đánh giá **SLO, sự cố, rủi ro, chi phí và hành động tiếp theo**.

Với ứng dụng Java và các dịch vụ Azure như AKS/App Service, Azure SQL, Service Bus và Key Vault, hãy bắt đầu từ **SLI/SLO có denominator đúng và telemetry đáng tin**, sau đó mới chọn layout/visualization. Mọi panel cần scope, đơn vị, time range và trạng thái **no data** rõ ràng. Workbooks và báo cáo cần dùng cùng **KPI dictionary, query version, access control và data cutoff**, đồng thời có runbooks/alerts hoạt động độc lập với việc ai đó đang mở dashboard.

Một hệ thống observability được vận hành tốt không chỉ tạo biểu đồ đẹp: nó giúp trả lời **khách hàng có bị ảnh hưởng không, từ khi nào, tại sao, ai chịu trách nhiệm và thay đổi nào ngăn sự cố lặp lại**. Khi kết hợp các câu trả lời ấy với quản trị **RBAC, bảo vệ dữ liệu, kiểm soát chi phí và review định kỳ**, Azure Monitor trở thành nền tảng cho quyết định vận hành có thể kiểm chứng và cải thiện liên tục.
