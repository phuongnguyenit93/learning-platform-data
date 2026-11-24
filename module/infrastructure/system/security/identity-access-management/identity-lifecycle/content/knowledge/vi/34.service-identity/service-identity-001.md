# Service identity là gì trong quản lý vòng đời danh tính IAM?

> **Chương:** Service identity
>
> **Bài:** Service identity là gì
>
> **Module:** SECURITY_IDENTITY_ACCESS_MANAGEMENT_IDENTITY_LIFECYCLE
>
> **Bối cảnh:** Quản lý vòng đời danh tính trong IAM theo **Joiner–Mover–Leaver**, từ xác minh, tạo danh tính, cấp quyền đến rà soát, điều chỉnh và thu hồi. Bài học kết nối **IdP, SSO, SCIM, RBAC/ABAC, tài khoản dịch vụ, kiểm toán** và cách giảm **quyền truy cập tồn dư**.

## 1. Service identity là gì?

Một ứng dụng thanh toán cần gọi API kho dữ liệu để ghi giao dịch. Không có con người đăng nhập vào màn hình mỗi lần ứng dụng gửi request. Tuy nhiên hệ thống kho dữ liệu vẫn phải biết:

- **Ai đang gọi?** Chính xác workload nào thuộc tổ chức nào?
- **Có thể tin lời tự nhận không?** Danh tính đã được xác thực bởi cơ chế nào?
- **Được phép làm gì?** Chỉ ghi bản ghi giao dịch hay được xóa toàn bộ dữ liệu?
- **Được phép trên đâu?** Đúng database, tenant, environment và resource nào?
- **Khi ngừng hoạt động thì sao?** Danh tính và quyền được thu hồi như thế nào?
- **Có thể kiểm toán không?** Có truy ngược request đến workload, owner và phiên bản triển khai không?

**Service identity (định danh dịch vụ)** là một danh tính được hệ thống IAM dùng để nhận diện và kiểm soát **một dịch vụ, ứng dụng, workload hoặc tiến trình phi con người** khi nó truy cập tài nguyên hay gọi dịch vụ khác.

Một service identity có thể được biểu diễn bằng **service principal, managed identity, workload identity, service account, OAuth client hoặc certificate identity**, tùy nền tảng. Những thuật ngữ này **không hoàn toàn tương đương**: có cái là danh tính logic, có cái là object chứa quyền, có cái là phương tiện chứng minh danh tính.

Service identity thường thuộc nhóm **Non-Human Identity (NHI)**, nhưng NHI rộng hơn: có thể bao gồm bot, tác vụ máy, agent, robot, service principals và các định danh tự động khác.

### 1.1. Ví dụ ngắn

Một job sao lưu chạy mỗi đêm và cần đọc một bucket.

**Thiết kế không tốt:** lập một tài khoản nhân viên giả tên backup-admin, tạo mật khẩu không hết hạn và cấp toàn quyền cloud.

**Thiết kế tốt hơn:** đăng ký danh tính riêng cho workload sao lưu, gắn owner, xác thực bằng cơ chế workload thích hợp, cấp quyền **chỉ đọc bucket/prefix cần sao lưu**, giới hạn môi trường và kiểm tra được lịch sử sử dụng. Khi job ngừng hoặc chuyển nơi chạy, đánh giá lại trust và thu hồi quyền cũ.

### 1.2. Service identity không nhất thiết là một tài khoản tên “service”

Một chuỗi như service-payment-prod chỉ là **tên hiển thị**. Nó không đủ để bảo đảm chủ thể thực sự là workload được phép. Danh tính phải được ràng buộc với một **identifier đáng tin, issuer/trust domain, thông tin xác thực và quyền** theo nền tảng.

## 2. Phân biệt identity, principal, account, credential và token

Đây là phần quan trọng nhất để không nhầm khi thiết kế hoặc deprovision.

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| **Identity** | Danh tính logic của workload được tổ chức quản trị | payment-api production |
| **Principal** | Chủ thể được hệ thống bảo mật nhận diện để ra quyết định | Service principal có ID riêng trong cloud tenant |
| **Account** | Đối tượng quản lý ở một hệ thống, có thể đại diện cho principal | Service account tại SaaS hoặc Kubernetes |
| **Credential** | Bằng chứng dùng để xác thực hoặc chứng minh quyền giữ identity | Private key, client secret, certificate, workload proof |
| **Token** | Bằng chứng/ủy quyền được phát theo một giao thức và phạm vi | OAuth access token dành cho API |
| **Role/entitlement** | Tập quyền principal được cấp | storage.object.read trên một bucket |
| **Trust relationship** | Quy tắc công nhận nguồn danh tính và điều kiện xác thực | Chỉ tin OIDC issuer của CI runner đúng repository |
| **Owner** | Cá nhân/nhóm chịu trách nhiệm vòng đời và rủi ro | Team Platform Backup |

### 2.1. Identity khác credential

Một service identity có thể thay private key nhiều lần mà vẫn giữ identifier logic để audit không bị đứt. Ngược lại, một secret dùng chung ở nhiều workload khiến rất khó biết **workload nào thực sự đã dùng quyền**.

### 2.2. Principal khác permission

Principal đã được xác thực thành công **không tự có quyền** đọc database. Quyền được xác định bởi chính sách RBAC/ABAC, ACL hoặc resource policy. Xác thực (authentication) và phân quyền (authorization) phải tách bạch.

### 2.3. Account không phải lúc nào cũng là credential

Một Kubernetes ServiceAccount là đối tượng API thể hiện identity trong cluster và có thể dùng token projectable. Nó không đồng nghĩa luôn tồn tại một mật khẩu tĩnh trong object đó. Một cloud managed identity cũng có thể lấy token qua nền tảng mà không cần team lưu client secret dài hạn.

### 2.4. Token còn hạn không chứng minh grant còn hợp lệ

Một access token có thể còn thời hạn kỹ thuật trong khi role của service principal đã bị thu hồi. Với action rủi ro cao, resource server phải áp dụng chính sách thời hạn, issuer/audience và cơ chế revoke/entitlement freshness tương ứng.

## 3. Human identity và service identity khác nhau ở đâu?

| Khía cạnh | Human identity | Service identity |
|---|---|---|
| Chủ thể | Người lao động, đối tác, khách | Workload, chương trình, tiến trình |
| Đăng nhập | Thường qua IdP/SSO, MFA | Workload federation, mTLS, client authentication, platform identity |
| Tính tương tác | Người dùng có thể xác nhận bằng UI | Thường chạy tự động, không có giao diện MFA |
| Nguồn vòng đời | HRIS, contract, manager | Service catalog, deployment, platform/owner, CI/CD |
| Quyền | Dựa trên vị trí, nhiệm vụ, SoD | Dựa trên chức năng dịch vụ, resource, environment |
| Rotation | Password/key tùy mô hình | Secret/certificate/token/trust lifecycle |
| Giám sát | User session, activity | API calls, job runs, issuance và identity bindings |
| Leaver | Người nghỉ việc | Service retire, workload decommission, chuyển owner |
| Rủi ro điển hình | Đăng nhập bị chiếm, role tồn dư | Secret lộ, shared identity, quyền rộng, orphan workload |

Không nên tạo một “nhân viên giả” trong HRIS để chạy bot chỉ vì hệ thống hỗ trợ user login nhưng thiếu service-principal integration. Nếu vendor buộc dùng service account kiểu user, phải ghi rõ đây là **non-human**, có owner, credential policy, login restriction và ngoại lệ có kiểm soát.

### 3.1. Service identity không có MFA như người dùng

Không phải mọi workload có thể tương tác với OTP, passkey hoặc push notification. Với machine-to-machine authentication, dùng cơ chế chứng minh workload phù hợp như managed identity, workload identity federation, mTLS certificate hoặc client authentication được bảo vệ.

Không cố tự động đọc mã OTP của một nhân viên để chạy job; đây là dấu hiệu sai mô hình trust và audit.

### 3.2. Service vẫn cần người chịu trách nhiệm

Danh tính phi con người không đồng nghĩa không có owner. Mỗi identity nên có **owner nghiệp vụ hoặc kỹ thuật**, contact/on-call, resource scope, mục đích và thời gian rà soát.

## 4. Những ví dụ thực tế về service identity

| Tình huống | Subject phi con người | Tài nguyên cần quyền |
|---|---|---|
| Microservice gọi service khác | payment-api | ledger-api |
| CI/CD triển khai ứng dụng | Deployment job | Cloud deployment API |
| ETL nạp dữ liệu hằng đêm | warehouse-loader | Data lake và database |
| Cron job xử lý email | notification-worker | Queue và email provider |
| Kubernetes Pod truy cập storage | Workload gắn Kubernetes ServiceAccount | Object storage |
| Serverless function xử lý file | image-processor function | Một bucket và queue |
| Job sao lưu | backup-runner | Backup source/destination |
| SaaS integration | CRM connector | CRM API của một tenant |
| Monitoring agent | observability-agent | Metrics/log ingestion API |
| IaC automation | Terraform runner | Cloud resource management API |

Các workload trên cần identity khác nhau khi **đơn vị sở hữu, môi trường, risk boundary và tập quyền** khác nhau. Việc một image/container được tái sử dụng không có nghĩa nên dùng chung identity ở development và production.

### 4.1. Một service có thể có nhiều identity

Một ứng dụng có thể có các identity riêng cho:

- Runtime đọc/ghi dữ liệu production.
- Job migration schema có quyền cao theo cửa sổ bảo trì.
- Deployment pipeline thay phiên bản ứng dụng.
- Monitoring agent chỉ xuất metrics.
- Backup workload chỉ đọc nguồn và ghi đích.

Đây là cách tránh cấp một identity duy nhất vừa deploy, vừa xóa database, vừa xem tất cả secrets.

### 4.2. Nhiều instance có thể dùng chung logical identity

Một deployment có ba replica cùng chạy payment-api có thể dùng cùng logical service identity, miễn quy tắc trust và audit đáp ứng mục tiêu. Khi cần phân biệt instance/pod, dùng workload instance attributes trong chứng nhận/token hoặc telemetry.

Không tự kết luận mỗi replica luôn phải có identity hoàn toàn riêng; granularity phụ thuộc threat model và khả năng nền tảng.

## 5. Các dạng service identity thường gặp

| Dạng | Đặc điểm | Lưu ý |
|---|---|---|
| **Cloud service principal** | Principal ứng dụng được quản trị trong một tenant/cloud | Cần role/resource scope và owner |
| **Managed identity** | Nền tảng quản lý danh tính/credential cho workload | Giảm secret tĩnh, nhưng vẫn cần least privilege |
| **OAuth client** | Client được đăng ký với authorization server | Client ID không phải secret; client auth và grants tùy profile |
| **Kubernetes ServiceAccount** | Identity đối với Pod/process trong cluster | Không mặc định có quyền cloud ngoài cluster |
| **Workload identity federation** | Đổi bằng chứng workload từ issuer đáng tin lấy quyền/token ở target | Kiểm tra issuer, audience, subject và trust conditions |
| **mTLS/certificate identity** | Chứng minh private-key possession và danh tính certificate | Quản lý CA, SAN, expiry, revocation |
| **SaaS service account** | Account dùng riêng cho automation trong SaaS | Có thể dùng credential truyền thống, cần quản trị ngoại lệ |
| **SPIFFE-style workload identity** | Workload identity được biểu diễn bằng SPIFFE ID và SVID trong trust domain | Phụ thuộc triển khai SPIFFE/SPIRE hoặc tương đương |

Các tên gọi tùy nền tảng, không có ánh xạ một-một giữa mọi vendor. Không mặc định mọi “service account” đều hỗ trợ OAuth hoặc mọi managed identity đều dùng SCIM.

### 5.1. Client ID không phải mật khẩu

Một OAuth client ID thường là định danh để AS nhận ra client. Bản thân ID thường **không bí mật**. Secret, private key hoặc workload proof mới là thành phần chứng thực; không bảo vệ hệ thống bằng cách giấu client ID rồi cấp quyền rộng.

### 5.2. Kubernetes ServiceAccount và cloud IAM

Pod chạy dưới Kubernetes ServiceAccount **không tự có quyền cloud storage**. Cần binding/trust integration do platform cung cấp nếu muốn đổi danh tính Pod thành quyền cloud, kèm issuer/audience/subject restrictions thích hợp.

### 5.3. Managed identity giảm secret tĩnh, không giảm quyền tự động

Nếu workload dùng managed identity nhưng được gán cloud-admin trên toàn tổ chức, rủi ro quyền quá rộng vẫn còn. Thay credential bằng cơ chế tốt hơn phải đi cùng giảm phạm vi entitlement.

## 6. Kiến trúc cơ bản: service gọi service

~~~mermaid
flowchart LR
    DEV[Deployment / Service Catalog] --> REG[Identity Registry / Trust Policy]
    REG --> AS[Identity Provider / Authorization Server]
    WORK[Payment API Workload] --> PROOF[Workload Identity Proof]
    PROOF --> AS
    AS --> TOK[Short-lived Access Token]
    TOK --> WORK
    WORK --> PEP[Ledger API / PEP]
    PEP --> VAL[Token Validation + RBAC/ABAC]
    VAL --> DATA[(Ledger Resource)]
    REG --> AUD[Audit and Lifecycle]
    PEP --> AUD
~~~

Luồng logic:

1. Team đăng ký workload với owner, environment, purpose và resource requirements.
2. Nền tảng/issuer chứng thực workload bằng phương thức được chấp nhận.
3. AS hoặc STS kiểm tra trust policy và phát token cho audience/scope thích hợp.
4. Workload gọi API đích bằng token/credential được phép.
5. API xác minh identity, token, resource scope và quyết định authorization.
6. Log truy cập gắn principal ID, service/workload, tenant và correlation ID.
7. Khi workload chuyển vai trò hoặc ngừng, trust và grants được điều chỉnh/thu hồi.

**Sơ đồ là kiến trúc minh họa**, không bắt buộc mọi hệ thống dùng OAuth hoặc AS. Một số giao tiếp dùng mTLS và authorization policy trực tiếp.

### 6.1. Control plane và data plane

- **Control plane:** nơi tạo identity, đặt trust, gán role, cấp grants, sửa policy, review owner và deprovision.
- **Data plane:** nơi service identity dùng quyền thực tế để đọc, ghi hoặc gọi API.

IAM đánh dấu role đã xóa ở control plane không tự chứng minh token hoặc session ở data plane đã mất quyền tức thời. Cần thiết kế propagation và verification.

### 6.2. Trust boundary

Không chỉ xét microservice gọi service: phải xét Pod/host có được quyền lấy credential của identity không, cluster issuer có đáng tin không, token được chấp nhận bởi đúng target/tenant không và có nguy cơ bị dùng ngoài môi trường được duyệt không.

## 7. Xác thực (AuthN) và phân quyền (AuthZ) với Service Identity

Hai câu hỏi riêng:

- **Authentication:** “Bạn có phải workload payment-api-prod mà tôi tin không?”
- **Authorization:** “Identity đó có được phép gọi action ledger.write trên đúng tenant/project/resource này không?”

Ví dụ:

~~~text
Principal: payment-api-prod
Issuer: trusted-workload-issuer
Audience: ledger-api
Action: ledger.entry.create
Resource: tenant-a/ledger
Decision: PERMIT nếu trust + grant + resource policy đều hợp lệ
~~~

Workload được xác thực đúng vẫn phải bị từ chối nếu cố gọi ledger.entries.delete hoặc truy cập tenant B.

### 7.1. RBAC cho service identity

RBAC có thể cấp role theo chức năng:

| Identity | Role | Scope |
|---|---|---|
| payment-api-prod | ledger-writer | tenant-a/ledger |
| analytics-reader-prod | report-viewer | tenant-a/approved-views |
| backup-runner | backup-reader | designated source prefix |
| deploy-runner | release-deployer | project-a production |
| monitoring-agent | metrics-publisher | collector namespace |

Một role có thể được tái sử dụng ở nhiều service nhưng các **bindings** phải có resource scope rõ.

### 7.2. ABAC cho service identity

ABAC có thể xét:

- Subject attributes: service ID, namespace, deployment environment, owner, identity issuer.
- Resource attributes: tenant, project, classification, region.
- Action attributes: read, write, deploy, delete.
- Context attributes: trust level, credential age, network posture, workload attestation.

Ví dụ pseudo-policy:

~~~text
PERMIT nếu:
    principal.serviceId == "payment-api"
    AND principal.environment == "prod"
    AND principal.issuer IN trustedIssuers
    AND token.audience == "ledger-api"
    AND resource.tenantId == principal.tenantId
    AND action == "ledger.entry.create"
    AND currentTime < grant.validUntil
    AND principal.lifecycleStatus == ACTIVE
~~~

Các attributes phải được lấy từ **nguồn đáng tin** (issuer/trust policy, resource lookup, registry), không tin string do client tự gửi.

### 7.3. Không dùng network location thay identity

“Request đến từ subnet nội bộ” không chứng minh service là payment-api. Có thể kết hợp network policy với mTLS/token identity, nhưng không dùng IP/VPC làm bằng chứng duy nhất cho quyền nhạy cảm.

## 8. OAuth 2.0, OIDC và Machine-to-Machine (M2M)

Trong OAuth 2.0, một workload có thể là **confidential client** khi gọi Authorization Server để lấy access token. Một cơ chế phổ biến cho giao tiếp không có người dùng trực tiếp là **client credentials grant**, khi điều kiện và profile phù hợp.

~~~mermaid
sequenceDiagram
    participant W as Workload
    participant AS as Authorization Server
    participant API as Resource Server
    W->>AS: Authenticate client / workload proof
    AS->>AS: Validate trust, scope, tenant and policy
    AS-->>W: Access token for API audience
    W->>API: Request with access token
    API->>API: Validate issuer, audience, token, scope
    API->>API: Check principal, RBAC/ABAC and resource
    API-->>W: Response or authorization denial
~~~

### 8.1. Client credentials không phải “đăng nhập người dùng”

Client credentials dùng client identity, không đòi một nhân viên bấm SSO ở mỗi lần gọi. Nó không tự chứng minh request đang thay mặt người dùng cuối.

Nếu API cần thực hiện **on-behalf-of/delegation**, phải dùng luồng/chính sách phù hợp để bảo toàn quyền của người dùng và của workload. Không tự gắn một userId vào access token M2M rồi cho toàn quyền nhân danh người đó.

### 8.2. OIDC token không đồng nghĩa access token

OIDC ID token chủ yếu truyền thông tin xác thực của end user cho client/RP; OAuth access token dùng để truy cập protected resource theo contract. Resource Server không được chấp nhận bất kỳ JWT nào chỉ vì chữ ký hợp lệ; cần kiểm tra token type, issuer, audience, expiry và quy tắc profile.

### 8.3. Một số claim quan trọng

| Thành phần | Mục đích |
|---|---|
| **iss** | Token do issuer nào phát |
| **sub** | Subject được token nói tới, ngữ nghĩa phụ thuộc profile |
| **aud** | Audience/resource được phép nhận token |
| **exp / nbf / iat** | Thời gian token hết hạn/chưa hợp lệ/phát |
| **scope / permissions** | Khả năng được cấp trong token theo contract |
| **client_id / azp** | Thông tin client khi profile có dùng |
| **jti** | Định danh token phục vụ một số kiểm soát replay/revocation |

Không mặc định một claim nhất định xuất hiện ở mọi AS hoặc có cùng ý nghĩa giữa các token profile. **Token có scope vẫn phải qua resource-level authorization**.

### 8.4. Audience confusion và confused deputy

Nếu API A phát token dùng cho chính API A nhưng API B cũng chấp nhận nó, token có thể bị sử dụng sai audience. Khi service gọi thay mặt caller, API B cần kiểm tra caller được phép nhờ API A làm hành động đó và service A không tự nâng quyền. Những vấn đề này liên quan đến **audience validation**, delegation contract và chống confused deputy.

## 9. Các cơ chế chứng minh định danh workload

Không có một phương thức xác thực phù hợp cho mọi dịch vụ. Lựa chọn phụ thuộc vào **runtime, trust boundary, threat model, độ nhạy cảm của tài nguyên và khả năng quản lý credential**.

| Cơ chế | Cách hoạt động tổng quát | Lưu ý |
|---|---|---|
| **API key tĩnh** | Workload gửi một key cho API | Dễ lộ, khó quy trách nhiệm nếu chia sẻ, cần rotate/revoke |
| **OAuth client secret** | Client dùng secret để xác thực với AS | Lưu trong secret manager, giới hạn client grants |
| **Private-key JWT** | Client chứng minh quyền giữ private key | Quản lý key, clock, key rotation và verification |
| **mTLS** | Hai bên chứng minh danh tính certificate ở TLS | Trust CA và SAN, không tự có authorization |
| **Managed identity** | Platform cung cấp identity và cơ chế lấy token | Giảm secret trong app; không giảm role rộng tự động |
| **Workload federation** | Đổi bằng chứng workload từ issuer tin cậy lấy token đích | Ràng buộc issuer, audience, subject, environment |
| **SPIFFE/SVID** | Identity workload theo trust domain, có chứng nhận danh tính | Tùy hạ tầng và SPIFFE-compatible implementation |
| **Platform token** | Token được gắn với Pod/job/VM/function | Kiểm tra audience, TTL, issuer, runtime binding |

### 9.1. Static secret là lựa chọn cần quản trị rủi ro

Nếu vendor chỉ hỗ trợ API key hoặc secret tĩnh:

1. Dùng key riêng cho workload và environment.
2. Cất trong vault/secret manager, không hardcode.
3. Giới hạn permission và target resource nếu có thể.
4. Gắn owner và lịch rotation, kiểm tra lastUsedAt.
5. Không ghi secret vào log, URL, CI output hoặc ticket.
6. Có phương án thu hồi khi nghi ngờ lộ hoặc workload retired.

### 9.2. Federation không phải tin mọi OIDC token

Trust policy nhận token từ CI/CD phải giới hạn **issuer, subject/repository, audience, environment** và những điều kiện cần thiết. Chỉ tin một issuer rộng có thể cho job không liên quan lấy quyền production.

### 9.3. mTLS xác thực kênh, không thay phân quyền

Handshake TLS hợp lệ chứng minh peer có certificate phù hợp, nhưng không đồng nghĩa được phép xóa resource. API vẫn cần authorization theo principal, action, resource và tenant.

### 9.4. “Secretless” không có nghĩa không có bằng chứng

Workload không lưu static secret vẫn dùng token, certificate hoặc attestation do runtime cấp. Những bằng chứng ngắn hạn đó vẫn cần bảo vệ khỏi bị đọc hoặc chuyển sang workload khác.

## 10. Bốn vòng đời phải quản lý riêng

Một logical identity có thể tồn tại nhiều năm, trong khi credential thay đổi hằng ngày.

- **Identity lifecycle:** registered, active, owner changed, retired.
- **Credential lifecycle:** issued, rotated, expired, revoked.
- **Entitlement lifecycle:** roles/ACL/grants được cấp, điều chỉnh, review và thu hồi.
- **Session/token lifecycle:** token/phiên đang sống, hạn và cơ chế chấm dứt.

~~~mermaid
flowchart TD
    A[Đăng ký service identity] --> B[Thiết lập trust và grant]
    B --> C[Cấp token/credential ngắn hạn]
    C --> D[Service gọi tài nguyên]
    D --> E[Rotate/Renew proof]
    E --> D
    B --> F[Thay owner, runtime hoặc scope]
    F --> B
    B --> G[Retire workload]
    G --> H[Revoke trust, grant, credential]
    H --> I[Readback effective access]
    I --> J{Đã chặn đúng?}
    J -- Có --> K[VERIFIED_CLOSED]
    J -- Chưa --> L[PARTIAL / escalation]
    L --> I
~~~

### 10.1. Rotate secret không gỡ IAM role

Đổi client secret có thể khiến secret cũ không còn dùng được nhưng principal vẫn giữ cloud-admin. Việc credential được rotate phải đi cùng rà soát entitlement và trust policy, không coi rotation là deprovision.

### 10.2. Token ngắn hạn không thay role ngắn hạn

Token năm phút có thể được xin lại vô hạn nếu trust policy còn cho phép và principal giữ standing role. Khi cần retire, phải chặn **issuance mới** và xử lý token đang lưu hành theo SLA.

### 10.3. Identity có thể nhiều credential

Một service có thể dùng nhiều key hoặc certificate trong quá trình rotation zero-downtime. Inventory phải theo dõi **credential IDs và trạng thái riêng**, tránh vô tình xóa key mới hoặc quên key cũ.

## 11. Service identity registry: biết ai sở hữu và làm gì

Một tổ chức nên có nơi quản lý identity phi con người, không chỉ danh sách secrets.

Ví dụ **JSON mô phỏng**, không phải schema bắt buộc của IdP/cloud:

~~~json
{
  "identityId": "svc-payment-api-prod",
  "type": "WORKLOAD",
  "displayName": "Payment API production",
  "ownerTeam": "payments-platform",
  "businessOwner": "payments-domain",
  "environment": "production",
  "tenant": "tenant-a",
  "runtime": "kubernetes",
  "namespace": "payments-prod",
  "workloadSubject": "cluster-a/payments-prod/payment-api",
  "trustedIssuer": "https://issuer.example.invalid/cluster-a",
  "trustedAudiences": ["ledger-api"],
  "entitlements": [
    {
      "action": "ledger.entry.create",
      "resource": "tenant-a/ledger"
    }
  ],
  "status": "ACTIVE",
  "lastReviewedAt": "2026-11-23T09:00:00+07:00",
  "reviewBy": "2027-02-23T09:00:00+07:00",
  "sourceVersion": 12,
  "changeRef": "CHG-2841"
}
~~~

### 11.1. Metadata thiết yếu

| Nhóm | Thuộc tính cần quan tâm |
|---|---|
| Identity | Stable principal ID, type, issuer/trust domain |
| Ownership | Team, business owner, on-call, contact |
| Runtime | Service, namespace, cluster, environment |
| Trust | Issuer, allowed subject/audience, issuance conditions |
| Authorization | Role/action/resource/tenant và nguồn grant |
| Lifecycle | Created, active/disabled/retired, last-used, review deadline |
| Evidence | Policy version, source version, audit/correlation |

Không lưu private key, password hoặc token nguyên dạng trong registry. Có thể lưu secret reference nếu cần, kèm kiểm soát truy cập.

### 11.2. Display name không phải khóa bất biến

Email alias và service display name có thể đổi. Dùng **immutable principal ID cộng namespace/tenant/issuer** để không thu hồi nhầm identity hoặc tái sử dụng tên cũ.

### 11.3. Owner không tồn tại là rủi ro

Một service principal còn cloud permission nhưng không ai nhận trách nhiệm có thể là **orphan identity**. Tạo exception, cảnh báo, xác minh dependency, reassign owner hoặc deprovision theo policy; không đơn giản xóa ngay workload production chưa hiểu tác động.

## 12. Joiner của service identity: từ nhu cầu đến quyền thực thi

Khi một service/job mới cần gọi API, quy trình Joiner cho máy có thể là:

1. Xác định business purpose và dependency hợp lệ.
2. Ghi owner/approver, service catalog entry và risk tier.
3. Chọn logical principal ID và namespace ổn định.
4. Chọn cơ chế chứng minh workload phù hợp runtime.
5. Giới hạn issuer, audience, subject và environment.
6. Tính minimum actions/resource/tenant cần cấp.
7. Kiểm tra approval và SoD cho role nhạy cảm.
8. Provision identity, trust và target grants.
9. Readback identity và effective access ở hệ thống đích.
10. Gắn telemetry, audit correlation, owner và review date.
11. Kiểm thử hành động được phép và action ngoài scope bị từ chối.
12. Đưa identity vào inventory phục vụ Mover, Leaver và recertification.

### 12.1. Tách dev/staging/prod

Không dùng chung một secret hoặc principal có production rights cho laptop developer, CI test và production runtime. Quyền được cấp theo môi trường và trust boundary.

### 12.2. Không mặc định identity tạo thành công là đã có quyền

Một API tạo principal trả 200 không chứng minh role binding đã propagation. Ngược lại, role đã cấp nhưng runtime chưa nhận trust cũng không có nghĩa hệ thống nên tự mở rộng quyền để chữa lỗi. Readback và chẩn đoán đúng lớp.

### 12.3. Quyền khởi tạo không phải quyền runtime

CI deployment identity có thể cần cập nhật infrastructure; payment-api runtime chỉ cần ledger write. Không gom hai quyền vào một principal để “dễ triển khai”.

## 13. Mover của service identity: thay đổi phạm vi, owner hoặc nơi chạy

Mover xảy ra khi service:

- Chuyển từ cluster/namespace A sang B.
- Chuyển cloud account, tenant hoặc region.
- Thay team owner hoặc business owner.
- Thay API dependency, data classification hoặc mục đích.
- Đổi cơ chế client secret sang workload federation.
- Chia một service thành hai workloads có quyền khác nhau.

### 13.1. Đánh giá desired state, không chỉ cộng quyền

Khi service chuyển từ bucket A sang bucket B:

~~~text
Before:
  permission: object.read on bucket-A

After:
  permission: object.read on bucket-B

Required:
  add permitted access to B
  revoke no-longer-needed grant on A
  verify effective access at both targets
~~~

Nếu chỉ thêm quyền B, access tới A trở thành **quyền tồn dư**.

### 13.2. Chuyển đổi có thể cần chồng trust tạm

Blue/green rollout có thể dùng cả identity/credential cũ và mới. Phải đặt owner, thời gian kết thúc, readback và thông báo khi đường cũ vẫn active quá hạn.

### 13.3. Event cũ không được hồi sinh identity

Khi một Mover job retry sau lệnh retire, workflow phải kiểm tra lifecycle source version và desired state mới nhất trước khi cấp lại grant. Retry idempotent không đồng nghĩa blindly replay old grant.

### 13.4. Bàn giao owner không phải để trống ownership

Nếu owner sang bộ phận mới, update responsibility matrix, approvals và credential access. Không giữ người cũ có quyền secret-manager hoặc production IAM sau khi hết nhiệm vụ.

## 14. Leaver của service identity: retirement và deprovision

Leaver của workload xảy ra khi dịch vụ/job/integration không còn phục vụ nhiệm vụ hợp lệ hoặc được thay thế.

Quy trình:

1. Xác nhận owner và quyết định decommission.
2. Kiểm tra dependencies và impact đến production.
3. Ngừng runtime/job hoặc chuyển traffic sang phiên bản mới.
4. Chặn khả năng xin token/credential mới từ trust/issuer.
5. Thu hồi IAM role, direct ACL, group, resource policy, delegation.
6. Revoke/rotate credential còn có thể sử dụng.
7. Xử lý session/token cũ theo khả năng target và yêu cầu SLA.
8. Readback chính xác mọi target có quyền.
9. Đánh dấu VERIFIED_CLOSED nếu đủ; PARTIAL nếu chưa.
10. Lưu audit và cập nhật inventory owner/status.

### 14.1. Disable không phải invalidate mọi JWT

Một token tự chứa có exp còn hạn vẫn có thể được resource server chấp nhận nếu nó không kiểm tra entitlement hiện hành. Cần token TTL thích hợp, introspection/status checks, denylist, session controls hoặc policy khác theo kiến trúc.

### 14.2. Giữ tài nguyên doanh nghiệp cần thiết

Retire principal không mặc định xóa bucket, database, document hay log nó từng tạo. Bàn giao ownership dữ liệu và chấm dứt identity là hai quy trình tách biệt.

### 14.3. Deprovision phải xác minh target

SCIM hoặc IAM API trả success nhưng có local role ngoài quản lý thì chưa thể gọi tất cả đường quyền đã mất. Readback thực tế và kiểm tra quyền theo rủi ro là cần thiết.

## 15. Khi nhân viên owner Joiner–Mover–Leaver

Không nhầm lifecycle con người và lifecycle dịch vụ.

| Sự kiện | Quyền con người | Service identity |
|---|---|---|
| Owner Joiner | Cấp quyền quản trị theo nhiệm vụ | Chỉ tạo principal khi có service mới thực sự |
| Owner Mover | Thu hồi quyền deploy/secret cũ | Chuyển owner, reviewer, rà grants |
| Owner Leaver | Khóa login và quyền cá nhân | Bàn giao workload, rotate/revoke credential người cũ có thể dùng |
| Service Mover | Không nhất thiết có HR event | Điều chỉnh runtime trust và entitlement |
| Service Leaver | Không nhất thiết có người nghỉ | Decommission principal/trust/grant |

### 15.1. Cẩn trọng key người nghỉ từng tải

Một kỹ sư có thể từng xuất private key của service principal về máy. Chặn IdP login cá nhân không chứng minh key đó không còn dùng được. Cần kiểm tra inventory, provenance và rotate/revoke khi phù hợp.

### 15.2. Tránh cron chạy dưới personal access token

Job sử dụng access token của nhân viên có thể ngừng khi người đó nghỉ, hoặc tệ hơn giữ quyền sau khi không còn trách nhiệm. Thiết kế principal riêng theo workload giúp rõ owner, policy và audit.

### 15.3. Owner của dịch vụ vẫn là người có trách nhiệm

Non-human identity không có người dùng cuối nhưng cần owner quyết định business purpose, role scope, lifecycle và recertification.

## 16. IdP, SSO, SCIM và service identity

| Thành phần | Vai trò điển hình |
|---|---|
| **IdP** | Nguồn identity/trust và xác thực theo nền tảng |
| **SSO** | Đăng nhập người dùng qua nhiều ứng dụng |
| **OAuth AS/STS** | Xác thực client/workload và phát token theo policy |
| **SCIM** | Provision User/Group/membership khi target hỗ trợ |
| **Cloud IAM** | Gắn role/permission cho principal trên resource |
| **PAM/Secret manager** | Quản trị credential và đặc quyền |
| **Service catalog/IGA** | Registry, owner, lifecycle, review và reconciliation |

### 16.1. SSO không phải giải pháp mặc định cho máy

Một bot không cần giả lập browser SSO của nhân viên. Workload có thể dùng OAuth M2M, managed identity, mTLS hoặc federation tùy môi trường.

### 16.2. SCIM không bao phủ mọi loại service principal

SCIM chuẩn hóa User/Group; không mặc định quản lý cloud workload identity, Kubernetes ServiceAccount, private keys, mTLS certificate, client credentials hay API key. Những đối tượng đó thường cần API chuyên biệt.

### 16.3. Gỡ group ở IdP chưa bảo đảm xóa role local

SaaS có thể giữ direct role, local login, API key hoặc session riêng. Reconciliation phải kiểm tra effective access ở target.

## 17. Least Privilege dành cho workload

| Chiều | Biện pháp |
|---|---|
| Action | Chỉ action cần, ví dụ ledger.entry.create |
| Resource | Chỉ database/schema/bucket prefix được giao |
| Tenant | Không đọc tài nguyên tenant khác |
| Environment | Dev principal không có production binding |
| Runtime | Chỉ đúng Pod/VM/CI job được cấp identity |
| Issuer | Chỉ tin issuer và subject được duyệt |
| Audience | Token cho API A không dùng ở API B |
| Time | Credential ngắn hạn, role tạm cho task đặc biệt |
| Delegation | Không tự tạo quyền/secret phụ nếu không cần |
| Network | Network policy bổ sung chứ không thay authz |

### 17.1. Runtime có identity và principal có resource permission

Hai điều kiện riêng: workload có được phép chứng minh/đại diện principal không, và principal có entitlement trên target không. Nếu một trong hai sai phải từ chối.

### 17.2. Grant ngắn hạn vẫn có thể quá rộng

CI job cần deploy một service trong 15 phút không nên nhận organization-admin nếu có permission release hẹp hơn. JIT và least privilege bổ sung cho nhau.

### 17.3. Quyền tạo secondary grants phải được kiểm soát

Một identity có role.assign, credential.create hoặc share.manage có thể tạo access lâu dài sau khi token hiện tại hết. Phải quản lý các quyền phái sinh, delegation và secret lifecycle.

## 18. Access recertification cho non-human identities

Service identity cũng phải được rà soát định kỳ hoặc theo sự kiện.

Một reviewer nên xác minh:

1. Service/job còn chạy hợp lệ và có nhu cầu không?
2. Ai là current owner? Owner có còn thẩm quyền?
3. Principal có đúng runtime, tenant và environment không?
4. Role/actions có còn đúng nhiệm vụ không?
5. Token issuance hoặc API activity có bất thường không?
6. Có credential cũ không còn dùng nhưng chưa revoke không?
7. Có direct grants, local account hoặc share link ngoài registry không?
8. Trust issuer/subject/audience còn đúng không?
9. Có quyền của môi trường cũ còn sau Mover không?
10. Nếu quyết định REVOKE, target đã thực sự chặn chưa?

### 18.1. Không dùng “không có human login” làm bằng chứng không dùng

Workload có thể dùng mTLS hoặc token issuance không xuất hiện trong log SSO người dùng. Cần đúng nguồn telemetry máy, kể cả monthly batch jobs.

### 18.2. KEEP không có nghĩa least privilege

Owner chọn KEEP role cloud-admin mà không có lý do và scope rõ vẫn cần kiểm tra lại. Decision completion không phải quality guarantee.

### 18.3. REVOKE chưa đồng nghĩa đã hết quyền

Nếu IAM gửi revoke nhưng target timeout, giữ PENDING_VERIFICATION/PARTIAL có owner. Chỉ khi đủ bằng chứng mới đánh dấu verified closure.

## 19. Rủi ro bảo mật thường gặp với service identity

Một danh tính không có người tương tác dễ bị bỏ quên vì các job vẫn tiếp tục chạy bình thường trong nhiều năm.

| Rủi ro | Tình huống | Hệ quả |
|---|---|---|
| **Static secret lộ** | Client secret trong Git hoặc CI logs | Kẻ khác lấy token/thay mặt workload |
| **Shared identity** | Nhiều microservice cùng dùng một key | Không truy vết rõ, phạm vi quyền phình to |
| **Overprivileged principal** | Bot đọc log có global-admin | Tác động lớn nếu bị chiếm |
| **No owner** | Service principal tồn tại sau khi team giải thể | Không ai phê duyệt/thu hồi |
| **Wrong audience** | Token cho API A được API B chấp nhận | Token substitution/confused deputy |
| **Trust quá rộng** | Tin mọi OIDC subject của CI issuer | Job không liên quan lấy quyền production |
| **Environment mixing** | Dev workload dùng principal production | Tấn công từ dev sang prod |
| **Token/session còn sống** | Disable principal nhưng JWT cũ vẫn được chấp nhận | Quyền tồn dư sau retire |
| **Local/direct role** | Gỡ group nhưng SaaS giữ role riêng | Effective access còn |
| **Certificate chưa quản trị** | Certificate hết hạn hoặc key bị lộ | Outage hoặc bị giả danh |
| **Privilege propagation** | Bot có quyền tạo API key/role | Secondary access tồn tại lâu |
| **Cross-tenant authorization** | API chỉ xét action, bỏ tenant | Rò dữ liệu giữa khách hàng |
| **Untrusted metadata** | Tin serviceId do caller tự gửi | Giả mạo workload trong logs/policy |
| **Supply-chain compromise** | CI step độc hại lấy proof của runner | Lấy token/triển khai trái phép |

### 19.1. Secret trong code repository

Nếu đã commit secret vào repo, **chỉ xóa dòng khỏi commit mới không đủ**: secret có thể còn trong lịch sử, fork, log hoặc cache. Nên revoke/rotate credential theo quy trình sự cố và hạn chế nơi có thể sử dụng.

### 19.2. Confused deputy khi service làm hộ

Một service có quyền admin để phục vụ một số nghiệp vụ nhưng lại chấp nhận request của bất kỳ caller nào và thực hiện tác vụ dưới quyền admin của chính mình. Cần kiểm tra **caller identity, delegated authorization và resource scope**, không chỉ trust rằng service đang chạy nội bộ.

### 19.3. Không đủ freshness của entitlement

Nếu policy engine cache principal.status=ACTIVE và role cũ quá lâu, service đã retire vẫn có thể gọi API. Đặt ngưỡng freshness và invalidation theo rủi ro, nhất là với privileged operations.

### 19.4. Network isolation không thay identity

Nằm trong VPC, service mesh hay cùng Kubernetes namespace không phải bằng chứng mặc định được phép truy cập mọi resource. Network policy nên bổ sung cho authentication/authorization ở service level.

## 20. Audit và observability cho danh tính dịch vụ

Audit cần trả lời **workload nào, từ runtime nào, đã dùng identity và permission gì, tại target nào và lúc nào**.

Một bản ghi sự kiện giả lập:

~~~json
{
  "eventType": "SERVICE_ACCESS_DECISION",
  "principalId": "svc-payment-api-prod",
  "principalType": "WORKLOAD",
  "serviceOwner": "payments-platform",
  "issuer": "trusted-workload-issuer",
  "target": "ledger-api",
  "tenantId": "tenant-a",
  "action": "ledger.entry.create",
  "resourceRef": "tenant-a/ledger",
  "decision": "PERMIT",
  "policyVersion": "ledger-authz-v3",
  "sourceVersion": 12,
  "timestamp": "2026-11-23T09:18:00+07:00",
  "correlationId": "req-2841"
}
~~~

**Dữ liệu minh họa**. Không log raw access token, client secret, private key, certificate private material hoặc toàn bộ request chứa dữ liệu khách hàng không cần thiết.

### 20.1. Ba loại sự kiện quan trọng

- **Control-plane events:** identity created, role granted, owner changed, trust changed, retired.
- **Credential/token events:** token issuance, key rotation, authentication failure, certificate nearing expiry.
- **Data-plane events:** API authorization decision, sensitive action, resource/tenant scope, denied attempts.

Kết hợp ba loại bằng principal ID và correlation ID giúp điều tra: một role mới được cấp lúc nào, token do issuer nào phát và action nào đã dùng quyền đó.

### 20.2. Metrics vận hành

| Chỉ số | Mục đích |
|---|---|
| Số service identities không owner | Tìm orphan identities |
| Số principal quyền admin còn thường trực | Đo bề mặt đặc quyền |
| Tỷ lệ identities có lastReviewedAt | Đo coverage của recertification |
| Số static secrets quá hạn policy rotation | Giảm rủi ro secret cũ |
| Số workload token bị phát sau decommission | Phát hiện trust chưa thu hồi |
| Số credential sắp hết hạn | Chủ động tránh outage |
| Thời gian revoke-to-enforced | Đo residual access |
| Số grants sai tenant/environment | Phát hiện misconfiguration |
| Số workloads dùng chung một principal | Kiểm soát shared identities |
| Số permission không dùng trong cửa sổ đánh giá | Cơ hội giảm privilege |
| Tỷ lệ review có evidence hợp lệ | Chất lượng kiểm toán |
| Số target còn PARTIAL/PENDING | Ưu tiên deprovision lỗi |

Những chỉ số không có một ngưỡng chuẩn cho mọi tổ chức; cần owner, risk tier và SLA được định nghĩa trước.

### 20.3. Không suy “không có log” là không có quyền

SaaS có thể thiếu telemetry API hoặc job chỉ chạy mỗi quý. LastUsedAt=unknown không phải bằng chứng principal vô dụng. Cần kết hợp source discovery, owner xác nhận, dependencies và target readback.

## 21. Mẫu policy và Java pseudocode

### 21.1. Policy minh họa

~~~yaml
serviceIdentityPolicy:
  identityId: svc-payment-api-prod
  environment: production
  ownerTeam: payments-platform
  trust:
    acceptedIssuer: trusted-workload-issuer
    subjectBinding: cluster-a/payments-prod/payment-api
    allowedAudiences:
      - ledger-api
  authorization:
    action: ledger.entry.create
    resourceScope: tenant-a/ledger
    allowDelegation: false
    requireActiveIdentity: true
  lifecycle:
    reviewCadenceDays: 90
    onRetired: REVOKE_TRUST_AND_ENTITLEMENTS
    onVerificationFailure: PARTIAL_AND_ESCALATE
~~~

Đây là **policy giả lập để học tập**. Cấu hình của cloud IAM, Kubernetes, OPA, OAuth AS hoặc vendor có schema khác; không dùng nguyên văn làm cấu hình production.

### 21.2. Pseudocode xác thực và cho phép

~~~text
function authorizeWorkloadRequest(request):
    token = verifyTokenUsingTrustedIssuerConfig(request.accessToken)

    if token is INVALID:
        return UNAUTHENTICATED

    if token.audience != expectedAudienceForThisAPI:
        return DENY

    principal = authoritativeRegistry.findByTrustedTokenIdentity(token)

    if principal is NONE or principal.status != ACTIVE:
        return DENY

    if principal.environment != requiredEnvironment:
        return DENY

    resource = authoritativeResourceCatalog.get(request.resourceId)
    if resource is NONE:
        return NOT_FOUND

    if principal.tenantId != resource.tenantId:
        return DENY

    if not policyEngine.permit(
        principal,
        action=request.action,
        resource=resource,
        trustedContext=request.verifiedContext
    ):
        return DENY

    recordAuditableDecisionWithoutSecrets(principal, request)
    return PERMIT
~~~

Không tin principal ID, tenant, audience hoặc environment lấy từ header do browser/client tự điền mà chưa xác minh. Triển khai thực phải kiểm tra token type, signature/JWKS/introspection, issuer, audience, thời gian, revocation và resource authorization theo profile của hệ thống.

### 21.3. Java: kiểm tra quyền trên resource sau bước xác thực

~~~java
import java.time.Clock;
import java.time.Instant;
import java.util.Set;

record WorkloadPrincipal(
        String principalId,
        String tenantId,
        String environment,
        boolean active) {}

record ServiceGrant(
        String principalId,
        String tenantId,
        String resourceId,
        Set<String> actions,
        Instant validFrom,
        Instant validUntil) {}

final class ServiceAuthorization {
    static boolean permit(
            WorkloadPrincipal subject,
            ServiceGrant grant,
            String action,
            String resourceId,
            Clock clock) {

        if (subject == null || grant == null || !subject.active()) {
            return false;
        }

        Instant now = clock.instant();

        return subject.principalId().equals(grant.principalId())
                && subject.tenantId().equals(grant.tenantId())
                && "production".equals(subject.environment())
                && grant.resourceId().equals(resourceId)
                && grant.actions().contains(action)
                && !now.isBefore(grant.validFrom())
                && now.isBefore(grant.validUntil());
    }
}
~~~

Đây là **mã Java minh họa logic time + scope** sau khi principal đã được xác thực bởi thành phần tin cậy. Nó **không phải một bộ xác thực JWT hay một authorization system hoàn chỉnh**: chưa xử lý policy inheritance, issuer, audience, token revocation, null field, ABAC, SoD hoặc race condition.

### 21.4. Tại sao không hardcode “production” trong ứng dụng thực?

Đoạn Java dùng constant production để minh họa điều kiện. Trong production, các điều kiện này phải là policy được quản trị, ràng buộc với deployment/tenant thực tế và được đưa qua trusted context. Không tin client tự khai environment=production.

## 22. Kubernetes ServiceAccount: ví dụ tối thiểu

Một ServiceAccount trong Kubernetes là identity namespace-scoped dành cho workload trong cluster. Đó là **đối tượng Kubernetes**, không phải cloud identity tự động được cấp quyền ở mọi provider.

Ví dụ YAML cho một Pod dùng service account riêng, với token được projection có audience giới hạn:

~~~yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: payment-api
  namespace: payments-prod
automountServiceAccountToken: false
---
apiVersion: v1
kind: Pod
metadata:
  name: payment-api-example
  namespace: payments-prod
spec:
  serviceAccountName: payment-api
  automountServiceAccountToken: false
  containers:
    - name: app
      image: registry.example.invalid/payments/payment-api:demo
      volumeMounts:
        - name: identity-token
          mountPath: /var/run/workload-identity
          readOnly: true
  volumes:
    - name: identity-token
      projected:
        sources:
          - serviceAccountToken:
              path: token
              expirationSeconds: 3600
              audience: sts.example.invalid
~~~

Ví dụ dùng registry/audience **không có thật** để minh họa cấu trúc, không phải manifest production được kiểm thử. Workload phải biết **đọc token đã projection**, gửi đúng trust service và bảo vệ file; việc bật projection không tự cấp quyền cloud.

### 22.1. Những điều cần kiểm tra

- Pod gắn đúng ServiceAccount và namespace.
- Không vô tình dùng default ServiceAccount cho workload nhạy cảm.
- Token có audience/TTL hợp lý theo target trust.
- RBAC trong cluster chỉ cấp verb/resource cần thiết.
- Cloud identity mapping (nếu có) chỉ tin đúng issuer/subject.
- Không cấp role admin mặc định cho mọi Pod trong namespace.
- Rotation/refresh token được hỗ trợ bởi SDK/runtime phù hợp.
- Không ghi token vào application log hoặc debug endpoint.

### 22.2. Có cần mount token vào mọi Pod?

Không. Một workload không gọi Kubernetes API hoặc trust provider có thể không cần service account token. Việc tắt auto-mount rồi chỉ projection khi cần giúp giảm khả năng token bị đọc ngoài mục đích. Quyết định cuối phụ thuộc ứng dụng và platform integration.

### 22.3. Kubernetes RBAC khác quyền ở hệ thống ngoài

RoleBinding cho Pod đọc ConfigMap trong Kubernetes không tự cho Pod quyền truy cập cloud database. Đây là hai authority/resource domains khác nhau, cần cấu hình riêng.

## 23. Tình huống xuyên suốt: Payment API gọi Ledger API

### 23.1. Bối cảnh

Một tổ chức có payment-api và ledger-api. payment-api cần tạo bút toán cho tenant A nhưng không cần xóa giao dịch hoặc quản lý tài khoản cloud.

Thiết kế mong muốn:

- payment-api runtime có logical identity riêng.
- Deployment pipeline dùng identity riêng để release.
- Runtime chứng minh workload bằng managed/federated identity.
- Access token dành đúng ledger-api audience.
- Ledger API kiểm tra principal, action, tenant và resource.
- Grants chỉ cho ledger.entry.create trong phạm vi tenant A.
- Log lưu principal, decision và correlation ID.
- Owner và review date được đăng ký trong service catalog.

### 23.2. Một luồng cấp quyền đúng

~~~mermaid
sequenceDiagram
    participant O as Service Owner
    participant IAM as IAM / Registry
    participant W as Payment Workload
    participant AS as Token Issuer / STS
    participant L as Ledger API
    O->>IAM: Register payment-api prod and purpose
    IAM->>IAM: Approve trust and minimal ledger grant
    W->>AS: Present verified workload proof
    AS->>AS: Check issuer, subject, audience and trust
    AS-->>W: Short-lived token for ledger-api
    W->>L: ledger.entry.create for tenant-a
    L->>L: Validate token and exact resource policy
    L-->>W: PERMIT / result
    W->>L: ledger.entry.delete
    L-->>W: DENY / audit
~~~

### 23.3. Ba biến cố thực tế

**Biến cố A — Dev Pod giả identity production.** Một dev workload cố trình token với name payment-api. Nếu trust policy chỉ tin displayName, có nguy cơ giả mạo. Cần trusted issuer/subject/environment binding, không tin name string.

**Biến cố B — Chuyển cluster.** Team chuyển payment-api từ cluster A sang B. Cấp trust mới để rollout; sau khi chuyển xong phải thu hồi cluster A binding. Nếu không, Pod cũ có thể tiếp tục lấy token.

**Biến cố C — Owner nghỉ việc.** Engineer quản lý service nghỉ nhưng payment-api vẫn phục vụ kinh doanh. Chuyển owner, thu hồi quyền cá nhân/secret họ giữ, xem xét rotate credential, không tắt payment-api vô điều kiện.

### 23.4. Điều gì là thành công?

Thành công không chỉ là workload gọi API và nhận HTTP 200; thành công phải có **identity đủ tin, quyền đúng resource, các action ngoài scope bị chặn, owner rõ và vòng đời có thể thu hồi**.

## 24. Tình huống lỗi: nhận diện lớp nào đang sai

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra có kiểm soát |
|---|---|---|
| Không lấy được token | Sai issuer/subject, client auth fail, trust không khớp | Kiểm tra cấu hình trust và logs không chứa secret |
| Token có nhưng API trả 401 | Issuer/audience/signature/time/token type không hợp lệ | Xác minh token profile và expected audience |
| API trả 403 | Principal hợp lệ nhưng thiếu action/resource entitlement | Kiểm tra RBAC/ABAC, tenant và target grants |
| Dev truy cập production được | Principal/trust/group dùng chung quá rộng | Rà environment binding và roles |
| Retire nhưng request vẫn thành công | Token còn sống, target cache, direct role | Đối soát data-plane và hiệu lực revoke |
| Certificate hết hạn gây outage | Thiếu rotation/cert monitoring | Xem expiry và khả năng renew an toàn |
| CI lấy được admin role ngoài dự kiến | OIDC trust policy quá rộng | Rà issuer, subject, audience, branch/environment |
| Service không owner | Catalog/HR Mover chưa đồng bộ | Reassign owner, review granted rights |
| Chặn API A nhưng B còn mở | Grant/credentials được cấp qua đường khác | Kiểm tra inventory mọi targets |
| Role gỡ rồi xuất hiện lại | Retry Mover event cũ hoặc controller drift | So sánh desired state, sourceVersion và idempotency |

### 24.1. 401 và 403 không phải luật tuyệt đối

Nhiều API dùng 401 cho authentication fail và 403 cho authorization fail, nhưng chi tiết phụ thuộc hợp đồng API, gateway và cách che resource existence. Không dựa một status code để kết luận toàn bộ security flow đúng.

### 24.2. Debug không cần in token ra log

Thường có thể ghi key ID, issuer, audience được chuẩn hóa, principal ID, correlation ID và error class đã lọc. Không dump bearer token, client secret hoặc private key để “cho dễ tìm lỗi”.

## 25. Ma trận kiểm thử service identity

| Bài kiểm thử | Kết quả kỳ vọng |
|---|---|
| Workload trình credential hợp lệ đúng issuer | Có thể xác thực theo trust |
| Credential sai/private key không khớp | Từ chối |
| Token hết hạn | Từ chối |
| Token chưa đến nbf | Từ chối |
| Token audience của API A dùng tại B | Từ chối |
| Token do issuer không được tin phát | Từ chối |
| Token không đúng type/profile | Từ chối |
| Principal RETIRED nhưng token còn hạn | Bị chặn theo revocation policy |
| Principal không có grant | Từ chối action |
| Có read nhưng cố delete | Từ chối |
| Tenant A gọi resource tenant B | Từ chối |
| Dev identity dùng token cho production | Từ chối theo environment/trust |
| CI token sai repository/branch | Không được lấy prod token |
| Kubernetes Pod dùng SA khác đã duyệt | Không được gắn prod trust |
| mTLS hợp lệ nhưng thiếu role | Authentication đạt, authorization từ chối |
| API nhận serviceId tự khai không xác minh | Không được coi là principal đáng tin |
| Workload token bị ghi vào log | Phát hiện/khắc phục việc rò rỉ |
| Key rotation có old/new overlap | Không gây outage ngoài window được duyệt |
| Sau rotation old key vẫn usable quá hạn | Cảnh báo và revoke |
| Owner Mover sang team khác | Owner/reviewer, grants và human access được cập nhật |
| Human owner Leaver | Workload hợp lệ tiếp tục; quyền cá nhân bị thu hồi |
| Service Leaver | Trust, grants, credential và token theo policy bị chặn |
| Event Mover cũ retry sau Retire | Không tái cấp quyền |
| Gỡ Group nhưng direct ACL còn | Không báo VERIFIED toàn phần |
| SaaS API revoke trả success nhưng target còn role | PARTIAL và escalation |
| Workload chỉ dùng một permission | Không được cấp role rộng dư thừa |
| Identity không owner | Flag exception và có action owner |
| Shared key giữa 2 workloads | Phát hiện shared principal/rủi ro audit |
| Repeated token issuance sau Retire | Alert và xử lý trust chưa thu hồi |
| Source outage lúc readback | UNKNOWN/PENDING, không ghi VERIFIED |

### 25.1. Kiểm thử fail-closed theo chính sách

Nếu target yêu cầu kiểm tra current grant nhưng PDP không thể phản hồi, hệ thống bảo vệ tài nguyên nhạy cảm thường phải từ chối hoặc áp dụng biện pháp fail-safe đã được phê duyệt. Không mặc định “PDP lỗi thì cho qua”.

### 25.2. Kiểm thử ở đúng boundary

Một service có thể đi qua mesh, gateway, application service và database. Chặn ở gateway nhưng direct backend port vẫn chấp nhận token hoặc local login là bypass cần phát hiện.

### 25.3. Test bằng principal và tài nguyên thử nghiệm

Không tự thay secret production, tắt payment service hoặc tạo key thật khi chạy ví dụ. Sử dụng môi trường kiểm thử và identities được cấp phép.

## 26. Những hiểu lầm phổ biến

**“Service identity là một username có chữ svc.”** Tên không phải bằng chứng; cần principal/trust/credential được xác thực.

**“Service account là nhân viên không có người ngồi máy.”** Một tài khoản máy nên có classification, owner và lifecycle riêng; không mượn user login.

**“Client ID là mật khẩu.”** Client ID thường là định danh, không phải bí mật chứng thực.

**“Đã có token nghĩa là được gọi mọi API.”** Phải kiểm tra issuer, audience, permissions và authorization trên resource.

**“mTLS thành công thì mọi action đều được phép.”** Authentication không thay RBAC/ABAC.

**“Kubernetes ServiceAccount là quyền cloud admin.”** Không; cần trust integration và role binding riêng.

**“Managed identity không cần quản lý.”** Vẫn phải quản lý principal, owner, grant, review và deprovision.

**“Token sống năm phút nên standing admin an toàn.”** Token ngắn không giảm scope quyền admin quá rộng.

**“Đổi secret là đã thu hồi principal.”** Rotation credential không gỡ role hoặc trust bindings.

**“Chỉ cần disable user owner là bot hết quyền.”** Workload principal có thể tiếp tục tồn tại hợp lệ hoặc mang credential độc lập.

**“SCIM gỡ group nghĩa là mọi SaaS session đã hết.”** Không mặc định; cần target readback và xử lý session/role local.

**“Không thấy login nên service account không sử dụng.”** Workload có thể dùng mTLS, STS hoặc token issuance ngoài log human login.

**“Identity đã RETIRED ở catalog nghĩa là mọi API sẽ chặn.”** Control-plane status không chứng minh data-plane enforcement.

**“Một principal dùng chung cho mọi microservice dễ quản lý hơn.”** Có thể tạo blast radius lớn và giảm khả năng audit.

**“Issuer nội bộ nào cũng đáng tin.”** Trust phải có issuer, subject, audience và scope theo chính sách.

## 27. Bài tập tự đánh giá

### Bài tập A: sao lưu bằng tài khoản admin nhân viên

Một job backup chạy bằng email/mật khẩu của kỹ sư vận hành và có toàn quyền cloud.

**Phân tích:** Trộn human identity và workload, khó audit, nguy cơ account Leaver làm job dừng, standing admin quá rộng. Thiết kế service identity riêng, owner, quyền đọc bucket đúng phạm vi, credential/trust ngắn hạn và vòng đời rõ.

### Bài tập B: OIDC trust của CI quá rộng

Pipeline production tin mọi token từ một CI issuer nhưng không giới hạn repository hoặc environment.

**Phân tích:** Job của project khác có thể cố dùng quyền. Cần trust policy ràng buộc issuer, subject/repository, audience, environment/branch và approval cho production.

### Bài tập C: dịch vụ chuyển cluster

Payment API chuyển từ cluster A sang B. Cả hai cluster vẫn lấy được token ở tuần tiếp theo.

**Phân tích:** Có cửa sổ quyền tồn dư trên cluster A. Nên có thời hạn migration, giám sát token issuance và thu hồi cluster A trust khi không còn nhiệm vụ.

### Bài tập D: secret rotation thành công nhưng role quá rộng

Client secret đã được rotate theo tháng, nhưng principal vẫn global-admin dù chỉ đọc log.

**Phân tích:** Rotation là credential hygiene; phải giảm role/action/resource scope và kiểm tra grants.

### Bài tập E: người sở hữu nghỉ việc

Kỹ sư owner service Leaver, nhưng service tiếp tục phục vụ khách hàng.

**Phân tích:** Thu hồi quyền cá nhân, bàn giao owner, rà lại secret đã xuất và quyền deploy; chỉ decommission workload nếu doanh nghiệp không còn cần.

### Bài tập F: thu hồi role nhưng bearer token còn sống

IAM gỡ quyền lúc 09:00, token tự chứa còn exp đến 10:00, API chỉ kiểm tra signature.

**Phân tích:** Phân biệt grant expiry với token expiry; cần chính sách token/session revocation hoặc dynamic entitlement check theo risk/SLA.

## 28. Checklist triển khai Service Identity

1. **Purpose:** service/job có nhiệm vụ được phê duyệt?
2. **Stable ID:** principal ID và trust domain được quản lý?
3. **Identity type:** cloud principal, managed identity, K8s SA hay workload?
4. **Owner:** technical/business owner còn active và có contact?
5. **Environment:** prod, staging, dev được phân biệt?
6. **Tenant:** namespace/tenant/resource scope không bị trộn?
7. **Trust:** issuer, subject, audience và runtime binding rõ?
8. **Credential:** secretless/federation/mTLS nếu hỗ trợ?
9. **Secrets:** không hardcode, có vault và rotation khi cần?
10. **Token:** issuer, audience, type, lifetime được kiểm tra?
11. **RBAC/ABAC:** chỉ cấp action/resource tối thiểu?
12. **Delegation:** không tự mở rộng grant hoặc impersonate caller?
13. **Separation:** deployment identity khác runtime identity?
14. **Provision:** approval và readback có bằng chứng?
15. **Joiner:** identity có registry entry và review date?
16. **Mover:** gỡ trust/role cũ khi đổi runtime, owner hoặc nhiệm vụ?
17. **Leaver:** service retire có kế hoạch revoke/verify?
18. **Human JML:** owner nghỉ không để secret/quyền quản trị cá nhân tồn dư?
19. **SCIM/SSO:** có hiểu giới hạn User/Group so với M2M?
20. **Rotation:** credential đổi không bị nhầm thành grant revoke?
21. **Token/session:** quyền cũ có còn được dùng sau retire không?
22. **Audit:** control plane, token issuance, API decisions được liên kết?
23. **Inventory:** có local/direct grants và các principals ngoài IdP?
24. **Recertification:** có owner, scope và decision evidence?
25. **Monitoring:** phát hiện orphan identities và role không dùng?
26. **Escalation:** target revoke lỗi được đánh dấu PARTIAL?
27. **Verification:** có kiểm chứng effective access thực tế?
28. **Testing:** audience/issuer/tenant/race/replay/credential leak được thử?
29. **Compliance:** log retention, secret handling và quyền xem audit?
30. **Accountability:** ai chịu trách nhiệm identity còn quyền sau khi dịch vụ dừng?

## 29. Tổng kết

**Service identity** là **danh tính dành cho dịch vụ hoặc workload phi con người**, giúp hệ thống biết ai đang gọi tài nguyên, dùng bằng chứng nào để xác thực và có quyền gì tại đúng resource. Nó không phải chỉ là username, một secret, một access token hoặc một Kubernetes ServiceAccount.

Cần tách rõ:

- **Identity/principal:** chủ thể được công nhận.
- **Credential/trust:** bằng chứng và điều kiện được phép đại diện chủ thể.
- **Grant/role:** hành động và tài nguyên được phép.
- **Session/token:** chứng nhận đang có hiệu lực kỹ thuật, có thể có hạn khác grant.
- **Owner/lifecycle:** ai chịu trách nhiệm và khi nào phải thay đổi/thu hồi.

Trong vòng đời **Joiner–Mover–Leaver**, service identity phải được **đăng ký, cấp trust và quyền tối thiểu, thay đổi khi runtime/owner/nhiệm vụ đổi, rồi retire có kiểm chứng**. Các công cụ **IdP, OAuth/STS, SSO, SCIM, RBAC/ABAC, cloud IAM, secret manager và audit** hỗ trợ những khâu khác nhau; không nên kỳ vọng một công cụ tự làm thay tất cả.

**Ghi nhớ:** Một service identity an toàn không chỉ “lấy token được” mà phải **đúng workload, đúng quyền, đúng tài nguyên, đúng thời điểm và thu hồi được**. Khi owner, credential, trust hoặc role thay đổi, cần đối chiếu quyền hiệu lực tại target để giảm **quyền truy cập tồn dư**.



