# Quy trình xử lý cảnh báo và bằng chứng kiểm toán

Khi vận hành ứng dụng trên Microsoft Azure, cảnh báo có thể xuất hiện vì tài nguyên ngừng hoạt động, truy cập đáng ngờ, thay đổi quyền quản trị, cấu hình không tuân thủ hoặc chi phí tăng bất thường. Việc nhận được cảnh báo chỉ là điểm bắt đầu. Nhóm vận hành cần xác minh tín hiệu, đánh giá tác động, xử lý đúng mức độ ưu tiên và lưu lại bằng chứng đáng tin cậy về những gì đã xảy ra.

Một quy trình tốt trả lời được hai nhóm câu hỏi:

- **Vận hành và bảo mật:** sự kiện nào xảy ra, ảnh hưởng đến ai, cần hành động gì, đã khôi phục dịch vụ và ngăn tái diễn chưa?
- **Kiểm toán và truy vết:** tổ chức phát hiện bằng cách nào, ai quyết định xử lý, thay đổi nào đã được thực hiện, bằng chứng nào chứng minh các biện pháp kiểm soát đang hoạt động?

Trong mô-đun CLOUD_PROVIDERS_AZURE, quy trình này kết nối Microsoft Entra ID, Azure subscription và resource group với Azure Monitor, Microsoft Defender for Cloud, Microsoft Sentinel (nếu triển khai), Azure Policy, công cụ giám sát, cơ chế phân quyền và kiểm soát chi phí. Bài học tập trung vào cách tổ chức thực hiện quy trình; một số nguồn log, tính năng lưu trữ và tích hợp cần được cấu hình trước và có thể phát sinh phí.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt tín hiệu giám sát, alert, incident, security finding và phát hiện không tuân thủ.
2. Xây dựng vòng đời xử lý cảnh báo gồm tiếp nhận, phân loại, xác minh, ứng phó, khôi phục và đóng vụ việc.
3. Xác định nguồn bằng chứng phù hợp trong Azure và Microsoft Entra ID, bao gồm những trường hợp không có dữ liệu nếu chưa cấu hình thu thập.
4. Ghi nhận chuỗi bảo quản bằng chứng (chain of custody), tính toàn vẹn, thời gian, người thao tác, nơi lưu và thời hạn giữ.
5. Viết truy vấn KQL cơ bản, kiểm tra Azure Activity Log và lập hồ sơ phục vụ kiểm toán.
6. Đề xuất cách tự động hóa an toàn mà vẫn có người phê duyệt cho hành động ảnh hưởng lớn.

Các ví dụ giả định một ứng dụng chạy trong resource group thuộc subscription Azure có người quản trị và nhóm trực sự cố. Mọi thời gian trong hồ sơ được chuẩn hóa theo UTC để dễ đối chiếu giữa khu vực và hệ thống.

## 2. Phân biệt alert, incident và bằng chứng

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| Tín hiệu hoặc sự kiện (event) | Một bản ghi hoặc phép đo do hệ thống tạo | Một thao tác ghi role assignment xuất hiện trong Azure Activity Log |
| Alert | Thông báo sinh ra khi điều kiện hoặc quy tắc phát hiện được thỏa mãn | Azure Monitor cảnh báo khi tỷ lệ HTTP 5xx vượt ngưỡng |
| Security finding/recommendation | Phát hiện về rủi ro hay cấu hình bảo mật cần cải thiện | Defender for Cloud phát hiện tài nguyên có cấu hình chưa an toàn |
| Incident | Vụ việc cần điều tra, phối hợp và xử lý theo quy trình | Một danh tính bị nghi chiếm quyền dẫn tới nhiều thay đổi trái phép |
| Audit evidence | Dữ liệu hoặc hồ sơ dùng để chứng minh sự kiện, quyết định hay việc thực thi kiểm soát | Log gốc, truy vấn, role assignment, ticket phê duyệt, báo cáo khắc phục |
| Control | Cơ chế hoặc quy trình quản trị rủi ro | MFA, Azure RBAC, Azure Policy, cảnh báo truy cập đặc quyền |
| Noncompliance | Trạng thái chưa đáp ứng một quy tắc đã định nghĩa | Một storage account vi phạm policy yêu cầu mã hóa hoặc cấu hình mạng |

**Một alert không đồng nghĩa với một sự cố bảo mật.** Alert có thể là dương tính giả, hành vi hợp lệ hoặc một triệu chứng của sự cố kỹ thuật. Nhiều alert có thể quy về cùng một incident. Ngược lại, một incident có thể được phát hiện qua phản ánh của người dùng mà chưa có alert tự động.

Bằng chứng kiểm toán cũng rộng hơn bằng chứng pháp chứng (forensic evidence) cho một vụ tấn công. Nó có thể chứng minh tổ chức đã cấu hình kiểm soát từ trước, phát hiện sai lệch, phê duyệt thay đổi, thực hiện ứng phó và đánh giá kết quả. Vì vậy cần duy trì hồ sơ vừa có dữ liệu hệ thống, vừa có diễn giải và quyết định của con người.

## 3. Các nguồn tín hiệu và bằng chứng trên Azure

### 3.1. Nguồn dữ liệu thường dùng

| Nguồn | Loại dữ liệu | Dùng khi nào | Giới hạn cần nhớ |
|---|---|---|---|
| Azure Monitor metric alerts | Chỉ số tài nguyên: CPU, lỗi, độ trễ, số kết nối | Sự cố độ sẵn sàng/hiệu năng | Metric chỉ cho biết triệu chứng, chưa đủ kết luận nguyên nhân |
| Azure Monitor log alerts | Kết quả truy vấn log theo lịch và điều kiện | Hành vi bất thường, lỗi ứng dụng hoặc thao tác quản trị | Chỉ hoạt động khi log phù hợp được thu thập và quy tắc được bật |
| Azure Activity Log | Sự kiện control plane ở phạm vi subscription, như tạo/xóa tài nguyên hoặc thay đổi quyền | Truy vết thao tác ARM và ai gọi thao tác | Không thay thế nhật ký truy cập dữ liệu; có giới hạn lưu giữ mặc định |
| Resource logs/diagnostic logs | Log riêng của dịch vụ: Key Vault, Storage, network, database… | Điều tra truy cập data plane và hoạt động của dịch vụ | Nhiều loại log yêu cầu bật diagnostic settings và chọn destination trước |
| Log Analytics workspace | Khu vực tập trung truy vấn các bảng log đã gửi đến workspace | Tương quan nhiều nguồn theo thời gian, IP, resource ID hoặc correlation ID | Chi phí ingest/retention, quyền truy cập và độ trễ ingest phụ thuộc cấu hình |
| Microsoft Entra sign-in/audit logs | Đăng nhập, thay đổi danh tính, cấu hình và quyền liên quan Entra | Điều tra truy cập bất thường, cập nhật ứng dụng và danh tính | Cấp phép, retention và cấu hình xuất log khác nhau tùy tenant |
| Microsoft Defender for Cloud | Recommendations, security alerts và thông tin bảo vệ workload khi bật các gói phù hợp | Phát hiện posture issue và mối đe dọa | Khả năng phát hiện phụ thuộc gói bảo vệ và cấu hình đang sử dụng |
| Microsoft Sentinel | Analytic rules, incidents, entities, investigation và automation | SOC cần tương quan cảnh báo, điều tra tập trung | Cần triển khai, kết nối nguồn và phân quyền; không tự có trong mọi subscription |
| Azure Policy | Định nghĩa, assignment, exemption và trạng thái compliance | Chứng minh cấu hình tuân thủ quy tắc đã đặt | Compliance assessment không thay thế kiểm tra vận hành hoặc pháp lý |
| Azure Resource Graph | Truy vấn inventory tài nguyên, loại, vùng, tag và thuộc tính hiện có | Đối chiếu phạm vi bị ảnh hưởng | Dữ liệu thể hiện trạng thái quan sát được, không phải lịch sử đầy đủ |
| Change ticket, deployment log, repo và approval | Người yêu cầu, người phê duyệt, commit, pipeline run, thay đổi đã thực hiện | Giải thích tính hợp lệ và quyết định của con người | Phải liên kết với dữ liệu hệ thống bằng ID và timestamp |

**Lưu ý quan trọng:** Azure Activity Log là control-plane log. Nó có thể cho biết một Key Vault hoặc policy đã được cấu hình lại nhưng không mặc nhiên ghi lại từng lần ứng dụng đọc secret. Muốn điều tra thao tác data plane phải kiểm tra cơ chế audit/diagnostic logging của dịch vụ đích và log đã được bật trước thời điểm sự kiện.

### 3.2. Chuẩn bị trước khi có cảnh báo

Không thể bảo đảm thu thập đầy đủ sự kiện quá khứ nếu hệ thống chưa bật logging hoặc đã hết thời hạn lưu giữ. Cần thiết kế khả năng quan sát từ khi triển khai:

1. Liệt kê tài nguyên trọng yếu: Entra ID, subscription production, Key Vault, Storage, App Service/AKS, database, network và công cụ CI/CD.
2. Xác định cảnh báo cần có: lỗi dịch vụ, thay đổi role nhạy cảm, hoạt động danh tính bất thường, truy cập dữ liệu trái phép, hành vi xóa/sửa tài nguyên và vi phạm policy.
3. Gửi các log bắt buộc về Log Analytics workspace, Storage Account hoặc Event Hub qua diagnostic settings hoặc cấu hình xuất log tương ứng của từng dịch vụ.
4. Chọn thời gian lưu giữ, phân quyền đọc, yêu cầu mã hóa, phạm vi mạng và vị trí lưu phù hợp chính sách tổ chức.
5. Kiểm tra thực tế rằng log đi đến đúng nơi, đúng bảng, có trường cần thiết và truy vấn được; bật cấu hình không có nghĩa là đã ingest thành công.
6. Cấu hình Action Group hoặc kênh thông báo để alert đến được nhóm trực, đồng thời chạy thử luồng escalations.
7. Đồng bộ thời gian và chuẩn hóa timestamp UTC; xác định khóa tương quan như subscription ID, resource ID, operation ID và correlation ID.
8. Ghi rõ người sở hữu alert rule, runbook, kênh khẩn cấp và người phê duyệt các hành động gây gián đoạn.

Với các tài nguyên production, cần quan tâm cả thời hạn lưu dữ liệu kiểm toán và yêu cầu khôi phục sau sự cố. Các chính sách compliance/retention phụ thuộc tổ chức, hợp đồng và pháp luật áp dụng; không có một mức thời hạn chung đúng cho mọi loại bằng chứng.

## 4. Thiết kế vòng đời xử lý cảnh báo

Một quy trình chuẩn có thể tổ chức thành tám bước:

~~~mermaid
flowchart TD
    A[Tiếp nhận cảnh báo] --> B[Chuẩn hóa và tạo hồ sơ]
    B --> C[Kiểm tra trùng và xác minh]
    C --> D{Cảnh báo có giá trị?}
    D -->|Không| E[Ghi lý do và điều chỉnh rule]
    D -->|Có| F[Đánh giá mức độ và ảnh hưởng]
    F --> G[Điều tra và bảo toàn bằng chứng]
    G --> H[Khoanh vùng và khắc phục]
    H --> I[Kiểm chứng khôi phục]
    I --> J[Đóng hồ sơ và cải tiến]
    E --> J
~~~

Sơ đồ là luồng cơ bản. Trong sự cố nghiêm trọng, bảo toàn bằng chứng và khoanh vùng có thể diễn ra song song theo quyết định của incident commander. Không trì hoãn hành động ngăn thiệt hại cấp bách chỉ để hoàn thành biểu mẫu, nhưng phải ghi lại quyết định và ảnh hưởng của hành động đó tới bằng chứng.

### Bước 1: Tiếp nhận và ghi nhận

Mỗi alert cần được gắn vào một case hoặc incident record có ID ổn định, ví dụ SEC-2026-0042. Tối thiểu ghi:

- Thời điểm hệ thống phát hiện và thời điểm đội trực nhận được (UTC).
- Nguồn alert, alert rule ID, alert instance ID, severity gốc và trạng thái hiện tại.
- Tenant, subscription, resource group, resource ID, region và môi trường liên quan.
- Đối tượng bị ảnh hưởng: ứng dụng, máy chủ, tài khoản, IP, request ID hoặc service principal.
- Người/nhóm phụ trách, kênh trao đổi và liên kết tới dashboard hoặc ticket.
- Liên kết tới thông báo gốc hoặc bản xuất dữ liệu, không chỉ chép nội dung vào ticket.

Nếu nhiều alert cùng phản ánh một chuỗi sự kiện, nên liên kết chúng vào một incident; không đóng bớt alert bằng cách xóa hồ sơ gốc.

### Bước 2: Loại trùng và xác minh

Trước khi hành động:

1. Xác minh alert có đến từ nguồn hợp lệ, không phải thông báo giả mạo.
2. Xác định quy tắc nào kích hoạt, ngưỡng và khoảng thời gian đánh giá.
3. So sánh các alert liên quan cùng tài nguyên, danh tính, correlation ID hoặc cửa sổ thời gian.
4. Kiểm tra maintenance window, thay đổi đã phê duyệt, deployment gần đây và dữ liệu vận hành.
5. Nếu nghi dương tính giả, lưu dữ liệu và lý do phân loại; không đơn giản xóa alert.

Ví dụ, cảnh báo “VM CPU vượt 90%” có thể đến từ tác vụ batch theo lịch. Tuy nhiên, cùng chỉ số đó cộng với lưu lượng egress bất thường và thay đổi quyền mới có thể đáng điều tra hơn. Một sự kiện hợp lệ theo lịch cũng cần được kiểm tra nếu vượt mức rủi ro được chấp nhận.

### Bước 3: Đánh giá severity và mức ưu tiên

Severity do công cụ gán và **mức ưu tiên xử lý của tổ chức** có thể khác nhau. Một cảnh báo kỹ thuật có mức cao nhưng không ảnh hưởng người dùng có thể được xử lý sau cảnh báo trung bình đang làm gián đoạn hệ thống thanh toán.

Ma trận tham khảo:

| Mức ưu tiên | Tác động và khả năng xảy ra | Cách xử lý mẫu |
|---|---|---|
| P1 – Nghiêm trọng | Nghi xâm nhập đang diễn ra, dữ liệu quan trọng bị lộ hoặc hệ thống production thiết yếu ngừng hoạt động trên diện rộng | Kích hoạt điều phối sự cố, xử lý và escalations ngay |
| P2 – Cao | Có nguy cơ đáng kể với một dịch vụ production, chưa có dấu hiệu lan rộng | Phân công người chịu trách nhiệm, điều tra khẩn |
| P3 – Trung bình | Sự kiện bất thường hạn chế, tác động thấp hoặc chưa có bằng chứng xâm nhập | Xử lý theo thời hạn nội bộ đã cam kết |
| P4 – Thấp | Cấu hình cải tiến, finding ít rủi ro hoặc tín hiệu cần theo dõi | Chuyển backlog với owner và hạn xử lý |

Đây là ví dụ cách phân loại, **không phải SLA mặc định của Azure**. Tổ chức cần quy định thời gian phản hồi riêng, phù hợp giờ trực, dữ liệu, nghĩa vụ thông báo và mức độ kinh doanh. Khi thông tin mới cho thấy phạm vi tác động thay đổi, phải nâng hoặc hạ mức ưu tiên và ghi lý do.

### Bước 4: Điều tra và dựng timeline

Người xử lý cần trả lời:

- Điều gì thực sự đã xảy ra? Tín hiệu độc lập nào xác nhận?
- Thời điểm bắt đầu, kết thúc và cửa sổ điều tra là gì?
- Thao tác đến từ người dùng, service principal, managed identity hay dịch vụ Azure nào?
- Resource ID, client IP, correlation ID, change request và deployment nào liên quan?
- Ứng dụng, dữ liệu, khu vực và khách hàng nào có thể bị ảnh hưởng?
- Log nào đáng tin, log nào thiếu và điều gì chưa thể kết luận?

Timeline nên ghi cả **thời điểm sự kiện** và **thời điểm thu thập/nhận dữ liệu**. Log có thể đến workspace trễ; không suy ra trình tự nhân quả chỉ từ thứ tự ingestion. Cần phân biệt sự kiện được quan sát với giả thuyết điều tra.

### Bước 5: Khoanh vùng, xử lý và khắc phục

Tùy mức độ, biện pháp có thể gồm:

- Hạn chế quyền của danh tính bị nghi xâm phạm, thu hồi credential hoặc session khi được phép.
- Tạm dừng pipeline hoặc automation đang tạo thay đổi ngoài dự kiến.
- Thắt chặt network rule, chặn luồng truy cập đáng ngờ hoặc cô lập workload.
- Khôi phục cấu hình bằng IaC/rollback có kiểm soát, vá lỗ hổng hoặc cập nhật policy.
- Di chuyển lưu lượng sang tài nguyên khỏe mạnh và kích hoạt phương án phục hồi phù hợp.

Hành động như vô hiệu hóa danh tính, ngắt mạng, xóa workload hay xoay khóa có thể làm gián đoạn hệ thống hoặc làm thay đổi dấu vết điều tra. Cần ghi người quyết định, lý do, phạm vi, thời gian, công cụ và kết quả; thực hiện quy trình phê duyệt thích hợp. Với sự cố đang lan rộng, dùng thẩm quyền khẩn cấp đã định nghĩa và hoàn thiện hồ sơ ngay sau đó.

**Không xóa tài nguyên bị nghi xâm phạm trước khi cân nhắc bảo toàn bằng chứng**. Nếu buộc phải xóa hoặc thay đổi để chặn thiệt hại, ghi rõ bằng chứng nào đã được thu thập và giới hạn còn lại.

### Bước 6: Khôi phục và xác nhận

Một sự cố chỉ nên coi là khắc phục khi có dữ liệu hỗ trợ:

- Dịch vụ hoạt động theo các SLI/SLO hoặc tiêu chí vận hành đã thống nhất.
- Các quyền quá mức, lỗ hổng hoặc sai cấu hình liên quan được xử lý.
- Alert gốc đã ngừng kích hoạt vì nguyên nhân được giải quyết, không phải chỉ do tắt rule.
- Không còn dấu hiệu lặp lại trong cửa sổ theo dõi.
- Chủ sở hữu ứng dụng hoặc incident commander xác nhận các tiêu chí hoàn tất.

Với sự cố liên quan dữ liệu, cần xác minh tính toàn vẹn và khả năng phục hồi của dữ liệu theo yêu cầu nội bộ, không chỉ dựa vào trạng thái “Healthy” của Azure resource.

### Bước 7: Đóng case và lưu hồ sơ

Một case có thể đóng khi có quyết định rõ ràng: confirmed incident, benign activity, false positive, duplicate hoặc accepted risk. Nêu ai duyệt đóng và dựa trên bằng chứng nào.

Hồ sơ cuối nên liên kết dữ liệu gốc, timeline, quyết định, thay đổi, phép kiểm tra sau khắc phục, thông báo liên quan và action items. Đừng chỉ chụp màn hình alert đã chuyển sang “Resolved” vì trạng thái đó không chứng minh nguyên nhân hay tính hiệu quả của biện pháp ứng phó.

### Bước 8: Post-incident review và cải tiến

Đánh giá độ trễ phát hiện, thời gian phản hồi, hành động nào có hiệu quả, log nào bị thiếu, luồng phê duyệt nào chậm và quy tắc nào gây quá nhiều cảnh báo không có giá trị. Mỗi cải tiến cần có owner, độ ưu tiên và hạn hoàn tất. Có thể tổ chức review không đổ lỗi cá nhân nhưng vẫn xác định trách nhiệm vận hành và quyền quyết định.

## 5. Phân vai và cơ chế chuyển cấp

| Vai trò | Trách nhiệm chính |
|---|---|
| On-call/SOC analyst | Xác minh, phân loại, tạo hoặc cập nhật case, thu thập thông tin ban đầu |
| Incident commander | Điều phối vụ việc lớn, quyết định ưu tiên, phê duyệt và theo dõi hành động ứng phó |
| Application/service owner | Đánh giá tác động nghiệp vụ, phân tích ứng dụng, xác nhận khôi phục |
| Cloud/IAM/SRE engineer | Kiểm tra quyền, hạ tầng, log và triển khai biện pháp kỹ thuật |
| Security/Compliance | Xác định nghĩa vụ xử lý, yêu cầu bằng chứng, hỗ trợ đánh giá và kiểm toán |
| Evidence custodian | Kiểm soát thu thập, bàn giao, nơi lưu, toàn vẹn và truy cập bằng chứng |
| Auditor/reviewer độc lập | Đối chiếu bằng chứng với tiêu chí kiểm soát và báo cáo thiếu sót |

Trong nhóm nhỏ, một người có thể đảm nhận nhiều vai trò, nhưng vẫn cần ghi rõ ai thực hiện và ai kiểm tra/phê duyệt. Với thao tác nhạy cảm, nên tách người thay đổi cấu hình khỏi người phê duyệt hoặc người xác nhận kết quả khi điều kiện cho phép.

Kênh thông báo cần phân biệt tác vụ kỹ thuật thông thường, sự cố bảo mật và tình huống có thể ảnh hưởng nghĩa vụ hợp đồng/pháp luật. Khi nghi rò rỉ dữ liệu, bộ phận an ninh và pháp chế hoặc đầu mối được tổ chức chỉ định phải được tham gia theo quy trình hiện hành; không tự công bố kết luận chưa có căn cứ.

## 6. Bằng chứng kiểm toán cần những thuộc tính gì?

Một bằng chứng có thể dùng được cần đạt ít nhất các tiêu chí:

1. **Liên quan:** trực tiếp hỗ trợ một khẳng định hoặc tiêu chí kiểm soát.
2. **Có nguồn gốc:** ghi rõ hệ thống tạo dữ liệu, phạm vi tenant/subscription/resource, phương pháp xuất và quyền của người xuất.
3. **Đúng khoảng thời gian:** có timestamp, múi giờ và cửa sổ quan sát; dữ liệu ngoài kỳ kiểm toán chỉ nên dùng làm bối cảnh.
4. **Có thể kiểm tra lại:** ghi truy vấn, bộ lọc, policy ID, alert ID hoặc correlation ID đủ để người có quyền tái hiện kết quả nếu dữ liệu còn được lưu.
5. **Toàn vẹn:** lưu bản gốc, hạn chế sửa đổi, có hash hoặc cơ chế bảo vệ tương đương khi cần.
6. **Kiểm soát truy cập:** chỉ người có thẩm quyền mới được xem hoặc xử lý; tránh đưa log chứa thông tin cá nhân và bí mật vào ticket công khai.
7. **Có giải thích:** mô tả bằng chứng chứng minh điều gì, không chứng minh điều gì và những hạn chế dữ liệu.
8. **Lưu giữ theo chính sách:** nơi lưu, thời hạn giữ, yêu cầu legal hold và cách hủy sau khi hết nghĩa vụ phải được định nghĩa.

### 6.1. Chứng cứ cho sự cố và chứng cứ cho kiểm soát

| Câu hỏi kiểm toán | Bằng chứng phù hợp | Giới hạn cần diễn giải |
|---|---|---|
| Ai thay đổi Azure RBAC? | Azure Activity Log, role assignment hiện tại, change ticket | Activity Log phản ánh hoạt động control plane; không tự chứng minh người đó có động cơ xấu |
| Truy cập đăng nhập bất thường đã được điều tra chưa? | Entra sign-in logs, case, quyết định SOC và kết quả xử lý | Sign-in log có thể thiếu nếu ngoài thời hạn giữ hoặc thiếu điều kiện truy cập |
| Key Vault có bật audit log không? | Diagnostic settings và log đã được ingest, bằng chứng kiểm tra pipeline | Cấu hình hiện tại không tự chứng minh log đã tồn tại trong toàn bộ kỳ trước |
| Chính sách cấu hình có được tuân thủ? | Azure Policy assignment, compliance state, exemption, lịch sử remediation | Compliance chỉ đánh giá điều kiện policy được định nghĩa |
| Pipeline production có được phê duyệt? | Run ID, commit SHA, deployment record, approval và IAM permissions | Screenshot dashboard là bằng chứng hỗ trợ; cần liên kết bản ghi nguồn |
| Cảnh báo có người xử lý đúng hạn? | Alert ID, ticket có lịch sử chuyển trạng thái và timestamp, escalation log | Chỉ có trạng thái hiện tại không chứng minh thời điểm từng bước |
| Dữ liệu có khả năng phục hồi? | Backup job history, cấu hình retention và kết quả thử restore | “Backup successful” không thay thế thử phục hồi |
| Chi phí được kiểm soát? | Cost Management budget, cảnh báo chi phí, báo cáo phân tích và quyết định tối ưu | Budget alert không tự giới hạn chi phí Azure |

Một tiêu chí kiểm soát thường cần **nhiều nguồn bằng chứng**. Chẳng hạn, chứng minh thay đổi quyền đã được phê duyệt cần cả ticket phê duyệt, log thao tác thực tế và thông tin role assignment sau thay đổi.

### 6.2. Dữ liệu gốc, bản xuất và bản trình bày

Nên phân biệt:

- **Dữ liệu nguồn:** sự kiện được ghi trong Azure/Entra, ticket system hoặc hệ thống bảo mật.
- **Bản xuất bảo quản:** JSON, CSV hoặc bản ghi có cấu trúc được trích xuất theo bộ lọc xác định, lưu trong kho bằng chứng.
- **Bản phân tích:** truy vấn KQL, timeline, biểu đồ hoặc ghi chú của điều tra viên.
- **Bản trình bày:** báo cáo tóm tắt, ảnh chụp màn hình hay bảng kết luận gửi người kiểm toán.

Không sửa dữ liệu gốc hoặc ghi đè bản xuất gốc để “cho dễ đọc”. Nếu cần loại bỏ thông tin nhạy cảm khi chia sẻ, tạo **bản đã biên tập** riêng, nêu rõ trường bị che và giữ bản nguyên gốc tại nơi có quyền truy cập phù hợp.

Ảnh chụp màn hình hữu ích để giải thích giao diện, nhưng thường không đủ để xác minh tính đầy đủ của hàng nghìn sự kiện hoặc các thay đổi theo thời gian. Ưu tiên dữ liệu có cấu trúc và bằng chứng truy xuất được khi có thể.

## 7. Thu thập và bảo quản bằng chứng có kiểm soát

### 7.1. Chuỗi bảo quản bằng chứng (chain of custody)

Chain of custody mô tả bằng chứng đã được ai thu thập, lưu ở đâu, được ai truy cập/chuyển giao và có thay đổi gì từ khi thu thập tới khi kiểm toán. Mục tiêu là giúp người đánh giá tin rằng dữ liệu chưa bị thay đổi ngoài quy trình được ghi nhận.

Ví dụ một bản ghi:

~~~json
{
  "evidenceId": "EV-SEC-2026-0042-01",
  "incidentId": "SEC-2026-0042",
  "source": "Azure Activity Log",
  "scope": "/subscriptions/<SUBSCRIPTION_ID>",
  "eventWindowStartUtc": "2026-11-20T08:00:00Z",
  "eventWindowEndUtc": "2026-11-20T09:00:00Z",
  "collectedAtUtc": "2026-11-20T09:20:00Z",
  "collectedBy": "soc-analyst-01",
  "exportFormat": "JSON",
  "fileName": "EV-SEC-2026-0042-01.json",
  "sha256": "<SHA256_OF_SAVED_FILE>",
  "storageReference": "<RESTRICTED_EVIDENCE_OBJECT_URI>",
  "classification": "confidential",
  "retentionPolicy": "<APPROVED_POLICY_ID>",
  "notes": "Export of role assignment events; see query record."
}
~~~

Một manifest như trên **không tự chứng minh** rằng log đã được thu thập đúng hoặc file bất biến. Phải có file thực tế, nơi lưu được kiểm soát, lịch sử truy cập và phương pháp tính hash đi kèm. Mã SHA-256 dùng để nhận biết sự thay đổi nội dung của file đã xuất; nó không chứng minh dữ liệu bên trong là đúng hay không bị sửa trước khi xuất.

### 7.2. Quy trình thu thập tối thiểu

1. Ghi case ID, nguồn dữ liệu, người thao tác, tenant/subscription và điều kiện truy vấn.
2. Xuất phạm vi thời gian đủ rộng để hiểu trước, trong và sau tín hiệu; đánh dấu rõ khoảng thời gian theo UTC.
3. Ưu tiên xuất có cấu trúc, giữ nguyên toàn bộ trường cần thiết như event ID, resource ID, caller, correlation ID, status và timestamp.
4. Lưu bản xuất gốc tại kho bằng chứng có RBAC hạn chế, mã hóa và lưu nhật ký truy cập theo cấu hình tổ chức.
5. Tính hash trên **đúng file được lưu**, ghi hash vào manifest và bảo vệ manifest theo cùng quy trình.
6. Chỉ phân tích hoặc biên tập trên bản sao có kiểm soát; ghi lại người thao tác và phương pháp.
7. Khi chuyển giao, ghi người gửi, người nhận, thời điểm, vị trí mới và kết quả xác minh hash.
8. Giữ theo chính sách retention và legal hold nếu có; xóa theo lịch chỉ sau khi chắc chắn không còn nghĩa vụ bảo quản.

Kho bằng chứng có thể dùng Azure Blob Storage với encryption, private endpoint/network restrictions, Azure RBAC và cơ chế immutable storage phù hợp khi yêu cầu. **Immutable storage có các chế độ và điều kiện cấu hình riêng** (ví dụ time-based retention hoặc legal hold). Cần kiểm tra yêu cầu quản trị và thử nghiệm trước khi áp dụng cho dữ liệu cần khả năng thay đổi hoặc xóa. Không nhầm “Blob đã bật versioning” với bằng chứng chắc chắn không thể sửa hoặc xóa.

### 7.3. Kiểm tra toàn vẹn file bằng SHA-256

Trên máy thu thập có quyền và thư mục lưu bằng chứng đã phê duyệt, có thể chạy:

~~~powershell
Get-FileHash -Algorithm SHA256 -LiteralPath ".\EV-SEC-2026-0042-01.json"
~~~

Hoặc trên Linux:

~~~bash
sha256sum EV-SEC-2026-0042-01.json
~~~

Sau khi copy, tính lại hash trên bản nhận và đối chiếu với hash trong manifest. Nếu không khớp, cách xử lý phù hợp là cô lập file để kiểm tra nguyên nhân, không ghi đè hay âm thầm cập nhật hash.

Tránh in access token, connection string hoặc secret vào bằng chứng không cần thiết. Khi có dữ liệu cá nhân, cần áp dụng chính sách phân loại và quyền truy cập tương ứng. Trong tình huống có yêu cầu pháp chứng chính thức, nhóm an ninh/pháp chế phải định nghĩa thủ tục bảo toàn chuyên biệt.

## 8. Thực hành truy vấn bằng chứng trong Azure

Các đoạn lệnh sau minh họa điều tra **chỉ đọc**. Người chạy cần có quyền phù hợp và dữ liệu phải còn trong phạm vi lưu giữ.

### 8.1. Azure CLI: xem Azure Activity Log

Kiểm tra subscription hiện tại:

~~~bash
az account show --output table
~~~

Liệt kê sự kiện trong 24 giờ gần đây:

~~~bash
az monitor activity-log list --offset 24h --output json
~~~

Giới hạn ở resource group của ứng dụng:

~~~bash
az monitor activity-log list \
  --resource-group rg-orders-prod \
  --offset 24h \
  --query "[].{time:eventTimestamp,operation:operationName.value,status:status.value,caller:caller,resource:resourceId,correlation:correlationId}" \
  --output json
~~~

Kết quả từ lệnh trên chỉ phản ánh những sự kiện Activity Log có thể truy vấn tại thời điểm chạy. Khi tạo bằng chứng kiểm toán cần lưu cả lệnh, phạm vi, thời điểm truy vấn và file xuất. Việc xuất bản ghi có cấu trúc vẫn có thể bị giới hạn bởi phân trang, quyền hoặc thời hạn lưu; xác minh độ đầy đủ trước khi kết luận.

### 8.2. KQL: điều tra thay đổi role assignment

Nếu Azure Activity Log đã được gửi đến Log Analytics workspace và tạo dữ liệu trong bảng AzureActivity, có thể sử dụng Kusto Query Language:

~~~kusto
AzureActivity
| where TimeGenerated between (ago(24h) .. now())
| where OperationNameValue =~ "MICROSOFT.AUTHORIZATION/ROLEASSIGNMENTS/WRITE"
| project
    TimeGenerated,
    SubscriptionId,
    ResourceGroup,
    ResourceId,
    Caller,
    ActivityStatusValue,
    CorrelationId,
    OperationNameValue
| order by TimeGenerated asc
~~~

Truy vấn giúp tìm thao tác tạo/cập nhật role assignment. Tùy cấu trúc log và loại sự kiện, bạn có thể cần xem bản ghi chi tiết hoặc đối chiếu role assignment hiện tại để biết chính xác principal, role và scope bị thay đổi. Một thao tác “Write” chưa đủ để kết luận rằng quyền đã bị cấp trái phép.

Nếu cần theo dõi thao tác xóa quyền, kiểm tra thêm OperationNameValue tương ứng với ROLEASSIGNMENTS/DELETE. Tên trường và cách biểu diễn phụ thuộc bảng dữ liệu; hãy mở schema và một bản ghi thực tế trước khi kết luận.

### 8.3. KQL: điều tra đăng nhập Microsoft Entra ID

Nếu sign-in logs đã được gửi đến Log Analytics workspace, có thể truy vấn bảng SigninLogs:

~~~kusto
SigninLogs
| where TimeGenerated > ago(24h)
| where ResultType != "0"
| project
    TimeGenerated,
    UserPrincipalName,
    AppDisplayName,
    IPAddress,
    ResultType,
    ConditionalAccessStatus,
    CorrelationId
| order by TimeGenerated desc
~~~

Kết quả minh họa đăng nhập thất bại và thông tin hỗ trợ điều tra, **không tự chứng minh tài khoản đã bị xâm phạm**. Một số workload dùng service principal hoặc managed identity có dữ liệu trong những bảng sign-in riêng, tùy cấu hình xuất và loại license; không chỉ dựa vào bảng người dùng để kết luận không có hoạt động workload.

### 8.4. Kiểm tra pipeline log của dịch vụ

Ví dụ liệt kê diagnostic settings của một Azure resource:

~~~bash
az monitor diagnostic-settings list \
  --resource "/subscriptions/<SUBSCRIPTION_ID>/resourceGroups/<RESOURCE_GROUP>/providers/<PROVIDER_NAMESPACE>/<RESOURCE_TYPE>/<RESOURCE_NAME>" \
  --output json
~~~

Kết quả thể hiện cấu hình diagnostic settings của resource có hỗ trợ, chẳng hạn destination và category đã bật. Để chứng minh log thực sự được nhận, phải đối chiếu dữ liệu ở Log Analytics, Storage hoặc Event Hub tương ứng. Nếu không có log trong khoảng thời gian cần kiểm toán, ghi rõ khoảng thiếu và nguyên nhân đã xác định hoặc đang điều tra; không tự suy luận “không có sự kiện”.

### 8.5. Gắn bằng chứng với thay đổi và người phê duyệt

Một thay đổi role hợp lệ nên có chuỗi:

~~~text
Change ticket CHG-1428
   |
   +-- Người yêu cầu và lý do nghiệp vụ
   +-- Approval: người phê duyệt, thời gian UTC
   +-- Pull request/commit và pipeline run (nếu dùng IaC)
   +-- Azure Activity Log: operation + correlationId
   +-- Trạng thái role assignment sau thay đổi
   +-- Kết quả kiểm tra quyền và xác nhận đóng
~~~

Mỗi liên kết cần sử dụng ID cụ thể và có thể truy cập bởi nhóm kiểm toán theo quyền được cấp. Nếu hệ thống ticket chỉ chứa đường dẫn tới log hết hạn sau vài ngày, bằng chứng có thể không còn khi tới kỳ kiểm toán. Cần kế hoạch xuất/lưu phù hợp trước hạn.

## 9. Tình huống thực tế: cảnh báo cấp quyền bất thường

**Bối cảnh:** ứng dụng orders chạy tại subscription production, sử dụng Azure Key Vault và một pipeline CI/CD. Bộ phận an ninh nhận cảnh báo về thao tác role assignment mới trên resource group rg-orders-prod ngoài thời gian triển khai thường lệ.

### 9.1. Xác minh tín hiệu

Alert chỉ ra operation liên quan Microsoft.Authorization/roleAssignments/write. Analyst tạo case SEC-2026-0042, ghi thời gian UTC, resource ID, caller và correlation ID. Người xử lý đối chiếu:

- Activity Log cho thao tác, trạng thái và chuỗi sự kiện liên quan.
- Role assignment hiện tại để xác định principal, role và scope.
- Microsoft Entra sign-in/audit logs (nếu phù hợp) để hiểu danh tính gọi API.
- Run ID của pipeline và change ticket trong cùng cửa sổ thời gian.
- Các thao tác tiếp theo trên Key Vault hoặc resource khác nếu diagnostic logs đã được bật.

Có thể thấy caller là service principal của pipeline nhưng không có deployment được phê duyệt. Đó là tình huống cần điều tra thêm, chưa đủ để khẳng định bị tấn công.

### 9.2. Đánh giá và ứng phó

Nếu role được cấp là quyền cao trên production và không có giải thích hợp lệ, incident commander có thể nâng mức ưu tiên, yêu cầu đội IAM xác minh danh tính, kiểm tra nguồn token/credential và thu hẹp quyền hoặc dừng pipeline theo quy trình khẩn cấp.

Trước và trong thay đổi, nhóm cần bảo toàn log liên quan và ghi nhận role assignment ban đầu. Sau khi ngăn chặn, kiểm tra các thay đổi khác trong cùng thời gian, dấu hiệu truy cập dữ liệu, phạm vi tác động và nhu cầu xoay credential. Nếu phát hiện lỗi tự động hóa hợp lệ, nhóm vẫn cần sửa pipeline, tài liệu và approval để ngăn tái diễn.

### 9.3. Hồ sơ kiểm toán sau xử lý

| Artifact | Nội dung tối thiểu |
|---|---|
| SEC-2026-0042 | Timeline, severity, người xử lý, kết luận, quyết định và thời điểm |
| EV-01 | Xuất Azure Activity Log, câu lệnh/KQL, phạm vi và hash |
| EV-02 | Bản đối chiếu role assignment, scope và principal |
| EV-03 | Pipeline run, commit, thông tin phê duyệt hoặc ghi nhận thiếu phê duyệt |
| EV-04 | Entra log và Key Vault diagnostic log liên quan, nếu có |
| EV-05 | Hồ sơ action/rollback, người phê duyệt và kết quả |
| EV-06 | Kết quả kiểm tra cuối, cập nhật detection rule và action items |

Nếu log data plane chưa được bật, báo cáo phải ghi **không đủ khả năng kết luận** về một số thao tác đọc dữ liệu, thay vì suy ra chắc chắn không có truy cập. Đây là điểm quan trọng để bằng chứng được trình bày trung thực.

## 10. Tự động hóa cảnh báo và lưu bằng chứng an toàn

Azure Monitor Action Groups, Logic Apps, Azure Functions, Automation hoặc Microsoft Sentinel automation/playbooks (khi có triển khai) có thể hỗ trợ:

- Tạo case và phân công đội trực từ alert.
- Chuẩn hóa resource ID, severity, timestamp và liên kết tới log.
- Tra cứu metadata của resource, owner, tags và change window.
- Thu thập một số dữ liệu chỉ đọc theo mẫu, xuất có cấu trúc vào kho được kiểm soát.
- Gửi yêu cầu phê duyệt cho hành động khoanh vùng có rủi ro.
- Theo dõi quá hạn, nhắc escalation và lập báo cáo định kỳ.

Tách rõ **tự động hóa thu thập/đối chiếu** với **tự động hóa thay đổi hoặc xóa**. Chặn tài khoản, xóa tài nguyên, thay đổi network rule hoặc rotate credential có thể gây gián đoạn và làm thay đổi bằng chứng. Nếu có auto-remediation, phải xác định điều kiện kích hoạt, scope, idempotency, quyền quản lý, audit trail, cơ chế tạm dừng và rollback phù hợp.

Automation identity nên sử dụng managed identity ở dịch vụ Azure hỗ trợ hoặc workload identity federation trong CI/CD thay vì hard-code secret. Cấp RBAC tối thiểu, lưu secrets (nếu thực sự cần) trong giải pháp quản lý bí mật được phê duyệt. Đừng để workflow xử lý alert có quyền Owner toàn subscription chỉ vì cần ghi một artifact.

### Giảm nhiễu và cải thiện chất lượng alert

Khi alert quá nhiều, người trực dễ bỏ qua tín hiệu quan trọng. Có thể cải tiến theo chu kỳ:

1. Đo tỷ lệ false positive, alert trùng và alert không có owner.
2. Điều chỉnh ngưỡng, logic kết hợp, cửa sổ đánh giá, dynamic thresholds hoặc suppression theo khả năng của công cụ.
3. Bổ sung dữ liệu ngữ cảnh như environment, tag Criticality, change window và đối tượng chịu ảnh hưởng.
4. Gắn rule với runbook có bước xác minh và quyết định escalation.
5. Kiểm tra lại hiệu quả sau thay đổi và lưu lịch sử điều chỉnh rule.

Việc tắt rule chỉ nên thực hiện khi có quyết định được ghi nhận và biện pháp kiểm soát thay thế phù hợp; tránh giảm số alert bằng cách che mất tín hiệu rủi ro.

## 11. Mẫu hồ sơ xử lý cảnh báo

Mỗi tổ chức có thể dùng hệ thống case management khác nhau, nhưng một mẫu tối thiểu nên chứa các trường sau:

~~~yaml
caseId: SEC-2026-0042
alertSource: Azure Monitor
alertId: "<SOURCE_ALERT_ID>"
detectedAtUtc: "2026-11-20T08:41:00Z"
acknowledgedAtUtc: "2026-11-20T08:45:00Z"
tenantId: "<TENANT_ID>"
subscriptionId: "<SUBSCRIPTION_ID>"
resourceId: "<RESOURCE_ID>"
severity: P2
status: Investigating
owner: team-security-operations
summary: "Unplanned role assignment write on production resource group"
businessImpact: "Under investigation"
observedFacts:
  - "Role assignment write operation recorded"
hypotheses:
  - "Possible unapproved deployment credential use"
evidenceRefs:
  - EV-SEC-2026-0042-01
actions:
  - atUtc: "2026-11-20T09:10:00Z"
    approvedBy: "<APPROVER>"
    actor: "<OPERATOR>"
    description: "Restricted deployment identity pending review"
    outcome: "Completed; verified by IAM engineer"
decision: "Open - scope still being assessed"
nextReviewAtUtc: "2026-11-20T10:00:00Z"
~~~

Các giá trị trong mẫu chỉ mang tính minh họa, không mô tả một sự cố thực tế. Trong case cuối cùng nên bổ sung sự kiện theo thứ tự thời gian, liên kết bản ghi gốc, ai duyệt đóng, xác nhận khôi phục và nguyên nhân gốc nếu đã được điều tra đủ.

### Kiểm tra chất lượng hồ sơ trước khi kết thúc

- Có ID case và ID alert gốc không?
- Tất cả sự kiện và thao tác có timestamp UTC không?
- Có phân biệt sự kiện quan sát được với giả thuyết hoặc kết luận không?
- Đã xác định scope, tài nguyên, người có quyền và phạm vi dữ liệu liên quan chưa?
- Có bằng chứng cho những hành động được ghi là hoàn thành không?
- Có chỗ nào thiếu log và đã nêu giới hạn kết luận chưa?
- Bản gốc và hash có được lưu trong kho có quyền kiểm soát không?
- Người phê duyệt đóng và người sở hữu action items đã rõ chưa?

## 12. Các lỗi thường gặp

**Chỉ dựa vào severity của công cụ.** Alert severity và mức độ ảnh hưởng nghiệp vụ có thể khác nhau. Cần đánh giá môi trường, dữ liệu và phạm vi tác động.

**Đánh dấu “Resolved” nhưng không chứng minh đã khắc phục.** Trạng thái alert không thay thế log, kiểm tra sau khắc phục và xác nhận của chủ dịch vụ.

**Tin rằng Azure tự lưu mọi log vô thời hạn.** Mỗi nguồn có cơ chế lưu giữ và cấu hình xuất khác nhau. Cần cấu hình trước, thử truy vấn và theo dõi ingestion.

**Lấy screenshot thay cho dữ liệu gốc.** Screenshot có thể thiếu bộ lọc, timestamp, nội dung trang tiếp theo và ngữ cảnh. Nên kèm bản xuất JSON/CSV hoặc truy vấn truy xuất được khi phù hợp.

**Đưa secret và dữ liệu nhạy cảm vào ticket chung.** Log và bằng chứng có thể chứa dữ liệu cần phân loại. Chỉ chia sẻ qua kho và kênh được kiểm soát; dùng bản đã biên tập khi cần.

**Xóa tài nguyên hoặc rotate token mà không ghi nhận.** Điều này có thể làm mất dấu vết hoặc ảnh hưởng dịch vụ. Cần bảo toàn bằng chứng khả thi và ghi lý do hành động, đặc biệt trong tình huống khẩn cấp.

**Nhầm log control plane với data plane.** Activity Log cho thao tác ARM không chứng minh được mọi lần đọc dữ liệu của ứng dụng. Cần log riêng của dịch vụ.

**Tạo policy/audit rule rồi cho rằng đã có tuân thủ.** Phải có dữ liệu cho thấy rule đã được áp dụng, cảnh báo được tiếp nhận và ngoại lệ được quản lý.

**Không xác định người sở hữu bằng chứng.** Dữ liệu có thể nằm rải rác nhiều nơi, hết hạn hoặc không ai chịu trách nhiệm cung cấp khi kiểm toán. Hãy giao evidence custodian và quy định lịch lưu giữ.

## 13. Tự kiểm tra

1. **Một alert có tự động là incident không?** Không. Cần xác minh, phân loại và đánh giá tác động trước khi quyết định.
2. **Azure Activity Log có chứng minh mọi lần đọc secret từ Key Vault không?** Không. Cần cấu hình và xem log data plane phù hợp.
3. **Ba thành phần quan trọng trong hồ sơ bằng chứng là gì?** Nguồn gốc/phạm vi, timestamp/phương pháp thu thập và cơ chế kiểm tra tính toàn vẹn; còn cần quyền truy cập và giải thích hạn chế.
4. **Một file có hash SHA-256 có mặc nhiên là bằng chứng hợp lệ không?** Không. Hash chỉ giúp phát hiện nội dung thay đổi sau thời điểm tính; vẫn cần provenance và chuỗi bảo quản.
5. **Bằng chứng cho thay đổi Azure RBAC được phê duyệt cần gì?** Ticket/approval, log thực hiện, role assignment thực tế và kết quả kiểm tra.
6. **Nếu KQL không trả về kết quả, có được kết luận không xảy ra sự kiện không?** Chưa. Cần kiểm tra phạm vi truy vấn, quyền, nguồn log, thời hạn lưu giữ và ingestion.
7. **Sau khi dừng cảnh báo lỗi, tại sao vẫn cần post-incident review?** Để xác định nguyên nhân, thiếu sót kiểm soát và biện pháp ngăn tái diễn.
8. **Có nên tự động xóa toàn bộ workload khi nhận cảnh báo security high không?** Không nên mặc định. Cần xét khả năng dương tính giả, ảnh hưởng tới bằng chứng, phạm vi và phê duyệt theo runbook.
9. **Ai quyết định thời hạn lưu bằng chứng?** Chính sách của tổ chức dựa trên rủi ro, hợp đồng, yêu cầu kiểm toán và luật áp dụng; không có một thời hạn chung cho mọi trường hợp.
10. **Tại sao phải ghi giới hạn dữ liệu trong báo cáo?** Để tránh kết luận vượt quá những gì nguồn bằng chứng có thể chứng minh.

## 14. Tài liệu tham khảo

- [Azure Monitor documentation](https://learn.microsoft.com/azure/azure-monitor/) — cảnh báo, log, metric và diagnostic settings.
- [Azure Activity Log](https://learn.microsoft.com/azure/azure-monitor/essentials/activity-log) — sự kiện control plane trong subscription.
- [Azure Monitor Logs / KQL](https://learn.microsoft.com/azure/azure-monitor/logs/log-query-overview) — truy vấn và phân tích log.
- [Microsoft Defender for Cloud](https://learn.microsoft.com/azure/defender-for-cloud/) — security posture, khuyến nghị và cảnh báo bảo mật.
- [Microsoft Sentinel](https://learn.microsoft.com/azure/sentinel/) — phát hiện, điều tra và điều phối incident.
- [Microsoft Entra monitoring and health](https://learn.microsoft.com/entra/identity/monitoring-health/) — nhật ký đăng nhập và kiểm toán danh tính.
- [Azure Policy](https://learn.microsoft.com/azure/governance/policy/) — đánh giá tuân thủ cấu hình.
- [Azure Blob immutable storage](https://learn.microsoft.com/azure/storage/blobs/immutable-storage-overview) — cơ chế bảo vệ dữ liệu lưu giữ.
- [Azure RBAC](https://learn.microsoft.com/azure/role-based-access-control/overview) — phân quyền theo phạm vi tài nguyên.

Trong môi trường thực tế, luôn đối chiếu cấu hình, bảng log và tính năng đang được triển khai. Báo cáo kiểm toán tốt cần thể hiện cả các bằng chứng hỗ trợ kết luận lẫn những giới hạn dữ liệu còn tồn tại.
