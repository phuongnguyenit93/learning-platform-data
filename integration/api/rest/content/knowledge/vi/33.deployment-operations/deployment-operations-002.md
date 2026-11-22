# Reverse proxy, load balancer và API gateway trong chuỗi xử lý

Một REST API trả **201 Created** cho yêu cầu tạo đơn ở môi trường local. Nhưng sau khi triển khai qua CDN, ingress và API gateway, client thấy **Location** trỏ về hostname nội bộ, đăng nhập liên tục bị mất cookie, POST thỉnh thoảng thành hai đơn và khi backend treo thì có lúc nhận **502**, lúc nhận **504**. Đây không chỉ là lỗi cấu hình mạng: **mỗi tầng trung gian đã tham gia vào hợp đồng HTTP, bảo mật và khả năng phục hồi** của API.

Bài thuộc chương **Triển khai và vận hành** của module **INTEGRATION_API_REST**. Mục tiêu là thiết kế REST API nhất quán từ resource/URI, phương thức và mã trạng thái HTTP đến xác thực, phân quyền, cache, rate limit, idempotency, tracing và kiểm thử trên chuỗi **client → reverse proxy → load balancer → API gateway → Java/Spring service**.

## 1. Mục tiêu học tập và từ vựng

Sau bài này, bạn có thể:

1. Giải thích sự khác nhau giữa **reverse proxy**, **load balancer (LB)** và **API gateway**, kể cả khi một sản phẩm đảm nhiệm nhiều vai trò.
2. Phân biệt **L4/L7 load balancing**, TLS termination/pass-through, HTTP/1.1 keep-alive và HTTP/2 multiplexing ở ranh giới connection/request.
3. Thiết kế chuỗi **Host, Forwarded, X-Forwarded-For, X-Forwarded-Proto** mà backend chỉ tin các hop đáng tin cậy.
4. Giữ **URI, Location, cookie, CORS, mã lỗi và OpenAPI server URL** đúng khi có path rewrite và TLS offload.
5. Chọn **health checks, readiness, drain, retry, timeout, circuit breaker, rate limit** mà không gây retry storm hoặc lặp giao dịch.
6. Cấu hình minh họa **Nginx và Spring Boot/Spring Security**, nhận diện lỗ hổng Host-header poisoning, SSRF và token forwarding.
7. Kiểm thử qua **đường đi bên ngoài thực tế**, fault injection, HA, phân quyền đa tenant và dấu vết observability.

### 1.1. Ba vai trò, không phải ba loại sản phẩm tách biệt

| Vai trò | Câu hỏi chính | Chức năng tiêu biểu |
|---|---|---|
| **Reverse proxy** | Request tới server ứng dụng nào? | Nhận kết nối từ client, chuyển tiếp HTTP, TLS termination, route theo host/path, giới hạn body |
| **Load balancer** | Replica/backend nào nhận request? | Chọn upstream, health check, phân phối tải, loại node lỗi, connection draining |
| **API gateway** | Chính sách API nào áp dụng trước service? | Route theo resource/version, JWT/API key, rate limit, quota, CORS, transform có kiểm soát, logging |

**Nginx, Envoy, HAProxy, cloud L7 LB, Kubernetes ingress controller và Spring Cloud Gateway** có thể chồng lấn các vai trò. **Gateway** cũng có thể chính là reverse proxy và load balancer cho nhóm service; không nhất thiết triển khai đủ ba hộp vật lý theo tên. Phân loại theo **trách nhiệm và ranh giới tin cậy**, không theo logo sản phẩm.

**L4 LB** chọn backend dựa trên kết nối TCP/UDP, không hiểu REST resource, path hoặc JWT nếu không giải mã/chặn traffic. **L7 proxy/LB** hiểu HTTP method, Host, URI, header, status; có thể route/rate-limit theo request nhưng phải xử lý HTTP semantics và dữ liệu nhạy cảm. Khi TLS pass-through, một thiết bị L4 thường không thể đọc header bên trong TLS; khi TLS terminate, tầng đó có thể đọc dữ liệu và phải trở thành một ranh giới bảo mật được quản trị.

## 2. Theo dõi một request qua các hop

Giả sử khách gọi **POST https://api.example.test/v1/orders**. Kiến trúc minh họa:

~~~mermaid
sequenceDiagram
    autonumber
    participant C as Client
    participant E as Edge reverse proxy
    participant G as API Gateway
    participant L as Service LB
    participant A as Orders API (Spring)
    participant D as Database
    C->>E: HTTPS POST /v1/orders
    Note over E: TLS, hostname, body limits
    E->>G: Trusted forwarding headers
    Note over G: AuthN, route, limit, trace
    G->>L: HTTP request + identity context
    L->>A: Chọn healthy replica
    A->>D: Transaction: create order + outbox
    D-->>A: COMMIT OK
    A-->>L: 201 + Location /v1/orders/{id}
    L-->>G: 201
    G-->>E: 201
    E-->>C: 201 Created
~~~

Trong sơ đồ, **LB service** được thể hiện riêng để phân tích; ở Kubernetes, nó có thể là Service/sidecar hoặc discovery mechanism của gateway. Dù đi qua bao nhiêu hop, client vẫn chỉ thấy **một API hợp đồng công khai**. Các hop phải bảo toàn method/body/status, trừ các chuyển đổi đã được thiết kế và kiểm thử; không tự biến một HTTP 409 từ service thành 500, hoặc sửa POST thành GET khi retry.

### 2.1. Những đặc tính phải được theo dõi end-to-end

| Thuộc tính | Đường đi/điểm cần kiểm tra | Sai hỏng thường gặp |
|---|---|---|
| **Scheme/Host/port** | HTTPS public → TLS offload → upstream | Spring dựng absolute URL thành http://orders:8080 |
| **Request path/query** | /v1/orders qua từng router | Strip prefix hai lần, mất query hoặc decode sai |
| **Method/body/Content-Type** | POST JSON qua gateway và service | Proxy từ chối body lớn, không forward header đúng |
| **Authorization/Cookie** | Browser/client → gateway → API | Token bị log hoặc forward sang service không tin cậy |
| **HTTP status/headers** | Service → gateway → edge → client | Location sai, Retry-After mất, 401 challenge bị che |
| **Trace context** | traceparent xuyên các hop | Một request bị chia thành nhiều trace rời rạc |
| **Connection/deadline** | Client → từng proxy → service → DB | Gateway 504 dù DB tiếp tục COMMIT sau deadline |

Đây là lý do test chỉ dùng MockMvc trực tiếp trên Controller **chưa đủ**: nó bỏ qua TLS offload, Host, rewrite, gateway policy, LB routing, connection timeout và proxy-generated error.

## 3. Reverse proxy: đường vào HTTP và đường ra của response

Reverse proxy nhận request **đại diện cho các backend**, thường xử lý TLS certificate, HTTP version, hostname routing, request size limits, compression/caching và header forwarding. Nó có thể phục vụ nhiều service trên cùng một domain hoặc nhiều domain trên một nhóm IP.

### 3.1. TLS termination, re-encryption và pass-through

- **TLS termination tại edge:** client dùng HTTPS tới edge, edge giải mã rồi chuyển request tiếp. Nếu đường nội bộ dùng HTTP, cần mạng tin cậy và biện pháp bảo vệ phù hợp; với yêu cầu cao, dùng **TLS lại giữa các hop**, thường kết hợp mTLS.
- **TLS pass-through:** LB chuyển luồng TLS mà không đọc body/header; routing thường dựa IP/port hoặc SNI trong giới hạn giao thức và cấu hình. Không thể áp policy JWT/URI ở hop không giải mã HTTP.
- **mTLS phía trong:** xác minh **service/workload identity** của các hop, không thay thế xác thực end-user hoặc authorization tới resource.

**X-Forwarded-Proto: https** không tự chứng minh kết nối upstream đã được mã hóa. Nó chỉ mô tả **scheme public do hop đáng tin ghi nhận**. Nếu proxy/ứng dụng chấp nhận header đó từ Internet, kẻ ngoài có thể làm ứng dụng tin rằng request đến qua HTTPS hoặc làm sai redirect/cookie.

### 3.2. Hop-by-hop so với end-to-end headers

HTTP intermediaries quản lý connection riêng và không được mù quáng chuyển tiếp các trường chỉ áp dụng cho một hop. Các header như **Connection** và các trường được liệt kê trong nó, cùng **Transfer-Encoding, Keep-Alive, Upgrade** phải được xử lý theo HTTP version và semantics, không sao chép tùy tiện. HTTP/2 có những giới hạn riêng đối với connection-specific headers.

Ngược lại, nhiều header phản ánh hợp đồng API cần được **bảo toàn có kiểm soát**, như **ETag, If-Match, Cache-Control, Retry-After, WWW-Authenticate, Location, Content-Type, Idempotency-Key**. Proxy có thể chủ động chuyển đổi encoding/transfer nhưng không được làm lệch semantics của representation hoặc phương thức.

### 3.3. Path rewrite phải có một nguồn sự thật

Giả sử public route là **/api/v1/orders** còn backend dùng **/v1/orders**. Có hai lựa chọn rõ:

1. **Gateway strip /api** trước khi gọi Spring, Spring mapping dùng /v1/orders; public URL được quản trị tập trung ở gateway.
2. **Spring biết context path /api**, gateway forward nguyên path; không strip hai lần.

Nếu Spring trả **Location: /v1/orders/o-918** trong phương án 1, client sẽ dùng URI khác với public prefix trừ khi gateway sửa Location đáng tin cậy hoặc service dựng **public relative URI** như **/api/v1/orders/o-918**. Tốt nhất là lựa chọn **một public resource URI contract** và kiểm tra trong integration tests; đừng vá ngẫu nhiên theo Host từng request.

**Uri encoding** phải được thống nhất: %2F trong path segment, dấu cộng/space trong query, UTF-8, trailing slash và duplicate slash có thể được diễn giải khác nhau ở edge, gateway và Spring. Tránh decode hai lần hoặc cho phép canonicalization khác nhau làm lệch route security và route business. Giới hạn method, path và kích thước header/body ở biên nhưng tránh một rule WAF quá rộng vô tình chặn OpenAPI endpoint hợp lệ.

## 4. Forwarded headers và ranh giới tin cậy

Backend thường chỉ thấy **remote address của proxy gần nhất** và một kết nối HTTP/TLS khác với kết nối public. Để ứng dụng dựng redirect, absolute URI, cookie và log đúng, các proxy sử dụng **Forwarded (RFC 7239)** hoặc các biến thể phổ biến **X-Forwarded-For, X-Forwarded-Proto, X-Forwarded-Host, X-Forwarded-Port, X-Forwarded-Prefix**.

~~~http
GET /v1/orders/o-918 HTTP/1.1
Host: orders.internal.example
Forwarded: for=203.0.113.42;proto=https;host=api.example.test
X-Forwarded-For: 203.0.113.42
X-Forwarded-Proto: https
X-Forwarded-Host: api.example.test
X-Request-Id: req-918
~~~

Các giá trị trên là **ví dụ**, không phải thứ mà Java/Spring tự xác minh bằng mật mã. Client ngoài Internet cũng có thể gửi những header này. **Điều kiện tiên quyết:** chỉ cho phép ingress/proxy đáng tin gọi trực tiếp backend và **xóa/thay thế header forwarded do client tự khai ở ranh giới đầu tiên**, sau đó có quy tắc append/preserve rõ giữa các proxy được tin cậy.

### 4.1. Quy tắc một chuỗi proxy đáng tin

1. Ở **edge public**, đặt lại **X-Forwarded-Proto, X-Forwarded-Host** từ request TLS/Host đã được xác minh; không giữ giá trị client tự đưa.
2. Với **X-Forwarded-For**, dựng chuỗi từ địa chỉ peer tin cậy theo policy; proxy kế tiếp chỉ append khi đã xác minh kết nối trước đó đến từ proxy được phép.
3. Tại **API gateway/backend**, chỉ tiêu thụ header nếu network path bảo đảm request đến từ hop tin cậy; nếu không, **loại bỏ chúng**.
4. Không tin các header **x-user, x-role, x-tenant-id** đến từ browser như một principal. Identity propagation nội bộ cần cơ chế xác thực giữa service, chữ ký/claim được kiểm chứng và chính sách rõ ràng.
5. Ghi **client IP theo trusted proxy algorithm**, không đọc phần tử đầu hay cuối XFF tùy tiện. IP là tín hiệu vận hành/rate-limit yếu, **không phải authorization**.

Nếu một proxy ở giữa vừa giữ **Forwarded** vừa tạo **X-Forwarded-*** nhưng hai bộ khác nhau, Spring có thể xử lý scheme/host sai. Hãy chọn **một convention chủ đạo**, thử nghiệm nhiều hop và đảm bảo các giá trị được tái tạo nhất quán. Không chỉ thêm header ở proxy cuối mà bỏ qua khả năng spoof từ Internet.

### 4.2. Host-header poisoning, redirect và cookie

Một số framework sinh absolute URL từ request Host hoặc forwarded host. Nếu người ngoài điều khiển được chúng, response có thể chứa:

~~~http
HTTP/1.1 302 Found
Location: https://attacker.example/reset-password?token=...
~~~

Đây là **minh họa anti-pattern**: reset-password link, OAuth callback, absolute Location, email xác nhận hoặc URL trong OpenAPI bị xây từ Host không tin cậy. Chọn **public base URL từ cấu hình** cho link nhạy cảm; chỉ chấp nhận Host thuộc allowlist, và để trusted edge kiểm soát forwarded headers.

Cookie cũng bị ảnh hưởng bởi scheme/path/domain. Browser chỉ gửi **Secure cookie** qua HTTPS; **HttpOnly** không thay chống CSRF, **SameSite** phải cân đối UX cross-site. Nếu API đi qua /api nhưng backend trả cookie có **Path=/internal**, trình duyệt có thể không gửi cookie ở route public. Nếu muốn cookie có prefix **__Host-**, cần **Secure; Path=/; không có Domain**. Thực hiện và kiểm thử cookie tại **public HTTPS endpoint**, không suy đoán từ local HTTP.

### 4.3. CORS, CSRF và proxy forwarding

CORS là chính sách browser đọc response cross-origin, không phải phương thức xác thực. Gateway có thể xử lý preflight **OPTIONS**, nhưng response chính cũng phải có CORS policy nhất quán. Không dùng **Access-Control-Allow-Origin: \*** cùng credentialed requests; cần allowlist origin thực và cách xử lý **Vary: Origin** phù hợp nếu phản hồi thay đổi theo Origin.

**Cookie-backed API** phải chống **CSRF** cho thao tác thay đổi trạng thái, kể cả khi gateway đã bật CORS. **Bearer JWT trong Authorization** không tự đi theo request browser như cookie, nhưng API vẫn phải bảo vệ XSS, token leak, scope và resource-level authorization. Nếu đường public vừa chấp nhận cookie vừa bearer token, không mặc định tắt CSRF toàn bộ chỉ vì có JWT ở một số route.

## 5. Load balancer: chọn node khỏe và rút node an toàn

**LB không đơn thuần là round-robin.** Nó phải đảm bảo request vào một upstream có khả năng thực thi, nhận biết node mất readiness, phân phối tải theo capacity và đưa node ra khỏi luồng trước khi shutdown/deploy.

### 5.1. L4 connection balancing và L7 request balancing

| Khía cạnh | L4 LB | L7 LB/proxy |
|---|---|---|
| Đơn vị chọn backend | TCP connection/flow | HTTP request/stream tùy triển khai |
| Thông tin thường biết | IP/port, state kết nối | Host, path, method, header, HTTP status |
| TLS | Có thể pass-through | Thường terminate hoặc re-encrypt |
| Keep-alive / HTTP/2 | Nhiều request có thể cùng connection đã chọn | Có thể định tuyến theo request/stream |
| Ứng dụng | Phân phối network flow, đơn giản/lưu lượng lớn | Route API, canary, header/rate policy |

**L4 cân bằng connection không bảo đảm cân bằng request**: một connection HTTP/2 có thể chứa hàng nghìn stream, trong khi connection khác gần như rảnh. Cần đo active requests, connection/stream saturation và latency theo replica. Với WebSocket/SSE/streaming dài, một request có thể giữ connection lâu; LB và gateway phải có timeout/drain/connection limits riêng.

### 5.2. Chọn thuật toán theo loại tải

- **Round robin:** đơn giản, hữu ích khi replica tương đồng và request ngắn; không biết request nào giữ DB 30 giây.
- **Least connections / least outstanding requests:** phù hợp request có độ dài khác nhau; số connection chưa chắc phản ánh công việc đang chạy khi HTTP/2 multiplex.
- **Weighted balancing:** điều chỉnh cho replica khác CPU/memory hoặc canary 1–5%; cần đo sức chịu tải thật.
- **Consistent hashing/affinity:** một key thường đi cùng backend, có ích cho cache locality; **không** thay shared session store hay bảo đảm idempotency khi node chết.

**Sticky session** có thể làm một HTTP session nằm trên cùng replica, nhưng khi autoscale/failover hoặc node chết, state local vẫn mất. Với Java Spring nhiều replica, session quan trọng cần **shared store** như Spring Session Redis hoặc thiết kế bearer stateless phù hợp; không lấy affinity làm bằng chứng dữ liệu bền vững.

### 5.3. Health, liveness, readiness và graceful draining

**Liveness** trả lời process có cần restart không. **Readiness** trả lời instance có sẵn sàng nhận request mới không. Nếu DB/IdP tạm chậm, một liveness probe kiểm tra sâu có thể khiến toàn cụm tự restart theo vòng lặp. Readiness nên phản ánh khả năng phục vụ cần thiết và có điều kiện mất readiness rõ; không phụ thuộc không kiểm soát vào một upstream gây cascading eviction.

~~~text
ROLLING DEPLOY (minh họa):
1. New replica start -> JVM warm-up, dependencies cần thiết được kiểm tra.
2. Readiness PASS -> LB mới đưa vào rotation.
3. Old replica chuyển readiness FAIL trước khi shutdown.
4. LB ngừng gửi request mới; drain active HTTP requests/streams.
5. Grace period cho thao tác đang chạy và worker; giải phóng resource.
6. Terminate khi hết grace period, quan sát unfinished operations.
~~~

Cần tính **độ trễ lan truyền endpoint/readiness** từ orchestrator tới LB, connection draining của proxy và **terminationGracePeriod** theo request deadline. Với job dài hơn grace period, chuyển sang **durable queue/lease**, không cố giữ HTTP connection mở hàng giờ. Đừng để shutdown làm lệnh thanh toán đang commit rồi bị retry như operation mới.

### 5.4. Retry upstream chỉ khi an toàn

LB có thể thử node khác nếu **kết nối chưa được thiết lập hoặc upstream lỗi**; nhưng với một request POST đã được gửi, lần đầu có thể đã commit ở server trước khi response mất. Tự động gửi POST tới replica thứ hai có thể tạo **hai đơn/hai giao dịch**, ngay cả khi retry diễn ra tại proxy chứ không phải SDK.

**GET/HEAD** thường an toàn hơn để retry có giới hạn, với deadline/jitter và kiểm soát cache. **PUT/DELETE** có intended effect idempotent nhưng vẫn cần ETag/version nếu có cạnh tranh. **POST/PATCH** phải có policy và idempotency contract rõ; không bật retry tự động chỉ vì HTTP status là 502/503/504. Khi client gửi **Idempotency-Key**, tất cả replicas phải dùng **shared durable operation store** để dedupe; bộ đếm trong RAM không có tác dụng xuyên replica.

## 6. API gateway: nơi đặt chính sách chung, không thay domain service

API gateway là cửa vào logic dành cho client, thường giữ một **public API namespace** rồi chọn backend và áp policy theo route. Gateway phù hợp với các kiểm soát **đồng nhất, sớm và không phụ thuộc sâu vào dữ liệu domain**:

| Policy ở gateway | Vì sao hữu ích | Điều service vẫn phải làm |
|---|---|---|
| Route/version: /v1/orders → orders-service | Tách URL public khỏi service discovery | Giữ hợp đồng resource/method/status |
| Xác thực sơ bộ JWT, API key | Loại request không hợp lệ trước DB | Kiểm chứng principal/scope phù hợp ranh giới trust |
| Rate limit và body/header limits | Bảo vệ tải chung, tránh resource exhaustion | Quota business, idempotency, giới hạn concurrency |
| CORS/preflight | Nhất quán origin policy | CSRF cho cookie write, response headers đúng |
| Circuit breaker/timeouts | Cắt đường gây quá tải | Trạng thái nghiệp vụ, async recovery/outbox |
| Metrics/tracing | Đo toàn bộ traffic ở biên | Đo commit, domain outcomes, downstream dependencies |
| Canary/weighted traffic | Triển khai dần version | API contract và schema tương thích |

**Gateway không biết người dùng có được xem order o-918 hay không** nếu quyền sở hữu ở DB. Bên trong service vẫn cần **BOLA/IDOR checks** theo tenant, owner, role và trạng thái tài nguyên. Không đặt quyền tối quan trọng chỉ ở gateway rồi mở service cho mọi caller nội bộ, vì request có thể đến từ worker, sidecar hoặc đường mạng khác.

### 6.1. JWT/identity giữa gateway và backend

Hai mô hình phổ biến:

1. **Mỗi service tự validate JWT**: gateway có thể kiểm tra sơ bộ để giảm tải, backend vẫn validate signature/issuer/audience/lifetime/scope. Dễ hiểu về ranh giới tin cậy, đổi lại có chi phí kiểm chứng thêm.
2. **Gateway phát assertion nội bộ**: gateway validate credential public, sau đó gửi identity assertion **được ký hoặc bảo vệ bằng mTLS+chính sách identity được kiểm chứng**, backend chỉ tin khi request xuất phát từ trusted gateway. Thiết kế cần chống spoof/replay, kiểm soát claim mapping và trust chain.

Không chuyển header **X-User-Id: admin** từ browser thẳng tới backend rồi coi đó là danh tính. Nếu cần propagation, gateway phải **loại bỏ header identity do client tự gửi**, tạo lại từ credential đã validate và backend xác minh theo hợp đồng. Đừng forward bearer token end-user tới một host bên ngoài, API analytics hoặc webhook không liên quan; token có **audience/scope** cho service cụ thể.

**Issuer không đồng nghĩa audience**: JWT đúng chữ ký bởi identity provider vẫn có thể không được cấp cho API hiện tại. API resource server phải kiểm tra **audience** theo hợp đồng. Key rotation/JWKS cache outage cần policy rõ; khi không thể xác thực an toàn, không âm thầm cho qua chỉ vì gateway đang lỗi.

### 6.2. Rate limiting ở nhiều tầng

**Edge** có thể giới hạn trước xác thực theo network/IP đáng tin để giảm abuse. **Gateway** giới hạn theo **verified client/tenant/operation**, còn **service** kiểm tra quota nhận voucher, giới hạn đồng thời hoặc ngân sách báo cáo. Với nhiều gateway replicas, limiter trong RAM trên từng gateway **không phải global quota**; dùng Redis/distributed limiter hoặc kiến trúc phù hợp nếu policy công bố hạn mức toàn hệ thống.

Đừng đếm **HTTP retries** như một lần nhận thưởng mới; quota business cần dựa vào **logical operation và transaction**. Một request hợp lệ vượt rate nên nhận **429 + Retry-After**; một service/limiter tạm hỏng có thể nhận **503**, không được ngụy trang thành user abuse. Khi nhiều lớp giới hạn cùng hoạt động, header thông báo limit phải có **scope** được tài liệu hóa; không hứa một con số remaining duy nhất đại diện mọi tenant/global budget.

### 6.3. Một nguồn sự thật cho OpenAPI và error contract

Public URI của API là thứ client dùng, không phải hostname nội bộ: OpenAPI **servers** và tài liệu **Location, Link, pagination cursor, webhook callback** phải theo public base URL. Route của gateway không được tự tạo API version không có trong contract. Khi rewrite hoặc prefix thay đổi, cập nhật contract SDK/docs cùng deploy.

Với lỗi từ backend, gateway thường phải **giữ mã HTTP và các header có ý nghĩa**, ví dụ:

~~~http
HTTP/1.1 409 Conflict
Content-Type: application/problem+json
Cache-Control: no-store

{"type":"https://api.example.test/problems/order-conflict",
 "title":"Order conflict","status":409,"code":"ORDER_CONFLICT"}
~~~

Nếu **gateway tự sinh lỗi** (auth failure, rate limit, upstream unavailable), nó cũng nên trả **Problem Details** với type/code và trace ID đã chuẩn hóa, nhưng **không giả mạo lỗi domain**. Cùng client cần phân biệt **401 auth, 403 authz, 404 not found, 409 conflict, 429 throttled, 502/503/504 proxy/dependency failure**. Cấu hình nhất quán cả **WWW-Authenticate, Retry-After, Content-Type, Cache-Control**, không chỉ JSON body.

### 6.4. Gateway cache và HTTP semantics

Gateway có thể cache **GET/HEAD** phù hợp Cache-Control/ETag/Vary, nhưng **không cache representation riêng của tenant như public**. **Authorization, Cookie, Accept-Language, query và filter** có thể thay đổi response, nên cache key và policy cần được định nghĩa chặt chẽ. Cache nằm giữa hai HTTP request **không bảo đảm read-after-write**; sau POST 201, GET có thể chạm cache cũ nếu invalidation sai.

Không bật cache cho **POST tạo order**, response chứa secret hay user profile. Nếu gateway làm compression, phải giữ semantics **Content-Encoding, ETag strong/weak validators, Vary: Accept-Encoding** đúng với representation thực tế. Đối với static docs/health endpoints, caching policy có thể khác với data-bearing API.

## 7. Timeout, mã lỗi và retries qua nhiều hop

Một request có thể đi qua **client timeout, edge read timeout, gateway response timeout, backend servlet timeout, DB statement timeout và HTTP client timeout tới downstream**. Mỗi giá trị áp lên **một khoảng thời gian khác nhau**. Tổng budget cần được thiết kế từ trải nghiệm client: nếu client chỉ chờ 3 giây, gateway không nên giữ một retry chuỗi 20 giây mà cuối cùng trả response client đã bỏ đi.

### 7.1. Căn chỉnh deadline thay vì chồng nhiều timeout ngẫu nhiên

Ví dụ đơn giản cho POST checkout đồng bộ với **deadline client 4 giây**:

| Thành phần | Giới hạn minh họa | Mục đích |
|---|---|---|
| Client tổng | 4.000 ms | Trải nghiệm người dùng |
| Edge → Gateway | Dưới 3.800 ms | Tránh đợi khi client đã rời |
| Gateway → service | Dưới 3.500 ms | Còn thời gian trả response qua proxy |
| Service DB + business | Budget riêng trong khoảng còn lại | Tránh tác vụ kéo dài quá khả năng trả kết quả |
| Tracing/logging | Bất đồng bộ và có giới hạn | Không chặn critical path |

Số liệu chỉ là ví dụ, **không cộng một cách cơ học**: mỗi timeout thường là giới hạn cho một hop/phase, không phải deadline tổng có tính đến thời gian đã tiêu. Dùng **absolute deadline được truyền đáng tin** hoặc lấy remaining budget tại từng bước; có timeout cho connect, idle/read, overall request và pool acquire phù hợp. Khi retry, **ngân sách phải giảm**, không reset về đầy đủ mỗi attempt.

**Cancellation không phải rollback**. Khi proxy hủy kết nối vì timeout, Spring service hoặc DB transaction có thể **vẫn COMMIT**. API có side effect nên thiết kế **Idempotency-Key + operation status/reconciliation**; nhận 502/504 không cho phép client kết luận thanh toán đã thất bại. Nếu workflow dài, trả **202 Accepted + Location tới operation đã lưu bền vững**, không giữ HTTP request mở vô thời hạn.

### 7.2. 502, 503, 504 thuộc tầng nào?

~~~http
HTTP/1.1 504 Gateway Timeout
Content-Type: application/problem+json
Cache-Control: no-store

{"type":"https://api.example.test/problems/upstream-timeout",
 "title":"Upstream timed out","status":504,"code":"UPSTREAM_TIMEOUT"}
~~~

| Mã | Ý nghĩa thường gặp | Ví dụ |
|---|---|---|
| **502 Bad Gateway** | Proxy/gateway nhận response không hợp lệ từ upstream hoặc gặp sự cố giao tiếp theo triển khai | Upstream đóng connection sai thời điểm, phản hồi malformed |
| **503 Service Unavailable** | Service tạm không có khả năng phục vụ | Không có healthy backend, quá tải, maintenance, pool bị cạn |
| **504 Gateway Timeout** | Proxy/gateway không nhận phản hồi từ upstream trong thời hạn | Gateway hết response timeout khi orders-service đang chờ DB |
| **429 Too Many Requests** | Client/actor vượt giới hạn theo chính sách | User gửi quá nhiều OTP hoặc GET |
| **408 Request Timeout** | Server chưa nhận đủ request từ client kịp thời | Client upload chậm/không gửi body |

**502/503/504 không buộc phải do ứng dụng Spring phát**. Nhìn vào **response server header, ingress metrics, gateway logs, proxy upstream status/latency** để xác định tầng tạo lỗi. Một ứng dụng có thể chủ động trả 503 khi không đủ capacity; client cũng có thể thấy 503 do LB không còn backend khỏe. 504 chỉ nói proxy **không nhận kịp**, không chứng minh transaction ở server rollback.

Một số ingress/proxy có log **499** để biểu diễn client đóng kết nối, nhưng **499 không phải mã trạng thái HTTP chuẩn** và không mặc định được gửi như response. Dùng nó như metric/log nội bộ theo vendor; không khai trong OpenAPI như HTTP chuẩn bắt buộc của REST.

### 7.3. Retry storm và khuếch đại số attempt

Client retry 2 lần, gateway retry 2 lần và service SDK retry 2 lần có thể tạo **3 × 3 × 3 = 27 attempts** cho một logical request khi mỗi lớp hiểu “2 retries” là hai lần thử thêm. Nếu request tạo side effect, hệ thống phải kiểm soát **attempt budget xuyên các hop** và idempotency từ đầu tới cuối.

Phương án ưu tiên: retry **tại một tầng có đủ ngữ cảnh về safety/deadline**, exponential backoff + jitter, giới hạn concurrency và **circuit breaker/admission control** để giảm công việc mới khi downstream quá tải. Tôn trọng **Retry-After** khi nhận 429/503 và còn tổng deadline; không retry 401/403 hay lỗi validation 400 chỉ vì muốn tăng success rate.

## 8. Ví dụ triển khai: Nginx edge → gateway → Spring Orders API

Giả sử API public là **https://api.example.test/v1/orders**, Nginx là edge đã xác thực Host và terminate TLS, gateway là một cụm nội bộ và Orders API nằm sau service discovery. **Ví dụ này không phải cấu hình production hoàn chỉnh**: chứng chỉ, DNS, ACL, secret, chính sách TLS, limiter, health và discovery phải được thiết kế cho môi trường thực.

### 8.1. Reverse proxy Nginx với ranh giới header rõ

~~~nginx
upstream internal_api_gateways {
    least_conn;
    server gateway-a.internal.example:8080 max_fails=3 fail_timeout=10s;
    server gateway-b.internal.example:8080 max_fails=3 fail_timeout=10s;
    keepalive 32;
}

server {
    listen 443 ssl;
    server_name api.example.test;

    ssl_certificate     /etc/tls/fullchain.pem;
    ssl_certificate_key /etc/tls/privatekey.pem;
    client_max_body_size 2m;

    location /v1/ {
        proxy_http_version 1.1;
        proxy_pass http://internal_api_gateways;

        # Edge công khai: ghi đè header có thể bị client giả mạo.
        proxy_set_header Host api.example.test;
        proxy_set_header X-Forwarded-Host api.example.test;
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header X-Forwarded-Port 443;
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_set_header X-Forwarded-Prefix "";
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header Forwarded "";
        proxy_set_header Connection "";

        proxy_connect_timeout 1s;
        proxy_send_timeout 5s;
        proxy_read_timeout 5s;

        # Không tự thử backend thứ hai cho POST có side effect.
        proxy_next_upstream error timeout;
        proxy_next_upstream_tries 1;
    }
}
~~~

**Điểm cần hiểu thay vì copy máy móc:**

- **X-Forwarded-For = $remote_addr** đúng khi đây là **public trusted edge** thấy client peer thật. Nếu ở sau CDN/LB tin cậy, giá trị này có thể là **IP CDN**, và phải cấu hình trusted real-IP chain rõ ràng; không dùng **$http_x_forwarded_for** trực tiếp làm danh tính.
- **X-Forwarded-Prefix** được loại bỏ trong ví dụ vì đường public và gateway cùng dùng /v1. Khi thiết kế thực sự cần prefix, chỉ trusted edge/gateway được đặt nó sau khi validate route; không cho client tự yêu cầu thay context path.
- **proxy_pass** ở ví dụ **không có URI suffix** nên giữ nguyên path public /v1/... cho gateway. Nếu route cần đổi prefix, đặt một rewrite rule có test và cập nhật contract Location.
- **max_fails/fail_timeout** trong upstream này thể hiện phát hiện lỗi **thụ động** của Nginx, không phải một active readiness probe đầy đủ. Việc đưa node mới vào/loại node khỏi rotation theo readiness cần hệ discovery/orchestrator/health-check được cấu hình và kiểm thử riêng.
- **Gateway nội bộ dùng HTTP** chỉ để minh họa mạng tách biệt; nếu trust model yêu cầu bảo vệ từng hop, chuyển sang **HTTPS/mTLS** và kiểm tra upstream certificate/identity.
- **proxy_next_upstream_tries 1** giới hạn ở một attempt tới upstream trong ví dụ; với GET có thể cấu hình retry được review riêng, nhưng vẫn không vượt deadline. Chính sách upstream retry còn phụ thuộc phiên bản/config của proxy và việc response đã gửi một phần.
- **proxy_read_timeout** thường là giới hạn **khoảng không đọc được dữ liệu mới từ upstream** (idle giữa các lần đọc), không tự động là **tổng thời gian HTTP response**. Nếu cần total deadline, phải thiết kế và đo riêng.
- Mẫu chỉ phục vụ **/v1/** trên HTTPS; cần chính sách rõ cho hostname không hợp lệ, HTTP→HTTPS redirect và đường admin/actuator. Không công bố /actuator/prometheus cho toàn Internet.

Trong sản phẩm thực, cần xem xét **HTTP/2, SSE, gRPC, WebSocket, upload streaming, proxy buffering** và tối ưu TLS/connection riêng. Với SSE, buffering/idle timeout có thể làm client không nhận event dù backend đang phát; với upload lớn, max body size/timeout và signed URL cần được thiết kế cùng nhau.

### 8.2. Gateway route theo public URI, tránh hai lớp rewrite

Một gateway policy ở mức kiến trúc, không phụ thuộc vendor, có thể định nghĩa:

~~~yaml
routes:
  - id: orders-v1
    externalPath: /v1/orders/**
    backendService: orders-service
    preservePath: true
    methods: [GET, POST, PUT, PATCH, DELETE]
    authentication: jwt
    audience: orders-api
    ratePolicy: orders-client-tenant
    connectTimeoutMs: 500
    responseTimeoutMs: 3000
    retryNonIdempotent: false
~~~

Đây là **policy minh họa dạng YAML**, **không phải schema cấu hình chạy được của Spring Cloud Gateway hoặc một sản phẩm cụ thể**. Cấu hình thật cần khớp version gateway và test ingress/security/discovery; không đưa đoạn minh họa này vào file application.yml của Spring mà mong nó tự chạy. Một route gateway cần map **/v1/orders/** vào backend giữ path tương ứng và có policy cho **404 route không tồn tại, OPTIONS preflight và health**.

### 8.3. Spring Boot nhìn đúng public scheme

~~~properties
# Chỉ bật khi ingress đã strip/overwrite Forwarded/X-Forwarded-* tin cậy.
server.forward-headers-strategy=framework

# Minh họa graceful shutdown cho HTTP requests đang chạy.
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=20s
management.endpoint.health.probes.enabled=true
~~~

**server.forward-headers-strategy=framework** cho phép Spring Framework xử lý forwarded headers qua cơ chế tương ứng. Nó **không tự tạo trust boundary** và không thể biết client có giả header hay không. Với ứng dụng chạy sau ingress, chọn **FRAMEWORK hoặc NATIVE** phù hợp cấu hình container/proxy, **tránh xử lý forwarded headers hai lần**. Khi backend có thể bị gọi trực tiếp từ mạng không tin cậy, trước hết **khóa network access/strip headers**, không chỉ thay properties.

Nếu public URI luôn là **/v1/orders/{id}**, tạo **relative Location** giúp tránh phụ thuộc scheme/Host do proxy chuyển tiếp:

~~~java
import java.net.URI;
import java.util.UUID;
import org.springframework.http.CacheControl;
import org.springframework.http.ResponseEntity;

record CreatedOrder(UUID id, String state) {}

class OrderHttpResponses {
    static ResponseEntity<CreatedOrder> created(CreatedOrder order) {
        URI location = URI.create("/v1/orders/" + order.id());
        return ResponseEntity.created(location)
                .cacheControl(CacheControl.noStore())
                .body(order);
    }
}
~~~

Đoạn Java trên chỉ dựng response từ ID server đã tạo; **service phải COMMIT trước khi controller phát 201**. Nếu API có public prefix /api mà backend chỉ biết /v1, relative Location trong ví dụ phải dùng **public path thật**, hoặc gateway sửa Location theo quy tắc rõ được test. Không tạo Location từ **X-Forwarded-Host** tự khai. Với **201** cho resource đã commit nhưng payment chạy sau, body nên là **PENDING**, không “PAID” giả.

### 8.4. Spring Security ở backend và các route nội bộ

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class OrdersSecurityConfiguration {
    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http.authorizeHttpRequests(auth -> auth
                    .requestMatchers(HttpMethod.GET, "/v1/orders/**")
                        .hasAuthority("SCOPE_orders:read")
                    .requestMatchers(HttpMethod.POST, "/v1/orders")
                        .hasAuthority("SCOPE_orders:write")
                    .anyRequest().authenticated())
                .oauth2ResourceServer(oauth2 ->
                        oauth2.jwt(Customizer.withDefaults()))
                .sessionManagement(session ->
                        session.sessionCreationPolicy(
                                SessionCreationPolicy.STATELESS))
                .csrf(csrf -> csrf.disable())
                .build();
    }
}
~~~

**Chỉ tắt CSRF nếu đây thực sự là bearer-only API không xác thực thao tác ghi bằng cookie tự gửi**. Với browser session cookie hoặc BFF, bảo vệ CSRF ở route write. Cần dependency OAuth2 Resource Server, cấu hình JWT decoder **issuer, audience, lifetime, trusted algorithms/keys** và phân quyền từng order theo **tenant/owner**, không chỉ scope ở route. Đường **actuator/metrics/admin** nên nằm trên port/network/policy riêng; đoạn filter chain minh họa không thay thiết kế đó.

## 9. Observability xuyên proxy, gateway và service

Một **504 từ gateway** sẽ không xuất hiện trong metric HTTP 5xx của Orders API nếu request chưa tới service. Bởi vậy, dashboard cần nối ba lớp: **edge incoming**, **gateway upstream** và **backend HTTP/business outcomes**. Mỗi lớp ghi ít nhất request count/status, latency, connection active/pending và lỗi upstream.

### 9.1. Truy vết một request và một logical operation

~~~http
POST /v1/orders HTTP/1.1
Host: api.example.test
Authorization: Bearer <redacted>
Idempotency-Key: order-op-918
traceparent: 00-81bf2f4b7e1f46b38b63128a9f6c2385-7a0823d41c752e93-01
Content-Type: application/json

{"cartId":"c-918"}
~~~

**traceparent (W3C Trace Context)** giúp liên kết span của edge/gateway/orders/payment khi tất cả hop đều instrument và propagate đúng. **X-Request-ID** có thể phục vụ log một request; **Idempotency-Key/operationId** nhận diện logical operation qua nhiều attempt. Không dùng giá trị client cung cấp làm **định danh đáng tin hoặc metric label**; validate độ dài/ký tự, sinh ID tại trust boundary khi cần và không log token/baggage chứa PII.

| Triệu chứng | Metric/log cần so chéo |
|---|---|
| Edge 5xx tăng, backend 5xx không tăng | LB no healthy upstream, TLS/connect, gateway timeout |
| Gateway 504 tăng, service tiếp tục xử lý | Upstream timeout, DB query/lock, client cancellation sau commit |
| 401/403 tăng sau rollout | JWT issuer/audience/JWKS, policy gateway khác backend |
| 429 tăng | Throttle policy, key theo tenant/actor, lỗi NAT/false positive |
| p99 tăng nhưng CPU thấp | DB pool pending, queue, locks, network/dependency |
| POST retry khiến đơn trùng | Operation store/idempotency, proxy retry, concurrent requests |
| Read-after-write 404 | Replica lag/cache staleness hoặc tenant authorization |

Dashboard nên có **route template, method, status family, region, release version** với cardinality có hạn. Đừng đưa **orderId, sessionId, client IP, JWT hay raw path** thành metric label. Log/trace phải che **Authorization, Cookie, Set-Cookie, signed URLs và nội dung body nhạy cảm**. Hạn retention và quyền xem telemetry cần được kiểm soát như một hệ thống dữ liệu nội bộ.

## 10. Kiểm thử tích hợp từ client qua đúng chuỗi hop

**Unit test của controller không kiểm chứng proxy.** Cần môi trường test có TLS endpoint, routing thực, ít nhất hai replica của service và các policy gateway tương đương production. Để không gửi giao dịch thật, dùng database, payment stub, token/identity test và DNS/chứng chỉ phù hợp.

### 10.1. Ma trận hợp đồng và bảo mật

| Kịch bản | Cách thực hiện | Kết quả phải chứng minh |
|---|---|---|
| HTTPS public → backend HTTP/TLS | Gửi GET qua domain public | 200 đúng path, không redirect sang internal hostname |
| **201 + Location** | POST tạo resource đã commit | Location dùng URI public; GET Location đọc được resource trong scope |
| **Forwarded spoofing** | Client gửi X-Forwarded-Host/Proto/For giả | Edge ghi đè, backend không dựng URL hoặc identity từ header giả |
| Không có/sai bearer token | Gửi 401/403 từ public endpoint | WWW-Authenticate/Problem Details đúng, không forward token sang host lạ |
| Tenant A dùng ID của tenant B | Gửi GET/PUT có JWT A | Không lộ dữ liệu B, dù gateway auth đã pass |
| Preflight và cookie | OPTIONS/POST với Origin khác | CORS allowlist, Vary và CSRF policy đúng |
| Query/encoded path | %2F, duplicate slash, Unicode và query phức tạp | Proxy/gateway/Spring hiểu một canonical route hoặc từ chối an toàn |
| Header/body quá lớn | Gửi input vượt giới hạn | 413/431/400 theo hợp đồng, không OOM |
| Backend trả ETag/Cache-Control | GET/If-Match qua gateway | Header được bảo toàn; 412 không bị đổi thành 500 |
| Backend trả 409/429 | Gây conflict và vượt rate | Problem Details, Retry-After không mất ở gateway |
| Một replica lỗi readiness | Ngừng readiness của node | Không phân phối request mới sau propagation delay |
| Rolling deploy/drain | Tạo in-flight requests rồi shutdown | Request hoàn thành trong grace hoặc retry an toàn theo operation ID |
| Gateway timeout sau DB commit | Delay response tới quá deadline | Client không tạo đơn trùng khi retry cùng Idempotency-Key |
| Không còn healthy backend | Đánh rớt tất cả backend test | 503/502 theo implementation, cảnh báo và fallback được quan sát |
| Proxy mất scrape/trace | Chặn exporter hoặc gãy propagation | Có alert no-data, không báo healthy giả |

Mỗi test cần assert **cả response status, headers, body, side effect và telemetry**. Ví dụ với timeout sau COMMIT, chỉ assert “client nhận 504” không đủ: phải kiểm tra DB chỉ có **một logical order**, operation record lưu đúng kết quả và retry cùng key trả đúng outcome.

### 10.2. Test Java cho response Location độc lập Host

Đoạn JUnit 5 dưới đây kiểm tra method dựng response của mục 8.3:

~~~java
import java.net.URI;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpStatus;
import static org.junit.jupiter.api.Assertions.*;

class OrderHttpResponsesTest {
    @Test
    void createdUsesPublicRelativeResourceUri() {
        UUID id = UUID.fromString(
                "57337722-1111-4444-8888-999999999999");
        var response = OrderHttpResponses.created(
                new CreatedOrder(id, "PENDING"));

        assertEquals(HttpStatus.CREATED, response.getStatusCode());
        assertEquals(URI.create("/v1/orders/" + id),
                response.getHeaders().getLocation());
        assertEquals("PENDING", response.getBody().state());
        assertTrue(response.getHeaders().getCacheControl()
                .contains("no-store"));
    }
}
~~~

Test này **chỉ chứng minh builder Location**, chưa chứng minh reverse proxy giữ nguyên header hoặc DB đã COMMIT. Cần end-to-end integration test qua public HTTPS endpoint, có token và fixture dữ liệu, để xác minh **actual Location/Host/CORS/cookie**. Test Spring Security riêng với **MockMvc + spring-security-test** có thể kiểm tra 401/403/scope, nhưng mock JWT **không kiểm chứng chữ ký/issuer/audience thực**; phần đó cần integration test với IdP/JWKS giả lập hoặc test token được ký bằng khóa test.

Ví dụ kiểm tra bằng HTTP client trên test environment, không thực hiện giao dịch thật:

~~~bash
# Chạy với certificate tin cậy của test environment.
curl --include --silent --show-error \
  https://api.example.test/v1/health

# Header client giả mạo phải được edge strip/overwrite.
curl --include --silent --show-error \
  -H "X-Forwarded-Host: attacker.invalid" \
  -H "X-Forwarded-Proto: http" \
  https://api.example.test/v1/health
~~~

Các lệnh trên chỉ là **mẫu thao tác kiểm thử**; path /v1/health và tên domain cần được cấu hình trong environment test. Việc trả 200 không đủ để kết luận chống Host spoof: cần endpoint test có redirect/Location do Spring dựng, kiểm tra giá trị host/scheme **qua public edge** và kiểm chứng server không tin identity headers giả. Không dùng tùy chọn tắt kiểm tra chứng chỉ để “cho qua TLS”.

### 10.3. Fault injection đúng thời điểm

~~~text
TEST A — Failover khi chưa gửi request:
  Gateway gửi GET vào một node đang lỗi connect;
  theo policy cho phép retry bounded tới healthy node;
  assert GET thành công và không vượt retry budget.

TEST B — POST đã commit nhưng response bị cắt:
  Service ghi order + idempotency result và COMMIT;
  proxy cắt response hoặc timeout trước khi client nhận 201;
  client retry CÙNG key/payload;
  assert tổng số order = 1, không charge trùng.

TEST C — Graceful drain:
  Đưa node A ra khỏi readiness, giữ một request đang chạy;
  LB ngừng gửi request mới tới A;
  A hoàn thành request cũ trong grace (hoặc operation được đối soát).

TEST D — Gateway/DB quá tải:
  Giới hạn DB connection hoặc cho downstream trả 503;
  quan sát 502/503/504 theo nơi phát sinh;
  assert không xuất hiện retry storm và hệ thống hồi phục khi bỏ fault.
~~~

Sử dụng fault injection trên hệ **test/staging** có phạm vi rõ, không làm đứt hệ production để thử mà chưa có quy trình an toàn. Các bài test timing nên dùng barrier/proxy fault hooks có thể tái lập; **Thread.sleep** không phải bằng chứng request đã COMMIT hoặc LB đã ngừng route.

## 11. Runbook vận hành khi lỗi xuất hiện ở nhiều tầng

Một cảnh báo “API 5xx tăng” phải chỉ đến **dashboard và runbook** phân luồng được theo hop:

1. **Xác nhận ảnh hưởng:** bắt đầu từ RPS, error rate, p95/p99 ở public edge; tách 401/403/429 khỏi 5xx và xác định route/region.
2. **Tìm tầng phát lỗi đầu tiên:** so edge status, gateway upstream status/latency, backend traces và DB/pool metrics. Nếu edge 504 nhưng backend không thấy request, kiểm tra connect/routing; nếu backend tiếp tục sau timeout, kiểm tra commit uncertainty.
3. **Kiểm tra thay đổi gần nhất:** ingress rule, gateway policy, TLS/secret, route rewrite, deploy version, readiness config, DB migration. Cẩn thận khi rollback nếu schema đã thay đổi không tương thích.
4. **Giảm tác động:** loại replica không ready, điều chỉnh traffic/canary, hạn retries, tạm dừng workload nền hoặc mở circuit breaker theo policy; không tắt authorization/CSRF/idempotency chỉ để giảm lỗi.
5. **Đối soát business outcome:** kiểm tra order/operation IDs và outbox/payment statuses sau 502/504; không phát lại lệnh tài chính bằng key mới.
6. **Xác nhận hồi phục:** giảm 5xx, latency/queue trở lại mức chấp nhận, readiness ổn định, không có backlog/duplicate tăng; cập nhật incident timeline và runbook.

Runbook nên ghi **owner, escalation, dashboard deep link giữ time range, lệnh kiểm tra an toàn, điều kiện rollback và tiêu chí đóng**. Một response 503 do hết backend khỏe khác 503 do chính ứng dụng chủ động từ chối khi quá tải; nếu thiếu dấu vết **upstream response vs proxy-generated response**, quá trình điều tra sẽ nhầm hướng.

## 12. Bài tập: deploy REST API nhiều replica qua gateway

Một hệ thống **Orders API** có bốn Spring Boot replicas trong Kubernetes, gateway dùng JWT và rate limiting, public edge là reverse proxy terminate TLS. Client web dùng session cookie trên BFF, ứng dụng mobile dùng bearer token. POST /v1/orders có **Idempotency-Key**, API trả 201 nếu đơn đã commit hoặc 202 nếu mới tạo operation job bền vững. Sau deploy, khách phản ánh **Location dùng hostname nội bộ**, đôi lúc **504 sau khi vẫn bị trừ tiền**, và một số 403 xảy ra khi canary mới nhận request.

Hãy thiết kế và giải thích:

1. **Sơ đồ hop và trách nhiệm:** edge, gateway, service LB, Spring API, DB/outbox; xác định ai TLS terminate, ai kiểm JWT và ai kiểm owner/tenant.
2. **Forwarded headers:** policy strip/overwrite X-Forwarded-* ở public ingress, cơ chế Spring tiêu thụ header và cách chống Host poisoning; xử lý khi có CDN trước edge.
3. **URI/Location:** public path dùng /v1/orders, gateway rewrite hay preserve; test HTTP cho Location, ETag, Cache-Control và link phân trang.
4. **Health và rollout:** readiness, liveness, drain/grace, canary 5% và tiêu chí rollback; tránh tự restart cả cụm khi DB hơi chậm.
5. **Timeout/retry:** budget từ client tới DB, tình huống 504 sau COMMIT, idempotency và reconciliation với PSP.
6. **Bảo mật:** browser cookie CSRF, mobile bearer audience/scope, mTLS nội bộ, tenant isolation và CORS.
7. **Kiểm thử:** ít nhất sáu ca qua public endpoint, bao gồm XFF spoof, một node mất readiness, POST response-lost-after-commit, canary auth lỗi, no healthy backend và redirect/cookie.
8. **Quan sát/runbook:** phân biệt lỗi do edge, gateway và Spring; chọn metric, trace và điều kiện khép incident.

**Gợi ý:** dựng Location **tương đối theo URI public** hoặc dùng trusted public origin, không lấy từ header khách khai. Không retry POST giữa các replica khi chưa có idempotency store bền vững. Canary cần cùng version của public contract, JWT trust config và migration tương thích. **HTTP 504 là outcome chưa rõ đối với client**, không chứng minh payment đã rollback. Web cookie cần CSRF; JWT đã được gateway kiểm vẫn không thay domain authorization ở backend.

## 13. Checklist và tài liệu tham khảo

- [ ] Có sơ đồ các hop, ai quản lý TLS, route, auth, rate, health và backend ownership.
- [ ] Header **Forwarded/X-Forwarded-*** chỉ được tin sau trusted ingress strip/overwrite; backend không lộ trực tiếp ra Internet.
- [ ] Public **scheme/Host/URI/Location/OpenAPI** đồng nhất; rewrite, percent-encoding và query được test.
- [ ] **401/403/404/409/429/502/503/504** và **Retry-After/WWW-Authenticate** giữ đúng semantics.
- [ ] **JWT issuer/audience/scope** và domain tenant/owner được kiểm tra; CORS, CSRF và cookie có chính sách riêng.
- [ ] LB có readiness/drain, thuật toán phù hợp, canary/rollback và cơ chế session/operation bền vững.
- [ ] Timeout/retry có tổng deadline; POST side effect có idempotency + reconciliation, không coi cancel là rollback.
- [ ] Gateway cache/rate limit không làm lộ dữ liệu cá nhân hoặc phá read-after-write.
- [ ] Dashboard/trace nối từ edge tới service/DB; test fault injection trên nhiều replica và public HTTPS.

Tham khảo: **RFC 9110 HTTP Semantics**, https://www.rfc-editor.org/rfc/rfc9110.html; **RFC 7239 Forwarded HTTP Extension**, https://www.rfc-editor.org/rfc/rfc7239.html; **RFC 9457 Problem Details**, https://www.rfc-editor.org/rfc/rfc9457.html; **W3C Trace Context**, https://www.w3.org/TR/trace-context/; **Spring Boot Using Behind a Proxy**, https://docs.spring.io/spring-boot/reference/how-to/webserver.html; **Spring Security Resource Server**, https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html; **Nginx HTTP Proxy Module**, https://nginx.org/en/docs/http/ngx_http_proxy_module.html; **Kubernetes Probes**, https://kubernetes.io/docs/concepts/configuration/liveness-readiness-startup-probes/.

**Kết luận:** Reverse proxy bảo vệ/định tuyến HTTP ở biên, load balancer phân phối tới backend khỏe, còn API gateway áp chính sách API thống nhất; một sản phẩm có thể thực hiện nhiều vai trò. Để REST API vận hành đúng, phải kiểm tra **hợp đồng HTTP và ranh giới bảo mật trên toàn chuỗi**, từ Host/Forwarded tới commit và retry. **Một 201 đúng trong unit test chưa đủ nếu Location, headers, quyền, deadline hoặc idempotency bị phá ở tầng trung gian.**
