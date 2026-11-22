# Phân biệt lỗi 4xx dự kiến với lỗi ảnh hưởng chất lượng dịch vụ

## 1. Vì sao “tỷ lệ lỗi HTTP” có thể khiến đội vận hành hiểu sai?

Một REST API nhận ba loại request:

1. Khách hàng gọi `GET /api/orders/not-exist` với một ID không tồn tại. API xác thực thành công, truy vấn đúng và trả **404 Not Found** theo hợp đồng.
2. Người dùng gửi `PATCH /api/orders/101` với ETag cũ, trong lúc đơn đã bị cập nhật bởi request khác. API chặn ghi đè và trả **412 Precondition Failed** đúng quy tắc concurrency.
3. Nhiều người dùng đang có phiên hợp lệ gọi `GET /api/orders`, nhưng database connection pool cạn; API trả **503 Service Unavailable** hoặc timeout.

Nếu dashboard chỉ tô đỏ toàn bộ response từ **400 trở lên**, nhóm vận hành có thể bị đánh thức vì những lần 404/412 hoàn toàn hợp lệ. Nhưng nếu hệ thống gạt **mọi 4xx** khỏi chỉ số chất lượng, sẽ bỏ qua sự cố thực tế: một deploy sai scope khiến tất cả người dùng nhận 403, một cấu hình quota nhầm khiến 429 tăng đột biến, hoặc một router mới trả 404 cho endpoint vốn hoạt động hôm qua.

**HTTP status mô tả kết quả của một request. Chất lượng dịch vụ phải được đánh giá bằng việc hệ thống có thực hiện đúng hợp đồng đối với lưu lượng hợp lệ và trải nghiệm người dùng hay không.** Hai lớp thông tin này liên quan chặt chẽ nhưng không trùng khít.

Trong module **INTEGRATION_API_REST**, người học đã thiết kế resource/URI, phương thức HTTP, hợp đồng lỗi, phân trang, cache, idempotency, OpenAPI, authentication và authorization. Bài này biến chính những hợp đồng đó thành **tín hiệu quan sát** để phân biệt yêu cầu bị từ chối đúng đắn với lỗi ảnh hưởng availability, latency, correctness và tiến trình nghiệp vụ.

### Mục tiêu học tập

Sau bài này, người học có thể:

- Phân loại 400/401/403/404/409/412/422/429, 5xx và timeout dựa trên **nguồn gốc, tính dự kiến và tác động**, thay vì chỉ dựa vào chữ số đầu.
- Thiết kế taxonomy mã lỗi ổn định với `application/problem+json`, logging có cấu trúc và correlation ID.
- Xác định **SLI/SLO/error budget** với tập request đủ điều kiện, tiêu chí “good event” rõ ràng và chỉ số chất lượng nghiệp vụ.
- Triển khai quan sát HTTP trong Java/Spring Boot bằng Actuator, Micrometer, tracing và metric nghiệp vụ có cardinality kiểm soát.
- Xây dashboard, cảnh báo, runbook và kiểm thử phát hiện 4xx do hồi quy hoặc 5xx bị che trong phản hồi 2xx.
- Bảo vệ token, thông tin cá nhân và tenant khi thu thập dữ liệu quan sát.

## 2. HTTP 4xx thường là từ chối đúng, nhưng không phải lúc nào cũng vô hại

### 2.1. Ma trận phân loại ban đầu

| HTTP | Tình huống 4xx **dự kiến** | Khi nào có thể là sự cố chất lượng |
|---|---|---|
| **400 Bad Request** | JSON sai cú pháp, tham số thiếu, định dạng không hợp lệ | SDK vừa phát hành tạo payload sai cho phần lớn người dùng; API đổi schema không tương thích |
| **401 Unauthorized** | Thiếu access token, token hết hạn hoặc sai chữ ký/audience | Cấu hình JWKS/issuer sai sau deploy khiến mọi token hợp lệ bị từ chối; backend định danh bị lỗi được ánh xạ nhầm thành 401 |
| **403 Forbidden** | Principal hợp lệ nhưng thiếu scope hoặc quyền đối tượng | Chính sách phân quyền mới vô tình cấm mọi chủ sở hữu hợp lệ; role/tenant mapping sai |
| **404 Not Found** | Resource thật sự không tồn tại hoặc được che giấu vì BOLA | Router/proxy đổi prefix khiến endpoint hợp lệ đồng loạt trả 404; dữ liệu bị mất hoặc ánh xạ tenant sai |
| **405 Method Not Allowed** | Client gọi phương thức không được API hỗ trợ | Bản phát hành thay route/method trái OpenAPI contract |
| **408 Request Timeout** | Server không nhận đủ request từ client đúng hạn | Lỗi kết nối, áp lực mạng hoặc hành vi proxy gây timeout hàng loạt |
| **409 Conflict** | Cùng `Idempotency-Key` nhưng payload khác; trạng thái đơn không cho thao tác | Race trong DB/service khiến request hợp lệ bị conflict hàng loạt |
| **412 Precondition Failed** | `If-Match`/ETag cũ khi cập nhật đồng thời | Client/edge giữ ETag sai hoặc triển khai ETag thay đổi bất thường |
| **413 Content Too Large** | Upload vượt kích thước đã công bố | Gateway hạ ngưỡng đột ngột khiến upload hợp lệ bị chặn |
| **422 Unprocessable Content** | JSON hợp lệ nhưng không đạt semantic validation theo contract | Luật validation triển khai sai, chặn dữ liệu nghiệp vụ hợp lệ |
| **429 Too Many Requests** | Một API key/tenant vượt quota đã công bố | Quota key bị gộp sai, limiter lỗi hoặc ngưỡng bị giảm khiến người dùng hợp lệ bị 429 |
| **499 (không chuẩn HTTP)** | Một số proxy như NGINX dùng để ghi nhận client đóng kết nối | Người dùng hủy do server chậm; phải điều tra latency và timeout trước khi xem là “lỗi của client” |

Bảng là **điểm khởi đầu để đặt câu hỏi**, không phải quy tắc phân loại tự động bất biến. Một 404 do URI sai của bot có thể không ảnh hưởng sản phẩm; cùng 404 trên endpoint checkout sau deploy có thể là outage. 401 hoặc 403 có thể là kiểm soát bảo mật đã hoạt động đúng; nhưng tăng đột biến trên lưu lượng chính đáng vẫn có thể là sự cố.

### 2.2. Không gộp 429 với 503

**429 Too Many Requests** thường nói rằng một caller/khóa quota đã vượt chính sách sử dụng. Server có thể vẫn phục vụ tốt các consumer khác. **503 Service Unavailable** nói rằng service tạm không thể xử lý do overload hoặc maintenance; kể cả caller chưa vượt quota vẫn bị ảnh hưởng.

~~~http
HTTP/1.1 429 Too Many Requests
Content-Type: application/problem+json
Retry-After: 30
Cache-Control: no-store

{
  "type": "https://api.example.test/problems/rate-limit",
  "title": "Too Many Requests",
  "status": 429,
  "code": "CLIENT_RATE_LIMITED"
}
~~~

~~~http
HTTP/1.1 503 Service Unavailable
Content-Type: application/problem+json
Cache-Control: no-store

{
  "type": "https://api.example.test/problems/unavailable",
  "title": "Service Unavailable",
  "status": 503,
  "code": "SERVICE_OVERLOADED"
}
~~~

Cả hai **có thể** có `Retry-After`, nhưng không nên tự bịa thời gian khôi phục cho 503 chưa biết khi nào phục hồi. Không dùng 429 để che việc Redis quota store hỏng nếu không có bằng chứng caller vượt quota. Đối với 429 đúng hợp đồng, client cần throttle theo quota key; đối với 503, client cần backoff+jitter, retry budget và có thể degrade/failover khi an toàn.

Một 429 tăng cao **không tự động** là SLO violation: chiến dịch tải kiểm thử vượt quota có thể hoạt động đúng. Nhưng một 429 phát cho các request nằm dưới giới hạn đã công bố là sự cố trải nghiệm dù status vẫn thuộc nhóm 4xx. Metric 429 và điều tra theo policy/consumer cohort cần được giữ độc lập với 503.

### 2.3. 5xx thường là tín hiệu server, nhưng cũng cần bối cảnh

| HTTP / tín hiệu | Ý nghĩa chính | Ví dụ ảnh hưởng chất lượng |
|---|---|---|
| **500 Internal Server Error** | Lỗi ngoài dự kiến ở ứng dụng | Null pointer, transaction lỗi, bug mapping |
| **502 Bad Gateway** | Gateway nhận response không hợp lệ từ upstream | Kết nối upstream bị đóng, protocol sai |
| **503 Service Unavailable** | Service tạm không đáp ứng | DB pool cạn, overload, maintenance không có capacity thay thế |
| **504 Gateway Timeout** | Gateway không nhận phản hồi kịp thời | Downstream quá chậm, timeout budget sai |
| **Lỗi transport không có status** | Không nhận được HTTP response | TCP reset, TLS handshake fail, network timeout |
| **2xx nhưng kết quả sai** | HTTP báo thành công nhưng contract nghiệp vụ bị vi phạm | Trả nhầm tenant, 200 chứa dữ liệu cũ, 202 nhưng job không bao giờ xong |

Đừng xem mọi 5xx là cùng một nguyên nhân hoặc đếm 502 ở CDN cùng một lần 500 ở service như **hai request độc lập** trong cùng SLI. Phải biết tầng nào quan sát request và denominator đến từ đâu. Một số lỗi HTTP không tới ứng dụng (gateway từ chối trước hoặc mạng thất bại), nên chỉ dùng metric `http.server.requests` từ Spring sẽ bỏ sót sự cố người dùng thực sự gặp.

## 3. Bốn chiều để phân loại sự kiện lỗi

Nên phân tách bốn chiều, thay vì lưu mỗi `status=404`:

| Chiều | Câu hỏi | Giá trị gợi ý |
|---|---|---|
| **HTTP outcome** | API trả gì? | `2xx`, `4xx`, `5xx`, `transport_error` |
| **Nguyên nhân** | Quy tắc hoặc component nào tạo kết quả? | `VALIDATION`, `AUTHENTICATION`, `POLICY_DENY`, `CLIENT_QUOTA`, `DEPENDENCY`, `OVERLOAD`, `BUG` |
| **Kỳ vọng theo hợp đồng** | Với request này, từ chối có phải hành vi đúng? | `EXPECTED_REJECTION`, `UNEXPECTED`, `UNKNOWN` |
| **Tác động chất lượng** | Người dùng hợp lệ có bị mất chức năng, sai kết quả hoặc quá chậm? | `GOOD`, `IMPACTING`, `NEEDS_REVIEW` |

**Expected rejection** là phản hồi API bảo vệ đúng hợp đồng: dữ liệu sai, quyền thiếu, resource không tồn tại, ETag không khớp. Nó không nhất thiết là “thành công nghiệp vụ” từ phía người dùng, nhưng **không phải lỗi availability của server** nếu API đã đáp ứng đúng và đúng hạn.

**Impacting failure** là khi người dùng gửi request hợp lệ mà service không thực hiện được cam kết: 5xx, timeout, 4xx do cấu hình sai, dữ liệu không đúng tenant, hoặc 202 đã nhận công việc nhưng xử lý bị treo. **NEEDS_REVIEW** dành cho trường hợp chưa đủ thông tin; không mặc nhiên gán mọi code 4xx là expected.

### 3.1. Các trường hợp đối chiếu

| Request | Phản hồi | Kết luận quan sát |
|---|---|---|
| `GET /orders/123`, ID không tồn tại | 404 | Expected rejection nếu contract che giấu/không tồn tại |
| `GET /orders/123`, order có tồn tại và chủ sở hữu có quyền, nhưng route bị sai sau deploy | 404 | Impacting failure vì hợp đồng bị vi phạm |
| `POST /orders` thiếu `cartId` bắt buộc | 400 | Expected rejection |
| `POST /orders` từ phiên hợp lệ, SDK mới bỏ nhầm `cartId` | 400 | API validation đúng, nhưng **chất lượng sản phẩm/tích hợp** bị ảnh hưởng; phải cảnh báo spike |
| `PATCH /orders/123` với ETag cũ | 412 | Expected concurrency rejection |
| `GET /orders` nhận 401 khi user thật sự hết hạn token | 401 | Expected authentication rejection |
| `GET /orders` nhận 401 vì JWKS cache sai sau key rotation | 401 | Impacting failure / auth incident |
| Tenant A vượt quota 100 req/min đã công bố | 429 | Expected quota enforcement |
| Mọi tenant đột ngột nhận 429 vì khóa quota bị gộp | 429 | Impacting failure |
| Gateway timeout trong lúc provider đã xử lý POST | 504 hoặc transport timeout | Impacting; kết quả nghiệp vụ có thể UNKNOWN, phải đối soát |
| API trả 200 với danh sách thuộc tenant khác | 200 | **Sự cố bảo mật/correctness nghiêm trọng**, không được coi là GOOD |

Không yêu cầu service phải suy đoán “ý định thật” của user từ mỗi request. Hãy định nghĩa **rule theo route + phương thức + error code + policy outcome**, rồi dùng tín hiệu về release, tỷ lệ người dùng chịu ảnh hưởng và hành vi client để phát hiện hồi quy. Phân loại động để điều tra không nên âm thầm thay đổi định nghĩa SLI đã cam kết sau sự cố.

### 3.2. Phân biệt nguồn phát lỗi

Một request có thể đi qua:

~~~mermaid
flowchart LR
    B[Browser hoặc Java client] --> C[CDN/WAF]
    C --> G[API Gateway]
    G --> S[Spring REST API]
    S --> D[(PostgreSQL)]
    S --> P[Payment/Inventory API]

    C -. 4xx / 5xx .-> O[Quan sát tại edge]
    G -. 401 / 429 / 502 / 504 .-> O
    S -. 4xx / 5xx / 2xx .-> M[Quan sát ứng dụng]
    D -. timeout / error .-> M
    P -. timeout / 5xx .-> M
~~~

Nếu gateway trả 504 vì Orders API không phản hồi, Spring có thể chưa ghi được request hoàn chỉnh hoặc trả 200 **sau khi** gateway đã timeout. Khi xem chất lượng cho người dùng, cần metric tại edge/gateway hoặc synthetic client. Khi tìm nguyên nhân, dùng telemetry theo hop với trace/correlation ID; tránh cộng tất cả metric ở các tầng rồi tuyên bố có nhiều request lỗi hơn thực tế.

## 4. Thiết kế mã lỗi ứng dụng ổn định

HTTP status giúp client hiểu lớp hành vi; **mã lỗi máy đọc được** giúp biết rule cụ thể mà không phải parse câu chữ. Có thể dùng `application/problem+json` theo RFC 9457:

~~~http
HTTP/1.1 409 Conflict
Content-Type: application/problem+json
Cache-Control: no-store
X-Request-Id: req-7b21

{
  "type": "https://api.example.test/problems/order-version-conflict",
  "title": "Conflict",
  "status": 409,
  "detail": "Đơn hàng đã được cập nhật; vui lòng tải lại trước khi sửa.",
  "code": "ORDER_VERSION_CONFLICT",
  "requestId": "req-7b21"
}
~~~

`code` và `requestId` là extension do API định nghĩa, không phải thành phần bắt buộc của RFC. `status` trong body phải nhất quán với HTTP status. `detail` có thể được dịch cho người dùng; **không sử dụng câu `detail` làm khóa phân loại metric**. `type` nên ổn định và có tài liệu hành vi. Ví dụ bộ code:

| Code | HTTP | Nhóm | Hành vi client |
|---|---|---|---|
| `INVALID_REQUEST` | 400 | Validation dự kiến | Sửa request |
| `TOKEN_INVALID` | 401 | Authentication | Lấy/refresh token có kiểm soát |
| `FORBIDDEN` | 403 | Policy denial | Không retry nguyên trạng |
| `ORDER_NOT_FOUND` | 404 | Resource access | Dừng hoặc kiểm lại ID |
| `ORDER_VERSION_CONFLICT` | 412 | Concurrency | GET lại representation/ETag, yêu cầu xác nhận nếu cần |
| `IDEMPOTENCY_KEY_CONFLICT` | 409 | Command conflict | Không đổi payload rồi retry cùng key |
| `CLIENT_RATE_LIMITED` | 429 | Quota | Đợi `Retry-After`, throttle |
| `DEPENDENCY_UNAVAILABLE` | 503 | Service health | Retry an toàn với backoff, theo deadline |
| `INTERNAL_ERROR` | 500 | Không xác định | Báo support kèm request ID, không lộ stack trace |

**Không ánh xạ bừa tất cả `DataIntegrityViolationException` thành 409.** Chỉ map conflict khi biết đúng constraint nghiệp vụ (ví dụ unique idempotency key) và xử lý transaction boundary an toàn. FK hỏng do bug hoặc schema mismatch là lỗi server cần điều tra. Tương tự, không bắt mọi `RuntimeException` rồi trả 400 để giữ dashboard “xanh”.

### 4.1. Bảng phân loại lỗi để dùng chung

Có thể định nghĩa một bảng cấu hình/enum được review cùng OpenAPI:

~~~text
status | app_code                  | class                  | owner
400    | INVALID_REQUEST           | EXPECTED_REJECTION     | api-client
401    | TOKEN_INVALID             | EXPECTED_REJECTION     | auth
403    | FORBIDDEN                 | EXPECTED_REJECTION     | authorization
404    | ORDER_NOT_FOUND           | EXPECTED_REJECTION     | resource
409    | IDEMPOTENCY_KEY_CONFLICT  | EXPECTED_REJECTION     | command
412    | ORDER_VERSION_CONFLICT    | EXPECTED_REJECTION     | concurrency
429    | CLIENT_RATE_LIMITED       | EXPECTED_REJECTION*    | quota
500    | INTERNAL_ERROR            | IMPACTING              | application
503    | DEPENDENCY_UNAVAILABLE    | IMPACTING              | infrastructure

* 429 được xem là expected khi chính sách quota thực thi đúng.
  Phát hiện quota cấu hình sai cần tín hiệu và cảnh báo riêng.
~~~

Bảng thể hiện **mặc định cho từng error code**, không thay thế giám sát hồi quy. Mọi 4xx chưa được tài liệu hóa/không biết nguồn phải vào `NEEDS_REVIEW` hoặc nhóm phân tích riêng, không cho phép “unknown 4xx = good” vô điều kiện. Khi đổi error code hoặc policy, cập nhật hợp đồng, dashboard và test cùng nhau.

## 5. SLI, SLO và error budget: chọn “good event” trước khi tính tỷ lệ

**SLI (Service Level Indicator)** là phép đo trải nghiệm/chất lượng thực tế. **SLO (Service Level Objective)** là mục tiêu cho SLI trong một khoảng thời gian. **Error budget** là mức độ không đáp ứng được phép trước khi vượt mục tiêu. Không nên bắt đầu bằng biểu đồ “tổng 4xx + 5xx” rồi gọi đó là availability SLI.

### 5.1. Availability SLI theo hợp đồng

Một định nghĩa khả thi cho REST API:

\[
\text{Availability SLI} =
\frac{\text{Số request đủ điều kiện được xử lý đúng hợp đồng}}
{\text{Tổng request đủ điều kiện}}.
\]

Định nghĩa *request đủ điều kiện* phải được viết **trước sự cố** và dựa trên route/client/loại traffic đã công bố. Ví dụ: các request sản phẩm tới `/api/orders/**` tại public gateway; loại health probes nội bộ, load tests đã nhận diện, bot không nằm trong hợp đồng và các request do hệ thống giám sát tạo ra. Không được loại mọi 5xx hoặc mọi request chậm khỏi mẫu số, vì như vậy làm đẹp SLI giả tạo.

Định nghĩa “xử lý đúng hợp đồng” có thể gồm:

- **2xx/3xx thích hợp** với dữ liệu đúng, latency trong phạm vi và quyền tài nguyên được đảm bảo.
- **4xx dự kiến** do request không hợp lệ, không có quyền, ETag cũ hoặc vượt quota **đúng chính sách**, khi API phản hồi đúng và trong thời gian cam kết.
- **Không gồm** 5xx, lỗi transport/timeout ở biên người dùng, phản hồi bất ngờ, 4xx do hồi quy và 2xx sai dữ liệu.

Không phải mọi SLI đều cần tính expected 4xx vào good events. Một SLI khác chỉ đánh giá **request hợp lệ đã qua admission/authentication** có thể đặt tập đủ điều kiện hẹp hơn. Điều quan trọng là định nghĩa minh bạch, nhất quán và không thay tiêu chí theo hướng thuận lợi sau khi có sự cố.

### 5.2. Ví dụ số học

Giả sử có **10.000 request sản phẩm đủ điều kiện** trong một cửa sổ quan sát, được phân loại theo chính sách đã công bố:

| Nhóm | Số request | Được tính tốt cho availability? |
|---|---:|---|
| 2xx đúng hợp đồng và đúng hạn | 9.100 | Có |
| 4xx dự kiến, trả đúng rule và đúng hạn | 700 | Có |
| 5xx và transport timeout | 150 | Không |
| 4xx do lỗi route/quota/security policy | 50 | Không |
| **Tổng** | **10.000** | |

Số good events là **9.800**, số impacting là **200**; availability SLI = **98%**. Nếu dashboard chỉ lấy `1 - 5xx_rate`, kết quả có thể lạc quan vì bỏ qua 50 trường hợp 4xx tác động thật. Nếu dashboard coi tất cả 700 expected 4xx là failure, lại bi quan không phản ánh đúng server.

Giả sử SLO **99,9%** trên 100.000 request đủ điều kiện, ngân sách tương đương **100 bad events** trong cửa sổ đó. Đây là minh họa tính theo số request; trong thực tế cần xác định cửa sổ thời gian, cách xử lý traffic thấp, latency, business operation và quy tắc cửa sổ rolling.

### 5.3. Không chỉ đo availability

| SLI | Đơn vị | 4xx liên quan thế nào? |
|---|---|---|
| **Availability** | Tỷ lệ request được đáp ứng đúng contract | Expected 4xx có thể good; unexpected 4xx là bad |
| **Latency** | Tỷ lệ request dưới ngưỡng, ví dụ GET order nhanh hơn ngưỡng SLO | Expected 404 quá chậm vẫn có thể vi phạm latency |
| **Correctness** | Tỷ lệ kết quả đúng tenant, giá, trạng thái và nghiệp vụ | 200 sai JSON/dữ liệu là bad; không thể suy từ status |
| **Async completion** | Tỷ lệ operation `202 Accepted` kết thúc trong SLA | 202 không tự tương đương SUCCEEDED |
| **Freshness** | Tuổi dữ liệu trong cache/projection | 200 với dữ liệu quá cũ có thể là lỗi chất lượng |
| **Security policy** | Tỷ lệ quyết định kiểm soát quyền đúng | 403 chặn truy cập trái phép là tốt; 200 lộ tenant là sự cố |
| **Client integration health** | Tỷ lệ 400/401/403/404/409 theo SDK/version/cohort | Spike có thể là lỗi tích hợp dù server trả status đúng |

Đối với một REST API vận hành được, cần kết hợp **technical SLI** (availability/latency) với **business SLI** (đơn hàng hoàn thành, không trùng payment, không lộ tenant). Không thể chỉ dựa vào response 200 hoặc số lượng request để kết luận hệ thống khỏe.

### 5.4. Cửa sổ và error budget burn

**Burn rate** đo tốc độ tiêu thụ error budget so với tốc độ được phép của SLO. Ví dụ SLO 99,9% cho phép tỷ lệ bad events 0,1%. Nếu cửa sổ ngắn có tỷ lệ bad events 1%, đó là mức burn khoảng **10 lần** tỷ lệ cho phép. Trong vận hành, cảnh báo đa cửa sổ (ngắn để bắt sự cố nhanh, dài để tránh nhiễu) thường hữu ích hơn một ngưỡng “5xx lớn hơn 1 lần”. Với route ít request, tỷ lệ có thể biến động mạnh: cần ngưỡng số lượng tối thiểu, mức độ quan trọng và synthetic check để giảm báo động giả.

Định nghĩa alert nên có **người chịu trách nhiệm và hướng xử lý**. Nếu không ai biết phải làm gì khi 404 tăng, một cảnh báo 404 ngưỡng cố định có thể tạo quá nhiều tiếng ồn. Nhưng một tăng đột biến 404 ở route `/api/checkout` ngay sau deploy cần được điều tra nhanh.

## 6. Phân lớp telemetry: metrics, logs và traces

### 6.1. Metrics trả lời “bao nhiêu, ở đâu, xu hướng thế nào?”

Các phép đo quan trọng (theo route template và method):

| Nhóm | Metric/đặc trưng | Câu hỏi |
|---|---|---|
| Traffic | requests/sec, concurrent requests, active connections | Lưu lượng có đổi bất thường? |
| HTTP status | count/rate theo `status`, `method`, `uri` | 401/403/404/429/5xx đang tăng ở endpoint nào? |
| Latency | duration histogram và p50/p95/p99 | Người dùng có chờ lâu trước khi lỗi? |
| Quality classification | bad/good/expected/needs-review theo rule **cố định** | Lỗi có ảnh hưởng hợp đồng? |
| Dependency | DB pool usage, queue depth, outbound timeout, upstream 5xx | Nguồn gốc 503/504 là gì? |
| Rate limiting | `CLIENT_RATE_LIMITED` theo policy/plan/route | Có client vượt quota hay cấu hình bị sai? |
| Authentication/authorization | invalid JWT, forbidden theo loại rule | Có deployment sai issuer/JWKS hoặc policy? |
| Business workflow | `operations_pending`, `reconciliation_age`, duplicate attempts | 202 có hoàn tất đúng thời gian? |
| Cache | hit/miss, stale/eviction, cache errors | API trả dữ liệu cũ hoặc rò tenant không? |

Không gắn `userId`, raw `orderId`, `access_token`, URI động `/orders/123` hay payload JSON vào label metric: chúng tạo **high cardinality**, tăng chi phí và có thể lộ dữ liệu. Dùng `uri="/api/orders/{id}"`, `status="404"`, `error_code="ORDER_NOT_FOUND"`, `policy="tenant-owner-read"` từ tập giá trị được kiểm soát. Thông tin chi tiết của một giao dịch thuộc **trace/log có phân quyền**, không phải label của time series.

### 6.2. Logs trả lời “điều gì đã xảy ra?”

Một bản ghi cấu trúc có thể gồm:

~~~json
{
  "timestamp": "2026-11-18T10:15:00Z",
  "severity": "INFO",
  "service": "orders-api",
  "environment": "production",
  "route": "/api/orders/{id}",
  "method": "GET",
  "status": 404,
  "error_code": "ORDER_NOT_FOUND",
  "error_class": "EXPECTED_REJECTION",
  "latency_ms": 12,
  "trace_id": "e829db1b7a4e4b37ad94c2ab8dd92b93",
  "request_id": "req-47a1"
}
~~~

Expected 400/404 có thể ghi `INFO` hoặc theo sampling, **không cần stack trace `ERROR` cho từng request sai**. Lỗi server không mong đợi nên có log `ERROR`, exception chain và trace ID, nhưng tránh nhân đôi log ở controller, service, exception handler và gateway cho cùng một vấn đề. Lựa chọn log level phụ thuộc mức độ đe dọa/bảo mật: nhiều 401 sai token có thể là brute-force cần security event/alert, dù từng response 401 là expected.

Đối với lỗi từ chối quyền, giữ audit ở nơi phù hợp: actor đã xác thực, tenant, loại thao tác, policy decision, thời gian. Không đưa raw access token, cookie, Authorization header, số thẻ, secret, full body chứa PII hoặc thông tin owner của tenant khác vào log. Có thể dùng ID nội bộ đã băm hoặc kho log có quyền đặc biệt khi điều tra.

### 6.3. Traces trả lời “tại hop nào phát sinh lỗi?”

W3C Trace Context dùng `traceparent` để truyền ngữ cảnh truy vết qua gateway → Orders API → Inventory/Payment API. Một trace hữu ích:

~~~text
trace 7b21...
  gateway: GET /api/orders       1.5 s (504 trả cho client)
    orders-api: GET /api/orders   1.8 s
      postgres query             1.6 s (pool wait)
      mapper                     0.01 s
~~~

Từ đó thấy gateway hết hạn trước khi ứng dụng hoàn thành. Nếu chỉ xem log cuối ở Spring, bạn có thể thấy 200 sau 1,8 giây, trong khi client đã nhận 504 ở 1,5 giây. Cần liên kết **edge request ID**, trace ID, dependency spans và status cuối người dùng nhìn thấy.

Trace sampling có thể làm mất các trường hợp ít gặp; nếu yêu cầu điều tra lỗi hiếm, cân nhắc sampling theo policy/collector phù hợp, vẫn tôn trọng dữ liệu nhạy cảm và ngân sách. **Baggage** được lan truyền qua service nên tránh chứa PII hoặc token; người dùng cũng có thể tự gửi trace headers vào gateway, vì thế không coi trace ID là bằng chứng danh tính hay quyền.

### 6.4. 4xx do CORS có thể bị nhìn thành lỗi mạng ở browser

Browser có thể báo `TypeError: Failed to fetch` vì CORS/preflight sai, dù backend trả 200 ở actual request hoặc 403 ở OPTIONS. Server-only metrics không nói đầy đủ trải nghiệm browser. Khi quan sát ứng dụng web, cần correlation với **client-side errors**, CORS response headers (`Access-Control-Allow-Origin`, `Vary: Origin`), OPTIONS preflight, edge cache và route. CORS không thay authentication/authorization; 403 từ preflight sai cấu hình có thể là regression dù HTTP là 4xx.

## 7. Java/Spring Boot: thu thập HTTP metrics và traces

Ví dụ dùng Java 17+, Spring Boot 3.x, Spring MVC và Micrometer. Các version Boot/Actuator có thể khác cách đặt tên metric/exporter; kiểm cấu hình đang dùng thay vì ép ví dụ vào mọi bản phát hành.

### 7.1. Dependencies

Ví dụ `build.gradle` (dự án dùng BOM của Spring Boot để chọn version tương thích):

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'

    runtimeOnly 'io.micrometer:micrometer-registry-prometheus'

    // Nếu hệ thống export distributed traces qua OpenTelemetry:
    implementation 'io.micrometer:micrometer-tracing-bridge-otel'
    runtimeOnly 'io.opentelemetry:opentelemetry-exporter-otlp'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

Khi bật Spring Boot Actuator/Observability, Spring MVC thường có metric/timer cho request server và tracing nếu bridge/exporter được cấu hình. **Không tự đếm request lần nữa bằng Counter trùng với metric HTTP mặc định**. Dùng metric tùy chỉnh cho ý nghĩa nghiệp vụ mà HTTP timer không thể nói, chẳng hạn `idempotency_conflict`, `reconciliation_due_age` hoặc `policy_expected_rejection`.

### 7.2. Cấu hình actuator và phân phối thời gian

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,prometheus
  metrics:
    distribution:
      percentiles-histogram:
        http.server.requests: true
  tracing:
    sampling:
      probability: 0.1
~~~

Cấu hình histogram giúp tính percentile từ distribution phù hợp ở Prometheus khi registry/exporter hỗ trợ. `sampling.probability: 0.1` là ví dụ tỷ lệ trace sampling, không phải yêu cầu cho mọi môi trường. Các đường `/actuator/**` cần quyền/khả năng truy cập được giới hạn theo hạ tầng; **không mở endpoint metrics công khai** cho Internet. Health liveness/readiness cũng phải có ý nghĩa đúng và tránh lộ chi tiết phụ thuộc nhạy cảm.

Ví dụ metric sau khi export sang Prometheus có thể xuất hiện dưới dạng `http_server_requests_seconds_count` hoặc các series histogram liên quan, tùy phiên bản/registry. Label thường bao gồm `method`, `uri` theo template, `status`, `outcome` và các chiều được cấu hình. **Không giả định cố định tên/tag ở mọi Spring Boot version**; xem `/actuator/prometheus` trên môi trường thử nghiệm để xác nhận.

### 7.3. ProblemDetail từ domain exception

Thay vì trả một JSON chuỗi tự viết trong mọi controller, map lỗi dự kiến sang code/HTTP có cấu trúc. Ví dụ domain exception:

~~~java
final class OrderVersionConflictException extends RuntimeException {}

final class DependencyUnavailableException extends RuntimeException {}
~~~

Handler của Spring MVC:

~~~java
import org.springframework.http.CacheControl;
import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
class ApiProblemHandler {

    @ExceptionHandler(OrderVersionConflictException.class)
    ResponseEntity<ProblemDetail> onVersionConflict(
            OrderVersionConflictException ex) {
        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
            HttpStatus.PRECONDITION_FAILED,
            "Dữ liệu đã được cập nhật; hãy tải lại bản mới nhất.");
        problem.setTitle("Precondition Failed");
        problem.setProperty("code", "ORDER_VERSION_CONFLICT");

        return ResponseEntity.status(HttpStatus.PRECONDITION_FAILED)
            .cacheControl(CacheControl.noStore())
            .body(problem);
    }

    @ExceptionHandler(DependencyUnavailableException.class)
    ResponseEntity<ProblemDetail> onDependencyUnavailable(
            DependencyUnavailableException ex) {
        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
            HttpStatus.SERVICE_UNAVAILABLE,
            "Dịch vụ phụ thuộc tạm thời không sẵn sàng.");
        problem.setTitle("Service Unavailable");
        problem.setProperty("code", "DEPENDENCY_UNAVAILABLE");

        return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
            .cacheControl(CacheControl.noStore())
            .body(problem);
    }
}
~~~

Ví dụ này **chỉ** xử lý hai ngoại lệ miền, để những exception khác được Spring xử lý theo cơ chế tương ứng. Nếu thêm handler 500 mặc định, phải giữ logging/tracing nguyên nhân và không lộ stack trace cho caller. Khi có trace/request ID ở MDC, có thể thêm **ID an toàn** vào ProblemDetail; không chép nguyên thông tin đầu vào thiếu tin cậy, Authorization header hoặc exception message chứa SQL vào body.

**Lưu ý ETag:** `412` chỉ chính xác khi một HTTP precondition (ví dụ `If-Match`) không thỏa; nếu xung đột nghiệp vụ thuần không liên quan precondition, có thể chọn `409 Conflict`. Đặt exception/code theo hợp đồng thật, tránh đổi status tùy tiện làm hỏng client.

### 7.4. 401/403 được xử lý ở SecurityFilterChain

Lỗi authentication và access denied thường xảy ra trong **Spring Security filter chain** trước khi tới controller; `@RestControllerAdvice` không tự bắt toàn bộ các trường hợp ấy. Cấu hình `AuthenticationEntryPoint` và `AccessDeniedHandler` phù hợp nếu muốn Problem Details/mã lỗi nhất quán, đồng thời giữ semantics `WWW-Authenticate` của Bearer token khi cần. Resource Server phải xác minh issuer, audience, expiry, chữ ký hoặc introspection và scope; log không được in raw token.

Hãy phân biệt:

- **401 token thiếu/hết hạn/sai issuer**: thường là request bị từ chối đúng. Nếu validator/JWKS hỏng làm token hợp lệ bị chặn, cảnh báo theo thay đổi đột ngột ở người dùng hợp lệ và dependency health.
- **403 thiếu scope**: kiểm soát quyền đúng; nếu role mapping sai sau deploy, đó là regression.
- **404 che giấu tài nguyên**: phù hợp chống BOLA, không được ghi chi tiết owner/tenant vào response để giải thích lý do.
- **503 khi service định danh tạm không thể xác minh**: cần quyết định fail-closed an toàn và mapping theo nguyên nhân hạ tầng, không mặc định trả 401 để làm đẹp SLI.

### 7.5. Metric nghiệp vụ với tập label giới hạn

Micrometer `MeterRegistry` có thể đếm một số **biến cố domain** không thể phân biệt từ status HTTP, ví dụ conflict idempotency hoặc request bị từ chối bởi một policy cụ thể:

~~~java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.stereotype.Component;

enum BusinessRejection {
    IDEMPOTENCY_CONFLICT,
    STALE_ORDER_VERSION,
    CLIENT_QUOTA_EXCEEDED
}

@Component
class BusinessRejectionMetrics {
    private final MeterRegistry registry;

    BusinessRejectionMetrics(MeterRegistry registry) {
        this.registry = registry;
    }

    void record(BusinessRejection reason) {
        Counter.builder("api.business.rejections")
            .description("Expected policy rejections by stable reason")
            .tag("reason", reason.name())
            .register(registry)
            .increment();
    }
}
~~~

Với enum có số giá trị hữu hạn, metric có cardinality kiểm soát. Không tạo metric name hoặc tag theo `error.getMessage()`, `userId`, URL chứa ID, tenant UUID hay API key. Việc dùng `register(registry)` nhiều lần với cùng name/tags thường trả meter đã tồn tại; nếu dùng trong đường request rất nóng, có thể cache Counter theo enum để giảm overhead. Chỉ gọi `record` tại **một điểm** phát sinh decision, tránh ghi hai lần khi exception được bắt ở nhiều tầng.

Mỗi request vẫn được theo dõi qua HTTP metrics mặc định. Metric domain này **không trực tiếp thay thế availability SLI**, vì một 409 expected không phải lỗi server và một 200 sai dữ liệu có thể không sinh event rejection nào.

### 7.6. Ghi log mức độ phù hợp

Một chính sách đơn giản:

| Nhóm sự kiện | Log level thường phù hợp | Ghi chú |
|---|---|---|
| 400/404/409 expected | INFO/DEBUG, có sampling | Không spam ERROR mỗi request |
| 401/403 dự kiến | INFO/security audit tùy chính sách | Phân biệt đăng nhập sai thông thường với tấn công |
| 429 quota dự kiến | INFO/WARN theo ngưỡng, metric cho policy | Không ghi một stack trace cho từng request |
| 500 do bug | ERROR | Cần exception/trace, không lộ secret |
| 503/504 do dependency | WARN/ERROR theo mức độ và vị trí | Nêu dependency, timeout/deadline, circuit state |
| 4xx spike do regression | Alert/dashboard độc lập | Không chỉ đổi log level của từng request |

Không sử dụng log message làm “cơ sở dữ liệu” để tính SLI khi metric counter trực tiếp đáng tin hơn. Logs thích hợp để điều tra case cụ thể và lưu audit với retention/access controls.

## 8. Xây dashboard không đếm sai lỗi

Một dashboard hữu ích có nhiều hàng đo thay vì một biểu đồ “Error rate 4xx+5xx”:

| Panel | Trục chính | Điều tra được |
|---|---|---|
| **Requests & SLI** | Good/bad eligible requests theo time/route | Chất lượng người dùng và SLO burn |
| **5xx/transport** | 500/502/503/504, timeout ở edge và app | Sự cố service/dependency |
| **4xx expected** | 400/401/403/404/409/412/429 theo code, route | Hành vi caller và chính sách |
| **4xx anomalies** | So sánh baseline, release, SDK/client cohort, quota plan | 4xx do regression |
| **Latency** | p50/p95/p99, queue/waiting time | Response vẫn 2xx nhưng quá chậm |
| **Dependencies** | DB pool, broker lag, upstream errors | Nguyên nhân gián tiếp |
| **Business correctness** | 202 pending quá SLA, duplicate effect, reconciliation lag | Tác động nằm ngoài HTTP |
| **Security** | Deny spikes, cross-tenant attempts, invalid token trends | Chống lạm dụng, kiểm policy |

Phân tầng route: `GET /api/catalog`, `POST /api/orders`, `POST /api/payments` có yêu cầu SLO khác nhau. Không để hàng triệu 404 từ một bot dò URI lấn át thành công của checkout; ngược lại, không loại mọi traffic “xấu” theo suy đoán chỉ vì sẽ làm số liệu đẹp hơn. Định nghĩa traffic đủ điều kiện dựa trên hợp đồng/edge classification có kiểm toán được.

### 8.1. Ví dụ truy vấn PromQL như tín hiệu ban đầu

Giả sử exporter cung cấp `http_server_requests_seconds_count` và tag `status`, `uri`, `job` như đã quan sát trong môi trường. Tỷ lệ **5xx tại Spring application**:

~~~promql
sum(rate(http_server_requests_seconds_count{
  job="orders-api",
  status=~"5..",
  uri!~"/actuator/.*"
}[5m]))
/
sum(rate(http_server_requests_seconds_count{
  job="orders-api",
  uri!~"/actuator/.*"
}[5m]))
~~~

Đây là **tín hiệu kỹ thuật 5xx**, không phải availability SLI hoàn chỉnh: nó bỏ lỡ timeout tại CDN, các 4xx gây tác động và 2xx sai nghiệp vụ. Với traffic bằng 0, mẫu số bằng 0 cần xử lý “không có dữ liệu” riêng; đừng tự giả định đó là 100% khỏe. Khi cần SLO chất lượng đúng hợp đồng, thiết kế telemetry **good/bad theo criteria cố định** ở biên đo thích hợp (edge/gateway và business outcome) rồi tính trên **cùng tập eligible events**.

Một truy vấn để theo dõi 429 (tín hiệu tách riêng):

~~~promql
sum by (uri) (
  rate(http_server_requests_seconds_count{
    job="orders-api", status="429"
  }[5m])
)
~~~

Truy vấn này cho biết **429 đến đâu**, chưa cho biết đúng quota hay do sự cố limiter. Cần thêm policy ID có cardinality thấp, số client/cohort chịu ảnh hưởng, rate-limit store health và thay đổi cấu hình. Khi dashboard không quan sát được 429 do gateway phát, cần bổ sung số liệu ở gateway thay vì tin một con số Spring là toàn bộ sự thật.

### 8.2. Cohort và đường cơ sở

Theo dõi error code theo:

- Phiên bản API (`/v1`, `/v2`) và route template.
- Release/version của ứng dụng và SDK nếu được client khai báo đáng tin ở mức thống kê.
- Phương thức, trạng thái auth tổng quát, nhóm tenant plan (không dùng tenant ID thô làm metric label).
- Vùng/khu vực, gateway instance hoặc nhà cung cấp dependency.
- Thời điểm deploy/config change so với baseline trước đó.

Ví dụ 403 tăng 20 lần sau deploy nhưng 5xx bằng 0 có thể là authorization regression. Nếu chỉ mở incident khi có 5xx, hệ thống sẽ bỏ lỡ mất chức năng ở người dùng hợp lệ. Ngược lại, một 404 ổn định từ crawler không cần paging đội trực đêm; có thể dùng thống kê bot/route và review định kỳ.

## 9. Thiết kế cảnh báo và runbook theo tác động

Không phải mọi metric lớn cần pager. Một cấu trúc tốt phân biệt:

1. **Page ngay:** availability SLO burn quá mức ở hành trình quan trọng, 5xx/timeout diện rộng, sai dữ liệu cross-tenant, charge trùng, 202 backlog ảnh hưởng đơn hàng.
2. **Ticket/triage sớm:** 401/403/404/429 tăng bất thường trên cohort hợp lệ, p95 latency tăng, SDK mới phát nhiều 400/422, cache invalidation chậm.
3. **Dashboard/phân tích sản phẩm:** expected 400 validation ở form, 404 do ID không tồn tại, 409 business conflict ổn định, 429 của client ngoài quota.

### 9.1. Runbook gợi ý

~~~text
Tín hiệu: 403 tăng mạnh trên POST /api/orders sau deploy.

1. Xác nhận phân bố theo route, API version, release, client cohort.
2. So với 2xx và traffic: có nhiều người dùng hợp lệ bị chặn không?
3. Kiểm trace/log policy decision và mapping scope/role/tenant.
4. Kiểm cấu hình issuer/JWKS, token audience, key rotation nếu có 401 kèm theo.
5. Dùng tài khoản test có quyền phù hợp tái hiện trên staging/canary.
6. Nếu là regression, rollback/disable thay đổi có kiểm soát.
7. Không mở quyền wildcard hoặc bỏ authorization để “chữa” 403.
8. Xác minh 403 giảm và business SLI phục hồi; bổ sung regression test.
~~~

Tương tự với 429: kiểm chính sách quota, khóa theo tenant/API key, redis limiter và `Retry-After`; nếu limiter chung làm mọi khách hàng bị chặn, sửa nguyên nhân trước khi tăng quota bừa bãi. Với 503: kiểm pool/queue, dependency health, load shedding, circuit breaker và retry storm. Có thể đặt ngân sách paging khác nhau theo giờ cao điểm/cửa sổ SLO, nhưng không để chính sách giờ hành chính che outage nghiêm trọng.

### 9.2. Tại sao một nhóm 4xx vẫn có thể cần báo động khẩn cấp?

Bảo mật và tính đúng đắn tạo ra ngoại lệ quan trọng. Ví dụ:

- Một regression trả **200** kèm order của tenant khác là sự cố nghiêm trọng dù metric error HTTP bằng 0.
- Một bùng nổ **401** do login service không xác minh JWT sau key rotation làm mọi người mất truy cập; có tác động availability.
- Một loạt **403** vì policy sai khiến người dùng không thể thanh toán.
- Một loạt **404** do route của phiên bản API mới bị thay thế gây mất chức năng.
- Một quota **429** sai khiến một khách hàng lớn không thể thực hiện giao dịch theo hợp đồng.

Vì vậy, cần các **canary/synthetic transactions với danh tính và quyền hợp lệ**, kiểm cả status và nội dung thực tế. Chúng bù những góc khuất mà status metrics không thể mô tả.

## 10. Kiểm thử API error contract và observability

### 10.1. Kiểm HTTP response trước

Có thể dùng `MockMvc` trong Spring để kiểm validation/domain error được ánh xạ ổn định. Ví dụ giả sử `OrderController` gọi service có thể ném `OrderVersionConflictException` và hệ thống bật Security MockMvc support. Bộ test cần thiết kế fixture rõ, ví dụ:

~~~java
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.patch;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class ApiProblemIT {
    @Autowired MockMvc mvc;

    @Test
    void staleEtagReturns412WithStableCode() throws Exception {
        // Fixture phải tạo order, caller có quyền và ETag hiện tại.
        // Tại đây dùng URI minh họa; security/fixture được cấu hình
        // trong test thực tế để dẫn đến nhánh If-Match sai.
        mvc.perform(patch("/api/orders/{id}", "order-101")
                .header("If-Match", "\"stale-version\"")
                .contentType("application/json")
                .content("{\"note\":\"changed\"}"))
            .andExpect(status().isPreconditionFailed())
            .andExpect(jsonPath("$.code")
                .value("ORDER_VERSION_CONFLICT"));
    }
}
~~~

Đây là **khung test cần fixture/authentication cụ thể**, không tự chạy độc lập chỉ với đoạn handler ở mục 7. Bảo đảm kiểm 412 với `If-Match` thật; nếu endpoint chưa hỗ trợ ETag thì phải triển khai contract trước khi kỳ vọng test xanh. Các test bổ sung nên kiểm body không chứa exception class, SQL hoặc token; `Content-Type: application/problem+json` và `Cache-Control` phù hợp.

### 10.2. Security test và lỗi 401/403

Với Spring Security:

- Không token hoặc JWT sai issuer/audience/chữ ký → 401.
- JWT hợp lệ thiếu scope → 403.
- JWT đúng scope nhưng không có quyền đọc order của tenant khác → 403 hoặc 404 theo policy.
- `jwt()` trong `spring-security-test` tạo principal giả cho authorization tests; **không chứng minh JwtDecoder xác minh chữ ký/audience thật**.
- Thêm integration test bằng access token JWT ký bởi test key/JWKS hoặc introspection fake có kiểm soát, đảm bảo Resource Server từ chối token không dành cho API.

Những 401/403/404 được từ chối đúng phải được gắn code ổn định; khi chúng bất ngờ tăng trên request có quyền, phải có alert riêng. Không bao giờ sửa SLO bằng cách mở rộng quyền truy cập.

### 10.3. Kiểm metric và trace thực sự tồn tại

Một test gọi endpoint và assert HTTP 409 **chưa** chứng minh exporter có tag đúng. Với Spring Boot 3.x, nhiều auto-observations có thể bị điều chỉnh trong test context; khi cần kiểm Actuator/observability, cấu hình test để bật instrumentation phù hợp (ví dụ `@AutoConfigureObservability` theo phiên bản), rồi quan sát `MeterRegistry` hoặc endpoint Prometheus của môi trường test. Không khẳng định một metric đã được ghi nếu test đang tắt exporter/observations.

Kiểm tra:

1. `GET /api/orders/{id}` bị 404 → metric HTTP có `uri` **templated**, `status=404`; không sinh label `id=...`.
2. `POST /api/orders` trả 409 expected → metric domain `api.business.rejections` tăng **một lần** với reason đã định nghĩa.
3. Lỗi dependency tạo 503 → metric/tracing cho thấy route và dependency, body không lộ stack trace.
4. Gateway 504 nhưng backend trả 200 trễ → telemetry edge/trace cho biết client thấy 504, không chỉ Spring 200.
5. `X-Request-Id`/trace IDs được truyền qua hop theo chính sách và không được tin như credential.
6. Lỗi có token/PII → log/traces/metrics đã che dữ liệu, không chứa header Authorization hoặc SQL chứa thông tin cá nhân.

### 10.4. Kiểm 4xx spike như một regression

Dựng một kiểm thử tích hợp/canary:

~~~text
Given:  người dùng "alice" có scope orders.read và membership tenant A
When:   GET /api/tenants/A/orders/A101 bằng access token hợp lệ
Then:   200 + order đúng owner

When:   GET cùng order với user thuộc tenant B
Then:   404 theo chính sách che giấu

When:   client hợp lệ gửi If-Match mới nhất để PATCH
Then:   2xx và version tăng

When:   cùng PATCH với If-Match cũ
Then:   412 ORDER_VERSION_CONFLICT

When:   fake dependency mất kết nối
Then:   503 DEPENDENCY_UNAVAILABLE; trace có thông tin dependency
~~~

Khi deploy làm user Alice nhận 403/404, test canary thất bại dù response là 4xx. Đó chính là khác biệt giữa **từ chối có chủ đích** và **mất chức năng**. Test should check business state, not only status: một 200 nhưng trả dữ liệu của user khác là lỗi cần bắt.

### 10.5. Ma trận test lỗi và tín hiệu mong đợi

| Tình huống | HTTP | Classification mặc định | SLI/alert cần xem |
|---|---|---|---|
| JSON sai do người dùng nhập | 400 | EXPECTED_REJECTION | Tỷ lệ 400 theo SDK/form |
| JWT hết hạn thật | 401 | EXPECTED_REJECTION | Auth UX/refresh success |
| JWT hợp lệ bị lỗi JWKS validator | 401 hoặc lỗi hạ tầng tùy implementation | IMPACTING | Token hợp lệ bị chặn, synthetic auth |
| Scope không đủ | 403 | EXPECTED_REJECTION | Policy deny trend |
| User hợp lệ bị policy mới chặn | 403 | IMPACTING | Canary + regression |
| Order không tồn tại | 404 | EXPECTED_REJECTION | 404 theo route |
| Router mới trả 404 cho endpoint hợp lệ | 404 | IMPACTING | Route probe/SDK cohort |
| ETag cũ | 412 | EXPECTED_REJECTION | Optimistic locking conflict rate |
| Client vượt quota đúng hợp đồng | 429 | EXPECTED_REJECTION | Quota policy và Retry-After |
| Hệ thống quota cấu hình sai | 429 | IMPACTING | Consumer dưới ngưỡng vẫn bị chặn |
| DB connection pool hết | 503 | IMPACTING | DB pool, error budget burn |
| Gateway chờ upstream quá lâu | 504 | IMPACTING | Gateway latency/timeout |
| Endpoint trả 202 nhưng job kẹt | 202 | IMPACTING theo business SLA | Async completion age |
| API trả 200 dữ liệu tenant khác | 200 | IMPACTING/SECURITY | Data isolation invariant |

Phân loại `EXPECTED_REJECTION` ở bảng là **giả định rule được thực thi đúng**. Khi bằng chứng thay đổi, điều tra và cập nhật rule/test/hệ thống đo theo quy trình có review; không dùng từng request từ client tự gắn nhãn “expected”.

## 11. Những sai lầm phổ biến trong thiết kế quan sát

| Sai lầm | Hậu quả | Cách sửa |
|---|---|---|
| Đếm mọi 4xx như lỗi server | SLO xấu giả, cảnh báo ồn | Phân loại expected rejection theo contract; theo dõi 4xx riêng |
| Loại mọi 4xx khỏi giám sát | Bỏ lỡ auth/route/quota regression | Alert theo baseline/cohort/canary cho 401/403/404/429 |
| Chỉ đo 5xx trong ứng dụng | Bỏ timeout/TLS/gateway error | Lấy thêm telemetry edge và synthetic clients |
| Coi mọi 2xx là thành công nghiệp vụ | Không thấy sai dữ liệu, 202 job treo | Business correctness/completion SLIs |
| Mọi exception đều map 400 | Che bug và làm client hiểu sai | Chỉ map lỗi dự kiến bằng code cụ thể; 5xx cho lỗi server |
| Dùng exception message làm error code | Metric cardinality cao, lộ dữ liệu, dashboard không ổn định | Stable enum/code, message chỉ để người dùng đọc |
| Ghi stack trace cho mỗi 404 | Tốn chi phí, log noise | Sampling/INFO cho expected, ERROR cho unexpected |
| Dùng `userId`/`orderId` làm metric label | Nổ cardinality, rò PII | Route template, enum reason, cohort nhỏ |
| Nối số lỗi ở CDN và API rồi cộng | Đếm một request hai lần | Chọn SLI measurement boundary; trace để tìm root cause |
| Đọc CORS error chỉ từ 200 backend | Không thấy browser bị chặn | RUM/frontend errors và preflight/edge headers |
| Báo 503 vì một client vượt quota | Client retry sai, mất tín hiệu fairness | 429 cho client quota, 503 cho service overload |
| Đặt ngưỡng alert không có runbook | Pager fatigue | Alert gắn user impact, owner, bước xử lý |
| Expose Actuator/Prometheus công khai | Rò thông tin hạ tầng | Chặn bằng network/auth và cấu hình endpoint |
| Ghi Authorization header vào trace/log | Lộ token | Redaction và allowlist field cho telemetry |

## 12. Bài tập thực hành

### Bài tập 1 — Phân loại 4xx dự kiến và ảnh hưởng chất lượng

Cho các quan sát sau:

1. 10.000 request GET; 200 response 404 cho ID do bot dò tìm.
2. 300 request checkout đúng token/scope; sau deploy đều nhận 403.
3. Một người dùng gửi PATCH với ETag cũ và nhận 412.
4. Tenant có quota 100/phút gửi 120 request/phút và nhận 20 lần 429.
5. Redis limiter gộp mọi API key thành một bucket, làm các tenant dưới quota cũng nhận 429.
6. API trả 200 nhưng body chứa đơn hàng của tenant khác.

Yêu cầu: chọn `EXPECTED_REJECTION`, `IMPACTING` hoặc `NEEDS_REVIEW`; đề xuất metric, log, alert tương ứng. Giải thích vì sao status 4xx/2xx không đủ.

**Gợi ý:** (1) thường expected theo hợp đồng và traffic classification; (2) impacting; (3) expected; (4) expected nếu policy đúng; (5) impacting; (6) impacting nghiêm trọng. Khi không có bằng chứng bot hay policy đúng, giữ NEEDS_REVIEW trước khi kết luận.

### Bài tập 2 — Viết SLI cho Orders API

Cho một tháng có 100.000 request đủ điều kiện, gồm 96.000 2xx đúng hạn/đúng dữ liệu, 2.500 expected 4xx, 1.000 5xx/transport timeout và 500 4xx do route regression.

Hãy tính availability SLI khi expected 4xx được tính good; so với SLO 99,9%; tính error budget tương đương số request và xác định đã vượt bao nhiêu. Sau đó thiết kế một SLI khác cho `POST /orders` trả 202 nhưng operation cần hoàn tất trong 10 phút.

**Đáp án kiểm tra:** Good = 98.500; bad = 1.500; SLI = **98,5%**. Với 100.000 request và mục tiêu 99,9%, budget là **100 bad events**; vượt **1.400** event. Async SLI phải đo operation kết thúc đúng SLA, không chỉ status 202.

### Bài tập 3 — Mở rộng Problem Details và metric trong Spring

Viết Spring `@RestControllerAdvice` cho `InvalidCartException → 422 INVALID_CART`, `OrderVersionConflictException → 412 ORDER_VERSION_CONFLICT` khi dùng `If-Match`, `DependencyUnavailableException → 503 DEPENDENCY_UNAVAILABLE`. Trả `application/problem+json`, không lộ SQL/stack trace, bổ sung correlation ID an toàn. Dùng Micrometer đếm `api.business.rejections` theo một enum có tập giá trị hữu hạn.

**Tiêu chí đạt:** Expected 4xx và impacting 503 có HTTP status/code nhất quán; metric không chứa raw path/user ID và không double count.

### Bài tập 4 — Kiểm 401/403 regression sau key rotation

Một deploy thay JWKS cache hoặc audience validator, sau đó 401 tăng lên 80% trên request của người dùng đã đăng nhập. Hãy đưa ra runbook: nguồn log/trace/metric cần xem, cách phân biệt token hết hạn thật với validator lỗi, canary bằng access token test hợp lệ, cách rollback an toàn và regression tests.

**Tiêu chí đạt:** Không mở bỏ kiểm chữ ký/audience; xem 401 tăng là sự cố chất lượng khi request hợp lệ bị chặn; có xác thực trở lại sau sửa.

### Bài tập 5 — Thiết kế dashboard cho 429 và 503

Một đối tác vượt quota 100/phút nên nhận 429, trong khi một sự cố DB khiến nhiều tenant nhận 503. Hãy thiết kế dashboard tách quota key/policy, per-route 429, `Retry-After`, DB pool, queue, 503, p99 và error budget burn. Xác định chính sách client retry phù hợp cho từng lỗi.

**Tiêu chí đạt:** Không coi 429 của client vượt quota là server outage; không coi 503 là do client sử dụng quá mức; retry/backoff có giới hạn, POST cần idempotency.

### Bài tập 6 — Không tin HTTP 200/202

Orders API trả 202 cho 1.000 operation; 950 hoàn tất trong 5 phút, 30 hoàn tất sau 20 phút và 20 không hoàn tất. SLO nghiệp vụ là 99% hoàn tất trong 10 phút. Hãy tính completion SLI, xác định nhóm vi phạm, thiết kế metric `operation_completion_age`/backlog và cảnh báo cho `RECONCILING` quá SLA.

**Đáp án kiểm tra:** 950/1.000 = **95%**, thấp hơn SLO 99%; có 50 operation vi phạm ngưỡng 10 phút, dù HTTP ban đầu đều có thể là 202 hợp lệ.

### Bài tập 7 — Viết integration tests cho observability

Tạo test dùng Spring Security và PostgreSQL Testcontainers để xác minh:

- Request malformed trả 400, Problem Details code ổn định, không ghi stack trace.
- Người dùng thuộc tenant A đọc order B nhận 404/403 theo policy và không lộ dữ liệu.
- Token sai audience bị `JwtDecoder` thật từ chối 401.
- Quota theo tenant đúng trả 429; DB mất kết nối trả 503.
- `MeterRegistry` ghi HTTP request theo URI template; metric domain chỉ tăng một lần.
- Trace ID có thể liên hệ với log request, không có raw token.

**Tiêu chí đạt:** Tách `jwt()` mock authorization tests với JWT/JWKS thật; có kiểm dữ liệu, metrics và logs/trace theo khả năng test infrastructure. Testcontainers không tự thay thế việc kiểm bảo mật.

## 13. Tự kiểm tra

1. **404 có luôn làm availability SLI xấu không?** Không. Nếu resource không tồn tại và server xử lý đúng contract, đó có thể là expected rejection.
2. **Tất cả 4xx đều vô hại?** Không. Regression router/authorization/quota có thể làm mất chức năng dù trả 4xx.
3. **Một 429 có đồng nghĩa quá tải server?** Không. Thường là quota consumer; kiểm tính đúng đắn của limiter.
4. **503 khác 429 thế nào?** 503 mô tả service tạm không sẵn sàng; 429 thường từ chối vì caller vượt giới hạn sử dụng.
5. **Nếu API trả 200 nhưng dữ liệu sai tenant, SLI có nên xem tốt không?** Không; đó là lỗi correctness/security nghiêm trọng.
6. **SLI có nên chỉ tính request mà server trả status?** Không nếu cần phản ánh người dùng; gateway/transport timeout cũng có thể làm request thất bại.
7. **Có nên gắn `userId` làm Prometheus label?** Không; nguy cơ cardinality cao và rò thông tin.
8. **Tại sao cần app error code ngoài HTTP status?** Để phân biệt nguyên nhân và tạo tín hiệu ổn định cho client/telemetry.
9. **`jwt()` trong MockMvc chứng minh chữ ký JWT thật?** Không; nó bypass decoder. Cần test bearer/JWKS thật.
10. **202 Accepted chứng minh job đã hoàn tất chưa?** Chưa; cần business completion SLI và trạng thái operation.
11. **Alert nào có thể bắt 403 regression dù 5xx = 0?** Canary request có quyền hợp lệ, cohort baseline và policy deny anomaly.
12. **Expected 4xx có thể vẫn cần log bảo mật?** Có, nhất là tấn công dò quét hoặc brute-force; bảo vệ PII/token.

## 14. Tài liệu chuẩn và checklist

Tài liệu đối chiếu:

- **RFC 9110 — HTTP Semantics:** ý nghĩa nhóm 4xx, 5xx và từng status — https://www.rfc-editor.org/rfc/rfc9110
- **RFC 6585 — Additional HTTP Status Codes:** 429 và quy tắc liên quan — https://www.rfc-editor.org/rfc/rfc6585
- **RFC 9457 — Problem Details for HTTP APIs:** định dạng lỗi có cấu trúc — https://www.rfc-editor.org/rfc/rfc9457
- **RFC 9111 — HTTP Caching:** tránh cache sai response riêng/có lỗi — https://www.rfc-editor.org/rfc/rfc9111
- **W3C Trace Context:** `traceparent`/`tracestate` để liên kết trace — https://www.w3.org/TR/trace-context/
- **OpenTelemetry — Concepts and semantic conventions:** metrics, logs, traces — https://opentelemetry.io/docs/concepts/
- **Spring Boot Actuator/Metrics:** https://docs.spring.io/spring-boot/reference/actuator/metrics.html
- **Spring Boot Tracing:** https://docs.spring.io/spring-boot/reference/actuator/tracing.html
- **Spring Security Resource Server:** https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/index.html
- **Google SRE Workbook — Alerting on SLOs:** https://sre.google/workbook/alerting-on-slos/

Trước khi công bố dashboard và alert cho REST API, hãy xác nhận:

- Định nghĩa **eligible traffic**, **good event** và SLO có được ghi rõ, ổn định trước khi có sự cố?
- 400/401/403/404/409/412/422/429 có error code ổn định, phân loại theo contract và có theo dõi spike?
- 5xx/transport timeout ở edge và ở application có được phân biệt nguồn, tránh đếm trùng?
- Có **latency** và **business correctness/completion** SLI để phát hiện 200/202 không đúng chất lượng?
- Metric dùng route template và enum có cardinality thấp, không gắn user/token/ID động?
- Log/trace có correlation ID, nguyên nhân, policy decision và đã loại secret/PII?
- `@RestControllerAdvice`, security filters và gateway trả lỗi nhất quán, không che bug bằng 4xx tùy tiện?
- Có canary cho request hợp lệ với JWT/scope/tenant, phát hiện 401/403/404 regression?
- Alert gắn **tác động người dùng, error budget burn và runbook**, không chỉ số lần exception?
- Test chứng minh HTTP, metric, trace và dữ liệu nghiệp vụ; CI chạy kiểm thử thích hợp trước deploy?

**Điểm cốt lõi:** Trong REST API, **4xx có thể là kết quả dự kiến của hợp đồng**: từ chối request sai, thiếu quyền, conflict hoặc vượt quota đúng chính sách. Nhưng **chất lượng dịch vụ** phải được đo qua những request và nghiệp vụ mà hệ thống cam kết phục vụ: 4xx do regression, 5xx, timeout và cả 2xx sai kết quả đều có thể là sự cố. Phân loại đúng nguyên nhân, gắn metric/log/trace và định nghĩa SLI minh bạch giúp vận hành phản ứng trước tác động thật thay vì chạy theo màu đỏ của status.
