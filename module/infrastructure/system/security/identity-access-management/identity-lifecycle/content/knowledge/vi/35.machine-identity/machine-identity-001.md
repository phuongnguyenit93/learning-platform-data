# Machine identity là gì? Danh tính của máy và workload trong IAM Identity Lifecycle

**Machine identity** (*danh tính máy*, thường được mở rộng thành *non-human identity* hoặc *workload identity* theo ngữ cảnh) là **định danh được hệ thống tin cậy gắn với một thực thể phi con người** — chẳng hạn dịch vụ, ứng dụng, container, máy ảo, thiết bị, agent hoặc tác vụ tự động — để thực thể đó có thể **chứng minh nó là ai**, được **cấp quyền phù hợp** và chịu **quản trị vòng đời** khi giao tiếp với hệ thống khác.

Ví dụ, một dịch vụ `order-service` muốn gọi `payment-api`. Thay vì gắn mật khẩu của lập trình viên vào mã nguồn, tổ chức có thể cấp cho workload này một danh tính `spiffe://company.example/ns/commerce/sa/order-service` hoặc một danh tính cloud được quản lý, cùng credential/ngữ cảnh tin cậy ngắn hạn. `payment-api` chỉ cho phép thao tác `payment:request` khi **đúng workload**, **đúng môi trường**, **đúng tài nguyên** và **đúng policy**. Khi dịch vụ đổi owner, chuyển môi trường hoặc ngừng hoạt động, quyền và credential liên quan phải được rà soát, thay đổi hoặc thu hồi.

Machine identity là một phần của **Identity and Access Management (IAM)**, nhưng khác với danh tính nhân viên. Trong module **Identity Lifecycle**, chúng ta nghiên cứu **Joiner–Mover–Leaver (JML)** từ xác minh danh tính, tạo account, cấp quyền, rà soát tới thu hồi quyền tồn dư. Với machine identity, cùng các nguyên tắc **identity proofing, provisioning, least privilege, lifecycle, auditing và deprovisioning** vẫn quan trọng, song **nguồn sự thật, cách xác thực, người chịu trách nhiệm và mốc vòng đời** thường đến từ **service catalog, orchestration platform, cloud/IAM, PKI, CI/CD và workload owner** chứ không phải chỉ từ HRIS.

> **Cần nhớ:** **Machine identity ≠ một chuỗi API key**. Identity là “chủ thể nào”, credential là “bằng cách nào chứng minh/chứng thực chủ thể”, còn authorization là “chủ thể được phép làm gì”. Một máy có nhiều credential; một service có thể có nhiều instance; một account có thể đại diện cho một hoặc nhiều workload nếu thiết kế không tách bạch.

## 1. Vì sao hệ thống cần danh tính cho máy?

Một ứng dụng hiện đại không chỉ có người đăng nhập. Hàng chục đến hàng nghìn chương trình tự động trao đổi dữ liệu:

- API backend gọi một microservice khác.
- Job theo lịch lấy dữ liệu từ data warehouse.
- CI/CD pipeline triển khai phần mềm lên cloud.
- Container trong Kubernetes truy cập secret manager.
- Agent giám sát gửi telemetry.
- Máy chủ kết nối database qua TLS.
- Thiết bị IoT báo trạng thái cho control plane.
- Backup agent khôi phục dữ liệu trong sự cố.
- Automation bot tạo/cập nhật account theo yêu cầu IAM đã duyệt.

Nếu các tác vụ này không có danh tính đáng tin, hệ thống đích **không thể phân biệt workload nào** đang gọi API, hoặc phải dùng shared password không thể quy trách nhiệm. Ngược lại, nếu một API key quyền admin được copy sang mọi service, kẻ tấn công chiếm một service có thể **di chuyển ngang (lateral movement)** sang nhiều mục tiêu.

Machine identity giúp đặt những câu hỏi cụ thể:

1. Chủ thể gọi API **thực sự là service/device nào**?
2. Ai/cái gì **phát hành và bảo đảm** thông tin định danh?
3. Credential là gì, được cấp **ở đâu, bao lâu, theo trust nào**?
4. Chủ thể được phép thao tác trên **tài nguyên nào**, trong **môi trường nào**?
5. Ai là **human/service owner** chịu trách nhiệm khi cần thay đổi hoặc thu hồi?
6. Nếu workload bị thay thế hoặc ngừng chạy, **identity, token, certificate, key và grants** được xử lý ra sao?
7. Làm sao phát hiện **orphaned identity** và quyền còn tồn dư?

### 1.1. Một ví dụ không có quản trị machine identity

~~~text
Billing job:
  credential = API_KEY_ADMIN_SHARED
  target = payments-api
  operation = generate-monthly-report

API_KEY_ADMIN_SHARED cũng được dùng ở:
  - deploy pipeline
  - analytics job
  - staging test service

Hậu quả:
  - Không xác định chắc job nào làm thao tác
  - Mỗi job được nhiều quyền hơn cần thiết
  - Đổi key có thể phá cả ba workflow
  - Không biết phải thu hồi gì khi một job bị xóa
~~~

Một thiết kế có quản trị sẽ có **identity riêng hoặc tách biệt hợp lý cho từng workload/trust boundary**, credential có lifecycle và **role/scope tối thiểu**, cộng audit theo target và action.

## 2. Machine identity, non-human identity, workload identity và device identity

Những thuật ngữ này liên quan nhưng **không hoàn toàn đồng nghĩa**.

| Thuật ngữ | Phạm vi điển hình | Ví dụ |
| --- | --- | --- |
| **Machine identity** | Danh tính gắn với hệ thống/máy, dịch vụ hoặc thực thể kỹ thuật, thường qua certificate/key hoặc account kỹ thuật. | VM, server, agent, service. |
| **Non-human identity (NHI)** | Khái niệm rộng cho chủ thể không phải người cần được quản trị trong IAM. | Service account, workload, bot, application integration, device. |
| **Workload identity** | Danh tính của chương trình hoặc đơn vị thực thi workload, có thể độc lập với node vật lý. | Pod/service, job, function, CI pipeline. |
| **Device identity** | Danh tính gắn với thiết bị vật lý hoặc logic và cơ chế xác nhận thiết bị. | Laptop quản lý, gateway IoT, máy chủ edge. |
| **Application identity** | Định danh ứng dụng/integration, đôi khi được biểu diễn bằng OAuth client hoặc service principal. | App backend tích hợp SaaS. |
| **Service account** | Loại account dùng cho dịch vụ/job, tùy nền tảng. | Kubernetes ServiceAccount, database service user. |
| **Service principal** | Thực thể đại diện ứng dụng/dịch vụ ở một số hệ thống IAM/cloud. | Principal được gán role cloud. |
| **Robot/bot identity** | Danh tính cho tác vụ tự động, có thể mô phỏng workflow người dùng. | Bot RPA điền form sau khi được ủy quyền. |

**Điểm phân biệt cốt lõi:** Một **Kubernetes ServiceAccount** là đối tượng định danh/ủy quyền bên trong cluster; nó **không tự đồng nghĩa** một cloud service account hoặc một OAuth client. Một **X.509 certificate** có thể mang tên service/device, nhưng certificate là **chứng thư/credential**, không phải toàn bộ mô hình lifecycle của identity.

### 2.1. Machine identity có thể không gắn “một máy” vật lý

Một service chạy 20 replica:
- Có thể có **một logical workload identity** cho cả service.
- Mỗi replica có credential riêng ngắn hạn chứng minh nó là **instance hợp lệ** của workload.
- Workload mới được autoscale không yêu cầu tạo account người.
- Khi Pod/VM bị thay thế, credential cũ phải hết hạn/không được dùng tiếp, dù logical service vẫn tồn tại.

Ngược lại, cùng một máy chủ có thể chạy nhiều workload **với identity riêng**. Dùng một identity node có quyền cao cho tất cả containers sẽ tạo rủi ro nếu một container bị xâm nhập.

### 2.2. Danh tính logic và danh tính phiên thực thi

Ví dụ:

~~~text
Logical service identity:
  order-service (production, commerce)

Runtime instances:
  pod/order-service-7b8d-1
  pod/order-service-7b8d-2

Credential examples:
  short-lived signed workload JWT
  rotating mTLS certificate

Owner:
  commerce-platform-team
~~~

Policy có thể cấp `orders:write` cho logical service, nhưng issuer chỉ phát credential cho instance đã **chứng minh thuộc workload đúng**. Không nên để một process bất kỳ trên node tự khai rằng nó là `order-service`.

## 3. Identity, account, principal, credential, authentication và authorization

Đây là các lớp dễ bị trộn lẫn nhất khi nói tới machine identity.

| Khái niệm | Câu hỏi | Ví dụ |
| --- | --- | --- |
| **Identity** | Chủ thể kỹ thuật nào đang tồn tại? | Workload `billing-etl` thuộc team Finance Data. |
| **Principal** | Chủ thể mà authorization engine nhìn thấy là ai? | Principal ID `svc-billing-042` trong cloud IAM. |
| **Account** | Bản ghi chứa định danh và trạng thái tại một hệ thống. | Database user `etl_writer`. |
| **Credential** | Chủ thể chứng minh quyền kiểm soát gì? | Private key, JWT, certificate, client secret. |
| **Authenticator/trust proof** | Bằng chứng/chuỗi tin cậy nào xác thực request? | mTLS proof-of-possession, signed token issuer. |
| **Authentication (AuthN)** | Request có chứng minh đúng identity theo policy không? | Certificate được chấp nhận cho đúng service. |
| **Authorization (AuthZ)** | Identity có được làm action này trên resource này không? | `etl_writer` chỉ `INSERT` vào bảng đích. |
| **Entitlement/grant** | Quyền được cấp từ role/group/policy nào? | `DatasetReader` trên dataset-vn. |
| **Session/token context** | Bằng chứng và trạng thái có còn hợp lệ ở thời điểm request? | Token chưa hết hạn, audience đúng, grant chưa revoke. |
| **Owner** | Ai chịu trách nhiệm con người/tổ chức cho identity? | Team billing-platform, service owner. |

### 3.1. Ví dụ phân tách rõ

~~~text
identity:        billing-etl
runtime:         scheduled-job/2026-12
authentication:  projected workload token -> trusted issuer
cloud principal:  svc-billing-etl-prod
authorization:   SELECT billing_view + INSERT monthly_summary
resource:        finance warehouse tenant-vn
owner:           finance-data-platform
~~~

**Client ID hoặc service account name không phải bí mật** chỉ vì dùng để nhận diện client. Điều bảo vệ là **private key/secret, token, cryptographic proof và trust binding** thích hợp; ngược lại, một secret string không có inventory/owner chưa tạo nên identity được quản trị tốt.

### 3.2. Authentication thành công chưa phải quyền được cấp

Một mTLS certificate hợp lệ có thể chứng minh caller là `analytics-service`. Nhưng nếu API chỉ cho `payment:refund` đối với `payment-service`, request từ analytics vẫn phải **DENY**. Xác minh identity là điều kiện cần, không phải giấy phép truy cập mọi resource.

## 4. Những đặc điểm khác biệt so với human identity

| Khía cạnh | Human identity | Machine/workload identity |
| --- | --- | --- |
| Nguồn authoritative | HRIS, contractor registry, person proofing. | Service catalog, cloud/orchestrator, CI/CD, device enrollment, PKI. |
| Định danh | Employee/contractor ID, person binding. | Workload/service/device ID, trust domain, runtime binding. |
| Xác thực | Passwordless/FIDO2, MFA, SSO. | mTLS, workload token, OAuth client auth, signed JWT, managed identity. |
| Vòng đời | Joiner → Mover → Leaver theo quan hệ lao động. | Create/deploy → change/scale/rotate → retire/delete. |
| Owner | Người/tổ chức và manager. | Service owner/team + technical owner; có thể liên quan nhiều nhân viên. |
| Credential | Authenticator gắn với người, có thể dùng MFA. | Keys, certificates, short-lived tokens, workload attestation. |
| Mức hoạt động | Người có session và giờ làm việc. | Chạy 24/7, autoscale, short-lived jobs/replicas. |
| Authorization | RBAC/ABAC theo chức vụ/đơn vị. | RBAC/ABAC theo service, environment, resource, task, identity binding. |
| Thu hồi | Disable person account, revoke các target sessions/tokens. | Revoke identity/grants, stop workload/issuer binding, rotate credentials. |

### 4.1. “Không có người đăng nhập” không có nghĩa không cần governance

Một bot có thể thực hiện lệnh thanh toán, truy cập dữ liệu khách hàng hoặc tạo IAM accounts. Tác động có thể **lớn hơn quyền một nhân viên**. Vì vậy NHI cần owner, approval, review, audit và response khi bị compromise.

### 4.2. MFA của người không phải yêu cầu máy móc cho workload

Một service gọi API không thể bấm push MFA mỗi request như nhân viên. Workload cần **machine-specific AuthN**: trust bootstrap, short-lived credentials, private-key possession, audience restrictions, mTLS hoặc federation. Người quản trị cấp/đổi quyền cho workload vẫn có thể cần **phishing-resistant MFA và phê duyệt độc lập**.

## 5. Machine identity xuất hiện ở những hệ thống nào?

| Nền tảng | Biểu diễn identity thường gặp | Lưu ý |
| --- | --- | --- |
| **Kubernetes** | ServiceAccount gắn Pod, projected service account tokens. | ServiceAccount không tự là permission cloud; cần federation/trust nếu truy cập ngoài cluster. |
| **Cloud IAM** | Managed identity, role-based workload principal, service principal. | Scope/trust riêng theo provider, project, region, tenant. |
| **API/SaaS integration** | OAuth 2.0 client, private-key JWT, client secret. | Client ID chỉ là identifier; bảo vệ credential và scopes. |
| **Service mesh** | Workload ID, mTLS certificate, service identity. | Cần tin đúng issuer/trust domain và ánh xạ authorization. |
| **Database** | Technical DB user, certificate authentication, integrated identity. | Quyền table/schema và connection/session cần review. |
| **CI/CD** | Pipeline/workflow identity, short-lived federation token. | Không mặc định pipeline có quyền production toàn tổ chức. |
| **PKI/TLS** | X.509 identity certificate gắn service/device. | Certificate expiry, key custody, CA trust và revocation. |
| **IoT/Edge** | Device ID, hardware-backed key/certificate. | Enrollment, attestation, mất thiết bị và update trust. |
| **Secrets manager** | Service/workload auth binding, secret access policy. | Secret manager bảo vệ credential, không thay thế least privilege. |

Không có một chuẩn duy nhất mô tả đầy đủ tất cả dạng machine identity trên các hệ thống. Cần phân biệt **định danh logic**, **trust proof**, **grant tại target** và **nguồn quản trị**.

## 6. Cách xác thực một machine identity

Có nhiều cơ chế; lựa chọn phụ thuộc **mô hình đe dọa, nền tảng, khả năng phân phối credential, rotation, tính sẵn sàng và tương thích hệ thống**.

### 6.1. API key và static secret

Một ứng dụng dùng key để gọi API:

~~~http
POST /v1/report-jobs HTTP/1.1
Host: reports.example.invalid
Authorization: Bearer <example-token-or-key>
Content-Type: application/json

{"reportType":"monthly-summary"}
~~~

Key ở ví dụ là **placeholder**, không phải secret thật. Cần lưu ý:
- Key chỉ là credential; **không chứng minh duy nhất process nào đang dùng** nếu nó bị sao chép.
- Phải có owner, scope, issue time, expiry/rotation và revocation path.
- Không hard-code key vào repository, image, frontend, chat hay log.
- Không dùng một admin key chung cho dev/staging/prod.
- Đổi key phải thiết kế rollover để không làm ngắt dịch vụ.

**API key chỉ nên dùng khi phù hợp sản phẩm/threat model**; nếu có workload federation hoặc credential ngắn hạn đáng tin, thường có thể giảm rủi ro từ key sống lâu.

### 6.2. Public/private key và X.509 certificate

Một workload có private key, certificate chứa thông tin định danh và được ký bởi CA/issuer đáng tin. Khi xác thực, bên nhận kiểm tra:
- Certificate chain và trust anchor.
- Certificate chưa hết hạn và thời gian hợp lệ.
- Key usage/extended key usage và certificate policies phù hợp.
- Subject/SAN/service identity đúng ngữ cảnh.
- Proof-of-possession của private key khi giao thức yêu cầu.
- Revocation status nếu hệ thống áp dụng.
- Mapping identity → permissions tại resource.

**Certificate chứa public key không phải private key**. Private key phải được bảo vệ. Một certificate tên `payment-service` có thể hợp lệ trong một trust domain, nhưng **không được tự tin** nếu đến từ CA hoặc môi trường khác.

### 6.3. Mutual TLS (mTLS)

Với mTLS, **cả client và server** có thể trình certificate và chứng minh possession của private key khi thiết lập kênh TLS. Khi cấu hình đúng:
- Client xác thực server.
- Server xác thực client workload/device.
- Dữ liệu được bảo vệ trên kênh.
- Authorization engine vẫn quyết định client có quyền action/resource hay không.

**mTLS giải quyết AuthN/kênh, không tự giải quyết authorization**, và không đảm bảo rằng Pod thực sự thuộc service được mong đợi nếu bootstrap/certificate issuance bị sai.

### 6.4. OAuth 2.0 client credentials

Với một client được phép gọi API dưới danh nghĩa **chính client/workload**, không phải người sử dụng cuối, có thể dùng **client credentials grant** cùng một phương thức client authentication phù hợp.

~~~mermaid
sequenceDiagram
    autonumber
    participant W as Workload client
    participant AS as Authorization server
    participant RS as Resource server
    W->>AS: Token request, client authentication + requested scope
    AS->>AS: Validate client identity, policy, allowed scope
    AS-->>W: Access token (audience/scope/expiry)
    W->>RS: Access token + API request
    RS->>RS: Verify token, audience, scope and runtime policy
    RS-->>W: Permit or Deny
~~~

Những điểm quan trọng:
- `client_id` là định danh client, **không phải secret**.
- Client authentication có thể dùng secret, private-key JWT, mTLS hoặc phương án được hỗ trợ.
- Access token cần **issuer, audience, expiration và scope** phù hợp.
- Không giả định client-credentials token có human identity.
- **OAuth authorization grant** không mặc nhiên có human MFA.
- Target phải kiểm **authorization** từng action/resource, không chỉ token valid.

### 6.5. Workload identity federation và short-lived credentials

Một workload đang chạy ở môi trường A có thể nhận **credential ngắn hạn** cho môi trường B nhờ hệ thống B tin một **issuer** của A, sau khi kiểm tra claim/binding phù hợp.

~~~text
Workload in platform A
    -> presents signed platform identity token
    -> cloud/service B validates issuer, audience, claims and trust policy
    -> B issues scoped short-lived credential
    -> workload accesses intended resource
~~~

Ưu điểm là giảm nhu cầu lưu static cloud key trong container/pipeline. Rủi ro chuyển sang **trust configuration, issuer control, subject binding, audience và token theft**. Một trust policy cho phép “bất kỳ workload nào thuộc cluster/tenant” có thể quá rộng.

### 6.6. Managed identity

Ở một số cloud, một nền tảng có thể cấp **managed identity** gắn tài nguyên/chương trình và chịu trách nhiệm một phần vòng đời credential. **Managed** không có nghĩa quyền đã đúng least privilege hoặc tự động thu hồi theo mọi service lifecycle. Vẫn cần scope/role inventory, owner, log và kiểm tra grants sau khi resource di chuyển/ngừng hoạt động.

## 7. SPIFFE/SPIRE: định danh workload qua trust domain

**SPIFFE (Secure Production Identity Framework For Everyone)** mô tả cách định danh workload bằng **SPIFFE ID** và cơ chế chứng minh danh tính trong hệ thống phân tán. Một định danh minh họa:

~~~text
spiffe://company.example/ns/commerce/sa/order-service
~~~

Ở đây:
- `spiffe://` là scheme cho SPIFFE ID.
- `company.example` là **trust domain** minh họa.
- Đường dẫn tiếp theo là **workload identifier** trong trust domain, do tổ chức định nghĩa.
- Tên/định dạng đường dẫn chỉ minh họa; không mặc định mọi SPIFFE deployment dùng cùng convention.

**SVID (SPIFFE Verifiable Identity Document)** là tài liệu xác thực workload identity, có thể ở dạng **X.509-SVID** hoặc **JWT-SVID**, với đặc tính/trust và use case khác nhau.

### 7.1. SPIRE là gì?

**SPIRE** là một implementation của SPIFFE, có khả năng **workload attestation, node attestation, issuance và rotation** credentials theo cấu hình. Một triển khai có thể đưa SVID tới workloads qua Workload API.

Điểm phân biệt:
- **SPIFFE ID:** định danh logic.
- **SVID:** bằng chứng/chứng thực được phát hành cho ID.
- **SPIRE:** hạ tầng triển khai issuance/attestation/rotation.
- **Authorization policy:** quyết định SPIFFE ID nào được phép hành động ở target.

### 7.2. Attestation trước khi phát identity

Cấp SVID chỉ dựa vào chuỗi tên process do caller tự khai là không an toàn. Hệ thống issuance cần xác minh **node/workload attributes** theo chính sách: orchestration metadata, runtime context, selectors, trust domain, nguồn triển khai hoặc các tín hiệu phần cứng/phần mềm khi phù hợp.

Nếu một attacker có thể chạy workload tùy ý với cùng selector hoặc sửa metadata được tin cậy, họ có thể **nhận identity của service khác**. Phải bảo vệ **registration policy, node trust, issuer keys và attestation pipeline**.

### 7.3. Không đồng nhất SPIFFE với RBAC toàn bộ hệ thống

Một service có SVID hợp lệ không tự được `secret:read-all`. Resource server/service mesh cần **policy** gắn identity với action/resource. Khi service đổi team hoặc decommission, grants gắn SPIFFE ID cần được rà soát/thu hồi riêng, không chỉ để certificate tự hết hạn.

## 8. Kubernetes ServiceAccount và projected tokens

Trong Kubernetes, **ServiceAccount** là đối tượng định danh cho process chạy trong Pod. Pod có thể nhận **ServiceAccount token** được cấp với audience/expiration theo cấu hình; API server hoặc hệ thống liên quan sẽ xác thực token theo trust model.

### 8.1. Một sơ đồ minh họa

~~~mermaid
flowchart LR
    P["Pod: order-service"] --> SA["Kubernetes ServiceAccount"]
    SA --> T["Projected signed token"]
    T --> A["Trusted token verifier / federation"]
    A --> IAM["Workload principal and role mapping"]
    IAM --> API["Target API with scoped permissions"]
    API --> AUD["Audit and reconciliation"]
~~~

**Cần phân biệt:** K8s ServiceAccount dùng để xác thực với Kubernetes API hoặc làm trust input cho workload federation; nó **không tự cấp role** tại cloud/SaaS. Việc liên kết phải do provider IAM/issuer trust configuration đúng.

### 8.2. Token projection và security

Một số thực hành quan trọng:
- Dùng **projected bound service account tokens** với audience/expiration thích hợp khi được hỗ trợ.
- Không mount token Kubernetes API nếu workload không cần.
- Không chia sẻ cùng ServiceAccount cho nhiều workload khác trust boundary chỉ vì tiện.
- Hạn chế permission `pods/exec`, `serviceaccounts/token` và quyền thay đổi Pod spec; chúng có thể cho kẻ tấn công lấy hoặc tạo workload credentials.
- Bảo vệ node/runtime, không coi Pod label do người dùng tự đặt là một bằng chứng đủ.
- Rotate và kiểm tra trạng thái tokens theo cơ chế nền tảng.
- Phân quyền Kubernetes RBAC và cloud resource RBAC **độc lập**.

### 8.3. Ví dụ YAML mang tính khái niệm

~~~yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: order-service
  namespace: commerce
automountServiceAccountToken: false
~~~

YAML trên chỉ định **không tự mount ServiceAccount token theo mặc định** cho Pod dùng ServiceAccount này; khi cần token cho workload federation hoặc Kubernetes API, phải cấu hình volume projection và audience đúng theo sản phẩm. Đây **không phải cấu hình đầy đủ** để triển khai federation hay để chứng minh Pod đã được cấp một cloud role.

## 9. Enrollment và trust bootstrap: máy chứng minh gì khi mới xuất hiện?

Khó khăn đầu tiên của machine identity là **con gà–quả trứng**: workload chưa có credential tin cậy thì làm sao xin credential mới?

Các phương án bootstrap phụ thuộc nền tảng:
- Node/VM được quản lý cấp identity dựa trên hạ tầng cloud.
- Kubernetes service account token được issuer ký.
- Agent được đăng ký và attested theo node/workload selectors.
- Thiết bị có hardware-backed key/certificate từ quá trình sản xuất/enrollment.
- CI/CD runner được cấp short-lived OIDC token gắn pipeline/job.
- Onboarding thủ công qua PKI/CA với xác minh owner và service.

### 9.1. Chuỗi tin cậy phải bắt đầu từ nguồn có thẩm quyền

~~~mermaid
flowchart TD
    CAT["Service catalog / deployment approval"] --> REG["Register workload + owner + environment"]
    REG --> TRUST["Node/workload/device attestation"]
    TRUST --> ISS["Trusted issuer: token/certificate"]
    ISS --> PROOF["Workload proves credential possession"]
    PROOF --> AUTH["Resource server authenticates identity"]
    AUTH --> PERM["RBAC/ABAC authorization"]
    PERM --> LOG["Auditing + revocation lifecycle"]
~~~

Không phải tất cả tổ chức cần một hệ thống attestation phức tạp ngay, nhưng **không được tự coi client-provided service name là bằng chứng đáng tin**.

### 9.2. Khóa được tạo ở đâu?

Một private key có thể được tạo:
- Trong HSM/TPM hoặc secure enclave của thiết bị.
- Trong runtime/agent với bảo vệ hệ điều hành.
- Trong PKI issuance workflow.
- Trong secret manager/kho khóa theo policy.

Mỗi cách có khác biệt về **key exportability, rotation, trust và compromise impact**. Hardware-backed key thường giúp hạn chế trích xuất private key nhưng **không tự bảo đảm code đang dùng key là code an toàn**.

### 9.3. Service owner và identity naming

Một identity cần metadata có quản trị:

~~~text
identityId: workload-prod-commerce-order-service
ownerTeam: commerce-platform
serviceCatalogRef: service-order
environment: production
runtimePlatform: kubernetes-cluster-vn
trustDomain: company.example
status: ACTIVE
reviewAt: policy-defined
~~~

**Tên dễ đọc** hỗ trợ vận hành nhưng không nên là authorization key duy nhất nếu tên có thể đổi/tái sử dụng. Cần ổn định ID/binding hoặc cơ chế tái đăng ký/thay đổi được kiểm chứng.

## 10. Lifecycle của machine identity: tạo, thay đổi và ngừng dùng

Một machine identity **không có ngày nghỉ việc** như nhân viên, nhưng có vòng đời đầy đủ.

~~~mermaid
flowchart TD
    D["Service/project approved"] --> REG["REGISTERED"]
    REG --> ENR["ENROLLED: trust/bootstrap"]
    ENR --> ACT["ACTIVE: credential + scoped grants"]
    ACT --> ROT["ROTATING: new key/token/cert"]
    ROT --> ACT
    ACT --> CHG["CHANGED: owner, env, role, scope"]
    CHG --> ACT
    ACT --> SUS["SUSPENDED: security risk/compromise"]
    SUS --> ACT
    ACT --> RET["RETIRED: no workload need"]
    SUS --> RET
    RET --> REV["REVOKING grants, credentials, sessions"]
    REV --> VER["VERIFIED_CLOSED"]
~~~

### 10.1. Create / enroll / provision

- Xác minh **service tồn tại, đã được chấp thuận và có owner**.
- Ghi **stable identity ID** với environment/trust domain.
- Thiết lập issuer trust, attestation rule và account binding.
- Cấp **credential** theo cách phù hợp.
- Provision **least-privilege role/permission** tại target.
- Kiểm tra positive/negative API authorization.
- Gắn expiration, rotation và review schedule.

### 10.2. Change / rotate / move

- Đổi owner/team, service name, project, tenant hoặc môi trường.
- Tăng/giảm replicas, đổi cluster và trust domain.
- Thay quyền khi task thay đổi, đánh giá SoD nếu có.
- Rotate certificate/key/token với rollover tránh downtime.
- Tách identity mới khi trust boundary thay đổi đáng kể.
- Thu hồi grants và credentials cũ khi cutover hoàn thành.
- Cập nhật service catalog, logs, approver route và monitoring.

### 10.3. Retire / deprovision

- Xác định workload/service **đã thực sự hết nhu cầu**.
- Revoke OAuth clients/service principals, cloud roles, app direct grants.
- Gỡ trust binding, issuer mappings hoặc workload registration phù hợp.
- Disable/rotate secrets, keys, certificates; xử lý sessions/tokens.
- Loại bỏ scheduled automation có thể tạo lại identity.
- Xóa hoặc lưu metadata theo chính sách nhưng **không xóa dấu vết audit cần thiết**.
- Đọc lại target access và kiểm tra credential không còn được chấp nhận.

### 10.4. Account tồn tại nhưng workload đã chết là rủi ro

Một Pod bị xóa không có nghĩa:
- OAuth client registration bị xóa.
- Cloud role assignment bị thu hồi.
- Static API key trong vault bị vô hiệu hóa.
- Certificate chưa hết hạn không còn được tin.
- CI/CD secret không được copy ở đâu khác.

**Workload termination ≠ identity deprovisioning**. Hãy quản lý **grant source** và **credential inventory**, không chỉ tài nguyên runtime.

## 11. Joiner–Mover–Leaver của người và machine identity gắn nhau thế nào?

Một workload thường có **human accountable owner**, sponsor hoặc service team. Khi nhân viên Joiner/Mover/Leaver, phải xem ảnh hưởng tới **quyền quản trị workload**, không tự giả định workload phải dừng.

### 11.1. Human Joiner

Engineer mới vào team:
- Có thể được cấp **viewer/operator role** theo assignment.
- Không mặc định được xem/rotate tất cả secrets của service.
- Quyền quản trị service principals, workload roles và CI/CD pipelines có thể cần approval, MFA, SoD.
- Nếu được giao ownership, cập nhật service catalog và owner authority.
- Không cho engineer tạo workload principal với `CloudOwner` mà không có policy.

### 11.2. Human Mover

Lan chuyển từ đội Commerce sang Finance:
1. HRIS tạo Mover event theo hiệu lực.
2. IAM tính KEEP/REMOVE/GRANT/REVIEW cho quyền con người.
3. Thu hồi quyền của Lan vào **Commerce CI/CD, secret manager, cloud IAM, cluster admin, runtime logs nhạy cảm** nếu không còn căn cứ.
4. Cập nhật **owner/contact/escalation** của `order-service` nếu Lan từng là owner.
5. Đánh giá credential Lan từng có thể lấy/copy, rotate nếu cần.
6. **Không xóa logical workload identity** nếu service vẫn phục vụ Commerce.
7. Reconcile granted access tại target và kiểm tra không còn đường impersonation.

### 11.3. Human Leaver

Khi Lan nghỉ việc:
- Disable IdP/SSO account và privileged accounts liên quan.
- Gỡ role IAM/PAM cho con người vào workload/service.
- Revoke personal access tokens, keys, certificates/credentials do Lan kiểm soát.
- Chuyển service owner/team và on-call responsibility.
- Rotate workload secrets **nếu có rủi ro Lan vẫn biết/truy cập**, với kế hoạch không cắt dịch vụ.
- Xử lý direct grants hoặc CI/CD permissions ngoài IdP.
- Không coi Leaver đã hoàn tất chỉ vì account IdP bị disable.

**Điểm phân biệt:** Leaver là của **người**; service vẫn có thể là **ACTIVE**. Workload chỉ trở thành **RETIRED** khi nhiệm vụ/dịch vụ thực sự ngừng theo owner/service lifecycle.

### 11.4. Service retirement là “Leaver” tương đương của máy

Có thể mượn tư duy Joiner–Mover–Leaver để mô tả:
- **Machine Joiner:** dịch vụ/job được tạo, đăng ký, attested, provision.
- **Machine Mover:** đổi owner/environment/role/trust, rotate và hạ quyền.
- **Machine Leaver:** workload decommission, revoke grants/credentials, kiểm chứng không còn truy cập.

Đây là **phép tương tự về lifecycle**, không phải ngữ nghĩa HRIS hay SCIM bắt buộc. Một container ngừng chạy không tự là “Machine Leaver” nếu logical service vẫn còn replicas khác.

## 12. IdP, SSO và SCIM có quản lý machine identity không?

### 12.1. IdP/SSO chủ yếu gắn human interactive AuthN, nhưng có tích hợp máy

IdP có thể là nơi quản lý:
- Human SSO (OIDC/SAML) và MFA.
- OAuth clients và service principals, tùy sản phẩm.
- Token issuer cho workload federation.
- Application/group assignments.
- API authorization policies.

Nhưng **không nên gọi một service account dùng client credentials là “đăng nhập SSO như nhân viên”**. Máy–máy thường không có browser redirect, end-user consent session hoặc human MFA trong mỗi lần gọi.

### 12.2. SCIM có giới hạn

**SCIM 2.0** chuẩn hóa những tài nguyên phổ biến như **User/Group** và các thao tác provisioning; một provider có thể có extension. SCIM **không cung cấp một mô hình phổ quát để quản trị mọi loại machine/workload identity, issuer trust, X.509 certificate, Kubernetes ServiceAccount, cloud role hay session/token**.

Một service account được biểu diễn như User tại một sản phẩm **không có nghĩa** mọi service account ở mọi nơi đều được SCIM deprovision đầy đủ. Cần target-specific APIs và grant inventory.

### 12.3. Mối liên hệ RBAC/ABAC

- **RBAC**: role `OrderServicePublisher` cho phép `orders:publish`.
- **ABAC**: chỉ khi `environment=production`, `tenant=vn`, `resource.classification` phù hợp.
- **Trust/authentication**: xác minh caller thực sự là `order-service` trong môi trường hợp lệ.
- **Provisioning**: cấp/gỡ role ở IAM/cloud/target.
- **Reconciliation**: bảo đảm actual permission khớp desired.

**SSO/token issuer** và **permission engine** có thể là các hệ thống khác nhau. Máy đã được issuer công nhận không có nghĩa nên được grant mọi role.

## 13. RBAC và ABAC cho workload: đúng action, resource và environment

Ví dụ `order-service` cần:
- Đọc cấu hình thuộc namespace commerce.
- Ghi order events vào queue phù hợp.
- Không đọc thanh toán nguyên thủy từ data lake.
- Không chỉnh IAM policy hoặc secrets của hệ thống khác.

~~~text
permitPublishOrderEvent =
    subject.identityId == "order-service-prod"
    AND subject.trustDomain == "company.example"
    AND subject.environment == "production"
    AND action == "orders:publish"
    AND resource.queueId == "commerce-order-events-vn"
    AND resource.tenantId == subject.tenantId
    AND validWorkloadAuthenticationContext
~~~

Đây là **pseudocode chính sách**; thực tế cần kiểm tra issuer, token/audience, identity binding, claims và policy data tại trusted PDP/PEP. Không tin `environment=production` từ HTTP header tự khai.

### 13.1. Role assignment và resource policy

Một workload có thể có quyền từ:
- Service account role.
- Group membership.
- Cloud IAM role.
- Resource-based policy.
- Database GRANT.
- K8s RoleBinding/ClusterRoleBinding.
- Delegated identity/impersonation.
- Token scope và dynamic ABAC rule.

Thu hồi một role nhưng còn **resource policy** hoặc static key quyền cao thì effective access có thể vẫn tồn tại. Cần tìm **grant paths**, không chỉ role trực tiếp.

### 13.2. Không cho workload tự nâng quyền

Các quyền như `iam:assign-role`, `serviceaccounts/token`, `secrets:read-all`, `cloud:owner` hoặc `policy:edit` có thể cho workload:
- Tạo credential mới.
- Giả danh service khác.
- Tự gán privilege cao hơn.
- Đọc bí mật để di chuyển ngang.
- Sửa audit/logging và che giấu hành động.

**Least privilege bao gồm cả đường leo thang gián tiếp**, không chỉ API mà service đang gọi lúc bình thường.

### 13.3. Dữ liệu dynamic không làm role dư thừa tự mất

ABAC condition có thể chặn permission khi workload chuyển từ staging sang production, nhưng **role cũ tại target vẫn có thể tồn tại** và được dùng ở endpoint khác. Phải thu hồi entitlement không còn căn cứ, đồng thời dùng request-time authorization.

## 14. Xác định ranh giới môi trường và tenant

Một lỗi nguy hiểm là dùng **cùng một machine identity/credential** cho development, staging và production. Nếu môi trường staging bị chiếm, attacker có thể lấy credential production.

Một cách phân tách:

| Thuộc tính | Development | Production |
| --- | --- | --- |
| Logical identity | `order-service-dev` | `order-service-prod` |
| Trust domain/issuer | Được phân tách theo policy. | Issuer/trust protected production. |
| Resource scopes | Test queues/datasets. | Chỉ queue/dataset production cần thiết. |
| Credential | Ngắn hạn/dev-scoped. | Ngắn hạn/prod-scoped, bảo vệ chặt. |
| Owner/approval | Dev owner. | Production owner + risk approval khi cần. |
| Audit | Development logs. | Protected production logs/monitoring. |

### 14.1. Không chỉ dùng prefix tên để phân tách

Thêm hậu tố `-prod` vào tên account không đủ nếu cùng một key/trust policy vẫn mở đường sang production. Ranh giới phải được enforce ở **issuer, trust binding, role, resource policy, network và runtime authorization** phù hợp.

### 14.2. Multi-tenant service identity

Một service có thể xử lý nhiều tenant. Không được lấy danh tính hợp lệ của service làm lý do được truy cập tất cả tenant. API phải kiểm:
- Actor workload identity.
- Tenant/resource của request.
- Context được workload phép xử lý.
- Delegation/on-behalf-of nếu service làm thay người.
- Data-level constraints.
- Audit tenant và authorization decision.

## 15. Workload thay người dùng cuối: service identity và user context

Một microservice có thể gọi API theo hai cách:

1. **App-only (machine-to-machine)**: service tự gọi theo quyền của chính nó, ví dụ batch tổng hợp dữ liệu.
2. **Delegated / on-behalf-of user**: service gọi một downstream API trong ngữ cảnh người dùng đã xác thực.

Hai mô hình **không nên trộn lẫn**.

### 15.1. App-only

`billing-job` dùng OAuth client credentials để ghi báo cáo định kỳ. Resource server đánh giá **service principal** và scopes/app roles.

### 15.2. On-behalf-of user

`portal-api` nhận yêu cầu từ Lan và phải đọc tài liệu chỉ Lan được xem. Nếu nó chỉ dùng một superuser machine credential để đọc mọi tài liệu, ứng dụng có thể tạo **confused deputy**: quyền rộng của backend bị lợi dụng để vượt quyền người dùng.

Cần áp:
- Token exchange/delegation theo giao thức và nền tảng hỗ trợ.
- Audience/scope phù hợp từng downstream API.
- Quyền của **workload** và **end-user** đều được kiểm tra nếu chính sách yêu cầu.
- Object/tenant-level authorization tại resource.
- Chống tự khai user ID, spoofing headers và token forwarding sai audience.

### 15.3. Audit cả hai thực thể khi cần

~~~json
{
  "action": "document:read",
  "actorWorkloadIdentity": "portal-api-prod",
  "endUserIdentityId": "person-2048",
  "targetResource": "document-882",
  "tenant": "tenant-vn",
  "result": "PERMIT"
}
~~~

JSON minh họa. **Không bắt mọi app-only request phải có endUserIdentityId**; ngữ nghĩa audit phải đúng loại grant. Nếu có user context, tránh ghi full token hay dữ liệu riêng tư không cần thiết.

## 16. Credential lifecycle: tạo, phân phối, rotate và revoke

### 16.1. Không xem credential rotation là một dự án làm một lần

Credential có lifecycle riêng:

~~~mermaid
flowchart LR
    G["Generate protected secret/key"] --> I["Issue/Bind to identity"]
    I --> D["Deliver via trusted channel"]
    D --> U["Use with least-privilege policy"]
    U --> R["Rotate/renew"]
    R --> U
    U --> X["Expire/Revoke"]
    X --> V["Verify old credential unusable"]
~~~

Credential inventory nên có:
- Credential ID/kind, issuer và subject.
- Owner/service và target.
- Issued time, expiration/rotation policy.
- Storage/binding (vault, workload projection, hardware).
- Resource/audience/scopes.
- Last seen/usage telemetry khi có.
- Revocation/rotation result và next action.

### 16.2. Rotation với overlapping validity

Một DB client có thể không chuyển sang key mới ngay khi được phát. Quy trình rotation an toàn thường:
1. Phát credential mới.
2. Cập nhật workload/secret reference theo phân phối an toàn.
3. Kiểm thử truy cập hợp lệ với credential mới.
4. Ngừng dùng credential cũ.
5. Thu hồi credential cũ.
6. Đối soát target sessions/keys và kiểm chứng không còn sử dụng.

**Overlapping validity** có thể giúp tránh downtime, nhưng nên ngắn và có deadline. Không để key cũ active vô hạn “đề phòng rollout chưa xong”.

### 16.3. Ngắn hạn không đồng nghĩa an toàn tuyệt đối

Một token tồn tại 5 phút vẫn có thể bị đánh cắp và dùng ngay; một attacker có thể tiếp tục xin token mới nếu họ đã chiếm workload hoặc issuer trust. Cần cả:
- Attestation và issuer trust.
- Protected runtime/metadata endpoints.
- Resource scopes/audience.
- Revocation/incident response.
- Monitoring và phát hiện token replay.
- Hardening host/container/pipeline.
- Rotation và compromise response.

### 16.4. Certificate expiry và revocation

Certificate hết hạn làm nó không còn hợp lệ trong quá trình validation **nếu bên nhận thực thi đúng**. Certificate bị thu hồi trước hạn có thể đòi CRL/OCSP hoặc cơ chế trust revocation khác theo PKI; không phải mọi client đều kiểm tra revocation. Không tuyên bố “revoke certificate là mọi kết nối đang mở tự ngắt”.

### 16.5. Token expiry và session lifetime

OAuth JWT access token có `exp` riêng; resource server có thể còn cache authorization hoặc giữ session vượt hạn role. Khi machine identity Leaver/retire, cần xét **access/refresh tokens, client secrets, certificates và phiên đã mở** theo cơ chế thực tế.

## 17. Rủi ro bảo mật phổ biến của machine identity

| Rủi ro | Diễn biến | Phòng ngừa/giảm thiểu |
| --- | --- | --- |
| **Hard-coded secret** | API key được commit vào Git hoặc image. | Secret manager, scanning, short-lived federation, rotate khi lộ. |
| **Shared admin credential** | Nhiều workloads dùng cùng key toàn quyền. | Tách identity, scoped grants, inventory. |
| **Orphaned identity** | Job đã xóa nhưng cloud principal/key vẫn active. | Service catalog sync, lifecycle deprovisioning. |
| **Overprivileged service account** | Workload có `ClusterAdmin` để đọc một config. | JEA/RBAC/ABAC scope, policy review. |
| **Trust policy quá rộng** | Bất cứ pipeline nào trong org xin role prod được. | Subject/audience/environment binding, approval. |
| **Token theft/replay** | Attacker lấy workload token từ pod/metadata. | Runtime hardening, short TTL, audience/replay controls. |
| **Certificate/private key leak** | Key bị copy sang host khác. | Key protection, revocation/rotation, attestation. |
| **Privilege escalation** | Workload tự tạo service account admin hoặc sửa policy. | Giới hạn IAM/admin permissions và SoD. |
| **Confused deputy** | Backend dùng quyền riêng bỏ qua quyền user. | Delegated context, object authorization, policy. |
| **Cross-tenant access** | Service hợp lệ nhưng gọi resource tenant khác. | Tenant-aware ABAC, claims and resource checks. |
| **Stale token/session** | Role đã gỡ nhưng token cũ còn được nhận. | Runtime authorization, session expiry/revocation. |
| **Supply-chain compromise** | Runner/CI job độc hại nhận production identity. | Provenance, scoped trust, protected workflows. |
| **Device cloning** | Private key bị trích xuất dùng trên thiết bị giả. | Hardware-backed keys, attestation/rotation. |
| **Owner Leaver** | Người rời công ty còn nắm credential/workload admin. | Human JML linked owner handover and rotation. |
| **Log forgery/erasure** | Bot được phép sửa/xóa audit. | Immutable/separate logging, least privilege. |

### 17.1. Compromise không chỉ xảy ra do key lộ

Một attacker có thể **chiếm đúng workload** và dùng issuer cấp token mới hợp lệ. Rotation một key có thể chưa đủ; cần xử lý **runtime compromise, trust binding, workload deployment, CI/CD source và permission**.

### 17.2. Device inventory không đủ cho service identity

Danh sách VMs chỉ cho thấy máy đang chạy. Serverless jobs, SaaS integrations, OAuth clients, ephemeral containers và API keys có thể tồn tại **không có VM cố định**. NHI inventory nên liên kết đa nguồn, không chỉ CMDB máy chủ.

## 18. Machine identity inventory: phải biết mình có bao nhiêu và ai sở hữu

### 18.1. Những trường hữu ích

| Trường | Ý nghĩa |
| --- | --- |
| `identityId`, `type` | Định danh bền vững và loại NHI. |
| `serviceCatalogRef` | Dịch vụ/job/device mà identity đại diện. |
| `ownerTeam`, `businessOwner` | Người/đơn vị chịu trách nhiệm. |
| `environment`, `tenant` | Phân tách dev/prod, tổ chức/đơn vị. |
| `platform`, `trustDomain` | Cloud/cluster/issuer/PKI namespace. |
| `accountRefs` | Target accounts, service principals, K8s SAs. |
| `credentialRefs` | Key/certificate/token registration (không lưu plaintext). |
| `grants`, `effectivePermissions` | Role, direct grants, resource policy và inherited rights. |
| `createdAt`, `lastSeenAt` | Thời điểm tạo/sử dụng, có thể không đầy đủ. |
| `rotateBefore`, `expiresAt` | Lịch rotation/expiry. |
| `reviewPolicy`, `reviewDueAt` | Access recertification theo risk. |
| `decommissionRef` | Sự kiện ngừng dịch vụ và các task thu hồi. |
| `status` | Registered/Active/Suspended/Retired/VerifiedClosed. |

### 18.2. Nguồn dữ liệu để đối soát

- Service catalog/CMDB và application ownership registry.
- Cloud IAM/service principal lists.
- Kubernetes ServiceAccounts, RBAC bindings và Pod serviceAccountName.
- OAuth client registrations và API gateway credentials.
- PKI/certificate inventory, secret manager và vault.
- Database technical users.
- CI/CD service connections, runners và pipeline identity.
- Device enrollment và hardware key registry.
- Target application access logs và grants.

**Không có một connector duy nhất bảo đảm thấy mọi NHI.** Cần deduplicate bằng stable IDs và account binding, tránh vừa bỏ sót vừa đếm trùng credential của cùng identity.

### 18.3. Last used không đủ để xóa

Một recovery workload có thể không dùng sáu tháng nhưng rất quan trọng. Với identity không thấy hoạt động:
- Xác minh service owner.
- Kiểm tra lịch chạy, dependency và disaster-recovery plan.
- Xác định liệu nó là emergency capability hợp lệ.
- Thiết kế retirement/secret rotation không gây lockout.
- Dùng expiry/approval và kiểm thử thay vì giữ credential toàn quyền vô hạn.

## 19. Access recertification và SoD cho danh tính máy

### 19.1. Reviewer không nhất thiết là HR manager

Machine identity có thể do:
- Service/application owner.
- Platform/security owner.
- Data owner.
- Risk/SoD reviewer theo loại entitlement.
- PAM privileged reviewer.
- Service account sponsor/team lead.

Người đã nghỉ việc không thể tiếp tục làm certifier chỉ vì tên được lưu trong secret metadata.

### 19.2. Những câu hỏi review

1. Dịch vụ còn hoạt động và có owner hợp lệ không?
2. Credential có còn cần, có tồn tại bản sao không?
3. Quyền có vượt nhu cầu công việc không?
4. Có quyền admin/impersonation hoặc self-grant không?
5. Trust domain, issuer, audience, resource scope có đúng không?
6. Có static keys, certificates sắp hết hạn, tokens bất thường không?
7. Có thể chuyển sang short-lived workload federation không?
8. Owner con người vừa Mover/Leaver có còn truy cập bí mật không?
9. Có xung đột SoD ở CI/CD: cùng identity sửa code, approve, deploy và xóa log?
10. Khi retire, quyền tại target và sessions đã chặn được chưa?

### 19.3. SoD áp cho workload như thế nào?

Một pipeline vừa **build artifact**, vừa **tự approve release**, vừa **deploy production** có thể làm mất independent review dù nó không phải người. Cần:
- Tách identity/trust giữa build và production deploy khi phù hợp.
- Protected branches/approval policies.
- Artifact provenance/signatures.
- Approval của người có authority độc lập.
- Deploy token chỉ có scope và thời gian cần.
- Audit code revision, job ID, actor phê duyệt và target.

**Không dùng luận điểm “bot không phải người nên không cần SoD”**. SoD phụ thuộc khả năng hoàn thành một chuỗi hành động nhạy cảm không có kiểm tra độc lập.

## 20. Kiến trúc tham khảo từ workload tới API

~~~mermaid
flowchart LR
    C["Service catalog/owner"] --> REG["Register identity + policy"]
    RUN["Workload runtime"] --> ATT["Attestation/platform identity"]
    REG --> ISS["Trusted issuer / IAM"]
    ATT --> ISS
    ISS --> CREDS["Short-lived workload credential"]
    CREDS --> API["API gateway/service PEP"]
    POL["RBAC/ABAC policy"] --> API
    API --> DATA["Target resource"]
    API --> LOG["AuthN/AuthZ audit events"]
    REG --> REC["Reconciliation/recertification"]
    LOG --> REC
    REC --> REV["Revoke/reduce/rotate on change or retirement"]
    REV --> ISS
    REV --> API
~~~

### 20.1. Trình tự runtime

~~~mermaid
sequenceDiagram
    autonumber
    participant W as Workload
    participant I as Identity issuer
    participant AS as Token service
    participant RS as Resource server/PEP
    participant AUD as Audit
    W->>I: Prove deployment/runtime identity
    I-->>W: Signed workload assertion or credential
    W->>AS: Exchange/authenticate as workload
    AS->>AS: Verify issuer, subject, audience, trust policy
    AS-->>W: Scoped short-lived access token
    W->>RS: API call with access token
    RS->>RS: Verify token + resource authorization
    RS-->>W: Permit or Deny
    RS-->>AUD: Identity, action, resource, result
~~~

Đây là sơ đồ **khái niệm**. Một triển khai thực tế có thể dùng mTLS trực tiếp và không có token exchange, hoặc issuer và authorization server là cùng hệ thống. Không coi mũi tên token issuance là bằng chứng tất cả permissions đều đã được approve.

### 20.2. Source of truth không phải luôn là IdP

- Logical service owner từ service catalog.
- Workload/runtime attestation từ orchestrator/cloud.
- Credential từ PKI/token issuer.
- Target grants từ cloud/app/DB IAM.
- Human approver từ HRIS/IGA.
- Risk/SoD policy từ Security/IGA/GRC.

Cần xác định **nguồn nào có thẩm quyền với trường nào**, tránh một hệ thống đồng bộ stale dữ liệu và tái cấp quyền đã thu hồi.

## 21. JSON identity record minh họa

Một bản ghi quản lý NHI có thể như sau:

~~~json
{
  "identityId": "workload-prod-commerce-order-service",
  "identityType": "WORKLOAD",
  "status": "ACTIVE",
  "service": {
    "catalogRef": "service-order",
    "environment": "production",
    "tenant": "tenant-vn",
    "ownerTeamRef": "commerce-platform"
  },
  "trust": {
    "platform": "kubernetes",
    "trustDomain": "company.example",
    "subjectRef": "spiffe://company.example/ns/commerce/sa/order-service",
    "issuerRef": "workload-issuer-prod"
  },
  "accounts": [
    {
      "systemRef": "orders-event-bus",
      "principalRef": "svc-order-publisher-prod"
    }
  ],
  "grants": [
    {
      "resourceRef": "commerce-order-events-vn",
      "actions": ["orders:publish"],
      "scope": "tenant-vn"
    }
  ],
  "credentialGovernance": {
    "type": "SHORT_LIVED_FEDERATION",
    "rotationManagedBy": "platform-workload-issuer"
  },
  "review": {
    "policyRef": "nhi-prod-review-v2",
    "ownerRequired": true
  }
}
~~~

**Đây là dữ liệu nội bộ minh họa**, không phải schema chuẩn SCIM, SPIFFE, Kubernetes hay OAuth. Trong thực tế cần bảo vệ integrity và identity references; **không đặt private key, client secret hoặc access token đầy đủ** vào inventory.

### 21.1. Event audit nên liên kết identity và runtime

~~~json
{
  "eventId": "authz-2026-4381",
  "timestamp": "2026-12-02T03:15:00Z",
  "actor": {
    "identityId": "workload-prod-commerce-order-service",
    "runtimeRef": "k8s-pod-ref-77",
    "issuerRef": "workload-issuer-prod"
  },
  "request": {
    "action": "orders:publish",
    "resourceRef": "commerce-order-events-vn",
    "tenant": "tenant-vn"
  },
  "decision": "PERMIT",
  "policyRef": "orders-publisher-v4",
  "correlationId": "request-2026-9901"
}
~~~

Audit có thể ghi workload logical ID lẫn runtime instance khi có bằng chứng đáng tin; tránh ghi secret, full JWT, password, private key hay payload dữ liệu nhạy cảm. **Log chỉ có giá trị khi target thực sự enforce quyết định** và người có quyền cao không thể xóa dễ dàng.

## 22. Pseudocode: đăng ký và cấp quyền machine identity

~~~text
function enrollWorkload(serviceRef, runtimeInfo, requestedAccess):
    service = loadApprovedServiceCatalogEntry(serviceRef)
    require service.active
    require service.ownerTeamExists
    require runtimeInfo.platformAndEnvironmentAreTrusted

    identity = allocateStableWorkloadIdentity(
        serviceRef, runtimeInfo.environment, runtimeInfo.trustDomain
    )

    require attestationPolicyCanVerify(runtimeInfo, identity)
    require requestedAccess within service.approvedLeastPrivilegePolicy
    require noApplicableSoDOrPrivilegeEscalationConflict
    require approvalForSensitiveGrantsIfPolicyRequires

    registerIdentityAndIssuerBinding(identity, runtimeInfo)
    issueOrEnableShortLivedCredentialFlow(identity)
    provisionApprovedResourceGrants(identity, requestedAccess)

    actual = readTargetAccountAndEffectivePermissions(identity)
    require actual matches approvedDesiredAccess

    recordAudit(identity, service.ownerTeam, actual)
    return identity
~~~

Đây là **pseudocode học thuật**, không phải API có thể chạy trực tiếp. Thực tế cần transaction/outbox, idempotency, eventual consistency, issuer trust và khả năng retry.

### 22.1. Không tin source code/metadata tự khai

Nếu developer gửi `service=payment-admin` trong một JSON request, hệ thống không thể chỉ dựa vào chuỗi đó để cấp identity payment-admin. Cần xác minh **đường triển khai và runtime**, code/pipeline provenance và owner/policy khi phù hợp.

## 23. Pseudocode: xác thực và ủy quyền yêu cầu máy–máy

~~~text
function authorizeMachineRequest(request, trustedNow):
    proof = validateWorkloadAuthentication(
        request.credential,
        expectedIssuer,
        expectedAudience,
        trustedNow
    )

    if not proof.valid:
        return DENY

    identity = resolveRegisteredWorkloadIdentity(proof.subject)
    if identity missing or identity.status != ACTIVE:
        return DENY

    if not trustBindingMatchesRuntimeAndEnvironment(proof, request):
        return DENY

    policy = loadCurrentTargetAuthorizationPolicy()
    if not policy.allows(
        identity,
        request.action,
        request.resource,
        request.tenant,
        trustedNow
    ):
        return DENY

    if identity.revoked or identity.serviceRetired:
        return DENY

    return PERMIT
~~~

Trong hệ thống thực tế còn cần kiểm **token signature/certificate chain/PoP, issuer, audience, nbf/exp, replay, transport security, scopes và object-level authorization** tùy giao thức. Nếu token tự chứa có role cũ nhưng không re-evaluate quyền, nó có thể còn dùng được sau khi revoke; cần thiết kế **revocation latency** và PEP enforcement.

## 24. Deprovisioning và thu hồi quyền machine identity

### 24.1. Không chỉ xóa runtime object

Một workload decommission có thể phải gỡ quyền ở:
- Identity/issuer registration.
- Kubernetes ServiceAccount, RoleBinding/ClusterRoleBinding liên quan.
- Cloud IAM/service principal role assignments.
- OAuth client registrations và app credentials.
- Secrets manager/vault policies.
- Database technical users/GRANTs.
- API gateway application permissions.
- CI/CD secrets và service connections.
- PKI certificates, device bindings.
- Scheduled jobs có thể phát hành credential lại.

### 24.2. Readback actual vs desired

~~~mermaid
flowchart TD
    RET["Service retired or access reduction approved"] --> INV["Inventory principal + all grant paths"]
    INV --> DES["Compute desired access = removed/scoped"]
    DES --> EXEC["Revoke at authoritative source"]
    EXEC --> PROP["Wait for target propagation when needed"]
    PROP --> READ["Readback roles, keys, tokens, sessions"]
    READ --> TEST{"Effective privileged action denied?"}
    TEST -->|Có| DONE["VERIFIED_CLOSED + audit"]
    TEST -->|Không| FIX["REMEDIATION_REQUIRED + owner/SLA"]
    FIX --> EXEC
~~~

Một record `SCIM PATCH 200` hoặc `Cloud role removed` chưa bảo đảm:
- Static key không còn dùng được.
- Access token cũ không còn hiệu lực.
- Session DB đang mở bị ngắt.
- Dynamic group không tái cấp role.
- Resource policy không có đường trực tiếp khác.

**Không được đánh dấu VERIFIED_CLOSED nếu còn access path phải chặn theo scope quyết định**.

### 24.3. Xóa quyền không nên ảnh hưởng workload khác

Nếu nhiều services dùng chung principal hoặc credential, thu hồi có thể làm hệ thống khác lỗi. Trước khi revoke:
- Phân tích dependency và owner.
- Thiết kế tách identity/credentials nếu cần.
- Lập rollout/rollback an toàn.
- Không giữ admin key chung vô hạn chỉ vì sợ downtime.
- Kiểm thử positive (service hợp lệ vẫn chạy) và negative (dịch vụ đã retire không còn quyền).

### 24.4. Leaver có thể vẫn cần giữ workload nhưng phải gỡ đường truy cập cá nhân

Không xóa `billing-etl` khi người từng quản lý nó nghỉ, nếu job vẫn cần. Cần:
- Bàn giao owner/team.
- Gỡ quyền người cũ ở CI/CD, vault, cloud và app.
- Rotate credential có khả năng bị biết.
- Rà soát service identity permissions.
- Gắn người duyệt mới cho yêu cầu tương lai.
- Reconcile sau thay đổi.

## 25. Incident response khi credential workload bị lộ

Giả sử một short-lived token hoặc static key của `order-service` bị lộ trên log.

### 25.1. Phân loại ban đầu

1. Identity/workload nào bị ảnh hưởng? Owner là ai?
2. Credential thuộc loại nào, audience/scope/expiry ra sao?
3. Có quyền nào có thể tăng đặc quyền hoặc truy cập dữ liệu nhạy cảm?
4. Cred có thể dùng từ môi trường ngoài runtime hợp lệ không?
5. Có bằng chứng token replay, unauthorized access hoặc lateral movement không?
6. Có nhiều replicas/pipelines dùng chung credential không?
7. Issuer/attestation trust có bị xâm nhập không?

### 25.2. Containment và phục hồi

- Revoke/disable credential hoặc role liên quan theo khả năng.
- Rotate key/secret/certificate và cập nhật workload an toàn.
- Chặn nguồn truy cập trái phép bằng target authorization và network controls phù hợp.
- Kiểm tra sessions/tokens đã phát, cloud roles và impersonation paths.
- Không xóa log cần phục vụ điều tra.
- Tái triển khai image/runner sạch nếu runtime bị chiếm.
- Kiểm tra trust policy, issuer keys, CI/CD và secret distribution.
- Readback actual access; mở remediation nếu revoke không tức thời.
- Ghi postmortem/owner/lessons và cập nhật recertification.

### 25.3. Không phải lúc nào rotation cũng đủ

Nếu attacker vẫn có quyền gọi token issuer như workload hợp lệ, họ có thể tiếp tục lấy token mới sau rotation. Phải **sửa nguồn compromise và trust binding**, không chỉ đổi một chuỗi secret.

## 26. Ma trận kiểm thử và chỉ số quản trị

### 26.1. Các test nền tảng

| Test | Tình huống | Kết quả mong đợi |
| --- | --- | --- |
| **T1** | Workload hợp lệ, token đúng issuer/audience. | AuthN thành công; AuthZ vẫn xét action/resource. |
| **T2** | Token được ký bởi issuer không được tin. | Deny. |
| **T3** | Audience không dành cho API đích. | Deny. |
| **T4** | Token/certificate hết hạn. | Deny theo kiểm soát validation. |
| **T5** | Chỉ có service name trong header, không có proof. | Không coi là authenticated identity. |
| **T6** | Pod dùng ServiceAccount sai. | Không nhận trust/permission của service khác. |
| **T7** | Dev workload gọi API production. | Deny nếu policy không cho. |
| **T8** | Workload được quyền queue A gọi queue B. | Deny ngoài scope. |
| **T9** | Tenant-vn service truy cập tenant khác. | Deny nếu không có grant hợp lệ. |
| **T10** | OAuth token client credentials, không có user. | Audit app-only đúng, không giả user. |
| **T11** | Backend on-behalf-of user thiếu user permission. | Deny theo delegated policy. |
| **T12** | Service account có permission tự gán admin. | Block/review privilege escalation path. |
| **T13** | Owner Mover, role quản trị cũ đã gỡ. | Người cũ không còn quản lý workload. |
| **T14** | Owner Leaver nhưng job còn hoạt động. | Human access revoked; workload có owner mới, tiếp tục quyền tối thiểu. |
| **T15** | Service retired, static key vẫn active. | Fail closure; remediation. |
| **T16** | Role removed nhưng JWT cũ vẫn cho phép. | Residual access được phát hiện và xử lý. |
| **T17** | Certificate rotation trước expiry. | Service không gián đoạn; key cũ bị vô hiệu hóa đúng hạn. |
| **T18** | Dynamic group tự thêm identity đã gỡ. | Regrant được phát hiện, sửa source policy. |
| **T19** | Attestation selectors bị giả mạo. | Issuer không cấp identity sai. |
| **T20** | CI/CD pipeline tự approve và deploy prod. | SoD policy chặn nếu cần reviewer độc lập. |
| **T21** | Secret manager bị lỗi trong rotation. | Có rollback/continuity mà không giữ key cũ vô hạn. |
| **T22** | Unowned NHI phát hiện qua reconciliation. | Gắn remediation/owner; không xóa máy móc. |

### 26.2. Metrics hữu ích

| KPI | Cách hiểu | Cạm bẫy |
| --- | --- | --- |
| **NHI inventory coverage** | Tỷ lệ principals/credentials được map tới inventory. | Chỉ đếm VMs, bỏ API clients/pipelines. |
| **Owner coverage** | Tỷ lệ machine identities có owner team và business purpose. | Tên employee đã nghỉ không phải owner hợp lệ. |
| **Short-lived credential adoption** | Tỷ lệ workloads dùng federation/ephemeral credentials. | Token ngắn hạn nhưng trust quá rộng vẫn rủi ro. |
| **Credentials past rotation/expiry** | Key/cert không tuân thủ kỳ hạn. | Không đo rủi ro quyền nằm trong key. |
| **Privileged NHI count** | Số workload principals có quyền nhạy cảm. | Bỏ qua direct/resource grants. |
| **Orphaned identities** | Identity không còn service/owner/căn cứ hợp lệ. | Không phân biệt DR workload ít chạy với orphan thực. |
| **Grant removal latency** | Từ retirement/permission change tới target access bị chặn. | Lấy thời điểm ticket đóng. |
| **Regrant recurrence** | Quyền đã revoke tự xuất hiện lại. | Không xét source mapping/dynamic groups. |
| **Owner-leaver transfer latency** | Thời gian đổi owner/revoke human admins sau HR Leaver. | Không cần xóa workload chạy hợp lệ. |
| **NHI access review completeness** | Quyền được owner/risk reviewer đánh giá. | Approved review ≠ actual access đúng. |
| **Effective-access verification rate** | Các quyền thu hồi đã readback/test. | HTTP 200 chưa đủ. |
| **Credential compromise MTTR** | Thời gian chặn misuse và phục hồi trust. | Chỉ tính rotation mà bỏ runtime compromise. |

Đặt ngưỡng theo policy, data sensitivity, workload criticality và khả năng hệ thống; không có một tỷ lệ hoặc thời hạn đúng cho mọi tổ chức.

## 27. Tình huống xuyên suốt: triển khai service qua cloud federation

**Bối cảnh:** Công ty có `order-service` chạy Kubernetes production, gọi một API queue của cloud. Đội Commerce quản lý ứng dụng, Security quản lý policy và platform team vận hành cluster.

### 27.1. Thiết kế cũ

Ứng dụng dùng `CLOUD_ADMIN_KEY` lưu trong environment variable. Key có quyền đọc/ghi nhiều tài nguyên ở các project. Người từng tạo key đã chuyển sang đội khác.

Rủi ro:
- Không có owner rõ cho key.
- Có thể bị trích xuất từ runtime/log hoặc secret.
- Không giới hạn audience và action.
- Người cũ có thể còn quyền xem/rotate key.
- Khi Pod chết, key vẫn hợp lệ.
- Không biết có workload khác dùng chung key.

### 27.2. Thiết kế mới

1. Đăng ký logical identity `order-service-prod` trong service catalog với owner team.
2. Dùng ServiceAccount dành riêng cho workload trên Kubernetes.
3. Thiết lập trust federation chỉ chấp nhận token issuer/subject/audience đúng.
4. Map vào cloud principal chỉ được `orders:publish` trên queue `commerce-order-events-vn`.
5. Cấp short-lived credentials; không hard-code static cloud admin key.
6. Áp tenant/environment conditions ở resource server.
7. Ghi audit actor workload, runtime, resource, action và decision.
8. Kiểm thử đúng queue được Permit, queue khác bị Deny.
9. Rotate/revoke admin key cũ sau khi xác minh không workload nào còn phụ thuộc.
10. Rà soát permissions và owner theo kỳ.

### 27.3. Khi service chuyển owner

Commerce team đổi người chịu trách nhiệm. Không cần cấp identity mới nếu **logical service/trust boundary không đổi** và policy cho phép. Cần cập nhật owner, remove human grants cũ, rotate credentials có rủi ro và kiểm tra approvals/SoD.

### 27.4. Khi service ngừng hoạt động

Owner xác nhận không còn production deployment/consumer. IAM/Platform:
- Xóa/disable workload registration và federation trust nếu phù hợp.
- Gỡ cloud role/resource grants.
- Revoke client registrations/old keys/certificates.
- Kiểm tra target còn nhận token cũ hay không.
- Xóa scheduled jobs/CI tasks có thể phát hành credentials lại.
- Giữ audit/evidence theo policy.
- Đánh dấu `VERIFIED_CLOSED` chỉ khi không còn access path ngoài desired state.

**Bài học:** Machine identity mang lại attribution và trust, nhưng giá trị bảo mật nằm ở **gắn đúng identity với workload thật, cấp quyền tối thiểu và có lifecycle kiểm chứng**.

## 28. Tình huống: service account bị chia sẻ giữa nhiều jobs

**Bối cảnh:** Ba jobs `export-customer`, `billing-etl` và `support-report` cùng dùng một database user `svc-data-admin`.

### 28.1. Vấn đề

Một job chỉ cần SELECT bảng tổng hợp, job khác cần INSERT, job thứ ba export dữ liệu nhạy cảm. Vì chúng dùng chung DB user:
- Không phân biệt được job nào chạy một câu lệnh chỉ từ DB account.
- Secret bị lộ ở một job ảnh hưởng cả ba.
- Không thể thu hồi quyền export mà không ảnh hưởng các job khác.
- Khó xác định owner khi một job retired.
- Credential rotation và password leak blast radius lớn.

### 28.2. Phương án cải thiện

- Tạo principal/credential riêng theo job hoặc trust boundary hợp lý.
- Gán đúng table/schema/tenant permissions.
- Dùng managed/workload identity nếu database và môi trường hỗ trợ.
- Cập nhật workflows và test positive/negative.
- Chuyển từng job sang identity mới, revoke shared admin credential cuối cùng.
- Ghi owner/capability và review schedule.
- Kiểm chứng account cũ không còn effective admin access.

**Không nhất thiết phải có một account mới cho từng replica**, nhưng **những workloads khác chức năng, owner hoặc phạm vi bảo mật** thường không nên dùng chung một secret toàn quyền.

## 29. Những sai lầm phổ biến

| Sai lầm | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Coi API key là identity đầy đủ. | Không có owner, service mapping hoặc lifecycle. | Inventory NHI, trust, credential và grant riêng. |
| Một cloud admin key cho mọi workload. | Blast radius lớn, khó revoke. | Scoped workload identities và short-lived credentials. |
| Dùng human account để chạy production automation. | Gãy khi người nghỉ, thiếu accountability. | Workload principal riêng, human admin tách biệt. |
| Tên ServiceAccount được tin không cần attestation. | Caller tự nhận danh tính khác. | Issuer/subject/workload binding có xác minh. |
| Client ID bị xem là secret. | Dễ bỏ qua bảo vệ actual credential. | Phân biệt identifier và secret/proof. |
| Có certificate là được phép gọi mọi API. | AuthN bị nhầm AuthZ. | RBAC/ABAC at resource. |
| mTLS được coi là bảo đảm code an toàn. | Workload bị chiếm vẫn dùng cert hợp lệ. | Runtime hardening/attestation/monitoring. |
| Không kiểm audience/issuer của JWT. | Token cho API khác có thể bị lạm dụng. | Validate issuer/audience/expiry/signature. |
| Tin `tenantId` do client gửi. | Cross-tenant access. | Bind identity và resource-side tenant policy. |
| Dùng cùng workload identity cho dev và prod. | Lateral movement xuyên môi trường. | Trust/credential/permission boundary riêng. |
| Trao quyền K8s `cluster-admin` để đọc một ConfigMap. | Overprivilege. | Namespace RBAC cụ thể. |
| Không quản lý role hierarchy/direct grants. | Quyền tồn dư sau role revoke. | Effective-grant path inventory. |
| Chỉ xóa Pod khi service retired. | Account, key và role còn sống. | End-to-end deprovisioning. |
| Rotation nhưng static secret cũ vẫn active. | Credential leak vẫn dùng được. | Revoke old credential + readback. |
| Token hết hạn dài hơn assignment. | Quyền tồn dư. | Short TTL/revocation/runtime authorization. |
| Owner Leaver thì xóa luôn workload đang chạy. | Dịch vụ gián đoạn. | Handover owner và revoke human access. |
| Không chuyển approval authority khi owner đổi. | Bot có owner trên giấy nhưng không có người chịu trách nhiệm. | Service catalog ownership lifecycle. |
| NHI không cần SoD vì không phải người. | Pipeline tự code–approve–deploy. | Separation of roles và independent approval. |
| Tin SCIM quản lý mọi loại machine identity. | Bỏ sót cloud/K8s/PKI/API keys. | Provider-specific discovery/provisioning. |
| Chỉ đếm certificate sắp hết hạn. | Bỏ role quá rộng và orphaned principals. | Risk-based recertification. |
| Coi last-used lâu là chắc có thể xóa. | Làm hỏng recovery job. | Verify owner/dependency và DR readiness. |
| Ghi full token trong audit. | Rò rỉ credential qua log. | Redact, use token/credential reference. |
| Đóng deprovision ticket khi API trả 200. | Target vẫn có residual access. | Readback và effective-access verification. |

## 30. Checklist thực hành quản lý machine identity

### 30.1. Đăng ký và cấp quyền

- [ ] Mỗi machine identity có **logical ID, type, owner team và business purpose**.
- [ ] Phân biệt workload identity, account, principal và credential.
- [ ] Mapping account/target rõ, không suy identity từ email/service name tùy ý.
- [ ] Trust issuer/attestation và subject binding được kiểm chứng.
- [ ] Chia tách dev/staging/prod, tenant và security boundary phù hợp.
- [ ] Không dùng human username/password làm credential job thường xuyên.
- [ ] Ưu tiên short-lived credentials/federation khi phù hợp.
- [ ] Không commit secret/private key/token vào repository hoặc image.
- [ ] Có RBAC/ABAC scoped permission, hạn chế direct grants và escalation.
- [ ] Target kiểm issuer, audience, expiry, signature/PoP và object authorization.
- [ ] Có positive/negative tests và audit có actor/service/resource.

### 30.2. Trong vòng đời

- [ ] Có inventory cloud/K8s/DB/OAuth/PKI/CI/CD/API keys.
- [ ] Có rotation/renewal/expiry policy và rollover an toàn.
- [ ] Owner/team change trigger cập nhật authority và review grants.
- [ ] Human Mover/Leaver trigger revoke quyền quản trị workload của người cũ.
- [ ] Workload còn hoạt động không bị xóa chỉ vì owner nhân sự nghỉ.
- [ ] Service replatforming/rename/tenant move có trust revalidation.
- [ ] Machine identities có access recertification theo mức rủi ro.
- [ ] SoD và independent approvals áp dụng cho privileged bots/pipelines.
- [ ] Có monitoring token misuse, credential exposure và regrant drift.
- [ ] Khi runtime compromise, xử lý cả nguồn trust chứ không chỉ rotate key.

### 30.3. Khi ngừng dùng

- [ ] Owner xác nhận workload/service đã retired.
- [ ] Gỡ OAuth clients, service principals, cloud roles, K8s/DB grants.
- [ ] Thu hồi static secrets, certificates, keys và trust bindings.
- [ ] Kiểm tra sessions/tokens còn hiệu lực theo hệ thống.
- [ ] Ngăn CI/CD/job hoặc dynamic policy tái cấp quyền.
- [ ] Readback target grants và kiểm tra effective access.
- [ ] Không gỡ nhầm quyền của workload hợp lệ dùng chung resource.
- [ ] Audit lưu decision, executor, source, timestamp, target, result.
- [ ] Nếu còn quyền, có owner/remediation/SLA.
- [ ] Chỉ đánh dấu `VERIFIED_CLOSED` khi không còn access path phải thu hồi.

## 31. Bài tập tự kiểm tra

### 31.1. Bài A — Identity hay credential?

Một ứng dụng chỉ có `API_KEY_PROD` được copy giữa ba jobs, không ai biết người tạo và không có inventory. Key đó đã là một machine identity được quản trị đầy đủ chưa? Phân biệt **logical identity, account, credential, owner và authorization**.

### 31.2. Bài B — Kubernetes ServiceAccount

Pod `order-service` dùng ServiceAccount `default` có quyền `cluster-admin` và cloud account quyền `Owner`. Hãy mô tả những nguồn grant/đường leo thang cần kiểm tra, thiết kế ServiceAccount riêng và scope cloud role phù hợp.

### 31.3. Bài C — OAuth client credentials

Backend dùng `client_id` và `client_secret` để lấy access token gọi API. Vì sao không cần human SSO session cho từng request? Token cần kiểm những trường nào, và vì sao `client_id` không nên coi là secret?

### 31.4. Bài D — mTLS certificate

Một service có certificate hợp lệ do CA nội bộ phát hành, nhưng xin quyền `payments:refund` dù nhiệm vụ chỉ đọc đơn hàng. Resource server nên làm gì? Phân biệt mTLS AuthN và RBAC/ABAC AuthZ.

### 31.5. Bài E — Owner Mover

Engineer quản lý `billing-etl` chuyển từ Finance Data sang Security. Cần thu hồi những human grants nào, cập nhật owner ra sao, lúc nào cần rotate workload secret, và tại sao không xóa job đang chạy?

### 31.6. Bài F — Owner Leaver

Người tạo cloud service principal đã nghỉ. Principal vẫn phục vụ production. Tổ chức nên kiểm tra role assignments, secret exposure, CI/CD, token và owner như thế nào trước khi kết luận đã offboard người đó?

### 31.7. Bài G — SPIFFE trust domain

Một attacker chạy Pod trên cluster không đáng tin nhưng tự gắn label `app=order-service`. Vì sao không được phát `spiffe://company.example/ns/commerce/sa/order-service` chỉ dựa trên label? Gợi ý các bước node/workload attestation và issuer trust.

### 31.8. Bài H — Static key và rollover

Một DB job dùng mật khẩu lưu trong script từ hai năm trước. Hãy xây kế hoạch tách identity, giảm table permission, tạo key/credential mới, chuyển job và thu hồi credential cũ không làm ngắt dữ liệu.

### 31.9. Bài I — API hỗ trợ người dùng

`portal-api` dùng machine admin credential để đọc document thay Lan. Làm sao tránh confused deputy và bảo đảm cả **workload và user** có đủ permission ở đúng tenant/document?

### 31.10. Bài J — Review và retirement

Service catalog ghi `export-customer` đã retired, nhưng OAuth client còn active và `report:export-all` tại SaaS chưa gỡ. Mô tả desired-state reconciliation, revocation và negative test an toàn để đóng `VERIFIED_CLOSED`.

### 31.11. Bài K — Certificate ngắn hạn và token replay

Một workload có JWT TTL 5 phút nhưng attacker đã chiếm runner và tự xin token mới. Vì sao giảm TTL không đủ? Phân tích attestation, runner trust, policy binding và response khi compromise.

### 31.12. Bài L — Chỉ số NHI

Tổ chức báo “100% ServiceAccounts có owner”, nhưng 200 static cloud keys và 80 OAuth clients không được liệt kê. Tỷ lệ inventory coverage thực chất ra sao? Hãy đề xuất cách đối soát đa nguồn và phân biệt logical identities với credentials để không đếm sai.

**Điểm cần ghi nhớ:** **Machine identity** là danh tính đáng tin của **workload, service, thiết bị hoặc tác vụ tự động**, không phải chỉ một API key/certificate. Cần tách **identity, account, principal, credential, authentication, authorization và owner**; kiểm soát trust/attestation, issuer/audience, mTLS/OAuth federation, RBAC/ABAC và permissions tại target. Trong IAM **Joiner–Mover–Leaver**, sự kiện của **người quản trị** phải kéo theo đánh giá quyền của người đó đối với workload, còn **workload identity** có lifecycle riêng từ đăng ký tới retire. Chỉ khi **grant, credential, session/token và access path** được cấp đúng, thay đổi có quản trị và **thu hồi có readback, reconciliation, audit** thì mới tránh được **machine identity mồ côi và đặc quyền tồn dư**.

