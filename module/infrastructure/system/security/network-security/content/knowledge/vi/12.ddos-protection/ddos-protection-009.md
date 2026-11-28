# Rate limiting và connection limit: Kiểm soát tốc độ và số kết nối trong phòng vệ DDoS

## 1. Tổng quan và mục tiêu

**Rate limiting** là cơ chế giới hạn số yêu cầu hoặc lượng lưu lượng được tiếp nhận trong một **đơn vị thời gian**. **Connection limit** là cơ chế giới hạn **số kết nối đồng thời**, thường theo nguồn, dịch vụ, vùng mạng hoặc tổng hệ thống. Hai cơ chế này liên quan nhưng không đồng nghĩa: một client có thể tạo rất nhiều HTTP request trên ít kết nối, hoặc mở nhiều kết nối mà gần như không gửi request nào.

Trong chương **DDoS** của học phần **SECURITY_NETWORK_SECURITY**, rate limiting và connection limit hỗ trợ giảm tác động của lưu lượng bất thường, bảo vệ tài nguyên kết nối và duy trì khả năng phục vụ cho người dùng hợp lệ. Chúng cần được phối hợp với phân đoạn mạng, firewall, WAF, bảo vệ DNS, IDS/IPS, xác thực kết nối, quan sát lưu lượng và hệ thống giảm thiểu DDoS tại phía nhà cung cấp mạng/cloud.

**Tình huống:** một API nhận bình thường vài trăm request mỗi giây, nhưng một đợt lưu lượng tăng đột biến khiến CPU, connection pool hoặc database bị quá tải. Giới hạn tại CDN/gateway có thể từ chối hoặc trì hoãn một phần request để giữ ứng dụng hoạt động. Tuy nhiên, nếu băng thông đường Internet **đã bão hòa trước khi traffic đến gateway**, quy tắc trên máy chủ gốc không thể tự cứu đường truyền; cần chặn hoặc hấp thụ lưu lượng ở hạ tầng upstream.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **request rate**, **new connection rate**, **concurrent connections**, **concurrent requests**, băng thông và packets per second.
2. Giải thích fixed window, sliding window, token bucket, leaky bucket và giới hạn đồng thời.
3. Chọn **khóa giới hạn (limiting key)** phù hợp với IP, tài khoản, API key, workload và môi trường NAT/proxy.
4. Đặt rate limiting và connection limit đúng điểm trong hệ thống CDN, WAF, load balancer, reverse proxy, API gateway và ứng dụng.
5. Hiểu cơ chế phản hồi 429, retry, backoff, timeout, queue và những hệ quả với người dùng hợp lệ.
6. Thiết kế kiểm thử và chỉ số vận hành để tinh chỉnh chính sách phòng vệ DDoS mà không tự gây gián đoạn dịch vụ.

## 2. Đo đúng đại lượng trước khi đặt giới hạn

| Đại lượng | Đơn vị minh họa | Đếm gì? | Dùng để xử lý vấn đề |
| --- | --- | --- | --- |
| **Request rate** | requests/second (RPS), requests/minute | Số HTTP/API request trong một khoảng thời gian | API bị gọi quá thường xuyên, bot gửi request lặp |
| **New connection rate** | connections/second (CPS) | Số kết nối mới bắt đầu mỗi giây | Bão hòa khả năng thiết lập TCP/TLS hoặc state table |
| **Concurrent connections** | kết nối đang tồn tại | Số kết nối đang mở tại cùng thời điểm | Cạn socket, file descriptor, connection tracking |
| **Concurrent requests** | request đang xử lý | Số thao tác ứng dụng chưa hoàn tất | Cạn worker, thread, DB pool, tác vụ tốn CPU |
| **Bandwidth** | bit/second (bps), byte/second | Lưu lượng dữ liệu theo thời gian | Bão hòa đường truyền hoặc chi phí truyền tải |
| **Packet rate** | packets/second (PPS) | Số gói được xử lý mỗi giây | Bão hòa thiết bị mạng/CPU xử lý gói |
| **Request body size** | byte/request | Kích thước từng request | Chặn upload/payload quá lớn; không thay rate limit |
| **Quota** | yêu cầu/ngày, byte/tháng | Tổng lượng sử dụng trong chu kỳ dài | Bảo vệ ngân sách/tài nguyên và quyền sử dụng |

**Ví dụ phân biệt:**

- Một client gửi **500 HTTP request trong một giây** qua một kết nối HTTP/2: request rate rất cao, nhưng số kết nối TCP có thể chỉ là một.
- Một client mở **300 TCP connection** rồi giữ chúng nhàn rỗi: concurrent connection cao, request rate có thể gần bằng không.
- Một request xuất báo cáo cần **20 giây** xử lý: request rate có thể thấp, nhưng nhiều request tương tự đồng thời vẫn làm cạn worker/DB pool.
- Một nguồn gửi lượng rất lớn gói nhỏ: PPS có thể là giới hạn trước cả băng thông.

Không nên áp một con số “100” rồi gọi chung là “giới hạn kết nối”. Cần ghi **100 request/giây theo API key**, **100 kết nối đồng thời theo IP**, hay **100 kết nối mới/giây trên listener**.

### 2.1. Rate, burst và concurrency không thay thế nhau

Rate limiting kiểm soát **mật độ sự kiện theo thời gian**; connection limit kiểm soát **số kết nối còn tồn tại tại một thời điểm**. Một đợt mở kết nối mới tốc độ cao có thể vượt CPS dù số kết nối đồng thời chưa nhiều, trong khi nhiều kết nối nhàn rỗi có thể vượt concurrency dù CPS thấp.

Ở lớp HTTP/2 và HTTP/3, một kết nối giao thức có thể mang nhiều stream/request đồng thời. Do đó, giới hạn TCP/QUIC connection **không phải** giới hạn số HTTP request đang chạy; phải xác định cách điểm thực thi đếm kết nối, stream và request.

## 3. Rate limiting nằm ở đâu trong phòng vệ DDoS?

Tấn công từ chối dịch vụ phân tán có thể tiêu tốn tài nguyên ở nhiều lớp:

| Nhóm tác động | Đặc điểm | Cơ chế phù hợp |
| --- | --- | --- |
| **Volumetric / L3–L4** | Băng thông hoặc PPS quá lớn, traffic đến từ nhiều nguồn | Giảm thiểu upstream, Anycast, lọc tại ISP/cloud, bảo vệ hạ tầng mạng |
| **Protocol/state exhaustion** | Tạo áp lực lên handshake, bảng trạng thái, connection tracking | SYN protection theo nền tảng, CPS/concurrency limits, timeout và capacity planning |
| **Application-layer / L7** | HTTP request dày đặc hoặc yêu cầu tốn tài nguyên | CDN/WAF/API gateway rate limit, concurrency control, cache, kiểm soát tài nguyên ứng dụng |
| **Slow connections** | Giữ kết nối lâu, gửi dữ liệu rất chậm | Header/body/read timeout, minimum data rate nếu hỗ trợ, giới hạn kết nối và worker |
| **Cost/resource exhaustion** | Gọi API/DB/file processing tiêu tốn chi phí | Quota theo danh tính, request weight, giới hạn worker và ngân sách |

**Không có một rule duy nhất chống mọi loại DDoS.** Giới hạn HTTP có thể giảm tải backend nhưng không xử lý được một đường mạng đã bị bão hòa bởi traffic không hợp lệ. Ngược lại, chặn volumetric ở upstream không tự giải quyết API hợp lệ về cú pháp nhưng tiêu tốn nhiều CPU.

### 3.1. Đặt kiểm soát trước điểm nghẽn

~~~mermaid
flowchart LR
    Client[Người dùng / nguồn traffic] --> Edge[ISP / CDN / DDoS scrubbing]
    Edge --> WAF[WAF / API Gateway]
    WAF --> LB[Load balancer]
    LB --> Proxy[Reverse proxy / Ingress]
    Proxy --> App[Application]
    App --> DB[(Database / phụ thuộc)]
    WAF -. RPS / bot policy .-> WAF
    Proxy -. Conn / timeout .-> Proxy
    App -. In-flight / quota .-> App
~~~

Sơ đồ là mô hình các **chức năng**; thực tế CDN và WAF có thể nằm cùng dịch vụ, hoặc proxy nằm trước load balancer tùy kiến trúc.

Một thiết kế tốt đặt giới hạn:

1. **Upstream:** hấp thụ hoặc loại lưu lượng trước khi nghẽn đường mạng.
2. **WAF/API gateway:** kiểm soát request theo IP, danh tính, route, bot signal hay điểm số rủi ro khi có khả năng.
3. **Reverse proxy/ingress:** giới hạn request, kết nối và timeout trước khi tới backend.
4. **Application/worker:** kiểm soát số tác vụ đồng thời, chi phí xử lý, DB pool và quota nghiệp vụ.
5. **Database/dịch vụ phụ thuộc:** xác thực, giới hạn tài nguyên và các cơ chế tự bảo vệ phù hợp.

**Kiểm tra đường bypass:** nếu origin vẫn có thể truy cập trực tiếp, lưu lượng đi qua đường khác có thể không chịu CDN/WAF policy. Cần kiểm soát truy cập origin qua firewall/security group, kết nối riêng, xác thực phía trước hoặc các cơ chế được hệ thống hỗ trợ.

## 4. Các thuật toán rate limiting phổ biến

### 4.1. Fixed window counter

Đếm số request trong từng cửa sổ thời gian cố định, ví dụ mỗi phút. Khi số request vượt ngưỡng, từ chối hoặc làm chậm.

**Ví dụ:** cho phép 100 request/phút theo client. Một nguồn gửi gần 100 request ở cuối phút và 100 request ngay đầu phút sau có thể tạo **burst gần 200 request trong thời gian ngắn**, dù mỗi cửa sổ riêng lẻ hợp lệ.

**Ưu điểm:** dễ triển khai, dễ tính toán. **Nhược điểm:** hiệu ứng ranh giới cửa sổ (*boundary burst*). Không phù hợp nếu backend không chịu được burst đột ngột.

### 4.2. Sliding window log/counter

Sliding window đánh giá lượng request trong khoảng thời gian vừa trôi qua, thay vì reset hoàn toàn theo mốc thời gian cố định.

- **Sliding log:** giữ timestamp của các request trong cửa sổ; có thể chính xác nhưng tốn bộ nhớ khi có nhiều key và request.
- **Sliding counter xấp xỉ:** kết hợp số đếm của các khoảng thời gian nhỏ hoặc cửa sổ kề nhau; tiết kiệm tài nguyên hơn nhưng có sai số so với log chính xác.

**Ưu điểm:** giảm khả năng burst lớn ở ranh giới. **Nhược điểm:** phức tạp hơn trong quản lý trạng thái phân tán, đồng hồ và số lượng key.

### 4.3. Token bucket

Hình dung mỗi client có một “xô token”:

- Xô có dung lượng tối đa **B token**.
- Token được bổ sung với tốc độ **r token/giây**, không vượt quá dung lượng B.
- Mỗi request thường tốn một token; request được chấp nhận nếu đủ token.
- Khi không đủ token, hệ thống có thể từ chối, trì hoãn hoặc xếp hàng tùy policy.

**Ví dụ định lượng:** r = 5 token/giây, B = 10 token, một request tốn 1 token. Nếu xô đang đầy, 12 request đến **cùng một thời điểm** thì tối đa 10 request được chấp nhận ngay, 2 request bị giới hạn nếu chính sách không cho chờ. Sau 3 giây không có yêu cầu, xô có thể đầy lại tối đa 10 token, **không tích lũy vô hạn thành 15 token**.

Token bucket thích hợp cho dịch vụ có **tốc độ trung bình ổn định nhưng chấp nhận burst ngắn**. Nếu mỗi thao tác có chi phí khác nhau, mô hình có thể tính nhiều token cho request tốn tài nguyên, miễn là cách tính được bảo vệ khỏi khai báo chi phí không đáng tin từ client.

~~~text
capacity = 10 tokens
refill_rate = 5 tokens/second
cost_per_request = 1 token

on_request(now):
    elapsed = max(0, now - last_update)
    tokens = min(capacity, tokens + elapsed * refill_rate)
    last_update = now

    if tokens >= cost_per_request:
        tokens = tokens - cost_per_request
        ALLOW
    else:
        RATE_LIMIT
~~~

Đây là **giả mã**, không phải một triển khai thread-safe hoặc dùng được trực tiếp trong production. Nếu nhiều worker cùng sửa bộ đếm, việc đọc/trừ token cần atomicity và đồng bộ phù hợp.

### 4.4. Leaky bucket / paced processing

Leaky bucket nhấn mạnh làm **mượt tốc độ xử lý/đầu ra**, thường qua hàng đợi hoặc cơ chế pacing. Request đến nhanh có thể được giữ tạm và xử lý ở tốc độ được kiểm soát, cho đến khi hàng đợi đầy hoặc hết thời gian chờ.

**Ưu điểm:** hạn chế burst truyền tới backend. **Nhược điểm:** thêm latency và có thể giữ bộ nhớ/connection nếu hàng đợi lớn. Khi tải liên tục vượt công suất, xếp hàng mãi không làm hệ thống ổn định hơn; cần **backpressure** và từ chối sớm.

Các sản phẩm có thể dùng tên “leaky bucket”, “token bucket”, “burst” theo chi tiết triển khai khác nhau. Không suy ra semantics chính xác chỉ từ tên thuật toán; hãy đọc tài liệu nền tảng và kiểm thử ở ranh giới.

### 4.5. Sliding window và token bucket chọn thế nào?

| Phương pháp | Điều nó kiểm soát tốt | Điểm cần cân nhắc |
| --- | --- | --- |
| Fixed window | Tổng request mỗi khoảng cố định | Burst ở ranh giới cửa sổ |
| Sliding window | Số request trong khoảng di chuyển | Chi phí lưu trạng thái / độ xấp xỉ |
| Token bucket | Tốc độ trung bình và burst có kiểm soát | Chọn rate, capacity và cost/token |
| Leaky bucket/pacing | Làm mượt tốc độ chuyển tiếp đến backend | Hàng đợi, latency và tình trạng quá tải kéo dài |
| Concurrency semaphore | Số tác vụ đang xử lý | Không giới hạn tốc độ tạo request trong thời gian dài |

Có thể kết hợp các cơ chế, nhưng cần tránh **quá nhiều tầng cùng giới hạn một luồng mà không có dữ liệu quan sát**. Chẳng hạn CDN 100 RPS, gateway 50 RPS, app 30 RPS có thể khiến kết quả thực tế khác dự kiến và khó xác định lớp chặn.

## 5. Connection limit: Những kiểu giới hạn không nên nhầm lẫn

### 5.1. Số kết nối đang mở

**Concurrent connection limit** giới hạn số TCP/QUIC connection đang tồn tại tại thời điểm kiểm tra. Có thể gắn vào:

- Một IP nguồn hoặc nhóm nguồn.
- Một virtual host, listener hoặc dịch vụ.
- Một ứng dụng/upstream backend.
- Toàn hệ thống hoặc nhóm tài nguyên.

Nó giúp tránh một nguồn chiếm quá nhiều socket, file descriptor hoặc trạng thái kết nối. Tuy nhiên, một kết nối hợp lệ có thể xử lý nhiều request nối tiếp; chỉ giới hạn số connection không kiểm soát được số request trên đó.

### 5.2. Connection establishment rate

**CPS limit** kiểm soát số kết nối **mới được khởi tạo mỗi giây**. Đây là cơ chế khác với concurrent connection limit:

| Tình huống | Concurrent connections | New connection rate |
| --- | --- | --- |
| 100 kết nối tồn tại lâu | Cao | Có thể thấp sau khi đã mở |
| 1.000 kết nối ngắn đến rồi đóng nhanh | Có thể không cao tại mỗi thời điểm | Có thể rất cao |
| Client dùng HTTP keep-alive | Ít kết nối tồn tại lâu | Thường ít handshake hơn |
| Client gửi nhiều request qua HTTP/2 | Ít connection TCP/QUIC | Request rate và stream concurrency vẫn có thể cao |

CPS limit có thể được thực thi ở load balancer, firewall hoặc hệ điều hành tùy khả năng. Không phải directive tên “connection limit” nào cũng đo CPS.

### 5.3. Connection concurrency so với request concurrency

**Concurrent requests** giới hạn số HTTP request hoặc tác vụ ứng dụng đang chạy. Với HTTP/1.1 keep-alive, một TCP connection có thể phục vụ nhiều request theo thời gian; với HTTP/2 và HTTP/3, nhiều stream/request có thể đồng thời trên một connection. Trong kiến trúc asynchronous, một request có thể giữ ít thread nhưng vẫn chiếm DB connection hoặc tài nguyên khác.

**Ví dụ công suất:** một API nhận ổn định 40 request/giây và thời gian xử lý trung bình 0,25 giây. Trong điều kiện ổn định, số request đang xử lý trung bình xấp xỉ:

~~~text
L = λ × W
L = 40 requests/second × 0,25 second
L ≈ 10 requests đang xử lý trung bình
~~~

Đây là cách dùng **định luật Little** cho hệ thống ổn định, không phải mức concurrent tối đa. Nếu thời gian xử lý tăng lên 2 giây trong khi lưu lượng vẫn 40 RPS, số request đang xử lý trung bình có thể tăng lên khoảng **80**. Tắc nghẽn có thể tự khuếch đại khi hàng đợi kéo dài.

Do đó cần song song:

1. Rate limit để kiểm soát lượng request mới.
2. Concurrency limit để bảo vệ số tác vụ đang chạy.
3. Timeout và giới hạn queue để từ chối sớm khi dịch vụ không đáp ứng được.
4. Backpressure tới client/upstream và cache cho những request có thể phục vụ từ bộ nhớ đệm.

### 5.4. Slow connections, keep-alive và timeout

Một kết nối không gửi đủ header/body trong thời gian dài có thể giữ tài nguyên mà không tạo nhiều request hoàn chỉnh. Ngoài connection limit, nên xem:

- Thời gian tối đa để nhận header và body.
- Idle/keep-alive timeout.
- Thời gian bắt tay TCP/TLS theo khả năng từng điểm chặn.
- Giới hạn request body, streaming và tốc độ dữ liệu tối thiểu nếu sản phẩm hỗ trợ.
- Hàng đợi và số kết nối tới backend.

Không chọn timeout quá ngắn một cách tùy tiện: mạng di động, kết nối xa, người dùng chậm và upload hợp lệ có thể bị ảnh hưởng. Mỗi loại endpoint cần mức thời gian thích hợp.

### 5.5. Lưu ý tầng TCP, TLS, HTTP/2 và HTTP/3

- **TCP SYN backlog** và **connection tracking** là các tài nguyên khác nhau. Một limit ở tầng HTTP thường chỉ có tác dụng sau khi thiết lập kết nối và có thể không ngăn đầy các bảng ở lớp thấp hơn.
- **SYN cookies**, lọc SYN và các biện pháp kernel/network khác cần được cấu hình theo kiến trúc; không thay thế rate limit HTTP.
- **TLS handshake** tiêu thụ tài nguyên riêng. Có thể cần bảo vệ kết nối mới và tối ưu TLS/session reuse, nhưng phải giữ cấu hình mật mã an toàn.
- **HTTP/2 multiplexing** và **HTTP/3 trên QUIC** khiến quan hệ “một kết nối = một request” không còn đúng.
- Một số triển khai có thể đếm **request đồng thời của HTTP/2/3 như kết nối riêng trong module limit cụ thể**. Cần kiểm tra tài liệu của sản phẩm, không diễn giải tên rule theo số socket TCP quan sát được.

## 6. Chọn limiting key cho đúng đối tượng

**Limiting key** là định danh để gắn bộ đếm/hạn mức, ví dụ IP nguồn, tài khoản, token API, tenant, hostname, route hoặc kết hợp nhiều chiều.

| Khóa | Ưu điểm | Rủi ro / điểm mù |
| --- | --- | --- |
| IP nguồn tại điểm thực thi | Có sẵn trước khi xác thực; hữu ích với traffic chưa rõ danh tính | NAT/CGNAT gom nhiều người; botnet dùng nhiều IP; IPv6 thay đổi |
| API key đã xác thực | Theo client ứng dụng, tương đối ổn định | Khóa bị lộ hoặc một client có nhiều khóa; cần bảo vệ và thu hồi |
| Account/user ID đã xác thực | Hạn mức theo người dùng/chi phí | Cần chống brute force trước đăng nhập; tài khoản dùng chung |
| Tenant/customer ID | Phân phối công suất giữa khách hàng | Một tenant có thể có nhiều user hoặc workload |
| Endpoint/route | Bảo vệ thao tác nặng hơn thao tác nhẹ | Client có thể chuyển sang route khác; cần global limit bổ sung |
| IP + route hoặc account + route | Hạn chế theo đúng ngữ cảnh API | Số lượng key lớn làm tăng chi phí bộ đếm |
| Toàn dịch vụ | Bảo vệ công suất tổng thể | Không công bằng nếu nguồn xấu chiếm toàn bộ ngân sách |

### 6.1. NAT, CGNAT và mạng doanh nghiệp

Nhiều người có thể đi ra Internet qua **cùng một IP công cộng**. Nếu giới hạn cứng theo IP quá thấp, một văn phòng hoặc mạng di động có thể bị chặn hàng loạt dù mỗi người chỉ gửi ít request.

Một thiết kế thường dùng nhiều cấp: giới hạn rộng ở IP chưa xác thực; sau khi xác thực, bổ sung hạn mức theo user/tenant/API key; kiểm soát tổng công suất theo route và backend. Không dùng tài khoản làm khóa duy nhất cho endpoint đăng nhập khi chưa xác minh được người dùng.

### 6.2. IP thực sau CDN/reverse proxy

Tại origin, IP TCP peer có thể là **địa chỉ CDN, ingress hoặc proxy**, không phải người dùng ban đầu. Nếu giới hạn theo IP peer ở vị trí này mà không hiểu topology, tất cả traffic có thể dùng chung một bucket và gây chặn nhầm diện rộng.

HTTP header như **X-Forwarded-For** chỉ đáng tin khi được **proxy tin cậy tạo hoặc chuẩn hóa**. Client Internet có thể tự gửi header giả nếu origin tin trực tiếp vào giá trị do bên ngoài cung cấp.

**Quy trình an toàn:**

1. Xác định danh sách proxy/load balancer đáng tin cậy và nguồn kết nối được phép.
2. Chỉ tiếp nhận/tham chiếu chuỗi thông tin client IP theo quy tắc tin cậy cụ thể của nền tảng.
3. Chặn đường gọi trực tiếp origin nếu kiến trúc yêu cầu mọi request qua edge.
4. Thử truy cập qua edge và đường không hợp lệ để xác nhận bộ đếm áp dụng đúng đối tượng.
5. Ghi rõ **client identity, observed peer IP và limiting key** trong telemetry khi không chứa dữ liệu nhạy cảm.

### 6.3. IPv6 và lượng IP phân tán

Một nguồn có thể sử dụng nhiều địa chỉ IPv6. Limiting theo **từng địa chỉ /128** có thể kém hiệu quả nếu địa chỉ thay đổi liên tục. Có thể cân nhắc prefix grouping theo chính sách, nhưng không mặc định gom mọi địa chỉ thành /64: độ dài prefix được cấp thực tế khác nhau và dễ ảnh hưởng người dùng khác nhau. Ưu tiên kết hợp các tín hiệu danh tính đã xác thực, hành vi và nhóm tài nguyên được kiểm soát.

### 6.4. Botnet phân tán

Hàng nghìn IP mỗi IP gửi lượng request nhỏ có thể khiến **per-IP rate limit** gần như không tác dụng, dù tổng tải ứng dụng lớn. Cần bổ sung giới hạn tổng/tenant, bot management, đánh giá hành vi, kiểm soát các API tốn tài nguyên, caching và khả năng giảm thiểu upstream.

**Không dựa hoàn toàn vào CAPTCHA, IP reputation hay ASN** như một tiêu chuẩn chặn tuyệt đối. Chúng có thể gây false positive và bị thay đổi theo thời gian; mức kiểm soát cần phản ánh rủi ro và ảnh hưởng tới người dùng.

## 7. Ví dụ cấu hình Nginx trong môi trường lab

Nginx có các module thường dùng:

- **ngx_http_limit_req_module:** giới hạn tốc độ xử lý HTTP request theo khóa và vùng trạng thái; có cơ chế burst.
- **ngx_http_limit_conn_module:** giới hạn số kết nối theo khóa trong các điều kiện mà module áp dụng.

Đoạn sau **minh họa**, giả định một máy lab có upstream API tại 127.0.0.1:8080 và Nginx lắng nghe 127.0.0.1:8088. Nó **không** phải cấu hình production đầy đủ, chưa có TLS, authentication, logging chính thức và chiến lược tin cậy IP sau proxy.

~~~nginx
http {
    # Bộ đếm request theo IP peer; vùng trạng thái dùng chung
    # giữa các worker của chính instance Nginx này.
    limit_req_zone $binary_remote_addr zone=api_rps:10m rate=10r/s;

    # Bộ đếm số kết nối theo cùng khóa IP peer.
    limit_conn_zone $binary_remote_addr zone=api_conn:10m;

    upstream api_backend {
        server 127.0.0.1:8080;
    }

    server {
        listen 127.0.0.1:8088;
        server_name app.lab.test;

        location /api/ {
            limit_req zone=api_rps burst=20 nodelay;
            limit_conn api_conn 20;

            # Trả mã rõ ràng khi vượt limit ở lớp HTTP.
            limit_req_status 429;
            limit_conn_status 429;

            proxy_pass http://api_backend;
        }
    }
}
~~~

**Giải thích quan trọng:**

1. **rate=10r/s** là tốc độ trung bình cho mỗi khóa mà module sử dụng; không có nghĩa “cứ mỗi giây đồng hồ được 10 request rồi reset”.
2. **burst=20** cho phép xử lý một mức dồn request ngắn theo cơ chế mà module định nghĩa. **nodelay** tránh trì hoãn những request trong ngưỡng burst được chấp nhận; không có nghĩa traffic không bị giới hạn.
3. **limit_conn api_conn 20** kiểm soát lượng kết nối theo cách module **limit_conn** đếm ở điểm xử lý HTTP; **không phải** chỉ số CPS hay giới hạn TCP SYN.
4. **limit_req_status / limit_conn_status 429** đặt mã phản hồi khi module từ chối. Khi không cấu hình các directive này, sản phẩm/phiên bản có thể dùng mã mặc định khác, ví dụ 503.
5. **$binary_remote_addr** lấy địa chỉ IP peer theo cấu hình Nginx. Nếu phía trước là proxy, cần cấu hình cơ chế nhận diện địa chỉ nguồn đáng tin cậy trước khi dùng làm khóa.
6. Bộ đếm trong **zone dùng chung giữa các worker của cùng instance**, nhưng **không tự đồng bộ giữa nhiều máy Nginx độc lập**. Nếu load balancer phân phối tới nhiều instance, hiệu lực tổng có thể khác mức kỳ vọng nếu không có điểm giới hạn tập trung.
7. Các module HTTP chỉ áp dụng tại giai đoạn xử lý HTTP phù hợp; với traffic bị chặn sớm ở network/TLS layer, cơ chế này không thay thế firewall hoặc công cụ chống DDoS upstream.

**Chú ý về HTTP/2 và HTTP/3:** tài liệu Nginx mô tả các request đồng thời của HTTP/2/3 được xem như các “connection” riêng đối với limit_conn. Đây là **semantics của module**, không nên suy ra số socket TCP/QUIC vật lý bằng số đếm đó.

### 7.1. Cẩn trọng khi đổi chính sách

Không copy mẫu này vào server đang hoạt động mà chưa xác định **đường truy cập thật**, các location, biến khóa và năng lực backend. Một rule theo IP peer sai có thể gộp mọi request đến từ CDN vào một bucket và làm website gián đoạn.

Trên máy lab đã cấu hình Nginx, có thể kiểm tra cú pháp:

~~~bash
# Đọc/kiểm tra cấu hình Nginx của môi trường lab.
nginx -t

# Kiểm tra một request hợp lệ tới endpoint được phép thử.
curl -i --max-time 5 \
  -H 'Host: app.lab.test' \
  http://127.0.0.1:8088/api/health
~~~

Kiểm tra cú pháp thành công **không chứng minh** limit đã có hiệu lực; phải thực hiện thêm kiểm thử request từ nguồn và lưu lượng phù hợp, quan sát HTTP status và log của Nginx.

### 7.2. Chế độ quan sát trước khi chặn

Một số phiên bản Nginx hỗ trợ **limit_req_dry_run** và **limit_conn_dry_run** để ghi nhận điều kiện vượt ngưỡng mà không áp dụng từ chối theo limit đó. Khi dùng phải kiểm tra phiên bản và chính sách hiệu lực, vì những lớp khác vẫn có thể chặn traffic.

Đây là hướng kiểm thử hữu ích trước khi chuyển từ monitoring sang enforcement. Chỉ số vượt limit trong chế độ quan sát cần đối chiếu với nhóm client và chức năng nghiệp vụ; không thể coi toàn bộ lượt vượt là tấn công.

## 8. Phản hồi cho client khi vượt giới hạn

### 8.1. HTTP 429 Too Many Requests

**429 Too Many Requests** (RFC 6585) thể hiện client đã gửi quá nhiều request trong một khoảng thời gian theo chính sách server. Phản hồi có thể kèm **Retry-After** để hướng dẫn khi nào thử lại, nếu server có thể xác định thời điểm phù hợp.

~~~http
HTTP/1.1 429 Too Many Requests
Content-Type: application/json
Retry-After: 30

{"error":"rate_limit_exceeded","retry_after_seconds":30}
~~~

Đây là **phản hồi minh họa**. Retry-After có thể là số giây hoặc ngày giờ HTTP theo ngữ nghĩa giao thức. Không phải mọi hệ thống 429 đều gửi header này; không tự đặt Retry-After cố định 30 giây nếu backend không có cơ sở.

### 8.2. 429, 503, drop và timeout khác nhau

| Hành động | Khi nào thường được dùng | Điều cần lưu ý |
| --- | --- | --- |
| HTTP **429** | Client vượt quota/tốc độ áp dụng cho yêu cầu | Hữu ích cho client API; cần chính sách retry/backoff |
| HTTP **503** | Dịch vụ tạm thời không sẵn sàng/quá tải | Có thể kèm Retry-After khi phù hợp, không đồng nghĩa per-client rate limit |
| HTTP **403** hoặc challenge | Quy tắc WAF/bot policy không cho phép request | Không diễn giải tất cả 403 là rate limit |
| TCP drop/reset | Lớp network/IPS từ chối kết nối | Client có thể chỉ thấy lỗi hoặc timeout, không nhận HTTP status |
| Queue/delay | Hệ thống còn ngân sách đợi xử lý | Latency tăng; cần giới hạn chiều dài queue và thời gian chờ |

Ở lớp hạ tầng, nếu client không thể thiết lập kết nối đến HTTP server, nó sẽ **không nhận được 429**. Việc chọn phản hồi phải xét khả năng hệ thống còn xử lý được response hay không.

### 8.3. Retry và thundering herd

Client nên dùng **exponential backoff có jitter** và tôn trọng Retry-After khi có, thay vì mọi client đồng loạt thử lại ngay. Retry không giới hạn có thể làm quá tải trầm trọng thêm.

Ví dụ một chiến lược hợp lệ: số lần retry tối đa hữu hạn, tăng thời gian đợi theo số lần lỗi, thêm ngẫu nhiên và chỉ retry khi thao tác được thiết kế an toàn. Với API có side effect, cần hiểu **idempotency** và khả năng server đã xử lý request trước khi client nhận lỗi.

## 9. Chọn chính sách theo endpoint và mức chi phí

**Không nên có một ngưỡng giống nhau cho toàn bộ ứng dụng.** Route đọc cache, upload file, login, xuất báo cáo và API tính toán nặng có tải CPU/I/O khác nhau.

| Nhóm endpoint | Mục tiêu bảo vệ | Chính sách gợi ý về mặt thiết kế |
| --- | --- | --- |
| Trang tĩnh/cacheable | Giảm request tới origin | Cache/CDN; rate limit rộng ở edge, ưu tiên người dùng hợp lệ |
| API đọc dữ liệu nhẹ | Tránh gọi quá thường xuyên | Per client/tenant + giới hạn tổng/backend |
| API tạo đơn hàng/thanh toán | Tránh quá tải và gửi lại trùng | Rate limit theo danh tính; idempotency key và kiểm soát giao dịch |
| Login/đặt lại mật khẩu | Chống đoán mật khẩu và spam | Per account + IP/device; xác thực đa yếu tố và phát hiện hành vi |
| Tìm kiếm/phân tích | Bảo vệ truy vấn tốn CPU/DB | Concurrency limit, cost-based quota, timeout |
| Upload/processing | Bảo vệ băng thông, storage và workers | Body size, quota, số tác vụ đồng thời, scanning |
| Webhook từ đối tác | Tránh mất sự kiện hợp lệ khi burst | Hợp đồng rate, queue bền vững, xác thực chữ ký và replay protection |
| Health checks | Duy trì quan sát hệ thống | Đặt policy riêng cho probe đáng tin cậy, tránh bị bot lạm dụng |

### 9.1. Hạn mức nhiều cấp

Một dịch vụ có thể đồng thời áp dụng:

- **Per-IP:** giảm spam trước xác thực.
- **Per-account/API key:** tránh một client sử dụng quá mức.
- **Per-tenant:** phân bổ công bằng giữa các khách hàng.
- **Per-route:** bảo vệ thao tác nặng.
- **Global/cluster:** bảo vệ công suất chung khi traffic phân tán vượt tổng khả năng.
- **Concurrency:** tránh DB/worker pool bị lấp đầy dù request rate nhìn có vẻ chấp nhận được.

Cần định nghĩa **thứ tự, phạm vi và hành vi khi mỗi cấp từ chối**, tránh một ngưỡng global quá thấp làm tất cả tenant cùng bị ảnh hưởng.

### 9.2. Giới hạn theo chi phí xử lý

Một endpoint thực hiện tác vụ tốn CPU/DB có thể cần hạn mức **trọng số** cao hơn request đọc cache. Ví dụ một thao tác xuất báo cáo tiêu thụ 20 đơn vị ngân sách, còn thao tác đọc metadata là 1 đơn vị. Đây là chiến lược định lượng ứng dụng, không phải cách tính mặc định của HTTP hoặc Nginx.

Phần ước lượng chi phí cần dựa vào đo đạc thực tế và **không tin chỉ số chi phí do client tự khai** khi thiếu xác thực/kiểm tra.

## 10. Thiết kế trong hệ thống phân tán

### 10.1. Local limit và global limit

Giả sử có bốn instance API, mỗi instance giới hạn **100 RPS theo client** bằng bộ đếm cục bộ. Nếu lưu lượng client được phân phối đều, tổng khả năng tiếp nhận có thể gần **400 RPS** trước khi từng instance chạm mức cục bộ. Vì vậy **100 RPS tại một node không đồng nghĩa 100 RPS toàn cụm**.

Giải pháp có thể là:

1. Thực thi hạn mức tại **một gateway/edge chung**.
2. Dùng bộ đếm phân tán có thao tác atomic khi cần global quota.
3. Phân chia ngân sách giữa các node, có cơ chế hiệu chỉnh khi autoscaling.
4. Dùng rate limit xấp xỉ kết hợp với bảo vệ concurrency/backend khi yêu cầu độ sẵn sàng cao.

Mỗi phương pháp có trade-off về độ trễ, độ chính xác, tính sẵn sàng và chi phí. Không nên dùng một kho trạng thái từ xa cho mọi packet ở lớp mạng nếu điều đó khiến hệ thống giới hạn chính nó thành nút nghẽn.

### 10.2. Đồng bộ thời gian, atomicity và fail policy

Trong một bộ đếm phân tán:

- Đồng hồ giữa các node có thể lệch; sliding window dựa trên timestamp cần chính sách thời gian nhất quán.
- Tăng bộ đếm và kiểm tra ngưỡng phải có tính nguyên tử phù hợp để tránh nhiều worker cùng chấp nhận quá mức.
- TTL của key và thu hồi trạng thái cần tránh rò rỉ bộ nhớ khi có rất nhiều IP/account khác nhau.
- Khi hệ thống lưu bộ đếm lỗi, cần xác định **fail-open** hay **fail-closed** theo mức rủi ro. Fail-open bảo vệ tính sẵn sàng nhưng bỏ kiểm soát; fail-closed giữ chính sách nhưng có thể ngắt traffic hợp lệ.
- Có thể dùng các cấp giới hạn dự phòng, nhưng cần biết khi nào quy tắc chuyển từ “exact global” sang “best-effort local”.

### 10.3. Tránh thêm một điểm nghẽn

Nếu mọi request phải gọi một kho dữ liệu quota tập trung chậm, **rate limiter** có thể trở thành điểm yếu về latency hoặc availability. Đo cả p95/p99 thời gian kiểm tra limit, lỗi backend của limiter, số key đồng thời, lượng bộ nhớ và hành vi khi hệ thống điều khiển không sẵn sàng.

## 11. Kiểm thử trong phòng lab được phê duyệt

Không thực hiện stress test quy mô lớn lên dịch vụ bên ngoài phạm vi. Với chức năng rate limiting, các phép thử **nhỏ, có kiểm soát ngay quanh ngưỡng** đã đủ để kiểm tra nhiều lỗi logic. Test công suất/DDoS chuyên sâu cần kế hoạch tải, ranh giới, giám sát và phê duyệt riêng.

### 11.1. Ma trận kiểm thử

| Kịch bản | Cách thử | Kỳ vọng |
| --- | --- | --- |
| Dưới ngưỡng RPS | Gửi ít request hợp lệ theo khoảng thời gian | Không bị chặn bởi rate limit |
| Burst ngay trên dung lượng được phép | Phát lượng nhỏ request giả lập quanh ngưỡng | Chặn/delay đúng theo thuật toán |
| Qua ranh giới phút | Thử fixed/sliding window ở mốc thời gian | Không có burst ngoài thiết kế |
| Đủ và vượt concurrent connections | Mở số kết nối lab đã được phê duyệt | Phản ứng đúng kiểu limit, không ngắt toàn dịch vụ |
| Ít kết nối, nhiều HTTP/2 requests | Gửi request đồng thời trên cùng connection | Kiểm chứng request limit và stream semantics |
| Nhiều request nhỏ, xử lý chậm | Đo concurrent requests và backend pool | Có backpressure/timeout phù hợp |
| Hai user sau cùng một NAT | So sánh khóa IP với danh tính user | Không chặn nhầm nhóm người hợp lệ quá mức |
| Nhiều IP với tổng tải lớn | Bộ dữ liệu mô phỏng theo kế hoạch | Global/backend limit bảo vệ tổng công suất |
| Qua CDN và gọi origin trực tiếp | Chỉ với đường origin lab được phép thử | Không bypass được policy theo thiết kế |
| 429 và retry | Kiểm tra response, header, giới hạn retry | Không tạo retry storm |
| Một instance bị lỗi | Lab failover/fail policy theo kế hoạch | Hành vi được dự đoán và phục hồi được |
| Đủ IPv4 và IPv6 | Thử hai họ địa chỉ trong lab | Không có khoảng trống quản lý key |

### 11.2. Dữ liệu thử không gây quá tải

Với lab có ngưỡng thấp như **3 request trong một cửa sổ thử**, có thể gửi vài request thủ công hoặc bằng bộ test harness do nhóm vận hành kiểm soát, rồi đối chiếu lần nào được chấp nhận/từ chối. Không cần tạo hàng nghìn kết nối để xác nhận xử lý 429.

~~~bash
# Một request bình thường đến endpoint lab đã được phê duyệt.
curl -i --max-time 5 https://app.lab.test/api/health

# Quan sát riêng các header trả về khi có rate limit.
# Hệ thống có thể hoặc không có Retry-After/RateLimit headers.
curl -sS -D - -o /dev/null --max-time 5 \
  https://app.lab.test/api/health
~~~

Các lệnh trên **không tự tạo tải DDoS** và không chứng minh limiter đã hoạt động. Để xác nhận, cần bộ thử có số lượng request, khoảng thời gian và nguồn xác định rõ, cùng log ở điểm thực thi và nguồn đo độc lập.

### 11.3. Kiểm thử token bucket bằng suy luận

Cho bucket có:

~~~text
capacity = 6 tokens
refill_rate = 2 tokens/s
cost = 1 token/request
state at t=0: 6 tokens
~~~

Nếu có 8 request cùng lúc tại **t = 0** và không có hàng đợi, 6 request có thể được cho phép, 2 request bị giới hạn. Nếu sau đó không có request, tại **t = 2 giây**, bucket hồi tối đa 4 token. Bốn request ngay lúc đó có thể được phép; request thứ năm sẽ bị giới hạn. Đây chỉ là mô hình token bucket lý tưởng; sản phẩm thực có thể có cách tính burst/độ phân giải thời gian khác.

### 11.4. Kiểm tra theo đúng nguồn

Một rate limiter tại origin nhìn thấy **peer IP của CDN** có thể dùng sai khóa nếu chưa được cấu hình nhận diện nguồn tin cậy. Hãy thử từ hai user lab đi qua CDN và từ một đường kiểm thử đặc biệt chỉ dành cho quản trị, đối chiếu các event để xác định **limiting key thực sự**. Không tạo ngoại lệ bỏ qua WAF hoặc công khai origin cho người ngoài chỉ để kiểm thử.

## 12. Giám sát và điều tra sự cố

### 12.1. Những metric nên có

| Nhóm | Metric cần quan sát | Câu hỏi trả lời |
| --- | --- | --- |
| Traffic | RPS, PPS, bps, CPS, request theo route | Tải tăng ở lớp nào? |
| Concurrency | Active TCP/QUIC connections, in-flight requests, queue depth | Tài nguyên nào gần cạn? |
| Limiter | Allowed, rejected, delayed, dry-run exceeds, counter errors | Chính sách đang làm gì? |
| HTTP | 429, 503, 403, retry rate và latency | Client có gặp lỗi/nhầm lẫn không? |
| Resource | CPU, RAM, FD/socket, DB pool, cache hit ratio | Có bảo vệ được backend không? |
| Network | Packet drops, retransmits, link utilization, conntrack pressure | Nghẽn xảy ra trước hay sau limiter? |
| Business | Tỷ lệ giao dịch thành công, upload success, login success | Người dùng hợp lệ còn sử dụng được không? |
| Security | WAF/IDS alerts, bot score, nguồn, vùng, route | Lưu lượng bất thường có thể phân loại được không? |

Giữ lại **thời gian, route, hành động, ngưỡng, khóa đã được ẩn danh khi cần, nguồn quan sát và request/correlation ID** để đối chiếu giữa CDN, WAF, proxy và ứng dụng. Không ghi plaintext API key, mật khẩu, Authorization hoặc cookie phiên vào log.

Ví dụ bản ghi **giả lập**:

~~~text
timestamp=2026-11-28T10:00:00Z
service=api-lab
layer=edge-waf
route=/api/search
limit_type=request_rate
limit_key=tenant:lab-42
configured_rate=10rps
action=REJECT
http_status=429
request_id=req-lab-0042
~~~

Log này cho biết một yêu cầu đã bị từ chối bởi chính sách giới hạn, **không tự chứng minh là tấn công**. Một client hợp lệ có thể vượt quota do lỗi retry, tích hợp batch hoặc thay đổi tải. Cần xem bối cảnh, lịch thay đổi và xu hướng trong một khoảng thời gian.

### 12.2. Khi người dùng hợp lệ liên tục gặp 429

Kiểm tra tuần tự:

1. Request đến qua CDN/WAF hay origin; bộ đếm thực thi tại lớp nào?
2. Limiting key có đúng người dùng/tenant không, hay đang gộp chung NAT/proxy?
3. Có nhiều instance và global limit không? Các node có lệch cấu hình?
4. Request có thực sự tăng hoặc client đang retry không có backoff?
5. Thao tác bị giới hạn có cần burst/queue riêng không?
6. Backend có đủ công suất để nới ngưỡng không, hay nên tối ưu/cache?
7. Có thay đổi code, chính sách, lịch job hoặc giao dịch hợp lệ trước thời điểm lỗi không?

Tăng ngưỡng bừa bãi có thể chuyển vấn đề từ “429 dễ thấy” thành “database quá tải, 503 và timeout”. Cần tìm điểm nghẽn và lý do phải tăng hạn mức.

### 12.3. Khi DDoS vẫn gây mất dịch vụ dù đã có rate limit

Các khả năng thường gặp:

- **Đường truyền nghẽn trước edge:** cần phối hợp ISP/CDN/nhà cung cấp chống DDoS upstream.
- **Nguồn phân tán:** mỗi IP dưới ngưỡng nhưng tổng tải vẫn cao.
- **Lỗ hổng bypass:** traffic vào origin hoặc route không có rule.
- **Key bị gom sai:** một proxy/IP dùng chung khiến chính sách phân biệt client kém.
- **Protocol attack:** áp lực vào TCP/TLS/conntrack trước khi HTTP limiter được chạy.
- **L7 hợp lệ nhưng nặng:** mỗi request dưới ngưỡng RPS nhưng DB/query rất tốn chi phí.
- **Quá nhiều request đồng thời:** thiếu concurrency limit, queue/backpressure và timeout.
- **Limiter phân tán không đồng bộ:** ngưỡng local không phản ánh ngân sách toàn cụm.

Trong mọi trường hợp, đối chiếu telemetry ở **từng điểm điều khiển** để xác định tầng nào bão hòa, thay vì mặc định rằng WAF đã chặn thì mọi phía sau đều an toàn.

## 13. Vận hành và quản trị chính sách

Một quy trình triển khai giảm rủi ro tự gây gián đoạn:

1. **Khảo sát luồng và năng lực:** xác định công suất, baseline traffic theo route/tenant, burst hợp lệ, tail latency và tài nguyên backend.
2. **Lập threat model:** phân biệt volumetric, connection exhaustion, slow request và resource-intensive L7.
3. **Chọn limiting key và điểm thực thi:** hiểu IP sau proxy, NAT/CGNAT, IPv6, danh tính client và đường bypass.
4. **Thiết kế nhiều ngưỡng:** sustained rate, burst, CPS, concurrent connections, in-flight requests, queue, timeouts và quota nếu cần.
5. **Thử quan sát:** dùng dry-run/simulate khi sản phẩm hỗ trợ; xem số lượng người dùng hợp lệ bị ảnh hưởng.
6. **Kiểm thử và rollout nhỏ:** xác minh cả traffic hợp lệ, burst hợp lệ, traffic vượt ngưỡng và chức năng dự phòng.
7. **Chuyển enforcement có rollback:** ghi rule ID, owner, ngưỡng, thời hạn ngoại lệ, người phê duyệt và kế hoạch hạ cấp.
8. **Giám sát liên tục:** đo 429/503, người dùng bị ảnh hưởng, độ trễ, queue, sensor health và lưu lượng bypass.
9. **Rà soát định kỳ:** dọn ngoại lệ cũ, điều chỉnh theo seasonality, tính năng mới và thay đổi công suất.

**Ngoại lệ cho đối tác/monitoring** phải giới hạn đúng định danh, nguồn, route, thời gian và quota. Không tạo miễn trừ toàn mạng hoặc bỏ xác thực chỉ vì một job batch hợp lệ bị limit.

## 14. Tình huống thiết kế tổng hợp

**Bối cảnh:** ứng dụng bán hàng có ba loại đường dẫn:

- **GET /catalog:** đa số đọc cache; lưu lượng người dùng công cộng.
- **POST /orders:** tạo đơn hàng, cần xác thực và tính nhất quán giao dịch.
- **POST /reports:** xuất báo cáo nặng, thường mất vài giây.

Kiến trúc có CDN/WAF, API gateway và hai instance ứng dụng. Nhóm vận hành nhận thấy thời điểm chiến dịch khuyến mại, số RPS tăng nhưng tỷ lệ giao dịch thành công giảm; DB pool gần đầy. Mỗi IP thường chỉ gửi ít request nhưng tổng số request từ nhiều IP rất lớn.

**Phân tích:**

1. Chỉ giới hạn **per-IP** không đủ khi tổng tải phân tán vượt công suất DB.
2. Giảm request đến **/catalog** có thể tận dụng cache/CDN thay vì ép tất cả request vào origin.
3. **/orders** cần quota theo tài khoản/tenant, hạn mức tổng backend, kiểm soát idempotency và bảo đảm không làm khách hàng trả tiền/đặt hàng trùng khi retry.
4. **/reports** cần concurrency limit riêng và queue/worker có ngân sách được kiểm soát; RPS thấp không bảo đảm an toàn với request xử lý lâu.
5. Hai instance cần chính sách thống nhất; hạn mức ở từng instance **không tự là hạn mức toàn cụm**.
6. Nếu upstream bị bão hòa, phải dùng cơ chế giảm thiểu ở ISP/CDN chứ không chỉ chỉnh rate limit trên app.

### 14.1. Ma trận đề xuất để thảo luận

| Tuyến | Cấp giới hạn | Kết quả mong muốn |
| --- | --- | --- |
| /catalog | CDN cache + edge rate/bot policy | Giảm tải origin, vẫn cho người dùng hợp lệ truy cập |
| /orders | Per-account/tenant + global requests + idempotency | Tránh spam và sai lệch giao dịch |
| /reports | Per-account + concurrent job quota + deadline | Tránh chiếm hết worker/DB pool |
| Toàn API | Global protection + health/latency feedback | Giữ ứng dụng dưới ngưỡng bão hòa |
| Hạ tầng L3/L4 | Upstream mitigation + firewall/connection controls | Bảo vệ băng thông và connection state |

Ma trận chỉ mô tả **loại chính sách**, không đưa số lượng RPS/CPS cụ thể vì chưa có đo đạc công suất, tỷ lệ người dùng hợp lệ hoặc đặc tính lưu lượng thực tế.

### 14.2. Câu hỏi tự kiểm tra

1. Vì sao **50 connection đồng thời** không đồng nghĩa **50 request/giây**?
2. Với token bucket r = 2 token/giây và B = 6, sau khi xô đầy và có 8 request đồng thời, kết quả dự kiến là gì?
3. Nếu chỉ đặt rate limit tại origin nhưng băng thông Internet bị bão hòa trước đó, cần bổ sung lớp bảo vệ nào?
4. Vì sao một API sau CDN có thể chặn nhầm toàn bộ người dùng nếu key dựa trên IP peer của proxy?
5. Tại sao bảo vệ **/reports** cần concurrent job limit dù RPS không cao?
6. Nếu một user gọi 100 request qua HTTP/2 trên một kết nối TCP, chỉ giới hạn 1 TCP connection có đủ không?
7. Trong hệ thống bốn instance với local limit 100 RPS/instance, có chắc khách hàng chỉ nhận 100 RPS toàn cụm không?
8. Khi 429 tăng đột ngột sau triển khai chính sách, làm sao phân biệt bot bị chặn với người dùng hợp lệ bị ảnh hưởng?
9. Khi một server trả 503 vì quá tải, vì sao không nên đơn giản tăng mọi ngưỡng rate limit?
10. Những lớp nào giúp ngăn một API tốn CPU bị lạm dụng dù request rate của từng IP thấp?

**Gợi ý:** (1) Connection là trạng thái đang mở, rate là số sự kiện theo thời gian. (2) Cho phép tối đa 6 request tức thời, 2 vượt hạn nếu không chờ. (3) CDN/ISP/upstream scrubbing và khả năng hấp thụ ở biên mạng. (4) Mọi client đi qua cùng proxy có thể dùng chung bucket. (5) Thời gian xử lý dài làm tăng số job đồng thời. (6) Không; cần request/stream concurrency limit. (7) Không; local limit không đồng bộ. (8) Đối chiếu key, route, identity, log và business success. (9) Có thể khiến backend sụp nhanh hơn. (10) Concurrency/weighted quota, queue, timeout, cache, xác thực và giới hạn tổng.

## 15. Những sai lầm thường gặp

| Nhận định sai | Cách hiểu đúng |
| --- | --- |
| “Rate limiting là giới hạn connection.” | Rate và concurrency là hai đại lượng khác nhau. |
| “Chặn theo IP sẽ chống được mọi DDoS.” | Botnet phân tán hoặc NAT/CGNAT khiến per-IP limit có giới hạn. |
| “Mỗi node có rate limit 100 RPS thì toàn cụm cũng 100 RPS.” | Cần xét global limit và phân phối giữa các instance. |
| “429 nào cũng là tấn công.” | Client hợp lệ, retry loop hoặc lỗi cấu hình cũng có thể vượt quota. |
| “Dùng HTTP 429 sẽ giải quyết được TCP SYN flood.” | HTTP policy được áp dụng muộn hơn và không bảo vệ toàn bộ tài nguyên L3/L4. |
| “Một connection tương đương một HTTP request.” | Keep-alive, HTTP/2 và HTTP/3 có thể phục vụ nhiều request trên một connection. |
| “Cứ xếp hàng request thay vì chặn là tốt.” | Hàng đợi quá dài làm tăng latency, sử dụng bộ nhớ và timeout. |
| “Tăng burst không có rủi ro.” | Burst vượt khả năng backend vẫn có thể tạo đỉnh tải nguy hiểm. |
| “X-Forwarded-For luôn là IP thật.” | Chỉ đáng tin khi qua chuỗi proxy được xác thực/cấu hình đúng. |
| “Giới hạn ở WAF đã bảo vệ mọi đường vào origin.” | Phải kiểm tra ingress nội bộ, host, IPv6 và đường bypass. |
| “Rate limit cố định tốt cho mọi endpoint.” | Chi phí công việc và mức hợp lệ khác nhau theo route, user và thời gian. |

## 16. Tổng kết

**Rate limiting** hạn chế số sự kiện theo thời gian, còn **connection limit** hạn chế số kết nối đang tồn tại; bên cạnh đó còn có **new connection rate**, **request concurrency**, kích thước payload, timeout và quota tài nguyên. Các cơ chế phải được đo và áp dụng theo đúng lớp để xử lý những vấn đề khác nhau, từ HTTP request flood đến tiêu thụ trạng thái kết nối.

Trong **SECURITY_NETWORK_SECURITY**, phòng vệ DDoS hiệu quả cần **nhiều lớp cùng vận hành**: upstream/CDN bảo vệ băng thông, firewall và hạ tầng L4 bảo vệ trạng thái kết nối, WAF/API gateway kiểm soát request, ứng dụng bảo vệ công suất và quota, còn IDS/IPS cùng telemetry hỗ trợ phát hiện và phản ứng. Chính sách tốt phải dựa trên **baseline hợp lệ, threat model, thử nghiệm có phạm vi, giám sát tác động nghiệp vụ và quy trình rollback**, chứ không chỉ là một con số RPS.

### Tài liệu tra cứu

- **RFC 6585 — Additional HTTP Status Codes:** định nghĩa HTTP 429 Too Many Requests.
- **RFC 9110 — HTTP Semantics:** mã trạng thái HTTP và Retry-After.
- **NGINX Documentation — ngx_http_limit_req_module:** rate limiting, burst, dry-run và cách cấu hình limit_req.
- **NGINX Documentation — ngx_http_limit_conn_module:** connection limit, cách đếm và cấu hình limit_conn.
- **OWASP Denial of Service Cheat Sheet:** nguyên tắc giảm tiêu thụ tài nguyên và bảo vệ ứng dụng.
- **OWASP API Security Top 10 (2023), API4 — Unrestricted Resource Consumption:** rủi ro về giới hạn tài nguyên ở API.
- **CISA — Distributed Denial-of-Service (DDoS) guidance:** chuẩn bị, nhận biết và phối hợp phản ứng với lưu lượng DDoS.
