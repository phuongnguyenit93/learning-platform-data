# Workload identity trong Service identity và quản lý vòng đời danh tính IAM

## 1. Workload identity là gì?

**Workload identity** là danh tính được cấp cho **một thực thể phần mềm đang thực thi tác vụ**: ứng dụng, microservice, container, pod, batch job, serverless function, pipeline CI/CD hoặc tác nhân tự động. Danh tính này cho phép hệ thống trả lời câu hỏi **“workload nào đang gọi tài nguyên?”** và quyết định workload đó được **xác thực, ủy quyền, ghi nhận hành vi và thu hồi** như thế nào.

Ví dụ, dịch vụ **payments-api** cần đọc một secret của chính nó và gửi message vào queue **payment-events**. Một thiết kế tốt cho phép instance của payments-api chứng minh danh tính workload rồi nhận credential ngắn hạn cho **đúng API, queue và phạm vi**. Không cần lưu mật khẩu của nhân viên trong container, không cần chia sẻ cloud-admin key cho mọi dịch vụ.

Trong mô-đun **SECURITY_IDENTITY_ACCESS_MANAGEMENT_IDENTITY_LIFECYCLE**, workload identity là một dạng **non-human identity (NHI)** nằm trong vòng đời IAM. Mô-đun tập trung **Joiner–Mover–Leaver (JML)**, từ xác minh, tạo account và cấp quyền đến rà soát, thu hồi khi vai trò hoặc quan hệ thay đổi; kết nối **IdP, SSO, SCIM, RBAC/ABAC, tài khoản dịch vụ, kiểm toán** và hạn chế **quyền truy cập tồn dư**. Với workload, vòng đời kỹ thuật của ứng dụng không giống hợp đồng lao động, nhưng **quan hệ giữa workload, chủ sở hữu và quyền được cấp** vẫn phải được quản trị.

### Mục tiêu học tập

Sau bài học, người đọc có thể:

1. Giải thích **workload identity**, phân biệt với service account, API key, OAuth client, human account và device identity.
2. Mô tả **chuỗi tin cậy** để workload nhận credential tạm và gọi hệ thống đích.
3. Hiểu **attestation, federation, Security Token Service (STS), issuer–subject–audience, mTLS** và credential ngắn hạn.
4. So sánh các cơ chế tiêu biểu như **OIDC workload federation**, **Kubernetes ServiceAccount token** và **SPIFFE/SPIRE** ở mức khái niệm.
5. Thiết kế quyền theo **least privilege, action–resource–context, RBAC/ABAC/PBAC** và phạm vi tenant.
6. Quản lý **workload lifecycle**, rotation, revocation, credential/session tồn dư và event tới sai thứ tự.
7. Xử lý ảnh hưởng của **Joiner–Mover–Leaver của human owner** mà không xóa nhầm workload sản xuất.
8. Thiết kế **audit, reconciliation, tests và incident response** cho danh tính máy.

## 2. Tại sao workload cần danh tính riêng?

Trong hệ thống phân tán, workload liên tục giao tiếp:

- Microservice gọi API nội bộ.
- Pod truy cập secret manager hoặc database.
- Pipeline CI/CD tải artifact rồi triển khai.
- Batch job xử lý dữ liệu theo lịch.
- Serverless function phát sự kiện.
- Agent giám sát đọc metrics hoặc log.
- Connector IAM/SCIM đồng bộ user và group.

Nếu tất cả sử dụng **một mật khẩu chung hoặc một access key dài hạn**, hệ thống khó phân biệt ai gọi, khó giới hạn phạm vi và khó thu hồi khi một service bị xâm nhập.

### Ví dụ thiết kế chưa tốt

~~~text
payments-api, reports-job, deployment-runner
        |
        +-- Cùng dùng SECRET_GLOBAL_ADMIN
        |
        +-- Truy cập mọi bucket, queue và database
~~~

Khi khóa lộ từ reports-job, kẻ tấn công có thể dùng quyền thuộc những dịch vụ khác. Thao tác trong audit có thể đều mang cùng tên **global-admin**.

### Thiết kế có tách danh tính

~~~text
payments-api    -> identity/payments-api    -> queue/payment-events:publish
reports-job     -> identity/reports-job     -> bucket/reports-approved:read
deployment-job  -> identity/deployment-job  -> app/payments:deploy
~~~

Các đường cấp quyền phải được thực thi bởi resource server hoặc platform IAM; chỉ đổi tên account mà tiếp tục gán quyền global-admin không cải thiện least privilege.

**Mục tiêu là tách định danh, giảm đặc quyền và giảm thời gian credential có hiệu lực**, đồng thời giữ khả năng truy vết từng workload và instance khi cần.

## 3. Phân biệt workload identity, service account và credential

| Khái niệm | Vai trò | Ví dụ | Không nên hiểu nhầm |
|---|---|---|---|
| **Workload** | Phần mềm đang chạy thực hiện tác vụ | Pod payments-api, serverless function | Một workload luôn là một VM cố định |
| **Workload identity** | Danh tính máy được xác minh và được tin cậy | service:payments-api trong trust domain | Bản thân nó là mật khẩu |
| **Service account** | Account kỹ thuật gắn với service, phạm vi phụ thuộc nền tảng | Kubernetes ServiceAccount, SaaS technical user | Account luôn có credential tĩnh |
| **OAuth client** | Ứng dụng được đăng ký với authorization server | client_id=reports-batch | client_id công khai là chứng cứ xác thực |
| **Credential** | Bằng chứng workload có thể dùng để xác thực | JWT, certificate, short-lived token | Credential luôn chứng minh quyền đúng mãi |
| **Access token** | Credential cho resource server/API | Token có audience và scope | Có thể gửi tới API bất kỳ |
| **Cloud role / permission** | Quyền được thực thi trên resource | object.read cho bucket A | Role là chính workload identity |
| **Device identity** | Danh tính thiết bị/vật thể phần cứng | Máy POS, gateway | Tương đương container identity |
| **Human identity** | Danh tính một người và quan hệ nhân sự | person-2046 | Có thể dùng thay cho bot mà không ảnh hưởng audit |

**Service account là một cách hiện thực danh tính kỹ thuật**, còn **workload identity** nhấn mạnh việc gắn quyền xác thực với workload thực thi và **căn cứ tin cậy**. Một Kubernetes ServiceAccount có thể làm cơ sở cho workload identity, nhưng không phải mọi service account đều có cơ chế attestation và token ngắn hạn.

### Identity khác account và principal

Một workload logical như **payments-api** có thể có nhiều **instance/pod**. Chúng có thể cùng thuộc một **service identity** cho phép đọc cấu hình, nhưng cần phân biệt instance, environment hoặc tenant khi policy/risk yêu cầu. Principal là thực thể mà policy engine sử dụng để quyết định quyền; nó có thể đại diện cho workload logical, một service account, hoặc một phiên được chứng thực.

## 4. Các loại workload và trust boundary

| Loại workload | Môi trường | Nguồn chứng cứ danh tính có thể dùng | Rủi ro cần xét |
|---|---|---|---|
| **Microservice container** | Kubernetes hoặc container platform | ServiceAccount token, SPIFFE SVID, runtime attestation | Pod giả mạo, token bị đọc, RBAC rộng |
| **VM application** | Máy ảo/cloud | Instance identity, metadata credential, certificate | Metadata abuse, credential reuse |
| **Serverless function** | FaaS | Platform execution identity/role | Quyền dùng chung giữa functions |
| **CI/CD job** | Runner/pipeline | OIDC job assertion, workload federation | Fork/PR không tin cậy, claim quá rộng |
| **Batch/cron** | Scheduler | Workload identity bound to job/runtime | Secret nằm trong script hoặc log |
| **Edge/IoT gateway** | Thiết bị ngoài datacenter | Hardware-backed key, device enrollment | Thiết bị thất lạc, clone key |
| **SaaS integration** | Bên thứ ba | OAuth client credentials, certificate, vendor token | Scope quá rộng, khó thu hồi |
| **Monitoring/backup agent** | Host/cluster | Agent identity/managed identity | Quyền đọc dữ liệu nhạy cảm và backup |

### Không tự tin cậy chỉ vì workload ở mạng nội bộ

**IP nội bộ, namespace, container label hoặc hostname không phải bằng chứng xác thực mạnh theo mặc định.** Một attacker trong cluster có thể giả thông tin network, chiếm token hoặc lợi dụng misconfiguration. Danh tính workload cần được gắn với **chứng cứ không thể chỉ tự khai** và được policy engine/resource server xác minh.

### Trust boundary quan trọng

- Giữa **CI/CD runner và cloud production**.
- Giữa **Kubernetes namespace A và namespace B**.
- Giữa **tenant A và tenant B**.
- Giữa **service mesh và ứng dụng không tham gia mesh**.
- Giữa **production và staging/development**.
- Giữa **workload identity provider và hệ thống cấp quyền đích**.

Danh tính có cùng tên trong hai môi trường không tự phải được coi là cùng một principal được ủy quyền.

## 5. Chuỗi tin cậy của workload identity

Một mô hình tổng quát:

~~~mermaid
flowchart LR
    W[Workload instance] --> EV[Chứng cứ nền tảng / attestation]
    EV --> ISS[Issuer / Workload identity provider]
    ISS --> ASS[Assertion ngắn hạn]
    ASS --> STS[STS hoặc token exchange]
    STS --> CRED[Credential cho resource đích]
    CRED --> API[Resource Server / API]
    API --> POL[Authorization: action, resource, context]
    POL --> AUD[Audit và reconciliation]
    OWNER[Workload registry + owner + JML] --> POL
    OWNER --> ISS
~~~

Quy trình cụ thể có thể không có đủ mọi bước: một nền tảng có thể cấp credential trực tiếp thay vì qua token exchange, hoặc service mesh dùng **X.509-SVID/mTLS** mà không cần OAuth access token cho mỗi request.

### Bốn câu hỏi kiểm tra chuỗi tin cậy

1. **Ai phát hành chứng cứ danh tính?** Issuer có được cấu hình tin cậy không?
2. **Chứng cứ ràng buộc với workload nào?** Subject có đủ phân biệt namespace, app, môi trường và nguồn runtime không?
3. **Resource đích xác thực chứng cứ ra sao?** Chữ ký/certificate chain, audience, issuer, expiry, revocation và trust policy.
4. **Workload được quyền làm gì?** Resource/action scope, policy và trạng thái lifecycle có được thực thi?

**Xác thực được workload không đồng nghĩa workload có mọi quyền**. STS hoặc Identity Provider có thể phát credential hợp lệ, nhưng authorization vẫn phải giới hạn theo grant và resource.

## 6. Workload attestation và registration

**Workload attestation** là quá trình một thành phần tin cậy kiểm tra **thuộc tính của tiến trình hoặc môi trường thực thi** trước khi xác nhận danh tính. Tùy nền tảng, nó có thể dựa trên:

- Kubernetes ServiceAccount và thông tin pod từ control plane.
- Node identity, namespace, pod UID và runtime metadata.
- VM instance identity và metadata có chữ ký của platform.
- CI/CD job identity gắn repository, workflow, ref hoặc environment.
- Attestation của TEE/hardware khi được hỗ trợ.
- Quy tắc đăng ký service, deployment và workload owner trong registry.

### Điều cần phân biệt

**Attestation không đồng nghĩa bảo đảm code không có lỗ hổng.** Một pod thật sự được deploy từ môi trường hợp lệ vẫn có thể chạy image bị nhiễm độc, bị chiếm tiến trình hoặc dùng package nguy hiểm.

**Attestation không nên chỉ dựa vào self-reported environment variables.** Nếu workload có thể tự ghi claim **isProduction=true** và issuer tin điều đó, attacker có thể tự nâng quyền.

### Workload registry

Một registry quản lý nên có:

~~~json
{
  "workloadId": "service:payments-api",
  "ownerTeamId": "payments-platform",
  "environment": "production",
  "namespace": "payments",
  "runtimePlatform": "kubernetes",
  "serviceAccount": "payments-api",
  "trustDomain": "prod.example.org",
  "purpose": "Xử lý yêu cầu thanh toán",
  "status": "ACTIVE",
  "approvedResourceScopes": [
    "queue:payment-events:publish",
    "secret:payments-api-config:read"
  ],
  "reviewDueAt": "2027-02-01T00:00:00Z"
}
~~~

Đây là **schema nội bộ minh họa**, không phải API bắt buộc của SPIFFE, Kubernetes hay SCIM. **Registry là căn cứ quản trị**, còn việc workload chứng minh đang thực thi đúng deployment phải do cơ chế nền tảng tin cậy thực hiện.

## 7. Subject, issuer, audience và các claims quan trọng

Trong OIDC hoặc JWT-based workload federation, cần hiểu những thành phần thường gặp:

| Thành phần | Ý nghĩa | Kiểm tra thiết yếu |
|---|---|---|
| **iss** | Đơn vị phát hành assertion/token | Chính xác issuer được trust policy cho phép |
| **sub** | Định danh subject trong namespace của issuer | Khớp workload/repository/ServiceAccount được phép |
| **aud** | Đối tượng mà token hướng tới | Chỉ đúng STS/API đích được chỉ định |
| **exp** | Thời điểm hết hạn | Chưa hết hạn theo clock đáng tin |
| **nbf / iat** | Thời gian bắt đầu phát biểu/phát hành | Chống token tương lai/lỗi thời theo policy |
| **jti** | Định danh token khi issuer cung cấp | Có thể hỗ trợ phát hiện replay nếu có state phù hợp |
| **kid** | Khóa dùng ký token | Chọn đúng khóa trong JWKS tin cậy |
| **repository / workflow / ref** | Claims đặc thù pipeline issuer | Kiểm với định dạng và nguồn được bảo đảm |
| **namespace / service account** | Claims đặc thù môi trường | Ràng buộc đúng cluster/issuer và workload |

**Không phải token nào cũng có toàn bộ claims trên.** Cấu trúc và bảo đảm của claim tùy issuer. Không được dùng một trường thiếu bằng chứng trust như **repository_name** do client tự gửi để kết luận quyền production.

### Ví dụ assertion payload minh họa

~~~json
{
  "iss": "https://issuer.ci.example.org",
  "sub": "repo:example/payments:environment:production",
  "aud": "sts.production.example.org",
  "iat": 1795395600,
  "nbf": 1795395600,
  "exp": 1795396200,
  "repository": "example/payments",
  "environment": "production",
  "workflow": "deploy-payments"
}
~~~

Các thời điểm Unix là **giá trị giả định**. Payload này **không phải một JWT đã ký** và không chứng minh bất kỳ deployment thật nào; resource server chỉ nên tin claim sau khi xác minh toàn bộ token và trust configuration.

### Subject phải đủ hẹp

Một trust policy chỉ cho phép **mọi repository thuộc organization** có thể quá rộng đối với role deploy production. Chính sách nên kiểm chính xác **issuer, subject và điều kiện workflow/environment/ref** theo khả năng của provider.

## 8. OIDC workload identity federation: không lưu cloud key dài hạn

**Workload identity federation** cho phép workload có assertion từ một **identity provider được tin cậy**, sau đó trao đổi assertion lấy credential ngắn hạn mà tài nguyên đích chấp nhận.

### Luồng khái quát

~~~mermaid
sequenceDiagram
    participant JOB as CI Job / Workload
    participant ISS as OIDC Issuer
    participant STS as STS / Cloud Token Service
    participant API as Target API
    JOB->>ISS: Xin assertion cho audience đã định
    ISS-->>JOB: Assertion có issuer, subject, audience, expiry
    JOB->>STS: Trình assertion / federation request
    STS->>STS: Kiểm signature, issuer, aud, sub, trust policy
    STS-->>JOB: Credential scoped có thời hạn
    JOB->>API: Gọi action bằng credential đích
    API->>API: Kiểm audience, scope, role và resource
    API-->>JOB: Kết quả / Deny
~~~

### Lợi ích

- Giảm yêu cầu lưu **long-lived client secret/cloud access key** trong pipeline.
- Cấp credential theo **job/instance và thời hạn**.
- Có thể ràng buộc **repository, branch/tag/environment, audience và workflow**.
- Quản trị quyền bằng **trust policy + resource policy**.
- Thu hồi trust của một nguồn có thể chặn việc **phát credential mới**.

### Giới hạn quan trọng

- Credential được cấp trước khi trust bị thu hồi có thể **tiếp tục hợp lệ đến expiry**, tùy provider và API.
- Nếu trust policy có wildcard quá rộng, nhiều workload không mong muốn vẫn có thể đổi credential.
- Assertion bị lộ trong thời hạn hiệu lực có nguy cơ bị dùng lại nếu không có biện pháp chống replay/binding phù hợp.
- Một job hợp lệ nhưng code bị xâm nhập vẫn có thể lạm dụng quyền trong phạm vi grant.
- Một số cloud hoặc SaaS không hỗ trợ federation phù hợp; cần lựa chọn credential và kiểm soát thay thế.

**Federation giảm phụ thuộc vào secret dài hạn; không tự loại bỏ authorization, supply-chain security hoặc vận hành thu hồi.**

## 9. STS, token exchange và credential đích

**Security Token Service (STS)** kiểm chứng chứng cứ từ một trust domain rồi phát hành credential theo policy cho trust domain/resource khác. Trong các kiến trúc OAuth, **token exchange** có thể liên quan cơ chế chuẩn hóa như OAuth 2.0 Token Exchange; trong các cloud platform, quy trình federation và API có **hợp đồng riêng**.

Một quyết định cấp credential cần dựa trên:

~~~text
permitCredentialIssuance if
    assertion.signatureValid
    and assertion.issuer in trustedIssuers
    and assertion.audience == configuredSTS
    and assertion.subject matches approvedWorkloadBinding
    and assertion.isWithinValidityWindow
    and workloadRegistry.status == ACTIVE
    and requestedTargetRole is approvedForWorkload
    and requestedScope doesNotExceedApprovedScope
else deny
~~~

Đây là **giả mã**, không phải cú pháp tiêu chuẩn của cloud IAM.

### Ba loại quyền phải phân biệt

1. **Quyền lấy assertion:** workload được issuer phát chứng cứ.
2. **Quyền trao đổi assertion:** STS cho phép subject/issuer đó nhận credential đích.
3. **Quyền truy cập tài nguyên:** credential đích chỉ cho các action/resource được cấu hình.

Một lỗi ở tầng 2 có thể phát credential cho workload sai. Một lỗi ở tầng 3 có thể cho credential hợp lệ truy cập phạm vi quá lớn. **Cả ba đều cần policy và audit riêng**.

## 10. OAuth 2.0 client credentials và workload identity

Một service có thể dùng **OAuth 2.0 Client Credentials Grant** để xin access token khi tự hành động, không nhân danh một user cụ thể. Trong thiết kế này:

- **client_id** xác định OAuth client trong authorization server.
- Client cần **phương thức xác thực hoặc chứng cứ phù hợp**, chẳng hạn secret, private-key JWT, mTLS hoặc cơ chế federation tùy hệ thống.
- Authorization server cấp **access token** theo scope/audience và policy.
- Resource server xác minh token và **authorization trên resource/action**.

~~~mermaid
sequenceDiagram
    participant S as Service A
    participant AS as Authorization Server
    participant RS as Resource Server B
    S->>AS: Client authentication + token request
    AS->>AS: Kiểm workload/client và policy
    AS-->>S: Access token scoped
    S->>RS: API request + access token
    RS->>RS: Validate token + authorization
    RS-->>S: Permit/Deny + response
~~~

### Client credentials không phải delegated human identity

Một token phát cho **workload** không tự chứng minh “người Lan đã phê duyệt thanh toán”. Nếu API yêu cầu **human accountability** và dynamic SoD, ứng dụng phải có cơ chế xác minh **actor con người và authority/approval phù hợp**, không coi client token có scope rộng là giấy phép thay người thực hiện mọi nghiệp vụ.

### Không nhầm ID token và access token

**OIDC ID token** chủ yếu phục vụ client xác minh sự kiện đăng nhập/định danh được issuer khẳng định theo flow tương ứng. **OAuth access token** là credential đưa tới resource server. Một ID token có audience là client không nên được gửi như bearer token cho API khác chỉ vì nó cũng là JWT hợp lệ.

## 11. Kubernetes ServiceAccount và bound projected token

Trong Kubernetes, **ServiceAccount** là identity thuộc namespace được pod/workload sử dụng khi giao tiếp với Kubernetes API hoặc làm cơ sở để workload federation. Kubernetes có thể cung cấp **projected ServiceAccount token** qua cơ chế được runtime cập nhật và có các thuộc tính như **audience, expiry, binding với pod** theo phiên bản/cấu hình nền tảng.

### Ví dụ Pod sử dụng projected token riêng

~~~yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: payments-api
  namespace: payments
---
apiVersion: v1
kind: Pod
metadata:
  name: payments-api-example
  namespace: payments
spec:
  serviceAccountName: payments-api
  automountServiceAccountToken: false
  containers:
    - name: app
      image: registry.example.org/payments-api:1.2.3
      volumeMounts:
        - name: identity-token
          mountPath: /var/run/workload
          readOnly: true
  volumes:
    - name: identity-token
      projected:
        sources:
          - serviceAccountToken:
              path: token
              audience: sts.production.example.org
              expirationSeconds: 3600
~~~

Đây là **ví dụ cấu hình kiến trúc**, không phải hướng dẫn có thể áp cho mọi cluster/STS. Registry, image và audience là giả định. Việc đặt **automountServiceAccountToken: false** rồi mount rõ volume projected giúp tránh mặc định cấp token Kubernetes API không cần thiết cho workload, nhưng ứng dụng phải thực sự đọc token được mount và bên nhận phải **xác thực đúng issuer/audience/subject**.

### Các lưu ý thiết kế

1. **ServiceAccount nằm trong namespace**, nhưng token còn cần được xác minh theo **cluster/issuer/trust policy**.
2. ServiceAccount có thể có **RBAC tới Kubernetes API**; không tự động có quyền cloud hay SaaS nếu chưa có federation/mapping.
3. **Không cho mọi pod dùng default ServiceAccount** với quyền rộng.
4. Dùng **audience chuyên biệt cho target**; token dành STS không nên được dùng như token của API bất kỳ.
5. Token projected có thời hạn và kubelet có thể làm mới; workload cần **xử lý rotation và cache** phù hợp.
6. Tránh sao chép token vào environment variable, log, artifact hoặc image.
7. Kiểm các quyền nguy hiểm như **create pods, read secrets, impersonate users, modify RBAC**.
8. Việc xóa pod hoặc ServiceAccount không mặc nhiên thu hồi mọi **credential đích đã được STS phát**.

**Bound token giảm khả năng tái sử dụng và giúp liên kết chứng cứ với đối tượng runtime** nhưng không ngăn hoàn toàn việc token bị lấy cắp và sử dụng trong thời hạn hiệu lực nếu bên nhận không có kiểm soát bổ sung.

## 12. SPIFFE/SPIRE và danh tính workload xuyên nền tảng

**SPIFFE** đưa ra mô hình định danh workload có thể liên thông trong môi trường đa nền tảng. Một **SPIFFE ID** là URI thể hiện danh tính, ví dụ:

~~~text
spiffe://prod.example.org/ns/payments/sa/payments-api
~~~

Trong ví dụ:

- **prod.example.org** là trust domain.
- Phần đường dẫn có thể mô tả namespace/workload theo quy ước của tổ chức.
- Cấu trúc sau trust domain là **tên định danh được vận hành quản trị**, không tự chứng minh đây là pod hợp lệ.

**SPIFFE Verifiable Identity Document (SVID)** là chứng cứ danh tính theo SPIFFE. Những dạng phổ biến:

- **X.509-SVID:** certificate mang SPIFFE ID trong SAN URI, dùng cho mTLS.
- **JWT-SVID:** JWT mang SPIFFE identity và audience theo quy tắc xác minh tương ứng.

**SPIRE** là một triển khai của các ý tưởng SPIFFE, cung cấp cơ chế registration, node/workload attestation và cấp/phân phối SVID. Nó không tự thay thế authorization policy của ứng dụng.

### Luồng khái quát

~~~mermaid
flowchart LR
    W[Workload process] --> AG[SPIRE Agent / Workload API]
    AG --> AT[Node and workload attestation]
    AT --> SV[SPIRE Server / Registration]
    SV --> SVID[Issued SVID]
    SVID --> TLS[Service-to-service mTLS / JWT validation]
    TLS --> AUTHZ[Authorization policy + resource scope]
    AUTHZ --> AUDIT[Audit]
~~~

### Điểm cần kiểm tra

- **Trust domain** đúng và có trust bundle/certificate chain hợp lệ.
- SPIFFE ID khớp policy của service, không chỉ regex quá rộng.
- SVID có hiệu lực và được rotate đúng.
- Kênh nhận SVID không cho workload khác giả mạo caller.
- Với federation giữa trust domains, **federation bundle và trust relationships** phải được quản trị riêng.
- Có policy **deny by default** cho service identity chưa được ủy quyền.
- Khi workload bị retire, phải ngừng cấp SVID mới và xử lý những kết nối/credential còn sống theo thiết kế.

### SPIFFE không đồng nghĩa service mesh

Một service mesh có thể sử dụng SPIFFE/SPIRE để xác thực service-to-service; nhưng **SPIFFE là mô hình danh tính**, không phải một authorization engine hay toàn bộ service mesh.

## 13. mTLS: xác thực cả hai phía của kết nối

**Mutual TLS (mTLS)** cho phép client và server cùng xác minh certificate của nhau. Trong hệ thống workload identity, certificate có thể mang định danh service hoặc SPIFFE ID.

### mTLS giúp gì?

- Server xác minh **client workload identity** thay vì chỉ tin địa chỉ IP.
- Client xác minh **server đích**, giảm nguy cơ gửi dữ liệu sang endpoint giả.
- Kênh truyền được mã hóa và xác thực theo cấu hình TLS.
- Certificate ngắn hạn có thể giảm vòng đời secret dài hạn.

### mTLS không tự quyết định quyền nghiệp vụ

Một workload được xác thực là **reports-job** chưa chắc có quyền gọi **payment.refund**. Resource server vẫn cần:

~~~text
permit if
    peer.workloadIdentity == "service:reports-job"
    and action == "report.generate"
    and resource.tenantId in workload.approvedTenants
    and workload.lifecycleState == ACTIVE
    and servicePolicyVersion is current
else deny
~~~

Đây là giả mã, không phải cú pháp mTLS/TLS. TLS chỉ chứng minh kết nối theo certificate; **RBAC/ABAC/PBAC và target-specific permission** quyết định action.

### Hạn chế thực tế

- Kết nối TLS đã thiết lập có thể tồn tại tới khi đóng; việc thu hồi certificate/role không phải luôn khiến mọi kết nối đang mở bị cắt ngay.
- Certificate revocation, TTL, trust bundle rotation và reload behavior khác nhau theo stack.
- Nếu proxy/service mesh là điểm kiểm mTLS, cần bảo vệ **header identity** khi chuyển tới backend, chống client giả mạo header ngoài trust boundary.
- Một số backend vẫn cần kiểm **object-level authorization** vì mTLS chỉ định danh service gọi.

## 14. Cloud workload identity và role binding

Các cloud platform cung cấp cơ chế **execution identity, instance role, managed identity hoặc workload federation**. Tên và API khác nhau; ý tưởng chung là workload được cấp credential từ nền tảng thay vì lưu cloud key dài hạn.

### Cách thiết kế theo chức năng

| Mục tiêu | Cơ chế khái niệm | Kiểm soát |
|---|---|---|
| VM gọi object storage | VM/instance identity → temporary credential | Role gắn đúng instance/service, scope bucket |
| Kubernetes Pod gọi cloud API | ServiceAccount/OIDC assertion → federated credential | Issuer, subject, audience, namespace |
| Serverless function đọc secret | Execution role/managed identity | Secret scope, function isolation |
| CI/CD deploy production | CI OIDC job assertion → production role | Repository, environment, ref, workflow và approval |
| Cross-cloud job | Federated trust với identity nguồn | Trust domain, scope, TTL, audit |
| Service A gọi Service B | mTLS hoặc access token scoped | Audience/peer identity và API authorization |

### Những điều thường bị bỏ qua

1. **Trust policy cấp quyền nhận role** khác với **permission policy của role**.
2. Một workload có thể lấy role hợp lệ nhưng role vẫn có quyền quá rộng.
3. Nếu nhiều service cùng dùng một execution identity, khó tách **blast radius**.
4. Credential phát từ role có thể tồn tại sau khi workload hoặc role binding bị thay đổi, tùy provider.
5. Resource-based policies có thể cấp quyền thêm ngoài identity-based role.
6. Nguyên tắc **deny/least privilege** phải xét quyền hiệu lực cuối cùng, không chỉ policy tên gần đúng.
7. Không giả định **staging** và **production** có thể chia sẻ cùng role/issuer trust mà không làm tăng rủi ro.

**Không đồng nhất khả năng lấy credential với việc được phép gọi mọi resource cloud.**

## 15. CI/CD workload identity: tránh khóa cloud trong repository

Pipeline là nơi workload identity có tác động lớn vì nhiều tổ chức từng lưu **cloud access key dài hạn** trong CI secrets.

### Luồng an toàn hơn

1. Runner tạo **job identity** được CI platform xác thực.
2. Job lấy **OIDC assertion có audience dành cho STS**.
3. STS kiểm issuer, subject và các claims được policy tin cậy.
4. STS cấp **credential ngắn hạn cho deploy role hẹp**.
5. Job chỉ triển khai đúng project/service/environment đã duyệt.
6. Audit liên kết action với **repository, job, commit, artifact và actor/phê duyệt**.
7. Khi job kết thúc, credential hết hạn và không còn lưu trong artifact/log.

### Trust policy mẫu, không phụ thuộc vendor

~~~yaml
trustedIssuer: https://issuer.ci.example.org
allowedSubject: repo:example/payments:environment:production
audience: sts.production.example.org
conditions:
  repository: example/payments
  environment: production
  workflow: deploy-payments
targetRole: payments-production-deployer
maxCredentialLifetimeSeconds: 1800
allowedActions:
  - deployment.deploy
  - deployment.rollback
resourceScope:
  service: payments
  environment: production
~~~

Đây là **ngôn ngữ policy minh họa nội bộ**, không phải cấu hình có thể dán trực tiếp vào một cloud vendor. Claim names, format subject và mức đảm bảo phải xác minh theo tài liệu của chính issuer.

### Rủi ro đặc biệt

- **Pull request hoặc fork không tin cậy** chạy code có quyền lấy production assertion.
- Policy tin **repository** mà không xét **environment/ref/workflow**.
- Attacker thay workflow file rồi vẫn có được role production.
- Artifacts không được bảo vệ integrity, dẫn đến triển khai code không mong muốn.
- Reusable workflow hoặc runner chia sẻ làm mất tính phân tách.
- Job log in raw token hoặc tạo artifact chứa credential.
- Người author release đồng thời có thể tự **approve** và triển khai trái SoD.

**Workload identity không thay thế kiểm soát supply chain hoặc approval độc lập.** Phải tách **ai được phát credential** khỏi **ai được release artifact**, và kiểm soát cả hai.

## 16. Service-to-service authorization: danh tính không phải quyền

Giả sử **orders-api** gọi **payments-api**. mTLS có thể xác nhận orders-api đang gọi, nhưng payments-api vẫn cần kiểm:

- **Action:** create-payment, read-payment, refund-payment.
- **Resource:** order/payment thuộc tenant nào, owner nào.
- **Scope:** orders-api được tạo payment cho project/tenant được giao không.
- **Context:** request có mối liên hệ với order hợp lệ, chống replay/idempotency.
- **Delegation:** có acting-on-behalf-of user không, user nào.
- **Rate/amount limits** và SoD nếu action nhạy cảm.
- **Lifecycle:** workload vẫn ACTIVE, trust và role mapping hiện hành.

~~~mermaid
sequenceDiagram
    participant O as orders-api
    participant P as payments-api
    participant AUTH as Authorization policy
    participant DB as Payments datastore
    O->>P: mTLS + POST payment(orderId, tenant)
    P->>AUTH: Peer ID, action, resource, context
    AUTH->>AUTH: Trust + workload scope + business checks
    AUTH-->>P: Permit hoặc Deny
    alt Permit
        P->>DB: Validate order/payment và transaction
        DB-->>P: Result
        P-->>O: Operation result
    else Deny
        P-->>O: Forbidden
    end
~~~

### Confused deputy

**Confused deputy** xảy ra khi một service có quyền cao bị service/quá trình khác lợi dụng để thực hiện action không được phép. Ví dụ reports-api có quyền đọc cả hai tenant, nhưng client tenant A đưa một **resourceId thuộc tenant B** và reports-api đọc hộ.

Phòng tránh:

1. Xác minh danh tính **caller và workload**.
2. Ràng buộc **resource ownership/tenant** từ dữ liệu đáng tin.
3. Không mặc định workload có global privilege vì “backend nội bộ”.
4. Dùng access token có **audience và phạm vi đúng API**.
5. Phân biệt **workload authority** với **delegated user authority**.
6. Kiểm object-level authorization, không chỉ route-level role.

## 17. Delegation và “on behalf of” user

Một workload có thể hoạt động **tự chủ** hoặc **thay mặt người dùng**:

| Trường hợp | Chủ thể chịu trách nhiệm | Điều cần phân biệt |
|---|---|---|
| **Batch job định kỳ** | Workload + owner tổ chức | Không có user tương tác hiện tại |
| **User kích hoạt thao tác qua API** | User + service đang thực thi | Cần trace cả actor và workload |
| **OAuth delegated call** | User được ủy quyền, client làm trung gian | Scope người dùng và client đều bị giới hạn |
| **Service-to-service nội bộ** | Caller workload | Không tự suy ra quyền của một human user |
| **CI/CD deploy** | Pipeline workload + change approver | SoD giữa author, approver, deployer |

### Quy tắc hạn chế “mượn quyền”

Không cho service A truyền tự do header **X-User-Id** rồi service B coi header đó là danh tính được xác thực. Nếu dùng identity propagation qua gateway hoặc service mesh, cần **trust boundary rõ, integrity protection và khả năng xác minh**.

Một workload có quyền tạo báo cáo không nhất thiết có quyền **xem mọi báo cáo của mọi user**. Khi gọi “on behalf of” phải áp **intersection hoặc delegation policy phù hợp**, không tự cộng quyền workload và user để mở rộng quyền.

### Audit cả hai phía

Sự kiện nhạy cảm nên ghi **workload principal, human actor (nếu có), delegated authority, target resource, action và outcome**, nhưng không log bearer token hoặc secret.

## 18. Least privilege cho workload: action, resource, environment và time

Một workload cần ít quyền nhất cho mục đích đã duyệt.

\[
WorkloadGrant=(Identity,\ Actions,\ ResourceScope,\ Environment,\ Time,\ Conditions)
\]

Ví dụ:

| Workload | Quyền quá rộng | Quyền hẹp hơn |
|---|---|---|
| **payments-api** | Cloud project owner | publish message vào payment-events, đọc secret config của service |
| **reports-job** | Storage admin tất cả buckets | object.read ở prefix reports/approved |
| **backup-agent** | Database superuser | backup-related permission có kiểm soát |
| **monitoring-agent** | Cluster-admin | read metrics/log namespace phù hợp |
| **CI deployer** | Global deployment administrator | deploy một service trong environment được duyệt |
| **data-ingest** | Data warehouse admin | append vào bảng/dataset chỉ định |

### Cách giảm role explosion

Thay vì tạo một role mới cho từng container instance, có thể dùng **logical service identity** với **resource-scoped policy**, hoặc dùng thuộc tính environment/namespace để quyết định phạm vi nếu engine hỗ trợ.

Tuy nhiên, **không gộp nhiều workload có mục đích khác nhau thành một identity** chỉ để giảm số role. Tách danh tính giúp truy vết, rotation và containment khi một workload bị xâm nhập.

### Deny mặc định

Nếu workload chưa đăng ký, đã retire, thiếu owner, identity issuer không đáng tin hoặc yêu cầu vượt scope, **không tự cấp quyền nhạy cảm**. Một ngoại lệ phải có owner, thời hạn và phương án xử lý rõ.

## 19. PBAC/ABAC/RBAC cho workload identity

Danh tính workload là đầu vào của **authorization policy**, không phải toàn bộ quyết định.

- **RBAC:** service identity thuộc role nào và role có permission gì.
- **ABAC:** environment, namespace, project, tenant, resource classification, thời gian.
- **PBAC:** tổng hợp rules, deny guardrails và quyết định.
- **ReBAC:** workload có quan hệ với project, service owner hoặc repository nào.

### Ví dụ policy khái niệm

~~~text
permit if
    peer.workloadId == "service:payments-api"
    and peer.environment == "production"
    and workloadRegistry[peer.workloadId].state == ACTIVE
    and action == "queue.message.publish"
    and resource.queueId == "payment-events"
    and resource.tenantId in workload.approvedTenants
    and credential.issuer is trusted
    and credential.audience == thisResourceServer
    and credential.isWithinValidityWindow
    and not policy.hasMandatoryDeny
else deny
~~~

Đây là **giả mã**. Không phải mọi token có cùng claims, và không nên coi **peer.environment** là tin cậy nếu nó chỉ do client gửi.

### Chặn xung đột quyền

Một service identity có thể được cấp cả **security.policy.edit** và **security.policy.publish**. Khi tổ chức yêu cầu **dual control**, workload phải được kiểm SoD ở các bước thực thi; pipeline có thể cần phê duyệt từ người độc lập, kể cả khi workload credential hợp lệ.

## 20. Vòng đời riêng của workload: Create–Activate–Change–Retire

Workload không có “ngày tuyển dụng” như nhân viên. Một mô hình vòng đời riêng:

~~~mermaid
stateDiagram-v2
    [*] --> Proposed
    Proposed --> Registered: Owner + purpose + identity mapping
    Registered --> Eligible: Security review + policy approved
    Eligible --> Active: Deployment + attestation + credential issuance
    Active --> Changed: Release, scope, owner hoặc environment đổi
    Changed --> Active: Revalidate và cấp lại credential hợp lệ
    Active --> Suspended: Incident / trust failure
    Suspended --> Active: Approved recovery + re-attestation
    Active --> Retiring: Service sunset / migration
    Suspended --> Retiring: Retire sau điều tra
    Retiring --> Retired: Revoke, deprovision, verify
    Retired --> [*]
~~~

### Bước 1 — Register

- Định danh **workload logical** bằng ID ổn định có namespace.
- Khai **owner team, mục đích, repo/deployment nguồn và environment**.
- Chỉ định **issuer, trust domain** và phương thức attestation dự kiến.
- Xác định **action/resource scope** cần thiết.
- Xác định **review cycle, expiry hoặc trigger retire**.

### Bước 2 — Activate

- Deployment/instance được nền tảng chứng thực.
- STS/issuer kiểm binding rồi cấp credential ngắn hạn.
- Resource server chỉ Permit những action hợp lệ.
- Ghi evidence cấp phát, không log credential.

### Bước 3 — Change

- Khi đổi namespace, repository, owner, runtime hoặc resource scope, **đánh giá lại trust policy**.
- Không chỉ đổi tên identity và giữ quyền cũ theo đường legacy.
- Cập nhật role mapping và negative tests.

### Bước 4 — Retire

- Ngừng cấp credential mới.
- Thu hồi role, trust relationship và secrets liên quan.
- Xử lý credentials đã phát, sessions và target permissions.
- Đọc lại trạng thái quyền để xác minh không còn access không hợp lệ.

## 21. Ownership, sponsorship và JML của người phụ trách

Một workload thường có **owner team**, đôi khi có technical owner là một người. Khi người đó **Joiner–Mover–Leaver**, cần phân biệt **vòng đời human** với **vòng đời workload**.

### Joiner của người phụ trách

Nhân viên mới vào đội Platform có thể được cấp quyền **quản trị workload registry, deployment và secret** theo nhiệm vụ; điều đó **không tự làm workload nhận thêm quyền runtime**. Quyền thao tác của nhân viên và quyền của service identity là hai tập permission khác nhau.

### Mover của owner

Kỹ sư từ Payments chuyển sang Analytics:

- Gỡ quyền cá nhân trên deployment, secret manager và trust policy của Payments.
- Cập nhật owner registry nếu đội quản lý thay đổi.
- Rà soát quyền của workload nếu service chuyển đội hoặc mục đích.
- Xử lý credentials người cũ có thể đã biết.
- Kiểm SoD và quyền approve/release sau thay đổi.

### Leaver của owner

Khi owner là nhân viên nghỉ việc, **không tự xóa payments-api production chỉ vì người quản lý nghỉ**. Cần:

1. Chấm dứt **human privileged access** và những credential riêng của người đó.
2. **Chuyển ownership** cho một team/người có thẩm quyền.
3. Đối chiếu workload registry, secret access, approval route và incident escalation.
4. **Rotate hoặc revoke secrets** mà cá nhân có thể đã biết, theo rủi ro.
5. Rà soát workload identity grants có còn phục vụ mục đích hợp lệ.
6. Xác minh account/token/role của người đã Leaver không thể điều khiển workload trái phép.

### Rejoiner

Nếu người cũ quay lại, không tự phục hồi quyền admin/workload owner lịch sử. Cần quan hệ công việc mới, approval và entitlement hiện hành.

**Leaver của human owner và Retire của workload là hai sự kiện khác nhau**, nhưng có quan hệ kiểm soát chặt: quyền người nghỉ phải bị cắt, trong khi workload hợp lệ cần được tiếp tục vận hành dưới owner mới.

## 22. Rotation và thời hạn credential

Một điểm mạnh của workload identity hiện đại là **khả năng phát credential ngắn hạn và tự làm mới**.

### Các loại credential

| Loại | Có thể ngắn hạn? | Những điều cần quản lý |
|---|---|---|
| **OIDC assertion** | Thường có exp ngắn | Issuer, audience, trust, subject, leak |
| **STS-issued credential** | Tùy nền tảng, thường theo phiên | Role scope, TTL, revocation limits |
| **SPIFFE X.509-SVID** | Được cấp/rotate theo cơ chế SPIFFE | Trust bundle, certificate reload, connection lifecycle |
| **JWT-SVID** | Có exp và audience | Signature, subject, audience, replay |
| **OAuth access token** | Có exp theo AS policy | Audience, scope, refresh, stale grants |
| **API key tĩnh** | Có thể không có exp mặc định | Vault, inventory, rotation, revoke |
| **Long-lived service secret** | Có thể bị dùng vô hạn nếu không kiểm | Giảm dùng, hạn chế scope, rotation plan |

### Nguyên tắc vận hành

1. Dùng **TTL phù hợp với rủi ro và khả năng refresh**.
2. Tránh để token trong log, error response, build artifact hoặc config image.
3. Cấu hình SDK/agent để **refresh trước expiry** và xử lý race.
4. Cân nhắc **clock skew**, issuer outage và cache.
5. Khi rotate trust bundle/signing key, duy trì khoảng giao nhau có kiểm soát để tránh ngắt toàn bộ service.
6. Phân biệt **rotation** (đổi credential) với **revocation** (chấm dứt quyền).
7. Không tự tăng TTL lên vô hạn chỉ vì refresh bị lỗi; cần xử lý sự cố nền tảng.
8. Với secret dài hạn còn tồn tại, có owner, phạm vi, kho an toàn và kế hoạch loại bỏ.

**Token ngắn hạn vẫn có thể bị lạm dụng trong khoảng hiệu lực.** TTL làm giảm cửa sổ rủi ro, không xóa nhu cầu kiểm soát hành động và resource.

## 23. Thu hồi workload identity: nhiều lớp phải đồng bộ

Một workload bị xâm nhập hoặc retire cần được chặn ở những lớp khác nhau:

| Lớp | Hành động | Giới hạn |
|---|---|---|
| **Workload registry** | Đổi state thành SUSPENDED/RETIRED | Registry flag chỉ có tác dụng nếu issuer/PEP kiểm |
| **Issuer/STS** | Dừng phát credential mới, sửa trust binding | Token/credential cũ có thể còn sống |
| **Runtime** | Scale down/stop pod, isolate job | Workload có thể chạy ở nơi khác |
| **IAM role binding** | Gỡ quyền cloud/SaaS/API đích | Target cache/session có thể trễ |
| **Certificate/trust** | Rotate/revoke SVID, thay trust bundle phù hợp | Kết nối mTLS đã mở có thể tiếp tục |
| **OAuth token** | Revoke/introspect/denylist khi được hỗ trợ | JWT self-contained thường không bị “xóa” tức thì |
| **API key/secret** | Revoke/rotate credential độc lập | Có thể có bản copy ở artifact |
| **Resource policy** | Deny workload subject/action ngay tại PEP/RS | Cần coverage toàn bộ đường truy cập |
| **Audit/reconciliation** | Readback và negative tests | Không biết mọi đường nếu inventory thiếu |

### Một ví dụ sự cố

09:00 phát hiện pod reports-job bị xâm nhập. Security dừng pod và hủy trust của service account. Tuy nhiên, job đã lấy cloud temporary credential có exp 10:00. Nếu cloud API vẫn chấp nhận credential đó, kẻ tấn công có thể tiếp tục đọc dữ liệu trong khoảng còn hiệu lực.

Ứng phó cần xem **resource-level deny, revocation/cutover khả dụng, key rotation và scope**. Không kết luận “đã thu hồi hoàn toàn” chỉ từ việc xóa pod.

### Điều kiện đóng sự cố

- Không còn **credential mới** được phát ngoài policy.
- Những **quyền ở đích** đã bị gỡ hoặc bị chặn.
- Token/cert/session còn sống được xử lý theo khả năng nền tảng.
- Các action nhạy cảm bị **Deny trong kiểm tra có kiểm soát**.
- Có evidence, owner và những ngoại lệ nếu phạm vi chưa xác minh đầy đủ.

## 24. IdP, SSO và SCIM: những gì workload identity không tự thay thế

**IdP** thường được dùng cho human login/SSO nhưng cũng có thể hỗ trợ **machine-to-machine clients, certificate trust và workload federation**. Cần phân biệt:

| Lĩnh vực | Với nhân viên | Với workload |
|---|---|---|
| **Identity source** | HRIS/contract và identity proofing | Service/workload registry, deployment/attestation |
| **Authentication** | Passwordless/MFA/SSO | Certificate, workload token, federation, client authentication |
| **Credential lifecycle** | Authenticator enrollment, session | Issuance/rotation/revoke của token, SVID, key |
| **Authorization** | RBAC/ABAC theo người, resource | Service principal + action/resource policy |
| **Provisioning** | SCIM User/Group, SaaS account | Platform IAM, workload role, service account, vendor API |
| **Joiner/Mover/Leaver** | Sự kiện quan hệ nhân sự | Create/Change/Retire và owner JML |
| **Audit** | Human actor/account | Workload principal, instance/job, owner, delegated actor |

### SCIM không phải cơ chế xác thực workload phổ quát

SCIM thường quản lý **User và Group**, hữu ích khi service identity tồn tại như technical user ở SaaS. Nhưng **SCIM không cung cấp một phương thức chuẩn chung để attestation pod hoặc cấp SPIFFE SVID**. Với workload chạy trên cloud/Kubernetes, provisioning thường qua platform IAM, Kubernetes API, IaC hoặc integration riêng.

### SSO không phải runtime service identity

Một service không nên đăng nhập bằng **tên người dùng/mật khẩu SSO của nhân viên** và giữ cookie trong bot. Điều này phá traceability, MFA có thể bị bypass và quyền máy sống phụ thuộc lifecycle người sở hữu.

### Role mapping và quyền tồn dư

Khi JML làm manager Leaver, **SSO disable** của người đó không tự thu hồi cloud role của workload. Ngược lại, xóa workload service account không tự disable human access của người quản trị. Cần inventory và reconciliation cả hai phía.

## 25. Bảo vệ metadata service và token delivery

Một số cloud/runtime cung cấp **metadata endpoint** để workload nhận identity token hoặc temporary credential. Nếu attacker có thể khiến một service gọi URL tùy ý (**SSRF**) hoặc nếu endpoint không giới hạn, attacker có thể truy cập credential của workload.

### Các biện pháp phòng vệ

1. Dùng **cơ chế metadata access bảo vệ theo platform**, gồm session/token hoặc hop limits nếu sản phẩm có.
2. Giới hạn workload nào có thể truy cập metadata endpoint.
3. Không để ứng dụng thực hiện arbitrary URL fetch tới metadata service từ input của user.
4. Dùng network/egress policy khi thích hợp; không coi egress filtering là bảo vệ duy nhất.
5. Phân tách instance/role giữa workloads có trust khác nhau.
6. Hạn chế quyền của credential có thể lấy từ metadata.
7. Cảnh báo bất thường khi workload nhận role/token không phù hợp.
8. Không log response chứa credential.
9. Đối với container sharing host, kiểm **isolation của host metadata và node privileges**.

### Dịch vụ không thể “an toàn vì token khó đọc”

Bất kỳ service nào có quyền đọc token trong môi trường thực thi có thể làm lộ nó qua bug, debug log, core dump hoặc attacker. Cần thiết kế **least privilege, runtime isolation, TTL, giám sát và thu hồi**.

## 26. Chống giả mạo identity, replay và confused deputy

| Mối đe dọa | Biểu hiện | Kiểm soát |
|---|---|---|
| **Issuer spoofing** | Token ký bởi nguồn không được trust | Chỉ chấp nhận issuer/JWKS hoặc CA được cấu hình |
| **Audience confusion** | Token của API A được dùng với API B | Verify aud theo từng resource server |
| **Subject wildcard quá rộng** | Repo hoặc ServiceAccount khác lấy role prod | Trust policy subject/resource cụ thể |
| **Token replay** | Assertion bị lấy cắp và trình lại | TTL ngắn, jti/state khi có thể, token binding phù hợp |
| **JWT alg confusion** | Validator chấp nhận thuật toán sai | Allowlist thuật toán, xác minh khóa và loại token |
| **Stale claims** | Role đã gỡ nhưng token cũ còn quyền | State check, cache invalidation, revocation phù hợp |
| **Key leakage** | Private key nằm trong image/git/CI logs | Vault/workload federation, secret scanning, rotation |
| **Metadata SSRF** | Service bị lừa đọc credential từ metadata | IMDS protection, SSRF defense, egress restrictions |
| **Confused deputy** | Service quyền cao làm hộ requester trái scope | Object-level authorization, caller/delegation binding |
| **Cross-tenant access** | Token hợp lệ đọc tài nguyên tenant khác | Tenant isolation ở API và data layer |
| **Service identity sharing** | Nhiều workload dùng chung principal | Tách identity và role theo blast radius |
| **Untrusted CI workflow** | Fork/PR nhận quyền deploy | Job claims, branch/environment approval, least privilege |
| **Supply chain compromise** | Image/job hợp lệ chạy code độc hại | Artifact integrity, provenance, runtime protections |
| **Privilege escalation** | Role có thể cấp role hoặc đọc secret rộng | SoD, permission boundary, guardrails |
| **Orphan service principal** | Không owner nhưng vẫn có quyền | Inventory, ownership review, expiry/remediation |
| **Policy rollback stale** | Khôi phục cấu hình cấp quyền đã bị gỡ | Version/fencing và JML-aware restore |

### Phân biệt xác thực token với ủy quyền tài nguyên

Một JWT có chữ ký hợp lệ không có nghĩa client **được quyền đọc object B**. Resource server phải kiểm **issuer, signature, audience, time, subject trust** rồi vẫn kiểm **permission, tenant, resource và action**.

### Không tin certificate chỉ vì do một CA nào đó ký

Với mTLS, cần xác định **CA/trust domain, subject/SAN, EKU khi áp dụng, validity, revocation strategy và identity mapping** phù hợp. Một certificate hợp lệ do CA chung ký nhưng không thuộc workload được phép không đủ để Permit.

## 27. Trạng thái JML và race condition trong lifecycle workload

Workload thay đổi liên tục: redeploy, scale-out, rotate cert, chuyển namespace, đổi repository, chuyển owner. Những thay đổi có thể đến **không theo thứ tự** ở IAM, STS và target.

### Tình huống: retire rồi job cũ tái cấp quyền

- 09:00 owner đánh dấu reports-job **RETIRED**.
- 09:01 IAM gỡ cloud role.
- 09:02 một provisioning job cũ từ deployment trước chạy lại.
- 09:03 job cũ gán lại role và STS có thể tiếp tục cấp credential.

Nếu không có **desired-state version, event ordering, fencing hoặc revalidation**, workload đã retire vẫn có thể được tái cấp quyền.

### Cách xử lý

1. Định nghĩa **source of truth** cho trạng thái workload và owner.
2. Gắn **workloadVersion/generation** vào thay đổi trọng yếu.
3. Trước khi provision/rotate/assume role, kiểm workload còn **ACTIVE và mapping hiện hành**.
4. Không dùng approval quá hạn để tự kích hoạt lại.
5. Dùng **idempotency keys** theo operation/resource.
6. Khi timeout, **readback** trước retry.
7. Chặn grant trái policy tại resource server khi cần.
8. Đối soát sau rollout, migration, retire và security incident.

**Rollback deployment không được đồng nghĩa rollback authorization tới quyền đã bị thu hồi.**

## 28. Audit và phân biệt service identity với actor con người

Một hành động máy có thể cần nối được:

- **Workload logical ID**.
- **Instance/pod/job ID** nếu mức quan sát yêu cầu.
- **Issuer/trust domain** và loại credential (không phải token thô).
- **Target resource**, tenant và environment.
- **Action/permission**.
- **Decision**: Permit, Deny, error.
- **Policy/role version** và grant source.
- **Owner team** và linked human actor nếu workflow có.
- **Request/trace/correlation ID**.
- **Time**, outcome và transaction ID.
- **Revocation/rotation events** khi có.

### Audit event minh họa

~~~json
{
  "eventId": "workload-authz-20261123-0117",
  "correlationId": "corr-b9a4",
  "workloadId": "service:payments-api",
  "instanceId": "pod:payments-api-5c8d",
  "ownerTeamId": "payments-platform",
  "identityIssuer": "https://issuer.cluster.example.org",
  "targetService": "events-api",
  "action": "queue.message.publish",
  "resourceId": "payment-events",
  "tenantId": "org-vn",
  "policyVersion": "payments-authz-v6",
  "decision": "PERMIT",
  "executionOutcome": "SUCCESS",
  "observedAt": "2026-11-23T09:20:00+07:00"
}
~~~

Đây là **schema audit nội bộ minh họa**. Không lưu bearer token, client secret, private key hoặc dữ liệu nhạy cảm không cần thiết.

### Không nhầm Decision với Execution

- **PDP Permit:** policy cho phép theo dữ liệu đầu vào.
- **Target API execution succeeded:** tác vụ đã thực hiện thành công.
- **Token issued:** workload đã nhận credential, chưa chắc dùng nó.
- **Role revoked:** grant bị gỡ trong control plane, chưa chứng minh mọi session/credential cũ vô hiệu.
- **Workload suspended:** issuer có thể ngừng cấp mới nhưng token cũ vẫn có thể dùng.

Mỗi sự kiện cần bằng chứng riêng để kiểm toán và phản ứng sự cố.

## 29. Các chỉ số theo dõi Workload identity

| Metric | Ý nghĩa | Điều cần lưu ý |
|---|---|---|
| **Total workload identities** | Số principal trong phạm vi | Không đồng nghĩa số pod/job |
| **Workloads with approved owner** | Tỷ lệ có owner/team hợp lệ | Owner nhân viên Leaver cần chuyển |
| **Long-lived secret inventory** | Số key/secret không có TTL ngắn | Cần ưu tiên migration có kiểm soát |
| **Federated vs static credential ratio** | Mức sử dụng cơ chế không cần shared key | Federation chỉ có giá trị khi trust hẹp |
| **Overprivileged workload grants** | Quyền vượt mục đích đã duyệt | Cần xem effective permissions |
| **Unused privileged grants** | Quyền nhạy cảm không được dùng | Là tín hiệu điều tra, không tự xóa |
| **Expired/retired-but-active identities** | Workload không còn căn cứ nhưng còn role/token | Rủi ro quyền tồn dư |
| **Credential issuance anomalies** | STS phát token ngoài kỳ vọng | Cần phân biệt scale-out hợp lệ |
| **Trust policy wildcard exposure** | Subject/issuer bindings quá rộng | Có thể mở production tới workload ngoài phạm vi |
| **Token validation failure rate** | Sai issuer/aud/exp/signature | Có thể là cấu hình hoặc tấn công |
| **Revocation verification latency** | Từ retire/suspend tới target Deny | Khác thời gian cập nhật registry |
| **Service identity reuse** | Nhiều apps khác chức năng chia sẻ một principal | Tăng blast radius |
| **Cross-tenant denial tests** | Số đường bị chặn theo isolation policy | Phải kiểm coverage |
| **Unmapped local technical accounts** | SaaS/service users không nối với registry | Không thể khẳng định đã kiểm soát |
| **Owner JML handoff backlog** | Workload thiếu owner mới sau Mover/Leaver | Nguy cơ secret/approval vô chủ |
| **Attestation/rotation failures** | Không cấp/rotate được credential đúng hạn | Ảnh hưởng availability |

Không nên tối ưu KPI “ít workload identities” bằng cách cho nhiều dịch vụ dùng một account chung. Mục tiêu là **đúng danh tính, đúng quyền, có owner, giới hạn blast radius và khả năng thu hồi có bằng chứng**.

## 30. Kiểm thử Workload identity và federation

| Kịch bản | Điều kiện | Kết quả mong đợi |
|---|---|---|
| **Issuer hợp lệ** | Assertion ký bởi issuer tin cậy | Đi tiếp các kiểm tra khác, chưa tự Permit |
| **Issuer giả** | URL issuer không trong trust policy | Deny |
| **Audience sai** | Assertion dành API A gửi STS B | Deny |
| **Subject sai** | CI repo khác cố nhận production role | Deny |
| **Token hết hạn** | Server time vượt exp | Deny |
| **Token chưa có hiệu lực** | nbf ở tương lai | Deny theo clock/skew policy |
| **Missing claim** | Không có subject/issuer bắt buộc | Không tự Permit |
| **JWT alg không cho phép** | Header khai thuật toán không thuộc allowlist | Deny |
| **Workload RETIRED** | Registry inactive nhưng token mới được xin | Không phát credential mới |
| **Retired existing token** | Token cũ còn exp | Target xử lý theo policy revocation/cutoff |
| **Cross-tenant request** | Service tenant A đọc object tenant B | Deny |
| **Scope vượt grant** | Reports job gọi secret.delete | Deny |
| **Staging dùng prod role** | Same service name, khác environment | Deny nếu không được ủy quyền |
| **Default Kubernetes SA** | Pod không được phê duyệt xin quyền cloud | Deny |
| **ServiceAccount token rotation** | Token file thay đổi khi refresh | SDK vẫn hoạt động trong TTL đúng |
| **STS unavailable** | Không xin được credential mới | Không fallback về shared global-admin key |
| **Secret bị lộ** | Credential bị thu thập trái phép | Xử lý incident/rotate/revoke, hạn chế scope |
| **CI pull request không tin** | Job từ fork muốn deploy production | Deny |
| **Approval bypass** | Pipeline author tự approve release trái SoD | Deny/require independent approval |
| **Multiple instances** | Scale-out nhiều pods đúng service | Chính sách không cấp chéo workload |
| **SSRF tới metadata** | Untrusted URL trỏ metadata service | Request bị chặn theo thiết kế |
| **Human owner Leaver** | Service còn cần, owner cũ nghỉ | Gỡ quyền owner cũ, chuyển owner service |
| **Retire event race** | Job provisioning cũ chạy sau retire | Version/fencing chặn regrant |
| **Target permission drift** | App role cấp quyền rộng hơn mapping | Finding được phát hiện khi reconcile |
| **Audit** | Token/credential được cấp rồi dùng | Có trace đúng workload, không log secret |

### Các lớp test

1. **Trust configuration tests:** issuer, subject, audience, claims và certificate chain.
2. **Credential lifecycle tests:** issuance, refresh, expiry, rotation, revocation.
3. **RBAC/ABAC tests:** action/resource scope và tenant isolation.
4. **Runtime tests:** mTLS, mesh/proxy identity propagation và backend PEP.
5. **JML tests:** owner Joiner/Mover/Leaver, service Change/Retire.
6. **Concurrency tests:** stale job, retry timeout, token refresh race.
7. **Adversarial tests:** SSRF, token replay, forged headers, confused deputy.
8. **Negative tests:** action trái scope vẫn Deny dù credential đúng chữ ký.
9. **Audit/reconciliation tests:** observed access và bằng chứng không lộ secret.

**Một token federation được phát thành công không đủ chứng minh chính sách ủy quyền tài nguyên an toàn**. Cần test action thực tế, deny cases và những đường bypass không đi qua trust proxy.

## 31. Runbook khi Workload identity không hoạt động hoặc không thể thu hồi

### A. Workload nhận lỗi 401

1. Xác minh workload runtime còn đang chạy và identity binding đúng.
2. Kiểm issuer, **audience, subject, signature, nbf/exp** của credential theo cách an toàn.
3. Kiểm JWKS/certificate trust bundle và clock skew.
4. Kiểm token mount/refresh, không dán credential vào log hoặc ticket.
5. Xác định API đích có chấp nhận loại credential đó không.
6. Không tạm sửa bằng cách bỏ kiểm chữ ký, tắt mTLS hoặc dùng shared admin key.

### B. Workload nhận lỗi 403

1. Credential có hợp lệ và dành đúng API không?
2. Target role/resource policy cấp action nào?
3. Resource/tenant/environment có nằm trong grant scope không?
4. Có deny policy, SoD, classification hoặc condition nào áp dụng?
5. Role mapping/SCIM/API đích đã cập nhật chưa?
6. Có quyền bị thu hồi theo change/retire nhưng workload chưa redeploy không?
7. Không gán global-admin để che một quyền hẹp bị thiếu.

### C. STS không phát credential

1. Kiểm issuer/trust config đã thay đổi?
2. Assertion còn hiệu lực và đúng audience?
3. Subject có khớp chính xác workload binding không?
4. CI job có tới từ fork/ref không được phép?
5. Owner/workload registry có bị suspended hoặc retired?
6. Kiểm lỗi quota/rate limit/network và backoff có giới hạn.
7. Không retry bằng cách lộ assertion hoặc disable kiểm bảo mật.

### D. Workload đã retire nhưng còn truy cập

1. Ưu tiên **chặn action rủi ro tại resource policy/PEP**.
2. Liệt kê tất cả issuer, STS-issued credentials, role bindings và API keys.
3. Dừng cấp credential mới; xóa trust binding không còn hợp lệ.
4. Kiểm token/cert còn hiệu lực, phiên mTLS và session đang mở.
5. Gỡ quyền tại target, đọc lại observed state.
6. Thử deny có kiểm soát cho action đã bị thu hồi.
7. Nếu credential không thể revoke tức thì, áp biện pháp bù trừ và ghi finding.
8. Đóng khi không còn quyền trái policy trong phạm vi đã xác minh.

### E. Human owner nghỉ việc

1. Nhận HRIS Leaver event có thẩm quyền.
2. Thu hồi quyền người cũ trên registry, IAM, CI/CD, secrets và cloud.
3. Xác định workload vẫn cần chạy hay không.
4. Chỉ định owner mới và điều chỉnh approval/escalation.
5. Rà soát secrets hoặc credential người cũ có thể đã biết.
6. Giữ service production hợp lệ hoạt động nhưng không giữ human privilege tồn dư.

## 32. Tình huống xuyên suốt: Workload identity trong hệ thống thanh toán

Giả sử doanh nghiệp có **payments-api** chạy trên Kubernetes, **reporting-batch** chạy theo lịch và pipeline **deploy-payments** dùng CI/CD. Ba workload cần truy cập cloud nhưng không nên chia sẻ một cloud-admin key.

### Giai đoạn 1 — Thiết kế danh tính

Đội Platform đăng ký:

- **service:payments-api** do Payments Platform sở hữu.
- **job:reporting-batch** do Analytics Platform sở hữu.
- **pipeline:deploy-payments** do Release Engineering quản trị.

Mỗi workload có **purpose, source runtime, trusted issuer, resource scope và review date**. Security phê duyệt role hẹp; tránh cấp toàn project.

### Giai đoạn 2 — Xác thực workload

Pod payments-api sử dụng **projected ServiceAccount token** với audience dành cho STS. STS chỉ chấp nhận issuer của cluster production và subject tương ứng service account được duyệt. Sau đó STS phát credential ngắn hạn cho quyền **queue.message.publish** trên payment-events.

Đồng thời, **reporting-batch** có credential chỉ đọc từ storage prefix cho báo cáo được phép; không có quyền publish payment.

### Giai đoạn 3 — CI/CD federation

Pipeline deploy-payments chạy trên workflow được phê duyệt, nhận OIDC assertion từ CI issuer. STS kiểm **repository/environment/workflow/subject**, cấp credential deploy **service payments production** có TTL ngắn. Pipeline không lưu cloud access key dài hạn trong repository.

Một pull request từ fork không tin cậy cố lấy role deploy production. Trust policy không cho subject/ref/environment đó nhận credential, nên **deny**.

### Giai đoạn 4 — Authorization và SoD

Một caller nội bộ yêu cầu payments-api tạo giao dịch. mTLS xác thực service gọi, nhưng payments-api còn kiểm **tenant, orderId, action và permission**. Nếu payload yêu cầu giao dịch thuộc tenant khác, API từ chối dù caller có certificate hợp lệ.

Pipeline cũng phải có **change approval độc lập** nếu chính sách production yêu cầu; workload identity không cho phép người viết code tự bỏ bước release control.

### Giai đoạn 5 — Mover của owner

Kỹ sư chịu trách nhiệm payments-api chuyển đội. IAM gỡ quyền cá nhân trên cloud production và CI secrets, cập nhật owner registry. Payments-api không bị xóa vì vẫn là workload production hợp lệ.

Security kiểm những secret cũ, session và role mapping. Workload tiếp tục dùng identity riêng với quyền đã được xác minh.

### Giai đoạn 6 — Incident và thu hồi

Phát hiện token của reporting-batch bị log ra một hệ thống không đáng tin. Incident response chặn scope nhạy cảm nếu có thể, ngừng cấp token mới, xử lý credential đang sống và khắc phục log. Không chỉ rotate secret metadata rồi coi token cũ đã chết. Đội xác minh endpoint không còn cho token ngoài policy đọc dữ liệu.

### Giai đoạn 7 — Retire batch job

Reporting-batch được thay thế. Registry chuyển sang **RETIRED**, STS trust binding và target role bị gỡ, secret đã dùng được xử lý, runtime job dừng. Reconciliation xác minh **reporting-batch không còn quyền đọc storage**, kể cả credential tồn dư trong phạm vi quan sát.

### Bài học

**Workload identity gắn quyền với phần mềm thật đang chạy và nguồn phát chứng cứ được tin cậy**, thay vì gắn service vào mật khẩu người dùng hoặc khóa admin dùng chung. Giá trị bảo mật chỉ đạt khi **issuer/trust policy, authorization scope, lifecycle, rotation, revocation, audit và reconciliation** được vận hành đồng bộ.

## 33. Checklist thiết kế Workload identity an toàn

1. **Định nghĩa:** workload identity khác human account, service account và credential chưa?
2. **Danh mục:** mỗi workload có ID ổn định, purpose, owner và environment?
3. **Trust:** issuer/trust domain, subject và audience được xác minh chặt?
4. **Attestation:** chứng cứ workload đến từ platform tin cậy, không do client tự khai?
5. **Registration:** thay đổi repo, service account, namespace, runtime có được review?
6. **Authentication:** STS/JWT/certificate có validation chữ ký, exp, algorithm và trust?
7. **Federation:** có dùng short-lived credential thay static cloud key khi khả thi?
8. **Scopes:** role cho đúng action, resource, tenant và environment?
9. **RBAC/ABAC/PBAC:** credential hợp lệ không tự cho quyền trên mọi tài nguyên?
10. **mTLS:** peer được xác thực nhưng backend vẫn kiểm object-level authorization?
11. **SPIFFE/SVID:** workload ID, trust bundle và rotation được quản lý khi dùng?
12. **Kubernetes:** ServiceAccount riêng, projected token với audience và RBAC hẹp?
13. **CI/CD:** trust policy giới hạn repository, ref/workflow/environment theo khả năng issuer?
14. **Supply chain:** artifact provenance, runner trust và approval được kiểm riêng?
15. **Delegation:** acting on behalf of user có gắn actor/subject phù hợp?
16. **SoD:** người tạo change không tự duyệt/release trái policy?
17. **Secret storage:** không lưu credential trong image, git, log hoặc artifact?
18. **Rotation:** SDK và platform làm mới token/cert trước expiry đúng?
19. **Revocation:** retire/suspend chặn issuance mới và xử lý credential còn sống?
20. **Owner JML:** human Leaver được gỡ quyền cá nhân nhưng không xóa nhầm service cần chạy?
21. **Mover:** owner/role thay đổi có dẫn tới rà soát workload grants và secrets?
22. **Rejoiner:** human cũ không tự nhận lại quyền quản trị workload lịch sử?
23. **Non-human lifecycle:** create, activate, change, suspend, retire có owner và audit?
24. **Metadata security:** IMDS/SSRF và token delivery được bảo vệ?
25. **Cross-tenant:** role/token không cho truy cập nhầm tenant/resource?
26. **Threat model:** replay, forged header, confused deputy và trust wildcard đã được test?
27. **Cache/session:** token/cert/kết nối cũ được xử lý theo khả năng và risk?
28. **Concurrency:** job lỗi thời không regrant sau retire nhờ version/fencing?
29. **Audit:** trace issuer, workload, instance/job, action, resource, decision và human actor khi có?
30. **Access review:** service principals, SaaS technical users và local grants được inventory?
31. **Metrics:** đo orphan/overprivileged/retired-but-active, TTL và revoke latency?
32. **Negative tests:** đúng signature nhưng sai audience, scope hoặc tenant phải Deny?
33. **Reconciliation:** observed access tại target khớp desired state và ghi rõ coverage?
34. **Incident response:** có runbook rotation, containment, credential leak và owner transfer?
35. **Closure:** không khẳng định hoàn tất chỉ vì pod đã xóa hoặc role đã gỡ trong control plane?

### Ghi nhớ

**Workload identity là danh tính dùng để xác thực và quản trị quyền của phần mềm đang thực thi**, bao gồm microservice, container, job và pipeline CI/CD. Nó phân biệt **workload principal** với **credential** và **permission**, cho phép sử dụng những cơ chế như **OIDC federation, STS, Kubernetes ServiceAccount token, SPIFFE/SVID và mTLS** theo khả năng nền tảng. Thiết kế an toàn phải có **trusted issuer/subject/audience, phạm vi quyền tối thiểu, credential ngắn hạn, attestation phù hợp, token/session controls, audit và thu hồi có kiểm chứng**. Trong **IAM Identity Lifecycle**, vòng đời **Create–Change–Retire của workload** cần gắn với **Joiner–Mover–Leaver của người chịu trách nhiệm**, nhưng không bị đánh đồng: **cắt quyền người đã nghỉ, chuyển ownership cho workload còn hợp lệ, ngăn cấp lại sai và xác minh quyền truy cập thực tế ở hệ thống đích** mới giúp giảm **quyền truy cập tồn dư**.
