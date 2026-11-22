# Liên kết danh tính, SSO và quyền truy cập tối thiểu

## 1. Vì sao kiến trúc cloud cần liên kết danh tính?

Một hệ thống cloud có nhiều nhóm caller: nhân viên đăng nhập console, developer triển khai ứng dụng, service account chạy pipeline, container truy cập object storage, function đọc queue, đối tác tích hợp API và người dùng đăng nhập sản phẩm. Nếu mỗi nơi có tài khoản, mật khẩu hoặc access key riêng, tổ chức sẽ khó theo dõi ai đang truy cập gì, thu hồi quyền khi nhân sự đổi vai trò, kiểm soát phiên làm việc và điều tra hoạt động bất thường.

**Identity federation (liên kết danh tính)** cho phép một hệ thống tin cậy danh tính được xác minh bởi Identity Provider (IdP) khác theo giao thức và trust relationship đã cấu hình. **Single Sign-On (SSO)** cho phép người dùng xác thực với IdP rồi truy cập nhiều ứng dụng được liên kết mà không phải nhập lại credential cho từng ứng dụng. **Least privilege (quyền tối thiểu)** giới hạn mỗi người dùng, ứng dụng hoặc workload chỉ có đúng quyền cần thiết, trong đúng phạm vi và khoảng thời gian cần thiết.

Ba cơ chế giải quyết các câu hỏi khác nhau:

- Federation: hệ thống nào phát hành và xác minh danh tính? Hai bên tin cậy nhau dựa trên điều kiện nào?
- SSO: người dùng đăng nhập vào nhiều ứng dụng bằng phiên xác thực nào?
- Least privilege: danh tính đã được xác minh được làm những hành động gì, trên tài nguyên nào?

SSO giúp quản lý phiên đăng nhập tập trung, nhưng không tự động làm mọi ứng dụng an toàn. Nếu một role liên kết có quyền Administrator trên toàn bộ cloud account, SSO chỉ làm việc sử dụng quyền rộng trở nên thuận tiện hơn. Kiến trúc phải ghép identity federation với authorization, lifecycle, audit, session control và quy trình review quyền.

Trong module **CLOUD_ARCHITECTURE**, đây là nền tảng bảo mật xuyên suốt network, compute, storage, database và data platform. Danh tính nên là ranh giới kiểm soát chính; địa chỉ IP hoặc vị trí trong private network chỉ là tín hiệu bổ sung.

### Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt identity, authentication, federation, SSO, provisioning và authorization.
2. Chọn SAML 2.0 hoặc OpenID Connect (OIDC) cho các tình huống SSO phù hợp.
3. Phân biệt xác thực với cấp phát tài khoản và quyền qua SCIM/lifecycle workflow.
4. Thiết kế danh tính workforce và workload mà không phải nhúng credential dài hạn.
5. Áp dụng RBAC, ABAC, permission boundary và resource-level policy theo least privilege.
6. Thiết kế session, MFA, role assumption, JIT access và quy trình thu hồi quyền.
7. Kiểm soát trust giữa account, project, tenant, service và cloud provider.
8. Thiết lập audit, access review và kiểm thử policy trước khi triển khai.

## 2. Các lớp của hệ thống danh tính

| Thành phần | Vai trò | Ví dụ |
|---|---|---|
| **Subject / principal** | Thực thể đang yêu cầu truy cập | Nhân viên, service, function, partner |
| **Identity Provider (IdP)** | Xác thực subject và phát assertion/token | Enterprise IdP |
| **Service Provider / Relying Party** | Ứng dụng tin cậy IdP để xác thực | Cloud console, internal portal |
| **Federation trust** | Quy tắc xác định IdP/issuer nào được tin cậy | SAML metadata, OIDC issuer/JWKS, trust policy |
| **Credential / authenticator** | Chứng minh subject kiểm soát tài khoản hoặc key | Password, passkey, security key, certificate |
| **Provisioning system** | Tạo, cập nhật và vô hiệu hóa account/group | HRIS, IAM governance, SCIM |
| **Authorization engine** | Quyết định hành động được phép | IAM policy, RBAC, ABAC, resource policy |
| **Audit / risk engine** | Ghi nhận hành vi và đánh giá rủi ro | Sign-in logs, access events, SIEM |

### 2.1. Authentication và authorization không giống nhau

Authentication trả lời “caller là ai?”. Authorization trả lời “caller được phép làm gì với resource này?”. Một người đăng nhập đúng SSO vẫn có thể không được quyền đọc production database. Một workload dùng đúng certificate vẫn không được phép xóa object nếu trust policy chỉ cấp quyền đọc.

Quyết định truy cập thường kết hợp danh tính principal đã xác minh; credential/session còn hiệu lực và đạt yêu cầu MFA/risk; group/role/attribute phù hợp; action và resource trong phạm vi cho phép; không có explicit deny hoặc permission boundary chặn; cùng context như environment, source identity, time hay network.

### 2.2. Mô hình trust

~~~mermaid
flowchart LR
    User["Employee / workload"] --> IdP["Identity Provider"]
    IdP --> Assertion["SAML assertion / OIDC token"]
    Assertion --> Trust["Federation trust validation"]
    Trust --> Session["Short-lived session"]
    Session --> AuthZ["Authorization policies"]
    AuthZ --> Resource["Cloud resource / API"]
    Resource --> Audit["Audit events"]
    Session --> Audit
~~~

Trust validation phải kiểm tra issuer, audience, signature, thời hạn và các claim cần thiết theo giao thức. Sau khi tạo session, hệ thống vẫn phải áp dụng authorization cho từng action/resource.

## 3. Workforce identity và workload identity

Hai nhóm danh tính có vòng đời và cách xác thực khác nhau.

| Loại | Đại diện cho | Cơ chế thường phù hợp |
|---|---|---|
| **Workforce identity** | Nhân viên, quản trị viên, developer, nhà thầu | Enterprise IdP, SSO, MFA, group/role mapping, JIT elevation |
| **Workload identity** | VM, container, function, CI/CD job, application service | Managed identity, workload federation, service account, short-lived token, mTLS |
| **Customer identity** | Người dùng sản phẩm | Customer IdP/CIAM, OIDC, passkey/MFA theo rủi ro |
| **Partner identity** | Đối tác B2B hoặc integration client | Federation riêng, OAuth client, certificate hoặc identity có scope |

Không dùng tài khoản nhân viên chia sẻ cho ứng dụng. Một workload cần principal riêng để audit biết service nào đã gọi API. Tương tự, không dùng một service account chung cho mọi pipeline nếu mỗi pipeline có thể được cấp quyền riêng theo dataset và environment.

### 3.1. Danh tính workload không phải secret tĩnh

Một mẫu cũ là lưu access key trong environment variable hoặc file cấu hình rồi cho ứng dụng dùng vô thời hạn. Nếu key bị lộ trong log, image hoặc repository, attacker có thể sử dụng cho tới khi key được thu hồi.

Ưu tiên managed identity/service identity do nền tảng cấp; federation từ workload identity của CI/CD sang cloud role; token ngắn hạn với audience và scope giới hạn; certificate ngắn hạn được cấp theo identity; rotation/revocation có quy trình và audit.

Khi nền tảng không hỗ trợ federation, secret tĩnh có thể là phương án chuyển tiếp; cần secret manager, quyền đọc secret tối thiểu, rotation tự động, phát hiện usage bất thường và kế hoạch loại bỏ.

## 4. SSO hoạt động như thế nào?

SSO giảm số lần người dùng phải nhập credential bằng cách để IdP làm trung tâm xác thực. Ứng dụng nhận assertion hoặc token theo một giao thức đã cấu hình và tạo session riêng.

### 4.1. Luồng SAML 2.0

SAML 2.0 thường dùng XML assertion giữa Identity Provider và Service Provider (SP), phổ biến trong workforce SSO và ứng dụng doanh nghiệp.

~~~mermaid
sequenceDiagram
    participant U as User
    participant SP as Service Provider
    participant IdP as Identity Provider
    U->>SP: Truy cập ứng dụng
    SP-->>U: Redirect tới IdP / AuthnRequest
    U->>IdP: Đăng nhập, MFA nếu yêu cầu
    IdP-->>U: SAML Response qua browser
    U->>SP: Gửi SAML Response
    SP->>SP: Verify signature, issuer, audience, time, recipient
    SP-->>U: Tạo session ứng dụng
~~~

Ứng dụng phải xác minh chữ ký bằng signing certificate đáng tin cậy; kiểm tra issuer, audience, destination/recipient, thời gian hiệu lực, request correlation và replay protection theo cấu hình. Không chỉ parse XML rồi tin nội dung assertion. Cần cấu hình chống XML signature wrapping và xử lý XML an toàn.

### 4.2. Luồng OpenID Connect

OIDC xây dựng trên OAuth 2.0 và dùng ID Token để truyền thông tin xác thực người dùng cho relying party. Authorization Code Flow với PKCE thường phù hợp cho web/mobile public client; backend confidential client có thể giữ credential trong môi trường bảo vệ.

~~~mermaid
sequenceDiagram
    participant U as User
    participant C as Client
    participant IdP as OIDC Provider
    participant API as Resource API
    U->>C: Bắt đầu đăng nhập
    C->>IdP: Authorization request + state + nonce + PKCE
    IdP->>U: Authenticate / MFA
    IdP-->>C: Authorization code
    C->>IdP: Redeem code + PKCE verifier
    IdP-->>C: ID token + access token
    C->>C: Validate ID token
    C->>API: Access token
    API->>API: Validate access token + authorize resource
~~~

ID Token phục vụ client xác minh đăng nhập; access token dành cho API/resource server. API phải kiểm tra audience của access token và không dùng ID Token thay thế.

### 4.3. SAML và OIDC: chọn theo hệ sinh thái

| Tiêu chí | SAML 2.0 | OIDC |
|---|---|---|
| Format | XML assertion | JWT ID Token; access token theo profile/issuer |
| Mô hình phổ biến | Enterprise browser SSO, ứng dụng cũ | Web, mobile, API, modern application |
| Client integration | Redirect/POST binding, metadata và certificate | Authorization endpoint, token endpoint, JWKS/discovery |
| Claims | Attributes trong assertion | Claims trong ID/access token hoặc userinfo |
| API authorization | Thường kết hợp cơ chế khác | OAuth access token/scopes thường được dùng |
| Vòng đời key | Signing certificate/metadata rollover | JWKS signing key rotation |

Hai giao thức không thay thế mọi chức năng của nhau và có thể cùng tồn tại. Chọn dựa trên IdP, ứng dụng, yêu cầu B2B và hỗ trợ nền tảng; tránh tự xây protocol parser nếu có thư viện/SDK được duy trì.

## 5. Federation trust: xác minh đúng bên phát hành

Federation chỉ an toàn khi relying party kiểm tra đúng nguồn phát hành và đúng mục tiêu sử dụng token/assertion.

### 5.1. Những thông tin cần ràng buộc

- **Issuer:** IdP nào phát hành assertion/token?
- **Subject:** principal nào được nhận diện? Có ổn định và duy nhất trong issuer không?
- **Audience:** assertion/token dành cho ứng dụng/API nào?
- **Signature/key:** chữ ký hợp lệ theo key và thuật toán được phép?
- **Validity:** token/assertion chưa hết hạn, chưa ở ngoài cửa sổ thời gian hiệu lực?
- **Nonce/state/request correlation:** response có gắn đúng auth request không?
- **Tenant/domain:** principal thuộc tổ chức/tenant nào?
- **Authentication context:** MFA hoặc assurance level có đạt yêu cầu?

Không ánh xạ role chỉ dựa trên email domain nếu domain chưa được quản trị và xác minh. Không mặc định mọi claim do IdP phát đều có cùng độ tin cậy; phải thiết lập claim contract và kiểm tra mapping khi group/attribute thay đổi.

### 5.2. Rollover signing key

IdP có thể xoay signing certificate hoặc JWKS key. Ứng dụng cần tin cậy endpoint metadata/JWKS qua cấu hình issuer chính thức; cache key với TTL hợp lý và refresh khi gặp key ID mới theo quy trình an toàn; hỗ trợ overlap key cũ/mới trong giai đoạn rollover; cảnh báo khi signature verification thất bại tăng bất thường; không chấp nhận thuật toán yếu hoặc để token tự chọn thuật toán ngoài allowlist.

Không tải key từ URL tùy ý do token gửi lên. Key discovery phải gắn với issuer đã cấu hình và trust anchor.

## 6. Provisioning và deprovisioning: SCIM và lifecycle

SSO chỉ xác thực người dùng; nó không tự bảo đảm user đã có account trong từng ứng dụng, thuộc group nào hoặc cần được thu hồi quyền khi nghỉ việc.

**SCIM (System for Cross-domain Identity Management)** là giao thức provisioning phổ biến để tự động tạo, cập nhật và vô hiệu hóa user/group giữa IdP hoặc identity governance system với ứng dụng.

| Hoạt động | Mục tiêu |
|---|---|
| Create | Tạo tài khoản khi nhân sự được cấp quyền sử dụng ứng dụng |
| Update | Đồng bộ tên, trạng thái, group hoặc attribute cần thiết |
| Deactivate | Vô hiệu hóa account khi nghỉ việc/không còn đủ điều kiện |
| Group membership | Đồng bộ group phục vụ role mapping |
| Reconciliation | Phát hiện account lệch giữa nguồn identity và ứng dụng |

### 6.1. Vòng đời nhân sự

~~~mermaid
flowchart TD
    Hire["Joiner: được tuyển / onboard"] --> Provision["Provision account + baseline access"]
    Provision --> Change["Mover: đổi team / nhiệm vụ"]
    Change --> Reevaluate["Recalculate groups and roles"]
    Reevaluate --> Active["Active access"]
    Active --> Leave["Leaver / contract ends"]
    Leave --> Disable["Disable identity and revoke sessions"]
    Disable --> Remove["Remove group grants / credentials"]
    Remove --> Audit["Verify deprovisioning and retain audit"]
~~~

Khi nhân sự rời tổ chức, cần disable account và revoke/expire session/token theo khả năng; xóa group membership và role assignment; thu hồi access key, certificate, SSH key, PAT, OAuth grant và credential phụ; chuyển ownership của resource/repository/job/service; vô hiệu hóa account local hoặc emergency account theo quy trình; kiểm tra service account hoặc secret người đó quản lý; giữ audit evidence nhưng không giữ quyền đăng nhập không cần thiết.

Token đã phát trước khi user bị vô hiệu hóa có thể còn hiệu lực đến khi hết hạn nếu resource server không có cơ chế revocation/introspection. Do đó cần access token ngắn hạn, session revocation và policy phù hợp mức rủi ro.

### 6.2. SCIM không phải authorization engine

SCIM đồng bộ user/group và trạng thái tài khoản; nó không tự quyết định mọi action trên cloud resource. Group được đồng bộ cần được ánh xạ sang role/policy có review. Nếu một group IdP bị gán nhầm vào role Administrator, provisioning sẽ tự động lan truyền quyền quá rộng.

## 7. RBAC: quyền theo vai trò

Role-Based Access Control (RBAC) gom một tập permission thành vai trò để cấp quyền nhất quán theo nhiệm vụ.

| Role | Phạm vi thường gặp | Không mặc định có quyền |
|---|---|---|
| viewer | Xem resource/configuration trong project được giao | Create, update, delete |
| developer | Deploy ứng dụng vào non-production | Thay IAM, đọc production secret |
| data-operator | Chạy pipeline và xem log dataset được giao | Quản trị account hoặc sửa policy |
| security-auditor | Đọc audit/config posture | Thay đổi resource |
| production-operator | Thực hiện operation đã định nghĩa trong production | IAM administration toàn account |
| platform-admin | Quản trị platform theo trách nhiệm | Quyền đặc quyền thường trực không giới hạn |

Role nên gắn với nhiệm vụ, có owner và phạm vi resource cụ thể. Tránh role tích tụ quyền qua nhiều năm mà không có review.

### 7.1. Role explosion

Nếu tạo một role cho mọi tổ hợp team × environment × action × region, số lượng role có thể tăng nhanh. Có thể giảm bằng role theo chức năng rõ ràng; group/attribute để xác định phạm vi; resource hierarchy và policy kế thừa; permission set template có tham số environment/project; role ngắn hạn cho tác vụ đặc quyền.

Không gộp mọi người cùng phòng ban vào một role nếu nhiệm vụ thực tế khác nhau. Đơn giản hóa cần giữ đúng separation of duties.

## 8. ABAC: quyền theo thuộc tính và ngữ cảnh

Attribute-Based Access Control (ABAC) đánh giá thuộc tính của subject, resource, action và environment để quyết định truy cập.

Ví dụ thuộc tính:

- Subject: department, team, employmentType, clearance, tenantId.
- Resource: ownerTeam, environment, dataClassification, projectId.
- Action: read, deploy, delete, rotate-secret.
- Environment: device posture, source network, time, approval ID, risk level.

~~~text
ALLOW deploy IF
  subject.team == resource.ownerTeam
  AND resource.environment == "staging"
  AND action == "deploy"
  AND session.mfa == true
~~~

ABAC hữu ích khi quyền phụ thuộc nhiều thuộc tính thay đổi thường xuyên. Nhưng attribute phải có nguồn đáng tin, schema rõ, giá trị được xác thực và có quy trình cập nhật. Không để client tự gửi department=security rồi dùng làm căn cứ cấp quyền.

### 8.1. Kết hợp RBAC và ABAC

RBAC có thể xác định nhóm vai trò; ABAC giới hạn phạm vi. Ví dụ chỉ user có role developer mới được deploy, và chỉ deploy resource thuộc team của họ trong staging. Kết hợp hai mô hình giúp policy dễ quản lý hơn so với tạo một role cho mọi tổ hợp.

## 9. Least privilege: giới hạn quyền theo action, resource và điều kiện

Least privilege không chỉ là “không cấp Administrator”. Cần giới hạn theo nhiều chiều:

1. **Action:** chỉ cho phép API/action cần thiết, không cấp wildcard nếu không cần.
2. **Resource:** chỉ đúng bucket, queue, database, secret, project hoặc environment.
3. **Condition:** giới hạn tenant, tag, network, MFA, source identity hoặc approval.
4. **Duration:** dùng session ngắn hạn và JIT elevation thay cho quyền thường trực.
5. **Data scope:** chỉ đọc field/dataset cần; masking hoặc row-level/column-level security.
6. **Delegation:** service chỉ được assume role tiếp theo theo trust policy giới hạn.
7. **Separation of duties:** người request, approve và execute tác vụ nhạy cảm có thể phải tách biệt.

### 9.1. Ví dụ policy tối thiểu

~~~json
{
  "version": "2026-01-01",
  "statement": [
    {
      "effect": "allow",
      "actions": ["object:Get"],
      "resources": ["bucket/booking-reports/staging/*"],
      "conditions": {
        "principalTeam": "analytics",
        "environment": "staging"
      }
    }
  ]
}
~~~

Đây là policy minh họa trung lập, không phải JSON policy dùng trực tiếp cho provider cụ thể. Trong production cần kiểm tra default deny, explicit deny, resource policy, boundary và cách wildcard được diễn giải.

### 9.2. Default deny và explicit deny

Nguyên tắc phổ biến là mặc định không cấp quyền nếu không có allow rõ ràng. Một số IAM engine có explicit deny ưu tiên hơn allow; một số mô hình có policy boundary, organization guardrail hoặc permission ceiling. Phải hiểu đúng cách kết hợp policy của nhà cung cấp.

Không giả định hai allow policy luôn hợp lại thành quyền hợp lệ nếu còn boundary hoặc deny ở tầng khác.

## 10. Quyền tạm thời và Just-in-Time access

Một developer có thể cần quyền production để xử lý incident nhưng không cần giữ quyền đó cả năm. **Just-in-Time (JIT) access** cấp quyền trong thời gian ngắn sau khi đáp ứng điều kiện như ticket, approval, MFA và lý do truy cập.

~~~mermaid
sequenceDiagram
    participant E as Engineer
    participant G as Access governance
    participant A as Approver
    participant IAM as IAM / Cloud STS
    E->>G: Request role + resource + duration + ticket
    G->>G: Check eligibility and policy
    G->>A: Approval request if required
    A-->>G: Approve / deny
    G->>IAM: Grant eligible short-lived session
    IAM-->>E: Temporary credentials
    E->>IAM: Perform approved action
    IAM->>IAM: Session expires / revoke
    G->>G: Audit and review activity
~~~

JIT giảm quyền thường trực nhưng quy trình phải có role được phép xin và resource scope rõ; thời lượng tối đa, lý do và ticket/incident reference; MFA hoặc authentication assurance phù hợp; approval và separation of duties; session log/recording nếu công cụ hỗ trợ; expiration tự động, thu hồi khi hoàn tất và audit.

Emergency/break-glass access cần được bảo vệ riêng, alert ngay khi sử dụng, kiểm tra sau sự kiện và diễn tập định kỳ. Không để break-glass trở thành con đường bỏ qua mọi kiểm soát hằng ngày.

## 11. Cross-account và delegated access

Cloud environment thường chia nhiều account/project/subscription để tách production, staging, security, data và sandbox. Federation cho phép user hoặc workload ở một account assume role ở account khác nếu trust policy cho phép.

### 11.1. Hai phía của assume role

Để một principal assume role:

1. Principal nguồn phải có permission gọi hành động assume/delegate.
2. Target role phải trust đúng source principal hoặc federation identity.
3. Session policy/boundary có thể thu hẹp permission hiệu lực.
4. Resource policy và organization guardrail vẫn áp dụng.
5. Session phải có source identity/audit để truy vết.

Trust policy và permission policy là hai thứ khác nhau. Trust policy trả lời “ai được assume role này?”; permission policy trả lời “sau khi assume, role được làm gì?”.

### 11.2. Tránh trust quá rộng

Tránh tin toàn bộ account/tenant hoặc wildcard principal nếu không có condition đủ hẹp. Giới hạn theo exact account/project/tenant; issuer/provider đã cấu hình; audience hoặc subject claim; repository/branch/environment của CI/CD; external ID cho mô hình partner role assumption khi giao thức/provider yêu cầu; session tags/source identity được kiểm soát.

Không để đối tác giả mạo subject claim của workload nội bộ hoặc assume role ngoài phạm vi hợp đồng.

## 12. Service-to-service identity và workload federation

Một pipeline CI/CD cần deploy vào cloud, hoặc function cần đọc object storage, không nhất thiết phải dùng access key dài hạn.

### 12.1. Workload identity federation

~~~mermaid
sequenceDiagram
    participant W as CI/CD workload
    participant O as OIDC issuer
    participant STS as Cloud Security Token Service
    participant R as Target resource
    W->>O: Request workload identity token
    O-->>W: Signed token (issuer, subject, audience)
    W->>STS: Exchange token under trust policy
    STS->>STS: Validate issuer, audience, subject, claims
    STS-->>W: Short-lived cloud session
    W->>R: Access with least-privilege role
~~~

Trust nên ràng buộc repository, branch, environment hoặc workload subject chính xác. Nếu chỉ tin issuer chung mà không giới hạn subject/audience, nhiều workload khác có thể lấy được role.

### 12.2. Managed identity

Managed identity cho phép compute service nhận danh tính do cloud platform quản lý. Ứng dụng lấy token từ runtime identity endpoint hoặc SDK; key rotation và credential lifecycle do nền tảng xử lý.

Dù vậy, managed identity vẫn cần role/resource policy. Việc bật identity không đồng nghĩa identity có quyền truy cập mọi resource trong subscription/account.

### 12.3. mTLS và service mesh

mTLS xác thực hai đầu kết nối ở lớp transport bằng certificate. Service mesh có thể cấp identity và xoay certificate tự động cho workload. Tuy nhiên certificate xác thực peer trong trust domain; application authorization vẫn phải quyết định peer được phép gọi endpoint/action nào.

Không dùng subject CN hoặc SAN tự do làm bằng chứng quyền nếu không có mapping identity được kiểm soát.

## 13. Session management, MFA và điều kiện truy cập

SSO tạo trải nghiệm đăng nhập tập trung nhưng mỗi ứng dụng có session riêng. Cần thiết kế:

- **Session lifetime:** thời gian tối đa của phiên.
- **Idle timeout:** hết phiên khi không hoạt động.
- **Reauthentication:** yêu cầu xác thực lại cho action nhạy cảm.
- **MFA / phishing-resistant authentication:** yêu cầu nhiều yếu tố hoặc passkey/security key theo rủi ro.
- **Device posture:** chỉ cho phép thiết bị đáp ứng policy.
- **Risk-based access:** phát hiện vị trí/thiết bị/behavior bất thường.
- **Token audience/scope:** ngăn dùng token ở API ngoài mục đích.
- **Logout/revocation:** xử lý session tại ứng dụng và IdP; hiểu giới hạn propagation.

MFA tại IdP không tự bảo đảm mọi access token downstream đều giữ được assurance context. Nếu thao tác yêu cầu MFA gần đây, ứng dụng cần kiểm tra claim/authentication context hoặc yêu cầu step-up authentication theo giao thức.

### 13.1. Session không nên sống vô hạn

Session dài giúp giảm số lần đăng nhập nhưng tăng thời gian attacker sử dụng session bị chiếm đoạt. Có thể dùng access token ngắn hạn, refresh/session policy theo risk, reauthentication cho quyền đặc biệt và revoke khi identity bị disable.

## 14. Phân tách nhiệm vụ và quản trị quyền đặc quyền

Một số hành động không nên do cùng một principal request, approve và execute:

| Tác vụ | Phân tách gợi ý |
|---|---|
| Thay IAM trust policy production | Người đề xuất + reviewer/security approver |
| Xóa backup hoặc dữ liệu có retention lock | Data owner + approver có thẩm quyền |
| Cấp quyền admin tạm thời | Requester + approver khác + audit |
| Phát hành signing key/certificate | Owner hệ thống + key custodian |
| Deploy thay đổi policy ở production | Pull request review + pipeline identity riêng |

Quyền break-glass hoặc super-admin phải có danh sách người được phép, bảo vệ MFA/phishing-resistant, cảnh báo và access review riêng. Không cấp quyền rộng thường trực chỉ để tránh quy trình approval chậm.

## 15. Access review và quyền không còn cần thiết

Quyền tối thiểu cần được duy trì liên tục vì team, workload và resource thay đổi.

Một access review nên kiểm tra:

- User/group/role nào có quyền trên resource nào?
- Quyền có owner và business justification không?
- Last-used activity có còn cần thiết? (Không dùng không đồng nghĩa tự động xóa nếu đó là quyền phục hồi/DR.)
- Role có chứa wildcard hoặc quyền nhạy cảm ngoài nhiệm vụ không?
- Service account có credential cũ, owner rời tổ chức hoặc scope quá rộng không?
- Federated trust có issuer/subject không còn dùng không?
- Permission có được cấp qua nhiều đường (group, direct grant, resource policy) không?
- Quyền tạm thời đã hết hạn và được revoke chưa?

### 15.1. Quy trình review

1. Export inventory identity, group, role, resource policy và credential.
2. Gom quyền hiệu lực theo principal, kể cả indirect grants.
3. Gửi owner xác nhận mục đích và phạm vi.
4. Xác định quyền thừa, orphaned identity, stale access key và trust cũ.
5. Approve thay đổi/thu hồi theo workflow.
6. Thực hiện với rollback plan phù hợp.
7. Xác minh effective permissions sau thay đổi.
8. Lưu kết quả review, exception, approver và ngày review tiếp theo.

Không chỉ xem policy JSON; cần kiểm tra quyền hiệu lực sau khi các policy, group, boundary và resource policy được kết hợp.

## 16. Audit, detection và incident response

Các sự kiện identity quan trọng gồm sign-in success/failure, MFA challenge và step-up; user/group created/updated/disabled/removed; role assignment/grant/revoke và permission policy change; role assumption/token issuance/session creation; secret/access key/certificate create/rotate/delete; sử dụng quyền đặc quyền; thay đổi trust relationship; access denied bất thường; break-glass usage.

Log cần có principal, issuer, subject/source identity, target role, resource, action, decision, timestamp, request/session ID và context cần thiết. Tránh ghi access token, refresh token, private key, password hoặc secret.

### 16.1. Cảnh báo có giá trị

- Một workload assume role từ repository/branch/environment ngoài allowlist.
- Quyền admin được cấp ngoài JIT approval.
- Một principal đột ngột truy cập nhiều resource nhạy cảm.
- Identity bị disable nhưng vẫn có session/credential activity.
- Trust policy hoặc federation metadata thay đổi ngoài quy trình.
- Service account không có owner hoặc access key không được rotate theo policy.
- Nhiều lần assume role thất bại hoặc token audience không khớp.

Alert phải gắn owner/runbook; một số access denied là bình thường. Cần correlation với change ticket, baseline và risk context để giảm false positive.

## 17. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách cải thiện |
|---|---|---|
| Cho rằng SSO đồng nghĩa least privilege | Người dùng đăng nhập một lần có thể nhận quyền quá rộng | Map group/role theo nhiệm vụ và resource scope |
| Dùng email làm principal bất biến | Email đổi hoặc được tái sử dụng gây ánh xạ sai | Dùng stable subject/object ID trong issuer namespace |
| Chỉ cấu hình SAML/OIDC mà không provisioning | User nghỉ việc vẫn còn local account/quyền | SCIM hoặc deprovision workflow và reconciliation |
| SCIM group được map thẳng thành admin không review | Sai group membership lan truyền quyền cao | Approval, mapping policy và access review |
| Dùng access key dài hạn cho workload | Credential lộ có thể dùng lâu | Managed identity/workload federation/short-lived token |
| Trust toàn bộ account/issuer | Principal ngoài phạm vi có thể assume role | Giới hạn subject, audience, tenant và condition |
| Nhầm trust policy với permission policy | Principal được assume role nhưng quyền quá rộng | Review hai phía độc lập |
| Cấp role admin thường trực | Tăng blast radius khi account bị chiếm | JIT, short session, MFA và separation of duties |
| Chỉ kiểm tra role, bỏ qua resource scope | Có thể truy cập resource của team/tenant khác | RBAC kết hợp ABAC/resource policy |
| Không revoke session khi offboarding | Token/session cũ còn dùng được | Disable, revoke, short TTL và kiểm tra downstream |
| Tự xây SAML/OIDC parser | Lỗi xác minh signature/claim/replay | Dùng thư viện/SDK được duy trì và cấu hình đúng |
| Chỉ audit sign-in | Không thấy ai assume role hay thay policy | Audit cả provisioning, authorization và privileged action |

## 18. Case study: SSO cho nhiều cloud account

**Bối cảnh:** một nền tảng đặt phòng có ba môi trường cloud: development, staging và production. Nhân viên đăng nhập qua enterprise IdP; CI/CD deploy ứng dụng; data pipeline đọc một số dataset; security team cần audit; đối tác có workload gửi báo cáo định kỳ.

### 18.1. Identity architecture

~~~mermaid
flowchart TD
    HR["HR / Identity governance"] --> IdP["Enterprise IdP"]
    IdP --> SSO["SAML / OIDC SSO"]
    SSO --> Dev["Development account"]
    SSO --> Stage["Staging account"]
    SSO --> Prod["Production account"]
    CI["CI/CD OIDC identity"] --> STS["Cloud STS / federation"]
    STS --> DeployRole["Short-lived deploy role"]
    DeployRole --> Stage
    DeployRole --> Prod
    DataJob["Data pipeline identity"] --> DataRole["Dataset-scoped role"]
    DataRole --> Lake["Approved data locations"]
    Partner["Partner identity"] --> PartnerRole["Partner-specific role"]
    PartnerRole --> Reports["Report ingestion endpoint"]
    Dev --> Audit["Central identity / cloud audit"]
    Stage --> Audit
    Prod --> Audit
~~~

### 18.2. Workforce access

- Enterprise IdP xác thực nhân viên bằng SSO, MFA theo risk và device policy.
- Group được provisioning qua SCIM; group chỉ map sang permission set đã được phê duyệt.
- Developer có quyền rộng hơn ở development, quyền deploy hạn chế ở staging.
- Production operator dùng JIT role có ticket, MFA và thời lượng ngắn.
- Security auditor có quyền đọc audit/config posture nhưng không sửa production.
- Khi nhân viên rời công ty, identity bị disable, session revoke và các direct grants/keys liên quan được rà soát.

### 18.3. Workload access

- CI/CD dùng OIDC federation, trust policy ràng buộc repository, protected branch và deployment environment.
- Deploy role chỉ được cập nhật đúng service/resource và environment; không có quyền IAM admin mặc định.
- Data pipeline có workload identity riêng, chỉ đọc dataset được giao và ghi output vào prefix/path đã định.
- Partner dùng principal riêng và role giới hạn tới report ingestion; không có quyền truy cập cloud console.
- Credential của workload ngắn hạn; không lưu cloud access key dài hạn trong repository.

### 18.4. Authorization và audit

| Principal | Quyền | Guardrail |
|---|---|---|
| Developer | Deploy staging | Team/project ownership, protected pipeline, short session |
| Production operator | Thao tác production theo runbook | JIT, ticket, MFA, approval, audit |
| Security auditor | Read-only security/audit | Không sửa policy hoặc resource |
| CI/CD workload | Deploy artifact vào service cụ thể | Issuer/subject/audience, branch/environment trust |
| Data pipeline | Read dataset A, write curated prefix B | Dataset scope, encryption, audit |
| Partner workload | Upload report vào endpoint/prefix riêng | Partner identity, quota, schema validation |

### 18.5. Tiêu chí nghiệm thu

- Nhân viên đăng nhập qua SSO và không cần tài khoản console dùng chung.
- Leaver bị deprovision đúng SLA và session/credential liên quan được thu hồi.
- CI/CD chỉ assume role từ repository/branch/environment được phép.
- Production elevated access có JIT, approval, expiration và audit.
- Data workload không đọc được dataset ngoài phạm vi.
- Partner không thể truy cập cloud console hoặc dữ liệu của partner khác.
- Access review xác định được quyền trực tiếp, group-derived và role-assumed.

## 19. Kiểm thử federation và least privilege

| Test | Cách kiểm tra | Kết quả mong muốn |
|---|---|---|
| Wrong issuer | Token/assertion từ IdP không tin cậy | Reject |
| Wrong audience | Token dành cho ứng dụng khác | Reject |
| Expired assertion/token | Dùng token hết hạn | Reject |
| Invalid signature | Thay đổi payload hoặc dùng key không tin cậy | Reject |
| Replay | Gửi lại assertion/response đã dùng | Reject theo replay protection |
| Wrong subject/tenant | Workload ngoài allowlist assume role | Deny |
| Excessive role | Developer thử action admin ngoài nhiệm vụ | Deny |
| Resource boundary | Team A truy cập resource Team B | Deny |
| Offboarding | Disable user và thử dùng session/credential cũ | Revoke/expire theo policy |
| JIT expiration | Gọi lại resource sau khi role hết hạn | Deny |
| SCIM deprovision | Disable user tại nguồn | Account downstream bị disable theo SLA |
| Key rollover | IdP xoay signing key | Hệ thống chấp nhận key mới hợp lệ và từ chối key không tin cậy |
| Workload token | Token có audience/subject sai | STS không cấp session |
| Audit coverage | Assume role, grant/revoke, break-glass | Log đủ principal, target, action và thời điểm |

Kiểm thử policy cần dùng principal giả lập và môi trường thử nghiệm. Không thử privilege escalation trên production ngoài phạm vi được phê duyệt.

## 20. Checklist review kiến trúc danh tính

### Federation và SSO

- [ ] Chọn SAML/OIDC theo hệ sinh thái và use case.
- [ ] Issuer, subject, audience, signature, validity và replay được xác minh.
- [ ] Signing key rollover và metadata/JWKS refresh có quy trình.
- [ ] MFA/step-up, session lifetime, idle timeout và logout/revocation được xác định.
- [ ] Customer, workforce, partner và workload identity được phân biệt.

### Provisioning và lifecycle

- [ ] Joiner/mover/leaver có owner và SLA.
- [ ] SCIM/group sync có mapping được review và reconciliation.
- [ ] Offboarding bao gồm local account, API key, certificate, token, OAuth grant và service ownership.
- [ ] Access review có tần suất, approver và evidence.
- [ ] JIT/break-glass có expiration, approval, alert và audit.

### Least privilege và trust

- [ ] Mọi principal có purpose/owner và quyền tối thiểu theo action/resource.
- [ ] RBAC/ABAC sử dụng claim/attribute từ nguồn đáng tin.
- [ ] Default deny, explicit deny, boundary và organization guardrail được hiểu đúng.
- [ ] Trust policy tách khỏi permission policy và giới hạn issuer/subject/audience.
- [ ] Cross-account delegation có session duration/source identity phù hợp.
- [ ] Workload ưu tiên managed identity/federation và short-lived credentials.

### Audit và vận hành

- [ ] Ghi nhận sign-in, provisioning, role assumption, policy change và privileged action.
- [ ] Không log token, password, private key hoặc secret.
- [ ] Có alert cho trust change, privilege escalation và identity activity bất thường.
- [ ] Có runbook revoke credential, disable identity và xử lý account compromise.
- [ ] Đã kiểm thử positive/negative authorization và offboarding end-to-end.

## 21. Bài tập thực hành

**Bối cảnh:** công ty vận hành nền tảng đặt phòng có 120 nhân viên, 4 team engineering, 2 team dữ liệu, đội hỗ trợ và hai đối tác tích hợp. Hệ thống có ba cloud account: dev, staging và production. Một CI pipeline hiện dùng access key tĩnh có quyền Administrator để deploy; nhân viên đăng nhập console bằng tài khoản riêng; quyền của nhân viên cũ đôi khi chưa bị gỡ khỏi database console.

Hãy thiết kế lại:

1. Vẽ trust architecture cho workforce SSO, partner federation và workload identity.
2. Chọn SAML/OIDC cho console/web app và mô tả issuer/audience/subject validation.
3. Xác định SCIM/group lifecycle và quy trình joiner/mover/leaver.
4. Thiết kế role cho developer, data engineer, support, auditor và production operator.
5. Kết hợp RBAC/ABAC để giới hạn team, project, environment và dataset.
6. Thay static Administrator key của CI bằng workload federation; giới hạn repository/branch/environment và target resource.
7. Thiết kế JIT production access, approval, MFA, session duration và break-glass.
8. Viết trust policy concept và permission scope cho từng workload/partner.
9. Đề xuất access review, audit event và alert cho privilege escalation.
10. Xây dựng negative tests cho wrong issuer/audience, stale user, excessive permission và cross-team access.

**Gợi ý tự kiểm tra:** SSO không thu hồi quyền local đã được cấp trước đó; SCIM không thay authorization; role được assume phải có trust policy và permission policy riêng. Một CI token hợp lệ chỉ nên nhận session cho đúng repository/environment và quyền deploy cần thiết, không phải Administrator toàn account.

## 22. Ghi nhớ

Federation xác lập niềm tin giữa các hệ thống danh tính; SSO cho phép dùng phiên đăng nhập tập trung; provisioning quản lý vòng đời tài khoản; authorization quyết định hành động và resource được phép; least privilege giới hạn quyền theo nhiệm vụ, phạm vi, điều kiện và thời gian.

Một kiến trúc cloud đáng tin dùng SAML/OIDC đúng semantics, SCIM hoặc lifecycle workflow để thu hồi account, workload identity và credential ngắn hạn thay cho key tĩnh, RBAC/ABAC và trust policy có phạm vi hẹp, JIT cho quyền đặc quyền, cùng audit/access review liên tục. Chỉ khi danh tính, phiên, quyền và vòng đời được kiểm soát đồng thời, SSO mới giảm độ phức tạp mà không mở rộng blast radius.
