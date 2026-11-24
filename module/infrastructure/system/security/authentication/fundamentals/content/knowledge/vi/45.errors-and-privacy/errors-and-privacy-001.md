# Authentication error

> **Chương:** Error và privacy  
> **Module:** SECURITY_AUTHENTICATION_FUNDAMENTALS  
> **Trọng tâm:** Thiết kế lỗi xác thực và thông báo bảo mật sao cho người dùng biết bước tiếp theo, trong khi hệ thống không làm lộ sự tồn tại của tài khoản, credential, dữ liệu cá nhân hoặc chi tiết nội bộ có thể hỗ trợ attacker.

## 1. Authentication error là gì?

**Authentication error (lỗi xác thực)** là kết quả hoặc sự cố xảy ra khi hệ thống không thể xác minh credential, không thể hoàn tất một bước xác thực hoặc không thể tin cậy trạng thái danh tính của request. Lỗi có thể đến từ người dùng nhập sai password, token hết hạn, MFA thất bại, session bị thu hồi, clock skew, identity provider không khả dụng hoặc một thành phần xác minh gặp lỗi.

Ví dụ, người dùng nhập sai mật khẩu. Ứng dụng cần thông báo rằng đăng nhập chưa thành công và hướng dẫn thử lại hoặc khôi phục tài khoản. Ứng dụng không nên tiết lộ rằng email đó có tồn tại hay không, không trả về password hash và không hiển thị stack trace của authentication service.

Lỗi xác thực cũng có thể là tín hiệu của tấn công: nhiều lần thử password, MFA push bất thường, token replay, credential stuffing hoặc thay đổi recovery method không được phép. Vì vậy, xử lý lỗi cần đồng thời phục vụ trải nghiệm, bảo mật, vận hành và quyền riêng tư.

### Kết quả học tập

Sau bài này, người học có thể:

- Phân loại lỗi authentication và phân biệt với lỗi authorization.
- Thiết kế thông báo công khai không làm lộ trạng thái tài khoản hoặc credential.
- Chọn HTTP status và error code phù hợp cho web/API.
- Xử lý lỗi từ IdP, MFA, session, token và time service an toàn.
- Ghi log có cấu trúc mà không lưu password, token hoặc secret.
- Áp dụng data minimization, retention và access control cho dữ liệu xác thực.
- Kiểm thử account enumeration, timing leak, logging leak và failure mode.

## 2. Authentication, authorization và operational error

Không nên gom mọi lỗi thành một thông báo kỹ thuật duy nhất. Cần phân biệt bản chất lỗi để hệ thống xử lý đúng, dù nội dung gửi cho người dùng có thể được chuẩn hóa.

| Nhóm lỗi | Ý nghĩa | Ví dụ |
|---|---|---|
| Authentication failure | Không xác minh được credential hoặc principal | Password sai, token chữ ký sai |
| Authentication challenge | Cần thêm bước để hoàn tất xác thực | MFA required, step-up required |
| Credential state | Credential không còn được chấp nhận | Expired, revoked, disabled |
| Session state | Session không hợp lệ hoặc đã hết hạn | Session timeout, session revoked |
| Authorization denial | Principal đã được xác thực nhưng không đủ quyền | User không có permission trên resource |
| Abuse/rate limit | Request bị giới hạn do tần suất hoặc rủi ro | Quá nhiều lần thử password |
| Dependency failure | Dịch vụ phụ thuộc không thể xử lý | IdP, directory hoặc key service unavailable |
| Internal error | Lỗi ngoài dự kiến trong ứng dụng | Database exception, parser bug |

Authentication thành công không có nghĩa request được phép. Ví dụ, access token hợp lệ nhưng thiếu quyền đọc hồ sơ phải dẫn tới authorization denial. Ngược lại, lỗi kết nối tới IdP không chứng minh password sai; không nên báo người dùng rằng họ nhập sai credential khi hệ thống không thể xác minh.

### Quy tắc phân loại

- Xác định lỗi ở tầng nào: browser, gateway, authentication service, IdP, MFA provider, session store hay resource server.
- Tách nguyên nhân nội bộ khỏi thông điệp công khai.
- Dùng error code ổn định cho client và reason code chi tiết hơn cho log nội bộ.
- Không chuyển lỗi dependency thành lỗi credential.
- Không fail-open để biến lỗi xác thực thành quyền truy cập mặc định.

## 3. Hai lớp thông tin lỗi: công khai và nội bộ

Một thiết kế tốt thường có hai dạng thông tin:

1. **Thông báo cho người dùng/client:** ngắn gọn, an toàn, dễ hành động và không tiết lộ dữ liệu nhạy cảm.
2. **Diagnostic/audit event nội bộ:** đủ thông tin để điều tra, vận hành và phát hiện tấn công; được kiểm soát quyền truy cập và thời hạn lưu giữ.

Ví dụ:

| Tình huống nội bộ | Thông báo công khai | Reason code nội bộ |
|---|---|---|
| Không có account với identifier đã nhập | Thông tin đăng nhập không hợp lệ | AUTH_CREDENTIAL_REJECTED |
| Password hash không khớp | Thông tin đăng nhập không hợp lệ | PASSWORD_VERIFY_FAILED |
| Tài khoản bị hạn chế | Không thể đăng nhập lúc này; xem hướng dẫn hỗ trợ | ACCOUNT_ACCESS_RESTRICTED |
| MFA code sai | Không thể xác minh mã; thử lại hoặc dùng phương thức được hỗ trợ | MFA_CODE_INVALID |
| Token hết hạn | Phiên xác thực đã hết hạn; đăng nhập lại | TOKEN_EXPIRED |
| IdP timeout | Dịch vụ đăng nhập tạm thời không khả dụng | IDP_TIMEOUT |
| Session store lỗi | Không thể hoàn tất yêu cầu; thử lại sau | SESSION_STORE_UNAVAILABLE |
| User đã xác thực nhưng thiếu quyền | Bạn không có quyền thực hiện thao tác này | AUTHZ_PERMISSION_DENIED |

Thông báo công khai không cần hiển thị nguyên nhân nội bộ chính xác. Nhưng cũng không nên nói sai sự thật. Nếu IdP đang ngừng hoạt động, người dùng cần biết dịch vụ tạm thời không khả dụng thay vì liên tục đổi password.

## 4. Chống account enumeration

**Account enumeration** là việc attacker xác định tài khoản nào tồn tại, đang active, bị khóa hoặc đã đăng ký một phương thức xác thực. Thông tin này có thể hỗ trợ phishing, credential stuffing, social engineering và tấn công recovery.

### Các kênh rò rỉ phổ biến

- Thông báo khác nhau giữa “email không tồn tại” và “password sai”.
- HTTP status hoặc response body khác nhau cho từng trạng thái account.
- Thời gian phản hồi khác biệt có thể đo lường được.
- Trang recovery xác nhận địa chỉ email có đăng ký hay không.
- API gửi OTP trả về thông tin tài khoản cụ thể.
- Trang đăng ký tiết lộ email đã được sử dụng.
- MFA enrollment cho biết user có bật TOTP hoặc passkey hay không.

### Cách giảm enumeration

- Dùng thông báo công khai nhất quán cho các trường hợp credential không hợp lệ.
- Giữ response shape và status ổn định khi phù hợp với API contract.
- Tránh nhánh xử lý có thời gian chênh lệch lớn; dùng password verify path tương đương khi account không tồn tại nếu phù hợp.
- Rate limit login, recovery, OTP send và account lookup.
- Không trả danh sách phương thức MFA hoặc recovery đã đăng ký trước khi user chứng minh quyền kiểm soát account.
- Không xác nhận account tồn tại trong form reset password; gửi thông báo tới kênh đã đăng ký.
- Theo dõi pattern enumeration theo IP, device, network và account identifier.

Không cần làm mọi response giống hệt nhau trong mọi ngữ cảnh. Sau khi người dùng đã xác thực hoặc hoàn tất proof-of-control phù hợp, hệ thống có thể cung cấp hướng dẫn cụ thể hơn. Mục tiêu là không cho người chưa được xác thực dùng endpoint công khai để lập danh sách tài khoản.

## 5. Thông báo lỗi password và recovery

Thông báo login nên giúp người dùng biết phải làm gì mà không tiết lộ password có đúng một phần, account có tồn tại hay trạng thái nội bộ.

### Mẫu thông báo phù hợp

- “Thông tin đăng nhập không hợp lệ. Hãy kiểm tra và thử lại.”
- “Bạn chưa thể đăng nhập lúc này. Hãy thử lại sau hoặc dùng kênh hỗ trợ chính thức.”
- “Phiên đăng nhập đã hết hạn. Hãy đăng nhập lại.”
- “Không thể hoàn tất xác minh bổ sung. Hãy thử phương thức khác đã đăng ký.”
- “Nếu địa chỉ này có tài khoản, hướng dẫn khôi phục sẽ được gửi tới kênh đã đăng ký.”

### Tránh thông báo

- “Email này không tồn tại.”
- “Tài khoản của bạn là administrator nhưng đã bị khóa.”
- “Mật khẩu sai ở ký tự thứ sáu.”
- “OTP của bạn gần đúng.”
- “Tài khoản có bật SMS MFA nhưng không có passkey.”
- “User ID 48392 không có trong database.”

### Hỗ trợ người dùng khi bị hạn chế

Nếu account bị khóa tạm thời hoặc cần hỗ trợ, có thể đưa liên kết tới trang help chính thức và mã tham chiếu sự cố. Mã tham chiếu không được chứa account ID, token hoặc reason code nhạy cảm. Không yêu cầu người dùng gửi password, OTP hoặc recovery code cho helpdesk.

## 6. HTTP status và API error contract

API cần status code đúng nghĩa để client xử lý nhất quán. Status code không nên tiết lộ nhiều trạng thái nội bộ hơn mức cần thiết.

| HTTP status | Ý nghĩa thường dùng | Ví dụ |
|---|---|---|
| 400 Bad Request | Request sai cú pháp hoặc thiếu trường bắt buộc | Body không hợp lệ |
| 401 Unauthorized | Thiếu hoặc credential không hợp lệ | Bearer token không hợp lệ |
| 403 Forbidden | Đã xác thực nhưng không được phép | Thiếu permission |
| 404 Not Found | Resource không tồn tại hoặc được che theo policy | Resource được ẩn để tránh enumeration |
| 409 Conflict | Trạng thái nghiệp vụ xung đột | Challenge đã được dùng |
| 429 Too Many Requests | Bị rate limit | Thử OTP quá nhiều |
| 500 Internal Server Error | Lỗi nội bộ ngoài dự kiến | Bug xử lý |
| 502/503/504 | Gateway hoặc dependency không thể phục vụ | IdP unavailable, upstream timeout |

### 401 và WWW-Authenticate

Với HTTP authentication, 401 thường đi kèm WWW-Authenticate challenge theo scheme được hỗ trợ. Với Bearer token, API có thể trả challenge phù hợp và error code chuẩn hóa. Không đưa token, claim nhạy cảm hoặc chi tiết xác minh chữ ký vào response.

### 403 không phải lỗi password

Nếu token hợp lệ nhưng user không có permission, trả authorization denial theo API contract. Không yêu cầu người dùng nhập lại password liên tục để giải quyết quyền thiếu. Với hành động có thể step-up, response có thể hướng client vào một flow xác thực bổ sung đã được thiết kế.

### 429 và Retry-After

Khi rate limit, có thể cung cấp Retry-After hoặc thông tin retry an toàn. Không trả số lần thử còn lại nếu thông tin đó giúp attacker tối ưu brute force. Client nên áp dụng backoff và không tự động retry dồn dập.

## 7. Error response có cấu trúc

Response có cấu trúc giúp client xử lý nhất quán và tránh phải phân tích chuỗi thông báo tự do.

Ví dụ:

~~~json
{
  "type": "https://api.example.test/problems/authentication-failed",
  "title": "Authentication failed",
  "status": 401,
  "detail": "Thông tin xác thực không hợp lệ hoặc đã hết hạn.",
  "instance": "/requests/req-7f31",
  "code": "AUTH_CREDENTIAL_REJECTED"
}
~~~

Đây là ví dụ minh họa theo phong cách Problem Details. Các trường public phải được chọn cẩn thận:

- type: URI định danh loại lỗi, không phải đường dẫn tới stack trace.
- title: tiêu đề ngắn, không chứa secret.
- status: HTTP status tương ứng.
- detail: thông báo an toàn, không chứa nguyên nhân nhạy cảm.
- instance: mã tham chiếu request không tiết lộ định danh cá nhân.
- code: mã ổn định để client xử lý, không mã hóa trạng thái account nhạy cảm.

Không trả exception message nguyên bản, SQL error, tên bảng, đường dẫn file, hostname nội bộ, key ID bí mật hoặc stack trace. Client không nên phụ thuộc vào detail để điều khiển logic; hãy dùng status và code đã tài liệu hóa.

## 8. Lỗi MFA, passkey và step-up

MFA có nhiều trạng thái khác nhau: chưa bắt đầu challenge, challenge hết hạn, code sai, push bị từ chối, authenticator không khả dụng hoặc yếu tố bị thu hồi. Thông báo cần giúp người dùng tiếp tục mà không tiết lộ phương thức đã đăng ký của một account chưa được xác minh.

### TOTP

- Không cho biết mã sai ở vị trí nào.
- Không tiết lộ seed hoặc secret trong response/log.
- Giới hạn số lần thử và tốc độ gửi lại challenge.
- Nếu clock skew có thể là nguyên nhân, hướng dẫn kiểm tra thời gian tự động sau khi user đã chứng minh account.
- Không mở rộng cửa sổ TOTP vô hạn chỉ để giảm support ticket.

### Push MFA

- Không tiết lộ liệu account khác có push MFA hay không.
- Prompt không do người dùng khởi tạo phải có thể bị từ chối và báo cáo.
- Khi bị rate limit, response không được khuyến khích user approve một prompt cũ.
- Ghi nhận số prompt, kết quả và context cần thiết; không lưu secret.

### Passkey/WebAuthn

- Không trả chi tiết credential ID hoặc danh sách passkey của account chưa xác minh.
- Phân biệt lỗi challenge, origin/RP ID, user verification và credential state trong log nội bộ.
- Public response nên hướng người dùng thử lại hoặc dùng phương thức recovery đã đăng ký.
- Không coi mọi lỗi WebAuthn là password failure.

### Step-up

Nếu action cần step-up, response nên cho biết cần hoàn tất xác minh bổ sung qua flow chính thức. Challenge phải gắn với session, action, resource và thời hạn; không chấp nhận challenge cũ hoặc dùng cho hành động khác.

## 9. Lỗi token, session và federation

Các lỗi credential có thể gồm:

- Token malformed hoặc chữ ký không hợp lệ.
- Issuer không được tin cậy.
- Audience không khớp resource server.
- Token chưa đến thời điểm nbf hoặc đã qua exp.
- Token bị revoke hoặc introspection không xác minh được.
- Session hết idle/absolute timeout.
- Session bị rotate/revoke sau recovery hoặc risk event.
- OIDC state/nonce không khớp.
- Authorization code đã dùng hoặc hết hạn.
- Federation metadata/JWKS không khả dụng hoặc key rotation đang diễn ra.

### Public response và internal reason

Với request từ người dùng cuối, token không hợp lệ thường có thể được phản hồi bằng yêu cầu đăng nhập lại. Với service-to-service, log cần reason code để phân biệt audience mismatch, issuer mismatch, signature failure hoặc dependency outage. Không cần gửi toàn bộ lý do xác minh cho caller không đáng tin.

### Dependency failure

Nếu introspection endpoint, JWKS endpoint hoặc IdP timeout, hệ thống cần quyết định theo policy rõ:

- Không mặc định token hợp lệ khi không thể xác minh.
- Có thể dùng key cache đã xác minh trong giới hạn an toàn nếu protocol và policy cho phép.
- Cảnh báo khi key cache quá cũ hoặc không thể refresh.
- Trả 503/504 hoặc lỗi tạm thời phù hợp thay vì báo password sai.
- Không cho client retry vô hạn; dùng backoff và Retry-After khi thích hợp.

## 10. Lỗi và quyền riêng tư trong log

Log xác thực rất hữu ích để phát hiện brute force, credential stuffing, MFA fatigue và account takeover. Nhưng log cũng có thể trở thành nơi tập trung nhiều dữ liệu nhạy cảm.

### Tuyệt đối không ghi trực tiếp

- Password hoặc password confirmation.
- OTP, TOTP seed, recovery code và backup code.
- Access token, refresh token, ID token hoặc authorization code.
- Session cookie, session ID thô và bearer credential.
- Private key, API secret, client secret hoặc signing secret.
- Toàn bộ request body của login/recovery nếu có chứa credential.
- URL query chứa token hoặc thông tin khôi phục.

### Có thể ghi khi có mục đích và kiểm soát

- Event type và result.
- Timestamp UTC và service/node ID.
- Request/correlation ID ngẫu nhiên.
- Principal reference đã pseudonymize hoặc internal ID được bảo vệ.
- Authentication method ở mức cần thiết.
- Reason code không chứa secret.
- Risk signal tối thiểu cần cho phát hiện abuse.
- Source network information khi có cơ sở, thời hạn và kiểm soát phù hợp.

Không phải mọi trường đều cần được ghi trong mọi sự kiện. Hãy dùng allowlist field và purpose limitation thay vì log toàn bộ request rồi cố xóa secret sau.

## 11. Pseudonymization và dữ liệu nhận diện

Địa chỉ IP, email, số điện thoại, device identifier, user agent, geolocation và authentication history có thể là dữ liệu cá nhân hoặc dữ liệu nhạy cảm theo ngữ cảnh.

### Giảm khả năng nhận diện

- Dùng internal principal ID thay cho email trong log thông thường.
- Dùng HMAC với key được bảo vệ để tạo identifier ổn định cho correlation khi cần.
- Tránh hash email đơn giản vì attacker có thể đoán và tra ngược qua dictionary.
- Rút gọn hoặc loại bỏ IP khi không cần độ chính xác đầy đủ.
- Không thu thập browser fingerprint nếu không có mục đích, căn cứ và đánh giá rủi ro phù hợp.
- Không gắn dữ liệu xác thực với analytics quảng cáo hoặc tracking bên thứ ba.

Pseudonymization không đồng nghĩa anonymization. Nếu tổ chức còn có thể liên kết identifier trở lại một người bằng key hoặc bảng mapping, dữ liệu vẫn cần được bảo vệ như dữ liệu có thể nhận diện.

## 12. Data minimization và purpose limitation

Chỉ thu thập và xử lý dữ liệu cần thiết cho mục đích xác thực, bảo vệ tài khoản, audit hoặc vận hành đã xác định.

Trước khi thêm một trường vào log hoặc telemetry, hãy trả lời:

1. Trường này phục vụ mục đích cụ thể nào?
2. Có cách ít xâm phạm hơn để đạt mục đích không?
3. Ai cần truy cập và trong bao lâu?
4. Có thể pseudonymize, aggregate hoặc giảm độ chi tiết không?
5. Nếu dữ liệu bị lộ, hậu quả với người dùng là gì?
6. Có thể xóa dữ liệu khi hết mục đích không?

Ví dụ, để đếm số lần login thất bại, hệ thống có thể dùng counter theo account reference đã bảo vệ và cửa sổ thời gian, thay vì lưu password, full request body và mọi header của browser.

## 13. Retention và kiểm soát truy cập log

Không có một thời hạn lưu log phù hợp cho mọi tổ chức. Retention cần dựa trên mục đích bảo mật, nghĩa vụ pháp lý, yêu cầu điều tra và nguyên tắc giảm dữ liệu.

### Thiết kế retention

- Phân loại authentication event, security audit, application diagnostic và analytics.
- Xác định retention cho từng loại thay vì giữ tất cả vô thời hạn.
- Xóa hoặc aggregate dữ liệu khi hết mục đích.
- Giữ legal hold chỉ khi có căn cứ và người chịu trách nhiệm.
- Kiểm soát bản sao trong backup, data lake, SIEM và hệ thống ticket.
- Kiểm tra vòng đời dữ liệu khi đổi nhà cung cấp logging.

### Access control

- Chỉ đội và vai trò cần thiết được xem log xác thực chi tiết.
- Dùng RBAC/ABAC, MFA và audit cho truy cập log.
- Tách quyền quản trị hệ thống log khỏi quyền chỉnh sửa ứng dụng phát log.
- Phát hiện truy vấn hàng loạt hoặc truy cập bất thường.
- Mask dữ liệu cá nhân trong dashboard mặc định.
- Có quy trình phê duyệt khi cần mở dữ liệu chi tiết phục vụ điều tra.

Log có thể chứa bằng chứng về hành vi người dùng và hoạt động nội bộ. Không xem log là dữ liệu vô hại chỉ vì nó được tạo tự động.

## 14. Audit log và diagnostic log

Hai loại log có mục đích khác nhau:

| Loại | Mục đích | Ví dụ |
|---|---|---|
| Security audit | Ghi lại sự kiện quan trọng, nguồn và kết quả | Login success, MFA factor added, recovery completed |
| Diagnostic log | Hỗ trợ tìm lỗi và vận hành | IdP timeout, session store latency |
| Metrics | Đếm/tổng hợp trạng thái | Login failure rate, MFA rejection count |
| Trace | Liên kết request qua nhiều service | Gateway đến authentication service |

Audit cần tính toàn vẹn, khả năng truy vết và quyền truy cập nghiêm ngặt. Diagnostic log cần giới hạn dữ liệu và tránh ghi payload nhạy cảm. Metrics nên dùng nhãn có cardinality hợp lý và không đưa email/token vào label. Trace không được mang bearer credential trong baggage hoặc span attributes.

### Ví dụ audit event an toàn

~~~json
{
  "event_type": "authentication.login",
  "event_id": "evt-91a2",
  "timestamp": "2026-11-22T08:30:00Z",
  "service": "web-auth",
  "principal_ref": "pseudonymous-7f31",
  "method": "passkey",
  "result": "success",
  "reason_code": "AUTH_SUCCESS",
  "request_id": "req-7f31"
}
~~~

Ví dụ này không chứa password, token, session cookie, private key hoặc raw authenticator response. Nếu cần điều tra sâu, hệ thống có thể dùng quy trình được phê duyệt để tra principal reference trong kho dữ liệu có kiểm soát.

## 15. Error handling không được tạo side channel

Attacker có thể quan sát nhiều hơn nội dung thông báo:

- HTTP status.
- Response length.
- Timing.
- Redirect destination.
- Cookie được set hay không.
- Số lần gửi email/OTP.
- Khác biệt trong retry behavior.
- Kích thước và cấu trúc response.

Các khác biệt này có thể tiết lộ account tồn tại, MFA method, trạng thái khóa hoặc loại credential.

### Giảm side channel

- Chuẩn hóa public response cho các trường hợp cần chống enumeration.
- Dùng redirect và cookie behavior nhất quán.
- Rate limit và abuse detection ở nhiều lớp.
- Không cung cấp endpoint tra cứu account/method công khai.
- Giảm chênh lệch timing có thể đo lường được.
- Không gửi email/OTP cho mỗi lần request vô hạn; áp dụng cooldown.
- Không tiết lộ trạng thái account trong URL hoặc referrer.

Không cần làm hệ thống hoàn toàn không thể phân biệt về thời gian ở mọi trường hợp. Ưu tiên loại bỏ khác biệt rõ, lặp lại được và có thể khai thác; đo kiểm ở môi trường thực tế.

## 16. Lỗi từ hệ thống phụ thuộc và fail-safe

Authentication thường phụ thuộc IdP, database, directory, MFA provider, HSM/KMS, session store, NTP và dịch vụ gửi thông báo.

### Khi dependency lỗi

- **IdP unavailable:** không xác minh danh tính mới; hiển thị lỗi tạm thời.
- **JWKS refresh failure:** dùng key cache đã xác minh trong giới hạn policy; không tin key mới không xác thực.
- **Session store unavailable:** không tạo session mặc định hoặc bypass kiểm tra session.
- **MFA provider unavailable:** không tự bỏ qua MFA; cung cấp phương án dự phòng đã được phê duyệt.
- **Directory unavailable:** không suy ra membership hoặc role từ dữ liệu thiếu.
- **KMS/HSM unavailable:** không dùng secret dự phòng không được quản lý.
- **Time service unhealthy:** không nới leeway tùy tiện hoặc bỏ kiểm tra expiry.
- **Notification provider unavailable:** ghi nhận và retry có giới hạn; không lộ recovery token trong log.

### Retry và circuit breaker

Retry cần có exponential backoff, jitter, deadline và giới hạn số lần. Retry dồn dập có thể làm IdP hoặc MFA provider quá tải hơn. Circuit breaker và bulkhead giúp giới hạn lỗi lan truyền, nhưng không được biến trạng thái dependency lỗi thành xác thực thành công.

Nếu có break-glass, đó phải là quy trình riêng có danh tính cá nhân, phạm vi hẹp, phê duyệt, thời hạn, audit và review sau sử dụng. Không tạo tài khoản dùng chung không kiểm soát để thay thế IdP.

## 17. Phát hiện abuse qua authentication error

Lỗi xác thực có thể là tín hiệu cho các hành vi:

- Credential stuffing: thử credential bị rò rỉ trên nhiều tài khoản.
- Password spraying: thử một số password phổ biến trên nhiều account.
- Brute force: thử nhiều password cho một account.
- MFA fatigue: tạo nhiều push request để ép người dùng chấp thuận.
- OTP brute force: thử nhiều mã ngắn trong một cửa sổ.
- Token replay: dùng lại token hoặc signed request bị đánh cắp.
- Account recovery abuse: gửi nhiều reset request hoặc chiếm kênh recovery.
- Enumeration: dò account, email, MFA method hoặc trạng thái khóa.

### Tín hiệu cần theo dõi

- Tỷ lệ failure theo account reference, IP/network và device/risk signal.
- Số account bị thử từ cùng nguồn.
- Số nguồn thử một account trong thời gian ngắn.
- MFA prompt được gửi và bị deny.
- OTP resend và verify failure.
- Login success bất thường sau chuỗi failure.
- Thay đổi recovery method hoặc passkey ngay sau login rủi ro.
- Token validation failure theo issuer/audience/time reason.

Không dùng một tín hiệu đơn lẻ để tự động khóa tài khoản vĩnh viễn. Kết hợp risk, rate limit, step-up, notification và quy trình review để tránh false positive và denial of service do attacker cố ý gây ra.

## 18. Ví dụ xử lý lỗi đăng nhập

**Bối cảnh:** Một người dùng gửi POST login. Password không đúng hoặc tài khoản không tồn tại. Hệ thống có thể xác định nội bộ hai trường hợp khác nhau, nhưng public response phải giảm account enumeration.

### Luồng xử lý

1. Kiểm tra request format, CSRF và rate limit.
2. Chuẩn hóa identifier theo chính sách.
3. Tìm account; nếu không có, chạy đường xử lý tương đương phù hợp để giảm timing difference.
4. Nếu có account, verify password bằng password hashing library.
5. Nếu credential không hợp lệ, tăng counter/risk signal và trả thông báo chung.
6. Ghi reason code nội bộ cùng request ID, không ghi password hoặc body.
7. Nếu vượt ngưỡng, áp dụng delay/challenge hoặc hạn chế tạm thời theo policy.
8. Nếu user yêu cầu recovery, phản hồi chung và gửi thông tin tới kênh đã đăng ký nếu phù hợp.

### Ví dụ response

~~~http
HTTP/1.1 401 Unauthorized
Content-Type: application/problem+json
Cache-Control: no-store
~~~

~~~json
{
  "type": "https://api.example.test/problems/authentication-failed",
  "title": "Authentication failed",
  "status": 401,
  "detail": "Thông tin đăng nhập không hợp lệ. Hãy thử lại hoặc dùng quy trình khôi phục chính thức.",
  "instance": "/requests/req-7f31",
  "code": "AUTH_CREDENTIAL_REJECTED"
}
~~~

### Ví dụ event nội bộ

~~~json
{
  "event_type": "authentication.failure",
  "request_id": "req-7f31",
  "principal_ref": "pseudonymous-7f31",
  "reason_code": "PASSWORD_VERIFY_FAILED",
  "result": "failure",
  "source_service": "web-auth"
}
~~~

Không ghi identifier thô nếu không cần; nếu vận hành cần tìm account, dùng kho mapping riêng với quyền truy cập và audit. Không ghi password, password hash, OTP, cookie hoặc token.

## 19. Kiểm thử authentication error và privacy

Kiểm thử trong môi trường được phép với account, token và secret giả lập:

| Trường hợp | Kết quả mong đợi |
|---|---|
| Account tồn tại, password sai | Public response không tiết lộ account state |
| Account không tồn tại | Response tương đương về nội dung và shape |
| Hai trường hợp login trên | Timing không có chênh lệch rõ, lặp lại được |
| Account bị khóa | Không tiết lộ trạng thái cho unauthenticated caller |
| Password đúng nhưng MFA chưa xong | Chỉ trả challenge giới hạn, không cấp full session |
| MFA code sai | Không tiết lộ vị trí sai hoặc secret |
| Token hết hạn | Client được yêu cầu xác thực lại theo contract |
| Token sai audience/signature | Bị từ chối; reason chi tiết chỉ ở log nội bộ |
| Token hợp lệ nhưng thiếu permission | Authorization denial, không báo password sai |
| IdP timeout | Lỗi tạm thời, không biến thành invalid credential |
| Session store lỗi | Không fail-open hoặc tạo session không xác minh |
| Rate limit bị kích hoạt | 429/Retry-After theo policy, không lộ account threshold |
| Recovery account không tồn tại | Public response không xác nhận account |
| OTP send bị lặp | Cooldown/rate limit, không gửi vô hạn |
| Error response có stack trace | Không xuất hiện thông tin nội bộ |
| Response có SQL/database detail | Không lộ schema hoặc dữ liệu backend |
| Authorization header vào log | Redaction loại bỏ giá trị |
| Password/OTP/recovery code vào log | Secret scanning/test xác nhận không được lưu |
| Token/session ID trong trace | Không xuất hiện trong baggage/span |
| Email/IP/device identifier trong metrics label | Không có dữ liệu cá nhân thô |
| Log viewer không đủ quyền | Truy cập bị từ chối và có audit |
| Retention hết hạn | Dữ liệu được xóa/aggregate theo policy |
| Break-glass được sử dụng | Có actor, approval, expiry và review |
| Authentication dependency outage | Fail-safe và có alert |

### Chỉ số vận hành

- Login failure rate theo reason code tổng hợp.
- Tỷ lệ account enumeration/rate-limit signal.
- MFA failure, deny và push fatigue signal.
- Tỷ lệ dependency timeout và authentication availability.
- Thời gian phát hiện và xử lý credential abuse.
- Số secret bị phát hiện trong log/trace/analytics.
- Số log access không đúng vai trò.
- Tỷ lệ dữ liệu được xóa theo retention policy.
- Số authentication event thiếu request ID hoặc audit context.

## 20. Checklist authentication error và privacy

- [ ] Phân biệt authentication failure, authorization denial, challenge và dependency failure.
- [ ] Public response không tiết lộ account existence, lock state hoặc MFA enrollment.
- [ ] Nội dung, status và timing được xem xét để giảm enumeration.
- [ ] Error code ổn định, không chứa trạng thái nhạy cảm.
- [ ] Không trả stack trace, SQL error, path hoặc hostname nội bộ.
- [ ] 401, 403, 429 và 5xx được dùng đúng ngữ nghĩa.
- [ ] Retry có backoff, deadline và giới hạn.
- [ ] Dependency failure không biến thành xác thực thành công hoặc báo password sai.
- [ ] Không ghi password, OTP, recovery code, token, cookie hoặc private key.
- [ ] Log dùng allowlist field và reason code an toàn.
- [ ] Pseudonymization có key bảo vệ; không nhầm với anonymization.
- [ ] Data collection có purpose, owner và retention.
- [ ] Log access được giới hạn, audit và giám sát.
- [ ] Metrics/trace không chứa secret hoặc identifier cá nhân thô.
- [ ] Có phát hiện credential stuffing, spraying, MFA fatigue và recovery abuse.
- [ ] Có quy trình điều tra và hỗ trợ người dùng khi account bị hạn chế.
- [ ] Break-glass có scope hẹp, phê duyệt, thời hạn và audit.
- [ ] Kiểm thử enumeration, timing, response leakage, log leakage và dependency outage.

## Ghi nhớ

Authentication error vừa là kết quả xác thực vừa là tín hiệu vận hành và bảo mật. Hãy tách thông báo công khai khỏi diagnostic nội bộ, phân biệt lỗi credential với lỗi dependency và authorization, đồng thời dùng response nhất quán để giảm account enumeration.

Privacy cần được áp dụng từ lúc tạo log: không lưu password, OTP, recovery code, token, cookie hoặc private key; chỉ thu thập dữ liệu có mục đích; pseudonymize khi phù hợp; giới hạn người xem và thời hạn lưu giữ. Lỗi cần đủ thông tin để người dùng biết bước tiếp theo và đội vận hành điều tra, nhưng không trao cho attacker dữ liệu để chiếm tài khoản.
