# Timeout, connection limit và chống resource exhaustion tại proxy, reverse proxy và load balancer

Trong chương **Proxy reverse proxy và cân bằng tải** của module **SECURITY_NETWORK_SECURITY**, thiết kế **timeout**, **connection limit** và biện pháp chống **resource exhaustion** (cạn kiệt tài nguyên) quyết định khả năng một hệ thống tiếp tục phục vụ người dùng hợp lệ khi traffic tăng đột biến, client gửi chậm, backend suy giảm hoặc có hành vi lạm dụng. Những control này không chỉ phục vụ hiệu năng: chúng giúp giới hạn tài nguyên mà một kết nối, một request, một tenant hoặc một upstream có thể chiếm giữ, tạo điều kiện cho firewall, WAF, IDS/IPS và các lớp phòng vệ mạng khác làm việc có hiệu quả.

Điểm khó là **không có một timeout hoặc số lượng kết nối tối đa đúng cho mọi dịch vụ**. Giới hạn quá cao có thể làm proxy hết file descriptor, bộ nhớ, CPU hoặc kết nối backend; quá thấp lại cắt đứt upload, gRPC streaming, WebSocket và những thao tác hợp lệ. Cần đo **đặc tính tải, độ trễ, số request đang xử lý, khả năng backend, thời gian phục vụ và hành vi retry** trước khi triển khai policy.

Sau bài học, bạn có thể:

- Phân biệt timeout theo **client–proxy**, **proxy–backend**, **kết nối idle**, **tổng request deadline** và **health check**.
- Phân biệt **TCP connections**, **HTTP requests**, **HTTP/2/HTTP/3 streams**, **active upstream connections**, **queue depth** và **request rate**.
- Giải thích nguyên nhân tài nguyên bị cạn: slow clients, large bodies, request fan-out, retry storms, TLS handshake load, connection leaks và upstream chậm.
- Xây dựng biện pháp phòng vệ theo lớp: **connection limits, rate limits, concurrency budgets, backpressure, bounded queues, circuit breakers, resource quotas và capacity planning**.
- Cấu hình và đọc một ví dụ **NGINX reverse proxy** có timeout, giới hạn và upstream pool, nhận biết giới hạn/ngữ nghĩa phụ thuộc phiên bản.
- Chẩn đoán bằng log, HTTP status, metrics, packet/flow evidence và kiểm thử tải có quyền mà không tạo sự cố cho production.

## 1. Đặt vấn đề: một request nhỏ có thể chiếm tài nguyên trong bao lâu?

Giả sử client truy cập một API qua reverse proxy:

~~~mermaid
flowchart LR
    C["Client / mobile / browser"] -->|TCP/TLS/HTTP| L["WAF / Load balancer"]
    L -->|HTTP request| P["Reverse proxy"]
    P -->|Upstream connection| A["Application service"]
    A -->|Query| D["Database / cache / dependency"]
    L -. "Ingress metrics" .-> S["Monitoring / SOC"]
    P -. "Timeout, pool, limits, errors" .-> S
    A -. "Queue, latency, saturation" .-> S
~~~

Một request có thể sử dụng hoặc tác động đến nhiều tài nguyên:

| Tầng | Tài nguyên có thể bị giữ | Triệu chứng khi quá tải |
| --- | --- | --- |
| **Client ↔ edge** | Socket, TLS state, connection-tracking entry, HTTP stream, receive/send buffer | Nhiều socket mở, handshake chậm, tỷ lệ timeout cao |
| **Load balancer / reverse proxy** | File descriptor, worker event state, header/body buffers, temporary disk files, request metadata | FD/memory/cpu cao, pending connections, 4xx/5xx tăng |
| **Proxy ↔ upstream** | TCP connection, keepalive pool, ephemeral port, SNAT/conntrack state | Connect timeout, upstream connection errors, pool bão hòa |
| **Application** | Worker/thread/event-loop task, memory, DB client, per-request state | p95/p99 latency tăng, queue dài, reject, OOM hoặc crash |
| **Dependency** | DB connections, locks, cache operations, remote API quota | Wait time tăng, timeout lan truyền sang API |

**Connection không bằng request.** Một TCP connection có thể mang nhiều request HTTP/1.1 theo thời gian; HTTP/2 và HTTP/3 còn cho phép nhiều **streams** đồng thời. Vì vậy, số socket “không quá lớn” không bảo đảm số request đang chạy thấp.

### 1.1. Resource exhaustion khác volumetric DDoS

**Volumetric DDoS** có thể làm nghẽn băng thông hoặc thiết bị upstream trước khi reverse proxy nhận request. **Resource exhaustion ở lớp ứng dụng** có thể xuất hiện với lưu lượng thấp hơn nhiều nhưng giữ tài nguyên lâu hoặc yêu cầu xử lý tốn kém. Cả hai có thể xảy ra cùng lúc.

Một số tình huống:

1. Client gửi header/body rất chậm và giữ kết nối lâu.
2. Backend xử lý một API mất hàng chục giây, nhiều request cùng chờ.
3. Frontend tự động retry khi gặp timeout, làm tải vào backend tăng mạnh.
4. Request upload lớn tiêu thụ RAM, disk temporary storage hoặc network bandwidth.
5. Một endpoint tạo nhiều lệnh gọi DB/dịch vụ phụ thuộc (*fan-out*), khuếch đại tài nguyên mỗi request.
6. Load balancer vẫn chuyển request tới backend đã yếu vì health check không đủ đại diện.

Những tình huống này **không nhất thiết là tấn công**; có thể do thay đổi ứng dụng, dependency lỗi hoặc lượng người dùng hợp lệ tăng.

## 2. Phân biệt các loại timeout

Từ “timeout” có thể chỉ nhiều đồng hồ khác nhau. Điều tra phải luôn hỏi **đồng hồ nào, bắt đầu tính khi nào, ngừng tính khi nào và bên nào quyết định đóng kết nối?**

| Timeout | Áp dụng tại đâu | Bảo vệ khỏi điều gì | Hiểu nhầm phổ biến |
| --- | --- | --- | --- |
| **TCP connect timeout** | Proxy khi thiết lập kết nối tới upstream | Next hop/backend không phản hồi thiết lập kết nối | Không phải tổng thời gian xử lý HTTP |
| **TLS handshake timeout** | TLS listener hoặc outbound TLS tới upstream | Bắt tay TLS không hoàn tất, giữ tài nguyên | Không thay thế request timeout sau handshake |
| **Client header read timeout** | Proxy nhận request headers | Header gửi quá chậm hoặc không hoàn chỉnh | Không phải hạn của response backend |
| **Client body read timeout** | Proxy nhận body/upload | Body bị treo hoặc gửi quá chậm | Cần xét upload thật từ mạng yếu |
| **Upstream send/write timeout** | Proxy gửi request cho backend | Backend không tiêu thụ dữ liệu đủ nhanh | Không có nghĩa mọi upload phải xong trước mốc này |
| **Upstream read timeout** | Proxy chờ hoặc đọc bytes từ backend | Backend không gửi dữ liệu trong thời gian chờ | Nhiều implementation đo khoảng **giữa các lần đọc**, không phải tổng request |
| **Client response send timeout** | Proxy ghi response tới client | Client không tiếp nhận dữ liệu, giữ send buffer/socket | Có thể cắt client chậm hợp lệ |
| **Idle keepalive timeout** | Kết nối chưa có request/stream tích cực | Kết nối rảnh giữ socket/bộ nhớ quá lâu | Không phải deadline của request đang xử lý |
| **Total request deadline** | Gateway, service hoặc ứng dụng nếu được hỗ trợ | Giới hạn thời gian **end-to-end** của một operation | Không giống chỉ đặt inactivity timeout |
| **Health check timeout** | LB kiểm tra backend | Tránh chọn endpoint không đạt điều kiện health | Health check xanh không chắc API thật khỏe |
| **Stream/connection lifetime** | WebSocket, gRPC, HTTP/2, QUIC | Kết nối kéo dài vô hạn ngoài nhu cầu | Không được dùng cùng số với API request ngắn mà không xét sản phẩm |

### 2.1. Inactivity timeout khác deadline

Ví dụ backend gửi một chunk dữ liệu mỗi 10 giây. Nếu **upstream read timeout = 30 giây** và được tính theo **khoảng giữa hai lần đọc thành công**, stream có thể chạy nhiều phút mà không timeout, vì chưa từng có khoảng im lặng quá 30 giây.

~~~text
t=0s     Proxy gửi request lên backend
t=10s    Backend gửi chunk 1
t=20s    Backend gửi chunk 2
t=30s    Backend gửi chunk 3
t=40s    Backend gửi chunk 4
...

Upstream read inactivity timeout: 30s
Total request deadline:            chưa được thiết lập trong ví dụ
~~~

Do đó, để giới hạn một operation không được kéo dài vượt mức SLO, đôi khi cần **request deadline riêng** tại gateway hoặc ứng dụng. Ngược lại, với SSE/gRPC streaming hợp lệ, một deadline tuyệt đối quá ngắn có thể là cấu hình sai.

### 2.2. Timeout nối tiếp nhau cần nhất quán

Giả sử:

~~~text
Client deadline:          5s
Edge request timeout:    10s
Reverse proxy timeout:   15s
App DB timeout:          30s
~~~

Đây là một **ngân sách thiếu nhất quán**: client có thể bỏ cuộc sau 5 giây, trong khi app tiếp tục chờ DB tới 30 giây và tiêu thụ tài nguyên. Proxy chưa chắc tự hủy tác vụ downstream khi client đóng kết nối.

Thiết kế tốt hơn cần quyết định **end-to-end SLO**, phân bổ thời gian cho từng dependency và truyền/cưỡng chế **deadline hoặc cancellation** qua các chặng có hỗ trợ, cộng thời gian mạng và cleanup:

~~~text
Operation budget minh họa:   4.0s
Edge/network overhead:       0.3s
App processing:              0.7s
DB/dependency budget:        2.5s
Safety/cleanup margin:       0.5s
~~~

Các giá trị chỉ để học; không tự đặt theo bảng này trên production. Một phần mềm proxy có thể chỉ có **inactivity timers** chứ không có request deadline theo kiểu này. Trong trường hợp đó cần cơ chế bổ sung ở ứng dụng/gateway và kiểm chứng cancellation thực tế.

### 2.3. Timeout không phải cơ chế diệt tất cả request

Khi proxy hết thời gian chờ, kết nối client có thể nhận lỗi nhưng backend **vẫn tiếp tục xử lý** tùy giao thức/cách ứng dụng phát hiện client disconnect. Tác vụ DB, queue hoặc external API có thể tiếp tục chạy.

Đối với các thao tác **ghi, thanh toán, tạo đơn hàng**, timeout **không chứng minh thao tác thất bại**. Nếu client retry mù quáng, có thể thực hiện trùng. Cần **idempotency key, request ID, reconciliation** và chính sách retry an toàn.

## 3. Connection limit đang giới hạn đơn vị nào?

**Connection limit** có thể có nhiều ý nghĩa:

- **Socket/TCP session concurrency:** số kết nối vật lý mở tại một listener hoặc proxy.
- **HTTP/1.1 active requests:** số request đang được xử lý, có thể không bằng số keepalive sockets idle.
- **HTTP/2/HTTP/3 concurrent streams:** nhiều request đồng thời trên một kết nối transport.
- **Upstream active connections:** số kết nối proxy dùng để trao đổi request với backend.
- **Per-source / per-identity limit:** số kết nối hoặc requests mà một IP, user, API key đã được xác thực hoặc tenant được phép có.
- **Global/instance/worker limit:** tổng tài nguyên một node, một process, một worker, một upstream pool hoặc cả cluster được phép sử dụng.

| Control | Đơn vị thường xét | Mục tiêu |
| --- | --- | --- |
| **Listener max connections** | TCP/QUIC sessions tại node hoặc listener | Không cho số socket vượt nguồn lực |
| **Per-client connection limit** | Connections hoặc concurrent requests theo key | Hạn chế một nguồn chiếm quá nhiều slot |
| **Max concurrent streams** | Streams trên mỗi HTTP/2/3 connection | Giới hạn multiplexing trên một kết nối |
| **Max active upstream connections** | Connections tới backend | Bảo vệ backend khỏi quá nhiều kết nối song song |
| **Request concurrency limit** | In-flight operations theo route/tenant | Giới hạn công việc tốn tài nguyên |
| **Rate limit** | Requests hoặc bytes mỗi đơn vị thời gian | Chặn tốc độ lạm dụng/burst theo chính sách |
| **Queue bound** | Số request đang chờ hoặc thời gian chờ | Ngăn backlog vô hạn và độ trễ tăng dây chuyền |
| **Bandwidth/body/header limit** | Bytes, kích thước/tốc độ dữ liệu | Hạn chế RAM, disk, network và parser workload |

**Rate limiting không giống connection limiting.** Một client có thể mở ít kết nối nhưng tạo hàng nghìn requests/giây qua HTTP/2; một client khác có thể mở nhiều kết nối mà không gửi nhiều request. Chỉ một trong hai control không đủ cho mọi hình thức cạn kiệt.

### 3.1. HTTP/2 và HTTP/3 làm thay đổi cách đếm

HTTP/2 ghép nhiều request đồng thời vào **streams trên cùng một TCP connection**. HTTP/3 thực hiện multiplexing qua **QUIC trên UDP**. Vì vậy:

- Đếm **TCP sockets** không đủ để giới hạn số HTTP requests đồng thời.
- Cần kiểm tra khả năng **max concurrent streams**, **max requests/in-flight**, **header limits** và flow-control của proxy được dùng.
- Một kết nối transport nhiều streams có thể giữ CPU/RAM và upstream requests đáng kể.
- HTTP/3 còn liên quan **QUIC connection state, stream limits, UDP path, idle timers** và khả năng thiết bị firewall/WAF quan sát lưu lượng.

Một số module connection limiting của reverse proxy có quy tắc riêng về HTTP/2/3. Ví dụ, ở NGINX, **mỗi concurrent HTTP/2 hoặc HTTP/3 request có thể được tính như một connection** đối với module `limit_conn` theo tài liệu/phiên bản tương ứng. Không suy luận ý nghĩa “connection” từ TCP packet count nếu chưa hiểu tính năng của sản phẩm.

### 3.2. Kết nối client và kết nối upstream có thể không 1:1

Proxy có thể:

- Duy trì client-side keepalive lâu hơn request.
- Dùng upstream keepalive pool chia sẻ qua nhiều request nối tiếp.
- Chuyển HTTP/2 từ client sang HTTP/1.1 tới backend.
- Buffer request/response và giải phóng backend connection trước khi gửi hết response tới client.
- Mở nhiều kết nối tới nhiều upstream khi request routing/fan-out có yêu cầu.

Vì vậy, cần theo dõi **client connections, active requests, upstream connections và backend workers** độc lập. Việc “proxy còn 5.000 socket” chưa đủ xác định backend có đang chịu 5.000 concurrent operations hay không.

## 4. Vì sao hệ thống bị resource exhaustion?

### 4.1. Nguồn lực cạn kiệt

| Tài nguyên | Nguyên nhân điển hình | Evidence |
| --- | --- | --- |
| **File descriptors / sockets** | Quá nhiều kết nối mở, keepalive/idle lâu, rò rỉ socket | Open FD, active/idle connections, accept errors |
| **RAM và proxy buffers** | Nhiều request/response lớn, TLS/session state, HTTP/2 streams | RSS/heap, buffer usage, OOM logs |
| **CPU** | TLS handshake, request parsing, nén, WAF rules, JSON/XML processing | CPU/worker saturation, handshake/inspection latency |
| **Temporary disk** | Request body/response buffering, upload lớn, spill-to-disk | Disk free, tmp file count, I/O wait, 507/5xx tùy hệ thống |
| **Conntrack/NAT entries** | Nhiều flows, idle timers quá dài, DDoS | Conntrack usage/drops, firewall session table |
| **Ephemeral ports/SNAT capacity** | Nhiều outbound connections đến cùng đích, keepalive thấp, churn | Upstream connect failures, port exhaustion metrics |
| **Application threads/tasks** | Slow DB, blocking I/O, lock contention | Busy workers, queue wait, thread pool saturation |
| **Database pool** | In-flight requests quá nhiều, query chậm hoặc giữ connection lâu | Pool active/waiters, query timeouts, lock metrics |
| **Network bandwidth** | Upload/download lớn, amplification, traffic cao | Bytes/sec, drops, retransmissions, upstream utilization |

Trong cấu hình proxy, tăng `worker_connections` hoặc `ulimit -n` mà không xét RAM, conntrack, backend và băng thông có thể chỉ **dời nút nghẽn** sang tầng khác.

### 4.2. Slow client và slow upstream là hai vấn đề khác nhau

**Slow client:** trình duyệt, thiết bị IoT, mạng di động yếu hoặc client không gửi/nhận bytes đều. Proxy có thể bị giữ socket và buffers nếu không có client-side timeouts, kích thước body/header và buffering policy phù hợp.

**Slow upstream:** backend chậm vì xử lý, DB, deadlock hoặc phụ thuộc lỗi. Proxy chờ upstream khiến **in-flight requests** tăng; nếu không giới hạn, quá tải có thể lan sang nhiều instance.

Nguy cơ **Slowloris-style resource exhaustion** liên quan giữ rất nhiều kết nối HTTP chưa hoàn chỉnh bằng tốc độ gửi chậm. Phòng vệ chính là **header/body timeout, connection quotas, request limits, công nghệ proxy event-driven và điều kiện mạng phù hợp**. Không cần phát thử tấn công đó trên production để xác minh control.

### 4.3. Throttling cần đặt trước nơi tốn tài nguyên

Nếu request đã qua TLS handshake, WAF inspection, tải body lớn và gọi DB rồi **mới** bị rate limit, tài nguyên đã tiêu hao đáng kể. Nên áp các control phù hợp **càng sớm càng tốt**:

1. **Edge/DDoS provider, network ACL và firewall** để giảm traffic không mong muốn ở các lớp có thể quan sát.
2. **TLS listener/proxy** để giới hạn handshake, header/body và kết nối không hoàn chỉnh.
3. **WAF/API gateway** để kiểm tra request, rate/identity quotas và chính sách endpoint.
4. **Application** để giới hạn concurrency, chi phí truy vấn, deadline và cancellation.
5. **Database/dependency** để có pool/quota/timeout riêng, không phụ thuộc duy nhất vào reverse proxy.

Chặn sớm giúp tiết kiệm tài nguyên nhưng phải hiểu tác động lên các client dùng **NAT, CDN, mobile carrier hoặc proxy doanh nghiệp**.

## 5. Định lượng bằng Little's Law và ngân sách concurrency

Một cách ước lượng trong trạng thái ổn định là **Little's Law**:

\[
L = \lambda W
\]

Trong đó:

- **L:** số request trung bình đang hiện diện/đang xử lý trong hệ thống.
- **λ (lambda):** tốc độ request hoàn tất/đi qua hệ thống trong trạng thái ổn định (requests/giây).
- **W:** thời gian trung bình một request ở trong hệ thống (giây).

Ví dụ cùng tốc độ **600 request/giây**:

| Thời gian trung bình W | In-flight trung bình L ≈ λ × W |
| --- | ---: |
| **0,2 giây** | **120 requests** |
| **1 giây** | **600 requests** |
| **2 giây** | **1.200 requests** |
| **5 giây** | **3.000 requests** |

Khi backend chậm từ 0,2 lên 2 giây, số in-flight cần chứa **tăng khoảng 10 lần** nếu hệ thống còn nhận được lượng request như cũ. Đây là lý do một sự cố DB có thể trở thành **socket/worker exhaustion** dù traffic đầu vào không tăng.

**Giới hạn của phép tính:** Little's Law dựa trên hệ thống ổn định và số trung bình, không tự dự đoán p99, queue burst, retry fan-out hoặc số kết nối TCP. Nếu hệ thống bắt đầu reject/throttle hoặc throughput giảm, phải đo lại λ và W theo thực tế.

### 5.1. Sizing một backend pool

Giả sử có **hai application instances** và mỗi instance được thử nghiệm chịu an toàn **tối đa 300 in-flight requests** với workload cụ thể, thì tổng ngân sách lý thuyết khoảng **600** trước khi tính headroom, skew phân phối và trường hợp một node hỏng.

Để thiết kế an toàn:

- Đo **capacity theo loại endpoint** (API đọc nhẹ khác upload và báo cáo dài).
- Trừ phần dung lượng cho **health checks, quản trị, background jobs, retry và failover**.
- Xác định chính sách khi còn **một replica**: giảm admission hoặc chấp nhận SLO giảm có kiểm soát.
- Đặt **queue bound** và thời gian chờ, không tích lũy request vô hạn trong RAM.
- Bảo đảm rate limit và queue không khiến retry lặp lại và làm traffic vượt năng lực backend.

Không lấy một con số từ ví dụ này làm mặc định cho mọi API.

## 6. Bounded queue, load shedding và backpressure

Khi lượng yêu cầu tới vượt tốc độ xử lý, hệ thống có hai lựa chọn lớn:

1. **Đưa vào hàng đợi** để chờ capacity, nếu chờ còn giá trị với người dùng.
2. **Từ chối/giảm tải sớm** để bảo vệ tài nguyên và latency của những request được chấp nhận.

Nếu hàng đợi **không giới hạn**, request có thể chờ tới khi client đã timeout, khiến CPU/RAM vẫn bị tiêu thụ và làm tình hình xấu hơn. Một **bounded queue** giúp đặt trần số việc tồn đọng.

~~~mermaid
flowchart LR
    I["Incoming requests"] --> L["WAF / Rate & connection policy"]
    L --> A{"Còn concurrency budget?"}
    A -->|Có| U["Backend / worker pool"]
    A -->|Hết| Q{"Queue còn chỗ và deadline còn đủ?"}
    Q -->|Có| B["Bounded queue"]
    B --> U
    Q -->|Không| R["Load shed: 429/503 theo policy"]
    U --> O["Response + telemetry"]
    R --> O
~~~

### 6.1. Hạn chế chờ quá lâu

Nếu **total deadline của client** còn 1 giây nhưng **queue wait dự kiến** 3 giây, nhận thêm request vào queue thường không có ích. Có thể dùng admission policy theo **deadline còn lại, route priority, tenant quota và khả năng backend**, nếu nền tảng hỗ trợ.

Đặc biệt, các request có **thao tác ghi** cần phân biệt rõ:

- **Accepted/queued:** request đã nhận nhưng chưa hoàn tất.
- **Timed out:** bên gọi không nhận kết quả đúng hạn, kết quả backend chưa chắc đã thất bại.
- **Rejected before execution:** proxy/gateway từ chối trước khi có tác dụng phụ.

Đừng trả một mã phản hồi khiến client suy luận “an toàn retry” nếu backend có thể đã xử lý một phần. API cần **idempotency semantics** hoặc cơ chế kiểm tra trạng thái.

### 6.2. Circuit breaker

**Circuit breaker** giới hạn việc tiếp tục gọi một dependency đang thất bại hoặc quá chậm, nhằm bảo vệ worker và upstream:

~~~text
CLOSED    -> Request đi qua, hệ thống theo dõi error/latency
OPEN      -> Tạm thời từ chối hoặc fallback theo policy
HALF-OPEN -> Cho phép số probe giới hạn để kiểm tra phục hồi
~~~

Trạng thái/ngưỡng là mô hình khái niệm; các proxy/service mesh khác nhau có implementation khác nhau. Circuit breaker phải phối hợp **outlier detection, health checks, concurrency limits và retry budgets** để tránh mọi instance cùng chuyển trạng thái theo cách gây dao động.

### 6.3. Retry storms làm tăng tải

Giả sử frontend gửi **1 request** nhưng proxy tự retry tối đa 3 lần tới các backend và client cũng retry 3 lần. Tải tới downstream có thể lớn hơn rất nhiều so với số thao tác người dùng ban đầu.

Phòng vệ:

- Chỉ retry lỗi **phù hợp và request idempotent**, hoặc có idempotency key/thiết kế an toàn.
- Giới hạn **tổng attempt và thời gian** trong end-to-end deadline.
- Sử dụng **exponential backoff với jitter** và retry budget.
- Không retry ngay hàng loạt khi đang **503/429**; tôn trọng `Retry-After` nếu hệ thống dùng đúng semantics và client hỗ trợ.
- Cân nhắc giảm/khóa retries khi backend đã quá tải; retry có thể khuếch đại resource exhaustion.

## 7. HTTP response status và sự thật phía sau lỗi

| Status / tín hiệu | Ý nghĩa thường gặp | Điều không nên kết luận vội |
| --- | --- | --- |
| **408 Request Timeout** | Server không nhận được request đầy đủ trong thời gian mong đợi, tùy implementation | Không chứng minh backend bị lỗi |
| **413 Content Too Large** | Request body vượt giới hạn cho phép | Không mặc nhiên là payload tấn công |
| **429 Too Many Requests** | Rate/quota policy từ chối thêm request | Không đồng nghĩa client đã mở quá nhiều TCP connections |
| **502 Bad Gateway** | Gateway nhận response không hợp lệ hoặc lỗi ở giao tiếp upstream | Không tự nói nguyên nhân là timeout |
| **503 Service Unavailable** | Service tạm không thể xử lý, có thể do quá tải, maintenance hoặc limit | Cần xem policy/server logs để phân biệt |
| **504 Gateway Timeout** | Gateway không nhận được phản hồi upstream đúng hạn | Có thể request vẫn xử lý ở backend |
| **499 trong NGINX logs** | Mã **không chuẩn** NGINX dùng khi client đóng kết nối trước khi server trả response | Không tự chứng minh client ác ý hoặc proxy timeout |
| **TCP reset/FIN hoặc QUIC close** | Kết nối bị đóng theo một đường nào đó | Không đồng nghĩa đã có HTTP response, cần đối chiếu flow/session |

**Mã lỗi thực tế do cấu hình và sản phẩm quyết định**. Chẳng hạn một số module connection/rate limit của NGINX mặc định có thể trả **503** nếu không đặt status khác; không được khẳng định mọi limit violation đều là HTTP 429.

### 7.1. Phân biệt 504 và 499

- **504** thường do proxy/gateway kết thúc việc chờ upstream theo timeout và tạo phản hồi lỗi nếu có thể.
- **499 trong NGINX access log** thường ghi client đã đóng kết nối trước khi proxy kết thúc xử lý hoặc trả response.
- Hai loại event có thể xuất hiện trong chuỗi request của cùng một nghiệp vụ qua nhiều proxy hoặc trong các retry khác nhau.

Phải ghép **request ID, trace ID, timestamps, upstream timing và status ở từng hop**. Chỉ đếm các mã status tổng hợp không đủ để xác định timeout nào cần sửa.

## 8. Cấu hình minh họa NGINX reverse proxy có giới hạn

Đoạn sau là **mẫu học tập**, không phải cấu hình production hoàn chỉnh. Giả định reverse proxy trực tiếp nhận client và có **hai backend private**, certificate phù hợp và tài nguyên đã sizing. Trước triển khai cần kiểm tra cú pháp, module và **ngữ nghĩa chính xác của phiên bản NGINX**.

~~~nginx
# Mẫu minh họa; không copy nguyên xi vào production.
events {
    worker_connections 4096;
}

http {
    # Key là IP peer mà NGINX đang thấy.
    # Nếu đặt sau CDN/LB, phải xử lý real IP trên trust boundary đúng.
    limit_conn_zone $binary_remote_addr zone=per_client_conn:10m;
    limit_req_zone  $binary_remote_addr zone=per_client_req:10m rate=15r/s;

    upstream app_pool {
        # Shared upstream state hỗ trợ giới hạn giữa các worker theo tính năng.
        zone app_pool 64k;
        least_conn;

        server 10.20.30.11:8080 max_conns=200 max_fails=3 fail_timeout=10s;
        server 10.20.30.12:8080 max_conns=200 max_fails=3 fail_timeout=10s;
        keepalive 32;
    }

    server {
        listen 443 ssl;
        server_name app.example.test;

        ssl_certificate     /etc/nginx/tls/app-chain.pem;
        ssl_certificate_key /etc/nginx/tls/app.key;

        client_header_timeout 10s;
        client_body_timeout   20s;
        client_max_body_size  10m;
        keepalive_timeout     15s;
        send_timeout          30s;

        # Policy minh họa: vi phạm giới hạn trả lỗi theo lựa chọn ở đây.
        limit_conn_status 429;
        limit_req_status  429;

        location / {
            limit_conn per_client_conn 20;
            limit_req zone=per_client_req burst=30 nodelay;

            proxy_http_version 1.1;
            proxy_set_header Host $host;
            proxy_set_header X-Request-ID $request_id;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;

            proxy_connect_timeout 3s;
            proxy_send_timeout    20s;
            proxy_read_timeout    30s;

            proxy_pass http://app_pool;
        }
    }
}
~~~

Tên miền **app.example.test** dành cho ví dụ. Địa chỉ 10.20.30.11/12 là private-address minh họa; certificate path, upstream ports, mức tải, TLS policy, header và log phải được thay bằng cấu hình được phê duyệt. Đây cũng **không phải mẫu WAF, DDoS protection hoặc TLS hardening đầy đủ**.

### 8.1. Ý nghĩa các giới hạn trong mẫu

| Directive | Vai trò khái niệm | Điểm cần kiểm chứng |
| --- | --- | --- |
| `worker_connections` | Giới hạn số kết nối mà một worker có thể mở theo cơ chế NGINX | Gồm cả client/upstream; còn phụ thuộc file-descriptor limit, worker count và hạ tầng |
| `limit_conn_zone` | Định nghĩa shared zone lưu trạng thái limit theo key | Kích thước zone, số lượng keys và trust của source IP |
| `limit_conn` | Giới hạn concurrent connections/requests theo ngữ nghĩa module | H2/H3, chỉ request đã đọc đầy đủ header mới được tính theo policy của module |
| `limit_req_zone` | Định nghĩa tốc độ request theo key | NAT/shared IP, fair usage, burst và tính hiệu lực giữa workers |
| `limit_req` | Giới hạn tốc độ/burst request | `nodelay` làm các request nằm trong burst được xử lý mà không chờ theo ngữ nghĩa module; vẫn cần concurrency budget |
| `max_conns` trên upstream server | Giới hạn active connections tới backend | Với upstream zone/keepalive/multiple workers, tổng socket và active count có các caveat theo phiên bản |
| `client_header_timeout` | Giới hạn thời gian nhận request header | Chống client giữ header lâu; không thay giới hạn header size |
| `client_body_timeout` | Timeout khi đọc body từ client | Phải thử mạng di động/upload hợp lệ |
| `keepalive_timeout` | Thời gian idle của client keepalive connection | Không phải upstream read deadline |
| `proxy_connect_timeout` | Timeout thiết lập kết nối tới backend | Khác TLS handshake hoặc xử lý request toàn phần |
| `proxy_send_timeout` | Timeout giữa các hoạt động ghi request đến upstream | Không phải tổng thời gian upload/request |
| `proxy_read_timeout` | Timeout giữa các lần đọc từ upstream | Backend gửi chunk đều có thể giữ response lâu hơn giá trị đặt |
| `send_timeout` | Timeout giữa các hoạt động ghi response tới client | Client cực chậm có thể bị đóng để giải phóng tài nguyên |

Một proxy có thể xử lý **nhiều lớp timeout đồng thời**. Khi một timer kích hoạt, log nào được ghi và client nhận lỗi gì phụ thuộc trạng thái đã gửi header/body, giao thức và khả năng xử lý của proxy.

### 8.2. Cẩn trọng với IP nguồn và X-Forwarded-For

Ví dụ dùng `$binary_remote_addr` làm key. Nếu NGINX nằm **sau CDN hoặc load balancer**, `remote_addr` có thể là IP của node upstream, dẫn đến **gộp nhiều người dùng vào một quota** và chặn nhầm.

Mặt khác, không được tin trực tiếp giá trị `X-Forwarded-For` do client Internet tự khai để phân bổ quota: kẻ gửi request có thể thay header và giả nguồn.

Đúng cách là:

1. Xác định **proxy hops** thực sự được tin, mạng/certificate kiểm soát đường truyền và quy tắc ghi header tại edge.
2. Chỉ cấu hình **real-IP trust** cho **địa chỉ CIDR của proxy được phép**, không dùng `0.0.0.0/0` chỉ để “sửa IP”.
3. Kiểm tra liệu edge đã **xóa/ghi đè các client-supplied forwarding headers** trước khi gửi downstream chưa.
4. Dùng **verified identity/tenant key** cho quota nhạy cảm khi có thể; header chưa được xác thực không phải identity.
5. Kiểm thử trường hợp **CGNAT, VPN concentrator, Wi-Fi guest hoặc corporate proxy** có nhiều người dùng chung IP.

### 8.3. Những giới hạn còn thiếu trong mẫu

Mẫu NGINX trên không có: limit request header fields/size, TLS handshake controls, OS FD limits, `proxy_buffering` sizing, request deadlines tuyệt đối, application concurrency, global multi-node rate limiting, gRPC/WebSocket policy, abuse scoring, WAF rules hoặc per-user fair scheduling. **Không được xem một cấu hình minh họa là cấu hình chống DDoS toàn diện**.

Thêm nữa, `max_conns` và upstream keepalive có caveat: **kết nối idle được giữ ở worker khác hoặc kết nối trong lúc cân bằng tải** có thể khiến tổng TCP sockets tới backend lớn hơn số active connections được cấu hình. Phải đo thực tế cả hai phía.

## 9. Timeout cho WebSocket, SSE, gRPC và upload/download

### 9.1. WebSocket

WebSocket có thể nâng cấp từ HTTP rồi duy trì **kết nối hai chiều lâu dài**. Nếu proxy đặt `proxy_read_timeout` thấp nhưng ứng dụng không có traffic/ping ở khoảng đó, socket có thể bị đóng dù use case hợp lệ.

Cần:

- Chính sách **idle timeout** phù hợp và **ping/pong/heartbeat** được thiết kế giữa client, proxy và backend.
- **Max connection lifetime** hoặc session revalidation nếu có nhu cầu, nhưng không dùng ngưỡng quá nhỏ gây reconnect storm.
- Hạn mức **concurrent WebSockets** riêng theo tenant/user khi có khả năng.
- Kiểm soát **message/frame size**, outbound send buffers và backpressure cho client đọc chậm.
- Xử lý reconnect với **jitter** và authentication refresh, không để hàng nghìn clients cùng reconnect ngay khi deploy.

### 9.2. Server-Sent Events (SSE)

SSE thường giữ HTTP response mở để server đẩy event. Một upstream inactivity timer có thể được thiết kế đủ để hỗ trợ **SSE heartbeat** và chu kỳ event thực tế. Không nên tăng mọi timeout toàn site chỉ để giải quyết một SSE route; ưu tiên **policy theo đường dẫn** có được kiểm thử.

### 9.3. gRPC streaming

gRPC thường chạy trên HTTP/2 và có **deadlines/cancellation** ở tầng RPC. Cần phân biệt:

- **Unary RPC:** thích hợp với thời hạn xử lý hữu hạn.
- **Client/server/bidirectional streaming:** có thể kéo dài và cần liveness/idle settings riêng.
- **HTTP/2 stream concurrency:** một TCP connection có thể mang nhiều RPC đồng thời; giới hạn sockets không đủ.
- **Transport keepalive:** ping quá dày có thể bị gateway/server giới hạn hoặc từ chối; phải phối hợp chính sách.

Nếu proxy không hiểu chính xác **gRPC/HTTP2 trailers, status codes và cancellation**, một HTTP 200 ở edge có thể không đồng nghĩa RPC thành công. Giám sát thêm **gRPC status, deadlines exceeded và stream resets**.

### 9.4. Upload và download lớn

Một upload có thể cần thời gian gửi body dài, nhất là trên mạng di động. Những control thích hợp có thể gồm:

| Control | Ý nghĩa |
| --- | --- |
| **Max body size** | Giới hạn bytes tối đa một request hợp lệ có thể đưa vào hệ thống |
| **Client body timeout** | Không để client giữ socket vô hạn mà không gửi đủ dữ liệu |
| **Streaming vs buffering** | Chọn trade-off giữa an toàn backend, latency, memory và temporary storage |
| **Upload authentication/quota** | Không để anonymous client tải tùy ý lên disk/object store |
| **Chunked/resumable upload** | Giảm tác động khi mất kết nối, cần validate chunk và authorization |
| **Virus/malware scanning** | Kiểm soát payload sau upload theo threat model, không thay limit |

**`proxy_request_buffering` và `proxy_buffering`** có thể giảm hoặc tăng việc giữ tài nguyên ở các chặng khác nhau. Tắt buffering để tiết kiệm disk không mặc nhiên tốt hơn: có thể giữ backend connection lâu hơn khi client chậm. Bật buffering cũng cần **disk quota, filesystem monitoring và bảo vệ temporary files**.

## 10. Các lớp phòng vệ bổ trợ: WAF, CDN, firewall, IDS/IPS

Timeout/connection limit không thể tự mình xử lý mọi nguy cơ. Đặt chúng trong kiến trúc nhiều lớp:

~~~mermaid
flowchart LR
    I["Internet / clients"] --> E["DDoS edge / CDN"]
    E --> F["Firewall / network policy"]
    F --> W["WAF / API gateway"]
    W --> P["Reverse proxy / load balancer"]
    P --> A["Application pool"]
    A --> D["DB / external dependencies"]
    E -. "Traffic trends" .-> S["SOC / SRE telemetry"]
    W -. "Rate / abuse / WAF rules" .-> S
    P -. "Connections / timeouts" .-> S
    A -. "Latency / pool / 5xx" .-> S
~~~

### 10.1. Khi nào áp control ở đâu?

| Control | Vị trí thường hiệu quả | Giới hạn |
| --- | --- | --- |
| **Volumetric DDoS mitigation** | Upstream ISP/CDN/edge có dung lượng phù hợp | Không thay thế giới hạn ứng dụng và backend |
| **L3/L4 firewall + conntrack quotas** | Network boundary/host | Không hiểu hết HTTP request semantics nếu không có L7 visibility |
| **WAF / API rate policy** | HTTP-aware edge sau TLS termination phù hợp | Có thể tốn CPU và tạo false positive; quota key phải đáng tin |
| **Connection/stream limits** | Listener/reverse proxy/gateway | Không giải quyết chi phí DB của request ít nhưng đắt |
| **Application concurrency** | Backend/service framework | Cần phối hợp queue, timeout và reject semantics |
| **DB pool/query timeout** | Application và database | Không bảo vệ băng thông L3/L4 |
| **IDS/IPS/NDR** | Các điểm quan sát lưu lượng được lựa chọn | Một alert không chứng minh prevention hoặc kết quả end-to-end |
| **Identity quota / tenant fairness** | API gateway + application | Cần xác thực identity trước khi tính quota |

### 10.2. Tránh mở rộng quyền để “sửa 504”

Một số lỗi timeout do route, firewall hoặc DNS, nhưng **nới firewall thành Any–Any** thường không giải quyết đúng nguyên nhân. Hãy kiểm tra:

- DNS và hostname upstream có trỏ tới backend đúng không?
- Route/NAT/VRF có đưa traffic qua đúng security boundary không?
- TCP connect hoặc TLS handshake có hoàn tất không?
- Firewall có **deny event** cho đúng 5-tuple/session không?
- Backend có trả byte nào trước read timeout không?

Chỉ thay policy khi có bằng chứng, có scope hẹp và rollback được kiểm thử.

## 11. Metrics cần đo trước khi chọn timeout và connection limit

Một bộ dashboard nên nhìn thấy **nhiều tầng** và phân biệt success/rejection/timeout.

| Metric / nhóm | Vai trò chẩn đoán | Nguy cơ khi thiếu |
| --- | --- | --- |
| **Request rate (RPS/QPS)** theo endpoint/tenant | Đo tải và burst | Khó phân biệt traffic tăng với backend chậm |
| **Active/idle client connections** | Đo socket pressure | Chỉ nhìn active requests sẽ bỏ sót idle socket |
| **Concurrent requests/streams** | Đo thực sự có bao nhiêu công việc đang chạy | H2/H3 giấu tải khi chỉ đếm TCP |
| **Upstream active/idle connections** | Đánh giá áp lực/backend pool | Không biết nghẽn upstream hay frontend |
| **Queue depth và queue wait** | Nhận biết backpressure và rủi ro timeout trước xử lý | Queue dài có thể che capacity saturation |
| **p50/p95/p99 total latency** | Đo trải nghiệm người dùng và tail | Average che mất nhóm slow requests |
| **DNS/connect/TLS/TTFB/upstream response timing** | Tách đoạn gây trễ | “504” không chỉ ra nơi nghẽn |
| **408/413/429/499/502/503/504** | Tách từ chối chính sách, client abort và lỗi upstream | Dễ gộp sai mọi mã lỗi thành “WAF chặn” |
| **Timeout causes và limit triggers** | Xác định control nào đã kích hoạt | Không biết nên sửa policy hay capacity |
| **CPU/RSS/FD/worker utilization** | Đo nguồn lực proxy/host | Tăng limit có thể gây OOM/FD exhaustion |
| **Conntrack/SNAT port usage** | Nhìn giới hạn mạng/hệ điều hành | Nhầm connect timeout thành ứng dụng chậm |
| **Backend thread/DB pool** | Tìm bottleneck thực | Tuning proxy không giải quyết DB bão hòa |
| **Health/retry/circuit breaker** | Đánh giá failover và amplification | Retry storm có thể duy trì outage |

### 11.1. Log request nên có gì?

Một bản ghi normalized có thể gồm:

~~~json
{
  "timestamp": "2026-11-28T03:20:13.120Z",
  "request_id": "req-example-027",
  "route": "/api/search",
  "client_ip_observed": "198.51.100.24",
  "tenant_id": "tenant-demo",
  "method": "GET",
  "status": 504,
  "duration_ms": 30012,
  "upstream": "app-02",
  "upstream_connect_ms": 8,
  "upstream_first_byte_ms": null,
  "limit_action": "none",
  "timeout_type": "upstream_read",
  "retry_attempts": 1,
  "response_bytes": 172
}
~~~

Đây là **schema học tập do nhóm tự chuẩn hóa**, không phải các field sẵn có ở mọi proxy. Các trường `timeout_type`, `tenant_id`, `retry_attempts` cần được triển khai thực tế trước khi log. Không lưu session token, password, raw auth header hoặc payload nhạy cảm chỉ để điều tra timeout.

Địa chỉ **198.51.100.24** thuộc dải dành cho tài liệu. Khi báo cáo production, nên áp bảo vệ dữ liệu cá nhân, thời hạn lưu và quyền truy cập log theo chính sách.

### 11.2. Đối chiếu log khi có nhiều proxy

~~~text
Client -> CDN -> WAF -> Reverse Proxy -> App -> DB

request_id: req-example-027
Edge:        request received, latency high
WAF:         allowed, no rate block
Proxy:       upstream_read_timeout
App:         DB pool wait > budget, work still in progress
DB:          slow query / connection pool saturation
~~~

Không có **request/trace ID** liên thông thì dễ nhầm lỗi ở WAF hoặc proxy là nguyên nhân, trong khi nó chỉ là nơi timeout được **phát hiện**. Cần phân biệt **nơi báo lỗi**, **nơi gây chậm** và **bước đầu tiên trong chuỗi khiến load vượt capacity**.

## 12. Phương pháp xác lập threshold và SLO

Các con số timeout/limit phải dựa trên workload:

1. **Phân loại routes:** health check, API đọc nhanh, thao tác ghi, báo cáo dài, file upload, WebSocket/SSE, gRPC stream.
2. **Thu baseline:** RPS, p50/p95/p99 latency, error budget, request size, concurrency, peak-to-average ratio, DB pool và số replica.
3. **Chọn SLO:** ví dụ 99% request API ngắn hoàn tất trong giới hạn do sản phẩm cam kết; không áp chung cho mọi loại.
4. **Phân bổ deadline:** client, edge, app, dependency; chừa overhead mạng/cancellation margin.
5. **Chọn connection/concurrency/rate limit:** dựa trên thử nghiệm capacity và ngân sách tài nguyên, không chỉ theo số concurrent users.
6. **Thiết kế overload behavior:** queue bound, shed priority, status, Retry-After, retry budget, fallback và scale khi phù hợp.
7. **Pilot có quan sát:** phát hiện false positives, NAT group impact, timeout tại mạng di động và ứng dụng streaming.
8. **Kiểm thử failover:** một backend lỗi thì pool còn phục vụ được bao nhiêu request? Admission có tự giảm tương ứng không?
9. **Gắn owner:** ai thay chính sách, điều kiện rollback và cảnh báo khi threshold gây tác động người dùng.

### 12.1. Ví dụ bảng mục tiêu theo route

| Lớp request | Mục tiêu khái niệm | Chính sách cần cân nhắc |
| --- | --- | --- |
| **GET nhỏ, cacheable** | Latency thấp, dễ retry khi đúng semantics | Deadline ngắn, rate/quota, cache, concurrency theo route |
| **POST tạo tài nguyên** | Không ghi trùng khi timeout | Idempotency key, deadline phù hợp, tránh retry mù |
| **Báo cáo dài** | Có thể cần thời gian lớn | Async job + job ID/status thay vì giữ HTTP worker quá lâu |
| **Large upload** | Client có thể gửi chậm | Max body, streaming/resumable, quota/disk, read timeout phù hợp |
| **WebSocket/SSE** | Kết nối dài hợp lệ | Heartbeat/idle/lifetime, per-user connection quota, backpressure |
| **gRPC streaming** | Duy trì stream và cancellation đúng | Stream concurrency, keepalive, deadline theo RPC type |
| **Health check** | Phát hiện backend sẵn sàng | Timeout rất rõ, không gọi dependency tốn kém vô hạn |

Giá trị cụ thể cần do kiểm thử và SLO của hệ thống quyết định, không được lấy trực tiếp từ một tài liệu học làm production baseline.

## 13. Case study: API trả 504 rồi hệ thống sụp do retry storm

### 13.1. Bối cảnh giả định

Ứng dụng đặt hàng có reverse proxy trước ba application instances. Sau một thay đổi truy vấn DB, p99 latency tăng mạnh. Client mobile bắt đầu nhận nhiều 504 và retry liên tục; proxy cũng thử lại upstream. Tài nguyên application pool và database tiếp tục bị chiếm, dù số người dùng mới không tăng tương ứng.

### 13.2. Diễn biến từ log/metrics tổng hợp

| Mốc | Quan sát | Câu hỏi cần kiểm tra |
| --- | --- | --- |
| **T0** | RPS 500, p95 latency 200 ms, in-flight ổn định | Baseline khỏe là gì? |
| **T1** | DB query latency tăng; p99 vượt SLO | Có release, lock hoặc dependency incident nào? |
| **T2** | Proxy bắt đầu tăng `upstream_read_timeout` events | Timeout proxy do backend chậm hay route/network? |
| **T3** | Retry attempts/request tăng; tổng backend RPS vượt edge RPS | Có retry amplification không? |
| **T4** | DB pool waiters tăng, app queue bão hòa, 503/504 nhiều hơn | Backend đang cạn slot nào? |
| **T5** | Giới hạn retries, admission và DB fix được áp theo quy trình | Lỗi/latency và in-flight có trở về mức an toàn không? |

Đây là **case giả định**, không phải dữ liệu từ production. Không nên suy từ 504 rằng có DDoS đang diễn ra; cần kiểm tra **công việc chậm**, retries, lỗi upstream và lịch thay đổi.

### 13.3. Phân tích nguyên nhân theo tầng

~~~mermaid
flowchart TD
    Q["DB query chậm"] --> L["App latency tăng"]
    L --> C["In-flight requests tăng"]
    C --> P["Proxy/upstream pool bão hòa"]
    P --> T["Client nhận 503/504"]
    T --> R["Client/proxy retry tăng"]
    R --> C
    P -. "Mitigation" .-> M["Bounded queue, concurrency cap, retry budget, DB fix"]
~~~

**Containment phù hợp** có thể bao gồm: giảm retries không an toàn, bật giới hạn concurrency/queue đã kiểm thử, ngừng tính năng đắt đỏ tạm thời, sửa truy vấn DB, tăng capacity có kiểm soát và theo dõi sức khỏe user traffic.

**Hành động không đủ:** chỉ tăng `proxy_read_timeout` lên nhiều phút. Điều này có thể giảm số 504 tạm thời nhưng **giữ slot lâu hơn**, làm queue/DB pool tồi tệ hơn và khiến client đợi lâu. Trước khi tăng timeout phải chứng minh backend có thể hoàn tất công việc và capacity đáp ứng.

### 13.4. Cách chứng minh đã phục hồi

- In-flight/concurrent requests giảm về vùng capacity cho phép.
- Queue wait và DB pool waiters giảm.
- p95/p99 và error rate được cải thiện ở route chịu ảnh hưởng.
- Retry attempts/request trở lại ngưỡng được phê duyệt.
- Mã 429/503 do load shedding không tăng mất kiểm soát và người dùng hợp lệ phục hồi.
- Positive/negative tests về thao tác ghi không bị thực hiện trùng khi timeout/retry.
- Alert và owner sửa sự cố gốc đã được ghi trong incident record.

## 14. Case study: NAT chung khiến per-IP connection limit chặn nhầm

### 14.1. Bối cảnh

Một doanh nghiệp có vài trăm nhân viên truy cập ứng dụng qua cùng corporate proxy hoặc CGNAT. Reverse proxy đặt `limit_conn` theo IP nguồn với trần thấp. Khi nhiều người đồng thời họp hoặc mở dashboard, các request bị reject dù từng người sử dụng ở mức hợp lý.

### 14.2. Dấu hiệu

| Evidence | Quan sát | Ý nghĩa |
| --- | --- | --- |
| **Client IP distribution** | Nhiều người dùng cùng một public IP | Per-IP quota không tương đương per-user quota |
| **Proxy limit logs** | `limit_conn` triggered trong các giờ cao điểm | Control từ chối theo key đã chọn |
| **Identity/session logs** | Các request thuộc nhiều user/tenant đã xác thực | Không có một actor đơn lẻ chiếm toàn bộ slot |
| **Backend metrics** | Backend còn capacity tại thời điểm reject | Giới hạn có thể chặt hơn nhu cầu |
| **WAF events** | Không có bằng chứng abuse độc lập | Cần điều chỉnh rule chứ không quy kết tấn công |

### 14.3. Cách khắc phục

1. Xác định **source IP thực sự** và proxy hops đã được tin, không dùng header có thể bị client giả.
2. Chọn **quota key phù hợp**: authenticated user/tenant, route hoặc kết hợp với IP ở edge, tùy mô hình.
3. Điều chỉnh **bursts, session limits và fairness** dựa trên baseline, tránh chuyển sang unlimited.
4. Giữ **global capacity caps** để một lượng lớn users không vượt khả năng backend.
5. Kiểm thử cả **corporate NAT**, user đơn lẻ tải nặng, client mobile thay IP và traffic chưa authenticated.

Một limit policy tốt không chỉ chặn được hành vi lạm dụng mà còn **ít chặn nhầm traffic hợp lệ** khi nhiều người dùng chia sẻ địa chỉ.

## 15. Quy trình điều tra timeout và resource exhaustion

### Bước 1 — Xác định chính xác symptom

Ghi **timestamp + timezone, host/route, client group, request ID, HTTP/transport status, error message và tầng phát hiện**. Phân biệt 429 do policy, 503 do overload, 504 do upstream timeout, 499 do client đóng, TCP reset và TLS failure.

### Bước 2 — Kiểm tra health/capacity tại từng chặng

Đối chiếu **CDN/WAF → proxy → upstream → DB/dependency**. Hỏi: RPS có tăng không, hay chỉ latency tăng? Active/idle connections, queues, CPU/RAM/FD, backend pool, conntrack và ephemeral ports ra sao?

### Bước 3 — Xem các timer và retry được thiết lập

Lấy **client deadline, WAF/LB timeout, proxy connect/read/send timeout, app/DB timeout, retry policy và cancellation behavior**. Không chỉ nhìn số lớn nhất; cần biết timer đo **inactivity** hay **elapsed time** và thời điểm bắt đầu.

### Bước 4 — Chứng minh điểm nghẽn bằng evidence

Sử dụng **request ID/trace ID**, error log có `upstream` và timing, metrics của backend/DB cùng network flow. Nếu connect timeout, kiểm tra **DNS, route, firewall, TCP handshake, TLS**; nếu read timeout, kiểm tra **TTFB, ứng dụng và dependency**.

### Bước 5 — Chọn containment ít rủi ro nhất

Ưu tiên sửa lỗi gốc nếu rõ. Khi không thể sửa ngay, dùng **bounded concurrency, queue, rate policy, giảm retries, traffic shifting hoặc scale capacity** theo kế hoạch đã kiểm thử. Không mở firewall Any–Any, không tắt WAF/IDS/IPS diện rộng, không nâng tất cả timeouts lên vô hạn.

### Bước 6 — Xác minh user journey và bảo mật

Kiểm thử **API nhanh, upload, WebSocket/gRPC nếu có, user sau NAT, mobile client, VPN, health check, failover**; đối chiếu latency, error, rejected counts và backend saturation. Bảo đảm traffic hợp lệ tiếp tục đi qua điểm enforcement mong muốn.

### Bước 7 — Bảo quản chứng cứ và hậu kiểm

Lưu config revision, change ticket, source of metrics, time window, sample request IDs và giới hạn quan sát. Ghi nguyên nhân, biện pháp giảm thiểu, residual risk, owner và điều kiện rollback; không coi tạm tăng capacity là giải pháp cho một **retry storm hoặc endpoint quá đắt** chưa được sửa.

## 16. Bộ kiểm thử an toàn trước khi đưa limit vào production

Chỉ chạy benchmark/load test trên **lab, staging hoặc hạ tầng mà đội vận hành đã cấp phép**. Kiểm thử cần giới hạn **RPS/concurrency/duration**, có người theo dõi, giới hạn tác động, stop condition và rollback. Tránh thử traffic làm cạn kiệt tài nguyên trên dịch vụ công cộng hoặc mạng không thuộc quyền.

| Test | Cách kiểm chứng | Kết quả mong đợi |
| --- | --- | --- |
| **P1 – traffic bình thường** | Replay có kiểm soát mẫu request hợp lệ | Latency/SLO đạt, không bị limit sai |
| **P2 – keepalive reuse** | Client hợp lệ dùng HTTP keepalive theo workload | Idle/active sockets được xử lý đúng, không rò rỉ |
| **P3 – HTTP/2 concurrency** | Staging H2 clients với streams đồng thời có giới hạn | Policy đo đúng streams/requests, backend không quá tải |
| **P4 – API theo route** | API nhẹ và endpoint dài chạy theo budgets riêng | Không cắt endpoint hợp lệ chỉ vì cấu hình global quá ngắn |
| **N1 – concurrent cap** | Tăng concurrency trong test window được phê duyệt tới ngưỡng | Bounded/reject theo policy, không OOM/crash |
| **N2 – rate/burst** | Tạo burst kiểm soát theo test user/tenant | Limit action đúng, log có key/policy, không ảnh hưởng user khác |
| **N3 – slow client fixture** | Dùng test harness mô phỏng client gửi chậm có giới hạn | Header/body timeout giải phóng tài nguyên theo policy |
| **N4 – upstream hang** | Backend lab cố tình trì hoãn một request | Connect/read/deadline và cancellation hoạt động đúng |
| **N5 – large body** | Upload test vượt và dưới max body | 413 khi vượt, upload hợp lệ dưới ngưỡng vẫn chạy |
| **N6 – retry storm prevention** | Dựng dependency test trả lỗi có kiểm soát | Retry budget/backoff/circuit breaker không khuếch đại tải |
| **N7 – NAT fairness** | Nhiều test identities sau cùng source IP | Không chặn nhầm nhóm hợp lệ; global quota vẫn bảo vệ |
| **F1 – backend failure** | Tắt một replica trong staging theo quy trình | Load shedding/failover phù hợp, không đẩy quá capacity node còn lại |
| **F2 – slow recovery** | Cho replica trở lại, thử traffic tăng dần | Không flap, không tạo retry surge hoặc queue vô hạn |
| **P5 – streaming** | WebSocket/SSE/gRPC test trong lab | Heartbeat, idle, lifetime và cancellation đúng nhu cầu |
| **O1 – observability** | Gây một timeout và một limit event có kiểm soát | Log/metrics phân biệt đúng timeout, upstream và policy |

### 16.1. Những tiêu chí chấp nhận tối thiểu

Một rollout được xem là đạt khi:

- Trong **normal load**, p95/p99 latency và error rate không suy giảm quá SLO đã phê duyệt.
- Với **overload đã kiểm soát**, proxy từ chối sớm và không làm mất ổn định backend/DB.
- **Request rate, active connections, concurrent streams, queues và reject metrics** được quan sát độc lập.
- Logs chỉ rõ **request ID, route, upstream, timing, limit key đã được xác thực hoặc scope, policy và action**.
- Người dùng **qua NAT/VPN/CDN** không bị chặn nhầm hàng loạt.
- Các đường **WebSocket/SSE/gRPC/upload** có chính sách riêng nếu workload cần.
- **Failover và retry** không tạo amplification vượt capacity dự kiến.
- Có **runbook rollback** và owner thay đổi configuration.

## 17. Các sai lầm thường gặp

1. **“Timeout càng lớn thì hệ thống càng ổn định.”** Timeout quá dài có thể giữ sockets/workers lâu và che backend đang yếu.
2. **“Giảm timeout thật thấp sẽ tự chống mọi DDoS.”** Có thể gây false positives cho mạng di động, upload và streaming.
3. **“Read timeout 30 giây có nghĩa response không bao giờ dài hơn 30 giây.”** Nhiều proxy đo khoảng **không có bytes** giữa các lần đọc.
4. **“Giới hạn 100 TCP connections là tối đa 100 HTTP requests đồng thời.”** HTTP/2/3 multiplex nhiều streams trên một transport connection.
5. **“Connection limit và rate limit là một.”** Một cái xét concurrency/socket hoặc request đồng thời; cái kia xét tốc độ trên thời gian.
6. **“Thấy 504 là firewall chặn.”** 504 thường chỉ proxy hết thời gian chờ upstream; phải xem logs/timing.
7. **“Mọi 429 đều do WAF.”** Rate/connection limits có thể ở CDN, API gateway, proxy hoặc ứng dụng.
8. **“Status 499 là lỗi HTTP chuẩn do server trả.”** Đây là mã log phi chuẩn của NGINX khi client đóng kết nối.
9. **“Cứ tăng worker_connections là hết exhaustion.”** Có thể đụng FD, RAM, conntrack, SNAT ports hoặc DB pool.
10. **“Proxy đã trả timeout nên backend chắc chắn chưa ghi dữ liệu.”** Backend có thể vẫn xử lý; cần idempotency/reconciliation.
11. **“Retry mọi 503/504 giúp tăng reliability.”** Retry không giới hạn có thể gây storm, làm sự cố nặng thêm.
12. **“Một IP luôn là một người dùng.”** NAT/CGNAT, corporate proxy và VPN khiến nhiều người chung IP.
13. **“X-Forwarded-For luôn đáng tin.”** Client có thể tự tạo header; chỉ tin khi hạ tầng proxy chain được kiểm soát.
14. **“Upstream max_conns bằng số socket tới backend trong mọi trường hợp.”** Keepalive/worker/sharing có thể tạo khác biệt với active connection limit.
15. **“Thêm hàng đợi vô hạn bảo vệ backend.”** Queue vô hạn tiêu thụ RAM, tăng latency và chứa request đã hết deadline.
16. **“Health check xanh nghĩa API nặng vẫn đáp ứng.”** Health endpoint có thể không chạm DB hoặc workload đang quá tải.
17. **“Bật response buffering luôn tiết kiệm tài nguyên.”** Có thể tăng RAM/disk và cần quota temporary storage.
18. **“Chỉ nhìn average latency là đủ.”** p95/p99, queue wait và timeout rates phát hiện tail latency.
19. **“Một proxy có thể tự giải quyết resource exhaustion của mọi backend.”** Cần giới hạn và telemetry từ application, DB, cloud/network.
20. **“Một cấu hình thử nghiệm có thể copy lên mọi SSID, VLAN, route và dịch vụ.”** Chính sách phải theo request type, trust boundary, client behavior và SLO.

## 18. Bài tập vận dụng

### Bài 1 — In-flight concurrency thay đổi ra sao?

Hệ thống xử lý trung bình **400 requests/giây** với thời gian 0,25 giây. Sau khi DB chậm, thời gian trung bình tăng lên 2 giây trong khi tốc độ vẫn giữ được. Ước lượng in-flight trung bình?

**Gợi ý:** theo Little's Law, trước đó **400 × 0,25 = 100**, sau đó **400 × 2 = 800** in-flight requests. Số trung bình không thay thế việc kiểm thử p99 và queue burst.

### Bài 2 — Có phải read timeout là tổng request limit?

SSE endpoint gửi heartbeat mỗi 15 giây, proxy đặt upstream read inactivity timeout 30 giây. Stream chạy 10 phút. Điều này có tự động chứng minh timeout không hoạt động?

**Gợi ý:** không. Nếu timer đo khoảng giữa các reads, stream có thể sống lâu hơn 30 giây miễn không có khoảng im lặng vượt ngưỡng. Muốn giới hạn tổng thời gian phải có deadline/lifetime policy thích hợp.

### Bài 3 — Rate limit theo IP gây false positive

Hàng trăm nhân viên dùng cùng CGNAT IP và ứng dụng bị reject khi họ truy cập dashboard trong giờ làm. Cần kiểm chứng gì trước khi tăng limit?

**Gợi ý:** xem source IP trust chain, user/tenant identity, per-IP bucket usage, backend capacity, route mix, limit logs và CDN/proxy forwarding policy. Cân nhắc identity quota + global cap thay vì bỏ giới hạn.

### Bài 4 — 504 và retry không an toàn

Client POST tạo đơn hàng nhận 504 sau 30 giây. Người dùng gửi lại ngay một request y hệt. Điều gì có thể xảy ra và nên thiết kế API thế nào?

**Gợi ý:** backend có thể đã tạo đơn dù response đến trễ; retry có thể tạo hai đơn. Sử dụng **idempotency key, trạng thái giao dịch, reconciliation** và retry budget phù hợp.

### Bài 5 — Chọn control theo tài nguyên

Một reverse proxy có **FD usage cao, upstream DB pool bão hòa và disk temporary file tăng**. Hãy gắn mỗi symptom với metrics/controls cần xem.

**Gợi ý:** FD → active/idle connections, keepalive/header timeout; DB pool → application concurrency/queue/query timeout; tmp disk → buffering, max body size, quota và cleanup. Không giải quyết cả ba chỉ bằng tăng `worker_connections`.

### Bài 6 — NGINX sau CDN

NGINX đứng sau CDN và dùng `$binary_remote_addr` làm key cho `limit_conn`. Tất cả người dùng một vùng thường bị limit cùng lúc. Có nên thay bằng `$http_x_forwarded_for` do request gửi tới không?

**Gợi ý:** không tin header client tự khai. Xác minh CDN source IP/trust chain, cấu hình real IP chỉ cho proxy được phép và kiểm tra cách CDN overwrite header; nếu có thể dùng verified identity/tenant, giữ global capacity cap.

### Bài 7 — Thiết kế threat → control → evidence

Một hệ thống gồm **CDN + WAF + NGINX + 3 ứng dụng + DB**, phục vụ REST API, WebSocket và upload. Hãy lập ma trận:

- Loại request nào cần **deadline hữu hạn**, loại nào cần **idle/heartbeat policy**?
- Giới hạn **connections, HTTP/2 streams, in-flight requests, rate và queue** nằm ở lớp nào?
- Khi một backend lỗi, **failover/retry/circuit breaker** hoạt động ra sao mà không làm backend còn lại kiệt quệ?
- Làm thế nào phân biệt **429/503/504/499**, lỗi mạng, DNS, TLS và ứng dụng?
- Những **positive/negative tests** nào chứng minh traffic hợp lệ vẫn được phục vụ và hệ thống từ chối đúng khi vượt ngân sách?

**Gợi ý:** bắt đầu từ **SLO và đường đi thực của request**, đo capacity từng lớp, xác định nơi enforce và chứng cứ sau mỗi lần từ chối; tránh giới hạn không rõ đơn vị hoặc key không đáng tin.

## 19. Checklist vận hành và thiết kế

| Câu hỏi | Bằng chứng cần có |
| --- | --- |
| Đường client → proxy → upstream → dependency được vẽ đầy đủ chưa? | Diagram, ingress/egress network boundary và owner |
| Những timeout nào đang được cấu hình? | Client header/body, connect, send/read, idle, request deadline, health |
| Timer đo **inactivity** hay **total duration**? | Tài liệu/config thực tế và test có kiểm soát |
| Số connection đang đếm gì? | TCP, active requests, H2/H3 streams, upstream active/idle |
| Có global và per-identity/tenant caps không? | Config + telemetry về key/bucket/capacity |
| Đã xử lý NAT/CDN forwarding headers an toàn chưa? | Danh sách trusted proxy, real-IP policy và abuse tests |
| Backend có bounded concurrency/queue không? | Worker/DB pool metrics, reject behavior |
| Có kiểm soát retries và circuit breaker không? | Retry attempts/request, backoff, threshold và recovery logs |
| WebSocket/SSE/gRPC/upload có profile timeout riêng không? | Route config, heartbeat/lifetime/body quota tests |
| Có thể phân biệt rate reject, timeout và client abort không? | 408/413/429/499/502/503/504 logs + request/trace ID |
| Có headroom khi failover một replica/zone không? | Capacity tests và SLO khi degraded |
| Temporary disk, FD, conntrack, ephemeral ports đã được giám sát chưa? | Host/system metrics và alert thresholds |
| Timeout có làm tác vụ downstream tiếp tục chạy không? | Cancellation/idempotency tests |
| Chặn request có đúng nơi và giữ tuyến qua WAF/firewall/IDS không? | Flow, policy ID, positive/negative tests |
| Có kế hoạch rollout và rollback không? | Canary, versioned config, owner, maintenance window |
| Có cơ chế bảo vệ dữ liệu trong log không? | Log retention, access control, token/header redaction |

## 20. Tổng kết

**Timeout** giúp giới hạn thời gian một bên có thể giữ tài nguyên mà không tiến triển đúng kỳ vọng, nhưng phải phân biệt **kết nối, inactivity và deadline toàn tác vụ**. **Connection limit** chỉ hữu ích khi xác định rõ đơn vị đang giới hạn: socket, request, stream, upstream pool hay tenant. Khi backend chậm, **concurrency tăng theo thời gian giữ request**; hàng đợi, retry và buffer nếu không có ngân sách riêng có thể tạo vòng quá tải.

Trong kiến trúc **SECURITY_NETWORK_SECURITY**, phòng vệ hiệu quả là **giới hạn sớm ở edge/WAF, giới hạn chính xác tại proxy, backpressure ở ứng dụng, bảo vệ DB/OS/network resources và có observability xuyên các chặng**. Chính sách cần xét **HTTP/2/HTTP/3, TLS, NAT/CDN identity, VPN, WebSocket/SSE/gRPC, upload, failover và các trường hợp client chậm hợp lệ**. Không thể thay mọi biện pháp bằng một timeout dài hoặc một con số max connections lớn.

Một thiết kế đáng tin cậy phải chứng minh được ba kết quả: **request hợp lệ hoàn tất theo SLO; request vượt giới hạn bị từ chối theo chính sách trước khi làm hệ thống kiệt quệ; và khi lỗi xảy ra, log/metrics đủ chỉ rõ điểm nghẽn cùng hành động phục hồi có kiểm soát**.
