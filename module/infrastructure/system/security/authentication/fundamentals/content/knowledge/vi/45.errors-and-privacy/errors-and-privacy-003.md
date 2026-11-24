# Generic error — Thông báo lỗi chung an toàn trong hệ thống xác thực

Một người dùng nhập email vào màn hình đăng nhập và nhận được thông báo “Mật khẩu không đúng”. Attacker có thể thử nhiều địa chỉ email rồi quan sát phản hồi để biết tài khoản nào tồn tại. Ở màn hình khôi phục, nếu hệ thống trả “Không tìm thấy tài khoản” cho email chưa đăng ký nhưng trả “Đã gửi liên kết” cho email hợp lệ, endpoint khôi phục trở thành công cụ dò tài khoản. Một lỗi tưởng như giúp người dùng hiểu rõ hơn có thể tiết lộ dữ liệu danh tính và trạng thái bảo mật.

**Generic error (thông báo lỗi chung)** là phản hồi được thiết kế để cung cấp đủ hướng dẫn cho người dùng hoặc client mà không tiết lộ chi tiết nội bộ, dữ liệu cá nhân hay trạng thái xác thực nhạy cảm. Trong hệ thống authentication, generic error thường dùng để làm cho các trường hợp không nên phân biệt công khai — chẳng hạn tài khoản không tồn tại và mật khẩu sai — có phản hồi tương đương. Hệ thống vẫn cần lưu nguyên nhân chi tiết trong kênh chẩn đoán nội bộ có kiểm soát.

Bài học thuộc chương **Error và privacy** của học phần **SECURITY_AUTHENTICATION_FUNDAMENTALS**. Nội dung kết nối generic error với credential, mật khẩu, MFA, passkey, chứng chỉ, token, phiên, liên kết danh tính và khôi phục tài khoản. Người học sẽ biết mô hình hóa ranh giới tin cậy, phòng chống account enumeration, phishing, replay và lạm dụng đăng nhập; đồng thời thiết kế phản hồi lỗi vừa bảo vệ quyền riêng tư vừa hỗ trợ người dùng khắc phục sự cố.

## 1. Kết quả học tập

Sau bài này, người học có thể:

- Giải thích generic error và phân biệt thông báo công khai với diagnostic detail nội bộ.
- Nhận diện account enumeration qua message, HTTP status, response size, timing, header và hành vi phụ.
- Thiết kế phản hồi nhất quán cho login, registration, password reset, MFA, account recovery và federation.
- Chọn HTTP status và response schema phù hợp mà không làm lộ trạng thái tài khoản.
- Dùng correlation ID và structured logging để hỗ trợ điều tra mà không ghi secret hoặc PII dư thừa.
- Giảm timing side-channel bằng cách cân bằng đường xử lý và kiểm thử phân bố thời gian.
- Bảo vệ dữ liệu trong error page, API response, log, trace, analytics và support workflow.
- Cân bằng thông tin hữu ích, accessibility, localization và chống phishing.
- Xử lý rate limit, lockout, upstream failure và lỗi một phần mà không tạo thông báo gây hiểu nhầm.
- Viết tiêu chí kiểm thử cho enumeration, response parity, timing, privacy và observability.

## 2. Generic error là gì?

Một lỗi có hai góc nhìn:

- **Public response:** thông tin mà người dùng, browser, mobile app hoặc API client được phép biết.
- **Internal diagnostic:** nguyên nhân kỹ thuật và bảo mật để đội vận hành điều tra.

Hai góc nhìn không cần giống nhau. Public response có thể nói “Không thể hoàn tất đăng nhập với thông tin đã cung cấp” trong khi internal diagnostic ghi nhận một trong các reason code: PRINCIPAL_NOT_FOUND, PASSWORD_MISMATCH, ACCOUNT_DISABLED, ACCOUNT_LOCKED, PASSWORD_VERIFIER_ERROR hoặc RISK_POLICY_DENIED.

Generic error không có nghĩa là mọi lỗi đều trả cùng một chuỗi hoặc che giấu mọi vấn đề. Nó là cách giảm thông tin nhạy cảm ở ranh giới không tin cậy, trong khi vẫn giữ diagnostic đủ chính xác ở nơi có quyền truy cập.

### 2.1. Ví dụ phản hồi công khai và nội bộ

| Trường hợp nội bộ | Phản hồi công khai có thể dùng | Diagnostic nội bộ |
| --- | --- | --- |
| Email chưa đăng ký | “Không thể hoàn tất đăng nhập với thông tin đã cung cấp.” | PRINCIPAL_NOT_FOUND |
| Mật khẩu sai | Cùng thông báo như trường hợp trên | PASSWORD_MISMATCH |
| Tài khoản bị khóa | Thông báo đăng nhập chung; cung cấp đường khôi phục an toàn | ACCOUNT_LOCKED |
| Tài khoản bị disable | Thông báo chung trước khi xác minh danh tính | ACCOUNT_DISABLED |
| OTP sai hoặc hết hạn | “Mã xác minh không hợp lệ hoặc đã hết hạn.” | MFA_CODE_INVALID hoặc MFA_CHALLENGE_EXPIRED |
| Refresh token đã bị thu hồi | “Phiên đã hết hạn. Vui lòng đăng nhập lại.” | REFRESH_TOKEN_REVOKED |
| Identity provider lỗi | “Hiện không thể hoàn tất đăng nhập. Vui lòng thử lại sau.” | UPSTREAM_IDP_TIMEOUT |

Reason code ở cột nội bộ chỉ dành cho log/metric có kiểm soát; không đưa nguyên văn ra response cho unauthenticated client nếu nó tiết lộ trạng thái tài khoản hoặc cấu trúc hệ thống.

### 2.2. Generic error không được làm người dùng bế tắc

Một phản hồi tốt vẫn chỉ ra hành động an toàn tiếp theo: kiểm tra lại thông tin, thử phương thức đăng nhập khác đã đăng ký, mở ứng dụng chính thức để khôi phục hoặc thử lại sau. Tránh các câu mơ hồ như “Lỗi 12345” hoặc “Có vấn đề xảy ra” mà không có hướng dẫn.

Khi người dùng đã được xác thực đủ mức, giao diện có thể cung cấp thông tin cụ thể hơn về phiên, phương thức MFA hoặc trạng thái tài khoản, miễn là không tiết lộ dữ liệu cho người khác đang dùng chung thiết bị hay session yếu.

## 3. Vì sao lỗi authentication có thể làm lộ dữ liệu?

Một endpoint đăng nhập hoặc khôi phục thường nhận định danh do client cung cấp, chẳng hạn email, username, số điện thoại hoặc tenant. Nếu response thay đổi theo việc principal có tồn tại hay không, attacker có thể kiểm tra danh sách định danh và suy ra:

- Ai có tài khoản trong dịch vụ.
- Email/số điện thoại nào được liên kết với tài khoản.
- Tài khoản nào bị khóa, disable hoặc chưa xác minh.
- Người dùng đã đăng ký MFA/passkey hay chưa.
- Một external identity đã được liên kết với tài khoản nào.
- Tenant, tổ chức hoặc khách hàng nào đang sử dụng hệ thống.
- Một token/reset challenge có hợp lệ hay đã được dùng.

Thông tin này có thể hỗ trợ phishing có mục tiêu, credential stuffing, social engineering, dò recovery channel hoặc tấn công nhân viên của tổ chức.

### 3.1. Account enumeration không chỉ đến từ câu chữ

Attacker có thể quan sát nhiều tín hiệu:

- Message text, error code và response JSON.
- HTTP status code, header và redirect.
- Response length, HTML template hoặc trường JSON có/không có.
- Thời gian phản hồi và số bước xử lý.
- Email/SMS/push có được gửi hay không.
- Khác biệt trong rate limit, CAPTCHA hoặc lockout.
- Khác biệt giữa các endpoint hoặc giữa web và mobile.

Chỉ đổi câu chữ nhưng vẫn trả status, kích thước response hoặc thời gian khác biệt rõ ràng có thể chưa đủ chống enumeration.

### 3.2. Privacy là một thuộc tính của toàn bộ luồng

Generic error cần được áp dụng đồng bộ giữa login, register, forgot password, MFA enrollment, account linking, invitation, SSO callback và support tooling. Nếu login không tiết lộ tài khoản tồn tại nhưng registration trả “Email đã được sử dụng”, attacker vẫn có thể dò danh tính qua registration endpoint.

## 4. Nguyên tắc thiết kế phản hồi lỗi

### 4.1. Tiết lộ tối thiểu

Chỉ gửi thông tin cần để client hiển thị và người dùng chọn hành động tiếp theo. Không trả:

- Principal ID nội bộ, database key hoặc tên bảng.
- Password verifier, token, cookie, OTP, recovery code hoặc private key.
- Stack trace, exception class, file path, hostname, IP nội bộ hoặc service topology.
- Trạng thái tài khoản nhạy cảm trước khi xác minh danh tính.
- Danh sách authenticator, email/phone đầy đủ hoặc tenant membership nếu chưa được phép xem.
- Reason code nội bộ có thể tiết lộ logic phát hiện/risk policy.

### 4.2. Nhất quán giữa các trường hợp tương đương

Nếu hai tình huống không nên phân biệt công khai, hãy dùng cùng:

- Message và error code public.
- HTTP status theo contract của endpoint.
- Response shape và trường dữ liệu.
- Redirect/next step.
- Hành vi phụ có thể quan sát, trong giới hạn thực tế.

Không nhất thiết mọi lỗi của toàn hệ thống phải có cùng status. Ví dụ, request sai định dạng có thể là 400, unauthenticated request là 401, rate limit là 429 và upstream outage là 503. Mục tiêu là tránh khác biệt tiết lộ trạng thái tài khoản giữa các trường hợp cần giữ kín, không phá vỡ semantics HTTP.

### 4.3. Tách public code và internal reason

Public code nên ổn định, ít chi tiết và không mã hóa lý do nhạy cảm. Internal reason code nên có taxonomy rõ để vận hành phân loại được lỗi. Không dùng một chuỗi exception tự do làm mã public.

### 4.4. Không xác nhận thành công khi chưa thành công

Generic error không được dùng để che một thao tác thất bại theo cách khiến người dùng tin rằng credential đã đổi, phiên đã revoke hoặc recovery đã hoàn tất. Phản hồi có thể chung về trạng thái tài khoản, nhưng vẫn phải trung thực về việc hệ thống đã nhận yêu cầu, đang xử lý hay đã commit.

## 5. Login: tránh tiết lộ tài khoản có tồn tại

Một endpoint login thường cần giữ phản hồi tương đương cho principal không tồn tại, password sai, tài khoản chưa được phép đăng nhập hoặc credential không hợp lệ trước khi xác minh đủ danh tính.

### 5.1. Phản hồi nên dùng

Ví dụ:

~~~text
Không thể hoàn tất đăng nhập với thông tin đã cung cấp.
Hãy kiểm tra thông tin hoặc sử dụng phương thức khôi phục tài khoản
trong ứng dụng chính thức nếu bạn không thể đăng nhập.
~~~

Không nên trả các thông báo công khai như:

- “Email này chưa đăng ký.”
- “Mật khẩu sai nhưng email đúng.”
- “Tài khoản bị khóa vì có 5 lần đăng nhập thất bại.”
- “Người dùng này đã bật TOTP nhưng chưa đăng ký passkey.”

Thông báo cụ thể có thể phù hợp sau khi người dùng đã chứng minh quyền kiểm soát tài khoản qua một kênh đáng tin cậy. Trước thời điểm đó, thông tin nên được giới hạn.

### 5.2. Cân bằng đường xử lý

Nếu principal không tồn tại, server có thể trả ngay; nếu tồn tại nhưng password sai, server phải chạy password KDF. Chênh lệch này tạo timing side-channel. Một kỹ thuật phổ biến là dùng dummy verifier có cấu hình KDF tương đương cho principal không tồn tại, rồi chạy cùng đường xác minh mật khẩu.

Điều này cần kết hợp rate limit/admission control vì KDF tốn CPU/RAM. Không dùng delay cố định dài cho mọi request: nó có thể gây DoS và vẫn không loại bỏ được timing signal trong mọi môi trường.

### 5.3. Lockout và disabled account

Không tiết lộ trạng thái locked/disabled trước khi xác minh. Sau khi người dùng chứng minh quyền kiểm soát bằng phương thức còn tin cậy, hệ thống có thể giải thích trạng thái và cung cấp recovery/support path. Thông báo bảo mật có thể gửi tới contact đã xác minh khi có thay đổi trạng thái, nhưng không nên dùng email đó làm bằng chứng duy nhất để mở khóa.

## 6. Registration và account recovery

Registration và recovery là hai bề mặt enumeration phổ biến vì người dùng thường nhập email/phone trước khi xác thực.

### 6.1. Đăng ký tài khoản

Nếu hệ thống không muốn tiết lộ email đã tồn tại, phản hồi có thể trung lập:

~~~text
Nếu thông tin này đủ điều kiện đăng ký hoặc đã có tài khoản liên quan,
bạn sẽ nhận được hướng dẫn qua kênh phù hợp.
Hãy kiểm tra hộp thư hoặc mở ứng dụng chính thức.
~~~

Luồng backend cần tránh khác biệt dễ quan sát giữa tài khoản mới và tài khoản cũ. Có thể dùng email verification hoặc sign-in/recovery flow để người dùng hợp pháp tiếp tục mà không công khai trạng thái principal.

### 6.2. Forgot password

Một phản hồi phù hợp:

~~~text
Nếu có tài khoản phù hợp với thông tin bạn cung cấp,
hướng dẫn khôi phục sẽ được gửi tới kênh đã đăng ký.
Nếu không nhận được, hãy mở ứng dụng chính thức hoặc liên hệ hỗ trợ.
~~~

Backend chỉ tạo reset challenge và gửi thông báo khi principal tồn tại và đủ điều kiện. Public response vẫn giữ nhất quán. Gửi email/SMS bất đồng bộ qua queue/outbox để giảm chênh lệch timing; rate limit theo nguồn và recipient reference để chống email/SMS bombing.

### 6.3. Token khôi phục

Reset token phải gắn với:

- Principal đã xác định.
- Purpose cụ thể (password reset, email verification, MFA recovery...).
- Thời hạn ngắn.
- Một lần sử dụng hoặc trạng thái consume rõ.
- Transaction/audience phù hợp.

Response khi token sai, hết hạn hoặc đã dùng có thể dùng cùng thông báo “Liên kết không hợp lệ hoặc đã hết hạn”. Internal diagnostic phân biệt nguyên nhân. Không trả token hoặc lý do chi tiết trong URL/log.

### 6.4. Recovery không được yếu hơn login

Nếu login dùng passkey/MFA nhưng recovery chỉ cần biết email, attacker có thể đi vòng qua lớp xác thực mạnh. Generic error giúp tránh enumeration nhưng không làm recovery an toàn tự động. Recovery cần proofing, kiểm tra risk, notification tới kênh đã xác minh, delay/hold khi thích hợp và audit.

## 7. MFA, passkey, certificate và federation

Generic error cần nhất quán trên các phương thức xác thực nhưng không được làm mất hướng dẫn cần thiết.

### 7.1. MFA challenge

Public response có thể nói “Mã xác minh không hợp lệ hoặc đã hết hạn” cho các trường hợp mã sai, challenge hết hạn hoặc challenge không còn active. Không tiết lộ:

- Tài khoản có đăng ký TOTP/SMS/push hay không.
- Số điện thoại đầy đủ hoặc email recovery.
- Số lần thử còn lại nếu điều đó giúp attacker tối ưu guessing.
- Challenge ID, seed, OTP hoặc recovery code.

Sau khi người dùng đã vào được security settings, có thể hiển thị danh sách authenticator đã đăng ký ở dạng đã che và cho phép quản lý theo policy.

### 7.2. Passkey/WebAuthn

Không trả lỗi chi tiết giúp attacker dò credential ID, số passkey, thiết bị hoặc account binding. Có thể dùng thông báo chung như “Không thể xác minh bằng phương thức này. Hãy thử lại hoặc chọn phương thức khác đã đăng ký.”

Client cần xử lý các trường hợp user cancel, authenticator unavailable, timeout và assertion invalid theo UX phù hợp; không biến lỗi nội bộ WebAuthn thành stack trace công khai. Khi có thể phân biệt thao tác người dùng hủy với lỗi bảo mật mà không tiết lộ account state, hãy đưa hướng dẫn phù hợp.

### 7.3. Certificate và client authentication

Không trả thông tin nhạy cảm về CA nội bộ, certificate subject, serial number, trust bundle, key ID hoặc chính sách client certificate cho unauthenticated caller. Diagnostic nội bộ có thể ghi reason như chain invalid, expired, revoked, EKU mismatch hoặc issuer untrusted.

### 7.4. Federation và SSO

Lỗi SSO có thể phát sinh từ issuer không tin cậy, audience mismatch, state/nonce sai, assertion hết hạn, subject không được liên kết hoặc IdP tạm lỗi. Public response nên hướng dẫn thử lại hoặc dùng kênh hỗ trợ chính thức, không tiết lộ tenant/user mapping hoặc trạng thái liên kết danh tính.

Không hiển thị raw SAML assertion, OIDC ID token, authorization code, state hoặc nonce trong trang lỗi. Các giá trị này có thể bị phát lại hoặc làm lộ thông tin.

## 8. HTTP status và response schema

Generic error vẫn cần tuân thủ semantics giao thức. Không dùng HTTP 200 cho mọi lỗi authentication chỉ để che trạng thái; client, gateway và monitoring cần hiểu request thất bại ở đâu.

| Status | Ý nghĩa thường dùng | Lưu ý bảo mật |
| --- | --- | --- |
| 400 Bad Request | Request sai định dạng hoặc thiếu trường bắt buộc | Không phản ánh account existence trong response |
| 401 Unauthorized | Thiếu hoặc credential xác thực không hợp lệ | Với HTTP authentication scheme, cần header WWW-Authenticate phù hợp |
| 403 Forbidden | Caller đã được xác thực nhưng không được phép | Chỉ trả sau khi identity đã được xác minh; tránh lộ resource existence nếu policy yêu cầu |
| 404 Not Found | Resource không tồn tại hoặc được cố ý che giấu | Có thể dùng để tránh resource enumeration khi contract cho phép |
| 409 Conflict | Xung đột trạng thái nghiệp vụ | Không dùng để tiết lộ email/account đã tồn tại nếu endpoint công khai cần ẩn |
| 429 Too Many Requests | Đã chạm rate limit | Có thể kèm Retry-After; không tiết lộ ngưỡng nội bộ chi tiết |
| 500 Internal Server Error | Lỗi không dự kiến | Body chung; không trả stack trace/exception |
| 503 Service Unavailable | Dịch vụ tạm thời không sẵn sàng | Có thể cho Retry-After; không tiết lộ dependency nội bộ |

### 8.1. Problem Details

RFC 9457 định nghĩa Problem Details cho HTTP API, thường dùng media type application/problem+json. Một response có thể có type, title, status, detail và instance. Với endpoint authentication, trường detail cần giữ ở mức công khai an toàn; có thể bổ sung public error code ổn định, nhưng không đưa internal reason hoặc account state vào extension.

Ví dụ:

~~~json
{
  "type": "https://api.example.com/problems/authentication-failed",
  "title": "Không thể hoàn tất đăng nhập",
  "status": 401,
  "detail": "Hãy kiểm tra thông tin hoặc sử dụng phương thức khôi phục chính thức.",
  "instance": "/auth/login/requests/req_opaque_..."
}
~~~

Đây là ví dụ minh họa. Instance/correlation reference phải là giá trị opaque, không chứa email, user ID hoặc token. Không trả internal stack, database query, service name hay secret trong body.

### 8.2. Public error code

Public code nên:

- Ổn định qua các phiên bản API.
- Không chứa email, tenant ID, user ID hoặc trạng thái nhạy cảm.
- Có tài liệu để client hiển thị nội dung phù hợp.
- Không làm lộ internal reason chi tiết.
- Có thể ánh xạ nhiều internal reason vào một public code.

Ví dụ, nhiều nguyên nhân login failure có thể ánh xạ về AUTHENTICATION_FAILED; nhiều nguyên nhân reset link không hợp lệ có thể ánh xạ về RECOVERY_LINK_INVALID.

## 9. Timing side-channel và response parity

Nếu unknown account được xử lý trong 2 ms nhưng account tồn tại với password sai mất 150 ms do KDF, attacker có thể gửi nhiều request và phân loại principal theo thời gian. Message giống nhau không giải quyết được timing side-channel.

### Biện pháp

- Chạy dummy KDF cho principal không tồn tại với profile tương đương đường xác minh thông thường.
- Cân bằng các nhánh xử lý trước khi trả response, trong giới hạn không tạo DoS.
- Dùng asynchronous processing cho email/SMS recovery thay vì chờ provider chỉ ở nhánh account tồn tại.
- Tránh response body/header/redirect khác biệt theo account state nhạy cảm.
- Giới hạn tốc độ và theo dõi enumeration patterns.
- Kiểm thử phân bố thời gian trên nhiều lần chạy, không chỉ so sánh một request.
- Theo dõi chênh lệch do cache, database lookup, KDF version và network path.

### 9.1. Không dựa vào random delay đơn thuần

Thêm random sleep có thể làm nhiễu phép đo nhưng không xóa nguyên nhân timing. Nếu hai nhánh vẫn có phân bố thời gian khác nhau, attacker có thể thu thập đủ mẫu để phân biệt. Delay dài còn tiêu tốn worker/connection và tạo điều kiện DoS.

Ưu tiên cân bằng đường xử lý thực tế, dùng dummy verifier và asynchronous side effects. Randomization chỉ là biện pháp phụ nếu được đánh giá, không thay thế thiết kế.

### 9.2. KDF migration có thể tạo timing khác nhau

Một số tài khoản có verifier cũ với cost thấp, tài khoản khác dùng Argon2id mới. Timing có thể tiết lộ nhóm tài khoản hoặc trạng thái migration. Cần đặt deadline nâng cấp, theo dõi nhóm legacy và cân nhắc dummy work/normalization phù hợp. Không làm mọi request tốn tài nguyên quá mức chỉ để đạt thời gian giống hệt tuyệt đối.

## 10. Lỗi ở hệ thống phân tán và upstream dependency

Authentication thường phụ thuộc identity provider, database, KMS/HSM, message broker, email/SMS provider, fraud/risk engine và service mesh. Lỗi ở dependency không nên bị trình bày thành lỗi credential của người dùng.

### 10.1. Phân loại nội bộ

- **User/action error:** dữ liệu đầu vào không hợp lệ hoặc challenge hết hạn.
- **Authentication failure:** credential không chứng minh được danh tính.
- **Authorization denial:** principal hợp lệ nhưng không có quyền.
- **Policy decision:** step-up, hold hoặc deny theo risk policy.
- **Dependency failure:** IdP timeout, KMS unavailable, database connection error.
- **Internal defect:** bug, invariant violation hoặc unexpected exception.

Public response có thể dùng một thông báo tạm thời chung cho dependency outage, nhưng internal diagnostics cần giữ dependency category để vận hành không nhầm lỗi người dùng với lỗi hệ thống.

### 10.2. Retry và side effect

Không retry mù quáng các thao tác có side effect như tạo recovery challenge, gửi SMS, tạo session hoặc rotate refresh token. Dùng idempotency key/operation ID và trạng thái transaction. Nếu response bị mất sau khi commit, retry cần trả kết quả đã lưu theo thiết kế, không tạo nhiều token/challenge.

### 10.3. Fail open và fail closed

Nếu risk engine hoặc revocation store không khả dụng, policy phải xác định hành động nào fail closed. Không bỏ qua MFA, revocation hoặc audience validation chỉ để giảm lỗi hiển thị. Với tính năng ít nhạy cảm có thể dùng cache còn hợp lệ, nhưng phải kiểm tra expiry, tenant và policy version.

## 11. Internal diagnostics: ghi đủ để điều tra

Generic public response chỉ an toàn khi hệ thống vẫn có khả năng chẩn đoán lỗi nội bộ. Structured logging nên ghi các trường tối thiểu:

- Timestamp và service/environment.
- Correlation/request ID do server sinh hoặc đã xác minh.
- Public error code và internal reason code.
- Authentication flow/endpoint và bước xử lý.
- Kết quả policy ở mức reason category.
- Principal reference đã pseudonymize hoặc opaque ID nếu thực sự cần.
- Dependency/status/latency và retry count.
- Event/operation reference để liên kết audit.

### 11.1. Không log secret

Không ghi:

- Password, password verifier đầy đủ nếu không có mục đích đặc biệt và kiểm soát được phê duyệt.
- OTP, TOTP seed, recovery code hoặc reset token.
- Access token, refresh token, ID token, authorization code hoặc session cookie.
- Private key, client secret, API key hoặc HMAC secret.
- Toàn bộ request body chứa dữ liệu xác thực.
- Raw SAML assertion, OIDC token hoặc DPoP proof nếu không cần.

Redaction nên được áp dụng ở nhiều lớp: application logger, reverse proxy, API gateway, tracing SDK, crash reporting và analytics. Đừng chỉ dựa vào lập trình viên nhớ bỏ qua một header.

### 11.2. Correlation ID

Correlation ID giúp người dùng cung cấp mã tham chiếu khi liên hệ hỗ trợ. ID cần ngẫu nhiên/opaque, không chứa PII và không được dùng làm credential. Nếu client gửi correlation ID, server cần kiểm tra định dạng/độ dài hoặc tạo ID mới; không tin nó để truy cập log hoặc dữ liệu của người khác.

Public response có thể hiển thị “Mã tham chiếu: …”. Nhân viên hỗ trợ dùng mã đó để tìm diagnostic theo quyền được cấp. Không cho người dùng tra cứu log tùy ý chỉ bằng ID.

### 11.3. Log access và retention

Log authentication là dữ liệu nhạy cảm. Cần phân quyền, audit truy cập, bảo vệ integrity, retention có mục đích và xóa đúng hạn. Hạn chế đưa email/IP/phone nguyên vẹn vào dashboard rộng. Có thể dùng keyed hash/pseudonymous reference cho phân tích xu hướng; không coi hash email là dữ liệu vô danh tuyệt đối.

## 12. Privacy trong error handling

Thông báo lỗi có thể chứa PII ngay cả khi không chứa password. Ví dụ, echo lại email người dùng nhập, số điện thoại, tenant name, địa chỉ IP, thiết bị hoặc vị trí có thể làm lộ dữ liệu trên thiết bị dùng chung hay trong screenshot/support ticket.

### Nguyên tắc data minimization

- Không echo input nhạy cảm trong response hoặc HTML.
- Che email/phone khi hiển thị trong khu vực đã xác thực; trước xác thực tránh tiết lộ account state.
- Không đưa token, email hoặc user ID vào URL, query string hay referrer.
- Dùng Cache-Control: no-store cho response authentication/recovery nhạy cảm.
- Cấu hình Referrer-Policy phù hợp, thường không gửi referrer từ trang chứa dữ liệu xác thực.
- Không tải third-party analytics/script không cần trên trang login/recovery.
- Escape dữ liệu người dùng trong HTML để tránh reflected XSS qua error message.
- Hạn chế lưu IP/device signal và chỉ dùng cho mục đích bảo mật đã xác định.
- Đặt retention và quyền truy cập cho error log/trace.

### 12.1. Không biến error page thành phishing surface

Error page không nên hiển thị liên kết ngoài tùy ý, nút cài ứng dụng không rõ nguồn hoặc yêu cầu nhập lại credential trên domain khác. Dùng domain chính thức, HTTPS, nội dung nhất quán và hướng người dùng tự mở ứng dụng/trang đã biết khi cần recovery.

### 12.2. Multi-tenant privacy

Không tiết lộ tenant có tồn tại, tenant nào chứa email hoặc user thuộc tổ chức nào qua lỗi đăng nhập công khai. Với admin đã xác thực và có quyền, giao diện quản trị có thể hiển thị chi tiết theo audit policy. Public API cần kiểm tra tenant boundary ở cả lookup, error mapping và cache.

## 13. UX, localization và accessibility

Thông báo chung vẫn cần hữu ích:

- Viết ngắn, rõ và không đổ lỗi.
- Nêu bước tiếp theo an toàn, ví dụ thử lại, dùng phương thức đã đăng ký hoặc mở recovery chính thức.
- Không chỉ dùng màu sắc/icon để biểu đạt lỗi.
- Hỗ trợ screen reader, keyboard navigation và text scaling.
- Không tự xóa thông báo quá nhanh hoặc làm mất nội dung khi focus chuyển.
- Dùng localization nhất quán; không để bản dịch tiết lộ thêm trạng thái so với ngôn ngữ khác.
- Hiển thị mã tham chiếu có thể sao chép nếu cần hỗ trợ.
- Không yêu cầu người dùng gửi password/OTP/recovery code cho nhân viên hỗ trợ.

### 13.1. Hướng dẫn có điều kiện

Nếu tài khoản đã được xác thực, hệ thống có thể hiển thị phương thức recovery đã che, ví dụ email dạng a***@example.com. Trước xác thực, không nên trả mask cụ thể nếu nó vẫn giúp attacker xác nhận email hoặc phone đã đăng ký. Hãy chọn nội dung dựa trên mức xác thực hiện tại.

### 13.2. Thông báo bảo mật sau sự kiện

Generic error không thay thế security notification. Khi password reset, MFA thay đổi, passkey thêm/xóa hoặc session bị revoke, hệ thống có thể gửi cảnh báo tới contact đã xác minh. Notification cần được phát sau khi sự kiện commit và không chứa bí mật. Nếu email bị nghi compromise, không dùng email đó làm bằng chứng duy nhất để recovery.

## 14. Rate limiting, lockout và chống abuse

Một attacker có thể dùng endpoint login/reset để dò tài khoản, spam email/SMS hoặc gây lockout cho nạn nhân. Generic error cần phối hợp với kiểm soát lạm dụng:

- Rate limit theo nhiều chiều: account reference, source IP/network, device/session, tenant và recipient.
- Với principal không tồn tại, dùng keyed pseudonymous identifier để áp dụng quota mà không lưu raw input quá mức.
- Gộp hoặc trì hoãn notification thất bại theo policy; không gửi một email cho mỗi password guess.
- Không khóa tài khoản vĩnh viễn chỉ dựa trên request không xác thực; attacker có thể khóa hộ nạn nhân.
- Dùng progressive delay/risk-based step-up có giới hạn và không tạo timing oracle rõ ràng.
- CAPTCHA/bot challenge là lớp bổ sung, không thay thế rate limit và password defense.
- Có quota/circuit breaker cho email/SMS provider.
- Giữ audit event ngay cả khi response public được gộp.

### 14.1. Rate limit response

HTTP 429 có thể được trả khi client vượt giới hạn theo contract, kèm Retry-After nếu phù hợp. Đây là thông tin về trạng thái request/rate control, không nên kèm chi tiết như ngưỡng bí mật, tài khoản nào bị khóa hoặc risk score. Rate limit cần tránh cho phép attacker phân biệt account existence qua quota khác nhau quá rõ.

### 14.2. Account lockout

Lockout có thể bảo vệ password guessing nhưng cũng bị lạm dụng để từ chối dịch vụ cho người dùng. Cân nhắc progressive throttling, risk-based challenges, thông báo out-of-band và cơ chế mở khóa có xác thực. Public error trước khi xác thực không nên tiết lộ tài khoản đang locked.

## 15. Thiết kế kiến trúc error mapping

Một kiến trúc tốt tách exception nội bộ khỏi response serializer:

~~~mermaid
flowchart TD
    C[Client request] --> A[Authentication endpoint]
    A --> S[Service and dependency calls]
    S --> E[Internal error classifier]
    E --> P[Public error mapping policy]
    E --> L[(Structured diagnostic log)]
    P --> R[Safe response serializer]
    R --> C
    L --> O[Restricted observability]
    O --> I[Incident and support workflow]
~~~

### 15.1. Error classifier

Classifier ánh xạ exception/decision sang nhóm nội bộ ổn định. Không để mỗi controller tự viết message theo cảm tính. Một bảng mapping có thể gồm:

| Internal category | Public category | Diagnostic |
| --- | --- | --- |
| Invalid credentials | AUTHENTICATION_FAILED | PASSWORD_MISMATCH |
| Principal missing | AUTHENTICATION_FAILED | PRINCIPAL_NOT_FOUND |
| Account restricted | AUTHENTICATION_FAILED hoặc ACCOUNT_ACTION_REQUIRED theo trạng thái xác thực | ACCOUNT_DISABLED |
| Invalid/expired MFA | MFA_VERIFICATION_FAILED | MFA_CHALLENGE_INVALID |
| Token invalid/revoked | SESSION_INVALID | TOKEN_REVOKED |
| Policy denied | ACCESS_DENIED hoặc STEP_UP_REQUIRED | RISK_POLICY_DENY |
| Upstream unavailable | TEMPORARY_FAILURE | IDP_UNAVAILABLE |
| Unexpected exception | INTERNAL_ERROR | EXCEPTION_FINGERPRINT |

Public mapping phải dựa trên endpoint, authentication state và privacy policy. Không ánh xạ một cách máy móc mọi reason thành cùng message nếu người dùng đã xác thực và cần hành động khắc phục cụ thể.

### 15.2. Response contract

Một API error contract có thể gồm:

- HTTP status theo semantics.
- Public code ổn định.
- Message đã localization hoặc message key.
- Correlation/reference ID opaque.
- Optional retry guidance không tiết lộ policy nội bộ.

Không trả internal reason, stack, raw exception, query, service hostname hoặc token. Client nên dựa vào public code để hiển thị UX, không parse message tự do.

## 16. Pseudocode: login response chống enumeration

Ví dụ khái niệm cho password login. Thư viện KDF, storage và rate limit cần được triển khai bằng thành phần đã được đánh giá:

~~~ts
async function login(identifier, password, requestContext) {
  await rateLimiter.check({
    source: requestContext.sourceKey,
    identifierKey: keyedPseudonym(identifier)
  });

  const principal = await principalStore.findByNormalizedIdentifier(identifier);
  const verifier = principal?.passwordVerifier ?? configuredDummyVerifier();

  // Dùng profile KDF tương đương cho principal có hoặc không có.
  const passwordMatches = await passwordVerifier.verify(password, verifier);
  const accountEligible = Boolean(
    principal &&
    principal.status === "ACTIVE" &&
    !principal.loginRestricted
  );

  if (!principal || !passwordMatches || !accountEligible) {
    await securityAudit.record({
      event: "LOGIN_FAILURE",
      reason: classifyInternalLoginFailure(principal, passwordMatches),
      principalRef: principal?.safeReference ?? null,
      sourceRef: requestContext.safeSourceReference
    });

    return publicError({
      status: 401,
      code: "AUTHENTICATION_FAILED",
      message: "Không thể hoàn tất đăng nhập với thông tin đã cung cấp."
    });
  }

  return continueWithMfaOrSession(principal, requestContext);
}
~~~

Đây là pseudocode, không phải API production. Cần lưu ý:

- Rate limit/admission control phải bảo vệ trước chi phí KDF.
- Dummy verifier cần có thuật toán/tham số tương đương profile hiện hành; migration nhiều thuật toán cần đánh giá timing riêng.
- Không log identifier/password thô; keyedPseudonym cần khóa riêng được bảo vệ.
- Internal audit phân biệt nguyên nhân trong hệ thống có quyền; public response giữ chung.
- Account status/risk policy phải được kiểm tra lại trước khi tạo session.
- Không tạo session nếu MFA/step-up còn chưa hoàn tất.
- Không trả account state hoặc internal reason trong response.

## 17. Ví dụ tình huống: password reset và account enumeration

Một dịch vụ có endpoint POST /password/forgot nhận email. Phiên bản đầu trả:

- Email chưa tồn tại: 404 với body “User not found”.
- Email tồn tại: 200 với body “Reset link sent”.

Attacker có thể gửi danh sách email và phân loại tài khoản theo status/body. Phiên bản an toàn hơn:

1. Chuẩn hóa input và áp dụng rate limit theo source/recipient reference.
2. Tạo operation reference opaque.
3. Tra cứu principal trong backend.
4. Nếu principal đủ điều kiện, tạo reset challenge có purpose, expiry và one-time consume rồi ghi outbox để gửi tới contact đã xác minh.
5. Nếu principal không tồn tại, không tạo challenge nhưng vẫn trả cùng response public.
6. Response cho cả hai trường hợp dùng cùng status, shape và message: “Nếu có tài khoản phù hợp, hướng dẫn sẽ được gửi tới kênh đã đăng ký.”
7. Worker gửi thông báo bất đồng bộ; không chờ email provider chỉ ở nhánh principal tồn tại.
8. Audit ghi kết quả nội bộ với access control và không lưu reset token plaintext trong log.
9. Người dùng mở ứng dụng/trang chính thức và hoàn tất recovery; token cũ hoặc đã dùng bị từ chối với thông báo chung.

### Các điểm cần kiểm thử

- Response body/status/headers có nhất quán không?
- Timing giữa email tồn tại và không tồn tại có chênh lệch đo được không?
- Email/SMS có chỉ được gửi khi principal đủ điều kiện không?
- Rate limit có ngăn spam mà không tạo account-existence oracle không?
- Reset token có purpose binding, expiry và one-time consume không?
- Log, trace và queue có chứa token/PII không cần thiết không?

## 18. Tiêu chí chấp nhận và kiểm thử

| Tình huống | Kết quả mong đợi |
| --- | --- |
| Login với email không tồn tại | Public response tương đương credential sai; internal reason được ghi riêng |
| Login với password sai | Không tiết lộ email đúng hay sai |
| Login với account locked/disabled | Không tiết lộ trạng thái trước khi xác minh; có recovery path an toàn |
| Forgot password với email tồn tại/không tồn tại | Cùng public status, shape và message |
| Registration với email đã dùng/chưa dùng | Không tạo account enumeration nếu policy yêu cầu giữ kín |
| MFA code sai/hết hạn | Thông báo chung; không lộ factor inventory/challenge state |
| Passkey assertion invalid | Không lộ credential ID hoặc số lượng authenticator |
| SSO subject chưa liên kết | Không tiết lộ mapping/tenant state cho unauthenticated caller |
| Refresh token revoked | Public session error chung; internal reason phân biệt |
| API nhận input sai định dạng | 400 theo contract, không echo secret/PII |
| Rate limit bị vượt | 429/Retry-After theo contract; không lộ ngưỡng/risk score nội bộ |
| Identity provider timeout | Thông báo tạm thời; internal diagnostic ghi dependency failure |
| Unexpected exception | Không có stack trace/hostname/query trong response |
| Unknown account và wrong password | Timing distribution được kiểm tra; dummy KDF giảm khác biệt |
| Password verifier dùng KDF legacy | Timing/migration được theo dõi, không tạo oracle dễ khai thác |
| Reset email được gửi | Gửi bất đồng bộ sau khi challenge commit; không làm response tiết lộ principal |
| Correlation ID do client tự gửi | Được validate hoặc thay bằng opaque server ID; không cấp quyền tra cứu |
| Error response chứa input người dùng | Không echo; HTML được escape, tránh reflected XSS |
| Authentication response được cache | Cache-Control no-store cho nội dung nhạy cảm |
| Log/tracing nhận Authorization header | Redaction loại bỏ token/cookie/OTP/secret |
| Support tra cứu correlation ID | Chỉ nhân viên có quyền xem diagnostic cần thiết; có audit access |
| User đã xác thực đủ mức | Có thể nhận hướng dẫn cụ thể hơn theo policy mà không lộ dữ liệu cho session yếu |
| Localization thay đổi | Không có ngôn ngữ nào tiết lộ nhiều trạng thái tài khoản hơn |

### Chỉ số vận hành

Theo dõi số public error theo category, internal reason distribution, tỷ lệ login failure, reset request, rate limit, upstream failure, response latency p50/p95/p99, chênh lệch timing giữa các nhóm thử nghiệm, email/SMS delivery, secret redaction findings và support correlation lookup. Không đưa email, phone, token hoặc raw user ID vào metric label.

## 19. Bài tập tự kiểm tra

Một hệ thống hỗ trợ password login, passkey, TOTP, SSO và password recovery. Đội bảo mật phát hiện endpoint forgot password trả 404 cho email chưa đăng ký và 200 cho email đã đăng ký. Login endpoint cũng trả “Mật khẩu sai” khi tài khoản tồn tại nhưng trả “Không tìm thấy người dùng” khi không tồn tại.

Hãy:

1. Liệt kê các tín hiệu có thể dùng để enumerate account ngoài message text.
2. Thiết kế public response và internal reason code cho login, registration, reset, MFA và SSO.
3. Chọn HTTP status phù hợp và giải thích vì sao không trả 200 cho mọi lỗi.
4. Mô tả cách dùng dummy verifier và kiểm thử timing side-channel.
5. Thiết kế outbox/asynchronous email delivery để response reset không phụ thuộc account existence.
6. Xác định dữ liệu không được ghi vào log, trace, support ticket và error page.
7. Thiết kế correlation ID để hỗ trợ điều tra mà không trở thành credential.
8. Viết test case cho response parity, rate limit, localization, cache và secret redaction.

**Gợi ý đánh giá:** lời giải tốt phải phân biệt public response với internal diagnostics, giữ nhất quán các trường hợp cần ẩn, cân bằng timing, dùng HTTP semantics, bảo vệ PII/secret và vẫn cung cấp hướng dẫn khắc phục hữu ích cho người dùng.

---

**Ghi nhớ:** generic error bảo vệ người dùng bằng cách chỉ tiết lộ thông tin cần thiết ở ranh giới công khai. Với login/recovery, đừng để message, status, response shape, timing hoặc side effect tiết lộ tài khoản và authenticator có tồn tại hay không. Giữ reason code chi tiết trong structured log có kiểm soát; không ghi password, OTP, token, cookie hoặc recovery secret. Dùng response contract nhất quán, HTTP semantics đúng, correlation ID opaque, rate limit và kiểm thử enumeration. Thông báo chung vẫn cần chỉ ra bước tiếp theo an toàn — quyền riêng tư không đồng nghĩa với việc bỏ mặc người dùng.
