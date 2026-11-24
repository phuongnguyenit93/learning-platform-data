# Tạo account tự động trong Account provisioning

**Tạo account tự động (automated account provisioning)** là quá trình hệ thống IAM tiếp nhận một sự kiện hoặc yêu cầu hợp lệ, xác định chủ thể cần được cấp tài khoản, kiểm tra điều kiện, tạo hồ sơ tài khoản trên các hệ thống đích và ghi nhận kết quả mà không cần quản trị viên thao tác thủ công từng ứng dụng. Quy trình có thể đồng thời gán quyền cơ sở, đăng ký tài khoản vào Identity Provider (**IdP**) và đồng bộ dữ liệu đến ứng dụng qua giao thức **SCIM** hoặc API riêng.

Bài thuộc chương **Account provisioning** của module **SECURITY_IDENTITY_ACCESS_MANAGEMENT_IDENTITY_LIFECYCLE**. Trong bức tranh quản lý vòng đời danh tính **Joiner–Mover–Leaver (JML)**, tạo account tự động giúp nhân viên mới có quyền đúng lúc; khi chuyển vai trò, tài khoản hiện có được cập nhật đúng phạm vi; khi rời tổ chức, quyền và tài khoản phải được thu hồi. Chủ đề liên hệ **identity proofing**, IdP/SSO, SCIM, **RBAC/ABAC**, tài khoản dịch vụ, kiểm toán và giảm **quyền truy cập tồn dư**.

**Ví dụ xuyên suốt:** Hệ thống nhân sự ghi nhận Lan được tuyển vào bộ phận Tài chính, bắt đầu làm việc ngày 1/12. IAM nhận sự kiện Joiner, tạo định danh nội bộ, chuẩn bị tài khoản IdP, đồng bộ account tới ứng dụng tài chính, gán role đọc hóa đơn theo phê duyệt và chỉ kích hoạt đăng nhập/quyền tại thời điểm hợp lệ. Nếu hệ thống đích lỗi, IAM phải theo dõi và đối soát; không thể báo “đã hoàn tất onboarding” chỉ vì lệnh tạo đầu tiên thành công.

## 1. Phân biệt tạo account, đăng ký danh tính và cấp quyền

Các thuật ngữ trong provisioning thường bị dùng thay thế nhau, nhưng có mục tiêu khác nhau:

| Công việc | Câu hỏi cần giải quyết | Ví dụ đầu ra |
| --- | --- | --- |
| **Identity proofing** | Người này có thực sự gắn với danh tính khai báo không? | Kết quả kiểm tra hồ sơ HR/người đăng ký. |
| **Identity registration** | Danh tính nào là hồ sơ chuẩn trong IAM? | Một \`subjectId\` ổn định, liên kết hồ sơ HR. |
| **Account creation** | Có tài khoản ở IdP/ứng dụng đích chưa? | User record có ID riêng của ứng dụng. |
| **Authentication enrollment** | Người dùng đã đăng ký phương thức xác thực phù hợp chưa? | Passkey, khóa bảo mật hoặc phương thức MFA hợp lệ. |
| **Entitlement provisioning** | Cần cấp nhóm, role, scope, ACL nào? | Role \`FINANCE_INVOICE_READER\` được phê duyệt. |
| **Account activation** | Khi nào tài khoản được phép đăng nhập/sử dụng? | Chuyển trạng thái active theo ngày hiệu lực. |
| **Authorization** | Một yêu cầu cụ thể được phép thao tác với tài nguyên nào? | API cho đọc hóa đơn của tenant được phân quyền. |

**Tạo thành công không đồng nghĩa được phép truy cập.** Có thể tạo account ở trạng thái chưa hoạt động để chuẩn bị cho ngày bắt đầu; có thể có account nhưng chưa đăng ký MFA; và có thể đăng nhập thành công nhưng không có quyền gọi API nhạy cảm. Hệ thống cần lưu các trạng thái này riêng để tránh cấp quyền quá sớm.

Ngược lại, việc cấp role trong một bảng IAM cũng chưa chứng minh hệ thống đích đã tạo tài khoản hoặc chấp nhận role đó. Provisioning cần có **bằng chứng từ hệ thống đích**.

## 2. Các tác nhân trong kiến trúc tạo account tự động

~~~mermaid
flowchart TD
    HR["HRIS / nguồn nhân sự có thẩm quyền"] --> EVENT["Joiner / Mover / Leaver event"]
    SP["Sponsor / nguồn hợp đồng"] --> EVENT
    EVENT --> IAM["IAM/IGA: xác minh, chính sách, phê duyệt"]
    IAM --> REG["Identity registry: subject ID ổn định"]
    IAM --> ORCH["Provisioning orchestrator"]
    ORCH --> IDP["IdP: account, groups, MFA/SSO"]
    ORCH --> SCIM["SCIM connector"]
    ORCH --> API["API/connector riêng"]
    SCIM --> SAAS["SaaS / ứng dụng đích"]
    API --> LEGACY["Hệ thống nội bộ / legacy"]
    IDP --> LOGIN["SSO: OIDC / SAML"]
    LOGIN --> APP["Ứng dụng và API"]
    SAAS --> CHECK["Readback / reconciliation"]
    LEGACY --> CHECK
    IDP --> CHECK
    CHECK --> IAM
    IAM --> AUDIT["Audit / alert / review"]
~~~

Các thành phần có trách nhiệm khác nhau:

- **HRIS/nguồn có thẩm quyền** xác định sự tồn tại, loại quan hệ, trạng thái, ngày hiệu lực, bộ phận và các thuộc tính nhân sự. Với nhà thầu, nguồn có thể là hệ thống hợp đồng và người bảo trợ.
- **IAM/IGA (Identity Governance and Administration)** xác định liệu yêu cầu hợp lệ, cần phê duyệt gì, entitlement nào được phép và khi nào quyền phải kết thúc.
- **Identity registry** quản lý định danh ổn định của chủ thể, liên kết nhiều tài khoản ứng dụng và phòng tránh tạo trùng.
- **IdP** quản lý tài khoản và xác thực cho SSO. IdP có thể là nguồn quản lý một số nhóm/role, nhưng không nhất thiết là nơi duy nhất lưu quyền.
- **Provisioning orchestrator/connector** biến trạng thái mong muốn thành lệnh tới từng hệ thống, xử lý lỗi, retry, thứ tự phụ thuộc và lưu mapping giữa ID nội bộ với ID của hệ thống đích.
- **SCIM 2.0** cung cấp mô hình/API chuẩn để quản lý đối tượng như \`Users\` và \`Groups\`; **SCIM không phải giao thức đăng nhập hoặc kiểm tra MFA**.
- **Ứng dụng/API đích** thực thi authorization trên hành động và tài nguyên. Quyền thực tế có thể phát sinh từ role nội bộ, ACL hoặc thuộc tính ngoài IdP.

Không phải hệ thống nào cũng hỗ trợ SCIM. Một kiến trúc IAM thực tế cần có **adapter** cho API riêng, LDAP/AD, hệ thống cloud và ứng dụng legacy, với khả năng đọc lại trạng thái tương ứng.

## 3. Trước khi tạo: xác định nguồn sự thật và khóa định danh

Điểm khởi đầu không phải lệnh \`POST /Users\`, mà là câu hỏi **ai được phép yêu cầu tạo account và dữ liệu nào đáng tin**.

Ví dụ các nguồn:

| Thuộc tính | Nguồn thường được giao quyền quyết định | Rủi ro khi dùng sai nguồn |
| --- | --- | --- |
| Quan hệ lao động, ngày bắt đầu/kết thúc | HRIS hoặc workflow hợp đồng đã phê duyệt. | Tạo quyền cho người chưa bắt đầu hoặc đã nghỉ. |
| ID nhân sự/định danh nội bộ | Identity registry gắn với nguồn nhân sự. | Một người có nhiều account hoặc hai người bị gộp nhầm. |
| Bộ phận, vị trí, manager | HRIS/nguồn tổ chức chính thức. | Role được gán theo thông tin người dùng tự khai. |
| Tenant, dự án, phạm vi dữ liệu | Hệ thống nghiệp vụ/chủ sở hữu tài nguyên. | Truy cập chéo tenant hoặc dữ liệu ngoài nhiệm vụ. |
| Role/entitlement | IAM/IGA dựa trên chính sách và phê duyệt. | Tự động cấp quyền admin chỉ từ tên chức danh. |
| User ID của ứng dụng đích | Chính hệ thống đích khi tạo/link tài khoản. | Gửi update/revoke nhầm người do giả định ID trùng nhau. |

**Không dùng email làm khóa định danh duy nhất.** Email có thể đổi khi nhân viên đổi họ tên, domain, bộ phận, hoặc có thể được tái sử dụng sau một thời gian. Nên có \`subjectId\` ổn định cho toàn bộ vòng đời và bảng ánh xạ tới ID đích.

Ví dụ:

~~~text
Canonical IAM subject: person-4821
HR employee ref:      hr-92811
IdP user ID:          idp-u-38710
CRM SCIM User.id:     4dc0b44f-8ad3-42d0-aa7f-c3796c67c801
Finance app user ID:  fin-u-45091
Email at present:     lan@company.example
~~~

Một \`externalId\` trong SCIM có thể dùng làm tham chiếu do client quản lý. Tuy vậy, **không mặc định mọi SCIM server đều bảo đảm tính duy nhất hay hỗ trợ lọc theo \`externalId\` như mong muốn**; connector phải kiểm tra khả năng hệ thống đích và lưu \`User.id\` trả về.

### Không tự động gộp account theo tên

Hai nhân viên có thể trùng họ tên, còn một người có thể đổi email. Nếu tìm thấy nhiều kết quả tương tự, cần chuyển trường hợp sang **identity resolution/manual review** theo chính sách. Việc tạo account và liên kết sai chủ thể có thể khiến một người nhận quyền hoặc dữ liệu của người khác.

## 4. Điều kiện kích hoạt tự động: đúng người, đúng thời điểm

Một hệ thống tự động phải kiểm tra **eligibility** trước mỗi thao tác có tác động đến quyền.

Ví dụ điều kiện cấp quyền nền cho nhân viên:

~~~text
eligibleForBaselineAccess =
    trustedIdentitySource
    AND proofingRequirementSatisfied
    AND employmentStatus == ACTIVE
    AND effectiveDateReached
    AND onboardingApproval == APPROVED
    AND accountNotSuspended
~~~

Mô hình trên là biểu thức nghiệp vụ minh họa; tổ chức có thể tạo **pre-hire account** trước ngày làm việc ở trạng thái disabled để chuẩn bị thiết bị và đăng ký MFA có kiểm soát. Nếu làm như vậy, tài khoản chỉ được kích hoạt và cấp quyền nghiệp vụ khi đáp ứng chính sách.

Tách hai mốc:

1. **Provisioning time:** lúc tạo bản ghi tài khoản để chuẩn bị hạ tầng.
2. **Access effective time:** lúc tài khoản và các entitlement được phép sử dụng.

Không dùng một cờ \`created=true\` để suy ra \`active=true\`. Nếu ngày hiệu lực bị dời hoặc hồ sơ bị hủy tuyển dụng, quy trình cần hủy/thu hồi những gì đã chuẩn bị và không để account mồ côi.

### Trạng thái yêu cầu cần quản lý

| Trạng thái | Ý nghĩa | Được mở quyền chưa? |
| --- | --- | --- |
| \`REQUESTED\` | Nhận yêu cầu từ nguồn nghiệp vụ. | Chưa. |
| \`VALIDATED\` | Nguồn, danh tính, dữ liệu và ngày hiệu lực hợp lệ. | Chưa tự động. |
| \`APPROVED\` | Các phê duyệt theo chính sách đã đầy đủ. | Theo ngày hiệu lực/điều kiện khác. |
| \`PROVISIONING\` | Đang tạo/link account và nhóm tại các hệ thống. | Không mặc nhiên. |
| \`PROVISIONED_INACTIVE\` | Account đã có nhưng chưa được phép đăng nhập. | Chưa. |
| \`ACTIVE\` | Account đủ điều kiện hoạt động theo chính sách. | Chỉ những quyền đã được cấp và xác minh. |
| \`PARTIAL_FAILURE\` | Một hoặc nhiều hệ thống đích lỗi hoặc chưa xác nhận. | Chỉ phần đã được phép; không báo hoàn tất. |
| \`BLOCKED_FOR_REVIEW\` | Trùng danh tính, thiếu phê duyệt hoặc có xung đột. | Không cấp quyền phụ thuộc điều kiện chưa đạt. |

Tên state là ví dụ thiết kế workflow, không phải cấu trúc bắt buộc của một sản phẩm IAM.

## 5. Luồng tạo account tự động cho Joiner

Một luồng chuẩn có thể đi theo thứ tự sau:

1. **Nhận sự kiện Joiner** từ HRIS hoặc nguồn hợp đồng được xác thực; kiểm tra \`eventId\`, \`subjectId\`, revision và \`effectiveAt\`.
2. **Phân giải danh tính:** tìm subject đã tồn tại trong registry; chống tạo trùng hoặc nối nhầm tài khoản.
3. **Kiểm tra proofing và eligibility:** xác minh người được gắn đúng với hồ sơ, trạng thái quan hệ và yêu cầu phê duyệt.
4. **Lập trạng thái mong muốn (desired state):** account nào cần tồn tại, thuộc tính nào cần đồng bộ, role/group nào được phép, ngày kích hoạt và quyền tạm thời nếu có.
5. **Tạo/link IdP account:** lưu ID đích; đăng ký phương thức xác thực theo workflow bảo vệ, ví dụ passkey/MFA.
6. **Tạo/link account ứng dụng:** dùng SCIM/API hoặc cơ chế khác; chỉ phát lệnh tới những đích người dùng thực sự cần.
7. **Gán entitlement sau các điều kiện bắt buộc:** nhóm cơ sở và role được phê duyệt; không gán mọi quyền chỉ vì có tài khoản.
8. **Kích hoạt đúng ngày/giờ hiệu lực:** kiểm tra lại nguồn nhân sự, trạng thái và điều kiện an toàn trước khi mở quyền.
9. **Readback và đối soát:** kiểm tra account, thuộc tính, role, trạng thái active và quyền thực tế tại mỗi đích.
10. **Ghi kiểm toán, thông báo và xử lý ngoại lệ:** cảnh báo lỗi, mở ticket/escalation với owner của đích và xác nhận onboarding hoàn tất khi đủ bằng chứng.

~~~mermaid
sequenceDiagram
    participant HR as HRIS
    participant IAM as IAM / IGA
    participant IDP as IdP
    participant SAAS as SCIM / SaaS
    participant AUD as Audit / Reconciliation
    HR->>IAM: Joiner event (subjectId, effectiveAt)
    IAM->>IAM: Kiểm nguồn, proofing, approval
    IAM->>IAM: Tính desired accounts và entitlements
    IAM->>IDP: Tạo hoặc liên kết account (inactive nếu cần)
    IDP-->>IAM: IdP account ID + trạng thái
    IAM->>SAAS: Tạo hoặc liên kết SCIM User
    SAAS-->>IAM: SCIM User.id + trạng thái
    IAM->>IAM: Đợi thời điểm và điều kiện kích hoạt
    IAM->>IDP: Kích hoạt tài khoản / quyền được duyệt
    IAM->>SAAS: Gán nhóm và thuộc tính đã duyệt
    IAM->>AUD: Đọc lại trạng thái các đích
    AUD-->>IAM: Đối soát đạt hoặc có sai lệch
~~~

Một số hệ thống yêu cầu tài khoản IdP được tạo trước; một số ứng dụng chỉ tạo local account khi người dùng đăng nhập lần đầu. Orchestrator phải biết **phụ thuộc của từng connector**, xử lý tình huống account đã tồn tại và không áp một chuỗi thao tác giống nhau cho mọi ứng dụng.

## 6. Ví dụ SCIM 2.0: tạo User

SCIM thường được dùng để provisioning tài khoản người dùng tới SaaS. Một request tạo user được gửi bởi **connector đã được cấp quyền**, dùng access token hoặc credential tích hợp đáng tin.

~~~http
POST /scim/v2/Users HTTP/1.1
Host: saas.example.org
Authorization: Bearer <connector-access-token>
Content-Type: application/scim+json
Accept: application/scim+json

{
  "schemas": ["urn:ietf:params:scim:schemas:core:2.0:User"],
  "externalId": "person-4821",
  "userName": "lan@company.example",
  "name": {
    "givenName": "Lan",
    "familyName": "Nguyen"
  },
  "emails": [
    {
      "value": "lan@company.example",
      "primary": true,
      "type": "work"
    }
  ],
  "active": false
}
~~~

**Giải thích:**

- \`schemas\` khai báo loại tài nguyên theo SCIM.
- \`externalId\` là tham chiếu của bên provisioning, có thể dùng để nối với \`subjectId\` nội bộ.
- \`userName\` là tên đăng nhập theo quy định của hệ thống đích; không nhất thiết là khóa không đổi suốt đời.
- \`name\`, \`emails\` chỉ đồng bộ những thuộc tính cần thiết theo hợp đồng tích hợp và chính sách dữ liệu.
- \`active: false\` minh họa pre-provisioning; cách hệ thống đích áp dụng trạng thái này **phải được kiểm chứng**, vì không phải mọi sản phẩm hỗ trợ trạng thái truy cập giống nhau.

Server SCIM thành công thường trả **HTTP 201 Created**, body User có \`id\` do server cấp và có thể có \`Location\`, \`meta\`. Connector phải lưu mapping **subject ID nội bộ → SCIM User.id** và kiểm tra dữ liệu trả về.

Không gửi mật khẩu thực, access token thực hay dữ liệu cá nhân ngoài nhu cầu vào tài liệu mẫu. Connector phải xử lý bí mật qua kho quản lý credential, không ghi \`Authorization\` header vào log.

### Tạo User không đồng nghĩa cấp quyền vào mọi ứng dụng

Tài khoản mới có thể tồn tại mà chưa có membership nhóm. Khi cần nhóm theo baseline, connector mới thực hiện thao tác thêm thành viên hoặc role theo sơ đồ mapping được phê duyệt. Ví dụ minh họa SCIM PATCH Group:

~~~http
PATCH /scim/v2/Groups/finance-invoice-readers HTTP/1.1
Host: saas.example.org
Authorization: Bearer <connector-access-token>
Content-Type: application/scim+json

{
  "schemas": ["urn:ietf:params:scim:api:messages:2.0:PatchOp"],
  "Operations": [
    {
      "op": "add",
      "path": "members",
      "value": [
        { "value": "4dc0b44f-8ad3-42d0-aa7f-c3796c67c801" }
      ]
    }
  ]
}
~~~

\`value\` ở ví dụ là **ID User trong ứng dụng đích**, không phải \`subjectId\` IAM hoặc email nếu server không dùng cùng giá trị. \`finance-invoice-readers\` cũng chỉ là ID nhóm minh họa. Phải tìm đúng Group.id và kiểm tra group mapping trước khi ghi. Một số SCIM server chỉ hỗ trợ tập con của PATCH hoặc có quy tắc role riêng: connector cần được cấu hình, thử nghiệm và có nhánh xử lý lỗi.

Sau khi thêm nhóm, **đọc lại membership và quyền tại ứng dụng đích**, vì SCIM group thành công chưa bảo đảm API đã thực thi quyền đúng.

## 7. Tài khoản đã tồn tại: link, update hay từ chối?

Trong hệ thống thật, yêu cầu tạo mới có thể gặp account đã tồn tại do:

- Người dùng từng làm việc tại tổ chức rồi quay lại.
- Một ứng dụng tạo account theo cơ chế **Just-In-Time (JIT)** tại lần SSO đầu tiên.
- Quản trị viên đã tạo trước thủ công.
- Connector retry sau timeout nhưng request trước đã tạo thành công.
- Account tồn tại do dữ liệu migration hoặc đồng bộ từ IdP khác.

**Không thể giải quyết tất cả bằng “nếu trùng email thì bỏ qua”.** Cần so khớp \`subjectId\`/tham chiếu bên ngoài với mapping đáng tin, trạng thái tài khoản và bằng chứng liên kết. Nếu chưa chứng minh hai hồ sơ cùng một người, đưa vào \`BLOCKED_FOR_REVIEW\`; không tự chiếm account đã có hoặc ghi đè dữ liệu.

| Trường hợp | Xử lý phù hợp |
| --- | --- |
| Đã có mapping tin cậy và dữ liệu khớp | **Update/ensure desired state**; không tạo lại. |
| Không có mapping nhưng tìm được một account khớp đáng tin | Thực hiện **account linking** theo quy trình được phê duyệt, ghi bằng chứng. |
| Có nhiều account giống nhau hoặc mapping mâu thuẫn | Chặn, rà soát identity resolution, tránh gộp nhầm. |
| POST timeout, chưa biết có tạo thành công | Readback/tìm theo tham chiếu hỗ trợ trước khi retry; tránh tạo trùng. |
| Account cũ đã disabled do Leaver | Xem xét rehire và policy reactivation; không tự khôi phục quyền cũ. |
| Account thủ công có đặc quyền ngoài baseline | Không xóa/ghi đè mù; đối soát quyền và owner để xác định hành động. |

### SCIM POST không tự có bảo đảm idempotent trong mọi hệ thống

Với API tạo tài nguyên, gửi lại \`POST\` có thể tạo bản ghi thứ hai nếu server không phát hiện trùng. Orchestrator cần **idempotency ledger** cục bộ hoặc cơ chế idempotency do đích hỗ trợ, dùng khóa ổn định theo **subject + target + loại thao tác**, lưu request/result và xác minh trạng thái khi kết quả chưa chắc chắn.

Ví dụ:

~~~text
idempotencyKey: provision:user:person-4821:finance-saas
desiredVersion: 17
operation: ENSURE_USER_EXISTS
target: finance-saas
status: APPLIED_AND_VERIFIED
targetUserId: 4dc0b44f-8ad3-42d0-aa7f-c3796c67c801
~~~

Đây là định dạng logic minh họa của orchestrator, **không phải header idempotency chuẩn bắt buộc của SCIM**. Khi retry, cũng phải phân biệt bản ghi được tạo bởi **cùng một yêu cầu** với một account có email tương tự nhưng thuộc người khác.

## 8. Provisioning theo trạng thái mong muốn và RBAC/ABAC

Account provisioning an toàn nên đi từ **trạng thái mong muốn (desired state)**:

\[
\text{Desired Access} = f(\text{identity},\ \text{role},\ \text{attributes},\ \text{approvals},\ \text{resource policy})
\]

Đối chiếu với hiện trạng:

\[
\text{Grant} = \text{Desired} \setminus \text{Actual}, \quad
\text{Revoke} = \text{Actual} \setminus \text{Desired}
\]

Trong thực tế, phải phân tích **nguồn cấp quyền và effective access** vì cùng một quyền có thể có nhiều đường cấp: nhóm IdP, role SaaS, ACL trực tiếp, nhóm lồng, chính sách ABAC hoặc quyền kế thừa.

**RBAC** giúp định nghĩa entitlement theo chức năng, chẳng hạn \`FINANCE_INVOICE_READER\`. **ABAC** bổ sung ràng buộc trên thuộc tính và ngữ cảnh, ví dụ chỉ truy cập hóa đơn có \`tenantId\` tương ứng, trạng thái \`APPROVED\`, mức phân loại phù hợp. Hai cơ chế thường bổ trợ nhau.

### Ví dụ ma trận tài khoản và quyền

| Đối tượng | Account cần tồn tại | Quyền được tự động cấp | Quyền không cấp mặc định |
| --- | --- | --- | --- |
| Nhân viên Finance mới | IdP, portal, finance app | Đăng nhập cơ sở; đọc hóa đơn theo phạm vi được duyệt | Phê duyệt thanh toán, export toàn bộ dữ liệu |
| Nhân viên Sales mới | IdP, portal, CRM | Đọc khách hàng thuộc vùng quản lý | Đọc khách hàng mọi vùng hoặc quản trị CRM |
| Quản trị viên hạ tầng | IdP, hệ thống vận hành | Quyền cơ sở; quyền đặc biệt theo workflow riêng | Global admin vĩnh viễn khi chỉ mới có account |
| Nhà thầu có ngày hết hạn | IdP và app theo hợp đồng | Quyền có thời hạn, đúng sponsor | Quyền không giới hạn sau thời hạn hợp đồng |
| Workload đồng bộ dữ liệu | Service identity/connector theo phạm vi workload | Scope API hẹp cho tích hợp | Quyền của tài khoản nhân viên hoặc admin toàn tenant |

Một tài khoản Finance đã được tạo không mặc nhiên được quyền xem **mọi** bản ghi Finance. Backend/API vẫn phải kiểm tra authorization mức tài nguyên: subject, action, tenant, đối tượng, thời điểm và điều kiện chính sách. Việc ẩn chức năng trong giao diện không thay thế kiểm tra này.

### Separation of Duties (SoD)

Khi cấp account và role tự động, chính sách nên phát hiện cặp quyền xung đột: một người **tạo yêu cầu thanh toán** và **tự phê duyệt**, hoặc **cấp quyền cho chính mình** rồi **duyệt quyền đó**. Nếu role mới xung đột với quyền cũ, cần chặn hoặc gỡ quyền không còn hợp lệ theo quy trình Mover trước khi mở quyền mới.

## 9. Just-In-Time (JIT) provisioning và pre-provisioning

Hai mô hình phổ biến:

| Mô hình | Khi nào tạo account ở ứng dụng? | Ưu điểm | Điều cần kiểm soát |
| --- | --- | --- | --- |
| **Pre-provisioning** | Trước lần đăng nhập đầu tiên, bằng SCIM/API/connector. | Chủ động chuẩn bị account, group, thuộc tính và kiểm soát ngày hiệu lực. | Không kích hoạt sớm; xử lý account chuẩn bị nhưng chưa từng sử dụng. |
| **Just-In-Time (JIT)** | Lúc người dùng đăng nhập SSO lần đầu; ứng dụng tạo local account dựa trên assertion/token đáng tin. | Giảm số account chưa dùng; nhanh với ứng dụng hỗ trợ. | Chỉ tạo khi subject/tenant/claim đủ tin cậy; không tự cấp quyền rộng; quản trị offboarding đầy đủ. |

**JIT provisioning không phải là identity proofing.** Một assertion SSO hợp lệ chứng minh kết quả xác thực theo mối quan hệ tin cậy, nhưng ứng dụng phải hiểu nguồn danh tính, đối tượng nhận token, trạng thái account và policy cấp quyền. Nếu claim group/role không được kiểm soát hoặc quá cũ, JIT có thể cấp sai quyền.

**JIT cũng không thay thế deprovisioning.** Ứng dụng tạo account lần đầu có thể giữ local session/role lâu sau khi người dùng nghỉ việc; cần kênh thu hồi và đối soát riêng.

Lựa chọn mô hình phụ thuộc khả năng ứng dụng, yêu cầu chuẩn bị trước, độ nhạy dữ liệu và SLA. Có thể dùng **SCIM để tạo/disable** đồng thời dùng SSO để đăng nhập; hai luồng bổ sung cho nhau.

## 10. Trạng thái account và thứ tự kích hoạt

Một account thường đi qua nhiều trạng thái:

~~~mermaid
flowchart LR
    REQ["REQUESTED"] --> PRE["PREPROVISIONED / DISABLED"]
    PRE --> READY["READY_FOR_ENROLLMENT"]
    READY --> ACT["ACTIVE"]
    ACT --> SUSP["SUSPENDED"]
    SUSP --> ACT
    ACT --> REV["DEPROVISIONING"]
    SUSP --> REV
    REV --> RET["RETIRED / REVOKED"]
~~~

Mô hình trên là minh họa, không phải tên state bắt buộc của IdP/SCIM. Trong triển khai thực:

- **Tài khoản tồn tại** khác với **tài khoản được phép đăng nhập**.
- **Tài khoản đăng nhập được** khác với **có entitlement nghiệp vụ**.
- **Entitlement có trong IAM** khác với **ứng dụng đích đã thực thi quyền**.
- **Account disabled** khác với **session/token/API key đã bị vô hiệu hóa**.

Đối với dữ liệu nhạy cảm, nên bảo đảm các điều kiện cần hoàn tất trước khi account có thể truy cập: identity proofing theo chính sách, ngày hiệu lực, MFA/authenticator enrollment, approval và trạng thái thiết bị khi có yêu cầu.

Từng hệ thống đích có thể diễn giải cờ \`active\` hoặc \`enabled\` khác nhau; connector không nên giả định rằng SCIM \`active=false\` tự động xóa mọi local session hoặc tất cả quyền ngoài hệ thống.

## 11. Xử lý lỗi, retry và tính nhất quán đa hệ thống

Provisioning hiếm khi có một **transaction ACID duy nhất** giữa HRIS, IdP, ứng dụng SaaS, cơ sở dữ liệu và hệ thống quản lý bí mật. Một bước có thể thành công trong khi bước khác thất bại.

Ví dụ:

1. IAM tạo thành công IdP account của Lan.
2. Connector tạo thành công SCIM User tại Finance SaaS.
3. Lệnh thêm nhóm \`InvoiceReader\` bị timeout.
4. Không rõ SaaS đã nhận PATCH hay chưa.
5. Nếu gửi lại không kiểm tra trạng thái, có thể gây lỗi trùng hoặc làm sai số liệu trạng thái.

Xử lý an toàn:

- **Lưu trạng thái từng target operation**: \`PENDING\`, \`IN_PROGRESS\`, \`APPLIED\`, \`VERIFIED\`, \`RETRYABLE_FAILURE\`, \`BLOCKED\`.
- **Retry có backoff, giới hạn số lần thử và jitter** cho timeout, HTTP 429 hoặc lỗi tạm thời; tôn trọng \`Retry-After\` khi có.
- **Readback trước khi retry request không chắc chắn**, nhất là POST tạo account hoặc PATCH thay membership.
- **Không retry vô hạn** với lỗi thiếu quyền connector, identity collision, mapping mâu thuẫn hoặc approval chưa có; chuyển escalation.
- **Bảo vệ thứ tự sự kiện**: sử dụng revision/effectiveAt từ nguồn có thẩm quyền để event cũ không tạo lại quyền đã thu hồi.
- **Không tự khôi phục quyền bị gỡ đúng chính sách** chỉ vì một target mới cấp quyền thất bại.
- **Bảo đảm idempotent ở mức nghiệp vụ**, chống xử lý trùng event và trùng thao tác dưới concurrency.
- **Ghi lại và đối soát trạng thái thực tế** để phục hồi sau khi worker/orchestrator khởi động lại.

### Mẫu trạng thái cho từng hệ thống đích

| Target | Operation | Trạng thái | Điều kiện hoàn tất |
| --- | --- | --- | --- |
| IdP | Ensure user exists, inactive | \`VERIFIED\` | Đọc lại đúng account ID và trạng thái. |
| Finance SaaS | Ensure SCIM user exists | \`VERIFIED\` | Có mapping \`subjectId\` ↔ \`User.id\`, thuộc tính khớp. |
| Finance SaaS | Add approved group | \`RETRYABLE_FAILURE\` | Chưa hoàn tất cho đến khi readback membership và quyền. |
| Portal | Create baseline account | \`VERIFIED\` | Đọc lại dữ liệu và trạng thái. |
| IdP | Activate at effective time | \`PENDING\` | Chờ ngày và điều kiện activation. |

Workflow tổng nên phản ánh **PARTIAL_FAILURE** cho đến khi những thao tác bắt buộc đạt kết quả. Cần xác định quyền nào được phép sử dụng trước khi các ứng dụng khác hoàn tất; không một cờ “onboarding complete” nào được bỏ qua các phụ thuộc quan trọng.

## 12. Reconciliation: phát hiện account thiếu, trùng và quyền ngoài luồng

**Reconciliation (đối soát)** so sánh **desired state** do IAM tính với **actual state** đọc từ mỗi hệ thống đích. Nó giúp phát hiện lỗi mà các thao tác theo sự kiện không nhìn thấy được:

- Account chưa được tạo dù workflow báo đã gửi request.
- User tồn tại hai bản ghi ở cùng SaaS do retry POST.
- Role bị admin cấp thủ công ngoài IAM và không có phê duyệt.
- Account bị xóa/sửa cục bộ nên lệch thuộc tính hoặc mất mapping.
- User đã Mover/Leaver nhưng vẫn giữ quyền từ nhóm cũ.
- Account mồ côi không còn chủ thể/owner có hiệu lực.
- Service account hoặc personal token vẫn hoạt động dù người sở hữu đã rời vai trò.

~~~text
Desired:  subject person-4821
          finance-saas User.id = X
          active = true (sau ngày hiệu lực)
          roles = {InvoiceReader}

Actual:   finance-saas User.id = X
          active = true
          roles = {InvoiceReader, FinanceAdmin}

Drift:    FinanceAdmin là entitlement ngoài trạng thái được duyệt
Action:   Chặn/escalate theo policy, thu hồi quyền dư và xác minh lại
~~~

Không nên mặc định **ghi đè toàn bộ target account** khi gặp sai lệch: có thể tồn tại quyền hệ thống đích sở hữu hợp pháp hoặc đang có thay đổi đồng thời. Cần **ownership matrix** chỉ rõ thuộc tính và entitlement nào do IAM quản lý; hành động với quyền ngoài phạm vi phải qua quy trình được phê duyệt.

**Readback thành công không chỉ là HTTP 200.** Cần xác nhận account, thuộc tính, role, trạng thái đăng nhập và quyền thực tế đúng mục tiêu. Với đường truy cập quan trọng, có thể bổ sung kiểm thử authorization có kiểm soát để xác nhận role/ACL được thực thi.

## 13. Liên kết Joiner–Mover–Leaver và vòng đời tài khoản

Tạo account tự động chỉ là giai đoạn đầu của **quản trị vòng đời**. Mỗi tài khoản được tạo phải biết **điều kiện cập nhật và thu hồi** sau này.

| Sự kiện | Tác động đến account | Tác động đến quyền | Kiểm tra quan trọng |
| --- | --- | --- | --- |
| **Joiner** | Tạo/link account, kích hoạt theo điều kiện và ngày hiệu lực. | Cấp baseline theo vai trò, phê duyệt và MFA policy. | Không cấp account nhầm hoặc quyền quá sớm. |
| **Mover** | Giữ ID ổn định, cập nhật thuộc tính/nhóm và một số ứng dụng cần dùng. | Gỡ quyền cũ, cấp quyền mới, kiểm tra SoD, hết hạn ngoại lệ. | Không để privilege creep hoặc session giữ quyền cũ. |
| **Leaver** | Khóa/disable rồi deprovision theo chính sách tại từng hệ thống. | Gỡ group/role/ACL, xử lý refresh token/session/API key. | Không còn đường truy cập tồn dư; lưu evidence. |
| **Rehire** | Đối chiếu hồ sơ cũ và chính sách tạo/link/khôi phục. | Chỉ cấp quyền của quan hệ/vị trí mới. | Không tự khôi phục toàn bộ quyền cũ. |
| **Hủy nhận việc** | Hủy account đã chuẩn bị, revoke bootstrap credentials. | Không có entitlement nghiệp vụ được kích hoạt. | Account pre-hire không tồn tại dai dẳng. |

### Khi chuyển vai trò

Tạo account ở ứng dụng mới có thể là phần của Mover, nhưng hệ thống phải **thu hồi quyền ứng dụng cũ**. Nếu chỉ thêm Finance SaaS rồi giữ nguyên quyền Sales CRM, người dùng tích lũy quyền và có nguy cơ xung đột nhiệm vụ. Thực thi nên ưu tiên giải quyết quyền cũ có rủi ro trước khi mở quyền mới có xung đột.

### Khi rời tổ chức

Leaver cần vô hiệu hóa các account đã tạo; **SCIM \`active=false\` không mặc nhiên chấm dứt mọi phiên ứng dụng**. Nếu SaaS cho local login hoặc API token độc lập, cần xử lý bổ sung. Chính sách retention có thể yêu cầu giữ dữ liệu nghiệp vụ và audit mà không tiếp tục cho phép chủ thể cũ đăng nhập.

## 14. Provisioning danh tính dịch vụ và connector

Tạo account tự động không chỉ dành cho nhân viên. Các **service account**, **service principal**, **managed identity** hoặc **workload identity** cũng cần quy trình đăng ký, cấp quyền và thu hồi.

Ví dụ một dịch vụ đồng bộ hóa đơn cần:

1. **Owner:** đội kỹ thuật, business owner, ứng dụng và môi trường dùng danh tính.
2. **Request/approval:** mục đích, hệ thống đích, API scope, dữ liệu và thời hạn dự kiến.
3. **Identity:** danh tính riêng cho workload hoặc ranh giới tin cậy; không dùng mật khẩu nhân viên.
4. **Authentication:** ưu tiên managed identity/workload federation, token ngắn hạn hoặc mTLS khi phù hợp; tránh secret dài hạn chia sẻ.
5. **Authorization:** scope, tenant, resource và action tối thiểu.
6. **Lifecycle:** rotation, rà soát, xử lý compromise và decommissioning khi workload ngừng chạy.

**Provisioning connector** bản thân nó thường là một danh tính dịch vụ có quyền tạo/xóa account và gán nhóm trên nhiều ứng dụng. Vì vậy connector cần:

- Credential được bảo vệ trong vault hoặc cơ chế identity của nền tảng, không hardcode trong source/log.
- Scope giới hạn đúng tenant, ứng dụng và thao tác cần thiết.
- Secret/credential rotation, cảnh báo truy cập bất thường và log kiểm toán.
- Phân quyền riêng giữa người cấu hình mapping, người phê duyệt role và người quản lý credential.
- Hạn chế môi trường: connector staging không được tùy tiện cấp admin production.
- Cơ chế nhanh để revoke/disable connector khi bị lộ, cùng phương án xử lý công việc đang dở.

**Không áp MFA tương tác cho mỗi request của job tự động** như với người dùng. MFA phù hợp để bảo vệ những **người quản trị** connector/vault; workload cần xác thực máy đến máy bằng cơ chế phù hợp.

## 15. Mô hình dữ liệu và event-driven provisioning

Orchestrator nên nhận sự kiện có định danh ổn định và metadata đủ kiểm soát:

~~~json
{
  "eventId": "joiner-2026-2045",
  "eventType": "workforce.joiner.effective",
  "subjectId": "person-4821",
  "source": "trusted-hris",
  "revision": 7,
  "effectiveAt": "2026-12-01T00:00:00Z",
  "employmentStatus": "ACTIVE",
  "department": "FINANCE",
  "approvalRef": "approve-onboard-551"
}
~~~

**Dữ liệu minh họa**, không phải event thật. Thời gian dùng UTC để tránh mơ hồ; chính sách phải quy đổi đúng múi giờ/ngày hiệu lực của nhân sự. \`eventId\` giúp phát hiện lặp, nhưng **revision và trạng thái hiện hành** mới giúp tránh sự kiện cũ ghi đè kết quả mới.

Một bản ghi desired-state:

~~~yaml
subjectId: person-4821
sourceRef: trusted-hris
desiredRevision: 7
accountType: HUMAN
accessEffectiveAt: "2026-12-01T00:00:00Z"
targets:
  - application: workforce-idp
    accountState: ENABLED_AFTER_EFFECTIVE_AT
    roles:
      - EMPLOYEE_BASIC
  - application: finance-saas
    accountState: ENABLED_AFTER_EFFECTIVE_AT
    roles:
      - INVOICE_READER
    tenantScope: finance-vn
approvalRef: approve-onboard-551
policyVersion: joiner-policy-v4
~~~

Schema trên **minh họa cách tổ chức yêu cầu**, không phải cấu hình của SCIM/IdP thực tế. Lưu **source, revision, policy version, approval và target mappings** để một thao tác tự động có thể được giải thích và tái hiện.

### Các thuộc tính cần có trong task ledger

| Trường | Lý do |
| --- | --- |
| \`subjectId\`, \`targetSystem\`, \`operation\` | Định danh đúng việc cần làm. |
| \`desiredRevision\`, \`policyVersion\` | Không xử lý nhầm trạng thái cũ. |
| \`requestId\`, \`idempotencyKey\` | Chống tạo trùng và hỗ trợ retry. |
| \`targetAccountId\` | Liên kết ID thực do hệ thống đích cấp. |
| \`status\`, \`attemptCount\`, \`lastError\` | Theo dõi tiến độ và điều phối xử lý lỗi. |
| \`requestedAt\`, \`appliedAt\`, \`verifiedAt\` | Đo độ trễ và chứng minh tác động cuối. |
| \`approvalRef\`, \`actor\`, \`correlationId\` | Phục vụ audit và truy vết. |

## 16. Pseudocode Java: ensure account tồn tại và đúng trạng thái

Đoạn mã mô tả **hợp đồng nghiệp vụ**, không phải Java production-ready. Mọi adapter phải kiểm tra nguồn dữ liệu, bảo mật API, lỗi mạng và đồng bộ theo đặc tính hệ thống đích.

~~~java
// Pseudocode: chỉ nhận event đã xác thực từ nguồn có thẩm quyền.
ProvisioningResult handleJoiner(TrustedJoinerEvent event) {
    if (event.revision() <= eventLedger.latestAppliedRevision(event.subjectId())) {
        return ProvisioningResult.ignoredStaleOrDuplicate();
    }

    Identity identity = identityRegistry.resolveWithoutGuessing(event.subjectId());
    WorkforceState workforce = hrRepository.currentState(identity.id());
    Approval approval = approvalRepository.currentApproval(identity.id());

    if (!eligibilityPolicy.canProvision(identity, workforce, approval)) {
        return ProvisioningResult.blocked("not_eligible_or_approved");
    }

    DesiredState desired = provisioningPolicy.calculateDesiredState(
        identity, workforce, approval
    );

    for (TargetAccountRequest target : desired.targetsInDependencyOrder()) {
        // Ledger là nơi lưu idempotency, trạng thái và ID thực tại đích.
        ProvisioningTask task = taskLedger.ensureTask(
            identity.id(), target.system(), desired.revision()
        );

        try {
            // Không POST mù nếu request cũ timeout hoặc account đã tồn tại.
            TargetAccount actual = targetConnector(target.system())
                .findByTrustedMappingOrReconcile(identity.id(), task.targetAccountId());

            if (actual == null) {
                actual = targetConnector(target.system()).createPreprovisioned(
                    target, task.idempotencyContext()
                );
            }

            taskLedger.saveTargetAccountId(task, actual.id());
            targetConnector(target.system()).applyApprovedAttributesAndRoles(
                actual.id(), target, desired.accessEffectiveAt()
            );

            TargetAccount readback = targetConnector(target.system()).readById(
                actual.id()
            );
            if (!reconciliation.matchesExpectedState(readback, target)) {
                taskLedger.markNeedsReconciliation(task);
                continue;
            }

            taskLedger.markVerified(task);
        } catch (RetryableProvisioningException ex) {
            taskLedger.markRetryableFailure(task, ex.safeCode());
        } catch (AmbiguousIdentityOrPolicyException ex) {
            taskLedger.markBlockedForReview(task, ex.safeCode());
        }
    }

    // Check lại trạng thái hiện hành trước activation, vì HR có thể
    // thay đổi ngày bắt đầu hoặc hủy quyết định trong lúc đồng bộ.
    activationScheduler.activateWhenEligible(identity.id(), desired.revision());
    return provisioningReport.fromTaskLedger(identity.id(), desired.revision());
}
~~~

Đặc tính cần có khi triển khai thật:

- **Đồng bộ theo revision và khóa chủ thể/đích** để hai worker không cùng tạo account.
- **Không tự sửa account khác** nếu chỉ dựa vào email hoặc tên giống nhau.
- **Không đưa quyền chưa duyệt vào account active**; khi adapter không hỗ trợ pre-provisioning an toàn, cần trì hoãn thao tác tạo/cấp quyền đến mốc hiệu lực.
- **Không dùng exception chung rồi đánh dấu thành công**; lỗi chưa rõ trạng thái cần readback/retry có kiểm soát.
- **Tách việc cấp quyền và activation**, có kiểm tra điều kiện tại thời điểm thực thi thực sự.
- **Không xem \`POST\` thành công là hoàn tất:** cần đọc lại đúng account/role và báo cáo coverage gap nếu ứng dụng không hỗ trợ kiểm chứng.
- **Không lưu credential thật trong ledger/log**; các adapter lấy credential qua secret manager hoặc workload identity.

## 17. Audit và vận hành: làm sao biết provisioning thực sự thành công?

Một báo cáo chỉ ghi “đã tạo 10 tài khoản” chưa phản ánh chất lượng IAM. Cần lưu được chuỗi bằng chứng từ **nguồn yêu cầu đến hệ thống đích**:

| Nhóm bằng chứng | Dữ liệu quan trọng | Câu hỏi kiểm toán |
| --- | --- | --- |
| Nguồn Joiner | Event ID, subject ID, nguồn HR, effectiveAt, revision. | Ai yêu cầu và từ lúc nào có hiệu lực? |
| Proofing/approval | Kết quả kiểm tra, chính sách, approver, thời điểm. | Vì sao được phép tạo và kích hoạt? |
| Identity resolution | Canonical subject ID, liên kết HR/IdP/target account. | Có tạo nhầm hoặc tạo trùng không? |
| Desired entitlement | Role, scope, policy version, tenant, hạn quyền. | Tài khoản nên có những quyền nào? |
| Provisioning request | Target, operation, request ID, attempt, trạng thái. | Lệnh nào đã được gửi đến đâu? |
| Target readback | User ID đích, active state, membership/role, verifiedAt. | Ứng dụng có thực thi đúng không? |
| Failure/retry | Mã lỗi an toàn, owner, thời hạn, thao tác khắc phục. | Còn bước nào chưa hoàn tất? |
| Lifecycle changes | Mover/Leaver, revoke session, remove group, disable app. | Sau này quyền đã thu hồi đúng chưa? |

Không log **mật khẩu, API key, access token, refresh token, private key hoặc dữ liệu cá nhân không cần thiết**. Các ID, thuộc tính nhân sự và audit log phải có chính sách phân quyền, retention, mã hóa và cơ chế kiểm tra sửa đổi trái phép phù hợp.

### Các chỉ số nên theo dõi

- **Provisioning lead time:** từ lúc yêu cầu đủ điều kiện đến khi từng target đạt trạng thái mong muốn.
- **First-day readiness:** tỷ lệ Joiner có account/quyền cần thiết đúng ngày bắt đầu.
- **Partial failure rate:** tỷ lệ sự kiện có target chưa hoàn tất hoặc chưa readback.
- **Duplicate/orphan account count:** số tài khoản trùng hoặc không còn chủ thể/owner hợp lệ.
- **Entitlement drift:** quyền thực tế khác trạng thái mong muốn.
- **Approval bypass incidents:** lần cấp quyền thiếu phê duyệt hoặc sai ngày hiệu lực.
- **Reconciliation coverage:** tỷ lệ ứng dụng/tài khoản được đối soát và có bằng chứng.
- **Residual access after Mover/Leaver:** những quyền cũ chưa thu hồi xong tại hệ thống đích.

Tách **requestedAt**, **acceptedAt**, **appliedAt** và **verifiedAt**. Mã HTTP 200/201 cho một API có thể chỉ chứng minh thao tác được chấp nhận, chưa đủ chứng minh effective access đúng.

## 18. Các lỗi thiết kế thường gặp

| Sai lầm | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Tạo account ngay từ một email tự khai. | Account giả hoặc liên kết sai người. | Xác minh nguồn có thẩm quyền, proofing và approval. |
| Dùng email làm ID duy nhất. | Tạo trùng, gộp nhầm hoặc cấp lại account khi đổi email. | Canonical subject ID và target mappings ổn định. |
| Mọi Joiner mặc định có quyền admin. | Cấp quyền quá mức, SoD vi phạm. | Baseline RBAC/ABAC và approval cho quyền nhạy cảm. |
| Tạo account đồng nghĩa active. | Truy cập trước ngày làm việc. | Pre-provisioning inactive và activation theo điều kiện. |
| POST lại sau timeout mà không readback. | Account trùng hoặc mapping sai. | Idempotency ledger và tra cứu đối chiếu. |
| Tin \`externalId\` luôn là unique constraint. | Nhầm/đè account khi SCIM server không bảo đảm. | Kiểm khả năng server, lưu ID đích và kiểm tra trùng. |
| Chỉ tạo account ở IdP. | Ứng dụng đích chưa có account hoặc role đúng. | Orchestration và readback theo từng target. |
| Chỉ xét role tại IdP. | ACL, role SaaS, quyền DB ngoài luồng còn tồn. | Inventory nguồn quyền và reconciliation. |
| Không xử lý event cũ đến sau. | Khôi phục quyền sau Mover/Leaver. | Revision, event ordering và tính desired từ nguồn hiện hành. |
| Connector dùng secret trong source code. | Lộ quyền cấp tài khoản hàng loạt. | Vault/managed identity, rotation và scope hạn chế. |
| Lỗi SaaS nhưng vẫn báo onboarding complete. | Người dùng thiếu công cụ hoặc quyền bị cấp lệch. | Trạng thái partial failure, owner, retry và xác minh. |
| JIT tạo account nhưng không có deprovision. | Account và phiên tồn tại sau nghỉ việc. | Gắn JIT với lifecycle, disable/revoke ở ứng dụng. |

## 19. Tình huống thực hành: Joiner vào Finance

**Bối cảnh:** Lan được tuyển vào Finance, ngày bắt đầu đã được HR phê duyệt. Các ứng dụng bắt buộc là IdP, portal nội bộ và Finance SaaS. Chỉ cần quyền đọc hóa đơn đã duyệt, không được phê duyệt thanh toán.

### Bước 1 – Nhận và chuẩn hóa sự kiện

IAM nhận \`subjectId=person-4821\`, \`effectiveAt=2026-12-01T00:00:00Z\` cùng nguồn, revision và approval. Registry kiểm tra không có account thuộc người khác bị trùng liên kết. Proofing và ngày hiệu lực được kiểm theo quy định.

### Bước 2 – Tính desired state

~~~text
IdP user                       CREATE / LINK, then ACTIVATE when eligible
Portal account                 CREATE / LINK with employee baseline
Finance SaaS user              CREATE / LINK
Finance INVOICE_READER         GRANT after approval/effective time
Finance PAYMENT_APPROVER       DO NOT GRANT
Sales CRM account              DO NOT CREATE
Privileged cloud administrator DO NOT GRANT
~~~

### Bước 3 – Pre-provision và lưu mapping

Orchestrator tạo IdP account ở trạng thái không có quyền truy cập nghiệp vụ, lưu \`IdP user ID\`. Connector SCIM tạo Finance User với \`active=false\` nếu ứng dụng hỗ trợ, ghi nhận \`User.id\` và kiểm tra kết quả. Nếu có account đã tồn tại, workflow chỉ liên kết sau khi xác minh cùng chủ thể.

### Bước 4 – Kích hoạt và cấp quyền

Đến thời điểm hợp lệ, hệ thống kiểm tra lại trạng thái HR, approval và điều kiện MFA. IAM kích hoạt các account cần thiết, thêm nhóm \`InvoiceReader\`, xác nhận app đã nhận. API Finance vẫn chỉ cho Lan đọc hóa đơn trong tenant và trạng thái được phép.

### Bước 5 – Xử lý lỗi

Nếu SCIM trả timeout khi thêm \`InvoiceReader\`, task thành \`RETRYABLE_FAILURE\`; IAM kiểm tra membership thực tế, retry an toàn và không báo bước Finance hoàn tất cho tới khi readback đạt. Nếu phát hiện account Finance khác cùng email nhưng có \`externalId\` không khớp, dừng để điều tra, tránh gán quyền cho sai người.

### Bước 6 – Kiểm chứng và theo dõi vòng đời

Hồ sơ onboarding chỉ được đóng khi tất cả đích bắt buộc có trạng thái xác minh, entitlement đúng phê duyệt và không còn blocker. Khi Lan chuyển bộ phận hoặc nghỉ việc, cùng mapping và desired-state engine hỗ trợ gỡ quyền, vô hiệu hóa account, xử lý session/token và đối soát.

## 20. Bộ kiểm thử tối thiểu

| Tình huống | Kết quả kỳ vọng |
| --- | --- |
| HR gửi Joiner hợp lệ, proofing và approval đầy đủ, ngày hiệu lực đã đến. | Tạo/link account đúng chủ thể, chỉ cấp role được duyệt và readback. |
| HR ghi hồ sơ trước ngày bắt đầu. | Chỉ pre-provision inactive hoặc chờ theo chính sách; không truy cập nghiệp vụ sớm. |
| User tự gửi \`department=Finance\` trong request không đáng tin. | Không tự cấp quyền; chỉ dùng thuộc tính từ nguồn có thẩm quyền. |
| Email trùng với account của người khác tại SaaS. | Chặn linking/provisioning cho tới khi xác minh, không overwrite. |
| SCIM POST timeout nhưng user đã được tạo. | Tìm/readback theo mapping tin cậy trước khi retry, không tạo trùng. |
| Cùng một event Joiner đến hai lần. | Idempotent, chỉ một account hợp lệ và một tập entitlement mong muốn. |
| Joiner bị hủy sau khi pre-provision. | Thu hồi trạng thái chuẩn bị, bootstrap credential và quyền có thể đã phát sinh. |
| Tài khoản IdP tạo thành công, Finance SaaS lỗi. | Workflow partial failure, có retry/escalation; không báo toàn bộ hoàn tất. |
| SCIM user tồn tại nhưng chưa có group. | Tách account creation khỏi entitlement, không tự suy quyền. |
| Đã có group \`FinanceAdmin\` cấp ngoài IAM. | Phát hiện entitlement drift, xử lý qua chính sách và owner. |
| Role mới xung đột với quyền cũ khi Mover. | Chặn cửa sổ SoD, thu hồi quyền cũ cần thiết trước khi mở quyền mới. |
| Event Joiner/Mover cũ đến sau Leaver mới. | Không kích hoạt lại account; dùng revision và nguồn hiện hành. |
| Người dùng đăng nhập SSO nhưng không có quyền đọc hóa đơn tenant khác. | Backend từ chối request dù account và phiên hợp lệ. |
| Provisioning connector bị lộ token. | Có khả năng revoke/rotate, audit và giới hạn scope để giảm tác động. |
| Nhân viên nghỉ việc nhưng JIT-created account còn phiên local. | Leaver workflow xác định và xử lý session/quyền tại ứng dụng đích. |
| Service account ngừng được sử dụng. | Kiểm tra dependency, revoke credential/role và đóng owner theo policy. |

## 21. Tự kiểm tra kiến thức

**Câu 1.** Vì sao không thể coi việc tạo SCIM User thành công là hoàn tất account provisioning?

**Trả lời:** Vì còn trạng thái kích hoạt, mapping danh tính, group/role/ACL, đăng ký xác thực, ngày hiệu lực và readback quyền thực tế. Account có thể tồn tại nhưng chưa đủ hoặc đang có quyền sai.

**Câu 2.** \`email\` và \`externalId\` có phải lúc nào cũng đủ để tìm duy nhất account tại SaaS?

**Trả lời:** Không. Email có thể đổi hoặc được tái sử dụng; tính duy nhất và hỗ trợ lọc \`externalId\` phụ thuộc hệ thống đích. Cần canonical subject ID, mapping tới target account ID và cơ chế xác minh liên kết.

**Câu 3.** Khi request tạo account timeout, vì sao không nên gửi lại POST ngay?

**Trả lời:** Request đầu có thể đã được áp dụng dù phản hồi bị mất. Cần readback, đối chiếu target ID hoặc dùng cơ chế idempotency đáng tin để tránh tạo trùng.

**Câu 4.** Tạo account tự động có nên tự cấp quyền administrator cho mọi nhân viên phòng IT?

**Trả lời:** Không. Entitlement cần dựa trên role cụ thể, phạm vi, phê duyệt, điều kiện ABAC và phân tách nhiệm vụ; đặc quyền cao thường yêu cầu workflow riêng.

**Câu 5.** JIT provisioning khi đăng nhập SSO có thay thế SCIM và xử lý Leaver không?

**Trả lời:** Không. JIT có thể tạo local account ở lần đăng nhập đầu, nhưng quy trình thu hồi, xử lý session và cập nhật entitlement vẫn cần được thiết kế. SCIM là một cơ chế đồng bộ có thể bổ sung.

**Câu 6.** Sự kiện HR cho biết nhân viên chuyển vai trò, nhưng IdP nhóm cũ chưa được gỡ. IAM nên làm gì?

**Trả lời:** Tính lại desired state, gỡ entitlement không còn hợp lệ, xử lý session/token liên quan, đối soát ở hệ thống đích và ghi nhận lỗi nếu chưa thu hồi thực sự.

**Câu 7.** Vì sao cần kiểm tra lại nguồn HR tại thời điểm activation dù account đã pre-provision?

**Trả lời:** Ngày bắt đầu, quyết định tuyển dụng hoặc tình trạng quan hệ có thể thay đổi sau khi account được chuẩn bị. Kích hoạt cần dựa trên trạng thái và phê duyệt hiện hành, không chỉ dữ liệu tại lúc tạo.

---

**Ghi nhớ:** Tạo account tự động là một **quy trình quản trị trạng thái mong muốn**, bắt đầu từ **nguồn danh tính đáng tin và quyền được phê duyệt**, đi qua **tạo/liên kết account, cấp entitlement, kích hoạt đúng thời điểm**, rồi **đọc lại và đối soát tại từng hệ thống đích**. Thiết kế tốt phải xử lý sự kiện trùng, lỗi mạng, thay đổi vai trò, credential và quyền ngoài luồng. Chỉ như vậy account provisioning mới phục vụ trọn vòng đời **Joiner–Mover–Leaver**, duy trì **least privilege** và giảm quyền truy cập tồn dư.
