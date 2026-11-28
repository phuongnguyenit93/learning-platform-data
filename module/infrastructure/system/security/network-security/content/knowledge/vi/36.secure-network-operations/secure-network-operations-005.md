# Tách nhiệm vụ giữa người yêu cầu và người duyệt trong vận hành mạng an toàn

## 1. Vì sao phải tách người yêu cầu và người duyệt?

Một kỹ sư mạng nhận đề nghị mở kết nối từ subnet ứng dụng đến cơ sở dữ liệu, sửa chính sách VPN, thêm ngoại lệ DNS hoặc tắt tạm một rule IDS/IPS. Thao tác kỹ thuật có thể chỉ mất vài phút, nhưng thay đổi ấy có thể mở thêm đường cho kẻ tấn công, làm mất khả năng giám sát, gián đoạn dịch vụ hoặc gây khó khăn khi điều tra.

Nếu **một người vừa tạo đề nghị, tự phê duyệt, tự đưa lên production và tự xác nhận thành công**, tổ chức thiếu điểm kiểm soát độc lập để phát hiện sai phạm vi, xung đột lợi ích, sai mục đích hoặc cấu hình nguy hiểm. Đây là rủi ro của việc thiếu **Segregation/Separation of Duties (SoD) — phân tách nhiệm vụ**.

**Tách nhiệm vụ giữa người yêu cầu và người duyệt** nghĩa là một thay đổi có rủi ro phải được **người có thẩm quyền độc lập với người đề xuất** đánh giá và cho phép trước khi được thực hiện. Người duyệt cần có đủ thông tin để quyết định, không chỉ bấm nút “Approve” theo thói quen.

Chủ đề này thuộc chương **Quản trị vận hành mạng an toàn** trong module **SECURITY_NETWORK_SECURITY**, phục vụ quản lý cấu hình và vận hành các lớp phòng vệ như phân đoạn mạng, firewall, VPN/ZTNA, IDS/IPS, bảo vệ DNS, thiết bị Wi-Fi, hệ thống cloud, kênh quản trị và mạng giám sát xâm nhập.

Mục tiêu bài học:

- Hiểu mục đích, giới hạn và cách thiết kế SoD, maker-checker, four-eyes và dual control.
- Phân biệt vai trò **người yêu cầu, người sở hữu tài sản, người đánh giá, người phê duyệt, người triển khai, người xác minh và người kiểm toán**.
- Thiết kế quy trình phê duyệt thay đổi firewall, ACL, VPN, DNS, IDS/IPS, cloud network và tài khoản đặc quyền.
- Áp dụng RBAC, ABAC, IAM, PAM, GitOps/IaC, policy-as-code và audit để ngăn tự duyệt, sửa nội dung sau duyệt hoặc bỏ qua workflow.
- Xác định trường hợp cần hai người, hai nhóm độc lập hoặc cơ chế phê duyệt tự động theo chính sách đã được thẩm định.
- Xử lý thay đổi khẩn cấp, nhóm nhỏ, làm việc ngoài giờ và ngoại lệ mà không biến “khẩn cấp” thành đường tắt thường trực.
- Đo lường hiệu quả kiểm soát thông qua bằng chứng, thời gian xử lý, vi phạm chính sách và tỷ lệ thay đổi thất bại.

> **Nguyên tắc:** Người yêu cầu phải trình bày **mục tiêu và thay đổi đề xuất**; người duyệt phải đánh giá **sự cần thiết, phạm vi và rủi ro**; người triển khai chỉ áp dụng **đúng phiên bản đã được duyệt**; người xác minh kiểm tra **trạng thái thực tế và hậu quả**.

## 2. Thuật ngữ: SoD, maker-checker, four-eyes, dual control

Các khái niệm có liên quan nhưng không hoàn toàn đồng nghĩa:

| Thuật ngữ | Ý nghĩa | Ví dụ trong vận hành mạng |
|---|---|---|
| **Separation of Duties (SoD)** | Phân tách các chức năng có thể tạo xung đột hoặc cho phép một người tự hoàn thành chuỗi hành động rủi ro | Người tạo firewall rule không được tự duyệt rule đó |
| **Maker-checker** | Người tạo thay đổi và người kiểm tra/phê duyệt là hai chủ thể khác nhau | Kỹ sư tạo pull request; reviewer độc lập xem diff và phê duyệt |
| **Four-eyes principle** | Một hành động quan trọng được ít nhất hai người xem xét hoặc xác nhận | Điều chỉnh route/ACL quản trị cần người thứ hai xác nhận |
| **Dual control** | Hành động chỉ thực hiện khi có sự tham gia hoặc ủy quyền của ít nhất hai chủ thể, đôi khi đồng thời | Mở khóa thao tác đặc biệt bằng hai quyền tách biệt |
| **Least privilege** | Mỗi người chỉ có quyền cần thiết trong thời gian cần thiết | Người yêu cầu được tạo ticket nhưng không có quyền push production |
| **Peer review** | Đánh giá kỹ thuật bởi người khác; có thể là một bước SoD | Kiểm tra ACL có làm lộ subnet quản trị hay không |
| **Change approval** | Quyết định cho phép triển khai một thay đổi trong điều kiện cụ thể | Asset owner và security approver duyệt mở cổng trong 24 giờ |
| **Post-change verification** | Xác minh kết quả và tác dụng ngoài dự kiến sau khi áp dụng | Kiểm tra traffic đúng kỳ vọng, IDS/IPS logs và rollback readiness |

**Điểm phân biệt quan trọng:** Two-person review không mặc nhiên đảm bảo SoD nếu cả hai dùng chung tài khoản, cùng có quyền bypass kiểm soát hoặc người yêu cầu có thể tự sửa danh sách người duyệt. Ngược lại, SoD không bắt buộc phải có hai người thao tác cùng lúc trên thiết bị; có thể dùng quy trình một người yêu cầu, người khác phê duyệt và hệ thống tự triển khai sau khi kiểm tra.

SoD là **một kiểm soát quản trị kết hợp kỹ thuật**. Nó không đảm bảo thay đổi sẽ luôn đúng, không ngăn tuyệt đối thông đồng, không thay thế kiểm thử cấu hình hoặc điều tra khi có sự cố.

## 3. Rủi ro nếu thiếu phân tách nhiệm vụ

### 3.1. Các trường hợp điển hình

1. **Firewall:** kỹ sư tự thêm rule cho phép `0.0.0.0/0` tới cổng quản trị và tự phê duyệt; nhầm một CIDR có thể biến mạng quản trị thành tài sản public.
2. **VPN/ZTNA:** người quản trị tự nâng quyền mình vào nhóm quản trị hạ tầng mà không có xác minh nhu cầu.
3. **IDS/IPS:** người trực tắt signature gây false positive nhưng cũng làm mất lớp phát hiện tấn công khác; không có độc lập đánh giá phạm vi.
4. **DNS security:** một cá nhân tự allowlist domain mới rồi đánh dấu là ngoại lệ vĩnh viễn, không có owner và hạn hết hiệu lực.
5. **Cloud:** người có quyền tạo security group đồng thời được sửa rule và xóa audit logs, làm khó truy vết.
6. **Routing:** một thay đổi BGP hoặc static route sai có thể hút traffic qua mạng không được giám sát.
7. **Wi-Fi/NAC:** người vận hành tự nới policy SSID guest để truy cập nội bộ, vượt phân đoạn.
8. **Certificate/secret:** một người vừa cấp, phê duyệt, phân phối và thu hồi chứng chỉ dành cho controller trọng yếu.

Không nên đồng nhất mọi thao tác với cùng mức rủi ro. Đổi nhãn mô tả thiết bị có thể đủ theo change chuẩn hóa; mở đường từ Internet vào management plane lại cần kiểm soát chặt hơn.

### 3.2. SoD giảm rủi ro gì?

| Nguy cơ | Tác dụng của phê duyệt độc lập | Kiểm soát vẫn cần bổ sung |
|---|---|---|
| Sai cấu hình do vô ý | Reviewer phát hiện nhầm source/destination, port, thứ tự rule | Lint, test policy, canary, rollback |
| Mở rộng đặc quyền ngoài nhu cầu | Người duyệt yêu cầu business justification và phạm vi tối thiểu | IAM least privilege, JIT, access review |
| Thay đổi không có chủ sở hữu | Buộc xác định owner, ticket, thời hạn và người chịu rủi ro | CMDB, inventory, định kỳ rà soát |
| Tự phê duyệt hành vi gian lận | Yêu cầu chủ thể độc lập chấp thuận | Chống bypass, audit bất biến, giám sát độc lập |
| Sai khác giữa điều được duyệt và điều triển khai | Gắn approval vào exact diff/version | CI/CD gates, artifact signing, deployment attestation |
| Thiếu trách nhiệm khi sự cố | Có record ai đề nghị, ai duyệt, ai thực hiện | Change logs, NTP, SIEM, chain of custody |
| Khó thu hồi ngoại lệ | Người duyệt đặt expiry, điều kiện đóng, review | Tự động hết hạn, reconciliation |

**Mục đích SoD không phải tạo càng nhiều chữ ký càng tốt** mà là tạo một kiểm tra độc lập, có khả năng tác động đến quyết định trước khi rủi ro được đưa vào môi trường thực.

## 4. Các vai trò trong một thay đổi mạng

Một quy trình được kiểm soát thường có nhiều vai trò logic:

| Vai trò | Quyền và trách nhiệm chính | Không nên tự làm |
|---|---|---|
| **Requester / Maker — Người yêu cầu** | Nêu nhu cầu kinh doanh, tài sản, rule đề xuất, thời hạn, tác động và thông tin kiểm thử | Tự phê duyệt thay đổi của mình |
| **Service/Asset Owner** | Xác nhận tài sản, mục đích, SLO, quyền sở hữu luồng và phạm vi chấp nhận | Phê duyệt rủi ro của hệ thống không thuộc thẩm quyền |
| **Technical Reviewer** | Kiểm tra logic cấu hình, thứ tự rule, NAT, route, security impact, rollback | Bỏ qua cảnh báo vì tin người yêu cầu |
| **Security Approver / Risk Owner** | Xem xét rủi ro, ngoại lệ và tác động đến guardrails; chấp thuận hoặc từ chối theo thẩm quyền | Tự cấp quyền vượt phạm vi role hoặc tự sửa bằng chứng duyệt |
| **Change Manager / CAB** | Điều phối lịch, phụ thuộc, blackout window, xung đột thay đổi | Thay thế toàn bộ kiểm tra chuyên môn bằng dấu duyệt hình thức |
| **Implementer / Deployer** | Thực thi đúng phiên bản, ghi nhật ký, theo dõi canary và rollback | Tự đổi nội dung sau phê duyệt rồi triển khai mà không duyệt lại |
| **Verifier / Validator** | Kiểm tra actual state, traffic, monitoring, drift và impact sau thay đổi | Tự báo PASS nếu chưa có chứng cứ |
| **Auditor / SOC** | Giám sát việc tuân thủ, phát hiện bypass, kiểm tra trail và sự kiện trái phép | Tự xóa/chỉnh audit về hoạt động mình cần kiểm tra |

Một người có thể là **requester của ticket A** và **approver của ticket B** nếu hai thay đổi thực sự độc lập, họ đủ thẩm quyền và chính sách cho phép. SoD không nhất thiết cấm một người sở hữu nhiều vai trò trong mọi tình huống; điều cần ngăn là **cặp quyền xung đột trên cùng đối tượng/quy trình**.

### 4.1. RACI tham khảo

| Hoạt động | Requester | Asset Owner | Security Approver | Implementer | Verifier |
|---|---|---|---|---|---|
| Xác định mục tiêu nghiệp vụ | R | A | C | C | I |
| Đánh giá ảnh hưởng dịch vụ | C | A/R | C | R | C |
| Đánh giá rủi ro bảo mật | C | C | A/R | C | C |
| Phê duyệt triển khai | I | A/C theo chính sách | A theo mức rủi ro | I | I |
| Thực hiện thay đổi | I | I | I | A/R | I |
| Kiểm tra sau thay đổi | C | A/C | C | R | R |
| Chấp nhận ngoại lệ tồn đọng | I | A hoặc C | A hoặc R theo governance | I | C |

*R: Responsible; A: Accountable; C: Consulted; I: Informed.* Ma trận chỉ minh họa. Tổ chức cần xác định chính xác một chủ thể **chịu trách nhiệm cuối** cho từng quyết định, tránh phê duyệt kép mơ hồ dẫn tới không ai thực sự chịu trách nhiệm.

### 4.2. Independence không chỉ là khác tên người

Sự độc lập cần được xác minh theo thực tế:

- Người yêu cầu và người duyệt dùng **tài khoản định danh riêng**; tài khoản chia sẻ không phù hợp để xác minh danh tính.
- Người yêu cầu **không thể tự gán vai trò approver** hoặc sửa nhóm IAM/Code Owners liên quan tới ticket của mình.
- Người duyệt có **thẩm quyền và năng lực đánh giá rủi ro**, không chỉ là đồng nghiệp được chọn ngẫu nhiên.
- Nếu hai người cùng chịu áp lực kết quả hoặc xung đột lợi ích lớn, tổ chức có thể cần reviewer từ nhóm Security/Risk độc lập.
- Người triển khai không thể dùng quyền admin bypass policy thường xuyên mà không tạo alert và review riêng.
- Audit trail do hệ thống có ranh giới quyền bảo vệ, không chỉ là một dòng comment có thể bị xóa.

## 5. Quy trình chuẩn: từ yêu cầu đến xác minh

~~~mermaid
flowchart TD
    A["Requester tạo change request"] --> B["Kiểm tra scope, owner, thông tin bắt buộc"]
    B --> C["Phân loại rủi ro và xác định approver"]
    C --> D["Technical/security review và policy checks"]
    D --> E{"Đủ thông tin, đúng baseline?"}
    E -->|"Không"| F["Trả lại requester để chỉnh sửa"]
    F --> B
    E -->|"Có"| G["Approver độc lập xét exact change version"]
    G --> H{"Approve?"}
    H -->|"Reject"| I["Ghi lý do; không triển khai"]
    H -->|"Approve"| J["Đóng dấu version/hash, TTL và điều kiện"]
    J --> K["Deployment gate kiểm tra approval còn hiệu lực"]
    K --> L["Implementer/automation triển khai đúng artifact"]
    L --> M["Post-change verification: config, traffic, logs"]
    M --> N{"Pass và trong phạm vi?"}
    N -->|"Không"| O["Pause/rollback theo runbook, mở incident nếu cần"]
    N -->|"Có"| P["Ghi evidence, owner, expiry, đóng ticket"]
~~~

### 5.1. Bước 1 — Đề nghị đủ ngữ cảnh

Một yêu cầu mở firewall rule nên có tối thiểu:

- **Change ID**, người yêu cầu, asset/service owner và business justification.
- **Source và destination** theo asset ID/CIDR/FQDN phù hợp, ingress/egress zone, port, protocol, hướng lưu lượng.
- **Policy hiện tại và policy đề xuất**, thay đổi cụ thể ở mức diff (bao gồm thứ tự rule, NAT, IPv4/IPv6).
- **Phân loại dữ liệu**, môi trường (lab/staging/prod) và tài sản phụ thuộc.
- **Khoảng thời gian** cần rule, expiry cho ngoại lệ, cửa sổ thực hiện UTC.
- **Tác động/rủi ro**, biện pháp giảm thiểu, thay đổi đồng thời và người theo dõi.
- **Kế hoạch test**, acceptance criteria, rollback, chỉ số vận hành cần giám sát.
- **Evidence links** tới inventory, threat model hoặc kiến trúc liên quan.

Yêu cầu “mở mạng cho ứng dụng chạy” là chưa đủ. Cần xác định **dịch vụ nào, từ đâu đến đâu, tại sao, trong bao lâu**; tránh rule `any-any` được phê duyệt chỉ vì thiếu thông tin.

### 5.2. Bước 2 — Phân loại mức rủi ro

Có thể dùng các lớp:

| Phân loại | Ví dụ | Phương thức phê duyệt gợi ý |
|---|---|---|
| **Standard/pre-approved** | Thay đổi lặp lại có mẫu chuẩn, tác động thấp, đã được phê duyệt phương pháp | Workflow tự động theo policy, kiểm tra điều kiện, audit; không phải tự duyệt tự do |
| **Normal/medium** | Cho phép service nội bộ qua segment đã quản lý, thêm nguồn monitoring | Asset owner và reviewer độc lập theo ma trận |
| **High risk** | Mở cổng từ Internet, thay management plane, bypass security control | Security/risk approver có thẩm quyền, có thể cần hai cấp duyệt |
| **Emergency** | Khôi phục dịch vụ khẩn, vá chặn luồng nguy hiểm đang diễn ra | Quy trình khẩn cấp có giới hạn và review hậu kiểm |
| **Prohibited** | Tắt toàn bộ audit để “giảm tải”, mở mọi subnet không lý do | Từ chối; chỉ có thể xử lý qua quy trình ngoại lệ đặc biệt có thẩm quyền nếu pháp luật/chính sách cho phép |

Đây là cách chia minh họa. Mỗi tổ chức phải xác định điều kiện chính xác bằng risk appetite, phân loại dữ liệu, regulatory requirements và khả năng chịu lỗi.

### 5.3. Bước 3 — Người duyệt đánh giá

Reviewer/approver nên đặt những câu hỏi:

1. Đúng asset owner, business need, tài sản được phép và phạm vi?
2. Có phương án **ít quyền hơn**: source cụ thể, port cụ thể, TTL ngắn hơn, access via bastion/ZTNA, mTLS?
3. Có ảnh hưởng segment nhạy cảm, customer data, DNS/DHCP, monitoring, IDS/IPS hay đường quản trị?
4. Có policy trùng lặp, shadowed rule, rule trước đó đã cho phép, NAT hoặc route bỏ sót?
5. Có rủi ro tạo bypass qua IPv6, VPN split tunnel, cloud security groups, Wi-Fi guest?
6. Có cần hai bên phê duyệt: owner của source **và** owner của destination, hoặc cả Security?
7. Có test case cho **traffic được phép** và **traffic phải bị chặn**?
8. Có kế hoạch rollback và kênh OOB nếu vô tình khóa quản trị?
9. Hạn hiệu lực và cách thu hồi ngoại lệ có rõ?
10. Nội dung duyệt có đúng **diff/version** sẽ đưa vào production không?

**Approval phải gắn với một yêu cầu có nội dung xác định**, không chỉ với tên ticket. Nếu người yêu cầu sửa source từ một /32 thành /0 sau khi được duyệt, quyết định phê duyệt cũ không còn áp dụng.

### 5.4. Bước 4 — Thực hiện đúng bản đã duyệt

Trước lúc triển khai, hệ thống hoặc implementer cần xác minh:

- Ticket vẫn ở trạng thái **approved**, chưa hết hạn/chưa bị revoke.
- Người yêu cầu và người duyệt **khác danh tính độc lập**, và người duyệt đủ quyền.
- Đích, phạm vi, môi trường, time window và artifact hash khớp với bản được duyệt.
- Không có commit mới, config drift hoặc thay đổi phụ thuộc làm đánh giá rủi ro lỗi thời.
- Không có incident đang diễn ra, freeze window hoặc điều kiện dừng liên quan.
- Công cụ triển khai có quyền **tối thiểu**, ghi log và khả năng rollback.

Automation chỉ nên triển khai **artifact đã được kiểm tra**, không tái tính thay đổi với input chưa được phê duyệt rồi âm thầm mở rộng phạm vi.

### 5.5. Bước 5 — Kiểm tra sau thay đổi

Kết quả “lệnh chạy thành công” không đủ. Kiểm tra:

- **Desired vs actual:** config effective trên đúng firewall/device/region/tenant, kể cả rule order và backend.
- **Traffic đúng kỳ vọng:** kết nối hợp lệ chạy, kết nối trái policy vẫn bị deny; kiểm tra từ các source zone liên quan.
- **Khả năng giám sát:** firewall/IDS/IPS/DNS/VPN logs, alert, NTP, SIEM ingestion không bị mất ngoài dự kiến.
- **Độ ổn định:** latency, packet loss, session table, CPU, client error rate và ứng dụng.
- **Thời hạn ngoại lệ:** auto-expiry/revert hoặc review có owner và thời gian.
- **Bằng chứng:** người kiểm tra, UTC, phiên bản cấu hình, test ID, outcome, sai lệch và quyết định đóng/rollback.

## 6. SoD thực sự phải được cưỡng chế bằng quyền

Một checklist giấy không đủ nếu người yêu cầu vẫn có quyền tự deploy và tự sửa audit. Thiết kế quyền nên ngăn **toxic combinations** — những tổ hợp quyền cho phép một chủ thể tự hoàn thành chuỗi rủi ro.

### 6.1. Ma trận các cặp quyền xung đột

| Cặp quyền nguy hiểm | Ví dụ lạm dụng | Cơ chế hạn chế |
|---|---|---|
| Create change + Approve same change | Người đề xuất tự chấp thuận | Workflow kiểm tra identity, policy `requester != approver` |
| Approve + Edit approved payload | Sửa CIDR/port sau khi duyệt | Immutable revision, digest, revoke approval khi đổi |
| Create access + Grant own role | Tự nâng lên network-admin | PAM/IAM role separation, JIT, approval bên ngoài |
| Deploy production + Disable audit | Thay rule và che log | Tách quyền log storage, alerts từ SIEM/Cloud Audit |
| Manage approval group + Self-approve | Tự thêm mình vào nhóm reviewers | Quản trị entitlement độc lập, access review |
| Modify CI/CD pipeline + Bypass gate | Bỏ review để chạy pipeline | Protected branch, signed builds, restricted runner permissions |
| Update firewall + Change evidence | Tự thay thiết bị và xóa config diff | Off-device audit, immutable/retained evidence |
| Create + Approve + Close risk exception | Đưa ngoại lệ thành vĩnh viễn | Risk owner độc lập, TTL, review định kỳ |

Không phải mọi cặp trên đều tuyệt đối cấm trong mọi tổ chức; nhưng nếu chấp nhận kết hợp quyền vì giới hạn nhân lực, phải **ghi nhận rủi ro và kiểm soát bù trừ** có thể kiểm toán, không xem là mặc nhiên đủ SoD.

### 6.2. RBAC, ABAC và phân tách động

- **RBAC (Role-Based Access Control):** requester, approver, implementer, auditor có role riêng; giảm khả năng người duyệt được chọn tùy tiện.
- **ABAC (Attribute-Based Access Control):** quyết định còn dựa vào asset owner, risk tier, site, environment, dữ liệu nhạy cảm, thời điểm và mối quan hệ với requester.
- **Static SoD:** một user không thể đồng thời sở hữu hai role xung đột trong cùng phạm vi.
- **Dynamic SoD:** một user có thể sở hữu nhiều role trong tổ chức nhưng **không được thực hiện hai hành động xung đột trên cùng ticket/artifact hoặc cùng chuỗi giao dịch**.
- **PAM/JIT:** cấp quyền deploy production chỉ sau khi approval còn hiệu lực, cho thời gian ngắn; ghi session và thu hồi tự động.
- **Identity lifecycle:** khi chuyển nhóm/nghỉ việc, thu hồi role, cert, token, VPN/ZTNA membership và các phiên còn tồn tại.

Chỉ so sánh `created_by != approved_by` chưa đủ nếu một người có nhiều tài khoản hoặc service account dùng chung. Cần ràng buộc danh tính với chủ thể thật qua IdP và không để một người tự chi phối cả hệ thống định danh lẫn approval workflow.

### 6.3. Quyền phê duyệt là quyền đặc biệt

Người được quyền Approve có thể làm thay đổi ranh giới an ninh mà không trực tiếp cấu hình. Do đó:

- Cấp approver role theo **phạm vi tài sản và loại rủi ro**, không gắn vĩnh viễn cho mọi nhân viên senior.
- Yêu cầu MFA/step-up authentication khi duyệt thay đổi nhạy cảm nếu nền tảng hỗ trợ.
- Giới hạn approver delegation; ghi lại ủy quyền, owner, thời gian và lý do.
- Theo dõi tỷ lệ approve quá nhanh/không có review, phê duyệt hàng loạt và các cặp người liên tục duyệt cho nhau.
- Thu hồi quyền khi thay vai trò và thực hiện access certification định kỳ.

**Một người ký tên trên ticket** không tự động tạo ra kiểm soát độc lập nếu họ không có thẩm quyền hoặc không xem được bản diff và mức rủi ro.

## 7. Liên kết quyết định phê duyệt với đúng nội dung triển khai

Một lỗi nguy hiểm là **approve lúc T1, thay đổi cấu hình lúc T2**, nhưng hệ thống vẫn hiển thị “approved”. Phải ngăn phê duyệt của phiên bản cũ được dùng cho payload mới.

### 7.1. Mô hình dữ liệu thay đổi

~~~yaml
change_id: CHG-NET-2026-005
requester:
  principal_id: "idp:user:requester-17"
  role: "network-engineer"
asset_owner: "team:payments"
risk:
  tier: high
  rationale: "Mở cổng giữa hai segment có phân quyền"
environment: production
target:
  device_group: "firewall-east"
  scope: "app-zone to db-zone"
change_artifact:
  revision: "rev-4"
  sha256: "<digest của nội dung triển khai đã được tạo>"
  type: "policy-diff"
  repository_ref: "protected-repo/changes/CHG-NET-2026-005"
approvals:
  - principal_id: "idp:user:security-approver-2"
    decision: approved
    bound_revision: "rev-4"
    bound_sha256: "<cùng digest của nội dung>"
    approved_at_utc: "2026-11-28T09:00:00Z"
    valid_until_utc: "2026-11-28T10:00:00Z"
    justification: "Phạm vi, owner và rollback đã được xác minh"
deployment:
  status: pending
  only_if_exact_artifact_matches: true
  allowed_window_utc: "2026-11-28T09:15:00Z/2026-11-28T10:00:00Z"
  execution_identity: "service:network-deployer"
  require_audit: true
~~~

Đây là **mẫu thông tin học tập**, không phải một sự kiện thật hoặc schema của một sản phẩm cụ thể; hash chỉ có giá trị khi được tính từ đúng canonical representation của artifact và được kiểm tra tại deployment gate.

### 7.2. Điều kiện bắt buộc của deployment gate

Một logic chính sách minh họa:

~~~text
function mayDeploy(change, approval, actor, now):
    require change.status == "APPROVED"
    require approval.decision == "approved"
    require approval.request_id == change.id
    require approval.approver_identity != change.requester_identity
    require approval.approver_is_authorized_for(change.asset, change.risk)
    require approval.subject_revision == change.current_revision
    require approval.subject_digest == digest(change.actual_deploy_artifact)
    require now within change.approved_window
    require now < approval.expiration
    require not approval.revoked
    require actor.has_time_bounded_deploy_permission(change.target)
    require no_blocking_freeze_or_stop_condition
    return true

On any failed requirement:
    do_not_deploy()
    log_decision_with_reason()
~~~

Mẫu giả mã không giải quyết mọi kiểm tra an ninh: phải có cơ chế định danh đáng tin cậy, bảo vệ secret, replay protection, phòng ngừa race condition, đảm bảo trạng thái gate và artifact được xác minh lại **ngay lúc áp dụng**, không chỉ lúc request đi vào hàng đợi.

### 7.3. Re-approval và thay đổi sau duyệt

Nếu sửa:

- Source/destination, CIDR, cổng, protocol, NAT/route.
- Environment, account/region, vùng mạng hoặc nhóm thiết bị.
- Độ rộng của privilege, thời hạn, hướng kết nối.
- Rule precedence, cách bypass IDS/IPS hoặc DNS filtering.
- Cấu hình ứng dụng làm thay đổi tác động bảo mật.

...thì approval thường phải bị **invalidate** và trở về bước review. Đừng dựa hoàn toàn vào nhãn “minor change”; quyết định có cần duyệt lại nên do chính sách áp theo **risk và semantic diff**.

Một thay đổi comment thuần túy có thể được xử lý khác nếu policy có quy định, nhưng hệ thống phải xác định artifact nào được bind tới approval, các phần nào ảnh hưởng hành vi và cách audit. Nếu không kiểm soát chắc semantic diff, chọn hướng an toàn là yêu cầu duyệt lại.

## 8. Áp dụng trong GitOps, IaC và CI/CD

Nhiều tổ chức quản lý firewall policies, cloud security groups, Kubernetes NetworkPolicy hoặc DNS config dưới dạng code. **Pull request (PR) + protected branch + deployment pipeline** có thể thực thi SoD tốt nếu được thiết kế cẩn thận.

### 8.1. Luồng GitOps an toàn

~~~mermaid
flowchart TD
    A["Engineer tạo branch và PR"] --> B["Automated lint / policy-as-code / diff"]
    B --> C{"Có vi phạm guardrail?"}
    C -->|"Có"| D["Block và yêu cầu sửa"]
    C -->|"Không"| E["Owner + security reviewer độc lập"]
    E --> F{"Phê duyệt commit hiện tại?"}
    F -->|"Không"| G["Reject / request changes"]
    F -->|"Có"| H["Protected merge; commit/release reference"]
    H --> I["CI/CD kiểm tra approval và artifact provenance"]
    I --> J["Deploy canary/waves bằng service identity"]
    J --> K["Post-change policy/traffic tests"]
    K --> L["Config hash, applied version, audit, close"]
~~~

**Các điều kiện quan trọng:**

- PR author không được self-approve; reviewer được chọn theo Code Owners/asset ownership và đủ thẩm quyền.
- Push commit mới sau approval phải làm mất hiệu lực review khi policy yêu cầu; hệ thống không được giữ “approved” trên nội dung đã đổi.
- Branch protection ngăn force-push, bypass, tự merge khi chưa đủ review/check, và ngăn sửa pipeline/Code Owners chỉ để vượt kiểm soát.
- Pipeline runner/service identity chỉ có quyền cần thiết cho từng environment, không có credential admin chung lộ ở build logs.
- Artifact được deploy có ID/hash xác định; pipeline không lấy cấu hình ngoài repo chưa review và gộp vào runtime mà không kiểm soát.
- Config actual trên thiết bị/cloud cần được đối chiếu sau triển khai; merge PR thành công không đồng nghĩa enforcement đã cập nhật.
- Ngay cả admin có quyền emergency bypass cũng phải có audit riêng, giới hạn và review hậu kiểm.

### 8.2. Hai lớp kiểm soát: phòng ngừa và phát hiện

**Preventive controls:** policy gate, RBAC/IAM, branch protection, two-person review, restricted API token và change binding ngăn hành động trái quy trình ngay tại thời điểm thực hiện.

**Detective controls:** log kiểm tra hằng ngày, config drift detection, cảnh báo thay đổi production ngoài pipeline, đối chiếu SIEM, access review và kiểm toán độc lập phát hiện bypass, lỗi hoặc thông đồng.

Không nên chỉ dựa vào phòng ngừa: tài khoản admin đột xuất, backdoor API, cấu hình tay trên thiết bị hoặc thay đổi cloud console có thể tạo đường đi khác. Cần đối chiếu **desired state (source of truth)** và **observed actual state**.

## 9. Quy trình phê duyệt theo từng lớp phòng vệ

### 9.1. Firewall, ACL và phân đoạn mạng

**Ví dụ yêu cầu:** `app-prod` được truy cập `db-prod` qua `5432/tcp` để chạy workload mới.

Người yêu cầu cần chứng minh:

- Source/destination là tài sản cụ thể và có owner xác nhận.
- Chỉ mở port/protocol cần thiết, không dùng any-any.
- NAT, routing, stateful rules, cloud security groups và IPv6 được đánh giá.
- Đã thử từ source zone phù hợp, có kế hoạch test allow/deny và rollback.
- Hạn áp dụng/tồn tại rõ; nếu là ngoại lệ tạm thời phải có expiry.

Người duyệt (asset/security approver) kiểm tra mục đích, rủi ro di chuyển ngang, độ rộng của rule, dữ liệu nhạy cảm, policy xung đột và phương án ít quyền hơn. Implementer kiểm tra approved diff, áp dụng canary nếu có thể; verifier so rule actual và traffic/logs.

**Điểm dễ lỗi:** người duyệt chỉ xem dòng “Mở 5432” mà không nhìn source CIDR bị mở rộng từ `10.40.2.0/28` lên `10.0.0.0/8`.

### 9.2. VPN/ZTNA và quyền quản trị

**Yêu cầu:** cấp một nhóm kỹ thuật quyền truy cập mạng quản trị trong thời gian xử lý sự cố.

- Requester/asset owner mô tả nhóm người, thiết bị và thời hạn.
- Approver độc lập xác minh nhu cầu, vai trò, MFA, device posture, bastion và audit.
- IAM/PAM cấp quyền **time-bound**; không để người yêu cầu tự gán vai trò approval hoặc tự nâng quyền tài khoản mình.
- Sau sự kiện, kiểm tra quyền đã thu hồi, session bị đóng khi cần và audit đầy đủ.

Đặc biệt cần tách quyền **thêm user vào nhóm approver** khỏi quyền **duyệt quyền truy cập**. Nếu người quản lý IAM có thể tự sửa role và tự duyệt grant, phải có kiểm soát bù trừ độc lập và giám sát.

### 9.3. IDS/IPS, WAF và hệ thống phát hiện

**Yêu cầu:** giảm mức block của một signature vì gây false positive.

- Evidence: alert, thời gian, loại traffic, tỷ lệ false positive, mức ảnh hưởng.
- Reviewer Security đánh giá liệu tắt/bypass signature có làm mất phát hiện của kỹ thuật tấn công khác không.
- Ưu tiên exception hẹp theo application/host/path/timeout; không tắt toàn bộ IPS nếu có lựa chọn an toàn hơn.
- Người duyệt xác định thời hạn và điều kiện giám sát bù trừ.
- Post-change: theo dõi false positive và true-positive detection coverage; không chỉ nhìn CPU giảm.

**Một lệnh toggle signature trong giao diện quản trị** vẫn là thay đổi chính sách an ninh, có thể cần phê duyệt độc lập dù thao tác cực kỳ đơn giản.

### 9.4. DNS filtering và resolver

**Yêu cầu:** allowlist một domain đang bị chặn.

- Xác minh domain/FQDN, chủ ứng dụng, chức năng nghiệp vụ và mức nguy hiểm được cảnh báo.
- Phân biệt domain gốc với toàn bộ subdomain; tránh wildcard vô tình mở rộng phạm vi.
- Kiểm tra split DNS, DNSSEC/DoH/DoT, TTL, cache, policy của từng mạng/tenant.
- Nếu chấp nhận exception, đặt owner, hạn review/expiry và ghi cách giám sát kết nối ra ngoài.
- Post-change đối chiếu query logs, phản hồi resolver và hành vi từ nhiều client zone.

### 9.5. Wireless, NAC và guest network

**Yêu cầu:** cho phép thiết bị của nhà thầu trong guest Wi-Fi truy cập dịch vụ nội bộ.

Đây là thay đổi boundary giữa khách và nội bộ. Requester cần xác định thiết bị/nhà thầu, mục đích, loại dữ liệu, thời hạn; approver của tài sản nội bộ và Security đánh giá phân đoạn, 802.1X/NAC, client isolation, network policy, ACL và phương án cấp truy cập tối thiểu. Implementer không tự chuyển SSID guest sang VLAN nội bộ; verifier kiểm tra từ chính mạng guest và xác nhận các đường khác vẫn bị chặn.

### 9.6. Cloud, Kubernetes và IaC

**Yêu cầu:** thay security group, firewall policy, API gateway, Kubernetes NetworkPolicy hoặc IAM role để một workload kết nối dịch vụ khác.

Phải xem xét:

- Account/subscription/project, VPC/VNet, region, namespace, label selector và owner.
- Network exposure do route table, load balancer, NAT, transit gateway hoặc service mesh.
- Quyền của service account/CI runner, cloud console direct-edit, Terraform state và cơ chế drift.
- Quản lý PR/plan/approval theo exact revision; tránh `terraform apply` với plan đã đổi sau duyệt.
- Kiểm tra **actual state** sau apply ở những vùng/cluster phù hợp, không chỉ log pipeline.

Dữ liệu cloud có thể động: IP, pod, endpoint, label, target group thay đổi theo thời gian. Approval phải bind đúng tài sản hoặc tập điều kiện được xác định, và có cơ chế xác minh lại khi môi trường đã thay đổi đáng kể.

## 10. Phê duyệt dựa trên rủi ro, không chỉ dựa trên số chữ ký

Không phải mọi thay đổi đều cần CAB họp. Quy trình quá chậm có thể khuyến khích bypass, còn phê duyệt tự động thiếu ranh giới làm suy yếu SoD. Một mô hình cân bằng:

1. **Standard changes:** mẫu được người có thẩm quyền duyệt *trước*, policy-as-code kiểm tra các guardrails, automation triển khai và log theo mỗi lần. Người yêu cầu không tự do chọn đầu vào ngoài mẫu.
2. **Normal changes:** người yêu cầu tạo diff; reviewer/owner độc lập xem xét trong SLA; triển khai sau khi đủ approval.
3. **High-impact changes:** thêm Security/Risk owner, hai lớp duyệt hoặc thay đổi phải qua canary/maintenance window.
4. **Emergency changes:** quy trình riêng để giảm thời gian chờ, có người chịu trách nhiệm, điều kiện dừng và review hồi tố bắt buộc.
5. **Unauthorized changes:** mọi thay đổi ngoài workflow đều bị phát hiện, phân loại và điều tra; không tự động hợp thức hóa hậu kiểm.

**SoD có thể được thỏa mãn bằng kiểm soát tự động đã được người độc lập thiết kế, phê duyệt và quản lý** cho những thao tác chuẩn hóa tác động thấp. Nhưng robot không “độc lập” nếu chính requester có thể sửa luật robot hoặc tắt approval gate cho ticket của mình.

### 10.1. Approval SLA và escalation

Cần có:

- SLA phản hồi theo risk tier và giờ hỗ trợ.
- Approver dự phòng khi người chính nghỉ hoặc mất liên lạc.
- Quy tắc chuyển cấp nếu ticket bị treo, không tự động chuyển thành approved sau thời gian chờ.
- Thông tin tối thiểu để người duyệt ra quyết định, tránh yêu cầu đi qua quá nhiều người nhưng không ai xem chi tiết.
- Trạng thái `requested`, `needs-info`, `approved`, `rejected`, `deployed`, `verified`, `expired`, `rolled-back` được ghi rõ, không gộp lại thành “done”.

Có thể đo thời gian chờ approval và mức độ ảnh hưởng đến vận hành để cải thiện workflow, thay vì mở đường tắt thiếu kiểm soát.

## 11. Trường hợp khẩn cấp: vẫn phải có ranh giới

Trong incident response, một rule firewall sai cần được rollback ngay hoặc một đường kết nối thiết yếu cần mở tạm để khôi phục hệ thống. Khi đó chờ CAB đầy đủ có thể làm tác động tăng lên. Tổ chức cần **Emergency Change Procedure** được phê duyệt trước.

### 11.1. Luồng đề xuất

~~~mermaid
flowchart TD
    A["Phát hiện sự cố / nguy cơ cần xử lý ngay"] --> B["Xác thực severity, impact và owner"]
    B --> C{"Có approver on-call đủ thẩm quyền?"}
    C -->|"Có"| D["Đánh giá nhanh, duyệt scope và TTL nhỏ nhất"]
    C -->|"Không"| E["Break-glass theo chính sách đã phê duyệt"]
    E --> F["Ghi actor, lý do, giới hạn và cảnh báo độc lập"]
    D --> G["Triển khai giới hạn; ưu tiên rollback an toàn"]
    F --> G
    G --> H["Theo dõi liên tục tác động và bảo vệ logs"]
    H --> I["Review hồi tố bởi người độc lập trong hạn chính sách"]
    I --> J["Thu hồi exception, cập nhật runbook và action items"]
~~~

**Điểm cần giữ:**

- Chỉ dùng emergency khi tiêu chí severity/impact thực sự đạt, ghi incident ID.
- Duyệt nhanh bởi người trực độc lập nếu khả thi; khi không thể, break-glass phải dựa trên **ủy quyền đã thiết lập trước**, quyền tạm, cảnh báo và bắt buộc xem xét sau.
- Hành động phải tối thiểu, có thời hạn, có rollback và monitoring; không tự mở rộng quyền vượt yêu cầu khắc phục.
- Giữ lịch sử ai gọi break-glass, ai thực hiện, lệnh/config, thời điểm UTC, lý do, tác động và người review hậu kiểm.
- Khi ổn định, người độc lập đánh giá sự cần thiết, các thay đổi phát sinh và rủi ro còn lại; ngoại lệ không được để tồn tại vô hạn.

**Phê duyệt hồi tố không biến một hành động trái phép thành được phép tại thời điểm diễn ra.** Vì vậy cần quy trình khẩn cấp với giới hạn/phạm vi được tổ chức chấp thuận từ trước. Nếu người thực hiện đã vượt quyền, phải ghi nhận và xử lý đúng quy trình, không chỉnh timestamp hoặc tự tạo approval giả.

### 11.2. “Tách nhiệm vụ” khi chỉ có một người trực

Các đội nhỏ hoặc ca trực đêm có thể không có người thứ hai ngay lúc cần sửa. Một số cách giảm rủi ro:

- Trực on-call theo **hai tuyến** (operations và security/risk) hoặc approver luân phiên ngoài giờ.
- Chuẩn hóa emergency action được phép trước: chỉ rollback về last-known-good, giới hạn thiết bị, TTL và điều kiện cụ thể.
- Dùng PAM/JIT cấp quyền ngắn hạn với ticket/incident binding, bật session recording và gửi alert tới kênh độc lập.
- Hạn chế quyền trực tiếp ở production, yêu cầu **review độc lập sau thay đổi** trong hạn chính sách.
- Phân loại rõ đây là **compensating control**, không báo cáo là SoD đầy đủ nếu cùng một người vẫn thực hiện mọi bước.
- Thu hẹp scope của người trực và giảm số lần ngoại lệ bằng tự động hóa/rule chuẩn.

Một người có nhiều tài khoản không trở thành “hai người” chỉ vì đăng nhập lần lượt bằng hai danh tính.

## 12. Ngoại lệ, ủy quyền và xung đột lợi ích

### 12.1. Delegation có điều kiện

Người duyệt chính có thể ủy quyền cho người khác trong thời gian vắng mặt. Việc ủy quyền phải ghi:

- Người ủy quyền, người nhận, nhóm tài sản và risk tier được phép.
- Khoảng thời gian, lý do và người kiểm tra ủy quyền.
- Những loại thay đổi không được duyệt thay.
- Giới hạn xung đột: approver được ủy quyền không được là requester của cùng ticket.
- Việc thu hồi quyền khi hết hạn; audit cho quyết định được duyệt bằng quyền ủy quyền.

Không cho phép requester tự chọn bất kỳ người nào rồi hệ thống tự cấp quyền approver cho họ.

### 12.2. Vấn đề “hai người duyệt cho nhau”

Ví dụ kỹ sư A tạo ticket X và kỹ sư B duyệt; B tạo ticket Y và A duyệt. Điều này **không tự động là vi phạm** nếu hai thay đổi độc lập và cả hai có thẩm quyền. Nhưng một mạng phê duyệt lặp lại, cùng lợi ích hoặc không có bằng chứng review có thể là tín hiệu cần giám sát.

Kiểm soát bổ sung:

- Kiểm tra risk owner độc lập cho thay đổi nhạy cảm.
- Theo dõi approval time, số lần reject/request changes và tỷ lệ self-bypass.
- Random audit, phân tích approval graph và config drift.
- Rotation người kiểm duyệt khi phù hợp, nhưng không để người thiếu chuyên môn thay reviewer kỹ thuật.
- Phân tách quyền quản trị nhóm approver khỏi quyền thay đổi production.

### 12.3. Quy tắc xử lý khi người duyệt cũng là người hưởng lợi

Nếu người duyệt là chủ thể sẽ được cấp quyền đặc biệt hoặc là owner duy nhất của hệ thống bị thay đổi, cần đánh giá có xung đột lợi ích hay không. Chính sách có thể yêu cầu approver khác cấp cao/độc lập, thêm security risk review hoặc đưa quyết định qua cơ chế risk acceptance. Không để người được cấp quyền tự duyệt chính quyền của mình.

## 13. Audit, bằng chứng và khả năng kiểm tra độc lập

Một chuỗi phê duyệt đáng tin cần ghi đủ **ai, khi nào, đã duyệt chính xác điều gì, theo quyền nào và trạng thái kết quả ra sao**.

| Bằng chứng | Nội dung cần ghi |
|---|---|
| Request | Ticket/change ID, requester identity, business reason, owner, source/destination, risk |
| Review | Reviewer identity, tài liệu/diff đã xem, comments, test results, quyết định |
| Approval | Approver identity, quyền tại lúc duyệt, revision/hash, UTC, điều kiện, TTL |
| Deployment | Service/implementer identity, artifact ID, UTC, target scope, kết quả và lỗi |
| Actual state | Config version/hash, applied rule, policy precedence, asset/region |
| Validation | Người xác minh, test ID, nguồn thử, allow/deny, performance và monitoring |
| Exception | Người chấp nhận rủi ro, phạm vi, lý do, expiry và review |
| Emergency | Incident ID, break-glass event, quyền tạm, alert, review hồi tố |
| Closure | Kết quả khôi phục/rollback, approval đóng ticket, action items |

### 13.1. Những thuộc tính của audit trail

- **Tamper resistance:** audit lưu ở ranh giới quyền độc lập, versioning/immutability phù hợp, ghi thay đổi/xóa quyền.
- **Time integrity:** UTC, NTP/clock skew và sự khác nhau giữa event time, ingest time, collection time.
- **Identity binding:** liên kết user/service identity với chủ thể có trách nhiệm; không chỉ IP hoặc tài khoản shared admin.
- **Traceability:** kết nối request → approval → exact artifact → deployment → observed state → verification.
- **Confidentiality:** tránh ghi token, private key, credential hoặc cấu hình nhạy cảm ra ticket/CI logs không kiểm soát.
- **Retention:** theo mục đích, luật và chính sách; có review legal hold khi cần, không giữ dữ liệu mãi vì “dùng để audit”.

Một comment “đã duyệt” không chứng minh quyền người duyệt, nội dung tại thời điểm duyệt hoặc việc hệ thống đã áp đúng. Cần log từ workflow, IAM, CI/CD và thiết bị đích.

### 13.2. Cảnh báo nên có

- Self-approval hoặc approval bởi tài khoản cùng chủ thể.
- Tài khoản không có quyền vẫn tạo approval record.
- Deployment khi chưa approved, khi approval hết hạn hoặc digest thay đổi.
- Truy cập trực tiếp API/console production bỏ qua pipeline.
- Người triển khai tự thay Code Owners, branch protection, approver group hoặc policy gate.
- Bật break-glass nhiều lần ngoài lịch/sự cố, quyền không thu hồi.
- Thay policy nhưng không có matching change ID hoặc missing deployment audit.
- Exception quá hạn, không có owner hoặc tự gia hạn lặp lại.
- Thay đổi config từ tài khoản có quyền sửa audit collector/log retention.

Cần kiểm tra alert thật có được triage, tránh tạo quá nhiều cảnh báo hình thức khiến SOC bỏ qua bất thường có giá trị.

## 14. Đo hiệu quả kiểm soát SoD

Một tổ chức có thể có hàng nghìn ticket “Approved” nhưng vẫn không biết kiểm soát có hiệu quả. Theo dõi chỉ số phù hợp:

| Chỉ số | Ý nghĩa | Cách diễn giải thận trọng |
|---|---|---|
| % change cần approval có approval hợp lệ | Coverage của workflow | Ticket số lượng lớn không chứng minh review có chất lượng |
| % change self-approval bị ngăn | Mức độ thực thi rule | Bị chặn nhiều có thể do UX/rule sai hoặc cố bypass |
| % deployment khớp approved revision/hash | Tính toàn vẹn từ duyệt đến triển khai | Cần đo trên artifact thực tế, không chỉ PR |
| % change ngoài pipeline được phát hiện | Hiệu quả kiểm soát drift | Không biết tổng bypass thì tỷ lệ có thể chưa chính xác |
| Thời gian review p50/p95 | Độ trễ phối hợp | Phân loại theo risk, không đánh đổi mọi kiểm soát lấy tốc độ |
| Change failure rate | Tỷ lệ thay đổi dẫn đến incident/rollback | So theo độ phức tạp, loại dịch vụ và traffic |
| Emergency/break-glass frequency | Mức độ sử dụng đường khẩn | Tăng bất thường cần phân tích nguyên nhân và phạm vi |
| Exception overdue rate | Khả năng thu hồi ngoại lệ | Đo cả ngoại lệ được gia hạn hợp lệ và tồn đọng |
| % change có post-check PASS | Mức độ xác minh sau triển khai | PASS không đủ nếu test thiếu đường trái policy |
| Audit completeness | Mức độ liên kết request–approve–deploy–verify | Kiểm tra định kỳ mẫu record đầy đủ và tính tin cậy |

### 14.1. Công thức tham khảo

~~~text
Approval compliance rate =
  Số change thuộc phạm vi có approval hợp lệ trước deploy
  / Tổng số change trong phạm vi cần approval

Artifact binding rate =
  Số deployment khớp đúng revision/hash đã duyệt
  / Tổng số deployment cần binding

Emergency review completion rate =
  Số emergency change được review độc lập đúng hạn
  / Tổng số emergency change

Exception expiry compliance =
  Số exception đã hết hiệu lực hoặc được tái phê duyệt hợp lệ
  / Tổng số exception đến hạn review
~~~

Nên báo cáo kèm mẫu số, thời gian, risk tier, nguồn dữ liệu và sai số có thể có. Không lấy việc có approval làm thước đo duy nhất của an toàn; cần kết hợp sự cố, misconfiguration, exposure, độ trễ phát hiện và chất lượng xác minh.

## 15. Case study: quy tắc firewall phục vụ ứng dụng thanh toán

### 15.1. Bối cảnh giả định

Đội ứng dụng cần cho máy ứng dụng thanh toán trong segment `10.40.2.0/28` kết nối cơ sở dữ liệu tại `10.40.8.10` qua `5432/tcp`. Quy tắc hiện tại chặn kết nối này. Một kỹ sư đề nghị mở rule vào 09:00 UTC và thực hiện canary sau giờ thấp điểm.

Đây là **tình huống học tập** với địa chỉ private minh họa, không mô tả hệ thống thật và không có lệnh thay đổi production.

### 15.2. Đề nghị ban đầu

~~~yaml
change_id: CHG-NET-2026-005
purpose: "Cho phép ứng dụng thanh toán truy cập DB"
requester: "network-engineer-17"
service_owner: "payments-owner"
environment: "production"
requested_rule:
  source_cidr: "10.40.2.0/28"
  destination_ip: "10.40.8.10"
  protocol: "TCP"
  destination_port: 5432
  action: "ALLOW"
reason: "Workload cần kết nối DB qua mạng nội bộ"
expected_duration: "persistent unless reviewed"
test:
  permitted: "app subnet -> DB:5432"
  denied: "user subnet -> DB:5432"
rollback: "restore prior approved policy revision"
status: "DRAFT_EXAMPLE"
~~~

**Vấn đề cần review:** nguồn là cả subnet chứ không phải các workload cụ thể; DB yêu cầu TLS/mTLS hay kiểm soát identity nào? Rule precedence có vô tình cho phép user subnet qua NAT? Change có thể thay bằng identity-based policy không? “Persistent unless reviewed” cần owner và kỳ review; môi trường production cần hiểu rủi ro trước khi approve.

### 15.3. Dòng xử lý theo SoD

1. **Requester** tạo ticket và policy diff, đính kèm đường mạng và thông tin owner.
2. **Payments owner** xác nhận nhu cầu nghiệp vụ, scope của DB, thời gian và dữ liệu liên quan.
3. **Security approver độc lập** đánh giá CIDR/port, segmentation, TLS, NAT, hướng kết nối, quy tắc deny và rủi ro lộ dữ liệu.
4. **Technical reviewer** kiểm tra syntax, thứ tự rule, cloud/security group tương ứng, khả năng rollback, output policy-as-code và test.
5. Hệ thống **đóng dấu revision/hash** của cấu hình được phê duyệt, giới hạn cửa sổ triển khai.
6. **Deploy service** áp đúng artifact trong đợt canary, không có quyền sửa approval hoặc audit logs.
7. **Verifier** kiểm tra connection hợp lệ và không hợp lệ, config effective trên firewall, logs IDS/IPS và tình trạng ứng dụng.
8. **Ticket** được đóng sau khi owner xác nhận và lưu evidence; trường hợp lỗi thì rollback, ghi incident nếu có tác động.

### 15.4. Lỗi bị phát hiện

Sau khi approval cho revision `rev-2`, requester cập nhật `source_cidr` thành `10.40.0.0/16` ở `rev-3` nhằm “đỡ phải sửa nhiều lần”. Hệ thống CI/CD phát hiện **artifact hash không khớp approval**, chặn triển khai và yêu cầu duyệt lại.

Đây là giá trị quan trọng của SoD: **reviewer không chỉ là người khác, quyết định còn bị ràng buộc với chính xác nội dung được phép**.

### 15.5. Nếu vẫn xảy ra sự cố?

Giả sử rule được duyệt đúng nhưng làm gián đoạn kết nối do thứ tự policy và NAT:

- Kích hoạt stop condition và rollback theo runbook.
- Giữ log, config diff, mốc UTC, phiên bản triển khai, người thực hiện và kết quả khôi phục.
- Post-incident review xem cả test coverage, rule ordering, quality của approval và bước xác minh.
- Cập nhật policy-as-code test và playbook; không kết luận chỉ cần thêm một chữ ký là đủ.

SoD chỉ là một mắt xích trong change management và defense in depth.

## 16. Case study ngắn: thay đổi ngoại lệ IDS/IPS trong sự cố

Một ứng dụng kinh doanh bị IPS chặn nhầm, đội vận hành muốn vô hiệu hóa toàn bộ policy IPS.

**Cách xử lý không phù hợp:** engineer tạo ticket, tự duyệt, tắt sensor, thông báo “đã khôi phục dịch vụ”, không đặt hạn và không có bằng chứng.

**Cách xử lý có SoD theo rủi ro:**

1. Incident commander xác nhận mức độ khẩn và service owner; kỹ sư đưa log mẫu, signature ID và luồng cụ thể.
2. Security/on-call approver độc lập cân nhắc exception hẹp hơn theo source/app/zone/signature, chỉ trong khoảng cần thiết.
3. Nếu có thể, triển khai ở chế độ phát hiện cho đúng signature, **không tắt toàn bộ sensor**; xác định cách thu alert và thời hạn.
4. Gắn incident ID với change revision, quyền JIT, audit và monitor hiệu quả.
5. Sau phục hồi, người khác đánh giá false positive, rủi ro mất detection, thu hồi exception khi đủ điều kiện và tạo action item.
6. Nếu bắt buộc break-glass do không liên lạc được approver, thực hiện chỉ trong pre-authorized emergency scope, lưu bằng chứng và review độc lập hồi tố.

Quy trình này bảo vệ **availability** nhưng không tùy tiện làm suy yếu **detection integrity**.

## 17. Các tình huống sai lệch thường gặp

| Tình huống | Vấn đề | Cách cải thiện |
|---|---|---|
| Ticket có chữ “Approved”, không có reviewer identity | Không kiểm chứng được ai đã quyết định | Enforce named identity và immutable decision log |
| Requester tự thêm mình vào approver group | SoD bị bypass qua IAM | Tách entitlement admin, access review độc lập |
| Người duyệt khác tên nhưng cùng shared account | Không quy trách nhiệm | Cá nhân hóa danh tính, MFA, loại bỏ shared admin |
| Approval trước commit mới | Duyệt một nội dung, deploy nội dung khác | Invalidate approval on change, bind digest |
| Approver chỉ thấy mô tả chung, không thấy diff | Thiếu cơ sở đánh giá rủi ro | Hiển thị semantic diff, test, owner và impact |
| Deployment thành công nhưng rule thực tế khác | Missing reconciliation/rollback | Verify applied state, config hash và traffic |
| Emergency được dùng cho hầu hết tickets | Bypass trở thành vận hành thường xuyên | Sửa SLA, on-call backup, giám sát emergency |
| Hai nhân viên liên tục duyệt cho nhau tức thì | Dấu hiệu reviewer không độc lập thực chất | Risk-based audit và rotation/cross-team approval |
| Người duyệt không hiểu service/cloud topology | Review hình thức, bỏ sót NAT/IPv6/VPC | Reviewer có chuyên môn hoặc thêm domain expert |
| Pipeline cho phép admin bypass không có log | Cổng kiểm soát không cưỡng chế | Protected branches, PAM, independent alert, review |
| Requester chọn policy expiry rất dài | Ngoại lệ không được thu hồi | Bắt buộc TTL/review theo risk |
| Quyền thực thi gắn với role vĩnh viễn | Có thể deploy không cần ticket | JIT deploy permission và gate theo change |
| Audit log chứa secret/private key | Kiểm toán tạo rủi ro rò rỉ mới | Redact, secret vault, phân quyền audit |
| Người kiểm tra chỉ thử đường allow | Không thấy mở quá rộng | Test cả denied paths, IPv4/IPv6, nhiều zone |

## 18. Runbook chuẩn hóa cho vận hành mạng

~~~text
PREPARE
  1. Xác định asset/service owner, ticket ID và mục đích.
  2. Thu baseline và mô tả policy diff, nguồn/đích/cổng/vùng.
  3. Ghi rủi ro, thời hạn, ảnh hưởng, kế hoạch test và rollback.

REVIEW
  4. Workflow chọn approver theo quyền/risk/asset ownership.
  5. Chặn requester == approver và các quyền xung đột liên quan.
  6. Technical/security review; yêu cầu bổ sung khi thiếu thông tin.
  7. Quyết định approve/reject với danh tính, UTC và revision/hash.

DEPLOY
  8. Kiểm tra approval còn hiệu lực, không có diff/asset scope thay đổi.
  9. Cấp quyền deploy có hạn và triển khai đúng artifact được duyệt.
 10. Theo dõi canary, logs, policy convergence và stop conditions.

VERIFY
 11. Đối chiếu desired vs applied; thử allow/deny từ các vùng.
 12. Kiểm tra tài nguyên, SLO, IDS/IPS, DNS, VPN và audit events.
 13. Khi lỗi: pause, rollback, ghi incident và thông báo owner.

CLOSE
 14. Thu hồi quyền JIT/exception, đóng tài khoản/session thử.
 15. Lưu evidence, owner sign-off và retention/expiry.
 16. Rà soát KPI, bypass attempts, review quality và action items.
~~~

### 18.1. Checklist trước khi duyệt

- [ ] Requester, approver và asset owner có danh tính/tư cách rõ; không có tự duyệt.
- [ ] Đúng tài sản, zone, tenant, account, source/destination, port/protocol.
- [ ] Có business reason và phương án ít quyền hơn được xem xét.
- [ ] Có security assessment bao gồm NAT, route, IPv6, dữ liệu nhạy cảm.
- [ ] Có diff/version/hash của nội dung sẽ triển khai.
- [ ] Có test allow **và** deny, rollback, maintenance window, người theo dõi.
- [ ] Có hạn hiệu lực, owner và cách thu hồi nếu là ngoại lệ.
- [ ] Approver có đủ thẩm quyền và đã thấy bằng chứng để quyết định.

### 18.2. Checklist khi triển khai và xác minh

- [ ] CI/CD/PAM đã kiểm tra approval, danh tính, phiên bản, expiry và scope.
- [ ] Không có bypass qua console/API hoặc admin role không được giám sát.
- [ ] Triển khai bằng danh tính được cấp quyền tối thiểu, có audit.
- [ ] Config thực tế khớp bản được duyệt, có version/hash hoặc snapshot.
- [ ] Các luồng cần mở thực sự hoạt động; các luồng ngoài scope vẫn bị chặn.
- [ ] Không ảnh hưởng bất thường đến firewall, VPN, DNS, IDS/IPS và dịch vụ.
- [ ] Thu hồi exception/JIT khi đến hạn; kiểm tra log không chứa bí mật.
- [ ] Kết quả được xác nhận bởi người phù hợp và đóng ticket có traceability.

## 19. Câu hỏi tự kiểm tra

**1. Hai tài khoản khác nhau đều thuộc cùng một người, một tài khoản tạo ticket và tài khoản kia duyệt. Đã đảm bảo SoD chưa?**

Chưa. SoD dựa trên **chủ thể độc lập có thẩm quyền**, không chỉ khác username. IdP/audit phải ngăn một người tạo và tự phê duyệt bằng hai tài khoản; cần thiết kế quản lý service account và delegation phù hợp.

**2. Người duyệt đồng ý mở cổng 443 cho một /32, nhưng trước triển khai requester đổi thành /16. Approval cũ còn hiệu lực không?**

Không nên còn hiệu lực. Nội dung thay đổi đã mở rộng phạm vi; cần tính lại diff/hash và phê duyệt lại theo risk.

**3. Có phải mọi thao tác vận hành đều cần hai người ký không?**

Không. Standard change tác động thấp có thể được xử lý bằng policy chuẩn đã được phê duyệt trước và automation có guardrails/audit. Các thay đổi ảnh hưởng quyền hoặc mạng nhạy cảm cần approval độc lập theo chính sách.

**4. Vì sao người duyệt phải hiểu ứng dụng và topology, không chỉ xem port?**

Cùng một cổng có thể kết nối tới subnet rộng, management zone hoặc dịch vụ dữ liệu nhạy cảm. NAT, route, IPv6, proxy và thứ tự rule có thể tạo tác động vượt dòng mô tả.

**5. Break-glass được dùng ban đêm có nghĩa là SoD đã được đáp ứng?**

Không tự động. Đó có thể là ngoại lệ/kiểm soát bù trừ; cần pre-authorized emergency scope, JIT, audit, cảnh báo, giới hạn tác động và review độc lập sau khi ổn định.

**6. Một GitOps PR có hai approval nhưng runner có quyền sửa cả policy nguồn và log, vậy đã đủ an toàn?**

Chưa. Cần bảo vệ branch/pipeline, hạn chế runner, tách quyền audit, bind exact artifact và phát hiện thay đổi production ngoài đường triển khai chuẩn.

**7. Sau deploy firewall rule, thiết bị báo “success”. Có thể đóng ticket ngay không?**

Chưa. Cần xác minh applied config, luồng hợp lệ và luồng bị cấm, log, availability và rollback readiness. Success của API không thay thế post-change verification.

**8. Người duyệt không phản hồi đúng SLA. Có nên tự động chuyển ticket thành approved?**

Không mặc định. Cần escalation tới approver dự phòng hoặc quy trình emergency đúng điều kiện. Timeout không phải là quyết định chấp nhận rủi ro.

**9. SoD có ngăn hoàn toàn việc hai người thông đồng không?**

Không. Cần kết hợp audit độc lập, least privilege, risk review, access certification, monitoring và kiểm thử thực tế. SoD giảm khả năng một người hành động một mình và tăng trách nhiệm, nhưng không phải kiểm soát tuyệt đối.

**10. Tại sao cần phân biệt “approved revision” và “applied revision”?**

Vì thiết bị hoặc pipeline có thể triển khai phiên bản khác, triển khai một phần hoặc rollback. Audit phải chứng minh **nội dung được duyệt** chính là **nội dung có hiệu lực**, hoặc giải thích sai khác.

---

**Ghi nhớ:** Phân tách nhiệm vụ không đơn thuần là yêu cầu thêm một chữ ký. Đây là việc tổ chức **quyền yêu cầu, quyền phê duyệt và quyền triển khai theo ranh giới độc lập**, gắn phê duyệt với **đúng nội dung/thời hạn**, kiểm soát các đường bypass và chứng minh **trạng thái vận hành thực tế** sau thay đổi. Khi được kết hợp với RBAC/PAM, GitOps, audit, kiểm thử và xử lý khẩn cấp đúng quy trình, SoD làm giảm rủi ro thay đổi mạng sai hoặc không được phép mà vẫn hỗ trợ vận hành an toàn.
