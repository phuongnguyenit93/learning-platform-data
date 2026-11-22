# Thu thập và điều tra sự kiện với Microsoft Sentinel

> **Chương:** Bảo mật và tuân thủ  
> **Module:** CLOUD_PROVIDERS_AZURE — Khám phá hệ sinh thái Microsoft Azure từ subscription, resource group và Entra ID đến mạng ảo, dịch vụ tính toán, lưu trữ và dữ liệu; học cách triển khai, giám sát, bảo vệ và kiểm soát chi phí kiến trúc ứng dụng trên Azure.

## Mục tiêu bài học

Sau bài này, bạn có thể:

- Giải thích vai trò của **Microsoft Sentinel** trong giám sát an ninh và phản ứng sự cố trên Azure và các hệ thống khác.
- Xác định nguồn sự kiện cần thu thập, cách kết nối chúng vào môi trường Sentinel và cách kiểm tra chất lượng dữ liệu.
- Dùng **Kusto Query Language (KQL)** để khám phá sự kiện đăng nhập, thay đổi quyền và dấu hiệu bất thường.
- Phân biệt **log, alert, incident, entity, analytics rule, hunting** và **playbook**.
- Mô tả quy trình điều tra một incident từ tiếp nhận, xác minh, mở rộng phạm vi đến xử lý và tổng kết.
- Nhận diện những giới hạn về quyền truy cập, độ trễ log, quyền riêng tư, lưu giữ và chi phí.

## 1. Microsoft Sentinel giải quyết vấn đề gì?

Trong một ứng dụng triển khai trên Azure, dấu hiệu xâm nhập không nhất thiết nằm ở một nơi. Ví dụ, một tài khoản bị đánh cắp có thể tạo chuỗi sự kiện:

1. Nhiều lượt đăng nhập thất bại xuất hiện trong **Microsoft Entra ID**.
2. Một lần đăng nhập thành công diễn ra sau đó.
3. Tài khoản thực hiện thay đổi quyền truy cập đối với resource group.
4. Một máy chủ hoặc dịch vụ bắt đầu kết nối đến địa chỉ mạng bất thường.

Nếu chỉ nhìn Azure portal của từng dịch vụ, nhóm vận hành khó ghép các dấu vết thành câu chuyện thống nhất.

**Microsoft Sentinel** là giải pháp **SIEM** (*Security Information and Event Management*) và **SOAR** (*Security Orchestration, Automation and Response*) trên nền tảng đám mây. Nó giúp:

- **Thu thập và tập trung** tín hiệu bảo mật từ Azure, Microsoft 365, thiết bị, ứng dụng, hệ thống tại chỗ và dịch vụ bên thứ ba.
- **Phát hiện** hành vi đáng chú ý bằng quy tắc phân tích, truy vấn và các năng lực phát hiện tùy nguồn dữ liệu.
- **Liên kết và điều tra** các cảnh báo thành incident, làm rõ tài khoản, thiết bị, IP, tài nguyên và dòng thời gian.
- **Phối hợp phản ứng** qua automation rules và playbooks, có thể yêu cầu con người phê duyệt hành động nhạy cảm.

Trong mô hình triển khai phổ biến, dữ liệu được đưa vào một **Log Analytics workspace**; Sentinel dùng workspace và các tích hợp bảo mật để phân tích, điều tra. Một số khả năng, giao diện và nơi lưu trữ dữ liệu có thể thay đổi theo dịch vụ và cấu hình được Microsoft hỗ trợ tại thời điểm triển khai.

### So sánh các dịch vụ dễ nhầm lẫn

| Dịch vụ | Trọng tâm | Ví dụ |
| --- | --- | --- |
| **Azure Monitor / Log Analytics** | Thu thập, truy vấn và giám sát dữ liệu vận hành | Xem lỗi ứng dụng, hiệu năng VM, truy vấn log |
| **Microsoft Defender for Cloud** | Đánh giá tư thế bảo mật, khuyến nghị và khả năng bảo vệ workload | Phát hiện cấu hình yếu hoặc mối đe dọa đối với tài nguyên được bảo vệ |
| **Microsoft Entra ID** | Xác thực, quản trị danh tính và quyền truy cập | Sign-in logs, audit logs, Conditional Access |
| **Microsoft Sentinel** | Tập trung tín hiệu bảo mật, phát hiện, điều tra và phối hợp phản ứng | Phát hiện chuỗi đăng nhập thất bại và thay đổi quyền đáng ngờ |

Các dịch vụ bổ sung cho nhau. Sentinel có thể tiếp nhận dữ liệu hoặc cảnh báo từ những dịch vụ còn lại, nhưng **việc bật Sentinel không có nghĩa tất cả nguồn log tự động được thu thập**.

## 2. Hiểu đúng các khái niệm trong luồng điều tra

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Event / log record** | Bản ghi một hoạt động tại thời điểm cụ thể | Người dùng đăng nhập thất bại |
| **Data connector** | Cách kết nối nguồn dữ liệu với môi trường Sentinel | Kết nối Microsoft Entra ID |
| **Log Analytics table** | Bảng chứa bản ghi để truy vấn bằng KQL trong mô hình workspace | `SigninLogs`, `AzureActivity` |
| **Analytics rule** | Điều kiện phân tích tạo cảnh báo khi dữ liệu đáp ứng tiêu chí | Từ 10 lần đăng nhập thất bại trong 15 phút |
| **Alert** | Tín hiệu cho thấy quy tắc hoặc sản phẩm phát hiện một hoạt động cần xem xét | “Nhiều lượt đăng nhập thất bại” |
| **Incident** | Hồ sơ điều tra, có thể nhóm một hoặc nhiều alert và dữ liệu liên quan | “Khả năng tài khoản bị xâm nhập” |
| **Entity** | Đối tượng được trích ra để điều tra liên kết | Account, IP address, host |
| **Hunting** | Chủ động truy vấn tìm dấu hiệu chưa được quy tắc phát hiện | Tìm tài khoản bất thường trong 7 ngày |
| **Automation rule** | Quy tắc xử lý sự kiện, điều phối bước công việc | Gán incident cho nhóm trực |
| **Playbook** | Workflow tự động, thường dựa trên Azure Logic Apps | Gửi thông báo, tạo ticket, bổ sung ngữ cảnh |

**Log không đồng nghĩa với alert; alert không đồng nghĩa với incident.** Một log có thể hoàn toàn bình thường. Analytics rule thường chỉ tạo alert khi thỏa điều kiện; nhiều alert có thể được gom thành một incident để tránh xử lý lặp.

## 3. Kiến trúc thu thập và phát hiện

~~~mermaid
flowchart LR
    A["Microsoft Entra ID\nSign-in / Audit"]
    B["Azure subscription\nActivity / Resource logs"]
    C["VM, Firewall, Hybrid\nWindows / Syslog / CEF"]
    D["Microsoft Defender\nAlerts / Incidents"]
    E["Data connectors\nDiagnostic settings / AMA / API"]
    W["Log Analytics workspace\nvà dữ liệu liên quan"]
    Q["KQL / Analytics rules\nHunting / Workbooks"]
    I["Alerts → Incidents"]
    R["Triage → Investigation\n→ Response"]
    P["Automation rules\nLogic Apps playbooks"]

    A --> E
    B --> E
    C --> E
    D --> E
    E --> W
    W --> Q
    Q --> I
    I --> R
    I --> P
    P --> R
~~~

Sơ đồ mô tả luồng làm việc thường gặp; một số tích hợp sản phẩm và kiểu dữ liệu có thể có cách kết nối hoặc cơ chế đồng bộ riêng.

Các thành phần quan trọng:

1. **Nguồn dữ liệu:** nơi phát sinh sự kiện. Phải xác định dịch vụ nào có log cần thiết và khả năng xuất log của dịch vụ đó.
2. **Đường thu thập:** data connector, diagnostic settings, Azure Monitor Agent (AMA), Data Collection Rule (DCR) hoặc cơ chế tích hợp khác.
3. **Kho dữ liệu và truy vấn:** Log Analytics workspace chứa những bảng tương ứng; truy vấn KQL giúp tìm và kết hợp tín hiệu.
4. **Phát hiện:** analytics rules và cảnh báo từ các sản phẩm tích hợp chuyển những tín hiệu đáng chú ý vào luồng xử lý.
5. **Điều tra và phản ứng:** người phân tích xác minh incident, tìm tác động, thực hiện biện pháp ứng phó theo thẩm quyền và ghi nhận kết quả.

### Chọn nguồn log theo câu hỏi điều tra

| Câu hỏi an ninh | Nguồn gợi ý | Bảng KQL thường gặp |
| --- | --- | --- |
| Ai đăng nhập? Thất bại vì sao? | Microsoft Entra sign-in logs | `SigninLogs` |
| Ai đã thay đổi danh tính, nhóm, vai trò Entra? | Microsoft Entra audit logs | `AuditLogs` |
| Ai tạo, xóa, cập nhật tài nguyên Azure ở control plane? | Azure Activity Log | `AzureActivity` |
| Máy chủ Windows có sự kiện đăng nhập/quyền hệ thống nào? | Windows Security Events qua AMA | `SecurityEvent`; bảng thực tế tùy connector/cấu hình |
| Thiết bị Linux hoặc hệ thống gửi Syslog ghi nhận gì? | Syslog qua AMA | `Syslog` |
| Thiết bị mạng gửi Common Event Format có tín hiệu nào? | CEF qua cơ chế thu thập hỗ trợ | `CommonSecurityLog` |
| Công cụ bảo vệ endpoint có cảnh báo gì? | Tích hợp Microsoft Defender hoặc nguồn EDR khác | Tùy connector và mô hình tích hợp |

**Azure Activity Log khác Entra sign-in log.** Activity Log mô tả hoạt động quản lý tài nguyên Azure (control plane), chẳng hạn tạo VM hoặc thay đổi role assignment ở phạm vi Azure RBAC. Sign-in log trả lời câu hỏi xác thực danh tính; cả hai thường cần thiết khi điều tra việc lạm dụng tài khoản.

Đối với hoạt động **bên trong** một dịch vụ, như truy cập blob hoặc đọc bí mật, phải kiểm tra khả năng bật **resource logs** tương ứng. Không nên mặc định Azure Activity Log ghi lại mọi thao tác dữ liệu (data plane).

## 4. Chuẩn bị môi trường Sentinel

### 4.1. Xác định phạm vi và quyền

Trước khi cấu hình, hãy trả lời:

- Cần theo dõi **subscription, resource group, ứng dụng, tenant** và nguồn bên ngoài nào?
- Ai là người chịu trách nhiệm vận hành SOC, quản lý quy tắc, kiểm soát chi phí và bảo vệ dữ liệu?
- Dữ liệu có yêu cầu về **vị trí lưu trữ, thời gian lưu giữ, quyền riêng tư** hay không?
- Nguồn nào được ưu tiên triển khai trước để phục vụ một tình huống phát hiện cụ thể?

Một phạm vi khởi đầu hợp lý cho ứng dụng Azure là **Entra sign-in, Entra audit, Azure Activity** và log bảo mật của những workload then chốt. Mở rộng sau khi đã xác minh tín hiệu, độ trễ và chi phí.

Các quyền truy cập phụ thuộc vào bước thực hiện. Ví dụ, vai trò Microsoft Sentinel Reader/Responder/Contributor hỗ trợ các mức quyền khác nhau trong Sentinel; quản trị workspace, cấu hình diagnostic settings, quản trị Entra và chạy playbooks có thể yêu cầu **các quyền bổ sung riêng**. Nguyên tắc là cấp quyền tối thiểu và tách trách nhiệm người xem, người điều tra, người chỉnh sửa quy tắc, người quản lý tự động hóa.

### 4.2. Chuẩn bị Log Analytics workspace và bật Sentinel

Trong môi trường có quyền phù hợp:

1. Vào Azure portal, tạo hoặc chọn **Log Analytics workspace** ở subscription, resource group và region đã được phê duyệt.
2. Kiểm tra cấu hình bảo mật, quyền truy cập, lưu giữ dữ liệu và ước tính chi phí của workspace.
3. Bật hoặc kết nối **Microsoft Sentinel** với workspace theo quy trình sản phẩm hiện hành.
4. Mở khu vực **Data connectors** trong giao diện Sentinel được tổ chức sử dụng. Tùy giai đoạn chuyển đổi giao diện, một số trải nghiệm điều tra và quản lý Sentinel có thể được thực hiện từ **Microsoft Defender portal**.
5. Kiểm tra rằng workspace, tenant, subscription và quyền truy cập đều đúng trước khi thu thập dữ liệu thực.

Việc tạo workspace và bật các kết nối có thể phát sinh chi phí từ dữ liệu nạp, lưu giữ hoặc dịch vụ liên quan. Cần dùng subscription thực hành được phép và cấu hình ngân sách/giám sát chi phí trước khi mở rộng.

### 4.3. Kết nối các nguồn dữ liệu ưu tiên

**A. Microsoft Entra ID**

Kết nối nguồn sign-in và audit theo hướng dẫn của data connector áp dụng cho tenant. Việc cấu hình có thể liên quan đến quyền quản trị Entra, cài đặt xuất chẩn đoán và điều kiện giấy phép cho từng loại log.

Sau khi kết nối, kiểm tra các bảng như `SigninLogs` và `AuditLogs`. Tùy loại nhật ký và tích hợp, tên bảng hoặc cách dữ liệu đến workspace có thể khác; nên lấy bảng thực tế từ trang connector và schema của workspace.

**B. Azure Activity**

Kết nối dữ liệu hoạt động quản lý từ những subscription cần giám sát. Kiểm tra dữ liệu đến bảng `AzureActivity` và đối chiếu subscription nguồn bằng trường định danh liên quan. Một người có quyền ở một subscription không tự động cấu hình được connector cho mọi subscription khác.

**C. Windows, Linux, thiết bị mạng**

Đối với nguồn cần agent, cân nhắc **Azure Monitor Agent (AMA)** và **Data Collection Rule (DCR)** để xác định dữ liệu thu thập, đường chuyển và bộ lọc hợp lệ. Windows Security Events, Syslog và CEF có yêu cầu triển khai, hệ điều hành/thiết bị và cấu hình riêng.

Ví dụ, một máy chủ Windows có thể cần kết nối AMA và DCR chọn kênh Security Events phù hợp; nếu chỉ bật Sentinel nhưng không cấu hình đường thu thập cho máy chủ thì không có lý do gì để mặc định bảng `SecurityEvent` sẽ có dữ liệu.

**D. Tích hợp cảnh báo từ sản phẩm bảo mật khác**

Có thể tích hợp tín hiệu từ Microsoft Defender và sản phẩm khác qua connector được hỗ trợ. Cần xác định dữ liệu là **raw logs, alerts hay incidents đồng bộ**, tránh cấu hình nhiều đường đưa cùng một tín hiệu vào gây cảnh báo trùng.

### 4.4. Kiểm chứng dữ liệu trước khi viết quy tắc

Đừng xem trạng thái “Connected” của connector là đủ. Hãy kiểm tra:

1. **Bảng có tồn tại và có dữ liệu mới không?**
2. **Trường phân tích có giá trị không?** Chẳng hạn `UserPrincipalName`, `IPAddress` hoặc `Caller`.
3. **Dữ liệu đến từ đúng tenant/subscription/host không?**
4. **Độ trễ nạp là bao nhiêu?** Nhiều nguồn log không đến tức thời.
5. **Có thiếu dữ liệu, lệch múi giờ, sai định dạng hoặc trùng tín hiệu không?**

Truy vấn kiểm tra đầu tiên:

~~~kusto
// Chạy trong workspace đã có connector Entra sign-in.
SigninLogs
| where TimeGenerated >= ago(24h)
| summarize
    TotalEvents = count(),
    LatestEventUtc = max(TimeGenerated),
    DistinctAccounts = dcount(UserPrincipalName)
~~~

Với hoạt động quản lý Azure:

~~~kusto
AzureActivity
| where TimeGenerated >= ago(24h)
| summarize Events = count(), LatestEventUtc = max(TimeGenerated)
    by SubscriptionId
| order by Events desc
~~~

**Cách đọc:** Nếu không có kết quả, trước hết phải kiểm tra quyền, connector, workspace, phạm vi thời gian và log nguồn có đang phát sinh hay không. Một bảng trống chưa chứng minh môi trường an toàn; nó có thể cho thấy **mất khả năng quan sát**.

### 4.5. Độ trễ và thời gian trong điều tra

`TimeGenerated` là thời điểm gắn với bản ghi theo mô hình của nguồn dữ liệu; thời điểm hệ thống nhận log có thể muộn hơn. KQL cũng có hàm `ingestion_time()` trong những ngữ cảnh được hỗ trợ, nhưng không nên giả định mọi nguồn cung cấp đầy đủ thông tin độ trễ như nhau.

Khi so sánh sự kiện từ nhiều hệ thống:

- Dùng **UTC** hoặc ghi rõ múi giờ khi lập timeline.
- Tính đến độ trễ và sự sai lệch đồng hồ của nguồn.
- Chọn khoảng truy vấn đủ rộng để tránh bỏ sót log đến chậm.
- Ghi lại cả thời điểm sự kiện lẫn thời điểm phân tích viên phát hiện.

## 5. Truy vấn sự kiện với KQL

**Kusto Query Language (KQL)** là ngôn ngữ truy vấn dữ liệu dạng bảng, rất phù hợp để lọc sự kiện, gom nhóm, tổng hợp và liên hệ các nguồn log trong Log Analytics.

Các toán tử thông dụng:

| Toán tử | Công dụng |
| --- | --- |
| `where` | Lọc các bản ghi đáp ứng điều kiện |
| `project` | Chọn/đặt tên cột đầu ra |
| `extend` | Tính thêm cột |
| `summarize` | Gom nhóm và tính toán, ví dụ `count()`, `dcount()` |
| `sort by` hoặc `order by` | Sắp xếp kết quả |
| `join` | Kết hợp các tập dữ liệu theo khóa |
| `bin()` | Chia thời gian thành khoảng để tính xu hướng |
| `ago()` | Lấy mốc thời gian tương đối so với hiện tại |

### 5.1. Tìm các tài khoản đăng nhập thất bại nhiều lần

~~~kusto
SigninLogs
| where TimeGenerated >= ago(24h)
| where tostring(ResultType) != "0"
| summarize
    FailedAttempts = count(),
    DistinctSourceIPs = dcount(IPAddress),
    FirstSeenUtc = min(TimeGenerated),
    LastSeenUtc = max(TimeGenerated)
    by UserPrincipalName
| where FailedAttempts >= 10
| order by FailedAttempts desc
~~~

**Ý nghĩa:** tìm các tài khoản có ít nhất 10 bản ghi đăng nhập không thành công trong 24 giờ, đếm số IP nguồn và khoảng thời gian xuất hiện.

**Không kết luận tài khoản đã bị xâm nhập chỉ từ một ngưỡng đếm.** Người dùng nhập sai mật khẩu, ứng dụng cũ lưu thông tin xác thực lỗi hoặc cơ chế tự động thử lại có thể tạo chuỗi thất bại tương tự. Cần xem mã lỗi, ứng dụng, IP, thời điểm và bối cảnh tài khoản.

### 5.2. Xem xu hướng thất bại theo từng khoảng 15 phút

~~~kusto
SigninLogs
| where TimeGenerated >= ago(24h)
| where tostring(ResultType) != "0"
| summarize FailedAttempts = count()
    by bin(TimeGenerated, 15m)
| order by TimeGenerated asc
~~~

Kết quả cho thấy số lần thất bại theo từng khung thời gian. Dùng cùng truy vấn với điều kiện theo tài khoản, ứng dụng hoặc địa chỉ IP để xác định thời điểm tăng đột biến.

### 5.3. Tìm thay đổi phân quyền ở Azure control plane

~~~kusto
AzureActivity
| where TimeGenerated >= ago(7d)
| where OperationNameValue has "Microsoft.Authorization/roleAssignments/"
| project
    TimeGenerated,
    Caller,
    OperationNameValue,
    ActivityStatusValue,
    ResourceId,
    CorrelationId
| order by TimeGenerated desc
~~~

Đây là một điểm khởi đầu để tìm hoạt động liên quan đến **Azure RBAC role assignments**. Cần kiểm tra chi tiết operation, trạng thái thành công/thất bại, phạm vi, actor và yêu cầu thay đổi đã được phê duyệt. Tên operation và giá trị trường phụ thuộc cách nguồn ghi log.

Nếu muốn điều tra thay đổi **vai trò quản trị bên trong Entra ID**, hãy dùng nguồn audit của Entra:

~~~kusto
AuditLogs
| where TimeGenerated >= ago(7d)
| where Category =~ "RoleManagement"
| project
    TimeGenerated,
    OperationName,
    Result,
    InitiatedBy,
    TargetResources,
    CorrelationId
| order by TimeGenerated desc
~~~

Hai truy vấn phục vụ **hai hệ vai trò khác nhau**: Azure RBAC đối với tài nguyên Azure và vai trò quản trị Entra đối với thư mục danh tính.

### 5.4. Tìm đăng nhập thành công sau một chuỗi thất bại

~~~kusto
let FailuresByAccount =
    SigninLogs
    | where TimeGenerated >= ago(2h)
    | where tostring(ResultType) != "0"
    | summarize
        FailedAttempts = count(),
        LastFailedUtc = max(TimeGenerated)
        by UserPrincipalName
    | where FailedAttempts >= 5;
SigninLogs
| where TimeGenerated >= ago(2h)
| where tostring(ResultType) == "0"
| join kind=inner FailuresByAccount on UserPrincipalName
| where TimeGenerated between (LastFailedUtc .. LastFailedUtc + 30m)
| project
    SuccessTimeUtc = TimeGenerated,
    UserPrincipalName,
    IPAddress,
    AppDisplayName,
    FailedAttempts,
    LastFailedUtc
| order by SuccessTimeUtc desc
~~~

Truy vấn là **gợi ý tương quan theo tài khoản và thời gian**, không chứng minh phiên đăng nhập thành công thuộc cùng một người hay cùng chiến dịch tấn công với các lần thất bại. Nếu có nhiều đợt thất bại, cách tổng hợp lấy `LastFailedUtc` có thể bỏ qua một số chuỗi trước đó. Khi dùng làm quy tắc thật, cần tinh chỉnh theo cửa sổ thời gian, phiên đăng nhập, IP, thiết bị, ứng dụng và độ trễ log.

### 5.5. KQL chỉ hoạt động trên dữ liệu có thật

Các câu lệnh ở trên yêu cầu bảng tồn tại trong workspace, connector đã cấp dữ liệu và người chạy có quyền truy vấn. Nếu nhận lỗi kiểu “Failed to resolve table”, hãy kiểm tra **tên bảng và dữ liệu kết nối**. Không tự tạo bảng giả bằng cách đổi tên tùy ý chỉ để truy vấn chạy được; phải xác định schema đang có.

## 6. Biến truy vấn thành cảnh báo và incident

KQL dùng để **hunting** là bước khám phá. Để giám sát lặp lại, có thể xây dựng **scheduled analytics rule** dựa trên cùng ý tưởng phát hiện.

Ví dụ, nhóm an ninh muốn nhận cảnh báo khi một tài khoản có **từ 10 lượt đăng nhập thất bại trở lên, đến từ ít nhất hai IP, trong 15 phút**:

~~~kusto
SigninLogs
| where TimeGenerated >= ago(15m)
| where tostring(ResultType) != "0"
| summarize
    FailedAttempts = count(),
    DistinctIPs = dcount(IPAddress),
    FirstSeenUtc = min(TimeGenerated),
    LastSeenUtc = max(TimeGenerated)
    by UserPrincipalName
| where FailedAttempts >= 10 and DistinctIPs >= 2
~~~

### Thiết lập rule theo tư duy vận hành

1. **Tên và mục đích:** ví dụ “Nhiều lượt đăng nhập thất bại từ nhiều IP”.
2. **Nguồn và lịch chạy:** chọn workspace, chu kỳ chạy, khoảng thời gian truy vấn phù hợp với độ trễ thu thập. Ví dụ chu kỳ 5 phút, truy vấn 15 phút có vùng chồng lấn.
3. **Điều kiện kích hoạt:** nếu truy vấn trả về ít nhất một hàng, xử lý theo cách rule được cấu hình. Hiểu rõ cơ chế grouping, event grouping và giới hạn của loại rule sử dụng.
4. **Entity mapping:** ánh xạ tài khoản bằng `UserPrincipalName`; với IP, chuẩn bị kết quả dữ liệu ở dạng phù hợp để ánh xạ một địa chỉ cụ thể nếu cần. Kết quả tổng hợp như số lượng IP không tự đại diện cho IP entity.
5. **Mức độ nghiêm trọng và phân loại:** đặt severity theo bối cảnh tổ chức và giả thuyết phát hiện. Thống nhất tên kỹ thuật, mô tả điều tra và hướng xử lý.
6. **Incident settings và grouping:** cấu hình tạo incident và gom các alert liên quan để giảm trùng lặp.
7. **Kiểm thử và tinh chỉnh:** đánh giá trên dữ liệu mẫu, thời gian lịch sử được phép truy vấn và luồng phê duyệt trước khi bật cho production.

**Lưu ý về trùng cảnh báo:** nếu rule chạy 5 phút một lần nhưng truy vấn nhìn lại 15 phút, một chuỗi log có thể thỏa điều kiện qua nhiều lần chạy. Cần thiết lập grouping, suppression/deduplication hợp lý và kiểm tra khả năng bỏ sót trong thời gian ingestion trễ.

**Lưu ý về false positive:** nhiều IP có thể phát sinh từ VPN, proxy, lưu lượng doanh nghiệp hoặc người dùng thường xuyên thay đổi mạng. Nên bổ sung thông tin rủi ro tài khoản, loại ứng dụng, mã lỗi, IP đáng tin cậy và sự kiện sau đăng nhập trước khi nâng severity.

Không nên kích hoạt tác vụ khóa tài khoản tự động ngay từ quy tắc thử nghiệm nếu chưa đánh giá tác động đến người dùng và quyền phê duyệt.

## 7. Quy trình điều tra incident có hệ thống

Giả sử Sentinel tạo incident: **“Nhiều lượt đăng nhập thất bại, sau đó thành công đối với tài khoản triển khai”**. Một quy trình điều tra có thể gồm bảy bước.

### Bước 1 — Tiếp nhận và phân loại

Mở incident trong giao diện Sentinel/Defender portal phù hợp với môi trường, xem tên, severity, thời gian, nguồn alert, analytics rule, owner, trạng thái và các entity liên quan.

Xác nhận đây là sự kiện cần điều tra hay cảnh báo lặp do một thay đổi hợp lệ. Ghi lại điều đã biết và điều chưa biết. Chọn người phụ trách incident theo quy trình trực vận hành.

### Bước 2 — Kiểm tra nguồn log gốc

Mở các bản ghi thô hỗ trợ alert. Kiểm tra:

- Thời gian UTC, khoảng truy vấn và độ trễ ingest.
- Tài khoản, ứng dụng, loại đăng nhập, trạng thái, mã lỗi.
- IP, host/thiết bị và thông tin ngữ cảnh thực sự có trong log.
- Quy tắc nào tạo alert; dữ liệu có trùng, thiếu hoặc bị lọc không.

**Không dùng tên incident như một kết luận pháp chứng.** Incident là điểm bắt đầu để xác minh.

### Bước 3 — Dựng timeline

Ví dụ:

| Thời điểm UTC | Tín hiệu | Giả thuyết cần kiểm chứng |
| --- | --- | --- |
| 08:00–08:05 | 12 lượt đăng nhập thất bại | Có thể có hoạt động thử thông tin xác thực |
| 08:07 | Một lượt đăng nhập thành công | Thành công có liên quan đến chuỗi trước không? |
| 08:10 | Có thay đổi Azure RBAC trong subscription | Ai thực hiện, ở scope nào, được phê duyệt chưa? |
| 08:16 | Workload xuất hiện kết nối mạng lạ | Có liên quan đến tài khoản, workload, hoặc một thay đổi hợp lệ? |

Bảng là **tình huống mô phỏng**, không phải sự kiện thật. Hãy nối sự kiện bằng các khóa đáng tin cậy như định danh tài khoản, request/correlation ID, đối tượng tài nguyên và khoảng thời gian; chỉ dựa vào việc “gần nhau” về thời gian là chưa đủ.

### Bước 4 — Mở rộng phạm vi

Chạy hunting để tìm:

- Các tài khoản khác dùng cùng IP nguồn hoặc gặp chuỗi thất bại tương tự.
- Lượt đăng nhập thành công ở gần thời điểm nghi vấn.
- Thay đổi phân quyền, thêm thành viên nhóm, ứng dụng hoặc thông tin xác thực mới.
- Hoạt động bất thường ở tài nguyên mà tài khoản có quyền.
- Các tín hiệu endpoint/network liên quan, nếu log nguồn đã được thu thập.

Tận dụng **Entities, Investigation, Logs, Hunting, Bookmarks** và các tính năng điều tra sẵn có tùy giao diện/khả năng của môi trường. Các câu trả lời phải phân biệt rõ **quan sát từ log**, **suy luận** và **điều chưa có bằng chứng**.

### Bước 5 — Đánh giá tác động và mức độ tin cậy

Xác định danh tính và tài nguyên bị ảnh hưởng, quyền thực tế của principal, dữ liệu có thể truy cập, thời gian hoạt động, khả năng lan sang môi trường khác và mức độ gián đoạn nếu xử lý.

Ví dụ, tài khoản chỉ có Reader ở một resource group khác về mức độ rủi ro so với tài khoản có quyền Owner trên subscription production. Nhưng Reader vẫn có thể xem thông tin nhạy cảm tùy tài nguyên và phân quyền data plane, nên cần xem quyền thực tế thay vì suy luận đơn giản từ tên role.

### Bước 6 — Ứng phó theo quy trình được phê duyệt

Tùy bằng chứng và thẩm quyền, nhóm ứng phó có thể:

- Yêu cầu xác minh với chủ tài khoản hoặc đội phụ trách thay đổi.
- Thu hồi phiên đăng nhập hoặc vô hiệu hóa phương thức truy cập bị nghi xâm phạm qua cơ chế danh tính phù hợp.
- Rà soát/thu hồi phân quyền mới cấp trái phép.
- Cô lập workload bị ảnh hưởng, cập nhật khóa/bí mật và chặn hành vi độc hại theo quy trình.
- Tạo ticket, thông báo đội liên quan và bảo toàn bằng chứng.

Việc phản ứng có thể tác động production; bước chặn, vô hiệu hóa hoặc xóa nên có cơ chế phê duyệt và phương án phục hồi. **Không xóa dữ liệu gốc hoặc tài nguyên nghi vấn chỉ để đóng incident.**

### Bước 7 — Đóng incident và cải thiện phát hiện

Lưu kết luận, bằng chứng, các truy vấn KQL liên quan, nguồn log còn thiếu, người phê duyệt, biện pháp xử lý và thời điểm khôi phục. Đặt trạng thái/phân loại incident phù hợp với quy trình thực tế, ví dụ true positive hoặc false positive khi có đủ cơ sở.

Sau điều tra, xem xét điều chỉnh connector, alert threshold, entity mapping, grouping, automation và quyền truy cập. Bài học quan trọng thường là **tăng khả năng quan sát** và giảm thời gian phát hiện trong lần tiếp theo.

## 8. Hunting: đi tìm dấu hiệu chưa có cảnh báo

**Threat hunting** là hoạt động chủ động đặt giả thuyết và tìm bằng chứng trong dữ liệu. Ví dụ:

> Giả thuyết: một người dùng vừa có hàng loạt đăng nhập lỗi, vừa thực hiện thao tác quản trị tài nguyên ngay sau đó.

Cách tiếp cận:

1. Xác định các nguồn cần có: `SigninLogs` và `AzureActivity`.
2. Tìm tài khoản có hành vi đăng nhập đáng chú ý.
3. Đối chiếu `UserPrincipalName` với `Caller`, nhưng phải kiểm tra độ phù hợp của định danh (cùng người, service principal, cách viết hoa/thường, tên hiển thị).
4. Thu hẹp khoảng thời gian để xem hành động tài nguyên gần thời điểm nghi vấn.
5. Ghi lại bằng chứng, khoảng trống dữ liệu và kết quả, kể cả khi giả thuyết bị bác bỏ.

Ví dụ lấy danh sách Azure Activity có dấu hiệu cấp quyền và xem actor:

~~~kusto
AzureActivity
| where TimeGenerated between (ago(24h) .. now())
| where OperationNameValue has "Microsoft.Authorization/roleAssignments/"
| summarize
    Operations = count(),
    FirstSeenUtc = min(TimeGenerated),
    LastSeenUtc = max(TimeGenerated)
    by Caller, ActivityStatusValue
| order by Operations desc
~~~

Khi cần đối chiếu nhiều bảng, KQL hỗ trợ `join`. Tuy nhiên, điều tra viên phải kiểm tra **khóa join có cùng ý nghĩa nghiệp vụ hay không**. Hai chuỗi văn bản giống nhau không nhất thiết chỉ cùng một principal hoặc một phiên hoạt động.

### Chuẩn hóa dữ liệu

Các thiết bị có thể gọi cùng khái niệm bằng tên khác nhau, ví dụ `src_ip`, `sourceAddress` hoặc `IPAddress`. **ASIM (Advanced Security Information Model)** cung cấp mô hình chuẩn hóa cho nhiều loại sự kiện trong Microsoft Sentinel, giúp tái sử dụng cách phát hiện/hunting giữa các nguồn được hỗ trợ.

Chuẩn hóa giúp giảm công sức khi tích hợp nhiều nguồn, nhưng không tự bổ sung dữ liệu không tồn tại và không thay thế việc xác minh parser, schema hoặc độ đầy đủ của log.

## 9. Tự động hóa phản ứng bằng automation rules và playbooks

Một incident có nhiều bước lặp lại: gán owner, bổ sung thông tin, thông báo kênh trực, tạo ticket hoặc yêu cầu phê duyệt. Sentinel có thể điều phối những bước này bằng **automation rules** và **playbooks**.

- **Automation rule:** xét điều kiện và áp dụng hành động do Sentinel hỗ trợ; có thể chạy playbook khi được cấu hình.
- **Playbook:** workflow dựa trên **Azure Logic Apps**, có thể gọi các connector/API để gửi thông báo, lấy ngữ cảnh và thực hiện hành động trên hệ thống liên quan.

Ví dụ một playbook an toàn ở giai đoạn đầu:

~~~mermaid
flowchart TD
    A["Incident mới có severity phù hợp"]
    B["Automation rule kiểm tra điều kiện"]
    C["Logic Apps playbook"]
    D["Lấy thông tin incident và entities"]
    E["Tạo ticket / gửi thông báo"]
    F["Người trực xác minh"]
    G{"Có bằng chứng và phê duyệt?"}
    H["Thực hiện hành động theo runbook"]
    I["Ghi chú / tiếp tục điều tra"]

    A --> B --> C --> D --> E --> F --> G
    G -->|Có| H
    G -->|Chưa| I
~~~

Khi triển khai thật:

- Chỉ cấp cho playbook và identity chạy workflow các quyền cần thiết.
- Kiểm tra quyền cho Sentinel kích hoạt playbook, quyền truy cập Logic Apps và quyền của từng connector được sử dụng.
- Thiết kế hành động có khả năng chạy lại, chống xử lý trùng và có nhật ký thực thi.
- Thử với dữ liệu mô phỏng, không tự động thực hiện hành động phá hủy trong lần kiểm thử đầu.
- Đặt cơ chế **human approval** cho các thao tác gây gián đoạn như khóa tài khoản, chặn dịch vụ hoặc thu hồi quyền diện rộng.

Tự động hóa làm giảm thời gian xử lý các bước lặp nhưng không thay thế đánh giá của điều tra viên đối với sự cố chưa rõ bối cảnh.

## 10. Bảo mật dữ liệu, tuân thủ và chi phí vận hành

Thu thập nhiều log hơn chưa chắc tốt hơn. Một chương trình Sentinel hiệu quả phải trả lời được **vì sao cần dữ liệu đó, giữ bao lâu và ai được phép xem**.

### 10.1. Quyền truy cập và dữ liệu nhạy cảm

Log có thể chứa địa chỉ IP, tên người dùng, định danh tài nguyên, đường dẫn tệp và dữ liệu liên quan đến hoạt động cá nhân. Vì vậy cần:

- Giới hạn quyền truy vấn workspace và truy cập incident theo vai trò phù hợp.
- Kiểm soát việc chia sẻ/export kết quả tìm kiếm hoặc gửi log qua playbook.
- Che hoặc hạn chế trường nhạy cảm khi không cần cho phát hiện.
- Tuân thủ chính sách lưu giữ, khu vực dữ liệu và quy trình xử lý bằng chứng của tổ chức.
- Ghi nhận ai điều tra, phát hiện gì và quyết định xử lý nào được phê duyệt.

Không đưa bí mật truy cập, mật khẩu hoặc token thật vào ví dụ, ghi chú incident hoặc ticket.

### 10.2. Lưu giữ và khả năng điều tra lịch sử

Khả năng truy vấn sự kiện cũ phụ thuộc vào **loại dữ liệu, cấu hình lưu giữ, chính sách truy cập và các khả năng lưu trữ/truy vấn hiện hành**. Nếu một sự cố chỉ được phát hiện sau nhiều tuần nhưng log đã hết thời hạn lưu giữ, việc truy vết sẽ bị giới hạn.

Đừng giả định bật connector hôm nay sẽ tự động có toàn bộ log lịch sử từ trước. Khả năng nạp lại dữ liệu phụ thuộc vào nguồn và connector cụ thể.

### 10.3. Những yếu tố ảnh hưởng chi phí

| Yếu tố | Ảnh hưởng thường gặp | Cách kiểm soát |
| --- | --- | --- |
| **Khối lượng nạp dữ liệu** | Log nhiều nguồn hoặc tần suất cao làm tăng lượng dữ liệu nạp | Chọn nguồn có giá trị, lọc đúng cách, ước lượng GB/ngày |
| **Thời hạn và kiểu lưu giữ** | Lưu lâu hoặc dùng cách truy cập lịch sử khác nhau có thể phát sinh chi phí | Chọn theo yêu cầu điều tra và tuân thủ |
| **Loại log/connector và dịch vụ phụ trợ** | Một số nguồn, sản phẩm bảo mật, giấy phép có chi phí riêng | Kiểm tra điều kiện và giá dịch vụ áp dụng |
| **Automation/Logic Apps** | Số lượt chạy workflow, action và dịch vụ gọi kèm có thể tính phí | Giảm vòng lặp, chống trigger trùng, giám sát thực thi |
| **Mở rộng phạm vi giám sát** | Thêm subscription, endpoint và thiết bị làm tăng dữ liệu | Triển khai theo giai đoạn, đo chi phí thực tế |

Mô hình giá và tên gói có thể thay đổi. Khi lập ngân sách, sử dụng thông tin giá chính thức đang áp dụng cho **region, workspace, loại dữ liệu và điều khoản của tổ chức**. Không suy ra chi phí chỉ từ số alert hoặc số incident.

## 11. Thực hành có hướng dẫn: từ sự kiện đến giả thuyết điều tra

### Tình huống

Nhóm vận hành một ứng dụng nội bộ trên Azure, sử dụng Entra ID cho người dùng và triển khai hạ tầng ở subscription Dev/Prod. Nhóm muốn phát hiện chuỗi đăng nhập thất bại bất thường trước khi xem xét các thay đổi quyền Azure.

**Mục tiêu:** thực hành truy vấn, đọc kết quả, xác định hành động điều tra. Nếu có workspace thực hành được cấp quyền, bạn có thể đối chiếu với dữ liệu thật; phần mô phỏng dưới đây không cần tạo tài nguyên hoặc tạo lưu lượng đăng nhập lỗi.

### Phần A — Kiểm tra dữ liệu thật (nếu được cấp quyền)

1. Mở đúng workspace Sentinel và xác nhận đúng tenant/subscription.
2. Kiểm tra connector Entra sign-in và Azure Activity đang thu thập dữ liệu.
3. Chạy truy vấn ở mục **5.1**, ghi lại tài khoản có nhiều lần thất bại, `FirstSeenUtc`, `LastSeenUtc` và số IP nguồn.
4. Nếu có tín hiệu cần xem xét, truy vấn các sign-in thành công và Azure Activity liên quan trong khoảng thời gian phù hợp.
5. Ghi ra một kết luận có dẫn chứng và một giả thuyết còn phải kiểm chứng.

Chỉ đọc dữ liệu trong phạm vi được cấp quyền. Không cần chủ động thực hiện đăng nhập lỗi bằng tài khoản thật để tạo dữ liệu thử nghiệm.

### Phần B — Dữ liệu mô phỏng có thể chạy độc lập

Đoạn KQL sau **tự tạo 12 bản ghi giả**, không cần bảng `SigninLogs`. Địa chỉ IP thuộc các dải dành cho ví dụ tài liệu.

~~~kusto
range i from 1 to 12 step 1
| extend
    UserPrincipalName = iff(i <= 10, "linh@example.test", "minh@example.test"),
    IPAddress = iff(i % 2 == 0, "203.0.113.10", "198.51.100.22"),
    ResultType = iff(i <= 10, "50126", "0"),
    TimeGenerated = ago(3m)
| where ResultType != "0"
| summarize
    FailedAttempts = count(),
    DistinctIPs = dcount(IPAddress)
    by UserPrincipalName
| where FailedAttempts >= 10 and DistinctIPs >= 2
~~~

**Kết quả mong đợi:**

| UserPrincipalName | FailedAttempts | DistinctIPs |
| --- | ---: | ---: |
| `linh@example.test` | 10 | 2 |

Đây chỉ là tín hiệu theo điều kiện truy vấn. Bạn **chưa có bằng chứng** về người thực hiện, quốc gia nguồn, thiết bị, hành vi sau đăng nhập hoặc mức độ ảnh hưởng tài nguyên.

### Phần C — Tự phân tích như điều tra viên

Trả lời các câu hỏi:

1. Nếu cùng kết quả đến từ 10 lần retry tự động của ứng dụng nội bộ, incident có còn đáng ưu tiên cao không?
2. Cần tìm gì trong `SigninLogs` để biết có lần đăng nhập thành công tiếp theo?
3. Nếu xuất hiện thay đổi role assignment ở Azure, nguồn nào cho biết actor và scope?
4. Nếu `AzureActivity` không có dữ liệu, có thể kết luận “không có thay đổi quyền” hay không?
5. Những điều kiện nào phải xác minh trước khi dùng playbook khóa tài khoản?

**Gợi ý đáp án:**

- Cần xác định tính hợp lệ của retry, hệ thống nguồn và mức độ rủi ro; chỉ dựa vào số lượt thất bại chưa đủ.
- Tìm kết quả thành công, thời gian, principal, IP, ứng dụng, thiết bị và các correlation ID nếu có.
- Azure Activity và các log liên quan đến role assignment giúp kiểm tra hoạt động ở Azure RBAC; audit của Entra phục vụ thay đổi vai trò thư mục.
- Không. Bảng trống có thể do connector, quyền, thời gian hoặc độ trễ; đó là một lỗ hổng quan sát cần làm rõ.
- Phải xác minh bằng chứng, quyền xử lý, tính chất tài khoản, ảnh hưởng tới hệ thống phụ thuộc, phê duyệt và phương án khôi phục.

### Phần D — Định nghĩa analytics rule trên giấy

Viết cấu hình mô tả cho một rule dựa trên KQL ở mục 6:

| Thuộc tính | Giá trị ví dụ |
| --- | --- |
| Tên | Nhiều đăng nhập thất bại từ nhiều IP |
| Nguồn | `SigninLogs` |
| Điều kiện | Tối thiểu 10 thất bại, tối thiểu 2 IP trong 15 phút |
| Chu kỳ kiểm tra | 5 phút, cần kiểm soát vùng thời gian chồng lấn |
| Entity chính | Account: `UserPrincipalName` |
| Hướng xử lý đầu | Kiểm tra log gốc, bối cảnh tài khoản và đăng nhập thành công kế tiếp |
| Tự động hóa ban đầu | Tạo ticket và gán người điều tra |
| Tiêu chí đánh giá | Độ trễ, số false positive, dữ liệu thiếu, nguy cơ cảnh báo trùng |

Tài liệu này là **bản thiết kế thực hành**. Triển khai rule thật cần quyền phù hợp và quy trình phê duyệt của tổ chức.

## 12. Những lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| Không thấy sự kiện mới | Connector chưa cấu hình đủ, nguồn không phát log, ingest trễ | Kiểm tra connector, nguồn, thời gian và truy vấn gần nhất |
| KQL báo không tìm thấy bảng | Sai workspace, bảng chưa có dữ liệu hoặc tên bảng không đúng | Xác nhận bảng trong Logs và schema của connector |
| Cùng hành vi tạo nhiều incident | Rule có cửa sổ chồng lấn hoặc grouping chưa phù hợp | Đánh giá lịch chạy, suppression, grouping và logic truy vấn |
| Alert chứa ít thông tin điều tra | Chưa ánh xạ entity hoặc chưa giữ các trường ngữ cảnh hữu ích | Bổ sung entity mapping, kết quả truy vấn, mô tả rule |
| Có incident nhưng playbook không chạy | Thiếu quyền, sai trigger/điều kiện, lỗi Logic Apps hoặc kết nối | Kiểm tra run history, identity, role assignment và trạng thái workflow |
| Không xem được log trong incident | Quyền truy cập Sentinel và Log Analytics không khớp | Kiểm tra vai trò theo từng scope và workspace thực tế |
| Chi phí tăng bất ngờ | Thu thập quá rộng, log trùng hoặc thay đổi dữ liệu đầu vào | Soát dung lượng từng bảng, connector và retention |
| Không truy được sự kiện từ tháng trước | Thời hạn lưu giữ, kiểu dữ liệu hoặc quyền truy vấn lịch sử | Xác minh retention, lịch sử connector và chính sách truy cập |

## 13. Câu hỏi tự kiểm tra

**Câu 1.** Azure Activity Log có đủ để phát hiện mọi lượt đọc dữ liệu trong storage account không?

**Trả lời:** Không. Activity Log chủ yếu phản ánh hoạt động quản lý/control plane. Cần xem loại resource logs và khả năng giám sát data plane phù hợp với storage.

**Câu 2.** Một analytics rule tạo alert sau 10 lần đăng nhập thất bại. Có thể tự động coi đó là tài khoản bị chiếm quyền không?

**Trả lời:** Không. Ngưỡng là dấu hiệu để điều tra. Cần loại trừ retry hợp lệ, xem ngữ cảnh tài khoản và bằng chứng bổ sung.

**Câu 3.** Vì sao một rule chạy 5 phút/lần với khoảng nhìn lại 15 phút có thể tạo cảnh báo trùng?

**Trả lời:** Các lần chạy liên tiếp truy vấn một phần cùng tập sự kiện. Cần thiết kế grouping, deduplication/suppression và độ trễ một cách có chủ đích.

**Câu 4.** Sentinel có thể dùng playbook để phản ứng; vì sao không nên tự động khóa mọi tài khoản xuất hiện trong alert?

**Trả lời:** Alert có thể sai hoặc chưa đủ bối cảnh; khóa tài khoản có thể gây gián đoạn dịch vụ và tác động người dùng hợp lệ. Cần quyền, phê duyệt và phương án khôi phục.

**Câu 5.** Bảng `SigninLogs` rỗng có nghĩa là không ai đăng nhập trong 24 giờ qua?

**Trả lời:** Chưa thể kết luận. Cần kiểm tra tenant, connector, workspace, thời gian, quyền truy vấn, loại log và trạng thái ingest.

## Ghi nhớ

- **Microsoft Sentinel** kết hợp thu thập tín hiệu bảo mật, SIEM, điều tra incident và tự động hóa phản ứng SOAR.
- Chọn **nguồn log theo câu hỏi an ninh**; cần có connector, quyền và dữ liệu thật trước khi viết quy tắc phát hiện.
- **KQL** hỗ trợ lọc, tổng hợp và tương quan log, nhưng kết quả truy vấn là tín hiệu cần kiểm chứng bằng ngữ cảnh.
- **Alert** là dấu hiệu từ phát hiện; **incident** là hồ sơ để điều tra, phân loại và theo dõi quá trình xử lý.
- Điều tra tốt cần **timeline, entity, bằng chứng, phạm vi ảnh hưởng và giới hạn dữ liệu**.
- Vận hành Sentinel bền vững cần cân bằng **phát hiện, quyền truy cập, lưu giữ, tự động hóa và chi phí**.
