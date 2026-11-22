# Xây dựng runbook xử lý sự cố và hồ sơ yêu cầu hỗ trợ Azure

## 1. Mục tiêu: xử lý sự cố có thể lặp lại và phối hợp hiệu quả với Azure Support

Khi ứng dụng hoạt động trên Microsoft Azure gặp lỗi, tốc độ phục hồi không chỉ phụ thuộc vào kiến thức của một kỹ sư. Đội vận hành cần biết **phát hiện lỗi từ đâu, ai chịu trách nhiệm, bước chẩn đoán nào thực hiện trước, khi nào cần thay đổi hệ thống, bằng chứng nào phải giữ lại và lúc nào cần nhờ Microsoft hỗ trợ**. Một runbook rõ ràng giúp các ca trực khác nhau đưa ra quyết định nhất quán, giảm thao tác nguy hiểm trong lúc áp lực và rút ngắn thời gian khôi phục.

Bài học thuộc chương **Hiệu năng và vận hành** trong module `CLOUD_PROVIDERS_AZURE`. Các tình huống sử dụng kiến thức Azure từ subscription, resource group, Microsoft Entra ID và RBAC, đến VNet, compute, storage, database, Azure Monitor, bảo mật, kiểm soát quota và chi phí. Trọng tâm là **viết được một runbook khả thi và tạo được một hồ sơ yêu cầu hỗ trợ Azure (support request) đủ dữ kiện để đội hỗ trợ chẩn đoán**.

Sau bài học, bạn có thể:

1. Phân biệt incident, alert, vấn đề hiệu năng, lỗi thay đổi cấu hình, giới hạn dịch vụ và sự cố nền tảng Azure.
2. Xây dựng runbook có trigger, scope, quyền thao tác, thứ tự chẩn đoán, tiêu chí quyết định, rollback, kết quả mong đợi và kênh escalation.
3. Khai thác Azure Monitor, Application Insights, Log Analytics, Activity Log, Resource Health và Azure Service Health để khoanh vùng lỗi.
4. Phân loại hồ sơ hỗ trợ kỹ thuật, quota và billing; cung cấp impact, timestamp UTC, correlation ID, resource ID, các bước tái hiện và bằng chứng an toàn.
5. Kết hợp xử lý sự cố nội bộ với trao đổi Azure Support, theo dõi cập nhật và hoàn thành đánh giá sau sự cố.

**Phạm vi:** Hướng dẫn là mẫu triển khai vận hành; tên tài nguyên, cấu hình, ngưỡng và người chịu trách nhiệm trong ví dụ phải được điều chỉnh theo hệ thống thực tế. Quyền truy cập, phương án khôi phục và mức hỗ trợ Azure phụ thuộc subscription, sản phẩm và gói hỗ trợ của tổ chức.

## 2. Runbook là gì và khác tài liệu kiến trúc thế nào?

**Runbook** là hướng dẫn vận hành gồm các hành động có thứ tự và điều kiện rõ ràng để con người hoặc tự động hóa xử lý một tình huống cụ thể. Nó trả lời câu hỏi: “Khi nhận cảnh báo này, ca trực kiểm tra và hành động thế nào để đưa hệ thống trở lại mức phục vụ chấp nhận được?”.

Một tài liệu kiến trúc có thể mô tả API gọi database, queue và storage. Runbook phải nêu thêm:

- **Điểm kích hoạt:** metric, ngưỡng, symptom hoặc thông báo nào khiến quy trình bắt đầu?
- **Mức tác động:** giao dịch và người dùng nào bị ảnh hưởng, có vi phạm SLO hay không?
- **Bằng chứng:** kiểm tra metric, log, trace, deployment, Resource Health và Service Health ở đâu?
- **Quyết định:** khi nào rollback, scale, chuyển hướng lưu lượng, failover hoặc giữ nguyên để thu thêm chứng cứ?
- **Phân quyền:** ai được thao tác, ai duyệt và ai thông báo cho các bên liên quan?
- **Điều kiện kết thúc:** cần xác minh gì để tuyên bố đã phục hồi và chuyển sang hậu kiểm?

### 2.1. Runbook, playbook, checklist và post-incident review

| Loại tài liệu | Mục đích | Ví dụ |
| --- | --- | --- |
| **Runbook** | Các bước vận hành chi tiết cho một tình huống đã xác định | Xử lý HTTP 5xx tăng đột biến trên App Service |
| **Playbook** | Chiến lược phối hợp cho một nhóm tình huống rộng | Ứng phó mất vùng Azure hoặc dịch vụ dữ liệu ngừng hoạt động |
| **Checklist** | Nhắc những điều bắt buộc phải kiểm tra | Kiểm tra trước và sau rollback |
| **Dashboard** | Quan sát tín hiệu kỹ thuật và nghiệp vụ | Tỷ lệ lỗi, latency, CPU, dependency failures |
| **Post-incident review** | Phân tích tác động, nguyên nhân, bài học và hành động sau sự cố | Tại sao cảnh báo đến muộn và rollback mất 20 phút? |

Một runbook tốt liên kết đến dashboard, playbook, repository IaC, nơi lưu log và quy trình phê duyệt; không nên chép các thông số thay đổi thường xuyên vào nhiều nơi khiến tài liệu nhanh lỗi thời.

## 3. Chuẩn hóa cách phân loại và điều phối incident

**Alert** là tín hiệu cần đánh giá; không phải alert nào cũng là incident. **Incident** là sự kiện đã hoặc có nguy cơ làm suy giảm đáng kể dịch vụ theo mục tiêu vận hành. Một cảnh báo CPU cao ngắn hạn không nhất thiết là incident nếu hệ thống vẫn đáp ứng SLO; ngược lại, một lỗi thanh toán có thể nghiêm trọng ngay cả khi CPU bình thường.

### 3.1. Phân loại theo ảnh hưởng người dùng

Có thể dùng bảng **mức ưu tiên nội bộ minh họa** sau:

| Ưu tiên nội bộ | Ảnh hưởng ví dụ | Phản ứng dự kiến |
| --- | --- | --- |
| **P0 / Critical** | Dịch vụ trọng yếu ngừng phục vụ diện rộng, hoặc rủi ro mất dữ liệu nghiêm trọng | Kích hoạt điều phối sự cố ngay; ưu tiên giảm tác động và truyền thông |
| **P1 / High** | Chức năng chính lỗi ở một phần người dùng; workaround hạn chế | On-call xử lý và cập nhật tình trạng định kỳ |
| **P2 / Medium** | Có suy giảm hiệu năng nhưng chức năng chính vẫn hoạt động, có workaround | Điều tra có ưu tiên, xác định thời điểm sửa |
| **P3 / Low** | Lỗi nhỏ, đề nghị làm rõ, tình huống chưa ảnh hưởng đáng kể | Tạo vấn đề cần theo dõi và giải quyết theo quy trình thông thường |

Đây **không phải bảng ánh xạ bắt buộc** sang severity của Azure Support. Mức độ khẩn cấp khi mở support request cần phản ánh **tác động thực tế**, đồng thời lựa chọn severity và khả năng hỗ trợ phụ thuộc gói support, loại vấn đề và giao diện hỗ trợ của Azure tại thời điểm tạo.

### 3.2. Vai trò trong phiên ứng phó

| Vai trò | Trách nhiệm |
| --- | --- |
| **Incident Commander (IC)** | Điều phối tổng thể, xác định mức tác động, quyết định escalation, phê duyệt thay đổi rủi ro trong phạm vi được giao |
| **Technical Lead / Subject Matter Expert** | Dẫn dắt điều tra thành phần liên quan, đánh giá phương án khôi phục |
| **On-call Operator** | Chạy bước read-only, thao tác đã được phép, lưu log và xác nhận kết quả |
| **Communications Owner** | Cập nhật đối tượng liên quan, nội dung và thời điểm thông báo |
| **Scribe / Observer** | Ghi timeline UTC, giả thuyết, thay đổi và bằng chứng |
| **Azure Support Liaison** | Tạo/cập nhật yêu cầu hỗ trợ, chuyển câu hỏi cho chuyên gia nội bộ, theo dõi phản hồi |

Với đội nhỏ, một người có thể kiêm nhiều vai trò; nhưng **quyền quyết định thay đổi trên production** và nơi cập nhật trạng thái phải luôn rõ ràng.

### 3.3. Sơ đồ xử lý tổng thể

~~~mermaid
flowchart TD
    A["Alert / khách hàng báo lỗi"] --> B["Xác minh SLI, phạm vi và tác động"]
    B --> C{"Incident có ảnh hưởng thực tế?"}
    C -->|"Chưa"| D["Theo dõi / tạo vấn đề và cập nhật cảnh báo"]
    C -->|"Có"| E["Kích hoạt IC, ghi timeline UTC"]
    E --> F["Thu dữ kiện: Azure Monitor, Activity Log, Service/Resource Health"]
    F --> G{"Có biện pháp giảm tác động đã kiểm chứng?"}
    G -->|"Có"| H["Thực hiện thay đổi được duyệt; theo dõi và rollback nếu cần"]
    G -->|"Chưa rõ"| I["Điều tra thêm và escalation nội bộ / Azure Support"]
    I --> H
    H --> J{"Hành trình nghiệp vụ và SLO đã phục hồi?"}
    J -->|"Chưa"| F
    J -->|"Rồi"| K["Ổn định, thông báo phục hồi"]
    K --> L["Đối soát dữ liệu và hậu kiểm"]
~~~

Điều tra và giảm tác động có thể chạy song song. Không chờ xác định root cause hoàn hảo mới thực hiện một mitigation an toàn đã có bằng chứng và quyền.

## 4. Các trường bắt buộc của một runbook vận hành

Mỗi runbook nên có metadata dễ tìm khi trực ca. Mẫu sau là **cấu trúc tài liệu minh họa**, không phải định dạng cấu hình riêng của Azure:

~~~yaml
runbook_id: RB-AZ-APP-5XX
title: "HTTP 5xx tăng trên API Azure"
version: "1.0"
owner_team: "Application/SRE"
review_interval: "theo chu kỳ nội bộ và sau mọi thay đổi đáng kể"
trigger:
  - "Cảnh báo error-rate vượt ngưỡng SLO"
  - "Synthetic transaction thất bại liên tục"
service:
  subscription: "<subscription-id>"
  resource_group: "rg-orders-prod"
  primary_region: "<azure-region>"
  application: "orders-api"
dependencies:
  - "App Service hoặc compute tier"
  - "Azure SQL / database"
  - "Key Vault và Microsoft Entra ID"
  - "VNet / Private Endpoint / DNS"
  - "Queue / storage / external integrations"
roles:
  incident_commander: "<role-or-oncall>"
  technical_owner: "<role-or-oncall>"
  support_liaison: "<role-or-oncall>"
links:
  dashboard: "<internal-monitoring-url>"
  deploy_history: "<internal-pipeline-url>"
  escalation_matrix: "<internal-doc-url>"
steps:
  - "Xác minh impact và phạm vi"
  - "Thu metric, log, trace, Activity Log, Service Health"
  - "Chọn mitigation theo decision tree"
  - "Thực hiện thay đổi đã được duyệt"
  - "Xác minh SLO, backlog và dữ liệu"
  - "Ghi timeline, update ticket, hậu kiểm"
stop_conditions:
  - "Phát hiện nguy cơ mất dữ liệu vượt mục tiêu"
  - "Thiếu quyền hoặc không xác định được trạng thái authoritative"
  - "Mitigation gây ảnh hưởng lớn hơn sự cố ban đầu"
~~~

Những giá trị đặt trong dấu `<...>` là placeholder cần thay. Runbook thực tế nên đặt trong nguồn quản lý phiên bản, có người duyệt và lịch kiểm tra. Các lệnh chạy production phải gắn **scope và quyền cần thiết**, điều kiện trước/sau, các rủi ro và phương án rollback.

### 4.1. Thiết kế mỗi bước như một thao tác có thể kiểm tra

Một bước tốt có năm phần:

1. **Điều kiện trước:** Người thực hiện đã chọn đúng subscription, region, resource group và có quyền đọc hoặc thay đổi cần thiết.
2. **Hành động:** Đọc dashboard, chạy lệnh quan sát, áp dụng rollback đã được phê duyệt hoặc liên hệ chủ sở hữu.
3. **Bằng chứng:** Lưu kết quả (timestamp UTC, link truy vấn, operation ID); che giấu secret và dữ liệu người dùng.
4. **Điều kiện quyết định:** Nếu lỗi tập trung ở một deployment thì chuyển sang nhánh rollback; nếu Service Health công bố sự cố liên quan thì mở nhánh phối hợp nền tảng.
5. **Tiêu chí hoàn thành và fallback:** Probe khỏe, SLO phục hồi; nếu thất bại, dừng hoặc quay lại trạng thái trước theo kế hoạch.

Tránh hướng dẫn kiểu “kiểm tra log rồi khởi động lại” vì không nêu **log nào**, **khi nào khởi động lại là phù hợp**, và **đánh giá ảnh hưởng đến dữ liệu có trạng thái**.

## 5. Thu nguồn tín hiệu Azure đúng thứ tự

Đội vận hành cần phân biệt lỗi code ứng dụng, dependency, thay đổi cấu hình, quota/throttling và lỗi của nền tảng Azure. Không có một dashboard nào đủ cho mọi tầng.

| Nguồn | Cung cấp thông tin gì? | Khi nào ưu tiên? |
| --- | --- | --- |
| **Azure Monitor metrics** | CPU, memory (nếu có telemetry tương ứng), request count, latency, availability, throughput, quota/tính năng hỗ trợ tùy dịch vụ | Xác nhận phạm vi, thời điểm và xu hướng |
| **Application Insights** | Request, dependency, exception, distributed tracing, synthetic availability | Lỗi API, endpoint chậm hoặc phụ thuộc |
| **Log Analytics** | Phân tích log và telemetry bằng KQL khi đã cấu hình thu thập | Truy vấn theo resource, request ID, deployment, khoảng thời gian |
| **Azure Activity Log** | Hoạt động **management plane** như thay đổi resource, deployment, quyền và sự kiện quản trị | Nghi có thao tác cấu hình hay deployment gây lỗi |
| **Resource Health** | Trạng thái và lịch sử sức khỏe của tài nguyên **được hỗ trợ** | Nghi VM/resource cụ thể không khỏe do nền tảng |
| **Azure Service Health** | Sự kiện dịch vụ, planned maintenance và khuyến nghị liên quan subscription/region | Nghi ảnh hưởng nền tảng Azure tới dịch vụ/khu vực |
| **Azure Status** | Tình trạng dịch vụ Azure công khai ở mức tổng quát | Tham khảo tình hình diện rộng; không thay thế Service Health cá nhân hóa |
| **Deployment/pipeline logs** | Phiên bản artifact, IaC diff, rollout và thời điểm thay đổi | Lỗi bắt đầu ngay sau deploy hoặc cập nhật cấu hình |
| **Dữ liệu nghiệp vụ** | Tỷ lệ đặt hàng/thanh toán thành công, queue backlog, các giao dịch bị treo | Xác định tác động thật đối với người dùng |

**Activity Log không tự chứa đầy đủ log ứng dụng hoặc data-plane**. Muốn truy vết truy vấn database, lỗi API, access log storage, cần bật những nguồn diagnostic logs/telemetry tương ứng trước khi có sự cố. Tương tự, nếu Service Health không liệt kê một sự kiện thì chưa chứng minh lỗi không liên quan Azure; cần tiếp tục dựa vào bằng chứng thực tế.

### 5.1. Các nguyên tắc khi lập timeline

Ghi thời điểm ở **UTC**, độ phân giải và vùng giờ hiển thị; tách:

- `T_impact`: lúc giao dịch người dùng bắt đầu suy giảm.
- `T_detected`: lúc hệ thống hoặc người trực phát hiện.
- `T_declared`: lúc xác nhận incident và phân vai.
- `T_mitigated`: lúc giảm được tác động chính.
- `T_recovered`: lúc tiêu chí SLO và nghiệp vụ phục hồi trong cửa sổ định nghĩa.
- `T_closed`: lúc hoàn tất theo dõi, thông báo và thủ tục đóng incident.

Đừng lấy thời điểm alert tạo làm thời điểm lỗi bắt đầu nếu telemetry cho thấy người dùng bị ảnh hưởng trước đó. Theo dõi clock skew, sampling, vùng thời gian và event ingestion delay khi kết hợp nhiều nguồn.

**Đo hiệu quả runbook:** Với từng incident, ghi thời gian từ `T_impact` đến `T_detected` (thời gian phát hiện), từ `T_detected` đến khi on-call nhận trách nhiệm (thời gian nhận xử lý), và từ `T_impact` đến `T_recovered` (thời gian phục hồi thực đo). Tổ chức có thể tổng hợp MTTD và MTTR qua nhiều incident, đồng thời so thời gian phục hồi của từng lần với **RTO (Recovery Time Objective)** nếu dịch vụ có mục tiêu khôi phục được định nghĩa. Đây là các thước đo khác nhau; không dùng thời điểm đóng ticket Azure Support thay cho thời điểm người dùng thực sự được phục vụ lại.

## 6. Thao tác quan sát bằng Azure CLI và Kusto

Các lệnh dưới đây **chỉ đọc dữ liệu**, phù hợp với giai đoạn đầu. Người thực hiện phải thay placeholder, chọn đúng subscription và xác nhận quyền. Không đưa access token, SAS token, connection string hoặc khóa truy cập vào log, support ticket hay bản chụp màn hình.

### 6.1. Kiểm tra context và tài nguyên

~~~bash
# Subscription/tenant hiện đang chọn
az account show \
  --query "{subscription:id,tenant:tenantId,name:name}" \
  -o json

# Xem danh sách subscription khi cần xác minh context
az account list \
  --query "[].{name:name,id:id,state:state}" \
  -o table

# Đọc thuộc tính tài nguyên khi biết Resource ID
az resource show \
  --ids "/subscriptions/<subscription-id>/resourceGroups/rg-orders-prod/providers/<provider>/<type>/<name>" \
  -o json
~~~

Chỉ sử dụng `az account set --subscription ...` nếu người vận hành cần đổi context và đã đối chiếu đúng môi trường; lỗi thao tác ở nhầm subscription có thể nghiêm trọng hơn lỗi ban đầu. Ưu tiên các lệnh có `--subscription` tường minh khi được hỗ trợ.

### 6.2. Đọc Activity Log trong cửa sổ sự cố

~~~bash
az monitor activity-log list \
  --resource-group rg-orders-prod \
  --start-time "2026-11-20T09:30:00Z" \
  --end-time "2026-11-20T10:30:00Z" \
  --query "[].{time:eventTimestamp,operation:operationName.value,status:status.value,correlation:correlationId}" \
  -o table
~~~

Lệnh tìm các sự kiện quản trị trong resource group và khoảng thời gian minh họa. Khi thấy sự kiện thay đổi, kiểm tra đúng resource ID, actor và bản thay đổi. **Sự trùng thời điểm không đủ chứng minh quan hệ nhân quả**; đối chiếu log ứng dụng, diff deployment và kết quả trước/sau.

### 6.3. Xem danh mục metric được resource hỗ trợ

~~~bash
az monitor metrics list-definitions \
  --resource "/subscriptions/<subscription-id>/resourceGroups/rg-orders-prod/providers/<provider>/<type>/<name>" \
  -o table
~~~

Tên metric khác nhau theo loại resource và SKU. Chỉ sau khi biết metric được hỗ trợ mới lập câu lệnh `az monitor metrics list` với metric name, time window và aggregation phù hợp. Không đo CPU của dịch vụ managed PaaS bằng cách giả định metric giống VM.

### 6.4. KQL điều tra lỗi request và dependency

Ví dụ với **workspace-based Application Insights** sử dụng bảng `AppRequests`. Query tìm service gặp lỗi theo cửa sổ năm phút:

~~~kusto
AppRequests
| where TimeGenerated between (datetime(2026-11-20T09:30:00Z) .. datetime(2026-11-20T10:30:00Z))
| summarize
    Total = sum(ItemCount),
    Failed = sumif(ItemCount, Success == false),
    P95DurationMs = percentile(DurationMs, 95)
    by AppRoleName, bin(TimeGenerated, 5m)
| extend FailureRatePercent = iff(Total == 0, real(null), 100.0 * Failed / Total)
| order by TimeGenerated asc
~~~

Để nhận diện các dependency báo lỗi, khi workspace có bảng `AppDependencies`:

~~~kusto
AppDependencies
| where TimeGenerated > ago(1h)
| summarize
    Calls = sum(ItemCount),
    Failures = sumif(ItemCount, Success == false)
    by Target, Type, AppRoleName
| extend FailureRatePercent = iff(Calls == 0, real(null), 100.0 * Failures / Calls)
| order by Failures desc
~~~

Schema thực tế và độ đầy đủ dữ liệu phụ thuộc cách cấu hình telemetry, sampling và thời gian lưu giữ; một số môi trường dùng tên bảng khác như `requests` hoặc `dependencies`. Khi gửi hỗ trợ, ghi rõ khoảng UTC, query, khoảng giới hạn do sampling và **kết quả đã làm sạch dữ liệu nhạy cảm**.

### 6.5. Dùng correlation ID và trace khi nào?

Một request người dùng có thể đi qua API Gateway → API → database → queue. **Correlation ID / trace ID** giúp nối các đoạn đó. Từ request lỗi, ghi lại thời điểm UTC, endpoint, status code, operation ID, trace/correlation ID và dependency kết thúc bằng lỗi. Khi lỗi ở management plane Azure, giữ các giá trị **correlationId**, **operation ID**, **deployment name** hoặc request ID mà response cung cấp. Không đồng nhất các loại ID: chúng khác nguồn phát sinh và mục đích.

## 7. Quy trình runbook xử lý incident theo các giai đoạn

Một runbook thực tiễn phải phân nhánh theo dữ kiện. Quy trình sau phù hợp làm khung chung cho Azure, rồi chuyên biệt hóa theo App Service, VM, AKS, Azure SQL hoặc Storage.

### Giai đoạn 1 — Xác nhận và khoanh vùng

**Input:** Alert, ticket hoặc báo cáo của người dùng.

**Thao tác:**

1. Xác nhận môi trường, subscription, resource group, region, dịch vụ và thời gian bắt đầu.
2. Kiểm tra SLI từ ngoài vào trong: đặt hàng có thành công không, lỗi chỉ ở một endpoint hay toàn bộ ứng dụng?
3. So sánh giữa region, zone, instance, phiên bản release, network path hoặc nhóm khách hàng để tìm phạm vi lỗi.
4. Kiểm tra Service Health và Resource Health có sự kiện liên quan không; đừng dừng điều tra chỉ vì trang status hiển thị xanh.
5. Mở incident record, đặt mức ưu tiên nội bộ dựa vào tác động và thông báo vai trò trực ca.

**Output:** Mô tả tác động có thể kiểm chứng, khoảng thời gian và giả thuyết điều tra đầu tiên.

### Giai đoạn 2 — Điều tra nhanh với giả thuyết có bằng chứng

Tạo danh sách ít giả thuyết có sức giải thích cao; mỗi giả thuyết cần một phép kiểm tra phân biệt:

| Dấu hiệu | Giả thuyết | Phép kiểm tra |
| --- | --- | --- |
| 5xx tăng sau rollout | Ứng dụng/deployment mới lỗi | So thời điểm deploy, version, exception, canary |
| Response chậm và database timeout | Connection pool, query hoặc database quá tải | Dependency latency, connection count, service metrics |
| HTTP 429 tăng | Rate limit/throttling ở tầng API hoặc dịch vụ Azure | Response headers, error code, quota/metrics từng dịch vụ |
| HTTP 403 trên storage/Key Vault | RBAC, identity, firewall, token hoặc cấu hình mạng thay đổi | Activity Log, role assignments, sign-in và service diagnostics |
| Một zone không phục vụ | Backend placement, health probe hoặc sự cố zone | Probe/instance metrics, Resource Health, Service Health |
| Deployment thất bại | Quota, Azure Policy, provider registration, RBAC hoặc template | Deployment operation details, error code, Activity Log |
| Tăng chi phí bất thường | Autoscale, traffic, log ingestion hoặc resource mới | Cost Management và tài nguyên mới từ Activity Log |

Không chạy thay đổi production chỉ để kiểm tra một giả thuyết khi có phép đo read-only ít rủi ro hơn.

### Giai đoạn 3 — Giảm tác động và xác minh rủi ro

Chọn một biện pháp phù hợp với bằng chứng và quyền phê duyệt:

- **Rollback deployment** nếu có tương quan mạnh giữa phiên bản lỗi và triệu chứng, có bản trước an toàn và đã xác nhận tính tương thích với schema dữ liệu.
- **Scale hoặc điều chỉnh cấu hình** nếu có dấu hiệu nghẽn tài nguyên, quota và ngân sách cho phép; giữ lại metric trước/sau để tránh nhầm scale làm hết lỗi tạm.
- **Chuyển lưu lượng/failover** khi có môi trường khỏe, đã kiểm tra dữ liệu, DNS và quyền, đồng thời xử lý rủi ro split-brain hoặc mất dữ liệu.
- **Giới hạn traffic, bật circuit breaker, giảm retry storm** khi hệ thống phụ thuộc đang quá tải.
- **Liên hệ nhóm sở hữu dependency** và mở Azure Support khi bằng chứng chỉ ra lỗi nền tảng, hành vi sản phẩm không khớp tài liệu, quota vượt dự kiến hoặc không thể giải thích bằng quyền/cấu hình.

Trước thay đổi phải xác định **ai duyệt, ảnh hưởng dự kiến, dữ liệu có rủi ro, dấu hiệu thất bại và rollback**. Một số thao tác như xóa resource, forced failover dữ liệu bất đồng bộ hoặc khôi phục backup vào production có thể gây tổn thất khó đảo ngược; chỉ thực hiện theo runbook và quyền đã phê duyệt.

### Giai đoạn 4 — Xác minh phục hồi

Không đóng incident chỉ vì lệnh rollback trả thành công hoặc tài nguyên chuyển sang trạng thái Running. Phải kiểm tra:

- Tỷ lệ giao dịch nghiệp vụ thành công và p95 latency trong cửa sổ quan sát đã thỏa thuận.
- Dependency errors, connection pools, queue backlog, database transactions và lỗi background workers.
- Dữ liệu đã xác nhận trước sự cố có toàn vẹn, không trùng do retry/failover.
- Các vùng, instance và đường vào có phân phối traffic đúng; alert có trở lại ngưỡng khỏe.
- Không còn thay đổi tạm gây rủi ro bảo mật/chi phí, chẳng hạn mở rộng firewall, tăng replica quá mức hoặc tạo tài nguyên xử lý khẩn cấp.

**Output:** Tài liệu về thời điểm phục hồi, trạng thái cuối và bằng chứng đáp ứng SLO. Nếu vẫn còn giới hạn thì ghi rõ mức degraded mode và thời hạn chấp nhận.

### Giai đoạn 5 — Hậu kiểm và cải tiến runbook

Sau khi ổn định, ghép timeline: cái gì thay đổi, cái gì thất bại, hành động nào giúp khôi phục, điều gì chưa được kiểm chứng? Ghi owner, thời hạn và tiêu chí đóng cho từng cải tiến; chỉ xem một cải tiến hoàn thành khi đã có **bằng chứng test/diễn tập** thích hợp.

## 8. Ví dụ runbook hoàn chỉnh: API đơn hàng trả 503 sau deployment

**Bối cảnh giả định:** API `orders-api` chạy trên Azure App Service trong `rg-orders-prod`. Sau một deployment, request `POST /orders` có nhiều HTTP 503; các transaction đặt đơn bị gián đoạn. Phụ thuộc gồm Azure SQL, Key Vault và một queue. Hệ thống có Application Insights và quy trình rollback phiên bản ứng dụng.

**Mục tiêu runbook:** khôi phục tỷ lệ đặt đơn thành công theo SLO, giữ nguyên tính toàn vẹn đơn hàng, xác định khi nào cần mở Azure Support. Các địa chỉ và số liệu trong ví dụ chỉ để minh họa.

### 8.1. Điều kiện kích hoạt và thông tin tối thiểu

~~~yaml
runbook: RB-ORDERS-503
owner: "Orders / SRE"
trigger:
  - "5xx tăng vượt ngưỡng alert đã duyệt"
  - "Synthetic POST/GET test không thành công"
preconditions:
  - "Xác nhận subscription và App Service target"
  - "Có dashboard request/dependency và lịch sử rollout"
  - "Có người quyết định rollback theo quy trình release"
safety:
  - "Không thử giao dịch thanh toán thật"
  - "Không đưa token, connection string, PII vào báo cáo"
  - "Không chạy database migration ngược khi chưa đánh giá dữ liệu"
completion:
  - "SLI phục hồi theo cửa sổ quan sát"
  - "Không có đơn bị tạo trùng hoặc kẹt queue ngoài ngưỡng"
  - "Có timeline và liên kết đến evidence"
~~~

### 8.2. Triển khai theo nhánh quyết định

**Bước 1 — Quan sát:** Xem error rate và dependency failure trong ít nhất một khoảng trước và sau rollout. Lấy một số `operation_Id`/trace ID từ các request 503. Xác nhận thời gian `T_impact`.

**Bước 2 — Kiểm tra thay đổi:** So thời điểm artifact mới được đưa vào phục vụ, thay đổi app settings, instance count và các sự kiện ở Activity Log. Nếu deployment trùng thời điểm nhưng mọi phiên bản cùng lỗi do Azure SQL mất kết nối, tiếp tục điều tra dependency thay vì quy mọi lỗi cho code.

**Bước 3 — Kiểm tra nền tảng:** Xem Azure Service Health, Resource Health khi khả dụng, metrics App Service và dữ kiện scaling/cold start. Nếu resource không khỏe do sự kiện nền tảng hoặc lỗi khó tái hiện, chuẩn bị support request cùng timestamp, resource ID và request/correlation ID.

**Bước 4 — Chọn mitigation:**

| Điều kiện quan sát | Quyết định được xem xét |
| --- | --- |
| Phiên bản mới tăng lỗi, bản trước vẫn hoạt động, rollback tương thích DB | Kích hoạt rollback theo pipeline/slot strategy đã phê duyệt |
| Lỗi kết nối Azure SQL hoặc Private Endpoint trên mọi phiên bản | Ưu tiên kiểm tra database/network/DNS, không rollback mù |
| 503 do backend quá tải; CPU, connection pool hoặc queue depth vượt ngưỡng | Giới hạn traffic/retry; điều chỉnh scale khi quota và ngân sách cho phép |
| Không tìm thấy nguyên nhân và còn tác động cao | Escalate IC, nhóm phụ thuộc và Azure Support với hồ sơ bằng chứng |
| Khôi phục có thể gây mất dữ liệu/không xác định transaction state | Tạm dừng thay đổi ghi, nhờ data owner xác nhận phương án |

**Bước 5 — Xác minh:** Chạy synthetic create-order và read-order với mã idempotency. Theo dõi ít nhất một cửa sổ SLO đã xác định; kiểm tra order count, queue backlog và dependency errors. Lưu mã deployment tốt, mốc phục hồi và bất kỳ workaround còn hiệu lực.

**Bước 6 — Cập nhật liên lạc:** Thông báo mức phục hồi, chức năng còn suy giảm, thời điểm cập nhật tiếp theo. Khi incident kết thúc, mở post-incident review và cập nhật runbook.

### 8.3. Ví dụ timeline để đối chiếu

| Giờ UTC (giả định) | Sự kiện | Bằng chứng |
| --- | --- | --- |
| 09:55 | Deploy phiên bản `v2.14` | Pipeline release log |
| 09:59 | 5xx tăng, đơn mới bắt đầu lỗi | Synthetic transaction, AppRequests |
| 10:01 | Azure Monitor cảnh báo | Alert record |
| 10:04 | IC xác nhận P1; giao điều tra | Incident timeline |
| 10:07 | Dependency Azure SQL khỏe, lỗi tập trung trên v2.14 | Distributed trace, metrics |
| 10:12 | Phê duyệt rollback sang v2.13 | Change record |
| 10:17 | Traffic phục vụ từ phiên bản trước | Deployment status, ingress log |
| 10:21 | Giao dịch đặt đơn đạt SLO trong cửa sổ xác minh | Business SLI, synthetic test |

Ví dụ này cho thấy rollback giúp giảm tác động. Tuy nhiên **nguyên nhân gốc vẫn chưa được chứng minh** nếu chưa phân tích sự khác biệt giữa hai phiên bản và mô hình lỗi. Không cần mở Azure Support chỉ để xác nhận một lỗi ứng dụng đã được chứng minh, nhưng vẫn cần hỗ trợ khi có dấu hiệu lỗi dịch vụ Azure, hành vi không được giải thích hoặc yêu cầu chuyên môn về nền tảng.

## 9. Khi nào cần mở hồ sơ hỗ trợ Azure?

**Azure Support request** là hồ sơ để Microsoft và tổ chức trao đổi về một vấn đề thuộc dịch vụ hoặc tài khoản Azure. Mở hỗ trợ là **một nhánh của quy trình incident**, không thay thế quyền sở hữu sự cố, hành động giảm tác động hoặc truyền thông nội bộ.

Các loại yêu cầu phổ biến:

| Loại yêu cầu | Khi nào sử dụng | Chuẩn bị trước |
| --- | --- | --- |
| **Technical issue** | Dịch vụ Azure lỗi bất thường, không hoạt động như mong đợi, yêu cầu phân tích chuyên sâu | Resource ID, region, thời điểm, error code, request/correlation ID, ảnh hưởng và các bước tái hiện |
| **Service and subscription limits / quota** | Cần nâng hạn mức vCPU hoặc quota khác; gặp giới hạn cấp phát | Subscription, region, loại quota/SKU, mức hiện tại, mức đề nghị, lý do và thời điểm cần |
| **Billing / subscription management** | Tranh chấp hóa đơn, vấn đề thanh toán hoặc subscription | Billing scope/account phù hợp, kỳ thanh toán, charge liên quan; không đưa thông tin thanh toán nhạy cảm qua log không bảo vệ |
| **Account/access-related** | Vấn đề truy cập, quyền hoặc tình huống tài khoản cần nhóm hỗ trợ tương ứng | Tenant/subscription, identity được mô tả an toàn, bước lỗi, mã lỗi; dùng kênh xác thực chính thức |

**Phân biệt entitlement:** Một số loại yêu cầu liên quan billing hoặc quản trị subscription có thể có đường hỗ trợ khác technical support. Khả năng mở ticket kỹ thuật, số lần liên hệ, mức severity, kênh hỗ trợ và thời gian phản hồi phụ thuộc **gói hỗ trợ Azure** và chính sách áp dụng cho subscription/đối tác. Không mặc định mọi subscription có quyền technical support ở mức khẩn cấp cao nhất.

### 9.1. Trước khi tạo support request

1. Kiểm tra **Azure Service Health** và thông báo hiện có về dịch vụ, region và subscription liên quan.
2. Kiểm tra tài nguyên/đường lỗi cụ thể bằng metrics, logs, Resource Health và Activity Log.
3. Tìm thay đổi gần đây trong deployment/config/RBAC/Policy; ghi rõ những phép kiểm tra đã thực hiện.
4. Xác nhận có quyền tạo yêu cầu hỗ trợ trên đúng scope (ví dụ các vai trò Azure RBAC phù hợp với quyền `Microsoft.Support/supportTickets/write`, tùy cấu hình) và quyền xem subscription/resource liên quan. **Không cấp Owner chỉ để mở ticket** nếu vai trò chuyên biệt đáp ứng được.
5. Chuẩn bị mô tả impact, workaround, thời điểm UTC, resource ID và dấu vết đủ để nhóm hỗ trợ điều tra.

Khi incident ảnh hưởng nghiêm trọng, **không cần đợi thu thập hoàn hảo mọi log** mới mở ticket; gửi mô tả và bằng chứng đã có, cập nhật khi xuất hiện dữ kiện mới. Phải có người nội bộ theo dõi ticket và tiếp tục mitigation.

### 9.2. Luồng tạo yêu cầu trong Azure Portal

Các nhãn giao diện có thể thay đổi, nhưng quy trình thường là:

1. Đăng nhập **Azure Portal** bằng tài khoản được cấp quyền; chọn đúng tenant/subscription.
2. Mở **Help + support** hoặc luồng hỗ trợ của tài nguyên/subscription; chọn **Create a support request**.
3. Chọn loại vấn đề, dịch vụ/resource và subscription; đọc giải pháp tự hỗ trợ nếu có.
4. Nhập **Problem description**, mức tác động/severity được giao diện cho phép, môi trường và thông tin kỹ thuật.
5. Chọn gói/hình thức hỗ trợ khi hệ thống yêu cầu và khi subscription có quyền; cung cấp thông tin người liên hệ, thời gian và kênh phù hợp.
6. Kiểm tra lại toàn bộ thông tin, tài liệu đính kèm; loại bỏ bí mật và PII không cần thiết; gửi yêu cầu.
7. Lưu **support request ID**, đường dẫn hồ sơ, thời điểm gửi và người liên hệ vào incident record; theo dõi cập nhật và cung cấp kết quả điều tra mới.

Một số vấn đề quota được hướng tới giao diện quản lý **Usage + quotas** hoặc luồng quota request chuyên biệt. Hãy dùng luồng đang được Azure cung cấp cho loại quota đó, thay vì cho rằng mọi hạn mức đều được nâng qua cùng một nút hỗ trợ.

### 9.3. Mức severity và cách chọn

Mức severity trong Azure Support phản ánh **business impact và mức độ khẩn cấp** theo loại hỗ trợ/gói hỗ trợ. Một số kênh thể hiện các mức như A/B/C hoặc những lựa chọn tương đương, nhưng **mô tả, tính khả dụng và mục tiêu phản hồi phải xem theo subscription/support plan thực tế**.

Khi chọn mức, mô tả có thể kiểm chứng:

- Bao nhiêu người dùng, giao dịch hoặc workload production chịu tác động?
- Hệ thống ngừng hoạt động toàn bộ, suy giảm một chức năng hay chỉ môi trường test?
- Có workaround chấp nhận được hay không, và workaround ảnh hưởng bảo mật/dữ liệu/hiệu năng thế nào?
- Có nguy cơ mất dữ liệu, gián đoạn doanh thu hoặc vi phạm nghĩa vụ dịch vụ không?
- Đội kỹ thuật có sẵn để cùng làm việc liên tục nếu yêu cầu được xử lý theo mức khẩn cấp cao?

Không chọn severity cao chỉ để hy vọng câu trả lời nhanh cho một câu hỏi thông thường, và không hạ thấp tác động thực sự của sự cố production.

## 10. Một hồ sơ hỗ trợ Azure chất lượng cần những gì?

Nhân sự hỗ trợ cần biết **đang điều tra tài nguyên nào, lỗi xảy ra khi nào, tác động ra sao, có tái hiện được không và những gì đã thử**. Hồ sơ nên đủ ngắn để đọc nhanh nhưng đủ chính xác để nhóm dịch vụ tra cứu telemetry phía Azure.

### 10.1. Bộ trường thông tin gợi ý

| Trường | Cách ghi có ích |
| --- | --- |
| **Tiêu đề** | `Azure App Service — HTTP 503 tăng sau 09:59 UTC tại [region]` |
| **Loại vấn đề và dịch vụ** | Technical / App Service, Azure SQL, Network, Storage... |
| **Subscription và tenant** | ID thực tế qua kênh hỗ trợ chính thức; tránh nhầm scope |
| **Resource** | **Full ARM resource ID**, resource group, region, SKU/tier, zone nếu liên quan |
| **Impact** | Thành phần bị ảnh hưởng, môi trường production/staging, tỷ lệ lỗi, số người dùng, hành trình nghiệp vụ |
| **Timestamps UTC** | Bắt đầu, phát hiện, tái hiện gần nhất, thời điểm thay đổi, lúc mitigation |
| **Error** | HTTP status, Azure error code, message chính xác đã lọc nhạy cảm |
| **Identifiers** | `x-ms-request-id`, `x-ms-correlation-request-id`, `correlationId`, operation/trace ID nếu response có |
| **Reproduction** | Các bước ngắn với đầu vào thử nghiệm đã được làm sạch; tần suất xảy ra |
| **Checks performed** | Monitor/KQL, Health, Activity Log, deployment, mạng/RBAC/quota |
| **Mitigation/workaround** | Đã thử gì, kết quả, rủi ro còn lại, liệu còn ảnh hưởng hay không |
| **Expected vs actual** | Hành vi mong đợi dựa trên kiến trúc/tài liệu và hành vi quan sát |
| **Contact and availability** | Owner, múi giờ, kênh, khung giờ phản hồi, bridge nếu phù hợp |
| **Evidence** | Screenshot, redacted logs, sanitized trace, timestamps và link truy vấn nội bộ hợp lệ |

**Không phải mọi Azure service đều trả cùng header hoặc cùng correlation ID.** Chỉ đưa identifier thực sự được response/log cung cấp, ghi nguồn của ID và không tự tạo giá trị làm như thể có thật.

### 10.2. Đảm bảo thông tin hỗ trợ an toàn

Hồ sơ có thể cần resource ID, tenant/subscription ID hoặc tên tài nguyên phục vụ điều tra. Đây là thông tin vận hành cần quản lý theo quyền tổ chức, nhưng **không tương đương secret**. Luôn gửi qua **kênh hỗ trợ chính thức** và thực hiện quy định bảo mật nội bộ.

Tuyệt đối không đính kèm:

- Password, client secret, access key, SAS token, bearer token, refresh token hoặc connection string có credential.
- Dữ liệu thanh toán, thông tin khách hàng, payload cá nhân hoặc log ghi dữ liệu nhạy cảm không được cho phép.
- Toàn bộ environment variables hoặc file cấu hình chứa bí mật nếu chỉ cần một phần error message.
- Ảnh chụp màn hình có thông tin nhạy cảm khác nằm ngoài khu vực lỗi.

Khi cần chia sẻ network trace hoặc diagnostic package, kiểm tra nội dung, phạm vi thời gian và cách Azure Support yêu cầu upload. Chỉ đồng ý thu thập thêm telemetry/chia sẻ quyền truy cập khi đúng quy trình tổ chức, có chủ sở hữu và hiểu phạm vi dữ liệu được cung cấp.

## 11. Mẫu hồ sơ yêu cầu hỗ trợ kỹ thuật có thể tái sử dụng

Ví dụ minh họa cho API gặp HTTP 503, được cố ý dùng **placeholder và số liệu giả định**. Không gửi nguyên văn như một sự cố thật.

~~~text
Subject:
Azure App Service | Production HTTP 503 | <region> | 2026-11-20 09:59 UTC

Issue type:
Technical issue — Azure App Service

Subscription:
<subscription-id>

Resource:
 /subscriptions/<subscription-id>/resourceGroups/rg-orders-prod/
 providers/Microsoft.Web/sites/orders-api
(Đường dẫn trên được xuống dòng để dễ đọc; ID thực là một chuỗi liên tục.)

Region / SKU:
<region> / <app-service-plan-sku>

Business impact:
- Production orders-api, POST /orders affected.
- Approximately 28% of requests returned HTTP 503 between
  09:59 and 10:17 UTC.
- Customer order creation degraded; read-only endpoints remained available.
- No evidence of acknowledged order loss at the time of submission.
- Incident owner: <role / safe contact channel>.

Expected behavior:
POST /orders should accept a valid test transaction and return
the application's documented successful response within SLO.

Observed behavior:
503 responses with representative error code/message:
<sanitized-error-text>

UTC timeline:
09:55 Deployment v2.14 completed.
09:59 First observed impact via synthetic transaction.
10:01 Azure Monitor alert fired.
10:07 Dependency metrics appeared healthy.
10:12 Rollback approved.
10:17 Traffic started serving v2.13.
10:21 Success rate returned to SLO.

Correlation/request evidence:
- Example failed request time: 10:03:21 UTC
- App Insights operation ID: <sanitized-operation-id>
- Azure response request ID (if present): <actual-response-id>
- Deployment name/correlation ID (if relevant): <actual-id>
- Sanitized logs and metric snapshot: <attachment-or-reference>

Troubleshooting performed:
1. Checked Azure Service Health and Resource Health.
2. Correlated 5xx with deployment timeline.
3. Reviewed Application Insights requests and dependencies.
4. Confirmed database connectivity for healthy endpoints.
5. Rolled back to v2.13; errors decreased.

Current state:
Service recovered after rollback; root cause under investigation.
No further configuration changes planned until evidence review.

Assistance requested:
Please help determine whether platform-level App Service events,
instance behavior, or service-side diagnostics contributed to the
503 spike in the affected window, and recommend additional evidence
needed to distinguish platform behavior from the application release.

Availability:
<contact / timezone / preferred channel / on-call bridge>
~~~

**Điểm quan trọng:** Mẫu nêu **giả thuyết** và câu hỏi cần hỗ trợ, thay vì kết luận Azure bị lỗi khi chưa có bằng chứng. Nếu incident đang diễn ra, thay `Current state` bằng tình trạng hiện tại, mức độ ảnh hưởng và workaround đang dùng.

### 11.1. Ví dụ hồ sơ quota

Khi workload không triển khai được VM do quota:

~~~text
Issue: Quota increase / service and subscription limits
Subscription: <subscription-id>
Region: <azure-region>
Resource family/SKU: <VM family or exact quota category>
Current quota: <verified current limit>
Current usage: <verified usage>
Requested quota: <required limit>
Business reason: Planned capacity for 2 additional availability zones
Requested timeline: <business date>
Failure evidence: <error code, UTC timestamp, deployment operation ID>
Alternatives assessed: <supported SKU/region/capacity changes>
Contact: <responsible team and approved channel>
~~~

Phân biệt **quota đủ nhưng không còn capacity vật lý khả dụng trong zone/SKU** với **quota limit đã chạm**: hai vấn đề có nguyên nhân và phương án giải quyết khác nhau. Yêu cầu tăng quota không bảo đảm Azure có ngay khả năng cấp phát VM theo vùng và SKU.

## 12. Phối hợp incident nội bộ với support request

Runbook phải làm rõ trách nhiệm của nhóm vận hành sau khi đã có ticket. Mở ticket không chuyển quyền điều phối incident cho Microsoft.

~~~mermaid
sequenceDiagram
    participant U as User / Synthetic probe
    participant IC as Incident Commander
    participant OPS as Technical team
    participant SUP as Azure Support
    U->>IC: Báo lỗi / alert
    IC->>OPS: Xác minh impact, thu evidence
    OPS-->>IC: Scope, UTC, mitigation và hypothesis
    IC->>SUP: Tạo support request với dữ kiện hiện có
    par Điều tra song song
      SUP-->>IC: Cần thêm thông tin / hướng chẩn đoán
      OPS->>OPS: Tiếp tục mitigation đã được duyệt
    end
    OPS-->>IC: Kết quả kiểm tra / recovery
    IC->>SUP: Cập nhật status và evidence mới
    IC->>U: Thông báo mức phục hồi và điều còn hạn chế
    SUP-->>IC: Phân tích bổ sung / resolution theo ticket
    IC->>IC: Hậu kiểm, action items và đóng hồ sơ
~~~

### 12.1. Trạng thái và nhịp cập nhật

Tổ chức nên duy trì **một incident record nội bộ** là nguồn sự thật về mức tác động và các quyết định. Support ticket lưu phần phối hợp với Microsoft.

Một bảng theo dõi nhỏ giúp giảm thất lạc:

| Trường | Giá trị mẫu |
| --- | --- |
| Internal incident ID | `INC-2026-0118` |
| Azure Support request ID | `<ticket-id>` |
| Internal priority | `P1` |
| Azure support severity | `mức đã chọn và xác nhận trong portal` |
| Ticket owner | `on-call / support liaison` |
| Last update UTC | `2026-11-20 10:45Z` |
| Next action | `Gửi operation ID của request lỗi` |
| Next update due | `thời điểm theo quy trình nội bộ` |
| Mitigation state | `Rollback hoàn tất, đang theo dõi` |

Khi gửi cập nhật cho Support, nêu **điều gì mới thay đổi**, khoảng thời gian và kết quả: “Sau rollback tại 10:17 UTC, error rate giảm từ 28% còn dưới ngưỡng SLO; vẫn cần xác minh 503 có liên quan event nền tảng hay không.” Tránh gửi nhiều log trùng lặp mà không nêu ý nghĩa.

### 12.2. Khi cần escalation thêm

Xem xét escalation khi incident vượt mục tiêu khôi phục nội bộ, tác động tăng, bằng chứng mới cho thấy nguy cơ dữ liệu/bảo mật, hoặc tiến độ phối hợp không phù hợp với nhu cầu hiện tại. Cập nhật support ticket với **business impact mới**, tình trạng mitigation và availability của đội kỹ thuật. Các cách liên hệ hoặc escalations phụ thuộc hỗ trợ hiện có; không hứa rằng mức severity được tăng sẽ tự động khắc phục lỗi.

Nếu lỗi đang ảnh hưởng an toàn thông tin hoặc có dấu hiệu tấn công, phải kích hoạt cả **quy trình security incident của tổ chức**. Có thể cần kênh hỗ trợ/báo cáo bảo mật riêng; đừng chỉ xử lý như vấn đề hiệu năng.

### 12.3. Đóng hồ sơ và quản lý tri thức

Trước khi đóng ticket, lưu lại: mô tả nguyên nhân được xác minh (nếu có), thay đổi đã áp dụng, cách xác nhận lỗi hết, chi phí/tác động, link hướng dẫn hoặc giới hạn dịch vụ cần ghi nhớ. Nếu chưa xác nhận root cause, ghi **unknown / pending verification** và kế hoạch tiếp tục theo dõi; không “điền cho đủ”.

Dùng thông tin đã được phép chia sẻ để cập nhật runbook, dashboard, alerting và IaC. Giữ ticket ID và liên kết bằng chứng trong incident record để các ca trực sau truy tìm được lịch sử.

## 13. Đánh giá sau sự cố và cải tiến runbook

Sau khi hệ thống ổn định, làm **post-incident review** (PIR) dựa trên bằng chứng. Cách tiếp cận không quy lỗi cá nhân giúp tìm các điều kiện hệ thống thay vì kết luận “người trực chậm” hoặc “Microsoft lỗi”.

### 13.1. Mẫu hậu kiểm

~~~markdown
# Incident Review: <incident-id>

## Tác động
- Dịch vụ, region, đối tượng ảnh hưởng:
- Từ T_impact đến T_recovered (UTC):
- Các SLI/SLO hoặc giao dịch không đạt:
- Tính toàn vẹn dữ liệu / tác động bảo mật:

## Timeline UTC
| Time | Event | Evidence | Action/Decision |
| --- | --- | --- | --- |
| ... | ... | ... | ... |

## Nguyên nhân và yếu tố đóng góp
- Trigger:
- Điều kiện tồn tại trước sự cố:
- Hệ thống phát hiện/điều phối thế nào:
- Điều gì chưa đủ bằng chứng:

## Mitigation và phục hồi
- Phương án đã xét, đã thử và kết quả:
- Tại sao chọn biện pháp cuối:
- Rủi ro còn tồn tại và cách theo dõi:

## Azure Support
- Support request ID:
- Bằng chứng cung cấp:
- Phân tích hoặc hướng dẫn đã xác minh:

## Hành động khắc phục
| ID | Action | Owner | Deadline | Validation |
| --- | --- | --- | --- | --- |
| ... | ... | ... | ... | ... |
~~~

### 13.2. Biến phát hiện thành action có điều kiện đóng

| Phát hiện | Thay đổi đề xuất | Bằng chứng chấp nhận |
| --- | --- | --- |
| Cảnh báo 5xx đến trễ | Tạo synthetic transaction và alert theo SLI | Diễn tập một lỗi có kiểm soát, đo thời gian phát hiện |
| Nhầm subscription khi điều tra | Ghi tenant/subscription/resource ID trong runbook; lệnh đọc có scope rõ | Review runbook và kết quả tabletop đúng resource |
| Lỗi deployment do quota chỉ phát hiện khi release | Preflight quota và kiểm tra vùng/SKU trong pipeline | Pipeline cảnh báo trước triển khai, có test tình huống quá quota |
| Rollback bị chậm vì không biết migration tương thích | Thiết kế release rollback-safe, ghi checklist schema | Diễn tập rollback ở staging có dữ liệu đại diện |
| Support liên tục yêu cầu thêm timestamp/ID | Chuẩn hóa evidence package từ alert, tracing và Activity Log | Ticket thử nghiệm có đủ trường, không lộ secret |
| Lỗi phụ thuộc không được phân biệt với lỗi API | Thêm dependency metrics, distributed tracing | KQL và traces chỉ ra nơi phát sinh lỗi |
| Hệ thống khỏe nhưng ticket còn mở không ai theo dõi | Giao Support Liaison, lịch cập nhật và quy định đóng | Review incident xác nhận owner/closure evidence |

Đóng action khi **hành vi thực tế đã được xác minh**. Merge PR, thêm dashboard hoặc sửa một dòng runbook chưa đủ nếu chưa chứng minh bước đó giúp phát hiện/giải quyết tình huống tương ứng.

## 14. Diễn tập runbook định kỳ

Runbook viết xong nhưng không được kiểm tra sẽ nhanh lỗi thời khi Azure service, SKU, network, role hoặc kiến trúc thay đổi. Chọn mức diễn tập theo rủi ro:

1. **Tabletop:** Người trực nhận một alert giả định, đi qua quyết định, tìm resource ID/dashboard, xác định khi nào phải liên hệ Azure Support.
2. **Read-only drill:** Dùng môi trường test hoặc incident lịch sử, tái hiện các truy vấn Azure Monitor, KQL và Activity Log; xác minh quyền truy cập.
3. **Controlled failure injection:** Tạo lỗi kiểm soát ở staging (ví dụ tắt backend thử nghiệm, rollout phiên bản test lỗi) và thực hiện mitigation có rollback.
4. **Support-request simulation:** Soạn hồ sơ với log giả lập đã ẩn nhạy cảm, kiểm tra có đủ timestamp, correlation ID, impact và câu hỏi cụ thể trước khi dùng vào tình huống thật.
5. **Review:** Đo MTTD, thời gian xác minh impact, thời gian chọn mitigation, thời gian trở lại SLO, số bước cần liên hệ người không trực, và các hành động tài liệu chưa rõ.

Với bài diễn tập gây thay đổi, xác định owner, phạm vi staging, điều kiện dừng, dữ liệu synthetic, phương án rollback và tài nguyên tạm phải cleanup. Không cần gây ảnh hưởng production để chứng minh quy trình chẩn đoán; test môi trường cách ly đã có thể phát hiện nhiều thiếu sót.

### 14.1. Bảng chấm runbook

| Tiêu chí | Đạt khi |
| --- | --- |
| Dễ tìm và đúng phiên bản | On-call tìm được bản được duyệt, có owner và ngày rà soát |
| Scope chính xác | Nêu rõ subscription, resource group, region, dịch vụ và quyền |
| Trigger đo được | Metric/alert và ngưỡng có liên hệ với tác động nghiệp vụ |
| Chẩn đoán dựa trên dữ kiện | Có cách lấy log, metric, trace, Health và deployment history |
| Mitigation có kiểm soát | Có điều kiện, người duyệt, tác động, rollback, stop condition |
| Kiểm chứng end-to-end | Không chỉ nhìn trạng thái resource; kiểm tra giao dịch và dữ liệu |
| Hỗ trợ Microsoft đúng lúc | Biết khi nào mở ticket, severity phù hợp, data package an toàn |
| Hậu kiểm hữu ích | Có timeline, nguyên nhân/điều chưa biết, owner và bằng chứng cho action |

## 15. Bài thực hành tổng hợp: xây runbook và hồ sơ hỗ trợ cho ứng dụng Azure

**Bối cảnh:** Ứng dụng `orders-api` chạy ở subscription sản xuất trên Azure App Service, dùng Azure SQL, Key Vault, private networking và Application Insights. Từ 14:00 UTC, 20% yêu cầu `POST /orders` trả HTTP 503. Người trực nhận cảnh báo lúc 14:03 UTC. Không có thông báo lỗi nền tảng rõ ràng trong Azure Service Health; một deployment app settings vừa diễn ra lúc 13:55 UTC. Khách hàng chưa báo mất đơn nhưng giao dịch bị trễ.

**Yêu cầu:** Viết một runbook áp dụng được và một support request dự thảo **chưa gửi**. Mục tiêu vận hành do nhóm đặt ra là khôi phục thao tác đặt đơn trong 30 phút, tránh mất hoặc tạo trùng đơn đã xác nhận.

### Nhiệm vụ 1 — Hoàn thiện runbook

Từ mẫu mục 4 và mục 8, điền owner, liên kết dashboard/CI-CD, subscription và resource ID mẫu, điều kiện kích hoạt, phân quyền, lệnh read-only, cách kiểm tra deployment/app settings, database dependency và các nhánh rollback/scale/network investigation.

Chọn ít nhất **hai phép kiểm tra phân biệt giả thuyết**; ví dụ, “API mới lỗi” với “Azure SQL không đáp ứng”. Nêu điều kiện nào cho phép rollback, điều kiện nào buộc tạm dừng để data owner xác nhận.

### Nhiệm vụ 2 — Tạo evidence package

Với dữ liệu synthetic và timestamp UTC giả định, tổng hợp:

- T_impact, T_detected, các mốc thay đổi, mốc mitigation và T_recovered.
- Resource ID đúng cấu trúc, region, tier/SKU và endpoint bị lỗi.
- Metric error rate, p95 latency và dependency failure trước/sau thay đổi.
- Một operation/trace ID minh họa **được ghi rõ là giả định**, cùng log đã làm sạch secret và PII.
- Kết quả đối soát đặt đơn trước/sau recovery.

### Nhiệm vụ 3 — Soạn support request

Dùng mẫu mục 11, chọn đúng loại technical support, điền business impact, thời gian UTC, hành vi mong đợi/thực tế, những bước đã thử, workaround và **câu hỏi cần Microsoft giúp trả lời**. Nêu gói support/severity phải được xác minh theo subscription; không khẳng định một thời gian phản hồi cố định.

### Nhiệm vụ 4 — Đóng vòng học tập

Giả định rollback đã giúp tỷ lệ giao dịch thành công trở lại mục tiêu. Phân biệt **đã khôi phục dịch vụ** với **đã xác nhận root cause**. Viết đoạn PIR gồm timeline, phần chưa biết, ba action items có owner/validation và bước cập nhật runbook, monitoring. Soạn thông báo trạng thái ngắn cho stakeholder không chuyên kỹ thuật.

**Tiêu chí đạt:** Người khác có thể dùng runbook để xử lý cùng tình huống mà không phải đoán scope hoặc quyết định rủi ro; support ticket đủ bằng chứng để nhóm hỗ trợ bắt đầu chẩn đoán; dữ liệu nhạy cảm được che; kết quả được kiểm chứng bằng giao dịch nghiệp vụ và có hành động khắc phục được kiểm thử lại.

## 16. Những sai lầm cần tránh

| Sai lầm | Vì sao gây hại | Thay bằng |
| --- | --- | --- |
| Chỉ ghi “restart dịch vụ nếu lỗi” | Có thể che mất nguyên nhân, gây thêm downtime hoặc rủi ro state | Ghi bằng chứng/điều kiện restart, scope, approver và tiêu chí hậu kiểm |
| Kết luận Azure outage từ một HTTP 500 | 500 có thể do code, dependency hoặc cấu hình | So trace, Activity Log, Health và lỗi đa tài nguyên |
| Chỉ nhìn Azure Status công khai | Không phản ánh đủ thông tin riêng theo subscription/resource | Kết hợp Service Health, Resource Health và telemetry của ứng dụng |
| Gửi ticket ghi “Azure rất chậm, sửa giúp” | Không đủ dữ liệu để khoanh vùng | Ghi impact, region, UTC, resource ID, error code, steps và IDs |
| Dán toàn bộ log không kiểm soát | Có thể làm lộ credentials và dữ liệu người dùng | Chỉ gửi tập log liên quan đã redaction qua kênh chính thức |
| Giả định ticket sẽ tự xử lý incident | Bỏ lỡ mitigation và truyền thông nội bộ | IC giữ quyền điều phối, Support Liaison theo dõi ticket |
| Chọn severity cao nhất theo thói quen | Mức severity không phản ánh impact thực và tùy entitlement | Chọn theo business impact và gói hỗ trợ thực tế |
| Xem rollback thành công là đã tìm nguyên nhân | Lỗi có thể còn do điều kiện môi trường hoặc thay đổi khác | Viết hypothesis, thu bằng chứng và kiểm thử lại |
| Đóng ticket khi alert biến mất | Có thể còn backlog, mất đơn, lỗi âm thầm | Kiểm tra SLO, dữ liệu, queue, chi phí và ảnh hưởng còn lại |
| Runbook không có owner/phiên bản | Quy trình lỗi thời khi hạ tầng đổi | Review định kỳ và sau mọi incident hoặc thay đổi quan trọng |

## 17. Tổng kết kiến thức áp dụng

Một **runbook Azure** có ích khi xác định được trigger, người chịu trách nhiệm, phép đo từ người dùng, nguồn bằng chứng theo từng tầng, nhánh quyết định, thay đổi được phê duyệt và tiêu chí phục hồi. Một **support request Azure** có ích khi mô tả chính xác business impact, tài nguyên và scope, mốc UTC, error code/correlation ID, những phép kiểm tra đã thực hiện và câu hỏi cần chuyên gia Microsoft giải đáp.

Kết hợp hai phần tạo thành quy trình vận hành khép kín: **phát hiện → đánh giá tác động → điều tra → giảm tác động → phối hợp hỗ trợ → xác minh phục hồi → hậu kiểm và cải tiến**. Khi được diễn tập và cập nhật theo thay đổi kiến trúc Azure, runbook giúp đội vận hành phản ứng có bằng chứng, nhất quán giữa các ca trực và giảm rủi ro cho dữ liệu, bảo mật, hiệu năng cũng như chi phí.
