# TLS termination và TLS passthrough trong reverse proxy và load balancing

**TLS termination** là cách một thành phần trung gian, chẳng hạn **reverse proxy, API gateway, ingress gateway, CDN hoặc load balancer**, trở thành **đầu cuối TLS** của kết nối từ client: nó thực hiện TLS handshake, trình chứng chỉ, xác minh các điều kiện cần thiết, giải mã traffic trên chính đầu cuối đó và có thể đọc/xử lý dữ liệu lớp ứng dụng trước khi chuyển tiếp. **TLS passthrough** là cách một thành phần trung gian chuyển tiếp lưu lượng TLS mà **không kết thúc phiên TLS của client**, thường dựa trên khả năng xử lý TCP/UDP tầng vận chuyển hoặc đọc hạn chế metadata handshake khi còn quan sát được.

Hai cách tổ chức này khác nhau căn bản về **ai sở hữu khóa TLS, nơi nào dữ liệu tồn tại dưới dạng plaintext, nơi áp được chính sách HTTP/WAF, cách xác thực máy chủ và client, cách bảo vệ chặng tới backend và trách nhiệm vận hành chứng chỉ**. Khái niệm thứ ba đặc biệt quan trọng là **TLS re-encryption (TLS bridging)**: proxy kết thúc một phiên TLS từ client **rồi tạo một phiên TLS độc lập** tới backend. Mô hình này không phải passthrough, dù trên sơ đồ mọi chặng đều được vẽ với chữ HTTPS.

Bài thuộc chương **Proxy reverse proxy và cân bằng tải** của module **SECURITY_NETWORK_SECURITY**. Trong kiến trúc mạng an toàn gồm phân đoạn mạng, firewall, VPN, IDS/IPS, xác thực kết nối, bảo vệ DNS, Wi-Fi và hạ tầng cloud, lựa chọn chế độ TLS tại proxy quyết định nơi đặt WAF, nơi xác minh mTLS, nơi lưu khóa, mức khả dụng của giám sát và điểm thực thi chính sách. Bài học tập trung vào **thiết kế, quan sát, kiểm chứng và vận hành an toàn**, không chỉ vào một tùy chọn cấu hình.

> **Quy ước:** các miền dạng **api.example.test**, **orders.example.test** và **internal.example.test** chỉ dành cho ví dụ. Dải **192.0.2.0/24, 198.51.100.0/24 và 203.0.113.0/24** là TEST-NET dùng trong tài liệu. Địa chỉ **10.20.0.0/16** là ví dụ mạng riêng của lab. Không dùng chứng chỉ/key minh họa trong production và chỉ chạy thử trên hệ thống được cấp quyền.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Giải thích ranh giới của **TLS termination, L4 TLS passthrough, TLS offloading, TLS re-encryption/TLS bridging** và sự khác biệt giữa **proxy layer 4** với **proxy layer 7**.
2. Xác định **ai trình server certificate, ai biết private key, bên nào xác thực TLS peer**, và nơi xuất hiện plaintext trong từng mô hình.
3. Phân tích **SNI, ALPN, ClientHello, TLS 1.3, HTTP/2, gRPC, WebSocket, HTTP/3/QUIC và ECH** trong quyết định route.
4. Thiết kế **backend TLS verification, hostname/SAN validation, client mTLS identity và cơ chế truyền identity qua proxy** mà không mở lỗ hổng header spoofing.
5. Phân biệt **client IP gốc**, địa chỉ NAT/source IP, **X-Forwarded-For, Forwarded** và **PROXY protocol** với phạm vi tin cậy.
6. Chọn chiến lược **load balancing, health check, connection draining, session affinity, failover** phù hợp tầng L4/L7 và loại giao thức.
7. Xác định nơi có thể triển khai **WAF, rate limiting theo HTTP, IDS/IPS, logging, DDoS controls** và nơi bị giới hạn vì traffic vẫn mã hóa.
8. Xây dựng **certificate/key lifecycle, rotation, secret isolation, observability, test allow/deny và quy trình ứng cứu**.
9. Đọc các cấu hình minh họa có phạm vi rõ ràng, thử TLS trên localhost và phân tích sự cố **502/503/504, SNI/ALPN mismatch, client IP sai hoặc lỗi certificate**.

## 2. Nền tảng: proxy, load balancer và TLS ở các tầng

### 2.1. Điểm bắt đầu là một kết nối, không phải một URL

Một client muốn truy cập **https://api.example.test/** thường phải:

1. Giải tên **api.example.test** thành địa chỉ có thể kết nối được, theo DNS thực tế của client.
2. Chọn đường qua mạng, firewall và NAT phù hợp để tạo kết nối transport: thông thường **TCP/443** cho HTTPS qua HTTP/1.1 hoặc HTTP/2; **UDP/443** cho HTTP/3/QUIC nếu được hỗ trợ.
3. Thiết lập TLS/QUIC security handshake tới **đầu cuối mà client tin là api.example.test**; client kiểm tra certificate/hostname/trust policy.
4. Gửi HTTP request sau khi đủ điều kiện giao thức và chính sách bảo mật.
5. Nhận kết quả ứng dụng từ một backend mà nó có thể **không biết địa chỉ thực** vì đi qua proxy.

Ở mỗi chặng, **hostname logic của dịch vụ** không nhất thiết bằng địa chỉ IP của backend. DNS có thể trỏ vào virtual IP (VIP) của load balancer, còn proxy chọn backend dựa vào SNI/Host/path, health hoặc thuật toán phân phối tải.

### 2.2. Layer 4 và Layer 7

| Đặc điểm | L4 load balancing / transport proxy | L7 HTTP reverse proxy |
| --- | --- | --- |
| Đối tượng xử lý | Connection/flow TCP, UDP, IP/port, và có thể metadata handshake | HTTP request/response, header, method, path, host, status |
| Có phải giải mã TLS để cân bằng tải không? | **Không nhất thiết**; có thể passthrough | **Có**, nếu quyết định dựa trên nội dung HTTP trong TLS |
| Route dựa trên | Source/destination IP, port, connection hash; SNI khi sản phẩm đọc được ClientHello | Host/path/header/cookie, JWT/identity context khi được cấu hình |
| WAF kiểm tra body | Không, nếu traffic TLS vẫn mã hóa tại đây | Có thể tại điểm termination, tùy công nghệ và kích thước/định dạng body |
| Chứng chỉ client nhìn thấy | Backend nếu passthrough end-to-end | Proxy/edge nếu termination |
| Giữ source IP | Tùy kiến trúc NAT/DSR/TProxy hoặc PROXY protocol | Thường cần trusted forwarding headers hoặc cơ chế khác |
| Health check | TCP handshake, TLS handshake có cấu hình, hoặc giám sát bên ngoài | Có thể kiểm tra HTTP status/path/body và readiness |
| Giao thức phù hợp | Nhiều protocol trên TCP/UDP, kể cả không phải HTTP | HTTP/1.1, HTTP/2, gRPC, WebSocket theo khả năng proxy |
| Logging | Flow/session và một số TLS metadata | HTTP status, request ID, route, latency và security rule |

**L4 không đồng nghĩa mọi proxy L4 hoàn toàn không đọc byte đầu luồng.** Một TCP proxy passthrough có thể quan sát **TLS ClientHello** để tìm SNI/ALPN rồi route, miễn là phần cần đọc còn hiện rõ và sản phẩm hỗ trợ. Nó vẫn **không giải mã HTTP content** nếu không kết thúc TLS.

### 2.3. Ba mô hình thường gặp

~~~mermaid
flowchart TB
  subgraph T["A. TLS termination, backend HTTP"]
    C1["Client"] -->|"TLS A (HTTPS)"| P1["L7 proxy / WAF\nKết thúc TLS A"]
    P1 -->|"HTTP plaintext\ntrong vùng được kiểm soát"| B1["Backend"]
  end
  subgraph R["B. TLS re-encryption / bridging"]
    C2["Client"] -->|"TLS A"| P2["L7 proxy / WAF\nKết thúc TLS A"]
    P2 -->|"TLS B (độc lập)"| B2["Backend TLS server"]
  end
  subgraph S["C. TLS passthrough"]
    C3["Client"] -->|"TLS một mạch"| P3["L4 load balancer\nKhông kết thúc TLS"]
    P3 -->|"TLS bytes/flow"| B3["Backend\nKết thúc TLS"]
  end
~~~

**Cả ba mô hình có thể dùng TCP/443 phía client.** Tên cổng, từ "HTTPS" trên dashboard và một biểu tượng ổ khóa **không tiết lộ đủ** client TLS kết thúc ở đâu hoặc hop phía sau có mã hóa không. Cần đối chiếu cấu hình, certificate, đường kết nối và log của từng endpoint.

### 2.4. Proxy ngược và proxy xuôi

**Reverse proxy** đứng ở phía dịch vụ, nhận kết nối thay mặt một hoặc nhiều backend rồi chọn nơi xử lý. **Forward proxy** thường đứng ở phía client, kiểm soát truy cập ra bên ngoài. Cả hai có thể xử lý TLS theo cách riêng; tuy nhiên khi bàn về **TLS termination vs passthrough** trong bài này, trọng tâm là **reverse proxy / load balancer**.

Với forward proxy, **HTTP CONNECT** có thể tạo đường tunnel tới server ngoài; nếu forward proxy thực hiện TLS interception có kiểm soát, nó phải được client tin cậy theo quy trình PKI và chính sách tổ chức. Đó là một thiết kế khác với việc reverse proxy chủ động trình server certificate cho domain dịch vụ do mình quản lý.

### 2.5. Cái gọi là “end-to-end encryption” phụ thuộc điểm cuối

Nếu **client → proxy** được mã hóa nhưng **proxy → backend** chạy HTTP plaintext, dữ liệu được bảo vệ trên mạng công cộng tới proxy, **không được mã hóa trên chặng sau proxy**. Nếu **proxy → backend** cũng có TLS, dữ liệu được mã hóa trên cả hai chặng **nhưng có một điểm trung gian được phép thấy plaintext**: chính proxy.

Chỉ trong mô hình **passthrough đúng nghĩa**, TLS application data của client tới backend mới không bị proxy kết thúc/đọc. Ngay cả khi đó, proxy/đường mạng có thể thấy metadata IP/port, timing, kích thước và một số thông tin bắt tay chưa được bảo vệ; đồng thời backend phải trực tiếp quản lý certificate, mTLS, HTTP security và ứng dụng.

Không nên dùng câu “mã hóa end-to-end hoàn toàn” cho **TLS bridging** nếu đang muốn nhấn mạnh **proxy không đọc được dữ liệu**. Thuật ngữ chính xác hơn là **mã hóa trên từng chặng (hop-by-hop TLS)**.

## 3. TLS termination ở reverse proxy

### 3.1. Ai đóng vai trò TLS server?

Khi client kết nối tới API qua L7 proxy:

- **Proxy** thực hiện handshake như một **TLS server** đối với client, trình certificate tương ứng với hostname/SNI, sở hữu hoặc được cấp quyền sử dụng server private key (hoặc key service/HSM).
- **Client xác minh certificate của proxy** và tin rằng nó đang kết nối tới đúng hostname dịch vụ.
- Sau handshake, proxy có thể **giải mã HTTP**, áp WAF/rate limiting, bổ sung request IDs, routing theo path và tạo kết nối mới đến backend.
- **Backend** có thể nhận HTTP rõ hoặc một **TLS session riêng** nếu triển khai re-encryption; backend không mặc nhiên xem trực tiếp certificate client đã gửi cho proxy.

~~~mermaid
sequenceDiagram
    participant C as Browser / API client
    participant P as Reverse proxy / TLS edge
    participant W as WAF / L7 policy
    participant B as Backend
    C->>P: TCP connect + TLS ClientHello (SNI)
    P-->>C: Certificate + TLS handshake
    C->>P: HTTP request bảo vệ trong TLS A
    P->>W: Request đã giải mã
    W-->>P: Allow / deny / transform theo policy
    alt Request được cho phép
        P->>B: HTTP hoặc TLS B mới, theo thiết kế
        B-->>P: Application response
        P-->>C: TLS A encrypted response
    else Bị chặn
        P-->>C: Response bị chặn qua TLS A
    end
~~~

**Proxy có thể là trust boundary và security enforcement point**, không chỉ là thiết bị tối ưu hiệu năng. Việc cho WAF xem plaintext là một quyết định kiến trúc: bảo vệ ứng dụng tốt hơn tại edge, nhưng cũng làm **tăng tác động khi proxy hoặc key quản trị bị chiếm quyền**.

### 3.2. TLS offloading khác TLS termination như thế nào?

Thuật ngữ **SSL/TLS offloading** thường dùng khi proxy/LB kết thúc TLS và chuyển HTTP/plaintext vào mạng backend để giảm tải mã hóa ở origin. **TLS termination** là khái niệm rộng hơn: TLS kết thúc ở proxy, bất kể chặng tới origin sau đó là HTTP hay TLS mới.

Vì vậy:

- **Offloading cổ điển:** client TLS → proxy → HTTP backend.
- **Termination + re-encryption:** client TLS → proxy → TLS backend.
- **Passthrough:** client TLS xuyên qua proxy → backend termination.

Không thể suy từ tên “SSL offload enabled” trong cấu hình cũ rằng mọi hệ thống đang dùng plaintext phía backend: cần kiểm tra **backend protocol** và nơi chấm dứt TLS trong triển khai thực.

### 3.3. Những chức năng L7 đạt được khi termination

| Chức năng | Vì sao termination hữu ích | Cần cảnh giác |
| --- | --- | --- |
| Route theo **Host/path/header** | Proxy đọc request HTTP | Header Host/authority có thể do client cung cấp; phải kiểm soát vhost/default route |
| **WAF / API security** | Có thể phân tích method, URI, header, body | Payload cần chuẩn hóa, giới hạn kích thước, không thể bảo vệ mọi lỗ hổng logic |
| HTTP **rate limiting** | Định mức theo route, identity, API key hoặc source đã xác minh | X-Forwarded-For spoofing hoặc NAT khiến chính sách sai người |
| **Authentication gateway** | Kiểm tra JWT/session hoặc tích hợp identity provider | Không thay authorization chi tiết tại backend |
| CORS, HSTS, cookie security, redirect | Có thể áp chính sách HTTP tập trung | Cấu hình sai có thể tạo redirect loop hoặc lộ cookie |
| Observability chi tiết | Log HTTP response codes, routes, request IDs, latency | Không log raw token, cookie, mật khẩu và dữ liệu cá nhân không cần |
| Content caching / compression | Tối ưu theo HTTP response | Phải tuân theo Cache-Control, Vary và bảo vệ dữ liệu theo user |
| Protocol translation | HTTP/2 phía client, HTTP/1.1 hoặc gRPC h2 tới backend | Kiểm tra semantics streaming, timeout, trailer và Connection headers |

**Termination không tự đảm bảo an toàn:** proxy có thể xử lý HTTP nhưng vẫn route sai, tin header giả mạo, không xác thực origin, hoặc bỏ qua giới hạn upload/timeout.

### 3.4. TLS termination tập trung và private keys

Một điểm termination tập trung có thể đơn giản hóa quản lý certificate so với hàng trăm backend. Tuy nhiên, nó cũng tập trung **rủi ro key compromise**:

1. Chỉ những tiến trình/nodes cần thiết có quyền sử dụng private key tương ứng.
2. Dùng secret manager/HSM/KMS hoặc dịch vụ chứng chỉ được quản lý khi hỗ trợ, có **IAM và audit**.
3. Không đính kèm private key vào repository, image container, application log hoặc ticket troubleshooting.
4. Có kế hoạch rotation/renewal, rollback và phát hiện certificate sắp hết hạn.
5. Tách certificate/key theo hostname/tenant/environment cần cô lập; không dùng cùng key cho mọi dịch vụ nếu không có lý do và risk review.
6. Bảo vệ quản trị proxy bằng RBAC/MFA, mạng quản trị riêng và giới hạn thay đổi cấu hình.

### 3.5. Backend dùng plaintext: khi nào là lựa chọn có điều kiện?

Một số hệ thống legacy hoạt động trong vùng mạng được kiểm soát và chọn HTTP phía backend. Điều này tạo **đường plaintext** giữa proxy và ứng dụng; việc cho phép phải dựa vào **mô hình đe dọa, tính nhạy cảm của dữ liệu, mạng/host trust, yêu cầu compliance và quyền truy cập hạ tầng**.

Ngay cả trong mạng VPC private, việc có IP RFC1918 **không có nghĩa mọi workload đều đáng tin**. Nếu có lateral movement, node bị xâm nhập, hạ tầng dùng chung, packet capture hoặc quản trị viên có quyền quá rộng, plaintext trên chặng backend có thể bị lộ. Khi dữ liệu nhạy cảm, multi-tenant hoặc zero-trust yêu cầu **xác thực từng hop**, ưu tiên TLS re-encryption/mTLS theo khả năng.

## 4. TLS passthrough ở tầng vận chuyển

### 4.1. Đường đi “không chạm vào” TLS session của client

Trong **passthrough**, L4 proxy/load balancer xử lý kết nối và chuyển bytes tới backend. **Backend** là TLS server: trình certificate, sở hữu private key và quyết định cipher, mTLS, ALPN cũng như chính sách của kết nối đó. Client phải kiểm tra **certificate của backend**, dù địa chỉ TCP nó kết nối ban đầu có thể là VIP của load balancer.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant L as L4 load balancer
    participant B as Backend TLS server
    C->>L: TCP connect tới VIP:443
    L->>B: Kết nối/forward TCP flow
    C->>L: TLS ClientHello
    L->>B: Chuyển tiếp ClientHello bytes
    B-->>L: ServerHello + Certificate + handshake
    L-->>C: Chuyển tiếp TLS handshake
    C->>L: TLS application data đã mã hóa
    L->>B: Chuyển tiếp ciphertext, không đọc HTTP
    B-->>C: TLS application response qua L4
~~~

Sơ đồ minh họa **TCP proxy passthrough**. Một L4 load balancer còn có thể triển khai bằng NAT/DSR hoặc forwarding khác, do đó chi tiết source IP và connection tracking sẽ khác nhau; ý chính là **L4 không giải mã ứng dụng TLS**.

### 4.2. Passthrough vẫn có thể quan sát metadata

Với TLS qua TCP, một số L4 proxy có thể đọc phần **ClientHello chưa mã hóa** để route theo **SNI** hoặc các extension như **ALPN** theo khả năng sản phẩm. Nhưng:

- **SNI là hostname client khai**, không phải bằng chứng đã xác thực.
- **ALPN client chào** là các protocol ứng viên; proxy passthrough không luôn biết **protocol cuối cùng được hai đầu TLS chọn** nếu nó không giải mã handshake TLS 1.3.
- **ECH (Encrypted ClientHello)** có thể che SNI thật/những extension trong ClientHelloInner; proxy dựa vào SNI ngoài (ClientHelloOuter) có thể **không thấy hostname ứng dụng thực**.
- **Không thể route theo HTTP path/query/header** nếu HTTP đang mã hóa và proxy không terminate TLS.
- Không thể đọc một raw HTTP body hoặc token để áp WAF ở điểm passthrough.

**SNI-based passthrough routing** là lựa chọn hữu ích nếu backend tự xử lý TLS, nhưng cần có **default backend/unknown-SNI policy** và kiểm tra tương thích ECH/TLS 1.3.

### 4.3. L4 passthrough không bảo đảm giữ nguyên client source IP

Một TCP proxy thường tạo **một kết nối downstream khác** hoặc thực hiện NAT, khiến backend nhìn thấy **source IP của proxy/LB**. Một số L4 load balancer hỗ trợ preservation/DSR/TProxy hoặc gửi **PROXY protocol header**, nhưng không thể suy điều đó chỉ từ chữ “passthrough”.

Phải kiểm tra ở mỗi sản phẩm:

- Source IP trên socket/backend thật sự là gì?
- Có SNAT hay traffic asymmetric không?
- PROXY protocol v1/v2 được bật từ đúng peer có tin cậy không?
- Backend có parser PROXY header tương ứng **trước TLS** không?
- Firewall/ACL, flow logs và rate limits áp theo IP nào?

**Một TCP passthrough LB có thể không đổi byte TLS nhưng vẫn thay IP/port của TCP connection hoặc tham gia transport proxying.** “TLS passthrough” không đồng nghĩa “IP passthrough”.

### 4.4. Những trường hợp passthrough có lợi thế

- Backend cần **trực tiếp xác thực client certificate bằng mTLS**, không muốn tin một header thay thế.
- Ứng dụng dùng giao thức **TCP-over-TLS không phải HTTP** (database, messaging protocol, custom binary protocol) và proxy L7 không hiểu protocol.
- Yêu cầu **backend sở hữu TLS session và private key**, edge không được phép thấy plaintext.
- Có backend được quản trị riêng, certificate/ALPN/profile riêng theo dịch vụ.
- Muốn giảm phạm vi plaintext tại shared edge hoặc hạn chế khả năng inspection tại reverse proxy.

Đánh đổi là **quản lý chứng chỉ và TLS policy trên backend**, giảm khả năng WAF/L7 logging/routing tại LB, và khó phân loại lỗi ứng dụng nếu chỉ có transport health checks.

### 4.5. Passthrough không phải “an toàn hơn tuyệt đối”

Nếu backend certificate hết hạn, private key lộ, thiết bị không vá lỗi, dịch vụ nhận mật khẩu yếu, hoặc backend được công bố trực tiếp ngoài Internet, passthrough không tự giải quyết. **Không đặt toàn bộ trách nhiệm TLS lên backend mà bỏ qua vận hành certificate và network controls.**

Với gRPC hoặc WebSocket, passthrough cho phép backend hiểu protocol trực tiếp; nhưng điều đó không có nghĩa L4 load balancer có thể phân phối từng gRPC request/WebSocket message giữa các backend. **Đơn vị phân phối thường là cả connection**, có thể rất lâu và gây mất cân bằng tải theo số request thực.

## 5. TLS re-encryption / TLS bridging: mã hóa hai chặng, hai lần xác thực

### 5.1. Hai phiên TLS độc lập

TLS bridging kết hợp **L7 termination** với **TLS tới backend**:

~~~mermaid
sequenceDiagram
    participant C as Client
    participant P as TLS proxy / WAF
    participant B as Backend TLS server
    Note over C,P: TLS A: client xác minh certificate của proxy
    C->>P: TLS ClientHello / handshake A
    P-->>C: Certificate của api.example.test
    C->>P: HTTP request mã hóa trong TLS A
    Note over P: Giải mã và áp WAF/L7 policy
    Note over P,B: TLS B: proxy là TLS client, backend là TLS server
    P->>B: TLS ClientHello B với SNI phù hợp
    B-->>P: Backend certificate / handshake B
    Note over P: Xác minh CA, SAN, hostname, policy của backend
    P->>B: HTTP request mã hóa trong TLS B
    B-->>P: Response mã hóa trong TLS B
    P-->>C: Response mã hóa trong TLS A
~~~

Trên chặng A, **client xác thực proxy**. Trên chặng B, **proxy phải xác thực backend**. Nếu backend yêu cầu mTLS, backend còn xác thực client certificate **của proxy trên chặng B**, không tự nhìn thấy certificate của client gốc ở chặng A. Hai TLS sessions **không chia sẻ cùng traffic secrets, sequence numbers hoặc resumption tickets** chỉ vì cùng một request HTTP đi qua chúng.

### 5.2. Cấu hình đúng TLS B là điều kiện bắt buộc

Các kiểm soát quan trọng cho proxy khi **đóng vai TLS client**:

1. **Bật kiểm tra server certificate**, không dùng chế độ “insecure” hoặc bỏ verify chỉ vì backend dùng IP private.
2. **Xác định tên backend cần xác minh** trong Subject Alternative Name (SAN), cùng **SNI** dùng khi handshake B; chúng có thể khác public hostname nhưng phải được quản trị rõ.
3. Chỉ tin **CA/trust roots được chấp thuận** cho backend; cân nhắc PKI nội bộ thay vì tin mọi CA hoặc mọi self-signed certificate.
4. Kiểm tra certificate expiry, rotation, key usage/extended key usage và chính sách định danh máy chủ mà TLS stack hỗ trợ.
5. Đảm bảo **backend IP/port** và **tuyến mạng** thực sự được phê duyệt; hostname verification không thay route/firewall.
6. Định nghĩa **ALPN và protocol** giữa proxy–backend: HTTP/1.1, HTTP/2 hoặc gRPC, không đoán từ giao thức phía client.
7. Nếu dùng **mTLS trên chặng B**, quản lý certificate riêng của proxy và CA tin cậy tại backend; cấp quyền theo service identity.
8. Khi proxy chọn lại backend, phải xác thực **từng peer mới**, không chấp nhận certificate của backend A như bằng chứng cho backend B nếu danh tính khác.

**Chỉ bật TLS mà không kiểm tra backend certificate có thể chống nghe lén thụ động trong một số tình huống nhưng vẫn cho phép kết nối với peer không đáng tin**, làm hỏng mục tiêu xác thực đầu cuối. Nhiều reverse proxy yêu cầu tùy chọn **verify server** riêng cho upstream; không giả định cấu hình HTTPS upstream tự bật mọi kiểm tra cần thiết.

### 5.3. SNI, Host và tên certificate ở hai chặng

Một request có thể có nhiều tên hợp lệ với vai trò khác nhau:

~~~text
Client URL:          https://api.example.test/v1/orders
Client TLS SNI:      api.example.test
HTTP Host/authority: api.example.test
Proxy upstream IP:   10.20.10.11
Proxy TLS B SNI:     orders.internal.example.test
Backend cert SAN:    orders.internal.example.test
Backend HTTP Host:   api.example.test hoặc một giá trị được thiết kế
~~~

**Không bắt buộc upstream SNI bằng public Host**, nhưng phải nhất quán giữa mục đích định tuyến, backend certificate và kiểm soát ứng dụng. Đặt Host và SNI bừa bãi chỉ để “certificate hết lỗi” có thể làm request tới virtual host hoặc tenant không dự kiến.

Đặc biệt lưu ý:

- HTTP/2 dùng **:authority pseudo-header** thay cho cách biểu diễn Host của HTTP/1.1; proxy phải chuẩn hóa đúng semantics.
- **SNI không xác thực user**, chỉ là thông tin hostname được client đề nghị khi bắt tay.
- **HTTP Host/authority do client gửi** có thể bị giả; cần chặn unknown hosts, không dùng nó một mình để chọn backend quản trị.
- Nếu proxy upstream dùng địa chỉ IP nhưng backend certificate chỉ chứa DNS SAN, phải chọn hostname validation đúng thay vì tắt verify.
- Nếu một backend có nhiều virtual hosts, **SNI của TLS B** quyết định certificate/tenant phía backend theo cấu hình của nó, còn **Host** có thể quyết định route HTTP; cả hai cần được kiểm thử.

### 5.4. So sánh trường hợp HTTPS nhưng không tương đương an toàn

| Cấu hình | Client → proxy | Proxy → backend | WAF nhìn thấy HTTP? | Backend được xác thực bởi proxy? |
| --- | --- | --- | --- | --- |
| Termination + HTTP | TLS A | HTTP plaintext | Có | **Không có TLS server authentication** ở chặng B |
| Bridging có verify | TLS A | TLS B, CA/SAN được kiểm tra | Có | Có, theo trust policy |
| Bridging nhưng bỏ verify | TLS A | TLS B, kiểm tra peer không đầy đủ | Có | **Không đảm bảo** xác thực backend |
| Passthrough | TLS xuyên proxy | Cùng phiên TLS client–backend | Không tại LB | **Client** xác thực backend, proxy không tạo phiên TLS B |
| Passthrough rồi backend thêm proxy nội bộ | TLS client–backend ingress | Có thể có hop mới sau termination tại backend ingress | Tùy nơi terminate | Phải đánh giá riêng chặng tiếp theo |

**Một biểu tượng HTTPS ở backend không đủ** để chứng minh kiểm tra certificate đang bật. Khi review cần chứng cứ cấu hình verify, CA, hostname, kết quả test certificate sai và log handshake thực.

## 6. Quyết định route bằng TLS metadata: SNI, ALPN, ECH và TLS 1.3

### 6.1. SNI và sự khác biệt giữa ba cách dùng

**Server Name Indication (SNI)** cho phép client khai báo tên server mong muốn trong ClientHello. Các tình huống:

| Mô hình | Proxy làm gì với SNI? | Nó có thấy HTTP URL/path không? |
| --- | --- | --- |
| L7 TLS termination | Chọn certificate/virtual server, sau đó giải mã HTTP để route tiếp | **Có**, sau khi handshake thành công |
| L4 TCP TLS passthrough có sniff ClientHello | Có thể chọn upstream dựa trên SNI quan sát được, không chấm dứt TLS | **Không** |
| L4 TCP passthrough không inspect SNI | Route theo IP/port/flow policy | **Không** |
| TLS bridging | Dùng SNI A ở downstream và có thể chủ động gửi SNI B ở upstream | **Có tại proxy**, vì nó terminate TLS A |

**Không dùng SNI làm identity hoặc access token.** Client có thể gửi SNI tùy ý; server/proxy cần kiểm soát hostname được phục vụ, certificate được cấp và quyền ứng dụng sau đó.

### 6.2. Unknown SNI và catch-all backend

Một sai lầm vận hành là cấu hình L4 SNI passthrough:

~~~text
api.example.test    -> backend API
admin.example.test  -> backend quản trị
anything else       -> backend quản trị   # SAI
~~~

Nếu unknown SNI rơi vào backend quản trị, attacker hoặc client vô tình có thể tiếp cận dịch vụ ngoài phạm vi thiết kế. **Default route** phải được review: có thể từ chối kết nối hoặc chuyển tới endpoint không nhạy cảm có policy rõ, nhưng không gửi unknown SNI đến backend có quyền cao.

Không dùng cách “nếu SNI rỗng thì coi là api.example.test” khi hệ thống cần phân biệt tenant/security domains mà chưa đánh giá client không gửi SNI. TLS passthrough **không có cách đọc HTTP Host bên trong ciphertext** để sửa quyết định route sai ở bước này.

### 6.3. ALPN và protocol selection

**Application-Layer Protocol Negotiation (ALPN)** giúp TLS peers thống nhất application protocol như **h2** hoặc **http/1.1**; còn một số giao thức TLS-based khác có identifier riêng. Những điểm thường gây nhầm:

- Trong L7 termination, **proxy** và client thương lượng ALPN cho **TLS A**.
- Trong TLS bridging, **proxy** và backend thương lượng ALPN **riêng cho TLS B**.
- HTTP/2 phía client và HTTP/1.1 phía backend là kiến trúc có thể hợp lệ khi proxy hỗ trợ chuyển đổi request/response semantics.
- **gRPC thường yêu cầu HTTP/2 semantics ở chặng phù hợp**; không mặc định proxy HTTP/1.1 tới backend vẫn xử lý đầy đủ gRPC.
- Trong TLS passthrough, proxy L4 có thể đọc **ALPN client offered list** từ ClientHello khi hiện rõ, nhưng không đồng nghĩa đã xác định protocol được server chọn, đặc biệt trong TLS 1.3.
- HTTP/3/QUIC không dùng cùng cách proxy TCP/443; cần data path UDP/443 và TLS-in-QUIC được hỗ trợ.

### 6.4. TLS 1.3 không cho phép sniff mọi dữ liệu handshake

Trong TLS 1.3, nhiều thông điệp sau ServerHello, bao gồm certificate server và lựa chọn ALPN trong EncryptedExtensions, được **mã hóa**. Vì vậy một L4 passthrough proxy thụ động **không thể kiểm tra đầy đủ certificate/ALPN cuối cùng** theo cách có thể nhìn thấy ở một số trường hợp TLS 1.2.

Một hệ giám sát passthrough có thể biết:

- Có kết nối TCP/UDP mới, source/destination IP/port.
- SNI và ALPN offered khi còn quan sát được trong ClientHello.
- TLS version/capability ở mức giới hạn theo dữ liệu bắt tay còn hiển thị.
- Số bytes, packet timing, connection durations, lỗi TCP và flow metadata.

Nó **không tự thấy**:

- HTTP method/path, Cookie, Authorization, request body hoặc response body.
- Certificate server của TLS 1.3 sau khi được bảo vệ, nếu không phải endpoint TLS.
- HTTP status 401/403/500 hoặc rule WAF theo nội dung ứng dụng.

**Không khẳng định “IDS không thấy gì”**: network IDS có thể phân tích flow metadata, bất thường TLS ClientHello, JA3/JA4-like fingerprints theo phương pháp hỗ trợ; nhưng các tín hiệu này có giới hạn và không thay HTTP payload inspection.

### 6.5. ECH thay đổi route-by-SNI

**Encrypted ClientHello (ECH)** bảo vệ những thông tin trong ClientHelloInner, trong đó có hostname thực của client khi triển khai đúng. Một proxy passthrough chỉ thấy ClientHelloOuter có thể không biết **SNI thật** cần route, do đó:

- Không thể mặc định dùng **plaintext SNI inspection** để chia nhiều backend khi client dùng ECH và các tên nội bộ được che.
- Có thể cần một **ECH-capable TLS terminator** được cấp quyền giữ cấu hình/khóa ECH, hoặc thiết kế route theo VIP/IP/outer name được phép.
- Phải kiểm tra cách DNS HTTPS/SVCB, ECH config, certificate và reverse proxy phối hợp trong sản phẩm thực.
- Không xem ECH như một lỗi của client cần ép tắt đại trà; đây là thay đổi về quyền riêng tư và mô hình khả năng quan sát.
- Nếu một nền tảng không hỗ trợ ECH, ghi nhận giới hạn và kiểm thử với các client có/không có khả năng ECH theo chính sách.

**Egress firewall hoặc IDS** cũng có thể bị giới hạn bởi ECH, QUIC và mã hóa ứng dụng; cần chính sách được đặt tại điểm có quyền quan sát thích hợp thay vì hứa hẹn một cảm biến thụ động có thể đọc mọi hostname.

### 6.6. Session resumption và 0-RTT tại proxy

Trong termination hoặc bridging, mỗi chặng TLS có **session tickets, resumption PSK và khóa riêng** khi tính năng được hỗ trợ. Việc **TLS A resumed** không chứng minh **TLS B resumed**. Với passthrough, backend là bên phát/nhận ticket cho TLS client; L4 LB không có quyền giải mã/đánh giá PSK ứng dụng.

**0-RTT TLS 1.3/QUIC** có nguy cơ **replay**. Nếu proxy terminate TLS và chấp nhận early data rồi chuyển request vào backend có tác dụng phụ, backend có thể không biết đó là early data. Cần:

1. **Tắt 0-RTT theo mặc định** cho API có state changes, thanh toán, admin và thao tác nhạy cảm, trừ khi có thiết kế chống replay đã được duyệt.
2. Khi thật sự dùng, giới hạn route/method theo **ngữ nghĩa ứng dụng**, idempotency và xử lý **425 Too Early** nếu phù hợp.
3. Theo dõi early_data_accepted/rejected và các duplicate side effects; không tự cho rằng nhận ticket là có thể gửi early data.
4. Đánh giá nhiều edge nodes/regions vì anti-replay cache phân tán có thể không nhất quán.

Nếu **passthrough**, policy 0-RTT thuộc TLS backend. Nếu **termination**, policy 0-RTT thuộc TLS edge, và proxy phải phối hợp với backend. Không coi “đã bật TLS 1.3” đồng nghĩa “đã bật 0-RTT”.

## 7. Bảng quyết định chọn kiến trúc

### 7.1. So sánh theo yêu cầu bảo mật và vận hành

| Tiêu chí | TLS termination + HTTP | TLS re-encryption (bridging) | TLS passthrough |
| --- | --- | --- | --- |
| Ai giữ certificate/key client-facing? | L7 edge | L7 edge | Backend |
| Ai xác thực server với client? | Client xác thực edge | Client xác thực edge | Client xác thực backend |
| Ai xử lý HTTP application plaintext? | Edge + backend, qua hop plaintext | Edge + backend, mỗi hop TLS riêng | Backend, không phải LB |
| Mã hóa edge → backend | **Không** | **Có**, nếu được bật đúng | **Cùng TLS session client–backend** |
| WAF/HTTP routing ở LB | Có | Có | Không, trừ giải mã tại nơi khác |
| SNI-based traffic steering | Có | Có | Có thể khi ClientHello thấy được |
| Route theo path/HTTP header tại LB | Có | Có | Không |
| Backend trực tiếp thấy client mTLS cert | Không mặc định | Không mặc định | Có nếu mTLS kết thúc ở backend |
| TLS policy/cert tập trung ở edge | Có | Có ở edge; thêm upstream TLS policy | Phân tán tới backend |
| Chứng minh backend identity bằng TLS ở chặng sau | Không có | Proxy xác minh backend | Client xác minh backend |
| Kết nối non-HTTP TLS | Cần L7/protocol support | Cần L7/protocol support | Thường phù hợp hơn với TCP/TLS |
| Client IP tại backend | Header/PROXY/transport theo thiết kế | Header/PROXY/transport theo thiết kế | Tùy SNAT, DSR hoặc PROXY protocol |
| Application metrics tại LB | Đầy đủ hơn | Đầy đủ hơn | Chủ yếu flow/connection-level |
| Điểm rủi ro chính | Plaintext backend và edge key compromise | Hai trust boundaries và upstream verify sai | Backend cert/mTLS, WAF blindness tại LB và L4 policy |

### 7.2. Khi nào nên ưu tiên mỗi mô hình?

**Termination + HTTP** chỉ phù hợp khi môi trường và chính sách cho phép plaintext trên chặng backend, có kiểm soát rõ network/host, không có yêu cầu end-to-end peer authentication ở hop đó và rủi ro đã được chấp nhận. Đừng chọn nó chỉ vì “backend ở private subnet”.

**Bridging** là phương án thường hợp lý khi cần **L7 WAF, API routing, centralized observability** và vẫn muốn **TLS/mTLS cho traffic trong mạng backend**. Đây là phương án mạnh nếu upstream certificate/hostname validation được thiết kế đúng và proxy được bảo vệ như một vùng tin cậy.

**Passthrough** phù hợp khi backend phải trực tiếp kết thúc mTLS hoặc ứng dụng không phải HTTP, khi chính sách không cho L7 edge đọc payload, hoặc khi cần backend sở hữu TLS identity. Đánh đổi là không thể kiểm tra path/header/body tại LB, nên phải đặt **WAF/API gateway bên trong điểm termination** nếu ứng dụng cần kiểm tra HTTP.

### 7.3. Không chọn theo hiệu năng trước khi có threat model

Một benchmark có thể cho thấy passthrough giảm CPU mã hóa ở LB; nhưng chi phí mã hóa sẽ chuyển sang backend. Bridging thêm một TLS connection (và có thể thêm CPU/latency), nhưng cho phép WAF và bảo vệ chặng nội bộ. Termination + HTTP giảm một lớp mã hóa nhưng phơi lộ plaintext trên hop đó.

Đo **end-to-end throughput/latency, CPU, TLS handshake rate, connection pooling, backend load và cache hit rate** dưới cùng một workload; không dựa chỉ vào biểu đồ CPU ở edge. Chính sách **dữ liệu, quyền truy cập, mTLS và compliance** là các ràng buộc phải xét trước tối ưu.

## 8. mTLS và truyền danh tính qua proxy

### 8.1. mTLS ở ba mô hình

**mTLS (mutual TLS)** cho phép hai phía TLS xác thực chứng chỉ lẫn nhau theo policy. Trong ba mô hình:

| Mô hình | Ai yêu cầu và kiểm tra client certificate gốc? | Backend nhận được gì? |
| --- | --- | --- |
| Termination ở edge | Edge proxy yêu cầu/kiểm tra mTLS trên TLS A | Mặc định chỉ có request HTTP; phải có cơ chế truyền identity đáng tin |
| Bridging | Edge kiểm tra client cert trên TLS A; backend có thể kiểm tra **proxy cert** trên TLS B | Identity của proxy trên hop B, cộng identity gốc nếu được truyền có bảo vệ |
| Passthrough | Backend yêu cầu/kiểm tra mTLS với client | Trực tiếp thấy TLS client certificate trên cùng phiên |

**Không nhầm proxy mTLS certificate ở chặng B với end-user/client certificate của chặng A.** Hai certificate có thể đại diện cho các principal khác nhau, có phạm vi tin cậy khác nhau.

### 8.2. Danh tính client truyền xuống backend phải có nguồn đáng tin

Nếu TLS được terminate ở edge, backend không nhìn thấy trực tiếp TLS client handshake gốc. Một số proxy có thể chuyển identity đã xác minh vào header hoặc metadata riêng, ví dụ:

~~~text
X-Authenticated-Client: service-account-orders
X-Verified-Client-Cert-Fingerprint: <fingerprint được edge xác thực>
X-Request-ID: req-...
~~~

**Đây là các header minh họa, không có tiêu chuẩn tự động an toàn vì đặt tên bắt đầu bằng X-.** Nếu client có thể gửi chính những header đó và backend tin luôn, có thể xảy ra **identity spoofing**. Muốn dùng cách truyền này phải:

1. Edge **xóa mọi bản do client cung cấp** của các header định danh đáng tin trước khi xử lý.
2. Edge chỉ **tạo lại metadata** từ kết quả xác thực mTLS thực tế, sau khi kiểm chứng certificate chain, EKU, SAN/SPIFFE ID và chính sách.
3. Backend chỉ nhận request từ **edge đã xác thực**, ví dụ qua mTLS B, allowlist/segmentation và authorization theo service identity.
4. Backend kiểm tra **đúng header/metadata format, trust source và mapping principal → quyền**, không tự cấp quyền chỉ vì chuỗi header có giá trị.
5. Khi có nhiều proxy, phải xác định **điểm cuối tin cậy nào ghi header** và chuỗi proxy nào có quyền duy trì/đổi chúng.
6. Nếu dùng signed identity assertion hoặc JWT trao giữa gateway và backend, cần xác minh chữ ký, audience, issuer, expiry và replay/rotation controls như token ứng dụng; không xem transport header là bằng chứng mật mã.

### 8.3. mTLS identity không tương đương HTTP authorization

Backend có thể thấy “TLS peer hợp lệ” nhưng request vẫn không được quyền truy cập tài nguyên. Các lớp khác nhau:

- **Transport peer identity:** cert/PSK/trust chain xác minh ai đang kết nối.
- **User/service principal:** account, workload identity, OAuth/OIDC claims hoặc ánh xạ mTLS.
- **Authorization:** quyền với endpoint, tài nguyên, tenant, hành động và ngữ cảnh hiện tại.
- **Network policy:** firewall, ACL hoặc service mesh cho phép nguồn/đích/cổng nào.

Client bị thu hồi certificate hoặc quyền ứng dụng không được tiếp tục thao tác nhạy cảm chỉ vì **TLS resumption/session ticket** còn hiệu lực từ lần kết nối trước. Cần quản lý revocation/reauthentication và **đánh giá authorization cho từng request** theo policy.

### 8.4. Chứng chỉ client qua passthrough

Trong passthrough, backend có thể cấu hình bắt buộc mTLS, nên client kết nối thẳng về mặt TLS identity. Tuy nhiên:

- L4 LB vẫn có thể làm **SNAT** hoặc dùng TCP proxy: IP nguồn nhìn từ backend không chắc là IP client.
- Backend cần tự quản **client CA, certificate revocation, hostname/server identity, ALPN, session tickets** và phân tách service tenants.
- Backend app cần tự áp WAF/API controls hoặc nhận traffic qua một ingress nội bộ có các policy đó.
- Nếu nhiều backend phục vụ cùng public hostname, **tất cả phải có certificate hợp lệ cho hostname đó** hoặc cơ chế TLS virtual hosting được thiết kế đúng.
- Không thể dùng **mTLS chặng B** từ proxy termination như một chứng cứ client gốc đã trình certificate; cần có identity delegation rõ ràng nếu yêu cầu.

### 8.5. Chính sách client certificate khi sử dụng TLS 1.3 resumption

Một resumed TLS 1.3 PSK handshake có thể không yêu cầu client trình lại certificate theo cách full handshake; ngữ cảnh xác thực từ phiên trước có thể được tái dùng theo TLS stack/policy. Nếu client certificate bị thu hồi hoặc quyền đổi, hãy kiểm tra:

- Ticket lifetime và resumption scope.
- Điều kiện buộc **fresh client certificate authentication**.
- Cơ chế invalidation khi identity/CA/policy thay đổi.
- Authorization ở gateway/backend vẫn theo trạng thái mới.
- Tác động tới mTLS trên **cả hai chặng** nếu bridging.

Không coi một cờ “resumed=true” là kết quả xác thực mTLS vừa được kiểm tra ở thời điểm hiện tại.

## 9. Giữ và xác thực địa chỉ client: X-Forwarded-For, Forwarded và PROXY protocol

### 9.1. Tại sao client IP trở nên phức tạp?

Với một reverse proxy/LB ở giữa, backend có thể thấy **peer TCP source** là proxy thay vì IP public của client. Thêm một hoặc nhiều tầng NAT, CDN, sidecar, VPN hay load balancer làm thay đổi bức tranh:

~~~text
Client public IP:         198.51.100.25
CDN address:              203.0.113.10
Edge proxy:               10.20.1.10
Backend:                  10.20.2.11

Backend TCP peer:         10.20.1.10
HTTP X-Forwarded-For:     có thể ghi 198.51.100.25, 203.0.113.10
                          nếu chuỗi proxy được cấu hình đáng tin
~~~

**Không coi X-Forwarded-For là bằng chứng định danh người dùng.** Một client trực tiếp có thể tự gửi header tương tự nếu edge không xóa/thay/chuẩn hóa, và nhiều người dùng sau NAT có thể cùng IP public.

### 9.2. Các loại metadata không thay thế nhau

| Cơ chế | Vị trí | Thông tin | Điều kiện tin cậy |
| --- | --- | --- | --- |
| **TCP socket peer address** | Network/transport | IP/port peer mà endpoint nhìn thấy | Có thể là IP proxy/NAT, không nhất thiết client gốc |
| **X-Forwarded-For (XFF)** | HTTP header phổ biến nhưng không phải cơ chế xác thực | Danh sách IP liên quan chuỗi proxy | Chỉ tin từ reverse proxy/CDN đã xác thực và cấu hình đúng |
| **Forwarded (RFC 7239)** | HTTP header chuẩn hóa cú pháp | for, by, host, proto theo format quy định | Vẫn do bên gửi cung cấp; phải xác minh proxy chain |
| **X-Forwarded-Proto** | HTTP header phổ biến | Scheme client-facing (http/https) do proxy cung cấp | Cần trusted proxy và overwrite; không cho client tự quyết định |
| **X-Forwarded-Host** | HTTP header phổ biến | Host gốc ở edge khi được chấp nhận | Tránh Host/header injection và redirect/open redirect |
| **PROXY protocol v1/v2** | Header ở đầu transport connection, **ngoài TLS payload** | Có thể mang IP/port nguồn/đích và metadata mở rộng theo version/ứng dụng | **Chỉ bật trên listener nhận từ peer LB đáng tin**, parser phải hỗ trợ |
| **TPROXY/DSR/source-IP preservation** | Cơ chế network | Có thể giữ source IP thực ở backend theo topology | Route, return path, kernel/network controls phải phù hợp |
| **X-Request-ID/trace context** | Ứng dụng/log | Liên kết sự kiện nhiều hop | Không phải nhận dạng user hay bằng chứng chống spoof |

### 9.3. Trusted proxy chain

Với chuỗi **Client → CDN → WAF → Reverse proxy → App**, cách an toàn là:

1. Điểm đầu tiên thực sự tin cậy và nhận từ Internet **không tin dữ liệu Forwarded/XFF do client cung cấp** khi dùng cho security decisions; làm sạch hoặc tạo chuỗi đáng tin theo policy.
2. Mỗi proxy trung gian chỉ tin header từ **đúng IP/certificate/service identity upstream đã cấp quyền**.
3. Backend cấu hình **trusted proxies** chính xác, không đánh dấu toàn bộ Internet hoặc mọi mạng private là trusted.
4. Các proxy thống nhất **thứ tự hop**, cách xử lý IPv4/IPv6, port, unknown identifiers và nhiều header trùng lặp.
5. IP client được chuẩn hóa có thể dùng cho **rate limiting và điều tra**, nhưng authorization nhạy cảm vẫn cần identity được xác thực riêng.

Nếu cloud LB cho phép lưu lượng trực tiếp bypass CDN/WAF, attacker có thể gửi XFF giả làm IP được allowlist. Do đó **network origin restriction** phải đi kèm header trust policy.

### 9.4. PROXY protocol và TLS passthrough

**PROXY protocol** giúp gửi metadata transport từ LB tới backend trong môi trường passthrough hoặc termination theo khả năng. Trong một luồng TCP passthrough có PROXY protocol:

~~~text
LB -> Backend TCP bytes:

[PROXY protocol header][TLS ClientHello][TLS handshake/data...]
~~~

Backend phải hiểu PROXY protocol để **đọc header trước khi đưa bytes TLS vào TLS parser**. Nếu backend không hỗ trợ hoặc không bật tính năng:

- TLS server có thể nhận byte ASCII/binary của PROXY header thay vì TLS record và báo handshake error.
- Ngược lại, nếu backend bật bắt buộc PROXY protocol nhưng LB không gửi, backend có thể chờ/sai định dạng và lỗi kết nối.
- Nếu listener cho client Internet trực tiếp gửi PROXY header, attacker có thể **giả source IP/metadata** vì bản thân PROXY protocol không tự xác thực sender.

**PROXY protocol không phải TLS proxy và không tự mã hóa phần header.** Nếu link giữa LB và backend cần bảo vệ metadata, thiết kế tunnel/mạng hoặc cơ chế thích hợp riêng; không dựa vào một prefix header như bảo vệ mật mã.

### 9.5. Forwarded scheme và rủi ro redirect/cookie

Khi client dùng HTTPS nhưng proxy gửi HTTP tới backend, ứng dụng có thể nhìn socket scheme HTTP và tạo:

- Redirect từ HTTPS về HTTP hoặc **vòng lặp 301/302** khi middleware tự redirect HTTPS.
- Link tuyệt đối sai host/scheme.
- Cookie thiếu Secure hoặc cấu hình SameSite không phù hợp.
- OAuth/OIDC redirect URI/callback sai.
- WebSocket URL ws:// thay vì wss:// và lỗi upgrade.

Cần để backend nhận **thông tin external scheme/host đáng tin** từ proxy qua cơ chế/framework hỗ trợ, đồng thời chỉ tin **trusted proxy list**. Không bật “trust all forwarded headers” ở service có thể bị truy cập trực tiếp.

**HSTS** nên được phát ở host HTTPS phù hợp theo policy, nhưng không sử dụng HSTS như một cách sửa TLS verification tới backend. Cookie Secure và forward scheme phải phản ánh kết nối client-facing đã được xác minh, không cho client tự gắn X-Forwarded-Proto: https để đánh lừa server.

### 9.6. NAT, địa chỉ nguồn và giới hạn quy nguồn

Trong mạng doanh nghiệp, một client VPN hoặc nhiều thiết bị Wi-Fi có thể bị **SNAT** trước khi tới LB. XFF/PROXY protocol giúp truyền thông tin ở **điểm quan sát được**, nhưng không tự tìm lại user gốc nếu phía trước đã NAT mà không lưu mapping. Khi điều tra, cần **NAT source-port translation logs, DHCP lease, VPN/NAC identity, timestamp và application session** phù hợp.

Nếu rate limiting dựa IP được áp tại nơi đã NAT cả trăm người dùng thành một địa chỉ, có nguy cơ **chặn nhầm cả nhóm**. Với authenticated API, ưu tiên bổ sung rate limit theo principal/tenant/API key đã xác thực, kết hợp IP khi hợp lý.

## 10. HTTP/1.1, HTTP/2, gRPC, WebSocket, SSE và HTTP/3/QUIC

### 10.1. Một reverse proxy không tự hiểu mọi protocol

| Protocol/tình huống | Termination + L7 | Passthrough + L4 | Điểm cần kiểm chứng |
| --- | --- | --- | --- |
| HTTP/1.1 HTTPS | Route Host/path/header, WAF và caching | Backend trực tiếp nhận HTTPS | Keep-alive, Host validation, header normalization |
| HTTP/2 over TLS | Multiplex streams, có thể route per-request khi L7 hiểu H2 | Cả HTTP/2 connection tới một backend | ALPN h2, pseudo-headers, flow control, max streams |
| gRPC over HTTP/2 | Cần gateway hỗ trợ gRPC/H2 và trailers | Backend xử lý gRPC trực tiếp | gRPC status/trailers, streaming, deadline/timeout, H2 upstream |
| WebSocket qua HTTP/1.1 | Proxy phải hỗ trợ Upgrade và connection lifetime | Backend xử lý upgrade | Idle timeout, sticky connection và graceful close |
| Server-Sent Events (SSE) | Có thể proxy HTTP response streaming | Backend tự stream trong TLS | Buffering, timeout, connection drain |
| HTTP/3 over QUIC | L7 proxy cần hỗ trợ QUIC/HTTP3, có thể chuyển sang H2/H1 upstream | L4 UDP/QUIC LB theo flow/connection ID nếu hỗ trợ | UDP/443, QUIC CID, TLS-in-QUIC, retry/migration |
| TLS custom TCP protocol | Cần proxy ứng dụng hiểu protocol hoặc TCP mode | Phù hợp với TCP passthrough | Không áp HTTP WAF nếu payload không phải HTTP |
| Database TLS | Thường không dùng HTTP reverse proxy để xử lý SQL packets | Có thể load balance theo TCP tùy giao thức DB | Authentication, transactions, connection persistence |
| MQTT over TLS hoặc custom IoT | Nếu có gateway hiểu protocol có thể terminate | L4 passthrough | Client cert, keepalive, stateful sessions, gateway policy |

**gRPC không chỉ là “HTTPS request bình thường”.** Proxy phải giữ đúng semantics HTTP/2, metadata, trailers và stream lifetimes. L4 passthrough tránh HTTP protocol translation tại LB nhưng khả năng cân bằng theo **request** thấp hơn vì routing thường theo **connection**.

### 10.2. HTTP/2 connection pooling, coalescing và route fairness

Một HTTP/2 connection có thể chứa **nhiều streams**, dẫn đến:

- L4 least-connections có thể coi một client với hàng trăm streams chỉ là **một TCP connection**.
- L7 proxy có thể cân bằng tải **theo request/stream** ở backend nếu product hỗ trợ và thiết kế đúng.
- Một long-lived gRPC stream có thể giữ backend lâu, gây **imbalanced load** khi dùng connection hashing.
- Client connection coalescing có các điều kiện certificate/origin riêng; không mặc định một TLS session thuộc domain A có thể xử lý domain B mà bỏ Host/authority authorization.

Đo **active connections và active streams/requests** riêng; không giả định số TCP connections tỷ lệ với tổng số API requests.

### 10.3. WebSocket và idle timeouts

WebSocket có thể duy trì kết nối lâu, làm chiến lược load balancing theo connection trở thành **gắn backend cho cả phiên**. Nếu proxy terminate TLS, nó cần hỗ trợ WebSocket handshake/upgrade hoặc cơ chế phù hợp của HTTP/2/HTTP/3 khi có, giữ đúng **ping/pong, idle timeout và connection draining**.

Đổi chế độ termination sang passthrough mà không test WebSocket có thể làm client thấy certificate khác, route tới backend chưa sẵn sàng hoặc mất thống kê WAF trên handshake. Ngược lại, chuyển passthrough sang L7 proxy có thể làm fail vì **proxy timeout/buffering** nếu backend dùng stream dài.

### 10.4. HTTP/3 và QUIC có đường đi khác TCP

HTTP/3 chạy trên **QUIC qua UDP**, với TLS 1.3 handshake tích hợp bên trong QUIC CRYPTO frames. Một TCP stream proxy dùng SNI preread **không thể tự cân bằng HTTP/3** trên UDP/443; cần hỗ trợ QUIC/UDP đặc thù.

**QUIC connection ID (CID)** có thể hỗ trợ route/connection migration; load balancer phải xử lý chính xác flow và CID theo cơ chế được sản phẩm hỗ trợ. Không thay QUIC routing bằng cách chỉ hash UDP 5-tuple rồi cho rằng mọi client migration đều ổn.

Nếu hệ thống phục vụ cả HTTPS/TCP và HTTP/3/UDP, hai policy paths có thể khác nhau:

~~~text
Client TCP/443  -> HTTPS HTTP/1.1 hoặc HTTP/2 -> TLS TCP proxy/LB path
Client UDP/443  -> HTTP/3 QUIC                 -> QUIC-aware LB/path
~~~

Phải kiểm tra **firewall cả TCP/443 và UDP/443**, WAF/DoS policy tương đương về ý định, observability cả hai đường và chiến lược fallback khi UDP bị chặn. Không được ngầm giả định “port 443” chỉ là TCP.

### 10.5. TLS passthrough cho protocol không phải HTTP

Một hệ thống xử lý Postgres/TLS, AMQP/TLS, MQTT/TLS hoặc các protocol tùy chỉnh có thể dùng L4 passthrough để backend vẫn tự xác thực và xử lý ứng dụng. Nhưng:

- Kết nối lâu dài hoặc transaction stateful cần **drain/affinity** phù hợp.
- Health check TCP thành công chưa xác minh broker/DB có thể phục vụ nghiệp vụ.
- Client cert mTLS hoặc SASL/DB auth là kiểm soát riêng.
- **Database failover và consistency** không thể giải quyết chỉ bằng L4 LB lựa chọn backend ngẫu nhiên.
- Các thuật toán load balancing trên connection có thể không tính tới pending queries, transaction length hoặc stream load.

## 11. Cân bằng tải, health check, failover và connection draining

### 11.1. Thuật toán chọn backend không phụ thuộc hoàn toàn vào TLS

Các thuật toán phổ biến:

| Thuật toán | Đơn vị quyết định | Ưu điểm | Rủi ro / giới hạn |
| --- | --- | --- | --- |
| **Round robin** | Mỗi connection hoặc request tùy L4/L7 | Đơn giản khi backend tương đương | Backend chậm/ít tài nguyên vẫn nhận lượng như nhau |
| **Weighted round robin** | Connection/request theo trọng số | Hỗ trợ backend khác công suất | Weight không tự theo kịp CPU/latency thực |
| **Least connections** | Số connection đang hoạt động | Hữu ích với connection lifetimes biến thiên | Một HTTP/2 connection có thể chứa nhiều requests |
| **Least requests / least outstanding** | Request đang xử lý khi proxy L7 có dữ liệu | Tốt hơn khi requests khác thời gian | Không luôn có ở L4; stream dài cần đánh giá riêng |
| **Source-IP hash** | IP nguồn thấy tại LB | Một dạng affinity có tính xác định | Nhiều client sau NAT cùng IP; thay IP/VPN tạo redistribution |
| **Consistent hash** | Khóa định danh/routing được chọn | Hạn chế xáo trộn khi backend thay đổi | Không dùng input client-controlled cho vùng nhạy cảm mà không kiểm soát |
| **Cookie-based persistence** | Cookie do proxy/app quản lý | Giữ session/tenant khi ứng dụng cần | Cookie phải có integrity, lifetime và SameSite/Secure phù hợp |
| **Random choices / power of two** | Tập backend healthy, số liệu connection/load | Hiệu quả ở một số workload lớn | Phụ thuộc dữ liệu load và implementation |

**Phân phối connection ở L4** không đồng nghĩa **phân phối HTTP request ở L7**. Nếu một gRPC channel chứa 50.000 requests, LB L4 có thể luôn gửi chúng tới một backend trong suốt lifetime của connection.

### 11.2. Health check nhiều mức

| Mức health check | Kiểm tra được | Không chứng minh |
| --- | --- | --- |
| **TCP connect** | IP/port nhận kết nối tại thời điểm thử | TLS/certificate hợp lệ, HTTP app hoạt động |
| **TLS handshake** | Đầu cuối có thể bắt tay TLS theo client test; có thể xác minh certificate nếu cấu hình | API business path, database, authorization |
| **HTTP health endpoint** | HTTP status/path/content theo policy | Tất cả downstream dependencies hoặc mọi tenant đều khỏe |
| **Readiness application** | Service sẵn sàng nhận traffic theo định nghĩa của app | Mọi request nghiệp vụ đều thành công |
| **Synthetic end-to-end** | DNS→TLS→HTTP/API/identity trên đường thực của một client | Mọi vùng địa lý và tình huống traffic |

Với **passthrough**, health check của LB L4 chỉ **mở TCP tới backend** có thể trả “healthy” ngay cả khi certificate backend đã hết hạn hoặc TLS handshake fail với SNI cụ thể. Nếu LB có thể làm **active TLS check** như một client được phép, cần chọn **SNI, ALPN, trust CA và hostname validation** tương ứng; nếu không có, bổ sung synthetic probe từ hệ thống giám sát ngoài LB.

Với **bridging**, proxy có thể nhận request HTTPS thành công từ client, nhưng TLS B tới backend bị lỗi. Lỗi có thể biểu hiện như **502 Bad Gateway** hoặc biến thể tùy proxy, không phải một vấn đề certificate của client.

### 11.3. Quản lý readiness và startup

Không nên đưa backend vào pool chỉ vì cổng TCP đã mở; service có thể vẫn đang:

- Nạp key/certificate, CA bundle hoặc cấu hình mTLS.
- Khởi tạo DB connection pool hoặc cache.
- Đồng bộ routing/tenant configuration.
- Đợi workload certificate từ service mesh.
- Khôi phục state sau restart.

Readiness nên kiểm tra **những phụ thuộc thiết yếu để nhận lưu lượng** mà không gây side effects nguy hiểm. Một health endpoint chứa nhiều thao tác nặng hoặc gọi full dependency graph mỗi giây có thể tự tạo sự cố tải. Thiết kế **liveness** và **readiness** với ngữ nghĩa khác nhau.

### 11.4. Graceful drain và long-lived connections

Khi loại một backend khỏi pool để deploy hoặc rotate certificate:

1. Đánh dấu backend **không nhận connection/request mới** theo cơ chế LB.
2. Cho những connection/stream đang hoạt động hoàn tất trong giới hạn được chấp thuận.
3. Đối với HTTP/2/gRPC, có thể dùng cơ chế như **GOAWAY** khi proxy/server hỗ trợ để client chuyển dần stream mới.
4. Đối với WebSocket hoặc custom TCP, phải có policy timeout, client reconnect/backoff và state recovery.
5. Sau drain, xác nhận backend không còn phiên cần thiết rồi mới shutdown/rotate.

Một L4 passthrough LB không thể đọc HTTP/2 stream metadata để biết request nào còn đang xử lý; nó thường chỉ biết **connection state**. Vì vậy drain một TCP connection giữ nhiều gRPC streams có thể lâu hơn so với L7 proxy hiểu ứng dụng.

### 11.5. Affinity, sticky sessions và login state

Nếu ứng dụng yêu cầu mọi request của một user vào cùng backend vì state chỉ nằm trong RAM, source-IP hash hoặc sticky cookie có thể giảm lỗi tạm thời. Tuy nhiên:

- Affinity **không thay database/session store bền vững** nếu cần HA thực sự.
- Cookie affinity khác với **HTTP session cookie đăng nhập** và **TLS session ticket**.
- Client mobile/VPN/CGNAT có thể đổi IP hoặc nhiều người cùng IP; source-IP hash không đại diện user.
- Một backend bị lỗi cần failover; affinity không được giữ client mãi ở backend down.
- Trong passthrough, backend trực tiếp xử lý TLS và cookie HTTP; L4 LB không thể dựa vào cookie nằm trong HTTPS ciphertext để route.

### 11.6. TLS session resumption qua nhiều backend

Trong termination ở edge, resumption giữa client và edge phụ thuộc trạng thái/ticket keys **của edge**. Với passthrough, **backend** phát ticket; khi L4 LB chuyển client sang backend khác không chia sẻ resumption state, client có thể phải full handshake.

Với bridging, có **hai cơ chế nối phiên độc lập**. Nếu node A edge có ticket TLS A còn proxy → backend B tạo TLS B mới, tỷ lệ resumption hai chặng có thể khác nhau.

Không chia sẻ ticket keys rộng vô hạn chỉ để làm dashboard “resumption hit 100%”. Cần bảo vệ **key scope, lifetime, rotation, failover và cách fallback full handshake**; đặc biệt với mTLS và nhiều tenant.

### 11.7. Đường trả lời và stateful firewall

Một thiết kế LB có thể sử dụng **SNAT**, **DSR (Direct Server Return)**, TProxy hoặc các cách chuyển tiếp khác. Nếu traffic yêu cầu quay lại cùng điểm stateful firewall/NAT mà đường phản hồi đi nơi khác, có thể xảy ra timeout dù health check ở một số vị trí thành công.

Khi triển khai:

- Vẽ route từ client tới VIP, từ LB tới backend và từ backend trả về.
- Ghi chú mọi IP/port được NAT và điểm thấy source IP thật.
- Đảm bảo firewall/ACL cho phép đường cần thiết mà **không mở quá rộng**.
- Với DSR/source-IP preservation, kiểm tra network routing, ARP/ND, VIP ownership và tính bất đối xứng theo sản phẩm.
- Giám sát connection resets, retransmissions, SYN backlog, ephemeral port exhaustion và conntrack state.

**TLS handshake fail có thể là triệu chứng của network path**, không phải luôn do certificate. Ví dụ backend nhận ClientHello nhưng server response không về vì route asymmetry, trong khi công cụ hiển thị “SSL handshake timeout”.

## 12. PKI, chứng chỉ, private keys và vòng đời cấu hình

### 12.1. Bản đồ chứng chỉ theo endpoint

| Mô hình | Certificate client-facing | Certificate nội bộ | Private key cần ở đâu? |
| --- | --- | --- | --- |
| Termination + HTTP | api.example.test tại edge | Không có TLS phía backend | Edge hoặc key service của edge |
| Bridging | api.example.test tại edge | orders.internal.example.test tại backend | Edge giữ key A; backend giữ key B; proxy có thể giữ client cert cho mTLS B |
| Passthrough | api.example.test tại từng backend TLS | Có thể có downstream TLS tiếp sau backend ingress | Backend (hoặc TLS service của backend), không phải L4 LB |
| Multi-tenant virtual host | Cert/SAN theo tenant/host phục vụ | Cert service-specific theo tầng | Tách key scope, IAM và rotation |

Đây là những vị trí **logic**; thực tế HSM, hardware accelerator hoặc managed certificate service có thể giữ private key không xuất ra file. Quan trọng là **những identity/nhóm vận hành nào có quyền sử dụng khóa**, không phải chỉ file nằm ở thư mục nào.

### 12.2. Kiểm tra certificate đúng

Khi client xác thực server hoặc proxy xác thực backend, cần kiểm tra:

1. Certificate chain dẫn đến CA/trust anchor được phép.
2. Thời gian hiệu lực certificate và đồng hồ máy.
3. Hostname/identity nằm trong SAN phù hợp; không chỉ nhìn Common Name tùy tiện.
4. Mục đích sử dụng/chính sách xác thực phù hợp (serverAuth/clientAuth khi có).
5. Signature algorithms, key sizes và TLS versions theo baseline bảo mật.
6. Revocation policy theo khả năng và yêu cầu tổ chức, gồm OCSP/CRL hoặc cơ chế kiểm soát khác phù hợp.
7. Trust store/CA bundle được cập nhật và phân phối đồng bộ trong cluster.

**Không dùng insecure skip verify / verify none trong production** để chữa lỗi certificate khi bridging. Hãy điều chỉnh **CA, SAN/SNI, DNS và lifecycle** theo thiết kế đúng. Nếu backend certificate thiếu SAN hợp lệ, cấp đúng certificate thay vì chấp nhận một peer chưa xác thực.

### 12.3. Rotation không gây downtime

Một quy trình phổ biến:

1. Kiểm kê certificate sắp hết hạn và nơi được dùng, kể cả **edge, origin, mTLS proxy và service mesh**.
2. Cấp certificate/key mới và lưu qua secret manager/managed service được phép.
3. Bảo đảm trust roots phù hợp đã được phân phối **trước** khi chuyển certificate nếu thay CA.
4. Nạp cấu hình mới bằng hot reload/graceful deployment theo sản phẩm, kiểm soát quyền file/secret.
5. Kiểm tra **full TLS handshake** và certificate chain tại từng hostname/SNI/ALPN, không chỉ dựa vào resumed session cũ.
6. Kiểm tra kết nối proxy→backend **từ đúng node**, gồm backend name verification và client mTLS khi có.
7. Theo dõi handshake failures, 5xx, p95, active connections và cert expiry.
8. Loại bỏ key/cert cũ sau thời gian phù hợp, ghi audit và đảm bảo rollback có kiểm soát.

**Session resumption có thể không gửi certificate mới trong lần resumed handshake.** Một probe dùng session ticket cũ **không đủ để xác nhận certificate vừa triển khai**. Để kiểm tra rotation, dùng fresh full handshake với SNI đúng và xác minh chain thực.

### 12.4. Rủi ro chia sẻ key giữa môi trường

Một wildcard certificate có thể được dùng ở nhiều subdomain theo chính sách, nhưng **cùng certificate/key** trên production, staging và dịch vụ nhà thầu làm **mở rộng blast radius nếu private key bị lộ**. Tương tự, TLS ticket keys chia sẻ giữa nhiều edge clusters/tenants cần được review.

Nếu các tenant có yêu cầu cách ly cao:

- Cân nhắc certificate/keys riêng cho từng tenant/hostname.
- Tách secret store/IAM/RBAC và deployment pipeline.
- Phân biệt quyền đọc certificate public với quyền sử dụng private key.
- Không cho một worker staging nạp key production chỉ vì chung LB.
- Audit những nơi có thể export secret, thời gian và người/identity thực hiện.

### 12.5. Cơ chế mã hóa và protocol policy

Đặt baseline:

- Ưu tiên **TLS 1.3** ở những endpoint/client hỗ trợ; chỉ giữ **TLS 1.2** nếu yêu cầu tương thích được chấp thuận và dùng bộ mã mạnh.
- Vô hiệu **TLS 1.0/1.1** và cipher/kex lỗi thời theo baseline tổ chức.
- Ưu tiên forward secrecy, groups/ciphers được phép, quản lý ticket lifetime và resumption phù hợp.
- Giới hạn **ALPN protocols** theo nhu cầu, ví dụ HTTP/2/gRPC và HTTP/1.1.
- Kiểm tra HTTPS redirect, **HSTS** và certificate hostname ở client-facing edge.
- Khi TLS B dùng PKI nội bộ, **trust store/CA** phải được bảo vệ, không dùng “tin mọi self-signed”.

**TLS version và cipher policy có thể khác giữa hai hops bridging**, nhưng sự khác biệt phải được chủ động đánh giá, không để một hop yếu trở thành đường bị bỏ quên.

### 12.6. Sự cố lộ private key

Khi nghi certificate private key bị lộ:

1. Xác định những **hostnames, endpoints, nodes, regions, tenants** sử dụng key.
2. Thu hồi/rotate certificate theo quy trình PKI và xử lý secret compromise.
3. Kiểm tra **ticket keys, TLS session resumption state và client/server auth** bị ảnh hưởng nếu có.
4. Không cho traffic đi qua endpoint với key nghi lộ chỉ vì rollback khó.
5. Kiểm tra từng TLS hop, certificate mới và application authorization.
6. Điều tra log truy cập secret/key, cấu hình export và khả năng bị lộ payload.

Không khẳng định **mọi traffic TLS trong quá khứ đều giải mã được** khi key lộ: tác động phụ thuộc phiên bản, trao đổi khóa, forward secrecy, ticket key/state và dữ liệu thu thập. Cần đánh giá theo chứng cứ và thuật toán đang dùng.

## 13. WAF, IDS/IPS, firewall và các ranh giới tin cậy

### 13.1. WAF chỉ xử lý được những gì nó thấy

Một **Web Application Firewall (WAF)** áp chính sách HTTP tại điểm xử lý request. Khi TLS terminate trước WAF hoặc tại WAF, nó có thể kiểm tra:

- HTTP method, path, query, headers, body theo hỗ trợ.
- Signatures và patterns của SQL injection/XSS hoặc hành vi đáng ngờ.
- API schema/JSON validation khi cấu hình, rate limits và bot rules.
- Session/identity context được các hệ thống tin cậy cung cấp.

Nếu TLS **passthrough xuyên qua vị trí WAF** mà không có thành phần giải mã phù hợp, WAF ở vị trí đó **không đọc được HTTP payload**. Có thể đặt WAF **tại backend ingress sau khi TLS được terminate**, nhưng đó là **điểm thực thi khác**, cần đánh giá latency/coverage và quyền quản trị tương ứng.

**WAF không bảo đảm chặn mọi hành vi nguy hiểm**, nhất là lỗi authorization nghiệp vụ, IDOR/BOLA, SSRF tại backend, logic giao dịch hoặc traffic không đi qua WAF. Phải giữ authn/authz, input validation và controls ở ứng dụng.

### 13.2. Firewall và IDS/IPS bên ngoài TLS

Trong passthrough, thiết bị mạng vẫn có thể kiểm soát **IP, port, connection rate, traffic volume và TLS metadata quan sát được**. NIDS/IPS có thể dùng thông tin flow, TLS handshake fingerprints và anomaly detection theo sản phẩm, nhưng không kiểm tra plaintext HTTP không được giải mã.

Trong termination, edge có thể tạo **HTTP/WAF logs** đầy đủ hơn; tuy nhiên sensor nằm trên đoạn **client→edge** vẫn thường thấy **ciphertext**, còn sensor ở đoạn **edge→backend HTTP** có thể thấy plaintext nếu nó được đặt ở vùng cho phép. Nếu có TLS bridging, sensor mạng phía sau edge cũng thấy ciphertext trừ khi có log/visibility từ endpoint.

Do đó, để xây dựng **IDS/IPS + SIEM correlation**, cần biết **sensor nằm trước hay sau TLS termination**, tuyến traffic nào bị bypass và việc đặt sensor có phù hợp quyền riêng tư/compliance không.

### 13.3. Bảo vệ origin khỏi truy cập bỏ qua edge

Một kiến trúc không an toàn thường gặp:

~~~text
Client Internet -> CDN/WAF -> origin API
                   (có WAF)

Client Internet ------------> origin API public IP
                   (bypass WAF)
~~~

Nếu origin có IP public/cổng mở và chỉ dựa vào HTTP header “đây là request qua CDN”, một client có thể thử kết nối trực tiếp, gửi header giống CDN và tránh WAF. Phòng vệ:

1. Giới hạn network reachability tới origin bằng **firewall/security groups/ACL/private link** theo khả năng.
2. Xác thực **identity của edge/proxy** ở hop tới origin, ví dụ mTLS hoặc cơ chế được nhà cung cấp hỗ trợ.
3. Không tin **X-Forwarded-For/Host/Proto hoặc client-cert header** từ nguồn chưa xác thực.
4. Đặt backend authorization độc lập ngay cả khi route đi qua WAF.
5. Theo dõi **direct-origin attempts** và thay đổi DNS/route/network policies.

Một allowlist theo IP CDN chỉ hiệu quả khi **danh sách IP và tính chất origin access** được quản lý đúng; nếu dải IP dùng chung cho nhiều khách hàng, cần **xác thực bổ sung** theo mô hình nhà cung cấp.

### 13.4. Host confusion, SSRF và request smuggling

Khi L7 proxy terminate TLS và chuyển HTTP tới backend, nó có thể tạo ra lỗ hổng nếu **proxy và backend diễn giải HTTP không nhất quán**:

- **Host-header injection:** dùng Host/authority do client cung cấp để tạo redirect, reset link hoặc chọn tenant mà không allowlist.
- **HTTP request smuggling/desync:** các hop không thống nhất ranh giới request, Content-Length/Transfer-Encoding hoặc HTTP/2→HTTP/1.1 translation.
- **SSRF qua proxy route:** client điều khiển upstream URL hoặc internal host mà proxy chấp nhận làm đích.
- **Forwarded header spoof:** backend tin IP/identity/scheme do client tự khai.
- **Path normalization mismatch:** proxy và backend chuẩn hóa percent-encoding, dot segments, duplicate slashes khác nhau.
- **Cache poisoning:** cache key không bao gồm đúng Host/headers/identity hoặc cache dữ liệu riêng tư.

**Kiểm soát theo thiết kế**: allowlist backend origins/vhosts, chuẩn hóa HTTP nhất quán, giới hạn header/body, tránh dynamic upstream từ input chưa xác thực, dùng trusted forwarding metadata và kiểm thử các tình huống mâu thuẫn protocol bằng môi trường được cấp quyền.

### 13.5. DDoS và hiệu năng TLS handshake

TLS termination phải xử lý **CPU cho handshake, certificate operations, connection state, request parsing và WAF rules**. Những đợt kết nối mới lớn có thể gây quá tải dù mỗi client chưa gửi request HTTP.

Biện pháp tùy nền tảng:

- Edge capacity, connection admission/rate limiting và SYN protection ở tầng phù hợp.
- TLS 1.3, session resumption được quản lý an toàn, keep-alive/HTTP/2 pooling.
- WAF/API rate limits theo route/identity đã xác thực sau termination.
- L4 controls trước TLS cho transport-level flood.
- Backpressure, max connections, queues và thời gian chờ phù hợp.
- Monitoring **full/resumed handshakes, handshake failures, TCP resets, CPU, p95/p99**.

**Không bật 0-RTT đại trà để chống DDoS**: early data vẫn cần xử lý và có replay risk; nó không thay connection admission controls.

### 13.6. Mạng nội bộ và phân đoạn

Backend dùng IP private không có nghĩa mọi workload trong VPC đều được phép truy cập. Thiết kế:

~~~text
Internet client
   |
Edge WAF/VIP: only TCP/443 (và UDP/443 nếu hỗ trợ HTTP/3)
   |
Edge -> API backends: chỉ port TLS/HTTP được duyệt
   |
API -> Database: chỉ identity/port/flow cần thiết
   |
Management network: admin APIs, TLS secrets, logging riêng
~~~

Các hệ thống phải có **security group/firewall/NetworkPolicy, identity/authorization và audit** phù hợp. Nếu passthrough, backend tự bảo vệ HTTP và peer TLS; nếu bridging, proxy phải chứng thực backend; nếu offloading plaintext, rủi ro truy cập network/host phải được chấp nhận rõ.

## 14. Triển khai trên cloud, Kubernetes và service mesh

### 14.1. Phân biệt lớp dịch vụ thay vì dựa vào tên sản phẩm

Trong các nền tảng cloud, các tên như **application load balancer, network load balancer, application gateway, ingress proxy, edge front door** gợi ý về tính năng, nhưng **không đủ để suy chế độ TLS thực tế**. Một network LB có thể có TLS listener hoặc chỉ TCP passthrough tùy nhà cung cấp và loại target. Một application LB thường hỗ trợ HTTPS termination và HTTP-aware routing, nhưng khả năng TLS re-encryption, mTLS và HTTP/3 lại khác nhau.

| Nhóm dịch vụ | Mô hình có thể gặp | Điểm bắt buộc phải xác minh |
| --- | --- | --- |
| Cloud **L7 application LB** | Client TLS termination, HTTP routing, có thể HTTPS target | Có verify backend certificate/SAN không? Có mTLS/HTTP2/gRPC/QUIC không? |
| Cloud **L4 network LB** | TCP/UDP passthrough, NAT/DSR hoặc TLS listener tùy dịch vụ | TLS thật sự kết thúc ở LB hay target? Source-IP preservation và PROXY protocol? |
| CDN / managed WAF | Client TLS termination, L7 WAF, TLS tới origin | Origin network restrictions, origin certificate/mTLS, key scope và logging |
| Managed API gateway | TLS termination, authn/authz và API routing | Backend TLS, request/header normalization, quotas và identity propagation |
| Kubernetes Ingress Controller | HTTP(S) reverse proxy, TLS termination ở ingress phổ biến | TLS Secret/reference, IngressClass/controller behavior, upstream scheme |
| Kubernetes Service type LoadBalancer | L4 network exposure theo cloud integration | Không mặc định Kubernetes Service tự kết thúc TLS |
| Kubernetes Gateway API implementation | Gateway/listeners/HTTPRoute hoặc TLSRoute theo hỗ trợ | TLS mode, certificates, route attachment, feature support của controller |
| Service mesh gateway/sidecar | TLS termination, mTLS origination hoặc passthrough theo mesh | Sidecar identity, trust domain, certificate rotation, authorization |

**Ví dụ khái niệm:** ở AWS có các loại Application Load Balancer và Network Load Balancer với đặc tính khác nhau; ở Azure có Application Gateway/Front Door và Load Balancer; ở Google Cloud có nhiều loại application/network load balancers. Không sao chép cấu hình từ một loại vào loại khác chỉ vì đều là “load balancer”. Phiên bản, vùng, listener, target group và kiểu backend phải được kiểm tra theo môi trường vận hành.

### 14.2. Kubernetes Ingress và TLS Secret

Một cấu hình Kubernetes Ingress điển hình cho HTTPS termination có thể khai báo:

~~~yaml
# CẤU TRÚC MINH HỌA, không phải manifest được phép triển khai ngay.
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: orders-https
  namespace: orders
spec:
  ingressClassName: approved-ingress-class
  tls:
    - hosts:
        - api.example.test
      secretName: api-example-test-tls
  rules:
    - host: api.example.test
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: orders-service
                port:
                  number: 8080
~~~

**Ý nghĩa:** trong nhiều Ingress controllers, controller đọc certificate/key từ Secret phù hợp, terminate TLS và chuyển HTTP tới Service port 8080. Nhưng **Ingress API không tự bảo đảm mTLS, upstream HTTPS verification hay mọi security headers**; chúng phụ thuộc **IngressClass, controller implementation và policy**.

Đặc biệt:

- Secret chứa private key phải được bảo vệ bằng **Kubernetes RBAC, encryption at rest theo nền tảng, namespace controls và secret management**; tránh copy vào Git.
- Một namespace hoặc service account không nên tự được phép đọc Secret TLS production của namespace/tenant khác.
- Nếu muốn **TLS tới pod/backend**, cần cấu hình **HTTPS upstream/mTLS** theo controller hoặc Gateway/mesh hỗ trợ; không suy từ việc khai báo TLS cho ingress.
- Cấu hình **passthrough** không phải tính năng được bảo đảm bởi mọi Ingress implementation/API thông thường; một số controllers dùng extension/CRD hoặc Gateway API mode riêng.
- Service type **LoadBalancer** có thể tạo VIP external nhưng không tự động mang lại HTTP WAF hoặc certificate verification.

### 14.3. Gateway API và route delegation

Trong Gateway API, một **Gateway** có listeners và các **Routes** đi kèm. Theo controller/phiên bản hỗ trợ, HTTPS listener có thể terminate TLS rồi dùng HTTPRoute để route ở L7; TLS passthrough có thể dùng **TLSRoute** hoặc một khả năng tương đương của implementation.

Cần kiểm tra:

1. **Listener protocol/TLS mode** thực sự là terminate hay passthrough.
2. Route nào được phép **attach** vào listener, theo namespace policy và route admission.
3. **CertificateRefs** thuộc namespace/Secret nào và quyền tham chiếu cross-namespace nếu được hỗ trợ.
4. SNI/hostname matching, unknown hosts và conflict resolution giữa routes.
5. BackendRefs, TLS policy/BackendTLSPolicy hoặc cơ chế xác minh backend được implementation hỗ trợ.
6. Cách Controller báo **Accepted, ResolvedRefs, Programmed** hoặc các trạng thái hiệu lực tương đương.

Không đồng nhất **“Gateway API đã chấp nhận YAML”** với **“network dataplane đã áp backend TLS verification và isolation đúng”**. Cần kiểm tra cấu hình thực tế do controller tạo và phép thử TLS/API đầu-cuối.

### 14.4. Service mesh và workload identity

Trong mesh, traffic có thể đi:

~~~text
Client
  -> External Gateway (TLS A, edge policy)
  -> Ingress/sidecar (mTLS B)
  -> Orders sidecar (mTLS C)
  -> Orders process (HTTP localhost hoặc một TLS hop khác)
~~~

Mỗi điểm kết thúc TLS **định nghĩa một trust boundary**. Workload certificate có thể mang danh tính service/namespace/trust domain; authorization ở mesh nên được thiết kế theo principal/service, không chỉ IP. Nhưng:

- NetworkPolicy vẫn cần khi mục tiêu là hạn chế reachability/egress.
- Proxy sidecar không tự bảo vệ dữ liệu trong process khi application bị xâm nhập.
- Chứng chỉ workload có lifecycle và rotation riêng so với certificate public client-facing.
- Nếu sidecar terminate mTLS và gửi plaintext vào local process, phải kiểm soát host/pod security và trust boundary tương ứng.
- Những kết nối bypass sidecar hoặc ports không thuộc mesh policy có thể không được kiểm tra theo cùng một tiêu chuẩn.

### 14.5. Multi-cluster và multi-region

Một application gateway ở Region A có thể terminate TLS rồi chuyển tới backend Region B. Khi có traffic cross-region:

- **Chặng nội bộ dài hơn** và có nhiều miền quản trị, nên không coi plaintext backend là “nội bộ an toàn” chỉ vì cùng tổ chức.
- DNS private zone/peering/VPN route và firewall phải được kiểm tra cho các backend IP thực.
- Certificate SAN/CA ở backend Region B phải hợp lệ với proxy Region A, đặc biệt khi failover.
- TLS session resumption state ở edge và upstream có thể đổi khi LB chọn node/region khác.
- Health check cần phân biệt **region unavailable** với **backend TLS invalid**.
- Ngăn share key giữa tenants/clusters vượt phạm vi cho phép chỉ để tăng resumption hit rate.

**Một cloud health check pass không thay cho phép thử application/TLS từ vùng client thật**, đặc biệt khi có split DNS, WAF, header routing hoặc SNI virtual hosting.

### 14.6. Nhiều miền tin cậy và mô hình Zero Trust

Nếu tổ chức áp dụng Zero Trust, không đủ kết luận “nội bộ VPC thì tin cậy”. Nên:

1. Xác thực danh tính của **mỗi hop** phù hợp.
2. Cấp quyền truy cập theo **service identity, user identity và resource policy**.
3. Giới hạn backend networks chỉ cho traffic từ gateways được phép.
4. Giám sát thay đổi TLS secret/certificate và proxy routes.
5. Đưa WAF/authorization vào đúng điểm plaintext được phép.
6. Phân tách production/staging, tenants và trust domains trong key/route policy.

## 15. Cấu hình minh họa: NGINX termination + re-encryption và stream passthrough

Mục này cung cấp **mẫu học tập** để thấy rõ vị trí những cài đặt cần thiết. Chúng là **hai cấu hình thay thế nhau** trên cùng listener TCP/443, không phải hai block có thể chạy song song cùng IP:port. **Không dùng nguyên mẫu trong production**: cần bổ sung rate limiting, monitoring, timeout, CA/certificate lifecycle, config validation, trusted ingress, policy mTLS và version-specific syntax.

### 15.1. L7 HTTPS termination + HTTPS upstream

Ví dụ máy chạy NGINX hỗ trợ HTTP/TLS proxying. Trong mạng lab, backend ở 10.20.10.11:8443 với certificate SAN **orders.internal.example.test** được CA nội bộ đã tin cậy ký.

~~~nginx
# MINH HỌA: phần cấu hình thuộc ngữ cảnh http { ... } của NGINX.
upstream orders_pool {
    server 10.20.10.11:8443;
    server 10.20.10.12:8443;
    keepalive 32;
}

server {
    listen 443 ssl;
    server_name api.example.test;

    ssl_certificate     /etc/nginx/tls/api.crt;
    ssl_certificate_key /etc/nginx/tls/api.key;
    ssl_protocols TLSv1.2 TLSv1.3;

    location / {
        proxy_pass https://orders_pool;

        # TLS B: proxy xác minh đúng backend hostname + CA.
        proxy_ssl_server_name on;
        proxy_ssl_name orders.internal.example.test;
        proxy_ssl_verify on;
        proxy_ssl_trusted_certificate /etc/nginx/pki/backend-ca.pem;
        proxy_ssl_verify_depth 3;

        # Edge trực tiếp nhận client, overwrite các metadata đã biết.
        # Nếu có CDN phía trước, phải thiết kế lại trusted proxy chain.
        proxy_set_header Host api.example.test;
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_set_header X-Request-ID $request_id;

        proxy_http_version 1.1;
        proxy_set_header Connection "";
    }
}
~~~

**Đọc cấu hình:**

- **listen 443 ssl** làm NGINX kết thúc TLS A.
- **proxy_pass https://orders_pool** mở kết nối TLS B tới backend, **không phải passthrough**.
- **proxy_ssl_server_name on** và **proxy_ssl_name** chọn SNI/hostname phía backend; **proxy_ssl_verify on** cùng CA đáng tin là điều kiện xác minh.
- **proxy_set_header X-Forwarded-For $remote_addr** thay XFF mà client gửi, phù hợp mô hình NGINX là edge đầu tiên nhận trực tiếp từ client; **không giữ nguyên source IP gốc của CDN nếu CDN đứng trước**. Khi có CDN, phải xác thực CDN peer và cấu hình real-IP/trusted chain đúng.
- **proxy_http_version 1.1** là lựa chọn minh họa cho HTTP upstream; **không được dùng như cấu hình gRPC upstream**, vì gRPC có đường proxying/HTTP2 khác.
- Mẫu chưa trình bày WAF, HSTS, default server, body limits, timeout, DNS resolver, upstream mTLS certificate, active health checks hoặc error pages.

Nếu backend dùng **mTLS B**, cần thêm chứng chỉ client dành cho NGINX và cấu hình CA/policy tại backend theo sản phẩm; **certificate của NGINX không đại diện cho certificate client bên ngoài**.

**Quan trọng:** NGINX bản OSS/Plus, module, runtime và version có thể khác nhau về health checks, HTTP/2 upstream hoặc tính năng TLS. Chỉ áp dụng cấu hình có **syntax check và thử behavior** trên đúng bản được quản trị.

### 15.2. L4 TCP TLS passthrough dựa SNI

Ví dụ NGINX **stream** với module **ssl_preread** được build/bật theo cấu hình nền tảng:

~~~nginx
# MINH HỌA: phần cấu hình thuộc ngữ cảnh stream { ... }.
map $ssl_preread_server_name $tls_upstream {
    api.example.test 10.20.10.11:8443;
    default          127.0.0.1:9;  # không route tới backend nhạy cảm
}

server {
    listen 443;
    ssl_preread on;
    proxy_connect_timeout 5s;
    proxy_timeout 120s;
    proxy_pass $tls_upstream;
}
~~~

**Ý nghĩa:**

- Không có chỉ thị listen ssl, không chỉ định server certificate/private key ở NGINX stream listener; chính backend **10.20.10.11:8443** trình certificate cho **api.example.test**.
- **ssl_preread** chỉ đọc metadata phù hợp từ ClientHello khi còn hiện rõ, **không giải mã HTTP**.
- Unknown SNI được gửi đến local port không có dịch vụ trong lab để fail connection; production nên thiết kế **explicit reject/default policy** theo hỗ trợ và giám sát hiệu quả.
- Nếu backend certificate là **orders.internal.example.test** mà client muốn **api.example.test**, handshake **không tự đúng**: backend phải có certificate hợp lệ cho tên **api.example.test** hoặc một cơ chế TLS routing/virtual hosting tương ứng.
- Với ECH, ClientHelloOuter có thể không chứa SNI thực; **SNI preread routing không bảo đảm chọn được backend đích**.
- TCP connection đến backend không nhất thiết giữ source IP client; cần kiểm tra SNAT/PROXY protocol và backend listener.

Hai ví dụ đều dùng **TCP/443**; để phục vụ HTTP/3/QUIC cần thiết kế riêng **UDP/443**, không thêm một tham số TCP vào NGINX stream rồi coi như đã hỗ trợ QUIC.

### 15.3. PROXY protocol: bên gửi và bên nhận phải đồng bộ

Nếu muốn LB gửi PROXY protocol tới backend TLS:

~~~text
L4 LB:
  proxy_protocol = enabled, chỉ gửi đến trusted backend

Backend TCP listener:
  expect_proxy_protocol = enabled
  parse PROXY header BEFORE TLS record handling
  accept ONLY from approved LB peers

Firewall:
  backend port reachable only from trusted LB source identities/networks
~~~

Đây là **pseudo-configuration**, không phải cú pháp áp vào một sản phẩm cụ thể. Khi bên gửi không bật mà bên nhận bật, hoặc ngược lại, **TLS handshake thường lỗi**. Nếu backend mở listener PROXY protocol trực tiếp cho client không được cấp quyền, client có thể tự khai IP giả.

### 15.4. Policy YAML mô tả ý định bảo mật

~~~yaml
# Ý định thiết kế, KHÔNG phải manifest cho cloud/NGINX/HAProxy.
service: orders-api
public_host: api.example.test
client_transport: HTTPS-over-TCP
tls_mode: bridging
front_end:
  tls_versions: [TLSv1.3, TLSv1.2]
  server_certificate_owner: edge-security
  mTLS_client_auth: required_for_partner_routes
  waf: enabled
  trusted_http_forwarders: approved_only
back_end:
  endpoints:
    - 10.20.10.11:8443
    - 10.20.10.12:8443
  protocol: HTTPS
  hostname_to_verify: orders.internal.example.test
  ca_bundle: internal-service-ca
  verify_server_certificate: true
  mTLS_proxy_identity: edge-orders-service
  access_policy: edge_only
  health_check: HTTPS-with-hostname-validation-and-app-readiness
traffic:
  algorithm: least_requests
  connection_drain: reviewed_for_websocket_and_grpc
  fallback_on_tls_verification_failure: deny_upstream
monitoring:
  distinguish_downstream_tls_and_upstream_tls: true
  report_unexpected_sni_and_certificate_expiry: true
  do_not_log_secrets: true
~~~

Khi chuyển ý định này sang sản phẩm thật, các chức năng như **per-route mTLS, least requests, active HTTPS health checks hoặc upstream validation** có thể thiếu hoặc cần license/feature khác. Không thay chúng bằng “verify none” hoặc bỏ qua policy mà không báo giới hạn kiến trúc.

## 16. Bài lab có kiểm soát: chứng minh điểm kết thúc TLS

**Mục tiêu:** phân biệt certificate client nhìn thấy với certificate origin, quan sát TLS A/TLS B, thử passthrough với SNI, kiểm tra unknown host và phân tích metadata client IP. Chỉ dùng localhost hoặc mạng lab mà người học có quyền; không thu packet của người khác hoặc gửi request thử vào ứng dụng production.

### 16.1. Mô hình giả định

| Thành phần | Endpoint lab | Certificate theo vai trò |
| --- | --- | --- |
| Client giả lập | localhost | Tin CA của lab hoặc certificate test được chỉ định |
| Edge HTTPS proxy | 127.0.0.1:443 (hoặc port lab khác) | SAN: api.example.test |
| Backend Orders TLS | 10.20.10.11:8443 | SAN: orders.internal.example.test (bridging) hoặc api.example.test (passthrough) |
| Backend dự phòng | 10.20.10.12:8443 | Certificate tương ứng với mode |
| WAF/L7 policy | Chạy tại edge termination | Có thể thấy HTTP sau TLS A |
| Client origin identity | Certificate/mTLS lab nếu chọn thử | Chỉ được tin khi đã được xác minh |
| Monitoring | Proxy/backend logs | TLS handshake, SNI, verified peer, backend và HTTP code khi có |

**Cùng tên service không bắt buộc cùng certificate trên tất cả hops**, nhưng certificate từng hop phải hợp lệ cho tên được peer kiểm tra. Trong passthrough, client thấy certificate **của backend**; trong bridging, client thấy certificate **của proxy**.

### 16.2. Chuẩn bị certificate thử nghiệm

Trên máy lab Linux/macOS hoặc shell hỗ trợ OpenSSL:

~~~bash
umask 077
mkdir -p "$HOME/tls-proxy-lab"
cd "$HOME/tls-proxy-lab"
chmod 700 .

# Chứng chỉ tự ký chỉ dùng trong bài lab.
openssl req -x509 -newkey rsa:2048 -nodes \
  -keyout edge.key -out edge.crt -days 1 \
  -subj "/CN=api.example.test" \
  -addext "subjectAltName=DNS:api.example.test"

openssl req -x509 -newkey rsa:2048 -nodes \
  -keyout backend.key -out backend.crt -days 1 \
  -subj "/CN=orders.internal.example.test" \
  -addext "subjectAltName=DNS:orders.internal.example.test"
~~~

Mỗi certificate tự ký trong lab được **tin riêng bằng -CAfile hoặc --cacert**, không dùng tùy chọn vô hiệu kiểm tra TLS. Nếu muốn dùng PKI nội bộ gần thực tế hơn, có thể lập CA lab và ký chứng chỉ cho hai names; bảo vệ CA key và không commit files key/cert nhạy cảm vào Git.

Hai certificates trong ví dụ phục vụ **bridging**. Để chạy passthrough cho hostname api.example.test, **backend phải có certificate hợp lệ cho api.example.test**, không thể dùng backend.crt chỉ có SAN orders.internal.example.test.

### 16.3. Thử backend TLS trực tiếp

Nếu backend lab được khởi động bằng TLS server trên loopback/port 8443:

~~~bash
# Terminal A: chỉ lắng nghe loopback trong lab.
openssl s_server \
  -accept 127.0.0.1:8443 \
  -cert backend.crt -key backend.key \
  -tls1_3 -www
~~~

Terminal B test với hostname backend thực:

~~~bash
openssl s_client \
  -connect 127.0.0.1:8443 \
  -servername orders.internal.example.test \
  -verify_hostname orders.internal.example.test \
  -verify_return_error \
  -CAfile backend.crt -brief
~~~

**Kỳ vọng:** certificate trust và hostname verification thành công theo CA file lab; nếu yêu cầu kiểm tra api.example.test trên certificate này thì **phải thất bại** về hostname. Không dùng tham số tắt verification để che lỗi tên. Cú pháp option khác nhau theo OpenSSL version; đọc trợ giúp bản cài thực nếu cần điều chỉnh.

### 16.4. Thử client-facing TLS sau termination

Khi proxy lab được cấu hình TLS termination cho api.example.test, dùng lệnh gửi **SNI và HTTP Host đúng** dù DNS không trỏ hostname vào localhost:

~~~bash
curl --resolve api.example.test:443:127.0.0.1 \
  --cacert edge.crt \
  --head --verbose \
  https://api.example.test/
~~~

Xác minh:

1. Client thấy certificate **edge.crt**, SAN chứa api.example.test.
2. HTTPS handshake với proxy thành công; không bỏ qua CA/hostname verification.
3. Proxy có HTTP access log tương ứng với request.
4. Nếu bridging, proxy mở TLS B và **phải xác minh** backend certificate.
5. Backend có thể thấy TLS peer là proxy, nhưng **không tự nhận certificate client gốc** chỉ qua TLS B.
6. Nếu backend không đáp ứng, proxy có thể trả 502/503/504 tùy sản phẩm trong khi TLS A vẫn thành công.

**Nếu chỉ curl tới edge và nhận HTTP 200, chưa chứng minh upstream TLS verification bật.** Cần negative test certificate sai hoặc xem cấu hình/log TLS B.

### 16.5. Phân biệt passthrough

Chạy **cấu hình L4 TCP passthrough thay thế**, không đồng thời chiếm listener TCP/443 của L7 termination. Backend lab cần certificate **api.example.test**:

~~~bash
openssl s_client \
  -connect 127.0.0.1:443 \
  -servername api.example.test \
  -verify_hostname api.example.test \
  -CAfile passthrough-backend-api.crt \
  -brief
~~~

File passthrough-backend-api.crt ở đây **là đầu vào giả định** được tạo trong lab với SAN api.example.test. **Kỳ vọng:** client thấy certificate do backend trình; L4 LB không ghi HTTP path/body, nhưng có thể ghi TCP flow và hostname SNI nếu module hỗ trợ. Backend nhận TLS ClientHello và xử lý certificate/mTLS trực tiếp.

### 16.6. Unknown SNI phải fail closed theo policy

~~~bash
openssl s_client \
  -connect 127.0.0.1:443 \
  -servername unknown.example.test \
  -brief
~~~

Ở mode **passthrough SNI routing**, unknown hostname **không được tự chuyển vào backend quản trị hoặc tenant khác**. Kết nối có thể bị từ chối theo cấu hình lab; ghi log quyết định route. Ở mode **L7 termination**, default virtual host cũng phải có policy rõ, không route theo Host bất kỳ.

### 16.7. Test client IP/header spoofing trong lab

Khi edge trực tiếp nhận client và đã cấu hình **thay X-Forwarded-For**, một phép thử vô hại có thể gửi header giả:

~~~bash
curl --resolve api.example.test:443:127.0.0.1 \
  --cacert edge.crt \
  -H "X-Forwarded-For: 192.0.2.200" \
  -H "X-Forwarded-Proto: http" \
  -H "X-Authenticated-Client: forged-lab" \
  https://api.example.test/debug/request-metadata
~~~

Endpoint **/debug/request-metadata** chỉ là **service mock lab** do người học tự tạo, không mở trên production. Phải xác minh:

- Backend **không coi 192.0.2.200 là client IP đáng tin** nếu edge là hop đầu tiên và đã override XFF.
- Backend không chấp nhận chuỗi **forged-lab** như danh tính mTLS đã xác thực.
- Scheme external là HTTPS theo proxy policy, không bị client ghi đè thành HTTP.
- Debug endpoint không log credential/secret/địa chỉ riêng tư quá mức.

Một số framework tự đọc forwarded headers; cần cấu hình trusted proxies ở ứng dụng. Override tại edge chưa đủ nếu còn đường bypass khác.

### 16.8. Test backend certificate verification

Cho backend lab trình certificate **không chứa SAN orders.internal.example.test** hoặc do CA khác không được proxy tin, rồi gọi edge:

~~~text
Client TLS A:
    Edge certificate api.example.test: hợp lệ.

Proxy TLS B:
    Backend certificate orders.internal.example.test: KHÔNG HỢP LỆ
    vì sai SAN hoặc CA.

Kỳ vọng:
    Proxy KHÔNG gửi HTTP request vào backend trái danh tính.
    Proxy báo upstream TLS verification failure.
    Client có thể nhận 502/503/5xx theo proxy, không nhận
    200 từ một backend chưa xác thực.
~~~

**Không chữa negative test bằng cách tắt verify**. Sửa SAN/CA/SNI và quản lý vòng đời certificate. Nếu proxy vẫn trả HTTP 200 với backend certificate sai, kiểm tra có thật sự đi qua backend đã đổi hay proxy đang không verify.

### 16.9. Ma trận thử nghiệm allow/deny

| ID | Tình huống | Kỳ vọng | Chứng cứ |
| --- | --- | --- | --- |
| L01 | Client TLS hợp lệ vào edge termination | TLS A thành công | Edge certificate SAN, TLS version/cipher |
| L02 | Client vào passthrough | Backend certificate xuất hiện trực tiếp | Client TLS trace và backend handshake log |
| L03 | Bridging với backend cert hợp lệ | TLS B được xác minh, HTTP trả theo app | Proxy verify logs, backend request |
| L04 | Bridging với backend SAN sai | **Không cho upstream request thành công** | TLS verify error tại proxy, 5xx phù hợp |
| L05 | Bridging với CA không đáng tin | Reject backend peer | Verify chain error, no backend processing |
| L06 | L4 unknown SNI | Fail closed, không route backend nhạy cảm | Route log và backend access count |
| L07 | Client giả XFF/XFP | Edge loại bỏ/overwrite theo policy | Backend metadata khác giá trị giả |
| L08 | Client giả mTLS identity header | Không được xem là authenticated principal | Header stripping và app deny |
| L09 | HTTP/2 client, HTTP/1.1 upstream | Chỉ khi proxy hỗ trợ, semantics đúng | ALPN và backend logs |
| L10 | gRPC qua L7 | H2/trailers/stream hoạt động | gRPC status/deadlines |
| L11 | Client mTLS hợp lệ/không hợp lệ | Allow/deny đúng ở TLS endpoint có trách nhiệm | Certificate verification và authorization |
| L12 | Backend TCP listener mở nhưng app chưa sẵn sàng | Health readiness không đánh dấu sai | App/synthetic check và backend selector |
| L13 | Backend failover, draining | Kết nối mới chuyển healthy node, stream cũ kết thúc theo policy | Connection/stream counts, error rate |
| L14 | PROXY protocol mismatch lab | Handshake fail được phân loại đúng | Backend parser/log và LB config |
| L15 | Ticket sau key rotation | Full handshake fallback vẫn đúng | Full/resumed metrics và TLS success |
| L16 | UDP/443 blocked | HTTP/3 fallback theo client policy; TCP/443 vẫn hoạt động | QUIC/TCP logs |
| L17 | Edge HTTPS OK nhưng origin certificate sai | Cảnh báo TLS B, không bỏ verify | Edge/origin per-hop metrics |
| L18 | ECH hoặc SNI ẩn theo khả năng lab | Ghi nhận giới hạn SNI-preread | Effective route và policy hỗ trợ |
| L19 | Direct origin request ngoài edge | Bị chặn bằng network/identity policy | SG/ACL, origin access logs |
| L20 | Unauthorized network tới backend | Bị deny dù biết private IP | Firewall/NetworkPolicy counters |

**Lưu ý:** L14, L16 và L18 chỉ thực hiện nếu lab hỗ trợ, không tạo tình huống gây gián đoạn trên mạng chung. Mỗi test ghi **timestamp, nguồn, TLS endpoint, certificate, kết quả kỳ vọng, quan sát thực tế và sai khác**.

## 17. Troubleshooting: xác định lỗi thuộc TLS A, TLS B, L4 hay ứng dụng

### 17.1. Đừng bắt đầu bằng câu hỏi “SSL có lỗi không?”

Khi client báo lỗi HTTPS, hãy xác minh **đường đi, vị trí TLS termination và thời điểm lỗi**:

1. Client đang dùng **DNS** nào và kết nối đến **VIP/IP nào**?
2. Client dùng **TCP/443 hay UDP/443 (HTTP/3)**?
3. TLS thực sự terminate ở **edge hay backend**?
4. Client có gửi **SNI, ALPN** đúng và endpoint trình certificate cho hostname nào?
5. Trong bridging, **TLS B tới backend** có được xác minh CA/SAN và có route/firewall đúng không?
6. Sau handshake, lỗi xảy ra ở **HTTP parser, WAF, auth, route, health check hay backend**?
7. Có sự khác nhau giữa các node, regions, SNI hosts, TLS versions và request types không?

Một packet capture thụ động bên ngoài TLS termination thường không thấy HTTP body. Ưu tiên kết hợp **TLS termination logs**, proxy access/error logs, health check status, flow logs và application logs.

### 17.2. Sơ đồ quyết định điều tra

~~~mermaid
flowchart TD
  A["Client lỗi HTTPS / TLS / 5xx"] --> B{"DNS và transport tới VIP đúng?"}
  B -- "Không" --> B1["Kiểm tra DNS, route, firewall,\nNAT, TCP/UDP, QUIC fallback"]
  B -- "Có" --> C{"TLS A / client-facing TLS hợp lệ?"}
  C -- "Không" --> C1["Kiểm tra SNI, certificate SAN/CA,\nTLS versions, ALPN, mTLS"]
  C -- "Có" --> D{"Đang termination/bridging hay passthrough?"}
  D -- "Termination / bridging" --> E{"Proxy chọn đúng HTTP route/backend?"}
  E -- "Không" --> E1["Host, path, trusted headers,\nWAF policy và route rules"]
  E -- "Có" --> F{"Upstream TLS B hoặc backend HTTP có hoạt động?"}
  F -- "Không" --> F1["Backend CA/SAN/SNI, health,\nnetwork, mTLS B và timeouts"]
  F -- "Có" --> G["Kiểm tra application auth,\nHTTP status, database và SLO"]
  D -- "Passthrough" --> H{"SNI route và backend TLS hợp lệ?"}
  H -- "Không" --> H1["SNI/ECH, backend cert,\nPROXY header, backend listener"]
  H -- "Có" --> I["Kiểm tra backend application\nvà connection/stream state"]
~~~

**Nếu client TLS A thành công và nhận HTTP 502**, đừng lập tức kết luận lỗi server certificate của client. Rất có thể **edge đã nhận HTTPS thành công** nhưng bị lỗi khi chọn/upstream tới backend, trong đó có lỗi xác minh certificate TLS B.

### 17.3. Ma trận triệu chứng và nguyên nhân

| Triệu chứng | Nguyên nhân thường gặp | Kiểm tra ưu tiên |
| --- | --- | --- |
| Client certificate hostname mismatch | SNI đi sai virtual host, backend cert sai SAN trong passthrough, DNS/VIP sai | Certificate client thấy, SNI, backend selected |
| TLS handshake timeout trước HTTP | Firewall/route/NAT, TLS mode mismatch, backend listener lỗi | TCP/QUIC flow, TLS ClientHello và response, route |
| Proxy trả 502 Bad Gateway | Backend TLS verification fail, port/protocol mismatch, upstream reset | Proxy error log, backend TLS B, service readiness |
| Proxy trả 503 Service Unavailable | Pool không có healthy backend, circuit breaker hoặc quota policy | Upstream health list, readiness, capacity |
| Proxy trả 504 Gateway Timeout | Upstream chậm/không phản hồi, timeout hoặc network return path | Request trace, backend latency, firewall conntrack |
| HTTP redirect loop | Backend nghĩ request là HTTP, forwarded scheme không đáng tin/sai | X-Forwarded-Proto, trusted proxy config, redirect rules |
| Client IP đều thành IP của proxy | SNAT/TCP proxy, thiếu trusted XFF/PROXY | L4 topology, backend socket peer, forwarding config |
| Có thể giả XFF làm vượt IP allowlist | Backend tin header client gửi hoặc trực tiếp bypass edge | Header overwrite, trusted proxy list, origin ACL |
| Passthrough gửi TLS lỗi đầu tiên | LB bật PROXY protocol nhưng backend không parse, hoặc ngược lại | Bytes đầu luồng, proxy/backend listener config |
| Passthrough route nhầm backend | SNI không có, ECH, default route sai, ClientHello inspect timeout | SNI policy, unknown hosts, effective backend |
| gRPC lỗi dù HTTPS trang web thường chạy | ALPN h2, HTTP2 upstream, trailers, streaming/buffering | gRPC-specific proxy support, h2 hop B |
| WebSocket bị ngắt sau 60s | Idle timeout/proxy buffering/drain | Per-hop timeout, Upgrade/stream log |
| HTTP/3 không hoạt động nhưng H2 chạy | UDP/443 bị chặn, QUIC listener thiếu, LB không route CID | UDP flow, QUIC handshake, fallback policy |
| Full TLS A thành công nhưng origin 401/403 | Backend authn/authz khác với TLS validation | API gateway token/session, mTLS identity propagation |
| Backend mTLS từ chối proxy | Proxy không gửi client cert B, CA/subject policy sai | Upstream mTLS cert and trust, authentication logs |
| Một backend trả chứng chỉ sai sau deploy | Certificate/key rotation không đồng bộ trong pool | Per-node cert inspect, rollout and health |
| Certificate mới nhưng client vẫn thấy cũ | VIP route tới node cũ, reload chưa hoàn tất, client session resumption | Forced full handshake, per-node cert inventory |
| Backend ghi HTTP plaintext dù thiết kế yêu cầu TLS | Proxy pass nhầm http scheme, TLS B không bật | Effective upstream config, packet/endpoint logs |
| Connection count phân phối đều nhưng request rate lệch | HTTP/2/gRPC multiplexing, long-lived connections | Streams/request metrics và thuật toán L4/L7 |
| Nhiều 400 sau chuyển HTTP/2→H1 | Host/authority, Content-Length, Transfer-Encoding hoặc headers sai | Request normalization, proxy/backend parser |
| WAF không thấy request qua IP backend | Origin bypass hoặc traffic passthrough | Effective route, security group, WAF placement |

**Mã 502/503/504 phụ thuộc sản phẩm và cấu hình**; một TLS handshake từ client đôi khi bị reset trực tiếp thay vì nhận HTTP status. Dựa trên **evidence của từng hop**, không suy đoán nguyên nhân từ mã 5xx đơn lẻ.

### 17.4. Khi backend certificate fail

Giả sử:

~~~text
Client:
  TLS A tới api.example.test -> OK.

NGINX:
  proxy_pass tới 10.20.10.11:8443;
  SNI B = orders.internal.example.test;
  verify_hostname = orders.internal.example.test.

Backend:
  SAN = legacy.internal.example.test.

Result:
  TLS B verification FAIL.
  Client có thể thấy HTTP 502 hoặc proxy-specific upstream error.
~~~

Sửa đúng bằng **cấp chứng chỉ SAN phù hợp, chọn đúng SNI/CA hoặc route tới backend đúng**, không tắt verification. Đồng thời xác minh **chặng A vẫn hợp lệ**, vì có thể có hai lỗi certificate độc lập.

### 17.5. Khi upstream network fail nhưng DNS đúng

Client có thể phân giải đúng DNS tới VIP và thực hiện TLS A thành công, nhưng proxy không tạo được TCP/TLS B tới backend do:

- Private DNS zone của proxy khác nguồn client, trả IP cũ.
- VPC/VNet peering/VPN route không tới backend.
- Firewall/SG chặn proxy source IP hoặc backend port.
- NAT/connection tracking làm return path không phù hợp.
- Proxy backend pool chứa endpoint đã thay/thu hồi.
- Backend listener chưa sẵn sàng hoặc quá tải accept queue.

Để phân biệt, kiểm tra:

1. DNS query **từ proxy node** cho upstream hostname.
2. Route/flow của **proxy → backend**, không chỉ client → VIP.
3. TLS handshake trực tiếp tới backend trong phạm vi lab/production được cấp quyền, với **SNI và hostname validation thật**.
4. Backend readiness/health và error logs.
5. Trạng thái connection pool, pending requests và upstream timeouts.

### 17.6. Chứng chỉ proxy và backend có thời hạn khác nhau

Trong bridging, certificate edge hết hạn sẽ làm **client không tin** ngay ở TLS A, thường trước khi request đến WAF/backend. Ngược lại certificate backend hết hạn có thể làm proxy **từ chối TLS B** khi client vẫn kết nối HTTPS hợp lệ với edge.

Do đó monitoring phải có **hai chỉ số expiry**, hai bộ CA/certificate owners, và các synthetic tests cho từng hop. Một cảnh báo “TLS certificate sắp hết hạn” không đủ nếu thiếu hostname, endpoint, owner và vị trí trong đường traffic.

### 17.7. Kiểm tra PROXY protocol không làm hỏng TLS

Khi áp PROXY protocol vào một backend TLS, hãy thử cả:

- **Đường được phép** từ LB có header PROXY đúng version/format và backend parser đã bật.
- **Đường không được phép** từ một client trực tiếp: phải bị firewall/identity policy chặn trước khi backend có cơ hội tin header do client tự gửi.
- **Version mismatch** giữa v1/v2 nếu một bên không hỗ trợ.
- **IPv4/IPv6 và địa chỉ port** được ghi đúng trong backend log.
- **TLS SNI/certificate** vẫn đúng sau khi parser bóc header.

Không xem một header PROXY có IP “trông hợp lệ” là bằng chứng nguồn đã được xác thực nếu listener có thể truy cập từ ngoài LB.

## 18. Threat modeling: rủi ro đặc thù của termination và passthrough

### 18.1. Tài sản và ranh giới tin cậy

Các tài sản quan trọng:

1. **Public server certificate/private key** tại edge hoặc backend.
2. **Origin certificate, internal CA và mTLS proxy/workload credentials**.
3. **Đường dữ liệu plaintext** khi termination và proxy xử lý HTTP.
4. **Route table, SNI/Host/ALPN mapping** và pool backend.
5. **WAF/security policies, client identity propagation và trusted headers**.
6. **NAT, source IP mapping, PROXY protocol** và network access to origin.
7. **TLS session tickets, resumption keys, 0-RTT policy**.
8. **Observability, health checks, audit/config versions**.

### 18.2. Ma trận đe dọa

| ID | Tình huống | Điều kiện | Hậu quả | Kiểm soát / phép thử |
| --- | --- | --- | --- | --- |
| P-T01 | Proxy terminate TLS nhưng chặng B plaintext bị nghe lén | Workload/host/network nội bộ không đủ tin cậy | Lộ HTTP payload/credential | Re-encryption/mTLS, segmentation, hạn chế sniffing; kiểm chứng hop B |
| P-T02 | Proxy bật HTTPS upstream nhưng bỏ xác minh certificate | Upstream peer không đáng tin có thể nhận kết nối | MITM/đổi backend không phát hiện | CA + SAN/SNI verification, negative cert tests |
| P-T03 | L4 passthrough rơi unknown SNI vào admin backend | Default route quá rộng | Truy cập endpoint quản trị không mong muốn | Fail closed, backend network ACL, test SNI rỗng/lạ |
| P-T04 | ECH che true SNI | L4 route chỉ dựa SNI quan sát được | Không route đúng/gián đoạn | ECH-aware architecture, per-VIP route, capability tests |
| P-T05 | Header giả XFF/Proto/Identity | Backend tin metadata do client gửi | IP allowlist bypass, identity confusion, redirect sai | Strip/overwrite, trusted proxy list, authenticated upstream |
| P-T06 | Origin public accessible bypass WAF | Không có ingress ACL/mTLS | Request tránh kiểm soát L7 | Origin restriction, mTLS, direct-origin negative test |
| P-T07 | PROXY protocol exposed to untrusted clients | Backend tin header trước TLS không kiểm tra nguồn | Spoof client IP/port, policy sai | Backend chỉ nhận LB tin cậy, correct parser |
| P-T08 | Cross-tenant certificate/key sharing | RBAC/secret scopes quá rộng | Một key compromise tác động nhiều tenants | Tách keys/secret stores, audit và rotation |
| P-T09 | Client mTLS tại edge nhưng backend tin header giả | Identity delegation không được bảo vệ | Vượt quyền API nếu backend không auth | Edge identity stripping/signing, backend mTLS, per-request auth |
| P-T10 | TLS 1.3 resumption dùng auth context cũ | Certificate hoặc role bị thu hồi | Tiếp tục nhận request ngoài policy | Ticket invalidation, fresh auth, application authorization |
| P-T11 | 0-RTT early data được gửi tới payment/admin | Replay hoặc retry dẫn đến duplicate side effects | Giao dịch trùng, thay trạng thái sai | Tắt 0-RTT route nhạy cảm, idempotency/anti-replay |
| P-T12 | HTTP protocol translation desync | H1/H2 parsing không nhất quán | Request smuggling/cache poisoning | Header normalization, hardening, regression tests |
| P-T13 | Host/authority injection | Dynamic backend/redirect tin client Host | SSRF, sai tenant, open redirect | Host allowlist, fixed upstream policy, app validation |
| P-T14 | LB health chỉ TCP | Backend listener sống nhưng TLS/app hỏng | Route traffic vào node không phục vụ được | TLS+app readiness health, synthetic probes |
| P-T15 | Rotation không đồng bộ | Một node còn cert cũ/CA cũ | Intermittent TLS failures/5xx | Per-node inventory, canary, forced full handshake tests |
| P-T16 | L4 balancing long-lived gRPC/TCP | Connection hashing không xét request/stream load | Hotspot/DoS ở một backend | Request-aware balancing khi có, max connection/drain |
| P-T17 | Quản trị proxy bị chiếm | RBAC/MFA/management network yếu | Thay route, xóa WAF, sử dụng private keys | IAM, least privilege, config drift/audit |
| P-T18 | QUIC path không có WAF tương đương | Chỉ kiểm TCP/443 | Policy bypass qua UDP/443 | QUIC-aware gateway/WAF, test TCP/UDP parity |
| P-T19 | Dữ liệu giải mã bị log quá mức | HTTP body/token/PII vào SIEM | Lộ dữ liệu từ log | Redaction, RBAC, retention, exclude secrets |
| P-T20 | Stateful firewall bị bypass do route/DSR | Return path bất đối xứng | Timeout, sai enforcement/visibility | Route/conntrack tests và segmentation |

### 18.3. STRIDE cho ranh giới proxy

- **Spoofing:** giả danh client IP bằng XFF/PROXY, giả backend khi proxy không verify TLS B, giả mTLS identity qua header.
- **Tampering:** sửa proxy route/Host handling, WAF policy, certificate/CA hoặc HTTP request trên hop plaintext.
- **Repudiation:** thiếu config audit, request IDs, backend selection/verify logs, không truy ra ai đổi TLS mode.
- **Information disclosure:** key compromise, plaintext backend, raw tokens trong HTTP logs hoặc metadata exposed.
- **Denial of Service:** TLS handshake flood, connection exhaustion, HTTP/2 stream overload, unhealthy backends và rotation lỗi.
- **Elevation of privilege:** WAF/origin bypass, tenant confusion, authorization dựa vào header hoặc mTLS context cũ.

### 18.4. Attack tree mức phòng vệ

~~~mermaid
flowchart TD
  G["Rủi ro: dịch vụ qua proxy mất bí mật,\ntính toàn vẹn hoặc khả dụng"] --> A{"Bề mặt"}
  A --> T["TLS termination/keys"]
  A --> R["Route/SNI/ALPN/Host"]
  A --> I["Client identity / headers"]
  A --> B["Backend TLS/network"]
  A --> H["HA/health/observability"]
  T --> T1["PKI, RBAC, rotation,\nTLS policy, log redaction"]
  R --> R1["SNI/host allowlist,\nECH/QUIC capabilities"]
  I --> I1["mTLS, trusted proxy chain,\nper-request authorization"]
  B --> B1["CA/SAN verification,\norigin ACL, segmentation"]
  H --> H1["Readiness, graceful drain,\nper-hop SLO and recovery"]
  T1 --> V["Security regression tests"]
  R1 --> V
  I1 --> V
  B1 --> V
  H1 --> V
~~~

Sơ đồ nhằm **tổ chức kiểm soát phòng vệ**, không phải trình tự khai thác. Mỗi nhánh chỉ thành rủi ro thực khi có điều kiện và tài sản cụ thể; không coi một header lỗi tự động là compromise đã xảy ra.

## 19. Quy trình triển khai, giám sát và quản lý thay đổi

### 19.1. Bước 1 — Inventory TLS termination và trust boundaries

Lập bảng cho **từng ứng dụng và hostname**:

| Trường | Ví dụ lab | Tại sao cần? |
| --- | --- | --- |
| Service/owner | Orders API / Platform team | Người chịu trách nhiệm thay đổi và ứng cứu |
| Public hostname | api.example.test | SNI/SAN/Host mong đợi |
| Client entry | TCP/443 VIP, HTTP/2; UDP/443 nếu có | Chỉ ra cả transport paths |
| TLS mode | Bridging | Phân biệt termination và passthrough |
| Frontend certificate owner | Edge security | Quyền private key và rotation |
| Frontend client auth | Public HTTPS hoặc mTLS theo route | Kiểm soát identity client |
| L7 policy | WAF, rate limit, API authorization | Chỉ ra nơi HTTP được đọc |
| Upstream endpoint/name | 10.20.10.11:8443, orders.internal.example.test | SNI B/SAN và route |
| Upstream trust | CA nội bộ, verify required | Xác định nguồn tin cậy thật |
| Forwarded metadata | XFF/XFP/identity từ edge, trusted proxy | Ngăn header spoof |
| Backend firewall | Chỉ edge/proxy service identity | Chống origin bypass |
| Load-balancing algorithm | Least requests/round robin theo workload | Hiểu đơn vị request/connection |
| Health check | HTTPS TLS verify + readiness | Không chỉ TCP connect |
| Observability | TLS A/B errors, HTTP statuses, WAF, flow | Căn cứ điều tra từng hop |
| Rollback owner | Network + Application + Security | Xử lý khi release lỗi |

**Inventory phải bám cấu hình hiệu lực**, không chỉ tên gọi kiến trúc trong sơ đồ. Nếu một service cũ chạy passthrough còn service mới dùng bridging trên cùng gateway, phải ghi **từng listener/hostname/port** để tránh khái quát sai.

### 19.2. Bước 2 — Xác định yêu cầu bảo mật

Trả lời:

1. Có **dữ liệu nhạy cảm** nào đi qua proxy/backend, thuộc ràng buộc compliance nào?
2. Có cần **client mTLS trực tiếp ở backend** hay edge được phép xác thực thay mặt?
3. Có cần **WAF kiểm tra HTTP body** hay chỉ network/transport policy?
4. Có chấp nhận **HTTP plaintext trên chặng nội bộ** không, với điều kiện nào?
5. Có cần **HTTP/2/gRPC/WebSocket/HTTP/3** và route theo Host/path?
6. Có nhiều tenant/region/cloud/account và vùng trust khác nhau không?
7. Nếu client IP được dùng cho rate limit/authorization, nguồn IP nào **thực sự đáng tin**?
8. Cần điều gì khi backend bị thu hồi credential, certificate hoặc service identity?
9. Có dự phòng/failover và SLO nào quan trọng hơn resumption hit rate?
10. Nếu TLS termination bị chiếm, **blast radius** gồm những keys, tenant và traffic nào?

Sau đó chọn termination, bridging hoặc passthrough từ **nhu cầu xác thực và policy**; không chọn vì vài câu lệnh proxy ngắn nhất.

### 19.3. Bước 3 — Thiết kế chính sách cấu hình và cấp quyền

- Tách **dev/staging/prod** secrets và config pipelines.
- Gắn mỗi virtual host, route và upstream với một **owner** và quy tắc default deny.
- Định nghĩa TLS versions/ciphers, certificate, CA trust, SNI/ALPN, mTLS và ticket scope.
- Định nghĩa **trusted proxies** và loại bỏ các forwarded/identity headers client tự đưa.
- Đặt origin/private endpoints chỉ cho **authorized gateway**.
- Định nghĩa health probes, timeout, body/header limits, retry policy và long-lived connection behavior.
- Kiểm soát quyền sửa WAF, SSL policies, backend pool và secret bằng IAM/RBAC/audit.
- Tách quản trị/observability traffic khỏi application traffic theo segmentation.

### 19.4. Bước 4 — Validation ở nhiều lớp

Một thay đổi TLS mode ảnh hưởng ít nhất bốn lớp:

| Lớp | Phép thử chính |
| --- | --- |
| **Network** | DNS, route, TCP/UDP port, NAT, return path, firewall allow/deny |
| **TLS** | Client-facing certificate, backend TLS verify, SNI/ALPN, mTLS, revocation, fallback |
| **HTTP/application** | Host/path routing, WAF, headers, gRPC/WebSocket/QUIC compatibility, authn/authz |
| **Operations** | Health, load balancing, drain, rollover, secrets lifecycle, logging, capacity, rollback |

**Negative tests quan trọng ngang positive tests**: thử unknown SNI, certificate backend sai SAN, client giả XFF, direct-origin bypass, backend unready và guest→management. Không thể kết luận kiến trúc an toàn chỉ từ một request HTTPS trả 200.

### 19.5. Bước 5 — Canary/rollout có quan sát

Nếu chuyển từ passthrough sang bridging:

1. **Kiểm tra certificate frontend mới** và đối chiếu mTLS client authentication có còn đúng không.
2. Cấu hình **upstream TLS B** với CA/SAN verification và mTLS khi cần.
3. Thử WAF/L7 rules, header normalization, body limit, authn/authz.
4. Thử HTTP/2, gRPC streams, WebSocket và timeouts với traffic đại diện.
5. Giữ **một nhóm canary** hoặc hostname lab được phép trước khi chuyển toàn bộ traffic.
6. Quan sát 4xx/5xx, handshake failures, CPU, p95/p99, origin bypass attempts, backend connection count và client IP correctness.
7. Kiểm tra failover/draining và session continuity.
8. Chỉ mở rộng tỷ lệ nếu đạt SLO và security gates.

Nếu chuyển từ bridging sang passthrough, phải **chuyển trách nhiệm certificate client-facing, mTLS/WAF/API policy và logs** về backend hoặc một điểm termination sâu hơn. Không tắt WAF ở edge mà không có lớp tương đương khi yêu cầu WAF vẫn còn.

### 19.6. Bước 6 — Rollback nhưng không bỏ xác minh

Khi gặp lỗi sau rollout:

- Dùng cấu hình **đã kiểm thử** còn đáp ứng TLS/mTLS/security policy.
- Tách riêng lỗi **certificate trust** khỏi lỗi **routing/health**.
- Nếu policy mới bật verify backend và phát hiện certificate backend sai, **không quay lại trạng thái verify none** chỉ để khôi phục nhanh, trừ khi có quyết định ngoại lệ an ninh được phê duyệt rõ ràng và kiểm soát rủi ro.
- Kiểm tra thời điểm hiệu lực secret/certificate/trust store và khả năng roll forward cấp cert đúng.
- Đảm bảo mọi backend vẫn được cô lập khỏi direct-origin traffic.
- Giữ lại audit diff, incident timeline và phép thử để tránh lặp lại.

Rollback an toàn thường là **khôi phục một cấu hình bảo mật đã được chấp thuận** hoặc **tạm giảm traffic tới backend lỗi**, chứ không phải xóa ranh giới xác thực.

### 19.7. Theo dõi hàng ngày và báo cáo

| Nhóm chỉ số | Chỉ số gợi ý | Điều cần phát hiện |
| --- | --- | --- |
| TLS A | Full/resumed handshakes, versions, cipher, SNI, client cert failures | Khách không bắt tay được, cert sai/hết hạn |
| TLS B | Upstream verification failures, mTLS errors, cert expiry | Proxy chọn backend không hợp lệ |
| L4 | TCP/UDP opens, resets, bytes, flows, PROXY protocol errors | Dữ liệu bị rơi/sai metadata transport |
| L7 | 4xx/5xx, WAF rule hits, upstream route, request IDs | Lỗi backend, WAF block, header routing |
| SLO | p50/p95/p99 latency, active streams, throughput | Regression sau đổi TLS mode |
| HA | Backend health, pool size, queue, drain and failover | Cạn pool/traffic dồn vào một node |
| Security | Direct-origin attempts, unexpected Host/SNI, XFF spoof suspicion | Bypass hoặc policy mismatch |
| Secrets | Cert TTL, key rotation, unexpected secret access | Key compromise, out-of-date nodes |
| Pipeline | Collector heartbeat, log delay, schema parse errors | Mất visibility bị nhầm với ít sự cố hơn |

### 19.8. Dữ liệu sự kiện mẫu cho SIEM

Ví dụ **synthetic JSON**, không phải schema cố định của proxy:

~~~json
{
  "event_id": "edge-tls-20261128-004",
  "event_time": "2026-11-28T09:45:00Z",
  "service": "orders-api",
  "edge": {"id": "edge-hn-01", "region": "lab-hn"},
  "request": {
    "request_id": "req-lab-004",
    "host": "api.example.test",
    "method": "GET",
    "path_template": "/v1/orders/{id}"
  },
  "downstream_tls": {
    "mode": "terminated",
    "version": "TLSv1.3",
    "sni": "api.example.test",
    "alpn": "h2",
    "client_certificate_verified": false,
    "client_certificate_required": false
  },
  "upstream_tls": {
    "enabled": true,
    "backend": "10.20.10.11:8443",
    "sni": "orders.internal.example.test",
    "server_identity_verified": true,
    "verification_policy": "approved-internal-ca"
  },
  "waf": {"decision": "allow"},
  "response": {"status": 200, "latency_ms": 43},
  "synthetic": true
}
~~~

Mẫu chỉ ghi **metadata cấu hình và kết quả kiểm tra**, không ghi raw certificate private key, HTTP Authorization/Cookie, TLS tickets hoặc payload dữ liệu khách hàng. Ở mode passthrough, phần upstream TLS verify của **LB** không tồn tại như trong ví dụ: **client/backend** mới có kết quả xác thực TLS tương ứng. SIEM phải ghi đúng điểm quan sát thay vì gán “verified=true” một cách suy diễn.

### 19.9. Theo dõi sự thay đổi không còn phù hợp kiến trúc

Các trigger cần review lại TLS mode:

- Dịch vụ chuyển từ REST/HTTP sang gRPC bidirectional streaming.
- Bật HTTP/3/QUIC hoặc ECH cho public hostname.
- Thêm partner mTLS yêu cầu backend trực tiếp kiểm tra identity.
- Bổ sung WAF/Bot management cần nhìn HTTP payload.
- Chuyển sang multi-tenant/multi-region với key isolation nghiêm ngặt.
- Đổi cloud LB, Ingress controller hoặc service mesh.
- Certificate CA/SAN hoặc trust domain thay đổi.
- Backend được chuyển sang private link, network segmentation mới.
- Lượng kết nối dài (WebSocket, IoT/MQTT) tăng đột biến.
- Sự cố origin bypass, header spoof hoặc mTLS revocation.

Mỗi thay đổi đều có thể làm **giả định ban đầu về visibility, identity hoặc health** không còn đúng. Thiết kế theo ranh giới tin cậy giúp thay đổi mà không hy sinh bảo mật để “giữ nguyên cách cũ”.

## 20. Tình huống vận hành thực tế

### Tình huống A — WAF bị bỏ qua khi chuyển sang passthrough

Một nhóm chuyển public API từ TLS termination tại edge sang TCP passthrough để backend nhận trực tiếp client certificates. Sau deployment, WAF ở edge không còn ghi HTTP requests nhưng dashboard vẫn báo “TLS traffic healthy”.

**Phân tích:** đây là hệ quả kiến trúc: **L4 edge không giải mã HTTP** nên WAF ở vị trí đó không áp rule theo body/path. Nếu ứng dụng vẫn yêu cầu WAF, cần chuyển WAF tới **điểm termination trong backend ingress**, hoặc dùng mô hình termination/bridging và **identity delegation** được thiết kế đúng. Không coi "không có WAF alerts" là "không có HTTP attacks".

### Tình huống B — HTTPS client xanh nhưng 502 từ upstream

Client xác minh **api.example.test** thành công, nhưng tất cả request trả 502 ngay sau khi cấu hình proxy dùng HTTPS upstream. Log cho thấy certificate backend SAN là **orders-old.internal.example.test**, còn proxy verify **orders.internal.example.test**.

**Phân tích:** TLS A hoạt động; **TLS B lỗi hostname verification**. Cần cấp backend certificate đúng SAN hoặc chỉnh cấu hình upstream tới hostname/certificate thật sự được phê duyệt. **Không sửa bằng cách bỏ proxy_ssl_verify**. Kiểm thử âm với wrong SAN sau khi sửa để đảm bảo proxy thật sự chặn peer sai.

### Tình huống C — Client mTLS hợp lệ nhưng backend không thấy chứng chỉ

Proxy terminate mTLS ở edge. Backend đọc TLS client certificate từ socket nhưng thấy certificate của **proxy trên TLS B**, không phải certificate client bên ngoài; rule backend từ chối.

**Phân tích:** trong bridging, TLS A và TLS B là hai phiên độc lập. Nếu backend cần identity client gốc, thiết kế một cơ chế **identity propagation đáng tin** từ edge tới backend kèm mTLS giữa proxies và authorization. Nếu yêu cầu backend tự xác minh client certificate nguyên gốc là bắt buộc, cân nhắc passthrough cho flow tương ứng. Không copy raw client-cert header do client tự cung cấp để đánh lừa backend.

### Tình huống D — Rate limit khóa cả văn phòng

Nhiều nhân viên truy cập API qua NAT/VPN, backend chỉ nhìn source IP của edge. Sau khi bật rate limit theo remote address, toàn bộ traffic của nhóm bị gom vào một IP và khóa nhầm.

**Phân tích:** xác định trusted proxy chain và NAT mapping; sau đó dùng **authenticated principal/tenant** để rate limit theo quyền, bổ sung IP khi phù hợp. Không tin XFF không được kiểm soát và không gán mọi người dùng của một NAT IP thành cùng identity.

### Tình huống E — Bật PROXY protocol gây TLS handshake failures

L4 LB thêm PROXY v2 header tới backend TLS, trong khi backend chỉ đọc TLS record. Kết nối vốn chạy nay lỗi handshake ngay khi bắt đầu.

**Phân tích:** backend nhận **PROXY header trước ClientHello** nhưng không biết cách parse. Cần cấu hình listener hỗ trợ PROXY v2 hoặc bỏ PROXY protocol theo thiết kế, cùng giới hạn nguồn kết nối từ LB. Không để client không đáng tin gửi PROXY header tự nhận client IP.

### Tình huống F — Chỉ HTTP/3 thất bại

API chạy tốt với HTTP/2/TCP nhưng mobile client ở một mạng dùng QUIC bị timeout. Firewall chỉ cho phép TCP/443, hoặc LB không có UDP/443 listener.

**Phân tích:** phân biệt transport; HTTP/3 dùng QUIC/UDP và có policy/lifecycle riêng. Nếu muốn hỗ trợ, mở đúng UDP path có kiểm soát, bổ sung QUIC-aware LB/WAF và monitor. Không mở mọi UDP chỉ để chữa lỗi. Nếu client fallback HTTP/2, kiểm tra trải nghiệm thực và các trường hợp không fallback.

### Tình huống G — Chuyển region, backend certificate trust khác nhau

Edge ở Region A xác minh CA nội bộ tốt; khi failover sang Region B, các backend có certificate do CA mới ký nhưng proxy chưa cập nhật trust store. Health TCP còn xanh; HTTPS requests trả 502.

**Phân tích:** TLS B trust chain/CA rollout không đồng bộ. Cần cập nhật trusted roots và kiểm tra SAN/mTLS theo quy trình, thử per-region forced full handshake và readiness. Sau đó kiểm tra key retirement để không giữ mọi CA cũ vĩnh viễn.

### Tình huống H — SNI passthrough đưa traffic vào backend sai

Gateway L4 dùng SNI preread để chọn backend. Một client không gửi SNI, hoặc dùng cơ chế làm hostname thực không quan sát được. Default route lại trỏ tới backend admin.

**Phân tích:** thiết kế vi phạm fail-closed. Phải đưa unknown/hidden SNI về một policy được chấp thuận, không để tới backend đặc quyền. Nếu ECH là yêu cầu sản phẩm, đánh giá kiến trúc route theo VIP hoặc termination có khả năng ECH, thay vì ép tất cả traffic rơi vào cùng backend nhạy cảm.

### Tình huống I — gRPC timeout khi proxy đổi từ passthrough sang L7

Trước đây gRPC client kết nối thẳng tới backend qua L4 passthrough. Khi chuyển sang TLS termination, edge dùng HTTP/1.1 upstream với buffer/timeouts như API REST. Một số gRPC bidirectional streams bị lỗi hoặc mất trailers.

**Phân tích:** L7 proxy phải **hỗ trợ gRPC/HTTP2 upstream** và giữ semantics stream/trailers, deadlines, keepalive. Cần sửa route/protocol/timeouts, kiểm thử long-lived streams và application logs; không suy rằng gRPC phải luôn đi passthrough, nhưng cũng không ép nó qua HTTP/1.1 reverse proxy không có gRPC support.

### Tình huống J — WAF logs bình thường dù có direct-origin abuse

Origin có public IP để “dễ troubleshoot”. Một client trực tiếp gọi origin mà không qua CDN/WAF, gửi Host giống public website và được backend trả dữ liệu. SIEM chỉ quan sát edge nên không thấy request.

**Phân tích:** cần **origin ingress restriction và xác thực edge–origin**, đồng thời bổ sung backend access logs, direct-origin alert và network controls. Host header, DNS hay certificate public **không phải cơ chế buộc client phải đi qua WAF**.

### Tình huống K — Rotate certificate thành công một node nhưng client vẫn lỗi ngẫu nhiên

Một load balancer có ba edge nodes. Hai node nạp certificate mới, node thứ ba chưa reload. Monitoring chỉ nhìn VIP và nhiều kết nối resumed nên không thấy certificate cũ ngay.

**Phân tích:** kiểm tra **fresh full TLS handshake tới từng node/region**, SNI/certificate serial/SAN và rollout version. Thêm canary bằng key/cert metadata an toàn, đồng bộ reload và drain. Không chỉ chạy một request từ laptop rồi kết luận rotation hoàn tất.

### Tình huống L — Backend không cho phép TLS B nhưng health TCP vẫn “up”

Gateway bridging cần HTTPS tới origin port 8443. Backend sau release chỉ còn HTTP plaintext trên port đó. L4 TCP health tiếp tục thành công, nhưng mọi TLS B handshake thất bại.

**Phân tích:** dùng HTTPS readiness hoặc synthetic check kiểm tra **TLS/HTTP**, không chỉ mở TCP. Khôi phục backend TLS đúng thay vì sửa proxy sang HTTP ngoài kiến trúc đã phê duyệt. Kiểm tra release procedure để TLS mode client-facing và upstream không thay đổi bất ngờ.

## 21. Checklist thiết kế, kiểm thử và nghiệm thu bảo mật

### 21.1. TLS mode và quyền sở hữu

- [ ] Có sơ đồ xác định đúng **client-facing TLS termination point** cho từng hostname/listener/port.
- [ ] Xác định rõ **termination + HTTP**, **re-encryption** hay **passthrough**, không nhầm vì cả ba dùng TCP/443.
- [ ] Có sơ đồ **từng TLS hop**, nơi tồn tại plaintext, ai sở hữu private key/certificate/CA và người vận hành.
- [ ] Không mô tả bridging là end-to-end TLS không có trung gian có thể đọc nội dung.
- [ ] Có quy định khi nào **backend phải trực tiếp kiểm tra mTLS client** và khi nào edge có quyền xác thực thay.
- [ ] Nếu yêu cầu WAF/L7 authorization, có **điểm termination với khả năng thực thi** trước endpoint cần bảo vệ.
- [ ] Unknown/missing SNI hoặc hostname được xử lý theo **default policy không đưa vào admin/tenant sai**.
- [ ] Cấu hình riêng TCP/443 và UDP/443 khi cần HTTP/3/QUIC.

### 21.2. PKI và backend TLS verification

- [ ] Client kiểm tra certificate chain, hostname/SAN và TLS policy tại endpoint mà nó kết nối.
- [ ] Proxy bridging **bật backend CA/certificate/hostname verification** cho TLS B.
- [ ] Upstream SNI, tên xác minh và Backend Host được thiết kế nhất quán theo từng service/tenant.
- [ ] Backend certificate private keys và proxy private keys nằm trong secret store/vùng phù hợp với IAM/audit.
- [ ] Cert expiry/rotation được giám sát **tại edge và origin**, kể cả mTLS CA/trust roots.
- [ ] Có test **wrong SAN, wrong CA, expired certificate và unknown SNI** theo quy trình lab.
- [ ] Session resumption/ticket key scope được review; không dùng ticket cũ để bỏ qua cập nhật quyền/mTLS.
- [ ] TLS versions/ciphers/ALPN và forward secrecy phù hợp baseline đã duyệt.
- [ ] Không có cấu hình **skip verification/insecure TLS fallback** ngoài ngoại lệ được quản trị.

### 21.3. Danh tính, headers và access controls

- [ ] Edge **strip/overwrite** XFF/XFP/identity headers từ nguồn chưa được tin cậy.
- [ ] Ứng dụng chỉ tin forwarded metadata từ **đúng proxy peers** đã được xác thực/allowlisted.
- [ ] mTLS client identity qua bridging có cơ chế truyền xuống được bảo vệ, backend không tin header giả.
- [ ] **PROXY protocol** chỉ được bật khi bên gửi/nhận cùng version/semantics và backend chỉ nhận peer đáng tin.
- [ ] Origin không thể truy cập trực tiếp để bypass WAF hoặc auth gateway ngoài kiến trúc được duyệt.
- [ ] Host/authority và routes được allowlist, không dùng client Host tùy ý làm upstream SSRF destination.
- [ ] Application authn/authz độc lập với TLS session/ticket và network allowlist.
- [ ] Backend nhận đúng client IP/identity trong điều kiện NAT/VPN/CDN theo metadata đã được xác minh.
- [ ] Guest/IoT/untrusted networks không được vào backend production dù biết private IP.

### 21.4. Load balancing và tính sẵn sàng

- [ ] LB algorithm phù hợp **connection vs request/stream** semantics.
- [ ] Backend health check đủ mức **TCP, TLS và HTTP/readiness** theo khả năng sản phẩm.
- [ ] Có kế hoạch **failover, graceful drain, WebSocket/gRPC long-lived streams và retry idempotency**.
- [ ] Đường reply qua NAT/stateful firewall và route dự phòng đã được kiểm tra.
- [ ] Các proxy/edge có CPU/connection limits và khả năng chịu thêm full handshakes khi rotate keys.
- [ ] Không để TCP health pass che giấu backend TLS/certificate sai.
- [ ] HTTP/3/QUIC có network, LB, WAF/DoS và logging riêng tương đương theo mục tiêu.
- [ ] Có synthetic probes từ các mạng/region/tenant quan trọng, không chỉ một VIP health check.

### 21.5. Giám sát, bảo mật dữ liệu và vận hành

- [ ] Log **downstream TLS A và upstream TLS B** riêng biệt; mode passthrough ghi đúng giới hạn quan sát.
- [ ] Log request ID, selected backend, route, WAF rule, TLS error category, latency mà không lưu secret.
- [ ] Không ghi raw private keys, TLS tickets/PSKs, Authorization/Cookie, tài liệu nhạy cảm vào SIEM.
- [ ] Có cảnh báo **certificate expiry, upstream verify fail, unknown SNI, direct-origin attempts, 0-RTT state và header spoof**.
- [ ] Collector heartbeat/data-lag được giám sát để phân biệt **mất telemetry** với ít cảnh báo hơn.
- [ ] Config changes và secret usage có owner, change ticket, RBAC/MFA khi phù hợp và audit.
- [ ] Negative tests chạy lại sau thay **LB, Ingress controller, service mesh, CA, SNI, ALPN hoặc cloud route**.
- [ ] Có runbook khôi phục mà **không tắt certificate validation, không mở origin bypass và không nới authorization**.

## 22. Bài tập thiết kế và câu hỏi ôn tập

### 22.1. Đề bài tổng hợp

Một công ty triển khai **Orders API** và **Payment API** trên nhiều vùng, có:

- Ứng dụng web/mobile truy cập qua **CDN/WAF**.
- Một **API gateway** route theo Host/path và kiểm tra OAuth/JWT.
- Hai cụm backend trong hai VPC/VNet khác nhau; Orders có HTTP/2/gRPC, Payment có giao dịch ghi trạng thái.
- Một nhóm đối tác dùng **mTLS client certificate**, một nhóm user dùng cookie/JWT.
- Một số workload backend dùng **service mesh mTLS**.
- Mạng công ty có **VPN, IDS/IPS, firewall/NetworkPolicy, private DNS** cho các backend.
- HTTP/3 được cân nhắc ở edge; session resumption TLS 1.3 được bật, **0-RTT chưa bật**.

Nhiệm vụ:

1. Vẽ sơ đồ định tuyến từ client qua CDN/WAF/API gateway tới hai cụm backend, **đánh dấu mọi TLS termination và plaintext boundary**.
2. Chọn **TLS termination/bridging/passthrough** cho từng dịch vụ, giải thích dựa trên WAF requirement, mTLS identity và protocol.
3. Chỉ ra **certificate SAN/CA và private key owner** cho từng hop; bảo đảm verify TLS B.
4. Thiết kế **trusted forwarded headers và identity propagation** để client không giả IP hoặc mTLS identity.
5. Thiết kế **firewall/SG/NetworkPolicy** chặn direct-origin access và traffic Guest/IoT vào production.
6. Lựa chọn **load-balancing algorithm**, health check, graceful draining cho gRPC và traffic REST.
7. Thiết kế **HTTP/3/QUIC path** và kiểm tra fallback về HTTP/2 khi UDP/443 không được phép.
8. Xác định **20 test cases**, gồm 10 positive và 10 negative: certificate đúng/sai, SNI lạ, mTLS invalid, gRPC, 502 backend, PROXY mismatch, HTTP header spoof, origin bypass, failover và WAF blocking.
9. Lập **SIEM event schema** phản ánh TLS A/B, route, mTLS identity, selected backend và kết quả WAF mà không log secrets.
10. Viết **playbook** khi phát hiện certificate backend bị cấp nhầm SAN và when client-facing certificate bị lộ, có phân loại phạm vi ảnh hưởng và rollback an toàn.

**Tiêu chí đạt:** giải thích đúng điểm TLS terminate, không gọi bridging là passthrough; WAF nằm ở nơi thực sự thấy HTTP; backend TLS được xác minh; client IP/identity chỉ tin từ nguồn được kiểm soát; các test negative pass và giải pháp có khả năng vận hành.

### 22.2. Câu hỏi kiểm tra

**Câu 1.** TLS termination khác TLS passthrough ở điểm then chốt nào?

*Gợi ý:* Termination biến proxy thành TLS endpoint, có thể giải mã/xử lý HTTP; passthrough chuyển TLS flow đến backend là TLS endpoint, không giải mã HTTP tại LB.

**Câu 2.** Vì sao TLS bridging không phải một TLS session duy nhất giữa client và backend?

*Gợi ý:* Có hai handshake, hai cặp peer và hai bộ traffic secrets; proxy thấy plaintext ở giữa, dù mỗi hop đều mã hóa.

**Câu 3.** Có thể dùng một WAF kiểm tra request body trong L4 TLS passthrough thuần túy tại vị trí LB không?

*Gợi ý:* Không. Nội dung HTTP nằm trong ciphertext; cần một điểm termination có quyền kiểm tra, có thể ở backend ingress.

**Câu 4.** Proxy dùng HTTPS upstream có chắc đang xác minh server certificate của backend không?

*Gợi ý:* Không. Phải xác minh tùy chọn verify, CA bundle và hostname/SAN/SNI cụ thể; không chỉ nhìn URI HTTPS.

**Câu 5.** Khi client truy cập api.example.test qua passthrough, certificate cần chứa SAN nào?

*Gợi ý:* Backend TLS server trình certificate hợp lệ cho hostname mà client xác minh, ở đây api.example.test; private hostname riêng không tự đáp ứng.

**Câu 6.** Khi bridging, proxy gửi SNI B khác public Host có luôn sai không?

*Gợi ý:* Không. Có thể hợp lệ khi backend TLS identity và application Host policy được thiết kế thống nhất; vẫn phải verify SAN/CA.

**Câu 7.** SNI có thể dùng để chứng minh danh tính người dùng hoặc tenant authorization không?

*Gợi ý:* Không. SNI do client khai; chỉ giúp chọn context/route/certificate. Quyền cần authn/authz độc lập.

**Câu 8.** Vì sao ECH gây khó khăn cho L4 SNI-based passthrough routing?

*Gợi ý:* ClientHelloInner có thể che hostname thực, proxy chỉ thấy outer metadata; cần ECH-capable termination hoặc route theo cách khác đã được thiết kế.

**Câu 9.** TLS 1.3 passthrough proxy có thấy HTTP status code hoặc server certificate nội dung không?

*Gợi ý:* Không thấy HTTP ciphertext, và certificate server TLS 1.3 nằm trong phần handshake được bảo vệ khi proxy không terminate.

**Câu 10.** Sự khác nhau giữa X-Forwarded-For và PROXY protocol là gì?

*Gợi ý:* XFF là HTTP header qua proxy chain, PROXY protocol là transport preamble trước TLS/ứng dụng; cả hai đòi nguồn tin cậy, không tự chứng minh user identity.

**Câu 11.** Một backend chỉ bật TLS listener nhưng không hỗ trợ PROXY protocol; L4 LB bật PROXY v2 sẽ thế nào?

*Gợi ý:* Backend có thể đọc PROXY bytes như TLS record và handshake fail. Cả hai bên phải đồng bộ format và giới hạn nguồn.

**Câu 12.** Client gửi X-Forwarded-For giả có thể vượt API rate limit không?

*Gợi ý:* Có nguy cơ nếu backend/edge tin header từ client. Strip/overwrite và trusted proxy configuration là điều kiện bắt buộc.

**Câu 13.** Khi nào backend trực tiếp kiểm tra mTLS client certificate?

*Gợi ý:* Thường khi passthrough và TLS terminate tại backend. Trong bridging, backend trực tiếp xác thực proxy trên TLS B, client identity gốc cần được ủy quyền/đưa xuống an toàn.

**Câu 14.** Tại sao một HTTP/2/gRPC connection có thể làm least-connections L4 phân phối tải không đều?

*Gợi ý:* Một kết nối có nhiều streams/requests; L4 chỉ thấy số connections, không biết lượng request thực.

**Câu 15.** Một HTTP GET qua L7 thành công nhưng gRPC bidirectional stream lỗi; có thể do gì?

*Gợi ý:* H2/ALPN, upstream gRPC support, trailers, buffering, timeout, connection drain; không chỉ certificate TLS.

**Câu 16.** Vì sao TCP health check thành công không chứng minh backend HTTPS an toàn?

*Gợi ý:* TCP listener mở không xác minh certificate/SNI/mTLS, readiness hoặc khả năng trả HTTP hợp lệ.

**Câu 17.** Khi client nhận 502 sau TLS A thành công, nên xem log nào?

*Gợi ý:* Proxy upstream/backend routing, TLS B verification, health, timeout và application; certificate phía client có thể hoàn toàn hợp lệ.

**Câu 18.** Vì sao phải phân biệt TCP/443 và UDP/443?

*Gợi ý:* HTTP/1.1/H2 HTTPS thường TCP+TLS, HTTP/3 dùng QUIC/UDP+TLS 1.3; load balancing và firewall/observability khác nhau.

**Câu 19.** Session ticket client–edge có được dùng để resume proxy–backend không?

*Gợi ý:* Không tự động. TLS A và TLS B là phiên độc lập với peer, ticket key và policy riêng.

**Câu 20.** Tắt 0-RTT có làm mất TLS 1.3 session resumption không?

*Gợi ý:* Không. TLS 1.3 có thể resume 1-RTT mà không gửi early data; 0-RTT là tính năng bổ sung có replay risk.

**Câu 21.** Tại sao chỉ cho CDN IP vào origin không luôn đủ chống bypass?

*Gợi ý:* IP range có thể dùng chung; cần đánh giá product model, origin mTLS/service identity và các network restrictions phù hợp.

**Câu 22.** Một service đã bật TLS ở backend nhưng certificate được proxy chấp nhận dù không đúng tên. Có gì sai?

*Gợi ý:* Bảo vệ mã hóa mà không xác minh đúng peer không đạt mục tiêu xác thực. Phải bật hostname validation và trust CA đúng.

**Câu 23.** Bật passthrough có mặc định giữ source IP của client ở backend không?

*Gợi ý:* Không. NAT/TCP proxy có thể thay IP; preservation, DSR hoặc PROXY protocol cần thiết kế riêng.

**Câu 24.** Backend có thể tin Authorization hay mTLS identity từ một HTTP header do khách tự đặt không?

*Gợi ý:* Không. Trusted metadata phải được edge xác minh và thay thế, backend nhận qua nguồn được xác thực; authorization vẫn độc lập.

**Câu 25.** Tại sao testing certificate rotation phải ép một full handshake mới?

*Gợi ý:* Session resumption có thể không gửi lại certificate server; một resumed connection không đủ chứng minh cert mới đã được nạp.

### 22.3. Bài tập phân tích log giả

Một proxy có số liệu sau:

~~~text
Client-facing edge:
  TLS A handshakes: 10,000 successful
  Client TLS verification errors observed: 0
  HTTP responses: 2,800 status 502; 7,200 status 200

Proxy -> Backend:
  TLS B verify failures: 2,800
  Backend pool:
    node-1 10.20.10.11:8443: cert valid, 200 responses
    node-2 10.20.10.12:8443: cert SAN mismatch, verify denied

Health:
  TCP checks: both nodes UP
  HTTPS checks with proper hostname: node-1 UP, node-2 DOWN

Routing:
  Weighted round robin 70:30 approximately.
~~~

**Câu hỏi:**

1. Lỗi thuộc TLS A hay TLS B? Chứng cứ nào hỗ trợ?
2. Có nên tắt verify backend để toàn bộ request trả 200 không?
3. Tại sao TCP health check lại báo node-2 UP?
4. Khi tạm loại node-2, cần kiểm tra gì về capacity và drain?
5. Sau khi cấp đúng certificate SAN cho node-2, cần kiểm tra gì trước khi đưa vào pool?

**Đáp án tham khảo:**

- **TLS A thành công** theo log; các lỗi 502 tương quan với **TLS B certificate verification failures**, chưa đủ nói có rủi ro dữ liệu bị lộ.
- **Không tắt verify**: cấp đúng SAN/CA và kiểm chứng proxy xác thực backend.
- **TCP health** chỉ chứng minh port nhận kết nối; cần HTTPS check/readiness nếu hỗ trợ.
- **Tạm remove node-2** có thể làm node-1 quá tải; đánh giá backlog, connection draining, backend scaling và user SLO.
- Sau khi sửa certificate, thử **fresh TLS B handshake từ proxy với SNI/CA đúng**, chứng minh wrong-SAN test vẫn bị chặn, kiểm tra app readiness rồi canary đưa node vào pool.

## 23. Tổng kết

- **TLS termination** biến reverse proxy thành đầu cuối TLS của client. Nó thấy HTTP plaintext và có thể áp WAF/L7 routing/authorization, nhưng phải quản lý private key, plaintext boundary và chính sách backend.
- **TLS passthrough** chuyển TLS flow tới backend làm TLS endpoint; L4 LB không đọc HTTP payload. Nó có thể route theo SNI khi ClientHello còn quan sát được, nhưng không có HTTP path/body để áp WAF tại đó.
- **TLS re-encryption/bridging** là **hai TLS sessions độc lập**: client→edge và proxy→backend. Nó cho phép WAF ở edge và mã hóa hop nội bộ, nhưng proxy phải **xác minh CA/SAN/hostname của backend**, không chỉ bật HTTPS upstream.
- **mTLS client identity** qua termination không tự đến backend. Backend sẽ thấy proxy TLS peer trên hop B nếu mTLS ở đó; việc truyền identity gốc phải có **trust boundary, header stripping/signing và authorization** rõ ràng.
- **SNI/ALPN/ECH** quyết định giới hạn route: SNI không chứng minh danh tính, ALPN có thể khác giữa hai TLS hops, và ECH có thể che hostname thật khỏi L4 passthrough.
- **X-Forwarded-For/Forwarded và PROXY protocol** mang metadata khác nhau, đều cần tin cậy nguồn gửi. Passthrough không mặc định giữ client IP, và IP qua NAT không đại diện một người dùng.
- **HTTP/2/gRPC/WebSocket và HTTP/3/QUIC** có đặc điểm connection/stream và transport riêng; phải kiểm thử routing, protocol translation, timeouts, draining và UDP/443 khi cần.
- **Health check TCP, TLS và application readiness khác nhau**. Một cổng mở không chứng minh certificate hợp lệ hoặc app khỏe, còn HTTP 502 sau handshake A có thể do TLS B.
- **PKI, certificate rotation, secret isolation, resumption, 0-RTT, WAF và firewall/segmentation** là những lớp phòng vệ bổ trợ; không dùng một khóa/ticket, một IP allowlist hoặc một header để thay quyền ứng dụng.
- **Chọn TLS mode theo trust boundaries, dữ liệu nhạy cảm, yêu cầu WAF, mTLS và protocol**, sau đó đo hiệu năng bằng telemetry cả hai hops. Không đánh đổi certificate verification và origin access restriction chỉ để tăng throughput hoặc giảm số lỗi tạm thời.
- **Kiểm thử thành công bao gồm cả negative cases**: unknown SNI, wrong backend certificate, forwarded header spoofing, direct-origin access, PROXY protocol mismatch, HTTP/3 fallback và lỗi node/region. Kết quả cần có **bằng chứng từng chặng**, không chỉ một request HTTPS trả 200.
