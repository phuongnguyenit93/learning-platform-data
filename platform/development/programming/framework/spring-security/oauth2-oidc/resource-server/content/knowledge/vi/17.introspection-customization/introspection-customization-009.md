# Thử lại có giới hạn, quá tải và chính sách lỗi không bỏ qua xác minh

Trong **Spring Security OAuth 2.0/OIDC Resource Server**, một API có thể nhận **opaque access token** và gọi **Authorization Server** qua OAuth 2.0 Token Introspection (RFC 7662) để xác định token đang hoạt động hay đã bị thu hồi, cùng các thuộc tính như `scope`, `sub`, `aud` và `exp`. Cách làm này cho phép Resource Server dựa vào nguồn thông tin tập trung, nhưng cũng tạo ra một phụ thuộc vận hành: nếu introspection endpoint chậm, quá tải hoặc không thể truy cập, việc xác thực Bearer token có thể bị ảnh hưởng trên mọi request liên quan.

Giải pháp không phải là **thử lại vô hạn** hoặc **tạm bỏ qua xác minh để API tiếp tục trả dữ liệu**. Cần xác định một chính sách rõ ràng cho **timeout, thử lại có giới hạn, giảm tải, circuit breaker, cache và phân loại lỗi**. Dù chính sách ưu tiên tính sẵn sàng đến đâu, Resource Server không được biến một token **chưa được xác minh** thành một principal đã xác thực.

Bài học này tập trung vào đề mục **“Thử lại có giới hạn, quá tải và chính sách lỗi không bỏ qua xác minh”** trong chương **Tùy chỉnh introspection**, thuộc module **Spring Security OAuth 2.0 OIDC Resource Server**. Nội dung trình bày từ cơ chế introspection, mô hình lỗi, thiết kế resilience, ví dụ triển khai Spring Security Servlet/WebFlux đến kiểm thử các tình huống quá tải.

> Phạm vi chủ yếu là OAuth 2.0 **Bearer access token**. Dù tên cấu hình Spring Security là `opaqueToken()`, đường xác thực bằng introspection cũng có thể được sử dụng cho **JWT access token** khi Authorization Server hỗ trợ. Việc định dạng token là JWT hay opaque không thay đổi nguyên tắc **không chấp nhận token khi chưa có bằng chứng xác thực đáng tin**.

## 1. Introspection là một phần của đường đi xác thực

Client gọi Orders API:

~~~http
GET /api/orders/42 HTTP/1.1
Host: orders-api.example.test
Authorization: Bearer <ACCESS_TOKEN>
Accept: application/json
~~~

Một Resource Server dựa vào introspection thường xử lý theo chuỗi:

~~~mermaid
sequenceDiagram
    participant C as Client
    participant R as Spring Security Resource Server
    participant A as Authorization Server
    C->>R: GET /api/orders/42 + Bearer token
    R->>A: POST /introspect (token, client authentication)
    A-->>R: HTTP 200 + active=true, scope, aud, exp...
    R->>R: Validate attributes + create principal
    R->>R: HTTP/method/domain authorization
    R-->>C: API response nếu được phép
~~~

Request introspection theo RFC 7662:

~~~http
POST /oauth2/introspect HTTP/1.1
Host: login.example.test
Authorization: Basic <INTROSPECTION_CLIENT_CREDENTIALS>
Content-Type: application/x-www-form-urlencoded
Accept: application/json

token=<ACCESS_TOKEN>&token_type_hint=access_token
~~~

Response ví dụ khi token active:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store

{
  "active": true,
  "scope": "orders.read",
  "sub": "user-123",
  "client_id": "orders-web",
  "aud": "orders-api",
  "iss": "https://login.example.test/realms/company",
  "exp": 1924992000
}
~~~

Khi token không được Authorization Server công nhận:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "active": false
}
~~~

**HTTP 200 không đồng nghĩa token hợp lệ**: phải đọc `active`. Ngược lại, HTTP 503 hoặc timeout khi gọi introspection **không chứng minh token sai**; chúng cho biết Resource Server **chưa lấy được kết quả xác minh đủ tin cậy**.

### 1.1. Ba kết quả logic cần phân biệt

| Kết quả | Bằng chứng | Quyết định đối với request |
|---|---|---|
| **VALID** | Introspection hợp lệ, `active=true` và các điều kiện issuer/audience/expiry/profile phù hợp | Có thể tạo `Authentication` rồi tiếp tục phân quyền |
| **INVALID** | Introspection hợp lệ, `active=false` hoặc token không đạt điều kiện bắt buộc | Không tạo authentication thành công |
| **UNKNOWN / UNAVAILABLE** | Timeout, network lỗi, 5xx, 429, response không xử lý được, không xác minh được nguồn | Không tạo authentication thành công; phân loại lỗi hạ tầng riêng |

Điểm quan trọng: **UNKNOWN không được xem là VALID**. Chính sách có thể quyết định trả mã lỗi khác nhau cho caller hoặc dùng một kết quả **đã xác minh trước đó** trong giới hạn cache được phê duyệt, nhưng không được tự trả thành công chỉ vì Authorization Server tạm lỗi.

### 1.2. Phân biệt authentication và authorization

~~~text
Client Bearer token
     |
     v
OpaqueTokenIntrospector
     |
     +-- active=false / không xác minh được ---> KHÔNG xác thực
     |
     v
OAuth2AuthenticatedPrincipal + GrantedAuthority
     |
     v
HTTP authorization: SCOPE_orders.read?
     |
     v
Domain authorization: order có thuộc subject/tenant?
~~~

`active=true` chỉ là một bước. Resource Server còn phải áp chính sách phù hợp cho **issuer, audience, token type, thời hạn, scope và quyền trên tài nguyên**. Đừng vì quá tải mà chỉ kiểm tra `active` rồi bỏ các ràng buộc vốn bắt buộc.

## 2. Thử lại đúng lỗi: cần phân loại trước khi retry

Một retry có ích khi lỗi **tạm thời** có khả năng hết sau một khoảng ngắn. Nó gây hại khi lặp lại request mà kết quả đã chắc chắn, hoặc khi toàn bộ Authorization Server đang quá tải.

### 2.1. Bảng chính sách theo loại kết quả

| Tín hiệu từ introspection | Ý nghĩa thường gặp | Có nên tự động retry? | Quyết định xác thực |
|---|---|---|---|
| HTTP 200, `active=true`, metadata hợp lệ | Token được công nhận | **Không** | Xác thực và áp policy còn lại |
| HTTP 200, `active=false` | Token không active theo AS | **Không** | Từ chối token |
| HTTP 400 do request sai/thiếu tham số | Lỗi client gọi introspection | **Không** trước khi sửa cấu hình/code | Không xác thực |
| HTTP 401 do sai introspection client credentials | Credential/cấu hình hạ tầng sai | **Không** | Không xác thực; alert cấu hình |
| HTTP 403 do không có quyền introspect | Policy caller introspection không hợp lệ | **Không**, trừ thay đổi policy hợp lệ | Không xác thực; alert |
| HTTP 404 sai endpoint URI | Endpoint không tồn tại hoặc cấu hình sai | **Không** | Không xác thực |
| HTTP 429 Too Many Requests | AS yêu cầu giảm tải | **Rất hạn chế**, chỉ khi đã có hạn mức/budget và hướng dẫn retry phù hợp | Không tự cho qua |
| HTTP 500/502/503/504 | Lỗi server/proxy tạm thời có thể phục hồi | Có thể retry **tối đa số lần nhỏ**, có backoff/jitter | Không tự cho qua |
| Connect timeout/TLS handshake timeout | Mạng hoặc AS chưa khả dụng | Có thể retry có giới hạn nếu hợp đồng cho phép và còn deadline | Không tự cho qua |
| Read timeout | Không biết upstream đã xử lý request chưa | Chỉ retry nếu thao tác được xác nhận có ngữ nghĩa an toàn khi lặp và còn deadline | Không tự cho qua |
| DNS/TLS certificate invalid | Lỗi trust/transport | Thường **không** retry tức thì; alert | Không xác thực |
| JSON sai schema/không có `active` | Endpoint/protocol không đúng | **Không** lặp vô ích khi chưa biết nguyên nhân | Không xác thực |
| Introspection trả `active=true` nhưng thiếu `aud` bắt buộc | Thiếu bằng chứng dành cho API | **Không**; sửa hợp đồng/cấu hình | Không xác thực |

**Không retry chỉ dựa vào một exception chung**. Một số thư viện gói cả `active=false`, lỗi HTTP, lỗi deserialize và timeout thành những exception cùng họ. Muốn retry an toàn, cần phân loại ở **tầng HTTP/transport** hoặc có exception domain đã được chuẩn hóa trước khi gắn retry.

### 2.2. Tại sao không retry `active=false`?

`active=false` là **kết quả xác minh hợp lệ** của Authorization Server, không phải “thử lại chưa thành công”. Lặp lại có thể:

- Làm chậm phản hồi cho client có token sai.
- Tạo thêm tải trên Authorization Server đúng lúc đang cần phục vụ token hợp lệ.
- Tạo điều kiện token guessing/DDoS chiếm tài nguyên.
- Che giấu một token thực sự hết hạn hoặc bị revoke.

Với những token không active, Resource Server phải từ chối theo policy mà **không đặt chúng vào hàng đợi retry**.

### 2.3. Vì sao HTTP 401 từ introspection khác HTTP 401 gửi cho client?

Nếu Authorization Server trả:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Basic realm="introspection"
~~~

thường vấn đề là **Resource Server không xác thực được chính nó khi gọi introspection**, ví dụ client secret sai hoặc đã rotate. Đây không phải bằng chứng `active=false` của token được người dùng gửi.

Resource Server không được cho request đi tiếp; đồng thời cần alert **lỗi cấu hình/kết nối AS** thay vì gắn nhãn mọi client có token sai. Response gửi về client có thể là lỗi authentication hoặc lỗi dịch vụ tùy exception handling, nhưng dữ liệu nhạy cảm như client secret/Basic header không được trả ra.

### 2.4. Mã 429 và `Retry-After`

Một AS hoặc gateway có thể trả:

~~~http
HTTP/1.1 429 Too Many Requests
Retry-After: 2
~~~

Giá trị `Retry-After` là gợi ý thời điểm thử lại, **không phải lệnh bắt buộc phải chờ trong request hiện tại**. Chỉ retry nếu thời gian chờ và lần gọi tiếp theo **nằm trong tổng deadline** của request và chính sách chịu tải. Nếu `Retry-After` dài hơn budget, nên dừng thay vì giữ thread/connection cho một yêu cầu chắc chắn quá hạn.

`Retry-After` có thể là số giây hoặc HTTP-date; implementation cần parse an toàn, chặn giá trị âm/quá lớn/sai định dạng. Không lấy header tùy ý làm lệnh `sleep` không giới hạn.

## 3. Retry có giới hạn: ba ranh giới đồng thời

Để chống retry storm, không đủ đặt “retry 3 lần”. Một chính sách an toàn phải có **ba giới hạn**:

1. **Số lần thử tối đa**: bao gồm lần đầu và số lần retry.
2. **Tổng thời gian tối đa**: deadline cho *toàn bộ quá trình introspection*, không chỉ timeout của từng HTTP call.
3. **Số request đồng thời/budget retry toàn hệ thống**: giới hạn áp lực lên AS khi nhiều client cùng gặp lỗi.

Ví dụ hợp đồng minh họa:

~~~text
Per-attempt connection timeout:      200 ms
Per-attempt response timeout:        350 ms
Max total introspection time:        900 ms
Max attempts:                        2 (1 initial + 1 retry)
Backoff:                             random 50..150 ms
Retryable:                           select 502/503/504, known transient I/O
Never retry:                         active=false, 400/401/403/404
Retry on 429:                        normally no in-request retry,
                                     unless Retry-After fits budget and
                                     rate-limit policy explicitly allows
~~~

**Những con số trên là ví dụ**, không phải thông số mặc định của Spring Security, Nimbus, RFC 7662 hay SLA bắt buộc. Giá trị thực tế phụ thuộc p95/p99 của AS, request SLO, thread/connection pool và tải dự kiến.

### 3.1. “2 attempts” nghĩa là mấy HTTP calls?

Nên tránh cách gọi mơ hồ “retry 2 lần”:

~~~text
Maximum attempts = 2:
    attempt #1  → request đầu tiên
    attempt #2  → một lần retry nếu phù hợp
~~~

Nếu nói “2 retries” thì thường có thể hiểu là **3 attempts**. Hãy đặt tên cấu hình chính xác như `maxAttempts` và ghi rõ nó **bao gồm lần thử đầu**.

### 3.2. Tổng deadline quan trọng hơn tổng per-attempt timeout

Nếu mỗi lần HTTP timeout 2 giây và cho tối đa 3 attempts, một request có thể giữ tài nguyên 6 giây **chưa kể backoff**. Khi lượng request lớn, điều đó làm đầy hàng đợi và tăng thời gian phản hồi của mọi endpoint.

Với tổng deadline 900 ms:

~~~text
0 ms      request đến Resource Server
0–300 ms  attempt #1
300–400   backoff có jitter
400–750   attempt #2
750–900   dư địa xử lý/cleanup
~~~

Nếu attempt #1 đã dùng 800 ms, không được retry thêm 350 ms chỉ vì “chưa hết số lần”. Retry chỉ được phép khi **còn deadline và tài nguyên cho attempt hợp lệ tiếp theo**.

### 3.3. Backoff và jitter giảm đồng bộ retry

Một công thức minh họa:

~~~text
baseDelay(attempt) = min(maxDelay, initialDelay × 2^(attempt-1))
actualDelay        = random(0, baseDelay(attempt))
~~~

Jitter giúp nhiều Resource Server instance **không đồng loạt retry tại cùng một thời điểm**. Nhưng jitter **không thay thế bulkhead/rate limit**: khi có 100.000 request cùng chờ introspection, kể cả backoff ngẫu nhiên vẫn có thể tạo tổng tải vượt sức AS.

### 3.4. Retry POST introspection: cần xác nhận ngữ nghĩa

RFC 7662 dùng HTTP POST; thao tác introspection về bản chất **hỏi thông tin**, không phải yêu cầu cấp hay revoke token. Trong nhiều triển khai, lặp lại introspection không thay đổi token state. Tuy nhiên, **không mặc định mọi HTTP POST đều được retry**: AS có thể ghi audit, áp rate-limit, tính phí hoặc thực hiện logic riêng.

Trước khi retry read timeout, cần xác nhận **endpoint introspection cụ thể** hỗ trợ request lặp lại và không tạo hiệu ứng bất ngờ. Đặc biệt **không tái sử dụng cùng chính sách retry** cho token issuance, refresh-token grant hoặc token revocation chỉ vì chúng cũng là HTTP POST.

## 4. Quá tải và hiệu ứng khuếch đại

Một hệ thống có 20 Resource Server instances, mỗi instance nhận 100 request/s cần introspect, có thể tạo:

~~~text
20 instances × 100 authenticated requests/s
= 2.000 introspection requests/s
~~~

Nếu mỗi request được phép **3 attempts**, một sự cố 503 có thể tăng mức yêu cầu tiềm năng đến:

~~~text
2.000 requests/s × 3 attempts
= 6.000 outbound attempts/s
~~~

Đây là **tải thử yêu cầu tiềm năng**, không phải số hoàn tất chính xác: còn phụ thuộc deadline, concurrency, queue, rate-limit và thời điểm retry. Nhưng nó minh họa vì sao retry thiếu điều kiện có thể làm outage của AS **trở nên nặng hơn**, đồng thời làm đầy thread pool của chính Resource Server.

### 4.1. Retry storm

~~~mermaid
flowchart TD
    U["Lượng request vào API tăng"] --> R["Resource Server instances"]
    R --> A["Authorization Server introspection"]
    A -->|"timeout/503"| B["Tự động retry không giới hạn"]
    B -->|"Thêm HTTP calls"| A
    B -->|"Giữ thread/connection"| R
    R --> C["Queue dài, request timeout, lỗi dây chuyền"]
~~~

Đừng coi retry là “cố gọi cho đến khi AS hoạt động”. Khi upstream đã quá tải, **giảm áp lực** là điều kiện để hệ thống phục hồi.

### 4.2. Little's Law và lượng request đang chờ

Theo cách tính gần đúng:

~~~text
inFlight ≈ arrivalRate × averageTimeInSystem
~~~

Nếu một service nhận 500 request/s và introspection mất trung bình 0,1 giây, khoảng 50 yêu cầu có thể đang chờ. Khi AS chậm lên 2 giây, số yêu cầu chờ có thể tăng lên khoảng 1.000 nếu không giới hạn concurrency. Đây là **mô hình minh họa** cho quan hệ tải và latency, không phải capacity guarantee.

Từ đó cần cơ chế **bulkhead/concurrency limit**, request queue có giới hạn, timeout phù hợp và quan sát pool/queue saturation.

### 4.3. Phân biệt sự cố riêng lẻ và outage diện rộng

| Dấu hiệu | Cách phản ứng phù hợp |
|---|---|
| Vài lỗi 503 trong khi p95 latency bình thường | Có thể thử một retry ngắn có jitter |
| Tỷ lệ 503 tăng cao trên nhiều instance | Giảm/khóa retry, mở circuit breaker, không tạo thêm tải |
| HTTP 429 liên tục | Respect rate limit, giảm concurrency; không đổ thêm retry vào AS |
| Connect timeout đồng loạt | Coi là network/upstream incident, không giữ request chờ vô hạn |
| Client credentials sai | Cấu hình/secret incident; không retry mãi |
| `active=false` tăng nhiều | Có thể nhiều token invalid; không retry, kiểm tra nguồn phát hành và khả năng abuse |

## 5. Timeout phải gắn với request budget

Một request API có thể cần nhiều thao tác:

~~~text
Gateway → TLS → Spring Security introspection → Controller
        → Database → Downstream service → JSON response
~~~

Nếu request SLO tổng là 2 giây mà introspection dùng đến 1,9 giây, controller/service có rất ít thời gian còn lại. Vì vậy cần phân bổ budget:

~~~text
End-to-end request budget:             2.000 ms
Introspection total budget:              500 ms
Business logic + DB/downstream budget: 1.000 ms
Gateway/serialization/other:             500 ms
~~~

Giá trị trên minh họa cách đặt giới hạn, không phải phải phân phối chính xác theo các tỷ lệ này. Nếu Authorization Server bình thường đã cần 500 ms p99, phải cân đối thiết kế tải, SLA, cache và latency thực tế trước khi chọn giới hạn.

### 5.1. Các loại timeout khác nhau

| Loại | Ý nghĩa | Nếu bỏ qua |
|---|---|---|
| Connection timeout | Giới hạn thời gian mở kết nối | Giữ request khi upstream không đến được |
| TLS handshake timeout | Giới hạn bắt tay TLS | Kẹt trong cấu hình TLS/network |
| Response/read timeout | Giới hạn chờ dữ liệu từ endpoint | Chờ AS trả response vô hạn |
| Connection pool acquisition timeout | Giới hạn chờ lấy kết nối từ pool | Hàng đợi ứng dụng phình to |
| **Total operation deadline** | Giới hạn cả attempts + backoff + overhead | Retry kéo dài vượt HTTP request SLO |

Không nhầm timeout của một `RestClient`/`WebClient` request đơn lẻ với **deadline tổng thể**. Tại WebFlux, Reactor timeout bao quanh toàn bộ publisher có thể là một tầng bảo vệ bổ sung, nhưng cần đặt nó sao cho tài nguyên/connection được hủy và exception được phân loại đúng.

### 5.2. Timeout không đồng nghĩa token sai

Khi introspection timeout:

~~~text
Đúng:
    UNKNOWN / UNAVAILABLE
    → không tạo principal
    → chính sách error phù hợp
    → metric upstream_timeout

Sai:
    UNKNOWN
    → assume active=true
    → tạo principal và authorities giả
~~~

Resource Server có thể dùng kết quả cache **đã xác minh từ trước** nếu hệ thống cho phép và nó vẫn trong giới hạn hiệu lực/freshness, nhưng điều đó khác về bản chất với việc bỏ xác minh.

## 6. Chính sách lỗi: fail closed không đồng nghĩa luôn trả cùng một HTTP status

**Fail closed** trong authentication có nghĩa: **khi không có bằng chứng xác minh token đáng tin cậy, hệ thống không cấp quyền cho request**. Điều này không bắt buộc mọi nguyên nhân từ chối đều được truyền đến client dưới cùng một mã 401, cũng không cho phép tiết lộ nội dung nội bộ của introspection.

### 6.1. Phân biệt INVALID và UNAVAILABLE ở cửa API

Một cách thiết kế response:

| Tình huống nội bộ | Tình trạng xác thực | HTTP response đề xuất theo hợp đồng |
|---|---|---|
| Không có Bearer token trên endpoint yêu cầu auth | Chưa xác thực | 401, Bearer challenge phù hợp |
| `active=false` | Token invalid | 401, `invalid_token` |
| Token đã được xác thực nhưng thiếu scope | Auth thành công, authorization thất bại | 403, `insufficient_scope` nếu phù hợp |
| Introspection timeout/AS 503, không có cache được phép | Không thể xác minh | Có thể 503/502 hoặc lỗi phù hợp với hạ tầng; **không được trả dữ liệu bảo vệ** |
| Introspection caller bị 401 do client secret sai | Lỗi cấu hình Resource Server | Alert vận hành; không cho request qua, không lộ credential |
| Circuit breaker đang mở | Introspection không khả dụng trong giai đoạn đó | Từ chối trước khi gọi AS; có thể 503 theo thiết kế |
| Response sai schema/không có `active` | Không có kết quả xác minh hợp lệ | Không tạo principal; báo lỗi protocol/AS nội bộ |

Lựa chọn chính xác giữa 401 và 503 đối với lỗi hạ tầng phụ thuộc exception mapping và **hợp đồng API**. Spring Security và các thư viện có thể mặc định ném lỗi khiến response cụ thể khác ví dụ. Điều cần giữ bất biến là: **không xem timeout/503/circuit-open như `active=true`**.

### 6.2. Ba ví dụ phản hồi

Token invalid theo AS:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
Cache-Control: no-store
~~~

Principal xác thực nhưng thiếu authority:

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope"
Cache-Control: no-store
~~~

Hạ tầng introspection không khả dụng, khi hệ thống chọn biểu diễn lỗi dịch vụ:

~~~http
HTTP/1.1 503 Service Unavailable
Cache-Control: no-store
Content-Type: application/json

{
  "code": "AUTHENTICATION_SERVICE_UNAVAILABLE",
  "message": "Authentication cannot be completed."
}
~~~

Đây là **response policy minh họa**, không phải các response tự sinh từ mọi cấu hình `OpaqueTokenIntrospector`. Nếu tùy biến handler để phát 503, cần đảm bảo lỗi vẫn **dừng request** ở security boundary và không bị bắt bởi fallback cho phép.

Không trả ra các thông tin như:

~~~json
{
  "token": "<ACCESS_TOKEN>",
  "clientSecret": "<INTROSPECTION_SECRET>",
  "introspectionErrorBody": "<RAW_INTERNAL_RESPONSE>"
}
~~~

### 6.3. Phản ví dụ nguy hiểm: fail open

~~~java
// PHẢN VÍ DỤ: tuyệt đối không tạo principal khi introspection lỗi.
try {
    return delegate.introspect(token);
} catch (Exception ex) {
    return new DefaultOAuth2AuthenticatedPrincipal(
        "unknown",
        Map.of("active", true),
        List.of(new SimpleGrantedAuthority("SCOPE_orders.read"))
    );
}
~~~

Đoạn trên cho phép token **chưa được chứng minh hợp lệ** nhận quyền đọc chỉ vì lỗi mạng/AS. Một attacker có thể tận dụng thời điểm hệ thống xuống cấp để dùng bất kỳ Bearer string nào. Nó biến vấn đề availability thành **bỏ qua xác thực**.

Một lỗi tương tự là:

~~~java
// PHẢN VÍ DỤ: không dùng default active=true khi thiếu phản hồi AS.
boolean active = introspectionResponse == null
    || Boolean.TRUE.equals(introspectionResponse.get("active"));
~~~

Chính sách đúng phải phân biệt:

~~~text
active=true AND metadata policy valid  → Authentication thành công
active=false / invalid metadata         → Từ chối
không có response đáng tin              → Từ chối vì UNAVAILABLE
~~~

### 6.4. Fail closed còn áp dụng cho policy kiểm tra attributes

Không đủ để chỉ tránh tạo principal khi `active=false`. Nếu introspection trả `active=true` nhưng **thiếu audience bắt buộc** hoặc scope/issuer không thỏa hợp đồng, cũng không được bỏ bước kiểm tra còn lại để “cho client đỡ lỗi”.

Ví dụ Orders API yêu cầu `aud=orders-api`:

~~~json
{
  "active": true,
  "scope": "orders.read",
  "aud": "billing-api"
}
~~~

Token này không được nhận bởi Orders API, dù introspection endpoint trả 200 và token active. Kết quả remote là bằng chứng token đang active theo AS, không nhất thiết là bằng chứng token được cấp cho **mọi resource**.

## 7. Circuit breaker, bulkhead và rate limiting giải quyết các vấn đề khác nhau

Một retry policy tốt vẫn chưa đủ để chống quá tải. Cần tách các cơ chế:

| Cơ chế | Chống loại rủi ro nào? | Quyết định khi giới hạn đạt |
|---|---|---|
| **Timeout** | Upstream chậm, request giữ tài nguyên quá lâu | Dừng chờ, trả failure/UNAVAILABLE |
| **Bounded retry** | Lỗi tạm thời hiếm, có thể phục hồi ngay | Tối đa attempts/budget; hết thì fail |
| **Exponential backoff + jitter** | Nhiều instance retry đồng loạt | Trải đều thời điểm retry |
| **Circuit breaker** | AS đang outage/503 liên tục | Tạm không gửi call; fail nhanh |
| **Bulkhead / concurrency limit** | Quá nhiều introspection đồng thời | Từ chối sớm hoặc queue giới hạn |
| **Rate limiter** | Tốc độ gửi request quá khả năng AS | Shed hoặc giới hạn tốc độ |
| **Bounded queue** | Xếp hàng không có điểm dừng | Từ chối khi queue đầy, không chờ vô hạn |
| **Request-level deadline** | Tổng retries/backoff vượt API SLO | Không bắt đầu attempt mới nếu đã hết budget |
| **Cache được phê duyệt** | Lặp lại introspection cùng token tốn tài nguyên | Tái sử dụng **kết quả xác minh hợp lệ chưa hết hạn/freshness** |

### 7.1. Trạng thái circuit breaker

~~~mermaid
stateDiagram-v2
    [*] --> Closed
    Closed --> Open: tỷ lệ lỗi transient vượt ngưỡng
    Open --> HalfOpen: hết wait duration
    HalfOpen --> Closed: probe thành công theo policy
    HalfOpen --> Open: probe lỗi
~~~

**Closed**: cho phép request qua tới introspection, ghi nhận tỷ lệ lỗi.  
**Open**: không tiếp tục gọi AS cho mỗi request, trả lỗi không xác thực nhanh.  
**Half-open**: chỉ cho một số probe/requests có giới hạn để đánh giá AS đã phục hồi chưa.

Nếu circuit open, **không mặc định cho qua những token chưa xác minh**. Circuit breaker chỉ tối ưu cách xử lý failure và bảo vệ tài nguyên; nó không phải cơ chế cấp quyền.

### 7.2. Đừng tính `active=false` là lỗi sức khỏe của AS

Giả sử có một bot gửi 10.000 token giả, AS hoạt động tốt và trả `active=false`. Nếu circuit breaker xem mọi “introspection rejection” là lỗi server, bot có thể khiến circuit mở và gây gián đoạn cho người dùng hợp lệ.

Nên phân loại:

~~~text
HTTP 200 + active=false → kết quả application/protocol bình thường
HTTP 200 + active=true  → kết quả application/protocol bình thường
HTTP 503 / timeout     → upstream transient failure
HTTP 401 caller auth   → configuration/security incident
HTTP 429               → overload/rate-limit signal
~~~

Circuit breaker nên đo **sức khỏe của introspection transport/service**, không phải tỷ lệ token hợp lệ của người dùng.

### 7.3. Bulkhead bảo vệ thread và connection pool

Ví dụ một Servlet Resource Server được phép thực hiện tối đa 40 introspection calls đồng thời. Khi vượt ngưỡng:

~~~text
requests waiting for introspection
                |
                v
       concurrency limiter
                |
       +--------+---------+
       |                  |
    slot free          saturated
       |                  |
       v                  v
 call AS             fail fast /
                    bounded queue
~~~

Nếu chỉ dùng timeout mà không giới hạn concurrency, một đợt AS slowdown có thể làm hàng trăm hoặc hàng nghìn Servlet threads đợi. Với bulkhead, chi phí được chặn trong giới hạn dự đoán được. Nếu dùng queue, queue phải **hữu hạn** và thời gian chờ queue phải nằm trong tổng deadline.

### 7.4. Rate limiter bảo vệ Authorization Server

Rate limiter thường đặt ở tầng outbound introspection hoặc chia budget theo toàn cụm, không chỉ ở inbound endpoint. Một limit per-instance có thể vẫn tạo tổng tải lớn nếu số instance tăng gấp đôi.

Ví dụ:

~~~text
AS introspection capacity theo hợp đồng: 1.000 req/s
Resource Server cluster: 10 instances
    ↓
Per-instance budget không thể tự đặt 1.000 req/s
~~~

Trong thiết kế thực tế, cần tính tổng mức phân bổ, độ lệch giữa instances, traffic burst và overhead do retry. Nếu dùng shared distributed limiter, phải đánh giá thêm tính sẵn sàng của chính limiter; **không thiết kế cơ chế “limiter lỗi thì cho phép retry không giới hạn”**.

### 7.5. Thứ tự resilience components cũng quan trọng

Một ý tưởng tổ chức:

~~~text
Incoming request
   |
   v
Total deadline
   |
   v
Retry controller (max attempts + jitter)
   |
   +-- mỗi attempt:
        capacity/rate permit
            |
            v
        Circuit breaker check
            |
            v
        HTTP client với per-attempt timeout
            |
            v
        RFC 7662 response classifier
   |
   v
Authentication outcome
~~~

Không có một thứ tự thư viện bắt buộc cho mọi triển khai. Cần tránh hai lỗi cấu trúc:

1. Retry lặp lại **chính lỗi “bulkhead full” hoặc “circuit open”** và làm tạo thêm tải.
2. Thời gian backoff giữ một permit/connection mà lẽ ra có thể được trả lại, khiến khả năng phục vụ giảm.

Nếu dùng thư viện resilience, hãy xác định **retry bọc circuit breaker hay ngược lại**, ngoại lệ nào được record, và limiter áp trên từng attempt hay toàn operation. Không chỉ đặt annotations rồi giả định chúng tạo ra cùng hành vi trong mọi thứ tự AOP.

## 8. Chính sách thử lại được diễn đạt bằng thuật toán

Một pseudo-code an toàn cần phân biệt outcome và deadline:

~~~text
function introspectWithPolicy(token, deadline):
    attempts = 0

    while attempts < maxAttempts:
        if deadline exhausted:
            raise IntrospectionUnavailable

        if circuit is open:
            raise IntrospectionUnavailable

        if capacity permit unavailable:
            raise IntrospectionUnavailable

        attempts += 1
        try:
            response = callIntrospectionWithPerAttemptTimeout(
                token, remainingDeadline
            )

            if response is valid RFC 7662 with active=false:
                raise InvalidTokenWithoutRetry

            if response is valid RFC 7662 with active=true:
                validate required metadata
                return VerifiedPrincipal

            if response has invalid schema or trusted policy mismatch:
                raise InvalidProtocolOrTokenWithoutRetry

        catch known non-retryable error:
            propagate error (no retry)

        catch known transient upstream error:
            if attempts >= maxAttempts:
                raise IntrospectionUnavailable

            delay = boundedBackoffWithJitter(attempts)
            if delay + minimumNextAttemptBudget > remainingDeadline:
                raise IntrospectionUnavailable

            wait delay (without violating capacity policy)

    raise IntrospectionUnavailable
~~~

Thuật toán trên minh họa **các quyết định**, không phải một implementation Spring Security có thể copy/chạy trực tiếp. Những thành phần như HTTP client, deadline propagation, circuit breaker, JSON parser và mapping exception phải được triển khai theo thư viện/phiên bản thực tế.

### 8.1. Không retry lỗi bất biến hoặc lỗi bảo mật

Điều kiện `retryable` cần là một **allowlist rõ ràng**:

~~~text
retryable =
    transient upstream 502/503/504
    OR một số connect/read timeout được policy cho phép
    OR rate-limit signal với Retry-After phù hợp budget

NOT retryable =
    active=false
    OR token thiếu/sai profile
    OR introspection client credentials sai
    OR audience không phù hợp
    OR protocol response hỏng theo contract
    OR TLS certificate validation thất bại
    OR circuit breaker open / bulkhead rejected
~~~

Ngay cả các lỗi được liệt kê “retryable” cũng phải chịu **attempt budget, thời gian, concurrency và trạng thái tải**. Trong outage diện rộng, chính sách có thể tắt retry hoàn toàn.

### 8.2. Tổng lượng retry cần có budget riêng

Một cách quản lý là **retry budget**: chỉ cho phép một tỷ lệ nhỏ số request introspection phát sinh thêm attempts so với lượng request gốc trong một cửa sổ. Ví dụ giả định:

~~~text
Introspection requests mới:  1.000/s
Retry budget:                 5% additional attempts
Extra attempts allowed:       50/s
~~~

Giới hạn như vậy giúp hệ thống không tăng gấp đôi lượng call khi AS đã yếu. Con số 5% chỉ là ví dụ policy; cơ chế thực tế cần tính theo capacity toàn cụm và mức giới hạn AS đồng ý.

### 8.3. Bảo vệ token khi retry

Mọi retry lặp lại **cùng Bearer credential** trong form field `token` tới endpoint introspection. Do đó:

- Không ghi `token` vào log khi retry.
- Không đưa client secret vào exception message hoặc tracing.
- Không log HTTP request/response body của introspection.
- Không lưu token trong distributed retry queue không được bảo vệ.
- Nếu retry bị hủy do timeout/client disconnect, hủy/giải phóng các HTTP operation và buffers có thể hủy được theo API.
- Không đổi introspection URI theo dữ liệu trong token để thử “endpoint khác” không thuộc trust registry.

## 9. Spring Security Servlet: nơi đặt chính sách retry

Trong ứng dụng Spring MVC/Servlet, Spring Security thường dùng **`OpaqueTokenIntrospector`** để nhận một chuỗi Bearer token rồi trả **`OAuth2AuthenticatedPrincipal`** đã được xác minh hoặc ném exception khi không thể xác thực.

~~~text
BearerTokenAuthenticationFilter
   |
   v
OpaqueTokenAuthenticationProvider
   |
   v
OpaqueTokenIntrospector
   |
   +--> outbound HTTP / local state
   +--> classification + resilience policy
   |
   v
OAuth2AuthenticatedPrincipal / failure
   |
   v
BearerTokenAuthentication + GrantedAuthority
~~~

### 9.1. Cấu hình Resource Server với introspection endpoint

Dependency Servlet:

~~~gradle
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
~~~

`application.yml`:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://login.example.test/oauth2/introspect
          client-id: ${INTROSPECTION_CLIENT_ID}
          client-secret: ${INTROSPECTION_CLIENT_SECRET}
~~~

Ví dụ dùng biến môi trường thay vì hard-code secret. Trong môi trường thật, nên quản lý client credentials qua secret manager, dùng TLS tin cậy và có kế hoạch rotation.

Security chain:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration
class OrdersResourceServerSecurity {

    @Bean
    SecurityFilterChain api(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .anyRequest().denyAll()
            )
            .oauth2ResourceServer(oauth2 ->
                oauth2.opaqueToken(withDefaults()))
            .build();
    }
}
~~~

**Đây mới là cấu hình introspection cơ bản**. Các property ở trên không tự khai báo policy retry, circuit breaker, per-attempt timeout hay audience validation tùy chỉnh. Nếu cần thay đổi behavior, phải chọn HTTP client/introspector implementation phù hợp với phiên bản Spring Security và kết nối các cơ chế resilience một cách tường minh.

### 9.2. Không đặt retry sau khi authentication đã thất bại

Một số kiến trúc định retry bằng cách:

~~~text
Spring Security authentication failed
         |
         v
HTTP 401 to client
         |
         v
Gateway retries entire HTTP request
~~~

Đây thường **không phải vị trí đúng để retry introspection**. Gateway retry cả request có thể lặp lại controller side effects nếu request đã được thực thi, làm rối 401/503 và tăng tải. Retry introspection nên được đặt ở **điểm gọi dịch vụ xác minh token**, với bộ phân loại lỗi giao thức rõ ràng và deadline, chứ không phải retry mọi request nghiệp vụ.

### 9.3. Không gắn retry vào mọi exception của `OpaqueTokenIntrospector`

Phản ví dụ:

~~~java
// PHẢN VÍ DỤ: bắt mọi exception và retry là sai.
for (int i = 0; i < 5; i++) {
    try {
        return delegate.introspect(token);
    } catch (Exception anyFailure) {
        // Nguy hiểm: active=false cũng có thể bị gói thành exception.
    }
}
~~~

Mã trên có thể lặp 5 lần với token invalid, client secret sai, TLS certificate error hoặc circuit-open. Không nên sử dụng nó như một resilience policy.

### 9.4. Đặt một transport adapter phân loại lỗi trước khi bọc retry

Sơ đồ một cấu trúc phù hợp:

~~~text
OpaqueTokenIntrospector (bean được SecurityFilterChain sử dụng)
   |
   v
VerifiedIntrospectionAdapter
   |
   v
BoundedRetryPolicy
   |
   v
HTTP Transport (phân loại status/timeout theo allowlist)
   |
   v
Trusted introspection endpoint
~~~

Adapter cần ánh xạ kết quả thành những nhóm **không chồng lấn**:

~~~text
TokenRejected:
  active=false; sai audience/claim bắt buộc
  => không retry

IntrospectionConfigurationError:
  caller 401/403; TLS certificate invalid; endpoint sai
  => không retry tự động

IntrospectionTransientError:
  timeout/502/503/504 được policy cho phép
  => có thể retry có giới hạn

IntrospectionRateLimited:
  429; optional Retry-After
  => giảm tải; thường không retry trong request
~~~

Không thể phân loại chính xác chỉ từ exception message string như `contains("timeout")`. Tầng HTTP client phải giữ thông tin status và exception cause theo cách được version của thư viện hỗ trợ; nếu không phân loại được an toàn, mặc định **không retry**.

## 10. Một decorator minh họa retry có giới hạn

Ví dụ sau minh họa cấu trúc **Servlet/blocking** khi tầng transport đã chuẩn hóa **chỉ những lỗi transient cho phép retry** thành exception riêng. Nó không tự phân loại HTTP status của thư viện Nimbus hoặc tự thực hiện kết nối HTTP; đó là phần của `delegate` được ứng dụng cung cấp.

~~~java
import java.time.Duration;
import java.util.Objects;
import java.util.concurrent.ThreadLocalRandom;

import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.introspection.OAuth2IntrospectionException;
import org.springframework.security.oauth2.server.resource.introspection.OpaqueTokenIntrospector;

// Do transport adapter phát ra CHỈ với lỗi transient đã phân loại.
final class TransientIntrospectionFailure extends OAuth2IntrospectionException {
    TransientIntrospectionFailure(String message, Throwable cause) {
        super(message, cause);
    }
}

final class BoundedRetryIntrospector implements OpaqueTokenIntrospector {

    private final OpaqueTokenIntrospector delegate;
    private final int maxAttempts;
    private final Duration totalBudget;

    BoundedRetryIntrospector(
            OpaqueTokenIntrospector delegate,
            int maxAttempts,
            Duration totalBudget) {
        if (maxAttempts < 1 || totalBudget.isZero()
                || totalBudget.isNegative()) {
            throw new IllegalArgumentException("Invalid retry policy");
        }
        this.delegate = Objects.requireNonNull(delegate);
        this.maxAttempts = maxAttempts;
        this.totalBudget = totalBudget;
    }

    @Override
    public OAuth2AuthenticatedPrincipal introspect(String token) {
        long started = System.nanoTime();
        long budgetNanos = totalBudget.toNanos();

        for (int attempt = 1; attempt <= maxAttempts; attempt++) {
            long elapsed = System.nanoTime() - started;
            if (elapsed >= budgetNanos) {
                throw new OAuth2IntrospectionException(
                    "Introspection unavailable within deadline");
            }

            try {
                // Delegate phải có per-attempt HTTP timeout riêng,
                // được cắt theo thời gian còn lại nếu có thể.
                return delegate.introspect(token);
            } catch (TransientIntrospectionFailure transientFailure) {
                if (attempt == maxAttempts) {
                    throw transientFailure;
                }

                long remainingNanos =
                    budgetNanos - (System.nanoTime() - started);
                long jitterNanos =
                    ThreadLocalRandom.current().nextLong(
                        50_000_000L, 150_000_001L);

                // Giữ tối thiểu 250 ms cho attempt kế tiếp.
                if (remainingNanos <= jitterNanos + 250_000_000L) {
                    throw transientFailure;
                }

                try {
                    long ms = jitterNanos / 1_000_000L;
                    int ns = (int) (jitterNanos % 1_000_000L);
                    Thread.sleep(ms, ns);
                } catch (InterruptedException interrupted) {
                    Thread.currentThread().interrupt();
                    throw new OAuth2IntrospectionException(
                        "Introspection interrupted", interrupted);
                }
            }
        }

        throw new OAuth2IntrospectionException(
            "Introspection attempt budget exhausted");
    }
}
~~~

### 10.1. Chính sách của ví dụ trên

Với:

~~~java
new BoundedRetryIntrospector(
    classifiedDelegate,
    2,
    Duration.ofMillis(900)
);
~~~

ý nghĩa là **tối đa hai attempts**, tổng budget minh họa 900 ms. Một lỗi `active=false` hoặc cấu hình sai được `delegate` phát ra bằng loại exception **không phải** `TransientIntrospectionFailure` nên **không bị retry**.

### 10.2. Những gì ví dụ cố ý không tuyên bố

- Không phải mã production-ready: chỉ minh họa **phân loại exception và bounded retries** trong wrapper.
- `Thread.sleep` chặn Servlet thread trong thời gian backoff; ở tải cao nên ưu tiên resilience library/kiến trúc có concurrency budget rõ ràng, tránh chờ hàng loạt thread.
- `System.nanoTime` dùng để đo thời gian trôi, không phải thời gian thực dùng tính JWT expiry.
- **Tổng deadline là điều kiện logic**; nếu HTTP client của delegate không có **per-attempt timeout** nhỏ hơn thời gian còn lại, một lần gọi có thể chặn quá budget và wrapper không thể tự cắt nó.
- Retry budget, bulkhead, circuit breaker, rate limiter, timeout ở connection pool và metrics phải được cấu hình riêng.
- Không nên dựa vào `TransientIntrospectionFailure` do bọc mọi `OAuth2IntrospectionException` một cách ngây thơ; việc phân loại phải diễn ra ở HTTP boundary.
- Nếu caller hủy request, cần đảm bảo transport client hủy hoặc giải phóng tài nguyên theo khả năng library; một blocking call có thể vẫn chạy nếu không có cơ chế cancellation.
- Token và credential không được ghi vào exception text hoặc log của decorator.

### 10.3. Vì sao cần phân loại ở delegate?

`OpaqueTokenIntrospector` chỉ có hợp đồng “trả principal hoặc thất bại”, không bắt buộc mọi implementation phải tạo cùng class exception cho HTTP 429/5xx/timeout. Nếu wrapper bắt:

~~~java
catch (OAuth2IntrospectionException ex) {
    // retry mọi thứ
}
~~~

thì nó có thể lặp lại lỗi client secret hoặc `active=false` tùy cách implementation tạo exception. **Tách transport errors thành domain failure types ở nơi có thông tin HTTP đầy đủ** mới giữ được chính sách retry chính xác.

## 11. Cấu hình resilience cần gắn vào đúng introspector

Với Spring Security Servlet, có thể cung cấp một bean `OpaqueTokenIntrospector` hoặc cấu hình một introspector trực tiếp qua DSL. Điều quan trọng là chính **introspector mà security chain sử dụng** phải chứa policy đã thiết kế.

Mã ghép cấu trúc (giả sử bean `classifiedDelegate` được ứng dụng triển khai):

~~~java
import java.time.Duration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.server.resource.introspection.OpaqueTokenIntrospector;

@Configuration
class IntrospectionResilienceConfiguration {

    @Bean
    OpaqueTokenIntrospector opaqueTokenIntrospector(
            ClassifiedIntrospectionDelegate classifiedDelegate) {
        return new BoundedRetryIntrospector(
            classifiedDelegate,
            2,
            Duration.ofMillis(900)
        );
    }
}
~~~

`ClassifiedIntrospectionDelegate` là **interface/class ứng dụng tự định nghĩa** với semantics phân loại lỗi ở phần trước; cần cung cấp implementation để đoạn code được sử dụng trong dự án thật. Đây không phải class Spring Security có sẵn. Không khai báo đồng thời nhiều bean introspector cạnh tranh nếu chain không chỉ định rõ bean nào được dùng.

Nếu security chain gắn introspector khác qua `opaqueToken(...).introspector(...)`, bean ở trên có thể **không được sử dụng**. Khi có nhiều chain hoặc nhiều issuer, mỗi chain phải nhận policy phù hợp.

### 11.1. Thư viện resilience có thể thay wrapper tự viết

Một thư viện như Resilience4j có thể giúp triển khai retry, circuit breaker, bulkhead và rate limiter. Tuy nhiên, annotation/decorator **không tự biết `active=false` khác 503**, cũng không tự đặt tổng request deadline hoặc bảo đảm retry cùng issuer đáng tin.

Ví dụ chính sách dạng cấu hình **minh họa, không phải property auto-config mặc định của Spring Security**:

~~~yaml
app:
  introspection:
    timeout:
      total: 900ms
      connect: 200ms
      response: 350ms
    retry:
      max-attempts: 2
      base-delay: 50ms
      max-delay: 150ms
      jitter: true
      retryable-statuses: [502, 503, 504]
    capacity:
      max-in-flight-per-instance: 40
      max-queue: 0
    circuit-breaker:
      enabled: true
      half-open-probes: 3
~~~

Những property `app.introspection.*` chỉ là **schema do ứng dụng tự đặt**, không tự có tác dụng chỉ vì xuất hiện trong `application.yml`. Cần code cấu hình HTTP client/Resilience4j tương ứng, cùng cơ chế đo/quan sát giới hạn.

### 11.2. Quan trọng: thứ tự tích hợp và bao phủ policy

Một cấu hình có thể “trông đẹp” nhưng không có tác dụng nếu:

- Retry được cấu hình trên một `RestClient` không phải client mà introspector đang dùng.
- Bean `OpaqueTokenIntrospector` mặc định do Boot tạo thay vì custom bean.
- Bean custom tồn tại nhưng security chain đã chỉ định một introspector khác.
- Circuit breaker chỉ áp cho controller service downstream, không áp cho HTTP introspection.
- Timeout được đặt trên request nghiệp vụ nhưng không có timeout trên introspection transport.
- Rate limiter per instance lớn hơn tổng quota AS khi scale out.

Vì vậy cần xác định rõ **pipeline thực sự được một request Bearer đi qua**, chứ không dừng ở việc các bean/cấu hình tồn tại trong application context.

## 12. WebFlux: retry bất đồng bộ, không chặn event loop

Trong **Spring WebFlux**, Resource Server dùng `ReactiveOpaqueTokenIntrospector`. Mô hình lỗi và quy tắc fail-closed vẫn như Servlet, nhưng triển khai retry/backoff nên dựa trên publisher bất đồng bộ thay vì `Thread.sleep`.

### 12.1. Cấu hình Reactive Resource Server cơ bản

Dependencies:

~~~gradle
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
~~~

HTTP security:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration
class ReactiveOrdersSecurity {

    @Bean
    SecurityWebFilterChain api(ServerHttpSecurity http) {
        return http
            .authorizeExchange(auth -> auth
                .pathMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .anyExchange().denyAll()
            )
            .oauth2ResourceServer(oauth2 ->
                oauth2.opaqueToken(withDefaults()))
            .build();
    }
}
~~~

Spring Boot có thể cấu hình introspection endpoint qua `spring.security.oauth2.resourceserver.opaquetoken.*` như ở phần Servlet. Khi muốn custom retry, cần đảm bảo chính `ReactiveOpaqueTokenIntrospector` được chain sử dụng chứa policy đã thiết kế.

### 12.2. Reactor retry chỉ cho những lỗi đã phân loại

Ví dụ wrapper reactive:

~~~java
import java.time.Duration;
import java.util.Objects;

import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.introspection.ReactiveOpaqueTokenIntrospector;

import reactor.core.publisher.Mono;
import reactor.util.retry.Retry;

final class BoundedReactiveIntrospector
        implements ReactiveOpaqueTokenIntrospector {

    private final ReactiveOpaqueTokenIntrospector delegate;

    BoundedReactiveIntrospector(ReactiveOpaqueTokenIntrospector delegate) {
        this.delegate = Objects.requireNonNull(delegate);
    }

    @Override
    public Mono<OAuth2AuthenticatedPrincipal> introspect(String token) {
        return Mono.defer(() -> delegate.introspect(token))
            .retryWhen(
                Retry.backoff(1, Duration.ofMillis(50))
                    .maxBackoff(Duration.ofMillis(150))
                    .jitter(0.5)
                    .filter(error ->
                        error instanceof TransientIntrospectionFailure)
            )
            .timeout(Duration.ofMillis(900));
    }
}
~~~

Ý nghĩa:

- `Retry.backoff(1, ...)` cho phép **tối đa một retry** sau request đầu tiên, tức tối đa hai attempts trong trường hợp lỗi retryable liên tục.
- `filter(...)` đảm bảo chỉ exception transient đã được **transport adapter phân loại tin cậy** mới được retry. `active=false` và lỗi cấu hình không thuộc nhóm này.
- `timeout(900ms)` đặt giới hạn thời gian cho **publisher toàn bộ chuỗi retries**, bao gồm backoff. Ngoài ra HTTP client vẫn cần connection/read timeouts và giới hạn pool phù hợp.
- `Mono.defer(...)` làm delegate được gọi ở mỗi subscription/retry theo đúng semantics publisher.
- Không có `onErrorResume(error -> Mono.just(fakePrincipal))`: nếu lỗi hết attempts hoặc quá thời gian thì **Mono lỗi**, không tạo principal.

**Đây là mẫu minh họa**, không phải hệ thống resilience production hoàn chỉnh. `TransientIntrospectionFailure` là một exception do adapter ứng dụng chuẩn hóa, như trong ví dụ Servlet. Cần bổ sung **bulkhead, circuit breaker, rate-limit, cancellation policy, telemetry, exception mapping** theo kiến trúc. Reactor `retryWhen` có thể bọc exception khi hết retries; error handler cần phân loại an toàn mà không làm thay đổi quyết định xác thực.

### 12.3. Không thực hiện blocking call trong reactive callback

Phản ví dụ:

~~~java
// PHẢN VÍ DỤ: có thể chặn Reactor event loop.
return Mono.fromCallable(() -> blockingIntrospector.introspect(token))
    .retryWhen(...);
~~~

Một `Mono.fromCallable` không tự biến blocking HTTP client thành non-blocking. Nếu không có scheduling thích hợp, nó có thể chạy trên thread nhạy cảm với blocking. Nên dùng reactive HTTP client, hoặc nếu buộc phải kết hợp thư viện blocking thì giới hạn và chuyển execution sang bounded scheduler được thiết kế đúng, cùng số lượng concurrent tasks phù hợp.

### 12.4. CORS và lỗi authentication trên WebFlux

Đối với browser client, preflight có thể không mang Bearer token. Cần xử lý CORS đúng thứ tự để không khiến mọi preflight bị introspect hoặc trả lỗi auth không cần thiết. Tuy nhiên, request thật sau preflight vẫn phải đi qua introspection và authorization.

Một hỏng hóc upstream không được giải quyết bằng:

~~~java
// PHẢN VÍ DỤ:
.onErrorResume(ex -> Mono.just(anAuthenticatedPrincipal))
~~~

Nếu cần phản hồi 503 thay vì 401 cho transport errors, hãy làm trong **exception mapping ở security boundary** và giữ kết quả authentication là thất bại, không tạo principal.

## 13. Cache introspection: giảm tải nhưng không được “hợp thức hóa” stale data

Cache có thể giảm lượng HTTP calls khi cùng một token được trình nhiều lần. Nhưng nó chuyển một phần quyết định tin cậy từ **Authorization Server tại thời điểm request** sang **bằng chứng được lưu ở Resource Server**.

### 13.1. Cache `active=true` phải có giới hạn

Một cache entry đã được xác minh cần lưu thông tin có cấu trúc:

~~~text
key:         protected fingerprint(token) + trust context
value:       verified active=true result + accepted attributes
verifiedAt:  timestamp của lần xác minh thành công
expiresAt:   hạn sử dụng cache theo policy
tokenExp:    exp của token nếu có
context:     issuer, resource/audience, introspection client/policy
~~~

Quy tắc tổng quát:

~~~text
cacheEntryExpiresAt <= tokenExpiresAt (nếu được tin cậy)
cacheEntryExpiresAt <= verifiedAt + maxAcceptedCacheTTL
cacheEntryExpiresAt <= any policy-specific freshness deadline
~~~

Không cache kết quả `active=true` vô thời hạn nếu token thiếu `exp`; cần giới hạn policy khác hoặc không cache. Cache key không nên là raw Bearer token trong log, metrics, tracing hoặc dashboard; có thể dùng một fingerprint bảo vệ theo threat model và quản lý keys phù hợp. Nếu token store/cache bị lộ, nó có thể chứa identity/attributes nhạy cảm, cần RBAC, mã hóa và retention.

### 13.2. Khi AS outage: entry nào còn dùng được?

Tình huống:

~~~text
10:00:00 introspection → active=true, exp=10:30
10:00:00 local cache entry TTL 30 giây
10:00:15 AS bị outage
10:00:20 request cùng token đến
10:00:40 request cùng token đến
~~~

Theo policy **chỉ dùng cache còn hiệu lực**:

| Thời điểm | Cache state | Quyết định |
|---|---|---|
| 10:00:20 | Entry còn TTL và token chưa hết hạn | Có thể dùng entry đã xác minh nếu policy cho phép |
| 10:00:40 | TTL đã hết, AS vẫn unavailable | **Không** sử dụng entry cũ để tự xác thực; fail closed |

Đây là **một lựa chọn thiết kế**. Có thể một hệ thống phê duyệt một cửa sổ “stale-if-error” rất ngắn có kiểm soát để duy trì availability, nhưng khi đó phải ghi nhận rõ **độ trễ revocation mà tổ chức chấp nhận**, không gọi đó là xác minh trạng thái hiện tại. Đối với endpoint nhạy cảm yêu cầu immediate revocation, có thể cần **không cache hoặc không dùng stale**.

Không triển khai fallback mơ hồ kiểu:

~~~java
// PHẢN VÍ DỤ:
catch (Exception upstreamDown) {
    return lastSuccessByToken.get(token); // Có thể đã hết TTL/revoked!
}
~~~

### 13.3. Nếu chính sách chấp nhận stale-if-error

Một chính sách có thể được phê duyệt trước dưới các điều kiện:

1. Entry ban đầu phải là kết quả introspection **đã được xác minh thành công** cho đúng token/issuer/audience/client context.
2. Token chưa qua `exp` và không có local revocation/denylist signal mới.
3. Stale window được giới hạn cứng (ví dụ vài giây theo risk assessment), không gia hạn qua mỗi request.
4. Chỉ được dùng khi lỗi hạ tầng thực sự **đã phân loại**, không dùng cho `active=false` hoặc sai claims.
5. Có metric và audit rõ lúc dùng stale evidence.
6. Các endpoint nhạy cảm có thể cấm dùng stale hoàn toàn.
7. Không triển khai khi chưa có đồng thuận từ chủ sở hữu bảo mật/AS về độ trễ thu hồi.

**Bảo vệ bằng cache đã xác minh còn trong window** là một lựa chọn nhất quán theo policy, nhưng **không phải introspection mới**. Nếu policy yêu cầu xác minh từ xa mỗi request, stale-if-error có thể không phù hợp.

### 13.4. Cache kết quả `active=false`

Negative caching có thể giảm lặp introspection với những token invalid thường gặp. Tuy nhiên, cần cân nhắc:

- Một token mới vừa phát hành có thể chưa được thấy bởi replica introspection, dẫn đến false negative tạm thời.
- Một attacker có thể gửi vô số random token để tạo rất nhiều negative entries, gây memory pressure.
- Cache key phải được bảo vệ và giới hạn cardinality.
- TTL negative cache phải ngắn, có giới hạn dung lượng và không được thay thế policy authentication.
- Không cache lỗi 429/503/timeout như một giá trị `active=false` trừ khi có chiến lược rõ ràng; lỗi hạ tầng không chứng minh token invalid.

### 13.5. Stampede khi một token phổ biến hết hạn cache

Nếu cùng một service token được hàng nghìn request sử dụng, mọi cache entry hết TTL có thể khiến hàng trăm request đồng loạt gọi AS:

~~~text
same token cache expires
  ├── request A → introspection
  ├── request B → introspection
  ├── request C → introspection
  └── ...
~~~

Có thể dùng **single-flight/request coalescing** để những request đồng thời với cùng cache key dùng chung một **future/publisher của lần introspection đang chạy**, thay vì gọi AS nhiều lần. Cần giới hạn số key đang chờ, thời gian chờ, kết quả lỗi và cancellation để tránh memory leak/DoS. Nếu request đầu nhận `active=false`, mọi waiter vẫn phải bị từ chối; không cho một waiter dùng trạng thái cũ thay thế.

### 13.6. Không dùng cache để vượt token binding

Nếu access token có sender constraints (ví dụ mTLS/DPoP), việc introspection `active=true` chưa đủ cho mọi request: Resource Server còn cần xác minh **proof/key binding của chính request hiện tại**. Không cache một kết quả authentication rồi bỏ qua sender proof. Tương tự, audience và tenant context có thể cần được gắn vào cache key/policy.

## 14. Khi bảo vệ chính Authorization Server khỏi quá tải

Một Resource Server có thể nhận đồng thời:

- Token hợp lệ dùng thường xuyên.
- Token đã hết hạn.
- Token giả do bot tạo ngẫu nhiên.
- Traffic từ client mới sau rollout.
- Lượng request tăng đột biến do sự cố retry ở gateway.

Mọi token chưa được biết đều có thể tạo một introspection call nếu không có cơ chế giảm tải.

### 14.1. Inbound rate limit và outbound rate limit khác nhau

**Inbound rate limit** bảo vệ Resource Server trước request burst; có thể áp tại gateway/IP/client identity phù hợp, nhưng phải tránh phụ thuộc vào claims chưa xác minh để đánh giá identity.

**Outbound rate limit** bảo vệ Authorization Server trước tổng lượng introspection calls mà Resource Server phát ra. Nó nên xét **toàn cụm**, không chỉ từng pod.

Hai limiter thường bổ sung nhau. Nếu inbound attacker dùng nhiều IP hoặc token giả, inbound policy theo IP có thể chưa đủ; outbound limit vẫn giúp ngăn AS bị request flood.

### 14.2. Từ chối sớm khi saturation

Nếu pool có 40 slots và đã đầy:

~~~text
new request
    |
    v
capacity permits: 0
    |
    v
short-circuit (không tạo Authentication)
    |
    v
service-unavailable response theo policy
~~~

Không cần giữ request chờ cho tới khi queue dài hàng nghìn phần tử. Một phản hồi lỗi đúng lúc có thể tốt hơn một hàng đợi không giới hạn khiến cả service mất khả năng phục vụ.

### 14.3. Xử lý `Retry-After` của AS qua Resource Server

Không nên sao chép mù quáng HTTP 429 của introspection thành HTTP 429 cho client, vì **hạn mức có thể thuộc introspection client credentials của chính Resource Server**, không phải quota của user gọi API. Có thể trả 503 hoặc response chính sách khác, nhưng cần **tự giảm tốc outbound** và giám sát nguồn 429.

Nếu cần hướng dẫn client thử lại, đừng hứa một thời điểm mà service không biết AS sẽ phục hồi. `Retry-After` ở public response phải phù hợp hợp đồng, không chứa metadata nhạy cảm và không tạo làn sóng retries đồng loạt.

### 14.4. Một issuer phục vụ nhiều Resource Server

Nếu hàng chục microservices dùng chung một introspection client hoặc chung quota, mỗi service độc lập retry 2 lần vẫn có thể phá quota tổng. Cần:

~~~text
Shared AS capacity / contract
       |
       +--> Orders API budget
       +--> Billing API budget
       +--> Inventory API budget
       +--> Admin API budget
~~~

Các budget có thể tách theo mức quan trọng và độ nhạy cảm endpoint. Một service bị tấn công bằng token giả không nên làm dịch vụ khác hết quota xác thực. Nếu không thể tách credential hoặc quota, phải có cơ chế bảo vệ tổng tải/circuit phù hợp.

## 15. Quan sát hệ thống mà không làm lộ token

Một chính sách retry chỉ có thể vận hành được nếu đội phát triển phân biệt các nguồn lỗi. Nhưng log raw token hoặc client secret để “debug” lại làm tăng rủi ro bảo mật.

### 15.1. Những metric hữu ích

| Metric | Nhãn nên dùng | Tránh |
|---|---|---|
| `introspection_attempts_total` | issuer alias, outcome category, environment | Raw token, email, full URI có secret |
| `introspection_retries_total` | retry reason, policy version | Token hash tùy ý làm label |
| `introspection_duration_seconds` | service, outcome, bounded buckets | Subject/jti per request |
| `introspection_in_flight` | instance/cluster | Credential hoặc PII |
| `introspection_queue_depth` | endpoint alias | Full request body |
| `introspection_circuit_state` | CLOSED/OPEN/HALF_OPEN | Arbitrary exception messages |
| `introspection_rejected_capacity_total` | bulkhead/rate-limit cause | Token string |
| `introspection_cache_hits_total` | hit/miss/stale-within-policy | Token as a label |
| `authentication_outcomes_total` | authenticated/invalid/unavailable | Claims/credentials |

Các metric nên có **nhãn bounded cardinality**. Sử dụng trace/request ID do hệ thống tạo nếu cần tương quan từng request. Không dùng `sub`, `jti`, token value hoặc client secret làm metric dimension.

### 15.2. Phân loại structured logging

Ví dụ an toàn:

~~~text
INFO event=introspection outcome=active duration_ms=81 attempts=1 req_id=...
WARN event=introspection outcome=upstream_503 attempts=2 req_id=...
WARN event=introspection outcome=rate_limited attempts=1 req_id=...
WARN event=introspection outcome=invalid_token attempts=1 req_id=...
ERROR event=introspection outcome=client_auth_failed req_id=...
~~~

Không dùng:

~~~text
WARN introspection failed token=eyJ... clientSecret=...
ERROR upstream request body=token=...&client_secret=...
DEBUG principal={all-claims-and-credentials}
~~~

Vì introspection POST chứa **raw access token** trong form body và có thể chứa Basic client auth trong header, cần tắt/redact HTTP wire/body/header logging ở `RestClient`, `WebClient`, gateway/proxy, distributed tracing và error monitoring.

### 15.3. Alerting theo loại sự cố

| Tín hiệu | Điều tra ưu tiên |
|---|---|
| `active=false` tăng bất thường | Client gửi token hết hạn, abuse hoặc issue trong token issuance |
| 401 từ AS introspection | Secret rotation/caller authentication |
| 429 từ AS introspection | Quota/capacity, duplicate retries, deployment tăng tải |
| 503/timeout liên tục | AS outage/network, circuit breaker, thread pools |
| Retry ratio vượt budget | Backoff/retry config hoặc AS đang degraded |
| Circuit breaker OPEN lâu | Upstream chưa phục hồi, probe không đạt |
| Cache stale-use tăng | AS không ổn định hoặc policy đang dùng risk allowance |
| 401/403 ở Resource Server sau khi đổi AS | Mapping scope/audience/token metadata có thay đổi |

**Đừng lấy tăng số 401 của client làm bằng chứng duy nhất AS bị outage**: cùng status có thể xuất hiện do token invalid, issuer policy, thiếu authority hoặc exception handling. Cần theo dõi chính tầng introspection.

## 16. Kiểm thử lỗi và tải: phải chứng minh không có đường “bỏ qua xác minh”

Kiểm thử retry không chỉ xác nhận request cuối cùng thành công sau một lần 503. Điều quan trọng hơn là xác nhận **mọi đường thất bại đều không sinh Authentication hợp lệ** và không làm số request outbound vượt budget.

### 16.1. Ma trận tích hợp với introspection endpoint giả lập

| Kịch bản | Response/transport của AS giả lập | Attempts mong đợi | Kết quả authentication |
|---|---|---|---|
| Token hợp lệ | 200 `active=true` và metadata đầy đủ | 1 | Thành công |
| Token không active | 200 `active=false` | **1**, không retry | Không xác thực |
| Token sai audience | 200 `active=true`, `aud=billing-api` | 1 | Không xác thực cho Orders API |
| Token thiếu metadata bắt buộc | 200 `active=true`, không có `aud` theo contract | 1 | Không xác thực |
| Credential của RS sai | HTTP 401 từ introspection | **1** | Không xác thực; alert |
| Caller không có quyền introspect | HTTP 403 | 1 | Không xác thực; alert |
| URI introspection sai | HTTP 404 | 1 | Không xác thực; lỗi cấu hình |
| Lỗi tạm thời rồi phục hồi | 503 rồi 200 `active=true` | Tối đa 2 khi policy cho phép | Thành công nếu tổng deadline còn |
| Lỗi tạm thời kéo dài | 503, 503, 503... | Không vượt `maxAttempts` | Không xác thực |
| Quá tải từ AS | 429 với `Retry-After` lớn | Thường 1, không chờ quá budget | Không xác thực |
| Connect timeout | Timeout đã được phân loại retryable | Theo attempt/budget | Không xác thực nếu không có kết quả |
| Read timeout sau khi request gửi | Không biết AS đã xử lý | Theo idempotency policy | Không xác thực nếu không có kết quả |
| TLS certificate invalid | TLS validation failure | 1 | Không xác thực |
| JSON hỏng / thiếu `active` | 200 nhưng response sai contract | 1 | Không xác thực |
| Circuit breaker OPEN | Không gửi request tới AS | **0 outbound calls** | Không xác thực |
| Bulkhead saturated | Không có permit | 0 hoặc theo queue policy | Không xác thực |
| Cached entry còn hiệu lực | Đã xác minh trước và trong TTL | 0 outbound calls cho hit | Có thể xác thực theo cache policy |
| Cached entry hết TTL, AS unavailable | Không còn bằng chứng được phép | Không vượt attempts/budget | **Không xác thực** |

Trong test, cần quan sát **số lần gọi HTTP thật**, elapsed time và kết quả `SecurityContext`. Nếu chỉ assert status cuối mà không đo số attempts, implementation có thể âm thầm gửi 10 requests tới AS rồi vẫn trả 401, làm trầm trọng thêm outage.

### 16.2. Unit test decorator không retry lỗi token invalid

Ví dụ unit test cho `BoundedRetryIntrospector` ở phần 10. Đây là ví dụ đơn vị độc lập với HTTP; exception `BadOpaqueTokenException` biểu diễn một token không active và không được xem là lỗi transient.

~~~java
import java.time.Duration;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;
import org.springframework.security.oauth2.server.resource.introspection.BadOpaqueTokenException;
import org.springframework.security.oauth2.server.resource.introspection.OpaqueTokenIntrospector;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class BoundedRetryIntrospectorTest {

    @Test
    void inactiveTokenIsNeverRetried() {
        AtomicInteger attempts = new AtomicInteger();

        OpaqueTokenIntrospector delegate = token -> {
            attempts.incrementAndGet();
            throw new BadOpaqueTokenException("Token not active");
        };

        OpaqueTokenIntrospector policy = new BoundedRetryIntrospector(
            delegate, 2, Duration.ofMillis(900));

        assertThatThrownBy(() -> policy.introspect("fake-token"))
            .isInstanceOf(BadOpaqueTokenException.class);

        assertThat(attempts.get()).isEqualTo(1);
    }
}
~~~

Vì wrapper chỉ catch `TransientIntrospectionFailure`, exception token invalid sẽ được truyền ra ngay. Test này kiểm tra **số attempts**, không chỉ kiểm tra có exception.

### 16.3. Unit test lỗi transient chỉ được retry một lần

~~~java
import java.time.Duration;
import java.util.List;
import java.util.Map;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;
import org.springframework.security.oauth2.core.DefaultOAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.introspection.OpaqueTokenIntrospector;

import static org.assertj.core.api.Assertions.assertThat;

class TransientRetryExampleTest {

    @Test
    void oneTransientFailureCanBeRetriedOnce() {
        AtomicInteger attempts = new AtomicInteger();

        OpaqueTokenIntrospector delegate = token -> {
            if (attempts.incrementAndGet() == 1) {
                throw new TransientIntrospectionFailure(
                    "Synthetic upstream 503",
                    new IllegalStateException("test-only")
                );
            }
            return new DefaultOAuth2AuthenticatedPrincipal(
                "test-user",
                Map.of("sub", "test-user"),
                List.of()
            );
        };

        OpaqueTokenIntrospector policy = new BoundedRetryIntrospector(
            delegate, 2, Duration.ofMillis(900));

        assertThat(policy.introspect("fake-token"))
            .isNotNull();
        assertThat(attempts.get()).isEqualTo(2);
    }
}
~~~

Mục đích test là kiểm tra **retry tối đa một lần**. `DefaultOAuth2AuthenticatedPrincipal` trong test được tạo bởi stub khi lần thứ hai thành công; ở hệ thống thật, **chỉ một introspection response tin cậy đạt policy** mới được phép tạo principal.

### 16.4. Unit test lỗi transient kéo dài hết attempts

~~~java
@Test
void persistentTransientFailureStopsAtAttemptLimit() {
    AtomicInteger attempts = new AtomicInteger();
    OpaqueTokenIntrospector delegate = token -> {
        attempts.incrementAndGet();
        throw new TransientIntrospectionFailure(
            "Synthetic upstream 503",
            new IllegalStateException("test-only")
        );
    };

    OpaqueTokenIntrospector policy = new BoundedRetryIntrospector(
        delegate, 2, Duration.ofMillis(900));

    assertThatThrownBy(() -> policy.introspect("fake-token"))
        .isInstanceOf(TransientIntrospectionFailure.class);
    assertThat(attempts.get()).isEqualTo(2);
}
~~~

Đây là ví dụ phương thức test đặt trong class có các imports/phụ thuộc `JUnit`, `AssertJ`, `AtomicInteger`, `Duration`, `OpaqueTokenIntrospector` và các class demo đã được định nghĩa. Các snippet ở đây **không phải toàn bộ test suite** của dự án.

### 16.5. Test timeout phải xét cả tổng budget

Một test quan trọng:

~~~text
Configured maxAttempts: 3
Total operation budget: 900 ms
Attempt #1 duration: 850 ms
Retry delay planned: 100 ms
Minimum next-attempt budget: 200 ms

Expected:
    Không bắt đầu attempt #2
    Không tạo Authentication
    Kết thúc theo chính sách UNAVAILABLE
~~~

Khi test blocking HTTP client, bắt buộc cấu hình **read/response timeout** vì một wrapper chỉ đo `System.nanoTime()` trước/sau call không tự cắt được một request mạng đang bị treo.

### 16.6. Test không có “fallback principal” ở mọi đường lỗi

Đặc biệt nên mô phỏng:

- AS bị ngắt ngay lúc startup.
- AS trả 503 liên tục trong 30 giây.
- Circuit breaker chuyển OPEN rồi HALF_OPEN.
- Một token có thể được introspect lúc AS ổn định nhưng cache entry đã hết TTL khi AS outage.
- Một token vừa bị revoke trong lúc cache `active=true` còn hiệu lực.
- Một request tới endpoint nhạy cảm không có token, token invalid hoặc thiếu scope.
- Gateway/Resource Server bị quá tải concurrency, không còn permits.
- HTTP client bị lỗi TLS/secret rotation.
- Client disconnect khi introspection đang chờ, để quan sát cancellation/resource cleanup.

Mọi tình huống **không có bằng chứng xác minh hợp lệ** phải kết thúc mà **không có authenticated principal hoặc quyền truy cập nghiệp vụ**.

## 17. Kiểm thử tải và sự cố trên nhiều instances

Một vài unit tests không chứng minh hệ thống an toàn khi 100 pods cùng retry. Cần thử tải có kiểm soát trong môi trường staging với test credentials và introspection service giả lập/được phép.

### 17.1. Những đại lượng cần đo

| Đại lượng | Vì sao đo? |
|---|---|
| Incoming RPS | Xác định lượng request cần xác thực |
| Introspection outbound RPS | Phát hiện retry amplification |
| Retry attempts / original requests | Kiểm soát retry budget |
| Concurrency / waiting queue | Phát hiện exhaustion |
| Connection pool utilization | Phát hiện bottleneck HTTP client |
| AS latency p50/p95/p99 | Chọn per-attempt timeout |
| Resource Server end-to-end latency | Đảm bảo tổng request budget |
| Circuit breaker transitions | Đánh giá tốc độ phát hiện/khôi phục outage |
| Cache hit/expiry/stale usage | Hiểu tỷ lệ call giảm và revocation window |
| Active=false / unavailable / invalid_metadata | Tránh nhầm token invalid với AS outage |
| 401/403/503 từ API | Quan sát tác động lên client |

### 17.2. Một bài test tải minh họa

~~~text
Normal:
  Incoming request rate: 500/s
  Introspection p95:      80 ms
  AS response:           mostly active=true/false

Degraded:
  AS 503:                60% of calls
  AS latency p95:        400 ms
  Max attempts:          2
  Total budget:          900 ms
  Max in-flight:         40 per instance

Expected:
  No requests bypass token verification
  Retry attempts bounded
  No unbounded queue growth
  Circuit breaker opens according to policy
  Resources released after timeout/cancellation
  HTTP responses distinguish token invalid vs unavailable
~~~

Con số là ví dụ kịch bản thử tải, không phải capacity được bảo đảm. Nếu yêu cầu doanh nghiệp cần chịu 500/s ở mức 503 60%, phải đánh giá capacity thực tế và liệu chính sách cho phép client nhận lỗi tạm thời ở tỷ lệ nào.

### 17.3. Thử nghiệm phối hợp với gateway

Nếu cả Resource Server **và** gateway đều có retry:

~~~text
Gateway retry 2 attempts × Resource Server introspection 2 attempts
= tối đa 4 introspection attempts cho một client request
~~~

Nếu còn service mesh retry thêm nữa, tổng mức khuếch đại có thể tăng. Cần xác định **chỉ một hoặc vài vị trí được phép retry**, loại request nào an toàn để lặp, và cách chia deadline xuyên hệ thống. Không để gateway tự retry các API có side effect chỉ vì nhận 503 nếu business request có thể đã bắt đầu thực thi ở một nhánh khác.

### 17.4. Thử nghiệm dưới mô hình nhiều issuer

Nếu Resource Server dùng nhiều issuer/introspection endpoints:

~~~text
Issuer A: healthy
Issuer B: slow / 503
~~~

Đừng để circuit breaker của Issuer B làm khóa mọi token Issuer A, trừ khi kiến trúc thực sự chia sẻ một tài nguyên bắt buộc. Nên có metrics và capacity theo issuer alias/trust policy, đồng thời không tin claim issuer chưa xác minh để tự động chọn introspection endpoint ngoài allowlist.

## 18. Runbook vận hành khi introspection endpoint bị lỗi

Khi thấy tỷ lệ lỗi tăng, có thể xử lý theo các bước sau mà **không nới lỏng xác thực**.

### 18.1. Nhận diện đúng loại sự cố

Phân biệt:

~~~text
A. active=false tăng, AS trả 200 ổn định
   → Client/token issuance/expiration/abuse issue

B. AS trả 401/403 cho introspection client
   → Credential/permission/config issue

C. AS trả 429
   → Capacity/quota/retry amplification issue

D. AS trả 5xx hoặc timeout
   → Upstream outage/network/service degradation

E. JSON sai, thiếu active hoặc metadata thay đổi
   → Protocol/contract incompatibility
~~~

Không dùng một lệnh bật `permitAll()` cho các endpoint để “tạm chữa” C/D; cách đó có thể biến một API bảo vệ thành API công khai trong thời gian outage.

### 18.2. Nếu AS đang 429 hoặc 503

- Xác nhận retry budget và circuit breaker đang giảm outbound calls, không khuếch đại.
- Kiểm tra saturation của HTTP connection pool, Servlet threads hoặc reactive event loops.
- Kiểm tra các instance có cùng policy attempts/timeout hay một phiên bản cũ đang retry nhiều.
- Liên hệ chủ sở hữu AS về quota, capacity, timeouts và rollout gần đây.
- Nếu có cache entry hợp lệ, chỉ sử dụng theo TTL/freshness đã được phê duyệt; không bật stale vô hạn.
- Nếu không có bằng chứng xác thực, trả lỗi tạm thời/không xác thực theo policy và giữ boundary bảo mật.
- Quan sát khi AS phục hồi để đóng circuit breaker dần, tránh cho toàn bộ traffic vào ngay một lúc.

### 18.3. Nếu introspection client secret không còn hợp lệ

- Xác nhận secret/certificate từ secret manager và rotation schedule.
- Không log Basic header hoặc nguyên secret trong ticket.
- Không retry các HTTP 401 caller-auth mãi; lỗi này thường không tự hết sau 100 ms.
- Cập nhật credential qua quy trình được phê duyệt và xác nhận AS cho phép đúng caller introspection.
- Bảo đảm mọi instance được rollout với secret mới trong thời gian chính sách cho phép.

### 18.4. Nếu token invalid tăng sau một đợt triển khai

- Kiểm tra Authorization Server có thay token issuance, TTL, client policy hoặc token profile không.
- Kiểm tra Resource Server có đổi audience/issuer/scope mapping hoặc introspection caller không.
- Kiểm tra cache/clock/replica lag, nhưng không tạm đổi `active=false` thành `active=true`.
- Tách số lỗi ở decoder/introspector với lỗi authorization thiếu scope hoặc quyền bản ghi.

### 18.5. Khi được yêu cầu “cho qua tạm lúc IdP hỏng”

Cần trả lời bằng chính sách:

~~~text
Không có kết quả xác minh tin cậy:
    KHÔNG tạo Authentication
    KHÔNG cấp quyền mặc định
    KHÔNG trả dữ liệu bảo vệ

Giải pháp vận hành:
    giảm tải/retry có giới hạn
    circuit breaker/bulkhead
    cache kết quả xác minh còn hạn (nếu policy cho phép)
    khôi phục AS/cấu hình/secrets
    trả lỗi dịch vụ rõ ràng và retry guidance hợp lý
~~~

Nếu nghiệp vụ cần khả năng hoạt động ngoại tuyến, đó phải là một **kiến trúc authentication được thiết kế trước** với bằng chứng cục bộ và chính sách thu hồi/freshness rõ ràng, không phải một `catch(Exception) { permitAll(); }` trong Resource Server.

## 19. Những quyết định phải thống nhất với Authorization Server

Một Resource Server không thể tự đặt retry policy hiệu quả nếu không biết hạ tầng AS có khả năng đáp ứng ra sao.

### 19.1. Hợp đồng introspection tối thiểu

| Chủ đề | Câu hỏi cần làm rõ |
|---|---|
| URI/trust | Endpoint chính thức là gì? Có thay đổi theo môi trường/issuer không? |
| Client authentication | Dùng Basic, private_key_jwt, mTLS hoặc cơ chế nào? Rotation như thế nào? |
| Token types | AS có introspect opaque token, JWT access token hoặc nhiều profile không? |
| `active` | Khi nào trả false: expiry, revoke, client disabled, session revoked? |
| Audience/resource | AS trả `aud`, resource indicator hay tự áp policy cho introspection client? |
| Metadata | Claims nào bắt buộc để xây principal/scope/tenant? |
| Timeout | p95/p99 thực tế, giới hạn server và gateway là bao nhiêu? |
| Rate limit | Quota theo client, IP, tenant hay toàn cụm? Có `Retry-After` không? |
| Retry semantics | Có được retry POST introspection sau read timeout không? |
| Availability | SLO, các khu vực dự phòng, failover endpoint được phép |
| Revocation | Độ trễ khi revoke token/session/client, consistency giữa replicas |
| Caching | AS có cho phép cache `active=true` không? Giới hạn tối đa? |
| Error contract | HTTP 401/403/429/5xx/response malformed được phân loại thế nào? |
| Observability | Alert và thông tin chẩn đoán nào không chứa credential? |

Các giá trị retry và cache **phải đáp ứng những ràng buộc này**. Ví dụ AS quy định không retry trên HTTP 429 nhưng client lại retry không giới hạn thì ngay cả một implementation có tên “resilient” cũng làm hệ thống yếu đi.

### 19.2. Failover endpoint cần danh sách tin cậy

Nếu AS có vùng dự phòng:

~~~text
primary:   https://idp-primary.example.test/oauth2/introspect
secondary: https://idp-backup.example.test/oauth2/introspect
~~~

Chỉ failover khi hai endpoint được thiết kế để chia sẻ **nguồn trạng thái token tương đương** và trust policy phù hợp. Một secondary trả `active=false` vì chưa đồng bộ không thể tự bị bỏ qua để tìm secondary khác trả true. Quy tắc phải thống nhất với AS về replica consistency, client credentials, TLS và revocation.

Đừng thử “địa chỉ introspection dự phòng” lấy từ claim trong Bearer token hoặc redirect chưa được xác thực. Những URL này phải thuộc **trust registry được phê duyệt**. Tránh vô tình gửi token/secret tới một hostname không đáng tin trong quá trình retry/failover.

### 19.3. Mỗi issuer có policy và circuit riêng khi cần

Một Resource Server chấp nhận nhiều issuer nên phân tách:

~~~text
Issuer A:
  trusted introspection URI A
  credentials A
  audience policy A
  circuit/bulkhead/rate budget A

Issuer B:
  trusted introspection URI B
  credentials B
  audience policy B
  circuit/bulkhead/rate budget B
~~~

Không trộn kết quả cache giữa các issuers. Claim `iss` chưa xác minh có thể được dùng để chọn một cấu hình từ **allowlist**, nhưng không được khiến Resource Server tự động gửi Bearer token đến URI tùy ý do client nhập.

## 20. Checklist trước khi đưa chính sách vào production

### 20.1. Bắt buộc về bảo mật

- [ ] Token invalid hoặc `active=false` không bị retry.
- [ ] Timeout/503/429 không tạo principal mặc định.
- [ ] Response thiếu `active` hoặc metadata bắt buộc không được coi là success.
- [ ] Issuer, audience, scope, token type và thời gian hiệu lực vẫn được kiểm tra theo hợp đồng.
- [ ] Không sử dụng cache entry sau expiry/freshness window đã phê duyệt.
- [ ] Không dùng stale-if-error ngoài chính sách bảo mật đã được chấp thuận.
- [ ] Không ghi raw token, introspection client secret, Basic header hay response claims nhạy cảm vào logs/traces.
- [ ] Không tự động chuyển request sang endpoint introspection không đáng tin.
- [ ] Circuit breaker/bulkhead rejection dừng authentication, không bỏ qua filter.

### 20.2. Bắt buộc về tài nguyên và resilience

- [ ] `maxAttempts` bao gồm lần đầu và có giới hạn nhỏ.
- [ ] Per-attempt connect/response timeout được cấu hình ở HTTP client thực.
- [ ] Tổng operation deadline giới hạn attempts + backoff + queue wait.
- [ ] Retry chỉ áp cho allowlist lỗi transient đã được phân loại.
- [ ] HTTP 429 được xử lý theo rate limit/`Retry-After` và tổng budget.
- [ ] Có backoff và jitter nếu policy cho retry.
- [ ] Concurrency/bulkhead/queue đều có giới hạn.
- [ ] Retry budget xét khả năng khuếch đại trên toàn cụm.
- [ ] Circuit breaker không bị mở bởi `active=false`.
- [ ] HALF_OPEN chỉ cho probe số lượng nhỏ, tránh phục hồi đồng loạt.
- [ ] Có kế hoạch khi AS quay lại hoặc degraded kéo dài.

### 20.3. Bắt buộc về tích hợp và quan sát

- [ ] `OpaqueTokenIntrospector` hoặc `ReactiveOpaqueTokenIntrospector` đúng là implementation được security chain sử dụng.
- [ ] Exception mapping giữ quyết định fail-closed trên Servlet và WebFlux.
- [ ] Gateway retries không cộng dồn không kiểm soát với retries nội bộ.
- [ ] Có metrics attempts, retry, latency, timeout, 429, 5xx, circuit/bulkhead, cache freshness.
- [ ] Metric labels và logs không chứa token/subject/email không được phê duyệt.
- [ ] Có test cho `active=true`, `active=false`, 401 client secret, 429, 503, timeout, malformed, stale cache.
- [ ] Test đo số outbound calls và thời gian tối đa, không chỉ HTTP status.
- [ ] Có test tải khi nhiều Resource Server instances cùng gặp lỗi AS.

Checklist này là **công cụ thiết kế triển khai**, không thay thế threat modeling, review vận hành của đội IAM/Security hoặc test thật của hệ thống.

## 21. Các hiểu lầm thường gặp

### 21.1. “Gặp lỗi gì cứ retry ba lần là tăng availability”

Sai. Token invalid, client secret sai và TLS trust failure thường không tự hết sau retry. Ngược lại, retry 503 trên hàng chục instances có thể khuếch đại tải và làm AS lâu phục hồi hơn. Retry phải **có điều kiện**, giới hạn thời gian và giới hạn concurrency.

### 21.2. “HTTP 200 từ introspection nghĩa là token đúng”

Sai. RFC 7662 trả `active=false` trong một HTTP 200 hợp lệ. Resource Server phải kiểm tra nội dung `active` và metadata resource. Retry `active=false` là retry một **kết quả nghiệp vụ hoàn tất**, không phải retry network failure.

### 21.3. “Introspection 401 là người dùng gửi token sai”

Không nhất thiết. HTTP 401 từ **introspection endpoint** thường chỉ lỗi authentication của **client gọi introspection**. Nó khác HTTP 401 Resource Server trả cho **caller API** khi Bearer token invalid. Phân loại nhầm khiến hệ thống che lỗi secret rotation và retry vô ích.

### 21.4. “Circuit breaker OPEN thì ứng dụng nên tạm cho qua auth”

Sai. Circuit breaker nhằm **giảm tải cho upstream** và cho lỗi nhanh khi không thể xác minh; nó không phải công tắc bỏ qua authentication. Nếu không có bằng chứng còn hiệu lực theo policy, không tạo principal.

### 21.5. “Tổng timeout 900 ms là đủ dù mỗi call có thể treo 30 s”

Sai. Một wrapper đo thời gian sau khi HTTP call kết thúc **không thể tự ngắt call đang treo**. Cần các timeouts ở HTTP client/connection pool, tổng deadline, cancellation và quan sát tài nguyên thực tế.

### 21.6. “Cache giúp giữ mọi token hoạt động khi AS hỏng”

Sai. Cache chỉ có thể lưu **kết quả xác minh trước đây** và cần TTL/freshness, token expiry và revocation policy rõ. Cache entry hết hạn không tự thành bằng chứng token vẫn active.

### 21.7. “Bật cache 60 giây nhưng vẫn thu hồi token tức thì”

Không chắc. Một `active=true` được cache có thể tồn tại sau khi AS đã revoke token. Nếu cần thu hồi nhanh hơn, phải giảm/loại cache hoặc có invalidation/synchronization phù hợp.

### 21.8. “Khi introspection timeout, thử đổi sang mọi endpoint cùng domain”

Nguy hiểm. Chỉ chuyển tới URI đã được công bố và tin cậy trong **failover contract**. Không gửi raw token và client secret tới endpoint ngẫu nhiên hoặc hostname do input chưa xác minh ảnh hưởng.

### 21.9. “Resilience4j annotations tự bảo đảm chính sách xác thực”

Không. Thư viện resilience giải quyết retry/circuit/bulkhead ở mức gọi hàm, nhưng **không tự hiểu** ý nghĩa `active=false`, audience, client credentials, scope và trust boundary. Ứng dụng phải phân loại lỗi đúng và để security provider từ chối khi chưa xác minh được token.

### 21.10. “Token hợp lệ thì không cần HTTP authorization”

Sai. `active=true` chỉ là một phần của authentication. Orders API còn cần `SCOPE_orders.read` hoặc quyền khác, và phải kiểm tra owner/tenant theo từng bản ghi.

## 22. Tình huống thực hành: một đợt 503 kéo dài 20 giây

Hệ thống giả định:

~~~text
Orders API instances:           8
Requests requiring introspect:  100/s mỗi instance
Total incoming to AS:           800/s (chưa tính retry)
Normal AS p95 latency:           70 ms
Transient 503 rate:              80% trong 20 giây
Max attempts per request:       2
Total introspection budget:     900 ms
Max in-flight per instance:     40
~~~

### 22.1. Nếu retry không có giới hạn

Mỗi request có thể gửi nhiều calls; nhiều instances chờ và retry đồng loạt. Tổng outbound rate có thể lớn hơn nhiều mức 800/s ban đầu, làm AS phục hồi chậm. Thread/connection pools của Resource Server cũng bị chiếm lâu.

### 22.2. Với retry có giới hạn và circuit breaker

Giả sử policy giới hạn:

~~~text
1 initial attempt + tối đa 1 retry được phê duyệt
Backoff jitter: 50–150 ms
Total budget: 900 ms
Bulkhead: tối đa 40 in-flight mỗi instance
Circuit breaker: mở khi đủ dữ liệu lỗi transient
Retry budget: chia theo quota AS
~~~

Ở những request đầu:

1. Nếu AS trả 200 `active=true` với metadata hợp lệ, tiếp tục authentication và authorization.
2. Nếu AS trả 200 `active=false`, từ chối ngay, không retry.
3. Nếu AS trả 503, chỉ retry khi còn budget và capacity permit.
4. Nếu tiếp tục 503 hoặc hết deadline, không tạo principal, trả lỗi theo policy.
5. Khi circuit breaker mở, dừng gửi phần lớn calls và fail nhanh; HALF_OPEN chỉ thử một số request giới hạn.
6. Khi AS phục hồi, circuit dần đóng theo policy, không cho toàn bộ requests vượt quota bất ngờ.

### 22.3. Một token đã được cache thì sao?

Nếu token có `active=true` đã được introspect trước outage và **cache entry vẫn trong TTL/freshness và trước `exp`**, hệ thống có thể dùng entry đó theo chính sách được duyệt. Nếu entry hết TTL trong outage, mặc định fail closed; không tạo kết quả `active=true` từ “lần trước có vẻ ổn”.

### 22.4. Điều kiện để kết luận giải pháp phù hợp

Không thể chỉ nói “API vẫn trả được bao nhiêu phần trăm request”. Cần kiểm tra **hai chiều**:

**Bảo mật:** không có token invalid/unknown nào được cho qua, không mất audience/scope validation, không lộ credential.

**Vận hành:** tổng outbound attempts trong giới hạn, không queue vô hạn, p99 response/timeouts có kiểm soát, circuit hoạt động như thiết kế và có cảnh báo chính xác theo loại lỗi.

## 23. Ghi nhớ chính sách tổng thể

~~~mermaid
flowchart TD
    A["Bearer access token"] --> B{"Có cache result đã xác minh, còn hạn và policy cho phép?"}
    B -->|Có| C["Dùng verified attributes còn hiệu lực"]
    B -->|Không| D{"Circuit/capacity cho phép call AS?"}
    D -->|Không| U["UNAVAILABLE: không tạo principal"]
    D -->|Có| E["Introspection HTTP với deadline và timeouts"]
    E --> F{"Kết quả?"}
    F -->|"active=true + metadata đúng"| G["Authenticated principal"]
    F -->|"active=false / policy invalid"| I["INVALID: không tạo principal"]
    F -->|"Transient failure"| R{"Còn retry budget + deadline?"}
    R -->|Có| E
    R -->|Không| U
    F -->|"Configuration/protocol failure"| U
    C --> H["Kiểm tra scope/HTTP/domain authorization"]
    G --> H
    H --> J["Trả API data chỉ khi được phép"]
~~~

**Nguyên tắc cốt lõi:**

1. **Retry có điều kiện:** chỉ với lỗi transient phù hợp, không retry `active=false`, 401 client credentials hoặc response sai policy.
2. **Giới hạn đồng thời:** attempts, total deadline, connection/read timeouts, concurrency, queue, retry budget và rate-limit phải có ranh giới thực.
3. **Giảm tải chủ động:** circuit breaker, bulkhead, jitter và cache có kiểm soát giúp AS không bị retry storm.
4. **Không bỏ xác minh:** nếu không có một kết quả introspection đáng tin hoặc cache evidence còn hiệu lực theo policy, Resource Server không tạo `Authentication` thành công.
5. **Không bỏ phân quyền:** token active vẫn phải qua issuer/audience/time/profile, scope và quyền trên tài nguyên.
6. **Không tiết lộ credential:** bảo vệ raw token và introspection client secret khỏi logs, traces, lỗi và hệ thống hỗ trợ.

**“Thử lại có giới hạn, quá tải và chính sách lỗi không bỏ qua xác minh”** không chỉ là lựa chọn vài tham số HTTP. Đây là cách xác định **ranh giới tin cậy khi Authorization Server không sẵn sàng**: phục hồi có kiểm soát khi lỗi tạm thời, giảm áp lực lên upstream khi quá tải, và duy trì quyết định bảo mật nhất quán — **không cấp quyền khi chưa thể xác thực token**.

## Tài liệu tham khảo

- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662)
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749)
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009)
- [RFC 9110 — HTTP Semantics (bao gồm status và Retry-After)](https://www.rfc-editor.org/rfc/rfc9110)
- [Spring Security — Servlet OAuth 2.0 Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html)
- [Spring Security — Reactive OAuth 2.0 Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/opaque-token.html)
- [Spring Security — OpaqueTokenIntrospector Javadoc](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/server/resource/introspection/OpaqueTokenIntrospector.html)
- [Spring Security — ReactiveOpaqueTokenIntrospector Javadoc](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/server/resource/introspection/ReactiveOpaqueTokenIntrospector.html)
- [Spring Security — Servlet Architecture](https://docs.spring.io/spring-security/reference/servlet/architecture.html)
- [Spring Boot — Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html)
- [Resilience4j — Documentation](https://resilience4j.readme.io/docs)
- [Project Reactor — Retry Reference](https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html)
- [OWASP Cheat Sheet — REST Security](https://cheatsheetseries.owasp.org/cheatsheets/REST_Security_Cheat_Sheet.html)
- [OWASP Cheat Sheet — Logging](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html)
