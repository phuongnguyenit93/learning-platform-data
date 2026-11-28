# Bảo vệ network credential trong runtime container: danh tính, bí mật kết nối và vòng đời an toàn

## 1. Network credential trong runtime là gì và vì sao cần bảo vệ?

Một ứng dụng chạy trong container không chỉ mở socket TCP/UDP. Nó thường phải **chứng minh danh tính** trước API, cơ sở dữ liệu, Kubernetes API server, cloud control plane hoặc một dịch vụ khác; đôi khi cũng phải **xác thực peer** trước khi trao đổi dữ liệu. Những vật liệu chứng thực đó được gọi chung trong bài là **network credentials**: các token, private keys, chứng chỉ, thông tin đăng nhập và shared secrets được dùng để **thiết lập kết nối hoặc xin quyền truy cập qua mạng**.

Ví dụ, service **orders** trong Pod Kubernetes cần gọi **payments** qua mTLS, truy cập một database bằng credential ngắn hạn và đôi khi lấy cấu hình từ cloud secret manager. Nếu một container bị chiếm quyền thực thi hoặc bị cấu hình quá nhiều quyền, kẻ xâm nhập có thể tìm thấy credential ở **biến môi trường, volume, bộ nhớ process, file log, crash dump hoặc socket cục bộ**, rồi dùng credential đó truy cập một dịch vụ khác. Đến lúc này, rủi ro không còn nằm ở container ban đầu mà có thể lan sang **namespace, cluster, cloud account hoặc vùng dữ liệu Production**.

Trong module **SECURITY_NETWORK_SECURITY**, bảo vệ credential là cầu nối giữa **network segmentation, firewall, VPN, IDS/IPS, TLS/mTLS, identity-based access control, phân tích lưu lượng và bảo mật mạng cloud**. Mã hóa đường truyền và NetworkPolicy rất quan trọng, nhưng **không thể thay cho quản lý danh tính và bí mật** nếu một token đã bị đánh cắp vẫn được hệ thống đích chấp nhận.

**Phạm vi bài:** tập trung vào **lúc workload đang chạy (runtime)**, bao gồm injection/consumption, file/socket/memory exposure, workload identity, quyền truy cập, luân chuyển/thu hồi, giám sát và ứng phó. Build-time secrets, image signing và registry credentials chỉ được nhắc khi ảnh hưởng tới runtime; chúng không phải trọng tâm.

### Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân biệt **credential của workload**, **chứng chỉ public**, **private key**, **ServiceAccount token**, **OAuth access token**, **database secret** và **image pull credential**.
2. Vẽ **đường đi của bí mật** từ identity provider/secret manager tới process, sidecar và network peer; xác định ranh giới tin cậy.
3. Giải thích các rủi ro khi truyền credential bằng **environment variables, filesystem mounts, Kubernetes Secret, CSI driver, socket và log**.
4. Sử dụng **workload identity và token ngắn hạn** với issuer/audience/subject/scopes, thay vì phát tán static cloud credentials.
5. Phân tích **mTLS/SPIFFE/service mesh**, file private key, SDS/agent và tác động của sidecar khi bị compromise.
6. Thiết kế **least privilege, NetworkPolicy/egress, RBAC/IAM, namespace isolation và runtime hardening** phối hợp.
7. Lập **quy trình cấp phát, rotate, revoke, thu hồi và điều tra** credential theo từng nhóm.
8. Đọc manifest và thực hành **kiểm tra offline bằng Python** trên dữ liệu cấu hình mô phỏng, không dùng secrets thật.

## 2. Phân loại các credential liên quan kết nối mạng

| Vật liệu | Dùng ở đâu | Bản thân có bí mật? | Phạm vi rủi ro khi lộ |
| --- | --- | --- | --- |
| **Bearer access token** (OAuth/JWT hoặc opaque) | Gọi API, cloud API | **Có**; bên giữ token có thể dùng theo điều kiện token | Các API/resource được scope/audience cho phép |
| **Kubernetes ServiceAccount token** | Kubernetes API, đôi khi làm assertion để xin cloud token | **Có** | Quyền RBAC của SA hoặc quyền liên kết federation |
| **mTLS certificate (public)** | Xác định workload identity | Thường **không**, certificate được chia sẻ công khai | Lộ public certificate không tương đương lộ private key |
| **mTLS private key** | Chứng minh danh tính trong handshake | **Có** | Mạo danh workload nếu trust policy vẫn chấp nhận |
| **CA/root trust bundle** | Xác thực peer | Public CA certificate thường **không** | Bị **thay thế trái phép** có thể làm sai quyết định tin cậy |
| **Cloud short-lived credentials** | Cloud storage, database/API services | **Có** | Tài nguyên cloud theo IAM session/role |
| **Static API key / database password** | API/database/queue | **Có** | Quyền thường tồn tại lâu, khó thu hồi nếu chia sẻ |
| **Registry pull credential** | Node/kubelet/container runtime kéo image | **Có** | Registry/repository theo quyền; thường không cần có trong app container |
| **Webhook/HMAC signing secret** | Ký hoặc xác thực message | **Có** | Giả thông điệp hoặc xác nhận sai nguồn |
| **Secret manager access identity** | Xin hoặc đọc các secrets khác | Có thể là assertion/token/key | Lộ quyền **truy cập nhiều secrets**, không chỉ một API |
| **TLS session traffic secret** | Mã hóa một phiên TLS | **Có** | Traffic thuộc phiên tương ứng có thể bị lộ |

### 2.1. Public identity khác authentication secret

**Certificate X.509 chứa public key, metadata và chữ ký số** thường được trao cho peer; việc ai đó xem certificate không cho phép tự ký hợp lệ thay cho workload. **Private key tương ứng** phải được bảo vệ. Một CA trust bundle cũng có thể được phân phối rộng cho workloads để xác thực peer, nhưng **quyền cập nhật trust bundle** lại đặc biệt nhạy cảm: thêm một CA sai có thể khiến workload tin server giả.

**JWT không mặc định được mã hóa:** JWT dạng JWS thường là **base64url-encoded claims có chữ ký**, bất kỳ ai có token có thể đọc nhiều claims. Không đưa PII/secret trong payload rồi hy vọng mã hóa TLS đủ giải quyết nếu token bị xuất sang log. **Bearer token** phải được đối xử như mật khẩu trong phạm vi quyền của nó.

### 2.2. Pull secret không tự thuộc mọi container

Trong Kubernetes, **imagePullSecrets** thường được **kubelet/container runtime** dùng để xác thực với registry khi kéo image. Chúng **không nhất thiết được mount vào application container**. Không tự đưa registry password vào Pod environment chỉ để image pull; tách quyền **pull image** khỏi quyền **ứng dụng gọi API**.

### 2.3. Secret manager không làm biến mất trách nhiệm runtime

Secret manager hoặc KMS có thể bảo vệ secrets **at rest**, audit việc đọc và cung cấp cơ chế rotation. Nhưng khi ứng dụng cần sử dụng secret, nó có thể hiện diện **trong memory, file, socket hoặc network response**. Nếu process có quyền sử dụng credential và bị chiếm quyền toàn phần, attacker có thể **sử dụng credential hoặc thực hiện hành động với identity ấy**, dù private key không export được. Mục tiêu thực tế là **giảm thời gian tồn tại, quyền và phạm vi ảnh hưởng**, không hứa bí mật tuyệt đối trước compromise cùng process.

## 3. Mô hình đe dọa: credential đi qua những ranh giới nào?

~~~mermaid
flowchart LR
    I["Identity provider / CA / Secret manager"] -->|"Token, cert, secret delivery"| A["Node agent / CSI / workload identity broker"]
    A -->|"Bound token / file / socket"| P["Application container"]
    P -->|"TLS/mTLS, Authorization"| S["Remote API / database"]
    P --> M["Local sidecar / service mesh proxy"]
    M -->|"mTLS + workload identity"| T["Remote service mesh proxy"]
    R["Cloud audit, K8s audit, eBPF/CNI / app logs"] -. "Quan sát có giới hạn" .-> P
    R -. "Identity + policy events" .-> I
~~~

Các điểm tấn công/nhầm cấu hình điển hình:

- **Source:** secrets hardcode trong image, Git, CI output, Helm values hoặc ConfigMap.
- **Delivery:** agent/CSI driver bị cấp quyền quá rộng, shared secret store, hostPath nhạy cảm.
- **Process:** RCE, file đọc được bởi user/process khác, debug endpoint, memory dump, accidental logging.
- **Node boundary:** privileged Pod, hostPID/hostNetwork/hostPath, Docker/container runtime socket, node compromise.
- **Network:** plaintext hop, giả mạo peer, SSRF tới cloud metadata/secret services, egress không kiểm soát.
- **Identity plane:** ServiceAccount rộng quyền, federation trust condition sai, token audience không đúng.
- **Lifecycle:** token quá lâu, không rotate, certificate cũ còn hợp lệ, chưa revoke khi Pod/workload bị xóa.
- **Response:** log phân tích chứa raw token; incident team chia sẻ file secret trong ticket.

### 3.1. Tách các chủ thể

| Chủ thể | Quyền/thông tin thường có | Không được mặc nhiên tin |
| --- | --- | --- |
| Application process | Credentials được cấp cho chức năng của chính nó | Không tự được quyền toàn namespace/cluster |
| Sidecar/mesh proxy | Workload identity và khả năng xử lý lưu lượng giữa services | Không mặc nhiên hoàn toàn độc lập trust boundary với cùng Pod |
| Node/kubelet/container runtime | Chạy workloads, thao tác volumes và network | Node compromise có thể ảnh hưởng nhiều Pods trên node |
| Kubernetes API | ServiceAccounts, RBAC, Secret objects, Pod specs | Cần kiểm soát người có quyền tạo/patch Pod và đọc Secret |
| Cloud STS/identity broker | Đổi workload assertion thành cloud temporary credential | Cần trust binding theo issuer, audience, subject và identity |
| Remote API/database | Kiểm tra token/cert và application authorization | Không chỉ dựa vào source IP của Pod |
| SOC/observability | Log/metrics/flow info để giám sát | Không mặc nhiên được xem raw credential |

### 3.2. Mục tiêu bảo mật theo STRIDE

| Nhóm | Ví dụ với network credential | Phòng vệ |
| --- | --- | --- |
| **Spoofing** | Token bị đánh cắp dùng mạo danh workload | Token audience/scope/time hạn hẹp, mTLS và peer validation |
| **Tampering** | Kẻ tấn công thay trust bundle hoặc mount path | Read-only mounts, policy/attestation, file provenance |
| **Repudiation** | Không biết workload nào dùng credential sai | Audit issuance/use và identity correlation không log raw secret |
| **Information disclosure** | Bearer token rơi vào env dump, log, artifact | Secret handling, redaction, least privilege, retention |
| **Denial of service** | Rotation lỗi khiến mọi mTLS connection fail | Graceful overlap/rollout, health metrics, rollback có kiểm soát |
| **Elevation of privilege** | App Pod đọc cluster-wide Secrets hoặc cloud admin | RBAC/IAM tách theo workload, hạn chế projected token |

**Quan trọng:** Network segmentation và firewall hạn chế **nơi có thể kết nối**, nhưng nếu một workload được phép gọi API nhạy cảm bằng credential có quyền rộng, attacker chiếm workload ấy có thể **lạm dụng chính đường được phép**. Phải kết hợp **network-level allowlist với identity-aware authorization**.

## 4. Quy tắc cốt lõi: credential tối thiểu, ngắn hạn, ràng buộc đúng nơi dùng

Một credential tốt cần được thiết kế theo năm câu hỏi:

1. **Ai?** Workload identity/subject là gì, được chứng minh bằng cách nào?
2. **Dùng ở đâu?** Audience, service, tenant, namespace, environment nào được phép chấp nhận?
3. **Được làm gì?** IAM role, Kubernetes RBAC, API scopes, database grants cụ thể ra sao?
4. **Dùng bao lâu?** Expiry, TTL, rotation window và cơ chế làm mới thế nào?
5. **Bị lấy mất sẽ ra sao?** Có thể revoke/chặn ở verifier không, và phát hiện misuse bằng logs nào?

| Thiết kế | Rủi ro | Khuyến nghị |
| --- | --- | --- |
| Một API key Production dùng chung toàn bộ microservices | Khó biết ai dùng và thu hồi không gián đoạn | Tách identity/token theo workload, service và environment |
| Static cloud access key ghi trong image/env | Dễ tồn tại lâu, lộ qua artifacts và debugging | Dùng workload identity + temporary credentials |
| Token audience chung cho mọi dịch vụ | Token dùng sai service vẫn được nhận | Ràng buộc issuer/audience/subject và resource policy |
| Token có cluster-admin hoặc cloud owner role | Chiếm một container dẫn tới toàn hệ thống | Least-privilege RBAC/IAM và policy checks |
| Certificate mTLS dùng chung cho nhiều Pods lâu dài | Khó attribution, blast radius lớn | Danh tính riêng theo workload và short-lived certificates |
| Không có kế hoạch refresh/revoke | Outage khi hết hạn hoặc lạm dụng kéo dài | Thiết kế trước lifecycle, observability và response |

### 4.1. TTL ngắn giúp gì và không giúp gì?

**TTL ngắn** giảm khoảng thời gian mà **một bản sao credential** còn hiệu lực, nếu verifier áp expiry đúng. Tuy nhiên attacker giữ quyền trong process **có thể xin token mới** hoặc sử dụng identity liên tục. Vì vậy cần ngăn **refresh path bị lạm dụng**, revoke quyền ở nơi cấp/kiểm tra, cô lập workload và xác minh nguyên nhân xâm nhập.

### 4.2. Không biến expiry thành giả định revocation

Hết hạn token khác với **thu hồi ngay**. JWT có chữ ký có thể còn được verifier chấp nhận **tới khi hết hạn** nếu hệ thống không có cơ chế denylist/introspection/trust revocation tương ứng. Certificate ngắn hạn thường giảm rủi ro nhưng **CRL/OCSP, trust bundle và phân phối policy** cũng có semantics riêng. Không hứa “rotate là token cũ mất tác dụng lập tức”.

## 5. Kubernetes Secret: cách đưa vào runtime và giới hạn

Kubernetes **Secret** lưu cấu hình nhạy cảm ở dạng Kubernetes API object, có thể được tiêu thụ bởi Pod qua **environment variables** hoặc **volume-mounted files**. Khả năng bảo vệ tùy **RBAC, node, etcd encryption at rest, audit, admission policy và cách ứng dụng dùng**.

### 5.1. Base64 không phải mã hóa

Trong nhiều manifest Secret, trường data chứa **base64-encoded values**. Đây là **mã hóa biểu diễn**, không bảo mật khỏi người đọc được YAML hoặc object. Muốn bảo vệ bí mật khi lưu trong Kubernetes backend cần cấu hình **encryption at rest** của API server/etcd theo nền tảng, kết hợp **KMS, IAM, RBAC và backup controls**. Điều đó không tự bảo vệ file/memory sau khi Secret được cấp cho Pod.

### 5.2. Environment variables và mounted files

| Cách phân phối | Ưu điểm | Điểm cần bảo vệ |
| --- | --- | --- |
| **Environment variable từ Secret** | Nhiều ứng dụng dễ dùng | Có thể lộ qua crash/debug/process inspection; thường **không tự cập nhật** trong process khi Secret thay |
| **Secret mounted volume** | Có thể tách file, giới hạn mount path và read-only | Quyền đọc file, update behavior, path traversal, Pod/container access |
| **CSI/external secret provider mount** | Có thể tích hợp external secret manager và rotation | Phụ thuộc driver/provider sync/permissions, node plugin/agent, lifecycle |
| **Agent/socket-based delivery** | Có thể xin credentials theo identity trong runtime | Bảo mật Unix socket, API auth, buffer/memory, agent compromise |
| **Workload identity + on-demand token** | Giảm static secret | Trust configuration, audience, refresh path và cloud IAM scope |

**Secret volume trên Linux Kubernetes thường dùng filesystem được quản lý dưới node (có thể memory-backed theo loại volume)**, nhưng chi tiết lưu trữ/phân phối khác nhau theo driver và OS. Không giả định mọi Secret mount không bao giờ chạm disk hoặc không thể đọc bởi node administrator.

### 5.3. Secret volume update không đồng nghĩa ứng dụng đã rotate

Kubernetes có thể cập nhật dữ liệu Secret mounted volume theo cơ chế propagation của kubelet và cache; update **không tức thời**, và **mount qua subPath** không nhận cập nhật tự động tương tự volume thông thường. Ứng dụng có thể **giữ file descriptor, buffer hoặc TLS client context cũ** và không reload. Vì vậy cần cả:

1. Cơ chế cập nhật secret/certificate ở **storage/mount**.
2. Cơ chế **reload và reconnect/rehandshake** ở ứng dụng hoặc sidecar.
3. Giám sát **expiry, reload failures, stale credential usage**.
4. Kế hoạch rollback/overlap khi certificate/key mới chưa được mọi peers tin cậy.

## 6. ServiceAccount token: đừng để credential cluster tự xuất hiện không cần thiết

Mỗi Pod gắn với một **Kubernetes ServiceAccount**. Tùy Pod/SA settings và cơ chế platform, token có thể được tự động mount để workload gọi **Kubernetes API**. Nếu một ứng dụng chỉ nhận HTTP requests và **không cần Kubernetes API**, việc có token API trong filesystem tăng rủi ro bị lạm dụng khi container bị xâm nhập.

### 6.1. Tắt automount ở Pod không cần Kubernetes API

~~~yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: orders-api
  namespace: prod-apps
automountServiceAccountToken: false
---
apiVersion: v1
kind: Pod
metadata:
  name: orders-api-example
  namespace: prod-apps
spec:
  serviceAccountName: orders-api
  automountServiceAccountToken: false
  containers:
    - name: api
      image: registry.example.org/orders:example
      ports:
        - containerPort: 8080
~~~

**Ví dụ manifest chỉ minh họa tính năng, không phải cấu hình production hoàn chỉnh.** Tắt automount ở Pod có thể ngăn token tự xuất hiện ở path mặc định, nhưng **không thu hồi các credential khác** do ứng dụng tự lấy hoặc các projected volumes được khai báo tường minh. Một số thư viện/mesh agents/cloud integrations **cần token** để hoạt động; cần inventory chức năng trước khi tắt.

### 6.2. Projected ServiceAccount token có ràng buộc audience và hạn dùng

Kubernetes hỗ trợ **projected serviceAccountToken volume**: workload có thể xin token với **audience** và **expirationSeconds** phù hợp, thường do kubelet quản lý refresh/rotation. Token vẫn là **bearer credential**. Ví dụ mô tả ý tưởng cho một ứng dụng gọi identity broker riêng:

~~~yaml
apiVersion: v1
kind: Pod
metadata:
  name: broker-client-example
  namespace: prod-apps
spec:
  serviceAccountName: orders-api
  automountServiceAccountToken: false
  securityContext:
    runAsNonRoot: true
    runAsUser: 10001
    runAsGroup: 10001
    fsGroup: 10001
  containers:
    - name: client
      image: registry.example.org/broker-client:example
      volumeMounts:
        - name: broker-identity
          mountPath: /var/run/workload-identity
          readOnly: true
  volumes:
    - name: broker-identity
      projected:
        defaultMode: 0440
        sources:
          - serviceAccountToken:
              path: token
              audience: broker.example.org
              expirationSeconds: 3600
~~~

**Lưu ý bắt buộc:** Đây là **mẫu khái niệm, không cam kết chạy nguyên vẹn trên mọi cluster**; hỗ trợ/giới hạn expiration, volume ownership, group/mode, token refresh và đường dẫn khác nhau theo phiên bản/nền tảng. Trước production phải **xác minh Pod thực sự đọc được file bằng identity dự kiến**, **broker kiểm tra đúng issuer/audience/subject/expiry** và ứng dụng **reread token sau rotation**. Không chuyển token này thành token được chấp nhận bởi mọi API chỉ vì nó có chữ ký.

### 6.3. TokenRequest / bound token thay cho token tĩnh tồn tại dài

Trong các phiên bản Kubernetes hiện đại, token ServiceAccount được **project với thời hạn và binding phù hợp** thay vì dựa vào token Secret tự sinh tồn tại mãi theo mô hình cũ. Vẫn có trường hợp người quản trị **tạo long-lived token hoặc công cụ legacy**; cần inventory/loại bỏ theo hướng dẫn phiên bản. Việc xóa Pod hay ServiceAccount có thể ảnh hưởng tính hợp lệ của bound tokens theo semantics token validation, nhưng không cho phép suy tất cả **external token exchanges** đã bị thu hồi đồng thời.

### 6.4. RBAC là giới hạn quyền thật của token

Một token chỉ hữu ích theo **quyền được API server cho phép**. Không cấp quyền **get/list/watch Secrets trên toàn namespace/cluster** cho workload chỉ cần xem một ConfigMap. Không gán **cluster-admin** hoặc bind Role quá rộng chỉ để khắc phục lỗi kết nối SDK.

Kiểm tra đường quyền của người dùng có thể **create Pods, update Deployments, exec vào Pods hoặc mount Secrets**: quyền thao tác workload đôi khi tạo đường đọc bí mật gián tiếp ngay cả khi tài khoản **không được quyền get Secret**. Cần review **RBAC verbs, admission control và PodSecurity** cùng nhau.

## 7. Workload identity và cloud federation: tránh phát static cloud keys vào Pod

Một mẫu thiết kế tốt là workload được chứng thực bằng **danh tính ngắn hạn của nền tảng container**, sau đó xin **temporary cloud credentials** qua cơ chế federation, thay vì đưa access key dài hạn vào environment hoặc image.

~~~mermaid
sequenceDiagram
    participant W as Workload trong Pod
    participant K as Kubernetes / Token issuer
    participant I as Cloud identity service / STS
    participant C as Cloud API
    K-->>W: Bound workload token / assertion
    W->>I: Xin temporary token, kèm assertion hợp lệ
    I->>I: Kiểm tra issuer, audience, subject, trust binding, policy
    I-->>W: Temporary credential có scope và expiry
    W->>C: TLS + short-lived credential
    C->>C: IAM/resource authorization
    C-->>W: Response
~~~

### 7.1. Mỗi tầng có một điều kiện tin cậy riêng

| Tầng | Kiểm tra cần thiết | Lỗi thường gặp |
| --- | --- | --- |
| Kubernetes issuer | ServiceAccount/Pod identity và token hợp lệ | Mọi Pod dùng chung ServiceAccount |
| Federation trust | Issuer/OIDC, **audience, subject**, binding claims | Trust bất kỳ service account trong cluster |
| Cloud STS | Assertion, chính sách role và thời hạn credential | Cấp broad cloud admin thay cho tài nguyên cụ thể |
| Cloud resource | IAM, resource policy, network path | Tin token hợp lệ là được đọc tất cả buckets/databases |
| Application runtime | Refresh trước expiry, không log token | Cache token cũ hoặc sao chép ra disk/log |

**Token có audience dành cho Kubernetes API không đương nhiên phù hợp để xin cloud credential.** Federation cần cấu hình **audience/trust policy đúng** và ràng buộc đúng workload subject. Sai audience có thể làm ứng dụng lỗi; mở rộng audience không cần thiết lại tăng phạm vi có thể lạm dụng.

### 7.2. Triển khai trên các cloud phổ biến

Tên cơ chế và cấu hình phụ thuộc phiên bản và nền tảng, ví dụ:

- **AWS:** identity dành cho workloads chạy trên EKS có thể dùng cơ chế **IAM Roles for Service Accounts (IRSA)** hoặc cơ chế identity cho Pod khác do nền tảng hỗ trợ. Phải kiểm tra policy trust, mapping ServiceAccount↔role, token audience và IAM/resource policy.
- **Azure:** **Microsoft Entra Workload ID** hoặc cơ chế workload identity federation được hỗ trợ sử dụng issuer/subject/federated credential và managed identity/app identity theo thiết kế. Kiểm tra namespace/service account binding cùng quyền RBAC/cloud resource.
- **Google Cloud:** **Workload Identity Federation for GKE** hoặc cơ chế liên kết workloads với IAM principal/service account theo cấu hình; cần kiểm tra pool/provider mapping, KSA identity và IAM roles.

**Không chuyển nguyên YAML/annotation của một provider sang provider khác.** Trong cùng cloud, các mẫu triển khai có thể thay đổi theo service tier, region, identity plugin và phiên bản SDK. Bài này trình bày **security invariants**, không khẳng định một API cụ thể hiện có cùng flags trên mọi nền tảng.

### 7.3. Chọn workload identity theo ranh giới cấp quyền

Một ServiceAccount **orders-reader** chỉ cần đọc một bucket theo policy riêng; không gán cho tất cả Pods trong namespace. Khi Pod scale từ 2 lên 20 replicas, mỗi replica có thể xin **temporary credentials** nhưng quyền vẫn bị giới hạn bởi **identity và resource policy**; không được vì autoscale mà chia sẻ một static cloud admin token.

**Cảnh báo về shared node:** Bảo đảm ranh giới giữa Pod identities đòi hỏi **node/agent isolation, token delivery protection, metadata service access controls và runtime hardening**. Nếu node bị chiếm quyền ở mức đủ cao, kẻ tấn công có thể quan sát credentials của nhiều workloads; federated identity giảm static secret sprawl nhưng không làm node compromise trở nên vô hại.

## 8. mTLS trong service mesh: chứng chỉ riêng, khóa riêng và peer authorization

**Mutual TLS (mTLS)** dùng hai phía để xác thực và thiết lập kênh TLS. Trong môi trường container, một service mesh thường có **workload identity**, **CA hoặc identity control plane**, **data plane proxy** và cơ chế phân phối certificate/private key ngắn hạn.

~~~mermaid
flowchart LR
    CA["Identity CA / control plane"] -. "Cert & identity material" .-> PA["Proxy/agent A"]
    CA -. "Cert & identity material" .-> PB["Proxy/agent B"]
    A["Orders application"] --> PA
    PA ==>|"mTLS + peer identity"| PB
    PB --> B["Payments application"]
    PB -. "Authorization policy" .-> AZ["Allow Orders -> Payments API"]
~~~

### 8.1. Private key được đặt ở đâu?

Tùy mesh/agent/runtime:

- **Ứng dụng tự terminate mTLS:** private key có thể nằm trong process hoặc mounted file.
- **Sidecar proxy terminate mTLS:** key có thể nằm trong **proxy memory, secret delivery socket hoặc filesystem được quản lý**, tùy implementation.
- **Node/ambient proxy model:** secret/identity flow và trust boundary khác sidecar; cần đọc đặc tả của nền tảng đang triển khai.
- **External KMS/HSM signing:** trong một số thiết kế private key không export, nhưng ai **được phép yêu cầu ký/xác thực** bằng key vẫn cần bảo vệ.

**Không được kết luận rằng sidecar luôn cách ly bí mật khỏi app container.** Các containers trong một Pod thường **chia sẻ network namespace** và có thể chia sẻ volumes; mức độ cô lập process/files/Unix sockets tùy Pod settings, runtime và mesh. Một app compromise có thể sử dụng **luồng mạng hợp lệ của workload** ngay cả khi không lấy được private key.

### 8.2. SPIFFE identity và SVID

**SPIFFE** mô tả danh tính workload theo **SPIFFE ID**; **SVID** là chứng thực danh tính có thể ở dạng X.509 hoặc JWT tùy trường hợp. **SPIRE** là một implementation phổ biến có thể cấp SVID thông qua node/workload attestation, nhưng không phải service mesh nào cũng chạy SPIRE.

Ví dụ danh tính khái niệm:

~~~text
spiffe://corp.example.org/ns/prod-apps/sa/orders-api
spiffe://corp.example.org/ns/prod-apps/sa/payments-api
~~~

Service payments nên kiểm tra **SPIFFE ID/subject/authorization policy** của caller, không chỉ certificate có chữ ký bởi cùng CA. Hai workloads có cert hợp lệ trong cùng trust domain **không đương nhiên** được phép gọi mọi RPC của nhau.

### 8.3. Secret Discovery Service (SDS) và rotation

Một số proxy sử dụng **SDS hoặc cơ chế secret delivery tương tự** để nhận/update certificates, keys và trust bundles. Cần bảo vệ:

1. **Server/agent** trả secrets chỉ cho đúng workload identity.
2. **Local socket/API** chống truy cập từ process/container khác.
3. **TLS private key** không xuất vào access log, metrics labels hoặc debug dump.
4. **Certificate renewal** có thời gian overlap, chain/trust bundle được rollout theo thứ tự an toàn.
5. **Proxy health/reload/handshake metrics** cho thấy cert mới đã thực sự được dùng.
6. **Revocation/quarantine** khi workload bị compromise, không chỉ chờ expiry.

### 8.4. Trust bundle và cert rotation hai pha

Khi đổi CA/trust domain, làm đồng bộ sai thứ tự có thể khiến toàn bộ mTLS hỏng. Một lộ trình thông thường:

1. Phân phối **trust bundle mới** cho các bên kiểm tra peer, có thời gian overlap cần thiết với CA cũ.
2. Phát hành và rotate **workload certificates** sang CA mới.
3. Xác minh các đường mTLS gồm client/server, east-west, canary và DR.
4. Sau khi tất cả phụ thuộc đã chuyển và có phê duyệt, **loại CA cũ** khỏi trust stores theo chính sách.

**Giữ CA cũ vô thời hạn để tránh downtime** cũng tạo rủi ro. Overlap cần có mốc kết thúc và kiểm soát CA key compromise.

## 9. Cách đưa secrets vào container: chọn theo phạm vi và khả năng refresh

### 9.1. Đừng hardcode trong image hoặc Dockerfile

~~~dockerfile
# SAI: Không dùng trong thực tế.
# ENV ORDERS_API_TOKEN=real-production-token
# ARG CLOUD_SECRET_ACCESS_KEY=...

# MẪU TƯ DUY: image không chứa network credentials.
FROM registry.example.org/runtime/base:example
WORKDIR /app
COPY --chown=10001:10001 . /app
USER 10001:10001
ENTRYPOINT ["/app/orders"]
~~~

**Không đưa secret vào Dockerfile ARG/ENV, image layers, build logs, artifact metadata hoặc registry tags**. Xóa một dòng ở layer cuối không đảm bảo bí mật đã biến mất khỏi **các layer/cache trước**. Một runtime image chỉ nên chứa code/dependencies cần thiết; secrets được cấp sau dựa trên workload identity.

### 9.2. File mount từ một Secret đã tồn tại

Ví dụ Pod sử dụng một Secret **đã được một hệ thống được phê duyệt tạo ra**; không ghi password, token hay private key trực tiếp trong tài liệu:

~~~yaml
apiVersion: v1
kind: Pod
metadata:
  name: payments-client-example
  namespace: prod-apps
spec:
  serviceAccountName: orders-api
  automountServiceAccountToken: false
  securityContext:
    runAsNonRoot: true
    runAsUser: 10001
    runAsGroup: 10001
    fsGroup: 10001
    seccompProfile:
      type: RuntimeDefault
  containers:
    - name: app
      image: registry.example.org/orders:example
      securityContext:
        allowPrivilegeEscalation: false
        readOnlyRootFilesystem: true
        capabilities:
          drop: ["ALL"]
      volumeMounts:
        - name: peer-credentials
          mountPath: /var/run/credentials/payments
          readOnly: true
  volumes:
    - name: peer-credentials
      secret:
        secretName: payments-client-creds
        defaultMode: 0440
        items:
          - key: tls.crt
            path: tls.crt
          - key: tls.key
            path: tls.key
~~~

**Điều kiện:** Secret **payments-client-creds** và các keys được tạo sẵn, đúng namespace; image/ứng dụng biết đọc đường dẫn và có quyền filesystem; runtime/CSI/kubelet hỗ trợ chính sách owner/group tương ứng. **fsGroup và file ownership phải được kiểm tra trên cluster thật**; cấu hình ở trên là ví dụ có chủ đích, không phải template production vạn năng. Để reload certificate phải có cơ chế trong app/proxy hoặc rollout.

### 9.3. Mount bí mật vào đúng container

Trong Pod có nhiều containers (application, sidecar, metrics, init), **không mount secret volume vào tất cả** nếu chỉ proxy cần TLS key. Nếu một debug sidecar hoặc init container nhìn thấy cùng file, phạm vi bí mật đã mở rộng. Kiểm tra **volumeMounts của từng container, initContainers và ephemeralContainers** khi audit; một Pod-level volume definition không chứng minh mọi container đã mount nó.

### 9.4. Secret CSI và external stores

CSI driver/external secret provider có thể lấy bí mật từ Vault/cloud secret store và đặt vào Pod dưới dạng volume. Thiết kế tốt phải hỏi:

- **Identity nào** được dùng để lấy secret từ external store?
- Driver/agent chạy ở **node hay Pod**, có thể đọc secret của workload khác không?
- Dữ liệu có **sync thành Kubernetes Secret object** hay chỉ mount, và điều đó thay đổi rủi ro etcd ra sao?
- **Rotation poll interval**, file update semantics và readiness khi provider unavailable thế nào?
- Nếu secret manager bị lỗi, ứng dụng **fail closed hay dùng cache** bao lâu theo policy?
- Ai có quyền **đổi SecretProviderClass/config, mount path, role binding**?

**External secrets không đồng nghĩa “secret không bao giờ xuất hiện trên node”.** Đường dữ liệu, nơi lưu trên đĩa/RAM, quyền root/node và agent logs vẫn cần audit. Dùng **short-lived credentials** không loại bỏ nhu cầu least privilege.

## 10. Environment variables, logs, core dumps và bộ nhớ process

### 10.1. Vì sao env vars cần thận trọng?

Đặt token vào environment có thể tiện cho SDK, nhưng dễ bị rò qua:

- **Stack traces, exception diagnostics**, debugging/logging vô tình in environment.
- **Process inspection, /proc** hoặc tooling có quyền tương ứng trong container/node.
- **Crash/core dumps, heap dumps, profiling và support bundles** được đưa tới storage ngoài chính sách.
- Các subprocess/connections được tạo bởi app có thể **kế thừa environment** không cần thiết.
- Các công cụ vận hành hiển thị **Pod specs, debugging output** hoặc metadata nếu secret bị đặt trực tiếp bằng plaintext.

**Dùng envFrom/secretKeyRef không đồng nghĩa Secret được bảo vệ khỏi chính process nhận được giá trị**. Với các trường hợp cần rotate thường xuyên, env var còn có nhược điểm **giá trị đang chạy không tự cập nhật khi object Secret thay**; Pod cần restart/SDK refresh tùy cách thiết kế.

### 10.2. Quy tắc tránh ghi secret vào logs

| Dữ liệu | Có nên log? | Cách thay thế |
| --- | --- | --- |
| Raw bearer token, kubeconfig client key, private key | **Không** | Log credential type, issuer/subject đã xác minh và token ID hash được thiết kế an toàn nếu cần |
| HTTP Authorization, Cookie, Set-Cookie | **Không ở dạng raw** | Redaction trước khi gửi log, sampling cần thiết |
| Certificate public serial/expiry | Có thể, theo privacy policy | Ghi expiry và fingerprint public certificate để audit |
| Service identity, audience/scope names | Có thể theo quyền truy cập | Tránh PII/tenant secrets trong labels |
| Secret path trong filesystem | Hạn chế chia sẻ chi tiết nhạy cảm | Log trạng thái đã load/refresh, không log file content |
| Token expiry/reload result | **Có giá trị** | Ghi timestamp, success/failure, code lỗi và workload ID |
| TLS session keylog | **Không dùng Production trừ ngoại lệ cực kỳ kiểm soát** | Dùng metadata và staging/lab synthetic traffic |

**Không đưa nguyên token vào công cụ hash rồi mặc định bảo mật:** hash của token có thể tạo **stable correlator nhạy cảm**, và những token có entropy thấp có thể bị đoán theo cách khác. Cần thiết kế telemetry chuyên dụng với owner, retention và access controls; có thể sử dụng **issuer-provided safe token ID** nếu được hỗ trợ.

### 10.3. Redaction phải có kiểm thử

Một pipeline có filter **Authorization** trong JSON không có nghĩa đã xử lý **URL query, gRPC metadata, HTTP trailers, exception messages, tracing baggage hoặc framework debug dumps**. Test bằng **fake tokens có marker dễ nhận dạng** trong staging và xác minh mọi log sink/APM/tracing/alert/ticket đã redact.

### 10.4. Memory và zeroization

Trong runtime managed languages, **garbage collector** có thể sao chép objects hoặc giữ bytes trong RAM đến khi thu gom; cố tự xóa một string không đảm bảo xóa mọi bản sao. Nên **giảm số lần copy secret, tránh lưu lâu, dùng SDK/secret APIs được hỗ trợ, vô hiệu hóa debug keylog** và kết hợp **process isolation, swap/dump restrictions, encryption/permissions** theo OS/runtime. Không tự viết crypto để “giữ token trong RAM an toàn tuyệt đối”.

## 11. Runtime isolation: bảo vệ credential trước các đường vượt Pod

Kubernetes Pod không phải một máy ảo độc lập. Các containers thường chia sẻ **network namespace** và có thể có **volumes, process namespace hoặc host resources** được cấu hình chung; **container isolation không đảm bảo chống được host-level compromise**.

### 11.1. Những cấu hình làm tăng mức phơi lộ

| Tùy chọn/điểm yếu | Vì sao liên quan credential? | Phòng vệ |
| --- | --- | --- |
| **privileged: true** | Tăng khả năng truy cập host/kernel và resources của Pods khác | Mặc định cấm với app; ngoại lệ hạ tầng có quản trị |
| **hostPath** tới secrets/kubelet/runtime files | Có thể đọc dữ liệu host hoặc state của workload khác | Không mount host dirs nhạy cảm, dùng CSI/SDK được hỗ trợ |
| **Docker/container runtime socket** | API quản lý containers có thể cho phép kiểm soát cấp host tùy quyền | Không đưa socket vào Pod ứng dụng |
| **hostPID / shareProcessNamespace** | Mở rộng khả năng quan sát process/env/dump | Chỉ bật khi có nhu cầu và threat model phù hợp |
| **hostNetwork** | Pod dùng network namespace host, thay đổi firewall/port/metadata exposure | Chỉ cấp cho workload hạ tầng cần thiết |
| **allowPrivilegeEscalation** | Process có thể tận dụng khả năng tăng quyền theo điều kiện | Đặt false khi không có ngoại lệ |
| **extra capabilities** | Có thể ảnh hưởng kernel/network/process observation | Drop ALL và chỉ bổ sung capability cần thiết |
| **run as root** | Mở rộng quyền trong container và với mounted files | Non-root UID/GID, rootless runtime khi phù hợp |
| **writable root filesystem** | Dễ lưu token/credential và tạo persistence | Read-only rootfs với vùng ghi tối thiểu |
| **unconfined seccomp/AppArmor/SELinux** | Giảm biên độ hạn chế system calls/access | RuntimeDefault hoặc profile được đánh giá |
| **shared writable volume** | Secret hoặc file token có thể bị container khác đọc/sửa | Mount riêng read-only, permissions và owner |

### 11.2. Pod Security Standards và admission policies

Áp **Pod Security Standards** hoặc cơ chế admission policy tương đương để **hạn chế privileged, host namespaces, hostPath, capabilities và privilege escalation** ở namespace Production. Nhưng policy admission chỉ bảo vệ những gì nó kiểm tra; cần kiểm soát **ai có quyền tạo/sửa Pod specs, attach ephemeral containers, dùng exception hoặc đổi namespaces**.

### 11.3. Docker socket không phải chỉ “một cổng debugging”

Quyền truy cập **container runtime socket** thường có thể thực hiện thao tác tương đương quyền điều khiển containers trên node, do đó có rủi ro nghiêm trọng đối với **secrets và identity của nhiều workloads**. Không mount socket vào application container vì tiện thu logs/build images; dùng **controller/build service riêng có RBAC và isolation**.

### 11.4. Node compromise có phạm vi rộng hơn một Pod

Khi node bị chiếm ở mức admin/root, attacker có thể tiếp cận **runtime files, credential caches, Pod volumes, network traffic hoặc kubelet services** theo quyền và cấu hình. Phòng vệ cần **node hardening, trusted images, patching, dedicated node pools cho workloads nhạy cảm, admission controls, cloud IAM segmentation và node-level detection**. Không tuyên bố mTLS hoặc Secret volume đủ cách ly khỏi node admin.

## 12. NetworkPolicy và egress control: giảm khả năng lạm dụng credential

Ngay cả token hợp lệ cũng có thể bị sử dụng trái phép nếu một process bị chiếm có thể kết nối tới **mọi endpoint**. **Egress allowlist** theo workload/namespace/identity giúp giảm **đường sử dụng và đường đưa secret ra ngoài**, phối hợp với **API authorization và IAM**.

### 12.1. Phân biệt hai câu hỏi

- **Workload A có kết nối được tới service B không?** — network policy, firewall, route, CNI, service mesh network controls.
- **Danh tính A có được thực hiện operation X trên B không?** — mTLS identity, OAuth scopes, SPIFFE authorization, application/resource policy.

**Cho phép network path không tự cho phép API operation.** Ngược lại, token đủ quyền cũng không nên được sử dụng từ một network source/zone ngoài dự kiến nếu chính sách mạng có thể hạn chế.

### 12.2. Ví dụ NetworkPolicy cho Pod cần gọi identity broker và DNS

Đây là **ví dụ Kubernetes NetworkPolicy với nhãn namespace/Pods giả định**; cần chỉnh selectors, DNS implementation và port theo cluster thực. NetworkPolicy chỉ được thực thi nếu **CNI hỗ trợ**, và chính sách này không thay cơ chế network security ở cloud/VPC.

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: orders-restricted-egress
  namespace: prod-apps
spec:
  podSelector:
    matchLabels:
      app: orders
  policyTypes:
    - Egress
  egress:
    - to:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: platform-security
          podSelector:
            matchLabels:
              app: identity-broker
      ports:
        - protocol: TCP
          port: 443
    - to:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: kube-system
          podSelector:
            matchLabels:
              k8s-app: kube-dns
      ports:
        - protocol: UDP
          port: 53
        - protocol: TCP
          port: 53
~~~

**Quan trọng:** NetworkPolicy trên chỉ liệt kê **một số đích minh họa**. Nếu service còn cần **payments, database, cluster DNS ở hostNetwork/NodeLocal DNSCache hoặc external STS**, phải thiết kế rule theo đúng endpoint thực tế. Đừng copy manifest rồi dùng lỗi kết nối làm lý do mở egress ANY/ANY. NetworkPolicy chuẩn **không tự thực thi hostname/FQDN allowlist L7**, cũng không cung cấp chặn cloud metadata ở mọi CNI/topology.

### 12.3. Cloud metadata và SSRF

Một ứng dụng có khả năng fetch URL theo input chưa tin có thể bị **server-side request forgery (SSRF)** và truy cập metadata/identity endpoints hoặc những service nội bộ. Với Pod dùng cloud identity:

1. Kiểm soát **trusted URL destinations** và tránh proxy HTTP tùy ý từ request bên ngoài.
2. Áp **egress policy** ở Pod/node/VPC theo implementation, bảo vệ metadata service bằng cơ chế cloud hỗ trợ.
3. Đảm bảo metadata/STS chỉ cấp role của **đúng workload identity**, không cấp node admin credential cho mọi Pod.
4. Theo dõi các **token issuance, IAM access, unexpected metadata calls và network flows**.
5. Không phá chính cơ chế workload identity đang dùng khi chặn metadata; cần hiểu kiến trúc provider.

**Địa chỉ link-local như metadata endpoint không có cùng hành vi trên mọi cloud**. Không giả định một NetworkPolicy luôn chặn được đường tới metadata service qua host network hoặc provider-managed routing.

### 12.4. Service mesh egress gateway có ích nhưng không toàn năng

Egress gateway có thể **tập trung policy, mTLS origination, logging và route** cho một số traffic. Tuy nhiên phải đảm bảo **workload không thể đi vòng gateway** bằng direct IP, DNS alternative, hostNetwork hoặc CNI path khác. Nơi cần kiểm soát mạnh, kết hợp **network firewall/SG, CNI policy và identity** cùng kiểm thử DENY thực.

## 13. Quy trình cấp phát credential trước khi container được phép gọi mạng

### 13.1. Cấp phát từ identity thay vì từ mật khẩu chung

Một flow lý tưởng cho **orders → payments**:

~~~mermaid
sequenceDiagram
    participant O as Orders Pod
    participant I as Identity / Token service
    participant P as Payments API
    O->>I: Chứng minh workload identity
    I->>I: Kiểm tra subject, namespace, env và policy
    I-->>O: Short-lived credential cho audience payments
    O->>P: mTLS + token chỉ có scope đọc/tạo cần thiết
    P->>P: Verify issuer, audience, time và authorization
    P-->>O: Authorized response
~~~

**Không phải mọi hệ thống bắt buộc dùng cả mTLS và bearer token**: đôi khi **mTLS identity + application authorization** đủ, nơi khác cần **OAuth token** chứa delegation của người dùng. Phải chọn theo **trust model** và tránh token thừa tồn tại trong workload.

### 13.2. Các bước thiết kế cấp phát

1. **Identity inventory:** Pod/Deployment, ServiceAccount, namespace, cluster và owner.
2. **Resource mapping:** API, DB, bucket nào thực sự cần, method/resource scope.
3. **Trust binding:** Issuer, audience, subject, tenant/env và trust root.
4. **Credential lifetime:** TTL, refresh, expiry tolerance/clock skew và outage behavior.
5. **Delivery mechanism:** Projected token, identity SDK, CSI/secret volume hoặc agent socket theo năng lực.
6. **Permissions:** RBAC/IAM, filesystem UID/GID, socket access, namespace/Pod scope.
7. **Network:** DNS, endpoint, mTLS, egress and backend policies.
8. **Observability:** Issuance/refresh failure, certificate expiry, rejected auth, owner/audit.
9. **Revocation:** Xác định cách giảm quyền, khóa subject/issuer, revoke/rotate secrets.
10. **Validation:** ALLOW đúng workload và DENY workload/identity không được cấp quyền.

### 13.3. Tách danh tính theo môi trường

**Không dùng chung API key/CA issuance role hoặc ServiceAccount quyền rộng giữa Dev và Prod**. Một Pod Dev bị compromise không được có credential được Production payment API hoặc Prod database chấp nhận. Cả **issuer/trust policy, audience, RBAC/IAM, resource policies và network segmentation** cần phản ánh ranh giới môi trường.

## 14. Rotation: thay credential mà không phá kết nối hợp lệ

**Rotation** thay một bí mật hoặc certificate bằng phiên bản mới. Mục tiêu là giảm thời gian tồn tại của credential và hạn chế blast radius, nhưng nếu ứng dụng không reload, reverse proxies hoặc verifier chưa nhận trust material mới, rollout có thể gây outage.

### 14.1. Ba lớp khác nhau cần rotate

| Loại | Ai thực hiện | Rủi ro khi triển khai thiếu |
| --- | --- | --- |
| **Bearer access token** | SDK/identity provider/STS | 401 đột ngột, retry storm, token mới có audience sai |
| **TLS certificate & private key** | CA/mesh agent/CSI/app | mTLS handshake failures, không đồng bộ trust bundle |
| **Static shared secret/password** | Secret manager, DB/API và consumer | Old/new mismatch, stale Pods, database connection failures |

### 14.2. Mô hình rotation có overlap

~~~mermaid
flowchart LR
    A["Issue new secret / cert"] --> B["Update verifier trust / policy"]
    B --> C["Deliver new material to workload"]
    C --> D["Reload/reconnect; verify traffic"]
    D --> E["Stop using old credential"]
    E --> F["Revoke old material & cleanup"]
    F --> G["Audit complete: old still accepted?"]
~~~

**Thứ tự có thể khác nhau** giữa shared secrets, asymmetric certificates và provider-managed IAM tokens. Chẳng hạn JWT signing key rotation cần publisher/verifiers phối hợp qua JWKS cache; secret manager DB credential rotation có thể dùng user/password staging; CA rotation đòi hỏi trust bundle overlap. Luôn có **tài liệu protocol/provider** và **rollback được phê duyệt**.

### 14.3. Bài toán stale connections

Một ứng dụng có thể tiếp tục dùng **TCP connection pool** hoặc **TLS session** đã xác thực từ trước. Đổi file certificate hoặc IAM policy không nhất thiết làm **mọi kết nối hiện tại bị ngắt ngay**. Cần xác định các cơ chế:

- Client credential cache, connection pool max lifetime, forced reauthentication.
- TLS rehandshake/reconnect semantics theo protocol; gRPC long-lived streams.
- Revocation enforcement tại **server** và token introspection/cache TTL.
- Session termination/quarantine khi incident nghiêm trọng.

### 14.4. Chỉ số theo dõi rotation

| Metric | Ý nghĩa |
| --- | --- |
| Credential expires in | Thời gian còn lại trước expiry |
| Last successful refresh | Lần cuối workload nhận được credential mới |
| Refresh error rate | Lỗi contact secret manager/identity issuer |
| mTLS handshake failures | Sai trust, expired cert, identity mismatch |
| Access 401/403 theo workload | Token hết hạn/không đủ quyền hoặc policy sai |
| Old credential still used | Một instance chưa reload/đường fallback còn mở |
| Secret delivery lag | Thời gian từ rotate tới khi mount/app dùng phiên bản mới |
| Revocation effective time | Khoảng từ quyết định thu hồi tới lúc verifier từ chối |

**Không log raw token để nhận diện “old credential still used”.** Dùng credential version ID, cert serial/public fingerprint hoặc identity audit metadata được cung cấp và bảo vệ phù hợp.

## 15. Revocation và containment khi credential bị lộ

Không có một nút “revoke mọi credential” giống nhau trên tất cả các công nghệ. Cần tách **token bearer**, **Kubernetes token**, **cloud STS session**, **database password** và **mTLS certificate**.

| Credential | Cách giảm nguy cơ/thu hồi có thể có | Điều chưa nên giả định |
| --- | --- | --- |
| Kubernetes bound SA token | Cô lập Pod, hạn chế quyền SA/RBAC, xóa/recreate token-bound resource khi phù hợp, điều tra issuer | Mọi token copy đã bị chặn trên mọi external verifier tức thời |
| OAuth opaque token | Thu hồi qua authorization server/introspection theo hỗ trợ | Mọi resource server cập nhật cache ngay |
| Self-contained JWT access token | Disable identity/claims tại verifier hoặc blocklist theo kiến trúc, đợi TTL, rotate signing key khi cần | Rotate issuer key cho một token không ảnh hưởng rộng |
| Cloud STS temporary credential | Giảm quyền/deny resource/trust, cô lập workload, dùng mechanism revoke session theo provider nếu có | Đã được thu hồi mọi session chỉ nhờ restart Pod |
| mTLS certificate + key | Rotate/re-issue, block identity, trust/policy update, revocation nếu verifier có hỗ trợ | Certificate bị revoke sẽ luôn bị kiểm tra CRL/OCSP ở mọi connection |
| Database password | Rotate account/password, hủy phiên/connection khi được hỗ trợ, kiểm tra user privileges | Đổi password tự động hủy mọi session đang mở |
| Shared HMAC secret | Cấp secret mới, update verifier/consumer, ngừng chấp nhận old secret | Chỉ sửa env một Pod làm tất cả peers ngừng dùng old |

### 15.1. Thu hồi danh tính khác đổi network address

**Xóa một Pod** thường làm endpoint IP biến mất nhưng **credential đã bị copy** có thể vẫn dùng được tại API ngoài nếu token còn hiệu lực và verifier không biết Pod đã bị xóa/binding. **Chặn egress tại Pod** giúp cô lập workload còn hoạt động, nhưng nếu token đã bị đưa ra ngoài, cần **server-side revoke/deny** tại resource/identity plane.

### 15.2. Chuẩn bị emergency disable

Một hệ thống nhạy cảm nên có khả năng **chặn một workload identity cụ thể**, thu hẹp IAM scopes hoặc revoke service credential mà **không phải tắt toàn cluster**. Xác minh trước **who can revoke, emergency contacts, command/change mechanism, impact, evidence, và recovery path**. Không rotate cluster-wide signing keys để xử lý một app token lộ mà không phân tích blast radius.

## 16. Runtime network credential và authorization phía server

Mã hóa và identity **không đồng nghĩa quyền sử dụng dữ liệu**. Khi payments nhận mTLS certificate của orders, vẫn cần quyết định:

- Orders được **tạo payment**, hay chỉ được **đọc payment status**?
- API có kiểm tra **tenant/order ownership** và delegation của user không?
- Một workload Dev có mTLS certificate hợp lệ trong một trust domain chung có được gọi Prod không?
- Token có **audience=payments**, **scope=payment.read** và expiry phù hợp không?
- Một request đến qua **ingress ngoài dự kiến** có bị kiểm tra identity như đường chính không?

### 16.1. Không dùng một bearer token để chứng minh nhiều điều

Một **ServiceAccount token dành cho Kubernetes API** không phải mặc định là **user access token**, càng không phải bằng chứng người dùng cuối có quyền tới order cụ thể. **Delegated user identity** và **workload identity** cần được phân biệt, ký/kiểm tra đúng **issuer/audience/scopes**, tránh **confused deputy**.

### 16.2. Không suy quyền từ IP Pod

IP Pod thay đổi và có thể bị tái sử dụng. Một allowlist theo IP để xác định caller ở tầng ứng dụng dễ bị sai trong CNI/NAT/sidecar/scale. Với RPC nhạy cảm, ưu tiên **cryptographically authenticated workload identity** cộng authorization; IP/subnet policies vẫn hữu ích như **lớp phòng vệ bổ sung**.

### 16.3. Đồng bộ chính sách qua ingress/egress

Một app có thể được truy cập qua **ClusterIP, direct Pod IP, ingress, mesh service discovery hoặc node port**. Không nên đặt authentication chỉ ở một reverse proxy rồi cho **direct internal route bypass**. Đặc biệt secrets cho backend DB/cloud API phải gắn với **server-side policy** để bị từ chối khi sử dụng ngoài scope.

## 17. DNS, TLS, proxy, VPN và các bí mật kết nối khác

**Credential chỉ an toàn khi đúng peer được xác thực.** Một token ngắn hạn gửi qua HTTPS tới server giả nhưng client **bỏ qua certificate validation** vẫn có thể bị lấy cắp.

### 17.1. Bảo vệ TLS đến đúng đích

- Dùng TLS/mTLS theo protocol và threat model; kiểm tra **CA trust, hostname/SAN, expiry và peer identity**.
- Không dùng option kiểu **insecureSkipVerify** hoặc bỏ kiểm tra hostname trong Production chỉ để khắc phục lỗi cert.
- Không gắn **Authorization bearer token** vào request được phép **redirect tùy ý sang hostname khác**; kiểm tra hành vi client SDK.
- Cẩn thận với **egress proxy TLS termination**: proxy được cấp phép có thể nhìn plaintext; credential handling và log redaction phải đúng.
- Mỗi hop qua CDN/ingress/sidecar/reverse proxy là một **trust boundary độc lập**, cần peer validation và policy riêng.

### 17.2. DNS spoofing và service discovery

DNS/service discovery có thể quyết định nơi workload kết nối, nhưng **tên DNS trả địa chỉ không chứng minh peer identity**. Có thể dùng mTLS/service identity để chống gọi nhầm peer sau khi DNS/route thay đổi. DNS logs hỗ trợ điều tra nhưng không tự xác minh token đã gửi tới host nào khi dùng DoH/HTTP proxy/CDN shared IP.

### 17.3. IPsec/VPN và mạng cloud

Một workload chạy sau IPsec VPN hoặc private link vẫn cần **credential và application authorization** riêng. VPN bảo vệ/định tuyến đoạn mạng, không biến mọi Pod trong subnet thành cùng một identity đáng tin. Nếu mTLS private key hoặc API token bị copy ra khỏi subnet, phải **revoke tại dịch vụ đích**, không chỉ thay VPN route.

### 17.4. Ingress credentials và egress credentials

Phân biệt:

- **Ingress server credential:** private key/certificate để Pod/proxy chứng minh danh tính với caller.
- **Egress client credential:** token/cert để Pod gọi upstream.
- **Trust bundle:** CA/public keys để xác minh phía bên kia.

Nếu mọi service dùng chung **một bundle và private key** cho ingress/egress, compromised workload có thể mạo danh nhiều dịch vụ. Cấp **identity theo service/role và hướng quyền**, với certificate/EKU/scopes phù hợp giao thức được triển khai.

## 18. Giám sát misuse và phát hiện rò rỉ credential từ runtime

Để phát hiện token/certificate bị lạm dụng, chỉ nhìn **Network flow logs** là chưa đủ: flow logs cho IP/port/bytes/time/action, nhưng không cho biết **credential nào** được dùng trong HTTP/TLS và user nào được ủy quyền.

### 18.1. Kết hợp telemetry nhiều lớp

| Nguồn | Dữ liệu hữu ích | Giới hạn |
| --- | --- | --- |
| Kubernetes audit | SA và tài khoản nào gọi API, thay Secret/Role/Pod | Không thấy mọi traffic tới cloud/API bên ngoài |
| Cloud IAM/STS audit | Role assumption, subject, service, resource access | Không mặc định thấy token đã bị copy ngoài nền tảng |
| Mesh/proxy mTLS logs | Authenticated workload ID, peer, handshake outcome | Không chứng minh quyền sở hữu dữ liệu ở app |
| CNI/eBPF/flow logs | Source/destination IP/port, egress bất thường | Không chứa bearer token, có sampling/coverage gaps |
| Application access logs | Route, authenticated client/user, status/decision | Dễ lộ tokens nếu log headers không được redact |
| Secret manager audit | Ai/bằng identity nào đọc hoặc rotate secret | Đọc hợp lệ không chứng minh không bị lạm dụng |
| EDR/runtime detection | Process/file access, unexpected exec/dump, node events | Không luôn liên kết được chính xác với JWT/API operation |
| CI/CD/admission audit | Image/mount/RBAC policy và deployment changes | Chỉ là cấu hình, không chứng minh runtime không có compromise |

### 18.2. Những tín hiệu đáng điều tra

- Workload **vốn không cần Kubernetes API** đột nhiên gọi API để đọc Secret hoặc liệt kê namespaces.
- Một **ServiceAccount** được cấp Role mới hoặc binding thay đổi ngoài quy trình.
- Pod không có nhiệm vụ quản trị truy cập **metadata, identity broker hoặc secret manager** bất thường.
- Credential của service A được dùng từ **network origin, region, cluster hoặc workload identity** không phù hợp với policy.
- **mTLS handshake failures/unknown peer ID** tăng đột biến ngay sau certificate/CA change.
- Runtime logs/trace exporter phát hiện các **synthetic secret markers** trong staging hoặc scanner an toàn cảnh báo rò secrets thật đã được kiểm soát.
- Container bắt đầu có **unexpected exec, privilege escalation, hostPath mount hoặc socket access**.
- Egress tới **destination mới** cùng thời điểm IAM token issuance tăng mà không có change ticket.

### 18.3. Tránh gán nhãn “token bị đánh cắp” quá sớm

Một token được dùng từ IP lạ có thể do **NAT/LB, DR failover, cloud region mới, proxy egress hoặc thay đổi route hợp lệ**. Cần xác minh **issuer logs, workload/pod UID, cloud role session, authenticated client, NAT mapping, control-plane changes và traffic baseline**. Nếu evidence thiếu, ghi **suspected misuse** và mở điều tra; không coi một IP khác là bằng chứng hoàn tất.

### 18.4. Metrics tối thiểu

| Metric | Cảnh báo/ý nghĩa |
| --- | --- |
| Certificate/token expires soon | Ngăn expiry outage |
| Identity issuance failures | Workload không lấy được credential mới |
| Secrets read by unusual identity | Bất thường cần review access |
| RBAC/IAM policy drift | Quyền rộng hơn baseline |
| mTLS peer authorization denies | Caller không thuộc allowed identity |
| API 401/403 by service ID | Audience/scope/expiry hoặc misuse |
| Egress to unexpected destinations | Có thể là exfiltration/misconfiguration |
| Runtime debug/keylog enabled | Nguy cơ lộ raw traffic/session secrets |
| Secret present in support artifacts | Lộ qua logs/dumps/ticket |
| Revoked credential still accepted | Gap trong verifier cache/revocation |

## 19. Runbook xử lý khi nghi network credential bị lộ

**Mục tiêu:** hạn chế việc dùng credential bị lộ, xác định phạm vi quyền và lưu lượng đã bị sử dụng, bảo toàn bằng chứng, phục hồi dịch vụ hợp lệ và ngăn tái diễn. Không cố giải quyết bằng cách **xóa log, đổi Pod name hoặc chỉ restart container**.

### 19.1. Phân vai

| Vai trò | Trách nhiệm |
| --- | --- |
| Incident commander | Ưu tiên rủi ro, quyết định cô lập/gián đoạn, điều phối và thời gian |
| SOC/DFIR | Bằng chứng, timeline, identity usage, endpoint/network investigation |
| Platform/Kubernetes team | Pod/node isolation, RBAC/admission, workload rollout, network policies |
| IAM/PKI/Secret manager team | Revoke/rotate token/key/cert, kiểm tra trust và blast radius |
| Application owner | Business SLI, retry behavior, authentication/authorization và recovery |
| Cloud/network team | Cloud IAM/STS, SG/firewall/VPN/NAT/flow logs và đường bypass |
| Data/privacy/legal owner | Data classification và nghĩa vụ thông báo nếu incident yêu cầu |

### 19.2. Năm giai đoạn

~~~mermaid
flowchart TD
    A["Phát hiện token/key có thể lộ"] --> B["Xác định loại bí mật & identity"]
    B --> C["Cô lập nguồn rò, giữ bằng chứng"]
    C --> D["Revoke/deny/rotate tại verifier và issuer"]
    D --> E["Đối chiếu IAM, K8s, network, app logs"]
    E --> F["Phục hồi workload từ nguồn tin cậy"]
    F --> G["Kiểm tra old credential denied và app healthy"]
    G --> H["Postmortem, hardening, retention và owners"]
~~~

**Trình tự có thể thay đổi khi đang có truy cập trái phép nghiêm trọng.** Việc thu hồi credential đôi khi cần ưu tiên ngay để giảm thiệt hại; đồng thời vẫn phải có **forensic preservation tối thiểu** theo khả năng và kế hoạch incident. Không kéo dài compromise chỉ để có đủ log.

### 19.3. Thu thập chứng cứ không làm lộ thêm bí mật

| Bằng chứng | Ghi lại | Không nên đưa vào ticket chung |
| --- | --- | --- |
| Kubernetes | Namespace, Pod UID, node, ServiceAccount, RoleBinding, owner, timeline | Raw projected token, Secret data |
| Identity/STS | Issuer, audience, subject, role ID, issuance time, policy revision | Bearer token hoặc session secret |
| mTLS/PKI | Public certificate serial, fingerprint, expiry, trust domain | Private key, decrypted traffic keys |
| Cloud/secret manager | IAM access events, secret version IDs, rotation/audit, object access | API keys, database password |
| Runtime | Pod restart/exec events, image digest, mounts, privilege settings | Heap dump chứa secrets trừ khu vực evidence được khóa |
| Network | Flow source/dest, port, NAT/LB, egress path, VPN tunnels | Packet payload/tokens ngoài phạm vi được phép |
| Application | Request ID, verified identity, endpoint, 401/403, resource decisions | Authorization/Cookie headers, PII raw |

### 19.4. Tình huống cụ thể: JWT access token lộ

1. Xác định **issuer, audience, subject, scopes, expiry, token type và nơi có bản sao**. Nếu token lộ trong log, bảo vệ và hạn chế truy cập log đó.
2. Áp **deny/revocation** theo khả năng verifier, giảm quyền/disable principal hoặc revoke session; phân biệt **self-contained JWT** với **opaque introspected token**.
3. Cô lập container/process đã lộ, tắt export nhạy cảm, cập nhật secret injection và policy.
4. Xem **API usage theo token identity/subject, resource/tenant access, nguồn/region, thời gian và audit**; không cần sao chép raw token vào SIEM.
5. Cấp credential mới cho workload sạch, xác minh correct audience/scope và application SLI.
6. Test **bản sao token cũ bị từ chối theo cơ chế được phê duyệt**, đồng thời không ghi nó vào log hay truyền trong kênh không an toàn.

### 19.5. Tình huống cụ thể: mTLS private key bị lộ

1. Xác định **workload identity, certificate serial, issuer/CA, expiry, pods/instances** dùng key.
2. Cách ly điểm lộ; thay key/certificate và cập nhật **server-side authorization hoặc trust controls** để hạn chế identity cũ.
3. Xem **CA key có bị lộ không**. Nếu chỉ một leaf key bị lộ thì **không mặc định** phải rotate cả CA; nếu CA key thực sự bị lộ, blast radius lớn hơn.
4. Kiểm tra **revocation enforcement và existing TLS sessions**, không suy xóa Pod là tất cả kết nối đã đóng.
5. Xác minh từng hop mesh/TLS **còn xác thực đúng peer** và không chấp nhận identity cũ ngoài chính sách.
6. Đánh giá lưu lượng trái phép đã thực hiện bằng **proxy logs, API auth, workload audit và flow logs**.

### 19.6. Tình huống cụ thể: ServiceAccount token có quyền rộng

1. Inventory những **Role/ClusterRoleBindings**, group bindings, cloud federation grants liên quan SA.
2. Tạm dừng/quarantine workload, thu hẹp **RBAC/IAM và external trust** đúng scope.
3. Tìm **Kubernetes API audit** cho những request bất thường từ SA, đặc biệt get/list/watch Secrets, create pods, exec, modify workload.
4. Kiểm tra **bound token issuance, Pod UID, kubelet logs, ServiceAccount lifecycle và audit** nếu có.
5. Deploy workload với **SA quyền tối thiểu**, automount false nếu không cần hoặc scoped projected token nếu có.
6. Test RBAC **ALLOW đúng action và DENY secrets/admin actions**, rồi quan sát SDK connectivity.

### 19.7. Điều kiện kết thúc incident

- Nguồn rò được **khắc phục**, workloads/hosts nghi compromise được xử lý bằng phương án tin cậy.
- Credential hoặc quyền bị lộ đã được **vô hiệu hóa/giảm phạm vi** tại verifier, không chỉ đổi file.
- Từng identity/role có **owner, affected resources và last authorized use**.
- **Logs, artifacts, secrets** không tiếp tục phát tán qua incident ticket/pipeline.
- Kết nối hợp lệ **TLS/mTLS/API/DB** phục hồi trong SLO; những request trái quyền **DENY**.
- Có danh sách **remaining gaps**: token chưa thể revoke tức thời, session chưa kết thúc, log sampling, external provider caches.
- Postmortem có **action owners, kiểm soát phòng ngừa, deadline và regression tests**.

## 20. Case study A: ServiceAccount token của một Pod bị gửi vào log

**Bối cảnh giả định:** Một ứng dụng quản lý đơn hàng sử dụng thư viện Kubernetes SDK dù chức năng chính không cần Kubernetes API. Pod tự mount ServiceAccount token, trong một exception logger đã vô tình in một HTTP request chứa **Authorization: Bearer**. Log được chuyển tới một hệ thống quan sát có nhiều người có quyền xem.

### 20.1. Đánh giá rủi ro

| Câu hỏi | Điều cần làm rõ |
| --- | --- |
| Token có thực sự xuất hiện? | Xác minh trong restricted evidence channel, không copy raw token |
| Token là loại nào? | Projected bound token hay credential legacy, issuer/audience/expiry |
| ServiceAccount có quyền gì? | RBAC get/list/watch Secrets, Pod exec, config changes và bindings |
| Log đã đi đâu? | Log agents, aggregator, retention, export, alert/webhook, downloads |
| Ai có thể đọc log? | IAM/RBAC, external vendors, support tickets |
| Có dấu hiệu misuse? | Kubernetes audit, cloud STS nếu federation, unusual API calls |

### 20.2. Các hành động

1. Hạn chế quyền truy cập log bị ảnh hưởng; xác định **toàn bộ nơi token đã được nhân bản** theo data lineage.
2. Thu hẹp ServiceAccount RBAC ngay nếu quá rộng, cô lập Pod và xác minh issuer/expiry/revoke options.
3. Nếu app không cần Kubernetes API, **tắt automount** và bỏ SDK không cần, hoặc tách chức năng sang workload có identity riêng.
4. Sửa **log redaction** ở HTTP clients/framework và test với token giả.
5. Rotate/revoke phù hợp, kiểm tra **credential cũ đã bị từ chối** và ứng dụng vẫn phục vụ đúng request.
6. Rà soát **đường đọc Secret gián tiếp** qua quyền tạo Pod/mount thay vì chỉ kiểm tra get Secret.

### 20.3. Bài học

**Token ngắn hạn không bù được một logging pipeline công khai rộng**. Nếu workload không cần Kubernetes API, cách bảo vệ mạnh hơn là **không cấp credential ngay từ đầu**, rồi ràng buộc quyền và log hygiene cho những phần thật sự cần token.

## 21. Case study B: certificate mTLS hết hạn sau khi sidecar không reload

**Bối cảnh giả định:** Service mesh cấp certificate có TTL ngắn cho Pod **payments**. Identity agent đã cập nhật file/secret và log báo “rotation success”, nhưng một phiên bản proxy cũ **vẫn giữ TLS context trước đó**. Sau khi certificate cũ hết hạn, một số RPC từ **orders** tới payments bắt đầu thất bại.

### 21.1. Điều không được suy đoán

- **File timestamp đổi** chưa chứng minh proxy đã đọc key mới.
- **CA cấp certificate mới** chưa chứng minh tất cả peers có **trust bundle** phù hợp.
- **Readiness trả OK** chưa chứng minh mTLS giữa hai workloads thành công.
- **HTTP 503** từ gateway không chứng minh backend application process chết.

### 21.2. Bằng chứng và xử lý

| Nguồn | Cần xem |
| --- | --- |
| Identity/CA logs | Cert issued time, serial, notBefore/notAfter, workload identity |
| Sidecar/agent | Secret delivery event, reload success/failure, SDS or equivalent status |
| TLS metrics | Handshake failures: expired cert, unknown CA, identity mismatch |
| Kubernetes events | Pod restart, image digest, config/secret mount behavior |
| Application | RPC error types, retry, business SLI, active connections |
| Security policy | Allowed peer identities, trust bundle revision và rollout |

**Khắc phục:** canary restart/reload proxy theo cơ chế được hỗ trợ, kiểm tra handshake thực trên luồng được phép, phối hợp CA trust rollout có overlap và xác nhận **old certificate không còn được dùng** sau hạn được phê duyệt. Không **tắt peer verification** hoặc cho mọi trust domain qua mTLS chỉ để bỏ lỗi.

### 21.3. Bài học

**Rotation có ba thành phần:** phát hành credential mới, đưa vào runtime và **thực sự sử dụng trong kết nối mới**. Muốn SLO ổn định cần cảnh báo trước expiry và test **mTLS end-to-end**, không chỉ kiểm file.

## 22. Case study C: nhầm quyền cloud identity khi dùng chung ServiceAccount

**Bối cảnh giả định:** Dev và Prod workloads nằm trong hai namespaces nhưng cùng sử dụng một ServiceAccount name và identity trust policy quá rộng. Một Dev Pod không cần truy cập dữ liệu khách hàng lại có thể xin temporary credentials cho một cloud role đọc production storage.

### 22.1. Vì sao đây là lỗi identity, không chỉ firewall?

Một **cloud role** được cấp dựa trên điều kiện **OIDC issuer/audience/subject** và trust binding. Nếu trust cho phép quá rộng, token hợp lệ từ Dev có thể được chấp nhận như Prod. Dù ban đầu NetworkPolicy chặn egress, attacker có thể tìm **một allowed route, proxy hoặc external location** nơi cloud token được dùng, nếu đã lấy được token hoặc quyền cloud tương ứng.

### 22.2. Bằng chứng và cách giảm rủi ro

1. Đối chiếu **OIDC trust conditions** và subject thật theo namespace/ServiceAccount/cluster.
2. Kiểm tra **role/resource IAM permissions**; vai trò Prod có bị dùng bởi Dev caller không?
3. Ràng buộc federation theo **đúng workload identity**; tách roles và resources giữa environments.
4. Kiểm tra Pod không tự lấy token dành cho cloud broker nếu không cần, và source/service restrictions.
5. Giảm blast radius bằng **resource-level permissions, permission boundaries và deny conditions** theo hỗ trợ.
6. Correlate **STS/identity audit, cloud object access logs, workload/Pod identity và flow telemetry**.
7. Test **Dev→Prod DENY**, Prod được phép đúng tài nguyên ALLOW, và unknown workload DENY.

**Bài học:** **Danh tính ServiceAccount chỉ có ý nghĩa trong ranh giới issuer/cluster/trust binding được kiểm chứng**. Tên giống nhau không phải bằng chứng cùng quyền, nhưng **trust quá rộng** có thể biến một token Dev thành cloud access ngoài chủ đích.

## 23. Thực hành Python offline: đánh giá cấu hình và vòng đời credential

Bài lab này **chỉ phân tích dữ liệu Python giả lập trong bộ nhớ**, không đọc filesystem, không mở socket, không gọi Kubernetes/cloud API, không sinh/giải mã token và không sửa tài nguyên. Mục tiêu là **đánh dấu những cấu hình cần review**, không tự kết luận một workload an toàn hay đã bị xâm nhập.

### 23.1. Mô hình đầu vào

Mỗi workload có:

- **namespace và owner** để phân định môi trường.
- Cờ **automount ServiceAccount token**; riêng trường hợp cần token tường minh phải được đánh giá theo audience/role.
- Có/không **static credential trong environment**.
- Có/không **mTLS key volume**, chính sách read-only và bảo vệ quyền file.
- **Privilege/hostPath/runtime socket** để nhận diện khả năng mở rộng blast radius.
- Danh sách **credential audiences** dự kiến.
- Số ngày **còn lại trước khi certificate hết hạn** (số giả định).

~~~python
from dataclasses import dataclass


@dataclass(frozen=True)
class Workload:
    name: str
    namespace: str
    needs_kubernetes_api: bool
    automount_service_account_token: bool
    static_token_in_env: bool
    tls_key_mounted: bool
    tls_key_volume_read_only: bool
    privileged: bool
    runtime_socket_mounted: bool
    cloud_role: str
    allowed_audiences: tuple[str, ...]
    cert_days_remaining: int | None


def review(workload: Workload) -> list[str]:
    """Các tín hiệu review; không đọc bí mật thật và không xác minh cluster."""
    findings: list[str] = []

    if (
        workload.automount_service_account_token
        and not workload.needs_kubernetes_api
    ):
        findings.append("UNNEEDED_K8S_API_TOKEN")

    if workload.static_token_in_env:
        findings.append("STATIC_TOKEN_ENV_RISK")

    if workload.tls_key_mounted and not workload.tls_key_volume_read_only:
        findings.append("TLS_KEY_VOLUME_NOT_READ_ONLY")

    if workload.privileged:
        findings.append("PRIVILEGED_RUNTIME")

    if workload.runtime_socket_mounted:
        findings.append("RUNTIME_SOCKET_EXPOSURE")

    if (
        workload.namespace.startswith("dev")
        and workload.cloud_role == "prod-storage-reader"
    ):
        findings.append("DEV_TO_PROD_CLOUD_ROLE")

    if len(set(workload.allowed_audiences)) > 1:
        findings.append("MULTIPLE_AUDIENCES_REVIEW")

    if (
        workload.cert_days_remaining is not None
        and workload.cert_days_remaining <= 7
    ):
        findings.append("CERT_EXPIRY_SOON")

    return findings


examples = [
    Workload(
        name="orders",
        namespace="prod-apps",
        needs_kubernetes_api=False,
        automount_service_account_token=False,
        static_token_in_env=False,
        tls_key_mounted=True,
        tls_key_volume_read_only=True,
        privileged=False,
        runtime_socket_mounted=False,
        cloud_role="none",
        allowed_audiences=("payments-api",),
        cert_days_remaining=45,
    ),
    Workload(
        name="legacy-debug",
        namespace="dev-tools",
        needs_kubernetes_api=False,
        automount_service_account_token=True,
        static_token_in_env=True,
        tls_key_mounted=True,
        tls_key_volume_read_only=False,
        privileged=True,
        runtime_socket_mounted=True,
        cloud_role="prod-storage-reader",
        allowed_audiences=("payments-api", "cloud-sts"),
        cert_days_remaining=2,
    ),
]

for workload in examples:
    print(workload.name, review(workload))

assert review(examples[0]) == []
assert "DEV_TO_PROD_CLOUD_ROLE" in review(examples[1])
assert "CERT_EXPIRY_SOON" in review(examples[1])
assert "RUNTIME_SOCKET_EXPOSURE" in review(examples[1])
~~~

Kết quả mong đợi:

~~~text
orders []
legacy-debug ['UNNEEDED_K8S_API_TOKEN', 'STATIC_TOKEN_ENV_RISK', 'TLS_KEY_VOLUME_NOT_READ_ONLY', 'PRIVILEGED_RUNTIME', 'RUNTIME_SOCKET_EXPOSURE', 'DEV_TO_PROD_CLOUD_ROLE', 'MULTIPLE_AUDIENCES_REVIEW', 'CERT_EXPIRY_SOON']
~~~

### 23.2. Vì sao đây không phải công cụ kiểm toán bảo mật?

1. **Không parse manifest thật**, không đọc RBAC/IAM, PodSecurityAdmission, NetworkPolicy hoặc trust relationships.
2. Cờ **automount** có thể được áp ở Pod/ServiceAccount, có projected token tường minh và các integrations riêng; lab không tính **effective** configuration.
3. **Empty findings không chứng minh an toàn**. Một role có thể có permissions nguy hiểm dù có tên nghe hợp lý; audience string có thể được verifier kiểm sai.
4. **static_token_in_env** là nhãn giả định; lab không quét token trong môi trường thật và không xử lý secret exfil.
5. **Namespace startswith dev** chỉ là heuristic bài tập; Production cần **namespace labels, cluster/account ID, policy và identity provider trust**.
6. **Certificate TTL** chỉ là một chỉ số: có thể sắp hết hạn nhưng rotation tự động hoạt động; ngược lại cert còn 45 ngày vẫn có thể bị lộ private key.
7. **TLS key volume read-only** không ngăn process đã bị compromise **đọc file**; phải hạn chế quyền, identity và thư mục mount.
8. Không có network connection, issuer verification, workload attestation hoặc thực thi revoke trong ví dụ.

### 23.3. Bài tập mở rộng

1. Thêm trường **serviceAccountName, projectedTokenAudience, issuer**, cảnh báo nếu token được gửi tới service khác audience.
2. Thêm **credential_expiry** theo UTC, dùng timezone-aware timestamps và clock-skew tolerance.
3. Thêm trường **RBAC verbs/resources** và cảnh báo nếu app thường có **get/list/watch secrets** hoặc **create privileged Pods**.
4. Thêm **environment/cluster/account** để phân biệt Dev/Prod thay vì dựa vào tên namespace.
5. Phân biệt **static API key** với **short-lived token lấy từ workload identity**, và đánh giá refresh/revoke plan.
6. Thêm **network_egress_destinations** và policy mapping; một token audience hẹp vẫn đáng review nếu Pod có ANY/ANY egress.
7. Tạo bài tập canary giả lập **certificate rotation**: cert cũ và mới cùng hợp lệ trong overlap window, rồi old cert bị từ chối sau deadline.
8. Thêm nhãn **confidence level**: những heuristic nào chỉ là gợi ý, những điều nào có thể được chứng minh từ config.

## 24. Ma trận kiểm thử bảo vệ credential trong runtime

Chỉ kiểm thử trên **lab, staging hoặc hệ thống được cấp quyền**; không tự trích xuất secrets từ Pods người khác, không tạo payload khai thác, không gửi credentials thật tới endpoint thử, không dùng quyền cluster-admin để kiểm thử ứng dụng thông thường. Các ca có thay đổi RBAC/IAM/NetworkPolicy hoặc gây tắt kết nối phải có **approval, scope, canary và rollback**.

| Test ID | Tình huống | Kỳ vọng / bằng chứng |
| --- | --- | --- |
| NC-01 | Pod không cần Kubernetes API | ServiceAccount token không bị tự mount theo effective config |
| NC-02 | Pod cần projected SA token | Token có audience và expiry phù hợp, app refresh thành công |
| NC-03 | Token dùng sai audience | API/identity broker từ chối |
| NC-04 | Token hết hạn trong lab | API từ chối, workload refresh an toàn không retry vô hạn |
| NC-05 | ServiceAccount không có get/list Secrets | Kubernetes API DENY kể cả khi workload có token hợp lệ |
| NC-06 | ServiceAccount không có create privileged Pods | Kubernetes API DENY thao tác vượt quyền |
| NC-07 | User có quyền sửa Pod spec | Review khả năng mount/read Secrets gián tiếp và admission controls |
| NC-08 | Dev workload thử role/trust của Prod | Cloud STS/IAM DENY không đúng subject/namespace/role |
| NC-09 | Workload hợp lệ xin temporary cloud credential | ALLOW đúng audience, resource policy và TTL |
| NC-10 | Static credential không nằm trong image/layers | Secret scan/build review với dữ liệu giả, không lộ keys |
| NC-11 | Registry pull credential | Chỉ node/kubelet path cần thiết có quyền pull, app container không bị cấp vô cớ |
| NC-12 | Secret từ environment trong runtime | Có risk register; không log/display, rotation/restart semantics rõ |
| NC-13 | Mounted TLS private key | Chỉ đúng container nhận volume, read-only và quyền file phù hợp |
| NC-14 | Secret file bị rotate | App/proxy thực sự reload credential mới trước expiry |
| NC-15 | Mount Secret qua subPath trong lab | Phát hiện không cập nhật tự động như ordinary secret volume |
| NC-16 | External CSI/secret provider unreachable | Hành vi fail-closed/cache theo policy; không phát tán fallback secrets |
| NC-17 | Pod cố dùng privileged/hostPath ngoài ngoại lệ | Admission/RBAC/DENY theo môi trường |
| NC-18 | Application Pod cố mount runtime socket | DENY bằng policy, không cấp host control |
| NC-19 | Non-root, read-only rootfs và capabilities | Pod chạy được workload, có profile bảo mật đúng |
| NC-20 | Sidecar chỉ cần mTLS key | App/debug containers không nhận key file/socket trái scope |
| NC-21 | Workload mTLS đúng peer ID | TLS handshake và application authorization ALLOW |
| NC-22 | Workload mTLS sai peer ID/trust domain | DENY dù network reachability hợp lệ |
| NC-23 | mTLS certificate gần hết hạn | Alert trước hạn, auto-renew và handshake mới thành công |
| NC-24 | Thay trust bundle/CA có overlap | Không tạo outage ngoài mục tiêu; CA cũ hết hạn chính sách bị loại |
| NC-25 | Revoked/blocked workload identity | Kết nối/API mới bị từ chối theo supported revocation semantics |
| NC-26 | Existing sessions sau credential rotation | Session lifetime/forced reconnect được đo, không suy revoke tức thời |
| NC-27 | Container không được truy cập metadata service | Network/identity controls DENY đúng cách; workload identity hợp lệ vẫn hoạt động |
| NC-28 | App bị thử SSRF bằng dữ liệu giả trong lab | Không fetch endpoints không được phép, không lộ token |
| NC-29 | Workload egress ngoài allowlist | NetworkPolicy/SG/eBPF DENY, các đường bypass được rà soát |
| NC-30 | DNS cho workload bị hạn chế egress | Resolver traffic cần thiết ALLOW, các nguồn khác DENY |
| NC-31 | Dev/Guest → Prod API/database | DENY theo identity và network policy |
| NC-32 | Log pipeline nhận fake Authorization marker | Marker được redact ở app/proxy/tracing/alert sinks |
| NC-33 | Support bundle/core dump trong lab | Không xuất raw credentials ra hệ thống ticket không có quyền |
| NC-34 | Workload gọi Kubernetes API bất thường | Audit/detection ghi identity/verb/resource mà không ghi bearer token |
| NC-35 | Cloud STS session từ môi trường không phù hợp | Identity audit phát hiện, policy DENY/triage đúng |
| NC-36 | Secret manager permission thay đổi | Alert về policy drift và access, không phải raw secret material |
| NC-37 | Pod restart/scale/move node | Credentials được cấp lại đúng identity, không chia sẻ stale token |
| NC-38 | Multi-region/DR service identity rollout | Issuer, trust, audience và permissions không trôi khỏi policy |
| NC-39 | Emergency revoke credential giả lập | Actor không được phép DENY, workload hợp lệ được phục hồi |
| NC-40 | Certificate/private key leak tabletop | Đánh giá identity, session, revocation và evidence, không hứa PFS bảo vệ key bị lộ |
| NC-41 | Security incident thay ServiceAccount RBAC | Kiểm thử ALLOW cần thiết và DENY admin/secrets ngoài quyền |
| NC-42 | Kubernetes Secret encryption at rest | Kiểm tra cấu hình provider/KMS và backup permissions theo policy |

### 24.1. Mẫu hồ sơ cho mỗi ca

~~~text
TEST ID / CHANGE ID:
ENVIRONMENT / NAMESPACE / CLUSTER / NODE:
WORKLOAD NAME / POD UID / SERVICEACCOUNT:
CREDENTIAL TYPE / ISSUER / SUBJECT / AUDIENCE / TTL:
SECRET DELIVERY: projected file / CSI / broker / env / agent
KEY MATERIAL ACCESS: user/group/volume/container scope (NO SECRET VALUES)
RBAC/IAM + NETWORK POLICY REVISION:
EXPECTED APPLICATION ALLOW / FORBIDDEN DENY:
OBSERVED AUTH/TLS STATUS / K8S AUDIT / STS AUDIT:
ROTATION/REVOCATION OUTCOME / VALIDATION WINDOW:
LOG REDACTION CHECK:
OWNER / APPROVER / ROLLBACK / REMAINING RISK:
~~~

### 24.2. Ba tầng bằng chứng

1. **Static:** Pod YAML, RBAC, IAM trust policy, admission controls, KMS/Secret manager settings và image supply-chain review.
2. **Runtime:** Mount/UID/GID/memory/agent behavior theo quyền, token issuance, certificate reload, proxy session và identity use.
3. **End-to-end:** Correct workload truy cập đúng API tài nguyên **ALLOW**; sai audience, identity, tenant hoặc network zone **DENY**, gồm cả sau rotate/failover.

**Một YAML có securityContext đẹp không chứng minh runtime an toàn tuyệt đối.** CNI/admission/secret provider cần thực thi đúng, IAM resource policy phải hẹp và các đường vòng phải được kiểm thử.

## 25. Kiến trúc tham chiếu và quy trình triển khai an toàn

Một ứng dụng Production có network credentials tốt không phải ứng dụng dùng nhiều công nghệ nhất, mà là ứng dụng **nhận đúng credential cần thiết, chỉ gửi đến đúng peer, dễ thu hồi và có đủ bằng chứng khi sự cố xảy ra**.

### 25.1. Kiến trúc gợi ý

~~~mermaid
flowchart LR
    U["User/API Client"] -->|"HTTPS"| E["API Gateway / Auth / WAF"]
    E --> O["Orders Pod: dedicated ServiceAccount"]
    K["K8s Token issuer"] -. "Bound token" .-> O
    I["Workload identity / STS"] -. "Scoped temporary access" .-> O
    C["Mesh CA / agent"] -. "Short-lived SVID / mTLS" .-> O
    O ==>|"mTLS, peer authZ"| P["Payments Pod"]
    O -->|"Restricted egress + IAM"| S["Cloud storage / broker"]
    O -. "Metadata + secure audit" .-> L["SOC: K8s/IAM/flow/app logs"]
    P -. "Peer auth/metrics" .-> L
~~~

Các bất biến nên được giữ:

1. **Không có shared Production static key** trong image, ConfigMap, repository hoặc debug logs.
2. **ServiceAccount** của Orders không được quyền quản trị Kubernetes nếu không có use case được phê duyệt.
3. **Cloud role** được cấp theo workload identity (issuer+subject+audience) và chỉ cho phép tài nguyên cần thiết.
4. **mTLS identity** chứng minh service nào kết nối, và Payments vẫn kiểm tra **operation/resource authorization**.
5. **Egress controls** chỉ cho phép các dịch vụ/ports theo chức năng; không dựa vào DNS/IP một mình để xác thực.
6. **Các key/token ngắn hạn** có refresh/rotation, on-call, alert và revocation path được kiểm thử.
7. **Pod được harden** với hạn chế privilege, runtime socket, filesystem và mounts.
8. **SOC có audit metadata**, không cần biết raw bearer tokens hay private keys.

### 25.2. Thứ tự rollout theo mức rủi ro

| Bước | Thay đổi | Bằng chứng/điều kiện |
| --- | --- | --- |
| 1 | Inventory credentials và owner | Loại secret, nơi cấp, nơi dùng, thời hạn, audience và quyền |
| 2 | Gán dedicated workload identity | Kubernetes SA/RBAC và cloud IAM review |
| 3 | Loại static tokens nếu có thể | Temporary access qua broker/STS hoạt động trong staging |
| 4 | Thay cách delivery | Mounted files/CSI/agent với permissions, app reload đúng |
| 5 | Giảm runtime privilege | PodSecurity, drop caps, non-root, no runtime socket |
| 6 | Giới hạn network egress | DNS, API, broker, DB ALLOW; unknown destinations DENY |
| 7 | Chuẩn hóa mTLS peer authorization | Verified identity, trust bundle và fail-closed tests |
| 8 | Kiểm thử rotation/revocation | New keys hoạt động, old keys bị chặn theo policy |
| 9 | Quan sát logs | Auth/K8s/IAM/flow/secret access audit, redaction |
| 10 | Canary Production | App SLO, token refresh, 401/403, latency, false positives |
| 11 | Readback | Actual Pod specs/identity policies và runtime behavior phù hợp |
| 12 | Retire credentials cũ | Revoke, xóa distribution, giảm quyền, update runbook |

### 25.3. Mẫu change record

~~~text
CHANGE ID / OWNER / APPROVER:
SERVICE / CLUSTER / NAMESPACE / ENVIRONMENT:
CURRENT CREDENTIAL TYPE AND OWNER (NO VALUES):
TARGET IDENTITY: issuer, audience, subject, scopes, TTL
TRUST: CA, SPIFFE ID, IAM trust binding, API resource policy
DELIVERY: mounted file / CSI / agent / STS
RUNTIME: UID/GID, secret volume access, PodSecurity, node pool
NETWORK: required DNS, egress destinations, ingress peer IDs
ROTATION: overlap, reload, session reconnect, revoke plan
MONITORING: expiry, refresh, unauthorized use, audit sources
TESTS: ALLOW authorized / DENY unauthorized / DR / IPv6
CANARY + ROLLBACK: safe path, SLO triggers, affected clients
READBACK / REMAINING GAPS:
~~~

**Rollback không có nghĩa khôi phục secret đã bị lộ.** Khi rollout credential mới gây outage, phải có phương án **fix forward hoặc quay lại một credential/trust path vẫn được phê duyệt và không compromise**, không bật lại cloud admin key cũ chỉ để phục hồi tạm.

### 25.4. Audit định kỳ không phải chỉ kiểm tra expiry

Đặt lịch review theo rủi ro:

- **Credential inventory drift:** workload mới có static token, secret mount không được review, SA/roles cũ còn quyền.
- **Identity entitlement:** workload nào có permission vượt nhu cầu, Dev→Prod grants hoặc federation trust rộng.
- **Runtime exposure:** privileged Pod, hostPath/socket, debug sidecar hoặc rootfs ghi được.
- **Network path:** Pod có thể gọi secret manager/metadata/cloud APIs không thuộc contract.
- **Rotation/revocation readiness:** cert/token gần hết hạn, old credentials còn được server chấp nhận.
- **Logs/data leakage:** có log raw headers, TLS keylog, crash dumps hoặc support bundles nhạy cảm không.

**Một báo cáo “mọi Secret đều encrypted at rest” chưa đủ:** dữ liệu có thể rò ở runtime/mount hoặc identity có quyền sử dụng sai. Mục tiêu đo là **số identities quá quyền, secrets tĩnh, người có đường đọc và thời gian thu hồi khi compromise**.

## 26. Những hiểu nhầm thường gặp

| Nhận định sai | Cách hiểu đúng |
| --- | --- |
| “Kubernetes Secret đã base64 nên được mã hóa.” | Base64 chỉ là encoding; cần encryption at rest và IAM/RBAC. |
| “Dùng Secret manager nghĩa là secret không bao giờ ở Pod.” | Process có thể cần secret trong RAM/file/socket khi sử dụng. |
| “Một ServiceAccount token chỉ dùng trong namespace ấy.” | Quyền thực phụ thuộc RBAC và verifier/trust federation; scope phải được kiểm tra. |
| “Tắt automount đồng nghĩa Pod không thể có credential.” | Explicit projected volumes, CSI, SDK và file riêng vẫn có thể cấp credential. |
| “Projected token hết hạn thì không thể bị lạm dụng.” | Có thể được sử dụng trong TTL, hoặc attacker còn quyền xin mới. |
| “Xóa Pod thu hồi mọi cloud token đã phát.” | External STS sessions có vòng đời/thu hồi riêng. |
| “Một Pod dùng một ServiceAccount mặc định cũng đủ cho mọi microservice.” | Dedicated identity và least privilege giảm blast radius. |
| “Registry pull credentials phải đưa vào app container.” | Kubelet/runtime thường là thành phần sử dụng khi kéo image. |
| “TLS certificate là một password.” | Public certificate có thể công bố; private key cần bảo vệ. |
| “Khi có mTLS, tất cả services cùng CA có thể gọi nhau.” | Còn cần peer identity authorization và operation/resource permissions. |
| “Service mesh sidecar hoàn toàn cách ly secrets khỏi app.” | Pod có thể chia sẻ network/volumes; cần kiểm tra implementation và attacker control. |
| “Rotate file cert là mọi kết nối dùng cert mới.” | Proxy/app có thể cache context và active sessions còn tồn tại. |
| “KeyUpdate/TLS encryption ngăn attacker dùng token đã lấy.” | Mã hóa kênh không chặn việc dùng bearer token còn hợp lệ. |
| “Đặt token trong env an toàn hơn file trong mọi trường hợp.” | Env có nguy cơ log/debug/process inspection; chọn theo rotation/permission model. |
| “Secret volume read-only nghĩa là không ai đọc được.” | Read-only chỉ chặn ghi, process có quyền vẫn có thể đọc/copy. |
| “Non-root container thì không có nguy cơ host-level compromise.” | Kernel vulnerabilities, capabilities, host mounts và runtime socket cần xét riêng. |
| “Dùng NetworkPolicy là bảo vệ được cloud metadata trên mọi cloud.” | Hành vi phụ thuộc CNI, node/metadata service và provider routing. |
| “Dùng IP allowlist là đủ để xác thực service.” | Pod IP có thể đổi/reuse; dùng workload identity và API authZ. |
| “Workload identity không cần kiểm tra issuer/audience.” | Sai binding tạo confused-deputy hoặc quyền chéo Dev/Prod. |
| “Đổi API key là mọi session cũ bị cắt.” | Active connections và verifier caches có thể kéo dài hiệu lực. |
| “Flow log biết được JWT nào đã dùng.” | Flow logs thường chỉ có IP/port/time/volume; cần identity/app logs. |
| “Không có 401/403 chứng minh secret chưa bị lộ.” | Attacker có thể dùng credential hợp lệ và nhận 200. |
| “Log raw Authorization giúp điều tra chính xác hơn.” | Đây là cách phát tán bearer credential; nên log identity metadata đã xác thực. |
| “Một quyền get Secret bị chặn nghĩa là user không thể đọc Secret.” | Quyền tạo Pod/mount hoặc exec có thể cho đường đọc gián tiếp theo policy. |
| “Container isolation đủ để bảo vệ secrets trước node root.” | Node compromise có blast radius rộng; cần hardening và dedicated isolation. |
| “TTL ngắn thay được giám sát và ứng phó.” | Attacker có thể xin token mới hoặc tận dụng refresh path khi còn kiểm soát process. |
| “Chỉ cần khóa outbound Internet là hết data exfil.” | Secrets có thể bị dùng qua approved API/proxy hoặc internal paths; cần identity/resource policy. |

## 27. Câu hỏi tự kiểm tra và bài tập tổng hợp

1. **Network credential là gì?** Vật liệu giúp xác thực danh tính, thiết lập kênh hoặc được chấp nhận khi gọi network API/database.
2. **Public certificate khác private key ra sao?** Certificate thường được gửi công khai; private key chứng minh quyền sở hữu identity và phải bảo vệ.
3. **Vì sao bearer JWT được xem như secret dù claims có thể đọc?** Ai giữ token có thể sử dụng theo quyền của nó; chữ ký không ngăn sao chép.
4. **Image pull credential có bắt buộc nằm trong container không?** Không; thường kubelet/runtime dùng ở đường pull.
5. **Tại sao không hardcode credential vào Dockerfile?** Bí mật có thể tồn tại trong image layers, cache, build logs, artifact.
6. **Kubernetes Secret base64 có phải encryption?** Không; cần etcd/KMS/encryption at rest và RBAC.
7. **Khi nào nên tắt automountServiceAccountToken?** Khi Pod không cần Kubernetes API hoặc token mặc định, sau khi xem integrations.
8. **Projected token cần ba claims/thông tin gì đặc biệt?** Subject, issuer, audience, cộng thời hạn và binding theo cơ chế.
9. **Tại sao workload federation tốt hơn static cloud key?** Giảm secret sprawl và cho phép temporary/scoped access, nhưng trust phải được ràng buộc đúng.
10. **mTLS bảo vệ những gì?** Peer authentication và confidentiality/integrity của kênh, không tự cấp resource authorization.
11. **SPIFFE ID được dùng để làm gì?** Xác định workload identity trong trust domain để kiểm tra peer/policy.
12. **Tại sao không chỉ kiểm file tls.crt sau rotation?** Proxy có thể vẫn dùng TLS context/private key cũ hoặc peer chưa trust CA mới.
13. **Secret volume update có tức thời không?** Không mặc định; propagation và ứng dụng reload có độ trễ, subPath đặc biệt.
14. **Read-only rootfs có chặn được process đọc TLS key mount không?** Không; chỉ giảm khả năng ghi tại rootfs, file permissions/identity vẫn quan trọng.
15. **Vì sao Docker socket nguy hiểm?** Có thể cấp quyền điều khiển container/node làm tăng blast radius vượt ứng dụng.
16. **NetworkPolicy có thay thế OAuth scopes không?** Không; nó kiểm soát đường mạng, không quyết định quyền operation/resource.
17. **SSRF tới metadata service đáng ngại vì sao?** Có thể khiến app truy cập identity/credential endpoints ngoài ý định.
18. **Một Pod Dev lấy được role Prod thường sai ở đâu?** Cloud federation trust, IAM/resource policy, identity binding hoặc network isolation.
19. **Vì sao xóa Pod chưa chắc thu hồi token đã copy?** Token có expiry/issuer/verifier và STS session lifecycle riêng.
20. **Vì sao không thể kết luận misuse chỉ từ IP khác?** NAT, proxy, DR region, route và collector position có thể đổi.
21. **Khi service vẫn trả 200, có chắc credential không bị lộ không?** Không; credential bị dùng trái phép có thể vẫn hợp lệ.
22. **Runbook cần phân biệt certificate leaf key với CA key thế nào?** Blast radius và trust/revocation khác, không rotate toàn CA theo phản xạ.
23. **Tại sao không lưu token hash tùy ý trong logs?** Stable identifier có thể nhạy cảm và tạo linkability, cần chính sách telemetry phù hợp.
24. **Một kiểm thử đúng phải chứng minh hai chiều gì?** Caller đúng identity có quyền được ALLOW, caller sai audience/scope/zone bị DENY.

### Bài tập cuối chương

Một tổ chức có ba môi trường **Dev, Staging, Prod** trên Kubernetes, service **orders** gọi **payments** và object storage. Orders dùng cloud temporary credentials, payments dùng mTLS trong service mesh; một CronJob cũ dùng static API key, mọi Pods từng dùng ServiceAccount mặc định. Cluster có egress qua NAT, CNI NetworkPolicy, centralized logs và secret manager.

Hãy chuẩn bị tài liệu kiến trúc gồm:

1. **Data flow và trust boundaries:** nơi phát token, nơi chứa key, path orders↔payments, cloud STS, NAT và secret manager.
2. **Credential inventory:** owner, subject, issuer, audience, scopes, TTL, delivery, refresh và revoke.
3. **Dedicated identities:** SA/RBAC, cloud roles cho Dev/Prod; không dùng chung static credentials.
4. **Manifest bảo vệ runtime:** automount policy, securityContext, chỉ mount secret cần thiết, không dùng runtime socket.
5. **Network rules:** DNS, payments, STS và storage có ALLOW cụ thể; unknown egress/admin/Dev→Prod DENY.
6. **mTLS authorization:** Payments chỉ chấp nhận đúng Orders workload identity và operation rights.
7. **Rotation plan:** TTL, refresh, CA trust overlap, app/proxy reload, active connection handling.
8. **Observability:** Kubernetes API audit, cloud IAM/STS, mTLS logs, CNI/flow logs, secret manager audit và redaction.
9. **Incident tabletop:** một token bị ghi vào log, cách cô lập, revoke và phục hồi mà không phát tán thêm.
10. **Ma trận ít nhất 12 kiểm thử** có ALLOW/DENY, failover, expired token, stale cert, SSRF và secret leak.

**Tiêu chí chấm:** Bản thiết kế không chỉ cất secret ở một nơi an toàn, mà phải chứng minh **credential có quyền tối thiểu, chỉ được cấp cho đúng process, dùng đúng peer, được refresh/thu hồi có kiểm chứng và không mở đường truy cập trái quyền khi container bị xâm nhập**.

## 28. Checklist bảo vệ network credential trong runtime

- [ ] Đã inventory **token, API key, mTLS key, certificate, DB password, HMAC secret và registry pull credential**?
- [ ] Phân biệt **public cert/trust bundle** với **private key/bearer credential**?
- [ ] Mỗi workload/environment có **identity, owner và quyền riêng**, không dùng chung quyền admin?
- [ ] Không có static production credentials trong **image, Dockerfile, ConfigMap, source, CI logs hoặc debugging artifacts**?
- [ ] Kubernetes Secret có **RBAC thích hợp**, data at rest/backup/KMS được bảo vệ?
- [ ] Đã review quyền **get/list/watch Secrets, create Pod, exec, update Deployments và mount Secret**?
- [ ] Pod không dùng Kubernetes API đã **tắt automount** nếu không có integration bắt buộc?
- [ ] Workload cần token đã dùng **projected/bound token** với audience/TTL phù hợp khi được hỗ trợ?
- [ ] Broker/verifier kiểm tra **issuer, audience, subject, expiry, binding và đúng policy**?
- [ ] Workload cloud identity được federation với **trust điều kiện hẹp**, quyền theo resource?
- [ ] Dev/Staging/Prod không chia sẻ **cloud role/SA/API key** ngoài exception phê duyệt?
- [ ] **mTLS private key** chỉ nằm trong đúng process/sidecar hoặc volume theo cần thiết?
- [ ] Trusted peer/workload identity được **authorization**, không chỉ tin cùng CA?
- [ ] Secret mounts có **read-only, UID/GID và filesystem permissions** được xác minh?
- [ ] Nếu dùng CSI/agent, đã đánh giá **node privileges, sync behavior, cache và rotation**?
- [ ] Ứng dụng/proxy **thực sự reload** sau token/certificate rotation, không chỉ đổi file?
- [ ] Có cảnh báo **certificate expiry, refresh failure, mTLS handshake errors và old-key use**?
- [ ] Có thể **revoke/deny credential** tại verifier/identity plane, không chỉ restart Pod?
- [ ] Active connections/tokens đã copy và external STS sessions được xét khi compromise?
- [ ] Không log raw **Authorization/Cookie/bearer token/private key/TLS keylog** vào Production telemetry?
- [ ] Crash/core dumps, tracing, debug endpoints và support bundles có **redaction, retention và quyền đọc**?
- [ ] Pod dùng **non-root, read-only rootfs, drop capabilities, seccomp/AppArmor/SELinux** theo policy?
- [ ] **privileged/hostPID/hostNetwork/hostPath/runtime socket** bị hạn chế và review ngoại lệ?
- [ ] Node/kubelet/mesh/secret manager có **hardening, IAM và audit** riêng?
- [ ] Egress policy hạn chế **broker, APIs, DNS, metadata, external destinations** theo chức năng?
- [ ] Đã kiểm thử **SSRF/metadata access** bằng phương pháp được phép, không phá workload identity hợp lệ?
- [ ] NetworkPolicy/CNI/SG được **thực thi thật**, không chỉ tồn tại YAML?
- [ ] Có quan sát **K8s API audit, cloud STS/IAM, mTLS, CNI/flow, app auth và secret manager**?
- [ ] Detection rule phân biệt **identity misuse** với thay đổi route/NAT/region hợp lệ?
- [ ] Sau rollout có **ALLOW đúng workload và DENY sai audience/scope/tenant/zone**?
- [ ] Có test **scale, restart, node move, multi-region/DR, certificate renewal, old-key rejection**?
- [ ] Runbook chứa **owner/IC, loại secret, blast radius, containment, revocation, evidence và rollback an toàn**?
- [ ] Những quyền/credential cũ đã được **retire và audit** theo thời hạn được duyệt?

**Kết luận:** Bảo vệ **network credential trong runtime container** không thể chỉ dựa vào việc đặt một chuỗi vào Kubernetes Secret hoặc bật mTLS. Cần kết hợp **danh tính workload được xác minh, token/certificate ngắn hạn, audience và quyền tối thiểu, phân phối đúng process, bảo vệ file/memory/log, runtime isolation, egress segmentation, peer authorization và quy trình rotation/revocation**. Khi có sự cố, hãy phân biệt **credential nào đã lộ, verifier nào còn chấp nhận, những dịch vụ nào có thể bị truy cập**, dùng Kubernetes/IAM/app/network evidence để đánh giá mà không tiết lộ thêm secret. Một thiết kế thành công phải chứng minh **workload hợp lệ truy cập được đúng dịch vụ, workload không có quyền bị từ chối và credential cũ không còn được chấp nhận sau mốc thu hồi đã phê duyệt**.
