# Metric alert, log alert và action group

Một ứng dụng Spring Boot trên Azure Container Apps vẫn trả HTTP 200 cho trang chủ nhưng 15% giao dịch thanh toán thất bại. Cùng lúc, một Azure Virtual Machine duy trì CPU gần 95% và pipeline dữ liệu không ghi bản ghi mới suốt nửa giờ. Dashboard thể hiện tình trạng này, nhưng người vận hành không thể ngồi quan sát liên tục. Nếu gửi email mỗi khi CPU tăng trong vài giây, đội trực lại bị **alert fatigue** và có thể bỏ qua sự cố nghiêm trọng.

Trong **Azure Monitor**, **metric alert** theo dõi số đo theo thời gian; **log alert** dùng truy vấn nhật ký, thường dưới dạng **scheduled query rule**; **action group** quyết định ai hoặc hệ thống nào được thông báo/kích hoạt khi alert xảy ra. Một thiết kế đúng phải xác định **tín hiệu đáng tin, phạm vi, aggregation, ngưỡng, window, tần suất đánh giá, xử lý mất dữ liệu, vòng đời cảnh báo, người trực và hành động an toàn**. Bài này dạy cách xây dựng chuỗi từ quan sát đến ứng cứu, không chỉ cách bấm nút tạo alert.

Bài học thuộc chương **Giám sát và quan sát hệ thống** của module **CLOUD_PROVIDERS_AZURE**: khám phá Azure từ subscription, resource group, Microsoft Entra ID đến virtual network, compute, storage và dữ liệu, sau đó triển khai, giám sát, bảo vệ và kiểm soát chi phí kiến trúc ứng dụng. Ví dụ dựa trên Azure Monitor, Azure Metrics, Log Analytics, workspace-based Application Insights và Azure Resource Manager (ARM).

> **Phạm vi và phiên bản:** Azure Monitor cung cấp thêm Activity Log alerts, Prometheus rule groups, availability tests và các loại tín hiệu khác; bài này tập trung metric alerts, scheduled-query log alerts và action groups. Metric names, KQL tables, supported aggregation/dimensions, Azure CLI/Bicep schema, limits và billing có thể thay đổi theo resource, region, cấu hình và thời điểm. Lệnh là ví dụ lab, không xác nhận đã được chạy trên subscription thật. Không dùng webhook/email thật ngoài phạm vi được phép.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt metric, log, trace, Activity Log và sự kiện Azure Monitor.
2. Chọn metric alert hoặc log alert dựa trên tín hiệu/SLO.
3. Cấu hình scope, signal, aggregation, threshold, dimensions, window size, evaluation frequency và severity.
4. Phân biệt static/dynamic threshold, stateful/stateless và Fired/Resolved.
5. Viết KQL để phát hiện count, error rate, missing heartbeat và dữ liệu trễ.
6. Hiểu log alert dựa trên **row count** so với **numeric measure**.
7. Tạo action group với receivers, common alert schema và test delivery.
8. Phân biệt action group với **alert processing rule** và suppression.
9. Xây ví dụ metric alert, log alert, action group qua Portal, CLI và Bicep.
10. Thiết kế 401/403 và identity permissions cho người triển khai/automation.
11. Giảm false positives, duplicate notifications và cardinality explosion.
12. Tính SLO/error budget, kiểm thử end-to-end và xử lý sự cố.
13. Theo dõi latency/availability, logs ingestion, cost/retention và reliability của notification.
14. Lập runbook, ownership, escalation và rollback cho production.

## 2. Mô hình end-to-end: dữ liệu, điều kiện, hành động

~~~mermaid
flowchart LR
  RES["VM / App / Storage / Database"] --> MET["Azure Monitor Metrics"]
  RES --> LOG["Resource logs / App Insights"]
  MET --> MA["Metric alert rule"]
  LOG --> LA["Log Analytics / KQL"]
  LA --> SQ["Scheduled query rule"]
  MA --> INST["Alert instance: Fired / Resolved"]
  SQ --> INST
  INST --> PROCESS["Alert processing rule"]
  PROCESS --> AG["Action group"]
  AG --> EMAIL["Email / SMS"]
  AG --> WORK["Webhook / Logic App / Function"]
  INST --> PORTAL["Alerts UI / incidents"]
~~~

**Bốn lớp cần tách biệt:**

- **Telemetry:** một VM phát metric CPU; Spring Boot gửi request/exception logs vào workspace.
- **Alert rule:** một cấu hình được Azure Monitor đánh giá định kỳ dựa trên nguồn telemetry.
- **Alert instance:** một lần vi phạm điều kiện, có lifecycle và metadata điều kiện.
- **Action delivery:** action group và alert processing rules quyết định thông báo/automation.

**Action group không tạo telemetry và không định nghĩa threshold.** Rule fire thành công cũng không đảm bảo email đến hộp thư; receiver delivery cần kiểm thử riêng. Một processing rule suppress thông báo không có nghĩa điều kiện đã khỏe.

## 3. Metrics, logs và các signal khác

| Signal | Dạng dữ liệu | Ưu thế | Giới hạn |
|---|---|---|---|
| **Platform metrics** | Numeric time series, có dimensions | Theo dõi nhanh CPU, request count, saturation | Không chứa toàn bộ business context |
| **Application/custom metrics** | Số đo do app phát ra | SLO và business indicators | Phụ thuộc instrumentation |
| **Resource logs** | Records có timestamp/fields | Phân tích chi tiết 4xx/5xx, diagnostics | Ingestion delay, KQL, retention và cost |
| **Application Insights** | Requests, exceptions, dependencies, traces | Chẩn đoán ứng dụng end-to-end | Sampling, instrument/ingest, schema |
| **Activity Log** | Subscription control-plane events | Ai sửa resource/role/policy | Không thay application data-plane logs |
| **Prometheus metrics** | Prometheus series từ AKS/containers | Kubernetes workloads | Alert rule groups, metric pipeline riêng |

**Không nhầm Azure Monitor Logs và Azure Activity Log.** Nếu cần “ai xóa một resource group?”, Activity Log alert có thể phù hợp hơn scheduled KQL query. Nếu cần “payment endpoint có lỗi 5xx với correlation ID?”, Application Insights/Log Analytics hỗ trợ chi tiết.

## 4. Khi nào dùng metric alert?

Chọn **metric alert** khi nguồn Azure đã có số đo với metric name/aggregation phù hợp, và cần thông báo sớm khi vượt ngưỡng:

- VM `Percentage CPU` quá cao kéo dài.
- Queue backlog tăng vượt giới hạn.
- Storage latency/availability theo metric có sẵn.
- HTTP requests/5xx count hoặc duration metric được resource phát ra.
- Disk free/memory metric đã được agent/custom metrics cung cấp (không mặc định có với mọi VM).

### Ví dụ CPU

~~~text
Scope: vm-monitor-lab
Metric: Percentage CPU
Aggregation: Average
Operator: Greater than
Threshold: 80 (%)
Window size: 5 minutes
Evaluation frequency: 1 minute
Severity: Sev2
Action group: ag-platform-oncall-lab
~~~

Rule xem dữ liệu metric của cửa sổ 5 phút và đánh giá theo lịch. **Average > 80** không đồng nghĩa mỗi phút đều >80, và **Greater than** khác **Greater than or equal to**.

### Sự khác nhau giữa các aggregations

~~~text
CPU samples over five minutes: 65, 77, 82, 91, 95 (%)
Average = (65+77+82+91+95) / 5 = 82%
Maximum = 95%
Minimum = 65%
~~~

Nếu Average >80 sẽ phản ánh tải cao hơn trong cả cửa sổ. Nếu Maximum >80, chỉ một spike ngắn đã đủ. Còn với **Requests** metric, nên tìm hiểu `Total` là số requests trong khoảng nào thay vì lấy Average tùy ý.

## 5. Thành phần của metric alert

| Trường | Vai trò | Sai sót phổ biến |
|---|---|---|
| `scopes` | Những Azure resource IDs được theo dõi | Chọn sai workspace/VM/region |
| `metricName` | Metric cụ thể có sẵn | Tên không tồn tại trong namespace |
| `metricNamespace` | Namespace số đo | Nhầm service/agent metric |
| `timeAggregation` | Average, Total, Maximum, Minimum, Count... | Không phù hợp unit/meaning |
| `operator` | GreaterThan, LessThan... | So lệch dấu |
| `threshold` | Ngưỡng kích hoạt | Không dựa vào baseline |
| `windowSize` | Khoảng dữ liệu tổng hợp | Quá ngắn, alert chập chờn |
| `evaluationFrequency` | Chu kỳ đánh giá | Quá dày so với signal collection |
| `dimensions` | Bộ lọc/tách theo region, instance... | Quá nhiều series |
| `severity` | Sev0–Sev4 | Tất cả alerts đều Sev0 |
| `enabled` | Bật/tắt rule | Quên bật |
| `actions` | Action group references | Chưa cấu hình receiver |

Có thể có thêm policy động, multi-resource target resource type/region, autoMitigate và fields riêng theo API version. **Chỉ chọn aggregation mà nguồn metric hỗ trợ**. Dùng Metrics Explorer/metric definitions để xem unit và dimension names thật.

## 6. Chọn aggregation và cửa sổ theo mục tiêu

| Mục tiêu | Số đo | Lựa chọn tham khảo |
|---|---|---|
| CPU saturation | CPU % | Average 5–15 phút |
| Disk gần hết | Free space nếu đã có | Minimum trong cửa sổ |
| Queue tồn đọng | Active messages | Maximum hoặc Average |
| Số lượng lỗi 5xx | Failed requests | Total |
| Requests tăng bất thường | Request count | Total, cân nhắc traffic baseline |
| Latency đuôi | p95/p99 metric nếu có | Đừng dùng Average thay p95 |
| Availability | Probe success metric nếu có | Tối thiểu nhiều kết quả fail |
| Freshness | Last success timestamp/custom metric | Cần logic no-data riêng |

**Ý nghĩa của window size:** thời gian mà một lần đánh giá dùng để tổng hợp telemetry, không mặc nhiên là “điều kiện phải liên tục true đúng từng giây”. Một rule 5 phút window, 1 phút frequency có các cửa sổ chồng lên nhau. Không nhân số lần evaluation với số samples rồi cho rằng có đúng N điểm.

### Lựa chọn severity

- **Sev0:** khẩn cấp, mất dịch vụ diện rộng, điều phối sự cố ngay.
- **Sev1:** tác động lớn, cần on-call response.
- **Sev2:** degradation có mức ảnh hưởng đáng kể.
- **Sev3:** cảnh báo vận hành cần xử lý nhưng không cấp cứu.
- **Sev4:** thông tin/tình trạng cần xem xét.

Đây là khung vận hành minh họa; severity thực phải theo **incident policy và user impact**, không chỉ ngưỡng CPU.

## 7. Static threshold và dynamic threshold

### Static threshold

~~~text
CPU Average > 80%
Queue active messages > 1,000
Disk free < 10 GiB
HTTP 5xx rate > 5% with minimum sample count
~~~

Thích hợp khi có giới hạn kỹ thuật/budget cụ thể. Nhưng traffic giờ cao điểm và thấp điểm khác nhau có thể dẫn tới false positives.

### Dynamic threshold

Với metrics/tính năng được hỗ trợ, Azure Monitor có thể học baseline lịch sử rồi cảnh báo khi chuỗi số khác hành vi thông thường. Cấu hình có thể gồm **sensitivity**, hướng bất thường, số lần vi phạm và học baseline.

Hạn chế:

- Cần dữ liệu lịch sử đủ tốt; alert mới chưa chắc có baseline đáng tin ngay.
- Sự kiện theo mùa/holiday/deploy release có thể ảnh hưởng.
- “Bình thường theo lịch sử” không đồng nghĩa đáp ứng SLO.
- Không phải mọi metric và dimension đều hỗ trợ.
- Khi absolute limit rõ (disk cạn), static threshold thường dễ giải thích hơn.

Không áp dynamic threshold để thay thế capacity planning/SLO. Đo false positive, false negative trước/sau áp dụng.

## 8. Dimensions, multi-resource scope và cardinality

Giả sử metric requests có dimensions:

~~~text
region = eastasia, southeastasia       (2)
status = 200, 400, 401, 404, 500, 503 (6)
instance = 1..20                       (20)
Theoretical combinations: 2 * 6 * 20 = 240 series
~~~

Kích thước series thực phụ thuộc source và combinations có xuất hiện, nhưng alert theo mỗi dimension có thể tạo rất nhiều **independent alert instances** và chi phí/notifications.

Nguyên tắc:

1. Chỉ chia theo dimension nếu owner/runbook **có hành động khác nhau**.
2. Không dùng `userId`, `requestId`, order ID làm dimension mặc định vì cardinality quá cao.
3. Giám sát service-level SLO trước, tách region/instance để chẩn đoán.
4. Với alert scope nhiều resources, kiểm tra loại, region và cấu hình `targetResourceType`/`targetResourceRegion` theo khả năng hỗ trợ.
5. Tránh alert per-pod trên Kubernetes khi pod liên tục được tạo/xóa; ưu tiên service health.
6. Kiểm tra **pricing metric time series** và limit trước khi bật split.

## 9. Stateful, stateless, Fired và Resolved

**Stateful alert** thể hiện trạng thái một vấn đề. Khi vượt ngưỡng → Fired; khi điều kiện phục hồi và rule đánh giá xong → Resolved. Một lần Fired có thể kéo dài qua nhiều evaluations.

**Stateless alert** có thể thông báo lại ở mỗi lần evaluation phù hợp, tùy loại rule/cấu hình, thuận tiện cho event-like condition nhưng dễ noise.

~~~mermaid
stateDiagram-v2
  [*] --> Healthy
  Healthy --> Fired: threshold breached
  Fired --> Fired: condition still true
  Fired --> Resolved: recovery condition
  Resolved --> Healthy: next cycle
~~~

**Không giả định Azure giải quyết alert ngay sau một lần query ra 0.** Resolution state/timing, autoMitigate và suppression khác theo metric, scheduled query và API version.

### Alert condition khác user acknowledgement

- **Monitor condition** (Fired/Resolved): điều kiện telemetry.
- **User state** (New/Acknowledged/Closed khi hỗ trợ): phản ánh quy trình xử lý của con người.

Đánh dấu incident là “acknowledged” không làm CPU giảm. Tương tự, metric trở lại bình thường không có nghĩa root cause đã được giải quyết.

## 10. Tạo metric alert trong Azure Portal

Ví dụ giám sát VM lab:

1. Mở **Azure Portal → Monitor → Alerts → Create alert rule**, hoặc từ VM → Alerts.
2. Scope đúng **VM resource ID** và subscription.
3. Chọn signal `Percentage CPU`.
4. Chọn Average, operator Greater than, threshold 80%.
5. Window size 5 minutes, evaluation 1 minute nếu signal hỗ trợ.
6. Severity Sev2, mô tả **owner, user impact, runbook URL**.
7. Gắn action group của nhóm trực lab.
8. Xem resource group/tags, Review + Create.
9. Sau tạo, kiểm tra rule Enabled, scopes, condition và actions.
10. Đo output khi tạo traffic/tải **có kiểm soát**.

Đừng ép CPU lên 100% trên production chỉ để test. Dùng VM sandbox hoặc thay threshold trên một rule **thử nghiệm tạm** rồi revert.

## 11. Azure CLI: kiểm tra metric source trước khi tạo

~~~bash
az account show \
  --query "{subscription:name,subscriptionId:id,tenantId:tenantId}" \
  -o json

RG="rg-observability-lab"
VM_NAME="vm-monitor-lab"

VM_ID=$(az vm show -g "$RG" -n "$VM_NAME" --query id -o tsv)

az monitor metrics list-definitions \
  --resource "$VM_ID" \
  --query "[].{name:name.value,unit:unit}" \
  -o table

az monitor metrics list \
  --resource "$VM_ID" \
  --metric "Percentage CPU" \
  --aggregation Average \
  --interval PT1M \
  -o json
~~~

Các lệnh chỉ đọc; metric definitions và data availability tùy loại resource, region và phiên bản CLI. Nếu query không có sample, xác minh time range/sampling interval trước khi tạo rule.

### Tạo metric alert minh họa

~~~bash
AG_ID="<ACTION_GROUP_RESOURCE_ID>"

az monitor metrics alert create \
  --name "alert-vm-cpu-high-lab" \
  --resource-group "$RG" \
  --scopes "$VM_ID" \
  --condition "avg Percentage CPU > 80" \
  --window-size 5m \
  --evaluation-frequency 1m \
  --severity 2 \
  --action "$AG_ID" \
  --description "VM CPU average >80% over 5m"
~~~

Đây là **mẫu CLI phổ biến**, phải kiểm tra `az monitor metrics alert create -h` trên phiên bản cài đặt, nhất là cú pháp `--condition`, resource type/region và `--action`. Thành công khi chạy create **không chứng minh** rule đã từng Fired hoặc notification đã đến.

### Kiểm tra cấu hình

~~~bash
az monitor metrics alert show \
  --resource-group "$RG" \
  --name "alert-vm-cpu-high-lab" \
  -o json
~~~

So sánh scopes, criteria, severity, frequency, window size, actionGroupId và enabled với thiết kế.

## 12. Action group là gì?

**Action group** là tài nguyên Azure Monitor cấu hình tập các receivers/actions: email, SMS/voice/push tùy khả năng, webhook, Logic Apps, Azure Functions, Event Hubs, ITSM hoặc integrations khác.

~~~mermaid
flowchart TD
  AL["Azure alert Fired"] --> AG["Action group"]
  AG --> EMAIL["On-call email"]
  AG --> SMS["SMS / push nếu hỗ trợ"]
  AG --> LOGIC["Logic App router"]
  AG --> HOOK["Webhook / incident service"]
  LOGIC --> TICKET["Ticket / escalation"]
~~~

Action group có thể tái sử dụng ở nhiều alert rules. Nó **không chọn signal và không kiểm soát threshold**; chỉ được gọi khi rule/processing flow kích hoạt hành động phù hợp.

### Bốn vấn đề cần thiết kế

1. **Ai nhận:** nhóm on-call, service owner, security hoặc dữ liệu.
2. **Độ khẩn cấp:** email, paging, incident ticket, automation.
3. **Payload:** common alert schema hay receiver-specific schema.
4. **Reliability:** xác thực, retry, idempotency, logging và failover.

Không cấu hình Sev4 gửi SMS lúc nửa đêm như Sev0.

## 13. Action group receiver types và an toàn

| Receiver | Sử dụng | Rủi ro/quyết định |
|---|---|---|
| Email | Alert ít khẩn cấp/team inbox | Ownership, spam, người nhận đã chuyển nhóm |
| SMS/Voice | Paging sự cố nghiêm trọng | Region/support, chi phí, consent |
| Push | Thiết bị/app tương thích | Quản lý enrollment và coverage |
| Webhook | Incident platform/custom handler | HTTPS, authentication, idempotency |
| Logic App | Router/escalation/ticket | Permissions, workflow costs/retries |
| Azure Function | Custom remediation | Quá quyền, infinite loop, secret safety |
| Event Hubs | Streaming event pipeline | Consumer lag, replay, retention |
| ITSM | Incident/ticket bên thứ ba | Duplicate ticket, connector credential |
| Automation Runbook | Một số playbook có điều kiện | Approval, allowlisted actions, rollback |

**Webhook HTTPS không tự đảm bảo request đến từ Azure Monitor.** Xác thực receiver bằng cơ chế được hỗ trợ, tránh long-lived URLs/keys bị lộ trong code/logs, giới hạn IP/identity hoặc đặt gateway nếu phù hợp. Không cho alert receiver mặc định có Owner trên subscription.

## 14. Common Alert Schema

**Common Alert Schema** chuẩn hóa payload cho các loại alerts và receiver types hỗ trợ, giúp automation parse các trường chính. Ví dụ rút gọn:

~~~json
{
  "schemaId": "azureMonitorCommonAlertSchema",
  "data": {
    "essentials": {
      "alertId": "<ALERT_INSTANCE_ID>",
      "alertRule": "alert-vm-cpu-high-lab",
      "severity": "Sev2",
      "signalType": "Metric",
      "monitorCondition": "Fired",
      "firedDateTime": "2026-11-20T11:00:00Z",
      "alertTargetIDs": ["<AZURE_RESOURCE_ID>"]
    },
    "alertContext": {
      "conditionType": "SingleResourceMultipleMetricCriteria"
    }
  }
}
~~~

Đây là **minh họa**, không phải full schema của tất cả cảnh báo. `alertContext` khác nhau theo metric/log/activity types, API versions và signal. Không parse một `metricValue` bắt buộc cho log alerts.

### Receiver phải idempotent

- Dùng `alertId` + condition/correlation để dedup, tránh tạo 10 incident giống nhau khi webhook retry.
- Khi nhận `Resolved`, cập nhật incident tương ứng thay vì tạo incident mới.
- Nếu không nhận đủ bối cảnh, gọi API/CMDB an toàn thay vì tự đoán tenant.
- Không lưu raw query chứa PII hoặc secrets trong public ticket.
- Có retry/dead-letter cho hành động thất bại, tránh vòng lặp alert → remediation → alert.

## 15. Tạo action group trong Portal và CLI

Portal: **Monitor → Alerts → Action groups → Create**. Chọn subscription, resource group, đặt name và short name, thêm receiver có email **lab được phép**, bật common alert schema cho receiver thích hợp, review/create, rồi **Test action group** và xác minh thông báo đã đến.

CLI ví dụ tạo object action group ban đầu:

~~~bash
RG="rg-observability-lab"

az monitor action-group create \
  --name "ag-platform-oncall-lab" \
  --resource-group "$RG" \
  --short-name "platform"

az monitor action-group show \
  --name "ag-platform-oncall-lab" \
  --resource-group "$RG" -o json
~~~

**Chưa có receivers thì chưa gửi email.** Thêm receiver bằng CLI/API/Portal theo schema phiên bản thật. Với tự động hóa, ưu tiên Bicep cấu hình có receivers cụ thể thay vì phụ thuộc thao tác UI không được lưu Git.

Lấy ARM ID:

~~~bash
AG_ID=$(az monitor action-group show \
  --name "ag-platform-oncall-lab" -g "$RG" \
  --query id -o tsv)
~~~

**Test action group không kiểm tra trigger condition.** Cần test cả đường rule firing và route/delivery.

## 16. Log alert là gì?

**Scheduled query rule** chạy truy vấn **KQL** trên Log Analytics/workspace hoặc resource scopes được hỗ trợ, so kết quả với threshold. Dùng khi cần tìm patterns không có trong platform metrics:

- Số request `checkout` thất bại quá nhiều.
- Lỗi `status=500` đồng thời trên nhiều dependencies.
- Không có bản ghi `payment-succeeded` trong khoảng thời gian cần có.
- Một operation `Key Vault SecretGet` bị từ chối lặp nhiều lần.
- Một số tenants có lỗi đặc trưng sau deployment.
- Transaction/business rule bị vi phạm theo query.

~~~mermaid
flowchart LR
  APP["Spring Boot / Azure resource"] --> DIAG["App Insights / diagnostic settings"]
  DIAG --> LA["Log Analytics workspace"]
  LA --> KQL["Scheduled KQL query"]
  KQL --> TEST{"Count/measure threshold?"}
  TEST -->|Yes| ALERT["Log alert fired"]
  ALERT --> AG["Action group"]
  TEST -->|No| NEXT["Next evaluation"]
~~~

Log alert cần **data ingestion**. Nếu logs chưa được gửi tới workspace hoặc sampling đã loại bỏ request cần theo dõi, query có thể trả không hàng nào ngay cả khi ứng dụng đang lỗi.

## 17. KQL: xác minh bảng trước khi tạo alert

Giả sử dùng workspace-based Application Insights có bảng `AppRequests`. Hãy mở Log Analytics Logs, xác nhận bảng và cột:

~~~kusto
AppRequests
| where TimeGenerated >= ago(15m)
| project TimeGenerated, OperationName, ResultCode, Success, DurationMs, _ResourceId
| take 20
~~~

Không phải mọi workspace đều có `AppRequests`. Nếu dùng legacy Application Insights hoặc resource-specific logs khác, cần chỉnh đúng bảng (ví dụ `requests` ở context tương ứng). **Không tạo rule dựa vào bảng chưa được ingest.**

Một số Azure resource logs có thể được gửi vào bảng tổng hợp `AzureDiagnostics` (chế độ cũ) hoặc các **resource-specific tables** tùy diagnostic settings. Các bảng đó có schema khác `AppRequests`: hãy kiểm tra đúng table, columns, categories và workspace data trước khi xây log alert; đổi bảng một cách cơ học mà không sửa KQL sẽ làm rule sai.

### Đếm các request thất bại

~~~kusto
AppRequests
| where TimeGenerated >= ago(15m)
| where _ResourceId =~ "<APP_INSIGHTS_RESOURCE_ID>"
| where Success == false
| project TimeGenerated, OperationName, ResultCode
~~~

Query trả **một hàng cho mỗi request lỗi**. Nếu rule so **number of rows > 20**, đây là logic hợp lý. Chú ý query filter phải giới hạn đúng ứng dụng/scope; một workspace có thể chứa logs của nhiều resources.

## 18. Row count khác numeric measure

### Row-count alert

~~~kusto
AppRequests
| where TimeGenerated >= ago(15m)
| where Success == false
~~~

Nếu có 42 bản ghi, **row count = 42**.

### Numeric-measure alert

~~~kusto
AppRequests
| where TimeGenerated >= ago(15m)
| summarize FailedRequests = countif(Success == false)
~~~

Query trả **một hàng** và cột `FailedRequests=42`. Nếu tạo rule “row count >20”, nó sẽ không fire vì chỉ có **1 row**. Phải cấu hình **measure column = FailedRequests** với aggregation/operator/threshold phù hợp.

### Tỷ lệ lỗi

~~~kusto
AppRequests
| where TimeGenerated >= ago(15m)
| summarize Total=count(), Failed=countif(Success == false)
| extend FailureRatePct =
    iff(Total == 0, real(null), 100.0 * todouble(Failed) / todouble(Total))
| where Total >= 100
| project FailureRatePct
~~~

`Total>=100` là guard chống nhiễu khi traffic thấp: 1 lỗi/1 request = 100%, không nhất thiết là outage diện rộng. **Nhưng 0 requests có thể là một outage**, nên cần availability/heartbeat/no-data alert riêng.

### Cửa sổ và lịch đánh giá

Ví dụ **window 15 phút, evaluation frequency 5 phút**: cùng một request có thể được đếm ở nhiều evaluations vì các cửa sổ chồng lấn. Stateful alert hạn chế duplication ở tầng notifications, nhưng không nên tính mỗi evaluation là một incident riêng. Tần suất cũng cần cân đối với **ingestion lag**.

## 19. Scheduled query rules: cấu hình đúng điều kiện

Một **scheduled query log alert** thường có những thành phần:

| Thuộc tính | Ý nghĩa |
|---|---|
| **Scope** | Log Analytics workspace hoặc resource có query access được hỗ trợ |
| **Query** | KQL tạo rows hoặc numeric measure |
| **Measure** | Number of rows hoặc measurement column |
| **Operator/threshold** | So giá trị kết quả với ngưỡng |
| **Evaluation frequency** | Ví dụ mỗi 5 phút |
| **Window size** | Ví dụ xét dữ liệu 15 phút |
| **Failing periods** | Bao nhiêu lần đánh giá bị vi phạm trong các lần xét |
| **Severity** | Mức ưu tiên vận hành |
| **State/auto mitigation** | Cách Fired/Resolved theo type/config |
| **Actions** | Action group(s) |
| **Identity/permissions** | Quyền đọc logs, identities nếu kiểu rule cần |
| **Dimensions** | Tách alert theo cột query khi hỗ trợ |

Không cố tạo một log alert query trả cả triệu rows: query nên **lọc sớm, chọn cột cần thiết và tính toán hiệu quả**. Query phải trả kết quả trong service limits, nếu chạy quá lâu hoặc không có quyền thì rule có thể gặp evaluation errors.

### Failing periods là gì?

Giả sử mỗi 5 phút đánh giá một lần:

~~~text
Window size: 15m
Evaluation frequency: 5m
Number of evaluation periods: 3
Minimum failing periods to alert: 2

Các kết quả 3 lần gần nhất: True, False, True
=> 2/3 lần vi phạm; rule có thể fire theo điều kiện này.
~~~

Đây là ý nghĩa logic của **failing periods** ở những scheduled query rules hỗ trợ. Cần kiểm tra schema/version và default khi không cấu hình. Nó **không phải** lấy thêm 3 lần số rows của query; window size và evaluation history là hai trục khác nhau.

## 20. Tạo log alert bằng Azure Portal

Ví dụ “trong 15 phút, số request lỗi > 20”:

1. Mở **Monitor → Alerts → Create alert rule**.
2. Chọn Log Analytics workspace chứa `AppRequests`.
3. Chọn condition **Custom log search** hoặc **Log search** theo Portal version.
4. Dán KQL lấy requests lỗi 15 phút ở phần 17.
5. Chọn measure **Table rows / Number of results** (không chọn numeric column).
6. Chọn operator **Greater than**, threshold **20**.
7. Chọn evaluation frequency **5 minutes**, window size **15 minutes**.
8. Chọn failing periods/alert logic và stateful behavior nếu supported.
9. Chọn **Sev2**, action group team ứng dụng, mô tả owner/runbook.
10. Review cost/query coverage, tạo rule và kiểm tra trạng thái Enabled.
11. Gửi test log có kiểm soát, xem ingestion, rule firing và delivery.
12. Xóa/revert test alerts hoặc threshold sau khi xong.

**Đừng vội tin Preview results là production alert sẽ fire.** Preview có thể chạy query ở một time range/connection khác so với evaluation schedule. Cần xác nhận đúng workspace, query window, role permission, signal ingestion và test end-to-end.

## 21. Azure CLI: kiểm tra scheduled query command surface

Azure CLI có các lệnh quản lý **scheduled-query rules**, ví dụ:

~~~bash
az monitor scheduled-query --help
az monitor scheduled-query create --help
az monitor scheduled-query list \
  --resource-group "rg-observability-lab" -o table
~~~

Tham số cho log alerts đã thay đổi theo CLI/API generation. Không sao chép mù quáng snippet cũ sử dụng `--condition "count ... > N"` khi schema hiện hành cần các thành phần khác; đặc biệt chú ý **scope**, `evaluation-frequency`, `window-size`, `failing-periods`, `action-groups` và KQL measure/row-count. Dùng **Bicep/ARM** ở phần 22 để xem mô hình cấu hình rõ hơn, hoặc tra `az monitor scheduled-query create -h` trước khi tạo.

### Vì sao không ép mọi KQL thành một CLI condition string?

- Scheduled query rule v2 có criteria riêng.
- Log query trả rows hay aggregated value thay đổi semantics.
- Dimensions/split và failingPeriods có thể không biểu diễn giống các phiên bản cũ.
- KQL quoting trong Bash/PowerShell dễ lỗi khi có dấu pipe, quotes và dấu dollar.
- Bicep/YAML/file template dễ review, version hóa và kiểm tra hơn một dòng CLI dài.

**Kết luận:** trước khi chạy, xác minh schema của extension đang cài và giá trị ID/tenant/resource group. Một câu lệnh đúng cú pháp nhưng trỏ nhầm workspace vẫn là alert sai.

## 22. Bicep: một action group, một metric alert, một log alert

Đây là **mẫu khai báo minh họa** theo ARM/Bicep resource types phổ biến, cần validate bằng tooling/schema của môi trường triển khai và quyền cho resource scopes. Chỉ dùng email lab do bạn được phép kiểm soát.

~~~bicep
@description('Azure VM resource ID (metric scope)')
param vmResourceId string

@description('Azure VM region, e.g. southeastasia')
param vmRegion string

@description('Log Analytics workspace ARM resource ID')
param workspaceResourceId string

@description('Workspace region for scheduled query rule')
param workspaceRegion string

@description('Application Insights ARM resource ID for AppRequests filter')
param appInsightsResourceId string

@description('Authorized testing mailbox only')
param oncallEmail string

resource ag 'Microsoft.Insights/actionGroups@2023-01-01' = {
  name: 'ag-platform-oncall-lab'
  location: 'global'
  properties: {
    groupShortName: 'platform'
    enabled: true
    emailReceivers: [
      {
        name: 'lab-email'
        emailAddress: oncallEmail
        useCommonAlertSchema: true
      }
    ]
  }
}

resource cpuHigh 'Microsoft.Insights/metricAlerts@2018-03-01' = {
  name: 'alert-vm-cpu-high-lab'
  location: 'global'
  properties: {
    description: 'VM CPU average over 80 percent'
    severity: 2
    enabled: true
    scopes: [
      vmResourceId
    ]
    targetResourceType: 'Microsoft.Compute/virtualMachines'
    targetResourceRegion: vmRegion
    evaluationFrequency: 'PT1M'
    windowSize: 'PT5M'
    criteria: {
      'odata.type': 'Microsoft.Azure.Monitor.SingleResourceMultipleMetricCriteria'
      allOf: [
        {
          criterionType: 'StaticThresholdCriterion'
          name: 'HighCpu'
          metricNamespace: 'Microsoft.Compute/virtualMachines'
          metricName: 'Percentage CPU'
          timeAggregation: 'Average'
          operator: 'GreaterThan'
          threshold: 80
        }
      ]
    }
    actions: [
      {
        actionGroupId: ag.id
      }
    ]
  }
}

resource errorLog 'Microsoft.Insights/scheduledQueryRules@2022-06-15' = {
  name: 'alert-app-requests-failed-lab'
  location: workspaceRegion
  properties: {
    displayName: 'App requests failed in 15m'
    description: 'Count of failed requests above threshold'
    enabled: true
    severity: 2
    evaluationFrequency: 'PT5M'
    windowSize: 'PT15M'
    scopes: [
      workspaceResourceId
    ]
    criteria: {
      allOf: [
        {
          query: 'AppRequests | where TimeGenerated >= ago(15m) | where _ResourceId =~ "${appInsightsResourceId}" | where Success == false'
          timeAggregation: 'Count'
          operator: 'GreaterThan'
          threshold: 20
          failingPeriods: {
            numberOfEvaluationPeriods: 1
            minFailingPeriodsToAlert: 1
          }
        }
      ]
    }
    autoMitigate: true
    actions: {
      actionGroups: [
        ag.id
      ]
    }
  }
}

output actionGroupId string = ag.id
output metricRuleId string = cpuHigh.id
output logRuleId string = errorLog.id
~~~

### Giải thích

- **Action group** là resource riêng, `location: 'global'` và receiver email được cấu hình.
- **Metric alert** theo VM resource ID và `Percentage CPU`, static threshold >80.
- **Log alert** query `AppRequests` của một **Application Insights resource ID** cụ thể (lọc qua `_ResourceId`) trong workspace.
- Query trả **các rows lỗi**, nên `timeAggregation: 'Count'` đánh giá row-count theo schema.
- `actions.actionGroups` liên kết log alert với group vừa tạo.
- `evaluationFrequency: 'PT5M'`, `windowSize: 'PT15M'` là thời gian ISO 8601.
- `autoMitigate` mô tả stateful recovery behavior theo API version tương ứng; không giả định instant resolution.
- Bicep dependency tới action group được infer qua `ag.id`.

### Trước khi deploy

1. Kiểm tra Bicep resource versions có supported trong region/tenant không.
2. Kiểm tra quyền tạo `Microsoft.Insights/*`, role assignment cần thiết và resource scopes.
3. Xác nhận workspace chứa đúng `AppRequests` data, cột `_ResourceId`, `Success` và ID khớp.
4. Chạy `az bicep build`/validation theo build pipeline **của người học** và review what-if (không yêu cầu worker này chạy).
5. Đảm bảo mailbox lab có owner/consent, không gửi tới người ngoài.
6. Nếu workspace resource nằm khác RG/subscription, kiểm tra cross-scope permissions và monitoring constraints.
7. Không dùng rule test trong prod hoặc Sev0 trong lab.
8. Kiểm thử first firing, recovery, action delivery và chi phí sau deployment.

Các field có thể cần điều chỉnh theo ARM schema và feature limits mới. Không gọi ví dụ này là “đã deploy chạy thật” nếu chưa kiểm tra/triển khai.

## 23. Alert processing rules: điều hướng và suppression

Một **alert processing rule** hoạt động với alert instances thỏa điều kiện và có thể:

- Thêm **action group** vào các alerts khớp filter.
- **Suppress** actions trong lịch bảo trì hoặc khung thời gian, nếu được hỗ trợ.
- Áp scope theo subscription/resource group/resource và filter như severity, monitor condition, alert rule ID/name hoặc resource type.

~~~mermaid
flowchart LR
  A["Fired alert"] --> MATCH{"Processing rule matches?"}
  MATCH -->|No| DEFAULT["Original action group(s)"]
  MATCH -->|Yes, add| EXTRA["Add escalation group"]
  MATCH -->|Yes, suppress| QUIET["No notification for matching period"]
  DEFAULT --> OPS["On-call / incident"]
  EXTRA --> OPS
  QUIET --> RECORD["Alert still visible in Alerts UI"]
~~~

**Lưu ý:** suppression của alert processing rule nhằm kiểm soát **thông báo/actions**, không hủy điều kiện telemetry và **không sửa alert rule query/metric**. Alert vẫn có thể tồn tại trong Azure Monitor và rule vẫn có thể phát sinh chi phí đánh giá.

### Use case

Trong maintenance window 01:00–02:00 UTC, nhóm thay backend có thể suppress các alerts `Sev3` đã dự kiến, nhưng **không suppress Sev0 về mất dịch vụ toàn vùng**. Sau thời hạn, rule tự hết hiệu lực theo schedule, không phụ thuộc người nhớ bật lại.

### Guardrail

- Có start/end UTC, owner và change ticket.
- Tối thiểu scope (không subscription-wide nếu không cần).
- Không suppress “all severity” khi không rõ tác động.
- Ghi audit khi processing rules được tạo/sửa.
- Xem sự kiện trong Alerts UI ngay cả khi không paging.

## 24. Mất dữ liệu: NoData không có nghĩa healthy

Một trong những failure mode nguy hiểm nhất:

~~~text
App bị crash -> không phát request telemetry
Log query errors > 20 -> trả 0 rows
Alert không fire -> on-call tưởng dịch vụ bình thường
~~~

**Không nhận log không chứng minh không có lỗi.**

### Tín hiệu độc lập nên có

1. **Availability test/probe** từ bên ngoài dịch vụ.
2. **Heartbeat** từ agent/app hoặc scheduled marker.
3. **Data freshness**: lần cuối nhận event thành công là khi nào?
4. **Ingestion health**: source có gửi logs và workspace có ingest kịp không?
5. **Traffic anomaly**: request count về 0 trong giờ cần có traffic.
6. **Dependency state**: queue backlog tăng trong khi consumer không phát logs.
7. **Platform metrics** không phụ thuộc pipeline logs nếu khả dụng.

### KQL alert thiếu heartbeat

Giả sử bảng `AppTraces` có marker `batch_completed` từ job hằng giờ:

~~~kusto
AppTraces
| where TimeGenerated >= ago(2h)
| where Message == "batch_completed"
| summarize LastSeen = max(TimeGenerated)
| where isnull(LastSeen) or LastSeen < ago(90m)
~~~

KQL `summarize` không có group thường tạo một hàng với `LastSeen = null` khi không có dữ liệu, để query trả row điều kiện bị thiếu. Dùng **row-count > 0**; nhưng logic này chỉ đúng nếu `AppTraces` tồn tại và có instrumentation. Nếu chỉ có scheduled job vào ngày làm việc, phải áp lịch phù hợp, tránh alert đêm cuối tuần.

### TimeGenerated khác ingestion time

`TimeGenerated` là timestamp log event; record có thể đến workspace muộn. Khi alert dùng `ago(15m)`, nên xét **ingestion latency**, delayed delivery, clock skew và window. Kusto hỗ trợ khả năng như `ingestion_time()` tùy context/chính sách, nhưng không mặc định mọi bảng đều có cùng ingestion metadata. Nếu pipeline logs trễ hơn evaluation window, có thể cần tăng window, đặt delay và bổ sung ingestion monitor.

## 25. SLO, burn rate và alert có ý nghĩa khách hàng

Threshold trên CPU giúp phát hiện **tài nguyên bận**, nhưng không phải lúc nào cũng tương quan với trải nghiệm người dùng. **SLO alert** dựa trên service level indicator như:

- Availability: tỷ lệ requests thành công trong tổng requests.
- Latency: tỷ lệ requests nhanh hơn ngưỡng SLO.
- Data freshness: tỷ lệ batches hoàn tất đúng hạn.
- Transaction quality: tỷ lệ checkout không lỗi nghiệp vụ.

### Error budget

Nếu SLO availability là **99,9%**, error budget cho cửa sổ thời gian là **0,1%** số requests/số phút tùy cách đo. **Burn rate** đo tốc độ tiêu thụ budget so với tỷ lệ cho phép.

Ví dụ minh họa:

~~~text
SLO success: 99.9% -> allowed error fraction 0.001
Observed error fraction: 0.020 (2%)
Burn rate = 0.020 / 0.001 = 20x
~~~

Nghĩa là trong khoảng đo giả định đang tiêu thụ error budget nhanh hơn 20 lần tốc độ bình quân chấp nhận được. Nhưng để quyết định paging, cần số mẫu tối thiểu, cửa sổ dài/ngắn, traffic pattern, business impact và điều kiện no-data.

### Multi-window multi-burn-rate

Một chiến lược tốt hơn “5xx >5 trong mọi trường hợp”:

- Cửa sổ ngắn, burn rate cao → page nhanh cho sự cố rõ.
- Cửa sổ dài, burn rate vừa phải → mở ticket/chỉnh capacity.
- Cần kết hợp số lượng samples và minimum traffic.
- Exclude các requests không thuộc SLI nếu đã định nghĩa hợp lệ, ví dụ user-generated 4xx không tính là service failure.

Không trộn query samples/units giữa request count và error fraction. Alert severity phải dựa vào user impact/SLO, không chỉ bảng log có bao nhiêu rows.

## 26. Dimension split và log alert cardinality

KQL có thể tách theo `Region` hoặc `OperationName`:

~~~kusto
AppRequests
| where TimeGenerated >= ago(15m)
| summarize Failed = countif(Success == false),
            Total = count()
    by OperationName
| extend FailurePct = iff(Total == 0, real(null),
                          100.0 * todouble(Failed)/todouble(Total))
| where Total >= 100 and FailurePct > 5
~~~

Nếu tạo cảnh báo per `OperationName`, mỗi operation có thể tạo alert instance riêng. Có thể hữu ích khi mỗi endpoint thuộc một owner khác, nhưng **không** tách theo requestId/customerId.

### Lưu ý schema

Log alert sử dụng **split-by dimensions** cần các trường/column support và type phù hợp; không phải cứ query `summarize by` là Azure Monitor tự tạo dimension cho từng row theo ý người viết. Phải cấu hình measure/dimensions/split trong rule schema và kiểm tra output shape. Với một số KQL query, người học có thể chọn alert khi **số rows của bảng kết quả >0** thay vì tạo một alert per row.

### Chi phí và noise

Nếu một bug chung làm 100 operations cùng fail, phát 100 tickets không giúp giải quyết nhanh hơn. Dùng group/dedup trong incident routing, dashboard để phân tích dimensions và một **service-level incident** khi thích hợp.

## 27. Thiết kế action group delivery đáng tin

Một action group có thể gửi webhook hoặc kích hoạt Logic App. Với workflow incident production:

~~~mermaid
sequenceDiagram
  participant M as Azure Monitor
  participant G as Action group
  participant W as Webhook / Logic App
  participant I as Incident platform
  M->>G: Alert Fired event
  G->>W: Common alert schema payload
  W->>W: Validate authentication & schema
  W->>W: Dedup alertId / condition
  W->>I: Create or update incident
  I-->>W: Incident ID
  Note over W,I: Retry an toàn nếu downstream 429/503
  M->>G: Resolved event
  G->>W: Same alert lifecycle (when emitted)
  W->>I: Resolve/update matching incident
~~~

### Tính chất cần giả định

- HTTP callback có thể thất bại hoặc được retry.
- Event có thể tới trễ hoặc lệch thứ tự khi qua nhiều systems.
- Một event duplicated phải **không** tạo hai actions không đảo ngược được.
- Receiver auth secrets/tokens phải được quản lý trong Key Vault/managed identity khi hỗ trợ.
- Event data phải được validate, không tin payload tùy ý từ Internet.
- Tách **notification** khỏi **automated remediation**: gửi ticket an toàn hơn việc tự delete/restart resources.
- Không kỳ vọng email đồng nghĩa với incident acknowledgement.
- Gắn correlation ID, alert ID, affected resource IDs và runbook URL.

### Bảo mật webhook

Dùng HTTPS, sender validation/OAuth hoặc receiver-authenticated endpoint tùy capability, secret rotation và network restrictions. Không đặt một raw long-lived webhook secret trong query description hoặc Log Analytics. Hạn chế quyền của Logic App/Function: ví dụ automation restart service cần role tại một resource, không Owner subscription.

## 28. Alert routing theo ownership và severity

Bảng ví dụ:

| Alert | Severity | Owner | Action |
|---|---|---|---|
| Checkout 5xx rate vượt SLO | Sev1 | Commerce on-call | Page + incident |
| VM CPU cao 10 phút | Sev2 | Platform | On-call/email + capacity review |
| Batch missing success event | Sev2 | Data platform | Job ticket + retry review |
| Key Vault 403 spike | Sev2 | Security/platform | Security ticket + config review |
| Certificate còn 30 ngày | Sev3 | PKI team | Scheduled ticket |
| Dev environment CPU cao | Sev4 | Dev owner | Email giờ hành chính |
| Dependency outage across regions | Sev0 | Incident commander | Multi-team escalation |

**Severity của Azure Monitor không tự gửi tới đúng người.** Alert rules tham chiếu action group; alert processing rules hoặc downstream workflow có thể thêm routing. Cần giữ mapping owner/resource/service tags trong CMDB/IaC để không gửi incident về mailbox không còn người quản lý.

### Tránh duplicate paging

Một sự cố database có thể gây:

- Database CPU/availability alert.
- Application dependency failure alert.
- API 5xx alert.
- Queue backlog alert.

Đây là **nhiều triệu chứng một nguyên nhân**, không nên tạo bốn incident tách biệt mà không có correlation. Tuy nhiên cũng không suppress hết triệu chứng nếu chúng đại diện những tác động độc lập. Tốt nhất có **dedup/correlation ở incident platform**, giữ evidence trên dashboard.

## 29. Phân quyền để tạo alert/action group

Azure Monitor alerts là Azure resources; người tạo cần quyền ARM trên scope tương ứng và **đọc telemetry** theo resource/workspace authorization.

| Vai trò/nhiệm vụ | Quyền cần đánh giá |
|---|---|
| Xem metrics của VM | Azure Monitor/Reader quyền tương ứng trên VM |
| Truy vấn logs trong workspace | Log Analytics query permissions và scope theo access control mode |
| Tạo/sửa metric alert | Quyền Microsoft.Insights/metricAlerts/write theo scope |
| Tạo/sửa scheduled query rule | Quyền Microsoft.Insights/scheduledQueryRules/write và query identity/permissions tương ứng |
| Tạo/sửa action group | Quyền Microsoft.Insights/actionGroups/write |
| Gán quyền cho automation identity | ARM role assignment write trong approved scope |
| Webhook remediation | Managed identity + role tối thiểu trên resource đích |
| Xem incident action logs | Quyền đọc diagnostics/workflow riêng |

**Contributor** ở resource group có thể tạo nhiều monitor resources nhưng không nên mặc định cấp rộng trên toàn subscription. Dùng role như Monitoring Contributor/Reader/Log Analytics Reader khi phù hợp, kiểm tra **role definitions thực tế** và policy.

Với automation cần thay đổi monitor resources hoặc thực hiện remediation quyền cao, có thể dùng **Privileged Identity Management (PIM)**/just-in-time activation cho quyền con người khi tenant và license hỗ trợ. PIM không thay kiểm soát scope, approval và audit; không cho một webhook hoặc Logic App toàn quyền Owner chỉ vì một cảnh báo cần thông báo.

### Log alert identity

Một số scheduled query configurations có thể cần managed identity hoặc service permissions để đọc workspace/resource, nhất là cross-resource/cross-tenant hoặc advanced scenarios. Không mặc định user tạo rule có quyền đọc logs vĩnh viễn; phải kiểm tra query authorization/service identity theo version.

## 30. Security và compliance trong cảnh báo

Một alert có thể chứa tài nguyên nhạy cảm trong:

- Rule name/description/query.
- KQL result columns.
- Alert context/dimensions.
- Webhook payload.
- Email subject và body.
- Incident/ticket comment.
- Logs/metrics từ ứng dụng.

**Không đưa** access tokens, raw database connection strings, customer PII, password hoặc secret values vào query result và alert description. Nếu cần điều tra, đưa người có quyền đến workspace có access control, dùng correlation IDs.

### Ràng buộc hành động tự động

Một alert 5xx **không nên tự xóa resource group**. Nếu automation restart instance hoặc scale compute:

1. Định nghĩa runbook, owner, risk và blast radius.
2. Chỉ cho phép action trên resource allowlist.
3. Kiểm tra trạng thái trước khi thực hiện, tránh restart loop.
4. Có concurrency limit/cooldown và idempotency key.
5. Có logging/audit, notification và rollback.
6. Đặc biệt với production, cân nhắc human approval cho destructive action.
7. Nếu remediation thất bại, mở/escalate incident thay vì retry vô hạn.

## 31. Azure Monitor log alerts: performance và chi phí KQL

Một log alert query chạy thường xuyên trên dữ liệu lớn có thể làm tăng query/resource costs hoặc bị giới hạn theo service plan/billing.

### Viết KQL tiết kiệm hơn

- Lọc `TimeGenerated` sớm và sát window cần.
- Lọc `_ResourceId` hoặc service identifier để tránh workspace-wide scan.
- Chỉ project các cột cần cho điều kiện.
- Không dùng `parse_json`/regex trên mọi raw message nếu có structured columns.
- Tránh `join` hoặc `union` rộng không cần thiết.
- Dùng `summarize` có kiểm soát cardinality.
- Cân nhắc sampling và data accuracy khi dùng Application Insights.
- Chọn evaluation frequency phù hợp với SLO và ingestion delay.
- Tránh alert rule duplicate cùng một query trên nhiều scopes.

### Tác động của sampling

Nếu Application Insights sampling loại bỏ 90% requests, query `count()` có thể không phản ánh chính xác tổng request nếu không xử lý sampling weight/`ItemCount` theo schema. Đối với tỷ lệ lỗi hoặc billing/business-critical metrics, cần hiểu sampling semantics, ưu tiên dedicated metrics khi cần độ chính xác.

**Không mặc định `countif(Success == false)` bằng số HTTP failures thực tế của toàn bộ hệ thống** khi logs đã bị sampling, ingestion drop hoặc phân vùng.

## 32. Reliability: alert pipeline cũng cần được giám sát

Giám sát ứng dụng mà không giám sát pipeline alert sẽ tạo **điểm mù**.

~~~text
Application healthy?
   ↓
Telemetry emitted?
   ↓
Ingested/available?
   ↓
Rule evaluated successfully?
   ↓
Alert fired?
   ↓
Action group invoked?
   ↓
Receiver delivered?
   ↓
Human acknowledged?
   ↓
Incident resolved?
~~~

Các câu hỏi runbook:

- Agent hoặc OpenTelemetry exporter đang hoạt động không?
- Diagnostic setting có route vào đúng workspace không?
- Có data ingestion delay, retention, sampling changes không?
- Rule có Enabled, đúng scope và query không?
- Rule evaluation có errors hoặc bị disable vì permissions không?
- Action group có receiver thật, common schema và địa chỉ đúng không?
- Alert processing rule có suppress theo lịch không?
- Webhook/Logic App có 401, 429, 5xx hoặc expired credential không?
- On-call schedule đã cập nhật người trực chưa?
- Có telemetry mất vào một ngày cao điểm khiến tất cả logs “đẹp” không?

### Synthetic canary cho alert delivery

Một tổ chức có thể tạo periodic test alert hoặc test action group theo lịch **được phê duyệt** rồi kiểm tra notification receipt. Nhưng test delivery có thể tạo chi phí và cảnh báo giả; cần đặt receiver lab/on-call training phù hợp, không gửi paging production không có ngữ cảnh.

## 33. Chi phí: metric alert, log alert và action group

Chi phí tổng có thể gồm:

~~~text
Monitoring cost =
  Alert rules / monitored metric series
  + scheduled query rule evaluations và data/query usage
  + telemetry ingestion vào Log Analytics/Application Insights
  + retention/export
  + action-group channel delivery / integration charges
  + Logic Apps/Functions/ITSM automation
  + human operational overhead
~~~

Không có một mức giá cố định cho mọi Azure Monitor signals. Giá phụ thuộc resource type, number of monitored time series, alert rule type, frequency, log query model, workspace ingestion, action delivery channel, region và hợp đồng dịch vụ.

### Cost traps

- Alert per instance + per error code + per customer tạo cardinality lớn.
- Một truy vấn KQL nặng đánh giá mỗi phút không cần thiết.
- Thu toàn bộ raw request bodies vào logs gây ingestion/privacy risk.
- Trùng rules giữa workspace/resource scopes.
- Action group webhook gọi Logic App tốn tiền mỗi lần retry.
- Email/SMS toàn bộ môi trường dev làm nhóm vận hành bị quá tải.
- Retention quá dài không có yêu cầu.
- Không xóa alert rules/action groups của lab sau thử nghiệm.

### FinOps checklist

1. Dùng severity và ownership rõ để giảm noise.
2. Phân biệt monitoring **safety-critical** với informational.
3. Đo alert volume, false-positive rate, ack time, resolution time.
4. Tính cost per **actionable incident**, không chỉ cost per alert rule.
5. Đặt budgets/tags owner/env/cost center.
6. Review unused rules và legacy queries định kỳ.
7. Không tắt cảnh báo có ý nghĩa chỉ để cắt chi phí; tối ưu signal/aggregation/query.
8. Kiểm tra trang giá Azure Monitor hiện hành trước dự toán.

## 34. Troubleshooting: rule không fire

| Triệu chứng | Nguyên nhân | Kiểm tra |
|---|---|---|
| Metric alert không có dữ liệu | Sai metric/resource/namespace, collection delay | Metrics Explorer và metric definitions |
| CPU >80 nhưng không fire | Aggregation Average 5m vẫn thấp hoặc evaluation chưa tới | Check window, aggregation, threshold |
| Rule Disabled | Tạo xong chưa enable | Rule configuration |
| Multi-resource alert sai | Type/region/scope không phù hợp | Target metadata |
| Log alert không fire | KQL không trả rows, wrong table/field | Run same query, actual schema |
| Log query returns 1 row count=42 | Rule đang đo row count=1 | Numeric measure column |
| Có lỗi nhưng logs tới muộn | Ingestion delay/sampling | TimeGenerated, ingestion health |
| KQL permission error | Identity/query authorization | Workspace permissions |
| Stateful alert không fire lại | Đang Fired, chưa Resolved | Alert state |
| Dynamic threshold chưa có baseline | Thiếu lịch sử hoặc sensitivity | Metric history và config |
| Conditions match nhưng action group không gửi | Receiver sai/disabled, routing/suppression | Test group, processing rules |
| Rule create 403 | Thiếu ARM permissions/Azure Policy | Caller role/scope/policy |
| Alert fire ở prod nhầm service | Workspace chứa nhiều app, query không filter | `_ResourceId` và scope |

### Quy trình debug từng chặng

1. **Telemetry:** có metric/log thật trong khoảng thời gian mong đợi không?
2. **Rule:** scope, Enabled, condition, aggregation, window/frequency có đúng?
3. **Evaluation:** lịch đánh giá và query có thành công không?
4. **State:** đã Fired chưa, đang stateful không, điều kiện recovery thế nào?
5. **Processing:** suppression/maintenance rule có áp dụng không?
6. **Action:** action group/receiver có enable và cấu hình đúng không?
7. **Delivery:** email/webhook/Logic App có nhận event và xử lý không?
8. **Incident:** có bị dedup/filtered bởi downstream incident system không?

Không tăng quyền Owner hoặc hạ severity/threshold vô tội vạ khi chưa định vị lỗi.

## 35. Troubleshooting: action group không gửi thông báo

1. Xác minh `actionGroupId` trong metric/log rule đúng ARM ID.
2. Kiểm tra action group `enabled` và danh sách receivers có nội dung.
3. Dùng **Test action group** với receiver lab; xác nhận email/webhook nhận payload.
4. Kiểm tra common schema flag có tương thích consumer parser không.
5. Kiểm tra alert processing rules đang suppress notifications trong maintenance window.
6. Kiểm tra email domain, spam, outbound policies, on-call distribution list.
7. Với webhook, kiểm tra TLS, auth, routing và status 2xx/401/429/5xx.
8. Với Logic App/Function, xem runs/history, managed identity permissions, quota.
9. Xác minh receiver idempotency/dedup có vô tình nuốt alert mới không.
10. Kiểm tra alert instance thực đã Fired hay chỉ test KQL/metric explorer.
11. Không gửi raw access token hoặc webhook shared secret qua chat để debug.
12. Có fallback path nếu primary notification provider không available.

### Tại sao firing và delivery là hai thử nghiệm?

- **Test group** kiểm tra receiver path, không thực thi condition thật.
- **Trigger alert bằng telemetry** kiểm tra rule, nhưng cần xem tiếp notification.
- **End-to-end test** phải chứng minh cả hai nối đúng với instance ID/correlation ID.

## 36. Case study: hệ thống thanh toán có ba kiểu sự cố

### Bối cảnh

Một sản phẩm e-commerce trên Azure gồm:

- Spring Boot API ở Azure Container Apps.
- PostgreSQL/Azure SQL cho giao dịch.
- Azure Service Bus queue xử lý đơn hàng.
- Azure VM chạy connector legacy.
- Workspace-based Application Insights/Log Analytics.
- Nhóm Commerce, Platform, Data và Security on-call.

### Thiết kế alert

| Sự cố | Signal | Rule | Action group |
|---|---|---|---|
| VM connector quá tải | VM `Percentage CPU` | Metric Average>80%, 5m | Platform |
| Checkout 5xx tăng | `AppRequests` errors | Log error count/rate, min traffic | Commerce |
| Queue backlog không giảm | Service Bus metric | Metric threshold theo baseline | Commerce/Data |
| Không có `batch_completed` đúng hạn | `AppTraces` marker | Log no-data/freshness | Data |
| Role/permission mới làm Key Vault 403 | App error logs + Key Vault audit | Log count/error alert | Security/Platform |
| Certificate sắp hết hạn | Cert metadata/event theo support | Scheduled query/event alert | Security |

### Giả lập sự cố

10:00 UTC, deployment mới làm checkout lỗi 500 trong 15 phút. Một số VM vẫn CPU bình thường nên **CPU alert không fire**; log alert và availability alerts phải phát hiện vấn đề. Tín hiệu gửi đến Commerce on-call qua action group. Sau đó incident platform nhận thêm DB dependency error alerts nhưng dedup theo service/incident correlation.

10:20 UTC, on-call rollback deployment. Error rate giảm; alert stateful chuyển Resolved theo behavior/tần suất đánh giá, workflow cập nhật incident. Team vẫn điều tra root cause và kiểm tra các giao dịch bị ảnh hưởng.

### Điều cần rút ra

- CPU không phải SLO của checkout.
- 5xx count cần sample guard và nguồn dữ liệu đáng tin.
- Action group phải có owner, test delivery và escalation.
- Receiver cần idempotency vì cùng incident có nhiều alert signals.
- Một alert Resolved không tự chứng minh mất dữ liệu được khôi phục.
- Logs ingestion/sampling có thể làm giảm accuracy của log alert.
- Alert processing rule có thể giảm noise trong maintenance, nhưng không che Sev0 outage.

~~~mermaid
flowchart TD
  API["Spring Boot + App Insights"] --> REQ["AppRequests error-rate KQL"]
  VM["Legacy VM"] --> CPU["CPU metric"]
  BUS["Service Bus"] --> QUEUE["Backlog metric"]
  REQ --> COM["Commerce on-call action group"]
  CPU --> PLAT["Platform action group"]
  QUEUE --> COM
  COM --> INCIDENT["Incident platform with dedup"]
  PLAT --> INCIDENT
  INCIDENT --> RUN["Owner + runbook + rollback"]
~~~

## 37. Bài thực hành tổng hợp: Metric alert + Log alert + Action group

> **An toàn:** chỉ triển khai trong resource group **lab** được cấp quyền, có ngân sách. KQL, metrics, action group notifications, Log Analytics và integration actions có thể tính phí. Không thử tải nặng trên production hoặc gửi cảnh báo thật tới người trực không biết trước.

### Phần A — Chuẩn bị telemetry

1. Xác định subscription/resource group lab.
2. Chọn VM hoặc resource lab đang phát metric.
3. Xem Metrics Explorer, metric namespace, units và dimensions.
4. Tạo hoặc dùng Log Analytics workspace lab.
5. Cấu hình ứng dụng thử nghiệm gửi telemetry tới workspace-based Application Insights.
6. Xác minh bảng `AppRequests` hoặc bảng logs phù hợp có dữ liệu.
7. Xác định cửa sổ ingestion latency và sampling policy.
8. Chọn team-owned mailbox lab cho action group.
9. Ghi tiêu chí severity và SLO trước khi tạo threshold.
10. Kiểm tra Azure Monitor RBAC quyền tạo rule và query logs.

### Phần B — Action group

1. Tạo `ag-platform-oncall-lab`.
2. Gắn receiver email lab, bật common alert schema nếu cần.
3. Test action group và xác minh email tới đúng mailbox.
4. Nếu có webhook lab, xác minh HTTPS/auth và parsing schema.
5. Xây dedup theo `alertId` và monitor condition.
6. Xác định runbook contact, time zone/on-call schedule.
7. Không dùng SMS/Phone thật nếu chưa có consent.
8. Ghi action group ARM ID cho các alert rules.

### Phần C — Metric alert

1. Chọn resource `vm-monitor-lab` và metric `Percentage CPU`.
2. Chọn Average, static threshold 80%, window 5m, evaluation 1m.
3. Chọn Sev2, gắn action group lab.
4. Tạo bằng Portal hoặc CLI/Bicep.
5. Kiểm tra rule Enabled và exact scope.
6. Trong **VM sandbox**, tạo biến động CPU có kiểm soát hoặc threshold thử tạm hợp lệ.
7. Quan sát Alert instance Fired cùng timestamp/metric value.
8. Xác minh email/action group thực nhận.
9. Chờ recovery và ghi Resolved behavior thực tế.
10. Rollback ngưỡng/rule test, không để noisy alert lưu lại.

### Phần D — Log alert

1. Tạo query `AppRequests` cho 5xx/Success=false.
2. Xem sample records, kiểm tra resource ID và schema.
3. Chọn **number of rows** thay vì numeric measure cho query row-level.
4. Cấu hình window 15m, evaluation 5m, threshold ví dụ >20.
5. Gắn cùng hoặc action group riêng theo ownership.
6. Tạo test requests failure **trong lab** có kiểm soát.
7. Đợi ingestion/evaluation, quan sát Fired.
8. Kiểm tra actual notification và common alert schema `signalType: Log`.
9. Thử query `summarize count()` và giải thích tại sao row-count != numeric count.
10. Thiết kế thêm no-heartbeat alert, không chỉ count of failures.

### Phần E — Noise, security và FinOps

1. Tạo một rule tạm có dimensions ít, đo alert series.
2. So ngưỡng Average vs Maximum và false positives.
3. Xem một maintenance-window alert processing rule **lab**; test suppression đúng scope.
4. Xác minh alert còn hiển thị khi notification bị suppress theo policy.
5. Kiểm tra RBAC của người tạo và identity của webhook remediation.
6. Đảm bảo logs/query không lộ tokens/PII.
7. Xem cost estimation/Cost Management cho metrics/logs/alerts.
8. Viết runbook 401/403, missing telemetry, alert not fired, delivery failed.
9. Dọn lab rules/action group/temporary resources theo quyền được cấp.
10. Ghi báo cáo cảnh báo nào có ích, cảnh báo nào gây noise và điều chỉnh ra sao.

## 38. Câu hỏi tự kiểm tra

**Câu 1.** Metric alert khác scheduled query log alert ở nguồn dữ liệu và độ trễ thế nào?

**Câu 2.** Action group có tự thu thập metrics hoặc chạy KQL không?

**Câu 3.** Alert rule khác alert instance và processing rule thế nào?

**Câu 4.** Average CPU >80 trong 5 phút có nghĩa tất cả samples >80 không?

**Câu 5.** Aggregation `Total` khác `Average` ở request count ra sao?

**Câu 6.** Evaluation frequency khác window size thế nào?

**Câu 7.** Metric dimension split có thể dẫn tới cardinality explosion vì sao?

**Câu 8.** Dynamic threshold thích hợp khi nào và có thay SLO không?

**Câu 9.** Stateful và stateless alert khác nhau về repeated notifications ra sao?

**Câu 10.** Monitor condition Fired/Resolved khác user acknowledgement thế nào?

**Câu 11.** Log query trả 1 row với cột `Failures=42`; vì sao row-count threshold >20 không fire?

**Câu 12.** Khi nào cấu hình numeric measure column?

**Câu 13.** Vì sao log alert dựa trên errors >5 không phát hiện app crash không phát log?

**Câu 14.** Ingestion delay và sampling có thể làm log alert sai thế nào?

**Câu 15.** Vì sao nên đặt minimum traffic khi alert theo error rate?

**Câu 16.** `AppRequests` có tồn tại trong mọi Log Analytics workspace không?

**Câu 17.** Quy tắc cần làm gì khi một workspace chứa logs của nhiều apps?

**Câu 18.** Failing periods khác windowSize thế nào?

**Câu 19.** Common Alert Schema dùng để làm gì? `alertContext` giống nhau cho metric và log alert không?

**Câu 20.** Tại sao receiver webhook cần auth và idempotency?

**Câu 21.** Test action group có chứng minh alert condition chạy đúng không?

**Câu 22.** Alert processing rule suppress actions có xóa cảnh báo không?

**Câu 23.** Vì sao không nên suppress mọi Sev0/Sev1 alert trong maintenance window?

**Câu 24.** Vì sao một sự cố DB có thể kích hoạt nhiều alert instances khác nhau?

**Câu 25.** SLO 99.9% cho phép error fraction bao nhiêu? Burn rate 20x có ý nghĩa gì?

**Câu 26.** Cần những quyền nào để tạo alert rule và query Log Analytics workspace?

**Câu 27.** Log alert không fire dù query thấy dữ liệu: phải kiểm tra các bước nào?

**Câu 28.** Alert Fired nhưng on-call không nhận email: điều tra đâu trước?

**Câu 29.** Vì sao không nên cấp Owner subscription cho Azure Function tự restart service?

**Câu 30.** Các thành phần nào có thể tạo chi phí trong monitoring pipeline?

**Câu 31.** Tại sao không dùng userId/requestId làm metric dimension mặc định?

**Câu 32.** Làm sao kiểm thử metric/log alert end-to-end mà không ảnh hưởng production?

**Tiêu chí hoàn thành:** người học biết chọn và cấu hình metric/log alerts theo nguồn telemetry có thật; viết KQL row-count/numeric-measure đúng; tạo action group/receivers/common schema; xác minh rule Fired, notification delivery, recovery/no-data handling; thiết kế severity/ownership/action processing, kiểm soát noise, bảo mật và chi phí.

## Kết luận

**Metric alert, log alert và action group** tạo thành ba phần bổ trợ trong **Azure Monitor**. Metric alert nhanh chóng nhận biết số đo vượt ngưỡng; scheduled query log alert truy vấn được các điều kiện vận hành/nghiệp vụ phức tạp hơn; action group kết nối điều kiện với người trực hoặc workflow xử lý. Một alert hữu ích cần **scope, signal, aggregation, threshold, evaluation, severity, ownership và action** rõ ràng, chứ không chỉ “tạo rule thành công”.

Để vận hành hệ Azure an toàn và có thể tin cậy, luôn kiểm tra **telemetry ingestion, row-count vs numeric measure, stateful/recovery, missing data, dimension cardinality, Common Alert Schema, notification delivery, SLO/error budgets, Azure RBAC, incident idempotency và FinOps**. Hãy diễn tập từ dữ liệu đến cảnh báo và hành động trong môi trường lab, đo false positives và cập nhật runbook trước khi áp dụng production.


