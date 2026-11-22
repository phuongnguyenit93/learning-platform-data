# Thiết kế thông báo lỗi cho bên gọi và nhật ký nội bộ

Khi xác minh JSON Web Token (JWT), hệ thống cần thông báo cho bên gọi biết request không được chấp nhận, đồng thời giúp đội vận hành và bảo mật tìm ra nguyên nhân. Hai nhu cầu này có mức chi tiết khác nhau. Một response quá chi tiết có thể tiết lộ cấu hình issuer, trạng thái khóa, cách xác minh chữ ký hoặc thông tin nội bộ; một nhật ký thiếu ngữ cảnh lại khiến việc điều tra và khắc phục sự cố rất khó khăn.

Bài này thuộc chương **Xác minh token** của module **Security - JSON Web Token (JWT)**. Nội dung áp dụng cho bảo mật JWT nói chung, độc lập ngôn ngữ lập trình, nền tảng và framework.

## 1. Mục tiêu và nguyên tắc thiết kế

Sau bài học, người đọc có thể:

1. Phân biệt lỗi request, lỗi xác thực token, lỗi phân quyền và lỗi hạ tầng xác minh.
2. Chọn HTTP status và Bearer challenge phù hợp.
3. Thiết kế thông báo bên ngoài ngắn gọn, ổn định và không tiết lộ chi tiết nhạy cảm.
4. Xây dựng reason code nội bộ và nhật ký có cấu trúc để điều tra.
5. Loại bỏ token, secret, claims nhạy cảm và dữ liệu không tin cậy khỏi log.
6. Dùng correlation ID, metrics, rate limit và cảnh báo để hỗ trợ vận hành.
7. Kiểm thử cả response, log redaction và hành vi khi hệ thống phụ thuộc bị lỗi.

Nguyên tắc trung tâm:

- **Bên gọi nhận thông tin đủ để xử lý request tiếp theo.**
- **Đội vận hành nhận thông tin đủ để chẩn đoán và ứng cứu.**
- **Chi tiết nhạy cảm chỉ được lưu trong hệ thống nội bộ có kiểm soát truy cập.**
- **Lỗi hạ tầng không bị trình bày như lỗi token của người dùng.**
- **Không ghi lại chính credential mà hệ thống đang bảo vệ.**

Không nên dùng cùng một chuỗi lỗi cho mọi tình huống ở mọi lớp. Hãy phân loại lỗi nội bộ trước, sau đó ánh xạ sang response công khai và sự kiện log theo policy.

## 2. Ba đối tượng cần thông tin

| Đối tượng | Cần biết | Không nên nhận |
| --- | --- | --- |
| Client / bên gọi API | Request có được chấp nhận không; cần lấy token mới, bổ sung quyền hay thử lại sau. | Stack trace, tên KMS/HSM, URL nội bộ, chi tiết khóa, cấu hình issuer hoặc lý do xác minh mật mã quá cụ thể. |
| Đội vận hành / SRE | Thành phần nào lỗi, thời điểm, dependency, request ID, mức độ ảnh hưởng và hướng xử lý. | Raw access token, private key, HMAC secret hoặc dữ liệu cá nhân không cần thiết. |
| Đội bảo mật / điều tra | Reason code, issuer/profile, key ID đã chuẩn hóa, principal, nguồn request, sự kiện liên quan và bằng chứng kiểm toán. | Credential có thể replay hoặc vật liệu bí mật chỉ để tiện điều tra. |

Một response có thể được hiển thị cho người dùng cuối, SDK, API gateway hoặc một dịch vụ khác. Hãy xác định rõ người nhận thực tế. Không đưa thông tin chỉ dành cho đội vận hành vào response của một API công khai.

## 3. Phân loại lỗi trước khi tạo thông báo

Không phải mọi lần xác minh thất bại đều có cùng nguyên nhân hoặc cùng cách xử lý.

| Nhóm lỗi | Ví dụ | Ý nghĩa vận hành |
| --- | --- | --- |
| Request không hợp lệ | Authorization header sai cú pháp, gửi nhiều phương thức truyền bearer token không được phép | Client cần sửa request. |
| Thiếu thông tin xác thực | Không có bearer token ở endpoint yêu cầu xác thực | Client cần cung cấp credential. |
| Token không hợp lệ | JWT malformed, chữ ký sai, issuer không được tin, audience sai, token hết hạn hoặc bị thu hồi | Token không được chấp nhận. |
| Xác thực thành công nhưng thiếu quyền | Scope/permission không đủ cho thao tác | Caller đã được nhận diện nhưng không được phép thực hiện hành động. |
| Dependency tạm thời không khả dụng | JWKS endpoint lỗi, không có cache hợp lệ; dịch vụ xác minh khóa/KMS không phản hồi | Hệ thống không thể hoàn thành xác minh an toàn. |
| Lỗi cấu hình hoặc triển khai | Không có issuer profile, allowlist thuật toán sai, key resolver cấu hình mâu thuẫn | Cần đội vận hành sửa cấu hình. |
| Lỗi nội bộ không dự kiến | Parser hoặc thành phần xác minh phát sinh exception không được xử lý | Cần điều tra và sửa lỗi hệ thống. |
| Bị giới hạn lưu lượng | Quá nhiều request hoặc vượt quota | Caller cần tuân thủ retry policy; vận hành cần kiểm tra abuse/load. |

Việc phân loại này phải dựa trên trạng thái thực tế của pipeline. Ví dụ, nếu JWKS endpoint không truy cập được và không có public key còn trong thời hạn tin cậy, verifier chưa thể kết luận token sai chữ ký. Đó là lỗi dependency, dù request cuối cùng vẫn phải bị từ chối theo nguyên tắc fail closed.

## 4. Phân biệt authentication, authorization và availability

Ba trạng thái thường bị gộp nhầm:

- **Authentication failure:** không chứng minh được token hợp lệ cho API/profile này.
- **Authorization failure:** token đã được xác minh, nhưng subject/client không có quyền thực hiện hành động.
- **Validation infrastructure failure:** verifier không thể hoàn tất quá trình xác minh do dependency hoặc cấu hình nội bộ.

Ví dụ:

| Tình huống | Phân loại | Cách phản hồi thường dùng |
| --- | --- | --- |
| Không gửi access token | Thiếu authentication | 401 Unauthorized |
| Token hết hạn hoặc chữ ký không hợp lệ | Authentication failure | 401 Unauthorized |
| Token hợp lệ nhưng thiếu scope bắt buộc | Authorization failure | 403 Forbidden |
| JWKS không tải được và không có cache tin cậy | Availability/dependency failure | 503 Service Unavailable theo API policy |
| Không có cấu hình issuer cho deployment | Configuration failure | 500 Internal Server Error hoặc trạng thái vận hành tương ứng |

Không trả 401 invalid_token cho mọi lỗi của verifier. Nếu dependency xác minh bị hỏng, client lấy token mới có thể không giải quyết được vấn đề và còn tạo thêm tải không cần thiết.

## 5. HTTP status và Bearer challenge

Với API nhận OAuth 2.0 Bearer Token, RFC 6750 định nghĩa các error code phổ biến trong header WWW-Authenticate.

### 5.1. Thiếu bearer token

Nếu request không có thông tin xác thực, resource server thường trả 401 Unauthorized và challenge Bearer. Theo RFC 6750, khi không có thông tin xác thực, server không nên đưa error hoặc chi tiết lỗi khác vào challenge.

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="orders-api"
Content-Type: application/problem+json
~~~

Response body có thể dùng một thông báo chung:

~~~json
{
  "type": "about:blank",
  "title": "Unauthorized",
  "status": 401,
  "detail": "Authentication is required to access this resource."
}
~~~

### 5.2. Request dùng bearer token sai cách

invalid_request thường áp dụng khi request có lỗi trong cách truyền bearer token, chẳng hạn dùng nhiều phương thức truyền token cùng lúc hoặc request không tuân thủ cú pháp được hỗ trợ. Có thể trả 400 Bad Request:

~~~http
HTTP/1.1 400 Bad Request
WWW-Authenticate: Bearer realm="orders-api", error="invalid_request"
Content-Type: application/problem+json
~~~

Không dùng invalid_request chỉ vì JWT có chữ ký sai hoặc hết hạn; đó là lỗi token.

### 5.3. Token không hợp lệ

invalid_token áp dụng khi bearer token được cung cấp nhưng không hợp lệ, hết hạn, bị thu hồi hoặc không thể được chấp nhận theo policy xác minh. Resource server thường trả 401 Unauthorized:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="orders-api", error="invalid_token"
Content-Type: application/problem+json
~~~

Body nên tránh nêu cụ thể token thất bại do chữ ký, issuer, key ID, audience, trạng thái thu hồi hay thời điểm hết hạn nếu thông tin đó không cần thiết cho caller.

### 5.4. Thiếu scope hoặc quyền

Nếu token đã được xác minh nhưng không đủ scope cho tài nguyên, RFC 6750 định nghĩa insufficient_scope và thường dùng 403 Forbidden:

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer realm="orders-api", error="insufficient_scope"
Content-Type: application/problem+json
~~~

Thuộc tính scope trong challenge có thể được dùng khi phù hợp. Chỉ công bố tên scope đã được thiết kế là public contract; không đưa tên permission nội bộ, vai trò quản trị hoặc quy tắc phân quyền nhạy cảm vào response.

### 5.5. Dependency xác minh không khả dụng

Nếu JWKS endpoint không truy cập được, cache đã hết thời hạn tin cậy và verifier không có public key hợp lệ để kiểm tra, hệ thống không thể hoàn tất xác minh. Có thể trả 503 Service Unavailable với thông báo chung:

~~~http
HTTP/1.1 503 Service Unavailable
Content-Type: application/problem+json
Retry-After: 30
~~~

~~~json
{
  "type": "about:blank",
  "title": "Service Unavailable",
  "status": 503,
  "detail": "Authentication is temporarily unavailable. Please retry later."
}
~~~

Chỉ gửi Retry-After nếu có cơ sở về thời gian retry. Không trả invalid_token khi chưa thể kiểm tra token. Vẫn phải fail closed: không cho request đi qua chỉ vì JWKS/KMS đang lỗi.

### 5.6. Lỗi cấu hình hoặc lỗi nội bộ

Nếu deployment thiếu cấu hình issuer hoặc có lỗi lập trình, có thể trả 500 Internal Server Error với nội dung chung. Không gửi stack trace, tên class, tên file, endpoint nội bộ hoặc chi tiết cấu hình cho caller.

## 6. Bảng ánh xạ lỗi JWT sang response công khai

Bảng dưới đây là một policy tham khảo cho resource server dùng Bearer token. API cần công bố contract nhất quán và điều chỉnh theo giao thức thực tế.

| Lỗi nội bộ | Response thường dùng | Thông tin bên ngoài |
| --- | --- | --- |
| Không có Authorization header | 401 | Bearer challenge không kèm error code; thông báo cần authentication. |
| Bearer header malformed / nhiều cách truyền token | 400 | invalid_request; hướng dẫn dùng một cách truyền credential hợp lệ. |
| JWT malformed hoặc segment sai định dạng | 401 | invalid_token; thông báo token không được chấp nhận. |
| Thuật toán không nằm trong allowlist | 401 | invalid_token; không nêu allowlist nội bộ. |
| Chữ ký không hợp lệ | 401 | invalid_token; không nêu thuật toán kiểm tra hoặc chi tiết chữ ký. |
| Issuer không được tin cậy | 401 | invalid_token; không tiết lộ registry issuer. |
| Audience không khớp | 401 | invalid_token; không tiết lộ audience nội bộ. |
| Token hết hạn / chưa đến nbf | 401 | invalid_token; client có thể lấy token mới theo luồng của mình. |
| Token bị thu hồi | 401 | invalid_token; không tiết lộ trạng thái session hoặc cơ chế revoke. |
| Token profile không phù hợp endpoint | 401 | invalid_token; không mô tả profile nội bộ. |
| Token hợp lệ nhưng thiếu scope | 403 | insufficient_scope nếu dùng Bearer semantics. |
| JWKS/KMS dependency tạm lỗi, không có cache tin cậy | 503 | Authentication tạm thời không khả dụng. |
| Lỗi cấu hình issuer/key resolver | 500 | Lỗi nội bộ chung; đội vận hành nhận reason code chi tiết. |
| Vượt rate limit | 429 | Thông báo thử lại sau; có thể kèm Retry-After. |

Không coi bảng này là quy tắc cứng cho mọi giao thức. Ví dụ, API nội bộ có thể có error envelope riêng; nhưng vẫn phải giữ đúng khác biệt giữa token invalid, permission denied và verifier unavailable.

## 7. Thiết kế thông báo công khai

Thông báo bên ngoài nên ngắn, ổn định, không phụ thuộc implementation và không tiết lộ nguyên nhân nội bộ quá mức.

### 7.1. Nội dung nên có

- HTTP status phù hợp.
- Error code chuẩn của giao thức nếu có, ví dụ invalid_token hoặc insufficient_scope.
- Một câu mô tả ngắn giúp caller hiểu request không được chấp nhận.
- Correlation/request ID để liên hệ đội hỗ trợ khi cần.
- Hướng xử lý an toàn nếu có thể: lấy token mới, yêu cầu scope phù hợp hoặc thử lại sau.

### 7.2. Nội dung không nên có

- “Chữ ký RSA không khớp với modulus key X” hoặc chi tiết kiểm tra mật mã.
- Tên issuer nội bộ, jwks_uri, host KMS/HSM, key resource ID hoặc cấu hình cache.
- Raw key ID, raw issuer, toàn bộ claims hoặc payload.
- Stack trace, exception message, tên package, đường dẫn file hoặc phiên bản thư viện dễ khai thác.
- Nội dung Authorization header hoặc JWT.
- Danh sách user/tenant tồn tại hoặc không tồn tại.

### 7.3. Dùng thông điệp ổn định

Ví dụ thông báo phù hợp:

| Code công khai | Message |
| --- | --- |
| invalid_request | The authentication request is invalid. |
| invalid_token | The access token is invalid or cannot be accepted. |
| insufficient_scope | The access token does not grant permission for this operation. |
| Dependency unavailable | Authentication is temporarily unavailable. Please retry later. |
| Internal error | The request could not be completed. |

Thông điệp nên tránh thay đổi theo từng chi tiết như expired, unknown key, invalid signature nếu không có yêu cầu sản phẩm rõ ràng. Thông tin hướng dẫn lấy token mới có thể đặt trong tài liệu client/SDK thay vì trả nguyên nhân xác minh chi tiết.

## 8. Dùng Problem Details hoặc error envelope nhất quán

RFC 9457 định nghĩa Problem Details cho HTTP APIs. Có thể dùng application/problem+json để chuẩn hóa body:

~~~json
{
  "type": "about:blank",
  "title": "Unauthorized",
  "status": 401,
  "detail": "The access token is invalid or cannot be accepted.",
  "instance": "/requests/req-7f2a"
}
~~~

Các trường:

- type: loại problem; about:blank phù hợp khi không cần loại tùy chỉnh.
- title: tiêu đề ngắn, thường gắn với status.
- status: HTTP status tương ứng.
- detail: thông báo an toàn cho caller.
- instance: định danh instance của lỗi nếu có ích; không dùng URL nội bộ hoặc dữ liệu chứa bí mật.

Có thể bổ sung code hoặc traceId theo API contract, nhưng không đưa internal reason code vào response. Nếu dùng một envelope riêng, giữ cùng nguyên tắc và không làm mất WWW-Authenticate header cần thiết.

## 9. Internal reason code: chi tiết dành cho hệ thống

Nên có mã lỗi nội bộ ổn định, không phụ thuộc câu exception của thư viện.

| Internal reason code | Ý nghĩa |
| --- | --- |
| AUTH_HEADER_MISSING | Không có thông tin xác thực. |
| AUTH_HEADER_MALFORMED | Authorization header sai cấu trúc. |
| BEARER_TRANSPORT_INVALID | Bearer token được truyền qua nhiều cách hoặc cách không được hỗ trợ. |
| JWT_COMPACT_FORMAT_INVALID | JWT compact serialization sai định dạng. |
| JWT_HEADER_INVALID | Protected header không hợp lệ hoặc thiếu member cần thiết. |
| JWT_ALGORITHM_NOT_ALLOWED | alg không nằm trong allowlist. |
| JWT_KEY_NOT_FOUND | Không tìm thấy khóa phù hợp trong JWKS tin cậy. |
| JWT_KEY_AMBIGUOUS | Có nhiều khóa phù hợp hoặc key ID gây mơ hồ. |
| JWT_KEY_TYPE_MISMATCH | kty/curve không tương thích thuật toán. |
| JWT_SIGNATURE_INVALID | Chữ ký không hợp lệ. |
| JWT_ISSUER_UNTRUSTED | Issuer không thuộc registry tin cậy. |
| JWT_ISSUER_MISMATCH | iss không khớp issuer được cấu hình. |
| JWT_AUDIENCE_MISMATCH | Audience không phù hợp. |
| JWT_EXPIRED | Token đã hết hạn. |
| JWT_NOT_YET_VALID | Thời điểm nbf chưa đến. |
| JWT_ISSUED_AT_INVALID | iat không hợp lệ theo policy. |
| JWT_TOKEN_REVOKED | Token hoặc key đã bị thu hồi theo cơ chế áp dụng. |
| JWT_PROFILE_MISMATCH | Token không đúng profile của endpoint. |
| AUTH_SCOPE_INSUFFICIENT | Token hợp lệ nhưng thiếu scope. |
| AUTH_PERMISSION_DENIED | Không đủ quyền theo policy nghiệp vụ. |
| JWKS_FETCH_FAILED | Không tải được JWKS endpoint. |
| JWKS_RESPONSE_INVALID | Response JWKS sai cấu trúc hoặc không hợp lệ. |
| JWKS_CACHE_STALE | Cache vượt giới hạn tin cậy. |
| ISSUER_METADATA_INVALID | Metadata issuer không hợp lệ hoặc không khớp. |
| VALIDATION_CONFIG_ERROR | Cấu hình verifier/issuer/key resolver bị lỗi. |
| VALIDATION_DEPENDENCY_TIMEOUT | Dependency xác minh vượt timeout. |
| VALIDATION_INTERNAL_ERROR | Lỗi nội bộ không dự kiến. |

Reason code là một contract nội bộ. Có thể thêm code theo nghiệp vụ, nhưng không nên dùng trực tiếp exception message làm code vì message thường thay đổi theo phiên bản thư viện và có thể chứa dữ liệu nhạy cảm.

## 10. Phân biệt internal reason code với error code công khai

Một số reason code nội bộ có thể ánh xạ vào cùng một lỗi công khai:

| Internal reason code | Public status | Public error |
| --- | --- | --- |
| JWT_COMPACT_FORMAT_INVALID | 401 | invalid_token |
| JWT_SIGNATURE_INVALID | 401 | invalid_token |
| JWT_ISSUER_UNTRUSTED | 401 | invalid_token |
| JWT_AUDIENCE_MISMATCH | 401 | invalid_token |
| JWT_EXPIRED | 401 | invalid_token |
| JWT_TOKEN_REVOKED | 401 | invalid_token |
| AUTH_SCOPE_INSUFFICIENT | 403 | insufficient_scope |
| JWKS_FETCH_FAILED không có cache tin cậy | 503 | Không dùng invalid_token |
| VALIDATION_CONFIG_ERROR | 500 | Lỗi nội bộ chung |

Không ánh xạ mọi lỗi vào một code công khai duy nhất nếu điều đó làm client không thể xử lý đúng. Ngược lại, không công khai từng reason code nội bộ nếu chúng tiết lộ trạng thái hệ thống hoặc tạo oracle cho attacker.

## 11. Thiết kế nhật ký xác minh token

Một event log tốt phải giúp trả lời:

- Request xảy ra khi nào và ở đâu?
- Thành phần nào xử lý?
- Token validation thành công hay thất bại?
- Thất bại ở giai đoạn nào và theo reason code nào?
- Issuer/profile/key set nào được sử dụng?
- Caller hoặc workload nào gửi request?
- Dependency có lỗi hoặc cache có vấn đề không?
- Có correlation ID để nối với gateway, API và trace không?

Nên dùng structured logging (ví dụ JSON) thay vì nối chuỗi tự do. Trường log cần có schema ổn định, kiểu dữ liệu rõ và giới hạn kích thước.

## 12. Schema log tham khảo

Ví dụ một event thất bại:

~~~json
{
  "timestamp": "2026-11-16T10:20:30.125Z",
  "level": "WARN",
  "event": "jwt.validation.failed",
  "event_id": "evt-91d2",
  "request_id": "req-7f2a",
  "trace_id": "trace-12ab",
  "service": "orders-api",
  "environment": "production",
  "outcome": "rejected",
  "reason_code": "JWT_SIGNATURE_INVALID",
  "validation_stage": "signature",
  "issuer_profile_id": "customer-identity-prod",
  "token_profile": "access-token",
  "algorithm": "RS256",
  "key_id": "signing-2026-04",
  "jwks_cache": "hit",
  "http_status": 401,
  "duration_ms": 4
}
~~~

Đây là ví dụ schema, không phải yêu cầu phải ghi mọi field trong mọi hệ thống. Chỉ thêm field khi có mục đích vận hành/bảo mật rõ ràng và dữ liệu được phép lưu.

### 12.1. Nhóm field nên cân nhắc

| Nhóm | Field ví dụ | Mục đích |
| --- | --- | --- |
| Thời gian và định danh | timestamp, event_id, request_id, trace_id | Tương quan sự kiện và điều tra. |
| Thành phần | service, environment, region, instance_id | Xác định nơi xử lý. |
| Kết quả | outcome, http_status, reason_code, validation_stage | Hiểu request được chấp nhận hay từ chối. |
| Trust context | issuer_profile_id, token_profile, audience_profile_id | Xác định policy đã áp dụng. |
| Thuật toán/khóa | algorithm, key_id, jwks_cache, key_version_ref | Điều tra vấn đề khóa và rotation. |
| Caller | client_id hoặc workload identity đã xác thực, source_ip theo policy | Xác định caller và nguồn request. |
| Hiệu năng/dependency | duration_ms, dependency, dependency_status, retry_count | Theo dõi timeout và availability. |

Không phải tất cả field đều an toàn ở mọi môi trường. Ví dụ source_ip, client_id, sub hoặc tenant identifier có thể là dữ liệu cá nhân/nhạy cảm theo chính sách tổ chức. Cần đánh giá mục đích, quyền truy cập và retention.

## 13. Tuyệt đối không ghi credential và dữ liệu nhạy cảm vào log

Không ghi:

- Toàn bộ JWT compact string.
- Authorization header hoặc cookie chứa bearer token.
- Refresh token, API key, HMAC secret hoặc private JWK.
- RSA private parameters (d, p, q, dp, dq, qi), EC/OKP d, symmetric k.
- Private key export, key wrapping material hoặc KMS credentials.
- Raw signing input hoặc payload/header đầy đủ khi có claims nhạy cảm.
- Password, session secret, recovery code hoặc dữ liệu xác thực khác.

Bearer token là credential dạng possession: ai lấy được token có thể dùng token trong thời hạn và phạm vi còn hiệu lực. Ghi token vào log có thể biến log platform, SIEM, ticket, bản sao lưu hoặc hệ thống hỗ trợ thành nơi phát tán credential.

### 13.1. Có cần ghi sub, jti hoặc claims không?

Chỉ ghi khi có mục đích điều tra cụ thể, căn cứ chính sách và kiểm soát dữ liệu phù hợp. Thông thường:

- Dùng issuer_profile_id nội bộ thay cho raw iss.
- Dùng token_profile thay cho toàn bộ header/payload.
- Không ghi raw sub nếu không cần; có thể dùng định danh nội bộ giả danh hóa.
- Tránh ghi jti trực tiếp nếu nó cho phép liên kết hoạt động người dùng; chỉ lưu khi cơ chế revoke/incident cần.
- Không ghi scope đầy đủ nếu chứa permission nhạy cảm; có thể ghi nhóm policy hoặc số lượng scope.

### 13.2. Token fingerprint khi cần tương quan

Trong một số cuộc điều tra, cần biết nhiều request có dùng cùng một token hay không. Có thể lưu fingerprint thay cho token:

- Tính digest hoặc keyed digest trên token compact trong bộ nhớ.
- Chỉ ghi fingerprint đã rút gọn theo policy, không ghi token gốc.
- Không dùng fingerprint như một credential hoặc gửi nó cho client.
- Giới hạn quyền truy cập vì fingerprint vẫn cho phép liên kết các request với cùng một token.

Nếu dùng HMAC để tạo fingerprint, khóa HMAC phải là khóa logging riêng, không dùng JWT signing secret. Không cần lưu fingerprint nếu request ID hoặc dữ liệu tương quan khác đã đủ.

## 14. Làm sạch dữ liệu không tin cậy trước khi log

JWT header, payload, key ID, iss, Authorization header và các giá trị từ request đều có thể do attacker kiểm soát trước khi xác minh. Nếu ghi trực tiếp vào log, có thể gặp:

- Log injection qua newline, ký tự điều khiển hoặc chuỗi giả mạo field.
- Log forging làm sai lệch điều tra.
- Log flooding bằng chuỗi rất dài hoặc nhiều giá trị duy nhất.
- Tạo cardinality quá cao trong metrics/trace.
- Lộ dữ liệu nhạy cảm qua exception message.

Biện pháp:

1. Ưu tiên dùng ID đã ánh xạ từ registry tin cậy thay vì ghi raw issuer.
2. Nếu cần ghi key ID, giới hạn độ dài, chuẩn hóa hoặc encode an toàn và đánh dấu đó là giá trị chưa tin cậy.
3. Escape ký tự điều khiển và dùng structured logger có serializer an toàn.
4. Không nối trực tiếp dữ liệu request vào log line.
5. Giới hạn kích thước từng field và tổng event.
6. Không đưa raw token/header/payload vào exception hoặc debug log.
7. Không dùng giá trị do attacker gửi làm metric label không giới hạn.

Không dựa vào việc parser đã thành công để coi header/payload là dữ liệu đáng tin. Chỉ claims sau khi chữ ký và policy xác minh hợp lệ mới có thể được dùng trong logic nghiệp vụ; việc log chúng vẫn phải tuân theo data policy.

## 15. Correlation ID và trace

Correlation ID giúp kết nối response mà caller nhìn thấy với log nội bộ mà không tiết lộ nguyên nhân.

Một cách làm:

1. Gateway hoặc API edge tạo request ID nếu request chưa có ID đáng tin.
2. Nếu nhận ID từ caller, kiểm tra định dạng và giới hạn độ dài; không tin giá trị tùy ý.
3. Gắn request ID vào context của request và truyền qua các service theo trace propagation đã quy định.
4. Trả request ID hoặc trace ID công khai trong response header/body nếu API contract cho phép.
5. Ghi cùng ID trong log gateway, verifier và resource server.

Ví dụ:

~~~http
HTTP/1.1 401 Unauthorized
X-Request-ID: req-7f2a
WWW-Authenticate: Bearer realm="orders-api", error="invalid_token"
~~~

Caller có thể gửi req-7f2a cho đội hỗ trợ. Đội vận hành tra log theo ID để xem reason code nội bộ. Không cần gửi JWT_SIGNATURE_INVALID hoặc chi tiết key resolver ra response.

Không dùng request ID làm authentication credential. Tránh để caller có thể cố tình tái sử dụng ID để ghi đè hoặc làm lẫn log của request khác.

## 16. Severity, sampling và rate limiting log

Không phải mọi lỗi token đều cần cùng severity:

| Tình huống | Mức log tham khảo | Lý do |
| --- | --- | --- |
| Thiếu token ở endpoint bảo vệ | INFO hoặc metric | Có thể là hành vi client bình thường. |
| Token hết hạn / audience mismatch | INFO hoặc WARN tùy tần suất | Thường do client/config; cần phát hiện pattern bất thường. |
| Chữ ký sai lặp lại hoặc issuer lạ | WARN | Có thể là token giả hoặc cấu hình sai. |
| JWKS endpoint timeout | ERROR cho dependency event, không nhất thiết cho từng request | Một sự cố dependency có thể ảnh hưởng nhiều request. |
| Private key bị lộ / key policy thay đổi bất thường | CRITICAL hoặc alert security | Sự cố ảnh hưởng trust boundary. |
| Lỗi nội bộ không dự kiến | ERROR | Cần điều tra. |

Đây chỉ là mức tham khảo. Severity cần dựa trên tác động và tín hiệu, không chỉ dựa vào status code.

### 16.1. Tránh log storm

Attacker có thể gửi hàng triệu token sai để tạo lượng log lớn. Cần:

- Rate limit request và giới hạn log theo nguồn/route phù hợp.
- Gộp sự kiện lặp lại theo reason code và cửa sổ thời gian.
- Sampling các sự kiện phổ biến, nhưng giữ khả năng phát hiện đột biến.
- Giữ audit event bắt buộc cho thay đổi key/config và hành động quản trị.
- Không sampling theo cách làm mất toàn bộ bằng chứng của một incident nghiêm trọng.

Metrics có thể đếm mọi request mà không lưu một log chi tiết cho từng request. Dùng label có cardinality giới hạn như service, environment, outcome, reason category; không dùng raw key ID, sub, token, IP tùy ý làm label.

## 17. Bảo vệ hệ thống log và retention

Log xác minh JWT có thể chứa metadata về issuer, key ID, caller, IP và hành vi xác thực. Vì vậy, bản thân log cũng là dữ liệu cần bảo vệ.

- Phân quyền đọc log theo vai trò và nhu cầu công việc.
- Tách quyền ghi, đọc, xóa và quản trị retention.
- Dùng mã hóa khi truyền và khi lưu theo policy.
- Bảo vệ audit/security log khỏi sửa/xóa trái phép; cân nhắc immutable storage.
- Đồng bộ thời gian giữa các thành phần để timeline điều tra chính xác.
- Thiết lập retention theo yêu cầu pháp lý, vận hành và bảo mật; không lưu vô thời hạn theo mặc định.
- Có quy trình xóa hoặc pseudonymize dữ liệu khi hết mục đích lưu.
- Theo dõi việc truy cập log nhạy cảm và export log ra ngoài.

Không đưa log đầy đủ vào ticket, email hoặc chat hỗ trợ nếu không cần. Khi chia sẻ, chỉ trích xuất field cần thiết và loại bỏ token, claims, IP hoặc identifier nhạy cảm theo policy.

## 18. Metrics và cảnh báo vận hành

Log giải thích từng sự kiện; metrics cho thấy xu hướng và mức độ ảnh hưởng.

Các metric tham khảo:

| Metric | Ý nghĩa |
| --- | --- |
| jwt_validation_requests_total | Tổng request được đưa qua bước xác minh. |
| jwt_validation_failures_total | Số lần xác minh thất bại theo nhóm reason category. |
| jwt_validation_duration_seconds | Độ trễ xác minh. |
| jwks_fetch_requests_total | Số lần fetch/refresh JWKS. |
| jwks_fetch_failures_total | Số lỗi tải JWKS. |
| jwks_cache_age_seconds | Tuổi cache JWKS đang dùng. |
| jwt_unknown_kid_total | Số lần key ID không tìm thấy. |
| jwt_revoked_key_rejections_total | Số lần token bị chặn do key/credential bị thu hồi. |

Label nên có cardinality thấp: service, environment, issuer profile ID, token profile, outcome và reason category. Không dùng raw issuer, raw key ID, sub, jti, request ID hoặc token làm label.

### 18.1. Tín hiệu cảnh báo

- Tỷ lệ JWT_SIGNATURE_INVALID tăng đột biến.
- Nhiều key ID không tồn tại từ một nguồn request.
- JWKS fetch lỗi hoặc cache age vượt ngưỡng.
- Issuer lạ xuất hiện thường xuyên.
- Tỷ lệ 401 tăng mạnh sau một đợt rotation.
- KMS/HSM signing hoặc verification latency tăng bất thường.
- Có thay đổi key policy, JWKS URI hoặc issuer metadata ngoài cửa sổ triển khai.

Alert cần kèm service, environment, issuer profile và runbook. Không tạo alert riêng cho từng key ID tùy ý vì attacker có thể làm bùng nổ số lượng alert.

## 19. Ví dụ end-to-end: token hết hạn

Giả sử một client gọi API bằng access token đã hết hạn.

**Phía caller nhận:**

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="orders-api", error="invalid_token"
X-Request-ID: req-9a31
Content-Type: application/problem+json
~~~

~~~json
{
  "type": "about:blank",
  "title": "Unauthorized",
  "status": 401,
  "detail": "The access token is invalid or cannot be accepted."
}
~~~

**Log nội bộ:**

~~~json
{
  "timestamp": "2026-11-16T10:20:30.125Z",
  "level": "INFO",
  "event": "jwt.validation.failed",
  "request_id": "req-9a31",
  "service": "orders-api",
  "environment": "production",
  "outcome": "rejected",
  "reason_code": "JWT_EXPIRED",
  "validation_stage": "claims",
  "issuer_profile_id": "customer-identity-prod",
  "token_profile": "access-token",
  "http_status": 401,
  "duration_ms": 3
}
~~~

Caller biết token không được chấp nhận và có thể lấy token mới. Đội vận hành biết lý do nội bộ là JWT_EXPIRED, biết request nào và service nào xử lý. Log không cần chứa token, subject hoặc toàn bộ claims.

## 20. Ví dụ end-to-end: JWKS dependency không khả dụng

Giả sử token có key ID mới. Verifier đã thử refresh từ JWKS URI tin cậy nhưng endpoint timeout; cache hiện tại không chứa key đó và đã hết thời hạn tin cậy.

**Phía caller nhận:**

~~~http
HTTP/1.1 503 Service Unavailable
Retry-After: 30
X-Request-ID: req-4c88
Content-Type: application/problem+json
~~~

~~~json
{
  "type": "about:blank",
  "title": "Service Unavailable",
  "status": 503,
  "detail": "Authentication is temporarily unavailable. Please retry later."
}
~~~

**Log dependency nội bộ:**

~~~json
{
  "timestamp": "2026-11-16T10:25:00.000Z",
  "level": "ERROR",
  "event": "jwks.fetch.failed",
  "request_id": "req-4c88",
  "service": "orders-api",
  "environment": "production",
  "issuer_profile_id": "customer-identity-prod",
  "dependency": "trusted-jwks",
  "reason_code": "JWKS_FETCH_FAILED",
  "failure_class": "timeout",
  "cache_state": "stale",
  "cache_age_seconds": 9200,
  "http_status": 503
}
~~~

Verifier từ chối request vì không có khóa tin cậy để xác minh. Nó không ghi nhận token là JWT_SIGNATURE_INVALID, vì phép kiểm tra chữ ký chưa thể diễn ra. Caller không cần biết endpoint hoặc hạ tầng nội bộ nào bị lỗi.

## 21. Ví dụ end-to-end: token hợp lệ nhưng thiếu scope

Giả sử chữ ký và claims hợp lệ, nhưng token không có scope cần thiết cho thao tác xóa đơn hàng.

**Phía caller nhận:**

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer realm="orders-api", error="insufficient_scope"
X-Request-ID: req-2b71
Content-Type: application/problem+json
~~~

~~~json
{
  "type": "about:blank",
  "title": "Forbidden",
  "status": 403,
  "detail": "The access token does not grant permission for this operation."
}
~~~

**Log nội bộ:**

~~~json
{
  "timestamp": "2026-11-16T10:27:11.500Z",
  "level": "INFO",
  "event": "authorization.denied",
  "request_id": "req-2b71",
  "service": "orders-api",
  "outcome": "denied",
  "reason_code": "AUTH_SCOPE_INSUFFICIENT",
  "token_profile": "access-token",
  "policy_id": "orders.delete",
  "http_status": 403
}
~~~

Sự kiện này không phải JWT validation failure. Chữ ký đã hợp lệ; quyết định từ chối nằm ở authorization policy.

## 22. Kiểm thử response và log

Kiểm thử cần xác nhận cả hành vi giao thức lẫn việc không rò rỉ dữ liệu.

| Ca kiểm thử | Response mong đợi | Kiểm tra log |
| --- | --- | --- |
| Không có bearer token | 401, challenge không có error code | Không ghi Authorization header; reason AUTH_HEADER_MISSING. |
| Authorization header malformed | 400, invalid_request khi phù hợp | Ghi reason code, không ghi raw header. |
| JWT malformed | 401, invalid_token | Không ghi token hoặc payload. |
| Chữ ký sai | 401, invalid_token | Reason JWT_SIGNATURE_INVALID; không ghi signature/signing input. |
| Issuer/audience sai | 401, invalid_token | Ghi issuer profile ID/reason code, không ghi claims đầy đủ. |
| Token hết hạn | 401, invalid_token | Reason JWT_EXPIRED, không ghi toàn bộ JWT. |
| Thiếu scope | 403, insufficient_scope | Event authorization denied, policy ID an toàn. |
| JWKS unavailable và cache stale | 503 theo policy | Dependency event, cache age và timeout; không phân loại chữ ký sai. |
| Verifier config lỗi | 500 | Reason VALIDATION_CONFIG_ERROR, không trả stack trace. |
| Request ID chứa newline/chuỗi dài | Response ID hợp lệ hoặc ID mới | Không tạo log forging; field bị giới hạn/escape. |
| JWT chứa key ID cực dài hoặc ký tự điều khiển | 401 nếu không hợp lệ | Không log raw value; không tạo cardinality vô hạn. |
| Nhiều token sai liên tục | Status theo rate limit/policy | Log được gộp/sampling, metrics vẫn phản ánh xu hướng. |

### 22.1. Kiểm tra redaction tự động

Có thể tạo test dùng token giả có marker dễ nhận diện, ví dụ DO_NOT_LOG_TOKEN_123, rồi gửi request qua mọi đường lỗi. Quét log output và bảo đảm marker, Authorization header, private key placeholder và raw payload không xuất hiện.

Kiểm tra cả:

- Application log.
- API gateway/access log.
- Reverse proxy/load balancer log.
- Distributed trace và span attributes.
- Error reporting/crash telemetry.
- Audit export và hệ thống hỗ trợ.

Redaction chỉ ở application logger là chưa đủ nếu gateway hoặc APM đang ghi toàn bộ header.

## 23. Những anti-pattern cần tránh

| Anti-pattern | Rủi ro | Cách xử lý |
| --- | --- | --- |
| Trả “signature invalid”, “unknown key ID”, “issuer not trusted” cho caller | Tiết lộ chi tiết trust/key resolver và hỗ trợ dò cấu hình. | Gom vào invalid_token; giữ reason code trong log nội bộ. |
| Trả 401 cho lỗi JWKS/KMS timeout | Client có thể refresh token vô ích; che giấu sự cố dependency. | Phân loại availability và dùng 503 theo policy. |
| Trả 403 cho token hết hạn | Nhầm authentication với authorization. | Dùng 401 cho token không hợp lệ. |
| Ghi toàn bộ JWT hoặc Authorization header | Log trở thành kho bearer credential có thể replay. | Không log token; dùng request ID hoặc fingerprint khi thật sự cần. |
| Ghi raw exception message | Có thể lộ URL, key ID, claims, stack hoặc dữ liệu đầu vào. | Map exception sang reason code nội bộ ổn định. |
| Log raw key ID, issuer, subject không giới hạn | Log injection, PII exposure, cardinality và log flooding. | Ánh xạ ID tin cậy, sanitize, truncate và kiểm soát dữ liệu. |
| Dùng cùng error body cho mọi lỗi | Caller không biết nên lấy token mới, bổ sung quyền hay thử lại. | Phân biệt invalid token, insufficient scope và dependency unavailable. |
| Ghi mọi lỗi ở mức ERROR | Alert fatigue và khó nhận diện sự cố thật. | Chọn severity theo tác động và pattern. |
| Không có correlation ID | Khó nối response với log nhiều service. | Sinh/kiểm tra request ID và truyền qua trace. |
| Dùng raw reason code làm public API contract | Lộ nội bộ và khó thay đổi implementation. | Tách public error code khỏi internal reason code. |

## 24. Checklist thiết kế

**Response bên ngoài**

- [ ] Thiếu token, token invalid, thiếu quyền và dependency failure được phân loại riêng.
- [ ] HTTP status và Bearer challenge nhất quán với giao thức.
- [ ] invalid_token không tiết lộ chi tiết chữ ký, issuer, key ID hoặc cache.
- [ ] insufficient_scope chỉ công bố scope được phép.
- [ ] Lỗi dependency không bị trả như token invalid.
- [ ] Response không chứa stack trace, URL nội bộ, secret hoặc claims nhạy cảm.
- [ ] Có request/correlation ID để hỗ trợ điều tra.

**Log nội bộ**

- [ ] Có event name, timestamp, outcome, reason code và validation stage.
- [ ] Có service/environment/issuer profile/token profile phù hợp.
- [ ] Có request ID/trace ID và thông tin dependency cần thiết.
- [ ] Không ghi JWT, Authorization header, refresh token, private key hoặc HMAC secret.
- [ ] Dữ liệu không tin cậy được sanitize, escape và giới hạn kích thước.
- [ ] Không dùng dữ liệu attacker kiểm soát làm metric label cardinality cao.
- [ ] Severity, sampling và rate limit được xác định.

**Vận hành và kiểm thử**

- [ ] Log có RBAC, retention, encryption và audit truy cập.
- [ ] Có metrics/alert cho invalid signature, unknown key ID, JWKS outage và cache stale.
- [ ] Có test cho 400/401/403/429/500/503 theo các tình huống phù hợp.
- [ ] Có test đảm bảo token và claims nhạy cảm không xuất hiện trong log/trace.
- [ ] Có runbook xử lý dependency outage, key rotation và credential compromise.

## 25. Tài liệu chuẩn tham khảo

- [RFC 6750 — The OAuth 2.0 Authorization Framework: Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): Bearer challenge, invalid_request, invalid_token, insufficient_scope và status code.
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110): ý nghĩa HTTP status như 400, 401, 403, 429, 500 và 503.
- [RFC 9457 — Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457): định dạng response lỗi chuẩn hóa.
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519): cấu trúc JWT và claims.
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): xác minh JWT an toàn, issuer/audience và giới hạn thuật toán.
- [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): dữ liệu cần loại khỏi log, chống log injection và bảo vệ nhật ký.
- [OWASP REST Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/REST_Security_Cheat_Sheet.html): xử lý lỗi và thực hành bảo mật REST API.

**Ghi nhớ:** caller cần status và thông điệp ổn định; đội vận hành cần reason code và ngữ cảnh có cấu trúc. Dùng 401 cho token không hợp lệ, 403 cho token hợp lệ nhưng thiếu quyền, và phân loại dependency outage riêng. Không bao giờ biến log thành nơi lưu bearer token hoặc private material.
