# 429, Retry-After và metadata hạn mức theo hợp đồng

## 1. Từ quá nhiều request đến một hợp đồng điều tiết lưu lượng

Giả sử ứng dụng bán hàng có Java client đồng bộ dữ liệu và một frontend gọi REST API. Khi client gửi quá nhiều request trong một khoảng thời gian, API có thể trả **429 Too Many Requests**. Nếu client lập tức thử lại hàng loạt, cả API lẫn hệ thống phụ thuộc có thể quá tải hơn. Nếu server chỉ trả một JSON lỗi mơ hồ, client cũng không biết phải đợi bao lâu.

**Rate limiting** là cơ chế kiểm soát mức sử dụng API theo một hoặc nhiều hạn mức: số request, dung lượng, chi phí tính toán, số tác vụ đồng thời hoặc năng lực của gói dịch vụ. Nhưng giới hạn chỉ thực sự hữu ích cho hệ thống tích hợp khi **server và client có hợp đồng HTTP rõ ràng** về:

- Điều kiện nào dẫn đến 429 và phạm vi tính quota.
- Khi nào client có thể thử lại: **Retry-After** và/hoặc metadata quota.
- Header nào được công bố, đơn vị và ý nghĩa của chúng.
- Hành vi với **429, 503, 409, timeout, idempotency** và request có side effect.
- Cách backoff, phân quyền, quan sát và kiểm thử dưới tải đồng thời.

Trong module **INTEGRATION_API_REST**, các lựa chọn này gắn với resource/URI, HTTP method/status, cache, OpenAPI, xác thực, phân quyền, hợp đồng dữ liệu và client Java/Spring.

> **Nguyên tắc:** 429 là phản hồi **từ chối request hiện tại vì giới hạn sử dụng**, không phải lời bảo đảm rằng lần thử tiếp theo sẽ thành công. **Retry-After là hướng dẫn thời điểm chờ**, còn quyền retry thao tác ghi phải được xét riêng qua tính lũy đẳng.

### 1.1. Ví dụ HTTP từ chối vì quota

~~~http
GET /api/orders?limit=20 HTTP/1.1
Host: api.example.test
Authorization: Bearer <access-token>
Accept: application/json

HTTP/1.1 429 Too Many Requests
Content-Type: application/problem+json
Retry-After: 30
Cache-Control: no-store

{
  "type": "https://api.example.test/problems/rate-limited",
  "title": "Too Many Requests",
  "status": 429,
  "detail": "Request quota exceeded; retry later.",
  "code": "RATE_LIMITED"
}
~~~

Phần JSON sử dụng **Problem Details (RFC 9457)**. Các thành viên **type, title, status, detail** có ngữ nghĩa chuẩn; **code** là extension tự định nghĩa. Không bắt buộc mọi API có 429 đều trả Problem Details, nhưng một API nên chọn một schema lỗi công khai nhất quán. **Không** đưa access token, toàn bộ quota của khách hàng khác, key nội bộ hay stack trace vào response.

Trong ví dụ, **Retry-After: 30** có nghĩa client nên chờ **ít nhất khoảng 30 giây sau khi nhận response** trước khi thử lại theo chính sách áp dụng. Giá trị này **không cấp quyền** truy cập tài nguyên, không hủy yêu cầu cũ và không đảm bảo một slot quota chắc chắn có sẵn.

## 2. Khi nào trả 429, khi nào không?

| Tình huống | Mã HTTP phù hợp | Điểm phân biệt |
|---|---|---|
| Principal/tenant vượt giới hạn request của API | **429 Too Many Requests** | Client bị throttle theo quota |
| Toàn dịch vụ tạm quá tải hoặc bảo trì | **503 Service Unavailable** | Phản ánh tình trạng phục vụ, không nhất thiết là quota cá nhân |
| Gateway hết thời gian chờ upstream | **504 Gateway Timeout** | Không xác định chắc chắn trạng thái xử lý upstream |
| Client thiếu/sai bearer token | **401 Unauthorized** | Cần xác thực, không biến thành quota 429 tùy tiện |
| Token hợp lệ nhưng thiếu quyền trên operation | **403 Forbidden** | Phân quyền, không phải hết quota |
| Payload/định dạng JSON không hợp lệ | **400 Bad Request** | Client phải sửa input |
| Cùng Idempotency-Key với payload khác | **409 Conflict** | Ý định nghiệp vụ xung đột, retry không sửa được |
| Precondition If-Match không đạt | **412 Precondition Failed** | Trạng thái resource đã thay đổi |
| Client gửi quá nhiều byte trong một body | **413 Content Too Large** | Giới hạn kích thước payload, không nhất thiết quota số lượt |
| Backend gặp lỗi không phân loại | **500 Internal Server Error** | Không che bug bằng 429 |

**429 không đồng nghĩa “mọi lỗi retryable”.** Server có thể dùng 429 khi áp giới hạn tốc độ/khối lượng theo người dùng hoặc client. Một hệ thống cũng có thể dùng 503 khi quá tải toàn cục và kèm Retry-After nếu có ước lượng thời gian phục hồi; quyết định ranh giới phải được ghi rõ trong contract.

**Đừng dựa vào status để đoán lệnh POST đã commit hay chưa.** Một request bị từ chối ngay tại rate limiter trước nghiệp vụ khác với timeout **sau khi server đã tạo đơn**. Khi có nhiều gateway, proxy hoặc retry tầng mạng, client nên dựa vào hợp đồng **idempotency/operation status** để xác định tác dụng của request.

### 2.1. Tầng phát hiện 429

~~~text
Java client / Browser
        |
     CDN / WAF       (có thể giới hạn theo IP, bot score)
        |
    API Gateway      (API key, tenant, plan, route)
        |
   Spring Security   (JWT, scope, tenant)
        |
    Application      (quota theo nghiệp vụ/cost)
        |
   Database/Redis    (counters, token bucket, ledger)
~~~

Cùng một request có thể chịu **nhiều chính sách**. Một limit “100 request/phút” ở gateway không bảo đảm database có đủ kết nối để phục vụ ngay. Cần tránh để gateway và ứng dụng gửi **metadata mâu thuẫn** hoặc âm thầm thay 429 thành 500. Quy định rõ tầng nào phát hành header quota, tầng nào điều phối Retry-After và schema lỗi.

## 3. Retry-After: cú pháp, cách hiểu và giới hạn

Theo HTTP Semantics **RFC 9110**, Retry-After có hai dạng hợp lệ:

~~~http
Retry-After: 120
Retry-After: Wed, 21 Oct 2015 07:28:00 GMT
~~~

- **delay-seconds:** số nguyên thập phân **không âm**, đơn vị giây. `Retry-After: 1.5`, `-1` hoặc `120ms` không đúng dạng này.
- **HTTP-date:** thời điểm cụ thể theo cú pháp HTTP date. Một client cần so với thời gian phù hợp, lưu ý clock skew và độ trễ mạng.
- **Giá trị thiếu/sai:** client không được treo vô hạn hoặc crash vì header hỏng; áp retry policy/backoff có giới hạn hoặc dừng nếu request không an toàn để retry.
- **Giới hạn trên:** server có thể gửi số giây rất lớn hoặc ngày xa trong tương lai; client phải áp **max retry delay** và deadline tổng theo sản phẩm.

Khi header xuất hiện trong **429**, nó cung cấp gợi ý chờ để thử lại request; khi ở **503**, nó báo thời gian server dự kiến chưa sẵn sàng. Retry-After cũng được định nghĩa dùng với chuyển hướng 3xx; không diễn giải mọi trường hợp thành “hết quota”.

### 3.1. Bẫy thời gian

Ví dụ hai response về mặt thời gian:

~~~http
HTTP/1.1 429 Too Many Requests
Date: Wed, 18 Nov 2026 10:00:00 GMT
Retry-After: 45
~~~

~~~http
HTTP/1.1 429 Too Many Requests
Date: Wed, 18 Nov 2026 10:00:00 GMT
Retry-After: Wed, 18 Nov 2026 10:00:45 GMT
~~~

Hai header minh họa ý định “chờ đến khoảng 45 giây sau” nhưng **không hoàn toàn tương đương với client có đồng hồ lệch hoặc response tới muộn**. Khi API có thể chọn định dạng, delay-seconds thường dễ thực thi hơn; nếu dùng HTTP-date, client nên xử lý theo HTTP-date chuẩn, giữ giới hạn thời gian và tránh clock skew lớn.

**Không suy rằng Retry-After là thời điểm reset của tất cả các quota.** Một user có thể gặp giới hạn **per-second**, **per-minute** và **per-day**, hoặc thêm giới hạn concurrency. Khi nhiều ràng buộc cùng áp dụng, metadata phải chỉ ra chính sách/bottleneck theo contract; client không thể đoán từ một giá trị Retry-After.

### 3.2. Ưu tiên giữa Retry-After và metadata quota

Nếu response có cả Retry-After và thông tin quota, **client nên lấy Retry-After làm chỉ dẫn chờ trực tiếp**, sau đó tuân thủ giới hạn deadline/retry của mình. Metadata còn lại giúp dự báo tốc độ các request tương lai, nhưng quota có thể đổi vì load, cấu hình plan hoặc các client khác cùng chia hạn mức.

Ví dụ `remaining=20` **không phải lời bảo đảm** rằng 20 request tới sẽ được phục vụ: quota có thể chia sẻ với tác vụ song song, nhiều route hoặc gateway; policies còn có thể giới hạn đồng thời, tổng byte hoặc điểm chi phí.

## 4. Metadata quota: chỉ tương thích khi định nghĩa rõ cú pháp

Trên thực tế có nhiều kiểu header truyền thông tin giới hạn. API phải nêu **tên header, đơn vị, window, reset semantics, partition key và thời gian hiệu lực**. Không thể chỉ viết “trả RateLimit headers” rồi để SDK tự suy diễn.

### 4.1. Các header X-RateLimit-* thường gặp là quy ước của provider

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 7
X-RateLimit-Reset: 1795000000
Cache-Control: private
~~~

**Đây là ví dụ giao thức riêng**, trong đó *giả định* `X-RateLimit-Limit` là 100 request của cửa sổ, `X-RateLimit-Remaining` là số request còn lại và `X-RateLimit-Reset` là **Unix timestamp tính bằng giây**. Một provider khác có thể định nghĩa Reset là số **giây còn lại**, HTTP-date hoặc milliseconds; **không được suy từ tên header**. Các field X-RateLimit-* không đồng nghĩa một chuẩn thống nhất có thể parse tùy ý giữa các đối tác.

Nếu API tự thiết kế bộ header riêng, công bố chính xác:

| Thuộc tính | Ví dụ contract cụ thể |
|---|---|
| Chính sách áp dụng | `orders.read` của tenant và API client |
| Cửa sổ | 100 request cho mỗi 60 giây, theo fixed window |
| Limit | 100 đơn vị request |
| Remaining | Số đơn vị còn sau request vừa xử lý |
| Reset | Unix epoch seconds UTC, **không phải milliseconds** |
| Đơn vị tính | 1 lượt GET = 1 quota unit; POST có thể khác |
| Các chính sách khác | Có thêm quota/ngày, concurrency, cost-based |
| Khi có nhiều lớp | Metadata do gateway phát, app không ghi đè |

### 4.2. RateLimit-Policy và RateLimit ở hướng chuẩn hóa IETF

IETF HTTPAPI đang phát triển **RateLimit-Policy** và **RateLimit** để thống nhất cách công bố quota. **Bản Internet-Draft tham chiếu năm 2026 chưa nên bị xem là hợp đồng RFC đã chốt**; người triển khai phải pin phiên bản, kiểm trạng thái cập nhật và thử tương thích với client.

Ví dụ cú pháp **theo Internet-Draft**:

~~~http
RateLimit-Policy: "perminute";q=100;w=60
RateLimit: "perminute";r=0;t=25
Retry-After: 25
~~~

Theo cú pháp tham chiếu: **q=100** là quota units của policy trong **w=60** giây; **r=0** là quota còn lại và **t=25** là thời gian hiệu lực còn lại được công bố cho chính sách. Các parameter này thuộc **structured fields**, không phải CSV tự định nghĩa; hệ thống production nên dùng parser tương thích phiên bản đặc tả chứ không parse thủ công bằng tách chuỗi đơn giản.

Chính sách thực tế có thể nhiều cửa sổ hoặc đơn vị khác **request count** (ví dụ bytes, chi phí, in-flight). Các giá trị quota chỉ là **thông tin điều phối**, không thay thế 429/503, authentication/authorization hay lời bảo đảm SLA. Khi cùng response có Retry-After, ứng dụng cần ưu tiên chỉ dẫn chờ phù hợp và không suy rằng `t` chắc chắn bằng Retry-After trên mọi API.

**Tài liệu tham khảo:** [RFC 9110 – Retry-After](https://www.rfc-editor.org/rfc/rfc9110#section-10.2.3), [RFC 6585 – 429](https://www.rfc-editor.org/rfc/rfc6585#section-4), [RFC 9457 – Problem Details](https://www.rfc-editor.org/rfc/rfc9457), và [IETF HTTPAPI RateLimit Internet-Draft](https://datatracker.ietf.org/doc/draft-ietf-httpapi-ratelimit-headers/). Tên header/quota cho sản phẩm phải dựa trên **bản contract đang triển khai** chứ không mặc định mọi API đồng nhất.

## 5. Thiết kế quota: thuật toán, phân vùng và điểm kiểm soát

**Rate limit policy** nên trả lời được: *Ai* bị giới hạn, *thao tác nào* tiêu thụ quota, *đơn vị tính* là gì, *cửa sổ/thời điểm reset* ra sao và *ai* chịu trách nhiệm thực thi.

### 5.1. Các thuật toán thường dùng

| Thuật toán | Cách hoạt động | Ưu điểm / rủi ro |
|---|---|---|
| **Fixed window counter** | Đếm số lần trong mỗi khoảng thời gian cố định | Dễ triển khai; có thể cho phép burst gần **gấp đôi limit** ở ranh giới hai cửa sổ |
| **Sliding window log/counter** | Cửa sổ dịch theo thời gian; log chính xác hoặc xấp xỉ có trọng số | Mượt hơn fixed window nhưng tốn lưu trữ/tính toán hoặc có sai số |
| **Token bucket** | Bucket có sức chứa tối đa; token nạp theo tốc độ, request dùng token | Hỗ trợ burst ngắn và tốc độ dài hạn; cần đồng bộ refill/consume |
| **Leaky bucket / paced queue** | Điều tiết đầu ra với tốc độ định trước | Hữu ích làm mượt tải; queue quá dài tăng latency và có thể cần từ chối |
| **Concurrency limiter** | Giới hạn số request đang thực thi | Bảo vệ tài nguyên bận; không đồng nghĩa N request/phút |
| **Cost-based quota** | Mỗi request tiêu thụ điểm khác nhau | Phản ánh truy vấn nặng; phải định nghĩa/giới hạn cost, tránh abuse |

Ví dụ **token bucket** có capacity **10**, refill **1 token/giây**: request GET đơn giản dùng 1 token, search nặng có thể dùng 3 tokens. Burst 10 GET gần nhau được chấp nhận, sau đó request thứ 11 có thể nhận 429 nếu bucket chưa nạp. **Retry-After** có thể dựa trên thời gian để có đủ tokens cho request tương ứng; không chỉ là thời gian token đầu tiên xuất hiện nếu request cần cost=3.

Fixed window 100 request/phút có thể cho 100 request ở giây 59 và 100 request ở giây 60. Điều này **không nhất thiết vi phạm fixed-window policy**, nhưng có thể vượt khả năng backend. Vì vậy quota theo gói dịch vụ và **overload protection** (concurrency/circuit breaker/queue bound) nên là hai lớp bổ sung.

### 5.2. Phân vùng theo identity, tenant, API key và route

~~~text
request
  -> authenticate caller / validate API key
  -> identify tenant and entitlement
  -> select route + cost + applicable policies
  -> atomically reserve quota
  -> authorize object / validate input / execute business
  -> emit consistent HTTP status and rate metadata
~~~

**Phạm vi chính sách** có thể phối hợp:

- 100 request/phút theo **API key** để bảo vệ tích hợp.
- 1.000 request/phút theo **tenant** để bảo đảm công bằng khi nhiều keys thuộc cùng doanh nghiệp.
- 10 request/giây theo **user** trên endpoint tìm kiếm tốn CPU.
- 5 requests đồng thời cho **export/report**; tách quota đồng thời với tốc độ.
- Hạn mức **daily budget** cho thao tác tốn phí, tách khỏi limit ngắn hạn.

Nếu request phải qua **tất cả** giới hạn, policy cần nói rõ quota nào bị trừ khi một policy khác từ chối. Với nhiều bucket, cần kiểm tra/reserve theo cách nhất quán, tránh **trừ quota một phần** do race giữa các node. Thực thi phân tán thường dùng Redis/atomic script, gateway có quota store chia sẻ hoặc dịch vụ quota riêng, tùy tải và rủi ro.

**Đừng chỉ giới hạn theo IP** cho API đã có authentication: nhiều người hợp lệ cùng NAT có thể bị giới hạn chung, trong khi bot có thể thay IP. IP có thể là lớp chống abuse, nhưng phải xác minh **địa chỉ client thật qua chuỗi trusted proxy**. Không lấy trực tiếp giá trị **X-Forwarded-For** do caller tự gửi để quyết định quota/tenant.

### 5.3. Các quyết định thực thi ảnh hưởng đến hợp đồng

Với request thiếu JWT hoặc token sai, thường nên xử lý **401** trước khi trả quota theo tenant, nếu không sẽ vô tình tiết lộ trạng thái một tài khoản chưa xác thực. Ở gateway vẫn có thể có **IP/anonymous throttling** trước authentication để chống brute force; khi đó tầng nào phát hành 429 và chính sách ưu tiên 401/429 phải được mô tả.

Với request invalid body (400) và replay **Idempotency-Key**:

- API có thể tính quota cho mọi attempt đến cửa, hoặc chỉ tính cho request đã xác thực/hợp lệ; phải **công bố quy tắc tính** khi nó ảnh hưởng quyền lợi khách hàng.
- Replay của cùng ý định **không tự động miễn quota**; tùy hợp đồng. Server cần tránh trừ hai lần *chi phí nghiệp vụ* nếu đã dedup nhưng vẫn có thể tính request transport để chống spam.
- Nếu request có kết quả **không rõ** do timeout, không dùng key mới để “vượt limit”; giữ idempotency key và inquiry theo contract.

### 5.4. Nhiều replica, đồng hồ và tính nhất quán

Nếu mỗi pod Spring có bộ đếm 100/phút riêng, hệ thống 10 pods có thể cho phép **1.000/phút**, trái với quota tenant 100/phút. Dùng **shared counter/token bucket** hoặc thiết kế phân phối quota đã chứng minh giới hạn. Với token bucket, thao tác **check + consume** cần nguyên tử; dùng cơ chế thời gian/TTL nhất quán, xử lý clock skew, Redis eviction và restart có chủ đích.

Khi kho quota không sẵn sàng, chính sách **fail-open hoặc fail-closed** phải dựa trên mức độ nhạy cảm:

- **Fail closed** với tài nguyên có rủi ro tài chính, credential stuffing, abuse cao; trả **503** cho lỗi hạ tầng quota nếu thích hợp, không gán nhầm 429 như thể đã đo quota.
- **Fail open có giám sát** có thể được chọn cho chức năng đọc ít nhạy cảm khi ưu tiên availability, kèm emergency limiter tại node và cảnh báo.

Không im lặng bypass limiter khi Redis timeout nếu điều đó có thể làm sập hệ thống. Cần quan sát **allowed/denied**, p95/p99 latency của quota store, số lần 429, bucket saturation, retry-after, tỉ lệ 503 và sự bất công giữa tenants — nhưng không dùng tenant ID bí mật hoặc API key làm nhãn metrics cardinality cao.

## 6. CORS, bảo mật và cache khi trả metadata quota

**429 không phải công cụ xác thực.** API phải xác minh JWT/API key, issuer/audience, tenant và scope; response 429 không được cho client A xem chính sách hoặc quota chi tiết của B. User được quyền gọi endpoint vẫn có thể bị hạn chế quota, còn có quota chưa dùng **không cấp quyền** truy cập một resource.

### 6.1. Problem Details và dữ liệu nhạy cảm

Nên dùng mã lỗi ổn định như **RATE_LIMITED**, **RATE_LIMIT_IN_PROGRESS**, **SERVICE_OVERLOADED**, nhưng phải phân biệt với lỗi authentication/authorization. Thông điệp công khai không chứa IP nội bộ, Redis key, account ID ngoài phạm vi caller, chính sách chống bot bí mật hay stack trace.

Với endpoint riêng tư, response **429 có Cache-Control: no-store** là lựa chọn an toàn, tránh proxy chia sẻ lỗi hoặc metadata giữa các users. Nếu API cache representation theo identity, cần thiết kế cache key, Authorization/Vary và mức metadata rõ ràng; **không gắn thông tin quota của user A lên cached 200 được phục vụ cho user B**.

### 6.2. Frontend browser phải đọc được Retry-After

Nếu JavaScript ở **https://app.example.test** gọi API tại **https://api.example.test**, browser thực thi **CORS** khi đọc response. Để frontend đọc header **Retry-After** và metadata không thuộc tập response headers safelisted, server phải expose chúng:

~~~http
HTTP/1.1 429 Too Many Requests
Access-Control-Allow-Origin: https://app.example.test
Access-Control-Expose-Headers: Retry-After, RateLimit, RateLimit-Policy
Vary: Origin
Retry-After: 30
Content-Type: application/problem+json
~~~

Khi dùng cookie/credentials, cấu hình **Access-Control-Allow-Credentials** và allowlist origin cụ thể theo chính sách; **CORS không thay CSRF protection**. Một frontend có thể không đọc được header quota dù network panel hiển thị 429, nếu thiếu **Access-Control-Expose-Headers**. Native Java HttpClient không thực thi CORS như browser nên **không thể dùng test Java thuần để chứng minh browser đọc được header**.

Các custom request headers như **Idempotency-Key** có thể làm browser phát sinh **OPTIONS preflight**. Server phải cấu hình CORS methods/headers phù hợp và cho preflight được xử lý trước khi yêu cầu token của actual POST. Đây là vấn đề khác với 429 của request thật.

## 7. HTTP contract hoàn chỉnh: quy tắc cần công bố

Để client và SDK không suy đoán, một hợp đồng rate-limit tối thiểu nên công bố:

| Quyết định | Ví dụ API đơn hàng |
|---|---|
| Giới hạn theo ai | Tenant ID đã xác minh + client ID |
| Đơn vị quota | GET/POST = 1 request; export = 5 quota units |
| Window/algorithm | 100 units/60 s token bucket, burst tối đa 20 |
| Endpoint áp dụng | /api/orders và /api/orders/{id}, trừ health |
| Phản hồi bị từ chối | 429 + Retry-After + Problem Details code RATE_LIMITED |
| Chính sách metadata | RateLimit/RateLimit-Policy theo phiên bản draft cụ thể hoặc header provider riêng |
| Reset và đơn vị | Seconds/datetime, làm tròn, multiple policies |
| Cache và CORS | no-store với response nhạy cảm; expose Retry-After nếu frontend cần |
| Retry | Exponential backoff + jitter, tổng deadline, giữ Idempotency-Key cho POST |
| In-flight/replay | Có bị trừ quota không? Lỗi 409 khác với 429 thế nào? |
| Quota exhausted vs outage | 429 cho vượt quota; 503 cho lỗi/quá tải toàn cục |
| Quản trị hạn mức | Ai thay policy, cách thông báo thay đổi, khách hàng xem usage ở đâu |

**Không có lý do kỹ thuật để hard-code các giá trị mẫu như một mặc định cho mọi sản phẩm.** API cung cấp bao nhiêu request, khi nào reset, có hỗ trợ burst hay không là quyết định sản phẩm/vận hành; việc diễn giải sai chỉ một unit của Reset có thể khiến client gửi request quá sớm hàng nghìn lần.

## 8. Spring MVC: trả 429 và Problem Details đúng tầng

Ví dụ sau minh họa một controller **chỉ thu quota sau khi Spring Security đã xác thực và kiểm scope**. API mẫu đọc tập hợp đơn riêng tư theo tenant, đơn vị quota = 1 mỗi GET. **Quyết định quota** do một service độc lập trả về; đoạn code controller không triển khai thuật toán hoặc distributed counter.

~~~java
import java.net.URI;
import java.time.Duration;
import java.util.List;
import org.springframework.http.CacheControl;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

record Caller(String subject, String tenantId) {}
record QuotaDecision(
        boolean allowed,
        long remaining,
        Duration retryAfter) {}
record OrderSummary(String id, String status) {}

interface OrderQuota {
    // Thực hiện check+reserve NGUYÊN TỬ trên quota store.
    QuotaDecision checkAndReserve(
            Caller caller, String operation, int cost);
}

interface OrderReadService {
    // Bắt buộc lọc tenant/owner/assignment trong DB.
    List<OrderSummary> listVisible(Caller caller);
}

@RestController
@RequestMapping("/api/orders")
class OrdersController {
    private final OrderQuota quota;
    private final OrderReadService orders;

    OrdersController(OrderQuota quota, OrderReadService orders) {
        this.quota = quota;
        this.orders = orders;
    }

    @GetMapping(produces = "application/json")
    @PreAuthorize("hasAuthority('SCOPE_orders.read')")
    ResponseEntity<?> list(@AuthenticationPrincipal Jwt jwt) {
        Caller caller = fromVerifiedJwt(jwt);
        QuotaDecision decision =
            quota.checkAndReserve(caller, "orders.read", 1);

        if (!decision.allowed()) {
            ProblemDetail problem = ProblemDetail.forStatus(
                HttpStatus.TOO_MANY_REQUESTS);
            problem.setType(URI.create(
                "https://api.example.test/problems/rate-limited"));
            problem.setTitle("Too Many Requests");
            problem.setDetail("Request quota exceeded; retry later.");
            problem.setProperty("code", "RATE_LIMITED");

            // Giả định QuotaDecision trả duration hợp lệ, đã có trần.
            long ms = Math.max(0L, decision.retryAfter().toMillis());
            long seconds = Math.max(1L, ms / 1000 + (ms % 1000 == 0 ? 0 : 1));

            return ResponseEntity.status(HttpStatus.TOO_MANY_REQUESTS)
                .header("Retry-After", Long.toString(seconds))
                .contentType(MediaType.APPLICATION_PROBLEM_JSON)
                .cacheControl(CacheControl.noStore())
                .body(problem);
        }

        return ResponseEntity.ok()
            .cacheControl(CacheControl.noStore())
            .body(orders.listVisible(caller));
    }

    private static Caller fromVerifiedJwt(Jwt jwt) {
        if (jwt == null || jwt.getSubject() == null
                || jwt.getSubject().isBlank()) {
            throw new AccessDeniedException("Missing subject");
        }
        String tenant = jwt.getClaimAsString("tenant_id");
        if (tenant == null || tenant.isBlank()) {
            throw new AccessDeniedException("Missing tenant context");
        }
        return new Caller(jwt.getSubject(), tenant);
    }
}
~~~

**Ranh giới ví dụ:**

- Cần cấu hình **SecurityFilterChain**, JWT issuer/audience/scope mapping, **@EnableMethodSecurity** và các dependency Spring Boot phù hợp. Nếu method security không bật, `@PreAuthorize` ở trên không tự có hiệu lực; route còn cần guard ở SecurityFilterChain.
- **OrderQuota.checkAndReserve** phải có Redis/distributed implementation, partition theo tenant/principal/operation, clock và concurrency tests. Trả 429 trong controller **không tự bảo đảm** giới hạn xuyên các node.
- **OrderReadService.listVisible** phải lọc bản ghi theo tenant/owner, không chỉ theo scope. Nếu service truy cập dữ liệu trước khi gọi quota, client có thể tiêu tốn CPU/DB dù đã hết hạn mức.
- **Không cho request tự gửi tenant_id, cost hoặc quota key** qua JSON/header rồi tin ngay. Caller phải đến từ access token đã được xác minh cùng membership policy.
- Khi quyết định quota có vấn đề (Redis timeout, config lỗi), **không tạo một QuotaDecision “allowed=false” như thể user đã hết quota**. Phân loại outage và áp fail policy, thông thường 503 khi hệ thống không thể xác định quyền gọi trong chế độ fail-closed.
- Nếu bật rate limit ở **gateway/filter trước controller**, phải dùng cùng error contract và bảo đảm 401/403, CORS preflight, service endpoints có cách xử lý hợp lý. Không cố áp annotation ở controller để thay thế gateway policy toàn hệ thống.

### 8.1. Spring Security và thứ tự ưu tiên

Một cấu hình route guard mẫu (fragment của `@Bean SecurityFilterChain`):

~~~java
http
    .authorizeHttpRequests(auth -> auth
        .requestMatchers(HttpMethod.GET, "/api/orders/**")
            .hasAuthority("SCOPE_orders.read")
        .anyRequest().denyAll())
    .oauth2ResourceServer(oauth2 ->
        oauth2.jwt(Customizer.withDefaults()));
~~~

Ở ứng dụng thực, quyết định quota tại gateway có thể diễn ra **trước** khi truy cập Spring Security. Vì vậy cần test thứ tự:

1. **No token** → theo policy xác thực, thường 401 với **WWW-Authenticate**.
2. **Wrong scope** → 403, không truy xuất đơn và không lộ quota tenant khác.
3. **Valid scope nhưng hết quota** → 429 + Retry-After.
4. **Valid scope/quota nhưng order ngoài quyền** → 403/404 theo object policy.

Nếu muốn hạn chế brute force vào login endpoint, quota theo IP/anonymous **trước** auth có thể có thứ tự khác; phải được document riêng. Với API browser, CORS preflight cần được cho qua đúng policy, không trừ quota tạo đơn hoặc bắt bearer token của actual POST.

### 8.2. WebFlux khác ở cách điều phối, không khác HTTP status

Trong WebFlux, quota service nên trả **Mono<QuotaDecision>** và dùng pipeline không chặn luồng. Tránh `block()` trên event loop. Một hướng xử lý:

~~~java
// Fragment trong handler reactive đã xác thực caller.
return quota.reserveReactive(caller, "orders.read", 1)
    .flatMap(decision -> decision.allowed()
        ? orders.listVisibleReactive(caller)
            .map(ResponseEntity::ok)
        : Mono.just(toTooManyRequests(decision)));
~~~

**toTooManyRequests** là hàm tạo response 429/Problem Details/Retry-After tương tự ví dụ Spring MVC; đoạn code là pseudocode Java có kiểu kết quả cần khớp trong ứng dụng thật. Không `retryWhen` một cách vô điều kiện trong server sau khi quota đã từ chối. Client mới là phía quyết định đợi và thử lại theo hợp đồng.

## 9. Java HttpClient: parse Retry-After đủ hai dạng

Client Java thường nhận **java.net.http.HttpResponse**, không nên phụ thuộc chuỗi lỗi của SDK để quyết định thời gian retry. Hàm dưới parse **đúng thời gian server yêu cầu**, còn tầng retry phải so với **ngân sách chờ** rồi dừng nếu không đủ; **không rút ngắn Retry-After để thử lại sớm**. Nó chỉ xử lý **IMF-fixdate** phổ biến qua `DateTimeFormatter.RFC_1123_DATE_TIME`; với HTTP-date legacy, production có thể cần parser HTTP-date chuyên dụng nếu hợp đồng đòi tương thích.

~~~java
import java.time.Clock;
import java.time.Duration;
import java.time.ZonedDateTime;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;
import java.math.BigInteger;
import java.util.Optional;

final class RetryAfterParser {
    private RetryAfterParser() {}

    static Optional<Duration> parse(
            String header, Clock clock) {
        if (header == null || header.isBlank() || clock == null) {
            return Optional.empty();
        }

        String value = header.trim();
        try {
            Duration delay;
            if (value.matches("[0-9]+")) {
                // Retry-After: 120 (integer seconds)
                // Giá trị rất lớn vẫn là "đợi rất lâu",
                // KHÔNG coi là malformed rồi retry sớm.
                BigInteger seconds = new BigInteger(value);
                long safeSeconds = seconds.min(
                    BigInteger.valueOf(Long.MAX_VALUE)).longValue();
                delay = Duration.ofSeconds(safeSeconds);
            } else {
                // Retry-After: Wed, 18 Nov 2026 10:00:45 GMT
                var instant = ZonedDateTime.parse(
                    value, DateTimeFormatter.RFC_1123_DATE_TIME
                ).toInstant();
                delay = Duration.between(clock.instant(), instant);
            }
            if (delay.isNegative()) delay = Duration.ZERO;
            return Optional.of(delay);
        } catch (NumberFormatException
                 | DateTimeParseException
                 | ArithmeticException invalid) {
            return Optional.empty();
        }
    }
}
~~~

**Tách Clock** giúp kiểm thử deterministic. Khi số giây vượt `Long.MAX_VALUE`, parser giữ ý nghĩa “đợi rất lâu” bằng duration cực lớn để tầng retry **dừng**, không diễn giải nó như header thiếu. Với header thiếu/sai, client chọn bounded backoff hoặc dừng theo policy. Khi giá trị hợp lệ vượt **retry budget/deadline**, **trả lỗi lên caller** chứ không cắt ngắn để gửi request sớm hơn.

### 9.1. Một client gửi GET có retry budget

Ví dụ luồng blocking Java HttpClient dưới đây chỉ retry **GET** khi nhận 429. Nó không tự động retry POST:

~~~java
import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Clock;
import java.time.Duration;
import java.util.concurrent.ThreadLocalRandom;
import java.util.concurrent.TimeUnit;

final class OrdersReadClient {
    private final HttpClient client;
    private final Clock clock;

    OrdersReadClient(HttpClient client, Clock clock) {
        this.client = client;
        this.clock = clock;
    }

    HttpResponse<String> getWithLimitRetry(
            URI uri, String bearerToken)
            throws IOException, InterruptedException {
        long deadline = System.nanoTime()
            + TimeUnit.SECONDS.toNanos(15);

        for (int attempt = 1; attempt <= 3; attempt++) {
            HttpRequest request = HttpRequest.newBuilder(uri)
                .timeout(Duration.ofSeconds(5))
                .header("Authorization", "Bearer " + bearerToken)
                .GET()
                .build();
            HttpResponse<String> response = client.send(
                request, HttpResponse.BodyHandlers.ofString());

            if (response.statusCode() != 429 || attempt == 3) {
                return response;
            }

            // Không parse RateLimit-* thay Retry-After nếu contract
            // chưa nói rõ đơn vị/reset của chúng.
            Duration wait = response.headers()
                .firstValue("Retry-After")
                .flatMap(raw -> RetryAfterParser.parse(
                    raw, clock))
                .orElse(Duration.ofMillis(
                    200L * attempt
                    + ThreadLocalRandom.current().nextLong(100L)));

            long remaining = deadline - System.nanoTime();
            // Valid Retry-After longer than the budget => stop, NOT
            // shorten the server's requested wait and retry early.
            if (remaining <= 0
                    || wait.compareTo(Duration.ofSeconds(10)) > 0
                    || wait.compareTo(Duration.ofNanos(remaining)) > 0) {
                return response; // Trả 429 cho caller quyết định.
            }
            Thread.sleep(wait.toMillis()); // Chỉ cho blocking thread.
        }
        throw new IllegalStateException("Unreachable");
    }
}
~~~

Đây là **ví dụ học tập**: một production HTTP client còn cần retry cho các lỗi network/503 theo hợp đồng, circuit breaker, connection pool, observability, giới hạn tổng request/byte và điều khiển concurrency theo caller. **Không log bearerToken** hoặc cho URI tùy ý từ người dùng để tránh SSRF. Lưu ý `HttpClient.send()` và `Thread.sleep()` là blocking, **không gọi trên event loop của Spring WebFlux**.

Với request **POST tạo đơn**, nếu timeout hoặc 429, client chỉ retry an toàn khi endpoint hỗ trợ idempotency và giữ **cùng Idempotency-Key cùng payload logic** giữa các attempts. Với response **202** hãy dùng operation status theo contract; với **409** do key-payload conflict không tự sinh key mới rồi thử lại.

## 10. OpenAPI: biến quota thành hợp đồng cho SDK

Một API không nên chỉ ghi “may return 429” trong mô tả tự do. Hãy ghi **mã trạng thái, response media type, headers và error schema**, kèm mô tả bên ngoài về quota partition, cost, reset, TTL và retry policy. Ví dụ **OpenAPI 3.1 rút gọn**:

~~~yaml
openapi: 3.1.0
info:
  title: Orders REST API
  version: 1.0.0
paths:
  /api/orders:
    get:
      operationId: listOrders
      security:
        - bearerAuth: []
      responses:
        '200':
          description: List of visible orders
        '401':
          description: Authentication required
        '403':
          description: Insufficient scope
        '429':
          description: Request quota exceeded for this caller
          headers:
            Retry-After:
              description: >
                RFC 9110 HTTP-date or nonnegative integer seconds.
                Subject to the client's deadline/retry budget.
              schema: {type: string}
            RateLimit:
              description: >
                Optional quota metadata in the selected IETF draft
                format when enabled by this API version.
              schema: {type: string}
          content:
            application/problem+json:
              schema:
                $ref: '#/components/schemas/ApiProblem'
        '503':
          description: Service temporarily unavailable
components:
  securitySchemes:
    bearerAuth: {type: http, scheme: bearer, bearerFormat: JWT}
  schemas:
    ApiProblem:
      type: object
      required: [type, title, status, code]
      properties:
        type: {type: string, format: uri-reference}
        title: {type: string}
        status: {type: integer}
        detail: {type: string}
        code: {type: string}
~~~

Đây là **fragment học tập**, chưa mô tả query parameters, response list schema, pagination hay mọi security scope. **Retry-After có thể thiếu** nếu server không dự đoán được thời điểm thử lại. Nếu dùng metadata kiểu `X-RateLimit-Reset`, hãy thay đúng header trong OpenAPI và nêu **epoch vs delta seconds**. API có thể chọn giữ một bản contract cũ để không phá SDK khi chuyển format metadata.

Trong Java/Spring, công cụ sinh OpenAPI từ annotation **không tự suy được** quota policy đặt tại gateway. Cần bổ sung các response 429/503 và headers vào OpenAPI từ nguồn cấu hình thống nhất, đồng thời chạy **contract test** để xác nhận gateway, Spring và đặc tả không mâu thuẫn.

## 11. Kiểm thử quota và Retry-After theo nhiều tầng

### 11.1. JUnit kiểm parser không phụ thuộc đồng hồ thật

~~~java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.Optional;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;

class RetryAfterParserTest {
    private final Clock clock = Clock.fixed(
        Instant.parse("2026-11-18T10:00:00Z"),
        ZoneOffset.UTC);

    @Test
    void acceptsSecondsAndHttpDate() {
        assertEquals(Optional.of(Duration.ofSeconds(12)),
            RetryAfterParser.parse("12", clock));

        assertEquals(Optional.of(Duration.ofSeconds(45)),
            RetryAfterParser.parse(
                "Wed, 18 Nov 2026 10:00:45 GMT", clock));
    }

    @Test
    void preservesLongDelayAndIgnoresInvalid() {
        // Caller stops retrying when this exceeds its wait budget.
        assertEquals(Optional.of(Duration.ofSeconds(9999)),
            RetryAfterParser.parse("9999", clock));
        assertEquals(Optional.of(Duration.ofSeconds(Long.MAX_VALUE)),
            RetryAfterParser.parse(
                "999999999999999999999999999", clock));
        assertEquals(Optional.empty(),
            RetryAfterParser.parse("-1", clock));
        assertEquals(Optional.empty(),
            RetryAfterParser.parse("20ms", clock));
    }
}
~~~

Kiểm thêm header rỗng, số quá lớn, ngày đã qua, giờ client lệch nhiều và nhánh client **không retry** khi Retry-After vượt deadline. Không dùng `Thread.sleep` trong unit test parser; test scheduler/retry với **fake clock hoặc virtual time** khi dùng Reactor.

### 11.2. MockMvc: từ chối trước khi gọi business service

Fragment này dựa vào OrdersController và các interface ở mục 8, với MockMvc/Mockito/JWT Spring Security Test đã cấu hình:

~~~java
when(quota.checkAndReserve(
        new Caller("buyer-17", "tenant-A"), "orders.read", 1))
    .thenReturn(new QuotaDecision(
        false, 0, Duration.ofSeconds(7)));

mockMvc.perform(get("/api/orders")
        .with(jwt()
            .jwt(j -> j.subject("buyer-17")
                .claim("tenant_id", "tenant-A"))
            .authorities(new SimpleGrantedAuthority(
                "SCOPE_orders.read"))))
    .andExpect(status().isTooManyRequests())
    .andExpect(header().string("Retry-After", "7"))
    .andExpect(content().contentTypeCompatibleWith(
        MediaType.APPLICATION_PROBLEM_JSON))
    .andExpect(jsonPath("$.code").value("RATE_LIMITED"));

verifyNoInteractions(orders);
~~~

Cần bổ sung imports và fixtures vào test class thực; một test `@WebMvcTest` có thể cần import SecurityFilterChain, method security và các mock beans phù hợp. **jwt()** của Spring Security Test không chứng minh chữ ký/issuer/audience được JwtDecoder thật xác minh. Test 401/403 và object-level authorization bằng security integration test riêng.

### 11.3. Kiểm thử concurrency, cửa sổ quota và request thật

| Ca kiểm thử | Điều phải chứng minh |
|---|---|
| 100 request đồng thời, quota chỉ cho 40 | **Không vượt 40 allowed** trong scope đã định; không chỉ test tuần tự |
| 3 pod cùng chia quota tenant | Không cho phép 3 lần số request vì counter cục bộ |
| Fixed window ở mốc giây cuối/đầu | Phù hợp thuật toán đã công bố, không sai do clock skew |
| Token bucket có burst và cost=3 | Retry-After tính đủ số tokens theo cost |
| User A và B cùng tenant | Có đúng quota tenant chung và quota user riêng nếu contract công bố |
| Khác tenant dùng cùng API key string sai cấu hình | Không lẫn/cấp quyền chéo tenant; identity phải đã xác minh |
| Hết quota trước khi query DB | Không gọi business service; phản hồi 429 ổn định |
| Redis/quota service chết | Fail policy được kiểm, không trả 429 giả hoặc allow vô hạn |
| Client gặp 429 rồi 200 | Retry đúng số lần/chờ, giữ auth/trace, không storm |
| POST sau mất response | Giữ cùng Idempotency-Key, chỉ một business effect |
| Metadata draft và custom headers | Parse đúng tên/đơn vị; không coi remaining như bảo đảm |
| Browser gọi API cross-origin | JS đọc được Retry-After qua expose headers nếu origin được allow |

Với Redis, database hoặc gateway thực, ưu tiên **integration/fault-injection tests** (có thể dùng Testcontainers hoặc môi trường staging) thay vì mock một counter luôn trả đúng. Với **WireMock/MockWebServer**, cho client thấy response 429 với Retry-After, sau đó 200, rồi assert request count, deadline và số lần retry. Không cần chờ vài phút trong unit tests; dùng scheduler/fake clock khi có thể.

**Đối chiếu client/backend:** nếu response 429 đến từ CDN trước API Spring, test MockMvc sẽ không nhìn thấy giới hạn của CDN. Phải có **end-to-end test qua tuyến truy cập production-like**, kiểm các headers sau proxy và việc auth/CORS/error schema còn nguyên.

## 12. Bài tập thực hành và đáp án

**Bài 1 — Phân biệt trạng thái.** GET /api/orders với JWT hợp lệ nhưng vượt quota tenant; lần khác toàn cụm database đang bảo trì. Trả mã nào? **Đáp án:** Trường hợp đầu thường **429**, trường hợp sau thường **503**, có thể kèm Retry-After phù hợp; không dùng 403 cho hết quota.

**Bài 2 — Đơn vị thời gian.** Server trả `Retry-After: 90`; client đợi 90 **milliseconds**. Sai ở đâu? **Đáp án:** Delay-seconds là **giây**, phải chờ khoảng 90 giây nhưng vẫn tôn trọng max deadline/retry policy.

**Bài 3 — Header Reset.** API A dùng `X-RateLimit-Reset` theo **Unix epoch seconds**, API B dùng **số giây đến reset**. SDK dùng một parser cho cả hai có ổn không? **Đáp án:** Không. Đây là contract provider-specific; cần adapter riêng, unit rõ, test giá trị ranh giới và clock skew.

**Bài 4 — Nhiều policy.** User còn 10 requests/minute nhưng đã hết 2 requests/second. Vì sao vẫn có thể nhận 429? **Đáp án:** Cả hai quota áp dụng đồng thời; remaining ở policy phút không bảo đảm policy giây còn chỗ. Chỉ Retry-After/policy của bottleneck theo contract mới giúp lập lịch hợp lý.

**Bài 5 — POST tạo đơn sau timeout.** Java client gửi POST với `Idempotency-Key: A` rồi mạng timeout sau khi server có thể đã commit. User bấm lại, SDK tạo key B. **Đáp án:** Nguy cơ tạo đơn trùng. Nếu API hỗ trợ, giữ key A, body logic cũ và inquiry/reconciliation; không mặc định retry mọi POST.

**Bài 6 — Tenant fairness.** Gateway giới hạn 100/min/IP, 50 người dùng doanh nghiệp cùng NAT đều bị 429 dù chỉ gửi 3 request/người. **Đáp án:** IP limiter đơn lẻ gây bất công; thêm quota theo principal/tenant/API key đã xác minh, giữ lớp chống abuse IP có chính sách riêng.

**Bài 7 — CORS.** Browser nhận 429 kèm Retry-After, nhưng `response.headers.get("Retry-After")` trả null trong JavaScript. **Đáp án:** Kiểm CORS và `Access-Control-Expose-Headers: Retry-After`, origin allowlist và credentials. Native curl đọc được header không chứng minh browser đọc được.

**Bài 8 — Kiểm thử concurrency.** Test MockMvc 10 lần tuần tự đều nhận đúng 429 sau request thứ 5. Đã chứng minh quota 5 request chạy trên 3 pods không bị vượt chưa? **Đáp án:** Chưa. Cần đồng thời nhiều clients/pods dùng quota store thật, kiểm atomic reservation, reset, race và hành vi Redis outage.

## 13. Checklist triển khai và kết luận

- [ ] 429, 503, 401/403/409/412 được phân biệt theo ngữ nghĩa HTTP?
- [ ] Retry-After hỗ trợ **delay-seconds hoặc HTTP-date**; client không retry sớm khi thời gian chờ vượt deadline?
- [ ] Quota scope/units/window/cost/burst/TTL và algorithm được công bố đúng?
- [ ] Các headers RateLimit hay X-RateLimit được **pin cú pháp và đơn vị theo contract**, không suy đoán?
- [ ] Có **atomic quota store** qua nhiều replicas, hành vi mất store/clock skew được thiết kế?
- [ ] Auth/tenant/ACL được xác minh; không tin X-Forwarded-For hay tenant từ client tùy ý?
- [ ] Problem Details có mã máy đọc được, không lộ Redis key, token, PII hoặc quotas người khác?
- [ ] Cache-Control, proxy, CORS exposed headers và error responses được kiểm thử?
- [ ] Client retry có **backoff + jitter, deadline**, tôn trọng Retry-After nhưng không retry vô hạn?
- [ ] POST có side effect dùng **idempotency contract** hoặc operation status, không retry mù?
- [ ] OpenAPI, gateway/Spring policy và bộ test contract nhất quán?
- [ ] Có concurrency tests, fault injection, metrics 429/503 và cảnh báo quota-store outage?

**Kết luận:** **429 Too Many Requests** diễn đạt việc API áp dụng hạn mức; **Retry-After** hướng dẫn thời gian chờ bằng giây hoặc HTTP-date; **metadata quota** chỉ có giá trị khi client hiểu chính xác cú pháp, đơn vị và chính sách theo hợp đồng. Một hệ thống REST bền vững cần quota phân vùng đúng, thao tác tính hạn mức nguyên tử, response HTTP rõ ràng, client retry có ngân sách, và **idempotency/phân quyền/kiểm thử tải** để hạn chế lỗi lan truyền thay vì khuếch đại chúng.
