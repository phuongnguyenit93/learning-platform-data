# Account enumeration — Ngăn dò tìm sự tồn tại của tài khoản

> **Chương:** Error và privacy  
> **Chủ đề:** Account enumeration

**Account enumeration** là kỹ thuật xác định một tài khoản có tồn tại trong hệ thống hay không bằng cách quan sát phản hồi của ứng dụng. Attacker có thể thử tên đăng nhập, email, số điện thoại, mã nhân viên hoặc định danh khác trên các chức năng như đăng nhập, đăng ký, quên mật khẩu, MFA, recovery, invitation và API. Nếu hệ thống phản hồi khác nhau tùy trạng thái tài khoản, attacker có thể suy ra danh tính hợp lệ ngay cả khi không biết password.

Account enumeration thường không cần khai thác lỗ hổng thực thi mã. Chỉ cần một khác biệt nhỏ về thông báo, HTTP status, redirect, kích thước response, thời gian xử lý, CAPTCHA, rate limit hoặc luồng MFA là có thể tạo thành oracle. Danh sách account hợp lệ sau đó có thể bị dùng cho credential stuffing, password spraying, phishing có mục tiêu, spam, social engineering hoặc suy luận thông tin cá nhân.

Bài học thuộc module **SECURITY_AUTHENTICATION_FUNDAMENTALS**, kết nối authentication, password, MFA, recovery, SSO, error handling và privacy. Trọng tâm là nhận diện các oracle tiết lộ trạng thái account, thiết kế phản hồi khó phân biệt, giới hạn lạm dụng mà không tạo điều kiện khóa nhầm người dùng, và kiểm thử toàn bộ luồng có thể tiết lộ sự tồn tại của danh tính.

## 1. Kết quả học tập

Sau bài học, người học có thể:

1. Giải thích account enumeration và phân biệt nó với credential stuffing, password spraying và brute force.
2. Nhận diện các oracle qua nội dung, status code, redirect, timing, response size, rate limit và giao diện.
3. Phân tích các endpoint có nguy cơ như login, registration, password reset, MFA, recovery, invitation và account linking.
4. Thiết kế phản hồi chung cho danh tính tồn tại và không tồn tại mà vẫn giữ UX hữu ích.
5. Giảm timing và side-channel leakage bằng cách xử lý bất đồng bộ, đường xử lý tương đồng và giới hạn hợp lý.
6. Áp dụng rate limit đa chiều, abuse detection và CAPTCHA/risk challenge đúng thời điểm.
7. Tránh biến account lockout hoặc recovery thành công cụ DoS và xác minh danh tính trái phép.
8. Cân bằng privacy, khả năng tiếp cận, vận hành hỗ trợ và nhu cầu discoverability có chủ đích.
9. Xây dựng test plan để đo khả năng phân biệt account state qua mọi giao diện và API.

## 2. Account enumeration là gì?

Một ứng dụng có thể cung cấp nhiều chức năng cần biết một định danh có tồn tại. Ví dụ người dùng nhập email để đăng nhập, đăng ký, khôi phục password hoặc gửi lời mời. Nếu kết quả khác nhau giữa account tồn tại và không tồn tại, hệ thống vô tình cung cấp một phép kiểm tra danh sách người dùng.

Ví dụ:

| Request | Phản hồi dễ bị khai thác |
| --- | --- |
| Đăng nhập email chưa tồn tại | “Tài khoản không tồn tại” |
| Đăng nhập email tồn tại nhưng password sai | “Mật khẩu không đúng” |
| Quên password email chưa tồn tại | “Không tìm thấy người dùng” |
| Quên password email tồn tại | “Đã gửi email đặt lại” |
| Đăng ký email đã dùng | “Email đã được đăng ký” |
| Đăng ký email mới | “Đăng ký thành công” |

Attacker không cần đăng nhập thành công. Chỉ cần gửi các request thử và phân loại phản hồi là có thể thu thập danh sách account.

### 2.1. Enumeration có thể tiết lộ điều gì?

- Email hoặc username có đăng ký dịch vụ;
- Số điện thoại được liên kết với account;
- Nhân viên thuộc tổ chức hoặc tenant;
- Account có bật MFA hay không;
- Account đang active, suspended, locked hoặc chưa xác minh;
- Người dùng có liên kết với IdP/SSO nào;
- Một recovery channel hoặc authenticator cụ thể có tồn tại;
- Account thuộc nhóm đặc quyền hoặc có vai trò nhạy cảm.

Không phải mọi thông tin trên đều phải được che giấu trong mọi sản phẩm. Tuy nhiên, việc tiết lộ cần có mục đích, quyền truy cập và chính sách rõ ràng.

## 3. Phân biệt enumeration với các kiểu tấn công đăng nhập

| Kỹ thuật | Mục tiêu | Khác biệt chính |
| --- | --- | --- |
| **Account enumeration** | Tìm account/định danh tồn tại | Khai thác khác biệt trong phản hồi |
| **Credential stuffing** | Thử cặp username/password bị lộ từ nơi khác | Dùng credential đã có, thường trên nhiều account |
| **Password spraying** | Thử một số password phổ biến trên nhiều account | Giảm nguy cơ khóa do thử quá nhiều trên một account |
| **Brute force** | Đoán password hoặc mã xác thực | Tập trung thử nhiều giá trị bí mật |
| **Password reset abuse** | Lạm dụng chức năng recovery | Có thể gửi spam, chiếm account hoặc gây gián đoạn |
| **Identity discovery** | Tìm danh tính qua directory hoặc tính năng chia sẻ | Có thể là hành vi hợp lệ nếu sản phẩm chủ ý công khai |
| **User tracking** | Liên kết hoạt động với một người dùng | Có thể dùng identifier, cookie hoặc fingerprint thay vì endpoint auth |

Enumeration thường là bước chuẩn bị giúp các cuộc tấn công khác hiệu quả hơn. Một danh sách email hợp lệ giúp attacker tập trung phishing hoặc credential stuffing vào account thật.

## 4. Threat model và tác động quyền riêng tư

### 4.1. Attacker có thể là ai?

- Người dùng Internet không có account;
- Người dùng đã đăng ký nhưng muốn dò account khác;
- Botnet hoặc script tự động;
- Attacker có một số email/số điện thoại từ nguồn công khai;
- Đối thủ muốn xác định nhân viên, khách hàng hoặc thành viên một tổ chức;
- Insider có quyền gọi API nhưng không có quyền xem directory.

### 4.2. Mục tiêu của attacker

- Thu thập danh sách account hợp lệ;
- Xác định account quản trị hoặc nhân viên mục tiêu;
- Biết một người có sử dụng dịch vụ nhạy cảm hay không;
- Xác định account nào có MFA hoặc phương thức recovery yếu;
- Chuẩn bị credential stuffing hoặc phishing;
- Gửi spam hoặc gây lockout;
- Liên kết danh tính giữa nhiều dịch vụ.

### 4.3. Tác động

Account existence có thể là dữ liệu cá nhân. Việc tiết lộ email có account ở một dịch vụ sức khỏe, tài chính, giáo dục hoặc tổ chức cụ thể có thể tiết lộ mối quan hệ nhạy cảm. Với nền tảng doanh nghiệp, danh sách account còn giúp attacker lập sơ đồ nhân sự và chọn mục tiêu có quyền cao.

## 5. Các kênh tạo account enumeration

Enumeration có thể xuất hiện ngoài màn hình login. Cần kiểm tra toàn bộ vòng đời account.

| Kênh | Ví dụ leakage |
| --- | --- |
| Login | “Unknown user” khác “Wrong password” |
| Registration | “Email already registered” |
| Password reset | Chỉ account tồn tại mới nhận thông báo thành công |
| MFA enrollment | Báo rõ account đã có authenticator hay chưa |
| MFA challenge | Phản hồi khác nhau khi account bật/chưa bật MFA |
| Account recovery | “Không có recovery phone” hoặc “Email không khớp” |
| Invitation | Cho biết email đã thuộc tenant hay chưa |
| SSO discovery | Tiết lộ domain có IdP hoặc tenant nào |
| Account linking | Cho biết identity đã được liên kết với user khác |
| Username availability | API trả true/false cho từng username |
| Profile lookup | Tìm email hoặc số điện thoại để biết account |
| API/GraphQL | Resolver trả object/null hoặc error code khác nhau |
| Support workflow | Helpdesk xác nhận account tồn tại trước khi xác minh caller |

### 5.1. UI không phải toàn bộ bề mặt

Một trang web có thể hiển thị thông báo chung nhưng API phía sau vẫn trả mã lỗi phân biệt. GraphQL có thể trả data null trong một trường hợp và error với extension code trong trường hợp khác. Mobile app có thể hiển thị chung nhưng response JSON vẫn có field account_exists.

### 5.2. Side channel ngoài response body

Khác biệt có thể nằm trong:
- HTTP status;
- Header;
- Redirect URL;
- Response length;
- Thời gian phản hồi;
- Kích thước hoặc số lượng email/SMS được gửi;
- CAPTCHA hoặc challenge được bật;
- Rate limit counter;
- Connection close/reset;
- Audit hoặc telemetry mà người dùng có quyền xem.

## 6. Thiết kế phản hồi chung

Mục tiêu là làm cho attacker khó phân biệt account state từ phản hồi bên ngoài, trong khi hệ thống vẫn xử lý đúng ở phía server.

### 6.1. Login

Thông báo chung có thể là:

> Không thể đăng nhập bằng thông tin đã cung cấp. Hãy kiểm tra thông tin hoặc sử dụng quy trình khôi phục tài khoản.

Không nói rõ email chưa tồn tại, password sai, account bị khóa hay chưa xác minh trong cùng một endpoint công khai. Với account đã tồn tại nhưng đang bị khóa, hệ thống vẫn cần áp dụng policy nội bộ và thông báo qua kênh đã xác minh.

### 6.2. Password reset

Phản hồi có thể là:

> Nếu tài khoản phù hợp với thông tin đã cung cấp, chúng tôi sẽ gửi hướng dẫn tới kênh liên hệ đã đăng ký.

Thông điệp nên giống nhau dù account tồn tại hay không. Không khẳng định email đã được gửi nếu hệ thống chưa hoàn tất thao tác; có thể nói “nếu có account phù hợp, hướng dẫn sẽ được gửi”.

### 6.3. Registration

Nếu email đã được đăng ký, có thể trả lời chung rằng yêu cầu đã được tiếp nhận và hướng dẫn sẽ được gửi tới địa chỉ đó nếu cần hành động. Người dùng hợp lệ nhận thông báo riêng trong hộp thư. Không trả thẳng “email đã tồn tại” trên endpoint công khai nếu privacy policy yêu cầu bảo vệ sự tồn tại của account.

### 6.4. Không tạo thông báo gây hiểu nhầm

Phản hồi chung không có nghĩa nói dối về trạng thái giao dịch. Nếu request bị rate limit, lỗi hệ thống hoặc thiếu định dạng, có thể trả lỗi tương ứng mà không tiết lộ account state. Nội dung nên đúng với hành động hệ thống thực sự đã thực hiện.

## 7. Login flow chống enumeration

Một login flow có thể xác minh account nội bộ nhưng dùng phản hồi bên ngoài tương đương.

~~~mermaid
flowchart TD
    A["Nhận username và password"] --> B["Chuẩn hóa định danh"]
    B --> C["Áp dụng rate limit và abuse checks"]
    C --> D["Tra account hoặc dummy verifier"]
    D --> E["Chạy password verification"]
    E --> F{"Xác thực hợp lệ và account được phép?"}
    F -->|"Có"| G["Tạo session theo policy"]
    F -->|"Không"| H["Không tạo session"]
    G --> I["Phản hồi thành công"]
    H --> J["Phản hồi lỗi chung"]
~~~

### 7.1. Dummy password verifier

Nếu account không tồn tại, hệ thống có thể thực hiện một phép password hash verification với dummy verifier có tham số tương đương. Điều này giảm khác biệt timing giữa “không có account” và “password sai”.

Dummy verifier phải được tạo bằng cùng thuật toán/chi phí phù hợp và không được gắn với account thật. Không dùng một nhánh trả về ngay lập tức cho user không tồn tại trong khi nhánh account thật thực hiện KDF tốn thời gian.

### 7.2. Xử lý account state

Account có thể tồn tại nhưng disabled, locked, pending verification hoặc suspended. Sau khi xác thực thông tin đăng nhập, server áp dụng trạng thái nội bộ và policy. Bên ngoài nên tránh tiết lộ trạng thái cụ thể nếu không có quyền; thông báo hỗ trợ có thể gửi qua kênh đã xác minh.

### 7.3. Không bỏ qua bảo vệ password

Chống enumeration không thay thế password hashing, breached-password screening, rate limit, MFA hoặc bot defense. Không làm password verification yếu đi chỉ để giảm thời gian phản hồi.

## 8. Timing side channel

Ngay cả khi nội dung và status giống nhau, thời gian xử lý có thể khác đủ để phân loại account.

Ví dụ:
- Account không tồn tại trả về ngay;
- Account tồn tại thực hiện Argon2/bcrypt;
- Account bật MFA cần thêm một lần truy vấn;
- Account bị khóa trả về trước khi xác minh password;
- Account có linked IdP gọi thêm dịch vụ ngoài.

### 8.1. Cách giảm timing leakage

- Dùng dummy verifier cho account không tồn tại;
- Giữ đường xử lý tương đồng ở các trạng thái;
- Tránh truy vấn phụ chỉ chạy cho một nhóm account nếu có thể;
- Dùng queue/background processing cho email/SMS;
- Chuẩn hóa thao tác database và cache;
- Đo phân phối latency trên nhiều lần thử, không chỉ một request;
- Áp dụng rate limit để giảm khả năng lấy mẫu lớn.

### 8.2. Không dựa vào sleep cố định

Thêm một khoảng delay cố định có thể làm chậm toàn bộ hệ thống và vẫn không xóa được khác biệt thống kê. Attacker có thể lấy nhiều mẫu hoặc nhận ra phân phối thời gian khác nhau. Tập trung vào đường xử lý tương đồng, xử lý bất đồng bộ và giảm thông tin có thể quan sát.

### 8.3. Timing không cần bằng nhau tuyệt đối

Mục tiêu thực tế là giảm khả năng phân biệt đáng tin cậy trong threat model, không phải đảm bảo mọi request có thời gian giống hệt nhau. Cần cân bằng privacy, latency, tài nguyên và chống DoS.

## 9. HTTP status, headers và response shape

Phản hồi nên có semantics ổn định cho các trạng thái account khác nhau.

### 9.1. Status code

Nếu endpoint login dùng 404 cho user không tồn tại và 401 cho password sai, status code đã trở thành oracle. Cân nhắc cùng status cho các trường hợp thông tin đăng nhập không hợp lệ, trong khi vẫn giữ status riêng cho lỗi không liên quan đến account state như malformed request hoặc rate limit.

### 9.2. Response body

Tránh field như:
- account_exists;
- user_found;
- mfa_enabled;
- recovery_method_count;
- account_status;
- registered_email;
- next_step chỉ xuất hiện khi account tồn tại.

Response schema có thể giữ cùng cấu trúc, còn hành động cụ thể được gửi qua kênh đã xác minh.

### 9.3. Headers và redirects

Kiểm tra:
- Location header;
- Retry-After;
- WWW-Authenticate;
- Set-Cookie;
- Cache-Control;
- Header tùy chỉnh từ gateway;
- Redirect tới IdP hoặc recovery route.

Không để redirect hoặc header tiết lộ account đang dùng SSO, MFA hay trạng thái bị khóa nếu caller chưa được phép biết.

### 9.4. Cache

Phản hồi login/recovery không nên bị cache công khai. Dùng Cache-Control phù hợp và tránh shared cache trộn response giữa account/request. Cache key phải không làm lộ identifier và không phục vụ nhầm response cá nhân cho request khác.

## 10. Password reset và recovery không tiết lộ account

Password reset là endpoint enumeration phổ biến vì hệ thống phải gửi link chỉ khi account tồn tại.

### 10.1. Quy trình an toàn

1. Nhận identifier và chuẩn hóa theo quy tắc account.
2. Áp dụng rate limit và abuse detection.
3. Trả phản hồi chung ngay theo contract.
4. Nếu account tồn tại và đủ điều kiện, tạo recovery transaction phía server.
5. Gửi email/SMS qua queue, không chặn response công khai để chờ provider.
6. Token có TTL, purpose binding, one-time consumption và gắn với subject.
7. Khi token được dùng, kiểm tra trạng thái hiện tại và áp dụng recovery policy.
8. Thông báo tới kênh đã đăng ký theo policy.
9. Ghi audit không chứa token/OTP.

### 10.2. Không tạo token cho account không tồn tại

Không cần tạo một recovery token thật cho account không tồn tại. Tuy nhiên, response bên ngoài vẫn cần giống nhau. Có thể enqueue một task no-op hoặc xử lý cùng contract mà không phát token có thể bị lạm dụng.

### 10.3. Không tiết lộ kênh recovery

Tránh trả “đã gửi SMS tới số kết thúc bằng 42” trước khi người dùng được xác minh đủ mức. Nếu cần hiển thị gợi ý, chỉ hiển thị sau một bước xác thực đã được policy chấp nhận và che dữ liệu đủ mạnh.

## 11. Registration và account linking

### 11.1. Registration

Một endpoint kiểm tra email đã dùng có thể là oracle trực tiếp. Các lựa chọn:
- Dùng phản hồi chung và gửi hướng dẫn qua email;
- Xác minh email trước khi hoàn tất tạo account;
- Có thể cho phép người dùng thử đăng nhập/recovery qua một flow an toàn;
- Tránh endpoint username availability công khai nếu không có nhu cầu sản phẩm rõ ràng.

Nếu sản phẩm có directory công khai, cần định nghĩa thông tin nào được công khai và ai có thể tìm kiếm, thay vì vô tình tiết lộ từ lỗi đăng ký.

### 11.2. Account linking

Khi liên kết IdP hoặc social identity, không tiết lộ email/identity đã liên kết với account khác trước khi xác minh quyền kiểm soát cả hai danh tính. Không tự động gộp account chỉ vì email giống nhau.

### 11.3. Invitation

Thông báo “email này đã thuộc tenant” có thể tiết lộ quan hệ tổ chức. Có thể trả lời chung rằng lời mời đã được tiếp nhận; gửi hướng dẫn cho người có quyền qua kênh đã xác minh. Admin có quyền quản lý tenant có thể được xem trạng thái membership trong giao diện quản trị có authorization.

## 12. MFA enrollment và challenge

MFA endpoint có thể tiết lộ account có bật MFA, loại authenticator hoặc số lượng factor.

### 12.1. Không tiết lộ factor trước khi xác minh

Không trả danh sách đầy đủ “SMS, TOTP, passkey” cho bất kỳ ai chỉ biết email. Có thể hiển thị một lựa chọn generic hoặc gợi ý đã che sau khi password/primary factor được xác minh và policy cho phép.

### 12.2. MFA challenge

Nếu account không bật MFA nhưng account khác bật, response không nên để lộ trạng thái đó cho attacker chưa xác thực. Có thể dùng flow có cấu trúc chung và chỉ phát challenge thật sau khi primary authentication thành công.

### 12.3. Enrollment và recovery

Thêm/gỡ authenticator cần xác thực lại và thông báo. Recovery factor không được dùng như endpoint discovery. Các thao tác thay đổi phải gắn với account, purpose, session và TTL.

## 13. SSO discovery và identity provider

Một số hệ thống chọn IdP theo email domain hoặc tenant. Nếu endpoint công khai cho biết “domain này dùng Okta/Entra/Google” hoặc “account không tồn tại trong tổ chức”, attacker có thể lập bản đồ tổ chức.

### 13.1. Domain discovery

Chỉ công khai IdP discovery nếu đó là yêu cầu sản phẩm. Có thể giới hạn bằng domain đã xác minh, tenant invitation hoặc flow có kiểm soát. Không trả danh sách tenant hoặc IdP nội bộ dựa trên email bất kỳ.

### 13.2. OIDC/SAML errors

Không làm lộ account existence qua lỗi tùy biến trước khi hoàn tất giao thức. Vẫn phải giữ các kiểm tra giao thức cần thiết như issuer, audience, redirect URI, state, nonce, signature và replay protection. Phản hồi chung không có nghĩa bỏ qua validation.

### 13.3. Tenant discovery có chủ đích

Một số SaaS cần người dùng tìm organization. Có thể cung cấp organization slug hoặc domain công khai do tổ chức chủ động công bố. Tách tính năng discoverability này khỏi endpoint login và không tiết lộ membership cá nhân.

## 14. API, GraphQL và mobile client

Enumeration thường dễ tự động hóa qua API hơn giao diện web.

### 14.1. API contract

- Dùng response schema nhất quán cho các account state không được công khai;
- Không trả field boolean tiết lộ account existence;
- Chuẩn hóa error code nội bộ thành response công khai phù hợp;
- Không để exception message hoặc stack trace lộ dữ liệu;
- Áp dụng rate limit ở gateway và service;
- Kiểm tra cả API version cũ.

### 14.2. GraphQL

Resolver có thể trả null, error path hoặc extension code khác nhau. Kiểm tra:
- Data shape;
- Error code/message;
- Resolver timing;
- Batch query;
- Alias và nested field;
- Introspection hoặc search resolver;
- DataLoader/cache key.

### 14.3. Mobile app

Không dựa vào việc app che thông báo. Attacker có thể gọi API trực tiếp hoặc phân tích response. Kiểm tra JSON, status, deep link, push notification, analytics event và lỗi offline. Không nhúng logic account existence chỉ ở client.

## 15. Rate limiting và abuse detection

Rate limit giảm khả năng attacker lấy đủ mẫu để enumerate và ngăn spam. Chỉ giới hạn theo IP là chưa đủ vì attacker có thể phân tán nguồn hoặc nhiều người dùng chung NAT.

### 15.1. Nhiều chiều giới hạn

Có thể kết hợp:
- IP/network/ASN;
- Account identifier đã chuẩn hóa hoặc keyed hash;
- Device/session/browser signal;
- Client application/API key;
- Tenant/organization;
- Endpoint và purpose;
- Tổng request theo thời gian;
- Tốc độ lỗi và tỷ lệ account mới được thử.

Không dùng raw email/phone trong metric rộng nếu không cần; có thể dùng keyed HMAC để gom nhóm định danh mà giảm lộ dữ liệu, với key và retention được quản lý.

### 15.2. Không tạo lockout DoS

Nếu mỗi lần nhập sai khiến account bị khóa, attacker có thể cố ý khóa account nạn nhân bằng cách gửi nhiều password sai. Ưu tiên throttling theo nhiều tín hiệu, progressive delay, risk challenge và bảo vệ password verification capacity. Nếu có account lock, cần recovery path an toàn và tránh tiết lộ trạng thái lock cho caller chưa xác thực.

### 15.3. CAPTCHA và challenge

CAPTCHA có thể tăng chi phí automation nhưng không phải giải pháp privacy hoặc authentication. Dùng theo risk/abuse signal, cung cấp phương án accessibility và tránh bật chỉ cho account tồn tại theo cách tạo oracle.

## 16. Timing, resource usage và các side channel khác

Ngoài thời gian, attacker có thể so sánh:
- CPU cost của password KDF;
- Số truy vấn database;
- Kích thước response;
- Thời điểm gửi email/SMS;
- Có tạo cookie/session hay không;
- Số lần redirect;
- Rate limit headers;
- Error correlation ID;
- Kích thước hoặc metadata của avatar/profile;
- Sự hiện diện của MFA setup endpoint.

Không nhất thiết phải làm mọi đường xử lý có cùng chi phí. Cần xác định tín hiệu có thể quan sát từ bên ngoài và đánh giá xem nó có đủ ổn định để suy ra account state hay không.

## 17. Privacy và discoverability có chủ đích

Không phải sản phẩm nào cũng cần ẩn hoàn toàn sự tồn tại của account. Một directory doanh nghiệp, mạng xã hội hoặc công cụ cộng tác có thể cần tìm người dùng. Điều quan trọng là phân biệt:
- Thông tin được công khai có chủ đích;
- Thông tin chỉ người dùng đã xác thực hoặc tenant admin được xem;
- Trạng thái account nội bộ không nên lộ;
- Thông tin nhạy cảm như recovery channel, MFA state hoặc suspension reason.

### 17.1. Chính sách discoverability

Xác định:
- Ai có thể tìm kiếm;
- Tìm bằng email, username, phone hay directory ID;
- Kết quả có hiển thị tên/avatar/organization không;
- Có opt-out hoặc privacy setting không;
- Có giới hạn tìm kiếm hàng loạt không;
- Dữ liệu được lưu và audit ra sao.

### 17.2. Không dùng phản hồi chung để phá UX

Nếu người dùng hợp lệ cần biết cách truy cập account của họ, có thể cung cấp hướng dẫn an toàn qua email đã xác minh, session hiện có hoặc support flow. Phản hồi công khai vẫn có thể chung, còn trợ giúp riêng được cung cấp sau khi xác minh phù hợp.

## 18. Logging, monitoring và incident response

Hệ thống cần quan sát enumeration mà không tự tạo thêm kho dữ liệu nhạy cảm.

### 18.1. Event nên ghi

- Endpoint và purpose;
- Kết quả công khai;
- Internal decision reason code;
- Identifier reference hoặc keyed pseudonym;
- IP/network và device risk theo policy;
- Số lần thử và phân phối endpoint;
- Correlation ID;
- Rate limit/CAPTCHA decision;
- Thời điểm và policy version.

Không ghi password, OTP, recovery code, access token hoặc session cookie.

### 18.2. Dấu hiệu enumeration

- Nhiều identifier khác nhau từ cùng nguồn;
- Một identifier được thử từ nhiều IP;
- Tốc độ cao trên password reset hoặc registration;
- Chuỗi username có pattern;
- Phân phối request qua nhiều tenant;
- Nhiều response được so sánh theo timing;
- Tỷ lệ account tồn tại/không tồn tại bất thường.

### 18.3. Phản ứng

- Throttle nguồn hoặc client đáng ngờ;
- Tăng risk challenge;
- Bảo vệ endpoint bị nhắm tới;
- Đánh giá dữ liệu account đã bị thu thập;
- Thông báo người dùng nếu có nguy cơ phishing/credential stuffing;
- Kiểm tra các lần đăng nhập tiếp theo;
- Điều chỉnh response contract và test regression.

Không tự động khóa hàng loạt account chỉ vì chúng bị dò; điều đó có thể giúp attacker gây DoS.

## 19. Pseudocode login chống enumeration

~~~text
login(identifier, password, request_context):
    normalized = normalize_identifier(identifier)
    enforce_multidimensional_rate_limits(
        identifier = keyed_hash(normalized),
        source = request_context.network,
        client = request_context.client
    )

    account = lookup_account(normalized)

    if account exists:
        verifier = account.password_verifier
    else:
        verifier = configured_dummy_password_verifier

    password_ok = verify_password(password, verifier)

    if account does not exist:
        authentication_ok = false
    else:
        authentication_ok = password_ok
            and account_is_eligible_for_authentication(account)

    if authentication_ok:
        session = create_session_with_current_policy(account)
        record_internal_success(account, request_context)
        return generic_success_contract(session)

    record_internal_failure(
        account_reference_if_known = account.reference,
        request_context = request_context
    )
    return generic_invalid_credentials_response()
~~~

Pseudocode chỉ minh họa logic. Thực tế cần xử lý timing, password KDF capacity, account lock policy, MFA, breached password, session rotation, audit, error mapping và chống race. Không trả account existence qua response, headers hoặc side effect quan sát được.

## 20. Pseudocode password reset không tiết lộ account

~~~text
request_password_reset(identifier, request_context):
    normalized = normalize_identifier(identifier)
    enforce_reset_rate_limits(
        identifier = keyed_hash(normalized),
        source = request_context.network
    )

    account = lookup_account(normalized)

    if account exists and account_is_recoverable(account):
        enqueue_recovery_message(
            account_reference = account.reference,
            purpose = PASSWORD_RESET,
            ttl = configured_short_ttl
        )
        record_internal_reset_request(account.reference)
    else:
        record_internal_nonmatching_request(
            identifier_reference = keyed_hash(normalized)
        )

    return same_public_response_for_all_account_states()
~~~

Không tạo recovery token có thể dùng cho account không tồn tại. Queue consumer cần kiểm tra account state và purpose trước khi gửi. Link/token phải gắn subject, TTL và one-time consumption; không đưa secret vào log hoặc URL analytics.

## 21. Kiểm thử account enumeration

Kiểm thử trong staging với account thử nghiệm ở các trạng thái khác nhau. Dùng cùng request context và lặp đủ số lần để so sánh phân phối phản hồi.

| Nhóm | Tình huống | Kết quả mong đợi |
| --- | --- | --- |
| Login | Email tồn tại + password sai so với email không tồn tại | Public response không phân biệt account state |
| Login state | Account active, locked, suspended, pending verification | Không lộ trạng thái nội bộ trước khi xác thực |
| Timing | So sánh latency của known/unknown identifier | Không có khác biệt ổn định dễ khai thác |
| Status | So sánh HTTP status | Cùng semantics cho credential failure |
| Body | So sánh JSON schema, message và length | Không có field account_exists/status |
| Headers | So sánh redirect, cookie, retry headers | Không lộ trạng thái account |
| Reset | Account tồn tại/không tồn tại | Cùng phản hồi công khai |
| Reset channel | Email/phone recovery | Không tiết lộ kênh trước xác minh |
| Registration | Email đã đăng ký/chưa đăng ký | Không lộ trực tiếp existence nếu policy yêu cầu |
| MFA | Account bật/chưa bật MFA | Không lộ trước primary authentication |
| MFA factor | Account có passkey/TOTP/SMS | Không trả danh sách factor cho caller chưa xác thực |
| Recovery | Account không có recovery factor | Không trả thông tin riêng tư |
| Invitation | Email thuộc tenant/chưa thuộc tenant | Phản hồi công khai không lộ membership |
| Account linking | Identity đã liên kết với account khác | Không tiết lộ owner trước khi xác minh |
| SSO discovery | Email domain có IdP/tenant | Chỉ tiết lộ theo discoverability policy |
| GraphQL | Null/error/extension code | Không có oracle qua resolver |
| Mobile API | JSON/deep link/push metadata | Không lộ trạng thái qua client protocol |
| Rate limit | Thử nhiều identifier từ một IP | Throttle theo nhiều chiều |
| Distributed source | Cùng identifier từ nhiều IP | Detection không chỉ dựa vào IP |
| Lockout DoS | Attacker cố khóa account nạn nhân | Không dễ khóa chỉ bằng request không xác thực |
| CAPTCHA | Known/unknown account | Không tạo challenge khác biệt có thể enumerate |
| Cache | Request khác identifier/tenant | Không dùng lại response sai scope |
| Logging | Debug/trace bật | Không ghi password, OTP hoặc token |
| Accessibility | CAPTCHA/challenge có phương án tiếp cận | Người dùng hợp lệ vẫn có đường sử dụng |

### 21.1. Phân tích thống kê timing

Không kết luận timing an toàn chỉ từ một vài request. Thu thập nhiều mẫu trong cùng điều kiện, so sánh median và phân phối, kiểm soát network noise và kiểm tra các nhóm account state. Mục tiêu là phát hiện khác biệt có thể khai thác ổn định, không đòi mọi request có thời gian tuyệt đối bằng nhau.

### 21.2. Bất biến bảo mật

- Public response không tiết lộ account existence ngoài discoverability policy;
- Status, headers, body và redirect không tạo oracle ngoài ý muốn;
- Reset/recovery không phát token cho định danh không phù hợp;
- Rate limit không dễ bị dùng để khóa account nạn nhân;
- MFA/recovery details chỉ lộ sau bước xác minh phù hợp;
- API, GraphQL và mobile có cùng chính sách privacy;
- Logs và telemetry không lưu bí mật xác thực.

## 22. Những lỗi triển khai thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| “User không tồn tại” khác “Password sai” | Dò account trực tiếp | Generic authentication failure |
| Reset trả “không tìm thấy email” | Thu thập account qua recovery | Generic reset response và queue |
| Dummy branch trả về ngay | Timing oracle | Dummy verifier và đường xử lý tương đồng |
| HTTP status khác nhau | Script phân loại account | Status semantics ổn định |
| JSON có account_exists | API oracle dù UI ẩn | Loại bỏ field và chuẩn hóa schema |
| MFA state lộ trước login | Attacker chọn mục tiêu MFA yếu | Chỉ tiết lộ sau xác minh |
| Lock account ngay khi sai | Attacker gây DoS | Throttling/risk-based controls |
| Chỉ rate limit theo IP | Distributed enumeration | Nhiều chiều identifier/client/network |
| CAPTCHA chỉ hiện cho account thật | Challenge trở thành oracle | Áp dụng theo risk, không theo existence |
| Email gửi đồng bộ | Timing tiết lộ account state | Queue và response chung |
| GraphQL trả error code riêng | Enumeration qua API | Chuẩn hóa resolver/error contract |
| SSO discovery quá chi tiết | Lộ tenant/IdP của tổ chức | Domain discovery có chủ đích |
| Helpdesk xác nhận email trước proofing | Social engineering | Xác minh caller và scoped support |
| Cache dùng chung response | Rò response giữa người dùng | Cache control và key đúng scope |
| Log raw identifier/secret | Tạo kho dữ liệu nhạy cảm | Pseudonymization và secret redaction |

## 23. Checklist production

1. **Threat model:** Account existence có nhạy cảm với người dùng/tenant này không?
2. **Endpoint inventory:** Login, registration, reset, MFA, recovery, invitation, linking và discovery đã được liệt kê?
3. **Response contract:** Body, status, headers và redirect có nhất quán theo privacy policy?
4. **Timing:** Known/unknown account có đường xử lý tương đồng; dummy verifier được dùng khi phù hợp?
5. **Async work:** Email/SMS và side effect được xử lý qua queue mà không tạo timing oracle?
6. **MFA:** Factor state không bị tiết lộ trước xác minh?
7. **Recovery:** Không tiết lộ recovery channel hoặc phát token sai subject/purpose?
8. **Registration:** Account existence không bị lộ qua availability API ngoài chủ đích?
9. **Federation:** SSO/IdP discovery được giới hạn theo tenant/domain policy?
10. **API coverage:** REST, GraphQL, mobile và legacy API cùng contract?
11. **Rate limit:** Có giới hạn theo identifier, source, client, tenant và endpoint?
12. **DoS resistance:** Không dễ khóa account nạn nhân bằng request không xác thực?
13. **CAPTCHA:** Chỉ bật theo risk và có accessibility path?
14. **Monitoring:** Có phát hiện enumeration nhưng không khóa account hàng loạt?
15. **Logging:** Không ghi password, OTP, token, cookie hoặc recovery secret?
16. **Privacy:** Identifier, IP và event được tối thiểu hóa, giới hạn truy cập và retention?
17. **Discoverability:** Directory công khai có mục đích, quyền, opt-out và rate limit?
18. **Testing:** Có so sánh status/body/header/timing và mọi account state trong regression suite?

## 24. Bài tập tình huống

Một nền tảng học tập có các endpoint:
- Login trả 404 nếu email không tồn tại và 401 nếu password sai;
- Password reset trả “Không tìm thấy tài khoản” khi email chưa đăng ký;
- Registration trả 409 nếu email đã tồn tại;
- MFA endpoint trả danh sách loại authenticator đang bật;
- GraphQL resolver trả null nếu không có user nhưng trả error code ACCOUNT_SUSPENDED nếu account bị khóa;
- Rate limit chỉ theo IP và tự khóa account sau năm lần đăng nhập sai.

Attacker dùng danh sách email từ nguồn công khai để dò account giảng viên và sau đó gửi phishing có mục tiêu.

**Yêu cầu:**

1. Xác định ít nhất **tám oracle** hoặc đường lộ account state trong hệ thống.
2. Thiết kế response contract chung cho login, reset, registration và MFA.
3. Đề xuất dummy verifier và cách kiểm tra timing side channel.
4. Thiết kế rate limit đa chiều mà không tạo lockout DoS.
5. Xác định dữ liệu nào có thể được công khai trong directory và dữ liệu nào cần bảo vệ.
6. Viết test cho REST, GraphQL và mobile API.
7. Đề xuất telemetry để phát hiện enumeration mà không lưu password/OTP hoặc lộ thêm dữ liệu cá nhân.

**Gợi ý đối chiếu:** Chuẩn hóa response/status/body/header; reset bất đồng bộ và phản hồi chung; không lộ MFA/recovery state trước primary authentication; dummy KDF; rate limit theo identifier và client/network; không khóa account chỉ dựa vào số lần thử không xác thực; monitor pattern thử nhiều định danh.

## 25. Ghi nhớ

- **Account enumeration** là suy ra account có tồn tại qua khác biệt trong phản hồi hoặc side channel.
- Enumeration có thể xảy ra ở login, registration, reset, MFA, recovery, invitation, account linking, SSO discovery và API.
- Generic error cần áp dụng nhất quán cho body, status, headers, redirect và response shape.
- Dummy password verifier và đường xử lý tương đồng giúp giảm timing leakage; delay cố định không phải giải pháp đầy đủ.
- Password reset nên trả phản hồi chung và xử lý email/SMS bất đồng bộ.
- MFA/recovery details chỉ được tiết lộ sau bước xác minh phù hợp.
- Rate limit cần đa chiều và tránh lockout dễ bị attacker khai thác để gây DoS.
- Discoverability có thể là tính năng hợp lệ, nhưng phải được thiết kế công khai có chủ đích và giới hạn.
- Logging/monitoring phải hỗ trợ phát hiện enumeration mà không lưu password, OTP, token hoặc recovery secret.

Account enumeration được kiểm soát tốt khi hệ thống **không biến những khác biệt nội bộ về trạng thái tài khoản thành tín hiệu công khai**, đồng thời vẫn cung cấp đường đăng nhập, recovery và hỗ trợ rõ ràng cho người dùng hợp lệ.
