# Sidecar proxy và đường đi của request trong service mesh

## 1. Sidecar proxy là gì, và tại sao request không đi thẳng tới service?

Trong kiến trúc microservices, một ứng dụng có thể gọi hàng chục dịch vụ qua HTTP, gRPC hoặc TCP. Nếu mỗi ứng dụng tự triển khai **service discovery, TLS/mTLS, xác thực peer, retry, timeout, circuit breaking, cân bằng tải và telemetry**, những chức năng mạng sẽ khác nhau giữa các ngôn ngữ và phiên bản. **Service mesh** đưa một phần chức năng kết nối liên dịch vụ vào **data plane** vận hành theo chính sách tập trung, thường được quản lý bởi **control plane**.

Trong mô hình **sidecar**, một tiến trình proxy riêng (ví dụ Envoy hoặc proxy được mesh hỗ trợ) được chạy cùng **workload application**, phổ biến là trong **cùng Pod Kubernetes**. Ứng dụng vẫn xử lý nghiệp vụ; proxy có thể xử lý **kết nối outbound và inbound**, thiết lập mTLS tới proxy ở phía bên kia, thực thi chính sách hoặc thu thập telemetry theo cấu hình. Trên mỗi Pod, sidecar thường **chia sẻ network namespace với app**; vì vậy những packet đi/đến Pod có thể được định tuyến tới proxy trước khi tới process ứng dụng.

Ví dụ, ứng dụng **orders** gọi **payments**. Không có mesh, orders có thể mở kết nối trực tiếp tới payments. Có sidecar capture, đường đi logic thành:

~~~text
Orders app -> Orders sidecar -> network -> Payments sidecar -> Payments app
~~~

**Điểm quan trọng:** sidecar **không tự tạo thêm một hop mạng vật lý giữa hai Pod** nếu nó chạy trong cùng Pod, nhưng tạo thêm một hoặc nhiều **điểm xử lý TCP/TLS/HTTP trong đường dữ liệu**. Tùy cấu hình, kết nối app↔sidecar có thể **plaintext trên loopback/Pod network namespace**, còn proxy↔proxy được bảo vệ bằng **mTLS**. Vì vậy không được viết tắt thành “toàn bộ request luôn TLS end-to-end từ app tới app”.

Trong module **SECURITY_NETWORK_SECURITY**, hiểu request path qua sidecar là nền tảng để phân tích **phân đoạn mạng, firewall, identity, TLS/mTLS, IDS/IPS, tracing, cloud VPC flow logs và troubleshooting**. Chỉ nhìn IP đích hoặc một access log ở ingress rất dễ bỏ qua chính sách đang được thực thi ở proxy nào.

### Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân biệt **application container, sidecar, control plane và data plane**.
2. Vẽ **request path outbound/inbound** của HTTP, gRPC và TCP qua hai sidecars.
3. Giải thích **iptables REDIRECT/TPROXY, eBPF/CNI capture, proxy listeners, upstream clusters và endpoint selection** ở mức nguyên lý.
4. Xác định **nơi TLS kết thúc/khởi tạo, private key nằm ở đâu, danh tính mTLS được xác minh** và ranh giới plaintext.
5. Hiểu **discovery/xDS, routing, retries, timeouts, connection pooling và policy** tác động lên từng request.
6. Phân tích **source IP/NAT, DNS, DNS caching, service VIP, IPv4/IPv6, headless services** cùng những trường hợp bypass.
7. Thiết kế **telemetry, runbook và ma trận ALLOW/DENY** để kiểm chứng đường đi trong thực tế.

## 2. Các thành phần tham gia request path

| Thành phần | Vai trò | Thường chứa/biết gì? |
| --- | --- | --- |
| **Application container** | Sinh/xử lý HTTP/gRPC/TCP request, thực thi nghiệp vụ | User/tenant auth, business state, application logs |
| **Local sidecar proxy** | Nhận traffic được capture, áp routing/TLS/policy/telemetry | Local listeners, upstream clusters, mTLS identity |
| **Remote sidecar proxy** | Nhận traffic mạng vào Pod, xác minh mTLS và chuyển tới app | Peer identity, inbound authorization, inbound listeners |
| **Service discovery / endpoints** | Xác định địa chỉ và thành viên của service | Service VIP, Pod IP, DNS records, registry/EndpointSlices |
| **Mesh control plane** | Cấp cấu hình động và chứng chỉ/identity theo thiết kế | Service graph, policies, destinations, trust information |
| **CA / identity provider** | Cấp vật liệu xác thực workload | Service account/workload identity, cert chain |
| **CNI/network fabric** | Định tuyến Pod↔Pod và áp network policy | Pod/Node IP, overlay/underlay, NAT/routing state |
| **Ingress/egress gateway** | Điểm vào/ra riêng cho traffic qua mesh nếu được sử dụng | Public endpoint, TLS termination, route/egress policy |
| **Security/observability plane** | Phân tích flow, logs, tracing và sự cố | Source/dest metadata, request ID, auth decision |

### 2.1. Control plane khác data plane

**Control plane** cấu hình cho proxy biết **dịch vụ nào tồn tại, endpoint nào khỏe, cần dùng mTLS thế nào, timeout và policy ra sao**. **Data plane sidecar** trực tiếp nhận và xử lý traffic đang diễn ra.

~~~mermaid
flowchart TB
    CP["Mesh Control Plane"] -. "Service, routes, endpoints, policy, cert config" .-> SA["Orders Sidecar"]
    CP -. "Service, routes, endpoints, policy, cert config" .-> SB["Payments Sidecar"]
    APP1["Orders App"] --> SA
    SA ==>|"Mạng Pod-to-Pod / mTLS nếu cấu hình"| SB
    SB --> APP2["Payments App"]
~~~

**Không nên nghĩ request đi qua control plane mỗi lần gọi.** Sau khi nhận cấu hình, proxy có thể xử lý traffic trên **data plane mà không cần hỏi control plane cho từng request**. Khi control plane tạm không truy cập được, proxy có thể tiếp tục sử dụng cấu hình đã nhận **tùy product, thời gian certificate, trạng thái restart và policy**. Không suy data plane sẽ hoạt động vô hạn khi control plane bị lỗi.

### 2.2. Sidecar container không đồng nghĩa proxy luôn nằm trên đường đi

Một Pod có container proxy chưa chắc mọi packet được chuyển qua proxy: có thể có **port exclusions, CIDR bypass, hostNetwork traffic, các giao thức không được hỗ trợ, loopback gọi trực tiếp hoặc chính sách capture sai**. Ngược lại, mô hình **ambient/sidecarless** có thể đưa một số chức năng mesh vào node-level proxy mà không thêm sidecar vào mỗi Pod. Luôn kiểm tra **đường dữ liệu thực tế**, không kết luận chỉ từ nhãn “mesh enabled”.

## 3. Sơ đồ đầy đủ: HTTP request từ Orders tới Payments

Giả sử hai Pod ở cùng một cluster, gọi qua DNS service nội bộ, không có ingress/egress gateway chen giữa. Ví dụ mô hình **L7 sidecar proxy cả hai đầu**:

~~~mermaid
sequenceDiagram
    autonumber
    participant O as Orders App
    participant OS as Orders Sidecar
    participant N as K8s DNS/CNI
    participant PS as Payments Sidecar
    participant P as Payments App
    O->>N: Resolve payments.prod-apps.svc.cluster.local
    N-->>O: Service IP / resolution theo cluster
    O->>OS: HTTP request qua local capture
    OS->>OS: Match listener, route, policy, chọn upstream
    OS->>PS: New/reused TCP connection + mTLS nếu mesh policy
    PS->>PS: Validate peer identity + inbound authorization
    PS->>P: Forward local HTTP/TCP request
    P-->>PS: Application response
    PS-->>OS: Response qua kết nối proxy-proxy
    OS-->>O: Response/application error
~~~

### 3.1. Bảy bước ở tầng dữ liệu

1. **Application tạo request**, ví dụ HTTP/1.1 GET hoặc gRPC unary call tới một service name; client có thể dùng DNS, cached IP, SDK discovery hoặc service VIP.
2. **Local capture** chuyển socket/packets outbound sang listener của sidecar theo cơ chế CNI/iptables/eBPF/TPROXY hoặc SDK được sử dụng. **Không phải mọi triển khai capture theo cùng một cách**.
3. **Outbound proxy** xác định original destination/service và chọn route/cluster/endpoints theo cấu hình từ control plane hoặc cấu hình cục bộ.
4. **Outbound proxy tạo hoặc tái sử dụng connection** tới remote endpoint. Khi mesh sử dụng mTLS, proxy xác minh remote certificate/identity theo trust policy và trình diện identity của mình.
5. **Remote inbound proxy** nhận connection, xác minh peer, áp policy phù hợp như mTLS requirement và authorization rồi chuyển tới app listener.
6. **Payments app** xác thực người dùng/tenant hoặc nghiệp vụ theo yêu cầu riêng và tạo response.
7. **Response trở về** theo hai hướng qua proxies, có thể được ghi metric/tracing/logs; những retry hoặc timeout do proxy tạo có thể khiến ứng dụng nhìn thấy **một kết quả khác với một lần gọi backend**.

### 3.2. Service IP không phải chắc chắn là Pod IP đích

Kubernetes Service thường cung cấp **ClusterIP/VIP** và mapping tới endpoints; nhiều mesh có cơ chế **nhìn service identity/host** rồi chọn **Pod endpoint IP** từ metadata mà không đi qua kube-proxy DNAT ở mọi bước. Các cluster khác có thể dùng **kube-proxy, IPVS, eBPF hoặc CNI interception**. Không cho rằng một packet outbound từ sidecar luôn có dst=ClusterIP ở mọi hop.

### 3.3. mTLS được xác lập ở bước nào?

Thông thường trong mô hình sidecar-to-sidecar, **Orders sidecar và Payments sidecar** là hai đầu của phiên mTLS. App có thể chỉ thấy HTTP trên localhost, còn proxies thấy nội dung ứng dụng khi xử lý L7. Nếu app thiết lập **application-level end-to-end TLS riêng** xuyên proxy passthrough, mức nhìn L7 của mesh có thể thay đổi. Phải xác minh **ai terminate TLS và ai nắm private key** ở từng hop.

## 4. Traffic capture: tại sao socket của app đi vào sidecar?

Với mô hình transparent interception, ứng dụng không cần đổi URL sang proxy address. CNI/init container hoặc agent cấu hình **network namespace và luật chuyển hướng** để traffic phù hợp đi vào proxy. Hai họ cơ chế thường được nhắc:

- **Netfilter/iptables REDIRECT:** thay destination port/address ở nơi thích hợp, để packet đến inbound/outbound listener cục bộ. Proxy phải có cách suy ra **original destination** hoặc mapping do hệ thống cung cấp.
- **TPROXY / policy routing:** chuyển traffic tới proxy với khả năng giữ nguyên thông tin destination gốc theo mô hình phù hợp; cần routing/sockets/capabilities và cấu hình tương ứng.
- **eBPF/CNI-based capture:** có thể dùng hooks ở kernel/network stack để điều hướng flow, theo thực thi của CNI/mesh; không mặc định có cùng semantics với REDIRECT.
- **Explicit proxy/SDK:** app có thể cấu hình HTTP_PROXY, gRPC proxy/interceptor hoặc library; lúc đó không nhất thiết cần transparent capture.

~~~mermaid
flowchart LR
    A["Orders process: connect payments:443"] --> K{"Capture rule / CNI"}
    K -->|"Proxy this traffic"| L["Local outbound listener"]
    K -->|"Excluded/bypass"| R["Original network path"]
    L --> D["Routing & mTLS origination"]
    D --> P["Remote Pod / gateway"]
    R --> P
~~~

### 4.1. Capture scope là phần phải kiểm thử

| Loại traffic | Câu hỏi cần trả lời |
| --- | --- |
| **Pod egress TCP** | Port/IP nào được capture, có exclusion không? |
| **Pod ingress TCP** | Traffic đến app port đi vào inbound proxy hay tới app trực tiếp? |
| **Loopback** | App gọi 127.0.0.1 hoặc ::1 có bypass không? |
| **Pod-to-Pod direct IP** | Gọi Pod IP có qua proxy, bị deny hay chuyển theo passthrough? |
| **Pod-to-Service VIP** | Proxy có nhận biết service metadata và load balance không? |
| **DNS UDP/TCP 53** | DNS query đi qua resolver/capture nào, có DNS proxy không? |
| **UDP/QUIC/ICMP** | Implementation có hỗ trợ không? Không mặc định sidecar TCP hiểu mọi UDP |
| **HostNetwork/NodeLocal** | Có nằm ngoài Pod capture policy thông thường không? |
| **IPv6** | Capture, service discovery và policy có bao phủ dual-stack không? |
| **Init/ephemeral containers** | Kết nối của chúng có thuộc cùng network namespace/capture? |

**Không tự thêm một iptables rule tùy ý vào Production để thử bypass.** Đây là thay đổi có thể làm gián đoạn dịch vụ và an ninh. Ưu tiên xem cấu hình capture, proxy config và sử dụng lab/staging được phép để kiểm thử.

### 4.2. Capture và authorization khác nhau

Lưu lượng bị **redirect vào proxy** không có nghĩa đã được **cho phép**. Sau capture, proxy còn áp policy mTLS, identity, L4/L7 authorization và định tuyến. Ngược lại, **lưu lượng bypass proxy** có thể bỏ qua policy được thực thi duy nhất ở proxy; cần **NetworkPolicy/cloud firewall/backend auth** làm lớp bảo vệ độc lập.

## 5. Outbound path chi tiết: app → local sidecar → remote endpoint

Một proxy L7 phổ biến có các khái niệm:

- **Listener:** địa chỉ/port mà proxy nhận kết nối.
- **Filter chain / network filter:** xử lý một connection, TLS, protocol detection, TCP proxy hoặc HTTP connection manager.
- **HTTP route:** so host/path/header/method và chọn destination hoặc policy.
- **Cluster:** tập hợp upstream có đặc tính timeout, TLS, cân bằng tải, connection pool.
- **Endpoint:** địa chỉ/port cụ thể của backend Pod/VM/gateway.
- **Transport socket/TLS context:** các cài đặt bảo mật cho upstream connection.

~~~text
Application socket
    |
Capture to outbound listener
    |
Original destination / SNI / HTTP authority / protocol metadata
    |
Filter chain -> route match
    |
Destination cluster -> selected endpoint -> connection pool
    |
TLS/mTLS origination (nếu enabled & policy hợp lệ)
    |
Cloud/CNI network -> remote sidecar/endpoint
~~~

### 5.1. Phân loại L4 và L7

Nếu proxy nhận được **HTTP plaintext hoặc tự kết thúc TLS**, nó có thể route theo **:authority/Host, path, header, gRPC method**. Nếu chỉ xử lý một **opaque TCP stream**, nó vẫn có thể chọn upstream theo **IP/port/SNI được phép quan sát**, nhưng không thể kiểm tra HTTP body hoặc application authorization chỉ từ ciphertext.

**Protocol sniffing** có thể giúp proxy tự nhận HTTP/TCP trong một số môi trường, nhưng có thể gây **timeout, unexpected fallback hoặc định tuyến sai** với protocol riêng, byte prefix tương tự HTTP hoặc TLS không tương thích. Với dịch vụ quan trọng nên khai báo **service port names/app protocol** rõ theo implementation và kiểm tra thực tế.

### 5.2. Service discovery và endpoint selection

Control plane có thể thông báo rằng payments có những endpoints:

~~~text
Service identity: payments.prod-apps.svc.cluster.local
Cluster:         payments-prod
Endpoints:       10.20.0.11:8080, 10.20.0.12:8080
Traffic policy:  mTLS to peer identity payments
Route behavior:  timeout 2 s, no retries for unsafe POST by default
~~~

Địa chỉ trong ví dụ là **private IP mô phỏng**. Nếu Pod 10.20.0.11 không ready, control plane/proxy có thể loại endpoint theo cơ chế health/discovery; nhưng **endpoint cập nhật chậm, stale connection pool hoặc health policy khác** vẫn có thể gây 503. Không mặc định Kubernetes readiness và proxy endpoint health có semantics hoàn toàn giống nhau.

### 5.3. Source identity khác source IP

Trên proxy-to-proxy connection, phía nhận có thể thấy **source IP là Pod/node/proxy address** do CNI/NAT, trong khi mTLS peer certificate chứng minh **workload identity**. Đối với authorization giữa services, identity được xác minh bằng mật mã thường tin cậy hơn **chỉ dùng IP**, vốn có thể thay đổi khi Pod scale, NAT hoặc kết nối qua gateway. Tuy nhiên certificate valid vẫn chưa đủ; cần **authorization per service/method/tenant**.

## 6. Inbound path chi tiết: remote sidecar → local app

Khi kết nối tới Payments Pod, traffic được chuyển vào **inbound listener** theo quy tắc capture của Pod đó. Proxy có thể:

1. Xác định **TLS/mTLS mode** và hoàn thành handshake nếu được cấu hình.
2. Xác thực **certificate chain, trust domain, expiry và peer service identity** theo chính sách.
3. Áp **authorization policy** dựa trên workload principal và thông tin HTTP/RPC nếu nhìn được.
4. Thực hiện **rate/connection limits hoặc telemetry** ở nơi proxy có chức năng đó.
5. Chuyển connection/request đến **Payments app port** nội bộ.
6. Trả application response ngược qua đường proxy tới remote client.

~~~mermaid
flowchart LR
    N["Network packet to Payments Pod"] --> C["Inbound capture"]
    C --> S["Payments Sidecar"]
    S --> I{"Peer authn + authz"}
    I -->|"ALLOW"| A["Payments app: :8080"]
    I -->|"DENY"| D["Reject / policy response"]
    A --> S
~~~

### 6.1. Inbound local hop vẫn cần đánh giá

Chặng **inbound sidecar → local app** có thể là một kết nối trên loopback tới app port; không vì mTLS kết thúc ở sidecar mà kết luận mọi byte giữa proxy và app được mã hóa. Trong cùng network namespace, process có quyền tương ứng có thể quan sát hoặc gọi localhost app tùy OS/capabilities/namespace. Cần:

- **Pod hardening** và hạn chế extra containers/ephemeral debugging.
- Ứng dụng vẫn thực hiện **authorization của người dùng và tài nguyên**, không dựa vào IP localhost.
- Hạn chế **direct app port bypass** ngoài luồng mesh, dựa trên network policy và cấu hình capture thực tế.
- Không chuyển **X-User/X-Role** hoặc header identity do client tự đặt thành principal đáng tin khi không xác minh nguồn.

### 6.2. mTLS bị từ chối ở inbound không đồng nghĩa backend đã nhận request

Nếu inbound proxy từ chối do **unknown CA, expired cert, wrong peer identity hoặc authorization deny**, **Payments app có thể hoàn toàn không thấy request**. Lỗi client có thể là TLS reset, gRPC UNAVAILABLE/PERMISSION_DENIED, HTTP 403/503 hoặc code khác tùy điểm từ chối và giao thức. Cần xem **proxy logs/counters, policy revision, peer identity và app logs** trước khi kết luận nguyên nhân.

## 7. DNS, service names và các đường chuyển tới backend

DNS ở Kubernetes thường giải tên **service.namespace.svc.cluster.local** sang **ClusterIP** hoặc danh sách endpoint addresses với headless service, theo cấu hình và service type. Nhưng DNS lookup **không nhất thiết do sidecar thực hiện**: ứng dụng, libc, SDK, DNS proxy, node resolver hoặc service-discovery mechanism có thể tham gia.

| Mô hình | Đường đi điển hình | Lưu ý |
| --- | --- | --- |
| **ClusterIP Service** | Client resolve service name → VIP; capture/mesh chọn upstream | Kube-proxy/eBPF/mesh có thể tham gia trước/sau interception |
| **Headless Service** | DNS trả các Pod IP/endpoints | Client có thể chọn IP trực tiếp; traffic policy vẫn cần được áp |
| **Direct Pod IP** | App connect địa chỉ Pod | Có thể làm thay đổi route identity, không nên dùng để tránh mesh policy |
| **External DNS hostname** | App resolve public/private IP, đi qua egress sidecar/gateway tùy policy | DNS không tự cung cấp xác thực peer |
| **ServiceEntry/external registry** | Control plane khai báo endpoint ngoài mesh theo implementation | Cấu hình thiếu có thể tạo passthrough/blackhole ngoài dự kiến |
| **Multi-cluster service** | Định tuyến tới endpoint/cluster khác qua gateways hoặc cross-network | Cần trust domain, DNS, reachability và network policy phù hợp |

### 7.1. DNS cache và route cache là hai thứ khác nhau

Một ứng dụng có thể **cache DNS answer** và dùng IP cũ, trong khi sidecar nhận **endpoint update** từ control plane. Ngược lại, ứng dụng có thể resolve đúng DNS mới nhưng sidecar còn **stale cluster state** hoặc kết nối pool tới backend cũ. Khi điều tra “Pod đã xóa nhưng request vẫn tới IP cũ”, hãy so **DNS TTL, SDK caching, xDS endpoint updates, connection reuse và kube-proxy/CNI rules**.

### 7.2. TLS hostname validation và workload identity

Nếu proxy dùng mTLS workload identity để kết nối đến peer, việc DNS trả đúng IP **không tự chứng minh** peer là service payments. Phải kiểm tra **peer identity phù hợp expected service**, certificate chain và authorization. Nếu ứng dụng tự tạo TLS end-to-end song song, hostname/SAN validation của **app** cũng cần đúng. Hai cơ chế có thể cùng tồn tại hoặc cấu hình xung đột, cần vẽ rõ termination points.

## 8. Service identity, mTLS handshake và những điểm thấy plaintext

Trong mô hình service mesh sidecar, chứng chỉ thường gắn với **workload/service account identity** thay vì chỉ một IP Pod. **SPIFFE ID/SVID** là một mô hình phổ biến, hoặc nền tảng có cơ chế workload identity tương đương. Danh tính được cấp và kiểm tra theo **trust domain, CA/issuer, subject và policy**.

~~~mermaid
sequenceDiagram
    participant OA as Orders App
    participant OP as Orders Proxy
    participant PP as Payments Proxy
    participant PA as Payments App
    OA->>OP: HTTP/gRPC plaintext trên local hop trong mô hình này
    OP->>PP: TLS ClientHello
    PP-->>OP: TLS certificate chain / handshake
    OP->>OP: Verify CA/trust and expected Payments identity
    OP-->>PP: Present Orders workload certificate
    PP->>PP: Verify CA/trust, Orders identity + auth policy
    OP->>PP: Encrypted application request (mTLS channel)
    PP->>PA: Application request on local hop
    PA-->>PP: Application response
    PP-->>OP: Encrypted response
    OP-->>OA: Response to application
~~~

Sơ đồ thể hiện **quan hệ logic**, không phải tuần tự gói TLS chính xác theo từng phiên bản. TLS 1.3 và TLS 1.2 có handshake/key schedule khác nhau, và **connection reuse** khiến các HTTP requests sau không handshake lại mỗi lần. Phần quan trọng là **ai có private key, ai kiểm tra peer identity và plaintext ở đâu**.

### 8.1. Bản đồ tin cậy của từng chặng

| Chặng | Mã hóa/xác thực thường gặp | Ai có thể thấy HTTP payload? |
| --- | --- | --- |
| Orders app → local sidecar | Nhiều mesh dùng loopback plaintext; có ngoại lệ app TLS | App, proxy và process có quyền ở local boundary |
| Orders sidecar → Payments sidecar | mTLS khi policy và implementation hỗ trợ, peer verification | Không thể đọc plaintext chỉ bằng quan sát packet ngoài đường truyền |
| Payments sidecar → Payments app | Thường loopback plaintext; có thể app TLS riêng | Proxy, app và process có quyền ở local boundary |
| Client ngoài → ingress gateway | TLS/mTLS theo endpoint; không nhất thiết là mesh workload identity | Ingress điểm termination và app phía sau tương ứng |
| Egress gateway → external service | TLS tới external hostname nếu cấu hình và verify đúng | Egress gateway nếu nó terminate/originate và route ở L7 |

**Mã hóa proxy-to-proxy không phải end-to-end confidentiality trước các proxies.** Một proxy có đủ quyền xử lý HTTP có thể thấy payload và thường có khả năng ghi request metadata; vì thế hardening proxy, log redaction và quyền debug đặc biệt quan trọng.

### 8.2. Không mặc định mọi connection đều được mesh mTLS

Lý do:

- Pod chưa injection hoặc **nằm ngoài mesh**.
- Traffic bị exclude khỏi capture theo **port/IP/CIDR**.
- Mesh đang dùng **permissive mode**, cho phép plaintext hoặc mTLS theo peer.
- Gọi external TCP service không có mesh identity/certificate tương ứng.
- Có gateway/sidecarless segment hoặc **TLS passthrough/app-owned TLS**.
- Config thay đổi chưa tới proxy hoặc proxy đang stale.

Chứng minh bằng **negotiated connection metadata, proxy config/logs, peer identity evidence và policy tests**, không chỉ thấy manifest “mTLS enabled” ở control plane.

### 8.3. mTLS authentication khác authorization

TLS peer certificate chứng minh **Orders proxy đại diện workload Orders** nếu verifier/trust đúng. Nó không tự chứng minh một user có quyền **refund payment của người khác**. Payments cần kiểm tra **function-level/object-level authorization**, delegation của user và tenant. Mô hình mesh authorization có thể chặn **Orders → Payments: admin RPC** trước app, nhưng **app-level resource authorization** vẫn quan trọng.

### 8.4. Forward secrecy và những gì bị lộ sau compromise

Khi proxy sử dụng TLS với **ephemeral (EC)DHE**, session có thể có forward secrecy trước một số trường hợp lộ khóa xác thực dài hạn **về sau**. Tuy nhiên attacker có quyền **trong proxy process** vẫn có thể thấy plaintext/traffic secrets khi đang xử lý, hoặc sử dụng workload identity để gọi dịch vụ. **Private key rotation, credential expiry, TLS key schedule và endpoint compromise** là các vấn đề khác nhau; không tuyên bố “mesh mTLS ngăn được mọi lộ dữ liệu”.

## 9. Dynamic configuration/xDS và thời điểm proxy biết đường đi

Nhiều proxy, đặc biệt hệ sinh thái **Envoy**, có thể nhận cấu hình động qua các nhóm API như:

- **LDS (Listener Discovery Service):** listener/filter chains.
- **RDS (Route Discovery Service):** HTTP route configuration.
- **CDS (Cluster Discovery Service):** upstream cluster properties.
- **EDS (Endpoint Discovery Service):** endpoints của cluster.
- **SDS (Secret Discovery Service):** TLS certificates/private keys/trust bundles theo cấu hình.

Không phải implementation nào cũng sử dụng đủ tất cả các nhóm API này, hoặc dùng cùng server/transport. Chúng mô tả **kênh cấu hình data plane**, không có nghĩa control plane đọc hay giải mã từng request.

~~~mermaid
flowchart TB
    K["Kubernetes Services / Endpoints / Policies"] --> CP["Mesh control plane"]
    CP --> LDS["Listeners/filters"]
    CP --> RDS["Routes"]
    CP --> CDS["Clusters"]
    CP --> EDS["Endpoints"]
    CP --> SDS["Certificates / trust material"]
    LDS --> PX["Sidecar proxy"]
    RDS --> PX
    CDS --> PX
    EDS --> PX
    SDS --> PX
    PX --> APP["Actual upstream connection"]
~~~

### 9.1. Xem config ở đâu khi routing sai?

Không đủ để xem **Kubernetes Service** và **mesh CRD** đã khai báo. Cần kiểm tra **effective proxy configuration**: listeners, filter chains, virtual hosts, route match, destination cluster, endpoint membership, transport TLS context và policy. Trên Envoy có **admin/config dump, stats và dynamic config status** theo deployment; trên mesh khác có CLI/diagnostics tương đương.

**Lưu ý bảo mật:** Một config dump có thể chứa **sensitive metadata, authentication secrets hoặc TLS configuration** tùy bản build và cấu hình. Chỉ sử dụng endpoint/CLI được cấp quyền, lưu kết quả trong hệ thống bảo vệ và **redact** trước khi gửi ticket. Không công khai proxy admin listener trên Pod/Node/Internet.

### 9.2. Version và thời điểm hội tụ

Giả sử control plane phát routing update lúc 09:15 UTC. Không thể kết luận **mọi proxy áp dụng ngay 09:15**. Có thể có delay, rejected configuration, proxy crash/restart, endpoint churn hoặc network partition. Khi triage cần hỏi:

1. Control plane đã **chấp nhận** cấu hình mới?
2. Sidecar cụ thể đã **nhận và áp dụng** version nào?
3. Endpoint pool được cập nhật chưa và **old connections** còn mở không?
4. Trust bundle/cert update có tới các proxies của cả hai đầu không?
5. SLI/metrics theo workload/region có chứng minh hành vi mong muốn?

### 9.3. Khi control plane mất kết nối

Nhiều data planes có khả năng tiếp tục xử lý với **last known good config**, nhưng **fresh Pod endpoint, certificate renewal, dynamic policy change và proxy restart** có thể bị ảnh hưởng. Đánh giá RTO/RPO/availability theo implementation, **không tự coi control plane outage là data plane outage tức thì** hoặc ngược lại.

## 10. HTTP/1.1, HTTP/2, gRPC, WebSocket và TCP passthrough

**Sidecar không xử lý mọi protocol theo cùng cách.** Một socket TCP có thể chở nhiều HTTP requests hoặc một stream rất dài. Quyết định routing/policy phải xét **đơn vị đang được xử lý**.

| Giao thức | Sidecar có thể làm gì nếu hỗ trợ/nhìn được nội dung? | Rủi ro vận hành |
| --- | --- | --- |
| **HTTP/1.1** | Host/path/header routing, retry, request metrics | Keep-alive, proxy timeout, request body buffering |
| **HTTP/2** | Route theo stream/request, multiplexing, gRPC | Một TCP connection nhiều streams, GOAWAY và concurrent limits |
| **gRPC unary** | Method routing, status/trailers, deadlines | gRPC status có thể khác HTTP response status |
| **gRPC streaming** | Giữ stream lâu, telemetry theo stream | Drain/idle timeout/reset/retry semantics phức tạp |
| **WebSocket** | Upgrade hỗ trợ, giữ connection lâu | Không tùy ý route lại từng message qua backend khác |
| **Raw TCP** | Connection routing, mTLS, basic metrics/policy | Không biết HTTP path/JSON/body |
| **UDP/QUIC** | Tùy proxy/CNI/implementation có hỗ trợ riêng | Không mặc định TCP sidecar xử lý HTTP/3 |
| **Application TLS passthrough** | Có thể xử lý như opaque TCP, xem metadata hạn chế | Không áp WAF/HTTP authorization khi không giải mã |

### 10.1. Một gRPC request đi qua mấy kết nối?

Một application channel có thể tạo hoặc reuse **HTTP/2 connection app→local proxy**, sidecar có thể mở **HTTP/2/mTLS connection khác tới remote sidecar**, rồi remote sidecar chuyển tới app. Nhiều unary RPCs hoặc streams dùng chung một kết nối dài. Vì vậy:

- **Least connections** không tương đương **least active RPCs**.
- Một L4 flow log không cho biết số RPCs bên trong.
- Connection bị reset có thể ảnh hưởng nhiều streams cùng lúc.
- Retry tự động đối với RPC có side effect có thể gây **nhân đôi xử lý**.

### 10.2. WebSocket và graceful drain

Trong rollout, remote Pod có thể bị **drain**: sidecar ngừng nhận new connections nhưng các WebSocket/gRPC streams vẫn còn. Cần **draining deadline, server shutdown behavior, client reconnect và auth recheck**. Không đặt timeout ngắn chỉ để tất cả requests trở lại nhanh mà không phân tích tác động tới giao dịch.

### 10.3. HTTP/2-to-HTTP/1.1 translation

Khi proxy chuyển HTTP/2 xuống upstream HTTP/1.1, **:authority, :path, pseudo-headers, transfer semantics, trailers và normalization** cần được xử lý nhất quán. Sự khác biệt parser giữa proxy và app có thể tạo **request desynchronization** hoặc auth bypass. Dùng phần mềm đã vá, hardening header policy và kiểm thử hợp pháp trên staging; không tự phát payload phá parser vào hệ thống không được ủy quyền.

## 11. L7 routing: host, path, header, subset và traffic shifting

Control plane có thể định nghĩa một policy ví dụ:

~~~text
IF authority = payments.prod-apps.svc.cluster.local
AND path starts with /v1/charge
THEN:
  95% requests -> payments-stable
   5% requests -> payments-canary
  Timeout = 3 seconds
  Retry = none for payment creation unless application idempotency is proven
~~~

Đây là **pseudocode chính sách**, không phải manifest hợp lệ của một sản phẩm. Một số mesh dùng custom resources như **VirtualService, HTTPRoute, TrafficSplit** hoặc route APIs tương ứng. Phải kiểm tra **controller/mesh version và effective proxy config**.

### 11.1. Trọng số canary chưa chắc là tỷ lệ người dùng

**5% requests** không nhất thiết bằng **5% users, sessions, TCP connections hay traffic bytes**. Một user có thể gửi nhiều requests; gRPC long-lived stream giữ một backend lâu. Nếu deploy canary 5% nhưng 100% traffic nhạy cảm thuộc một tenant, phải phân tích **client cohort, hash stickiness, retries, request cost và payload**.

### 11.2. Route retries có thể che lỗi hoặc gây hậu quả

Retries hữu ích với lỗi kết nối tạm thời cho **idempotent operations**, nhưng không nên áp đồng loạt cho **POST thanh toán, tạo tài nguyên hoặc gRPC method có side effect**. Proxy không biết backend đã commit trước khi connection timeout. Cần:

1. **Explicit idempotency contract** hoặc idempotency key ở application.
2. Retry budget/limits, exponential backoff/jitter khi cần.
3. Timeout tổng thể không vượt ứng dụng deadline.
4. Phân biệt lỗi **connect failure trước gửi request** và **response timeout sau gửi request**.
5. Metrics phân biệt **original requests, retries/attempts và duplicate processing**.

### 11.3. Route fallback phải được giới hạn

Nếu subset canary không healthy, fallback sang stable có thể hợp lý; nhưng fallback từ **Prod sang Dev**, từ **authenticated workload sang backend không có mTLS** hoặc từ **sensitive API sang external endpoint** là rủi ro nghiêm trọng. Policy fallback cần bảo toàn **environment, identity, security classification và data residency**.

### 11.4. Timeout budget trên nhiều hop

~~~text
Client deadline:              2,500 ms
Orders app processing budget:   300 ms
Orders outbound sidecar:        2,000 ms
Payments inbound+app target:    1,700 ms
Response/serialization margin:  200 ms
~~~

Các con số chỉ minh họa: **không nhất thiết cộng từng timeout như các pha nối tiếp tuyệt đối** vì có chồng lấp, đo ở ranh giới khác nhau. Hãy theo dõi deadline propagation (gRPC deadlines/HTTP headers được xác thực) và đo **app duration, proxy queueing, upstream connect time, service time** để tìm điểm trễ. Nếu outbound timeout dài hơn client deadline, retry có thể tiếp tục tiêu tài nguyên sau khi client đã bỏ.

## 12. Sidecar, load balancing và connection pools

Tại outbound proxy, route có thể trỏ đến **cluster** có nhiều endpoints. Thuật toán chọn endpoint có thể là **round robin, least requests, ring hash, maglev/hash, locality-aware** hoặc kiểu khác tùy proxy. Việc phân phối phải dựa trên **health, zone, capacity, request/stream behavior** chứ không chỉ gọi tên thuật toán.

### 12.1. Nơi nào load balance?

Một request có thể trải qua **nhiều lần cân bằng**:

~~~text
Client -> Cloud L4 LB -> Ingress Gateway -> Orders Pod
                                           |
                                           v
                                      Orders Sidecar
                                           |
                            Upstream endpoint chosen by mesh
                                           |
                                      Payments Pod
~~~

Cloud LB có thể chọn ingress node, gateway chọn Orders workload, rồi outbound sidecar chọn Payments endpoint. **Ba quyết định cân bằng không tự đồng bộ**, và số lần load balancing trong thực tế phụ thuộc architecture.

### 12.2. Connection pool ảnh hưởng request path

Một proxy có thể **reuse TCP/TLS connections**, vì vậy một **HTTP request mới không luôn mở socket mới** tới backend. Khi endpoint thay đổi, proxy có thể dùng connection cũ đến khi drain/timeout. Điều này tạo hiện tượng:

- Control plane đã cập nhật endpoints, nhưng một số streams vẫn gắn với old Pod.
- mTLS certificate mới đã có nhưng **connection cũ** còn giữ security context cũ.
- Flow logs có ít kết nối mới, nhưng L7 access logs có nhiều requests.
- Khi cạn upstream connections/streams/queues, proxy từ chối dù app vẫn healthy.

### 12.3. Circuit breaking, outlier detection và readiness

Proxy có thể giới hạn **max connections, pending requests, concurrent streams hoặc retries**, và tạm loại endpoint khi có mẫu lỗi nhất định. Điều này khác **Kubernetes readiness** và **application liveness**:

| Cơ chế | Mục tiêu | Rủi ro nếu cấu hình sai |
| --- | --- | --- |
| K8s readiness | Không gửi traffic cho Pod chưa ready theo hệ thống | Probe 200 nhưng nghiệp vụ lỗi hoặc tất cả Pods unready |
| Mesh endpoint health | Chọn upstream đủ khỏe theo nguồn discovery/health | Outlier ejection sai làm pool trống |
| Circuit breaker | Bảo vệ proxy/backend khỏi quá nhiều công việc đồng thời | Giới hạn thấp gây 503 ngay khi app còn capacity |
| Connection draining | Dừng cấp mới, cho công việc hiện tại hoàn tất | Deadline quá ngắn làm rớt streams |
| Retry budget | Giới hạn amplified load do retry | Retry sai gây duplicate writes/cascading overload |

**Không coi mọi 503 là backend trả 503.** Sidecar/gateway có thể tạo local reply do **no healthy upstream, connect timeout, circuit breaker hoặc policy**. Phải phân biệt response flags/upstream attempt và ứng dụng logs.

## 13. Source IP, NAT, headers và định danh client

Trong sidecar mesh, source IP có thể khác giữa những điểm:

~~~text
Orders app socket     -> sidecar capture      (local source)
Orders sidecar socket -> Payments Pod IP      (proxy source Pod IP/NAT)
Payments sidecar      -> Payments app :8080   (loopback/local address)
~~~

Nếu app Payments chỉ nhìn socket peer là **127.0.0.1**, nó không thể dựa vào IP đó để phân biệt Orders/Inventory/Unknown callers. **Workload identity** thường được xác thực tại inbound sidecar và có thể được chuyển tiếp bằng **metadata đã được proxy thiết lập**, nhưng app phải chỉ tin metadata từ **trusted sidecar channel** và có ứng dụng policy riêng.

### 13.1. X-Forwarded-For/Forwarded không phải chứng cứ mặc định

Headers như **X-Forwarded-For**, **Forwarded**, **X-Request-ID** hoặc các header chứa authenticated principal có thể được **client tạo tùy ý** nếu ingress đầu tiên không xóa/chuẩn hóa. Các proxies phải biết **trusted hops**, preserve client IP đúng source và không truyền identity header do Internet client tự khai tới backend như đã xác thực.

### 13.2. PROXY protocol và transparent source IP

Một số L4 load balancers/proxies dùng **PROXY protocol** để đưa source/dest metadata tới backend. **PROXY protocol không mặc định xác thực bên gửi**. Nếu Payments app nhận header này từ arbitrary Pod, attacker có thể tự khai IP khác. Cần giới hạn **listener source + mTLS/workload identity và cấu hình đúng data path**.

### 13.3. NAT/cross-node và flow logs

VPC flow log có thể thấy **Pod IP, node IP, overlay/VXLAN outer IP, LB/NAT address** tùy điểm quan sát/CNI. Mesh L7 log có thể có **service principal và HTTP path**, nhưng VPC flow log không tự biết request đó đến từ ai về mặt người dùng. Khi điều tra kết hợp **source/dest tuple, Pod UID tại thời điểm, CNI/NAT mapping, proxy access logs và trace IDs**.

## 14. Mesh policy: xác thực và phân quyền ở đúng chiều request

Một chính sách mTLS/authorization nên trả lời:

1. **Peer là workload nào?** Xác thực bằng CA/issuer + SPIFFE/SVID hoặc identity model tương đương.
2. **Peer được gọi dịch vụ nào?** Policy allowlist theo service/namespace/trust domain.
3. **Peer được thực hiện operation nào?** HTTP method/path hoặc gRPC service/method khi proxy nhìn L7.
4. **User/tenant bên trong request có quyền gì?** Quy tắc ứng dụng/authorization server, không chỉ mTLS.
5. **Nếu peer không có sidecar hoặc cert sai?** Fail-closed/compatibility mode đã được phê duyệt.

### 14.1. L4 và L7 authorization khác nhau

| Policy | Đòi hỏi nhìn thông tin gì? | Ví dụ |
| --- | --- | --- |
| **L4 identity allow** | Peer workload identity, destination port/protocol | Orders được kết nối Payments:8080 |
| **L7 HTTP allow** | Method, normalized path/authority, identity | Orders được POST /v1/charge |
| **gRPC method allow** | HTTP/2/gRPC service/method metadata | Orders được gọi CreatePayment, không được RefundAll |
| **Application object auth** | User, tenant, order ownership và dữ liệu | Không được charge order của tenant khác |

**Không thể áp L7 method rule trên opaque TCP stream nếu proxy không giải mã/parse giao thức.** Phải kiểm tra protocol classification; nếu unsupported, quy tắc không tự chuyển thành bảo vệ tương đương.

### 14.2. Mẫu chính sách ý định (pseudocode)

~~~yaml
# Minh họa policy intent, KHÔNG phải Kubernetes/Istio/Linkerd manifest.
target:
  workload: payments
  environment: production
transport:
  require_mtls: true
  expected_trust_domain: corp.example.org
rules:
  - caller_workload: orders
    allowed_http_methods: ["POST"]
    allowed_paths: ["/v1/charge"]
  - caller_workload: payment-auditor
    allowed_http_methods: ["GET"]
    allowed_paths: ["/v1/status"]
default: DENY
application_authorization:
  enforce_tenant_and_order_ownership: true
~~~

**Policy-as-code phải được kiểm chứng trên implementation cụ thể.** Ví dụ, có mesh hỗ trợ **Istio AuthorizationPolicy**, có nền tảng dùng **ServerAuthorization/HTTPRoute/auth policy** khác; một số match rules phụ thuộc **protocol sniffing, port names và selector scope**. Không sao chép mã ý định thành manifest rồi assume default deny được thực thi.

### 14.3. Mesh mode PERMISSIVE và giai đoạn migration

Trong quá trình đưa Pods cũ vào mesh, một số hệ thống có thể cho phép **plaintext và mTLS** cùng hoạt động (**PERMISSIVE mode**). Điều này giúp giảm downtime nhưng phải có **ngày kết thúc**, kiểm kê clients chưa vào mesh, đo plaintext traffic và thử **STRICT mode** trước khi chặn. Không gọi PERMISSIVE là “mTLS toàn bộ dịch vụ đã bảo vệ”.

## 15. Đường request qua ingress và egress gateway

**Sidecar** thường xử lý kết nối từ/đến chính workload, trong khi **ingress gateway** và **egress gateway** có thể đại diện cho ranh giới mạng ở biên mesh. Một kiến trúc có thể dùng cả ba, nhưng chúng không bắt buộc tồn tại đồng thời.

### 15.1. External client → ingress → service

~~~mermaid
flowchart LR
    C["Browser / Partner HTTPS"] --> W["CDN / WAF / public LB"]
    W --> IG["Ingress Gateway"]
    IG ==>|"mTLS hoặc TLS theo thiết kế"| S["Orders Sidecar"]
    S --> A["Orders Application"]
~~~

Chặng **client → CDN/WAF → gateway → sidecar** có thể có nhiều lần terminate/originate TLS. Gateway có thể xác thực user token/OIDC/mTLS client cert, route theo hostname/path, rồi thiết lập mTLS với sidecar. Nhưng:

- Nếu gateway chuyển HTTP không được mã hóa tới backend, phải đánh giá trust boundary.
- Nếu sidecar chỉ chấp nhận **mesh workload identity**, caller Internet không tự có identity tương đương; gateway có thể là principal được ủy quyền.
- **Application vẫn phải xác thực user/tenant/resource** hoặc dùng identity context được chuyển tiếp qua đường đáng tin.
- Đường **direct NodePort/LoadBalancer/Pod IP** nếu mở ra Internet có thể bỏ qua WAF/gateway auth. Cần network controls riêng.

### 15.2. Internal service → egress gateway → external API

~~~mermaid
flowchart LR
    A["Orders App"] --> S["Orders Sidecar"]
    S --> G["Mesh Egress Gateway"]
    G --> F["Cloud firewall / NAT"]
    F --> X["External payments partner"]
~~~

Một **egress gateway** có thể giúp tập trung authorization, log, TLS origination và outbound restrictions. Nhưng sidecar vẫn có thể phát direct egress nếu **capture/CNI/route policy cho bypass**. Muốn bắt buộc mọi traffic qua gateway, thường phải kết hợp **CNI NetworkPolicy, cloud SG/firewall, route hoặc mesh outbound policy** có bằng chứng runtime.

### 15.3. External TLS origination không nhất thiết là mesh mTLS

Kết nối **sidecar → egress gateway** có thể được bảo vệ bằng mTLS workload identity; kết nối **egress gateway → Internet API** thường dùng TLS công khai xác thực hostname/CA, hoặc mTLS với chứng chỉ client do đối tác cấp. Hai phiên là **hai trust domains**. Không mang nguyên service mesh private key cấp cho orders đi xác thực với một website không thuộc mesh.

### 15.4. Outbound policy unknown service

Khi app gọi một IP/host **không được mesh đăng ký**, tùy mesh có thể **passthrough, block/blackhole hoặc route theo fallback**. Chính sách an toàn nên **rõ về external destinations và trạng thái default**, không dựa vào việc “không có ServiceEntry thì chắc chắn chặn”. Kiểm thử **ALLOW partner hợp lệ và DENY DNS/IP đích không được phép** sau mọi thay đổi.

## 16. Sidecar và network segmentation: hai lớp bổ sung, không thay thế

Mesh authorization hoạt động ở **proxy/identity layer**; Kubernetes NetworkPolicy hoặc cloud firewall hoạt động tại **network enforcement point**. Một policy ở proxy chỉ có hiệu lực nếu request thật sự **đi qua proxy**.

| Đường lưu lượng | Nơi có thể kiểm soát | Rủi ro cần kiểm tra |
| --- | --- | --- |
| Orders → Payments qua sidecar | Mesh mTLS + L4/L7 authZ + NetworkPolicy | Peer ID đúng nhưng operation/tenant sai |
| Orders → Payments direct Pod IP | Capture, CNI policy và app auth | Bypass listener hoặc route classification |
| External → ingress gateway | Cloud LB/WAF/ingress auth + mesh auth | Direct origin/NodePort bypass |
| Orders → Internet | Egress gateway + firewall/SG/CNI | Passthrough unknown destination |
| App → Kubernetes API/metadata | RBAC/IAM/egress policy | Container compromise, token misuse/SSRF |
| Sidecar → control plane/CA | Mesh control communication/auth | Cert/config delivery outage, privileged debug |
| Node/hostNetwork traffic | Node firewall/cloud security controls | Nằm ngoài Pod-level capture/policies |

### 16.1. NetworkPolicy ví dụ cho đường Orders → Payments

Đây là **policy minh họa** cho ingress của Pods payments, trong đó chỉ Orders Pods ở namespace Production được phép gọi TCP/8080. Không có nghĩa mọi sidecar/proxy tự động đi bằng cổng này trên wire; **chọn port và selectors theo data path thực tế**.

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: payments-ingress-restrict
  namespace: prod-apps
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

**Cảnh báo quan trọng:** NetworkPolicy kiểm tra packet tại điểm thực thi **CNI**, còn sidecar inbound có thể nhận traffic tại port/interception point khác. Tùy CNI và mesh, cần phân tích **packet original/translated destination, sidecar identity và Pod selectors** để chọn port; ví dụ không thể copy nguyên vào mọi cluster. **Ingress policy này cũng không tạo default deny egress hoặc bảo vệ mọi route khác**. App authentication/mTLS policy vẫn cần.

### 16.2. Nếu app bị chiếm quyền, proxy có cứu được tất cả?

Không. Attacker điều khiển app process có thể **gửi request hợp lệ qua chính sidecar Orders** tới Payments trong phạm vi mesh policy cho phép. Sidecar chỉ biết **workload identity** của Orders, không biết request đại diện cho **user nào có quyền thanh toán** nếu không có token/metadata được xác thực. Vì thế **least-privilege method/resource authorization, anomaly detection và runtime hardening** vẫn bắt buộc.

## 17. Giới hạn bảo mật và các kiểu bypass thường gặp

### 17.1. Threat model ngắn gọn

| Threat/failure mode | Nguyên nhân | Phòng vệ và bằng chứng |
| --- | --- | --- |
| **Plaintext traffic bypass** | Pod chưa injection, excluded port, PERMISSIVE, hostNetwork | Inventory sidecar/capture, STRICT policy, CNI/network test |
| **Direct origin bypass** | Service exposed qua NodePort/direct LB ngoài gateway | SG/WAF/NetworkPolicy, route inventory, DENY test |
| **Untrusted identity headers** | Proxy append XFF/X-Role client tự khai | Trusted ingress stripping, peer identity and app authorization |
| **Cross-namespace/Dev→Prod call** | Mesh allow quá rộng, wildcard source principal | Least privilege mesh authZ + namespace isolation |
| **Sidecar admin endpoint exposure** | Debug/admin port reachable không kiểm soát | Bind localhost, RBAC, node/Pod firewall, protected diagnostics |
| **Proxy configuration drift** | Sidecar stale/reject xDS update | Version/ACK monitoring, config readback, drift alert |
| **mTLS key compromise** | Process/sidecar/node bị chiếm | Short-lived keys, workload identity scoping, rotation/revoke |
| **HTTP route ambiguity** | Parser/normalization/protocol sniffing khác app | Fixed protocol, consistent canonicalization, patched proxy |
| **Retry amplification** | Retry budget quá cao, side effects | Idempotency, bounded retries, circuit breaker |
| **No healthy upstream** | Discovery/readiness/outlier ejection | EDS/endpoint readback, correct health checks |
| **Data plane overloaded** | Too many connections/streams/filters | Proxy capacity, resource limits, priority/backpressure |
| **Telemetry leakage** | Proxy logs Authorization/PII | Redaction, sampling, RBAC/retention |
| **Egress policy bypass** | Direct IP, DNS alternative, tunnel, CNI gap | Network-level deny and verified gateway path |
| **Peer identity spoofing through compromised workload** | Valid key/token stolen | Verifier-side deny, narrow grants, incident response |

### 17.2. “Mesh có mTLS” chưa đủ để đạt zero trust

Zero-trust-style architecture yêu cầu **verify explicitly, least privilege, assume breach** trên nhiều lớp. mTLS giúp proxy xác minh peer nhưng không thay:

- End-user authentication/authorization và object ownership.
- Segmentation cho **DB/admin/metadata** và đường đi không qua proxy.
- Hardening/Kubernetes RBAC, secret key distribution, node isolation.
- Chính sách **ingress, egress, DNS và cloud firewall**.
- Quan sát ứng dụng, secret misuse và response sau incident.

### 17.3. Mesh outage không được biến thành “allow all”

Khi control plane, CA hoặc sidecar gặp lỗi, không nên **tắt mTLS, wildcard allow, bỏ backend certificate verification** như cách sửa mặc định. Có thể cần fallback đã được phê duyệt với mức rủi ro giới hạn; phải **ghi thời hạn, owner, blast radius và regression tests**. Với hệ thống nhạy cảm, ưu tiên **fail closed** ở unauthorized paths dù ảnh hưởng availability.

## 18. Observability: một request xuất hiện trong những logs nào?

Một request qua hai sidecars có thể tạo:

1. **Application client trace/log:** user action, request ID, deadline.
2. **Outbound proxy access log:** peer/service route, upstream cluster, status, attempts.
3. **Network flow log:** IP/port/bytes ở Pod NIC/node/VPC, không có HTTP path.
4. **Inbound proxy access log:** mTLS peer principal, local authorization, upstream target.
5. **Application server log:** handler, user/tenant authZ, DB status, business outcome.
6. **Cloud/Kubernetes audit:** thay đổi config/cert/RBAC/Service/Endpoint liên quan, không phải nội dung request.

~~~mermaid
flowchart TB
    R["Request ID / trace context"] --> A["Orders app span"]
    A --> B["Orders outbound sidecar span/log"]
    B --> C["Network flow metadata"]
    B --> D["Payments inbound sidecar span/log"]
    D --> E["Payments application span"]
    E --> F["DB/application evidence"]
~~~

**Không mặc định mọi mesh tạo distributed tracing tự động:** một số proxy chỉ truyền hoặc quan sát trace context và cần **application instrumentation/tracing provider/config** để có complete spans. Thêm sidecar không tự giúp thấy database query hoặc business authorization.

### 18.1. Mẫu correlation record đã giảm dữ liệu nhạy cảm

~~~json
{
  "time_utc": "2026-10-12T10:10:02Z",
  "trace_id": "example-trace-001",
  "source_workload": "orders",
  "destination_workload": "payments",
  "source_namespace": "prod-apps",
  "destination_namespace": "prod-apps",
  "source_principal": "spiffe://corp.example.org/ns/prod-apps/sa/orders",
  "destination_principal": "spiffe://corp.example.org/ns/prod-apps/sa/payments",
  "http_method": "POST",
  "route_template": "/v1/charge",
  "proxy_decision": "ALLOW",
  "upstream_cluster": "payments-prod",
  "response_code": 200,
  "upstream_attempts": 1,
  "tls_peer_verified": true
}
~~~

**Ví dụ là schema minh họa**, không phải JSON mà một mesh chắc chắn phát nguyên trạng. Không đưa **Authorization, Cookie, payload thanh toán, raw client certificate private key hoặc decrypted TLS secrets** vào access log. Nếu principal chứa tenant/user ID nhạy cảm, áp **redaction hoặc pseudonymization** theo policy.

### 18.2. Metrics cần xem cùng nhau

| Vị trí | Metric | Diễn giải |
| --- | --- | --- |
| Orders app | Client-side success, latency p95/p99 | User/business cảm nhận |
| Outbound proxy | RPS, retries, response flags, upstream connect errors | Routing và upstream connectivity |
| Inbound proxy | mTLS handshakes, policy DENY, received RPS | Authentication/authorization tại đích |
| Payments app | Handler success, business errors, DB pool | Nghiệp vụ và dependencies |
| K8s | Readiness, EndpointSlices, Pod restarts | Endpoint health/lifecycle |
| CNI/Network | Packet drops, NAT state, flow direction | Packet path và segmentation |
| Mesh control | xDS rejects, stale proxies, CA/SDS refresh | Config/cert propagation |

**HTTP 200 ở proxy** không chứng minh payment đã được ghi đúng nếu app trả 200 với business error payload. Ngược lại **mTLS 401/403** ở app/gateway có thể liên quan user token, không phải luôn lỗi mesh peer authentication. Sử dụng request ID và điểm phát lỗi.

### 18.3. Trace propagation và sự tin cậy

Các trace/request IDs có thể đến từ client không tin. Ingress nên **validate/normalize** headers theo chính sách, không coi trace ID là bằng chứng xác thực user. Một attacker có thể tự chọn traceparent để gây nhầm correlation; logs phải gắn thêm **authenticated principal, source peer, gateway ID và UTC timestamp**.

## 19. Performance và capacity: sidecar thêm công việc gì?

Sidecar có thể mang lợi ích quản lý traffic nhưng cũng tiêu thụ **CPU, RAM, sockets, TLS handshakes, file descriptors và network buffers**. Trong Pod có nhiều proxies, tổng tài nguyên cần sizing theo **app + sidecar + telemetry agent**.

### 19.1. Các chi phí cần benchmark

| Chi phí | Nguyên nhân | Chỉ số |
| --- | --- | --- |
| Latency per request | Local proxy hops, filters, queuing, network | p50/p95/p99, connection/setup/TTFB |
| CPU | TLS crypto, HTTP parse, metrics, logs, routing | CPU/throttling, handshakes per second |
| Memory | Connection pools, route configs, buffers, TLS state | RSS, OOM, per-connection memory |
| Socket/file descriptors | Hai phía của proxy connections, streaming | Open FDs, concurrent connections |
| Network throughput | Proxy copies, encapsulation, retries, headers | Bps/PPS, retransmissions |
| Telemetry cardinality | Metrics labels theo route/peer/tenant | TSDB series, cardinality, storage cost |
| Control-plane load | Nhiều proxies/watchers, endpoint churn | Config push latency, rejected updates |

**Không có mức overhead cố định cho mọi mesh.** Một proxy xử lý raw TCP, một proxy dùng mTLS và một proxy thêm L7 authorization/tracing có costs khác nhau. Benchmark cần workload tương đương, cùng **CPU limits, keep-alive, gRPC streams, TLS modes và logging rate**.

### 19.2. Công thức concurrency cơ bản

Nếu trung bình có \(\lambda\) requests/giây và request tồn tại trong một ranh giới đo trung bình \(W\) giây, Little's Law cho biết số yêu cầu đang trong hệ thống trung bình:

\[
L = \lambda W
\]

Ví dụ một service xử lý **400 RPC/s** và mỗi RPC đi qua ranh giới từ lúc outbound proxy nhận đến khi trả xong trung bình **0,05 s**, concurrency trung bình theo ranh giới đó là **20 RPC**. Nhưng đó **không phải** số TCP connections (HTTP/2 multiplexing), không thay p99 hay burst capacity, và **không chứng minh sidecar chỉ cần 20 sockets**.

### 19.3. Thử với retries và tail latency

Nếu client nhận 100 requests nhưng proxy retry 40 attempts, backend có thể thấy **140 attempts** (giả sử không có loại biến đổi khác). Backend RPS cao hơn client RPS có thể do retries, fan-out, health checks hoặc legitimate calls; không tự coi đó là tấn công. Theo dõi **retry amplification ratio, per-route timeouts, queue depth, upstream healthy endpoints** và business SLI.

### 19.4. Graceful shutdown

Trong rolling deployment, ứng dụng và sidecar phải phối hợp **readiness false, endpoint removal, drain, in-flight requests/streams, termination grace period**. Nếu proxy shutdown trước app hoàn tất hoặc ngược lại, các kết nối có thể reset. Đối với gRPC streams/WebSocket lâu dài, cần **deadline và client reconnect plan**; không chờ vô hạn hoặc kill ngay theo bản mẫu không kiểm thử.

## 20. Troubleshooting theo từng hop: bắt đầu ở triệu chứng rồi thu chứng cứ

### 20.1. Sơ đồ quyết định

~~~mermaid
flowchart TD
    A["Request lỗi hoặc timeout"] --> D{"App có resolve đích?"}
    D -- "Không" --> DNS["DNS, namespace, service, app cache"]
    D -- "Có" --> C{"Outbound capture/listener?"}
    C -- "Không" --> CAP["Injection, CNI, REDIRECT/TPROXY, port exclude"]
    C -- "Có" --> R{"Route/cluster/endpoints tồn tại?"}
    R -- "Không" --> CONF["xDS/LDS/RDS/CDS/EDS, readiness"]
    R -- "Có" --> T{"Network/mTLS tới remote proxy?"}
    T -- "Không" --> NET["NAT, NetworkPolicy, trust, cert/SDS, route"]
    T -- "Có" --> I{"Inbound policy cho phép?"}
    I -- "Không" --> AUTH["Peer identity, authZ, mode, protocol"]
    I -- "Có" --> APP["Local app port, business auth, DB, SLO"]
~~~

**Luồng quyết định nhằm thu hẹp nguyên nhân**, không phủ định sự cố nhiều lớp cùng lúc. Chẳng hạn DNS cache và expired cert có thể cùng xảy ra; một request có thể fail do deadline trước khi bước inbound được ghi nhận.

### 20.2. Một số triệu chứng và bằng chứng

| Triệu chứng | Giả thuyết phù hợp | Bằng chứng cần |
| --- | --- | --- |
| App connect timeout nhưng proxy không có log | Traffic bypass capture, app dùng protocol/port khác | Pod netns/capture config, socket source/dest, CNI flows |
| Outbound proxy ghi “no route” | RDS/route authority/path không match | Effective routes, :authority/SNI/protocol |
| “No healthy upstream” | EDS rỗng, readiness, outlier ejection | Endpoint membership, health, route cluster |
| TLS handshake error | CA, expiry, peer SAN/SPIFFE ID, policy mismatch | Cert metadata, mTLS mode, SDS refresh, time |
| Outbound success nhưng inbound không log | Network drop, NAT, wrong endpoint, logging scope | Flow logs tại hai phía và route/firewall |
| Inbound DENY, app không thấy request | Mesh authZ/mTLS peer rejection | Inbound proxy decision, principal, policy revision |
| App 401/403 nhưng proxy mTLS tốt | User token/scopes/tenant bị app từ chối | App auth logs đã redact, API contract |
| 503 từ sidecar nhưng backend health OK | Circuit breaker, timeout, stale cluster, connection pool | Proxy response flags, upstream attempts |
| gRPC UNAVAILABLE sau rollout | Drain, GOAWAY, mTLS, endpoint churn, deadline | gRPC status, stream metrics, Pod termination |
| Một region hoặc IPv6 lỗi | Route/trust/endpoint/capture drift | Per-region/pod config, IPv4/IPv6 checks |
| Response body chậm dù app nhanh | Buffering, retries, network bandwidth, proxy queue | Per-hop latency and attempt metrics |
| Service gọi external API thất bại | Egress gateway, DNS, TLS origination/peer verification | Egress route, policy, server cert, NAT |

### 20.3. Quy trình thu thập theo thứ tự ít xâm lấn

1. **Xác nhận phạm vi:** Source workload, destination, URI/RPC method, region/namespace/cluster, UTC event window, request ID.
2. **Xem application SLI:** HTTP/gRPC status, deadline, business operation, latency.
3. **Xem sidecar outbound logs/metrics:** Chosen cluster, endpoint, attempts, response flags, route match.
4. **Xem inbound logs/metrics:** Handshake result, peer principal, authZ decision, app forwarding.
5. **Kiểm tra effective proxy config:** xDS status, listener/filter, routes, clusters/endpoints, SDS.
6. **Đối chiếu Kubernetes:** Service/EndpointSlices, Pod readiness, sidecar injection, workload labels/ServiceAccount, rollout.
7. **Đối chiếu mạng:** Pod/node CNI, NetworkPolicy, security group/firewall/NAT, ingress/egress gateway, IPv6/DR.
8. **Dùng capture trong lab hoặc phạm vi được cấp quyền nếu cần**, không ghi credentials/TLS keylogs vào Production.
9. **Kết luận theo chứng cứ**, triển khai thay đổi hẹp có approval, canary và rollback, kiểm chứng ALLOW/DENY.

### 20.4. Không chạy lệnh debug tùy tiện

Proxy admin ports, packet capture, kubelet debugging và mesh CLI có thể expose **secrets hoặc nhạy cảm**. Chỉ sử dụng trên tài sản được phép; ưu tiên **read-only effective config, metrics và request logs**. Khi cần truy xuất config dump, giữ **role-based access, short retention và redaction**, không paste certificate private key hoặc raw JWT vào chat/ticket.

## 21. Sidecar injection, Pod lifecycle và ambient mode

Service mesh thường có **hai nhiệm vụ**: quyết định **workload nào tham gia** và bảo đảm workload ấy có **proxy/traffic capture/identity** đúng lúc. Một Deployment được gắn label bật sidecar không chứng minh tất cả Pods đang chạy đã được mutate hoặc mọi traffic đã được capture.

### 21.1. Admission-time injection

Một số mesh dựa vào **mutating admission webhook** để thêm proxy container, volumes, init settings và annotations khi Pod được **tạo**. Cơ chế/chi tiết thay đổi theo implementation.

~~~mermaid
sequenceDiagram
    participant D as Deployment / User
    participant K as Kubernetes API Admission
    participant M as Mesh Injector
    participant N as Scheduler/Kubelet/CNI
    participant P as Pod runtime
    D->>K: Create Pod
    K->>M: Admission review (nếu selector khớp)
    M-->>K: Pod spec patch: proxy/volumes/config
    K->>N: Schedule and start Pod
    N->>P: Configure network capture and containers
    P->>P: Proxy receives discovery/cert and becomes ready
~~~

**Không tự suy bật label namespace sẽ thêm sidecar vào các Pods đã tồn tại.** Thông thường cần **recreate/rollout** Pods, và phải xem effective spec. Nếu admission webhook fail hoặc CNI setup fail, Pod có thể không được tạo, chạy không proxy hoặc fail closed tùy failure policy — đây là quyết định **bảo mật và availability** cần review.

### 21.2. Khởi động sidecar và ứng dụng

Ứng dụng có thể chạy trước khi proxy **nhận endpoints, certificate hoặc listener**; khi đó các kết nối đầu tiên có thể fail, bị capture nhưng proxy chưa ready hoặc bypass theo setup. Kiểm tra:

- **Pod readiness probes** phản ánh **app và proxy** cần thiết cho phục vụ traffic.
- **Startup order** và khả năng proxy khởi động trước app theo implementation.
- **DNS và certificate issuance** ngay sau Pod creation.
- **Graceful termination** của app/sidecar, đặc biệt TCP streams lâu.
- **Workload identity binding** khi Pod đổi ServiceAccount hoặc node.

Không đánh đồng **Pod Ready** với **mTLS tới mọi upstream endpoint thành công**. Synthetic permitted requests hoặc mesh telemetry mới giúp kiểm tra end-to-end.

### 21.3. Sidecar-per-Pod vs ambient/sidecarless

| Thuộc tính | Sidecar model | Ambient / sidecarless model (tùy implementation) |
| --- | --- | --- |
| Nơi data plane xử lý | Proxy cùng Pod hoặc sát app | Một phần tại node/network layer, có thể thêm L7 waypoint |
| Chi phí per Pod | Thêm container/process/resources | Chia sẻ theo node/waypoint, có overhead khác |
| L4/mTLS identity | Thường tại Pod sidecar | Có thể ở secure node tunnel/agent |
| HTTP L7 policy | Có tại sidecar nếu nhìn HTTP | Có thể yêu cầu L7 waypoint hoặc component riêng |
| Capture | Pod-local interception/CNI | CNI/node-level redirection theo model |
| Trust boundary | Proxy trong Pod network namespace | Node proxy/waypoint được chia sẻ, blast radius khác |
| Troubleshooting | Local sidecar config + app | Node/ztunnel/waypoint hoặc kiến trúc tương ứng |

**Bài tập về sidecar không được áp máy móc lên ambient.** Ví dụ một ambient data plane có thể bảo đảm **mTLS L4** nhưng không áp L7 HTTP rules nếu không có **waypoint** được cấu hình. Khi một service chuyển mode, phải kiểm chứng **điểm thực thi policies và trace/log source** mới.

### 21.4. Sidecar injection không chữa mọi vấn đề bảo mật container

Sidecar không mặc nhiên cô lập **process memory, container filesystem, kubelet socket, ServiceAccount token, Pod networking**, và cũng không thay Kubernetes RBAC. Nếu app bị RCE, attacker có thể dùng **quyền của app và các request hợp lệ qua sidecar**. Cần **PodSecurity, non-root, capability minimization, secrets management, network egress và audit** bổ trợ.

## 22. Case study A: HTTP 503 sau rollout, service vẫn Ready

**Bối cảnh giả định:** Orders ở namespace Prod gọi Payments qua HTTP/gRPC. Sau khi scale Payments từ 2 lên 5 Pods, khách hàng gặp 503 gián đoạn. Kubernetes hiển thị đủ 5 Pods Ready, nhưng outbound proxy đôi lúc ghi **no healthy upstream** và **upstream connect failure**.

### 22.1. Những giả thuyết cần tách

| Giả thuyết | Vì sao hợp lý | Bằng chứng |
| --- | --- | --- |
| EDS/endpoint cache chưa hội tụ | Proxies có endpoint list cũ/missing | Effective endpoints per sidecar, xDS ACK/NACK |
| Payment sidecar chưa sẵn sàng | App readiness OK nhưng proxy/cert chưa ready | Proxy readiness, SDS, mTLS handshake |
| Mesh ejection/circuit breaker | Backend bị loại vì lỗi hoặc giới hạn connections | Outlier counters, pending requests, healthy host count |
| Route sai subset label | Canary route trỏ subset không có endpoints | Route/cluster/subset selectors, Pod labels |
| NetworkPolicy/CNI chặn Pods mới | IP/node/namespace thay đổi | Flow logs/CNI DENY, return routing |
| Application tự trả 503 | Dependency DB hoặc payment processing lỗi | Payments app logs, upstream response correlation |

### 22.2. Quy trình điều tra

1. Thu **trace ID, route, user operation, UTC timestamp, workload/Pod name và gRPC status**.
2. Tại **Orders outbound proxy**, đọc cluster name, selected endpoint, retries và response flags.
3. Tại **Payments inbound proxy**, xem request có đến, mTLS peer identity, authZ decision không.
4. Đối chiếu **effective EDS** với Kubernetes EndpointSlices tại cùng thời điểm; xác minh endpoint healthy, Pod label và zone.
5. Nếu upstream không thấy request, xem **CNI/NetworkPolicy/route/mTLS**; nếu app thấy request, điều tra Payments và DB.
6. Sửa **config/routing/health** có phạm vi hẹp, canary, kiểm tra cả **ALLOW Orders→Payments** và **DENY Dev→Payments**.

### 22.3. Điều không nên làm

Không tự đổi mọi upstream thành **passthrough plaintext**, tắt mTLS STRICT, mở firewall ANY/ANY hoặc tăng retry vô hạn để che 503. Những thay đổi đó có thể **mở quyền trái phép** hoặc làm DB/Payments quá tải.

**Bài học:** Service discovery trong mesh có **nhiều tầng sẵn sàng**: Kubernetes Pod readiness, route config, endpoint availability, proxy connectivity, TLS identity và application dependency. Mỗi tầng có bằng chứng khác nhau.

## 23. Case study B: mTLS peer identity DENY dù Pod IP vẫn reachable

**Bối cảnh giả định:** Team Orders chuyển một workload sang ServiceAccount mới **orders-v2**, nhưng inbound policy của Payments vẫn chỉ cho principal **orders** cũ. Ping/port reachability có thể vẫn hoạt động tùy policy, nhưng request tới /v1/charge bị từ chối tại inbound sidecar.

### 23.1. Tóm tắt dữ liệu giả định

~~~text
Orders Pod:
  namespace = prod-apps
  serviceAccount = orders-v2
  sidecar injected = true
  outbound mTLS = enabled

Payments inbound policy:
  allowed principal = spiffe://corp.example.org/ns/prod-apps/sa/orders
  current peer = spiffe://corp.example.org/ns/prod-apps/sa/orders-v2
  result = DENY

Payments app:
  request not observed
~~~

### 23.2. Cách giải quyết đúng

- Xác nhận certificate **issuer/trust domain, subject/SPIFFE ID, expiry** và service account mapping.
- Kiểm tra **inbound authZ** thực tế (effective policy), không sửa mTLS certificate validation nếu cert hợp lệ.
- Đánh giá business authorization của **orders-v2**, không cho phép principal mới chỉ vì tên gần giống.
- Cập nhật policy **explicit identity** sau review, rollout hẹp, kiểm tra **orders-v2 ALLOW** và **unauthorized-principal DENY**.
- Theo dõi **proxy DENY, application requests và Pod identity** sau đổi.

### 23.3. Bài học

**Network reachability và TLS identity hợp lệ không đồng nghĩa application authorization ALLOW.** Một thay đổi ServiceAccount name có thể tác động trực tiếp tới **mTLS principal/mesh authorization** dù địa chỉ IP, DNS và ứng dụng không đổi.

## 24. Case study C: egress gateway bị bỏ qua khi gọi external API

**Bối cảnh giả định:** Tổ chức bắt buộc Orders gọi external fraud API qua một egress gateway để kiểm soát TLS/traffic và lưu metadata. Dashboard gateway gần như không có traffic, nhưng NAT gateway cho thấy outbound TCP/443 từ một số Orders Pod IP tới external IP.

### 24.1. Phạm vi điều tra

| Observation | Giả thuyết | Bằng chứng bổ sung |
| --- | --- | --- |
| Sidecar outbound ít requests qua gateway | Route/ServiceEntry không match, passthrough | Effective outbound cluster và route |
| NAT vẫn thấy egress | Pod hoặc node có direct route | CNI/SG/firewall, source Pod UID/time |
| Ứng dụng hoạt động bình thường | External API reachable, không chứng minh gateway policy | Gateway logs và TLS endpoint metadata |
| Một nhóm Pods thiếu proxy | Injection label/webhook lỗi hoặc Pod cũ | Effective Pod spec, proxy readiness |
| External hostname có nhiều IP | DNS/caching, route classification khác | DNS logs, SNI, destination IP mapping |

### 24.2. Kế hoạch sửa

1. Vẽ **app→sidecar→egress gateway→NAT/firewall→external** ở từng network hop.
2. Kiểm tra **mesh route/service registration, proxy capture, sidecar mode, protocol và exclusion**.
3. Đặt **network egress deny** ngoài gateway theo policy được phép và khả năng CNI/cloud network.
4. Bảo đảm gateway **xác minh TLS peer** của external service, không tắt hostname verification.
5. Bổ sung **metrics direct egress vs gateway egress**, canary một workload, theo dõi false positives.
6. Kiểm thử **ALLOW fraud API qua gateway**, **DENY direct IP bypass** và **DENY endpoints khác**; kiểm tra IPv4/IPv6 nếu dùng dual-stack.

### 24.3. Bài học

**Chính sách egress ở mesh chỉ có hiệu lực trên đường dữ liệu nó quản lý**. Nếu sidecar hoặc gateway bị bypass, cần **NetworkPolicy/cloud firewall/route enforcement** độc lập, không chỉ thêm một route để hy vọng app tự sử dụng.

## 25. Lab Python offline: diễn giải hành trình và điểm lỗi của request

Mục tiêu là phân loại các sự kiện **giả lập** theo những chặng: app source, outbound sidecar, network, inbound sidecar, app destination. Code chỉ xử lý dữ liệu trong memory; **không mở socket, không truy cập Kubernetes API, không tạo cert/secret, không chạy proxy và không gửi request**.

### 25.1. Dữ liệu và quy tắc

- Một request có thể có **không đủ evidence** vì logging bị tắt/chậm, nên kết luận có nhãn **unknown** thay vì đoán.
- Nếu remote inbound proxy ghi **DENY**, biết request bị chặn tại policy của proxy; không suy Payments app đã xử lý.
- Nếu outbound ghi **no_healthy_upstream**, request có thể chưa đến network/remote sidecar; không đổ lỗi ngay cho ứng dụng.
- Nếu hai proxies **ALLOW** nhưng app trả **403**, có thể là business authorization, không phải lỗi mTLS.
- Các status trong lab là **nhãn chuẩn hóa tự định nghĩa**, không phải Envoy stats/response flags chính thức.

~~~python
from dataclasses import dataclass


@dataclass(frozen=True)
class Evidence:
    request_id: str
    source_app_sent: bool
    outbound_decision: str | None
    outbound_upstream: str | None
    remote_inbound_decision: str | None
    remote_peer: str | None
    destination_app_status: int | None


def assess_path(e: Evidence) -> tuple[str, str]:
    """Phân loại điểm kiểm tra, không khẳng định root cause tuyệt đối."""
    if not e.source_app_sent:
        return ("SOURCE_APP", "No request emitted in the simulated evidence")

    if e.outbound_decision is None:
        return ("UNKNOWN", "Missing outbound proxy evidence")

    if e.outbound_decision == "NO_HEALTHY_UPSTREAM":
        return ("OUTBOUND_DISCOVERY", "Check route, cluster and endpoints")

    if e.outbound_decision == "DENY":
        return ("OUTBOUND_POLICY", "Check outbound authorization")

    if e.outbound_decision != "ALLOW":
        return ("UNKNOWN", "Unrecognized outbound status")

    if e.remote_inbound_decision is None:
        return ("UNKNOWN", "Check network, mTLS or missing inbound logs")

    if e.remote_inbound_decision == "DENY":
        return ("INBOUND_POLICY", "Check authenticated peer and policy")

    if e.remote_inbound_decision != "ALLOW":
        return ("UNKNOWN", "Unrecognized inbound status")

    if e.destination_app_status is None:
        return ("UNKNOWN", "Check app evidence and response telemetry")

    if e.destination_app_status >= 500:
        return ("APP_OR_DEPENDENCY", "Investigate application response")

    if e.destination_app_status in (401, 403):
        return ("APP_AUTHORIZATION", "Investigate user/tenant access")

    return ("END_TO_END_OBSERVED", "Observed app status; inspect semantics")


samples = [
    Evidence("req-1", True, "NO_HEALTHY_UPSTREAM", None, None, None, None),
    Evidence("req-2", True, "ALLOW", "payments-1", "DENY",
             "spiffe://corp.example.org/ns/prod-apps/sa/orders-v2", None),
    Evidence("req-3", True, "ALLOW", "payments-1", "ALLOW",
             "spiffe://corp.example.org/ns/prod-apps/sa/orders", 403),
    Evidence("req-4", True, "ALLOW", "payments-2", None, None, None),
    Evidence("req-5", True, "ALLOW", "payments-2", "ALLOW",
             "spiffe://corp.example.org/ns/prod-apps/sa/orders", 200),
]

for e in samples:
    print(e.request_id, assess_path(e)[0])

assert assess_path(samples[0])[0] == "OUTBOUND_DISCOVERY"
assert assess_path(samples[1])[0] == "INBOUND_POLICY"
assert assess_path(samples[2])[0] == "APP_AUTHORIZATION"
assert assess_path(samples[3])[0] == "UNKNOWN"
assert assess_path(samples[4])[0] == "END_TO_END_OBSERVED"
~~~

Kết quả mong đợi:

~~~text
req-1 OUTBOUND_DISCOVERY
req-2 INBOUND_POLICY
req-3 APP_AUTHORIZATION
req-4 UNKNOWN
req-5 END_TO_END_OBSERVED
~~~

### 25.2. Những gì lab không thể chứng minh

1. Không xác minh **JWT/certificate signatures**, SPIFFE ID, TLS negotiation, IAM hay Kubernetes RBAC.
2. Không biết **request thực đã đi qua những NICs** hay ingress/egress gateway nào.
3. Không mô phỏng **retries, HTTP/2 multiplexing, NAT, route reconfiguration hay endpoint churn**.
4. Nhãn **END_TO_END_OBSERVED** chỉ nói app status đã hiện diện trong record, **không chứng minh payment thành công về nghiệp vụ**.
5. Thiếu inbound log có thể vì **network drop, sidecar crash, sampling, logging disabled hoặc sai correlation ID**, không phải chắc mạng lỗi.
6. Không có admin/debug endpoints, không đọc logs thật hoặc config production.

### 25.3. Bài tập mở rộng

1. Thêm trường **event_time/ingest_time** theo UTC, phát hiện log đến trễ so với request.
2. Thêm **source/destination Pod UID** và historical IP mapping để tránh gán nhầm Pod đã thay.
3. Thêm **route/cluster config revision** và so giữa control plane với effective proxy.
4. Thêm **attempt_count/retry_status**, giải thích tác động với POST không idempotent.
5. Bổ sung **mTLS peer verified** có thể là true/false/unknown; không đặt true mặc định nếu thiếu log.
6. Phân biệt **application 403** với **sidecar policy DENY** qua điểm phát response.
7. Thêm một test **authorized egress gateway path** và một test **direct egress bypass**, chỉ dùng dữ liệu mô phỏng.
8. Xây dựng summary có **evidence confidence**, không gắn nhãn attack khi chỉ có một triệu chứng.

## 26. Runbook vận hành: từ thay đổi cấu hình tới rollback an toàn

Khi triển khai mesh policy hoặc route mới, các sự cố thường liên quan **người có quyền sửa control plane, proxy nào đã nhận cấu hình và endpoint nào thực sự được chọn**. Một runbook an toàn cần kiểm tra **availability lẫn security ALLOW/DENY**, không chỉ thấy “lỗi hết rồi”.

### 26.1. Trước khi thay đổi

1. **Ghi rõ mục tiêu:** Thêm mTLS STRICT, thay service account principal, chuyển canary, thêm egress gateway hay rotate CA?
2. **Vẽ request path hiện tại và dự kiến** theo app/outbound proxy/network/inbound proxy/app; đánh dấu ingress/egress gateways nếu có.
3. **Inventory workloads và capture:** Namespaces, sidecar injection status, outbound/inbound listeners, excluded ports, ambient segments.
4. **Chốt policy:** Workload identity, trust domain, app method/route, external destination, fallback và default-deny semantics.
5. **Snapshot cấu hình có quyền:** Mesh resources, effective xDS, healthy endpoints, certificate expiry, Cloud SG/CNI/NetworkPolicy.
6. **Đo baseline:** Success rate, HTTP/gRPC statuses, p95/p99, retries, connection/stream counts, proxy CPU/memory.
7. **Lập kế hoạch rollback:** Ai phê duyệt, thay đổi nào có thể đảo, tình huống không được mở lại insecure/plaintext.

### 26.2. Canary rollout và kiểm tra

~~~mermaid
flowchart TD
    A["Approve plan + immutable change record"] --> B["Deploy staging / canary slice"]
    B --> C["Read effective proxy route, endpoint and mTLS policy"]
    C --> D["Run ALLOW and DENY tests from authorized workloads"]
    D --> E{"SLI and security checks pass?"}
    E -- "Không" --> F["Safe rollback or fix-forward"]
    E -- "Có" --> G["Gradually increase coverage"]
    G --> H["Check control/data plane convergence"]
    H --> I["Audit, post-change diagrams and handoff"]
~~~

**Canary traffic** cần được chọn theo identity/session/tenant phù hợp, không chỉ theo một tỷ lệ request nếu application stateful. Với payment, POST operations và streaming RPCs, tránh **mirror/duplicate real transactions** để so sánh hai backends.

### 26.3. Rollback không phải mở ANY/ANY

Nếu mTLS STRICT gây outage do Pod chưa injection, các phương án có thể là **sửa injection/cert/trust/binding** hoặc rollback policy theo phương án đã được **security owner phê duyệt**. Không tự chuyển toàn mesh thành **PERMISSIVE**, tắt authorization, chấp nhận unknown CA hoặc cho external passthrough mọi đích. Hãy phân biệt **outage về kỹ thuật** với **security exception có thời hạn**.

### 26.4. Mẫu change/incident ticket

~~~text
CHANGE / INCIDENT ID:
Owner / security reviewer / UTC window:
Source workload, namespace, ServiceAccount, cluster:
Destination workload/endpoint and route:
Expected app flow / network and TLS hops:
Expected peer principal / trust domain / auth policy:
Current proxy config revision, inbound/outbound listeners:
Routing: host/path, cluster, endpoints, retries, timeouts:
Capture: CNI, excluded ports, inbound/outbound mode:
Network: CNI policy, SG/firewall, LB/NAT, IPv4/IPv6:
Evidence: proxy logs, xDS, SDS, application, flow logs:
Security tests: ALLOW caller, DENY unauthorized/bypass:
App SLI / p95/p99 / streaming behavior:
Rollback criteria and owner:
Readback / remaining risk / postmortem:
~~~

### 26.5. Khi nghi sidecar bị chiếm hoặc private key lộ

1. Xác định **scope/identity** của proxy bị ảnh hưởng, Pod/node và tất cả services nó có quyền kết nối.
2. Cô lập workload hoặc chặn peer principal **tại verifier** theo incident plan, không chỉ xóa Pod.
3. Rotate/replace **workload certificate/private key** và review CA/trust; leaf key leak **không tự đồng nghĩa** CA private key bị lộ.
4. Correlate **mTLS peer auth, application authorization, cloud IAM, CNI flow và Kubernetes audit** để tìm misuse.
5. Bảo vệ **proxy config dumps, heap/core dumps, keylogs và raw access logs** khỏi tiếp tục phát tán secrets.
6. Phục hồi qua immutable/deployed image tin cậy, xác minh old identity không còn được chấp nhận theo policy và legitimate service SLO ổn.

## 27. Ma trận kiểm thử sidecar và request path

Mọi phép thử chủ động chỉ thực hiện trên **lab, staging hoặc tài sản được cấp quyền**, với **owner, time window, canary/rollback**. Không quét hoặc thử bypass mạng ngoài phạm vi được phép; không trích xuất mTLS private keys/TLS keylogs thật để chứng minh mesh hoạt động.

| Test ID | Tình huống | Kết quả/bằng chứng kỳ vọng |
| --- | --- | --- |
| SM-01 | Orders Pod có sidecar injection | Effective Pod spec/containers/volumes đúng, proxy ready |
| SM-02 | Pod mới đã bật injection label | Pod được tạo với proxy; Pod cũ được đánh giá riêng |
| SM-03 | Admission webhook/CNI setup trong lab lỗi | Failure policy được hiểu; không chạy unmeshed ngoài ý định |
| SM-04 | Outbound HTTP từ Orders → Payments | Local capture, outbound route, upstream endpoint đúng |
| SM-05 | Inbound Payments từ peer Orders | mTLS peer ID được verify, inbound route tới app đúng |
| SM-06 | App gọi localhost | Capture/bypass behavior đúng theo thiết kế và policy |
| SM-07 | App gọi direct Pod IP | Không bypass policy bắt buộc; DENY nếu trái mục tiêu |
| SM-08 | DNS service name | Records/TTL, route/cluster và effective endpoints phù hợp |
| SM-09 | Headless service/direct endpoints | Traffic capture và identity mapping đúng |
| SM-10 | Kubernetes EndpointSlice thay đổi khi scale | Proxy endpoint membership cập nhật, không route stale ngoài ý định |
| SM-11 | Empty upstream endpoint pool | Sidecar không âm thầm route sang Dev/unknown destination |
| SM-12 | mTLS đúng Orders identity | TLS peer verification và authZ ALLOW theo scope |
| SM-13 | mTLS cert sai CA/trust domain | Inbound/outbound DENY, không tự fallback plaintext |
| SM-14 | mTLS cert expired | Handshake bị từ chối, cảnh báo và rotate/reload đúng |
| SM-15 | Permissive vs Strict migration | Phát hiện plaintext clients, cutoff/STRICT test rõ |
| SM-16 | Workload principal không được phép | Inbound authZ DENY; app không nhận request theo policy |
| SM-17 | Workload được kết nối nhưng gọi admin operation | L7/app authorization DENY đúng nơi |
| SM-18 | User của tenant A truy cập payment tenant B | App object-level authorization DENY dù mTLS tốt |
| SM-19 | Proxy route theo HTTP Host/path | Upstream cluster đúng; unknown route safe reject |
| SM-20 | Opaque TCP qua proxy | Không coi L7 method rules là đã thực thi trên ciphertext |
| SM-21 | HTTP/2/gRPC unary | HTTP/2 semantics, trailers, gRPC status và timeout đúng |
| SM-22 | gRPC streaming/WebSocket | Connection lifecycle, drain, reconnect an toàn |
| SM-23 | Retry POST có side effect | Không nhân đôi giao dịch khi chưa có idempotency contract |
| SM-24 | Proxy circuit breaker/pending queue | Tách local rejection với app 503, capacity đo được |
| SM-25 | Client-facing ingress gateway | Public auth/WAF/TLS và gateway→service policy đúng |
| SM-26 | Direct origin/NodePort bypass | Network ingress DENY khi không qua gateway hợp lệ |
| SM-27 | Egress gateway cho external API | Outbound đi đúng gateway, TLS peer được verify |
| SM-28 | Direct external IP path từ Pod | DENY ngoài egress policy, kể cả IPv6 nếu áp dụng |
| SM-29 | Sidecar exclusions | Chỉ những port/IP có exception phê duyệt được bypass |
| SM-30 | HostNetwork/NodeLocal workloads | Bảo vệ bằng enforcement riêng, không mặc định Pod capture |
| SM-31 | IPv4 và IPv6 dual-stack | Endpoint discovery, capture, TLS, network policy đồng bộ |
| SM-32 | Sidecar configuration update | xDS/config version readback, convergence theo kỳ vọng |
| SM-33 | Control-plane outage tabletop | Last-known config behavior/cert renewal gaps được ghi |
| SM-34 | SDS/certificate rotation | New handshake dùng cert mới, old identity rejected theo policy |
| SM-35 | ServiceAccount rename | Peer identity và inbound allowlist được cập nhật có kiểm soát |
| SM-36 | App rollback/termination | Proxy drain và app shutdown không mất dữ liệu ngoài mục tiêu |
| SM-37 | Tracing/request ID | App/outbound/inbound/app logs được correlate, không lộ token |
| SM-38 | VPC flow vs proxy access logs | Không coi một TCP flow bằng một HTTP request |
| SM-39 | Proxy config dump/debug endpoint | Chỉ admin hợp lệ có quyền, secrets được redact |
| SM-40 | Proxy resource saturation | CPU/memory/FD/queue và app SLI được đo |
| SM-41 | Bounded retry khi upstream lỗi | Không có retry amplification vượt policy |
| SM-42 | Wrong service port protocol | Phát hiện sniffing/route mismatch, khai báo đúng protocol |
| SM-43 | Mesh traffic giữa clusters/DR | Trust, route, gateway, policy và identity không drift |
| SM-44 | NetworkPolicy khi proxy capture đổi port | ALLOW traffic mong đợi, DENY bypass sau kiểm chứng |
| SM-45 | Sidecar bị nghi compromise tabletop | Revoke peer identity, giữ bằng chứng, khôi phục app hợp lệ |

### 27.1. Mẫu hồ sơ kiểm thử

~~~text
TEST / CHANGE ID:
Environment / namespace / cluster / IP family:
Source app, Pod UID, ServiceAccount, proxy version:
Destination service, Pod UID, ServiceAccount, app port:
Time (UTC), request ID, protocol (HTTP/gRPC/TCP):
Expected capture: inbound/outbound, exclusions:
Expected route/cluster/endpoint:
Expected mTLS peer subject/trust and authorization:
App request and response expected:
Observed outbound and inbound proxy evidence:
Observed CNI/network/flow evidence:
Observed application/auth evidence:
Expected ALLOW/DENY vs actual:
Config revision, retries, timeout, cert expiry:
Quality gaps / owner / rollback:
~~~

### 27.2. Kiểm tra cả đường đúng và đường sai

Một test **Orders→Payments success** không chứng minh **Dev→Payments** bị chặn; cần kiểm tra **DENY của principal không đúng**. Một test **mTLS handshake successful** không chứng minh **user tenant authorization** đúng. Cần ít nhất ba lớp:

1. **Connectivity:** Packet/connection tới đúng remote endpoint; không bypass.
2. **Identity/security:** mTLS peer identity, L4/L7 authZ, WAF/ingress/egress, network segmentation.
3. **Business:** Payment/user/tenant authorization, response semantics và idempotency.

Nếu thiếu bằng chứng một lớp, ghi **UNKNOWN/NOT VERIFIED**, không tự kết luận toàn chuỗi bảo vệ đã thành công.

## 28. Những hiểu nhầm thường gặp về sidecar và đường đi request

| Nhận định sai | Cách hiểu đúng |
| --- | --- |
| “Sidecar là một máy chủ đứng giữa hai Pods.” | Thường là proxy chạy cùng Pod; thêm điểm xử lý, không nhất thiết thêm hop mạng vật lý riêng. |
| “Mọi request của Pod tự động qua sidecar vì đã injection.” | Capture phụ thuộc CNI/iptables, port/IP exclusion, protocol và network namespace. |
| “Control plane xử lý HTTP mỗi lần app gọi.” | Data plane proxy xử lý sau khi nhận cấu hình; control plane không nằm trên mỗi request path. |
| “Pod có sidecar là chắc đã bật mTLS.” | Có thể PERMISSIVE, passthrough, peer ngoài mesh hoặc mTLS policy chưa áp. |
| “mTLS là mã hóa end-to-end từ process app sang process app.” | Nhiều mô hình terminate TLS tại sidecars; local hops có thể plaintext. |
| “Certificate mTLS đúng CA là client được gọi mọi API.” | Cần peer identity authorization và user/resource authorization. |
| “IP Pod là danh tính service ổn định.” | Pod IP có thể thay đổi/reuse; workload identity phù hợp hơn cho auth. |
| “Service DNS trả ClusterIP nghĩa là sidecar luôn gửi tới ClusterIP.” | Mesh có thể chọn backend endpoint trực tiếp từ discovery. |
| “Xóa Pod thì mọi connection lập tức chuyển backend.” | Connection pools, streams và draining có thể giữ old endpoint tới một mốc. |
| “Readiness OK là mọi upstream có thể gọi được.” | Còn proxy route, endpoint, TLS, CNI, authorization và dependencies. |
| “503 luôn do ứng dụng backend trả.” | Sidecar/gateway có thể trả 503 do upstream, circuit hoặc timeout. |
| “Có HTTP/2 connection là chỉ có một RPC.” | HTTP/2 multiplex nhiều streams/requests trên một connection. |
| “Mesh HTTP retry luôn làm hệ thống ổn định hơn.” | Retry sai có thể nhân đôi side effect và khuếch đại tải. |
| “5% traffic canary nghĩa là 5% người dùng.” | Có thể là tỷ lệ requests/streams, không tương đương users. |
| “mTLS L4 kiểm tra được HTTP path trong TLS ciphertext.” | L7 rule đòi hỏi proxy thấy/parse HTTP; opaque TCP không có dữ liệu đó. |
| “Lệnh curl từ Pod thành công là chứng minh không có mesh bypass.” | Có thể thành công qua direct route; cần xác minh proxy logs và chính sách. |
| “Sidecar có thể bảo vệ traffic hostNetwork theo cùng cách Pod thường.” | Host network có capture/segmentation khác, cần enforcement riêng. |
| “DNS policy cũng là identity authentication.” | DNS trả địa chỉ; peer identity vẫn cần TLS/cert/app auth. |
| “Egress gateway tồn tại là Pod không thể gọi Internet trực tiếp.” | Cần CNI/firewall/route DENY và kiểm thử bypass. |
| “NetworkPolicy YAML là chắc chắn được thực thi.” | CNI phải hỗ trợ; selectors và port sau capture cần xem đúng. |
| “Sidecar proxy không đọc HTTP vì trên wire đã mTLS.” | Proxy thường chính là TLS endpoint và thấy HTTP để route. |
| “Proxy log ALLOW chứng minh user có quyền business.” | Mesh workload authorization khác tenant/order authorization. |
| “X-Forwarded-For là IP client thật được chứng thực.” | Header có thể bị client giả; trusted ingress phải chuẩn hóa. |
| “Một TCP flow log bằng một request.” | Keep-alive/HTTP2/gRPC multiplexing tạo nhiều requests trên một flow. |
| “Config đổi ở control plane là mọi proxy đã đổi.” | Phải xác minh xDS ACK, effective config và convergence. |
| “Proxy admin endpoint công khai giúp debug tiện.” | Có thể lộ cấu hình/secrets và quyền điều khiển, phải hạn chế truy cập. |
| “Khi control plane lỗi, dữ liệu luôn ngừng hoặc luôn chạy.” | Tùy last-known config, cert expiry, proxy restarts và implementation. |
| “Ambient mode là sidecar nhưng không thấy container.” | Đường dữ liệu và điểm enforce L4/L7 có thể khác; thường phải kiểm tra waypoint. |
| “Chuyển STRICT sang PERMISSIVE để chữa 503 là vô hại.” | Có thể mở plaintext/unauthorized path, cần phê duyệt và giới hạn. |
| “mTLS proxy-to-proxy đủ bảo vệ trước compromised app process.” | App bị chiếm có thể gọi API với chính workload identity; cần least privilege/monitoring. |

## 29. Câu hỏi tự kiểm tra và bài tập kiến trúc

1. **Sidecar proxy là gì?** Một proxy xử lý traffic cùng workload, thường trong Pod, thuộc mesh data plane.
2. **Control plane khác data plane thế nào?** Control plane phân phối discovery/policy/cert config, proxy data plane xử lý traffic thực.
3. **Tại sao app không cần đổi URL để dùng sidecar?** Transparent interception có thể chuyển traffic tới proxy bằng CNI/netfilter hoặc cơ chế phù hợp.
4. **REDIRECT và TPROXY cùng là gì?** Các kỹ thuật chuyển hướng traffic vào proxy; khác cách giữ original destination và routing/socket semantics.
5. **Có sidecar mà traffic vẫn bypass được không?** Có, do exclusions, protocol, host networking hoặc capture không hoạt động.
6. **Outbound listener làm gì?** Nhận traffic từ app, xác định route/cluster/endpoints và thường tạo upstream connection.
7. **Inbound listener làm gì?** Nhận traffic đến Pod, kiểm tra peer mTLS/policy rồi chuyển tới app.
8. **DNS trả ClusterIP thì route đã quyết định hết chưa?** Chưa; mesh/kube-proxy/CNI còn có thể chọn endpoint.
9. **Một Pod endpoint đổi thì connection cũ lập tức hết không?** Không nhất thiết, vì connection pooling/draining.
10. **mTLS sidecar-to-sidecar mã hóa những chặng nào?** Thường giữa hai proxies; local app↔proxy có thể plaintext.
11. **Vì sao peer identity khác TCP source IP?** Source IP có thể thay đổi qua NAT/proxy, identity mTLS dựa trên credentials được verify.
12. **SPIFFE ID hữu ích để làm gì?** Định danh workload phục vụ peer authentication/authorization trong trust domain.
13. **LDS/RDS/CDS/EDS/SDS khác nhau gì?** Listeners, routes, clusters, endpoints và TLS secrets.
14. **Tại sao cần effective proxy config?** CRD/control-plane policy đã khai báo không chứng minh proxy đã nhận và áp dụng.
15. **Tại sao một sidecar trả 503 dù app backend còn khỏe?** Pool rỗng, connect errors, circuit breaking, timeouts hoặc stale config.
16. **HTTP/2 multiplexing ảnh hưởng load balancing ra sao?** Nhiều RPCs trên một TCP connection, không nên chỉ cân bằng theo connection count.
17. **Vì sao không retry mọi payment POST?** Có thể backend đã commit nhưng response mất, retry tạo giao dịch trùng.
18. **Permissive mTLS khác Strict?** Permissive có thể chấp nhận plaintext trong quá trình migration, Strict yêu cầu mTLS theo policy.
19. **Một workload biết peer là Orders có thể bỏ user authorization không?** Không; cần object/tenant/function permission.
20. **Ingress gateway và sidecar có cùng chức năng ở mọi chặng không?** Không; gateway ở ranh giới, sidecar tại workload, TLS/policy tùy hop.
21. **Egress gateway không thấy traffic nghĩa là không có outbound không?** Không; có thể direct bypass/NAT, capture hoặc route sai.
22. **NetworkPolicy có thể giữ Pod khỏi bypass mesh không?** Có thể là một lớp quan trọng nếu CNI thực thi đúng, nhưng cần kiểm tra kiến trúc và exceptions.
23. **Trace ID từ client có tự xác thực nguồn không?** Không; ingress phải normalize và logs gắn identity đã xác minh.
24. **Vì sao flow logs không cho biết HTTP method?** L3/L4 metadata không thấy L7 payload qua TLS.
25. **Khi node-level ambient data plane thay sidecar, cần làm gì?** Vẽ lại hop/identity/L7 waypoint, kiểm tra policy/telemetry/capture thực.
26. **Một mTLS cert đã rotate thì session cũ được hủy tức thì không?** Không mặc định; connection cache/session lifetime cần kiểm soát.
27. **Khi một client lỗi sau rollback, cần tìm bằng chứng nào?** App/sidecar logs, effective route/endpoint/cert, CNI/NetworkPolicy, UTC change timeline.
28. **Mục tiêu của ALLOW/DENY regression?** Service hợp lệ phục vụ được và đường trái quyền/bypass vẫn bị từ chối.

### Bài tập cuối chương

Một tổ chức chạy Kubernetes có ba namespaces **dev, staging, prod**, triển khai **orders → payments → inventory** qua HTTP/gRPC. Có cloud L4 load balancer, public API ingress, một dịch vụ fraud API bên ngoài, Kafka TCP, service mesh sidecars mTLS, egress gateway và NetworkPolicy. Payments đang thử canary 10%; sau rollout, tỷ lệ 503 và gRPC UNAVAILABLE tăng. Đồng thời team an ninh thấy một số Pods direct egress tới public IP mà không qua gateway.

Hãy thiết kế tài liệu:

1. **Sơ đồ request path** từ mobile client → CDN/WAF → ingress gateway → Orders sidecar/app → Payments sidecar/app → Inventory, chú thích TLS termination.
2. **Inbound/outbound capture points** theo Pod/CNI; phân biệt loopback, Pod IP, Service VIP, UDP và hostNetwork.
3. **Bảng identity/trust:** CA/trust domain, ServiceAccount/SPIFFE ID, source principal và policies cho mỗi RPC.
4. **Topology và routing:** Gateway, clusters/endpoints, VirtualService/HTTPRoute pseudocode, 10% canary và timeout/retry limits.
5. **Mô hình connection reuse:** HTTP/2, gRPC streaming, graceful draining, connection pools và endpoint update lag.
6. **Phân đoạn mạng:** Cho phép những luồng thật sự cần, chặn direct origin/Dev→Prod/unknown egress.
7. **Threat model:** Bypass sidecar, route/header confusion, mTLS key compromise, external TLS origination, SSRF/metadata.
8. **Triage 503:** Thu proxy route/cluster/response flags, EndpointSlice/readiness, inbound authZ, application DB status và xDS/SDS.
9. **Telemetry/SLI:** Request IDs đã được chuẩn hóa, p95/p99, app vs proxy responses, retry attempts và flow logs.
10. **Ma trận tối thiểu 12 test:** Authorized ALLOW, wrong principal DENY, unknown route DENY, direct egress DENY, mTLS CA mismatch, DR/IPv6, stream drain và safe rollback.

**Tiêu chí chấm:** Bản thiết kế phải thể hiện **đường đi từng request ở cả lớp mạng và ứng dụng**, ai quyết định route, **peer identity được verify ở đâu**, những hop nào nhìn plaintext, vì sao policy không bị bypass và cách chứng minh hệ thống phục vụ hợp lệ sau failover.

## 30. Checklist xác minh sidecar và request path trong service mesh

- [ ] Đã xác định **workloads, ServiceAccounts, Pod UID, namespaces, clusters và owners**?
- [ ] Có sơ đồ **app → outbound proxy → network → inbound proxy → app**, gồm gateway nếu có?
- [ ] Đã kiểm tra **control plane vs data plane** và nơi phân phối policy/config?
- [ ] Mọi Pods dự kiến được mesh quản lý có **sidecar injection và proxy ready** thật không?
- [ ] Các Pods cũ sau đổi injection policy được rollout/recreate theo kế hoạch?
- [ ] Capture mode **REDIRECT/TPROXY/eBPF/CNI**, exclusion ports/CIDRs được review?
- [ ] Có kiểm thử **loopback, direct Pod IP, Service VIP, hostNetwork, init/ephemeral Pod** theo scope?
- [ ] Giao thức **HTTP/1.1, HTTP/2, gRPC, raw TCP và UDP/QUIC** có support đúng yêu cầu?
- [ ] **DNS resolution, cache, EndpointSlices, service registry và effective clusters** được kiểm tra?
- [ ] Route match **Host/:authority, path, method** không đẩy unknown traffic tới wrong backend?
- [ ] Chọn endpoint, locality, canary, connection pooling và readiness có cùng mục tiêu?
- [ ] Biết proxy xử lý **full connection hay HTTP request/stream**, không suy một TCP flow là một request?
- [ ] Có cấu hình **bounded retries, per-route timeout, circuit breaking, backpressure**?
- [ ] Không retry **payment/POST có side effect** nếu chưa chứng minh idempotency?
- [ ] **mTLS identity và expected peer principal** được verify với trust domain phù hợp?
- [ ] Có phân biệt **PERMISSIVE/STRICT**, traffic plaintext và ngoại lệ migration có hạn?
- [ ] **SDS/certificate/private key** có owner, TTL, refresh/reload và revocation plan?
- [ ] Biết chính xác **TLS terminate/originate tại đâu**, local hops có plaintext hay không?
- [ ] Mesh L4/L7 authZ chỉ cho **đúng source workload và operation**, default policy an toàn?
- [ ] Payments/app vẫn kiểm tra **end-user, tenant, object/resource permissions**?
- [ ] Ingress gateway auth/WAF/TLS được thực thi, **direct origin/NodePort bypass** bị chặn?
- [ ] Egress gateway là đường bắt buộc hoặc đã có **network DENY direct egress** ngoài danh sách?
- [ ] **NetworkPolicy/CNI, cloud SG/firewall, service mesh authZ** đã được đối chiếu cùng đường dữ liệu?
- [ ] **IPv4/IPv6, multi-cluster, trust domains, DR region** có cùng chính sách mong muốn?
- [ ] HTTP headers như **XFF, user principal và trace ID** chỉ được tin từ ingress/proxy hợp lệ?
- [ ] Effective config gồm **listeners, routes, clusters, endpoints, TLS/policy** được đọc lại sau change?
- [ ] Có theo dõi **xDS ACK/NACK/config staleness, certificate expiry, control-plane availability**?
- [ ] **App/proxy/network logs** có request correlation và source/peer identities đúng?
- [ ] Logs/traces **không chứa credentials, cookies, PII hoặc TLS keylogs** ngoài scope kiểm soát?
- [ ] Sidecar admin/debug endpoints có **RBAC/network access** bảo vệ?
- [ ] Capacity gồm **app + sidecar CPU/RAM/FD/TLS/telemetry** và N+1 theo requirements?
- [ ] Có **readiness/drain/rollout plan** cho gRPC streams/WebSocket/long-lived TCP?
- [ ] Đã thực hiện **ALLOW authorized + DENY unauthorized/bypass** từ từng đường vào/ra quan trọng?
- [ ] Khi lỗi có runbook **DNS → capture → proxy route → network/mTLS → inbound policy → app**?
- [ ] Có **change owner, approval, canary, safe rollback và post-change readback**?

**Kết luận:** **Sidecar proxy** đưa định tuyến, TLS/mTLS, policy và telemetry vào **data plane gần workload**, nhờ đó request giữa hai dịch vụ thường có đường đi **ứng dụng nguồn → outbound proxy → mạng → inbound proxy → ứng dụng đích**. Nhưng kiến trúc thực tế còn phụ thuộc **traffic interception, DNS/CNI, service discovery, proxy configuration, endpoint health, connection reuse, gateway và các đường bypass**. mTLS chứng thực workload trên **những hop được cấu hình**, không thay thế application authorization hoặc network segmentation. Khi thiết kế và điều tra, phải chứng minh **sidecar thật sự nhìn thấy request, proxy chọn đúng đích, TLS peer được verify, ứng dụng trả kết quả đúng và các đường không được phép vẫn DENY**.
