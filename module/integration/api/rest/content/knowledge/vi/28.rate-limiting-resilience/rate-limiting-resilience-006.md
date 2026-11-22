# Phân biệt quá hạn mức client với server không sẵn sàng

## 1. Tình huống: cùng là “thử lại sau”, nhưng nguyên nhân khác nhau

Giả sử Shop API phục vụ ứng dụng web, đối tác tích hợp và hệ thống thanh toán. API đặt hạn mức **100 lần gọi mỗi phút cho từng client** để ngăn một bên chiếm hết tài nguyên. Đồng thời, Orders API có giới hạn số request xử lý đồng thời và có thể tạm ngừng để bảo trì.

Hai tình huống:

- Đối tác A đã dùng hết 100 request trong cửa sổ một phút. Các đối tác khác vẫn gọi API bình thường. Đó là **client vượt quota/rate limit**: phản hồi điển hình là **429 Too Many Requests**.
- Database kết nối bão hòa hoặc API đang bảo trì; ngay cả đối tác B chưa dùng hết quota cũng không được phục vụ. Đó là **dịch vụ tạm thời không sẵn sàng**: phản hồi điển hình là **503 Service Unavailable**.

Cả hai có thể gợi ý **`Retry-After`**, nhưng client và người vận hành cần hiểu **lý do bị từ chối**, đối tượng bị ảnh hưởng, thời gian chờ, cách retry và trách nhiệm khắc phục. Nếu biến mọi lỗi thành 429, người dùng có thể bị báo “bạn gọi quá nhiều” trong khi hệ thống bị sự cố. Nếu biến mọi 429 thành 503, client có thể liên tục retry, làm tăng tải và che giấu việc một consumer sử dụng vượt hợp đồng.

**Mục tiêu học tập:** Phân biệt 429/503 và những mã lân cận; thiết kế response HTTP, `Retry-After`, Problem Details và quota policy; triển khai Java/Spring minh họa token bucket và load shedding; xử lý retry/backoff/idempotency phía client; đo lường, cảnh báo và kiểm thử REST API dưới tải.

## 2. Chọn HTTP status từ nguyên nhân, không chỉ từ thông điệp lỗi

| Mã | Khi nào dùng | Phạm vi thường gặp | Client nên làm gì? |
|---|---|---|---|
| **429 Too Many Requests** | Caller/khóa quota cụ thể dùng vượt số request được phép trong một khoảng hoặc vượt hạn mức được công bố | Theo tài khoản, API key, tenant, IP, route hoặc chính sách quota | Giảm tốc, tôn trọng `Retry-After` nếu có, xếp hàng/throttle theo khóa quota |
| **503 Service Unavailable** | Service không thể tiếp nhận/xử lý tạm thời do quá tải, đang bảo trì hoặc tài nguyên phụ thuộc khiến endpoint không sẵn sàng | Nhiều caller, node, khu vực hoặc cả service | Retry có backoff/jitter và deadline nếu thao tác an toàn; failover/degrade khi phù hợp |
| **502 Bad Gateway** | Gateway/proxy nhận **phản hồi không hợp lệ** từ upstream | Đường gateway → upstream | Xem lỗi upstream/proxy; retry có kiểm soát nếu an toàn |
| **504 Gateway Timeout** | Gateway/proxy không nhận **phản hồi kịp thời** từ upstream | Đường gateway → upstream | Tôn trọng timeout budget, chỉ retry an toàn; cẩn trọng vì upstream có thể đã xử lý |
| **500 Internal Server Error** | Lỗi bất ngờ nội bộ không ánh xạ được vào trạng thái cụ thể hơn | Một request hoặc phần hệ thống | Không mặc định lỗi sẽ hết bằng retry; ghi nhận và điều tra |
| **408 Request Timeout** | Server không nhận đủ request từ client trong thời gian cho phép | Request/connection | Có thể gửi lại theo semantics phương thức nếu an toàn |
| **401/403** | Chưa xác thực hoặc không đủ quyền truy cập | Danh tính/quyền | Lấy token hợp lệ hoặc điều chỉnh quyền; retry nguyên trạng không giải quyết |
| **400/422** | Đầu vào không hợp lệ theo contract/semantics | Dữ liệu của request | Sửa request; không retry vô hạn |

**Nguyên tắc nhận diện:** Nếu request bị chặn do **chính consumer đã vượt chính sách sử dụng** trong khi service vẫn có khả năng phục vụ các consumer hợp lệ khác, hãy nghĩ đến 429. Nếu service hiện **không có khả năng phục vụ request hợp lệ ngay cả khi caller chưa vượt quota**, hãy nghĩ đến 503. HTTP không bắt buộc mọi cơ chế quá tải đều trả được status (server có thể từ chối kết nối); khi có thể tạo phản hồi HTTP, chọn status phản ánh nguyên nhân sẽ giúp client phản ứng đúng.

### 2.1. Phân biệt “quota” với “overload”

**Quota** là chính sách phân chia quyền sử dụng: 50 request/10 giây cho API key, 1.000 request/giờ cho tenant, 5 request tạo báo cáo/giờ cho user. Một client bị giới hạn không đồng nghĩa server hết CPU hay database chết. Quota có thể dựa trên hợp đồng sản phẩm, fairness hoặc chống lạm dụng.

**Overload** là tình trạng không đủ năng lực xử lý an toàn tại thời điểm đó: thread pool hết slot, DB pool/queue bão hòa, downstream có sự cố, bộ nhớ vượt ngưỡng, đang triển khai maintenance. Load shedding từ chối bớt request để giữ service còn phục vụ được phần còn lại.

Một **giới hạn số job chạy đồng thời theo user** là quota nếu chỉ user ấy vượt mức — thường 429. Một **giới hạn số worker chung cho cả cụm** bị đầy làm service không nhận thêm job hợp lệ — thường 503. Cùng là “semaphore đã đầy”, nhưng chính sách và phạm vi quyết định status.

### 2.2. Một số tình huống dễ nhầm

| Tình huống | Mã phù hợp | Lý do |
|---|---|---|
| Một API key gọi 120 lần trong giới hạn 100 lần/phút | 429 | Hết quota của consumer |
| Khách chưa hết quota nhưng hàng đợi chung đã đầy, server từ chối nhận thêm | 503 | Thiếu năng lực phục vụ toàn cục |
| API đang bảo trì có lịch trong 5 phút | 503 + `Retry-After` nếu thời điểm dự kiến tin cậy | Không sẵn sàng tạm thời |
| API gateway không nhận được response upstream trước deadline | 504 | Timeout tại gateway |
| Gateway nhận response hỏng/không hợp lệ từ upstream | 502 | Bad gateway |
| Token hết hạn nên không gọi được endpoint | 401 | Sai thông tin xác thực, không phải rate limit |
| Scope không đủ nên gọi báo cáo bị từ chối | 403 | Không đủ quyền, không phải hết quota |
| Client retry ngay 100 lần sau một 503 và sau đó bị chặn theo quota | 503 trước, có thể 429 ở những lần sau | Hai tình trạng có thể nối tiếp, nên quan sát riêng |

Nếu hệ thống đồng thời bị quá tải và một client đã vượt quota, hãy **định nghĩa rõ thứ tự áp dụng chính sách** (ví dụ quota được kiểm ở gateway, overload được kiểm ở service) và mã lỗi có ý nghĩa cuối cùng. Không để các layer thay thế 429 thành 503 hoặc ngược lại tùy tiện; cần giữ thông tin nguồn phát sinh để điều tra.

## 3. Hợp đồng HTTP cho 429 Too Many Requests

RFC 6585 định nghĩa 429 để mô tả user đã gửi quá nhiều request trong một khoảng thời gian. Server **có thể** gửi `Retry-After` để đề nghị thời điểm được gọi tiếp và **nên** có phần giải thích điều kiện. RFC không áp đặt cách đếm quota hay xác định user; đó là hợp đồng của từng API.

Ví dụ đã hết hạn mức:

~~~http
GET /api/orders?page=1 HTTP/1.1
Host: api.example.test
Authorization: Bearer example-access-token
Accept: application/json

HTTP/1.1 429 Too Many Requests
Content-Type: application/problem+json
Cache-Control: no-store
Retry-After: 15

{
  "type": "https://api.example.test/problems/rate-limit-exceeded",
  "title": "Too Many Requests",
  "status": 429,
  "detail": "Hạn mức gọi API tạm thời đã hết.",
  "code": "CLIENT_RATE_LIMITED",
  "requestId": "req-8f3a"
}
~~~

Một số điểm quan trọng:

- `429` thuộc nhóm **4xx**, diễn tả ràng buộc sử dụng của caller; nó không chứng minh client đã gửi request sai cú pháp.
- `Retry-After: 15` đề nghị **đợi ít nhất 15 giây từ lúc nhận phản hồi** trước lần thử tiếp theo. Header là tùy chọn, có thể không có hoặc mang ngày HTTP.
- `429` theo RFC 6585 **không được cache bởi HTTP cache**. `Cache-Control: no-store` trong ví dụ làm rõ chủ ý và phòng các thành phần cache tùy biến cấu hình sai; vẫn cần kiểm chính sách edge thực tế.
- Trả mã lỗi ứng dụng ổn định (`CLIENT_RATE_LIMITED`) để client không phải đoán từ ngôn ngữ `detail`.
- Không đưa access token, API key, IP nguyên văn, danh tính của client khác hay ngưỡng chống lạm dụng nhạy cảm vào body.
- Nếu nhiều quota cùng áp dụng, server nên xác định hạn mức nào chặn request và cung cấp hướng dẫn đủ dùng; không bắt client đoán một khoảng reset từ số liệu của hạn mức khác.

### 3.1. Không có `Retry-After` có nghĩa gì?

429 vẫn hợp lệ khi không có `Retry-After`, ví dụ service không ước lượng được khi nào quota trở lại, hoặc chính sách sử dụng yêu cầu client tham khảo tài liệu. Client nên áp dụng backoff+jitter và giới hạn tổng số retry thay vì gọi ngay. Hạn mức dài hạn (ví dụ hết quota tháng) có thể không thể giải quyết bằng retry ngắn; hợp đồng nên phân biệt `quota_exhausted` cần nâng gói/đợi reset với `burst_limit_exceeded` thường hết nhanh.

### 3.2. Quota metadata không thay thế `Retry-After`

Một số API công bố các trường như `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset` hoặc các trường `RateLimit` theo contract của nhà cung cấp. **Tên trường, đơn vị reset, phạm vi quota và mức độ chuẩn hóa không nên tự suy đoán** từ một ví dụ HTTP. Khi triển khai, chọn một hợp đồng được tài liệu hóa, ghi rõ key limit, window, chi phí request, precision và cách xử lý nhiều giới hạn chồng nhau.

Ví dụ một thiết kế riêng chỉ mang tính minh họa:

~~~http
HTTP/1.1 200 OK
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 17
X-RateLimit-Reset: 30
Cache-Control: private
~~~

Ở đây tác giả API **phải** định nghĩa `Reset: 30` là gì, có phải số giây hay epoch và dành cho policy nào. Đừng yêu cầu mọi client hiểu những trường này nếu chúng chưa nằm trong contract. Khi phải chọn, `Retry-After` là hướng dẫn chung dễ liên thông hơn cho phản hồi tạm thời bị chặn.

## 4. Hợp đồng HTTP cho 503 Service Unavailable

RFC 9110 mô tả 503 khi server tạm thời không thể xử lý request do **overload hoặc bảo trì theo kế hoạch**. Server **có thể** trả `Retry-After` để cho biết dự kiến bao lâu dịch vụ chưa sẵn sàng.

Ví dụ đang bảo trì với thời gian dự kiến:

~~~http
GET /api/orders HTTP/1.1
Host: api.example.test
Authorization: Bearer example-access-token

HTTP/1.1 503 Service Unavailable
Content-Type: application/problem+json
Cache-Control: no-store
Retry-After: 120

{
  "type": "https://api.example.test/problems/service-unavailable",
  "title": "Service Unavailable",
  "status": 503,
  "detail": "Dịch vụ đang tạm thời không khả dụng.",
  "code": "SERVICE_TEMPORARILY_UNAVAILABLE",
  "requestId": "req-f74b"
}
~~~

Nếu node quá tải không thể dự đoán chính xác thời gian phục hồi, **không cần tự bịa `Retry-After`**; client vẫn cần exponential backoff có jitter và deadline riêng:

~~~http
HTTP/1.1 503 Service Unavailable
Content-Type: application/problem+json
Cache-Control: no-store

{
  "type": "https://api.example.test/problems/service-busy",
  "title": "Service Unavailable",
  "status": 503,
  "detail": "Hệ thống đang bận. Vui lòng thử lại sau.",
  "code": "SERVICE_OVERLOADED"
}
~~~

Nên trả lỗi nhanh khi server biết trước không còn năng lực thay vì giữ request chờ vô hạn trong queue. Với hệ thống phân tán, 503 có thể được phát tại load balancer, API gateway hoặc ứng dụng; request ID và telemetry nên cho biết tầng nào từ chối. Nếu **gateway timeout chờ upstream**, 504 rõ nguyên nhân hơn 503. Nếu **gateway nhận upstream response không hợp lệ**, 502 phù hợp hơn.

503 không phải “lỗi 500 mặc định”, và sự tồn tại của 503 không đảm bảo server quá tải sẽ luôn đủ tài nguyên để trả phản hồi này: trong sự cố nghiêm trọng, kết nối có thể bị reset/timeout. Client cần xử lý cả lỗi transport, không chỉ mã HTTP.

### 4.1. Khi nào không dùng 503?

Không dùng 503 để biểu diễn một request có payload sai, đăng nhập thất bại hoặc người dùng bị khóa quota theo chính sách. Không biến `404` thành `503` để mong client thử lại. Nếu downstream yêu cầu xác thực lại, xác định sai lầm ở đâu trước khi ánh xạ lỗi; đừng trả 503 cho mọi exception vì như vậy che lấp lỗi lập trình và tăng retry không cần thiết.

### 4.2. Cân nhắc tính sẵn sàng từng chức năng

Một dependency ảnh hưởng báo cáo nặng nhưng endpoint `GET /api/catalog` vẫn chạy: có thể trả 503 **chỉ** ở route báo cáo và vẫn giữ catalog 200. Chỉ đánh dấu readiness của toàn bộ service là không sẵn sàng nếu routing instance đó không còn đáp ứng những chức năng cần thiết theo hợp đồng triển khai. Nếu phương thức fallback trả kết quả giảm chất lượng, phải nói rõ trong API contract; tránh trả 200 với dữ liệu sai/không đủ trong khi client tưởng kết quả hoàn chỉnh.

## 5. `Retry-After`: cú pháp và cách diễn giải

`Retry-After` chấp nhận **hai định dạng** theo RFC 9110:

~~~http
Retry-After: 30
~~~

Giá trị là số nguyên không âm: **số giây** trì hoãn sau khi nhận response. Không diễn giải `30` là timestamp hoặc mili giây.

~~~http
Retry-After: Wed, 18 Nov 2026 14:00:00 GMT
~~~

Giá trị là **HTTP-date**, cần so với thời gian hiện tại; lưu ý đồng hồ lệch giữa client/server. Có thể dùng header `Date` của response để nhận biết độ lệch đồng hồ theo chính sách. Với ngày trong quá khứ, thời gian còn chờ bằng 0, nhưng vẫn cần chính sách chống retry ồ ạt.

| Tình huống | Cách diễn giải |
|---|---|
| 429 + `Retry-After: 10` | Caller đã chạm hạn mức; đợi tối thiểu 10 giây và giảm lưu lượng gửi |
| 503 + `Retry-After: 60` | Service ước lượng chưa sẵn sàng khoảng 60 giây; tránh gọi sớm |
| 503 không có Retry-After | Backoff+jitter với ngân sách retry có giới hạn |
| 429 với Retry-After lớn hơn timeout tổng của client | **Không** retry sớm hơn để “kịp deadline”; chuyển lỗi lên caller/scheduler |
| Header không hợp lệ | Bỏ qua header lỗi, dùng chính sách backoff an toàn và ghi telemetry |
| Có nhiều request cùng nhận 429/503 | Phối hợp throttle/queue theo key và jitter, không để tất cả cùng tỉnh lại chính xác một lúc |

`Retry-After` là **gợi ý giao thức, không bảo đảm request tiếp theo thành công**. Khi quota có nhiều chiều (IP và API key, tenant và endpoint) hoặc service còn overload, trạng thái tại thời điểm retry vẫn có thể khác. 429 và 503 đều có thể không có header này. Với 503 quá tải, server có thể cấp một ước lượng động thay vì hẹn giờ cụ thể; client phải luôn có giới hạn tổng thời gian và số lần retry.

## 6. Token bucket và load shedding khác nhau trong kiến trúc

### 6.1. Rate limiter: phân phối quota công bằng

**Token bucket** thường gồm:

- `capacity = B`: tối đa B token tích lũy, cho phép burst ngắn.
- `refillRate = r` token/giây: tốc độ cấp lại.
- Mỗi request tiêu tốn `cost` token (thường là 1; API đắt tiền có thể tính nhiều hơn).
- Request được phép nếu bucket có đủ token; nếu không, trả 429 hoặc xếp hàng theo policy. Khi trả 429, có thể ước lượng thời gian để có token mới.

Sau thời gian `Δt`:

`tokens = min(B, tokens + r * Δt)`

Sau khi request được chấp nhận:

`tokens = tokens - cost`

Ví dụ `B=5`, `r=1 token/giây`; một client gửi 6 request cùng lúc khi bucket đầy. Năm request đầu được cấp token, request thứ sáu bị 429. Sau khoảng 1 giây, bucket có thể cấp lại ít nhất một token. Nếu hệ thống dùng **fixed window** 100/phút, thời điểm reset lại có semantics khác; không mô tả mọi limiter như token bucket.

Có thể đặt nhiều lớp quota:

- **Theo consumer** (API key, user, client app): đảm bảo fairness và chặn client gọi quá nhanh.
- **Theo tenant/gói dịch vụ**: thực thi hợp đồng sử dụng.
- **Theo route/cost**: endpoint tạo báo cáo tốn tài nguyên hơn endpoint đọc health.
- **Theo IP** cho truy cập chưa xác thực: chống abuse sơ cấp, nhưng có thể bất công với NAT/proxy. Chỉ tin header IP từ gateway/proxy được cấu hình tin cậy; không lấy `X-Forwarded-For` do client tùy ý đặt.
- **Theo đồng thời từng consumer**: tránh một caller mở quá nhiều kết nối dài hoặc job.

Các key hạn mức phải xác định rõ, ví dụ `{tenant}:{clientId}:{routeClass}`, trong đó tenant và clientId đã được server **xác minh**. Không tin `tenantId` truyền trong URL là quyền truy cập. Tránh giới hạn một IP chung cho hàng nghìn người mà không có chính sách cân bằng thích hợp.

### 6.2. Load shedding: bảo vệ tài nguyên chung

Load shedding từ chối request **trước khi sử dụng thêm tài nguyên đắt đỏ** khi vượt ngưỡng vận hành: số request in-flight, độ dài queue, DB pool, CPU, latency hoặc hệ số lỗi downstream. Mục tiêu là ngăn cả service sụp đổ và bảo vệ tail latency. Nếu là thiếu năng lực phục vụ tạm thời của node/service, trả 503 khi có thể.

Những cơ chế liên quan nhưng khác mục đích:

| Cơ chế | Vai trò | Chú ý |
|---|---|---|
| Token bucket/fixed window | Hạn chế tốc độ/quota cho consumer | Khi một key vi phạm, 429 |
| Global concurrency limit/bulkhead | Không cho quá nhiều công việc đồng thời chiếm pool | Nếu pool chung đầy gây từ chối service-wide, có thể 503 |
| Bounded queue | Không giữ vô hạn request chờ | Queue đầy thì shed nhanh và có telemetry |
| Timeout/deadline | Giới hạn thời gian chờ dịch vụ phụ thuộc | Tránh giữ tài nguyên đến vô hạn |
| Circuit breaker | Ngừng gọi downstream đang lỗi; thử phục hồi có kiểm soát | Nếu chức năng không thể đáp ứng, có thể 503 hoặc fallback theo contract |
| Retry with backoff/jitter | Tăng cơ hội vượt lỗi thoáng qua, tránh dồn tải | Dùng cho request an toàn, có budget |
| Cache hợp lệ | Giảm tải truy vấn, giữ dữ liệu đáp ứng nhanh | Tôn trọng quyền, freshness và invalidation |
| Readiness/load balancer | Loại node không sẵn sàng khỏi luồng request | Không dùng readiness làm quota của từng user |

Không tạo vòng phụ thuộc: service overload trả 503 → mỗi client retry ngay → tăng tải → service overload nặng hơn. Cần hướng dẫn client giảm tải và chủ động shed/backpressure ngay từ sớm.

### 6.3. Sơ đồ quyết định trong request pipeline

~~~mermaid
flowchart TD
    A[Nhận REST request] --> B{Cơ chế xác thực hợp lệ?}
    B -->|Không| C[401 Unauthorized]
    B -->|Có| D{Có quyền thao tác?}
    D -->|Không| E[403 Forbidden]
    D -->|Có| F{Consumer hết quota?}
    F -->|Có| G[429 Too Many Requests]
    F -->|Không| H{Service còn năng lực xử lý?}
    H -->|Không| I[503 Service Unavailable]
    H -->|Có| J[Thực thi nghiệp vụ]
    J --> K{Kết quả}
    K -->|Thành công| L[2xx]
    K -->|Lỗi gateway timeout| M[504 nếu là gateway]
    K -->|Lỗi bất ngờ| N[5xx tương ứng]
~~~

Đây là thứ tự khái niệm, không bắt buộc gateway mọi hệ thống phải xác thực trước khi kiểm giới hạn lưu lượng. Lớp bảo vệ DDoS/IP có thể chạy trước authentication, còn quota theo user/tenant cần principal đáng tin. 503 do proxy không sẵn sàng thậm chí có thể phát sinh trước khi request tới ứng dụng. Khi thiết kế pipeline, ghi rõ tầng nào phát mã lỗi để client, log và dashboard không nhầm lẫn.

## 7. Java/Spring: minh họa rate limit theo client trả 429

Ví dụ Spring Boot 3.x, Java 17+, Spring Security 6.x. Dependencies cơ bản: `spring-boot-starter-web`, `spring-boot-starter-security`, `spring-boot-starter-oauth2-resource-server`, `spring-boot-starter-test`, `spring-security-test`. Đây là mẫu **in-memory cho một JVM** nhằm giải thích điểm quyết định HTTP; chưa phải limiter nhiều instance để triển khai production.

### 7.1. Token bucket nhỏ, quyết định rõ ràng

~~~java
import java.util.concurrent.ConcurrentHashMap;
import org.springframework.stereotype.Service;

record QuotaDecision(boolean allowed, long retryAfterSeconds) {}

@Service
class InMemoryClientQuota {
    private static final double CAPACITY = 5.0;
    private static final double REFILL_PER_SECOND = 1.0;

    private static final class Bucket {
        double tokens = CAPACITY;
        long lastNanos = System.nanoTime();
    }

    private final ConcurrentHashMap<String, Bucket> buckets =
        new ConcurrentHashMap<>();

    QuotaDecision take(String verifiedClientKey) {
        Bucket bucket = buckets.computeIfAbsent(
            verifiedClientKey, key -> new Bucket());

        synchronized (bucket) {
            long now = System.nanoTime();
            double elapsedSeconds =
                Math.max(0L, now - bucket.lastNanos) / 1_000_000_000.0;

            bucket.tokens = Math.min(
                CAPACITY,
                bucket.tokens + elapsedSeconds * REFILL_PER_SECOND);
            bucket.lastNanos = now;

            if (bucket.tokens >= 1.0) {
                bucket.tokens -= 1.0;
                return new QuotaDecision(true, 0);
            }

            double missing = 1.0 - bucket.tokens;
            long waitSeconds = Math.max(
                1L, (long) Math.ceil(missing / REFILL_PER_SECOND));
            return new QuotaDecision(false, waitSeconds);
        }
    }
}
~~~

`synchronized(bucket)` giữ thao tác kiểm tra/trừ token **atomic trong một JVM**. `System.nanoTime()` dùng để đo khoảng thời gian elapsed, tránh phụ thuộc việc đồng hồ wall-clock được chỉnh lại. Với capacity 5 và refill 1 token/giây, client được burst 5 rồi bị 429 tới khi có token. `retryAfterSeconds` là ước lượng cho quota bucket hiện tại, không phải cam kết quyền truy cập ở lần tiếp theo.

**Giới hạn cần giải quyết trước production:**

- Map không tự xóa key, có thể tăng bộ nhớ vô hạn nếu một attacker tạo nhiều identity/IP giả; phải TTL/eviction, giới hạn số key hoặc offload tới kho quota.
- Nhiều instance sẽ có **mỗi instance một bucket**, làm quota lệch; cần API gateway hoặc kho chia sẻ (ví dụ Redis có thao tác atomic Lua/script) nếu muốn quota nhất quán trên cụm.
- Restart sẽ reset bucket; quota trên gói dịch vụ cần lưu phân tán nếu có nghĩa vụ chính xác.
- Kết hợp key theo client/user/tenant/route đã xác minh; lưu ý quota phân quyền trước hoặc sau authentication, và chính sách fallback khi kho quota mất kết nối.
- Thời điểm trả 429 phải tránh gọi dịch vụ tốn tài nguyên **sau khi đã từ chối**; kiểm idempotency/không ghi dữ liệu nếu bị chặn.

### 7.2. Controller đặt quota sau authentication

Ví dụ API Resource Server đã cấu hình để kiểm token, issuer/audience và scope `orders.read`. Controller lấy `Jwt` từ Spring Security thay vì `clientId` tự khai trong body:

~~~java
import java.util.List;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

record OrderView(String id) {}

interface OrderReader {
    List<OrderView> forAuthenticatedSubject(String issuer, String subject);
}

@RestController
class OrderController {
    private final InMemoryClientQuota quota;
    private final OrderReader orders;

    OrderController(InMemoryClientQuota quota, OrderReader orders) {
        this.quota = quota;
        this.orders = orders;
    }

    @GetMapping("/api/orders")
    List<OrderView> myOrders(@AuthenticationPrincipal Jwt jwt) {
        // jwt phải đã được JwtDecoder kiểm chữ ký, iss, aud, exp.
        String verifiedKey =
            jwt.getIssuer() + "|" + jwt.getSubject();

        QuotaDecision decision = quota.take(verifiedKey);
        if (!decision.allowed()) {
            throw new ClientQuotaExceeded(decision.retryAfterSeconds());
        }

        // Service thật còn phải kiểm tenant, owner và quyền dữ liệu.
        return orders.forAuthenticatedSubject(
            jwt.getIssuer().toString(), jwt.getSubject());
    }
}
~~~

`issuer + subject` chỉ là **một key quota minh họa**. Nếu một `sub` dùng chung trong nhiều ứng dụng OAuth, bổ sung client/application identity được xác minh; nếu quota theo tenant, ánh xạ tenant và membership qua server. Không cho client vượt giới hạn bằng cách tự thay header `X-Client-Id`. Với endpoint công khai, có thể dùng quota IP nhưng phải tin cấu hình proxy; không lấy `X-Forwarded-For` từ Internet một cách trực tiếp.

Security rule minh họa:

~~~java
@Bean
SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
    return http
        .csrf(AbstractHttpConfigurer::disable)
        .sessionManagement(s ->
            s.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
        .authorizeHttpRequests(auth -> auth
            .requestMatchers(HttpMethod.GET, "/api/orders")
                .hasAuthority("SCOPE_orders.read")
            .anyRequest().denyAll())
        .oauth2ResourceServer(oauth ->
            oauth.jwt(Customizer.withDefaults()))
        .build();
}
~~~

Cần các import Spring Security tương ứng; cấu hình Resource Server thực tế phải xác minh issuer **và audience của API**, không mặc định mọi JWT cùng issuer đều dùng được. Tắt CSRF trong mẫu chỉ phù hợp API stateless xác thực bằng Bearer header; web session dùng cookie phải có CSRF policy riêng. Việc chặn 429 không thay thế xác thực, phân quyền đối tượng hay kiểm tra tenant.

### 7.3. Exception handler trả Problem Details và Retry-After

~~~java
import org.springframework.http.CacheControl;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

final class ClientQuotaExceeded extends RuntimeException {
    private final long waitSeconds;

    ClientQuotaExceeded(long waitSeconds) {
        this.waitSeconds = Math.max(1L, waitSeconds);
    }

    long waitSeconds() {
        return waitSeconds;
    }
}

final class ServiceBusyException extends RuntimeException {}

@RestControllerAdvice
class ApiErrorHandler {
    @ExceptionHandler(ClientQuotaExceeded.class)
    ResponseEntity<ProblemDetail> onQuota(ClientQuotaExceeded error) {
        ProblemDetail body = ProblemDetail.forStatusAndDetail(
            HttpStatus.TOO_MANY_REQUESTS,
            "Hạn mức gọi API tạm thời đã hết.");
        body.setTitle("Too Many Requests");
        body.setProperty("code", "CLIENT_RATE_LIMITED");

        return ResponseEntity.status(HttpStatus.TOO_MANY_REQUESTS)
            .header(HttpHeaders.RETRY_AFTER,
                Long.toString(error.waitSeconds()))
            .cacheControl(CacheControl.noStore())
            .body(body);
    }

    @ExceptionHandler(ServiceBusyException.class)
    ResponseEntity<ProblemDetail> onOverload(ServiceBusyException error) {
        ProblemDetail body = ProblemDetail.forStatusAndDetail(
            HttpStatus.SERVICE_UNAVAILABLE,
            "Dịch vụ đang bận, vui lòng thử lại sau.");
        body.setTitle("Service Unavailable");
        body.setProperty("code", "SERVICE_OVERLOADED");

        return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
            // Không ước lượng chính xác được thời gian hồi phục:
            // nên không tự tạo Retry-After giả.
            .cacheControl(CacheControl.noStore())
            .body(body);
    }
}
~~~

`ProblemDetail` tạo body `application/problem+json` theo hỗ trợ Spring Framework; các trường `code` là extension tùy API. Mẫu bắt **hai exception chuyên biệt**, tránh `@ExceptionHandler(Exception.class)` gán mọi lỗi thành 503. Handler thuộc ứng dụng; 503 do gateway tạo có thể cần cấu hình body/header tương đương ở gateway.

### 7.4. Load shedding chung trả 503

Mẫu giới hạn số tác vụ nặng chạy đồng thời **theo instance**:

~~~java
import java.util.concurrent.Semaphore;
import java.util.function.Supplier;
import org.springframework.stereotype.Component;

@Component
class HeavyWorkBulkhead {
    // 20 tác vụ nặng đồng thời tối đa trên một instance.
    private final Semaphore slots = new Semaphore(20, true);

    <T> T execute(Supplier<T> operation) {
        if (!slots.tryAcquire()) {
            // Năng lực chung của node đã đầy, khác quota client.
            throw new ServiceBusyException();
        }

        try {
            return operation.get();
        } finally {
            slots.release();
        }
    }
}
~~~

Với một endpoint:

~~~java
@GetMapping("/api/reports/{reportId}")
ReportView report(@PathVariable UUID reportId) {
    return bulkhead.execute(() -> reportService.generate(reportId));
}
~~~

Đoạn controller cần được đặt trong `@RestController` có `bulkhead`, `reportService` được inject; `ReportView` và `generate` là hợp đồng nghiệp vụ của ứng dụng. **Semaphore** chặn request mới trước khi gọi tác vụ nặng; luôn giải phóng trong `finally`. Nó không tạo số slot chung toàn cụm. Một concurrency limit theo **riêng client** với chính sách công bố có thể trả 429; ở đây slot chung của node bị đầy nên trả 503.

Nếu hệ thống có cơ chế asynchronous long-running job, tốt hơn nên trả **202 Accepted** khi job thực sự đã được **nhận vào hàng đợi bền vững** và có URL theo dõi, hoặc trả 503 khi chưa thể nhận; không trả 202 chỉ vì mong rằng request sẽ được xử lý về sau dù không có job đã được lưu. Với tác vụ đòi thời gian dài, quy định quota và idempotency ngay tại bước enqueue.

## 8. Client Java: hiểu Retry-After, backoff và deadline

### 8.1. Những điều kiện phải quyết định trước retry

Không retry chỉ vì nhìn thấy 429/503. Client nên kiểm:

1. **Thao tác có an toàn để gửi lại?** GET/HEAD theo contract chuẩn là safe; PUT/DELETE có semantics idempotent nhưng vẫn cần xem hành vi hệ thống. POST/PATCH dễ tạo side effect lặp và chỉ retry khi API thực sự hỗ trợ idempotency key hoặc có một cơ chế chống trùng được xác minh.
2. **Còn retry budget không?** Giới hạn số lần, tổng timeout, thời gian chờ và số request bổ sung. Không retry vô hạn.
3. **Có `Retry-After` không?** Parse số giây hoặc HTTP-date; nếu lớn hơn thời gian còn lại, dừng và báo lỗi/lên lịch sau thay vì gọi sớm.
4. **Có thể phân biệt lỗi tạm thời với lỗi cần sửa request không?** 401/403/400 thường không giải quyết bằng backoff. 429 làm giảm tốc theo principal/key quota; 503 cần backoff có jitter và có thể failover.
5. **Có nhiều request đồng thời không?** Cùng một client nên phối hợp rate limiting; nhiều client cùng retry 503 cần jitter để tránh tạo thundering herd.

Java 17 `HttpClient` có thể đọc header; hàm sau hỗ trợ hai dạng `Retry-After`:

~~~java
import java.net.http.HttpResponse;
import java.time.Duration;
import java.time.Instant;
import java.time.ZonedDateTime;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;
import java.util.Optional;

class RetryAdvice {
    static Optional<Duration> retryAfter(
        HttpResponse<?> response, Instant receivedAt
    ) {
        Optional<String> raw = response.headers()
            .firstValue("Retry-After");

        if (raw.isEmpty()) {
            return Optional.empty();
        }

        String value = raw.get().trim();

        try {
            long seconds = Long.parseLong(value);
            if (seconds >= 0) {
                return Optional.of(Duration.ofSeconds(seconds));
            }
        } catch (NumberFormatException ignored) {
            // Có thể là ngày HTTP.
        }

        try {
            Instant target = ZonedDateTime.parse(
                value, DateTimeFormatter.RFC_1123_DATE_TIME)
                .toInstant();
            Duration remaining = Duration.between(receivedAt, target);
            return Optional.of(
                remaining.isNegative() ? Duration.ZERO : remaining);
        } catch (DateTimeParseException ignored) {
            return Optional.empty();
        }
    }
}
~~~

Dùng `Instant` tại **thời điểm nhận response**. Với hệ thống có chênh lệch đồng hồ đáng kể, xem xét `Date` response và giới hạn tin cậy theo thiết kế. Header HTTP có thể quá lớn/bất thường; parse lỗi thì áp dụng fallback an toàn, không biến thành exception làm hỏng luồng retry. `Optional.empty()` nghĩa không có lời khuyên hợp lệ, **không** có nghĩa được retry ngay.

### 8.2. Backoff có jitter và tổng ngân sách

Khi thiếu `Retry-After`, có thể dùng exponential backoff kèm jitter:

`upperBound = min(maxDelay, baseDelay * 2^attempt)`

`delay = random(0, upperBound)`

Ví dụ với `baseDelay=500ms`, `maxDelay=10s`, các lượt retry có khoảng chờ ngẫu nhiên trong `[0, 0.5s]`, `[0, 1s]`, `[0, 2s]`...; nhiều client sẽ ít gửi lại đồng thời hơn. Đối với lỗi 429/503 có `Retry-After`, không đặt delay ngẫu nhiên khiến thời gian thực tế **ngắn hơn** chỉ dẫn của server; có thể cộng jitter nhỏ **sau** mốc tối thiểu nếu còn deadline.

Một phương thức retry minh họa ở mức thuật toán:

~~~text
deadline = thời điểm kết thúc ngân sách thao tác
attempt = 0

while attempt < maxAttempts:
    response = callWithPerAttemptTimeout()
    if response thành công:
        return response
    if status không thuộc nhóm có thể retry hoặc request không an toàn:
        return/raise lỗi

    minDelay = Retry-After hợp lệ nếu có; nếu không thì backoff+jitter
    if minDelay vượt thời gian còn lại trước deadline:
        return/raise lỗi kèm lời khuyên lịch hẹn
    chờ minDelay (có thể cộng jitter sau mốc tối thiểu)
    attempt += 1

return/raise lỗi hết ngân sách
~~~

Đây là pseudocode, không khuyên dùng `Thread.sleep` vô hạn trong servlet thread. Với hệ thống reactive/async nên dùng scheduler bất đồng bộ; với batch job có thể lưu lịch retry ở queue. Thời gian request timeout, timeout downstream và deadline chung cần **phối hợp** để một request không tồn tại lâu hơn ngân sách nghiệp vụ.

### 8.3. Retry POST và Idempotency-Key

Một POST tạo thanh toán/đơn hàng có thể đã được xử lý ở server trước khi kết nối bị ngắt. Nếu client lập tức gửi lại, có thể tạo trùng. Nếu API hỗ trợ `Idempotency-Key`:

~~~http
POST /api/orders HTTP/1.1
Host: api.example.test
Authorization: Bearer example-access-token
Content-Type: application/json
Idempotency-Key: order-create-7c8e

{"sku":"JAVA-BOOK","quantity":1}
~~~

Server cần lưu key **cùng caller/tenant, endpoint, fingerprint body**, phân biệt request trùng và request sử dụng lại key cho payload khác, và đưa cùng kết quả theo contract. Client **giữ nguyên key** khi retry cùng thao tác. Nếu 429 được trả **trước** khi thực thi nghiệp vụ, request đó chưa tạo side effect; nhưng nếu đã có timeout không rõ kết quả hay proxy trung gian thì phải coi kết quả là không chắc chắn. Chỉ retry POST/PATCH theo một hợp đồng idempotency đã được kiểm chứng. Quota và idempotency có thể cần thứ tự xử lý được định nghĩa: request replay đã được ghi nhận có tiêu tốn quota không là lựa chọn hợp đồng, cần nhất quán.

## 9. Vận hành: đo lường 429 và 503 riêng

Một dashboard chỉ có tỷ lệ “4xx/5xx” sẽ không giải thích được tại sao người dùng bị gián đoạn. Tối thiểu hãy đo:

| Tín hiệu | 429 | 503 |
|---|---|---|
| Tỷ lệ lỗi theo route, status và nguồn phát lỗi (gateway/app) | Có | Có |
| Khóa quota đã **băm/ẩn danh** hoặc phân loại client/tenant/plan | Quan trọng để phát hiện noisy neighbor và sai cấu hình | Hữu ích để thấy phạm vi ảnh hưởng |
| Số token còn lại, refill, loại quota, burst | Cốt lõi | Không phải nguyên nhân mặc định |
| Request in-flight, queue depth, pool utilization | Có thể ảnh hưởng | Cốt lõi |
| p95/p99 latency, timeout, connection errors | Theo dõi tác dụng phụ | Cốt lõi |
| Retry attempt/success, thời gian chờ, retry budget exhausted | Phát hiện client retry quá nhanh | Phát hiện retry storm và năng lực phục hồi |
| Dependency health, circuit breaker state, DB pool | Không giải thích 429 thông thường | Cốt lõi |
| Số request được shed, lỗi theo instance/region | Theo quota key nếu có | Cốt lõi |
| Time to recover và hiệu quả `Retry-After` | Xem client có tôn trọng quota | Xem phục hồi sau overload/bảo trì |

Không gắn user ID, access token hoặc IP đầy đủ vào metric labels: cardinality cao và nguy cơ lộ thông tin. Dùng nhóm tenant/gói hoặc mã đã băm trong log truy vết có phân quyền; metrics nên dùng các chiều có cardinality kiểm soát. Ghi `requestId`, route template, status, lý do `rate_limit_exceeded`/`overloaded`, layer phát lỗi, policy ID và thời gian xử lý.

**Cảnh báo 429:** một client tăng đột biến có thể là scraper, retry loop hoặc API tích hợp sai. Nếu tất cả client cùng gặp 429 sau khi cấu hình hạn mức thay đổi, có thể là deploy lỗi hoặc quota store bị dùng chung sai key; đừng chỉ trách consumer.

**Cảnh báo 503:** nhiều client đồng thời, tail latency tăng, pool/queue bão hòa, health check thất bại. Có thể giảm tải, mở rộng năng lực, bật cache, shed từ gateway, chuyển lưu lượng hoặc rollback tùy nguyên nhân. Đừng khắc phục 503 bằng cách tăng timeout vô hạn: request đang chờ càng lâu càng giữ tài nguyên và làm hệ thống khó hồi phục.

### 9.1. Chính sách fail-open/fail-closed khi limiter hỏng

Nếu Redis giữ quota mất kết nối, hệ thống cần quyết định riêng: chấp nhận tạm (fail-open) để giữ availability cho endpoint ít rủi ro, hay từ chối (fail-closed) đối với thao tác chi phí cao/chống abuse nghiêm ngặt. Quyết định ảnh hưởng fairness, chi phí và an toàn; phải được tài liệu hóa và quan sát. Nếu không thể phục vụ vì chính thành phần quản lý quota gây lỗi hạ tầng, **503 có thể trung thực hơn 429**, vì không có bằng chứng consumer đã vượt quota.

### 9.2. Cache lỗi và áp lực lên downstream

429 theo RFC 6585 không được lưu ở HTTP cache. Với 503, `Cache-Control: no-store` là lựa chọn thận trọng cho phản hồi phụ thuộc tình trạng tức thời, tránh CDN giữ lại phản hồi lỗi sau khi service đã phục hồi. Nếu edge được cấu hình negative caching cho 5xx, phải có TTL/invalidation được chủ động kiểm soát. Dữ liệu riêng theo user/tenant không được đưa vào shared cache dù response header có giá trị hỗ trợ retry.

Có thể phục vụ dữ liệu cached **còn phù hợp** cho endpoint đọc công khai hoặc trả kết quả “stale” theo hợp đồng đã xác định khi upstream lỗi, nhưng không tự trả dữ liệu đã hết hạn cho thanh toán, quyền truy cập hoặc tồn kho có yêu cầu consistency cao. Nếu làm như vậy, ghi rõ freshness/semantics trong response.

## 10. Kiểm thử HTTP/Spring và thử nghiệm dưới tải

### 10.1. Kiểm thử đơn vị bucket

Với bucket `capacity=5, refill=1/s`, cần ít nhất các ca:

1. Năm lần `take(clientA)` liên tiếp được phép; lần thứ sáu bị từ chối với thời gian chờ dương.
2. `clientB` vẫn còn quota khi A đã bị chặn.
3. Sau khi tiến đồng hồ mô phỏng thêm một giây, A nhận được token mới.
4. Gửi đồng thời nhiều thread trên cùng key không được cấp nhiều hơn capacity.
5. Burst lớn không làm bucket vượt capacity sau refill.
6. Key với tenant/client khác được tách đúng; input không tin cậy không thể tự ý chọn key.

Mẫu in-memory ở mục 7 dùng `System.nanoTime()`, thích hợp để giải thích thuật toán; để test thời gian **deterministic**, hãy đưa nguồn thời gian monotonic thành dependency có thể điều khiển rồi giả lập elapsed, tránh dùng `Thread.sleep` trong unit test. Với limiter phân tán, thêm integration test chạy nhiều instance và Redis thật, xác nhận hành vi atomic và quota xuyên instance.

### 10.2. MockMvc cho phản hồi 429

Giả sử `OrderController`, `ApiErrorHandler` và SecurityFilterChain đã được nạp vào test context; mock `InMemoryClientQuota` và `OrderReader` để kiểm response mà không phụ thuộc thời gian thực. Ví dụ với Spring Boot 3.x dùng `@MockBean` (ở các stack mới có thể dùng `@MockitoBean` tương ứng):

~~~java
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.when;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class QuotaHttpTest {
    @Autowired MockMvc mvc;
    @MockBean InMemoryClientQuota quota;
    @MockBean OrderReader orders;

    @Test
    void quotaExceededReturns429AndRetryAfter() throws Exception {
        when(quota.take(anyString()))
            .thenReturn(new QuotaDecision(false, 3));

        mvc.perform(get("/api/orders")
                .with(jwt()
                    .jwt(j -> j.issuer("https://login.example.test")
                               .subject("user-42"))
                    .authorities(new SimpleGrantedAuthority(
                        "SCOPE_orders.read"))))
            .andExpect(status().isTooManyRequests())
            .andExpect(header().string("Retry-After", "3"))
            .andExpect(header().string("Cache-Control",
                org.hamcrest.Matchers.containsString("no-store")))
            .andExpect(jsonPath("$.code")
                .value("CLIENT_RATE_LIMITED"));
    }
}
~~~

Test này kiểm **mapping quota → HTTP** và rule Spring được nạp, chưa chứng minh chữ ký, issuer/audience hoặc expiry của JWT thật; `jwt()` tạo principal giả. Bổ sung test tích hợp Resource Server qua bearer token được ký bằng test key/JWKS, token có `aud` sai, scope thiếu và token hết hạn. Cần bảo đảm request không hợp lệ bị chặn theo 401/403 trước khi tiêu tốn quota user đã xác minh nếu đó là contract của API.

### 10.3. Test 503 không phụ thuộc quota

Tạo một test route được bảo vệ bởi `HeavyWorkBulkhead` có đúng một slot. Giữ một tác vụ đang chạy bằng latch, gửi request thứ hai từ **client khác chưa hết quota**, rồi kiểm:

~~~http
HTTP/1.1 503 Service Unavailable
Content-Type: application/problem+json
Cache-Control: no-store

{"status":503,"code":"SERVICE_OVERLOADED"}
~~~

Không yêu cầu header `Retry-After` nếu server không có dự đoán phục hồi. Sau khi giải phóng slot, request mới thành công, và semaphore count không bị rò khi code nghiệp vụ ném exception. Test 503 do **planned maintenance** có thể gắn một `Retry-After` cố định do lịch đã biết; kiểm thời gian/định dạng thay vì chỉ kiểm status.

### 10.4. Ma trận kiểm thử tích hợp

| Kịch bản | Kỳ vọng HTTP | Điều cần xác minh thêm |
|---|---|---|
| Client A gọi vượt quota, B còn quota | A: 429; B: 2xx | Quota key cô lập, Retry-After hợp lệ |
| Client A hết quota nhưng API vẫn khỏe | A: 429 | Không nhầm thành 503 |
| CPU/queue chung bão hòa, B còn quota | 503 cho request bị shed | Không trừ quota sai thứ tự ngoài contract |
| Maintenance mode | 503; Retry-After nếu biết dự kiến | Không nhận request ghi và trả nhầm 200 |
| Token hết hạn / thiếu scope | 401 / 403 | Không trả 429/503 che lỗi xác thực |
| Gateway nhận response upstream không hợp lệ | 502 | Đúng tầng phát lỗi |
| Gateway hết thời gian chờ upstream | 504 | Có correlation ID và timeout budget |
| Burst đồng thời qua nhiều instance | 429 theo giới hạn chung | Kho quota atomic, không mỗi node cộng quota |
| `Retry-After` số giây hoặc HTTP-date | Client tính delay hợp lệ | Không hiểu số giây thành ms |
| `Retry-After` vượt deadline | Client không retry trước hạn | Chuyển lỗi hoặc lên lịch sau |
| 503 hàng loạt cho nhiều client | Retry được jitter | Không tạo thundering herd |
| POST sau timeout không rõ trạng thái | Không tạo đơn/thanh toán trùng | Server hỗ trợ idempotency khi retry |
| 429/503 với CDN ở giữa | Header/body/status không bị cache sai | 429 không lưu; 503 theo policy |
| Quota store mất kết nối | Chính sách fail-open/closed rõ | Không gán nhầm lỗi Redis thành “client hết quota” |
| Kết thúc overload, slot có lại | 2xx | Bulkhead không rò permit |
| User/tenant khác nhau cùng Origin | Chính sách riêng | Không lộ quota hoặc dữ liệu giữa tenant |

### 10.5. Thử tải có kiểm soát

Thử ở staging hoặc môi trường tách biệt, có ngưỡng dừng:

- **Kịch bản quota:** Cho A tăng RPS qua ngưỡng nhưng giữ B dưới ngưỡng; kiểm 429 của A, 2xx của B, số request thành công đúng burst/refill và không có side effect ở 429.
- **Kịch bản overload:** Giới hạn số slot ở mức nhỏ, tạo tác vụ chậm để tăng in-flight; kiểm 503 được phát nhanh, tail latency không tăng vô hạn và dịch vụ phục hồi sau khi tải giảm.
- **Kịch bản retry storm:** Có/không có `Retry-After`, hàng trăm client giả lập nhận 503; so sánh QPS retry khi dùng jitter và khi retry đồng thời.
- **Kịch bản dependency:** Giả lập DB chậm/mất kết nối, circuit breaker mở; kiểm chỉ route phụ thuộc bị ảnh hưởng nếu kiến trúc cho phép, gateway 502/504 được phân biệt với 503.
- **Kịch bản failover:** Drain một instance, kiểm readiness/load balancer chuyển traffic, và request in-flight không tạo duplicate side effect.

Dừng thử tải khi có dấu hiệu ảnh hưởng dữ liệu thật hoặc vượt giới hạn an toàn được định nghĩa. Không dùng các thao tác tốn tài nguyên thực tế trong bài test đơn giản chỉ để chứng minh header HTTP.

## 11. Bài tập thực hành

### Bài tập 1: chọn status và cách client phản ứng

Với mỗi trường hợp, chọn 429, 503, 502, 504, 401 hoặc 403 và giải thích:

1. User A dùng hết 10 lần xuất CSV mỗi giờ; user B xuất bình thường.
2. Cluster chỉ còn 0 slot xử lý, nhiều user chưa dùng hết quota.
3. API Gateway không nhận response từ payment-service trước 3 giây.
4. Gateway nhận response HTTP không hợp lệ từ một upstream.
5. Token của A hết hạn.
6. Token hợp lệ nhưng không có scope `reports.read`.

**Gợi ý:** 1→429, 2→503, 3→504, 4→502, 5→401, 6→403. Với request có quyền theo đối tượng/tenant, còn phải kiểm ownership; có thể dùng 404 che giấu tài nguyên không được phép theo contract.

### Bài tập 2: tính token bucket

Một client có bucket `B=4`, refill `r=2 token/giây`, mỗi request tốn 1 token. Tại `t=0`, bucket đầy và client gửi 5 request tức thời. Tại `t=0.5s`, client gửi tiếp 2 request. Hãy tính request nào được chấp nhận, request nào bị 429 và thời gian chờ tối thiểu khi cần.

**Gợi ý:** Tại `t=0`, bốn request đầu hợp lệ, request thứ năm bị 429. Tới `t=0.5s`, có khoảng một token, nên trong hai request tiếp chỉ một request được chấp nhận; request còn lại cần chờ thêm khoảng 0.5s để có một token mới. Giả định không có request nào khác chen vào bucket.

### Bài tập 3: sửa retry storm

Client Java đang xử lý cả 429 và 503 bằng vòng lặp `while (true) { request(); }` và gửi lại mọi POST không có `Idempotency-Key`. Viết pseudocode mới hỗ trợ `Retry-After` dạng số giây/ngày, exponential backoff+jitter, `maxAttempts`, overall deadline, giới hạn retry theo phương thức và cơ chế idempotency thực sự của server.

**Tiêu chí đạt:** Không gửi lại sớm hơn `Retry-After`; không retry vô hạn; không lặp POST có side effect nếu không được bảo đảm; biết dừng khi Retry-After vượt deadline.

### Bài tập 4: phân biệt limiter với bulkhead trong Spring

Từ hai mẫu Java ở trên, hãy thiết kế một endpoint `GET /api/reports/{id}` có quota theo tenant 30 request/phút và slot nặng chung 8 tác vụ. Mô tả thứ tự kiểm membership, quota, slot và quyền trên report. Tạo bộ kiểm thử hai tenant: A vượt quota nhưng B còn dưới quota; B chưa vượt quota nhưng cả tám slot chung đang bận.

**Tiêu chí đạt:** A nhận 429 do quota; B nhận 503 khi slot chung đầy; request được từ chối không có side effect; kiểm tra tenant/owner vẫn bắt buộc.

### Bài tập 5: thiết kế response và observability

Một hệ thống ghi tất cả lỗi vào counter `http_errors_total` và trả body `{"message":"Try again"}` cho cả 429/503. Hãy thiết kế `application/problem+json` cho từng loại, `requestId`, Retry-After phù hợp và các metric/trace attributes cho dashboard. Đề xuất một cảnh báo quota bị cấu hình sai (tất cả client cùng nhận 429) và một cảnh báo overload (503 tăng cùng queue depth/p99 latency).

**Tiêu chí đạt:** Nguyên nhân, status, policy và layer phát lỗi đo được độc lập; không log access token hay đưa user ID vào metric label có cardinality không giới hạn.

### Bài tập 6: bảo vệ tính đúng đắn khi retry thao tác tạo đơn

Một client gọi `POST /api/orders`, request đã xử lý ở server nhưng response bị mất; client nhận timeout, sau đó thấy 503 khi retry. Thiết kế luồng dùng `Idempotency-Key` để client có thể tiếp tục cùng thao tác mà không tạo đơn trùng. Cho biết quota sẽ tính request replay như thế nào, các khóa có ràng buộc tenant/caller không, và phải trả lỗi gì khi cùng key nhưng payload khác.

**Tiêu chí đạt:** Phân biệt “server chưa trả response” với “server chưa xử lý”; key ổn định trong toàn bộ lần thử lại; kiểm replay ở server; không dựa vào việc chỉ retry khi thấy 429/503 để bảo đảm không trùng side effect.

## 12. Câu hỏi tự kiểm tra

1. **429 có nghĩa server bị hỏng không?** Không. Thường caller vượt quota; server có thể vẫn phục vụ bình thường cho các client khác.
2. **503 có nghĩa user dùng quá nhiều API không?** Không. 503 mô tả service tạm thời không thể phục vụ request hợp lệ do overload hoặc maintenance.
3. **Cả 429 và 503 có thể mang Retry-After không?** Có, và header có thể vắng mặt; phải hỗ trợ delay-seconds lẫn HTTP-date.
4. **Retry-After: 60 là 60ms hay 60 giây?** Là 60 giây.
5. **Nếu Retry-After dài hơn deadline, có nên retry sớm?** Không. Dừng/đưa yêu cầu lên scheduler hoặc thông báo caller.
6. **504 khác 503 thế nào?** 504 là gateway/proxy chờ upstream quá hạn; 503 là service tạm không sẵn sàng.
7. **Tại sao cần jitter?** Giảm số client thức dậy và gửi retry cùng một lúc.
8. **Cần thêm gì để retry POST?** Hợp đồng idempotency hoặc cơ chế chống trùng có xác minh ở server; chỉ gửi lại nguyên request với cùng key khi an toàn.
9. **Một token bucket đặt trong mỗi pod đủ cho hạn mức toàn hệ thống không?** Không. Nếu cần quota chung, phải có limiter/kho chia sẻ atomic hoặc gateway thực thi nhất quán.
10. **429/503 có thay việc kiểm authorization không?** Không. Authentication, scope, tenant và quyền trên resource vẫn cần được thực thi theo pipeline đáng tin.

## 13. Tài liệu chuẩn và checklist

Nguồn tham khảo:

- **RFC 6585, mục 4 — 429 Too Many Requests:** https://www.rfc-editor.org/rfc/rfc6585#section-4
- **RFC 9110, mục 10.2.3 — Retry-After:** https://www.rfc-editor.org/rfc/rfc9110#section-10.2.3
- **RFC 9110, mục 15.6.4 — 503 Service Unavailable:** https://www.rfc-editor.org/rfc/rfc9110#section-15.6.4
- **RFC 9110, mục 15.6.3/15.6.5 — 502 Bad Gateway và 504 Gateway Timeout:** https://www.rfc-editor.org/rfc/rfc9110
- **RFC 9457 — Problem Details for HTTP APIs:** https://www.rfc-editor.org/rfc/rfc9457
- **RFC 9111 — HTTP Caching:** https://www.rfc-editor.org/rfc/rfc9111
- **Spring Security Reference — OAuth 2.0 Resource Server:** https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/index.html
- **Spring Framework Reference — Error Responses/ProblemDetail:** https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-rest-exceptions.html

Checklist khi thiết kế một endpoint có rate limiting và resilience:

- Có định nghĩa **quota key**, window/refill, burst, chi phí request và chính sách theo client/tenant/route?
- Phân biệt được **429 do quota của caller** với **503 do năng lực dịch vụ tạm thiếu**, cùng 502/504 do gateway?
- Có hướng dẫn `Retry-After` hợp lệ khi dự đoán được thời gian; không đưa thời gian giả?
- Client có backoff+jitter, tổng deadline, bounded retries và xử lý an toàn POST/PATCH qua idempotency?
- Shared limiter có xử lý concurrency giữa các instance và failure của quota store theo chính sách?
- API vẫn xác minh access token, scope, tenant/ownership; các request bị chặn không tạo side effect?
- Có metrics/log/traces tách lỗi quota, overload, gateway và dependency, không lộ bí mật?
- Response lỗi không bị CDN cache sai; 429 tuân theo quy tắc không lưu của RFC 6585?
- Đã kiểm thử tình huống **một client vượt quota nhưng service khỏe** và **service quá tải với client chưa vượt quota**?

**Điểm mấu chốt:** **429 nói về hạn mức sử dụng của caller**, còn **503 nói về khả năng phục vụ tạm thời của hệ thống**. HTTP status, `Retry-After`, chính sách retry, idempotency và tín hiệu vận hành phải cùng thể hiện đúng nguyên nhân để REST API vừa công bằng vừa có khả năng phục hồi.
