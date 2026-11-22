# Diagnostic setting và đích xuất dữ liệu giám sát

Giả sử một ứng dụng Spring Boot phục vụ đơn hàng chạy trên Azure App Service, sử dụng Azure SQL Database và Azure Key Vault. Khi hệ thống xuất hiện HTTP 500, nhóm SRE muốn biết **dịch vụ nào phát sinh lỗi, tài nguyên Azure có thay đổi cấu hình không, Key Vault có từ chối truy cập không và dữ liệu cần được lưu bao lâu để điều tra**. Azure Portal hiển thị một số biểu đồ sẵn có, nhưng các biểu đồ đó chưa tạo ra bộ nhật ký tập trung, chưa bảo đảm lưu được audit theo quy định và cũng chưa tự đẩy dữ liệu đến hệ thống SIEM.

**Azure Monitor diagnostic settings** (cấu hình chẩn đoán) giải quyết một phần quan trọng của bài toán: **chọn các loại nhật ký và metric được tài nguyên Azure hỗ trợ, rồi định tuyến chúng đến một hoặc nhiều đích** như Log Analytics workspace, Azure Storage, Azure Event Hubs hoặc tích hợp đối tác được hỗ trợ. Đây là **cơ chế xuất dữ liệu platform telemetry**, không phải công cụ tự sửa lỗi, công cụ alert, agent thu mọi file log hay nơi sinh ra những dữ liệu mà dịch vụ nguồn không cung cấp.

Bài **“Diagnostic setting và đích xuất dữ liệu giám sát”** thuộc chương **Giám sát và quan sát hệ thống** của module **CLOUD_PROVIDERS_AZURE**. Bài kết nối kiến thức về subscription, resource group, Microsoft Entra ID, mạng, compute, lưu trữ và dữ liệu với cách **thu thập, phân tích, bảo vệ, vận hành và kiểm soát chi phí dữ liệu quan sát** trong một kiến trúc ứng dụng Azure.

Sau khi học, bạn có thể:

- Phân biệt **resource logs, platform metrics, subscription Activity Log, application telemetry và guest OS logs**.
- Giải thích cấu trúc một diagnostic setting: **resource scope, categories/category groups, metrics, destination IDs và chế độ bảng Log Analytics**.
- Lựa chọn **Log Analytics, Storage Account, Event Hubs hoặc partner integration** theo mục tiêu điều tra, lưu giữ, streaming và governance.
- Hiểu quan hệ giữa **diagnostic settings, Data Collection Rules (DCR), Azure Monitor Agent (AMA), Application Insights và Azure Monitor alerts**.
- Cấu hình bằng **Azure Portal, Azure CLI** và cách biểu diễn qua **Bicep/IaC** mà không mở rộng quyền không cần thiết.
- Xác minh dữ liệu với **KQL, metrics, Storage và Event Hubs consumers**.
- Thiết kế **RBAC, data residency, Private Endpoint/firewall, mã hóa, retention, chi phí và độ tin cậy**.
- Điều tra những lỗi thường gặp như **chọn sai log category, sai resource ID, thiếu quyền đích, không thấy bảng KQL và routing không đến Event Hubs**.

> **Phạm vi:** Các ví dụ là mẫu hướng dẫn, không tạo hay thay đổi tài nguyên Azure khi soạn bài. Category names, category groups, loại metric hỗ trợ, bảng đích, CLI options và destination constraints **khác nhau theo resource provider và phiên bản dịch vụ**; luôn truy vấn khả năng thực tế của tài nguyên trước khi áp dụng.

## 1. Tại sao cần diagnostic settings?

Một resource trên Azure có thể phát ra **platform metrics** (ví dụ lượng requests, CPU/IO, số kết nối) và **resource logs** (ví dụ hoạt động data plane, audit, lỗi truy cập). Những tín hiệu này không giống nhật ký application do Spring Boot tự ghi.

### 1.1. Không phải mọi telemetry đều được chuyển đi tự động

| Câu hỏi | Nơi xuất phát | Nếu chưa cấu hình |
|---|---|---|
| Key Vault có yêu cầu truy cập secret bị từ chối không? | Key Vault resource logs/audit categories | Chưa chắc có dữ liệu ở Log Analytics workspace |
| App Service có HTTP 5xx từ platform/web server không? | App Service resource logs/metrics | Metrics có thể xem ở resource; logs chưa tập trung |
| Ai đã thay NSG hoặc xóa resource group? | Subscription Activity Log | Có lịch sử ở Azure; xuất/lưu dài hạn cần cấu hình phù hợp |
| Spring Boot lỗi `NullPointerException` ở class nào? | Application logs/traces | Diagnostic setting của App Service không tự instrument toàn bộ source code |
| VM Linux có file `/var/log/syslog` chứa sự kiện gì? | Guest OS syslog | Cần Azure Monitor Agent + DCR hoặc collector tương ứng |
| Backend API có trace p95 và dependency span không? | Application Insights/OpenTelemetry | Cần SDK/agent/instrumentation riêng |
| Azure SQL có spikes CPU hay deadlocks không? | Azure SQL platform metrics/resource logs và DB diagnostics | Chọn categories và cơ chế thu thập được hỗ trợ |

Diagnostic settings **định tuyến từ nguồn đã có**, không tự tạo mọi loại dữ liệu. Vì thế chọn đúng giải pháp thu thập quan trọng hơn việc “bật mọi checkbox”.

### 1.2. Mục tiêu kinh doanh và vận hành

- **Điều tra sự cố:** truy vấn logs theo tài nguyên, thời gian, operation, correlation ID.
- **Audit/compliance:** lưu những sự kiện cần thiết theo chính sách, có kiểm soát truy cập và retention.
- **Phát hiện bất thường:** stream telemetry đến pipeline phân tích hoặc SIEM.
- **Phân tích liên dịch vụ:** gom logs của App Service, Key Vault, Storage, SQL, networking.
- **Kiểm soát chi phí:** chỉ thu categories/metrics cần thiết, đặt retention và định tuyến hợp lý.
- **Khôi phục bằng chứng:** lưu archive có lifecycle và chính sách chống sửa/xóa khi cần.

**Một diagnostic setting có trạng thái tạo thành công không chứng minh hệ thống đang quan sát tốt.** Phải xác minh rằng nguồn thực sự phát event, đích nhận event, timestamps/bảng đúng và có người sử dụng dữ liệu đó để giám sát.

## 2. Kiến trúc Azure Monitor diagnostic settings

~~~mermaid
flowchart LR
    subgraph SRC[Azure data sources]
      APP[App Service]
      KV[Key Vault]
      DB[Azure SQL Database]
      NSG[Network resources]
    end
    APP --> DS[Diagnostic settings on source resource]
    KV --> DS
    DB --> DS
    NSG --> DS
    DS -->|Queryable logs| LA[(Log Analytics workspace)]
    DS -->|Retention / archive| STORAGE[(Azure Storage Account)]
    DS -->|Stream near-real-time| EH[Azure Event Hubs]
    DS -->|Supported integration| PARTNER[Partner solution]
    LA --> KQL[KQL / Workbooks / Alerts]
    STORAGE --> ARCHIVE[Lifecycle / audit archive]
    EH --> CONSUMERS[SIEM / Functions / stream consumers]
    DCR[Azure Monitor Agent + Data Collection Rule] --> LA
    APM[Application Insights / OpenTelemetry] --> LA
~~~

**Sơ đồ mang tính logic:** mỗi tài nguyên thông thường có **diagnostic setting gắn vào resource đó**; hình gom các cấu hình thành một nút để dễ nhìn. DCR/AMA và Application Insights nằm ở các **pipeline khác**; chúng không tự trở thành categories của một diagnostic setting.

### 2.1. Một diagnostic setting gồm những gì?

| Trường/khái niệm | Vai trò |
|---|---|
| **Resource scope** | Resource Azure phát logs/metrics; diagnostic setting là extension resource |
| **Name** | Tên cấu hình, ví dụ `diag-to-operations-law` |
| **Log categories** | Các loại nhật ký riêng mà provider hỗ trợ |
| **Category groups** | Nhóm như `allLogs`/`audit` khi provider hỗ trợ |
| **Metric categories** | Ví dụ `AllMetrics` nếu resource cho phép export qua diagnostic settings |
| **workspaceId** | Resource ID của Log Analytics workspace đích |
| **storageAccountId** | Resource ID của Azure Storage Account đích |
| **eventHubAuthorizationRuleId** | Resource ID của policy dùng để gửi Event Hubs |
| **eventHubName** | Tên hub đích khi sử dụng Event Hubs |
| **marketplacePartnerId** | Tích hợp partner phù hợp nếu khả dụng |
| **logAnalyticsDestinationType** | Chọn chế độ bảng resource-specific khi hỗ trợ |

**Không nhầm resource ID nguồn với resource ID đích.** Một cấu hình có thể trỏ đến nhiều destinations được hỗ trợ, nhưng phải xem từng destination nhận đúng loại logs/metrics và phép cấu hình hợp lệ. Trên nhiều Azure resources, dịch vụ cho phép tối đa **5 diagnostic settings trên một resource**; hãy xác minh giới hạn áp dụng và tránh tạo hàng chục cấu hình trùng lặp.

### 2.2. Diagnostic setting là đường dữ liệu, không phải bản sao metrics Explorer

Metric hiển thị trong Metrics Explorer **không đồng nghĩa** được export nguyên xi qua diagnostic settings. Có metric không hỗ trợ export, metric có dimensions khác nhau và dạng biểu diễn sau khi gửi workspace không giữ tất cả khả năng drill-down như API metrics gốc. Trước khi chọn export metric:

1. Kiểm tra metric/category thực sự hỗ trợ.
2. Đánh giá có cần dimensions (region, status code, operation) không.
3. So sánh sử dụng **metric alert trực tiếp** với xuất metric thành log.
4. Đặt mục tiêu retention và query, vì chuyển metric thành log có thể phát sinh ingestion cost.

### 2.3. Luồng phát, trễ và bản ghi trùng

~~~mermaid
sequenceDiagram
    participant SOURCE as Azure resource
    participant MON as Azure Monitor pipeline
    participant LA as Log Analytics
    participant EH as Event Hubs
    participant SIEM as Consumer
    SOURCE->>MON: Generate resource event
    MON->>MON: Apply enabled categories/settings
    par Deliver to destinations
      MON->>LA: Ingest supported record
    and
      MON->>EH: Publish diagnostic event
    end
    EH-->>SIEM: Consumer receives batch
    SIEM-->>SIEM: Validate / parse / deduplicate
~~~

Delivery **không bảo đảm zero latency hay exactly-once xuyên mọi destination**. Dữ liệu có thể đến trễ, khác timestamp xử lý, hoặc consumer Event Hubs phải xử lý lại sau retry. Không sử dụng diagnostic settings như transactional outbox cho một business event bắt buộc không được mất.

## 3. Phân biệt các loại dữ liệu trong Azure Monitor

### 3.1. Resource logs

Các events do chính resource provider phát ra, ví dụ:

- Azure Key Vault: operations/audit events theo categories được hỗ trợ.
- Azure Storage: hoạt động Blob/File/Queue/Table theo resource con và categories.
- Azure SQL Database: audit/errors/timeout/diagnostic categories theo database.
- Azure App Service: HTTP/application/web-server logs khi loại resource hỗ trợ.
- Azure Firewall và một số networking services: network/application threat/decision logs.

Tên category **không đồng nhất** giữa mọi loại resource. Không viết automation cứng `AuditEvent` cho mọi resource rồi tin rằng tất cả sẽ xuất audit logs.

### 3.2. Platform metrics

Metrics thường là chuỗi thời gian tổng hợp như:

~~~text
Time:       2026-11-20T09:00:00Z
Metric:     Requests
Aggregation: Total
Value:      1250
Dimensions: resource / region / status (if supported)
~~~

Metrics Explorer/Metric Alerts đọc platform metrics trực tiếp theo API. Nếu cần lưu/query như logs trong workspace hoặc stream sang pipeline khác, chọn export **chỉ khi diagnostic setting hỗ trợ metric category**. Không bật metric export nếu cùng câu hỏi có thể giải quyết bằng metric alerts không cần nhân bản dữ liệu.

### 3.3. Azure Activity Log

Activity Log ghi **control-plane** events, ví dụ tạo/xóa resource, thay role assignment hoặc cập nhật cấu hình. Đây là loại **subscription-level**; xuất Activity Log qua diagnostic setting ở **scope subscription**, không giả định chỉ cần bật logs của từng SQL Database sẽ thu được toàn bộ ai đã thay NSG trong subscription.

Một Activity Log event và một resource audit event khác nhau:

~~~text
Activity Log:
  User changes Key Vault network rules via ARM.

Key Vault resource audit log:
  Application attempts to read a secret.
~~~

Điều tra cần cả hai nếu muốn liên hệ thay đổi cấu hình và lỗi truy cập dữ liệu.

### 3.4. Microsoft Entra ID logs

Sign-in logs, audit logs và các events identity của Entra có **diagnostic settings/cấu hình xuất riêng tại Entra tenant scope** với quyền và licensing phù hợp. Không tự xuất Entra sign-in logs chỉ bằng việc tạo diagnostic setting trên một VM, database hoặc App Service.

### 3.5. Application Insights và OpenTelemetry

Để xem trace Java exception, HTTP dependencies hoặc custom business events, ứng dụng cần **Application Insights Java agent, Azure Monitor OpenTelemetry hoặc instrumentation tương ứng**. Azure App Service diagnostic settings có thể xuất platform logs, nhưng không thay việc instrument Spring Boot. Hai nguồn dữ liệu có thể được gửi vào cùng hoặc khác workspace theo kiến trúc.

### 3.6. Guest OS logs, VM Insights và DCR

Thu thập `Windows Event Logs`, Linux `syslog`, performance counters hoặc custom text logs của VM thường liên quan **Azure Monitor Agent + Data Collection Rule (DCR)**, không phải bật một category tùy ý trong diagnostic settings của VM. Một resource có thể vừa có diagnostic settings cho platform signals, vừa có AMA/DCR cho guest OS signals.

### 3.7. Công cụ nào phù hợp với mục tiêu nào?

| Mục tiêu | Cơ chế ưu tiên |
|---|---|
| Azure SQL/Key Vault resource audit logs | Diagnostic setting category phù hợp |
| Subscription resource change events | Activity Log export ở subscription |
| Linux syslog/Windows Event Logs | AMA + DCR |
| Spring Boot application traces/dependencies | Application Insights/OpenTelemetry |
| Alert CPU vượt ngưỡng ngay | Azure Monitor metric alert |
| Truy vấn lỗi/audit tập trung theo KQL | Log Analytics workspace |
| Lưu archive có lifecycle/immutability | Diagnostic setting → Storage (khi hỗ trợ) |
| Streaming đến SIEM/custom processor | Diagnostic setting → Event Hubs |

**Nhiều công cụ có thể dùng đồng thời**; mục tiêu là có hợp đồng dữ liệu và ownership rõ, không bật mọi thứ ở mọi nơi.

## 4. Chọn đích xuất dữ liệu: bảng quyết định

| Đích | Mục đích chính | Ưu điểm | Giới hạn cần nhớ |
|---|---|---|---|
| **Log Analytics workspace** | Điều tra KQL, dashboards, log alerts | Query, join, RBAC/retention, Azure Monitor integration | Ingestion/query/retention cost, schema/table khác nhau |
| **Azure Storage Account** | Archive, giữ lâu, compliance | Lifecycle, blob access tiers, immutability khi cấu hình | Không phải KQL workspace; cần parser/analytics riêng để đọc |
| **Azure Event Hubs** | Streaming đến SIEM/processing | Consumer groups, buffering, event processing | Quota/throughput, consumer lag, retry, retention |
| **Partner solution** | Tích hợp hệ giám sát của bên thứ ba | Hợp nhất quy trình đang dùng | Availability/tính năng/permission/giá theo partner |

### 4.1. Ba câu hỏi chọn đích

**Bạn cần truy vấn ngay bằng KQL?** Chọn Log Analytics. **Bạn cần giữ log thô dài hạn?** Xem Storage và lifecycle/immutability. **Bạn cần pipeline SIEM gần real-time?** Xem Event Hubs, cùng tiêu chí lag và consumer health.

Ví dụ chính sách:

~~~text
Critical audit:
  Log Analytics for recent incident investigation.
  Storage Account with lifecycle and protected retention for archive.

Operational network events:
  Log Analytics for KQL and alerts.
  Event Hubs for central SIEM/stream processing.

Noisy debug categories:
  Export only if value, sampling, owner and budget justify them.
~~~

Không phải mọi service/category cho phép đúng tổ hợp này; cần kiểm tra hỗ trợ. **Xuất đến hai đích không phải miễn phí**, và không tự tạo backup độc lập nếu cả hai đích cùng bị xóa bởi một account quyền quá cao.

### 4.2. Chọn Log Analytics khi nào?

- SRE thường xuyên truy vấn trong 7–90 ngày gần đây.
- Cần KQL joins theo `_ResourceId`, category, operation, correlation/timestamp.
- Có workbooks và log alerts.
- Có RBAC/query access và data classification phù hợp.

Không dùng Log Analytics như transactional primary database. Query result và ingestion có thể có delay; SLO realtime/control loop không được dựa độc nhất vào nó.

### 4.3. Chọn Storage khi nào?

- Audit/archive cần retention dài hơn query hot window.
- Cần giảm chi phí truy vấn dữ liệu cũ bằng việc đọc có chọn lọc.
- Có policy immutable/WORM, lifecycle, storage ownership và eDiscovery.
- Tổ chức có pipeline đọc Blob và parse diagnostic records khi cần.

**Storage raw export không tự có index KQL**. Nếu sau 2 năm mới cần điều tra, phải có công cụ tìm đúng blob/time partition và xử lý schema cũ.

### 4.4. Chọn Event Hubs khi nào?

- SIEM nhận events trong thời gian ngắn.
- Cần enrich/route/filter events qua Function, stream processor hoặc consumer tùy chỉnh.
- Có owner quản lý partitions, throughput, retention, consumer groups và replay.

Một consumer chậm có thể làm dữ liệu Event Hubs hết retention; đừng hiểu “đã xuất Event Hubs” là archive vĩnh viễn.

### 4.5. Chọn partner khi nào?

Tổ chức có nền tảng observability/SIEM đã chuẩn hóa và Azure Monitor hỗ trợ tích hợp cụ thể. Kiểm tra **provider/region/cost/permission/network support**, điều khoản dữ liệu bên thứ ba, retention ở partner và quy trình khôi phục nếu tích hợp dừng.

## 5. Categories và category groups: chọn dữ liệu nào được xuất

Mỗi Azure resource provider quyết định **log categories** và **metric categories** mà resource hỗ trợ. Một Azure Key Vault có danh sách khác Azure SQL Database; một resource con của Storage có danh sách khác Storage Account cha.

### 5.1. Category không phải log level của ứng dụng

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| **Log category** | Một loại resource log do provider phát | `AuditEvent` tại Key Vault, khi category đó khả dụng |
| **Category group** | Nhóm categories được provider cung cấp | `allLogs` hoặc `audit` nếu resource hỗ trợ |
| **Metric category** | Nhóm metrics có thể xuất | `AllMetrics` khi khả dụng |
| **App log severity** | Mức độ log do ứng dụng ghi | `ERROR`/`WARN` của Spring Boot, không mặc nhiên là resource diagnostic category |

Từ `allLogs` không có nghĩa “mọi loại dữ liệu trên Azure”. Nó đại diện **những resource log categories được nhóm đó bao phủ ở đúng resource/provider**. Nó không tự lấy Entra sign-ins, VM guest syslog, application traces hay các metrics không được hỗ trợ.

### 5.2. Khám phá thay vì đoán tên

Quy trình đúng trước khi áp dụng:

1. Xác định **chính xác resource ID** nguồn, gồm cả child-resource nếu cần.
2. Hỏi Azure Monitor về **supported categories/categories groups** của resource đó.
3. So sánh categories với nhu cầu bảo mật, incident và business.
4. Chọn group `audit` khi chỉ cần audit và resource hỗ trợ; chọn `allLogs` khi nhu cầu đủ rộng/có budget.
5. Cấu hình `AllMetrics` **chỉ khi được liệt kê và có mục đích cụ thể**.
6. Đọc lại cấu hình sau apply và xác minh ít nhất một record/metric ở destination.

Lưu ý: category group có thể thay đổi khi provider thêm category mới; đây là lợi ích của `allLogs` về phạm vi tương lai nhưng cũng là rủi ro **chi phí/PII** thay đổi ngoài dự kiến. Nếu cần governance cố định, theo dõi category catalog và chỉ bật categories cần thiết.

### 5.3. Chọn `audit` hay `allLogs`?

Ví dụ Key Vault:

~~~text
Goal A: audit access to secrets/keys/certificates
  → Discover audit category/group.
  → Enable supported audit logs to central workspace.

Goal B: broader operational diagnostics
  → Discover all supported resource log categories.
  → Assess volume, sensitivity, cost, retention.
  → Enable allLogs only if necessary and supported.
~~~

**Không mặc định hai group luôn có trên mọi tài nguyên**. Nếu resource chỉ liệt kê các categories riêng, dùng categories đó thay vì gửi một group không hợp lệ.

### 5.4. Chọn metrics khác logs thế nào?

Metric `AllMetrics` có thể xuất các metric types được hỗ trợ ở resource, nhưng không phải tất cả metrics trong Azure Monitor đều được xuất qua diagnostic settings với mọi dimensions/aggregations. Nếu mục tiêu là báo động CPU cao:

~~~text
Preferred simple path:
  Azure Monitor metric alert directly on supported metric.

If analytics/history/export is required:
  Confirm diagnostic metric export support,
  enable category and validate destination schema.
~~~

Đừng dùng **metric-to-log export** như cơ chế duy nhất cho cảnh báo cần latency thấp nếu metric alert trực tiếp đáp ứng tốt hơn.

## 6. Log Analytics: workspace, bảng và KQL

**Log Analytics workspace** là đích để ingest logs theo cơ chế Azure Monitor Logs và truy vấn bằng KQL. Một tài nguyên phát logs không đồng nghĩa tự sinh bảng ngay khi bạn tạo workspace.

### 6.1. Workspace là phạm vi vận hành và dữ liệu

Trước khi dùng workspace làm đích, quyết định:

- **Environment:** prod và non-prod dùng chung hay tách?
- **Tenant/subscription:** ai có quyền ingest/query? Cross-subscription scenarios được cho phép trong điều kiện gì?
- **Region/data residency:** dữ liệu lưu ở đâu, yêu cầu compliance/cross-region?
- **Retention và archival:** giữ dữ liệu tương tác bao lâu, cần long-term retention như thế nào?
- **RBAC/table access:** SRE, security, developer, audit team thấy bảng nào?
- **Budget:** data ingestion, retention, query và alerts.
- **Query workload:** dashboard real-time, forensic investigation hay ít truy vấn.

Tách workspace theo **môi trường/boundary** khi có lý do compliance hoặc quyền, nhưng chia nhỏ quá mức khiến correlation khó, nhiều nơi phải theo dõi và tăng overhead. Không có một thiết kế workspace duy nhất đúng cho mọi tổ chức.

### 6.2. Legacy AzureDiagnostics và resource-specific tables

Một số diagnostic settings có tùy chọn **destination table mode** cho Log Analytics:

| Chế độ | Kết quả | Khi lưu ý |
|---|---|---|
| **Azure diagnostics** | Các records của nhiều resource providers có thể vào bảng chung `AzureDiagnostics` | Schema rộng/sparse, query thường lọc Category/ResourceProvider |
| **Resource specific** | Records đi vào **các bảng chuyên biệt** nếu resource/provider hỗ trợ | Query rõ schema hơn, phải biết table name thực |

Trong ARM/Bicep, lựa chọn resource-specific có thể dùng:

~~~json
{
  "logAnalyticsDestinationType": "Dedicated"
}
~~~

**Không phải mọi resource/provider/loại log đều hỗ trợ Dedicated.** Chọn resource-specific không có nghĩa tất cả log categories sẽ luôn có một bảng mới tự đặt tên. Tra danh sách Azure Monitor resource log table mappings và xác minh **tables đã nhận data**. Đối với logs Activity, metrics hoặc Entra, tên bảng có thể khác; không cố query `AzureDiagnostics` cho mọi thứ.

### 6.3. KQL ví dụ trên `AzureDiagnostics`

Chỉ chạy khi workspace **đã nhận logs vào bảng này**:

~~~kusto
AzureDiagnostics
| where TimeGenerated > ago(24h)
| summarize Events=count()
    by ResourceProvider, Category
| order by Events desc
~~~

Để xem events của một resource:

~~~kusto
let SourceResourceId =
  "/subscriptions/<sub-id>/resourceGroups/<rg>/providers/Microsoft.KeyVault/vaults/<vault>";
AzureDiagnostics
| where TimeGenerated between (ago(2h) .. now())
| where _ResourceId =~ SourceResourceId
| project TimeGenerated, _ResourceId, ResourceProvider, Category,
          OperationName, ResultType
| top 100 by TimeGenerated desc
~~~

Tên cột tùy schema/provider. `OperationName`/`ResultType` có thể tồn tại ở một số records nhưng không phải mọi bảng đều có; hãy xem schema trước. `<sub-id>` là placeholder, không phải URL/ID thực. `=~` so sánh chuỗi **không phân biệt hoa/thường**, phù hợp khi resource IDs được biểu diễn khác case; tốt nhất vẫn dùng ID chuẩn.

### 6.4. Ví dụ resource-specific table

Với một resource/provider có bảng chuyên biệt, tên như `KeyVaultAuditEvents` chỉ là **ví dụ cho tình huống đã được xác nhận**:

~~~kusto
KeyVaultAuditEvents
| where TimeGenerated > ago(1h)
| summarize Events=count() by OperationName, ResultType
| order by Events desc
~~~

**Query này chỉ hợp lệ nếu workspace đã có đúng bảng và columns đó.** Nếu dữ liệu ở `AzureDiagnostics` hoặc khác bảng chuyên biệt, phải đổi query theo actual schema. KQL không thể truy vấn một bảng chưa được tạo chỉ vì đã tạo diagnostic setting.

### 6.5. Ví dụ platform metrics được xuất vào workspace

Một số trường hợp xuất metrics có thể truy vấn bảng `AzureMetrics`:

~~~kusto
AzureMetrics
| where TimeGenerated > ago(1d)
| summarize Samples=count() by MetricName
| order by Samples desc
~~~

Đây là ví dụ **chỉ khi Metric diagnostic export và bảng `AzureMetrics` thực sự khả dụng**. Nó không thay metric alert, và các dimensions/aggregations trong export có thể khác metric APIs. Không khẳng định cứ bật `AllMetrics` là mọi metric đều có trong `AzureMetrics`.

### 6.6. Activity Log ở workspace

Subscription Activity Log khi được xuất phù hợp có thể xuất hiện trong bảng `AzureActivity`:

~~~kusto
AzureActivity
| where TimeGenerated > ago(7d)
| summarize Changes=count() by OperationNameValue, ActivityStatusValue
| top 20 by Changes desc
~~~

**Đây là Activity Log**, không phải resource log của Key Vault, và cần **subscription-level diagnostic setting**. Tên bảng/columns được kiểm tra trong workspace trước khi dùng cho automation.

### 6.7. Bảng chưa xuất hiện không có nghĩa diagnostic setting hỏng ngay

Có thể do:

1. Chưa có event nào thuộc category đó.
2. Dữ liệu đang chờ ingestion, query quá sớm.
3. Chọn workspace khác hoặc quyền KQL không nhìn được bảng.
4. Log Analytics destination/table mode khác kỳ vọng.
5. Resource category/diagnostic setting không có hiệu lực hoặc nguồn sai scope.
6. Query sử dụng time range/resource ID sai.

Hãy tạo **sự kiện test hợp lệ, ít rủi ro** trên resource lab rồi đo từ event time đến ingest time. Không phát sinh sự cố bảo mật hoặc xóa resource production chỉ để ép một log xuất hiện.

## 7. Storage Account: lưu giữ, lifecycle và audit archive

Diagnostic setting có thể gửi **logs/metrics được hỗ trợ** vào Azure Storage để lưu lâu hơn, phục vụ audit, tra cứu hay reprocessing. Azure Monitor thường ghi dưới dạng blobs với cấu trúc theo service/category/time; **không giả định đúng một file CSV cho mỗi sự kiện**.

### 7.1. Những quyết định cần thiết

| Quyết định | Câu hỏi |
|---|---|
| Storage account | Dùng tài khoản riêng cho audit hay chung với dữ liệu ứng dụng? |
| Region | Đích có phải cùng region với resource nguồn theo yêu cầu dịch vụ? |
| Network access | Azure Monitor có thể ghi khi storage firewall/private networking đang bật không? |
| Redundancy | LRS/ZRS/GRS theo RPO và data residency? |
| Lifecycle | Hot → Cool/Cold/Archive/Delete sau bao lâu? |
| Immutability | Audit cần WORM/retention lock/legal hold không? |
| Encryption | Microsoft-managed/customer-managed keys theo chính sách? |
| Access control | Ai được liệt kê/download/xóa blobs? |
| Monitoring | Có biết export ngừng hoặc storage hết quota không? |

### 7.2. File format và partitioning

Data export có thể tạo containers/log paths theo category và time. Một mô hình logic:

~~~text
<storage-account>/
  diagnostic-data/
    <resource-type>/
      <resource-id>/
        <log-category>/
          yyyy/MM/dd/HH/
            <hourly or batched records>
~~~

**Đây không phải path mặc định chính xác của Azure Monitor.** Đường dẫn thực phụ thuộc dịch vụ/đích; thường có tên container theo category và time partitions do dịch vụ tạo. Hãy kiểm tra blobs thật bằng Storage Explorer/SDK và viết parser theo envelope/schema được phát ra; đừng hardcode mẫu minh họa rồi chạy cleanup vào path nhầm.

### 7.3. Lifecycle và retention

Một phương án minh họa:

~~~text
First 30 days:  hot/cool as required for occasional reads
Days 31–365:   lower-access tier if compatible with read needs
After 365d:    remove only when policy/legal holds permit
~~~

Các khoảng là **giả định học tập**, không phải nghĩa vụ pháp lý mặc định. Trước khi bật lifecycle auto-delete, xem retention, legal hold, recovery procedure và những khoản phí truy xuất/tier chuyển đổi. Với archive, truy cập có thể cần rehydrate và tạo độ trễ đáng kể; nếu SRE cần truy vấn trong vài giây, Storage archive không thể thay Log Analytics hot table.

### 7.4. Immutability và quyền xóa

Nếu audit cần chống sửa/xóa, dùng **immutable blob storage (WORM)**, policy/retention lock và RBAC phù hợp. Nhưng:

- Kích hoạt policy sai có thể khiến không thể dọn data trước ngày hết hạn.
- Người có quyền lớn trên subscription/storage có thể ảnh hưởng các cấu hình khác, cần separation of duties.
- Encryption không đồng nghĩa immutability.
- Data duplication ở những đích khác vẫn cần kiểm soát.
- Không thử khóa retention vĩnh viễn trên storage production trong lab.

### 7.5. Storage network và trusted services

Khi bật Storage firewall/Private Endpoint, diagnostic export có thể cần đường cho **Azure Monitor platform service** theo cơ chế trusted-service exception/permission được sản phẩm hỗ trợ. Private Endpoint cho ứng dụng **không tự bảo đảm** hệ thống diagnostic pipeline có thể ghi vào storage. Phải kiểm tra **network rules, trusted Microsoft services setting, resource access và region requirements** cụ thể, không chuyển thành public access cho toàn Internet.

### 7.6. Test archive có khả dụng thật không?

Một bản audit có giá trị khi có thể **tìm và đọc lại**:

1. Phát một event hợp lệ trên resource lab.
2. Chờ export và kiểm tra container/time partition.
3. Đọc JSON/envelope, kiểm tra event time, resource ID và category.
4. Test quyền **read-only archive reader**.
5. Test query/parse một khoảng giờ nhiều files.
6. Test lifecycle/restore trên storage thử nghiệm theo approval.

Không tuyên bố lưu trữ thành công chỉ dựa vào storage account tồn tại.

## 8. Event Hubs: streaming logs đến SIEM hoặc pipeline

Event Hubs làm nhiệm vụ **tiếp nhận sự kiện và phân phối đến consumers** với throughput, retention và replay theo cấu hình. Diagnostic setting publish các records được chọn; consumer đọc thông qua consumer group/partition offsets.

### 8.1. Luồng Event Hubs

~~~mermaid
flowchart LR
    DB[Azure SQL / Key Vault / Firewall resource] --> DS[Diagnostic setting]
    DS --> EH[Event Hubs namespace and hub]
    EH --> S1[SIEM consumer group]
    EH --> S2[Analytics consumer group]
    S1 --> ALERTS[Detection rules / incidents]
    S2 --> STORE[Data lake / ADX / other sink]
    OPS[Operations] -. Monitor lag / throttling .-> EH
~~~

**Consumers không phải destinations của diagnostic setting**. Diagnostic setting chỉ gửi đến Event Hubs; để có alert trên SIEM hoặc dữ liệu ở Data Lake/ADX, cần consumer/connector cấu hình riêng.

### 8.2. Cần chuẩn bị gì?

- **Event Hubs namespace + event hub** theo throughput/partition requirements.
- **Authorization rule** có quyền phù hợp để Azure Monitor diagnostic setting publish; permission requirements phụ thuộc cơ chế/configuration. Không dùng RootManageSharedAccessKey tùy tiện.
- Namespace/hub ở **region hợp lệ** so với resource nguồn.
- Firewall/Private Endpoint/trusted service configuration cho diagnostic delivery nếu bật restricted networking.
- Dedicated **consumer group cho từng ứng dụng tiêu thụ**, checkpoint store và replay plan.
- Retention đủ lớn so với consumer outage và ingestion lag.
- Alert throttling/backlog/quota, kiểm tra chi phí Event Hubs và consumer.

Nếu provider/portal yêu cầu policy có quyền `Manage`/`Send`/`Listen` để thao tác diagnostic configuration, phải làm theo hợp đồng quyền Azure Monitor hiện hành và review security; không đánh đồng chính sách quản lý namespace với credential mà SIEM consumer cần. Tách **publisher access** và **consumer listen access** khi tính năng/quy trình cho phép.

### 8.3. Định dạng message

Event Hubs có thể nhận diagnostic records với một envelope JSON chứa records hoặc cấu trúc tương ứng loại log. Ví dụ minh họa:

~~~json
{
  "records": [
    {
      "time": "2026-11-20T09:20:00Z",
      "resourceId": "/subscriptions/example/resourceGroups/rg-observe/providers/Microsoft.KeyVault/vaults/kv-lab",
      "category": "AuditEvent",
      "operationName": "SecretGet",
      "resultType": "Success"
    }
  ]
}
~~~

Đây là **event tổng hợp**, không phải schema contract chung cho mọi Azure resource logs. Consumer cần hỗ trợ số records trong batch, schema version, field thiếu, loại dữ liệu khác nhau, retry, duplicates và late delivery. Đừng parser bằng cách giả định một message Event Hubs luôn tương ứng một Azure resource log row.

### 8.4. Một consumer ổn định cần gì?

~~~text
Event Hubs
  → read partitions in consumer group
  → parse envelope and validate source/category
  → apply schema/version mapping
  → redact sensitive fields if policy permits processing
  → write to durable downstream store/SIEM
  → checkpoint only after processing outcome is recorded
  → retry transient faults; quarantine poison messages
~~~

**At-least-once processing** có thể tạo duplicates quanh checkpoint/retry. Dùng stable IDs/timestamps và dedup strategy phù hợp, không chỉ `count()` raw events rồi coi mọi record duy nhất. Event Hubs retention hữu hạn; nếu consumer outage lâu hơn retention, mất dữ liệu có thể xảy ra trừ khi có archive song song.

### 8.5. Event Hubs không tự nhận mọi provider resource logs

Chỉ category đã bật và provider phát mới được gửi. Đừng debug không có message bằng cách tăng consumer throughput trước khi xác minh:

- Đúng **resource scope**?
- Event category đang phát hay không?
- Diagnostic setting trỏ **đúng Event Hub authorization rule và name**?
- Có network/firewall/permission issue?
- Event Hubs incoming messages có tăng?
- Consumer group/offset checkpoint có đọc từ đầu hay cuối?

### 8.6. Khi nào không nên chọn Event Hubs?

Nếu nhu cầu chỉ là xem vài sự kiện audit/ngày trong KQL, Event Hubs thêm infrastructure và consumer operations không cần thiết. Nếu mục tiêu là archive immutable 7 năm, Event Hubs retention không thay Storage với compliance policy. Chọn Event Hubs khi có **stream consumer cụ thể, owner, replay SLO và budget**.

## 9. Partner destinations: tích hợp có kiểm soát

Azure Monitor có những tích hợp đối tác trong phạm vi dịch vụ hỗ trợ. Một partner destination có thể gom sự kiện vào hệ phân tích/SIEM ngoài Azure mà tổ chức đã sử dụng.

### 9.1. Bộ câu hỏi trước khi dùng

1. Partner solution có hỗ trợ **resource provider/category** và region hiện tại không?
2. Dữ liệu rời Azure tenant/region không, dưới quyền và hợp đồng nào?
3. Có ingest/retention/egress/seat licensing ngoài Azure không?
4. Có cách xác minh số sự kiện nhận, trễ, lỗi, duplicate và schema mapping không?
5. Tích hợp yêu cầu quyền Azure RBAC/partner principal ở phạm vi nào?
6. Nếu partner outage 24 giờ, logs có được replay hay lưu ở Storage song song không?
7. Có audit/approval để ngừng routing hoặc thu hồi partner access không?

Không tạo một partner integration chỉ vì marketplace hiển thị lựa chọn. Đối tác không được tự cấp quyền truy cập mọi subscription/Log Analytics workspace nếu use case chỉ liên quan một nhóm tài nguyên.

### 9.2. Đánh giá vendor lock-in

Nên lưu:

- Danh sách categories/providers đang export.
- Tập trường schema quan trọng, ví dụ resource ID, operation, time, status.
- Quy tắc normalization/retention của partner.
- Kịch bản “chuyển từ partner sang SIEM khác” với Event Hubs/Storage archive.

Nếu yêu cầu pháp lý đòi bằng chứng có thể truy cập độc lập sau khi chấm dứt hợp đồng SIEM, cần archive do tổ chức kiểm soát.

## 10. Scope, subscription, region và ranh giới nguồn–đích

### 10.1. Resource-level diagnostic setting

Ví dụ một Key Vault:

~~~text
/subscriptions/<sub-id>
 /resourceGroups/rg-application-prod
 /providers/Microsoft.KeyVault/vaults/kv-orders-prod
~~~

Diagnostic setting cho Key Vault được gắn ở **resource này**, không ở “mọi Vault cùng resource group”. Nếu một application có Key Vault, App Service và Azure SQL, thông thường cần **mỗi resource một diagnostic setting** (hoặc policy tự triển khai từng resource) để thu log tương ứng.

### 10.2. Subscription Activity Log khác resource-level scope

~~~text
Subscription:
  /subscriptions/<sub-id>
  └── Activity Log diagnostic setting
      → AzureActivity in Log Analytics

Resource:
  /subscriptions/<sub-id>/resourceGroups/<rg>/providers/<type>/<name>
  └── Resource diagnostic setting
      → AzureDiagnostics / resource-specific tables
~~~

Không cấu hình Azure Activity Log bằng cách copy nguyên `AuditEvent` của Key Vault; categories Activity Log có tên và phạm vi khác. Với management groups/tenants, kiểm tra loại diagnostic export được hỗ trợ riêng.

### 10.3. Azure Storage child resources

Đối với nhiều dạng Azure Storage logging, nguồn có thể ở **subservice resource scope** như Blob service thay vì Storage Account cha:

~~~text
Microsoft.Storage/storageAccounts/<account>/blobServices/default
Microsoft.Storage/storageAccounts/<account>/fileServices/default
Microsoft.Storage/storageAccounts/<account>/queueServices/default
Microsoft.Storage/storageAccounts/<account>/tableServices/default
~~~

Đừng tạo diagnostic setting ở Storage Account cha rồi chắc chắn rằng nó thu được mọi Blob read/write log. Khám phá supported categories trên **chính resource scope** cần thu thập và xác minh records bằng thao tác test an toàn.

### 10.4. Region compatibility

Với nhiều **regional resources**, đích **Storage Account và Event Hubs** thường phải đáp ứng ràng buộc **cùng region** với resource nguồn để diagnostic settings hoạt động. Với **global resources**, có thể có quy tắc khác. Log Analytics workspace có thể ở region khác khi được dịch vụ hỗ trợ, nhưng kéo theo **data residency và data transfer considerations**.

Trước khi tạo cấu hình:

1. Xem `location` của nguồn và destinations.
2. Xác định nguồn thuộc **regional hay global**.
3. Kiểm tra hỗ trợ export với destination đã chọn.
4. Đánh giá residency, compliance và egress.
5. Thử một setting trên resource lab trước khi policy triển khai hàng loạt.

**Không hiểu “workspace ở region khác vẫn hoạt động” là dữ liệu luôn được phép chuyển xuyên biên giới**. Ràng buộc pháp lý và hợp đồng có thể nghiêm ngặt hơn khả năng kỹ thuật của Azure.

### 10.5. Cross-subscription và cross-tenant

Một destination ở subscription khác có thể khả thi theo dịch vụ và quyền, nhưng:

- Người triển khai phải có quyền thao tác trên nguồn và quyền phù hợp ở đích.
- Tenant khác có thể có hạn chế/ủy quyền riêng; không giả định mọi cross-tenant scenario được hỗ trợ.
- Workspace/Storage/Event Hubs ownership và billing có thể ở một team khác.
- Cần audit access, change approval, data residency, resource locks và naming standards.

Với organization có nhiều subscriptions, một kiến trúc phổ biến là **application subscriptions gửi logs về central observability workspace/archive** dưới quyền của platform/security team. Đó vẫn là nhiều diagnostic settings ở từng nguồn, không phải một setting duy nhất đặt ở central workspace để “hút” mọi log.

## 11. Quyền RBAC, bảo mật dữ liệu và network destination

Diagnostic export có thể chứa **resource identifiers, IPs, operation names, error messages, user/object identifiers** và đôi khi metadata nhạy cảm tùy provider. Đây là dữ liệu phải kiểm soát như một tài sản của tổ chức.

### 11.1. Ai được phép tạo diagnostic settings?

Tạo/sửa diagnostic settings thường cần quyền control-plane như `Microsoft.Insights/diagnosticSettings/write` trên nguồn (qua role phù hợp, ví dụ Monitoring Contributor trong scope tương ứng) **và quyền liên quan đến destination** để cấu hình workspace/storage/Event Hubs. Chỉ có Reader trên nguồn thường không đủ.

Không cấp Owner toàn subscription như một “fix” mặc định khi deployment báo access denied. Hãy xem action bị từ chối và tài nguyên scope đúng.

### 11.2. Các nhóm quyền tách biệt

| Vai trò | Quyền cần cân nhắc | Không tự tương đương |
|---|---|---|
| **Resource operator** | Xem nguồn/các categories, tạo diagnostic settings khi được giao | Đọc mọi archived data |
| **Log Analytics analyst** | Query các tables được phép | Sửa resource network/firewall |
| **Archive reader** | Đọc blobs audit theo least privilege | Xóa/chỉnh retention policy |
| **Security administrator** | Quản audit export/retention/privileged access | Dùng app secrets như principal sản xuất |
| **Event Hubs consumer** | Read qua consumer group được cấp | Manage namespace hoặc alter diagnostic settings |
| **IaC service principal** | Deploy setting vào đúng scope | Owner tất cả subscriptions |

Nơi đọc được logs cần có quyền khác với nơi thay đổi cấu hình nguồn. Ví dụ team ứng dụng có thể xem logs của App Service, nhưng không tự sửa immutable audit retention.

### 11.3. Data minimization và PII

Không bật mọi log/metric chỉ vì giá trị chẩn đoán tiềm năng. Với từng category:

- Chứa fields gì, có IP/user IDs/metadata nhạy cảm không?
- Có thể pseudonymize/redact **tại nguồn** nếu business policy cho phép không?
- Ai được xem/export?
- Retention theo class bao lâu?
- Có chuyển đến third-party hoặc cross-region không?
- Có duplication qua Log Analytics + Storage + Event Hubs không?
- Khi người dùng yêu cầu xóa theo chính sách, các bản sao có được quản lý không?

**Mã hóa at rest/in transit không đồng nghĩa được phép thu thập mọi dữ liệu**. Nếu log vô tình chứa access token, cần sửa producer/provider configuration và xử lý incident; chỉ xóa dashboard không xóa những bản sao đã xuất.

### 11.4. Trusted services, firewall và Private Endpoint

Các trường hợp lỗi phổ biến:

~~~text
Source resource emits logs
     ↓
Diagnostic pipeline attempts destination write
     ↓
Storage / Event Hubs firewall blocks platform service
     ↓
No blob / no Event Hub message
~~~

Khi destination có network restrictions, cần kiểm tra **Azure Monitor diagnostic service trusted-services bypass, network rules, supported identity/permissions, resource instance rules và regional constraints**. Không mặc định một Private Endpoint dành cho ứng dụng đã cấp đường đi cho diagnostic pipeline backend. Cũng không tắt toàn bộ firewall chỉ vì không thấy events.

### 11.5. Key management, encryption và compliance

Log Analytics, Storage và Event Hubs có mô hình encryption, managed keys/CMK, permissions và retention khác nhau. Nếu dùng customer-managed keys:

- Xác định Key Vault/Managed HSM và dependencies.
- Lập kế hoạch key rotation/revocation.
- Giám sát key access failures làm gián đoạn ingestion.
- Tách break-glass principal và audit thay đổi key policies.
- Đảm bảo DR/backup plan không phụ thuộc vào một key bị mất.

Không dùng diagnostic setting làm bằng chứng hoàn tất compliance chỉ vì console hiện `Succeeded`; cần **retention/immutability, access review và khả năng truy xuất audit log**.

## 12. Cấu hình qua Azure Portal: một resource lab

**Điều kiện:** đã có một resource (ví dụ Key Vault thử nghiệm) và Log Analytics workspace được phê duyệt, người thực hiện có quyền cần thiết. Portal labels có thể thay đổi theo phiên bản.

### 12.1. Chuẩn bị

- Ghi rõ **subscription/resource group/resource name/resource ID**.
- Xác nhận workspace/Storage/EH destination và region/data classification.
- Xem categories mà chính resource hỗ trợ.
- Có owner phê duyệt log volume/retention/budget.
- Chọn tên setting có ý nghĩa, ví dụ `diag-kv-lab-to-law`.

### 12.2. Các bước trên Portal

1. Mở Azure Portal → resource cần giám sát.
2. Trong khu vực **Monitoring**, chọn **Diagnostic settings**.
3. Xem những settings đã có, tránh tạo cấu hình trùng đích/cùng category.
4. Chọn **Add diagnostic setting**.
5. Đặt tên rõ ràng (môi trường, đích, loại log).
6. Chọn **Log categories/category groups** được hỗ trợ; không bật toàn bộ theo thói quen.
7. Chọn metrics category nếu hỗ trợ và thực sự có nhu cầu.
8. Bật đích **Send to Log Analytics workspace**, **Archive to a storage account**, **Stream to an event hub** hoặc partner được hỗ trợ.
9. Chọn **đúng destination** (subscription, resource, workspace/hub/storage) và data table mode nếu có.
10. Xem lại chi phí, region, access, configuration, sau đó **Save** theo change approval.
11. **Đọc lại setting**, tạo test event hợp lệ trên resource lab rồi xác minh destination thực sự nhận.

### 12.3. Sau khi lưu, kiểm tra ngay

Một cấu hình resource-level phù hợp phải trả lời được:

~~~text
SOURCE:
  /subscriptions/.../providers/Microsoft.KeyVault/vaults/kv-lab

DIAGNOSTIC SETTING:
  diag-kv-lab-to-law
  enabled logs: discovered and approved audit category/group
  metrics: only if supported and approved

DESTINATION:
  /subscriptions/.../providers/Microsoft.OperationalInsights/workspaces/law-lab

VALIDATION:
  settings GET matches desired state
  generated event was actually received
  KQL table and timestamp match expected output
~~~

**Không kết luận PASS chỉ vì Portal hiện “saved successfully”**. Nếu không có events, cần phân biệt “source chưa phát” và “export thất bại”.

## 13. Azure CLI: khám phá, đọc và tạo setting tới Log Analytics

### 13.1. Lệnh chỉ đọc — xác minh scope

Ví dụ Bash với placeholder:

~~~bash
az login
az account set --subscription "<approved-subscription-id>"
az account show \
  --query "{subscription:id,name:name,tenant:tenantId}" \
  -o table

RESOURCE_GROUP="<approved-resource-group>"
VAULT_NAME="<approved-key-vault-name>"
WORKSPACE_RG="<approved-workspace-resource-group>"
WORKSPACE_NAME="<approved-law-name>"

SOURCE_ID=$(az keyvault show \
  --resource-group "$RESOURCE_GROUP" \
  --name "$VAULT_NAME" \
  --query id -o tsv)

WORKSPACE_ID=$(az monitor log-analytics workspace show \
  --resource-group "$WORKSPACE_RG" \
  --workspace-name "$WORKSPACE_NAME" \
  --query id -o tsv)

printf "Source: %s\nWorkspace: %s\n" "$SOURCE_ID" "$WORKSPACE_ID"
~~~

`SOURCE_ID` là **resource source**, `WORKSPACE_ID` là **destination**. Trong PowerShell, cú pháp gán biến khác Bash; không copy lệnh `$(...)` trong môi trường không có shell tương thích.

### 13.2. Khám phá category

~~~bash
az monitor diagnostic-settings categories list \
  --resource "$SOURCE_ID" \
  --output json

az monitor diagnostic-settings list \
  --resource "$SOURCE_ID" \
  --output json
~~~

Đọc output, xác nhận các `logs`/`metrics` categories/category groups có thật. Thao tác `categories list` chỉ đọc, thích hợp làm bước đầu CI lint. **Không hardcode `allLogs` hoặc `AllMetrics` nếu output/resource hiện tại không hỗ trợ**.

### 13.3. Tạo diagnostic setting Log Analytics

**Chỉ trong resource lab được phê duyệt** và khi category group `allLogs` thực sự được provider hỗ trợ:

~~~bash
SETTING_NAME="diag-kv-lab-to-law"

az monitor diagnostic-settings create \
  --name "$SETTING_NAME" \
  --resource "$SOURCE_ID" \
  --workspace "$WORKSPACE_ID" \
  --logs '[{"categoryGroup":"allLogs","enabled":true}]'
~~~

Ví dụ cố ý **không bật metrics** vì phải kiểm tra nguồn hỗ trợ metric export và xác định mục đích. Nếu muốn chỉ audit, thay `allLogs` bằng group `audit` **nếu được liệt kê**, hoặc dùng category riêng:

~~~bash
# Chỉ chọn nếu nguồn có category "AuditEvent".
az monitor diagnostic-settings create \
  --name "diag-kv-lab-audit-to-law" \
  --resource "$SOURCE_ID" \
  --workspace "$WORKSPACE_ID" \
  --logs '[{"category":"AuditEvent","enabled":true}]'
~~~

**Không chạy cả hai mẫu trên cùng resource chỉ để học**: có thể xuất trùng cùng category đến cùng workspace và làm tăng dữ liệu/phức tạp theo cách không mong muốn. Chọn một cấu hình rõ yêu cầu, cân nhắc giới hạn số settings.

### 13.4. Cấu hình metric category khi được hỗ trợ

~~~bash
# Chỉ dùng khi danh sách category metrics có "AllMetrics".
az monitor diagnostic-settings create \
  --name "diag-resource-metrics-to-law" \
  --resource "$SOURCE_ID" \
  --workspace "$WORKSPACE_ID" \
  --metrics '[{"category":"AllMetrics","enabled":true}]'
~~~

**Không giả định mọi resource có `AllMetrics` hoặc Log Analytics nhận đầy đủ metric dimensions**. Với một metric alert đơn giản, cân nhắc tạo metric alert trực tiếp thay vì luân chuyển metric thành logs.

### 13.5. Đọc lại setting sau khi tạo

~~~bash
az monitor diagnostic-settings show \
  --name "$SETTING_NAME" \
  --resource "$SOURCE_ID" \
  --output json
~~~

Kiểm tra:

- `id` chứa đúng resource nguồn.
- `workspaceId` đúng destination.
- `logs[].category` hoặc `logs[].categoryGroup` và `enabled` đúng.
- `metrics[]` chỉ có khi đã bật.
- Không có destination hoặc category không thuộc change request.

**Cẩn trọng:** `az monitor diagnostic-settings create` là **thao tác ghi**; một setting có cùng tên có thể bị cập nhật. Trước khi chạy phải đọc danh sách hiện có để không ghi đè cấu hình của nhóm khác. Tên setting duy nhất không có nghĩa record không trùng với setting khác.

### 13.6. CLI trong môi trường PowerShell

Lệnh Bash ở trên dùng single-quoted JSON, phù hợp nhiều terminal Bash. Trong Windows PowerShell, cú pháp quote JSON truyền cho native command có thể cần escape/serialization khác theo phiên bản. Có thể chuẩn bị payload từ PowerShell `ConvertTo-Json -Compress` và kiểm tra cách argument được Azure CLI nhận; **không tự chuyển dấu quote bằng tay rồi dùng ngay ở production**. Mục tiêu là gửi một JSON array hợp lệ theo CLI help đang dùng.

## 14. CLI cho Storage, Event Hubs và destination nhiều đích

### 14.1. Storage export

~~~bash
STORAGE_ID=$(az storage account show \
  --resource-group "<approved-storage-rg>" \
  --name "<approved-storage-name>" \
  --query id -o tsv)

# WRITE: chỉ chạy sau khi kiểm tra region/permission/category.
az monitor diagnostic-settings create \
  --name "diag-kv-lab-to-archive" \
  --resource "$SOURCE_ID" \
  --storage-account "$STORAGE_ID" \
  --logs '[{"category":"AuditEvent","enabled":true}]'
~~~

Mẫu sử dụng `AuditEvent` chỉ cho **nguồn hỗ trợ category đó**, và không phải tất cả resource đều hỗ trợ Storage destination. Sau apply, kiểm tra Blob containers và data thực tế, không chỉ setting. Nếu storage firewall bật, thử delivery theo trusted-services/network rules được hỗ trợ.

### 14.2. Event Hubs export

~~~bash
# Resource ID của Event Hubs authorization rule đã được cấp quyền.
EVENT_HUB_RULE_ID="<authorized-event-hubs-rule-resource-id>"
EVENT_HUB_NAME="<approved-event-hub-name>"

# WRITE: chỉ chạy sau khi kiểm tra regional/network/permissions.
az monitor diagnostic-settings create \
  --name "diag-kv-lab-to-eventhubs" \
  --resource "$SOURCE_ID" \
  --event-hub-rule "$EVENT_HUB_RULE_ID" \
  --event-hub "$EVENT_HUB_NAME" \
  --logs '[{"category":"AuditEvent","enabled":true}]'
~~~

Không nhầm **authorization rule resource ID** với **Event Hubs connection string có secret**. Đọc `az monitor diagnostic-settings create --help` tại thời điểm triển khai: CLI extension/API versions có thể đổi property labels. Consumer phải được cấu hình riêng; không có Event Hub consumer thì logs vẫn có thể vào hub mà không ai xử lý.

### 14.3. Một setting với nhiều destinations

Azure diagnostic settings cho phép một cấu hình chứa nhiều đích khi các options được dịch vụ hỗ trợ. Dạng lệnh minh họa:

~~~bash
az monitor diagnostic-settings create \
  --name "diag-kv-lab-multi-dest" \
  --resource "$SOURCE_ID" \
  --workspace "$WORKSPACE_ID" \
  --storage-account "$STORAGE_ID" \
  --event-hub-rule "$EVENT_HUB_RULE_ID" \
  --event-hub "$EVENT_HUB_NAME" \
  --logs '[{"category":"AuditEvent","enabled":true}]'
~~~

**Đây không phải lời khuyên bật cả ba đích mặc định.** Cần tính duplicate traffic, ingestion/storage/Event Hubs costs và compliance. Một số teams chọn **separate settings theo đích** để có ownership/config change riêng, trong giới hạn settings per resource. Với bất kỳ cách nào, kiểm tra destination IDs và real delivery.

### 14.4. Khi resource có category groups khác

Thay `AuditEvent` bằng category thực lấy từ `categories list`. Nếu chỉ muốn nhóm:

~~~json
[
  {"categoryGroup": "audit", "enabled": true}
]
~~~

**Fragment này chỉ là `logs` payload**, không phải toàn bộ diagnostic setting. Không gửi cả category `AuditEvent` và group `audit` nếu dẫn đến category overlap/validation error; chọn đúng scheme mà API hỗ trợ.

## 15. Infrastructure as Code: Bicep và thiết kế khai báo

Portal giúp học cách làm, nhưng một doanh nghiệp có nhiều subscriptions không thể phụ thuộc vào việc từng người nhớ mở Diagnostic settings và chọn checkbox. **IaC** giúp cấu hình có version, review, triển khai lặp lại và đối chiếu drift.

### 15.1. Bicep cho Key Vault đã tồn tại

Một file Bicep minh họa:

~~~bicep
targetScope = 'resourceGroup'

@description('Name of an existing Key Vault in this resource group.')
param keyVaultName string

@description('Full ARM resource ID of the approved Log Analytics workspace.')
param logAnalyticsWorkspaceId string

resource keyVault 'Microsoft.KeyVault/vaults@2023-07-01' existing = {
  name: keyVaultName
}

resource keyVaultDiagnostics 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = {
  name: 'diag-to-central-log-analytics'
  scope: keyVault
  properties: {
    workspaceId: logAnalyticsWorkspaceId
    logAnalyticsDestinationType: 'Dedicated'
    logs: [
      {
        categoryGroup: 'allLogs'
        enabled: true
      }
    ]
  }
}
~~~

**Điều kiện để dùng mẫu:**

- Provider/resource hiện tại hỗ trợ group `allLogs` và mode `Dedicated` cho categories được chọn.
- Workspace ID phải là **full ARM resource ID**, không phải Log Analytics Workspace GUID/customer ID hoặc ingestion endpoint URL.
- Người deploy có quyền tại resource nguồn và workspace đích như yêu cầu.
- Bản API version trong Bicep phải còn được hỗ trợ; validate với toolchain hiện tại.
- Đây là setting gắn vào **Key Vault đã tồn tại**, không tạo Vault mới.
- Nó **không tạo data**, chỉ định tuyến events phát sinh về sau nếu có.

Nếu mục tiêu chỉ audit, dùng group `audit` khi hỗ trợ hoặc liệt kê categories cụ thể. Nếu resource không hỗ trợ `Dedicated`, bỏ property hoặc dùng chế độ được hỗ trợ, rồi điều chỉnh các KQL queries theo bảng thật.

### 15.2. Cẩn trọng với `allLogs` trong CI/CD

Khi Azure resource provider thêm loại log mới vào `allLogs`, deployment không đổi nhưng lượng dữ liệu phát có thể tăng. IaC cần:

- Budget và quota alerts.
- Review supported category catalog định kỳ.
- Data classification và retention review.
- Test schema của downstream SIEM/parser.
- Cơ chế rollback configuration khi không phù hợp.

Không dùng `allLogs` như một shortcut bỏ qua đánh giá chi phí và PII.

### 15.3. Subscription Activity Log Bicep ở scope khác

Ví dụ riêng ở **subscription scope**:

~~~bicep
targetScope = 'subscription'

@description('Full ARM resource ID of the central workspace.')
param logAnalyticsWorkspaceId string

resource subscriptionActivityDiagnostics 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = {
  name: 'activity-to-central-log-analytics'
  properties: {
    workspaceId: logAnalyticsWorkspaceId
    logs: [
      {
        category: 'Administrative'
        enabled: true
      }
      {
        category: 'Security'
        enabled: true
      }
      {
        category: 'Policy'
        enabled: true
      }
    ]
  }
}
~~~

**Đây là mẫu riêng với scope subscription**, không tự động chạy cùng template resource group ở phần trước. Categories phải được xác nhận trong cấu hình Activity Log được hỗ trợ. Người deploy cần quyền ở subscription scope; không đưa template này vào pipeline chỉ có resource-group Contributor rồi cấp Owner vô hạn để chữa lỗi.

### 15.4. Kịch bản Azure Policy

Với nhiều subscriptions/resource groups, Azure Policy có thể dùng **DeployIfNotExists** để giúp tài nguyên thuộc một loại có diagnostic setting theo chuẩn tổ chức:

~~~text
Policy assignment (approved scope)
  → Identify resources without expected diagnostic setting
  → Deploy diagnostic configuration via managed identity
  → Remediation task for existing non-compliant resources
  → Compliance dashboard
  → Continuous validation of destination data
~~~

Cần phân biệt:

- **Policy compliance**: setting có cấu hình được đánh giá theo policy.
- **Data delivery health**: logs/metrics thực sự đến đích và có thể query/đọc.

Policy có thể báo compliant trong khi nguồn không phát event hoặc destination network cản trở delivery. Hãy bổ sung end-to-end test/alert.

### 15.5. Chiến lược ownership giữa app team và platform/security

| Lớp | Owner chính | Quyền/đầu việc |
|---|---|---|
| Resource source | Application/resource owner | Biết categories và business meaning |
| Diagnostic policy/IaC | Cloud platform | Naming, category baseline, destination IDs |
| Log Analytics workspace | Observability/SRE | Tables, KQL, alerts, access, cost |
| Archive Storage | Security/compliance | Retention, immutability, recovery |
| Event Hubs pipeline | Data/SIEM platform | Throughput, consumer groups, lag, replay |
| Privileged access | IAM/security | RBAC, identities, periodic review |
| Data classification | Privacy/data owner | PII, residency, retention policy |

Một workspace trung tâm không nên biến app team thành người có quyền xóa audit blob hoặc sửa monitoring policy của toàn tổ chức.

## 16. Kiểm chứng đích Log Analytics: từ event đến KQL

Một bước phát triển tốt phải có **post-deployment verification** thay vì dừng ở Azure CLI status code.

### 16.1. Test bằng sự kiện có kiểm soát

Ví dụ Key Vault **lab**:

1. Xác nhận resource ID và setting `diag-kv-lab-to-law`.
2. Chọn một operation audit vô hại đã được phép, chẳng hạn **đọc một secret test** bằng client có quyền hoặc thực hiện một thao tác được ghi log.
3. Ghi **UTC event time, operation, resource ID, identity test**.
4. Chờ ingestion theo đặc tính dịch vụ; không giả định dữ liệu xuất hiện tức thì.
5. Query đúng Log Analytics workspace và bảng thực.
6. Đối chiếu event/operation, phân biệt record thật với logs khác.
7. Ghi kết quả, thời gian đến, người xác minh và thất bại nếu có.

**Không thử đọc secret production trái phép, cố tạo lỗi an ninh, xóa resource hoặc thay firewall** để ép phát sinh logs. Chọn test events có quyền và rủi ro thấp.

### 16.2. KQL xác nhận resource ID

Khi logs vào `AzureDiagnostics`:

~~~kusto
let TargetResource =
  "/subscriptions/<sub-id>/resourceGroups/<rg>/providers/Microsoft.KeyVault/vaults/<vault>";
AzureDiagnostics
| where TimeGenerated > ago(2h)
| where _ResourceId =~ TargetResource
| summarize Events=count(), LastEventUtc=max(TimeGenerated)
    by Category
| order by Events desc
~~~

**Bảng `AzureDiagnostics` có thể hoàn toàn không tồn tại** nếu resource/provider đẩy vào bảng chuyên biệt. Khi đó dùng đúng dedicated table đã được xác minh, không tạo bảng giả để làm query “chạy xanh”.

### 16.3. Độ mới dữ liệu và thời gian ingestion

Một số bảng Log Analytics có thông tin thời gian nhận/ingestion, nhưng field/metadata không đồng nhất. Nếu bảng hỗ trợ `ingestion_time()`, có thể phân tích:

~~~kusto
AzureDiagnostics
| where TimeGenerated > ago(1d)
| extend IngestedAt = ingestion_time()
| where isnotnull(IngestedAt)
| extend LagMinutes =
    datetime_diff("minute", IngestedAt, TimeGenerated)
| summarize P95LagMinutes=percentile(LagMinutes, 95)
    by Category
~~~

**Cảnh báo diễn giải:** `TimeGenerated` là event time theo nguồn/record; `ingestion_time()` có thể null hoặc có semantics khác theo bảng và dữ liệu. Clock skew, buffering và provider delays làm lag khác nhau. Nếu không có metadata hỗ trợ, đo bằng một test event đã biết UTC time và thời điểm có thể query trong workspace.

### 16.4. Khi metric export có bảng `AzureMetrics`

~~~kusto
AzureMetrics
| where TimeGenerated > ago(24h)
| summarize Samples=count(), LastSample=max(TimeGenerated)
    by MetricName
| top 20 by Samples desc
~~~

Kiểm tra metric resource/provider schema thực; nhiều metric chỉ có ở Metrics Explorer hoặc API, không tạo records ở `AzureMetrics` qua diagnostic settings. Nếu `AzureMetrics` trống, đừng kết luận “CPU bằng 0”.

### 16.5. Khi source hoàn toàn không phát event

Một query:

~~~kusto
AzureDiagnostics
| where TimeGenerated > ago(15m)
| summarize Events=count()
~~~

có thể trả 0 vì chưa có sự kiện của loại cần đo, sai filter, ingestion delay hoặc export failure. **0 logs không tương đương 0 lỗi hay 100% availability**. Kết hợp metric alerts, synthetic tests, last-seen per source và kiểm tra diagnostic setting/configuration status.

### 16.6. Cross-resource correlation

Khi đã có logs của Key Vault, App Service và SQL:

~~~kusto
AzureDiagnostics
| where TimeGenerated between (
    datetime(2026-11-20T09:00:00Z)
    ..
    datetime(2026-11-20T09:30:00Z)
  )
| summarize Events=count()
    by ResourceProvider, Category, bin(TimeGenerated, 5m)
| order by TimeGenerated asc
~~~

Đây là **một phép so sánh thời điểm theo categories**. Nó không tự chứng minh quan hệ nhân quả giữa App Service 500 và Key Vault 403; cần trace ID/correlation IDs, resource logs, identity/audit evidence và thông tin deployment. Dùng **UTC** khi so logs nhiều dịch vụ.

## 17. Xác minh đích Storage, Event Hubs và partner

### 17.1. Storage export acceptance test

Trong Storage account đích:

1. Xác nhận account và region/permissions/diagnostic setting ID.
2. Phát một event **được phép** trên resource lab.
3. Sau khoảng thời gian phù hợp, liệt kê containers/blobs mới theo category/time.
4. Đọc JSON được Azure xuất, kiểm tra resource ID/event time/operation.
5. Kiểm tra lifecycle/immutability policy có phù hợp không.
6. Xác nhận **read-only auditor** xem được, principal ứng dụng không tự xóa archive.

Ví dụ **lệnh đọc metadata** nếu có quyền và phương thức auth phù hợp:

~~~bash
az storage container list \
  --account-name "<approved-storage-account>" \
  --auth-mode login \
  --query "[].name" \
  --output table
~~~

Lệnh này chỉ liệt kê container names; nó không chứng minh mọi log events đã được archive. Với firewall/Entra RBAC, ngay cả người có Azure Resource Reader cũng không mặc định có **Storage Blob Data Reader**.

### 17.2. Event Hubs acceptance test

Kiểm chứng theo ba lớp:

~~~text
1. Diagnostic setting:
   source + category + namespace rule + event hub name correct.

2. Event Hubs namespace/hub:
   incoming messages/bytes, throttling and partition health.

3. SIEM/consumer:
   consumer group offset/checkpoint advances,
   schema parsed, dedup and downstream persistence verified.
~~~

Nếu Event Hubs `IncomingMessages` tăng nhưng SIEM dashboard trống, có thể lỗi **consumer/subscription offset/parser** chứ không phải diagnostic setting. Nếu Event Hubs không thấy incoming messages, điều tra source category/permissions/network/region trước khi debug SIEM query.

### 17.3. Partner destination acceptance test

- Xác nhận partner integration provisioned đúng tenant/region.
- Kiểm tra diagnostic setting trỏ đúng partner resource.
- Thực hiện audit/log event test theo chính sách.
- Đối chiếu original source event ID/time với dashboard partner.
- Ghi nhận dữ liệu trễ, bị lọc, parse lỗi và quy trình support.
- Test quyền thu hồi tích hợp mà không gây ảnh hưởng logging đích khác.

Không dựa vào “Partner connector connected” để khẳng định mọi events đều đến SIEM. Các phía phải có monitoring và reconciliation độc lập.

## 18. Alerting dựa trên logs và metrics

Diagnostic setting chỉ chuyển dữ liệu; **alert rule** cần tạo riêng. Phân biệt:

### 18.1. Metric alert trực tiếp

~~~text
Azure SQL CPU percent > 80%
for a defined evaluation window
    ↓
Metric alert → Action Group
    ↓
On-call / automation with approvals
~~~

Metric alert có thể phản ứng không cần chờ logs được đưa vào workspace, khi metric/resource hỗ trợ. Chọn aggregation/window/severity và kiểm tra false positives; 80% chỉ là ngưỡng minh họa, không phải SLO mặc định.

### 18.2. Log search alert

~~~text
Key Vault audit category exported to Log Analytics
    ↓
KQL detects repeated failed access events
    ↓
Scheduled query rule / log alert
    ↓
Action Group / incident runbook
~~~

Ví dụ KQL khi workspace có `AzureDiagnostics` và các cột cần thiết:

~~~kusto
AzureDiagnostics
| where TimeGenerated > ago(15m)
| where ResourceProvider == "MICROSOFT.KEYVAULT"
| where Category == "AuditEvent"
| summarize Events=count() by ResultType
| order by Events desc
~~~

**Đây là truy vấn khám phá, chưa phải detection rule hoàn chỉnh.** Phải chọn semantics thất bại/`ResultType` thực trên bảng, ngưỡng/hành vi baseline, suppress schedule và data freshness. Nếu data dùng table chuyên biệt, query phải thay theo schema. Không gắn Action Group tự vô hiệu hóa tất cả identities vì một error event.

### 18.3. Action Groups và automation

Alert chỉ hữu ích nếu có **owner và runbook**. Một Action Group có thể gửi email/notification/webhook hoặc kết nối workflow được hỗ trợ, nhưng việc automation chỉnh firewall/revoke credentials/xóa resource cần RBAC và approvals; không để alert noise kích hoạt thao tác phá hủy tự động.

### 18.4. Missing telemetry alert

Nếu dự kiến có audit events hoặc heartbeat theo cadence, hệ thống cần báo khi **nguồn mất tín hiệu**. Tuy nhiên một resource ít sử dụng có thể không phát logs suốt nhiều giờ theo hành vi bình thường. Do vậy, missing-log alert cần:

- **Expected active sources/inventory**.
- Synthetic events được phép hoặc alternative health checks.
- Last-seen/query ingestion lag.
- Phân biệt không có hoạt động và delivery failure.

Không biến một audit log category ít phát sự kiện thành alert “0 logs = outage” mặc định.

## 19. Data Collection Rules, transformations và chuẩn hóa dữ liệu

### 19.1. Diagnostic settings vs DCR

**Diagnostic settings** phổ biến cho platform resource logs và metrics export. **Data Collection Rules (DCR)** định nghĩa cách thu/transform/route những data streams được hỗ trợ, đặc biệt khi dùng **Azure Monitor Agent** và các luồng ingestion khác.

~~~text
Azure resource platform logs/metrics
  → Diagnostic setting
  → Log Analytics / Storage / Event Hubs / partner

VM guest logs/performance counters
  → Azure Monitor Agent
  → Data Collection Rule
  → Azure Monitor Logs / other supported destinations

Application SDK / agent telemetry
  → Azure Monitor / Application Insights pipeline
  → Workspace-based monitoring as configured
~~~

Không mặc định gắn một DCR lên mọi diagnostic setting để có **ingestion-time transformation** tự do. Hỗ trợ transformation phụ thuộc **data source/stream/table/plan**, phải kiểm tra product-specific capabilities; có resource logs/workspace modes không hỗ trợ cách transform mà bạn dự kiến.

### 19.2. Chuẩn hóa schema khi stream Event Hubs

Một SIEM consumer có thể nhận records của Key Vault, App Service, Firewall và Azure SQL với các fields khác nhau. Nên dùng **normalized envelope** downstream:

~~~json
{
  "sourceResourceId": "/subscriptions/example/resourceGroups/rg-a/providers/Microsoft.KeyVault/vaults/kv-a",
  "provider": "Microsoft.KeyVault",
  "category": "AuditEvent",
  "eventTimeUtc": "2026-11-20T09:20:00Z",
  "ingestedAtUtc": "2026-11-20T09:22:10Z",
  "operation": "SecretGet",
  "outcome": "Success",
  "schemaVersion": 1
}
~~~

**Đây là schema thiết kế downstream**, không phải output cố định của diagnostic settings. Nếu consumer gắn `ingestedAtUtc` tại thời điểm nhận, nó biểu diễn **consumer ingestion time**, không nhất thiết thời điểm Azure Monitor log xuất hiện. Cần giữ raw record và mapping version phù hợp để điều tra.

### 19.3. Data deduplication và replay

Không phải mọi record đều có stable event ID duy nhất do provider cấp. Với Event Hubs:

- Dùng provider-provided ID/correlation nếu khả dụng.
- Nếu không có, định nghĩa key kết hợp **source + category + event time + operation + properties** với xác suất collision được đánh giá.
- Lưu original source timestamp và stream offset.
- Checkpoint sau khi consumer đã xử lý bền vững.
- Thiết kế DLQ/quarantine của **consumer pipeline**, không mặc định Azure Monitor tự có dead-letter queue cho mọi delivery failure.

Đối với audit legally significant, không suy luận event counts chính xác từ `dcount()` hoặc một consumer chưa có dedup/reconciliation strategy.

## 20. FinOps: chi phí khi định tuyến một nguồn đến nhiều đích

Một diagnostic setting có thể được tạo mà không có khoản phí “mỗi setting” riêng trong phần lớn use cases, nhưng **các đích và việc xử lý/giữ dữ liệu thường phát sinh chi phí**. Đừng hiểu “bật Azure Monitor Diagnostic settings là miễn phí” theo nghĩa toàn pipeline miễn phí.

### 20.1. Bảng nguồn chi phí

| Thành phần | Có thể tính phí bởi |
|---|---|
| **Log Analytics ingestion** | Dung lượng logs ingested, pricing plan và data type |
| **Log Analytics retention/query** | Interactive/long-term retention, search/query theo plan |
| **Storage** | Dung lượng blobs, transactions, replication, lifecycle và rehydrate |
| **Event Hubs** | Tier/capacity/throughput units/partitions/retention và phụ trợ |
| **Partner/SIEM** | Ingestion/seat/retention/license của vendor |
| **Networking** | Cross-region/egress/private networking theo thiết kế |
| **Azure Monitor alerts** | Scheduled query alerts, metric alerts và notification theo pricing |
| **Engineering operations** | Consumer maintenance, compliance, incident response, backfill |

**Cần xác nhận giá hiện hành theo region, Azure Monitor workspace plan và loại data**. Một số Azure logs/metrics có bảng giá hoặc chính sách free ingestion/benefit riêng; không lấy mô hình sau làm hóa đơn thực.

### 20.2. Ví dụ thể tích dữ liệu

Giả sử một nhóm tài nguyên phát trung bình:

~~~text
15 GB diagnostic resource logs / day
30 days
Destinations:
  Log Analytics workspace
  Storage archive
  Event Hubs → SIEM
~~~

Dung lượng dữ liệu logic mỗi tháng:

\[
15\ \text{GB/day}\times30\ \text{days}=450\ \text{GB/month}.
\]

Nếu gửi cùng dòng dữ liệu đến ba destination, cả ba đều phải **xử lý khoảng 450 GB logical source payload mỗi tháng**, nhưng không được đơn giản lấy `450 × 3` rồi coi đó là billable size chính xác:

- Log Analytics tính theo **đơn vị và pricing plan/record type**.
- Storage có **encoding/compression/metadata/replication** khác raw size.
- Event Hubs tính theo **throughput/capacity/retention** và có overhead/batching.
- SIEM có thể tính riêng theo records/bytes/field count.
- Network egress/cross-region có thể có phí.

Mục tiêu của ví dụ là nhận ra **fan-out làm tăng khối lượng được xử lý tại nhiều đích**, không phải thay Azure Pricing Calculator.

### 20.3. Kịch bản bật `allLogs` tăng dữ liệu

Trước khi bật:

~~~text
Audit category:       2 GB/day
Operational category: 13 GB/day

Required use case:
  Security team only needs audit.
~~~

Nếu bật `allLogs` vì “dễ”, workspace phải xử lý tới **15 GB/day** thay vì **2 GB/day** theo giả định. Khác biệt 13 GB/day có thể ảnh hưởng retention/cost/PII exposure. Nhưng nếu SRE cần operational categories, cắt chúng chỉ để tiết kiệm sẽ làm mất khả năng điều tra; quyết định cần **data value + owner + budget**.

### 20.4. Retention theo lớp

Một chiến lược minh họa:

| Data class | Log Analytics interactive | Storage archive | Điều kiện |
|---|---:|---:|---|
| Frequent operational logs | 30 ngày | Tùy business need | SRE query thường xuyên |
| Security audit | 90 ngày | 1–3 năm hoặc policy thực | SOC và compliance review |
| Debug/noisy telemetry | 7–14 ngày | Không lưu dài hạn khi không cần | Chi phí/PII risk |
| Financial/legal audit | Theo quy định thực tế | Immutability/retention được phê duyệt | Chính sách của tổ chức |

Các mốc **không phải quy định bắt buộc cho mọi quốc gia/ngành**. Retention ở Log Analytics, Storage, Event Hubs và partner **độc lập**; thay thời gian giữ ở Log Analytics không tự xóa logs đã stream sang SIEM.

### 20.5. Kiểm tra lượng ingest

Trong Log Analytics, bảng `Usage` (nếu có/được cấp quyền) có thể giúp ước lượng volume theo loại dữ liệu:

~~~kusto
Usage
| where TimeGenerated >= ago(30d)
| summarize UsageQuantity=sum(Quantity) by DataType
| order by UsageQuantity desc
~~~

**Không coi số `Usage.Quantity` là hóa đơn chuẩn trong mọi pricing plan/tables.** Đơn vị/coverage của records và khả năng hiển thị phụ thuộc workspace. Khi đánh giá bill thật, dùng **Azure Cost Management + workspace usage/cost details** và ghi rõ billing period/plan.

### 20.6. Kiểm soát chi phí mà không hy sinh compliance

- Bật categories theo nhu cầu và SLO được phê duyệt.
- Chọn group `audit`/specific categories khi chỉ cần audit.
- Dùng metric alerts trực tiếp nếu không cần export metrics thành logs.
- Chia Log Analytics retention và Storage archive theo data class.
- Tránh định tuyến cùng logs **trùng đích** qua nhiều settings không kiểm soát.
- Kiểm tra high-volume providers (networking/Firewall/Storage data plane).
- Dùng data ingestion/query dashboards, budget alerts và owner rõ.
- Đánh giá DCR transformations **chỉ khi stream/table hỗ trợ**, không giả định có thể filter mọi diagnostic category bằng một DCR.
- Nếu cần giữ lâu dài, đừng xóa audit để đạt cost target.

## 21. Monitoring chính pipeline diagnostic export

Diagnostic setting là **đường chuyển dữ liệu**, nên chính đường này cũng phải có health monitoring. Thiếu quan sát về pipeline sẽ tạo “điểm mù giám sát”: khi log export hỏng, dashboard lỗi có thể trông như hệ thống khỏe.

### 21.1. Những lớp cần giám sát

| Lớp | Chỉ số/câu hỏi | Nguồn bằng chứng |
|---|---|---|
| **Source resource** | Có phát đúng logs/metrics không? | Resource activity/test event/category docs |
| **Configuration** | Setting còn tồn tại và categories/đích đúng? | ARM GET/IaC/Policy compliance |
| **Log Analytics** | Last event time, table volume, ingestion lag? | KQL, usage/workspace metrics |
| **Storage archive** | Container/blob có tăng và đọc được? | Storage inventory/metrics, test reads |
| **Event Hubs** | Incoming messages, throttling, consumer lag? | Event Hubs metrics/consumer checkpoints |
| **Partner** | Events đến đúng schema và timely? | Partner status/ingest metrics |
| **Governance** | Có thay quyền/retention/network config không? | Activity Log/policy/audit |

### 21.2. Last-seen theo resource

Giả sử `AzureDiagnostics` có logs thường xuyên:

~~~kusto
AzureDiagnostics
| where TimeGenerated > ago(24h)
| summarize
    LastEventUtc=max(TimeGenerated),
    Events=count()
  by _ResourceId
| extend MinutesSinceLastEvent =
    datetime_diff("minute", now(), LastEventUtc)
| order by MinutesSinceLastEvent desc
~~~

**Không thấy resource nào trong kết quả** không có nghĩa resource đó không còn tồn tại. Nó có thể không phát event trong 24 giờ, bị chặn routing hoặc bảng đã chuyển sang resource-specific. Với missing-source alert cần inventory **expected resources** rồi đối chiếu, không chỉ dựa các resource đã xuất hiện.

### 21.3. Expected inventory để phát hiện resource im lặng

Một mô hình query với inventory tổng hợp:

~~~kusto
let Expected = datatable(_ResourceId:string)
[
  "/subscriptions/example/resourceGroups/rg-lab/providers/Microsoft.KeyVault/vaults/kv-a",
  "/subscriptions/example/resourceGroups/rg-lab/providers/Microsoft.KeyVault/vaults/kv-b"
];
let Observed =
    AzureDiagnostics
    | where TimeGenerated > ago(1d)
    | summarize LastEventUtc=max(TimeGenerated)
      by _ResourceId;
Expected
| join kind=leftouter (Observed) on _ResourceId
| extend HasRecentEvent=isnotnull(LastEventUtc)
| project _ResourceId, LastEventUtc, HasRecentEvent
~~~

**Đây là query tham khảo khi bảng `AzureDiagnostics` tồn tại.** Nó chỉ báo “có event trong ngày” chứ không xác nhận export lỗi; đối với Key Vault nhàn rỗi, không có request nào cả ngày là bình thường. Kết hợp synthetic test hoặc policy compliance/Activity Log.

### 21.4. Tránh chỉ giám sát workspace

Log Analytics ingest khỏe vẫn không bảo đảm:

- Storage archive đang nhận audit blobs;
- Event Hubs SIEM consumer còn đọc;
- một source Key Vault quan trọng chưa bị xóa diagnostic setting;
- PII chưa bị gửi sang partner trái policy.

Nếu dùng **ba đích**, phải có **ít nhất một phép kiểm tra delivery có ý nghĩa cho từng đích** và người phụ trách cụ thể.

### 21.5. Báo động thay đổi diagnostic settings

Resource control-plane changes xuất hiện trong **Activity Log** nếu loại operation/provider và scope được ghi nhận. Nên có alerts/Policy compliance khi:

- Diagnostic setting bị xóa hoặc disable một critical category.
- Đích workspace/storage/EH bị đổi.
- Public network access hoặc destination firewall bị thay.
- Audit archive retention/immutability bị hạ.
- RBAC privileged changes cấp quyền xóa audit data.

**Không tạo hệ thống vòng lặp phụ thuộc**: nếu tất cả alert về việc xóa diagnostic settings cũng phụ thuộc duy nhất vào logs đi qua chính setting vừa bị xóa, bạn có thể không nhận được cảnh báo. Dùng Activity Log/Policy và các đường độc lập cho critical monitoring.

## 22. Troubleshooting: tạo setting thành công nhưng không có dữ liệu

### 22.1. Bảng triệu chứng

| Triệu chứng | Nguyên nhân thường gặp | Hướng kiểm tra |
|---|---|---|
| `categories list` rỗng/không hỗ trợ | Sai resource type/scope hoặc provider không có categories | Đúng ARM resource ID và API/provider capabilities |
| CLI báo invalid `categoryGroup` | Resource không hỗ trợ `allLogs`/`audit` | Dùng supported category riêng |
| CLI báo invalid `AllMetrics` | Metric export không hỗ trợ | Discovery metrics; dùng metric alert |
| Saved setting, workspace không có bảng | Chưa có events, data delay, table mode khác | Test event, workspace ID, tables/schema |
| `AzureDiagnostics` không tồn tại | Resource-specific tables hoặc không có ingestion | Kiểm tra destination type và actual tables |
| KQL trả 0 rows | Sai time range/resource ID/Category | UTC, `_ResourceId`, time filter |
| Activity Log không xuất sang workspace | Chỉ bật resource-level setting | Tạo subscription-level Activity Log export |
| VM syslog không xuất | Nhầm platform diagnostics với guest collection | AMA + DCR |
| Log đến Storage nhưng KQL không thấy | Storage không tự trở thành Log Analytics | Ingest/query pipeline riêng |
| Storage không có blobs | Region/firewall/permission hoặc source chưa phát | Destination constraints, trusted services, source event |
| Event Hubs IncomingMessages không tăng | Rule/hub/region/network/categories sai | Delivery configuration và source validation |
| Event Hubs có messages nhưng SIEM trống | Consumer/offset/parser/lag | Consumer groups, checkpoints, DLQ |
| Destination ở region khác bị reject | Regional source export constraint | Deploy same-region destination hoặc supported alternative |
| Không đủ quyền create/update | Thiếu `diagnosticSettings/write`/destination authorization | Review RBAC on both sides |
| SIEM duplicates/log delay | Retries/checkpoint/partition behavior | Idempotency, lag, batch/schema validation |
| Log ingestion cost tăng đột ngột | `allLogs`/data volume/new categories/duplicate paths | Workspace usage, categories, Cost Management |
| Security alert mất khi setting bị xóa | Monitoring chỉ dựa chính exported logs | Activity Log/Policy independent alert |
| Có metrics ở Metrics Explorer nhưng không ở `AzureMetrics` | Metric không export được hoặc schema khác | Metric category support/destination mapping |

### 22.2. Runbook 10 bước

1. **Xác định scope:** đang kiểm tra đúng subscription/resource group/type/resource ID hay child resource?
2. **Xác nhận signal type:** Activity Log, resource log, platform metric, application telemetry hay guest OS?
3. **Khám phá categories:** provider có category/group/metric export cần thiết?
4. **Đọc cấu hình thật:** setting name, enabled categories, destination resource IDs và table mode?
5. **Tạo test event an toàn:** nguồn có phát đúng signal trong thời gian đã ghi?
6. **Kiểm tra vùng và quyền:** source/destination regions, Azure RBAC, network/trusted services?
7. **Kiểm tra destination health:** workspace ingestion, blob writes, EH IncomingMessages/consumer lag?
8. **Kiểm tra parser/query:** đúng table/column/category/resourceId/UTC range/envelope?
9. **Xác định chi phí, PII và duplicates:** có cấu hình thừa hoặc records bị trùng/đến muộn?
10. **Xác minh sửa lỗi:** event mới đến từng đích, alert/workbook chạy, lưu bằng chứng/runbook.

### 22.3. Tình huống 1 — App Service HTTP 500 không thấy trong Key Vault logs

Không nên tìm HTTP 500 application exception trong `KeyVaultAuditEvents`. App Service/Spring Boot 500 là **tín hiệu ứng dụng/web server**, còn Key Vault audit events trả lời client nào đọc secrets hoặc bị denied. Kết hợp:

~~~text
Spring Boot / Application Insights → HTTP 500 / exception trace
App Service resource logs        → web platform details (if supported)
Key Vault audit logs            → SecretGet/permission failures
Azure Activity Log              → config changes / deployments
~~~

Các loại logs có thể cùng có timestamp 09:20 mà không chứng minh một cái gây ra cái kia. Cần request trace/correlation và timeline.

### 22.4. Tình huống 2 — Storage có Private Endpoint nhưng không nhận logs

Ứng dụng trong VNet đọc blob qua Private Endpoint thành công, trong khi Azure Monitor diagnostic export không thấy blobs mới. Có thể destination firewall chưa cho phép Azure Monitor delivery theo cơ chế trusted services tương ứng, hoặc khác region/permission. **Đường đi từ app tới storage khác đường đi từ Azure Monitor platform tới storage**.

Đừng tắt toàn bộ storage firewall. Kiểm tra supported networking and service exceptions, RBAC/permissions và resource source event; thử trên Storage lab.

### 22.5. Tình huống 3 — Event Hubs bị lag

Diagnostic setting gửi 5.000 records/giây, consumer SIEM xử lý 1.000 records/giây. Backlog tăng và có thể vượt retention. Thêm diagnostic settings nữa **không chữa consumer bottleneck**; phải tăng consumer throughput/partitions theo architecture, tối ưu parser/checkpoint, giảm duplicate/unneeded categories và có archive/replay strategy.

### 22.6. Tình huống 4 — KQL sai table mode

IaC dùng:

~~~bicep
logAnalyticsDestinationType: 'Dedicated'
~~~

Analyst vẫn chạy:

~~~kusto
AzureDiagnostics
| where Category == "AuditEvent"
~~~

Query có thể trống vì records đi vào **resource-specific table**. Hướng sửa: xác định table được resource/provider tạo thực, sử dụng schema tương ứng, cập nhật dashboards/alerts và migration of existing queries. Không bật lại AzureDiagnostics chỉ để che rằng queries chưa được cập nhật.

### 22.7. Tình huống 5 — Policy compliant nhưng không có audit record

Azure Policy thấy diagnostic setting tồn tại và đúng category, nhưng resource không có audit event trong 1 ngày hoặc đích bị network block. **Compliance của setting ≠ bằng chứng delivery**. Dùng synthetic test được phép và độc lập đo từ source đến workspace/archive/SIEM.

## 23. Case study: đơn hàng lỗi sau khi thay cấu hình Key Vault

### 23.1. Bối cảnh

Một công ty thương mại điện tử có:

~~~text
Subscription:  production-commerce
Resources:
  App Service: orders-api
  Azure SQL Database: orders-db
  Key Vault: kv-orders
  Azure Firewall / network resources

Central observability:
  Log Analytics workspace: law-platform-prod
  Storage account: protected audit archive
  Event Hubs: streaming to SIEM
~~~

**Sự cố giả định:** 09:10 UTC, một change làm thay đổi quyền hoặc network rule Key Vault. Từ 09:20, Spring Boot ứng dụng nhận 403 khi đọc secret và phát HTTP 500 do xử lý exception không tốt. Dashboard chỉ cho thấy request errors tăng.

### 23.2. Kiến trúc thu thập đề xuất

~~~mermaid
flowchart TB
    APP[App Service orders-api] --> APPDS[App Service diagnostic settings]
    KV[Key Vault kv-orders] --> KVDS[Key Vault diagnostic settings]
    SQL[Azure SQL Database] --> SQLDS[SQL diagnostic settings]
    SUB[Subscription Activity Log] --> SUBDS[Subscription diagnostic setting]
    APPDS --> LA[(Log Analytics)]
    KVDS --> LA
    SQLDS --> LA
    SUBDS --> LA
    KVDS --> ARCH[(Storage protected archive)]
    KVDS --> EH[Event Hubs]
    EH --> SIEM[Security SIEM]
    APM[Spring Boot Application Insights] --> LA
    LA --> KQL[Incident KQL / workbook]
~~~

**Nút Application Insights là một pipeline application telemetry riêng**. Diagram không tuyên bố một App Service diagnostic setting tự thu đầy đủ trace Java. Các đích có thể nằm trong scope/region phù hợp theo policy và service support.

### 23.3. Chọn logs cụ thể

| Source | Loại tín hiệu cần có | Đích |
|---|---|---|
| **Key Vault resource logs** | Access/audit operations, denied accesses khi provider phát | Log Analytics + Storage + SIEM qua Event Hubs |
| **Subscription Activity Log** | Ai đã thay configuration/role/network | Log Analytics, archive nếu policy yêu cầu |
| **App Service resource logs/metrics** | HTTP requests/response categories mà service hỗ trợ | Log Analytics |
| **Spring Boot Application Insights** | Exception stack, dependency calls, trace ID | App Insights workspace/telemetry pipeline |
| **Azure SQL logs/metrics** | DB failures/performance/diagnostics khi hỗ trợ | Log Analytics/metric alerts |

Không mặc định Key Vault audit log cho biết toàn bộ **secret value** đã truy cập, và cũng không nên ghi secret value vào diagnostic pipeline. Audit thường nhằm mô tả request/operation/principal/result, không làm bản sao secret.

### 23.4. Timeline điều tra

~~~text
09:10 UTC  Activity Log: network/role change involving Key Vault
09:19 UTC  Key Vault audit: increase in denied SecretGet operations
09:20 UTC  App Insights: dependency failure and HTTP 500 spike
09:22 UTC  KQL dashboard: signals correlated by resource/time
09:26 UTC  SRE validates configuration and reaches on-call owner
09:35 UTC  Approved mitigation restores access
09:42 UTC  Error rate and freshness verified after deployment change
~~~

Các mốc chỉ là **tình huống học tập**, không phải số liệu Azure thật. Việc hai sự kiện gần nhau về thời gian **chưa chứng minh root cause**; phải xem operation details, request traces, principal/network identity và thay đổi được phê duyệt.

### 23.5. Một query quan sát log volume

Giả sử dữ liệu đi vào `AzureDiagnostics`:

~~~kusto
let StartUtc = datetime(2026-11-20T09:00:00Z);
let EndUtc = datetime(2026-11-20T10:00:00Z);
AzureDiagnostics
| where TimeGenerated >= StartUtc and TimeGenerated < EndUtc
| summarize Events=count()
    by ResourceProvider, Category, bin(TimeGenerated, 5m)
| order by TimeGenerated asc
~~~

Đọc kết quả như một **bảng số sự kiện**; đừng lấy count Key Vault logs = count HTTP 500. Nếu table mode là Dedicated, đổi query theo bảng thực. Với application trace correlation, dùng KQL cho bảng Application Insights có trace/dependency data và đúng correlation key.

### 23.6. Bằng chứng đến archive và SIEM

**Đừng chỉ kiểm tra Log Analytics.** Security/compliance cần trả lời:

1. Blob audit cho khoảng 09:10–09:30 có tồn tại, đọc được, retention/immutability đúng?
2. Event Hubs IncomingMessages có tăng trong thời gian đó?
3. SIEM consumer có nhận/parsing đúng records, có duplicate/drop?
4. Timestamps và resource IDs giữa đích có đồng nhất ở mức schema cần thiết?
5. Nếu SIEM tạm ngừng, có archive/replay plan?

### 23.7. Sửa sự cố và ngăn tái diễn

- Khôi phục change gây lỗi bằng quy trình được phê duyệt; không cấp toàn quyền Key Vault vĩnh viễn.
- Spring Boot cần xử lý SecretGet failure rõ, không trả raw internals cho client.
- Thiết lập Alert/Policy khi Key Vault network/role diagnostic setting thay đổi.
- Có alert từ KQL cho denied operations theo đúng schema, baseline và safety.
- Archive audit logs theo chính sách, giới hạn quyền xóa.
- Regression test trước khi thay network/identity trong CI.
- Xác minh pipeline telemetry **vẫn hoạt động sau mitigation**, không xem “HTTP 500 về 0” là bằng chứng đã lấy đủ audit logs.

## 24. Lab end-to-end: Key Vault → Log Analytics → Storage/Event Hubs

Lab có hai mức: **A. chỉ đọc/thiết kế** khi không có Azure resources, và **B. áp dụng thực tế trên resource được phê duyệt**. Không tự tạo resource hoặc thay network/firewall trong production khi chưa được phép.

### 24.1. Preflight

| Biến | Ý nghĩa | Mức độ nhạy cảm |
|---|---|---|
| `SOURCE_ID` | ARM ID của Key Vault lab | Metadata, không phải key |
| `WORKSPACE_ID` | ARM ID Log Analytics workspace | Metadata |
| `STORAGE_ID` | ARM ID Storage archive nếu dùng | Metadata |
| `EVENT_HUB_RULE_ID` | ARM ID Event Hubs authorization rule | Metadata; không phải key value |
| `EVENT_HUB_NAME` | Hub nhận diagnostic records | Metadata |
| `SETTING_NAME` | Tên diagnostic setting | Metadata |
| `SPRING_APP_ID` | App resource để liên hệ khi điều tra | Metadata |

Không đặt **Storage account key, Event Hubs connection string hoặc Key Vault secret values** vào README/pipeline output/logs. Các biến ở bảng là resource IDs/tên, không phải credential strings.

### 24.2. Lab A — không thay đổi Azure

1. Vẽ data flow gồm Key Vault resource logs, Activity Log, App Insights, Log Analytics, Storage và Event Hubs.
2. Ghi từng data source thuộc platform logs/metrics, Activity Log, application hay guest OS.
3. Chọn destination theo mục tiêu KQL/audit archive/SIEM.
4. Định nghĩa resource-level diagnostic setting và subscription-level Activity Log setting riêng.
5. Viết thử Azure CLI `categories list`, `diagnostic-settings show/list` và `create` nhưng **không chạy lệnh ghi**.
6. Đánh giá data residency, regional constraints, quyền và network.
7. Viết KQL `AzureDiagnostics`, `AzureActivity` và expected evidence.
8. Thiết kế volume/budget/retention.

**Kết quả học:** hiểu chính xác nguồn, scope, category và đích trước khi có quyền production.

### 24.3. Lab B — áp dụng trên Key Vault lab

**Chỉ khi có approval và các tài nguyên riêng được cấp:**

1. Dùng `az account show` và Portal để xác nhận subscription/resource ID.
2. Dùng `az monitor diagnostic-settings categories list --resource ...` để khám phá categories.
3. Xem những settings hiện có để tránh trùng.
4. Chọn **một** category/group audit được hỗ trợ.
5. Dùng Portal hoặc CLI `create` để xuất vào workspace lab.
6. Đọc lại setting bằng `show`.
7. Tạo một Key Vault test operation an toàn/được phép.
8. Query workspace đúng table mode/UTC range.
9. Ghi **time to first visible record** và các fields đã xác minh.
10. Nếu Storage được phê duyệt, thêm archive destination và xác minh blob thực.
11. Nếu Event Hubs được phê duyệt, thêm stream destination và kiểm tra incoming/consumer.
12. Đối chiếu resource ID/operation across destinations.
13. Đánh giá chi phí và PII.
14. Dọn **chỉ cấu hình lab** theo owner approval.

### 24.4. Bộ lệnh đọc lại có thể copy

~~~bash
az account show --query "{id:id,name:name}" -o table

az monitor diagnostic-settings categories list \
  --resource "$SOURCE_ID" -o json

az monitor diagnostic-settings list \
  --resource "$SOURCE_ID" -o json

az monitor diagnostic-settings show \
  --name "$SETTING_NAME" \
  --resource "$SOURCE_ID" -o json
~~~

Các lệnh là **chỉ đọc**, nhưng yêu cầu token/role truy cập resource tương ứng. Chúng không tạo dữ liệu test hoặc chứng minh data delivery, nên phải kết hợp Portal/KQL/Storage/EH verification.

### 24.5. Acceptance tests

| Test | Kết quả đạt |
|---|---|
| Source scope | `SOURCE_ID` khớp đúng resource/child resource |
| Categories | Được liệt kê là supported trong API |
| Setting | GET trả đúng enabled logs/metrics, destination IDs |
| Log Analytics | Bảng thực có ít nhất một event test tương ứng |
| KQL | UTC time, operation, resource ID và category hợp lệ |
| Storage (nếu dùng) | Blob mới tồn tại, parse được, retention policy đúng |
| Event Hubs (nếu dùng) | Incoming messages tăng và consumer xử lý được |
| Partner (nếu dùng) | SIEM có event và schema matching |
| RBAC | Analyst/auditor có quyền đọc đúng scope, không có xóa không cần thiết |
| Networking | Destination private/firewall restrictions vẫn đáp ứng policy |
| Cost | Ước lượng ingestion + storage + streaming; có owner |
| Monitoring | Có chiến lược phát hiện export bị tắt hoặc không có dữ liệu |

### 24.6. Lab kiểm tra âm tính có kiểm soát

Khi muốn thử lỗi:

- Thử KQL query sai table mode trên workspace **lab**, xác nhận nhận ra bảng thực.
- Thử time range không chứa event, giải thích 0 rows.
- Thử query bằng user **không có data-plane quyền** ở workspace lab, xác minh access denied.
- Thử một Event Hubs consumer sai checkpoint trên hub lab, giải thích lag và retry.

**Không thử bằng cách xóa audit setting, revoke production RBAC, mở firewall toàn Internet hoặc xóa Key Vault production.** Negative testing phải có scope hạn chế và recovery plan.

## 25. Bài tập tổng hợp và đáp án định hướng

### 25.1. Câu hỏi thực hành

1. Diagnostic setting giải quyết vấn đề gì và **không** giải quyết vấn đề gì?
2. Phân biệt platform resource logs, metrics, Activity Log, app traces và VM guest syslog.
3. Khi nào cần Log Analytics thay vì Storage?
4. Vì sao Event Hubs không phải long-term archive?
5. Có cần diagnostic setting riêng trên mỗi Azure resource không?
6. Resource category group `allLogs` có nghĩa gồm cả Entra sign-ins không?
7. Khi nào chọn group `audit` hoặc một category cụ thể?
8. Metric Explorer hiển thị CPU nhưng `AzureMetrics` trống: điều tra gì?
9. Workspace khác region nguồn có thể gặp yêu cầu dữ liệu nào?
10. Storage/Event Hubs region có thể bị ràng buộc so với source thế nào?
11. Vì sao App Service Private Endpoint inbound không giúp export logs từ Azure Monitor?
12. Nêu lệnh CLI để khám phá categories.
13. Nêu lệnh CLI đọc diagnostic settings hiện có.
14. Phân biệt `SOURCE_ID` và `WORKSPACE_ID`.
15. So sánh `AzureDiagnostics` với bảng resource-specific.
16. Tại sao `logAnalyticsDestinationType='Dedicated'` có thể làm KQL cũ không còn đúng?
17. Tại sao Activity Log có setting ở scope subscription?
18. Vì sao cần AMA/DCR để lấy syslog từ VM?
19. Nếu muốn lưu audit 3 năm có policy immutable, đích nào phù hợp?
20. Nếu muốn stream SIEM gần real time, đích nào phù hợp?
21. Một diagnostic setting fan-out sang ba destinations có miễn phí không?
22. Có cách nào giảm volume mà vẫn giữ audit?
23. Nếu workspace không có `AzureDiagnostics` sau 10 phút, cần kiểm tra những gì?
24. Nếu Storage không nhận blobs khi firewall bật, khắc phục theo hướng nào?
25. Nếu EH có messages nhưng SIEM trống, lỗi có thể nằm ở đâu?
26. Vì sao không nên dùng log alert chỉ dựa trên zero events?
27. Tính dữ liệu nguồn mỗi tháng khi logs 15 GB/ngày trong 30 ngày.
28. Mô tả quy trình Policy DeployIfNotExists cho fleet resources.
29. Làm sao phát hiện ai đó xóa diagnostic setting?
30. Nêu cách chứng minh archive audit đọc lại được sau một thời gian dài.

### 25.2. Đáp án mẫu

**Câu 2:** Resource logs đến từ resource provider, metrics là chuỗi số liệu, Activity Log ghi control plane ở subscription, App Insights/OTel ghi traces của ứng dụng, AMA+DCR thu dữ liệu guest OS.

**Câu 6:** `allLogs` là nhóm resource log categories **ở đúng provider/resource**, không tự thu Entra logs, application traces hay VM syslog.

**Câu 12:**

~~~bash
az monitor diagnostic-settings categories list \
  --resource "$SOURCE_ID" --output json
~~~

**Câu 13:**

~~~bash
az monitor diagnostic-settings list \
  --resource "$SOURCE_ID" --output json
~~~

**Câu 16:** Dedicated mode có thể chuyển logs vào bảng resource-specific; KQL hardcode `AzureDiagnostics` có thể không đọc được records mới.

**Câu 19:** Storage Account với lifecycle và immutability policy phù hợp; không coi Event Hubs hay bảng KQL retention ngắn là archive pháp lý.

**Câu 23:** Kiểm tra supported category, đúng resource ID/destination, có test event không, thời gian ingest, bảng dedicated hay shared, KQL time range/permissions và network/region requirements.

**Câu 25:** Kiểm tra consumer group, checkpoint/offset, consumer health/parser/schema mismatch và downstream SIEM ingest/retention.

**Câu 27:** 15 × 30 = **450 GB raw source volume** theo giả định; không nhân với số đích rồi xem đó là billable bytes cố định.

**Câu 29:** Dùng Azure Activity Log/Policy compliance và một kênh giám sát độc lập với diagnostic setting đang được bảo vệ.

### 25.3. Rubric

| Tiêu chí | Điều kiện đạt |
|---|---|
| **Phân loại signals** | Không nhầm resource/platform, Activity, app, guest logs |
| **Destination choice** | Chọn workspace/archive/EH/partner theo use case |
| **Scope và category** | Đúng ARM resource ID và supported category |
| **IaC/CLI** | Lệnh đọc/ghi phân biệt, resource vs subscription scope |
| **Verification** | Có real event test và xác nhận data tới từng destination |
| **Security** | RBAC, TLS/network/firewall, data residency/PII |
| **Cost** | Multi-destination, data volume, retention và cost owner |
| **Reliability** | Monitoring pipeline, lag, duplicates/replay và runbook |

## 26. Checklist production cho diagnostic settings

### 26.1. Trước khi tạo hoặc sửa setting

- [ ] Biết chính xác data source: **resource logs, metrics, Activity Log, Entra logs, application hay guest OS**.
- [ ] Xác định ARM resource ID, subscription, child-resource scope và resource owner.
- [ ] Truy vấn supported log categories/category groups và metric export của nguồn.
- [ ] Có business use case rõ cho mỗi category; không bật `allLogs` chỉ theo thói quen.
- [ ] Chọn Log Analytics/Storage/Event Hubs/partner dựa trên nhu cầu truy vấn, archive, stream và bảo mật.
- [ ] Kiểm tra region constraints của nguồn/destination, data residency và cross-subscription rights.
- [ ] Review existing diagnostic settings để tránh trùng hoặc ghi đè người khác.
- [ ] Xác định destination ownership, retention, budget và on-call owner.
- [ ] Có access model: ai sửa setting, ai query logs, ai xóa archive và ai đọc SIEM.

### 26.2. Cấu hình Log Analytics

- [ ] Workspace ID là ARM resource ID đúng và query access đã được cấp.
- [ ] Table mode **AzureDiagnostics/Dedicated** được quyết định theo provider support.
- [ ] KQL dashboards và alerts dùng đúng actual table/schema.
- [ ] Retention/plan/cost được chọn theo data class và policy.
- [ ] Có thử event thực từ resource lab/staging sau deploy.
- [ ] Đo ingestion delay, không dùng query 0 records làm bằng chứng service khỏe.
- [ ] Bảo vệ workspace RBAC/table access và không export PII không cần thiết.
- [ ] Có query/usage monitoring cho các categories volume lớn.

### 26.3. Cấu hình Storage archive

- [ ] Account ở region hợp lệ so với nguồn và phù hợp data residency.
- [ ] Firewall/trusted service/network policy cho diagnostic export đã được kiểm chứng.
- [ ] Storage RBAC tách archive reader và retention admin.
- [ ] Lifecycle, replication, encryption và immutability policy được review.
- [ ] Test tạo blob/đọc JSON/khôi phục theo partition và time range.
- [ ] Không đặt auto-delete audit ngắn hơn chính sách pháp lý.
- [ ] Có alerts khi archive pipeline dừng hoặc storage resources bất thường.

### 26.4. Cấu hình Event Hubs hoặc partner

- [ ] Namespace/hub/authorization rule ID đúng, không truyền SAS key plaintext trong IaC.
- [ ] Region, trusted services, network firewall và quotas được kiểm chứng.
- [ ] Consumer groups/checkpoint/replay/poison-message handling có owner.
- [ ] Kiểm tra incoming messages **và** SIEM/downstream persistence.
- [ ] Retention đủ cho downtime, có long-term archive nếu yêu cầu.
- [ ] Schema/version/dedup và data classification được kiểm tra.
- [ ] Partner contract, permissions, data residency/egress có approval.

### 26.5. IaC và governance

- [ ] Diagnostic settings nằm trong Bicep/Terraform/ARM/Policy được quản lý.
- [ ] PR review kiểm tra scope, destinations, categories, retention impact.
- [ ] Policy assignments có remediation identity với least privilege.
- [ ] Compliance dashboard **không thay end-to-end data delivery test**.
- [ ] Có cảnh báo Activity Log/Policy khi critical settings bị sửa/xóa.
- [ ] Có change records, affected resource inventory và rollback plan.
- [ ] New resource provisioning tự động nhận monitoring baseline phù hợp.
- [ ] Không thay scopes, destinations hoặc table mode mà quên sửa KQL queries.

### 26.6. Sau khi thay đổi

- [ ] GET setting cho thấy các categories/metrics/IDs đúng.
- [ ] Một event test đã được xác minh đến **từng destination bắt buộc**.
- [ ] KQL/Blob/consumer có timestamps, category và resource ID khớp.
- [ ] Không có destination failure, Event Hubs backlog/throttling hoặc quota issue.
- [ ] SRE/SOC có runbooks và quyền đọc phù hợp.
- [ ] Kiểm tra Cost Management/data volume trong kỳ tiếp theo.
- [ ] Có bằng chứng audit/change approval và owner ký xác nhận.

## 27. Dọn dẹp lab an toàn, không làm mất nhật ký audit

Một diagnostic setting và destination có thể phục vụ nhiều nhóm. Xóa nhầm setting có thể **làm gián đoạn bằng chứng audit**; xóa Storage hoặc workspace có thể mất dữ liệu đang được nhiều hệ thống sử dụng.

### 27.1. Trước khi xóa

1. Xác nhận subscription, source resource ID và setting name.
2. Đọc cấu hình và xác định destination có dùng chung không.
3. Kiểm tra Policy/CI có tự tái tạo setting nếu bị xóa hay không.
4. Xác định source có yêu cầu audit/compliance/incident hold không.
5. Nếu cần lưu bằng chứng, export/retain bằng cơ chế hợp lệ trước thay đổi.
6. Có owner approval và ticket đổi cấu hình.
7. Xác nhận cleanup không mở rộng sang resource group hoặc workspace shared.

### 27.2. Các lệnh chỉ đọc trước cleanup

~~~bash
az account show --query "{id:id,name:name}" -o table

az monitor diagnostic-settings list \
  --resource "$SOURCE_ID" \
  --output json

az monitor diagnostic-settings show \
  --resource "$SOURCE_ID" \
  --name "$SETTING_NAME" \
  --output json
~~~

Lệnh này chỉ đọc metadata, không động tới dữ liệu. Để xem Storage archive, dùng Storage Blob Data Reader hoặc quyền tương ứng, không cấp Owner subscription chỉ để liệt kê blobs.

### 27.3. Ví dụ lệnh phá hủy — không chạy nếu chưa có approval

~~~bash
# CHỈ LÀ VÍ DỤ ĐƯỢC COMMENT.
# Xóa diagnostic setting làm dừng export từ nguồn theo cấu hình đó.
# az monitor diagnostic-settings delete \
#   --resource "$SOURCE_ID" \
#   --name "$SETTING_NAME"

# KHÔNG xóa toàn resource group/shared workspace/storage
# chỉ để dọn một bài lab.
# az group delete --name "<approved-lab-rg>" --yes
~~~

Không xóa `AzureDiagnostics`/resource-specific tables/Storage containers chứa audit production để “dọn phí”. Với retention immutable, việc xóa có thể bị chặn đúng theo chính sách; không cố vượt guardrail.

### 27.4. Kết quả cleanup cần xác nhận

| Hạng mục | Kỳ vọng |
|---|---|
| Diagnostic setting **lab-only** | Được xóa/sửa theo approval, không ảnh hưởng source khác |
| Workspace trung tâm | Giữ nguyên, vẫn nhận logs các resources khác |
| Archive Storage | Chỉ thay data/policy thuộc lab theo retention rules |
| Event Hubs/SIEM | Không làm gián đoạn consumers chung |
| Azure Policy | Compliance impact được đánh giá và remediation kiểm soát |
| Budget | Không còn tài nguyên lab mới bị bỏ quên |
| Evidence | Báo cáo ghi rõ thao tác, người duyệt và tình trạng sau cleanup |

## 28. Tài liệu tham khảo và ghi nhớ

### 28.1. Nguồn kỹ thuật nên kiểm tra khi triển khai

- [Azure Monitor diagnostic settings](https://learn.microsoft.com/azure/azure-monitor/essentials/diagnostic-settings) — các loại destinations, constraints, setting configuration.
- [Diagnostic settings destination information](https://learn.microsoft.com/azure/azure-monitor/essentials/diagnostic-settings#destinations) — lưu ý Log Analytics, Storage, Event Hubs.
- [Azure Monitor resource logs](https://learn.microsoft.com/azure/azure-monitor/essentials/resource-logs) — category và dữ liệu do resource providers phát.
- [Azure Monitor platform metrics](https://learn.microsoft.com/azure/azure-monitor/essentials/data-platform-metrics) — metrics/aggregation/dimensions.
- [Azure Activity Log](https://learn.microsoft.com/azure/azure-monitor/essentials/activity-log) — control-plane logs ở subscription.
- [Azure Monitor Logs and Log Analytics](https://learn.microsoft.com/azure/azure-monitor/logs/data-platform-logs) — workspace/tables/query/retention.
- [Kusto Query Language](https://learn.microsoft.com/kusto/query/) — cách viết KQL và đọc bảng được ingest.
- [Data Collection Rules](https://learn.microsoft.com/azure/azure-monitor/data-collection/data-collection-rule-overview) — các data sources, transformations và routing khác diagnostic settings.
- [Azure Monitor Agent](https://learn.microsoft.com/azure/azure-monitor/agents/azure-monitor-agent-overview) — guest OS collection.
- [Azure Monitor alerts](https://learn.microsoft.com/azure/azure-monitor/alerts/alerts-overview) — metric/log alerts và action groups.
- [Azure Event Hubs overview](https://learn.microsoft.com/azure/event-hubs/event-hubs-about) — consumers, partitions, throughput và retention.
- [Azure Storage immutable blob storage](https://learn.microsoft.com/azure/storage/blobs/immutable-storage-overview) — WORM/retention.
- [Azure Monitor pricing](https://azure.microsoft.com/pricing/details/monitor/) — ingestion, retention, alerts và các khoản phí liên quan.
- [Azure CLI diagnostic settings commands](https://learn.microsoft.com/cli/azure/monitor/diagnostic-settings) — cú pháp commands và các phiên bản hỗ trợ.

Tên tables, commands, categories, partner integration, API versions và regional features có thể thay đổi. Khi production design, kiểm tra **tài liệu đang áp dụng, supported categories từ chính resource và pricing/RBAC/network constraints của tenant**, không dùng một ví dụ minh họa như bằng chứng mọi resource hỗ trợ giống nhau.

### 28.2. Mười hai điều cốt lõi

1. **Diagnostic settings định tuyến những Azure platform logs/metrics được hỗ trợ**; không tự thu toàn bộ application, guest OS hay identity telemetry.
2. **Scope cực kỳ quan trọng**: resource logs ở resource/child resource; Activity Log ở subscription; Entra logs có configuration riêng.
3. **Category names phải được khám phá**: `allLogs`/`audit`/`AllMetrics` không phải lựa chọn khả dụng cho mọi resource.
4. **Log Analytics cho KQL**, Storage cho archive, Event Hubs cho streaming, partner cho tích hợp đã được phê duyệt.
5. **Một setting có thể định tuyến nhiều đích**, nhưng tăng data duplication, cost và governance complexity.
6. **AzureDiagnostics không phải bảng duy nhất**: Dedicated/resource-specific tables và AzureActivity/AzureMetrics có semantics khác.
7. **Private networking không tự thông đường Azure Monitor delivery**; cần đánh giá region, firewall/trusted services và permissions từng destination.
8. **Azure RBAC để chỉnh setting khác data-plane rights để đọc logs/archive/consume Event Hubs**.
9. **Cấu hình thành công không chứng minh dữ liệu đã đến**: cần test event từ nguồn và kiểm chứng từng destination.
10. **Logs có thể đến trễ, bị trùng hoặc không phát**: đừng lấy 0 events làm 0 lỗi/100% availability.
11. **Bảo mật, retention và chi phí đi cùng nhau**: không bật `allLogs` hoặc lưu mọi payload vô hạn mà không có policy.
12. **Diagnostic settings phải được quản bằng IaC/Policy và tự được giám sát**: setting change, data freshness, delivery failures, SIEM consumer lag và archive integrity.

### 28.3. Kết luận

Một kiến trúc **Diagnostic setting và đích xuất dữ liệu giám sát** trên Azure chỉ thực sự vận hành tốt khi **đúng nguồn và phạm vi, đúng supported categories, đúng Log Analytics/Storage/Event Hubs hoặc partner destination, đúng quyền và kết nối mạng, dữ liệu được xác minh từ sự kiện nguồn đến nơi tiêu thụ, đồng thời có chiến lược retention, audit, cảnh báo, chi phí, phục hồi và quản trị thay đổi rõ ràng**.
