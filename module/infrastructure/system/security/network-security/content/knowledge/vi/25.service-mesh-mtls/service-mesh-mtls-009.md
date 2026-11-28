# Ingress gateway và public exposure

**Ingress gateway** là điểm tiếp nhận lưu lượng đi **từ bên ngoài vào** một hệ thống dịch vụ, thường thực hiện các chức năng như lắng nghe cổng public, chọn backend theo tên miền/đường dẫn, xử lý TLS, chuyển tiếp request và ghi log. Trong kiến trúc **service mesh**, gateway còn có thể là workload hoặc proxy được tích hợp với mặt phẳng điều khiển mesh để sử dụng chính sách routing, danh tính workload và **mutual TLS (mTLS)** trên các chặng nội bộ.

**Public exposure** mô tả những cách một tài nguyên có thể được truy cập từ mạng công cộng hoặc những mạng không cùng ranh giới tin cậy. Một public load balancer được thiết kế đúng có thể là cổng vào hợp lệ. Ngược lại, một **NodePort, LoadBalancer, public IPv6 listener, origin IP, đường VPN/peering đối tác hoặc route cũ** có thể tạo **đường vào ngoài dự kiến**, đi vòng qua WAF, gateway hoặc chính sách xác thực.

Ví dụ, doanh nghiệp muốn công bố API đơn hàng tại **https://api.example.test/orders**. Client gửi HTTPS tới public load balancer, traffic được chuyển đến mesh ingress gateway, gateway áp routing/những kiểm tra được cấu hình rồi gửi tới Orders API. Nếu mesh dùng mTLS giữa gateway và Orders, danh tính workload và tính bảo mật kênh có thể được bảo vệ ở chặng đó. Nhưng điều này **không tự khẳng định client Internet đã được xác thực** hoặc **đơn hàng nào được phép xem**. Ngoài ra, nếu Orders API vẫn có public LoadBalancer riêng, client có thể đi thẳng vào backend mà không qua gateway.

Trong chương **Service mesh và mTLS** của module **SECURITY_NETWORK_SECURITY**, ingress gateway liên kết trực tiếp với bảo mật TLS/PKI, API authorization, phân đoạn mạng, firewall/WAF, VPN, DNS, IDS/IPS và cloud security. Mục tiêu của bài là giúp bạn **vẽ đúng đường đi, xác định điểm thực thi thật, giới hạn public exposure và chứng minh bằng kiểm thử rằng các luồng bypass bị chặn**.

> **Nguyên tắc cốt lõi:** **Một gateway được bảo vệ không đồng nghĩa mọi backend đều chỉ truy cập được qua gateway.** Muốn ranh giới thực sự an toàn, cần đồng thời kiểm soát **exposure, routing, TLS, identity, authorization và network reachability** trên mọi đường có thể vào hệ thống.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **mesh ingress gateway**, Kubernetes **Service type LoadBalancer/NodePort**, **Ingress controller**, **Gateway API**, **API gateway**, **WAF** và **egress gateway**.
2. Phân tích trust boundaries tại **Internet/client → CDN/WAF/LB → ingress gateway → mesh workload → data**.
3. Hiểu sự khác biệt giữa **TLS termination, TLS passthrough, TLS origination/re-encryption** và **mTLS** trên các chặng.
4. Thiết kế **public hostname, SNI/Host routing, certificate lifecycle**, backend protection và host/path allowlist.
5. Sử dụng khái niệm **GatewayClass, Gateway, HTTPRoute, listener, allowedRoutes, backendRefs, ReferenceGrant** của Kubernetes Gateway API theo đúng phạm vi.
6. Giải thích cơ chế **mesh mTLS gateway-to-workload** và vì sao không thể đồng nhất nó với **client-to-gateway mTLS**.
7. Áp dụng **authentication và authorization** tại gateway/backend, JWT issuer/audience/scope, workload identity và least privilege.
8. Bảo vệ **client IP provenance** qua trusted proxy chain và tránh giả mạo forwarded headers.
9. Phát hiện **bypass qua backend public IP, NodePort, alternate LoadBalancer, IPv6, DNS hoặc hybrid routes**.
10. Thiết kế **NetworkPolicy/cloud firewall, WAF/DDoS, logging, HA, IaC, incident runbook** và bộ kiểm thử positive/negative.

## 2. Ingress, egress và những loại gateway dễ bị nhầm

| Thuật ngữ | Chức năng khái quát | Lưu ý bảo mật |
| --- | --- | --- |
| **Ingress gateway (mesh)** | Proxy tiếp nhận traffic từ ngoài mesh vào các workload được định tuyến | Có thể tích hợp mTLS, route policy, telemetry; tính năng phụ thuộc sản phẩm |
| **Egress gateway (mesh)** | Điểm trung gian cho traffic từ mesh ra mạng/dịch vụ bên ngoài | Không tự kiểm soát mọi egress nếu tồn tại đường bypass |
| **Kubernetes Ingress resource** | API cũ cho HTTP(S) routing khi có Ingress controller | Không tự hoạt động nếu controller thiếu/không xử lý |
| **Kubernetes Gateway API** | Họ tài nguyên chuẩn hóa vai trò infra/traffic routing | Cần Gateway controller cụ thể; không mặc nhiên là service mesh |
| **Ingress controller** | Triển khai routing/edge proxy cho Ingress hoặc tính năng tương đương | Nhiều sản phẩm có behavior và CRDs riêng |
| **Cloud LoadBalancer Service** | Công bố hoặc cân bằng traffic theo cơ chế cloud/controller | Có thể tạo external IP và listener công khai |
| **NodePort Service** | Đưa cổng Service ra network của node theo cách triển khai | Có thể tạo alternate ingress path; cần kiểm tra node firewall |
| **API gateway** | Routing, rate limiting, API authentication, transformations, governance | Có thể độc lập hoặc kết hợp mesh gateway |
| **WAF** | Kiểm tra HTTP(S) tại nơi có thể đọc request | Không bảo vệ TCP/UDP bất kỳ hoặc backend bypass |

### 2.1. Không có ánh xạ bắt buộc một-một

Một hệ thống có thể dùng cùng một data-plane proxy để thực thi **Ingress Gateway + API Gateway + WAF-like features**, hoặc dùng nhiều thành phần độc lập. Tương tự, một Kubernetes Gateway API controller có thể cấu hình **proxy mesh gateway** trong một số môi trường nhưng ở môi trường khác lại cấu hình cloud load balancer.

**Không suy từ tên tài nguyên Gateway rằng nó hỗ trợ JWT auth, WAF, mTLS, gRPC, IP filtering hay access logging.** Xác minh controller, phiên bản, các policy extensions và tính năng đang bật.

### 2.2. Public exposure là thuộc tính của đường đi

Một backend có Service type **ClusterIP** thường không tự tạo endpoint Internet như một external LoadBalancer, nhưng nó có thể vẫn reachable từ nhiều nguồn qua:

- Pod khác trong cluster với NetworkPolicy rộng.
- NodePort/Ingress/LoadBalancer khác trỏ vào backend.
- VPN, private interconnect, peering hoặc bastion path.
- Port-forward theo quyền Kubernetes API.
- Host-networked workloads hoặc các điểm quản trị nội bộ.

Vì vậy cần phân biệt **public Internet exposure**, **private-but-broad reachability** và **privileged administrative access**. Một private endpoint không đồng nghĩa đã an toàn với nguồn nội bộ bị xâm nhập.

## 3. Luồng điển hình: từ client Internet vào service mesh

~~~mermaid
flowchart TB
    U["Internet client"] -->|"HTTPS / TLS"| EDGE["DNS → CDN/WAF/DDoS protection (nếu dùng)"]
    EDGE -->|"Approved LB listener"| LB["Cloud LoadBalancer / reverse proxy"]
    LB -->|"TLS passthrough hoặc TLS từ LB tới gateway"| GW["Mesh Ingress Gateway"]
    GW -->|"Internal mesh transport: mTLS nếu được cấu hình/enforce"| ORD["Orders workload / sidecar hoặc ambient"]
    ORD -->|"Service auth + app authorization"| DB[("Orders data")]
    GW -. "Access/route/TLS logs" .-> SIEM["Security observability"]
    ORD -. "Application policy/audit" .-> SIEM
    LB -. "Exposure/LB logs" .-> SIEM
    BY["Unapproved direct LB / NodePort / IPv6"] -. "Phải chặn đường bypass" .-> ORD
~~~

Đường đi này là **mô hình logic**. Nơi terminate TLS và cách mesh thiết lập mTLS thay đổi theo nền tảng. Nếu CDN/LB terminate TLS, phía sau nó phải **xác minh upstream bằng TLS hoặc cơ chế bảo vệ được phê duyệt**; không được tự gọi một kết nối plaintext là end-to-end encryption.

### 3.1. Những điểm quyết định

| Chặng | Câu hỏi cần trả lời | Bằng chứng kiểm tra |
| --- | --- | --- |
| DNS → public edge | Domain trả những IP nào (A/AAAA), có origin khác không? | DNS/asset inventory, IPv4/IPv6 reachability |
| Internet → CDN/LB | Cổng nào public, TLS certificate nào được phục vụ? | Cloud listeners, certificate checks |
| CDN/LB → gateway | TLS terminate ở đâu, proxy nào được tin, source IP ra sao? | Config, TLS validation, trusted proxy settings |
| Gateway listener → route | Host/SNI/path nào khớp, route lạ có bị từ chối? | Gateway status, access logs, negative routes |
| Gateway → backend | Backend nào, port nào, TLS/mTLS identity thế nào? | Mesh config, workload cert identity, telemetry |
| Backend → dữ liệu | Caller/tenant/object nào được quyền? | API authorization, database policy/audit |
| Đường phụ | Có Service public, NodePort, IPv6, peering hoặc port-forward không? | Inventory và negative tests có giới hạn |

### 3.2. Gateway là điểm vào, không tự là nơi cấp mọi quyền

Gateway có thể xác thực access token hoặc TLS client certificate, nhưng Orders API vẫn cần quyết định **người gọi có được đọc đơn hàng số 42 của tenant A hay không**. **Network reachability**, **workload authentication** và **business authorization** phải được xem là các tầng khác nhau.

## 4. Public exposure: phân loại và kiểm kê

### 4.1. Những đối tượng cần rà soát

1. **Public DNS records:** A/AAAA/CNAME của hostname và aliases cũ.
2. **Cloud external LoadBalancers:** public IPv4/IPv6, listeners, target groups, health endpoints.
3. **Kubernetes Services:** type LoadBalancer, NodePort, ExternalIPs và các annotations liên quan.
4. **Ingress/Gateway routes:** hostnames, path rules, listener ports, TLS settings.
5. **Node public interfaces:** hostNetwork, hostPort, kube-proxy/CNI NodePort paths.
6. **Origins ngoài CDN/WAF:** alternate hostname, stale load balancer, direct public address.
7. **Cross-cluster/region:** failover, disaster recovery và test endpoints chưa gỡ.
8. **VPN/partner/peering:** các nguồn không public nhưng có độ tin cậy thấp hơn mesh nội bộ.
9. **Management surfaces:** admin endpoints, dashboards, metrics, debug và control-plane access.
10. **Cloud firewall/NetworkPolicy:** nguồn, đích, IPv4/IPv6, rule priority và phạm vi gắn policy.

### 4.2. Phân loại exposure theo ý định

| Đối tượng | Mức truy cập dự định | Điều kiện |
| --- | --- | --- |
| Public gateway listener TCP 443 | Được công bố | TLS, routing, WAF/DDoS theo rủi ro, auth |
| Gateway management/admin port | Không public | Private control plane, RBAC/MFA/PAM |
| Orders API backend port | Chỉ từ gateway/mesh sources được phép | Network segmentation, mTLS, API auth |
| Database | Chỉ từ workload cần thiết | NetworkPolicy, DB TLS/authz, không public |
| Health endpoint | Chỉ phù hợp nhu cầu LB/monitoring | Giới hạn dữ liệu, nguồn và port |
| Staging/test gateway | Không public trừ có phê duyệt | Auth riêng, không kết nối nhầm production |
| Mesh telemetry/control plane | Đường quản trị được bảo vệ | RBAC, certificate/secret management, network policy |

**Không phải mọi listener gắn 0.0.0.0/0 hoặc ::/0 đều là lỗi**: một public gateway bắt buộc cần nhận traffic từ mạng ngoài. Vấn đề là **đối tượng nào được công bố, cổng nào, chính sách nào, nguồn đến đâu và backend có đường bypass không**.

### 4.3. Tại sao “không có public IP trên Pod” chưa đủ?

Pod có thể không có public IP nhưng **Service LoadBalancer/NodePort** vẫn công bố nó qua node hoặc cloud LB. Một Backend Service type ClusterIP cũng có thể được proxy qua đường khác. Để khẳng định không public, phải kiểm tra **toàn bộ graph ingress**, không chỉ thuộc tính IP của Pod.

## 5. Các ranh giới TLS: terminate, passthrough và re-encrypt

TLS bảo vệ dữ liệu trên **một kết nối cụ thể**. Một kiến trúc có nhiều proxies có thể có **nhiều phiên TLS độc lập**, mỗi phiên kết thúc tại một điểm khác nhau.

### 5.1. TLS termination tại ingress gateway

Client tạo TLS connection với gateway (trực tiếp hoặc qua LB pass-through). Gateway giữ chứng thư/khóa liên quan server name, giải mã HTTP, sau đó áp route/auth/rate limits theo tính năng, rồi mở **kết nối upstream riêng** tới backend.

~~~text
Internet client == HTTPS/TLS ==> Ingress gateway == TLS/mTLS hoặc kênh khác ==> Backend
                       TLS session #1                   TLS session #2
~~~

Đây là **hai phiên độc lập**. Cần thiết kế TLS/mTLS trên chặng gateway→backend thay vì tin rằng việc terminate TLS ở gateway đã mã hóa mọi đoạn sau.

### 5.2. TLS passthrough

Với **TLS passthrough**, gateway/LB chuyển tiếp traffic TLS mà không giải mã nội dung ứng dụng. Một số triển khai có thể phân tuyến dựa trên **SNI hoặc thuộc tính kết nối sẵn có**.

Giới hạn:

- Proxy không thấy đầy đủ **HTTP path, headers, request body** trong kết nối TLS được chuyển thẳng.
- Không thể mặc nhiên áp **JWT header verification, HTTP WAF, HTTP method/path rules** ở điểm không giải mã.
- **Certificate và TLS endpoint identity** thuộc backend trực tiếp nhận TLS.
- TLS passthrough **không tự tạo mTLS giữa gateway và backend**, vì gateway không phải TLS peer của phiên passthrough.
- Các cơ chế mã hóa metadata mới hoặc đặc điểm protocol có thể hạn chế SNI-based routing theo khả năng hỗ trợ.

### 5.3. TLS origination/re-encryption

Proxy có thể nhận HTTP/TLS từ client, sau đó **tạo phiên TLS mới với upstream**, xác minh chứng thư/danh tính upstream. Trong mesh, phiên bên trong có thể sử dụng **workload mTLS** khi gateway tham gia mesh và policy điều khiển đúng.

**Không được dùng “TLS re-encryption” như lý do tắt hostname/certificate verification**. Gateway cần tin đúng CA/trust domain, xác minh tên hoặc workload identity và có chính sách certificate rotation.

### 5.4. So sánh

| Mode | Ai terminate client-facing TLS? | Gateway đọc được HTTP? | Kiểm soát bắt buộc bổ sung |
| --- | --- | --- | --- |
| **Gateway TLS termination** | Gateway | Có, nếu protocol phù hợp | Auth, WAF/L7 nếu dùng, upstream TLS/mTLS |
| **LB TLS termination → gateway HTTPS** | LB trước, gateway có phiên TLS riêng | Gateway có thể đọc HTTP sau khi terminate phiên sau | Xác minh upstream LB→gateway, trusted proxy chain |
| **TLS passthrough** | Backend đích | Không đọc HTTP tại gateway passthrough | Backend TLS/auth, SNI routing giới hạn |
| **mTLS client→gateway** | Gateway, với xác minh client cert | Có sau termination | Client CA/identity binding, API authz |
| **Gateway→mesh mTLS** | Gateway và mesh endpoint/proxy là hai TLS peers | Gateway có thể đã đọc request trước đó | Mesh identity, policy và authorization riêng |

## 6. mTLS: phân biệt client–gateway và gateway–workload

**Mutual TLS (mTLS)** yêu cầu hai TLS peers xác minh danh tính chứng thư của nhau theo trust policy; điều này khác với TLS một chiều nơi client thường chỉ xác minh server. Trong service mesh, mTLS nội bộ thường dùng **workload certificates** và danh tính dịch vụ do mesh CA/identity plane quản lý.

### 6.1. mTLS của người gọi Internet

Nếu API đối tác yêu cầu **client certificate**, gateway có thể cấu hình **client certificate authentication** tại public listener. Gateway cần:

1. Chứng thư server đúng public hostname.
2. Trust anchors cho client certs được cấp phép.
3. Kiểm tra certificate chain, validity, profile và client identity mapping.
4. Quản lý revocation/rotation theo sản phẩm và chính sách.
5. Ánh xạ client identity sang quyền cụ thể, không mặc định mọi chứng thư hợp lệ đều được gọi mọi API.

Nhiều ứng dụng Internet sử dụng **TLS server authentication + OAuth/OIDC/JWT** thay vì client-certificate mTLS. Không có một lựa chọn duy nhất bắt buộc cho mọi client.

### 6.2. mTLS giữa gateway và backend

Trong mesh, ingress gateway có thể gửi traffic tới backend qua **mTLS được mesh quản lý**. Backend/sidecar hoặc dataplane tương ứng cần xác minh **workload principal của gateway**, hoặc chính sách nhận diện phù hợp trust domain.

**STRICT mTLS** trên backend, nếu được mesh hỗ trợ và thực thi đúng, thường yêu cầu kết nối mesh inbound được xác thực bằng mTLS. Nhưng:

- Nó **không tự xác thực user Internet**.
- Nó **không tự bảo đảm request chỉ đến từ một ingress gateway cụ thể** nếu nhiều workloads khác có danh tính mTLS hợp lệ mà policy chưa giới hạn.
- Nó **không tự cấp quyền đọc/ghi dữ liệu**.
- Nó **không thay cloud firewall/NetworkPolicy** ở các đường không được mesh bảo vệ hoặc khi có lỗi triển khai.

### 6.3. Ví dụ hai principal khác nhau

~~~text
External client identity:
  - Client certificate của đối tác (nếu có), hoặc
  - User/workload access token đã được xác minh tại gateway/API.

Internal mesh peer identity:
  - Mesh workload identity của ingress gateway, ví dụ
    spiffe://cluster.example.test/ns/edge/sa/public-ingress
  - Mesh workload identity của Orders API, ví dụ
    spiffe://cluster.example.test/ns/payments/sa/orders-api
~~~

Hai danh tính khác nhau có mục đích riêng. **Workload identity của gateway không tự đại diện user Internet**; phải chuyển tiếp ngữ cảnh user qua cơ chế **được xác thực và được backend tin có kiểm soát**, hoặc backend tự xác thực credential của user.

### 6.4. Trust domain và liên cụm

Khi mesh chạy nhiều clusters/regions, cần kiểm tra **trust domain, mesh CA/certificate chain, federated identity, gateway peering và policy cross-cluster**. Một service identity cùng tên namespace/service account **không nhất thiết có cùng trust level** ở những clusters khác nhau.

## 7. Certificate lifecycle và TLS vận hành

Một ingress gateway có thể phụ thuộc nhiều loại chứng thư:

| Loại | Dùng cho | Owner/điểm cần kiểm soát |
| --- | --- | --- |
| **Public server certificate** | HTTPS hostname client truy cập | Gateway/edge operator, DNS ownership, CA issuance |
| **External client certificate** | Client→gateway mTLS khi có | Partner/client CA, identity mapping/revocation |
| **Mesh workload certificate** | Gateway→mesh workload mTLS | Mesh identity plane/CA, workload identity |
| **Gateway→external backend certificate** | Kết nối upstream ngoài mesh | Backend CA/trust và hostname verification |
| **Gateway admin/control-plane certificate** | Quản trị hoặc xDS/control plane theo sản phẩm | Mesh/platform operation, rotation và access control |

### 7.1. Bí mật khóa và nơi lưu trữ

- Chỉ cho service account/controller được phê duyệt đọc **TLS key material**.
- Sử dụng secret management/KMS/certificate controller phù hợp.
- Bảo vệ quyền **thay Secret/chứng thư**: có thể làm chuyển traffic sang một danh tính khác.
- Bật audit thay Secret/cert, thời gian hiệu lực và expiry alert.
- Không in private keys vào logs, CI output hoặc ticket.

### 7.2. Chuyển tiếp TLS không phải end-to-end theo nghĩa nguyên phiên

Nếu CDN terminate TLS rồi dùng một phiên TLS khác tới gateway, dữ liệu được bảo vệ theo **các chặng** nhưng không tồn tại một TLS session duy nhất từ client tới backend. Cần mô tả **chặng nào được giải mã và bởi bên nào** để đáp ứng threat model/tuân thủ.

### 7.3. Quy trình xoay chứng thư

1. Kiểm kê certificate expiry và hostname SAN.
2. Đảm bảo chủ sở hữu domain/DNS, issuer, Secret và gateway listener chính xác.
3. Cấp mới theo CA/trust profile được duyệt.
4. Đưa certificate vào gateway qua cơ chế kiểm soát thay đổi.
5. Test HTTPS/SNI, chain, OCSP/revocation khi kiến trúc dùng, client compatibility.
6. Giám sát handshake failures sau rollout, giữ rollback phù hợp.
7. Thu hồi credential cũ theo vòng đời đã phê duyệt.

### 7.4. TLS phiên bản và cipher policy

Ưu tiên **phiên bản TLS hiện đại** và cipher suites được tổ chức cho phép, cân nhắc khả năng tương thích với clients thực. **Không bật SSL/TLS cũ hoặc tắt certificate verification** chỉ để che lỗi hostname. HTTP Strict Transport Security (HSTS) có thể phù hợp cho một số public domains, nhưng cần đánh giá **subdomain coverage, preload và khả năng rollback** trước khi bật ở phạm vi rộng.

## 8. Kubernetes Gateway API: phân chia trách nhiệm

**Kubernetes Gateway API** cung cấp họ tài nguyên để tách người vận hành hạ tầng/gateway và người định nghĩa routes. Những đối tượng nền tảng thường gặp:

| Tài nguyên | Vai trò | Điểm kiểm soát |
| --- | --- | --- |
| **GatewayClass** | Chọn implementation/controller cung cấp Gateway | Ai được tạo/duyệt GatewayClass, tính năng controller |
| **Gateway** | Khai báo listeners, port/protocol/hostname, certificate refs và route attachment | Public exposure, TLS listener, allowedRoutes |
| **HTTPRoute** | Quy tắc route HTTP theo hostname/matches/backendRefs | Chủ sở hữu route, backend, filters, match precedence |
| **TLSRoute/TCPRoute/GRPCRoute** | Các route types phù hợp protocol và mức hỗ trợ của controller | Không mặc định controller hỗ trợ tất cả |
| **ReferenceGrant** | Cho phép một số tham chiếu qua namespace boundaries | Đặc biệt quan trọng với backendRefs khác namespace |
| **Gateway status/conditions** | Controller phản hồi tài nguyên đã được chấp nhận/programmed hay chưa | Accepted/Programmed/ResolvedRefs theo phiên bản và resource |

### 8.1. Gateway và Route là hai phạm vi ủy quyền khác nhau

Một đội **platform** có thể quản lý Gateway/listener/TLS, trong khi đội **ứng dụng** chỉ quản lý HTTPRoute trong những namespaces/hostnames được cấp. **allowedRoutes** giúp chủ sở hữu Gateway giới hạn nguồn route được gắn vào listener.

**allowedRoutes không thay authentication/authorization của request HTTP**. Nó là ranh giới **cấu hình control plane**.

### 8.2. Cross-namespace backend references

Khi HTTPRoute muốn tham chiếu Service ở **namespace khác**, nhiều trường hợp cần **ReferenceGrant ở namespace của đối tượng đích** để cho phép reference cụ thể. Không nên xem cross-namespace references là quyền mặc định của mọi route author.

**ReferenceGrant không phải firewall và không tự cho user quyền đọc dữ liệu**. Nó chỉ cho phép một tham chiếu cấu hình giữa các tài nguyên theo Gateway API rules.

### 8.3. Gateway API không đồng nghĩa mesh mTLS

Một Gateway với **HTTPS listener** mới chỉ mô tả phía nhận request. Việc **Gateway→backend** có được bảo vệ bằng TLS/mTLS hay không tùy controller, cấu hình backend TLS, service mesh enrollment và policy tương ứng. **Không suy từ Gateway API HTTPS rằng traffic tới Pod backend tự được mTLS**.

## 9. Ví dụ Gateway API: HTTPS listener và route liên namespace

Giả sử nhóm platform được phép tạo Gateway trong namespace **edge**; Orders API là Kubernetes Service **orders-api** ở namespace **payments**, phục vụ HTTP trên Service port 8080. Gateway controller đã được cài và hỗ trợ **HTTPS listener, HTTPRoute, cross-namespace backend refs**. Ba manifests dưới đây minh họa **cấu trúc theo Gateway API**, không phải cấu hình production hoàn chỉnh hay đảm bảo có thể chạy trên mọi controller.

~~~yaml
# 1) Gateway trong namespace edge. GatewayClass và Secret cần tồn tại.
apiVersion: gateway.networking.k8s.io/v1
kind: Gateway
metadata:
  name: public-api-gateway
  namespace: edge
spec:
  gatewayClassName: approved-gateway-class
  listeners:
    - name: public-https
      hostname: api.example.test
      port: 443
      protocol: HTTPS
      tls:
        mode: Terminate
        certificateRefs:
          - kind: Secret
            name: public-api-tls
      allowedRoutes:
        namespaces:
          from: Same
---
# 2) HTTPRoute ở cùng namespace edge với Gateway.
apiVersion: gateway.networking.k8s.io/v1
kind: HTTPRoute
metadata:
  name: orders-public-route
  namespace: edge
spec:
  parentRefs:
    - name: public-api-gateway
      sectionName: public-https
  hostnames:
    - api.example.test
  rules:
    - matches:
        - path:
            type: PathPrefix
            value: /orders
      backendRefs:
        - name: orders-api
          namespace: payments
          port: 8080
---
# 3) Backend namespace cho phép route ở edge tham chiếu Service này.
apiVersion: gateway.networking.k8s.io/v1
kind: ReferenceGrant
metadata:
  name: permit-edge-orders-route
  namespace: payments
spec:
  from:
    - group: gateway.networking.k8s.io
      kind: HTTPRoute
      namespace: edge
  to:
    - group: ""
      kind: Service
      name: orders-api
~~~

### 9.1. Ý nghĩa bảo mật của từng phần

- **GatewayClass** xác định controller được phê duyệt. Tên **approved-gateway-class** là placeholder.
- **Gateway listener** nhận HTTPS trên 443 cho **api.example.test**, tham chiếu TLS Secret trong namespace **edge**.
- **allowedRoutes.namespaces.from: Same** chỉ cho những routes từ **namespace edge** gắn vào listener này theo mô hình ví dụ.
- **HTTPRoute** giới hạn host và PathPrefix **/orders**, chuyển tới **Service** ở namespace payments.
- **ReferenceGrant** trong **payments** cho phép nguồn là HTTPRoute ở namespace edge tham chiếu Service **orders-api**; **nó không xác thực HTTP client**.
- **HTTPRoute** không tự viết lại path. Backend vẫn có thể nhận đường dẫn **/orders**; muốn rewrite phải thiết kế filter/controller support tường minh.

### 9.2. Những điều còn thiếu trước khi triển khai

1. **GatewayClass/controller** hoạt động, load balancer được provision/định tuyến theo đúng nền tảng.
2. **Secret public-api-tls** hợp lệ cho hostname, với key được bảo vệ.
3. **orders-api Service** ở payments thực sự phục vụ cổng 8080 với endpoints sẵn sàng.
4. **Routing/firewall/NetworkPolicy** cho phép đúng Gateway workload đến backend.
5. **Mesh enrollment và mTLS** trên chặng backend nếu yêu cầu; tài nguyên Gateway API ở trên **không tự cấu hình mTLS backend**.
6. **Authentication/authorization, rate limiting, WAF, logging** phải được bổ sung theo sản phẩm và threat model.
7. **Status conditions** của Gateway/HTTPRoute/ReferenceGrant-related reconciliation cần được kiểm tra; không chỉ dựa vào kết quả apply.
8. **Cloud network exposure** phải giới hạn các listener dự định, tránh public backend/alternate load balancers.

### 9.3. Cross-namespace route attachment khác backend reference

Trong ví dụ, HTTPRoute **ở edge** nên Gateway listener có thể cho attachment từ **Same namespace**. Mặc dù HTTPRoute được gắn thành công, backend Service lại nằm ở **payments**, vì vậy cần xem **ReferenceGrant tại namespace payments**. Đây là **hai quyết định quản trị khác nhau**:

| Quyết định | Ai kiểm soát? | Dữ liệu liên quan |
| --- | --- | --- |
| Route có được attach vào gateway listener? | Chủ Gateway thông qua allowedRoutes | HTTPRoute namespace/kind/hostname/listener |
| Route có được tham chiếu Service khác namespace? | Chủ tài nguyên đích thông qua ReferenceGrant | Kind/namespace nguồn, kind/name đích |
| HTTP client có quyền gọi operation? | Gateway/API auth policy | JWT, client cert, user/workload context |
| Gateway có được kết nối backend? | NetworkPolicy + mesh policy | Gateway workload identity, port, mTLS |
| Caller có quyền với object? | Ứng dụng/backend | Tenant, owner, business rules |

### 9.4. ReferenceGrant không có nghĩa là chuyển quyền vĩnh viễn

Một ReferenceGrant hợp lệ tạo điều kiện để controller chấp nhận reference theo phạm vi khai báo, nhưng quyền **sửa các tài nguyên Route, Gateway, Service, Secret** vẫn cần RBAC/admission policy. Nếu một route author có thể sửa host/path tùy ý tại một Gateway dùng chung, họ có thể gây xung đột hoặc chiếm route thuộc nhóm khác. Cần giới hạn **route ownership, hostname policy và code review**.

## 10. Mesh mTLS và workload authorization tại backend

Khi gateway tham gia service mesh, có thể áp quy tắc mTLS và quyền service-to-service. Tuy nhiên, **mesh identity của gateway, external user identity và network source IP** là ba tín hiệu khác nhau.

### 10.1. Ví dụ Istio cho backend sử dụng mTLS

Trong một môi trường **Istio** được cài phù hợp, backend **orders-api** ở payments có thể được cấu hình yêu cầu **STRICT mTLS** và giới hạn peer principal. Các manifests dưới đây là **ví dụ chuyên biệt Istio**, không áp được cho các service mesh khác và phải kiểm tra CRD/version, mesh enrollment cũng như danh tính workload thật.

~~~yaml
# Điều kiện: Orders pods được chọn thuộc mesh, policy được Istio hỗ trợ.
apiVersion: security.istio.io/v1
kind: PeerAuthentication
metadata:
  name: orders-require-mtls
  namespace: payments
spec:
  selector:
    matchLabels:
      app: orders-api
  mtls:
    mode: STRICT
---
# Chỉ cho principal ingress gateway đã được xác minh gọi port ứng dụng.
apiVersion: security.istio.io/v1
kind: AuthorizationPolicy
metadata:
  name: orders-from-approved-gateway
  namespace: payments
spec:
  selector:
    matchLabels:
      app: orders-api
  action: ALLOW
  rules:
    - from:
        - source:
            principals:
              - cluster.local/ns/edge/sa/approved-ingress-gateway
      to:
        - operation:
            ports:
              - "8080"
~~~

**Những điều phải xác nhận trước khi dùng:**

- Thay **cluster.local**, namespace và service account bằng **principal thật** theo mesh trust domain; không đoán qua Pod name.
- Gateway workload phải thực sự **tham gia mesh** và có khả năng thiết lập mTLS với Orders. Nếu gateway không thuộc đúng mesh data plane, policy có thể chặn cả luồng hợp lệ.
- **PeerAuthentication STRICT** và **AuthorizationPolicy ALLOW** có scopes, precedence, exceptions và interactions theo Istio; cần rà soát **toàn bộ policies** áp dụng tại backend, không tin một manifest đơn lẻ.
- ALLOW trên port 8080 **không xác minh user Internet hoặc object ownership**; Orders vẫn phải kiểm tra JWT/API authorization.
- **Istio API và cách enforce khác nhau ở sidecar/ambient modes**; cần kiểm chứng đường gateway→workload bằng test thực tế.

### 10.2. mTLS STRICT chỉ bảo vệ một lớp

Khi mesh bắt buộc STRICT mTLS nhưng có **API gateway công khai và workload khác trong mesh** có chứng thư hợp lệ, chỉ yêu cầu mTLS có thể chưa đủ giới hạn người gọi. **AuthorizationPolicy theo workload principal** hoặc một cơ chế tương đương xác định **gateway/service nào** được gọi backend.

Để giảm lateral movement, cần kết hợp:

1. **NetworkPolicy** chỉ cho đường mạng dự kiến.
2. **mTLS** xác minh workload peer.
3. **Mesh AuthorizationPolicy** giới hạn workload principal/port/operation được hỗ trợ.
4. **API authorization** xác thực external token và quyền với tài nguyên.

### 10.3. Gateway→backend mTLS có thể không được áp tự động

Một số mesh có khả năng **auto-mTLS** giữa workloads đã tham gia mesh. Nhưng không được giả định rằng một proxy gateway bất kỳ hoặc một Gateway API controller **luôn** tự dùng mesh mTLS. Kiểm tra:

- Gateway Pod/ServiceAccount có mesh identity không?
- Workload destination có được bảo vệ bởi mesh data plane không?
- Trạng thái inbound mTLS STRICT/PERMISSIVE/DISABLE theo policy thực?
- Outbound traffic từ gateway có tạo đúng TLS peer và upstream verification không?
- Flow/telemetry xác nhận **mTLS thực sự**, không chỉ TCP 200.

## 11. Host, SNI, :authority và request routing

Public gateway thường định tuyến dựa trên hostname và path. Những giá trị này đến từ nhiều giao thức:

- **TLS SNI**: tên server mà client thông báo ở bước handshake, nếu được gửi và nhìn thấy.
- **HTTP/1.1 Host**: hostname mà HTTP request hướng đến.
- **HTTP/2/3 :authority**: pseudo-header tương ứng với authority của HTTP request.
- **Gateway listener hostname/HTTPRoute hostnames**: danh sách tên được cấu hình cho phép.

### 11.1. SNI và Host không phải lúc nào giống nhau

Một client có thể tạo yêu cầu trong đó TLS SNI, HTTP Host và URL authority không nhất quán. **Gateway cần có chính sách đối với mismatch**, tùy khả năng sản phẩm: từ chối host không được duyệt, xác minh đúng route, không đưa traffic tới default backend có quyền cao.

**Hostname từ client không phải bằng chứng người gọi có quyền với một tenant**. Chỉ vì Host có chuỗi **tenant-a** không cho phép API bỏ qua authentication/tenant membership.

### 11.2. Default route nguy hiểm khi quá rộng

Một gateway cho phép **wildcard host**, catch-all path và forward tới backend admin có thể làm lộ những endpoint chưa được duyệt. Cần:

- Khai báo **hostnames được phê duyệt**.
- Giới hạn **route matches** và backend được phép.
- Có hành vi **no-route/unknown-host** từ chối an toàn.
- Không tạo **catch-all route** tới management/backend nhạy cảm.
- Kiểm tra route precedence và wildcard matching theo controller thực.

### 11.3. Path normalization và rewrite

Proxy và backend có thể hiểu URL encoding, slash, dot segments, case hoặc HTTP parser khác nhau. Nếu gateway cho phép một path nhưng backend chuẩn hóa theo cách khác, có thể xảy ra **authorization/path confusion**.

Kiểm soát:

1. Chọn **canonical routing behavior** được hỗ trợ.
2. Rà soát path rewrite/redirect filters và backend paths.
3. Từ chối request không hợp lệ hoặc parser ambiguity theo policy.
4. Không chỉ dựa vào gateway route để chặn **admin operation**; backend vẫn phải enforce permission.
5. Kiểm thử các biến thể path hợp lệ trong **lab được cấp phép**, không dò tấn công production.

### 11.4. Wildcard certificates không cấp quyền wildcard routes

Một certificate **\*.example.test** (khi đúng chuẩn và được CA chấp nhận) có thể phục vụ nhiều subdomains phù hợp, nhưng không tự cho phép mọi HTTPRoute gắn vào Gateway hoặc mọi tenant chia sẻ backend. Quyền route, certificate ownership, secrets access và backend authorization vẫn độc lập.

## 12. Authentication/authorization tại gateway và backend

### 12.1. External authentication

Gateway hoặc API gateway có thể kiểm tra:

- OAuth 2.0 **access token** (JWT hoặc opaque) với issuer và audience đúng.
- ID token/refresh token bị **từ chối khi dùng sai mục đích**.
- Client certificate của đối tác nếu sử dụng mTLS.
- API key theo chính sách quản lý key phù hợp, nếu hệ thống có cơ chế này.
- Session/cookie cho web apps cùng các kiểm soát CSRF, SameSite và origin phù hợp.

**Đừng gán một thành công TLS handshake thành “user đã đăng nhập”**. TLS server-auth chỉ xác minh điểm đích ở client; client mTLS có thể xác minh client cert nhưng vẫn cần authorization theo endpoint/quyền.

### 12.2. JWT: audience và scope phải được xác minh

Ví dụ một access token giả lập:

~~~json
{
  "iss": "https://identity.example.test",
  "aud": "https://orders.api.example.test",
  "sub": "user-0042",
  "scope": "orders.read",
  "tenant_id": "tenant-a",
  "exp": 1795863000
}
~~~

Đây **không phải JWT có chữ ký**. Khi token là JWT, gateway/backend phải dùng thư viện xác minh chữ ký, algorithm/key policy, issuer, token profile/type, audience và các thời gian theo chuẩn; với opaque token cần introspection tin cậy theo hợp đồng AS.

Ngay cả token đúng **audience=Orders** và **orders.read** cũng không tự cho user-0042 quyền đọc đơn hàng thuộc tenant khác. **Application object-level authorization** vẫn bắt buộc.

### 12.3. Quy tắc cấp quyền nhiều lớp

~~~text
allow_request =
    allowed_public_listener_and_host_route
    AND trusted_client_authentication_if_required
    AND valid_access_token_for_target_api_if_required
    AND required_scope_or_operation_permission
    AND gateway_is_allowed_to_reach_backend
    AND backend_authenticates_or_trusts_user_context_safely
    AND user_or_workload_has_resource_and_tenant_permission
~~~

Đây là **logic phòng vệ**, không phải rule engine cụ thể. Một API có thể có endpoint public không cần user token, nhưng vẫn phải có policy rõ ràng cho loại endpoint đó và không vô tình áp ngoại lệ sang admin/data operations.

### 12.4. Authentication ở gateway không thay backend checks

Mô hình thường dùng:

| Tầng | Trách nhiệm |
| --- | --- |
| **Edge/gateway** | Kiểm tra route, authentication coarse-grained, rate limit và định tuyến |
| **Mesh/workload** | Xác thực service peer, giới hạn nguồn gọi backend |
| **Application/backend** | Kiểm tra operation, user/tenant, object ownership, state và nghiệp vụ |

Nếu backend nhận ngữ cảnh xác thực qua header như **X-Verified-User** hoặc **X-Verified-Scopes**, gateway phải **xóa header untrusted do client gửi và tái tạo dữ liệu từ nguồn đã xác minh**; backend chỉ tin những headers qua đường nhận diện gateway được bảo vệ, hoặc tốt hơn tự kiểm tra credential/attested context.

### 12.5. JWT ở gateway và bên trong mesh

Một mesh có thể gắn JWT validation vào workload/gateway proxies, nhưng vị trí nào kiểm tra và chính sách nào áp dụng phải được thiết kế. Không nên chỉ bật JWT validation mà bỏ **authorization policy**, hoặc giả định một **JWT hợp lệ cho API A** được dùng cho API B.

## 13. Trusted proxy chain và địa chỉ IP client

Khi traffic đi qua **CDN → cloud LB → ingress gateway → backend**, địa chỉ IP mà mỗi hop quan sát có thể là IP của proxy trước đó, không phải IP của người dùng Internet.

### 13.1. Các header liên quan

- **X-Forwarded-For**: danh sách địa chỉ có thể được các proxies bổ sung.
- **Forwarded**: HTTP header chuẩn hóa những thông tin liên quan client/proxy theo cú pháp tương ứng.
- **X-Forwarded-Proto/Host**: scheme/host mà proxy khai báo.
- **PROXY protocol**: cơ chế ở lớp trước ứng dụng dùng để chuyển metadata kết nối qua hop hỗ trợ.

**Tất cả những trường do client tự gửi đều có thể bị giả mạo** nếu điểm tin cậy không loại bỏ/chỉnh sửa chúng đúng cách.

### 13.2. Thiết lập trust boundary

1. Xác định **những proxy/LB CIDRs và identities được tin**.
2. Chỉ cho gateway tin forwarded metadata **từ đúng downstream proxy hop**.
3. Loại bỏ/ghi đè header nguồn không tin cậy tại edge được phê duyệt.
4. Cấu hình số trusted hops và thứ tự xử lý header theo proxy implementation.
5. Không cho backend trực tiếp nhận client request với metadata bị giả là từ gateway.
6. Khi dùng PROXY protocol, cả listener và upstream phải đồng ý protocol; không mở hỗ trợ này vô điều kiện tới Internet.

### 13.3. Không dùng IP như danh tính user

Một public IP có thể thuộc NAT/corporate proxy và đại diện nhiều users. IP allowlisting, geo/rate controls hữu ích theo rủi ro, nhưng **không thay JWT, mTLS client identity hoặc authorization theo user/tenant**.

### 13.4. Rủi ro spoofed scheme/host

Nếu backend tin **X-Forwarded-Proto=https** hoặc **X-Forwarded-Host** do client đặt, nó có thể tạo redirect/callback URL sai, xử lý cookie sai thuộc tính hoặc dùng host làm quyết định tenant không an toàn. Cần chỉ tin forwarded headers **được chuẩn hóa bởi proxy có thẩm quyền**, và định nghĩa hostnames/callbacks allowlist.

## 14. WAF, DDoS, rate limiting và gateway capacity

### 14.1. Những lớp phòng vệ không tương đương nhau

| Rủi ro | Lớp phù hợp | Giới hạn |
| --- | --- | --- |
| Volumetric DDoS vào IP public | Cloud/edge DDoS mitigation, upstream capacity | Không sửa lỗ hổng nghiệp vụ |
| HTTP request bất thường | WAF tại chỗ có thể đọc HTTP | Không phân tích được payload nếu TLS passthrough |
| Bùng nổ request vào API | Rate limit/quota theo identity/client/route | Không thay object authorization |
| Bot/scraping | Edge/application abuse controls, identity/risk scoring | Có false positives |
| TLS handshake exhaustion | TLS limits, L4/edge capacity, DDoS protection | Cần cân nhắc traffic client hợp lệ |
| Gateway compromise | Hardening, least privilege, patching, secret protection | Một proxy đơn lẻ không phải trust boundary duy nhất |
| Database direct exposure | Cloud firewall, private endpoints, NetworkPolicy | WAF công khai không bảo vệ DB path |

### 14.2. WAF chỉ thấy HTTP khi có quyền quan sát

WAF ở CDN có thể đọc HTTP nếu TLS được terminate tại CDN. Một mesh gateway ở **TLS passthrough** thường không thể xem request URL/body để áp L7 policy. Nếu traffic đến backend qua đường **ngoài WAF/CDN**, những WAF rules đó không bảo vệ đường ấy.

### 14.3. Rate limiting phải dựa trên key đúng

Rate limit có thể dùng client ID/JWT subject, API route, source IP đã xác minh hoặc tổ hợp. Nếu dựa vào **X-Forwarded-For chưa được chuẩn hóa**, attacker có thể ảnh hưởng cách nhóm request. Nếu dùng mỗi IP của NAT doanh nghiệp, nhiều users hợp lệ có thể bị giới hạn chung.

Với quota nhạy cảm, phân biệt **per gateway instance** với **distributed/global limits**. Một giới hạn cục bộ không mặc nhiên giữ đúng tổng quota khi autoscale nhiều replicas hoặc multi-region.

### 14.4. Availability và fail mode

Cần định nghĩa:

- Nếu external auth service hoặc JWT JWKS cache lỗi: **fail closed hoặc cache đã xác minh còn hiệu lực theo chính sách**, không tự allow tất cả.
- Nếu rate-limit service lỗi: fail-open/fail-closed theo mức nhạy cảm và tác động khách hàng.
- Nếu WAF/IPS mới gây false positives: có canary, alert mode và rollback được phê duyệt.
- Nếu gateway replicas thiếu năng lực: HPA/capacity budgets, connection limits và readiness.
- Nếu control plane tạm ngừng: dataplane có giữ config đã xác minh và hiệu lực TLS/cert thế nào?

Không có một cấu hình fail mode phù hợp mọi API; **các endpoint admin/financial cần xem xét rủi ro khác với endpoint thông tin công khai**.

## 15. Backend bypass: rủi ro khi mesh gateway không phải đường duy nhất

**Bypass** xảy ra khi một người gọi đến backend mà không đi qua những điểm kiểm tra dự kiến (WAF, API gateway, ingress proxy hoặc identity layer).

### 15.1. Những đường thường phải kiểm tra

1. **Service type LoadBalancer** được tạo trực tiếp cho backend.
2. **NodePort** tồn tại và firewall node/cloud cho phép nguồn không dự kiến.
3. **External IP** của VM/node/Pod, hostPort hoặc hostNetwork.
4. **Public IPv6 listener** trong khi chỉ khóa IPv4.
5. **Legacy/origin LoadBalancer** còn hoạt động sau đổi CDN/gateway.
6. **Ingress/Gateway khác** trỏ đến cùng Service hoặc endpoint.
7. **Cross-namespace route/ReferenceGrant** quá rộng hoặc được tạo ngoài quy trình.
8. **VPN/peering/partner network** chạm trực tiếp workload với chính sách yếu.
9. **Pod-to-Pod east–west** từ workload bị xâm nhập và có route.
10. **Kubernetes port-forward/exec/debug tunnels** do tài khoản có quyền quản trị, cần quản trị RBAC/admission riêng.

### 15.2. Mesh mTLS có ngăn bypass không?

Khi backend bắt buộc **STRICT mTLS**, một client trực tiếp không có chứng thư mesh hợp lệ có thể bị từ chối ở proxy/mesh dataplane. Nhưng **đừng dùng mTLS là biện pháp duy nhất** vì:

- Backend có thể có cổng/workload không được mesh bảo vệ.
- Một workload khác **đã thuộc mesh** có thể có chứng thư hợp lệ nhưng không được phép gọi endpoint này.
- Host-network/ambient/sidecar enrollment và đặc điểm dataplane khác nhau.
- Client từ Internet có thể đi tới public proxy khác có danh tính mesh hợp lệ rồi bị routing sai.
- Gateway/app-level user authorization vẫn là yêu cầu riêng.

**Cần kiểm tra mTLS STRICT + identity allowlist + firewall/NetworkPolicy + backend authorization**, đồng thời kiểm tra những đường alternate paths.

### 15.3. Phòng thủ bằng nhiều lớp

| Lớp | Kiểm soát |
| --- | --- |
| Cloud | Chỉ public LB/ingress được phép, backend private, IPv4/IPv6 rules |
| Kubernetes | Hạn chế Services NodePort/LoadBalancer/hostNetwork bằng admission/policy |
| NetworkPolicy | Chỉ gateway workload/approved services được nối backend |
| Mesh | STRICT mTLS, peer workload identity và AuthorizationPolicy |
| Application | Token validation, scope/audience, object/tenant authorization |
| Observability | Route inventory, policy verdicts, backend source identity, API logs |

### 15.4. “Chặn trực tiếp bằng DNS” không đủ

Không công bố bản ghi DNS cho backend có thể giảm khả năng phát hiện hostname, nhưng **không ngăn kết nối theo IP, Host header hoặc đường public listener**. Security boundary phải nằm ở **routing/filtering/identity/auth**, không dựa vào việc “giấu” origin DNS.

## 16. NetworkPolicy và firewall quanh ingress gateway

NetworkPolicy chuẩn có thể giới hạn traffic **đến Pod gateway** và **từ gateway đến các backend được phê duyệt**, trong những đường được CNI thực thi. Cloud firewall thường kiểm soát **public LB/node path** trước khi traffic tới Pods.

### 16.1. Mẫu ingress policy tại backend

Giả định mesh ingress workload có label **app=public-ingress** ở namespace **edge**, còn Orders có label **app=orders-api** ở namespace **payments**. Một NetworkPolicy minh họa:

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: orders-only-from-approved-ingress
  namespace: payments
spec:
  podSelector:
    matchLabels:
      app: orders-api
  policyTypes:
    - Ingress
  ingress:
    - from:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: edge
          podSelector:
            matchLabels:
              app: public-ingress
      ports:
        - protocol: TCP
          port: 8080
~~~

Hai selectors trong **cùng một peer item** phải cùng đúng (**AND**). Nếu đặt thành hai items, rule sẽ rộng hơn (**OR**). Nhưng trước khi áp dụng cần kiểm tra:

- Gateway thực sự có Pod label/namespace này không?
- Dataplane sidecar/ambient thấy **source Pod identity/IP** nào tại enforcement point?
- Backend/Service dùng port nào sau translation và sidecar interception?
- Có NetworkPolicies khác cho phép nguồn khác không?
- CNI có enforce NetworkPolicy và bao phủ đường NodePort/host/IPv6 không?
- Health checks và telemetry hợp lệ có bị chặn không?

**Kubernetes NetworkPolicy chuẩn dùng allow-based semantics; các policies áp dụng được hợp lại.** Một policy hẹp không tự ghi đè một allow rộng tồn tại ở policy khác.

### 16.2. Egress policy của gateway

Gateway thường phải gọi:

- Những backends đã được phê duyệt.
- DNS cluster nếu cần phân giải service discovery.
- Mesh control plane hoặc discovery/config services nếu kiến trúc yêu cầu.
- Certificate issuance/rotation, telemetry, external authorization và rate-limit services theo policy.

**Default-deny egress thiếu dependency list** có thể làm gateway chấp nhận client TLS nhưng trả lỗi backend, hoặc làm cert/config không cập nhật. Nên kiểm kê rõ destination/port và rollout theo canary, không mở all-egress vĩnh viễn.

### 16.3. Cloud firewall và đường vào

Ngay cả khi NetworkPolicy hạn chế Pod, nên:

1. Chỉ cho **public LB listener 443** trên những IP/FQDN được phê duyệt.
2. Giới hạn node security group/NSG đối với NodePort/hostPort và cổng admin.
3. Đảm bảo origin/backend không có public IP hoặc đường khác không qua gateway khi policy yêu cầu.
4. Xác minh **IPv6** cùng với IPv4.
5. Theo dõi những Services/LBs mới phát sinh và các thay đổi route/firewall.

### 16.4. Scope của NetworkPolicy không bằng mesh policy

NetworkPolicy định nghĩa traffic theo Pod/namespace/CIDR/port; mesh AuthorizationPolicy có thể dùng **mTLS service principal** và những điều kiện cao hơn theo sản phẩm. Một Pod giữ label đúng nhưng service account khác có thể qua network policy; policy dựa trên principal/mTLS bổ sung xác thực peer.

## 17. Sidecar mesh, ambient mesh và ingress gateway

Không phải mọi service mesh triển khai cùng kiến trúc data plane.

### 17.1. Sidecar-based mesh

Trong mô hình **sidecar**, ứng dụng được ghép với proxy trong Pod, proxy có thể intercept traffic inbound/outbound theo cách mesh được cấu hình. Mạng Kubernetes/host vẫn cung cấp reachability; proxy thực hiện một số chức năng **mTLS, routing, authorization và telemetry**.

Hệ quả:

- Gateway có thể là **một proxy workload riêng**, được quản lý bởi mesh control plane.
- Backend sidecar có thể chấp nhận **mTLS từ gateway proxy** theo chính sách.
- Khi Pod **không có sidecar hoặc sidecar bị bỏ qua**, hành vi mTLS/policy có thể khác so với baseline.
- Nếu ứng dụng mở cổng hoặc dùng cơ chế network đặc biệt tránh interception, cần đánh giá **policy coverage**.

### 17.2. Ambient mesh

Trong mô hình **ambient** hoặc không cần sidecar theo sản phẩm, có thể có tầng xử lý L4 ở node và **waypoint proxy** cho những chức năng L7 nhất định khi được cấu hình. Ingress gateway vẫn là một thành phần riêng để nhận traffic từ ngoài.

Điểm cần phân biệt:

1. **L4 mesh identity/mTLS** có thể do thành phần dataplane node xử lý.
2. **HTTP request-level authorization/routing** có thể yêu cầu waypoint hoặc một L7 proxy tương ứng.
3. **Peer identity ở policy hook** có thể khác khi gateway gửi traffic vào waypoint hoặc dataplane node.
4. Không suy một policy viết cho sidecar mode chắc chắn có cùng semantics trong ambient mode.
5. Việc đưa workload vào mesh phải có bằng chứng **enrollment và enforcement** ở phiên bản triển khai thực.

### 17.3. Câu hỏi phải trả lời trước khi coi gateway đã nằm trong mesh

| Câu hỏi | Bằng chứng |
| --- | --- |
| Gateway được mesh quản lý theo mode nào? | Deployment, labels, config, policy status |
| Gateway có mesh workload identity không? | Certificate/peer identity telemetry hợp lệ |
| Backend xử lý mTLS ở sidecar/ambient/waypoint nào? | Mesh dataplane config và handshake/verdict |
| Policy L4 hay L7 đang thực thi? | Policy attachment, proxy/waypoint telemetry |
| Có đường bypass interception không? | Negative tests qua direct Pod IP, Service, host/network path |
| Có cổng admin/health nằm ngoài service mesh không? | Listener inventory và firewall policies |

### 17.4. Không trộn external client principal với gateway service principal

Nếu gateway nhận một request từ user A, backend có thể chỉ thấy **peer mTLS là gateway**. Muốn phân quyền user A, backend cần thông tin user đáng tin **riêng**. Một cách an toàn thường gặp là backend tự xác minh access token dành cho API hoặc nhận context đã được ký/ràng buộc và truyền trên một kênh có bảo đảm rõ; không tin bất kỳ **X-User-Id** header nào từ client.

## 18. HTTP/1.1, HTTP/2, gRPC, WebSocket và TCP ingress

### 18.1. Các protocol có khả năng và hạn chế khác nhau

| Protocol/kiểu traffic | Điểm cần chú ý tại gateway |
| --- | --- |
| **HTTP/1.1** | Host, path/method, keep-alive, forwarded headers, proxy parser normalization |
| **HTTP/2** | :authority, multiplexing/streams, per-stream controls, TLS/ALPN theo cách dùng |
| **gRPC** | HTTP/2 routing, method/service authorization, deadlines, stream handling |
| **WebSocket** | Upgrade/long-lived connection, auth tại handshake và phiên sau đó |
| **HTTP/3/QUIC** | UDP/TLS 1.3 và sự hỗ trợ cụ thể của edge/gateway/controller |
| **Raw TCP** | L4 routing/port controls; không tự thấy HTTP/JWT headers |
| **TLS passthrough** | Route theo SNI hoặc L4 khi hỗ trợ; HTTP auth/WAF không hoạt động tại proxy không terminate TLS |

### 18.2. gRPC authorization

Một Gateway/HTTPRoute có thể hỗ trợ gRPC hoặc có **GRPCRoute** nếu controller triển khai. Với streaming RPC, cần xem **per-request vs per-stream authorization**, deadline, retries và phương án hủy các phiên dài khi credential/role bị thu hồi.

Không suy tất cả các policy HTTP method/path áp nguyên xi vào gRPC service/method. Backend gRPC vẫn cần xác thực danh tính và quyền nghiệp vụ.

### 18.3. WebSocket và kết nối lâu dài

Gateway có thể kiểm tra request handshake ban đầu nhưng sau khi kết nối mở, traffic có thể là nhiều message với các quyền khác nhau. Nếu ứng dụng gửi lệnh nhạy cảm qua WebSocket, **authorization per message/operation** cần được thiết kế tại ứng dụng. TLS và gateway handshake không tự thay thế.

### 18.4. TCP passthrough và mTLS

Với TCP hoặc TLS passthrough, gateway thường chỉ thực hiện routing/filtering ở mức có thể quan sát; **service đích phải trực tiếp xử lý TLS/client auth hoặc mesh transport đúng kiến trúc**. Đừng bật một HTTP-focused WAF rule rồi khẳng định nó đã kiểm tra traffic TCP/gRPC opaque.

### 18.5. Bảo vệ tài nguyên

HTTP/2 streams, slow clients, long-lived WebSocket connections và large request bodies đều tiêu thụ tài nguyên gateway/backend. Chính sách **connection limits, per-route request timeout, body size, idle timeout, concurrency, circuit breaking và rate limiting** phải tính đến hợp lệ của ứng dụng, không tùy tiện đặt chung một ngưỡng.

## 19. Multi-tenant/multi-team ingress gateway

Một ingress gateway có thể phục vụ **nhiều ứng dụng, teams, tenants và domains**. Khi đó nó là **shared security boundary**: người có quyền cấu hình một route không nên có quyền thay certificate/backend của đội khác.

### 19.1. Vai trò vận hành

| Vai trò | Có thể sở hữu | Điều cần giới hạn |
| --- | --- | --- |
| **Platform/network team** | GatewayClass, Gateway listeners, public LB và TLS control plane | Chỉ public cổng/hostname được duyệt |
| **Application team** | HTTPRoute đã được cấp quyền, Service và backend | Không chiếm domain/route hoặc backend team khác |
| **Security/IAM team** | Auth policies, WAF/DDoS, JWT issuers, mesh identity | Không để policy có ngoại lệ ngầm |
| **PKI/certificate team** | Certificate issuance, trust anchors, Secret lifecycle | Không lộ private key hoặc cấp cert sai domain |
| **SOC/SRE** | Telemetry, incident response, canary/rollback | Phân quyền xem logs và tài nguyên production |

### 19.2. AllowedRoutes và namespace boundaries

Một listener mở **allowedRoutes.namespaces.from: All** có thể là nhu cầu hợp lệ ở cluster dùng multi-tenant routing, nhưng cần ràng buộc **hostname ownership, RBAC, admission và approval**. Nếu không, một team có thể cố gắn route không thuộc quyền họ.

Lựa chọn **Same** hoặc **Selector** giúp giới hạn những namespaces được phép attach theo chính sách. Tuy nhiên **được attach route** không tự cho phép **tham chiếu Service khác namespace**; ReferenceGrant và những cơ chế cross-namespace tương ứng vẫn phải được kiểm tra.

### 19.3. Route conflicts

Hai HTTPRoutes có thể khai báo host/path trùng nhau hoặc có thứ tự ưu tiên thay đổi theo Gateway API và controller. Cần:

- Chỉ định rõ **ownership của hostname và path prefixes**.
- Kiểm tra Gateway/HTTPRoute **status conditions**.
- Kiểm thử route precedence, unknown host và no-match behavior.
- Không đưa admin route vào default backend.
- Rà soát các route cũ khi chuyển domain hoặc rollout version mới.

### 19.4. Secret và certificate delegation

Một ứng dụng có quyền sửa **TLS Secret** mà gateway dùng có thể thay đổi server identity theo cấu hình, hoặc làm lộ key nếu quyền đọc secret không được hạn chế. **Không cho mọi route author quyền sửa secrets của shared gateway**; cân nhắc mô hình certificate automation tách biệt và policy cho cross-namespace references.

### 19.5. Phân tách gateway theo mức độ tin cậy

Không nhất thiết mọi API phải dùng **một gateway chung**. Một hệ thống có thể phân loại:

- **Public customer API gateway**.
- **Partner API gateway** cần client mTLS.
- **Internal-only gateway** qua VPN/private LB.
- **Admin gateway** với mTLS/MFA/PAM/allowlist chặt.

Tách gateway giúp giảm blast radius, nhưng tăng chi phí cấu hình và vận hành. Cần quyết định dựa trên trust boundaries, tenant isolation, certificate ownership và capacity.

## 20. DNS, public hostname và certificate identity

### 20.1. Public DNS giúp tìm IP, không phải cấp quyền

DNS trả **A/AAAA/CNAME** cho **api.example.test**; client vẫn phải xác minh chứng thư TLS và gateway/backend phải thực thi authz. **Không có DNS record cho origin không đồng nghĩa origin không truy cập được bằng IP hoặc alternate name**.

### 20.2. Certificate phải khớp hostname dự kiến

Khi client truy cập **https://api.example.test**, TLS server certificate cần hợp lệ cho hostname được xác minh theo quy tắc TLS/PKI. Nếu DNS trỏ sang LB khác trả certificate không phù hợp, client phải từ chối thay vì tắt certificate verification.

### 20.3. DNS cutover và TTL

Khi đổi public gateway:

1. Kiểm kê domain, A/AAAA/CNAME, geo-routing và CDN config.
2. Tạo gateway mới với certificate/route đã được test.
3. Test hostname/TLS và backend identity tại IP mới trong lab/staging hoặc canary.
4. Đánh giá DNS TTL, client caching và long-lived connections.
5. Theo dõi traffic ở gateway cũ và mới trong giai đoạn cutover.
6. Gỡ gateway/origin cũ **sau khi xác minh không còn phụ thuộc hợp lệ**.

**Giảm TTL không đảm bảo mọi client ngay lập tức bỏ IP cũ**; connection pooling, DNS cache và mạng trung gian có thể giữ kết nối cũ lâu hơn.

### 20.4. IPv6 phải được kiểm tra riêng

Một DNS A record trỏ CDN/WAF đúng nhưng **AAAA record** trỏ origin cũ có thể tạo đường bypass cho IPv6 clients. Phải kiểm tra **dual-stack listeners, security groups, ::/0 routes, IPv6 WAF coverage và HTTPRoute/gateway behavior**.

### 20.5. Private DNS và split-horizon

Các internal gateways có thể dùng **private DNS** để clients qua VPN/on-prem resolve tới private LB. Nhưng DNS private chỉ quản lý **tên/địa chỉ**; cloud firewall, TLS và identity phải quyết định ai có thể kết nối và thực hiện thao tác.

## 21. Mô hình chính sách trung lập với nhà cung cấp

Đây là một ví dụ **mô tả ý định bảo mật và bằng chứng vận hành**. Nó **không phải cấu hình có thể áp trực tiếp** trên Istio, Linkerd, Envoy, Gateway API, cloud API gateway hoặc WAF:

~~~yaml
meshIngressSecurityRequirements:
  name: public-api-protected-entry
  environment: isolated-training
  ownership:
    gatewayOwner: platform-network-team
    securityOwner: security-operations
    applicationOwner: orders-team
    certificateOwner: pki-team
  publicExposure:
    publicHostnames:
      - api.example.test
    publicListeners:
      - protocol: HTTPS
        port: 443
    prohibitDirectPublicBackend: true
    prohibitUnapprovedNodePortAndHostPort: true
    coverIpv4AndIpv6: true
    inventoryAlternateLoadBalancers: true
    requireReviewedDnsChanges: true
  ingressGateway:
    approvedGatewayClass: organization-approved
    routeOwnershipProtected: true
    listenerHostnamesRestricted: true
    unknownHostDecision: reject
    crossNamespaceReferences: owner-approved-and-reviewed
    tlsTerminationMode: explicitly-documented
    tlsServerCertificate:
      validateHostnameAndChain: true
      rotateBeforeExpiry: true
      restrictPrivateKeyAccess: true
    forwardedHeaders:
      trustOnlyApprovedProxies: true
      stripExternalUntrustedIdentityHeaders: true
      verifyOriginalSchemeAndHostContext: true
  edgeControls:
    ddosProtection: according-to-public-risk
    httpWaf: where-decrypted-traffic-is-observable
    rateLimiting: identity-and-route-based-when-appropriate
    safeLimitsForStreamsAndBodySize: true
    redactCredentialsInLogs: true
  mesh:
    requireVerifiedGatewayWorkloadIdentity: true
    gatewayToBackendTransport: verified-mtls-when-enrolled
    backendPolicy:
      restrictSourcePrincipals: true
      restrictDestinationPorts: true
      protectHostAndUnmeshedPaths: separately
    validateSidecarOrAmbientEnrollment: true
  apiAuthorization:
    requireValidIssuerAndAudience: on-protected-routes
    requireScopesAndObjectPermissions: according-to-api-policy
    propagateTrustedUserContextOnly: true
    prohibitBlindTrustInXVerifiedUser: true
  networkControls:
    cloudFirewall: public-edge-only-as-designed
    kubernetesNetworkPolicy: enforce-and-test
    denyBackendDirectExposure: true
    protectManagementListeners: true
  observability:
    logGatewayRouteAndTlsDecision: true
    logMeshPeerAndPolicyOutcome: true
    correlateRequestIdAcrossHops: true
    collectCloudLoadBalancerAndWafEvents: true
    detectRouteAndExposureDrift: true
  governance:
    requireReviewedIacAndChangeTickets: true
    requirePositiveAndNegativeTests: true
    expireTemporaryExposureExceptions: true
    maintainCanaryAndRollback: true
~~~

### 21.1. Giới hạn của mẫu

Một dòng như **gatewayToBackendTransport: verified-mtls-when-enrolled** không bật mTLS. Phải ánh xạ ý định sang **mesh identity/certificate, proxy policy, traffic flow, workload enrollment và logs/handshake** của hệ thống đang dùng.

### 21.2. Rủi ro cấu hình “lấy nhãn thay danh tính”

Nếu mesh policy hoặc NetworkPolicy dựa trên nhãn **app=public-ingress**, cần bảo vệ quyền gắn nhãn và triển khai workload. **Pod label không thay service account/workload mTLS principal**; đừng dùng label làm bằng chứng mật mã rằng đây là gateway đáng tin.

### 21.3. Default deny và exception

Chính sách **deny-by-default** có thể áp ở route, network và authorization layers, nhưng phải xem **semantics thực tế của từng sản phẩm**. Một số policy là allow-list, một số có priority/deny action riêng. Ngoại lệ tạm cần **owner, ticket, expiry, audit và phương án thu hồi**.

## 22. Logs, metrics và quan sát đường ingress

Một kết nối từ Internet tới Orders có thể xuất hiện trong **CDN/WAF log, cloud LB log, gateway access log, mesh proxy/authorization log, backend log và database audit log**. Những nguồn này không thay thế nhau.

### 22.1. Nguồn log và giới hạn

| Nguồn | Những dữ liệu có thể có | Không tự chứng minh |
| --- | --- | --- |
| **Cloud LB/edge logs** | Client connection, listener, target, TLS/network metadata | Backend đã xác thực user và object đúng |
| **CDN/WAF logs** | HTTP request/route/rule decisions tại edge | Mọi request đều đi qua CDN/WAF |
| **Gateway access logs** | Host, path, route, upstream, response flags, mTLS/tracing theo sản phẩm | Không có backend bypass |
| **Gateway/controller status** | Listener/route accepted, programmed, invalid refs | Runtime network allow/deny cho mọi đường |
| **Mesh proxy/policy telemetry** | Source/destination workload principal, TLS mode, allowed/denied, service | User API đã được cấp business permission |
| **Kubernetes audit** | Ai sửa Gateway, HTTPRoute, Service, Secret, NetworkPolicy | Request thực tế đã được chặn |
| **Cloud firewall/flow logs** | IP/port, NAT, allow/deny tại điểm cloud network | Nội dung HTTP hoặc JWT đã hợp lệ |
| **Application/database logs** | Request ID, user/tenant, operation, object-level outcome | Mọi network packet bị chặn trước ứng dụng |
| **DNS logs** | Name resolution và vùng private/public | Client thực sự kết nối theo IP được trả về |

### 22.2. Trường nên có trong gateway access event

- Timestamp, gateway/route ID, listener, hostname và path category.
- Request/trace ID xuyên các hops.
- Client IP **được suy ra từ trusted proxy chain** và thông tin proxy source.
- TLS version/SNI/handshake status theo phạm vi hỗ trợ.
- External client certificate identity hoặc **token validation outcome**, nếu dùng và được log an toàn.
- Upstream service/namespace, mesh workload principal khi có.
- HTTP status, response flags, latency và retries.
- Policy version, deployment revision, zone/region.
- Nguyên nhân deny ở đúng lớp, như **unknown_host, invalid_token, insufficient_scope, peer_not_authorized, backend_unreachable**.

**Không ghi full Authorization header, bearer token, refresh token, cookies, TLS private key, client secret hoặc thông tin cá nhân không cần thiết**. Nếu cần correlation, ưu tiên request ID và opaque identity reference được quản lý.

### 22.3. Log giả lập: gateway từ chối hostname lạ

~~~json
{
  "timestamp": "2026-11-28T20:15:00+07:00",
  "dataset": "synthetic-training-event",
  "event_type": "ingress_gateway_route_rejected",
  "gateway": "edge/public-api-gateway",
  "listener": "public-https",
  "requested_hostname": "unknown.example.test",
  "accepted_hostnames": ["api.example.test"],
  "route_match": false,
  "decision": "reject",
  "http_status": 404,
  "upstream_request_sent": false,
  "policy_version": "lab-gateway-12",
  "request_id": "req-lab-001"
}
~~~

Status **404** trong ví dụ chỉ minh họa một chính sách no-route, không phải status duy nhất mà mọi controller trả cho unknown host. Một số trường hợp TLS handshake có thể bị từ chối **trước HTTP**, tùy SNI/listener/TLS.

### 22.4. Log giả lập: mTLS peer được xác thực nhưng thiếu quyền

~~~json
{
  "timestamp": "2026-11-28T20:16:00+07:00",
  "dataset": "synthetic-training-event",
  "event_type": "mesh_authorization_denied",
  "destination_service": "orders-api.payments.svc.cluster.local",
  "destination_port": 8080,
  "peer_mtls": "verified",
  "peer_principal": "cluster.local/ns/tools/sa/debug-client",
  "expected_principals": [
    "cluster.local/ns/edge/sa/approved-ingress-gateway"
  ],
  "decision": "deny",
  "reason": "source_principal_not_allowed",
  "application_received_request": false,
  "request_id": "req-lab-002"
}
~~~

Điểm quan trọng: **mTLS có thể thành công nhưng mesh AuthorizationPolicy vẫn từ chối principal**. Có chứng thư mesh hợp lệ không đồng nghĩa được gọi Orders API. Đây cũng không phải log thật của Istio; schema chỉ mang tính minh họa.

### 22.5. Log giả lập: network/mTLS cho qua, API từ chối object

~~~json
{
  "timestamp": "2026-11-28T20:17:00+07:00",
  "dataset": "synthetic-training-event",
  "event_type": "orders_api_authz_denied",
  "gateway_route": "edge/orders-public-route",
  "peer_principal": "cluster.local/ns/edge/sa/approved-ingress-gateway",
  "peer_mtls": "verified",
  "api_audience_check": "pass",
  "api_scope_check": "orders.read:pass",
  "subject_ref": "user-0042",
  "verified_tenant": "tenant-a",
  "requested_resource_tenant": "tenant-b",
  "decision": "deny",
  "http_status": 403,
  "reason": "cross_tenant_access",
  "request_id": "req-lab-003",
  "token_recorded": false
}
~~~

Một **403 application authorization** không chứng minh NetworkPolicy hoặc mesh mTLS đã chặn request; ở ví dụ này chính **backend API** từ chối sau khi gateway/mesh cho kết nối.

### 22.6. Metrics quan trọng

| Chỉ số | Cách sử dụng |
| --- | --- |
| Public listeners/domains/LBs theo môi trường | Phát hiện tăng public exposure |
| Gateway TLS handshake failure/expiry | Phát hiện chứng thư/trust/client compatibility |
| Route 4xx/5xx và no-route count | Nhận biết routing/auth changes, không tự gắn tất cả với attack |
| JWT invalid audience/scope/auth failures | Kiểm tra client, issuer, access policy drift |
| mTLS negotiated vs plaintext/unknown | Xác minh transport theo mesh enrollment |
| Mesh policy allow/deny theo principal | Phát hiện nguồn không được phép và lateral attempts |
| Gateway-to-backend latency/upstream resets | Nhận biết network/backend availability |
| WAF/rate-limit outcomes | Điều chỉnh false positives và capacity |
| Direct-backend reachability check | Phát hiện bypass gateway |
| NodePort/LoadBalancer/IPv6 asset drift | Theo dõi đường công khai mới |
| Config/cert/route reconcile errors | Phát hiện controller chưa áp thay đổi |
| Resource saturation/HPA/restart trends | Tránh outage và bảo vệ gateway trước tải tăng |

### 22.7. Khi không có request trong gateway logs

Nếu backend ghi một request nhưng gateway không ghi, có thể do:

- Traffic đến qua **đường khác**.
- Gateway log bị tắt, sampling hoặc mất dữ liệu.
- Request ID không được truyền/quản lý thống nhất.
- Client kết nối trực tiếp tới backend nội bộ hợp lệ.

**Không kết luận bypass chỉ từ một log thiếu**, nhưng cần kiểm tra nguồn mesh identity, network path, alternate LB và access log coverage.

## 23. Troubleshooting: lỗi xảy ra ở lớp nào?

Một client báo không truy cập được API có thể do DNS/TLS, Gateway API route, Service endpoint, mesh mTLS, NetworkPolicy hoặc application 401/403. Nên điều tra theo **chuỗi bằng chứng từ ngoài vào trong**.

### 23.1. Triệu chứng và lớp ưu tiên

| Triệu chứng | Lớp nghi ngờ | Bằng chứng cần tìm |
| --- | --- | --- |
| DNS NXDOMAIN | Public/private DNS hoặc hostname sai | A/AAAA/CNAME, authoritative resolver |
| TCP connection timeout | Route/firewall/LB, listener down | Cloud listener/flow logs, effective routes |
| TLS hostname/certificate mismatch | Certificate/SNI/trust | SAN/chain, TLS listener, client verification |
| TLS alert do client cert | Client mTLS trust/identity | Gateway TLS auth logs, CA policy |
| HTTPS 404/No route | Gateway listener/HTTPRoute host/path | Route status, host/path match, gateway logs |
| HTTP 502/503 | Backend unavailable, endpoints, upstream TLS | EndpointSlice, proxy response flags, backend readiness |
| gRPC UNAVAILABLE | Protocol route, upstream transport/health | gRPC proxy/backends logs, HTTP/2 support |
| mTLS handshake failure gateway→backend | Mesh trust/STRICT, enrollment, cert | Gateway and workload mesh telemetry |
| Mesh policy denied | Service account/workload principal | Auth policy verdict, identity/trust domain |
| HTTP 401 invalid token | API gateway/backend authn | Token type/issuer/audience/time |
| HTTP 403 insufficient scope | API authorization | Scope requirement, auth policy |
| HTTP 403 object access | Backend business policy | Verified principal, tenant and resource |
| Chỉ IPv6 bypass/không vào | IPv6 DNS/listener/route/security group | AAAA, ::/0, IPv6 LB and firewall |
| Chỉ một AZ/region lỗi | Gateway replicas/LB targets/route | Placement, health, failover config |

### 23.2. Bước 1 – Xác định request được phép và hostname

Ghi lại request path và phương thức, **không ghi Bearer token**:

~~~text
Client source:        Authorized lab client
Public hostname:      api.example.test
Protocol/port:        HTTPS / TCP 443
Operation:            GET /orders/42
Expected route:       edge/orders-public-route
Expected backend:     payments/orders-api:8080
Expected upstream:    verified mesh mTLS
Observed:             503 upstream unavailable
Request ID:           req-lab-debug-101
Scope:                Lab hoặc hệ thống được cấp quyền
~~~

### 23.3. Bước 2 – Kiểm tra Kubernetes Gateway/Route/Service

Ví dụ **các lệnh quan sát read-only** trên cluster được phép:

~~~bash
# Kiểm tra Gateway và route; tên phải thay theo tài nguyên thật.
kubectl -n edge get gateway public-api-gateway -o yaml
kubectl -n edge get httproute orders-public-route -o yaml
kubectl -n payments get referencegrant permit-edge-orders-route -o yaml

# Xác định Service và EndpointSlice.
kubectl -n payments get service orders-api -o wide
kubectl -n payments get endpointslice -l kubernetes.io/service-name=orders-api

# Kiểm tra nhãn, node và trạng thái backend Pod.
kubectl -n payments get pods -o wide --show-labels
~~~

Xem **Accepted, Programmed, ResolvedRefs, listener/route parents** hoặc các conditions thực tế mà controller cung cấp. **Resource tồn tại không đồng nghĩa controller đã lập trình listener/route thành công.**

### 23.4. Bước 3 – Xem public exposure và TLS

Kiểm tra bằng nguồn quản trị/cloud được cấp phép:

- Public LB addresses và listeners, IPv4/IPv6.
- TLS certificate hostname, issuer, expiry và chain được gateway phục vụ.
- Chặng **LB→gateway** là TLS pass-through, TLS termination hay re-encrypted.
- CDN/WAF hostname/route coverage, origin restriction.
- Alternate public Services/LBs hoặc node ports.

Không sử dụng **TLS insecure/skip verify** để coi lỗi đã được sửa. Nếu cần chẩn đoán chứng thư, dùng chế độ quan sát an toàn trên endpoint được phép.

### 23.5. Bước 4 – Xác minh network và mesh policy

~~~bash
# Kubernetes NetworkPolicies áp dụng trên các namespaces có liên quan.
kubectl -n edge get networkpolicy -o yaml
kubectl -n payments get networkpolicy -o yaml

# Nếu cluster có CRDs Istio tương ứng và được cấp quyền đọc:
kubectl -n payments get peerauthentication -o yaml
kubectl -n payments get authorizationpolicy -o yaml
~~~

Không phải cluster nào cũng có Istio CRDs hoặc các tên policy này. Nếu không tồn tại, phải dựa vào implementation mesh thực tế. Kiểm tra **source/destination principal, mTLS mode, CNI policy coverage và Gateway→Backend port**, gồm đường host/ambient nếu liên quan.

### 23.6. Bước 5 – Kiểm tra API application

Nếu network/TLS đã hoạt động nhưng API trả 401/403, xem **JWT issuer/audience/scope, client identity và resource-level policy**. Không nới cloud firewall hoặc tắt mTLS để “sửa lỗi 403” nếu đây là authorization denial hợp lệ.

### 23.7. Bước 6 – So sánh positive và negative cases

Một ca hợp lệ qua gateway **phải thành công**, còn một ca truy cập thẳng backend từ nguồn không được phê duyệt **phải bị chặn**. Xác định **chặn tại lớp nào** bằng flow logs/mesh authz logs và backend telemetry; đừng chỉ nhìn TCP timeout.

## 24. Runbook: phát hiện backend public bypass ingress gateway

**Tình huống:** SOC tìm thấy một Kubernetes Service type LoadBalancer công khai trỏ trực tiếp tới Orders API. Trong khi đó public API chính thức phải đi qua CDN/WAF → mesh ingress gateway. Đường mới có thể làm các rule WAF/auth/rate limits ở gateway **không bao phủ** request trực tiếp.

### 24.1. Giai đoạn 1 – Xác minh exposure

1. Xác định **Service name/namespace/type, cloud LB resource, listener/IP (IPv4/IPv6), tạo bởi principal nào**.
2. Đọc **Kubernetes/cloud audit logs** để tìm change ticket hoặc nguồn tự động hóa.
3. Kiểm tra **Service selectors, target ports, EndpointSlices** và backend thực tế.
4. Kiểm tra cloud firewall/security groups, public routes và listener, không chỉ DNS record.
5. Đối chiếu mesh enrollment, STRICT mTLS và workload AuthorizationPolicy của backend.
6. Kiểm tra **backend/application access logs**: có request không đi qua gateway không? Có dữ liệu nào được trả ra theo bằng chứng?
7. Liệt kê những tài nguyên khác có chung labels/service templates hoặc rule mở rộng.

**Public LB tồn tại không tự chứng minh dữ liệu đã bị đọc**. Reachability, authentication và kết quả truy cập dữ liệu là ba câu hỏi phải điều tra riêng.

### 24.2. Giai đoạn 2 – Khoanh vùng an toàn

- Chặn nguồn/route ngoài dự kiến tại **cloud LB/firewall/Service exposure** theo quy trình phê duyệt.
- Giữ **luồng gateway hợp lệ** tiếp tục tới backend; tránh xóa Service đang phục vụ tác vụ nội bộ nếu chưa hiểu dependency.
- Siết **NetworkPolicy** tới nguồn gateway/workloads được duyệt khi engine hỗ trợ.
- Xác minh STRICT mTLS, mesh AuthorizationPolicy và app authorization đang enforce.
- Bảo vệ logs và audit; nếu nghi token/secret bị lộ, kích hoạt quy trình thu hồi/rotation phù hợp.
- Không đơn giản thêm WAF rule rồi tuyên bố đã khắc phục nếu backend còn đường bypass khác.

### 24.3. Giai đoạn 3 – Xác minh sau containment

| Kiểm tra | Kết quả mong đợi |
| --- | --- |
| Client hợp lệ tới **api.example.test/orders** | HTTPS/TLS, route và API access theo quyền |
| Client truy cập backend public LB cũ | Bị chặn hoặc endpoint không còn theo thiết kế |
| Client IPv6 qua origin cũ | Bị chặn, không tạo alternate path |
| Pod không được phép gọi Orders qua cluster Service | Bị NetworkPolicy/mesh authz từ chối |
| Gateway workload gọi Orders qua mesh | mTLS và principal authorization thành công |
| User thiếu scope/tenant access | API trả deny theo chính sách |
| WAF/gateway và backend logs | Correlation đầy đủ, không lộ credential |
| Backend health, TLS và cert rotation | Duy trì chức năng hợp lệ |

### 24.4. Giai đoạn 4 – Nguyên nhân gốc

Điều tra:

- Vì sao **LoadBalancer public** được tạo: chart mặc định, Helm value, manual action hay automation?
- Có **admission/policy-as-code guardrail** cấm public Services trong namespace backend không?
- Ai có thể đổi **Service type, Gateway listeners, routes, ReferenceGrants và cloud firewall**?
- Vì sao inventory/continuous scanning không phát hiện sớm?
- Backend có đủ **mTLS/authorization** để giảm tác động khi lớp edge bị bypass không?
- Các sự kiện tương tự có xảy ra trên IPv6, staging, disaster recovery hoặc cluster khác không?

### 24.5. Báo cáo sự cố cần tách các kết luận

1. **Có public exposure ngoài thiết kế**.
2. **Có reachability thực tế tới backend**.
3. **Có authentication/authorization bypass**.
4. **Có dữ liệu bị truy cập hoặc thay đổi trái phép**.

Mỗi kết luận cần bằng chứng riêng; không suy kết luận (4) tự động từ (1), nhưng cũng không coi (1) vô hại khi chưa điều tra.

## 25. Ma trận kiểm thử ingress gateway và public exposure

Các phép thử chỉ được thực hiện trên **môi trường lab hoặc tài nguyên mà bạn có quyền kiểm thử**. Không quét Internet/ports của bên thứ ba, không cố gây DDoS, không cố vượt qua xác thực production và không sử dụng token hay client certificate của người khác. Có thể dùng **synthetic logs và kết quả giả lập** để kiểm tra các kịch bản khó tạo an toàn.

### 25.1. Positive và negative tests

| Mã | Tình huống | Kết quả kỳ vọng |
| --- | --- | --- |
| T-01 | Client tới hostname HTTPS public được duyệt | TLS certificate hợp lệ, listener nhận request |
| T-02 | Request tới hostname lạ không nằm trong allowlist | No-route/TLS reject theo policy; không tới backend |
| T-03 | IPv4 đi qua CDN/WAF và public LB | Request được gateway xử lý đúng route |
| T-04 | IPv6 tới cùng hostname | Cùng policy bảo vệ; không bypass qua origin |
| T-05 | HTTPS listener trên Gateway API đã provision | Gateway/HTTPRoute conditions phù hợp, end-to-end test pass |
| T-06 | HTTPRoute tham chiếu Service khác namespace có ReferenceGrant hợp lệ | Controller resolve backend theo rule được duyệt |
| T-07 | Bỏ ReferenceGrant trong lab cô lập | Backend reference không được chấp nhận theo Gateway API semantics |
| T-08 | HTTPRoute ngoài namespace allowedRoutes | Không attach vào listener nếu policy không cho |
| T-09 | Route sai Host hoặc path không được duyệt | Không chuyển tới backend nhạy cảm |
| T-10 | TLS server cert sai tên/không tin cậy | Client TLS verification thất bại |
| T-11 | Gateway TLS certificate xoay đúng | Client không gặp lỗi trust; theo dõi expiry/rollout |
| T-12 | TLS passthrough qua gateway | Backend terminate TLS; không giả gateway đã xem HTTP/JWT |
| T-13 | Gateway terminate client TLS và kết nối backend qua verified mTLS | Chứng minh hai TLS hops theo cấu hình |
| T-14 | Gateway mesh enrollment bị cấu hình sai trong lab | STRICT mTLS/policy phát hiện/chặn theo implementation |
| T-15 | Backend yêu cầu STRICT mTLS, client plaintext direct | Bị từ chối tại mesh dataplane theo capability |
| T-16 | Workload mesh khác có mTLS hợp lệ nhưng principal không allow | Mesh AuthorizationPolicy deny |
| T-17 | Gateway workload principal đúng gọi Orders | Mesh authz allow, backend vẫn kiểm tra app auth |
| T-18 | Bearer token hợp lệ nhưng aud thuộc API khác | Gateway/backend deny invalid token/audience |
| T-19 | Token đúng aud nhưng thiếu scope | Deny theo API scope policy |
| T-20 | Token đúng aud/scope nhưng object tenant khác | Backend object authorization deny |
| T-21 | Client tự gửi X-Verified-User hoặc X-Forwarded-For giả lập | Gateway sanitize, backend không tin header client |
| T-22 | Request via proxy được phê duyệt | Source IP derived từ trusted hop, không từ header tùy ý |
| T-23 | Request đi trực tiếp tới backend public LB cũ trong lab | Deny hoặc không có public route theo thiết kế |
| T-24 | NodePort/hostPort/backend alternate origin tồn tại | Inventory/controls nhận biết và chặn nguồn không phép |
| T-25 | Pod ngoài quyền gọi backend ClusterIP | NetworkPolicy hoặc mesh authz deny |
| T-26 | Gateway HTTP/2 hoặc gRPC route đúng theo controller support | End-to-end protocol và auth hoạt động |
| T-27 | WebSocket long-lived connection có operation nhạy cảm | Message/application authorization vẫn thực thi |
| T-28 | WAF ở edge chặn request lab theo rule được phê duyệt | Chặn tại đúng điểm; backend không xử lý |
| T-29 | Request trực tiếp origin đi vòng WAF | Không reachable theo policy |
| T-30 | Rate limiting qua nhiều gateway replicas | Semantics/aggregation phù hợp kỳ vọng, không nới limit ngoài ý |
| T-31 | Gateway autoscale/rollout | Public listener và upstream auth vẫn hoạt động |
| T-32 | Một AZ/backend endpoint bị mất trong lab | HA/failover theo thiết kế, không mở fail-open |
| T-33 | External auth/JWKS service tạm unavailable trong lab | Cache/fail policy an toàn, không tự allow-all |
| T-34 | Sidecar ↔ ambient mode hoặc policy principal path khác | Mesh identity/enforcement được test đúng mode |
| T-35 | Certificate/key Secret bị thay đổi trái phép trong lab | RBAC/admission/audit/alert phát hiện |
| T-36 | Một HTTPRoute/Gateway/Service type bị thay đổi ngoài IaC | Drift detection và owner review |
| T-37 | CDN/edge DNS cutover với A/AAAA khác nhau | Cả hai families dùng đúng bảo vệ mới |
| T-38 | Tới admin/health/metrics listener từ Internet | Deny hoặc chỉ expose nội dung tối thiểu theo policy |
| T-39 | Hybrid/VPN partner tới internal gateway | Chỉ được các host/port/API scope được duyệt |
| T-40 | Client request timeout tại backend nhưng gateway route hợp lệ | Khoanh vùng tới endpoints/TLS/NetworkPolicy, không nhầm DNS |

### 25.2. Bằng chứng bắt buộc cho mỗi test

1. **Environment, authorization**, source location và request ID.
2. **Public DNS/hostname, A/AAAA, listener/LB**, TLS mode và certificate identity.
3. **GatewayClass/Gateway/HTTPRoute** status, route/ReferenceGrant và config version.
4. **Mesh mode**, gateway/backend workload principal và mTLS policy.
5. **Kubernetes NetworkPolicy, cloud firewall, WAF** nào có trách nhiệm cho allow/deny.
6. **API auth outcome** gồm audience/scope/object/tenant nếu liên quan.
7. **Flow/route/backend logs** tại đúng điểm kiểm tra, không chứa credentials.
8. **Expected và observed result**, ảnh hưởng tới client hợp lệ và rollback plan.

### 25.3. Không nhầm lớp bị chặn

Một HTTP 404 có thể do route không khớp, không tồn tại application resource hoặc policy ẩn tài nguyên. Một HTTP 403 có thể do gateway, mesh AuthZ hoặc backend. **Chỉ status code không chứng minh rule nào đang bảo vệ**. Cần kiểm tra **policy verdict và request path**.

### 25.4. Kiểm thử qua IPv4 và IPv6

Nếu hệ thống dùng dual-stack, mỗi ca exposure quan trọng nên được chạy ở **cả A/IPv4 và AAAA/IPv6** theo khả năng. Một origin bị khóa ở IPv4 nhưng mở ở IPv6 có thể làm sai toàn bộ kết luận “chỉ có đường gateway”.

### 25.5. Không dùng test gây gián đoạn

Để xác minh DDoS protection/capacity, ưu tiên **tài liệu kiểm định, traffic mô phỏng thấp, canary và test được nhà cung cấp phê duyệt**. Không thử volumetric flood, TLS handshake exhaustion hoặc ép cạn connection pool trên public production endpoints.

## 26. Case study: gateway có mTLS nhưng dữ liệu vẫn có thể bị truy cập sai

**Bối cảnh:** Hệ thống có public API **api.example.test/orders** qua CDN/WAF và mesh ingress gateway. Orders API ở namespace payments, mTLS STRICT đã bật. Nhóm phát triển xem một request trả 200 qua Gateway rồi khẳng định **không còn đường nào truy cập trực tiếp Orders**.

Trong một lần rà soát, phát hiện hai vấn đề:

1. **Orders API có Service type LoadBalancer cũ**, trực tiếp nhận traffic từ một dải đối tác ngoài đường WAF.
2. Backend có mesh AuthorizationPolicy cho phép **mọi workload trong một namespace internal-tools**, vì nhóm test tạm mở rộng quyền, trong khi app chỉ kiểm tra scope **orders.read** nhưng không kiểm tra **tenant của đơn hàng**.

### 26.1. Phân tích vấn đề thứ nhất: exposure

Một public LB cũ có thể cho client tới backend mà không qua WAF/gateway. Nếu backend proxy bắt buộc mTLS, client ngoài mesh có thể bị từ chối; nhưng **đó là biện pháp giảm thiểu**, không chứng minh public exposure được phê duyệt. Cần xem:

- LB listener/route có thật sự reach backend không?
- Backend có cổng/Pod nào **không nằm trong mesh** hoặc đường không bị STRICT mTLS bao phủ không?
- Có alternate public IPv6 listener không?
- Auth policy có áp vào cùng workload/port không?

**Không suy “public LoadBalancer tồn tại ⇒ dữ liệu bị lộ”** nếu chưa có bằng chứng truy cập. Nhưng cũng không được bỏ qua risk chỉ vì một phép thử thất bại.

### 26.2. Phân tích vấn đề thứ hai: danh tính workload

Một internal-tools Pod có mesh certificate hợp lệ **không đồng nghĩa** nó có quyền gọi API của payments. Mesh AuthZ cho phép một namespace quá rộng có thể vô tình tạo đường lateral movement, đặc biệt khi namespace chứa workloads có quyền thay labels hoặc tạo Pods.

Giới hạn principal theo **service account/workload identity cụ thể**, operation/port được phê duyệt và mô hình kết nối nội bộ. Không chỉ dựa vào nguồn IP private hoặc namespace name.

### 26.3. Phân tích vấn đề thứ ba: authorization dữ liệu

Giả sử user A có token **aud=Orders**, **scope=orders.read**, nhưng endpoint **GET /orders/{id}** không kiểm tra owner hoặc tenant. Dù network/mTLS hoàn toàn đúng, user A vẫn có thể yêu cầu xem một đơn hàng thuộc user B nếu backend xử lý ID mà không có resource authorization.

**Gateway xác minh token ở tầng coarse-grained; backend phải kiểm tra object/tenant/business policy.**

### 26.4. Kiến trúc sau khi sửa

~~~mermaid
flowchart LR
    U["Public client"] -->|"HTTPS only"| EDGE["Approved CDN/WAF"]
    EDGE -->|"Approved LB route"| GW["Mesh ingress gateway"]
    GW -->|"Verified mesh mTLS + allowed principal"| API["Orders API"]
    API -->|"Object/tenant authorization"| DB[("Orders database")]
    LEGACY["Legacy public LB"] -. "Removed/blocked by exposure policy" .-> API
    TOOLS["Unapproved tools workload"] -. "Mesh AuthZ/NetworkPolicy deny" .-> API
    U -. "Wrong audience/scope/tenant denied" .-> API
~~~

### 26.5. Tiêu chí nghiệm thu

- Chỉ những public listeners được phê duyệt còn hoạt động.
- Không có đường **public backend bypass**, gồm IPv6 và legacy LBs.
- Mesh mTLS xác thực gateway identity; **chỉ principals đã duyệt** được gọi Orders.
- External token được kiểm tra issuer/audience/scope; user không truy cập được object/tenant ngoài quyền.
- Gateway, mesh, application và cloud logs liên kết được theo request ID.
- Kiểm thử allow lẫn deny pass, không chỉ dựa vào request thành công.

## 27. Rollout, High Availability và governance

### 27.1. Quản trị thay đổi cấu hình

Rủi ro của public gateway không chỉ từ packet path mà còn từ quyền cấu hình **Gateway, HTTPRoute, Service, Secret, mesh policy và cloud firewall**. Một đường public có thể xuất hiện do Helm value sai hoặc một controller tạo LoadBalancer mới.

Áp dụng quy trình:

1. **Asset inventory:** hostname, cert, public LB/IP, Services, routes, owners.
2. **Threat modeling:** nguồn Internet/partner/internal và dữ liệu/operations nhạy cảm.
3. **Policy specification:** host/path/listener/mTLS/client auth requirements.
4. **GitOps/IaC review:** Gateway/HTTPRoute/ReferenceGrant, TLS secrets, mesh AuthZ và firewall policies.
5. **Admission/guardrails:** cảnh báo backend Service type LoadBalancer, wildcard route, TLS Secret ngoài danh mục.
6. **Staging/canary:** kiểm thử route/handshake/auth và negative public exposure.
7. **Production rollout:** theo dõi 4xx/5xx, TLS errors, WAF decisions, mTLS, origin traffic.
8. **Rollback:** biết cách quay về chính sách trước mà không tạo public alternate path.
9. **Continuous audit:** kiểm tra route/cert/exposure drift và ngoại lệ có expiry.

### 27.2. Nhiều gateway replicas và multi-zone

Một gateway đơn có thể là single point of failure. Cần đánh giá:

- Số replicas, pod disruption budget, readiness/liveness/startup probes.
- LB target health, node/zone placement và autoscaling.
- Config/Secret/certificate consistency trên replicas.
- Backend endpoint health, circuit breaking/retries với giới hạn phù hợp.
- Rate-limit state được chia sẻ giữa replicas khi cần quota global.
- Failover route có giữ nguyên **WAF, TLS và authorization** hay không.

### 27.3. Health checks không được thành đường quản trị

LB cần health probes, nhưng một endpoint như **/healthz** không nên trả secrets, cluster inventory hoặc thông tin người dùng. Các metrics/admin interfaces như **/metrics, /debug, admin dashboard** cần được bảo vệ riêng, không mặc nhiên public cùng listener 443.

### 27.4. Rollback có thể làm mất an toàn

Nếu một route mới yêu cầu JWT/mTLS, rollback về revision cũ có thể bỏ các kiểm tra. Vì vậy **rollback plan** phải bao gồm **authorization and exposure invariants**, không chỉ đưa hệ thống trở lại HTTP 200. Sau rollback cần chạy lại negative tests cho unknown hosts, missing scopes và direct backend paths.

### 27.5. Đánh giá thay đổi cấu trúc service mesh

Khi nâng cấp controller, thay GatewayClass, đổi sidecar/ambient, đổi trust domain hoặc certificate issuer, cần chạy lại:

- HTTPS/SNI/Host routing và certificate rotation.
- Route/ReferenceGrant/allowedRoutes acceptance.
- Upstream mTLS trust and workload principals.
- Backend policy enforcement ở đúng mode.
- WAF/forwarded headers và public LoadBalancer coverage.
- Cross-node, multi-zone, IPv4/IPv6 và gateway failover.

## 28. Những sai lầm phổ biến

| Sai lầm | Hậu quả | Cách nhìn và kiểm soát đúng |
| --- | --- | --- |
| “Có ingress gateway là mọi backend chỉ truy cập qua gateway” | NodePort, public LB, VPN hoặc Pod-to-Pod bypass | Kiểm kê toàn bộ đường, cloud firewall + NetworkPolicy |
| “Service type ClusterIP nghĩa là private tuyệt đối” | Vẫn có thể proxy/forward qua nguồn khác | Kiểm tra Service graph, RBAC và network reachability |
| “mTLS gateway→backend chứng minh user đã xác thực” | Nhầm service identity với external client/user | Xác thực external token/client cert riêng |
| “Mesh mTLS là quyền gọi mọi API” | Lateral movement giữa workloads có cert hợp lệ | Mesh principal authorization và API authorization |
| “STRICT mTLS tự chặn mọi đường bypass” | Workload không enrolled/alternate port/other mesh principal | Enforce coverage và test per path |
| “TLS terminate ở gateway nghĩa là mã hóa end-to-end nguyên phiên” | Chặng gateway→backend có thể plaintext | Kiểm tra transport và TLS upstream riêng |
| “TLS passthrough vẫn áp HTTP JWT/WAF tại gateway” | Proxy không thấy HTTP payload | Terminate TLS ở điểm cần L7 hoặc áp auth tại backend |
| “Gateway API HTTPS tự bật mesh mTLS” | Backend connection chưa được bảo vệ như mong muốn | Kiểm chứng mesh enrollment/upstream policy |
| “Có Gateway object là controller đã program route” | Config chưa được chấp nhận hoặc refs lỗi | Kiểm tra conditions và runtime tests |
| “allowedRoutes cho phép user được gọi API” | Nhầm route attachment với request authorization | Tách Gateway config policy khỏi API auth |
| “ReferenceGrant là firewall” | Chỉ cấp quyền tham chiếu cấu hình, không lọc packet | NetworkPolicy/cloud firewall/mTLS/AuthZ |
| “Tất cả teams đều có thể gắn routes vào shared gateway” | Route conflicts/domain hijack | allowedRoutes, hostname ownership, RBAC/admission |
| “Wildcard cert nghĩa là mọi hostname được route” | Host/tenant routing quá rộng | Hostname allowlist, tenant auth, route ownership |
| “X-Forwarded-For luôn là IP thật của client” | Giả mạo client identity/rate-limit keys | Trusted proxy chain và sanitize |
| “Public DNS không có record nên backend không public” | IP/alternate host/IPv6 vẫn truy cập được | Cloud listener/route inventory, negative tests |
| “WAF bảo vệ cả backend trực tiếp” | Origin bypass không qua WAF | Origin restrictions/mesh/network controls |
| “CORS thay thế API authorization” | Clients ngoài browser vẫn gọi được | Server-side auth và resource-level checks |
| “Rate limiting thay object authorization” | Request ít vẫn có thể đọc sai tenant | API resource authorization |
| “JWT signature hợp lệ là đủ” | Token sai audience/scope có thể bị chấp nhận | Verify issuer, token type, audience, time, scopes |
| “HTTP 403 chứng minh gateway đã chặn” | Backend có thể nhận rồi từ chối | Đối chiếu proxy/app verdict và request ID |
| “HTTP 200 chứng minh public route an toàn” | Không kiểm tra được đường trái quyền | Negative tests direct backend/unknown host |
| “Pod label là danh tính service được xác thực” | Labels có thể bị cấu hình hoặc lạm dụng | RBAC/admission, mTLS workload principal |
| “IPv4 private nghĩa là IPv6 cũng private” | AAAA/public IPv6 path mở | Test dual-stack DNS/LB/firewall |
| “Rollback route luôn an toàn” | Revision cũ có policy yếu hơn | Rollback acceptance tests và security invariants |
| “Một gateway replica đủ vì cloud LB có HA” | Replica đơn vẫn có thể bị mất | Multi-replica/multi-zone plan, health checks |
| “Ingress gateway và egress gateway là cùng vai trò” | Sai hướng traffic và policy scope | Phân biệt north–south ingress với outbound egress |

## 29. Câu hỏi ôn tập và bài tập thiết kế

### Câu hỏi 1 – Ingress gateway khác LoadBalancer Service như thế nào?

**Gợi ý:** LoadBalancer Service tạo/định nghĩa đường kết nối bên ngoài theo controller; gateway có thể áp routing/TLS/auth và tích hợp mesh. Hai lớp có thể phối hợp nhưng không tự tương đương.

### Câu hỏi 2 – Vì sao backend không có public IP vẫn cần kiểm tra bypass?

**Gợi ý:** NodePort, alternate LoadBalancer, Ingress/Gateway khác, VPN/peering hoặc network path nội bộ vẫn có thể chuyển traffic tới backend.

### Câu hỏi 3 – TLS termination và TLS passthrough ảnh hưởng thế nào đến HTTP WAF?

**Gợi ý:** proxy phải quan sát được HTTP sau khi giải mã thì mới áp HTTP payload/path/header rules; passthrough không đọc HTTP payload.

### Câu hỏi 4 – mTLS client→gateway và mTLS gateway→backend xác thực hai chủ thể nào?

**Gợi ý:** đường ngoài có thể xác thực partner/client certificate; đường mesh xác thực các workload peers. Đừng coi gateway principal là user.

### Câu hỏi 5 – Vì sao backend yêu cầu STRICT mTLS vẫn cần mesh AuthorizationPolicy?

**Gợi ý:** tất cả mesh workloads có chứng thư hợp lệ không nhất thiết đều được phép gọi backend nhạy cảm.

### Câu hỏi 6 – Gateway API allowedRoutes và ReferenceGrant khác nhau ra sao?

**Gợi ý:** allowedRoutes kiểm soát Route attachment vào Gateway listener; ReferenceGrant kiểm soát những cross-namespace resource references cần cấp phép.

### Câu hỏi 7 – Tại sao một HTTPRoute HTTPS ở public Gateway không tự có mTLS đến backend?

**Gợi ý:** HTTPS listener mô tả client-facing TLS; backend TLS/mTLS cần cấu hình/enrollment và được xác minh riêng.

### Câu hỏi 8 – SNI và HTTP Host có thể không trùng nhau không?

**Gợi ý:** có; listener routing/hostname policy phải xử lý mismatch và không route unknown-host tới admin backend.

### Câu hỏi 9 – Vì sao X-Forwarded-For không thể tin vô điều kiện?

**Gợi ý:** client có thể tự gửi header; chỉ tin phần metadata được trusted proxies quản lý đúng chain.

### Câu hỏi 10 – Khi nào một public IPv6 listener có thể làm hỏng chính sách “chỉ qua WAF”?

**Gợi ý:** A record qua WAF nhưng AAAA hoặc route IPv6 trỏ thẳng origin/backend.

### Câu hỏi 11 – Khi một request trả HTTP 403, cần dữ liệu gì để biết lớp nào đã từ chối?

**Gợi ý:** request ID, gateway/mesh policy verdict, JWT validation result, backend business authorization logs.

### Câu hỏi 12 – Vì sao một policy NetworkPolicy chỉ cho gateway Pod vẫn không thay API authorization?

**Gợi ý:** mọi request đi qua gateway đều có thể mang người dùng/quyền khác nhau; backend phải kiểm tra user, tenant và object.

### Câu hỏi 13 – HostPort/NodePort và hostNetwork phải được kiểm tra ra sao?

**Gợi ý:** inventory cloud/node listeners và policy đặc thù host path; không coi NetworkPolicy Pod-based là đủ cho mọi packet.

### Câu hỏi 14 – Ambient mesh thay đổi suy luận về Gateway→backend policy như thế nào?

**Gợi ý:** dataplane L4, waypoint L7 và peer identity tại hook có thể khác sidecar; phải kiểm tra cấu hình và effective enforcement.

### Câu hỏi 15 – Nếu backend access log có request nhưng không thấy ở gateway log, có thể kết luận bypass chưa?

**Gợi ý:** chưa. Có thể là log sampling, mất correlation hoặc đường nội bộ hợp lệ; phải đối chiếu identity/path/coverage.

### Câu hỏi 16 – Tại sao không nên cấp quyền thay gateway TLS Secret cho mọi HTTPRoute author?

**Gợi ý:** có thể thay server identity, rò private key hoặc gây outage; tách quyền certificate operations và route ownership.

### Bài tập thiết kế kiến trúc

Một hệ thống thương mại điện tử có **public checkout**, **Orders API**, **Billing API**, **PostgreSQL**, một **service mesh**, Kubernetes **Gateway API**, public cloud load balancer, CDN/WAF và kết nối đối tác qua VPN. Gateway phục vụ khách hàng Internet và có một listener riêng cho API đối tác yêu cầu client certificate.

Hãy thực hiện:

1. Vẽ **client → DNS/CDN/WAF/LB → ingress gateway → mesh workload → data** và chỉ rõ TLS termination/passthrough ở từng hop.
2. Liệt kê **public exposure inventory**: hostname, IPv4/IPv6, listeners, Services, NodePorts, origins, private VPN routes.
3. Thiết kế **GatewayClass/Gateway/HTTPRoute**, giới hạn hostnames/listeners và route attachment.
4. Mô tả **ReferenceGrant** khi Route trong namespace edge tham chiếu backend ở payments.
5. Thiết kế **mTLS cho gateway→Orders/Billing**, gồm workload identities, trust domain, policy chỉ cho gateway gọi backend.
6. Mô tả **client→partner gateway mTLS**: client CA, certificate mapping và khả năng thu hồi.
7. Phân biệt **TLS, mesh mTLS, JWT audience/scope và resource-level authorization** của Orders/Billing.
8. Thiết kế **NetworkPolicy/cloud firewall** để chặn direct backend origin và bảo vệ node/host/public LoadBalancer paths.
9. Định nghĩa **trusted proxy chain** và cách sử dụng X-Forwarded-For/Forwarded/PROXY protocol một cách an toàn.
10. Tính đến gRPC/WebSocket nếu sử dụng: connection lifetime, method authorization, request limits.
11. Đề xuất quyền cho ba nhóm **platform, security, application** đối với Gateway, routes, TLS Secrets, mesh policies và IAM.
12. Lập ít nhất **mười positive/negative tests** cho unknown hosts, wrong audience, missing scope, wrong principal, IPv6 bypass, NodePort và certificate expiry.
13. Thiết kế correlation giữa **cloud LB, WAF, gateway, mesh policy và API/database logs**.
14. Viết runbook khi xuất hiện Service type LoadBalancer mới làm lộ Orders API ngoài WAF.
15. Đặt tiêu chí rollout/rollback và security gates trước khi đổi gateway controller, mesh mode hoặc trust domain.

**Tiêu chí đạt:** **một và chỉ những đường public đã phê duyệt được phục vụ**, gateway/backend bảo đảm TLS và danh tính đúng, người gọi được kiểm tra đúng quyền, còn **backend alternate paths không được phép bị chặn và có telemetry chứng minh**.

## 30. Những điều cần ghi nhớ

- **Ingress gateway là điểm vào logic**, còn public exposure là thuộc tính của **mọi đường có thể đến tài nguyên**; phải kiểm kê cả LoadBalancer, NodePort, origin, IPv6 và hybrid routes.
- **Cloud LoadBalancer, Kubernetes Ingress/Gateway API, mesh gateway và WAF có trách nhiệm khác nhau**; một tài nguyên cấu hình không tự bảo đảm mọi lớp đã enforce.
- **TLS termination, passthrough và re-encryption có ranh giới khác nhau**; không khẳng định WAF/JWT L7 policy hoạt động ở một proxy không giải mã HTTP.
- **mTLS client→gateway và mTLS gateway→workload xác thực các peers khác nhau**; mesh identity của gateway không phải danh tính user Internet.
- **STRICT mTLS chưa đủ** nếu workload khác trong mesh được phép gọi backend; cần authorization theo **principal và operation**.
- **Gateway API allowedRoutes kiểm soát route attachment; ReferenceGrant kiểm soát tham chiếu liên namespace**, không thay application authorization.
- **Route host/SNI/path, TLS secrets và forwarded headers phải nằm trong trust boundary được cấu hình**; không tin metadata do client tự tạo.
- **Backend phải tiếp tục xác minh token audience/scope và resource/tenant rights**, ngay cả khi gateway đã xác thực người gọi.
- **NetworkPolicy/cloud firewall, WAF/DDoS, rate limiting, mesh policy và TLS** là các lớp bổ sung; không lớp nào thay hoàn toàn lớp khác.
- **Public IPv4/IPv6, alternate origins và host/NodePort paths** cần được kiểm thử độc lập để loại trừ đường bypass gateway.
- **Gateway API/controller, sidecar/ambient mesh và các policy extensions có semantics phụ thuộc triển khai**; cần kiểm tra status, mesh enrollment, policy verdict và đường đi thực tế.
- **Chứng thư, Gateway/HTTPRoute/ReferenceGrant, mesh policies và public LBs** cần owner, RBAC, IaC review, drift monitoring và quy trình rollback.
- **HTTP 200, HTTP 403 hoặc một log thiếu không đủ chứng minh trạng thái bảo mật**; phối hợp chứng cứ từ mạng, TLS, gateway, mesh và ứng dụng.
- **Bộ kiểm thử positive và negative trong môi trường được cấp phép** là nền tảng xác nhận luồng hợp lệ hoạt động và luồng trái quyền bị chặn tại đúng điểm.





