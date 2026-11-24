# Error response — Thiết kế phản hồi lỗi xác thực API an toàn và nhất quán

> **Chương:** Authentication trong API  
> **Chủ đề:** Error response  
> **Phạm vi:** Security Authentication Fundamentals — thiết kế HTTP error response cho API có xác thực và phân quyền, dùng đúng status code và authentication challenge, biểu diễn lỗi nhất quán, hỗ trợ retry có kiểm soát và tránh tiết lộ thông tin nhạy cảm.

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt lỗi request, authentication, authorization, throttling và lỗi phụ thuộc hệ thống.
2. Chọn HTTP status code phù hợp cho các trường hợp thiếu credential, credential không hợp lệ, thiếu scope và vượt rate limit.
3. Dùng WWW-Authenticate và Bearer challenge theo ngữ nghĩa HTTP/OAuth.
4. Phân biệt lỗi tại OAuth token endpoint với lỗi truy cập resource API.
5. Thiết kế response body nhất quán, có thể máy đọc được, ví dụ theo Problem Details.
6. Tránh rò rỉ token, account existence, policy nội bộ, key material, stack trace và thông tin hạ tầng.
7. Hướng dẫn client xử lý retry, refresh token, step-up, reauthentication và backoff đúng cách.
8. Liên kết error response với audit, correlation ID, metrics và incident response.
9. Kiểm thử status code, header, response body, CORS, timing và các trường hợp rò rỉ thông tin.

## 1. Error response trong API authentication là gì?

Error response là phản hồi cho biết một API request không thể được xử lý như yêu cầu. Với API có xác thực, lỗi có thể xuất hiện ở nhiều giai đoạn: request không hợp lệ, không có credential, credential không được chấp nhận, principal không có quyền, request vượt giới hạn hoặc hệ thống phụ thuộc không khả dụng.

Một error response tốt cần trả lời đúng mức những câu hỏi sau:

- Client cần thay đổi request, xác thực lại, xin thêm quyền hay chờ rồi thử lại?
- Request bị từ chối vì credential thiếu, không hợp lệ hay không đủ quyền?
- Có thể retry an toàn không?
- Nếu retry, client cần chờ bao lâu?
- Có mã lỗi ổn định nào để client hoặc support tra cứu?

Response đồng thời là một ranh giới bảo mật. Nó được gửi tới caller, có thể là ứng dụng hợp lệ, browser, SDK, proxy hoặc attacker. Vì vậy, response phải cung cấp đủ thông tin để client hành động nhưng không tiết lộ bí mật hoặc trạng thái nội bộ không cần thiết.

### Những thành phần của một error response

- HTTP status code;
- Header có ý nghĩa giao thức như WWW-Authenticate, Retry-After hoặc Content-Type;
- Response body với error code/type và mô tả an toàn;
- Correlation/request ID để tra cứu log;
- Cache policy phù hợp;
- CORS header nếu request đi từ browser origin được phép.

Không nên dùng một HTTP 200 cho mọi kết quả rồi đặt success=false trong JSON. Status code là một phần của giao thức HTTP; proxy, browser, SDK, monitoring và client retry logic dựa vào nó.

## 2. Phân biệt các lớp lỗi

API nên phân loại lỗi theo giai đoạn để trả đúng status và hướng xử lý.

| Lớp | Ví dụ | Hành vi phù hợp |
| --- | --- | --- |
| Request syntax/validation | JSON sai, thiếu field bắt buộc | 400 hoặc 422 theo quy ước API |
| Authentication missing | Không có credential cần thiết | 401 và challenge phù hợp |
| Authentication invalid | Token hết hạn, chữ ký sai, issuer/audience không hợp lệ | 401 và challenge/error code phù hợp |
| Authorization denied | Token hợp lệ nhưng thiếu scope/role | 403 hoặc 404 theo chính sách che giấu resource |
| Rate limit | Caller vượt giới hạn | 429 và Retry-After khi xác định được |
| Dependency unavailable | Identity provider, introspection hoặc key service tạm lỗi | 503 hoặc lỗi gateway phù hợp |
| Internal failure | Lỗi không dự kiến trong API | 500 với body chung, không lộ chi tiết |

Không biến mọi lỗi thành 401. Nếu token hợp lệ nhưng người dùng không có quyền, trả 401 có thể khiến client refresh token lặp vô ích và che khuất lỗi authorization.

## 3. HTTP status code cho lỗi authentication và authorization

### 400 Bad Request

Dùng khi request không hợp lệ về cú pháp hoặc cấu trúc, ví dụ thiếu tham số bắt buộc, JSON không parse được hoặc tham số giao thức sai định dạng.

Trong OAuth, token endpoint thường dùng 400 cho nhiều lỗi protocol như invalid_request, invalid_grant hoặc unsupported_grant_type. Cần theo đúng đặc tả endpoint, không suy ra rằng mọi lỗi credential đều phải là 401.

### 401 Unauthorized

401 có nghĩa request chưa có credential xác thực hợp lệ cho tài nguyên. Ví dụ:

- Không gửi Authorization header trong khi endpoint yêu cầu xác thực;
- Bearer token không hợp lệ hoặc hết hạn;
- Chữ ký token sai;
- Token có issuer/audience không được chấp nhận;
- Token đã bị thu hồi và verifier có thể xác định điều đó.

Theo HTTP semantics, server tạo response 401 cần gửi WWW-Authenticate challenge cho ít nhất một authentication scheme áp dụng. Header này giúp client biết phương thức xác thực được yêu cầu.

### 403 Forbidden

403 phù hợp khi server hiểu request và danh tính/credential đã được xác thực nhưng caller không có quyền thực hiện hành động. Ví dụ:

- Token hợp lệ nhưng thiếu scope;
- Principal không có role cần thiết;
- Policy từ chối thao tác trên resource;
- Account đã xác thực nhưng không được phép dùng API này.

Không nên trả chi tiết policy, role nội bộ hoặc tên resource nhạy cảm nếu caller không được phép biết.

### 404 Not Found

API có thể trả 404 thay cho 403 khi cần che giấu sự tồn tại của resource. Ví dụ, người dùng không được phép biết một hồ sơ riêng tư có tồn tại hay không.

Đây là lựa chọn theo threat model và consistency của API, không phải cách thay thế 403 cho mọi lỗi quyền. Cùng một loại truy vấn nên có hành vi nhất quán để tránh side channel qua status, body hoặc timing.

### 407 Proxy Authentication Required

407 dành cho proxy yêu cầu client xác thực với proxy. Nó không thay thế 401 của origin server. Proxy dùng header Proxy-Authenticate và client có thể gửi Proxy-Authorization theo cơ chế tương ứng.

### 429 Too Many Requests

429 cho biết caller đã gửi quá nhiều request trong khoảng thời gian nhất định. Có thể kèm Retry-After để hướng dẫn thời điểm thử lại. Rate limit có thể dựa trên client, principal, tenant, IP, route hoặc quota.

Không dùng 429 để biểu diễn token không hợp lệ hoặc thiếu quyền. Cần phân biệt abuse throttling với policy denial.

### 500 và 503

- **500 Internal Server Error:** lỗi nội bộ không dự kiến; response công khai không nên chứa exception hoặc stack trace.
- **503 Service Unavailable:** dịch vụ tạm thời không thể xử lý, ví dụ dependency thiết yếu đang outage hoặc hệ thống đang maintenance. Có thể kèm Retry-After nếu thời gian dự kiến có ý nghĩa.

Nếu token introspection service tạm unavailable, không được tự động coi token là hợp lệ. Policy fail-open/fail-closed phải được quyết định theo mức rủi ro của resource; response cần phản ánh service availability thay vì giả vờ rằng credential sai.

### Bảng chọn nhanh

| Tình huống | Status thường dùng | Header/hành vi |
| --- | --- | --- |
| Thiếu bearer token | 401 | WWW-Authenticate: Bearer |
| Bearer token không hợp lệ | 401 | Bearer challenge, error=invalid_token khi phù hợp |
| Token hợp lệ nhưng thiếu scope | 403 | Bearer challenge có thể nêu insufficient_scope |
| Request sai cú pháp | 400 | Body mô tả lỗi request an toàn |
| Body đúng cú pháp nhưng vi phạm validation | 422 theo API convention | Problem Details hoặc validation errors |
| Vượt rate limit | 429 | Retry-After nếu có thể |
| Identity dependency tạm outage | 503 | Retry-After khi xác định được |
| Lỗi không dự kiến | 500 | Mã lỗi chung và correlation ID |

## 4. WWW-Authenticate và authentication challenge

WWW-Authenticate là header HTTP cho biết authentication scheme mà resource server chấp nhận hoặc yêu cầu. Với bearer token, challenge thường có dạng:

`````````http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="orders-api"
Cache-Control: no-store
Content-Type: application/json

{
  "error": "authentication_required",
  "message": "A valid access token is required."
}
`````````

Realm giúp phân vùng không gian bảo vệ. Không đưa thông tin bí mật hoặc tên hệ thống nội bộ vào realm.

### Bearer error parameters

RFC 6750 định nghĩa các error value quan trọng cho bearer token:

- **invalid_request:** request thiếu tham số, chứa nhiều phương thức truyền token hoặc sai định dạng theo profile;
- **invalid_token:** access token hết hạn, bị thu hồi, sai chữ ký hoặc không hợp lệ;
- **insufficient_scope:** token không có quyền cần thiết.

Ví dụ token không hợp lệ:

`````````http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="orders-api", error="invalid_token"
Cache-Control: no-store
`````````

Ví dụ thiếu scope:

`````````http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer realm="orders-api",
  error="insufficient_scope", scope="orders:write"
Cache-Control: no-store
`````````

Chỉ nêu scope cần thiết nếu việc tiết lộ tên scope không làm lộ cấu trúc quyền nhạy cảm. Không đưa token value, chữ ký, claim riêng tư hoặc lý do xác minh nội bộ vào challenge.

### Khi không có credential

Nếu endpoint yêu cầu bearer authentication nhưng request không gửi token, server có thể trả 401 với WWW-Authenticate: Bearer mà không cần error=invalid_token. Không khẳng định token invalid khi client chưa gửi token.

## 5. Lỗi tại OAuth token endpoint và resource API

OAuth có các endpoint và vai trò khác nhau. Cần phân biệt lỗi khi client xin token với lỗi khi gọi API bằng access token.

### Token endpoint

Client gửi grant request tới authorization server. Một số error code tiêu biểu:

| Error | Ý nghĩa |
| --- | --- |
| invalid_request | Request thiếu tham số, chứa giá trị không hợp lệ hoặc lặp tham số |
| invalid_client | Client authentication thất bại |
| invalid_grant | Authorization grant hoặc refresh token không hợp lệ, hết hạn, bị thu hồi hoặc không khớp client |
| unauthorized_client | Client không được phép dùng grant type này |
| unsupported_grant_type | Grant type không được authorization server hỗ trợ |
| invalid_scope | Scope được yêu cầu không hợp lệ hoặc vượt quyền được cấp |

OAuth token endpoint thường trả JSON với HTTP 400 cho lỗi request/grant và có quy tắc riêng cho client authentication, tùy phương thức xác thực client và đặc tả áp dụng. Không trả thông tin giúp attacker dò client secret hoặc xác định chính xác tài khoản người dùng.

Ví dụ minh họa:

`````````http
HTTP/1.1 400 Bad Request
Content-Type: application/json
Cache-Control: no-store
Pragma: no-cache

{
  "error": "invalid_grant",
  "error_description": "The grant is invalid or can no longer be used."
}
`````````

Không trả lại authorization code, refresh token hoặc client secret trong error_description.

### Resource API

Resource server nhận access token và quyết định có cho phép truy cập resource hay không. Nó có thể trả:

- 401 khi token thiếu hoặc không hợp lệ;
- 403 khi token hợp lệ nhưng không đủ scope/quyền;
- 429 khi vượt rate limit;
- 503 khi dependency cần thiết không khả dụng.

Không dùng error code của token endpoint như invalid_grant cho lỗi truy cập resource API nếu semantics không phù hợp.

## 6. Thiết kế response body nhất quán

Response body nên có cấu trúc ổn định để SDK và ứng dụng xử lý tự động. Không nên phụ thuộc vào việc parse câu tiếng Việt/Anh tự do.

### Các trường gợi ý

| Trường | Mục đích |
| --- | --- |
| type | URI định danh loại lỗi, nếu dùng Problem Details |
| title | Tiêu đề ngắn, ổn định theo loại lỗi |
| status | HTTP status code |
| detail | Mô tả an toàn cho người tích hợp |
| instance | URI/reference cho occurrence cụ thể, nếu phù hợp |
| code | Mã lỗi ổn định của API |
| request_id | ID để support/operations tra cứu |
| errors | Chi tiết validation theo field, chỉ khi an toàn |

### Problem Details

RFC 9457 định nghĩa Problem Details cho HTTP APIs với media type application/problem+json. Các thành phần chuẩn gồm type, title, status, detail và instance; API có thể thêm extension member như code hoặc request_id.

Ví dụ:

`````````http
HTTP/1.1 403 Forbidden
Content-Type: application/problem+json
Cache-Control: no-store

{
  "type": "https://api.example.com/problems/insufficient-permission",
  "title": "Forbidden",
  "status": 403,
  "detail": "The caller is not permitted to perform this operation.",
  "instance": "/problem-occurrences/req-7f2c",
  "code": "INSUFFICIENT_PERMISSION",
  "request_id": "req-7f2c"
}
`````````

URI trong type có thể là tài liệu mô tả lỗi. Không bắt buộc type phải trỏ tới một trang có nội dung chi tiết, nhưng nó nên ổn định và có ngữ nghĩa nhất quán.

### Một response schema không cần làm mọi lỗi giống hệt nhau

Validation error có thể cần danh sách field; authentication error thường không cần chi tiết về credential; dependency failure có thể cần retry guidance. Điều quan trọng là các trường lõi, mã lỗi và semantics ổn định.

## 7. Không tiết lộ thông tin nhạy cảm trong error response

Error response là dữ liệu có thể bị caller lưu lại, chụp màn hình, gửi qua support ticket hoặc ghi vào telemetry. Chỉ trả thông tin cần thiết cho client hành động.

### Không bao giờ trả

- Password, password hash hoặc password candidate;
- Access token, refresh token, ID token hoặc authorization code;
- Session cookie, CSRF token hoặc API key;
- Private key, client secret, signing key hoặc TOTP seed;
- Raw authorization header;
- Stack trace, exception message nội bộ hoặc đường dẫn filesystem;
- SQL query, tên bảng nội bộ hoặc connection string;
- JWKS/private key location, secret manager path hoặc internal hostname;
- Toàn bộ claims của token khi không cần;
- Nội dung assertion SAML hoặc raw authenticator response.

### Tránh account enumeration

Nếu login API hoặc API tra cứu account có thể bị dùng để dò user, tránh phân biệt công khai giữa account không tồn tại, account bị disable, password sai, account bị khóa do policy và recovery factor chưa đăng ký.

Có thể dùng response chung ở public boundary, trong khi audit nội bộ giữ reason code chính xác. Cần kiểm tra cả status, body, header, redirect, response size và timing; chỉ đổi message nhưng để status khác nhau vẫn có thể rò rỉ.

### Không lộ policy nội bộ

Không trả risk score, ngưỡng lockout, số lần thử còn lại, danh sách device đã biết hoặc rule phát hiện fraud cho caller chưa được tin cậy. Những dữ liệu này có thể giúp attacker điều chỉnh chiến thuật.

### Timing và side channel

Không nhất thiết mọi lỗi phải có thời gian xử lý giống hệt nhau, nhưng cần tránh khác biệt lớn và ổn định làm lộ account existence hoặc credential state. Dùng cùng quy trình kiểm tra, response envelope và giới hạn timing khi threat model yêu cầu.

## 8. Error code ổn định và localization

Client nên dựa vào machine-readable code, không parse message tự do.

| Code | Ý nghĩa |
| --- | --- |
| AUTHENTICATION_REQUIRED | Cần credential |
| INVALID_ACCESS_TOKEN | Access token không hợp lệ |
| TOKEN_EXPIRED | Token hết hạn, nếu policy cho phép phân biệt |
| INSUFFICIENT_SCOPE | Token thiếu scope |
| ACCESS_DENIED | Policy từ chối truy cập |
| RESOURCE_NOT_FOUND | Resource không tồn tại hoặc được che giấu |
| RATE_LIMITED | Vượt rate limit |
| AUTH_DEPENDENCY_UNAVAILABLE | Dependency xác thực tạm unavailable |
| REQUEST_INVALID | Request sai cấu trúc |
| INTERNAL_ERROR | Lỗi nội bộ không dự kiến |

Không tạo code mới cho mọi biến thể kỹ thuật. Giữ code ổn định qua phiên bản; thêm chi tiết an toàn vào extension field hoặc audit reason.

### Message localization

Message có thể được dịch theo Accept-Language hoặc locale của client. Tuy nhiên:

- Code không được dịch;
- Status/header không phụ thuộc ngôn ngữ;
- Không dùng message làm protocol contract;
- Không đưa nội dung nhạy cảm vào bản dịch;
- Fallback language cần được xác định.

## 9. Retry, refresh token và reauthentication

Không phải lỗi nào cũng nên retry. Retry sai cách có thể gây token refresh storm, tăng tải identity provider hoặc tạo vòng lặp vô hạn.

| Response | Hành động client gợi ý |
| --- | --- |
| 400 request invalid | Sửa request; không retry nguyên trạng |
| 401 token invalid/expired | Thực hiện refresh/re-authentication theo policy một lần; tránh loop |
| 403 insufficient scope | Xin scope/consent hoặc hiển thị quyền thiếu; refresh token đơn thuần không tự cấp quyền |
| 404 resource hidden/not found | Không retry vô hạn; xử lý như resource không khả dụng |
| 429 rate limited | Tôn trọng Retry-After và exponential backoff có jitter |
| 500 | Retry có giới hạn chỉ khi thao tác an toàn/idempotent |
| 503 dependency unavailable | Backoff, circuit breaker và retry theo policy |

### Khi gặp 401

Client có thể thử refresh access token nếu refresh token hợp lệ và được phép dùng, lỗi có thể giải quyết bằng refresh, refresh chưa thất bại trước đó trong cùng request flow và không có dấu hiệu refresh token bị revoke hoặc reuse.

Nếu refresh thất bại với invalid_grant, client nên xóa trạng thái credential cục bộ phù hợp và yêu cầu người dùng đăng nhập lại. Không gửi refresh token tới resource API để thử lại.

### Khi gặp 403

Không tự động refresh lặp. Nếu token hợp lệ nhưng thiếu scope, client cần yêu cầu quyền/consent phù hợp hoặc thông báo người dùng. Server vẫn phải thực hiện authorization ở mỗi request.

## 10. Retry-After và rate limit headers

429 có thể đi kèm Retry-After:

`````````http
HTTP/1.1 429 Too Many Requests
Retry-After: 30
Content-Type: application/problem+json

{
  "type": "https://api.example.com/problems/rate-limited",
  "title": "Too Many Requests",
  "status": 429,
  "detail": "The request limit has been reached. Try again later.",
  "code": "RATE_LIMITED",
  "request_id": "req-a813"
}
`````````

Retry-After có thể biểu diễn số giây hoặc HTTP date theo HTTP semantics. Client cần xử lý cả hai dạng nếu API hỗ trợ.

### Rate limit headers

API có thể cung cấp các header quota như limit, remaining và reset theo convention đã công bố. Không có một bộ header rate limit duy nhất được mọi API sử dụng giống nhau; tài liệu API cần xác định tên, đơn vị và semantics.

### Backoff

Client nên ưu tiên Retry-After khi có, dùng exponential backoff với jitter khi không có hướng dẫn cụ thể, đặt maximum retry và deadline, không retry request không idempotent nếu không có idempotency key, và dừng retry khi nhận lỗi authentication/authorization không thể tự khắc phục.

## 11. CORS và browser client

Browser có thể không cho JavaScript đọc response nếu CORS header không hợp lệ, ngay cả khi server đã trả error body đúng. Vì vậy, API cần áp dụng CORS policy nhất quán cho cả success và error response.

### Kiểm soát

- Chỉ cho phép origin được phê duyệt;
- Không dùng wildcard origin cùng credentials;
- Thêm CORS header cần thiết trên các nhánh 401, 403, 429, 500 và 503;
- Xử lý OPTIONS preflight đúng;
- Không phản chiếu Origin tùy tiện;
- Không cho CORS trở thành cơ chế xác thực hoặc authorization.

CORS là chính sách browser kiểm soát việc script đọc response; nó không ngăn mọi client ngoài browser gọi API. Server vẫn phải xác thực và phân quyền từng request.

## 12. Cache và error response

Error response có thể chứa trạng thái xác thực hoặc thông tin cá nhân. Không để intermediary cache phản hồi nhạy cảm theo cách làm lộ dữ liệu giữa người dùng.

### Gợi ý

- Dùng Cache-Control: no-store cho response chứa token/authentication detail hoặc dữ liệu nhạy cảm;
- Cân nhắc private/no-cache tùy semantics và threat model;
- Không cache 401/403 theo key thiếu Authorization context;
- Đảm bảo CDN/gateway không bỏ qua Vary hoặc cache key cần thiết;
- Không để proxy cache error của một user rồi trả cho user khác.

Cache policy cần được xác định theo loại response và kiến trúc. Không cache một error response có thể phụ thuộc principal nếu cache không phân biệt principal đúng cách.

## 13. Correlation ID, audit và observability

Error response cần giúp support và security team tìm được sự kiện phía server mà không phải tiết lộ chi tiết nội bộ.

### Correlation/request ID

Server nên tạo request ID khó va chạm và ghi nó trong response. Nếu nhận correlation ID từ client, cần xác thực định dạng, giới hạn độ dài và tránh tin nó như định danh duy nhất; server có thể tạo ID riêng rồi liên kết với trace context.

Ví dụ:

`````````http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="inventory-api"
X-Request-ID: req-5c21d8
Cache-Control: no-store
`````````

### Audit event

Nên ghi event name và timestamp, request/correlation ID, service/route/method, subject/client reference nếu xác định được, authentication method và token validation outcome, authorization decision và policy version, reason code nội bộ, rate-limit decision, dependency status và response status.

Không ghi Authorization header, raw token, cookie, password, secret hoặc private key. Log reason code có thể chi tiết hơn response công khai, nhưng vẫn cần data minimization và access control.

### Metrics

- 401 rate theo route/client/method;
- 403 rate theo scope/resource class;
- 429 rate và retry behavior;
- 5xx rate liên quan identity dependency;
- Token refresh failure rate;
- Error code distribution;
- CORS preflight/error rate;
- Response latency theo error class;
- Tỷ lệ error response thiếu WWW-Authenticate khi status 401;
- Tỷ lệ response thiếu request ID hoặc sai content type.

Alert trên biến động bất thường, không chỉ trên tổng số lỗi. Một spike 401 có thể do token issuer outage, key rotation sai, clock drift hoặc tấn công credential; cần correlation với deployment và identity provider.

## 14. Ví dụ end-to-end

### Thiếu token

`````````http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="catalog-api"
Content-Type: application/problem+json
Cache-Control: no-store
X-Request-ID: req-101

{
  "type": "https://api.example.com/problems/authentication-required",
  "title": "Unauthorized",
  "status": 401,
  "detail": "A valid access token is required.",
  "code": "AUTHENTICATION_REQUIRED",
  "request_id": "req-101"
}
`````````

### Token không hợp lệ

`````````http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="catalog-api", error="invalid_token"
Content-Type: application/problem+json
Cache-Control: no-store
X-Request-ID: req-102

{
  "type": "https://api.example.com/problems/invalid-token",
  "title": "Unauthorized",
  "status": 401,
  "detail": "The access token is invalid or expired.",
  "code": "INVALID_ACCESS_TOKEN",
  "request_id": "req-102"
}
`````````

### Thiếu scope

`````````http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer realm="catalog-api",
  error="insufficient_scope", scope="catalog:write"
Content-Type: application/problem+json
X-Request-ID: req-103

{
  "type": "https://api.example.com/problems/insufficient-permission",
  "title": "Forbidden",
  "status": 403,
  "detail": "The caller is not permitted to perform this operation.",
  "code": "INSUFFICIENT_SCOPE",
  "request_id": "req-103"
}
`````````

### Rate limit

`````````http
HTTP/1.1 429 Too Many Requests
Retry-After: 20
Content-Type: application/problem+json
X-Request-ID: req-104

{
  "type": "https://api.example.com/problems/rate-limited",
  "title": "Too Many Requests",
  "status": 429,
  "detail": "The request limit has been reached. Try again later.",
  "code": "RATE_LIMITED",
  "request_id": "req-104"
}
`````````

### Identity dependency unavailable

`````````http
HTTP/1.1 503 Service Unavailable
Retry-After: 10
Content-Type: application/problem+json
Cache-Control: no-store
X-Request-ID: req-105

{
  "type": "https://api.example.com/problems/authentication-service-unavailable",
  "title": "Service Unavailable",
  "status": 503,
  "detail": "Authentication is temporarily unavailable. Try again later.",
  "code": "AUTH_DEPENDENCY_UNAVAILABLE",
  "request_id": "req-105"
}
`````````

Response 503 không được khẳng định token hợp lệ hoặc không hợp lệ khi verifier chưa thể đưa ra quyết định. Client cần backoff theo Retry-After và không tự bỏ qua authentication.

## 15. Threat model: lỗi response có thể bị khai thác

| Rủi ro | Cách xảy ra | Kiểm soát |
| --- | --- | --- |
| Account enumeration | Status/body/timing tiết lộ account tồn tại | Response công khai nhất quán, reason code nội bộ |
| Token leakage | Error body echo token hoặc header | Redaction, không phản chiếu credential |
| Stack trace disclosure | Trả exception/SQL/internal path | Generic public detail, request ID |
| Authorization confusion | Trả 401 cho thiếu scope | Dùng 403 hoặc 404 theo policy |
| Refresh storm | Client refresh liên tục với mọi 401 | Error code ổn định, client refresh một lần có kiểm soát |
| Retry storm | Client bỏ qua Retry-After | Backoff, jitter, retry budget |
| Cache poisoning/leak | Proxy cache response theo key thiếu principal | no-store/private và cache key đúng |
| CORS inconsistency | Error response thiếu CORS header | CORS middleware áp dụng cho mọi response |
| Policy disclosure | Nêu risk score/lockout threshold | Không trả policy nội bộ |
| Timing side channel | Nhánh account tồn tại chạy khác rõ rệt | Chuẩn hóa flow và đo timing |
| Dependency fail-open | Introspection outage bị coi là token hợp lệ | Fail policy theo risk, trả 503 phù hợp |
| Header injection | Dữ liệu user được phản chiếu vào header | Validate/encode header values |
| Content-type confusion | Body JSON nhưng header sai | Content-Type chuẩn, schema validation |
| Error amplification | Error detail lớn hoặc request ID bị lợi dụng | Giới hạn kích thước, rate limit và sanitization |

## 16. Bộ kiểm thử chấp nhận

| Trường hợp | Cách thử | Kết quả kỳ vọng |
| --- | --- | --- |
| Missing credential | Gọi protected endpoint không có token | 401 và WWW-Authenticate |
| Invalid bearer token | Gửi token sai chữ ký | 401, không tạo session/quyền |
| Expired token | Gửi token hết hạn | 401 theo token profile |
| Revoked token | Gửi token đã revoke | Bị từ chối nếu verifier có trạng thái revoke |
| Wrong issuer | Gửi token từ issuer không tin cậy | 401, không lộ trust configuration |
| Wrong audience | Gửi token dành cho API khác | 401 |
| Insufficient scope | Token hợp lệ nhưng thiếu scope | 403 hoặc 404 theo resource concealment policy |
| Missing role | Principal thiếu role | Authorization denial, không refresh loop |
| Malformed request | JSON sai cú pháp | 400 |
| Validation failure | Field hợp lệ về cú pháp nhưng vi phạm rule | 422 theo API contract |
| Token endpoint invalid_grant | Dùng grant/refresh token không hợp lệ | OAuth error response phù hợp |
| Invalid client | Client authentication sai | Token endpoint xử lý theo OAuth profile |
| Rate limit | Vượt quota | 429 và Retry-After khi có |
| Dependency outage | Introspection/JWKS service không khả dụng | 503 hoặc policy response đã định; không fail-open ngoài ý muốn |
| Internal exception | Gây lỗi không dự kiến | 500 generic, có request ID |
| WWW-Authenticate | Kiểm tra mọi response 401 | Có challenge phù hợp |
| Bearer insufficient_scope | Gọi API thiếu scope | Challenge dùng error đúng semantics |
| Problem Details | Kiểm tra Content-Type và schema | application/problem+json và field hợp lệ |
| No secret echo | Gửi token marker trong request lỗi | Marker không xuất hiện trong response/log |
| No stack trace | Gây exception | Không lộ stack trace, path hoặc SQL |
| Account enumeration | So sánh account tồn tại/không tồn tại | Không có khác biệt công khai dễ khai thác |
| Cache policy | Kiểm tra response auth-sensitive | Cache-Control phù hợp, không lộ giữa user |
| Retry-After seconds | Trả 429 với số giây | Client chờ đúng khoảng thời gian |
| Retry-After date | Trả HTTP date | Client xử lý đúng định dạng |
| Retry storm | Mô phỏng nhiều client nhận 503/429 | Backoff và jitter giới hạn tải |
| CORS error response | Browser gọi và đọc 401/403/429 | Header CORS áp dụng đúng origin |
| OPTIONS preflight | Gửi preflight | Policy và allow headers/methods đúng |
| Correlation ID | Gửi request lỗi | Có request ID để tra cứu |
| Client-supplied ID | Gửi ID bất thường/quá dài | Server validate hoặc thay ID an toàn |
| Header injection | Đưa CR/LF vào input được phản chiếu | Bị loại bỏ/encode, không tạo header mới |
| Content type | So sánh body và Content-Type | Luôn nhất quán |
| 404 concealment | Truy vấn resource không được phép biết | Hành vi nhất quán, không lộ existence |
| Refresh behavior | Nhận 401 rồi refresh thất bại | Dừng loop và yêu cầu đăng nhập lại |
| 403 refresh loop | Token hợp lệ nhưng thiếu scope | Client không refresh vô hạn |

Kiểm thử ở API gateway, resource server, authorization middleware, OAuth client/SDK và browser client. Cần kiểm tra cả status, headers, body, timing, caching và log; chỉ assert JSON message là chưa đủ.

## 17. Checklist thiết kế Error response

- **Status semantics:** 400/401/403/404/407/429/500/503 được dùng đúng mục đích?
- **401 challenge:** Mọi response 401 có WWW-Authenticate phù hợp?
- **Bearer errors:** invalid_request, invalid_token và insufficient_scope dùng đúng ngữ nghĩa?
- **OAuth endpoints:** Token endpoint errors theo OAuth protocol và không nhầm với resource API?
- **Response schema:** Có code ổn định, body máy đọc được và Problem Details khi phù hợp?
- **Disclosure:** Không có token, secret, stack trace, SQL, internal host hoặc policy nội bộ?
- **Enumeration:** Không tiết lộ account/resource existence qua status, body, header hoặc timing?
- **Retry:** Client phân biệt refresh, step-up, sửa request, backoff và dừng retry?
- **Rate limit:** 429 có Retry-After khi xác định được?
- **Dependency failure:** Không fail-open ngoài policy khi identity dependency unavailable?
- **CORS:** Error response và preflight có header nhất quán?
- **Cache:** Authentication error nhạy cảm không bị cache sai giữa principal?
- **Observability:** Có request ID, reason code nội bộ và metrics?
- **Logging:** Không ghi raw Authorization, cookie, password, token hoặc private key?
- **Testing:** Đã kiểm tra headers, schema, timing, retry, CORS, cache và redaction?

### Câu hỏi tự kiểm tra

1. Khi nào nên trả 401 và khi nào nên trả 403?
2. Vì sao 401 cần WWW-Authenticate?
3. Bearer error invalid_token khác insufficient_scope thế nào?
4. Token endpoint OAuth khác resource API ở loại lỗi nào?
5. Problem Details giúp client xử lý lỗi ra sao?
6. Vì sao không nên trả chi tiết account bị khóa cho caller chưa xác thực?
7. Khi gặp 403 thiếu scope, vì sao refresh token không tự giải quyết vấn đề?
8. Retry-After giúp ngăn retry storm thế nào?
9. Vì sao CORS header cần có trên cả error response?
10. Làm thế nào để correlation ID hỗ trợ điều tra mà không làm lộ secret?

## Kết luận

**Error response là một phần của giao thức bảo mật API: status, header và body phải phản ánh đúng lý do từ chối, hướng xử lý của client và giới hạn thông tin được tiết lộ.** Dùng 401 cho credential thiếu/không hợp lệ cùng WWW-Authenticate, 403 cho principal đã xác thực nhưng thiếu quyền, 429 cho throttling và 503 cho dependency tạm unavailable; áp dụng 404 khi policy cần che giấu resource một cách nhất quán. OAuth token endpoint có error semantics riêng, còn Problem Details giúp chuẩn hóa body máy đọc được. Response cần tránh echo secret, stack trace, account state và policy nội bộ; đồng thời hỗ trợ Retry-After, CORS, cache policy, correlation ID và audit. Client phải refresh, retry hoặc yêu cầu quyền theo đúng loại lỗi để không tạo vòng lặp và không làm tăng tải hệ thống.
