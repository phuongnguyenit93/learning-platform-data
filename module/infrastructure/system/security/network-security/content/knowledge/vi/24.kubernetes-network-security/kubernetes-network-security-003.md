# Ingress controller và trust boundary: Bảo vệ điểm vào Kubernetes

## 1. Vì sao Ingress controller là một ranh giới tin cậy quan trọng?

Trong Kubernetes, nhiều ứng dụng chạy trong các Pod có địa chỉ IP nội bộ và được truy cập thông qua **Service**. Khi cần đưa ứng dụng HTTP/HTTPS ra cho người dùng ngoài cluster, hệ thống thường dùng **Ingress controller** hoặc một gateway tương đương làm điểm nhận, xử lý và định tuyến lưu lượng. Đây là nơi một request đi từ **vùng có mức tin cậy thấp** (Internet, mạng đối tác hoặc mạng người dùng) vào **vùng chứa workload và dữ liệu**.

Một ví dụ phổ biến:

~~~text
Internet client
  -> CDN / WAF (nếu có)
  -> Public cloud load balancer
  -> Ingress controller
  -> Kubernetes Service
  -> Application Pod
  -> Database / internal services
~~~

**Ingress controller không tự biến một ứng dụng thành an toàn.** Nó có thể chọn backend theo hostname/path, kết thúc TLS và áp dụng một số chính sách, nhưng **xác thực danh tính, phân quyền nghiệp vụ, NetworkPolicy, firewall, DNS, bảo vệ secret và kiểm soát egress** vẫn là những trách nhiệm riêng. Nếu header được tin sai, Ingress có thể truyền một địa chỉ IP giả cho ứng dụng. Nếu quyền cấu hình Ingress quá rộng, một tenant có thể tác động đường vào của tenant khác. Nếu traffic từ controller tới backend đi qua HTTP, HTTPS ở trình duyệt **không chứng minh** nội dung đã mã hóa đến Pod.

### Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân biệt **Ingress resource**, **IngressClass**, **Ingress controller**, **Service**, **EndpointSlice** và **cloud load balancer**.
2. Vẽ được các **trust boundaries** từ người dùng tới Pod và xác định nơi cần xác minh dữ liệu/identity.
3. Phân tích TLS termination, TLS passthrough, re-encryption, SNI, `Host` và chứng thư số theo từng hop.
4. Chỉ ra rủi ro khi tin `X-Forwarded-For`, `X-Forwarded-Proto`, `X-Forwarded-Host`, `Forwarded` hoặc header đặc thù của CDN.
5. Thiết kế **NetworkPolicy**, cloud firewall, nguồn client IP đáng tin và giới hạn đường đi vòng qua Ingress.
6. Phân quyền việc tạo/sửa Ingress, annotations, TLS Secrets, IngressClass và các thành phần controller theo nguyên tắc ít quyền nhất.
7. So sánh vai trò Ingress API và **Gateway API**, đặc biệt trong môi trường đa nhóm/đa tenant.
8. Xây bộ kiểm thử positive/negative, quan sát log và điều tra lỗi routing, TLS, WAF hoặc policy.

Chủ đề thuộc chương **Bảo mật mạng Kubernetes**, module **SECURITY_NETWORK_SECURITY**: từ phân đoạn, firewall, VPN, IDS/IPS, DNS và xác thực kết nối đến bảo vệ kênh TLS, mạng container và hạ tầng cloud.

> **Phạm vi an toàn:** ví dụ sử dụng `*.lab.example.test`, IP dành cho tài liệu như `192.0.2.10`, `198.51.100.24` và namespace lab. Chỉ quan sát hoặc gửi những request được cấp phép tới môi trường mình quản lý. YAML minh họa có thể **thay đổi lưu lượng thật** nếu áp dụng; không chạy `kubectl apply`, sửa load balancer, mở firewall hay thử tấn công bypass trên cluster production ngoài change process.

## 2. Ingress API khác Ingress controller như thế nào?

Kubernetes cung cấp một API resource tên **Ingress**, nhưng **Ingress object không tự xử lý packet**. Một thành phần **Ingress controller** theo dõi những resources mà nó quản lý và cấu hình data plane (reverse proxy, cloud gateway, load balancer hoặc hệ thống thích hợp) để thực hiện routing.

| Khái niệm | Vai trò | Không nên nhầm với |
|---|---|---|
| **Ingress** (`networking.k8s.io/v1`) | Khai báo quy tắc HTTP/HTTPS từ host/path đến backend Service | Firewall, WAF hoặc proxy đã chạy |
| **IngressClass** | Chỉ định controller class và cấu hình liên quan theo cơ chế provider | Bảo đảm tự động cô lập tenant |
| **Ingress controller** | Theo dõi API và điều phối data plane xử lý lưu lượng | Kubernetes API server hoặc ứng dụng backend |
| **Ingress data plane** | Proxy/gateway/LB thực sự tiếp nhận request và chuyển tiếp | Luôn là một Pod dùng Nginx; có provider tích hợp cloud LB |
| **Service** | Cung cấp địa chỉ/đường ổn định tới nhóm backend Pods theo selector/Endpoints | NetworkPolicy hoặc authentication |
| **EndpointSlice** | Thông tin endpoints được Service điều hướng tới | Danh sách user được phép truy cập |
| **LoadBalancer Service** | Tích hợp cơ chế LB có external/internal entry point theo controller/cloud | Tự động public trong mọi cluster |
| **NetworkPolicy** | Luật allow L3/L4 do network plugin hỗ trợ và thực thi | HTTP method/path authorization |
| **Gateway API** | API có vai trò/phạm vi route và gateway rõ hơn cho nhiều trường hợp | Đồng nghĩa một implementation cụ thể |

### 2.1. Hai plane cần bảo vệ khác nhau

**Control plane**: người dùng/CI hoặc controller tạo và cập nhật Kubernetes resources, controller xem API, phát hiện thay đổi và cấu hình proxy/LB. **Data plane**: request thật đi từ client tới gateway/Service/Pod.

~~~mermaid
flowchart TD
    DEV["Platform admin / App team / CI"] -->|"Kubernetes API + RBAC"| API["Kubernetes API server"]
    API -->|"Watch Ingress, Service, EndpointSlice, Secret"| CTRL["Ingress controller reconciliation"]
    CTRL -->|"Configure/reconcile"| PROXY["Ingress data plane"]
    USER["Client request"] --> LB["External hoặc internal LB"]
    LB --> PROXY
    PROXY --> SVC["Service / dataplane routing"]
    SVC --> POD["Application Pod"]
~~~

Một người có quyền **sửa Ingress hoặc annotation** có thể thay đổi cách dữ liệu đi qua data plane dù họ không truy cập trực tiếp proxy. Một proxy có thể vận hành đúng nhưng vẫn mất an toàn nếu controller chấp nhận cấu hình không đáng tin, hoặc service account của controller có quyền API quá rộng.

### 2.2. Ingress không phải một API cho mọi giao thức

Kubernetes Ingress chuẩn chủ yếu mô tả **HTTP/HTTPS routing** theo host/path. Cấu hình TCP/UDP tùy ý, TLS passthrough, raw SNI routing hoặc những tính năng L7 nâng cao **không phải lúc nào cũng thuộc Ingress API chuẩn**; nhiều controller cung cấp qua config riêng, CRD hoặc Gateway API.

Đừng bê các annotations của một controller sang controller khác rồi mặc định ngữ nghĩa và bảo mật giữ nguyên. **IngressClass chỉ đưa resource tới controller đã chọn**, còn policy, TLS và network exposure phụ thuộc implementation và môi trường.

## 3. Đường đi request và sáu ranh giới cần kiểm tra

~~~mermaid
flowchart LR
    U["Internet client"] --> CD["CDN / WAF"]
    CD --> LB["Cloud LB"]
    LB --> ING["Ingress controller"]
    ING --> SVC["Kubernetes Service"]
    SVC --> API["API Pod"]
    API --> DB["Data service"]
~~~

Trong mỗi mũi tên, cần đặt câu hỏi: **Ai được gửi request qua ranh giới này? Điểm nhận có xác thực danh tính bên gửi không? Dữ liệu có mã hóa không? Thành phần nào được tin để cung cấp thông tin client, hostname và scheme?**

| Ranh giới | Điểm đầu → điểm cuối | Rủi ro điển hình | Kiểm soát |
|---|---|---|---|
| **TB-1** | Internet → CDN/WAF hoặc public LB | DDoS, request độc hại, hostname giả | Edge policy, WAF, DDoS mitigation, TLS, rate limit |
| **TB-2** | CDN → cloud LB/Ingress | CDN bypass, giả mạo client IP header | Origin allowlist/authentication, CIDR quản lý, XFF normalization |
| **TB-3** | LB → Ingress proxy | Source IP bị SNAT, sai TLS endpoint, trực tiếp vào node | LB policy, firewall, Service type, PROXY protocol trust |
| **TB-4** | Ingress → Service/Pod | HTTP plaintext, route sai tenant, Pod ngoài ý định | TLS upstream khi cần, service routing, NetworkPolicy, backend identity |
| **TB-5** | App Pod → DATA/internal service | Lateral movement, egress quá rộng | Default-deny có allowlist, mTLS, DB auth, least privilege |
| **TB-6** | Kubernetes API → controller config | Cấu hình route độc hại, annotation injection, lộ TLS Secret | RBAC, admission, class/namespace isolation, audit, controller hardening |

**Không có thứ tự tin cậy cố định cho mọi cụm.** Một triển khai có thể bỏ CDN, dùng internal LB, có service mesh sidecar hoặc hoàn toàn dùng controller quản lý cloud gateway ngoài cluster. Khi threat modeling, phải **thay sơ đồ mẫu bằng đường đi thực** rồi xác định từng điểm kết thúc TLS/packet inspection/policy.

### 3.1. Điểm cuối của request mạng không phải điểm cuối nghiệp vụ

Một API Pod nằm trong subnet/Pod CIDR private vẫn có thể xử lý request do người dùng Internet gửi qua Ingress. “Pod không có public IP” không đồng nghĩa “ứng dụng không Internet-facing”. Ngược lại, nếu LB chỉ internal nhưng đang nối VPN/peering, nhiều mạng đối tác vẫn có thể truy cập theo route và chính sách.

Đây là lý do phải kiểm tra cả **reachability** (có đường tới hay không), **authentication** (ai gửi), **authorization** (được phép làm gì) và **confidentiality/integrity** (nội dung được bảo vệ thế nào).

## 4. Vai trò của DNS, SNI, Host, path và Service selection

### 4.1. Một URL trải qua nhiều phép chọn

Giả sử browser gọi:

~~~text
https://api.lab.example.test/v1/orders
~~~

Các thành phần có thể xử lý:

1. **DNS** phân giải hostname thành địa chỉ LB/CDN; CNAME tới một edge không tự đổi danh tính HTTPS mà client mong đợi.
2. **TLS SNI** giúp endpoint đầu tiên chọn cấu hình/chứng thư phù hợp cho `api.lab.example.test` khi được gửi.
3. **Certificate SAN** được client so với hostname dự kiến, cùng chain/validity/key proof.
4. **HTTP Host hoặc HTTP/2 `:authority`** mang danh tính authority để proxy chọn HTTP virtual host.
5. **Path `/v1/orders`** được đối chiếu theo kiểu rule và thứ tự ưu tiên của controller/API.
6. **Backend Service** được Ingress route tới, rồi dataplane chọn một endpoint/Pod hợp lệ.
7. **Ứng dụng** tiếp tục xác thực user, kiểm tra quyền đối với order và ghi audit.

~~~mermaid
flowchart TD
    URL["https://api.lab.example.test/v1/orders"] --> DNS["DNS chọn address"]
    DNS --> TLS["TLS SNI và certificate validation"]
    TLS --> HOST["HTTP Host / :authority"]
    HOST --> PATH["Ingress host + path rules"]
    PATH --> SVC["Service port / backend mapping"]
    SVC --> POD["EndpointSlice → Pod"]
    POD --> AUTH["Application authentication + authorization"]
~~~

### 4.2. Cấu hình sai host/path tạo nhầm ranh giới

| Tình huống | Nguy cơ |
|---|---|
| Rule không khai báo host hoặc dùng wildcard quá rộng | Route các hostname ngoài ý định tới ứng dụng |
| Default backend trả nội dung nhạy cảm | Unknown hostname vẫn có nội dung cần bảo vệ |
| `ImplementationSpecific` path không được kiểm chứng | Kết quả match/regex khác expectation |
| Controller rewrite URL path thiếu kiểm soát | Bỏ qua middleware hoặc tạo route khác với policy API |
| Header `X-Forwarded-Host` không đáng tin | Absolute links, redirects, password reset URLs bị ảnh hưởng |
| CDN và Ingress khác quy tắc URL normalization | WAF kiểm tra một path, backend xử lý một path khác |
| Hai Ingress cùng host/path trên cùng controller | Tranh chấp hoặc precedence phụ thuộc implementation |

Với API Ingress `networking.k8s.io/v1`, `pathType: Exact`, `Prefix`, `ImplementationSpecific` có ngữ nghĩa không hoàn toàn giống nhau. `Prefix` dùng cách match **theo các phần tử đường dẫn** được chuẩn định nghĩa, không nên coi là một regex tùy ý. Annotations rewrite/regex hay thứ tự merge nhiều Ingress là **controller-specific**, phải kiểm thử từng version.

### 4.3. Unknown host cần chính sách rõ ràng

Một edge tốt cần định nghĩa hành vi khi client yêu cầu hostname **không nằm trong allowlist**. Ví dụ trả 404/421 hoặc response an toàn theo policy, không route nhầm vào ứng dụng mặc định chứa trang quản trị. Ingress `defaultBackend` là cơ chế định tuyến dự phòng tùy cấu hình; **nó không tự là deny rule**.

Mọi route công khai cần có owner, môi trường, hostname, backend, TLS/certificate, authentication policy và review. Không dùng tên `internal-api` để biện minh cho một hostname đang được public LB đưa ra Internet.

## 5. TLS termination và sự thật về “HTTPS end-to-end”

TLS xác thực danh tính endpoint và bảo vệ nội dung **giữa những endpoint của từng kết nối TLS**. Trong kiến trúc Ingress, điểm TLS kết thúc có thể là CDN, cloud LB, Ingress proxy, service mesh hoặc chính ứng dụng. Cần hiểu những chế độ thường gặp:

| Mô hình | Đường giao tiếp | Điểm cần kiểm tra |
|---|---|---|
| **TLS termination tại Ingress** | Client ↔ HTTPS Ingress; Ingress → Pod có thể là HTTP | Frontend TLS đúng không tự bảo vệ upstream hop |
| **TLS termination tại CDN/LB** | Client ↔ CDN/LB; LB → Ingress/Pod là một kết nối khác | Cần bảo vệ và xác thực đoạn tiếp theo theo threat model |
| **TLS re-encryption** | Client ↔ TLS edge; Ingress ↔ HTTPS backend | Ingress phải xác minh CA, SAN/hostname và chứng thư backend |
| **TLS passthrough** | Proxy chuyển luồng TLS tới backend mà không giải mã payload ứng dụng ở hop đó | Host/path HTTP routing và WAF L7 tại proxy có thể không hoạt động |
| **mTLS upstream** | Proxy và backend cùng xác thực nhau theo PKI/workload identity | Client cert, trust store, cert rotation, authorization độc lập |

~~~mermaid
flowchart LR
    C["Browser"] <-->|"TLS #1"| EDGE["Edge / CDN"]
    EDGE <-->|"TLS #2 hoặc HTTP"| IG["Ingress"]
    IG <-->|"TLS #3 / mTLS hoặc HTTP"| APP["Application Pod"]
    APP <-->|"TLS #4 nếu chính sách yêu cầu"| DATA["Internal data service"]
~~~

**Mỗi số TLS biểu thị một kênh riêng.** Nếu CDN kết thúc TLS #1, CDN nhìn được HTTP plaintext trước khi tạo TLS #2. Nếu Ingress kết thúc TLS #2, Ingress nhìn được plaintext trước khi chuyển tiếp. Không gắn nhãn “end-to-end encrypted” một cách tuyệt đối khi có các điểm termination đọc được nội dung.

### 5.1. Frontend certificate và SAN

Client yêu cầu `https://api.lab.example.test` phải xác minh chứng thư của **endpoint TLS đang kết nối** đối với hostname đó, gồm **Subject Alternative Name (SAN)** phù hợp, trust chain, thời gian hiệu lực và bằng chứng sở hữu private key trong TLS handshake.

`tls.secretName` trong Ingress thường trỏ tới một Kubernetes Secret loại `kubernetes.io/tls` **cùng namespace với Ingress**. Một Secret đúng kiểu nhưng có cert sai SAN hoặc không được controller chọn đúng cho SNI vẫn gây handshake/certificate verification failure.

Những lỗi thường gặp:

- TLS Secret hết hạn hoặc intermediate chain thiếu.
- SAN certificate không khớp `rules.host` hoặc hostname browser yêu cầu.
- SNI route tới default certificate của controller.
- CDN/Ingress giữ các certificate khác nhau trên hai TLS hops.
- Tự động gia hạn cert thành công trong Secret nhưng proxy chưa cập nhật như kỳ vọng.
- Credential/private key được log, export hoặc cho workload khác đọc qua RBAC quá rộng.

### 5.2. TLS tới backend không được định nghĩa đầy đủ chỉ bằng Ingress API

Ingress object chuẩn mô tả HTTP routing và TLS ở phía nhận, **không bảo đảm backend protocol sẽ là HTTPS** chỉ vì `spec.tls` đã có. Với nhiều controller, một kết nối tới Service backend theo mặc định có thể là **HTTP plaintext**; muốn dùng HTTPS tới origin có thể cần cấu hình/annotation riêng và chứng thư tin cậy.

Thậm chí khi đặt tên Service port là `https`, **không nên suy** controller đã xác minh certificate upstream. Phải xem **kết nối thực tế, cấu hình upstream TLS, CA trust, SNI và hostname validation**. Nếu proxy có tùy chọn bỏ xác minh cert upstream, việc “mã hóa mà không xác thực peer” có thể làm giảm khả năng chống MITM.

### 5.3. TLS passthrough có đánh đổi

TLS passthrough chuyển luồng được mã hóa tới backend mà Ingress proxy không giải mã application payload trong chặng đó. Vì vậy proxy trung gian có thể dựa vào SNI hoặc thông tin handshake còn nhìn thấy, nhưng **không thể áp dụng các rule HTTP method/path/header body như khi đã terminate TLS**.

Đây thường là khả năng **controller-specific**, không phải cứ tạo Ingress với `tls` là nhận passthrough. Nếu yêu cầu WAF, authentication gateway hoặc rate limit dựa URL path, phải xác định **thành phần nào có quyền quan sát plaintext và được phép thực thi chính sách**.

## 6. Nguồn IP client đáng tin: X-Forwarded-For không tự là bằng chứng

Khi đi qua nhiều proxy, Pod thường nhìn thấy socket peer là Ingress proxy, không phải client bên ngoài. Các HTTP forwarding headers thường xuất hiện:

~~~http
X-Forwarded-For: 198.51.100.24, 203.0.113.10
X-Forwarded-Proto: https
X-Forwarded-Host: api.lab.example.test
X-Real-IP: 198.51.100.24
~~~

**Rủi ro chính:** client có thể tự gửi tất cả những header đó. Nếu Ingress hoặc ứng dụng đọc `X-Forwarded-For` phần tử đầu tiên làm nguồn quyết định allowlist/rate limit/admin privilege, attacker có thể **khai IP tùy ý**. Tên header không có chữ ký mật mã và không cho biết giá trị có được proxy đáng tin tạo hay không.

### 6.1. Mô hình chain of trust

~~~text
Client socket peer ở Internet edge: 198.51.100.24
Client tự gửi X-Forwarded-For: 10.9.9.9  (không đáng tin)

CDN edge đáng tin:
  Bỏ hoặc ghi đè XFF client-supplied
  XFF sau edge: 198.51.100.24

LB đáng tin:
  Append CDN socket peer 203.0.113.10
  XFF sau LB: 198.51.100.24, 203.0.113.10

Ingress:
  Socket peer thực: LB internal IP
  XFF: cần xác minh chuỗi hops theo topology

Application:
  Dùng client IP đã được trusted ingress tính toán theo policy;
  không parse bừa XFF từ nguồn không xác minh.
~~~

Một thuật toán phổ biến là **bắt đầu từ socket peer thật**, chỉ xem XFF khi immediate peer nằm trong danh sách trusted proxies, rồi duyệt danh sách **từ phải sang trái** qua các hops tin cậy để tìm **địa chỉ gần nhất ngoài trust boundary**. Nhưng kết quả đúng phụ thuộc vào **hợp đồng mà từng proxy thực hiện** (overwrite hay append, loại header nào là canonical, xử lý IPv6/duplicate headers). Không tự xây parser đơn giản cho production.

### 6.2. Những header khác cũng tạo rủi ro

| Header/cơ chế | Dùng để làm gì? | Nếu tin không đúng nguồn |
|---|---|---|
| `X-Forwarded-For` | Truyền chuỗi IP hops | Giả IP, làm sai rate limit, audit, geo/IP allowlist |
| `X-Real-IP` | Một địa chỉ client IP theo quy ước proxy | Giả địa chỉ nếu không do trusted proxy tạo |
| `X-Forwarded-Proto` | External scheme `http`/`https` | Redirect/cookie/URL security logic hiểu sai |
| `X-Forwarded-Host` | Hostname public mà client yêu cầu | Host poisoning, link reset password/redirect sai |
| `Forwarded` (RFC 7239) | Chuẩn hóa `for`, `by`, `proto`, `host` | Giả mạo tương tự nếu gửi từ client không tin cậy |
| Header CDN riêng | Client IP/geo/identity do CDN cung cấp theo provider | Có thể bị client viết giống nếu origin mở direct path |
| PROXY protocol | Truyền transport peer metadata ngoài HTTP header | Có thể giả metadata nếu listener nhận nguồn không trusted |

**PROXY protocol không tự có xác thực**; cả sender/receiver phải cấu hình đồng bộ và chỉ chấp nhận metadata từ trusted LB/source. Một listener public chấp nhận PROXY preamble từ mọi nơi không chứng minh địa chỉ client là thật.

### 6.3. Quy tắc tại Internet-facing edge

1. **Không tin forwarding headers từ client chưa được xác minh**; ghi đè/sanitization tại edge đầu tiên.
2. Nếu CDN ở phía trước, chỉ tin những IP egress CDN được xác nhận và cập nhật theo provider; hạn chế bypass origin.
3. Chỉ forward một **canonical normalized client IP** với provenance rõ, không để mỗi tầng tính khác.
4. Giới hạn độ dài/số phần tử của XFF và xử lý IPv4/IPv6, duplicate headers bằng thư viện đáng tin.
5. Logging nên lưu **socket peer, verified client IP, ingress ID, request ID** riêng; raw header phải gắn nhãn untrusted.
6. Không sử dụng IP làm yếu tố phân quyền nghiệp vụ duy nhất; NAT/VPN/mobile IP khiến nó không đủ định danh người dùng.

### 6.4. `externalTrafficPolicy: Local` và địa chỉ nguồn

Một số Kubernetes Service type `LoadBalancer` hoặc `NodePort` có thể dùng `externalTrafficPolicy: Local` để **giúp bảo toàn địa chỉ client source IP ở một số đường mạng**, tùy cloud/CNI/LB/host network path. Tuy nhiên, lựa chọn này có thể thay đổi phân phối traffic, health checks, endpoint locality và availability.

**Không bật `Local` chỉ để sửa log XFF** khi chưa kiểm tra topology, traffic imbalance, node không có local endpoints và failover. Cần xác minh **socket source IP thực tế** ở Ingress và hành vi của provider sau NAT, không suy từ một YAML field.

## 7. Public LB, internal LB và đường đi vòng qua Ingress

Một IngressClass có tên `internal` **không đảm bảo LB không public**. Việc tạo một internet-facing hay internal LB thường phụ thuộc **controller configuration, cloud provider settings, subnet annotations và thực tế public/private IP/route/firewall**.

### 7.1. Phân loại exposure cần dựa vào bằng chứng

| Thiết kế | Câu hỏi cần kiểm tra |
|---|---|
| **Internet-facing Ingress** | LB có public/external address? Cổng nào mở? WAF/rate limit/TLS đặt ở đâu? |
| **Internal Ingress** | LB ở private address thực không? Những VPN/peering/on-prem networks nào có route tới? |
| **Multiple ingress controllers** | IngressClass nào được chọn? Cùng host có bị controller khác xử lý không? |
| **Ingress sau CDN** | Origin chỉ cho CDN hoặc nguồn được xác thực hay còn direct path? |
| **Service type LoadBalancer riêng ngoài Ingress** | Có tạo đường public bypass toàn bộ Ingress/WAF không? |
| **NodePort/hostPort/hostNetwork** | Có listener trên node bị cloud firewall lộ ra ngoài không? |
| **Admin/metrics endpoint** | Có được public hoặc gắn chung host với ứng dụng bên ngoài không? |

### 7.2. Direct-to-origin bypass

~~~mermaid
flowchart LR
    USER["Internet client"] --> CDN["CDN / WAF"]
    CDN --> ORIGIN["Origin LB / Ingress"]
    ORIGIN --> API["API Pod"]
    USER -. "Đường trực tiếp nếu origin mở" .-> ORIGIN
~~~

Nếu CDN kiểm tra WAF và chuẩn hóa XFF nhưng origin vẫn nhận mọi Internet source, client có thể truy cập trực tiếp origin (khi biết public address/host) mà không đi qua CDN. Điều này làm suy yếu **lọc request, rate limiting, bot protection và provenance**.

Phòng vệ: firewall/security group/CIDR allowlist hoặc **origin authentication/mTLS** khi hỗ trợ; không chỉ chặn bằng DNS, vì DNS không phải security boundary. Kết hợp test direct-to-origin (trong lab có phép) với kiểm tra **effective cloud LB addresses, routes và ACLs**.

### 7.3. Các đường public khác cũng quan trọng

Ngay cả khi ứng dụng chỉ có Ingress public được phê duyệt, một `Service type: LoadBalancer` mới hoặc `hostPort` trên node có public IP cũng có thể mở **đường vào thay thế**. Review phải bao gồm **tất cả Services, NodePorts, hostNetwork Pods, ingress controllers và cloud security groups**, không chỉ các Ingress resources.

**Không coi `ClusterIP` là firewall.** Pod ở namespace khác có thể gọi ClusterIP nếu route/network policies cho phép. Một internal Service có thể trở thành backend cho một public Ingress mà không cần public IP riêng.

## 8. Ví dụ Ingress manifest: hiểu đúng những gì YAML tuyên bố

Một tài nguyên Ingress HTTP/HTTPS chuẩn có thể được mô tả:

~~~yaml
# MINH HỌA: không apply lên cluster production.
# Service api-svc và Secret api-tls phải thuộc namespace team-app.
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: api-public
  namespace: team-app
  labels:
    app.kubernetes.io/part-of: orders
spec:
  ingressClassName: public-edge
  tls:
    - hosts:
        - api.lab.example.test
      secretName: api-tls
  rules:
    - host: api.lab.example.test
      http:
        paths:
          - path: /v1
            pathType: Prefix
            backend:
              service:
                name: api-svc
                port:
                  number: 8080
~~~

### 8.1. Ý nghĩa từng phần

| Trường | Khẳng định | Không khẳng định |
|---|---|---|
| `ingressClassName: public-edge` | Resource hướng tới IngressClass theo cơ chế controller | Có một public LB đã hoạt động hoặc WAF tự bật |
| `tls.hosts` / `secretName` | Yêu cầu controller dùng TLS theo khả năng tương ứng | Chứng thư hợp lệ, tự động gia hạn, frontend TLS đúng mọi node |
| `rules.host` | Match HTTP hostname theo controller và Ingress API | Client đã được xác thực và có quyền truy cập |
| `path: /v1`, `pathType: Prefix` | Routing theo path prefix | WAF/authorization cho toàn bộ API paths |
| `backend.service.name` | Trỏ tới Service trong namespace theo API Ingress chuẩn | Pod backend đang healthy và đã có NetworkPolicy |
| `port.number: 8080` | Backend Service port mà controller dùng | Ingress→backend có HTTPS hoặc mTLS |

`api-tls` và `api-svc` phải được thiết kế trong **namespace `team-app`** cho Ingress resource này. Mẫu không tự tạo Secret, Service hoặc controller; không thể áp dụng trực tiếp nếu thiếu các thành phần. Đối với controller sử dụng custom annotations, security posture phụ thuộc **phiên bản và cấu hình của controller**, không phải ở những trường API trên.

### 8.2. Một Service backend mang IP private

~~~yaml
# MINH HỌA: Service nội bộ tới các Pod app=api.
apiVersion: v1
kind: Service
metadata:
  name: api-svc
  namespace: team-app
spec:
  type: ClusterIP
  selector:
    app: api
  ports:
    - name: http
      protocol: TCP
      port: 8080
      targetPort: 8080
~~~

Service `ClusterIP` không tự xác thực callers hoặc mã hóa traffic. Nếu API nhạy cảm, cần **network segmentation và application authentication/authorization**. Ingress cho `api.lab.example.test` có thể đưa request từ Internet vào Pod này, dù Service và Pod đều không có public IP.

### 8.3. Bộ kiểm tra tối thiểu cho manifest

Trước khi triển khai, đặt câu hỏi:

1. Hostname này có chủ sở hữu và được phép Internet-facing không?
2. IngressClass `public-edge` trỏ đúng controller và LB chưa?
3. TLS Secret có certificate SAN phù hợp host, chain đúng, private key được bảo vệ và lịch rotation?
4. Có default backend an toàn cho host không khớp và có path ngoài ý định không?
5. Ingress tới backend là HTTP hay HTTPS? Nếu policy yêu cầu TLS, ai xác minh cert upstream?
6. Service endpoints có Pod labels đúng, có healthy backends và đúng targetPort?
7. NetworkPolicy có cho ingress→app đúng port mà vẫn deny các Pod không có quyền?
8. API có authn/authz độc lập, rate limit và structured logging không?

## 9. NetworkPolicy: chỉ cho Ingress controller gọi đúng backend

**Kubernetes NetworkPolicy** đặt giới hạn L3/L4 trên Pod traffic **khi plugin mạng thực sự hỗ trợ/thực thi**. Nó không có nghĩa các container trong cùng Kubernetes namespace tự bị ngăn truy cập nhau. Một Pod backend có thể bị reach trực tiếp qua Pod IP hoặc ClusterIP từ một Pod khác nếu chưa có policy phù hợp.

### 9.1. Bước đầu: default-deny cho namespace ứng dụng

~~~yaml
# Lab example: thay đổi chính sách mạng nếu áp dụng.
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: deny-by-default
  namespace: team-app
spec:
  podSelector: {}
  policyTypes:
    - Ingress
    - Egress
~~~

Policy này cô lập ở cả hai hướng đối với các Pod trong namespace `team-app` **trong phạm vi triển khai NetworkPolicy của CNI**. Không có rule allow nào trong chính policy trên. Nếu áp dụng thật, **DNS, monitoring, ingress và các kết nối tới dependency có thể bị ngắt**; phải có allow rules đúng và rollout canary.

### 9.2. Chỉ cho Ingress controller vào API TCP/8080

~~~yaml
# Lab: selector của namespace và Pod controller là ví dụ.
# Cần xác minh labels thật và nguồn traffic sau NAT/hostNetwork.
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: api-allow-from-ingress
  namespace: team-app
spec:
  podSelector:
    matchLabels:
      app: api
  policyTypes:
    - Ingress
  ingress:
    - from:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: ingress-system
          podSelector:
            matchLabels:
              app: ingress-controller
      ports:
        - protocol: TCP
          port: 8080
~~~

**Hai selector trong cùng một phần tử `from` có nghĩa phải cùng thỏa điều kiện namespace và Pod**. Nếu khai báo `namespaceSelector` và `podSelector` thành hai phần tử list riêng, ngữ nghĩa sẽ là **OR**, có thể mở rộng nguồn được phép đáng kể.

| Cách viết | Ý nghĩa |
|---|---|
| Một phần tử `from` chứa `namespaceSelector` **và** `podSelector` | Chỉ Pods có label phù hợp trong namespaces được chọn |
| Hai phần tử `from`, một chứa `namespaceSelector`, một chứa `podSelector` | Cho phép một tập namespace **hoặc** một tập Pod theo ngữ nghĩa tương ứng |
| Chỉ `podSelector` | Pods được chọn trong cùng namespace với policy |
| Chỉ `namespaceSelector` | Pods ở bất kỳ namespace nào thỏa selector, không bị giới hạn bởi Pod label |

**Kiểm tra plugin:** một số Ingress controllers chạy `hostNetwork`, dùng node-local proxy hoặc cloud LB data plane; source IP/identity mà CNI nhìn thấy ở backend có thể không tương ứng trực tiếp Pod labels của controller. Ví dụ ở trên chỉ phù hợp khi **đường controller Pod → API Pod thực sự được CNI nhận diện và enforce theo selectors**.

### 9.3. Egress từ controller và API cũng phải xét

Nếu namespace chứa Ingress controller bị cô lập egress, cần policy cho **controller → backend**. Nếu app bị cô lập egress, cần cho **API → DB**, DNS, identity services và destinations cần thiết. Một flow giữa hai Pods bị cách ly ở cả hai hướng cần **source egress allow và destination ingress allow**. Ngoài ra, policies ở cloud/host có thể tiếp tục chặn.

**Kubernetes NetworkPolicy chuẩn có allow rules mang tính cộng dồn**; việc tạo nhiều policies chọn cùng Pod không tạo khả năng “một deny rule có ưu tiên cao phủ quyết allow rule” như ACL firewall truyền thống. Với quy tắc L7, FQDN, host endpoints và global tiers, nhiều CNI có CRDs riêng; không coi chúng là API portable.

### 9.4. Không đồng nhất NetworkPolicy và identity

Một Pod mang label `app: ingress-controller` không phải identity mật mã. Nếu tenant có quyền đổi Pod labels hoặc tạo Pods cùng labels trong namespace được tin, cần đánh giá khả năng **mạo danh label** đối với chính sách. Dùng **RBAC, admission, namespace ownership, service account identity, TLS/mTLS và backend authorization** để giảm rủi ro.

## 10. WAF, authentication và authorization đặt ở đâu?

Một Ingress controller có thể hỗ trợ authentication, request size limits, IP filtering hoặc WAF qua extension/controller configuration. Nhưng những tính năng đó **không xuất hiện tự động** chỉ vì có Ingress resource.

### 10.1. Phân định trách nhiệm

| Nơi thực thi | Thường làm gì? | Không thay thế được |
|---|---|---|
| **CDN/WAF** | DDoS mitigation, bot/challenge, rules ở Internet edge | Authentication/authorization sâu theo nghiệp vụ |
| **Ingress controller** | TLS, host/path routing, header normalization, request limits, có thể auth gateway | API RBAC, per-record authorization |
| **API gateway / policy proxy** | Token verification, quotas, API version/schema controls theo thiết kế | Backend nghiệp vụ tự kiểm tra quyền dữ liệu |
| **Service mesh** | Workload mTLS, policy giữa services theo khả năng | HTTP object-level authorization nếu không cấu hình |
| **Application** | Session/token auth, user/role, quyền theo hành động/tài nguyên, CSRF | Firewall hoặc cloud network security |
| **Kubernetes NetworkPolicy** | Pod L3/L4 segmentation | Xác thực user, phân tích HTTP payload |

Ví dụ: request `GET /orders/1234` có token hợp lệ, vượt WAF, đi đúng Ingress, nhưng user không sở hữu order `1234`. **Application phải từ chối**; TLS và NetworkPolicy không chứng minh user có quyền đọc bản ghi đó.

### 10.2. Forward authentication và identity headers

Một số kiến trúc để Ingress gọi một dịch vụ identity trước khi chuyển request, rồi đưa thông tin user vào headers như `X-Authenticated-User`. Đây là **hợp đồng đặc biệt nhạy cảm**:

- Edge phải **xóa header identity do client gửi** trước khi chèn giá trị đã xác thực.
- Backend chỉ tin những header đó từ trusted ingress/mTLS peer; không được có direct Pod/Service bypass.
- Auth service phải **fail closed** theo policy khi không khả dụng, không “bỏ xác thực để giữ uptime”.
- Token/session cần được xác minh đầy đủ: issuer, audience, signature, expiry và scopes theo kiểu token.
- Không log bearer token, cookies hoặc dữ liệu phiên chưa được che.

**Một header `X-User: admin` không phải authentication.** Nếu client tự gửi được header đó trực tiếp hoặc proxy không ghi đè, hệ thống có nguy cơ **identity spoofing**.

### 10.3. Header security và ứng dụng

Ingress có thể thêm những response headers như HSTS và các headers bảo mật trình duyệt khi phù hợp. Nhưng:

- HSTS yêu cầu HTTPS thực tế hoạt động và có ảnh hưởng phạm vi hostname/subdomain.
- CORS là chính sách trình duyệt, không phải server-side authorization.
- `X-Forwarded-Proto` không chứng minh Pod đang trực tiếp dùng HTTPS.
- Các HTTP headers không làm sạch nghiệp vụ khỏi injection/SSRF.
- Một WAF có thể cần giải mã HTTPS mới kiểm tra được body/path đầy đủ.

### 10.4. Rate limit và nguồn khóa

Một API có thể giới hạn theo **verified client IP**, account, API key hoặc tổ hợp tín hiệu. Nếu controller tin leftmost XFF do client khai, limit có thể bị điều khiển bằng spoofed IP. Nếu controller chỉ thấy IP CDN/LB, mọi user có thể bị gộp chung. Cần đồng bộ **source IP policy ở CDN/LB/Ingress/app** và kiểm tra NAT/IPv6.

## 11. Kiểm soát quyền cấu hình Ingress trong môi trường đa tenant

Nhiều teams dùng chung cluster nhưng có **mức tin cậy khác nhau**. Ingress resources không chỉ là YAML: chúng có thể ảnh hưởng routing, TLS certificates, proxy headers, authentication và đôi khi cả cấu hình controller.

### 11.1. Vai trò cần tách

| Vai trò | Quyền cần thiết | Quyền nên hạn chế |
|---|---|---|
| Platform administrator | Quản lý controller deployment, class, RBAC và global config | Không phân phát admin secrets rộng rãi |
| Application owner | Tạo/sửa Ingress cho ứng dụng của mình trong namespace được duyệt | Không sửa controller ConfigMap/class của tenant khác |
| PKI/certificate operator | Cấp, gia hạn và quản lý TLS Secrets đúng phạm vi | Không có quyền đọc tất cả secrets mọi tenant |
| Security reviewer | Đọc policies, route exposure, audit logs | Không cần viết tùy ý mọi resource |
| CI automation | Triển khai những objects cụ thể theo pipeline | Không dùng cluster-admin token chung |
| Ingress controller service account | Watch/reconcile resources cần thiết, cập nhật status theo implementation | Không cấp quyền Kubernetes API ngoài nhu cầu thực tế |

**Namespace RBAC không tự giới hạn hostname** vì hostname là một chuỗi trong spec, không phải một resource có namespace ownership mặc định. Một team có quyền tạo Ingress trong namespace của mình có thể cố khai báo host trùng một tenant khác hoặc cấu hình route wildcard; cần admission/policy và quy trình **hostname ownership**.

### 11.2. Các control bổ sung

1. Dùng **IngressClass rõ ràng**, tránh resource mơ hồ bị một default controller không đúng xử lý.
2. Giới hạn ai được tạo/sửa Ingress trong những namespaces nhạy cảm.
3. Admission policies kiểm soát **hostname allowlist, IngressClass, annotations, backend references và TLS configuration**.
4. Phân tách public/internal controllers và credentials khi yêu cầu trust isolation.
5. Không cho tenants sửa global ConfigMap, admission webhooks, controller Deployment hoặc ServiceAccount.
6. Quản lý TLS Secrets theo namespace và PKI owner; không để controller hoặc tenant đọc secrets ngoài nhu cầu.
7. Audit các thay đổi Ingress, IngressClass, Secret, Service, EndpointSlice và permissions.

### 11.3. Shared controller là một shared failure domain

Một controller hoặc data plane phục vụ nhiều teams có thể bị ảnh hưởng bởi:

- Resource/route conflicts giữa hostnames của tenants;
- Một config lỗi khiến controller reload thất bại;
- DoS từ tenant có lưu lượng đột biến;
- Một annotation extension làm thay đổi proxy behavior ngoài phạm vi ứng dụng;
- Lộ log/headers chứa thông tin user hoặc internal topology;
- Lỗ hổng của controller có phạm vi ảnh hưởng rộng hơn một Pod ứng dụng.

Nếu các tenants có độ tin cậy khác nhau, cân nhắc **controllers tách biệt, namespaces/IngressClasses riêng, quotas, admission và RBAC**, đồng thời kiểm thử rằng isolation thật sự được enforce. Tách controller ở namespace khác chưa đủ nếu nó vẫn quản lý mọi class/host hoặc cùng dùng credential không phân biệt.

## 12. Annotations, template expansion và rủi ro cấu hình động

Annotations giúp các Ingress controllers bật các tính năng bổ sung, ví dụ upstream protocol, path rewrite, canary routing, authentication hoặc request buffering. Nhưng **tên/ý nghĩa annotations là controller-specific** và có thể thay đổi theo phiên bản.

### 12.1. Vì sao annotations có thể nhạy cảm?

Controller có thể chuyển đổi giá trị annotations của Ingress thành cấu hình của reverse proxy. Nếu cho người dùng ít tin cậy điền **các đoạn cấu hình proxy tùy ý**, có thể xảy ra:

- Thay đổi header/authentication, redirect hoặc upstream routing ngoài chính sách.
- Lộ dữ liệu trong request/response hoặc cấu hình proxy.
- Làm ảnh hưởng tenant khác qua shared configuration.
- Tạo cấu hình không hợp lệ khiến proxy reload thất bại.
- Tạo điều kiện khai thác lỗ hổng parsing/configuration của một phiên bản controller cụ thể.

**Không phải mọi annotation đều nguy hiểm như nhau.** Mức rủi ro phụ thuộc **controller, version, admission validation và phạm vi quyền**, nhưng những tính năng cho phép chèn **custom proxy snippets** đặc biệt cần quản trị.

### 12.2. Khuyến nghị kiểm soát

- Mặc định **tắt hoặc giới hạn snippets tùy ý** trong môi trường đa tenant, trừ khi có đánh giá và bảo vệ tương ứng.
- Duy trì **allowlist annotations** theo class/namespace/application owner.
- Dùng admission để từ chối các cấu hình có thể trỏ tới backend/hostname hoặc custom proxy directives ngoài quyền.
- Kiểm soát version controller, cập nhật bản vá và thay đổi theo change window.
- Review config generated/effective ở controller nếu plugin cho phép, không chỉ review Ingress YAML.
- Có canary và rollback khi annotation làm thay đổi request processing.

**Không có một annotation “bật WAF” portable cho tất cả controllers.** Không dùng cấu hình minh họa từ một implementation khác mà chưa xác minh hành vi thực.

### 12.3. Không để pipeline có quyền cao tin dữ liệu chưa review

Một workflow GitOps/CI có quyền tạo Ingress, Secrets hoặc thay controller config là **nguồn thay đổi control plane**. Nếu pipeline tự nhận cấu hình từ pull request của người không có quyền mà không qua review/admission, kẻ đó có thể điều khiển đường vào hoặc tạo resource public. Cần branch protection, least privilege credentials, review policy và audit trail.

## 13. Gateway API: phân chia quyền giữa chủ gateway và chủ route

**Gateway API** là tập APIs Kubernetes với mô hình vai trò rõ hơn cho nhiều trường hợp routing. Nó bao gồm các resource như **GatewayClass**, **Gateway** và **HTTPRoute** trong những profile được hỗ trợ. Không phải cluster nào cũng cài Gateway API CRDs/controller; **Ingress và Gateway API không tự thay thế lẫn nhau khi chỉ đổi tên resource**.

### 13.1. Mô hình phân vai

~~~mermaid
flowchart TB
    ADMIN["Platform team"] --> GC["GatewayClass / controller"]
    ADMIN --> GW["Gateway: listener, TLS, allowedRoutes"]
    APP["Application team"] --> RT["HTTPRoute: host, path, backendRef"]
    GW -->|"Cho phép route attachment theo policy"| RT
    RT --> SVC["Backend Service"]
    INTERNET["Client"] --> LB["Gateway data plane"]
    LB --> SVC
~~~

| Tài nguyên | Chủ thể thường quản lý | Điểm kiểm soát |
|---|---|---|
| **GatewayClass** | Platform/network team | Controller implementation và thông số class |
| **Gateway** | Infra/security team | Listener addresses, ports, TLS và điều kiện attach routes |
| **HTTPRoute** | Application team | Match hostname/path/header, backend references theo API |
| **ReferenceGrant** | Chủ namespace chứa đối tượng được tham chiếu, khi API yêu cầu | Chấp thuận một số tham chiếu qua namespace |

**Không phải mọi Route đều được tự attach tới bất kỳ Gateway nào.** Listener có các điều kiện như `allowedRoutes` cùng API rules; việc được tạo route trong namespace ứng dụng **không mặc nhiên cho phép** route gắn vào public Gateway do team khác sở hữu.

### 13.2. Cross-namespace references: cần hiểu hai loại quyền

1. **HTTPRoute ở namespace A attach tới Gateway ở namespace B**: chịu các điều kiện `allowedRoutes` của listener và quy tắc Gateway API về route attachment; không đơn giản “có Gateway name là được”.
2. **HTTPRoute muốn tham chiếu backend Service ở namespace khác**: trường hợp này thường yêu cầu một **ReferenceGrant** ở namespace chứa backend target theo cơ chế Gateway API.

Không đồng nhất **ReferenceGrant** với toàn bộ cơ chế route attachment, và không nghĩ rằng nó tự thay thế NetworkPolicy. Ngay cả khi HTTPRoute được phép tham chiếu một Service, **data plane vẫn cần kết nối L3/L4 tới backend**, và ứng dụng vẫn cần authentication/authorization.

### 13.3. Tại sao Gateway API hữu ích với trust boundary?

Khi platform team quản lý listener và cho app teams chỉ quản lý route trong phạm vi được cho phép, phạm vi quyền có thể **dễ mô hình hóa và kiểm thử hơn**. Tuy nhiên, **RBAC, admission, class/controller-specific policy và host ownership** vẫn quan trọng; một cấu hình `allowedRoutes` quá rộng hoặc wildcard hostname thiếu kiểm soát vẫn có thể phá ranh giới tenant.

**Không có một sản phẩm Gateway API phổ quát**: trước khi thay Ingress, kiểm tra controller support, feature conformance, CRD version, TLS modes, route matching, extensions và policy attachments được hỗ trợ. Không giả định mọi implementation đều giống nhau khi xử lý redirects, headers hoặc cross-namespace references.

## 14. Bảo vệ Ingress controller như một thành phần có đặc quyền

Ingress controller thường là một **workload hạ tầng** có quyền quan sát Kubernetes resources, nhận traffic từ ngoài và tạo config ảnh hưởng nhiều ứng dụng. Đây là mục tiêu có giá trị cao hơn một application Pod đơn lẻ.

### 14.1. Attack surface ở ba lớp

| Lớp | Ví dụ bề mặt | Kiểm soát |
|---|---|---|
| **Public data plane** | HTTP parser, TLS stack, header logic, request limits | Patch, WAF, fuzz/security tests theo sản phẩm, hardening |
| **Control-plane integration** | Watch API, credentials/service account, annotations, admission | Least-privilege RBAC, audit, admission/validating webhooks |
| **Node/runtime layer** | hostNetwork, hostPort, privileged, filesystem, secrets | Pod security, drop capabilities, root filesystem controls, node isolation |

Không cấp quyền `cluster-admin` cho controller chỉ để tránh các lỗi permissions mà chưa xem RBAC role nó thực sự cần. Nhiều implementations yêu cầu xem Services, EndpointSlices, IngressClasses, Secrets hoặc cập nhật status/events; quyền cụ thể phải theo **tài liệu và manifest version được phê duyệt**.

### 14.2. Một số controls nên có

- Chạy controller bằng **identity/service account chuyên biệt**; tách deployment công khai và nội bộ khi threat model yêu cầu.
- Giới hạn **Secret read access** theo controller scope và những TLS certificates nó phải phục vụ.
- Áp dụng policies để tránh pod privilege/host namespace ngoài nhu cầu implementation.
- Giữ **image/OS/TLS library cập nhật**, pin phiên bản và audit image provenance.
- Kiểm soát dashboard, metrics, status endpoint, admission webhook và health ports: **không public tùy ý**.
- Tách quyền sửa **controller configuration và Ingress annotations** khỏi quyền deploy application thông thường.
- Có resource requests/limits, replicas và availability phù hợp; tránh một cấu hình/route sai gây outage cho toàn bộ tenants.
- Log các thay đổi config và events của controller, không ghi private key/cookie/token.

### 14.3. Admission webhook là một trust boundary khác

Một số controllers có **validating admission webhook** để kiểm tra config khi tạo/sửa resource. Webhook có thể bảo vệ khỏi cấu hình không hợp lệ, nhưng bản thân nó cũng là **dependency của Kubernetes API** theo failure policy và availability.

Phải hiểu:

- Webhook kiểm tra loại resource nào, có thật sự kiểm soát dangerous annotations/host ownership không?
- Ai có quyền sửa `ValidatingWebhookConfiguration` hoặc policy?
- Khi webhook không phản hồi, policy được thiết kế **fail closed hay fail open**, ảnh hưởng availability thế nào?
- Có thông báo/telemetry khi config bị từ chối và quy trình canary/rollback?

Không tin rằng **cứ có admission webhook là đã giải quyết mọi rủi ro Ingress**. Webhook có thể kiểm tra cú pháp nhưng bỏ qua kiểm soát quyền theo hostname hoặc những trường controller-specific chưa được cấu hình.

## 15. Service backend, readiness và đường truy cập bỏ qua gateway

Ingress đến backend thường dựa trên **Service** và những endpoints mà dataplane chọn. Khi một Pod mới được tạo, Pod IP, node và trạng thái readiness có thể thay đổi.

### 15.1. Kiểm tra đúng backend

| Trường | Nếu cấu hình sai | Bằng chứng |
|---|---|---|
| Service `selector` | Chọn Pods không phải ứng dụng dự kiến | Service spec, Pod labels, EndpointSlices |
| Service `port` / `targetPort` | TCP connect refused, 502/504 hoặc đi sai service port | Service + Pod listener + proxy logs |
| Endpoint readiness | Request tới Pod không ready tùy controller behavior | EndpointSlice conditions, Pod readiness |
| Namespace | Backend Service không ở namespace mà Ingress resource yêu cầu | Ingress/service namespace và controller reconciliation |
| `hostNetwork`/node routing | Nguồn kết nối khác Pod identity dự kiến | CNI/host network path |
| Service account/identity | Routing đúng nhưng authorization fail hoặc workload identity sai | mTLS/JWT/DB authentication logs |

**Service name là một tham chiếu routing, không phải bằng chứng identity.** Nếu selector bị thay đổi hoặc service account có quyền sửa endpoints quá rộng, traffic có thể chuyển tới workload khác. Kubernetes RBAC, admission và audit phải bảo vệ quyền **sửa Service, labels, EndpointSlices và backend references**, không chỉ Ingress.

### 15.2. Ingress không ngăn các request đi vòng tới backend

~~~mermaid
flowchart LR
    CLIENT["Internet"] --> LB["Public LB"]
    LB --> IG["Ingress"]
    IG --> SVC["Service"]
    SVC --> API["API Pod"]
    OTHER["Untrusted Pod khác"] -. "Pod IP / ClusterIP direct" .-> SVC
~~~

Nếu Pod không được NetworkPolicy bảo vệ, một Pod khác có thể gọi **ClusterIP/Pod IP trực tiếp** mà không qua Ingress authentication, WAF hay rate limit. Do vậy:

1. API **không được tin các identity headers** chỉ vì “bình thường request luôn qua Ingress”.
2. Chặn đường bypass bằng **NetworkPolicy, cloud/node firewall và mTLS/peer identity** phù hợp.
3. Không cho quyền sửa Service/EndpointSlice/labels vượt quá owner.
4. Nếu API cần kiểm soát user-level, thực thi ngay tại API hoặc bảo đảm một identity layer không thể bị bypass, với bằng chứng cụ thể.

### 15.3. Health và readiness là security concerns

Nếu Ingress gửi request tới một Pod chưa cập nhật policy/security config, hệ thống có thể chạy **hai security postures khác nhau** trong lúc rollout. Readiness probes, config reload và canary cần bảo đảm Pod chỉ nhận traffic khi **TLS, authn/authz và dependencies quan trọng** sẵn sàng.

Ngược lại, health probes thường được exempt một phần authentication nhưng phải bảo đảm **không rò rỉ dữ liệu nhạy cảm hoặc cấp quyền nghiệp vụ**, và không mở một port quản trị cho toàn Internet chỉ để LB health check hoạt động.

## 16. Quan sát trust boundary bằng telemetry thay vì chỉ nhìn YAML

Đối với một request tới `api.lab.example.test`, nên có thể nối các sự kiện:

~~~text
Client -> CDN -> LB -> Ingress -> Service -> Pod -> Data service

Per hop:
  timestamp UTC
  request/trace ID
  socket peer IP and source provenance
  verified client IP (nếu có)
  TLS protocol/termination point
  SNI, HTTP Host/:authority, method/path được xử lý
  Kubernetes namespace, IngressClass, Ingress name
  backend Service, EndpointSlice, Pod UID
  authentication result, authorization decision
  HTTP status, latency, WAF/policy action
~~~

### 16.1. Không coi raw headers là facts

| Dữ liệu log | Nguồn | Cách sử dụng |
|---|---|---|
| `socket_peer_ip` | Peer của kết nối đang quan sát | Truy dấu hop, có thể là LB |
| `verified_client_ip` | Kết quả trusted-proxy algorithm hoặc edge contract | Abuse/rate limit trong phạm vi chính sách |
| `raw_x_forwarded_for` | Header có thể bị client làm giả | Chỉ phân tích, không tự dùng cho allowlist |
| `ingress_name`/`namespace` | Routing resource do controller áp dụng | Xác định owner và config revision |
| `backend_service`/`pod_uid` | Mapping request tới workload | Điều tra sai route, Pod thay đổi |
| `tls_handshake_result` | Log từ TLS endpoint thực | Phân biệt cert errors và HTTP errors |
| `auth_subject`/`policy_action` | Tầng identity và authorization | Phân tích quyền, tránh ghi token |

### 16.2. Chỉ số nên theo dõi

- Tỷ lệ TLS handshake success/failure, certificate expiry, SNI mismatch.
- Số request theo hostname, IngressClass, status 4xx/5xx và latency.
- Thay đổi số lượng **public LoadBalancers, NodePorts và Ingress routes**.
- Sự kiện config bị controller/admission từ chối, reload failures.
- WAF/rate limit blocks và sự khác nhau giữa raw XFF/verified IP.
- Số request tới unknown host/default backend.
- NetworkPolicy deny flows từ Pod không được phép tới API/DATA.
- Controller CPU/memory, request queue, healthy replicas, webhook availability.

**Không thấy log không đồng nghĩa traffic không tồn tại.** CNI có thể xử lý qua eBPF, một phần traffic không qua Ingress hoặc log bị sampling; kết hợp **controller logs, LB logs, CNI flow telemetry, app traces và Kubernetes audit events**.

### 16.3. Quyền riêng tư và dữ liệu nhạy cảm

Không ghi authorization headers, cookies, tokens, private keys hoặc request body chứa dữ liệu nhạy cảm vào access logs. Giới hạn retention, quyền đọc và mục đích sử dụng IP/user identifiers. Nếu cần quan sát HTTP payload ở WAF/Ingress, phải xem điểm TLS termination và chính sách bảo vệ dữ liệu của tổ chức.

## 17. Availability là rủi ro bảo mật vận hành riêng

Ingress là điểm tập trung traffic, nên một sự cố **certificate, admission webhook, controller reload, LB, route hoặc DNS** có thể khiến nhiều ứng dụng không phục vụ được, dù không có kẻ tấn công.

### 17.1. Các failure domains

| Failure domain | Triệu chứng | Hướng giảm thiểu |
|---|---|---|
| CDN/LB outage | Không kết nối được endpoint public | HA/multi-zone, DNS/LB failover theo kiến trúc |
| Controller Pod/node failure | 502/503/timeout, mất capacity | Replicas, anti-affinity/topology spread, health checks |
| Config generation/reload failure | Routes không cập nhật hoặc gateway lỗi | Validation, canary, rollback, audit |
| TLS cert hết hạn/sai SAN | Browser/client TLS errors | PKI rotation, expiry alerts, SNI tests |
| Ingress Service/EndpointSlice thiếu backend | 503/502 hoặc no healthy endpoints | Pod readiness, labels, service discovery |
| Authentication dependency down | 401/403/5xx hoặc auth bypass nếu fail-open sai | Fail-closed policy, HA identity service, test degradation |
| Default-deny thiếu DNS/identity allow | Ingress kết nối backend được nhưng app lỗi | Dependency allowlist và positive/negative tests |
| Public LB source-IP change | Network allowlist sai, verified IP sai | Provider CIDR management, route telemetry |
| Underlay/overlay MTU lỗi | Kết nối nhỏ OK, payload lớn timeout | MTU/PMTUD, CNI/underlay observability |

### 17.2. Tránh “sửa lỗi” bằng cách mở rộng trust

Khi một dịch vụ không truy cập được, **không tự sửa bằng cách bật `hostNetwork`, mở firewall `0.0.0.0/0`, tắt TLS verification, tin mọi XFF, tắt authentication hoặc xóa NetworkPolicy**. Những thay đổi đó có thể làm request hoạt động trở lại nhưng tạo đường vượt qua ranh giới tin cậy.

Quy trình tốt là phân biệt **DNS → TLS → LB → Ingress routing → Service/EndpointSlice → CNI policy → backend application**. Giải quyết đúng nguyên nhân và giữ các negative tests hoạt động sau sửa.

## 18. Lệnh quan sát chỉ đọc cho Ingress và trust boundary

Những ví dụ dưới đây áp dụng trong **cluster/lab có quyền truy cập**. Chúng chủ yếu dùng `kubectl get`, `describe` và một request kiểm tra có giới hạn. Dùng đúng kubecontext, namespace và tên resources. Output có thể chứa IP nội bộ, tên domain, TLS Secret references và đường đi dịch vụ; không đăng lên hệ thống công khai.

### 18.1. Xem cluster context và Ingress classes

~~~bash
# Chỉ xem context đang chọn, tránh quan sát nhầm production cluster.
kubectl config current-context

# Xem IngressClasses và controller identifiers.
kubectl get ingressclasses
kubectl describe ingressclass public-edge

# Inventory Ingress resources và external addresses/status.
kubectl get ingress -A -o wide
~~~

**Cẩn thận:** status `ADDRESS` trong Ingress không luôn phản ánh toàn bộ public exposure. Một controller có thể chạy internal LB, nhiều IP, một hostname cloud LB hoặc chưa cập nhật status. Phải xác minh Service của controller, cloud LB, effective routes và firewall.

### 18.2. Đọc Ingress resource và các rule có hiệu lực theo cấu hình

~~~bash
# Ingress thuộc namespace lab team-app.
kubectl describe ingress api-public -n team-app

# Đọc YAML: kiểm tra host/path, class, TLS secret và annotations.
kubectl get ingress api-public -n team-app -o yaml

# Liệt kê Services cùng namespace, xác minh backend name/port.
kubectl get services -n team-app -o wide
kubectl describe service api-svc -n team-app

# Xem endpoints theo cách Kubernetes hiện đại.
kubectl get endpointslices -n team-app
~~~

Một Ingress YAML hợp lệ **chưa chứng minh controller đã nhận/áp dụng config**. Cần xem controller events/logs, backend health, default host behavior và request thực. Trường `spec.ingressClassName` không tự tạo deployment ingress controller.

### 18.3. Kiểm tra NetworkPolicy, labels và host networking

~~~bash
# NetworkPolicy objects và nguồn/destination Pod labels.
kubectl get networkpolicies -A
kubectl describe networkpolicy api-allow-from-ingress -n team-app
kubectl get pods -n team-app -o wide --show-labels
kubectl get pods -n ingress-system -o wide --show-labels
kubectl get namespaces --show-labels

# Xem spec của controller Pod nếu biết đúng tên.
kubectl get pod INGRESS_POD -n ingress-system \
  -o jsonpath='{.spec.hostNetwork}{"\n"}{.status.podIP}{"\n"}{.spec.nodeName}{"\n"}'
~~~

**NetworkPolicy tồn tại không chứng minh nó được thực thi.** Phải xác nhận CNI hỗ trợ policy, selectors chọn đúng Pods, traffic source identity phù hợp node/hostNetwork semantics và có positive/negative connectivity evidence.

### 18.4. Kiểm tra Service controller và public exposure

~~~bash
# Liệt kê những Services có thể tạo entry points vào cluster.
kubectl get services -A -o wide

# Xem một Service của controller tại namespace lab.
kubectl describe service edge-controller -n ingress-system

# Xem workloads để xác định deployments, replicas và readiness.
kubectl get deployments -n ingress-system
kubectl get pods -n ingress-system -o wide
~~~

Để xác nhận một Service **Internet-facing hay internal**, không chỉ dựa trên `type: LoadBalancer` hoặc tên `internal`. Kiểm tra ingress IP/hostname, cloud LB loại public/private, route, security group/firewall, IPv4/IPv6 và cả những đường NodePort/hostPort.

### 18.5. Kiểm tra TLS certificate mà không xuất private key

~~~bash
# Trên thiết bị lab đã có DNS và CA trust đúng.
# Mở một TLS kết nối thử, xác minh hostname, không dùng -k/--insecure.
openssl s_client \
  -connect api.lab.example.test:443 \
  -servername api.lab.example.test \
  -verify_hostname api.lab.example.test \
  -verify_return_error \
  -brief < /dev/null

# Thử một endpoint lab ở IP đã xác định nhưng giữ SNI/URL hostname.
curl --head --verbose \
  --resolve api.lab.example.test:443:192.0.2.10 \
  --connect-timeout 3 --max-time 10 \
  https://api.lab.example.test/health
~~~

`--resolve` chỉ giúp ép địa chỉ kết nối trong **lab**, không tự bỏ hostname verification. Muốn test CA nội bộ, dùng **CA bundle/trust store đã được duyệt**, không thêm `-k` hoặc cấu hình “skip certificate validation”. Một TLS handshake thành công ở frontend không chứng minh hop Ingress→Pod cũng có TLS.

### 18.6. Negative test về forwarded headers trên môi trường thử

~~~bash
# Chỉ gửi một request kiểm tra tới endpoint lab được phép.
# Mục đích là xác minh edge ghi đè/bỏ qua header giả, không bypass rate limit.
curl --head --verbose \
  --resolve api.lab.example.test:443:192.0.2.10 \
  --header "X-Forwarded-For: 10.9.9.9" \
  --header "X-Forwarded-Proto: http" \
  --header "X-Forwarded-Host: unexpected.lab.example.test" \
  --connect-timeout 3 --max-time 10 \
  https://api.lab.example.test/health
~~~

**Điều cần quan sát:** socket peer ở edge, normalized client IP trong controller/app, hostname/scheme được backend tin, request ID, rate-limit key và response. Không lấy HTTP 200/403 đơn thuần làm bằng chứng: cần xem log ở đúng ingress point và validation policy.

### 18.7. Không xuất TLS Secret khi chỉ kiểm tra routing

`kubectl get secret ... -o yaml` có thể xuất dữ liệu certificate và **private key được mã hóa base64** trong Secret, không nên dùng làm phép kiểm tra mặc định và càng không đưa vào báo cáo. Người vận hành có thể dùng **metadata của Secret, certificate đã phục vụ công khai qua TLS handshake và thông tin PKI inventory được cấp phép** để kiểm tra hostname/expiry mà không lộ khóa riêng.

## 19. Ma trận kiểm thử Ingress controller và trust boundary

Mỗi test cần chỉ rõ **nguồn → đích, giao thức/cổng, hostname, thời gian, TLS endpoint, enforcement point và kết quả kỳ vọng**. Nhóm test bên dưới là thiết kế cho cluster lab; không phải kết quả đã chạy.

| Test ID | Kiểm soát muốn chứng minh | Phép kiểm thử | PASS khi |
|---|---|---|---|
| **EXPO-01** | Public hostname chỉ đưa vào đúng LB | Đối chiếu DNS, LB addresses và ingress rule | Public entry point trùng inventory đã duyệt |
| **EXPO-02** | Internal Ingress không public ngoài thiết kế | Đọc cloud LB/firewall/effective routes | Không có đường Internet direct không phê duyệt |
| **EXPO-03** | Không có đường bypass CDN/WAF | Kiểm tra origin source allowlist và request lab đi vòng | Origin chỉ nhận trusted edge/origin-auth peer |
| **EXPO-04** | NodePort/hostPort/LB riêng không bypass Ingress | Inventory Services, Pod specs và cloud firewall | Không có entry points công khai ngoài allowlist |
| **ROUTE-01** | Host đúng route đúng Service | HTTPS request cho `api.lab.example.test/v1/...` | Controller chọn `team-app/api-svc` đúng port |
| **ROUTE-02** | Unknown host không vào ứng dụng nhạy cảm | Request hostname lab không được đăng ký | Default behavior an toàn theo policy |
| **ROUTE-03** | Path ngoài phạm vi không route nhầm | Request lab với path không match | Không truy cập backend nhạy cảm ngoài rule |
| **ROUTE-04** | Không có host/path conflict giữa tenants | Audit tất cả Ingress cùng controller/class | Host ownership được enforce; conflict bị xử lý đúng |
| **TLS-01** | Frontend TLS identity đúng | OpenSSL/cURL verify SAN, chain, expiry | Client nhận cert hợp lệ cho hostname |
| **TLS-02** | SNI và default cert không gây confusion | Thử host hợp lệ/không hợp lệ trong lab | Không chấp nhận cert/route sai domain |
| **TLS-03** | Upstream TLS có xác thực khi policy yêu cầu | Review proxy upstream config và handshake evidence | Ingress xác minh certificate identity backend |
| **TLS-04** | TLS passthrough không làm mất WAF/authn ngoài ý muốn | Kiểm tra mode thực, TLS endpoints và rule support | Chỉ dùng passthrough khi policy được áp ở điểm phù hợp |
| **XFF-01** | Client không tự khai IP trusted | Gửi một request lab với XFF giả | Verified client IP không đổi theo prefix giả |
| **XFF-02** | Proto/Host headers được chuẩn hóa | Gửi header forwarded sai trong lab | App không tạo redirect/links từ giá trị giả |
| **XFF-03** | PROXY/vendor headers chỉ tin từ LB/CDN | Review peer restrictions và test nguồn lab không tin | Metadata giả từ untrusted peer bị bỏ qua/từ chối |
| **AUTH-01** | Backend có authentication thực | Gửi request không có credential hợp lệ | API không trả dữ liệu nhạy cảm |
| **AUTH-02** | Header identity không thể do client giả | Gửi user header giả qua edge lab | Edge xóa/ghi đè; backend không cấp quyền |
| **AUTH-03** | Auth service failure không mở quyền | Diễn tập dependency failure có kiểm soát | Fail-closed theo policy, log/alert phù hợp |
| **NP-01** | Ingress Pod → API đúng port được phép | Request qua controller với đúng source | Kết nối thành công và đúng backend identity |
| **NP-02** | Pod khác → API không bypass | Test từ Pod chưa được duyệt trong lab | Bị CNI/network policy ngăn theo thiết kế |
| **NP-03** | Controller→backend egress không bị chặn nhầm | Xem source/dest policies và test dương | Luồng cần thiết cho ứng dụng được phép |
| **NP-04** | Frontend→DATA direct bị chặn | Negative test từ Pod không có quyền | Không có lateral path tới DB |
| **RBAC-01** | App owner không sửa controller config | Test quyền `can-i` với identity lab | Không có quyền vượt role |
| **RBAC-02** | Tenant không chiếm hostname của tenant khác | Thử một manifest lab trong admission | Host ownership policy từ chối |
| **ANNO-01** | Dangerous annotations/snippets bị kiểm soát | Admission dry-run/review theo lab | Config ngoài allowlist bị từ chối |
| **SECRET-01** | TLS Secret không bị lộ rộng | RBAC/Secret owner audit, không xuất key | Chỉ identity được duyệt có quyền đọc |
| **GATEWAY-01** | Cross-namespace route attachment được kiểm soát | Xem `allowedRoutes` và ReferenceGrant | Không attach/đi backend ngoài quyền |
| **LOG-01** | Có provenance và trace chuẩn | So CDN/LB/controller/app logs | Peer/verified IP/request ID không bị nhầm |
| **REG-01** | Sau controller/cert upgrade vẫn giữ policy | Lặp positive và negative tests | Không mở route mới hoặc bypass sau rollout |
| **HA-01** | Controller failure/rollout không fail open auth | Canaries, readiness, identity dependency tests | HA/SLO và deny controls giữ đúng |

### 19.1. PASS / FAIL / INCONCLUSIVE

- **PASS:** bằng chứng đủ ở **đúng trust boundary**; ví dụ request hợp lệ đi qua CDN→Ingress→Pod, còn request trực tiếp vào origin bị firewall từ chối; Pod ngoài allowlist bị CNI deny trong khi Pod được phép vẫn kết nối.
- **FAIL:** có đường public hoặc route trái chính sách, spoofed header ảnh hưởng authorization/rate limit, backend không xác thực upstream TLS, hoặc quyền API của tenant vượt phạm vi.
- **INCONCLUSIVE:** không có log hoặc test bị lỗi DNS/certificate/server down; một request timeout không chứng minh NetworkPolicy hoạt động. Khi cần, thêm **positive control** chứng minh endpoint chạy đúng rồi mới đánh giá negative test.

### 19.2. Mẫu test evidence

~~~yaml
test_id: XFF-TRUST-LAB-01
environment: isolated-authorized-cluster
ingress_namespace: team-app
ingress_name: api-public
ingress_class: public-edge
requested_host: api.lab.example.test
path: /health
source: authorized-lab-client
source_supplied_xff: 10.9.9.9
observed_edge_socket_peer: pending
expected:
  frontend_tls_hostname_validation: pass
  forwarded_ip_spoofing_prevented: true
  public_host_allowlist_enforced: true
  origin_direct_bypass: denied
  application_health: success
evidence_required:
  - timestamp-utc-and-request-id
  - lb-and-ingress-peer-data
  - normalized-client-ip-provenance
  - kubernetes-resource-revision
  - app-authorization-and-http-result
result: pending-execution
~~~

Không ghi access token, session cookies, private keys hoặc dữ liệu người dùng nhạy cảm trong test evidence. Trường `result` chỉ đánh dấu **chưa chạy**.

## 20. Case study 1: Tin XFF giả và bỏ qua CDN/WAF

### 20.1. Bối cảnh giả định

Một nhóm triển khai API qua chuỗi:

~~~text
Browser
  -> CDN/WAF
  -> Public cloud load balancer
  -> Ingress controller
  -> api-svc
  -> API Pod
~~~

CDN có rate limit và hệ thống phân tích bot; backend API cũng có rate limit dựa vào IP. Tuy nhiên:

- Public origin load balancer **chưa giới hạn chỉ nhận CDN**.
- Một số lớp proxy tiếp tục chấp nhận XFF do client tự gửi.
- Middleware API sử dụng **leftmost XFF** để lấy IP và quyết định bucket giới hạn.
- Logging ở CDN và ứng dụng lưu các “client IP” khác nhau.

Đây là **kịch bản học tập về sai trust boundary**. Không cần thực hiện hàng loạt request hay vượt rate limit để xác định lỗi; chỉ cần một phép thử có phép và quan sát config/logs.

### 20.2. Bản đồ trust không nhất quán

~~~mermaid
flowchart LR
    U["Untrusted client"] --> CDN["CDN + WAF"]
    CDN --> ORIGIN["Origin LB"]
    ORIGIN --> ING["Ingress"]
    ING --> API["API"]
    U -. "Đường trực tiếp có thể tồn tại nếu origin public" .-> ORIGIN
    U -. "XFF tự khai có thể bị tin nhầm" .-> API
~~~

Ranh giới bị vượt không phải “hàng rào giữa hai IP subnets” đơn thuần, mà là **cam kết rằng chỉ CDN/Ingress được quyền cung cấp dữ liệu client đáng tin và thực thi kiểm soát request trước khi đến API**.

### 20.3. Phân tích từng lớp

| Lớp | Cấu hình sai giả định | Hậu quả |
|---|---|---|
| Cloud LB | Cho mọi Internet source tới origin | Có thể đi vòng ngoài CDN/WAF |
| CDN/Ingress headers | Không thống nhất overwrite/append | Client-supplied XFF tồn tại |
| API middleware | Chọn phần tử đầu tiên của XFF | Dùng IP giả làm rate-limit key |
| Audit | Không giữ socket peer và provenance | Khó xác định đường thật |
| NetworkPolicy | Chỉ cho Ingress→API nhưng không chặn Internet→Ingress | Policy backend không giải quyết CDN bypass |
| Authorization | Có nguy cơ dùng IP làm nguồn cấp quyền | Nếu hệ thống dựa IP alone, rủi ro tăng mạnh |

### 20.4. Hướng xử lý

1. Xác định **public origin addresses** và tất cả entry points, gồm NodePort/LoadBalancer khác.
2. Khóa origin để chỉ **CDN egress đã xác minh** hoặc cơ chế origin authentication/mTLS tương đương được phép.
3. Ở Internet-facing edge, **loại/ghi đè** client-supplied XFF, `Forwarded`, vendor client IP headers và identity headers không tin cậy.
4. Cấu hình Ingress trust-proxy theo **peer thực và CIDR cụ thể**. Không trust `0.0.0.0/0` hoặc toàn bộ RFC1918 chỉ vì có một LB.
5. Backend dùng **verified client IP** từ trusted middleware hoặc policy edge; authentication/authorization dựa identity/tokens/roles chứ không dựa vào XFF.
6. Kiểm tra nguồn IP và request ID giữa CDN, LB, controller, application. Giới hạn log raw header và dữ liệu cá nhân.
7. Thực hiện **positive control** qua CDN và negative control với đường origin trực tiếp trong lab, không tạo traffic vượt ngưỡng.

### 20.5. Kết quả kỳ vọng (chưa chạy)

~~~text
Case: TRUSTED-FORWARDED-IP-LAB

BEFORE (giả định):
  Direct-to-origin: potentially reachable
  Client-provided XFF: 10.9.9.9
  App client IP result: 10.9.9.9
  Rate-limit key: derived from untrusted data
  Security result: FAIL

AFTER (mục tiêu kiểm thử):
  Direct-to-origin from untrusted network: DENY
  CDN -> origin: ALLOW via authenticated path
  Client-provided XFF is ignored/normalized
  Verified client IP: based on approved CDN/LB provenance
  Application authz: independent of client IP header
  CDN and app request IDs: correlated
  Status: PENDING validation
~~~

**Kết luận:** NetworkPolicy chỉ bảo vệ Pod trong phạm vi mà CNI enforce; nó không tự sửa **một origin public nằm ngoài CDN** hoặc một middleware tin XFF giả. Phải bảo vệ **mọi hop của trust chain**.

## 21. Case study 2: Namespace khác nhưng có thể thay đổi Ingress route

### 21.1. Bối cảnh giả định

Cluster dùng một shared Ingress controller với hai tenants:

~~~text
Kubernetes namespace team-payments:
  payments-api
  Ingress host payments.lab.example.test

Kubernetes namespace team-analytics:
  analytics-api
  quyền tạo/sửa Ingress trong namespace của mình

Platform:
  Một controller/class public cho cả hai namespaces
  Chưa có hostname ownership admission policy
~~~

Một pull request từ tenant analytics đề xuất một Ingress dùng **hostname `payments.lab.example.test`** với backend analytics. Tùy controller, có thể xảy ra config conflict, precedence không mong muốn, controller reject hoặc route behavior khác. Không nên khẳng định cụ thể tenant nào “thắng” khi **chưa kiểm tra implementation/version**, nhưng bản thân việc app team khác có thể đề xuất **đụng hostname của tenant payments** là lỗ hổng quản trị trust boundary.

### 21.2. Ranh giới bị thiếu

~~~mermaid
flowchart TD
    PAY["Payments team"] --> PING["Ingress host payments.lab.example.test"]
    ANA["Analytics team"] --> AING["Ingress khai báo host trùng payments"]
    PING --> CTRL["Shared Ingress controller"]
    AING --> CTRL
    CTRL --> ROUTE{"Actual route/config merge theo controller"}
    ROUTE --> PAPP["Payments API"]
    ROUTE --> AAPP["Analytics API"]
~~~

**Kubernetes namespace** giúp tách phạm vi API resources và RBAC, nhưng chuỗi hostname public có thể **đụng nhau giữa các namespaces** trên cùng proxy/controller. RBAC cho phép `create ingress` trong namespace **không tự kiểm soát các hostnames được phép sử dụng**.

### 21.3. Threat model và hậu quả

| Vấn đề | Mối nguy |
|---|---|
| Host ownership không được xác minh | Tenant khai báo tên dịch vụ không thuộc quyền |
| Controller có behavior merge/conflict đặc thù | Có thể làm route sai, reject hoặc outage |
| Wildcard host quá rộng | Một route bao phủ nhiều tên ngoài ý định |
| Cho phép snippets/annotations nguy hiểm | Có thể ảnh hưởng cách proxy xử lý traffic hoặc config |
| TLS Secret được dùng sai | Certificate mismatch, route không đúng identity |
| Controller có quyền API rộng | Nếu controller bị chiếm, phạm vi tác động nhiều tenants |
| Không có admission/audit | Khó phát hiện thay đổi routing bất thường |

Không phải mọi host conflict đều dẫn đến lộ dữ liệu; **tác động thực tế phải dựa trên config effective, request routing và app logs**.

### 21.4. Thiết kế phòng vệ

1. Gắn **hostname ownership** với team/namespace hoặc chính sách platform được phê duyệt.
2. Dùng **IngressClass/controller riêng** cho nhóm có mức tin cậy khác nhau khi cần.
3. Admission chặn hostname ngoài allowlist, wildcard không cần thiết, snippets/annotations ngoài quyền.
4. Giới hạn RBAC: app team không sửa global controller config, TLS Secrets khác namespace hoặc IngressClass chung.
5. Với Gateway API, dùng **listener `allowedRoutes` và ReferenceGrant đúng chỗ** để giới hạn attachment/cross-namespace backend references.
6. Kiểm tra duplicate host/path conflicts trong CI và audit mọi Ingress effective routes.
7. Canary/negative tests: tenant A không thể tiếp quản hostname của tenant B, dù có quyền deploy ứng dụng.

### 21.5. Mẫu kết quả cần đạt

~~~text
Case: TENANT-HOST-OWNERSHIP-LAB

Tenant team-payments:
  Allowed public hostname: payments.lab.example.test
  Ingress class: payments-public
  Backend: payments-api

Tenant team-analytics:
  Allowed public hostname: analytics.lab.example.test
  Attempt to claim payments.lab.example.test: DENY by policy
  Request to change shared controller config: DENY by RBAC
  Dangerous proxy snippets: DENY unless specifically approved

Traffic:
  payments host -> payments backend: PASS
  analytics host -> analytics backend: PASS
  unknown host -> safe default route: PASS

Status: PROPOSED; not executed
~~~

**Bài học:** trust boundary của Ingress còn nằm ở **quyền ai có thể khai báo routes cho hostname nào**, không chỉ ở các kết nối TCP từ Internet vào cluster.

## 22. Troubleshooting Ingress theo từng lớp

### 22.1. Bảng biểu hiện và giả thuyết

| Triệu chứng | Nguyên nhân có thể | Kiểm tra |
|---|---|---|
| DNS hostname không resolve | DNS records/zone/split-view sai | Query DNS từ đúng client, Ingress status |
| TCP tới public LB timeout | Route, cloud firewall/SG, LB listener hoặc node paths | Effective LB exposure, source IP, ACL |
| TLS hostname mismatch | Sai SAN, SNI map tới default cert, Secret sai | OpenSSL verify hostname, Secret metadata, controller logs |
| TLS handshake OK nhưng HTTP 404 | Host/path không match hoặc default backend | Ingress rules, pathType, Host, URL |
| Một path trả backend của tenant khác | Duplicate host/path, annotation rewrite, default route | Audit all Ingress/controller configuration |
| HTTP 502/503 | Không có healthy endpoints, service port sai, upstream connection lỗi | EndpointSlice, readiness, Service, proxy logs |
| HTTP 504 hoặc timeout sau Ingress | NetworkPolicy/route/firewall deny, app quá tải, timeout | CNI flows, Pod listener, upstream metrics |
| Service/Pod gọi trực tiếp được nhưng Ingress lỗi | Host/path/TLS/controller riêng | So URL host và request headers |
| Ingress hoạt động nhưng app URL trả HTTP redirect | X-Forwarded-Proto/public base URL không chuẩn | TLS termination, trusted headers, redirect logic |
| Password reset link chứa host khác | Host/X-Forwarded-Host chưa allowlist | Host ownership, URL generation, proxy sanitizer |
| Client IP log chỉ là IP LB | SNAT hoặc trust proxy chưa đúng | Socket peer, LB mode, trusted CIDRs |
| Client IP log là IP attacker tự khai | App/controller đọc raw XFF | Edge overwrite, parser/trusted chain |
| Client nội bộ vào được backend bỏ qua auth gateway | ClusterIP/Pod IP bypass, NetworkPolicy thiếu | CNI policies, backend authentication |
| Policy có nhưng luồng không bị chặn | CNI không hỗ trợ/enforce, selector sai, hostNetwork | Pod labels, source/destination, CNI capability |
| Auth service down nhưng API vẫn trả dữ liệu | Fail-open auth hoặc direct backend bypass | Auth proxy config, app authn, internal paths |
| Controller config không cập nhật | Watch/RBAC/admission fail, reload error | Controller reconciliation logs/events |
| Sau cert rotation một vài requests lỗi | Nhiều edge nodes có cert khác, cache/reload | SNI từng node, serial/expiry và logs |
| IPv4 hoạt động nhưng IPv6 sai | AAAA/LB/SG/routes và policies v6 khác | Dual-stack networking và cert |
| Lớn payload mới lỗi | Body limits, proxy buffering, MTU/PMTUD | Proxy settings, CNI/underlay, HTTP logs |
| Service type LB mới xuất hiện ngoài ý định | CI/RBAC/admission bỏ sót resource | Service inventory và cloud audit |
| Webhook ngắt mọi Ingress deployments | Admission webhook unavailable, failurePolicy | Webhook events/logs/HA, rollback |
| WAF không thấy HTTP body | TLS passthrough hoặc TLS kết thúc ở nơi khác | Data plane mode, TLS termination |

### 22.2. Trình tự điều tra không phá vỡ chính sách

1. **Xác định request:** URL, method, hostname, path, port, DNS resolver, thời gian UTC, request/trace ID.
2. **DNS:** hostname được resolve tới CDN/LB nào? Client có dùng IPv6?
3. **Transport/TLS:** TCP/QUIC reachability, SNI, certificate chain/SAN, điểm TLS kết thúc.
4. **Cloud LB:** listener, public/internal exposure, firewall, source IP/NAT, health.
5. **Ingress controller:** IngressClass, resource spec, admission, annotations, default backend, config effective.
6. **Service/EndpointSlice:** đúng namespace, backend port, Pod labels, healthy endpoints.
7. **CNI/network:** NetworkPolicy, source/dest Pods, node/hostNetwork, ingress/egress và return route.
8. **Application:** listener, authentication, authorization, HTTP status, dependency.
9. **Logging:** so socket peer với verified client IP, CDN/proxy/app logs, config revisions.
10. **Regression:** sau sửa, kiểm tra lại cả request được phép và request bị cấm.

### 22.3. Cách đọc lỗi kết nối đúng

**Timeout** có thể do firewall drop, missing route, backend quá tải hoặc PMTUD; không mặc định là “NetworkPolicy đã chặn đúng”. **Connection refused** có thể do listener không chạy hoặc proxy từ chối chủ động. **HTTP 401/403** là phản hồi authorization/authentication trong một hop, không chứng minh host/path routing hoặc network segmentation hoàn hảo. **HTTP 502/503/504** có thể xuất phát từ proxy/Service/backend, cần xem chi tiết nơi sinh mã lỗi.

Muốn chứng minh **DENY** do NetworkPolicy, cần **positive control** từ một nguồn được phép tới cùng service đang hoạt động và evidence policy enforcement. Không dùng việc DB bị tắt để đánh dấu “Internet→DB bị deny PASS”.

## 23. Runbook triển khai hoặc thay đổi Ingress có kiểm soát

### Bước 1 — Phân loại exposure và owner

Với mỗi host:

~~~text
Hostname: api.lab.example.test
Application owner: team-app
Traffic scope: public Internet hoặc internal VPN
IngressClass/controller: public-edge
Front TLS endpoint: Ingress / CDN / LB theo topology
Backend Service: team-app/api-svc:8080
Authentication: OAuth/OIDC/session và API authz theo design
Trusted upstream proxies: danh sách cụ thể đã xác minh
Data classification: internal / confidential / public
Dependencies: DB, DNS, identity provider, cloud API
~~~

Phải xác định **ai được công khai hostname**, vùng mạng nào được phép kết nối, endpoint nào terminate TLS và người sở hữu certificate/Secret. Một tài nguyên không có domain hoặc chưa có DNS công khai vẫn có thể tiếp nhận request bằng public IP và `Host` tự khai; cần kiểm tra cloud exposure.

### Bước 2 — Vẽ sơ đồ trust boundaries thật

Liệt kê CDN, WAF, LB, Ingress, proxy/service mesh, Service, Pod, DB và Kubernetes API. Với mỗi hop:

1. IP/hostname, port, giao thức và route.
2. Ai quản trị điểm gửi và điểm nhận.
3. TLS/mTLS, CA/trust stores và điểm thấy plaintext.
4. Forwarded headers nào được tạo/ghi đè và từ socket peer nào.
5. Chỗ enforce network allowlist, WAF, authentication và authorization.
6. Logs, trace ID và failure mode.

Nếu có **hai đường vào** (public CDN và internal VPN), vẽ hai đường riêng; đừng mặc định chúng có cùng source hop count hoặc cùng chính sách XFF.

### Bước 3 — Bảo vệ control plane trước khi cho team deploy

- Tách **public/internal IngressClasses** theo nhu cầu, xác nhận controller thực tế.
- Gắn ownership cho host/path và xét wildcard.
- Giới hạn RBAC tạo/sửa Ingress, Secrets và global config.
- Admission kiểm tra annotation allowlist, backend ownership, public exposure và việc chọn class.
- Phê duyệt quyền **cross-namespace references** (Gateway API nếu dùng).
- Bảo vệ service account controller và validating webhook.
- Lưu config bằng IaC/GitOps có review, audit và rollback.

### Bước 4 — Thiết kế data plane

- Chỉ cho public traffic vào những LB/listeners/hostnames cần thiết.
- Origin phía sau CDN **chỉ nhận những nguồn đã xác thực/được duyệt**.
- Chọn TLS termination và upstream TLS/mTLS nếu policy yêu cầu; xác minh certificate/backend identity.
- Chuẩn hóa `Host`, `X-Forwarded-Host`, `X-Forwarded-Proto`, XFF hoặc `Forwarded` tại **đúng trusted edge**.
- Giới hạn body size, request timeouts, headers và rate limits theo nhu cầu mà không làm mất availability hợp lý.
- Dùng **NetworkPolicy** hạn chế Ingress→backend, backend→DB và egress; xem CNI support.
- Không cho backend tin “mọi request đến từ proxy” nếu có đường ClusterIP/Pod IP bỏ qua.

### Bước 5 — Canary và negative tests

Trong môi trường test/đợt triển khai có phép:

- **Positive:** hostname/SAN đúng; route API đúng; frontend TLS và upstream TLS đúng; ứng dụng xác thực/đáp ứng hợp lệ; DNS/backends khỏe.
- **Negative:** unknown host, path ngoài scope, wrong cert, user chưa đăng nhập, XFF/Proto/Host giả, Pod ngoài namespace không có quyền, direct origin.
- **Control plane:** tenant khác không tạo được route cùng hostname; annotations nguy hiểm bị policy từ chối.
- **Resilience:** cert rotation, failover của controller/LB, identity provider degradation giữ fail-closed.

**Quan sát cả ứng dụng và chính sách bị chặn**; chỉ có “route trả 200” không chứng minh security boundary đúng.

### Bước 6 — Rollout và rollback

~~~mermaid
flowchart TD
    A["Inventory + host ownership"] --> B["Map trust boundaries"]
    B --> C["RBAC/admission/NetworkPolicy/TLS design"]
    C --> D["Lab: positive & negative tests"]
    D --> E{"Security controls và app SLO đạt?"}
    E -- "Không" --> F["Sửa thiết kế / cấu hình"]
    F --> D
    E -- "Có" --> G["Canary một host/namespace"]
    G --> H["Theo dõi TLS, errors, route, CNI denies"]
    H --> I{"Có regression/bypass?"}
    I -- "Có" --> J["Rollback có kiểm soát"]
    J --> F
    I -- "Không" --> K["Rollout + audit + periodic tests"]
~~~

Mỗi thay đổi nên có **người phê duyệt, scope IngressClass/hostname, expected route changes, thời gian UTC, metrics, positive/negative test evidence, cấu hình trước/sau và rollback plan**. Khi sửa một shared controller, đánh giá ảnh hưởng **tất cả tenants** do nó phục vụ, không chỉ ứng dụng gửi pull request.

### Bước 7 — Hậu kiểm và drift detection

Theo dõi:

- Ingress/HTTPRoute mới, hostnames/wildcards trùng hoặc ngoài owner.
- Service `LoadBalancer`, `NodePort`, `hostPort`, `hostNetwork` mới.
- TLS Secrets sắp hết hạn, SAN không đúng, controller reload errors.
- Thay đổi cloud LB public/internal exposure và CDN trusted CIDRs.
- NetworkPolicy selectors/labels thay đổi, CNI enforcement regressions.
- Tăng lượng 4xx/5xx/unknown-host, WAF bypass, traffic từ source lạ.
- RBAC/admission changes và Secret access events.

Không chờ sự cố mới kiểm tra: **định kỳ thử các negative paths** và so trạng thái thực (effective config/routing/policies) với cấu hình mong muốn.

## 24. Bài tập tự kiểm tra và vận dụng

### Bài 1 — Ingress object và controller

Một admin tạo Ingress YAML hợp lệ nhưng cluster chưa cài Ingress controller phù hợp. Có thể kết luận dịch vụ sẽ nhận HTTPS từ Internet không?

*Đáp án gợi ý:* không. Ingress là resource khai báo; cần controller/data plane/LB/TLS/routing thực tế và backend healthy.

### Bài 2 — Private Pod nhưng public API

Pod ở `10.244.1.20`, Service `ClusterIP`, nhưng Ingress public route tới Pod. Ứng dụng có Internet-facing không?

*Gợi ý:* có thể có **public entry point qua Ingress**, dù Pod không có public IP. Cần kiểm tra external LB, authentication, authz, WAF và NetworkPolicy.

### Bài 3 — TLS ở frontend

Browser xác minh HTTPS của Ingress thành công. Ingress tới backend qua HTTP. Có thể nói mọi hop đều encrypted không?

*Đáp án:* không. TLS ở client→Ingress chỉ bảo vệ hop đó; muốn bảo vệ Ingress→backend cần TLS/mTLS hoặc cơ chế phù hợp riêng.

### Bài 4 — TLS passthrough

Một team bật TLS passthrough để backend tự giữ private key; WAF tại Ingress vẫn cần kiểm tra HTTP body. Điều gì mâu thuẫn?

*Gợi ý:* Ingress không giải mã payload khi passthrough nên không thể đọc HTTP body ở điểm đó. Phải đặt WAF tại điểm có plaintext hoặc thiết kế lại TLS termination theo yêu cầu.

### Bài 5 — XFF do client gửi

Client tự gửi `X-Forwarded-For: 10.9.9.9`; ứng dụng dùng phần tử đầu tiên làm IP allowlist. Rủi ro là gì?

*Đáp án:* IP có thể bị khai giả. Cần trusted immediate peer, edge normalization, parser có provenance và application authentication/authorization độc lập.

### Bài 6 — Chọn proxy trust CIDR

Một Ingress được đặt sau CDN và LB. Có nên cấu hình trusted proxies là `0.0.0.0/0` cho tiện không?

*Đáp án:* không. Chỉ tin những source proxies cụ thể đã được chứng minh qua socket peer và network enforcement, xử lý update CIDR và đường bypass.

### Bài 7 — X-Forwarded-Host

Password reset email của ứng dụng sau Ingress chứa domain ngoài allowlist. Những thành phần nào cần kiểm tra?

*Gợi ý:* `Host`, `X-Forwarded-Host`, trusted proxy policy, public base URL, host allowlist và URL generator. Không dùng header chưa xác thực để tạo link/token nhạy cảm.

### Bài 8 — NetworkPolicy backend

Namespace app có default-deny ingress và rule chỉ cho Ingress controller Pod vào API TCP/8080. Một Pod cùng namespace nhưng khác label được kết nối không?

*Gợi ý:* không theo network policy nêu trên, nếu CNI enforce, không có policy khác cho phép và Pod thật sự đi qua đường được mô hình hóa. NetworkPolicy chuẩn có allow rules cộng dồn; xem toàn bộ policies và host paths.

### Bài 9 — Selector `AND` và `OR`

Điều gì khác nhau khi khai báo `namespaceSelector` và `podSelector` trong **cùng** một phần tử `from` so với hai phần tử `from` riêng?

*Đáp án:* cùng phần tử là **AND** trên namespace và Pod; hai phần tử là **OR**, có thể cho phép tập nguồn rộng hơn.

### Bài 10 — IngressClass `internal`

Một IngressClass có tên `internal`, nhưng Service controller có external public LB address. Có thể tin hostname là nội bộ không?

*Đáp án:* không. Kiểm tra loại LB thực, public IP, cloud routes, firewall, DNS và các kết nối VPN/peering; tên class không tạo private network boundary.

### Bài 11 — Tenant chiếm hostname

Tenant A được tạo Ingress trong namespace A và khai `host` thuộc tenant B. Kubernetes RBAC theo namespace có tự ngăn không?

*Gợi ý:* không nhất thiết. Cần hostname ownership/admission và giới hạn IngressClass/controller; kiểm tra thực tế behavior conflict.

### Bài 12 — Gateway API

HTTPRoute trong namespace A muốn tham chiếu backend Service ở namespace B, khác với việc attach route A tới Gateway B thế nào?

*Gợi ý:* cross-namespace **backend reference** thường cần ReferenceGrant ở namespace đích; route attachment tới Gateway phụ thuộc listener `allowedRoutes` và Gateway API rules. Cả hai chưa thay thế NetworkPolicy.

### Bài 13 — Auth bypass qua ClusterIP

Ingress dùng external authentication, nhưng Pod khác có thể gọi API ClusterIP trực tiếp và API không kiểm tra identity. Vấn đề nằm ở đâu?

*Đáp án:* đường trực tiếp bỏ qua auth gateway. Cần NetworkPolicy/mTLS/service identity và authorization tại API hoặc một enforcement layer không thể bị bypass.

### Bài 14 — Upstream TLS

Ingress được cấu hình proxy tới `https://api-backend` nhưng bỏ certificate verification. Vì sao vẫn có vấn đề?

*Gợi ý:* kênh có mã hóa nhưng peer identity không được xác thực đúng, làm tăng rủi ro MITM. Cần CA/trust store, SNI/hostname và certificate validation phù hợp.

### Bài 15 — Controller Secret RBAC

Một shared controller có quyền đọc toàn bộ Secrets cluster, trong khi chỉ quản lý vài TLS hosts. Có thể cải thiện gì?

*Gợi ý:* đánh giá quyền cần thiết theo controller scope, namespace isolation, ServiceAccount least privilege, Secret ownership, audit access và controller separation khi cần.

### Bài 16 — Chẩn đoán 503

Ứng dụng trả HTTP 503 qua Ingress. Có nên mở ingress NetworkPolicy toàn cluster để thử ngay không?

*Đáp án:* không. Kiểm tra controller logs, Service port, EndpointSlice readiness, upstream route, source/destination policy và app health; dùng positive/negative controls rồi sửa đúng điểm.

### Bài 17 — SNI và HTTP Host

DNS trỏ tới đúng cloud LB, nhưng TLS trả certificate default cho host khác, trong khi API Pod vẫn chạy. Các bước cần điều tra?

*Gợi ý:* IngressClass/controller route, SNI virtual host, TLS Secret cùng namespace, SAN/expiry/chain và config reload. Không bỏ xác minh cert.

### Bài 18 — Thiết kế tổng hợp

Thiết kế một kiến trúc có **CDN public, Ingress controller, frontend/API Pods, DATA**, trong đó chỉ CDN truy cập origin, chỉ Ingress gọi API và chỉ API gọi DATA. Hãy nêu **ba luồng ALLOW, bốn luồng DENY**, nơi kiểm soát và một test âm tính cho mỗi trust boundary.

*Gợi ý:* ALLOW Internet→CDN HTTPS, CDN→origin qua authenticated path, Ingress→API; API→DATA là một ALLOW bổ sung. DENY Internet→origin direct, unrelated Pod→API, frontend→DATA, unauthenticated user→sensitive order. Kiểm tra identity, TLS, NetworkPolicy, cloud firewall, authz, log provenance và HA.

## 25. Checklist bảo vệ Ingress controller và trust boundary

### 25.1. Định tuyến và public exposure

- [ ] Có inventory **mọi public/internal Ingress, IngressClass, Gateway, Service LoadBalancer, NodePort, hostPort và hostNetwork**.
- [ ] Với mỗi hostname, ghi rõ **owner, namespace, môi trường, LB, controller, frontend TLS endpoint và backend Service**.
- [ ] Kiểm tra public/internal exposure dựa trên **cloud LB addresses, routes, IPv4/IPv6 và firewall**, không chỉ tên IngressClass.
- [ ] Unknown host và unmatched paths được xử lý an toàn; không route nhầm đến dashboard/admin hoặc tenant khác.
- [ ] Không có host/path conflicts không được phê duyệt, wildcard quá rộng hoặc default backend lộ nội dung.
- [ ] Direct-to-origin đi vòng CDN/WAF bị ngăn bằng **network allowlist hoặc origin authentication**.
- [ ] Không có Service hoặc node listener khác âm thầm public cùng backend ngoài entry point được duyệt.

### 25.2. TLS, header và identity

- [ ] Certificate frontend có **SAN/hostname, chain, validity và SNI routing** đúng trên các nodes/vùng.
- [ ] Đã biết từng **TLS termination point và hop HTTP plaintext**; backend TLS được xác minh khi chính sách yêu cầu.
- [ ] Không bật **skip certificate verification** để xử lý lỗi backend TLS.
- [ ] TLS passthrough chỉ dùng khi WAF/authentication/policy được thực thi ở vị trí có visibility thích hợp.
- [ ] `X-Forwarded-For`, `Forwarded`, vendor IP headers chỉ được tin **sau khi xác minh immediate peer và trust chain**.
- [ ] `X-Forwarded-Proto`, `X-Forwarded-Host`, `Host` và scheme/public base URL được chuẩn hóa, allowlist.
- [ ] Origin không chấp nhận identity headers như `X-User` nếu không đến từ trusted authenticator/ingress.
- [ ] Authentication và **per-resource authorization** được thực thi ở lớp ứng dụng hoặc một enforcement layer không có đường bypass.
- [ ] Verified client IP có **provenance**; không dùng raw XFF làm căn cứ duy nhất cho admin allowlist hay rate limit.

### 25.3. Kubernetes control plane và data plane

- [ ] Controller ServiceAccount có **least-privilege RBAC**, không phải cluster-admin theo thói quen.
- [ ] App teams chỉ có quyền tạo/sửa Ingress/HTTPRoute **trong phạm vi được duyệt**, có host ownership policy.
- [ ] Dangerous annotations, proxy snippets và global config có **admission validation/review**.
- [ ] TLS Secrets có owner rõ, chỉ được đọc bởi identities cần thiết; không xuất private key qua log/ticket.
- [ ] Controller runtime được harden: cập nhật image/library, giảm capabilities, hạn chế privileged/hostNetwork khi có thể.
- [ ] Metrics/admin/status/admission endpoints không public ngoài chủ đích.
- [ ] Ingress→API và API→DATA chỉ được phép qua **NetworkPolicy/CNI và cloud firewalls**, có kiểm thử Pod direct bypass.
- [ ] Đã xem đúng **service selectors, ports, EndpointSlices, source egress và destination ingress**.
- [ ] Với Gateway API, `allowedRoutes`, ReferenceGrant và backend references được kiểm soát đúng quyền.

### 25.4. Kiểm thử và vận hành

- [ ] Có **positive controls** cho traffic hợp lệ, backend healthy, DNS, TLS và identity dependencies.
- [ ] Có negative tests cho **origin direct access, wrong host/path, XFF giả, Host/Proto poisoning, Pod khác namespace, tenant host ownership và unauthenticated requests**.
- [ ] IPv6/CDN failover/multi-zone routes duy trì cùng security posture với IPv4/primary path.
- [ ] Đã xác định auth dependency **fail closed** và controller availability/rollback theo SLO.
- [ ] Có telemetry **request ID, socket peer, verified client IP, hostname/path, Ingress revision, backend Pod UID và policy decision**.
- [ ] Logs không tiết lộ credentials, session cookies, authorization tokens, private keys hoặc nội dung nhạy cảm ngoài quyền.
- [ ] Rollout có canary, version pinning, admission checks, config diff, audit, alert và rollback.
- [ ] Các thay đổi CDN/LB/controller/CNI/cert/Gateway API đều kéo theo **kiểm thử hồi quy allow/deny**.

**Kết luận:** ranh giới tin cậy của Ingress nằm ở **hai phía của cùng một hệ thống**. Phía data plane là đường request qua CDN/LB, TLS, headers, controller, Service và Pod. Phía control plane là **quyền ai được tạo route, dùng hostname, tham chiếu Secret/backend và thay đổi controller config**. Muốn có kiến trúc mạng Kubernetes an toàn, cần bảo vệ **cả đường đi lẫn quyền định nghĩa đường đi**, xác thực kênh và danh tính tại đúng điểm, giữ NetworkPolicy/authorization chống đường bypass và chứng minh mỗi ranh giới qua kiểm thử dương/âm có bằng chứng.

### Tài liệu tham khảo

- [Kubernetes Documentation — Ingress](https://kubernetes.io/docs/concepts/services-networking/ingress/): Ingress API, host/path routing và TLS.
- [Kubernetes Documentation — Ingress Controllers](https://kubernetes.io/docs/concepts/services-networking/ingress-controllers/): các mô hình controller và triển khai.
- [Kubernetes Documentation — IngressClass](https://kubernetes.io/docs/concepts/services-networking/ingress/#ingress-class): liên hệ Ingress resources với controller.
- [Kubernetes Documentation — Services](https://kubernetes.io/docs/concepts/services-networking/service/): ClusterIP, NodePort, LoadBalancer và endpoints.
- [Kubernetes Documentation — Network Policies](https://kubernetes.io/docs/concepts/services-networking/network-policies/): cách ly hướng ingress/egress và semantics selectors.
- [Kubernetes Documentation — EndpointSlices](https://kubernetes.io/docs/concepts/services-networking/endpoint-slices/): quản lý các endpoints cho Service.
- [Kubernetes Documentation — Role-Based Access Control](https://kubernetes.io/docs/reference/access-authn-authz/rbac/): quyền đọc/ghi resources trong control plane.
- [Kubernetes Documentation — Admission Controllers](https://kubernetes.io/docs/reference/access-authn-authz/admission-controllers/): kiểm tra/kiểm soát thay đổi resources.
- [Kubernetes Gateway API — Concepts](https://gateway-api.sigs.k8s.io/concepts/api-overview/): GatewayClass, Gateway, routes và phân quyền.
- [Kubernetes Gateway API — ReferenceGrant](https://gateway-api.sigs.k8s.io/api-types/referencegrant/): kiểm soát một số references qua namespaces.
- [RFC 7239 — Forwarded HTTP Extension](https://www.rfc-editor.org/rfc/rfc7239): `Forwarded` và các hạn chế tin cậy của thông tin proxy.
- [RFC 8446 — TLS 1.3](https://www.rfc-editor.org/rfc/rfc8446): xác thực kênh, handshake và record protection.
- [RFC 9525 — Service Identity in TLS](https://www.rfc-editor.org/rfc/rfc9525): xác minh hostname/danh tính dịch vụ TLS.
- [OWASP — Kubernetes Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Kubernetes_Security_Cheat_Sheet.html): thực hành phân quyền và hạn chế bề mặt tấn công.
- [OWASP — HTTP Headers Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/HTTP_Headers_Cheat_Sheet.html): kiểm soát HTTP headers liên quan bảo mật.
- [OWASP — Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): cấu trúc log và xử lý dữ liệu untrusted.
- [NIST SP 800-190 — Application Container Security Guide](https://csrc.nist.gov/pubs/sp/800/190/final): các rủi ro container platform và workload.
- [NIST SP 800-207 — Zero Trust Architecture](https://csrc.nist.gov/pubs/sp/800/207/final): xác thực và kiểm soát theo trust boundary.







