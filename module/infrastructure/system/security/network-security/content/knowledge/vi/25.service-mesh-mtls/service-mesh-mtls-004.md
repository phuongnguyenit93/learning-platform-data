# Workload identity trong service mesh

> **Chương:** Service mesh và mTLS  
> **Mô-đun:** SECURITY_NETWORK_SECURITY  
> **Bối cảnh:** Thiết kế mạng an toàn nhiều lớp từ phân đoạn, firewall, VPN, IDS/IPS, xác thực kết nối, bảo vệ DNS đến Kubernetes và hạ tầng cloud.  
> **Trọng tâm:** Gắn một **danh tính mật mã có thể xác minh** cho workload, chuyển danh tính đó qua kết nối mTLS trong service mesh và dùng nó để áp dụng chính sách giao tiếp tối thiểu; quản trị quy trình cấp, xoay, thu hồi, liên kết trust domain và điều tra sự cố.

## 1. Workload identity trong service mesh là gì?

Trong môi trường microservices/Kubernetes, một ứng dụng có thể chạy trên hàng chục Pod, được reschedule hoặc autoscale liên tục. **Pod IP không ổn định**, một node có thể chứa nhiều workload, và hai workload có thể cùng dùng NAT, VPN hoặc network subnet. Nếu chỉ dựa vào IP để quyết định service nào được gọi service nào, mô hình bảo mật dễ hỏng khi topology thay đổi.

**Workload identity** là **danh tính logic của một tiến trình/dịch vụ hoặc nhóm replica** được hệ thống tin cậy xác minh và gắn với một bằng chứng mật mã, thường là chứng thư X.509 ngắn hạn. Trong service mesh, proxy hoặc agent có thể dùng danh tính này trong **mutual TLS (mTLS)** để hai phía xác minh bên còn lại và mã hóa luồng truyền.

Ví dụ:

- Workload **orders** chạy bằng Kubernetes ServiceAccount **orders** trong namespace **shop**.
- Mesh cấp danh tính tương ứng, ví dụ **spiffe://cluster.local/ns/shop/sa/orders** trong một cấu hình Istio dùng trust domain **cluster.local**.
- Khi **orders → payments**, proxy chứng minh danh tính orders bằng certificate và kiểm tra danh tính payments.
- Policy ở phía payments chỉ cho phép danh tính **orders** truy cập cổng/route đã phê duyệt.
- Nếu một Pod khác cùng subnet mang danh tính **debug** thử kết nối, mTLS có thể vẫn xác thực được debug; **AuthorizationPolicy phải từ chối** vì debug không nằm trong allowlist.

**Không đồng nhất danh tính với quyền:** mTLS chứng minh *bạn là ai theo trust domain*, còn authorization quyết định *bạn được làm gì ở dịch vụ đích*. Hai bước đều quan trọng.

### Mục tiêu học tập

Sau bài học, người học có thể:

1. Phân biệt **IP/node/Pod/namespace/ServiceAccount identity, user identity và workload identity**.
2. Giải thích mô hình **SPIFFE ID, trust domain, SVID, workload attestation và trust bundle**.
3. Theo dõi vòng đời **bootstrap → xác minh workload → cấp certificate → mTLS → authorization → rotate/revoke**.
4. Hiểu sự khác nhau giữa **Istio sidecar, Istio ambient ztunnel/waypoint, Linkerd và SPIRE**.
5. Viết policy **PeerAuthentication, AuthorizationPolicy** minh họa và nhận biết phạm vi L4/L7.
6. Giải thích nguy cơ **ServiceAccount dùng chung, proxy bypass, PERMISSIVE, cross-cluster trust, key compromise**.
7. Kết hợp **Kubernetes RBAC, NetworkPolicy, admission, IAM, TLS, PKI và observability** trong kiến trúc Zero Trust.
8. Kiểm thử luồng ALLOW/DENY có phép, đọc logs và thực hiện runbook khi mTLS/identity gặp lỗi.

## 2. Vì sao IP address không đủ để làm danh tính dịch vụ?

| Thuộc tính | Có thể thay đổi/giả mạo thế nào? | Dùng làm gì? |
|---|---|---|
| **Pod IP** | Pod tái tạo/reschedule, CIDR đổi, NAT | Routing/flow diagnostics |
| **Node IP** | Một node chạy nhiều workload; node có nhiều interface | Hạ tầng và host policy |
| **Source IP** | SNAT qua LB, sidecar, egress gateway hoặc NAT | Bằng chứng mạng phụ trợ |
| **DNS/Service name** | Tên phân giải tới endpoint khác, có thể không phản ánh caller | Service discovery và server name kỳ vọng |
| **Namespace** | Nhóm tài nguyên Kubernetes, không tự cô lập traffic | Organization/RBAC scope |
| **ServiceAccount** | Kubernetes identity được workload dùng theo binding | Đầu vào quan trọng để mesh xác minh workload |
| **SPIFFE ID** | Chuỗi logic thuộc một trust domain được xác minh qua SVID | Peer authentication, authorization |
| **JWT user subject** | Danh tính end-user được xác thực bởi IdP | User-level authorization, không thay workload identity |
| **Workload instance ID** | Pod UID, VM ID hoặc incarnation của replica | Forensics, không đồng nghĩa service-level principal |

Một source IP có thể thuộc **orders lúc 10:00** nhưng sau reschedule thuộc workload khác; firewall theo IP vẫn hữu ích để kiểm soát đường đi, nhưng **không thay chính sách dựa trên verified identity** khi cần phân biệt service.

### 2.1. Service identity không phải instance identity

Nhiều replica **orders** có thể được cấp chứng thư riêng nhưng **cùng một workload principal** như **spiffe://cluster.local/ns/shop/sa/orders**. Điều này thuận tiện vì authorization theo chức năng chứ không phải Pod IP.

Hệ quả: nếu một replica bị compromise hoặc một Pod độc hại có thể chạy dưới **cùng ServiceAccount**, chính sách theo principal **không phân biệt được hai replica**. Phải bảo vệ **quyền tạo Pod, gán ServiceAccount, admission, node/runtime và supply chain**.

### 2.2. Workload identity không phải user identity

Một request checkout có thể do **user A** gửi qua frontend, còn service-to-service request **frontend → orders** được mTLS xác thực là **frontend workload**. Backend vẫn cần kiểm tra **user A có quyền đối với đơn hàng** bằng token/delegation/app logic hợp lệ. Không tự cho phép mọi user action chỉ vì frontend có mTLS identity.

## 3. Mô hình danh tính nhiều lớp

~~~mermaid
flowchart TD
    U[End user identity / OAuth2 JWT] --> F[Frontend application]
    K[Kubernetes ServiceAccount / Runtime Metadata] --> A[Workload attestation]
    A --> CA[Mesh CA / SPIRE / Identity Control Plane]
    CA --> CERT[X.509 workload certificate + trust bundle]
    CERT --> P1[Frontend proxy/agent]
    P1 -->|mTLS peer identity| P2[Orders proxy/agent]
    P2 --> AUTH{Authorization policy}
    AUTH -- ALLOW --> O[Orders application]
    AUTH -- DENY --> D[Reject + security event]
    U -. User token/delegation nếu được thiết kế .-> O
~~~

Bốn kiểm soát có mục tiêu khác nhau:

1. **Workload authentication:** bên gọi chứng minh danh tính của service/proxy qua mTLS.
2. **Peer authorization:** policy cho phép workload principal nào kết nối/call service đích.
3. **End-user authorization:** ứng dụng quyết định user/tenant nào được thao tác với dữ liệu.
4. **Network reachability:** CNI NetworkPolicy, firewall, VPN và routing giới hạn những đường đi có thể đến endpoint.

Chỉ một lớp không thể bảo đảm đầy đủ. **mTLS không chặn traffic đi vòng qua proxy nếu đường bypass được phép**; NetworkPolicy không xác minh user; RBAC của Kubernetes API không quyết định quyền HTTP route.

## 4. SPIFFE: danh tính workload portable

**SPIFFE** (Secure Production Identity Framework for Everyone) định nghĩa cách biểu diễn danh tính workload và bằng chứng có thể xác minh, giúp vượt qua giới hạn gắn quyền theo IP, VM name hoặc cloud account cố định.

### 4.1. Cấu trúc SPIFFE ID

~~~text
spiffe://<trust-domain>/<workload-path>

Ví dụ minh họa:
spiffe://prod.example.com/ns/shop/sa/orders
spiffe://prod.example.com/ns/shop/sa/payments
spiffe://staging.example.com/ns/shop/sa/orders
~~~

Theo SPIFFE, **scheme** là **spiffe**, **trust domain** là phần authority và **path** diễn tả danh tính theo quy tắc của hệ thống cấp. **Không có một quy tắc bắt buộc rằng mọi SPIFFE ID phải chứa ns/sa**; đây là convention được Istio/Kubernetes sử dụng trong những cấu hình nhất định.

### 4.2. Trust domain nói điều gì?

Trust domain xác định **ranh giới tin cậy gắn với nguồn cấp danh tính/khóa xác minh**. Hai chuỗi cùng path nhưng khác trust domain **không tự là cùng một danh tính**:

~~~text
spiffe://prod.example.com/ns/shop/sa/orders
spiffe://dev.example.com/ns/shop/sa/orders
~~~

Nếu production và development cần tách authority, **không nên đặt cùng một trust domain chỉ vì tên ServiceAccount giống nhau**. Quyết định cross-domain trust phải tường minh, có owner, policy và kiểm thử.

### 4.3. SPIFFE ID không phải token đăng nhập

SPIFFE ID là **tên/identity string**, có thể biết được bởi bên khác. Bằng chứng xác thực là **SVID có thể kiểm chứng** và quyền sử dụng khóa riêng/cryptographic proof liên quan, không phải chỉ cần đưa nguyên chuỗi SPIFFE ID vào header HTTP.

## 5. SVID: chứng cứ để xác minh một SPIFFE ID

**SVID** (SPIFFE Verifiable Identity Document) mang danh tính SPIFFE trong tài liệu mật mã có thể kiểm chứng. Hai dạng quan trọng:

| Dạng | Bằng chứng | Phù hợp | Rủi ro/chú ý |
|---|---|---|---|
| **X.509-SVID** | Chứng thư X.509 với SPIFFE ID trong URI SAN, gắn với khóa riêng | mTLS workload-to-workload | Bảo vệ key, chain, validity, SAN và trust bundle |
| **JWT-SVID** | JWT được ký cho danh tính workload, có audience và validity | Trường hợp không dùng được mTLS trực tiếp hoặc trao đổi qua ranh giới phù hợp | Bearer/replay nếu bị đánh cắp, xác minh issuer/audience/time và bảo vệ token |

**Trong service mesh mTLS**, mô hình phổ biến là **X.509 certificates** gắn với workload identity, do mesh CA/issuer phát và xoay tự động.

### 5.1. Các trường cần xác minh khi dùng X.509-SVID

- Chuỗi tin cậy đến **trust bundle** của trust domain được cho phép.
- **URI SAN** chứa đúng SPIFFE ID kỳ vọng, không chỉ kiểm tra certificate có chữ ký hợp lệ.
- Thời gian **notBefore/notAfter**, thời gian đồng bộ và hạn mức chấp nhận clock skew.
- Usage/extended key usage và các ràng buộc X.509/mTLS theo cách mesh implementation xác minh.
- Chính sách **trust domain, workload principal và scope của ứng dụng**.
- Xác minh chữ ký qua handshake: bên trình cert phải **sở hữu khóa riêng** tương ứng.

### 5.2. Chain hợp lệ chưa có nghĩa được quyền gọi service

Một CA có thể cấp chứng thư cho cả **orders, inventory, admin-job**. Payments chỉ nên cho những danh tính được phép trong policy. **Trust anchor** nói bên nào được chứng thực, còn **AuthorizationPolicy** nói identity nào được gọi operation cụ thể.

### 5.3. Không truyền X.509 private key trong log

Không đẩy certificate private key, raw SVID JWT, service account bearer token hoặc SDS secret vào ticket/central logs. Chỉ giữ **fingerprint/serial trong phạm vi cần thiết, SPIFFE principal đã xác minh, expiry, issuer reference và policy decision** theo quyền quản trị.

## 6. SPIRE: đăng ký và xác minh workload thực sự

**SPIRE** là một implementation của SPIFFE, thường gồm **SPIRE Server** và **SPIRE Agents**. SPIRE có thể cấp workload identities dựa trên **node attestation** và **workload attestation**.

~~~mermaid
flowchart TB
    SR[SPIRE Server + Registration Entries] --> AG[SPIRE Agent trên Node]
    AT[Node attestation / selector] -. Xác minh node .-> AG
    W[Workload process / Pod] --> API[Local SPIFFE Workload API]
    API --> AG
    AG --> WA[Workload attestation: process / K8s metadata]
    WA --> ID{Match selectors / registration?}
    ID -- Có --> S[X.509-SVID/JWT-SVID + trust bundle]
    ID -- Không --> DENY[No matching identity]
    S --> W
~~~

### 6.1. Node attestation

Agent cần chứng minh nó thuộc node/instance được cho phép, tùy môi trường có thể dựa trên **Kubernetes, cloud instance identity hoặc phương pháp được hỗ trợ**. Nếu agent/node không được tin nhưng vẫn cấp SVID, mọi mTLS phía sau có thể là **sự tin cậy sai nguồn**.

### 6.2. Workload attestation

Agent xác định **process/Pod nào đang gọi Workload API** bằng metadata đáng tin ở mức OS/Kubernetes, không chỉ đọc một text header do workload tự khai. Registration selectors có thể chứa **namespace, ServiceAccount, Pod attributes hoặc process UID/GID** tùy plugin.

**Nguy cơ:** nếu ai có quyền tạo Pod với ServiceAccount được cấp quyền cao, họ có thể đạt **cùng workload identity**. Phải kết hợp **Kubernetes RBAC, admission, node hardening, runtime isolation và workload admission restrictions**.

### 6.3. Workload API là local trust boundary

SPIFFE Workload API thường được mở qua **local endpoint/socket** để workload lấy danh tính/trust bundle. Quyền kết nối socket, host filesystem mounts và attestation metadata phải bảo vệ. **Không export Workload API công khai ra Internet** hoặc mount socket rộng rãi vào các container không được phép.

### 6.4. SPIRE và Istio không bắt buộc là một hệ

Istio có thể dùng **cơ chế CA/identity riêng** hoặc tích hợp với SPIRE/external CA theo thiết kế. SPIFFE là **chuẩn**, SPIRE là **một implementation**; service mesh như Istio/Linkerd cũng có các cơ chế danh tính riêng, không mặc định mọi sản phẩm là một SPIRE agent.

## 7. Kubernetes ServiceAccount: đầu vào của workload identity

Một Pod có thể chỉ định **spec.serviceAccountName**, hoặc dùng **default** nếu không đặt. Trong nhiều mesh triển khai trên Kubernetes, danh tính service proxy được gắn với **namespace + ServiceAccount**, không gắn trực tiếp với Kubernetes Service name hay Pod IP.

Ví dụ:

~~~yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: orders
  namespace: shop
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders
  namespace: shop
spec:
  replicas: 2
  selector:
    matchLabels:
      app: orders
  template:
    metadata:
      labels:
        app: orders
    spec:
      serviceAccountName: orders
      containers:
        - name: orders
          image: registry.example.invalid/orders:v1
          ports:
            - containerPort: 8080
~~~

Manifest trên **chỉ minh họa ràng buộc identity**, không phải deployment production: thiếu probes, resource limits, image signature, NetworkPolicy, securityContext, rollout settings và ứng dụng mẫu. Nó **không tự bật Istio injection hoặc mTLS**.

### 7.1. Không dùng chung ServiceAccount cho mọi workload

Nếu cả orders, payments và debug Pod đều chạy **default ServiceAccount**, mesh policy dựa trên identity sẽ khó phân biệt. Nên dùng **ServiceAccount riêng theo trust/permission boundary**, không nhất thiết một SA cho từng replica nếu chúng cùng chức năng và quyền.

### 7.2. Quyền Kubernetes RBAC khác quyền mesh

Kubernetes RBAC gán các **API verbs/resource permissions** cho ServiceAccount, ví dụ được đọc ConfigMap hay liệt kê Pods. Mesh mTLS identity dựa trên cùng ServiceAccount **không tự cấp quyền Kubernetes API**; ngược lại ServiceAccount có quyền Kubernetes API cao không nên được tự động cho quyền gọi mọi service.

**Cùng ServiceAccount là một điểm nối rủi ro:** một Pod sử dụng SA có quyền API rộng hoặc mesh role rộng có thể làm ảnh hưởng cả control plane và data plane nếu bị compromise.

### 7.3. Projected ServiceAccount token

Mesh/identity control plane có thể dùng **service account token có thời hạn/audience phù hợp** làm một phần bootstrap và attestation. Không log token, không chuyển nó tùy tiện giữa containers/namespaces, không coi JWT Kubernetes SA token là user credential. Bảo vệ **automountServiceAccountToken, token audiences, RBAC và issuer validation** theo nhu cầu.

## 8. Vòng đời workload identity từ khởi động đến rotation

~~~mermaid
sequenceDiagram
    autonumber
    participant P as Workload Pod
    participant A as Proxy / Local Agent
    participant I as Mesh Identity Control Plane / CA
    participant D as Destination Proxy
    P->>A: Bắt đầu chạy với ServiceAccount
    A->>I: Chứng thực node/workload + yêu cầu cấp identity
    I->>I: Validate attestation, identity và policy
    I-->>A: Short-lived certificate / trust bundle
    A->>D: mTLS handshake, present workload certificate
    D-->>A: Server certificate + mutual authentication
    D->>D: Verify peer identity and authorization policy
    D-->>P: Giao tiếp với backend nếu được ALLOW
    A->>I: Renew/rotate trước khi certificate hết hạn
    I-->>A: Certificate mới / trust updates
~~~

### 8.1. Bootstrap là bước nhạy cảm nhất

Để cấp certificate, identity provider cần một **bằng chứng ban đầu** rằng workload thực sự đang chạy ở node/namespace/SA đúng. Nếu một attacker có thể tự khai "tôi là payments" và được cấp cert, mọi xác minh mTLS về sau sẽ tin sai.

**Trust-on-first-use tùy tiện** hoặc một shared bootstrap secret dài hạn gắn trên mọi Pod là điểm yếu lớn. Cần attestation từ nền tảng, service account token đúng audience và policies không thể tùy ý thay bởi workload.

### 8.2. Rotation giúp giảm thời gian lạm dụng nhưng không thay revocation

Certificates ngắn hạn được **renew/rotate tự động** giúp giảm thời gian một credential bị đánh cắp còn hiệu lực. Tuy nhiên:

- Khi private key đã lộ, attacker có thể mạo danh trong khoảng thời gian credential/trust còn hiệu lực và có đường kết nối.
- Không phải mọi mesh hỗ trợ **revocation X.509/CRL/OCSP giống Internet PKI**; cơ chế thực tế có thể dựa vào short-lived cert, ngăn issuance mới, policy revoke hoặc trust bundle rotation.
- **Xóa Pod/ServiceAccount không tự làm chứng thư đã cấp lập tức vô hiệu** tại mọi peer.
- Phải đánh giá **cách invalidate sessions/long-lived connections, rotate issuer/root và revoke access** trong incident plan.

### 8.3. Control plane outage

Nếu mesh identity CA hoặc distribution service ngừng hoạt động:

- Những workload đang có cert/trust hợp lệ có thể tiếp tục một thời gian, phụ thuộc implementation và TTL.
- Workload mới hoặc quá hạn rotation có thể mất mTLS connectivity.
- Không xử lý bằng cách **tắt verify/STRICT** cho toàn mesh trong production.
- Cần giám sát **cert expiry remaining time, CA availability, xDS/SDS updates, issuance failures** và có recovery procedure.

## 9. PKI và trust bundle: nền tảng của mTLS identity

Một mô hình mesh PKI có thể gồm **root/trust anchor, intermediate/issuer CA, workload leaf certificates và trust bundle**.

| Thành phần | Trách nhiệm | Rủi ro |
|---|---|---|
| Root/trust anchor | Điểm neo xác minh certificate chains | Root key compromise có phạm vi rất lớn |
| Issuer/intermediate CA | Ký cert workload theo chính sách | Issuer bị lộ có thể phát identity giả |
| Workload leaf cert | Chứng minh SPIFFE/mesh identity trong mTLS | Leaf key lộ ảnh hưởng workload principal |
| Private key | Chứng minh sở hữu identity | Bảo vệ khỏi log, mount sai hoặc memory dump |
| Trust bundle | Danh sách CA/trust anchors peer được phép tin | Quá rộng hoặc cập nhật sai dẫn tới cross-trust |
| Certificate validity | Giới hạn thời gian cert được chấp nhận | Clock skew, lỗi rotation hoặc TTL quá dài |
| Identity control plane | Xác minh workload và phát cert/bundle | Attestation bypass, RBAC quá rộng hoặc mất sẵn sàng |

### 9.1. Phân biệt trust và authorization

Nếu payments nhận chứng thư **đúng issuer** từ orders, payments biết caller thuộc trust domain và có identity **orders**. Nó vẫn phải kiểm tra orders có quyền gọi **payments API** không. Một lệnh **allow tất cả authenticated callers** có thể gây lateral movement khi tenant/role boundaries cần hẹp hơn.

### 9.2. Trust bundle rotation không thể chỉ thay một lần ở server

Khi đổi root/intermediate hoặc chuyển CA, phải lập kế hoạch **overlap trust anchors** phù hợp, cập nhật phân phối tới proxies rồi mới loại bỏ CA cũ theo quy trình. Nếu bên gọi có CA mới nhưng bên nhận chỉ tin CA cũ, hàng loạt mTLS handshakes sẽ thất bại.

### 9.3. Không gom dev và prod vào chung quyền chỉ vì cùng tên SA

Production nên kiểm tra **trust domain và principal đầy đủ**. Một trust bundle chung hoặc trustDomainAliases có thể dẫn tới danh tính từ môi trường khác được tin; nếu business không yêu cầu liên thông, tách trust roots/domains và giới hạn federation.

## 10. mTLS xác minh hai bên: luồng handshake và policy

~~~mermaid
sequenceDiagram
    participant O as Orders Proxy
    participant P as Payments Proxy
    participant A as Payments Application
    O->>P: TLS ClientHello
    P-->>O: Server certificate / TLS handshake
    O->>O: Verify server chain, identity, trust domain
    O->>P: Client certificate + proof of key
    P->>P: Verify client chain, identity, validity
    P->>P: Check authorization allowlist/policy
    alt Caller allowed
        P->>A: Forward request tới app
        A-->>P: Application response
        P-->>O: Response
    else Caller denied
        P-->>O: Deny / connection failure theo tầng
    end
~~~

Sơ đồ **khái niệm**, không mô tả thứ tự chính xác mọi TLS 1.3 handshake message. Điểm cần hiểu là **mTLS hỗ trợ xác minh peer identity hai chiều**, sau đó policy quyết định có cho application traffic vào không.

### 10.1. Bảo mật đoạn proxy ↔ application

Service mesh có thể mã hóa **proxy-to-proxy**, nhưng đoạn **app container → local proxy** hoặc **proxy → app** có thể là plaintext trong Pod/host network tùy triển khai. Điều này cần được phản ánh trong threat model, đặc biệt nếu **compromised Pod, host access, sidecar bypass hoặc traffic egress ngoài mesh**.

### 10.2. Hạn chế lateral movement

Nếu attacker chiếm một Pod **frontend**, họ có thể dùng danh tính frontend hợp lệ để gọi những service mà frontend được phép. Mesh identity không ngăn attacker dùng đúng quyền của một workload bị compromise. Cần **phân quyền tối thiểu ở service đích, network segmentation, app authorization, rate limits và anomaly detection**.

## 11. Istio: cách ánh xạ ServiceAccount sang workload principal

Trong Istio/Kubernetes, workload thường được định danh từ **namespace + ServiceAccount + trust domain**, ví dụ:

~~~text
spiffe://cluster.local/ns/shop/sa/orders
spiffe://cluster.local/ns/shop/sa/payments

Phần principal dùng trong nhiều Istio AuthorizationPolicy:
cluster.local/ns/shop/sa/orders
cluster.local/ns/shop/sa/payments
~~~

Ở đây **cluster.local** là một **trust domain ví dụ**, không phải quy tắc bất biến. Istio có thể dùng trust domain khác hoặc aliases theo cấu hình. **Principal trong source.principals** thường được viết **không có tiền tố spiffe://** theo định dạng API Istio; không dán nhầm URI đầy đủ vào trường có format khác nếu phiên bản yêu cầu format riêng.

### 11.1. Istio certificate provisioning

Trong mô hình Istio sidecar thông thường:

1. Pod có Kubernetes ServiceAccount và agent/proxy được chèn hoặc cấu hình.
2. Istio agent thu thập thông tin/tokens được cấp và gửi **CSR + credentials** đến identity/CA service theo cấu hình.
3. Control plane xác minh credentials với Kubernetes và policy attestation của mesh.
4. CA trả **certificate ký cho workload identity** và trust bundle.
5. Proxy Envoy nhận material qua cơ chế **Secret Discovery Service (SDS)** và dùng để mTLS.
6. Agent/mesh tự giám sát **expiry và renewal**, cập nhật proxies khi certificate/trust bundle thay đổi.

**Không giả định Istio certificate là một Kubernetes Secret có thể đọc bằng kubectl get secret**. Trong nhiều cấu hình SDS, certificate/key do agent quản lý và đưa trực tiếp cho proxy. Tránh dump SDS secrets vì có thể chứa dữ liệu mật.

### 11.2. ServiceAccount alias và quyền vào mesh

Các Pods chạy cùng **shop/orders** SA thường có cùng workload principal mặc dù tên Deployment/Service khác. **Không dùng display name của Deployment như identity được chứng thực** nếu mesh không mã hóa tên đó trong policy đã xác minh.

## 12. Istio sidecar vs ambient: identity được thực thi ở đâu?

| Khía cạnh | Istio sidecar | Istio ambient |
|---|---|---|
| Data plane phổ biến | Envoy sidecar chạy cùng Pod | **ztunnel** ở node cho secure L4 overlay |
| Workload identity | Proxy/agent có credential gắn với workload | ztunnel quản lý mTLS và identity đại diện cho workloads được enroll |
| Transport mTLS | Sidecar ↔ sidecar hoặc kết nối mesh phù hợp | ztunnel ↔ ztunnel qua **HBONE/mTLS** cho traffic ambient |
| L4 authorization | Envoy policy ở workload sidecar | ztunnel phía nhận |
| L7 authorization | Envoy sidecar có HTTP parsing | **waypoint** L7 proxy khi có và traffic thực đi qua |
| Identity source | Kubernetes ServiceAccount/mesh identity | Kubernetes ServiceAccount/mesh identity |
| Policy targeting | Selector/namespace theo policy | L4 selector tại ztunnel; L7 **targetRefs** ở waypoint |
| Bypass risk | Traffic không đi qua sidecar, unmeshed workload, exceptions | Traffic không enroll/không được capture, waypoint bypass |
| Debug trọng tâm | Sidecar injection, SDS, xDS, proxy status | Ambient enrollment, ztunnel, HBONE, waypoint and policy target |

### 12.1. Sidecar không phải là một lớp bảo vệ tuyệt đối

Nếu app/Pod dùng **hostNetwork, bypass ports, proxy exclusion, direct-to-Pod đường không qua sidecar** hoặc mesh injection thiếu, một số traffic có thể không được kiểm soát bởi sidecar theo thiết kế/thực tế. Bật **PeerAuthentication STRICT** trên target được capture giúp từ chối plaintext inbound, nhưng vẫn cần **CNI/network policy và kiểm soát vùng unmeshed**.

### 12.2. Ambient: ztunnel thực thi L4, waypoint thực thi L7

**ztunnel không phân tích HTTP method/path/JWT để quyết định L7.** Nếu policy dựa trên HTTP method/path được đặt ở điểm ztunnel L4, nó có thể **không được thực thi như kỳ vọng**; Istio document có semantics khác nhau theo ALLOW/DENY khi gặp L7 conditions ở ztunnel. Với L7 security, cần waypoint đúng scope/targetRefs và **chặn đường direct-to-workload bỏ qua waypoint** nếu L7 policy bắt buộc.

### 12.3. Waypoint có identity riêng

Khi traffic đi qua waypoint, **ztunnel ở workload đích có thể thấy mTLS principal của waypoint**, không phải principal của client ban đầu. Nếu muốn enforce caller identity, đặt policy ở **waypoint**; đồng thời có thể đặt L4 policy ở destination **chỉ cho waypoint** để ngăn bypass. Không chỉ nhìn principal tại ztunnel rồi quy nó là end-user hoặc original caller.

## 13. Istio PeerAuthentication: bắt buộc mTLS inbound

**PeerAuthentication** xác định yêu cầu peer mTLS của **lưu lượng đi vào** workload. Một policy namespace-level minh họa:

~~~yaml
apiVersion: security.istio.io/v1
kind: PeerAuthentication
metadata:
  name: require-mtls
  namespace: shop
spec:
  mtls:
    mode: STRICT
~~~

### 13.1. STRICT, PERMISSIVE và DISABLE

| Mode | Ý nghĩa khái quát | Rủi ro/ứng dụng |
|---|---|---|
| **STRICT** | Inbound tới workloads được policy áp yêu cầu mTLS | Đích di trú an toàn; unmeshed plaintext callers cần xử lý trước |
| **PERMISSIVE** | Có thể chấp nhận cả mTLS và plaintext theo môi trường sidecar; ambient cho phép traffic không được bọc mTLS từ ngoài mesh | Giai đoạn migration nhưng tạo cửa cho traffic không xác thực |
| **DISABLE** | Tắt peer mTLS theo semantics hỗ trợ | Không phù hợp với mesh có mục tiêu xác thực mạnh; **không được hỗ trợ ở ambient ztunnel** |

### 13.2. STRICT không tự nói ai được phép gọi

Nếu payments có STRICT và orders/debug đều có valid mesh certificates, **cả hai đều có thể được xác thực**, nhưng vẫn cần **AuthorizationPolicy** để từ chối debug. STRICT là **yêu cầu mTLS**, không phải danh sách cho phép từng principal.

### 13.3. Scope và rule inheritance

Policy có thể ở mesh/root namespace, namespace hoặc workload scope theo các quy tắc version/provider. Cần đọc **policy được chọn thực tế** thay vì giả định mọi Pods nhận cùng policy. Khi đặt STRICT ở namespace có unmeshed health checks hoặc agent đặc biệt, phải thử flows hợp lệ trước và không sửa bằng cách bật PERMISSIVE toàn production không thời hạn.

## 14. Istio AuthorizationPolicy: chỉ cho phép workload được duyệt

Ví dụ payments chỉ cho workload **shop/orders** vào cổng TCP 8080. Policy này có ý nghĩa **L4** và dùng selector nhắm Pod đích:

~~~yaml
apiVersion: security.istio.io/v1
kind: AuthorizationPolicy
metadata:
  name: payments-allow-orders
  namespace: shop
spec:
  selector:
    matchLabels:
      app: payments
  action: ALLOW
  rules:
    - from:
        - source:
            principals:
              - cluster.local/ns/shop/sa/orders
      to:
        - operation:
            ports:
              - "8080"
~~~

### 14.1. Tại sao chọn đúng principal?

- **source.principals** được rút từ **peer certificate** đã xác minh khi dùng mTLS; chuỗi ví dụ có dạng **trust-domain/ns/namespace/sa/service-account**.
- Không lấy principal từ một HTTP header **X-Service-Name** hoặc **X-User** tự khai.
- Một Pod khác có principal **shop/debug** không match rule, nên bị deny khi policy ALLOW đúng scope/enforcement.
- Một Pod cố tình dùng **ServiceAccount orders** nhưng không được ngăn ở Kubernetes admission/RBAC sẽ có cùng principal và có thể được allow; cần bảo vệ ranh giới issuance.

### 14.2. ALLOW rule không có nghĩa không còn DENY policy khác

Istio AuthorizationPolicy có các action như **CUSTOM, DENY, ALLOW, AUDIT** với quy tắc ưu tiên áp dụng của engine. **Đừng chỉ nhìn một ALLOW manifest rồi khẳng định final decision**, khi có DENY/CUSTOM policies khác hoặc policy target scope chồng lấn. Cần kiểm tra danh sách policy thực tế, cấu hình xDS và traffic tests.

### 14.3. Tại sao chọn port backend thay vì Service port?

Trong ví dụ Service có thể dùng **port 80 → targetPort 8080**; policy được thực thi ở destination workload và port thực tế có thể là **8080**, không phải cổng frontend Service 80. Xác minh **dịch vụ, service-port mapping, proxy view và targetPort** theo triển khai; không copy port một cách mù quáng.

### 14.4. Bắt đầu với phạm vi nhỏ

Một policy trên **app=payments** dễ xem hơn policy mesh-wide chỉ cho một caller. Khi đã chứng minh đúng, có thể mở rộng theo namespace/platform baseline. Mọi chính sách mới phải được thử **ALLOW caller dự kiến** và **DENY caller ngoài phạm vi** trước production rollout.

## 15. Istio AuthorizationPolicy và nguyên tắc default deny

Một nguyên tắc quan trọng: **không có ALLOW policy áp dụng** thường nghĩa là policy engine cho phép theo mặc định trong phạm vi Istio AuthorizationPolicy, không phải “default-deny mesh”.

Khi có **ALLOW policy chọn workload**, những request không match bất kỳ allow rule hợp lệ nào tới workload đó thường bị từ chối, tùy policy khác/enforcement. Có thể đặt policy namespace **action ALLOW với rules rỗng** để từ chối mọi request trong scope rồi tạo những allow policies hẹp:

~~~yaml
# Minh họa tính chất deny của ALLOW policy có rules rỗng.
# CHỈ thực hành trong namespace lab với rollout plan.
apiVersion: security.istio.io/v1
kind: AuthorizationPolicy
metadata:
  name: deny-by-default
  namespace: shop
spec:
  action: ALLOW
  rules: []
~~~

**Cảnh báo:** policy này chọn workloads theo namespace mặc định và có thể chặn traffic quản lý/DNS/health checks tùy đường đi và implementation, gây outage. Không áp lên production hoặc toàn mesh để “thử nhanh”. Đồng thời cần chú ý **các rules ALLOW khác** có thể tạo ngoại lệ; **Istio policy không thay Kubernetes NetworkPolicy**.

## 16. Linkerd: ServiceAccount-based identity và mTLS

Linkerd cũng dùng danh tính workload, thường xuất phát từ **Kubernetes ServiceAccount**, để cấp **chứng thư proxy ngắn hạn**. Cách biểu diễn identity và policy API **khác Istio**; không mặc định một SPIFFE URI của Istio sẽ là một Linkerd identity.

### 16.1. Linkerd identity cấp certificate cho proxy

Một mô hình điển hình:

1. Linkerd proxy khởi chạy cùng workload đã được mesh.
2. Proxy tạo khóa riêng/certificate signing request và dùng **Kubernetes ServiceAccount credential** phù hợp để trình với identity control plane.
3. Linkerd identity service xác thực SA token, ký certificate với **issuer** dựa trên trust anchor cấu hình.
4. Proxy dùng certificate **tự động xoay ngắn hạn** để mTLS đến proxies khác.
5. Khi gọi service khác, client proxy xác minh **expected destination identity** và trust anchor.

**Chi tiết hạn cert, thuật toán và việc tự rotation cần theo phiên bản Linkerd đang chạy**. Tài liệu Linkerd nêu workload proxy certificates có TTL ngắn (ví dụ 24 giờ trong một phiên bản), trong khi issuer/trust anchor có kế hoạch rotation độc lập.

### 16.2. Linkerd identity không bảo đảm tất cả traffic đều mTLS

Linkerd tự mTLS cho traffic **giữa các Pods được mesh và được proxy xử lý**; traffic tới/từ Pod **không mesh** hoặc **skip ports/bypass** có thể không được mTLS. Mặc định của những policy cụ thể có thể vẫn cho phép plaintext từ nguồn không mesh. Nếu muốn chỉ nhận authenticated callers, cần **policy phù hợp**, bảo vệ injection/HA và kiểm tra actual traffic.

### 16.3. Linkerd authorization policies

Linkerd có các khái niệm như **Server, HTTPRoute/GRPCRoute, MeshTLSAuthentication, NetworkAuthentication, AuthorizationPolicy** theo version CRD và default inbound policy. Ví dụ logic:

~~~text
Target: payments port 8080
Authentication: peer mTLS identity thuộc ServiceAccount shop/orders
Authorization: chỉ authentication trên được phép tới target
Enforcement: Linkerd proxies được inject, policy CRDs đúng version
Validation: requests từ shop/orders ALLOW, shop/debug DENY
~~~

Đây là **thiết kế logic**, không phải CRD có thể apply. Không dùng YAML **Istio AuthorizationPolicy** trong Linkerd cluster hoặc ngược lại: API groups, identity formats và cơ chế enforcement khác nhau.

## 17. Thiết kế ranh giới identity: nguyên tắc least privilege

Workload identity tốt cần **ổn định đủ để ứng dụng hoạt động** nhưng **không gom quá nhiều ứng dụng không cùng quyền** vào một principal.

### 17.1. Một ServiceAccount cho mỗi security boundary

| Cách gán | Ưu điểm | Nhược điểm/rủi ro |
|---|---|---|
| Một SA cho mọi Pod trong namespace | Dễ vận hành | Không phân biệt orders, payments, debug |
| Một SA cho mỗi nhóm workload cùng quyền | Chính sách rõ, hợp rollout | Cần quản trị ownership và policy |
| Một SA cho từng replica Pod | Granularity cao trên lý thuyết | Identity churn; không phải luôn cần/được mesh hỗ trợ tiện |
| Một SA cho mỗi environment/tenant riêng | Tách quyền và trust boundary | Tăng số identities/policies, cần lifecycle tốt |
| Dùng Pod/Service name thay SA khi mesh không chứng thực | Có vẻ đơn giản | Có thể chỉ là label/name dễ thay, không phải principal xác minh |

**Không mặc định phân tách tenant bằng namespace là đủ.** Nếu nhiều tenant share một namespace/ServiceAccount hoặc CA/trust domain, authorization phải có scope cụ thể hơn, đôi khi cần **separate cluster/trust domain, workload identity policy và end-user tenant claims**.

### 17.2. Ai có quyền chạy dưới một ServiceAccount?

Kubernetes thường cho phép người có quyền tạo workload trong namespace tham chiếu ServiceAccount trong namespace ấy, trừ khi có admission/permission governance bổ sung. Do đó **quyền tạo Pod/Deployment** trong namespace nhạy cảm cũng ảnh hưởng **quyền nhận mesh identity**.

Kiểm soát cần thiết:

- Tách namespace theo owner/trust boundary, hạn quyền create/patch workload.
- Admission kiểm tra **serviceAccountName**, image provenance, securityContext và namespace ownership.
- Không cho app team tùy tiện thay **ServiceAccount của payments** vào Deployment debug.
- Hạn quyền sửa **Pod labels và workload identity mapping** liên quan.
- Bảo vệ credentials/control plane của mesh CA và namespace của identity controller.
- Review service account token projection và quyền mount Workload API/socket khi áp dụng.

### 17.3. ServiceAccount quyền Kubernetes API và quyền mesh có thể khác nhau

Một workload có quyền đọc Secrets từ Kubernetes API **không nên đương nhiên** có quyền gọi payments API. Ngược lại một caller được mesh policy cho payments **không tự cần** quyền sửa ConfigMap/Pods. Hạn quyền ở **cả Kubernetes RBAC và mesh AuthorizationPolicy**, rồi kiểm tra khả năng nâng quyền qua IAM/CI.

## 18. Quy trình cấp và xoay certificate thực tế

Identity không dừng ở tên SPIFFE. Tính an toàn phụ thuộc toàn bộ quá trình chứng minh và giữ khóa.

### 18.1. Chuỗi hành động tin cậy

~~~mermaid
flowchart TD
    A[Pod / VM được scheduler khởi chạy] --> B[Runtime identity và node attestation]
    B --> C{Attestation / ServiceAccount token hợp lệ?}
    C -- Không --> DENY[Không cấp SVID]
    C -- Có --> D[CA tạo/kiểm tra CSR và identity binding]
    D --> E[Issue certificate ngắn hạn]
    E --> F[Đưa cert/key qua SDS/Workload API theo thiết kế]
    F --> G[mTLS peer verification + AuthorizationPolicy]
    G --> H[Renew trước expiry]
    H --> D
    G --> I[Logging, rotation monitoring, trust review]
~~~

### 18.2. Phân biệt key generation và distribution

Trong nhiều triển khai, proxy/agent **tự sinh private key**, gửi CSR và nhận certificate ký; CA **không cần nhận private key của workload**. Tuy nhiên tính chất chính xác tùy provider/SDS/agent: cần chứng minh key được lưu ở đâu, ai đọc được, có nằm trong Pod/host filesystem, memory hay HSM không.

### 18.3. Không dùng một leaf certificate cố định cho tất cả Pods

Một certificate chia sẻ chung khiến **một Pod compromise có thể mạo danh toàn bộ nhóm** và khó rotate/forensics. Workload principal có thể giống nhau theo ServiceAccount, nhưng **private keys/cert instances** nên được cấp/phân phối/rotate theo thiết kế mesh, thay vì copy PEM vào container image.

### 18.4. TTL cần cân bằng

Certificate sống quá lâu tăng thời gian lạm dụng sau compromise; sống quá ngắn tăng phụ thuộc identity control plane và nguy cơ outage do clock/rotation. Theo dõi **remaining lifetime, rotation success, CA health, bundle consistency và node clock skew** thay vì chỉ chọn TTL nhỏ nhất.

### 18.5. Certificate expiration không cắt mọi kết nối ngay lập tức

Các phiên mTLS đã thiết lập có thể tồn tại đến khi kết nối đóng, tùy TLS implementation/connection lifecycle. Khi thu hồi access hoặc điều tra compromise, xem **session draining, connection reuse, proxy restart** theo runbook; không giả định leaf cert hết hạn sẽ làm mọi socket đã mở bị reset đúng giây ấy.

## 19. Revocation và xử lý khi workload identity bị lộ

Một sự cố có thể liên quan **Pod bị compromise, token Kubernetes SA bị đánh cắp, private key X.509-SVID bị lộ, hoặc CA issuer bị xâm nhập**. Mỗi mức cần biện pháp khác nhau.

| Bị ảnh hưởng | Phạm vi tin cậy | Hướng xử lý chính |
|---|---|---|
| Một Pod/process | Runtime hiện tại | Isolation, forensic, replace image/node và kiểm tra role |
| Một workload SA/token | Workloads có thể claim SA | Thu hồi quyền/token/session, review admission và RBAC |
| Một leaf certificate/key | Danh tính được chứng minh trong khoảng hiệu lực | Ngăn lạm dụng principal, rotate key/cert, giới hạn connectivity |
| Issuer/intermediate CA | Có thể cấp danh tính giả cho nhiều workload | CA incident plan, trust update, reissue và revocation strategy |
| Root/trust anchor | Ranh giới tin cậy lớn nhất | Emergency trust rotation, federation review và impact assessment |
| SPIRE Agent/node | Attestation nhiều workload trên node | Isolate node, revoke registrations, reattest và reissue |
| Control plane policy | Nhiều workloads/namespace | Audit configuration, rollback, test deny/allow và control-plane hardening |

**Không chủ quan rằng xóa một Kubernetes Secret hay ServiceAccount có thể thu hồi mọi chứng thư đã phát.** Cần xác minh cơ chế thu hồi thực tế của mesh, kích thước và TTL trust bundles, quyền đang được phép, các kết nối tồn tại.

### 19.1. Nếu chỉ một workload bị xâm nhập

Có thể chặn ngay bằng **AuthorizationPolicy tại các target**, hạn NetworkPolicy/egress, cách ly Pod/node theo quy trình, rotate workload token/leaf certificates và rà soát pipeline phát hành image. Việc đổi cả root CA ngay không nhất thiết là bước đầu tiên nếu chưa có bằng chứng issuer compromise.

### 19.2. Nếu issuer bị xâm nhập

Phải tính phương án **thay issuer/root, phân phối trust bundle mới, cấp lại chứng thư và loại bỏ trust cũ**. Tránh rollout trust rời rạc khiến toàn hệ mTLS lỗi; nhưng cũng phải giảm thời gian tiếp tục tin issuer bị lộ theo mức độ nghiêm trọng.

### 19.3. Registration entries và selectors

Với SPIRE, thay đổi **registration entries/selectors** có thể giúp ngăn issuance mới. **Không đánh đồng ngăn cấp mới với vô hiệu ngay tất cả SVID cũ.** Kết hợp expiry, trust/authorization changes và session management.

## 20. Multi-cluster, multi-cloud và trust-domain federation

Một hệ thống có thể có **cluster A production, cluster B production, cluster C staging**, với mesh nối giữa Kubernetes, VM hoặc cloud providers.

~~~mermaid
flowchart LR
    A[Cluster A / trust domain prod-a] -->|mTLS + policy| B[Cluster B / trust domain prod-b]
    A --> T[Trust bundle / Federation config]
    B --> T
    C[Staging / trust domain staging] -. Không tự động được tin .-> T
~~~

### 20.1. Hai cluster cùng trust domain hay khác trust domain?

- **Cùng trust domain:** có thể hữu ích cho cùng một mesh authority nhưng dễ làm **ServiceAccount trùng namespace/name** trở thành identity tương đương ở nhiều cluster nếu không có ràng buộc bổ sung.
- **Khác trust domain:** tách authority tốt hơn, nhưng cần **cross-domain federation/aliases/bundle trust** khi hai vùng cần gọi nhau.
- **Dev và prod:** nên đánh giá tách trust root/domain theo risk; không mặc định cho dev caller có principal tương đương prod.

### 20.2. Federation không đồng nghĩa tin mọi principal của đối tác

Trao đổi trust bundles cho phép **xác minh certificate từ domain khác**; authorization vẫn phải allow **đúng principal/route**. Không đặt chính sách allow từ toàn bộ trust domain đối tác nếu chỉ một workload đối tác cần gọi một API.

### 20.3. Route và identity phải đi cùng nhau

Kết nối cloud–on-prem, VPN, private endpoint, service mesh east-west gateway và DNS cross-cluster cần xác minh:

1. **Kênh mạng** có route và firewall tới endpoint kỳ vọng.
2. **Server identity** đúng với đích đã cấu hình, không chỉ CA hợp lệ.
3. **Client identity** đúng cluster/trust domain và service.
4. **Policy source principal** không bị alias quá rộng.
5. **Ingress/egress gateway** không thay caller principal ngoài mô hình đã được thiết kế.
6. **Audit** chứa source/destination identities, trust domain và policy decision.

### 20.4. SVID không mặc định thay cloud IAM

Một SPIFFE ID được mTLS xác minh **không tự cấp** quyền gọi cloud API, đọc secret store hoặc tạo LB. Nếu dùng workload identity federation với cloud IAM, phải cấu hình mapping/issuer/audience/trust rõ và giới hạn cloud role. Tránh service có mTLS identity được assume cloud administrator role chỉ vì cùng tên.

## 21. JWT-SVID và JWT user: hai thực thể khác nhau

| Thuộc tính | JWT-SVID | OAuth/OIDC user access token |
|---|---|---|
| Chủ thể | Workload/service identity | User/client authorization context tùy token |
| Bên cấp | SPIFFE-compatible issuer | Identity provider/authorization server |
| Bằng chứng | JWT ký cho SPIFFE ID, audience/time | JWT/opaque token theo OAuth/OIDC profile |
| Mục đích | Workload authentication ở ranh giới không dùng mTLS trực tiếp | User/application authorization |
| Rủi ro | Bearer replay nếu bị đánh cắp | Token theft, audience confusion, scope overreach |
| Xác minh | Trust domain, issuer, audience, signature, time | Issuer, audience, signature/introspection, exp, scopes |
| Có thay mTLS không? | Không nhất thiết | Không |

### 21.1. Không dùng header untrusted làm workload identity

Một client có thể gửi **X-Workload-Identity: orders** hoặc **X-SPIFFE-ID: spiffe://...**. Đó chỉ là text, không phải bằng chứng. Nếu cần truyền verified principal từ gateway đến backend, hãy dùng **mTLS bên trong, cơ chế signed assertion hoặc metadata do trusted proxy tự đặt trong kênh được bảo vệ**, và chống direct-to-backend bypass.

### 21.2. Audience và token exchange

JWT-SVID phải được cấp và xác minh cho **audience thích hợp**. Token có audience service A không tự hợp lệ cho service B; cũng không lấy token user thay service token hoặc ngược lại chỉ vì đều là JWT. Không log bearer token để debug identity.

## 22. mTLS và authorization: nguyên tắc Zero Trust trong mesh

Một kiến trúc Zero Trust không chỉ bật **mTLS=on** mà cần:

- **Xác minh peer identity** từ certificate chain, SAN và trust domain.
- **Chỉ cho phép principal cụ thể** đối với destination service/port/route.
- **Xác minh user và object/tenant permission** ở ứng dụng khi có yêu cầu.
- **Giới hạn network reachability** bằng CNI NetworkPolicy, firewall, security group và egress.
- **Theo dõi chứng thư, policy changes và denied requests**.
- **Đánh giá endpoint bảo mật thật** (Pod, VM, gateway, waypoint), không chỉ Service name.

### 22.1. L4 authorization và L7 authorization

| Lớp | Có thể ra quyết định theo | Không tự giải quyết |
|---|---|---|
| L3/L4 NetworkPolicy/firewall | IP/CIDR, Pod/namespace selectors, cổng/protocol | User identity, URL path, JWT claims |
| Mesh mTLS peer auth | Certificate, verified workload principal/trust domain | Quyền thao tác nghiệp vụ, BOLA |
| Mesh L4 AuthZ | Peer principal, namespace/port và L4 attributes được hỗ trợ | HTTP method/path khi không có L7 proxy |
| Mesh L7 AuthZ | Peer principal, JWT claims sau validation, method/path/headers theo policy hỗ trợ | Backend object/tenant ownership toàn diện |
| Application AuthZ | User, tenant, resource, business action và trạng thái dữ liệu | Tự ngăn mọi đường network bypass nếu không có network controls |

### 22.2. L7 policy không thay backend AuthZ

Một policy cho **orders → GET /payments/status** có thể cho service orders gọi một route, nhưng backend vẫn phải kiểm tra **đơn hàng nào thuộc tenant nào**, số tiền và trạng thái thanh toán. Mesh chỉ có thông tin application policy mà mesh/proxy được cấu hình để quan sát và xác minh.

### 22.3. Phải bảo vệ đường đi vòng

Nếu app có **hostPort, NodePort, externalIPs, public LB, hostNetwork, direct Pod IP hoặc unmeshed proxy path** không được capture, request có thể đến nơi mà không qua L7 authz. Thiết kế cần admission, CNI NetworkPolicy, security group, gateway protection và **test bypass bị chặn**.

## 23. Istio ambient waypoint: nguyên tắc không bỏ qua L7 policy

Trong ambient, **ztunnel chỉ làm L4**; waypoint đảm nhiệm L7 khi được cấu hình và traffic thực đi qua. Một policy gắn vào waypoint bằng **targetRefs** có thể phân biệt HTTP method/path, nhưng không giúp nếu client gọi Pod/VM IP hoặc service theo đường khác không đi qua waypoint.

~~~mermaid
flowchart LR
    C[Orders workload] --> Z1[Source ztunnel]
    Z1 --> W[Waypoint L7: AuthZ theo caller + HTTP path]
    W --> Z2[Destination ztunnel]
    Z2 --> P[Payments workload]
    C -. Direct path ngoài waypoint phải bị deny .-> Z2
~~~

### 23.1. Policy L4 ở destination chỉ cho waypoint

Một cách giảm bypass là đặt chính sách L4 tại destination ztunnel **chỉ cho phép principal của waypoint**, sau khi xác minh các legitimate flows đang thực sự đi qua waypoint. Như vậy một caller cố đi trực tiếp sẽ không match identity waypoint.

**Cảnh báo:** nếu còn source workloads **sidecar** trong giai đoạn migration, những workload ấy có thể kết nối trực tiếp tới ztunnel mà không qua waypoint. Áp policy "chỉ waypoint" trước khi di trú xong có thể tạo outage. Thực hiện theo lộ trình và coverage tests.

### 23.2. Không đặt HTTP DENY policy ở ztunnel rồi mặc định nó có hiệu lực

Istio mô tả rõ **L7 attributes không được ztunnel xử lý**. Một **DENY rule chỉ có điều kiện HTTP** ở ztunnel có thể bị bỏ qua, cho phép traffic ngoài ý muốn. Một **ALLOW rule có L7 condition** ở L4 có thể không match và chặn toàn bộ traffic. Vì vậy phải **đặt đúng enforcement point**, đọc analyzer/status và test ALLOW/DENY với HTTP methods cụ thể.

### 23.3. Tránh policy chỉ dựa vào namespace

Nếu namespace **shop** chứa cả payments, debug và notebook, policy “allow tất cả shop namespace” quá rộng. Dùng **service account principal** cụ thể và xác minh quyền Pod/serviceAccount creation; một waypoint có identity của chính nó càng làm cần phân biệt caller identity tại waypoint với proxy identity tại ztunnel.

## 24. So sánh Istio sidecar, ambient, Linkerd và SPIRE theo trust boundary

| Câu hỏi | Istio sidecar | Istio ambient | Linkerd | SPIRE |
|---|---|---|---|---|
| Bên cấp/điều phối identity | Istio agent/CA hoặc CA tích hợp | Istio identity control plane với ztunnel | Linkerd identity service | SPIRE Server/Agent |
| Identity gắn workload | Thường Kubernetes SA → SPIFFE-like ID | Thường Kubernetes SA → SPIFFE-like ID | Kubernetes SA → Linkerd proxy identity | SPIFFE ID theo registration/attestation |
| Có mTLS tự động? | Trên traffic đã mesh theo policy | HBONE mTLS trong secure overlay | Giữa proxies đã mesh | Cấp SVID; app/proxy tự dùng |
| L4 enforcement | Envoy | ztunnel | Linkerd proxy | Tùy ứng dụng/proxy tích hợp |
| L7 enforcement | Envoy | Waypoint | Linkerd proxy với policy hỗ trợ | Không tự tạo L7 proxy |
| Certificate rotation | Mesh agent/control plane | Mesh control plane/ztunnel | Proxy + identity issuer | Agent/Server theo SVID |
| Traffic ngoài mesh | Có thể plaintext/bypass | Unenrolled/bypass cần kiểm soát | Unmeshed/skip ports cần policy | Phụ thuộc application/mesh sử dụng |
| Authorization | Istio AuthorizationPolicy | L4 ztunnel, L7 waypoint | Linkerd Server/AuthorizationPolicy | Do relying party hoặc policy khác |
| Trust federation | Trust domain configuration/aliases theo mesh | Tương tự với cảnh giác gateway | Multicluster trust anchor/identity theo version | SPIFFE federation/trust bundles |

**Không có một YAML security policy portable cho cả bốn.** Khi triển khai, phải chọn **version, CNI, data-plane mode, identity issuer và trust model** trước khi viết policy.

## 25. NetworkPolicy, firewall và mesh identity bổ sung cho nhau

### 25.1. Traffic được allow ở mạng nhưng bị deny ở identity

Một NetworkPolicy cho phép orders Pod kết nối payments TCP 8080 chỉ chứng minh **đường L4 từ nhóm Pod này** được mở. Nếu Pod **debug** cùng selector label không bị ngăn, network policy có thể cho phép kết nối; nhưng mesh AuthorizationPolicy vẫn nên **DENY** vì principal debug không khớp.

### 25.2. Identity được allow nhưng network deny

Một caller orders có certificate hợp lệ và nằm trong allowlist của payments, nhưng **CNI NetworkPolicy deny egress** có thể chặn trước handshake; log mesh không nhất thiết có AUTHZ_DENIED vì request không tới proxy đích. Cần quan sát cả **CNI flow logs, Istio/Linkerd proxy logs và app logs**.

### 25.3. Ví dụ Kubernetes NetworkPolicy cho đúng backend

~~~yaml
# Chỉ mở ingress của Pod payments cho các Pod orders cùng namespace shop.
# CNI phải hỗ trợ NetworkPolicy và namespace shop đã tồn tại.
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: payments-ingress-orders
  namespace: shop
spec:
  podSelector:
    matchLabels:
      app: payments
  policyTypes:
    - Ingress
  ingress:
    - from:
        - podSelector:
            matchLabels:
              app: orders
      ports:
        - protocol: TCP
          port: 8080
~~~

**Giới hạn:** NetworkPolicy chuẩn lọc Pod labels/ports, **không đọc SPIFFE principal**. Một người có quyền tạo Pod với label **app: orders** có thể được chính sách trên xem như orders; cần admission/RBAC và mTLS peer AuthZ. Với ambient/HBONE, **đường mạng được mã hóa và port/capture path** có thể khác; không copy policy L4 mẫu này mà không test trên CNI/mesh thực tế.

### 25.4. HostNetwork và node-level traffic

Một số traffic từ node, kubelet, agent, health checks hoặc hostNetwork có semantics khác Pod-to-Pod NetworkPolicy. **Không khẳng định NetworkPolicy chuẩn chặn mọi node-origin traffic**. Phải kiểm soát host firewall, cloud security group, kubelet authorization và cluster CNI policy khi cần.

## 26. Rủi ro bảo mật trong workload identity

| Rủi ro | Điều kiện | Kiểm soát |
|---|---|---|
| **Identity spoofing qua untrusted header** | App tin X-SPIFFE-ID do client gửi | Peer certificate verification, proxy trust boundary |
| **ServiceAccount impersonation** | Có quyền tạo Pod với SA đặc quyền | RBAC/admission, namespace isolation |
| **Certificate/key theft** | Host filesystem/socket/key material bị đọc | Node hardening, least privilege, short-lived cert |
| **CA/issuer compromise** | CA secrets/permissions bị xâm nhập | HSM/secret governance, rotation/incident response |
| **Trust-domain confusion** | Dev và prod có aliases/root trust quá rộng | Separate trust domains và scoped federation |
| **Sidecar bypass** | Traffic không đi qua proxy | STRICT, interception checks, NetworkPolicy |
| **Waypoint bypass** | Client gọi direct Pod hoặc route không qua waypoint | L4 only-waypoint policy, route inventory |
| **Overbroad ALLOW policies** | Allow whole namespace/trust domain | Exact service account principals/ports/routes |
| **Unmeshed plaintext traffic** | PERMISSIVE/Linkerd default cho nguồn không mesh | STRICT/authenticated inbound policy, migration plan |
| **Revocation gap** | Cert cũ vẫn được peer tin | Rotation, deny principal, session handling |
| **Control plane outage** | Certificates không được renew | HA, TTL SLO, monitoring và rollback plan |
| **Compromised authorized workload** | Attacker chạy trong orders hợp lệ | App authz, egress, rate limit, runtime detection |
| **Federation overtrust** | Shared bundle mà không có per-service allow | Principal-specific authorization |
| **Mesh drift/version issues** | Policies chỉ apply ở vài proxies/regions | xDS/SDS health, admission, audit, regression |
| **Plaintext proxy-app hop** | Pod/node bị compromise hoặc capture bypass | Node/pod isolation, app-level TLS khi cần |

### 26.1. Trusting a service is not trusting its callers

Nếu frontend được phép gọi orders, **user bên ngoài không mặc định có quyền dùng mọi API orders**. Không chuyển toàn bộ user permissions thành workload identity frontend; cần kiểm tra user token, tenant, request-level policy và audit.

### 26.2. Credential theft vs policy escalation

Một attack có thể không cần trộm private key: chỉ cần đổi **AuthorizationPolicy** thành ALLOW tất cả hoặc có quyền **tạo Pod dùng SA payments**. Vì vậy bảo vệ control plane và CI/IaC là **ngang hàng** với bảo vệ cert/key.

## 27. Logging và khả năng quan sát identity trong mesh

| Nguồn | Thông tin hữu ích | Điều không được suy diễn |
|---|---|---|
| Mesh proxy access/decision logs | Source/destination principal, peer mTLS, policy decision, route/port, status | Không tự là user identity |
| Mesh CA/SDS/identity logs | Certificate issued/renewed, expiry, trust bundle, error category | Không đồng nghĩa requester được phép gọi ứng dụng |
| Kubernetes API audit | Ai đổi SA/Deployment/AuthorizationPolicy/PeerAuthentication | Không chứng minh data plane đã nhận policy cùng thời điểm |
| CNI/flow logs | L3/L4 allow/deny, node/IP/port, NAT context | Không biết chắc SPIFFE principal nếu không liên kết |
| App logs/traces | Business authorization, JWT user, object-level outcome | Không thấy request bị chặn trước app |
| Cloud IAM/network audit | LB, SG, VPN, route changes, controller activity | Không chứng minh app authz |
| Metrics | mTLS coverage, denied connections, cert expiry, CA health, proxy readiness | Không dùng trace ID làm metric label |

### 27.1. Mẫu JSON sự kiện security

~~~json
{
  "event_time": "2026-11-28T10:15:14.220Z",
  "event_type": "MESH_AUTHZ_DENIED",
  "mesh": "istio",
  "dataplane_mode": "sidecar",
  "environment": "production",
  "cluster": "cluster-a",
  "source_principal": "spiffe://cluster.local/ns/shop/sa/debug",
  "destination_principal": "spiffe://cluster.local/ns/shop/sa/payments",
  "destination_service": "payments.shop.svc.cluster.local",
  "destination_port": 8080,
  "peer_mtls": true,
  "policy_id": "payments-allow-orders",
  "decision": "DENY",
  "request_id": "e7a4dd1c5b3b4a3d8e9e7cc142aa0b57",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "reason_code": "CALLER_PRINCIPAL_NOT_ALLOWED"
}
~~~

Đây là **schema do bài học đề xuất**, không phải log mặc định của Istio/Linkerd. Một denied TCP connection có thể không có **request_id/trace_id**; trong thực tế cần **timestamp, source/destination workload, policy, proxy response flags và network context** nếu không có L7.

### 27.2. Không log credential

Không xuất raw **SVID/JWT/token, private key, Kubernetes bound SA token, Workload API responses, SDS secrets**. Giới hạn quyền đọc security events vì namespace/SA identities có thể tiết lộ kiến trúc nội bộ.

### 27.3. Điểm mù instrumentation

Có thể không có proxy log nếu traffic bị NetworkPolicy chặn trước proxy, Pod chưa inject sidecar, waypoint bị bypass, health check dùng host network hoặc collector mất kết nối. Dựa vào **Kubernetes events, CNI logs, cloud audit và collector health** trước khi kết luận kết nối không xảy ra.

## 28. Truy vấn SIEM tương quan principal, policy và thất bại mTLS

Các ví dụ giả định bảng **normalized_mesh_security_events**; điều chỉnh SQL theo data platform và schema thật. Chỉ truy vấn log trong phạm vi được phép.

### 28.1. Những principal bị từ chối tại payments

~~~sql
SELECT event_time, source_principal, destination_service,
       destination_port, policy_id, reason_code, cluster
FROM normalized_mesh_security_events
WHERE event_type = 'MESH_AUTHZ_DENIED'
  AND destination_service = 'payments.shop.svc.cluster.local'
  AND event_time >= TIMESTAMP '2026-11-28 10:00:00'
ORDER BY event_time;
~~~

### 28.2. Thống kê lỗi cấp certificates

~~~sql
SELECT cluster, trust_domain, error_code,
       COUNT(*) AS issuance_errors
FROM normalized_mesh_identity_events
WHERE event_type IN ('SVID_ISSUE_FAILED', 'SVID_ROTATE_FAILED')
  AND event_time >= TIMESTAMP '2026-11-28 00:00:00'
GROUP BY cluster, trust_domain, error_code
ORDER BY issuance_errors DESC;
~~~

### 28.3. Tìm thay policy cùng thời điểm kết nối bị deny

~~~sql
SELECT event_time, actor_identity, resource_name,
       action, old_version, new_version, change_id
FROM normalized_kubernetes_audit
WHERE resource_kind IN ('AuthorizationPolicy', 'PeerAuthentication')
  AND event_time >= TIMESTAMP '2026-11-28 09:30:00'
  AND event_time < TIMESTAMP '2026-11-28 11:00:00'
ORDER BY event_time;
~~~

**Cảnh báo:** cùng principal có thể kết nối nhiều lần, retries/fan-out tạo nhiều events. **COUNT(*) đếm events**, không nhất thiết đếm user requests. Nếu incident cần đếm requests, dùng request_id/trace và source semantics đã được chuẩn hóa; đừng đặt principal/request_id làm metric label cardinality cao.

## 29. Chẩn đoán read-only và xác minh policy

Các lệnh sau chỉ nhằm **quan sát cấu hình** trong Kubernetes/Istio cluster được cấp quyền, không thay đổi tài nguyên. Chọn đúng kubeconfig/context; metadata về namespace, principal và policy cũng có thể nhạy cảm.

### 29.1. Xác định context, Pod và ServiceAccount

~~~bash
kubectl config current-context
kubectl get pods -n shop -o wide
kubectl get serviceaccounts -n shop
kubectl get deploy orders -n shop -o jsonpath='{.spec.template.spec.serviceAccountName}'
kubectl get deploy payments -n shop -o jsonpath='{.spec.template.spec.serviceAccountName}'
~~~

Nếu giá trị là **default/empty**, cần kiểm tra effective ServiceAccount của Pod; Pod có thể dùng **default SA** ngay cả khi Deployment template không khai báo rõ. Kiểm tra pod spec cụ thể, không suy từ tên Deployment.

### 29.2. Kiểm tra Istio policy objects

~~~bash
kubectl get peerauthentications.security.istio.io --all-namespaces
kubectl get authorizationpolicies.security.istio.io --all-namespaces
kubectl describe peerauthentication require-mtls -n shop
kubectl describe authorizationpolicy payments-allow-orders -n shop
~~~

Output chỉ cho biết **desired Kubernetes API objects**. Cần kiểm tra policy scope và trạng thái xDS/dataplane nhận config. **Không coi một YAML STRICT là bằng chứng mọi traffic đều mTLS** nếu có Pods chưa được enroll hoặc đường bypass.

### 29.3. Kiểm tra proxy connection/control plane

~~~bash
# Có istioctl và được cấp quyền đọc trong môi trường:
istioctl proxy-status

# Chỉ đọc Pod metadata nếu cần xem container presence.
kubectl get pod -n shop -l app=orders -o wide
kubectl describe pod ORDERS_POD_NAME -n shop
~~~

Không dump **istioctl proxy-config secret -o json hoặc SDS raw** trong ticket/chia sẻ chat: có thể chứa certificate/private key material hoặc dữ liệu nhạy cảm. Với Linkerd, sử dụng **linkerd check** và lệnh đọc policy/status đúng phiên bản, hạn quyền và đầu ra; không copy nguyên lệnh do version khác.

### 29.4. Kiểm tra NetworkPolicy và chính chủ thể có quyền thay policy

~~~bash
kubectl get networkpolicies -n shop
kubectl auth can-i get authorizationpolicies.security.istio.io -n shop
kubectl auth can-i create authorizationpolicies.security.istio.io -n shop
kubectl auth can-i patch peerauthentications.security.istio.io -n shop
kubectl auth can-i create pods -n shop
~~~

**kubectl auth can-i** chỉ trả lời về **Kubernetes API authorization**, không nói mTLS identities nào được phép kết nối. Muốn kiểm tra mesh authorization cần quan sát policy + test traffic ALLOW/DENY.

### 29.5. Khi cần dùng test request

Có thể dùng Pod test chuẩn bị sẵn với identity được duyệt để gọi **health endpoint lab**; không brute force, không thử truy cập service của tenant khác. Không vô hiệu TLS verification hoặc chia sẻ token production. Đánh giá hành vi ở cả **NetworkPolicy/CNI layer, mesh proxy và application response**.

## 30. Runbook triển khai workload identity an toàn

### Bước 1 — Inventory identity và trust boundaries

Liệt kê **namespace, ServiceAccounts, workloads/VMs, trust domains, mesh modes, mesh identity issuers, CA root/intermediate, LB/ingress/egress gateways, CNI, cloud connections**. Xác định vùng prod/dev, cluster-to-cluster/partner và user→workload boundaries.

### Bước 2 — Thiết kế principal và quyền

Mỗi workload quan trọng có **ServiceAccount riêng theo security boundary**. Lập ma trận **source principal → destination principal → port/route → action**, xác nhận application owner. Không dùng all namespaces/all trust domains như mặc định.

### Bước 3 — Bảo vệ bootstrap và issuer

Kiểm tra **SA token audience/rotation, Kubernetes RBAC, Pod creation rights, admission, CA/SPIRE Server/Agent permissions, node attestation, Workload API socket, SDS access**. Giới hạn ai có thể cấp identity hoặc thay trust bundle.

### Bước 4 — Cài đặt/đánh giá data plane

Xác minh **sidecar injection hoặc ambient enrollment, ztunnel coverage, waypoint routes**, control-plane HA và interoperability với CNI/NetworkPolicy. Không áp STRICT ở production trước khi biết legitimate non-mesh clients/health checks.

### Bước 5 — Đặt peer authentication

Áp **mTLS inbound policy** theo scope nhỏ, kiểm tra handshake và nguồn plaintext. Di trú theo kế hoạch từ **PERMISSIVE → STRICT** hoặc chính sách tương đương của mesh, tránh giữ PERMISSIVE vô hạn.

### Bước 6 — Đặt authorization theo exact identity

Bắt đầu với policy destination workload cho phép **đúng ServiceAccount principal và port**; với L7 dùng **sidecar Envoy hoặc waypoint** như thực tế, bảo đảm không có bypass. Review policy precedence và cross-namespace trust.

### Bước 7 — Test tích cực và tiêu cực

Với mỗi service đích, thử **allowed principal, denied principal, unmeshed plaintext source, wrong trust domain, expired/untrusted certificate trong lab**, rồi kiểm tra egress/ingress NetworkPolicy, status và logs. Một request ALLOW và một request DENY chỉ có ý nghĩa khi **đường đi thực sự đã qua enforcement point**.

### Bước 8 — Canary và observability

Rollout theo namespace/cluster; monitor **mTLS coverage, cert renewal, trust distribution, xDS/SDS lag, 4xx/5xx/connection errors, app latency**. Đặt alerts trước hạn certificate, khi CA unavailable và khi policy bị sửa trái chuẩn.

### Bước 9 — Rotation và recovery drill

Diễn tập **issuer/root rotation, expired cert, node compromise, policy rollback, mesh outage**. Có owner, approval, expiry và xác minh logs/traffic; không đặt private key trong runbook.

### Bước 10 — Governance liên tục

Review role/RBAC grants, đặc biệt người được **create Pod dùng privileged ServiceAccount**, sửa AuthorizationPolicy, PeerAuthentication, CA secrets, trust domain aliases hoặc admission. Kiểm tra patch level theo security bulletins đúng version mesh.

~~~mermaid
flowchart TD
    A[Inventory workload + trust domains] --> B[Least-privilege ServiceAccount design]
    B --> C[Secure attestation / CA / bootstrap]
    C --> D[Enroll sidecar/ambient or mesh proxies]
    D --> E[Peer mTLS requirement]
    E --> F[Exact peer AuthorizationPolicy]
    F --> G[Staging ALLOW + DENY tests]
    G --> H{mTLS, identity, bypass, app auth đúng?}
    H -- Không --> I[Fix policy/route/issuer/CNI]
    I --> D
    H -- Có --> J[Canary rollout + telemetry]
    J --> K[Rotation, incident drills, periodic review]
~~~

## 31. Runbook ứng phó sự cố mTLS và workload identity

### 31.1. Tình huống A — Các service bắt đầu gặp mTLS handshake failures

**Triệu chứng:** trước đây orders gọi payments được, sau rollout mesh/CA thì request lỗi kết nối, TLS handshake failure, 503 từ proxy hoặc workload không lấy được SVID mới.

**Bước điều tra an toàn:**

1. Xác định **cluster, namespace, source/destination workloads, mesh mode, policy/issuer versions và thời điểm**.
2. Phân biệt **network reachability/CNI deny** với **TLS cert validation failed** và **AuthZ denied**; mỗi loại có evidence khác nhau.
3. Kiểm tra **proxy/ztunnel readiness, istiod/identity service health, certificate expiry metadata, node clock sync, trust bundle mismatch**.
4. Đối chiếu **CA/issuer rotation và namespace PeerAuthentication/AuthorizationPolicy changes** trong cùng cửa sổ.
5. Với ambient, xem **ztunnel–waypoint–workload** path thực tế; không ép debug L7 ở một ztunnel chỉ làm L4.
6. Kiểm tra endpoints, service discovery và sidecar enrollment; lỗi endpoint trống hoặc network deny có thể bị nhầm là mTLS.
7. Dùng Pod/test identity được cấp phép, thử **đúng caller ALLOW và caller không được phép DENY**.

**Khắc phục theo đúng nguyên nhân:** sửa trust bundle/rotation, khôi phục identity controller, chỉnh policy sai scope, phục hồi DNS/CNI, hoặc rollback một change có chứng cứ. **Không tắt verification, không bật PERMISSIVE cho toàn mesh** để che nguyên nhân.

### 31.2. Tình huống B — Một workload bị cấp danh tính ngoài phạm vi

**Triệu chứng:** audit cho thấy Pod debug được chạy với **ServiceAccount payments** hoặc có SPIFFE ID vốn chỉ dành cho payments, mặc dù Deployment không thuộc team payments.

**Giai đoạn 1 — Khẳng định:**

- Xem **Pod UID/namespace/spec.serviceAccountName, creator audit, admission events, SA bindings** và thời điểm cấp cert.
- Đối chiếu **workload registration/attestation** hoặc identity agent metadata đã được bảo vệ.
- Xác minh cert/identity được cấp thật, không chỉ là text khai trong log.
- So policies tại service đích xem principal đó có được phép tới tài sản nhạy cảm không.

**Giai đoạn 2 — Khoanh vùng:**

- Giới hạn nguồn workload bị nghi, dùng **NetworkPolicy/mesh authz** tại service đích và khóa đường Pod/SA impersonation.
- Xem xét thu hồi/đổi issuer/leaf credentials phù hợp với phạm vi compromise.
- Giữ logs và audit trail; tránh hủy bằng chứng khi xóa Pod vội.
- Tìm các workloads khác có chung SA và các API privileges mà SA ấy sở hữu.

**Giai đoạn 3 — Phục hồi:** chỉnh **namespace RBAC, admission, SA ownership, image policy, node/runtime isolation và CI permissions**; xác nhận request được phép vẫn hoạt động, request dùng identity không được phép bị từ chối.

### 31.3. Tình huống C — Root/issuer CA compromise

**Giả định:** issuer có thể ký workload certificates giả. Đây là sự cố **trust infrastructure**, không chỉ lỗi của một Pod.

**Hành động:** kích hoạt CA incident plan, cô lập issuer, bảo vệ/đổi signing keys, thiết kế **new trust bundle và certificate reissuance**, quản lý giai đoạn overlap/retire trust theo mức độ khẩn cấp; phối hợp cross-cluster federation. Phải đánh giá **client/server certificate validation, long-lived sessions và quyền đã cấp**, không chỉ thay một Kubernetes Secret.

### 31.4. Kế hoạch rollback an toàn

Có thể cần rollback policy gây outage, nhưng không làm như thể rollback đồng nghĩa **ALLOW tất cả**. Tạo bản backup policy và IaC artifacts đã duyệt; rollback theo namespace/workload và quan sát **allow/deny tests, cert rotation, route health, CNI connectivity, business SLI**. Nếu chưa chắc trạng thái, tách vùng ảnh hưởng bằng controls mạng hẹp thay vì tắt bảo vệ toàn hệ thống.

### 31.5. Kết luận incident

Một báo cáo có ích cần ghi **timeline, affected principals/trust domains, certificate issuer/version, control-plane changes, network path, actual requests, blocked attempts, data impact evidence, uncertainty, remediation và owner**. “Có cert hợp lệ” không có nghĩa không có xâm nhập; “có TLS error” không tự chứng minh certificate bị đánh cắp.

## 32. Mười hai tình huống thực tế

### A — Orders và Debug dùng chung default ServiceAccount

**Triệu chứng:** mesh AuthorizationPolicy chỉ cho source **default** truy cập payments; Pod debug cũng vào được.

**Nguyên nhân:** hai workloads có cùng danh tính theo ServiceAccount nên rule không đủ hẹp. Cấp **ServiceAccount riêng theo security boundary**, bảo vệ quyền gán SA, và test debug DENY.

### B — STRICT làm health check từ ngoài mesh thất bại

**Triệu chứng:** sau chuyển PeerAuthentication STRICT, một health checker không được mesh mTLS hóa không vào được app, LB báo unhealthy.

**Giải pháp:** map đường health check, di trú legitimate probe/source hoặc cấu hình health mechanism phù hợp. Không chuyển toàn production sang PERMISSIVE vô thời hạn; chỉ thiết kế ngoại lệ tối thiểu nếu cần và có owner.

### C — mTLS thành công nhưng API trả 403

**Triệu chứng:** proxy peer identity verified, nhưng request bị 403.

**Giải thích:** có thể do **mesh AuthorizationPolicy** từ chối đúng caller/route hoặc **application authorization** từ chối user/object. Tra **decision source**, source principal, policy match và application logs; không tắt certificate verification.

### D — Cross-cluster kết nối được nhưng policy không nhận principal

**Triệu chứng:** orders cluster A gọi payments cluster B, certificate chain hợp lệ sau federation nhưng policy vẫn deny.

**Khả năng:** trust domain khác, principal string không đúng, AuthorizationPolicy chưa allow source hoặc traffic qua east-west gateway thay identity theo thiết kế. So **peer principal đã xác minh** và policy scope, không thêm wildcard toàn domain như giải pháp mặc định.

### E — Dev workload vào được dịch vụ production

**Triệu chứng:** service identity cùng namespace/SA được chấp nhận qua shared trust domain/alias.

**Nguyên nhân:** quá tin tương đương identity giữa dev và prod, hoặc authorization chỉ kiểm tra SA name. Tách trust boundaries, CA/federation, principal policy và hạn network reachability.

### F — Waypoint L7 policy bị bypass

**Triệu chứng:** GET endpoint đi qua waypoint được kiểm tra, nhưng client gọi trực tiếp workload IP thì không bị L7 deny.

**Nguyên nhân:** waypoint không phải điểm thực thi trên đường direct workload. Áp **destination L4 allow-only-waypoint**, kiểm tra route, capture và mixed sidecar/ambient migration để không gây outage.

### G — Istio ztunnel được cấu hình DENY theo HTTP method

**Triệu chứng:** policy chỉ deny DELETE nhưng phương thức DELETE vẫn tới backend ở một ambient workload.

**Giải thích:** ztunnel không làm L7. Dùng waypoint với đúng targetRefs, test policy enforcement, và chặn waypoint bypass nếu bắt buộc. Không suy có L7 deny khi chỉ thấy CRD được tạo.

### H — Linkerd workloads đều có mTLS nhưng Pod ngoài mesh vẫn vào được

**Triệu chứng:** hai Pods đã mesh giao tiếp mTLS, nhưng unmeshed health/debug Pod vẫn gửi plaintext đến service.

**Nguyên nhân:** mặc định/policy inbound cho traffic không mesh có thể vẫn cho phép, hoặc skip ports. Thiết kế **Linkerd policy yêu cầu authenticated clients**, kiểm tra injection coverage và legitimate probes.

### I — Certificate rotation thất bại sau outage control plane

**Triệu chứng:** workloads cũ còn chạy, Pod mới hoặc proxy restart không thiết lập được mTLS.

**Phân tích:** certificate đang còn hiệu lực có thể tiếp tục dùng trong khi identity service không cấp mới. Khôi phục issuer/CA/agent và verify trust distribution, không copy một leaf key giữa Pods để “sửa”.

### J — Lộ Workload API socket hoặc private key

**Triệu chứng:** container không đáng tin có thể mount socket cấp SVID hoặc đọc key material của service nhạy cảm.

**Xử lý:** đánh giá node/POD mount isolation và attestation, giảm quyền, rotate credentials có thể lộ, điều tra xem SVID nào đã được sử dụng. Không cho mọi sidecar/container cùng đọc tài nguyên identity nếu không cần.

### K — Mesh policy cho phép nhưng NetworkPolicy chặn

**Triệu chứng:** orders nằm trong allowlist Istio, song request timeout không có mesh authz deny event.

**Giải thích:** CNI egress/ingress có thể chặn trước handshake; xem denied flows, Service endpoints, port mapping và data-plane capture. Không mở NetworkPolicy tất cả để “thử” trên production.

### L — Sidecar bị thiếu sau một rollout

**Triệu chứng:** Deployment mới không inject sidecar, traffic outbound không được mTLS hóa hoặc inbound bị STRICT từ chối.

**Nguyên nhân:** namespace enrollment/injection annotation, admission webhook, Pod security/hostNetwork hoặc rollout configuration. Kiểm tra actual Pod containers và proxy status; thêm **fail-safe admission, alerts proxy coverage và regression**.

## 33. Ma trận 40 kiểm thử workload identity/mTLS

**Chỉ kiểm thử trên namespace, cluster, service identities và endpoints thuộc phạm vi được cấp phép.** Không trộm/giả chứng thư thật, không gửi requests gây hại và không tắt policy production để thử.

| ID | Kịch bản | Kết quả mong đợi | Bằng chứng |
|---|---|---|---|
| **T-01** | orders Pod dùng ServiceAccount orders | Identity map đúng namespace + SA | Pod spec, mesh principal |
| **T-02** | payments Pod dùng SA riêng | Principal khác orders | Identity telemetry |
| **T-03** | Hai replicas orders cùng SA | Cùng logical principal, keys theo issuance design | Cert metadata/identity mapping |
| **T-04** | Debug Pod dùng SA debug | Principal không phải orders | Peer identity log |
| **T-05** | Attestation hợp lệ | SVID/cert được cấp theo policy | Identity issuer event |
| **T-06** | Attestation không hợp lệ trong lab | Không được cấp privileged SVID | SPIRE/CA denial |
| **T-07** | CSR/identity mapping sai trong lab | Issuer từ chối hoặc cấp đúng identity có quyền | CA/attestation audit |
| **T-08** | X.509-SVID URI SAN đúng | Peer chứng thực exact identity | TLS/proxy verified principal |
| **T-09** | Trust bundle không chứa CA signer test | TLS handshake bị từ chối | mTLS error reason |
| **T-10** | Cert không còn hiệu lực trong lab | Peer không chấp nhận cert | Certificate validation log |
| **T-11** | Clock lệch trong test | Lỗi được nhận diện; NTP remediation | Node clock/PKI metrics |
| **T-12** | Rotation certificate thành công | Không gián đoạn quá SLO; cert mới active | Expiry/issuer/proxy metrics |
| **T-13** | Identity service temporarily unavailable | Alert và behavior theo TTL/HA design | Issuance failure/health |
| **T-14** | orders → payments với đúng mTLS identity | ALLOW trong scope được duyệt | Mesh log + app request |
| **T-15** | debug → payments với mTLS identity hợp lệ khác | DENY theo mesh AuthorizationPolicy | AuthZ denial |
| **T-16** | Unmeshed plaintext → STRICT destination | Bị từ chối theo policy | Peer auth logs |
| **T-17** | Chuyển PERMISSIVE → STRICT trong staging | Legitimate flows đi qua mTLS, source thiếu mesh bị phát hiện | Migration coverage |
| **T-18** | PeerAuthentication chọn sai namespace | Test nhận diện scope mismatch | Policy inventory |
| **T-19** | L4 AuthorizationPolicy port 8080 | Chỉ principal/port đã phê duyệt | Endpoint/proxy logs |
| **T-20** | L7 path rule trong sidecar có HTTP processing | Enforce đúng HTTP method/path | L7 proxy log |
| **T-21** | L7 policy đặt nhầm tại ambient ztunnel | Phát hiện không đạt yêu cầu | Negative HTTP tests |
| **T-22** | L7 policy attached waypoint đúng | ALLOW/DENY theo principal + route | Waypoint logs |
| **T-23** | Direct workload path bypass waypoint | Bị chặn bởi destination L4 policy khi yêu cầu | Ztunnel deny |
| **T-24** | Mixed sidecar/ambient migration | Không cắt traffic hợp lệ ngoài kế hoạch | Waypoint/ztunnel/source audit |
| **T-25** | Waypoint identity không phải original caller | Policies đặt đúng enforcement point | Proxy verified identity |
| **T-26** | Linkerd meshed → meshed | mTLS authenticated, cert rotation OK | Linkerd identity/metrics |
| **T-27** | Unmeshed → Linkerd target với strict policy | Bị deny theo expected default/Server policy | Linkerd policy logs |
| **T-28** | Linkerd skip port trong lab | Phát hiện bypass, điều chỉnh port list | Proxy configuration |
| **T-29** | Pod giả label orders nhưng dùng SA debug | Mesh deny dù NetworkPolicy có thể allow | Peer principal event |
| **T-30** | Principal có quyền create Pod dùng SA payments | Admission/RBAC chặn unauthorized use | Kubernetes API audit |
| **T-31** | NetworkPolicy deny trước mesh | Có CNI event, không buộc có mesh deny | CNI flow log |
| **T-32** | Pod khác namespace gọi ClusterIP | Mesh AuthZ deny nếu SA ngoài allowlist | AuthZ event |
| **T-33** | Trust domain staging gọi production | Deny trừ federation/allow policy được duyệt | Trust and AuthZ logs |
| **T-34** | Trust bundle rotation lab | Old/new cert overlap đúng, không overtrust | Trust distribution metrics |
| **T-35** | Thay AuthorizationPolicy qua CI | Change có owner/actor/version, traffic regression | Kubernetes audit + tests |
| **T-36** | Workload identity certificate/key lộ trong tabletop | Runbook có chặn principal/rotate/forensics | Incident drill evidence |
| **T-37** | Direct-to-Pod/NodePort bypass Ingress | Mesh/network policy bảo vệ đúng | Network reachability test |
| **T-38** | JWT user hợp lệ nhưng thiếu tenant permission | App từ chối dù workload mTLS allow | Application AuthZ event |
| **T-39** | Collector mất mesh authz logs | Alert telemetry gap, không suy requests biến mất | Pipeline heartbeat/lag |
| **T-40** | Rollback policy sau canary | Positive ALLOW và negative DENY tiếp tục đúng | Regression/rollback report |

### 33.1. Điều kiện PASS

Một test thành công cần **bằng chứng quyết định ở đúng enforcement point**, không chỉ nhìn HTTP 200/403. Ví dụ request từ debug bị timeout do NetworkPolicy **không chứng minh mesh AuthZ deny đã hoạt động**; phải xem riêng một luồng có network reachability nhưng identity không được phép.

### 33.2. Test negative không phải kiểm thử xâm nhập ngoài phạm vi

Tạo identities/certificates không tin cậy **trong lab có phép**; không brute force/impersonate prod token hoặc thử khai thác SPIRE/CA production. Nếu không có sandbox để test mutation, ưu tiên **static policy checks, simulation và tabletop**.

## 34. Những ngộ nhận thường gặp

| Ngộ nhận | Cách hiểu đúng |
|---|---|
| **“Có mTLS thì mọi workload trong mesh được phép gọi nhau.”** | mTLS chỉ xác thực peer; cần AuthorizationPolicy theo principal. |
| **“Pod IP là danh tính workload.”** | IP thay đổi và chịu NAT; service identity gắn với bằng chứng mật mã. |
| **“Kubernetes Service name là SPIFFE ID mặc định.”** | Nhiều mesh gắn identity với namespace/ServiceAccount, không phải Service resource. |
| **“Namespace tự ngăn traffic cross-namespace.”** | Cần NetworkPolicy/mesh authz, namespace chủ yếu là scope quản lý. |
| **“Hai replicas cùng principal phải dùng cùng private key.”** | Logical principal có thể giống nhưng key/cert nên được cấp riêng và rotate. |
| **“Ai biết chuỗi SPIFFE ID có thể mạo danh service.”** | Phải trình SVID và chứng minh sở hữu khóa/issuer trust. |
| **“SPIFFE là sản phẩm SPIRE.”** | SPIFFE là chuẩn; SPIRE là một implementation. |
| **“Mọi mesh đều dùng SPIFFE format của Istio.”** | Linkerd và các mesh khác có identity formats/policies riêng. |
| **“Cert được ký bởi CA hợp lệ nghĩa là được gọi payments.”** | Phải kiểm tra đúng subject/SAN/trust domain và authorization. |
| **“STRICT chính là allowlist caller.”** | STRICT yêu cầu mTLS, không giới hạn principal nào được gọi. |
| **“PERMISSIVE vẫn bảo đảm mọi request dùng mTLS.”** | Nó có thể nhận plaintext từ nguồn không mesh, cần kiểm tra migration. |
| **“Ambient ztunnel thi hành mọi L7 policies.”** | L7 cần waypoint; ztunnel chỉ hiểu L4 attributes. |
| **“Có waypoint nghĩa không thể bypass.”** | Direct workload paths có thể bỏ waypoint nếu không bị kiểm soát. |
| **“L7 policy attached đúng waypoint thì destination ztunnel vẫn thấy original caller.”** | Destination có thể thấy waypoint identity; caller check thuộc waypoint. |
| **“ServiceAccount token và user JWT là một.”** | Token workload bootstrap không phải end-user access token. |
| **“X-SPIFFE-ID header là proof.”** | Untrusted HTTP headers có thể giả; cần peer certificate verification. |
| **“Delete Pod/SA thu hồi ngay mọi cert.”** | Leaf cert/trust và active sessions có lifecycle riêng. |
| **“Short-lived cert không cần incident response.”** | Compromise vẫn có cửa sổ hiệu lực và khả năng lateral movement. |
| **“Cùng trust anchor thì cùng quyền.”** | Federation/trust chỉ phục vụ xác thực; policy vẫn phải allow hẹp. |
| **“Bật NetworkPolicy thay được mesh identity.”** | NetworkPolicy kiểm soát L3/L4 theo Pod/IP/port, không xác minh service principal. |
| **“Bật mesh thay được application authorization.”** | BOLA, tenant/object rights cần ứng dụng kiểm tra. |
| **“RBAC create serviceAccount quyết định được ai chạy dưới SA.”** | Cần bảo vệ cả quyền tạo/patch workload và admission serviceAccountName. |
| **“Một deny log thiếu nghĩa request không tồn tại.”** | Có thể bị CNI chặn, bypass proxy hoặc collector outage. |
| **“Chuyển cả mesh sang STRICT là luôn an toàn.”** | Cần kiểm kê unmeshed clients, probes, waypoint/multi-cluster và rollout. |
| **“Root rotation chỉ cần thay file PEM ở một nơi.”** | Cần trust bundle rollout và issuer/cert reissuance trên toàn mesh. |
| **“Traffic mTLS mã hóa tới tận application process.”** | Proxy–app hop có thể plaintext trong Pod/host tùy implementation. |

## 35. Checklist an toàn trước production

- [ ] Có danh sách workloads, namespaces, ServiceAccounts, mesh mode và trust domains.
- [ ] Workloads có quyền khác nhau không dùng chung ServiceAccount tùy tiện.
- [ ] Kiểm soát quyền create/patch Pod, Deployment, ServiceAccount, identity-binding và labels.
- [ ] Admission kiểm tra serviceAccountName, namespace ownership và pod security.
- [ ] Identity issuer xác minh node/workload attestation, không tin text header tự khai.
- [ ] TLS private keys, SVID/JWT, SA tokens và Workload API sockets được bảo vệ.
- [ ] Trust root/intermediate CA và ký chứng thư có owner, backup và audit.
- [ ] Workload leaf cert đủ ngắn hạn, có renewal monitoring và TTL SLO.
- [ ] Có quy trình rotation/compromise cho leaf, issuer, root và trust bundles.
- [ ] Peer certificate verification xét chain, time, URI SAN/identity và trust domain.
- [ ] Service destination xác minh **đúng server identity**, không chỉ CA ký hợp lệ.
- [ ] Source identity từ mTLS đã được xác minh mới được dùng cho AuthorizationPolicy.
- [ ] PeerAuthentication STRICT được áp theo phạm vi thích hợp sau migration.
- [ ] Không giữ PERMISSIVE lâu dài không có owner/expiry/telemetry.
- [ ] AuthorizationPolicy giới hạn exact ServiceAccount principal, port/route cần thiết.
- [ ] Không chỉ allow toàn namespace/trust domain nếu có ranh giới nhạy cảm bên trong.
- [ ] Istio policy được target đúng selector/namespace/root namespace.
- [ ] Sidecar injection/ambient enrollment thực sự có hiệu lực trên Pod đang chạy.
- [ ] Envoy/ztunnel identity/certificate distribution được giám sát và kiểm tra khi restart.
- [ ] Ambient L4 policy do ztunnel enforce; L7 policy do waypoint enforce.
- [ ] L7 waypoint security được bảo vệ trước direct-to-Pod/route bypass.
- [ ] Mixed sidecar/ambient migration được kiểm tra trước khi chỉ cho waypoint.
- [ ] Linkerd authenticated inbound policy được cấu hình khi muốn chặn unmeshed plaintext.
- [ ] Các skip ports, hostNetwork, hostPort, NodePort, ingress và egress bypass được kiểm kê.
- [ ] CNI NetworkPolicy chặn lateral paths ngoài danh sách nhưng không cắt dependencies hợp lệ.
- [ ] DNS, service discovery, ingress gateways và health checks có policy riêng đúng phạm vi.
- [ ] TLS/mTLS được đánh giá trên từng đoạn proxy-to-proxy và proxy-to-app.
- [ ] Application tiếp tục kiểm tra user, tenant và object-level authorization.
- [ ] Federation giữa cluster/cloud có trust bundle và principal allowlist hẹp.
- [ ] Dev/staging không mặc nhiên có quyền production chỉ vì trùng SA name.
- [ ] Kubernetes API RBAC hạn quyền sửa mesh policies, mesh controller và CA secrets.
- [ ] Cloud IAM giới hạn roles của mesh gateways/controllers và identity federation.
- [ ] IaC/CI security policy có review, branch protection, owner và rollback.
- [ ] Có logs từ CA/agent, proxy authorization, K8s audit, CNI và app khi cần.
- [ ] Log không chứa raw token, SVID secrets, certificate private keys hoặc PII không cần thiết.
- [ ] Dashboards có mTLS coverage, cert expiry, renewal failures, CA/control plane health.
- [ ] Alert cho policy bị mở rộng, authorization denies tăng, issuer fail và log gaps.
- [ ] Kiểm thử ALLOW đúng identity, DENY wrong identity, plaintext, trust domain, bypass.
- [ ] Có positive tests bảo đảm health checks, APIs và business workflows vẫn hoạt động.
- [ ] Có runbook xử lý expired cert, identity issuer outage, key compromise và CA rotation.
- [ ] Có lịch review security bulletins đúng phiên bản Istio/Linkerd/SPIRE.
- [ ] Chỉ kiểm tra kết nối và principals trong cluster/test scope được phê duyệt.

## 36. Câu hỏi tự kiểm tra

**1. Workload identity khác Pod IP thế nào?**  
Pod IP phục vụ routing và có thể thay; workload identity là danh tính logic được xác minh bằng chứng cứ mật mã như X.509-SVID, có thể ổn định qua nhiều replicas.

**2. SPIFFE ID có phải là certificate không?**  
Không. SPIFFE ID là URI định danh; **SVID** là tài liệu có thể kiểm chứng mang danh tính ấy.

**3. SPIRE là gì?**  
SPIRE là một implementation của các tiêu chuẩn SPIFFE, hỗ trợ node/workload attestation và cấp SVID qua Server/Agent/Workload API.

**4. Trust domain có thay quyền ứng dụng không?**  
Không. Trust domain xác định nguồn danh tính được tin; quyền caller→destination cần authorization policy riêng.

**5. Vì sao ServiceAccount ảnh hưởng đến mesh identity?**  
Nhiều mesh gắn danh tính workload với namespace/ServiceAccount được nền tảng xác minh; người có quyền chạy Pod với SA ấy có thể nhận cùng identity.

**6. Có nên dùng chung ServiceAccount cho tất cả service trong namespace không?**  
Không nên khi quyền khác nhau. Mesh khó phân biệt caller và tạo blast radius nếu một workload bị compromise.

**7. X.509-SVID khác JWT-SVID thế nào?**  
X.509-SVID gắn với keypair/certificate dùng mTLS; JWT-SVID là signed bearer token có audience/validity, cần chống theft/replay.

**8. mTLS bảo vệ gì?**  
Xác thực peer, bảo vệ tính toàn vẹn/bí mật của kênh được mesh bao phủ; không tự kiểm tra user/object-level permission hay đoạn traffic bypass.

**9. PeerAuthentication STRICT có đồng nghĩa default-deny service identities không?**  
Không. STRICT yêu cầu mTLS inbound; Authorized identities phải được hạn bằng AuthorizationPolicy.

**10. Vì sao không được tin X-SPIFFE-ID do HTTP client gửi?**  
Header có thể tự khai. Chỉ verified principal từ certificate/identity-aware trusted proxy mới là bằng chứng đáng tin.

**11. Istio source.principals thường viết dạng nào?**  
Thường dạng **trust-domain/ns/namespace/sa/serviceaccount** theo API Istio, không phải raw URI SPIFFE có scheme ở đầu.

**12. Ambient mode khác sidecar ở điểm enforcement?**  
ztunnel thực thi L4 identity/mTLS policies; waypoint thực thi các L7 route/JWT/path policies khi được thiết kế và traffic thực đi qua.

**13. Vì sao một L7 DENY ở ztunnel có thể gây nguy hiểm?**  
ztunnel không đọc HTTP attributes, nên rule có thể bị bỏ qua; cần waypoint L7 và bypass protection.

**14. Waypoint có thể làm destination ztunnel thấy principal nào?**  
ztunnel có thể thấy identity của **waypoint**; original caller policy nên được thực thi ở waypoint, và L4 policy tại đích có thể chỉ cho waypoint.

**15. Cert rotation thành công có nghĩa private key đã từng lộ không còn được sử dụng ngay?**  
Không chắc. Cert cũ và long-lived sessions có thể còn hiệu lực theo TTL/trust/connection semantics; cần incident controls và policy deny khi cần.

**16. Một caller có mesh identity hợp lệ nhưng không gọi được service, cần xem gì?**  
CNI/NetworkPolicy, DNS/routing, mTLS cert/trust, Authorized principals/ports, waypoint, app authorization và observability gaps.

**17. Vì sao cần tách dev và prod trust?**  
Tránh cùng tên namespace/SA ở môi trường yếu hơn được coi tương đương identity production; federation chỉ nên cấp khi có nhu cầu thật.

**18. SPIFFE federation có tự allow mọi workload từ trust domain khác không?**  
Không. Nó cho phép xác minh chứng cứ identity liên domain; AuthorizationPolicy vẫn phải cho phép principal cụ thể.

**19. Xóa Pod có tự thu hồi tất cả certificates của nó không?**  
Không mặc định. Credential validity/trust distribution/active connections tồn tại độc lập một phần; cần cơ chế rotation và revocation ứng dụng thực tế.

**20. Cần kiểm thử tối thiểu gì trước khi đưa mTLS identity policy lên production?**  
Caller chính đáng **ALLOW**, caller sai **DENY**, unmeshed/plaintext bị xử lý đúng, bypass bị chặn, certificate rotation và ứng dụng vẫn hoạt động theo SLO.

## 37. Tài liệu tham khảo

- [SPIFFE — Tổng quan tiêu chuẩn](https://spiffe.io/docs/latest/spiffe-about/overview/): kiến trúc danh tính workload portable, SPIFFE ID và SVID.
- [SPIFFE — Concepts](https://spiffe.io/docs/latest/spiffe-about/spiffe-concepts/): trust domain, SVID và Workload API.
- [SPIFFE — SPIFFE ID Specification](https://spiffe.io/docs/latest/spiffe-specs/spiffe-id/): định dạng URI SPIFFE ID và tính hợp lệ.
- [SPIFFE — Workload API](https://spiffe.io/docs/latest/spiffe-specs/spiffe_workload_api/): giao diện cung cấp SVID/trust bundles và các yêu cầu an ninh.
- [SPIFFE — Working with SVIDs](https://spiffe.io/docs/latest/deploying/svids/): sử dụng X.509-SVID và JWT-SVID.
- [SPIRE — Concepts](https://spiffe.io/docs/latest/spire-about/spire-concepts/): node attestation, workload attestation và selectors.
- [Istio — Security Concepts](https://istio.io/latest/docs/concepts/security/): workload identity, mTLS, certificate rotation và authorization.
- [Istio — Security Model](https://istio.io/latest/docs/ops/deployment/security-model/): trust/peer verification và các lớp thực thi.
- [Istio — PeerAuthentication Reference](https://istio.io/latest/docs/reference/config/security/peer_authentication/): STRICT, PERMISSIVE và các lưu ý ambient.
- [Istio — AuthorizationPolicy Reference](https://istio.io/latest/docs/reference/config/security/authorization-policy/): principals, source.serviceAccounts, ports và action precedence.
- [Istio Ambient — Layer 4 Policy](https://istio.io/latest/docs/ambient/usage/l4-policy/): enforcement tại ztunnel và hạn chế với L7 attributes.
- [Istio Ambient — Waypoint Proxies](https://istio.io/latest/docs/ambient/usage/waypoint/): proxy L7, traffic redirection và kiểm soát bypass.
- [Istio Ambient — Enforce Authorization Policies](https://istio.io/latest/docs/ambient/getting-started/enforce-auth-policies/): mẫu policy có ztunnel/waypoint.
- [Istio — Security Bulletins](https://istio.io/latest/news/security/): đối chiếu phiên bản mesh với thông báo bảo mật hiện hành.
- [Linkerd — Automatic mTLS](https://linkerd.io/docs/features/automatic-mtls/index.html): danh tính proxy, trust anchors, certificate rotation và caveats.
- [Linkerd — Authorization Policy](https://linkerd.io/docs/features/server-policy/): inbound policy, meshTLS auth và route/server authorization.
- [Linkerd — Automatically Rotating Control Plane TLS Credentials](https://linkerd.io/docs/tasks/automatically-rotating-control-plane-tls-credentials/index.html): issuer và trust anchor lifecycle.
- [Kubernetes — ServiceAccounts](https://kubernetes.io/docs/concepts/security/service-accounts/): danh tính workload dựa trên ServiceAccount.
- [Kubernetes — RBAC Good Practices](https://kubernetes.io/docs/concepts/security/rbac-good-practices/): giảm khả năng impersonation và nâng quyền.
- [Kubernetes — NetworkPolicy](https://kubernetes.io/docs/concepts/services-networking/network-policies/): bổ sung L3/L4 cho mesh identity.
- [Kubernetes — Auditing](https://kubernetes.io/docs/tasks/debug/debug-cluster/audit/): audit identity và policy mutations.
- [NIST SP 800-207 — Zero Trust Architecture](https://csrc.nist.gov/pubs/sp/800/207/final): phân biệt trust, identity, least privilege và continuous verification.
- [NIST SP 800-190 — Application Container Security Guide](https://csrc.nist.gov/pubs/sp/800/190/final): runtime, cluster, node và policy controls.
- [OWASP — Kubernetes Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Kubernetes_Security_Cheat_Sheet.html): RBAC, network policy, secrets và workload security.

**Ghi nhớ:** **Workload identity** trong service mesh là danh tính dịch vụ **được xác minh bằng bằng chứng mật mã**, không phải Pod IP, namespace hoặc tên service tự khai. **SPIFFE/SVID và ServiceAccount-based identity** giúp mTLS xác thực peers; **AuthorizationPolicy** phải quyết định caller nào được thực hiện kết nối/operation nào. Bảo vệ hiệu quả đòi hỏi **attestation đáng tin, key/certificate rotation, trust-domain isolation, đúng enforcement point (Istio sidecar/ambient waypoint, Linkerd), Kubernetes RBAC/admission, CNI NetworkPolicy, TLS/mTLS theo từng hop, cloud firewall và app-level AuthZ**. Luôn kiểm thử **ALLOW/DENY và bypass**, đồng thời chuẩn bị phương án **issuer outage, certificate compromise và trust-bundle rollover**.


