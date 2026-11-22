# Giới hạn tần suất cấp phát và ghi nhận sự kiện an toàn

> **Module:** `SECURITY_TOKEN_SECURITY_JWT` — **Security - JSON Web Token (JWT)**. **Chương:** Cấp phát token. Bài viết áp dụng cho hệ thống JWT nói chung, không phụ thuộc ngôn ngữ lập trình, nền tảng hoặc framework.

## 1. Vì sao endpoint cấp phát token cần được bảo vệ?

Endpoint phát hành hoặc làm mới token là điểm nhạy cảm trong hệ thống xác thực và ủy quyền. Một yêu cầu thành công có thể tạo credential mới; một yêu cầu thất bại liên tục có thể tiêu tốn CPU, truy vấn identity provider, policy engine, kho khóa hoặc hệ thống lưu trạng thái. Nếu không giới hạn và giám sát phù hợp, endpoint này có thể bị lợi dụng để:

- thử mật khẩu, mã OTP, client secret hoặc refresh token;
- tạo lượng lớn JWT để gây tải cho issuer và resource server;
- lạm dụng refresh token để duy trì quyền truy cập hoặc dò tìm trạng thái phiên;
- khai thác endpoint cấp token làm điểm khuếch đại request tới dịch vụ phụ thuộc;
- tạo nhiều phiên hoặc token bất thường để che giấu hành vi chiếm đoạt;
- gây từ chối dịch vụ bằng cách khóa nhầm tài khoản hoặc làm cạn quota của người dùng khác.

Hai biện pháp bổ trợ nhau:

1. **Rate limiting / abuse control:** giới hạn tốc độ và quy mô yêu cầu theo danh tính, client, nguồn truy cập, grant và tài nguyên.
2. **Security event logging / monitoring:** ghi nhận sự kiện có cấu trúc để phát hiện bất thường, điều tra, kiểm toán và cải thiện chính sách.

Rate limit giúp ngăn hoặc làm chậm hành vi lạm dụng; log giúp hiểu điều gì đã xảy ra. Cả hai phải được thiết kế theo rủi ro, không chỉ thêm một bộ đếm IP và ghi toàn bộ request vào file.

## 2. Xác định những luồng cần giới hạn

Không phải mọi endpoint trong hệ thống token có cùng chi phí hoặc cùng rủi ro. Cần phân loại luồng:

| Luồng | Rủi ro chính | Điều cần kiểm soát |
| --- | --- | --- |
| Đăng nhập / password grant ở hệ thống legacy | Thử mật khẩu, credential stuffing | Tốc độ thử sai, nguồn truy cập, tài khoản, client, MFA |
| Client authentication | Dò client ID/secret hoặc lạm dụng workload | Client identity, credential, nguồn và quota riêng |
| Authorization code / đổi code | Code replay, dò code, lạm dụng callback | Client, code một lần, redirect URI, PKCE và trạng thái giao dịch |
| Refresh token | Dò token, reuse, tạo access token liên tục | Token family/grant, client binding, rotation, reuse detection |
| Token exchange / delegation | Mở rộng quyền hoặc chuỗi exchange bất thường | Actor, subject, audience, grant và độ sâu delegation |
| Client credentials | Tạo token hàng loạt bằng workload | Service identity, audience, scope và quota của workload |
| Token dùng một lần | Thử mã xác minh/reset hoặc replay | Chủ thể, mục đích, giao dịch và trạng thái đã dùng |
| JWKS/metadata và endpoint hỗ trợ | Request flood làm tăng tải phụ thuộc | Cache, giới hạn tải và bảo vệ endpoint công khai |

Rate limit phải được áp dụng ở những tầng phù hợp: gateway/edge, authorization server, dịch vụ xác thực và kho trạng thái. Một giới hạn ở gateway không thay thế kiểm soát trong issuer, vì request có thể đi qua đường nội bộ khác hoặc đến trực tiếp dịch vụ.

## 3. Chọn chiều giới hạn phù hợp

Một bộ đếm chỉ theo địa chỉ IP thường không đủ. Người dùng hợp lệ có thể dùng chung IP qua NAT, mạng doanh nghiệp hoặc nhà mạng; kẻ tấn công có thể phân tán request qua nhiều IP. Cần kết hợp nhiều chiều và chọn khóa dựa trên dữ liệu đã được xác minh.

| Chiều giới hạn | Dùng khi nào | Lưu ý |
| --- | --- | --- |
| IP / network prefix | Trước xác thực, giảm flood và dò quét | Chỉ tin IP do proxy/gateway tin cậy xác định; NAT có thể tạo false positive |
| Account / subject | Đăng nhập, MFA, refresh và thao tác theo người dùng | Chỉ dùng định danh đã chuẩn hóa; không để client tự khai subject quyết định quota |
| Client ID | Client credentials, authorization code, token exchange | Client ID phải gắn với client đã xác thực hoặc được đăng ký |
| Credential / key fingerprint | Phát hiện một credential bị thử hoặc lạm dụng | Không log hoặc dùng secret nguyên bản làm khóa; dùng fingerprint/HMAC có kiểm soát |
| Session / grant / refresh family | Refresh, token exchange và phiên người dùng | Phải gắn với trạng thái grant đã xác minh |
| Tenant / organization | Giới hạn tổng mức tiêu thụ và tránh một tenant chiếm tài nguyên | Kiểm tra membership; không tin tenant từ request |
| Device / risk context | Khi có tín hiệu thiết bị đáng tin cậy | Không dùng fingerprint yếu làm danh tính duy nhất |
| Endpoint / operation class | Phân biệt request rẻ và request tốn tài nguyên | Tách quota cho password verification, signing, introspection và refresh |

### 3.1. Kết hợp quota thay vì chọn một khóa duy nhất

Một yêu cầu có thể phải thỏa mãn đồng thời:

- quota tổng cho endpoint;
- quota theo client;
- quota theo account/subject hoặc grant;
- quota theo IP/network;
- quota theo tenant;
- quota riêng cho thao tác đắt tiền.

Ví dụ, một client hợp lệ không được vượt quota tổng của chính nó dù gửi từ nhiều IP; một IP gây flood không được làm mọi tài khoản sau NAT bị khóa lâu dài. Chính sách kết hợp cần có mức giới hạn và hành vi riêng cho từng chiều.

### 3.2. Không tin định danh trước khi xác thực

Ở endpoint đăng nhập, `account_id` hoặc `username` trong request chưa phải định danh đã xác minh. Có thể dùng giá trị đã chuẩn hóa làm một chiều chống brute force, nhưng phải giới hạn độ dài, canonicalization và nguy cơ kẻ tấn công cố ý tạo nhiều khóa khác nhau. Sau khi xác thực, bổ sung quota theo subject ID ổn định.

Với client credentials, chỉ áp quota theo client ID sau khi client đã được xác thực hoặc khi ID đã được tra cứu trong registry có kiểm soát. Không cho phép gửi một client ID bất kỳ để làm tăng quota hoặc khóa client khác.

## 4. Chọn thuật toán rate limiting

Các thuật toán khác nhau có trade-off về độ chính xác, độ phức tạp và khả năng chịu burst.

| Thuật toán | Cách hoạt động | Ưu điểm | Hạn chế |
| --- | --- | --- | --- |
| Fixed window | Đếm request trong từng khoảng thời gian cố định | Đơn giản, dễ triển khai | Có thể burst lớn ở ranh giới hai cửa sổ |
| Sliding log | Lưu thời điểm từng request trong cửa sổ trượt | Chính xác theo từng request | Tốn bộ nhớ và thao tác lưu trữ |
| Sliding window counter | Kết hợp cửa sổ hiện tại và trước đó | Gần đúng cửa sổ trượt, tiết kiệm hơn | Kết quả phụ thuộc cách ước lượng |
| Token bucket | Token trong bucket được nạp theo tốc độ; mỗi request tiêu thụ token | Cho phép burst có giới hạn và kiểm soát tốc độ dài hạn | Cần quản lý trạng thái bucket và thời gian |
| Leaky bucket / queue | Request được xử lý theo tốc độ thoát ổn định | Làm mượt tải | Có thể tăng độ trễ và cần quản lý hàng đợi |

Token bucket thường là lựa chọn thực tế cho endpoint cần cho phép một lượng burst nhỏ nhưng vẫn giới hạn tốc độ trung bình. Ví dụ bucket có dung lượng 10 và nạp 1 token/giây có thể cho phép tối đa 10 request ngay khi đầy, sau đó trung bình 1 request/giây. Đây chỉ là ví dụ minh họa; giá trị thật cần được đo và điều chỉnh theo năng lực dịch vụ.

### 4.1. Chọn giới hạn theo chi phí và rủi ro

Không nên dùng cùng một quota cho mọi thao tác:

- Password verification có thể tốn CPU do thuật toán băm mật khẩu.
- MFA verification có thể gọi dịch vụ ngoài hoặc gửi thông báo.
- Token signing có thể sử dụng HSM/KMS và bị giới hạn throughput.
- Refresh token có thể cần đọc/ghi trạng thái, rotation và reuse detection.
- Token exchange có thể gọi nhiều hệ thống và thực hiện policy evaluation.

Có thể dùng cost unit: một request đăng nhập tiêu thụ nhiều đơn vị hơn request đọc metadata; hoặc tách hẳn quota theo operation. Rate limit phải phản ánh tài nguyên bị tiêu thụ, không chỉ số lượng HTTP request.

## 5. Thiết lập ngưỡng và phản hồi khi vượt giới hạn

Ngưỡng nên được xác định từ baseline lưu lượng hợp lệ, năng lực hạ tầng, chi phí xử lý và threat model. Không có một con số chuẩn dùng cho mọi issuer.

Một chính sách nên định nghĩa:

- giới hạn burst;
- tốc độ nạp lại hoặc cửa sổ thời gian;
- quota theo client, subject, IP, tenant và operation;
- mức tăng cường khi có tín hiệu rủi ro;
- thời gian cooldown và điều kiện phục hồi;
- ngoại lệ có kiểm soát cho workload quan trọng;
- cách phản hồi, ghi log và cảnh báo.

Khi vượt giới hạn, endpoint thường trả HTTP `429 Too Many Requests` và có thể kèm `Retry-After` cho biết thời điểm client nên thử lại. Response không nên tiết lộ thông tin nhạy cảm như tài khoản có tồn tại, trạng thái khóa nội bộ hoặc ngưỡng chống gian lận cụ thể.

Ví dụ response:

~~~http
HTTP/1.1 429 Too Many Requests
Retry-After: 30
Content-Type: application/json
Cache-Control: no-store

{
  "error": "temporarily_limited",
  "error_description": "Please retry later."
}
~~~

Giá trị 30 giây chỉ là minh họa. Thời gian thực tế có thể là số giây hoặc HTTP-date theo định dạng được hỗ trợ. Không trả `Retry-After` quá dài hoặc quá ngắn một cách tùy tiện; cần đồng bộ với cơ chế cooldown.

### 5.1. Không tạo điều kiện cho account lockout DoS

Nếu chỉ cần gửi nhiều request tới một username để khóa tài khoản, kẻ tấn công có thể cố tình làm người dùng hợp lệ mất quyền đăng nhập. Cần cân nhắc:

- giới hạn theo nhiều chiều, không chỉ account;
- dùng progressive delay hoặc yêu cầu MFA/challenge theo rủi ro;
- tránh khóa cứng tài khoản chỉ dựa trên số lần request từ nguồn không đáng tin;
- giữ thông báo lỗi bên ngoài chung, tránh xác nhận tài khoản có tồn tại;
- có cơ chế phục hồi và hỗ trợ người dùng hợp lệ;
- phát hiện nhiều tài khoản bị thử từ một nguồn và một tài khoản bị thử từ nhiều nguồn.

Rate limit nên làm giảm khả năng brute force mà không trở thành công cụ từ chối dịch vụ đối với nạn nhân.

## 6. Triển khai rate limit trong hệ thống phân tán

Nếu issuer chạy nhiều instance, bộ đếm trong bộ nhớ từng instance có thể bị vượt qua bằng cách phân tán request. Ví dụ mỗi node cho phép 10 request/phút; với 5 node, client có thể nhận tổng cộng 50 request/phút nếu không có điều phối chung.

Các lựa chọn:

- kho trạng thái dùng chung với thao tác tăng/kiểm tra nguyên tử;
- gateway phân phối quota tập trung;
- phân vùng quota theo client/tenant và cấp lease có giới hạn cho từng node;
- thuật toán approximate counter khi yêu cầu cho phép sai số;
- kết hợp local limiter để bảo vệ tức thời và global limiter để bảo vệ quota tổng.

### 6.1. Tính nguyên tử và đồng hồ

Cập nhật bộ đếm phải tránh race condition. Hai request đồng thời không được cùng đọc quota còn một lượt rồi cả hai đều được chấp nhận. Token bucket cần cập nhật số token và timestamp theo thao tác nguyên tử hoặc script giao dịch phù hợp.

Trong môi trường phân tán:

- dùng nguồn thời gian nhất quán hoặc thời gian do kho trạng thái cung cấp;
- xử lý clock drift và reset counter;
- đặt TTL cho key bộ đếm để tránh tăng trưởng vô hạn;
- bảo vệ kho rate limit khỏi request flood và truy cập trái phép;
- xử lý cache eviction, failover và partition theo chính sách;
- không dùng một khóa toàn cục duy nhất gây hot key nếu tải lớn.

### 6.2. Fail-open hay fail-closed?

Nếu kho rate limit không truy cập được, hệ thống phải có chính sách theo loại endpoint:

| Endpoint / rủi ro | Hướng xử lý thường phù hợp |
| --- | --- |
| Endpoint công khai, chi phí thấp | Có thể dùng local fallback có giới hạn và cảnh báo |
| Password/MFA verification | Ưu tiên bảo vệ tài nguyên xác thực; tránh bỏ toàn bộ giới hạn |
| Token issuance quyền cao | Cân nhắc từ chối tạm thời hoặc giới hạn chặt khi không kiểm tra được quota |
| Refresh token / reuse detection | Không bỏ qua kiểm tra bảo mật bắt buộc chỉ để duy trì tính sẵn sàng |
| Metadata công khai đã cache | Có thể phục vụ từ cache theo chính sách |

Không có một lựa chọn fail-open/fail-closed áp dụng cho mọi trường hợp. Quyết định phải dựa trên thiệt hại nếu bỏ qua giới hạn, thời gian outage, khả năng fallback và yêu cầu sẵn sàng. Nếu dùng local fallback, cần giới hạn tổng mức cho phép để nhiều node không cộng dồn thành quota lớn ngoài dự kiến.

## 7. Progressive throttling và phát hiện hành vi bất thường

Rate limiting có thể thích ứng theo mức rủi ro thay vì chỉ dùng một ngưỡng cố định:

- tăng delay sau nhiều lần xác thực thất bại;
- yêu cầu MFA hoặc challenge bổ sung khi có tín hiệu bất thường;
- hạ quota cho client có tỷ lệ lỗi cao hoặc hành vi khác baseline;
- giới hạn refresh khi phát hiện reuse hoặc nhiều thiết bị/địa điểm bất thường;
- tạm dừng client credential có dấu hiệu bị lộ;
- tăng giám sát khi có nhiều request tới nhiều account hoặc nhiều audience trong thời gian ngắn.

Tín hiệu có thể bao gồm số lần thất bại, tốc độ, phân bố IP/network, client, thiết bị đã xác minh, tỷ lệ refresh, số grant được tạo, phạm vi audience/scope và các sự kiện thu hồi. Tín hiệu phải được diễn giải trong bối cảnh; ví dụ nhiều người dùng cùng IP ở văn phòng không tự động là tấn công.

Không nên để một mô hình rủi ro tự động khóa tài khoản hàng loạt mà không có ngưỡng, audit và cơ chế phục hồi. Với hành động có ảnh hưởng lớn, cần policy rõ ràng và có thể cần phê duyệt/điều tra.

## 8. Ghi nhận sự kiện an toàn trong quy trình token

Log bảo mật cần cho biết ai/điều gì đã yêu cầu token, quyết định ra sao, vì sao bị từ chối và token được cấp trong ngữ cảnh nào. Không phải mọi request đều cần ghi toàn bộ dữ liệu; cần phân loại sự kiện.

| Sự kiện | Trường hợp ghi nhận |
| --- | --- |
| Token issuance attempt | Có yêu cầu cấp token mới |
| Token issuance success | Issuer đã ký và trả token |
| Token issuance denied | Xác thực, client, grant, policy hoặc rate limit từ chối |
| Authentication failure | Bằng chứng xác thực không hợp lệ |
| Rate limit exceeded | Vượt quota theo một chiều được xác định |
| Refresh success / denied | Refresh được chấp nhận hoặc từ chối |
| Refresh token reuse detected | Token đã rotation bị sử dụng lại |
| Grant/session revoked | Grant hoặc phiên bị thu hồi |
| Scope/audience denied | Yêu cầu vượt quyền hoặc resource không được phép |
| Signing/key error | KMS/HSM hoặc khóa ký gặp lỗi |
| Suspicious issuance pattern | Mẫu phát hành bất thường được phát hiện |
| Configuration/policy change | Thay đổi quota, issuer, scope hoặc chính sách phát hành |

Nên phân biệt:

- **Audit log:** bằng chứng về hành động và quyết định quan trọng, cần tính toàn vẹn và khả năng truy vết.
- **Security telemetry:** số liệu và tín hiệu để phát hiện hành vi bất thường, thường được tổng hợp theo thời gian.
- **Application/debug log:** hỗ trợ xử lý lỗi vận hành; không nên dùng thay audit log cho quyết định bảo mật.

## 9. Thiết kế cấu trúc security event

Log nên là sự kiện có cấu trúc, dễ lọc và liên kết giữa các thành phần. Ví dụ:

~~~json
{
  "event_type": "token_issuance_denied",
  "event_time": "2026-11-16T12:30:00Z",
  "issuer": "https://auth.example.net",
  "client_id": "dashboard",
  "subject_ref": "pseudonymous-subject-id",
  "audience": "https://api.example.net/orders",
  "grant_type": "authorization_code",
  "requested_scope": ["orders:read", "orders:refund"],
  "granted_scope": [],
  "decision": "deny",
  "reason_code": "rate_limit_exceeded",
  "limiting_dimension": "client",
  "retry_after_seconds": 30,
  "correlation_id": "req-8f71c2",
  "source_network": "203.0.113.0/24"
}
~~~

Đây là ví dụ schema nội bộ, không phải định dạng bắt buộc. Các trường có thể thay đổi theo chính sách quyền riêng tư và hệ thống logging.

Những nguyên tắc thiết kế:

- dùng event name và reason code ổn định, có tài liệu;
- timestamp ở UTC và có độ chính xác phù hợp;
- ghi correlation/request ID để nối sự kiện giữa gateway, issuer và dịch vụ phụ thuộc;
- ghi client, issuer, audience, grant và kết quả ở mức cần thiết;
- lưu scope yêu cầu và scope được cấp khi phục vụ audit, nhưng tránh log nội dung nhạy cảm không cần thiết;
- phân biệt lý do từ chối nội bộ với thông báo lỗi chung trả cho client;
- ghi dimension bị giới hạn mà không tiết lộ ngưỡng bí mật hoặc quy tắc chống gian lận.

### 9.1. Ghi nhận sự kiện thành công và thất bại

Không chỉ log lỗi. Sự kiện thành công giúp xác định hành vi phát hành bất thường, chẳng hạn một client tạo nhiều token mới hoặc một subject nhận token cho nhiều audience trong thời gian ngắn.

Tuy nhiên, ghi mọi request ở mức chi tiết có thể tạo lượng log lớn. Có thể kết hợp:

- audit đầy đủ cho phát hành thành công, thu hồi, thay đổi policy và sự kiện đặc quyền;
- log đầy đủ các quyết định bị từ chối quan trọng;
- metric tổng hợp cho lưu lượng thông thường;
- sampling có kiểm soát cho debug/telemetry, nhưng không làm mất các sự kiện audit bắt buộc.

Không sampling các sự kiện quan trọng như refresh reuse, signing key compromise hoặc policy change nếu chúng cần được lưu đầy đủ.

## 10. Không ghi token, secret hoặc dữ liệu xác thực nguyên vẹn

Một lỗi nghiêm trọng là log request/response nguyên bản ở endpoint token. Access token, refresh token, authorization code, client secret, password, OTP, private key hoặc proof có thể được sử dụng lại nếu bị lộ.

Không ghi các dữ liệu sau vào log thông thường:

- JWT nguyên vẹn hoặc chuỗi bearer authorization;
- refresh token và token exchange input;
- mật khẩu, OTP, recovery code;
- client secret, API key, private key hoặc secret HMAC;
- authorization code, PKCE verifier;
- toàn bộ payload có dữ liệu cá nhân hoặc thông tin nghiệp vụ nhạy cảm;
- header/cookie có session credential.

Thay thế bằng:

- định danh subject đã giả danh hóa (pseudonymized) hoặc ID nội bộ được phép;
- fingerprint/HMAC của credential nếu thật sự cần correlation, với khóa HMAC quản lý riêng;
- `jti` hoặc token reference khi có nhu cầu audit và chính sách cho phép;
- reason code thay cho raw exception chứa dữ liệu nhạy cảm;
- scope/audience ở mức cần thiết để phân tích quyền.

Nếu cần lưu fingerprint token, không dùng hash yếu hoặc một giá trị có thể bị dò offline khi token có entropy thấp; nên dùng HMAC với khóa riêng được bảo vệ và giới hạn quyền truy cập. Không bao giờ ghi token để “debug cho dễ”.

### 10.1. Chống log injection và rò rỉ

Dữ liệu như username, client name, user-agent hoặc error description có thể chứa newline, delimiter hay chuỗi điều khiển. Trước khi log:

- serialize theo định dạng có cấu trúc thay vì ghép chuỗi;
- escape ký tự điều khiển;
- giới hạn chiều dài field;
- loại bỏ hoặc che thông tin không cần thiết;
- không đưa raw exception/stack trace có secret vào event;
- không để dữ liệu client điều khiển event type, severity hoặc audit identity.

## 11. Bảo vệ kho log và thời gian lưu

Log bảo mật có giá trị điều tra nhưng cũng là mục tiêu có thể chứa dữ liệu nhạy cảm. Cần bảo vệ cả tính bí mật, toàn vẹn và khả dụng:

- phân quyền đọc/ghi theo vai trò; dịch vụ phát hành chỉ được ghi, không tự sửa/xóa audit đã gửi;
- truyền log qua kênh xác thực và mã hóa;
- dùng storage có kiểm soát sửa/xóa, append-only hoặc cơ chế tamper-evident khi phù hợp;
- đồng bộ thời gian hệ thống để ghép chuỗi sự kiện;
- backup và kiểm tra khả năng khôi phục;
- đặt retention theo mục đích, pháp lý, quyền riêng tư và nhu cầu điều tra;
- xóa hoặc tổng hợp dữ liệu khi hết thời hạn lưu;
- giám sát việc log pipeline bị dừng, trễ hoặc mất sự kiện.

Không giữ log vô thời hạn chỉ vì có thể hữu ích trong tương lai. Dữ liệu định danh và địa chỉ mạng cần được bảo vệ, giới hạn người truy cập và lưu trong thời gian cần thiết.

### 11.1. Đảm bảo sự kiện không bị mất khi phát hành

Có thể xảy ra tình huống issuer ký token thành công nhưng hệ thống audit không ghi được sự kiện, hoặc audit ghi thành công nhưng response trả token thất bại. Cần định nghĩa mức bảo đảm:

- Với sự kiện bắt buộc cho kiểm toán, cân nhắc transactional outbox hoặc hàng đợi bền vững để tránh mất event giữa các bước.
- Nếu không thể ghi audit bắt buộc, chính sách có thể yêu cầu dừng phát hành hoặc chuyển sang trạng thái degraded có kiểm soát.
- Không để logging outage làm sập toàn bộ hệ thống nếu sự kiện chỉ là telemetry không bắt buộc; có thể buffer và cảnh báo.
- Gắn event với request/correlation ID và trạng thái phát hành, tránh ghi hai sự kiện thành công cho một token do retry.
- Không lưu token nguyên vẹn trong outbox hoặc message queue.

Cách xử lý phụ thuộc yêu cầu tuân thủ và mức rủi ro. Phải quyết định rõ sự kiện nào là bắt buộc, sự kiện nào có thể trì hoãn và cách phục hồi khi pipeline trở lại.

## 12. Metrics, cảnh báo và phản ứng

Log chỉ hữu ích khi có khả năng phát hiện và hành động. Nên theo dõi các metric tổng hợp:

| Metric | Ý nghĩa |
| --- | --- |
| Token issuance requests / success / denied | Lưu lượng và tỷ lệ quyết định |
| Rate limit hits theo dimension | Chiều quota thường xuyên bị vượt |
| Authentication failure rate | Tín hiệu brute force hoặc credential stuffing |
| Refresh requests / reuse detected | Hành vi refresh bất thường |
| Tokens per client / subject / audience | Phát hiện client hoặc subject tạo token bất thường |
| Scope/audience denial rate | Phát hiện yêu cầu vượt quyền hoặc cấu hình sai |
| Signing latency / KMS errors | Tình trạng khóa và năng lực ký |
| Rate-limit store latency/errors | Khả năng thực thi giới hạn |
| Audit pipeline lag/drop | Nguy cơ mất dữ liệu điều tra |
| 429 rate and Retry-After | Tác động của throttling tới client |

Tránh dùng subject ID, token ID hoặc IP làm label có cardinality rất cao trong metric thời gian thực. Dùng log/event để tra cứu chi tiết và metric tổng hợp theo client class, endpoint, region hoặc reason code.

### 12.1. Tín hiệu cảnh báo ví dụ

- Tỷ lệ xác thực thất bại tăng đột biến ở một client hoặc network.
- Một client phát hành token nhanh hơn baseline hoặc cho quá nhiều audience.
- Refresh token reuse xảy ra nhiều lần hoặc trên nhiều subject.
- Nhiều account bị thử từ cùng một nguồn.
- Một account bị thử từ nhiều nguồn phân tán.
- Tỷ lệ 429 tăng bất thường sau một lần thay đổi cấu hình.
- KMS/HSM lỗi hoặc signing latency tăng cao.
- Audit event bị mất, trễ hoặc không thể truy cập.

Alert phải có ngưỡng, thời gian duy trì, mức độ nghiêm trọng và người/nhóm chịu trách nhiệm. Không cảnh báo mỗi lần 429 đơn lẻ; cần phát hiện xu hướng và mức tác động.

### 12.2. Quy trình phản ứng sự cố

Khi phát hiện lạm dụng:

1. Xác định endpoint, client, subject/grant và chiều quota bị ảnh hưởng.
2. Phân biệt lỗi client hợp lệ, cấu hình sai và hành vi tấn công.
3. Tăng giới hạn bảo vệ hoặc áp dụng progressive throttling theo chính sách.
4. Nếu credential/grant bị xâm phạm, thu hồi hoặc vô hiệu hóa theo phạm vi; không chỉ tăng rate limit.
5. Bảo toàn audit event và log liên quan; kiểm tra xem token đã phát hành có bị sử dụng trái phép không.
6. Khôi phục quyền truy cập cho người dùng hợp lệ bị ảnh hưởng bởi false positive.
7. Điều chỉnh chính sách, cập nhật baseline và ghi lại kết quả xử lý.

Không khóa hàng loạt tài khoản hoặc client chỉ dựa trên một IP chung. Hành động phải có phạm vi, thời hạn và khả năng hoàn tác.

## 13. Quy trình tham khảo cho endpoint phát hành token

~~~mermaid
flowchart TD
    A["Nhận yêu cầu token"] --> B["Kiểm tra quota tổng / IP / endpoint"]
    B --> C{"Vượt giới hạn?"}
    C -- "Có" --> L["Ghi rate_limit_exceeded"]
    L --> R["Trả 429 / Retry-After"]
    C -- "Không" --> D["Xác thực client và bằng chứng"]
    D --> E["Áp dụng quota subject / client / grant"]
    E --> F{"Được phép tiếp tục?"}
    F -- "Không" --> G["Ghi authentication/policy denial"]
    G --> H["Trả lỗi chung theo giao thức"]
    F -- "Có" --> I["Đánh giá grant, scope, audience và rủi ro"]
    I --> J{"Policy cho phép phát hành?"}
    J -- "Không" --> G
    J -- "Có" --> K["Ký token và ghi issuance event"]
    K --> M["Trả token qua kênh an toàn"]
~~~

Luồng thực tế có thể ghi nhận attempt trước khi xác thực, sau đó ghi outcome. Các sự kiện cần cùng correlation ID để ghép được một giao dịch. Quota theo subject chỉ nên dùng sau khi subject đã được xác minh; quota IP/client ở tầng trước có thể bảo vệ dịch vụ trước khi xác thực.

## 14. Checklist triển khai

**Rate limiting:**

- [ ] Đã phân loại endpoint theo chi phí và mức rủi ro.
- [ ] Có giới hạn tổng, client, subject/grant, IP và tenant phù hợp.
- [ ] Không dùng định danh chưa xác minh làm nguồn quyết định quota đặc quyền.
- [ ] Chọn thuật toán phù hợp burst, throughput và độ chính xác.
- [ ] Bộ đếm phân tán có cập nhật nguyên tử và TTL.
- [ ] Có phản hồi 429/Retry-After rõ ràng, không lộ thông tin nhạy cảm.
- [ ] Có kiểm soát account lockout DoS và false positive.
- [ ] Có chính sách fail-open/fail-closed theo endpoint.
- [ ] Có progressive throttling và cơ chế phục hồi.
- [ ] Kiểm thử đồng thời, nhiều node, cache failure và retry.

**Security event logging:**

- [ ] Có event schema và reason code ổn định.
- [ ] Ghi nhận attempt, success, denial, refresh, reuse, revoke và key/policy events phù hợp.
- [ ] Có correlation ID và timestamp UTC.
- [ ] Không log JWT, refresh token, password, OTP, client secret hoặc private key.
- [ ] Có pseudonymization, redaction và giới hạn kích thước field.
- [ ] Chống log injection.
- [ ] Kho log có kiểm soát truy cập, toàn vẹn, backup và retention.
- [ ] Có cảnh báo khi log pipeline lỗi hoặc mất event.
- [ ] Có dashboard/alert cho issuance, 429, auth failure, refresh reuse và signing errors.
- [ ] Có quy trình điều tra, thu hồi và khôi phục sau false positive.

## 15. Tài liệu tham khảo

- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): endpoint token, grant và response lỗi OAuth.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700): bảo vệ authorization server, refresh token và các luồng OAuth.
- [RFC 6585 — Additional HTTP Status Codes](https://www.rfc-editor.org/rfc/rfc6585): định nghĩa HTTP 429 Too Many Requests.
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110): ngữ nghĩa HTTP, bao gồm header Retry-After.
- [OWASP Automated Threats to Web Applications](https://owasp.org/www-project-automated-threats-to-web-applications/): phân loại và kiểm soát các hành vi tự động lạm dụng ứng dụng.
- [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): thiết kế log bảo mật, dữ liệu không nên ghi và bảo vệ log.
- [NIST SP 800-92 — Guide to Computer Security Log Management](https://csrc.nist.gov/pubs/sp/800/92/final): quản lý, lưu trữ và phân tích log an toàn.

**Ghi nhớ:** Giới hạn tần suất phải được áp dụng theo nhiều chiều và theo chi phí/rủi ro của từng luồng; sự kiện bảo mật phải đủ để truy vết nhưng không làm lộ credential hoặc dữ liệu nhạy cảm. Rate limit bảo vệ năng lực phát hành, còn audit, metrics và cảnh báo giúp phát hiện, điều tra và xử lý hành vi lạm dụng.

