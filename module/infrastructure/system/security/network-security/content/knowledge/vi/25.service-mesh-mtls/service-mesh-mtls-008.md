# Egress gateway và outbound boundary: kiểm soát lưu lượng ra khỏi service mesh bằng mTLS và chính sách mạng

Trong chương **Service mesh và mTLS** của module **SECURITY_NETWORK_SECURITY**, **egress gateway** là một điểm chuyển tiếp được thiết kế để tập trung và quan sát những kết nối từ workload trong mesh đi tới hệ thống **bên ngoài miền quản lý của mesh**. Đích có thể là API đối tác trên Internet, hệ thống thanh toán, dịch vụ SaaS, database ngoài cluster, on-premises qua VPN hoặc một hệ thống nội bộ thuộc trust domain khác.

Mục tiêu quan trọng không chỉ là “cho ứng dụng ra Internet”: kiến trúc cần xác định **ai được phép gửi, gửi tới đâu, dùng giao thức và danh tính nào, đường đi có bắt buộc qua gateway hay không, gateway và đích cuối xác thực ra sao, logs có chứng minh policy thực thi không**. Một proxy egress được triển khai nhưng workload vẫn có đường ra ngoài trực tiếp sẽ **không tự tạo thành security boundary**. Tương tự, mTLS giữa sidecar và gateway không chứng minh rằng kết nối từ gateway tới dịch vụ ngoài đã mã hóa hoặc xác minh danh tính đích đúng cách.

Nội dung bài tập trung vào kiến trúc **service mesh trên Kubernetes**, dùng các thuật ngữ quen thuộc trong **Istio/Envoy** làm ví dụ và nêu rõ những điểm phụ thuộc **sidecar, ambient, Gateway API, CNI và phiên bản**. Các mô hình trong Linkerd hoặc mesh khác không nhất thiết hỗ trợ cùng các tài nguyên cấu hình hay gateway semantics; vì vậy **không áp trực tiếp ví dụ Istio cho mọi service mesh**.

Sau bài học, bạn có thể:

- Phân biệt **outbound boundary, egress gateway, ingress gateway, Internet gateway, NAT gateway, firewall, forward proxy và API gateway**.
- Vẽ đường **workload → sidecar/ztunnel/waypoint → egress gateway → external service**, phân biệt đường logic với thực tế data plane.
- Phân biệt **mTLS nội bộ mesh, TLS passthrough, TLS origination, end-to-end TLS và HTTPS proxying**; xác định nơi nào biết nội dung HTTP.
- Hiểu vai trò của **ServiceEntry, VirtualService, DestinationRule, Gateway, AuthorizationPolicy, PeerAuthentication và outboundTrafficPolicy** trong Istio với các caveat về phiên bản.
- Giải thích vì sao **REGISTRY_ONLY, DNS/SNI allowlist hoặc route tới gateway không đủ ngăn direct egress bypass**.
- Thiết kế kiểm soát nhiều lớp bằng **Kubernetes NetworkPolicy/CNI, host/cloud firewall, IAM, NAT, DNS policy, workload identity, mTLS và egress gateway authorization**.
- Điều tra **TLS errors, DNS drift, gateway 503/504, upstream retries, policy rejects, SNAT source IP thay đổi, sidecar injection missing, gateway failover**.
- Xây dựng **positive/negative/bypass tests**, khả năng phục hồi, quan sát và playbook thay đổi/ứng phó an toàn.

## 1. Egress gateway là gì và outbound boundary nằm ở đâu?

### 1.1. Egress khác ingress

**Ingress** thường đưa request từ bên ngoài tới một dịch vụ trong cluster/mesh. **Egress** đưa request do workload bên trong khởi tạo ra một network hoặc trust domain khác.

~~~mermaid
flowchart LR
    U["Người dùng bên ngoài"] --> I["Ingress gateway"]
    I --> A["Service A trong mesh"]
    A --> B["Service B trong mesh"]
    B --> E["Egress gateway"]
    E --> X["API đối tác / SaaS / on-prem"]
    A -. "Telemetry và identity" .-> O["SOC / SRE"]
    E -. "Egress policy và logs" .-> O
~~~

Đây là **sơ đồ luồng dự kiến**, không phải bằng chứng packet đã buộc đi qua gateway. Đường **B → X trực tiếp** cần được chặn tại các lớp có hiệu lực nếu kiến trúc yêu cầu tất cả external traffic phải tập trung.

### 1.2. Những thành phần không đồng nghĩa

| Thành phần | Chức năng chính | Giới hạn cần nhớ |
| --- | --- | --- |
| **Egress gateway của mesh** | Điểm Envoy/proxy chuyển tiếp external traffic theo routing/policy mesh | Không mặc nhiên chặn bypass ở kernel, Pod, node hoặc cloud |
| **Ingress gateway** | Nhận request từ client ngoài vào services bên trong | Không mặc nhiên là điểm kiểm soát outbound của Pods |
| **Internet gateway / route gateway** | Kết nối subnet/VPC ra mạng ngoài theo nhà cung cấp | Không hiểu workload SPIFFE identity hay HTTP method theo mặc định |
| **NAT gateway / SNAT** | Chuyển đổi địa chỉ nguồn cho outbound connections | Không tự xác thực dịch vụ đích, không tương đương firewall |
| **Network firewall / NVA** | L3/L4 hoặc L7 filtering tại điểm routing/enforcement | Chỉ có tác dụng với packet đi qua nó |
| **Forward proxy** | Proxy client sử dụng để truy cập external resources, có thể HTTP CONNECT | Quy tắc authn/authz, TLS và application integration khác mesh egress |
| **API gateway** | Áp chính sách client-to-API, thường ở ranh giới API | Không thay policy routing hoặc Egress NAT của toàn node |
| **DNS resolver / DNS firewall** | Phân giải và kiểm soát tên miền khi traffic dùng resolver đó | Không bảo đảm client không kết nối thẳng IP hoặc dùng DoH |

### 1.3. Outbound boundary là một tập kiểm soát, không phải một Pod

Giả sử doanh nghiệp yêu cầu chỉ workload thuộc namespace **payments** mới được gọi API thanh toán **api.partner.example**. Boundary phải trả lời ít nhất năm câu hỏi:

1. **Identity:** ứng dụng nào/ServiceAccount nào được quyền ra ngoài?
2. **Destination:** tên miền, IP, port, giao thức và cấp độ xác minh endpoint nào được chấp nhận?
3. **Path:** có thật sự bị cưỡng chế đi qua gateway/NAT/firewall được duyệt không?
4. **Data protection:** workload-to-gateway và gateway-to-partner có mã hóa, xác minh danh tính đúng không?
5. **Evidence:** có thể ghép workload identity, policy decision, gateway flow và đối tác nhận request không?

Nếu một trong các lớp thiếu, boundary có thể có điểm yếu dù egress gateway đang chạy khỏe.

## 2. Xác định trust boundary của mesh

Trong một mesh, các workload có thể được cấp **workload identity** và chứng thư ngắn hạn theo một **trust domain**. Tuy nhiên, đối tác bên ngoài mesh thường không có chứng thư do CA của mesh cấp và không hiểu SPIFFE identity của workload nội bộ.

~~~text
Miền tin cậy A: Service mesh nội bộ
  Namespace payments
    invoice-service (identity: cluster.local/ns/payments/sa/invoice)
      -> local data-plane proxy
      -> egress gateway thuộc miền quản lý của mesh

Ranh giới A -> B:
  Egress gateway
      -> External API: api.partner.example:443
         (TLS trust theo CA/certificate policy của external service)

Miền tin cậy B: Dịch vụ đối tác
  Không mặc nhiên chấp nhận SPIFFE identity nội bộ như tài khoản đối tác.
~~~

### 2.1. Trust domain khác network namespace

- **Kubernetes namespace** giúp tổ chức workloads và RBAC/policy scope.
- **Mesh trust domain** xác định phạm vi định danh/PKI cho workload authentication.
- **Network zone/VPC/subnet** xác định đường routing và điểm L3/L4 enforcement.
- **External application identity** có thể dùng OAuth, API key, client certificate do đối tác cấp hoặc cơ chế khác.

Bốn khái niệm không thể hoán đổi. ServiceAccount của Pod là một nguồn tạo workload identity; nó **không tự trở thành tài khoản hợp lệ ở API đối tác**.

### 2.2. Một yêu cầu outbound cần được kiểm soát theo identity và đích

| Hạng mục | Ví dụ | Cần kiểm soát |
| --- | --- | --- |
| **Source workload** | payments/invoice | ServiceAccount, Pod labels, mesh identity, quyền join mesh |
| **Đích logic** | api.partner.example | ServiceEntry/route/allowed destination và TLS identity |
| **Đích mạng thực** | Một hoặc nhiều IP/CDN addresses | DNS answers, routing, firewall/NAT, IPv4/IPv6 |
| **Cổng/giao thức** | TCP 443, HTTPS | Protocol detection, TLS mode, SNI, TCP/HTTP policy |
| **Credential đối tác** | OAuth token hoặc client mTLS certificate | Secret storage, credential audience, rotation, least privilege |
| **Policy outcome** | Allow hoặc deny | Enforced ở điểm nào, theo identity nào và log gì |
| **External operation** | POST /v1/payments | Authorization tại API đối tác, idempotency và request logging |

Chỉ allow **TCP 443** tới Internet là một policy **rất rộng** nếu mục tiêu là “chỉ gọi API đối tác”. Ngược lại, chỉ đặt allowlist FQDN trong một proxy mà Pod có thể bypass proxy cũng chưa đạt yêu cầu.

## 3. Luồng data plane: direct egress so với egress qua gateway

### 3.1. Mô hình không bắt buộc egress gateway

~~~mermaid
flowchart LR
    A["App container"] --> P["Sidecar / proxy"]
    P -->|External route trực tiếp| N["Node / VPC NAT"]
    N --> X["External service"]
    P -. "Mesh observability" .-> O["Monitoring"]
~~~

Mô hình này có thể phù hợp cho workloads ít rủi ro, khi chính sách **network firewall và workload identity** đã đủ. Nhưng nó không tập trung kết nối qua một điểm egress có khả năng dùng **source IP cố định, central certificates hoặc per-partner policies**.

### 3.2. Mô hình egress gateway

~~~mermaid
flowchart LR
    A["App container"] --> S["Workload data-plane proxy"]
    S -->|Inner mesh identity/mTLS| G["Egress gateway"]
    G -->|External TLS/TCP theo policy| F["Cloud firewall / NAT"]
    F --> X["API đối tác"]
    G -. "Gateway logs/metrics" .-> O["SIEM / SRE"]
    F -. "Egress IP/flow logs" .-> O
~~~

Tùy mesh và cấu hình, traffic workload–gateway có thể đi qua **mTLS do mesh quản lý**; lưu lượng gateway–external service có thể là **TLS passthrough, TLS origination hoặc TCP không được mã hóa**. Không suy rằng vì đoạn đầu dùng mTLS thì **toàn tuyến** đã bảo mật.

### 3.3. Những chặng phải kiểm chứng

1. **Ứng dụng khởi tạo request** tới hostname/port.
2. **Outbound traffic capture** chuyển kết nối qua data-plane proxy nếu workload được quản lý và giao thức nằm trong phạm vi intercept.
3. **Service discovery/routing policy** quyết định gửi tới gateway thay vì tới external IP trực tiếp.
4. **Gateway inbound policy** xác thực identity của workload/proxy và chỉ cho nguồn phù hợp.
5. **Gateway outbound route/cluster** chọn external service và thiết lập TLS/transport theo policy.
6. **Node firewall/NAT/VPC route** chuyển packet tới external IP; địa chỉ nguồn có thể bị SNAT.
7. **External service** xác minh credential/application identity và trả response.
8. **Return path** đi qua các stateful devices, timeout và proxy tương ứng.

Một lỗi ở bất kỳ chặng nào đều có thể xuất hiện thành **timeout/503/504/TLS error** ở client. Không vội quy mọi lỗi outbound là “mesh chặn”.

### 3.4. Control plane không tự chở data plane

Trong các kiến trúc như Istio, control plane phân phối cấu hình/identity và Envoy xử lý request. Control plane **không mặc nhiên nằm trên đường truyền dữ liệu mọi request**.

Vì thế, kiểm tra mỗi tài nguyên cấu hình Kubernetes là chưa đủ; phải xem **proxy config thực đang được phân phối**, listener/cluster/routes và **flow/log tại gateway**.

## 4. Các quyết định quan trọng: gateway làm gì và không làm gì?

**Gateway có thể giúp**:

- Tập trung **external destination routes** và nơi lưu **policy evidence**.
- Thực thi gateway-level **client identity authorization** và kiểm soát đối tác được tiếp cận.
- Làm điểm **TLS origination** hoặc xử lý proxy protocols khi được cấu hình.
- Cung cấp **mTLS inbound giữa mesh proxies** và gateway.
- Đưa các kết nối ra ngoài theo **một vùng NAT/firewall/EIP** được thiết kế.
- Đặt **circuit breakers, timeout, retries, connection pools, access logs và metrics**.
- Hỗ trợ **credential/secret custody** tại điểm có quyền được tách khỏi app, trong những mô hình phù hợp.

**Gateway không tự bảo đảm**:

- Mọi Pod đều có sidecar hoặc outbound interception.
- **hostNetwork, privileged workloads, pods ngoài mesh, raw sockets, trực tiếp IP, DNS khác, HTTP CONNECT/DoH** đã bị chặn.
- Firewall node/VPC không cho đi Internet ngoài gateway.
- FQDN trong ServiceEntry luôn tương ứng IP được duyệt và TLS peer đúng danh tính.
- Bản thân gateway không thể bị lạm dụng để gọi những đích khác.
- Nhà cung cấp đối tác nhìn thấy IP cố định chỉ vì có gateway Pod.
- External request không lộ dữ liệu nhạy cảm, không bị retry trùng, không vượt quota API.

**Nguyên tắc:** Egress gateway là **enforcement point có thể kiểm toán**, nhưng để thành **mandatory outbound boundary**, nó cần **một enforcement point độc lập dưới lớp Pod/mesh** cấm đường đi vòng khi yêu cầu bảo mật đủ cao.

## 5. Istio: những tài nguyên và chính sách liên quan

Một kiến trúc Istio sidecar-based có thể sử dụng các tài nguyên sau. Tên, CRD API version, Gateway API support và hành vi chính xác phụ thuộc phiên bản/installation mode.

| Cơ chế | Vai trò chính | Không nên hiểu nhầm |
| --- | --- | --- |
| **ServiceEntry** | Khai báo external service host/ports/resolution trong service registry mesh | Không phải network firewall hoặc chứng minh external identity |
| **VirtualService** | Định tuyến HTTP/TLS/TCP traffic theo match/host/gateway tương ứng | Route cấu hình không tự chặn một Pod bypass proxy |
| **DestinationRule** | Policy cho outbound cluster: mTLS, subsets, connection pools, TLS và resilience | TLS mode cho một hop không bảo vệ mọi hop khác |
| **Gateway** | Cấu hình listener/server tại proxy gateway trên entry/exit được chọn | Gateway resource không tự triển khai Pod/firewall hoặc bật routing cho mọi workload |
| **AuthorizationPolicy** | L7/L4 authorization theo khả năng proxy, identity, action và match conditions | Không thay chặn raw traffic ngoài data-plane proxy |
| **PeerAuthentication** | Đặt mTLS mode giữa workloads/proxies theo phạm vi | STRICT không tự kiểm chứng TLS tới external SaaS |
| **Sidecar resource** | Có thể hạn chế service visibility và proxy config scope | Không tương đương egress firewall |
| **outboundTrafficPolicy** | Cách proxy xử lý external hosts không có trong registry: ALLOW_ANY hoặc REGISTRY_ONLY tùy cấu hình | REGISTRY_ONLY **không phải security firewall** và không ngăn bypass data plane |
| **Kubernetes NetworkPolicy** | Pod network egress/ingress L3/L4 nếu CNI hỗ trợ | Không có FQDN rules chuẩn trong Kubernetes NetworkPolicy cơ bản |
| **Cloud/host firewall** | Egress L3/L4, NAT và routing security tại network boundary | Không hiểu SPIFFE/ServiceAccount identity nếu không có hệ thống bổ sung |

### 5.1. ServiceEntry chỉ đăng ký đích

Ví dụ khai báo external HTTPS service trong Istio:

~~~yaml
# Mẫu Istio API mang tính minh họa; kiểm tra CRD version đang cài.
apiVersion: networking.istio.io/v1
kind: ServiceEntry
metadata:
  name: approved-partner-api
  namespace: payments
spec:
  hosts:
    - api.partner.example
  location: MESH_EXTERNAL
  ports:
    - number: 443
      name: tls-partner
      protocol: TLS
  resolution: DNS
~~~

**api.partner.example** là hostname tài liệu, không phải endpoint thật. Cấu hình này khai báo một hostname/port cho service discovery của mesh. Nó **không** tự:

- Buộc toàn bộ traffic tới hostname đó đi qua egress gateway.
- Chặn các hostname khác ở mạng node/cloud.
- Chứng minh Pod chỉ có thể kết nối tới hostname, không phải tới IP.
- Cấu hình certificate validation của ứng dụng hoặc credential đối tác.
- Tạo Kubernetes NetworkPolicy hay firewall rule.

Để thực thi đường qua gateway cần thêm **định tuyến có hiệu lực**, gateway listeners và những lớp ngăn direct egress.

### 5.2. ALLOW_ANY và REGISTRY_ONLY

Trong Istio, mesh outbound policy có thể có các chế độ như **ALLOW_ANY** và **REGISTRY_ONLY** theo capability/version:

- **ALLOW_ANY:** proxy có thể cho traffic tới destination ngoài registry đi theo cơ chế passthrough/unknown external traffic tương ứng.
- **REGISTRY_ONLY:** proxy có thể từ chối unknown external destinations không có trong mesh service registry.

**Cảnh báo quan trọng:** REGISTRY_ONLY không phải boundary bảo mật hoàn chỉnh. Workload không bị intercept, privileged Pod hoặc network path bên ngoài proxy vẫn có thể đi trực tiếp nếu host/CNI/firewall cho phép. Nó cũng không biến danh sách ServiceEntry thành kiểm tra application identity hoặc chứng minh một domain/IP được tin cậy.

### 5.3. Routing rule và Gateway resource chưa đủ

Để route HTTPS traffic qua egress gateway, cần xét:

1. **Port/protocol detection** tại workload sidecar.
2. **Outbound VirtualService** cho đúng host/port và match HTTP hoặc TLS/SNI.
3. **Egress Gateway resource** cùng selector trỏ đến proxy workload thực; port/listener thích hợp.
4. **DestinationRule** và mesh mTLS tới gateway nếu thiết kế yêu cầu.
5. **Route tiếp theo tại gateway** tới external host/cluster.
6. **Gateway egress permission**, DNS resolution, external TLS semantics và network SNAT/firewall.
7. **Negative bypass tests** sau khi triển khai.

Không copy một manifest egress gateway mẫu của phiên bản khác rồi mặc định mTLS, TLS origination, listener filter chain và routing sẽ tương thích. Đặc biệt, **TLS passthrough** và **gateway TLS termination/ISTIO_MUTUAL** phải được phối hợp đúng ở các hop.

### 5.4. Một policy mô tả đầy đủ hơn một danh sách CRDs

~~~yaml
# PSEUDOCONFIG phục vụ architecture review; KHÔNG phải Istio CRD.
policy_id: MESH-EGRESS-008
source:
  namespace: payments
  service_account: invoice
  workload_identity: cluster.local/ns/payments/sa/invoice
destination:
  hostname: api.partner.example
  port: 443
  protocol: HTTPS
  require_valid_tls_server_identity: true
path:
  local_proxy: required
  approved_egress_gateway: payments-egress
  gateway_mesh_mtls: required
  direct_egress_from_workload: denied_at_network_layer
  external_egress_via_approved_firewall_nat: true
authorization:
  source_identity_allowlist: ["payments/invoice"]
  partner_application_credentials: scoped_and_rotated
observability:
  workload_id: recorded
  gateway_policy_decision: recorded
  destination_and_tls_outcome: recorded
  external_source_ip: verified
~~~

Đây là **đặc tả mục tiêu**; các team cần chuyển từng field thành **Istio/Envoy policies, Kubernetes CNI rules, cloud firewall/NAT, certificate management và logging** tương ứng.

## 6. TLS passthrough, TLS origination và mTLS giữa các hop

Đây là phần thường gây nhầm nhất. Một kết nối outbound có thể chứa nhiều lớp TLS hoặc phân tách trust ở nhiều chặng.

### 6.1. TLS passthrough tới dịch vụ ngoài

~~~text
Application client:
  Bắt đầu HTTPS/TLS hướng tới api.partner.example
         |
         v
Local sidecar:
  Route theo host/SNI/metadata có thể quan sát
         |
         | mTLS mesh-to-egress (nếu được cấu hình)
         v
Egress gateway:
  Forward outer/inner stream đúng route, không giải mã HTTP
         |
         | TLS end-to-end của ứng dụng tiếp tục tới partner
         v
External HTTPS server:
  Kết thúc application TLS session; client kiểm tra certificate
~~~

Trong kiểu **TLS passthrough**, gateway thường có thể nhìn thông tin **transport metadata, địa chỉ, port, SNI khi hiện diện** nhưng không đọc được **HTTP path, headers hoặc body bên trong TLS**. Vì vậy, không thể giả định gateway áp HTTP method/path authorization lên nội dung không được giải mã.

### 6.2. TLS origination tại gateway

~~~text
Application -> Mesh proxy -> Egress gateway -> HTTPS partner

Application/gateway-side protocol:
  Có thể HTTP nội bộ hoặc giao thức do design quy định

Gateway:
  Chủ động thiết lập TLS tới external partner
  Xác minh server cert chain, hostname và trust anchors
~~~

**TLS origination** có thể cho phép gateway chủ động quản lý certificate validation, SNI, client certificate/mTLS to partner hoặc proxy policies. Nhưng nơi kết thúc và phát sinh TLS mới là **điểm được ủy quyền xử lý plaintext** hoặc làm **trust boundary**. Đặc biệt, **không được để đoạn ứng dụng–gateway chạy plaintext qua mạng không đáng tin** chỉ vì đoạn gateway–partner có HTTPS; phải dùng transport bảo vệ như mesh mTLS trong phạm vi phù hợp.

### 6.3. TLS termination + re-encryption

Một số kiến trúc cần gateway **nhìn được HTTP** để kiểm tra method/path/header và áp audit policy. Khi đó gateway có thể terminate một TLS session được cấp quyền, thực thi policy rồi thiết lập TLS khác ra partner.

Ưu điểm là có thể áp **application-layer controls**; đánh đổi:

- Gateway xử lý plaintext và có nguy cơ lộ dữ liệu trong logs/memory.
- Quản trị **certificate/private key** và rotation thêm phức tạp.
- Có thể ảnh hưởng end-to-end authenticity nếu proxy không được client tin đúng cách.
- Protocol nâng cao như HTTP/2/gRPC, WebSocket và request streaming cần kiểm tra tương thích.

Không bật TLS interception chỉ vì muốn đọc URL; cần có **yêu cầu nghiệp vụ, threat model, consent/compliance phù hợp và thiết kế PKI**.

### 6.4. Bảng so sánh

| Kiểu | Ai terminate TLS của external application? | Gateway có đọc HTTP nội dung? | Danh tính nào được xác minh? |
| --- | --- | --- | --- |
| **TLS passthrough** | External server, bởi client app | Thường không | Client app phải xác minh external server; mesh có thể xác minh identity ở hop đến gateway |
| **Gateway TLS origination** | Gateway tạo TLS mới tới external server | Có thể, nếu request trước đó là HTTP mà gateway hiểu | Gateway xác minh external cert/SAN, nội bộ bảo vệ bằng authn/mTLS |
| **Gateway TLS termination + re-encrypt** | Gateway kết thúc inbound TLS rồi thiết lập outbound TLS | Có, theo protocol/policy | Inbound client/gateway TLS identity và outbound partner identity đều cần |
| **Plain TCP forwarding** | Có thể không có TLS | Phụ thuộc giao thức | Không mặc nhiên có confidentiality/integrity |

### 6.5. Istio mTLS không giống mTLS với đối tác

Workload identity như **cluster.local/ns/payments/sa/invoice** có thể dùng trong mesh mTLS. Dịch vụ đối tác có thể yêu cầu **client mTLS certificate do PKI đối tác tin cậy**, không chấp nhận mesh CA.

Vì vậy phải phân biệt:

- **Mesh mTLS:** workload/sidecar ↔ egress gateway, chứng minh caller trong mesh theo trust domain.
- **External TLS:** egress gateway hoặc application ↔ partner, kiểm chứng hostname/certificate đối tác.
- **External mutual TLS:** thêm chứng chỉ client dành cho giao tiếp với partner, với secret custody/rotation riêng.
- **Application authorization:** OAuth/API key/scopes/business permissions, không mặc định được cấp chỉ vì mTLS thành công.

## 7. Workload identity và quyền gọi qua gateway

### 7.1. Dùng danh tính thay vì chỉ IP nguồn

Một NATed Pod IP không ổn định và có thể được tái sử dụng. Trong mesh, workload identity thường được gắn với **Kubernetes ServiceAccount** và chứng thư qua cơ chế mesh CA/SDS/xDS hoặc tương đương.

Ví dụ một policy cho phép **payments/invoice** sử dụng egress gateway tới đối tác, trong khi service thuộc namespace **analytics** không được gọi đối tác đó.

**Gateway inbound authorization** có thể dựa vào **source principal** khi mTLS đang thực sự được thiết lập và proxy có được identity đáng tin. Không tạo policy bằng một header **X-Service-Account** do client tự gửi nếu không có tầng proxy tin cậy đã xác minh rồi gán giá trị đó.

### 7.2. AuthorizationPolicy mẫu có điều kiện

~~~yaml
# Ví dụ Istio AuthorizationPolicy. KHÔNG áp thẳng lên shared production gateway.
# Selector 'istio: egressgateway' và identity tùy cluster đang dùng.
apiVersion: security.istio.io/v1
kind: AuthorizationPolicy
metadata:
  name: allow-invoice-egress-gateway
  namespace: istio-system
spec:
  selector:
    matchLabels:
      istio: egressgateway
  action: ALLOW
  rules:
    - from:
        - source:
            principals:
              - "cluster.local/ns/payments/sa/invoice"
~~~

Điều kiện quan trọng:

- Policy **selector phải khớp đúng gateway Pods**, không phải chọn nhầm tất cả ingress/gateway Pods.
- Policy này áp **gateway inbound** và **chưa giới hạn đích external**; cần chính sách routing/destination tương ứng.
- Khi một **ALLOW policy áp vào workload**, những request không được match theo luật Istio có thể bị deny; nếu shared gateway phục vụ nhiều namespaces, copy mẫu trên có thể **chặn toàn bộ clients hợp lệ khác**.
- Rule **source.principals** dựa vào mesh identity được xác thực; nếu mTLS không được thiết lập thì principal có thể không xuất hiện đúng như kỳ vọng.
- Cần áp dụng **port/host/destination-specific policies** theo khả năng product/protocol, và kiểm thử cả các luồng internal health/control-plane cần thiết.
- **ServiceAccount/RBAC cho phép ai được sửa AuthorizationPolicy** cũng là thành phần bảo mật: actor có quyền thay policy có thể mở gateway lại.

### 7.3. Khi source identity bị mất

Nếu gateway chỉ thấy IP node, một TCP peer không có mTLS, hoặc client đưa header tự khai, không thể suy ra identity **payments/invoice** một cách đáng tin.

Phải kiểm tra:

1. Có **sidecar/ambient data plane** thực sự quản lý workload không?
2. Có mTLS giữa nguồn và gateway không, cert chain/trust domain đúng không?
3. Gateway đang đọc identity từ **TLS peer** hay từ một header không được bảo vệ?
4. ServiceAccount có đúng Pod và namespace không?
5. Phân phối cert, rotation và node clock có ổn định không?
6. Có traffic **hostNetwork/daemonset hoặc sidecar bypass** không được nhận diện?

### 7.4. External application credentials

Một identity trong mesh không thay thế **API token/OAuth/client cert** mà đối tác yêu cầu. Hạn chế:

- **Scopes/permissions** tại bên đối tác.
- **Secret distribution** đến đúng nơi terminate/application TLS.
- Rotation, audit truy cập secrets, chặn log raw Authorization headers.
- **Retry/idempotency** với các operation có tác dụng phụ.
- Tách credentials giữa **dev, staging, production** và các tenants.

## 8. DNS, FQDN, IP, SNI và hostname validation

### 8.1. Một hostname không phải địa chỉ IP cố định

External host **api.partner.example** có thể phân giải thành nhiều IPv4/IPv6 và thay đổi do CDN/load balancing. Vì vậy gateway policy theo FQDN cần phối hợp:

- **DNS resolution** trong mesh/gateway và resolver mà proxy dùng.
- **Cloud firewall** nếu hỗ trợ domain policies hay IP feeds, kèm cơ chế cập nhật.
- **TLS server certificate hostname validation**; hostname trong cert cần khớp identity được client/gateway kỳ vọng.
- **SNI/TLS handling** theo giao thức/phiên bản; không giả định SNI luôn hiện ra plaintext (ví dụ tương lai có ECH).
- **DNS TTL/cache/failover**; không hardcode IP chỉ vì một lần nslookup.

### 8.2. SNI không phải bằng chứng endpoint đáng tin

**SNI** trong ClientHello giúp một TLS endpoint biết hostname mà client định kết nối; ở nhiều mô hình, proxy có thể dùng SNI để chọn route. Tuy nhiên:

- SNI có thể do client tự chọn và **không tự xác thực danh tính đích**.
- Host trong SNI, DNS hostname, certificate SAN và HTTP Host/:authority có thể không đồng nhất trong trường hợp cấu hình sai hoặc lạm dụng.
- Với **TLS passthrough**, gateway có thể không đọc được HTTP Host/path để kiểm tra thêm.
- Với **ECH**, phần hostname information có thể không còn quan sát được theo cách TLS cổ điển; policy dựa vào plaintext SNI cần review tương thích.
- Certificate verification phải diễn ra tại client/gateway tạo TLS đúng cách; **route theo SNI không thay việc kiểm chứng cert**.

Vì vậy, dùng SNI như **routing hint/điều kiện policy** phải kết hợp với **TLS identity validation, source authorization, network controls và upstream identity**.

### 8.3. DNS bypass và direct IP

Một Pod có thể bỏ qua DNS được duyệt bằng cách:

- Kết nối thẳng tới **IP external** nếu đường L3/L4 cho phép.
- Dùng **resolver riêng, DoH/DoT hoặc hardcoded IP**.
- Truy cập **proxy bên ngoài** rồi nhờ proxy gọi host bị cấm.
- Dùng **IPv6** khi policy chỉ kiểm soát IPv4.

Nếu yêu cầu là **mọi external traffic qua gateway**, cần ngăn các đường này ở **CNI/host/cloud routing/firewall**, không chỉ tạo DNS allowlist.

### 8.4. Cảnh báo về TLS origination

Nếu gateway thực hiện TLS origination, kiểm tra rõ:

1. **SNI/server hostname** gửi tới external peer.
2. **CA trust store** được gateway dùng.
3. **SAN/hostname verification** có đang bật đúng semantic và proxy version không?
4. Có vô tình dùng chế độ **insecureSkipVerify** hoặc bỏ kiểm tra certificate chain không?
5. **Client certificate** cho external mTLS có thuộc partner và scope đúng không?
6. Trust anchor, expiry, OCSP/CRL hoặc kiểm tra trạng thái certificate theo khả năng/requirements.

Mã hóa mà **không xác minh đúng peer identity** không giải quyết rủi ro kết nối tới máy chủ giả.

## 9. Buộc đường outbound đi qua gateway

### 9.1. Tại sao chỉ cấu hình VirtualService không đủ?

Khi có rule route qua egress gateway, Pod có thể vẫn:

- Chạy **không có proxy** vì namespace chưa bật injection hoặc bootstrap lỗi.
- Thuộc **ambient** nhưng traffic không đi qua lớp policy mà người vận hành giả định.
- Dùng **hostNetwork/privileged mode, alternate CNI interface hoặc capabilities** để không đi theo interception path chuẩn.
- Dùng cổng/giao thức không được capture như kỳ vọng hoặc **excludeOutboundPorts/IPRanges**.
- Kết nối tới external IP trực tiếp hoặc dùng tunnel/proxy khác.
- Được deploy ở **namespace/cluster/zone** chưa có same policies.

Một traffic policy cấu hình trong proxy chỉ chi phối traffic **được proxy xử lý**. Bảo vệ mạng cần chặn **direct egress** ở nơi nguồn không thể tự thay đổi, thường thông qua CNI/host/VPC/firewall.

### 9.2. Hai vòng enforcement

~~~mermaid
flowchart TD
    A["Workload Pod"] --> P{"Có mesh proxy/traffic capture?"}
    P -->|Có| R["Mesh route/policy: tới egress gateway"]
    P -->|Không/bypass| N{"CNI/host/cloud egress enforcement"}
    R --> G["Egress gateway"]
    N -->|Deny direct Internet| D["Drop + audit"]
    N -->|Policy ngoại lệ được duyệt| X["Explicit exception path"]
    G --> F["Approved firewall/NAT"]
    F --> E["Partner service"]
~~~

**Đường chính** được mesh định tuyến qua gateway. **Đường bảo vệ** là network firewall/policy chỉ cho workload ra các nội bộ bắt buộc và egress gateway, không cho direct Internet. Tùy CNI, sidecar/Pod lưu lượng có thể đi qua Service IP hoặc node path theo thứ tự NAT khác nhau; phải kiểm thử **real enforcement**.

### 9.3. Những ngoại lệ thực sự cần

Không thể đơn giản chặn **mọi egress của Pod trừ gateway** mà không cân nhắc:

- **DNS** tới resolver được duyệt.
- **Mesh control plane** nhận xDS/SDS/chứng thư, thường có ports và Services riêng.
- **Kubernetes API** cho workloads/controllers thực sự cần.
- **Internal service-to-service traffic** đã được phân quyền.
- **Metrics/logging/telemetry** và runtime/identity dependencies.
- **Node-level CNI/CSI, admission/controllers, health probes** theo nền tảng.

Nếu policy chặn các kết nối bootstrap này, Pod có thể không nhận cấu hình/cert, application sẽ mất kết nối và đội vận hành có thể vô tình mở “Any–Any” để cứu sự cố.

### 9.4. Không dùng default deny thiếu đường quản trị

Mọi thay đổi egress trong production cần có:

1. Flow inventory và role owner.
2. Bản đồ chính xác Pod/CNI/host/mesh gateway/cert endpoints.
3. Staging test và **positive control** cho traffic hợp lệ.
4. Negative test cho direct Internet/IP/alternate DNS/IPv6.
5. Cảnh báo khi policy gây reject/timeout bất thường.
6. Một **rollback strategy** không cần bypass security boundary lâu dài.

## 10. NetworkPolicy như một lớp phụ trợ

**Kubernetes NetworkPolicy** chuẩn có thể giới hạn Pod egress theo **ipBlock, namespaceSelector, podSelector và ports** khi CNI thực thi. Nó **không có primitive FQDN allowlist chuẩn**, và enforcement cho hostNetwork, node-local traffic, Service NAT hoặc multi-CNI có thể khác nhau.

### 10.1. Mẫu NetworkPolicy giới hạn egress Pod

Ví dụ giả định một workload **chỉ cần DNS và egress gateway**, không có internal dependencies khác:

~~~yaml
# Ví dụ học tập. Nếu áp thật, phải bổ sung mesh control-plane, internal API
# và mọi dependencies hợp lệ; port 15443/labels là giá trị cần xác minh.
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: restrict-external-egress
  namespace: payments
spec:
  podSelector:
    matchLabels:
      app: invoice
  policyTypes:
    - Egress
  egress:
    - to:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: istio-system
          podSelector:
            matchLabels:
              istio: egressgateway
      ports:
        - protocol: TCP
          port: 15443
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

**Không áp nguyên mẫu lên production.** Trong một cluster thật:

- Gateway có thể dùng **port 443, 15443 hoặc port khác**, và Service port → Pod targetPort có thể khác nhau.
- Label **istio: egressgateway** không phải chuẩn bắt buộc cho mọi gateway deployment.
- DNS service/Pod selector có thể là **kube-dns, CoreDNS hoặc tên khác**.
- Workload proxy có thể cần **istiod/xDS/SDS/CA traffic**, workload còn cần nội bộ khác.
- Service IP routing và điểm kiểm tra policy có thể làm **Pod selector/namespace selector hoạt động khác giả định** trong CNI cụ thể.
- Nếu CNI không enforce NetworkPolicy, YAML có thể **không bảo vệ gì**.
- Policy này không tự chặn **hostNetwork/privileged**, node-originated traffic hoặc external egress từ gateway Pod.

### 10.2. Gateway cũng cần egress boundary

Ngay cả khi APP Pods chỉ tới gateway, **egress gateway Pod** có thể có default route rộng tới Internet. Nếu một actor gọi gateway với đích không được kiểm soát hoặc gateway bị chiếm, gateway có thể trở thành **open proxy**.

Cần:

- **Inbound authorization** chỉ từ trusted mesh identities.
- **Destination/port policy** chỉ cho external services được duyệt.
- Network egress controls từ **gateway namespace/Pod/node** tới external destinations hoặc qua approved firewall.
- **TLS identity validation** cho external service và credential custody.
- Logging/rate/concurrency quotas, alert abnormal destination.
- Tách **high-risk gateways** theo tenant/trust zone nếu shared gateway quá rộng.

### 10.3. Cluster khác/namespace khác cũng phải kiểm chứng

Policy ở namespace payments **không áp dụng tự động** cho:

- Pod ở namespace khác.
- Node daemonsets/hostNetwork components.
- Khác cluster hoặc khác tenant.
- External workload ngoài Kubernetes.
- Sidecarless/ambient path chưa được kiểm thử.

Do đó, outbound boundary là **kiến trúc cấp cluster/network/cloud**, không chỉ một manifest trong namespace ứng dụng.

## 11. Static egress IP, NAT, firewall và đối tác allowlist

Một lý do phổ biến triển khai egress gateway là đối tác chỉ cho phép **một hoặc vài public source IP**.

### 11.1. Egress gateway không tự có static public IP

~~~text
Workload Pod IP
   |
   v
Egress gateway Pod IP (thường là private IP)
   |
   v
Node / VPC route
   |
   v
Cloud NAT / NAT appliance / outbound gateway
   |
   v
Public source IP nhìn thấy tại partner
~~~

Địa chỉ đối tác quan sát **có thể là NAT EIP hoặc node SNAT IP**, không phải IP của egress gateway Pod. Cần xác minh **actual public source IP từ endpoint kiểm tra do tổ chức sở hữu/được phép hoặc partner logs**, không đoán theo tên gateway.

### 11.2. Các điều kiện để public IP ổn định

- Route từ gateway Pods/nodes phải đi qua **NAT/firewall được phê duyệt**, không rẽ sang đường khác khi failover.
- Public IP/EIP phải được **quản lý theo hạ tầng**, không gắn tạm theo một node ephemeral.
- Nếu có nhiều zones/regions, phải có **danh sách mọi IP có thể được dùng** khi HA/failover.
- IPv6 có thể có cơ chế route/public address khác IPv4 SNAT; cần policy riêng.
- Đối tác cần xác nhận **allowlist scope và change process**.
- Network identity vẫn không thay **API authentication** của đối tác; IP allowlist là tín hiệu mạng.

### 11.3. Cloud firewall và route

| Lớp | Mục tiêu | Bằng chứng |
| --- | --- | --- |
| **Workload CNI/NetworkPolicy** | Pod không đi Internet trực tiếp ngoài approved paths | Negative direct-IP tests, policy hit counts |
| **Gateway Pod/node firewall** | Chỉ egress gateway được phép ra các destination/ports | Network rules + flow logs |
| **VPC/VNet subnet route** | Gateway egress đi đúng NAT/NVA/firewall | Effective routes, NAT/session logs |
| **Cloud security groups/NSG** | Giới hạn source/destination theo primitive provider | Ingress/egress policy review |
| **External partner allowlist** | Partner chỉ nhận từ static public IPs được duyệt | Partner connection logs, agreed IP inventory |
| **TLS/app auth** | Chỉ đúng server, client/credential được phép | Cert validation, HTTP 401/403, audit |

**Route có thể tồn tại mà firewall deny, và firewall allow có thể tồn tại mà route sai.** Phải kiểm tra cả hai hướng và khả năng **SNAT/return path**.

### 11.4. Split traffic và failover

Với multi-zone egress gateways, topology có thể gồm:

~~~mermaid
flowchart LR
    A["Workloads zone A/B"] --> G1["Egress GW A"]
    A --> G2["Egress GW B"]
    G1 --> N1["Approved NAT IP A"]
    G2 --> N2["Approved NAT IP B"]
    N1 --> E["Partner allowlist: A + B"]
    N2 --> E
~~~

Nếu partner chỉ allowlist **IP A**, failover sang IP B có thể làm kết nối thất bại dù gateway B và mesh đều healthy. **HA phải bao gồm đối tác, DNS, route, NAT, TLS và credentials**, không chỉ số lượng Gateway Pods.

## 12. Sidecar, ambient và các service mesh khác

### 12.1. Sidecar-based interception

Trong mô hình Istio sidecar, Envoy thường chạy cùng Pod và nhận outbound traffic qua cơ chế capture/iptables hoặc CNI theo cấu hình. Mesh policy được thực thi khi traffic **thực sự đi qua proxy**.

Các điều kiện nên kiểm tra:

- Namespace/Pod đã được **enable injection** và sidecar thực sự chạy/ready chưa?
- Pod có annotation **excludeOutboundPorts, excludeOutboundIPRanges** hoặc cổng đặc biệt nào?
- Sidecar có nhận được **xDS configuration, certificate và service registry** không?
- Destination traffic là **HTTP/TLS/TCP** hay giao thức không được proxy hỗ trợ theo cách mong đợi?
- Workload có **hostNetwork, privileged/capabilities** hoặc đường host routing khác không?

Không được dùng “Pod có nhãn injection enabled” làm bằng chứng sidecar thật đã được injected và chặn direct egress. Cần kiểm tra **runtime containers, proxy config và network data-plane evidence**.

### 12.2. Ambient mesh không phải sidecar được đổi tên

Trong những kiến trúc **Istio ambient** được hỗ trợ, lớp **ztunnel** và **waypoint proxy** có vai trò khác sidecar; policy enforcement và traffic path phụ thuộc loại workload/traffic, scope của waypoint và năng lực phiên bản.

Vì thế:

- Không áp mặc định các rule **sidecar-specific iptables hoặc DestinationRule routing** mà chưa xem tài liệu/khả năng ambient của cluster.
- Không giả định waypoint được tự động dùng cho **mọi external outbound connection**.
- Mô hình **L4 identity/mTLS** và **L7 waypoint policy** cần được đánh giá riêng.
- Các **egress gateway constructs** có thể thay đổi theo Istio release/Gateway API implementation.
- Nếu yêu cầu chặn bypass cao, vẫn phải có **CNI/host/cloud network enforcement** độc lập.

**Kết luận:** trước khi thiết kế egress gateway hãy ghi rõ cluster đang dùng **sidecar, ambient, mixed mode hoặc service mesh khác**. Một sơ đồ chỉ có “sidecar→gateway” có thể sai với data plane thực tế.

### 12.3. Linkerd và các mesh khác

Service mesh khác có thể hỗ trợ **outbound authorization hoặc egress networking** theo cơ chế riêng; không đồng nhất những CRDs như ServiceEntry/VirtualService/DestinationRule/PeerAuthentication của Istio với Linkerd, Consul hay các gateway implementations khác.

Khi so sánh, thay vì đối chiếu tên resource, hãy hỏi:

1. Workload identity được cấp và xác minh theo cách nào?
2. Có **centralized outbound gateway/forward proxy** được hỗ trợ không?
3. Có **mandatory routing** hay chỉ cấu hình proxy cho traffic đã intercept?
4. External **TLS server validation/mTLS client authentication** ở chặng nào?
5. FQDN/IP/port filtering và **policy theo identity** có thể enforce ở đâu?
6. Flow có **bypass prevention**, observability, HA và rollback không?

### 12.4. Kubernetes Gateway API và legacy Istio APIs

Tùy phiên bản, một mesh có thể sử dụng tài nguyên **Gateway API** hoặc những **Istio networking APIs** riêng. Tính năng egress, TLSRoute/TCPRoute/HTTPRoute, policy attachments và cross-namespace references không mặc nhiên tương đương giữa mọi controller.

**Gateway API Gateway** không tự nói rằng gateway đó là ingress hay egress mandatory enforcement. Phải xem implementation, listener/routes, allowedRoutes và backend selection có thật sự phục vụ đường outbound đang kiểm tra hay không.

## 13. Giao thức: HTTP, HTTPS, gRPC, TCP và streaming

### 13.1. HTTPS/TLS

Với HTTPS tới partner, cần phân biệt:

- Route dùng **SNI** từ TLS handshake khi proxy không terminate TLS.
- Route dựa vào **HTTP Host/:authority** nếu gateway thực sự thấy plaintext HTTP.
- Server certificate được **ứng dụng** kiểm tra trong TLS passthrough.
- Server certificate được **gateway** kiểm tra trong TLS origination.
- Đối tác có thể yêu cầu **client certificate, OAuth/API key hoặc custom authorization**.

Một gateway biết SNI mà **không xác minh external certificate** không đủ chứng minh đã gửi dữ liệu đúng server. Ngược lại, certificate hợp lệ nhưng request được route tới sai tenant/account cũng có thể tạo sự cố dữ liệu.

### 13.2. HTTP nội bộ và external HTTPS

Một mô hình có thể dùng **HTTP ở mức ứng dụng từ workload tới local proxy**, **mTLS giữa proxies** và **HTTPS từ gateway tới external server**. Điều đó bảo vệ đường truyền theo những hop được thiết kế, nhưng phải làm rõ:

- Tại điểm nào request trở thành **plaintext**?
- Sidecar/gateway có log headers/body không?
- Gateway dùng **TLS origination** có bảo đảm verify host/chain?
- Connection pooling có tái dùng kết nối khác identity/tenant sai phạm vi không?
- HTTP authorization ở gateway có thực thi **đúng L7 protocol**, không phải passthrough stream?

### 13.3. gRPC và HTTP/2

External gRPC thường sử dụng HTTP/2 và có thể dùng TLS. Cần quan tâm:

- **ALPN/HTTP2 negotiation** tới partner.
- **gRPC deadlines/status/trailers** ở những hop có termination.
- **Long-lived streams** và idle/read timeout không được cắt giữa phiên hợp lệ.
- **Retry semantics**: không retry mù với client/bidirectional streams hay thao tác ghi chưa idempotent.
- Flow-control/backpressure để một client chậm không chiếm toàn bộ proxy buffers.
- **mTLS và authorization** không tự kiểm tra protobuf message semantics.

Một external gRPC call thất bại có thể xuất hiện **gRPC status** dù HTTP status tại proxy trông bình thường. Monitoring nên xem cả **transport errors, HTTP status, gRPC status và upstream reset reason**.

### 13.4. WebSocket, SSE và streaming

Các kết nối này có thể **duy trì lâu**, cần:

| Control | Ý nghĩa |
| --- | --- |
| **Idle/read timeout** | Thời gian không có hoạt động trước khi đóng |
| **Request deadline/lifetime** | Tổng thời gian cho phép nếu nghiệp vụ yêu cầu |
| **Heartbeat/keepalive** | Giúp phát hiện peer chết và tránh idle disconnect không mong muốn |
| **Max concurrent streams/connections** | Tránh gateway chiếm hết FD/memory |
| **Buffer/backpressure limit** | Ngăn client chậm giữ không giới hạn bytes |
| **Authorization revalidation** | Đánh giá token/session khi kết nối dài hoặc đổi quyền |
| **Per-tenant quota** | Một namespace/tenant không chiếm hết gateway |

Đừng kéo dài **mọi timeout lên nhiều giờ** chỉ để một route SSE hoạt động; tạo profile theo protocol/route và đo thực tế.

### 13.5. Non-HTTP TCP và UDP

Một số đối tác dùng **TCP proprietary protocol**; mesh cần route và authz theo các khả năng thực được hỗ trợ, có thể chỉ kiểm tra **L4 destination/source/port**. Nếu không terminate protocol, gateway không hiểu nội dung ứng dụng.

**UDP** có đường xử lý khác TCP/TLS và không phải mọi mesh/gateway hỗ trợ UDP egress một cách tương đương. Không giả định cấu hình TLS/HTTP routing sẽ tự bao phủ DNS UDP, QUIC/HTTP3 hoặc custom UDP protocols.

### 13.6. Protocol sniffing và port naming

Trong Istio, **service port names và protocol declarations** ảnh hưởng cách proxy phân loại traffic. Khai nhầm HTTPS như HTTP hoặc nhầm TLS/TCP có thể dẫn tới:

- HTTP route không match.
- mTLS filter chains không được chọn như dự kiến.
- Gateway trả 404/503 hoặc reset connection.
- TLS origination không diễn ra, hoặc có **TLS trong TLS** sai kiểu.
- Logging thiếu method/path dù team tưởng gateway đã thấy HTTP.

Khi troubleshoot, kiểm tra **protocol thật từ client, ServiceEntry port definition, listener filter chains, VirtualService match và TLS mode**.

## 14. Zero trust egress theo application/tenant identity

Một gateway shared cho cả tổ chức có thể giúp giảm số lượng đường outbound, nhưng tạo **blast radius** nếu policy quá rộng.

### 14.1. Policy theo namespace và service account

Ví dụ:

| Workload identity | Đích hợp lệ | Protocol | Mức quyền |
| --- | --- | --- | --- |
| **payments/invoice** | api.partner.example | HTTPS 443 | Chỉ giao dịch được phép và scope hẹp |
| **billing/report** | report.vendor.example | HTTPS 443 | Chỉ đọc/batch reports, quota riêng |
| **observability/agent** | collector.example | HTTPS hoặc protocol được phê duyệt | Telemetry-only; tránh gửi secrets |
| **development/debug** | Lab endpoint có kiểm soát | HTTPS 443 | Không có production credentials |
| **unknown/unmeshed workload** | Không có external egress mặc định | — | Deny network-level, exception qua approval |

Các hostname **.example** chỉ để mô phỏng.

### 14.2. Không dùng DNS name thay authorization

“Được gọi api.partner.example” chưa đồng nghĩa ứng dụng được phép **POST /admin**, truy cập mọi account, hoặc upload dữ liệu nhạy cảm. Với TLS passthrough, gateway **không có đủ HTTP visibility** để quyết định theo path/method; cần:

- **Application/partner-side IAM/API authorization** theo scope.
- Credential riêng cho từng app/tenant.
- Contract/schema validation và data egress policy nếu dữ liệu nhạy cảm.
- Một gateway có L7 visibility hợp lệ hoặc application proxy theo thiết kế nếu bắt buộc kiểm soát endpoint-level.

### 14.3. Tách shared gateway khi rủi ro cao

Cân nhắc **gateway riêng cho thanh toán, dữ liệu nhạy cảm, tenant lớn hoặc đối tác đòi client mTLS riêng** khi:

- Key/certificate custody khác nhau.
- Compliance cần audit/log retention và network zones riêng.
- Partner allowlist yêu cầu public source IP khác nhau.
- Rủi ro một gateway bị lỗi/chạy hết capacity có thể ảnh hưởng toàn hệ thống.
- Policy L7 và request/response inspection khác nhau.

Đổi lại, nhiều gateways làm tăng **TLS/cert rotation, HA, DNS, NAT/IPAM, monitoring và vận hành**. Quyết định cần dựa trên threat model và SLO, không chỉ tối đa hóa số gateway.

## 15. Observability: một gateway log không đủ bằng chứng

### 15.1. Ghép evidence theo từng chặng

~~~text
APP Pod / identity / request ID
  -> Workload proxy outbound listener/cluster
  -> Gateway inbound listener + mTLS peer principal
  -> Gateway route/destination + TLS outcome
  -> Node/cloud firewall/NAT public source IP
  -> Partner server audit + application transaction ID
~~~

Cần phân biệt **route dự kiến**, **proxy thực đã chuyển traffic**, **flow thật ra khỏi cloud** và **external service có xử lý operation không**.

### 15.2. Metrics hữu ích

| Metric | Vì sao cần | Lưu ý |
| --- | --- | --- |
| **Request rate / bytes theo workload identity** | Phát hiện identity bất thường, traffic burst | Cardinality labels phải có giới hạn |
| **Gateway accepted/denied counts** | Kiểm tra AuthorizationPolicy và quotas | L4 reject và mesh 403 có semantics khác |
| **Upstream connect success/failure** | DNS, route, egress firewall, TLS errors | Không gộp mọi connect failure thành auth failure |
| **TLS handshake/cert validation errors** | External CA/SAN/cert rotation hoặc mTLS nội bộ | Ghi đúng hop xảy ra lỗi |
| **HTTP 4xx/5xx / gRPC status** | Auth failure, partner outage, gateway overload | 503/504 có thể phát sinh ở nhiều hop |
| **p50/p95/p99 latency** | Xem queue/connect/TLS/response time | Average che tail latency |
| **Active connections/streams** | Sizing gateway FD/CPU/memory | HTTP/2 multiplex khác TCP connections |
| **Retry attempts per logical operation** | Ngăn retry amplification | Cần phân biệt retry ở client, sidecar và gateway |
| **Connection pool/queue/buffer saturation** | Phát hiện resource exhaustion | Một route đắt có thể chiếm shared gateway |
| **CNI/host/network denied flows** | Bằng chứng direct egress bị chặn | Cần đúng điểm capture và logging |
| **DNS response/TTLs/resolver errors** | IP drift, split DNS, name resolution | Không ghi raw sensitive queries tràn lan |
| **NAT/EIP/conntrack state** | Xác minh static source IP, port exhaustion | Partner chỉ thấy public source, không phải Pod |
| **Gateway replica health and failover** | HA thực khi Pod/node/zone lỗi | Pod ready không chứng minh external connectivity |

### 15.3. Mẫu event chuẩn hóa

~~~json
{
  "timestamp": "2026-11-28T06:45:22Z",
  "caseId": "MESH-EGRESS-008",
  "cluster": "demo-production",
  "namespace": "payments",
  "serviceAccount": "invoice",
  "sourcePrincipal": "cluster.local/ns/payments/sa/invoice",
  "requestedHost": "api.partner.example",
  "destinationPort": 443,
  "protocol": "TLS",
  "gateway": "payments-egress",
  "routeMatch": "partner-api",
  "meshMtlsAuthenticated": true,
  "externalTlsVerifiedBy": "application-client",
  "policyDecision": "allow",
  "egressNatIp": "198.51.100.25",
  "transportResult": "connected",
  "requestCorrelationId": "req-demo-008"
}
~~~

Đây là **schema tự thiết kế**, không phải raw Envoy/Istio log tự động có đủ các trường. **meshMtlsAuthenticated**, **externalTlsVerifiedBy**, **egressNatIp** và **policyDecision** có thể cần được suy ra từ nhiều hệ thống, và không nên điền giá trị **true** nếu chưa có bằng chứng cho đúng hop.

Địa chỉ **198.51.100.25** nằm trong dải dành cho tài liệu; không phải EIP thật.

### 15.4. Bảo vệ nội dung logs

- Không log **Authorization, Cookie, API key, client private key, request body chứa dữ liệu cá nhân** khi không có nhu cầu và phê duyệt.
- Access logs gateway có thể chứa **SNI, hostname, account ID, URL query**; đây cũng là dữ liệu cần bảo vệ.
- Sử dụng **request ID, workload identity, route ID, partner transaction ID** thay vì raw payload.
- Tách **metrics liên tục** với **debug logging có TTL**, tránh tràn disk hoặc SIEM.
- Bảo quản bằng chứng theo **timestamp UTC, nguồn logs, tính toàn vẹn, retention và RBAC**.

### 15.5. Khi không thấy log ở egress gateway

Khả năng bao gồm:

1. Traffic **đã đi direct** qua node/NAT, route chưa match hoặc sidecar không injected.
2. Pod đi qua **gateway khác/namespace khác**, log xem sai instance.
3. TLS handshake/route lỗi **trước khi tới gateway**.
4. Envoy log chưa bật hoặc filter sampling/retention khác.
5. Traffic là **hostNetwork/UDP/unsupported protocol** theo đường khác.
6. Gateway nhận connection nhưng **đã timeout/reset trước khi emit request-level log**.

Do đó, thiếu log **không tự chứng minh traffic không tồn tại**. Phải ghép **CNI/host flow logs và cloud NAT/firewall**.

## 16. Threat model cho egress gateway và outbound boundary

| Threat / sai cấu hình | Điểm yếu | Tác động | Phòng ngừa / phát hiện |
| --- | --- | --- | --- |
| **Direct egress bypass** | Workload vẫn có default Internet route ngoài proxy | Không kiểm soát được đích, khó truy vết danh tính | CNI/host/VPC deny, negative direct-IP tests, flow logs |
| **Sidecar missing/injection drift** | Namespace/Pod chưa được quản lý | Routing/AuthorizationPolicy không áp | Admission checks, proxy readiness và inventory |
| **REGISTRY_ONLY bị hiểu là firewall** | Chỉ chi phối proxied traffic | Pod khác vẫn gọi Internet trực tiếp | L3/L4 network enforcement độc lập |
| **Gateway thành open proxy** | Không có inbound authz hoặc destination checks | Workload bất kỳ gọi endpoint ngoài chính sách | Source principal/port/host allowlist, CNI gateway egress |
| **Source principal spoofing qua header** | Tin header do client cung cấp | Identity bị giả mạo tại điểm policy | Mesh mTLS peer identity, trusted proxy chain |
| **TLS origination không verify cert** | CA/SAN validation sai | Kết nối tới server giả hoặc bị MITM | External CA trust, SNI/SAN verification, negative TLS tests |
| **Plaintext internal-to-gateway hop** | Không có mTLS/transport bảo vệ ở zone cần | Dữ liệu/credentials bị lộ trong cluster | Mesh STRICT mTLS và encrypted transport tests |
| **SNI-only destination policy** | Không xác thực hostname/IP/certificate thực | Hostname spoofing, IP drift hoặc protocol mismatch | Identity verification + firewall + DNS policy |
| **DNS/DoH/direct IP bypass** | DNS allowlist không enforce network | Kết nối đích bị cấm bằng đường khác | DNS egress restriction, network policy, IPv6 review |
| **Egress IP drift** | NAT failover sang IP chưa allowlist | Partner 403/connect failure, giao dịch gián đoạn | Actual source IP inventory, HA NAT, partner allowlist |
| **Secrets/client cert lộ ở gateway** | Private key/API token nằm ở nhiều containers | Lạm dụng partner identity | Secret store, RBAC, scoped credential, audit/rotation |
| **Too-broad shared gateway policy** | Nhiều tenants dùng cùng route/key | Cross-tenant blast radius, data leakage | Gateway segmentation, per-identity authz và quotas |
| **Rate/retry storm** | Partner chậm, retries không giới hạn | Gateway/partner overload, mất khả dụng diện rộng | Deadline, retry budget, circuit breaker, bounded queues |
| **Gateway SPOF** | Một replica/node/zone, single NAT | Mất external dependencies | Multi-zone HA, failover, positive tests |
| **Webhook/mesh CA/control-plane outage** | Proxy không nhận config/cert | Routing và identity bị ảnh hưởng | HA, expiry/reconnect monitoring, break-glass |
| **Route drift làm bypass firewall** | VPC route/SG/Node firewall thay đổi | Bỏ qua approved inspection zone | IaC guardrails, route/flow audits |
| **IPv6 escape path** | Policy chỉ kiểm soát IPv4 | Lưu lượng ra ngoài đường không kiểm tra | IPv6 route/firewall/flow negative tests |
| **HostNetwork/privileged exception** | Workload bypass CNI/proxy restrictions | Lateral movement/exfiltration | Pod Security, admission, privileged workload review |
| **Audit gaps** | Không correlate source identity và NAT | Không chứng minh ai gọi partner | Gateway + mesh + cloud flow + partner logs |
| **Sensitive data in access logs** | Log request headers/body | Secrets/PII lộ qua telemetry | Sanitization, sampling, retention, RBAC |

### 16.1. Potential path không đồng nghĩa successful exfiltration

Nếu phát hiện Pod có direct route tới Internet, đó là **potential bypass**. Cần kiểm tra **effective policy**, network flow và application evidence để kết luận có kết nối hoặc dữ liệu đã được gửi ra ngoài hay chưa. Ngược lại, nếu gateway log không ghi traffic nhưng cloud NAT ghi kết nối ngoài, cần điều tra route drift/bypass.

### 16.2. Kẻ có quyền sửa mesh resources có thể thay boundary

Một workload hoặc CI identity có quyền sửa **ServiceEntry, VirtualService, DestinationRule, Gateway, AuthorizationPolicy, NetworkPolicy hoặc deployment labels** có thể tạo đường truy cập ngoài mong muốn. Do đó:

- Kubernetes **RBAC/Admission/GitOps permissions** là control của outbound boundary.
- Không cho developer ứng dụng tự sửa **cluster-wide/shared gateway policies** nếu chưa review.
- Cấm đường bypass qua privileged/hostNetwork theo risk policy.
- Theo dõi **policy change events** và so effective config với IaC desired state.

### 16.3. Egress gateway vẫn có thể trở thành điểm exfiltration

Ngay cả khi không có bypass, một **đích được allow** có thể bị lạm dụng để đưa dữ liệu trái phép nếu quyền ứng dụng rộng. Ví dụ một API upload đối tác được phê duyệt nhưng credential bị chiếm và ứng dụng có quyền đọc quá nhiều dữ liệu.

Cần **least privilege ở ứng dụng và đối tác, data classification, DLP nếu phù hợp, rate/quota, scoped API credentials và audit theo business operation**. Network allowlist chỉ là một trong nhiều lớp.

## 17. Sizing, high availability và overload behavior

Egress gateway tập trung làm tăng khả năng kiểm soát nhưng cũng tập trung **tải, failure domain và chi phí TLS**.

### 17.1. Những tài nguyên chịu tải

| Tài nguyên | Nguyên nhân tăng | Dấu hiệu |
| --- | --- | --- |
| **TCP/HTTP active connections** | Nhiều workloads, long-lived streams | Active sockets, FD, connection pool saturation |
| **CPU/TLS handshakes** | New connections, mTLS, TLS origination, certificate operations | CPU, handshake latency, TLS errors |
| **RAM/buffers** | Large uploads/downloads, slow clients, HTTP/2 streams | RSS, proxy buffers, OOM/restarts |
| **Conntrack/SNAT ports** | Nhiều outbound flows tới same partner IP:port | NAT port usage, connect failures |
| **DNS/cache** | FQDN resolution burst, partner/CDN changes | DNS latency/errors, stale routes |
| **Network bandwidth** | Batch sync, backup, streaming | BPS/PPS, drops/retransmissions |
| **Retry/queue** | Partner timeout hoặc gateway overload | Attempts/request, pending queues, p99 latency |
| **Certificates/secret rotation** | Rollover cùng lúc, CA trust changes | Validation failures, config stale |

### 17.2. Little's Law cho concurrent outbound operations

Với trạng thái ổn định:

\[
L = \lambda W
\]

Trong đó **L** là số operations đang xử lý trung bình, **λ** là số operations mỗi giây và **W** là thời gian trung bình một operation trong hệ thống.

Ví dụ gateway xử lý trung bình **500 outbound requests/giây** với thời gian 0,2 giây thì khoảng **100 in-flight operations**. Nếu partner chậm thành 2 giây mà lượng requests vẫn được chấp nhận, khoảng **1.000 in-flight operations** có thể tích lũy, chưa tính retries, WebSocket hoặc HTTP/2 streams.

Con số chỉ dùng để **lý giải cơ chế**, không thay capacity testing và p99. Một gateway có nhiều TLS streams, buffered bodies và multi-hop retries có thể cần tài nguyên vượt số in-flight trung bình.

### 17.3. Bounded queues, circuit breakers và retry budgets

- Đặt **concurrency/connection pool limits** phù hợp với capacity gateway và partner.
- Nếu quá tải, dùng **bounded queue hoặc load shedding** theo thứ tự ưu tiên; không giữ backlog vô hạn.
- Retry chỉ cho **lỗi, method và idempotency semantics** phù hợp, trong tổng deadline.
- Dùng **backoff có jitter, circuit breaker, outlier detection** nếu implementation hỗ trợ.
- Nếu đối tác trả 429/503/Retry-After, client cần hiểu **quota và retry policy**, không retry ngay hàng loạt.
- Tách **tenant/service budgets** để một workload báo cáo lớn không làm hết connection pool dành cho payment.

### 17.4. Fail-open hay fail-closed?

Nếu gateway bị lỗi, có hai lựa chọn khái niệm:

1. **Fail-closed:** outbound không vượt ra đường khác ngoài approved gateway; an toàn về boundary nhưng ảnh hưởng availability.
2. **Fail-open/alternate path:** workload có thể ra ngoài trực tiếp hoặc qua gateway khác; tăng availability nhưng phải đánh giá liệu còn đáp ứng security policy.

Với workload xử lý dữ liệu nhạy cảm, **direct Internet fallback không được mặc nhiên cho phép**. Nếu muốn HA, thiết kế **nhiều gateway replicas/zones cùng một chính sách**, có route/NAT/partner allowlists được kiểm chứng.

### 17.5. Health checks không chứng minh partner path khỏe

Gateway Pod báo Ready hoặc Envoy listener healthy không có nghĩa:

- Partner DNS resolve được.
- Firewall/NAT route đúng và SNAT port chưa cạn.
- TLS certificate validation thành công.
- Partner API token còn quyền.
- Partner API đang đáp ứng trong SLO.

Nên kết hợp **liveness/readiness** với **synthetic outbound checks có quyền và quota nhỏ**, đồng thời tránh cho health check tạo giao dịch thực ngoài dự kiến.

## 18. Case study 1: egress gateway có policy nhưng Pod vẫn ra Internet trực tiếp

### 18.1. Bối cảnh giả định

Nhóm bảo mật triển khai Istio ServiceEntry và VirtualService định tuyến external HTTPS qua egress gateway. Dashboard gateway hiển thị nhiều traffic hợp lệ. Một Pod vừa triển khai ở namespace khác lại kết nối được tới một hostname ngoài allowlist.

### 18.2. Evidence

| Evidence | Quan sát | Câu hỏi |
| --- | --- | --- |
| **E1 – Pod deployment** | Sidecar/ambient enrollment khác các Pods production | Pod có traffic capture thật không? |
| **E2 – Proxy config** | Không có outbound route tương ứng ở Pod đó | Namespace/identity nào thiếu config? |
| **E3 – Gateway logs** | Không có connection từ Pod này | Traffic chưa tới gateway hay gateway log thiếu? |
| **E4 – Cloud NAT flow logs** | Source node mở direct connection tới external IP | Network layer có cho direct egress không? |
| **E5 – Kubernetes NetworkPolicy** | Không có default deny ở namespace này | Pod có thể bypass mesh routing bằng đường mạng |
| **E6 – Security baseline** | IaC chỉ kiểm tra ServiceEntry, không kiểm tra unmeshed workloads | Gap ở guardrails/ownership |

### 18.3. Cách xử lý

1. Định danh **Pod, namespace, ServiceAccount, node, network mode, thời điểm**.
2. Kiểm tra **sidecar injection/ambient enrollment**, proxy config và route match.
3. Xem **CNI/host/cloud flow logs**, không chỉ gateway access logs.
4. Bảo đảm **Kubernetes NetworkPolicy/host firewall** chặn direct Internet từ workload class này, ngoại trừ những destinations được phê duyệt.
5. Chạy **positive test** với partner qua gateway và **negative test** với direct IP/hostname ngoài allowlist.
6. Bổ sung **admission/GitOps checks** phát hiện workloads không tham gia mesh hoặc có đặc quyền bypass.
7. Xem lại cloud egress flows trong thời gian policy gap để xác định **phạm vi traffic thực**, không suy từ một kết nối test thành rò dữ liệu.

**Bài học:** route của mesh là một lớp; **bắt buộc đi qua gateway** phải được chứng minh ở network data plane.

## 19. Case study 2: TLS origination cho phép kết nối nhưng sai danh tính đích

### 19.1. Bối cảnh

Gateway được cấu hình để tạo TLS tới external service. Sau khi thay external DNS, một luồng outbound vẫn có **TCP connect/TLS handshake thành công**, nhưng team phát hiện certificate verification không được cấu hình chặt; gateway có thể chấp nhận certificate không khớp hostname dự kiến trong trường hợp policy sai.

### 19.2. Dòng rủi ro

~~~text
Client requests api.partner.example
       |
       v
Gateway resolves external DNS
       |
       v
Connects to an IP
       |
       v
Starts TLS
       |
       +-- Nếu hostname/CA verification thiếu:
       |     Encryption vẫn có thể có
       |     Nhưng identity của external server chưa chắc đúng
       |
       +-- Nếu validation đúng:
             Chỉ chấp nhận peer có certificate chain/hostname hợp lệ
~~~

### 19.3. Hành động

- Xác định **gateway là bên TLS client** hay application client vẫn sở hữu TLS session trong passthrough.
- Kiểm tra **SNI, CA bundle, SAN verification, TLS versions/ciphers** theo chuẩn được duyệt.
- Không dùng **insecureSkipVerify hoặc tương đương** để làm các cuộc gọi “chạy được”.
- Kiểm tra **certificate expiry, chain rotation, CDN endpoint/SAN changes** của partner.
- Chạy **negative TLS fixture** trong lab (wrong CA/wrong SAN) và xác nhận gateway từ chối.
- Tách **external client certificate** dùng cho partner mTLS khỏi mesh mTLS credentials.
- Đối chiếu audit/transaction logs để xác định request nào thực sự được gửi đi trong thời gian cấu hình yếu.

**Bài học:** mã hóa transport **không đồng nghĩa xác thực đích chính xác**. Bên nào phát sinh TLS phải có trách nhiệm verify identity.

## 20. Case study 3: NAT đổi IP sau failover khiến đối tác chặn

### 20.1. Bối cảnh

Một service thanh toán outbound qua hai egress gateway replicas. Partner chỉ cho kết nối từ một public IP được phê duyệt. Khi cluster di chuyển traffic sang zone dự phòng, gateway vẫn Ready, service mesh vẫn có mTLS, nhưng API thanh toán trả lỗi kết nối.

### 20.2. Evidence

| Nguồn | Quan sát | Hàm ý |
| --- | --- | --- |
| **Gateway access logs** | Workload request được nhận, TLS route đúng | Mesh-to-gateway path có thể khỏe |
| **Upstream connect errors** | Tăng đột biến sau zone failover | Lỗi nằm ở gateway-to-partner hoặc mạng |
| **Cloud NAT logs** | External source IP chuyển từ IP A sang IP B | Partner có thể đang thiếu allowlist B |
| **Partner logs** | IP B bị từ chối theo nguồn | Cần xác minh allowlist chính xác |
| **DNS/TLS diagnostics** | Host và cert đúng, không có hostname mismatch | Hạn chế khả năng TLS identity là nguyên nhân |
| **Change event** | Pod/node/zone failover | Cùng thời điểm route/NAT path thay đổi |

### 20.3. Khắc phục

1. Ghi lại **NAT source IP thực** ở cả hai zones/paths.
2. Xác minh **partner IP allowlist** cho toàn bộ IP dự kiến trong HA design.
3. Không sửa AuthorizationPolicy của mesh để “sửa” lỗi partner network allowlist.
4. Dùng **approved NAT/EIP architecture** hoặc cập nhật partner allowlist theo change process.
5. Kiểm thử failover **gateway Pod, node, zone, NAT/firewall**, không chỉ gateway Deployment readiness.
6. Tách lỗi **network rejection, TLS validation, 401/403 partner auth và app transaction**.

**Bài học:** static egress IP là thuộc tính của **toàn tuyến routing/NAT**, không phải tên egress gateway.

## 21. Case study 4: gateway trở thành nút nghẽn khi partner chậm

### 21.1. Bối cảnh

Partner reporting API tăng response latency. Workloads retry mạnh và gateway nhận nhiều streams. Ứng dụng bắt đầu thấy 503/504, trong khi CPU/memory gateway và số upstream connections tăng.

~~~mermaid
flowchart TD
    P["Partner chậm"] --> L["Upstream response latency tăng"]
    L --> Q["In-flight requests/queue tăng"]
    Q --> E["Egress gateway bão hòa"]
    E --> T["503/504/timeout tại workload"]
    T --> R["Client + proxy retry"]
    R --> Q
    E -. "Containment" .-> C["Retry budget, bounded concurrency/queue, traffic shed, partner fix"]
~~~

### 21.2. Vì sao tăng timeout có thể làm tệ hơn?

**Timeout dài hơn** có thể giúp một số request chậm hoàn tất, nhưng cũng khiến các connections/streams giữ tài nguyên lâu hơn. Khi retry storm chưa được kiểm soát, tăng timeout hàng loạt có thể tăng **in-flight load** và đẩy gateway vào exhaustion.

### 21.3. Phương án containment

- Xác định **nguồn request** nào đang tạo tải và phân biệt normal user traffic với retries.
- Giới hạn retries, concurrency/queue và dùng **circuit breaker** phù hợp.
- Đảm bảo **idempotency** cho các operation có side effects.
- Nếu partner đang rate limiting, tôn trọng quy tắc **backoff/Retry-After** phù hợp.
- Scale gateway hoặc tách workload budgets **sau khi đo bottleneck**, tránh nhân tải xuống partner.
- Theo dõi **recovery metrics**: p95/p99, active connections, retry ratio, queue wait, partner errors, business success.

**Bài học:** tập trung outbound qua gateway mang lại quan sát tốt, nhưng gateway cũng là một **shared dependency cần capacity và SLO**.

## 22. Case study 5: shared gateway cho phép tenant gọi đích ngoài phạm vi

### 22.1. Bối cảnh giả định

Một egress gateway dùng chung cho **payments** và **analytics**. Routing cho nhiều external destinations được khai báo, nhưng inbound AuthorizationPolicy chỉ kiểm tra “workload có mesh mTLS hợp lệ” thay vì phân quyền **source principal → destination**.

Kết quả: workload thuộc analytics có thể gọi host thanh toán dù ứng dụng đó không được phép theo kiến trúc, miễn gateway có route tới host.

### 22.2. Phân tích theo các lớp

| Lớp | Policy hiện tại | Gap |
| --- | --- | --- |
| **Workload→gateway mTLS** | Mọi mesh principal hợp lệ được vào | Identity được xác thực nhưng quyền chưa đủ hẹp |
| **Gateway routing** | Có route tới cả analytics và payments partners | Route availability không đồng nghĩa authorization |
| **Gateway outbound firewall** | Cho IP/port của cả hai partners | Không phân biệt source workload |
| **Partner auth** | Có API credential của từng dịch vụ | Nếu shared credential hoặc credential bị lộ, blast radius lớn |
| **Observability** | Chỉ ghi external hostname/source IP NAT | Không xác định được source principal cần điều tra |

### 22.3. Khắc phục

1. Thiết kế ma trận **source ServiceAccount identity → allowed destination/protocol/credential**.
2. Áp **source authorization** tại gateway hoặc policy point có khả năng kết hợp identity với destination theo giao thức thực.
3. Nếu L7 visibility không có do TLS passthrough, phải chọn **policy ở mức host/SNI/route/port** đủ tin cậy hoặc dùng cách terminate hợp lệ khi cần inspect.
4. Xem xét **gateway riêng** cho data nhạy cảm hoặc tenants có yêu cầu PKI/IP riêng.
5. Dùng **application credentials tách biệt**, scoped theo partner.
6. Chạy **negative test** analytics→payments partner và positive test cho mỗi luồng hợp lệ.
7. Log **principal, policy decision, destination và business operation ID** ở mức phù hợp.

**Bài học:** mTLS xác minh **ai gửi**, không tự trả lời **người đó được gửi tới đâu**.

## 23. Quy trình chẩn đoán outbound không hoạt động

Một lỗi ở gateway không nhất thiết là sự cố gateway. Nên điều tra từ **client identity và endpoint intent** ra từng chặng:

~~~mermaid
flowchart TD
    A["Workload gọi external API lỗi"] --> B{"DNS và endpoint có đúng?"}
    B -->|Không| C["Kiểm tra resolver, FQDN, IPv4/IPv6"]
    B -->|Có| D{"Workload được mesh quản lý?"}
    D -->|Không| E["Kiểm tra injection/ambient, CNI policy"]
    D -->|Có| F{"Proxy route tới gateway đúng?"}
    F -->|Không| G["ServiceEntry / VS / listeners / clusters"]
    F -->|Có| H{"Gateway xác thực/authorize workload?"}
    H -->|Không| I["mTLS cert / principal / authz"]
    H -->|Có| J{"Gateway -> external connect/TLS thành công?"}
    J -->|Không| K["DNS/NAT/firewall/SNI/CA/SAN/partner"]
    J -->|Có| L["HTTP/gRPC/app auth, quota, timeouts và retries"]
~~~

### Bước 1 — Định danh operation

Thu các dữ kiện:

- Cluster, namespace, Pod, ServiceAccount, mesh mode, thời điểm và timezone.
- Host external và **địa chỉ DNS resolved**, protocol/port, request/trace ID.
- Lỗi quan sát ở client: DNS error, connect timeout, TLS alert, HTTP/gRPC status, application error.
- SLO và operation type: GET an toàn retry hay POST có side effects?
- Kết nối đang phát sinh từ **app container, sidecar, gateway, node, CI/bastion** hay một network khác?

### Bước 2 — Xác minh data-plane enrollment và route

- Workload có **sidecar/ambient enrollment** đúng phạm vi không?
- Sidecar/ztunnel/waypoint/gateway có ready, nhận cấu hình và cert còn hạn không?
- ServiceEntry match **FQDN/port/protocol** không?
- VirtualService/Gateway API rules có route qua đúng gateway namespace/service/port không?
- DestinationRule TLS mode/cluster pool có khớp với listener trên gateway không?
- Có **direct outbound path** bị NetworkPolicy/host firewall chặn như kỳ vọng không?

**Lỗi route** có thể phát sinh ở proxy ngay cả khi external DNS khỏe. Không sửa firewall khi chưa kiểm tra listener/route match.

### Bước 3 — Xác minh mesh mTLS và source authorization

- Source principal đúng ServiceAccount/namespace/trust domain?
- Gateway nhận TLS peer identity hay chỉ IP/header?
- PeerAuthentication/AuthorizationPolicy đang áp trên **đúng workload/namespace/port**?
- Cert chain, clock skew, CA rotation hoặc trust-domain mapping có vấn đề?
- Có rule **DENY/ALLOW** nào override/hợp thành theo semantics của phiên bản hiện tại?

Nếu gateway từ chối source principal, thêm đối tác vào DNS allowlist sẽ không sửa authentication/authorization.

### Bước 4 — Xác minh gateway-to-partner network

1. DNS do gateway dùng trả về IP nào, có IPv6 không?
2. Có route qua approved firewall/NAT không?
3. NetworkPolicy/host/cloud firewall có allow đúng 5-tuple?
4. SNAT IP thực tại phía partner có thuộc danh sách được phê duyệt?
5. TCP handshake và TLS handshake thành công tới đúng hostname/cert chưa?
6. External application token/client mTLS có hiệu lực và đúng scope?
7. Partner trả status nào, có rate limit, DNS failover hoặc maintenance không?

### Bước 5 — Quan sát và chọn đúng biện pháp

| Triệu chứng | Lớp ưu tiên kiểm tra | Không nên làm |
| --- | --- | --- |
| **DNS NXDOMAIN** | Resolver, ServiceEntry, CoreDNS/private DNS | Mở firewall Any–Any |
| **No route/503 ở sidecar** | Listener/cluster/route/service discovery, xDS | Đổi API token đối tác |
| **Gateway từ chối principal** | mTLS identity/AuthorizationPolicy | Bỏ kiểm tra TLS hoặc mở gateway cho mọi source |
| **Connect timeout ở gateway** | Route/NAT/firewall/partner allowlist | Tăng timeout vô hạn |
| **TLS unknown CA/SAN mismatch** | Certificate chain, hostname, TLS origination vs passthrough | Bật insecure verification |
| **HTTP 401/403 từ partner** | External credential/authorization, partner-side logs | Nới ServiceAccount RBAC của Kubernetes |
| **HTTP 403 từ Envoy policy** | Gateway/workload AuthorizationPolicy | Kết luận partner đã chặn khi chưa xem hop |
| **HTTP 429** | Partner quota hoặc gateway rate policy | Retry lập tức và không giới hạn |
| **503/504 khi tải cao** | Gateway capacity, partner latency, retry budgets, DNS/TLS | Chỉ scale vô hạn gateway |
| **Chỉ fail khi gateway failover** | Zone NAT IP, DNS/HA route, partner allowlist | Tắt mTLS để lấy availability |
| **Traffic bypass xuất hiện** | CNI/host/cloud rules, mesh enrollment, Pod privileges | Chỉ tăng log tại gateway |

### Bước 6 — Khẳng định kết quả

Một fix đạt khi **client operation hợp lệ thành công**, **gateway có identity/policy/route evidence**, **cloud NAT/partner thấy đúng IP**, và **direct unauthorized traffic vẫn bị chặn**. Kết nối hoạt động trở lại **không chứng minh** outbound boundary còn nguyên vẹn nếu biện pháp tạm thời cho phép bypass.

## 24. Công cụ kiểm tra chỉ đọc trong Istio/Kubernetes

Những lệnh sau chỉ dùng trên **cluster được phép truy cập** và với danh tính có quyền phù hợp. Chúng phục vụ **inventory/diagnostics**, không thay packet/flow evidence. Tên labels, namespace, workload và resource types phụ thuộc cluster thực tế.

### 24.1. Liệt kê các tài nguyên có liên quan

~~~bash
# Kubernetes/Istio inventory, không sửa tài nguyên.
kubectl get pods -n istio-system -l istio=egressgateway -o wide
kubectl get serviceentries -A
kubectl get virtualservices -A
kubectl get destinationrules -A
kubectl get gateways -A
kubectl get authorizationpolicies -A
kubectl get peerauthentications -A
kubectl get networkpolicies -A

# Xem service account và proxy containers của workload mẫu.
kubectl get pod invoice-pod -n payments \
  -o jsonpath='{.spec.serviceAccountName}{"\n"}{.spec.containers[*].name}{"\n"}'
~~~

**Một số cluster dùng Gateway API/ambient**, nên tên resources/labels/injection khác hoặc Pod không có sidecar theo thiết kế. Không kết luận lỗi chỉ vì câu lệnh trên trả không có resource **istio: egressgateway**.

### 24.2. Xem trạng thái config proxy

~~~bash
# Istio CLI: read-only analysis trong phạm vi quyền hiện tại.
istioctl proxy-status

# Thay invoice-pod bằng đúng Pod có proxy và namespace được cấp quyền.
istioctl proxy-config listeners invoice-pod -n payments
istioctl proxy-config routes invoice-pod -n payments
istioctl proxy-config clusters invoice-pod -n payments
~~~

Các lệnh này **chỉ phản ánh Envoy proxy đã được chọn** và version-specific config. Nếu cần xác nhận gateway side, chạy tương tự với **egress gateway Pod thực** thay vì app Pod. Đặc biệt, với TCP/TLS passthrough, **routes** có thể biểu hiện khác HTTP route; cần xem **listeners/filter chains/clusters**.

### 24.3. Kiểm tra quyền thay policy

~~~bash
# Read-only authorization checks cho context/identity hiện tại.
kubectl auth can-i create serviceentries.networking.istio.io \
  -n payments
kubectl auth can-i update authorizationpolicies.security.istio.io \
  -n istio-system
kubectl auth can-i create networkpolicies.networking.k8s.io \
  -n payments
~~~

**can-i** phản ánh authorization của context/user đang dùng, không chứng minh toàn bộ users/ServiceAccounts khác bị chặn. Không cần nâng quyền chỉ để chạy checklist nếu danh tính ít quyền trả **no/Forbidden**.

### 24.4. Kiểm tra log, không lộ credentials

~~~bash
# Ví dụ tên deployment có thể khác; giới hạn lượng log lấy về.
kubectl logs -n istio-system \
  deployment/istio-egressgateway --tail=100
~~~

Không xuất **kubectl config view --raw**, Secrets, private keys, raw Authorization headers hoặc toàn bộ request bodies vào ticket. Nếu cần sâu hơn, dùng **access logging có redaction/TTL**, yêu cầu owner phù hợp và giới hạn dữ liệu.

### 24.5. Điều gì Kubernetes CLI không tự xác nhận?

- Partner nhìn thấy **public NAT IP nào**.
- Traffic direct đi qua **node/VPC firewall** ngoài Envoy.
- **External TLS server identity** đã được client/gateway validate hay chỉ handshake thành công.
- Một route được khai báo có được **mọi Pod** sử dụng không.
- Đường **IPv6, hostNetwork, custom CNI, transparent proxy bypass** có được kiểm soát không.

Các điểm này cần **cloud/network flow logs, gateway/Envoy logs, network policy counters, partner logs** và các test đúng nguồn.

## 25. Rollout, change management và policy-as-code

### 25.1. Inventory trước khi thay đổi

Ghi lại:

1. **Cluster/mesh version/mode/CNI** và gateway implementation.
2. Các **source workloads**, namespaces, ServiceAccounts và trust domains.
3. Tập **external hosts, protocols, destinations, ports, business owners**.
4. Các đường **DNS, proxy, NAT/firewall, VPN/on-prem, IPv4/IPv6**.
5. **PeerAuthentication, AuthorizationPolicy, ServiceEntry, routing policy** đang áp.
6. Những **identity/credential và CA/trust anchors** cần cho mesh/external TLS.
7. SLO, quota, criticality, expected traffic/streams và retry behavior.
8. Các ngoại lệ **unmeshed/hostNetwork/privileged** đã được phê duyệt.

### 25.2. Triển khai từng bước

Một lộ trình thường an toàn hơn “bật REGISTRY_ONLY cho toàn mesh ngay lập tức”:

- **Observe:** thu baseline external destinations, bytes/requests, trust boundary, application failures.
- **Classify:** phê duyệt hosts/identities, phân biệt required dependencies và traffic không rõ chủ sở hữu.
- **Prepare gateway:** listener/routes, mTLS identity, external TLS, firewall/NAT/HA, log/metrics.
- **Pilot:** áp cho một namespace hoặc service được kiểm soát, xác nhận positive và negative flows.
- **Enforce network boundary:** chặn direct egress ở đúng CNI/host/cloud path sau khi có bằng chứng routing hợp lệ.
- **Expand:** đưa workloads vào policy theo nhóm, có rollback, canary, communication với partner.
- **Monitor/drift:** theo dõi unexpected direct egress, policy edits, cert expiry, public NAT IP drift và SLO.

### 25.3. Ai được thay gì?

| Tài nguyên/khả năng | Chủ sở hữu đề xuất | Nguy cơ khi cấp quyền rộng |
| --- | --- | --- |
| **ServiceEntry cho external hostname** | Application owner đề nghị, platform/security review | Mở đích không được duyệt |
| **VirtualService/Gateway route** | Service mesh platform team | Chuyển traffic đi vòng gateway hoặc sai tenant |
| **DestinationRule TLS mode** | Mesh/PKI team | Downgrade TLS hoặc làm mất hostname validation |
| **AuthorizationPolicy** | Security/platform policy owner | Mở gateway cho nguồn không được phép |
| **NetworkPolicy/CNI policy** | Network/platform security | Cho direct Internet/bỏ chặn nguồn |
| **Cloud firewall/NAT/EIP** | Cloud network owner | Bypass inspection, public IP drift, route leak |
| **Credentials/client certs đối tác** | Secret/PKI owner, business API owner | Cross-tenant credential reuse, exfiltration |
| **Policy deployment automation** | GitOps/CI owner | Một token CI quá quyền thay toàn boundary |

### 25.4. Mẫu change record

~~~text
Change ID:
Source namespace/ServiceAccount:
External partner hostname/ports/protocol:
Expected routing through gateway:
Workload-to-gateway mTLS policy:
Gateway-to-partner TLS/certificate requirements:
Approved NAT/public source IP(s):
DNS/IPv4/IPv6/route and firewall scope:
Authentication credentials owner and rotation:
Expected metrics and success SLO:
Positive and negative tests:
Rollback/expiry/review date:
Approver and operational owner:
~~~

### 25.5. Hạn chế policy drift

Một thay đổi nhỏ tại **annotation injection**, gateway Deployment labels, ServiceEntry wildcard host, AuthorizationPolicy hoặc VPC route có thể làm outbound boundary yếu đi. Vì vậy nên:

- Kiểm tra drift giữa **IaC/GitOps desired state và runtime config**.
- Cảnh báo khi bật **ALLOW_ANY** không có exception hoặc khi thêm wildcard/external host quá rộng.
- Cảnh báo khi **namespace/workload bị loại khỏi mesh**, có hostNetwork/privileged access ngoài approval.
- Theo dõi **default routes** và cloud firewall egress thay đổi.
- Bảo vệ **CI credentials và review branch policies**.
- Kiểm thử **actual egress behavior** định kỳ, không chỉ validate YAML schema.

## 26. Bộ kiểm thử outbound boundary có kiểm soát

Mọi kiểm thử phải ở **lab/staging/cluster có ủy quyền**, giới hạn request/connection/bytes/time, không dùng công cụ scan/flood vào partner không cho phép. Với các test TLS giả lập hoặc partner outage, dùng **test endpoint do tổ chức kiểm soát** thay vì ảnh hưởng dịch vụ sản xuất.

| Test | Mục tiêu | Kết quả mong đợi |
| --- | --- | --- |
| **P1 – approved workload/host** | payments/invoice gọi partner hợp lệ | Route qua gateway, mesh identity và external TLS đúng |
| **N1 – unauthorized source identity** | analytics ServiceAccount thử gọi payments partner | Bị từ chối ở điểm được thiết kế, có policy event |
| **N2 – unregistered external FQDN** | Workload đã vào mesh gọi host không được duyệt | Reject/deny đúng policy; không direct fallback |
| **N3 – direct external IP** | Test workload kết nối một IP ngoài policy | CNI/host/cloud network layer chặn bypass |
| **N4 – alternate DNS/DoH** | Lab client dùng resolver khác hoặc DNS-over-HTTPS tới đích thử | Không vượt được egress boundary |
| **N5 – IPv6 alternate route** | Dual-stack test với external IPv6 endpoint | Không có bypass ngoài approved path |
| **N6 – unmeshed Pod** | Pod lab không có sidecar/ambient enrollment thử outbound | Không ra Internet trực tiếp nếu policy yêu cầu |
| **N7 – hostNetwork/privileged attempt** | Review admission và controlled fixture trong lab | Ngoại lệ bị chặn/cảnh báo hoặc có policy riêng |
| **P2 – mesh mTLS** | Workload đúng principal gọi gateway | Peer identity được xác thực, policy allow |
| **N8 – wrong principal/untrusted mesh peer** | Client lab không có cert/identity hợp lệ | Gateway từ chối trước external access |
| **P3 – external TLS chain and SAN** | Gateway/app kết nối đúng partner lab server | Certificate verification thành công |
| **N9 – wrong CA/hostname** | Lab partner giả có cert không phù hợp | Kết nối bị từ chối, không bật insecure mode |
| **P4 – partner client mTLS** | Khi hợp đồng yêu cầu | Đúng client certificate/identity, rotation path hoạt động |
| **N10 – wrong external client cert** | Test certificate không được đối tác tin | Partner không cấp phép truy cập |
| **P5 – NAT source IP** | Test hợp lệ qua gateway zone A/B | Partner thấy IP A/B đã allowlist |
| **F1 – gateway replica failure** | Staging kill/evict một gateway replica theo change plan | Failover theo approved path, không direct bypass |
| **F2 – NAT/zone failover** | Test alternate egress path | Partner allowlist/route/firewall đúng, session recovery theo SLO |
| **F3 – partner timeout/rate limit** | Test endpoint mô phỏng chậm hoặc 429 | Retry budget/circuit breaker/backpressure đúng |
| **F4 – mesh CA/cert rotation** | Test trong môi trường được kiểm soát | mTLS phục hồi, không phải tắt verification |
| **O1 – end-to-end correlation** | Một request/trace ID qua workload/gateway/NAT/partner | Logs đủ nguồn, đích, policy decision, không chứa secret |
| **O2 – policy drift** | GitOps test thêm ServiceEntry wildcard hoặc mở SG | Admission/review/alert phát hiện ngoài approval |
| **P6 – streaming/gRPC** | Với hệ thống có long-lived external calls | Không cắt stream hợp lệ, giới hạn concurrency/buffer vẫn có |

### 26.1. Positive control là bắt buộc

Nếu **direct IP test bị timeout**, điều đó có thể do external endpoint không hoạt động hoặc DNS sai, không phải do network policy. Cần một **positive request** tới endpoint hợp lệ, cùng thời điểm, và evidence **deny tại CNI/host firewall** nếu mục tiêu là chứng minh enforcement.

### 26.2. Test theo mọi đường thực tế

Đừng chỉ chạy từ một app Pod:

- Namespace được inject và namespace không được inject.
- Workload sidecar và ambient nếu chạy mixed mesh.
- Node/zone khác nhau, egress gateway replicas và NAT path dự phòng.
- IPv4 và IPv6 nếu cluster dual-stack.
- Workloads có **hostNetwork/privileged/egress proxy overrides** trong phạm vi được phép.
- CI/jobs/bootstrap, metrics agent, controllers có ngoại lệ hợp lệ.
- External partner thật trong giới hạn cho phép **và** test endpoint do tổ chức quản lý.

### 26.3. Tiêu chí chấp nhận

Một outbound boundary đạt yêu cầu khi:

- Chỉ **source identities được phê duyệt** gọi đúng external destinations/protocols/port.
- **Gateway thật được sử dụng**, không chỉ tồn tại trên Kubernetes.
- **External TLS identity và client auth** được kiểm tra đúng hop.
- **Direct IP/DoH/alternate DNS/IPv6/unmeshed path** không bypass khi chính sách yêu cầu.
- NAT/public source IP giữ đúng danh sách partner allowlist trong cả tình huống failover.
- Application workflows giữ **SLO**, gRPC/streaming/long requests hoạt động đúng.
- Logs từ mesh/gateway/firewall/partner đủ chứng minh **source identity → policy → destination → outcome**.
- Có **rollback/incident response/owner** và policy drift monitoring.

## 27. Những nhầm lẫn thường gặp

1. **“Triển khai egress gateway nghĩa toàn bộ outbound đều đi qua gateway.”** Phải kiểm chứng routing và chặn direct bypass.
2. **“REGISTRY_ONLY là firewall chống exfiltration.”** Nó chỉ áp với những luồng qua proxy theo policy của mesh.
3. **“ServiceEntry là allowlist có tính cưỡng chế ở kernel.”** Đây là khai báo service trong mesh registry.
4. **“VirtualService match tức firewall đã thấy flow.”** Config có thể chưa được phân phối hoặc traffic không được intercept.
5. **“Mesh mTLS bảo vệ tất cả data tới SaaS.”** mTLS nội bộ và external TLS là các hop khác nhau.
6. **“TLS passthrough cho gateway đọc HTTP path.”** Gateway thường không giải mã được nội dung HTTP.
7. **“Route theo SNI nghĩa external server được xác thực.”** SNI không phải server certificate verification.
8. **“TLS origination dùng HTTPS nên không cần verify SAN/CA.”** Thiếu identity verification vẫn có rủi ro MITM.
9. **“Partner cần mTLS thì có thể dùng mesh workload cert trực tiếp.”** External partner PKI có thể khác hoàn toàn.
10. **“mTLS authenticated identity tự có quyền mọi destinations.”** Cần authorization theo source principal và scope.
11. **“Source IP của gateway Pod chính là public IP đối tác thấy.”** Cloud NAT/SNAT và node path có thể đổi địa chỉ.
12. **“Gateway HA có hai Pods là đủ.”** Còn NAT zones, DNS, partner allowlist, certs và routes.
13. **“Một gateway có ServiceEntry cho mọi host là zero trust.”** Có thể biến gateway thành open proxy.
14. **“DNS policy chặn được direct IP, DoH và IPv6.”** Cần enforcement ở network layer và kiểm thử.
15. **“Istio AuthorizationPolicy luôn áp trên traffic chưa có mTLS.”** Source principals phụ thuộc identity được xác thực thật.
16. **“NetworkPolicy selector cho gateway luôn hoạt động giống nhau trên mọi CNI.”** Service NAT, endpoint path và hostNetwork có giới hạn provider.
17. **“Chặn mọi egress Pod trừ gateway là đủ.”** Có thể làm hỏng DNS, istiod/xDS/SDS, Kubernetes API hoặc internal dependencies.
18. **“Sidecar injection label có nghĩa Pod chắc chắn đang được intercept.”** Cần kiểm tra runtime và proxy route.
19. **“Ambient mesh dùng đúng mọi CRD và routing như sidecar.”** Hành vi có thể khác theo version/waypoint/ztunnel.
20. **“Gateway API Gateway đồng nghĩa mandatory egress gateway.”** Phải xem controller implementation và path thực.
21. **“Cloud NAT là firewall hiểu API.”** NAT chuyển địa chỉ; không xác thực HTTP business operations.
22. **“Đối tác trả 403 nghĩa gateway AuthorizationPolicy chặn.”** Có thể là API partner auth; phải xác định hop tạo lỗi.
23. **“Không thấy gateway log nghĩa Pod không có traffic.”** Có thể traffic bypass hoặc telemetry coverage khác.
24. **“Tăng timeout sẽ chữa mọi 504.”** Có thể kéo dài in-flight requests và làm gateway quá tải.
25. **“Retry tất cả POST sau timeout là an toàn.”** Cần idempotency và reconciliation.
26. **“Một shared gateway phù hợp mọi tenants và secrets.”** Blast radius và credential custody có thể yêu cầu tách.
27. **“Đã dùng egress gateway thì không cần Kubernetes RBAC/admission.”** Actor có quyền sửa policy có thể phá boundary.
28. **“Một CLI proxy-config output là đủ chứng minh enforcement.”** Cần data-plane flow/deny/partner evidence.
29. **“Nhìn certificate chain hợp lệ là đủ dù hostname sai.”** Cần kiểm tra đúng server identity theo FQDN/SAN.
30. **“Bật TLS interception cho mọi external traffic luôn tăng bảo mật.”** Có thể tạo rủi ro xử lý plaintext, khóa và privacy/compliance.

## 28. Bài tập vận dụng

### Bài 1 — Gateway có thật là outbound boundary?

Cluster có Istio ServiceEntry cho API đối tác, VirtualService định tuyến qua egress gateway, nhưng Pods vẫn có default route tới Cloud NAT không có deny policy. Có thể kết luận “mọi outbound bắt buộc qua gateway” không?

**Gợi ý:** không. Cần network enforcement chặn direct egress và negative tests từ **unmeshed Pod, direct IP, alternate DNS, IPv6** theo threat model.

### Bài 2 — mTLS đã bảo vệ external TLS chưa?

Workload mTLS với egress gateway thành công nhưng gateway gọi HTTP plaintext tới partner qua mạng ngoài. Có thể coi “mTLS end-to-end” không?

**Gợi ý:** không. Mesh mTLS bảo vệ một hop; phải thêm external TLS hoặc một transport bảo vệ tương ứng, xác minh danh tính partner và tránh plaintext trên đoạn không tin cậy.

### Bài 3 — Passthrough có kiểm tra HTTP path được không?

Gateway route HTTPS traffic theo SNI nhưng security team muốn chỉ cho **GET /v1/invoices** và chặn **POST /v1/admin**. Với TLS passthrough, gateway có đủ thông tin không?

**Gợi ý:** thường không. Cần application/partner-side authorization hoặc thiết kế L7 termination/re-encryption có phê duyệt để kiểm tra HTTP method/path; đồng thời lưu ý dữ liệu plaintext/PKI.

### Bài 4 — Source principal và điểm thực thi

Một AuthorizationPolicy có allowlist source principal **payments/invoice**, nhưng gateway nhận TCP traffic không có mTLS peer identity. Có nên dựa vào header “x-user: payments/invoice” tự gửi không?

**Gợi ý:** không. Cần xác minh mTLS peer identity từ mesh, source policy và trust domain; header client tự khai không phải chứng cứ identity đáng tin.

### Bài 5 — NAT public IP không ổn định

Gateway có hai replicas ở hai zones. Khi failover, partner chỉ chấp nhận IP A và từ chối IP B. Biện pháp đúng ở lớp nào?

**Gợi ý:** kiểm tra cloud NAT/routes, fixed public IP inventory và partner allowlist cho mọi HA paths; không nới AuthorizationPolicy mesh khi lỗi nằm ở external source IP.

### Bài 6 — HTTPS external nhưng cert không verify

Gateway TLS origination dùng certificate validation bị bỏ qua để “giải quyết lỗi DNS”. Điều gì còn thiếu?

**Gợi ý:** xác minh CA chain và SAN đúng hostname, SNI và resolver; kết nối được mã hóa nhưng chưa chắc đến đúng peer được tin cậy.

### Bài 7 — Partner chậm làm gateway bão hòa

Partner API chậm từ 200 ms lên 3 giây, traffic logic vẫn 500 requests/s, clients và proxy đều retry. Vì sao số in-flight tăng và phải kiểm soát gì?

**Gợi ý:** theo Little's Law, latency dài hơn làm tăng concurrency khi throughput giữ; retries khuếch đại tải. Cần retry budget, bounded queues, circuit breaker, deadlines, partner quota và capacity testing.

### Bài 8 — NetworkPolicy có chặn hoàn toàn outbound không?

Một NetworkPolicy chỉ cho Pods gọi gateway TCP 15443 và DNS UDP/TCP 53. Sau rollout, một số workloads không nhận được cert từ istiod và không khởi động thành công. Lỗi thiết kế nào có thể xảy ra?

**Gợi ý:** chưa kiểm kê control-plane/xDS/SDS/CA/internal dependencies, selector và Service NAT behavior. Phải bổ sung ngoại lệ hẹp, kiểm thử positive trước khi enforce, không mở tất cả egress.

### Bài 9 — Shared gateway giữa tenants

Payments và Analytics dùng cùng egress gateway. Gateway có route đến cả payment partner và reporting SaaS, và mọi mesh identity đều được phép vào gateway. Cách nào ngăn Analytics gọi payment partner?

**Gợi ý:** gắn **source principal → permitted destination/protocol/credential** vào policy thực thi hoặc tách gateways khi cần; dùng independent partner credentials và kiểm thử unauthorized source.

### Bài 10 — Thiết kế threat → control → evidence

Cho kiến trúc **Kubernetes + Istio + WAF/Ingress + Service A + Service B + egress gateway + Cloud NAT/Firewall + partner API**. Hãy lập ma trận:

1. Workloads nào thực sự được quyền outbound? Theo **ServiceAccount/identity** nào?
2. Đích nào được allow theo **hostname, IP/port, protocol** và business purpose?
3. Mesh mTLS được thực hiện giữa những hop nào, **external TLS** ai là client?
4. Nếu dùng TLS passthrough, đâu là những **L7 policies không thể thực thi** tại gateway?
5. **Kubernetes NetworkPolicy/CNI, host và cloud firewall** ngăn direct bypass như thế nào?
6. Những Pod **không inject, hostNetwork, IPv6, DoH, direct IP** nào cần negative tests?
7. **Gateway scale/failover/NAT IP/partner allowlist** đáp ứng SLO ra sao?
8. Làm thế nào correlate **workload principal, gateway log, cloud NAT flow và partner transaction ID** mà không lộ Secrets?

**Gợi ý:** bắt đầu từ **trust boundary + flow matrix**, ghi rõ điểm thực thi thật, rồi thiết kế **positive/negative tests** cho cả đường chính và đường bypass.

## 29. Runbook ứng phó sự cố outbound boundary

Khi phát hiện lưu lượng đi vòng egress gateway, identity bị lạm dụng, partner credential bị lộ hoặc gateway bị chiếm quyền, cần **xác định đường đi thực và phạm vi tác động trước khi sửa policy**. Không mặc định xóa Gateway/ServiceEntry hoặc tắt toàn mesh, vì hành động đó có thể làm gián đoạn thanh toán, hệ thống nhận dữ liệu và các dependencies sống còn.

### Giai đoạn 1 — Xác nhận sự kiện và thu evidence

1. Ghi **timestamp UTC, cluster/namespace/Pod/ServiceAccount, external destination, protocol/port, source node/zone**.
2. Thu **mesh proxy/gateway route, AuthorizationPolicy decision, observed source principal và mTLS peer identity** nếu có.
3. Đối chiếu **host/CNI/NetworkPolicy logs, cloud NAT/firewall flows, partner logs** để xác định traffic qua gateway hay direct.
4. Kiểm tra **Kubernetes/cloud IAM audit** xem ai đổi ServiceEntry, VirtualService, DestinationRule, gateway Deployment, NetworkPolicy, sidecar injection hoặc VPC route.
5. Xác định **credential/Secret/client cert/token** đã được sử dụng hoặc có nguy cơ bị sao chép.
6. Bảo quản những request IDs, transaction IDs và network session IDs cần thiết; **không ghi raw secrets vào incident ticket**.

### Giai đoạn 2 — Containment theo loại sự cố

| Loại sự cố | Containment ưu tiên | Sai lầm cần tránh |
| --- | --- | --- |
| **Pod bypass gateway** | Áp/khôi phục CNI/host/cloud direct-egress deny có scope, kiểm tra mesh enrollment | Chỉ thêm ServiceEntry rồi nghĩ đã chặn bypass |
| **Untrusted principal dùng gateway** | Thu hẹp inbound identity allowlist, kiểm tra trust domain và mTLS | Mở gateway cho mọi principal để application chạy |
| **Partner credential bị lộ** | Revoke/rotate partner token/cert, thu hẹp permissions, điều tra downstream operations | Chỉ đổi gateway route nhưng giữ credential bị lộ |
| **TLS peer verification bị tắt** | Khôi phục CA/SAN checks, dừng route không đáng tin theo risk decision | Giữ insecure mode lâu dài vì “TLS đã mã hóa” |
| **Gateway thành open proxy** | Hạn chế destination allowlist và gateway network egress | Chỉ chặn một IP khi nhiều alternate DNS/CDN/IPv6 paths |
| **Gateway overload/partner outage** | Retry budget, concurrency/queue caps, HA/failover theo SLO | Bật direct Internet fallback hoặc tăng mọi timeout vô hạn |
| **NAT IP drift** | Khôi phục approved egress path, xác minh partner allowlist từng zone | Nới RBAC/mTLS policy vì partner reject source IP |
| **Policy change trái quyền** | Giới hạn IAM/RBAC CI credentials, khôi phục cấu hình được phê duyệt | Xóa audit hoặc config trước khi thu đủ evidence |

### Giai đoạn 3 — Xác định phạm vi và khôi phục

1. Dựng **timeline route/identity/credential/policy changes** và thời gian policy đã yếu.
2. Phân tách **potential exposure, observed network connections và confirmed data access/exfiltration** theo bằng chứng.
3. Xác minh các **routes khác/secondary gateways/other clusters/IPv6/DoH/hostNetwork/privileged workloads** không còn tạo bypass.
4. Nếu Secrets bị lộ, xét **credential rotation ở external partner và downstream systems**, không chỉ restart Pod.
5. Restore **approved configurations** qua IaC/GitOps, kiểm thử mTLS identity và đúng TLS peer verification.
6. Chạy **positive tests** cho business operations, **negative tests** cho unauthorized principal/destination và **failover tests** trong scope được phép.
7. Giám sát **gateway policy rejects, direct-egress denies, partner transaction logs, API error rates và NAT IP** sau sửa.

### Giai đoạn 4 — Bàn giao và phòng ngừa tái diễn

Một báo cáo sự cố nên ghi:

~~~text
Case ID, severity, time window (UTC):
Cluster/mesh mode/version, affected namespaces/identities:
Expected egress path and enforcement points:
Observed path, source/destination/protocol:
Gateway route/policy ID and certificate/trust status:
CNI/host/cloud firewall and NAT evidence:
Partner-side source IP/auth/application evidence:
IAM/RBAC/config actor and change revision:
Containment/credential rotation/recovery steps:
Positive/negative tests and residual risks:
Owners, expiry of temporary exceptions, follow-up deadlines:
~~~

**Điều kiện kết thúc:** outbound flows hợp lệ đã phục hồi theo SLO, không còn đường bypass ngoài policy, credentials bị lộ đã được xử lý theo phạm vi, audit đủ phục vụ điều tra và mọi exception tạm thời đều có owner/thời hạn.

## 30. Checklist triển khai dành cho Network, Platform và Security

| Câu hỏi | Evidence cần có |
| --- | --- |
| Egress gateway được chọn có đúng implementation/mode/version? | Mesh inventory, gateway Deployment/Pod, Istio/Gateway API capability |
| Source workloads thuộc identity và trust domain nào? | Namespace/SA/mesh cert inventory và access review |
| Có route rõ từng hostname/port/protocol ra gateway? | Effective sidecar/ztunnel/waypoint/gateway config |
| Đã phân biệt mTLS mesh và external TLS/mTLS? | Hop-by-hop TLS diagram và certificate tests |
| Bên nào thực hiện external server CA/SAN validation? | TLS mode config, negative wrong-CA/SAN tests |
| ServiceEntry có bị hiểu sai thành enforcement firewall? | Routing/network policy design review |
| Gateway inbound chỉ cho principals được phê duyệt? | AuthorizationPolicy và authn/mTLS logs |
| Gateway có chỉ được gọi destinations được duyệt không? | Egress route policy, network firewall, negative tests |
| Pod unmeshed/hostNetwork/privileged có bypass không? | Admission inventory, CNI/host negative tests |
| DNS, DoH, direct IP và IPv6 có đường ngoài policy không? | Resolver/firewall audit, IPv4/IPv6 test evidence |
| Workload Pod cần DNS/xDS/SDS/CA/API/metrics nào? | Dependency inventory và positive bootstrap tests |
| Kubernetes CNI có thực thi NetworkPolicy trên đường mong đợi? | CNI capability matrix và flow/deny logs |
| Gateway/nodes đi qua approved egress firewall/NAT? | Effective routes, NAT flow logs, public IP evidence |
| Public NAT IP có ổn định qua zone/failover? | Partner allowlist và failover report |
| TLS client credentials/API tokens được tách theo partner/tenant? | Secret custody, scopes, rotation audit |
| HTTP/gRPC/streaming deadlines và retries phù hợp? | Latency/error/retry budget tests |
| Gateway HA, capacity, conntrack/SNAT ports đã sizing? | Load test, FD/CPU/RAM, NAT and partner SLO evidence |
| Gateway failure có direct fail-open ngoài ý định không? | Fault injection trong staging và negative tests |
| Logs có source identity, route, policy decision và partner outcome? | Sanitized audit sample và trace correlation |
| RBAC/GitOps có ngăn sửa policy ngoài phê duyệt? | RBAC checks, PR approval và IaC guardrails |
| Mỗi exception có owner, expiry, review và rollback? | Change record, residual risk, monitoring |

## 31. Tổng kết

**Egress gateway và outbound boundary** là cách định hình và kiểm soát lưu lượng từ workloads trong service mesh tới mạng/dịch vụ ngoài miền tin cậy. Một gateway đúng chức năng giúp tập trung **workload identity authorization, routing, TLS handling, logging, quotas và external network egress**. Tuy nhiên, **gateway có mặt không có nghĩa gateway là đường bắt buộc**: workloads thiếu proxy, hostNetwork/privileged, IP direct, DNS khác hoặc IPv6 có thể tạo đường bypass nếu CNI/host/cloud firewall chưa thực thi chính sách độc lập.

Trong mesh mTLS cần tách rõ **hai tầng trust**: mesh **mTLS giữa workloads/proxies và egress gateway**, rồi **TLS/mTLS tới external partner**. **TLS passthrough** bảo vệ end-to-end TLS theo client nhưng không cung cấp HTTP contents cho gateway; **TLS origination** đặt trách nhiệm xác minh external certificate, hostname và client credentials lên gateway. **SNI, DNS, ServiceEntry hay REGISTRY_ONLY** đều không thay cho **peer identity verification và network-layer enforcement**.

Trong hệ thống **SECURITY_NETWORK_SECURITY**, một outbound boundary đáng tin cậy phải chứng minh được bằng **effective proxy config, workload identity/mTLS, Kubernetes/CNI/host/cloud firewall, NAT logs, TLS validation, partner audit và positive/negative tests** rằng **chỉ workloads được phép gọi đúng external destinations theo đúng đường**, **mọi direct/bypass path nằm ngoài policy bị chặn**, và **gateway vẫn có HA, capacity, rollback, credential rotation và telemetry đủ để xử lý khi đối tác hoặc mesh gặp sự cố**.
