# Authorization policy giữa các service: Cấp quyền theo danh tính trong service mesh

## 1. Vì sao đã bật mTLS vẫn cần authorization policy?

Trong kiến trúc microservices, một request thường đi qua nhiều thành phần: frontend gọi API, API gọi dịch vụ thanh toán, dịch vụ đơn hàng gọi kho dữ liệu, một worker gọi message broker. Các service có thể nằm trong cùng Kubernetes cluster, cùng VPC hoặc kết nối qua nhiều cluster. Chỉ vì các thành phần sử dụng địa chỉ IP riêng, chạy trong những namespace khác nhau hoặc đã bật **mutual TLS (mTLS)** không có nghĩa **mọi service đều được phép gọi mọi service khác**.

**mTLS** chủ yếu giúp hai đầu kết nối **xác thực danh tính của nhau** và bảo vệ **tính bí mật/toàn vẹn của dữ liệu trên kênh truyền**. **Authorization policy** quyết định **danh tính nào** được thực hiện **hành động nào** trên **dịch vụ/tài nguyên nào**, trong những điều kiện nào. Một kết nối được mã hóa và xác thực hoàn toàn vẫn có thể là một kết nối **không được phép**.

Ví dụ: service `frontend` và `billing` đều có chứng thư workload hợp lệ do cùng mesh CA phát hành. Điều đó chỉ chứng minh chúng là những workload đã được mesh xác thực, **không chứng minh `frontend` có quyền gọi API hoàn tiền của `billing`**. Nếu không có chính sách phân quyền, một service bị chiếm quyền có thể tận dụng kênh mTLS hợp lệ để thực hiện lateral movement.

### Mục tiêu học tập

Sau bài học, người học có thể:

1. Phân biệt **authentication**, **mTLS peer identity**, **authorization** và **audit** trong service-to-service communication.
2. Giải thích nguồn gốc, phạm vi và độ tin cậy của **workload identity** như SPIFFE ID/Kubernetes ServiceAccount.
3. Xác định **policy enforcement point** thực sự trong sidecar, ambient mesh, gateway và ứng dụng.
4. Mô hình hóa quyết định **subject–action–resource–context** cho API nội bộ theo nguyên tắc least privilege.
5. Hiểu mô hình **Istio AuthorizationPolicy** và quan hệ với **PeerAuthentication**, **RequestAuthentication**, NetworkPolicy.
6. Phân tích cách kết hợp **ALLOW, DENY, CUSTOM, AUDIT** cùng ưu tiên và những tình huống chọn rule nguy hiểm.
7. Viết mẫu chính sách có giới hạn **service principal, namespace, HTTP method/path và port**; phân biệt kiểm soát L4/L7.
8. Nhận diện rủi ro từ plaintext bypass, workload không tham gia mesh, hostNetwork, service account dùng chung, JWT không được yêu cầu, cross-cluster trust.
9. Kiểm thử chính sách từ **nguồn được phép và nguồn không được phép**, có bằng chứng từ proxy, CNI và application.
10. Thiết lập runbook rollout, theo dõi, xử lý sự cố và khôi phục khi chính sách mới gây lỗi.

Trong chương **Service mesh và mTLS** thuộc module **SECURITY_NETWORK_SECURITY**, chủ đề này nối các lớp **phân đoạn, firewall, VPN, IDS/IPS, DNS, cloud/container networking và bảo vệ kênh truyền** với **quyết định quyền truy cập dựa trên danh tính dịch vụ**. Chính sách mesh là một lớp trong kiến trúc zero trust, không thay thế các lớp bảo vệ khác.

> **Phạm vi ví dụ:** dùng cluster lab `shop-lab`, các service `frontend`, `orders`, `billing` và dữ liệu mô phỏng. Các cấu hình Istio dưới đây chỉ để học và phải được kiểm tra với **phiên bản Istio, data plane mode và CRD** thực tế trước khi triển khai. Không áp dụng `default-deny`, `STRICT` hoặc chính sách DENY lên production khi chưa có change window, positive controls, rollback và phê duyệt; không gửi lưu lượng test tới hệ thống không thuộc quyền quản lý.

## 2. Bốn câu hỏi khác nhau: kết nối, xác thực, cấp quyền, ghi nhận

Giả sử service A gọi `POST /v1/refunds` trên service B:

| Lớp kiểm soát | Câu hỏi | Cơ chế ví dụ | Có thể kết luận gì? |
|---|---|---|---|
| **Network reachability** | A có đường TCP tới B không? | Route, DNS, CNI NetworkPolicy, cloud firewall | Có/không có đường kết nối mạng được phép |
| **Transport authentication** | B đang nói chuyện với workload nào? | mTLS certificate và identity validation | Peer có workload identity đã xác thực |
| **Authorization** | Peer đó được phép `POST /v1/refunds` không? | Mesh AuthorizationPolicy, API gateway, application RBAC | Hành động được allow/deny theo policy |
| **Application/business authorization** | User và giao dịch cụ thể có quyền hoàn tiền không? | API token, user roles, record ownership, approval workflow | Quyền trên dữ liệu/tác vụ cụ thể |
| **Audit/monitoring** | Ai quyết định, tại đâu, khi nào? | Proxy decision logs, traces, app audit, policy revision | Có bằng chứng và khả năng điều tra |

**Xác thực không tạo quyền.** Cả `frontend-sa` và `payments-sa` có thể có workload certificate hợp lệ, nhưng chỉ `payments-sa` được phép gọi endpoint hoàn tiền. Ngược lại, cho phép một IP hoặc một port không chứng minh ai là service thực sự.

### 2.1. mTLS bảo vệ kết nối nào?

~~~mermaid
flowchart LR
    subgraph A["Pod frontend"]
        FA["Application A"]
        PA["Mesh proxy / dataplane A"]
    end
    subgraph B["Pod orders"]
        PB["Mesh proxy / dataplane B"]
        OB["Application B"]
    end
    FA -->|"Local hop"| PA
    PA <-->|"mTLS: peer authentication + encryption"| PB
    PB -->|"Local hop"| OB
    POLICY["Authorization decision"] -. "Enforce tại điểm nhận phù hợp" .-> PB
~~~

Sơ đồ minh họa **sidecar-style data plane**. Local app↔proxy hop không nhất thiết là TLS. Trong **ambient mesh**, điểm thực thi có thể là **ztunnel và/hoặc waypoint**, với khả năng L4/L7 khác nhau. Không lấy sự tồn tại của nhãn “mesh-enabled” làm bằng chứng rằng mọi luồng đã đi qua TLS/proxy và được kiểm soát.

### 2.2. Authn và authz cần đúng thứ tự logic

Nếu chính sách yêu cầu principal `cluster.local/ns/shop-lab/sa/frontend-sa`, điểm thực thi phải nhận được danh tính peer **đã xác thực**, không suy ra từ header tùy ý như `X-Service-Name: frontend`. Chỉ khi có nguồn danh tính hợp lệ mới so nó với tập principals được phép.

Nếu service chấp nhận plaintext tại một đường khác, identity mTLS có thể **không tồn tại** trên đường đó. Một chính sách cấp quyền dựa vào principals phải xử lý trường hợp thiếu identity theo hướng **không cấp đặc quyền**; đồng thời cần đóng **đường bypass** bằng network controls và cấu hình mesh đúng.

## 3. Mô hình chủ thể – hành động – tài nguyên – ngữ cảnh

Một policy dễ review nên trả lời bốn câu hỏi:

| Thành phần | Ví dụ | Điều cần tránh |
|---|---|---|
| **Subject** | SPIFFE workload principal của `frontend-sa` | Tin tên Pod, địa chỉ IP tạm thời hoặc HTTP header giả |
| **Action** | `GET`, `POST`, gRPC method hoặc kết nối TCP tới port cụ thể | Cho phép mọi HTTP methods hoặc mọi port khi không cần |
| **Resource** | `orders` API `/v1/orders/*` hoặc port của dịch vụ dữ liệu | Áp cùng một policy quá rộng cho mọi Pods |
| **Context** | Namespace, trust domain, JWT claims đã xác minh, request path, source namespace | Dùng dữ liệu chưa xác minh hoặc thuộc tính không tồn tại trên TCP |

**Ý định nghiệp vụ** trong lab:

~~~text
Frontend workload identity:
  cluster.local/ns/shop-lab/sa/frontend-sa

Orders workload identity:
  cluster.local/ns/shop-lab/sa/orders-sa

Billing workload identity:
  cluster.local/ns/shop-lab/sa/billing-sa

Desired:
  frontend -> orders  GET /v1/orders/*        ALLOW
  frontend -> billing POST /v1/refunds       DENY
  orders   -> billing POST /v1/charge        ALLOW
  unrelated workload -> orders              DENY
  orders   -> database via approved port    ALLOW by separate policy
~~~

Đây là **mục tiêu chính sách**, chưa phải cấu hình đã được thực thi. Network route có thể vẫn cho các Pods kết nối IP của nhau; **mesh policy cần quyết định cho/từ chối tại đúng destination enforcement point**. Nếu có đường không đi qua mesh proxy, CNI/host firewall và ứng dụng phải tiếp tục bảo vệ.

### 3.1. Áp dụng least privilege

Đừng đặt policy “mọi Pod trong namespace `shop-lab` được gọi tất cả endpoints của `billing`” nếu chỉ `orders` cần `POST /v1/charge`. Một namespace có thể chứa jobs, debugging Pods, deployment cũ và service accounts khác nhau. **Namespace là một phạm vi quản lý**, không phải danh tính dịch vụ đủ chi tiết cho mọi tác vụ.

**Cách ưu tiên:** cho phép đúng workload principal, đúng destination, đúng port và đúng action. Tại ứng dụng, tiếp tục xác minh quyền của user/business operation (đơn hàng cụ thể, số tiền, quyền refund).

### 3.2. Từ policy lý thuyết tới điểm thực thi thật

Một chính sách YAML chỉ có ích khi:

1. Nó **được API server chấp nhận** và thuộc namespace/scope phù hợp.
2. Controller/control plane **dịch chính sách** đúng cho data plane.
3. Request **thực sự đi qua policy enforcement point** có khả năng áp dụng rule.
4. Workload identity **được chứng minh** bằng cơ chế được yêu cầu.
5. Rule **match** đúng protocol, port, method, path và các thuộc tính có sẵn.
6. Không có **ALLOW khác**, bypass path hoặc mô hình quyền ngoài ý định làm mất mục tiêu.
7. Hệ thống có **negative tests và telemetry** chứng minh kết quả.

## 4. Workload identity: điều gì làm một service trở nên đáng tin?

Trong service mesh, certificate dùng cho mTLS thường chứa **workload identity**, có thể dựa trên mô hình **SPIFFE**. Một ví dụ dạng SPIFFE URI:

~~~text
spiffe://cluster.local/ns/shop-lab/sa/frontend-sa
~~~

Đường dẫn này biểu diễn một identity trong **trust domain** `cluster.local`, gắn với Kubernetes namespace `shop-lab` và service account `frontend-sa` theo quy ước thường dùng trong Istio/Kubernetes. Mesh identity được **cấp và xác thực** qua một chuỗi thành phần: workload enrollment, service account/token/attestation, CA, certificate distribution và proxy TLS handshake.

### 4.1. Certificate và identity

| Khái niệm | Ý nghĩa |
|---|---|
| **Trust domain** | Phạm vi định danh và trust anchors được chấp nhận |
| **SPIFFE ID** | URI danh tính workload, thường chứa thông tin namespace/service account theo triển khai |
| **SVID** | Chứng thực danh tính SPIFFE, thường là X.509-SVID; còn có JWT-SVID trong hệ sinh thái SPIFFE |
| **CA / trust bundle** | Cấp và xác minh certificates theo policy |
| **Workload attestation / enrollment** | Cách hệ thống gắn danh tính với workload hợp lệ |
| **Certificate rotation** | Gia hạn/đổi credentials để tránh key/cert hết hạn hoặc dùng kéo dài ngoài ý định |
| **Policy principal** | Giá trị danh tính mà engine authorization so với allow/deny rules |

Trong ví dụ Istio, policy field `source.principals` thường dùng dạng **không có tiền tố `spiffe://`**:

~~~yaml
principals:
  - cluster.local/ns/shop-lab/sa/frontend-sa
~~~

Không nhầm cú pháp **SPIFFE URI trong chứng thư** với **định dạng principal trong API chính sách của một sản phẩm cụ thể**. Tham chiếu chính xác phải được kiểm tra theo phiên bản mesh/controller.

### 4.2. ServiceAccount không tự chứng minh duy nhất một deployment

Nếu hai Deployments cùng chạy bằng `serviceAccountName: frontend-sa`, chúng có thể nhận cùng **workload principal** theo mô hình Istio thông thường. Authorization theo service account sẽ **không phân biệt** chúng chỉ vì Pod names/labels khác nhau.

Đây là lý do nên:

- Cấp **service account chuyên biệt theo workload/trust boundary**, tránh dùng `default` account chung cho nhiều dịch vụ nhạy cảm.
- Giới hạn RBAC quyền **tạo Pod hoặc sửa `serviceAccountName`** để workload không được phép không thể “nhận” danh tính đặc quyền.
- Bảo vệ node admission, service account tokens, CA/trust bundle và certificate issuance.
- Đánh giá việc cấp identity qua nhiều cluster/trust domains có cùng chính sách hay không.

### 4.3. Một principal xác thực không đồng nghĩa user identity

Khi `frontend` gọi `orders`, mTLS thường xác thực **frontend workload**; nó không chứng minh trực tiếp người dùng nào đang thao tác trên trình duyệt. Nếu API cần user-level permission, cần thêm **JWT/OIDC/session hoặc identity context đã xác minh**; không sao chép user identity dưới dạng `X-User: admin` mà không có trusted authentication chain.

### 4.4. Trust domain aliases và multi-cluster

Trong đa cluster hoặc migration, hai mesh/trust domains có thể cần **federation hoặc trust-domain aliases** theo implementation. Mở rộng trust bundle có thể làm một tập workloads mới được xác thực. Chính sách principal dùng chuỗi trust domain phải được review để không vô tình **tin toàn bộ danh tính từ một miền mới** chỉ vì cần kết nối một service.

**Đừng dùng wildcard principals trên nhiều trust domains** nếu yêu cầu chỉ có một caller. Thiết kế phải nêu được trust anchors, danh tính nguồn, namespace/service account và cách xác minh chúng tại destination.

## 5. Threat model: service nào có thể lạm dụng kết nối hợp lệ?

### 5.1. Sơ đồ trust boundaries

~~~mermaid
flowchart LR
    U["Internet user"] --> ING["Ingress gateway"]
    ING --> FE["Frontend workload"]
    FE --> ORD["Orders workload"]
    ORD --> BILL["Billing workload"]
    ORD --> DB["Data service"]
    UN["Unapproved Pod"] -. "Không được gọi Orders" .-> ORD
    FE -. "Không được gọi refund trực tiếp" .-> BILL
    P["Mesh identity / authorization"] -. "Enforce trên data plane" .-> ORD
    P -. "Enforce trên data plane" .-> BILL
    N["CNI / cloud firewall"] -. "Giới hạn bypass paths" .-> UN
~~~

Các ranh giới cần kiểm tra:

1. **User → Ingress**: browser identity, WAF, public TLS, JWT/session.
2. **Ingress → Frontend**: principal của ingress gateway và auth context nào được truyền.
3. **Frontend → Orders**: danh tính service `frontend-sa` được mTLS xác minh.
4. **Orders → Billing**: chỉ `orders-sa` được gọi đúng API/port theo chính sách.
5. **Application → Database**: mesh policy nếu mesh bảo vệ được protocol đó, kết hợp network/database authentication.
6. **Control plane → data plane**: ai được sửa AuthorizationPolicy, PeerAuthentication, ServiceAccount, mesh config.
7. **Bypass paths**: Pod không inject proxy, hostNetwork, NodePort, external LB, health probes, direct Pod IP.

### 5.2. Mối nguy và loại chính sách liên quan

| Mối nguy | Vì sao mTLS chưa đủ | Kiểm soát cần có |
|---|---|---|
| `frontend` gọi endpoint hoàn tiền | Frontend có cert hợp lệ nhưng không có quyền hoàn tiền | Destination authz theo principal + method/path; app-level authz |
| Workload không liên quan gọi `orders` | Mọi workload trong mesh có thể có identity hợp lệ | Default deny + ALLOW tối thiểu |
| Pod giả danh service account quan trọng | Workload dùng chung account hoặc có quyền deploy bằng account khác | ServiceAccount ownership, RBAC/admission, workload identity |
| Pod không tham gia mesh gọi trực tiếp backend | Không có peer principal/không đi qua proxy | STRICT mTLS ở điểm phù hợp, CNI/network firewall, test bypass |
| JWT hợp lệ nhưng scope không đủ | JWT xác thực người dùng chứ không tự cấp quyền nghiệp vụ | Claims validation, scope/role policy, app authorization |
| API GET bị cho phép cả POST | Rule chỉ kiểm tra service identity/port | L7 method/path rules khi dataplane hỗ trợ |
| TCP protocol bị xử lý như HTTP | Method/path không khả dụng trên TCP thuần | L4 port/principal policy, port-specific DENY |
| Bị chiếm quyền một proxy/gateway | Proxy có thể có identity/quyền rộng | Hardening, separation, least privilege, logs |
| Multi-cluster trust quá rộng | Workloads ở domain khác cũng được xác thực | Federation/trust aliases có scope, explicit principals |
| Mesh policy chưa được đẩy tới proxy | API object tồn tại nhưng dataplane chưa cập nhật | Control-plane sync telemetry, policy inspection, canary |
| Chính sách khác mở lại quyền | ALLOW rules cộng dồn hoặc namespace/root policies | Audit tất cả applicable policies, thử nghiệm kết hợp |
| Egress tới Internet quá rộng | Destination ngoài mesh chưa được chính sách inward mesh bảo vệ | CNI/cloud egress firewall, gateway, DNS controls |

**Mục tiêu phòng vệ:** hạn chế **blast radius** khi một workload bị chiếm quyền, kể cả khi attacker đã có một service certificate hợp lệ. Authorization policy không bảo đảm loại bỏ toàn bộ rủi ro, nhưng làm giảm các luồng ngang không cần thiết.

## 6. Policy enforcement point: chính sách được thực thi tại đâu?

Một **Policy Enforcement Point (PEP)** là nơi tiếp nhận thông tin đã xác thực và quyết định allow/deny được thực thi trên traffic. Trong mesh, PEP có thể là:

- **Destination sidecar proxy** cho inbound traffic tới workload.
- **Ingress/egress gateway** cho traffic qua cổng ranh giới.
- **Ambient dataplane** như ztunnel (một số kiểm soát L4) và waypoint (các kiểm soát L7 khi được cấu hình) theo phiên bản và tính năng hỗ trợ.
- **Ứng dụng** cho authorization nghiệp vụ trên từng tài nguyên.
- **CNI/firewall** cho giới hạn đường kết nối ở L3/L4.

### 6.1. Đường data plane và điểm quyết định

~~~mermaid
flowchart TD
    REQ["Request từ workload A"] --> T{"Request có đi qua PEP?"}
    T -- "Không" --> GAP["Policy mesh có thể không được áp dụng"]
    T -- "Có" --> ID{"Danh tính/thuộc tính bắt buộc được xác minh?"}
    ID -- "Không" --> NO["Không cấp quyền đặc biệt / từ chối theo policy"]
    ID -- "Có" --> MATCH{"Policy có cho hành động và đích?"}
    MATCH -- "Không" --> DENY["DENY + telemetry"]
    MATCH -- "Có" --> APP["Forward tới workload ứng dụng"]
    APP --> AUTHZ["Application authz trên dữ liệu cụ thể"]
~~~

**Quan trọng:** chính sách destination proxy không thể bảo vệ một đường đi **không đi qua destination proxy**. Bởi vậy, phải kiểm tra **workload enrollment, iptables/eBPF redirection, ambient interception, host networking, VM/Pod khác kiểu, direct traffic** và các exception port/protocol.

### 6.2. Sidecar và ambient không hoàn toàn tương đương

| Tiêu chí | Sidecar mesh thông thường | Ambient mesh theo thiết kế hỗ trợ |
|---|---|---|
| Điểm chặn traffic | Sidecar proxy đi cùng workload Pod | L4 node proxy/ztunnel và có thể L7 waypoint |
| Nguồn identity | Workload cert/mTLS qua mesh CA | Workload identity với secure transport theo cơ chế ambient |
| L4 authorization | Có thể áp tại dataplane hỗ trợ | Có thể áp tại ztunnel/điểm L4 |
| HTTP L7 authorization | Destination sidecar/gateway nhận HTTP đã giải mã ở hop phù hợp | Cần waypoint/điểm L7 hỗ trợ và đúng policy attachment |
| Lộ trình policy | Namespace/workload selector và control-plane config | Có thể dùng attachment/target references khác theo phiên bản |
| Bypass cần kiểm tra | Non-injected Pod, excluded ports, host networking | Traffic ngoài ambient capture, waypoint enrollment, direct paths |

**Không suy rằng `AuthorizationPolicy` có `methods`/`paths` sẽ được ztunnel L4 tự hiểu.** Khi dùng ambient, cần biết rule thuộc loại L4 hay L7 và liệu waypoint đang xử lý traffic đó hay không. Một số tính năng và cú pháp `targetRefs` thay đổi theo phiên bản; luôn kiểm tra tài liệu và khả năng của dataplane đang dùng.

### 6.3. Quyền được cấp trong ứng dụng vẫn cần thiết

Kể cả khi destination proxy cho `orders-sa` gọi `POST /v1/charge`, ứng dụng billing phải kiểm tra:

- Token/user/order context có hợp lệ và đã được xác thực chưa?
- Đơn hàng có đủ trạng thái để trừ tiền không?
- Giao dịch có đúng tenant, currency, amount và idempotency key không?
- Caller có được hoàn tiền hoặc hủy thanh toán trên bản ghi cụ thể không?

Mesh authorization **không hiểu toàn bộ luật nghiệp vụ** nếu không có policy engine/ứng dụng tương ứng. Ghi một rule HTTP `POST` không thay thế phân quyền theo resource owner.

## 7. Các nguồn identity và thuộc tính request

| Nguồn dữ liệu | Cách thu | Nên dùng trong policy nào? | Rủi ro |
|---|---|---|---|
| **mTLS source principal** | Được xác minh từ peer certificate/mesh identity | Service-to-service allowlist, workload-level policy | Thiếu nếu plaintext hoặc workload không có mTLS |
| **Source namespace** | Được xác định từ mesh identity theo cách implement | Giới hạn vùng/nhóm workloads | Rộng hơn một service account |
| **ServiceAccount** | Mapping principal theo workload identity | Least privilege theo service identity | Shared account tạo chung quyền |
| **Source IP** | Peer IP tại PEP | Rule mạng phụ trợ, network logs | NAT/proxy có thể thay nguồn, IP spoof/trust boundary |
| **HTTP method/path** | Được PEP L7 parse từ request | HTTP/gRPC L7 authorization | Không sẵn trên TCP thuần, normalization khác app |
| **JWT request principal** | Được xác minh từ JWT khi cấu hình authentication | Xác thực end-user/client token ở gateway/destination | Không chứng minh workload mTLS và cần explicit require token |
| **JWT claims** | Thuộc tính từ token đã xác minh | Scope/role/tenant hints theo policy | Claims quá rộng, token forwarding hoặc audience sai |
| **SNI/Host** | TLS/HTTP routing attributes | Hostname routing và một số gateway policies | Header Host có thể do client khai, khác certificate identity |
| **Custom identity headers** | Do ingress/auth proxy phát hành theo hợp đồng | Chỉ khi có nguồn đã chứng minh và không thể bypass | Header giả nếu client truy cập trực tiếp |

### 7.1. Hai cấp danh tính không thể tự đổi chỗ cho nhau

Một HTTPS request từ browser qua ingress rồi đến API có thể có:

~~~text
Transport peer tại API:
  principal = cluster.local/ns/ingress-system/sa/ingress-gateway-sa

Application user:
  JWT subject = user-12345, verified issuer/audience

Requested action:
  GET /v1/orders/987
~~~

Mesh principal là **ingress gateway**, không phải `user-12345`. Cần **cả chính sách cho phép ingress gateway gọi API** lẫn **quyền user truy cập order 987**. Không copy `sub` của JWT vào mesh principal hoặc coi mTLS chứng minh danh tính browser.

### 7.2. Không tin địa chỉ IP hoặc header để thay thế cert identity

Traffic qua Service, sidecar, NAT, CNI và egress gateway có thể thay đổi địa chỉ source IP quan sát. Các HTTP headers như `X-Forwarded-For`, `X-Service-Identity` hoặc `X-Authenticated-User` có thể được client tự gửi nếu edge không chuẩn hóa. Với service-to-service mesh, **mTLS-derived principal** thường đáng tin hơn một chuỗi header không có nguồn bảo đảm. Dùng trusted headers khi có **hợp đồng rõ và không có đường bypass**, không dùng chúng làm quyền mặc định.

### 7.3. Kiểm tra trust domain và audience riêng

Workload certificate được tin bởi mesh CA không đồng nghĩa một JWT từ issuer bất kỳ hợp lệ. Tương tự, JWT có signature hợp lệ không chứng minh nó dành cho **đúng audience và mục đích** nếu authorization không xét. Hai hệ thống trust cần được cấu hình/tư duy độc lập, rồi kết hợp theo policy yêu cầu.

## 8. Cách đọc Istio AuthorizationPolicy

Istio cung cấp custom resource `AuthorizationPolicy` trong API security. Một policy có thể dùng các trường chính:

| Trường | Ý nghĩa | Điểm dễ nhầm |
|---|---|---|
| `metadata.namespace` | Namespace sở hữu policy | Scope có thể chịu quy tắc **mesh root namespace** hoặc attachment đặc biệt |
| `spec.selector` | Chọn workload bằng Pod labels theo ngữ nghĩa chính sách | Label không tự là danh tính mật mã; không áp cho mọi waypoint kiểu ambient |
| `spec.targetRefs` | Đính policy vào đối tượng được hỗ trợ, ví dụ Service/Gateway theo phiên bản/implementation | Không tự tương đương `selector`; cần kiểm tra release/support |
| `spec.action` | `ALLOW`, `DENY`, `CUSTOM`, `AUDIT` theo chức năng | Không được lấy thứ tự từ vị trí YAML file |
| `spec.rules` | Một hoặc nhiều điều kiện có thể tạo match | **Không có rule** khác với rule rỗng `{}` |
| `from.source` | Điều kiện danh tính và thông tin nguồn | `principals`, `namespaces` đòi hỏi identity đáng tin |
| `to.operation` | Port, HTTP method/path/host tùy protocol | Không có HTTP attributes cho TCP thuần |
| `when` | Các điều kiện thuộc tính bổ sung, ví dụ verified JWT claim | Điều kiện chỉ hữu ích khi thuộc tính thực có mặt và đáng tin |

### 8.1. Cấu trúc rule: AND và OR

Một cấu trúc tư duy hữu ích:

~~~text
Policy:
  rules: [rule1, rule2]                  -> rule1 OR rule2

Inside a rule:
  from: [source1, source2]              -> source1 OR source2
  to: [operation1, operation2]         -> operation1 OR operation2
  when: [condition1, condition2]       -> condition1 AND condition2

Matching a rule requires:
  matching source AND operation AND any when conditions
  (the fields that are present in that rule)
~~~

**Một mảng nhiều giá trị cùng thuộc tính** như `methods: ["GET", "HEAD"]` thường mang ý nghĩa chọn một trong các giá trị. Các trường `not...` là phép loại trừ theo schema; không nên dùng để viết logic phủ định phức tạp trước khi thử nghiệm.

### 8.2. Policy evaluation: CUSTOM, DENY, ALLOW và AUDIT

Với mô hình authorization của Istio, cách diễn giải thực dụng là:

1. Các policy **`CUSTOM`** liên quan có thể gọi external authorization provider; nếu từ chối thì request bị từ chối theo semantics của extension.
2. Nếu có policy **`DENY`** áp dụng và match, request bị từ chối, bất kể có rule ALLOW khác.
3. Nếu **không có ALLOW policy nào áp dụng**, request không bị cơ chế ALLOW chặn mặc định (vẫn có thể bị mTLS/DENY/CUSTOM/firewall/app chặn).
4. Nếu **có ít nhất một ALLOW policy áp dụng**, request phải match một ALLOW rule thì mới được phép qua lớp ALLOW; nếu không match, bị từ chối.
5. **`AUDIT`** dùng ghi nhận/đánh dấu quyết định cần audit theo khả năng dataplane và telemetry, **không tự block** request.

~~~mermaid
flowchart TD
    R["Request tới một PEP"] --> C{"CUSTOM policy liên quan cho phép?"}
    C -- "Không" --> X["Reject"]
    C -- "Có / không áp dụng" --> D{"Có DENY rule match?"}
    D -- "Có" --> X
    D -- "Không" --> A{"Có ALLOW policy áp dụng?"}
    A -- "Không" --> OK["Không bị lớp ALLOW chặn"]
    A -- "Có" --> M{"Match ít nhất một ALLOW rule?"}
    M -- "Không" --> X
    M -- "Có" --> OK
    OK --> APP["App tiếp tục xác thực/phân quyền nghiệp vụ"]
~~~

**AUDIT không phải một bước tuần tự cho phép/từ chối trong sơ đồ.** Logging/telemetry có thể được thực thi song song theo khả năng sản phẩm. Kết quả thực còn phụ thuộc các tầng khác và cấu hình dataplane/version.

### 8.3. Policy rỗng: hai hình thức khác hẳn nhau

~~~yaml
# Ví dụ Istio ALLOW policy không chứa rules:
# Ở phạm vi workload được chọn, không có rule ALLOW nào match từ policy này.
apiVersion: security.istio.io/v1
kind: AuthorizationPolicy
metadata:
  name: default-deny-example
  namespace: shop-lab
spec: {}
~~~

Khi **chỉ có chính sách ALLOW này áp dụng**, request không match rule nào nên bị chặn theo lớp ALLOW. Nhưng nếu một **ALLOW policy khác** cũng áp dụng cho workload và match request, rule đó vẫn có thể cho phép vì các ALLOW rules **cộng dồn**. Không xem default-deny policy là một DENY có quyền phủ quyết.

Ngược lại:

~~~yaml
# PHẢN VÍ DỤ: rule {} thường match mọi request thuộc scope của policy.
# KHÔNG ÁP DỤNG vào production.
apiVersion: security.istio.io/v1
kind: AuthorizationPolicy
metadata:
  name: allow-all-example
  namespace: shop-lab
spec:
  action: ALLOW
  rules:
    - {}
~~~

Policy thứ hai có một **rule rỗng**, mang ý nghĩa match mọi request trong phạm vi policy đó; dùng sai có thể mở quyền rộng. Tương tự, một `DENY` policy với `rules: - {}` có thể **từ chối mọi request** trong phạm vi áp dụng. Các khác biệt này cần code review và tests, không phán đoán theo tên resource.

## 9. PeerAuthentication STRICT: bảo đảm tầng xác thực transport

`PeerAuthentication` trong Istio mô tả chế độ mTLS inbound tại các workloads thuộc phạm vi phù hợp. Một mẫu lab:

~~~yaml
# LAB: có thể làm ngắt tất cả callers chưa mesh/mTLS.
apiVersion: security.istio.io/v1
kind: PeerAuthentication
metadata:
  name: require-mtls
  namespace: shop-lab
spec:
  mtls:
    mode: STRICT
~~~

Ở cấu hình sidecar/workload Istio phù hợp, `STRICT` yêu cầu các kết nối inbound qua mesh dataplane **sử dụng mTLS hợp lệ**. Điều này giúp policies dùng `source.principals` có thông tin peer identity cần thiết, nhưng **không tạo allowlist** cho từng service.

### 9.1. Các chế độ mTLS cần phân biệt

| Chế độ | Ý định | Điều cần chú ý |
|---|---|---|
| **STRICT** | Chỉ nhận inbound mTLS theo dataplane/policy support | Callers chưa mesh hoặc TLS không hợp lệ có thể bị từ chối |
| **PERMISSIVE** | Có thể chấp nhận mTLS và plaintext theo ngữ cảnh | Request plaintext có thể **không có peer principal** |
| **DISABLE** | Tắt mTLS ở phạm vi áp dụng | Không phù hợp với mục tiêu identity-based mTLS authz nếu thiếu nguồn xác thực khác |
| **UNSET** | Kế thừa policy theo scope phù hợp | Phải kiểm tra policy kế thừa và effective mode |

### 9.2. STRICT không thay thế authorization policy

~~~text
Frontend       -> Orders : mTLS OK
Unknown mesh SA -> Orders : mTLS OK, identity vẫn hợp lệ

Nếu Orders không có ALLOW restriction / DENY thích hợp:
  Unknown workload có thể được mesh cho qua tới application.

Nếu Orders chỉ ALLOW frontend-sa:
  Unknown workload bị chặn dù có mTLS certificate hợp lệ.
~~~

Đây là sự khác biệt giữa **“tôi biết ai gọi”** và **“tôi cho danh tính đó thực hiện việc này”**.

### 9.3. Compatibility khi rollout STRICT

Trước khi chuyển từ `PERMISSIVE` sang `STRICT`, cần:

- Inventory callers: đã tham gia mesh, gateway, batch jobs, probes, VMs, cross-cluster clients?
- Xác minh **client TLS origination** và trust bundle; destination không thể tự ép một unmeshed caller tạo Istio mTLS.
- Phân loại traffic bị loại trừ khỏi mesh interception, port đặc biệt và health probes.
- Thử positive flow từ trusted service và negative flow từ caller không có mTLS.
- Có canary/rollback, quan sát TLS handshake errors, 503/connection reset và SLO.
- Đánh giá policy đã áp vào **đúng workload mode**; trong ambient, kiểm tra cấp L4 và các giới hạn version.

Không áp một namespace-wide STRICT lên production chỉ vì muốn “bật bảo mật nhanh”. Nó có thể ngắt nhiều dependencies nếu các callers không tương thích.

## 10. AuthorizationPolicy ALLOW theo principal, port và hành động

Giả sử namespace `shop-lab` có workload `orders` chạy HTTP tại port 8080, source `frontend` dùng dedicated service account `frontend-sa`. Ý định: chỉ service đó được gửi `GET` vào API orders.

### 10.1. Đầu tiên đặt baseline chính sách

~~~yaml
# LAB: policy ALLOW không có rules - cô lập tầng ALLOW cho namespace.
# Không áp lên production trước khi có allow rules cho phụ thuộc hợp lệ.
apiVersion: security.istio.io/v1
kind: AuthorizationPolicy
metadata:
  name: namespace-default-deny
  namespace: shop-lab
spec: {}
~~~

Khi một workload ở namespace này không có bất kỳ ALLOW rule áp dụng nào match request, request bị từ chối ở tầng authorization. Tuy nhiên, **không phải một DENY có mức ưu tiên riêng**: các ALLOW policies khác có thể mở luồng. Kiểm tra **root-namespace policies, selector và những targetRef policies** liên quan khi dùng các data planes khác nhau.

### 10.2. Cho phép một workload principal gọi một nhóm route

~~~yaml
# LAB ONLY: ví dụ sidecar-style Istio AuthorizationPolicy.
# Cần kiểm tra controller/version, workload labels, mesh identity và port thực.
apiVersion: security.istio.io/v1
kind: AuthorizationPolicy
metadata:
  name: orders-allow-frontend-read
  namespace: shop-lab
spec:
  selector:
    matchLabels:
      app: orders
  action: ALLOW
  rules:
    - from:
        - source:
            principals:
              - cluster.local/ns/shop-lab/sa/frontend-sa
      to:
        - operation:
            methods:
              - GET
            paths:
              - /v1/orders
              - /v1/orders/*
            ports:
              - "8080"
~~~

**Đọc kỹ điều kiện:**

- `selector.matchLabels.app: orders` chọn **destination workloads** có label phù hợp trong scope namespace theo mô hình sidecar hỗ trợ.
- `source.principals` yêu cầu **peer identity đã được mTLS xác minh** khớp danh tính `frontend-sa`, không phải Pod có tên bắt đầu bằng `frontend`.
- `methods: GET` giới hạn HTTP method, không tự cho phép `POST`, `PUT` hoặc `DELETE`.
- `paths` giới hạn **đường HTTP** theo path matching/normalization của Istio/proxy; cần test percent encoding, slash và path transformations.
- `ports: ["8080"]` là **destination workload port tại PEP**, không tự là Service port/public LB port.

Nếu API orders được phục vụ qua `Service port 80 → targetPort 8080`, rule cần được đánh giá theo **destination port mà Envoy/PEP quan sát**, không đơn giản điền cổng Ingress 443. Không suy kiểu đường nội bộ từ tên port.

### 10.3. Một policy riêng cho Billing

~~~yaml
# LAB: chỉ orders-sa được gọi POST /v1/charge tại Billing.
apiVersion: security.istio.io/v1
kind: AuthorizationPolicy
metadata:
  name: billing-allow-charge-from-orders
  namespace: shop-lab
spec:
  selector:
    matchLabels:
      app: billing
  action: ALLOW
  rules:
    - from:
        - source:
            principals:
              - cluster.local/ns/shop-lab/sa/orders-sa
      to:
        - operation:
            methods:
              - POST
            paths:
              - /v1/charge
            ports:
              - "9090"
~~~

**Kết quả kỳ vọng:** một workload `orders-sa` mTLS đúng có thể gọi endpoint này, còn `frontend-sa` không được vì không có ALLOW rule phù hợp với billing. Nhưng cần **kiểm tra mọi ALLOW policies khác áp dụng cho billing**; một policy mở rộng từ trước có thể làm mục tiêu ít quyền thất bại.

### 10.4. Health probes, monitoring và debugging

Không mặc định mở `GET /healthz` cho **mọi principal** chỉ để readiness hoạt động. Các probes của kubelet, sidecar, node agents và monitoring có đường đi/điểm thực thi khác nhau tùy mesh/CNI/Pod. Hãy kiểm tra **probe rewrite, excluded ports, monitoring identity** và tạo exception đúng cần thiết, không bỏ toàn bộ authorization.

### 10.5. Với ambient mesh, policy attachment có thể khác

Đối với workload được xử lý qua **ambient ztunnel/waypoint**, policy L7 cần được gắn đúng **waypoint/Service/target** theo semantics của phiên bản tương ứng. Ví dụ dùng `selector` cho sidecar ở trên **không tự bảo đảm** method/path được enforce bởi một ztunnel chỉ có khả năng L4. Thực hiện kiểm tra theo mode thực, không chỉ đối chiếu YAML với một mẫu sidecar.

## 11. DENY policy: lớp phủ quyết cho hành động không được phép

Mặc dù dùng default-deny cộng với các ALLOW rules cụ thể là cách hiệu quả để đạt least privilege, một số môi trường cần **DENY rõ ràng** đối với cổng quản trị, một method nhạy cảm hoặc nguồn bị cấm, để ngăn một ALLOW policy khác mở nhầm. Trong Istio, **DENY rule match có quyền phủ quyết** một ALLOW rule.

### 11.1. Ví dụ chặn port quản trị tại workload API

~~~yaml
# LAB: DENY traffic tới port 9000 của orders.
# Port 9000 là port giả định, cần kiểm tra port thật trước khi dùng.
apiVersion: security.istio.io/v1
kind: AuthorizationPolicy
metadata:
  name: orders-deny-admin-port
  namespace: shop-lab
spec:
  selector:
    matchLabels:
      app: orders
  action: DENY
  rules:
    - to:
        - operation:
            ports:
              - "9000"
~~~

Policy này mô tả **từ chối request đi qua PEP của orders đến port 9000** theo hỗ trợ implementation; nó không dựa vào nội dung HTTP request. Không đặt port thật đang phục vụ business API vào DENY mà chưa đánh giá tác động và test.

### 11.2. Vì sao DENY theo HTTP path có thể gây lỗi với TCP?

Một số thuộc tính như `methods`, `paths` không tồn tại trên **TCP thuần**. Theo semantics Istio, khi **DENY policy** dùng thuộc tính HTTP mà request là TCP và thiếu thuộc tính đó, các điều kiện thiếu có thể được **đối xử như match trong ngữ cảnh DENY**. Điều này có thể khiến DENY rộng hơn người viết nghĩ.

~~~yaml
# PHẢN VÍ DỤ: DENY theo HTTP method mà KHÔNG giới hạn port.
# Có thể ảnh hưởng kết nối TCP thuần ngoài dự tính; không áp dụng.
apiVersion: security.istio.io/v1
kind: AuthorizationPolicy
metadata:
  name: unsafe-deny-post-without-port
  namespace: shop-lab
spec:
  selector:
    matchLabels:
      app: orders
  action: DENY
  rules:
    - to:
        - operation:
            methods:
              - POST
~~~

Nếu mục tiêu chỉ là HTTP port 8080, phải **giới hạn port rõ** và kiểm thử rule trên các listeners/protocols của workload:

~~~yaml
# LAB: giới hạn DENY ở cổng được thiết kế là HTTP.
apiVersion: security.istio.io/v1
kind: AuthorizationPolicy
metadata:
  name: orders-deny-post-on-http-port
  namespace: shop-lab
spec:
  selector:
    matchLabels:
      app: orders
  action: DENY
  rules:
    - to:
        - operation:
            ports:
              - "8080"
            methods:
              - POST
~~~

**Quan trọng:** rule mẫu cuối sẽ chặn **mọi HTTP POST đến orders:8080**, kể cả những POST hợp lệ, và cần được thay theo nhu cầu thật. Không sao chép như policy production. Với TCP ports khác, phải test rằng chúng **không bị chặn ngoài ý định**.

### 11.3. Mối quan hệ với các ALLOW policies

~~~text
Rule ALLOW:
  frontend-sa -> orders GET /v1/orders/* : ALLOW

Rule DENY:
  * -> orders port 9000                 : DENY

Evaluation:
  frontend-sa GET on 8080  : Có thể ALLOW nếu không policy khác từ chối
  frontend-sa to port 9000 : DENY cho dù có một ALLOW rộng khác
  unknown-sa GET on 8080   : DENY khi tồn tại ALLOW policies áp dụng
~~~

Policy evaluation phải xét **toàn bộ policies có hiệu lực**, không chỉ một manifest. Root namespace, namespace-local rules, selector/targetRefs và attachment semantics có thể tạo phạm vi khác với người review tưởng.

## 12. JWT request authentication khác peer mTLS identity

Với API cần xác minh **người dùng hoặc client token**, Istio có cơ chế `RequestAuthentication` để cấu hình xác minh JWT trong request tại workloads được chọn. Tuy nhiên, **cấu hình JWT validation riêng chưa phải một quy tắc bắt buộc mọi request phải có token**.

### 12.1. Mẫu RequestAuthentication cho endpoint có user token

~~~yaml
# LAB: issuer/JWKS là URL giả định và chưa có service thực.
# JWT phải được phát hành bởi issuer có khóa/trust hợp lệ.
apiVersion: security.istio.io/v1
kind: RequestAuthentication
metadata:
  name: orders-jwt
  namespace: shop-lab
spec:
  selector:
    matchLabels:
      app: orders
  jwtRules:
    - issuer: https://id.lab.example.test/
      jwksUri: https://id.lab.example.test/.well-known/jwks.json
      audiences:
        - orders-api
~~~

Khi JWT được cung cấp theo nơi nhận dạng của policy và sai chữ ký, hết hạn, issuer hoặc audience, dataplane có thể từ chối theo quy tắc xác thực. Nhưng **request hoàn toàn không cung cấp JWT** có thể vẫn đi qua lớp `RequestAuthentication` nếu chưa có rule yêu cầu JWT.

### 12.2. Yêu cầu có JWT đã xác minh cho một route

~~~yaml
# LAB: yêu cầu BOTH ingress workload principal và JWT request principal
# trên HTTP GET /v1/orders/*; tùy ingress/backend topology thực.
apiVersion: security.istio.io/v1
kind: AuthorizationPolicy
metadata:
  name: orders-require-ingress-and-jwt
  namespace: shop-lab
spec:
  selector:
    matchLabels:
      app: orders
  action: ALLOW
  rules:
    - from:
        - source:
            principals:
              - cluster.local/ns/ingress-system/sa/ingress-gateway-sa
            requestPrincipals:
              - "*"
      to:
        - operation:
            methods:
              - GET
            paths:
              - /v1/orders/*
            ports:
              - "8080"
~~~

Trong ví dụ, cả **mTLS workload principal** và **JWT request principal** đều phải có để rule match. Tuy nhiên:

- `requestPrincipals: ["*"]` chủ yếu chứng minh **một JWT đã được xác thực** theo cấu hình; chưa nói user có quyền đọc mọi order.
- Một **ALLOW policy khác** áp dụng cho orders có thể cho phép cùng request mà **không yêu cầu JWT**. Muốn coi route là “bắt buộc JWT”, phải audit **tất cả ALLOW policies** và các PEP/đường bypass.
- JWT issuer/JWKS phải thật, key rotation/availability và audience được kiểm soát; ví dụ dùng domain giả định.
- Một ingress có thể **xác thực user trước** rồi chuyển danh tính theo cơ chế khác; không cố trộn hai kiến trúc mà chưa thiết kế rõ.

### 12.3. Khi nào dùng claim-based authorization?

Một policy có thể xét claims đã xác minh, ví dụ `request.auth.claims[role]`, theo hỗ trợ của dataplane và cấu trúc token. Nhưng:

- Role/scope claims có thể không phản ánh **quyền trên một order cụ thể**.
- Multi-tenant APIs cần xác minh tenant id từ nguồn tin cậy và mapping tới tài nguyên thật.
- Token của một audience khác không nên dùng thay cho workload certificate.
- Một JWT của người dùng có thể bị forwarded qua nhiều services; cần giới hạn token propagation và replay theo threat model.

Nếu policy cần logic động như số tiền, vai trò theo đơn hàng hoặc trạng thái giao dịch, **ứng dụng hoặc external authorization service** thường phù hợp hơn một biểu thức match đơn giản trên method/path.

## 13. CUSTOM và AUDIT: mở rộng quyết định nhưng không bỏ ranh giới tin cậy

### 13.1. CUSTOM external authorization

Action `CUSTOM` trong Istio có thể tích hợp **external authorization provider** đã được cấu hình trong mesh (ví dụ một dịch vụ kiểm tra token/permission theo mô hình hỗ trợ). Nó không phải cú pháp chung để gọi tùy ý đến URL trong `AuthorizationPolicy` mà không có provider configuration.

~~~mermaid
flowchart LR
    C["Caller"] --> P["Destination proxy/PEP"]
    P -->|"Authorization check"| EXT["Configured external authorization provider"]
    EXT -->|"Allow/Deny"| P
    P -->|"Nếu được phép bởi toàn bộ layers"| APP["Backend application"]
~~~

Khi dùng external authz cần kiểm tra:

1. **Provider identity và kết nối:** proxy gọi provider qua đường nào, có TLS/mTLS và trust CA không?
2. **Nguồn dữ liệu:** provider được thấy method/path/header/identity nào, có rò rỉ credentials không?
3. **Không tin spoofed headers:** external service phải phân biệt identity mTLS/JWT đã xác thực với giá trị người gửi tự khai.
4. **Timeout/circuit breaking:** policy khi provider chậm hoặc down, có fail-open/fail-closed như thiết kế không?
5. **Caching:** token/claims và resource permissions có thể đổi, cần TTL/invalidation phù hợp.
6. **Rate/availability:** external authz có thể thành điểm lỗi tập trung; cần HA, metrics và bảo vệ service.
7. **Combine policies:** CUSTOM cho qua **không phủ quyết** một DENY policy khác; cần đánh giá toàn bộ policy chain.

**Không áp dụng** một đoạn CUSTOM YAML dùng tên provider không tồn tại rồi kỳ vọng mesh tự tạo provider. Cấu hình cụ thể khác theo Istio release/extension provider và loại dataplane.

### 13.2. AUDIT không phải “DENY nhưng chỉ log”

Policy `AUDIT` mô tả **việc đánh dấu request để audit** theo khả năng dataplane/logging đã được cấu hình. Nó **không từ chối** request như `DENY` và không tạo bảo vệ nếu chỉ thêm YAML mà telemetry chưa bật.

Đối với mô phỏng rollout, có thể sử dụng **telemetry và audit policy** để đo request candidates trước khi siết ALLOW, nhưng **không coi đó là shadow-mode hoàn toàn tương đương** của một DENY policy phức tạp nếu implementation không hỗ trợ. Phải xác minh log evidence và policy matching.

### 13.3. Quyết định không chỉ là allow/deny

Ngoài verdict, hệ thống cần ghi:

- Source workload identity đã xác minh, không chỉ IP.
- Destination service, port, route, policy name/revision.
- Tầng nào từ chối: mTLS handshake, mesh authorization, CNI, external authz hay application.
- User principal từ token, khi được phép ghi, và **không log raw token**.
- Trace/request ID xuyên hop, timestamp UTC và mức tin cậy của dữ liệu.

**Thấy HTTP 403 không chứng minh DENY từ Istio AuthorizationPolicy.** 403 có thể do Envoy, external auth service hoặc backend app. Cần định vị PEP và log/response metadata cụ thể.

## 14. L4 và L7: kiểm soát TCP không giống HTTP/gRPC

### 14.1. L4 policy

Ở tầng L4, các thuộc tính có thể gồm peer principal đã xác thực, namespace và destination port. Những luồng như PostgreSQL, Redis, Kafka hoặc TCP proprietary protocols **không có HTTP method/path**, trừ khi traffic được xử lý qua một proxy có hiểu protocol và hỗ trợ attributes tương ứng.

Ví dụ: chỉ `orders-sa` được kết nối tới database TCP/5432 là một mục tiêu **L4/mTLS identity policy**, nhưng database vẫn cần **xác thực tài khoản, quyền SQL, TLS theo cơ chế của nó**. Không dùng một HTTP path policy để bảo vệ một TCP port chỉ vì cả hai đều được đặt dưới mesh.

### 14.2. L7 policy

Ở HTTP/HTTP2, proxy có thể xác định `method`, normalized `path`, `host`, một số request headers và token claims đã xác minh. Điều này cho phép giới hạn:

~~~text
frontend-sa -> GET /v1/orders/*     ALLOW
frontend-sa -> POST /v1/refunds     DENY
orders-sa   -> POST /v1/charge      ALLOW
~~~

Nhưng L7 matching không thay thế application authorization trên tài nguyên: `GET /v1/orders/987` có thể là endpoint hợp lệ, nhưng chỉ user được phép mới được đọc order 987.

### 14.3. gRPC method names và routes

gRPC thường dùng HTTP/2, method được mã hóa thành đường dẫn như:

~~~text
/package.Service/Method
~~~

Một mesh hỗ trợ HTTP/2 L7 có thể áp authorization theo path hoặc metadata tương ứng. Tuy nhiên **gRPC method/path parsing**, HTTP transcoding, gateway rewrites và traffic classification tùy proxy/data plane. Nếu proxy nhận nhầm protocol là TCP, rules theo `methods`/`paths` có thể không match hoặc tạo deny không dự kiến.

### 14.4. Path normalization và L7 mismatch

Proxy có thể chuẩn hóa percent-encoding, slash, dot segments hoặc case theo cấu hình, trong khi ứng dụng/framework xử lý đường dẫn theo quy tắc khác. Khi match rule theo path, phải thử:

- Slash cuối đường, segment rỗng, đường dẫn có hoặc không có prefix.
- URL encoding/decoding, ký tự đặc biệt, Unicode khi có.
- Reverse proxy path rewrite, gRPC transcoding và HTTP/2 `:path`.
- Phân loại port là HTTP, HTTP2/gRPC hay TCP.

**Không xây allowlist bằng một wildcard path rộng rồi coi controller và backend hiểu giống nhau.** Dùng test đúng runtime, không chỉ đọc một biểu thức YAML.

## 15. Policy scope, tenancy và quyền thay đổi chính sách

Một policy chỉ an toàn khi **đúng người có quyền tạo và sửa**, và đúng data plane nhận/thi hành nó. Trong Kubernetes, `AuthorizationPolicy` là một custom resource; quyền thay đổi thuộc **Kubernetes RBAC/admission**, không tự được bảo vệ bởi chính các rule authorization của mesh.

### 15.1. Namespace policy và mesh-wide policy

Istio có những phạm vi chính sách khác nhau:

- Policy trong namespace ứng dụng với selector phù hợp thường áp dụng cho **workloads được chọn**.
- Policy trong **mesh root namespace** có thể có phạm vi mesh-wide theo semantics của implementation.
- `selector` và `targetRefs` có hành vi, đối tượng được chọn và khả năng hỗ trợ khác nhau, đặc biệt với **gateway/ambient waypoint**.
- Các policy ở nhiều phạm vi có thể cùng áp dụng; quyết định cuối không được suy từ **một** YAML object riêng lẻ.

**Không lấy namespace của policy làm bằng chứng chính sách chỉ áp cho một Service duy nhất.** Cần kiểm tra target workload, labels, root namespace, version controller và config đã được đẩy tới dataplane.

### 15.2. Ai có quyền gì?

| Chủ thể | Quyền cần thiết | Quyền cần hạn chế |
|---|---|---|
| **Platform/mesh administrator** | Quản lý mesh CA, control plane, trust domain, global policy, gateway | Không phát quyền này mặc định cho app developers |
| **Security policy owner** | Định nghĩa baseline deny, exceptions, policy review | Không có toàn quyền sửa mọi workload code nếu không cần |
| **Application team** | Đề xuất ALLOW cho workloads do team sở hữu | Không sửa policies của tenant khác, root namespace hoặc trust config |
| **CI/GitOps pipeline** | Triển khai đúng namespace/objects theo approval | Không dùng token cluster-admin dùng chung |
| **Workload** | Chỉ dùng service account/identity của chính nó | Không tự cập nhật AuthorizationPolicy/PeerAuthentication |
| **Auditor/SOC** | Đọc effective policy, logs và change history | Không cần đọc private keys hoặc raw JWT secrets |

### 15.3. Rủi ro đặc biệt của quyền deploy Pod

Nếu team A có thể tạo một Pod với `serviceAccountName` thuộc identity mà team B được cho phép, policy mesh theo principal có thể **không phân biệt hai Deployments**. Kubernetes RBAC và admission cần hạn chế **quyền sử dụng service account đặc quyền** theo thiết kế, và không cho service account chung cấp quyền rộng cho nhiều trust boundaries.

**Không coi `metadata.labels.app: orders` là chứng thư danh tính.** Labels giúp chọn workloads nhận policy; định danh peer cần được xác minh qua mTLS hoặc cơ chế được chấp nhận. Một actor có quyền sửa labels có thể thay đổi **phạm vi policy đang áp** nếu không bị admission/ownership kiểm soát.

### 15.4. Đừng dựa vào tên resource để suy hiệu lực

Một policy tên `deny-all` có thể đang chứa ALLOW rules rộng; một policy tên `only-frontend` có thể không match workload do label thay đổi. Đánh giá phải dựa trên **spec, selector, targetRefs, action, rules và dataplane effective config**, không dựa vào tên YAML hay annotation mô tả.

## 16. Ingress gateway, external callers và danh tính bị chuyển tiếp

### 16.1. Caller của API có thể là gateway, không phải frontend

Trong một luồng:

~~~text
User browser
  -> Public CDN/WAF
  -> Ingress gateway
  -> Orders API
~~~

Destination proxy của Orders có thể thấy mTLS peer là **ingress gateway service account**, nếu ingress→Orders được bảo vệ bằng mesh mTLS và gateway có identity đó. Nó **không tự thấy** SPIFFE identity của browser hoặc identity của frontend nếu frontend không nằm trên đường đó.

Vì thế policy muốn Orders nhận traffic từ gateway phải:

- Đưa **gateway principal** vào phạm vi được phép cho route phù hợp.
- Xác minh **user JWT/session** ở gateway/Orders theo thiết kế và ngăn header spoofing.
- Hạn chế **đường bypass gateway** từ Pod khác qua NetworkPolicy hoặc authorization ở backend.
- Không cấp quyền của user A cho user B chỉ vì cả hai đều qua cùng ingress principal.

### 16.2. Forwarded identity headers và trust boundary

Một số ingress/authentication gateways có thể truyền `X-Authenticated-User`, `X-User-Id` hoặc headers riêng. Các giá trị đó **chỉ là dữ liệu HTTP** trừ khi:

1. Gateway đã xác minh user theo nguồn đáng tin (token/session).
2. Gateway **xóa/ghi đè** headers do client tự khai.
3. Backend chỉ tin connection đến từ **mTLS peer gateway đúng identity** hoặc đường không thể bypass.
4. Backend không có source path khác cho phép gửi header giả.
5. Hệ thống giới hạn phạm vi user claims và có app-level authorization.

Nếu không đáp ứng các điều kiện này, client có thể giả người dùng bằng cách gửi header mang tên quen thuộc.

### 16.3. Mô hình external auth service

Nếu gateway gọi external auth service để kiểm tra user trước khi chuyển tới API, cần bảo vệ **gateway→auth service** bằng policy và TLS phù hợp; cần quan sát failure behavior. **Auth service được phép quyết định quyền** không có nghĩa **mọi request qua gateway đều có quyền với mọi resource**. Kiểm tra cả gateway routing, API authorization và quyền kết nối vào auth service.

## 17. Đường bypass mesh: mạng vẫn là lớp phòng vệ bắt buộc

AuthorizationPolicy chỉ có tác dụng ở điểm mà traffic **thực sự được intercept và policy được thực thi**. Một số đường cần rà soát:

| Đường đi | Vì sao có thể không được mesh policy bảo vệ đầy đủ | Kiểm soát cần có |
|---|---|---|
| Pod không được mesh enrollment/injection | Không có proxy hoặc secure dataplane trên đường đó | Admission, STRICT tại đích, CNI firewall |
| Pod có `hostNetwork: true` | Network path khác Pod network thường | Node firewall, CNI host policy, hạn chế hostNetwork |
| Port bị exclude khỏi interception | Traffic đi thẳng tới app | Review excluded ports, application auth, NetworkPolicy |
| Sidecar/waypoint không được cập nhật | Policy còn ở control plane, proxy chưa nhận | Sync status, config inspection, canary |
| Ambient không gắn đúng waypoint | Chỉ có L4 PEP nên HTTP method/path không được enforce như kỳ vọng | Enrollment/targetRef phù hợp, L7 tests |
| Direct Pod IP/ClusterIP từ workload khác | Không qua ingress gateway, có thể thiếu identity/auth layer dự kiến | Destination mesh policy, CNI policy, app authz |
| NodePort/public LoadBalancer khác | Có thể bypass route/WAF được thiết kế | Cloud SG/NSG, LB inventory, gateway authentication |
| VM/legacy service ngoài mesh | Không có SVID/mesh transport tương thích | Workload enrollment, dedicated gateway, network ACL |
| Local app→sidecar/loopback | Nhiều local hops không dùng TLS | Pod trust model, app/process isolation, least privilege |
| Direct Internet egress | Destination ngoài mesh không chạy PEP của mình | Egress firewall/proxy, DNS policy, identity |

### 17.1. CNI NetworkPolicy và mesh authorization bổ sung cho nhau

**Kubernetes NetworkPolicy** có thể giới hạn Pod-level ingress/egress khi CNI hỗ trợ thực thi. **Mesh AuthorizationPolicy** có thể giới hạn **workload principal và HTTP methods/paths** ở điểm PEP phù hợp. **Application authorization** bảo vệ user và tài nguyên cụ thể.

~~~mermaid
flowchart TD
    A["Caller Pod"] --> N{"CNI / network policy cho flow?"}
    N -- "Deny" --> X["Không kết nối"]
    N -- "Allow" --> T{"mTLS xác thực peer?"}
    T -- "Không" --> X
    T -- "Có" --> M{"Mesh authz cho action?"}
    M -- "Không" --> X
    M -- "Có" --> B{"App authz cho user/resource?"}
    B -- "Không" --> X
    B -- "Có" --> OK["Thực hiện tác vụ"]
~~~

Sơ đồ biểu diễn các **điều kiện logic cần thỏa**, không khẳng định thứ tự packet processing chính xác trên mọi CNI/mesh. Một firewall có thể từ chối trước TLS, hoặc proxy xử lý traffic tại vị trí khác.

### 17.2. Policy dự kiến cho database

~~~text
Network layer:
  Chỉ orders Pod/service identity được tới DB TCP/5432.

Mesh layer (nếu DB traffic đi qua PEP hỗ trợ):
  Chỉ mTLS principal orders-sa được kết nối vào DB listener.

Database layer:
  DB authentication hợp lệ, role chỉ có SQL permissions cần thiết.

Operational layer:
  TLS hostname/CA, audit query/roles, secrets rotation và flow logs.
~~~

Khi một DB là managed cloud service **không tham gia cùng mesh**, destination mesh policy có thể **không tồn tại**. Đặt egress restrictions tại source/gateway/network, và xác minh TLS/database credentials tới cloud endpoint.

### 17.3. Egress policies không tự chặn mọi đường Internet

Việc khai báo service registry, ServiceEntry hoặc egress gateway **không tự bảo đảm toàn bộ Pod traffic bắt buộc qua gateway**, nếu ứng dụng còn đường trực tiếp ra Internet hoặc bypass interception. Đối với yêu cầu không cho exfiltration, cần kết hợp:

- CNI egress deny/allowlist và host/cloud firewall.
- Route ra Internet thông qua egress gateway/proxy đúng thiết kế.
- DNS policies, private endpoints, NAT/source IP inventory.
- Service identity và TLS certificate validation tới đối tác.
- Positive/negative tests từ đúng Pod và node, cả IPv4/IPv6.

**Gateway egress là một dataplane component, không phải phép màu để loại bỏ mọi network bypass.**

## 18. Multi-cluster, federation và failover authorization

Khi các services phân tán qua nhiều clusters/regions, authorization phải giữ cùng **mức ít quyền nhất** nhưng identity và đường mạng có thể thay đổi:

~~~mermaid
flowchart LR
    A["Orders / Cluster A"] --> EG["East-west gateway"]
    EG --> WG["Ingress / Cluster B"]
    WG --> B["Billing / Cluster B"]
    I["Trust bundle / identity federation"] -. "Xác thực theo policy" .-> WG
    P["Authorization ở destination"] -. "Principal + action + port" .-> B
~~~

### 18.1. Ba loại danh tính có thể khác nhau

- **Caller workload identity:** danh tính của Orders trong Cluster A.
- **Gateway identity:** danh tính của east-west gateway nếu nó terminate/re-originate TLS.
- **Destination workload identity:** Billing trong Cluster B.

Điều quan trọng là **destination PEP thật sự thấy identity nào** theo topology. Không mặc định xuyên cluster thì luôn bảo tồn original principal, hay chỉ thấy gateway principal. Nếu một gateway terminate TLS và origination một kết nối mới, trách nhiệm xác thực và chuyển assertion phải được xác định cụ thể.

### 18.2. Trust bundle mở rộng có tăng bề mặt tin cậy?

Có thể. Khi Cluster B chấp nhận CA/trust domain của Cluster A, nhiều danh tính hơn có thể được xác thực. **Không cấp quyền cho toàn bộ trust domain chỉ vì một workload ở A cần gọi B.** Authorization nên chọn đúng principals và các namespaces/service accounts có sở hữu rõ, kèm hạn chế issuer/CA và rotation.

### 18.3. Policy khi failover

Khi traffic chuyển sang Cluster B/region DR:

1. Destination PEP có nhận được chính sách đúng không?
2. Gateway/proxy ở DR có mTLS identity và CA trust phù hợp?
3. Service account/principal có khác khi đổi cluster/trust domain?
4. CNI/firewall return paths có cho đúng luồng và chặn những nguồn không được phép?
5. JWT issuer/JWKS, external auth provider có sẵn không?
6. Có fallback nào **fail-open** khi identity provider unavailable không?
7. Audit logs có nối được request ID và policy revision giữa clusters không?

**HTTP 200 từ vùng DR không đủ chứng minh authz vẫn đúng.** Phải chạy lại negative tests: unapproved principal, wrong method/path, missing JWT, bypass gateway và cross-namespace callers.

## 19. Quan sát chính sách thực tế bằng công cụ chỉ đọc

**Nguyên tắc:** một `AuthorizationPolicy` tồn tại trong Kubernetes API **không đồng nghĩa** workload đã nhận và thực thi policy đúng. Cần quan sát **Pod identity, dataplane enrollment, policy resources, proxy configuration/sync và log quyết định**. Các lệnh dưới đây chỉ minh họa cho **cluster lab có quyền**, không phải lệnh đã chạy trên hệ thống thực.

### 19.1. Đầu tiên kiểm tra kubecontext và workload identities

~~~bash
# Chỉ đọc: kiểm tra đang ở đúng cluster/namespace lab.
kubectl config current-context
kubectl get namespaces
kubectl get pods -n shop-lab -o wide --show-labels
kubectl get serviceaccounts -n shop-lab

# Xem serviceAccountName và Pod UID để phân biệt workloads thật.
kubectl get pod ORDERS_POD -n shop-lab \
  -o jsonpath='{.metadata.uid}{"\n"}{.spec.serviceAccountName}{"\n"}{.metadata.labels}{"\n"}'

# Đọc Service/EndpointSlice, không suy từ tên Service.
kubectl get services -n shop-lab -o wide
kubectl get endpointslices -n shop-lab
~~~

Thay `ORDERS_POD` bằng Pod thuộc lab đã được duyệt. Output có thể lộ tên namespace, node, Pod IP, labels và kiến trúc nội bộ; không chia sẻ lên nơi công khai.

### 19.2. Đọc các chính sách security Istio

~~~bash
# Chỉ đọc: yêu cầu cluster đã cài các Istio CRDs tương ứng.
kubectl get authorizationpolicies.security.istio.io -A
kubectl get peerauthentications.security.istio.io -A
kubectl get requestauthentications.security.istio.io -A

# Xem đúng policy và những rule/selector/ports đã khai báo.
kubectl describe authorizationpolicy orders-allow-frontend-read \
  -n shop-lab
kubectl get authorizationpolicy orders-allow-frontend-read \
  -n shop-lab -o yaml

# Xem PeerAuthentication namespace lab.
kubectl get peerauthentication require-mtls -n shop-lab -o yaml
~~~

Nếu CRD không được cài hoặc mesh dùng **sản phẩm khác**, lệnh có thể báo `the server doesn't have a resource type`; đây không tự là một lỗi CNI/network. Tương tự, policy nằm trong một namespace khác hoặc dùng root policy phải được xem cùng nhau để biết **effective scope**.

### 19.3. Quan sát data plane đã nhận policy chưa

Với cluster dùng **Istio sidecar mode và CLI tương thích**:

~~~bash
# Chỉ đọc, tùy phiên bản Istio/data plane:
# Kiểm tra đồng bộ giữa control plane và proxies.
istioctl proxy-status

# Xem listeners/config trên proxy của Orders Pod trong lab.
istioctl proxy-config listeners ORDERS_POD -n shop-lab
istioctl proxy-config clusters ORDERS_POD -n shop-lab
~~~

Lệnh có thể thay đổi options theo phiên bản, quyền và cấu trúc dataplane. Đối với **ambient**, `proxy-config` trên Pod không chứa sidecar có thể **không áp dụng**; phải dùng công cụ tương ứng cho ztunnel/waypoint và đánh giá chính xác phiên bản. **Không kết luận policy đã enforce** chỉ từ `istioctl proxy-status` cho thấy trạng thái đồng bộ tốt; cần test allow/deny.

### 19.4. Xem Kubernetes RBAC cho quyền sửa policy

~~~bash
# SelfSubjectAccessReview: lệnh chỉ đọc đối với quyền truy cập hiện tại.
kubectl auth can-i get authorizationpolicies.security.istio.io \
  -n shop-lab

# Kiểm tra quyền tạo/sửa policies của identity đang dùng trong lab.
kubectl auth can-i create authorizationpolicies.security.istio.io \
  -n shop-lab
kubectl auth can-i patch authorizationpolicies.security.istio.io \
  -n shop-lab
~~~

`kubectl auth can-i` **không tạo/sửa policy**; nó hỏi API server về quyền. Nếu muốn kiểm tra quyền của CI identity khác, dùng cơ chế impersonation/ủy quyền chính thức; không tự mượn token hoặc bypass RBAC.

### 19.5. Một phép thử HTTP từ đúng caller Pod

~~~bash
# CHỈ lab, Pod đã có curl và endpoint test chỉ đọc.
# Request được phát ra với identity/network context của frontend Pod.
kubectl exec -n shop-lab FRONTEND_POD -- \
  curl --silent --show-error --max-time 5 \
  --output /dev/null --write-out '%{http_code}\n' \
  http://orders.shop-lab.svc.cluster.local:8080/v1/orders/test-only
~~~

Kết quả cần giải thích theo **service, method GET, principal frontend-sa, TLS origination, endpoint readiness và application behavior**. Nếu test nhận HTTP 200, phải có log/proxy evidence chứng minh request được phép đúng danh tính, không phải đi qua đường bypass. Nếu nhận 403/503, không kết luận ngay có rule DENY: tách **mesh authz, proxy upstream, CNI, mTLS và application**.

### 19.6. Test từ caller không được duyệt

~~~bash
# CHỈ lab: Pod UNAPPROVED_POD thuộc ServiceAccount không nằm trong ALLOW.
kubectl exec -n shop-lab UNAPPROVED_POD -- \
  curl --silent --show-error --max-time 5 \
  --output /dev/null --write-out '%{http_code}\n' \
  http://orders.shop-lab.svc.cluster.local:8080/v1/orders/test-only
~~~

**PASS khi** destination PEP từ chối vì principal không match và có bằng chứng từ proxy/mesh telemetry. Nếu mạng hoặc app đang down, kết quả chỉ là **INCONCLUSIVE**, trừ khi có thêm thông tin chứng minh từ enforcement point.

### 19.7. Những lệnh không được xem là read-only

`kubectl apply`, `kubectl patch`, `kubectl delete`, `kubectl rollout restart`, thay `PeerAuthentication` hoặc gỡ sidecar đều **thay đổi trạng thái**, có thể gây outage hay mở security boundary. Chỉ thực hiện trong một triển khai được phê duyệt, với config diff, canary, tests và rollback.

## 20. Ma trận kiểm thử authorization giữa các service

Bộ kiểm thử cần chứng minh cả **service hợp lệ vẫn làm việc** và **caller không có quyền bị từ chối vì đúng policy**, không phải vì backend tắt. Kết quả sau là **tiêu chí đề xuất**, chưa chạy thực tế.

| Test ID | Kiểm soát | Phương pháp trong lab được phép | PASS khi |
|---|---|---|---|
| **IDN-01** | Source mTLS principal khớp service account | Gọi từ Pod `frontend-sa`, so proxy identity | Identity được xác minh đúng |
| **IDN-02** | Caller sai service account không mạo danh | Gọi từ `unapproved-sa` | Không nhận quyền `frontend-sa` |
| **IDN-03** | ServiceAccount không dùng chung ngoài design | Audit Pod specs và RBAC | Mỗi sensitive workload có account phù hợp |
| **TLS-01** | Destination yêu cầu mTLS STRICT | Gọi từ mesh caller đã duyệt | Kênh mTLS hợp lệ, app nhận đúng |
| **TLS-02** | Plaintext caller không qua | Controlled unmeshed caller test | Bị chặn đúng enforcement point |
| **TLS-03** | Cert/trust không hợp lệ bị từ chối | Policy/trust validation trong lab | Không chấp nhận peer identity sai |
| **ALLOW-01** | Frontend GET orders được phép | `GET /v1/orders/test-only` từ frontend | Đúng rule ALLOW match |
| **ALLOW-02** | Unapproved Pod GET orders bị chặn | Cùng path từ identity không được duyệt | Deny do authz, positive control OK |
| **ALLOW-03** | Frontend không gọi billing | Controlled request tới billing API lab | Không có ALLOW rule phù hợp |
| **ALLOW-04** | Orders gọi billing charge theo policy | Test handler sandbox không thực hiện giao dịch tiền | Service identity và action được phép |
| **DENY-01** | Port quản trị được bảo vệ | Test connection tới admin port trong lab | DENY dù có ALLOW khác |
| **DENY-02** | DENY không chặn TCP sai phạm vi | Test TCP service độc lập | Không có match ngoài ý định |
| **DENY-03** | ALLOW và DENY precedence đúng | Xem combined policy + test | DENY có hiệu lực khi match |
| **HTTP-01** | Method không được phép bị chặn | GET vs POST tại route test read-only | HTTP method rule enforce đúng |
| **HTTP-02** | Path không được phép bị chặn | Host/path test ngoài allowlist | Không mở route rộng hơn policy |
| **HTTP-03** | Path normalization khớp ứng dụng | Test slash/encoding trong lab | Proxy/app không hiểu path khác nhau gây bypass |
| **JWT-01** | JWT thiếu bị từ chối khi bắt buộc | Request không mang JWT | Không được phép dù mTLS peer hợp lệ |
| **JWT-02** | JWT sai signature/issuer/audience bị từ chối | Token lab cố ý không hợp lệ | Không có trusted request principal |
| **JWT-03** | User hợp lệ nhưng sai quyền tài nguyên bị từ chối | App-level test order của tenant khác | API authz deny đúng record |
| **CUSTOM-01** | External auth service cấp quyết định | Authorized test qua provider | Allow/deny đúng và có audit |
| **CUSTOM-02** | Provider failure có fail behavior đúng | Simulate outage trong lab | Không tạo fail-open trái policy |
| **BYPASS-01** | Pod unmeshed không bypass | Traffic từ unmeshed lab Pod | Không vào backend trái quyền |
| **BYPASS-02** | Direct Pod IP/ClusterIP không bỏ authz | Gọi API không qua gateway | PEP/app từ chối caller không được duyệt |
| **BYPASS-03** | NodePort/hostNetwork không bypass | Review listener/network + test hạn chế | Không có đường ngoài enforcement |
| **SCOPE-01** | Root/namespace policies không mở rộng ALLOW | Audit mọi applicable ALLOW policies | Least-privilege effective rules đúng |
| **SCOPE-02** | Tenant không đổi principal/policy ngoài quyền | RBAC/admission checks | Không dùng quyền deploy để chiếm identity |
| **AMB-01** | Ambient L4 policy thực thi ở ztunnel | Test đúng ambient capture path | L4 deny/allow theo identity |
| **AMB-02** | Ambient L7 policy có waypoint phù hợp | Kiểm tra attachment + method/path test | Không nhầm L4 với L7 |
| **DR-01** | Failover giữ cùng authz | Repeat allow/deny ở DR cluster | Không có trust/principal bypass |
| **OBS-01** | Authz logs có provenance | So PEP logs/identity/policy revision | Source và verdict truy vết được |
| **OBS-02** | Logging không lộ credentials | Review artifacts/log access | Không xuất token/key/secrets |

### 20.1. Quy tắc kết luận

- **PASS:** bằng chứng **đồng thời** cho thấy positive flow đến được đúng app, negative flow bị chặn bởi **đúng PEP/policy**, danh tính nguồn được xác minh, không có đường bypass.
- **FAIL:** principal không thuộc allowlist nhưng vẫn gọi được, method/path sai vẫn được quyền, unmeshed path bypass, DENY policy không như thiết kế hoặc một ALLOW khác mở quyền rộng.
- **INCONCLUSIVE:** backend chưa ready, DNS lỗi, thiếu cert, test chạy nhầm account/namespace, không có log hoặc request bị chặn ở cloud firewall trước khi tới PEP cần kiểm thử.

Một kết quả **`curl` timeout** không đủ chứng minh mesh authorization DENY. Một response **403** cũng chưa đủ: phải biết 403 từ Envoy, external authorization service hay backend app.

### 20.2. Mẫu bằng chứng cho test âm tính

~~~yaml
test_id: ALLOW-02
environment: authorized-isolated-mesh-lab
time_utc: pending
source:
  namespace: shop-lab
  service_account: unapproved-sa
  pod_uid: pending
destination:
  service: orders
  port: 8080
  request:
    method: GET
    path: /v1/orders/test-only
expected:
  mTLS_identity: unapproved_service_account
  mesh_authorization: deny
positive_control:
  source_service_account: frontend-sa
  mesh_authorization: allow
evidence_required:
  - source-and-destination-pod-uid
  - effective-authorization-policies
  - mtls-peer-identity
  - proxy-authorization-decision-and-response-code
  - cni-flow-status
  - positive-control-application-result
result: pending-execution
~~~

Đây là **mẫu học tập**, không phải bằng chứng đã thu. Chỉ ghi dữ liệu phục vụ kiểm định, không lưu access tokens, JWT nguyên bản, private keys hay nội dung người dùng nhạy cảm.

## 21. Case study 1: Shared ServiceAccount làm tăng phạm vi lateral movement

### 21.1. Bối cảnh giả định

Một tổ chức vận hành các dịch vụ `frontend`, `orders`, `reporting` và `billing` trong cùng Kubernetes cluster. Service mesh đã bật mTLS cho Pods được quản lý. Team muốn chỉ `orders` gọi `billing` theo endpoint `POST /v1/charge`.

Tuy nhiên, vì muốn đơn giản hóa manifest, `orders` và `reporting` được triển khai với **cùng Kubernetes ServiceAccount `shared-business-sa`**. Policy của `billing` cho phép principal `cluster.local/ns/shop-lab/sa/shared-business-sa` trên port 9090.

~~~text
Frontend Pod:
  serviceAccountName: frontend-sa

Orders Pod:
  serviceAccountName: shared-business-sa

Reporting Pod:
  serviceAccountName: shared-business-sa

Billing policy:
  ALLOW principal shared-business-sa on POST /v1/charge
~~~

**Vấn đề:** mesh có thể xác thực cả Orders và Reporting bằng **cùng principal**. Nếu chỉ dựa principal đó, Billing **không phân biệt** Request từ hai Deployments theo tên hoặc labels. Workload `reporting` không có business need để charge nhưng có thể nhận quyền từ cấu hình identity quá rộng.

### 21.2. Sơ đồ nguyên nhân

~~~mermaid
flowchart LR
    O["Orders Pod"] -->|"SA: shared-business-sa"| ID["Cùng mesh principal"]
    R["Reporting Pod"] -->|"SA: shared-business-sa"| ID
    ID -->|"ALLOW POST /v1/charge"| BILL["Billing API"]
    POL["AuthorizationPolicy tại Billing"] -. "Không phân biệt deployments bởi tên Pod" .-> BILL
~~~

**Không cần giả định attacker đã kiểm soát Reporting để nhận diện lỗi.** Chỉ cần đối chiếu `serviceAccountName` của hai Pods, identity được cấp qua mTLS và chính sách Billing là đủ thấy **một quyền ngoài ý định** có thể tồn tại. Để xác nhận enforcement thực tế, dùng một negative test ở lab với request chỉ đọc/không gây giao dịch tài chính.

### 21.3. Vì sao Kubernetes namespace hoặc Pod labels không giải quyết?

| Biện pháp đơn lẻ | Vì sao chưa đủ |
|---|---|
| `orders` và `reporting` có Pod labels khác nhau | Destination mTLS peer principal vẫn trùng nếu dùng chung ServiceAccount |
| Chạy khác Deployments | Deployment name không tự xuất hiện trong SPIFFE ID của mô hình này |
| Chạy cùng private subnet | IP routing không phân biệt quyền charge |
| Có certificate hợp lệ từ mesh CA | Cả hai chứng thư đều hợp lệ; **mTLS không cấp quyền** |
| Billing có `AuthorizationPolicy` | Policy cấp quyền cho principal chung nên scope vẫn quá rộng |
| NetworkPolicy cho cả namespace gọi Billing | Namespace-level allow có thể rộng hơn business need |

### 21.4. Sửa thiết kế và kiểm thử

1. Cấp **dedicated ServiceAccounts**: `orders-sa` cho Orders và `reporting-sa` cho Reporting.
2. Giới hạn RBAC/admission: Reporting team không thể tùy ý tạo Pod sử dụng `orders-sa`.
3. Gia hạn/xoay identity theo lifecycle của Pods và xác minh mesh đã cấp **principal khác nhau**.
4. Đổi Billing ALLOW policy để chỉ chấp nhận `cluster.local/ns/shop-lab/sa/orders-sa` cho route/cổng được duyệt.
5. Xóa/bỏ rule cho `shared-business-sa` sau migration có canary và rollback.
6. Kiểm tra **tất cả applicable ALLOW policies** không còn cấp quyền tương đương.
7. Giữ application/database authorization: một POST hợp lệ từ Orders vẫn phải thỏa quy tắc nghiệp vụ, tránh duplicate transaction.

### 21.5. Ma trận before/after

| Luồng | Before (rủi ro giả định) | After (mục tiêu) |
|---|---|---|
| Orders → Billing POST test route | ALLOW do shared identity | ALLOW theo `orders-sa` |
| Reporting → Billing POST test route | Có thể ALLOW cùng principal | DENY theo mesh policy |
| Frontend → Billing POST test route | DENY nếu không có ALLOW khác | DENY |
| Orders → Billing GET vào admin route | Tùy policy rộng | DENY nếu không trong allowlist |
| Reporting cố dùng `orders-sa` | Cần xem quyền tạo Pod | Denied by Kubernetes RBAC/admission |

**Kết quả chỉ được đánh dấu PASS khi:** Reporting thực sự bị policy từ chối **do sai identity**, Orders vẫn gọi API test được và không có đường khác bypass. Không gọi endpoint tài chính thật để thử tính đúng của policy; dùng **test handler/mocks trong lab**.

### 21.6. Bài học rút ra

**Mesh identity là cơ sở cho authorization, nhưng identity phải đủ hẹp.** Nếu hai workloads cùng chia sẻ một principal, policy theo principal có thể cấp quyền chéo ngoài ý định. Hãy phối hợp **dedicated service accounts, RBAC/admission, mesh authorization và application controls**.

## 22. Case study 2: Chính sách L7 không có điểm thực thi phù hợp

### 22.1. Bối cảnh giả định

Một platform team chuyển một nhóm workloads từ sidecar mode sang **ambient mesh**. Trước đây, Orders có policy `ALLOW` chỉ cho `frontend-sa` dùng `GET /v1/orders/*`. Team cho rằng YAML cũ giữ nguyên nghĩa, nên không kiểm tra waypoint hoặc policy attachment.

Ở môi trường mới, một số traffic đi qua **L4 ztunnel**, nhưng HTTP L7 policy chưa được gắn vào một **waypoint** phù hợp với request path. Tùy phiên bản và policy semantics, phương thức/path có thể **không được enforce ở nơi team kỳ vọng** hoặc cấu hình có thể bị từ chối/không áp theo scope. Đó là một **khoảng trống cần xác minh**, không nên khẳng định mọi ambient mesh đều bypass L7.

~~~mermaid
flowchart LR
    FE["Frontend workload"] --> Z1["Ambient L4 dataplane"]
    Z1 --> Z2["Destination L4 dataplane"]
    Z2 --> APP["Orders app"]
    WP["Waypoint L7 / nếu được gắn đúng"] -. "Có thể enforce HTTP method/path" .-> Z2
    RULE["HTTP AuthorizationPolicy"] -. "Phải target đúng L7 enforcement point" .-> WP
~~~

### 22.2. Dấu hiệu có thể gặp

- HTTP `GET` từ frontend hoạt động, nhưng không có bằng chứng rằng `POST` bị chặn bởi **L7 PEP**.
- Istio resources tồn tại trong API nhưng không có hiệu lực tại endpoint mà kiểm thử đang dùng.
- Không tìm thấy sidecar Envoy của Orders vì workload đã dùng ambient, trong khi script kiểm thử chỉ chạy `istioctl proxy-config` trên application Pod.
- Một test trực tiếp qua Pod IP hoặc `ClusterIP` có routing path khác test qua waypoint-bound Service.
- L4 identity checks hoạt động, nhưng method/path rules chưa được chứng minh.

### 22.3. Quy trình sửa

1. Lập inventory Pods/Services nào đã vào **ambient**, namespace labels và đường được capture.
2. Đọc **Istio version/feature support**, waypoint deployment/enrollment và cách gắn chính sách (`targetRefs` hoặc cơ chế được hỗ trợ).
3. Xác định L4 policy tại ztunnel và L7 policy tại waypoint **khác nhau ở phạm vi nào**.
4. Kiểm tra mọi đường truy cập: từ frontend, Pod không được duyệt, Service DNS và direct Pod IP khi được phép.
5. Nếu thiếu L7 PEP, triển khai waypoint/policy attachment phù hợp qua **change control**, không coi rule YAML đã đủ.
6. Chạy positive/negative: GET từ principal đúng ALLOW; POST/sai path hoặc source sai DENY.
7. Quan sát logs từ đúng ztunnel/waypoint và ứng dụng để biết **PEP nào đã quyết định**.
8. Giữ NetworkPolicy/host firewall và application authorization như các lớp bắt buộc.

### 22.4. Kết quả mong muốn

~~~text
Topology: ambient mesh in authorized lab

Expected:
  frontend-sa GET /v1/orders/test-only    : ALLOW by intended L7 policy
  frontend-sa POST /v1/orders/test-only   : DENY by intended L7 policy
  unapproved-sa GET /v1/orders/test-only  : DENY by identity policy
  unmeshed plaintext caller              : DENY by boundary controls
  bypass gateway / direct path           : No unauthorized access
  policy owner, waypoint, target, version : Verified

Status: PENDING independent validation
~~~

### 22.5. Bài học rút ra

**Policy YAML không phải enforcement point.** Khi thay data plane mode, phải kiểm tra **traffic có đi qua đúng PEP, PEP hỗ trợ những thuộc tính nào và policy attachment có đúng không**. Đánh giá chỉ bằng “Istio resource tồn tại” hoặc “GET hoạt động” là chưa đủ.

## 23. Troubleshooting: vì sao request bị chặn hoặc được phép sai?

### 23.1. Triệu chứng, giả thuyết và bằng chứng

| Triệu chứng | Nguyên nhân có thể | Quan sát trước khi thay đổi |
|---|---|---|
| HTTP 403 từ gateway | JWT/auth service từ chối, mesh DENY/ALLOW, hoặc app 403 | Status origin, Envoy logs, app logs, auth provider |
| HTTP 503 sau khi bật STRICT | Caller chưa mTLS, cert trust mismatch, no healthy upstream | TLS handshake, proxy peer identity, endpoints |
| Source principal trống | Plaintext/PERMISSIVE, unmeshed caller hoặc data plane không thấy identity | PeerAuthentication, TLS mode, PEP logs |
| `frontend-sa` không được ALLOW | Principal string/trust domain sai, wrong SA hoặc wrong port | Pod SA, cert identity, source principal, destination listener |
| Không có ALLOW policy vẫn gọi được | Istio không có default deny áp dụng hoặc request bypass PEP | All applicable policies, dataplane enrollment, network path |
| Có default-deny nhưng caller vẫn được phép | Một ALLOW policy khác match, root/target policy, bypass | Full policy inventory và proxy config |
| DENY chặn mọi request TCP | DENY dùng HTTP attributes thiếu trên TCP hoặc scope quá rộng | Protocol classification, `ports`, rule match |
| GET bị chặn dù URI đúng | Path normalization, route rewrite, port/protocol mismatch | Proxy HTTP path, method, actual workload port |
| POST được phép dù chỉ định GET | L7 policy không enforce, ALLOW rộng khác hoặc path khác | Effective L7 PEP, applicable policies và request logs |
| `RequestAuthentication` có nhưng JWT thiếu vẫn được phép | JWT validation không đồng nghĩa JWT requirement | ALLOW rule có `requestPrincipals`, toàn bộ policy set |
| JWT hợp lệ nhưng access sai tenant | Token authn thành công, app-level authz thiếu | Token claims đã xác minh, resource ownership |
| Source IP không như mong đợi | NAT, ingress gateway, CNI/mesh proxy, LB | Socket peer, verified client IP, traffic path |
| ServiceAccount giống nhau giữa hai deployments | Identity không đủ phân biệt workloads | Pod specs, mesh principals, SA ownership |
| Sidecar không thấy policy mới | Control plane config không sync, selector/namespace sai | Istio status, labels, effective config |
| Ambient ztunnel không chặn path | L4 PEP không hiểu HTTP path; waypoint/target policy thiếu | Ambient enrollment, waypoint, targetRefs, test L7 |
| Cross-cluster caller bị từ chối | Trust domain, CA bundle, identity mapping khác | Peer certificate chain, gateway identity, policy principals |
| Cùng principal từ DR có quyền quá rộng | Trust aliases/federation hoặc wildcard policy quá rộng | Trust config, identities và rule scope |
| Provider external authz timeout | Provider unavailable, TLS, timeout/circuit settings | Provider health, proxy logs, fail behavior |
| CNI deny nhưng mesh logs không có | Packet bị chặn **trước khi tới** mesh PEP | CNI flow logs, policy source/destination |
| Network flow OK nhưng API trả 401/403 | Lỗi authn/authz trong ứng dụng hoặc token | Backend application logs và user permission |
| Egress vẫn tới Internet ngoài gateway | Direct route/interception bypass, network egress mở | Cloud route/NAT, CNI policy, node path |
| Tạo Pod mới vẫn có quyền cũ | Pod dùng service account chung hoặc policy label rộng | Pod SA, policies, admission rules |
| Một vài replicas có behavior khác nhau | Proxy config stale, rollout mixed versions | Per-Pod proxy sync, labels, policy revisions |
| Không có audit logs dù AUDIT policy tồn tại | Telemetry/audit sink chưa bật, policy không match | Audit configuration và observed events |
| Sau rollback vẫn lỗi | Mesh config caching, root policy, DNS/endpoint hoặc application state | Actual effective config, propagation, service readiness |

### 23.2. Mười bước chẩn đoán theo lớp

1. **Định danh request:** timestamp UTC, source Pod UID/ServiceAccount, destination, port, method/path, request ID.
2. **Kiểm tra network:** DNS, Service/EndpointSlice, route, CNI NetworkPolicy và firewall; phân biệt TCP connect failure với HTTP response.
3. **Xác minh mTLS:** peer certificate, trust domain, trust CA, STRICT/PERMISSIVE và handshake result tại destination.
4. **Xác định PEP:** sidecar, ztunnel, waypoint, ingress gateway hay application; request có đi qua đúng điểm?
5. **Xem toàn bộ policy:** namespace/root policies, selector/targetRefs, ALLOW/DENY/CUSTOM/AUDIT, config phiên bản.
6. **Đối chiếu attributes thực:** principal, destination port, HTTP method, normalized path, JWT principal/claims.
7. **Kiểm tra external authz:** nếu dùng, provider availability, timeout, identity chain và fail mode.
8. **Đối chiếu application:** user/resource permission, app 401/403, DB authorization, business validation.
9. **Chạy controlled tests:** positive từ caller được duyệt và negative từ caller không được duyệt, đúng route và port.
10. **Khắc phục và xác minh hậu kiểm:** policy diff, rollout/canary, deny log, SLO, revert option, audit.

### 23.3. Giải nghĩa các tín hiệu thường gặp

**TCP timeout** có thể do route, firewall, CNI, service down, MTU hoặc traffic blackhole; không tự chứng minh mesh DENY. **TLS handshake failure** thường khác một **HTTP 403** do authorization proxy trả. **HTTP 401** có thể là ứng dụng yêu cầu credentials; **HTTP 403** có thể do proxy, external auth hoặc ứng dụng; **HTTP 503** có thể do upstream unreachable, TLS mismatch hoặc no endpoints.

Kết luận phải xác định **lớp đã ra quyết định**, chính sách và identity được sử dụng. Đừng “sửa” bằng cách tắt STRICT, bỏ certificate verification hoặc thêm `ALLOW rules: - {}` trước khi biết nguyên nhân.

### 23.4. Tại sao positive control rất quan trọng?

Giả sử test từ `unapproved-sa` tới Billing thất bại. Nếu Billing Pod đang CrashLoopBackOff hoặc port sai, chính sách mesh có thể vẫn **không có hiệu lực**. Muốn kết luận authorization đang bảo vệ, cần chứng minh **caller hợp lệ** tới cùng endpoint thành công, đồng thời caller không hợp lệ bị chặn ở **đúng PEP** chứ không phải bởi hạ tầng tình cờ lỗi.

## 24. Runbook thiết kế và triển khai service-to-service authorization

### Bước 1 — Inventory luồng và phạm vi ảnh hưởng

Lập danh sách services theo **namespace, owner, Kubernetes ServiceAccount, mesh identity, port, protocol, dependencies và data sensitivity**. Phân tách:

~~~text
Source identity  -> Destination     Action                 Purpose
frontend-sa      -> orders          GET /v1/orders/*       Đọc đơn hàng của user
orders-sa        -> billing         POST /v1/charge        Yêu cầu thanh toán
orders-sa        -> db              TCP/5432               Truy cập data với DB auth
reporting-sa     -> billing         DENY                   Không có nhu cầu
unapproved-sa    -> orders          DENY                   Không có quyền
~~~

Với mọi source/destination, xác định **đường mạng thật và PEP**, không lấy biểu đồ tài liệu cũ làm bằng chứng. Kiểm kê service account dùng chung, legacy VMs, non-mesh Pods và cross-cluster gateways.

### Bước 2 — Chuẩn hóa identity và trust

Kiểm tra:

- CA/trust bundles, SPIFFE/trust domain, service account identities.
- Workload có được mTLS enrollment/cert rotation như kỳ vọng?
- Pod/team nào có quyền dùng một ServiceAccount đặc quyền?
- Gateway nào terminate/re-originate mTLS, destination thấy principal nào?
- Cross-cluster federation/trust aliases có tăng phạm vi danh tính được tin không?
- External clients có JWT/session và tầng nào xác minh chúng?

**Không triển khai least-privilege policy dựa identity khi chưa chứng minh identity được cấp đúng và không bị chia sẻ ngoài ý định.**

### Bước 3 — Vẽ trust boundaries và viết policy-as-intent

~~~yaml
# Biểu diễn ý định để review; KHÔNG phải Kubernetes/Istio CRD triển khai được.
environment: shop-lab
service: billing
destination_workload: app=billing
workload_port: 9090
default: deny_unlisted_sources_and_actions
trusted_callers:
  - principal: cluster.local/ns/shop-lab/sa/orders-sa
    actions:
      - POST /v1/charge
unauthorized_callers:
  - cluster.local/ns/shop-lab/sa/frontend-sa
  - cluster.local/ns/shop-lab/sa/reporting-sa
business_authorization:
  - validate_order_and_tenant
  - validate_amount_and_idempotency
required_controls:
  - destination_mtls_identity
  - matching_l7_policy_at_actual_pep
  - cni_network_segmentation
  - application_authentication_and_authorization
  - audit_and_regression_tests
~~~

Đảm bảo policy có owner, lý do nghiệp vụ, source principal, destination, port, HTTP method/path khi được hỗ trợ và exception/expiry date nếu cần. Policy “allow all namespace” thường quá rộng cho các dịch vụ nhạy cảm.

### Bước 4 — Chọn PEP và mô hình thực thi phù hợp

- **Sidecar:** xác định destination sidecar/ingress gateway và policies áp dụng.
- **Ambient:** phân biệt **L4 ztunnel** và **L7 waypoint**; kiểm tra enrollment, policy attachment/targetRefs và supported features.
- **TCP:** dùng principal/port policy phù hợp; không đòi HTTP method/path nếu không có L7 parser.
- **External services:** xác định egress gateway, network firewall, private endpoints và application auth.
- **Legacy/unmeshed:** có migration strategy hoặc network/application controls bổ sung để không tạo bypass.

### Bước 5 — Thiết kế policy ít quyền nhất

1. Xác định baseline **default-deny** ở phạm vi phù hợp, lưu ý ALLOW policies **cộng dồn**.
2. Thêm ALLOW cho **đúng principal, destination, port/action**, không dùng wildcard nếu không cần.
3. Dùng DENY cho những cấm quan trọng đã được review, **giới hạn port** nhất là khi match HTTP properties trên TCP hỗn hợp.
4. Nếu cần JWT, cấu hình RequestAuthentication **và** AuthorizationPolicy yêu cầu request principal/claims phù hợp.
5. Nếu cần business policy động, dùng application/external authz với **fail behavior** rõ và HA.
6. Audit root namespace/targetRefs và các rules đã tồn tại để không có một ALLOW khác mở rộng quyền.

### Bước 6 — Staging và canary trước STRICT/default deny

Chọn một destination thử nghiệm hoặc namespace lab. Thu baseline traffic cùng provenance; xác minh cert/mTLS, service accounts, CNI support và dependency. Khi áp dụng policy:

- Positive tests: dịch vụ thật được phép gọi đúng endpoint.
- Negative tests: wrong principal, wrong method, wrong path, missing token, direct path.
- Non-HTTP: TCP destinations không bị DENY rộng ngoài ý định.
- Availability: probes, DNS, ingress, identity provider và external auth service hoạt động.
- Rollback: sẵn manifests/revision cũ, owner phụ trách, phương pháp revert có quyền.

### Bước 7 — Production rollout theo change control

~~~mermaid
flowchart TD
    I["Inventory flows, identities, PEPs"] --> P["Least-privilege policy design"]
    P --> S["Security review + static checks"]
    S --> L["Lab allow/deny + positive control"]
    L --> G{"Security và app SLO đạt?"}
    G -- "Không" --> F["Sửa policy/scope/identity"]
    F --> L
    G -- "Có" --> C["Canary destination / namespace"]
    C --> O["Monitor mTLS, authz, CNI, app"]
    O --> R{"Regression hoặc bypass?"}
    R -- "Có" --> B["Controlled rollback"]
    B --> F
    R -- "Không" --> M["Wider rollout + periodic audit"]
~~~

Khi thực hiện thay đổi, log **timestamp UTC, ticket ID, policy diff, source/destination identities, affected versions, expected denied flows, exceptions và rollback instructions**. Không dùng default-allow fail-open như một rollback “an toàn” nếu nó mở quyền rộng; rollback phải được thiết kế để cân bằng availability và bảo mật.

### Bước 8 — Hậu kiểm và kiểm soát drift

Theo dõi các tín hiệu:

- Thêm service accounts dùng chung hoặc Pod mới có principal đặc quyền.
- Thay đổi ALLOW/DENY/CUSTOM/AUDIT policies, root namespace/global trust.
- Source principals không rõ hoặc tăng request không có mTLS identity.
- Deny rates theo service, HTTP method/path và loại policy/PEP.
- Lỗi JWT issuer/JWKS, external auth provider latency, certificate rotation.
- Sidecar/ztunnel/waypoint policy sync và version mismatch.
- Route/NetworkPolicy mới tạo đường bypass.
- Multi-cluster changes làm thay trust domain hoặc nguồn request thực.
- Lưu lượng tới admin endpoints, database ports hoặc egress không nằm trong allowlist.

**Periodic review** nên kiểm tra quyền **đã trở nên không cần thiết** chứ không chỉ phát hiện các service mới cần thêm ALLOW. Thu hồi quyền thừa và chứng minh không gây regression.

## 25. Bài tập vận dụng

### Bài 1 — mTLS và authorization

Hai workload đều có chứng thư mTLS hợp lệ từ cùng mesh CA. Có thể kết luận workload A được phép gọi mọi endpoint của workload B không?

*Đáp án gợi ý:* không. mTLS xác thực peer identity và bảo vệ kênh; AuthorizationPolicy/application authorization quyết định những endpoint/action nào được phép.

### Bài 2 — Xác định subject

Orders và Reporting cùng dùng ServiceAccount `shared-business-sa`. Policy chỉ ALLOW principal của account này. Những deployment nào có thể match?

*Gợi ý:* cả hai có thể có cùng mesh principal; không thể phân biệt deployment theo tên nếu policy chỉ xét service account. Cấp account riêng và bảo vệ quyền deploy với account đó.

### Bài 3 — Không có ALLOW policies

Một workload không có AuthorizationPolicy ALLOW áp dụng, cũng không có DENY/CUSTOM chặn. Nó có tự bị từ chối ở tầng mesh authorization không?

*Đáp án gợi ý:* theo semantics Istio thông thường, **không có ALLOW policy áp dụng** thì lớp ALLOW không tạo default deny. Các lớp mTLS, network firewall và ứng dụng có thể vẫn chặn.

### Bài 4 — Default deny và ALLOW khác

Namespace có một `AuthorizationPolicy` `spec: {}` và một ALLOW policy khác cho `frontend-sa` gọi Orders GET. ALLOW policy thứ hai có thể cho request qua không?

*Đáp án gợi ý:* có thể, nếu nó áp dụng và match, vì các ALLOW policies cộng dồn. Empty ALLOW policy không phải một DENY phủ quyết.

### Bài 5 — DENY priority

Một ALLOW rule cho `frontend-sa` vào mọi port nhưng một DENY rule từ chối port 9000. Request từ frontend tới port 9000 có được phép không?

*Đáp án gợi ý:* không, nếu DENY match ở đúng PEP. DENY có quyền phủ quyết một ALLOW phù hợp trong mô hình Istio.

### Bài 6 — DENY theo HTTP attributes

Một DENY policy dùng `methods: POST` mà không giới hạn port, trên workload có cả HTTP/8080 và TCP/5432. Cần đánh giá rủi ro nào?

*Gợi ý:* HTTP attribute có thể không tồn tại ở TCP; DENY trên thuộc tính thiếu có thể match rộng theo Istio semantics. Nên chỉ rõ port và kiểm thử TCP/hành vi thực tế.

### Bài 7 — Principal và `spiffe://`

Một workload có SPIFFE URI `spiffe://cluster.local/ns/shop-lab/sa/frontend-sa`. Có thể copy nguyên chuỗi URI đó vào mọi mesh policy engine không?

*Đáp án gợi ý:* không. Trong Istio `source.principals` thường dùng dạng `cluster.local/ns/shop-lab/sa/frontend-sa` không có `spiffe://`; các sản phẩm khác có schema riêng. Phải kiểm tra API thực.

### Bài 8 — STRICT chưa đủ

Billing bật mTLS `STRICT` nhưng chưa có ALLOW/other authz restriction. Một workload không có quyền nghiệp vụ nhưng có cert mesh hợp lệ có thể gửi request không?

*Gợi ý:* nó có thể vượt qua bước mTLS authentication; cần thêm destination authorization và app-level permission checks.

### Bài 9 — PERMISSIVE và nguồn identity

Orders dùng PeerAuthentication `PERMISSIVE`, một caller không có mTLS gửi plaintext qua đường được phép. Source principal có chắc tồn tại không?

*Đáp án gợi ý:* không. Không nên tạo quyền đặc biệt từ principal không được chứng minh; cần bảo vệ đường bypass/siết mTLS theo rollout phù hợp.

### Bài 10 — JWT không bắt buộc

Một workload có `RequestAuthentication` xác minh JWT hợp lệ nhưng không có ALLOW rule yêu cầu `requestPrincipals`. Request thiếu JWT có tự bị từ chối không?

*Đáp án gợi ý:* không tự động. `RequestAuthentication` không có nghĩa mọi request đều phải mang JWT; cần AuthorizationPolicy/app policy buộc authentication cho route được bảo vệ.

### Bài 11 — End-user và ingress principal

Ingress gateway dùng mTLS identity `ingress-gateway-sa` để gọi Orders cho nhiều người dùng. Orders có thể suy user ID từ gateway principal không?

*Đáp án gợi ý:* không. Gateway workload principal khác end-user identity. Cần JWT/session đã xác minh và per-record authorization.

### Bài 12 — Bypass bằng Pod IP

API chỉ kiểm tra header `X-Authenticated-User` mà ingress chèn. Một Pod nội bộ có thể gọi trực tiếp ClusterIP của API và tự gửi header này. Nên sửa gì?

*Gợi ý:* API không tin header chưa có trusted-origin proof; dùng destination mTLS policy và NetworkPolicy để hạn chế direct call, đồng thời application verify token/auth context hoặc xác minh nguồn gateway không thể bypass.

### Bài 13 — CNI versus mesh

NetworkPolicy từ chối Pod A→Pod B trước khi request tới sidecar. Có thể đánh dấu một Istio DENY rule đang hoạt động chỉ từ kết quả timeout không?

*Đáp án:* không. Packet có thể bị chặn ở CNI. Cần positive control và log từ đúng PEP để xác nhận mesh authorization.

### Bài 14 — Ambient L7

Một team dùng ambient ztunnel L4 nhưng muốn giới hạn `GET /v1/orders/*`. Cần kiểm tra điểm thực thi nào?

*Gợi ý:* L7 waypoint và cách policy được attach/target theo Istio version; ztunnel L4 không tự có full HTTP method/path enforcement.

### Bài 15 — External authorization

External auth provider không phản hồi trong lúc xử lý API nhạy cảm. Đội vận hành có thể tự chuyển sang allow-all để giữ uptime không?

*Đáp án:* không làm thay đổi mở quyền ngoài phê duyệt. Cần fail-mode đã xác định, HA, timeout policy, alert và rollback an toàn theo yêu cầu nghiệp vụ.

### Bài 16 — Cross-cluster

Orders ở Cluster A gọi Billing ở Cluster B. Billing thấy principal của east-west gateway, khác Orders. Có thể dùng nguyên policy principal cũ mà không đổi?

*Gợi ý:* chỉ khi thiết kế chứng minh destination nhìn đúng original workload identity. Nếu gateway re-originates TLS, cần xác định peer identity mới và mô hình ủy quyền phù hợp, không suy theo tên source Pod.

### Bài 17 — TLS và DB authorization

Orders có mTLS identity hợp lệ và có quyền mở TCP/5432 đến database. Nó có tự có quyền `DROP TABLE` không?

*Đáp án:* không. Database authentication/SQL authorization vẫn là một lớp riêng, kết hợp network segmentation và mTLS.

### Bài 18 — Gỡ quyền không còn cần thiết

Một ALLOW rule cho Reporting gọi Billing đã không còn nhu cầu. Vì sao nên gỡ dù chưa thấy abuse?

*Gợi ý:* giảm blast radius, tránh dùng quyền có sẵn khi Reporting bị xâm nhập, giữ chính sách phù hợp least privilege và giảm rủi ro compliance.

### Bài 19 — Thiết kế tổng hợp

Thiết kế chính sách cho `frontend`, `orders`, `billing`, `reporting`, trong đó chỉ `frontend` đọc Orders; chỉ Orders gọi charge; Reporting không gọi Billing; Internet client bắt buộc qua ingress; API cần JWT của user để đọc đơn hàng. Nêu **ba luồng ALLOW, bốn luồng DENY**, nơi thực thi, cách giữ ServiceAccount riêng và cách test.

*Gợi ý:* ALLOW frontend→Orders GET; Orders→Billing POST charge; ingress→public API theo principal được duyệt; cần thêm ALLOW DNS/identity dependencies theo architecture. DENY Reporting→Billing, unapproved-sa→Orders, frontend→Billing, unauthenticated user→order. Xác định JWT validation + request principal, mesh/cross-hop identity, CNI default deny, ingress network exposure và negative tests có positive controls. Tại API phải có kiểm tra user sở hữu order.

## 26. Checklist thiết kế authorization giữa các service

### 26.1. Danh tính và tín nhiệm

- [ ] Mỗi workload nhạy cảm có **dedicated ServiceAccount/mesh identity**, không dùng `default` hoặc account chung ngoài chủ đích.
- [ ] SPIFFE/trust domain, CA, certificate rotation, peer identity được **xác minh tại destination**.
- [ ] Phân biệt **workload mTLS identity** với **end-user JWT/session identity**; không chuyển hóa bằng header tự khai.
- [ ] Quyền tạo Pod với ServiceAccount đặc quyền được kiểm soát bằng **RBAC và admission**.
- [ ] Multi-cluster federation/trust aliases được review, không làm mọi service ở trust domain mới thành caller được phép.
- [ ] Có inventory callers chưa mesh và lộ trình xử lý thay vì bật `PERMISSIVE` vô thời hạn.

### 26.2. Quyết định chính sách

- [ ] Có ma trận **subject–action–resource–context** theo nhu cầu nghiệp vụ, owner và data sensitivity.
- [ ] Mỗi protected destination có **ALLOW policy tối thiểu** hoặc baseline deny rõ trong phạm vi đã xác minh.
- [ ] Các ALLOW rules không cho quyền rộng theo namespace/wildcard khi service account cụ thể đủ dùng.
- [ ] DENY rules được review để tránh ảnh hưởng TCP khi dùng HTTP attributes thiếu, có **port scoping**.
- [ ] Thử tương tác **CUSTOM, DENY, ALLOW, AUDIT** và không suy từ tên YAML.
- [ ] `spec: {}` và `rules: - {}` được phân biệt rõ trong code review.
- [ ] Policy scope gồm **namespace, root namespace, selector, targetRefs**, tất cả applicable policies và effective dataplane config.
- [ ] Port trong rule là **workload destination port**, không nhầm với LB/Ingress/Service port.
- [ ] HTTP method/path, gRPC route, URL normalization và version proxy được xác minh.
- [ ] JWT authentication được bổ sung **explicit token requirement** khi cần; issuer, audience, claims đều được kiểm soát.
- [ ] Application vẫn kiểm tra **per-user, per-tenant, per-resource authorization** và business rules.

### 26.3. Enforcement và chống bypass

- [ ] Biết mọi luồng đi qua **sidecar, ztunnel, waypoint, ingress/egress gateway** hoặc application PEP nào.
- [ ] Với ambient, L7 policy được gắn vào **đúng waypoint/đối tượng được hỗ trợ**, không mặc định ztunnel hiểu HTTP path.
- [ ] PeerAuthentication STRICT/PERMISSIVE tương thích callers và đã có test plaintext/mTLS.
- [ ] Non-mesh, hostNetwork, excluded ports, direct Pod IP/ClusterIP và NodePort được kiểm tra chống bypass.
- [ ] CNI NetworkPolicy/cloud firewall giới hạn east–west, egress và direct access ngoài ý định.
- [ ] Egress gateway/ServiceEntry không bị coi là firewall mặc định; đã thử direct Internet path từ workload.
- [ ] External auth service có TLS/identity, timeout/HA và **fail behavior** được phê duyệt.
- [ ] Gateway mTLS identity không được nhầm với original caller hoặc user identity.

### 26.4. Vận hành, giám sát và hồi quy

- [ ] Có **positive tests** chứng minh services được phép vẫn hoạt động và dependencies khỏe.
- [ ] Có **negative tests** cho sai principal, sai method/path, sai port, thiếu JWT, non-mesh và bypass.
- [ ] Có test HTTP và TCP riêng, IPv4/IPv6 khi sử dụng, cross-node và cross-cluster/DR khi có.
- [ ] Kết quả DENY được gắn với **đúng PEP**, không nhầm timeout hoặc app 403 thành mesh policy PASS.
- [ ] Logs giữ timestamp UTC, workload principal, destination, action, policy revision và trace ID; không ghi secrets.
- [ ] Proxy/control-plane config sync, certificate expiry, external auth latency, deny spikes được giám sát.
- [ ] CI/GitOps và app teams có least-privilege quyền tạo/sửa mesh policies, PeerAuthentication và trust config.
- [ ] Rollout có canary, config diff, approver, rollback và bảo đảm không vô tình fail-open.
- [ ] Mỗi thay đổi service account, mesh mode, ingress/gateway, policy API hoặc topology đều kích hoạt regression tests.
- [ ] Có periodic review để **thu hồi quyền đã hết nhu cầu** và cập nhật threat model.

**Kết luận:** bảo vệ giao tiếp giữa các service không chỉ là “bật mTLS”. Trước tiên cần **cấp đúng workload identity và xác thực peer**, sau đó **cho phép đúng chủ thể, đúng hành động, đúng dịch vụ**, tại **điểm thực thi thật trên đường mạng**. Cuối cùng phải kết hợp NetworkPolicy, gateway controls và phân quyền trong ứng dụng để ngăn đường bypass. **Bằng chứng quan trọng nhất** là những phép thử xác nhận cả hai mặt: dịch vụ hợp lệ vẫn hoạt động, còn caller không có quyền **bị từ chối bởi đúng chính sách ở đúng lớp**.

### Tài liệu tham khảo

- [Istio — Security concepts](https://istio.io/latest/docs/concepts/security/): workload identity, authentication và authorization trong mesh.
- [Istio — AuthorizationPolicy reference](https://istio.io/latest/docs/reference/config/security/authorization-policy/): `ALLOW`, `DENY`, `CUSTOM`, `AUDIT`, policy match và semantics.
- [Istio — PeerAuthentication reference](https://istio.io/latest/docs/reference/config/security/peer_authentication/): mTLS modes và phạm vi áp dụng.
- [Istio — RequestAuthentication reference](https://istio.io/latest/docs/reference/config/security/request_authentication/): JWT validation và request identity.
- [Istio — HTTP traffic authorization](https://istio.io/latest/docs/tasks/security/authorization/authz-http/): ví dụ và kiểm thử policy theo HTTP.
- [Istio — Ambient mesh architecture](https://istio.io/latest/docs/ambient/architecture/): ztunnel, waypoint và mô hình dataplane.
- [Istio — Ambient L4 policy](https://istio.io/latest/docs/ambient/usage/l4-policy/): khả năng kiểm soát L4 theo ambient.
- [Istio — Ambient L7 features](https://istio.io/latest/docs/ambient/usage/l7-features/): waypoint và các yêu cầu L7.
- [SPIFFE — Overview](https://spiffe.io/docs/latest/spiffe-about/overview/): workload identities và SPIFFE IDs.
- [SPIRE — Overview](https://spiffe.io/docs/latest/spire-about/overview/): cách triển khai issuing/attestation cho SPIFFE.
- [Kubernetes — Service Accounts](https://kubernetes.io/docs/concepts/security/service-accounts/): danh tính và quyền của service accounts.
- [Kubernetes — Network Policies](https://kubernetes.io/docs/concepts/services-networking/network-policies/): cô lập mạng giữa Pods theo L3/L4.
- [Kubernetes — RBAC authorization](https://kubernetes.io/docs/reference/access-authn-authz/rbac/): quyền sửa tài nguyên và policies.
- [RFC 8446 — TLS 1.3](https://www.rfc-editor.org/rfc/rfc8446): handshake và xác thực kết nối.
- [RFC 7519 — JSON Web Token](https://www.rfc-editor.org/rfc/rfc7519): cấu trúc JWT và claims.
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): các biện pháp tránh lạm dụng JWT.
- [NIST SP 800-207 — Zero Trust Architecture](https://csrc.nist.gov/pubs/sp/800/207/final): xác thực, authorization và least privilege.
- [OWASP — Kubernetes Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Kubernetes_Security_Cheat_Sheet.html): Kubernetes platform policy và workload hardening.








