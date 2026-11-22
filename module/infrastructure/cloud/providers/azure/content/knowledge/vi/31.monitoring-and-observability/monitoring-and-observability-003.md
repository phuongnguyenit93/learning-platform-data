# Log Analytics Workspace và thiết kế lưu giữ log

## 1. Vấn đề thực tế: lưu log bao lâu, ở đâu, để làm gì?

Một ứng dụng Java/Spring Boot chạy trên Azure App Service và AKS phát sinh hàng triệu bản ghi mỗi ngày: HTTP access log, application errors, container stdout, audit events, thông báo thay đổi tài nguyên và sự kiện bảo mật. Đội vận hành cần tìm nguyên nhân sự cố trong vài phút; đội bảo mật cần điều tra trong nhiều tháng; bộ phận kiểm toán có thể phải giữ một số bằng chứng lâu hơn nữa.

Nếu đẩy tất cả dữ liệu vào cùng một nơi và giữ mọi bảng vô hạn, chi phí lưu trữ, truy vấn, quyền truy cập và rủi ro lộ dữ liệu đều tăng. Nếu xóa quá sớm, hệ thống mất khả năng tìm nguyên nhân sự cố hoặc đáp ứng yêu cầu kiểm toán. **Log Analytics Workspace** là một thành phần trung tâm của **Azure Monitor Logs**, giúp tập trung dữ liệu log có cấu trúc, truy vấn bằng **Kusto Query Language (KQL)**, phân quyền, giám sát và đặt chính sách lưu giữ.

Bài thuộc chương **Giám sát và quan sát hệ thống**, trong module **CLOUD_PROVIDERS_AZURE**: từ subscription/resource group và Microsoft Entra ID đến networking, compute, storage, data, monitoring, security và cost management cho ứng dụng Azure.

**Bài toán xuyên suốt:** hệ thống đặt hàng gồm **orders-api** (Spring Boot trên AKS), **payment-worker** (Azure Container Apps), Azure SQL, Storage và Azure Key Vault. Ta thiết kế workspace, phân loại log, quy định thời hạn lưu, định tuyến nguồn, dùng KQL để điều tra và kiểm soát chi phí. Các số liệu, tên tài nguyên và thời hạn trong bài là **giả định minh họa**, không phải policy thực tế của một doanh nghiệp.

## 2. Mục tiêu học tập

Sau khi học, bạn có thể:

1. Giải thích vai trò của Azure Monitor, Log Analytics Workspace, tables và KQL.
2. Phân biệt logs, metrics, traces, audit/security events và archival evidence.
3. Chọn mô hình workspace tập trung hay phân tách theo môi trường, dữ liệu, vùng và quyền.
4. Thiết kế ingestion bằng Azure Monitor Agent (AMA), Data Collection Rules (DCR), diagnostic settings, Application Insights và Logs Ingestion API.
5. Hiểu workspace-level retention, table-level retention và sự khác biệt giữa **interactive/analytics retention** với **total/long-term retention**.
6. Phân loại table plans như **Analytics, Basic, Auxiliary** theo khả năng dịch vụ đang hỗ trợ và yêu cầu truy vấn.
7. Đề xuất ma trận lưu giữ log theo mục tiêu vận hành, pháp lý, bảo mật và ngân sách.
8. Tính toán lưu lượng ingest, GB/ngày, dung lượng giữ và những yếu tố tính phí.
9. Viết KQL tìm lỗi, thống kê p95 latency, lọc theo tài nguyên và ước lượng data volume.
10. Thiết kế quyền truy cập bằng Azure RBAC, resource-context/workspace-context và phạm vi truy vấn.
11. Quản lý secrets/PII, redaction, data minimization, data residency và xuất dữ liệu khi cần chứng cứ bất biến.
12. Thiết lập alert, monitoring của chính pipeline và runbook khắc phục mất log, ingest chậm, chi phí tăng.
13. Xây tài nguyên mẫu với Portal/CLI/IaC theo nguyên tắc chỉ thay đổi tài nguyên được phép.
14. Hoàn thành các lab về DCR/diagnostic settings, KQL, retention và kiểm soát chi phí.

## 3. Azure Monitor và Log Analytics Workspace nằm ở đâu?

~~~mermaid
flowchart LR
    AKS[AKS / Container Apps] --> AMA[Container Insights / AMA + DCR]
    VM[Azure VMs] --> DCR[AMA + Data Collection Rule]
    P[Azure SQL / Key Vault / Storage] --> DS[Diagnostic settings]
    JAVA[Java / Spring Boot] --> AI[Application Insights / OTel]
    CUSTOM[Custom application logs] --> ING[Logs Ingestion API + DCR]
    AMA --> LAW[(Log Analytics Workspace)]
    DCR --> LAW
    DS --> LAW
    AI --> LAW
    ING --> LAW
    LAW --> KQL[KQL queries]
    LAW --> ALERT[Azure Monitor alerts]
    LAW --> DASH[Workbooks / Dashboards]
    LAW --> RET[Table plans / Retention policy]
~~~

**Azure Monitor** là nền tảng quan sát Azure, có metrics, logs, alerts và các thành phần liên quan. **Log Analytics Workspace** là tài nguyên chứa các bảng log và là bối cảnh quản lý truy vấn, truy cập, chi phí và lưu giữ. **Log Analytics** cũng là trải nghiệm truy vấn KQL trong Azure Portal; đừng nhầm công cụ truy vấn với workspace resource.

### 3.1. Workspace không phải một thư mục log

Một workspace không chỉ lưu file văn bản. Dữ liệu được đưa vào **tables** với schema columns; truy vấn dựa trên tên bảng, thời gian, các trường và KQL. Một số trường thường gặp:

- **TimeGenerated**: timestamp sự kiện theo semantics của nguồn.
- **_ResourceId**: định danh Azure resource khi nguồn cung cấp.
- **_BilledSize**: kích thước bản ghi được tính trong một số phép đo ingest.
- **_IsBillable**: cho biết record có nằm trong nhóm billable theo semantics của bảng.
- Các cột riêng như **Message**, **SeverityLevel**, **OperationId**, **ResultCode**, **Computer**, **PodName**.

Không phải bảng nào cũng có tất cả các cột nói trên; phải xem schema thật trước khi viết query.

### 3.2. Metrics và logs không thay thế nhau

- **Metrics** phù hợp theo dõi số đo dạng chuỗi thời gian, tần suất cao và cảnh báo dựa trên tín hiệu tổng hợp.
- **Logs** phù hợp điều tra chi tiết, join/aggregate những sự kiện có context.
- **Distributed traces** nối các spans giữa services bằng trace/correlation IDs.
- **Audit logs** ghi hành động và danh tính/đối tượng liên quan với chính sách lưu giữ và bảo vệ riêng.

Không cần đưa toàn bộ metrics có sẵn vào logs chỉ để vẽ CPU chart; điều này có thể tăng ingestion và duplicate data.

## 4. Từ sự kiện đến bản ghi có thể truy vấn

Một sự kiện đi qua nhiều chặng:

~~~text
Ứng dụng tạo event
   |
Logger / OpenTelemetry instrumentation
   |
Collector / Agent / Azure service diagnostic export
   |
Filter / transformation / schema mapping (nếu hỗ trợ)
   |
Ingestion vào đúng workspace và table
   |
Interactive queries / alerts / workbooks
   |
Long-term retention / export / expiration
~~~

Mỗi chặng có thể mất dữ liệu, làm chậm hoặc làm thay đổi fields. Không được suy rằng ứng dụng đã in một dòng vào stdout thì chắc chắn dòng đó đã vào workspace.

### 4.1. Các thời điểm khác nhau

- **Event time:** khi sự kiện xảy ra.
- **Collection time:** khi agent/collector nhận dữ liệu.
- **Ingestion time:** khi workspace nhận được dữ liệu.
- **Query time:** khi người vận hành tìm kiếm.

Sự khác biệt rất quan trọng khi backlog hoặc thiết bị offline. KQL **TimeGenerated** thường đại diện thời gian event, còn **ingestion_time()** có thể giúp đo độ trễ nhập dữ liệu ở những bảng hỗ trợ.

### 4.2. Không sửa timestamp tùy tiện

Nếu logger ghi local time không kèm timezone, điều tra sự cố qua nhiều vùng có thể sai trình tự. Chuẩn hóa thời gian theo UTC, giữ offset khi cần và xác minh clock synchronization.

### 4.3. Event identity và duplicate

Collectors/retries có thể tạo duplicates trong một số trường hợp. Nếu audit event cần dedup hoặc kiểm chứng, ứng dụng nên phát **eventId/operationId** nhất quán; workspace không tự cung cấp exactly-once business semantics cho mọi nguồn.

## 5. Phân loại dữ liệu trước khi quyết định thời hạn

Một nguyên tắc quan trọng: **không thiết kế retention bằng một con số cho toàn bộ log**. Trước hết phân nhóm theo giá trị và rủi ro.

| Nhóm | Ví dụ | Đặc trưng |
|---|---|---|
| Application diagnostics | Exception, failed HTTP call, retry | Cần query nhanh trong giai đoạn xử lý sự cố |
| Performance & telemetry | Request duration, dependencies, counters | Nhiều records; có thể sampling/aggregate |
| Container/host logs | stdout/stderr, syslog, Windows events | Volume lớn; tín hiệu hữu ích không đồng đều |
| Azure platform diagnostics | Azure SQL, Key Vault, Storage | Phụ thuộc categories và resource settings |
| Control-plane activity | Tạo/xóa VM, thay policy, role assignments | Quan trọng cho audit/investigation |
| Security & access | Auth failure, policy denial, suspicious activity | Nhạy cảm, cần quyền riêng |
| Compliance evidence | Thay đổi quyền, truy cập dữ liệu trọng yếu | Có thể cần thời hạn dài và bảo đảm bất biến |
| Business events | OrderCreated/PaymentAuthorized | Không tự đồng nghĩa log kỹ thuật; phải giữ dữ liệu chuẩn ở hệ nghiệp vụ |

### 5.1. Log khác nguồn dữ liệu nghiệp vụ

Một thông báo "OrderCreated" trong log không thay bảng Orders/outbox. Log có thể bị lọc, sampling, hết retention hoặc đến trễ; không dùng Log Analytics Workspace làm hệ thống ghi sổ giao dịch chính.

### 5.2. Dữ liệu nhạy cảm

Không nên log password, API key, bearer token, SAS URL, connection string, full credit-card number hay dữ liệu cá nhân vượt mục đích. **Tốt nhất là không tạo log nhạy cảm từ đầu**, thay vì chỉ dựa vào masking downstream.

### 5.3. Quy định lưu giữ phải có owner

Chính sách nên xác định: loại dữ liệu, chủ sở hữu, mục đích, nơi lưu, ai được truy cập, thời hạn xử lý nhanh, tổng thời gian lưu, cách xóa và cơ chế giữ pháp lý (legal hold) nếu áp dụng.

## 6. Một workspace hay nhiều workspaces?

Không có một cách phân vùng workspace phù hợp mọi tổ chức. Các yếu tố quyết định:

1. **Data residency/region:** nơi dữ liệu phải nằm.
2. **Access boundaries:** nhóm nào cần xem những logs nào.
3. **Environment isolation:** dev/test/prod có nên chung không.
4. **Operational ownership:** cùng nhóm SRE hay nhiều đơn vị độc lập.
5. **Cost ownership:** chargeback theo subscription/team/workload.
6. **Query experience:** điều tra cần join logs của bao nhiêu resources.
7. **Retention/table plan:** các nhóm log cần chính sách khác nhau không.
8. **Compliance/security:** audit logs có bị giới hạn quyền hơn application diagnostics không.

### 6.1. Mô hình workspace tập trung

~~~text
Subscription A: App Service -----+
Subscription B: AKS ------------+--> central-ops-law
Subscription C: Azure SQL -------+
~~~

**Ưu điểm:** dễ cross-resource correlation, query và quản trị chung. **Nhược điểm:** quyền truy cập và chargeback phức tạp hơn; có thể xung đột về region/retention/security.

### 6.2. Mô hình tách theo môi trường hoặc trust boundary

~~~text
dev subscriptions  --> law-dev
prod app resources  --> law-prod-ops
prod security logs  --> law-prod-security (khi cần ranh giới riêng)
~~~

**Ưu điểm:** cô lập quyền và môi trường. **Nhược điểm:** truy vấn chéo và quản lý DCR, dashboards, IaC có thể phức tạp hơn.

### 6.3. Quy tắc thực hành

Không tạo một workspace cho mỗi Pod hay mỗi microservice chỉ vì có nhiều deployments; một workspace có thể chứa rất nhiều resource logs và dùng **_ResourceId**, table, service, environment fields để lọc. Nhưng nếu có yêu cầu tách dữ liệu theo khu vực pháp lý hoặc tổ chức, quyền truy cập quan trọng hơn sự tiện dụng của query chung.

### 6.4. Cross-workspace queries không miễn phí

Có thể truy vấn chéo nhiều workspaces/resources theo khả năng KQL, nhưng cần quyền ở từng scope, cân nhắc latency, limits, billing và bảo mật. Không lấy lợi ích cross-workspace query làm lý do bỏ qua data residency.

## 7. Các thành phần bên trong Workspace

Một workspace có:

- **Tables:** schema và dữ liệu; một số do Azure tạo theo nguồn, một số là custom.
- **Workspace settings:** default interactive retention, access control mode, replication hoặc tùy chọn khác khi được hỗ trợ.
- **Table-level settings:** plan/retention cho các bảng được phép.
- **Data collection rules và associations:** định tuyến/lọc một số luồng dữ liệu trước khi vào tables.
- **Access permissions:** Azure RBAC trên workspace, resources và khả năng truy vấn liên quan.
- **Query & alert layer:** KQL, alert rules, workbooks/dashboards.
- **Network controls:** cách nguồn và người dùng truy cập, có thể gồm Azure Monitor Private Link Scope.

### 7.1. Workspace-level và table-level retention

Workspace có **default retention** áp dụng theo hành vi của dịch vụ với các bảng không override. Với những bảng cho phép, có thể cấu hình retention riêng. **Không mặc định mọi table type cho phép cùng thời hạn hoặc cách đặt thông số.**

### 7.2. Bảng khác container

Workspace table là dữ liệu trong Azure Monitor Logs; không phải Azure Storage container hay Cosmos DB container. Đừng đưa Azure Storage lifecycle rules vào một table rồi kỳ vọng nó tự thay retention của Log Analytics.

### 7.3. Không phải mọi table đều user-configurable

Một số tables do Azure quản lý, có giới hạn table plan, retention hoặc schema settings. Trước khi dùng ARM/CLI đặt cấu hình, kiểm tra khả năng của table và service hiện hành.

## 8. Những bảng thường gặp khi giám sát Azure

| Bảng / nguồn có thể gặp | Ý nghĩa | Ghi chú |
|---|---|---|
| **AzureActivity** | Subscription control-plane events | Thu thập qua activity log export/diagnostic configuration phù hợp |
| **AzureDiagnostics** | Một số resource diagnostic logs | Legacy/resource-specific collection có thể sinh nhiều cột; tables dedicated khác nhau |
| **ContainerLogV2** | Container stdout/stderr qua collection tương ứng | Hữu ích cho AKS Container Insights khi cấu hình |
| **KubePodInventory** | Inventory Kubernetes Pod | Có thể có khi bật collection tương ứng |
| **Heartbeat** | Dữ liệu heartbeat máy/agent | Nguồn/phạm vi phụ thuộc cấu hình |
| **Perf** | Performance counters | Không có nếu chưa collect |
| **AppRequests** | Request telemetry trong workspace-based Application Insights | Không mặc định mọi app dùng bảng này |
| **AppDependencies** | Dependencies telemetry | Liên quan instrumentation và workspace-based mode |
| **AppTraces** | Application trace messages | Có thể bị sampling/filters |
| **CustomTable_CL** | Custom logs schema | Tên/schema do thiết kế và hỗ trợ của Logs Ingestion API |

### 8.1. Bảng không xuất hiện có phải lỗi?

Chưa chắc. Table có thể chưa được tạo do nguồn chưa gửi dữ liệu, diagnostic category chưa bật hoặc sản phẩm đang dùng dedicated resource-specific tables thay cho **AzureDiagnostics**.

### 8.2. Dùng schema explorer

Trong Log Analytics, xem **Tables**, schema columns và sample records. Không copy một câu KQL có cột **Computer** vào **AppRequests** rồi cho rằng cột đó bắt buộc tồn tại.

### 8.3. Giữ tên bảng theo nguồn

Nếu một category có bảng resource-specific chuẩn, cân nhắc dùng thay vì đẩy tùy tiện vào custom catch-all table. Schema nhất quán giúp quản lý parsing, alerts và request charge hiệu quả.

## 9. Ingestion path 1: Diagnostic settings của Azure resource

Nhiều Azure services có **Diagnostic settings** để chuyển logs/metrics categories tới các đích hỗ trợ, chẳng hạn:

- Log Analytics Workspace.
- Azure Storage account.
- Azure Event Hubs.

Các destinations và categories thực tế phụ thuộc dịch vụ và policy.

~~~mermaid
flowchart LR
    SQL[Azure SQL] --> SET[Diagnostic settings]
    KV[Azure Key Vault] --> SET
    STORAGE[Azure Storage] --> SET
    SET --> LAW[(Log Analytics)]
    SET --> ARCH[(Storage archive khi cấu hình)]
    SET --> HUB[Event Hubs / downstream]
~~~

### 9.1. Chọn category có chủ đích

Một resource có thể cung cấp nhiều diagnostic categories. Bật mọi category cho mọi resource có thể tạo ingestion volume lớn mà không cải thiện SLO. Định nghĩa theo câu hỏi cần trả lời: lỗi truy vấn, truy cập secret thất bại, thay đổi chính sách hay dữ liệu audit.

### 9.2. Resource-specific hay AzureDiagnostics

Một số dịch vụ cho phép dùng dedicated/resource-specific tables thay vì một bảng tổng **AzureDiagnostics**, tùy diagnostic setting và category. Chọn theo khả năng hiện hành, query schema và các tác động migration nếu chuyển mode.

### 9.3. Diagnostic settings không tự chuyển logs đã xảy ra

Việc tạo diagnostic setting thường áp dụng cho events sau khi cấu hình. Đừng mặc định toàn bộ lịch sử quá khứ tự xuất hiện trong workspace.

### 9.4. Tách các đích phục vụ mục tiêu khác nhau

Có thể dùng Log Analytics để query vận hành và Storage account với retention/immutability phù hợp để lưu chứng cứ. Hai đường đi cần được kiểm tra độc lập về completeness, cost, quyền và thời gian lưu; không coi một đích thay thế đích kia.

## 10. Ingestion path 2: Azure Monitor Agent và Data Collection Rules

Với Azure VM và những nguồn được hỗ trợ, **Azure Monitor Agent (AMA)** kết hợp **Data Collection Rule (DCR)** để thu thập và định tuyến dữ liệu như events, syslog và performance counters.

~~~text
Azure VM / supported host
        |
Azure Monitor Agent
        |
Data Collection Rule (source + streams + destination)
        |
Log Analytics Workspace / target table
~~~

### 10.1. DCR gồm những phần gì?

Một DCR tùy loại thường mô tả:

- **Data sources**: thu những streams/logs nào.
- **Streams**: luồng dữ liệu được định danh và schema.
- **Destinations**: gửi tới workspace hoặc đích được hỗ trợ.
- **Data flows**: ánh xạ stream tới destination/table, transformation KQL khi cho phép.
- **Association**: gắn DCR với resource/agent theo cơ chế được hỗ trợ.

### 10.2. DCR không có nghĩa mọi bảng đều được lọc qua một KQL transformation

Ingestion-time transformations có giới hạn theo stream, schema, table và plan; chỉ một tập KQL operators/behaviors được hỗ trợ. Không dùng truy vấn KQL điều tra tùy ý làm DCR transformation và mong deploy thành công.

### 10.3. Legacy agent và AMA

Các mô hình cũ như Log Analytics Agent/MMA có lịch sử tồn tại; với kiến trúc mới nên ưu tiên **Azure Monitor Agent và DCR** theo hướng dẫn đang được hỗ trợ. Khi migrate, cần đối chiếu data coverage, tables, field names và policies; không bật hai collectors vô thức để tránh duplicate ingest.

### 10.4. Resource và DCR phải liên kết đúng

Có AMA chưa đủ: DCR phải có association hoặc cơ chế kết nối đúng với nguồn, table/destination và quyền liên quan. Một agent “healthy” không chứng minh syslog/Windows events đã tới workspace.

## 11. Ingestion path 3: AKS và container logs

Với AKS, có thể bật tích hợp monitoring phù hợp (chẳng hạn Container Insights / Azure Monitor agent-based collection) để đưa container logs và Kubernetes telemetry về workspace.

Các dữ liệu thường có:

- Container stdout/stderr.
- Pod/container metadata.
- Inventory và một số thông số Kubernetes.
- Application messages nếu process ghi ra stdout/stderr.
- Các streams bổ sung theo profile/configuration.

### 11.1. Không log mọi request body từ Java

Spring Boot service có thể ghi một dòng structured JSON cho mỗi failed request hoặc một mẫu nhỏ của successful requests; ghi cả HTTP request body/auth headers ở mọi request sẽ tốn GB và gây rủi ro privacy.

### 11.2. Chuẩn hóa một JSON log event

~~~json
{
  "timestamp": "2026-11-20T10:15:00Z",
  "service": "orders-api",
  "environment": "prod",
  "level": "ERROR",
  "operation": "submitOrder",
  "correlationId": "req-7f21",
  "tenantHash": "t-2e1d",
  "errorCode": "DEPENDENCY_TIMEOUT",
  "durationMs": 2160
}
~~~

**Không** đưa card number, access token, secret hoặc toàn bộ customer profile vào sự kiện. Hash tenant chỉ là pseudonymization, không tự đảm bảo hoàn toàn ẩn danh.

### 11.3. Sampling không áp dụng bừa cho audit

Có thể sampling high-volume diagnostics/traces khi chấp nhận mất một phần events. Với audit/security evidence phải xác định rõ yêu cầu completeness, không sampling nếu chính sách yêu cầu lưu đầy đủ.

### 11.4. Đánh giá ContainerLogV2 và logging pipeline

Bật cấu hình thu thập đúng namespaces/pods/log levels. Kiểm tra schema thực trước khi viết queries, đặc biệt khi có migration từ tables/container insights generation cũ.

## 12. Ingestion path 4: Application Insights dạng workspace-based

**Application Insights** giúp giám sát application requests, dependencies, traces, exceptions và distributed tracing. Với loại **workspace-based Application Insights**, dữ liệu ứng dụng được liên kết với Log Analytics Workspace và có thể được truy vấn trong các bảng tương ứng.

### 12.1. Không trộn Application Insights với logger của mọi service

Application Insights/OTel instrumentation thu request/dependency telemetry, trong khi Java logger thu business/application trace messages. Dùng cả hai để nối **traceId/operationId**, nhưng cần tránh double instrumentation và duplicate log ingestion.

### 12.2. Sampling và retention

Application telemetry volume cao có thể dùng sampling phù hợp để kiểm soát chi phí; quyết định này không nên áp dụng cho audit records cần đầy đủ. Retention trên các bảng liên quan cần được kiểm tra theo workspace-based configuration và table-specific restrictions.

### 12.3. Trace correlation

Khi một request đi qua orders-api → payment-worker → Azure SQL, trace context giúp nối spans. Nếu log không ghi correlation identifier, việc kết hợp app logs và distributed traces sẽ khó và có thể phải dùng heuristics thiếu chính xác.

### 12.4. PII trong traces

Không gắn request headers chứa Authorization, password hay full URL query string có secrets vào attributes. Observability không nên trở thành kênh thu thập dữ liệu nhạy cảm không cần thiết.

## 13. Ingestion path 5: Logs Ingestion API và custom table

Khi ứng dụng hoặc hệ thống ngoài cần gửi custom logs, **Azure Monitor Logs Ingestion API** (kết hợp DCR/stream, destination, authentication và custom table) là một lựa chọn được hỗ trợ theo cấu hình dịch vụ.

~~~text
Custom log producer
    |
JSON payload / batch
    |
Entra-protected Logs Ingestion API endpoint
    |
DCR stream + transformation
    |
Custom table, ví dụ OrderAudit_CL
    |
KQL + retention / access control
~~~

### 13.1. Không gửi API key tùy tiện

Logs Ingestion API sử dụng mô hình xác thực/ủy quyền của Azure Monitor tương ứng, thường dựa trên Microsoft Entra ID và role/scope phù hợp. Đừng nhầm API này với ingestion qua một workspace shared key của các cơ chế legacy.

### 13.2. Thiết kế schema custom table

Các fields tối thiểu có thể là:

| Field | Kiểu | Lý do |
|---|---|---|
| TimeGenerated | datetime | Timeline |
| EventId | string | Correlation/dedup |
| Service | string | Filter |
| Environment | string | Filter |
| TenantHash | string | Hạn chế nhận dạng trực tiếp |
| EventType | string | Phân loại |
| Result | string | Success/failure |
| DurationMs | real/int | Performance |
| CorrelationId | string | Nối traces |

### 13.3. Tránh field động vô hạn

Một document với hàng nghìn attribute names khác nhau làm schema khó quản lý, query khó viết và tăng overhead. Chuẩn hóa naming, data types và schema version.

### 13.4. Điều phối ingest và retry

Custom producer nên dùng batching hợp lý, bounded queue, Retry-After khi có, dedup theo eventId nếu nghiệp vụ yêu cầu và dead-letter khi không thể gửi. Không để out-of-memory do dồn logs khi endpoint tạm không khả dụng.

## 14. Tư duy table plan: Analytics, Basic, Auxiliary

Azure Monitor Logs cung cấp những **table plans** nhằm cân bằng nhu cầu truy vấn và chi phí. Các tên thường gặp gồm **Analytics**, **Basic** và **Auxiliary**; tính năng, giới hạn retention/alerts/query, tính khả dụng theo table và pricing có thể thay đổi theo thời điểm.

| Tiêu chí | Analytics | Basic | Auxiliary |
|---|---|---|---|
| Mục tiêu | Observability/troubleshooting, truy vấn tương tác | High-volume logs với truy vấn ít phức tạp | Infrequently accessed, high-volume data |
| Query | KQL phong phú hơn | Một số khả năng/giới hạn khác Analytics | Giới hạn và mô hình query khác, phụ thuộc features |
| Alerting | Thường phù hợp các loại log alert hỗ trợ | Cần kiểm tra loại alert/khả năng hiện hành | Cần kiểm tra trước khi dùng |
| Retention | Có chính sách interactive/total retention theo giới hạn | Không giả định bằng Analytics | Không giả định bằng Analytics |
| Cost | Cân đối khả năng query với ingestion/retention | Có mô hình billing/query khác | Có mô hình billing riêng |
| Khi dùng | Lỗi ứng dụng, requests, security investigations cần KQL | Verbose diagnostics và occasional lookup | Volume lớn, ít phải truy vấn ngay |

### 14.1. Plan là thuộc tính của table, không chỉ workspace

Không thể chỉ nói workspace có retention 30 ngày là mọi dữ liệu có cùng mức truy vấn và giá. Cần xem **table plan** và các settings của bảng cụ thể.

### 14.2. Chuyển plan có giới hạn

Một số built-in tables không cho chuyển sang mọi plan; có giới hạn về update frequency, supported features và retention settings. **Phải kiểm tra table capability** trước khi thay đổi production.

### 14.3. Đừng chọn Basic/Auxiliary cho security detection mà không kiểm tra

Nếu SOC cần correlation phức tạp, near-real-time alert hoặc khả năng hunting cụ thể, một plan rẻ hơn nhưng bị hạn chế truy vấn có thể làm mất yêu cầu bảo mật. Chọn theo use cases đã kiểm thử.

### 14.4. Tách retention khỏi plan

Table plan ảnh hưởng cách lưu/truy vấn/tính phí; retention ảnh hưởng thời gian dữ liệu tồn tại và khả năng truy vấn ở từng giai đoạn. Hai biến cần được quyết định đồng thời nhưng không phải cùng một thông số.

## 15. Interactive retention và long-term retention: hai lớp thời gian

Khi thiết kế Log Analytics retention, cần phân biệt:

1. **Interactive/analytics retention:** khoảng dữ liệu còn trong phạm vi truy vấn tương tác theo plan/query support của bảng.
2. **Long-term retention:** giai đoạn giữ dữ liệu lâu hơn sau interactive period khi tính năng/table hỗ trợ; cách truy cập có thể đòi hỏi search jobs/restore hoặc quy trình khác tùy service.
3. **Total retention:** tổng thời gian được giữ theo cấu hình, có thể gồm interactive + phần long-term.

~~~text
Event Time                                              Expiration
    |--- Interactive/analytics retention ---|
                                              |--- Long-term period ---|
    |---------------- Total retention ------------------------------|
~~~

### 15.1. Ví dụ thiết kế giả định

- Incident troubleshooting cần tra cứu thường xuyên trong **30 ngày**.
- Security investigations cần giữ tổng cộng **180 ngày**.
- Một nhóm audit records cần giữ theo quy định riêng, chẳng hạn **365 ngày** hoặc lâu hơn nếu được phê duyệt.

**Đây là thời hạn nghiệp vụ minh họa, không phải khẳng định mọi table/plan hỗ trợ được những con số này.** Giới hạn tối thiểu/tối đa và billing thực thay đổi theo plan và sản phẩm.

### 15.2. Sau giai đoạn interactive sẽ truy vấn thế nào?

Không mặc định một dòng dữ liệu trong long-term period vẫn có thể query trực tiếp bằng mọi KQL/alert như lúc còn interactive. Tùy table plan/features, có thể cần **search job**, **restore** hoặc cơ chế hỗ trợ khác, với chi phí, delay, quota và quyền riêng.

### 15.3. Long-term retention không phải immutability

Giữ một bản ghi 365 ngày không đồng nghĩa có bảo đảm WORM/immutable/legal hold. Nếu kiểm toán đòi không thể sửa/xóa và có bằng chứng chain-of-custody, cần kiến trúc lưu trữ chứng cứ chuyên biệt, ví dụ xuất sang Azure Storage có immutable blob policy khi phù hợp.

### 15.4. Thay đổi retention có thể có tác động không đảo ngược

Giảm retention có thể làm dữ liệu cũ bị xóa theo quy tắc dịch vụ sau một thời gian áp dụng. Trước khi đổi cấu hình, cần review legal hold, regulatory retention, backups/exports và impact window. Không dùng một lệnh CLI production để “thử” xóa dữ liệu.
## 16. Thiết kế ma trận retention cho hệ thống mẫu

Đừng bắt đầu bằng “workspace lưu 180 ngày”. Hãy chọn từng data category theo **câu hỏi điều tra**, **mức độ truy cập** và **yêu cầu tuân thủ**.

| Nhóm dữ liệu giả định | Nguồn/table có thể gặp | Cần truy vấn tương tác | Mục tiêu giữ tổng | Phương án |
|---|---|---:|---:|---|
| Application error | AppTraces hoặc table tùy logging pipeline | 30 ngày | 90 ngày | Analytics với table override nếu hỗ trợ |
| HTTP request telemetry | AppRequests | 30 ngày | 60 ngày | Analytics, sampling phù hợp |
| Container verbose log | ContainerLogV2 | 7–30 ngày | 30 ngày | Giảm volume trước ingest, cân nhắc plan theo tính năng |
| VM syslog/Windows events | Syslog/Event | 30 ngày | 180 ngày | DCR lọc severity/category |
| Platform control-plane | AzureActivity | 90 ngày | 365 ngày | Kiểm tra table capabilities và nguồn audit song song |
| Key Vault access audit | Bảng diagnostic tương ứng | 90 ngày | 365 ngày | Cô lập access, có thể export chứng cứ |
| Custom business audit | OrderAudit_CL | 90 ngày | Theo chính sách pháp lý | Design schema/retention và immutable evidence khi cần |

**Các thời hạn trong bảng chỉ là yêu cầu giả định**. Khi áp dụng, xác nhận hạn mức retention/table plan, billing, privacy, data residency và quy định của tổ chức. Không coi “bắt buộc giữ 365 ngày” là điều mặc định cho mọi doanh nghiệp.

### 16.1. Thêm cột owner và disposal action

Trong tài liệu retention production nên có:

~~~text
Data category | Owner | Source | Table
Interactive days | Total days | Allowed roles
Legal basis | Residency | Export requirement
Deletion method | Budget | Review date
~~~

### 16.2. Khi log có nhiều mục đích

Một log có thể phục vụ SRE 30 ngày và security 1 năm. Nếu hai nhóm quyền rất khác nhau, cân nhắc separate pipelines/workspaces hoặc lưu bản chứng cứ khác có ACL riêng, thay vì mở quyền xem toàn bộ thông tin bảo mật cho mọi developer.

### 16.3. Retention không bảo đảm dữ liệu được thu đầy đủ

Mục tiêu lưu giữ 365 ngày không có ý nghĩa nếu diagnostic setting bị tắt 20 ngày. Theo dõi ingestion health, coverage và loss detection song song với table configuration.

## 17. Thời hạn giữ: một ví dụ theo đường thời gian

Giả sử event xảy ra ngày **01/01** và table có interactive retention 30 ngày, total retention 180 ngày theo cấu hình được hỗ trợ.

~~~text
01/01                   Khoảng 31/01                  Khoảng cuối 06
  |--------------------------|------------------------------|
      Interactive queries          Long-term retention
      (theo table plan)            (cách truy cập khác)
  |---------------------------------------------------------|
                       Total retention
~~~

### 17.1. Tổng thời hạn không phải cộng hai con số một cách máy móc

Nếu **total retention = 180 ngày** và interactive = 30 ngày, giai đoạn long-term minh họa khoảng 150 ngày còn lại, không phải **30 + 180 = 210 ngày**. Tham số API/Portal thực phải được xác minh cho table và plan.

### 17.2. Mốc thời gian và expiration

Dịch vụ có thể áp dụng housekeeping/xóa theo chu kỳ và các semantics ingestion/TimeGenerated cụ thể. Không dùng Workspace retention làm một đồng hồ xóa chính xác đến từng giây cho dữ liệu cần bảo đảm đặc biệt. Khi có quy định xóa theo ngày, phải xây quy trình kiểm chứng trên hệ thống thực và lưu biên bản.

### 17.3. Khi cần truy cập lịch sử

Nếu investigation yêu cầu truy vấn dữ liệu hết interactive period nhưng còn long-term, người vận hành cần biết **quy trình search/restore**, thời gian chờ, quyền và chi phí. Runbook phải có owner và bước xác nhận. Không đợi đến sự cố mới phát hiện table đang ở plan không hỗ trợ query mong muốn.

### 17.4. Khi cần lưu lâu hơn giới hạn table

Xem kiến trúc **xuất log sang Azure Storage hoặc hệ lưu chứng cứ khác**, áp chính sách immutability/retention riêng theo nguồn và yêu cầu. Đó là một hệ thống khác, có quyền, chi phí và thủ tục truy xuất khác, không chỉ là tăng retentionInDays.

## 18. Quy trình lựa chọn retention có thể kiểm toán

Một phương pháp 8 bước:

1. **Inventory**: liệt kê nguồn, table, schema, size, owner, vùng dữ liệu và nhãn nhạy cảm.
2. **Use cases**: điều tra vận hành, cảnh báo, threat hunting, audit và pháp lý.
3. **Interactive horizon**: cần tìm dữ liệu bao xa với thời gian trả lời thấp?
4. **Total horizon**: cần còn tồn tại bao lâu, kể cả dữ liệu ít truy vấn?
5. **Technical feasibility**: plan/table hỗ trợ retention và search/alert gì?
6. **Access controls**: ai được truy vấn theo scope? Có cần workspace tách biệt?
7. **Cost model**: ingest GB, interactive retention, long-term retention, search/restore/export.
8. **Approval & review**: phê duyệt, triển khai bằng IaC, xác minh và rà soát định kỳ.

### 18.1. Khi yêu cầu mâu thuẫn

Ví dụ SOC muốn log chi tiết một năm, còn privacy policy chỉ cho giữ dữ liệu nhận dạng tối thiểu 30 ngày. Không tự chọn con số lớn hơn. Cần cùng legal/privacy/SOC thống nhất mục đích, redaction, access, dữ liệu cần giữ và căn cứ pháp lý; có thể giữ chỉ số/tổng hợp thay cho dữ liệu định danh chi tiết.

### 18.2. Retention không thay data lifecycle toàn hệ thống

Azure Storage archive, SQL audit, Event Hubs capture, Application Insights và Log Analytics có các chính sách độc lập. Cần một **data map** để biết bản sao nào còn tồn tại, không chỉ kiểm tra một workspace.

### 18.3. Retention theo bảng hay theo category?

Dễ quản trị nhất khi mỗi table chứa loại dữ liệu có thời hạn và quyền tương đối thống nhất. Nếu một table trộn nhiều category với retention trái ngược, table-level policy sẽ khó tối ưu; nên cân nhắc routing/splitting phù hợp hơn.

## 19. Workspace retention mặc định và table overrides

Workspace-level retention là **baseline**, không thay thế per-table policy. Một thiết kế gợi ý:

~~~text
Workspace: law-prod-ops
  Default interactive retention: 30 days (minh họa)

Tables:
  AppRequests        -> follow baseline or approved override
  AppTraces          -> independent total retention when supported
  ContainerLogV2     -> approved plan/retention
  AzureActivity      -> retention and compliance-specific controls
  OrderAudit_CL      -> policy-driven retention, secure access
~~~

### 19.1. Kiểm tra cả retentionInDays và totalRetentionInDays

Các interfaces/API có thể dùng các trường tương đương **retentionInDays** (interactive) và **totalRetentionInDays** (total), nhưng hình thức/khả năng cấu hình phụ thuộc table. Cần đọc lại cấu hình sau deploy, không chỉ tin IaC template đã apply.

### 19.2. Nếu một table theo workspace default

Đừng ghi nhận trong policy rằng table chắc chắn giữ 30 ngày chỉ vì workspace đang đặt 30. Có thể table override hoặc service-specific behavior. Inventory settings từ Azure resource để xác nhận thực tế.

### 19.3. Kế hoạch thay đổi retention

- Ước lượng volume affected, cost và dữ liệu có thể hết hạn.
- Kiểm tra legal hold và tác động tới alert/query.
- Xác minh plan change nếu có.
- Backup/export theo yêu cầu trước khi giảm thời hạn.
- Deploy có approval và audit.
- Query lại settings sau triển khai.
- Theo dõi truy vấn, alert và bill sau thay đổi.

## 20. Tính kích thước log trước khi cam kết lưu giữ

Giả sử hệ thống minh họa có:

- **15 GB/ngày** application/container logs trước lọc.
- **5 GB/ngày** platform/security logs.
- Sau sampling/filter hợp lệ, giảm application diagnostics xuống **8 GB/ngày**.
- Tổng ingest còn **13 GB/ngày**.

Ước lượng rough order of magnitude:

\[
\text{Volume}_{30d} \approx 13 \times 30 = 390\ \text{GB}
\]

\[
\text{Volume}_{180d} \approx 13 \times 180 = 2340\ \text{GB}
\]

**Đây là phép nhân số liệu lưu lượng, không phải công thức tính bill Azure**. Azure Monitor có cách đo billed data volume, plan/tier, table retention, free data categories, compression/metadata và pricing model riêng.

### 20.1. Không nhân mọi loại log với cùng 180 ngày

Nếu 8 GB/ngày app log chỉ giữ 30 ngày còn 5 GB/ngày security log giữ 180 ngày, dữ liệu tồn tại trung bình theo mô hình đơn giản xấp xỉ:

\[
8 \times 30 + 5 \times 180 = 1140\ \text{GB}
\]

Số này minh họa tồn lưu logic, chưa phân loại interactive vs long-term, index/storage representation hay cách Azure tính tiền.

### 20.2. Burst và growth

Sự cố có thể làm error logs tăng gấp 10 lần trong vài giờ. Cost forecast phải có peak scenarios, release growth, container autoscaling, retries và retention export duplication.

### 20.3. Cần đo actual ingestion

Không lấy số dòng logger × kích thước trung bình làm billing chính thức. Kiểm tra workspace usage/billing metrics và các bảng thực, đối chiếu với hóa đơn Cost Management.

## 21. Các thành phần chi phí cần đưa vào mô hình

| Nguồn phí | Vì sao phát sinh | Cách giảm hợp lý |
|---|---|---|
| **Data ingestion** | Bản ghi đưa vào Azure Monitor Logs theo table plan | Lọc trước ingest, sampling được phép, structured concise logs |
| **Interactive/analytics retention** | Giữ dữ liệu trong phạm vi truy vấn nhanh khi vượt mức included/quy định | Chọn retention horizon đúng |
| **Long-term retention** | Lưu dữ liệu lâu hơn interactive khi hỗ trợ | Chỉ áp vào categories cần giữ |
| **Query charges** | Một số table plans/query modes/search jobs có tính phí | Giới hạn time range và selectivity |
| **Restore/search jobs** | Truy cập dữ liệu long-term theo tính năng | Dự tính nhu cầu điều tra/khôi phục |
| **Data export** | Xuất bản ghi tới Storage/Event Hubs qua tính năng liên quan | Chỉ export categories thật cần |
| **Storage archive** | Lưu immutable/long-retention evidence | Lifecycle tier và access policy |
| **Network/egress** | Chuyển dữ liệu giữa region/đích | Đặt cùng region khi phù hợp |
| **Compute/agents** | AMA, OTel collectors, Java resource usage | Kiểm soát CPU/heap/pipeline |
| **Dashboards/alerts** | Rule evaluations và telemetry ingestion theo pricing | Tối ưu polling/query |

### 21.1. Analytics vs Basic/Auxiliary không chỉ là ingest price

Plan khác có thể có giới hạn query/alert/retention, cách tính phí query riêng. Mức phí tổng phải dựa trên **use case**, không chọn chỉ theo giá ingest trên một GB.

### 21.2. Retention và reserved capacity/commitment tiers

Một số pricing options có mô hình cam kết ingest và chiết khấu theo usage; cần kiểm tra lợi ích với workload ổn định, minimum/commitment terms và biến thiên lưu lượng. Không giả định commitment luôn rẻ hơn pay-as-you-go.

### 21.3. Data volume của development

Debug logs ở dev có thể rất verbose; tách workspace hoặc dùng filters/horizon ngắn giúp tránh nuốt ngân sách của production operations.

## 22. DCR transformations: bỏ dữ liệu rác trước khi ingest

Với các streams/tables có hỗ trợ **ingestion-time transformation**, có thể dùng một subset KQL để chọn bản ghi, làm sạch fields hoặc ánh xạ schema trước khi dữ liệu vào workspace.

Ví dụ **minh họa logic**, không phải DCR JSON triển khai trực tiếp cho một stream bất kỳ:

~~~kusto
source
| where Level in ("Error", "Critical", "Warning")
| project TimeGenerated, Level, Service, Message, CorrelationId
~~~

### 22.1. Lợi ích

- Bỏ debug/verbose records không cần thiết.
- Giảm số trường dài hoặc vô dụng.
- Chuẩn hóa một số fields để query.
- Hạn chế gửi dữ liệu nhạy cảm khi transform được hỗ trợ và thiết kế đúng.

### 22.2. Các giới hạn

- Không phải mọi data source/table đều có transformation ở cùng chặng.
- Chỉ subset operators được hỗ trợ; syntax/stream names phải đúng.
- Một số ingestion costs/processing charges có semantics riêng.
- Transform có thể làm mất dữ liệu cần cho forensic investigation.
- Thay DCR có thể làm logs sau thay đổi khác schema với quá khứ.

### 22.3. Transform không phải biện pháp bảo mật duy nhất

Nếu event đã chứa secret ở upstream logs, nó có thể tồn tại ở buffers/intermediate collectors hoặc nơi khác. Loại bỏ secret **ngay tại ứng dụng** là ưu tiên cao hơn.

### 22.4. Kiểm thử trước khi bật rộng

Bắt một sample stream lab, xác minh số events trước/sau, schema, KQL và downstream alerts; rollout canary, có cách rollback và kiểm tra các nguồn không bị mất dữ liệu quan trọng.

## 23. KQL căn bản: lọc thời gian, bảng và trường

KQL là ngôn ngữ truy vấn dạng pipeline, mỗi stage được nối bằng dấu **|**. Ví dụ tìm lỗi application traces:

~~~kusto
AppTraces
| where TimeGenerated >= ago(24h)
| where SeverityLevel >= 3
| project TimeGenerated, Message, OperationId, _ResourceId
| order by TimeGenerated desc
| take 100
~~~

**Điều kiện:** workspace-based Application Insights thực sự có bảng **AppTraces** và các cột nêu trên. Severity semantics cần kiểm tra theo nguồn/SDK.

### 23.1. Đặt time range trước

Giới hạn query ngay từ đầu giúp giảm dữ liệu scan và latency. Một query “all time” không cần thiết có thể đắt, nhất là với table plans có query billing riêng.

### 23.2. Project ít cột

Không dùng **project \*** để xuất toàn bộ document, PII và custom fields khi chỉ cần Message/OperationId. Query output có thể bị copy vào ticket và lan dữ liệu nhạy cảm.

### 23.3. Không nhầm message text với event type

Tìm bằng contains trong log text có thể dùng khi điều tra nhưng khó chuẩn hóa; với các sự kiện quan trọng nên có cột **EventType**, **ErrorCode** hoặc **OperationName** riêng để aggregate.

## 24. KQL: thống kê p95 latency và tỷ lệ lỗi ứng dụng

Ví dụ workspace-based Application Insights:

~~~kusto
AppRequests
| where TimeGenerated >= ago(24h)
| summarize
    Requests = count(),
    Failures = countif(Success == false),
    P95LatencyMs = percentile(DurationMs, 95)
  by Name
| extend FailureRatePct = 100.0 * Failures / Requests
| order by P95LatencyMs desc
~~~

### 24.1. p95 và p99 dùng làm gì?

- **p95**: 95% requests có latency không vượt ngưỡng đó.
- **p99**: nhìn đuôi latency cho 1% requests chậm nhất.
- **Average** có thể che sự cố ảnh hưởng một nhóm người dùng.

Nếu telemetry bị sampling hoặc thiếu records, phép tính từ sampled data cần được diễn giải đúng; không mặc định count tuyệt đối luôn đại diện mọi request production.

### 24.2. Dimension cardinality

Gom theo **Name** phù hợp endpoint/operation, còn gom theo raw URL có user ID/order ID sẽ tạo hàng triệu nhóm và lộ dữ liệu. Chuẩn hóa URL routes thành **/orders/{id}** trước khi ghi telemetry.

### 24.3. Đọc schema thực trước khi sửa query

Cột **DurationMs**, **Success**, **Name** có trong table/model liên quan; nếu nguồn là custom table, cần đổi theo các cột tương ứng. Không giả định Application Insights luôn ở workspace-based mode.

## 25. KQL: điều tra thay đổi tài nguyên với AzureActivity

~~~kusto
AzureActivity
| where TimeGenerated >= ago(7d)
| summarize Events = count()
  by OperationNameValue, ActivityStatusValue
| order by Events desc
~~~

### 25.1. Tìm thay đổi có rủi ro

Tập trung các operations như thay RBAC, xóa tài nguyên, chỉnh network/firewall hoặc thay policy theo cột được nguồn cung cấp. Tên operations/category cần xác nhận trên subscription thực tế.

### 25.2. Control-plane không bao gồm mọi data access

**AzureActivity** không tự ghi đầy đủ ai đã đọc một secret hay ai đã query một SQL row. Để giám sát data-plane, cần bật đúng diagnostic categories của Key Vault, SQL, Storage và các tài nguyên liên quan.

### 25.3. Quyền truy vấn audit

Những ai được phép xem changes/audit events thường khác nhóm dev debugging. Áp RBAC và xuất audit evidence thích hợp; không phát URL query chứa sensitive details công khai.

## 26. KQL: quan sát lỗi container trên AKS

~~~kusto
ContainerLogV2
| where TimeGenerated >= ago(1h)
| summarize Events = count()
  by PodName, LogLevel
| order by Events desc
~~~

**Lưu ý:** tên các cột phụ thuộc schema table/data collection version. Nếu không có **LogLevel** trong môi trường của bạn, thay bằng field thực hoặc parse message theo schema được phê duyệt.

### 26.1. Lỗi Pod không luôn nằm trong stdout

Một Pod bị OOMKilled hoặc scheduling error có thể cần Kubernetes events/metrics và inventory, không chỉ ContainerLogV2. Quan sát tốt kết hợp metrics + events + logs.

### 26.2. Nhiều replicas và correlation

Tìm logs theo service/namespace/pod và request correlation ID. Không dựa vào PodName duy nhất vì Pod có thể bị recreate; cần đánh giá deployment labels, namespace và time range.

### 26.3. Container restart

Khi Pod restart, logs có thể bị mất nếu collector chưa gửi hoặc container runtime đã rotate. Workspace retention chỉ áp dụng cho dữ liệu đã được ingest, không đảm bảo giữ stdout trên node trước khi ingest.

## 27. KQL: ước lượng dung lượng dữ liệu đã ingest

Với một bảng có hỗ trợ **_BilledSize**:

~~~kusto
AppTraces
| where TimeGenerated >= ago(7d)
| summarize
    Records = count(),
    ApproxGB = sum(_BilledSize) / 1024.0 / 1024.0 / 1024.0
  by bin(TimeGenerated, 1d)
| order by TimeGenerated asc
~~~

Đây là **ước lượng theo cột trên bản ghi được truy vấn**, không phải hóa đơn chính thức. Sự khác biệt có thể đến từ billable status, latency/time boundary, data plans và bảng không có _BilledSize.

### 27.1. Cần đo tổng workspace theo billing telemetry

Để chargeback/cost, đối chiếu Azure Monitor usage metrics, bảng Usage khi phù hợp, table-level data ingestion và Azure Cost Management. Không dựa vào một truy vấn 7 ngày trên AppTraces để kết luận toàn workspace tiêu thụ bao nhiêu GB.

### 27.2. Mismatch giữa TimeGenerated và ingestion date

Nếu có logs đến trễ (ví dụ agent offline hai ngày), lọc TimeGenerated có thể không trùng ngày billed ingestion. Khi phân tích sự cố pipeline, kiểm tra **ingestion_time()** và service usage theo cách được hỗ trợ.

### 27.3. Không coi mọi GB đều cùng giá

Analytics/Basic/Auxiliary plans và pricing dimensions khác nhau; một phép cộng GB không phản ánh query/retention/export charges.

## 28. KQL: đo độ trễ ingest ở một bảng có hỗ trợ

~~~kusto
AppTraces
| where TimeGenerated >= ago(24h)
| extend IngestedAt = ingestion_time()
| where isnotnull(IngestedAt)
| extend IngestionDelayMin =
    datetime_diff("minute", IngestedAt, TimeGenerated)
| summarize
    P50DelayMin = percentile(IngestionDelayMin, 50),
    P95DelayMin = percentile(IngestionDelayMin, 95)
  by bin(TimeGenerated, 1h)
| order by TimeGenerated asc
~~~

### 28.1. Diễn giải cẩn thận

Với hàm **datetime_diff("minute", later, earlier)**, kết quả thường là số phút **later - earlier**. Trong ví dụ, IngestedAt là mốc đến sau TimeGenerated. Bản ghi có clock skew, delayed batch hoặc timestamp sai có thể làm delay âm/bất thường.

### 28.2. Khi không có ingestion_time()

Không phải table/plan nào hỗ trợ hoặc có giá trị như mong đợi. Cần dùng Azure Monitor ingestion metrics, collector health hoặc timestamps từ source và pipeline theo tính năng hỗ trợ.

### 28.3. Thiết lập alert theo độ trễ

Nếu hệ thống yêu cầu sự kiện bảo mật được truy vấn trong vòng 10 phút, giám sát ingestion latency và missing-event coverage, không chỉ Workspace có tồn tại hoặc workspace query chạy được.

## 29. KQL: tránh lỗi query tốn kém

Những anti-pattern thường gặp:

- Query không đặt **TimeGenerated** window.
- Sử dụng **search \*** trên mọi table/workspace không cần thiết.
- Lấy tất cả cột/text chứa PII để export ra CSV.
- Join dữ liệu volume lớn mà không lọc trước.
- Tạo summarize theo field cardinality cực lớn như requestId.
- Alert evaluation chạy quá thường xuyên trên queries phức tạp.
- Query một table plan không hỗ trợ operator/alert đang dùng.
- Dùng KQL query result như database transaction log đảm bảo đầy đủ.

### 29.1. Tối ưu có hệ thống

1. Lọc time range và resources càng sớm càng hợp lý.
2. Chỉ chọn tables chứa signal cần tìm.
3. Project những fields cần thiết.
4. Aggregate theo dimensions có cardinality vừa phải.
5. Giới hạn output rows.
6. Đo thời gian thực thi và dữ liệu scan.
7. Test alert rules với synthetic events và historical data.

### 29.2. KQL không biến log thành bằng chứng không thể sửa

Một truy vấn in ra “0 failures” có thể vì chưa ingest, table không tồn tại, time range sai hoặc logs đã bị filter. Luôn xác minh data completeness trước khi kết luận hệ thống hoàn toàn không lỗi.

## 30. Truy vấn và thiết kế alerts phải gắn với retention

Ví dụ SRE cần alert khi ứng dụng có nhiều thất bại trong 5 phút. Có thể dùng một **scheduled query alert** dựa trên KQL hỗ trợ:

~~~kusto
AppRequests
| where TimeGenerated >= ago(5m)
| summarize Failed = countif(Success == false)
| where Failed >= 20
~~~

Đây là **query minh họa**; ngưỡng, tần suất đánh giá, dimensions và quyền rule được cấu hình trong Azure Monitor alert rule theo tính năng table plan và resource hiện hành.

### 30.1. Retention không thay alert evaluation

Giữ log 180 ngày không đồng nghĩa alert có thể đánh giá một cửa sổ 180 ngày hoặc có nghĩa vụ xem toàn lịch sử. Cảnh báo thường dựa trên windows ngắn, kèm telemetry có chất lượng và độ trễ ingest được chấp nhận.

### 30.2. Long-term data không mặc định là nguồn cho real-time alerts

Nếu logs chuyển sang long-term stage không có interactive alert capabilities, phải bảo đảm threat detections được đánh giá trong khi dữ liệu còn ở giai đoạn hỗ trợ. Lưu giữ dài để điều tra quá khứ khác mục đích phát hiện sớm.

### 30.3. Alert phải kiểm chứng với failure injection

Tạo một synthetic test event hoặc lab lỗi có kiểm soát, xác minh event tới table, KQL match, alert fires và action group/notification đúng kênh. Không chỉ test câu query có syntax hợp lệ.

### 30.4. Cost và cardinality của alert

Một query alert quét logs quá rộng mỗi phút có thể tăng query cost hoặc quá tải. Chọn scopes, filters và evaluation frequency theo SLO và capacity.
## 31. Azure RBAC: ai được xem log của ai?

Một workspace có thể chứa logs nhạy cảm từ nhiều Azure resources. Cần kiểm soát quyền không chỉ ở “có thể mở workspace” mà cả **query scope**, **resource permissions**, **table restrictions** khi khả dụng và dữ liệu nhạy cảm trong bản ghi.

### 31.1. Workspace-context và resource-context

Azure Monitor Logs hỗ trợ những mô hình truy cập liên quan tới workspace context và resource context:

- **Workspace-context:** người dùng có quyền workspace phù hợp có thể truy vấn dữ liệu theo phạm vi được cấp.
- **Resource-context:** theo cách cấu hình và khả năng của Azure Monitor, quyền trên resource có thể cho truy vấn logs liên quan resource đó mà không nhất thiết cấp quyền rộng trên toàn workspace.
- **Access control mode:** thiết lập workspace ảnh hưởng cách áp dụng quyền theo resource/workspace.

**Không mặc định resource-context lọc an toàn mọi custom row của mọi bảng.** Bản ghi cần có metadata/resource association hợp lệ và table/query capabilities tương ứng. Đừng dùng điều kiện WHERE tenantId = ... trong KQL làm ranh giới chống đọc chéo nếu người dùng có thể query nguyên bảng.

### 31.2. Role nào phù hợp?

Các built-in roles như **Log Analytics Reader**, **Log Analytics Contributor**, **Monitoring Reader** hoặc custom roles có quyền khác nhau trên scopes. Cần kiểm tra **actions/data actions** đúng với nhiệm vụ, ví dụ xem logs, sửa retention, thay diagnostic setting, tạo alert hay export data.

### 31.3. Tách người điều tra và người quản trị

| Vai trò tổ chức | Quyền cần thiết | Tránh |
|---|---|---|
| SRE | Query application logs, xem alerts/workbooks | Không cần sửa workspace retention |
| Developer | Xem logs dịch vụ được phân quyền | Không cần xem secrets/audit toàn tổ chức |
| Security analyst | Query security/audit logs, điều tra sự cố | Không mặc định có quyền chỉnh pipelines |
| Platform admin | Quản lý workspace/DCR/IaC | Không cần xem mọi PII |
| Compliance auditor | Truy xuất bằng chứng theo quy trình | Không cần sửa/xóa event data |
| CI/CD identity | Deploy đúng resources được cấp | Không cấp Owner toàn subscription nếu không cần |

### 31.4. Kiểm tra access thực

Dùng test principals đại diện SRE, developer, security, CI/CD và một người không thuộc nhóm; thử queries ở workspace và resource contexts. Xác minh **không truy cập được** tables/resources ngoài phạm vi, không chỉ thử case được phép.

## 32. Microsoft Entra ID, Managed Identity và ingestion permissions

Có nhiều principal khác nhau:

1. **Người truy vấn** trong Portal/KQL.
2. **Managed identity của ứng dụng/collector** gửi custom logs.
3. **Identity hoặc service configuration** dùng khi Diagnostic settings chuyển logs.
4. **IaC deployment identity** tạo workspace/DCR/permissions.
5. **Automation/runbook identity** truy vấn, export hoặc kiểm tra retention.

### 32.1. Không dùng một identity làm tất cả

Workload Java chỉ cần ingest custom logs không nên được phép sửa workspace retention hoặc cấp RBAC cho người khác. IAM principle: **least privilege, separation of duties và auditing**.

### 32.2. Logs Ingestion API

Custom log ingestion cần authentication/authorization theo DCR/Logs Ingestion API contract; role và scope phải đúng với DCR/destination được phép. Khi dùng managed identity, không lưu token dài hạn trong source, không hardcode secrets trong collector config.

### 32.3. IaC và RBAC là hai kế hoạch khác nhau

Một deployment có thể tạo workspace thành công nhưng không thể query logs do identity thiếu read permission. Ngược lại, quyền query không tự cho phép thay retention. Ghi rõ caller principal và scope cho từng bước.

### 32.4. Token/log leakage

Không log bearer tokens hoặc Key Vault secret values trong “debugging HTTP headers”. Ngay cả nếu log chỉ giữ 7 ngày, việc dữ liệu bí mật đã đi vào hệ monitoring là một sự cố cần xử lý.

## 33. Network security, Private Link và data residency

Một kiến trúc private có thể cần **Azure Monitor Private Link Scope (AMPLS)**, Private Endpoints, DNS và cấu hình phù hợp giữa workspace/data collection endpoints/query endpoints tùy ingestion path.

~~~mermaid
flowchart LR
    APP[Azure VMs / AKS collectors] --> VNET[Private VNet / DNS]
    VNET --> SCOPE[Azure Monitor Private Link Scope]
    SCOPE --> LAW[(Log Analytics Workspace)]
    USER[Secured analyst network] --> VNET
    LAW --> POLICY[Workspace/table retention]
~~~

### 33.1. Không phải bật private endpoint một lần là xong

Các nguồn như Azure platform Diagnostic settings, AMA/DCR, Logs Ingestion API và các query clients có cơ chế network khác nhau. Xác minh data path thực cho từng loại và tính năng hỗ trợ. Đừng giả định tất cả services “đi qua cùng private IP”.

### 33.2. Data Collection Endpoint (DCE)

Một số luồng ingestion/DCR và Private Link scenarios sử dụng **Data Collection Endpoint** hoặc endpoints do DCR cung cấp tùy API/source. Khi thiết kế AMPLS, DCR, DCE và DNS phải thống nhất; kiểm tra tài liệu theo API version/service cụ thể.

### 33.3. DNS/TLS troubleshooting

- FQDN có resolve về đúng public/private endpoint theo network policy?
- Proxy/NAT/firewall có cho phép lưu lượng cần thiết?
- TLS trust chain có được giữ nguyên?
- Có outbound restriction hoặc private DNS zone bị thiếu?
- Agent/collector có đủ quyền và liên kết DCR đúng?

Không tắt TLS verification hoặc mở public ingress vô hạn để chữa lỗi logs không đến.

### 33.4. Residency và cross-region

Workspace có region riêng, khác với resources phát log; export/cross-workspace queries có thể liên quan nhiều vùng. Kiểm tra chính sách data residency và chi phí chuyển dữ liệu trước khi tập trung log vào workspace khác region.

## 34. Governance: privacy, PII và lifecycle xóa dữ liệu

Một chính sách giữ log tốt phải giải thích **không nên ingest gì**, **ai được xem** và **khi nào xóa**.

### 34.1. Phân cấp dữ liệu

Ví dụ nhãn:

- **Public telemetry**: số lượng requests, latency tổng hợp.
- **Internal operational**: error codes, deployment metadata.
- **Confidential business**: tenant event payloads, customer IDs.
- **Restricted**: authentication material, các thông tin cá nhân nhạy cảm.

Đối với restricted secrets, giải pháp mặc định là **không ghi vào log**. Với identifiers cần thiết cho correlation, xem pseudonymization/tokenization, retention ngắn và ACL chặt.

### 34.2. Redaction theo nhiều lớp

1. Redact ở Java logger/instrumentation.
2. Lọc headers/query parameters tại ingress/collector.
3. DCR transformation nếu stream hỗ trợ.
4. Restrict query/export permissions.
5. Giám sát accidental secret leakage và có quy trình incident response.

**Redaction downstream không xóa các bản sao upstream** như app stdout buffer, collector files hoặc exported audit pipeline.

### 34.3. Quyền xóa dữ liệu cá nhân

Một số quy định có thể yêu cầu xóa hoặc hạn chế xử lý dữ liệu. Cần phân tích dữ liệu đã phát tán ở những hệ thống nào, tính năng purge/delete mà Azure Monitor hỗ trợ, giới hạn thời gian và legal hold. **Không mặc định thay retention xuống một ngày sẽ đáp ứng ngay một yêu cầu xóa cụ thể.**

### 34.4. Retention review

Mỗi 3–6 tháng (hoặc theo chính sách) review tables, owner, volume, permission, use case, legal basis, costs và khả năng truy xuất lịch sử. Ghi thành change record kèm người phê duyệt.

## 35. Audit evidence, long-term export và immutability

Một số loại sự kiện (thay role, truy cập secrets, hành động tài chính quan trọng) có thể cần bằng chứng giữ lâu và chống sửa/xóa.

### 35.1. Vì sao Log Analytics không phải hệ WORM mặc định?

Table retention điều khiển thời gian log còn tồn tại. Nó không tự cấp bảo đảm **write-once-read-many (WORM)** theo yêu cầu kiểm toán, không tự đảm bảo legal hold hoặc chứng minh integrity chain.

### 35.2. Kiến trúc chứng cứ tham khảo

~~~mermaid
flowchart LR
    SOURCE[Security / audit events] --> QUERY[(Log Analytics)]
    SOURCE --> EXPORT[Authorized export path]
    EXPORT --> STORE[(Azure Storage)]
    STORE --> WORM[Immutability policy / Legal hold]
    QUERY --> DETECT[Detections / Investigations]
    WORM --> AUDIT[Compliance retrieval]
~~~

Tùy dịch vụ, có thể dùng **Diagnostic settings** xuất trực tiếp sang Storage/Event Hubs hoặc **Log Analytics data export** cho tables được hỗ trợ. Tính năng export, phí, table compatibility và thời điểm bắt đầu export khác nhau; đừng mặc định export tự bao gồm mọi bản ghi quá khứ.

### 35.3. Azure Storage immutable blob storage

Azure Storage có các khả năng **time-based retention/immutability policy, legal hold** khi loại tài khoản/container phù hợp. Cần xem xét:

- Phạm vi policy.
- Ai có quyền set/remove/lock policy.
- Retention period theo yêu cầu.
- Encryption, access logs và backup.
- Cách truy xuất phục vụ audit.
- Rủi ro chi phí và không thể xóa trước hạn khi khóa đúng.

### 35.4. Chain of custody

Nếu cần bằng chứng pháp lý, ghi export timestamp, source, file hashes, manifest, owner, access history và quy trình kiểm tra integrity. Một file CSV lưu trong Storage chưa phải chứng cứ pháp lý đáng tin chỉ vì có tên “audit”.

### 35.5. Đừng dùng export làm backup toàn diện mà không thử restore

Test khả năng tìm lại đúng phạm vi thời gian, schema, nguồn, event count, timestamp và khả năng truy vấn lại. Nếu muốn restore/search sau 9 tháng, cần chứng minh trước trong lab theo quy trình được hỗ trợ.

## 36. Tạo workspace bằng Azure Portal và CLI

Trước khi thao tác, dùng resource group, subscription, region và ngân sách lab có quyền. Không chạy lệnh quản trị trên production nếu chưa được phê duyệt.

### 36.1. Portal workflow

1. Tạo/chọn resource group **rg-observability-lab**.
2. Tạo **Log Analytics Workspace** tên **law-observability-lab** ở region được phê duyệt.
3. Kiểm tra workspace identity/resource ID, region, pricing và retention baseline.
4. Cấu hình access control phù hợp; phân quyền qua RBAC.
5. Chọn data sources: diagnostic settings, DCR/AMA hoặc App Insights.
6. Xác minh có ít nhất một table nhận dữ liệu.
7. Mở Logs, chạy query có time range.
8. Thiết lập alerts và budgets cho lab.
9. Ghi rõ cleanup requirements.

### 36.2. Azure CLI mẫu cho workspace

Ví dụ Bash/WSL; các biến và lệnh chỉ để chạy trong **tài khoản lab được phép**:

~~~bash
RG="rg-observability-lab"
LAW="law-observability-lab"
LOCATION="southeastasia"

az account show --query "{subscription:id,name:name}" -o table

az group create \
  --name "$RG" \
  --location "$LOCATION"

az monitor log-analytics workspace create \
  --resource-group "$RG" \
  --workspace-name "$LAW" \
  --location "$LOCATION" \
  --sku PerGB2018 \
  --retention-time 30

az monitor log-analytics workspace show \
  --resource-group "$RG" \
  --workspace-name "$LAW" \
  --query "{id:id,retention:retentionInDays,location:location}" \
  -o json
~~~

**southeastasia là region minh họa, không phải mặc định tối ưu cho mọi tổ chức.** CLI extension/version và SKU capabilities có thể thay đổi: trước khi dùng automation, kiểm tra **az monitor log-analytics workspace create -h** và compatibility trong môi trường thực. **Đây không phải kết quả lệnh đã chạy**.

### 36.3. Không suy rằng workspace có dữ liệu ngay

Sau create, workspace thường chưa có log sources. Kết nối diagnostic setting hoặc DCR, chạy event thử và đợi ingestion; workspace rỗng không phải lỗi nếu chưa có pipeline.

### 36.4. Không xóa resource group mù quáng

Khi cleanup, xác minh đây là RG lab riêng, không có resource dùng chung và có approval. Lệnh xóa RG có thể xóa cả những tài nguyên Azure không liên quan nếu dùng sai tên.

## 37. Kiểm tra và cấu hình table retention bằng CLI

Khi có table và table plan hỗ trợ cấu hình, các lệnh CLI Log Analytics workspace table có thể dùng để đọc/cập nhật settings.

~~~bash
RG="rg-observability-lab"
LAW="law-observability-lab"

az monitor log-analytics workspace table list \
  --resource-group "$RG" \
  --workspace-name "$LAW" \
  --query "[].{name:name,plan:plan,interactive:retentionInDays,total:totalRetentionInDays}" \
  -o table
~~~

Ví dụ **minh họa cách yêu cầu thay đổi** cho một bảng hỗ trợ retention:

~~~bash
az monitor log-analytics workspace table update \
  --resource-group "$RG" \
  --workspace-name "$LAW" \
  --name AppTraces \
  --retention-time 30 \
  --total-retention-time 180
~~~

### 37.1. Ràng buộc quan trọng

- Table **AppTraces** phải tồn tại trong workspace.
- Bảng phải hỗ trợ retention và plan settings được yêu cầu.
- Cần quyền quản trị phù hợp trên workspace.
- CLI/API version có thể thay đổi tên flags và giới hạn.
- Giảm retention ở hệ thống đang có dữ liệu có thể dẫn đến xóa.
- Con số 30/180 là policy giả định cho lab.

**Không chạy lệnh update trên production mà chưa review chính sách lưu giữ, độ tuổi dữ liệu, legal hold và approval.**

### 37.2. Readback sau khi đổi

~~~bash
az monitor log-analytics workspace table show \
  --resource-group "$RG" \
  --workspace-name "$LAW" \
  --name AppTraces \
  -o json
~~~

Đối chiếu **plan**, **retentionInDays**, **totalRetentionInDays**, table name và effective settings. Nếu bảng không hỗ trợ override, dừng và báo blocker; không tự chọn table khác để “vượt” kiểm tra.

### 37.3. Không chỉnh retention bằng một dashboard setting duy nhất

Một workbook/dashboard có thể phản ánh cấu hình mong muốn, không phải resource state thật. Khi audit, đọc setting trên Azure resource hoặc API và lưu evidence theo change record.

## 38. Infrastructure as Code: baseline workspace bằng Bicep

Một Bicep resource minh họa:

~~~bicep
param location string = resourceGroup().location
param workspaceName string = 'law-observability-lab'

resource law 'Microsoft.OperationalInsights/workspaces@2022-10-01' = {
  name: workspaceName
  location: location
  properties: {
    sku: {
      name: 'PerGB2018'
    }
    retentionInDays: 30
  }
}

output workspaceResourceId string = law.id
~~~

### 38.1. Chú ý API version

API version ở ví dụ là một contract minh họa, không khẳng định mới nhất hoặc hỗ trợ mọi tính năng tại thời điểm chạy. **Trước triển khai phải kiểm tra schema ARM/Bicep và region capability**; điều chỉnh version theo policy tổ chức.

### 38.2. DCR và diagnostic settings cũng là IaC resources

Sau workspace, một hệ thống vận hành hoàn chỉnh còn cần khai báo:

- DCR/associations cho AMA.
- Diagnostic settings ở từng resource.
- Application Insights workspace-based linkage nếu dùng.
- RBAC assignments và network/private-link resources.
- Table retention/plan policies theo API hỗ trợ.
- Alert rules, action groups, workbooks.
- Budgets/tags và monitoring of monitoring.

### 38.3. Table retention trong release phải có change control

Vì thay đổi retention có thể khiến dữ liệu không truy vấn được hoặc hết hạn, cần tách approval cho retention policy so với thay đổi Java app hàng ngày. IaC drift detection cần phân biệt người vận hành đổi cấu hình khẩn cấp có lý do với drift không được phê duyệt.

### 38.4. Không coi IaC state như bằng chứng đã thu log

IaC có thể tạo DCR đúng resource nhưng collector offline hoặc permissions thiếu. Cần synthetic event + KQL readback để xác minh pipeline end-to-end.

## 39. Theo dõi chính workspace và ingestion pipeline

Đây là **observability of observability**: nếu collector chết, người vận hành vẫn cần biết trước khi có sự cố lớn.

### 39.1. Các health signals

| Tín hiệu | Diễn giải |
|---|---|
| Latest event timestamp theo nguồn | Nguồn có còn gửi dữ liệu? |
| Ingestion delay p95 | Log có đến trễ? |
| Collector/AMA health | Agent còn kết nối và DCR đúng? |
| Number of records theo category | Event count có bất thường giảm? |
| Error/retry/drop counters | Có mất dữ liệu trong pipeline? |
| Workspace ingestion volume | Volume có tăng đột biến? |
| Table schema changes | Pipeline transform/SDK có làm hỏng KQL? |
| Query/alert execution failures | Alert có còn hoạt động? |
| Export destination health | Chứng cứ dài hạn có đang được ghi? |
| Cost daily estimate | Có vượt budget? |

### 39.2. Missing-data alert

Nếu payment-worker bình thường luôn gửi heartbeat/synthetic event mỗi vài phút, cảnh báo khi mất tín hiệu hơn 15 phút có thể phát hiện pipeline hỏng. Cẩn thận phân biệt **ứng dụng thật sự không phát sự kiện** với **pipeline mất dữ liệu**.

### 39.3. Ngăn blind spot

Nếu alert về lỗi ingestion cũng phụ thuộc chính workspace đang mất dữ liệu, nó có thể không chạy. Cân nhắc health signal độc lập (Azure metrics/agent health/resource alerts, external synthetic checks hoặc hệ giám sát thứ hai) cho những hệ thống quan trọng.

### 39.4. Noisy logging cũng là sự cố vận hành

Một exception loop khiến logs tăng gấp 50 lần có thể tiêu hết budget và làm mất tín hiệu quan trọng trong noise. Dùng rate-limited loggers, dedup/sampling phù hợp và kiểm soát retry storm tại nguồn.

## 40. Security operations và lưu giữ log ứng phó sự cố

Một quy trình điều tra cần xác định rõ:

1. **Khoảng thời gian** cần giữ/truy vấn.
2. **Nguồn chứng cứ** và mức độ đầy đủ.
3. **Quyền** của người điều tra.
4. **Cách bảo toàn** bằng chứng trước khi retention expiration.
5. **Khả năng export** và integrity verification.
6. **Mức độ privacy** khi chia sẻ incident data.
7. **Kế hoạch xóa** sau khi legal hold/retention obligations kết thúc.

### 40.1. Khi xảy ra sự cố ngay sát ngày hết hạn

Đội điều tra phải biết cửa sổ interactive/long-term và quy trình bảo toàn/export được phê duyệt. Tăng retention khẩn cấp có thể yêu cầu quyền, thời gian áp dụng và chi phí; không tự giả định có thể “hồi sinh” dữ liệu đã hết hạn.

### 40.2. Log completeness là chất lượng bằng chứng

Có một vài events chưa chứng minh đầy đủ chuỗi hành động. Đối soát với AzureActivity, Key Vault audit, AppRequests, Service Bus telemetry hoặc nguồn khác tùy incident; mô tả rõ khoảng trống.

### 40.3. Quyền xem và quyền xuất

Xuất log ra file CSV/screenshot là một hành động lan truyền dữ liệu; cần quản lý người nhận, retention và audit. Có thể có những điều khoản hạn chế gửi logs ra ngoài tenant hoặc region.

### 40.4. Tài liệu hóa runbook tìm log cũ

Ghi những steps xem table settings, chọn query time range, tạo search/restore job khi được hỗ trợ, lấy kết quả, xác nhận nguồn và dọn tài nguyên tạm sau điều tra.
## 41. Runbook: không thấy log trong Workspace

**Tình huống:** orders-api báo lỗi HTTP 500 nhưng trong Log Analytics không có AppTraces tương ứng.

### Bước 1 — Xác nhận sự kiện được phát

Kiểm tra logger/tracer ở ứng dụng, log level, sampling và container stdout. Có phải bản ghi bị bỏ ở source do filter hoặc quá hạn retention trên host?

### Bước 2 — Xác nhận đúng nguồn/table

- Ứng dụng dùng Application Insights workspace-based hay custom collector?
- Logs đi vào **AppTraces**, **ContainerLogV2**, **AzureDiagnostics** hay custom table khác?
- Workspace ID/region có phải nơi người điều tra đang query?
- Có DCR hoặc diagnostic setting mới đổi destination không?

### Bước 3 — Kiểm tra thời gian

So sánh **TimeGenerated**, UTC offset, ingestion time và query time filter. Agent có thể đẩy logs đến trễ sau khi offline.

### Bước 4 — Kiểm tra collector và cấu hình

AMA/DCR association, Container Insights config, OpenTelemetry exporter, service identity, network/DNS/firewall và logs ingestion endpoint. Với diagnostics, xác minh category đã bật và đúng resource ID.

### Bước 5 — Kiểm tra quyền KQL

Người dùng có thể thiếu quyền query workspace/table hoặc đang ở resource context không bao gồm logs đó. Test bằng một principal được cấp quyền phù hợp, không tự nâng quyền rộng để chữa lỗi.

### Bước 6 — Kiểm tra volume và drop/retry

Collector có errors/queue full? Workspace/data collection API có throttling? Có transform lọc mất severity/category hoặc đổi schema khiến query không match?

### Bước 7 — Tạo synthetic event an toàn

Gửi một log giả với EventId riêng, không có PII, từ đúng nguồn; ghi UTC timestamp, tra theo table/correlation ID. Synthetic event không xuất hiện thì tiếp tục khoanh pipeline.

### Bước 8 — Ghi incident

Mô tả khoảng thời gian mất log, mức độ dữ liệu bị ảnh hưởng, nguyên nhân, cách khôi phục, liệu dữ liệu cũ có backfill được không và những điều tra nào có blind spot. **Không nói "không có lỗi" chỉ vì không có logs.**

## 42. Runbook: ingestion volume và chi phí tăng đột biến

**Tình huống:** Workspace từ 10 GB/ngày lên 70 GB/ngày sau một release.

### Bước 1 — Kiểm tra tín hiệu

Đối chiếu Azure Monitor usage/billing metrics và Cost Management, theo ngày/giờ, workspace/table. Loại trừ khác biệt về số ngày, delayed ingestion và billing windows.

### Bước 2 — Tìm nguồn tăng

Top tables, Azure resource IDs, services, environments, severity categories. Có bật diagnostic setting mới hoặc duplicate collector không?

### Bước 3 — Kiểm tra thay đổi ứng dụng

Debug/trace level bị bật trong production, exception retry loop, ghi request bodies lớn, duplicate OpenTelemetry exporters, container restarts quá nhiều hoặc batch replay.

### Bước 4 — Cắt giảm có kiểm soát

Giảm logging noise ở nguồn, điều chỉnh sampling cho application diagnostics, sửa retry loop, điều chỉnh DCR filter ở supported streams. **Không tự tắt audit/security category** hoặc retention đã được legal/compliance phê duyệt.

### Bước 5 — Soát table plan/retention

Có table plan phù hợp cho high-volume data không? Đã có query/alert dependencies trên bảng đó chưa? Nếu định đổi retention, cần change approval và đánh giá dữ liệu lịch sử.

### Bước 6 — Đặt guardrails

Daily budget alerts, ingestion thresholds, review owner và policy-as-code/IaC drift checks. Một ingestion cap nếu được cấu hình phải tính tới nguy cơ **mất dữ liệu quan trọng**, không nên dùng như biện pháp bảo mật thay cho logging policy.

### Bước 7 — Hậu kiểm

Đo lại GB/ngày, operational visibility, alert coverage, errors và cost estimate. Chỉ công nhận tối ưu nếu những signals cần thiết vẫn đầy đủ và điều tra sự cố vẫn thực hiện được.

## 43. Runbook: phải giảm thời hạn lưu giữ

Một yêu cầu giảm retention từ 180 xuống 30 ngày có thể ảnh hưởng dữ liệu và điều tra pháp lý.

1. Xác minh **đúng workspace, table, region, owner**.
2. Đọc policy và regulatory/legal hold hiện hành.
3. Xác minh interactive retention, total retention và table plan thực tế.
4. Ước lượng dữ liệu nằm ngoài mốc mới, bao gồm case đang điều tra.
5. Xác nhận nơi lưu bản sao (exports, Storage, backups) và quyền xóa.
6. Phê duyệt thay đổi với SRE, security, privacy/legal và owner.
7. Chuẩn bị phương án rollback **trước khi dữ liệu bị hết hạn**; rollback cấu hình không tự khôi phục records đã xóa.
8. Thử trên lab/table đại diện khi khả thi.
9. Deploy bằng IaC/CLI được review, lưu activity ID/changelog.
10. Readback plan/interactive/total retention sau deploy.
11. Kiểm tra alerts, KQL, search/restore workflows và billing.
12. Tài liệu hóa thời điểm áp dụng và bằng chứng tuân thủ.

**Không tự ý sử dụng công cụ purge/xóa dữ liệu trên production**, vì purge có đặc tính và điều kiện riêng, không đồng nghĩa thay retention policy.

## 44. Lab 1: tạo Workspace và thu platform diagnostics

**Điều kiện:** dùng tài nguyên Azure lab được phép, tài khoản có chi phí được kiểm soát. Không bật categories chứa PII trên resource production chỉ để thử.

### A. Tạo Workspace

1. Chọn subscription và resource group lab.
2. Tạo Log Analytics Workspace trong region được chấp thuận.
3. Đặt default retention giả định cho lab theo giới hạn dịch vụ.
4. Ghi workspace resource ID, region, access control settings.
5. Cấp tối thiểu quyền đọc query cho test operator.
6. Ghi lại pricing SKU/cost budget.

### B. Bật Diagnostic settings

1. Chọn một resource lab có hỗ trợ diagnostic logs, chẳng hạn Key Vault lab hoặc Azure SQL lab.
2. Mở **Monitoring → Diagnostic settings**.
3. Xem các **log categories** thực được resource hỗ trợ.
4. Chỉ chọn category cần thử, destination là workspace lab.
5. Save và xác nhận setting gắn đúng resource.
6. Tạo một hành động thử phù hợp (không lộ secrets/PII).
7. Chờ ingestion theo đặc tính dịch vụ và kiểm tra table xuất hiện.

### C. KQL

Tùy schema/destination được sử dụng, thử tìm trong đúng table:

~~~kusto
AzureDiagnostics
| where TimeGenerated >= ago(2h)
| summarize Events = count() by Category
| order by Events desc
~~~

Chỉ dùng query này nếu category đang ghi vào **AzureDiagnostics**. Nếu dịch vụ xuất vào resource-specific table, đổi tên table/schema. Không coi truy vấn trả 0 là lỗi cho tới khi xác minh log source và ingestion.

### D. Kiểm chứng

| Kiểm tra | Kết quả cần ghi |
|---|---|
| Workspace ở đúng region | Actual region |
| Diagnostic setting đúng nguồn | Resource ID |
| Category enabled | Category name |
| Log table nhận event | Table name |
| First/last event UTC | Timestamp |
| Time delay | Thời gian đo |
| Permissions | Ai query được/không được |

### E. Cleanup

Tắt diagnostic setting thử nghiệm, dọn tài nguyên lab **chỉ khi được phép** và xem chi phí để không còn workspace/Storage/compute không cần thiết.

## 45. Lab 2: KQL, alert và đo ingestion

### A. Dữ liệu

Sử dụng workspace-based Application Insights cho ứng dụng lab hoặc một bảng logs đã có dữ liệu. Không tạo hàng triệu sự kiện thật.

### B. Ba câu query căn bản

**Tìm lỗi:**

~~~kusto
AppTraces
| where TimeGenerated >= ago(1d)
| where SeverityLevel >= 3
| summarize Errors = count() by bin(TimeGenerated, 1h)
| order by TimeGenerated asc
~~~

**Đo request p95:**

~~~kusto
AppRequests
| where TimeGenerated >= ago(1d)
| summarize Requests=count(),
            P95Ms=percentile(DurationMs, 95)
  by bin(TimeGenerated, 1h)
| order by TimeGenerated asc
~~~

**Ước lượng billed-size theo bảng:**

~~~kusto
AppTraces
| where TimeGenerated >= ago(1d)
| summarize ApproxGB =
    sum(_BilledSize) / 1024.0 / 1024.0 / 1024.0
~~~

Các queries yêu cầu tables/columns có thật. Nếu table không tồn tại, sử dụng table tương ứng nguồn đã bật; không tự thêm dummy dữ liệu production để “cho query có kết quả”.

### C. Alert

1. Chọn một metric hoặc scheduled KQL query được table plan hỗ trợ.
2. Thiết lập evaluation window, threshold, severity và action group test.
3. Tạo một synthetic error event an toàn trong môi trường lab.
4. Xác minh alert fires theo dự kiến, thông báo không chứa PII.
5. Dừng alert sau bài, tránh phát notification rác.

### D. Kết quả

Đo record counts, query latency, ingestion delay, p95 request latency, approximate volume và alert detection delay. So sánh timestamp event và khi sự kiện xuất hiện trên workspace.

## 46. Lab 3: mô phỏng chính sách retention theo bảng

### A. Xây ma trận chính sách mẫu

~~~text
Table              Interactive     Total
AppTraces          30 days         90 days
AppRequests        30 days         60 days
ContainerLogV2     30 days         30 days
Security audit     90 days         365 days
~~~

**Các số chỉ là yêu cầu minh họa.** Xác minh từng bảng có hỗ trợ các mức này và cách service hiện hành áp retention/plan.

### B. Kiểm tra các bảng

1. Mở Workspace → Tables.
2. Ghi table name, current plan, interactive và total retention.
3. Kiểm tra table capability/limits.
4. So sánh với yêu cầu và xác định gap.
5. Nếu table chưa tồn tại, không giả định có thể cấu hình ngay.
6. Xác định người có quyền approve/change.

### C. Thử trên lab

1. Chọn một table lab có dữ liệu giả, cho phép chỉnh retention.
2. Read current plan/retention bằng Portal hoặc CLI.
3. Thay một thông số **chỉ theo phương án đã phê duyệt**.
4. Readback và ghi trước/sau.
5. Kiểm tra query behavior/alerts.
6. Hoàn trả theo change plan nếu an toàn và chưa mất dữ liệu.
7. Không thử giảm retention bằng dữ liệu compliance thật.

### D. Điều tra lịch sử

Lập mô phỏng tình huống sự kiện đã nằm ngoài interactive period nhưng còn trong total retention. Viết các bước truy cập bằng search job/restore (nếu hỗ trợ) và ước lượng delay/chi phí. Không giả lập kết quả đã query được nếu không thật sự có dữ liệu/time horizon phù hợp.

### E. Kết luận

Mỗi nhóm nộp policy matrix kèm table capabilities, roles, ước lượng volume/GB và change approval record.

## 47. Lab 4: kiểm chứng quyền truy cập và bảo vệ chứng cứ

### A. RBAC

Tạo các test personas/identities được cấp quyền:

- Developer chỉ được xem application diagnostics phù hợp.
- SRE được query phạm vi vận hành.
- Security analyst được điều tra security logs.
- IaC identity được quản trị đúng scope.
- Unprivileged test identity không được query dữ liệu nhạy cảm.

Thử cả những truy cập **phải thành công** và **phải bị từ chối**. Cần kiểm tra workspace/resource query context đúng thiết kế.

### B. Data minimization

1. Cho ứng dụng phát một event giả với customer identifier dạng tokenized.
2. Kiểm tra log không chứa email/password/access token.
3. Nếu DCR transform hỗ trợ, thử lọc debug hoặc project fields trong lab.
4. Đối chiếu số events trước/sau.
5. Không áp dụng filtering khiến audit evidence bị mất.

### C. Evidence export

1. Chọn một audit event **giả**.
2. Xuất bản ghi/manifest theo phương thức được phép.
3. Đối chiếu source ID, timestamp, event count và checksum.
4. Nếu lab có Storage immutable policy được phê duyệt, thử retention policy theo tài nguyên riêng.
5. Kiểm tra quyền xem/download và cách dọn sau retention.
6. Ghi rõ việc lưu bản sao không tự thay retention trong Log Analytics.

### D. Cost and security review

Lập bảng tổng hợp ingest GB/ngày, table plan, total retention, xuất dữ liệu, access roles và những log đã được loại bỏ ở source. Đánh giá cân bằng: investigation coverage, privacy exposure và cost.

## 48. Checklist triển khai production

- [ ] Đã xác định owners và use cases cho từng nhóm log.
- [ ] Biết Azure resource nào sinh log và nguồn nào dùng DCR/AMA/Diagnostic settings/App Insights.
- [ ] Đã vẽ luồng ingest từ ứng dụng tới table.
- [ ] Có đối soát completeness và ingestion latency.
- [ ] Workspace topology phù hợp region, data residency và trust boundary.
- [ ] Dev/test/prod logs có quyền và ngân sách tách biệt hợp lý.
- [ ] Không tạo workspace riêng cho mỗi Pod vô cớ.
- [ ] Schema và correlation IDs thống nhất giữa services.
- [ ] Không log passwords, keys, bearer tokens, SAS URLs hoặc PII không cần thiết.
- [ ] Logging level và sampling được review cho từng category.
- [ ] Audit/security events quan trọng không bị sampling tùy tiện.
- [ ] Table plan Analytics/Basic/Auxiliary được chọn theo khả năng truy vấn/alert/retention thực.
- [ ] Đã kiểm tra per-table support/limits trước khi đổi plan.
- [ ] Workspace default retention đã được đọc và ghi nhận.
- [ ] Các table overrides/total retention đã được kiểm tra.
- [ ] Chính sách có interactive horizon và total horizon riêng.
- [ ] Có owner, căn cứ giữ, thời điểm review và quy trình xóa.
- [ ] Legal hold/compliance evidence không phụ thuộc một query log duy nhất.
- [ ] Nếu cần WORM, có export path và Azure Storage immutability policy phù hợp.
- [ ] Đã kiểm chứng dữ liệu xuất ra đầy đủ, schema và checksum.
- [ ] IAM phân biệt workspace readers, developers, security và admin.
- [ ] Resource-context access không bị nhầm thành row-level tenant isolation.
- [ ] Azure Monitor Private Link Scope/DCR/DCE/DNS được kiểm tra khi cần private networking.
- [ ] Managed identity có quyền ingest đúng scope, không có quyền quản trị thừa.
- [ ] DCR transformations chỉ dùng cho streams hỗ trợ và có regression tests.
- [ ] Diagnostic settings không bị duplicate ingestion không chủ đích.
- [ ] KQL queries giới hạn time/resource/table và không xuất PII tùy tiện.
- [ ] Scheduled alerts hỗ trợ plan/table và đã được test với synthetic events.
- [ ] Có alert khi data source mất log hoặc ingestion lag.
- [ ] Có health monitoring độc lập cho logging pipeline quan trọng.
- [ ] Có monitoring table-level volume và daily cost.
- [ ] Đã ước lượng peak logging burst và chi phí export/long-term search.
- [ ] Có budget/alerts và runbook xử lý ingestion spike.
- [ ] Retention changes dùng IaC, approvals và readback.
- [ ] Có backup/export trước khi giảm retention nếu policy yêu cầu.
- [ ] Không mặc định rollback IaC có thể phục hồi logs đã hết hạn.
- [ ] Có runbook khi mất log, query thất bại, 429/ingest delay hoặc thay schema.
- [ ] Có kiểm thử DR/retrieval dữ liệu cũ theo SLO và khả năng sản phẩm.
- [ ] Có cleanup an toàn cho lab và tách biệt dữ liệu production.

## 49. Câu hỏi tự kiểm tra

1. Azure Monitor và Log Analytics Workspace khác nhau ở vai trò nào?
2. Workspace table khác một file văn bản hay Azure Storage container thế nào?
3. Metrics, logs và distributed traces có thay thế nhau hoàn toàn không?
4. Vì sao chọn retention theo category thay vì đặt một số chung?
5. Interactive retention khác total retention ra sao?
6. Nếu interactive=30 ngày, total=180 ngày thì long-term period minh họa dài bao lâu?
7. Có chắc mọi table plan hỗ trợ query/alert như Analytics không?
8. Basic/Auxiliary có phù hợp security detections real-time không cần kiểm tra?
9. Tại sao giảm retention production có thể không đảo ngược?
10. Log Analytics total retention có tự tạo WORM/legal hold không?
11. Khi nào cần xuất log sang Azure Storage immutable storage?
12. Một workspace chung nhiều subscriptions có lợi và rủi ro gì?
13. Khi nào cần tách workspace theo region/trust boundary?
14. AzureActivity có chứa đầy đủ mọi lượt đọc dữ liệu Key Vault không?
15. Diagnostic settings khác Azure Monitor Agent/DCR thế nào?
16. DCR association đóng vai trò gì?
17. Ingestion-time transformation có chạy được mọi KQL query không?
18. Nếu tạo workspace nhưng chưa có DCR/diagnostic settings, có logs không?
19. Workspace-based Application Insights khác logging vào stdout như thế nào?
20. Vì sao phải chuẩn hóa correlationId và timestamps UTC?
21. Sampling application diagnostics khác sampling audit events thế nào?
22. Vì sao không log Authorization header hoặc SAS URL?
23. Resource-context query có mặc nhiên bảo vệ row-level tenantId không?
24. Azure management RBAC và log query permissions khác gì?
25. Một managed identity chỉ ingest logs cần quyền nào?
26. AMPLS và DCE có vai trò gì trong private logging scenarios?
27. Tại sao table AzureDiagnostics có thể không tồn tại dù diagnostic setting đã bật?
28. Query KQL cần lọc TimeGenerated sớm vì sao?
29. AppRequests có thể tính p95 latency bằng operator nào?
30. _BilledSize từ một table có bằng hóa đơn toàn workspace không?
31. TimeGenerated khác ingestion_time() có ý nghĩa gì?
32. Nếu logger có log nhưng workspace không có dữ liệu, nên kiểm tra những chặng nào?
33. Làm sao phát hiện collector chết trước khi có incident?
34. Vì sao monitoring pipeline không nên chỉ phụ thuộc chính pipeline đó?
35. Nếu ingestion tăng 7 lần sau release, bước điều tra đầu tiên là gì?
36. Chi phí retention khác chi phí ingestion/query/export như thế nào?
37. Những ai phải duyệt một thay đổi giảm retention cho security logs?
38. IaC apply thành công có chứng minh log stream healthy không?
39. Có nên chạy thử purge/retention reduction trên production để học không?
40. Thế nào là policy log hoàn chỉnh từ collection đến disposal?

## 50. Tổng kết

**Log Analytics Workspace** là nơi tổ chức và truy vấn dữ liệu log trong **Azure Monitor Logs**. Để xây dựng khả năng quan sát tốt, người vận hành phải hiểu **nguồn dữ liệu, đường đi của log, table schema, KQL, access control, alerting và mức độ đầy đủ của dữ liệu**. DCR/AMA, Diagnostic settings, workspace-based Application Insights và Logs Ingestion API là các đường ingest có mục tiêu và giới hạn khác nhau.

**Thiết kế lưu giữ log** bắt đầu từ phân loại dữ liệu và use cases: lỗi ứng dụng cần truy vấn nhanh, verbose telemetry có thể cần giữ ngắn, security/audit events có thể cần giữ lâu hơn và chặt chẽ hơn. Phải phân biệt **workspace default với table override**, **interactive/analytics retention với total/long-term retention**, đồng thời kiểm tra giới hạn của **Analytics, Basic và Auxiliary plans** trước khi áp dụng. Long-term retention không tự đồng nghĩa với bằng chứng bất biến; khi quy định đòi WORM/chain-of-custody cần thêm phương án chứng cứ thích hợp.

Một kiến trúc production phải có **least-privilege Entra RBAC, private networking khi cần, data minimization, KQL/alerts có kiểm soát, monitoring ingestion health, retention IaC với readback, dự báo chi phí và runbook khắc phục**. Đích cuối không phải lưu thật nhiều log mà là **đủ tín hiệu để phát hiện và điều tra, có thể truy xuất khi cần, bảo vệ đúng dữ liệu và không vượt ngân sách hoặc nghĩa vụ lưu giữ**.




