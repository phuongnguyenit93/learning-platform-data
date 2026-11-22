# Viết truy vấn KQL để điều tra ứng dụng và hạ tầng

Lúc 10:15, một ứng dụng Java/Spring Boot trên Azure bắt đầu trả HTTP 500, độ trễ tăng và một số Pod của Azure Kubernetes Service (AKS) khởi động lại. Dashboard cho biết có sự cố, nhưng chưa trả lời **sự cố bắt đầu từ đâu, ảnh hưởng những phiên bản nào, dependency nào chậm, Pod nào bất thường và có thay đổi hạ tầng ngay trước đó không**. Thay vì mở từng log file và tìm thủ công, kỹ sư có thể dùng **Kusto Query Language (KQL)** trong **Azure Monitor Logs / Log Analytics** để khoanh vùng, tổng hợp, đối chiếu telemetry và kiểm chứng giả thuyết.

Bài thuộc chương **Giám sát và quan sát hệ thống** của mô-đun **CLOUD_PROVIDERS_AZURE**. Mô-đun khám phá Azure từ subscription, resource group và Microsoft Entra ID đến mạng ảo, compute, storage và dữ liệu; đồng thời rèn cách triển khai, giám sát, bảo vệ, kiểm soát chi phí kiến trúc ứng dụng Azure. KQL là công cụ điều tra giúp kết nối biểu hiện ở ứng dụng với dấu vết của hạ tầng, deployment và dịch vụ phụ thuộc.

> **Phạm vi và lưu ý:** Bài tập trung vào KQL trong **Azure Monitor Logs**, **Log Analytics workspace** và **workspace-based Application Insights**, cùng dữ liệu Azure Activity, Container Insights và resource diagnostics khi đã được thu thập. Schema, tên bảng/cột và khả năng truy vấn có thể khác theo loại Application Insights, bảng legacy, giải pháp thu thập, chế độ lưu trữ, tenant và thời gian. Mọi ví dụ sử dụng **tên bảng phổ biến và dữ liệu giả định**, phải đối chiếu schema thực của workspace trước khi chạy. Đây là truy vấn **chỉ đọc dữ liệu**; đọc logs vẫn có thể phát sinh phí truy vấn, lộ thông tin nhạy cảm nếu cấp quyền quá rộng hoặc trả về dữ liệu production không được phép.

## Mục tiêu học tập

Sau bài học, người học có thể:

1. Giải thích nơi lưu telemetry và vai trò của Azure Monitor, Log Analytics, Application Insights, Container Insights.
2. Xác định **scope**, **time range**, bảng và schema trước khi truy vấn.
3. Viết KQL sử dụng **where, project, extend, order by, take, summarize, bin, countif, dcount, percentile**.
4. Điều tra tỉ lệ lỗi, độ trễ p95/p99, request failures, dependency failures và exceptions.
5. Liên kết requests, dependencies và traces bằng **OperationId** đúng cách, tránh nhân bản kết quả khi join.
6. Phân tích log AKS qua **ContainerLogV2**, **KubePodInventory**, máy chủ/VM qua **Heartbeat**, **Perf**, **InsightsMetrics** khi tồn tại.
7. Tìm sự kiện thay đổi Azure resources trong **AzureActivity**, diagnostics trong **AzureDiagnostics** hoặc resource-specific tables.
8. Xử lý **dynamic JSON**, null, type conversions, UTC timestamps, ingestion lag và sampling.
9. Tối ưu KQL để giảm scan/cost và tránh tạo dashboard/alert sai.
10. Thực hiện quy trình điều tra một incident đầu-cuối, có bằng chứng, giả thuyết và giới hạn kết luận.

## 1. KQL là gì, dùng ở đâu?

**KQL (Kusto Query Language)** là ngôn ngữ truy vấn phân tích tập dữ liệu theo pipeline. Nó được dùng trong Azure Monitor Logs, Azure Data Explorer và các dịch vụ khác của Microsoft theo sản phẩm. Bài này chú trọng **log analytics**, không viết SQL DML hoặc thay đổi dữ liệu sản xuất.

~~~text
Spring Boot / AKS / Azure SQL / Gateway / VMs
                     |
                     | Logs, metrics, traces, diagnostics
                     v
        Azure Monitor collection pipeline
                     |
             +-------+-------+
             |               |
             v               v
       Log Analytics     Metrics store
       workspace         (metrics riêng)
             |
             v
     Tables: AppRequests, AppDependencies,
     ContainerLogV2, AzureActivity, ...
             |
             v
         KQL in Logs
             |
             v
       Triage / Workbooks / Alerts
~~~

Không phải mọi metric Azure nằm trong một bảng KQL. **Azure Monitor Metrics** và **Azure Monitor Logs** có đường lưu/thu thập khác nhau; muốn truy vấn metric bằng KQL cần dữ liệu tương ứng được đưa vào bảng có hỗ trợ, ví dụ **AzureMetrics**, **Perf** hoặc **InsightsMetrics** theo cấu hình.

## 2. Ba tín hiệu quan sát: logs, metrics, traces

| Tín hiệu | Câu hỏi giải quyết | Ví dụ |
|---|---|---|
| **Logs** | Đã xảy ra sự kiện/lỗi gì? | Exception, Pod restart log, Activity |
| **Metrics** | Hệ thống thay đổi thế nào theo thời gian? | CPU, request rate, p95 latency |
| **Distributed traces** | Một request đi qua những dịch vụ nào? | API → Redis → SQL → Service Bus |

Trong Application Insights, các bảng request/dependency có các trường correlation cho phép **truy vết theo operation**, nhưng **KQL không tự tạo distributed trace** khi ứng dụng chưa instrument hoặc mất propagation context.

**Không suy đoán root cause từ một chỉ số.** CPU tăng có thể là nguyên nhân hoặc hệ quả của retry storm, lỗi database hoặc traffic spike.

## 3. Các thành phần Azure liên quan

| Thành phần | Vai trò |
|---|---|
| **Azure Monitor** | Nền tảng giám sát, thu thập, truy vấn và cảnh báo |
| **Log Analytics workspace** | Chứa bảng log với retention/permissions theo cấu hình |
| **Application Insights** | Telemetry ứng dụng: requests, dependencies, exceptions, traces |
| **Azure Monitor Agent / DCR** | Một số luồng thu thập/log routing trên VM hoặc tài nguyên hỗ trợ |
| **Container Insights** | Thu thập trạng thái/log/metrics từ Kubernetes theo cấu hình |
| **Diagnostic settings** | Định tuyến resource logs/metrics của Azure resources tới đích hỗ trợ |
| **Azure Activity log** | Hoạt động control-plane trên Azure resources |
| **Logs query interface** | Chạy KQL theo workspace/resource scope và time range |

### Bẫy quan trọng

Khi một bảng trống, điều đó **không tự chứng minh không có sự cố**. Có thể chưa bật collection, diagnostic settings không gửi về workspace đó, retention đã hết, thiếu RBAC hoặc data ingestion đang trễ.

## 4. Chọn đúng scope trước khi truy vấn

Khi mở **Logs** từ workspace hoặc resource, **scope** quyết định dữ liệu được truy cập:

~~~text
Subscription
  |
  +-- Log Analytics workspace "ops-prod"
  |      +-- AppRequests của nhiều ứng dụng
  |      +-- ContainerLogV2 từ nhiều clusters
  |      +-- AzureActivity / resource diagnostics
  |
  +-- Application Insights resource "checkout-prod"
  |
  +-- AKS cluster "aks-prod"
~~~

### Quy trình

1. Xác nhận **tenant, subscription, resource group, resource name**.
2. Xác định Application Insights có phải **workspace-based** và gửi tới workspace nào.
3. Xác định AKS/VM/resource diagnostic logs có đang gửi tới cùng workspace không.
4. Kiểm tra **time picker** và timezone của giao diện.
5. Nếu workspace có nhiều ứng dụng, thêm **AppRoleName** hoặc **_ResourceId** khi cột tồn tại.
6. Nếu resource không dùng workspace đang chọn, không tự kết luận log đã mất.

**Một câu KQL không thể join dữ liệu không được ingest hoặc người dùng không có quyền xem.** Cross-resource/cross-workspace queries có điều kiện về permission, hỗ trợ và cost; thiết kế scope rõ trước.

## 5. Tên bảng: workspace-based và legacy Application Insights

Trong **workspace-based Application Insights**, các bảng phổ biến:

| Loại telemetry | Workspace-based (thường gặp) | Legacy/Application Insights context (thường gặp) |
|---|---|---|
| HTTP requests | **AppRequests** | **requests** |
| Dependencies | **AppDependencies** | **dependencies** |
| Exceptions | **AppExceptions** | **exceptions** |
| Application traces/logs | **AppTraces** | **traces** |
| Page views | **AppPageViews** | **pageViews** |
| Custom events | **AppEvents** | **customEvents** |

Tên và casing/cột **khác nhau**. Đặc biệt:

~~~text
AppRequests:
  TimeGenerated, Name, Success, ResultCode,
  DurationMs, OperationId, AppRoleName, ItemCount ...

requests (legacy context):
  timestamp, name, success, resultCode,
  duration, operation_Id, cloud_RoleName, itemCount ...
~~~

**Đừng chạy nguyên query AppRequests vào bảng requests rồi chỉ đổi tên bảng**. Cần đổi tên cột, đơn vị đo và type. Ví dụ **DurationMs** là milliseconds trong AppRequests; **duration** ở legacy thường là timespan nên không so trực tiếp bằng số millisecond.

## 6. Những bảng hạ tầng thường gặp

| Bảng | Loại dữ liệu và điều kiện |
|---|---|
| **AzureActivity** | Các sự kiện quản trị Azure control plane được đưa vào Logs |
| **AzureDiagnostics** | Resource diagnostics kiểu chung khi dùng AzureDiagnostics destination mode |
| **Resource-specific tables** | Tên riêng theo dịch vụ/log category, khi cấu hình resource-specific mode |
| **ContainerLogV2** | Log stdout/stderr container theo Container Insights/data collection cấu hình |
| **KubePodInventory** | Trạng thái và metadata Kubernetes Pod được thu thập |
| **KubeNodeInventory** | Trạng thái và metadata nodes nếu được ingest |
| **Heartbeat** | Heartbeats của máy/agent khi thu thập |
| **Perf** | Performance counters theo agent/DCR/config |
| **InsightsMetrics** | Metrics từ những giải pháp giám sát được hỗ trợ |
| **AzureMetrics** | Metrics được export/ingest vào logs theo cấu hình |

Không mặc định mỗi bảng luôn có ở workspace. Azure resource logs có thể chuyển thành **resource-specific table** thay vì AzureDiagnostics, và một số signals nằm ở Metrics backend chứ không ở Log Analytics.

## 7. Khởi đầu từ schema chứ không từ câu truy vấn sao chép

Trong Azure Portal, vào **Log Analytics workspace → Logs** hoặc Application Insights → Logs, xem schema browser để biết bảng/cột thực tế.

Truy vấn giới hạn rất nhỏ:

~~~kusto
AppRequests
| take 5
~~~

Xem cấu trúc cột nếu môi trường hỗ trợ operator tương ứng:

~~~kusto
AppRequests
| getschema
~~~

### An toàn vận hành

**take 5 không phải bảo đảm chi phí bằng không**, nhất là khi chưa có time filter hoặc workspace lưu dữ liệu rất lớn. Khi điều tra thật, dùng time range và cột/resource filter trước:

~~~kusto
AppRequests
| where TimeGenerated >= ago(30m)
| project TimeGenerated, AppRoleName, Name, ResultCode, Success, DurationMs
| take 10
~~~

**Không dùng .show tables** như mặc định ở Azure Monitor Logs: KQL control commands của Azure Data Explorer không nhất thiết được hỗ trợ trong Log Analytics query interface. Ưu tiên schema pane và KQL query operators được Logs hỗ trợ.

## 8. KQL pipeline: bảng rồi toán tử

KQL đọc từ trái sang phải qua toán tử **|**:

~~~kusto
AppRequests
| where TimeGenerated >= ago(1h)
| where Success == false
| project TimeGenerated, AppRoleName, Name, ResultCode, DurationMs
| order by TimeGenerated desc
| take 20
~~~

Giải thích:

1. **AppRequests**: nguồn dữ liệu.
2. **where**: lọc thời gian và lỗi.
3. **project**: chỉ giữ các cột cần dùng.
4. **order by**: sắp xếp mới nhất trước.
5. **take**: giới hạn số dòng trả về.

### Phân biệt take và top

**take 20** lấy một tập dòng giới hạn, **không có thứ tự được đảm bảo** nếu không sắp xếp. **top 20 by TimeGenerated desc** là dạng gọn cho yêu cầu lấy bản ghi mới nhất:

~~~kusto
AppRequests
| where TimeGenerated >= ago(1h)
| top 20 by TimeGenerated desc
~~~

## 9. Lọc thời gian: UTC và cửa sổ incident

Trong Log Analytics, **TimeGenerated** thường là datetime UTC. Khi người vận hành nói “sự cố bắt đầu lúc 10:15” phải xác định múi giờ.

~~~text
10:15 giờ Việt Nam (UTC+7)
= 03:15 UTC cùng ngày
~~~

Ví dụ truy vấn một cửa sổ UTC minh họa:

~~~kusto
let IncidentStart = datetime(2026-11-20T03:15:00Z);
let IncidentEnd = datetime(2026-11-20T04:00:00Z);
AppRequests
| where TimeGenerated >= IncidentStart
  and TimeGenerated < IncidentEnd
| summarize Requests = count() by bin(TimeGenerated, 5m)
| order by TimeGenerated asc
~~~

### Vì sao dùng cửa sổ nửa mở?

Điều kiện **>= start và < end** giúp ghép các cửa sổ liên tiếp mà không đếm trùng sự kiện đúng thời điểm biên.

### Phân biệt time picker và where

Giao diện Logs có time range riêng. Điều kiện **where TimeGenerated** trong query và lựa chọn thời gian trên UI có thể cùng giới hạn dữ liệu theo cơ chế truy vấn. Hãy kiểm tra cả hai nếu query “không có dòng” dù nghĩ rằng dữ liệu tồn tại.

## 10. Toán tử where: lọc đúng chứ không quét tất cả

~~~kusto
AppRequests
| where TimeGenerated >= ago(2h)
| where AppRoleName == "checkout-api"
| where Success == false
| project TimeGenerated, OperationId, Name, ResultCode, DurationMs
~~~

### Một số phép lọc

| Biểu thức | Ý nghĩa |
|---|---|
| **==** | Bằng, so sánh phù hợp type |
| **!=** | Khác |
| **in (...)** | Thuộc một tập giá trị |
| **between (a .. b)** | Nằm trong khoảng, cần lưu ý biên |
| **contains** | Chuỗi chứa đoạn con |
| **has** | Tìm term theo cơ chế tokenization của Kusto |
| **startswith** | Bắt đầu bằng chuỗi |
| **isnotempty(x)** | Không null/rỗng |
| **isnull(x)** | Null |

### contains khác has

~~~kusto
AppTraces
| where TimeGenerated >= ago(1h)
| where Message has "timeout"
| project TimeGenerated, AppRoleName, Message
| take 50
~~~

**has** thích hợp tìm thuật ngữ theo term index trong nhiều tình huống; **contains** là phép kiểm tra chuỗi con và thường có thể tốn hơn. Cần chọn theo ngữ nghĩa: tìm "order" như từ độc lập khác tìm "preorder" như một phần chuỗi.

## 11. project, extend, project-away và rename

**project** chọn/tạo cột output:

~~~kusto
AppRequests
| where TimeGenerated >= ago(1h)
| project
    TimeGenerated,
    Service = AppRoleName,
    RequestName = Name,
    LatencyMs = DurationMs
| take 20
~~~

**extend** thêm cột mà vẫn giữ các cột cũ:

~~~kusto
AppRequests
| where TimeGenerated >= ago(1h)
| extend SlowRequest = DurationMs > 1000.0
| project TimeGenerated, Name, DurationMs, SlowRequest
| take 30
~~~

### Dùng project sớm hay muộn?

Lọc **TimeGenerated** và resource trước, sau đó **project** chỉ cột cần thiết để giảm dữ liệu chuyển qua các bước nặng, nhưng bảo đảm không loại mất **OperationId** trước khi join hoặc tính toán. KQL optimizer có thể đẩy projection/filter xuống nguồn; mục tiêu vẫn là query dễ đọc và ít dữ liệu phải xử lý.

## 12. Tổng hợp với summarize, count và bin

Truy vấn tổng số requests theo năm phút:

~~~kusto
AppRequests
| where TimeGenerated >= ago(2h)
| summarize RequestRows = count() by bin(TimeGenerated, 5m)
| order by TimeGenerated asc
~~~

Theo dịch vụ:

~~~kusto
AppRequests
| where TimeGenerated >= ago(2h)
| summarize RequestRows = count()
    by AppRoleName, bin(TimeGenerated, 5m)
| order by TimeGenerated asc
~~~

### Cách đọc

- Một dòng output tương ứng một bucket **TimeGenerated** và **AppRoleName**.
- **count()** đếm các records có trong bảng, không nhất thiết là số requests gốc khi có sampling.
- **bin(TimeGenerated, 5m)** làm tròn thời điểm về đầu bucket.

Khi incident trong vài phút, dùng 1m hoặc 5m tùy traffic; bin quá nhỏ ở hệ thống ít requests gây dao động lớn, bin quá lớn có thể che burst lỗi.

## 13. Tính tỉ lệ lỗi theo HTTP request

~~~kusto
AppRequests
| where TimeGenerated >= ago(1h)
| summarize
    Total = count(),
    Failed = countif(Success == false)
    by AppRoleName, bin(TimeGenerated, 5m)
| extend FailureRatePct = iff(
    Total == 0,
    0.0,
    round(100.0 * todouble(Failed) / todouble(Total), 2)
)
| order by TimeGenerated asc
~~~

### Vì sao không tính mỗi HTTP 500?

**Success** trong Application Insights chịu semantics từ SDK/telemetry và có thể coi một số status codes là lỗi khác với kỳ vọng nghiệp vụ. Nếu muốn chỉ HTTP server errors, dùng thêm:

~~~kusto
AppRequests
| where TimeGenerated >= ago(1h)
| summarize
    Requests = count(),
    Http5xx = countif(toint(ResultCode) between (500 .. 599))
    by AppRoleName
| extend Http5xxPct = round(
    100.0 * todouble(Http5xx) / todouble(Requests), 2)
~~~

### Đọc kết quả có trách nhiệm

Một nhóm có **1 lỗi / 2 requests = 50%** nhưng nhóm khác **200 lỗi / 100.000 requests = 0,2%**. Cần xem cả tỷ lệ và mẫu số, không chỉ sắp xếp dịch vụ theo FailureRatePct.

## 14. Application Insights sampling và ItemCount

Application Insights có thể dùng **sampling** để giảm volume/cost. Trong các bảng tương ứng, **ItemCount** (khi có) cho biết số telemetry items được mẫu đại diện theo cơ chế SDK/ingestion.

~~~kusto
AppRequests
| where TimeGenerated >= ago(1h)
| summarize
    StoredRows = count(),
    EstimatedRequests = sum(ItemCount),
    EstimatedFailed = sumif(ItemCount, Success == false)
    by AppRoleName
| extend EstimatedFailurePct = round(
    100.0 * todouble(EstimatedFailed)
    / todouble(EstimatedRequests), 2)
~~~

### Không so sánh ngây thơ

- **count()** đếm records đã ingest.
- **sum(ItemCount)** có thể xấp xỉ events gốc khi sampling và field semantics phù hợp.
- Một số telemetry bị loại trước ingestion, bị drop do quotas, sampling không đồng đều hoặc custom instrumentation.
- **percentile(DurationMs, 95)** trên sampled rows không tự được weighted theo ItemCount.
- Nếu bảng thiếu ItemCount, ví dụ phải được điều chỉnh; không tự giả định ItemCount=1 ở mọi hệ thống.

Trong báo cáo chính thức, ghi rõ **stored events hay estimated original events**, sampling configuration và mức tin cậy của số liệu.

## 15. Độ trễ: avg, percentile p50/p95/p99

~~~kusto
AppRequests
| where TimeGenerated >= ago(2h)
| summarize
    Requests = count(),
    AvgMs = round(avg(DurationMs), 1),
    P50Ms = round(percentile(DurationMs, 50), 1),
    P95Ms = round(percentile(DurationMs, 95), 1),
    P99Ms = round(percentile(DurationMs, 99), 1)
    by AppRoleName, bin(TimeGenerated, 5m)
| order by TimeGenerated asc
~~~

### Vì sao p95 quan trọng?

Trung bình 100 ms có thể che việc 5% requests mất 3 giây. **p95** là ngưỡng mà khoảng 95% quan sát có latency không vượt qua (theo cách tính percentile gần đúng của engine); **p99** xem tail latency cao hơn.

### Hạn chế

- Sample size ít khiến p99 nhiễu.
- Percentile queries trong KQL có tính xấp xỉ theo thuật toán.
- Sampling và missing telemetry làm sai lệch phân bố.
- Có thể phân tích endpoint khác nhau: checkout và health probe có latency rất khác.
- **DurationMs** là request telemetry duration, không phải toàn bộ browser-to-origin time qua CDN/gateway.

## 16. Phân tích top endpoint lỗi và chậm

Các endpoint nhiều lỗi nhất:

~~~kusto
AppRequests
| where TimeGenerated >= ago(1h)
| summarize
    Total = count(),
    Failed = countif(Success == false),
    P95Ms = percentile(DurationMs, 95)
    by AppRoleName, Name
| where Total >= 20
| extend FailurePct = round(100.0 * todouble(Failed) / Total, 2)
| top 20 by Failed desc
~~~

### Tại sao dùng Name thay URL?

Application Insights thường chuẩn hóa **Name** theo route như **GET /orders/{id}**. Nếu group theo URL chứa orderId/customerId, số nhóm tăng không kiểm soát, chi phí truy vấn cao và có nguy cơ hiển thị thông tin nhạy cảm.

**Điều kiện Total >= 20 là ví dụ**, cần thay theo traffic thực. Một endpoint ít request nhưng quan trọng về doanh thu vẫn cần điều tra dù có 1–2 lỗi.

## 17. Phân biệt ResultCode, Success và nghiệp vụ thất bại

Request HTTP 200 có thể trả:

~~~json
{
  "status": "PAYMENT_DECLINED",
  "reason": "BUSINESS_RULE"
}
~~~

Về HTTP, request có thể thành công; về nghiệp vụ, thanh toán không hoàn tất. KQL trên **AppRequests.Success** không tự biết quy tắc business.

### Thiết kế telemetry

- Logs/custom events có **outcome code** được chuẩn hóa.
- Không ghi card data, auth token, email/plain PII vào trace.
- Chứa **OperationId/traceId** để liên kết request với nghiệp vụ.
- Giữ semantics rõ: **technical failure** và **business rejection** khác nhau.

**Không biến mọi HTTP 4xx thành sự cố server.** 401/403 do thiếu quyền, 429 do throttling và 404 do resource không tồn tại cần phân loại theo endpoint/khách hàng.

## 18. let: đặt phạm vi một lần, dùng lại

KQL hỗ trợ **let** để khai báo biểu thức, scalar hoặc tabular expressions.

~~~kusto
let StartTime = ago(2h);
let Service = "checkout-api";
AppRequests
| where TimeGenerated >= StartTime
| where AppRoleName == Service
| summarize Requests = count(),
    Failures = countif(Success == false)
    by bin(TimeGenerated, 5m)
| order by TimeGenerated asc
~~~

### Lưu ý về let

**let** gắn tên với một biểu thức chứ không luôn là giá trị được tính/chốt ngay. Với biểu thức không xác định hoặc truy vấn lớn tái sử dụng nhiều nơi, có thể cân nhắc **toscalar()** hoặc **materialize()** khi phù hợp và engine hỗ trợ. Không materialize một tập dữ liệu khổng lồ chỉ để “tăng tốc” không đo đạc.

## 19. Diễn giải kết quả đúng thứ tự

Một dashboard phản ánh HTTP 500 tăng:

~~~text
10:10  API deployment completed
10:12  AppRequests p95 rises
10:13  AppDependencies SQL failures rise
10:15  AppExceptions timeout increase
10:18  AKS restarts some Pods
~~~

Các sự kiện **có tương quan về thời gian**, nhưng không tự chứng minh deployment gây ra SQL timeout. KQL giúp xác định sự kiện nào xuất hiện trước, ở phiên bản/Pod nào và request nào có dependency failure. Root cause cần kiểm chứng bằng logs, traces, deployment changes và đôi khi reproductions.

**Quy trình tốt:** xác định time window → định lượng ảnh hưởng → phân nhóm → tìm dependency → đối chiếu hạ tầng/change events → xác minh giả thuyết → hành động có rollback.

## 20. AppDependencies: dịch vụ phụ thuộc nào chậm?

**AppDependencies** chứa những outbound calls được instrument, như HTTP, database hoặc các loại dependency khác theo SDK/agent:

~~~kusto
AppDependencies
| where TimeGenerated >= ago(2h)
| summarize
    Calls = count(),
    Failed = countif(Success == false),
    AvgMs = round(avg(DurationMs), 1),
    P95Ms = round(percentile(DurationMs, 95), 1)
    by AppRoleName, Type, Target
| top 20 by Failed desc
~~~

Nếu ứng dụng có **Target=sql-prod.database.windows.net** với tỉ lệ lỗi tăng, cần kiểm tra SQL availability, query timeout, connection pool, TLS, firewall và identity. **Target không nhất thiết ánh xạ duy nhất tới một Azure resource.**

Không phải mọi SDK/tác vụ đều được auto-instrument. Không thấy dependency telemetry không chứng minh ứng dụng không gọi dependency.

## 21. Lỗi và p95 của dependency theo thời gian

~~~kusto
AppDependencies
| where TimeGenerated >= ago(3h)
| where AppRoleName == "checkout-api"
| summarize
    Total=count(),
    Failed=countif(Success == false),
    P95Ms=percentile(DurationMs, 95)
    by Target, bin(TimeGenerated, 5m)
| extend FailurePct=round(
    100.0 * todouble(Failed) / todouble(Total), 2)
| order by TimeGenerated asc
~~~

Với dependency **Type** là SQL, Service Bus hoặc loại khác, **ResultCode** không chắc là HTTP status; không áp điều kiện toint(ResultCode) >= 500 cho mọi dependency. Dùng **Success**, **Type**, service-specific diagnostics và errors tương ứng.

## 22. AppExceptions: nhóm lỗi thay vì đọc từng stack trace

~~~kusto
AppExceptions
| where TimeGenerated >= ago(2h)
| summarize
    ExceptionRows=count(),
    LastSeen=max(TimeGenerated)
    by AppRoleName, ProblemId,
       ExceptionType=column_ifexists("ExceptionType", "")
| top 20 by ExceptionRows desc
~~~

Để điều tra một lỗi:

~~~kusto
AppExceptions
| where TimeGenerated >= ago(1h)
| where AppRoleName == "checkout-api"
| project TimeGenerated, OperationId, ProblemId,
    ExceptionType=column_ifexists("ExceptionType", ""),
    Message=column_ifexists("Message", "")
| top 30 by TimeGenerated desc
~~~

Tên và sự tồn tại của **ExceptionType, Message, ProblemId** phụ thuộc bảng/schema. **Details** có thể chứa exception hierarchy; không mặc định Message là toàn bộ stack trace. Không gửi raw exceptions chứa PII hoặc secret vào ticket/chat công khai.

## 23. AppTraces: tìm tín hiệu ứng dụng

~~~kusto
AppTraces
| where TimeGenerated >= ago(1h)
| where AppRoleName == "checkout-api"
| where Message has "timeout"
| project TimeGenerated, SeverityLevel, OperationId,
    AppRoleName, Message
| top 50 by TimeGenerated desc
~~~

Log văn bản tùy ý khó tổng hợp và có thể lộ dữ liệu:

~~~text
checkout failed for customer 12345 with auth token ...
~~~

Nên dùng **structured logging** với fields có ý nghĩa, tránh PII/tokens:

~~~json
{
  "event": "checkout_failed",
  "failure_category": "dependency_timeout",
  "trace_id": "synthetic-id",
  "dependency": "azure-sql",
  "elapsed_ms": 1200
}
~~~

Các fields có thể được đưa vào **Properties/customDimensions** theo instrumentation; không tự giả định mọi key sẽ hiện lên nếu logger/telemetry pipeline chưa cấu hình.

## 24. Dynamic JSON và Properties

Trong nhiều bảng, **Properties** là trường **dynamic** chứa key-value:

~~~kusto
AppTraces
| where TimeGenerated >= ago(2h)
| extend
    Category=tostring(Properties["failure_category"]),
    Dependency=tostring(Properties["dependency"]),
    ElapsedMs=todouble(Properties["elapsed_ms"])
| where Category == "dependency_timeout"
| summarize
    Events=count(),
    P95ElapsedMs=percentile(ElapsedMs, 95)
    by AppRoleName, Dependency
~~~

Khi một field là **string chứa JSON**, có thể **parse_json()**:

~~~kusto
AppTraces
| where TimeGenerated >= ago(30m)
| extend PayloadText=tostring(Properties["payload_summary"])
| extend Parsed=parse_json(PayloadText)
| project TimeGenerated,
    EventType=tostring(Parsed["event_type"]),
    Outcome=tostring(Parsed["outcome"])
| take 30
~~~

Với Properties đã là dynamic, dùng **Properties["key"]** trực tiếp. Không parse/log payload nhạy cảm vào dashboard nếu không được phép.

## 25. Null, chuỗi rỗng và chuyển đổi kiểu

~~~kusto
AppTraces
| where TimeGenerated >= ago(1h)
| extend ParsedDuration=todouble(Properties["duration_ms"])
| summarize
    Total=count(),
    Valid=countif(isnotnull(ParsedDuration)),
    Invalid=countif(isnull(ParsedDuration))
    by AppRoleName
~~~

- **toint()/tolong()/todouble()** có thể trả null nếu parse thất bại.
- **coalesce()** chọn giá trị không null đầu tiên, không nên tự thay giá trị lỗi thành 0 nếu 0 có ý nghĩa.
- **isnull()** và **isempty()/isnotempty()** giải quyết các trạng thái dữ liệu khác nhau.
- Thiếu DurationMs không đồng nghĩa request hoàn thành với 0 ms.

Không tự cho missing data bằng 0 rồi kết luận p95 giảm.

## 26. Regex và trích trường từ log chưa có cấu trúc

~~~kusto
AppTraces
| where TimeGenerated >= ago(1h)
| where Message contains "traceId="
| extend ExtractedTraceId=
    extract(@"traceId=([A-Za-z0-9_-]+)", 1, Message)
| where isnotempty(ExtractedTraceId)
| project TimeGenerated, AppRoleName, ExtractedTraceId
| take 50
~~~

Regex dễ lỗi khi format thay đổi, tốn công/chi phí và có thể kéo PII ra kết quả. **OperationId** từ instrumentation chuẩn đáng tin cậy hơn cách parse một trace ID tự do, khi context propagation hoạt động đúng.

## 27. OperationId: liên kết một giao dịch

~~~text
HTTP /checkout (OperationId=op-42)
      |
      +-- SQL dependency    (OperationId=op-42)
      +-- Service Bus call  (OperationId=op-42)
      +-- Trace             (OperationId=op-42)
      +-- Exception         (OperationId=op-42)
~~~

Ví dụ truy vết một operation đã biết:

~~~kusto
let Op = "<OPERATION_ID_FROM_INCIDENT>";
union isfuzzy=true
    (AppRequests | project TimeGenerated, OperationId,
        Kind="request", Detail=Name, AppRoleName),
    (AppDependencies | project TimeGenerated, OperationId,
        Kind="dependency", Detail=Name, AppRoleName),
    (AppTraces | project TimeGenerated, OperationId,
        Kind="trace", Detail=Message, AppRoleName),
    (AppExceptions | project TimeGenerated, OperationId,
        Kind="exception",
        Detail=tostring(column_ifexists("Message", "")), AppRoleName)
| where TimeGenerated >= ago(2h)
| where OperationId == Op
| order by TimeGenerated asc
~~~

**Thay placeholder** bằng ID thật. Nếu một bảng không tồn tại, cần điều chỉnh theo schema; union isfuzzy không tự cấp quyền truy cập hoặc thay thế bảng bị thiếu. Telemetry sampling, missing context propagation hoặc các background jobs có thể khiến vài spans không xuất hiện.

## 28. Join requests lỗi với dependencies

Giới hạn thời gian **ở cả hai bên** và tổng hợp dependencies trước để tránh nhân dòng:

~~~kusto
let FailedRequests =
    AppRequests
    | where TimeGenerated >= ago(1h)
    | where AppRoleName == "checkout-api"
    | where Success == false
    | where isnotempty(OperationId)
    | project RequestAt=TimeGenerated, OperationId,
        RequestName=Name, RequestCode=ResultCode;
let DependencyRollup =
    AppDependencies
    | where TimeGenerated >= ago(1h)
    | where isnotempty(OperationId)
    | summarize
        DepCount=count(),
        FailedDeps=countif(Success == false),
        MaxDepMs=max(DurationMs)
        by OperationId;
FailedRequests
| join kind=leftouter (DependencyRollup) on OperationId
| project RequestAt, OperationId, RequestName, RequestCode,
    DepCount, FailedDeps, MaxDepMs
| top 30 by RequestAt desc
~~~

Một operation có thể có nhiều dependencies: **join trực tiếp rồi count()** sẽ đếm trùng requests. Tổng hợp phải trước join nếu muốn dữ liệu một dòng/operation ở phía phải.

Một **OperationId** cũng có thể gắn nhiều AppRequests trong distributed transaction; muốn quan hệ parent-child chính xác, đối chiếu **Id, ParentId/span IDs** theo schema và timestamps, không xem OperationId là primary key duy nhất của request.

## 29. Chọn join kind theo câu hỏi

| Loại | Câu hỏi |
|---|---|
| **inner** | Bên trái/bên phải có khóa khớp nào? |
| **innerunique** | Join với deduplication phía trái theo key (dễ làm mất chi tiết nếu hiểu sai) |
| **leftouter** | Giữ tất cả dòng bên trái kể cả không có match |
| **leftsemi** | Dòng trái có tồn tại match không? |
| **leftanti** | Dòng trái nào không có match? |
| **fullouter** | Có những dòng unmatched nào ở cả hai phía? |

Tìm request lỗi thiếu dependency telemetry:

~~~kusto
let R =
    AppRequests
    | where TimeGenerated >= ago(30m)
    | where Success == false
    | where isnotempty(OperationId)
    | project TimeGenerated, OperationId, Name;
let D =
    AppDependencies
    | where TimeGenerated >= ago(30m)
    | where isnotempty(OperationId)
    | distinct OperationId;
R
| join kind=leftanti (D) on OperationId
| top 30 by TimeGenerated desc
~~~

Không có dependency telemetry không đồng nghĩa lỗi không liên quan dependency: instrumentation/sampling/scope/ingestion có thể thiếu.

## 30. arg_max: lấy trạng thái mới nhất của đối tượng

Các bảng inventory ghi nhiều snapshots. Để xem trạng thái Pod mới nhất:

~~~kusto
KubePodInventory
| where TimeGenerated >= ago(2h)
| summarize arg_max(TimeGenerated, PodStatus)
    by ClusterName, Namespace, Name
| project TimeGenerated, ClusterName, Namespace, PodName=Name, PodStatus
| order by TimeGenerated desc
~~~

**arg_max(TimeGenerated, PodStatus)** lấy PodStatus thuộc dòng có TimeGenerated lớn nhất, không phải giá trị PodStatus cao nhất theo alphabet.

### Cần lưu ý

Kubernetes Pod tên giống nhau qua những lần thay thế không nhất thiết là cùng instance; dùng Pod UID nếu bảng có và mục đích cần xác định instance chính xác. Inventory là snapshots, không phải event log đầy đủ của mọi lần container crash.

## 31. dcount: số ID duy nhất (ước lượng)

~~~kusto
AppRequests
| where TimeGenerated >= ago(1h)
| summarize
    Requests=count(),
    DistinctOperations=dcount(OperationId)
    by AppRoleName
~~~

**dcount()** là distinct-count ước lượng thích hợp cho tập lớn. **OperationId** không phải user ID. Không group trực tiếp theo customer ID/session ID nếu chưa có cơ sở quyền, privacy và nhu cầu phân tích; cardinality cao làm query đắt và dễ lộ dữ liệu.

## 32. So sánh trước/sau deployment

Giả sử deployment lúc **03:20 UTC**:

~~~kusto
let DeployAt = datetime(2026-11-20T03:20:00Z);
AppRequests
| where TimeGenerated >= DeployAt - 30m
  and TimeGenerated < DeployAt + 30m
| where AppRoleName == "checkout-api"
| extend Phase = iff(TimeGenerated < DeployAt, "before", "after")
| summarize
    Requests=count(),
    Failed=countif(Success == false),
    P95Ms=percentile(DurationMs, 95)
    by Phase
| extend FailurePct=round(100.0 * todouble(Failed) / Requests, 2)
| order by Phase asc
~~~

### Vì sao chưa đủ kết luận?

- Traffic mix và giờ cao điểm có thể khác.
- Rolling deployment diễn ra trên nhiều Pod trong khoảng thời gian dài.
- Version mới và cũ cùng phục vụ ở canary.
- Azure SQL/Redis hoặc hạ tầng có thể gặp sự cố cùng lúc.
- Cần phân tích endpoint/version/dependency và **AzureActivity/deployment events** để kiểm chứng.

## 33. So sánh theo phiên bản ứng dụng

Nếu ứng dụng tự gắn version vào **Properties**:

~~~kusto
AppRequests
| where TimeGenerated >= ago(2h)
| extend AppVersion=tostring(Properties["app_version"])
| where isnotempty(AppVersion)
| summarize
    Requests=count(),
    Failed=countif(Success == false),
    P95Ms=percentile(DurationMs, 95)
    by AppRoleName, AppVersion
| extend FailurePct=round(
    100.0 * todouble(Failed) / Requests, 2)
| order by AppRoleName asc, FailurePct desc
~~~

**app_version là ví dụ custom property**, không phải cột mặc định luôn có. Có thể dùng deployment revision, image digest, cloud role instance hoặc release ID nếu pipeline cung cấp dimension phù hợp. Đừng group theo URL/request ID cá nhân để thay thế release version.

## 34. make-series và biểu đồ timechart

~~~kusto
AppRequests
| where TimeGenerated >= ago(3h)
| where AppRoleName == "checkout-api"
| make-series RequestCount=count() default=0
    on TimeGenerated from ago(3h) to now() step 5m
| render timechart
~~~

**make-series** tạo series với các bucket đều; **render timechart** là visualization directive cho giao diện hỗ trợ. Với query API/SDK, giá trị data arrays mới là phần cần xử lý.

**default=0 không chứng minh traffic bằng 0** nếu agent/ingestion hỏng. Đừng tạo chuỗi với hàng nghìn groups hoặc bước vài giây trên nhiều tháng dữ liệu khi chưa tính chi phí.

## 35. Anomaly detection và seasonality

KQL có những time-series functions theo backend/version để tìm xu hướng và điểm dị thường. Nhưng:

- Traffic ngày thường/cuối tuần tạo seasonality.
- Sự kiện marketing hoặc lịch batch là bất thường hợp lệ.
- Sampling, log loss và ingestion delay có thể tạo spikes/gaps giả.
- Low traffic khiến kết quả thống kê thiếu tin cậy.

Một cảnh báo đơn giản như **5xx rate > ngưỡng trong 10 phút với min 100 requests** đôi khi dễ giải thích hơn anomaly algorithm chưa được kiểm thử. Dùng anomaly detection là tín hiệu bổ sung, không thay root-cause investigation.

## 36. Ingestion lag và event time

Khi backend hỗ trợ **ingestion_time()**, có thể xem chênh lệch thời gian ingest và event:

~~~kusto
AppRequests
| where TimeGenerated >= ago(2h)
| extend IngestedAt=ingestion_time()
| where isnotnull(IngestedAt)
| extend LagSeconds=
    datetime_diff("second", IngestedAt, TimeGenerated)
| summarize
    Samples=count(),
    P95LagSeconds=percentile(LagSeconds, 95),
    MaxLagSeconds=max(LagSeconds)
    by AppRoleName
~~~

Hàm ingestion_time() không có cùng hành vi/precision hoặc support trong mọi bảng/giải pháp; clock skew, buffering và transforms gây chênh lệch. Nếu không có dòng hôm nay, hãy kiểm tra pipeline ingestion/agent trước khi tuyên bố hệ thống ngừng gửi requests.

### Event time khác ingestion time

**TimeGenerated** là thời điểm telemetry phản ánh theo schema; **ingestion_time()** nếu có là lúc backend ingest. Chúng khác nhau và có thể không tăng cùng thứ tự. Khi đối chiếu 10:15, phải dùng cùng chuẩn UTC và ghi rõ mốc nào.

## 37. ContainerLogV2: tìm lỗi Java trong AKS

Khi Container Insights đã thu thập container stdout/stderr vào **ContainerLogV2**:

~~~kusto
ContainerLogV2
| where TimeGenerated >= ago(1h)
| where PodNamespace == "checkout"
| extend Text=tostring(LogMessage)
| where Text has "Exception" or Text has "ERROR"
| project TimeGenerated, PodNamespace, PodName,
    ContainerName, LogLevel, Text
| top 50 by TimeGenerated desc
~~~

**LogLevel** có thể được thu thập/parse theo cấu hình, không nên dựa duy nhất vào LogLevel nếu ứng dụng in log không đúng format; trường này có thể rỗng. Tên các cột theo ContainerLogV2; nếu workspace đang dùng **ContainerLog** đời cũ, phải dùng schema khác, không chỉ đổi tên bảng.

### Cẩn trọng với Java multi-line exceptions

Một stack trace Java nhiều dòng có thể chia thành nhiều log records hoặc được multiline processing gom lại tùy agent/pipeline. Cùng Pod/TimeGenerated gần nhau **không đảm bảo các dòng thuộc cùng exception**. Structured logging với traceId và newline handling phù hợp giúp điều tra chính xác hơn.

## 38. Phân nhóm lỗi theo Pod trong AKS

~~~kusto
ContainerLogV2
| where TimeGenerated >= ago(2h)
| where PodNamespace == "checkout"
| extend Text=tostring(LogMessage)
| where Text has "OutOfMemoryError" or Text has "TimeoutException"
| summarize MatchingLines=count(), LastSeen=max(TimeGenerated)
    by PodNamespace, PodName, ContainerName
| top 20 by MatchingLines desc
~~~

### Giới hạn của cách đếm

**MatchingLines** đếm các dòng log có thuật ngữ, không đếm số incident hay restart. Một exception có thể tạo nhiều dòng, một Pod có thể phát log lặp do retry. Cần đối chiếu metrics/status inventory và Kubernetes events.

## 39. KubePodInventory: Pod nào bất thường?

~~~kusto
KubePodInventory
| where TimeGenerated >= ago(1h)
| summarize arg_max(TimeGenerated, PodStatus)
    by ClusterName, Namespace, Name
| where PodStatus !in ("Running", "Succeeded")
| project TimeGenerated, ClusterName, Namespace,
    PodName=Name, PodStatus
| top 30 by TimeGenerated desc
~~~

### Không nên giải thích quá mức

Pod ở **Pending** có thể do image pull, scheduling/quota, PVC, admission, taints hoặc node capacity. Pod **Succeeded** có thể là Job đã hoàn thành, không phải service hỏng. Các trạng thái còn phụ thuộc schema/chu kỳ snapshot; Pod CrashLoopBackOff thường là container waiting reason chứ không đơn thuần PodStatus.

Để xác định restart và waiting reason chính xác, cần **Kubernetes events, kubectl describe và container state** theo quyền được cấp, kết hợp với logs nếu pipeline đã ingest những signals đó.

## 40. KubeNodeInventory: góc nhìn nodes

~~~kusto
KubeNodeInventory
| where TimeGenerated >= ago(2h)
| summarize LastSeen=max(TimeGenerated)
    by ClusterName, Computer
| order by LastSeen desc
~~~

Bảng KubeNodeInventory có thể có tên cột/định dạng khác theo schema; nếu **Computer** không có, chọn NodeName/field phù hợp trong schema thực.

### Câu hỏi cần kiểm tra

- Có node nào không còn xuất hiện snapshots?
- Pod failures tập trung ở node nào?
- Node có tình trạng CPU/memory/disk pressure không?
- AKS node pool autoscale/upgrade gần thời điểm incident?

**Node không có dòng mới** không tự là node chết; ingestion/agent/cấu hình workspace có thể mất dữ liệu. Đối chiếu trạng thái cluster từ control plane.

## 41. Heartbeat: VM hay agent ngừng gửi telemetry?

~~~kusto
Heartbeat
| where TimeGenerated >= ago(3h)
| summarize LastHeartbeat=max(TimeGenerated) by Computer
| extend MinutesSinceLastHeartbeat =
    datetime_diff("minute", now(), LastHeartbeat)
| order by MinutesSinceLastHeartbeat desc
~~~

### Cách hiểu

**Heartbeat** là tín hiệu agent/máy gửi vào Logs theo collection configuration. Nó không phải ping tới application API. Máy đang chạy nhưng agent bị ngắt, DCR sai hoặc data ingestion trễ có thể khiến LastHeartbeat cũ.

Ngược lại, VM có heartbeat mới không chứng minh API hoặc SQL bên trong đã khỏe. Cần combine với **Perf, service logs, Azure Metrics và synthetic probes**.

## 42. Perf: phân tích CPU/memory qua counters

Nếu workspace đã cấu hình thu **Perf**:

~~~kusto
Perf
| where TimeGenerated >= ago(2h)
| summarize
    Samples=count(),
    LastSeen=max(TimeGenerated)
    by Computer, ObjectName, CounterName
| top 30 by Samples desc
~~~

Sau khi biết counter names thực, chọn một counter:

~~~kusto
Perf
| where TimeGenerated >= ago(1h)
| where CounterName == "% Processor Time"
| summarize AvgValue=avg(CounterValue),
    P95Value=percentile(CounterValue, 95)
    by Computer, bin(TimeGenerated, 5m)
| order by TimeGenerated asc
~~~

### Lưu ý

- **CounterName** và **ObjectName** khác giữa Windows/Linux/collection rule.
- % Processor Time có thể là per-core/per-process/total theo InstanceName.
- Dữ liệu CPU ở Pod/Kubernetes không nhất thiết nằm trong Perf.
- Không kết luận VM CPU luôn 90% nếu query chỉ đọc một subset counter instances.

## 43. InsightsMetrics: khám phá metric schemas

Một bảng **InsightsMetrics** có thể có các cột như **Namespace**, **Name**, **Val**, **Tags**, **TimeGenerated** theo giải pháp:

~~~kusto
InsightsMetrics
| where TimeGenerated >= ago(2h)
| summarize Samples=count()
    by Namespace, Name
| top 30 by Samples desc
~~~

Khi đã biết metric có thật:

~~~kusto
InsightsMetrics
| where TimeGenerated >= ago(1h)
| where Namespace == "<ACTUAL_NAMESPACE>"
  and Name == "<ACTUAL_METRIC_NAME>"
| summarize AvgValue=avg(Val)
    by bin(TimeGenerated, 5m)
| order by TimeGenerated asc
~~~

**Phải thay placeholders theo schema hiện hữu**. Các metric tên gần giống nhau có thể khác đơn vị: nanocores, bytes, percentages hoặc rates. Không chia/nhân đơn vị nếu chưa đọc định nghĩa đo.

## 44. AzureMetrics: resource metrics đã export tới Logs

Nếu diagnostic settings đưa metrics vào Log Analytics:

~~~kusto
AzureMetrics
| where TimeGenerated >= ago(2h)
| summarize Samples=count()
    by ResourceProvider, MetricName
| top 30 by Samples desc
~~~

Các trường metadata/units như **MetricName, Average, Total, Maximum** phụ thuộc bảng/schema và metric. **Azure Metrics backend** thường là nguồn phù hợp để đo service metrics; AzureMetrics chỉ hiện khi data được cấu hình export/ingest theo con đường được hỗ trợ.

Nếu bảng thiếu, không giả định Azure service không có metric. Hãy kiểm tra **Metrics blade**, data collection/diagnostic settings, resource scope và permissions.

## 45. AzureActivity: có ai thay đổi hạ tầng gần lúc lỗi?

**AzureActivity** là nguồn hữu ích để xem hoạt động **management/control plane** (ví dụ tạo, sửa, xóa hoặc ghi resource). Tùy schema/collection, các cột thường gặp gồm **TimeGenerated, OperationNameValue, ActivityStatusValue, Caller, CorrelationId, ResourceGroup, _ResourceId**.

~~~kusto
AzureActivity
| where TimeGenerated >= ago(4h)
| where ActivityStatusValue in ("Succeeded", "Failed")
| project TimeGenerated, OperationNameValue, ActivityStatusValue,
    Caller, ResourceGroup, _ResourceId, CorrelationId
| top 50 by TimeGenerated desc
~~~

### Vì sao phải lọc resource scope?

Một workspace tập trung có thể ingest activity từ nhiều subscriptions. Tìm “mọi thao tác trong 4 giờ” có thể trả hàng nghìn dòng không liên quan. Hãy dùng resource group, resource ID hoặc operation cụ thể:

~~~kusto
AzureActivity
| where TimeGenerated >= ago(4h)
| where ResourceGroup =~ "rg-checkout-prod"
| where OperationNameValue contains "write"
| project TimeGenerated, Caller, OperationNameValue,
    ActivityStatusValue, _ResourceId, CorrelationId
| top 30 by TimeGenerated desc
~~~

**AzureActivity không ghi tất cả data-plane operations** như đọc Blob hay chạy SQL SELECT. Hệ thống cần Azure resource diagnostic logs, database audit hoặc app telemetry để điều tra các hoạt động đó. Mặt khác, CI/CD triển khai image/container có thể sinh records ở nhiều nguồn ngoài AzureActivity.

## 46. AzureDiagnostics: chọn ResourceProvider và Category

**AzureDiagnostics** là bảng chung cho nhiều resource diagnostic logs khi tài nguyên dùng **AzureDiagnostics destination mode**:

~~~kusto
AzureDiagnostics
| where TimeGenerated >= ago(1h)
| summarize Records=count()
    by ResourceProvider, ResourceType, Category
| top 30 by Records desc
~~~

Sau khi biết Category cụ thể:

~~~kusto
AzureDiagnostics
| where TimeGenerated >= ago(1h)
| where ResourceProvider == "MICROSOFT.KEYVAULT"
| summarize Events=count()
    by Category, bin(TimeGenerated, 5m)
| order by TimeGenerated asc
~~~

### Schema caveat

- Bảng này chứa nhiều cột theo resource/category; những cột có hậu tố **_s, _d, _g** hoặc dạng JSON tùy trường có thể xuất hiện.
- **AzureDiagnostics** không phải nơi mặc định cho mọi dịch vụ: nhiều resource dùng **resource-specific tables** khi cấu hình tương ứng.
- Không viết query phụ thuộc một field như **resultType_s** trước khi kiểm tra nó có thật.
- **ResourceProvider** có thể là tên namespace viết hoa theo log format; kiểm tra giá trị thực trước khi lọc chính xác.

Không đổi diagnostic destination mode production chỉ vì một câu truy vấn sample không thấy bảng. Phải đánh giá retention, dữ liệu hiện có, query changes, access và chi phí.

## 47. Resource-specific tables so với AzureDiagnostics

Một dịch vụ có thể có bảng theo tên riêng của nhóm log:

~~~text
Azure resource diagnostic settings
       |
       +-- Destination mode: AzureDiagnostics
       |       |
       |       v
       |    AzureDiagnostics shared schema
       |
       +-- Destination mode: resource-specific
               |
               v
         Service-specific tables
         (tên/cột tùy category)
~~~

### Khi điều tra Key Vault hoặc Application Gateway

1. Mở diagnostic settings của đúng resource để biết categories và workspace đích.
2. Mở schema browser của workspace.
3. Xác nhận mode/table thực tế.
4. Dùng **TimeGenerated**, **_ResourceId** và trường status/error của bảng đó.
5. Đối chiếu với request application và AzureActivity.

Không ghi cứng một bảng tên dịch vụ bất kỳ rồi nói đó là chuẩn cho mọi region/tier. Các bảng mới/legacy có thể cùng tồn tại trong quá trình chuyển collection.

## 48. _ResourceId: giới hạn đúng Azure resource

Trong nhiều bảng, **_ResourceId** giúp gắn record với Azure resource. Lọc một resource có thể giảm noise và tránh trộn môi trường:

~~~kusto
AppRequests
| where TimeGenerated >= ago(1h)
| where _ResourceId =~
    "/subscriptions/<SUB_ID>/resourcegroups/<RG>/providers/microsoft.insights/components/<APP_NAME>"
| summarize Requests=count() by AppRoleName
~~~

**Thay ID placeholders** bằng resource ID chính xác. _ResourceId không bắt buộc có/được điền trong mọi bảng; đặc biệt các custom logs, dữ liệu migrated hoặc agent-generated records có thể khác.

### Resource filtering không thay RBAC

Một query filter không phải cơ chế bảo vệ tenant data. Người dùng có quyền query toàn workspace vẫn có thể bỏ filter; phải cấp quyền truy cập log theo workspace/resource/table phù hợp, dùng redaction và data classification.

## 49. Resource ID và environment metadata

Để giảm nhầm staging/prod:

~~~kusto
AppRequests
| where TimeGenerated >= ago(1h)
| summarize
    Requests=count(),
    Failures=countif(Success == false)
    by _ResourceId, AppRoleName
| order by Failures desc
~~~

Một **AppRoleName** như **api** có thể được tái sử dụng trong nhiều môi trường. Nếu query bỏ **_ResourceId**, số liệu sẽ trộn sản phẩm và gây kết luận sai. Nếu ứng dụng không gắn environment metadata, cần thêm **deployment/environment dimension** được quản lý, không lấy hostname từ raw URL để suy đoán khi không đủ bằng chứng.

## 50. Ghép thay đổi hạ tầng với lỗi theo timeline

Một cách hữu ích là biểu diễn **các events theo từng dòng thời gian**, thay vì join các records chỉ bằng một bucket năm phút rồi tuyên bố quan hệ nhân quả:

~~~kusto
let RequestErrors =
    AppRequests
    | where TimeGenerated >= ago(3h)
    | where AppRoleName == "checkout-api"
    | where Success == false
    | project TimeGenerated, Kind="request_failure",
        Detail=Name;
let Changes =
    AzureActivity
    | where TimeGenerated >= ago(3h)
    | where ResourceGroup =~ "rg-checkout-prod"
    | where OperationNameValue contains "write"
    | project TimeGenerated, Kind="azure_resource_change",
        Detail=OperationNameValue;
union RequestErrors, Changes
| top 100 by TimeGenerated desc
~~~

### Diễn giải

- Nếu write operation xuất hiện trước lỗi 500, đó là **manh mối**, chưa là bằng chứng nguyên nhân.
- AzureActivity có thể không ghi app container rollout hoặc database schema change đầy đủ.
- Thời gian các nguồn khác nhau cần chuẩn UTC và lưu ý ingestion delay.
- Khi query nhiều bảng có quyền/retention khác nhau, thiếu dòng trong một nguồn không phải chứng cứ phủ định.

**Join theo bin(TimeGenerated, 5m)** chỉ nói sự kiện cùng bucket, không chứng minh dependency/causality.

## 51. Điều tra lỗi 401/403 và throttling

Các mã lỗi cần phân nhóm vì cách xử lý khác nhau:

~~~kusto
AppRequests
| where TimeGenerated >= ago(1h)
| extend Status=toint(ResultCode)
| extend Category=case(
    Status == 401, "unauthorized",
    Status == 403, "forbidden",
    Status == 429, "throttled",
    Status between (500 .. 599), "server_error",
    Status between (400 .. 499), "other_4xx",
    Status between (200 .. 399), "2xx_3xx",
    "other"
)
| summarize Requests=count()
    by AppRoleName, Category
| order by Requests desc
~~~

### Điều cần kiểm tra

| Mã | Hướng điều tra |
|---|---|
| **401** | JWT/credential, token audience/expiry, policy |
| **403** | Authorization, Entra roles, Key Vault/Storage data-plane RBAC, firewall |
| **429** | App rate limit, backend quota, retry behavior |
| **5xx** | Exceptions, dependencies, infrastructure, capacity |

Một 403 từ Key Vault dependency không nhất thiết hiện như **HTTP 403 AppRequests** ở API: ứng dụng có thể bắt lỗi và trả 500. Cần xem AppDependencies/AppExceptions với OperationId.

## 52. Điều tra bất thường theo source IP: lưu ý riêng tư

App telemetry có thể có client location/IP fields theo cách instrument/configure. Tuy nhiên Application Insights có các cơ chế bảo vệ/ẩn IP và nhiều dữ liệu địa lý chỉ là ước lượng.

**Không mặc định truy vấn ClientIP để lập danh sách người dùng**. Khi điều tra bảo mật cần:

- Quyền truy cập telemetry nhạy cảm hợp lệ.
- Data minimization và retention rõ.
- Không xuất raw IP, email, bearer token hoặc full URL query string ra ticket công cộng.
- Nhận diện việc proxy/CDN/NAT làm IP được quan sát khác IP thực.
- Đánh giá application/edge logs trước khi kết luận user thật hoặc tấn công.

KQL hỗ trợ điều tra sự kiện, nhưng **không thay SIEM/detection/forensics process** hoặc phê duyệt xử lý dữ liệu cá nhân.

## 53. Tối ưu KQL: lọc sớm, lấy ít cột, tránh scan rộng

Một query kém hiệu quả:

~~~kusto
// Chỉ minh họa anti-pattern, không nên chạy trên workspace lớn:
AppTraces
| where Message contains "timeout"
| order by TimeGenerated desc
~~~

Truy vấn có định hướng:

~~~kusto
AppTraces
| where TimeGenerated >= ago(30m)
| where AppRoleName == "checkout-api"
| where Message has "timeout"
| project TimeGenerated, OperationId, AppRoleName, Message
| top 50 by TimeGenerated desc
~~~

### Ưu tiên

1. **TimeGenerated** và time picker hợp lý.
2. Filter **_ResourceId/AppRoleName/Namespace/Computer** trước.
3. Chỉ lấy cột cần dùng.
4. **summarize** hoặc **top N** thay trả toàn bộ raw records.
5. Dùng **has** khi phù hợp thay contains hoặc regex.
6. Giới hạn các phía của **join/union** riêng rẽ.
7. Tránh **search \*** trên toàn bộ workspace theo mặc định.
8. Dùng dynamic parsing **sau** bước lọc.
9. Đánh giá execution stats khi có và kiểm chứng kết quả.

### Anti-pattern join rất lớn

Nếu bạn join AppRequests 30 ngày với toàn bộ AppTraces 30 ngày qua OperationId, query có thể quét rất nhiều dữ liệu, tiêu thụ memory và nhân kết quả. Khi điều tra incident 30 phút, dùng **30 phút + resource scope** trước.

## 54. KQL và chi phí Log Analytics

Chi phí tổng thể quan sát hệ thống có thể gồm:

- Ingestion volume theo bảng/data plan và pricing hiện hành.
- Retention và archive/restore hoặc extended retention.
- Query/scanning/analytics charges tùy workspace/table plan/tính năng.
- Scheduled query alert rule execution theo pricing.
- Workbooks và các integrations liên quan.
- Data export, cross-region transfer, automation.

### Các cơ chế giảm chi phí tốt

- Instrument đúng trường cần thiết, giảm verbose logs không có giá trị.
- Thiết kế sampling phù hợp SLO/security requirements.
- Dùng **Data Collection Rules/ingestion transforms** khi phù hợp và có review.
- Chọn retention/table plan theo truy vấn cần thiết.
- Tối ưu KQL thay vì chỉ tăng limit/time range.
- Đánh giá trade-off giữa giảm log ingestion và mất bằng chứng điều tra.

**Không áp giá USD/GB hoặc tính năng của table plan như một quy tắc cố định**: Azure Monitor pricing, plan capabilities và supported KQL operators thay đổi theo dịch vụ/region/thời điểm.

## 55. Table plans và những giới hạn truy vấn

Log Analytics có các **table plans** như Analytics, Basic và Auxiliary tùy thời điểm/khu vực/tính năng. Một số loại có **khả năng truy vấn, retention, access hoặc alerting khác nhau**.

Trước khi viết một query dùng nhiều bảng:

1. Xác định plan của từng bảng trong workspace.
2. Kiểm tra **join/union/cross-table search** có được hỗ trợ trong trải nghiệm đó không.
3. Kiểm tra retention/query time range, ingestion latency và permission.
4. Kiểm tra scheduled query alert có hỗ trợ bảng/plan đó không.
5. Tránh chuyển plan chỉ để chạy một query trước khi phân tích cost/coverage.

Một query đúng cú pháp trong **Azure Data Explorer** không nhất thiết chạy giống hệt trong Log Analytics ở mọi table plan.

## 56. Retention, archive và historical incident

Nếu cần điều tra sự cố cách đây 90 ngày mà bảng chỉ giữ interactive data ngắn hơn:

- Query không có dòng trong time window có thể do **retention**.
- Dữ liệu có thể đã nằm trong long-term retention/archive theo policy và cần quy trình search/restore khác.
- Có thể cần dùng lưu trữ log ngoài/backup/audit records được phép.
- Không tăng retention toàn workspace ngay khi chưa ước lượng chi phí và chính sách dữ liệu.

### KQL không tái tạo dữ liệu đã mất

Nếu một collector bị tắt 12 giờ hoặc sampling loại bỏ records, không có cú pháp KQL nào có thể khôi phục chính xác raw records chưa từng ingest. Ghi rõ **coverage gap** trong incident report thay vì tự điền dữ liệu.

## 57. Dùng KQL làm cơ sở cho Scheduled Query Alerts

Một alert tốt phải có **đối tượng, cửa sổ thời gian, điều kiện kích hoạt, ngưỡng tối thiểu và owner/on-call**. Ví dụ tính lỗi của checkout API trong 10 phút:

~~~kusto
AppRequests
| where TimeGenerated >= ago(10m)
| where AppRoleName == "checkout-api"
| summarize
    Total=count(),
    Failed=countif(Success == false)
| extend FailurePct=iff(
    Total == 0,
    0.0,
    100.0 * todouble(Failed) / todouble(Total)
)
| where Total >= 100 and FailurePct > 5.0
| project Total, Failed, FailurePct
~~~

### Đây chỉ là phần KQL

Scheduled query alert còn cần cấu hình **frequency, evaluation period, threshold/condition, action group, scope, severity, managed identity và dimensions** theo Azure Monitor alert capability. Không sao chép nguyên câu vào production rồi giả định alert đã được tạo.

### Tránh bẫy khi ít traffic

1 lỗi trên 2 requests là 50% nhưng có thể không đủ tín hiệu để đánh thức on-call. **Total >= 100** là ngưỡng minh họa; chọn theo SLO, workload, critical endpoints và thời gian quan sát. Với thanh toán quan trọng, một lỗi bảo mật nghiêm trọng vẫn cần alert dù traffic thấp.

### Tránh dùng một alert duy nhất

Tách **high error rate, low availability, dependency latency, ingestion silence, Pod failures và TLS errors** khi cần. Một query chỉ nhìn AppRequests không thể phát hiện ingestion pipeline hỏng mà application vẫn chạy.

## 58. KQL alert về không có telemetry: bài toán khó

Nếu hệ thống cần tối thiểu một request trong mỗi khoảng thời gian, có thể dùng dạng:

~~~kusto
AppRequests
| where TimeGenerated >= ago(10m)
| where AppRoleName == "checkout-api"
| summarize ObservedRequests=count()
| where ObservedRequests == 0
~~~

### Rất dễ báo động giả

- Ứng dụng ban đêm có thể không có traffic.
- Agent/SDK bị tắt hoặc ingestion chậm.
- AppRoleName đổi sau release.
- Workspace scope bị thay, tables/tracing bị sampling/drop.

Với mục tiêu **availability**, nên kết hợp **synthetic tests/availability probes** độc lập và health metrics. Query có không có logs **không đủ** để phân biệt dịch vụ tắt với pipeline quan sát bị lỗi.

## 59. Workbooks, dashboards và SLO

KQL có thể làm nền cho **Azure Monitor Workbooks** hoặc các dashboard được hỗ trợ:

~~~text
Service health workbook
   |
   +-- Requests/5 min
   +-- Failure rate (technical)
   +-- p95 latency
   +-- Top dependency targets/errors
   +-- AppExceptions by ProblemId
   +-- AKS Pod status/log categories
   +-- AzureActivity changes
   +-- Telemetry ingestion freshness
~~~

### Dashboard và SLO khác nhau

**Dashboard** cung cấp hình ảnh; **SLO** là cam kết mục tiêu đo được, ví dụ 99,9% requests của một tập API nhất định có phản hồi thành công trong cửa sổ được quy định.

Trước khi định nghĩa SLO trong KQL:

- Xác định requests nào nằm trong mẫu số.
- Quy định HTTP 4xx nào là lỗi client được loại khỏi SLI.
- Xác định sampling, health probes và endpoint mix.
- Xác định cách phân vùng theo region/version.
- Đồng bộ time window và nguồn dữ liệu.

Không viết SLO bằng **Success==true** mà không hiểu SDK/response code semantics của ứng dụng.

## 60. Quản lý quyền đọc Logs và dữ liệu nhạy cảm

Logs có thể chứa tenant IDs, resource paths, exception messages, IP/network metadata hoặc thông tin người dùng. Một truy vấn KQL là **read-only** nhưng trả dữ liệu nhạy cảm cho người không được phép vẫn là vấn đề bảo mật.

### Nguyên tắc

1. Áp **Azure RBAC** theo workspace/resource/table và chế độ truy cập được hỗ trợ.
2. Tách dev/test/prod workspaces và query scopes khi cần.
3. Không cấp workspace-wide logs access chỉ vì một nhóm muốn xem health của một app.
4. Redact secrets, tokens, passwords, connection strings, payment/PII ngay ở instrumentation.
5. Hạn chế export query results, CSV, workbook sharing và screenshots.
6. Quản lý retention, audit và data residency.
7. Không dùng KQL filter đơn thuần làm cơ chế cô lập dữ liệu giữa tenants.

### Tại sao filter không phải authorization?

Nếu người dùng có quyền toàn bộ workspace, họ có thể bỏ **where AppRoleName == "service-A"**. Phạm vi quyền phải được enforce bởi **nền tảng**, không phải bằng mẫu câu truy vấn mà người dùng tình nguyện giữ lại.

## 61. KQL query parameters và an toàn truy vấn

Khi dùng query trong API/automation thay vì copy-paste Portal:

- Ưu tiên **query parameters** hoặc cách bind được SDK/API hỗ trợ.
- Validate resource scope, start/end times và maximum lookback.
- Không nối trực tiếp input người dùng chưa kiểm tra vào KQL expression.
- Giới hạn query timeout/rows/size theo SLA/cost.
- Sử dụng identity riêng, quyền chỉ đọc phù hợp.
- Tránh log nguyên query nếu nó chứa IDs nhạy cảm.

### Ví dụ let cố định để học

~~~kusto
let WindowStart = ago(1h);
let Role = "checkout-api";
AppRequests
| where TimeGenerated >= WindowStart
| where AppRoleName == Role
| summarize Events=count()
~~~

**let chỉ là khai báo trong câu KQL**, không tự là biện pháp chống query injection khi bạn ghép input vào chuỗi ở Java. Application code phải kiểm soát cách lập query/parameters theo Azure Monitor Query SDK và service APIs tương ứng.

## 62. Lab A: học KQL hoàn toàn bằng datatable

**Mục tiêu:** chạy KQL trên dữ liệu tổng hợp ngay trong Logs/Kusto environment hỗ trợ, **không cần bảng Azure thật**. Điều này thuận tiện khi workspace trống hoặc người học chưa được cấp quyền production.

### Dữ liệu giả

~~~kusto
let SampleRequests = datatable(
    TimeGenerated:datetime,
    AppRoleName:string,
    Name:string,
    Success:bool,
    DurationMs:real,
    ResultCode:string,
    OperationId:string
)
[
    datetime(2026-11-20T03:00:00Z), "checkout-api", "POST /checkout", true, 120.0, "200", "op1",
    datetime(2026-11-20T03:01:00Z), "checkout-api", "POST /checkout", true, 145.0, "200", "op2",
    datetime(2026-11-20T03:02:00Z), "checkout-api", "POST /checkout", false, 1800.0, "500", "op3",
    datetime(2026-11-20T03:03:00Z), "checkout-api", "POST /checkout", false, 2200.0, "503", "op4",
    datetime(2026-11-20T03:04:00Z), "checkout-api", "GET /health", true, 15.0, "200", "op5",
    datetime(2026-11-20T03:05:00Z), "catalog-api", "GET /items", true, 65.0, "200", "op6",
    datetime(2026-11-20T03:06:00Z), "catalog-api", "GET /items", true, 70.0, "200", "op7",
    datetime(2026-11-20T03:07:00Z), "catalog-api", "GET /items", false, 540.0, "500", "op8",
    datetime(2026-11-20T03:08:00Z), "checkout-api", "POST /checkout", true, 140.0, "200", "op9",
    datetime(2026-11-20T03:09:00Z), "checkout-api", "POST /checkout", false, 1900.0, "500", "op10"
];
SampleRequests
| summarize
    Total=count(),
    Failed=countif(Success == false),
    P95Ms=percentile(DurationMs, 95)
    by AppRoleName
| extend FailureRate=round(
    100.0 * todouble(Failed) / todouble(Total), 1)
| order by FailureRate desc
~~~

### Bài tập

1. Chạy nguyên khối KQL (datatable và truy vấn trong cùng lượt).
2. Kiểm tra **checkout-api có 7 requests, 3 failed**; catalog-api có **3 requests, 1 failed**.
3. Thêm **where Name != "GET /health"** trước summarize để xem health probes ảnh hưởng ra sao.
4. Thay summarize bằng **by bin(TimeGenerated, 5m), AppRoleName** và xem bucket.
5. Thêm **top 1 by P95Ms desc** để xem service chậm nhất theo dữ liệu giả.
6. Thử **project AppRoleName, Total, Failed, FailureRate** để chỉ xuất các cột cần thiết.

### Cần hiểu

Con số p95 của 3–7 bản ghi chỉ có giá trị minh họa. Không đưa kết quả synthetic này vào dashboard SLO production. Nếu KQL editor không cho chạy datatable theo bảng thật, kiểm tra syntax và workspace query experience; datatable là tabular constructor, không yêu cầu ingest records.

## 63. Lab B: điều tra Application Insights trong workspace lab

**Mục tiêu:** phát hiện một lỗi ứng dụng bằng AppRequests, AppDependencies, AppExceptions và AppTraces.

### Chuẩn bị

- Workspace-based Application Insights **lab** đã có synthetic telemetry.
- Quyền truy vấn được cấp, không lấy dữ liệu production khi chưa được phép.
- AppRoleName/service ID được xác minh từ schema.
- Có một time window sự cố do người học/giảng viên cung cấp.

### Quy trình

1. Mở Logs đúng workspace/scope và chọn 1–2 giờ gần incident.
2. Dùng **AppRequests | take 5** sau time filter để xem schema.
3. Tổng hợp Requests, Failed, p95 theo 5 phút.
4. Tìm endpoint có nhiều failed requests nhất và xem sample size.
5. Tìm dependency targets có failure/latency tăng.
6. Xem nhóm exceptions theo **ProblemId**.
7. Chọn một **OperationId** của request lỗi.
8. Dùng union hoặc join có time filter để xem request/dependency/trace/exception.
9. Ghi **hypothesis + supporting evidence + missing telemetry**.
10. Không chạy sửa resource/database từ KQL; nếu cần khắc phục thì chuyển runbook được phê duyệt.

### Nghiệm thu

| Tiêu chí | PASS khi |
|---|---|
| Scope | Đúng Application Insights và workspace |
| Time | UTC window đúng sự cố |
| Request error | Có số requests, failed, rate, p95 và mẫu số |
| Dependency | Có Target/Type/Success hoặc ghi rõ thiếu instrumentation |
| Correlation | OperationId được đối chiếu và biết giới hạn |
| Security | Không xuất token, PII, raw request bodies |
| Kết luận | Có phân biệt observed facts và giả thuyết |

## 64. Lab C: điều tra AKS và Azure Activity

**Mục tiêu:** biết ứng dụng lỗi do container, cluster hay một thay đổi resource gần thời điểm đó, không dùng quyền sửa production.

### Chuẩn bị

- AKS cluster lab đã bật Container Insights/data collection phù hợp.
- ContainerLogV2/KubePodInventory hoặc bảng tương đương có telemetry.
- AzureActivity được ingest/khả dụng theo scope.
- Người học có logs read permissions.

### Các bước

1. Xác định namespace và khoảng thời gian.
2. Dùng **ContainerLogV2** tìm Java error/timeout/OOM records.
3. Nhóm theo **PodName/ContainerName** để xem Pod nào có nhiều log lỗi.
4. Dùng **KubePodInventory** lấy trạng thái mới nhất.
5. Nếu có KubeNodeInventory/InsightsMetrics, xem node/metric bất thường.
6. Dùng **AzureActivity** tìm write operations cùng khung giờ.
7. Lập timeline theo UTC, so sánh app errors, Pod states và change events.
8. Phân biệt **correlation** với **causation**.
9. Nếu thiếu collection, ghi rõ bảng không hiện và kiểm tra agent/DCR/diagnostic settings theo quyền; không tự mở rộng quyền hoặc thay settings.

### Câu hỏi

Nếu container logs cho thấy OutOfMemoryError nhưng KubePodInventory chưa có restart evidence, có thể kết luận AKS đã OOM-kill Pod không?

**Không.** JVM **OutOfMemoryError** có thể xuất hiện bên trong process khi container vẫn chưa bị OS/kernel OOM-kill; cần Pod status/container termination reason, memory limits, metrics và timeline để xác định.

## 65. Lab D: làm việc với dữ liệu thiếu và schema khác

**Mục tiêu:** tránh đoán sai vì query chạy trống hoặc field không tồn tại.

### Tình huống 1

Bạn dán query **AppRequests** vào một trải nghiệm Application Insights legacy chỉ có **requests**. Hãy:

1. Xem schema browser.
2. Đổi bảng thành **requests**.
3. Chuyển tên **TimeGenerated → timestamp**, **AppRoleName → cloud_RoleName**, **OperationId → operation_Id**, v.v.
4. Xác định kiểu của **duration** (timespan) trước khi so sánh với milliseconds.
5. Không sao chép **DurationMs > 1000** thành **duration > 1000**.

### Tình huống 2

Một workspace có **ContainerLog** nhưng không có **ContainerLogV2**. Hãy:

1. Đọc schema thật.
2. Tìm cột text/ContainerID/namespace qua bảng đúng.
3. Kiểm tra cấu hình collection/Container Insights version.
4. Không tạo query trộn các trường không tồn tại.

### Tình huống 3

AzureDiagnostics không có records cho Azure SQL nhưng service vẫn có diagnostics:

1. Kiểm tra resource-specific tables.
2. Xem diagnostic categories và destination workspace.
3. Kiểm tra retention, data collection gaps và RBAC.
4. Không kết luận SQL không phát sinh events.

## 66. Case study 1: checkout latency tăng sau triển khai

**Bối cảnh:** API checkout Spring Boot chạy trên AKS, đọc Azure SQL Database, gửi Service Bus messages và nhận traffic qua Application Gateway.

~~~text
Browser
   |
   v
Application Gateway
   |
   v
AKS ingress -> checkout-api (Java)
                  |
                  +--> Azure SQL Database
                  |
                  +--> Service Bus
~~~

Vào **03:20 UTC**, bản **v2** bắt đầu rollout; sau đó p95 tăng từ dưới 300 ms lên hơn 1.500 ms và 5xx tăng. On-call cần tìm nguyên nhân:

### Bước 1: định lượng ảnh hưởng

~~~kusto
AppRequests
| where TimeGenerated >= datetime(2026-11-20T03:00:00Z)
  and TimeGenerated < datetime(2026-11-20T04:00:00Z)
| where AppRoleName == "checkout-api"
| summarize
    Requests=count(), Failed=countif(Success == false),
    P95Ms=percentile(DurationMs, 95)
    by bin(TimeGenerated, 5m)
| order by TimeGenerated asc
~~~

### Bước 2: phân biệt dependency

~~~kusto
AppDependencies
| where TimeGenerated >= datetime(2026-11-20T03:00:00Z)
  and TimeGenerated < datetime(2026-11-20T04:00:00Z)
| where AppRoleName == "checkout-api"
| summarize
    Calls=count(), Failed=countif(Success == false),
    P95Ms=percentile(DurationMs, 95)
    by Type, Target
| order by Failed desc
~~~

### Bước 3: kiểm tra hạ tầng

- KubePodInventory: Pod mới Pending/Failed ở node pool nào?
- ContainerLogV2: connection pool timeout, SQL authentication hoặc OOM?
- AzureActivity: có cập nhật storage/SQL/AKS/network resource không?
- AKS deployment/audit: bản v2 có rollout đúng giờ/đúng image digest không?
- Azure SQL Metrics: CPU/DTU/vCore/connections có tăng không?

### Hai giả thuyết cần phân biệt

**Giả thuyết A:** bản v2 tăng JDBC pool size, scale 30 Pods tạo connection storm tới SQL.

**Giả thuyết B:** network/identity change làm SQL requests timeout, pod retries gây tải sau đó.

KQL chỉ thấy **traces/timeline tương ứng**; cần xác minh code/config diff, connection pool metrics, SQL diagnostics và sự kiện triển khai. Không rollback hoặc scale database chỉ dựa vào một chart.

## 67. Case study 2: AKS báo lỗi nhưng ứng dụng vẫn trả 200

**Bối cảnh:** một dịch vụ Java có liveness endpoint luôn trả 200 nhưng các background consumers đọc Service Bus ngừng xử lý. Dashboard HTTP Success cao, nhưng queue backlog tăng.

### Vì sao query request chưa đủ?

~~~text
GET /health -> HTTP 200
                    |
                    v
             AppRequests.Success = true

Service Bus consumer loop stopped
                    |
                    v
             Business work not progressing
~~~

### KQL và dữ liệu cần bổ sung

1. **AppTraces** theo sự kiện consumer started/stopped và errors.
2. **AppExceptions** của message-processing loop.
3. **AppDependencies** Service Bus failures nếu được instrument.
4. **ContainerLogV2** cho crashes/restarts/timeouts.
5. **Azure Monitor Metrics** của Service Bus queue backlog/active messages theo dịch vụ.
6. **KubePodInventory** để xem Pod status, không dựa vào health HTTP đơn thuần.

### Thiết kế telemetry tốt hơn

Đo **last_message_processed_at**, **messages_processed_total**, **processing_failure_count** và **queue lag** bằng metrics/logs đã chuẩn hóa, sau đó alert khi processing không tiến triển dù Pods đang Ready.

**Một liveness probe thành công không đồng nghĩa toàn bộ nghiệp vụ chạy khỏe**. KQL chỉ tốt bằng telemetry đã được instrument và gửi vào hệ thống.

## 68. Runbook điều tra sự cố bằng KQL trong 15 bước

Một quy trình có thể lặp lại giúp tránh truy vấn không giới hạn hoặc suy đoán quá sớm.

### Pha A — Định danh và đặt phạm vi

1. **Xác nhận incident:** triệu chứng, người dùng bị ảnh hưởng, SLO, severity và mốc thời gian do on-call cung cấp.
2. **Chuẩn hóa UTC:** quy đổi thời điểm báo lỗi trong timezone địa phương sang UTC; ghi rõ điểm đầu/cuối.
3. **Chọn subscription/workspace/resource:** Application Insights, Log Analytics, AKS, VM, diagnostic settings.
4. **Kiểm tra telemetry availability:** bảng có dữ liệu, schema, retention, sampling, ingestion lag và RBAC.

### Pha B — Định lượng biểu hiện

5. **Request overview:** count, failures, p95/p99 theo 1–5 phút và AppRoleName.
6. **Khoanh vùng routes/releases:** Name, ResultCode, app version hoặc role instance nếu có.
7. **Dependency overview:** Type, Target, failures và duration.
8. **Exceptions/traces:** ProblemId, error category và một số OperationIds tiêu biểu.

### Pha C — Kiểm tra hạ tầng

9. **AKS:** ContainerLogV2, KubePodInventory, nodes/metrics theo bảng thực.
10. **VM/agents:** Heartbeat, Perf hoặc Azure Metrics khi được thu thập.
11. **Control plane:** AzureActivity và deployment events/IaC logs.
12. **Resource diagnostics:** AzureDiagnostics hoặc service-specific tables cho SQL, Key Vault, Application Gateway, Service Bus, Storage, v.v.

### Pha D — Xác minh và kết luận

13. **Tạo timeline:** observed events và time windows, ghi rõ gaps.
14. **Kiểm chứng giả thuyết:** kết hợp telemetry, release/config diff, metrics dịch vụ và reproduction được phê duyệt.
15. **Handoff:** viết incident summary, mitigation/rollback do owner phê duyệt, follow-up instrumentation/alerts/retention.

### Mẫu ghi nhận bằng chứng

| Trường | Ví dụ |
|---|---|
| Incident | checkout-incident-001 |
| First observed UTC | 2026-11-20T03:20Z |
| Scope | checkout-api / production workspace |
| User impact | checkout failures tăng; số liệu đo riêng |
| Request evidence | FailurePct và p95 theo 5m |
| Dependency evidence | SQL target timeout tăng |
| Infrastructure evidence | Pod/connection metrics và deployment activity |
| Correlation | OperationId/traceId của yêu cầu mẫu |
| Missing data | Chưa có Service Bus consumer lag metric |
| Hypothesis | Pool pressure sau rollout, chưa chứng minh |
| Action owner | SRE / service owner |
| Validation | Canary metrics và customer-facing health |

**Dấu thời gian và incident ID chỉ là ví dụ**, không phải sự cố thật. Báo cáo phân biệt **quan sát đã có bằng chứng**, **giả thuyết** và **hành động**.

## 69. Những sai lầm KQL thường gặp

| Sai lầm | Hậu quả | Cách làm đúng |
|---|---|---|
| Không chọn đúng workspace | Tưởng không có dữ liệu | Xác minh Application Insights/Log Analytics linkage |
| Không lọc thời gian | Query chậm, tốn scan | Where TimeGenerated từ đầu |
| Bỏ qua timezone | Đọc sai thời điểm incident | UTC nhất quán và ghi rõ timezone |
| AppRequests dùng cột của requests | Query lỗi hoặc logic sai | Đối chiếu schema hiện hành |
| Dùng count() thay tổng đã tính sampling | Ước lượng traffic sai | Xem ItemCount/sampling |
| Group theo full URL/PII | Cardinality và dữ liệu nhạy cảm | Group theo Name/route đã chuẩn hóa |
| Dùng avg thay p95 | Bỏ sót tail latency | Dùng percentile với đủ mẫu |
| Count 1 lỗi/2 requests rồi báo 50% khủng hoảng | False alarm | Kết hợp tỷ lệ, tổng volume và business impact |
| Join không giới hạn hai bảng lớn | Nhân số dòng, chi phí cao | Filter/projection/rollup trước join |
| Coi OperationId là row ID duy nhất | Join sai, đếm trùng | Xem Id/ParentId/span context |
| Union cả bảng không cần | Tốn chi phí, nhiễu | Chọn sources cần thiết |
| Regex mọi log | Query đắt và dễ sai | Instrument structured fields |
| Thay missing Duration bằng 0 | Báo p95 thấp giả | Giữ null, đo data coverage |
| Coi AppDependencies thiếu là không gọi dependency | Bỏ sót nguyên nhân | Kiểm tra instrumentation |
| Coi ContainerLogV2 ERROR là Pod restart | Kết luận sai | Xem Pod termination/state/events |
| Coi AzureActivity là mọi data-plane activity | Bỏ sót SQL/Blob actions | Dùng resource diagnostics/audit |
| Coi AzureDiagnostics là bảng mặc định mọi dịch vụ | Không tìm thấy logs | Kiểm tra resource-specific tables |
| Coi AppRequests 200 là nghiệp vụ khỏe | Bỏ sót backlog/process failures | Business metrics, queues, background workers |
| Coi TimeGenerated là ingestion time | Sai timeline | Phân biệt event/ingestion times |
| Coi no rows là hệ thống không có lỗi | Thiếu telemetry/permission/retention | Kiểm tra collection và data freshness |
| Truy vấn Logs như Azure Data Explorer control commands | Lệnh không được hỗ trợ | Dùng operators/schemas của Azure Monitor Logs |
| Ghi full exception/URLs vào ticket | Rò rỉ PII/secrets | Redaction và access controls |
| Biến query filter thành “authorization” | Người khác có thể bỏ where | RBAC/table/resource access thật |
| Coi biểu đồ tương quan là root cause | Mitigation sai | Kiểm chứng bằng nhiều nguồn độc lập |
| Không lưu phiên bản truy vấn/runbook | Khó tái hiện điều tra | Version hóa KQL không chứa secrets |

### Trọng tâm khi học KQL

Kỹ năng quan trọng không chỉ là nhớ cú pháp. Đó là **đặt câu hỏi điều tra có thể kiểm chứng**, chọn dữ liệu đúng, hiểu giới hạn telemetry và biết khi nào **không thể kết luận**.

## 70. Checklist trước khi dùng query trong production

| Nhóm | Kiểm tra |
|---|---|
| Scope | Tenant, subscription, workspace, resource đúng |
| Bảng | Tồn tại, schema/cột đúng, legacy/workspace-based được phân biệt |
| Timezone | Mốc UTC và time picker thống nhất |
| Time filter | Cửa sổ có giới hạn, hợp lý với sự cố |
| Resource filter | AppRoleName/_ResourceId/namespace khi có |
| Data type | String/datetime/duration/dynamic conversion chính xác |
| Telemetry coverage | Instrumentation, sampling, drop/ingestion lag đã kiểm tra |
| Counts | Distinguish rows, ItemCount estimates và distinct operations |
| Latency | P95/p99 đơn vị ms, sample size đủ |
| Join | Key, duplicate/rollup và time filters ở cả hai phía |
| Dependency | Type/Target/status theo đúng backend |
| AKS | Container logs vs Pod inventory/events không bị nhầm |
| VM | Heartbeat khác availability và service health |
| Diagnostics | AzureDiagnostics hay resource-specific table đúng |
| Activity | Control-plane changes, không suy rộng sang data plane |
| Cost | Tránh full scan/search, join/union quá lớn |
| Table plan | KQL operators/retention/query limitations được hỗ trợ |
| Privacy | PII/token/connection string không ra query result |
| Authorization | Reader role theo workspace/resource/table, least privilege |
| Alerts | Volume threshold, frequency, false-positive checks và action group |
| SLO | Mẫu số, endpoint mix, sampling và success definition rõ |
| Dashboard | Không xem missing telemetry là zero incidents |
| Correlation | RequestId/OperationId/trace propagation được kiểm chứng |
| Validation | Dùng synthetic/test incidents trước khi cảnh báo prod |
| Handoff | Facts, hypotheses, gaps, UTC timeline và action owner |
| Reproducibility | Truy vấn có version, parameters, schema assumptions |

## 71. Câu hỏi tự kiểm tra

1. KQL là gì, và vì sao Azure Monitor Logs khác Azure Monitor Metrics?
2. Log Analytics workspace đóng vai trò gì trong Azure monitoring?
3. Application Insights workspace-based thường dùng bảng nào cho requests?
4. Bảng **requests** trong legacy Application Insights khác **AppRequests** ở những cột nào?
5. Khi AppRequests không tồn tại, bước kiểm tra đầu tiên là gì?
6. Vì sao nên giới hạn TimeGenerated trước khi xử lý text/JSON?
7. UTC ảnh hưởng thế nào khi sự cố được báo bằng giờ Việt Nam?
8. **take 20** và **top 20 by TimeGenerated desc** khác nhau thế nào?
9. Phân biệt **has**, **contains** và exact match.
10. **project** khác **extend** thế nào?
11. **summarize count() by bin(TimeGenerated, 5m)** cho kết quả gì?
12. Vì sao một tỉ lệ lỗi 50% trên 2 requests chưa đủ để đánh giá toàn hệ thống?
13. **AppRequests.Success** có phải luôn là business outcome không?
14. **ResultCode** của SQL dependency có nên được xem như HTTP status không?
15. Average latency và p95/p99 khác nhau ở ý nghĩa vận hành gì?
16. Sampling làm **count()** và **sum(ItemCount)** khác nhau thế nào?
17. Vì sao p95 sampled requests có thể sai lệch nếu không xét sampling?
18. Làm sao tìm top 10 endpoints lỗi nhiều nhất và loại health probe?
19. **AppDependencies.Target** có bảo đảm là unique Azure resource ID không?
20. Khi nào dùng **AppExceptions** thay vì tìm từ ERROR trong AppTraces?
21. Dynamic Properties và JSON string khác nhau thế nào?
22. Nếu todouble() không chuyển được dữ liệu, KQL trả gì và cần xử lý ra sao?
23. Regex log thiếu structured logging có những nhược điểm nào?
24. OperationId dùng để làm gì, có phải khóa duy nhất cho một request row không?
25. Vì sao join AppRequests với AppDependencies có thể nhân số requests?
26. **leftouter**, **leftanti** và **leftsemi** khác nhau thế nào?
27. **arg_max(TimeGenerated, PodStatus)** trả giá trị gì?
28. **dcount()** có đếm chính xác từng user không?
29. Vì sao so sánh trước/sau deployment chưa đủ chứng minh causality?
30. Làm sao so sánh failure rate giữa application versions nếu version là custom property?
31. **make-series** có lợi ích gì, và default=0 có rủi ro nào?
32. Event time và ingestion time khác nhau ra sao?
33. **ContainerLogV2** thường chứa telemetry gì?
34. Một Java OutOfMemoryError có tự chứng minh Kubernetes OOMKilled không?
35. KubePodInventory snapshots khác Kubernetes events ở điểm nào?
36. Heartbeat của VM có chứng minh REST API luôn khỏe không?
37. Perf và InsightsMetrics có cùng cột/đơn vị metric cho mọi OS không?
38. AzureMetrics xuất hiện trong Log Analytics khi nào?
39. AzureActivity chủ yếu phản ánh data plane hay management plane?
40. Resource-specific tables và AzureDiagnostics khác nhau như thế nào?
41. _ResourceId có thể dùng để phân biệt prod/staging không, và có thay RBAC không?
42. Vì sao join các events chỉ vì cùng một bucket 5 phút chưa chứng minh nguyên nhân?
43. Query tối ưu cần làm gì trước khi chạy join hai bảng lớn?
44. Khi nào log retention/table plan khiến một query không thể trả dữ liệu quá khứ?
45. Một scheduled query alert cần những thành phần ngoài câu KQL?
46. Không có AppRequests trong 10 phút có chứng minh ứng dụng down không?
47. Tại sao SLO không chỉ là một biểu đồ “Success Rate” chưa có định nghĩa?
48. Trong case study checkout, cần ít nhất ba nguồn dữ liệu nào để kiểm chứng lỗi?
49. Trong case study Service Bus, vì sao HTTP 200 không đủ cho service health?
50. Làm sao viết incident report phân biệt **observed facts**, **hypothesis** và **unknowns**?

## Tài liệu tham khảo

- Microsoft Learn — *Azure Monitor overview*: https://learn.microsoft.com/azure/azure-monitor/overview
- Microsoft Learn — *Log Analytics workspace overview*: https://learn.microsoft.com/azure/azure-monitor/logs/log-analytics-workspace-overview
- Microsoft Learn — *Log Analytics tutorial*: https://learn.microsoft.com/azure/azure-monitor/logs/log-analytics-tutorial
- Microsoft Learn — *Kusto Query Language overview*: https://learn.microsoft.com/kusto/query/?view=microsoft-fabric
- Microsoft Learn — *KQL tutorial*: https://learn.microsoft.com/kusto/query/tutorials/learn-common-operators?view=microsoft-fabric
- Microsoft Learn — *where operator*: https://learn.microsoft.com/kusto/query/where-operator?view=microsoft-fabric
- Microsoft Learn — *summarize operator*: https://learn.microsoft.com/kusto/query/summarize-operator?view=microsoft-fabric
- Microsoft Learn — *join operator*: https://learn.microsoft.com/kusto/query/join-operator?view=microsoft-fabric
- Microsoft Learn — *make-series operator*: https://learn.microsoft.com/kusto/query/make-series-operator?view=microsoft-fabric
- Microsoft Learn — *parse_json function*: https://learn.microsoft.com/kusto/query/parse-json-function?view=microsoft-fabric
- Microsoft Learn — *Azure Monitor Logs table reference*: https://learn.microsoft.com/azure/azure-monitor/reference/tables/tables-category
- Microsoft Learn — *AppRequests table*: https://learn.microsoft.com/azure/azure-monitor/reference/tables/apprequests
- Microsoft Learn — *AppDependencies table*: https://learn.microsoft.com/azure/azure-monitor/reference/tables/appdependencies
- Microsoft Learn — *AppExceptions table*: https://learn.microsoft.com/azure/azure-monitor/reference/tables/appexceptions
- Microsoft Learn — *AppTraces table*: https://learn.microsoft.com/azure/azure-monitor/reference/tables/apptraces
- Microsoft Learn — *ContainerLogV2 table*: https://learn.microsoft.com/azure/azure-monitor/reference/tables/containerlogv2
- Microsoft Learn — *KubePodInventory table*: https://learn.microsoft.com/azure/azure-monitor/reference/tables/kubepodinventory
- Microsoft Learn — *AzureActivity table*: https://learn.microsoft.com/azure/azure-monitor/reference/tables/azureactivity
- Microsoft Learn — *AzureDiagnostics table*: https://learn.microsoft.com/azure/azure-monitor/reference/tables/azurediagnostics
- Microsoft Learn — *Azure Monitor Logs and metrics*: https://learn.microsoft.com/azure/azure-monitor/data-platform
- Microsoft Learn — *Application Insights telemetry model*: https://learn.microsoft.com/azure/azure-monitor/app/data-model-complete
- Microsoft Learn — *Application Insights sampling*: https://learn.microsoft.com/azure/azure-monitor/app/sampling-classic-api
- Microsoft Learn — *Azure Monitor Container Insights*: https://learn.microsoft.com/azure/azure-monitor/containers/container-insights-overview
- Microsoft Learn — *Azure Monitor diagnostic settings*: https://learn.microsoft.com/azure/azure-monitor/essentials/diagnostic-settings
- Microsoft Learn — *Azure Monitor log alerts*: https://learn.microsoft.com/azure/azure-monitor/alerts/alerts-create-log-alert-rule
- Microsoft Learn — *Azure Monitor Logs permissions*: https://learn.microsoft.com/azure/azure-monitor/logs/manage-access
- Microsoft Learn — *Azure Monitor Logs table plans*: https://learn.microsoft.com/azure/azure-monitor/logs/data-platform-logs
- Microsoft Learn — *Azure Monitor Logs query optimization*: https://learn.microsoft.com/azure/azure-monitor/logs/query-optimization
- Microsoft Learn — *Azure Monitor pricing*: https://azure.microsoft.com/pricing/details/monitor/
- Azure Pricing Calculator: https://azure.microsoft.com/pricing/calculator/
