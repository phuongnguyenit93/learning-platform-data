# Federated cloud access

**Chương:** Cloud IAM  
**Bài học:** Federated cloud access  
**Ngữ cảnh:** Quản lý vòng đời danh tính trong Identity and Access Management (IAM), theo mô hình **Joiner–Mover–Leaver (JML)**; kết nối IdP, SSO, SCIM, RBAC/ABAC, danh tính workload, kiểm toán và giảm quyền truy cập tồn dư.

## 1. Federated cloud access là gì?

**Federated cloud access** (truy cập đám mây qua liên kết danh tính) cho phép một hệ thống cloud **tin cậy bằng chứng danh tính hoặc chứng thực do một hệ thống khác phát hành**, rồi sử dụng mối quan hệ tin cậy đó để xác định chủ thể và áp quyền truy cập. Người dùng hoặc workload có thể nhận phiên truy cập cloud thông qua nhà cung cấp danh tính (**Identity Provider – IdP**) hay một issuer được tin cậy, thay vì phải lưu mật khẩu hoặc khóa truy cập dài hạn riêng tại mỗi nơi.

Ví dụ:

- Nhân viên dùng tài khoản doanh nghiệp và xác thực đa yếu tố ở IdP để đăng nhập AWS console, sau đó nhận đúng vai trò được phê duyệt tại account sản xuất.
- Nhóm vận hành đăng nhập Microsoft Entra ID, được Azure RBAC xét quyền ở một subscription hoặc resource group.
- Đối tác dùng IdP bên ngoài để truy cập dự án Google Cloud qua một cơ chế workforce federation phù hợp.
- Pipeline CI/CD cung cấp một OIDC token mô tả workload và bối cảnh chạy; cloud xác thực token, kiểm tra trust, rồi phát credential ngắn hạn cho việc triển khai staging.

Các ví dụ đều có quan hệ tin cậy giữa những miền danh tính, nhưng **cách nhận diện chủ thể, ánh xạ quyền, loại token và vòng đời phiên truy cập không giống nhau**.

**Mục tiêu cốt lõi:** Xác thực danh tính tại nguồn đáng tin cậy, cấp quyền đúng nơi sử dụng, và thu hồi quyền một cách kiểm chứng được khi con người hoặc workload thay đổi trạng thái.

### 1.1. Phân biệt federation, SSO, provisioning và authorization

| Khái niệm | Giải quyết vấn đề | Điều không tự bảo đảm |
| --- | --- | --- |
| **Federation** | Thiết lập niềm tin giữa IdP/issuer và cloud relying party/service | Không bảo đảm quyền luôn tối thiểu hoặc đã được thu hồi |
| **Single Sign-On (SSO)** | Người dùng đăng nhập một lần rồi truy cập nhiều ứng dụng theo chính sách | Không đồng nghĩa mọi ứng dụng có chung vòng đời account |
| **SAML/OIDC** | Giao thức và cấu trúc bằng chứng danh tính/đăng nhập cho federation | Không tự quy định toàn bộ IAM permissions trên tài nguyên |
| **OAuth 2.0** | Khung ủy quyền để client nhận access token cho resource server | OAuth 2.0 tự nó không phải giao thức đăng nhập danh tính hoàn chỉnh |
| **SCIM/provisioning API** | Tạo, cập nhật, vô hiệu hóa user/group tại hệ thống hỗ trợ | Không tự hủy session và không phải API chung để gán mọi cloud role |
| **RBAC/ABAC và cloud IAM** | Kiểm tra principal được thực hiện action nào trên resource nào | Không tự suy ra trạng thái nhân sự nếu không có kết nối và kiểm soát phù hợp |
| **JML/IGA** | Điều phối quyền theo vòng đời, phê duyệt, đối soát, chứng cứ | Không thay thế bộ máy xác thực hoặc phân quyền của cloud |

Điểm dễ nhầm: **đăng nhập thành công chưa chắc có quyền truy cập**, và **khóa tài khoản ở IdP chưa chắc vô hiệu hóa ngay mọi token, phiên hoặc khóa cloud đã cấp**.

## 2. Những vai trò và ranh giới tin cậy trong kiến trúc

| Thành phần | Chức năng | Ví dụ |
| --- | --- | --- |
| **Nguồn dữ liệu có thẩm quyền** | Quyết định một danh tính có hợp lệ, thuộc đơn vị nào và khi nào hết hiệu lực | HRIS, hệ thống quản lý nhà thầu, workload registry |
| **Identity Provider (IdP)** | Xác thực danh tính, quản lý thuộc tính, nhóm, yếu tố xác thực | IdP doanh nghiệp |
| **Issuer** | Ký và phát hành token/assertion được hệ thống đích kiểm tra | OIDC issuer của IdP hoặc CI/CD |
| **Relying Party (RP)/Service Provider (SP)** | Tiêu thụ bằng chứng danh tính, thiết lập session hoặc chọn principal | Ứng dụng cloud console hoặc dịch vụ federation |
| **Cloud IAM / Security Token Service** | Ánh xạ danh tính, áp trust, cấp phiên tạm thời và đánh giá quyền | AWS IAM/STS, Azure identity/RBAC, Google Cloud IAM |
| **Principal / Role** | Đại diện cho chủ thể hoặc quyền được gán/đảm nhận tại cloud | Người dùng liên kết, role session, service account |
| **IGA/lifecycle workflow** | Thực thi Joiner–Mover–Leaver và đối soát entitlement | Quy trình phê duyệt/thu hồi quyền |
| **Audit/SIEM** | Thu thập log xác thực, token exchange, cấp quyền và sử dụng API | Log IdP, cloud audit logs, SIEM |

Một danh tính người dùng không nhất thiết bằng một cloud principal duy nhất: một người có thể có quyền trên nhiều account/subscription/project, trong khi một phiên federation có thể ánh xạ người đó thành role session. Vì vậy hồ sơ JML cần liên hệ **định danh nguồn ổn định** với từng principal, role và entitlement ở cloud đích.

### 2.1. Kiến trúc federated access tổng quan

~~~mermaid
flowchart TD
    HR["HRIS / nguồn nhân sự<br/>Joiner - Mover - Leaver"] --> IGA["IGA / Identity Lifecycle<br/>Desired access + approval"]
    IGA --> IDP["IdP / Directory<br/>Users, groups, MFA"]
    IGA --> PROV["SCIM / provisioning API<br/>Cập nhật đích hỗ trợ"]
    IDP -->|"SAML / OIDC"| RP["Cloud federation / relying party<br/>Kiểm tra issuer, audience, chữ ký"]
    RP --> MAP["Ánh xạ principal và role<br/>Trust + scope + policy"]
    MAP --> CLOUD["Cloud APIs / Console<br/>Tài nguyên và dữ liệu"]
    REG["Workload registry<br/>Owner + repo + environment"] --> CI["Workload issuer / CI-CD<br/>OIDC token ngắn hạn"]
    CI --> RP
    PROV --> CLOUD
    IGA -.-> AUD["Log / SIEM / đối soát"]
    IDP -.-> AUD
    RP -.-> AUD
    CLOUD -.-> AUD
~~~

Đây là sơ đồ logic: một nhà cung cấp có thể gộp nhiều lớp, hoặc hỗ trợ các luồng khác nhau cho workforce và workload. **SCIM không có nghĩa là giao thức cung cấp credential cloud**, và federation không tự động tạo hoặc xóa mọi tài khoản đích.

### 2.2. Thiết lập quan hệ tin cậy

Một trust configuration phải trả lời:

1. **Tin ai?** Issuer/IdP/tenant nào, khóa ký nào và cách cập nhật khóa ra sao?
2. **Tin cho mục đích gì?** Token có audience/recipient đúng với dịch vụ tiêu thụ không?
3. **Tin chủ thể nào?** Định danh ổn định nào, nhóm/thuộc tính/claim nào được chấp nhận?
4. **Đổi lấy quyền nào?** Role, scope và entitlement thực tế tại cloud đích là gì?
5. **Tin trong bao lâu?** Token/assertion, phiên cloud và credential tạm thời có hiệu lực đến thời điểm nào?
6. **Ai chịu trách nhiệm?** Owner hai phía, quy trình đổi cấu hình, thu hồi và ứng phó sự cố?

Trust rộng hơn nhu cầu sẽ tạo rủi ro ngay cả khi phần còn lại của quy trình SSO hoạt động đúng. Ví dụ, trust cho phép bất kỳ repository trong một tổ chức CI/CD đều được nhận role deploy sẽ làm mở rộng tập workload có thể dùng role ngoài dự kiến.

## 3. Định danh, claim và cơ chế ánh xạ

Federation cần có cách xác định danh tính nguồn và liên kết với danh tính hoặc role đích:

- **Issuer:** Hệ thống phát token/assertion, nên được định danh chính xác.
- **Subject:** Định danh chủ thể do issuer quản lý; thường cần xét đồng thời cặp **issuer + subject**.
- **Audience / Recipient:** Đối tượng được nhận và tiêu thụ bằng chứng.
- **Groups/roles/attributes:** Dữ liệu được dùng để lựa chọn entitlement nếu được tin cậy.
- **Expiration/issued-at:** Giới hạn hiệu lực của bằng chứng.
- **Authentication context:** Cấp độ và phương thức xác thực được xác nhận theo giao thức/hệ thống.

**Không nên ghép danh tính chỉ dựa vào tên hiển thị hoặc địa chỉ email**. Email có thể đổi hoặc được tái sử dụng; dữ liệu từ issuer khác nhau có thể chứa cùng một email nhưng không phải cùng người. Việc liên kết cần một định danh bền vững, có namespace rõ ràng và một quy trình xác minh.

### 3.1. Bản đồ danh tính từ nguồn đến quyền đích

Ví dụ dữ liệu quản trị:

| Trường | Giá trị giả định | Mục đích |
| --- | --- | --- |
| Source identity ID | EMP-5172 | Liên kết với HRIS và sự kiện JML |
| Issuer | idp.company.example | Phân biệt nguồn định danh đáng tin cậy |
| Subject | directory-object-8c2 | Nhận diện người dùng trong issuer |
| Federation target | production-read-access | Quan hệ trust đã được quản trị |
| Cloud scope | Một AWS account production | Giới hạn phạm vi |
| Entitlement | IncidentReadOnly | Quyền được duyệt |
| Approver/owner | Platform Security / Service Owner | Trách nhiệm cấp và thu hồi |
| Effective dates | Theo hợp đồng và sự kiện | Thời điểm có hiệu lực của quyền |
| Last verified | Theo bản ghi đối soát | Bằng chứng trạng thái tại hệ thống đích |

Đối với **external user**, cần thêm sponsor nội bộ, tổ chức đối tác, mục đích truy cập và ngày hết hạn; không nên phụ thuộc vào việc đối tác tự báo khi nhân sự rời đi.

## 4. SAML 2.0 trong federation cho người dùng

**Security Assertion Markup Language (SAML) 2.0** thường được dùng cho SSO giữa IdP doanh nghiệp và ứng dụng/cloud console. Sau khi xác thực người dùng, IdP phát **SAML assertion**, trong đó có subject và các thuộc tính/điều kiện liên quan. Service Provider (SP) xác minh assertion và thiết lập session hoặc ánh xạ đến role thích hợp.

### 4.1. Luồng SAML ở mức khái niệm

~~~mermaid
sequenceDiagram
    participant U as Người dùng
    participant SP as Cloud Service Provider
    participant ID as Corporate IdP
    participant IAM as Cloud IAM / Role mapping
    U->>SP: Mở console
    SP-->>U: Chuyển hướng đến IdP
    U->>ID: Xác thực + MFA theo policy
    ID-->>U: SAML response/assertion
    U->>SP: Gửi assertion qua trình duyệt
    SP->>SP: Kiểm tra chữ ký, issuer, recipient, audience, thời hạn
    SP->>IAM: Ánh xạ subject/nhóm thành quyền được duyệt
    IAM-->>SP: Principal/role/session phù hợp
    SP-->>U: Truy cập cloud console theo quyền
~~~

Sơ đồ minh họa một luồng **SP-initiated**; hệ thống có thể hỗ trợ **IdP-initiated** hoặc cách trao đổi khác. Mức độ hỗ trợ và các bước cụ thể phải theo tài liệu của IdP và cloud target.

### 4.2. Những kiểm tra SAML quan trọng

**Chữ ký:** Xác minh chữ ký XML theo cấu hình IdP tin cậy; bảo đảm dữ liệu đã xác minh chính là dữ liệu được sử dụng để xác thực/ánh xạ quyền. Không chỉ kiểm tra rằng tài liệu “có chứa” chữ ký.

**Issuer:** Assertion phải đến từ IdP được cấu hình cho quan hệ tin cậy đó.

**Audience, Destination, Recipient:** Bằng chứng chỉ được nhận tại SP/dịch vụ dự kiến; tránh dùng nhầm assertion dành cho ứng dụng khác.

**Thời gian:** Kiểm tra điều kiện hiệu lực, NotBefore và NotOnOrAfter (khi có), lệch đồng hồ hợp lý và thời gian sống ngắn phù hợp.

**InResponseTo và chống phát lại:** Khi dùng request/response correlation, SP cần kiểm tra tương quan; nơi phù hợp cần cơ chế phát hiện assertion cũ hoặc dùng lại.

**Subject và role mapping:** NameID/attribute cần được quản trị, không cấp role đặc quyền chỉ vì một chuỗi thuộc tính do nguồn không đáng tin cậy cung cấp.

**Chuyển đổi chứng thư:** Khi IdP đổi chứng thư ký, cần cập nhật metadata/trust theo quy trình được duyệt để tránh gián đoạn đăng nhập hoặc chấp nhận issuer không hợp lệ.

### 4.3. SAML không tự giải quyết deprovisioning

Một IdP có thể từ chối phát assertion mới sau khi tài khoản bị disable, nhưng session cloud đã tạo trước đó có thể tiếp tục đến khi hết hạn hoặc bị thu hồi theo cơ chế đích. Vì vậy **Leaver** phải kiểm tra cả quyền đã gán, tài khoản cloud-local, credential và các session có liên quan.

## 5. OIDC và OAuth 2.0 trong federation

**OpenID Connect (OIDC)** là lớp danh tính xây dựng trên OAuth 2.0. OIDC cung cấp cách client xác nhận sự kiện đăng nhập và nhận **ID token**, thường là JWT, từ một issuer. **OAuth 2.0 access token** lại phục vụ yêu cầu truy cập resource server theo quyền được cấp.

Không được dùng **ID token thay cho access token** trong API vốn yêu cầu access token. Token phải được kiểm tra theo mục đích của nó, với **issuer, audience, thời hạn, chữ ký, subject và các yêu cầu của luồng/giao thức**.

### 5.1. Những thành phần thường thấy ở JWT

Ví dụ payload minh họa (không phải token thực, không có chữ ký):

~~~json
{
  "iss": "https://issuer.example.org",
  "sub": "repo:example-org/learning-api:environment:staging",
  "aud": "cloud-token-exchange",
  "iat": 1795420800,
  "exp": 1795421400,
  "repository": "example-org/learning-api",
  "environment": "staging"
}
~~~

Các tên claim ngoài nhóm chuẩn phụ thuộc issuer. **Một JSON payload có thể được đọc hoặc tự tạo rất dễ dàng; chỉ token được ký hợp lệ, phát bởi issuer tin cậy, dành cho đúng audience, còn hạn và thỏa mọi điều kiện mới có thể dùng**. Không xác thực bằng cách giải mã base64 payload rồi tin ngay nội dung claim.

### 5.2. Xác thực OIDC token đúng mục đích

- Cấu hình issuer/metadata và JWKS (khóa công khai ký token) đúng nguồn, quản lý việc xoay khóa.
- Kiểm tra chữ ký bằng thuật toán được cấu hình hoặc cho phép; không chấp nhận thuật toán ngoài dự kiến.
- Kiểm tra issuer và audience đúng dịch vụ nhận token.
- Kiểm tra thời hạn, thời điểm chưa có hiệu lực khi áp dụng và độ lệch đồng hồ hợp lý.
- Kiểm tra subject/claims có định dạng và giá trị chính xác theo chính sách trust.
- Kiểm tra yêu cầu chống CSRF, replay và correlation tùy luồng, chẳng hạn state/nonce cho đăng nhập OIDC thích hợp.
- Bảo vệ token khi truyền, lưu và ghi log; tránh ghi nguyên bearer token vào telemetry.

**OIDC federation cho workload** thường sử dụng JWT về danh tính workload nhằm đổi lấy **credential cloud tạm thời**; đó là luồng có tính chất khác người dùng đăng nhập tương tác vào web app.

### 5.3. Ví dụ workload token exchange

~~~mermaid
sequenceDiagram
    participant P as CI/CD Pipeline
    participant I as CI OIDC Issuer
    participant STS as Cloud Federation / STS
    participant IAM as Cloud IAM
    participant API as Cloud API
    P->>I: Yêu cầu OIDC token cho job
    I-->>P: Token ký, có subject/audience/thời hạn
    P->>STS: Gửi token để đổi lấy quyền
    STS->>STS: Kiểm tra issuer, chữ ký, aud, sub, exp
    STS->>IAM: Kiểm tra trust và quyền role/principal
    IAM-->>STS: Được phép theo điều kiện
    STS-->>P: Credential tạm thời
    P->>API: Gọi API triển khai staging
    API->>IAM: Đánh giá quyền trên resource
    IAM-->>API: Cho phép hoặc từ chối
    API-->>P: Kết quả thao tác
~~~

Việc chứng minh token thuộc một pipeline không có nghĩa pipeline được phép gọi mọi API: **trust cho phép đổi danh tính, permissions quyết định khả năng thực thi sau đó**.

## 6. Federation cho workforce và workload có gì khác?

| Chiều so sánh | Workforce federation | Workload federation |
| --- | --- | --- |
| Chủ thể | Nhân viên, đối tác, nhà thầu, quản trị viên | Ứng dụng, container, VM, job, CI/CD |
| Nguồn gốc danh tính | HRIS/đối tác, IdP, directory | Workload registry, nền tảng chạy, CI issuer |
| Bằng chứng chính | SAML assertion, OIDC token, phiên đăng nhập tương tác | OIDC token nền tảng, workload attestation hoặc cơ chế liên kết hỗ trợ |
| Kiểm soát xác thực | MFA, quản lý thiết bị, chính sách rủi ro | Ràng buộc issuer, repository, branch, environment, identity của runtime |
| Cấp quyền | Nhóm, role, assignment, permission set | Managed identity, role, service account, workload principal |
| Vòng đời | Nhận việc, đổi đội/vai trò, nghỉ việc | Tạo service, chuyển môi trường/owner, ngừng pipeline/workload |
| Rủi ro | Session cũ, tài khoản khách, quyền trực tiếp | Trust rộng, key tĩnh, job không owner, pipeline bị sửa |
| Bằng chứng | IdP event, JML event, role/scope, audit log | Build/job ID, token exchange event, workload owner, IAM log |

Trong cả hai trường hợp, nên tránh sự phụ thuộc vào **credential dài hạn** khi provider hỗ trợ federation/managed identity và credential ngắn hạn. Tuy nhiên thời gian sống ngắn không bù được một trust policy quá rộng: kẻ có khả năng nhận token hợp lệ vẫn có thể liên tục đổi lấy phiên mới nếu trust chưa được khắc phục.

## 7. AWS: federated cloud access

AWS có nhiều cơ chế federation cho người dùng và workload; không nên coi chúng là một luồng duy nhất.

### 7.1. Workforce: AWS IAM Identity Center

**AWS IAM Identity Center** có thể được cấu hình với nguồn danh tính doanh nghiệp và hỗ trợ cấp quyền truy cập nhiều AWS account thông qua **permission sets** và **assignments**. Người dùng thường xác thực qua cơ chế SSO được cấu hình; IAM Identity Center quản lý tài nguyên quyền cần thiết trong account đích.

Luồng logic:

1. IdP xác thực nhân viên và áp MFA/chính sách đăng nhập.
2. Nhân viên truy cập portal hoặc điểm truy cập được doanh nghiệp cấu hình.
3. Hệ thống xác định account và permission set mà họ được cấp.
4. Nhân viên chọn quyền được phép; phiên AWS nhận credential/role access tương ứng.
5. AWS IAM kiểm tra thao tác trên tài nguyên theo role, policy và các giới hạn áp dụng.

**Permission set không phải một tên khác của IAM role có thể quản lý tùy ý tại mọi account.** IAM Identity Center điều phối việc triển khai các role cần thiết và assignment; khi JML thay đổi quyền, cần xác minh quyền ở cả lớp IAM Identity Center và account đích.

### 7.2. Workforce: direct SAML federation

AWS cũng hỗ trợ các cấu hình **SAML 2.0 federation** trực tiếp để người dùng nhận phiên quyền AWS thông qua một IAM role, với thao tác tương ứng như **AssumeRoleWithSAML**. Cần kiểm soát IdP tin cậy, SAML assertion, role mapping, trust policy, permission policy và thời hạn session.

### 7.3. Workload: OIDC và AssumeRoleWithWebIdentity

Với một workload bên ngoài AWS, có thể cấu hình **IAM OIDC identity provider**, trust policy và role để nhận credential tạm thời qua **AssumeRoleWithWebIdentity** trong những trường hợp hỗ trợ. Pipeline gửi token do issuer ký, AWS kiểm tra quan hệ tin cậy và các điều kiện liên quan, rồi cấp session role.

Ví dụ mô tả yêu cầu nghiệp vụ:

~~~yaml
# Giả mã, KHÔNG phải AWS trust policy JSON có thể triển khai
provider: AWS
role: learning-staging-deployer
trustedIssuer: approved-ci-issuer
expectedAudience: cloud-sts-audience
subjectConstraints:
  repository: example-org/learning-api
  environment: staging
permissionScope:
  account: learning-staging
  allowedActions:
    - deploy-approved-service
    - read-deployment-artifacts
sessionDuration: short
owner: learning-platform-team
~~~

Giá trị claim và cách gắn điều kiện trust phải tuân theo issuer và IAM condition keys AWS hỗ trợ. Cú pháp giả mã trên chỉ thể hiện các yêu cầu bảo mật, **không thể chép trực tiếp để cấp quyền**.

### 7.4. Kiểm soát chính sách sau federation

- **Trust policy:** Ai được phép assume role?
- **Permissions policy:** Role session được thực hiện action nào trên resource nào?
- **Session policy/conditions:** Phiên có bị giới hạn thêm không?
- **SCP/permission boundary và các hạn chế khác:** Những giới hạn quyền ở cấp account/organization/principal nào đang áp dụng?
- **Resource policy:** Tài nguyên có đường cấp quyền bổ sung hoặc điều kiện riêng không?

Một assertion hợp lệ không tự vượt qua mọi giới hạn của IAM. Khi revocation xảy ra, cần hiểu **lifetime của AWS STS credential và cơ chế chặn/thu hồi session phù hợp**, không mặc định khóa IdP làm token STS đã phát hành biến mất.

## 8. Azure và Microsoft Entra: workforce, workload và RBAC

**Microsoft Entra ID** thường đóng vai trò IdP và hệ thống danh tính của tổ chức. Trong Azure, principal được gán **Azure RBAC role assignment** tại management group, subscription, resource group hoặc resource để thực hiện thao tác tài nguyên phù hợp.

### 8.1. Workforce: đăng nhập và cấp quyền tài nguyên

Người dùng xác thực với Microsoft Entra ID; điều kiện đăng nhập như MFA, Conditional Access hoặc quản lý thiết bị có thể áp dụng theo cấu hình tổ chức. Sau đăng nhập, quyền tài nguyên được đánh giá bằng **Azure RBAC** và các cơ chế quyền dịch vụ liên quan.

**Entra directory role** và **Azure RBAC role** khác nhau về mục tiêu. Một người có quyền quản trị danh tính trong directory không mặc nhiên có mọi role tài nguyên Azure; ngược lại, người sở hữu một subscription không mặc nhiên có mọi quyền quản trị danh tính toàn tenant.

### 8.2. Workforce từ tổ chức khác

Microsoft Entra cung cấp các cơ chế làm việc với danh tính bên ngoài, ví dụ **B2B collaboration/guest access** tùy kiến trúc và chính sách. Doanh nghiệp cần xác định:

- Tổ chức đối tác nào được phép?
- Có cần tài khoản guest hoặc cơ chế liên kết khác ở tenant đích không?
- Ai là sponsor nội bộ, và khi nào quyền hết hạn?
- Có yêu cầu xác thực mạnh, điều kiện đăng nhập hoặc review truy cập đặc biệt không?
- Khi hợp đồng kết thúc, ai thu hồi guest, group, RBAC assignments và phiên liên quan?

Không suy ra rằng khi đối tác khóa nhân viên ở IdP của họ thì tất cả quyền còn gắn tại tenant của doanh nghiệp sẽ tự được xóa.

### 8.3. Workload identity federation

**Workload identity federation** có thể cho một workload bên ngoài trình OIDC token để nhận quyền sử dụng một danh tính đã được cấu hình tại Entra/Azure (ví dụ ứng dụng/service principal hoặc managed identity theo kịch bản được hỗ trợ), tránh phụ thuộc client secret lâu dài.

Quan hệ tin cậy cần ràng buộc các trường như **issuer, subject, audience** theo cơ chế cấu hình federated identity credentials tương ứng. Sau khi nhận token phù hợp, quyền sử dụng tài nguyên Azure vẫn cần được gán qua Azure RBAC hoặc authorization của dịch vụ.

Ví dụ: một workflow triển khai chỉ được dùng danh tính triển khai staging. Cấu hình federation phải giới hạn đúng workflow/repository/nhánh hoặc environment được hỗ trợ; identity đó chỉ nhận role deploy thích hợp ở scope staging, không được có Contributor/Owner trên toàn tenant hoặc subscription production.

### 8.4. Những điểm cần kiểm tra khi Mover/Leaver

Rà soát đồng thời **group membership, Azure RBAC assignments trực tiếp/kế thừa, guest accounts, service principals, federated identity credentials, app credentials và quyền trong dịch vụ**. Session và token đã phát hành có giới hạn thu hồi phụ thuộc khả năng của Entra/dịch vụ; sự kiện khóa danh tính cần đi kèm đối soát quyền thực tế.

## 9. Google Cloud: Workforce Identity Federation và Workload Identity Federation

Google Cloud hỗ trợ các cơ chế federation riêng cho **người dùng bên ngoài** và **workload bên ngoài**. Những cơ chế này không đồng nghĩa với việc mọi ứng dụng đăng nhập theo cùng giao thức hay mọi workload đều phải tạo service account key.

### 9.1. Workforce Identity Federation

**Workforce Identity Federation** cho phép những người dùng thuộc hệ thống danh tính bên ngoài truy cập Google Cloud theo một quan hệ tin cậy được cấu hình. Tổ chức có thể lập **workforce pool/provider**, ánh xạ thuộc tính và gán quyền IAM cho những principal phù hợp.

Khi triển khai, cần:

1. Xác định issuer/IdP đáng tin cậy và giao thức hỗ trợ trong cấu hình cụ thể.
2. Quản lý subject/attributes và các điều kiện giới hạn nhóm người dùng đủ điều kiện.
3. Gán IAM roles tại organization, folder, project hoặc resource phù hợp.
4. Đặt owner, sponsor, thời hạn và cơ chế review cho workforce bên ngoài.
5. Kiểm tra log truy cập, token exchange và quyền kế thừa/assignment thực tế.

### 9.2. Workload Identity Federation

**Workload Identity Federation** cho phép workload bên ngoài Google Cloud dùng chứng thực từ issuer được hỗ trợ để nhận quyền Google Cloud trong những điều kiện đã cấu hình. Cách thực thi có thể **cấp IAM access trực tiếp cho federated principal** hoặc **thông qua service account impersonation**, tùy dịch vụ và yêu cầu tích hợp.

Các phần thường xuất hiện:

- **Workload identity pool/provider:** Cấu hình nguồn danh tính và cách xác minh chứng thực.
- **Attribute mapping/conditions:** Chuyển claim thành thuộc tính dùng cho phân quyền và hạn chế ai đủ điều kiện.
- **Principal identifiers:** Định danh federated principal hoặc tập principal.
- **IAM binding:** Gán role cần thiết ở phạm vi tài nguyên.
- **Service account impersonation (nếu dùng):** Cấp quyền phù hợp cho principal được phép sử dụng service account; sau đó quyền tác vụ phụ thuộc quyền service account.

Nếu pipeline được phép impersonate một service account có quyền rộng, việc giới hạn role trực tiếp trên workload chưa chắc giải quyết rủi ro. Cần rà soát **cả quyền impersonation và quyền của service account đích**.

### 9.3. IAM Conditions, allow và deny

Google Cloud IAM thường biểu diễn quyền qua **role bindings** trên tài nguyên. Trong những trường hợp được hỗ trợ, **IAM Conditions** có thể giới hạn binding; **IAM deny policies** và các hạn chế tổ chức có thể ảnh hưởng quyền hoặc cấu hình.

Federation chỉ xác thực/ánh xạ principal đầu vào; các quyết định cho phép hay từ chối hành động trên tài nguyên vẫn dựa vào **IAM policy thực tế**, scope và các hạn chế áp dụng.

## 10. Bảng so sánh các mô hình cloud

| Nhu cầu | AWS | Azure / Entra | Google Cloud |
| --- | --- | --- | --- |
| Workforce SSO tập trung | IAM Identity Center hoặc SAML federation phù hợp | Microsoft Entra ID; tích hợp IdP và SSO theo cấu hình | Google identity hoặc Workforce Identity Federation tùy nguồn |
| Quyền người dùng trên tài nguyên | IAM role, permissions, permission-set assignment | Azure RBAC role assignment theo scope | IAM role bindings theo scope |
| Workload từ issuer ngoài cloud | OIDC federation và STS role session khi được hỗ trợ | Federated identity credentials và quyền của app/identity đích | Workload identity pool/provider, direct principal hoặc service account impersonation |
| Ràng buộc nguồn | Trust policy, issuer/audience/claims theo provider | Issuer, subject, audience trong cấu hình federation | Provider, attribute mapping/condition, principal và IAM binding |
| Hạn chế quyền bổ sung | SCP, permission boundary, session policy, resource policy | Scope, RBAC condition/deny, quyền dịch vụ | IAM Conditions, deny policies và organization constraints |
| Theo dõi | CloudTrail và audit của IAM Identity Center/IdP | Sign-in/audit của Entra, Azure Activity và resource logs | Cloud Audit Logs và sự kiện identity phù hợp |

Mục đích của bảng là xác định **vai trò kiến trúc**, không phải tuyên bố các sản phẩm là tương đương hoàn toàn. Quyền có cùng tên ở hai cloud có thể bao phủ action và resource khác nhau; cần đánh giá từng provider và dịch vụ.

## 11. Role mapping, RBAC, ABAC và nguyên tắc ít quyền nhất

Một federation an toàn đòi hỏi **xác minh đúng nguồn** và **chọn đúng quyền đích**. Nếu chỉ tập trung vào login, tổ chức dễ cấp vai trò quá rộng hoặc giữ các quyền cũ khi nhân sự đổi nhiệm vụ.

### 11.1. Role mapping theo nhóm

Ví dụ nghiệp vụ:

| Nhóm nguồn | Điều kiện bổ sung | Target | Vai trò mong muốn |
| --- | --- | --- | --- |
| platform-developers | Nhân viên active, môi trường dev | Một project phát triển | DevLogReader |
| sre-oncall | Trực vận hành và được duyệt | Một account production | IncidentViewer |
| sre-elevated | Incident có approval và thời hạn | Một service production | ScopedOperator |
| external-auditors | Sponsor còn hiệu lực | Scope kiểm toán được duyệt | ReadOnlyAuditor |
| cicd-staging | Repository + environment hợp lệ | Một account staging | StagingDeployer |

Đây là tên nhóm/vai trò ví dụ, không phải role được cloud provider tạo sẵn. Với quyền có rủi ro cao, không nên coi việc thuộc nhóm ở IdP là điều kiện duy nhất nếu còn yêu cầu phê duyệt, MFA, thời hạn hoặc phân tách trách nhiệm.

### 11.2. Attribute-Based Access Control

**RBAC** tổ chức quyền theo role. **ABAC** đưa thuộc tính danh tính, tài nguyên và ngữ cảnh vào quyết định truy cập nếu nền tảng hỗ trợ. Ví dụ giới hạn vai trò đọc dữ liệu cho người có team phù hợp với nhãn của resource và chỉ ở môi trường dev.

~~~yaml
# Giả mã mô tả ABAC: không áp trực tiếp vào provider
identity:
  status: active
  team: learning
resource:
  environment: dev
  team: learning
request:
  action: logs.read
allowWhen:
  - identity.status == active
  - identity.team == resource.team
  - resource.environment == dev
~~~

Các claim/attribute ảnh hưởng quyền cần có **nguồn thẩm quyền rõ ràng**. Không được để người dùng tự sửa các thuộc tính nhằm nhận role cao hơn; cũng không giả định mọi cloud trực tiếp hiểu thuộc tính HRIS.

### 11.3. Separation of Duties và đặc quyền

Người có quyền thay IAM role, trust policy, service account impersonation, secret hoặc pipeline production có thể **nâng đặc quyền gián tiếp**. Vì vậy:

- Tách người yêu cầu và người phê duyệt quyền nhạy cảm khi cần.
- Giới hạn scope và thời hạn của role quản trị.
- Dùng MFA chống phishing, máy quản trị được kiểm soát và JIT/PIM/PAM khi phù hợp.
- Ghi log cả thao tác **thay trust** lẫn thao tác **sử dụng trust**.
- Rà soát đường nâng quyền qua service account, IAM administrator, secret và CI/CD.

## 12. Lifecycle federation theo Joiner–Mover–Leaver

**JML** làm cho tư cách danh tính và entitlement phù hợp với công việc hiện hành. Đối với federation, cần quản lý cả nguồn xác thực, liên kết danh tính và quyền tại cloud target.

| Giai đoạn | Tác nhân khởi phát | Việc cần thực hiện | Chỉ tiêu xác minh |
| --- | --- | --- | --- |
| **Joiner** | Nhận việc, đối tác được phê duyệt, workload ra mắt | Xác minh danh tính/issuer; tạo account/group nếu cần; ánh xạ role tối thiểu; cấu hình trust và MFA; phê duyệt | Principal nhận đúng quyền, đúng scope và không có quyền thừa |
| **Mover** | Đổi đội, vai trò, dự án, issuer/repository, môi trường | Tính lại role mapping; thu hồi entitlement/trust cũ; cấp quyền mới; rà soát session và credential | Không còn quyền thuộc vai trò cũ hoặc ngoại lệ chưa được duyệt |
| **Leaver** | Nghỉ việc, hết hợp đồng, workload kết thúc | Disable IdP/source; thu hồi account/role/binding/trust/key; xử lý phiên; chuyển ownership | Không còn đường truy cập hợp lệ ngoài dự kiến, có readback tại target |

### 12.1. Joiner: đúng danh tính, đúng quyền, đúng thời điểm

Giả sử nhân viên **Hà** có ID nguồn **EMP-5172**, gia nhập đội Platform. HRIS xác nhận trạng thái và ngày bắt đầu. IdP tạo identity dùng SSO, bật chính sách xác thực mạnh, và nhóm Platform Developers được liên kết đến role chỉ đọc ở môi trường dev.

Phải lưu rõ:

1. Identity ID nguồn, issuer và subject đã ghép đúng.
2. Scope cloud (account/subscription/project/resource) và role được phê duyệt.
3. Vai trò nghiệp vụ, owner, approver và lý do cấp quyền.
4. Thời điểm hiệu lực và hết hạn khi phù hợp.
5. Kết quả xác minh đăng nhập được phép, các thao tác cần thiết được phép và quyền ngoài phạm vi bị từ chối.

Không nên kích hoạt quyền production chỉ vì tài khoản IdP đã được tạo.

### 12.2. Mover: ngắt đường truy cập cũ

Hà chuyển sang đội Analytics. Nhóm IdP được cập nhật nhưng một direct IAM assignment tại production vẫn còn. Nếu workflow chỉ thêm quyền cho Analytics, Hà sẽ giữ quyền thừa từ Platform.

Quy trình:

1. Nhận sự kiện Mover từ nguồn có thẩm quyền và xác định ngày hiệu lực.
2. Tính **desired access** theo công việc mới và ngoại lệ được phê duyệt.
3. Truy vấn **actual access** gồm group, role, assignment, resource policy, trust, service-account impersonation và credential liên quan.
4. Thu hồi quyền cũ; xét thứ tự thu hồi/cấp mới để giảm xung đột **Separation of Duties**.
5. Kiểm tra session/credential còn hiệu lực và đường cấp quyền tương đương.
6. Đọc lại trạng thái tại mỗi cloud target; ghi exception nếu chưa thể xử lý dứt điểm.

### 12.3. Leaver: tách quyền mới và phiên đã phát hành

Khi Hà nghỉ việc, IdP disable tài khoản và dừng phát assertion/token mới. Nhưng hệ thống vẫn cần xử lý:

- IAM bindings/assignments trực tiếp và quyền qua nhóm.
- Local cloud users, guest accounts, external principals và các mapping còn tồn tại.
- API key, access key, refresh token hoặc secret độc lập với IdP.
- Role session, temporary credentials, access tokens đã cấp, tùy khả năng revoke/expiry của từng dịch vụ.
- Role trust có thể cho principal khác truy cập theo điều kiện quá rộng.
- Pipeline/service account do người đó sở hữu, cần chuyển giao ownership hoặc xoay credential.

**Không xóa toàn bộ cloud role dùng chung chỉ vì một người nghỉ việc.** Thông thường cần thu hồi quyền gắn với người đó, còn định nghĩa role vẫn giữ nếu những người khác hoặc workload còn sử dụng hợp lệ.

### 12.4. Partner Leaver và liên kết ngoài doanh nghiệp

Đối tác có thể ngừng hợp tác nhưng tài khoản ở IdP đối tác vẫn active. Doanh nghiệp cần **source event nội bộ** như ngày kết thúc hợp đồng, sponsor xác nhận hoặc kỳ access review, để chủ động hết hạn guest, role và trust.

Nên có quy tắc:

- Mọi external principal có sponsor nội bộ và ngày hết hạn/đánh giá lại.
- Quyền truy cập được hạn chế theo tài nguyên và mục đích hợp tác.
- Thu hồi khi hợp đồng hết hiệu lực, sponsor thay đổi hoặc đối tác không còn đáp ứng yêu cầu.
- Kiểm tra quyền trực tiếp và session/credential độc lập sau khi tắt liên kết.

## 13. Phiên truy cập và bài toán thu hồi

**Federation authentication** và **cloud authorization session** có thể có thời hạn khác nhau. Một IdP có thể phát assertion OIDC/SAML ngắn hạn, nhưng cloud RP/STS đã cấp session hoặc temporary credentials với thời hạn riêng.

### 13.1. Các mốc cần theo dõi

~~~mermaid
flowchart LR
    A["IdP xác thực người dùng<br/>T0"] --> B["Phát assertion/token<br/>T1"]
    B --> C["Cloud chấp nhận federation<br/>T2"]
    C --> D["Cloud session / credential<br/>Hạn dùng riêng"]
    E["Sự kiện Leaver<br/>T3"] --> F["IdP disable"]
    E --> G["Thu hồi grants / trust / session nếu hỗ trợ"]
    D --> H["Session bị thu hồi hoặc tự hết hạn"]
    G --> I["Đọc lại quyền + kiểm tra hiệu lực"]
    H --> I
    I --> J["VERIFIED hoặc EXCEPTION"]
~~~

**T3 không tự xóa T2**. Nếu token/session tồn tại đến T4 và dịch vụ không hỗ trợ thu hồi tức thời, quy trình phải ghi nhận khoảng phơi nhiễm, dùng biện pháp giảm rủi ro được hỗ trợ và xác minh khi hết hạn.

### 13.2. Biện pháp giảm rủi ro

- Dùng thời hạn phiên/credential thích hợp theo loại tác vụ; phiên quản trị thường cần giới hạn chặt hơn.
- Yêu cầu tái xác thực hoặc thu hồi phiên khi công cụ hỗ trợ.
- Thu hồi assignment, role trust hoặc quyền gọi API theo cách provider thực sự đánh giá.
- Xoay credential đã bị chia sẻ hoặc nghi ngờ lộ.
- Chặn phiên/người dùng qua cơ chế rủi ro cao phù hợp, kết hợp giám sát sự kiện bất thường.
- Đảm bảo Leaver khẩn cấp có kênh xử lý ưu tiên khi phát hiện tài khoản bị chiếm.

Không thể khẳng định “disable SSO sẽ logout tất cả dịch vụ lập tức” nếu chưa kiểm chứng cơ chế liên thông session của các hệ thống thực tế.

## 14. JML cho workload và CI/CD federation

Một workload có thể sinh ra, đổi owner, đổi repository hoặc bị loại bỏ; những sự kiện đó tương đương vòng đời JML dù không đến từ HRIS.

### 14.1. Joiner của workload

Khi tạo pipeline triển khai:

1. Đăng ký workload ID và owner chính/phụ.
2. Xác định issuer, repository, nhánh, môi trường và điều kiện chạy tin cậy.
3. Tạo trust policy và role/service account có permission nhỏ nhất.
4. Ưu tiên credential tạm thời/federation thay cho secret tĩnh.
5. Gắn log và kiểm tra một token hợp lệ được phép dùng đúng scope.
6. Kiểm tra token đến từ workload không hợp lệ phải bị từ chối.

### 14.2. Mover của workload

Khi ứng dụng đổi repository hoặc được chuyển từ staging sang production, cần **thay đổi trust theo thông tin mới** và thu hồi trust cũ; không chỉ thêm điều kiện mới bằng phép OR quá rộng. Quyền production nên có bước phê duyệt độc lập.

### 14.3. Leaver của workload

Khi pipeline bị xóa, phải thu hồi federated identity credential/provider binding/role assignment có liên quan; kiểm tra secret hoặc key còn tồn tại và chuyển giao resource ownership nếu cần. Một issuer còn được tin cậy quá rộng có thể cho workload khác tiếp tục nhận credential dù pipeline ban đầu đã ngừng.

### 14.4. Ví dụ trust cho CI/CD

~~~yaml
# Giả mã nghiệp vụ, không triển khai nguyên văn vào cloud
workload:
  id: deploy-learning-staging
  owner: platform-team
  issuer: https://ci.example.org
  subject: repo:example-org/learning-api:environment:staging
  audience: cloud-token-exchange
destination:
  environment: staging
  role: deploy-learning-service
permissions:
  - deploy-approved-version
  - read-staging-artifacts
restrictions:
  productionAccess: denied
  staticSecret: none
governance:
  approval: deployment-policy
  reviewCadence: monthly
~~~

Để có giá trị bảo mật, những thuộc tính như environment, repository hay branch phải thật sự có **ngữ nghĩa được issuer bảo đảm**, và cloud provider phải hỗ trợ điều kiện kiểm tra tương ứng. Cũng cần bảo vệ workflow/repository khỏi việc người không được duyệt sửa pipeline để nhận quyền.

## 15. Thiết kế bảo mật cho liên kết đa cloud

Doanh nghiệp có thể dùng một IdP tập trung để liên kết nhiều cloud, song quyền đích vẫn được quản trị theo từng nền tảng. Một nhân viên có thể dùng cùng danh tính nguồn để nhận:

- Quyền đọc trên một AWS account.
- Quyền vận hành có thời hạn trên một Azure resource group.
- Quyền phân tích tại một Google Cloud project.

**Không nên ánh xạ trực tiếp cùng tên role giữa các cloud** như thể quyền tương đương tuyệt đối. Chức năng role và scope khác nhau; mỗi target phải có policy mapping, owner và bằng chứng review riêng.

### 15.1. Account/tenant boundary

Federation thường xuyên đi qua ranh giới tenant và account. Cần xác định chính xác:

- IdP nào được tin cậy bởi account/subscription/project nào?
- Cloud target chấp nhận issuer chung toàn tổ chức hay issuer giới hạn nhóm?
- Role cấp đến scope hẹp hay phạm vi toàn organization?
- Có tài khoản khẩn cấp hoặc cloud-local principal nằm ngoài federation không?
- Khi tổ chức tái cơ cấu hoặc chuyển tenant, điều gì xảy ra với định danh nguồn và trust?

Đối với workload federation, càng cần phân biệt **identity của pipeline**, **identity của ứng dụng ở cloud** và **role mà phiên đó sử dụng**, để không mở quyền production cho workload test.

### 15.2. Sự cố IdP và quyền khẩn cấp

Nếu IdP hoặc federation provider bị gián đoạn, nhân viên có thể không đăng nhập được vào cloud dù hạ tầng vẫn chạy. Tổ chức nên có quy trình **break-glass** để xử lý sự cố nghiêm trọng theo chính sách:

- Danh tính/quyền khẩn cấp được bảo vệ độc lập phù hợp với kiến trúc.
- Người có thẩm quyền, vị trí cất giữ yếu tố xác thực và điều kiện kích hoạt rõ ràng.
- Cảnh báo khi sử dụng và kiểm toán đầy đủ.
- Kiểm tra định kỳ để xác nhận có thể dùng khi hệ thống xác thực tập trung gặp sự cố.
- Thực hiện review và chấm dứt phiên khẩn cấp sau ứng cứu.

Quyền khẩn cấp không nên trở thành một đường quản trị thường ngày để bỏ qua approval hoặc MFA.

## 16. Vận hành: xác minh, monitoring và policy-as-code

Federation thường bị lỗi tại những ranh giới như certificate rollover, issuer thay đổi, token audience sai, subject claim khác định dạng, metadata lệch hoặc cấu hình role trust không đồng bộ.

### 16.1. Quy trình thay đổi trust

~~~mermaid
flowchart TD
    R["Yêu cầu federation / thay đổi trust"] --> S["Xác định owner, issuer, subject, audience, scope"]
    S --> D["Cập nhật cấu hình có quản lý phiên bản"]
    D --> L["Lint + kiểm tra syntax / security rules"]
    L --> T["Thử nghiệm đường hợp lệ và không hợp lệ"]
    T --> A["Phê duyệt theo mức rủi ro"]
    A --> P["Triển khai có kiểm soát"]
    P --> V["Readback cấu hình + kiểm chứng quyền thực tế"]
    V --> M["Giám sát token exchange, IAM events, drift"]
    V -->|Không đạt| F["Khắc phục và xử lý ngoại lệ"]
    F --> D
~~~

Với quyền production và cross-tenant federation, kiểm thử “token hợp lệ được chấp nhận” **chưa đủ**; phải kiểm tra token có issuer sai, audience sai, subject không được duyệt và claim thiếu quan trọng **bị từ chối**. Không cần dùng token giả mạo để kiểm tra trên hệ thống thật nếu có công cụ mô phỏng hoặc môi trường thử nghiệm được phê duyệt.

### 16.2. Các trạng thái vận hành cần phân biệt

~~~text
REQUESTED   Đã nhận yêu cầu liên kết hoặc thay quyền
APPROVED    Đã có phê duyệt theo chính sách
APPLIED     API/config change báo áp dụng thành công
VERIFIED    Đã đọc lại target và xác minh trạng thái mong muốn
FAILED      Thao tác hoặc xác minh không thành công
EXCEPTION   Còn ngoại lệ với owner, lý do và hạn xử lý
~~~

**APPLIED không đồng nghĩa VERIFIED.** Một quy trình đã gọi API xóa role thành công vẫn có thể để sót quyền trực tiếp khác hoặc một phiên còn hiệu lực.

### 16.3. Log nào cần giữ?

| Dữ liệu | Mục đích |
| --- | --- |
| IdP sign-in/authentication events | Biết principal, phương thức xác thực và kết quả |
| Federation/trust configuration changes | Theo dõi ai đổi issuer, certificate, attribute mapping, role trust |
| Token exchange/role assumption events | Biết principal nguồn đã đổi lấy phiên/quyền tại target |
| Cloud IAM role, policy, assignment changes | Chứng minh entitlement được cấp/thu hồi |
| Resource/API audit events | Xác định quyền đã được dùng để thao tác gì |
| JML source events và approvals | Liên kết quyết định nhân sự/nghiệp vụ với thay đổi IAM |
| Reconciliation/readback results | Phân biệt thao tác đã yêu cầu với quyền thực tế |

Không ghi **raw SAML assertions, bearer tokens, private keys hoặc secrets** vào log chỉ để thuận tiện điều tra. Cần giữ metadata định danh, thời gian, correlation ID và bằng chứng thay đổi đủ để truy vết mà không tạo kho credential mới.

## 17. Đối soát quyền và phát hiện residual access

Mục tiêu của JML là thống nhất **quyền được duyệt** với **quyền thực tế** trên tất cả cloud target. Đối với federation, một danh tính có thể nhận quyền qua nhiều đường:

- Group mapping ở IdP hoặc federation provider.
- IAM Identity Center permission-set assignment, Azure RBAC assignment, Google IAM binding.
- IAM role trust, resource policy hoặc quyền cross-account.
- Quyền impersonate service account hoặc dùng workload principal.
- Guest account, cloud-local identity hoặc credential độc lập.
- Session và temporary token đã phát hành.

### 17.1. Mô hình desired/actual/effective access

~~~text
event = getAuthoritativeLifecycleEvent(identityId)
targets = discoverCloudTargetsAndTrustRelationships(identityId)

for target in targets:
    desired = approvedEntitlements(identityId, target, event.effectiveTime)
    actual = enumerateGroupsRolesBindingsTrustAndCredentials(identityId, target)
    stale = compareNormalizedGrants(actual, desired)

    for entitlement in stale:
        revokeEntitlement(entitlement)

    verify = evaluateEffectiveAccessAndSessions(identityId, target)
    if verify.satisfiesDesiredState:
        recordVerified(event, target)
    else:
        escalateException(event, target, verify)
~~~

Đây là giả mã vận hành. Phép đối chiếu phải chuẩn hóa theo **issuer, subject, principal, role, scope, điều kiện, thời hạn, đường kế thừa và chính sách deny**, nếu không sẽ bỏ sót quyền hoặc báo chênh lệch sai. Một số quyền hiệu lực cần công cụ phân tích IAM và kiểm thử truy cập có kiểm soát thay vì chỉ một API liệt kê.

### 17.2. Tình huống mâu thuẫn quyền

Giả sử người dùng đã bị xóa khỏi nhóm SRE trong IdP nhưng vẫn có Azure RBAC assignment trực tiếp ở production. Đăng nhập mới có thể bị hạn chế nhưng quyền cấu hình vẫn tồn tại, và có thể còn session phù hợp.

**Kết luận:** Sự kiện Mover/Leaver chưa đạt trạng thái VERIFIED. Hệ thống phải thu hồi assignment, kiểm tra các đường khác, xử lý session theo hỗ trợ, ghi owner và bằng chứng thực tế.

## 18. Tình huống xuyên suốt: từ nhân viên đến pipeline

Tổ chức vận hành ứng dụng Learning trên AWS staging, Azure development và Google Cloud analytics. Nhân viên **Hà** có identity ID **EMP-5172**, được xác thực qua IdP doanh nghiệp.

### 18.1. Joiner của người dùng

Hà gia nhập Platform. HRIS phát sự kiện Joiner; IdP tạo account và nhóm; IAM gán quyền đọc telemetry ở development đúng scope. Người dùng xác thực SSO, nhận cloud session và có quyền theo role. Tổ chức xác minh rằng Hà **không được đọc secret hoặc sửa policy production**.

### 18.2. Mover của người dùng

Hà chuyển sang Analytics. Hệ thống cập nhật nhóm ở IdP và cấp quyền analytics. Tuy nhiên một permission set assignment cũ tại AWS và direct role assignment tại Azure vẫn còn. Quy trình đối soát phát hiện hai quyền tồn dư; chỉ khi thu hồi và đọc lại cloud target thành công, Mover mới được VERIFIED.

### 18.3. Leaver của người dùng

Hà nghỉ việc. Tài khoản IdP bị disable; hệ thống thu hồi group/assignment/binding và xử lý guest/local account, key/token/session theo provider. Pipeline Hà từng sở hữu được chuyển owner sang nhóm Platform. Việc chuyển owner **không đồng nghĩa giữ lại quyền cá nhân của Hà**.

### 18.4. Joiner và Leaver của pipeline

Một pipeline mới được đăng ký, dùng OIDC federation từ CI/CD để nhận quyền deploy AWS staging, giới hạn đúng repository và environment. Khi repository bị lưu trữ vĩnh viễn, workflow xóa trust liên quan và assignment, kiểm tra không còn API call được phép từ workload cũ.

### 18.5. Bản ghi audit minh họa

~~~json
{
  "eventId": "FED-JML-5172",
  "identityId": "EMP-5172",
  "eventType": "mover",
  "source": "HRIS",
  "issuer": "https://idp.company.example",
  "target": "aws-staging",
  "previousEntitlement": "LearningDeveloper",
  "desiredEntitlements": [],
  "operation": "revoke_assignment",
  "status": "verification_pending",
  "approvalRef": "ACCESS-MOVE-5172",
  "occurredAt": "2026-11-23T07:00:00Z"
}
~~~

Trạng thái **verification_pending** là **chưa hoàn tất**. Bản ghi chỉ được chuyển sang verified khi quyền cũ đã được xác minh không còn hiệu lực tại đích theo phạm vi kiểm tra, hoặc có exception được ghi nhận rõ nếu không thể chặn ngay session còn sống.

## 19. Những anti-pattern thường gặp

| Sai lầm | Rủi ro | Cách xử lý |
| --- | --- | --- |
| Chỉ kiểm tra token có chữ ký hợp lệ | Chấp nhận token sai issuer/audience/subject | Xác thực đầy đủ trust và claims |
| Ghép principal bằng email hiển thị | Nhầm người khi email đổi hoặc tái sử dụng | Dùng issuer + stable subject và identity ID nguồn |
| Trust OIDC cho mọi repository/branch | Workload ngoài dự kiến có thể nhận role | Ràng buộc claim theo repo, branch/environment được phép |
| Federation SAML không xác minh audience/recipient | Assertion dành cho SP khác có thể bị dùng nhầm | Kiểm tra đầy đủ điều kiện của assertion |
| Ánh xạ tất cả người đăng nhập thành Admin | Một tài khoản IdP bị chiếm có phạm vi tác động rất lớn | Role mapping theo nghiệp vụ, scope và phê duyệt |
| Dùng token ID như API access token | Sai mục đích và audience token | Tách OIDC authentication với OAuth API authorization |
| Chỉ disable user ở IdP khi Leaver | Cloud-local key, assignment và session có thể còn | Thu hồi entitlement/credential và xác minh ở target |
| Tin SCIM sẽ thu hồi mọi IAM role | Còn binding/trust ngoài đối tượng SCIM | API quản lý quyền riêng và reconciliation |
| Không giới hạn quyền impersonation | Principal có quyền gián tiếp qua service account | Review cả quyền impersonate và quyền service account |
| Không quản lý sponsor của đối tác | Guest/đối tác vẫn truy cập sau hết hợp đồng | Owner, expiry, access review và Leaver từ nguồn nội bộ |
| Lưu access key tĩnh thay cho federation | Credential lâu dài bị lộ hoặc tồn dư | OIDC/managed identity và token ngắn hạn khi phù hợp |
| Không theo dõi chứng thư/khóa ký | SSO gián đoạn hoặc trust cập nhật sai | Quy trình rollover, cảnh báo và kiểm tra metadata |
| Tin rằng revoke assignment xóa mọi phiên ngay | Session tạm thời tiếp tục đến khi bị chặn hoặc hết hạn | Hiểu TTL, dùng revoke được hỗ trợ, giám sát |
| Lưu raw token trong log | Tạo kho credential có thể bị lạm dụng | Log metadata/correlation ID và bảo vệ dữ liệu |
| Quản lý trust thủ công không qua review | Drift, sai phạm vi và khó kiểm toán | Policy-as-code, diff, approval, readback |

## 20. Chỉ số vận hành và kiểm toán liên kết danh tính

| Chỉ số | Cách diễn giải |
| --- | --- |
| **Tỷ lệ federation trust có owner và phạm vi rõ** | Trust có issuer/subject/audience/scope, owner và kỳ review |
| **Số liên kết external principal quá hạn** | Guest/contractor/workload còn đường truy cập sau ngày hết hạn |
| **P95 thời gian thu hồi quyền sau Leaver** | Từ thời điểm có hiệu lực đến lúc cloud target được VERIFIED |
| **Tỷ lệ JML events hoàn tất VERIFIED** | Có readback tại mọi target liên quan, không chỉ request thành công |
| **Số phiên/credential còn hiệu lực sau Leaver** | Theo dõi giới hạn revocation và mức phơi nhiễm |
| **Tỷ lệ workload dùng federation/credential ngắn hạn** | Giảm phụ thuộc secret tĩnh cho automation |
| **Số trust cho phép principal quá rộng** | Ưu tiên ràng buộc issuer, subject và audience |
| **Số trường hợp quyền impersonation/role-assumption quá mức** | Phát hiện đường nâng đặc quyền gián tiếp |
| **Số thay đổi cấu hình federation ngoài pipeline** | Giám sát configuration drift và thay đổi không được duyệt |
| **Tỷ lệ kiểm thử negative case đạt yêu cầu** | Chứng minh token/principal ngoài phạm vi bị từ chối |

Nên chia chỉ số theo **workforce/workload, quyền thường/quyền đặc biệt, production/non-production và provider**. Một role production có trust rộng là vấn đề ưu tiên hơn một quyền chỉ đọc sandbox có phạm vi nhỏ.

### 20.1. Bằng chứng phục vụ audit

Hệ thống nên có:

1. Sự kiện nguồn và identity/workload ID ổn định.
2. Issuer, subject, audience/trust reference và phiên bản mapping liên quan.
3. Target account/subscription/project, role/scope, người phê duyệt.
4. Dấu vết thay đổi group, policy, assignment, impersonation và credential.
5. Thời điểm triển khai, kết quả API và readback tại cloud.
6. Bằng chứng kiểm tra effective access và giới hạn session có liên quan.
7. Owner và ngày hết hạn của mọi exception chưa xử lý.

Không lưu mật khẩu, private key hay bearer token thô như bằng chứng kiểm toán.

## 21. Bài tập tự kiểm tra

### Bài 1. SAML SSO có đủ cho Leaver?

**Tình huống:** Người dùng bị disable ở IdP; nhóm kỹ thuật kết luận đã mất mọi quyền cloud.

**Đáp án:** Chưa thể kết luận. Cần rà soát session đã phát hành, IAM grants trực tiếp, cloud-local users, keys, trust và những hệ thống đích ngoài SSO; xác minh theo provider.

### Bài 2. Pipeline có token OIDC hợp lệ nhưng bị từ chối

**Tình huống:** Pipeline chạy ở repository A, token ký hợp lệ, nhưng trust chỉ cho phép repository B.

**Đáp án:** Từ chối là kết quả đúng. Chữ ký hợp lệ chỉ chứng minh token đến từ issuer; subject và các điều kiện trust vẫn phải khớp.

### Bài 3. Nhân viên chuyển team nhưng còn quyền trực tiếp

**Tình huống:** IdP group đã cập nhật, nhưng Azure RBAC role assignment trực tiếp còn tồn tại.

**Đáp án:** Mover chưa VERIFIED. Cần xác định quyền có còn hợp lệ không, thu hồi quyền tồn dư và kiểm tra cả scope kế thừa lẫn session phù hợp.

### Bài 4. Đối tác nghỉ việc trước ngày hết hợp đồng

**Tình huống:** IdP bên ngoài vẫn cho đăng nhập, nhưng sponsor nội bộ nhận thông báo nhân sự đối tác đã nghỉ.

**Đáp án:** Doanh nghiệp phải kích hoạt Leaver ở phía hệ thống cấp quyền, thu hồi guest/assignment/trust và kiểm tra đích. Không chờ đối tác đổi trạng thái IdP nếu rủi ro truy cập đang hiện hữu.

### Bài 5. Service account có quyền rộng

**Tình huống:** Workload federation dùng service account có quyền quản trị toàn project mặc dù chỉ cần đọc một bucket.

**Đáp án:** Thu hẹp IAM role/binding của service account và quyền được phép impersonate, kiểm tra trust, đồng thời thử cả hành động cần được phép và hành động ngoài phạm vi bị từ chối.

## 22. Checklist triển khai federated cloud access

1. **Nguồn đúng:** Biết issuer/IdP, HRIS hoặc workload registry và owner.
2. **Định danh đúng:** Dùng subject ổn định theo issuer; mapping qua hệ thống có thẩm quyền.
3. **Bằng chứng đúng:** Kiểm tra chữ ký, issuer, audience, expiry, replay/correlation theo giao thức.
4. **Trust đúng:** Giới hạn principal, issuer, claim, repository/branch/environment theo hỗ trợ thực tế.
5. **Role đúng:** RBAC/ABAC tối thiểu theo action, scope và thời gian; tránh quyền nâng đặc quyền gián tiếp.
6. **Xác thực mạnh:** Workforce tuân thủ chính sách MFA, thiết bị và rủi ro; workload dùng identity riêng.
7. **Provisioning rõ ràng:** SCIM cập nhật user/group khi phù hợp; IAM API quản lý các entitlement khác.
8. **JML đầy đủ:** Joiner cấp đúng quyền; Mover thu hồi quyền cũ; Leaver xử lý cả token/session/credential.
9. **Session được hiểu rõ:** Có chính sách TTL, revoke theo khả năng và phương án khi không thể hủy ngay.
10. **Đối tác được quản trị:** Sponsor, expiry, scope và access review cụ thể.
11. **Workload có lifecycle:** Chủ sở hữu, trust, role, rotation và quy trình ngừng hoạt động.
12. **Đổi trust có kiểm soát:** Policy-as-code, review, kiểm thử allow/deny, certificate/key rollover.
13. **Readback bắt buộc:** Không đánh dấu hoàn tất chỉ vì API trả về thành công.
14. **Audit an toàn:** Giữ metadata và bằng chứng, không lưu raw credential trong log.
15. **Độ tin cậy vận hành:** Có break-glass được bảo vệ và kiểm tra khi IdP gặp sự cố.

## 23. Tổng kết

**Federated cloud access** cho phép kết nối danh tính từ IdP hoặc workload issuer đến các hệ thống cloud thông qua quan hệ tin cậy có kiểm soát. **SAML** thường phục vụ đăng nhập liên kết của người dùng; **OIDC/OAuth** hỗ trợ danh tính và các luồng token/ủy quyền phù hợp; **cloud IAM** quyết định quyền thực tế theo principal, role, policy, scope và điều kiện.

Trong mô hình quản lý vòng đời danh tính, federation chỉ an toàn khi có liên kết giữa **nguồn danh tính – xác thực – ánh xạ quyền – entitlement tại cloud – JML – kiểm toán**. Tổ chức phải xử lý cả workforce và workload, tài khoản dịch vụ, quyền gián tiếp, trust rộng, session và credential đã cấp. Sự kiện **Joiner–Mover–Leaver** được xem là hoàn tất khi những quyền không còn hợp lệ đã được thu hồi tại cloud target, **quyền thực tế được xác minh**, và các ngoại lệ còn lại có người chịu trách nhiệm cùng bằng chứng kiểm toán.
