# Timeout và circuit breaker trong kết nối: bảo vệ API và hệ thống mạng trước lỗi dây chuyền

Một API được triển khai trên cloud có thể phụ thuộc DNS, kết nối TCP/TLS, API gateway, một gRPC service, cache và database đặt tại data center riêng qua VPN. Khi database phản hồi chậm, hàng nghìn request giữ kết nối và worker chờ kết quả; client lần lượt timeout rồi tự retry, gateway cũng retry, khiến backend vốn đang yếu lại nhận nhiều request hơn. Chỉ mở thêm connection pool hoặc tăng timeout có thể làm hàng đợi dài ra và khuếch đại sự cố.

**Timeout** là giới hạn thời gian chờ ở một thao tác hoặc một giai đoạn kết nối. **Circuit breaker** là cơ chế tạm thời ngừng cho các lời gọi đến một dependency được đánh giá là đang lỗi, sau đó thăm dò có kiểm soát để quyết định khôi phục lưu lượng. Hai cơ chế **bổ trợ**: timeout giới hạn thời gian một tác vụ có thể chiếm tài nguyên; circuit breaker giảm số lời gọi mới tới một dependency đang gặp sự cố. Không cơ chế nào thay thế xác thực, phân quyền, firewall, giám sát hay thiết kế phục hồi.

Trong mô-đun **SECURITY_NETWORK_SECURITY**, chủ đề này liên kết bảo vệ API, TLS, VPN, IDS/IPS, firewall stateful, phân đoạn, DNS, routing và hệ thống cloud. Mục tiêu thực tế là **giữ dịch vụ phản hồi trong ngân sách thời gian, giảm lan truyền lỗi, tránh tạo tải ngoài ý muốn và khôi phục có kiểm chứng**. Các cấu hình, thời gian và hostname dưới đây chỉ để học; không dùng làm mặc định cho mọi hệ thống production.

> **Nguyên tắc thực hành:** Chỉ kiểm tra trên hệ thống thuộc phạm vi được phép; ưu tiên mock/staging và kết nối đọc dữ liệu. Không cố ý gây mất mạng, làm đầy connection pool, mở hàng loạt kết nối hoặc tắt backend production để thử circuit breaker nếu chưa có phê duyệt và điều kiện dừng rõ ràng.

## 1. Mục tiêu học tập

Sau bài học, người học có thể:

1. Phân biệt **DNS timeout, TCP connect timeout, TLS handshake timeout, connection-pool acquire timeout, read/write timeout, idle timeout, request timeout và end-to-end deadline**.
2. Thiết kế **timeout budget** cho đường API nhiều hop, bao gồm queueing, retry và thời gian còn lại do client gửi.
3. Giải thích trạng thái **CLOSED, OPEN, HALF_OPEN**, các điều kiện mở lại, cửa sổ đo lỗi và thăm dò khôi phục.
4. Phân loại **lỗi mạng, TLS, 5xx, 429, gRPC status, 4xx/authorization, cancellation** để không coi mọi phản hồi đều là lỗi của dependency.
5. Kết hợp circuit breaker với **retry policy, exponential backoff, jitter, idempotency, rate limiting, bulkhead và load shedding**.
6. Nhận diện tình huống **retry storm, cascading failure, resource exhaustion, stale keep-alive connection, asymmetric route và VPN failover**.
7. Thiết kế metrics/logs/traces cho **HTTP/1.1, HTTP/2, gRPC, service mesh và cloud API gateway**.
8. Đề xuất **runbook, test matrix và kiểm thử có kiểm soát**; nêu được bằng chứng để xác nhận recovery mà không làm mở quá mức các kiểm soát an ninh.

## 2. Vì sao timeout là kiểm soát availability và security?

Một lời gọi mạng luôn chiếm một số tài nguyên: socket, file descriptor, bộ nhớ, worker/thread, coroutine, stream HTTP/2, slot kết nối database hoặc hàng đợi. Nếu thao tác **chờ vô hạn**, lỗi của một dependency có thể làm tích lũy tài nguyên bị giữ và lan sang các dịch vụ không liên quan.

| Hiện tượng | Khi không có timeout phù hợp | Lợi ích khi giới hạn đúng |
|---|---|---|
| Dependency không trả lời | Worker giữ tới khi hệ điều hành hoặc người dùng bỏ cuộc | Giải phóng quyền chờ có giới hạn |
| TCP connect đến đích mất route | Nhiều connection attempt treo lâu | Phản hồi lỗi trong ngân sách dịch vụ |
| TLS handshake dở dang | Socket và handshake state chiếm tài nguyên | Cắt kết nối không hoàn tất |
| HTTP/gRPC stream không kết thúc | Buffer, memory và stream slot bị giữ | Dừng request quá hạn/không hoạt động |
| Database chậm | Queue app tăng và gây lỗi dây chuyền | Ngăn hết thời gian xử lý ở upstream |
| Nhiều tầng retry | Nỗ lực gọi xuống có thể nhân lên | Áp giới hạn tổng nỗ lực và retry budget |

**Timeout không phải tường lửa chống DDoS.** Nó giúp giảm thời gian giữ tài nguyên nhưng không tự giới hạn số lượng request, băng thông, message size hoặc quyền người gọi. Cần phối hợp **admission control, authentication, rate limit, resource quota, WAF/IDS/IPS khi phù hợp và monitoring**.

### Hai mục tiêu không đồng nhất

- **Fail fast:** nhanh chóng trả lỗi khi biết lời gọi không có cơ hội hoàn tất trong thời gian chấp nhận.
- **Graceful degradation:** tiếp tục phục vụ chức năng còn khỏe, có thể dùng cache/fallback hoặc trả thông báo phù hợp.

**Fail fast không có nghĩa luôn tốt hơn chờ.** Một thao tác batch đã thỏa thuận chờ lâu có thể cần deadline khác một API tìm kiếm tương tác. Quyết định phải gắn với **SLO, giá trị nghiệp vụ và chi phí tài nguyên**.

## 3. Tách lớp vòng đời một yêu cầu mạng

Một lời gọi từ client tới API có thể gồm các pha:

~~~text
Client
  |
  +-- DNS resolution / service discovery
  |
  +-- Connection pool acquire (nếu tái sử dụng kết nối)
  |
  +-- TCP connect hoặc transport establishment
  |
  +-- TLS handshake + peer certificate validation
  |
  +-- Send request / upload body
  |
  +-- Wait for first response bytes/headers
  |
  +-- Read response / stream messages
  |
  +-- Application parsing + processing
  |
  +-- Business transaction complete
~~~

Các bước **không luôn nối tiếp đúng thứ tự** trong mọi runtime: DNS có thể được cache, connection pool có thể trả sẵn kết nối, TLS session có thể được resume, HTTP/2 có nhiều stream cùng kết nối, proxy tạo một kết nối TLS khác đến upstream, và QUIC vận hành khác TCP. Vì vậy cần đọc định nghĩa timeout của **thư viện và sản phẩm đang sử dụng**.

### Phân loại giới hạn thời gian

| Loại giới hạn | Đo từ đâu đến đâu? | Lỗi điển hình cần phân biệt |
|---|---|---|
| **DNS resolution timeout** | Khi hỏi resolver tới lúc có kết quả hoặc hết thời gian | Resolver chậm, DNS query bị chặn |
| **Pool acquire timeout** | Thời gian chờ lấy connection từ pool | Pool đầy, connection leak |
| **TCP connect timeout** | Quá trình thiết lập kết nối tới remote socket | Route/firewall/drop/đích không nghe |
| **TLS handshake timeout** | Thời gian thương lượng TLS và xác thực peer | Peer chậm, certificate/trust, proxy |
| **Write/send timeout** | Giới hạn thời gian gửi request/body theo API thư viện | Peer không đọc, network congestion |
| **Read/response timeout** | Chờ byte/headers/response theo cách định nghĩa | Backend treo, proxy buffering |
| **Idle timeout** | Không có hoạt động trong một khoảng trên connection/stream | Kết nối không hoạt động quá lâu |
| **Per-attempt timeout** | Toàn bộ một lần thử gọi dependency | Chưa giới hạn tổng khi có retry |
| **End-to-end deadline** | Thời điểm cuối cùng của toàn bộ yêu cầu nghiệp vụ | Chuỗi hop/retry vượt ngân sách |

**Tên cùng một timeout có thể mang nghĩa khác nhau theo framework.** Ví dụ read timeout thường được triển khai theo **khoảng chờ giữa các lần đọc**, không nhất thiết giới hạn **tổng thời gian** nhận một response. Một stream gửi dữ liệu nhỏ đều đặn có thể không bao giờ chạm read timeout kiểu idle dù tổng cuộc gọi kéo dài rất lâu.

## 4. Phân biệt connect timeout, request timeout và deadline

Giả sử client dự kiến hoàn tất một yêu cầu trong tối đa 2 giây. Nếu chỉ cấu hình **connect timeout = 2 giây**, kết nối TCP thành công sau 20 ms nhưng service sau đó chờ database 60 giây vẫn có thể khiến ứng dụng bị treo nếu không có giới hạn khác.

~~~text
Time axis (minh họa)
0 ms            20 ms        300 ms          2.000 ms
 |---------------|------------|-----------------|
 start         connected     TLS done       total deadline
 |<--- connect --->|
 |<--- TLS/request processing + queue + retries ------->|
~~~

Một **total deadline** bao trùm các công việc mà hệ thống thiết kế muốn giới hạn. Tuy nhiên, API client có thể không áp deadline lên mọi pha DNS/pool/TLS như kỳ vọng nếu triển khai thiếu nhất quán. Cần **kiểm chứng bằng instrumentation và thử nghiệm được kiểm soát**.

### Timeout là khoảng thời gian; deadline là thời điểm

- **Timeout = 500 ms**: cho phép một thao tác chờ tối đa khoảng thời gian được định nghĩa.
- **Deadline = 10:00:02.000Z**: kết thúc trước một mốc thời gian cụ thể.
- Khi truyền deadline giữa các service, phải xem **clock synchronization, cách encode và chuyển thời gian còn lại** của framework; không tự tin rằng mọi host có đồng hồ tuyệt đối đồng bộ.

Với gRPC, các runtime thường quản lý **deadline/remaining timeout** trong metadata và có cơ chế propagation khi được cấu hình, nhưng ứng dụng vẫn phải **chấp hành cancellation và giới hạn công việc bên dưới**.

### Hết deadline có bảo đảm dừng xử lý không?

**Không.** Client nhận timeout chỉ chứng minh **client ngừng chờ** theo điều kiện xác định. Server có thể tiếp tục chạy DB query, gửi email, trừ tiền hoặc ghi dữ liệu nếu cancellation không được truyền/xử lý đúng. Đó là lý do yêu cầu idempotency và xử lý kết quả không chắc chắn rất quan trọng.

## 5. Thiết kế timeout budget cho nhiều hop

Một API gọi nhiều dependency nối tiếp phải phân bổ thời gian chờ **phù hợp deadline tổng**, không cộng vô hạn các cấu hình riêng lẻ.

~~~text
  Mobile Client
      |
      | Total budget: ví dụ 2.000 ms
      v
   API Gateway -------- Auth service
      |
      v
   App Service -------- Cache
      |
      v
   Data Service -------- Database
      |
      v
    Response
~~~

**Ví dụ phân bổ sơ bộ cho đường tuần tự**, không phải chuẩn kỹ thuật:

| Phần việc | Dự phòng tối đa minh họa |
|---|---:|
| Ingress/auth và overhead gateway | 150 ms |
| App validation + routing | 100 ms |
| Gọi dependency A | 450 ms |
| Gọi dependency B | 650 ms |
| Serialization/response | 150 ms |
| Buffer cho jitter, queue, scheduling | 300 ms |
| **Tổng dự trù** | **1.800 ms** |

Với deadline **2.000 ms**, khoảng chênh lệch là **200 ms** trong ví dụ. Con số phải được chỉnh theo phân bố latency và cả những nhánh thực thi **song song** (không cộng thời gian của nhánh song song như tuần tự), số request fan-out và tình trạng giờ cao điểm.

### Quy tắc quan trọng

1. Bắt đầu từ **SLO của hành trình người dùng**, không từ con số mặc định trong SDK.
2. Lưu lại phần thời gian đã tiêu ở gateway, queue, TLS, service và DB.
3. Dùng **deadline còn lại** khi quyết định có nên gọi dependency hoặc retry không.
4. Không cấp per-attempt timeout dài hơn ngân sách còn lại nếu điều đó khiến cuộc gọi không thể kết thúc đúng SLO.
5. Khi một dependency có nhiều điểm dự phòng, dành **budget cho failover hoặc retry** theo chính sách.
6. Đặt timeout cho cả pha **acquire connection và xử lý ứng dụng**, không chỉ TCP connect.
7. Chừa ngân sách cho ghi log, dọn tài nguyên và response/rollback khi nghiệp vụ yêu cầu.

**Đặt mọi service timeout bằng 30 giây không tạo end-to-end budget 30 giây.** Khi có hàng đợi, retry hoặc fan-out, thời gian tích lũy và tài nguyên giữ có thể lớn hơn nhiều.

## 6. Timeout theo percentile và SLO: tránh đoán ngẫu nhiên

Nếu một API cần p99 latency dưới một giới hạn, dùng **phân bố latency của dependency**, bao gồm giờ cao điểm và network path, để chọn giới hạn thay vì mặc định ngưỡng quá ngắn.

| Quan sát | Hệ quả |
|---|---|
| Dependency p99 xấp xỉ 180 ms trong điều kiện bình thường | Timeout 100 ms có thể cắt nhiều request hợp lệ |
| Dependency p99 tăng lên 2 s khi quá tải | Timeout 30 s giữ quá nhiều slot và không giải quyết nguyên nhân |
| Route VPN failover tạo vài giây bất ổn | Cần tính tới HA, nhưng không nên cho mọi lời gọi chờ vô hạn |
| Một số request xử lý batch dài | Cần endpoint/task model hoặc async workflow riêng |
| Backend có heavy-tail latency | Chọn timeout theo sự cân bằng giữa thành công, false timeouts và tài nguyên |

**p95/p99 không phải ngưỡng an toàn phổ quát.** Chọn timeout rất gần p99 có thể làm một phần request khỏe bị cắt do biến động/measurement noise. Cần xét tail distribution, load, fan-out, retry cost và tỉ lệ lỗi được chấp nhận.

### Ba lớp SLO khác nhau

- **User-facing SLO:** hành trình cuối cùng hoàn thành đúng thời gian.
- **Dependency SLO:** một dịch vụ con đáp ứng trong budget được cam kết.
- **Protection SLO:** khi dependency xấu, hệ thống **giới hạn tài nguyên, giảm ảnh hưởng và phục hồi** theo các mục tiêu quan sát được.

Circuit breaker tốt có thể **tăng tỷ lệ từ chối nhanh** trong thời gian lỗi để **bảo toàn availability của phần hệ thống còn khỏe**. Không nên đánh giá nó chỉ qua số request bị OPEN từ chối.

## 7. TCP, TLS, DNS, VPN và timeout trong network security

Lỗi ứng dụng “timeout” có thể đến từ nhiều lớp:

| Lớp | Tình huống | Bằng chứng nên lấy |
|---|---|---|
| **DNS** | Resolver chậm, split DNS sai, cache stale | Resolve time, DNS responses, TTL và nguồn hỏi |
| **Routing** | Route bị rút hoặc next hop sai | RIB/FIB, VRF, route changes, chiều về |
| **Firewall** | SYN bị drop, policy mới chặn response | Firewall logs, counters, session state |
| **VPN** | Tunnel UP nhưng traffic selectors/return path lỗi | IKE/SA, route/BGP, NAT-T, tunnel counters |
| **TLS** | Handshake chậm, cert/trust lỗi, proxy trả certificate khác | SNI, TLS alerts, handshake time, cert identity |
| **HTTP/2** | Stream bị queue, reset hoặc flow-control stall | In-flight streams, RST_STREAM, GOAWAY |
| **Application** | Thread pool đầy, DB lock hoặc downstream chậm | Trace, queue, pool metrics, DB telemetry |

**Không mở firewall Allow Any–Any chỉ vì client timeout.** Trước tiên xác định nguồn/đích, port, protocol, đường đi hai chiều và điểm dừng của phép thử. Một timeout tại TLS hoặc ứng dụng khác với **kết nối không có route**.

### Timeout và proxy nhiều hop

Một request có thể qua:

~~~text
Client -> CDN/WAF -> API Gateway -> Service Mesh -> App -> DB
            |           |              |           |
       idle timeout   route/queue    retry/cb    DB query timeout
~~~

Các timeout cần **tương thích với hành vi giữa các hop**, nhưng không nhất thiết đặt giá trị theo một công thức giản đơn. Ví dụ upstream proxy chờ quá ngắn so với backend khiến client sớm nhận lỗi rồi retry, trong khi backend vẫn chạy. Ngược lại, đặt gateway timeout cực dài có thể khiến nhiều connection bị giữ khi downstream chết.

## 8. HTTP/1.1, HTTP/2 và gRPC: timeout không cùng ngữ nghĩa

### HTTP/1.1 và connection reuse

Một connection keep-alive có thể phục vụ nhiều request nối tiếp theo implementation. Connection **đã mở từ trước** có thể bị proxy đóng do idle timeout; client lấy lại socket stale từ pool và gặp lỗi khi thử sử dụng. Cần cơ chế health check/retry có kiểm soát.

### HTTP/2 multiplexing

Một TCP/TLS connection có thể có **nhiều stream đồng thời**, nên **connection idle timeout và per-stream deadline khác nhau**. Đóng cả connection khi một stream quá hạn có thể ảnh hưởng những RPC khác đang dùng kết nối. Ngược lại, chỉ giới hạn connection count không kiểm soát được lượng RPC đồng thời.

### gRPC deadlines

gRPC hỗ trợ deadline và tín hiệu cancellation ở mức RPC. Với server streaming/bidirectional streaming, cần xác định rõ:

- Stream được phép tồn tại tối đa bao lâu?
- Khi không có message trong một khoảng, có phải lỗi không?
- Có heartbeats/keepalive và giới hạn nhịp phù hợp không?
- Một message lớn hoặc client chậm có tiêu thụ buffer quá nhiều không?
- Khi client cancel, backend và các downstream có dừng công việc không?

**gRPC status DEADLINE_EXCEEDED** có nghĩa deadline theo ngữ nghĩa RPC đã vượt; **CANCELLED** có thể đến từ client hoặc ngữ cảnh liên quan. Không coi chúng luôn là lỗi server cần tính vào circuit breaker.

## 9. Circuit breaker: khái niệm và mục tiêu

Circuit breaker là mẫu thiết kế **chuyển trạng thái** dựa trên độ khỏe của một dependency. Nó không thử phục hồi ngay bằng cách gửi **mọi** request xuống dependency khi dependency đang lỗi, mà giảm số request được phép đi qua.

~~~text
           CLOSED
      (cho phép lời gọi)
             |
      Lỗi vượt chính sách
             v
            OPEN
      (từ chối nhanh)
             |
      Hết thời gian chờ mở
             v
         HALF_OPEN
   (thử ít lời gọi có kiểm soát)
       /               \
 Thăm dò đạt        Thăm dò lỗi
       |                 |
       v                 v
     CLOSED             OPEN
~~~

### Ý nghĩa ba trạng thái

| Trạng thái | Xử lý request | Ý nghĩa |
|---|---|---|
| **CLOSED** | Cho phép lời gọi đi tới dependency, ghi kết quả | Hệ thống chưa coi dependency cần ngắt tạm |
| **OPEN** | Từ chối nhanh hoặc dùng fallback theo policy, thường không gọi dependency | Giảm tải tới vùng đang lỗi |
| **HALF_OPEN** | Cho một số request/probe hữu hạn đi qua để đánh giá khôi phục | Tránh mở lại toàn bộ traffic chỉ sau một lần thành công |

Tên trạng thái là **mẫu phổ biến**, không phải mọi thư viện đều dùng cùng state machine hoặc thời gian. Một số có **DISABLED, FORCED_OPEN, METRICS_ONLY** hoặc các trạng thái bổ sung; cần xem tài liệu của implementation.

### Circuit breaker khác timeout

- **Timeout** tác động lên **một lần chờ**.
- **Circuit breaker** dùng **kết quả lịch sử** và trạng thái dependency để quyết định có **gửi lời gọi mới** hay không.
- Breaker OPEN không bảo đảm **lời gọi đang chạy** được dừng; chúng vẫn cần deadline/cancellation.
- Breaker CLOSED không bảo đảm dependency đang khỏe trong mọi request; nó chỉ cho phép request đi qua và đo kết quả.

## 10. Nên đặt circuit breaker ở đâu?

Đặt circuit breaker ở lớp **biết dependency nào đang được gọi và có thể phân loại kết quả**. Một breaker quá rộng có thể làm tất cả chức năng ngừng vì một endpoint phụ lỗi.

| Vị trí | Hữu ích khi | Điều phải cảnh giác |
|---|---|---|
| **API gateway** | Gọi upstream hoặc route theo backend cụ thể | Breaker chung cho mọi route có thể chặn nhầm service khỏe |
| **Service client library** | Gọi API, DB, queue hoặc external service từ một ứng dụng | Cần scope/instance phù hợp, shared metrics và policy nhất quán |
| **Service mesh sidecar** | Bảo vệ upstream cluster, outlier detection và retry policy | Không thay application-level authorization, budget hoặc business context |
| **Background worker** | Gọi batch/third-party API theo job | Xử lý retry queue và idempotency cần thiết |
| **Database access layer** | Đối phó khi DB/service proxy không khỏe | Không che tình trạng transaction không chắc đã commit |

### Chọn phạm vi breaker

- **Per dependency/service:** phù hợp khi phần lớn endpoint của một service có cùng failure mode.
- **Per endpoint/method:** tránh method báo cáo nặng làm tê liệt method health đơn giản.
- **Per instance/zone:** giảm tác động khi một node/region lỗi nhưng các node khác vẫn tốt.
- **Per tenant/caller:** đôi khi giúp cô lập hành vi lạm dụng/quota, nhưng **không nên dùng chung khái niệm này để thay authorization hoặc rate limiting**.

**Breaker scope phải phản ánh fault domain.** Nếu ba region độc lập nhưng dùng một breaker toàn cầu, region A lỗi có thể làm request tới B/C khỏe cũng bị từ chối. Ngược lại, nếu mỗi pod giữ trạng thái hoàn toàn riêng, quá nhiều pod cùng HALF_OPEN có thể tạo **probe stampede**.

## 11. Chọn loại lỗi nào được tính vào circuit breaker?

Không phải mọi phản hồi không thành công đều chứng minh dependency mất khả năng phục vụ. Ví dụ **401/403** thường thể hiện caller thiếu thông tin xác thực/quyền; mở circuit breaker vì user nhập sai token có thể tạo một điểm gây từ chối dịch vụ.

| Tín hiệu | Thường nên xem như | Lưu ý |
|---|---|---|
| **Connection refused, reset, timeout** | Dấu hiệu lỗi network/dependency tùy nguồn | Phân biệt DNS, TLS trust, firewall policy và stale socket |
| **HTTP 500, 502, 503, 504** | Có thể tính là lỗi downstream | 502/504 có thể do gateway hoặc upstream; phân loại theo hop |
| **HTTP 429** | Hạn mức/quota hoặc overload, không nhất thiết lỗi hạ tầng | Tôn trọng Retry-After khi phù hợp, không retry ồ ạt |
| **HTTP 400/401/403/404** | Thường là kết quả client/policy hoặc không tìm thấy | Không mặc định tăng breaker failure rate |
| **gRPC UNAVAILABLE** | Có thể là lỗi tạm thời/unreachable | Xem retry semantics, peer/transport |
| **gRPC DEADLINE_EXCEEDED** | Có thể là chậm/lỗi tài nguyên hoặc budget quá ngắn | Xem request duration và điểm áp deadline |
| **gRPC RESOURCE_EXHAUSTED** | Có thể là quota hay overload | Phân biệt caller vượt quota với backend bị quá tải |
| **gRPC UNAUTHENTICATED/PERMISSION_DENIED** | Thường là từ chối truy cập đúng chính sách | Không mở breaker chỉ vì người dùng không có quyền |
| **gRPC CANCELLED** | Thường có thể do client chủ động hủy | Không tự coi server lỗi |
| **Success response có dữ liệu sai** | Lỗi nghiệp vụ cần validation riêng | Một HTTP 200 không chứng minh dependency khỏe toàn diện |

**Phải phân biệt lỗi của caller với lỗi của dependency.** Policy không nên cho phép một client không được xác thực tạo ra hàng nghìn 401 rồi làm OPEN breaker dùng chung cho mọi người dùng hợp lệ.

### Gọi lỗi là transient hay permanent?

- **Transient:** kết nối hoặc dịch vụ có thể hồi phục sau thời gian ngắn, ví dụ một node đang chuyển đổi.
- **Permanent/semantic:** request thiếu quyền, sai input, resource không tồn tại theo nghiệp vụ.
- **Unknown:** không đủ log hoặc dữ liệu phản hồi để phân loại.

Timeout, retry và breaker cần dùng **bảng phân loại nhất quán nhưng có khả năng hiệu chỉnh theo từng dependency**.

## 12. Cửa sổ đo lỗi và ngưỡng mở circuit

Breaker không nên OPEN vì một lỗi ngẫu nhiên khi có tổng số request rất thấp. Một số implementation kết hợp **sliding window**, **minimum number of calls**, **failure rate** và **slow call rate**.

~~~text
Policy minh họa cho service A (không phải mặc định production)

Observation window:       60 giây
Minimum observed calls:   20
Failure-rate threshold:   >= 50%
Open-state wait:          30 giây
Half-open probe limit:    3 lời gọi đồng thời có kiểm soát
Recovery decision:       Theo tiêu chí đủ số probe và kết quả
~~~

| Thông số | Điều cần cân nhắc |
|---|---|
| **Count-based/time-based window** | Tính trên N lời gọi gần nhất hay trong T giây |
| **Minimum calls** | Tránh một lỗi duy nhất trong dịch vụ ít traffic làm mở circuit |
| **Failure rate threshold** | Ngưỡng phù hợp baseline và tỉ lệ lỗi chấp nhận |
| **Slow-call threshold** | Có nên nhận diện lời gọi quá chậm dù chưa thất bại? |
| **Open wait duration** | Quá ngắn tạo thăm dò liên tục; quá dài kéo dài gián đoạn |
| **Half-open permitted calls** | Tránh tất cả caller cùng đẩy tải khi hồi phục |
| **Result classification** | 401/403/429/deadline phải xử lý theo ngữ cảnh |

### Ví dụ tính failure rate

Nếu một cửa sổ hợp lệ ghi 40 lời gọi, có 24 lỗi thuộc nhóm đã chọn:

~~~text
Failure rate = 24 / 40 * 100% = 60%
~~~

Nếu policy mở khi **failure rate >= 50%** sau tối thiểu 20 lời gọi, kết quả này **đủ điều kiện kích hoạt theo mẫu**. Nhưng trạng thái thực còn phụ thuộc thời gian cập nhật, loại lỗi, giới hạn do library thiết lập và khả năng có một breaker được buộc OPEN/DISABLED.

**Một API ít traffic không nên mặc định đợi đủ 20 request mới bảo vệ được service.** Có thể cần health-based routing/other signals hoặc chính sách riêng, được thiết kế cẩn thận để tránh false positives.

## 13. HALF_OPEN: khôi phục có kiểm soát

Một lỗi dễ mắc là vừa hết 30 giây chờ OPEN đã cho **toàn bộ** traffic đi tới dependency đang hồi phục. Nếu nhiều instance/gateway đồng loạt thử, backend có thể bị quá tải ngay khi vừa khởi động lại.

~~~text
OPEN
  |
  | Wait expires
  v
HALF_OPEN
  |
  +-- Allow small number of approved probe requests
  |
  +-- Evaluate outcomes and latency
  |       |
  |       +-- Healthy enough --> CLOSED
  |       |
  |       +-- Still unhealthy --> OPEN
  |
  +-- Other requests: reject/queue/fallback per policy
~~~

### Những điều cần bảo đảm

1. **Probe không gây tác dụng phụ nguy hiểm.** Nếu dùng health-check riêng, phải có phép xác minh phù hợp; nếu dùng real traffic, chọn cách đánh giá và idempotency cẩn thận.
2. **Giới hạn đồng thời** ở HALF_OPEN, đặc biệt khi nhiều replica cùng giữ breaker state.
3. **Kiểm tra đủ bằng chứng**: một kết nối TCP thành công không chứng minh DB hoặc API đã phục hồi.
4. Có **backoff/jitter** ở probe/recovery khi phù hợp để tránh synchronized retry.
5. Khi CLOSED, vẫn duy trì rate limit và bulkhead thay vì xả toàn bộ hàng đợi cũ vào backend.

**Half-open không phải quyền bỏ qua authorization.** Mọi probe/request hợp lệ vẫn phải được xác thực, phân quyền và ghi nhận theo chính sách.

## 14. Pseudocode của circuit breaker có xét deadline

~~~text
function callDependency(request, context):
    if context.remainingDeadline <= safetyMargin:
        return DEADLINE_EXCEEDED

    if !authorizationAllowsThisOperation(context, request):
        return PERMISSION_DENIED

    breaker = breakerFor(dependency, operationClass)

    if breaker.state == OPEN and !breaker.shouldAttemptRecovery():
        record("circuit_rejected")
        return approvedFallbackOrUnavailable()

    permit = breaker.tryAcquirePermit()
    if permit == NONE:
        return approvedFallbackOrUnavailable()

    try:
        budget = min(perAttemptTimeout, context.remainingDeadline)
        result = dependencyCallWithTimeoutAndCancellation(budget)
        breaker.record(classifyDependencyOutcome(result))
        return result
    finally:
        permit.release()
~~~

Pseudocode minh họa **quan hệ giữa deadline, breaker và quyền gọi**, không phải implementation đầy đủ. Trên thực tế cần xử lý thread safety, state race, cleanup, exception mapping, clock, metrics, resource pool và semantics của fallback. **Không được để fallback hoặc breaker bypass quyền truy cập**.

## 15. Retry: vì sao thử lại có thể làm sự cố tệ hơn?

Retry có thể hữu ích khi gặp lỗi **tạm thời** như connection reset trong quá trình chuyển node hoặc HTTP 503 khi dịch vụ đang bảo trì ngắn. Nhưng retry **tiêu thụ thêm tài nguyên**, và nếu nhiều tầng đồng thời retry thì tải có thể tăng theo cấp số nhân.

### Ví dụ khuếch đại tải

Giả sử client có **tối đa 3 attempts** cho một request, gateway cũng có tối đa 3 attempts tới service A, và service A lại có tối đa 3 attempts tới database:

~~~text
Client:     3 attempts
Gateway:    3 attempts per client attempt
Service A:  3 attempts per gateway attempt

Worst-case attempt count toward DB:
3 * 3 * 3 = 27 attempts

Đây là số lượng khả dĩ theo cấu hình ví dụ,
không phải số request chắc chắn trong mọi tình huống.
~~~

Nếu tất cả những attempt này xảy ra khi DB đang quá tải, **27 nỗ lực từ một request gốc** có thể làm tình trạng nghiêm trọng hơn. Vấn đề không nằm ở giao thức HTTP/gRPC mà ở **thiếu chính sách retry toàn chuỗi**.

### Điều kiện retry có trách nhiệm

1. **Chỉ retry lỗi phù hợp**, không retry mù mọi 4xx hoặc lỗi authentication.
2. Xem lời gọi có **idempotent** hay được bảo vệ bởi idempotency key/transaction semantics không.
3. Giới hạn **số attempt**, tổng thời gian và ngân sách retry trong một đơn vị thời gian.
4. Dùng **backoff và jitter**, tránh hàng nghìn client đồng thời thử lại.
5. Tính timeout cho **mỗi attempt** bên trong **end-to-end deadline còn lại**.
6. Tôn trọng tín hiệu giới hạn tải như **Retry-After** khi giao thức/ứng dụng hỗ trợ.
7. Không retry khi circuit breaker OPEN nếu đường gọi đó không được chính sách cho phép thăm dò.
8. Đo **retry attempt rate, successful-after-retry, failed retry, downstream load** và tác động lên latency.

**Ngừng chờ một request không đồng nghĩa server chưa thực hiện hành động.** Với giao dịch ghi dữ liệu, timeout có thể khiến client không biết đã commit hay chưa; nếu retry không an toàn có thể tạo bản ghi/thanh toán trùng.

## 16. Exponential backoff, jitter và retry budget

**Exponential backoff** tăng khoảng chờ giữa các lần retry. **Jitter** thêm biến thiên để nhiều client không thử lại cùng thời điểm. Một phương án minh họa:

~~~text
baseDelay = 100 ms
maxDelay  = 2.000 ms

delayBeforeAttempt(n) =
    random(0, min(maxDelay, baseDelay * 2^(n-1)))

Chỉ thử lại nếu:
- loại lỗi được phép retry;
- operation an toàn khi retry;
- circuit breaker cho phép;
- còn attempts budget;
- còn đủ deadline budget cho delay + attempt.
~~~

Ví dụ trên là **full jitter** theo mô hình tổng quát, không phải cấu hình mặc định cần sao chép. Một số thư viện có sẵn nhiều biến thể exponential/decorrelated jitter; cần hiểu đơn vị, điều kiện tràn số, cách tính số lần retry và cách hủy lịch retry khi request đã hết deadline.

### Retry budget theo tải

Giả sử hệ thống cho phép retry traffic trong khoảng **một tỷ lệ có giới hạn** so với traffic gốc đang phục vụ, thay vì để tất cả request tự retry nhiều lần khi lỗi. Chính sách có thể dùng **token bucket** hoặc quota tương đương. Mục tiêu là **không làm backend mất khả năng phục hồi** chỉ vì client muốn có kết quả bằng mọi giá.

**Rate limiting và retry budget không đồng nghĩa nhau:** rate limit giới hạn tổng lưu lượng hoặc request cho một caller/operation; retry budget giới hạn phần tải **bổ sung vì cố gắng lại**.

### Idempotency phải kiểm chứng ở nghiệp vụ

| Tác vụ | Retry an toàn không? | Kiểm soát cần thiết |
|---|---|---|
| GET thông tin đã được ủy quyền | Thường thuận lợi hơn, nếu không có tác dụng phụ | Timeout và cache/consistency policy |
| Đọc danh sách lớn | Có thể, nhưng tốn tài nguyên | Pagination, quotas, request budget |
| Tạo đơn hàng | Không mặc nhiên | Idempotency key, deduplication, transaction state |
| Gửi thông báo/email | Không mặc nhiên | Outbox/deduplication và trạng thái gửi |
| Thanh toán | Không retry mù | Idempotency, transaction reconciliation và audit |
| Stream ghi nhiều thông điệp | Tùy protocol và state | Resume token/sequence numbers hoặc retry ở mức nghiệp vụ |

**Tính idempotent của HTTP method không thay thế hợp đồng nghiệp vụ**: một GET bị thiết kế có side effect hoặc một POST đã có idempotency key cần đánh giá theo implementation thật.

## 17. Thứ tự áp dụng timeout, retry, breaker và bulkhead

Một hệ thống nên xem các cơ chế resilience là **nhiều vòng bảo vệ có quan hệ**, không phải từng checkbox bật độc lập.

~~~text
  Request + authenticated principal
                 |
          Authorization
                 |
        Deadline check
                 |
        Admission / rate limit
                 |
      Bulkhead permit / queue budget
                 |
       Circuit breaker policy
                 |
        Retry controller
                 |
      Per-attempt timeout
                 |
          Dependency
                 |
      Outcome classification
                 |
      Metrics / breaker update
~~~

**Sơ đồ là logic minh họa, không phải thứ tự cố định của mọi framework.** Một số thư viện bọc breaker bên ngoài retry để tính **một request tổng**, số khác đặt breaker bên trong để tính **từng attempt**. Hai cách có thể cho failure rate và hành vi thăm dò rất khác nhau.

### Hai lựa chọn cần ra quyết định

| Thiết kế | Hệ quả có thể |
|---|---|
| **Breaker ngoài retry** | Breaker có thể thấy một kết quả cuối sau nhiều attempt; phải có metrics riêng về attempt load |
| **Breaker trong retry** | Mỗi attempt có thể ảnh hưởng trạng thái breaker; dễ mở hơn nếu nhiều retry lỗi cùng lúc |

**Không có thứ tự luôn đúng.** Hãy kiểm tra semantics và mục tiêu: bạn muốn bảo vệ dependency khỏi nhiều **attempt**, hay muốn đánh giá tỷ lệ thất bại của những **request logic**? Trong mọi trường hợp cần đo cả hai và giữ deadline/quotas xuyên suốt.

## 18. Bulkhead: cô lập vùng lỗi

**Bulkhead** là chia tài nguyên thành các khoang, để một dependency hoặc nhóm request bị lỗi không tiêu thụ hết tài nguyên của các chức năng khác.

### Ví dụ một API có ba dependency

~~~text
                 API Service
             /        |        \
            v         v         v
       Payment      Search      Reporting
        pool         pool         pool
       20 slots     80 slots     10 slots
          |            |            |
       Payment DB    Search svc   Analytics DB
~~~

Số slot là ví dụ. Nếu reporting chậm, **reporting pool** có thể đầy và từ chối nhanh request báo cáo, thay vì chiếm hết worker khiến **payment hoặc search** cũng ngừng.

### Bulkhead bổ trợ breaker thế nào?

- **Breaker** giảm lời gọi tới dependency đã xác định là không khỏe.
- **Bulkhead** giới hạn mức tài nguyên dependency đó được phép chiếm **ngay cả khi breaker còn CLOSED**.
- **Rate limit** giới hạn tốc độ request theo caller/operation.
- **Queue limit** tránh hàng chờ tăng vô hạn.
- **Timeout** giúp trả lại tài nguyên đã cấp sau một khoảng chờ.

Không nên đặt queue capacity rất lớn để “hạn chế lỗi 503” khi service không có đủ throughput. **Queueing kéo dài có thể khiến mọi request hết deadline trước khi được thực hiện**, còn memory áp lực hơn.

## 19. Load shedding, backpressure và overload protection

Khi tài nguyên đã gần cạn, **load shedding** chủ động từ chối một số request để phần được phục vụ còn đáp ứng SLO. **Backpressure** cho phép một thành phần báo cho phía gửi biết nó không thể nhận thêm dữ liệu nhanh như trước.

| Cơ chế | Lớp sử dụng | Ví dụ |
|---|---|---|
| **Rate limiting** | Gateway/app | Hạn số request/phút theo tenant và method |
| **Concurrency cap** | Ingress/service | Giới hạn in-flight RPC theo operation |
| **Load shedding** | Gateway/backend | Trả lỗi quá tải có cấu trúc, không xếp hàng vô hạn |
| **Backpressure** | Stream/queue/broker | Chỉ nhận dữ liệu theo tốc độ xử lý |
| **Circuit breaker** | Client/upstream | Từ chối nhanh khi dependency đang lỗi |
| **Bulkhead** | Service/resource pool | Tách slot cho luồng quan trọng |

### Phản hồi lỗi có điều khiển

HTTP **429** thường thể hiện vượt hạn mức phía client; **503** thường thể hiện dịch vụ chưa sẵn sàng/quá tải. Với gRPC, **RESOURCE_EXHAUSTED** hoặc **UNAVAILABLE** có thể được dùng theo semantics và hợp đồng API. Không nên đổi mọi lỗi thành **500** vì client không phân biệt được nên retry hay dừng.

**Thống nhất retry policy với tín hiệu overload.** Nếu server trả 429/503 để giảm tải nhưng SDK lập tức retry nhiều lần, chính sách bảo vệ có thể bị vô hiệu hóa trên thực tế.

## 20. Fallback: chỉ dùng khi an toàn về quyền và dữ liệu

Fallback có thể là phục vụ từ cache, trả dữ liệu đọc-only đã có, chuyển sang vùng dự phòng hoặc tạm ẩn chức năng không trọng yếu. Nhưng **trả một kết quả mặc định** không phải lúc nào cũng đúng.

### Ví dụ fallback có điều kiện

| Chức năng | Phương án có thể phù hợp | Trường hợp không nên |
|---|---|---|
| Danh sách sản phẩm công khai | Cache có TTL và độ mới phù hợp | Cache có dữ liệu riêng tư không theo tenant |
| Gợi ý nội dung | Bỏ qua gợi ý, giữ trang chính | Tự suy quyền truy cập từ kết quả gợi ý |
| Trạng thái hàng tồn | Hiển thị dữ liệu cũ có nhãn nếu nghiệp vụ cho phép | Dùng tồn kho cũ để xác nhận đặt hàng không kiểm chứng |
| Phê duyệt giao dịch | Từ chối/đưa vào trạng thái pending an toàn | Tự động chấp nhận khi service kiểm tra quyền lỗi |
| Xác thực/phân quyền | **Fail closed** theo chính sách rủi ro | Cho phép truy cập vì identity service không trả lời |
| Hệ thống analytics | Queue/defer công việc có kiểm soát | Lưu payload vô hạn hoặc mất audit |

### Rủi ro security đặc biệt

Nếu dependency xác thực/authorization bị lỗi, fallback “allow by default” có thể biến **availability problem thành unauthorized access**. Với chức năng nhạy cảm, ưu tiên **fail closed** hoặc workflow khôi phục được kiểm soát. Nếu hệ thống có quyết định authorization được cache, phải xác định **TTL, phạm vi identity/resource, revocation behavior và rủi ro dùng quyền cũ**.

**Fallback phải có hợp đồng dữ liệu rõ**: nguồn, tuổi dữ liệu, tenant, quyền, mức độ hoàn chỉnh và cách báo user. Không bao giờ trả kết quả của tenant khác chỉ để tránh HTTP/gRPC error.

## 21. Timeout và circuit breaker trong VPN/hybrid cloud

Hệ thống hybrid có thể gặp những thời gian khôi phục khác biệt khi route, BGP và VPN thay đổi. Ví dụ on-prem app gọi database hoặc identity API ở cloud qua hai tunnel:

~~~text
On-prem App -> FW -> VPN Tunnel A -> Cloud Hub -> Auth API
                       ||
                 VPN Tunnel B
                       ||
             Backup path khi A lỗi
~~~

### Khi tunnel A mất

1. Monitoring nhận tín hiệu link/SA/BGP của đường A.
2. Route/FIB thay đổi sang đường B, có thể cần thời gian hội tụ.
3. Một số connection TCP/TLS có thể bị reset/timeout hoặc có return path khác.
4. Client library có thể mở lại connection qua đường mới.
5. Nếu breaker OPEN quá lâu trên **cả service**, dù B đã khỏe, recovery có thể chậm thêm.

### Câu hỏi thiết kế

- Circuit breaker theo **service logic** hay theo **endpoint/gateway/region**?
- Có **health-based routing** để tránh node/tunnel lỗi trước khi breaker mở?
- Per-attempt timeout có đủ ngắn để không giữ request quá SLO, nhưng đủ dài cho failover được dự kiến?
- Session state của firewall, NAT và TLS có hỗ trợ đường đi mới không?
- Khi retry, có **connection reuse stale hoặc DNS cache** khiến client tiếp tục dùng endpoint không khỏe?
- Một đường dự phòng có cùng trust/TLS/ACL với đường chính hay không?

**Circuit breaker không tự sửa định tuyến hoặc VPN SA.** Nó chỉ giúp kiểm soát mức lời gọi; root cause vẫn cần điều tra network path, DNS, TLS và application behavior.

## 22. Tương tác với DNS, service discovery và health checks

Một dịch vụ có nhiều địa chỉ IP/backend. Nếu client chỉ giữ một connection tới node cũ hoặc DNS cache chưa cập nhật, thời gian chờ có thể tăng dù các node khác vẫn khỏe.

| Thành phần | Lỗi thường gặp | Biện pháp |
|---|---|---|
| **DNS resolver** | Timeout, NXDOMAIN/SERVFAIL, cached stale records | Metrics theo resolver, TTL, discovery policy |
| **Client connection pool** | Reuse socket cũ, không thay endpoint | Max connection age/idle, error handling theo SDK |
| **Load balancer** | Health check chỉ TCP OK trong khi app chậm | Health check phản ánh readiness đúng, không quá tốn tài nguyên |
| **Service discovery** | Node đã rút nhưng client còn kết nối | Deregistration, draining và endpoint update |
| **Circuit breaker** | OPEN toàn service vì chỉ một node lỗi | Scope theo failure domain và route alternatives |
| **Health probe** | Probe quá nhiều hoặc quá ít | Giới hạn tần suất, phân biệt liveness/readiness |

### Liveness khác readiness

- **Liveness:** quá trình còn hoạt động theo một nghĩa nhất định.
- **Readiness:** instance có sẵn sàng nhận **traffic mới** theo chính sách không.
- **Dependency health:** các dịch vụ phụ thuộc cần thiết cho request có ở trạng thái phục vụ không.

Nếu một readiness check gọi toàn bộ dependency theo cách **vừa tốn tải vừa phụ thuộc lẫn nhau**, sự cố một dependency có thể làm tất cả instance bị loại khỏi load balancer và gây hiệu ứng domino. Thiết kế health check phải cân bằng phạm vi và tần suất; đôi khi nên đánh giá **degraded mode** thay vì loại bỏ toàn bộ instance.

## 23. HTTP/2/gRPC multiplexing và giới hạn theo stream

Một kết nối HTTP/2 có thể đồng thời mang nhiều gRPC stream. Vì vậy:

- **Connection idle timeout** không thay **per-RPC deadline**.
- **HTTP/2 SETTINGS_MAX_CONCURRENT_STREAMS** không tự giới hạn mọi backend job/DB query khi đã có request đang chạy.
- **GOAWAY** giúp đóng kết nối có trật tự theo ngữ nghĩa giao thức, nhưng không chứng minh RPC đã xử lý thành công.
- **RST_STREAM/cancellation** cần được backend xử lý để tránh làm việc tiếp sau khi client bỏ chờ.
- **Flow control** hạn dữ liệu trên stream/connection, nhưng không tự ngăn header/CPU/DB exhaustion.

### Timeout cho streaming

| Kiểu RPC | Chính sách nên phân biệt |
|---|---|
| **Unary** | Total deadline, per-attempt timeout, retry theo idempotency |
| **Server streaming** | Time to first message, stream idle, total duration/bytes, cancellation |
| **Client streaming** | Client write timeout, per-message limit, tổng message/bytes, backpressure |
| **Bidirectional streaming** | Heartbeats/keepalive, idle policy, connection/stream lifetime và quyền theo message |

**Không dùng một deadline ngắn như unary cho mọi stream đã được thiết kế hoạt động lâu**, nhưng cũng không cho phép stream vô hạn không có giới hạn resource/identity. Nếu liveness của stream dựa vào keepalive PING, phải hiểu **quy định server/proxy** để tránh tự tạo quá nhiều ping hoặc bị disconnect.

### HTTP/3/QUIC

Một số API qua HTTP/3 chạy trên QUIC/UDP, không dùng TCP connect theo nghĩa thông thường. **Handshake, idle timeout, stream cancellation và connection migration** có semantics riêng. Không sao chép thông số TCP timeout sang QUIC mà không kiểm tra SDK/gateway và đường mạng.

## 24. Security boundaries: timeout không được trở thành đường bỏ qua chính sách

Khi identity service, WAF, NAC hoặc policy engine bị chậm, tổ chức có thể bị cám dỗ “tạm cho phép” để người dùng không gặp 503. Đây là điểm rủi ro cao vì timeout là **lỗi availability**, không phải quyết định **authorization allow**.

### Ma trận fail-open và fail-closed theo tình huống

| Dependency | Khi không có kết quả trong deadline | Nguyên tắc bảo mật |
|---|---|---|
| **Authentication provider** | Không xác định được danh tính mới | Không cấp phiên/role mới khi chưa xác thực |
| **Authorization policy engine** | Không kiểm tra được quyền đối tượng nhạy cảm | Từ chối hoặc chuyển sang quy trình đã được phê duyệt |
| **Non-critical recommendations** | Không có dữ liệu gợi ý | Bỏ qua tính năng phụ để phục vụ phần chính |
| **Metrics/export service** | Không gửi được telemetry tức thời | Queue có giới hạn và log phù hợp, không làm mất kiểm soát truy cập |
| **Fraud/risk engine** | Không thể đánh giá giao dịch | Policy theo mức rủi ro, có thể pending/reject thay vì tự động approve |
| **Public read-only cache** | Upstream không khỏe | Cache với freshness/tenant policy phù hợp |

**Không thể đưa ra một câu “mọi timeout đều fail closed” cho mọi chức năng**: một dịch vụ hiển thị tin tức công khai có thể dùng cache an toàn. Nhưng **đối với hành động đòi xác thực/phân quyền**, không biến lỗi timeout thành bằng chứng được phép.

### Timeout và audit logging

Nếu log/telemetry backend không sẵn sàng, hệ thống vẫn cần hành vi **theo chính sách lưu dấu**. Với thao tác có yêu cầu audit bắt buộc, phải xác định liệu hệ thống sẽ chặn, ghi vào buffer bền vững hay thực hiện phương án khác được kiểm soát. Không để một fallback âm thầm bỏ qua audit pháp lý hoặc lưu trữ dữ liệu nhạy cảm vô hạn.

## 25. Logging và tracing cần có để điều tra

Một thông báo **“request timeout”** không đủ để xác định nơi lỗi. Cần thu các mốc thời gian và quan hệ nhân quả qua nhiều hop.

### Mẫu log đã che dữ liệu

~~~text
time=2026-11-28T12:00:00+07:00
environment=staging
trace_id=example-trace-001
service=checkout-api
dependency=inventory-api
operation=GetInventory
caller_identity=service-checkout
method=inventory.v1.InventoryService/GetInventory
deadline_remaining_ms_at_start=680
connection_pool_wait_ms=8
dns_ms=0
connect_ms=0
tls_handshake_ms=0
attempt_number=2
attempt_timeout_ms=250
call_duration_ms=254
grpc_status=DEADLINE_EXCEEDED
circuit_state_before=CLOSED
circuit_state_after=CLOSED
retry_decision=NO_BUDGET
fallback=NOT_USED
authentication_result=VERIFIED
authorization_token=[REDACTED]
~~~

Số **0** ở dns/connect/tls trong ví dụ có thể phản ánh **connection reuse** hoặc không có phép đo riêng; thực tế nên phân biệt **NOT_APPLICABLE/NOT_OBSERVED** với **đã đo bằng 0 ms** để không diễn giải sai.

### Trường telemetry quan trọng

| Trường | Lý do |
|---|---|
| **Trace/request ID** | Liên hệ client → gateway → service → dependency |
| **Source/caller identity** | Phân biệt lỗi theo service/tenant/role, không lưu secret |
| **Target endpoint/zone** | Biết một node/region/VRF nào đang lỗi |
| **Attempt number** | Nhận biết retry amplification |
| **Original deadline / remaining** | Biết request có thể hoàn thành trong budget không |
| **DNS/connect/TLS/pool/queue latency** | Định vị điểm nghẽn |
| **HTTP status/gRPC status** | Phân biệt transport và nghiệp vụ |
| **Circuit state/rejection reason** | Không nhầm breaker OPEN với network timeout |
| **Rate/bulkhead limit** | Phân biệt quota và lỗi dependency |
| **Fallback type/cache age** | Kiểm tra tính an toàn/cập nhật của dữ liệu phục hồi |

### Bảo vệ dữ liệu trong logs

Không ghi **Authorization, Cookie, API key, private key, request payload nhạy cảm, thông tin cá nhân ngoài mục đích**. Một trace ID do client tự gửi cũng không phải bằng chứng danh tính. Cần **source redaction, RBAC, retention và audit** khi truy cập log/trace.

## 26. Metrics và cảnh báo cho timeout/circuit breaker

| Chỉ số | Điều giúp hiểu | Bẫy diễn giải |
|---|---|---|
| **Request success/error rate** | Lời gọi nghiệp vụ hoàn thành hay không | HTTP 200 có thể đi cùng gRPC status lỗi |
| **p50/p95/p99 latency** | Trải nghiệm theo phân vị, độ dài đuôi | p99 của ít mẫu có thể thiếu ổn định |
| **Timeout rate theo loại** | Connect, pool, TLS, read, total deadline | Gộp mọi timeout sẽ che nguyên nhân |
| **Circuit state transitions** | OPEN/HALF_OPEN/CLOSED và số lần chuyển | Nhiều OPEN không tự là tấn công |
| **Circuit short-circuit count** | Request được từ chối trước khi gọi dependency | Có thể là bảo vệ hữu ích nhưng làm tăng lỗi user-facing |
| **Dependency failure/slow-call rate** | Dữ liệu ra quyết định breaker | Cần đúng failure classifier |
| **Half-open probe success** | Tình trạng recovery | Một probe thành công có thể chưa đủ |
| **Retry attempts per original request** | Nhận ra retry amplification | Nếu chỉ nhìn request count từ gateway có thể bỏ tầng dưới |
| **Bulkhead occupancy/queue depth** | Khả năng cạn worker/DB pool | Queue lớn không có nghĩa throughput cao |
| **Fallback response rate** | Tần suất dùng dữ liệu/đường thay thế | Có thể che một dịch vụ đang hỏng nếu không có alert |
| **Cancellation cleanup** | Tài nguyên được trả lại sau timeout/cancel | Client timeout vẫn có thể để backend tiếp tục chạy |
| **Network path health** | DNS, VPN, routing, TLS, LB | Không thay synthetic transaction |

### Một cảnh báo mẫu

~~~text
ALERT: DEPENDENCY_CIRCUIT_OPEN
Environment: production
Service: checkout-api
Dependency: inventory-api / region-b
Circuit state: OPEN
Failure rate / window: 65% / last 60s
Minimum calls: satisfied
Primary errors: DEADLINE_EXCEEDED + UNAVAILABLE
Short-circuited calls: increasing
Observed p99: above dependency SLO
Fallback: available only for public read-only inventory summary
Business impact: checkout errors increased
Change window: deployment in region-b 5 minutes ago
Owner: inventory on-call
Next action: inspect network/app/DB and recovery probes
~~~

Không hardcode “mọi breaker OPEN là SEV1”. Đánh giá theo **dịch vụ quan trọng, số người dùng bị ảnh hưởng, đường dự phòng, tác động giao dịch và khả năng fallback**.

## 27. Quy trình triage sự cố: từ timeout đến root cause

Khi error rate tăng, đừng bắt đầu bằng hành động **tăng timeout** hoặc **vô hiệu hóa breaker**. Cần phân biệt **sự cố network thật**, **quá tải trong ứng dụng**, **policy giới hạn quá chặt** và **circuit breaker đang từ chối hợp lý**.

### Giai đoạn 1 — Xác định phạm vi

1. Ghi **thời điểm, môi trường, nguồn, service/method, dependency, region và trace ID**.
2. Xem lỗi chủ đạo là **connect timeout, deadline exceeded, pool acquire timeout, TLS failure, 429/503, circuit rejected** hay lỗi nghiệp vụ.
3. Đo **phạm vi ảnh hưởng**: một tenant, một AZ/region, một upstream, một client SDK hay toàn bộ API.
4. Kiểm tra thay đổi gần đây ở **deploy, routing, firewall, VPN, certificate, DNS, proxy và config timeout**.
5. Xác nhận synthetic test và giao dịch người dùng, không chỉ tunnel hoặc pod status.

### Giai đoạn 2 — Chẩn đoán theo lớp

~~~text
Request fail / timeout
          |
          +-- Không resolve hostname?
          |       -> DNS, resolver, split-horizon
          |
          +-- TCP/TLS không hoàn tất?
          |       -> route, firewall, VPN, cert/SNI, path
          |
          +-- Pool acquire timeout?
          |       -> pool occupancy, leaks, in-flight calls
          |
          +-- Gateway queue/503?
          |       -> capacity, overload, rate/bulkhead policy
          |
          +-- Circuit OPEN?
          |       -> failure classifier, window, upstream health
          |
          +-- Backend slow?
          |       -> DB locks, external API, CPU, fan-out, queue
          |
          +-- Client deadline?
                  -> remaining budget, retry amplification,
                     cancellation and backend work
~~~

### Giai đoạn 3 — Kiềm chế

- Nếu nguồn gây tải bất thường được xác minh, dùng **rate limit/quotas có mục tiêu và đúng principal**, tránh chặn IP chung của nhiều người dùng.
- Nếu lỗi đến từ deployment, dùng **canary rollback** hoặc chuyển tải tới vùng khỏe theo change đã phê duyệt.
- Nếu retry storm, giảm retry attempts/budget bằng cấu hình an toàn, giữ latency SLO và tránh resend thao tác ghi.
- Nếu breaker quá rộng, chỉ chỉnh scope/threshold theo bằng chứng và kiểm thử; không tắt mọi breaker cùng lúc.
- Nếu network path đổi qua VPN/firewall, xử lý đúng route/SA/ACL và đường về; không dùng Allow Any–Any.
- Nếu authorization provider lỗi, đảm bảo **không fail-open trái chính sách** để phục hồi chức năng.

### Giai đoạn 4 — Xác nhận khôi phục

1. Dependency thật sự phản hồi đúng, không chỉ socket CONNECT thành công.
2. Breaker từ HALF_OPEN về CLOSED theo chính sách; số short-circuit giảm.
3. Retry attempts/queue/in-flight calls hồi phục về baseline.
4. User-facing p95/p99 và error rate về mức SLO.
5. Authentication/authorization, tenant isolation và audit logging vẫn có hiệu lực.
6. Giao dịch ghi **không bị lặp hoặc sai trạng thái** do retry trong thời gian sự cố.
7. Bổ sung test để phát hiện sớm cùng loại lỗi ở lần tiếp theo.

## 28. Case study 1: lỗi DNS làm circuit breaker của API OPEN

**Bối cảnh giả định:** Một dịch vụ đặt hàng trên cloud gọi **inventory-api.internal.example.test**. Sau khi cấu hình resolver thay đổi, DNS lookups tại một nhóm pod bắt đầu timeout. Client SDK phân loại mọi exception là server failure; tỷ lệ lỗi vượt 50%, breaker OPEN và trả **UNAVAILABLE** cho mọi request.

### Bằng chứng ban đầu

~~~text
Service: order-api
Dependency: inventory-api
Affected zone: cluster-prod / zone-b
Application error: UNAVAILABLE
Underlying error: DNS resolution timeout
Circuit status: OPEN
Recent change: DNS forwarding policy update
Affected traffic: requests from zone-b
Unaffected traffic: same API from zone-a
~~~

### Các giả thuyết

1. Resolver timeout hoặc forwarding loop sau change.
2. Network policy/egress firewall chặn truy cập DNS.
3. Endpoint inventory-api thực tế đã rút nhưng client giữ DNS cache cũ.
4. Application connection pool hoặc TLS lỗi nhưng bị ghi chung “DNS error”.
5. Breaker scope dùng chung nhiều zone khiến vùng không bị lỗi cũng bị từ chối.

### Điều tra có hệ thống

1. Tách **DNS resolve latency/error** khỏi TCP connect và application response.
2. Đối chiếu resolver configuration, TTL, pod network policy và firewall DNS egress của **zone-b**.
3. Kiểm tra address result và reachability tới endpoint **được phép**, chỉ dùng phép thử không phá hoại.
4. Xem circuit breaker key/scope: theo **service**, **zone**, **endpoint** hay global?
5. Khôi phục DNS policy đúng qua change control, xác minh các pod resolve được tên và gọi API thành công.
6. Quan sát HALF_OPEN probes/transition và alerting sau khi route/DNS hồi phục.
7. Bổ sung monitor **DNS availability và circuit rejected**, tránh chỉ theo dõi gRPC status.

**Kết luận đúng trước khi có bằng chứng:** “Circuit breaker OPEN do tỷ lệ lỗi từ client, trong đó nhiều lỗi liên quan DNS; root cause cần xác minh.” Breaker đang làm đúng việc giới hạn lời gọi nhưng **không phải nguyên nhân gốc của sự cố DNS**.

## 29. Case study 2: retry storm khi database chậm

**Bối cảnh giả định:** API thanh toán gọi một service ledger qua mTLS. Database bắt đầu chậm do transaction lock. Gateway có retry mặc định, service client cũng retry, và một job nền gọi lại request sau timeout mà không có idempotency key. CPU/database pool tăng; một số giao dịch thành công nhưng client báo thất bại rồi lặp lại.

~~~text
Original user requests:         100 / minute
Attempts from app to ledger:    260 / minute
Ledger DB pool occupancy:       high
HTTP/gRPC client timeouts:      increasing
Ledger writes:                 some completed after client timeout
Idempotency key:               not consistently present
Circuit state:                 CLOSED -> OPEN -> HALF_OPEN
Business risk:                 duplicate processing
~~~

### Những rủi ro đồng thời

- **Availability:** DB càng chậm vì thêm attempts.
- **Integrity:** transaction có thể được thực hiện nhiều lần nếu nghiệp vụ không bảo vệ idempotency.
- **Observability:** user-facing timeout không phản ánh trạng thái commit.
- **Security:** vội tắt policy hoặc mở quyền để “giảm lỗi” có thể làm rộng phạm vi truy cập không cần thiết.

### Hướng xử lý phù hợp

1. **Tạm dừng hoặc giới hạn retry** trên đường ghi không idempotent theo quy trình khẩn cấp.
2. Tìm dấu vết **transaction ID/idempotency key**, kiểm tra thực tế DB commit trước khi quyết định thử lại.
3. Giữ deadline và bounded queues để tránh backlog tăng vô hạn.
4. Kiểm tra nguồn lock, connection pool và slow queries; xử lý root cause DB theo owner.
5. Tách breaker cho ledger writes khỏi read-only lookup nếu semantics và fault domain cho phép.
6. Thực thi **idempotency/deduplication** ở tầng ứng dụng, không chỉ SDK retry config.
7. Khôi phục có giới hạn, theo dõi retries, duplicate detection, ledger consistency và user impact.

**Bài học:** **Timeout + retry thiếu idempotency** có thể biến lỗi availability thành lỗi toàn vẹn dữ liệu. Một circuit breaker chỉ làm giảm lưu lượng trong một giai đoạn; nó không đảm bảo các transaction đã gửi trước đó được hủy.

## 30. Case study 3: failover VPN nhưng circuit breaker không khôi phục

**Bối cảnh giả định:** API on-prem gọi một dịch vụ ở cloud qua hai IPsec tunnels. Tunnel A gặp lỗi, định tuyến chuyển sang B. Metrics gateway cho biết tunnel B UP, nhưng API tiếp tục trả lỗi nhanh vì breaker global đang OPEN và chưa thăm dò thành công. Một số client giữ connection cũ nên tiếp tục gặp reset.

### Các lớp cần xác minh

| Lớp | Câu hỏi |
|---|---|
| **IPsec/BGP** | Tunnel B có SA, route và đường về phù hợp chưa? |
| **Firewall/NAT** | Session state và NAT có chuyển/được tái tạo đúng? |
| **DNS/service discovery** | Client có tiếp tục dùng địa chỉ/node cũ không? |
| **Connection pool** | Socket stale có được làm mới khi gặp reset không? |
| **Circuit breaker** | OPEN wait/half-open probes và phạm vi của breaker là gì? |
| **Application** | Một RPC được phép qua B có hoàn tất nghiệp vụ không? |
| **Security** | B có tuân thủ TLS/mTLS, ACL và IDS inspection như A không? |

### Quy trình đề xuất

1. Đo end-to-end path từ đúng nguồn được cấp phép và log **VPN/BGP/FIB**.
2. Xác nhận **mTLS handshake và RPC thực** qua đường B.
3. Xem thời điểm breaker mở, half-open thử lại và vì sao probe thất bại.
4. Kiểm tra stale sockets/connection age và SDK reconnect logic.
5. Nếu mọi lớp cần thiết đã phục hồi, breaker sẽ chuyển theo policy; chỉ can thiệp thủ công theo runbook được phê duyệt.
6. Test lại chiều về, failback, policy lọc route, audit và trạng thái người dùng.

**Tunnel B UP không chứng minh ứng dụng khỏe**; ngược lại **breaker OPEN không chứng minh đường B còn lỗi** nếu chính sách chưa cho phép thăm dò.

## 31. Bài thực hành an toàn: quan sát thời gian kết nối

Bài lab **không tạo tải hoặc cố ý gây sự cố production**. Người học sử dụng một endpoint **staging/health/read-only** do chủ dịch vụ cung cấp để đo time-to-connect, time-to-first-byte và total request time theo khả năng công cụ.

### 31.1. Quan sát với curl

~~~bash
# Thay FQDN bằng endpoint staging được phép.
# Lệnh minh họa chỉ tạo một request GET đọc dữ liệu.
curl --connect-timeout 2 --max-time 5 \
  --output /dev/null \
  --silent --show-error \
  --write-out 'dns=%{time_namelookup} connect=%{time_connect} tls=%{time_appconnect} first_byte=%{time_starttransfer} total=%{time_total}\n' \
  https://api.example.test/health
~~~

**Các chỉ số thời gian ở curl thường là mốc tích lũy tính từ lúc bắt đầu transfer**, không phải tất cả là thời lượng độc lập để cộng trực tiếp. Ví dụ **time_appconnect** là thời gian tính tới hoàn thành kết nối ứng dụng/TLS trong điều kiện thích hợp; **time_starttransfer** tới byte đầu. Muốn tính chi phí mỗi pha, phải hiểu định nghĩa metric và lấy **chênh lệch mốc phù hợp**, đồng thời xem trường hợp connection reuse/proxy/TLS khác nhau.

**--connect-timeout không thay --max-time.** Tùy phiên bản curl, connect timeout có thể tính những pha kết nối như DNS/TCP/TLS theo định nghĩa của công cụ; hãy kiểm tra tài liệu phiên bản trước khi suy đây là TCP SYN timeout thuần. Giá trị **2 và 5 giây** chỉ minh họa cho lab; không dùng một cách máy móc trên mọi endpoint.

### 31.2. Quan sát TLS/ALPN nếu phù hợp

~~~bash
openssl version
openssl s_client \
  -connect api.example.test:443 \
  -servername api.example.test \
  -verify_hostname api.example.test \
  -verify_return_error \
  -alpn h2 \
  -brief
~~~

Phép thử OpenSSL kiểm tra **TLS connection và identity theo trust store hiện hành**, **không chứng minh** rằng một RPC gRPC hoặc backend operation đã hoàn tất trước deadline.

### 31.3. Diễn tập circuit breaker trên mock dependency

Lập một mock service **được kiểm soát trong staging** có khả năng trả kết quả thành công hoặc lỗi theo tình huống định nghĩa, không thay đổi tài sản thật.

~~~text
Mock dependency:
  Mode A: trả kết quả thành công bình thường
  Mode B: trả lỗi 503 theo một kịch bản thử đã giới hạn
  Mode C: trả kết quả trễ hơn per-attempt timeout thử nghiệm
  Mode D: phục hồi thành công

Test sequence:
  1. Xác nhận CLOSED khi dependency khỏe.
  2. Tạo đúng số lời gọi lab được phê duyệt để kiểm tra classifier.
  3. Xác nhận OPEN khi điều kiện thử đạt ngưỡng.
  4. Quan sát short-circuit không làm tăng tải mock.
  5. Cho phép HALF_OPEN với ít probes.
  6. Xác minh CLOSED sau đủ bằng chứng recovery.
  7. Đo retry count, deadline, cleanup và false blocks.
~~~

Đây là **kịch bản lab có giới hạn**, không phải hướng dẫn tạo overload hoặc phá dịch vụ. Một môi trường staging có thể dùng **fake clock, stubbed responses và unit tests** để xác minh state machine mà không cần chờ thời gian thực hoặc gửi nhiều request.

### 31.4. Phiếu ghi kết quả

~~~text
Lab ID:                   API-RESILIENCE-01
Environment:              staging / isolated lab
Date/timezone:            [timestamp]
Requester/approver:       [owner]
Source/client:            [authorized test principal]
Destination/method:       [approved FQDN/RPC]
Network path:             [DNS/VPN/gateway/service]
Client library/version:   [curl/SDK/framework]
Deadline budget:          [ms]
Connect/TLS timeout:      [ms]
Per-attempt timeout:      [ms]
Retry limit/budget:       [attempts or quota]
Circuit scope:            [dependency/method/region]
Breaker policy:           [window, min calls, thresholds]
Before state:             [CLOSED/OPEN/HALF_OPEN]
Observed error:           [status and layer]
Attempts actually made:   [count]
Resources/latency:        [metrics]
After state:              [state]
Expected authorization:   [allow/deny]
Observed outcome:         [result]
Verdict:                  [PASS/FAIL/INCONCLUSIVE]
Evidence/change record:   [approved logs, no secrets]
~~~

**INCONCLUSIVE** phù hợp khi thiếu log phân loại lỗi, không biết điểm kết thúc timeout, hoặc không thể chứng minh cuộc gọi đã đi qua đường dự kiến.

## 32. Ma trận kiểm thử timeout, breaker và phục hồi

| Test ID | Tình huống có kiểm soát | Kỳ vọng |
|---|---|---|
| **RES-01** | Dependency khỏe, latency dưới budget | Request thành công, breaker CLOSED |
| **RES-02** | DNS không phản hồi trong mock/staging | Báo DNS timeout, không nhầm với TLS trust |
| **RES-03** | TCP connect không hoàn tất tới test endpoint | Connect timeout được nhận diện, tài nguyên dọn đúng |
| **RES-04** | TLS handshake chậm/lỗi trust trong lab | Phân loại đúng, không tắt certificate validation |
| **RES-05** | Connection pool đầy trong staging | Acquire timeout và queue giới hạn, không leak |
| **RES-06** | Backend trả response muộn hơn request deadline | Client dừng chờ; server thực thi cancellation phù hợp |
| **RES-07** | Dependency trả 401/403 theo policy | Không mở breaker vì caller thiếu quyền |
| **RES-08** | 429/quota từ một caller lab | Không retry ồ ạt hoặc đánh đồng dependency outage |
| **RES-09** | 5xx và connect errors vượt ngưỡng breaker | OPEN theo classifier/window đã cấu hình |
| **RES-10** | Một lỗi đơn lẻ khi dưới minimum calls | Không OPEN ngoài policy |
| **RES-11** | Circuit OPEN nhận thêm request | Short-circuit, không tiếp tục gọi dependency |
| **RES-12** | Hết OPEN wait, dependency phục hồi | HALF_OPEN giới hạn probe, CLOSED khi đạt tiêu chí |
| **RES-13** | HALF_OPEN probe thất bại | Trở lại OPEN đúng policy, không xả tải |
| **RES-14** | Nhiều instance cùng recovery | Không có probe stampede vượt tài nguyên đã định |
| **RES-15** | Client deadline còn ít hơn retry delay + attempt | Không thực hiện retry vô ích |
| **RES-16** | Lỗi transient ở thao tác đọc an toàn | Retry có budget/jitter và kết quả đúng |
| **RES-17** | Timeout sau khi thao tác ghi đã commit | Idempotency ngăn xử lý trùng |
| **RES-18** | Một dependency analytics chậm | Bulkhead không làm nghẽn chức năng thanh toán |
| **RES-19** | Queue/service nhận burst trong staging | Load shedding theo quota, không giữ queue vô hạn |
| **RES-20** | Identity/authorization provider không sẵn sàng | Không có fail-open trái policy |
| **RES-21** | Fallback trả cache cho tenant A | Không lộ dữ liệu tenant B, TTL/authorization đúng |
| **RES-22** | Stream gRPC bị client cancel | Backend giải phóng tài nguyên sau cancel |
| **RES-23** | HTTP/2 nhiều RPC trên một connection | Per-stream deadline hoạt động độc lập hợp lý |
| **RES-24** | Connection idle nhưng request nghiệp vụ dài hợp lệ | Không bị ngắt ngoài chính sách đã thiết kế |
| **RES-25** | VPN failover A→B trong môi trường được duyệt | Route, TLS, gRPC, circuit và app phục hồi |
| **RES-26** | Một backend region lỗi, region khác khỏe | Breaker scope không chặn nhầm region khỏe |
| **RES-27** | DNS cache/connection pool còn endpoint cũ | Connection refresh và recovery có kiểm soát |
| **RES-28** | Deploy rolling và connection draining | In-flight request không bị mất không cần thiết, retries an toàn |
| **RES-29** | Log có token giả trong test | Token được redacted, trace/timeout metrics vẫn đủ |
| **RES-30** | Sau thay đổi timeout/breaker | Không regression trên p95/p99, error budget và security controls |

Không chạy tất cả test bằng cách cố ý gây lỗi trên production. Dùng **unit test, fake clock, mock dependency, staging traffic có giới hạn và diễn tập được phê duyệt**. Các trường hợp VPN failover, mất link hoặc backend outage cần bảo đảm **phạm vi, rollback và stop condition**, không làm ảnh hưởng hệ thống khác.

## 33. Những hiểu nhầm và cách khắc phục

| Nhận định sai | Vì sao không đúng | Cách làm phù hợp |
|---|---|---|
| “Connect timeout là tổng thời gian API được phép chạy” | Chỉ giới hạn một số pha của kết nối | Có end-to-end deadline và per-phase metrics |
| “Read timeout luôn là tổng thời gian response” | Có thể chỉ đo thời gian không có byte mới | Xem semantics của client library |
| “Timeout là server đã dừng công việc” | Server/DB có thể vẫn commit hoặc chạy tiếp | Propagate cancellation, idempotency và audit |
| “Tăng timeout sẽ giải quyết backend chậm” | Giữ thêm tài nguyên, có thể tăng queue | Tìm root cause và thiết kế budget |
| “Retry luôn tốt cho availability” | Retry có thể khuếch đại tải và lặp giao dịch | Jitter, retry budget và idempotency |
| “Circuit breaker ngăn mọi request xấu” | Nó đánh giá sức khỏe dependency, không phải phân quyền | Authentication/authorization riêng |
| “Breaker OPEN nghĩa dependency đang hỏng ở thời điểm này” | Có thể chưa thử recovery hoặc scope quá rộng | HALF_OPEN có kiểm soát và health evidence |
| “Một request 401 là dependency failure” | Đó có thể là từ chối truy cập đúng policy | Phân loại lỗi caller và downstream |
| “429 cũng cần retry lập tức để tăng tỉ lệ thành công” | 429 là tín hiệu hạn mức/quá tải | Respect backoff/Retry-After khi phù hợp |
| “Một timeout chung 30 giây cho tất cả hop là đơn giản nhất” | Không đảm bảo tổng deadline và SLO | Budget theo đường đi và operation |
| “Connection pool càng lớn càng nhanh” | Có thể làm DB/backend chịu tải vượt khả năng | Bulkhead/pool sizing theo benchmark |
| “Queue lớn giúp giảm mất request” | Request có thể hết hạn trước khi tới worker | Bounded queue, load shedding |
| “HALF_OPEN cho phép toàn bộ traffic thử lại” | Có thể làm backend vừa phục hồi quá tải | Probe concurrency cap |
| “Fallback cho phép mặc định khi auth service lỗi” | Có thể tạo truy cập trái phép | Fail closed/approved degraded mode |
| “Cache stale là an toàn cho mọi API” | Dữ liệu nhạy cảm, tenant hoặc transaction có thể sai | TTL, authorization và tính nhất quán |
| “VPN tunnel UP là request end-to-end khỏe” | Route, firewall state, DNS và TLS có thể lỗi | Synthetic application probes |
| “HTTP/2 một connection = một RPC” | Multiplex nhiều streams | Đo in-flight streams/RPC và per-stream deadline |
| “Circuit breaker là thay thế firewall/WAF/IDS” | Không kiểm tra identity hay nội dung tấn công | Defense-in-depth |
| “Mọi CANCELLED/DEADLINE_EXCEEDED là DDoS” | Client chủ động hủy, latency hoặc policy có thể bình thường | Xem baseline, nguồn và tác động |
| “Một probe TCP thành công nghĩa dependency đã phục hồi” | Ứng dụng/DB có thể còn lỗi | Kiểm thử RPC/transaction thật |
| “Chỉnh breaker OPEN để giảm lỗi user” | Có thể xả tải vào dependency đang suy yếu | Chẩn đoán, canary và rollback |
| “Đóng incident khi breaker CLOSED” | Business transactions có thể còn fail | Kiểm tra SLO, state và security controls |

## 34. Câu hỏi tự kiểm tra

1. Vì sao TCP connect timeout không giới hạn tổng thời gian một API request?
2. Read timeout kiểu idle khác total request timeout thế nào khi server trả dữ liệu nhỏ từng đợt?
3. Deadline của request khác timeout của một attempt như thế nào?
4. Khi client deadline hết, tại sao server vẫn có thể tiếp tục ghi database?
5. Vì sao cần buffer thời gian trong end-to-end budget và không cộng máy móc các nhánh song song?
6. Dependency p99 = 180 ms có đủ để khẳng định timeout 200 ms luôn hợp lý không? Còn cần dữ liệu nào?
7. Những lớp nào có thể gây “timeout” trên đường on-prem → firewall → VPN → cloud API?
8. HTTP/2 multiplexing làm thay đổi nhu cầu đo connection count và stream count như thế nào?
9. CLOSED, OPEN và HALF_OPEN là gì? Khi nào breaker có thể OPEN?
10. Vì sao cần minimum calls cùng failure-rate threshold để tránh false positive?
11. Những loại HTTP status/gRPC status nào thường không nên được tính như lỗi dependency?
12. Circuit breaker per region có lợi gì so với một breaker toàn cục khi một AZ bị lỗi?
13. Một breaker OPEN có chắc chắn chứng minh dependency vẫn hỏng ngay lúc bạn quan sát không?
14. Vì sao cần giới hạn số probes tại HALF_OPEN và backoff khi nhiều replica cùng phục hồi?
15. Nếu client, gateway và backend mỗi tầng thử lại tối đa 3 attempt, số attempt xuống DB có thể tăng đến bao nhiêu theo cấu hình minh họa?
16. Tại sao retry một thao tác thanh toán sau client timeout có thể gây lặp giao dịch?
17. Exponential backoff với jitter giải quyết điều gì mà delay cố định không làm tốt bằng?
18. Bulkhead khác rate limiting, queue limit và circuit breaker như thế nào?
19. Khi nào một fallback cache có thể an toàn và khi nào có nguy cơ lộ dữ liệu tenant khác?
20. Nếu identity/authorization provider timeout, vì sao “allow by default” là giải pháp nguy hiểm?
21. Trong case study lỗi DNS, vì sao breaker OPEN không phải nguyên nhân gốc?
22. Khi VPN failover, cần đo những điều gì để phân biệt SA UP với RPC đã phục hồi?
23. Những trường nào nên có trong một log timeout để xác định đúng pha gây lỗi?
24. Làm sao nhận biết retry amplification nếu chỉ có HTTP/gRPC status ở API gateway?
25. Tại sao phải kiểm tra cả lời gọi hợp lệ và lời gọi không có quyền sau khi chỉnh timeout/breaker?
26. Hãy đề xuất policy khác nhau cho một unary GetInventory và một bidi streaming telemetry.
27. Vì sao không nên dùng health check gọi nhiều dependency nặng trên mỗi lần kiểm tra readiness?
28. Khi sự cố đang xảy ra, bạn sẽ thực hiện những bước nào trước khi tăng timeout hoặc disable breaker?

## 35. Ghi nhớ trọng tâm

**Timeout bảo vệ một thao tác không được chờ quá lâu, còn circuit breaker giảm lời gọi mới tới dependency đang bị đánh giá không khỏe.** Để dùng đúng, cần phân biệt **DNS, TCP connect, TLS handshake, pool acquire, read/write, idle, per-attempt timeout và end-to-end deadline**. Các giới hạn phải xuất phát từ **SLO, phân bố latency, đặc điểm request và thời gian còn lại trong chuỗi hop**, không phải chỉ sao chép một giá trị mặc định.

Circuit breaker hoạt động phổ biến qua **CLOSED → OPEN → HALF_OPEN → CLOSED/OPEN**, dựa trên cửa sổ đo, ngưỡng lỗi, tối thiểu số lời gọi và chính sách thăm dò. **Failure classifier và breaker scope quyết định chất lượng bảo vệ**: không coi 401/403 của caller là lỗi dependency, không làm OPEN toàn region khỏe vì một node lỗi, không xả tải khi mới có một probe thành công. Timeout/breaker cần kết hợp **retry có backoff/jitter và budget, idempotency, cancellation, bulkhead, load shedding, backpressure và fallback có giới hạn**.

Trong mạng doanh nghiệp và hybrid cloud, cần quan sát **DNS, route/VPN, TLS, firewall, HTTP/2/gRPC, API gateway, service mesh, database và giao dịch người dùng** để phân biệt lỗi kết nối với lỗi ứng dụng. Những cơ chế resilience **không thay firewall, mTLS, authentication, authorization hoặc kiểm soát dữ liệu**; đặc biệt không dùng timeout làm lý do mở quyền truy cập khi policy engine không trả lời. Thiết kế tốt có **test matrix có phép, metrics, circuit state transitions, retry amplification, SLO, runbook, rollback và bằng chứng end-to-end** cho cả **request được phép thành công** lẫn **request trái quyền bị từ chối**.
