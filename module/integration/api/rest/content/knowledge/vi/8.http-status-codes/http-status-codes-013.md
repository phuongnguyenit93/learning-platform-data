# 500, 502, 503, 504 theo tầng phát sinh sự cố

Khách hàng gọi một REST API và nhận **HTTP 502 Bad Gateway**. Đội frontend nói API đang lỗi; đội backend xem log của Spring Boot lại thấy request đã xử lý thành công; đội vận hành phát hiện API gateway mất kết nối tới một backend trong lúc triển khai. Ở một tình huống khác, khách nhận **504 Gateway Timeout** nhưng vài giây sau hệ thống vẫn tạo đơn hàng. Nếu tự động gửi lại POST, người dùng có thể bị tạo đơn hoặc thanh toán hai lần.

Các mã **500, 502, 503 và 504** đều thuộc nhóm lỗi máy chủ 5xx, nhưng chúng mô tả **những điều kiện thất bại khác nhau tại thành phần tạo ra HTTP response**. Đọc đúng mã trạng thái giúp thiết kế hợp đồng lỗi, chẩn đoán theo từng tầng, chọn chiến lược retry, đặt timeout và điều tra sự cố không làm mất dữ liệu.

Bài học thuộc chương **Mã trạng thái** của module **INTEGRATION_API_REST**. Người học sẽ vận dụng HTTP Semantics, URI, phương thức HTTP, idempotency, xử lý lỗi chuẩn và Java/Spring để thiết kế API có thể quan sát và phục hồi trước sự cố. Các ví dụ dùng kiến trúc nhiều tầng, nhưng nguyên tắc vẫn áp dụng cho hệ thống nhỏ hoặc triển khai trên nền tảng cloud khác.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích chính xác ý nghĩa của **500 Internal Server Error, 502 Bad Gateway, 503 Service Unavailable và 504 Gateway Timeout** theo HTTP Semantics.
2. Nhận ra mã nào do **origin**, **reverse proxy/load balancer lớp 7**, **API gateway** hoặc **dịch vụ facade** có thể phát sinh.
3. Phân biệt **mã client nhận**, **mã từng hop ghi nhận** và **nguyên nhân gốc** của sự cố.
4. Thiết kế phản hồi lỗi thống nhất với **Problem Details (RFC 9457)**, correlation/trace ID và thông tin retry an toàn.
5. Áp dụng retry/backoff, timeout budget, circuit breaker, idempotency và đối soát cho hệ thống nhiều dịch vụ.
6. Điều tra, kiểm thử và diễn tập các kịch bản 5xx bằng log, metric, trace và ví dụ Java/Spring.

## 2. Nền tảng: 5xx nói về khả năng xử lý request

Nhóm **5xx** thể hiện server nhận thấy mình đã lỗi hoặc không thể thực hiện yêu cầu trong hoàn cảnh hiện tại. Tuy nhiên, **“server” trong HTTP không đồng nghĩa chỉ với một ứng dụng Spring Boot**. Một thành phần trung gian nhận request từ client rồi gửi HTTP response cũng có thể là bên tạo mã 5xx.

Một đường đi phổ biến:

~~~mermaid
flowchart LR
    C["Client / Mobile / Browser"] --> CDN["CDN / WAF"]
    CDN --> GW["API Gateway"]
    GW --> LB["L7 Load Balancer"]
    LB --> API["Spring Boot API"]
    API --> SVC["Internal service"]
    SVC --> DB[("Database")]
    API --> PSP["External payment API"]
~~~

Một request có thể đi qua nhiều kết nối HTTP khác nhau. Ví dụ:

- Client gửi GET tới CDN; CDN gửi một GET khác tới gateway.
- Gateway gửi request tới load balancer; load balancer chuyển tới Spring API.
- Spring API gọi payment API hoặc dịch vụ nội bộ.
- Từng hop có **timeout**, **chính sách retry**, **giới hạn tài nguyên** và **khả năng tạo response** riêng.

Vì vậy, **response cuối cùng không tự xác nhận vị trí của lỗi gốc**. Gateway có thể trả 504 vì chờ Spring quá lâu, nhưng Spring chậm vì database lock. Spring có thể trả 503 do database tạm thời không khả dụng, trong khi gateway chỉ chuyển nguyên mã đó về client.

### 2.1. Định nghĩa chuẩn của bốn mã

| Mã | Tên | Ý nghĩa trọng tâm theo HTTP Semantics |
|---|---|---|
| **500** | Internal Server Error | Server gặp tình trạng bất ngờ khiến không thể hoàn thành request |
| **502** | Bad Gateway | Server **đang đóng vai gateway/proxy** nhận phản hồi không hợp lệ từ upstream (inbound server) khi cố thực hiện request |
| **503** | Service Unavailable | Server hiện không thể xử lý request, thường do quá tải tạm thời hoặc bảo trì theo lịch; có thể thông báo thời gian thử lại |
| **504** | Gateway Timeout | Server **đang đóng vai gateway/proxy** không nhận được phản hồi kịp thời từ upstream cần thiết để thực hiện request |

Theo **RFC 9110, §15.6**, 500 là mô tả chung; 502 và 504 gắn với vai trò gateway/proxy; 503 mô tả tình trạng dịch vụ không thể phục vụ tại thời điểm đó.

**Không suy luận máy móc:** 502 không bắt buộc lỗi nằm ở gateway; nó có thể là gateway đang phản ánh lỗi giao tiếp do upstream. 504 không chắc upstream “chết”; upstream có thể vẫn chạy và hoàn thành công việc sau khi gateway đã ngừng chờ. 503 cũng có thể do chính gateway phát ra khi hết backend khỏe mạnh.

### 2.2. Một request có thể có nhiều mã trạng thái ở các hop

Xét hai tình huống:

~~~text
Tình huống A: origin tự trả lỗi
Client <- 503 <- Gateway <- 503 <- Spring API
Spring API không thể phục vụ vì hết capacity.
Gateway chuyển tiếp response 503 hợp lệ.

Tình huống B: gateway tự tạo lỗi
Client <- 504 <- Gateway     (quá thời gian chờ 10 giây)
                        \
                         Spring API còn xử lý tới giây thứ 18
~~~

Trong tình huống A, client thấy 503 và gateway có thể ghi **upstream_status=503**. Trong tình huống B, gateway ghi **downstream_status=504**, còn upstream có thể không hề gửi status trước khi deadline hết. Tên field phụ thuộc sản phẩm, nên phải đối chiếu ý nghĩa metric/log thực tế.

Nếu upstream trả một **HTTP 500 hợp lệ**, gateway thường có thể chuyển tiếp mã 500 đó. Không nên tự đổi mọi HTTP 500 của upstream thành 502, bởi **502 nói về phản hồi không hợp lệ hoặc sự cố lớp gateway**, không đơn giản là “upstream báo lỗi ứng dụng”.

## 3. HTTP 500 Internal Server Error

### 3.1. Khi nào phù hợp?

**500** thích hợp khi server không thể thực hiện yêu cầu vì một tình trạng **bất ngờ** mà hợp đồng hiện tại chưa có mã cụ thể hơn. Ví dụ tại một Spring application:

- Một invariant nội bộ bị vi phạm, làm luồng xử lý không thể hoàn tất.
- Một exception ngoài dự kiến xuất hiện trong xử lý yêu cầu.
- Lỗi serialization hoặc lỗi logic trong chuyển đổi trạng thái nghiệp vụ.
- Thành phần ứng dụng chạy sai cấu hình dẫn tới lỗi xử lý không được phân loại.

Nếu request sai cú pháp hoặc validation không hợp lệ, nên trả **400** hoặc mã 4xx phù hợp; nếu thiếu xác thực hoặc không được phép, dùng **401/403**; nếu record không tồn tại, thường là **404**. Đừng dùng 500 cho mọi lỗi vì nó khiến client khó phân biệt lỗi có thể sửa ở phía họ với lỗi của dịch vụ.

Nếu nguyên nhân là **quá tải có chủ đích bảo vệ dịch vụ** hoặc **bảo trì**, mã **503** diễn tả tình trạng phù hợp hơn. Nếu server đang đóng vai gateway chờ upstream và quá thời gian, **504** mô tả trực tiếp hơn. Dù vậy, việc ứng dụng xử lý phụ thuộc thất bại không tự buộc nó trả 502/504; còn phải xem **vai trò endpoint** và hợp đồng đối với client.

### 3.2. Phản hồi HTTP minh họa

~~~http
HTTP/1.1 500 Internal Server Error
Content-Type: application/problem+json
Cache-Control: no-store
X-Request-Id: req-8f2b

{
  "type": "https://api.example.test/problems/internal-error",
  "title": "Internal Server Error",
  "status": 500,
  "detail": "The request could not be completed.",
  "instance": "/v1/orders/ord-19",
  "requestId": "req-8f2b"
}
~~~

Client nhận thông báo chung và mã dùng để liên hệ hỗ trợ; log nội bộ giữ stack trace cùng context đã được làm sạch. **Không để lộ** chuỗi kết nối database, địa chỉ nội bộ, stack trace, SQL, access token, dữ liệu thanh toán hoặc PII trong phần **detail** gửi ra ngoài.

### 3.3. Một 500 có thể là triệu chứng của lỗi ở tầng dưới

Spring API ném exception khi một query database lỗi rồi trả 500. Ở góc nhìn HTTP, **Spring tạo 500**. Ở góc nhìn vận hành, **database** hoặc truy vấn là nguồn gây lỗi. Nếu API còn khả năng phân loại tình trạng phụ thuộc “tạm thời không phục vụ được”, có thể chọn 503 theo hợp đồng. Điều quan trọng là ghi đủ thông tin về **dependency failure** để phân biệt code bug với sự cố hạ tầng.

## 4. HTTP 502 Bad Gateway

### 4.1. Vai trò gateway/proxy là điều kiện ngữ nghĩa

**502** mô tả trường hợp thành phần đang làm **gateway hoặc proxy** nhận được phản hồi không hợp lệ từ upstream khi cần hoàn tất request. Ở triển khai thực tế, các gateway thường dùng 502 cho cả những lỗi như kết nối đến upstream bị từ chối, bị reset trước khi đọc được HTTP response, hoặc lỗi TLS/handshake. **Cách phân loại chính xác phụ thuộc sản phẩm**; cần đối chiếu upstream connection error trong log.

Một vài ví dụ:

- Reverse proxy kết nối tới backend qua giao thức/cổng sai, không nhận được HTTP response hợp lệ.
- Upstream gửi HTTP headers sai định dạng hoặc trả dữ liệu không hợp lệ đối với giao thức mong đợi.
- Kết nối giữa L7 gateway và origin bị reset trước khi tạo response có thể sử dụng.
- Cấu hình TLS giữa gateway và upstream không khớp, làm quá trình giao tiếp không tạo được phản hồi hợp lệ.

Sơ đồ ví dụ:

~~~mermaid
sequenceDiagram
    actor C as Client
    participant G as API Gateway
    participant A as Spring API
    C->>G: GET /v1/products/42
    G->>A: GET /v1/products/42
    A--xG: Kết nối reset / phản hồi không hợp lệ
    G-->>C: 502 Bad Gateway
~~~

HTTP response minh họa:

~~~http
HTTP/1.1 502 Bad Gateway
Content-Type: application/problem+json
Cache-Control: no-store
X-Request-Id: req-9bc1

{
  "type": "https://api.example.test/problems/bad-gateway",
  "title": "Bad Gateway",
  "status": 502,
  "detail": "An upstream service returned an invalid response.",
  "requestId": "req-9bc1"
}
~~~

### 4.2. Không đánh đồng 502 với HTTP 500 từ upstream

Hai trường hợp rất khác nhau:

| Trạng thái upstream | Gateway nhận gì? | Hành vi thường phù hợp |
|---|---|---|
| Spring trả **HTTP 500 hợp lệ** | Status, headers và message HTTP có cấu trúc | Thường chuyển tiếp **500** hoặc chuẩn hóa lỗi theo hợp đồng rõ ràng |
| Spring đóng kết nối hoặc trả response malformed | Không có HTTP response upstream hợp lệ | Gateway có thể tự trả **502** |
| Spring trả **HTTP 404 hợp lệ** | Một phản hồi nghiệp vụ hợp lệ | Chuyển **404**; không coi là lỗi gateway |
| Spring trả **HTTP 503 hợp lệ** | Upstream tạm thời không phục vụ | Thường chuyển **503**; không tự động đổi thành 502 |

Một API đóng vai **facade/gateway** trước dịch vụ khác cũng có thể trả 502, nếu thực sự giao tiếp với upstream theo vai trò đó. Nhưng một ứng dụng nghiệp vụ gọi database và gặp lỗi kết nối không nhất thiết là “gateway” chỉ vì có dependency.

### 4.3. Hướng điều tra

Kiểm tra **upstream host/port**, DNS, service discovery, health check, TLS, HTTP protocol version, keep-alive, connection pool và lỗi reset. So sánh log ở gateway và origin bằng trace ID; tìm thời điểm request có đến origin hay không. Nếu origin không ghi nhận request, đừng bắt đầu sửa business logic của controller.

## 5. HTTP 503 Service Unavailable

### 5.1. Tình trạng dịch vụ không phục vụ được ngay lúc đó

**503** thường dùng khi dịch vụ **tạm thời** không xử lý được request do:

- Quá tải: số request đồng thời vượt năng lực hiện có, pool tài nguyên cạn hoặc queue đã đầy.
- Đang bảo trì/đang rút lưu lượng để nâng cấp mà không còn khả năng tiếp nhận.
- Mọi backend mục tiêu không đạt health check, khiến L7 load balancer/gateway không có nơi chuyển tiếp.
- Một dependency cốt lõi bị gián đoạn khiến origin quyết định tạm dừng cung cấp một năng lực, theo hợp đồng đã thiết kế.

Lưu ý **không bắt buộc** sự cố 503 chỉ tồn tại trong thời gian ngắn thực tế: RFC mô tả trạng thái không thể phục vụ, nhưng mã không hứa thời điểm chắc chắn khôi phục. Không áp dụng 503 như lời nói chung cho mọi 5xx vì client có thể dùng nó để quyết định backoff/retry.

### 5.2. Retry-After và giới hạn gửi lại

Server **có thể** đưa ra **Retry-After** cùng 503 để gợi ý thời gian trước khi client thử lại. Giá trị của Retry-After là số giây không âm hoặc HTTP-date:

~~~http
HTTP/1.1 503 Service Unavailable
Retry-After: 30
Content-Type: application/problem+json
Cache-Control: no-store

{
  "type": "https://api.example.test/problems/temporarily-unavailable",
  "title": "Service Unavailable",
  "status": 503,
  "detail": "The service is temporarily unavailable."
}
~~~

Hoặc:

~~~http
Retry-After: Wed, 18 Nov 2026 11:30:00 GMT
~~~

Đó là **chỉ dẫn thử lại** chứ không phải lời cam kết dịch vụ chắc chắn khôi phục. Client cần áp dụng timeout, exponential backoff, jitter, tối đa số lần retry và tôn trọng Retry-After khi hợp lý. Với lệnh ghi, phải biết thao tác có an toàn để retry hay không; mã 503 **không chứng minh rằng yêu cầu trước đó chưa làm thay đổi dữ liệu**.

### 5.3. Phân biệt 503, 429 và 500

| Hiện tượng | Mã thường cân nhắc | Ý nghĩa |
|---|---|---|
| Dịch vụ **toàn cục** bị quá tải hoặc tạm dừng bảo trì | **503** | Dịch vụ hiện không thể phục vụ |
| **Một khách hàng/API key** vượt quota/rate limit đã công bố | **429 Too Many Requests** | Client gửi quá nhiều request trong khoảng thời gian |
| Ứng dụng gặp exception không lường trước | **500** | Không hoàn thành vì lỗi nội bộ |
| Gateway hết backend khỏe mạnh | **503** là một cách phổ biến | Không còn nơi phục vụ request theo cấu hình routing |

Sản phẩm gateway khác nhau có thể trả mã khác cho một tình trạng hạ tầng. Không dùng bảng trên để suy ra thiết bị hoặc lớp cụ thể đã phát mã, mà dùng như cơ sở **thiết kế và đối chiếu log thực tế**.

### 5.4. Readiness, liveness và draining

Trong môi trường container/cluster:

- **Liveness** cho biết tiến trình có cần khởi động lại không.
- **Readiness** cho biết instance có đủ điều kiện nhận lưu lượng mới không.
- **Draining** giúp instance đang nâng cấp hoàn tất hoặc ngừng nhận kết nối mới có kiểm soát.

Health check sai có thể khiến tất cả backend bị đánh dấu không sẵn sàng rồi gateway trả 503. Nếu dependency chậm nhưng ứng dụng vẫn cung cấp được một phần API, không nên dùng một readiness check quá rộng để kéo toàn bộ hệ thống khỏi cân bằng tải khi không cần.

## 6. HTTP 504 Gateway Timeout

### 6.1. Timeout ở vai trò gateway

**504** có nghĩa thành phần đang làm **gateway hoặc proxy** không nhận được phản hồi **kịp thời** từ upstream cần thiết để xử lý request. Ví dụ:

~~~mermaid
sequenceDiagram
    actor C as Client
    participant G as L7 Gateway
    participant A as Spring Orders API
    participant D as Database
    C->>G: POST /v1/orders
    G->>A: POST /v1/orders
    A->>D: Lưu đơn hàng (có thể đã commit)
    Note over G,A: Deadline của gateway: 10 giây
    G-->>C: 504 Gateway Timeout
    D-->>A: DB trả kết quả sau giây 12
    Note over A: API có thể tiếp tục hoặc đã mất đường trả phản hồi
~~~

**504 không đồng nghĩa thao tác nghiệp vụ thất bại.** Nó chỉ cho biết gateway không nhận được phản hồi đúng hạn. Backend có thể tiếp tục xử lý hoặc hoàn tất một giao dịch trước/sau khi client nhận 504. Điều này đặc biệt nguy hiểm với POST đặt hàng, thanh toán hoặc job không idempotent.

Phản hồi minh họa:

~~~http
HTTP/1.1 504 Gateway Timeout
Content-Type: application/problem+json
Cache-Control: no-store
X-Request-Id: req-c813

{
  "type": "https://api.example.test/problems/upstream-timeout",
  "title": "Gateway Timeout",
  "status": 504,
  "detail": "The upstream service did not respond within the required time.",
  "requestId": "req-c813"
}
~~~

### 6.2. Phân biệt 504 với các lỗi timeout khác

| Hiện tượng | Ý nghĩa / mã liên quan |
|---|---|
| Gateway chờ upstream quá thời gian | **504** đúng vai trò gateway/proxy |
| Server không nhận **đầy đủ request từ client** kịp thời | Có thể là **408 Request Timeout** |
| Client chủ động đóng kết nối khi server chưa trả | Một số proxy ghi mã **499**, nhưng đây **không phải mã trạng thái HTTP chuẩn** |
| Ứng dụng chạy quá hạn xử lý nội bộ, không làm gateway | Không tự động trở thành 504; cần phân loại theo contract, thường 500 hoặc 503 nếu dịch vụ tạm không sẵn sàng |
| Upstream trả HTTP 503 nhanh, đúng cấu trúc | **503** do upstream tạo; chưa phải 504 |
| Proxy không hiểu được response upstream | **502** phù hợp hơn timeout 504 |

Các gateway/CDN có thể có **mã mở rộng riêng** cho timeout; xem tài liệu của sản phẩm trước khi quy mọi mã trong log về một mã chuẩn.

### 6.3. Timeout budget: tránh timeout đảo chiều

Giả sử request đi qua gateway → Spring API → ERP. Thiết kế tối thiểu phải có các mốc đo được:

| Thành phần | Deadline ví dụ | Mục đích |
|---|---:|---|
| ERP request từ Spring | **3 giây** | Giới hạn chờ dependency |
| Xử lý tổng tại Spring | **6 giây** | Có thời gian phân loại lỗi, ghi trạng thái và trả response |
| Gateway chờ Spring | **8 giây** | Có biên dự phòng cho kết nối/chuyển tiếp |
| Client chờ response | **10 giây** | Hạn tổng được thiết kế cho trải nghiệm người dùng |

Đây là **số minh họa**, không phải cấu hình chuẩn cho mọi nghiệp vụ. Khi API cần nhiều cuộc gọi, deadline phải tính **đường găng** (critical path), số lần retry, thời gian queue/DB lock, overhead mạng và khả năng hủy công việc. Không thể cộng tùy tiện từng timeout mà vẫn thỏa mục tiêu đầu-cuối.

Nếu **gateway timeout sớm hơn Spring**, client có thể nhận 504 trong lúc Spring tiếp tục commit. Khi request bị hủy, backend **không phải lúc nào cũng rollback** tất cả giao dịch bên ngoài; cần mô hình hóa trạng thái chưa rõ và đối soát.

### 6.4. Hướng điều tra

So sánh **thời điểm bắt đầu request, upstream connect time, time to first byte, tổng thời gian gateway chờ**, cùng trace ở Spring/DB. Tìm xem chậm tại query, connection pool, thread pool, GC, deadlock, external API hay mạng. Một 504 không đủ kết luận “hãy tăng timeout”; tăng timeout có thể che bottleneck và làm cạn thêm tài nguyên.

## 7. Đọc mã 5xx theo tầng phát sinh sự cố

Bảng sau là cách **định hướng điều tra**, không phải ánh xạ tuyệt đối từ một mã sang một máy chủ:

| Tầng phát response | 500 có thể do | 502 có thể do | 503 có thể do | 504 có thể do |
|---|---|---|---|---|
| **CDN / WAF / reverse proxy HTTP** | Lỗi xử lý nội bộ của edge | Nhận response không hợp lệ hoặc lỗi giao tiếp upstream được map 502 | Chính edge quá tải, bảo trì, không có origin khỏe | Edge chờ origin quá thời hạn |
| **API gateway / L7 load balancer** | Gateway lỗi logic/cấu hình xử lý | Kết nối/tương tác không thành công với upstream theo policy | Không có target healthy, quá tải hoặc tạm dừng route | Upstream không trả lời trước deadline |
| **Spring Boot origin** | Exception/lỗi xử lý ngoài dự kiến | Khi **đóng vai gateway** và nhận response upstream không hợp lệ | Service tạm không nhận được yêu cầu hoặc phụ thuộc cốt lõi không sẵn sàng | Khi **đóng vai gateway** và chờ HTTP upstream quá hạn |
| **Một downstream HTTP service** | Chính downstream gặp lỗi bất ngờ | Downstream lại làm gateway tới dịch vụ khác | Downstream quá tải/bảo trì | Downstream lại làm gateway và upstream của nó timeout |
| **Database** | Không trực tiếp phát HTTP 500 | Không trực tiếp phát HTTP 502 | Không trực tiếp phát HTTP 503 | Không trực tiếp phát HTTP 504 |

**Database, queue hoặc TCP load balancer lớp 4 không nhất thiết tạo HTTP response.** Lỗi của chúng được một thành phần HTTP phía trên **chuyển thành** mã HTTP. Vì vậy, nói “database trả 504” là cách diễn đạt dễ gây hiểu nhầm nếu database chỉ trả lỗi driver/timeout nội bộ.

### 7.1. Ma trận sự cố và mã client có thể nhận

| Sự cố gốc | Nơi quan sát/gây ra | Mã client thường thấy | Vì sao cần kiểm tra thêm |
|---|---|---|---|
| NullPointerException tại controller | Spring origin | **500** | Gateway có thể chỉ chuyển tiếp response hợp lệ |
| Origin đang bảo trì trả response ngay | Spring origin | **503** | Có thể có Retry-After nếu biết thời điểm thử lại |
| Gateway không còn healthy target | Gateway/L7 | **503** trong nhiều sản phẩm | Origin có thể không ghi log request |
| Gateway kết nối vào cổng TLS sai | Gateway → origin | **502** trong nhiều sản phẩm | Cần xác minh lỗi handshake/connection trong log |
| Origin trả HTTP headers hỏng | Origin → gateway | **502** | Gateway không đọc được response hợp lệ |
| Query ở Spring kéo dài hơn gateway timeout | Gateway chờ origin | **504** | Spring có thể vẫn tiếp tục và commit |
| Spring gọi ERP, chính Spring đặt deadline | Spring → ERP | **500/503** hoặc mã hợp đồng khác; **504** nếu Spring thật sự đóng vai gateway | Không phải mọi timeout đều là 504 |
| PSP trả **HTTP 500 hợp lệ** cho Spring | PSP | Tùy facade: thường là lỗi API được ánh xạ rõ, không tự động 502 | Phải xét hợp đồng và khả năng retry/đối soát |
| Người dùng gửi URL sai | API / router | Thường **4xx**, không phải 5xx | Cần tách lỗi client khỏi lỗi server |

### 7.2. Quy trình điều tra theo response thực tế

~~~mermaid
flowchart TB
    A["Client báo lỗi request"] --> B{"Có HTTP response không?"}
    B -->|Không| N["Kiểm tra DNS, TLS, TCP, client timeout, hủy request"]
    B -->|Có| C["Ghi mã response, timestamp UTC, route, request/trace ID"]
    C --> D{"Hop nào tạo response?"}
    D -->|CDN / Gateway / LB| E["Đọc edge access log, upstream status, connect/read timeout, health"]
    D -->|Spring / Origin| F["Đọc app trace/log, exception, DB/dependency spans"]
    D -->|Chưa rõ| G["Đối chiếu log từng hop theo trace ID và timestamp"]
    E --> H{"Dạng lỗi"}
    F --> H
    G --> H
    H -->|500| I["Exception / invariant / cấu hình trong thành phần trả response"]
    H -->|502| J["Invalid upstream response / connection / TLS"]
    H -->|503| K["Overload / maintenance / không có instance sẵn sàng"]
    H -->|504| L["Deadline / upstream latency / transaction còn chạy"]
    I --> M["Xác minh nguyên nhân gốc và tác động nghiệp vụ"]
    J --> M
    K --> M
    L --> M
~~~

**Bước quan trọng:** tìm **response emitter** trước rồi mới giải thích mã. Header **Server** hoặc **Via** đôi khi có ích, nhưng có thể bị loại, chuẩn hóa hoặc thay đổi; không dùng nó như bằng chứng duy nhất. Trace context cũng có thể không truyền tới upstream nếu middleware thiếu cấu hình.

### 7.3. Dữ liệu cần giữ khi tạo incident

Một mẫu incident tối thiểu:

~~~text
Incident: order-checkout-5xx
Observed at: 2026-11-18T10:25:00Z
Client request: POST /v1/orders
Client-visible status: 504
Edge requestId: req-c813
TraceId: 7d2e... (đã rút gọn)
Gateway duration: 10000 ms
Gateway upstream status: no response before deadline
Origin observation: request arrived; order commit at 12000 ms
Database: lock wait increased at same time
Customer impact: 18 requests báo 504; 11 orders tồn tại trong DB
Next action: đối soát theo idempotency key trước khi retry
~~~

Đây là ví dụ giả định. Thông tin thực tế cần lấy từ **log đáng tin cậy có dấu thời gian**, dashboard và truy vấn đối soát. Không ghi payload chứa thông tin cá nhân/thẻ hoặc secret vào biên bản nếu không cần thiết.

## 8. Retry, idempotency và tác dụng phụ

Sai lầm nguy hiểm nhất là thiết lập **“gặp 5xx thì retry ngay mọi request”**. Retry có thể cải thiện lỗi thoáng qua, nhưng cũng có thể khuếch đại quá tải, tạo giao dịch trùng và làm sự cố lan rộng.

### 8.1. Khả năng retry phụ thuộc method và hợp đồng

| Request | Tính chất | Chiến lược khi 500/502/503/504 |
|---|---|---|
| **GET / HEAD** | Safe và idempotent theo HTTP | Có thể retry có giới hạn khi lỗi tạm thời; phải tuân thủ deadline và backoff |
| **PUT** | Idempotent về hiệu ứng dự kiến | Có thể cân nhắc retry nếu request đúng hợp đồng và không tạo side effect không được kiểm soát |
| **DELETE** | Idempotent về hiệu ứng dự kiến | Có thể retry có điều kiện, nhưng status lần sau có thể khác; tránh tạo job/refund lặp |
| **POST** | Không mặc định idempotent | Chỉ tự động retry khi đã thiết kế idempotency key, mã giao dịch bền vững và/hoặc đối soát |
| **PATCH** | Không mặc định idempotent | Chỉ retry khi thao tác cụ thể có hợp đồng idempotent hoặc cơ chế chống lặp |

**Idempotent không có nghĩa hai response phải giống nhau.** DELETE lần đầu 204, lần sau 404 vẫn có thể có cùng hiệu ứng dự kiến. Ngược lại, API POST nhận cùng idempotency key nhưng mỗi lần tạo đơn khác nhau **chưa có idempotency đúng**.

### 8.2. Trường hợp đặt hàng và 504

Client gọi:

~~~http
POST /v1/orders HTTP/1.1
Host: api.example.test
Idempotency-Key: checkout-78a1
Content-Type: application/json

{"cartId":"cart-19"}
~~~

Sau 10 giây client nhận 504, nhưng không biết trạng thái giao dịch trong Spring. Thiết kế hợp lý cần:

1. Sinh **idempotency key** duy nhất theo phạm vi người dùng/hành động và lưu bền vững **key + dấu vân tay nội dung + trạng thái + resource ID/response** ở server.
2. Ghi trạng thái đơn bằng transaction hoặc quy trình có khả năng đối soát; không tạo hai đơn vì cùng một key.
3. Nếu client không nhận được phản hồi, **truy vấn trạng thái bằng orderId hoặc request ID đã được công bố**; nếu cần retry, dùng **cùng idempotency key**, không sinh key mới cho lần gửi lại của cùng thao tác.
4. Khi đã gọi cổng thanh toán, dùng mã idempotency/payment intent theo hợp đồng PSP và đối soát các giao dịch có kết quả chưa rõ.
5. Thiết lập TTL lưu key đủ theo chính sách nghiệp vụ và thông báo hành vi nếu cùng key nhưng payload khác.

Một luồng minh họa:

~~~mermaid
sequenceDiagram
    actor C as Client
    participant G as Gateway
    participant A as Orders API
    participant D as Order DB
    C->>G: POST /orders + key K
    G->>A: POST /orders + key K
    A->>D: Tạo đơn gắn key K
    Note over G: Chờ quá deadline
    G-->>C: 504
    D-->>A: Commit thành công
    C->>G: Tra cứu kết quả / retry cùng key K
    G->>A: Request cùng key K
    A->>D: Tìm kết quả đã xử lý cho K
    D-->>A: Đơn ord-19
    A-->>C: Kết quả ổn định của K / ord-19
~~~

Nếu hệ thống có **payment / inventory / shipping** là tác động bên ngoài, chống trùng chỉ ở bảng Orders chưa đủ. Cần idempotency và đối soát ở từng ranh giới. Đồng thời không nên bảo client “thử lại chắc chắn không sao” nếu contract không đảm bảo.

### 8.3. Chính sách retry có giới hạn

Một chính sách thực tế thường gồm:

- **Retryable classification:** xác định loại lỗi nào đủ khả năng tạm thời; 503 có thể kèm Retry-After; 502/504 cần xem trạng thái request và khả năng xử lý trùng.
- **Exponential backoff + jitter:** tránh mọi client thử lại đồng thời sau khi dịch vụ vừa phục hồi.
- **Max attempts và retry budget:** chặn retry vô hạn và retry storm; giới hạn cả tổng thời gian đã trải qua.
- **Circuit breaker và bulkhead:** ngăn dịch vụ đang lỗi giữ hết worker/thread/connection của upstream khác.
- **Timeout/deadline chung:** các lần retry phải nằm trong ngân sách thời gian của request hoặc chuyển sang trạng thái bất đồng bộ rõ ràng.
- **Rate limit/load shedding:** khi quá tải, từ chối sớm request phù hợp còn hơn giữ mọi kết nối rồi timeout hàng loạt.

Ví dụ minh họa cho một GET an toàn, nếu chưa có chỉ dẫn Retry-After:

~~~text
Lần đầu thất bại: chờ khoảng 200 ms + jitter
Lần retry 1 thất bại: chờ khoảng 400 ms + jitter
Lần retry 2 thất bại: dừng nếu đã hết retry budget
~~~

Các thời gian trên chỉ là ví dụ; cần điều chỉnh theo SLO, timeout ở upstream và độ dài xử lý thực tế. Nếu server trả Retry-After, client nên cân nhắc chỉ dẫn đó trong giới hạn timeout và chính sách ứng dụng. **Không áp dụng trực tiếp mẫu này cho POST thanh toán.**

### 8.4. Tránh biến 503 thành 504 vì queueing

Khi một dịch vụ đã quá tải, việc tiếp tục xếp hàng không giới hạn có thể làm tất cả request chờ tới timeout ở gateway, biến **503 sớm và dễ dự đoán** thành **504 trễ và khó điều tra**. Dùng bounded queue, admission control và tín hiệu tải để phản hồi sớm, đồng thời đo queue wait/processing time.

Điều này giúp client có cơ sở backoff, giảm tiêu hao tài nguyên và rút ngắn thời gian hồi phục. Tuy nhiên, cơ chế shed tải phải ưu tiên yêu cầu đúng theo thỏa thuận nghiệp vụ, tránh bỏ qua nhiệm vụ đã được chấp nhận và ghi bền vững.

## 9. Thiết kế hợp đồng lỗi REST API

Client cần hiểu **điều gì đã xảy ra ở mức hợp đồng**, **có thể làm gì tiếp**, và **mã nào dùng khi hỏi hỗ trợ**. Có thể sử dụng **Problem Details for HTTP APIs (RFC 9457)** để thống nhất response của các lỗi 4xx/5xx.

### 9.1. Cấu trúc Problem Details

~~~json
{
  "type": "https://api.example.test/problems/upstream-unavailable",
  "title": "Service Unavailable",
  "status": 503,
  "detail": "The service is temporarily unavailable.",
  "instance": "/v1/orders",
  "requestId": "req-0fb7",
  "errorCode": "ORDER_DEPENDENCY_UNAVAILABLE"
}
~~~

Những member chuẩn quan trọng:

- **type:** URI nhận diện loại vấn đề; có thể trỏ đến tài liệu về cách xử lý.
- **title:** mô tả ngắn, ổn định theo loại lỗi.
- **status:** status HTTP được phản ánh ở body, hữu ích khi response được lưu/đọc riêng.
- **detail:** chi tiết an toàn cho người gọi, không tiết lộ thông tin nội bộ.
- **instance:** nơi xảy ra vấn đề ở phạm vi request/occurrence theo hợp đồng.

**requestId** và **errorCode** là **extension members** của ví dụ, không phải member bắt buộc của RFC. Một API có thể công bố trường **retryable** theo nghiệp vụ, nhưng không nên suy đoán retryable chỉ từ số 5xx: với request ghi, tình trạng hoàn tất có thể chưa rõ.

### 9.2. Mã, content và cache

| Mã | Gợi ý response | Lưu ý |
|---|---|---|
| 500 | Problem detail chung, request/trace ID | Không lộ exception và nội tình hệ thống |
| 502 | Bad Gateway, nguyên nhân bên ngoài đã được khái quát hóa | Không lộ địa chỉ upstream/secret |
| 503 | Service Unavailable, có thể có Retry-After | Chỉ dùng hướng dẫn retry khi phù hợp |
| 504 | Gateway Timeout, làm rõ kết quả thao tác có thể chưa xác định | Hướng client tra cứu hoặc retry có idempotency |

Phản hồi lỗi chứa dữ liệu theo yêu cầu hay người dùng nên dùng cache policy phù hợp, ví dụ **Cache-Control: no-store** nếu không muốn lưu. **Không mặc định tất cả 5xx tuyệt đối không thể được cache**: HTTP có các quy tắc caching dựa vào method, status và thông tin cache; nên đặt chính sách minh bạch để tránh giữ một kết quả lỗi tạm thời ngoài ý muốn.

### 9.3. Giữ tương thích giữa gateway và ứng dụng

Không phải lỗi nào cũng đi qua Spring controller: 502/503/504 đôi khi được sinh ở CDN hoặc gateway trước khi request chạm origin. Nếu muốn client nhận một định dạng lỗi nhất quán, cần cấu hình **error response ở gateway** hoặc cơ chế chuẩn hóa đã được thử, không chỉ cài **@RestControllerAdvice** trong Spring.

Nếu gateway tạo mã lỗi và không thể biết chi tiết nghiệp vụ, nó nên trả thông tin chung. Tránh gateway bắt mọi upstream 4xx/5xx rồi đổi thành một 500, vì sẽ làm hỏng hợp đồng giữa client và API.

## 10. Ví dụ Java/Spring: phân loại lỗi không nhầm vai trò

Ứng dụng Spring có thể tạo lỗi 500/503 trực tiếp. Nếu nó **đóng vai gateway/facade** để phục vụ một HTTP API phía sau, nó còn có thể tạo 502/504 khi upstream hỏng giao tiếp hoặc không đáp ứng đúng hạn. Việc map lỗi phải dựa trên **ngữ cảnh thiết kế**, không phải đơn giản một quy tắc “catch Exception → 500/502”.

### 10.1. Định nghĩa các tình huống lỗi rõ nghĩa

Ví dụ một **facade API** gọi dịch vụ báo giá bên ngoài:

~~~text
GET /v1/quotes/{quoteId}
  -> QuoteFacade
     -> HTTP Quote Provider
~~~

Các exception bên dưới chỉ mang ý nghĩa trong bối cảnh facade:

- **UnexpectedApplicationFailure:** lỗi nội bộ không mong đợi của facade → 500.
- **ServiceTemporarilyUnavailable:** facade tự từ chối do quá tải/bảo trì hoặc điều kiện tạm thời → 503.
- **InvalidUpstreamResponse:** facade làm gateway và nhận phản hồi upstream không hợp lệ → 502.
- **UpstreamDeadlineExceeded:** facade làm gateway, upstream không trả lời trong deadline → 504.

Nếu provider trả **HTTP 400/404/500/503 hợp lệ**, facade cần dùng **hợp đồng ánh xạ hoặc chuyển tiếp cụ thể**; không tạo InvalidUpstreamResponse chỉ vì status là 500. Cần kiểm tra response từ nhà cung cấp có thuộc hợp đồng hay không.

### 10.2. Spring REST Controller Advice dùng ProblemDetail

Ví dụ Spring Framework 6 / Spring Boot 3:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
class ApiProblemHandler {
    private static final Logger log =
            LoggerFactory.getLogger(ApiProblemHandler.class);

    @ExceptionHandler(UnexpectedApplicationFailure.class)
    ResponseEntity<ProblemDetail> unexpected(UnexpectedApplicationFailure ex) {
        log.error("Unexpected application failure", ex);
        return respond(
                HttpStatus.INTERNAL_SERVER_ERROR,
                "Internal Server Error",
                "The request could not be completed."
        );
    }

    @ExceptionHandler(ServiceTemporarilyUnavailable.class)
    ResponseEntity<ProblemDetail> unavailable(ServiceTemporarilyUnavailable ex) {
        log.warn("Temporary service unavailability: {}", ex.getMessage());
        // Chỉ gửi Retry-After nếu có cơ sở cho khoảng chờ này.
        return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
                .header(HttpHeaders.RETRY_AFTER, "30")
                .contentType(MediaType.APPLICATION_PROBLEM_JSON)
                .body(problem(
                        HttpStatus.SERVICE_UNAVAILABLE,
                        "Service Unavailable",
                        "Please try again later."
                ));
    }

    @ExceptionHandler(InvalidUpstreamResponse.class)
    ResponseEntity<ProblemDetail> badGateway(InvalidUpstreamResponse ex) {
        log.error("Invalid response from upstream", ex);
        return respond(
                HttpStatus.BAD_GATEWAY,
                "Bad Gateway",
                "An upstream service returned an invalid response."
        );
    }

    @ExceptionHandler(UpstreamDeadlineExceeded.class)
    ResponseEntity<ProblemDetail> timeout(UpstreamDeadlineExceeded ex) {
        log.warn("Upstream request timed out", ex);
        return respond(
                HttpStatus.GATEWAY_TIMEOUT,
                "Gateway Timeout",
                "An upstream service did not respond in time."
        );
    }

    private static ResponseEntity<ProblemDetail> respond(
            HttpStatus status, String title, String detail) {
        return ResponseEntity.status(status)
                .contentType(MediaType.APPLICATION_PROBLEM_JSON)
                .body(problem(status, title, detail));
    }

    private static ProblemDetail problem(
            HttpStatus status, String title, String detail) {
        ProblemDetail body = ProblemDetail.forStatusAndDetail(status, detail);
        body.setTitle(title);
        String traceId = MDC.get("traceId");
        if (traceId != null && !traceId.isBlank()) {
            body.setProperty("traceId", traceId);
        }
        return body;
    }
}

class UnexpectedApplicationFailure extends RuntimeException {}
class ServiceTemporarilyUnavailable extends RuntimeException {}
class InvalidUpstreamResponse extends RuntimeException {}
class UpstreamDeadlineExceeded extends RuntimeException {}
~~~

**Giới hạn của ví dụ:** chỉ minh họa ánh xạ các lỗi **đã được phân loại**; chưa định nghĩa đầy đủ phát sinh exception, truy cập dữ liệu, tracing filter, authentication hay circuit breaker. Một exception không xác định khác thường được framework xử lý theo cơ chế mặc định và có thể trả 500. Trong ứng dụng thật cần cấu hình response 500 nhất quán và tránh một **catch-all** vô tình biến những 4xx hợp lệ (như validation hoặc phân quyền) thành 500.

Trường **traceId** chỉ hiện khi ứng dụng đã cấu hình truyền và ghi MDC theo hệ quan sát đang dùng. Không được tin tuyệt đối header request ID do client gửi nếu chưa validate và gắn với định danh tin cậy ở ingress. Mã status trả cho client cần khớp với **status** trong ProblemDetail.

### 10.3. Vì sao không map mọi lỗi HTTP downstream thành 502?

Giả sử facade gọi dịch vụ báo giá:

~~~text
QuoteProvider trả HTTP 404 hợp lệ  -> facade trả 404 theo hợp đồng
QuoteProvider trả HTTP 503 hợp lệ  -> facade cân nhắc chuyển 503 hoặc
                                     trả lỗi nghiệp vụ đã được định nghĩa
QuoteProvider trả HTTP 500 hợp lệ  -> không tự động biến thành 502
QuoteProvider đóng kết nối giữa chừng -> facade có thể trả 502
QuoteProvider không trả lời trước deadline -> facade có thể trả 504
~~~

Nếu service không đóng vai gateway mà đang thực hiện một giao dịch nghiệp vụ cần DB/ERP, timeout với dependency nên được **định nghĩa ở cấp nghiệp vụ và availability**. Chọn 502/504 chỉ vì có HTTP client trong code sẽ khiến mã lỗi đánh lạc hướng người vận hành và phá hợp đồng.

### 10.4. Không dùng 503 thay cho mọi lỗi tải cao ở client

Nếu API xác định một người dùng vượt quota đã công bố, **429 Too Many Requests** thường phù hợp hơn 503. Nếu server đang bảo vệ toàn bộ hệ thống khỏi quá tải, **503** có thể phù hợp. Khi có Retry-After, xác định ai được retry, khi nào và liệu request ghi đã thực hiện một phần hay chưa.

## 11. Quan sát, log và trace để xác nhận tầng tạo lỗi

Một dashboard “5xx tăng” là tín hiệu bắt đầu, chưa phải chẩn đoán. Trong hệ phân tán, cần kết nối **HTTP edge metrics, upstream metrics, application traces, dependency spans và chỉ số nghiệp vụ**.

### 11.1. Phân biệt ba loại trạng thái trong log

Giả sử request đi qua một L7 gateway:

| Trường | Ý nghĩa mong muốn |
|---|---|
| **downstream_status** | Mã HTTP gateway thực sự gửi cho client |
| **upstream_status** | Mã HTTP gateway nhận từ origin; có thể trống khi không có response |
| **response_origin / failure_reason** | Lỗi do gateway tự tạo hay chuyển tiếp; timeout, reset, no healthy target… |
| **duration_ms** | Tổng thời gian xử lý đo tại hop hiện tại |
| **upstream_connect_ms** | Thời gian tạo kết nối tới upstream |
| **upstream_response_ms** | Thời gian chờ đến response upstream, nếu nhận được |
| **route / upstream_cluster** | Tuyến và nhóm backend được chọn |
| **traceId / requestId** | Khóa đối chiếu các hop và log nghiệp vụ |

Tên field tùy sản phẩm và cấu hình, **không phải một schema HTTP chuẩn**. Một số reverse proxy ghi upstream status của nhiều lần retry dưới dạng chuỗi; một số gateway không ghi thời gian connect nếu reuse kết nối. Trước khi phân tích, cần hiểu chính xác đơn vị và ngữ nghĩa trường log.

Ví dụ hai access log rút gọn:

~~~json
{
  "timestamp": "2026-11-18T10:25:00Z",
  "route": "POST /v1/orders",
  "downstreamStatus": 504,
  "upstreamStatus": null,
  "failureReason": "upstream_response_timeout",
  "durationMs": 10000,
  "traceId": "trace-001"
}
~~~

~~~json
{
  "timestamp": "2026-11-18T10:25:01Z",
  "route": "GET /v1/products",
  "downstreamStatus": 503,
  "upstreamStatus": 503,
  "failureReason": "upstream_response_forwarded",
  "durationMs": 48,
  "traceId": "trace-002"
}
~~~

Ở ví dụ đầu, gateway tự tạo 504 khi không có response kịp thời. Ở ví dụ sau, origin trả 503 hợp lệ và gateway chuyển tiếp. Hai trường hợp có cùng lớp lỗi 5xx nhưng nhóm cần xử lý và mức nguy hiểm khi retry khác nhau.

### 11.2. Metric và SLI cần có

- **Client-facing availability:** tỷ lệ request thành công theo định nghĩa SLI; phân tách theo route, method, status và khu vực.
- **Gateway-origin connectivity:** error rate kết nối, handshake/TLS failures, reset, no healthy backend, timeout, số lần retry.
- **Latency:** p50/p95/p99 ở gateway, ứng dụng và từng dependency, kèm **queue wait** và **time to first byte**.
- **Application health:** thread pool/connection pool, CPU, memory, GC pauses, error log theo exception class, readiness của từng instance.
- **Data layer:** query latency, lock wait, deadlock, connection saturation, slow query và replication lag khi liên quan.
- **Business invariants:** số đơn chưa rõ kết quả, số giao dịch PSP cần đối soát, duplicate processing, độ trễ job quan trọng.

**Đừng chỉ tính tổng 5xx.** Cùng 1% lỗi, một 503 của endpoint xem catalog có thể khác rất xa 1% checkout 504 khi tiền đã bị thu. Kết hợp tỷ lệ lỗi với **ảnh hưởng nghiệp vụ và khả năng khôi phục**.

Nếu dùng các loại metric của Prometheus/OpenTelemetry, cần tránh gắn **user ID, order ID hoặc raw URL có ID riêng** làm nhãn có độ đa dạng cao. Thay bằng route template như **/v1/orders/{id}**, còn định danh request riêng thuộc trace/log có kiểm soát.

### 11.3. Tracing với tình trạng timeout chưa rõ

Trong distributed tracing, một trace có thể kết thúc ở gateway vì deadline, còn span xử lý tại Spring hoặc database vẫn chạy. Đảm bảo có **trace context propagation**, sampling phù hợp khi có lỗi và đồng bộ đồng hồ ở các host. Tìm:

1. Gateway bắt đầu và ngừng chờ ở thời điểm nào?
2. Origin thực sự nhận request chưa?
3. Origin có hủy hoặc tiếp tục công việc sau khi client rời đi?
4. Giao dịch dữ liệu và tác động bên ngoài đã commit hay chưa?
5. Có retry tự động ở gateway làm origin xử lý cùng request nhiều lần không?

Nếu không có bằng chứng giao dịch đã bị hủy, **không được coi timeout là rollback chắc chắn**.

### 11.4. Quy tắc alert để giảm thời gian điều tra

Một số alert nên chia theo chủ thể xử lý:

| Alert | Tín hiệu | Hành động gợi ý |
|---|---|---|
| **Gateway 502 spike** | Tỷ lệ 502 tăng theo upstream cluster | Kiểm tra health, connect/TLS, rollout, reset |
| **Gateway 504 + latency** | 504 tăng cùng p99 upstream/DB | Kiểm tra bottleneck, timeout budget và khả năng commit sau timeout |
| **503 do hết backend healthy** | Healthy target count giảm về 0 | Kiểm tra readiness, capacity, lỗi deploy, autoscaler |
| **Origin 500 spike** | Exception error rate trong application tăng | Khoanh vùng release, stack trace và dữ liệu kích hoạt |
| **Payment pending lâu** | Giao dịch thanh toán chưa đối soát vượt ngưỡng | Chạy quy trình đối soát, không retry tùy tiện |

Ngưỡng phải gắn với **SLO/error budget và lưu lượng thực tế**; không lấy con số minh họa làm alert chung cho mọi hệ thống.

## 12. Thực hành kiểm thử HTTP và mô phỏng sự cố

Các lệnh dưới đây là minh họa gọi một API **đã triển khai trong môi trường thử nghiệm**; tên miền **api.example.test** không phải endpoint đang hoạt động.

### 12.1. Nhìn thấy response mà client thật nhận

~~~bash
curl -i --max-time 15 \
  -H "Accept: application/problem+json" \
  -H "X-Request-Id: req-demo-001" \
  "https://api.example.test/v1/products/p-1"
~~~

Kiểm tra:

- Status line **500/502/503/504** và các header thực tế.
- Response content type có phải **application/problem+json** không; body có khớp status hay không.
- Có header **Retry-After** trên 503 khi có chính sách thử lại không.
- Header request/trace ID trả về có nguồn đáng tin không.
- Response có dữ liệu nhạy cảm hoặc nội bộ vô tình bị tiết lộ không.

Với lỗi mạng trước khi nhận được HTTP response, curl có thể trả **lỗi client/transport** thay vì một mã HTTP. Đừng ghi nhận mọi lỗi do curl báo là HTTP 500.

### 12.2. Kiểm thử từng lớp bằng fault injection

| Mục tiêu | Cách gây lỗi trong staging | Điều kỳ vọng |
|---|---|---|
| 500 từ Spring origin | Inject một lỗi xử lý được phân loại unexpected | Client nhận 500; log origin có trace; problem detail an toàn |
| 502 từ gateway | Đưa một upstream test trả response HTTP không hợp lệ hoặc cấu hình một kết nối TLS bị từ chối | Gateway map theo policy thực tế; ghi connection/invalid response |
| 503 từ origin | Bật chế độ bảo trì hoặc giới hạn tài nguyên ở instance test | Origin trả 503; gateway phản ánh đúng; có/không Retry-After theo contract |
| 503 từ gateway | Đưa tất cả target của một route test về trạng thái unhealthy | Gateway tự trả 503 theo triển khai; origin không nhận request |
| 504 từ gateway | Delay response origin vượt upstream response deadline | Gateway trả 504; kiểm tra origin có tiếp tục xử lý không |
| 504 với POST ghi dữ liệu | Cho commit xảy ra sau gateway timeout | Retry cùng idempotency key không tạo bản ghi trùng |
| Retry storm | Nhiều client retry khi nhận 503 | Backoff/jitter/rate limit bảo vệ hệ thống |
| DR/rollback | Chuyển route giữa hai phiên bản, hoặc khôi phục backend | Không làm rơi tác vụ đã được chấp nhận hoặc mất khả năng đối soát |

**Chỉ fault-inject trên môi trường và dữ liệu được phép kiểm thử**. Trong bài thực hành, người học có thể dùng stub upstream hoặc các container thử nghiệm để tạo lỗi, không cần thao tác trên dịch vụ production.

### 12.3. Kiểm thử contract và gateway behavior

Một bài test đơn vị của **@RestControllerAdvice** chỉ xác minh được status/body do Spring tạo. Cần thêm:

- **Integration test:** API gọi stub upstream trả response hợp lệ/không hợp lệ/timeout; kiểm tra code mapping.
- **Gateway test:** gọi qua chính route L7/WAF/CDN dự kiến và kiểm tra response lỗi do tầng này tạo.
- **Idempotency test:** cùng một key, nhiều request song song, timeout giữa commit và response, kết quả vẫn một hiệu ứng nghiệp vụ.
- **Load test:** tăng concurrency, đo khi nào ứng dụng chọn trả 503 so với khi gateway bị 504 hàng loạt.
- **Observability test:** từ client requestId lần được log/trace nguồn gốc lỗi đến backend, gồm trường hợp origin chưa từng nhận request.

Một response chứa **500 do backend trả** và một response **500 do gateway tự phát sinh** có thể nhìn giống nhau ở status line. Test cần xác minh **nguồn phát và đường xử lý** qua log đáng tin.

## 13. Tình huống thực tế: thanh toán xuyên nhiều dịch vụ

Hệ thống thương mại điện tử có các thành phần:

~~~mermaid
flowchart LR
    C["Client"] --> G["API Gateway"]
    G --> O["Orders API / Spring"]
    O --> D[("Order DB")]
    O --> P["Payment Adapter"]
    P --> PSP["Payment Provider"]
    O --> E["Inventory API"]
~~~

Một sự kiện checkout bị lỗi có thể cho nhiều kết quả:

### Tình huống A — 500 từ Orders API

Orders API đã nhận request nhưng gặp exception khi chuyển trạng thái đơn. Gateway nhận **HTTP 500 hợp lệ** rồi chuyển cho client. Đội ứng dụng phải tìm stack trace và kiểm tra giao dịch đã commit ở DB hay chưa. Việc sửa exception không tự hoàn tác một khoản tiền PSP đã thu.

### Tình huống B — 502 từ Gateway

Một bản phát hành Spring mới làm backend đóng kết nối quá sớm hoặc handshake không hoàn thành. Gateway không nhận HTTP response hợp lệ nên tạo **502**. SRE kiểm tra backend target, TLS, connection reset, rolling deployment và socket pooling trước khi khẳng định OrderController có bug.

### Tình huống C — 503 từ Gateway hoặc Orders

Do quá tải, tất cả pod Orders bị đánh dấu không ready và gateway trả **503**. Hoặc Orders còn nhận được request nhưng chủ động shed load và trả 503. Hai trường hợp đều có thể khiến client thấy 503 nhưng **nơi điều chỉnh** khác nhau: health/readiness/scaling ở gateway/cluster, hoặc admission control/capacity trong ứng dụng.

### Tình huống D — 504 nhưng tiền có thể đã bị thu

Gateway chờ Orders 10 giây. Orders đang đợi PSP xác nhận, PSP đã xử lý khoản thanh toán nhưng callback/response chậm; gateway trả **504**. Nếu client retry với một idempotency key mới, PSP hoặc Orders có thể tạo thao tác trùng. Cần giữ **payment intent**, kiểm tra trạng thái bằng ID và xử lý đối soát; không dựa vào mã 504 để suy rằng giao dịch chưa xảy ra.

### 13.1. Biểu diễn trạng thái chưa rõ bằng API

Nếu quy trình bất đồng bộ, API có thể trả **202 Accepted** cùng một resource để theo dõi:

~~~http
HTTP/1.1 202 Accepted
Location: /v1/checkout-requests/chk-78a1
Content-Type: application/json

{
  "requestId": "chk-78a1",
  "status": "PENDING"
}
~~~

Client dùng **GET /v1/checkout-requests/chk-78a1** để xem trạng thái sau đó. Đây là một **thiết kế được cân nhắc trước**, không phải giải pháp tự động cho mọi 504. Hệ thống phải lưu request ID bền vững, có quy trình đồng bộ kết quả PSP và hạn xử lý nếu request ở trạng thái pending quá lâu.

### 13.2. Bài học về tính đúng nghiệp vụ

**HTTP phản ánh trạng thái phục vụ request tại một hop; trạng thái đơn hàng, tồn kho và thanh toán là những trạng thái nghiệp vụ riêng.** Một mã 5xx có thể đi kèm một giao dịch đã thành công ở hệ thống khác. API cần định danh giao dịch, quy tắc idempotency, cơ chế tra cứu trạng thái và luồng bù trừ khi trạng thái không thể kết luận ngay.

## 14. Bài tập chẩn đoán

Cho các dữ kiện sau:

| Case | Dữ kiện điều tra | Câu hỏi |
|---|---|---|
| **A** | Client nhận 502; gateway báo TLS handshake failed; Spring không có access log tương ứng | Tầng nào tạo response, ưu tiên kiểm tra gì? |
| **B** | Client nhận 503 trong 4 phút; tất cả backend bị health check fail sau rollout | 503 có bắt buộc do Spring trả không? |
| **C** | Client nhận 504 sau 8 giây; Spring log hoàn thành sau 13 giây và ghi đơn đã commit | Có nên POST lại bằng key mới không? |
| **D** | Spring trả HTTP 500 hợp lệ; gateway log upstreamStatus=500 và downstreamStatus=500 | 500 có nên bị đổi thành 502 không? |
| **E** | Client GET danh mục bị từ chối 429 theo quota user, trong khi server vẫn còn capacity | Vì sao không nên thay toàn bộ thành 503? |
| **F** | Gateway trả 504 nhưng origin không ghi request; gateway log connect timeout | Cần tìm ở lớp nào trước? |

Hãy trả lời mỗi case theo bốn phần: **người tạo HTTP response → khả năng nguyên nhân gốc → rủi ro khi retry → bằng chứng cần thu thập**.

### 14.1. Gợi ý lời giải

**A:** Gateway tạo 502 vì giao tiếp tới upstream thất bại. Kiểm tra TLS/cert, SNI, cổng, protocol, target và route. Spring không ghi log là dữ kiện hỗ trợ rằng request chưa đi tới controller; không nên bắt đầu bằng sửa repository logic.

**B:** 503 có thể được **gateway sinh ra** vì không còn backend khỏe mạnh. Kiểm tra readiness/liveness, rollout, resource pressure, health check path và thông báo từ load balancer. Có thể rollback deployment hoặc sửa điều kiện health nếu xác minh nó sai.

**C:** Không tự tạo idempotency key mới cho cùng thao tác. Client cần tra cứu trạng thái đơn hoặc retry có idempotency key đã dùng theo hợp đồng. 504 mô tả gateway hết thời gian chờ, không chứng minh đơn chưa tạo.

**D:** Upstream đã trả một HTTP 500 hợp lệ và gateway chuyển tiếp; **không tự đổi thành 502**. Root cause vẫn cần tìm trong Spring/database, nhưng thành phần tạo response lỗi là origin.

**E:** 429 diễn đạt hành vi vượt quota ở cấp người gọi, còn 503 mô tả dịch vụ hiện không thể phục vụ. Việc thay sai mã khiến SDK retry không đúng và đo lường sai capacity.

**F:** Gateway không kết nối upstream kịp, nên cần kiểm tra DNS, network, routing, firewall, connection pool và health. Không có access log ở origin là một manh mối; muốn kết luận cần đối chiếu log kết nối/tracing.

### 14.2. Câu hỏi mở rộng

1. Nếu hai lớp gateway đều retry GET hai lần, số request cuối cùng có thể đến origin nhiều hơn kỳ vọng thế nào? Phải đặt **retry budget chung** ở đâu?
2. Tại sao tăng gateway timeout từ 10 lên 60 giây có thể **làm tăng** số 503/504 khi hệ thống đang quá tải?
3. Nếu upstream trả 503 kèm Retry-After=30 nhưng client có deadline tổng còn 5 giây, client nên ứng xử ra sao?
4. Hãy đề xuất một cảnh báo riêng cho **PSP đã thu tiền nhưng Orders API nhận 504**. Chỉ số nào xác minh rủi ro thất thoát hoặc thanh toán trùng?
5. Một API có thể dùng 503 cho một chức năng phụ tạm ngừng trong khi các chức năng khác vẫn hoạt động không? Điều này ảnh hưởng thế nào đến readiness và route-level availability?

## 15. Các nhầm lẫn thường gặp

**“500 là lỗi backend, 502/504 là lỗi DevOps.”** Mã phản ánh bối cảnh trả response, không xác định ai chịu trách nhiệm sửa. Một query chậm do code gây 504 ở gateway; một lỗi deploy gateway có thể gây 500 do chính gateway trả.

**“502 nghĩa là upstream trả 500.”** Không đúng theo ngữ nghĩa chuẩn. Một HTTP 500 hợp lệ từ upstream thường là một response hợp lệ có mã lỗi; 502 mô tả phản hồi upstream không hợp lệ hoặc tình huống giao tiếp mà gateway map thành Bad Gateway.

**“504 nghĩa là database timeout.”** Không nhất thiết. 504 là timeout chờ upstream ở vai trò gateway/proxy. Database timeout do Spring xử lý sẽ được Spring map ra HTTP theo hợp đồng riêng.

**“503 nhất định phải có Retry-After.”** Không bắt buộc. Có thể gửi Retry-After khi server ước lượng được thời điểm thử lại; nếu không biết, vẫn có thể trả 503 mà không có header.

**“Có 5xx thì POST lại sẽ an toàn.”** Sai. Server có thể đã thực hiện một phần hoặc toàn bộ tác động. POST cần idempotency contract và khả năng đối soát trước khi retry.

**“Cứ tăng timeout để hết 504.”** Có thể tăng thời gian giữ kết nối và cạn resource. Cần đo nguyên nhân chậm, queue, database, external API và thiết kế deadline phù hợp.

**“Mọi lỗi 5xx đều do Spring tạo.”** CDN, gateway hoặc proxy có thể trả trước khi request đến ứng dụng. Muốn thống nhất Problem Details phải xử lý cả edge layer.

**“Nếu app trả 200 thì nghiệp vụ chắc chắn thành công.”** Không nhất thiết, nhất là hệ thống bất đồng bộ. Kiểm tra trạng thái đơn/PSP và contract của resource; tránh trả 200 thành công cho một thao tác chưa được xác nhận nếu đó không phải ý nghĩa đã thiết kế.

## 16. Checklist thiết kế và vận hành

- [ ] Phân biệt bốn mã: 500 bất ngờ, 502 invalid upstream response, 503 unavailable, 504 upstream timeout tại gateway.
- [ ] Biết **hop nào tạo response** và lưu log đầy đủ trạng thái client-facing/upstream.
- [ ] Không tự động đổi HTTP 500 hợp lệ từ upstream thành 502 thiếu căn cứ.
- [ ] API có mã lỗi 4xx/5xx đúng bản chất, Problem Details an toàn và request/trace ID.
- [ ] Có timeout budget giữa client, gateway, origin và dependency; kiểm thử timeout thực tế.
- [ ] Có chính sách Retry-After khi phù hợp và retry với backoff, jitter, số lần tối đa.
- [ ] POST/PATCH ghi dữ liệu có idempotency hoặc cơ chế đối soát khi outcome không chắc chắn.
- [ ] Circuit breaker, admission control, bounded queue và load shedding được đo theo SLO.
- [ ] Health/readiness và draining không loại nhầm tất cả backend khỏi cân bằng tải.
- [ ] Có dashboard theo route, status, response emitter, upstream health, latency và tác động nghiệp vụ.
- [ ] Đã kiểm thử origin 500, gateway 502, hai loại 503, gateway 504 và lỗi thanh toán sau timeout.
- [ ] Biết ai trực khi có lỗi, có runbook, trách nhiệm và điều kiện xác nhận khôi phục.

## 17. Tài liệu chuẩn tham khảo

- **RFC 9110 — HTTP Semantics, §15.6**: định nghĩa nhóm 5xx và các mã 500/502/503/504; https://www.rfc-editor.org/rfc/rfc9110.html
- **RFC 9110 — Retry-After**: ngữ nghĩa header chỉ dẫn thời gian thử lại; https://www.rfc-editor.org/rfc/rfc9110.html#name-retry-after
- **RFC 9457 — Problem Details for HTTP APIs**: cách biểu diễn lỗi máy đọc được; https://www.rfc-editor.org/rfc/rfc9457.html
- **RFC 9111 — HTTP Caching**: chính sách cache và tương tác với status; https://www.rfc-editor.org/rfc/rfc9111.html
- **Spring Framework — Error Responses / ProblemDetail**: tài liệu lập trình Spring MVC; https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-rest-exceptions.html

**Nguyên tắc cốt lõi:** mã 5xx cho biết **điều kiện lỗi tại thành phần trả HTTP response**, còn nguyên nhân gốc có thể nằm ở tầng xa hơn. Hãy đối chiếu log/trace qua từng hop trước khi sửa hệ thống, thiết kế timeout và retry có ngân sách, và luôn coi kết quả của thao tác ghi sau một **504** là **chưa xác định cho đến khi đối soát**. Đó là nền tảng để REST API vừa phản hồi đúng chuẩn vừa an toàn cho dữ liệu và nghiệp vụ.
