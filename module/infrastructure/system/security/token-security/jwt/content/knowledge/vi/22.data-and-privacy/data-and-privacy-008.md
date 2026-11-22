# Che giấu token khi gỡ lỗi và sử dụng dữ liệu mẫu

JWT access token, refresh token, ID Token và session credential đều là dữ liệu nhạy cảm. Khi chúng xuất hiện trong log, ảnh chụp màn hình, trace, ticket hỗ trợ hoặc ví dụ tài liệu, người có quyền đọc những nơi đó có thể lấy credential và sử dụng chúng. Gỡ lỗi an toàn vì vậy phải bắt đầu từ nơi dữ liệu được thu thập, chỉ ghi những trường thực sự cần thiết và thay credential bằng giá trị giả đã được kiểm soát.

Bài học thuộc chương **Dữ liệu và riêng tư** của module **Security – JSON Web Token (JWT)**. Nội dung hướng dẫn che giấu token trong log và công cụ quan sát, phân biệt masking với pseudonymization, tạo dữ liệu mẫu không chứa bí mật thật, và xây dựng quy trình debug/test an toàn cho mọi ngôn ngữ, runtime và nền tảng.

## 1. Vì sao token phải được che giấu khi debug?

Bearer token là credential: bất kỳ bên nào sở hữu token còn hiệu lực đều có thể thử sử dụng nó trong phạm vi quyền được cấp. Token có thể xuất hiện ngoài nơi lưu trữ chính thức trong nhiều tình huống:

- HTTP request/response logging tại client, gateway, reverse proxy hoặc resource server.
- Distributed tracing, APM, telemetry và error reporting.
- Exception message, crash dump, diagnostic bundle và support bundle.
- Browser developer tools, console output, mobile device logs.
- CI/CD output, test report, build artifact và pipeline variable dump.
- Ticket hỗ trợ, chat nội bộ, email, ảnh chụp màn hình và tài liệu kỹ thuật.
- Database audit, analytics event, message queue và bản ghi replay.

Một token bị ghi vào log có thể tồn tại lâu hơn token trong ứng dụng vì log được sao chép, lập chỉ mục, backup và chia sẻ giữa nhiều hệ thống. Thu hồi token có thể giảm khả năng sử dụng về sau, nhưng không xóa được mọi bản sao đã lưu.

### 1.1. JWT không đồng nghĩa với dữ liệu bí mật đã được mã hóa

JWS thường bảo vệ tính toàn vẹn và nguồn phát hành bằng chữ ký/MAC. Payload của JWS Compact có thể được giải mã Base64url và đọc mà không cần khóa bí mật. Vì vậy, không đưa PII, credential hoặc dữ liệu nghiệp vụ nhạy cảm vào payload với giả định rằng chỉ người có khóa mới đọc được.

JWE có mã hóa nội dung, nhưng toàn bộ JWE vẫn là credential cần bảo vệ. Người có JWE access token hợp lệ vẫn có thể sử dụng nó theo chính sách của resource server.

Nguyên tắc:

- Không log raw JWT, dù token là JWS hay JWE.
- Không log toàn bộ payload chỉ để xem một claim.
- Không cho rằng che phần signature là đủ; header và payload vẫn có thể chứa thông tin nhạy cảm.
- Không cho rằng token hết hạn thì log chứa token trở nên vô hại.
- Không dùng token thật trong tài liệu, ảnh chụp, ví dụ hoặc test fixture.

## 2. Xác định dữ liệu nào phải được bảo vệ

Không chỉ trường có tên token mới là bí mật. Cần nhận diện credential theo ngữ cảnh và tên trường.

| Dữ liệu | Mức độ nhạy cảm | Cách xử lý khi log/debug |
| --- | --- | --- |
| Access token/JWT | Rất nhạy cảm | Không ghi giá trị; redact toàn bộ |
| Refresh token | Rất nhạy cảm | Không ghi giá trị; redact toàn bộ |
| ID Token | Nhạy cảm | Không ghi raw token; claims có thể chứa PII |
| Authorization header | Rất nhạy cảm | Redact toàn bộ header value |
| Cookie/Set-Cookie chứa session | Rất nhạy cảm | Redact giá trị cookie |
| Client secret/private key | Rất nhạy cảm | Không ghi; quản lý trong secret store |
| Authorization code | Rất nhạy cảm | Redact; code có thể đổi lấy token |
| Password/OTP/recovery code | Rất nhạy cảm | Không ghi giá trị |
| sub, email, phone, tenant ID | Dữ liệu nhận diện | Chỉ ghi khi cần và theo chính sách riêng tư |
| iss, aud, scope, typ | Metadata bảo mật | Có thể ghi allowlist nếu không tiết lộ thông tin nhạy cảm |
| exp, iat, nbf | Metadata thời gian | Có thể ghi khi phục vụ chẩn đoán |
| jti, sid | Định danh token/phiên | Xem là dữ liệu nhạy cảm có thể liên kết; hạn chế và pseudonymize nếu cần |

Danh sách trên là điểm khởi đầu. Mỗi hệ thống cần lập data inventory cho header, cookie, body, query parameter, claim, log field và telemetry attribute mà nó thực sự sử dụng.

### 2.1. Không log toàn bộ claims để thuận tiện

Payload có thể chứa:

- Email, tên, số điện thoại hoặc mã nhân viên.
- Tenant, nhóm, role và permission.
- Định danh phiên hoặc định danh liên kết tài khoản.
- Dữ liệu về thiết bị, vị trí hoặc phương thức xác thực.
- Thông tin nghiệp vụ mà người đọc log không cần biết.

Nếu cần xác minh token được ánh xạ đúng, chỉ ghi những metadata đã được allowlist và tối thiểu hóa. Ví dụ có thể ghi issuer profile, audience đã chuẩn hóa, quyết định scope và kết quả validation thay vì dump toàn bộ claims.

## 3. Che giấu, loại bỏ và pseudonymization khác nhau

Các kỹ thuật bảo vệ dữ liệu có mục đích khác nhau. Không gọi chung tất cả là mask token.

| Kỹ thuật | Cách hoạt động | Có thể khôi phục dữ liệu gốc? | Ví dụ phù hợp |
| --- | --- | --- | --- |
| Redaction | Loại bỏ giá trị nhạy cảm khỏi bản ghi | Không từ bản ghi đã redact | Authorization: [REDACTED] |
| Masking | Thay một phần giá trị bằng ký tự che | Có thể lộ một phần dữ liệu | user-****42 |
| Pseudonymization | Thay định danh bằng mã giả có thể liên kết theo cơ chế được kiểm soát | Có thể liên kết lại nếu có khóa/bảng ánh xạ | HMAC subject ID |
| Anonymization | Biến dữ liệu để không còn khả năng nhận diện hợp lý | Không nên khôi phục được | Thống kê tổng hợp đủ lớn |
| Synthetic data | Tạo dữ liệu mới, không lấy bí mật thật làm đầu vào | Không có bản gốc tương ứng | User, tenant và JWT giả cho test |

Với bearer token, **redaction toàn bộ** là lựa chọn mặc định. Masking một phần như giữ 8 ký tự đầu/cuối vẫn tạo ra một định danh ổn định, có thể giúp liên kết bản ghi và có thể tiết lộ thông tin không cần thiết. Chỉ dùng fingerprint khi có mục đích điều tra cụ thể và đã đánh giá rủi ro.

### 3.1. Redaction

Ví dụ trước khi redaction:

~~~http
Authorization: Bearer <SYNTHETIC_TOKEN_VALUE>
~~~

Ví dụ sau khi redaction:

~~~http
Authorization: [REDACTED]
~~~

Không chỉ xóa chữ Bearer; phải xóa toàn bộ giá trị credential. Nếu chỉ ghi [REDACTED] ở dashboard nhưng raw value vẫn được lưu trong storage, pipeline vẫn đang giữ bí mật.

### 3.2. Masking một phần không phải biện pháp mặc định cho token

Ví dụ một giá trị bị che một phần:

~~~text
eyJhbGci...signature
~~~

Giá trị rút gọn vẫn có thể:

- Cho phép tương quan request qua nhiều hệ thống.
- Tiết lộ header/payload hoặc cấu trúc token.
- Tạo điều kiện tìm token trong bản ghi khác.
- Bị ghép với dữ liệu khác để nhận diện credential.

Với token, không cần giữ prefix/suffix để debug thông thường. Hãy ghi request ID, issuer profile, kết quả validation hoặc fingerprint có khóa nếu thực sự cần tương quan.

### 3.3. Pseudonymization bằng HMAC fingerprint

Nếu cần biết hai sự kiện có liên quan đến cùng một token mà không lưu token, có thể tính fingerprint bằng HMAC với khóa riêng cho mục đích logging:

~~~text
token_fingerprint = HMAC-SHA-256(logging_key, raw_token)
~~~

HMAC fingerprint không phải token thay thế và không được gửi tới resource server. Nó chỉ là mã tương quan trong log.

Yêu cầu:

- Dùng khóa HMAC riêng cho logging, không tái sử dụng signing key, encryption key hoặc client secret.
- Giữ khóa trong secret manager và giới hạn người có quyền sử dụng.
- Không log khóa HMAC.
- Đánh giá việc fingerprint có tạo khả năng liên kết người dùng/phiên qua nhiều hệ thống hay không.
- Có rotation và retention cho khóa/fingerprint.
- Không dùng fingerprint thay cho redaction của raw token.

Không cần fingerprint trong phần lớn log vận hành. Request ID hoặc trace ID thường đủ để nối các sự kiện của một request.

## 4. Redaction phải diễn ra ở đâu?

Redaction tốt nhất được thực hiện **trước khi dữ liệu nhạy cảm đi vào log, trace hoặc telemetry exporter**. Chỉ che ở giao diện xem log là chưa đủ vì raw value có thể vẫn nằm trong backend storage, index, archive hoặc bản sao.

~~~mermaid
flowchart LR
    A["HTTP request / token"] --> B["Instrumentation tại nguồn"]
    B --> C["Allowlist và redaction"]
    C --> D["Structured log / trace"]
    D --> E["Collector / exporter"]
    E --> F["Log/APM storage"]
    F --> G["Dashboard / support"]
    X["Raw credential"] -. "Không được đi vào" .-> D
~~~

### 4.1. Những lớp cần kiểm tra

| Lớp | Dữ liệu có thể bị ghi | Việc cần làm |
| --- | --- | --- |
| Client/browser | Console, network capture, local diagnostic | Không log token; scrub dữ liệu trước khi gửi báo cáo |
| Mobile app | Device log, crash report, analytics | Redact header/credential; kiểm soát diagnostic bundle |
| CDN/WAF/load balancer | Request header, URL, query | Tắt log header nhạy cảm; redact query chứa credential |
| API gateway/reverse proxy | Authorization, Cookie, upstream headers | Cấu hình field-level redaction trước access log |
| Resource service | Request dump, exception, debug log | Structured logging với allowlist |
| Service mesh | Proxy access log và trace attribute | Redact header ở proxy sidecar/gateway |
| APM/tracing | Span attributes, baggage, request capture | Không đưa credential vào span/baggage |
| Error tracker | Breadcrumb, request context, stack context | Scrub trước khi gửi và kiểm tra dữ liệu lưu |
| CI/CD | Env dump, command output, test report | Mask secret và không in request header |
| Support workflow | Ticket, chat, screenshot | Chỉ chia sẻ dữ liệu synthetic hoặc đã scrub |

### 4.2. Redact ở nguồn và ở collector

Nên có nhiều lớp bảo vệ:

1. Ứng dụng không tạo log chứa credential ngay từ đầu.
2. HTTP instrumentation xóa header/cookie nhạy cảm trước khi serialize.
3. Proxy/gateway redaction để bảo vệ request capture ở biên.
4. Collector áp dụng thêm quy tắc phòng thủ nếu dữ liệu nhạy cảm lọt qua.
5. Dashboard giới hạn quyền truy cập và retention.

Collector-side redaction là lớp dự phòng, không phải lý do để ứng dụng tiếp tục ghi raw token.

## 5. Dùng allowlist thay vì log tất cả rồi cố redact

Denylist redaction chỉ che các trường đã biết. Một trường mới như session_credential, jwt_value hoặc delegation_token có thể lọt qua nếu nhóm phát triển quên thêm quy tắc.

Với structured logging, ưu tiên allowlist các trường được phép ghi:

~~~json
{
  "event": "jwt.validation",
  "request_id": "req-7f31",
  "issuer_profile": "corporate",
  "audience": "https://billing-api.example",
  "token_type": "access_token",
  "signature_valid": true,
  "time_valid": true,
  "scope_decision": "invoice:read",
  "authorization_result": "allowed",
  "duration_ms": 8
}
~~~

Ví dụ này không chứa raw JWT, Authorization header, refresh token hoặc toàn bộ claims. Tên issuer profile và audience chỉ nên được ghi khi chúng không làm lộ cấu hình nhạy cảm.

### 5.1. Những trường nên loại bỏ theo mặc định

~~~text
authorization
proxy-authorization
cookie
set-cookie
access_token
refresh_token
id_token
token
client_secret
client_assertion
assertion
password
otp
recovery_code
authorization_code
private_key
~~~

Đây không phải danh sách đầy đủ. Tên trường có thể khác nhau giữa API và ứng dụng; cần dựa trên data inventory và kiểm thử thực tế.

### 5.2. Không chỉ kiểm tra tên trường

Credential có thể nằm trong:

- Header Authorization hoặc header tùy chỉnh.
- Cookie hoặc Set-Cookie.
- Query string và path.
- JSON/form body.
- Nested object hoặc array.
- Exception message do thư viện tạo.
- Trace baggage hoặc custom span attribute.
- URL redirect hoặc Referer.

Không dựa vào một regex duy nhất để bảo vệ mọi định dạng. Nên parse cấu trúc request theo giao thức, xác định vị trí credential và loại bỏ trường trước khi log.

## 6. Ví dụ log an toàn khi xác minh JWT

### 6.1. Log không an toàn

~~~json
{
  "message": "JWT validation failed",
  "authorization": "Bearer <REAL_TOKEN_WOULD_BE_HERE>",
  "decoded_payload": {
    "sub": "real-user-identifier",
    "email": "person@example.com",
    "role": "billing-admin",
    "tenant": "customer-17"
  }
}
~~~

Vấn đề:

- Raw bearer token có thể bị phát lại.
- Email và subject bị ghi vào log.
- Role và tenant có thể tiết lộ cấu trúc quyền và khách hàng.
- Người đọc log có thể không cần các dữ liệu này để chẩn đoán lỗi.

### 6.2. Log đã tối thiểu hóa

~~~json
{
  "event": "jwt.validation",
  "request_id": "req-7f31",
  "issuer_profile": "corporate",
  "validation_stage": "signature",
  "result": "rejected",
  "failure_code": "invalid_signature",
  "duration_ms": 4
}
~~~

Nếu cần biết lỗi ở claim nào, ghi mã lỗi có kiểm soát như expired, wrong_audience, unknown_issuer hoặc invalid_signature. Không đưa token, payload nguyên vẹn hoặc exception chứa credential vào message.

### 6.3. Tránh ghi chi tiết quá mức trong response

Thông báo cho client nên đủ để xử lý, nhưng không cần trả:

- Raw token hoặc một phần token.
- Public/private key material.
- Toàn bộ payload.
- Nội dung claim nhạy cảm.
- Chi tiết nội bộ của JWKS lookup hoặc issuer registry.

Có thể trả mã lỗi chung và dùng request ID để nhóm vận hành tra cứu log đã được scrub.

## 7. Tạo JWT mẫu an toàn cho tài liệu và kiểm thử

Dữ liệu mẫu nên được tạo mới cho mục đích minh họa. Không lấy token từ production, staging có dữ liệu thật hoặc tài khoản nhân viên/khách hàng rồi thay vài ký tự.

### 7.1. Quy tắc tạo dữ liệu synthetic

- Dùng subject giả như demo-user-01, không dùng email/tên thật.
- Dùng tenant giả như demo-tenant.
- Dùng domain dành cho ví dụ như identity.example hoặc api.example.
- Dùng scope và role giả có phạm vi nhỏ.
- Dùng thời gian cố định trong test hoặc clock giả lập.
- Không nhúng dữ liệu cá nhân, mã khách hàng, số điện thoại hoặc thông tin giao dịch thật.
- Không dùng private key, shared secret hoặc signing key production.
- Đặt fixture trong test environment tách biệt và không đưa vào runtime production.

Ví dụ payload synthetic:

~~~json
{
  "iss": "https://identity.example",
  "sub": "demo-user-01",
  "aud": "https://api.example",
  "scope": "profile:read",
  "tenant": "demo-tenant",
  "iat": 2000000000,
  "nbf": 2000000000,
  "exp": 2000000300,
  "jti": "demo-token-0001"
}
~~~

Đây là payload minh họa, không phải token đã ký và không đại diện cho một tài khoản thật. Timestamp cố định phù hợp cho test có clock được kiểm soát; không dùng nó như giá trị mặc định trong production.

### 7.2. Placeholder rõ ràng cho tài liệu

Khi tài liệu chỉ cần cho thấy vị trí token trong request, dùng placeholder không thể bị hiểu nhầm là credential:

~~~http
GET /v1/profile HTTP/1.1
Host: api.example
Authorization: Bearer <SYNTHETIC_ACCESS_TOKEN>
~~~

Không dùng token thật đã bị mask một phần làm ví dụ. Không copy token từ browser developer tools rồi sửa payload; token gốc có thể vẫn còn trong clipboard, undo history, ảnh chụp hoặc file tạm.

### 7.3. Fixture JWT nên được tạo trong test environment

Nếu test cần một JWT có chữ ký hợp lệ:

1. Dùng issuer và audience riêng cho test.
2. Sinh key test ngẫu nhiên, tách biệt với mọi môi trường khác.
3. Chỉ cấu hình public key tương ứng trong verifier test.
4. Giới hạn thời gian sống và quyền của token test.
5. Không chia sẻ key test với production hoặc staging.
6. Hủy/rotate key test theo vòng đời fixture.
7. Đảm bảo production không tin test issuer hoặc test key.

Một fixture có chữ ký hợp lệ chỉ hợp lệ trong test profile. Không đưa private key hoặc HMAC secret cố định vào repository với suy nghĩ “đây chỉ là test”; nếu production vô tình tin cùng key/issuer, fixture có thể trở thành credential được chấp nhận.

## 8. Dùng dữ liệu mẫu cho các tình huống kiểm thử

Một bộ fixture tốt nên bao phủ cả trường hợp hợp lệ và lỗi, nhưng mọi giá trị đều phải synthetic.

| Fixture | Mục tiêu | Dữ liệu mẫu |
| --- | --- | --- |
| Valid access token | Luồng thành công | demo-user-01, audience API test, scope profile:read |
| Expired token | Kiểm tra expiration | exp nằm trước test clock |
| Not-yet-valid token | Kiểm tra nbf | nbf nằm sau test clock |
| Wrong audience | Kiểm tra resource boundary | aud là https://other-api.example |
| Unknown issuer | Kiểm tra trust registry | iss là https://untrusted.example |
| Invalid signature | Kiểm tra integrity | Token ký bằng test key không nằm trong registry |
| Missing claim | Kiểm tra schema | Bỏ exp hoặc sub theo profile test |
| Wrong claim type | Kiểm tra parser | exp là string thay vì number |
| Oversized token | Kiểm tra giới hạn đầu vào | Payload synthetic lớn có kiểm soát |
| PII redaction | Kiểm tra log scrubber | Email/phone giả được đánh dấu test-only |

Không dùng credential production làm fixture cho negative test. Token thật có thể vô tình được gửi tới endpoint thật nếu cấu hình môi trường bị sai.

### 8.1. Tách biệt test data với môi trường production

- Dùng issuer, audience, JWKS và key riêng.
- Tách secret store và quyền truy cập.
- Tách endpoint, network route và account.
- Chặn production gọi test authorization server hoặc ngược lại.
- Dùng guard trong deployment để phát hiện test issuer/key trong cấu hình production.
- Không đưa test token vào sample config có thể được copy nguyên trạng sang production.

## 9. Debug an toàn theo từng tình huống

### 9.1. Khi token không xác minh được

Không in toàn bộ token để tìm lỗi. Ghi:

- Request ID hoặc trace ID.
- Issuer profile đã chọn (nếu đã xác định an toàn).
- Giai đoạn lỗi: parse, key lookup, signature, issuer, audience, time, schema.
- Mã lỗi đã chuẩn hóa.
- Key ID nếu policy cho phép; không ghi key material.
- Phiên bản cấu hình/validator.

Nếu cần tái hiện, tạo fixture synthetic có cùng loại lỗi: sai chữ ký, sai audience, hết hạn hoặc thiếu claim.

### 9.2. Khi cần kiểm tra claims

Không dump toàn bộ payload. Chỉ xem các claim allowlist cần thiết, ưu tiên giá trị synthetic hoặc đã pseudonymize. Ví dụ có thể ghi audience_match=false thay vì log toàn bộ aud.

Nếu phải kiểm tra dữ liệu cá nhân trong một sự cố thật, dùng quy trình truy cập dữ liệu có phê duyệt, giới hạn người xem, mục đích, thời gian và audit. Không đưa dữ liệu đó vào log thông thường hoặc ticket rộng quyền.

### 9.3. Khi cần tái hiện request

Tạo request mẫu mới:

~~~http
GET /v1/invoices/demo-invoice-01 HTTP/1.1
Host: billing-api.example
Authorization: Bearer <SYNTHETIC_ACCESS_TOKEN>
X-Request-ID: req-demo-0001
Accept: application/json
~~~

Không export HAR, curl command hoặc Postman collection có credential thật rồi gửi nguyên bản cho người khác. Trước khi chia sẻ, scrub header, cookie, query, body và URL; tốt nhất tái tạo request bằng dữ liệu synthetic.

## 10. Những nguồn rò rỉ thường bị bỏ sót

### 10.1. Browser và mobile diagnostics

- Browser console có thể ghi request object hoặc response object chứa header.
- HAR file có thể chứa Authorization, Cookie và query string.
- Screenshot có thể hiển thị token trong network panel.
- Mobile crash report có thể đính kèm request metadata hoặc memory context.
- Clipboard, autofill, recent apps và backup có thể giữ dữ liệu ngoài dự kiến.

Chỉ chia sẻ diagnostic bundle sau khi scrub và kiểm tra thủ công. Tắt hoặc giới hạn network capture trong môi trường production.

### 10.2. CI/CD và test output

- Shell trace hoặc verbose mode có thể in command chứa token.
- Environment dump có thể in biến bí mật.
- Test assertion có thể in toàn bộ request khi thất bại.
- Snapshot test có thể lưu header và payload.
- Build artifact có thể chứa file cấu hình, fixture hoặc request dump.

Masking của CI/CD chỉ là lớp hỗ trợ. Tránh đưa secret vào command line hoặc output; dùng secret injection phù hợp, tắt shell tracing và kiểm tra artifact trước khi lưu.

### 10.3. Proxy, APM và tracing baggage

Một ứng dụng có thể redact access log nhưng APM agent vẫn tự thu thập request header. Distributed tracing baggage có thể được truyền qua nhiều service và lưu trong span.

- Tắt capture header nhạy cảm.
- Không thêm token vào baggage hoặc span attribute.
- Kiểm tra sampling/debug mode có bật request/response body capture hay không.
- Xác nhận redaction xảy ra trước export.
- Kiểm tra cả trace được lưu, bản sao archive và dữ liệu gửi tới vendor.

## 11. Quy trình xử lý khi token thật đã bị lộ

Nếu raw token xuất hiện trong log, ticket, screenshot hoặc diagnostic bundle, hãy coi đó là sự cố credential exposure. Xóa bản ghi khỏi giao diện không đảm bảo các bản sao đã biến mất.

Quy trình cơ bản:

1. **Xác định loại credential:** access token, refresh token, ID Token, authorization code hay client secret.
2. **Đánh giá khả năng sử dụng:** token còn hạn không, audience nào, scope nào, có sender-constrained không.
3. **Giảm khả năng lạm dụng:** thu hồi token/grant hoặc phiên liên quan theo khả năng của hệ thống; rotate secret/key nếu bị lộ.
4. **Khoanh vùng bản sao:** log index, archive, trace, ticket, chat, artifact, backup và bản tải xuống.
5. **Hạn chế truy cập:** khóa quyền đọc hoặc chia sẻ những bản ghi có credential.
6. **Làm sạch theo retention policy:** xử lý bản sao theo quy trình xóa/retention và yêu cầu pháp lý áp dụng.
7. **Điều tra sử dụng trái phép:** kiểm tra audit event bằng request ID, token fingerprint có khóa hoặc metadata an toàn.
8. **Sửa nguồn phát sinh:** cấu hình redaction ở instrumentation, proxy, collector và test pipeline.
9. **Kiểm thử hồi quy:** tạo canary synthetic token và xác nhận không có nơi nào ghi raw value.

Không paste token thật vào công cụ phân tích, chatbot, issue tracker hoặc hệ thống bên ngoài để “kiểm tra xem token có còn hiệu lực”. Nếu cần xác minh, dùng validator nội bộ được kiểm soát và quy trình incident response.

## 12. Kiểm thử redaction

Redaction cần được kiểm thử giống một kiểm soát bảo mật, không chỉ kiểm tra bằng mắt trên dashboard.

### 12.1. Test các vị trí credential

| Vị trí | Dữ liệu test | Kết quả mong đợi |
| --- | --- | --- |
| Authorization header | Bearer synthetic token | Header value được redact hoàn toàn |
| Proxy-Authorization | Synthetic credential | Value được redact |
| Cookie | Session cookie giả | Cookie value được redact |
| Set-Cookie | Session cookie giả | Secret value không xuất hiện trong log |
| Query string | access_token=synthetic | Query value bị loại bỏ hoặc redact |
| JSON body | refresh_token trong nested object | Trường nhạy cảm bị redact |
| Exception | Error message có token giả | Token không xuất hiện trong error report |
| Trace span | Header/token attribute giả | Attribute bị loại bỏ trước export |
| CI output | Secret test marker | Marker không xuất hiện trong output/artifact |
| Screenshot/HAR | Request có synthetic credential | File chia sẻ không chứa raw value |

### 12.2. Dùng canary synthetic secret

Có thể tạo một chuỗi canary riêng cho test, ví dụ:

~~~text
CANARY_SECRET_DO_NOT_LOG_7F31A9
~~~

Đưa canary vào từng vị trí test có kiểm soát, chạy request qua toàn bộ pipeline rồi tìm canary trong:

- Application logs.
- Proxy/gateway logs.
- Trace/APM storage.
- Error reports.
- CI output và test artifacts.
- Diagnostic bundles.

Kết quả đạt yêu cầu khi raw canary không xuất hiện ở bất kỳ nơi lưu log nào; chỉ có placeholder đã redact hoặc sự kiện kiểm tra an toàn.

Canary chỉ là dữ liệu giả, không dùng chuỗi này làm credential thật. Không chạy test canary trên hệ thống production nếu chưa có kế hoạch và phê duyệt vận hành phù hợp.

### 12.3. Kiểm tra allowlist

Khi thêm một field mới vào structured log:

1. Mặc định field không được ghi.
2. Chủ sở hữu dữ liệu xác định mục đích và độ nhạy.
3. Field được review và thêm vào allowlist nếu thực sự cần.
4. Test xác nhận field không chứa token/PII ngoài dự kiến.
5. Theo dõi thay đổi schema và kiểm tra collector/downstream consumer.

## 13. Checklist gỡ lỗi và dữ liệu mẫu an toàn

### Trước khi debug

- [ ] Xác định log, trace, screenshot, HAR và diagnostic bundle sẽ được lưu ở đâu.
- [ ] Dùng tài khoản, tenant và token synthetic.
- [ ] Không copy token production vào công cụ debug.
- [ ] Tắt wire logging/body capture không cần thiết.
- [ ] Xác định trường claims có PII hoặc định danh nhạy cảm.

### Khi ghi log

- [ ] Redact Authorization và Proxy-Authorization.
- [ ] Redact Cookie, Set-Cookie và các token field trong body/query.
- [ ] Không log raw JWT hoặc toàn bộ payload.
- [ ] Dùng structured logging với allowlist.
- [ ] Ghi failure code, request ID và validation stage thay cho credential.
- [ ] Không đưa token vào trace baggage, span attribute hoặc exception.
- [ ] Nếu cần correlation, ưu tiên request ID; HMAC fingerprint chỉ dùng khi có lý do.

### Khi tạo fixture

- [ ] Subject, tenant, email và resource ID đều synthetic.
- [ ] Issuer, audience và endpoint dùng domain test/example.
- [ ] Key và secret test tách biệt hoàn toàn với production.
- [ ] Fixture không chứa dữ liệu cá nhân hoặc credential thật.
- [ ] Production không tin test issuer/key.
- [ ] Token mẫu trong tài liệu dùng placeholder rõ ràng.

### Khi chia sẻ kết quả

- [ ] Scrub HAR, screenshot, curl, Postman collection và ticket.
- [ ] Kiểm tra log storage, archive và bản export.
- [ ] Chỉ chia sẻ cho người cần biết.
- [ ] Áp dụng retention và quyền truy cập phù hợp.
- [ ] Có quy trình thu hồi/rotate nếu raw token đã lộ.

## 14. Tình huống thực tế

### Tình huống A — Debug log ghi nguyên Authorization header

Một lỗi 401 khiến nhóm bật request logging. Log ghi toàn bộ Authorization header và được gửi tới APM có nhiều nhóm truy cập.

**Bài học:** redaction phải xảy ra trước khi log/export; debug không cần raw bearer token.

### Tình huống B — Dashboard che token nhưng storage vẫn giữ raw value

Giao diện log hiển thị [REDACTED], nhưng collector đã lưu header gốc vào index và archive.

**Bài học:** kiểm tra raw event ở storage và mọi bản sao; che ở UI không đủ.

### Tình huống C — Chỉ mask một phần JWT

Nhóm hỗ trợ giữ prefix/suffix để nhận diện token qua nhiều log. Các giá trị này vẫn tạo khả năng liên kết và có thể tiết lộ cấu trúc.

**Bài học:** redact toàn bộ; dùng request ID hoặc HMAC fingerprint có khóa riêng khi cần correlation.

### Tình huống D — Dùng token production trong Postman collection

Một kỹ sư export collection để gửi đồng nghiệp. Authorization header và environment variable chứa token thật vẫn nằm trong file.

**Bài học:** tái tạo request bằng synthetic token; scrub cả collection, environment, history và file đính kèm.

### Tình huống E — Test dùng chung signing key với production

Fixture test ký bằng một secret cố định được dùng lại ở production. Token mẫu có thể được production chấp nhận nếu issuer/audience/profile phù hợp.

**Bài học:** tách issuer, key, audience và secret theo môi trường; không chia sẻ khóa test.

### Tình huống F — Claims PII xuất hiện trong exception

Validator ném exception chứa toàn bộ payload để hỗ trợ debug. Error tracker thu thập exception và gửi sang hệ thống bên ngoài.

**Bài học:** exception chỉ nên chứa failure code và request ID; không nhúng raw payload hoặc PII.

### Tình huống G — Token bị lộ trong trace baggage

Ứng dụng thêm Authorization header vào baggage để downstream service tiện dùng. Trace được export và lưu qua nhiều hệ thống.

**Bài học:** baggage không phải kho credential; truyền credential qua kênh request được bảo vệ và không ghi nó vào trace.

## 15. Ma trận kiểm thử quyền riêng tư và debug

| Kịch bản | Kết quả mong đợi |
| --- | --- |
| Log request có bearer token synthetic | Chỉ placeholder xuất hiện |
| Log response có Set-Cookie | Cookie value được redact |
| Token nằm trong nested JSON body | Trường nhạy cảm được redact |
| Token nằm trong query string | Không xuất hiện trong URL log |
| Exception có token trong context | Error report không chứa token |
| APM bật header capture | Authorization/Cookie bị loại bỏ trước export |
| Trace baggage có canary | Canary không được export |
| Test fixture được tạo mới | Không có credential production hoặc PII thật |
| Test key xuất hiện trong production config | Deployment/policy check từ chối |
| Dashboard hiển thị redacted event | Raw storage và archive cũng không có secret |
| HMAC fingerprint được bật | Dùng key logging riêng, không thể dùng làm bearer credential |
| Token thật bị phát hiện trong log | Có thể thu hồi token và xác định phạm vi log đã lưu |
| Schema log thêm field mới | Field bị chặn cho tới khi được review/allowlist |
| HAR/Postman export được chia sẻ | Không có Authorization, Cookie hoặc secret environment |

## 16. Tự kiểm tra

| Câu hỏi | Đáp án |
| --- | --- |
| Có nên log raw JWT để debug lỗi chữ ký không? | **Không.** Ghi validation stage, failure code và request ID; tái hiện bằng token synthetic. |
| JWS payload có bí mật vì đã Base64url không? | **Không.** Base64url là encoding; payload thường đọc được nếu không dùng JWE. |
| Che token ở dashboard có đủ không? | **Không.** Raw value có thể đã nằm trong collector, index, archive hoặc export. |
| Có nên giữ vài ký tự đầu/cuối của bearer token không? | Không theo mặc định; redact toàn bộ và dùng request ID hoặc fingerprint có kiểm soát khi cần. |
| HMAC fingerprint có thay thế raw token được không? | Không. Nó chỉ hỗ trợ correlation và cần khóa logging riêng. |
| Có thể dùng token production làm fixture sau khi thay một phần payload không? | **Không.** Dùng dữ liệu và key synthetic hoàn toàn. |
| Token test có nên dùng chung signing key với production không? | **Không.** Tách issuer, key, audience và secret theo môi trường. |
| Claims như email, sub, tenant có cần xem xét quyền riêng tư không? | **Có.** Đây có thể là dữ liệu nhận diện hoặc liên kết người dùng. |
| Nên log allowlist hay log tất cả rồi redact denylist? | Ưu tiên allowlist; kết hợp redaction nhiều lớp như phòng thủ bổ sung. |
| Nếu token thật lọt vào log, xóa khỏi dashboard có đủ không? | **Không.** Cần đánh giá, thu hồi credential, khoanh vùng bản sao và xử lý retention. |

## 17. Ghi nhớ

- JWT và các token liên quan là credential; không log raw access token, refresh token, ID Token hoặc Authorization header.
- JWS payload thường có thể đọc được; Base64url không phải encryption. JWE vẫn cần được bảo vệ như credential.
- Redaction nên diễn ra trước khi log, trace hoặc telemetry được serialize/export.
- Dùng structured logging với allowlist; không dump toàn bộ claims hoặc request object.
- Redact cả header, cookie, query, body, exception, trace baggage, APM, CI output và diagnostic bundle.
- Mask một phần không phải mặc định an toàn cho token; ưu tiên redaction toàn bộ.
- Nếu cần correlation, dùng request ID; HMAC fingerprint chỉ là lựa chọn bổ sung với khóa logging riêng.
- Tạo dữ liệu mẫu hoàn toàn synthetic; issuer, audience, key, tenant và subject phải tách biệt production.
- Khi token thật bị lộ, coi là credential exposure: đánh giá và thu hồi/rotate, khoanh vùng bản sao, sửa nguồn log và kiểm thử hồi quy.

### Tiêu chuẩn và tài liệu tham khảo

- [RFC 7519 – JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519)
- [RFC 7515 – JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515)
- [RFC 7516 – JSON Web Encryption (JWE)](https://www.rfc-editor.org/rfc/rfc7516)
- [RFC 6750 – OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
- [RFC 6973 – Privacy Considerations for Internet Protocols](https://www.rfc-editor.org/rfc/rfc6973)
- [RFC 9110 – HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110)
- [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html)
- [OWASP Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html)
- [OWASP REST Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/REST_Security_Cheat_Sheet.html)
