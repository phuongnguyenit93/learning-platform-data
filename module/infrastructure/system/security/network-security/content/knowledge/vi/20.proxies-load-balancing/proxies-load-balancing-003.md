# Load balancer Layer 4 và Layer 7: cơ chế phân phối, bảo mật và vận hành

## 1. Load balancer L4 và L7 giải quyết vấn đề gì?

**Load balancer (LB)** là thành phần phân phối lưu lượng từ client tới một hoặc nhiều backend theo chính sách, giúp tăng **khả năng phục vụ, tính sẵn sàng, khả năng mở rộng và kiểm soát đường vào**. Tùy kiến trúc, LB có thể là thiết bị phần cứng, phần mềm, dịch vụ cloud hoặc một cụm proxy. Một địa chỉ dịch vụ có thể được công bố qua **virtual IP (VIP)**, DNS name, Anycast hoặc endpoint do nhà cung cấp quản lý.

Hai mô hình thường gặp:

- **Layer 4 (L4) load balancing:** quyết định chuyển một **luồng ở lớp vận chuyển**, chủ yếu dựa trên thông tin **IP, TCP/UDP và trạng thái kết nối/flow**. L4 có thể chuyển bằng NAT, direct server return hoặc tạo proxy TCP; không nhất thiết hiểu HTTP.
- **Layer 7 (L7) load balancing:** hiểu **giao thức ứng dụng** như HTTP/HTTPS, có thể quyết định theo **hostname, URL path, method, headers, cookies, gRPC metadata** và chính sách ứng dụng, sau khi thông tin cần thiết có thể được đọc ở điểm LB.

Trong module **SECURITY_NETWORK_SECURITY**, L4/L7 LB còn là **điểm phân định vùng tin cậy** giữa Internet, DMZ, ứng dụng, DNS, firewall, IDS/IPS và hạ tầng cloud. Chọn LB không chỉ để tăng throughput; thiết kế sai có thể làm **lộ origin, tin nhầm header nguồn, bỏ qua WAF, trộn traffic Dev/Prod hoặc phá phiên khi failover**.

### Mục tiêu học tập

Sau bài này, người học có thể:

1. Giải thích **ranh giới L4/L7** qua luồng TCP/UDP và HTTP/HTTPS, tránh coi nhãn sản phẩm là định nghĩa tuyệt đối.
2. Phân biệt **NAT, full-proxy, DSR, TLS passthrough và TLS termination**.
3. Chọn **thuật toán phân phối**, health check, session persistence và connection draining cho từng workload.
4. Phân tích **source IP, PROXY protocol, Forwarded/X-Forwarded-For**, trust boundary và yêu cầu xác thực.
5. Thiết kế HA, failover, zone awareness, routing đối xứng, segmentation và quan sát IDS/IPS.
6. Chẩn đoán lỗi 502/503/504, connection reset, sticky session, gRPC/WebSocket và các vấn đề DDoS.
7. Xây dựng kiểm thử ALLOW/DENY, ví dụ phân phối offline, runbook và kế hoạch thay đổi có rollback.

## 2. Layer 4 và Layer 7 là cách phân loại chức năng, không phải hai hộp kín

| Khía cạnh | L4 LB | L7 LB |
| --- | --- | --- |
| Đơn vị quyết định thường gặp | TCP connection hoặc UDP flow | HTTP request, stream hoặc giao dịch ứng dụng theo năng lực |
| Thông tin nhìn vào | IP nguồn/đích, TCP/UDP port, protocol, flow state | HTTP Host/authority, path, method, headers, cookies, request metadata |
| Có cần giải mã TLS để đọc HTTP? | Không, nếu chỉ dựa vào L4 | **Có** khi quyết định dựa vào HTTP bên trong TLS; điểm LB/proxy phải kết thúc/giải mã TLS hợp lệ |
| Xử lý TCP | Có thể forward ở mức packet hoặc terminate TCP như proxy | HTTP reverse proxy thường terminate TCP/TLS và tạo kết nối phía backend |
| Phân phối trong một kết nối | Thường giữ cùng một backend cho flow | Có thể phân phối theo request/HTTP stream nếu kiến trúc hỗ trợ |
| Hỗ trợ TCP/UDP bất kỳ | Thường phù hợp hơn | Chỉ nếu proxy hiểu giao thức và triển khai chức năng tương ứng |
| WAF/auth theo HTTP | Không có nếu chỉ nhìn TCP/UDP | Có thể tích hợp WAF, routing/auth policy, nhưng không tự động |
| Chi phí xử lý | Thường ít parsing hơn | Có parsing, buffering, TLS, logging và chính sách có thể tốn CPU/RAM |

**Cảnh báo về cách gọi:** Một sản phẩm quảng cáo “L4 LB” vẫn có thể cung cấp **health check HTTP**, theo dõi TLS handshake hoặc đọc SNI trong **ClientHello** mà không giải mã HTTP. Ngược lại, một “L7 reverse proxy” có thể hỗ trợ TCP passthrough. Khi chọn giải pháp hãy xem **đường dữ liệu đang dùng**, không chỉ dựa trên tên sản phẩm.

### 2.1. Ví dụ gói/luồng để so sánh

~~~text
Client 198.51.100.50:51515
  -> VIP 203.0.113.10:443

L4:
  IP/TCP flow -> chọn backend 10.20.10.11:443
  Giữ flow affinity cho chiều trả lời.

L7:
  Nhận kết nối TLS và đọc HTTP sau khi giải mã hợp lệ.
  GET /images/logo.png, Host: shop.example.org -> static pool
  POST /checkout, Host: shop.example.org -> checkout pool
~~~

Hai prefix **198.51.100.0/24** và **203.0.113.0/24** dành cho tài liệu; tên miền **example.org** dùng làm ví dụ. Đây không phải IP public để thiết lập dịch vụ production.

## 3. Sơ đồ kiến trúc cơ bản

### 3.1. L4 cân bằng nhiều backend

~~~mermaid
flowchart LR
    C["Client / TCP hoặc UDP"] --> VIP["VIP :443"]
    VIP --> LB["L4 Load Balancer"]
    LB -->|"Flow A"| A["Backend A"]
    LB -->|"Flow B"| B["Backend B"]
    LB -->|"Flow C"| D["Backend C"]
~~~

L4 thường gán từng flow cho một backend, ví dụ **TCP 5-tuple** gồm source IP/port, destination IP/port và transport protocol. Vì nhiều backend khác nhau có thể phục vụ những flow riêng, ứng dụng cần **state sharing, replicated database hoặc session persistence** nếu không xử lý stateless.

### 3.2. L7 định tuyến theo nội dung HTTP

~~~mermaid
flowchart LR
    C["Client HTTPS"] --> LB["L7 Reverse Proxy / LB"]
    LB -->|"Host api.example.org, /v1/"| API["API Pool"]
    LB -->|"Host shop.example.org, /checkout"| CK["Checkout Pool"]
    LB -->|"Host shop.example.org, /assets/"| ST["Static Pool"]
    LB -. "WAF / Auth / Rate policy" .-> SEC["Security controls"]
~~~

L7 có thể thay đổi backend theo **request**, không chỉ theo kết nối đầu tiên. Tuy nhiên điều đó **không bảo đảm** ở mọi sản phẩm hoặc giao thức: gRPC streams dài, WebSocket upgrade hoặc connection pinning có thể khiến một backend giữ nhiều request/message trong thời gian lâu.

### 3.3. Điểm bắt buộc phải giải thích

Một HTTP request có thể đi qua nhiều hops:

~~~text
Browser --TLS 1--> CDN/WAF --TLS 2--> L7 LB --TLS 3/mTLS--> Service
                                                   |
                                                   +--> Database
~~~

**TLS 1, TLS 2, TLS 3 là các chặng bảo mật khác nhau**, không phải ba tên của cùng session. Chứng chỉ, thuật toán, khả năng forward secrecy, quyền truy cập logs và nơi nhìn thấy plaintext phải được kiểm soát riêng. Nếu chặng LB → Service dùng HTTP nội bộ, phải đánh giá rõ ranh giới mạng và dữ liệu mà LB giải mã.

## 4. Các mô hình L4: NAT, full-proxy và Direct Server Return

Không phải mọi L4 LB đều chuyển packet theo cùng một cách. Ba mô hình thường được dùng để giải thích **đường đi-về** và trạng thái cần lưu.

### 4.1. Destination NAT (DNAT)

LB nhận gói đến VIP, thay **destination IP/port** thành địa chỉ backend đã chọn. Đường trả lời cần đi qua cơ chế đảo translation tương ứng, thường qua LB hoặc một thiết kế NAT/routing phù hợp.

~~~text
Trước DNAT:
  198.51.100.50:51515 -> 203.0.113.10:443

Sau DNAT:
  198.51.100.50:51515 -> 10.20.10.11:443

Return qua LB:
  10.20.10.11:443 -> 198.51.100.50:51515
  LB ánh xạ thành packet từ VIP 203.0.113.10:443.
~~~

Nếu backend không trả về qua LB và không có cơ chế phù hợp, client có thể nhận địa chỉ nguồn sai hoặc **LB mất state**. Khi dùng DNAT/SNAT phải xem đúng NAT table, route và thứ tự policy.

### 4.2. Full-proxy TCP

LB **terminate TCP connection từ client** rồi mở **TCP connection khác tới backend**:

~~~text
Client ---- TCP connection #1 ----> L4 TCP proxy
                                  L4 TCP proxy ---- TCP #2 ----> Backend
~~~

Mặc dù xử lý hai kết nối, proxy này vẫn có thể được coi là **L4** nếu không cần đọc hoặc hiểu HTTP. Backend có thể thấy **IP của LB** thay vì IP thật của client; muốn truyền metadata nguồn phải có giải pháp được hỗ trợ và được tin cậy.

### 4.3. Direct Server Return (DSR)

Trong **DSR**, LB thường xử lý lưu lượng **inbound**, còn backend **gửi response trực tiếp tới client** trong kiến trúc có VIP/định tuyến phù hợp:

~~~mermaid
flowchart LR
    C["Client"] -->|"Request"| L["L4 LB"]
    L -->|"Select backend"| B["Backend với thiết lập VIP/DSR"]
    B -->|"Response trực tiếp"| C
~~~

DSR có thể giảm tải đường trả lời tại LB, nhưng đòi hỏi kiến trúc backend/ARP/ND/VIP, source IP và route chính xác. **Bất đối xứng ở đây có thể là thiết kế hợp lệ**; điều cần kiểm chứng là không có stateful firewall/NAT/IPS nào bắt buộc thấy hai chiều nhưng lại chỉ nhìn thấy một.

### 4.4. Bảng đánh đổi

| Kiểu dataplane | Lợi ích | Rủi ro vận hành |
| --- | --- | --- |
| DNAT | Cấp VIP/flow mapping rõ, có thể giữ source IP | Đường trả lời, conntrack/NAT state, SNAT ở đúng vị trí |
| L4 full-proxy | Tách TCP client/backend, kiểm soát timeout/buffer tốt hơn | Mất source IP trực tiếp, hai tập socket/timeout, CPU/RAM |
| DSR | Backend trả trực tiếp, giảm egress qua LB | VIP và return path phức tạp; IDS/IPS có thể chỉ thấy một chiều |
| Stateless/packet steering theo platform | Có thể giảm lượng state trên từng node | Cần xác minh hashing, protocol support, fragment và failover |

**Không tự suy DSR an toàn hơn hoặc nhanh hơn trong mọi hệ thống.** Chọn dataplane phải dựa trên khả năng phần mềm/ASIC, throughput thực tế, policy bảo mật, số lượng kết nối, NAT, observability và failover.

## 5. L7 reverse proxy xử lý HTTP như thế nào?

Một L7 LB nhận request theo **giao thức ứng dụng**, lựa chọn upstream và tạo response trở lại client. Nó có thể **đọc URI, Host/authority, method, headers, cookies**, áp chính sách và tạo kết nối tới backend phù hợp.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant P as L7 Reverse Proxy
    participant A as Application Backend
    C->>P: HTTPS: GET /api/v1/orders, Host: api.example.org
    P->>P: TLS termination, route/auth/rate/WAF policy
    P->>A: HTTP hoặc TLS tới upstream được chọn
    A->>P: Response status + body
    P->>C: HTTPS response
~~~

### 5.1. Host, path và method routing

| Tiêu chí | Ví dụ | Rủi ro nếu xử lý sai |
| --- | --- | --- |
| **Hostname / authority** | api.example.org → API pool | Host header spoofing, default vhost trỏ nhầm backend |
| **Path prefix** | /admin/ → admin service | Path normalization/encoding khác giữa proxy và backend |
| **HTTP method** | POST /upload được xử lý theo giới hạn riêng | Chặn sai hoặc bypass khi HEAD/OPTIONS/other methods |
| **Header** | X-API-Version: 2 → service v2 | Client có thể tự đặt header nếu không được kiểm soát |
| **Cookie/identity** | Sticky route theo signed cookie | Session fixation, cookie theft hoặc nhầm scope |
| **gRPC method** | /package.Service/Method | HTTP/2 stream, deadline và auth metadata cần đúng |

**L7 routing phải có default-deny/default-safe backend rõ ràng.** Một request có Host/authority không được công bố không nên rơi vào admin pool chỉ vì rule khớp cuối cùng. Đường admin nên có **authentication, authorization và network policy độc lập**, không dựa vào bí mật của URL.

### 5.2. Reverse proxy khác forward proxy

- **Reverse proxy** đứng trước server/ứng dụng, đại diện dịch vụ cho client; thường được dùng làm L7 LB.
- **Forward proxy** đứng về phía client để truy cập các đích khác theo chính sách egress.

Chúng có thể dùng chung phần mềm nhưng **không cùng trust boundary**. Một reverse proxy cấu hình nhầm thành **open forward proxy** có thể bị lạm dụng để truy cập đích nội bộ hoặc bên ngoài.

### 5.3. Routing theo request không đồng nghĩa đảm bảo xác thực

L7 LB có thể kiểm tra JWT, mTLS client identity, OIDC hoặc gọi external auth service tùy thiết kế. Nhưng nếu không cấu hình, nó chỉ làm nhiệm vụ **phân phối**. Hệ thống cần bảo đảm backend **không tin blindly các header do client gửi**, và những chức năng nhạy cảm vẫn tự xác thực/ủy quyền theo threat model.

## 6. Bảng quyết định L4 hay L7

| Nhu cầu | Lựa chọn thường phù hợp | Lý do và lưu ý |
| --- | --- | --- |
| TCP protocol riêng, không phải HTTP | **L4** hoặc proxy chuyên protocol | Không cần parse HTTP; giữ tính tương thích payload |
| UDP protocol bất kỳ | **L4 UDP flow** | Theo dõi flow timeout, fragmentation và source affinity |
| HTTP API theo path/host | **L7** | Có thông tin ứng dụng để route hoặc chặn |
| WAF, URL normalization, HTTP rate limiting | **L7** có WAF/HTTP enforcement | Phải terminate TLS đúng và đánh giá false positives |
| TLS passthrough tới backend | **L4** hoặc TCP/SNI-aware passthrough | LB không đọc HTTP đã mã hóa; backend giữ TLS private key |
| Multi-tenant microservices, canary theo header | **L7** | Chính sách định tuyến, auth và observability ở cấp request |
| Lượng kết nối TCP/giây cao, ít cần thông tin app | **L4** có thể hiệu quả | Benchmark theo workload; không mặc định tốt hơn |
| HTTP/2, gRPC, streaming | **L7** nếu cần request/stream policy | Kiểm tra HTTP/2-to-upstream, grpc-timeout/trailer, stream lifetime |
| HTTP/3/QUIC cần policy HTTP | **QUIC/HTTP3-aware L7** | UDP L4 chỉ thấy flow/header giới hạn, không đọc HTTP/3 payload |
| Client IP cần được bảo toàn tới ứng dụng | Tùy dataplane: DSR/DNAT, transparent proxy hoặc header được bảo vệ | Kiểm chứng nguồn ở backend, tránh tin XFF tự đặt |
| DNS, mail, database hoặc protocol stateful khác | L4 hoặc LB hiểu giao thức cụ thể | Health, session pinning, protocol correctness và HA khác nhau |

**Không có lựa chọn tốt tuyệt đối.** Nhiều hệ thống đặt **L4 trước L7**: L4 phân phối TCP/UDP vào cụm L7 reverse proxy, rồi L7 route HTTP tới backend. Khi đó cần rõ **NAT/source identity, health checking, TLS điểm cuối, logs và thứ tự security policy** trên từng hop.

## 7. Thuật toán cân bằng tải và sự công bằng với backend

Chọn backend phải xét **năng lực từng máy, trạng thái health, thời lượng request, số kết nối và dữ liệu cần giữ theo phiên**. Tên một thuật toán không bảo đảm kết quả tối ưu.

| Thuật toán | Ý tưởng | Hợp với tình huống | Giới hạn |
| --- | --- | --- | --- |
| **Round robin (RR)** | Luân phiên chọn các backend khỏe | Request/connection có chi phí tương đối đồng đều | Không xét request nặng nhẹ và connection lâu |
| **Weighted round robin** | Phân chia tỷ lệ theo trọng số | Backend khác năng lực CPU/RAM | Weight tĩnh có thể không phản ánh tải thực |
| **Least connections** | Chọn backend có ít connection active | TCP connections có thời lượng khác nhau | Một connection HTTP/2 có thể chứa nhiều streams; số conn không phản ánh CPU |
| **Weighted least connections** | Xem kết nối và năng lực tương đối | Pool không đồng nhất | Cần thống nhất định nghĩa capacity/connection |
| **Least requests / least outstanding** | Dựa trên request đang xử lý | HTTP workloads có thời lượng thay đổi | Phụ thuộc L7 telemetry, queue và sản phẩm |
| **Consistent hashing** | Ánh xạ key → backend tương đối ổn định | Cache locality/session affinity | Hot keys gây lệch tải, thay pool vẫn có remapping |
| **Source IP hash** | Dùng địa chỉ client để chọn backend | Một số nhu cầu affinity đơn giản | CGNAT/proxy làm hàng nghìn user trùng source IP |
| **Random / power-of-two choices** | Chọn ngẫu nhiên hoặc so sánh mẫu nhỏ | Pool lớn và workload phù hợp | Cần hiểu metric được dùng để so sánh |
| **Latency-aware / adaptive** | Điều chỉnh theo chất lượng và tải quan sát | Hệ thống có metric và feedback tin cậy | Đo sai có thể gây oscillation; cần guardrail |

### 7.1. Ví dụ weighted round robin

~~~text
Pool gồm 3 backend:
  A: weight=3
  B: weight=2
  C: weight=1

Phân phối kỳ vọng trên nhiều lượt:
  A ~ 50%
  B ~ 33,3%
  C ~ 16,7%

Không có nghĩa mọi nhóm liên tiếp 6 request đều đúng tỉ lệ,
và không có nghĩa A xử lý được lượng công việc gấp 3 lần C.
~~~

**Trọng số là chính sách phân phối**, không phải phép đo công suất. Nếu A xử lý request nặng hơn, A vẫn có thể quá tải dù tỉ lệ được chọn đúng.

### 7.2. Thuật toán phải tính cả lỗi và quá trình mở rộng

Khi một backend bị loại vì unhealthy, mọi thuật toán phải cập nhật **eligible pool**. Khi backend trở lại sau restart, nếu dồn ngay lượng traffic lớn vào một instance có cache cold/DB pool chưa sẵn sàng, có thể gây **flapping và cascading overload**. Có thể dùng **slow start/warm-up**, connection/request limits, readiness gates và quan sát SLI.

Khi tăng node, consistent hashing thường giảm số key bị remap so với hash modulo đơn giản, nhưng không loại trừ ảnh hưởng **cache warmup, shard movement và hot key**. Với workloads có trạng thái, cần đánh giá khả năng service xử lý khi traffic chuyển backend.

## 8. Health check: phân biệt alive, ready và thực sự phục vụ được

Health check là phép kiểm **backend có đủ điều kiện nhận traffic hay không**. Hai loại thường gặp:

- **Active health check:** LB chủ động gửi probe TCP, HTTP/HTTPS, gRPC health hoặc giao thức được hỗ trợ.
- **Passive health observation:** LB nhận biết lỗi từ traffic thực, như connection failure, reset hoặc một số status và timeout.

LB **L4 có thể dùng HTTP health probe** dù dataplane không đọc HTTP. Điều quyết định L4/L7 là **cách xử lý traffic người dùng**, không phải chỉ loại probe.

### 8.1. Liveness, readiness và health thực tế

| Kiểm tra | Điều đo được | Điều chưa được bảo đảm |
| --- | --- | --- |
| TCP port open | Có process/listener accept TCP | HTTP handler/DB/queue hoạt động đúng |
| HTTP 200 từ /healthz | Endpoint health trả lời thành công | Thanh toán/login/search hoạt động, dependency có thể bị mock |
| Readiness endpoint | Backend có thể tiếp nhận công việc theo logic ứng dụng | Toàn bộ dependencies ở mọi request đều khỏe |
| Deep synthetic probe | Một hành trình nghiệp vụ thử nghiệm hoàn thành | Tất cả nhóm user/region/tenant đều không lỗi |
| Passive error ratio | Những request thực quan sát có lỗi | Có thể bị ảnh hưởng bởi client errors, traffic lệch, sampling |

**Liveness và readiness có mục đích khác nhau.** Một ứng dụng còn sống nhưng đang khởi tạo cache, migration hoặc connection pool có thể **chưa ready**; LB không nên cấp traffic khi chưa có bằng chứng. Ngược lại, dùng deep health check có side effect hoặc phụ thuộc vào một dịch vụ shared đang lỗi có thể khiến **toàn bộ pool bị loại**, tạo outage lớn hơn.

### 8.2. Hysteresis và chống health flapping

~~~text
Health-check interval:    5 giây (ví dụ)
Unhealthy threshold:      3 lần thất bại liên tiếp
Healthy threshold:        2 lần thành công liên tiếp
Timeout:                  2 giây (ví dụ)
Action khi unhealthy:     Dừng cấp mới; xử lý existing flows theo policy
Action khi healthy:       Warm-up/slow-start rồi mới nhận tải đầy đủ
~~~

Đây chỉ là **số liệu minh họa**, không phải khuyến nghị mặc định. Quá nhạy gây flapping; quá chậm khiến traffic bị gửi tới node lỗi. Cần chọn threshold phù hợp **RTO, độ trễ backend, tải probe, failure domain và đặc tính giao thức**.

### 8.3. Khi tất cả backend đều unhealthy

Sản phẩm có thể **fail closed** (trả 503/không có destination), chọn **fallback pool**, dùng **last resort** hoặc có hành vi khác theo cấu hình. Không mặc định “gửi tới mọi backend kể cả unhealthy” là cách nâng availability. Trong hệ thống nhạy cảm, phải biết **fail-open/fail-closed semantics** và ảnh hưởng an ninh của fallback: không được fallback sang **Dev** hoặc backend không kiểm soát.

## 9. Connection, request, session và cơ chế persistence

**Một connection không phải một request.** HTTP/1.1 keep-alive có thể gửi nhiều request tuần tự trên một TCP connection; **HTTP/2** có thể multiplex nhiều streams đồng thời; **HTTP/3** dùng QUIC streams. Ngược lại, một hành trình người dùng có thể tạo nhiều connections.

### 9.1. Mỗi lớp có thể cân bằng theo đơn vị khác nhau

~~~text
L4 TCP:
  1 TCP connection (client ↔ VIP) -> backend A
  Các HTTP requests bên trong connection đó thường cùng backend A.

L7 HTTP/1.1:
  Request #1 -> backend A
  Request #2 -> backend B
  Nếu proxy xử lý từng request và policy cho phép.

L7 HTTP/2:
  Streams #1,#3,#5 trên một client connection
  có thể chọn upstream khác nhau nếu kiến trúc hỗ trợ.
~~~

**WebSocket** thường nâng cấp từ HTTP/1.1 sang một kết nối lâu dài (hoặc dùng các cơ chế tương ứng theo phiên bản HTTP); sau khi upgrade, LB cần duy trì backend cho session/stream phù hợp. gRPC **unary** và **streaming RPC** có vòng đời khác nhau: một backend bị drain có thể làm stream lâu bị kết thúc ngay cả khi health probe trả OK.

### 9.2. Sticky sessions / session affinity

| Cơ chế | Lợi ích | Rủi ro |
| --- | --- | --- |
| Source IP affinity | Không cần ứng dụng đổi code | CGNAT, roaming mobile, reverse proxy che IP nguồn |
| Cookie affinity của L7 | Dễ gắn một user/browser vào pool node | Cookie phải có thuộc tính Secure/HttpOnly/SameSite phù hợp, scope/lifetime rõ |
| Hash theo session/user ID | Duy trì locality theo identity | Key skew, PII, hot users, mapping đổi khi node rời |
| Shared session store | Backend stateless tương đối, dễ thay node | Dependency/latency và bảo mật kho session |

**Affinity không phải authorization.** Cookie hoặc header chọn backend không được cho phép user truy cập session của người khác. Nếu ứng dụng giữ toàn bộ session trên RAM của một node, chỉ thêm sticky routing chưa giải quyết **failover, node shutdown và loss of session**.

### 9.3. Connection draining và graceful shutdown

Khi deploy hoặc loại backend:

1. Mark backend **not ready / drain**, dừng cấp phiên/request mới theo khả năng LB.
2. Cho **in-flight requests/streams** hoàn tất trong deadline đã định.
3. Với HTTP/2/gRPC, dùng cơ chế đóng/kết thúc stream và **GOAWAY** theo hỗ trợ.
4. Với WebSocket/long-lived TCP, có chính sách timeout/reconnect; không chờ vô hạn.
5. Kiểm tra connection/request counters và ứng dụng có retry **an toàn/idempotent**.
6. Chỉ shutdown khi đạt tiêu chí; nếu cưỡng bức timeout phải ghi rõ tác động.

**Không retry bừa mọi POST/payment hoặc request có side effect.** Một response timeout không chứng minh backend chưa xử lý giao dịch; cần idempotency key/application contract để ngăn nhân đôi.

## 10. TLS termination, passthrough, SNI và ALPN

TLS là nơi L4/L7 khác biệt rõ nhất: **L7 cần đọc HTTP bên trong HTTPS**, nên thường cần terminate TLS ở một trust boundary hợp lệ; còn **TLS passthrough** có thể chỉ chuyển các byte TLS tới backend.

### 10.1. Ba sơ đồ phổ biến

~~~text
A. TLS passthrough:
  Client ==== TLS end-to-end at Backend ====> L4 LB ---> Backend
  L4 chọn flow; không giải mã nội dung HTTP.

B. TLS termination tại L7:
  Client == TLS == L7 proxy ---- HTTP trong mạng được kiểm soát ---> Backend
  Proxy đọc được HTTP; chặng backend không được TLS bảo vệ ở lớp này.

C. TLS re-encryption:
  Client == TLS #1 == L7 proxy == TLS #2 / mTLS == Backend
  Proxy đọc HTTP tại điểm termination và mở một phiên TLS khác.
~~~

**TLS termination ở L7 không tự đồng nghĩa mất mã hóa trên toàn bộ backend path**: re-encryption hoặc mTLS cho chặng backend là lựa chọn thiết kế. Mặt khác, **TLS passthrough** không tự chứng minh private key chỉ có ở backend nếu hệ thống khác vẫn có quyền truy cập key.

### 10.2. SNI và ALPN được nhìn thấy ở mức nào?

- **SNI (Server Name Indication):** Trong nhiều TLS handshakes, tên miền dự định có trong ClientHello và có thể được đọc để chọn backend **mà không cần giải mã HTTP**. Nếu **Encrypted ClientHello (ECH)** được hỗ trợ, tên thật có thể được bảo vệ; cần xem cơ chế fallback/outer name.
- **ALPN:** Thông tin đàm phán giao thức ứng dụng như h2/http/1.1 có phần hiển thị khác nhau tùy TLS version/ECH và handshake; không suy mặc định mọi trường luôn có thể đọc từ mọi điểm quan sát.
- **L4/SNI-aware passthrough:** Có thể quyết định theo ClientHello trước khi chuyển stream đã mã hóa tới backend, nhưng **không thể dùng HTTP path/Authorization header** nếu không terminate TLS.
- **TLS 1.3:** Nhiều thông tin handshake sau ServerHello được mã hóa; sensor không có secrets không thể tùy ý đọc certificate/payload trên dây.

### 10.3. Certificate validation trên từng hop

Một reverse proxy terminate HTTPS rồi mở TLS tới backend phải **xác minh chứng chỉ backend** (tên, chain, trust policy hoặc identity thích hợp), không chỉ bật TLS mà tắt verification. **mTLS** còn có thể xác thực proxy/workload phía client của hop backend.

Nếu proxy nhận client certificate, nó không nên đơn giản chuyển một header tùy ý như **X-Client-Cert** từ Internet và coi đó là identity. Chỉ proxy đã xác thực mới được **thiết lập lại metadata identity**, backend phải chỉ chấp nhận qua kênh được xác thực và đúng mạng tin cậy.

## 11. Giữ địa chỉ nguồn và chống header spoofing

Đối với network forensics, rate limiting và access control, backend cần biết **nguồn thực** của request. Nhưng sau một hoặc nhiều reverse proxies, source IP ở TCP socket thường là **IP của proxy gần nhất**.

### 11.1. X-Forwarded-For và chuẩn Forwarded

Ví dụ:

~~~text
Client thật:       198.51.100.50
CDN egress:        203.0.113.20
L7 proxy:          10.10.0.20
Backend TCP peer:  10.10.0.20

Một header X-Forwarded-For có thể chứa chuỗi:
  X-Forwarded-For: 198.51.100.50, 203.0.113.20
~~~

**X-Forwarded-For (XFF)** là header được dùng rộng rãi; chuẩn HTTP **Forwarded** có cấu trúc tương đương cho một số metadata. **Không header nào tự được bảo vệ bằng mật mã chỉ vì có mặt.** Client có thể tự gửi một XFF giả, và một reverse proxy có thể append thay vì xóa giá trị đã có.

### 11.2. Quy tắc trust chain

1. **Xác định các proxy/edge đáng tin** theo IP ranges/certificate/identity và đường mạng được bảo vệ.
2. Tại **trusted ingress đầu tiên** nhận traffic không đáng tin, **loại bỏ hoặc chuẩn hóa header nguồn client gửi** theo chính sách.
3. Thiết lập header metadata do chính ingress đo được; proxy tiếp theo append/normalize theo **chuỗi proxy tin cậy**.
4. Backend chỉ tin metadata khi TCP peer/identity là **proxy được phép**, không lấy “IP bên trái nhất” một cách mù quáng.
5. Đồng bộ IP ranges/identity của CDN khi chúng thay đổi, giới hạn trực tiếp **origin bypass**.
6. Giữ logs gồm **socket peer IP, trusted client IP, request ID, proxy chain và timestamp** để phân tích.

**Nguy hiểm:** Rate limit dựa vào XFF do Internet client tự đặt sẽ cho phép đối tượng gửi nhiều giá trị IP tùy ý để vượt quota, hoặc giả IP người khác gây khóa nhầm.

### 11.3. PROXY protocol

**PROXY protocol** (v1 dạng văn bản, v2 dạng nhị phân) được một số L4 LB/proxy dùng để chuyển metadata **địa chỉ nguồn/đích** tới backend ở đầu luồng kết nối, bên ngoài nội dung giao thức ứng dụng theo cơ chế cụ thể.

~~~text
Client -> L4 full proxy -> Backend

L4 proxy biết socket source của client.
LB đưa metadata nguồn qua PROXY protocol tới backend
nếu cả hai đầu đều được cấu hình và tin cậy.

Backend phải hiểu PROXY protocol trước khi đọc TLS/HTTP
theo thứ tự được sản phẩm hỗ trợ.
~~~

**PROXY protocol không mặc nhiên xác thực metadata.** Nếu backend công khai cổng chấp nhận PROXY protocol cho client Internet bất kỳ, họ có thể gửi **địa chỉ giả** như thể đến từ proxy. Cần **network allowlist, mTLS/identity hoặc ranh giới tin cậy tương ứng**, và không bật PROXY protocol trên backend chưa hiểu định dạng vì sẽ gây lỗi TLS/application.

### 11.4. Transparent proxy và DSR

Một số dataplane có thể **bảo toàn source IP** ở gói hoặc dùng transparent socket, còn DSR cho phép response đi thẳng. Đây là các lựa chọn về routing/connection ownership, không đồng nghĩa một header XFF phải có hay không; cần kiểm tra **source IP nhìn ở backend, route trả lời, NAT và security monitoring**.

## 12. Routing, NAT, ECMP và mạng bất đối xứng

LB không hoạt động độc lập với routing. Gói đi qua LB nhưng trả về một nhánh khác có thể làm **conntrack, NAT hoặc firewall stateful** không đủ dữ liệu.

### 12.1. Hai topology dễ nhầm

~~~mermaid
flowchart TB
    C["Client"] --> L["L4 NAT LB"]
    L --> A["Backend A"]
    A -->|"Return không qua LB/NAT owner"| R["Router B"]
    R --> C
~~~

Ở topology này, **return bypass L4 NAT LB** có thể làm gói trả về sai source VIP hoặc thiếu inverse NAT. Nhưng ở **DSR được thiết kế hợp lệ**, return trực tiếp lại là mục tiêu; phải biết chính xác **mode và state ownership**.

### 12.2. ECMP và flow hashing

Nếu có nhiều LB instances và một router ECMP phân phối traffic, hash theo 5-tuple có thể giữ một flow trên một node ở một chiều nhưng **không bảo đảm return chiều ngược** đi cùng node. Stateful LB cần **consistent flow steering, session/state sharing hoặc mô hình DSR/anycast** được thiết kế đúng.

Khi một next hop rời nhóm ECMP, một số flows có thể bị **rehashed** tới node khác. Đánh giá **RTO, session loss, NAT mapping, upstream/downstream route convergence** và hành vi client retry.

### 12.3. Source validation, uRPF và chống spoofing

**Strict uRPF** có thể loại một packet hợp lệ trong multi-homed/asymmetric topology nếu reverse best path tới source nằm trên interface khác. Đừng tắt chống giả mạo bừa; chọn **source ACL theo interface, feasible/loose mode theo thiết kế** hoặc chỉnh topology theo chính sách. Với transparent proxy/DSR còn phải xét nơi **source IP được giữ nguyên** và chính sách anti-spoofing tại backend/router.

### 12.4. DNS-based balancing khác per-flow LB

DNS có thể trả nhiều records hoặc hướng client tới VIP khác nhau theo vùng/health. Nhưng client/resolver **cache theo TTL và hành vi riêng**, không bảo đảm chuyển traffic ngay khi một backend hỏng, và DNS thường không nhìn vào mỗi HTTP request. **DNS steering** bổ sung cho L4/L7 LB, không thay connection draining hoặc health checks tại data plane.

## 13. HA, failover và các failure domain

Một LB đơn lẻ có thể trở thành **single point of failure**, dù phía sau có hàng chục backend. Cần tách:

- **Data plane:** nơi xử lý gói/connection/request thực.
- **Control plane:** nơi giữ cấu hình, health state, service discovery, certificates, weight, routes.
- **Failure domain:** host, rack, switch, power, zone, region, ISP, identity provider và các dependencies chung.

### 13.1. Active/passive và active/active

| Thiết kế | Lợi ích | Các điểm phải kiểm tra |
| --- | --- | --- |
| **Active/passive** | Một node xử lý chính, node dự phòng takeover | VIP/route move, fencing, state/NAT sync, RTO |
| **Active/active** | Nhiều nodes cùng xử lý traffic | ECMP/hash, flow ownership, capacity khi mất một node |
| **Managed regional LB** | Provider quản lý data-plane redundancy theo dịch vụ | Multi-AZ support, SLA, limits, health, client endpoint |
| **Cross-region LB / DNS steering** | Có vùng dự phòng trước region outage | Data replication, consistency, DNS TTL và failover ownership |

**Active/active không tự bảo đảm zero-downtime.** Một TCP flow lâu năm có thể reset khi backend hoặc LB owner mất; client/app phải có **reconnect, timeout và retry có kiểm soát**. Failover tốt nghĩa là đạt mục tiêu **RTO/SLO** trong các failure modes đã kiểm thử, không chỉ VIP đổi chủ.

### 13.2. Capacity N+1

Nếu một cụm gồm ba LB nodes chỉ đủ capacity khi **cả ba cùng khỏe**, khi mất một node cụm có thể lập tức quá tải. Hãy tính **capacity sau failure**, gồm cả:

- Connections concurrent, new connections per second (CPS), UDP flows.
- Throughput bps/pps, TLS handshakes per second, HTTP requests per second (RPS).
- CPU cho WAF/TLS/logging, RAM cho buffers/session state, NIC/IRQ và kernel limits.
- Số backend connections, pool sizes, ephemeral ports, NAT table và conntrack.
- Chi phí cross-zone/cross-region, shared cache/DB dependencies và quotas.

Đánh giá năng lực theo **cơ chế LB thực tế** và **ứng dụng**, không lấy tổng capacity datasheet rồi coi là công suất chắc chắn dưới mọi thuật toán.

### 13.3. Khi autoscaling tạo thêm nodes

Việc thêm backend không làm tăng capacity nếu DB hoặc external API đã nghẽn. Autoscaling cần gắn **readiness, warm-up, quota, pool draining, service discovery và giới hạn chi phí**. Đối với stateful apps, thêm node có thể làm mất cache affinity hoặc tạo session-store bottleneck.

## 14. Load balancing trong cloud, Kubernetes và hybrid network

### 14.1. Cloud L4 và L7

Các nhà cung cấp cloud thường có dịch vụ tương tự **network load balancer** cho TCP/UDP/TLS passthrough hoặc proxy, và **application load balancer** cho HTTP/HTTPS/gRPC. Tên, giới hạn, cách tính giá, tính năng NAT/source preservation, WAF và health probe khác nhau theo provider, service tier và region.

| Thuộc tính | Cần xác minh trong tài liệu nền tảng |
| --- | --- |
| Public/internal LB | Có thể đặt LB private chỉ trong VPC/VNet hay không |
| Protocol | TCP, UDP, TLS, HTTP/1.1, HTTP/2, HTTP/3, gRPC có được hỗ trợ trực tiếp không |
| TLS termination | Chứng chỉ, ciphers, mTLS, backend encryption, certificate verification |
| Backend target | VM IP, instance, container/Pod, endpoint group, serverless |
| Source identity | Client IP preservation, SNAT, XFF/Forwarded, PROXY protocol |
| Cross-zone | Traffic phân phối giữa AZs, costs và kết quả khi một AZ lỗi |
| Security controls | WAF integration, security groups/NSG, route tables, private endpoints |
| Observability | Access logs, flow logs, metrics, tracing, sampled logs và giới hạn retention |
| Quota/SLA | Throughput, CPS/RPS, listeners, backend connections và autoscaling |

**Không suy “L4 có source IP thật, L7 thì không” cho mọi cloud.** Một dịch vụ có thể giữ IP nguồn ở L4 tùy target mode, hoặc proxy bằng địa chỉ riêng; L7 có thể truyền địa chỉ qua metadata đáng tin. Luôn kiểm tra **TCP peer thực tế tại backend** trong đúng deployment mode.

### 14.2. Kubernetes Service, Ingress và Gateway API

Kubernetes có nhiều lớp trừu tượng:

- **Service:** khai báo tập endpoints và địa chỉ truy cập logic; phần thực thi L4 có thể qua kube-proxy, eBPF/CNI hoặc cơ chế cloud.
- **Service type LoadBalancer:** yêu cầu một hạ tầng điều khiển (cloud/controller) cung cấp LB bên ngoài hoặc nội bộ; **không mặc định** nó là L7.
- **Ingress:** tài nguyên khai báo luật HTTP/HTTPS, cần **Ingress controller** để thực thi; controller/triển khai có thể tạo L7 reverse proxy và tích hợp cloud LB.
- **Gateway API:** mô hình định tuyến và phân quyền theo tài nguyên như Gateway, HTTPRoute/TCPRoute (tùy hỗ trợ), do implementation/controller phù hợp thực thi.

~~~mermaid
flowchart TB
    U["Internet / Client"] --> N["Cloud or On-prem L4 LB"]
    N --> G["Ingress / Gateway implementation (L7)"]
    G -->|"HTTPRoute /api"| A["Service API"]
    G -->|"HTTPRoute /web"| W["Service Web"]
    A --> P["Pods / Endpoints"]
    W --> Q["Pods / Endpoints"]
~~~

**Chú ý:** Đây là **một** topology khả thi, không phải tất cả clusters đều cần cả hai lớp. Có ingress được exposure trực tiếp bằng một L7 managed LB; cũng có TCP route/passthrough hoặc service mesh tùy controller. **Gateway API resource không tự cung cấp data plane** nếu chưa có implementation.

### 14.3. NetworkPolicy và phân đoạn không tự xuất hiện nhờ ingress

Một Ingress hoặc Gateway cho phép Internet tới service **không tự chứng minh** backend bị cô lập khỏi nguồn khác. Cần xác định **NetworkPolicy/CNI enforcement**, security group/NSG, route/VPC, mTLS, role/service account và không cho truy cập trực tiếp tới backend ngoài đường được duyệt.

Ví dụ:

~~~text
Internet -> Public L7 LB -> Ingress Pods -> API Pods -> DB

Mục tiêu:
  Internet -> LB:443                         ALLOW
  LB/Ingress -> API:app-port                 ALLOW
  API identity -> DB:db-port                 ALLOW theo chính sách
  Internet/Guest/Dev -> DB:db-port           DENY
  Internet -> Origin API NodePort trực tiếp  DENY (trừ đường được duyệt)
~~~

Kiểm tra cả **IPv4/IPv6, internal/external LB, node IP, hostNetwork và Pod networking**. Một route công khai khác có thể vô tình bypass WAF/Ingress dù cấu hình HTTP routing chính đúng.

### 14.4. Hybrid và private service connectivity

Tổ chức có private circuit, VPN/SD-WAN và nhiều cloud regions thường có **L4 internal LB** trước các ứng dụng private; **L7 LB** định tuyến API theo path hoặc identity. Với hybrid cần rà soát **trùng CIDR, routing domain/VRF, source NAT, return path, TLS re-encryption và health check từ chính điểm traffic**.

Không giả định health check từ cloud LB trong một AZ đến backend thành công sẽ chứng minh on-prem client qua VPN có thể truy cập: chúng có thể đi **những tuyến và trust boundaries khác nhau**.

## 15. Mô hình hóa mối đe dọa với L4/L7

LB là **điểm tập trung lưu lượng**, do đó thường trở thành mục tiêu hoặc cơ hội để vượt ranh giới bảo mật. Tách rõ lỗi **availability**, **identity**, **confidentiality** và **authorization**.

| Kịch bản | Lớp liên quan | Rủi ro | Kiểm soát |
| --- | --- | --- | --- |
| **DDoS volumetric** bão hòa uplink | Trước L4/L7 | LB không nhận được gói hợp lệ dù backend khỏe | ISP/upstream scrubbing, Anycast/CDN theo thiết kế |
| **SYN/connection exhaustion** | L4/TCP | Cạn bảng state, socket, worker, memory | Syn protection/capacity/connection limits đúng phạm vi |
| **Slow HTTP / slow body** | L7 | Giữ socket/buffer dài, giảm throughput | Header/body timeouts, body limits, rate/buffer policy |
| **Host/path routing confusion** | L7 | Request tới admin/internal backend ngoài ý định | Host allowlist, normalize path, default deny, authorization |
| **Request smuggling/desync** | L7 và HTTP intermediaries | Các hop hiểu sai ranh giới request (CL/TE, HTTP version conversion) | Chuẩn hóa parsing, hardening, patching, test protocol translation |
| **Header spoofing** | L7/metadata | Giả IP client, identity/role, bypass quota | Strip/overwrite untrusted headers, trusted proxy chain |
| **PROXY protocol spoofing** | L4/backend metadata | Giả TCP source nếu backend nhận từ nguồn không tin | Hạn chế listener tới trusted LB, xác thực kênh |
| **Open proxy/SSRF** | L7/egress | Proxy bị lợi dụng truy cập metadata/internal endpoints | Không mở forward proxy, upstream allowlist, egress controls |
| **TLS termination downgrade** | L7/backend | Chặng backend plaintext hoặc không validate peer | mTLS/re-encrypt, certificate validation, TLS policy |
| **Origin bypass** | Network topology | Bỏ WAF/rate/auth và truy cập backend trực tiếp | Network ACL/SG, private origin, trusted ingress only |
| **Cross-tenant routing** | L7 multi-tenant | Tenant A vào dịch vụ/host của tenant B | Identity-aware authorization, route scope, tests |
| **DSR/asymmetric visibility** | L4/IDS | Firewall hoặc sensor chỉ thấy một chiều | Security choke points, monitoring cả chiều hoặc state design |
| **Health-check abuse** | Control plane/application | Probe gây side effect hoặc làm pool flapping | Read-only probes, threshold, authentication/limited access |
| **Control-plane compromise** | LB API/IaC | Thay target tới máy do attacker kiểm soát, đổi certificate/policy | MFA/RBAC, config review, audit, immutable deployment |
| **Log/secret leakage** | L7/access logs | Lộ Authorization, cookies, PII, cert keys | Redaction, retention, quyền đọc và bảo vệ secrets |

### 15.1. LB health status không chứng minh quyền truy cập đúng

Backend trả HTTP 200 cho /healthz chỉ chứng minh một phép kiểm đạt. Nó **không chứng minh** app tuân thủ least privilege, certificate backend được xác minh, Admin routes bị khóa hay traffic khách hàng hợp lệ không bị chặn nhầm.

### 15.2. Request smuggling và HTTP parsing

Khi nhiều proxies/backend parse HTTP khác nhau, chẳng hạn khi **chuyển HTTP/2 xuống HTTP/1.1** hoặc có cách hiểu khác nhau về **Content-Length, Transfer-Encoding, duplicate headers và request framing**, một request có thể được giải thích khác nhau giữa hai hop.

Phòng ngừa ở mức kiến trúc: **dùng phiên bản phần mềm đã vá, có parser chặt, chuẩn hóa/loại bỏ các tổ hợp header không hợp lệ, áp policy nhất quán và kiểm thử trên staging**. Không cần gửi payload tấn công tới hệ thống không thuộc quyền quản lý để xác minh nguy cơ.

### 15.3. Bảo vệ LB control plane

LB configuration thường cho phép đổi **backend IP/port, TLS certificate, WAF rules, response headers, routing, access logs và failover**. Vì thế thay đổi control-plane phải có **MFA, RBAC/ABAC, review, IaC drift detection, audit trail và rollback**. Không cho pipeline của Dev viết listener hoặc upstream Production chỉ vì cùng tài khoản cloud.

## 16. WAF, rate limiting, bot control và DDoS: chọn đúng tầng

### 16.1. L4/L7 xử lý các loại áp lực khác nhau

| Vấn đề | Điểm xử lý phù hợp | Điều cần tránh |
| --- | --- | --- |
| Bão hòa WAN bps/pps trước LB | ISP/upstream DDoS mitigation/CDN/Anycast phù hợp | Đợi tới L7 mới lọc khi link đã đầy |
| TCP SYN/connection surge | L4/SYN protection, connection quotas, upstream | Coi mọi IP có nhiều conn là attacker |
| HTTP request flood một endpoint | L7 rate limit, cache, app circuit breaker và WAF | Chặn theo IP toàn site khiến CGNAT khách hàng bị khóa |
| Bot traffic mang HTTP hợp lệ | Bot mitigation và hành vi/identity theo scope | Dùng một quy tắc user-agent đơn giản làm kết luận |
| Backend DB pool cạn | L7 admission control, bounded queues, app/DB capacity | Autoscale web vô hạn làm DB cạn nặng hơn |
| HTTP protocol exploit | L7 WAF/patch ứng dụng, input validation | Dựa hoàn toàn vào L4 vì “đã có LB” |
| Origin bị gọi trực tiếp | Network ingress policy/ACL/private endpoint | Tin rằng DNS chỉ công bố CDN là đủ bảo vệ origin |

### 16.2. Rate limit theo identity và chi phí request

Một địa chỉ IP có thể đại diện cho **hàng nghìn user qua CGNAT**, còn một người dùng có thể có nhiều IP. L7 có thể dùng **authenticated user/tenant/API key**, đường dẫn, loại request, quota và hành vi để đánh giá chính xác hơn; nhưng metadata cũng phải được xác thực.

**Token bucket/leaky bucket** là các mô hình hạn chế tốc độ thường gặp. Dùng rate limit riêng cho **đăng nhập, tìm kiếm, báo cáo, upload, checkout** theo nhu cầu/nguy cơ; gắn với SLI để thấy false positives. Thao tác chặn/cấp challenge phải có **owner, phạm vi, TTL và rollback**.

### 16.3. Một mục tiêu an ninh, hai metric bắt buộc

Sau khi bật mitigation hãy đo:

1. **Áp lực tài nguyên có giảm?** Bps/pps, connections, backend RPS, CPU, DB queue.
2. **Người dùng hợp lệ có dùng dịch vụ tốt hơn không?** Login/checkout/API success, p95/p99, false-positive 403/429, conversion.

**Request volume giảm không đủ chứng minh thành công**, vì rule có thể đang chặn cả request hợp lệ.

## 17. Capacity planning, queueing và nguy cơ “LB khỏe nhưng app chết”

LB thường có ít nhất hai đường capacity: **front side client ↔ LB** và **back side LB ↔ upstream**. Một proxy có thể accept được 100.000 sockets nhưng ứng dụng chỉ xử lý được một phần nhỏ throughput mong muốn.

### 17.1. Các đại lượng cần tách

| Metric | Định nghĩa | Đơn vị |
| --- | --- | --- |
| **CPS** | New TCP connections mỗi giây | connections/s |
| **Concurrent connections** | Số connections đang mở cùng lúc | connections |
| **RPS** | HTTP requests mỗi giây | requests/s |
| **Active requests/streams** | Số request/stream đang xử lý đồng thời | requests/streams |
| **Throughput** | Bytes/bit truyền theo thời gian | B/s hoặc bps |
| **PPS** | Packets mỗi giây | packets/s |
| **Latency p95/p99** | Phân vị thời gian phản hồi theo phạm vi đo | milliseconds |
| **TLS handshakes/s** | Khả năng thiết lập khóa/kênh TLS mới | handshakes/s |
| **Upstream queue** | Request chờ lấy connection/worker | count/time |
| **Error/drop rates** | Tỷ lệ lỗi theo loại: 5xx, reset, reject | %/s |

### 17.2. Ví dụ Little's Law

Trong một hệ thống ổn định và với **định nghĩa đơn vị thống nhất**:

\[
L = \lambda W
\]

Ở đây \(L\) là số công việc trung bình đang nằm trong hệ thống, \(\lambda\) là thông lượng trung bình (request/giây) và \(W\) là thời gian trung bình một công việc ở trong hệ thống (giây).

Giả sử có **200 requests/giây**, mỗi request trung bình chiếm **0,15 giây** từ lúc nhận đến khi hoàn thành trong cùng ranh giới đo:

\[
L = 200 \times 0{,}15 = 30 \text{ requests đang ở trong hệ thống (trung bình).}
\]

**Không suy từ kết quả này rằng máy chủ chỉ cần 30 TCP sockets hay 30 workers.** Request concurrency khác TCP connection count; HTTP/2 multiplexing, timeout, queueing, bursts, retry và tail latency có thể khiến mức đỉnh lớn hơn trung bình rất nhiều.

### 17.3. Các nút nghẽn “ẩn sau LB”

- Backend connection pool giới hạn, nhưng LB không giới hạn queued requests.
- TLS termination/WAF chạy ở CPU LB; backend chưa kịp thấy request.
- HTTP/2 một connection nóng chứa hàng trăm streams, least connections chọn sai backend.
- DB/Redis/message queue đã cạn; thêm backend làm dependency nặng hơn.
- DNS/service discovery trả endpoint cũ; health logic chưa loại.
- Cụm autoscaling chưa warm cache hoặc còn migration/readiness.
- NAT/SNAT port exhaustion, ephemeral port/time-wait, kernel conntrack limits.

**Giải pháp không chỉ là thêm LB.** Cần *backpressure*, bounded queue, connection/request limits, timeout budgets và circuit breaker theo thứ tự ưu tiên nghiệp vụ.

## 18. Kiến trúc phòng vệ nhiều lớp cho một public API

~~~mermaid
flowchart LR
    USER["Internet Client"] --> EDGE["Upstream DDoS / CDN"]
    EDGE --> NLB["L4 LB / TCP entry"]
    NLB --> ALB["L7 Reverse Proxy / WAF"]
    ALB --> API["API service pool"]
    API --> DB[("Database")]
    ALB -. "Auth + Rate limit" .-> POL["Identity / Security policy"]
~~~

Sơ đồ dùng **cả L4 và L7** để minh họa, không có nghĩa mọi tổ chức cần đầy đủ từng hộp. Trong thực tế CDN có thể đã làm L7/WAF, provider managed application LB có thể xử lý listener trực tiếp, còn internal LB có thể nằm sau ingress.

### 18.1. Ma trận dữ liệu và quyền

| Luồng | Kết quả mong muốn | Điểm thực thi |
| --- | --- | --- |
| Client → Public endpoint TCP/443 | ALLOW theo policy | Edge/L4/L7 ingress |
| Client → Origin API IP trực tiếp | DENY trừ đường quản trị được duyệt | Firewall/SG/private network |
| Client → /admin | DENY nếu không có auth và quyền tương ứng | L7 + ứng dụng |
| L7 proxy → API ports cần thiết | ALLOW | NetworkPolicy/SG + workload identity |
| API → DB đúng principal/port | ALLOW theo least privilege | DB auth + network policy |
| Dev/Guest → Prod DB | DENY | Segmentation/route/firewall |
| LB logs → log collector | ALLOW theo kênh bảo mật có kiểm soát | IAM/mTLS/retention |
| Arbitrary Internet → LB management API | DENY | Management network/IAM |

### 18.2. Các bất biến trước khi coi kiến trúc an toàn

1. **Không có đường origin bypass** đi vòng điểm WAF/identity bắt buộc.
2. Mọi trust headers (client IP, client cert identity, role) chỉ được **thiết lập bởi proxy đáng tin**.
3. Các chặng TLS có **peer validation**, quyền đọc certificate/secret phù hợp.
4. Route và source IP/NAT không gây **asymmetric stateful drops** hoặc IDS visibility gaps.
5. Health, canary và fallback **không đưa request Prod sang Dev** khi Prod lỗi.
6. Cụm vẫn có capacity và giữ policy khi **mất một LB/backend/AZ** theo mục tiêu HA.

## 19. Triển khai và rollback thay đổi LB

### 19.1. Quy trình từ thiết kế tới production

1. **Xác nhận yêu cầu:** protocol, endpoints, owner, peak CPS/RPS, p95/p99 SLO, sessions, TLS và security zone.
2. **Vẽ data flow:** source/dest, NAT, TLS termination, XFF/PROXY protocol, route return, firewall/IDS position.
3. **Chọn L4/L7 dataplane:** hiểu giới hạn TCP/UDP/HTTP2/HTTP3, phần nào được parse và được mã hóa.
4. **Chọn thuật toán:** RR/weighted/least requests/hash theo tải thực; xác định pool weights và persistence.
5. **Thiết lập health/readiness:** tránh probes có side effect và tất cả backend bị loại đồng thời do dependency chung.
6. **Chốt policy:** Host/path allowlist, auth, WAF, TLS-to-origin, trusted headers, rate limit, logging redaction.
7. **Đánh giá HA/capacity:** N+1 hoặc headroom theo yêu cầu, dự phòng AZ/route và LB failover.
8. **Kiểm thử staging:** ứng dụng ALLOW, luồng DENY, DDoS false-positive, backend drain và failover trong phạm vi phép thử.
9. **Deploy canary:** thay đổi nhỏ, đo metrics, nhật ký và tác động business trước mở rộng.
10. **Readback:** so sánh running config/API/observed routes với IaC/change record; cập nhật sơ đồ và runbook.

### 19.2. Mẫu change ticket

~~~text
CHANGE ID / UTC TIME:
OWNER / APPROVER:
SERVICE / ENVIRONMENT / ZONE:
CURRENT: L4/L7 architecture, VIP/listeners, pools and weights
PROPOSED: exact route/backend/TLS/security changes
EXPECTED: application SLO and traffic distribution
RISKS: 502/503/504, retry storm, NAT, sticky sessions, header spoofing
SECURITY: ALLOW/DENY, origin bypass, XFF trust, TLS backend validation
HEALTH: probes, thresholds, draining/warm-up
ROLLBACK: previous config, listener/route restoration, state behavior
MONITORING: front/backend connections, latency, error, saturation
READBACK: deployed state + application and firewall test evidence
~~~

**Không chỉ rollback file config.** Nếu đã đổi DNS/route, cookie affinity, certificate, backend registration hoặc NAT table, cần biết **trạng thái nào không hoàn nguyên tức thì**, và các phiên hiện tại có thể cần reconnect. Mọi thay đổi phải có người vận hành/điều phối rõ ràng.

## 20. Chẩn đoán lỗi L4/L7 theo chứng cứ

Trước khi chỉnh cấu hình hãy xác định **client, protocol, hostname/VIP, source/destination IP:port, thời điểm UTC, zone, request ID và hành trình người dùng**. Lỗi “không vào được website” có thể ở DNS, TCP, TLS, HTTP routing, backend, dữ liệu hoặc authorization.

### 20.1. Cây phân tích theo lớp

~~~mermaid
flowchart TD
    A["Client không dùng được dịch vụ"] --> DNS{"DNS trả đúng VIP/endpoint?"}
    DNS -- "Không" --> D["DNS, cache, zone, health steering"]
    DNS -- "Có" --> TCP{"TCP/UDP tới VIP có đi được?"}
    TCP -- "Không" --> N["Route, ACL, L4, NAT, SYN/flow limits"]
    TCP -- "Có" --> TLS{"TLS/ALPN đúng?"}
    TLS -- "Không" --> T["Certificate/SNI, ciphers, backend TLS"]
    TLS -- "Có" --> HTTP{"HTTP/gRPC request đúng route?"}
    HTTP -- "Không" --> P["L7 rules, Host/path, auth/WAF, retries"]
    HTTP -- "Có" --> APP["Backend readiness, DB, queues, SLI"]
~~~

**Sơ đồ là trình tự triage**, không khẳng định mỗi lỗi chỉ thuộc một hộp. Ví dụ DNS cache cũ và WAF false-positive có thể cùng xuất hiện; TLS termination có thể ở CDN chứ không phải LB được kiểm tra.

### 20.2. Các triệu chứng thường thấy

| Triệu chứng | Giả thuyết ban đầu | Bằng chứng nên thu |
| --- | --- | --- |
| TCP handshake timeout tới VIP | Route/ACL/uRPF/SYN backlog, L4 không có listener | Packet/flow counters và route cả hai phía |
| TCP reset ngay sau connect | Listener/proxy/backend reset, protocol mismatch, conn limits | Client + LB + backend event correlation |
| TLS certificate mismatch | SNI, default certificate, backend trust | Negotiated SNI, cert identity, trust validation |
| HTTP **502 Bad Gateway** | Proxy nhận phản hồi upstream không hợp lệ hoặc upstream connection/protocol failure | LB upstream error detail, backend log, TLS-to-origin |
| HTTP **503 Service Unavailable** | Pool empty/unhealthy, overload, maintenance hoặc app trả 503 | Healthy targets, admission policy, backend status |
| HTTP **504 Gateway Timeout** | Proxy không nhận kịp response upstream trong thời hạn | Proxy timeout, backend service latency, network loss |
| HTTP **403 Forbidden** | WAF/auth/authorization policy hoặc app | Rule ID, identity, false-positive scope |
| HTTP **429 Too Many Requests** | Rate limit tại edge/L7/app hoặc quota tenant | Quota key, trusted client IP, retry policy |
| Một nhóm user lỗi sau CDN | Origin bypass, IPv4/IPv6, region/edge, cookie affinity | Endpoint/region distribution, header chain, DNS |
| WebSocket rớt sau vài phút | Idle timeout, heartbeat, drain/rollout | Connection lifetime, LB/backend timeout, close code |
| gRPC stream lỗi nhưng HTTP probe OK | HTTP/2 upstream, trailers, deadline, streaming behavior | gRPC status, h2 logs, stream concurrency |
| Chỉ request lớn lỗi | Body limits, timeout, proxy buffering, PMTU | Content-Length, upload size, upstream response/counters |

HTTP status ở bảng thể hiện **ý nghĩa thường gặp**, không phải mọi sản phẩm đều phát mã giống nhau. Ví dụ **499** thường là status/log code không chuẩn của một số reverse proxy cho client đóng kết nối; **gRPC status** có thể nằm trong **trailers** dù HTTP status là 200. Phải xem **nơi phát status và request ID** trước khi gán nguyên nhân.

### 20.3. Tách lỗi frontend và backend

~~~text
Client:
  DNS A/AAAA, VIP, TCP connect, TLS validation, HTTP request ID

LB Frontend:
  listener, protocol, client peer IP, TLS/SNI, WAF/auth decision

LB Upstream:
  selected pool/backend, connection attempt, retries, response timing

Backend:
  request ID, application logs, DB/dependency calls, resource usage

Network:
  route forward/return, NAT/conntrack, firewall allow/deny, IPS visibility
~~~

Không phải mọi luồng cần packet capture. Trước hết dùng **application metrics, proxy access/error logs, cloud flow logs, routing snapshots**. Nếu capture cần thiết, chỉ thu ở **interface, filter, time window được ủy quyền**, loại bỏ tokens/cookies/PII khi có thể.

### 20.4. Nguyên tắc kiểm tra retry

Nếu request POST timeout, **không tự retry vô hạn**: backend có thể đã commit giao dịch nhưng response bị mất. L7 retry theo method/status/timeout phải có **idempotency contract**, idempotency keys khi phù hợp, retry budget, jitter/backoff và giới hạn số lần.

## 21. Thực hành Python offline: phân phối pool và route HTTP

Bài lab dưới đây **chỉ sử dụng dữ liệu mô phỏng trong bộ nhớ**, không tạo socket, không gửi request, không cấu hình proxy hoặc thực thi firewall. Mục tiêu là minh họa **weighted round robin trên backend đủ điều kiện**, cùng cách L7 chọn pool theo hostname/path.

### 21.1. Code mô phỏng

~~~python
from dataclasses import dataclass


@dataclass(frozen=True)
class Backend:
    name: str
    weight: int
    ready: bool
    draining: bool = False


def choose_backend(pool: list[Backend], request_index: int) -> str | None:
    """Weighted RR đơn giản để học, KHÔNG phải data plane production."""
    eligible = [
        node for node in pool
        if node.ready and not node.draining and node.weight > 0
    ]
    schedule = [
        node.name for node in eligible for _ in range(node.weight)
    ]
    if not schedule:
        return None
    return schedule[request_index % len(schedule)]


def route_http(host: str, path: str) -> str | None:
    """Minh họa chọn pool theo HTTP, không thực hiện normalization/auth."""
    if host == "api.example.org" and path.startswith("/v1/"):
        return "api"
    if host == "shop.example.org" and path.startswith("/checkout"):
        return "checkout"
    if host == "shop.example.org" and path.startswith("/assets/"):
        return "static"
    return None  # Unknown host/path: không route vào admin/default nhạy cảm


pool = [
    Backend("api-a", weight=3, ready=True),
    Backend("api-b", weight=2, ready=True),
    Backend("api-c", weight=1, ready=True),
]

print("normal:", [choose_backend(pool, i) for i in range(6)])

drain_pool = [
    Backend("api-a", weight=3, ready=True),
    Backend("api-b", weight=2, ready=True, draining=True),
    Backend("api-c", weight=1, ready=True),
]
print("draining:", [choose_backend(drain_pool, i) for i in range(4)])

print("route API:", route_http("api.example.org", "/v1/orders"))
print("route unknown:", route_http("unknown.example.org", "/admin"))

assert choose_backend(pool, 0) == "api-a"
assert choose_backend(pool, 5) == "api-c"
assert choose_backend(drain_pool, 3) == "api-c"
assert route_http("unknown.example.org", "/admin") is None
~~~

Kết quả dự kiến:

~~~text
normal: ['api-a', 'api-a', 'api-a', 'api-b', 'api-b', 'api-c']
draining: ['api-a', 'api-a', 'api-a', 'api-c']
route API: api
route unknown: None
~~~

### 21.2. Cách đọc kết quả

- Trọng số 3:2:1 tạo **lịch lựa chọn minh họa** gồm 6 slot; không đo latency/CPU thực.
- Khi backend B **draining**, nó không nhận request mới theo mô hình; code **không mô phỏng** connection cũ vẫn còn trên B.
- Host/path routing trả **None** khi không khớp, thay vì vô tình gửi request lạ tới admin/backend mặc định.
- Kết quả **không hề chứng minh bảo mật**: code không parse HTTP thật, không xác thực JWT/TLS, không normalize path, không chống smuggling hay tự phân biệt XFF đáng tin.

### 21.3. Những giới hạn cần nhớ

1. **Không phải smooth weighted RR**: lịch có những backend lặp liền nhau; một số LB phân phối đều hơn trong ngắn hạn.
2. Không có **distributed state** giữa LB nodes; request_index ở hai nodes có thể không đồng bộ.
3. Không xét **TCP connection affinity, HTTP/2 streams, retries, concurrency hay upstream timeouts**.
4. **Thay đổi eligible pool** làm lịch phân phối đổi; đang drain node không tự di chuyển state của user.
5. **Path check đơn giản không an toàn cho production**: URL encoding, percent decoding, Unicode, dot segments, case, duplicate headers và URI canonicalization phải do HTTP stack/policy chuẩn xử lý.
6. Không đánh giá **header spoofing, PROXY protocol, NAT, WAF, authorization**, hoặc TLS certificate.

### 21.4. Bài tập mở rộng

1. Thêm backend **api-d** có weight 4; tính tỉ lệ lượt chọn dự kiến.
2. Đặt tất cả backend **ready=False**; chương trình nên trả về gì và LB production phải xử lý thế nào?
3. Thêm trường **active_requests** và mô hình least-requests; giải thích tại sao concurrency không hoàn toàn bằng CPU usage.
4. Viết bản ghi mô phỏng **trusted_proxy=False** và chỉ ra vì sao không được dùng XFF từ Internet làm client identity.
5. Thêm một test route HTTP với **unknown Host** và chứng minh không rơi vào admin backend.
6. Xây dựng mô hình **backend draining** có deadline cho in-flight requests, tách khỏi chọn backend cho request mới.
7. Thêm metric **backend 5xx và retry budget**, nhưng chỉ ghi cảnh báo, tuyệt đối không tự tạo traffic vào Internet.

## 22. Hai case study minh họa

### 22.1. Case study A — ECMP và L4 NAT sau failover

**Bối cảnh:** Hai L4 NAT LB nodes đứng sau ECMP. Khi node A hỏng, router bắt đầu gửi traffic mới và một số flow cũ sang B. **B không có NAT/conntrack state của flow cũ**, trong khi backend có thể đang trả response về đường qua A hoặc theo route cũ.

| Quan sát | Giải thích có thể | Bằng chứng |
| --- | --- | --- |
| TCP connect mới thành công, socket cũ reset | Không bảo toàn state cũ trên node B | Session/NAT counters, client reset/retransmission |
| Backend trả response nhưng client không thấy | Sai inverse NAT hoặc return route | Flow logs trước/sau LB, gateway FIB |
| Ping VIP vẫn OK | VIP reachable, không chứng minh TCP session continuity | Test TCP và ứng dụng, không chỉ ICMP |
| IDS thấy request mà không có response | Return path đi nhánh khác | Sensor placement và packet correlation |

**Hướng xử lý:** Thiết kế **flow ownership/state sharing hoặc cơ chế consistent routing được hỗ trợ**, health/failover có kiểm soát, N+1 capacity, kỳ vọng client reconnect và đo ứng dụng. Không bật **ACCEPT mọi out-of-state** trên firewall chỉ để giảm reset.

**Thử an toàn:** Trong lab, mô phỏng mất node và ghi flow mới/cũ, route, NAT, session drop, application success và **DENY**. Nếu có HA managed service, đọc giới hạn của vendor; không suy mọi LB tự bảo toàn TCP session khi failover.

### 22.2. Case study B — Dùng X-Forwarded-For chưa kiểm soát để giới hạn đăng nhập

**Bối cảnh:** Một public API đặt sau CDN và L7 reverse proxy. Application rate limiter lấy **IP đầu tiên trong X-Forwarded-For** làm identity mà không biết header này có thể được client bên ngoài tự gắn. Kết quả: chính sách chặn có thể bị qua mặt, và người dùng đi qua NAT dùng chung địa chỉ bị khóa nhầm.

~~~text
Request từ Internet:
  TCP peer đến CDN = 198.51.100.50
  Client tự gửi X-Forwarded-For: 192.0.2.99

Nếu edge không loại bỏ/chuẩn hóa header không tin cậy:
  Backend có thể tưởng client thật = 192.0.2.99.

Rủi ro:
  Rate limit theo "client IP" không còn đáng tin,
  audit mapping sai, điều tra nguồn tấn công khó khăn.
~~~

**Hướng xử lý phòng vệ:** Tại trusted ingress đầu tiên, **overwrite/strip header nguồn không đáng tin**, dùng cấu hình trusted proxy chain theo địa chỉ/identity của CDN/LB, không cho public client gọi origin trực tiếp; rate limit nhạy cảm nên dựa vào **authenticated user/tenant/API key** khi phù hợp. Ghi nhận socket peer và sanitized client IP để điều tra.

**Bài học:** L7 có thể cung cấp metadata phong phú hơn L4, nhưng metadata ấy phải có **nguồn xác thực và trust boundary rõ**; thêm header không tạo ra tính xác thực.

### 22.3. Case study C — Pool khỏe nhưng checkout thất bại

**Bối cảnh:** Health endpoint /healthz chỉ kiểm tra process và trả HTTP 200. Sau một đợt traffic cao, DB connection pool cạn; LB tiếp tục gửi toàn bộ checkout requests tới những ứng dụng “healthy” và nhận hàng loạt 5xx.

**Phân tích:** Đây không nhất thiết là lỗi thuật toán load balancing. Backend readiness và ứng dụng không phản ánh **dependency saturation**, trong khi autoscale web có thể càng tăng tải DB.

**Hướng cải tiến:** Theo dõi checkout SLI, DB pool/queue, admission control, circuit breaker, bounded retries, cache hợp lệ và giới hạn công suất. Không thay mọi health checks bằng truy vấn ghi DB có side effect; thiết kế dependency-aware readiness có guardrail để tránh **cả pool mất health đồng thời**.

## 23. Ma trận kiểm thử load balancing và bảo mật

Chỉ kiểm thử trên **lab, staging hoặc tài sản thuộc quyền quản lý**, đúng phạm vi và thay đổi được phê duyệt. Các tình huống làm gián đoạn mạng, ép failover, DDoS, TCP exhaustion hoặc gửi request giao thức bất thường không được thực hiện trên Internet hay Production nếu chưa có kế hoạch/ủy quyền.

| Test ID | Tình huống | Kết quả và bằng chứng mong đợi |
| --- | --- | --- |
| LB-01 | L4 cân bằng TCP giữa 3 backend | Flow được gán ổn định; success/error và backend flow logs phù hợp |
| LB-02 | L4 cân bằng UDP | Phân phối theo flow/timer chính xác, request/response hợp lệ |
| LB-03 | L4 DNAT và reverse NAT | Client nhận response từ VIP, state không bị mismatch |
| LB-04 | L4 DSR trong lab | Backend trả trực tiếp đúng source, stateful policy không bị bypass |
| LB-05 | L4 full-proxy | Hai TCP connections hoạt động, source identity được ghi đúng |
| LB-06 | L7 host/path routing | api.example.org /v1 tới API, /assets tới Static theo policy |
| LB-07 | Unknown Host/authority | Không route nhầm tới admin/internal/default backend nhạy cảm |
| LB-08 | TLS passthrough tới backend | LB không giải mã HTTP; backend xác thực chứng chỉ và xử lý TLS |
| LB-09 | TLS termination + re-encryption | Edge/backend certificate validation đúng, không chấp nhận peer sai |
| LB-10 | Trusted XFF/Forwarded chain | Backend xác định nguồn thực từ ingress hợp lệ, không từ client tự khai |
| LB-11 | Client giả XFF/identity headers trong lab | Không vượt authentication, quota hoặc audit mapping |
| LB-12 | PROXY protocol backend listener | Chỉ trusted LB gửi metadata; nguồn khác không thể giả source |
| LB-13 | Backend unhealthy | Không có request mới đến backend bị loại theo policy |
| LB-14 | Backend recovering | Slow-start/readiness tránh dồn tải đột ngột |
| LB-15 | Toàn bộ backend unhealthy | Hành vi 503/fallback/fail-closed đúng chính sách đã công bố |
| LB-16 | Weighted RR với cấu hình tĩnh | Distribution phù hợp trọng số ở lượng mẫu đủ lớn |
| LB-17 | HTTP/2, gRPC unary và streaming | Proxy hỗ trợ đúng HTTP/2 upstream, trailers, deadlines, stream lifecycle |
| LB-18 | WebSocket long-lived connection | Idle timeouts/heartbeat/draining phù hợp, không reset ngoài dự kiến |
| LB-19 | HTTP/3/QUIC được bật | Lớp xử lý QUIC/HTTP3 tương thích, không coi UDP L4 là WAF HTTP tự động |
| LB-20 | Backend graceful shutdown/deploy | Không cấp request mới; in-flight requests được xử lý trong deadline |
| LB-21 | L4 node failover/ECMP | Route/NAT/session mới và cũ được đo, không vòng lặp hay bypass |
| LB-22 | Cross-AZ hoặc region failure tabletop | Capacity và health steering theo kế hoạch, không chuyển dữ liệu sai vùng |
| LB-23 | IPv4 vs IPv6 listener | TLS, routing, WAF và origin protection không khác ngoài ý định |
| LB-24 | Origin backend trực tiếp từ Internet | **DENY** trừ tuyến được phê duyệt |
| LB-25 | Guest/Dev → Prod DB qua đường không đúng | **DENY** trên cả đường chính và đường failover |
| LB-26 | WAF rate limit gây false positive trong staging | Có audit rule, đo user impact, rollback đúng scope |
| LB-27 | Authenticated vs unauthenticated /admin | ALLOW chỉ cho đúng identity/role; mọi trường hợp khác DENY |
| LB-28 | HTTP parser/normalization conflict ở lab | Proxy/backend thống nhất ranh giới request hoặc loại input không hợp lệ |
| LB-29 | Request POST timeout và retry policy | Không nhân đôi giao dịch có side effect khi thiếu idempotency |
| LB-30 | Rollback listener/TLS/backend pool/route | Đường đi và security policy trở lại trạng thái dự kiến, có readback |

### 23.1. Mẫu bằng chứng cho mỗi ca

~~~text
TEST ID:
Service / environment / region:
Time UTC / owner / approval:
Client source IP:port / VIP / protocol:
Expected L4 or L7 behavior:
TLS hop / HTTP authority / request ID:
Backend selection / pool health:
NAT / source identity / trusted proxy chain:
Security zone / expected ALLOW or DENY:
Application outcome (SLI):
Route, access, error and security logs:
Rollback / remaining risk:
~~~

**Yêu cầu hai chiều:** Kiểm thử **người dùng hợp lệ truy cập thành công** và **đường trái quyền vẫn bị chặn**. Một hệ thống có thể trả HTTP 200 vì đã bypass WAF; chỉ số availability riêng lẻ không chứng minh thiết kế an toàn.

### 23.2. Kiểm tra chênh lệch giữa giả lập và triển khai thật

Bài lab Python ở mục 21 chỉ dự đoán **lựa chọn của một lịch trọng số**. Bản triển khai phải đo **actual requests/flow counts, origin health, retry behavior, TLS, source identity, routing và latency**. Không dùng tỷ lệ phân phối giữa 6 request mô phỏng làm bằng chứng N+1 capacity hoặc công bằng thực tế.

## 24. Giám sát, logging và runbook vận hành liên tục

### 24.1. Phân biệt các phép đo frontend và upstream

| Nhóm | Metric/telemetry | Câu hỏi cần trả lời |
| --- | --- | --- |
| Frontend traffic | Connections, CPS, RPS, PPS, bps, protocol versions | LB đang nhận bao nhiêu công việc? |
| Frontend errors | TCP resets, TLS handshake failures, 4xx/5xx, 429 | Người dùng bị lỗi tại lớp nào? |
| Backend health | Healthy/unhealthy count, readiness, flaps | Pool có đủ targets phục vụ? |
| Upstream latency | Connect time, time-to-first-byte, request duration | Thời gian nằm ở proxy hay backend? |
| Queue/buffers | Pending requests, proxy buffer usage, memory | Đang backpressure hay cạn tài nguyên? |
| Balancing behavior | Chọn backend, weight, connection/request skew | Traffic có tập trung bất thường? |
| TLS | Certificate expiry, cipher/version, backend verification | Các TLS hops có bảo vệ đúng không? |
| NAT/route | Conntrack, SNAT port usage, ECMP next hops | Có nguy cơ return path lỗi hoặc state loss? |
| Security | WAF rule hits, block/challenge, auth decision, origin bypass | Có chặn sai hay thiếu enforcement? |
| Business SLI | Login, checkout, API success, p95/p99 | Người dùng hợp lệ có đạt SLO? |

**Không giữ nguyên văn mọi HTTP headers/body trong logs.** Authorization tokens, cookies, PII, client certificates và URL query chứa thông tin nhạy cảm có thể bị lộ nếu ingest toàn bộ. Cần **redaction, data minimization, access controls và retention** theo chính sách.

### 24.2. Correlation theo request ID

Một trace tốt có thể gắn:

~~~text
UTC:               2026-01-10T09:15:00Z
Request ID:        req-example-001
Client socket IP:  198.51.100.50
Trusted client IP: theo metadata CDN được xác thực
Edge location:     region-a
Listener/VIP:      203.0.113.10:443
Protocol:          HTTPS / HTTP/2
LB rule:           api-v1-route
Selected backend:  api-a / upstream pool
WAF/Auth decision: allowed / policy-id
Proxy response:    200
Backend response:  200
Duration:          total, upstream, queue (theo metric có sẵn)
~~~

Không dùng request ID do Internet client tự cấp như bằng chứng toàn vẹn nếu không có cơ chế **trusted ID generation/validation** tại ingress. Khi qua nhiều proxies, cần đồng bộ timestamp/trace IDs và định nghĩa **scope của client IP trước/sau NAT**.

### 24.3. Quy trình vận hành khi tăng lỗi

1. **Xác nhận tác động:** SLI ứng dụng, khách hàng/đối tác, region/zone, bắt đầu lúc nào.
2. **Chọn lớp lỗi:** DNS/VIP, transport, TLS, HTTP/L7 policy, upstream/backend, dependency.
3. **Kiểm tra change history:** cert, routing, WAF, backend weights, pool registration, autoscale, deployment.
4. **Thu logs của đúng điểm:** Frontend và upstream metrics, selected backend, identity/rule ID, route/NAT nếu có.
5. **Khoanh chính xác:** Có ảnh hưởng theo hostname, path, protocol, IPv6, tenant, edge zone, source ASN hay một backend?
6. **Giảm tác động có phê duyệt:** Drain node lỗi, giảm quota/hạn chế traffic phù hợp, rollback route/policy đã biết sai.
7. **Xác minh hậu thay đổi:** ALLOW/ DENY, giao dịch thực, false positives, TLS và backend data consistency.
8. **Handoff/postmortem:** Lưu timeline, owner, root cause/unknowns, action items và kiểm tra lại.

**Không được nới lỏng identity validation, bật open proxy, tắt mọi WAF hoặc tạm công khai origin** chỉ để che triệu chứng mà chưa đánh giá rủi ro và phạm vi ảnh hưởng.

## 25. Những nhầm lẫn thường gặp về L4/L7

| Nhầm lẫn | Cách hiểu đúng |
| --- | --- |
| “L4 là stateless, L7 là stateful.” | L4 có thể giữ NAT/connection state; L7 thường giữ application/proxy state. |
| “L4 luôn chỉ là NAT.” | L4 có thể là full TCP proxy, DSR, NAT hoặc packet steering. |
| “L7 luôn xử lý từng request ở backend khác nhau.” | Connection reuse, gRPC/WebSocket và implementation có thể pin traffic. |
| “Có HTTP health check nghĩa là LB L7.” | L4 dataplane cũng có thể hỗ trợ HTTP health probe. |
| “TLS passthrough có thể route theo URL path.” | Không nếu proxy không giải mã HTTP bên trong TLS. |
| “TLS termination đồng nghĩa backend plaintext.” | Có thể re-encrypt/mTLS giữa proxy và backend. |
| “Dùng RSA certificate thì TLS không thể có forward secrecy.” | PFS phụ thuộc negotiated key exchange, không chỉ certificate key type. |
| “X-Forwarded-For là client IP thật vì đó là header chuẩn.” | Client có thể giả; phải xác định trusted proxy chain. |
| “PROXY protocol tự chống spoofing.” | Chỉ là metadata; phải giới hạn nguồn/identity của sender. |
| “IP nguồn ở backend luôn là IP client khi dùng L4.” | Full-proxy/SNAT có thể thay IP; DSR/DNAT tùy mode. |
| “DSR trả trực tiếp nghĩa là lỗi asymmetric routing.” | DSR có thể cố ý bất đối xứng; kiểm tra NAT/state/security design. |
| “Weighted RR làm backend không bao giờ quá tải.” | Weight không đo request cost, dependency bottleneck hoặc hot keys. |
| “Least connections tương đương least workload.” | Một HTTP/2 connection có thể có nhiều streams và CPU lớn. |
| “Thêm backend luôn giải quyết 503.” | Có thể nghẽn DB, queue, WAF/TLS hoặc quotas. |
| “Health 200 có nghĩa checkout hoạt động.” | Health endpoint có thể không kiểm tra hành trình nghiệp vụ. |
| “Cứ bật retry sẽ nâng availability.” | Có thể nhân đôi giao dịch và làm retry storm. |
| “Cloud LoadBalancer của Kubernetes đương nhiên là L7.” | Service type LoadBalancer thường cung cấp LB theo controller; protocol khác nhau. |
| “Ingress tự phân phối traffic không cần controller.” | Ingress là khai báo; controller/implementation mới thực thi data plane. |
| “Có CDN là không thể truy cập origin trực tiếp.” | Origin vẫn có thể public/bypass nếu không kiểm soát ingress. |
| “Có L7 WAF thì không cần upstream DDoS.” | Flood làm đầy uplink trước WAF cần upstream protection. |
| “Có LB dự phòng là session không bao giờ rớt.” | Failover, conntrack và stream state có thể làm client reconnect. |
| “Cứ giảm 5xx tại proxy là người dùng đã phục hồi.” | Phải đo application/business SLI, auth và false positives. |

## 26. Câu hỏi tự kiểm tra và bài tập thiết kế

1. **LB Layer 4 thường dựa trên những trường nào?** IP, TCP/UDP port, protocol và flow/connection state theo mode.
2. **L7 LB có thêm khả năng gì khi xử lý HTTPS?** Sau TLS termination hợp lệ, nó có thể đọc HTTP Host/path/method/headers để route hoặc áp policy.
3. **L4 full-proxy khác DNAT?** Full-proxy tạo kết nối tới backend riêng; DNAT dịch địa chỉ đích và thường yêu cầu inverse NAT trên đường về.
4. **DSR có nghĩa tất cả packet phải quay qua LB không?** Không. Backend trả trực tiếp theo mô hình DSR được thiết kế.
5. **SNI-aware TLS passthrough có biết HTTP path?** Không; chỉ có thể đọc thông tin ClientHello được phép hiển thị, không có plaintext HTTP.
6. **Vì sao backend không được tin XFF từ Internet?** Client tự viết được XFF; proxy đáng tin phải chuẩn hóa và xác minh chuỗi.
7. **PROXY protocol có sẵn mật mã xác thực không?** Không, cần bảo vệ kênh và giới hạn nguồn truyền metadata.
8. **Least connections có phù hợp nhất cho mọi HTTP/2 workload không?** Không; một connection có thể multiplex nhiều streams với chi phí khác nhau.
9. **Sự khác biệt giữa ready và alive?** Alive là process/endpoint còn hoạt động; ready là đủ điều kiện tiếp nhận workload theo chính sách.
10. **Connection draining giúp gì?** Dừng cấp mới và cho phép in-flight work hoàn tất trong giới hạn trước khi ngừng backend.
11. **Tại sao không retry mọi POST sau 504?** Backend có thể đã ghi dữ liệu; retry không idempotent gây giao dịch lặp.
12. **WAF ở L7 có chống được upstream link saturation?** Không nếu đường WAN đã đầy trước khi đến WAF; cần upstream mitigation.
13. **Phân biệt Kubernetes Service LoadBalancer và Ingress?** Service type LB cung cấp endpoint theo controller; Ingress khai báo HTTP routing do Ingress controller thực thi.
14. **Một node L4 hỏng nhưng VIP vẫn trả ping có chứng minh service tốt?** Không; cần test TCP/UDP, NAT, application success và security policies.
15. **L4/L7 liên quan gì tới phân đoạn Dev/Prod?** LB chỉ phân phối; route/firewall/identity phải ngăn lưu lượng ngoài quyền dù Host/path bị giả.
16. **Vì sao phải test IPv6?** Listener, route, TLS/WAF và origin bypass có thể khác IPv4.
17. **Khi nào dùng L4 trước L7?** Khi cần phân phối transport và scale cụm L7 riêng, với kế hoạch health, identity, TLS, return path rõ.
18. **Tại sao TLS re-encryption cần kiểm tra chứng chỉ backend?** Mã hóa kênh không đủ nếu proxy chấp nhận peer giả mạo.
19. **Thước đo thành công của LB là chỉ RPS cao?** Không; cần business SLO, latency, error, saturation và policy enforcement.
20. **Khi mọi backend unhealthy nên cho traffic vào Prod hay Dev?** Không tự gửi traffic Prod sang Dev; phải theo fail-closed/fallback đã phê duyệt.

### Bài tập tổng hợp

Thiết kế một nền tảng có ứng dụng bán hàng HTTPS, API gRPC, dịch vụ upload lớn, cơ sở dữ liệu Production, một môi trường Dev, hai availability zones và người dùng truy cập qua cả IPv4/IPv6. Có yêu cầu bảo vệ khỏi DDoS, chạy canary và hỗ trợ người dùng mobile sau NAT.

Hãy thực hiện:

1. Vẽ **sơ đồ data flow** gồm edge/upstream protection, L4 hoặc L7, TLS termination, firewall zones, application pools và database.
2. Nêu **lý do chọn L4 hay L7** cho HTTPS, gRPC streaming, TCP/UDP custom service và HTTP/3 nếu có.
3. Chọn thuật toán phân phối, **weights, readiness, draining và warm-up** cho pool không đồng nhất.
4. Định nghĩa **trusted proxy chain** để xác định source IP và request ID, không tin headers client tự khai.
5. Lập **ma trận TLS** client→edge, edge→LB, LB→backend với certificate validation/mTLS.
6. Thiết kế **rate limiting, WAF và chống DDoS upstream**, có metrics false positives và chi phí.
7. Xác định topology failover khi mất LB node/AZ, kể cả **return path, NAT state, ECMP và N+1 capacity**.
8. Viết ít nhất **10 kịch bản kiểm thử** gồm auth, Dev→Prod DENY, origin bypass DENY, WebSocket/gRPC drain, IPv6, 429/502/504 và rollback.

**Tiêu chí chấm:** Một bản thiết kế tốt không chỉ chứa sơ đồ LB phân phối nhiều backend, mà còn chứng minh **traffic hợp lệ phục vụ ổn định, ranh giới mạng bảo mật đúng và sự cố có thể phát hiện/khôi phục theo quy trình**.

## 27. Checklist review trước khi đưa L4/L7 LB vào vận hành

- [ ] Đã xác định **protocol, ứng dụng, owner, peak traffic và SLO**?
- [ ] Đã nêu rõ **L4 hay L7**, mode DNAT/full-proxy/DSR và đơn vị phân phối flow/request?
- [ ] Biết vị trí **VIP/listener, NAT/SNAT, source preservation và return routing**?
- [ ] Đã kiểm tra ECMP, anti-spoofing/uRPF và những đường bất đối xứng hợp lệ?
- [ ] Thuật toán RR/weighted/least connections/least requests/hash có phù hợp workload?
- [ ] Health checks đo đủ **readiness**, có threshold chống flapping, không gây side effect?
- [ ] Có slow start/warm-up và **graceful connection/request draining**?
- [ ] Sticky sessions/consistent hash có owner và phương án khi backend biến mất?
- [ ] Có hỗ trợ đúng HTTP/1.1, HTTP/2, gRPC, WebSocket, HTTP/3/QUIC hoặc TCP/UDP cần thiết?
- [ ] TLS passthrough/termination/re-encryption được mô tả chính xác theo từng hop?
- [ ] Certificate, SNI/ECH, ALPN, mTLS và **backend peer validation** được kiểm chứng?
- [ ] **X-Forwarded-For/Forwarded/PROXY protocol** chỉ được tin từ kênh/proxy có thẩm quyền?
- [ ] Host/path normalization, default route, admin paths và header policies có deny an toàn?
- [ ] Origin/private backend không thể bị **bypass trực tiếp** ngoài đường đã phê duyệt?
- [ ] Dev/Guest/Internet → Prod DB và management API vẫn bị **DENY**?
- [ ] L4/L7 rate limit, WAF, bot mitigation và upstream DDoS được đặt tại điểm phù hợp?
- [ ] Các rule WAF/429 có **quan sát false-positive user impact** và rollback rõ?
- [ ] Sizing gồm CPS/RPS, throughput, HTTP streams, TLS CPU, NAT/conntrack, memory và N+1?
- [ ] Có dự phòng theo LB node, switch, AZ, region, ISP và dependency quan trọng?
- [ ] Kubernetes Service/Ingress/Gateway API có controller thực thi, CNI/NetworkPolicy đúng?
- [ ] Đã kiểm tra IPv4/IPv6, public/internal listeners, DNS steering, caching và TTL?
- [ ] Có metrics frontend/upstream, request IDs, trace correlation và logs đã redaction?
- [ ] Có kiểm thử backend errors, all-unhealthy, graceful drain, reconnect, rollout và rollback?
- [ ] Đã xác minh **ALLOW hợp lệ và DENY bắt buộc** cả sau failover?
- [ ] Config/IaC được review, có RBAC/MFA/audit và readback sau triển khai?
- [ ] Có runbook chẩn đoán DNS → L4 → TLS → L7 → backend/dependency?

**Kết luận:** **L4 load balancing** phân phối traffic dựa trên kết nối/flow TCP/UDP và cách triển khai dataplane như NAT, proxy hoặc DSR; **L7 load balancing** hiểu yêu cầu ứng dụng như HTTP để route theo host/path và áp chính sách sâu hơn. Hai lớp có thể bổ sung nhau, không thay thế **xác thực, phân đoạn, TLS, IDS/IPS hay DDoS protection**. Một thiết kế tốt phải cân bằng **hiệu năng, tính sẵn sàng, bảo mật và khả năng quan sát**, đồng thời chứng minh **người dùng hợp lệ được phục vụ, những luồng không được phép bị chặn và sự cố có quy trình phục hồi an toàn**.
