# Guest account: tài khoản khách trong quản lý vòng đời danh tính IAM

## 1. Guest account là gì và vì sao cần quản lý?

Trong **Identity and Access Management (IAM)**, **guest account** (tài khoản khách) là bản ghi danh tính hoặc tài khoản được tổ chức **cung cấp tài nguyên** tạo ra để một chủ thể **bên ngoài phạm vi nhân sự nội bộ** có thể sử dụng ứng dụng, dữ liệu hoặc dịch vụ đã được cấp quyền. Người khách có thể là chuyên gia tư vấn, nhà cung cấp, nhân viên đối tác, kiểm toán viên hoặc người cộng tác theo dự án.

Ví dụ: Công ty A mời kỹ sư của công ty B xem tài liệu dự án P42. A tạo một guest record, gắn với B, người bảo trợ phía A, dự án P42, quyền đọc tài liệu và hạn truy cập. Kỹ sư B có thể xác thực bằng IdP của B rồi sử dụng guest record tại A để nhận quyền được duyệt. Khi hợp đồng kết thúc, A thu hồi quyền cho guest, kể cả khi tài khoản gốc ở B vẫn còn hoạt động.

Vì vậy, một guest account thường biểu diễn hai khía cạnh khác nhau:

- **Identity/authentication:** Ai đã đăng nhập, bằng nguồn danh tính nào và bằng chứng có hợp lệ không?
- **Local authorization/lifecycle:** Tổ chức A có chấp nhận chủ thể đó làm khách không, gắn với sponsor/tenant/dự án nào, được thao tác gì và đến khi nào?

Trong module **SECURITY_IDENTITY_ACCESS_MANAGEMENT_IDENTITY_LIFECYCLE**, guest account là một trường hợp quan trọng của quản lý vòng đời **Joiner–Mover–Leaver**: xác minh, mời/tạo tài khoản, liên kết danh tính, cấp quyền; thay đổi quyền khi nhiệm vụ chuyển dịch; rà soát và thu hồi truy cập khi không còn nhu cầu. Chủ đề liên hệ trực tiếp tới **IdP, SSO, SCIM, RBAC/ABAC, tài khoản dịch vụ, kiểm toán và giảm quyền truy cập tồn dư**.

### Phân biệt những thuật ngữ dễ nhầm

| Thuật ngữ | Ý nghĩa | Quan hệ với guest account |
|---|---|---|
| External user | Con người bên ngoài cần truy cập | Có thể được đại diện bằng guest record tại hệ thống A |
| Guest account / guest record | Bản ghi truy cập tại tổ chức nhận | Lưu định danh liên kết, trạng thái, owner, membership và quyền |
| Home identity | Danh tính gốc do nơi khác quản lý | Người B đăng nhập qua IdP B |
| Federated identity | Danh tính được chứng minh qua trust giữa IdP và ứng dụng | Guest có thể sử dụng OIDC/SAML để xác thực |
| Partner/vendor identity | Danh tính và quan hệ cấp tổ chức bên ngoài | Một partner/vendor có thể có nhiều guest |
| Member/internal account | Danh tính thuộc phạm vi quản trị nội bộ theo chính sách hệ thống | Có lifecycle và nguồn sự kiện khác |
| Service account/workload identity | Danh tính của chương trình, agent hoặc tác vụ tự động | Cần quản lý riêng; không dùng guest của con người làm robot |

**“Guest” không nhất thiết có nghĩa là mật khẩu riêng tại tổ chức A.** Trong nhiều mô hình, A chỉ lưu bản ghi khách và ủy thác xác thực cho IdP B. Một số hệ thống khác dùng tài khoản được A quản lý hoặc phương thức đăng nhập một lần. Cần mô tả chính xác **ai xác thực**, **ai cấp quyền** và **ai thu hồi phiên** thay vì suy đoán chỉ từ nhãn guest.

## 2. Ba mô hình guest account thường gặp

### 2.1. Guest được liên kết với IdP bên ngoài

Người dùng xác thực bằng tài khoản đang có tại IdP của tổ chức họ. Ứng dụng hoặc hệ thống IAM của A kiểm tra token/assertion và ánh xạ danh tính ngoài sang guest record tại A.

**Ưu điểm:** giảm tài khoản mật khẩu rời rạc, hỗ trợ trải nghiệm SSO, có thể tận dụng MFA của IdP đã được tin cậy. **Giới hạn:** A phụ thuộc vào cấu hình federation và độ kịp thời của tín hiệu Mover/Leaver từ đối tác; phiên và quyền tại A vẫn phải được kiểm soát riêng.

### 2.2. Guest dùng danh tính do tổ chức A quản lý

A cấp một phương thức đăng nhập riêng cho người ngoài, ví dụ tài khoản được quản trị trực tiếp, mật khẩu kèm MFA hoặc phương thức không mật khẩu theo chính sách của A.

**Ưu điểm:** A chủ động hơn về xác thực, khóa tài khoản và hỗ trợ người dùng. **Giới hạn:** phát sinh trách nhiệm bảo vệ credential, đặt lại phương thức xác thực, đồng bộ nghỉ việc và tránh tài khoản mồ côi.

### 2.3. Guest dùng lời mời hoặc đăng nhập xác minh qua email

Một số ứng dụng hỗ trợ invitation kèm đường dẫn xác nhận và đăng nhập bằng mã/đường dẫn một lần. Phương thức này có thể phù hợp với hợp tác ngắn hạn, tùy loại dữ liệu và chính sách rủi ro.

**Giới hạn:** Việc nhận được email hoặc nắm giữ một liên kết chưa tự chứng minh người nhận thuộc đúng tổ chức, đang có vai trò hợp lệ hoặc đã được cấp mọi quyền. Invitation cần hết hạn, chống dùng lại khi thích hợp, ràng buộc đúng người/ngữ cảnh và có phê duyệt riêng.

| Tiêu chí | Federation qua IdP ngoài | Tài khoản do A quản lý | Email-based invitation/login |
|---|---|---|---|
| Nguồn xác thực | IdP của tổ chức ngoài | Hệ thống A | Cơ chế email và xác minh bổ sung |
| Bảo trì credential | Chủ yếu bên ngoài | A | Phụ thuộc nhà cung cấp dịch vụ đăng nhập |
| SSO | Thường phù hợp | Tùy thiết kế | Có thể không có |
| Tín hiệu nghỉ việc | Cần tích hợp/đối soát | Chủ yếu từ sponsor hoặc HR/đối tác | Cần hạn truy cập và rà soát độc lập |
| Trách nhiệm cấp quyền tài nguyên A | A | A | A |

Không có mô hình nào tự động an toàn trong mọi trường hợp. Quyết định phụ thuộc rủi ro, thời hạn hợp tác, yêu cầu MFA, độ nhạy dữ liệu, khả năng provisioning và trách nhiệm của đối tác.

## 3. Kiến trúc: IdP, guest record, membership và resource server

~~~mermaid
flowchart LR
    subgraph OUT["Bên ngoài: tổ chức B"]
      USER["Người dùng B"] --> IDP["IdP B"]
    end
    subgraph IN["Tổ chức A"]
      APP["Ứng dụng / SSO entry"]
      GUEST["Guest directory / identity record"]
      MEM["Membership + grant + expiry"]
      POL["RBAC / ABAC policy"]
      DATA["API và tài nguyên theo tenant"]
      AUD["Audit + access review"]
      APP --> POL
      POL --> GUEST
      POL --> MEM
      POL --> DATA
      GUEST --> AUD
      MEM --> AUD
      DATA --> AUD
    end
    IDP <-->|"OIDC / SAML khi có federation"| APP
    SP["Sponsor / resource owner A"] -->|"Mời, duyệt, rà soát"| MEM
    PROV["Nguồn lifecycle có kiểm soát"] -->|"SCIM nếu được hỗ trợ"| GUEST
~~~

Trong mô hình này, **IdP B** chịu trách nhiệm về bằng chứng xác thực từ nguồn đã được A tin cậy. **Guest directory** của A lưu danh tính bên ngoài được liên kết, trạng thái và dấu vết. **Membership/grant** xác định người khách được truy cập tenant, nhóm, dự án, tài nguyên và hành động nào. **Policy tại backend** kiểm tra tất cả điều kiện trước khi cho phép truy cập.

### 3.1. Dữ liệu tối thiểu hữu ích cho một guest

| Trường | Tác dụng | Ví dụ |
|---|---|---|
| guest_id | Khóa nội bộ ổn định | G-1084 |
| external_subject | Định danh từ IdP đã xác thực | Cặp issuer + subject |
| home_organization_id | Tổ chức nguồn đã xác minh | partner-B |
| sponsor_id | Người nội bộ chịu trách nhiệm | employee-A-17 |
| invitation_id / request_id | Nguồn gốc và phê duyệt | INV-2042 |
| status | pending, active, suspended, revoked... | active |
| membership | Tenant, dự án, nhóm/vai trò | tenant-B / P42 / viewer |
| valid_from / expires_at | Thời điểm quyền có hiệu lực và hết hạn | 2026-12-31 |
| last_reviewed_at | Bằng chứng rà soát gần nhất | Theo lịch nội bộ |
| provisioning_source | Invitation, JIT, SCIM hoặc quy trình khác | invitation |

**Guest record và entitlement là các thực thể có thể có vòng đời khác nhau.** Một người khách có thể được phép ở lại trong danh bạ để lưu lịch sử audit, nhưng không còn bất kỳ membership đang hoạt động nào. Ngược lại, không được xem một guest đang có trạng thái active là mặc nhiên có quyền truy cập mọi tài nguyên.

### 3.2. Không dùng email làm khóa ghép duy nhất

Email có thể đổi sau sáp nhập, được cấp lại cho nhân viên mới hoặc dùng với nhiều danh tính. Với OIDC, hệ thống nên liên kết bằng **(iss, sub)** sau khi xác minh ID token. Với SAML, liên kết định danh ổn định từ issuer đã được đăng ký. Khi đổi IdP, cần quy trình chứng minh danh tính cũ–mới và chuyển liên kết có kiểm soát.

Không tự động ghép một người mới với guest cũ chỉ vì email trùng. Điều đó có thể khiến người mới kế thừa quyền và lịch sử của người trước.

## 4. Guest Joiner: yêu cầu và mời truy cập

**Joiner** với guest bắt đầu bằng **nhu cầu truy cập hợp lệ**, không đơn thuần là việc nhập một địa chỉ email vào danh sách mời.

### 4.1. Xác minh nhu cầu và người bảo trợ

Trước khi gửi lời mời, chủ tài nguyên hoặc sponsor cần xác nhận:

1. Người được mời là ai, thuộc tổ chức nào, mục đích hợp tác có thực không?
2. Ai phía A chịu trách nhiệm về nhu cầu và việc rà soát tài khoản?
3. Những ứng dụng, tenant, dự án, đối tượng dữ liệu và hành động nào cần thiết?
4. Quyền được cấp trong bao lâu, có hạn tự động và điều kiện gia hạn không?
5. Dữ liệu có nhạy cảm hoặc yêu cầu đặc quyền, MFA, bước phê duyệt bổ sung không?
6. Nguồn xác thực của người dùng và kênh xác minh danh tính có đủ tin cậy không?

Đối với nhà thầu làm việc trong hệ thống production, cấp quyền chỉ đọc vào dashboard và quyền quản trị máy chủ là hai yêu cầu khác nhau về rủi ro. Không lấy một lời mời cộng tác để cấp tất cả các quyền.

### 4.2. Bản ghi yêu cầu mời

Ví dụ mô hình dữ liệu minh họa:

~~~yaml
invitation:
  id: "INV-2042"
  requested_identity:
    email_for_delivery: "consultant@partner.example"
    expected_organization: "partner-B"
  sponsor_id: "employee-A-17"
  project_id: "P42"
  tenant_id: "tenant-B"
  requested_role: "document_reader"
  business_reason: "review-design-document"
  invitation_expires_at: "2026-12-01T00:00:00Z"
  access_expires_at: "2026-12-31T00:00:00Z"
  approval_state: "approved"
~~~

Đây là cấu trúc logic, không phải chuẩn API cụ thể. Trường **invitation_expires_at** chỉ giới hạn thời gian chấp nhận lời mời; **access_expires_at** giới hạn thời gian quyền tồn tại sau khi chấp nhận. Hai thời hạn cần được quản lý riêng.

### 4.3. Các trạng thái thường gặp

| Trạng thái minh họa | Ý nghĩa | Hành động an toàn |
|---|---|---|
| requested | Có đề nghị chưa được duyệt | Chưa cấp quyền tài nguyên |
| invited / pending | Lời mời đã phát, chưa xác minh/chấp nhận đầy đủ | Chỉ cho các bước hoàn tất onboarding |
| active | Đã liên kết danh tính, đáp ứng điều kiện và có grant hợp lệ | Kiểm tra quyền tại từng request |
| suspended | Tạm khóa vì rủi ro, cần xác minh hoặc không rõ sponsor | Từ chối truy cập trong phạm vi bị đình chỉ |
| expired | Thời hạn không còn hiệu lực | Không tự gia hạn quyền nếu thiếu phê duyệt |
| revoked | Quyền hoặc guest bị thu hồi theo quyết định IAM | Chặn quyền/phiên liên quan, giữ audit theo chính sách |

Tên trạng thái và mô hình chuyển trạng thái phụ thuộc hệ thống. **Chấp nhận invitation không đồng nghĩa có quyền vĩnh viễn**; trạng thái local principal, membership và grant đều phải đáp ứng policy hiện hành.

## 5. Invitation redemption: chấp nhận lời mời an toàn

**Redemption** là quá trình người nhận sử dụng lời mời để chứng minh mình là chủ thể dự kiến và hoàn tất liên kết guest record với danh tính thực sự dùng để đăng nhập.

~~~mermaid
sequenceDiagram
    participant S as Sponsor A
    participant I as Invitation/IAM A
    actor U as Người nhận B
    participant IDP as IdP B
    participant APP as Ứng dụng A
    S->>I: Yêu cầu + phê duyệt + scope/expiry
    I-->>U: Lời mời có hạn
    U->>I: Mở lời mời
    I->>IDP: Chuyển tới nguồn xác thực đã tin cậy
    U->>IDP: Xác thực / MFA theo chính sách
    IDP-->>I: Assertion hoặc token hợp lệ
    I->>I: Xác minh subject, issuer, invitation binding
    I->>I: Liên kết guest và grant được duyệt
    U->>APP: Truy cập tài nguyên
    APP->>I: Kiểm tra status, scope, expiry
    I-->>APP: Allow hoặc deny
~~~

Quy trình chấp nhận cần quan tâm:

1. **Lời mời có hạn và có ngữ cảnh:** gắn request, sponsor, đối tượng nhận và scope; không để invitation trở thành URL mở quyền vô thời hạn.
2. **Xác thực thực sự:** xác minh người chấp nhận qua IdP hoặc cơ chế được chính sách chấp thuận, không chỉ tin tên hiển thị.
3. **Ràng buộc identity:** kiểm tra issuer và subject hoặc định danh đáng tin cậy khác; yêu cầu xác nhận bổ sung nếu lời mời có thể chuyển tiếp hoặc danh tính không khớp.
4. **Chống replay và lạm dụng:** giới hạn số lần, hạn token, cơ chế vô hiệu hóa invitation và theo dõi hành vi đáng ngờ khi hệ thống hỗ trợ.
5. **Phê duyệt quyền độc lập:** việc bấm “Accept” xác nhận hoàn tất onboarding, không vượt qua bước duyệt role, tenant hoặc tài nguyên.
6. **Ghi audit:** ai mời, ai duyệt, nguồn đăng nhập nào, lúc nào được liên kết, kết quả chấp nhận hay từ chối.

### Hai tình huống quan trọng

**Lời mời bị chuyển tiếp:** A gửi lời mời cho người B nhưng email bị chuyển đến người khác. Nếu hệ thống chỉ kiểm tra ai đang giữ liên kết, người lạ có thể nhận quyền. Cần giới hạn danh tính hoặc dùng cơ chế xác minh ngữ cảnh và phê duyệt đủ mạnh cho tài nguyên cần bảo vệ.

**Email được tái sử dụng:** một người B rời công ty, email đó được cấp cho người mới. Không tự liên kết người mới với guest cũ và giữ nguyên role; nếu external subject đã thay đổi, phải xử lý như một sự kiện identity linking cần xác minh.

## 6. Guest provisioning: invitation, JIT và SCIM

Ba cách khởi tạo bản ghi có thể kết hợp tùy ứng dụng:

| Cơ chế | Khi nào phù hợp | Điều cần kiểm soát |
|---|---|---|
| Invitation/pre-provisioning | Cần sponsor duyệt trước, biết trước danh sách khách | Hạn mời, ngữ cảnh, trạng thái pending, quyền tối thiểu |
| JIT provisioning | Người ngoài đăng nhập lần đầu mới tạo local guest | Chặn tự cấp quyền khi chưa có invitation/quan hệ hợp lệ |
| SCIM provisioning | Có hệ thống nguồn và đích hỗ trợ đồng bộ user/group | Đúng source/partner, xử lý lỗi, mapping và deactivation |

### 6.1. JIT không phải tự động cấp quyền

**Just-in-time (JIT) provisioning** là tạo local guest tại lần đăng nhập đầu tiên. Ví dụ, sau OIDC login thành công, IAM có thể tạo user ở trạng thái pending/no-access. Chỉ khi tìm được invitation còn hiệu lực và grant được sponsor duyệt, guest mới có quyền cụ thể.

Nếu ứng dụng cấu hình “mọi tài khoản thuộc domain B được role editor”, nhân viên B không liên quan dự án cũng có thể nhận quyền. Điều này trái nguyên tắc **least privilege** và phá ranh giới tenant.

### 6.2. SCIM quản lý trạng thái và group

Khi dùng SCIM, một nguồn provisioning đã được ủy quyền có thể tạo, cập nhật hoặc vô hiệu hóa user/group tại hệ thống nhận. Ví dụ PATCH SCIM:

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

Ví dụ chỉ minh họa cú pháp, không có nghĩa mọi IdP/ứng dụng đều hỗ trợ SCIM hoặc thao tác trên. Hệ thống phải xác thực SCIM client, giới hạn quyền theo partner/tenant, đối soát response và xử lý retry nếu đồng bộ lỗi.

**SCIM khác với SSO.** SCIM cập nhật bản ghi người dùng/nhóm; OIDC/SAML phục vụ xác thực; RBAC/ABAC quyết định quyền. SCIM đặt inactive không đảm bảo mọi phiên ứng dụng hoặc access token đã phát hành bị hủy tức thời.

### 6.3. Nguồn nào là nguồn sự thật?

Nên xác định chủ sở hữu cho từng thuộc tính:

| Thuộc tính | Chủ sở hữu thường phù hợp |
|---|---|
| Người B còn thuộc tổ chức B không | IdP/HR hoặc đầu mối quản trị được B ủy quyền |
| Quan hệ/hợp đồng A–B còn hiệu lực không | Hệ thống quản lý đối tác/hợp đồng và owner A |
| Người B được truy cập dự án nào tại A | Sponsor/resource owner và IAM A |
| User đã sử dụng phiên nào trong ứng dụng A | Ứng dụng/session manager A |
| Quyền thực tế tại một ứng dụng đích | Chính ứng dụng và hệ thống IAM có tích hợp |

Không nên cho một attribute do B tự sửa quyết định mọi quyền tại A. Khi tín hiệu từ B thiếu hoặc đến muộn, ngày hết hạn và access review tại A trở thành lớp bảo vệ quan trọng.

## 7. Cấp quyền cho guest: RBAC, ABAC và tenant isolation

**Có bản ghi guest không có nghĩa là đã được cấp quyền.** Sau khi xác thực và liên kết danh tính, A vẫn phải quyết định guest được làm gì trên đúng tài nguyên được yêu cầu.

### 7.1. RBAC theo nhiệm vụ

**Role-Based Access Control (RBAC)** giúp gom các quyền đã được thiết kế thành vai trò:

| Role minh họa | Quyền chính | Giới hạn bắt buộc |
|---|---|---|
| guest_document_reader | Đọc tài liệu được chia sẻ | Project và tài liệu cụ thể |
| guest_project_commenter | Đọc và bình luận | Không đổi owner hoặc chia sẻ lại tùy ý |
| guest_support_viewer | Xem ticket được gán | Tenant và ticket thuộc hợp đồng |
| guest_auditor_readonly | Đọc bằng chứng phục vụ kiểm toán | Phạm vi thời gian và dữ liệu được duyệt |
| guest_project_editor | Chỉnh nội dung dự án | Resource owner phê duyệt, hạn truy cập |
| guest_privileged_support | Thao tác hỗ trợ nhạy cảm | Cấp tạm qua PAM/JIT khi cần |

Không nên tạo một role “guest” chung cho phép truy cập mọi hệ thống. Role mô tả khả năng hành động; **membership và grant** cần mô tả tổ chức, tenant, dự án, dữ liệu, thời gian và ngữ cảnh.

### 7.2. ABAC bổ sung điều kiện truy cập

**Attribute-Based Access Control (ABAC)** có thể xét trạng thái guest, tổ chức ngoài, sponsor, dự án, mức độ phân loại dữ liệu, môi trường, giờ làm việc hoặc điều kiện xác thực mạnh. Một chính sách đơn giản:

~~~text
authorize(guest, action, resource, context):
    if not context.authentication_valid: DENY
    if guest.status != "active": DENY

    partner = lookup_partner(guest.partner_id)
    if partner.status != "active": DENY

    membership = lookup_membership(guest.id, resource.tenant_id)
    if membership is missing or membership.status != "active": DENY
    if now >= membership.expires_at: DENY

    grant = lookup_grant(guest.id, resource.id)
    if grant is missing: DENY
    if now >= grant.expires_at: DENY
    if action not in grant.allowed_actions: DENY
    if resource.project_id != grant.project_id: DENY
    if resource.tenant_id != grant.tenant_id: DENY
    if not satisfies_data_policy(guest, resource, context): DENY

    ALLOW
~~~

Đây là mã giả để làm rõ chính sách, không phải cú pháp của một engine cụ thể. Trong thực tế cần xác định nguồn thuộc tính tin cậy, cách cập nhật trạng thái và xử lý cache/quyền khi hệ thống IAM không khả dụng.

### 7.3. Ngăn truy cập chéo tenant

Giả sử guest U của B có vai trò document_reader cho dự án P42. Nếu backend chỉ kiểm tra vai trò rồi chấp nhận ID tài liệu từ URL, U có thể đổi ID để xem tài liệu của C. Đây là lỗi kiểm tra quyền ở cấp đối tượng (object-level authorization).

Để tránh lỗi, **backend phải kiểm tra tài liệu thực sự thuộc tenant/dự án đã cấp quyền cho U**. Việc ẩn menu hoặc chỉ lọc danh sách trên frontend không bảo vệ được API. Các bộ lọc truy vấn dữ liệu cũng nên gắn với tenant context đáng tin cậy từ phiên và authorization result, không dùng trực tiếp tenant_id do người gọi tự khai.

### 7.4. Guest trong nhiều nhóm và nhiều dự án

Một guest có thể nằm trong nhiều nhóm tại A, hoặc dùng nhiều tài khoản liên kết. Nên xác định quyền có hiệu lực theo từng **membership và resource context**; không tự cộng dồn quyền giữa hai partner/tenant khác nhau. Khi gỡ guest khỏi P42, grant P42 phải hết hiệu lực dù người đó vẫn tham gia P51 hợp lệ.

Một nhóm hoặc lời mời có thể cấp quyền gián tiếp qua nhiều ứng dụng. Để tránh quyền còn sót, hệ thống cần biết **grant được cấp từ nguồn nào** và các resource nào đã nhận quyền đó. Đặc biệt nên thận trọng với nhóm lớn chứa quyền truy cập dữ liệu nhạy cảm.

## 8. Mover: thay đổi vai trò và quan hệ của guest

**Mover** xảy ra khi khách đổi dự án, được nâng quyền, đổi sponsor, chuyển tổ chức, đổi IdP hoặc thay đổi mục đích sử dụng dữ liệu. IAM phải so sánh quyền cũ với quyền mới và đánh giá lại toàn bộ điều kiện.

| Sự kiện Mover | Câu hỏi cần trả lời | Xử lý phù hợp |
|---|---|---|
 Guest chuyển từ P42 sang P51 | Quyền P42 có còn cần không? | Gỡ grant P42, duyệt và cấp P51 |
 Guest được bổ sung quyền editor | Chủ tài nguyên có chấp thuận nâng quyền không? | Phê duyệt quyền mới, có hạn và log |
 Sponsor A chuyển công tác | Ai chịu trách nhiệm về guest? | Bàn giao sponsor và rà soát quyền |
 Đối tác B đổi IdP | Guest có còn là đúng người đã mời không? | Account linking qua thủ tục xác minh |
 Email người dùng thay đổi | Subject gốc có ổn định không? | Cập nhật thuộc tính qua nguồn đáng tin |
 Hợp đồng thu hẹp phạm vi | Tài nguyên nào không còn được phép? | Thu hồi grant ngoài phạm vi mới |
 Guest từ tư vấn chuyển sang nhân viên nội bộ | Có thể chuyển loại tài khoản, quyền và lifecycle không? | Đánh giá riêng theo HR/IAM, không tự kế thừa quyền |
 Guest được thêm vào một nhóm mới | Nhóm có cấp quyền vượt mục đích mời ban đầu không? | Kiểm soát group mapping và resource scope |

### 8.1. Tránh tích lũy quyền

Ví dụ: U của B ban đầu là viewer P42, sau đó được chuyển sang editor P51. Nếu hệ thống chỉ thêm role P51, U vẫn có thể đọc P42. Đó là **residual access** hình thành từ Mover chưa hoàn tất. Quy trình đúng:

1. Xác định vai trò và grant hiện tại của U ở tất cả hệ thống liên quan.
2. Đánh giá nhiệm vụ mới và phê duyệt các quyền cần thiết ở P51.
3. Thu hồi grant P42 không còn hợp lệ, kể cả group và chia sẻ trực tiếp.
4. Áp dụng quyền P51 có hạn và kiểm tra phân quyền backend.
5. Ghi lại quyền trước/sau, lý do, sponsor và kết quả thực thi.

### 8.2. Đổi IdP hoặc đổi cách đăng nhập

Nếu U chuyển từ IdP B cũ sang IdP B mới, hệ thống có thể thấy một **issuer/subject khác**. Không tự gộp guest mới với guest cũ bằng email. Phải xác nhận thay đổi từ nguồn tin cậy, thẩm định liên kết danh tính, kiểm tra grant nào được tiếp tục và gỡ liên kết/nguồn xác thực cũ đúng kế hoạch.

Việc đổi phương thức xác thực không nên tạo cơ hội **account takeover** hoặc vô tình phục hồi quyền đã bị thu hồi trong quá khứ.

## 9. Leaver: vô hiệu hóa guest và thu hồi quyền thực tế

Leaver có thể đến từ nhân viên B nghỉ việc, hợp đồng hết hạn, dự án kết thúc, sponsor thu hồi lời mời, quyền đã quá hạn review hoặc sự cố bảo mật. Nhiều nguồn này nằm ngoài HR nội bộ của A, vì vậy cần **expiry, owner review và sự kiện từ đối tác** phối hợp.

### 9.1. Ba phạm vi thu hồi

| Phạm vi | Kết quả mong muốn |
|---|---|
 Thu hồi một membership của guest | Guest không vào được project/tenant đó nhưng vẫn giữ quyền hợp lệ khác |
 Thu hồi toàn bộ guest | Guest không còn được phép truy cập tài nguyên của A theo local account |
 Offboard toàn bộ partner/vendor | Tất cả guest, workload, nhóm, trust và grant phụ thuộc quan hệ đó bị xử lý |

Khi chỉ kết thúc một dự án, không nhất thiết xóa danh tính khách nếu họ vẫn có quyền hợp lệ trong dự án khác. Khi toàn bộ quan hệ chấm dứt, phải tìm mọi quyền phát sinh từ quan hệ đó.

### 9.2. Quy trình Leaver

1. **Xác minh tín hiệu:** nhận sự kiện từ sponsor, vendor/partner manager, hệ thống hợp đồng, IdP, SCIM, review hoặc incident response; xác nhận phạm vi và thời điểm hiệu lực.
2. **Chặn truy cập mới:** đặt guest, membership hoặc partner relationship vào trạng thái revoked/suspended để các quyết định cấp quyền mới bị từ chối.
3. **Gỡ grants và chia sẻ:** group, role, project membership, ACL ở ứng dụng, quyền xem tài liệu, chia sẻ trong SaaS và các ủy quyền liên quan.
4. **Vô hiệu hóa phiên:** kết thúc ứng dụng session và refresh token nơi được hỗ trợ; kiểm tra khả năng thu hồi hoặc hiệu lực còn lại của access token.
5. **Kiểm tra credential khác:** token/API key gắn người dùng, phiên PAM, credential phát sinh từ guest; tách tài khoản máy cần offboard riêng.
6. **Ngăn tái tạo quyền:** bảo đảm JIT/SCIM/invitation cũ không tự kích hoạt lại tài khoản đã bị thu hồi; giới hạn quyền phục hồi.
7. **Đối soát hệ thống đích:** xác nhận guest không còn quyền trong các tài nguyên liên quan; ghi lại hệ thống lỗi và biện pháp khắc phục.
8. **Lưu dữ liệu và bằng chứng đúng chính sách:** tài khoản có thể được vô hiệu hóa trước rồi xóa hoặc ẩn danh sau; không loại bỏ audit trail cần thiết.

### 9.3. Vì sao chỉ disable ở IdP chưa đủ?

Nếu IdP B khóa U, ứng dụng A vẫn có thể có **phiên đăng nhập riêng**, refresh token, access token ngắn hoặc dài hạn, group tại ứng dụng và quyền chia sẻ tài liệu trực tiếp. Đặc biệt, JWT đã phát hành có thể còn được API chấp nhận đến khi hết hạn nếu resource server không kiểm tra trạng thái hoặc không có cơ chế revocation.

Do đó cần phân biệt:

| Lớp trạng thái | Câu hỏi cần kiểm tra |
|---|---|
 Home IdP | B còn cho U xác thực mới không? |
 Guest principal tại A | A còn chấp nhận U là guest active không? |
 Membership và grants | U còn quyền trên project/object nào? |
 Phiên và token | Session/refresh token có bị thu hồi? Access token còn có hiệu lực bao lâu? |
 Downstream apps | SaaS, repository, API, file share có còn quyền riêng không? |

Không có một nút “disable guest” bảo đảm mọi thành phần bên ngoài tự động thay đổi trạng thái nếu không có tích hợp và kiểm thử tương ứng.

### 9.4. Xử lý xóa tài khoản

**Disable, revoke access và delete là các thao tác khác nhau.** Disable có thể chặn đăng nhập, nhưng vẫn cần gỡ grants. Delete có thể xóa bản ghi local song vẫn không tác động được tất cả API keys hoặc chia sẻ bên ngoài. Việc xóa cũng phải xét yêu cầu lưu lịch sử kiểm toán, dữ liệu cá nhân và thời hạn lưu trữ.

Sau khi guest đã offboard, yêu cầu mời lại phải có **quy trình phê duyệt mới**, đặc biệt không khôi phục tự động các grant cũ chỉ vì cùng địa chỉ email.

## 10. MFA, Conditional Access và bảo vệ phiên guest

Guest có thể đến từ thiết bị, mạng và IdP ngoài quyền quản trị của A. Chính sách truy cập nên dựa trên **rủi ro tài nguyên và mức đảm bảo xác thực**, không chỉ dựa vào việc tài khoản được đánh dấu guest.

### Các kiểm soát có thể áp dụng

- **MFA phù hợp:** đặc biệt đối với dữ liệu nhạy cảm và đặc quyền; ưu tiên phương thức chống phishing khi khả thi.
- **Federation trust được xác minh:** issuer, chữ ký, audience, token lifetime và thuộc tính xác thực phải được kiểm tra đúng giao thức.
- **Step-up authentication:** yêu cầu xác thực mạnh hơn khi truy cập tài nguyên nhạy cảm nếu hệ thống và IdP hỗ trợ.
- **Device posture:** kiểm tra tín hiệu tuân thủ thiết bị khi có nguồn đáng tin; không mặc định mọi thiết bị của bên ngoài đều được A quản lý.
- **Giới hạn phiên:** TTL, idle timeout, tái xác thực và khả năng kết thúc phiên theo rủi ro.
- **Giám sát bất thường:** đăng nhập từ nguồn lạ, thay đổi thiết bị, số lần từ chối quyền tăng đột biến hoặc thao tác dữ liệu bất thường.
- **Least privilege và deny by default:** thiếu trạng thái guest/membership tin cậy thì từ chối theo chính sách.

Trong một số cấu hình B2B, tổ chức A có thể chọn tin cậy một số tuyên bố MFA của IdP đối tác. Đây phải là **quyết định trust có kiểm soát**, có thỏa thuận ý nghĩa claim và cách vận hành, thay vì tin mọi chuỗi tên nhóm hoặc thông tin do phía ngoài tự khai.

### Thời hạn phiên và thời hạn quyền khác nhau

Ví dụ: guest U được duyệt quyền đến hết ngày 31/12, nhưng một phiên đăng nhập có TTL 8 giờ. Nếu sponsor thu hồi quyền ngay ngày 20/12, **phiên còn hạn không phải lý do tiếp tục cho truy cập**. Backend cần đánh giá status/grant hiện hành theo thiết kế phù hợp; session cần có cách vô hiệu hóa khi quyền bị thu hồi.

Tương tự, việc lời mời có hiệu lực 48 giờ không có nghĩa quyền sau khi chấp nhận chỉ tồn tại 48 giờ. Phân biệt **invitation validity**, **account validity**, **grant validity**, **session lifetime** và **access-token lifetime**.

## 11. Access review và xử lý guest mồ côi

Với guest, **access review** đặc biệt quan trọng vì không có hệ thống HR nội bộ nào chắc chắn nắm toàn bộ thay đổi nhân sự bên ngoài.

Reviewer phía A nên trả lời:

1. Người này còn thuộc tổ chức/dự án được phê duyệt không?
2. Sponsor còn làm việc tại A và chịu trách nhiệm hợp lệ không?
3. Guest còn nhu cầu xem tài nguyên cụ thể nào, role có quá rộng không?
4. Hợp đồng, dự án và mục đích chia sẻ dữ liệu còn hiệu lực không?
5. Có guest không sử dụng lâu ngày, hết hạn hoặc chưa chấp nhận invitation không?
6. Có quyền đặc biệt, group chia sẻ, app permission hoặc quyền downstream chưa được đối soát không?
7. Có token, service account hoặc robot từng được vận hành bằng tài khoản guest cá nhân không?

### Khi sponsor rời tổ chức

Nếu sponsor của guest nghỉ việc, IAM không nên để bản ghi guest không có chủ sở hữu vô hạn. Có thể thực hiện:

1. Chuyển ownership tới người phụ trách mới đã được xác nhận;
2. Yêu cầu sponsor mới tái xác nhận nhu cầu và phạm vi quyền;
3. Tạm đình chỉ những quyền nhạy cảm hoặc quyền không được tái duyệt đúng hạn;
4. Thu hồi khi không còn người chịu trách nhiệm hoặc mục đích truy cập.

Tần suất review dựa trên rủi ro. Một guest được cấp quyền bảo trì production cần kiểm soát chặt hơn người chỉ được xem tài liệu công khai trong một đợt cộng tác ngắn. Ngoài review định kỳ, Mover và sự cố bảo mật cần kích hoạt review theo chính sách.

### Guest không hoạt động chưa chắc vô hại

Tài khoản không đăng nhập sáu tháng có thể vẫn giữ group, token hoặc các chia sẻ nhạy cảm. **Last sign-in** chỉ là một tín hiệu; các quyết định thu hồi còn phải dựa trên hợp đồng, owner, permission, ứng dụng đích và khả năng truy cập hiện hữu.

## 12. Audit và reconciliation: chứng minh quyền đã được xử lý

Audit của guest account phải ghi cả **vòng đời tài khoản** và **vòng đời quyền**. Chỉ có log đăng nhập không trả lời được vì sao một người ngoài có quyền hoặc quyền đã được thu hồi hoàn toàn chưa.

| Nhóm sự kiện | Dữ liệu cần có |
|---|---|
 Yêu cầu và phê duyệt mời | Invitation ID, requester, sponsor, resource owner, lý do, scope, expiry |
 Chấp nhận lời mời | Guest ID, nguồn xác thực, subject được liên kết, kết quả, thời điểm |
 Tạo/sửa guest | Trạng thái trước–sau, nguồn thao tác, correlation ID |
 Cấp/đổi/gỡ grant | Group/role, tenant, project, resource, người duyệt, thời điểm |
 Truy cập ứng dụng | Principal, resource, hành động, allow/deny, nguồn truy cập cần thiết |
 Review | Reviewer, quyết định giữ/gỡ quyền, bằng chứng, thời hạn review mới |
 Leaver | Sự kiện đầu vào, hệ thống đích, trạng thái revocation, lỗi còn mở |
 Federation/SCIM change | Issuer, nguồn provisioning, key/config thay đổi, người duyệt |

Ví dụ log minh họa cho một lần thu hồi:

~~~json
{
  "event_type": "guest.grant.revoked",
  "timestamp": "2026-11-23T08:00:00Z",
  "guest_id": "G-1084",
  "partner_id": "partner-B",
  "resource": "project-P42",
  "role": "document_reader",
  "reason": "project_finished",
  "requested_by": "sponsor-A-17",
  "result": "applied",
  "correlation_id": "revocation-82f3"
}
~~~

Log nên dùng định danh nội bộ hoặc tham chiếu phù hợp, giới hạn dữ liệu cá nhân cần lưu, kiểm soát quyền xem, bảo đảm tính toàn vẹn và thực hiện retention theo chính sách. **Không lưu mật khẩu, private key, session cookie hoặc access token còn dùng được trong audit log.**

### 12.1. Desired state và actual state

**Desired state**: Theo hợp đồng, sponsor và grants đã duyệt, guest U chỉ còn quyền xem P51. **Actual state**: Một ứng dụng tài liệu vẫn lưu quyền đọc P42 được cấp trực tiếp trước đó. Nếu chỉ kiểm tra IAM, tổ chức có thể kết luận sai rằng thu hồi đã hoàn tất.

Một quy trình đối soát:

~~~text
for each guest in external_identity_registry:
    desired = calculate_approved_access(
        guest.status, guest.memberships,
        valid_contracts, approved_grants
    )
    actual = discover_access_from_target_systems(guest.id)
    differences = compare(desired, actual)

    if differences:
        notify_owner(guest.sponsor_id, differences)
        remediate(differences)
        verify_revocation_or_approved_exception()
~~~

Đây là mã giả, vì không phải ứng dụng nào cũng cung cấp API quản lý quyền. Với hệ thống không thể xuất quyền tự động, phải có cách kiểm tra khác phù hợp và nêu rõ phạm vi chưa được kiểm chứng.

### 12.2. Các chỉ số nên theo dõi

- **Guest quá hạn nhưng còn active:** phát hiện quyền chưa bị đóng theo thời gian.
- **Guest không có sponsor hợp lệ:** phát hiện account mồ côi.
- **Invitation pending quá hạn:** lời mời không được dùng nhưng chưa được vô hiệu hóa.
- **Grant không được review đúng lịch:** giảm nguy cơ đặc quyền tích lũy.
- **Thời gian thu hồi quyền:** từ lúc nhận Leaver tới khi hệ thống đích xác nhận revoke.
- **Lỗi SCIM/JIT và chênh lệch quyền downstream:** đánh giá độ tin cậy của tự động hóa.
- **Guest có quyền nhạy cảm/đặc quyền:** đo nhóm rủi ro cần kiểm soát chặt.

Không có ngưỡng thời gian chung đúng cho mọi guest. Hệ thống cần đặt SLA và tần suất review theo độ nhạy dữ liệu, mức độ đặc quyền, hợp đồng và yêu cầu vận hành.

## 13. Những trường hợp đặc biệt

### 13.1. Một người có nhiều guest record

Cùng một người có thể được mời vào hai tenant, hai dự án hoặc qua hai phương thức xác thực. Không phải mọi bản ghi trùng email đều là bản ghi trùng danh tính. Cần xác minh issuer/subject, nguồn tạo, sponsor và quan hệ dự án trước khi hợp nhất. Nếu hợp nhất không đúng, người dùng có thể vô tình nhận **tổng quyền** từ hai tài khoản khác nhau.

### 13.2. Guest được chia sẻ tài liệu trực tiếp

Ngoài group/role chính thức, một hệ thống có thể cho người dùng chia sẻ riêng tài liệu với guest. Khi Leaver, phải đối soát cả **direct share**, ACL, external links và nhóm riêng của ứng dụng. Chỉ gỡ group IAM có thể không xóa những quyền được cấp trực tiếp.

### 13.3. Khách làm việc cho nhiều đối tác

Một chuyên gia tư vấn có thể cùng lúc làm việc cho B và C. Hệ thống phải biểu diễn rõ guest đang hành động trong ngữ cảnh nào, thuộc partner và tenant nào, đã có sponsor nào phê duyệt. Không tự chuyển quyền của B sang C chỉ vì principal là cùng người.

### 13.4. Guest cần quyền đặc biệt tạm thời

Một kỹ sư bên ngoài cần bảo trì production theo ticket. Nên xem xét **Privileged Access Management (PAM)** hoặc **Just-in-Time elevation** theo phiên: xác thực mạnh, phê duyệt có thời hạn, scope cụ thể và ghi dấu vết. Guest vẫn có thể giữ quyền xem ticket bình thường sau khi đặc quyền production hết hạn.

### 13.5. Mất quyền đăng nhập ở IdP ngoài

Nếu IdP B tạm ngừng dịch vụ, không nên “chữa cháy” bằng cách tự gắn một tài khoản email chưa xác minh vào guest có quyền nhạy cảm. Phương án khôi phục phải có quy trình thẩm định, ràng buộc danh tính, giới hạn quyền và audit. Khi không thể xác minh yêu cầu truy cập nhạy cảm, policy nên từ chối theo nguyên tắc an toàn.

### 13.6. Chuyển từ guest thành nhân viên nội bộ

Khi một người ngoài được tuyển làm nhân viên, tổ chức cần áp dụng luồng Joiner của HR, xác minh nguồn danh tính mới và đánh giá quyền theo vai trò nội bộ. Việc chỉ đổi nhãn guest sang member có thể giữ lại quyền dự án cũ trái nguyên tắc tối thiểu. Nếu nền tảng hỗ trợ chuyển đổi, cần có mapping và thu hồi/cấp lại quyền có kiểm soát.

### 13.7. Dùng guest như service account

Đôi khi một nhóm dùng tài khoản guest của người B để chạy script, cron job hoặc kết nối API. Đây là mô hình dễ lỗi: mật khẩu/MFA gắn với con người, quyền khó kiểm toán, khi người B nghỉ việc job sẽ hỏng hoặc bị giữ lại vô thời hạn.

Nên chuyển tác vụ máy sang **workload identity/service account riêng** với owner, credential quản lý trong secret manager, scope tối thiểu, rotation và vòng đời gắn với ứng dụng/hợp đồng. Con người vẫn giữ guest riêng cho tương tác.

## 14. Kịch bản thực tế: cộng tác với chuyên gia kiểm toán

Công ty A mời hai chuyên gia từ công ty B kiểm tra hồ sơ của dự án P42 trong 45 ngày. A có cổng tài liệu, dashboard trạng thái và một ứng dụng theo dõi ticket.

| Ngày | Diễn biến | Hành động IAM phù hợp |
|---|---|---|
 1 | Sponsor A cần hai người xem hồ sơ P42 | Xác minh quan hệ B, lập yêu cầu, duyệt tài nguyên, scope và hạn 45 ngày |
 2 | Hai invitation được gửi | Mời có hạn, liên kết với dự án và danh tính dự kiến |
 3 | Người U chấp nhận lời mời | Xác thực qua IdP B, kiểm tra định danh và tạo guest record G-1084 |
 3 | Người V chưa phản hồi | Giữ trạng thái pending, chưa cấp quyền tài nguyên |
 10 | U cần bổ sung quyền xem dashboard P42 | Resource owner duyệt grant đúng dự án và ghi audit |
 20 | B thông báo V không còn tham gia | Thu hồi invitation pending, không để lời mời cũ có thể kích hoạt quyền |
 25 | U được chuyển sang dự án P51 | Gỡ quyền P42 không còn cần, duyệt P51 mới |
 35 | Sponsor A đổi vị trí | Bàn giao guest ownership, review vai trò và hạn truy cập |
 45 | Hợp đồng kiểm toán kết thúc | Thu hồi tất cả grants thuộc quan hệ đó, xử lý phiên và đối soát |

### Kiểm thử sau khi chấp nhận lời mời

**Tình huống hợp lệ:** U đã được duyệt, có guest active, ID token xác minh hợp lệ, grant document_reader của P42 còn thời hạn, tài liệu thuộc P42. Resource server cho phép đọc.

**Tình huống sai tenant:** U thay ID tài liệu sang P99 thuộc đối tác C. Dù đăng nhập SSO hợp lệ và có role document_reader, API từ chối do resource không thuộc grant.

**Tình huống Mover:** Sau khi U chuyển sang P51, một URL tài liệu P42 cũ vẫn còn trong email. Backend tiếp tục từ chối P42 vì grant đã bị gỡ, kể cả nếu URL cũ vẫn mở được giao diện.

**Tình huống Leaver chưa hoàn tất:** A vô hiệu hóa guest G-1084 nhưng trong một ứng dụng SaaS, U vẫn nằm trong ACL chia sẻ trực tiếp. Đợt reconciliation phát hiện ACL và yêu cầu app owner xử lý, xác minh lại.

### Điều có thể học từ kịch bản

Sự tồn tại của invitation, guest record, quyền trên ứng dụng và phiên truy cập là các trạng thái khác nhau. Một quy trình có chất lượng cần nối chúng thành **chuỗi chứng cứ từ nhu cầu kinh doanh đến việc thu hồi quyền thực tế**.

## 15. Những sai lầm phổ biến và cách phòng tránh

| Sai lầm | Rủi ro | Cách xử lý |
|---|---|---|
 Mời bằng email rồi tự cấp toàn quyền | Bất kỳ người nhận lời mời có thể có quyền quá rộng | Xác minh danh tính, sponsor, approval và least privilege |
 Dùng email làm identity key | Đổi/reuse email khiến ghép sai người | Stable external subject + issuer |
 Không đặt hạn cho guest | Tài khoản mồ côi sau hợp đồng | Expiry, auto-review và recertification |
 Giữ invitation không bao giờ hết hạn | Đường dẫn mời cũ có thể bị lạm dụng | Hạn mời, cơ chế vô hiệu hóa, binding phù hợp |
 Cho mọi user cùng domain tự nhận quyền | Người ngoài dự án nhận quyền trái phép | Invitation/grant theo cá nhân và scope |
 Tin role/group từ IdP B không kiểm soát | Đối tác có thể tự nâng quyền tại A | Mapping do resource owner/IAM A quản lý |
 Role viewer không gắn tenant/object | Đọc chéo dữ liệu | Authorization tại backend theo resource |
 Quên cập nhật sponsor | Không ai chịu trách nhiệm review | Ownership transfer và tạm khóa khi cần |
 Chỉ disable home IdP | Session và grants tại A còn hoạt động | Session revocation và deprovision downstream |
 Xóa guest record trước khi thu hồi ACL | Mất liên kết để tìm quyền còn sót | Thu hồi, kiểm chứng và lưu dấu vết trước xử lý xóa |
 Dùng guest chung cho nhiều người | Không truy vết từng người | Account cá nhân, MFA, audit theo principal |
 Dùng guest của người cho API tự động | Credential và quyền máy không có lifecycle đúng | Workload/service identity riêng |
 Khôi phục guest cũ theo email | Hồi sinh quyền đã thu hồi | Onboarding và approval mới |

## 16. Khắc phục sự cố guest account

Khi người dùng báo không truy cập được, cần xác định lỗi xảy ra ở **invitation, authentication, identity linking, provisioning, authorization** hay **session**.

| Triệu chứng | Nguyên nhân có thể | Kiểm tra |
|---|---|---|
 Không nhận được lời mời | Sai địa chỉ liên hệ, mail bị chặn, invitation chưa phát | Yêu cầu mời và trạng thái giao nhận |
 Lời mời báo hết hạn | Redemption quá muộn hoặc lời mời đã bị hủy | Validity, sponsor và yêu cầu mời lại |
 Chấp nhận lời mời nhưng tạo guest khác | Đổi issuer/subject hoặc sai account khi đăng nhập | Account linking và nguồn xác thực |
 Đăng nhập bị từ chối | Sai issuer/audience/chữ ký hoặc điều kiện MFA | Federation trust và security policy |
 Đăng nhập thành công nhưng không thấy ứng dụng | Chưa có membership/grant hoặc guest đang pending | Local principal, approval, role và scope |
 Vào được ứng dụng nhưng không đọc được tài liệu | Tài liệu ngoài tenant/project hoặc grant hết hạn | Resource ownership, role, expiry |
 Guest đã bị khóa nhưng còn phiên hoạt động | Session chưa bị hủy hoặc token chưa hết hạn | Session manager và resource-server validation |
 User đã nghỉ việc vẫn còn trong nhóm | SCIM/deprovision lỗi hoặc quyền tạo thủ công | Sync log, group mapping và reconciliation |
 Guest không còn sponsor | Sponsor rời công ty hoặc owner không được bàn giao | Ownership transfer và access review |
 Khách bị mời lại nhưng có quyền cũ | Quy trình restore tự mang grant cũ | Revocation history, reapproval và grant migration |

**Không nên bỏ qua kiểm tra chữ ký/token hoặc cấp admin tạm thời chỉ để sửa lỗi đăng nhập.** Khi thiếu bằng chứng xác thực hoặc quyền, cần xác minh cấu hình và đưa hệ thống về trạng thái đáp ứng chính sách.

## 17. Checklist triển khai guest lifecycle

### Identity và invitation

- [ ] Guest có ID ổn định, nguồn danh tính đã xác minh và owner/sponsor rõ ràng.
- [ ] Invitation có request, mục đích, scope, người duyệt và thời hạn.
- [ ] Redemption ràng buộc người nhận với external subject đáng tin; có khả năng vô hiệu hóa lời mời.
- [ ] IdP/SSO OIDC hoặc SAML được cấu hình và kiểm tra issuer, audience, chữ ký và các điều kiện giao thức.
- [ ] Guest tạo qua JIT/SCIM không tự cấp quyền rộng khi chưa có approval.

### Authorization và vận hành

- [ ] Role, group và grants được giới hạn theo tenant, dự án, tài nguyên, hành động và thời gian.
- [ ] Backend thực thi RBAC/ABAC với object ownership; deny by default khi thiếu điều kiện.
- [ ] Có MFA/điều kiện truy cập phù hợp rủi ro và quản lý phiên ứng dụng.
- [ ] Có quy trình Mover gỡ quyền cũ, cấp quyền mới có phê duyệt.
- [ ] Có quy trình bàn giao sponsor, xử lý guest inactive và access review.
- [ ] Guest có quyền đặc biệt chỉ được cấp theo nhiệm vụ và thời hạn, cân nhắc PAM/JIT.

### Leaver và kiểm chứng

- [ ] Leaver có nguồn sự kiện tin cậy và SLA theo độ nhạy.
- [ ] Thu hồi guest/membership/grant, session/token khi hỗ trợ và quyền downstream.
- [ ] SCIM/JIT/invitation không vô tình kích hoạt lại quyền sau thu hồi.
- [ ] Service account và workload liên quan được quản lý riêng có owner.
- [ ] Audit log và reconciliation chứng minh quyền thực tế đã được xử lý.
- [ ] Retention và xử lý dữ liệu cá nhân sau offboarding theo chính sách.

## 18. Tự kiểm tra kiến thức

**Câu 1.** Một người đã chấp nhận invitation, guest record ở trạng thái active. Người ấy có tự động quyền xem toàn bộ dữ liệu dự án không?

**Đáp án:** Không. Guest active chỉ thể hiện trạng thái danh tính; quyền còn phụ thuộc grant, membership, tenant/project scope, hạn và policy ở resource server.

**Câu 2.** Vì sao invitation có hạn và quyền truy cập có hạn phải được quản lý riêng?

**Đáp án:** Hạn invitation kiểm soát thời gian người nhận được phép hoàn tất bước mời; hạn grant kiểm soát thời gian người đó được phép dùng tài nguyên sau khi chấp nhận.

**Câu 3.** IdP B khóa user U, nhưng U vẫn dùng được ứng dụng A qua tab trình duyệt đã mở. Điều gì cần kiểm tra?

**Đáp án:** Phiên và token do A/ứng dụng liên quan cấp, trạng thái guest và grants tại A, khả năng resource server kiểm tra revoke, cùng quyền trực tiếp ở ứng dụng đích.

**Câu 4.** Guest U chuyển từ P42 sang P51. Chỉ thêm group P51 có đủ không?

**Đáp án:** Không. Cần đánh giá và thu hồi quyền P42 không còn phù hợp, duyệt P51, áp dụng chính sách mới và kiểm chứng tại backend.

**Câu 5.** Email cũ của người B được cấp lại cho một người khác. IAM có nên gắn người mới vào guest cũ không?

**Đáp án:** Không tự động. Email không phải định danh bất biến; cần xác minh external subject, issuer và thực hiện onboarding/linking có kiểm soát.

**Câu 6.** Guest thuộc role viewer nhưng cố xem tài liệu tenant C. Vì sao phải kiểm tra quyền ở API?

**Đáp án:** Role viewer không chỉ rõ tài nguyên thuộc tenant nào. API phải kiểm tra object ownership và grant của đúng membership, kể cả khi giao diện đã ẩn link.

**Câu 7.** SCIM đã đặt user inactive, vậy access review có còn cần?

**Đáp án:** Có. SCIM có thể đồng bộ thiếu, thất bại hoặc không chạm tới session và quyền tại ứng dụng khác; access review và reconciliation phát hiện các quyền không còn lý do tồn tại.

**Câu 8.** Có nên sử dụng guest account của kỹ sư để chạy tác vụ API định kỳ?

**Đáp án:** Không nên. Tác vụ máy cần workload/service identity có owner, credential và phạm vi riêng, gắn vòng đời với tích hợp và hợp đồng.

## Kết luận

**Guest account** là cầu nối giữa **danh tính bên ngoài** và **quyền truy cập tại hệ thống sở hữu tài nguyên**. Quản lý hiệu quả đòi hỏi xác minh nguồn định danh, lời mời có trách nhiệm, liên kết principal ổn định, cấp quyền **RBAC/ABAC** theo đúng tenant/tài nguyên và thời hạn, đồng thời phối hợp **IdP, SSO, SCIM, MFA, audit và access review**. Khi áp dụng đầy đủ mô hình **Joiner–Mover–Leaver**, tổ chức kiểm soát được ai đang được mời, ai thực sự có quyền, quyền nào cần thay đổi và quyền nào phải thu hồi có kiểm chứng để giảm truy cập tồn dư.
