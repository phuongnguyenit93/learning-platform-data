# Partner review: rà soát quan hệ và quyền truy cập đối tác trong IAM

## 1. Partner review là gì?

**Partner review** trong **Identity and Access Management (IAM)** là quá trình kiểm tra có hệ thống xem **một tổ chức đối tác, những người và workload đại diện cho họ, cùng các quyền được cấp trên tài nguyên của tổ chức** có còn đáp ứng điều kiện kinh doanh và an ninh hay không. Review không chỉ là kiểm tra một doanh nghiệp có còn hợp đồng, mà còn phải xem **ai còn cần quyền gì, đối với tenant/dự án/tài nguyên nào, trong bao lâu**, ai chịu trách nhiệm và quyết định có thực sự được áp dụng trên các hệ thống đích.

Ví dụ: Công ty A hợp tác phân phối với công ty B trong một năm. Hàng quý, A rà soát 12 guest accounts của nhân viên B, hai OAuth clients, nhóm truy cập cổng đơn hàng, các quyền chia sẻ tài liệu và một phiên hỗ trợ production. Sau ba tháng, B chỉ còn 8 nhân viên tham gia, dự án P42 hoàn tất và một API client đã ngừng hoạt động. Kết quả review hợp lệ có thể là **giữ quyền của 8 người đúng nhiệm vụ, gỡ 4 người, thu hồi grants P42 và disable client không dùng**, đồng thời cập nhật thời hạn và xác nhận quyền thực tế ở hệ thống đích.

Partner review gắn với mô hình **Joiner–Mover–Leaver (JML)** của module SECURITY_IDENTITY_ACCESS_MANAGEMENT_IDENTITY_LIFECYCLE:

- **Joiner:** xác minh đối tác, người đại diện, nguồn xác thực và cấp quyền ban đầu; review xác nhận hồ sơ tạo quyền có căn cứ.
- **Mover:** khi nhân sự, hợp đồng, dữ liệu hoặc dự án thay đổi, review giúp xác định quyền cũ cần gỡ và quyền mới cần phê duyệt.
- **Leaver:** khi người dùng hoặc quan hệ hợp tác kết thúc, review phát hiện quyền dư và theo dõi quá trình thu hồi có kiểm chứng.

Các cơ chế **IdP, SSO, SCIM, RBAC/ABAC, service account, kiểm toán và access governance** là những đầu vào/công cụ giúp partner review có thể kiểm tra cả quyết định nghiệp vụ lẫn hiệu lực kỹ thuật.

### Mục tiêu học tập

Sau bài học, người học có thể:

1. Phân biệt review cấp tổ chức/hợp đồng, cấp principal, cấp grant và cấp workload.
2. Thiết kế chiến dịch **access review/recertification** theo mức rủi ro và sự kiện JML.
3. Phân công sponsor, partner manager, resource owner, IAM và reviewer độc lập đúng trách nhiệm.
4. Xây dựng một gói bằng chứng quyền hiện có, cách sử dụng và nguồn phê duyệt.
5. Đánh giá các lựa chọn **keep, reduce, revoke, reassign, suspend, escalate** và kiểm tra sau quyết định.
6. Phát hiện quyền tồn dư ở guest, group, SaaS ACL, token, API client và service account.
7. Xây dựng runbook, chỉ số và tiêu chí hoàn tất review có khả năng kiểm toán.

## 2. Review khác với xác thực, provisioning và offboarding như thế nào?

Review trả lời **quyền này có còn chính đáng và đáp ứng policy hay không?**. Những hệ thống hỗ trợ khác xử lý các câu hỏi riêng:

| Hoạt động | Câu hỏi chính | Kết quả |
|---|---|---|
| Identity verification | Chủ thể hoặc đối tác là ai? Có bằng chứng đáng tin không? | Danh tính/quan hệ đã xác minh |
| Authentication và SSO | Chủ thể đăng nhập qua IdP nào, chứng cứ có hợp lệ không? | Phiên hoặc danh tính đã xác thực |
| Provisioning (JIT, SCIM) | Bản ghi/người dùng/nhóm nào cần tạo, đổi, vô hiệu hóa? | Trạng thái user/group ở hệ thống đích |
| Authorization (RBAC/ABAC) | Request cụ thể có được phép không? | Allow/deny theo policy |
| **Partner review** | Quan hệ, principal và quyền hiện tại có còn cần, đúng phạm vi không? | Quyết định giữ/đổi/gỡ, bằng chứng và nhiệm vụ thực thi |
| Offboarding/Leaver | Khi nhu cầu kết thúc, phải thu hồi những gì? | Quyền, session/credential và trust phù hợp mất hiệu lực |
| Reconciliation | Quyền thực tế có khớp với trạng thái IAM mong muốn không? | Sai lệch, remediation và xác minh |

Một người B có thể vẫn đăng nhập thành công qua OIDC nhưng không còn làm việc với dự án A. Review xác định quyền không còn lý do; **quyết định revoke phải được thực thi** bởi IAM/ứng dụng. Việc bấm “Revoke” trên giao diện review **không tự bảo đảm** phiên JWT cũ hoặc quyền chia sẻ trực tiếp đã biến mất.

### Access review và recertification

**Access review** là hoạt động đối chiếu các quyền với nhu cầu. **Recertification** là kết quả xác nhận có trách nhiệm rằng một quyền vẫn được giữ hoặc phải thay đổi/thu hồi. Một chiến dịch review có thể bao gồm nhiều recertification decisions cho từng principal, role, relationship và resource.

Không nên nhầm **hoàn tất biểu mẫu review** với **quyền sau review đã được đồng bộ và kiểm chứng ở mọi hệ thống**. Cần quản lý hai trạng thái riêng.

## 3. Rà soát ở cấp nào?

Một partner có thể có nhiều dự án, hợp đồng và nguồn danh tính. Chỉ duyệt trạng thái “partner-B: active” chưa đủ để khẳng định từng quyền còn hợp lệ.

### 3.1. Cấp tổ chức và quan hệ hợp đồng

| Đối tượng | Điều cần kiểm tra |
|---|---|
| Partner organization | Pháp nhân/đầu mối có còn được xác minh, status active/suspended? |
| Contract/relationship | Hợp đồng còn hiệu lực, mục đích, dữ liệu, dự án có thay đổi? |
| Sponsor | Có người nội bộ chịu trách nhiệm, còn đủ điều kiện không? |
| Resource owner | Ai có quyền duyệt entitlement trên tài nguyên được chia sẻ? |
| Trust profile | IdP issuer/entityID, federation/broker, SCIM integration có còn được dùng? |
| Subcontractor | Có nhà thầu phụ mới hoặc người không được duyệt không? |

**Một partner có thể còn active nhưng một relationship đã hết hạn.** Review phải xử lý quyền theo nguồn hợp đồng. Nếu B còn hợp đồng P51 nhưng hợp đồng P42 kết thúc, cần thu hồi grants P42 và giữ grants P51 phù hợp, không mặc định khóa hoặc giữ toàn bộ B.

### 3.2. Cấp human external user và guest

Với từng principal:

- Người đó có còn làm việc cho B và tham gia đúng hạng mục không?
- Local guest có liên kết với đúng external subject/IdP không?
- Có sponsor và resource owner hợp lệ không?
- Membership tenant/project nào còn cần?
- Group, app roles, direct shares và privileged grants nào còn hiệu lực?
- Có tài khoản không sử dụng lâu ngày, đã hết hạn hoặc chưa chấp nhận invitation?
- Có dấu hiệu dùng tài khoản chung, trùng định danh hoặc account linking sai không?

**Lần đăng nhập gần nhất không đủ làm căn cứ duy nhất.** Một người không đăng nhập sáu tháng có thể vẫn sở hữu grants rủi ro cao, còn người đăng nhập mỗi ngày có thể đang dùng quyền vượt hợp đồng.

### 3.3. Cấp workload và service account

Các OAuth clients, API keys, webhook credentials, service accounts và workload federation subjects thường chạy không có người tương tác. Review phải tìm **technical owner**, **business sponsor** và **relationship tạo ra quyền**.

| Thuộc tính workload | Câu hỏi review |
|---|---|
| Client/service principal | Client này còn phục vụ tích hợp nào? |
| Contract/partner | Quan hệ nào cho phép client truy cập? |
| API action/scope | Có action nào dư hoặc quá rộng không? |
| Tenant/resource | Client chỉ thao tác dữ liệu đúng tenant và loại tài nguyên? |
| Credential/key | Khóa/cert đã được bảo vệ, rotate/review phù hợp và còn cần không? |
| Last activity | Không dùng có phải dịch vụ đã ngừng? Dùng bất thường có cần điều tra? |
| Technical owner | Ai chịu trách nhiệm cập nhật, xoay khóa và revoke? |
| Business owner | Ai chứng minh tích hợp còn nhu cầu nghiệp vụ? |

Đánh giá cả máy là phần bắt buộc của review hoàn chỉnh: **human access review không phát hiện được một API client âm thầm tiếp tục lấy dữ liệu sau khi dự án kết thúc**.

### 3.4. Cấp grant, tenant và tài nguyên

Một local principal có thể tham gia hai tenant hoặc hai dự án, mỗi grant do sponsor khác nhau chịu trách nhiệm. Review nên được chia đến cấp **membership/grant đủ cụ thể**:

- Partner ID và relationship/contract ID;
- Principal ID và loại chủ thể;
- Role, action, resource, tenant, project và môi trường;
- Nguồn cấp quyền: request, group, inheritance, direct share hoặc delegated administration;
- Approval, sponsor, resource owner và thời hạn;
- Trạng thái ở IAM trung tâm và ứng dụng đích.

Không thể tái chứng nhận chính xác bằng câu hỏi duy nhất “giữ tài khoản U không?”, bởi U có thể cần quyền P51 nhưng không còn được phép xem P42.

## 4. Ai có trách nhiệm trong một kỳ partner review?

| Vai trò | Trách nhiệm chính |
|---|---|
| **Partner/vendor manager** | Xác nhận pháp nhân, quan hệ hợp đồng, đầu mối, nhà thầu phụ và trạng thái hợp tác |
| **Business sponsor A** | Xác nhận người/workload còn nhu cầu và mục đích kinh doanh của từng grant |
| **Resource/data owner A** | Quyết định role, action, phạm vi dữ liệu và điều kiện cấp quyền trên tài nguyên |
| **IAM/Identity Governance** | Chuẩn bị inventory, điều phối campaign, thực thi grant change, theo dõi kết quả |
| **Security/Compliance** | Định nghĩa kiểm soát theo rủi ro, SoD, exception, audit và giám sát bất thường |
| **App/API owner** | Xuất quyền thực tế, gỡ ACL/role ở hệ thống đích, xác minh remediation |
| **Technical owner của workload** | Xác nhận service/API client, key, chứng thư, lịch rotation và tích hợp |
| **Đầu mối IdP phía B** | Xác minh trạng thái nhân sự B, phát tín hiệu thay đổi/Leaver qua kênh tin cậy |
| **Auditor độc lập** | Kiểm tra bằng chứng, nguyên tắc phân tách nhiệm vụ và tính đầy đủ |

Sponsor **không mặc nhiên được phê duyệt quyền production admin** nếu chính sách yêu cầu resource owner/Security độc lập. Ngược lại, owner ứng dụng không nên tự khẳng định nhu cầu hợp đồng vẫn hợp lệ khi không có sponsor hoặc partner manager xác nhận.

### 4.1. Reviewer có đủ hiểu biết và thẩm quyền?

Một review giả tạo thường chỉ gửi hàng trăm dòng quyền cho người quản lý không hiểu ứng dụng. Reviewer cần biết **quyền này cho phép thao tác gì, trên tài nguyên nào, mức rủi ro ra sao và có căn cứ công việc nào**. Với role kỹ thuật phức tạp, IAM cần bổ sung role description hoặc nhờ app owner tham gia.

Nếu quyền thuộc dự án khác, reviewer nên **reassign** cho owner có thẩm quyền thay vì nhấn Keep theo suy đoán. Tránh để người đề nghị đặc quyền tự xác nhận toàn bộ bước phê duyệt khi policy yêu cầu tách nhiệm vụ.

### 4.2. Sponsor nghỉ việc hoặc không phản hồi

Hệ thống phải phát hiện sponsor nghỉ việc/đổi công tác, tìm các grants được bảo trợ, chỉ định người nhận theo quy trình và yêu cầu tái xác nhận. Với quyền rủi ro cao hoặc quá hạn, có thể đình chỉ/thu hồi theo chính sách. **Im lặng không có nghĩa là chấp nhận gia hạn vô hạn**.

## 5. Khi nào kích hoạt partner review?

Một chương trình hiệu quả cần cả **review định kỳ dựa trên rủi ro** và **review theo sự kiện**.

### 5.1. Review định kỳ theo rủi ro

| Nhóm truy cập | Đặc điểm | Hướng review |
|---|---|---|
| Đọc tài liệu giới hạn, không nhạy cảm | Tác động thấp, scope nhỏ | Theo chu kỳ và hợp đồng phù hợp |
| Xem dữ liệu cá nhân/khách hàng | Có nghĩa vụ bảo vệ dữ liệu | Thường xuyên hơn, cần data owner và scope rõ |
| Cloud admin / production support | Đặc quyền, tác động rộng | Review chặt và theo sự kiện, cân nhắc PAM/JIT |
| API client đồng bộ dữ liệu | Hoạt động liên tục, credential lâu dài | Xét owner, purpose, scopes, logs và rotation |
| Delegated administration | Đối tác có thể cấp quyền cho người khác | Review trần quyền, danh sách nhóm, audit |
| Nhà thầu phụ hoặc tài khoản dùng chung | Độ rõ trách nhiệm thấp | Cần xác minh lại chủ thể, thay tài khoản chia sẻ nếu khả thi |

Không có chu kỳ cố định chung phù hợp mọi tổ chức. Tần suất nên dựa vào **độ nhạy dữ liệu, mức đặc quyền, khả năng thu hồi, điều kiện hợp đồng và chính sách nội bộ**. Nên tránh áp đặt lịch review chỉ theo “mỗi quý” mà bỏ qua những thay đổi xảy ra giữa kỳ.

### 5.2. Review do sự kiện kích hoạt

- **Joiner mới:** partner onboarding, thêm guest, thêm OAuth client hoặc phạm vi dữ liệu mới;
- **Mover:** đổi nhiệm vụ, chuyển tenant, tăng quyền, thay IdP, đổi nhà thầu phụ, đổi sponsor;
- **Leaver:** người B nghỉ việc, một dự án/contract kết thúc, client ngừng hoạt động;
- **Access anomaly:** quyền cross-tenant bị thử lặp lại, admin role xuất hiện bất thường;
- **Credential event:** secret lộ, certificate rotation, khóa không có owner;
- **System event:** ứng dụng mới tích hợp IAM, thay đổi cấu trúc role hoặc dữ liệu;
- **Governance event:** partner bị đình chỉ, audit finding, review quá hạn, SoD conflict;
- **Operational event:** SCIM lỗi, user inactive nhưng còn grants downstream.

Với một **sự cố đang diễn ra**, không chờ kỳ review: chính sách incident response có thể yêu cầu **chặn quyền ngay**, rồi thực hiện review điều tra và remediation sau.

## 6. Cần thu thập dữ liệu gì trước review?

### 6.1. Nguồn dữ liệu nghiệp vụ

- Partner/contract registry: ID, status, ngày hiệu lực và phạm vi quan hệ;
- Project/service registry: dự án còn hoạt động, tài nguyên và owner;
- Sponsor/resource-owner directory: ai còn đủ thẩm quyền phê duyệt;
- Hệ thống ticket/approval: business justification, người duyệt, thời hạn;
- Phản hồi từ đối tác: ai còn tham gia, nhà thầu phụ nào được phép.

### 6.2. Nguồn dữ liệu kỹ thuật

- IdP/SSO: external subjects, issuer/entityID, guest links và trạng thái xác thực;
- IAM/grant store: memberships, roles, groups, ABAC attributes, expiry;
- SCIM/JIT: user/group provisioning state, sync error, nguồn record;
- Ứng dụng đích: quyền SaaS, ACL, document share, repository, cloud role;
- API platform: OAuth clients, scopes, audiences, secrets, certificate trust;
- PAM/ZTNA: quyền đặc biệt, sessions, quyền truy cập hạ tầng;
- Audit/monitoring: lần sử dụng, thay đổi quyền, lỗi policy, dấu vết revoke.

### 6.3. Một bản ghi review đủ thông tin

~~~json
{
  "review_item_id": "REV-2026-Q4-0142",
  "partner_id": "partner-B",
  "relationship_id": "CTR-P42",
  "principal_id": "external-user-U",
  "principal_type": "human",
  "sponsor_id": "employee-A-17",
  "resource_owner_id": "owner-A-9",
  "tenant_id": "tenant-B",
  "project_id": "P42",
  "resource_id": "reporting-P42",
  "role": "report_viewer",
  "actions": ["reports.read"],
  "grant_expires_at": "2026-12-31T00:00:00Z",
  "contract_status": "active",
  "grant_source": "approved-request-2042",
  "last_observed_use_at": "2026-10-12T04:00:00Z",
  "target_access_state": "observed-active",
  "review_decision": "pending"
}
~~~

Đây là **mô hình minh họa**, không phải schema chuẩn của SCIM hay sản phẩm IAM. Có thể bổ sung mức nhạy tài nguyên, dấu vết phiên, nguồn trust, risk rating và kỳ review trước. Hệ thống phải giới hạn truy cập các dữ liệu nhạy cảm trong báo cáo.

### 6.4. Chất lượng dữ liệu quan trọng hơn số lượng dòng

Nếu danh sách quyền chỉ có email và role mà không có **tenant, project, resource owner, action hoặc nguồn hợp đồng**, reviewer khó quyết định chính xác. IAM nên gắn từ sớm provenance của grant: được cấp theo yêu cầu nào, quan hệ nào, ai là owner và lúc nào hết hạn.

**Email không phải khóa định danh đủ mạnh.** Với OIDC, liên kết local principal tới cặp **(issuer, subject)** của ID token đã xác minh. Với SAML, sử dụng định danh ổn định gắn với IdP/issuer đã được cấu hình. Việc B đổi IdP hoặc email cần được review trước khi chuyển grants.

## 7. Workflow một chiến dịch partner review

Review cần có điểm bắt đầu, danh sách item được xác định tại một thời điểm, người duyệt, hạn, cách xử lý không phản hồi và tiêu chí **đã áp dụng quyết định**.

### 7.1. Bước 1 — Chọn scope và tạo snapshot

IAM xác định kỳ review liên quan partner nào, hợp đồng/dự án nào, ứng dụng nào và nhóm rủi ro nào. Một chiến dịch có thể rà soát toàn bộ quan hệ B2B hoặc chỉ một loại quyền đặc biệt. Cần ghi **thời điểm snapshot** và chính sách lọc để biết rõ các item nào đã được đưa vào kỳ review.

Trong thời gian campaign diễn ra, grants vẫn có thể thay đổi. Hệ thống cần nhận diện một item đã bị revoke từ trước, đã đổi resource owner hoặc có grant mới sau snapshot; không lấy một quyết định Keep cũ để tái kích hoạt quyền đã bị thu hồi.

### 7.2. Bước 2 — Enrich dữ liệu và phân công reviewer

Mỗi item cần có business justification, partner/contract status, role/action, resource scope, owner, kỳ review trước, hạn và trạng thái ở hệ thống đích. Reviewer được chọn theo phạm vi:

- Sponsor xác nhận nhu cầu hợp tác;
- Resource owner xác nhận entitlement và loại dữ liệu;
- Technical owner đánh giá workload/client credential;
- Security/Compliance review đặc quyền hoặc ngoại lệ;
- Partner manager xác nhận hợp đồng và đầu mối.

Nếu người được phân công đã nghỉ việc hoặc không có thẩm quyền, **reassign** trước khi yêu cầu quyết định. Với quyền đặc biệt, áp dụng separation of duties phù hợp, không để người hưởng quyền tự phê duyệt nếu chính sách cấm.

### 7.3. Bước 3 — Yêu cầu quyết định có căn cứ

Reviewer phải chọn quyết định **cho mỗi item hoặc nhóm item có cùng scope rõ ràng**. Không nên cho phép một nút “Approve all” thiếu ngữ cảnh trên hàng nghìn quyền nhạy cảm. Có thể nhóm các grants ít rủi ro để giảm tải, nhưng phải hiển thị rõ tác động và ngoại lệ.

### 7.4. Bước 4 — Áp dụng và xác minh quyết định

Khi reviewer chọn Revoke, IAM tạo tác vụ deprovision vào target. Khi chọn Reduce, hệ thống tính quyền mới và gỡ phần dư; khi chọn Keep có hạn, cập nhật expiry theo đúng approval policy. App owner xác nhận các quyền được áp dụng, rồi IAM **reconcile desired/actual state**.

### 7.5. Bước 5 — Xử lý lỗi và đóng campaign

Campaign chỉ nên được đánh dấu đạt tiêu chí hoàn tất khi:

1. Tất cả items có reviewer hợp lệ hoặc quyết định theo policy rõ ràng;
2. Các quyết định giảm/thu hồi đã được thực thi hoặc có ngoại lệ được quản lý;
3. Quyền ở target được kiểm tra trong phạm vi đã cam kết;
4. Mọi lỗi chưa xử lý có owner, mức rủi ro, deadline và compensating control;
5. Audit snapshot, phê duyệt, remediation và kết quả được lưu theo retention policy.

### Sơ đồ quy trình

~~~mermaid
flowchart TD
    T["Trigger định kỳ/sự kiện"] --> S["Chọn partner/relationship, scope, snapshot"]
    S --> E["Bổ sung quyền thực tế và owner"]
    E --> A{"Reviewer hợp lệ?"}
    A -->|"Không"| R["Reassign hoặc escalate"]
    R --> A
    A -->|"Có"| D{"Quyết định?"}
    D -->|"Keep"| K["Xác nhận scope/expiry còn hợp lệ"]
    D -->|"Reduce/Revoke"| P["Tạo tác vụ IAM/app owner"]
    D -->|"Suspend"| U["Chặn theo policy và điều tra"]
    D -->|"Escalate"| X["Chuyển Security/resource owner"]
    X --> D
    K --> V["Đối soát và lưu bằng chứng"]
    P --> V
    U --> V
    V --> Q{"Desired = actual?"}
    Q -->|"Chưa"| F["Remediation + exception tracking"]
    F --> V
    Q -->|"Đúng"| C["Đóng item/campaign theo policy"]
~~~

Sơ đồ thể hiện logic chung; đường phê duyệt, trạng thái và mức tự động hóa cụ thể phụ thuộc sản phẩm IAM.

## 8. Bộ quyết định review và ý nghĩa kỹ thuật

| Quyết định | Khi nào chọn? | Tác động mong muốn |
|---|---|---|
| **Keep** | Còn nhu cầu và grant đáp ứng chính sách | Duy trì đúng scope/hạn, ghi xác nhận |
| **Reduce** | Chỉ còn cần một phần action/resource | Gỡ role/grant dư, giữ subset hợp lệ |
| **Revoke** | Không còn nhu cầu, sai đối tác, hết hợp đồng | Thu hồi grant/membership, xử lý quyền phụ thuộc |
| **Suspend** | Nghi vấn, cần kiểm chứng hoặc rủi ro cấp bách | Tạm chặn truy cập theo phạm vi, giữ bằng chứng |
| **Reassign** | Reviewer không còn trách nhiệm | Chuyển người có thẩm quyền đánh giá |
| **Escalate** | Thiếu chứng cứ, conflict, role nhạy cảm | Giao Security, resource owner hoặc partner manager |
| **Replace/Remediate** | Cấu hình quyền sai hoặc owner không hợp lệ | Tạo thay đổi kỹ thuật và kiểm chứng |

### 8.1. Keep phải có hạn rõ ràng

Một quyết định Keep không nên mặc nhiên gia hạn vô hạn. Nếu hợp đồng hết hạn ngày 31/12 nhưng reviewer Keep ngày 01/12, grant vẫn phải tuân theo expiry của hợp đồng hoặc các hạn ngắn hơn theo policy. Đổi expiry cần căn cứ, approval phù hợp và audit.

### 8.2. Reduce khác với xóa toàn bộ tài khoản

Một kỹ sư B có quyền đọc log staging và quyền production support theo JIT. Khi dự án bảo trì kết thúc nhưng B vẫn được giao kiểm thử staging, reviewer có thể **thu hồi production entitlement** mà vẫn giữ staging viewer nếu có hợp đồng và scope hợp lệ. Xóa toàn bộ guest có thể gây gián đoạn không cần thiết.

### 8.3. Revoke phải xét quyền phụ thuộc

Nếu role được gán qua group, việc chỉ xóa một direct grant có thể không chặn quyền vì group còn được ánh xạ. Nếu guest U đã được share file riêng, gỡ group không đủ. **Kết quả review phải tính quyền có hiệu lực (effective permissions)** chứ không chỉ một dòng assignment.

### 8.4. Khi bằng chứng thiếu

Reviewer không nên chọn Keep chỉ vì không biết role làm gì. Có thể đánh dấu **Need clarification/Escalate**, yêu cầu app owner mô tả role và resource, đặt hạn trả lời. Với quyền nhạy cảm quá hạn, chính sách có thể yêu cầu tạm đình chỉ trong khi xác minh.

## 9. Đánh giá theo rủi ro thay vì nhìn tên role

Một vai trò cùng tên viewer có thể có tác động khác nhau tùy dữ liệu và phạm vi. Rủi ro review nên xét ít nhất:

- **Sensitivity:** tài nguyên chứa thông tin công khai, nội bộ, cá nhân hay tài chính nhạy cảm?
- **Privilege:** chỉ đọc hay có thể thay đổi cấu hình, xóa, cấp quyền?
- **Reach:** một object, một tenant, nhiều tenant hay toàn tổ chức?
- **Persistence:** quyền có thời hạn, đặc quyền JIT theo ticket hay admin thường trực?
- **Trust assurance:** nguồn danh tính và MFA đủ tin cậy, IdP còn được duyệt?
- **Lifecycle confidence:** có sponsor, SCIM/Leaver event, ngày hết hạn và kết quả review gần đây?
- **Usage and anomalies:** có hành vi bất thường hoặc quyền hiếm sử dụng không?
- **Recovery difficulty:** nếu quyền bị lạm dụng, khó phát hiện/khôi phục tới đâu?

### Ví dụ phân loại

| Quyền | Những yếu tố tăng rủi ro | Cách tiếp cận |
|---|---|---|
| Đọc ticket dự án P42 | Scope hẹp, dữ liệu ít nhạy cảm | Review theo hợp đồng và lịch phù hợp |
| Đọc toàn bộ hóa đơn khách hàng | Dữ liệu nhạy cảm, số lượng lớn | Data owner xác nhận trường dữ liệu và purpose |
| Tải export nhiều tenant | Phạm vi lớn, dễ rò rỉ | Giảm scope, phê duyệt riêng và audit |
| Sửa production configuration | Đặc quyền và tác động vận hành | Ưu tiên JIT/PAM, review theo sự kiện |
| API client dùng key lâu dài | Credential không gắn human session | Review owner, key rotation, scope, activity |
| Delegated admin đối tác B | Có thể cấp lại quyền cho người khác | Kiểm tra role ceiling, logs và membership |

Không nên xem bảng là xếp hạng chuẩn. **Tổ chức tự thiết lập thang rủi ro và lịch review** phù hợp dữ liệu, kiến trúc, quy định và thỏa thuận.

### 9.1. Có thể tự động đề xuất, không tự động quyết định mọi thứ

Các thuật toán có thể phát hiện user không còn sponsor, grant quá hạn hoặc client không hoạt động để gợi ý Revoke. Nhưng **không có activity không chứng minh không còn nhu cầu**, và activity thường xuyên không chứng minh quyền là hợp lệ. Cần policy, reviewer/owner và cơ chế khiếu nại/khôi phục có kiểm soát.

### 9.2. Review quyền privileged

Khi partner có role cloud admin, database owner hoặc quyền truy cập production, nên kiểm tra session PAM, ticket, người phê duyệt và lý do quyền đang thường trực. Nếu công việc chỉ phát sinh khi có sự cố, cân nhắc chuyển sang **Just-in-Time elevation** có giới hạn thời gian. Review đặc quyền không thay cho monitor/revoke khẩn cấp khi có sự cố.

## 10. IdP, SSO và federation trong partner review

### 10.1. Trust được duyệt không đồng nghĩa mọi user được duyệt

**B2B federation** cho phép user B đăng nhập vào A qua **OIDC/SAML**. A phải xác minh đúng token/assertion và tin cậy issuer/entityID. Tuy nhiên, IdP B có thể xác thực hàng nghìn người; **chỉ user được gắn local membership/grant hợp lệ mới được truy cập tài nguyên A**.

Review cần phân biệt:

1. **Trust profile review:** issuer/entityID nào còn cần, signing key/certificate nào được quản lý, endpoint/client config có owner và hạn/rotation?
2. **Identity linking review:** local guest liên kết với đúng external subject, không gắn nhầm email/issuer?
3. **Entitlement review:** role/tenant/project/resource nào được cấp từ nguồn phê duyệt hợp lệ?
4. **Session assurance review:** chính sách MFA, phiên, refresh token và xác thực nâng mức có phù hợp rủi ro?

### 10.2. Những kiểm tra OIDC/SAML đáng lưu ý

| Thành phần | Điều cần kiểm tra trong review |
|---|---|
| OIDC issuer / client | Có được đăng ký cho đúng partner và ứng dụng, còn hoạt động không? |
| JWKS/signing key | Nguồn khóa đáng tin, cách thay/xoay khóa và owner rõ? |
| ID token validation | Ứng dụng kiểm tra signature, issuer, audience, expiry và nonce khi áp dụng? |
| SAML entityID / metadata | Có mapping đúng SP, IdP, ACS, certificate không? |
| SAML response validation | Chữ ký, audience, destination/recipient, time, replay control đúng? |
| Account linking | Dùng định danh ổn định gắn issuer, không chỉ email? |
| MFA/authentication context | Claim mức xác thực từ B có được hiểu/được tin cậy có kiểm soát? |
| Logout/session | Quyền tại A có được đánh giá lại khi B disable user không? |

Partner review không nhất thiết thực hiện pentest toàn bộ giao thức, nhưng phải phát hiện cấu hình trust **không owner**, **issuer cũ không dùng**, **mappings quá rộng** hoặc **đăng nhập được dù relationship đã kết thúc**; chuyển các phát hiện kỹ thuật cho đội IAM/Security phù hợp.

### 10.3. Khi B đổi IdP hoặc email domain

Không tự gộp tài khoản cũ và mới theo email. Cần bằng chứng đáng tin để ánh xạ issuer/subject mới với local principal và xác nhận grants còn hợp lệ theo relationship. Nếu hai trust cùng hoạt động trong giai đoạn chuyển đổi, review phải thấy **cửa sổ chuyển tiếp và ngày thu hồi trust cũ**.

### 10.4. Review trust dùng chung

Một issuer/SSO broker có thể phục vụ nhiều hợp đồng hoặc đối tác. Nếu chỉ hợp đồng P42 kết thúc nhưng P51 còn active, không xóa toàn bộ IdP trust đang cần cho P51. Review theo **reference và dependency graph**, thay vì mặc định một issuer chỉ tương ứng một hợp đồng.

## 11. SCIM, JIT và hiệu lực thực tế của review

### 11.1. SCIM hỗ trợ đồng bộ user/group

**SCIM** là cơ chế quản lý user/group có cấu trúc giữa các hệ thống tích hợp, không phải giao thức cấp quyền toàn cục. Trong review, IAM có thể so sánh:

- User active theo nguồn provisioning và user active tại A;
- Group từ B đã được ánh xạ tới role nào trong A;
- Sự kiện deactivate/remove group đã áp dụng thành công chưa;
- Retry/error và các record bị thiếu, tạo trùng hoặc đến chậm;
- User đã bị revoke có bị provisioning cũ tái kích hoạt không.

Ví dụ PATCH SCIM vô hiệu hóa một user:

~~~http
PATCH /scim/v2/Users/guest-1084 HTTP/1.1
Authorization: Bearer <provisioning-access-token>
Content-Type: application/scim+json

{
  "schemas": ["urn:ietf:params:scim:api:messages:2.0:PatchOp"],
  "Operations": [
    {"op": "Replace", "path": "active", "value": false}
  ]
}
~~~

Ví dụ chỉ mô tả yêu cầu ở một hệ thống hỗ trợ SCIM, không thể hiện toàn bộ quy trình thu hồi. SCIM client cần được xác thực và giới hạn scope, còn target cần kiểm tra kết quả. **Đặt active=false không tự hủy mọi phiên ứng dụng, JWT hoặc direct shares**.

### 11.2. JIT provisioning và lời mời guest

Khi dùng **Just-in-Time user provisioning**, người đăng nhập lần đầu có thể được tạo local principal. Review phải xác nhận JIT rule có **partner eligibility, invitation/sponsor hoặc approval** chứ không cho mọi email từ domain B tự nhận role rộng.

Khi kết thúc relationship, policy phải chặn JIT và provisioning từ nguồn cũ **tái cấp quyền đã bị thu hồi**. Nếu người cũ quay lại hợp tác, cần phê duyệt mới, không tự khôi phục grants trước đây.

### 11.3. Desired và actual state

Một item review có thể mang:

- **Approved desired state:** quyền mà sponsor/resource owner chấp nhận sau review.
- **Provisioned state:** trạng thái IAM/SCIM báo đã đồng bộ.
- **Actual effective state:** điều backend, SaaS, repository hoặc API đang thực sự cho phép.

Nếu cả ba không đồng nhất, cần remediation và kiểm tra lại. Không nên đóng chiến dịch chỉ dựa vào màn hình đã chuyển sang approved hoặc revoked.

## 12. Review RBAC, ABAC và quyền hiệu lực

### 12.1. RBAC role là điểm bắt đầu, không phải toàn bộ phạm vi

**Role-Based Access Control (RBAC)** gán nhóm quyền theo nhiệm vụ. Nhưng role cùng tên có thể được gán ở phạm vi rộng hơn nhiều so với mục đích công việc. Review phải kiểm tra cả **role và scope**.

| Role minh họa | Hành động | Scope cần xác nhận |
|---|---|---|
| partner_report_viewer | reports.read | Tenant, dự án, loại báo cáo |
| partner_ticket_operator | tickets.read, tickets.update | Các ticket được giao |
| partner_order_status_writer | orders.status.update | Order thuộc tenant/hợp đồng đã duyệt |
| partner_auditor | evidence.read | Dữ liệu kiểm toán được đánh dấu phù hợp |
| partner_delegated_admin | members.manage | Chỉ nhóm/role được A ủy quyền trong tenant |
| partner_prod_support_jit | Thao tác quản trị giới hạn | Ticket, host, khoảng thời gian và phê duyệt |

Không nên giữ role global_viewer chỉ vì người dùng vẫn cần xem một báo cáo ở P42. Reviewer có thể chọn **Reduce** về role hẹp hơn hoặc scope theo object, thay vì giữ quyền toàn tenant.

### 12.2. ABAC giới hạn quyền theo ngữ cảnh

**Attribute-Based Access Control (ABAC)** đánh giá các thuộc tính như partner, relationship, principal, tenant, project, resource classification, action, expiry và điều kiện xác thực. Review cần biết nguồn thuộc tính nào đáng tin và cách xử lý thay đổi.

Mã giả cho API:

~~~text
authorize(principal, action, resourceId, context):
    if not context.authentication_valid: DENY
    if principal.status != "active": DENY

    resource = get_resource_from_trusted_store(resourceId)
    if resource is missing: DENY

    membership = get_membership(principal.id, resource.tenant_id)
    if membership is missing or membership.status != "active": DENY

    partner = get_partner(membership.partner_id)
    relationship = get_relationship(partner.id, resource.project_id)
    if partner.status != "active": DENY
    if relationship is missing or relationship.status != "active": DENY
    if now >= relationship.expires_at: DENY

    grant = get_effective_grant(principal.id, action, resourceId)
    if grant is missing or grant.status != "active": DENY
    if now >= grant.expires_at: DENY
    if resource.tenant_id != grant.tenant_id: DENY
    if resource.project_id not in grant.project_ids: DENY
    if action not in grant.allowed_actions: DENY
    if not context.satisfies_data_risk_policy: DENY

    ALLOW
~~~

Đây là **mã giả minh họa**; trong hệ thống thật cần kiểm tra token/phiên đúng giao thức trước đó và xem xét tính nhất quán, policy engine, cache và các explicit deny. Reviewer cần xác định **grant có còn đúng trong mô hình này không**, không tự thay đổi logic backend.

### 12.3. Lỗi cross-tenant và quyền theo object

Giả sử U thuộc B và có role partner_report_viewer cho tenant-B/P42. Nếu URL báo cáo chứa ID, U có thể thử ID của tenant-C. Backend không được chỉ kiểm tra role viewer; phải tải resource ownership từ nguồn đáng tin và đối chiếu tenant/project/membership/grant.

Trong review, nên lấy mẫu những API hoặc ứng dụng mà quyền được cấp ở cấp role chung nhưng tài nguyên phân chia theo tenant. Đó là khu vực có nguy cơ lỗi **Broken Object Level Authorization (BOLA/IDOR)** nếu kiểm tra quyền ở backend thiếu scope.

### 12.4. Phân tách nhiệm vụ và delegated admin

Nếu B được phép tự quản lý thành viên trong tenant của mình, reviewer phải kiểm tra:

1. Danh sách role B được cấp cho người khác có bị giới hạn không?
2. Có thể tự gán admin toàn cục hoặc cấp quyền ngoài tenant B không?
3. Các thay đổi group có audit, owner và thời hạn không?
4. Người duyệt/tạo/triển khai thay đổi nhạy cảm có bị vi phạm **Separation of Duties (SoD)** không?
5. Khi quan hệ B kết thúc, delegated admin có bị chặn khả năng tạo lại quyền không?

**Review một role delegated_admin không chỉ đánh giá quyền trực tiếp của một cá nhân, mà cả khả năng cá nhân đó cấp quyền cho nhiều người khác.**

## 13. Review workload, token và danh tính máy

### 13.1. Review API client không phải review user

Một OAuth client có thể hoạt động 24/7, không có MFA và không gắn sự kiện nghỉ việc của một người. Việc owner kỹ thuật chuyển công tác không đồng nghĩa tích hợp phải dừng, nhưng **phải chỉ định owner mới và xem xét credential đã từng được người cũ biết**.

| Chủ đề | Câu hỏi reviewer cần trả lời |
|---|---|
| Business justification | Client có còn xử lý dữ liệu phục vụ hợp đồng hiện tại? |
| Technical owner | Ai triển khai, rotate, giám sát và disable client? |
| Client registration | Client có riêng theo đối tác, ứng dụng và môi trường? |
| OAuth audience/scope | Token dành đúng API và action tối thiểu? |
| Resource entitlement | API chỉ cho client xem/cập nhật đối tượng đúng tenant? |
| Credential | Key/cert/secret đang được bảo vệ và có kế hoạch rotation? |
| Last activity | Không sử dụng là dấu hiệu ngừng tích hợp hay chỉ hoạt động định kỳ? |
| Endpoint/dependency | Webhook, queue, service account hoặc CI/CD nào còn liên quan? |
| Revocation readiness | Có thể disable/rotate mà không ảnh hưởng đối tác khác? |

### 13.2. OAuth scope không đồng nghĩa quyền nghiệp vụ

Một access token có scope orders.read vẫn **không** mặc nhiên được đọc mọi order trên mọi tenant. Resource server phải kiểm tra token phù hợp (issuer, audience, signature/introspection, expiry, scope) và quyền nghiệp vụ liên kết với client, partner, relationship, dữ liệu và action cụ thể.

Nếu client W thuộc B nhưng request order của C, API phải từ chối dù token còn hạn và có scope đọc. Review cần xác nhận cơ chế này bằng policy và test, không chỉ bằng việc nhìn scope string.

### 13.3. Nhìn cả credential và phiên

Các đối tượng cần kiểm tra tùy môi trường:

- OAuth client registration và secret/public key;
- API key, certificate mTLS, workload federation mapping;
- Service account và quyền trong cloud IAM/SaaS;
- CI/CD tokens, deploy keys và webhook secrets;
- Refresh token, access token và quyền giữ phiên;
- Credential chia sẻ giữa nhiều partner hoặc nhiều môi trường;
- Khả năng chặn token cũ khi relationship bị revoked.

Với OAuth client credentials, access token có thể tiếp tục hoạt động đến expiry nếu API chỉ xác minh token offline mà không kiểm tra trạng thái entitlement. Review phải ghi nhận **revocation capability**, token TTL và giới hạn kỹ thuật của hệ thống.

### 13.4. Khi workload không còn owner

Một client active không có owner là finding có rủi ro đáng kể. Có thể:

1. Xác minh nguồn tích hợp và hợp đồng còn hiệu lực;
2. Giao technical owner mới và business sponsor nếu nhu cầu vẫn tồn tại;
3. Rà soát scope/key và rotate credential khi cần;
4. Nếu không còn nhu cầu hoặc không xác minh được ở mức rủi ro cao, suspend/revoke theo policy;
5. Kiểm chứng client không còn gọi API, đồng thời các client hợp lệ khác vẫn hoạt động.

Không chuyển một service account thành guest account của người để “có owner”: human identity và workload identity cần vòng đời riêng.

## 14. Kết nối kết quả review với Joiner–Mover–Leaver

### 14.1. Joiner: kiểm tra chất lượng quyền ban đầu

Trước khi tạo local guest hoặc workload mới, IAM cần biết đối tác, sponsor, resource owner, relationship, role/action, tenant, resource scope và thời hạn. Review đầu vào giúp tránh tạo quyền quá rộng ngay lúc onboarding.

Trong một kỳ review đầu tiên sau onboarding, có thể phát hiện những tài khoản đã được mời nhưng chưa bao giờ redeem, user bị trùng, sai source IdP, group mapping không khớp hoặc client chưa có owner. Các phát hiện nên kích hoạt sửa provisioning và thu hồi quyền không phù hợp.

### 14.2. Mover: gỡ quyền cũ khi đổi vai trò

Ví dụ U của B chuyển từ P42 sang P51. Một review theo sự kiện cần so sánh grants trước–sau:

| Trước Mover | Sau Mover được duyệt | Hành động |
|---|---|---|
| reports.read trên P42 | Không còn nhiệm vụ P42 | Revoke grant P42 |
| Không có quyền trên P51 | tickets.read P51 trong 30 ngày | Phê duyệt và provision P51 |
| guest account B active | Vẫn đại diện hợp lệ cho B | Giữ principal, thay membership |
| Quyền admin hỗ trợ P42 theo ticket | Ticket đã đóng | Kết thúc grant/phiên đặc quyền |

Nếu chỉ cấp thêm P51 mà giữ P42, quyền sẽ tích lũy (**privilege creep**). Review là nơi phát hiện và yêu cầu sửa sai lệch.

### 14.3. Leaver: review phải kích hoạt thu hồi có kiểm chứng

Leaver có thể là một người B nghỉ việc, một workload dừng, một hợp đồng hết hạn hoặc toàn bộ partner B offboard. Review cần nêu rõ **phạm vi cần thu hồi**, tránh vô tình ảnh hưởng relationship còn hiệu lực.

~~~mermaid
flowchart TD
    E["Sự kiện JML hoặc review theo lịch"] --> L{"Quyền còn hợp lệ?"}
    L -->|"Có"| KEEP["Keep đúng scope và hạn"]
    L -->|"Chỉ một phần"| RED["Reduce grant và role"]
    L -->|"Không"| REV["Revoke membership/grant"]
    L -->|"Không rõ/rủi ro"| SUS["Suspend hoặc escalate"]
    RED --> DOWN["IAM/app owner thực thi"]
    REV --> DOWN
    SUS --> DOWN
    DOWN --> SESS["Đánh giá session/token/credential liên quan"]
    SESS --> VERIFY["Đối soát actual access"]
    VERIFY --> DONE["Audit outcome và remediation"]
    KEEP --> DONE
~~~

**Leaver tại IdP B không tự thu hồi mọi quyền ở A.** SCIM inactive cũng không tự hủy tất cả JWT, API client và direct share. Cần kiểm tra ở từng điểm thực thi theo kết quả review.

### 14.4. Gia hạn hợp đồng không phải gia hạn vô điều kiện

Một hợp đồng được gia hạn thêm sáu tháng nhưng phạm vi công việc thu hẹp. Sponsor cần đánh giá từng user, workload và resource. Quyền P42 không còn nhu cầu phải revoke, trong khi quyền P51 còn hợp lệ có thể được gia hạn đúng thời gian và approval.

### 14.5. Đổi IdP và chuyển tài khoản

Khi B đổi issuer, review phải xác nhận việc liên kết (issuer cũ, subject cũ) với (issuer mới, subject mới) bằng bằng chứng đáng tin. Không tự nối account theo email để chuyển quyền; các grants cũ có thể được tiếp tục sau approval hoặc bị thu hồi theo scope mới.

## 15. Reconciliation: review có kết quả thật hay chỉ là giấy tờ?

### 15.1. Ba lớp trạng thái

| Lớp | Ví dụ | Tại sao cần phân biệt |
|---|---|---|
| Review decision | U bị Revoke quyền P42 | Ý chí quản trị đã ghi |
| Provisioning state | IAM/SCIM báo remove group thành công | Thao tác kỹ thuật đã được gửi/thực thi trong phạm vi tích hợp |
| Actual effective access | U vẫn có direct share P42 ở SaaS | Quyền thực tế có thể khác |

Một chiến dịch có thể hoàn tất 100% quyết định nhưng tỷ lệ quyền được thu hồi và **đã kiểm chứng** vẫn thấp. Do đó cần theo dõi hai kết quả riêng.

### 15.2. Phương pháp đối soát

~~~text
for each reviewItem in completedDecisions:
    desired = deriveExpectedAccess(
        reviewItem.decision,
        currentPartnerAndContractState,
        approvedGrants
    )
    actual = enumerateEffectiveAccessFromTargets(
        reviewItem.principal,
        reviewItem.resources
    )

    differences = compare(desired, actual)
    if differences:
        assignRemediationToTargetOwner(differences)
        recordRiskAndDueDate(differences)
        verifyAgainAfterChanges()
~~~

Mã giả không bảo đảm mọi SaaS/API đều cho phép liệt kê quyền; cần nêu rõ phạm vi không có API và cách xác nhận thay thế. Đối soát nên dùng cùng partner ID, principal ID và grant provenance để tránh xóa nhầm quyền của một relationship khác.

### 15.3. Kiểm thử sau quyết định

| Tình huống | Kỳ vọng |
|---|---|
| U bị Revoke P42 | Request đọc P42 bị DENY |
| U được giữ P51 | Request đúng scope P51 vẫn ALLOW |
| Workload W bị disable | W không xin token mới được; API từ chối khi phù hợp |
| Guest B không còn quan hệ hợp lệ | JIT không tái tạo quyền từ invitation cũ |
| User có role viewer nhưng object thuộc C | Backend DENY vì sai tenant |
| Quyền production JIT hết hạn | Phiên/quyền đặc biệt bị kết thúc |
| Group B bị remove từ SCIM | Direct share và ACL ngoài SCIM cũng được kiểm tra |

Kiểm thử phải dùng fixture/tài nguyên được phép, không truy cập dữ liệu thật ngoài quyền. Với JWT còn hạn, cần xác nhận cơ chế revocation/TTL của hệ thống và ghi rõ giới hạn nếu không thể chặn ngay.

### 15.4. Khi không thể xác minh

Nếu app đích không có API hoặc log phù hợp, review có thể ghi **applied but unverified** với owner và kế hoạch cải thiện, không báo “verified” vô căn cứ. Với quyền nhạy cảm, tổ chức có thể áp dụng chặn tại gateway hoặc kiểm soát bù có thời hạn khi chờ remediation.

### 15.5. Chống re-provision sau review

Nếu quyết định revoke đến trước một SCIM sync cũ đang treo, hệ thống có thể xóa quyền rồi vô tình cấp lại. Cần dùng **trạng thái partner/relationship**, version của quyết định, idempotency và kiểm tra policy khi apply. Không cho sự kiện cấp quyền đến trễ vượt qua trạng thái đã revoked.

## 16. Audit evidence và KPI của chương trình partner review

### 16.1. Bằng chứng tối thiểu để giải trình

Mỗi review item nên truy vết được:

1. **Đối tượng và scope:** partner/relationship, principal hoặc workload, tenant, resource, action, role và ngày hết hạn;
2. **Nguồn quyền:** request/ticket, group mapping hoặc direct share; ai là sponsor và resource owner;
3. **Thông tin tại thời điểm review:** snapshot, trạng thái hợp đồng, quyền đang có, mức rủi ro và dữ liệu sử dụng liên quan;
4. **Reviewer và thẩm quyền:** ai được phân công, có bị chuyển giao không, có xung đột SoD không;
5. **Quyết định:** Keep/Reduce/Revoke/Suspend/Reassign/Escalate, lý do, thời gian, điều kiện và hạn mới;
6. **Thực thi:** task ID, target application, trạng thái applied, lỗi, retries và người xử lý;
7. **Xác minh:** actual effective access, test allow/deny, evidence reference, sai lệch và exception;
8. **Đóng:** thời điểm, người chịu trách nhiệm và lưu vết theo retention policy.

Ví dụ audit event (minh họa):

~~~json
{
  "event_type": "partner_review.decision",
  "campaign_id": "PR-2026-Q4",
  "review_item_id": "REV-2026-Q4-0142",
  "partner_id": "partner-B",
  "relationship_id": "CTR-P42",
  "principal_id": "external-user-U",
  "resource_id": "reporting-P42",
  "decision": "revoke",
  "reason": "project_completed",
  "reviewer_id": "owner-A-9",
  "requested_at": "2026-11-23T07:00:00Z",
  "provisioning_state": "pending",
  "correlation_id": "review-revoke-9d12"
}
~~~

Đây **không phải** bằng chứng quyền đã được thu hồi: trạng thái vẫn là pending. Sau khi target thực hiện và được đối soát, hệ thống phải ghi event riêng về kết quả, có thể kèm mã target và kiểm chứng. Audit log cần được bảo vệ chống chỉnh sửa trái phép, hạn chế người đọc và tuân thủ retention; **không ghi mật khẩu, private key hoặc access token còn sử dụng được**.

### 16.2. Các KPI nên theo dõi

| KPI | Cách diễn giải |
|---|---|
| Review coverage | Phần trăm principal/grant/workload trong phạm vi được đưa vào campaign |
| Decision completion rate | Phần trăm review items có quyết định hợp lệ |
| Verified remediation rate | Phần trăm quyết định Reduce/Revoke đã xác minh trên target |
| Overdue reviews | Số item quá hạn hoặc không có reviewer đủ thẩm quyền |
| Orphaned partner access | Số grants không có sponsor/owner/relationship hợp lệ |
| Residual access after revoke | Số quyền còn hiệu lực tại ứng dụng sau quyết định thu hồi |
| Time to verified revoke | Thời gian từ quyết định/sự kiện Leaver đến xác minh quyền bị chặn |
| Privileged external grants | Số quyền admin/production còn thường trực hoặc quá hạn |
| Workload credentials without owner | Số client/key/cert không có technical owner hợp lệ |
| SCIM/JIT exceptions | Số sai lệch provisioning, tài khoản bị tạo lại hoặc sync error |
| Cross-tenant policy denies | Tín hiệu kiểm soát hoặc bất thường cần phân tích |

Chỉ số phải kèm **mẫu số, phạm vi và kỳ đo**. Ví dụ 100% decision completion không chứng minh 100% deprovision. Một chiến dịch bao phủ 50% hệ thống không nên công bố là đã review toàn bộ quyền đối tác.

### 16.3. Đừng tối ưu theo tốc độ bấm Approve

Nếu reviewer được đánh giá chỉ qua số quyết định hoàn tất, họ có thể chọn Keep hàng loạt mà không xem quyền. Tốt hơn là theo dõi **chất lượng dữ liệu**, số quyền dư bị gỡ đúng, thời gian remediation và phát hiện quyền mồ côi/đặc quyền.

### 16.4. Chỉ dùng dữ liệu cần thiết

Review có thể cần danh tính cá nhân, hợp đồng và nhật ký hoạt động. Hệ thống nên phân quyền reviewer theo phạm vi, giảm trường không cần thiết, hạn chế xuất báo cáo và giữ theo policy. Thông tin login hoặc activity là dữ liệu hỗ trợ quyết định chứ không tự trở thành mục đích giám sát vượt nhu cầu công việc.

## 17. Case study: rà soát đối tác B có hai hợp đồng

Giả sử công ty A điều hành nền tảng đơn hàng đa tenant. Đối tác B đang có hai hợp đồng:

- **CTR-P42:** phân phối đơn hàng tại tenant-B, sắp kết thúc;
- **CTR-P51:** hỗ trợ kỹ thuật cho ứng dụng staging, còn hiệu lực;
- Đối tác C có hợp đồng riêng và không liên quan kỳ review.

B có nhân viên U, V, W; API client ORDER-SYNC để cập nhật trạng thái đơn và client METRICS để gửi số liệu vận hành. Sponsor P42 là S-X, sponsor P51 là S-Y. Tất cả nhân viên B xác thực qua IdP B; A lưu guest/membership riêng.

### 17.1. Snapshot quyền tại thời điểm review

| Item | Trạng thái lúc review | Phát hiện | Đề xuất |
|---|---|---|---|
| U: reports.read P42 | Active, hợp đồng P42 sắp kết thúc | U sẽ rời dự án | Revoke khi P42 kết thúc |
| V: ticket.read P51 | Active, sponsor S-Y xác nhận | V còn nhiệm vụ hỗ trợ | Keep có hạn |
| W: admin trên production | Admin thường trực, ticket đã đóng | Không có nhu cầu admin liên tục | Revoke admin, chỉ dùng PAM/JIT khi được duyệt |
| ORDER-SYNC | OAuth client active theo P42 | Tích hợp ngừng khi P42 đóng | Disable client, revoke scope/credential |
| METRICS | Workload active theo P51 | Service còn cần, owner vừa chuyển công tác | Reassign owner, review token/scope |
| Direct file share của U | SaaS ACL active | Không nằm trong grant store IAM | Revoke nếu phụ thuộc P42 |

### 17.2. Kỳ review được triển khai

**Ngày bắt đầu:** IAM lấy snapshot, liên kết grants với CTR-P42/CTR-P51, đối chiếu local guest, OAuth clients, group và SaaS sharing. IAM phát hiện một direct share thiếu source request và một quyền admin thường trực không có ticket đang mở.

**Reviewer S-X:** xác nhận U không cần P42 khi hợp đồng kết thúc, ORDER-SYNC không còn mục đích, và direct share P42 phải gỡ. Resource owner P42 duyệt revoke đúng các grants liên quan.

**Reviewer S-Y:** xác nhận V vẫn cần quyền đọc ticket ở P51. Với METRICS, S-Y và platform owner chỉ định technical owner mới, kiểm tra scope đúng API và quay vòng secret theo chính sách nếu người cũ từng nắm giữ.

**Security:** xác nhận role production admin của W không nên thường trực; xóa quyền admin và sử dụng approval JIT/PAM theo ticket nếu cần trong tương lai.

### 17.3. Quyết định và kết quả áp dụng

| Item | Quyết định | Điều cần kiểm chứng |
|---|---|---|
| U / P42 | Revoke | U không đọc được báo cáo P42 sau cutover |
| V / P51 | Keep | V vẫn đọc đúng ticket P51, không vượt tenant |
| W / production | Revoke privileged grant | Không còn quyền admin hoặc phiên đặc quyền tồn dư |
| ORDER-SYNC | Revoke | Client không lấy token mới và API không còn nhận quyền P42 |
| METRICS | Reassign + Keep scoped access | Có owner mới; client chỉ đọc dữ liệu P51 |
| U / direct share | Revoke | URL/file share cũ không còn cho U đọc |

Sau khi IAM gỡ group P42 của U, ứng dụng tài liệu vẫn giữ direct share. Reconciliation phát hiện sai lệch. App owner thu hồi share và xác minh lại; **chỉ sau đó item mới được xem là revoked_verified**.

### 17.4. Kiểm thử giữ đúng quyền của quan hệ còn hiệu lực

B vẫn có hợp đồng P51; hệ thống phải bảo đảm **V và METRICS tiếp tục hoạt động đúng phạm vi**. Đối tác C cũng phải đăng nhập bình thường. Không xóa IdP trust B chỉ vì CTR-P42 kết thúc, vì P51 vẫn phụ thuộc vào trust đó.

### 17.5. Bài học từ case study

Một campaign review có kết quả tốt không phải là “mọi tài khoản B đều bị khóa”. Kết quả đúng là **cắt bỏ quyền không còn hợp lệ, giữ quyền hợp lệ đã chứng minh, giảm đặc quyền và khép kín các lỗ hổng inventory**. Cần cùng lúc xét con người, workload, trust và ứng dụng đích.

## 18. Runbook thực hành: tổ chức một chiến dịch review đối tác

### Giai đoạn A — Lập kế hoạch

1. Chọn partner, relationship, hệ thống, role và loại danh tính thuộc phạm vi.
2. Xác định rủi ro, deadline, chính sách khi không phản hồi và người chịu trách nhiệm.
3. Thu thập nguồn hợp đồng, IdP/SSO, IAM, SCIM, app, API, PAM và audit.
4. Liệt kê các hệ thống không xuất được quyền hoặc có direct shares ngoài IAM.
5. Chụp snapshot có version/thời gian và lưu audit chiến dịch.

**Tiêu chí xong:** có danh sách item đủ dữ liệu tối thiểu, nhận diện được những khoảng trống inventory và reviewer.

### Giai đoạn B — Chuẩn bị quyết định

1. Liên kết mỗi principal/grant với partner và relationship đúng.
2. Bổ sung sponsor, resource owner, business justification và hạn.
3. Tính effective rights từ cả group, role và direct shares nếu có thể.
4. Xác định quyền đặc biệt, SoD conflict, orphaned accounts, stale grants và credential không owner.
5. Phân công người có thẩm quyền, tạo lịch review theo mức rủi ro.

**Tiêu chí xong:** reviewer có thể trả lời quyền này dùng để làm gì, trên tài nguyên nào và kết thúc khi nào.

### Giai đoạn C — Thu thập quyết định

1. Reviewer xác nhận Keep, Reduce, Revoke, Suspend hoặc Escalate theo scope.
2. Yêu cầu lý do/hạn mới khi chọn Keep với quyền rủi ro cao.
3. Kiểm tra approval bổ sung khi quyền nhạy cảm hoặc tăng quyền.
4. Reassign item nếu reviewer không còn hợp lệ.
5. Escalate quá hạn; không mặc định im lặng là phê duyệt.

**Tiêu chí xong:** mỗi item có quyết định hợp lệ hoặc ngoại lệ còn được quản lý có người chịu trách nhiệm.

### Giai đoạn D — Áp dụng và đối soát

1. IAM triển khai thay đổi với idempotency/version phù hợp.
2. App owner gỡ direct shares, ACL, group và role không thuộc provisioning trung tâm.
3. Với workload: disable client, rotate/revoke credential, kiểm tra API grants.
4. Xử lý session/token/PAM khi revoke phải chặn truy cập thực tế.
5. Đối soát desired/actual; kiểm thử allow/deny với dữ liệu được phép.
6. Tạo remediation task cho target lỗi hoặc chưa kiểm chứng.

**Tiêu chí xong:** kết quả thực thi đạt phạm vi kiểm chứng yêu cầu, không làm mất quyền hợp lệ khác.

### Giai đoạn E — Đóng và cải tiến

1. Lưu snapshot, decisions, approvals, target results, exceptions và owner.
2. Tổng hợp KPI riêng cho coverage, decision completion và verified remediation.
3. Đánh giá nguyên nhân phát sinh quyền tồn dư: thiếu HR/SCIM event, grant thủ công, owner rời công ty, scope quá rộng?
4. Sửa quy trình Joiner/Mover/Leaver, không đợi kỳ review sau để phát hiện cùng lỗi.
5. Lên lịch review tiếp theo theo policy và theo sự kiện.

**Tiêu chí xong:** audit đủ để tái hiện quyết định, những sai lệch còn lại có kế hoạch giải quyết.

### Minh họa cấu hình chiến dịch

~~~yaml
partner_review:
  campaign_id: "PR-2026-Q4"
  partner_id: "partner-B"
  scope:
    relationship_ids:
      - "CTR-P42"
      - "CTR-P51"
    include:
      - "human_principals"
      - "service_accounts"
      - "oauth_clients"
      - "direct_shares"
      - "privileged_grants"
  reviewers:
    require_business_sponsor: true
    require_resource_owner_for_sensitive_data: true
  decisions:
    allowed:
      - "keep"
      - "reduce"
      - "revoke"
      - "suspend"
      - "escalate"
  verification:
    reconcile_target_access: true
    record_unverified_targets: true
    test_cross_tenant_isolation: true
  close_when:
    require_recorded_decisions: true
    require_remediation_or_approved_exception: true
~~~

Đây là YAML giải thích cấu trúc, **không phải cấu hình có thể đưa trực tiếp vào sản phẩm**. Các trường và điều kiện phải được điều chỉnh theo công cụ IAM, mô hình ownership và chính sách của tổ chức.

## 19. Anti-pattern trong partner review

| Sai lầm | Hệ quả | Cách khắc phục |
|---|---|---|
| Review chỉ dựa trên partner.status | Hợp đồng/dự án con hết hạn vẫn giữ quyền | Review tới relationship/grant cụ thể |
| Chỉ có danh sách email | Ghép nhầm danh tính, không biết scope | Dùng principal ID, issuer/subject, partner mapping |
| Reviewer bấm Keep hàng loạt | Quyền thừa được tái chứng nhận hình thức | Hiển thị business need, risk và resource scope |
| Sponsor inactive nhưng không được thay thế | Không có người chịu trách nhiệm | Reassign và recertify, xử lý quá hạn |
| Review chỉ human users | API client và service account tồn dư | Bao phủ workload, owner, credential, scope |
| Chỉ nhìn role từ IdP | Quyền tại A có thể được cấp thủ công | Đối soát effective rights ở app đích |
| Tin group Global-Admin từ IdP B | Partner có thể tự nâng quyền | Mapping/trần quyền do A quản lý |
| Không kiểm tra tenant/object | User B đọc dữ liệu C | Kiểm tra ABAC/object-level authorization tại backend |
| Tự Keep khi không có activity | Có thể bỏ quyền nhạy cảm ít dùng hoặc giữ nhầm quyền | Xác nhận mục đích và rủi ro, không suy từ activity đơn lẻ |
| Quyết định Revoke không được thực thi | Review đẹp trên dashboard nhưng quyền vẫn còn | Theo dõi task/applied/verified và remediation |
| Không phát hiện direct share | ACL ngoài IAM còn sống | Inventory SaaS/file sharing, reconciliation |
| SCIM đến muộn tái cấp quyền | Hồi sinh user/grant đã revoked | Trạng thái relationship, idempotency và version |
| Gia hạn hợp đồng đồng nghĩa Keep mọi grant | Privilege creep | Đánh giá từng principal/action/resource |
| Thu hồi issuer dùng chung không kiểm tra | Làm gián đoạn đối tác/hợp đồng hợp lệ | Kiểm tra trust references và dependencies |
| Không giữ snapshot/audit | Không giải trình được ai đã duyệt | Lưu decisions, owner, source và target evidence |
| Đóng campaign dù còn lỗi trọng yếu | Không biết actual access | Ghi exception/compensating control và theo dõi |

## 20. Checklist triển khai Partner Review

### A. Phạm vi và chủ sở hữu

- [ ] Đối tác có partner_id, relationship/contract ID và trạng thái rõ ràng.
- [ ] Campaign xác định chính xác tenant, dự án, ứng dụng, loại quyền và thời điểm snapshot.
- [ ] Bao phủ human guest, federated principal, workload/service account và direct shares.
- [ ] Sponsor, resource owner và technical owner còn hợp lệ, đủ thẩm quyền.
- [ ] Các hệ thống không cung cấp inventory tự động được liệt kê như giới hạn.

### B. Chất lượng quyết định

- [ ] Reviewer thấy business purpose, role/action, resource, tenant/project và expiry.
- [ ] Có nguồn phê duyệt và trạng thái hợp đồng cho mỗi grant.
- [ ] Có đánh giá mức nhạy dữ liệu, đặc quyền và phạm vi ảnh hưởng.
- [ ] Phân tách nhiệm vụ được áp dụng cho quyền nhạy cảm.
- [ ] Cho phép Keep/Reduce/Revoke/Suspend/Escalate có lý do, không tự gia hạn vô hạn.
- [ ] Item không có reviewer hợp lệ được reassign; quá hạn được escalate.

### C. IAM, SSO và provisioning

- [ ] IdP/SSO trust có owner, issuer/entityID và mapping được kiểm soát.
- [ ] External principal liên kết bằng định danh ổn định, không ghép chỉ theo email.
- [ ] Group claims từ đối tác không tự vượt RBAC role ceiling của A.
- [ ] SCIM/JIT xử lý Mover/Leaver và không tái cấp quyền trái trạng thái.
- [ ] RBAC/ABAC thực thi tenant/resource/action/expiry ở API/backend.
- [ ] Service account/OAuth client có owner, scope/audience và credential lifecycle phù hợp.

### D. Sau review

- [ ] Các quyết định Reduce/Revoke đã được đưa đến đúng hệ thống đích.
- [ ] Session/refresh token, access token và PAM được đánh giá theo khả năng revocation.
- [ ] Direct share, ACL, SaaS, repository và cloud grants được kiểm tra khi thuộc phạm vi.
- [ ] Reconciliation so sánh desired và actual effective rights.
- [ ] Có kiểm thử quyền bị DENY và quyền hợp lệ khác vẫn ALLOW.
- [ ] Ngoại lệ có owner, mức rủi ro, deadline, compensating control và kế hoạch xác minh.
- [ ] Snapshot, approvals, audit và báo cáo KPI được lưu đúng chính sách.

## 21. Câu hỏi tự kiểm tra

**Câu 1.** Hợp đồng của B còn active và nhân viên U đăng nhập SSO thành công. U có cần access review không?

**Trả lời:** Có. IdP xác thực danh tính, nhưng không chứng minh mọi grant còn có mục đích. Review phải xét nhiệm vụ, resource owner, tenant, action, expiry và trạng thái quyền thực tế.

**Câu 2.** Một đối tác có hai hợp đồng P42 và P51. Nếu P42 kết thúc, reviewer phải làm gì?

**Trả lời:** Thu hồi grants phụ thuộc P42 và kiểm chứng downstream; giữ quyền P51 nếu relationship, owner và nhu cầu vẫn hợp lệ. Không mặc định disable toàn bộ partner hoặc IdP dùng chung.

**Câu 3.** Sponsor bấm Revoke trên dashboard. Đã hoàn tất access review chưa?

**Trả lời:** Mới ghi quyết định. IAM/app owner phải thực thi revoke, xử lý phiên/token nếu liên quan và kiểm chứng actual access. Lỗi ở ứng dụng đích cần remediation hoặc ngoại lệ rõ ràng.

**Câu 4.** Vì sao review phải bao gồm OAuth clients và service accounts?

**Trả lời:** Chúng là danh tính máy, có thể tiếp tục chạy sau khi nhân viên hoặc hợp đồng kết thúc. Cần kiểm tra owner, API scope, tenant, credential, activity, expiry và khả năng thu hồi.

**Câu 5.** Guest U không đăng nhập sáu tháng. Có thể tự khẳng định quyền không còn cần?

**Trả lời:** Không. Đây là tín hiệu cần điều tra, không phải chứng cứ duy nhất. Sponsor và resource owner cần đối chiếu công việc, hợp đồng, quyền còn hiệu lực, mức rủi ro và các cách sử dụng khác.

**Câu 6.** SCIM báo active=false nhưng một SaaS vẫn cho U xem tài liệu. Review phát hiện điều gì?

**Trả lời:** Desired/provisioned state lệch actual effective access; quyền có thể đến từ direct share hoặc app ngoài phạm vi SCIM. Cần gỡ ACL, kiểm tra session và đối soát lại.

**Câu 7.** Vì sao không nên dùng email làm khóa định danh để hợp nhất user từ hai IdP?

**Trả lời:** Email có thể đổi hoặc tái sử dụng. Cần nguồn issuer và định danh chủ thể ổn định đã được xác minh, cùng quy trình account linking đáng tin để tránh gán quyền sai người.

**Câu 8.** User B có role report_viewer nhưng gọi API lấy báo cáo tenant-C. Phần nào phải chặn?

**Trả lời:** Backend/resource server phải kiểm tra resource ownership, tenant/project và membership/grant; role viewer không tự cho phép xem mọi đối tượng.

**Câu 9.** Một OAuth token còn hạn sau quyết định Revoke. Reviewer có thể đánh dấu Verified ngay không?

**Trả lời:** Chỉ khi cơ chế thực thi đã kiểm chứng request không còn được phép trong phạm vi yêu cầu. Token tự chứa có thể tiếp tục được chấp nhận đến expiry nếu API không kiểm tra trạng thái hiện hành; cần ghi nhận TTL/giới hạn hoặc áp dụng kiểm soát khác.

**Câu 10.** Sponsor nghỉ việc khi review chưa hoàn tất. Hệ thống cần xử lý gì?

**Trả lời:** Tìm và chuyển quyền review/grants cho người có trách nhiệm mới, tái xác nhận nhu cầu, xử lý quá hạn hoặc tạm khóa theo rủi ro; không xem im lặng là phê duyệt.

**Câu 11.** Cần những loại KPI nào để biết review có hiệu quả?

**Trả lời:** Ít nhất phải phân biệt coverage, tỷ lệ item có quyết định hợp lệ, tỷ lệ remediation đã được verified, số quyền mồ côi/tồn dư và thời gian tới khi thu hồi thực tế. Chỉ số lượt nhấn Approve không đủ.

**Câu 12.** Khi B quay lại hợp tác sau khi toàn bộ quyền đã bị revoke, có nên khôi phục roles cũ?

**Trả lời:** Không tự động. Cần kiểm tra quan hệ/hợp đồng mới, danh tính và owner, rồi cấp những quyền tối thiểu theo Joiner hoặc Mover mới được phê duyệt. Tránh phục hồi các quyền từng bị thu hồi.

## Kết luận

**Partner review** biến việc “đối tác vẫn có quyền” thành một quyết định có căn cứ, được rà soát định kỳ và khi xuất hiện sự kiện **Joiner–Mover–Leaver**. Review hiệu quả phải xem xét đồng thời **quan hệ đối tác, con người, workload, quyền trên từng tài nguyên, hợp đồng, thời hạn và trách nhiệm phê duyệt**. **IdP/SSO** cung cấp nền tảng xác thực, **SCIM/JIT** hỗ trợ provisioning, **RBAC/ABAC** giới hạn quyền, còn **audit/reconciliation** cho biết quyết định đã thực sự có hiệu lực hay chưa.

Một chiến dịch được xem là có giá trị không chỉ vì nhiều người đã hoàn tất biểu mẫu, mà vì tổ chức **giữ đúng quyền còn cần, gỡ quyền thừa, xử lý quyền mồ côi, phát hiện sai lệch và kiểm chứng kết quả tại hệ thống đích**. Đây là cách giảm truy cập tồn dư mà không làm gián đoạn những quan hệ B2B vẫn hợp lệ.
