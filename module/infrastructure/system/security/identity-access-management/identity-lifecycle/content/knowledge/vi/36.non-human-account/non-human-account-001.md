# Non-human account là gì? Quản lý danh tính máy, tài khoản dịch vụ và quyền truy cập của workload trong IAM

**Non-human account (NHA, tài khoản phi con người)** là tài khoản được một **ứng dụng, dịch vụ, tiến trình, máy chủ, job, bot hoặc workload** sử dụng để xác thực và truy cập hệ thống **thay vì một cá nhân đăng nhập tương tác để làm việc trực tiếp**. Ví dụ: ứng dụng đồng bộ dữ liệu gọi API báo cáo, pipeline CI/CD triển khai phần mềm, một tác vụ sao lưu kết nối cơ sở dữ liệu, hoặc workload trên cloud sử dụng managed identity để đọc secret.

Trong thực hành, người ta còn dùng các thuật ngữ **non-human identity (NHI), machine identity, service account, workload identity, service principal, application identity, API client**. Các khái niệm **có liên quan nhưng không hoàn toàn đồng nghĩa**: *identity* biểu diễn chủ thể cần được nhận diện, *account* là thực thể tại một hệ thống, *credential* là phương tiện chứng minh danh tính, còn *grant/role* cho biết chủ thể được phép làm gì.

Một NHA không có “nhân viên đứng sau” theo nghĩa đăng nhập thông thường, nhưng **phải có người hoặc nhóm chịu trách nhiệm** về mục đích, quyền, credential, vận hành và vòng đời của nó. Không có chủ sở hữu hợp lệ không có nghĩa tài khoản không có rủi ro: những NHA mồ côi có thể giữ **quyền production, token, secret và đường truy cập tồn dư** rất lâu.

Bài học thuộc chương **Non-human account** trong mô-đun **SECURITY_IDENTITY_ACCESS_MANAGEMENT_IDENTITY_LIFECYCLE**, nghiên cứu quản lý vòng đời danh tính theo **Joiner–Mover–Leaver (JML)**, từ xác minh, tạo account và cấp quyền đến rà soát, thu hồi khi vai trò thay đổi. Nội dung kết nối **IdP, SSO, SCIM, RBAC/ABAC, tài khoản dịch vụ, kiểm toán và giảm quyền tồn dư**. Trọng tâm của bài là **khái niệm và kiến trúc nền tảng** để nhận biết và quản trị NHA đúng cách.

**Thông điệp quan trọng:** **Tài khoản không do người đăng nhập trực tiếp vẫn là một chủ thể bảo mật đầy đủ**. Nó cần **định danh riêng, nguồn tin cậy để xác thực, quyền tối thiểu, chủ sở hữu, giới hạn phạm vi và vòng đời được chứng minh bằng readback** — không thể bỏ qua quản trị chỉ vì nó phục vụ automation.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Định nghĩa **non-human account** và phân biệt **non-human identity, account, service principal, workload, credential, token, role, secret và owner**.
2. Nhận diện các loại NHA trong **API integration, CI/CD, Kubernetes, cloud, database, batch job, monitoring, backup và automation**.
3. Giải thích vì sao **human SSO/MFA flow** không phải mô hình áp nguyên xi cho mọi workload; biết các cách xác thực phù hợp với máy.
4. Hiểu **OAuth 2.0 Client Credentials, managed identity, workload identity federation, certificate/mTLS và credential ngắn hạn** ở mức kiến trúc.
5. Thiết kế phân quyền **least privilege** theo action, resource, tenant, audience, environment, thời gian và trạng thái workload.
6. Xây dựng inventory và metadata tối thiểu có **identity ID, owner, mục đích, dependency, quyền, credential reference, expiry và audit**.
7. Phân biệt **vòng đời workload/NHA** với **Joiner–Mover–Leaver của người sở hữu**, tránh xóa bừa hoặc giữ tài khoản mồ côi.
8. Đánh giá rủi ro credential leak, privilege escalation, token còn hạn, secret không rotate, shadow integration và quyền tồn dư.
9. Mô tả provisioning, rotation, suspension, deprovision, reconciliation và cách chứng minh quyền hiệu dụng đã thay đổi.
10. Áp dụng checklist, tình huống và ví dụ mã giả để vận hành NHA có kiểm soát.

## 2. Vì sao hệ thống cần tài khoản phi con người?

Nhiều hệ thống cần trao đổi dữ liệu mà **không có một người luôn ngồi trước màn hình**:

- Job tổng hợp doanh thu vào cuối ngày.
- Backend gọi service khác để xử lý thanh toán.
- CI/CD pipeline kéo image và triển khai môi trường staging.
- Agent giám sát đọc chỉ số hệ thống.
- Database backup task ghi dữ liệu vào kho backup.
- Workload đọc cấu hình bí mật từ secret manager.
- Bot xử lý ticket hoặc gửi thông báo.
- Connector đồng bộ account/group giữa IdP và ứng dụng.
- Dịch vụ phục hồi khẩn cấp thực hiện thao tác theo runbook đã duyệt.

Nếu dùng **tài khoản/mật khẩu cá nhân** của một nhân viên để vận hành các tác vụ trên, doanh nghiệp gặp nhiều vấn đề:

1. Nhân viên **Mover/Leaver** làm job hỏng hoặc khiến credential cá nhân tiếp tục được dùng không kiểm soát.
2. Quyền của người có thể **quá rộng** so với tác vụ.
3. Audit khó phân biệt **tác vụ tự động** với hành động cá nhân.
4. Password/MFA phục vụ người dùng tương tác không phù hợp với job chạy không có người.
5. Credential thường bị sao chép vào mã nguồn, biến môi trường hoặc tài liệu triển khai.
6. Không biết ai có trách nhiệm rotation khi người tạo job nghỉ việc.

**NHA giải quyết bài toán định danh độc lập cho workload**, nhưng chỉ phát huy giá trị nếu tài khoản được gắn **purpose, owner, scope, credential lifecycle và audit**.

## 3. Phân biệt sáu khái niệm nền tảng

| Khái niệm | Bản chất | Ví dụ | Sai lầm thường gặp |
|---|---|---|---|
| **Non-human identity (NHI)** | Danh tính logic của máy/workload | `workload:billing-reconcile` | Đồng nhất identity với một mật khẩu |
| **Non-human account** | Account hoặc principal tại một target/IdP | `svc-billing-prod` | Cho rằng một NHI chỉ có đúng một account |
| **Credential** | Phương tiện xác thực | Certificate, private key, secret, assertion | Coi credential chính là quyền |
| **Access token/session** | Bằng chứng truy cập được phát theo cơ chế cụ thể | OAuth access token có `aud`/`exp` | Coi xóa secret thì token lập tức mất hiệu lực |
| **Role/entitlement/scope** | Quyền được giao cho chủ thể | `invoices.read@tenant-A` | Coi xác thực thành công là được làm mọi thao tác |
| **Owner/custodian** | Người/nhóm chịu trách nhiệm quản trị NHA | Payments Platform Team | Cho rằng account máy không cần owner |

### 3.1. Một workload có thể có nhiều account

~~~text
Workload identity logic: invoice-reconciler
  ├─ Cloud service principal: sp-invoice-prod
  ├─ Database user: invoice-reader-prod
  ├─ OAuth client registration: client-invoice-prod
  ├─ Kubernetes ServiceAccount: finance/invoice-reconciler
  └─ Runtime credential/token:
       ├─ short-lived cloud token
       └─ projected service-account token
~~~

Các thực thể này **có thể liên kết**, nhưng không mặc nhiên là một account duy nhất. Việc kiểm kê phải xác định **mapping giữa workload logic, account target, credential và quyền hiệu dụng**.

### 3.2. Một account có thể được nhiều phiên dùng

Một service principal có thể được nhiều replica của cùng service sử dụng. Điều đó không nhất thiết sai nếu cùng workload boundary được thiết kế, nhưng cần cân nhắc **blast radius, separation giữa environment/tenant, khả năng quy trách nhiệm từng deployment** và rủi ro khi một replica bị chiếm quyền.

## 4. Non-human account khác tài khoản người dùng như thế nào?

| Khía cạnh | Human account | Non-human account |
|---|---|---|
| **Chủ thể** | Người được xác minh và gắn engagement | Workload, service, automation hoặc thiết bị |
| **Đăng nhập** | Thường tương tác: password/passkey/MFA/SSO | Programmatic authentication, managed identity, certificate, assertion |
| **Nguồn vòng đời** | HR/VMS, Joiner–Mover–Leaver | Service catalog, workload/deployment registry, asset lifecycle |
| **Owner** | Người dùng, manager, sponsor | Technical/service owner và nhóm vận hành |
| **Quyền** | Theo nhiệm vụ/role/ngữ cảnh của người | Theo chức năng workload, API/resource/environment |
| **Phiên** | Browser/app session, access/refresh tokens | API token, service session, workload credential |
| **Review** | Manager/app/data owner | Service owner + app/resource/security owner |
| **Thu hồi** | Gắn với engagement/role/user account | Gắn với service decommission, credential lifecycle, owner change |
| **Sự cố thường gặp** | Phishing, session theft, privilege creep | Secret leakage, overbroad scope, shadow automation, orphan principal |
| **Dấu vết audit** | Actor người và tài nguyên | Workload ID, job/deployment ID, nguồn kích hoạt và target |

**NHA không phải “con người nhưng được miễn MFA”.** Một hệ thống cần xác thực machine-to-machine theo cơ chế phù hợp; không nên xây bot bằng cách lưu mật khẩu người, OTP hoặc session cookie của nhân viên vào script.

## 5. Các loại Non-human account phổ biến

| Loại | Ví dụ | Nguồn nhận diện và yêu cầu quản trị |
|---|---|---|
| **Service account ứng dụng** | `svc-payment-api` | Service catalog, API role, environment |
| **OAuth client/application registration** | Client gọi Reporting API | Client ID, owner, allowed grant, audience/scope |
| **Cloud managed identity** | VM/function truy cập storage | Cloud workload binding, IAM policy |
| **Service principal** | Automation triển khai cloud resources | Cloud IAM, role assignment, credential |
| **Kubernetes ServiceAccount** | Pod `inventory-reader` | Namespace, pod binding, RBAC, projected token |
| **CI/CD identity** | Pipeline release staging | Repo/workflow identity, environment, deployment policy |
| **Database service user** | `backup_reader` | Schema/DB role, credential, audit |
| **Integration/bot account** | ChatOps bot mở ticket | Integration owner, API permissions, webhook trust |
| **Monitoring agent** | Agent đọc metric, config | Host/agent identity, telemetry scope |
| **Backup/DR identity** | Job ghi backup và thử restore | Recovery owner, storage permissions, credential |
| **Device/IoT identity** | Thiết bị gửi telemetry | Device registry, certificate, attestation khi áp dụng |
| **Robotic Process Automation (RPA)** | Bot điều khiển giao diện legacy | Bot owner, phạm vi tài khoản, session controls |
| **Emergency recovery workload** | Job khôi phục IdP trong sự cố | Break-glass policy, đặc quyền có điều kiện, hậu kiểm |

### 5.1. Không phải mọi “bot” đều là một identity độc lập

Nếu bot dùng một cookie đăng nhập của nhân viên, hệ thống đích chỉ thấy **human account**. Về mặt chức năng đó là automation nhưng chưa đạt yêu cầu **identity riêng**. Cần phân biệt:

- **Loại tác vụ:** Do phần mềm tự động thực hiện.
- **Loại account:** Hệ thống đang dùng principal riêng hay credential người?
- **Khả năng audit:** Có biết job/deployment, người phê duyệt, target và scope không?

### 5.2. Shared human admin khác NHA đúng nghĩa

Một account `administrator` dùng chung giữa nhiều người là **shared privileged account**, không nên tự xếp nó thành NHA lành mạnh chỉ vì không gắn tên cá nhân. Nó vẫn cần **actor attribution, PAM, kiểm soát credential và hậu kiểm**. NHA đúng nghĩa nên đại diện cho **workload/service**, không dùng như cách che tên người thao tác.

## 6. Kiến trúc NHA trong IAM

~~~mermaid
flowchart TD
    C["Service catalog / CMDB<br/>Workload ID, owner, purpose"] --> I["IAM / IGA<br/>Inventory + governance + lifecycle"]
    HR["HR / VMS<br/>Owner Joiner–Mover–Leaver"] --> I
    I --> P["Policy / RBAC / ABAC<br/>Least privilege + SoD"]
    I --> PROV["Provisioning<br/>IdP, cloud IAM, API, SCIM nếu hỗ trợ"]
    PROV --> TARGET["Account / principal ở target"]
    R["Runtime: Pod / VM / CI job<br/>workload runtime identity"] --> AUTH["Trusted authentication<br/>managed identity, cert, OIDC, etc."]
    AUTH --> AS["Token service / IdP<br/>Issuer + audience + expiry"]
    AS --> R
    R --> PEP["API / Resource Server / PEP"]
    P --> PDP["PDP / Policy decision"]
    PDP --> PEP
    TARGET --> PEP
    PEP --> RESOURCE["Resource / Secret / Data"]
    AUTH --> AUD["Audit + credential monitoring"]
    PEP --> AUD
    I --> AUD
    AUD --> VERIFY["Reconciliation / Readback<br/>Effective access + owner status"]
    VERIFY --> I
~~~

Sơ đồ thể hiện trách nhiệm logic. Trong kiến trúc thực tế, một cloud provider có thể tích hợp identity issuance và IAM role; PDP có thể nằm ngay trong API; workload không nhất thiết có account lưu lâu dài. **Điều quan trọng là xác định nguồn danh tính đáng tin, cách cấp credential, chính sách quyền và nơi thực thi.**

### 6.1. Source of truth không giống runtime

- **Service catalog/CMDB:** Workload nào tồn tại, chủ sở hữu, môi trường và mục đích.
- **Identity/authorization registry:** Principal/role nào đã đăng ký và được phép.
- **Runtime/deployment registry:** Instance/job nào đang chạy thực tế.
- **Credential/token service:** Credential hoặc token nào được cấp, còn hiệu lực.
- **Target/Resource Server:** Action nào hiện thực sự được phép.

Các nguồn có thể lệch nhau trong quá trình cập nhật. Vì vậy **một bản ghi inventory ACTIVE không tự chứng minh workload còn chạy hoặc còn cần quyền**.

## 7. Nhận diện “đúng workload” là một bài toán bảo mật

Với con người, hệ thống có thể xác minh một nhân viên trong quy trình identity proofing. Với NHA, câu hỏi tương ứng là:

> “Request này thật sự đến từ **workload/deployment được phép**, hay từ một script khác đang dùng credential bị sao chép?”

Các yếu tố đáng xem:

1. **Workload ID:** Tên định danh ổn định, không chỉ IP hoặc hostname dễ thay đổi.
2. **Runtime binding:** Pod, VM, repository workflow, service instance hay platform identity nào được tin.
3. **Environment:** Production/staging/dev có tách danh tính và quyền không?
4. **Issuer:** Bên phát chứng thực/token có được tin cậy không?
5. **Subject binding:** Token/assertion gắn với đúng workload/repository/namespace/deployment không?
6. **Audience:** Credential/token chỉ có ý nghĩa với dịch vụ đích dự kiến?
7. **TTL và replay:** Chứng thực có thời hạn và cơ chế hạn chế dùng lại không?
8. **Key ownership:** Private key/secret có bị dùng ngoài runtime đã duyệt không?
9. **Account mapping:** Principal tại target có thuộc đúng workload logic không?
10. **Audit:** Có thể truy vết một request đến đúng job/release/service owner không?

**Địa chỉ IP không nên là bằng chứng duy nhất của machine identity** nếu môi trường có NAT, autoscaling, host tái sử dụng hoặc hạ tầng mạng có thể đổi.

## 8. Các cách xác thực workload: tổng quan

| Phương pháp | Ý tưởng | Rủi ro/giới hạn cần kiểm |
|---|---|---|
| **Static client secret/password** | Workload trình secret đã đăng ký | Dễ sao chép, lộ và tồn tại lâu |
| **Certificate / mutual TLS** | Chứng minh kiểm soát private key, xác thực hai đầu kết nối | Quản lý key, certificate issuance/rotation, trust |
| **OAuth 2.0 Client Credentials** | Client máy xác thực với Authorization Server để lấy access token | Scope/audience, client auth, TTL và key protection |
| **Cloud managed identity** | Nền tảng cấp identity/token cho workload được gắn | Binding cloud role/resource và bảo vệ metadata/runtime |
| **Workload identity federation** | Tin assertion từ platform issuer để đổi lấy token đích | Kiểm issuer, subject, audience, repository/namespace |
| **Kubernetes ServiceAccount token** | Pod có token định danh theo service account/platform | RBAC, audience, thời hạn, pod/namespace binding |
| **Short-lived issued certificate** | CA cấp chứng thư ngắn hạn dựa trên workload identity | CA trust, key lifecycle, revocation/freshness |
| **API key** | Key định danh integration được API chấp nhận | Phân quyền tối thiểu, bảo vệ key, rotation, audit |

**Không có một phương pháp tốt nhất cho mọi hệ thống**. Khi lựa chọn, cần xét khả năng nền tảng, threat model, secret distribution, TTL, khả năng rotate/revoke và mức độ nhạy cảm của target.

### 8.1. “Không có password” không đồng nghĩa “không có credential”

Một managed identity không cần developer lưu password tĩnh, nhưng runtime vẫn dựa trên **thông tin chứng thực và trust của nền tảng** để được cấp token. Credential ngắn hạn vẫn cần bảo vệ khỏi rò rỉ và sử dụng sai trong thời gian còn hợp lệ.

## 9. OAuth 2.0 Client Credentials cho NHA

**OAuth 2.0 Client Credentials grant** là mô hình trong đó **một client xác thực danh tính của chính nó** tại Authorization Server và yêu cầu access token cho những phạm vi được phép. Nó phù hợp với một số kịch bản machine-to-machine, đặc biệt khi client có thể **bảo vệ phương tiện xác thực**.

Một luồng tổng quát:

~~~mermaid
sequenceDiagram
    autonumber
    participant W as Billing Worker
    participant AS as Authorization Server
    participant API as Reporting API / Resource Server
    participant AUD as Audit / Policy

    W->>AS: Client authentication + token request
    AS->>AS: Verify client, policy, allowed scopes/audience
    AS-->>W: Access token (short-lived)
    W->>API: Request + access token
    API->>API: Verify signature/issuer/audience/expiry/scopes
    API->>API: Enforce resource/tenant authorization
    API-->>W: PERMIT result hoặc DENY
    AS-->>AUD: Token issuance metadata
    API-->>AUD: Client ID, action, resource, decision
~~~

**Client Credentials không đại diện cho một nhân viên cuối**. Token phát từ grant này thông thường biểu diễn quyền của **client/workload** theo chính sách; không tự được xem là delegated user permission.

### 9.1. Ví dụ request ở mức khái niệm

~~~text
POST /oauth2/token
Content-Type: application/x-www-form-urlencoded

grant_type=client_credentials
&scope=reports.read

Client authentication:
  Theo phương thức được Authorization Server hỗ trợ,
  ví dụ private_key_jwt, mutual TLS hoặc secret bảo vệ tốt.
~~~

Không đặt client secret hoặc private key vào tài liệu học, URL, log hay mã nguồn. Thông số request cụ thể phụ thuộc implementation; nhiều hệ thống còn cấu hình **audience/resource** hoặc sử dụng phương thức ràng buộc token khác.

### 9.2. Resource Server phải kiểm gì?

- Token **được phát bởi issuer đáng tin** và có cơ chế xác minh hợp lệ.
- Token dành cho **audience/resource server** này.
- Token còn hiệu lực thời gian và chưa bị từ chối theo cơ chế hỗ trợ.
- **Client subject** là NHA được phép gọi API.
- Scope/role/permission đáp ứng **action**.
- **Tenant, project, resource classification và context** phù hợp.
- Không thiếu thông tin bắt buộc khi PDP/PEP cần đánh giá.
- Grant/workload status có được kiểm theo độ mới mà chính sách yêu cầu hay không.

**Token hợp lệ không có nghĩa mọi hành động trên mọi tài nguyên đều được phép.** Access token có `reports.read` không tự cấp `reports.export` hay quyền đọc mọi tenant.

### 9.3. Rotation của client secret và token còn hạn

Khi secret bị thay, một access token đã phát **có thể tiếp tục hợp lệ đến hết hạn** nếu Resource Server chỉ kiểm token tự chứa và không có cơ chế thu hồi/kiểm trạng thái bổ sung. Phải xem cả **client credential, refresh token nếu có, token TTL, cache và quyền hiệu dụng**.

## 10. Managed identity: để nền tảng cấp identity cho workload

**Managed identity** là cách nền tảng cloud hoặc runtime quản lý một phần vòng đời credential và cung cấp identity/token cho workload được gắn. Ví dụ một compute workload cần đọc một secret:

~~~text
Workload chạy trên compute được tin
  -> Runtime/nền tảng xác định workload identity
  -> Token service cấp token phù hợp target
  -> Workload gọi secret manager
  -> Secret manager kiểm token + IAM policy
  -> Chỉ trả secret mà identity được phép đọc
~~~

Điểm mạnh thường gặp là **giảm nhu cầu lưu một client secret tĩnh** trong repository hay environment. Tuy nhiên:

- Có thể vẫn bị lạm dụng nếu **runtime bị chiếm**.
- Role cloud có thể được gán quá rộng.
- Cần tách identity/permission theo **environment và workload**.
- Audit cần biết principal và resource; không chỉ tên VM.
- Khi workload bị decommission, **role assignment và access còn lại** phải được gỡ/đối soát.

**Managed identity không phải cơ chế auto least-privilege.** Quyền gán cho identity vẫn cần IAM governance và review.

## 11. Workload Identity Federation và OIDC

**Workload identity federation** cho phép một nền tảng tin **chứng thực ngắn hạn từ issuer của nền tảng workload**, thay vì bắt pipeline hoặc container giữ một long-lived secret của target.

Ví dụ CI/CD:

~~~text
CI runner/workflow
  -> Nền tảng CI phát OIDC assertion gắn với job/repo
  -> Cloud Security Token Service xác minh issuer,
     audience và subject/claim binding đã cấu hình
  -> Trả credential ngắn hạn cho một cloud role
  -> Pipeline deploy đúng service/environment được phép
~~~

### 11.1. Các ràng buộc quan trọng

- **Issuer:** Chỉ tin OIDC issuer được chấp thuận.
- **Audience:** Assertion/token phải dành cho exchange endpoint phù hợp.
- **Subject:** Ràng buộc repository, branch/tag, workflow, environment hoặc service account phù hợp threat model.
- **Expiry:** Chứng thực và credential đích có thời hạn giới hạn.
- **Role boundary:** Chỉ gán quyền cần để deploy target đã duyệt.
- **Change control:** Ai được sửa workflow, branch protection và job permissions?
- **Audit:** Truy job/run ID, commit/release và cloud actions.

**Không cấu hình tin tất cả repository hoặc mọi branch của một issuer**, vì có thể cho workflow ngoài ý muốn nhận credential production.

### 11.2. Federation vẫn có đặc quyền gián tiếp

Người không trực tiếp có cloud admin nhưng có thể **sửa workflow chạy bằng cloud role mạnh** có thể tạo tác động tương đương. Cần review cả **CI/CD repository permissions, approval gates và principal role**, không chỉ token phát ra lúc runtime.

## 12. Kubernetes ServiceAccount và danh tính pod

**Kubernetes ServiceAccount** là một đối tượng dùng để cung cấp identity cho các tiến trình trong Pod khi tương tác với API hoặc tích hợp nhận dạng workload. Nó không phải account của nhân viên và không tự bảo đảm quyền ngoài cluster.

Ví dụ YAML rút gọn:

~~~yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: invoice-reconciler
  namespace: finance
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: invoice-reconciler
  namespace: finance
spec:
  replicas: 2
  selector:
    matchLabels:
      app: invoice-reconciler
  template:
    metadata:
      labels:
        app: invoice-reconciler
    spec:
      serviceAccountName: invoice-reconciler
      containers:
        - name: worker
          image: example.invalid/invoice-reconciler:v1
~~~

**Đây là ví dụ minh họa**, không phải manifest production đầy đủ: thiếu resource limits, image verification, security context và các cấu hình bảo vệ khác.

### 12.1. Những điểm phải kiểm

- ServiceAccount có **RBAC role/rolebinding tối thiểu**.
- Không vô tình dùng `default` ServiceAccount có quyền rộng.
- Token được cấp theo khả năng nền tảng, ưu tiên **audience và thời hạn phù hợp**.
- Không mount ServiceAccount token vào Pod **không cần dùng** Kubernetes API.
- Tách namespace/environment khi cần và kiểm quyền xuyên namespace/cluster.
- Chỉ Pod/identity tin cậy mới được dùng để đổi credential cloud qua workload federation.
- Role cloud gắn với ServiceAccount cần **điều kiện trust** chặt, không chỉ trùng tên.
- Khi Deployment hoặc namespace bị xóa, kiểm cả **cloud role assignment, external tokens và secret references**.

### 12.2. ServiceAccount name không tự chứng minh một Pod an toàn

Nếu kẻ tấn công có thể tạo Pod mang cùng ServiceAccount hoặc truy cập token từ một Pod bị chiếm, họ có thể dùng quyền đã gán. Cần kiểm **ai được deploy Pod, ai được bind ServiceAccount, admission controls, network và runtime security**.

## 13. Certificate/mTLS và machine identity

Một số NHA sử dụng **certificate và private key** để chứng minh danh tính cho service khác. Với **mutual TLS (mTLS)**, cả hai phía kết nối có thể xác thực certificate của nhau theo trust policy.

Cần phân biệt:

- **TLS bảo vệ kênh truyền**.
- **Client certificate** có thể giúp xác thực workload.
- **Authorization** vẫn cần quyết định client này được dùng action/resource nào.
- **Certificate lifetime/renewal** và key protection là phần của credential lifecycle.
- **Certificate identity binding** phải được quản trị, tránh chấp nhận sai trust domain.

Trong các hệ thống dùng **SPIFFE/SPIRE** hoặc mô hình tương tự, workload có thể được cấp **identity và chứng thực ngắn hạn** dựa trên trust của runtime/platform. Đây là lựa chọn kiến trúc để giảm quản lý secret thủ công; vẫn cần quản trị **trust domain, registration, workload selectors, policy và vòng đời**.

**Không coi “có chứng thư hợp lệ” là “được phép truy cập tất cả API”**. Xác thực và phân quyền là hai bước khác nhau.

## 14. Quyền NHA phải tuân Least Privilege

Một NHA cần được quyền **đủ cho nhiệm vụ**, không phải toàn quyền trên ứng dụng hoặc subscription.

| Công việc | Quyền phù hợp hơn | Quyền dễ bị xin quá |
|---|---|---|
| Đồng bộ báo cáo | `reports.read@tenant-A` | `tenant.admin` |
| Ghi backup vào vùng chỉ định | `backup.write@bucket-A` | `storage.*@all-buckets` |
| Đọc một secret ứng dụng | `secret.get@payment-service` | `vault.admin` |
| Triển khai một service staging | `deploy.update@staging/service-X` | `subscription.owner@production` |
| Đọc metric health | `metrics.read@service-X` | `cluster.admin` |
| Đưa bản tin vào queue | `queue.publish@orders-events` | `queue.admin@all` |
| Truy vấn DB báo cáo | `SELECT trên view cụ thể` | `DBA/DDL/DELETE` |
| Tạo ticket hỗ trợ | `ticket.create` | `ticket.delete/all-data-export` |

### 14.1. Scope cần nhiều chiều

Một quyền mô tả rõ nên xét:

~~~text
Subject:       workload / identity / owner
Action:        read | write | publish | deploy | administer
Resource:      API, bucket, database, queue, secret
Tenant:        tenant-A (nếu có)
Environment:   staging | production
Audience:      Resource Server dự kiến
Time:          TTL hoặc lifecycle gate
Context:       workload state, deployment, policy, risk
~~~

NHA có token hợp lệ cho API X không nên dùng cùng token để gọi API Y nếu **audience khác nhau**. Role `writer` ở tenant A không tự có quyền ghi tenant B.

### 14.2. JIT/JEA cho workload có đặc quyền

Một job sửa cấu hình production có thể chỉ cần role quyền cao **trong cửa sổ triển khai đã duyệt**. Có thể áp **Just-in-Time (JIT)** và **Just-Enough Access/Administration (JEA)** cho cả non-human access theo khả năng nền tảng, không mặc định để principal làm admin 24/7.

## 15. RBAC, ABAC và PBAC cho tài khoản máy

**Role-Based Access Control (RBAC)** gán quyền theo role; **Attribute-Based Access Control (ABAC)** đánh giá thêm thuộc tính; **Policy-Based Access Control (PBAC)** tập hợp quy tắc và điều kiện để PDP/PEP quyết định.

Ví dụ một chính sách:

~~~text
PERMIT invoice.read nếu:
  subject.kind == WORKLOAD
  AND subject.workloadId == "invoice-reconciler"
  AND subject.status == ACTIVE
  AND subject.environment == "production"
  AND action == "invoice.read"
  AND resource.tenantId == subject.tenantId
  AND resource.projectId thuộc authorizedProjects
  AND token.audience đúng Reporting API
  AND không có explicit deny áp dụng

DENY nếu:
  thiếu thuộc tính bắt buộc, vượt scope,
  workload đã retired hoặc credential không hợp lệ.
~~~

**Đây là logic mô tả, không phải DSL chuẩn.** Mọi dữ liệu workload/tenant/scope phải lấy từ **trusted identity claims hoặc dữ liệu backend**, không tin các field do client tự khai.

### 15.1. Workload không mượn vai trò người

Nếu API có policy `finance_employee` đòi employee engagement ACTIVE, không nên tự tạo fake employee record cho service principal để qua kiểm tra. Hãy định nghĩa **subject kind và policy riêng** cho workload, với owner và scope rõ.

### 15.2. PEP phải bảo vệ hành động tại API

Ẩn một route admin khỏi bot hoặc không cấp nút UI **không tạo authorization**. Resource Server phải kiểm token/credential và quyền trên **resource/action** trong backend, kể cả batch API và background job.

## 16. Metadata tối thiểu của một Non-human account

Một hệ thống governance nên có thể trả lời:

| Trường | Vì sao cần | Ví dụ |
|---|---|---|
| **canonicalWorkloadId** | Định danh ổn định | `workload:invoice-sync-prod` |
| **account/principal IDs** | Ánh xạ các target | Cloud principal, OAuth client, DB user |
| **kind** | Phân biệt human và workload | `WORKLOAD` |
| **businessPurpose** | Lý do tồn tại | Đồng bộ hóa hóa đơn |
| **technicalOwner** | Người/nhóm vận hành hiện tại | Billing Platform Team |
| **businessOwner/sponsor** | Chủ mục đích hoặc dữ liệu | Finance Data Owner |
| **application/service** | Dịch vụ được đại diện | Invoice Reconciler |
| **environment/tenant** | Ranh giới quyền | prod/tenant-A |
| **resource/action scope** | Permission cần thiết | invoice.read/project-17 |
| **credential method** | Xác thực bằng gì | Managed identity/OIDC federation |
| **secret reference** | Truy vết quản lý secret nếu có | Vault path ID, không chứa secret |
| **creation/last-verified** | Lịch sử và độ mới | Timestamps |
| **review/expiry/retirement** | Lifecycle và hạn kiểm | Review cadence, retire trigger |
| **dependency** | Tránh xóa sai workload đang chạy | Deployment/job ID |
| **approval/change** | Căn cứ cấp quyền | Ticket/change ID |
| **audit references** | Truy dấu hoạt động/quyết định | Correlation IDs |

### 16.1. JSON ví dụ về inventory

~~~json
{
  "workloadId": "workload:invoice-reconciler:prod",
  "kind": "WORKLOAD",
  "status": "ACTIVE",
  "service": "invoice-reconciler",
  "environment": "production",
  "tenantId": "tenant-A",
  "technicalOwner": "billing-platform-team",
  "businessOwner": "finance-data-owner",
  "accounts": [
    {
      "system": "cloud-iam",
      "principalRef": "principal-invoice-prod"
    },
    {
      "system": "reporting-api",
      "clientRef": "client-invoice-prod"
    }
  ],
  "authentication": {
    "method": "WORKLOAD_IDENTITY_FEDERATION",
    "issuerRef": "trusted-runtime-issuer",
    "credentialReference": "NO_LONG_LIVED_SECRET"
  },
  "authorizedAccess": [
    {
      "action": "invoice.read",
      "resourceScope": "project-17",
      "audience": "reporting-api"
    }
  ],
  "lifecycle": {
    "createdByChange": "CHG-221",
    "lastOwnerReview": "2026-11-15T09:00:00Z",
    "reviewRequiredOn": [
      "OWNER_CHANGED",
      "DEPLOYMENT_RETIRED",
      "SCOPE_CHANGED",
      "CREDENTIAL_EXPOSURE"
    ]
  }
}
~~~

**Dữ liệu minh họa, không phải schema chuẩn.** Không đưa private key, client secret, access token, refresh token hoặc credential nguyên văn vào inventory. Nếu phải trỏ tới vault, sử dụng **tham chiếu có kiểm soát quyền**.

## 17. Discovery và kiểm kê Non-human accounts

Một tổ chức có thể có NHA ở nhiều hệ thống mà không nằm chung trong một danh sách.

### 17.1. Những nguồn phát hiện

- OAuth client registrations và service principals tại IdP/Authorization Server.
- Cloud IAM roles, identities, access keys và resource bindings.
- Kubernetes ServiceAccounts và RoleBindings/ClusterRoleBindings.
- Database users, scheduled jobs và credential stores.
- CI/CD runners, deploy credentials, repository secrets và pipeline identities.
- Secret manager/vault, certificate authority và PKI inventory.
- API gateways, access logs, integrations và webhooks.
- CMDB, service catalog, deployment manifests và job schedulers.
- SCIM connectors và application-local accounts nếu sản phẩm hỗ trợ.
- PAM/privileged access records, backup/DR accounts.

### 17.2. Discovery khác phân loại chính xác

Một account tên `svc-admin` không chắc là service identity hiện đang dùng; một principal `app-101` có thể là workload quyền cao. Không phân loại chỉ bằng **prefix tên**.

Cần correlation qua **principal ID, owner, deployment, credential reference, token issuance và audit usage**. Nếu nguồn chưa đủ, đánh dấu **UNKNOWN_OWNER/UNKNOWN_PURPOSE**, đừng tự kết luận “không hoạt động”.

### 17.3. Coverage có mẫu số rõ

Tỷ lệ “100% service accounts được review” chỉ có ý nghĩa nếu đã bao phủ **cloud, directory, database, CI/CD, ứng dụng và workload instances** trong scope. Khi một connector bị lỗi, **không có dữ liệu** khác với **không có account**.

## 18. Ownership và trách nhiệm giải trình

Một NHA nên có ít nhất một **technical/service owner**, và với dữ liệu nhạy cảm có thể cần thêm **business/data owner**.

| Vai trò | Trách nhiệm |
|---|---|
| **Technical owner** | Vận hành, deployment, kiểm dependency, cập nhật credential và account |
| **Business/data owner** | Xác nhận mục đích nghiệp vụ và quyền trên tài nguyên |
| **IAM/IGA governance** | Policy cấp quyền, review, SoD, exception và lifecycle |
| **Security team** | Threat model, phát hiện đặc quyền, ứng phó lộ credential |
| **Platform/IdP/cloud admin** | Cấp principal, thiết lập trust, hỗ trợ revoke/rotation |
| **Application/Resource Server owner** | Thực thi RBAC/ABAC và xác minh effective access |
| **Auditor** | Kiểm bằng chứng owner, grant, review, remediation |

### 18.1. Owner không đồng nghĩa “người sở hữu mật khẩu”

Owner chịu trách nhiệm **để workload được quản trị an toàn**, không nhất thiết biết hoặc trực tiếp xem private key. Một thiết kế tốt tránh cho người vận hành phải đọc secret plaintext khi có giải pháp managed identity hoặc vault injection.

### 18.2. Tránh ownership theo một cá nhân duy nhất

Nếu account production chỉ có `createdBy=P-2048` mà không có service/team owner, khi P-2048 Leaver sẽ không ai biết cách rotation hay thu hồi. Nên gắn với **đơn vị chịu trách nhiệm và dự phòng**, có quy trình thay đổi owner khi tổ chức tái cơ cấu.

## 19. Vòng đời NHA: từ nhu cầu đến nghỉ sử dụng

~~~mermaid
flowchart LR
    A["REQUESTED<br/>Mục đích + owner"] --> B["REVIEWED<br/>Risk + scope + approval"]
    B --> C["PROVISIONED<br/>Identity/account + credential"]
    C --> D["ACTIVE<br/>Workload đang dùng"]
    D --> E["ROTATE/REVIEW<br/>Credential + owner + rights"]
    E --> D
    D --> F["SUSPENDED<br/>Security hold / maintenance"]
    F --> D
    D --> G["RETIRE_REQUESTED<br/>Dependency migration"]
    G --> H["REVOKED<br/>Credential, grant, session"]
    H --> I["VERIFIED_RETIRED<br/>Target readback + audit"]
    F --> G
~~~

Đây là **mô hình logic**, không phải enum bắt buộc. Có thể có trạng thái `COMPROMISED`, `ORPHAN_REVIEW` hoặc `PENDING_DEPROVISION` tùy tổ chức. Không được gán “RETIRED” chỉ vì job deployment đã bị xóa nếu **principal hoặc credential vẫn còn quyền**.

### 19.1. Ba vòng đời liên quan nhưng khác nhau

1. **Workload lifecycle:** Service được xây dựng, triển khai, chuyển môi trường và decommission.
2. **Identity/account lifecycle:** Principal và role được tạo, thay đổi, suspend, thu hồi.
3. **Credential/token lifecycle:** Key/secret/token được phát, rotate, hết hạn, thu hồi.

**Một trong ba kết thúc không kéo theo hai cái còn lại hoàn tất tức thời.** Ví dụ xóa Deployment không tự gỡ cloud service principal hoặc IAM policy.

## 20. Provisioning NHA theo nhu cầu có thể kiểm chứng

Quy trình cấp một NHA mới nên bắt đầu từ **mục đích sử dụng**, không bắt đầu bằng “tạo một admin user cho tiện”.

### 20.1. Các bước tham khảo

1. **Đăng ký workload** với service ID, environment, team, business owner.
2. **Xác định luồng kỹ thuật**: Workload gọi API nào, hành động gì, dữ liệu ở đâu?
3. **Chọn identity type**: Managed identity, service principal, OAuth client hoặc Kubernetes ServiceAccount phù hợp.
4. **Thiết kế trust/authentication**: Issuer/subject/audience, credential method và TTL.
5. **Định nghĩa least privilege**: Permission/role theo resource, tenant và môi trường.
6. **Kiểm rủi ro/SoD**: Cloud admin, secret/key access, CI/CD pipeline quyền cao.
7. **Phê duyệt** bởi technical owner, resource/data owner và security khi policy yêu cầu.
8. **Provision** identity/account, role và secret reference qua kênh được kiểm soát.
9. **Kiểm thử** đúng action được phép và hành động ngoài scope phải bị từ chối.
10. **Ghi inventory/audit**, rotation plan, owner review và decommission trigger.

### 20.2. Những gì không nên làm

- Dùng account của lập trình viên để chạy production job.
- Tạo NHA trên tenant production bằng một password chung cho cả dev/staging/prod.
- Cấp `Owner/Admin` cho service chỉ cần đọc một API.
- Copy private key vào Git, image, wiki hoặc ticket.
- Để `expiresAt` trống mà không có review/lifecycle trigger.
- Cho requester tự sửa `approvalStatus` hoặc `riskTier` qua API.
- Tuyên bố “provision complete” khi chưa kiểm quyền ở target.

## 21. Credential management: tránh long-lived secrets nếu có thể

Một credential bị lộ có thể cho phép kẻ tấn công **mạo danh workload** mà không cần tài khoản con người.

Những kiểm soát cần thiết:

- **Ưu tiên credential ngắn hạn hoặc platform identity** khi kiến trúc hỗ trợ.
- Nếu cần secret tĩnh, lưu ở **vault/secret manager** với phân quyền hẹp.
- **Không nhúng secret trong source control, container image hay file cấu hình công khai.**
- Phân quyền ai được **đọc, tạo, rotate, revoke** credential.
- Bảo vệ key vật lý hoặc qua HSM/TPM khi mức rủi ro và nền tảng phù hợp.
- Audit mọi truy cập secret và issuance token có ý nghĩa bảo mật.
- Giới hạn **credential audience, environment và target** nếu công nghệ cho phép.
- Giám sát secret **không owner, không dùng, sắp hết hạn, bị lộ hoặc chưa rotate**.
- Có quy trình **khẩn cấp** khi secret/key bị compromise.
- Không tự coi việc đổi mật khẩu trong vault là đã đổi được tại ứng dụng đích.

### 21.1. Một secret có thể được sao chép

Nếu người hoặc workload từng xem plaintext credential, xóa quyền **checkout từ vault** không làm bản sao cũ vô hiệu. Cần **rotate/revoke tại target** và kiểm target không còn chấp nhận secret cũ.

### 21.2. Credential injection không tự giải quyết quyền quá rộng

Vault có thể cấp credential đúng cho workload, nhưng credential đó vẫn có `database.admin` trên toàn bộ cluster. Cần **credential protection** và **authorization least privilege** đồng thời.

## 22. Rotation an toàn: không làm gián đoạn workload hợp lệ

**Rotation** là thay credential đang sử dụng bằng credential mới để giảm thời gian và phạm vi lạm dụng. Một phương án rotation thường có:

~~~mermaid
sequenceDiagram
    autonumber
    participant O as Service owner / Automation
    participant V as Vault / Credential issuer
    participant W as Workload runtime
    participant T as Target API / DB
    participant A as Audit / Verification

    O->>V: Yêu cầu rotation có căn cứ
    V-->>O: Credential mới / secret version
    O->>W: Triển khai reference/binding mới
    W->>T: Xác thực với credential mới
    T-->>A: Kết quả auth và phạm vi quyền
    A-->>O: New credential works, scope đúng
    O->>V: Revoke/retire credential cũ theo policy
    V->>T: Đồng bộ thay đổi nếu cần
    O->>A: Xác minh credential cũ không còn truy cập
    A-->>O: Rotation verified hoặc exception
~~~

### 22.1. Rotation khác đổi giá trị trong cấu hình

Một secret được thay trong vault nhưng **Pod đang giữ bản cũ trong memory** vẫn có thể sử dụng bản cũ, hoặc ngược lại Pod bị hỏng vì credential mới chưa được target chấp nhận. Cần hiểu:

- Target hỗ trợ **dual credential/overlap window** hay không?
- Ứng dụng **hot reload** secret hay cần restart?
- Thay đổi có làm hỏng job/connection pool không?
- Token đã phát trước rotation còn hợp lệ tới khi nào?
- Có môi trường test/canary hoặc rollout từng phần?
- Hệ thống nào bị ảnh hưởng khi revoke ngay credential cũ?

Không duy trì credential cũ vô hạn sau migration. Với secret bị lộ, **incident response** có thể yêu cầu ưu tiên revoke nhanh hơn kế hoạch rotation thông thường.

### 22.2. Readback rotation cần hai chiều

- **Positive:** Credential mới hoạt động **đúng scope**.
- **Negative:** Credential cũ bị từ chối theo yêu cầu revoke.
- **Authorization:** Workload không được phép vượt action/resource.
- **Operations:** Job/deployment còn hoạt động đúng.

**Đổi credential thành công không tự chứng minh quyền dư thừa đã bị gỡ**.

## 23. Token, session và vấn đề quyền tồn dư

Workload có thể lấy access token có TTL và giữ connection pool lâu dài. Khi IAM gỡ role hoặc revoke client credential, đường truy cập thực tế phụ thuộc công nghệ:

| Thành phần | Có thể vẫn tồn tại | Cần xem gì? |
|---|---|---|
| **Access token** | JWT tự chứa còn hạn | Token TTL, Resource Server validation, revocation strategy |
| **Refresh token** | Nếu flow/phương án có phát | Chính sách issuance, revoke và rotation |
| **Database connection** | Session đã xác thực | Target revalidate privilege hay chỉ tại connect? |
| **Cloud session credentials** | Temporary credentials còn thời gian | IAM policy/role check, session TTL, kill mechanism |
| **API key** | Key tồn tại ở gateway | Revoke ở API gateway/service, cache |
| **Certificate** | Cert còn hạn | Trust, expiry, revocation/check behavior |
| **Local role/ACL** | Quyền cấp trực tiếp ngoài IAM | Target readback và grant provenance |
| **PIM/PAM grant** | Eligible hoặc active privilege | Revocation của role và phiên |

**Không mặc định “đã disable principal” đồng nghĩa mọi request đang có token sẽ bị từ chối ngay.** Nếu yêu cầu thu hồi tức thời, thiết kế cần có cơ chế **kiểm trạng thái, token lifetime phù hợp, revocation, session management hoặc chặn tại PEP**.

## 24. NHA và Joiner–Mover–Leaver của con người

Đây là điểm cốt yếu của mô-đun. **Nhân viên là owner/maintainer**, còn **workload có lifecycle kỹ thuật riêng**. Sự kiện JML của người tạo/owner **phải kích hoạt review các quyền có liên quan**, nhưng **không tự suy ra mọi workload phải bị xóa**.

### 24.1. Joiner: người mới nhận quyền quản lý NHA

Nhân viên mới có thể được:

- Xác minh identity/engagement qua HR/VMS.
- Tạo account qua IAM/IdP/SSO, áp MFA cho đường human admin.
- Được giao role vận hành `workload.operator` hoặc quyền xem log theo nhiệm vụ.
- Có khả năng yêu cầu rotation/deploy theo approval.
- **Không mặc định có quyền đọc mọi production secret** chỉ vì vào đội Platform.
- Không tự có quyền sửa cloud IAM role của mọi NHA hoặc cấp credential tùy ý.
- Được đào tạo và áp SoD cho hành động nhạy cảm.

**Quyền quản lý NHA của người mới cũng là access grant**, cần xét least privilege và mốc hiệu lực engagement.

### 24.2. Mover: owner/maintainer chuyển bộ phận

Ví dụ kỹ sư An chuyển Platform → Analytics:

~~~text
Trước Mover:
  An quản lý workload billing-sync
  Có quyền rotate production client credential
  Có quyền sửa deployment và cloud role

Sau Mover:
  billing-sync vẫn chạy cho Finance
  An không còn nhiệm vụ quản trị service
  Team Platform mới nhận ownership
~~~

Phải đồng thời:

1. Chuyển **technical owner** và runbook.
2. Gỡ role của An trong vault, CI/CD, cloud IAM, console và service catalog.
3. Kiểm credential/secret An từng biết hoặc có khả năng lấy được.
4. Rotate/revoke theo rủi ro, tránh ảnh hưởng production khi cần migration.
5. Kiểm active session/PAT và nhóm quản trị khác.
6. Xác minh service vẫn hoạt động và An không còn đường tác động trái policy.

**Không xóa `billing-sync` chỉ vì An Mover**; cũng không giữ An có `secret.admin` mãi vì “từng là người tạo”.

### 24.3. Leaver: người sở hữu nghỉ việc

Khi owner Leaver:

- HR/VMS phát **event và effectiveAt**.
- IAM/IGA xác định mọi NHA mà người đó tạo, quản lý, có quyền sửa hoặc từng checkout credential.
- Tìm owner/người dự phòng mới có thẩm quyền cho workload còn phục vụ.
- Thu hồi **quyền quản trị của human** tại vault/cloud/CI/CD/IdP/directory/app.
- Kiểm credential từng bị biết hoặc khả năng bị lưu bên ngoài; rotate/revoke nếu cần.
- Đối soát account/service còn có owner, role đúng scope.
- Nếu NHA đã không còn nhiệm vụ, lập kế hoạch **retire an toàn**.
- Đọc lại quyền và xác nhận kết quả.

**Disable IdP user của Leaver không tự thu hồi client secret, SSH key, service principal hay API token của một NHA đang chạy độc lập.**

## 25. Vòng đời workload: Provision–Change–Retire

Ngoài JML của con người, NHA cần lifecycle riêng:

| Sự kiện workload | Hành động IAM/NHA |
|---|---|
| **Create service** | Đăng ký NHI/NHA, owner, purpose, policy, credential |
| **Deploy dev/staging** | Dùng principal/scope tách khỏi production |
| **Deploy production** | Approval phù hợp, role và trust binding production |
| **Scale replicas** | Không tạo secret thủ công theo mỗi replica; kiểm sharing boundary |
| **Change API/resource** | Review audience/scope, cập nhật policy |
| **Change technical owner** | Reassign, review credential access và approval roles |
| **Incident/compromise** | Suspend, rotate/revoke, điều tra và phục hồi |
| **Credential expiration** | Reissue/rotate có readback |
| **Migrate platform** | Chuyển principal/trust/roles an toàn; thu hồi credential cũ |
| **End of project** | Xem NHA còn tác vụ hay phụ thuộc nào không |
| **Decommission** | Revoke tokens/keys/roles, xóa account/ACL, xác minh |
| **Recreate workload** | Provision identity theo policy hiện hành, không tự phục hồi grant cũ |

### 25.1. Recreate không phải hồi sinh toàn bộ quyền cũ

Sau khi service bị retire, một dự án mới có thể dùng cùng tên nhưng **mục đích, owner, tenant và trust đã khác**. Không tự dùng lại credential/grant từ workload cũ chỉ vì tên container hoặc service trùng.

## 26. Deprovision NHA đúng cách

Đây là quy trình **chấm dứt quyền truy cập** cho một NHA không còn nhiệm vụ hoặc bị thu hồi theo sự kiện.

### 26.1. Quy trình thực hành

1. **Xác minh quyết định retire/suspend** và owner có thẩm quyền.
2. **Kiểm dependency:** Workload, cron job, backup, consumer, API gateway, cloud role, secret ref.
3. **Xác định desired state:** Principal nào phải mất role, key nào cần revoke, token/session nào phải ngừng.
4. **Chặn kích hoạt/cấp token mới** theo chính sách.
5. **Thu hồi credential/grant ở target:** Client secret/certificate/API key, cloud role, DB user, service principal, ACL.
6. **Xử lý token/session đã phát** theo khả năng và mức rủi ro.
7. **Gỡ secret references** trong deployment/config/CI/CD mà không làm rò bí mật.
8. **Readback:** Target không còn chấp nhận credential/quyền; không có role ngoài căn cứ.
9. **Theo dõi regrant:** Kiểm automation/desired state không tái cấp account đã retire.
10. **Lưu audit và bằng chứng**, giữ owner của phần chưa thể xử lý.

### 26.2. Tách “đã gửi lệnh” khỏi “đã mất quyền”

~~~text
IAM/IGA desired state: account RETIRED
  !=
Cloud/DB/App target: role/secret đã thực sự bị gỡ
  !=
Access token/session: không còn được chấp nhận

Verified deprovision:
  Tất cả đường truy cập bắt buộc đạt desired state
  theo tiêu chí readback được duyệt.
~~~

Một response `HTTP 200` từ connector chỉ chứng minh lệnh được nhận/xử lý theo contract, không bao phủ mọi hệ thống hoặc cached session.

### 26.3. Khi không thể thu hồi ngay

Ví dụ job xử lý thanh toán production đang dùng static credential shared với một service khác. Không xóa bừa rồi gây outage; phải:

- Mở **remediation/exception** có risk owner và deadline.
- Cân nhắc bù trừ: hạn network, scope, alert và giám sát.
- Lập kế hoạch tách principal/credential.
- Test deployment mới.
- Revoke credential/quyền cũ và xác minh.

**Không để “khó thu hồi” trở thành lý do cho NHA không owner sống vô thời hạn.**

## 27. SCIM, IdP, SSO và NHA: phạm vi hỗ trợ khác nhau

**SCIM** thường được dùng để đồng bộ **Users/Groups** giữa hệ thống quản trị danh tính và ứng dụng hỗ trợ. Nó hữu ích cho lifecycle account người và một số loại account/nhóm theo implementation, nhưng **không phải giao thức chuẩn chung để quản lý mọi workload identity, secret, certificate, OAuth client, Pod hoặc cloud principal**.

| Thành phần | Có thể đóng vai trò gì | Không tự giải quyết |
|---|---|---|
| **HR/VMS** | Nguồn JML của human owner/sponsor | Trạng thái runtime của workload |
| **IdP/SSO** | Xác thực human admin; đôi khi quản lý app/client registration | Mọi local service credential của ứng dụng |
| **Authorization Server** | Cấp token cho OAuth client đã xác thực | Quyền resource cụ thể nếu API không kiểm |
| **SCIM** | Đồng bộ Users/Groups ở target hỗ trợ | Revoke mọi token, key, cloud IAM role |
| **Cloud IAM** | Managed identity, role/policy, workload trust | Human owner đã Mover/Leaver nếu không có kết nối governance |
| **PAM/PIM** | Quản lý privileged identity, credential, session hoặc elevation | Mọi service token ngoài phạm vi sản phẩm |
| **Kubernetes** | ServiceAccounts, RBAC và runtime identity | Mọi entitlement trên cloud/DB ngoài cluster |
| **IGA/service catalog** | Ownership, approval, certification, lifecycle | Tự chứng minh mọi target đã áp thay đổi |
| **PEP/Resource Server** | Kiểm action/resource với token/context | Tự xác định business purpose nếu thiếu nguồn dữ liệu |

### 27.1. SSO cho người quản lý NHA, không nhất thiết cho NHA

Kỹ sư dùng **SSO + MFA** để đăng nhập console quản trị service principal. Bản thân workload gọi API bằng **client credentials, managed identity hoặc federation**. Hai đường xác thực có mục đích khác nhau; không ép robot “đăng nhập browser SSO như người” bằng credential người.

## 28. Access review và recertification cho NHA

Quyền workload có thể tồn tại lâu, vì vậy review cần định kỳ/theo sự kiện theo rủi ro.

Một reviewer phải trả lời:

1. Workload còn tồn tại và được triển khai ở đâu?
2. Mục đích nghiệp vụ/technical purpose còn đúng không?
3. Technical owner và data owner còn hiệu lực không?
4. Có service/account duplication hoặc unused principal không?
5. Có permission vượt scope, role admin hoặc SoD conflict không?
6. Credential đang dùng phương thức nào, có rotation/expiry không?
7. Workload có production/staging separation không?
8. Có token/API key/secret do owner cũ từng biết?
9. Các quyền trực tiếp/role kế thừa có bị bỏ sót?
10. Nếu quyết định REVOKE/MODIFY, đã xác minh quyền hiệu dụng và dependency chưa?

### 28.1. Những quyết định review

| Quyết định | Khi nào | Bằng chứng tiếp theo |
|---|---|---|
| **KEEP** | Workload còn nhu cầu, đúng scope, owner xác nhận | Decision, purpose, policy, mốc review |
| **MODIFY** | Role/tenant/resource quá rộng | Provision scope mới và test DENY ngoài phạm vi |
| **ROTATE** | Credential quá lâu, lộ hoặc owner change | New credential hoạt động, old credential bị từ chối |
| **REVOKE** | Tài khoản không còn nhiệm vụ hoặc trái chính sách | Deprovision + target readback |
| **ESCALATE** | Không rõ owner/dependency/rủi ro | Risk owner, service owner, hạn xử lý |
| **EXCEPTION** | Chưa sửa ngay vì dependency | Owner, TTL, bù trừ, kế hoạch và theo dõi |

**Last-used=never** là tín hiệu điều tra, không phải kết luận tự động xóa NHA: recovery/backup account có thể được thiết kế dùng hiếm. Ngược lại, một client được dùng hàng ngày **không chứng minh** quyền admin của nó hợp lệ.

## 29. Những mối đe dọa phổ biến

| Rủi ro | Ví dụ | Kiểm soát |
|---|---|---|
| **Hard-coded secret** | Client secret trong Git/image | Secret scanning, vault, short-lived credentials |
| **Credential leakage** | Token ghi vào log/build artifact | Log sanitization, revoke/rotate, IR |
| **Overprivileged principal** | Job đọc metrics có `cloud.owner` | Least privilege, IAM policy review |
| **Shared credential across env** | Dev/staging/prod dùng cùng key | Separate identity, isolation, rotation |
| **Shadow integration** | Bot tự tạo không có owner | Discovery, inventory, approval |
| **Orphan NHA** | Người tạo đã Leaver, principal vẫn admin | Owner reassignment, review, revoke |
| **Workload impersonation** | Job không đúng nguồn dùng trust rộng | Issuer/sub/audience binding, runtime controls |
| **Token replay/theft** | Token ngắn hạn bị lấy từ container | Key/token protection, TTL, audience, telemetry |
| **Privilege escalation via CI/CD** | Người sửa workflow dùng role production | Protected branches, approval, role boundaries |
| **Cross-tenant access** | Client A đọc tenant B | PEP resource/tenant enforcement |
| **Missing deprovision** | Workload nghỉ, API key vẫn active | Event-driven retire, readback |
| **Multiple grant sources** | Xóa role A nhưng direct ACL vẫn cho phép | Effective access reconciliation |
| **Unmanaged certificates** | Cert/CA trust không ai quản | PKI inventory và renewal/revocation |
| **No logging** | Service principal gọi API không có trace | Client/job/resource audit correlation |
| **Unreliable rotation** | Đổi secret khiến production outage | Canary, overlap nếu cho phép, tests |
| **Owner self-approval** | Developer tự cấp admin cho job của mình | SoD, resource owner review |
| **Persistence after compromise** | Attacker tạo key/role mới | Alert, inventory diff, incident response |
| **Retired account reappears** | IaC/controller tạo lại principal đã xóa | Fix source of truth, reconciliation |

### 29.1. Một secret có thể có blast radius rất lớn

Một key của service principal chỉ đọc một queue ít nhạy cảm thường khác hoàn toàn key có thể **sửa cloud IAM policy, đọc mọi production secret và xóa backup**. Ưu tiên kiểm soát phải dựa **impact, reachability, scope, lifetime và khả năng phát hiện**, không chỉ số lượng NHA.

## 30. Quan sát và kiểm toán NHA

NHA cần được ghi nhận tại nhiều điểm:

- **Identity administration:** Ai tạo principal, gán owner, sửa role, rotate credential.
- **Token/credential issuance:** Client nào xin token, audience/scope, issuer, thành công/thất bại.
- **Runtime/deployment:** Job run, release/commit, Pod/service ID, environment.
- **API/resource actions:** Action, resource, tenant, quyết định PERMIT/DENY, policy.
- **Privileged changes:** Sửa IAM policy, secret, role, CI/CD hoặc firewall.
- **Lifecycle events:** Suspend, owner transfer, deprovision, revocation.
- **Alert/incident:** Hành vi bất thường, credential exposure và remediation.
- **Readback:** Target xác nhận permission/credential không còn hoặc đã giảm scope.

### 30.1. Actor và subject có thể khác nhau

Một người dùng SSO chạy deployment; pipeline nhận OIDC assertion và đổi lấy cloud credential; cloud audit ghi `principal=deploy-workload`. Cần correlation:

~~~text
Human requester/approver (nếu có)
  -> Change/deployment ID
  -> CI/CD run ID + commit
  -> Workload identity / principal
  -> Token issuance
  -> Cloud/API action + resource
  -> Target outcome + audit
~~~

Nếu automation chạy theo scheduler được duyệt, audit nên ghi **trigger/policy version** thay vì gán bừa cho nhân viên không thực sự kích hoạt.

### 30.2. Mẫu audit event

~~~json
{
  "eventType": "WORKLOAD_ACCESS",
  "time": "2026-12-03T09:22:00+07:00",
  "workloadId": "workload:invoice-reconciler:prod",
  "principalRef": "principal-invoice-prod",
  "runtimeRef": "job-run-8821",
  "issuerRef": "trusted-runtime-issuer",
  "audience": "reporting-api",
  "action": "invoice.read",
  "resourceRef": "invoice-501",
  "tenantRef": "tenant-A",
  "decision": "PERMIT",
  "policyVersion": "invoice-workload-policy-v3",
  "credentialType": "SHORT_LIVED_TOKEN",
  "ownerRef": "billing-platform-team",
  "correlationId": "REQ-8821-51"
}
~~~

Đây là dữ liệu giả lập. Không ghi **access token, secret, private key hoặc nội dung dữ liệu nghiệp vụ** vào log chỉ để truy vết. Bảo vệ log khỏi sửa/xóa bằng quyền của workload được theo dõi khi khả năng nền tảng cho phép.

## 31. Reconciliation: desired access khác effective access

Khi quản trị NHA, cần phân biệt:

~~~text
Desired access:
  Quyền được policy/owner phê duyệt cho workload hiện tại

Observed assigned access:
  Role, ACL, group, secret permission đang gán ở target

Effective access:
  Những action mà Resource Server thực sự cho phép
  xét token, claim, policy, tenant, session và cache

Discrepancy:
  Quyền thừa, thiếu quyền, quyền ngoài catalog
  hoặc đường truy cập chưa được kiểm kê
~~~

Ví dụ IAM gỡ role `storage.admin`, nhưng một **direct bucket policy** vẫn cho principal xóa đối tượng. Nếu readback chỉ xem role, kết luận thu hồi có thể sai. Cần xem **mọi grant source liên quan** và thực hiện permission check/negative test an toàn.

### 31.1. Snapshot và eventual consistency

Cloud IAM policy, directory group, cached token và target ACL có thể cập nhật không đồng thời. Vì vậy cần lưu:

- `desiredStateVersion` và mốc yêu cầu.
- Connector/target update result.
- `observedAt` và độ mới dữ liệu.
- Credential/token/session đã phát có còn hiệu lực không.
- Kết quả permission test và phạm vi.
- Ngoại lệ còn mở, owner và hạn xử lý.

**Không coi “không tìm thấy account trong một API” là không còn đường truy cập**, nếu còn target/local account hoặc token khác.

## 32. Pseudocode phân biệt workload hợp lệ với yêu cầu vượt scope

Ví dụ Python sau chỉ mô tả các điểm kiểm soát; **không phải thư viện xác thực hay authorization production**.

~~~python
def authorize_workload_request(identity, request, policy, sources):
    """
    Mọi giá trị identity / token claims phải đến từ bộ xác thực
    đã kiểm chứng, không lấy từ JSON do client tự khai.
    """

    if identity is None or identity.kind != "WORKLOAD":
        return False

    if not identity.authenticated:
        return False

    if identity.workload_id != policy.workload_id:
        return False

    if identity.status != "ACTIVE":
        return False

    if identity.audience != policy.required_audience:
        return False

    if request.action not in policy.allowed_actions:
        return False

    if request.resource_id not in policy.allowed_resources:
        return False

    # Resource metadata phải được lấy từ nguồn tin cậy.
    resource = sources.resource(request.resource_id)
    if resource is None:
        return False

    if identity.tenant_id != resource.tenant_id:
        return False

    if sources.is_explicitly_denied(identity, resource, request.action):
        return False

    # Còn cần xét token expiry/revocation, env, project, SoD,
    # context và kết quả policy combining theo kiến trúc thật.
    return True
~~~

Điều quan trọng không nằm ở câu lệnh Python mà ở **trust boundary**: client có thể gửi `workloadId=invoice-reconciler` trong request body, nhưng việc khai một chuỗi tên **không chứng minh danh tính workload**. Identity phải được xây từ **credential/assertion/token hợp lệ** do hệ thống xác minh.

### 32.1. Vì sao kiểm tra mỗi client_id chưa đủ?

Nếu một secret của `client-invoice-prod` bị lộ, kẻ tấn công có thể dùng đúng `client_id` và secret để mạo danh client. Cần bảo vệ credential, giảm scope/TTL, giám sát runtime và phương án revoke/rotate.

## 33. Tình huống A: cron job sử dụng mật khẩu nhân viên

**Bối cảnh:** Job đối soát dùng tên đăng nhập/mật khẩu của nhân viên An để đọc database. An Mover sang bộ phận khác; job vẫn chạy bằng credential đó.

**Vấn đề:** Không tách human identity và workload; audit không phân biệt hành động người và job. Khi An Leaver, nếu account bị disable thì job có thể hỏng; nếu giữ account vì job thì tạo quyền tồn dư cho người.

**Cách xử lý:**

1. Kiểm nhu cầu job, target/action và owner hiện hành.
2. Tạo workload identity hoặc service account riêng có role read-only theo nguồn policy.
3. Chuyển job sang credential được quản lý, ưu tiên ngắn hạn nếu hỗ trợ.
4. Test chạy thành công và chặn thao tác ngoài scope.
5. Gỡ credential người khỏi job, revoke bản sao cũ an toàn.
6. Kiểm role của An theo JML, không giữ vì automation.
7. Đăng ký owner, rotation, monitoring và decommission trigger.

**Bài học:** Tài khoản cá nhân không nên trở thành dependency dài hạn của automation.

## 34. Tình huống B: CI/CD có cloud admin trên production

**Bối cảnh:** Pipeline chỉ deploy một microservice ở staging nhưng service principal của CI/CD có quyền `subscription.owner` trên cloud production.

**Rủi ro:** Người có quyền sửa workflow hoặc lấy credential có thể tác động toàn subscription. Đây là **privileged non-human access**, không chỉ là một job triển khai tiện lợi.

**Cách xử lý:**

- Tách principal của staging và production.
- Gán permission chỉ cho target/resources được triển khai.
- Xem xét OIDC workload identity federation thay secret dài hạn nếu phù hợp.
- Ràng buộc issuer, repository/branch/environment, audience và role trust.
- Bảo vệ thay đổi pipeline, approval release và artifact provenance.
- Revoke principal/credential production cũ sau migration có readback.
- Kiểm negative test pipeline staging không thể sửa production.

**Bài học:** Khả năng sửa automation có thể tạo **đặc quyền gián tiếp** lớn hơn role hiển thị của người.

## 35. Tình huống C: service account “mồ côi” sau Leaver

**Bối cảnh:** `svc-invoice-export` có client secret đọc dữ liệu nhạy cảm. Người tạo account đã nghỉ, service catalog không có owner, nhưng access logs còn hoạt động.

**Sai lầm thứ nhất:** Xóa ngay account không đánh giá dependency, làm hỏng báo cáo production.

**Sai lầm thứ hai:** Giữ toàn bộ quyền vô thời hạn vì “không biết ai dùng”.

**Hướng xử lý:**

1. Đối chiếu client ID với token issuance, API access, deployment và job scheduler.
2. Tìm service/business owner có thẩm quyền.
3. Xem scope có thật sự cần export toàn tenant không.
4. Kiểm nhân sự cũ từng có quyền lấy secret và lập kế hoạch rotation.
5. Nếu workload còn hợp lệ, cập nhật owner và giảm quyền.
6. Nếu workload không còn, decommission theo change plan.
7. Kiểm credential cũ không còn được chấp nhận và log không còn truy cập trái policy.

**Bài học:** **Ownerless** là finding cần điều tra, không tự tương đương “unused”.

## 36. Tình huống D: một workload dùng chung key cho dev và production

**Bối cảnh:** Nhóm kỹ thuật dùng cùng API key cho integration dev, staging và production. Key được đặt trong nhiều repository và một lần log build.

**Rủi ro:** Lộ key ở môi trường ít được bảo vệ có thể làm lộ quyền production. Không thể rotate một nơi mà không tác động nơi khác.

**Cách xử lý:**

- Phân loại sự cố lộ credential, xác định phạm vi.
- Tạo identity và credential **riêng theo environment**.
- Giảm quyền production đến mức cần thiết.
- Đưa secrets vào hệ thống quản lý phù hợp; không commit key.
- Migration có kiểm thử, rồi revoke key dùng chung.
- Xác minh dev không còn quyền production.
- Thêm secret scanning và policy ngăn re-use.

**Bài học:** **Environment isolation** là ranh giới quan trọng của NHA.

## 37. Tình huống E: xóa Pod nhưng cloud role vẫn tồn tại

**Bối cảnh:** Deployment và Kubernetes ServiceAccount `data-sync` đã được xóa sau kết thúc dự án. Tuy nhiên cloud role trust và binding cho workload cũ vẫn còn cấu hình.

**Rủi ro:** Nếu trust policy quá rộng hoặc có thể tái tạo ServiceAccount có cùng subject, quyền cũ có thể được kích hoạt lại; cũng có nguy cơ principal, ACL hoặc key khác vẫn tồn tại.

**Cách xử lý:**

1. Kiểm danh sách role/trust bindings, cloud service principals và authorization hiện hành.
2. So sánh với service catalog và quyết định retirement.
3. Thu hồi role/credential/ACL/identity ngoài Kubernetes.
4. Kiểm trust policy có ràng buộc đúng source/namespace/workload không.
5. Xác minh token/credential cũ không còn khả năng truy cập theo yêu cầu.
6. Theo dõi automation/IaC không tạo lại quyền đã retire.

**Bài học:** **Xóa workload runtime không tự thu hồi mọi quyền NHA bên ngoài runtime**.

## 38. Tình huống F: đổi secret rồi vẫn dùng được token cũ

**Bối cảnh:** Client secret bị lộ. Đội vận hành rotate secret ở Authorization Server, nhưng Reporting API vẫn chấp nhận access token phát trước đó đến khi hết `exp`.

**Phân tích:** Đây là sự khác nhau giữa **client authentication credential** và **access token**. Rotation secret không luôn làm access token đã phát bị vô hiệu tức thời.

**Cách xử lý:**

- Xác định token TTL, audience, scopes và validation mode.
- Áp biện pháp revoke/introspection/status check hoặc giới hạn PEP theo năng lực và rủi ro.
- Theo dõi hành động từ client bị ảnh hưởng.
- Rotate/disable credentials và xử lý phiên/token liên quan.
- Kiểm token/secret cũ bị từ chối theo yêu cầu security.
- Cập nhật runbook incident và TTL policy phù hợp.

**Bài học:** **Credential rotation, token revocation và quyền hiệu dụng là ba việc khác nhau**.

## 39. Tình huống G: workload cần quyền khẩn cấp phục hồi

**Bối cảnh:** Job recovery chỉ chạy khi IdP bị sự cố. Vì ít dùng, đội kiểm toán đề xuất xóa service account; trong khi workload có role production cao và chỉ một kỹ sư cũ biết cách sử dụng.

**Cách quản trị:**

- Xác minh đây là emergency workload được phê duyệt, có owner và runbook.
- Kiểm hoạt động trong diễn tập thay vì chỉ dựa last-used.
- Giới hạn role/target và điều kiện kích hoạt.
- Bảo vệ credential, không để một nhân viên duy nhất giữ bí mật.
- Có incident/job correlation, native audit và hậu kiểm.
- Khi owner Leaver, thay owner và rotate/revoke credential từng được biết.
- Kết thúc phiên/job, thu hồi quyền tạm và kiểm readback.

**Bài học:** Account phục hồi hiếm dùng vẫn cần thiết có thể **KEEP theo căn cứ rõ**, không để thành admin mồ côi.

## 40. Câu hỏi tự kiểm tra

**Câu 1.** Non-human account có phải mọi tài khoản không có tên người dùng không?

**Gợi ý:** Không. Cần phân biệt identity của workload với account dùng chung cho nhiều người; đánh giá mục đích, cách xác thực và attribution.

**Câu 2.** Một service account có cần owner không?

**Gợi ý:** Có. NHA phải có technical/service owner chịu trách nhiệm quyền, credential, vòng đời, đặc biệt khi người tạo Leaver.

**Câu 3.** Khác nhau giữa NHI, account, credential và token?

**Gợi ý:** Identity nhận diện chủ thể, account là thực thể ở hệ thống, credential giúp xác thực, token là chứng thực truy cập được phát theo flow cụ thể.

**Câu 4.** Vì sao không nên dùng mật khẩu nhân viên cho cron job?

**Gợi ý:** Phụ thuộc JML người, dễ lộ, khó audit automation, quyền có thể quá rộng.

**Câu 5.** Managed identity có tự bảo đảm least privilege không?

**Gợi ý:** Không. Giảm quản lý secret tĩnh nhưng role/resource policy vẫn phải giới hạn.

**Câu 6.** Token OAuth Client Credentials có chứng minh nhân viên An trực tiếp phê duyệt request không?

**Gợi ý:** Không tự động. Token thường đại diện cho client/workload; cần audit nguồn kích hoạt/approval riêng.

**Câu 7.** Xóa Kubernetes Deployment có tự gỡ cloud IAM role không?

**Gợi ý:** Không; kiểm tất cả trust, principal và role/credential ngoài cluster.

**Câu 8.** Vì sao subject/audience của OIDC federation cần ràng buộc chặt?

**Gợi ý:** Để ngăn workflow/repository/workload không được phép đổi assertion thành credential đích.

**Câu 9.** Owner Mover nên xóa mọi service principal họ từng tạo không?

**Gợi ý:** Không. Chuyển owner, rà quyền quản lý human, credential exposure và dependency; retire workload riêng khi hết mục đích.

**Câu 10.** Rotation client secret có làm mọi JWT access token cũ hết hiệu lực ngay không?

**Gợi ý:** Không nhất thiết; tùy cơ chế validation/revoke và TTL.

**Câu 11.** Một bot cần đọc report tenant-A, có nên cấp `tenant.admin` không?

**Gợi ý:** Không; gán action/resource/scope tối thiểu và kiểm API theo tenant.

**Câu 12.** Một NHA không dùng sáu tháng có chắc nên xóa?

**Gợi ý:** Không. Có thể là backup/recovery dùng hiếm; cần review owner, purpose, dependency và risk.

**Câu 13.** Gỡ role từ IAM nhưng API vẫn trả PERMIT, bước tiếp theo?

**Gợi ý:** Kiểm direct grants, nested roles, token/session, cache và Resource Server; readback effective access.

**Câu 14.** Non-human identity cần đi qua browser SSO và MFA của nhân viên không?

**Gợi ý:** Không như một quy tắc chung; workload nên dùng cơ chế machine authentication phù hợp, còn human admin quản lý NHA bằng SSO/MFA theo policy.

## 41. Checklist quản lý Non-human accounts

- [ ] **Định nghĩa:** Đã phân biệt human account, shared admin và NHA thực sự?
- [ ] **Identity:** Mỗi workload có canonical ID, loại subject và account mapping?
- [ ] **Owner:** Có technical owner, business/data owner theo rủi ro và người dự phòng?
- [ ] **Purpose:** Có mô tả nhiệm vụ hiện hành, service catalog/deployment reference?
- [ ] **Inventory:** Bao phủ OAuth clients, cloud, CI/CD, Kubernetes, DB, integrations và local accounts?
- [ ] **Trust:** Issuer, audience, subject binding và nguồn credential đáng tin?
- [ ] **Authentication:** Không dùng password/session người cho automation khi có phương án tốt hơn?
- [ ] **Secrets:** Không commit hoặc ghi secret/token vào log, image, ticket?
- [ ] **Short-lived:** Cân nhắc managed identity/federation/short-lived credentials khi hỗ trợ?
- [ ] **RBAC/ABAC:** Role, action, tenant, project, audience và environment đúng scope?
- [ ] **Least privilege:** Không dùng global admin cho tác vụ đọc/đồng bộ đơn giản?
- [ ] **CI/CD:** Người sửa pipeline không thể gián tiếp chiếm quyền production ngoài policy?
- [ ] **Kubernetes:** ServiceAccount, token mounting, namespace và RBAC được giới hạn?
- [ ] **Rotation:** Có owner, lịch/sự kiện rotation, canary và test credential cũ bị từ chối?
- [ ] **Tokens:** Đã tính token/session/cache còn sống sau credential revoke?
- [ ] **SoD:** Quyền cấp credential, phê duyệt và audit có tách khi cần?
- [ ] **Joiner:** Người mới chỉ có quyền quản lý NHA đúng nhiệm vụ và đủ điều kiện?
- [ ] **Mover:** Reassign owner và gỡ quyền quản trị/secret access của người chuyển vai trò?
- [ ] **Leaver:** Disable human account không bị nhầm với revoke workload credentials?
- [ ] **Workload change:** Scope/tenant/environment được review khi dịch vụ thay đổi?
- [ ] **Decommission:** Xóa grant/account/credential ngoài runtime, không chỉ xóa Pod/job?
- [ ] **SCIM/IdP:** Hiểu giới hạn SCIM và SSO, không coi là bao phủ mọi machine principal?
- [ ] **Service principal:** Có role/action/resource hẹp và owner thật?
- [ ] **Privileged workload:** Áp JIT/JEA hoặc kiểm soát tương đương khi phù hợp?
- [ ] **Incident:** Có phương án secret exposure, token misuse và emergency revoke?
- [ ] **Monitoring:** Audit có workload/job/run ID, token issuance và API resource actions?
- [ ] **Readback:** Đã kiểm quyền hiệu dụng sau grant/rotation/revoke, kể cả negative tests?
- [ ] **Regrant:** Theo dõi IaC/controller hoặc directory đồng bộ cấp lại quyền cũ?
- [ ] **Exceptions:** Quyền chưa thu hồi có risk owner, bù trừ, hạn xử lý và review?
- [ ] **Privacy:** Audit không lưu dữ liệu cá nhân/secret dư thừa?
- [ ] **Coverage:** Chất lượng inventory và unknown-owner được báo cáo trung thực?
- [ ] **Kết luận:** NHA chỉ tồn tại khi còn mục đích, owner và quyền được xác minh hợp lệ?

## 42. Tổng kết

**Non-human account là tài khoản mà một workload, ứng dụng, dịch vụ, job hoặc thiết bị sử dụng để xác thực và truy cập hệ thống mà không cần người đăng nhập tương tác theo mỗi tác vụ**. Nó thuộc nhóm **non-human identities**, nhưng cần phân biệt rõ **identity logic, account tại target, credential, token, session và role/entitlement**.

NHA có thể là **OAuth client, service principal, managed identity, Kubernetes ServiceAccount, database service user, CI/CD identity, bot hoặc tài khoản của hệ thống backup/monitoring**. Để quản trị an toàn, mỗi chủ thể cần **mục đích, technical owner, danh mục tài nguyên, authentication trust, quyền tối thiểu, credential lifecycle, review, audit và khả năng deprovision có kiểm chứng**. **IdP/SSO, SCIM, cloud IAM, RBAC/ABAC và PAM/PIM** đóng những vai trò khác nhau, không thành phần nào tự bao phủ toàn bộ quyền NHA.

Với **Joiner–Mover–Leaver**, người phụ trách workload có thể thay đổi nhưng service vẫn cần hoạt động hợp lệ. Vì vậy cần **chuyển ownership, gỡ quyền quản lý của người không còn nhiệm vụ, đánh giá secret từng bị biết, rotate/revoke và đọc lại quyền target**, thay vì xóa bừa workload hoặc giữ account mồ côi. Khi chính workload nghỉ sử dụng, phải thu hồi **principal, role, ACL, token/credential và các đường cấp quyền còn lại**, đồng thời kiểm nguồn automation không tự tái cấp.

**NHA được quản lý tốt không chỉ là “tài khoản chạy được job”, mà là một danh tính phi con người có thể giải thích, giới hạn, kiểm toán và thu hồi được — để hệ thống hoạt động liên tục mà vẫn cấp đúng quyền và giảm quyền truy cập tồn dư.**
