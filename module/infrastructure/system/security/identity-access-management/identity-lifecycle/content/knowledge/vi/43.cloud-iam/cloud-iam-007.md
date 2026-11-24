# Temporary cloud credential

**Chương:** Cloud IAM  
**Chủ đề:** Temporary cloud credential (thông tin xác thực đám mây tạm thời)  
**Phạm vi:** Quản lý quyền truy cập ngắn hạn cho con người và workload trong hệ thống **Identity and Access Management (IAM)**; kết nối IdP, SSO, SCIM, RBAC/ABAC, tài khoản dịch vụ, kiểm toán và mô hình **Joiner–Mover–Leaver (JML)**.

## 1. Temporary cloud credential là gì?

**Temporary cloud credential** là thông tin xác thực có thời gian hiệu lực giới hạn, được phát hành sau khi hệ thống xác minh một chủ thể và điều kiện cấp quyền. Nó cho phép một người hoặc workload thực hiện những yêu cầu được phép tới dịch vụ cloud trong **phạm vi và thời gian cụ thể**.

Ví dụ:

- Một kỹ sư đăng nhập SSO qua Identity Provider (IdP), chọn vai trò chỉ đọc trên một AWS account và nhận bộ thông tin xác thực AWS STS có hạn.
- Một ứng dụng chạy với Azure managed identity yêu cầu Microsoft Entra cấp access token để gọi API một tài nguyên cụ thể.
- Một service trên Google Cloud nhận OAuth access token thông qua metadata server hoặc cơ chế service account được hỗ trợ.
- Pipeline CI/CD xuất trình OIDC token do nền tảng CI phát hành, đổi lấy một phiên cloud ngắn hạn chỉ có quyền triển khai staging.

Điểm chung là **credential có thời điểm hết hiệu lực**, còn cách biểu diễn khác nhau giữa nhà cung cấp. Temporary credential có thể là **access token**, **session credential gồm nhiều thành phần**, hoặc một dạng chứng thực có hạn dùng được ứng dụng/dịch vụ đích chấp nhận. Không phải mọi token ngắn hạn đều là cùng một loại quyền.

### 1.1. Vì sao cần credential tạm thời?

Trong mô hình cũ, một script có thể chứa access key không có ngày hết hạn rõ ràng. Nếu key bị lộ, bị sao chép vào log hoặc còn trong repository sau khi ứng dụng ngừng hoạt động, đường truy cập vẫn có thể tồn tại cho đến khi key bị thu hồi.

Credential tạm thời giúp:

1. **Giới hạn thời gian phơi nhiễm:** Credential bị lộ chỉ có thể được sử dụng trong khoảng hiệu lực còn lại, trừ khi kẻ tấn công cũng kiểm soát được cơ chế phát hành hoặc làm mới.
2. **Giảm lưu trữ bí mật dài hạn:** Workload nhận credential tại runtime qua identity do nền tảng quản lý hoặc federation.
3. **Áp ngữ cảnh khi phát hành:** Chọn role, account/project, audience, điều kiện trust và một số giới hạn phiên theo khả năng của provider.
4. **Tăng khả năng kiểm toán:** Liên kết lần cấp phiên với principal nguồn, workload, yêu cầu phê duyệt và các thao tác cloud.
5. **Hỗ trợ JML:** Có thể ngăn phát phiên mới khi danh tính đổi vai trò hoặc kết thúc vòng đời, đồng thời xử lý credential/phiên còn sống.

**Giới hạn cần nhớ:** Một bearer token bị đánh cắp vẫn có thể bị dùng ngay trong thời hạn của nó. Credential tạm thời **không thay thế** ít quyền nhất, bảo vệ runtime, xác thực đúng issuer/audience, kiểm soát trust và thu hồi quyền tồn dư.

## 2. Phân biệt credential, token, role, session và quyền

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Identity** | Bản ghi nhận diện con người hoặc workload | Nhân viên EMP-6208; service reporting-api |
| **Principal** | Chủ thể được hệ thống IAM đánh giá cho một yêu cầu | Role session, managed identity, service account |
| **Authentication** | Xác minh bằng chứng danh tính | SSO với MFA; OIDC token do issuer tin cậy ký |
| **Authorization** | Quyết định principal được làm gì trên resource | Đọc một bucket, triển khai một service |
| **Role / policy** | Tập permissions và điều kiện được cấp hoặc đánh giá | Deployment role chỉ dành cho staging |
| **Credential** | Thông tin dùng để chứng minh hoặc thực hiện quyền truy cập | Access token, STS session credentials |
| **Session** | Trạng thái truy cập có hiệu lực trong một khoảng thời gian | Phiên cloud console hoặc assumed role session |
| **Issuer / STS** | Hệ thống phát bằng chứng hoặc đổi bằng chứng lấy quyền tạm thời | Corporate IdP, CI OIDC issuer, AWS STS |
| **Trust relationship** | Quy tắc xác định issuer/principal nào được phép nhận quyền đích | OIDC subject của pipeline được phép dùng một role |
| **Entitlement** | Quyền đang được gán cho danh tính, có thể tồn tại lâu hơn phiên | Group membership, IAM role assignment, IAM binding |

**Credential hết hạn không có nghĩa entitlement đã được thu hồi.** Người dùng vẫn thuộc nhóm cấp quyền có thể đăng nhập lại và được phát credential mới. Ngược lại, việc xóa entitlement có thể không làm một credential đã phát hành mất hiệu lực ngay lập tức. Đây là khác biệt quan trọng trong **Mover** và **Leaver**.

### 2.1. Những loại token dễ bị nhầm

| Loại | Mục đích chính | Có phải credential dùng trực tiếp để gọi mọi cloud API? |
| --- | --- | --- |
| **OIDC ID token** | Chứng minh kết quả xác thực cho client có audience phù hợp | **Không**; không sử dụng thay access token nếu API yêu cầu access token |
| **OAuth 2.0 access token** | Cho phép gọi resource server được chỉ định | Chỉ đối với resource/audience và quyền phù hợp |
| **Refresh token** | Yêu cầu cấp access token mới theo chính sách | Không dùng thay access token; thường có vòng đời khác và phải bảo vệ chặt |
| **SAML assertion** | Chuyển bằng chứng xác thực/thuộc tính giữa IdP và SP | Thường là đầu vào federation, không phải credential API cloud nói chung |
| **AWS STS session credentials** | Cho phép ký và thực hiện AWS API request với quyền phiên tạm thời | Có, dưới quyền role/session và các hạn chế áp dụng |
| **Kubernetes projected ServiceAccount token** | Chứng minh service account của Pod với audience được định | Thường dùng để xác thực tới Kubernetes API hoặc đổi token với cloud federation |
| **Signed URL / Azure SAS** | Trao quyền được ủy nhiệm cho tài nguyên/thao tác nhất định trong thời gian giới hạn | Là một **delegated capability**; không đồng nghĩa danh tính/role cloud tổng quát |
| **Service-account private key dài hạn** | Có thể ký/chứng minh danh tính hoặc nhận token theo cơ chế cụ thể | **Không phải** mô hình temporary credential chỉ vì token tạo từ key có hạn |

Signed URL hoặc Shared Access Signature (SAS) thường là **bearer capability**: ai có URL/token hợp lệ có thể sử dụng theo quyền và thời hạn được ký. Khả năng vô hiệu hóa trước hạn phụ thuộc cách ký, khóa và cơ chế dịch vụ; chặn SSO của người tạo không mặc nhiên thu hồi mọi URL đã phát hành.

## 3. Hai vòng đời khác nhau: entitlement và credential

Một hệ thống an toàn quản lý đồng thời:

- **Vòng đời entitlement:** Ai được cấp role/group/trust ở cloud đích? Quyền đó có còn phù hợp với trạng thái nhân sự hoặc workload?
- **Vòng đời credential/session:** Một lần truy cập được cấp bằng chứng gì, từ thời điểm nào tới thời điểm nào, có thể làm mới hoặc thu hồi bằng cách nào?

~~~mermaid
flowchart TD
    HR["HRIS / Workload registry<br/>Joiner - Mover - Leaver"] --> LIFE["IGA / Lifecycle<br/>Desired access + approvals"]
    LIFE --> IDP["IdP / Directory hoặc workload issuer"]
    LIFE --> GRANT["Cloud IAM entitlement<br/>Role, binding, trust, scope"]
    IDP --> AUTH["Xác thực người / workload"]
    AUTH --> EX["Federation / token exchange / STS"]
    GRANT --> EX
    EX --> CRED["Temporary credential + expiration"]
    CRED --> API["Cloud API / resource"]
    GRANT --> DECISION["Authorization tại resource"]
    API --> DECISION
    DECISION --> LOG["Audit events / monitoring"]
    LIFE -.-> RECON["Desired vs actual vs effective access"]
    GRANT -.-> RECON
    LOG -.-> RECON
~~~

**Điểm mấu chốt:** Thu hồi quyền tại IAM sẽ ngăn hoặc giới hạn những lần cấp hoặc sử dụng quyền tiếp theo theo cơ chế của provider, nhưng cần kiểm tra **credential đã phát hành trước thời điểm thu hồi**. Không được chỉ dựa trên việc IdP đã disable tài khoản.

### 3.1. Nguồn phát hành và bên chấp nhận khác nhau

Trong một luồng federation, **source token** do issuer A phát ra có thể chỉ dùng để **đổi lấy cloud credential** tại hệ thống B. Cloud credential có expiration và permissions riêng. Source token hết hạn không nhất thiết kéo theo cloud credential đã đổi hết hạn ngay.

~~~text
Source identity token: phát T1, hết hạn T2
Cloud session credential: phát T1b, hết hạn T3
Điều kiện: T1 <= T1b < T2; T3 có thể sau T2
Sự kiện Leaver: T4, xảy ra giữa T1b và T3

Tại T4:
  Ngăn xác thực / đổi credential mới theo chính sách.
  Thu hồi entitlement và credential/session đã cấp khi có cơ chế hỗ trợ.
  Đối soát quyền thực tế tới khi đạt trạng thái được xác minh.
~~~

Các mốc là **mô hình minh họa**, không quy định thời hạn cụ thể của AWS, Azure hoặc Google Cloud.

## 4. Thông tin và thuộc tính cần xác minh

Temporary credential có thể là bearer token dạng opaque, JWT, bộ khóa phiên hoặc định dạng riêng. **Không phải loại credential nào cũng có đủ các trường dưới đây**, nhưng những thuộc tính tương đương cần được hiểu trong thiết kế:

| Thuộc tính | Câu hỏi cần trả lời | Rủi ro nếu sai |
| --- | --- | --- |
| **Issuer** | Ai cấp bằng chứng/credential? | Nhận token từ nguồn không tin cậy |
| **Subject / principal** | Danh tính nguồn và chủ thể đích là ai? | Nhầm tài khoản, nhầm workload |
| **Audience / resource** | Token dành cho dịch vụ nào? | Replay hoặc dùng token dành cho hệ thống khác |
| **Not before / issued at** | Token bắt đầu có hiệu lực khi nào? | Chấp nhận trước thời điểm cho phép |
| **Expiration** | Khi nào token/credential hết hiệu lực? | Quyền sống quá lâu hoặc gián đoạn nếu TTL quá ngắn |
| **Role / scope / claims** | Credential có ý nghĩa quyền gì? | Quyền quá rộng hoặc nhầm môi trường |
| **Session/source correlation** | Phiên bắt nguồn từ sự kiện, workload, phê duyệt nào? | Không truy vết được khi điều tra |
| **Revocation / renewal method** | Có thể hủy hoặc làm mới thế nào? | Leaver bị coi là hoàn tất khi token cũ vẫn hoạt động |

Ví dụ metadata cho hệ thống kiểm toán, **không phải nội dung access token hay credential thực tế**:

~~~json
{
  "credentialEventId": "CRED-2026-0620",
  "sourceIdentityId": "WORKLOAD-reporting-staging",
  "sourceIssuer": "https://ci.example.invalid",
  "sourceSubject": "repo:example/reporting:environment:staging",
  "cloudTarget": "staging-reporting",
  "cloudRole": "reporting-staging-deployer",
  "issuedAt": "2026-11-23T07:00:00Z",
  "expiresAt": "2026-11-23T07:30:00Z",
  "verificationState": "issued"
}
~~~

**Đừng ghi bearer token, session token, secret access key hoặc refresh token thực vào log** chỉ để thu thập bằng chứng. Dùng ID, hash an toàn nếu có cơ sở kỹ thuật phù hợp, correlation metadata và thời gian; bảo vệ log khỏi tiết lộ dữ liệu nhạy cảm.

## 5. Luồng phát hành temporary credential cho người dùng

Với nhân viên, sự kiện đăng nhập thường bắt đầu tại IdP doanh nghiệp. Cloud là **relying party/service provider** tin cậy danh tính được chứng minh theo SAML hoặc OIDC và sau đó áp IAM.

~~~mermaid
sequenceDiagram
    participant U as Nhân viên
    participant I as Corporate IdP / SSO
    participant F as Cloud federation service
    participant A as Cloud IAM
    participant R as Cloud resource
    U->>I: Đăng nhập + MFA theo policy
    I-->>U: SAML assertion / OIDC identity proof
    U->>F: Chuyển bằng chứng cho đích tin cậy
    F->>F: Kiểm tra issuer, audience, signature, expiry
    F->>A: Ánh xạ principal + role/scope được duyệt
    A-->>F: Kết quả trust và entitlement
    F-->>U: Cloud session / temporary credential
    U->>R: Gọi API hoặc mở console
    R->>A: Kiểm tra quyền hành động/tài nguyên
    A-->>R: Allow hoặc Deny
    R-->>U: Kết quả truy cập
~~~

Sơ đồ mô tả một mẫu logic, không phải giao thức cố định cho mọi console. Có nền tảng dùng cookie phiên, có nền tảng phát token qua SDK hoặc role session; các điểm kiểm soát vẫn là **xác thực đúng nguồn, ánh xạ quyền đúng và kiểm soát thời gian hiệu lực**.

### 5.1. Vì sao SSO không đủ để bảo đảm Leaver?

SSO giúp ngăn **đăng nhập mới** sau khi IdP disable tài khoản. Tuy nhiên có thể còn:

- Cloud console session hoặc API credential đã cấp trước đó.
- Refresh token ở những hệ thống sử dụng loại token này.
- IAM role assignment trực tiếp không thuộc nhóm đã được xóa.
- Local cloud user, access key, guest account hoặc quyền thuộc một tenant khác.
- Quyền assume role/impersonate service account.

Quy trình Leaver phải thu hồi và **kiểm chứng quyền ở các cloud target**, kết hợp phương án xử lý session theo khả năng thực tế của provider.

## 6. Luồng phát hành temporary credential cho workload

Với workload, **máy hoặc chương trình** cần chứng minh danh tính mà không dùng mật khẩu cá nhân. Các cơ chế thường thấy: managed identity, instance/task/execution role, projected Kubernetes ServiceAccount token, OIDC federation của CI/CD và service account impersonation.

~~~mermaid
sequenceDiagram
    participant W as Workload / CI job
    participant S as Runtime identity / OIDC issuer
    participant T as Cloud STS / token endpoint
    participant P as Cloud IAM trust + permissions
    participant R as Cloud API
    W->>S: Lấy identity evidence đúng workload
    S-->>W: Token hoặc chứng thực có hạn
    W->>T: Yêu cầu đổi lấy cloud credential
    T->>T: Xác minh issuer, audience, subject, signature, exp
    T->>P: Kiểm tra principal có được nhận role không
    P-->>T: Cho phép hoặc từ chối
    T-->>W: Temporary cloud credential
    W->>R: Thực hiện thao tác trong scope được cấp
    R->>P: Đánh giá quyền tài nguyên
    P-->>R: Allow hoặc Deny
    R-->>W: Kết quả
~~~

Đây là mô hình federation. Một workload chạy ngay trong cloud có thể nhận credential trực tiếp qua metadata service hoặc credential provider của SDK, **không cần tự triển khai HTTP token exchange**.

### 6.1. Trust và permissions phải được kiểm soát riêng

**Trust:** Workload nào được phép nhận credential? Cần xem issuer, audience, subject, repository, namespace, branch/environment và các điều kiện mà provider thực sự hỗ trợ.

**Permissions:** Khi có credential, workload được làm những action nào trên resource và scope nào? Role deployment không nên mặc nhiên có quyền đọc dữ liệu production hoặc sửa IAM.

Nếu issuer và subject quá rộng, **credential tạm thời vẫn có thể được phát liên tục cho workload không mong muốn**. TTL ngắn không thay thế điều kiện trust hẹp.

## 7. AWS STS: temporary security credentials

**AWS Security Token Service (STS)** cung cấp các thao tác phát **temporary security credentials** để truy cập tài nguyên AWS trong một số luồng được hỗ trợ. Một bộ STS credentials thường gồm:

- **AccessKeyId:** ID của khóa truy cập cho phiên.
- **SecretAccessKey:** Thành phần bí mật dùng ký AWS API requests.
- **SessionToken:** Session token đi kèm bộ khóa tạm thời.
- **Expiration:** Thời điểm credential hết hiệu lực.

**Cả SecretAccessKey và SessionToken đều là thông tin nhạy cảm.** Không đưa vào Git, ticket, log, bản chụp màn hình hoặc output job được chia sẻ.

### 7.1. Các luồng phát hành thông dụng

| Luồng | Chủ thể / hoàn cảnh | Điểm kiểm soát |
| --- | --- | --- |
| **AssumeRole** | Principal được phép đảm nhận IAM role | Trust policy của role, quyền cần thiết, session và permissions |
| **AssumeRoleWithSAML** | Federation SAML từ IdP phù hợp | Chữ ký assertion, issuer, audience, role mapping, trust |
| **AssumeRoleWithWebIdentity** | Web identity/OIDC token được tin cậy | OIDC provider, claims/conditions, role trust, token TTL |
| **GetSessionToken** | Trường hợp cần phiên tạm thời dựa trên IAM user credentials | Bảo vệ credential nguồn, MFA và giới hạn tương ứng |
| **EC2/Lambda/ECS/EKS runtime role** | Workload dùng role/identity do nền tảng tích hợp | Không lưu key cứng; giữ quyền và ranh giới runtime đủ hẹp |

**Phần lớn workload nên ưu tiên IAM role phù hợp hoặc federation thay vì quản lý IAM user access key dài hạn.** Hình thức phát token phụ thuộc runtime và dịch vụ.

### 7.2. AWS IAM role: trust và permissions

Một role có **trust policy** trả lời “ai được assume role?”, và **permissions policy** trả lời “phiên role được làm gì?”. Một số lớp giới hạn như **Service Control Policies (SCP)**, permissions boundary, session policy và resource policy cũng có thể ảnh hưởng quyền theo ngữ nghĩa AWS.

~~~yaml
# GIẢ MÃ yêu cầu bảo mật, KHÔNG phải AWS IAM policy JSON
role: learning-staging-artifact-reader
trust:
  issuer: approved-ci-issuer
  audience: expected-cloud-token-exchange
  subject:
    repository: org/learning-api
    environment: staging
permissions:
  allow:
    - action: artifact.read
      resource: staging-artifacts
session:
  duration: bounded-by-approved-policy
owner: platform-team
~~~

Điều kiện trong trust và tên action/resource trên đây là **mô tả nghiệp vụ**, không phải cú pháp AWS có thể triển khai nguyên trạng. Khi triển khai phải dùng đúng condition keys, ARN, tên API, yêu cầu quyền phía nguồn và giới hạn phiên mà AWS hỗ trợ.

### 7.3. Dùng SDK credential provider thay cho tự lưu token

SDK của AWS thường có credential provider chain hoặc provider riêng cho runtime; ứng dụng có thể lấy và làm mới role credentials theo cơ chế chuẩn. Cần:

1. Gắn role đúng cho instance, task, function, pod hoặc pipeline.
2. Chọn provider/SDK hỗ trợ refresh tự động và xử lý thời hạn đúng.
3. Không log toàn bộ credential object.
4. Tránh tạo file credential tạm lưu vô hạn trên đĩa hay trong artifact CI.
5. Kiểm tra principal thực tế và quyền của service bằng công cụ phù hợp, chẳng hạn truy vấn danh tính caller trong môi trường kiểm soát.

**Tự gọi STS mỗi request** thường không cần thiết và có thể tạo vấn đề tải, giới hạn API hoặc lỗi đồng bộ. Nên sử dụng cache và refresh có kiểm soát của SDK phù hợp.

### 7.4. Thu hồi AWS STS sessions

Xóa quyền assume role thường ảnh hưởng **những lần assume mới**; session được cấp trước đó có thể còn hiệu lực. AWS có các cơ chế quản trị để hạn chế hoặc thu hồi phiên role tùy kịch bản, chẳng hạn áp điều kiện từ chối các session được phát trước một mốc, nhưng **không nên khẳng định mọi STS credential sẽ bị hủy ngay chỉ vì người dùng bị disable ở IdP**.

Với Leaver hoặc sự cố, cần kiểm tra role trust, permissions, phiên đã cấp, role sessions có liên quan và các đường access key khác; ghi nhận hiệu lực thực tế sau khi áp biện pháp thu hồi.

## 8. Microsoft Azure và Entra: access token cho workload

Trong Azure, một workload có thể dùng **managed identity** hoặc **service principal** để yêu cầu **Microsoft Entra access token** cho resource cụ thể. Token được dịch vụ đích chấp nhận theo audience/issuer và các kiểm tra của dịch vụ; **Azure RBAC** hoặc authorization riêng của resource quyết định hành động được phép.

### 8.1. System-assigned và user-assigned managed identity

| Loại identity | Vòng đời | Hệ quả JML |
| --- | --- | --- |
| **System-assigned managed identity** | Gắn với một tài nguyên Azure hỗ trợ | Khi tài nguyên bị xóa, identity liên quan thường được xóa theo cơ chế dịch vụ; vẫn cần kiểm tra quyền và dữ liệu phụ thuộc |
| **User-assigned managed identity** | Là một tài nguyên riêng có thể dùng cho nhiều workload được hỗ trợ | Xóa một workload không tự xóa identity này; phải rà soát owner, RBAC assignment và các liên kết còn tồn tại |
| **Service principal với federated credential** | Ứng dụng hoặc principal được cấu hình nhận chứng thực từ issuer ngoài | Khi repository hoặc nguồn thay đổi, phải sửa/xóa federated credential và rà soát role đích |
| **Service principal với secret/certificate** | Dùng bí mật hoặc chứng thư làm bằng chứng danh tính | Token nhận được có thể ngắn hạn nhưng bí mật nguồn vẫn cần rotation, expiry, lưu trữ và thu hồi |

**Managed identity giảm việc tự quản lý secret**, nhưng không tự bảo đảm role nhỏ nhất. Một managed identity được gán Owner ở scope rộng vẫn có quyền lớn khi yêu cầu được xác thực hợp lệ.

### 8.2. Access token có audience và thời hạn riêng

Access token dành cho Azure Resource Manager, Storage hoặc một dịch vụ khác **không mặc nhiên dùng được ở mọi API**. Cần chỉ định resource/scope phù hợp, kiểm tra thời hạn và chọn SDK credential provider tương ứng.

Không mặc định thời hạn access token là một con số cố định; thời hạn có thể thay đổi theo loại token, ứng dụng, điều kiện truy cập và hỗ trợ của hệ thống. Một số dịch vụ và tình huống hỗ trợ **Continuous Access Evaluation (CAE)**, nhưng không phải mọi access token đều có khả năng thu hồi ngay theo cùng cách.

### 8.3. Federated identity credential cho CI/CD

Workload ngoài Azure có thể xuất trình OIDC token và dùng **federated identity credential** để liên kết với một Entra application/service principal hoặc managed identity trong các kịch bản được hỗ trợ. Ràng buộc issuer, subject và audience phải khớp với nguồn CI đã duyệt.

Sau token exchange, ứng dụng chỉ được thao tác tài nguyên nếu **principal đích có role assignment hoặc quyền dữ liệu cần thiết**. Gán quyền dựa trên scope quá rộng vẫn nguy hiểm dù credential chỉ sống ngắn.

### 8.4. Thu hồi và đối soát

Khi workload retire hoặc nhân viên đổi vai trò, cần xem xét:

- RBAC assignments trực tiếp và kế thừa.
- Managed identities còn liên kết với tài nguyên khác.
- Federated identity credentials tiếp tục tin repository/environment cũ.
- Secrets/certificates gắn với ứng dụng.
- Access token đã phát hành, refresh mechanisms và khả năng thu hồi theo từng loại dịch vụ.

Chỉ xóa một Pod, function hoặc bản ghi group chưa chứng minh **mọi token hoặc quyền cloud** đã mất.

## 9. Google Cloud: short-lived tokens và service account impersonation

Google Cloud có các cơ chế cấp credential tạm cho workload:

1. **Service account gắn với runtime:** Compute/GKE hoặc dịch vụ được hỗ trợ dùng metadata/credential provider để nhận token thay vì lưu khóa private tĩnh.
2. **Service account impersonation:** Principal nguồn có quyền phù hợp yêu cầu **IAM Service Account Credentials API** tạo access token hoặc token hỗ trợ cho một service account đích.
3. **Workload Identity Federation:** Token từ issuer ngoài Google Cloud được xác minh qua workload identity pool/provider và trao đổi qua **Security Token Service (STS)**; có thể cấp IAM access trực tiếp cho federated principal hoặc qua service account impersonation tùy thiết kế.

### 9.1. Token trao đổi không đồng nghĩa mọi quyền API

Token từ OIDC issuer ngoài cloud thường dùng để **chứng minh workload nguồn**. STS hoặc phương thức federation đổi bằng chứng này lấy quyền phù hợp. Sau đó IAM vẫn đánh giá quyền trên project/resource, bao gồm bindings và những hạn chế áp dụng.

~~~yaml
# Mô tả thiết kế, KHÔNG phải cấu hình Google Cloud có thể dùng trực tiếp
workload:
  issuer: approved-ci
  subject: org/reporting/environment/staging
googleTarget:
  project: reporting-staging
  mode: service-account-impersonation
  serviceAccount: reporting-deployer@example-project.iam.gserviceaccount.com
permissions:
  - deploy-only-reporting-staging
session:
  shortLived: true
owner: reporting-platform
~~~

Với impersonation, phải quản lý **cả quyền của principal được impersonate** và **quyền cho phép principal nguồn impersonate**. Nếu service account đích có Owner/Editor rộng, workload nguồn có thể sở hữu quyền gián tiếp lớn hơn grant trực tiếp của nó.

### 9.2. Access token và ID token có mục đích khác

**OAuth access token** được dùng cho resource/API phù hợp. **Service account ID token** thường phục vụ chứng minh danh tính với audience cụ thể, ví dụ một dịch vụ HTTP kiểm tra OIDC; không được dùng như access token cho API yêu cầu OAuth token.

Không nên tạo hoặc tải về **service account private key** chỉ để có token có hạn nếu nền tảng đã hỗ trợ impersonation, federation hoặc attached service account.

### 9.3. Kiểm tra khi Leaver

Trong deprovision:

- Xóa IAM bindings hoặc quyền impersonation đã hết lý do.
- Thu hồi/đóng federation provider/trust theo phạm vi hợp lệ.
- Rà soát service account keys, user-managed keys và owner.
- Kiểm tra access tokens/session tồn tại theo thời hạn và khả năng xử lý thực tế.
- Đọc lại quyền IAM và kiểm tra thao tác không còn được phép trong kịch bản an toàn.

## 10. Kubernetes ServiceAccount token và cloud credential

Kubernetes có khái niệm **ServiceAccount** cho workload trong Pod. Token projected từ Kubernetes thường là JWT có **audience và thời hạn**, có thể được dùng để xác thực với Kubernetes API hoặc làm bằng chứng trong một cơ chế cloud workload identity federation phù hợp.

**Kubernetes ServiceAccount không đồng nghĩa Google Cloud IAM service account**, và Kubernetes **Role/ClusterRole** kiểm soát Kubernetes API, không tự cấp quyền truy cập AWS S3, Azure Storage hay Google Cloud Storage.

### 10.1. Pod nhận quyền cloud như thế nào?

Tùy nền tảng:

- **Amazon EKS:** IRSA hoặc EKS Pod Identity theo cơ chế hỗ trợ, ánh xạ identity Pod/ServiceAccount sang AWS IAM role.
- **Azure AKS:** Microsoft Entra Workload ID có thể dùng projected service account token và federated credential để nhận access token của principal đích.
- **Google Kubernetes Engine:** Workload Identity Federation for GKE có thể liên kết workload với principal/role Google Cloud phù hợp.

Trong mỗi trường hợp, cần xem **Kubernetes identity, cấu hình trust, cloud principal và IAM permissions**. Một namespace hoặc cluster bị cấp quyền cloud rộng có thể tạo rủi ro lan sang nhiều Pod.

### 10.2. Projected token và audience

~~~yaml
# Minh họa một phần Kubernetes Pod; nhà cung cấp cloud cần cấu hình federation riêng
apiVersion: v1
kind: Pod
metadata:
  name: reporting-api
  namespace: reporting-dev
spec:
  serviceAccountName: reporting-api
  containers:
    - name: app
      image: registry.example.invalid/reporting-api:v1
      volumeMounts:
        - name: identity-token
          mountPath: /var/run/identity
          readOnly: true
  volumes:
    - name: identity-token
      projected:
        sources:
          - serviceAccountToken:
              path: token
              expirationSeconds: 3600
              audience: cloud-token-exchange
~~~

Đây là ví dụ về **cơ chế project token**, chưa phải manifest triển khai cloud federation hoàn chỉnh. Audience được chọn phải trùng với nơi tiêu thụ token và khả năng của provider; expiration trong manifest là cấu hình yêu cầu, thời hạn thực tế có thể chịu giới hạn của Kubernetes và thiết lập cluster.

### 10.3. Rủi ro khi Pod bị xâm nhập

Nếu mã chạy trong Pod bị khai thác, kẻ tấn công có thể đọc token hoặc temporary credential khả dụng trong Pod trong thời gian token còn hiệu lực. Do đó cần:

- Cấu hình ServiceAccount riêng cho workload.
- Hạn chế quyền ai được sửa Pod, Deployment, ServiceAccount và admission controls.
- Bảo vệ metadata endpoints và đường truy cập credential của node.
- Giảm quyền cloud và Kubernetes API riêng rẽ.
- Không lưu token vào log, crash dump, artifact CI hoặc image.
- Dùng quyền ngắn hạn, điều kiện trust và network/runtime isolation thích hợp.

## 11. CI/CD OIDC: không lưu access key dài hạn

Pipeline thường cần quyền triển khai, phát hành artifact hoặc đọc kết quả scan. **OIDC federation** cho phép job lấy identity token do CI issuer phát hành rồi đổi lấy cloud credential tạm, hạn chế việc quản lý key tĩnh.

### 11.1. Thiết kế theo hai lớp

**Lớp trust:** Chỉ job có issuer, audience, repository, branch/tag, workflow hoặc environment đúng được chấp nhận. Các claim phải có ngữ nghĩa đáng tin từ issuer và được cloud target hỗ trợ.

**Lớp permissions:** Cloud role chỉ được quyền deploy đúng ứng dụng và môi trường. Không cấp quản trị IAM hoặc đọc secret production nếu job chỉ cần push artifact staging.

Ví dụ chính sách nghiệp vụ:

~~~yaml
# Giả mã trung lập với cloud provider
source:
  issuer: https://ci.example.invalid
  audience: cloud-sts
  subject:
    repository: example-org/learning-api
    environment: staging
destination:
  role: learning-staging-deployer
  account: staging-learning
  actions:
    - deploy-approved-release
    - read-approved-artifacts
session:
  maxDuration: according-to-security-policy
owner: learning-platform
~~~

### 11.2. Kiểm thử phải có các trường hợp bị từ chối

| Kịch bản | Kết quả mong đợi |
| --- | --- |
| Token đúng issuer, subject, audience, còn hiệu lực | Có thể đổi lấy phiên nếu các điều kiện khác đúng |
| Token từ repo khác trong cùng tổ chức | Từ chối nếu không nằm trong trust được duyệt |
| Token dành cho audience khác | Từ chối |
| Token hết hạn, chữ ký sai hoặc issuer không được tin cậy | Từ chối |
| Job đúng được cấp role nhưng cố đọc secret production | Từ chối theo permissions |
| Repository đã retire nhưng token mới vẫn được phát | Không đổi được cloud credential sau khi trust bị thu hồi |
| Session đã cấp trước thay đổi trust | Theo dõi, xử lý theo khả năng revocation/TTL |

**Bảo vệ repository và workflow** cũng quan trọng: ai có quyền sửa pipeline production có thể kích hoạt job và sử dụng role mà pipeline được cấp. Branch protection, review và approval môi trường phải đi cùng trust policy.

## 12. Thời hạn, refresh, cache và đồng hồ

Credential tạm thời cần được sử dụng **trước khi hết hạn** và làm mới một cách an toàn. Không nên chọn TTL theo cảm tính: thời gian quá dài tăng rủi ro, quá ngắn có thể làm gián đoạn dịch vụ nếu runtime thường xuyên mất kết nối với token issuer.

### 12.1. Các thời hạn khác nhau

| Thời hạn | Ý nghĩa | Điều cần nhớ |
| --- | --- | --- |
| **Source token TTL** | Identity token của CI/IdP còn hiệu lực để trình với target | Hết hạn có thể ngăn exchange mới |
| **Cloud credential TTL** | STS session hoặc access token đích còn hiệu lực | Có thể khác source token TTL |
| **Refresh capability** | Runtime có thể xin token mới hay không | Phụ thuộc tư cách principal, trust và credential nguồn |
| **Entitlement lifetime** | Role/binding/trust còn hợp lệ | Có thể dài hơn nhiều session |
| **Business approval expiry** | Quyền được phê duyệt tới ngày/giờ nào | JML phải ngăn cấp mới và thu hồi entitlement khi hết hạn |

Một quyền được phê duyệt trong một giờ **không nhất thiết** tương đương việc phát token có thời hạn một giờ: role assignment có thể còn tồn tại sau đó nếu không có workflow gỡ. Cần thực thi cả **hạn quyền** lẫn **hạn phiên**.

### 12.2. Refresh an toàn trong ứng dụng

Một mẫu logic:

~~~text
credentialProvider = cloudSdk.providerForCurrentRuntime()

beforeEachRequest:
    credential = credentialProvider.currentValidCredential()
    if credential.nearExpiry:
        credentialProvider.refreshWithBackoffAndJitter()
    if noValidCredential:
        failClosedAndReport()
    else:
        sendSignedOrAuthorizedCloudRequest(credential)
~~~

Đây là giả mã; nhiều SDK đã tích hợp cache/refresh, ứng dụng **không cần tự gọi refresh ở mỗi request**. Các nguyên tắc quan trọng:

- Refresh trước hạn với khoảng đệm phù hợp, không chờ token vừa hết hạn mới xin lại.
- Tránh hàng nghìn instance đồng loạt refresh, dùng backoff/jitter hoặc provider SDK được hỗ trợ.
- Có độ lệch đồng hồ cho phép theo giao thức; đồng bộ thời gian hệ thống.
- Không fallback sang key tĩnh quyền cao nếu refresh thất bại.
- Không tiếp tục dùng token đã quá hạn chỉ để “cứu” một request.
- Trường hợp IAM bị thu hồi phải dẫn tới **không được cấp quyền mới**, không retry vô hạn bằng credential không hợp lệ.

### 12.3. Failure mode hay gặp

| Lỗi | Biểu hiện | Xử lý |
| --- | --- | --- |
| Token hết hạn giữa các request | API trả lỗi xác thực | Provider refresh đúng cách, retry idempotent khi phù hợp |
| Đồng hồ runtime lệch | Token bị đánh giá chưa có hiệu lực hoặc đã hết hạn | Đồng bộ thời gian, không nới lỏng kiểm tra tùy tiện |
| Issuer/STS bị gián đoạn | Không cấp token mới | Sử dụng cache còn hợp lệ theo chính sách, circuit breaker, cảnh báo |
| Thay trust nhưng không cập nhật claim | Token exchange bị từ chối | So issuer/aud/sub và version cấu hình |
| Role permissions sai | Token được cấp nhưng resource API từ chối | Phân biệt lỗi xác thực với lỗi phân quyền |
| Provider cache không được refresh | Ứng dụng lặp lại credential hết hạn | Dùng SDK/provider hỗ trợ hoặc sửa luồng refresh |

## 13. Thu hồi: ngăn cấp mới và vô hiệu hóa phiên cũ

**Revocation** không phải một thao tác giống nhau trên tất cả nhà cung cấp. Cần phân biệt **ngăn nguồn cấp token mới**, **thu hồi quyền** và **xử lý credential/session đã được phát hành**.

~~~mermaid
flowchart TD
    E["Sự kiện Mover / Leaver / incident"] --> S["Chặn hoặc hạn chế source identity"]
    E --> G["Thu hồi group, role, binding, trust"]
    S --> N["Ngăn đăng nhập/exchange mới"]
    G --> N
    E --> P["Liệt kê session, key và đường access liên quan"]
    P --> D{"Provider có cơ chế revoke phù hợp?"}
    D -->|Có| R["Revoke / deny / invalidate theo cơ chế hỗ trợ"]
    D -->|Không ngay| T["Giám sát TTL, giảm quyền, chặn khả năng sử dụng khi khả thi"]
    R --> V["Readback và xác minh quyền"]
    T --> V
    N --> V
    V --> F{"Đạt desired state?"}
    F -->|Có| OK["VERIFIED + bằng chứng"]
    F -->|Chưa| X["EXCEPTION + owner + hạn xử lý"]
~~~

### 13.1. Bốn việc không thể gộp làm một

1. **Disable IdP account:** Thường ngăn xác thực mới, nhưng không đảm bảo mọi cloud session đã biến mất ngay.
2. **Remove role assignment / trust:** Giảm hoặc chặn một đường cấp quyền, nhưng còn đường khác hoặc session cũ phải kiểm tra riêng.
3. **Revoke key/token/session:** Chỉ làm được theo loại credential, provider và phạm vi API hỗ trợ; phải biết token nào có thể bị vô hiệu hóa.
4. **Verify effective access:** Đọc lại và/hoặc kiểm tra hành động được phép/từ chối tại đích, có bằng chứng thời điểm kiểm tra.

### 13.2. Không đồng nhất JWT tự chứa với tra cứu trạng thái trực tuyến

Một JWT có thể được dịch vụ kiểm tra bằng chữ ký và thời hạn mà không truy vấn trạng thái phiên ở IdP trên mỗi request. Vì vậy **xóa user ở nguồn không bắt buộc làm token đã phát hành không còn được dịch vụ chấp nhận ngay**. Một số cơ chế revocation, introspection, CAE hoặc deny policy có thể rút ngắn khoảng này, nhưng phải xác minh đúng dịch vụ/luồng.

Trong ứng phó sự cố, cần biết chính xác **đường truy cập nào vẫn còn hợp lệ tới khi nào**, và biện pháp chặn bổ sung có được hệ thống đích thực thi không.

## 14. Joiner–Mover–Leaver cho người dùng

Temporary credential liên kết trực tiếp với vòng đời quyền của một người, nhưng một credential **không phải nguồn thẩm quyền** xác nhận người đó còn làm việc. HRIS hoặc nguồn được ủy quyền mới quyết định trạng thái tư cách.

| Giai đoạn | Sự kiện | Hành động | Tiêu chí xác minh |
| --- | --- | --- | --- |
| **Joiner** | Nhân viên/đối tác được xác minh và được duyệt quyền | Tạo/liên kết IdP; gán nhóm/role đúng scope; bật SSO/MFA; cấu hình phiên ngắn hạn | Nhận đúng quyền, thao tác ngoài phạm vi bị từ chối |
| **Mover** | Đổi chức vụ, team, dự án, account hoặc thời hạn hợp đồng | Tính lại desired entitlements; thu hồi quyền cũ; cập nhật role mapping; kiểm tra session | Không còn quyền từ vai trò cũ ngoài ngoại lệ được duyệt |
| **Leaver** | Nghỉ việc, chấm dứt hợp đồng hoặc khóa khẩn cấp | Disable IdP; gỡ grants/keys; revoke session theo hỗ trợ; rà soát tài khoản cloud-local | Không còn đường truy cập ngoài mong muốn, có bằng chứng |

### 14.1. Joiner: người có quyền phải là người đã xác minh

Giả sử nhân viên **Quân**, mã nguồn **EMP-6208**, được nhận vào đội SRE. HRIS tạo sự kiện Joiner; IdP gắn một subject ổn định và chính sách MFA. IGA gán nhóm chỉ đọc log production, nhưng không gán quyền sửa IAM.

Quân đăng nhập SSO và nhận cloud session có hạn. Việc cấp quyền cần gắn **person ID, issuer/subject, cloud principal/role, account scope, owner phê duyệt, thời hạn và kết quả kiểm tra**. Không dựa riêng vào email có thể đổi/tái sử dụng để ghép account.

### 14.2. Mover: TTL ngắn không tự thu hồi role cũ

Quân chuyển sang Analytics. Nếu nhóm SRE cũ vẫn còn, session hiện tại sớm hết hạn nhưng Quân có thể **đăng nhập lại và tiếp tục được cấp phiên SRE**. Vì vậy:

1. Nhận sự kiện Mover có thời điểm hiệu lực.
2. Tính desired access của đội mới.
3. Gỡ SRE role assignment/group/binding không còn hợp lệ.
4. Kiểm tra các đường cấp trực tiếp, trust, local account và session được phát hành trước.
5. Ghi nhận kết quả từng cloud target; chỉ đánh dấu hoàn tất khi đã xác minh.

### 14.3. Leaver: khóa nguồn, thu hồi đích, kiểm tra phiên

Khi Quân nghỉ việc, disable IdP là bước đầu. IAM lifecycle phải đối soát mọi cloud account/subscription/project và thu hồi role, key, guest/local account, API token hoặc quyền impersonation của người đó. Nếu một session đã được phát hành và chưa thể revoke ngay, phải ghi ngoại lệ có owner, thời gian hết hạn hoặc biện pháp chặn bổ sung.

**Không xóa role dùng chung của 40 nhân viên** chỉ vì Quân nghỉ; cần xóa assignment hoặc quyền cụ thể của Quân. Role definition được quản lý trong vòng đời riêng.

## 15. Joiner–Mover–Leaver cho workload và tài khoản dịch vụ

Workload không có HRIS; nguồn chuẩn có thể là **service catalog, CMDB, kho IaC, CI/CD registry hoặc hệ thống quản lý tích hợp**. Mỗi workload cần ID ổn định, owner chính/dự phòng và thông tin runtime.

### 15.1. Joiner: tạo quyền đúng cho ứng dụng

Một workload mới cần:

- Workload ID, ứng dụng, owner và trạng thái hoạt động.
- Runtime identity và issuer/metadata source được tin cậy.
- Role/trust cụ thể cho dev/staging/production.
- Phạm vi quyền theo action và resource tối thiểu.
- Cơ chế lấy credential ngắn hạn và lịch refresh an toàn.
- Log cấp phiên/sử dụng API, review định kỳ và cơ chế retire.

Ví dụ metadata workflow:

~~~yaml
# Dữ liệu quản trị, không phải policy cloud
workloadId: learning-reporting-staging
owner: learning-platform
runtime: ci-pipeline
identitySource: approved-oidc-issuer
repository: org/learning-reporting
environment: staging
cloudTarget: reporting-staging
role: staging-artifact-reader
staticKeyAllowed: false
credentialLifetime: short
reviewCadence: quarterly
state: active
~~~

### 15.2. Mover: đổi nguồn, môi trường hoặc owner

Khi pipeline đổi repository hoặc chuyển từ staging sang production, cần **cập nhật subject/issuer/trust và quyền đích**. Thêm quyền production mà giữ trust staging quá rộng hoặc quyền trên account cũ sẽ tạo residual access.

Nếu có giai đoạn chuyển tiếp cho cả hai môi trường, ngoại lệ phải ghi rõ owner, scope và thời hạn. Sau migration cần đọc lại target và thu hồi các grants không còn hợp lệ.

### 15.3. Leaver: retire workload

Khi service hoặc job ngừng:

1. Xác minh không còn dependency cần giữ hoặc đã chuyển giao đầy đủ.
2. Xóa trust/federated credential và role/binding không còn hợp lệ.
3. Disable/delete identity riêng khi phù hợp, xử lý key tĩnh, token và secret.
4. Kiểm tra temporary credentials đã phát hành theo khả năng revoke/expiry.
5. Đối soát tất cả account/project/resource đích; lưu kết quả.

**Xóa Kubernetes Pod hoặc archive repository không tự xóa cloud role, service account hoặc user-assigned managed identity.** Những đối tượng này có vòng đời riêng cần được kiểm tra.

### 15.4. Khi người sở hữu workload nghỉ việc

Nếu lập trình viên nghỉ việc nhưng ứng dụng vẫn hoạt động, chuyển owner sang nhóm có thẩm quyền; đảm bảo workload dùng identity riêng và credential được bảo vệ. Nếu pipeline từng dùng secret cá nhân, cần thu hồi/rotation; không để ứng dụng tiếp tục hoạt động nhờ credential của người đã rời công ty.

## 16. Least privilege, RBAC/ABAC và cấp quyền có thời hạn

Credential tạm thời chỉ thu hẹp **thời gian sử dụng**, không tự thu hẹp **phạm vi quyền**. IAM phải giới hạn:

| Chiều | Ví dụ phù hợp | Ví dụ không phù hợp |
| --- | --- | --- |
| **Action** | Chỉ đọc object báo cáo | Toàn quyền IAM và Storage |
| **Resource** | Một bucket hoặc một service cụ thể | Mọi resource toàn organization |
| **Environment** | Chỉ staging | Quyền production do job thử nghiệm |
| **Principal** | Một workload ID được phê duyệt | Bất kỳ repo nào cùng CI issuer |
| **Time** | Credential ngắn hạn, elevation có hạn | Static access key không rõ hạn |
| **Context** | Trust theo claim, audience và thuộc tính được quản trị | Tin nhãn/claim do principal có thể tự sửa |

**RBAC** cấp quyền theo role; **ABAC** dùng thuộc tính của principal, tài nguyên và ngữ cảnh khi hệ thống hỗ trợ. Việc giới hạn phiên/credential không thay thế quản trị nhóm và role sau Mover.

### 16.1. JIT privileged access khác temporary credential

**Just-in-time (JIT) privileged access** là quyết định **cấp quyền nhạy cảm trong một cửa sổ đã duyệt**. Temporary credential là cơ chế **mang quyền truy cập được phát hành có hạn dùng**. Có thể kết hợp chúng:

~~~text
12:00  Người trực xin quyền can thiệp service production
12:02  Chủ sở hữu phê duyệt JIT trong cửa sổ 30 phút
12:03  IAM mở role/assignment đủ hẹp; người dùng nhận session
12:30  Workflow kết thúc entitlement quyền cao theo phê duyệt
12:31  Đối soát assignment và session, áp thu hồi khi hỗ trợ
12:35  Lưu kết quả VERIFIED hoặc EXCEPTION có owner
~~~

**Kết thúc cửa sổ JIT không tự bảo đảm session đã phát hành hết hiệu lực.** Cần biết TTL credential, cách revoke và cách xác minh quyền thực tế.

### 16.2. Đường nâng đặc quyền gián tiếp

Một workload có token chỉ mang role đọc log nhưng đồng thời có quyền **sửa trust policy**, **impersonate service account mạnh**, **đọc secret chứa key admin** hoặc **sửa deployment pipeline production** có thể thực tế có khả năng lớn hơn mô tả role. Access review cần xét các đường này.

## 17. Khi credential bị lộ: xử lý sự cố

Một token có hạn ngắn bị lộ vẫn có thể bị lạm dụng trong thời gian còn hiệu lực. Khi phát hiện credential xuất hiện trong log, repository, image, ticket hoặc nơi không được phép:

1. **Xác định credential type và principal nguồn:** STS session, OAuth access token, service account key hay signed URL/SAS?
2. **Xác định scope và hạn dùng:** Resource, role, audience, quyền đặc biệt và đường cấp token mới.
3. **Chặn tái cấp:** Khóa/ngăn nguồn bị xâm nhập, thu hẹp trust hoặc tắt quyền thích hợp theo kịch bản.
4. **Thu hồi hoặc giảm quyền:** Dùng API/session revocation được provider hỗ trợ; nếu là key tĩnh thì vô hiệu hóa/rotate; nếu bearer capability thì xử lý theo cơ chế ký và tài nguyên.
5. **Bảo toàn bằng chứng:** Log sử dụng, role assumption, token exchange và cloud API trong khung thời gian liên quan.
6. **Xác minh không còn đường truy cập:** Đọc lại policy/binding/trust, kiểm tra quyền và theo dõi session còn hiệu lực.
7. **Khắc phục nguyên nhân:** Bỏ log raw token, sửa CI, kiểm soát namespace/repository và loại credential tĩnh không cần.

Không đăng lại credential bị lộ vào incident ticket. Chỉ cung cấp **metadata đủ để định danh** và lưu bí mật bị ảnh hưởng theo quy trình xử lý an toàn.

### 17.1. Bảng phản ứng theo loại credential

| Loại bị lộ | Việc cần ưu tiên |
| --- | --- |
| AWS STS session credential | Xác định role/session, chặn dùng tiếp theo cơ chế có hỗ trợ, rà soát quyền và API logs |
| Azure access token | Xác định principal/audience/resource, dùng cơ chế revoke hoặc giảm quyền được hỗ trợ; theo dõi TTL |
| Google Cloud access token | Giới hạn IAM/impersonation, xử lý token theo khả năng nền tảng, kiểm tra logs |
| OIDC source token của CI | Xác định repository/job/issuer, thu hẹp trust và ngăn exchange mới |
| Refresh token | Thu hồi phiên/cơ chế refresh ở issuer nếu hỗ trợ; kiểm tra token mới đã cấp |
| Static access key/client secret | Disable/rotate ngay theo chính sách; thay nguồn credential |
| Signed URL/SAS | Kiểm tra loại chữ ký, khóa/chính sách và phương án vô hiệu hóa hoặc chờ hết hạn được hỗ trợ |

## 18. Những anti-pattern thường gặp

| Anti-pattern | Vì sao rủi ro | Hướng khắc phục |
| --- | --- | --- |
| Lưu access key dài hạn trong CI dù đã hỗ trợ OIDC | Key có thể tồn tại sau khi xóa pipeline | Dùng federation/managed identity |
| Cho toàn bộ CI organization assume cùng role | Repo không được duyệt có thể nhận credential | Giới hạn issuer, audience, subject, environment |
| Cấp token ngắn hạn nhưng role Administrator | Trong TTL ngắn vẫn có thể gây thiệt hại lớn | Giới hạn role, action và scope |
| Chỉ nhìn trường expiration | Bỏ qua quyền refresh và tái cấp token | Kiểm soát source identity, trust và entitlement |
| Log nguyên credential để debug | Log trở thành kho secret | Chỉ ghi metadata và correlation ID |
| Đọc JWT payload mà không xác minh chữ ký | Chấp nhận claim do nguồn giả mạo cung cấp | Xác thực issuer, signature, audience, expiry |
| Dùng OIDC ID token thay access token cho API | Sai mục đích, audience, mô hình xác thực | Dùng đúng loại token theo resource server |
| Tự refresh bằng key tĩnh quyền cao khi SDK lỗi | Một lỗi auth biến thành đường bypass | Fail closed, dùng provider chuẩn và cảnh báo |
| Disable IdP rồi đánh dấu Leaver hoàn tất | Role/key/session cũ có thể còn | Đối soát cloud target và xử lý credential |
| Xóa Pod nhưng để lại managed identity | IAM grant tiếp tục tồn tại | Deprovision identity, role binding và trust |
| Xem token expire là đủ cho Mover | Quyền cũ còn nên đăng nhập lại vẫn được cấp | Thu hồi entitlement vai trò cũ |
| Không phân biệt source token với target credential | Thu hồi sai nơi, bỏ sót phiên cloud | Theo dõi cả hai TTL và đường exchange |
| Tự tin revoke API thành công là đã xong | Quyền có thể còn qua grant khác | Readback, kiểm tra effective access |
| Dùng chung service account cho mọi workload | Không thể cô lập hoặc thu hồi từng service | Tạo principal theo workload và phân cấp quyền |
| Tin short-lived là hoàn toàn không thể bị đánh cắp | Bearer token vẫn dùng được khi còn hạn | Runtime security, least privilege, trust và giám sát |

## 19. Reconciliation và xác minh quyền truy cập tồn dư

Để giảm **residual access**, hệ thống cần so sánh:

- **Desired access:** Quyền được duyệt theo tình trạng người/workload, chức trách, resource và thời hạn.
- **Assigned access:** Group, role, binding, trust, impersonation, key và grant đang cấu hình.
- **Effective access:** Những thao tác IAM thực tế cho phép, sau các giới hạn, điều kiện và phiên còn sống.

### 19.1. Giả mã quy trình đối soát

~~~text
event = getAuthorizedLifecycleEvent(identityOrWorkloadId)
targets = discoverAllCloudTargets(identityOrWorkloadId)

for target in targets:
    desired = approvedEntitlements(identityOrWorkloadId, target)
    assigned = enumerateRolesGroupsBindingsTrustAndKeys(target)
    stale = compareNormalizedGrants(assigned, desired)

    for grant in stale:
        revokeGrantWithAudit(grant)

    sessions = discoverRelevantSessionsWhenSupported(target)
    handleRevocationOrExpiry(sessions)

    verification = assessEffectiveAccessUsingSupportedMethods(target)
    if verification.meetsDesiredState:
        recordVerified(event, target)
    else:
        recordExceptionWithOwnerAndDeadline(event, target, verification)
~~~

Đây là **giả mã nghiệp vụ**. Không phải cloud provider nào cũng cung cấp API liệt kê tất cả session đang sống; cần dùng log, TTL, chính sách hạn chế, mô phỏng quyền hoặc kiểm tra được phép tùy khả năng thực tế. Phép so sánh role phải chuẩn hóa **principal, role, scope, điều kiện, source và thời hạn**, không đơn giản so tên role.

### 19.2. Trạng thái cần phản ánh đúng bằng chứng

~~~text
REQUESTED   Đã có yêu cầu cấp/sửa/thu hồi quyền
APPROVED    Quyết định đã được duyệt
APPLIED     Thao tác tới cloud target trả về thành công
VERIFIED    Đã kiểm tra đạt trạng thái quyền mong muốn
FAILED      Thao tác hoặc xác minh thất bại
EXCEPTION   Có đường truy cập chưa xử lý, với owner và hạn giải quyết
~~~

**APPLIED không đồng nghĩa VERIFIED.** Nếu credential chưa hết hạn và không thể revoke ngay, cần lưu tình trạng còn lại và trách nhiệm xử lý; không tuyên bố Leaver đã xóa mọi phiên.

## 20. Tình huống xuyên suốt: một nhân viên và một pipeline

Công ty triển khai ứng dụng **Learning Analytics** trong ba môi trường. Nhân viên Quân (ID **EMP-6208**) là kỹ sư vận hành, còn pipeline **learning-analytics-deployer** là workload có owner là đội Platform.

### 20.1. Joiner của Quân

Quân đăng nhập qua IdP/SSO và MFA để nhận role đọc log ở môi trường dev. Cloud session có thời gian sống giới hạn. Quy trình kiểm tra đọc log dev thành công, còn sửa IAM production bị từ chối. Audit lưu mã nhân viên, phiên bản role và kết quả đối chiếu quyền.

### 20.2. Mover của Quân

Quân chuyển sang đội Data. Quyền đọc log dev không còn cần nhưng một role assignment trực tiếp vẫn còn trên cloud. Khi token hiện tại hết hạn, Quân vẫn có thể đăng nhập lại và nhận quyền từ assignment đó. Hệ thống JML phải gỡ grant trực tiếp và xác minh, không chỉ đợi TTL.

### 20.3. Leaver của Quân

IdP disable user vào thời điểm nghỉ việc; hệ thống thu hồi role, kiểm tra cloud-local key và session đang hoạt động. Nếu không thể revoke một phiên ngay, sự kiện giữ **EXCEPTION** với owner cho đến khi điều kiện xác minh được đáp ứng.

### 20.4. Joiner của pipeline

Pipeline dùng OIDC token từ đúng repository và environment staging để đổi lấy credential cloud tạm thời, chỉ được deploy service staging. Chủ sở hữu đội Platform quyết định vòng đời role và trust; không dùng access key cá nhân của Quân.

### 20.5. Leaver của pipeline

Khi pipeline retire, trust và role binding được thu hồi. Một job cũ dù có identity token còn hạn không được đổi lấy cloud session mới nếu quan hệ trust đã bị chặn phù hợp. Những credential cloud đã cấp trước đó phải được xử lý theo TTL/cơ chế revocation và ghi bằng chứng.

### 20.6. Ví dụ bản ghi audit

~~~json
{
  "eventId": "JML-LEAVER-6208",
  "identityId": "EMP-6208",
  "eventType": "leaver",
  "source": "HRIS",
  "cloudTarget": "learning-dev",
  "operation": "revoke-role-assignment-and-sessions",
  "changeApplied": true,
  "effectiveAccessVerified": false,
  "status": "verification_pending",
  "occurredAt": "2026-11-23T07:00:00Z"
}
~~~

**verification_pending** chỉ nói rằng thao tác đã được áp nhưng trạng thái cuối chưa được chứng minh. Khi không còn đường truy cập trái phép theo phạm vi kiểm tra, hệ thống mới ghi **VERIFIED** cùng bằng chứng readback.

## 21. Giám sát và chỉ số vận hành

### 21.1. Log và bằng chứng nên thu thập

| Dữ liệu | Lý do |
| --- | --- |
| Source identity và JML event | Biết nguồn có thẩm quyền và thời điểm thay đổi |
| Issuer, subject, audience, trust reference | Truy ngược nguyên nhân cấp credential |
| Target principal/role/scope | Biết quyền được dùng ở đâu |
| Credential issuance metadata và expiration | Theo dõi khoảng hiệu lực, không lộ secret |
| Role assumption/token exchange events | Tìm phiên được cấp từ nguồn nào |
| Cloud API access/audit events | Xác định những hành động đã được thực hiện |
| IAM grant/trust/key changes | Kiểm tra quyền được cấp, thu hồi hoặc sửa |
| Approval, owner và change ticket | Liên hệ kỹ thuật với lý do nghiệp vụ |
| Readback, verification và exception | Phân biệt request, apply và kết quả thực |

Không lưu raw bearer tokens, private keys, refresh tokens hoặc session secrets trong hệ thống log. Khi cần tương quan, dùng định danh phiên/token do provider cho phép và cơ chế lưu trữ bảo mật thích hợp.

### 21.2. Các chỉ số cần theo dõi

| Chỉ số | Ý nghĩa |
| --- | --- |
| **Tỷ lệ workload dùng credential ngắn hạn** | Tiến trình loại bỏ key tĩnh |
| **Số long-lived keys không có owner** | Phát hiện credential mồ côi |
| **P95 thời gian thu hồi sau Leaver** | Từ hiệu lực sự kiện đến khi quyền được VERIFIED |
| **Số phiên/credential còn hiệu lực sau deprovision** | Đo residual access và giới hạn revocation |
| **Tỷ lệ JML events có readback** | Đánh giá chứng cứ hoàn tất thay đổi |
| **Số trust có audience/subject quá rộng** | Xác định đường tái cấp credential trái phép |
| **Số privileged workload sessions** | Ưu tiên giám sát role cao trên production |
| **Tỷ lệ refresh failure** | Phát hiện rủi ro gián đoạn dịch vụ xác thực |
| **Số lần sử dụng credential ngoài hành vi thường thấy** | Phát hiện lạm dụng hoặc key leak |
| **Tỷ lệ service identities có owner và kỳ review** | Kiểm soát vòng đời danh tính phi con người |

Chia số liệu theo **provider, môi trường, loại principal, độ nhạy cảm quyền và workload/human**. Một credential có quyền quản trị IAM production cần ngưỡng cảnh báo và xử lý chặt hơn credential chỉ đọc trên sandbox.

## 22. Checklist triển khai temporary cloud credential

1. **Định danh nguồn:** Biết người/workload nào đang yêu cầu và nguồn có thẩm quyền.
2. **Xác thực chuẩn:** Dùng IdP/SSO với MFA cho người; managed identity/federation thích hợp cho workload.
3. **Trust hẹp:** Kiểm tra issuer, chữ ký, audience, subject, hạn token và claims được provider hỗ trợ.
4. **Đúng token:** Phân biệt ID token, access token, SAML assertion, STS credentials, refresh token và delegated URL.
5. **Đúng principal đích:** Map nguồn tới role, service account hoặc identity đã phê duyệt.
6. **Ít quyền:** RBAC/ABAC và IAM giới hạn action/resource/scope; xem đường nâng đặc quyền.
7. **Thời hạn hợp lý:** Session TTL và entitlement expiry được thiết kế riêng, có giải thích rủi ro.
8. **Refresh an toàn:** Dùng SDK/credential provider chuẩn, cache hợp lý, không fallback sang key admin.
9. **Không lộ secret:** Không commit, log, chia sẻ token hoặc lưu vào artifact CI.
10. **Workload có owner:** Service account, pipeline, Pod hoặc managed identity có người/đội chịu trách nhiệm.
11. **JML đầy đủ:** Joiner cấp đúng quyền, Mover thu hồi quyền cũ, Leaver chặn tái cấp và xử lý credential còn sống.
12. **Revocation được hiểu rõ:** Ghi khả năng thu hồi thực tế từng provider và những giới hạn phải chờ TTL.
13. **Readback bắt buộc:** Đối soát role, trust, key, session và effective access trước khi đánh dấu VERIFIED.
14. **Kiểm thử negative case:** Token sai issuer/audience/sub, credential hết hạn hoặc action ngoài scope đều phải bị từ chối.
15. **Kiểm toán:** Ghi nguồn, thời gian, quyền, owner, phê duyệt, kết quả và ngoại lệ mà không lộ bí mật.
16. **Ứng cứu:** Có quy trình phản ứng khi lộ credential, issuer bị xâm nhập hoặc STS không cấp token.

## 23. Bài tập tự kiểm tra

### Bài 1. Token hết hạn có thay thế thu hồi quyền không?

**Tình huống:** Một kỹ sư đổi từ SRE sang Analytics, cloud session của họ chỉ còn 10 phút. Người quản trị đề xuất chờ credential hết hạn là xong.

**Trả lời:** Chưa đủ. Nếu role assignment/group/trust của SRE còn hợp lệ, người đó có thể nhận session mới. Phải thu hồi entitlement cũ, kiểm tra đường cấp quyền khác và xử lý session hiện tại theo cơ chế provider.

### Bài 2. OIDC token hợp lệ nhưng STS từ chối

**Tình huống:** CI job mang token có chữ ký đúng nhưng audience khác với audience của federation target.

**Trả lời:** Từ chối là hành vi đúng. Token hợp lệ về chữ ký vẫn không phù hợp với target; cần xác minh issuer, audience, subject và những điều kiện liên quan.

### Bài 3. Azure managed identity đã có token

**Tình huống:** Workload Azure đã nhận access token nhưng vẫn không đọc được một blob.

**Trả lời:** Token chứng minh danh tính/ủy quyền với audience phù hợp, còn resource xét role assignment và quyền dữ liệu. Cần kiểm tra scope, data-plane role, trạng thái áp quyền và điều kiện tương ứng; không tự cấp Owner toàn subscription.

### Bài 4. GCP service account impersonation

**Tình huống:** Pipeline chỉ có binding trực tiếp cho quyền đọc log nhưng được impersonate service account có quyền Editor trên project.

**Trả lời:** Pipeline có đường nhận quyền gián tiếp lớn hơn. Phải rà soát quyền impersonation và quyền của service account đích, không chỉ nhìn binding trực tiếp của principal nguồn.

### Bài 5. Pod bị xóa nhưng credential còn sống

**Tình huống:** Pod bị xóa lúc 14:00, một temporary token được cấp trước đó còn hạn tới 14:30.

**Trả lời:** Xóa Pod không đảm bảo token cloud bị vô hiệu hóa tức thời. Cần kiểm tra token và cơ chế revoke thực tế, thu hồi trust/binding để chặn cấp mới, giám sát TTL còn lại và xác minh quyền.

### Bài 6. Refresh token khác access token thế nào?

**Tình huống:** Một ứng dụng tuyên bố chỉ dùng access token một giờ, nhưng lưu refresh token nhiều ngày không có revocation.

**Trả lời:** Refresh token có thể dùng xin access token mới nên thời gian quyền thực tế có thể dài hơn một giờ. Cần bảo vệ và quản lý vòng đời refresh token riêng, có cơ chế thu hồi khi người dùng Leaver hoặc có sự cố.

## 24. Tổng kết

**Temporary cloud credential** là thành phần quan trọng để truy cập AWS, Azure và Google Cloud mà không phải lưu bí mật dài hạn ở mọi ứng dụng. AWS dùng STS role sessions và temporary credentials; Azure thường dùng Entra access tokens qua managed identity hoặc federation; Google Cloud dùng access tokens, workload federation và service account impersonation theo cấu hình. Kubernetes và CI/CD cung cấp identity evidence để các hệ thống cloud tin cậy khi đủ điều kiện.

Để có giá trị bảo mật, credential tạm thời phải đi cùng **định danh và trust đáng tin cậy, quyền tối thiểu theo RBAC/ABAC, thời hạn và refresh an toàn, giám sát và khả năng thu hồi được kiểm chứng**. Trong vòng đời **Joiner–Mover–Leaver**, cần quản lý riêng entitlement, lần cấp credential và session đã phát hành. Chỉ khi đã xử lý các role, binding, trust, key và phiên không còn hợp lệ ở đúng cloud target, **quyền truy cập tồn dư được xác minh** và có bằng chứng kiểm toán, sự kiện JML mới được xem là hoàn tất về mặt kiểm soát truy cập.
