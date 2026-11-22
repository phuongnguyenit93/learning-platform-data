# Thu thập dữ liệu bằng Azure Monitor Agent và Data Collection Rule

Một hệ thống ứng dụng chạy trên ba máy ảo Azure Windows và hai máy ảo Linux. Đội vận hành muốn biết: có lỗi đăng nhập bất thường không, Windows Event Log nào báo lỗi dịch vụ, CPU tăng trong khoảng thời gian nào và dịch vụ trên Linux có ghi thông điệp Syslog cảnh báo không? Một nhóm khác muốn thu thập log ứng dụng tùy biến nhưng chỉ giữ những bản ghi hữu ích để không tăng chi phí Log Analytics. Nếu mỗi máy ảo được cấu hình thủ công, không có chuẩn chọn log, không có cơ chế cập nhật tập trung và không kiểm tra luồng dữ liệu sau khi cài agent, rất dễ gặp tình trạng **đã cài agent nhưng Log Analytics vẫn không có dữ liệu**, hoặc **thu thập quá nhiều dữ liệu gây tốn chi phí**.

**Azure Monitor Agent (AMA)** là thành phần thu thập dữ liệu trên các máy được hỗ trợ. **Data Collection Rule (DCR)** là cấu hình dạng tài nguyên Azure xác định **lấy nguồn dữ liệu nào, xử lý/biến đổi ra sao và gửi tới đích nào**. **Data Collection Rule Association (DCRA)** gắn DCR với một nguồn tài nguyên, ví dụ máy ảo, để agent nhận cấu hình phù hợp.

```text
Azure VM / Azure Arc-enabled server
   |
   | Azure Monitor Agent (AMA)
   |   - nhận cấu hình từ DCR association
   |   - thu thập nguồn đã khai báo
   v
Data Collection Rule (DCR)
   |
   +-- Data sources: Windows Events, Linux Syslog, performance counters,
   |                 custom text/JSON logs theo khả năng hỗ trợ
   |
   +-- Transform KQL (nếu cấu hình và hỗ trợ)
   |
   +-- Data flows: stream -> destination
   |
   v
Destination: Log Analytics workspace / đích khác được hỗ trợ
   |
   v
Azure Monitor Logs
   |
   +-- KQL: Event / Syslog / Perf / Custom tables
   +-- Workbooks, alerts, dashboards, investigations
```

Mấu chốt: **AMA, DCR, DCRA, DCE và Log Analytics workspace không phải năm tên gọi của cùng một đối tượng**. Chúng giải quyết các việc khác nhau, có vòng đời, quyền và điều kiện mạng khác nhau.

Bài học thuộc chương **Giám sát và quan sát hệ thống** của module `CLOUD_PROVIDERS_AZURE`. Module này tìm hiểu hệ sinh thái Microsoft Azure từ subscription, resource group, Microsoft Entra ID, mạng ảo, tính toán, lưu trữ và dữ liệu, rồi triển khai, giám sát, bảo vệ và kiểm soát chi phí một kiến trúc ứng dụng. Vì vậy bài sẽ đi từ **thiết kế tín hiệu cần thu thập** tới **cấu hình agent/rule, giám sát dữ liệu đến, bảo mật, tối ưu ingestion cost và xử lý sự cố**.

> Ví dụ dùng kiến trúc phổ biến cho Azure VMs/Arc-enabled servers và Azure Monitor Logs. Các tính năng, Azure CLI extension/API versions, loại data sources, kiểu endpoint, region, giá, quota, default values và điều kiện private link có thể thay đổi. Luôn đối chiếu môi trường thực, policy tổ chức và tài liệu sản phẩm trước triển khai Production. Lệnh và biểu mẫu có placeholder phải được thay bằng resource IDs thật, và mọi thao tác tạo/sửa/xóa chỉ được chạy trong môi trường được phê duyệt.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt Azure Monitor, Azure Monitor Logs, Log Analytics workspace, AMA, DCR, DCRA và DCE.
2. Mô tả **đường đi dữ liệu** từ Windows/Linux VM đến bảng Log Analytics.
3. Chọn nguồn thu thập **Windows Event Logs, Linux Syslog và performance counters** theo yêu cầu giám sát.
4. Hiểu phạm vi hỗ trợ của **custom log files**, DCR stream declarations và ingestion-time transformations.
5. Tạo DCR có data sources, destinations và data flows hợp lý.
6. Gắn DCR cho máy qua **DCR association** và xác minh AMA extension hoạt động.
7. Phân biệt **Azure Activity Log**, VM guest logs, diagnostic settings, metrics và application telemetry.
8. Hiểu khi nào **Data Collection Endpoint (DCE)** có liên quan tới cấu hình/ingestion và Azure Monitor Private Link.
9. Thiết kế triển khai nhất quán bằng Azure Policy, IaC và cơ chế quản trị thay đổi.
10. Sử dụng KQL truy vấn `Heartbeat`, `Event`, `Syslog` và `Perf`.
11. Tách lỗi **agent**, **association**, **DCR**, **workspace**, **network/identity** và **query**.
12. Tối ưu khối lượng ingest, transformations, retention và chi phí theo nguồn.
13. Bảo vệ dữ liệu log khỏi rò PII/secrets và giới hạn quyền quản trị.
14. Xây checklist Production, bài lab và quy trình xử lý sự cố.

## 2. Quan sát hệ thống cần những tín hiệu nào?

Quan sát hệ thống (observability) giúp suy luận về trạng thái của hệ thống từ dữ liệu vận hành. Ba nhóm tín hiệu thường được dùng:

| Tín hiệu | Câu hỏi trả lời | Ví dụ |
|---|---|---|
| **Logs** | Sự kiện gì đã xảy ra? Vì sao? | Event Windows, Syslog Linux, log ứng dụng. |
| **Metrics** | Độ lớn/tần suất thay đổi bao nhiêu? | CPU, memory, disk I/O, requests/sec. |
| **Traces** | Một request đi qua các services nào? | Distributed traces trong Application Insights/OpenTelemetry. |

Azure Monitor Agent chủ yếu tham gia **thu thập những loại dữ liệu guest OS được hỗ trợ**, không phải thay thế toàn bộ distributed tracing. Traces từ Java/.NET app thường dùng Application Insights/OpenTelemetry và đường xuất telemetry khác.

### Định nghĩa câu hỏi trước khi thu thập

Ví dụ người vận hành muốn:

- Phát hiện Windows service lỗi trong vòng 5 phút.
- Điều tra đăng nhập thất bại với phạm vi và quyền được phê duyệt.
- Theo dõi CPU trung bình 5 phút cho nhóm máy xử lý.
- Cảnh báo không nhận được heartbeat từ VM quá 15 phút.
- Phân tích Syslog liên quan tới SSH hoặc ứng dụng daemon.
- Dự báo Log Analytics ingestion để tránh tăng ngân sách bất thường.

Mỗi yêu cầu cần chỉ rõ **nguồn, field, độ trễ chấp nhận được, nơi lưu, quyền, retention, alert và chi phí**. Đừng thu thập mọi log cấp Debug trước rồi mới tìm use case.

## 3. Bản đồ các tài nguyên chính

| Thành phần | Vai trò | Nằm ở đâu? |
|---|---|---|
| **Azure Monitor Agent (AMA)** | Đọc dữ liệu guest OS/nguồn agent hỗ trợ và chuyển theo rules. | Extension/agent trên Azure VM, Arc-enabled server và một số môi trường được hỗ trợ. |
| **DCR (Data Collection Rule)** | Khai báo data sources, stream routing, transformations, destinations. | Azure resource `Microsoft.Insights/dataCollectionRules`. |
| **DCRA (Data Collection Rule Association)** | Gắn DCR vào nguồn tài nguyên như VM. | Association resource gắn với monitored resource. |
| **DCE (Data Collection Endpoint)** | Endpoint cho những kịch bản cấu hình/ingestion có yêu cầu, gồm một số private-link scenarios. | Azure resource riêng theo điều kiện dịch vụ. |
| **Log Analytics workspace** | Lưu/truy vấn log tables, áp governance và retention. | `Microsoft.OperationalInsights/workspaces`. |
| **Azure Policy** | Tự động gắn agent/DCR vào nguồn phù hợp ở quy mô lớn. | Assignment, definition, remediation. |
| **Azure Monitor Logs/KQL** | Query, alert và phân tích dữ liệu đã ingest. | Workspace, bảng và query engine. |
| **Diagnostic settings** | Định tuyến resource/platform logs/metrics khi resource hỗ trợ. | Cấu hình của từng Azure resource. |

### Ba hành động tách biệt

1. **Cài AMA** vào máy.
2. **Tạo DCR** mô tả collection.
3. **Tạo DCRA** liên kết máy với DCR.

Thiếu một trong ba bước có thể khiến không có dữ liệu kỳ vọng. Ngược lại, DCR có thể tồn tại mà chưa gắn cho máy nào.

## 4. Phân biệt nguồn log guest và Azure platform

Một lỗi thiết kế hay gặp là cho rằng AMA chịu trách nhiệm tất cả logs của Azure.

| Nguồn | Cơ chế điển hình | Bảng/đích |
|---|---|---|
| **Windows Event Logs trong guest OS** | AMA + DCR Windows Event Logs. | `Event` trong Log Analytics khi route tới workspace. |
| **Linux Syslog trong guest OS** | AMA + DCR Syslog; cần syslog daemon/nguồn phù hợp. | `Syslog`. |
| **OS performance counters** | AMA + DCR Performance Counters. | `Perf` hoặc đích/stream được hỗ trợ khác theo cấu hình. |
| **Custom text logs trên VM** | AMA custom logs + DCR theo loại file được hỗ trợ. | Custom table được cấu hình. |
| **Azure subscription Activity Log** | Activity Log export/diagnostic settings theo phạm vi. | Ví dụ `AzureActivity` nếu được gửi tới workspace. |
| **Azure resource logs** | Diagnostic settings hoặc pipeline nền tảng riêng. | Bảng resource-specific/legacy theo cấu hình. |
| **Application Insights traces** | App instrumentation/SDK/OTel. | Application telemetry tables theo workspace/service. |
| **AKS Container Insights** | Pipeline/agent/container monitoring được hỗ trợ riêng. | Các bảng Container Insights tương ứng. |

**DCR dành cho AMA không tự thu thập Activity Log của subscription.** Muốn điều tra thay đổi resource group/VM từ ARM, cần thiết kế đường đi cho Activity Log riêng.

## 5. AMA thay thế cách thu thập cũ trong nhiều kịch bản

Một số tài liệu hoặc hệ thống legacy có thể dùng **Log Analytics agent/Microsoft Monitoring Agent (MMA)** hoặc Linux OMS agent. Đây là thành phần cũ, cần xem tình trạng hỗ trợ và kế hoạch migration trong môi trường đang vận hành.

AMA đưa collection configuration vào **DCR được quản lý tập trung** và hỗ trợ các khả năng lựa chọn nguồn/định tuyến theo DCR, nhưng không đồng nghĩa mọi kịch bản legacy đều có bản thay thế 1:1.

### Cần kiểm tra khi di trú

- Machine OS/distribution có được AMA hỗ trợ không?
- Trước đây thu thập những sources/tables nào?
- Có dùng legacy workspace agent configurations không?
- Azure VM hay Arc-enabled machine?
- Custom app logs có cần đổi nguồn/format/table không?
- Các alerts/workbooks đang truy vấn bảng nào?
- Có collector khác thu cùng events gây nhân bản không?
- Phân quyền/network và đường data ingestion có thay đổi không?
- Có yêu cầu song song agent trong giai đoạn canary không?
- Khi nào gỡ đường thu thập cũ để tránh duplication?

Không xóa legacy agent khi chưa có bằng chứng **dữ liệu AMA mới đã đầy đủ và alert vẫn hoạt động**.

## 6. Kiến trúc thu thập từ Azure VM

Luồng đơn giản:

```text
Azure VM (Windows/Linux)
   |
   +-- OS emits events/counters
   |
   +-- AMA extension runs in guest OS
   |     |
   |     +-- gets effective collection config
   |     |    from DCR association(s)
   |     |
   |     +-- selects requested records
   |     +-- sends streams to monitoring pipeline
   |
   v
Azure Monitor ingestion
   |
   v
Log Analytics workspace
   |
   +-- Event / Syslog / Perf
   +-- Alerts, Workbooks, KQL
```

DCR không được “copy thủ công vào file cấu hình của agent” trong mô hình quản trị phổ biến. Agent lấy cấu hình tương ứng thông qua tài nguyên và association trên Azure.

### Một máy có thể tham gia nhiều quy tắc

Một VM có thể được liên kết với nhiều DCR trong giới hạn tính năng. Ví dụ:

- DCR A: Windows Event Logs.
- DCR B: Performance counters.
- DCR C: Custom application logs.

Điều đó có ích cho phân quyền giữa teams, nhưng có thể **thu lặp cùng dữ liệu** nếu nhiều rules có source/stream/destination chồng lấn. Không coi việc gắn hai DCR giống nhau là cơ chế dự phòng miễn phí.

## 7. DCR: bốn lớp cấu hình

Một DCR cho AMA có thể mô tả:

```text
DCR
 |
 +-- dataSources
 |     +-- windowsEventLogs
 |     +-- syslog
 |     +-- performanceCounters
 |     +-- logFiles / supported extensions
 |
 +-- streamDeclarations (khi cần custom streams)
 |
 +-- destinations
 |     +-- logAnalytics
 |     +-- other supported destinations as applicable
 |
 +-- dataFlows
       +-- from stream(s)
       +-- optional transformKql / outputStream
       +-- to named destination(s)
```

**Không phải DCR nào cũng có tất cả các khối này.** Ví dụ rule chỉ thu Windows Events không cần Syslog. Custom streams có thêm cấu trúc khai báo schema riêng. Điều kiện dùng transform có thể phụ thuộc loại nguồn/đích và API version.

### Quan hệ giữa stream và table

- **Stream** là dạng dữ liệu logic trong pipeline, ví dụ `Microsoft-WindowsEvent`.
- **Destination** là vị trí ghi, ví dụ một Log Analytics workspace.
- **Table** là nơi dữ liệu xuất hiện sau ingestion, ví dụ `Event`.

Không nhầm tên stream `Microsoft-WindowsEvent` với tên bảng `Event` khi viết KQL.

## 8. DCR Association: áp quy tắc vào đúng máy

Giả sử có:

```text
dcr-windows-baseline
    |
    +-- associated with vm-win-01
    +-- associated with vm-win-02

dcr-linux-baseline
    |
    +-- associated with vm-linux-01
    +-- associated with arc-linux-02
```

DCRA là liên kết từ resource được giám sát tới rule. Một VM Windows gắn nhầm Linux-specific DCR có thể không sinh dữ liệu như mong muốn.

### Nguyên tắc

1. DCR tạo thành công chưa đủ: phải xem **association thực tế**.
2. Resource ID dùng để liên kết phải trỏ đúng VM/Arc machine.
3. Agent phải có mặt và healthy trên nguồn.
4. DCR và data sources phải tương thích OS.
5. Destination phải đúng workspace/environment.
6. Resource/location constraints của DCR và monitored machine phải đáp ứng quy định hiện hành.
7. Azure Policy assignments/remediation có thể tự tạo associations; kiểm tra để tránh thao tác chồng chéo.
8. Sau khi đổi DCR, agent cần thời gian nhận và áp config; đo thay đổi bằng telemetry thay vì mong kết quả tức thì.

**Một DCRA không phải đường mạng**. Nó là cấu hình Azure resource; agent vẫn cần connectivity, identity và quyền/định tuyến phù hợp.

## 9. DCE: Data Collection Endpoint có luôn bắt buộc không?

**Không.** Một hiểu nhầm phổ biến là mọi DCR phải có DCE do người dùng tự tạo.

DCE là endpoint dùng trong **những tình huống cấu hình/ingestion** yêu cầu nó, ví dụ một số kiến trúc dùng **Azure Monitor Private Link Scope (AMPLS)**, điều kiện mạng riêng hoặc một số data ingestion scenarios. Một số DCR/API mới có đường ingest/endpoints riêng theo tính năng.

### Ma trận tư duy

| Kịch bản | Điều cần xác minh |
|---|---|
| AMA trên Azure VM, thu Windows Events/Perf qua tuyến mạng được hỗ trợ thông thường. | Có thể không cần tự tạo DCE; theo yêu cầu DCR/network thực tế. |
| AMA với Azure Monitor Private Link/AMPLS. | Kiểm tra DCE, association cấu hình và private DNS/network rules theo hướng dẫn hiện hành. |
| Logs Ingestion API trực tiếp từ ứng dụng. | Endpoint và DCR configuration cho API, authorization, stream schema; không nhầm với AMA. |
| Arc-enabled server sau firewall/proxy. | Kết nối agent/service endpoints, Arc requirements và các DCE/private networking constraints. |

DCE không phải nơi lưu logs; dữ liệu vẫn được route tới destinations. **Không tạo DCE chỉ vì thấy chữ “endpoint” trong bài học**, cũng không bỏ qua DCE nếu kiến trúc private link thực sự yêu cầu.

## 10. Chọn Log Analytics workspace và phạm vi quản trị

Workspace quyết định nhiều yếu tố:

- Region và data residency theo dịch vụ.
- Access control và mô hình RBAC.
- Data retention/table plans.
- KQL queries, workbooks, alerts.
- Ingestion/billing/commitment tier nếu có.
- Quản trị cross-team và multi-tenant.
- Network/private link và export.
- Incident forensics và audit.

### Dùng một workspace hay nhiều?

**Một workspace chung** có thể thuận lợi cho correlation và quản trị tập trung. **Nhiều workspace** có thể hỗ trợ boundary giữa môi trường/đơn vị/điều khoản pháp lý, nhưng khiến cross-workspace queries và vận hành phức tạp hơn.

Một DCR có thể route streams đến Log Analytics destinations theo API hỗ trợ, nhưng **không xem workspace như một bảng dữ liệu độc lập trên từng VM**. Cần quản trị quy tắc truyền tới workspace nào và ai có quyền query dữ liệu.

### Quy tắc scope

Không trộn log Production chứa PII vào workspace lab chỉ vì muốn giảm chi phí. Quyết định phải dựa trên **data classification, role, retention, residency, performance và budget**.

## 11. Chuẩn bị trước khi cài AMA và tạo DCR

Checklist:

1. Chọn Azure tenant/subscription/resource group đúng.
2. Kiểm tra Windows/Linux OS và VM/Arc support.
3. Xác định Azure VM, VM Scale Set hay Arc-enabled servers.
4. Quyết định workspace và region.
5. Xác định tín hiệu thật sự cần: Event, Syslog, Perf, custom logs.
6. Ước lượng khối lượng dữ liệu/ngày và độ trễ cần thiết.
7. Kiểm tra managed identity/agent requirements của môi trường.
8. Kiểm tra route mạng, TLS, DNS, firewall và private link.
9. Chọn data collection rule structure theo OS và nhu cầu.
10. Xác định ai được tạo/sửa DCR, DCRA và ai được query logs.
11. Thiết kế tags, owner, naming, IaC và rollout plan.
12. Có bộ truy vấn xác minh và mẫu event được phê duyệt.
13. Có rollback về DCR trước đó khi rule mới lọc sai.
14. Có policy cho dữ liệu nhạy cảm, retention và anomaly alerts.

**Preflight quan trọng:** một máy đang được quản lý bởi collector khác có thể đã có Syslog/Windows Events route tới workspace. Gắn AMA mà không tính nguồn cũ có thể tăng bill gấp đôi.

## 12. Cài Azure Monitor Agent trên Windows VM

Một hướng phổ biến trong Azure Portal:

1. Chọn VM Windows lab.
2. Vào vùng Extensions/Monitoring hoặc luồng thu thập Azure Monitor được hỗ trợ.
3. Cài hoặc xác minh extension **Azure Monitor Windows Agent**.
4. Xác nhận provisioning và health của extension.
5. Tạo DCR Windows có Windows Event Logs/Perf data sources.
6. Tạo association từ đúng VM tới DCR.
7. Xác minh workspace và quyền/network.
8. Tạo event test không nhạy cảm trong lab nếu cần.
9. Query bảng `Event`/`Perf` và heartbeat.
10. Theo dõi ingestion latency.

Tên extension trong Azure VM API thường là `AzureMonitorWindowsAgent` với publisher `Microsoft.Azure.Monitor`; **xác minh thông số/version/region được hỗ trợ trước khi dùng IaC**.

Không nhất thiết mọi trải nghiệm Portal đều cài agent cùng một bước tạo DCR; phải **kiểm tra trạng thái extension thực** chứ không đoán.

## 13. Cài AMA trên Linux và Azure Arc

Máy Linux có thể gửi Syslog/Perf thông qua AMA khi OS/agent được hỗ trợ. Với server ngoài Azure, Azure Arc-enabled Servers mang resource identity để quản lý extensions và DCR associations.

```text
Azure Linux VM / Arc-enabled Linux server
      |
      +-- AMA Linux agent
      +-- OS syslog daemon and logs
      +-- DCR association for Linux sources
      |
      v
Azure Monitor Logs
      |
      v
Syslog / Perf / supported custom tables
```

### Điểm cần lưu ý

- Với Linux, nguồn **Syslog** phải thực sự được hệ thống/daemon tạo ra theo cấu hình OS.
- Kiểm tra `rsyslog`/`syslog-ng` hoặc pipeline logging phù hợp distro; không sửa mọi config OS chỉ để “ép có log”.
- Linux performance counter names và OS support có thể khác Windows.
- AMA Linux extension tên phổ biến `AzureMonitorLinuxAgent`.
- Arc machine cần Arc connectivity, agent và policy/association phù hợp.
- DCR chỉ nhận dữ liệu **sau khi** agent/source hoạt động; nó không tái tạo log đã không được giữ.
- Agent gửi dữ liệu theo tuyến network được hỗ trợ; proxy/private link có thể cần cấu hình đặc biệt.

## 14. Windows Event Logs: chọn đúng channels và levels

Trên Windows, các event channels phổ biến:

- **Application**: lỗi ứng dụng/dịch vụ.
- **System**: service, driver, OS events.
- **Security**: đăng nhập, audit và sự kiện nhạy cảm, cần quyền/quy trình kiểm soát.
- **Custom application/provider channels**: theo phần mềm được cài đặt.

AMA/DCR Windows Event Logs có thể chọn events bằng **XPath expressions** theo contract của data source.

Ví dụ ý tưởng:

```text
Application!*[System[(Level=1 or Level=2 or Level=3)]]
```

Trong nhiều Windows Event Log schemas:

- Level 1: Critical.
- Level 2: Error.
- Level 3: Warning.

Đây là XPath query cho **Windows Event Log source**, không phải KQL dùng trên Log Analytics.

### Tại sao không lấy mọi events?

Security audit và verbose application events có thể tạo lượng dữ liệu rất lớn, ảnh hưởng chi phí và quyền riêng tư. Cần chọn event IDs/channels/severity phù hợp use case và retention.

### Cảnh báo

- Event log level/IDs phải kiểm chứng từ provider và mục tiêu giám sát cụ thể.
- Không thu Security logs vào workspace mà user không được phép truy cập.
- Dùng allowed channel/XPath syntax được AMA hỗ trợ, không mặc định mọi Windows event query expression đều hợp lệ.
- Với Windows Events từ AMA, bảng Log Analytics thường là `Event`, nhưng nếu dùng pipeline khác có thể gặp `WindowsEvent`. Query phải đúng table theo nguồn thực.

## 15. Performance Counters: mức đo và tần suất

Performance counters biểu diễn CPU, memory, disk và các signals từ guest OS.

Ví dụ Windows:

```text
\Processor(_Total)\% Processor Time
\Memory\Available MBytes
\LogicalDisk(_Total)\% Free Space
```

Data source thường cần:

- Danh sách `counterSpecifiers`.
- `samplingFrequencyInSeconds`.
- Stream/output tương ứng, ví dụ `Microsoft-Perf`.
- Destination và data flow.

### Chọn tần suất theo use case

- 60 giây có thể đủ cho capacity trends và nhiều cảnh báo vận hành.
- 10–15 giây có thể hữu ích với burst rất ngắn nhưng tăng volume.
- 5 phút có thể giảm chi phí nhưng bỏ sót các spike ngắn.

Đây là **đánh đổi kỹ thuật**, không phải ngưỡng mặc định của dịch vụ. Ngoài counter names, phải kiểm tra OS/locale và khả năng hỗ trợ của agent.

**Perf Logs** và **Azure Monitor Metrics** là hai đường lưu/giám sát có thể khác nhau. Không kết luận mọi counter trong DCR đều xuất hiện tại bảng `Perf` nếu DCR đã định tuyến sang một stream/destination khác.

## 16. Linux Syslog: facility và severity

Syslog cung cấp cấu trúc thông điệp gồm:

- **Facility**: loại nguồn như `auth`, `authpriv`, `daemon`, `syslog`, `local0` ...
- **Severity/level**: Debug, Info, Notice, Warning, Error, Critical, Alert, Emergency theo các định nghĩa liên quan.
- **ProcessName**/source và nội dung thông điệp.
- Timestamp, host và metadata.

Ví dụ kịch bản:

| Facility | Mục đích giám sát | Mức đề xuất thử |
|---|---|---|
| `authpriv` | Xác thực SSH/login. | Warning/Error trở lên hoặc policy audit chuyên biệt. |
| `daemon` | Dịch vụ nền. | Warning/Error/Critical. |
| `local0` | Syslog ứng dụng phát vào facility này. | Tùy application SLO. |
| `syslog` | Daemon/system logging. | Warning/Error trở lên. |

Đây chỉ là mẫu thiết kế. Việc lựa chọn facility và level phải dựa trên **source thực phát event**; có phân phối Linux khác nhau và logging pipeline không dùng syslog truyền thống.

**Không mặc định lọc chỉ Error là đủ cho security**: các events authentication quan trọng đôi khi có severity khác; hãy so với audit requirements của tổ chức.

## 17. DCR JSON minh họa cho Windows VM

Ví dụ **phần nội dung tài nguyên DCR** dùng trên một Windows VM lab. Đây là JSON data source/destination có cấu trúc để học; không phải ARM template đầy đủ hoặc lệnh triển khai copy-run.

```json
{
  "location": "eastus",
  "properties": {
    "dataSources": {
      "windowsEventLogs": [
        {
          "name": "application-critical-errors",
          "streams": ["Microsoft-WindowsEvent"],
          "xPathQueries": [
            "Application!*[System[(Level=1 or Level=2 or Level=3)]]"
          ]
        }
      ],
      "performanceCounters": [
        {
          "name": "cpu-and-memory",
          "streams": ["Microsoft-Perf"],
          "samplingFrequencyInSeconds": 60,
          "counterSpecifiers": [
            "\\Processor(_Total)\\% Processor Time",
            "\\Memory\\Available MBytes"
          ]
        }
      ]
    },
    "destinations": {
      "logAnalytics": [
        {
          "name": "la-ops",
          "workspaceResourceId": "/subscriptions/SUBSCRIPTION_ID/resourceGroups/RG_MONITOR/providers/Microsoft.OperationalInsights/workspaces/LAW_OPS"
        }
      ]
    },
    "dataFlows": [
      {
        "streams": [
          "Microsoft-WindowsEvent",
          "Microsoft-Perf"
        ],
        "destinations": ["la-ops"]
      }
    ]
  }
}
```

### Đọc cấu hình này

1. `windowsEventLogs` chỉ chọn Application Critical/Error/Warning.
2. `performanceCounters` lấy CPU/memory khoảng 60 giây/lần.
3. Cả hai streams chuyển vào named destination `la-ops`.
4. Workspace resource ID phải là ID thật được phép sử dụng.
5. DCR cần resource name, Azure API/version và association để agent dùng.
6. Cấu hình phải được kiểm tra với phiên bản resource provider/DCR service hiện hành.
7. DCR này **chỉ phù hợp Windows Event Logs**; không gắn cho Linux rồi kỳ vọng có dữ liệu.
8. Đổi DCR có thể làm thay đổi volume dữ liệu và alerts.

**JSON không chứa workspace shared keys, token hoặc connection strings.** DCR/resource platform xử lý cấu hình theo identity/network model được hỗ trợ.

## 18. DCR Syslog minh họa cho Linux

Một phần `dataSources` dùng cho Linux:

```json
{
  "dataSources": {
    "syslog": [
      {
        "name": "security-and-daemon",
        "streams": ["Microsoft-Syslog"],
        "facilityNames": [
          "auth",
          "authpriv",
          "daemon",
          "syslog"
        ],
        "logLevels": [
          "Warning",
          "Error",
          "Critical",
          "Alert",
          "Emergency"
        ]
      }
    ]
  }
}
```

Để thành DCR đầy đủ còn cần:

- `location` và resource metadata thích hợp.
- `destinations`, ví dụ Log Analytics.
- `dataFlows` mapping stream `Microsoft-Syslog` tới đích.
- Association tới Linux/Arc machines được hỗ trợ.
- AMA Linux và syslog source thực sự hoạt động.

**Không copy cấu trúc này rồi kỳ vọng tài nguyên DCR đã được tạo hoàn chỉnh.** Phần JSON trên chỉ minh họa selection của Syslog data source.

### Tác động của chọn facilities

Một DCR chỉ thu `daemon` sẽ không tự chứa tất cả `authpriv` events. Tương tự, nếu log app gửi vào `local0` nhưng rule không chọn `local0`, câu lệnh KQL không thể tìm lại những events chưa được ingest.

## 19. Data flows: định tuyến từ stream tới destination

DCR data flow mô tả đường đi:

```text
source windowsEventLogs
     -> stream Microsoft-WindowsEvent
     -> dataFlow
     -> destination la-ops
     -> table Event

source performanceCounters
     -> stream Microsoft-Perf
     -> dataFlow
     -> destination la-ops
     -> table Perf
```

Khi dùng custom streams, có thể cần `streamDeclarations` và `outputStream` để ánh xạ dạng input sang schema/table đích.

### Dễ nhầm

- **Source name**: ví dụ `cpu-and-memory`.
- **Stream name**: `Microsoft-Perf`.
- **Destination name**: `la-ops` trong DCR.
- **Workspace resource name**: `law-operations-prod`.
- **Log Analytics table**: `Perf`.

Chúng là năm tên có chức năng khác nhau. Nếu nhầm stream/destination, ingestion có thể bị từ chối hoặc không xuất hiện ở bảng mong đợi.

## 20. Ingestion-time transformations bằng KQL

Một DCR có thể áp dụng **KQL transformation tại ingestion** cho một số streams/destinations khi được hỗ trợ. Mục đích:

- Lọc events không cần thiết.
- Chọn các fields được phép giữ.
- Chuẩn hóa/cắt dữ liệu theo schema đích.
- Giảm volume và bảo vệ dữ liệu trước lưu trữ trong phạm vi tính năng hỗ trợ.

Ví dụ **mẫu biểu thức** cho Windows Events có trường `EventID`:

```kusto
source
| where EventID in (1000, 1001)
```

Trong DCR data flow, cấu hình có thể gồm:

```json
{
  "streams": ["Microsoft-WindowsEvent"],
  "destinations": ["la-ops"],
  "transformKql": "source | where EventID in (1000, 1001)"
}
```

**Lưu ý quan trọng:**

1. Đây là **ingestion-time KQL subset/contract**, không phải mọi lệnh KQL query đều được chấp nhận.
2. Cột đầu vào phải có trong stream schema tương ứng.
3. Output fields/types phải phù hợp output stream/table; với custom tables cần khai báo schema đúng.
4. Transformation chạy đối với **dữ liệu mới đi qua pipeline**, không sửa những records đã ingest trước đó.
5. Không nên xóa các trường cần điều tra sự cố hoặc theo nghĩa vụ audit.
6. Transformation có chi phí/tính năng riêng tùy tier/table plan.
7. Trước rollout, test những events sẽ bị loại và ảnh hưởng đến alerts.

**Lọc càng sớm càng tốt khi có đủ bằng chứng về nhu cầu**, nhưng không loại dữ liệu security/compliance chỉ để giảm hóa đơn mà chưa có phê duyệt.

## 21. DCR transformations và quyền riêng tư

Một số log ứng dụng vô tình chứa:

```text
2026-11-20T12:00:00Z INFO Login succeeded user=user@example.test
2026-11-20T12:01:00Z ERROR Payment failed card=4111-.... token=<redacted>
```

Tốt nhất là **không ghi secret/PII ngay ở nguồn**. Nếu ứng dụng đã có lỗi logging, ingestion transformation có thể hỗ trợ lọc hoặc ẩn một số trường theo khả năng hỗ trợ, nhưng không phải giải pháp bảo mật duy nhất.

### Vì sao không đủ?

- Dữ liệu thô đã tồn tại trên VM/app file.
- Agent vẫn phải đọc và truyền thông điệp tới pipeline.
- Field mới hoặc message format mới có thể vượt qua regex.
- Transformation sai có thể xóa bằng chứng điều tra.
- Một số log paths không đi qua DCR bạn nghĩ.
- Dữ liệu có thể đã được gửi tới service khác trước khi transform.

Cần kiểm soát cả **source logging, data classification, RBAC, network, retention và audit**. Không dựa vào một `replace_regex` duy nhất để chứng minh compliance.

## 22. Custom log files: khác với built-in streams

Với các ứng dụng ghi file text/JSON riêng trên VM, AMA có những tính năng **custom text/JSON log collection** dựa trên DCR khi được hỗ trợ.

Luồng tư duy:

```text
Application writes file
  /var/log/myapp/events.log
        |
        v
AMA custom log file source
        |
        +-- file path patterns
        +-- record boundaries / timestamp format
        +-- stream schema
        |
        v
DCR transformation
        |
        v
Log Analytics custom table
        |
        v
KQL query
```

### Checklist custom logs

1. AMA có quyền đọc file và thư mục không?
2. File path patterns đúng vị trí/ký tự hoa-thường?
3. Files rotate theo cách nào? Agent có đọc tiếp/new files không?
4. Mỗi record bắt đầu bằng timestamp/format như thế nào?
5. Multiline stacktrace cần ghép record theo khả năng hỗ trợ không?
6. Custom table/schema đã tồn tại hoặc được tạo đúng pipeline chưa?
7. Column `TimeGenerated` được lấy từ đâu và chuyển đúng UTC không?
8. Transformation output fields/types khớp table schema không?
9. File dữ liệu có PII/secrets cần loại ngay tại source không?
10. Log volume có giới hạn/budget/retention không?
11. DCR được association đúng VM không?
12. Test tại một VM trước khi gắn hàng trăm máy.

**Đừng giả định mọi binary log hoặc định dạng bất kỳ đều được AMA đọc trực tiếp**. Với ứng dụng viết tới stdout trong container hoặc gửi HTTP telemetry, có thể cần pipeline khác.

## 23. Custom tables, Logs Ingestion API và sự khác biệt

Có ít nhất hai luồng dễ nhầm:

**A. AMA custom file collection**

```text
VM file → AMA → DCR file source → transformation → workspace table
```

**B. Logs Ingestion API**

```text
Application/client → authenticated HTTP ingestion endpoint
                   → DCR/stream mapping → workspace table
```

Chúng có thể cùng dùng **DCR concepts**, nhưng:

- **AMA** cần agent và DCR association với máy.
- **Logs Ingestion API** gửi dữ liệu trực tiếp qua API, cần endpoint/authorization/schema riêng, không mặc định có AMA.
- Một số APIs/deployment models yêu cầu DCE; những cách mới có thể cung cấp ingestion endpoint theo DCR.
- Quyền tạo DCR, gọi Logs Ingestion API và query workspace có thể khác nhau.

**Không cho rằng cài AMA là điều kiện bắt buộc của mọi custom table**, và cũng không cho rằng Logs Ingestion API sẽ tự đọc file trên VM.

## 24. DCR và Azure Policy để triển khai hàng trăm máy

Một tổ chức có 500 Azure VMs thì không nên cấu hình thủ công từng máy. Azure Policy có thể giúp:

- Audit máy thiếu AMA extension.
- Deploy extension được yêu cầu qua policy phù hợp.
- Tạo DCR associations cho machines theo scope/tags/OS.
- Theo dõi compliance.
- Chạy remediation với managed identity/roles được cấp phù hợp.
- Duy trì cấu hình baseline khi có VM mới.

```text
Management group / subscription
       |
       v
Azure Policy assignment
       |
       +-- Identify matching machines
       +-- Deploy AMA extension if required
       +-- Associate correct DCR
       |
       v
Compliance + remediation + monitoring
```

### Điều kiện quan trọng

- Policy definition/initiative phải đúng loại resource và OS.
- Scope, exclusions và tags không được nhầm lab/Production.
- Policy identity phải có quyền triển khai extensions/associations.
- Managed identity riêng của guest machine/Arc phải đáp ứng yêu cầu agent.
- Kết quả `Compliant` không thay thế việc xác minh **dữ liệu thực đã đến workspace**.
- Policy remediation có thể chạy trễ hoặc bị lỗi; cần audit.
- Một policy khác cũng có thể tạo association gây trùng streams.

**IaC/Azure Policy quản lý trạng thái mong muốn; KQL và telemetry xác nhận hệ thống đang thu thập thật**.

## 25. Đặt tên, tags và ownership

Một quy tắc đặt tên dễ kiểm soát:

```text
dcr-win-prod-baseline
dcr-linux-prod-security
dcr-win-staging-perf
law-platform-prod
dce-monitor-private-prod
```

Tags nên ghi:

- `environment`, `owner`, `costCenter`.
- `dataClassification` và `retentionPolicy`.
- `ruleVersion` hoặc commit hash IaC.
- `ticketId` hoặc change request.
- `sourceOS` và workload group.

**Không đặt username, access token, service password hoặc PII trong tags**. Tags và resource names có thể hiển thị trong inventory/audit với quyền rộng hơn nội dung log.

### Quyền sở hữu

Nên quy định team:

- Platform team sở hữu base AMA extensions/network.
- Observability team sở hữu DCR baseline và Log Analytics schema.
- Application team sở hữu custom log format.
- Security team phê duyệt Security logs/PII/retention.
- Finance/FinOps theo dõi ingest volume và cost anomalies.

## 26. Triển khai qua Azure Portal: quy trình lab

Trong subscription được phê duyệt:

1. Tạo hoặc chọn **Log Analytics workspace** lab.
2. Chọn **Azure VM Windows/Linux** lab đã có sự kiện.
3. Kiểm tra OS support và cài AMA extension nếu chưa có.
4. Vào **Azure Monitor → Data Collection Rules**.
5. Tạo DCR với platform Windows hoặc Linux phù hợp.
6. Chọn một data source nhỏ (Windows Application errors hoặc Linux daemon Syslog).
7. Chọn workspace destination theo môi trường.
8. Liên kết máy bằng DCR association theo wizard/luồng phù hợp.
9. Nếu private networking đòi DCE/AMPLS, cấu hình và xác minh DNS/network theo tài liệu.
10. Xem Azure resource status, AMA extension provisioning và associations.
11. Chờ thời gian ingestion hợp lý, không coi vài giây đầu chưa có log là lỗi chắc chắn.
12. Dùng KQL xác minh dữ liệu trong đúng workspace/table.
13. Ghi lại lượng dữ liệu và alert sớm nếu volume vượt dự tính.
14. Kiểm tra permissions, retention và chính sách PII.
15. Chỉ sau khi canary PASS mới nhân rộng rule.

**Không sửa dữ liệu hoặc cấu hình Production để tạo “event test” tùy tiện.** Dùng VM lab và loại event được phê duyệt.

## 27. Azure CLI: kiểm tra DCR, workspace và AMA extension

Những lệnh sau **chỉ đọc metadata** trong môi trường đã đăng nhập; chúng không tạo/sửa resources.

```bash
RG="rg-observability-lab"
VM="vm-win-lab"
DCR="dcr-win-lab"
LAW="law-lab"

az account show \
  --query "{Name:name,Subscription:id,Tenant:tenantId}" \
  --output table

az monitor data-collection rule list \
  --resource-group "$RG" \
  --output table

az monitor data-collection rule show \
  --resource-group "$RG" \
  --name "$DCR" \
  --query "{location:location,properties:properties}" \
  --output json

az vm extension list \
  --resource-group "$RG" \
  --vm-name "$VM" \
  --output table

az monitor log-analytics workspace show \
  --resource-group "$RG" \
  --workspace-name "$LAW" \
  --query "{Name:name,Location:location,Id:id}" \
  --output json
```

Các subcommands/arguments cần đúng **Azure CLI/Azure Monitor extension** được cài ở môi trường thực. Nếu thiếu lệnh, xem CLI help/capability được tổ chức hỗ trợ; không tự chạy installation/script lạ trên máy Production.

### Kiểm tra DCRA

DCR associations là **child resources gắn với monitored VM/Arc resource**, không phải một thuộc tính trong `properties.dataSources` của DCR. Có thể kiểm tra qua Portal hoặc câu lệnh/API association được phiên bản CLI hỗ trợ; cần lấy **VM resource ID** chính xác.

**Không kết luận DCR không có consumers chỉ vì danh sách DCR không hiển thị tên máy**. Phải kiểm tra các associations.

## 28. Khái niệm IaC cho DCR và DCRA

Đồ thị triển khai IaC:

```text
Resource group
   |
   +-- Log Analytics workspace
   |
   +-- Data Collection Rule
   |      +-- dataSources
   |      +-- destinations
   |      +-- dataFlows
   |
   +-- VM extension AMA (on target VM)
   |
   +-- Data Collection Rule Association (on VM resource)
   |
   +-- optional DCE/AMPLS networking
```

DCR và DCRA nên được khai báo qua **ARM/Bicep/Terraform** hoặc chính sách được phê duyệt. IaC cần:

1. Resource IDs theo đúng subscription/resource group.
2. Regions và constraints được hỗ trợ.
3. Managed identities/role assignments đủ scope.
4. Source OS và stream/schema phù hợp.
5. DCRA parent resource ID chính xác.
6. Có dependency ordering hoặc điều kiện readiness.
7. Không ghi workspace keys/secrets trong repo.
8. Có plan/diff preview và code review.
9. Có rollback và policy cho drift.
10. Có post-deployment KQL smoke test.

**Deploy success không chứng minh data ingestion success**; IaC chỉ thiết lập cấu hình mong muốn.

## 29. KQL xác minh Heartbeat

Với môi trường AMA có Heartbeat data được hỗ trợ, truy vấn:

```kusto
Heartbeat
| where TimeGenerated > ago(1h)
| summarize LastHeartbeat=max(TimeGenerated) by Computer, OSType
| order by LastHeartbeat desc
```

### Đọc kết quả

- `Computer`: máy phát heartbeat theo dữ liệu được ingest.
- `LastHeartbeat`: lần cuối workspace nhận bản ghi có `TimeGenerated` tương ứng.
- `OSType`: nhãn hệ điều hành khi field có sẵn.

**Heartbeat không chứng minh tất cả DCR streams đang chạy**. Một VM có Heartbeat nhưng không có `Event` vì XPath rule không chọn event nào hoặc DCRA/data source bị sai.

### Đừng báo động sai

VM lab có thể đang deallocated hoặc vừa được tạo, nên chưa có Heartbeat. Query phạm vi 1 giờ có thể quá ngắn/dài tùy workload. Khi dùng alert absence, cần danh sách máy **expected to be alive** độc lập với chính dữ liệu Heartbeat; nếu truy vấn chỉ chọn máy đã có heartbeat, máy mất hẳn có thể biến mất khỏi kết quả thay vì xuất hiện với count=0.

## 30. KQL xác minh Windows Events

```kusto
Event
| where TimeGenerated > ago(2h)
| project TimeGenerated, Computer, EventLog, EventID,
          EventLevel, Source, RenderedDescription
| order by TimeGenerated desc
| take 50
```

Để thống kê:

```kusto
Event
| where TimeGenerated > ago(24h)
| summarize EventCount=count() by Computer, EventLog, EventLevel
| order by EventCount desc
```

**Một bảng trống có nhiều khả năng giải thích**:

- Không có event trùng XPath trong khoảng thời gian.
- DCRA chưa áp cho VM.
- AMA extension không healthy.
- Data flow/destination sai.
- Workspace/query time range sai.
- Ingestion bị trễ.
- Logs route tới workspace khác.
- Cột/bảng khác nếu đang dùng pipeline không phải AMA.

Không mở toàn bộ Security Events vĩnh viễn chỉ để “làm cho bảng có dữ liệu”.

## 31. KQL xác minh Linux Syslog

```kusto
Syslog
| where TimeGenerated > ago(2h)
| project TimeGenerated, Computer, Facility,
          SeverityLevel, ProcessName, SyslogMessage
| order by TimeGenerated desc
| take 50
```

Nhóm theo facility/severity:

```kusto
Syslog
| where TimeGenerated > ago(24h)
| summarize Events=count() by Computer, Facility, SeverityLevel
| order by Events desc
```

Nếu không thấy Syslog:

1. VM có chạy Linux và AMA tương thích không?
2. Syslog daemon có tạo/forward messages không?
3. `facilityNames` đã chọn đúng facility của log source chưa?
4. `logLevels` có loại mất severity đang kiểm tra không?
5. DCR data flow mapping tới `Microsoft-Syslog` đúng không?
6. DCRA đã gắn vào machine resource ID chưa?
7. Có connectivity/identity/network lỗi không?
8. Query đúng workspace/TimeGenerated range chưa?

## 32. KQL xác minh Performance Counters

```kusto
Perf
| where TimeGenerated > ago(4h)
| where CounterName == "% Processor Time"
| summarize AvgCpuPct=avg(CounterValue)
    by Computer, bin(TimeGenerated, 5m)
| order by TimeGenerated desc
```

Để kiểm tra những counters thực sự được ingest:

```kusto
Perf
| where TimeGenerated > ago(2h)
| summarize Samples=count() by ObjectName, CounterName,
          InstanceName, Computer
| order by Samples desc
```

Các cột/thống kê nêu trên áp dụng cho bảng `Perf` theo schema tương ứng. Nếu DCR route performance metrics sang đích/stream khác, cần query đúng nơi dữ liệu đến.

### Lỗi diễn giải CPU

- `% Processor Time` có instance `_Total` hoặc per-core tùy nguồn.
- Windows/Linux counters không hoàn toàn tương đương.
- CPU trong Azure Monitor platform metric của VM có thể khác guest OS measurement do lấy theo tầng khác.
- `CounterValue` cần xem unit và instance trước khi tính ngưỡng.
- Average 5 phút có thể che spike 10 giây.

## 33. Ingestion latency và TimeGenerated

Một event có thể xảy ra tại `10:00` nhưng hiện trên Log Analytics lúc `10:03` vì:

- Agent batching/buffering.
- Chậm cấu hình hoặc network.
- Data collection pipeline queue.
- Source timestamps khác UTC/time zone.
- Workload overload/backpressure.

Cần phân biệt:

- **Event time / TimeGenerated**: thời điểm event được ghi nhận theo schema/logic nguồn.
- **Ingestion time**: lúc nền tảng nhận và lưu vào workspace.
- **Query time**: lúc operator chạy truy vấn.

Một ví dụ KQL đo độ trễ ingest:

```kusto
Event
| where TimeGenerated > ago(2h)
| extend IngestionLagSeconds =
    datetime_diff('second', ingestion_time(), TimeGenerated)
| summarize P95LagSeconds=percentile(IngestionLagSeconds, 95)
    by Computer
```

**Cẩn trọng:** hàm `datetime_diff` lấy hiệu theo thứ tự đối số; biểu thức trên cần được kiểm tra dấu hiệu và đặc điểm timestamp thực. Với dữ liệu có clock skew, lag âm hoặc bất thường cần xử lý riêng. Không coi `ingestion_time()` luôn có giá trị trong mọi bảng/pipeline và queries.

### Cách đơn giản hơn

Để tránh nhầm dấu, dùng:

```kusto
Event
| where TimeGenerated > ago(2h)
| extend Lag = ingestion_time() - TimeGenerated
| summarize P95Lag = percentile(Lag, 95) by Computer
```

Khi triển khai alert latency, kiểm tra type `timespan` và hỗ trợ của query/alert engine.

## 34. Tối ưu chi phí bằng collection scope

Các điểm quyết định volume:

1. Bao nhiêu VMs/agents thu thập?
2. Mỗi VM có bao nhiêu DCR associations?
3. Windows channels/XPath filters rộng đến đâu?
4. Syslog facilities/levels nào được giữ?
5. Perf sampling mỗi 10/60/300 giây?
6. Custom log file growth mỗi ngày?
7. Có DCR transformations giúp lọc/cắt records không?
8. Có collectors/agents cũ làm nhân đôi ingestion không?
9. Log Analytics table plan và retention như thế nào?
10. Logs bị ingest vào nhiều workspaces?
11. Những bảng/query nào thật sự được sử dụng trong alerts?
12. Có spikes Debug logs sau một lần deploy?

### Nguyên tắc thiết kế

- **Đo volume trước**: lấy 24–72 giờ dữ liệu đại diện nếu được phép.
- **Lọc có mục đích**: giữ events cần SLO/security/forensics.
- **Chọn đúng tần suất**: CPU mỗi 10 giây không phải lúc nào cũng cần.
- **Không thu trùng**: kiểm tra DCR overlap/legacy agents.
- **Retention theo mục đích**: không giữ mọi bảng như nhau.
- **Giới hạn dữ liệu nhạy cảm**: tránh secret/PII từ source.
- **So sánh cost với khả năng điều tra**: dữ liệu rẻ nhưng quá thiếu có thể gây incident tốn kém hơn.

**Không tối ưu bằng cách xóa log bảo mật bắt buộc khi chưa có Security/Compliance approval.**

## 35. Bảng đo volume và cost

Ví dụ mô hình ước tính:

- 50 Windows VMs.
- Mỗi VM tạo trung bình 200 MB log/ngày trước lọc.
- DCR lọc còn 25% theo workload benchmark.
- Giả sử không có duplication và thêm overhead không đáng kể.

```text
Raw candidate volume = 50 × 200 MB = 10,000 MB/day
Filtered estimate    = 10,000 × 25% = 2,500 MB/day
                     ≈ 2.5 GB/day (decimal units)

Monthly estimate for 30 days ≈ 75 GB
```

**Đây là ví dụ minh họa, không phải billing estimate chính xác.** Actual billed data phụ thuộc bảng, ingestion format, transformation, workspace plan, free/billable columns, region và pricing meter hiện hành.

### Cost review table

| Hạng mục | Nhóm tính phí cần kiểm tra |
|---|---|
| Log Analytics ingestion | Dữ liệu ingest/billing plan theo bảng/workspace. |
| Retention | Thời gian giữ và khả năng archive/restore theo plan. |
| Transformation | Tính năng và phí xử lý khi áp dụng. |
| Azure Monitor Agent | Kiểm tra cách tính phí của dịch vụ; dữ liệu/đích thường là driver lớn. |
| Azure Monitor Alerts/queries | Alert execution và các dịch vụ liên quan theo loại. |
| Networking/Private Link | DCE/AMPLS/networking/egress khi có. |
| Diagnostics | Log volume và Log Analytics workspace consumption. |

Không suy luận “AMA là miễn phí nên việc thu thập unlimited logs miễn phí”.

## 36. Retention và table plans

Log Analytics workspace/table có cơ chế retention và **table plans** (ví dụ các loại plans phù hợp Analytics, Basic, Auxiliary theo tính năng) với khả năng query, alert, ingestion và retention có thể khác nhau.

Cần quyết định:

- Event/security logs nào cần tra cứu nhanh?
- Custom application debug logs nào chỉ dùng thỉnh thoảng?
- Logs có cần incident correlation và KQL joins?
- Có yêu cầu audit 90 ngày/năm theo chính sách?
- Có archive/restore/search jobs được hỗ trợ?
- Có data residency hoặc legal hold?
- AI/analytics jobs có cần đọc dữ liệu cũ không?

**Không chọn Basic/Auxiliary plan chỉ vì thấy giá thấp** mà không kiểm tra query/alert limitations và nhu cầu phát hiện sự cố. Và cũng không giữ mọi bảng ở retention cao nhất theo thói quen.

## 37. RBAC: ai có quyền tạo DCR và ai đọc logs?

Hai lớp quyền:

| Tầng | Ví dụ thao tác | Quyền cần xem xét |
|---|---|---|
| **Control plane DCR** | Tạo/sửa/xóa Data Collection Rule. | Role/resource scope cho `Microsoft.Insights/dataCollectionRules`. |
| **Control plane association** | Gắn DCRA vào VM/Arc resource. | Quyền trên monitored resource và DCRA type. |
| **Agent extension** | Cài/sửa VM extension. | Quyền VM extension phù hợp, Azure Policy managed identity nếu tự động. |
| **Workspace management** | Tạo/sửa workspace/retention. | Azure resource/workspace management roles. |
| **Log query/data access** | Đọc bảng Event/Syslog/Perf. | Log Analytics data access/RBAC và resource-context/workspace-context theo thiết kế. |
| **Private networking** | Quản lý DCE/AMPLS/Private Endpoint. | Network/resource permissions. |
| **Security incident** | Query log nhạy cảm và audit. | Quyền ít nhất và access review. |

**Không cấp Owner/Contributor toàn subscription cho ứng dụng chỉ để đọc log**. Phân quyền deploy/modify DCR khác với permission xem dữ liệu đã ingest.

### Least privilege

- Agent/data flow dùng cơ chế auth của dịch vụ theo thiết kế; không phân phối workspace shared keys thủ công cho từng server nếu không cần.
- IaC identity chỉ cần quyền triển khai resource/scope liên quan.
- Security Event logs nên có policy truy cập chặt hơn application metrics.
- Secrets/PII trong logs là lỗi ở nguồn; RBAC chỉ là lớp giảm phạm vi ảnh hưởng.

## 38. Network, Private Link và DCE

Agent không ingest được nếu network/identity path bị chặn.

```text
VM AMA / Arc machine
     |
     +-- configuration/control path
     |
     +-- data ingestion path
     |
     v
Azure Monitor service endpoints
     |
     v
Log Analytics workspace

Private scenario:
  VNet/Private Endpoint/Private DNS
  + Azure Monitor Private Link Scope (AMPLS)
  + DCE association/config where required
```

Checklist:

1. Azure VM/Arc machine có route outbound hợp lệ không?
2. DNS phân giải đúng service hostnames từ **máy thực** không?
3. NSG/UDR/Azure Firewall/proxy có chặn traffic không?
4. TLS trust/inspection có làm hỏng connection không?
5. Có private link scope/endpoint và DCE đúng region/cấu hình không?
6. DCR/agent có được hỗ trợ trong mô hình private networking đã chọn không?
7. Workspace có thuộc phạm vi AMPLS/phương thức mạng đúng không?
8. Arc connectivity có đáp ứng điều kiện không?
9. Logs bị định tuyến qua workspace khác/đường public ngoài ý muốn không?
10. Có alert về ingestion failure sau thay firewall/DNS không?

**Private Endpoint không tự tạo DCR association và không giải quyết sai XPath**, tương tự cài AMA không tự mở firewall.

## 39. Security, compliance và dữ liệu nhạy cảm

Guest logs có thể chứa:

- Tên người dùng, email, IP address.
- File paths, machine hostnames và ứng dụng nội bộ.
- Token/session IDs hoặc connection string bị log nhầm.
- Thông tin thanh toán, lịch sử truy cập.
- Audit events với danh tính nhân viên.
- Stack traces chứa URL có query string nhạy cảm.

Các lớp bảo vệ:

1. **Source logging policy**: không log secrets/PII không cần thiết.
2. **DCR source selection**: giảm dữ liệu ngoài phạm vi.
3. **Transformation** khi cần và hỗ trợ, nhưng không dựa duy nhất vào đó.
4. **Network encryption**/private networking theo policy.
5. **Workspace access control** và audit queries.
6. **Retention/deletion** dựa trên classification.
7. **Log ingestion validation** chống định dạng/identity giả.
8. **SIEM/incident response** cho truy cập bất thường.
9. **Separate workspaces/tables** khi cần chia trust boundary.
10. **Export/backup policy** tránh copy dữ liệu nhạy cảm sang nơi ít được bảo vệ.

**Không gửi credential vào câu lệnh `logger` hay Windows Event Log để test AMA.** Dùng mẫu chuỗi giả lập không chứa bí mật.

## 40. Runbook: AMA đã cài nhưng Log Analytics trống

**Triệu chứng:** extension provisioning thành công, truy vấn `Event` hoặc `Syslog` không có bản ghi.

### Điều tra theo thứ tự

1. Xác nhận đang query **đúng workspace** và time range.
2. VM/Arc machine có thực sự online không?
3. AMA extension đã healthy, running, tương thích OS chưa?
4. DCR có tồn tại, JSON hợp lệ và stream source đúng OS không?
5. **DCRA có gắn đúng VM resource ID** không?
6. XPath/facility/level có chọn được event thật không?
7. DCR destination đúng workspace và data flow mapping không?
8. Có DCE/AMPLS/private networking requirements đang thiếu không?
9. Identity/agent configuration có lỗi không?
10. Có ingestion latency/chậm đồng bộ cấu hình?
11. Có transformation loại hết events?
12. Có custom table/schema mismatch nếu là custom log?
13. Có collector/route khác khiến dữ liệu nằm ở bảng khác?
14. Có thể phát sinh **một event lab an toàn** để xác minh end-to-end không?

### Không nên làm

- Không mở toàn bộ Event Security logs vô thời hạn chỉ để nhìn thấy dữ liệu.
- Không xóa/tạo lại workspace Production như bước debug đầu tiên.
- Không cấp Owner subscription khi gặp 403.
- Không đổi tất cả network rules cùng lúc vì khó tìm nguyên nhân.

## 41. Runbook: Windows Events đến nhưng Perf không có

**Triệu chứng:** `Event` có dữ liệu của VM, `Perf` rỗng.

Cách phân tích:

1. AMA và một phần DCR có hoạt động (Windows Events đã có).
2. DCR `performanceCounters` có khai báo không?
3. `streams` có `Microsoft-Perf` và data flow map tới Log Analytics không?
4. Counter specifiers có đúng tên, instance và OS/locale không?
5. Sampling interval có hợp lệ theo service constraints?
6. Có transformKql lọc hết Performance events không?
7. Perf records bị gửi sang stream/destination khác?
8. Query `Perf` có đúng thời gian/Computer filter không?
9. VM vừa restart/thay instance và chưa có đủ samples?
10. IAM/network có lỗi không — nhưng ít khả năng nếu mọi data đều dùng cùng tuyến và Event đang đến.

**Bài học:** agent healthy không chứng minh **từng data source trong rule** healthy.

## 42. Runbook: Syslog volume tăng đột biến

**Triệu chứng:** bill/ingestion tăng gấp ba sau khi rollout DCR Linux.

Điều tra:

1. DCR mới có `facilityNames=["*"]` hoặc logLevels bao gồm Debug/Info rộng không?
2. Có nhiều DCR thu cùng facility/same stream tới workspace không?
3. AMA và legacy collector có chạy song song không?
4. Application vừa bật verbose logging không?
5. Có log loop/retry storm ở daemon nào?
6. Có thay đổi số lượng máy/tags/Policy remediation?
7. Trong KQL `Syslog`, nhóm theo Computer/Facility/ProcessName để tìm nguồn?
8. Có custom table ingest duplicate ngoài `Syslog` không?
9. Ingestion-time transform có vô hiệu/không chạy như dự kiến?
10. Có volume spike thật do security incident đang xảy ra không?

### Khắc phục

- Trước tiên đánh giá **an toàn/security relevance** của volume tăng.
- Thu hẹp facility/severity và thêm application logging policy có owner.
- Loại duplicate DCR associations/legacy routes.
- Giữ audit logs bắt buộc.
- Tạo cost anomaly alert và dashboard theo nguồn.
- Test thay đổi trên canary VM trước khi nhân rộng.

Không “giảm chi phí” bằng cách bỏ các tín hiệu của một sự cố đang diễn ra.

## 43. Runbook: custom log không vào bảng đích

**Triệu chứng:** file `/var/log/myapp/events.log` liên tục tăng nhưng `MyApp_CL` không có record.

Điều tra:

1. AMA có quyền đọc directory/file không?
2. DCR custom log data source đang theo dõi đúng path pattern không?
3. File format/record boundary/timestamp có đúng capability không?
4. App dùng rotation rename/truncate có khiến agent mất vị trí đọc không?
5. Stream declarations có match input fields không?
6. Destination table/schema đã tạo và khớp output stream không?
7. `transformKql` có loại bỏ dữ liệu/throw conversion error không?
8. DCR association đúng VM/Arc resource chưa?
9. Destination workspace đúng region/name và có connectivity không?
10. Dữ liệu có quá dài hoặc vi phạm ingestion limits?
11. Query đúng bảng, workspace và time range chưa?
12. Có agent diagnostic/errors về file ingestion không?

Khắc phục theo **điểm đứt luồng** thay vì tạo một table mới khác tên để “xem có lên log không”.

## 44. Bài thực hành: thu Windows Events, Linux Syslog và Perf

**Bối cảnh lab:** một Windows VM và một Linux VM, một Log Analytics workspace. Các máy không xử lý dữ liệu thật; bạn được phép cài AMA và tạo DCR/DCRA trên Azure subscription lab.

### Kiến trúc mong đợi

```text
vm-win-lab ── AMA ── dcr-win-lab ──┐
                                  |
                                  v
                            law-ops-lab
                                  ^
                                  |
vm-linux-lab ─ AMA ─ dcr-linux-lab┘
                                  |
                           KQL + Workbook
```

### Nhiệm vụ

1. Ghi rõ VM IDs, OS, owners và workspace region.
2. Chọn một security-approved Windows Application event filter.
3. Chọn Windows CPU và memory counters; sampling 60 giây trong lab.
4. Chọn Linux Syslog facilities `daemon` và `authpriv` phù hợp distro.
5. Tạo DCR Windows có data source/streams/destination/dataFlows.
6. Tạo DCR Linux có Syslog source và cùng workspace destination.
7. Cài/xác minh AMA extensions trên hai máy.
8. Tạo DCRA từ Windows VM tới DCR Windows.
9. Tạo DCRA từ Linux VM tới DCR Linux.
10. Kiểm tra Azure resource state, OS support, DCE requirement và network.
11. Tạo vài events **không nhạy cảm** trong lab nếu chưa có nguồn phù hợp.
12. Query `Heartbeat` xem lastSeen của hai máy.
13. Query `Event` theo Computer và EventLog.
14. Query `Syslog` theo Facility/SeverityLevel.
15. Query `Perf` theo Computer/CounterName.
16. Ghi lại thời gian từ event tạo tới lúc thấy trong workspace.
17. Thử DCR selection khác trên canary, quan sát volume thay đổi.
18. Bổ sung `transformKql` đơn giản trong môi trường lab khi được hỗ trợ; xác minh không loại dữ liệu cần thiết.
19. Thử tạm bỏ association của một máy lab để thấy ảnh hưởng có kiểm soát; khôi phục ngay.
20. Test query đúng workspace nhưng sai time range để học cách loại trừ lỗi.
21. Mô phỏng không có Syslog matching facility; sửa chọn lọc.
22. Ghi bảng quyền cần cho tạo DCR, cài extension, query workspace.
23. Ước tính MB/ngày và monthly bill theo bảng/dữ liệu thực đo.
24. Tạo ít nhất một alert có ý nghĩa cho môi trường lab (ví dụ error count).
25. Dọn DCR/DCRA/VM lab đúng quyền, không xóa workspace/tài nguyên chia sẻ.

### Bằng chứng nghiệm thu

| Điều kiện | PASS khi |
|---|---|
| AMA installed | Hai máy có extension/agent healthy. |
| DCRA association | Windows/Linux VM trỏ tới DCR đúng OS. |
| DCR streams | WindowsEvent, Syslog và Perf được route đúng đích. |
| Workspace data | Các bảng có dữ liệu phù hợp khoảng thời gian thử nghiệm. |
| KQL | Trả được Computer, source và metrics cần thiết. |
| Alert | Có ngưỡng/cách diễn giải không tạo quá nhiều cảnh báo giả. |
| Security | Không có secrets/PII test trong logs. |
| Cost | Có báo cáo volume, dữ liệu giữ lại và chi phí ước lượng. |
| Cleanup | Không ảnh hưởng máy hoặc workspace Production. |

## 45. Bài tập thiết kế DCR cho 100 máy ảo

**Đề bài:** 60 Windows VMs, 40 Linux VMs thuộc ba môi trường dev/staging/prod. Security muốn nhận audit events; SRE cần CPU, memory và process errors; FinOps đặt ngân sách ingestion.

### Thiết kế tham khảo

| Nhóm | DCR | Association scope | Đích |
|---|---|---|---|
| Windows Production | `dcr-win-prod-core` | Prod Windows machines via Azure Policy. | `law-prod-ops`. |
| Linux Production | `dcr-linux-prod-core` | Prod Linux machines via Azure Policy. | `law-prod-ops`. |
| Security signals | Rule/stream được duyệt riêng. | Machines thuộc phạm vi security. | Workspace có RBAC/retention theo policy. |
| Dev/Staging | `dcr-nonprod-lite` chia theo OS khi cần. | Dev/staging matches. | `law-nonprod`. |

### Câu hỏi cần trả lời

1. Làm sao không thu thập cùng Windows Events hai lần nếu DCR core và security trùng filter?
2. Vì sao dev/staging không nhất thiết dùng cùng retention với prod?
3. Làm sao Azure Policy phân loại Windows vs Linux và không gắn nhầm DCR?
4. Kiểm tra bằng gì để biết policy `Compliant` nhưng VM vẫn chưa có dữ liệu?
5. Ai có quyền thay security audit filter?
6. Làm sao phát hiện billing tăng sau một ứng dụng bật DEBUG?
7. Khi có Private Link, những thành phần nào phải được kiểm chứng?
8. Kế hoạch rollback DCR phiên bản mới là gì?
9. Làm sao bảo đảm VM mới xuất hiện được giám sát?
10. Làm sao báo động VM mất heartbeat mà không bỏ qua máy đã biến mất khỏi query result?

**Đáp án định hướng:** tách quy tắc theo owner/OS/environment, tránh duplicate filters, dùng Azure Policy để gắn AMA/DCR, xác minh thực tế bằng KQL và application metrics, có Security approval cho log bắt buộc, kiểm soát cost theo workspace/table và bảo vệ pipeline mạng/identity.

## 46. Checklist Production

**Thiết kế tín hiệu**

- [ ] Có use case rõ cho WindowsEvent/Syslog/Perf/custom logs.
- [ ] Chọn fields, frequency, severity và data classification phù hợp.
- [ ] Không nhầm Azure Activity Log với VM guest logs.
- [ ] Có SLO ingestion latency/alert freshness.
- [ ] Không thu trùng sources giữa AMA và legacy agents/DCRs.
- [ ] Không log secrets/PII không cần thiết tại nguồn.

**Agent và DCR**

- [ ] AMA extension đúng OS/version và healthy.
- [ ] DCR dataSources, streams, dataFlows/destination có chủ đích.
- [ ] DCRA gắn đúng resource IDs, không sót VM/Arc servers.
- [ ] DCE/AMPLS áp dụng chỉ khi kiến trúc thực yêu cầu.
- [ ] KQL transformations/schema/custom tables được test.
- [ ] Có Azure Policy/IaC và drift remediation an toàn.
- [ ] DCR changes có PR, owner, canary và rollback.
- [ ] Không xem Deploy succeeded là ingestion succeeded.

**Security và mạng**

- [ ] RBAC deploy DCR/agent khác quyền query workspace.
- [ ] Workspace data access và retention theo classification.
- [ ] VM/Arc/agent identities và network requirements đã kiểm tra.
- [ ] TLS/DNS/NSG/Firewall/Private Link hoạt động từ máy thật.
- [ ] Không có token/workspace keys trong YAML, repo hoặc logs.
- [ ] Có audit access, permission changes và incident runbooks.
- [ ] Data residency/legal retention được xác nhận.

**Quan sát và chi phí**

- [ ] `Heartbeat` và source tables có smoke tests.
- [ ] Có alerts cho agent missing, ingestion lag và volume spikes.
- [ ] Có KQL dashboards theo Computer, Facility và CounterName.
- [ ] Ingestion volume, retention/table plans và billing được theo dõi.
- [ ] Có cảnh báo duplicate collection/Debug log growth.
- [ ] Runbooks cho Empty tables, Perf missing, Syslog spike, custom logs.
- [ ] Có owner vận hành và ngân sách cho Log Analytics.

## 47. Câu hỏi tự kiểm tra

**Câu 1.** Azure Monitor Agent và Data Collection Rule khác nhau thế nào?

**Đáp án:** AMA là thành phần thu thập dữ liệu trên nguồn được hỗ trợ; DCR là cấu hình chọn nguồn, transform và destination.

**Câu 2.** DCR đã được tạo nhưng chưa associate với VM thì máy có tự áp rule không?

**Đáp án:** Không. Cần DCRA/association hoặc cơ chế cấu hình nguồn phù hợp, cùng agent đã cài/đang chạy.

**Câu 3.** DCRA có phải workspace hoặc điểm cuối lưu log không?

**Đáp án:** Không. DCRA là liên kết giữa source resource và DCR.

**Câu 4.** DCE có luôn bắt buộc cho mọi AMA DCR không?

**Đáp án:** Không. Nó dùng trong các tình huống yêu cầu như một số private-link/configuration/ingestion scenarios.

**Câu 5.** Dữ liệu Windows Event Log từ AMA thường được query ở bảng nào?

**Đáp án:** `Event`, nếu data flow route theo stream/bảng chuẩn của AMA vào Log Analytics.

**Câu 6.** Linux Syslog thường vào bảng nào?

**Đáp án:** `Syslog`.

**Câu 7.** Windows performance counters qua `Microsoft-Perf` thường vào bảng nào?

**Đáp án:** `Perf`, nếu được route tới Log Analytics với data flow tương ứng.

**Câu 8.** Cài AMA có tự đưa Azure subscription Activity Log vào workspace không?

**Đáp án:** Không. Activity Log export dùng cơ chế riêng như diagnostic settings.

**Câu 9.** Một VM có Heartbeat có nghĩa mọi logs/Perf đã được thu không?

**Đáp án:** Không. Heartbeat chỉ xác minh tín hiệu về agent/máy; từng stream/source cần kiểm tra riêng.

**Câu 10.** XPath cho Windows Events có phải KQL không?

**Đáp án:** Không. XPath chọn events ở Windows Event Log source, KQL query dữ liệu đã ingest.

**Câu 11.** DCR transformation có tự sửa events đã lưu trong workspace từ tuần trước không?

**Đáp án:** Không. Ingestion-time transformation áp cho dữ liệu mới đi qua pipeline.

**Câu 12.** Có thể dùng mọi KQL function khi viết `transformKql` không?

**Đáp án:** Không. Transformation dùng tập chức năng/contract được hỗ trợ, cần khớp input/output schema.

**Câu 13.** Một Syslog DCR chỉ chọn `daemon` có thu `authpriv` không?

**Đáp án:** Không nếu facility đó không được chọn bởi rule hoặc nguồn thu thập khác.

**Câu 14.** Vì sao không thu DEBUG logs mọi VM mặc định?

**Đáp án:** Có thể tạo volume/chi phí lớn, noise và tăng rủi ro lộ dữ liệu; cần use case/phê duyệt.

**Câu 15.** Có cần AMA để gửi dữ liệu qua Logs Ingestion API trực tiếp không?

**Đáp án:** Không nhất thiết; đây là hai pipeline khác nhau dù cùng có thể dùng DCR.

**Câu 16.** Một custom log file không vào table thì phải kiểm tra gì?

**Đáp án:** File permissions/path/format, AMA, DCR/DCRA, stream declarations, table schema/transform, network và query phạm vi.

**Câu 17.** Azure Policy báo Compliant có chắc workspace đã có Event records không?

**Đáp án:** Không. Phải query dữ liệu và kiểm tra source/agent/ingestion end-to-end.

**Câu 18.** Khi có nhiều DCR trên một VM có rủi ro gì?

**Đáp án:** Thu trùng cùng stream/source/destination, tăng volume, chi phí và tạo dữ liệu nhân bản.

**Câu 19.** Vì sao `Perf` có thể trống dù `Event` có dữ liệu?

**Đáp án:** Performance counters/dataFlow có thể chưa khai báo hoặc bị sai counter, stream, transformation hoặc time range.

**Câu 20.** DCR có thể lưu dữ liệu trực tiếp trong chính nó không?

**Đáp án:** Không. DCR mô tả collection/flow; destination như workspace là nơi dữ liệu được lưu.

**Câu 21.** `TimeGenerated` khác `ingestion_time()` thế nào?

**Đáp án:** Một bên biểu diễn thời điểm log event theo schema, một bên khi dữ liệu được ingest (nếu hàm được hỗ trợ).

**Câu 22.** Role quản lý DCR có tự là quyền đọc tất cả Log Analytics workspace tables không?

**Đáp án:** Không. Control plane và log data access là hai lớp permission.

**Câu 23.** Private Endpoint có thể thay thế DCRA không?

**Đáp án:** Không. Private networking giải quyết kết nối, DCRA giải quyết rule association.

**Câu 24.** Khi AMA/Linux agent có lỗi mạng, bước đầu tiên là gì?

**Đáp án:** Kiểm tra trạng thái VM/agent, DNS/TLS/proxy/firewall/route và DCE/AMPLS nếu có; không tự sửa source selection để che lỗi mạng.

**Câu 25.** Vì sao cần retention policy?

**Đáp án:** Quản lý chi phí, nghĩa vụ pháp lý, privacy và khả năng truy vấn/điều tra theo thời gian.

**Câu 26.** Ingestion-time filter có thay thế việc không log secrets trong ứng dụng không?

**Đáp án:** Không. Dữ liệu nhạy cảm đã tồn tại ở nguồn và có thể đi qua nhiều pipelines khác.

**Câu 27.** Tại sao performance counter sampling mỗi 10 giây có thể đắt hơn mỗi 60 giây?

**Đáp án:** Tăng số lượng measurements/records và ingestion volume trong cùng thời gian.

**Câu 28.** Có thể xem Azure Monitor Logs là hệ thống lưu raw telemetry vô hạn, miễn phí không?

**Đáp án:** Không. Có quy tắc billing, retention/table plans, quotas và chi phí theo dịch vụ.

**Câu 29.** Kỹ thuật tốt nhất để xác nhận rollout AMA/DCR thành công là gì?

**Đáp án:** Kết hợp kiểm tra **extension + DCRA + DCR contents + connectivity + KQL data thực + alerts/volume**.

**Câu 30.** Nguyên tắc cốt lõi của bài?

**Đáp án:** **Thu đúng dữ liệu qua AMA, cấu hình bằng DCR, liên kết đúng DCRA, chọn đích/tần suất/transform có mục đích, kiểm chứng bằng KQL và quản trị quyền, mạng, retention cùng chi phí**.

## 48. Tổng kết và hướng áp dụng

Trong một hệ thống Azure có nhiều Windows/Linux VMs, **Azure Monitor Agent** tạo lớp thu thập trên máy, **Data Collection Rule** định nghĩa **data sources, streams, transforms và destinations**, còn **Data Collection Rule Association** là sợi dây nối đúng máy với rule. **Data Collection Endpoint** chỉ tham gia khi có yêu cầu network/configuration/ingestion tương ứng, không phải tài nguyên mặc định bắt buộc cho mọi DCR.

Tư duy triển khai cần được giữ theo thứ tự:

1. Đặt câu hỏi quan sát và SLO.
2. Chọn nguồn cần thu, bảo vệ dữ liệu nhạy cảm.
3. Tạo workspace và DCR phù hợp OS/stream/table.
4. Cài AMA và liên kết DCRA bằng cấu hình được quản trị.
5. Kiểm tra network, identity và các điều kiện DCE/private link.
6. Query dữ liệu thực bằng KQL để nghiệm thu.
7. Giám sát freshness, duplication, costs và data governance.
8. Dùng Azure Policy/IaC để mở rộng có kiểm soát.
9. Có runbook và rollback khi dữ liệu bị mất hoặc chi phí tăng.

**Một hệ thống quan sát đáng tin không được định nghĩa bởi số lượng log ingest, mà bởi khả năng trả lời đúng câu hỏi vận hành khi có sự cố, trong giới hạn bảo mật, độ trễ và chi phí đã cam kết.**
