# Thực hành giám sát, thử tải và diễn tập khôi phục hệ thống

## 1. Mục tiêu và bối cảnh bài thực hành

Một hệ thống chỉ được xem là sẵn sàng vận hành khi nhóm kỹ thuật có thể trả lời bằng **bằng chứng**: dịch vụ có khỏe từ góc nhìn người dùng không, chịu được bao nhiêu tải, điểm nghẽn ở đâu, cảnh báo có đến đúng người và khi một thành phần hỏng thì hệ thống khôi phục trong bao lâu. Việc tạo tài nguyên Azure thành công hoặc thấy trạng thái `Running` không trả lời được những câu hỏi này.

Trong chương **Kiến trúc và thực hành tổng hợp** của module `CLOUD_PROVIDERS_AZURE`, bài học kết nối kiến thức từ subscription, resource group, Microsoft Entra ID, VNet, compute, storage, database, triển khai, giám sát, bảo mật và chi phí để thực hành ba vòng liên tục:

1. **Giám sát:** xác định hành trình nghiệp vụ, đo SLI/SLO, thu metric–log–trace, tạo cảnh báo và kiểm tra đường thông báo.
2. **Thử tải:** mô hình hóa lượng request, chạy baseline/ramp/peak/stress, tìm điểm nghẽn và đánh giá khả năng chịu tải khi một thành phần suy giảm.
3. **Diễn tập khôi phục:** kích hoạt lỗi **có kiểm soát** hoặc thử restore ở môi trường cô lập, đo RTO/RPO và tính toàn vẹn dữ liệu, cập nhật runbook và đánh giá sau sự cố.

Bài học sử dụng **ứng dụng giả định `orders`**, gồm API đặt đơn, worker xử lý sự kiện, database và blob storage. Các số liệu về traffic, ngưỡng và thời gian là **giả định học tập**, không phải SLA hay cam kết sẵn có của Azure.

### 1.1. Kết quả cần nộp

Kết thúc thực hành, người học có:

- Sơ đồ workload và bảng mục tiêu SLI/SLO, RTO/RPO được chủ sở hữu nghiệp vụ xác nhận.
- Dashboard và truy vấn KQL đọc được request success, latency, dependency errors và saturation.
- Ít nhất một alert có đường thông báo đã kiểm thử riêng, kèm runbook cho người trực.
- Kịch bản thử tải có giới hạn, kết quả p95/p99, throughput, error rate, tài nguyên/chi phí và nguyên nhân nghẽn.
- Bằng chứng về một bài tập failover ứng dụng và một bài test restore dữ liệu được tách phạm vi rõ ràng.
- Timeline UTC, phép đo thời gian phục hồi, đối soát dữ liệu đã xác nhận và báo cáo hậu kiểm có action items.

**Giới hạn an toàn:** Không dùng tài khoản, dữ liệu thanh toán hoặc khách hàng thật để sinh tải. Không gây lỗi production, không tắt backup, không thực hiện forced failover trên dữ liệu thật để hoàn thành bài tập.

## 2. Kiến trúc mẫu và phạm vi đánh giá

Ứng dụng `orders` có giao dịch `POST /orders` và `GET /orders/{id}`. Một lần đặt đơn tạo record ở database, phát sự kiện vào queue, worker tạo tệp xác nhận trong blob storage. Người dùng có thể đăng nhập qua Microsoft Entra ID hoặc một hệ thống identity phù hợp; API dùng Managed Identity để truy cập các dịch vụ Azure hỗ trợ.

~~~mermaid
flowchart TB
    U["Người dùng / synthetic tests"] --> EDGE["Azure Front Door / ingress"]
    EDGE --> A["Orders API Region A"]
    EDGE --> B["Orders API Region B (dự phòng)"]
    A --> DB["Azure SQL / database chính"]
    B --> DB
    A --> Q["Queue / message broker"]
    B --> Q
    Q --> WK["Background worker"]
    WK --> ST["Azure Blob Storage"]
    A --> ID["Entra ID / Managed Identity / Key Vault"]
    B --> ID
    MON["Azure Monitor + App Insights + Log Analytics"] -.-> EDGE
    MON -.-> A
    MON -.-> B
    MON -.-> DB
    MON -.-> Q
    MON -.-> WK
    OPS["On-call / runbook / alerts"] -.-> MON
~~~

Đây là **sơ đồ logic**. Nếu database chỉ ở một region thì API Region B vẫn phụ thuộc dữ liệu ở region đó; việc có hai API **chưa chứng minh DR cấp region**. Muốn thực hành failover dữ liệu, workload phải có replica/failover group hoặc bản sao lưu có thể khôi phục được theo dịch vụ cụ thể.

### 2.1. Bảng inventory cần điền

| Thành phần | Scope/owner | Chỉ số sức khỏe | Lỗi sẽ tạo tác động gì? |
| --- | --- | --- | --- |
| Azure Front Door hoặc ingress | Platform | Origin health, HTTP 5xx, latency | Người dùng không tới API khỏe |
| App Service/VM/AKS API | App/SRE | RPS, success, p95, CPU, memory nếu có | Không tạo/đọc được đơn |
| Database | DBA | Query latency, kết nối, CPU/IO, throttling, replication | Lỗi ghi/đọc, rủi ro dữ liệu |
| Queue và worker | App | Backlog, oldest-message-age, dead-letter, retries | Đơn được tạo nhưng xử lý trễ |
| Blob Storage | Data/platform | Request success/latency, capacity, auth failures | Không tạo/đọc tệp xác nhận |
| Identity/Key Vault | Security | Auth failures, access denied, availability | API không lấy được token/secret |
| VNet, DNS, Private Endpoint | Network | DNS, TCP/TLS, flow, connection tests | Tài nguyên chạy nhưng không kết nối |
| Monitoring/alerting | SRE | Ingest health, alert delivery, data latency | Không phát hiện hoặc đánh giá được lỗi |

Hãy thêm **subscription ID, resource group, region, SKU/tier, dependency FQDN, người trực và đường dẫn dashboard** của môi trường thực tế. Chỉ dùng dữ liệu/scope mà người học được phép truy cập.

### 2.2. Những câu hỏi không thể bỏ qua

- Nếu API Region A lỗi, Front Door có đưa request tới Region B không? Health probe kiểm tra điều gì?
- Nếu database region lỗi, API B có thể đọc/ghi vào dữ liệu được phục hồi không?
- Nếu một worker không chạy, queue có tồn đọng mà API vẫn trả HTTP 200 không?
- Nếu token/secret hết hạn, các synthetic tests có phát hiện được không?
- Sau failover, đơn được xác nhận trước đó có còn đủ và không trùng không?

Mỗi câu trả lời cần **bằng chứng riêng**. Không được kết luận hệ thống khỏe chỉ bằng CPU thấp.

## 3. Xác định SLI, SLO, RTO và RPO trước khi chạy thử

### 3.1. SLI và SLO

**Service Level Indicator (SLI)** là phép đo chất lượng dịch vụ, ví dụ tỷ lệ đặt đơn thành công hoặc p95 latency. **Service Level Objective (SLO)** là mục tiêu của phép đo đó trong cửa sổ đã định nghĩa.

Mục tiêu bài tập giả định:

| Chỉ số | Định nghĩa | Mục tiêu giả định |
| --- | --- | --- |
| Availability SLI | Tỷ lệ giao dịch đặt đơn hợp lệ trả trạng thái thành công, không trùng | **≥ 99,9%** trong tháng |
| API latency | p95 của `POST /orders` thành công ở tải bình thường | **< 500 ms** |
| Read latency | p95 của `GET /orders/{id}` | **< 300 ms** |
| Asynchronous processing | p95 thời gian từ đơn đã commit đến worker xử lý hoàn tất | **< 30 s** |
| Error rate lúc peak | Tỷ lệ lỗi server/timeout trong cửa sổ thử | **< 1%** |
| Detection | Thời gian từ lúc user impact đến cảnh báo được phát hiện | **≤ 3 phút** |
| Recovery | Thời gian từ `T_impact` đến đạt tiêu chí khôi phục | **RTO ≤ 30 phút** |
| Recovery point | Độ cũ dữ liệu tối đa theo nghiệp vụ trong kịch bản phục hồi | **RPO ≤ 5 phút**, tùy phân loại dữ liệu |

**Cảnh báo:** Một yêu cầu nghiệp vụ có thể đòi **không mất bất kỳ đơn đã xác nhận/thanh toán nào**. Khi đó RPO năm phút chung cho các bản ghi bình thường không hợp thức hóa việc mất đơn đã xác nhận; cần có cơ chế giao dịch/đối soát hoặc yêu cầu RPO riêng cho dữ liệu đó.

### 3.2. Cách chọn mẫu số cho availability

Ví dụ:

~~~text
Valid business transactions:       100.000
Successful unique transactions:     99.920
Failed/timeout transactions:             80

Success rate = 99.920 / 100.000 × 100% = 99,92%
Error rate   =     80 / 100.000 × 100% = 0,08%
~~~

Nếu API trả HTTP 200 nhưng đơn không được ghi hoặc bị tạo trùng, không xem là thành công nghiệp vụ. Một phép đo chỉ dựa trên status code là **SLI HTTP**, chưa chắc là **SLI của luồng đặt đơn**.

Với SLO availability **99,9%** trong tháng 30 ngày, ngân sách lỗi theo thời gian tương đương khoảng:

~~~text
30 ngày × 24 giờ × 60 phút × (1 − 0,999)
= 43,2 phút tương đương không sẵn sàng
~~~

Đây là phép quy đổi khi đo theo thời gian liên tục, không tự động là định nghĩa error budget nếu tổ chức đo availability theo **tỷ lệ request**. Phải giữ nhất quán mẫu số và cửa sổ SLO.

### 3.3. Phân biệt thời gian khôi phục và điểm khôi phục

- **RTO (Recovery Time Objective):** giới hạn thời gian từ lúc tác động xảy ra đến khi dịch vụ phục hồi mức đáp ứng yêu cầu. Đo thực tế bằng `T_recovered − T_impact` với điều kiện kết thúc được định nghĩa trước.
- **RPO (Recovery Point Objective):** giới hạn mức dữ liệu có nguy cơ mất theo điểm phục hồi. Phải đối chiếu **timestamp và ID của transaction đã được xác nhận**, không lấy downtime thay cho RPO.
- **MTTD/MTTR:** trung bình thời gian phát hiện/khôi phục qua nhiều sự cố; một lần diễn tập chỉ cho thời gian quan sát của lần đó, không đủ tính trung bình đại diện.

Một hệ thống có thể đạt RTO 10 phút nhưng vẫn mất đơn đã xác nhận: **không thể tuyên bố toàn bộ diễn tập thành công**.

## 4. Thiết lập vùng thử và giới hạn an toàn

### 4.1. Phạm vi được phép tác động

Môi trường lab nên có:

~~~yaml
exercise_id: "orders-observe-load-dr-lab"
environment: "staging-isolated"
subscription: "<test-subscription>"
resource_group: "rg-orders-lab"
business_owner: "<business-role>"
technical_owner: "<sre-role>"
data_classification: "synthetic-only"
allowed_targets:
  - "staging-api"
  - "staging-database"
  - "test-ingress-origin"
prohibited_targets:
  - "production-database"
  - "production-payment-provider"
  - "shared-identity-control-plane"
approvals:
  load_test: "<owner>"
  failure_injection: "<exercise-controller>"
stop_conditions:
  - "Ảnh hưởng production ngoài phạm vi"
  - "Dữ liệu thật xuất hiện trong đường test"
  - "Throttling lan sang dịch vụ dùng chung"
  - "Chi phí hoặc giới hạn vượt mức duyệt"
cleanup_owner: "<platform-role>"
~~~

Mẫu trên là **exercise charter** phục vụ quản trị, không phải YAML được một dịch vụ Azure tự động thi hành. Thay placeholder bằng dữ liệu được phép. Trước khi thử lỗi, phải có người điều phối (Exercise Controller) có quyền dừng bài tập.

### 4.2. Tách dữ liệu và quyền

- Tạo tenant/user và order ID riêng cho synthetic data; gắn `exercise_id` để lọc sau.
- Sử dụng Managed Identity hoặc test identity có quyền tối thiểu; tuyệt đối không đưa token, SAS, connection string có secret vào file tải hoặc báo cáo.
- Chặn thông báo/email/webhook tới khách hàng thật; không gọi gateway thanh toán thật từ bài test.
- Giới hạn ingress nguồn sinh tải, rate và tổng số request; bảo vệ môi trường dùng chung.
- Ghi baseline và backup/recovery point trước mọi bài test làm thay đổi dữ liệu.
- Đặt Azure Cost Management budget/alerts phù hợp. **Budget không tự dừng phí**, vì vậy phải có quota, giới hạn thời gian và người chịu trách nhiệm cleanup.

### 4.3. Kịch bản nào cần cô lập?

| Kịch bản | Nên thực hiện ở đâu? | Không nên làm |
| --- | --- | --- |
| Load test baseline/ramp | Staging đại diện kiến trúc, có giới hạn tải | Bắn tải không giới hạn vào production |
| Thử origin failover | Front Door/origin **test** hoặc test route cô lập | Tắt một origin production chỉ để học |
| Database restore | Database/resource group **khác production** | Restore đè dữ liệu thật |
| Kiểm tra alert delivery | Action Group test + alert điều khiển ở staging | Tạo sự cố production để “thử cho chắc” |
| Kiểm tra region DR | Tabletop hoặc môi trường test đã thiết kế DR | Forced failover account/database production tùy tiện |

## 5. Thiết kế telemetry: metrics, logs, traces và synthetic checks

Không có một dashboard duy nhất cho toàn bộ hệ thống. Cần thu dữ kiện theo cả **control plane**, **data plane**, ứng dụng và trải nghiệm người dùng.

| Loại telemetry | Dùng để hiểu gì? | Ví dụ Azure |
| --- | --- | --- |
| **Metrics** | Giá trị số theo thời gian, dễ alert nhanh | Azure Monitor resource metrics, CPU, request rate, latency |
| **Application logs** | Lý do nghiệp vụ/kỹ thuật, lỗi cụ thể | Structured logs trong Log Analytics hoặc Application Insights |
| **Distributed traces** | Luồng một request qua API, database, queue và downstream | Application Insights/OpenTelemetry instrumentation |
| **Synthetic transactions** | Hành trình từ góc nhìn người dùng bên ngoài | Availability tests hoặc script có kiểm soát |
| **Management activity** | Ai đổi resource, khi nào, operation thành công hay lỗi | Azure Activity Log |
| **Platform health** | Tình trạng sự kiện Azure có liên quan resource/region được hỗ trợ | Azure Resource Health, Azure Service Health |
| **Business events** | Đơn đã commit, được xử lý, thanh toán hoặc bị trùng | Application/business telemetry độc lập |

**Không nhầm control plane với data plane.** Activity Log có thể cho biết có thay đổi App Service, không tự chứa tất cả exception của API. Resource Health khỏe không chứng minh đường đi `POST /orders` hoạt động.

### 5.1. Các trường cần tương quan

Dùng structured logs có những trường:

~~~json
{
  "timestampUtc": "2026-11-20T10:00:00Z",
  "service": "orders-api",
  "environment": "staging",
  "region": "region-a",
  "operation": "create-order",
  "correlationId": "trace-example-0001",
  "synthetic": true,
  "exerciseId": "orders-observe-load-dr-lab",
  "orderId": "lab-order-0001",
  "result": "success",
  "latencyMs": 187
}
~~~

Không cho địa chỉ email, số điện thoại, token hoặc thông tin thanh toán vào log. Ghi `correlationId` xuyên suốt ingress → API → database/queue/worker. Nếu một request phát sinh nhiều thao tác bất đồng bộ, có thể cần **trace ID và business event ID** để nối cả chuỗi.

### 5.2. Instrumentation có ý nghĩa

- HTTP inbound: method, route template, status, duration, region, instance, test run ID.
- Dependency outbound: database/Storage/queue calls, timeouts, retry count và duration.
- Background worker: `message_age`, backlog, retries, dead-letter và thời gian xử lý.
- Business: `order_created`, `order_processed`, `order_failed`, `order_duplicate_blocked` theo ID duy nhất.
- App capacity: CPU, memory, GC/heap đối với Java, thread pool, connection pool; khả năng metric phụ thuộc App Service/VM/AKS và agent.
- Data health: replication lag/recovery state khi có chức năng hỗ trợ, DB saturation và backup status.

Đảm bảo logs có **retention** phù hợp với mục tiêu điều tra, sampling được hiểu đúng và đồng hồ thống nhất UTC. Sampling có thể làm thông số request count/p95 ở telemetry bị lệch nếu cách xử lý không phù hợp; nên đối chiếu với bộ đo ở load generator.

## 6. Azure Monitor và Application Insights: những thao tác đầu tiên

### 6.1. Thiết lập workspace và theo dõi ứng dụng

Trong môi trường test, chuẩn bị **Log Analytics workspace** và **Application Insights** theo cách tích hợp được workload hỗ trợ. Chọn phương thức instrumentation cho ứng dụng Java/App Service/AKS phù hợp, xác nhận:

1. Requests xuất hiện với application role/service và timestamp.
2. Dependencies có thể liên hệ cùng một trace/operation ID.
3. Exception và log ứng dụng có đủ thông tin để chẩn đoán, không làm lộ PII.
4. Synthetic test hoặc workload request vào staging xuất hiện trên dashboard.
5. Team on-call có quyền đọc truy vấn/alert ở scope đã xác minh.

**Azure Monitor không tự thu mọi log cần thiết nếu chưa bật diagnostic settings/instrumentation.** Kiểm tra chi phí ingest/retention và tránh bật debug logging vô thời hạn khi thử tải.

### 6.2. Lệnh Azure CLI chỉ đọc context và resource

~~~bash
# Kiểm tra subscription/tenant để tránh điều tra nhầm môi trường.
az account show \
  --query "{subscription:id,tenant:tenantId,name:name}" \
  -o json

# Kiểm kê trong resource group của bài thực hành.
az resource list \
  --resource-group rg-orders-lab \
  --query "[].{name:name,type:type,location:location,id:id}" \
  -o table

# Liệt kê metric mà một resource thực sự hỗ trợ.
az monitor metrics list-definitions \
  --resource "/subscriptions/<subscription-id>/resourceGroups/rg-orders-lab/providers/<provider>/<type>/<resource-name>" \
  -o table
~~~

Ký hiệu `<...>` là placeholder. Chỉ khi đã biết tên metric, namespace và aggregation của resource mới dùng `az monitor metrics list`. Các dịch vụ managed PaaS không nhất thiết có cùng CPU/memory metric như VM.

### 6.3. Kiểm tra thay đổi control plane quanh thời điểm lỗi

~~~bash
az monitor activity-log list \
  --resource-group rg-orders-lab \
  --start-time "2026-11-20T09:30:00Z" \
  --end-time "2026-11-20T11:00:00Z" \
  --query "[].{utc:eventTimestamp,operation:operationName.value,status:status.value,correlation:correlationId}" \
  -o table
~~~

Các mốc UTC là minh họa. Nếu cùng lúc xảy ra deployment và 5xx tăng, đó là **tín hiệu để điều tra**, chưa phải bằng chứng quan hệ nhân quả; cần xem dependency errors, bản phát hành và kết quả rollback.

## 7. Truy vấn KQL đo SLI và phát hiện điểm nghẽn

Các ví dụ này giả định ứng dụng gửi telemetry vào **workspace-based Application Insights** có các bảng `AppRequests` và `AppDependencies`. Với workspace, agent, sampling hoặc kiểu thu thập khác, tên bảng/cột có thể thay đổi; phải kiểm tra schema thực tế.

### 7.1. Tỷ lệ request thất bại và p95 theo phút

~~~kusto
AppRequests
| where TimeGenerated between (
    datetime(2026-11-20T09:30:00Z) .. datetime(2026-11-20T11:00:00Z))
| summarize
    Requests = sum(ItemCount),
    Failures = sumif(ItemCount, Success == false),
    P95LatencyMs = percentile(DurationMs, 95)
  by AppRoleName, bin(TimeGenerated, 1m)
| extend ErrorRatePct =
    iff(Requests == 0, real(null), 100.0 * Failures / Requests)
| order by TimeGenerated asc
~~~

`ItemCount` có thể thể hiện trọng số khi telemetry sampling được áp dụng. Phép đo p95 qua các mẫu vẫn cần đối chiếu với dữ liệu gốc khi có sampling; đừng coi con số tròn trên dashboard là độ trễ của mọi request.

### 7.2. Tách endpoint quan trọng

~~~kusto
AppRequests
| where TimeGenerated > ago(1h)
| summarize
    Requests = sum(ItemCount),
    Failed = sumif(ItemCount, Success == false),
    P95Ms = percentile(DurationMs, 95)
  by Name, ResultCode, AppRoleName
| order by Failed desc, P95Ms desc
~~~

Tùy instrumentation, `Name` có thể là route template hoặc tên thao tác. Nếu lộ path chứa ID khách hàng trong telemetry, chỉnh cách instrumentation để log **route template** thay vì URL thô.

### 7.3. Phân tích dependency lỗi

~~~kusto
AppDependencies
| where TimeGenerated > ago(1h)
| summarize
    Calls = sum(ItemCount),
    Failures = sumif(ItemCount, Success == false),
    P95DependencyMs = percentile(DurationMs, 95)
  by AppRoleName, Type, Target
| extend FailureRatePct =
    iff(Calls == 0, real(null), 100.0 * Failures / Calls)
| order by Failures desc
~~~

Nếu p95 của API tăng cùng p95 dependency database, cần kiểm tra database connections, query plans, throttling và network RTT. Không vội tăng CPU của API trước khi biết bottleneck.

### 7.4. Truy vấn phục vụ một cảnh báo dựa trên lỗi

~~~kusto
AppRequests
| where TimeGenerated >= ago(5m)
| summarize
    Requests = sum(ItemCount),
    Failed = sumif(ItemCount, Success == false)
| extend FailureRatePct =
    iff(Requests == 0, real(null), 100.0 * Failed / Requests)
| where Requests >= 30 and FailureRatePct > 2.0
~~~

Đây là ví dụ **điều kiện nghiệp vụ** khi có tối thiểu 30 request trong cửa sổ 5 phút. Nếu không có request nào, truy vấn không báo lỗi cao, nhưng hệ thống có thể đã mất traffic hoàn toàn; vì vậy cần **cảnh báo availability/synthetic** riêng. Khi tạo Azure Monitor log alert, xem quy tắc xử lý kết quả query, aggregation, evaluation frequency và hành vi no-data của loại alert đang dùng.

### 7.5. Đo alert và đường thông báo

Một alert phù hợp có **signal**, **threshold**, **lookback window**, **evaluation frequency**, **severity**, **action group** và **runbook link**. Không nên phát nhiều thông báo trùng cho cùng root symptom nếu có thể nhóm theo workload/incident. Dữ liệu từ Log Analytics có độ trễ ingest, nên alert dựa trên log không phải lúc nào cũng phù hợp cho mục tiêu phát hiện ở mức vài giây.

## 8. Dashboard và bộ cảnh báo tối thiểu

### 8.1. Dashboard phục vụ on-call

Tổ chức thành ba tầng:

| Nhóm | Biểu đồ/metric | Câu hỏi |
| --- | --- | --- |
| **Golden signals** | Traffic, errors, latency, saturation | Người dùng đang chịu tác động gì? |
| **Dependencies** | Database latency/errors, queue backlog, storage failures, identity/Key Vault errors | Tầng nào tạo bottleneck? |
| **Recovery & operations** | Region/origin health, failover status, recent deployments, backup health, synthetic tests | Có thể phục hồi và xác nhận từ đâu? |

Gắn filter theo **subscription, resource group, region, application role, deployment version và test run ID** khi dữ liệu cho phép. Với một bài thử tải, phải tách dữ liệu synthetic khỏi traffic thật để không phá ý nghĩa của báo cáo SLO production.

### 8.2. Mẫu các alert cần cấu hình

| Alert | Điều kiện minh họa | Hành động |
| --- | --- | --- |
| Synthetic create-order thất bại | Nhiều lần thất bại theo cửa sổ đã duyệt | Báo on-call về lỗi hành trình |
| HTTP error rate | > 2% trong 5 phút, đủ lượng request | Mở runbook API/ingress |
| p95 API latency | > 500 ms trong cửa sổ có đủ mẫu | Điều tra dependency và saturation |
| Queue backlog age | Tuổi message cũ nhất > 60 s khi có workload | Kiểm tra worker, dead-letter và retry |
| Database saturation/timeout | Chỉ số của service vượt ngưỡng baseline | DBA + app owner cùng điều tra |
| Region/origin unhealthy | Probe tương ứng không đạt | Kiểm tra định tuyến và năng lực vùng còn lại |
| Backup job/replication không khỏe | Sự kiện/metric phù hợp dịch vụ | Data/SRE kiểm tra khả năng DR |

Mọi ngưỡng đều cần thử và hiệu chỉnh theo **baseline thực**, không coi ví dụ là threshold Azure khuyến nghị.

### 8.3. Cấu hình một alert qua Azure Portal

1. Chọn đúng resource hoặc workspace trong **Azure Monitor → Alerts → Create**.
2. Chọn scope và signal thích hợp: metric hoặc log query, kiểm tra đơn vị, aggregation và window.
3. Chọn threshold theo bảng SLI/SLO, lưu kèm điều kiện tối thiểu để tránh alert do mẫu quá nhỏ.
4. Liên kết **Action Group** được phép: email nhóm, kênh on-call hoặc workflow phù hợp.
5. Thêm mô tả, runbook, severity và owner; chỉ cấp quyền cần thiết cho người nhận.
6. Lưu; thử riêng **đường gửi của Action Group**, rồi nếu có thể tạo sự kiện staging có kiểm soát để xác minh **đường từ signal đến alert**.

**Action Group test chỉ kiểm tra một phần đường thông báo**, không chứng minh điều kiện metric/log alert và ingestion luôn vận hành đúng. Ngược lại, alert fired không chứng minh người trực đã nhận, đọc và xử lý.

## 9. Lập kế hoạch thử tải trước khi sinh request

Mục tiêu của load test là trả lời các câu hỏi kiến trúc đã định trước, không phải tạo RPS lớn nhất có thể.

### 9.1. Các kiểu thử tải

| Kiểu | Cách thực hiện | Điều cần học |
| --- | --- | --- |
| **Baseline** | Tải thấp, ổn định, xác nhận dữ kiện ban đầu | Độ trễ chuẩn và chất lượng instrumentation |
| **Load / ramp** | Tăng từng bước tới tải dự kiến | Khả năng đáp ứng theo đường tăng tải |
| **Peak** | Duy trì tải đỉnh thiết kế trong thời gian đủ đo | SLO tại peak, backlog và quota |
| **Stress** | Tăng qua giới hạn dự kiến trong phạm vi an toàn | Điểm gãy, load shedding và phục hồi |
| **Spike** | Tăng nhanh rồi giảm | Autoscale reaction, retry storm, cold starts |
| **Soak / endurance** | Duy trì tải vừa đủ trong thời gian dài | Memory leak, connection leak, log/disk growth |
| **Resilience under load** | Mất instance/origin khi còn tải đại diện | N−1 capacity, failover latency và tính đúng dữ liệu |

Mỗi loại phải có **stop conditions**, tài nguyên cần giám sát và người điều phối. Không chạy stress/soak kéo dài trong môi trường chia sẻ nếu chưa có phê duyệt ngân sách và khả năng chịu tải.

### 9.2. Open workload và closed workload

- **Open model:** lên lịch request đến theo một rate mục tiêu (ví dụ 60 requests/giây) ngay cả khi server chậm, để quan sát hệ thống khi đến hạn tải.
- **Closed model:** một số virtual users gửi request, chờ phản hồi/thời gian nghĩ rồi gửi tiếp; khi server chậm, thông lượng có thể giảm tự nhiên.

Hai mô hình có giá trị khác nhau. Nếu đang đo khả năng chịu **arrival rate**, cần chú ý **achieved RPS** chứ không chỉ target. Nếu bộ sinh tải không đủ tài nguyên, kết quả có thể bị giới hạn bởi load generator.

### 9.3. Kịch bản nghiệp vụ và tỷ lệ request

Ví dụ workload tham chiếu ở tải peak:

~~~text
60%: GET /api/catalog               (read-only)
30%: GET /api/orders/{syntheticId}  (read-only với dữ liệu test)
10%: POST /api/orders               (ghi dữ liệu test, idempotent)

Target total arrival rate:            100 requests/giây
Expected read rate:                    90 requests/giây
Expected write rate:                   10 requests/giây
~~~

Không lấy 100 RPS làm KPI tự thân. Một POST có thể tiêu thụ nhiều database operation và queue events hơn GET. Thử tải cần phản ánh đúng **mix, payload size, phân bố tenant/khách hàng và các request đồng thời**.

**Bắt đầu an toàn** bằng read-only endpoint ở staging để xác nhận khả năng đo. Chỉ thêm write test khi đã tạo tài khoản test/ledger riêng, giới hạn số bản ghi, có idempotency và cleanup.

## 10. Tạo kịch bản thử tải bằng k6

Ví dụ sau dùng **k6** như công cụ load generator chạy từ môi trường test/local/CI có kiểm soát. **Không** khẳng định file JavaScript k6 được nhập trực tiếp vào Azure Load Testing; Azure Load Testing có luồng URL-based hoặc framework/script được dịch vụ hỗ trợ riêng, cần chọn đúng công cụ.

### 10.1. Mẫu k6 đọc catalogue

Lưu mã dưới tên `catalog-load.js` trong môi trường người học. Đường dẫn/ngữ cảnh là một **ví dụ minh họa**, không phải file bài học sẽ tạo thêm.

~~~javascript
import http from 'k6/http';
import { check } from 'k6';

export const options = {
  scenarios: {
    catalog_read: {
      executor: 'ramping-arrival-rate',
      startRate: 5,
      timeUnit: '1s',
      preAllocatedVUs: 40,
      maxVUs: 200,
      stages: [
        { duration: '3m', target: 20 },
        { duration: '5m', target: 20 },
        { duration: '3m', target: 60 },
        { duration: '5m', target: 60 },
        { duration: '3m', target: 20 }
      ],
      gracefulStop: '30s'
    }
  },
  thresholds: {
    'http_req_failed{journey:catalog-read}': ['rate<0.01'],
    'http_req_duration{journey:catalog-read}': ['p(95)<500']
  }
};

export default function () {
  const baseUrl = __ENV.BASE_URL;
  if (!baseUrl) {
    throw new Error('Missing BASE_URL for staging');
  }

  const headers = {
    'x-test-run-id': __ENV.TEST_RUN_ID || 'staging-load-lab'
  };

  if (__ENV.TEST_TOKEN) {
    headers.Authorization = 'Bearer ' + __ENV.TEST_TOKEN;
  }

  const response = http.get(
    baseUrl + '/api/catalog?limit=20',
    {
      headers,
      tags: { journey: 'catalog-read' },
      timeout: '10s'
    }
  );

  check(response, {
    'catalog status 200': (r) => r.status === 200,
    'response is nonempty': (r) => r.body !== null && r.body.length > 0
  });
}
~~~

**Cách hiểu script:**

- `ramping-arrival-rate` điều chỉnh tốc độ đến, không trực tiếp là số user.
- `preAllocatedVUs`/`maxVUs` quyết định khả năng bộ sinh tải cấp đủ VU để đạt rate, không thay đổi quota của ứng dụng Azure.
- `thresholds` là điều kiện đánh giá của bài thử, không phải giới hạn bảo vệ môi trường production.
- `TEST_TOKEN` là credential thử nghiệm do người học quản lý an toàn; không được đưa token vào command history/log nếu chính sách yêu cầu phương thức an toàn khác.
- Check response theo `200` chỉ hợp lệ nếu endpoint thật định nghĩa 200 là thành công; phần nghiệp vụ đặt đơn cần thêm idempotency/correctness check.

Lệnh chạy minh họa trên máy đã cài k6:

~~~bash
# Chỉ tới URL của môi trường staging được phép thử.
BASE_URL="https://staging-orders.example.com" \
TEST_RUN_ID="lab-2026-11" \
k6 run --summary-export catalog-summary.json catalog-load.js
~~~

Tên miền là **ví dụ**, không phải một đích cần gọi thật. Trước khi chạy, xác nhận allowlist IP nguồn, xác thực, quota, rate cap, bộ sinh tải đủ capacity, và không có tác động đến dependency production.

### 10.2. Thử tải bằng Azure Load Testing

Nếu tổ chức dùng dịch vụ **Azure Load Testing**, quy trình khái quát:

1. Tạo/kiểm tra Azure Load Testing resource trong subscription test và quyền thao tác.
2. Chọn loại test được giao diện hỗ trợ, ví dụ **URL-based test** cho một endpoint hoặc **Apache JMeter test** nếu muốn mô tả hành trình phức tạp.
3. Cấu hình target là staging, số engine/tải tăng theo bước, request headers và secrets qua cơ chế được hỗ trợ.
4. Cấu hình **test failure criteria** dựa trên error rate/response time, cùng Azure resource metrics được dịch vụ hỗ trợ.
5. Kiểm tra **network access** từ test engine tới private endpoint hoặc staging VNet nếu dùng, không mặc định tài nguyên private sẽ được công cụ truy cập.
6. Chạy baseline nhỏ, xác minh test engine không tự nghẽn, rồi tăng tải trong khung phê duyệt.
7. Xuất/lưu kết quả, đối chiếu với Azure Monitor/Application Insights và Cost Management.

Không nhập `catalog-load.js` vào luồng JMeter khi chưa có công cụ hỗ trợ/biến đổi đúng định dạng. Người học có thể chọn **k6 hoặc Azure Load Testing** dựa trên yêu cầu; cần dùng một bộ metric chuẩn để so kết quả.

### 10.3. Kiểm tra bộ sinh tải

Trước khi kết luận server quá chậm, kiểm tra:

- RPS đạt được so target; số request bị dropped/skipped do thiếu VUs hoặc lỗi load generator.
- CPU/memory/network của generator và khả năng phát traffic từ vị trí địa lý dự kiến.
- DNS, TLS handshake, connection reuse, timeout của client.
- Mẫu dữ liệu và cơ chế xác thực có làm nghẽn một service khác ngoài workload đang đo không?
- Kết quả p95 từ tool so với App Insights: có cùng cửa sổ thời gian, loại request và sampling không?

Load test thiếu khả năng phát đủ request có thể làm hệ thống **trông khỏe giả**.

## 11. Tiến hành bài thử tải theo từng giai đoạn

Một phiên test tham khảo:

| Giai đoạn | Thời gian minh họa | Target | Kiểm tra cần làm |
| --- | --- | --- | --- |
| Warm-up | 3 phút | 5–10 RPS | Đảm bảo instrumentation, dependency và cache sẵn sàng |
| Baseline | 5 phút | 20 RPS | Ghi p50/p95/p99, error rate, CPU, DB/queue |
| Ramp | 3 phút | 20 → 60 RPS | Theo dõi saturation, scale events |
| Sustained peak | 10 phút | 60 RPS | Kiểm tra đáp ứng SLO, 429 và queue age |
| Controlled stress (tùy chọn) | 3–5 phút | Tăng theo giới hạn duyệt | Nhận diện điểm gãy và load shedding |
| Cool-down | 5 phút | 20 RPS rồi dừng | Quan sát hồi phục, backlog và tài nguyên còn tăng |

Đây là **lịch gợi ý**, không bắt buộc trùng chính xác script ở mục 10. Khi sử dụng script ví dụ, đọc các stages và ghi chính xác tải thực đã chạy. Nếu hệ thống chưa từng phục vụ 60 RPS, tăng từ thấp hơn theo quyền phê duyệt.

### 11.1. Các phép đo phải lưu

1. Target RPS và achieved RPS theo phút; số request thật, duration và status code.
2. SLI của đúng hành trình và p95/p99 latency, không chỉ average.
3. CPU/memory/GC, network, connection pools, DB resource utilization, query latency.
4. Queue depth và oldest-message-age; kiểm tra worker có tiêu thụ đúng.
5. Throttling (HTTP 429 hoặc error code quota của từng dịch vụ) và retry count.
6. Autoscale events, quota/instance allocation, thời gian scale-out và cold-start khi có.
7. Kết quả synthetic business ledger: bao nhiêu đơn đã ack, được xử lý, lỗi hoặc trùng.
8. Chi phí phát sinh và log ingest trong khoảng thử; xác định resource tạm sau khi kết thúc.

### 11.2. Đưa ra kết luận đúng bằng dữ liệu

Ví dụ kết quả giả định:

| Tải đạt được | API p95 | Lỗi 5xx | DB p95 | Queue age | Diễn giải sơ bộ |
| --- | ---: | ---: | ---: | ---: | --- |
| 20 RPS | 180 ms | 0,1% | 45 ms | 4 s | Trong mục tiêu |
| 40 RPS | 280 ms | 0,2% | 85 ms | 6 s | Còn dư tải |
| 60 RPS | 490 ms | 0,8% | 180 ms | 23 s | Gần giới hạn SLO |
| 70 RPS | 920 ms | 3,5% | 390 ms | 85 s | Vượt nhiều ngưỡng |

Các số là **ví dụ học tập**, không phải benchmark Azure. Giả thuyết đầu tiên có thể là database/queue bão hòa, nhưng cần kiểm tra query, connection pool, RU/DTU/vCore/IOPS theo dịch vụ, telemetry từng tầng và retry trước khi kết luận.

Một biểu đồ tăng latency cùng traffic chưa tự chứng minh autoscale thất bại. Có thể capacity bị chặn bởi database hoặc do một deployment làm phát sinh N+1 query.

## 12. Cách chẩn đoán nghẽn theo CPU, memory, disk, network và dependency

| Triệu chứng | Khả năng thường gặp | Bằng chứng phân biệt | Hướng xử lý cần cân nhắc |
| --- | --- | --- | --- |
| CPU application cao, p95 tăng | Code CPU-bound, serialization, GC hoặc instance quá ít | CPU per instance, profiler, GC time, request mix | Tối ưu CPU, scale phù hợp, cân nhắc cache |
| Memory tăng liên tục ở soak | Memory leak, cache không giới hạn, heap pressure | Heap/GC, RSS, OOM/restarts, time series | Leak investigation, memory limits và cache policy |
| Disk latency tăng, worker chậm | Disk/IOPS giới hạn, storage throttling | Disk latency/queue, service metrics, IO profile | Batch IO, SKU/throughput, indexing, caching |
| Network RTT và timeouts tăng | Route, DNS, TLS, egress, SNAT exhaustion | Connection errors, RTT, DNS resolution, network metrics | Kiểm tra đường đi, pool reuse và scale outbound |
| HTTP 429 | Quota/throttling của gateway hoặc downstream | Error/substatus, headers, service metrics, retries | Backoff/jitter, giảm burst, điều chỉnh quota khi phù hợp |
| DB dependency p95 tăng mạnh | Query/index, lock, pool, CPU/IO, connections | Query diagnostics, DB metrics, app dependencies | Tối ưu query/index, transaction, pool hoặc capacity |
| Queue age tăng khi API vẫn 200 | Consumer chậm, lỗi worker, downstream không khỏe | Backlog, dead-letter, worker errors | Scale worker an toàn, sửa consumer, chống duplicate |
| Tất cả instance cùng lỗi sau deploy | Config, identity, secret hoặc schema | Deploy history, Activity Log, exceptions | Rollback có điều kiện, kiểm tra tương thích dữ liệu |
| Chỉ một region/zone lỗi | Route/ingress/zone dependency | Origin probes, health, network, telemetry per region | Failover theo runbook và kiểm tra n−1 capacity |

**Cần xác định nghẽn thật trước khi tăng SKU.** Mua VM lớn hơn có thể làm hóa đơn tăng mà không cải thiện một câu SQL không có index. Ngược lại, quá tối ưu chi phí làm thiếu headroom khi mất một zone có thể phá Reliability.

### 12.1. Retry và load shedding

Khi backend quá tải, một request lỗi khiến client retry ngay có thể nhân số request đến, làm hệ thống tệ hơn. Thiết kế:

- Timeout và retry budget hữu hạn.
- Exponential backoff, jitter và tôn trọng các hướng dẫn retry-after nếu dịch vụ cung cấp.
- Idempotency keys cho thao tác ghi; không tạo đơn/thanh toán trùng.
- Circuit breaker hoặc bulkhead để giảm lan truyền lỗi dependency.
- Trả trạng thái suy giảm rõ ràng khi không thể phục vụ, thay vì giữ kết nối vô hạn.

Thử lại các cơ chế này trong môi trường test; không đánh dấu “đã chịu tải” nếu thành công nhờ bỏ qua giao dịch mà không có thông báo đúng cho người dùng.

## 13. Diễn tập khôi phục: phân biệt các cấp lỗi

“DR drill” không chỉ là nhấn nút failover. Phải chọn **failure domain** và minh chứng tương ứng.

| Loại lỗi | Ví dụ injection an toàn | Điều muốn chứng minh |
| --- | --- | --- |
| Process/instance | Đưa một backend test vào trạng thái unready | Health probe bỏ instance lỗi, instance còn lại đủ tải |
| Region/API | Vô hiệu hóa origin Region A trong tuyến thử | Ingress chuyển sang API Region B, SLI được khôi phục |
| Database/service | Restore bản backup vào DB test hoặc failover test được dịch vụ hỗ trợ | Dữ liệu và API dùng được sau khôi phục |
| Network/identity | Mô phỏng network deny hoặc identity test thiếu quyền ở staging | Phát hiện dependency, xử lý đúng mà không mở quyền rộng |
| Queue/worker | Tạm dừng consumer test một khoảng có giới hạn | Alert backlog, replay an toàn và không xử lý trùng |
| Toàn region | Tabletop hoặc DR exercise trên môi trường dự phòng | Runbook, dependency, route, data và RTO/RPO ở phạm vi tương ứng |

Không dùng một bài tắt API để khẳng định khả năng DR khi **toàn region hoặc database hỏng**. Mỗi kịch bản chỉ chứng minh đúng failure domain được diễn tập.

### 13.1. Chuẩn bị Runbook DR

Một runbook nên ghi:

~~~yaml
runbook_id: "RB-ORDERS-DR-LAB"
scenario: "staging-region-a-api-unavailable"
environment: "staging-isolated"
incident_commander: "<role>"
exercise_controller: "<role>"
application_owner: "<role>"
database_owner: "<role>"
trigger:
  - "Synthetic create-order failure vượt ngưỡng"
  - "Origin A unhealthy"
go_conditions:
  - "Origin B sẵn sàng nhận tải"
  - "Data plane và identity B đã xác minh"
  - "Không có production traffic ngoài scope"
stop_conditions:
  - "Dữ liệu đã xác nhận có nguy cơ mất"
  - "Injection ảnh hưởng dependency dùng chung"
  - "Thử tải vượt giới hạn được duyệt"
verification:
  - "API SLI trong cửa sổ phục hồi đạt mục tiêu"
  - "Đơn được tạo/đọc đúng, không trùng"
  - "Queue và worker khôi phục đúng"
  - "Metrics, traces và alert hoạt động"
cleanup:
  - "Hoàn nguyên origin test"
  - "Xác nhận health cả hai API"
  - "Đối soát tài nguyên và chi phí tạm"
~~~

Đây là **tài liệu bài tập**, không phải cấu hình tự động của Azure Chaos Studio, Front Door hoặc dịch vụ failover. Thay mọi placeholder, làm rõ quyền phê duyệt trước khi chạy.

### 13.2. Runbook cho lỗi origin ở Front Door

Trong một môi trường **staging có hai origin độc lập**:

1. Xác nhận origin A/B đều healthy, cùng version API và cùng quyền truy cập dữ liệu/secret.
2. Ghi baseline tại tải test được duyệt, bao gồm synthetic create/read-order.
3. Dùng cơ chế cấu hình hoặc fault injection **chỉ trên origin test** khiến API A không healthy; ghi `T_impact`.
4. Xác minh Health Probe đã phát hiện lỗi; ghi `T_detected`.
5. Quan sát request chuyển sang B theo chính sách route; đánh giá lỗi transient và connection draining.
6. Chạy synthetic end-to-end, xác minh đơn và queue; ghi `T_recovered` khi đạt SLO trong cửa sổ yêu cầu.
7. Hoàn nguyên origin A, chỉ đưa vào phục vụ khi đủ healthy; kiểm tra traffic và telemetry.
8. Lưu thay đổi, timestamps, log và kết quả vào báo cáo.

**Thời gian chuyển origin không chỉ phụ thuộc TTL DNS** nếu sử dụng Front Door/traffic management; health probe intervals, threshold, route policy, connection state và client retries đều tác động. Không hứa thời gian failover cố định khi chưa đo.

### 13.3. N−1 capacity khi một vùng/instance mất

Giả sử workload đỉnh cần **600 requests/giây**, trải đều trên hai vùng có thể xử lý tối đa **400 RPS mỗi vùng**.

~~~text
Capacity khỏe ban đầu = 400 + 400 = 800 RPS
Demand ở peak         = 600 RPS

Sau khi mất một vùng:
Remaining capacity    = 400 RPS
Deficit               = 600 − 400 = 200 RPS
~~~

Kiến trúc có hai vùng nhưng **không đủ N−1 capacity** để giữ SLO tại peak. Phải cân nhắc mỗi vùng có khả năng đạt mục tiêu khi vùng kia mất, có cơ chế scale-out kịp thời và database/queue/ingress đủ capacity. Các con số chỉ mô tả **giới hạn đo được**, không phải công suất Azure mặc định.

## 14. Diễn tập khôi phục dữ liệu: backup, restore và tính đúng đắn

**Có backup không đồng nghĩa restore được trong RTO.** Bài test dữ liệu nên tách khỏi fault injection vào API để đo đúng phương án phục hồi dữ liệu.

### 14.1. Mô hình bài thử trên Azure SQL hoặc dịch vụ có backup tương ứng

Ví dụ với **Azure SQL Database** khi tính năng restore được hỗ trợ:

1. Xác nhận dữ liệu synthetic và **thời điểm recovery point** khả dụng theo retention/chính sách thực tế.
2. Tạo một tập đơn có ID duy nhất; lưu ACK ledger độc lập với database mục tiêu.
3. Thực hiện restore theo quy trình dịch vụ vào **database thử nghiệm mới**, không ghi đè production.
4. Kiểm tra schema, tables, permissions, kết nối API thử, số lượng item và checksum/transaction IDs.
5. Ghi thời gian bắt đầu restore, thời gian database có thể phục vụ truy vấn, thời gian khôi phục hành trình đặt đơn end-to-end.
6. Đối soát các đơn đã xác nhận trước thời điểm sự cố với những gì có trong database phục hồi.
7. Kiểm tra private networking, firewall, RBAC/Entra auth, keys và monitoring cho database được khôi phục.
8. Cleanup resource test theo quy trình sau khi báo cáo; giữ lại bằng chứng không chứa dữ liệu nhạy cảm.

Với Azure Backup/ASR hoặc database engine khác, phương pháp và thao tác khôi phục khác nhau. Không tự áp lệnh failover/restore của Azure SQL vào mọi dịch vụ Azure.

### 14.2. Phép đo RPO đúng cách

Ví dụ có các mốc giả định:

~~~text
T_impact                  = 10:00:00 UTC
Last acknowledged write   = 09:59:50 UTC
Last recoverable write    = 09:57:30 UTC

Estimated recovery-point gap
  = 09:59:50 − 09:57:30
  = 2 phút 20 giây
~~~

Khoảng **2 phút 20 giây** là phép đo dựa trên timestamp của ví dụ, chưa đủ chứng minh mọi transaction đã được khôi phục. Phải kiểm tra danh sách `orderId`, phiên bản, trạng thái commit, checksum và duplicate. Đồng hồ có thể lệch và replication/ingestion có thể bất đồng bộ.

Mẫu đối soát:

| Order ID synthetic | Đã ACK trước sự cố? | Có trong DB phục hồi? | Kết luận |
| --- | --- | --- | --- |
| `lab-001` | Có | Có, checksum đúng | Đạt |
| `lab-002` | Có | Không | **Mất dữ liệu đã xác nhận – không đạt** |
| `lab-003` | Chưa | Không | Cần retry/cancel theo nghiệp vụ |
| `lab-004` | Có | Có hai bản logic | **Trùng – không đạt** |

Nếu có một đơn đã xác nhận bị mất, phải **đánh dấu thất bại về data integrity** dù độ cũ recovery point còn trong giới hạn RPO chung. Với giao dịch thanh toán, cần đối soát qua ledger/hệ thống nguồn đáng tin thay vì tự retry charge.

### 14.3. Failover và failback dữ liệu

Nếu ứng dụng dùng geo-replication/failover group hay bản DR có thể nhận ghi:

- Xác nhận **single authoritative writer** và tránh split-brain.
- Hiểu nguy cơ mất dữ liệu của replication bất đồng bộ trước forced failover.
- Kiểm tra DNS/listener/connection pool và SDK reconnect sau khi đổi vai trò.
- Khi failback, **tái đồng bộ dữ liệu được ghi trong lúc DR phục vụ**, phân định nguồn đúng và đưa traffic trở lại có kiểm soát.
- Ghi riêng phép đo RTO, data correctness và thời gian failback; không coi “failover succeeded” của control plane là hệ thống đã phục hồi.

## 15. Đo timeline khôi phục một cách nhất quán

Cần có người chuyên ghi timeline, sử dụng **UTC và bằng chứng từ nhiều nguồn**.

| Mốc | Ví dụ giả định | Ý nghĩa |
| --- | --- | --- |
| `T_impact` | 10:00:00 | Người dùng không hoàn thành được giao dịch chính |
| `T_detected` | 10:02:15 | Alert hoặc ca trực phát hiện |
| `T_declared` | 10:04:00 | Incident Commander xác nhận và phân vai |
| `T_mitigated` | 10:11:00 | Chuyển lưu lượng/giảm ảnh hưởng phần lớn |
| `T_recovered` | 10:14:30 | Giao dịch đạt SLI/SLO trong cửa sổ được quy định |
| `T_closed` | 11:05:00 | Hoàn tất xác minh, cleanup và cập nhật thông tin |

~~~text
Detection time = 10:02:15 − 10:00:00 = 2 phút 15 giây
Observed RTO   = 10:14:30 − 10:00:00 = 14 phút 30 giây
~~~

Theo mục tiêu giả định ở mục 3, thời gian phát hiện và RTO đều đạt. **Điều này không nói gì về RPO hoặc tính toàn vẹn dữ liệu**: hai tiêu chí đó phải có phép đối soát riêng.

### 15.1. Điều kiện “đã phục hồi”

Hệ thống được xem là phục hồi khi:

- Synthetic **create + read order** đạt ngưỡng trong cửa sổ quan sát.
- Tỷ lệ lỗi và p95 latency của các hành trình quan trọng đã trở lại giới hạn.
- Queue worker không còn backlog tăng không kiểm soát, không tạo đơn trùng.
- Database read/write và authorization đúng từ vùng đang phục vụ.
- Rủi ro dữ liệu đã được kiểm tra, hoặc trạng thái chưa biết được ghi rõ và chưa tuyên bố toàn hệ thống đạt.
- Monitoring/alert hoạt động tại môi trường phục hồi, không chỉ ở primary.

Không chọn `T_recovered` bằng thời điểm API/VM báo Running hoặc khi người trực click nút failover.

## 16. Kịch bản tích hợp: chạy tải trong khi mất một origin

Bài tổng hợp kết hợp cả ba kỹ năng, nhưng phải giữ **phạm vi staging** để tránh ảnh hưởng ngoài ý muốn.

### 16.1. Kế hoạch theo từng pha

~~~mermaid
flowchart LR
    A["Baseline telemetry & synthetic ledger"] --> B["Load test trong giới hạn"]
    B --> C["Record healthy-region metrics"]
    C --> D["Inject origin A failure"]
    D --> E["Alert & failover observe"]
    E --> F["Verify API, data, queue"]
    F --> G["Restore origin & observe"]
    G --> H["Review RTO/RPO, SLO, cost"]
    H --> I["Runbook updates & retest"]
~~~

Thứ tự đề xuất:

1. Tạo test run ID và **dữ liệu synthetic**; ghi số lượng/order IDs đã ACK độc lập.
2. Chạy baseline ở một mức traffic mà cả hệ thống đạt SLO.
3. Tăng đến **mức tải đại diện được duyệt**, không mặc định chạy peak ngay khi chưa biết năng lực N−1.
4. Khi origin A còn healthy, thu p95, CPU, dependency errors, worker lag và phân bố ingress.
5. Chỉ Exercise Controller kích hoạt lỗi trên origin A thuộc môi trường test.
6. Quan sát alert, route sang B và time-to-recovery; nếu vượt stop condition, dừng injection/load và khôi phục an toàn.
7. Tiếp tục một cửa sổ quan sát ngắn để xác nhận API B còn xử lý đúng.
8. Hoàn nguyên origin A, kiểm tra traffic/health và dọn dữ liệu/tài nguyên test.
9. Tách kết quả **API failover** khỏi kết quả **database restore**; chỉ kết luận DR data khi có test và evidence tương ứng.

### 16.2. Bảng kết quả mẫu

| Phép kiểm tra | Mục tiêu | Quan sát minh họa | Đánh giá |
| --- | --- | --- | --- |
| Alert detection | ≤ 3 phút | 2 phút 15 giây | Đạt |
| API recovery | RTO ≤ 30 phút | 14 phút 30 giây | Đạt |
| Peak API error rate | < 1% | 0,7% | Đạt |
| p95 create-order | < 500 ms | 620 ms lúc lỗi | **Không đạt** |
| Queue age | < 30 giây | 75 giây trong 4 phút | **Không đạt** |
| Data integrity | Không mất/trùng đơn đã ACK | 1 đơn không có sau restore test | **Không đạt** |
| Cleanup | Không còn tài nguyên test ngoài phạm vi | Đã xử lý đầy đủ | Đạt |

Dù recovery time đạt, **bài tổng hợp vẫn không thể ghi PASS toàn bộ** nếu latency, queue và dữ liệu vi phạm tiêu chí đã thống nhất. Báo cáo phải thể hiện kết quả theo từng mục và trạng thái tổng hợp `PARTIAL/FAILED` cho tới khi khắc phục hoặc có risk acceptance theo quy trình.

### 16.3. Diễn giải không nhầm lẫn giữa nguyên nhân và tương quan

Nếu p95 tăng mạnh sau khi tắt origin A, có thể do capacity B không đủ, database connection pool bị giới hạn, ứng dụng mới scale chưa kịp, hoặc các client retry khiến traffic thực tăng. Cần so:

- Request counts trước/sau ở A/B.
- App instances, autoscale events, CPU/GC, DB dependency latency.
- Retry counts, queue age, timing của origin health.
- Cùng loại giao dịch và cùng tải đạt được, không chỉ target RPS.

Nêu **giả thuyết và phép kiểm tra**, không tự kết luận từ một đường biểu đồ.

## 17. Runbook xử lý sự cố và phối hợp hỗ trợ Azure

Một runbook thực tiễn có trigger, scope, người phụ trách và nhánh quyết định:

| Bước | Thao tác | Bằng chứng | Điều kiện chuyển |
| --- | --- | --- | --- |
| 1. Validate | Xác minh alert, SLI, scope, giờ UTC | Dashboard/synthetic | Có tác động thực thì mở incident |
| 2. Classify | API, database, queue, network, identity hay Azure platform? | Traces, metrics, Health, Activity Log | Chọn owner và hướng điều tra |
| 3. Mitigate | Giảm load, route sang origin khỏe, rollback theo duyệt | Operation ID, change record | Không gây rủi ro dữ liệu ngoài phạm vi |
| 4. Verify | Synthetic create/read, data ledger, queue, p95 | Test + log/traces | Đạt SLO trong cửa sổ định nghĩa |
| 5. Escalate | Tăng hỗ trợ nội bộ/đến Microsoft khi cần | Resource ID, UTC, error code, correlation ID | Có người quản lý ticket |
| 6. Recover | Hoàn nguyên môi trường test hoặc failback theo runbook | Healthy state, replication/backup | Không có dependency chưa được kiểm tra |
| 7. Review | Timeline, nguyên nhân, action items và retest | PIR report | Gắn owner + acceptance test |

**Azure Support request** không thay thế người điều phối incident. Nếu phát hiện khả năng lỗi nền tảng Azure hoặc hành vi dịch vụ không giải thích được, chuẩn bị:

- Subscription/resource group/region và **ARM resource ID** chính xác.
- UTC interval, business impact, error codes và request/correlation IDs thực tế.
- Kết quả Azure Service Health, Resource Health, Azure Monitor, Activity Log, steps và workaround đã thử.
- Các log/screenshot đã **redact token, password, SAS, connection string và PII**.
- Câu hỏi cụ thể cần Microsoft hỗ trợ, owner nhận phản hồi và tình trạng recovery hiện tại.

Mức severity/kênh hỗ trợ phụ thuộc gói support và business impact thật. Không mở ticket cấp khẩn cấp chỉ để lấy nhận xét cho một bài lab không ảnh hưởng production.

## 18. Đánh giá sau sự cố và chuyển kết quả thành cải tiến

**Post-incident review (PIR)** cần được thực hiện kể cả khi chỉ là game day: bài thử thất bại là nguồn thông tin có giá trị nếu có log và hành động sửa cụ thể.

### 18.1. Mẫu báo cáo sau bài thử

~~~markdown
# Orders Monitoring / Load / DR Exercise — <exercise-id>

## Scope
- Subscription, resource group, regions, owner:
- Đối tượng test và stop conditions:
- Kiến trúc, phiên bản ứng dụng và dữ liệu synthetic:

## Mục tiêu và kết quả
| SLI/SLO/RTO/RPO | Target | Observed | Pass/Fail |
| --- | --- | --- | --- |
| ... | ... | ... | ... |

## Timeline UTC
| UTC | Event | Evidence | Owner |
| --- | --- | --- | --- |
| ... | ... | ... | ... |

## Load test
- Tool và cấu hình RPS/VUs, thời gian:
- Achieved throughput, p95/p99, error rates:
- Saturation, dependencies, retries, queue:
- Bottleneck hypotheses và kiểm tra:

## Resilience / DR
- Failure domain và cách injection:
- Traffic routing/recovery:
- RTO thực đo:
- Recovery point/đối soát transaction IDs:
- Các tiêu chí chưa được kiểm chứng:

## An toàn, bảo mật và chi phí
- Secrets/PII đã được bảo vệ:
- Chi phí và resource cleanup:
- Ảnh hưởng ngoài scope nếu có:

## Findings và hành động
| ID | Finding | Owner | Deadline | Acceptance test |
| --- | --- | --- | --- | --- |
| ... | ... | ... | ... | ... |
~~~

### 18.2. Ví dụ action items có thể kiểm chứng

| Finding | Hành động | Điều kiện đóng |
| --- | --- | --- |
| p95 vượt 500 ms sau failover | Tăng năng lực N−1 và kiểm tra DB connection pool/worker | Chạy lại test mất origin tại tải đại diện, p95 đạt SLO |
| Queue backlog lên 75 giây | Giới hạn retry, cải thiện worker scale và dead-letter monitoring | Worker hoàn tất backlog trong thời gian mục tiêu |
| Alert chỉ tới email không có on-call | Chỉnh Action Group/on-call route, thêm escalation | Test nhận alert và acknowledgement trong giới hạn |
| Restore DB có đơn thiếu | Điều tra recovery point, data reconciliation và replay/idempotency | Drill tiếp theo có dữ liệu đã xác nhận đầy đủ theo yêu cầu |
| Không phân biệt request synthetic | Thêm test run tag/trace field | Truy vấn lọc được dữ liệu test và business traffic |
| Chi phí logs tăng quá dự báo | Giảm debug noise, đặt retention và sampling có kiểm soát | Cost ingest giảm, security/incident telemetry vẫn đủ |

Chỉ đánh dấu action `Done` khi phép thử hoặc bằng chứng đã xác minh thay đổi **làm hành vi tốt hơn**. Merge PR hoặc tăng quota mà chưa chạy lại bài kiểm tra không chứng minh finding đã được khắc phục.

## 19. Ngân sách, quản trị và cleanup sau lab

Thử tải, bật telemetry và chạy nhiều region đều có chi phí. Các khoản cần dự báo gồm:

- Compute API, worker, autoscale instances và thời gian duy trì môi trường DR.
- Database throughput/IO, backups/restores, replicas và storage tạm.
- Azure Front Door/ingress, data transfer và các thành phần networking.
- Azure Load Testing nếu sử dụng, số engine/chạy test theo mô hình giá đang áp dụng.
- Log Analytics ingestion, retention, Application Insights và dashboard.
- Traffic synthetic tạo dữ liệu (orders, blobs, queue messages), cleanup/retention.

**Không có giá cố định trong bài**; xem Azure Cost Management/Pricing Calculator theo region, SKU, subscription và thỏa thuận để lập ngân sách. Dùng budget alerts làm cảnh báo, không coi đây là cơ chế giới hạn chi phí cứng.

### 19.1. Checklist cleanup

1. Dừng load generator và vô hiệu hóa fault injection; xác nhận không còn traffic thử ngoài kế hoạch.
2. Hoàn nguyên Front Door origin/route và trạng thái API ở staging; kiểm tra không ảnh hưởng production.
3. Xác minh backup/replication của các tài nguyên bị động đến đã về trạng thái khỏe.
4. Xóa dữ liệu synthetic theo `exercise_id` khi an toàn, giữ lại bằng chứng đã làm sạch dữ liệu nhạy cảm.
5. Xóa tài nguyên **chỉ trong scope lab thuộc quyền sở hữu**, tránh xóa resource group dùng chung.
6. Kiểm tra worker, queue, disk, public IP, database restore và test resources còn phát sinh phí.
7. Xác minh alert, logs và dashboard cần giữ lại cho lần diễn tập tiếp theo; điều chỉnh logging level sau bài thử.
8. Ghi chi phí thực đo khi dữ liệu Cost Management cập nhật và owner xác nhận kết thúc.

## 20. Câu hỏi kiểm tra hiểu biết và ngộ nhận thường gặp

**1. Nếu p95 API vẫn trong 500 ms nhưng tạo đơn bị duplicate, bài thử đạt không?** Không. Latency HTTP chỉ là một chỉ số; cần kiểm tra **business correctness**. Giao dịch trùng có thể vi phạm tiêu chí nghiêm trọng.

**2. Nếu Action Group test gửi email thành công, alert đã được kiểm thử end-to-end chưa?** Chưa. Nó xác minh kênh gửi; cần kiểm tra signal, điều kiện, evaluation window và dữ liệu thật của staging.

**3. Tại sao tăng CPU hoặc RU/s chưa chắc giải quyết mọi nghẽn?** Bottleneck có thể là query/index, pool, network, lock, hot partition hoặc downstream; phải đọc telemetry và phép thử phân biệt.

**4. Có API ở hai region thì có thể tuyên bố hệ thống DR hoàn chỉnh?** Không. Database, identity, network, queue và storage có thể còn phụ thuộc một region duy nhất.

**5. RTO dưới 30 phút có đồng nghĩa dữ liệu đạt RPO không?** Không. RTO là thời gian phục hồi dịch vụ; RPO và data integrity phải kiểm chứng bằng điểm dữ liệu và transaction IDs.

**6. Nếu thử failover tạo ra 30 giây lỗi, có cần ghi báo cáo không?** Có. Ghi timeline, loại request, tác động, mức chấp nhận và biện pháp giảm thiểu. Không chỉ ghi “chuyển vùng thành công”.

**7. Có nên chạy stress test trên production để tìm công suất tối đa?** Không tự ý. Cần phạm vi, chấp thuận, guardrail, giới hạn và điều kiện dừng; môi trường staging đại diện thường an toàn hơn.

**8. Có backup thành công mỗi ngày nghĩa là dữ liệu chắc chắn khôi phục được?** Không. Phải diễn tập restore, kiểm tra quyền, cấu hình và đối soát dữ liệu sau khôi phục.

**9. Vì sao phải lưu achieved RPS và tải của load generator?** Nếu công cụ không phát đủ tải, “server không lỗi” chưa chứng minh capacity. Cần tách giới hạn generator và hệ thống.

**10. Khi chạy game day, có được chỉ đo status code 200 không?** Không. Phải kiểm tra end-to-end transaction, queue, dữ liệu, identity, chi phí và sự phục hồi của các chỉ số liên quan.

## 21. Bài capstone và tiêu chí chấm đạt

### Nhiệm vụ A — Thiết lập giám sát

Dựa trên sơ đồ mục 2, định nghĩa ít nhất **bốn SLI** cho API, database/queue và người dùng. Tạo dashboard/queries cho request rate, p95 latency, dependency errors và queue backlog. Gắn owner, phạm vi, đường dẫn runbook cho alert. Ghi rõ giới hạn khi chưa có telemetry.

### Nhiệm vụ B — Thử tải

Thiết kế thử nghiệm gồm **baseline, ramp, sustained peak và cool-down**; mô tả tool, tải, mix request, generated data và stop conditions. Dùng k6 hoặc luồng Azure Load Testing hỗ trợ. Thu target/achieved RPS, p95/p99, 429, lỗi, dependency saturation và chi phí.

### Nhiệm vụ C — Diễn tập giảm năng lực

Trong **staging**, loại origin API A khỏi đường phục vụ theo phương án có phê duyệt. Đo `T_impact`, `T_detected`, `T_recovered`, các request lỗi và sức chịu tải của API B. Lập bảng **N−1 capacity** theo tải thiết kế.

### Nhiệm vụ D — Khôi phục dữ liệu

Chạy restore test vào tài nguyên cô lập hoặc trình bày tabletop nếu chưa có quyền. Đối soát các ID đã ACK với dữ liệu có thể đọc ở DB phục hồi, ghi giới hạn đo RPO. Không dùng điểm backup “Success” làm bằng chứng đã khôi phục được ứng dụng.

### Nhiệm vụ E — Hậu kiểm và cải tiến

Viết báo cáo theo mẫu mục 18 với ít nhất **ba findings**, owner, thời hạn và acceptance tests. Phân biệt mục tiêu đạt, không đạt và chưa kiểm chứng; đề xuất bài test lại sau khắc phục.

### Rubric nghiệm thu

| Hạng mục | Đạt khi |
| --- | --- |
| **SLO/SLI** | Định nghĩa theo giao dịch nghiệp vụ và cửa sổ đo nhất quán |
| **Monitoring** | Có metrics, logs, traces và synthetic tests, alert có owner |
| **Load model** | Có target/achieved RPS, request mix và phạm vi an toàn |
| **Performance** | Có p95/p99 và bằng chứng bottleneck, không suy từ CPU đơn lẻ |
| **Resilience** | Phân biệt instance/region/API/database failure domain |
| **RTO/RPO** | Có timestamp và data ledger, đối soát mất/trùng riêng |
| **Security** | Test cô lập, quyền tối thiểu, không lộ secret/PII |
| **Cost** | Có budget, tài nguyên tạm và cleanup được kiểm tra |
| **Decision** | Có runbook, tiêu chí stop/rollback và người phê duyệt |
| **Learning** | Có PIR, action items và phép thử xác minh lại |

## 22. Tổng kết

Giám sát, thử tải và diễn tập khôi phục là **một vòng kiểm chứng liên tục**, không phải ba công việc rời rạc:

~~~text
Mục tiêu nghiệp vụ
  → SLI/SLO và RTO/RPO
  → Instrumentation + alert
  → Baseline và load test
  → Phân tích saturation và dependency
  → Fault injection / restore test có kiểm soát
  → Đo recovery time và đối soát data integrity
  → Post-incident review
  → Cải tiến kiến trúc, runbook và thử lại
~~~

Điều quan trọng nhất là **bằng chứng về trải nghiệm người dùng và dữ liệu**: API đạt HTTP 200, resource ở trạng thái Running hoặc backup có Success chưa đủ để tuyên bố hệ thống khỏe hay đã khôi phục. Một workload Azure đáng tin cậy phải có đo lường phù hợp, biết giới hạn hiệu năng, đủ năng lực khi thành phần lỗi, phục hồi dữ liệu đúng, có cơ chế điều phối con người và hoạt động trong phạm vi chi phí/bảo mật được phép.
