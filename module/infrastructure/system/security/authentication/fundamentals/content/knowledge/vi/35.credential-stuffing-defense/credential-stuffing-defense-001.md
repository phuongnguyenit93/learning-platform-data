# Brute force — Phòng chống tấn công thử đoán mật khẩu

> **Chương:** Chống đoán credential  
> **Chủ đề:** Brute force  
> **Phạm vi:** Security Authentication Fundamentals — hiểu cách kẻ tấn công thử nhiều giá trị credential, phân biệt tấn công online và offline, thiết kế kiểm soát đăng nhập, lưu trữ password an toàn, phát hiện bất thường và ứng phó khi credential bị lộ.

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích brute force và phân biệt brute force, dictionary attack, password spraying và credential stuffing.
2. Phân tích sự khác nhau giữa đoán mật khẩu trực tiếp trên dịch vụ và crack password hash ngoại tuyến.
3. Đánh giá ảnh hưởng của độ dài, tính ngẫu nhiên, password reuse và tốc độ thử.
4. Thiết kế rate limiting, progressive delay và account protection mà không tạo điều kiện denial of service.
5. Chọn cách lưu password bằng password hashing chuyên dụng, salt và pepper phù hợp.
6. Kết hợp MFA, passkey, breached-password screening và recovery an toàn.
7. Xây dựng detection cho hành vi đoán mật khẩu phân tán, password spraying và login success đáng ngờ.
8. Thiết kế incident response khi phát hiện brute force hoặc khi password database bị lộ.
9. Kiểm thử hiệu quả của các biện pháp bảo vệ, khả năng phục hồi và tính sẵn sàng của đăng nhập.

## 1. Brute force là gì?

**Brute force attack** là cách thử nhiều giá trị credential cho tới khi tìm được giá trị được hệ thống chấp nhận. Với đăng nhập bằng mật khẩu, attacker gửi nhiều password candidate cho một hoặc nhiều account, dựa trên khả năng có một mật khẩu đủ yếu hoặc dễ đoán.

Ví dụ: Một endpoint đăng nhập cho phép thử mật khẩu không giới hạn. Attacker tự động gửi nhiều password candidate cho một tài khoản. Nếu một candidate trùng mật khẩu thật và không có kiểm soát bổ sung, attacker có thể đăng nhập.

Brute force khai thác một hoặc nhiều điểm yếu:

- Mật khẩu ngắn, phổ biến hoặc có thể đoán từ thông tin cá nhân;
- Một endpoint cho phép thử quá nhiều lần;
- Không có throttling hoặc kiểm soát theo nhiều chiều;
- Không có MFA hoặc phương thức chống phishing;
- Password hash dễ tính toán nếu database bị đánh cắp;
- Recovery hoặc reset password yếu hơn đăng nhập chính;
- Detection chỉ nhìn một IP nên bỏ sót tấn công phân tán.

Brute force không phải lúc nào cũng thử mọi chuỗi có thể có. Trong thực tế, attacker thường kết hợp từ điển, mẫu phổ biến, biến thể, thông tin công khai và tự động hóa để giảm số lần thử cần thiết.

## 2. Phân biệt các kiểu tấn công đoán credential

Các thuật ngữ thường bị dùng lẫn nhau, nhưng chúng mô tả những cách tấn công khác nhau.

| Kiểu tấn công | Cách hoạt động | Dấu hiệu thường gặp |
| --- | --- | --- |
| **Brute force** | Thử nhiều password candidate cho một account hoặc một nhóm account | Nhiều lần thử trên cùng account hoặc theo một chiến lược đoán |
| **Dictionary attack** | Thử danh sách từ/cụm từ/mật khẩu phổ biến và biến thể | Candidate tập trung vào password phổ biến |
| **Password spraying** | Thử một số ít password phổ biến trên rất nhiều account | Một password hoặc pattern nhắm tới nhiều subject |
| **Credential stuffing** | Dùng cặp username/password bị lộ từ dịch vụ khác | Nhiều cặp credential có sẵn, thường phân tán nguồn thử |
| **Offline password cracking** | Thử candidate trực tiếp trên password hash đã đánh cắp | Không cần gọi endpoint đăng nhập của dịch vụ |

**Điểm phân biệt quan trọng:** Credential stuffing dùng credential đã biết hoặc bị rò rỉ; brute force/dictionary attack cố đoán password. Password spraying là chiến lược thử ít password trên nhiều account để tránh ngưỡng khóa theo từng account.

Các kiểu tấn công có thể kết hợp. Một attacker có thể dùng spraying để tìm account yếu, sau đó dùng brute force có mục tiêu hoặc credential stuffing để mở rộng truy cập.

## 3. Online brute force và offline cracking

Hai mô hình này cần các lớp phòng thủ khác nhau.

### Online brute force

Attacker gửi yêu cầu tới dịch vụ đang hoạt động:

- Login form của website;
- API xác thực;
- VPN hoặc remote access gateway;
- SSH hoặc dịch vụ quản trị;
- OIDC/identity provider login;
- Endpoint recovery/reset password.

Dịch vụ có thể quan sát request và áp dụng rate limit, throttling, risk evaluation, MFA, CAPTCHA theo ngữ cảnh và account protection.

### Offline password cracking

Attacker có password hash từ database backup, SQL injection, compromised server, insider misuse hoặc bản sao lưu bị lộ. Họ thử password candidate trên thiết bị của mình và so sánh kết quả hash mà không gọi login service.

Trong tình huống này:

- Rate limit tại login endpoint không có tác dụng;
- CAPTCHA không có tác dụng;
- Account lockout không có tác dụng;
- MFA không làm cho password hash khó crack hơn;
- Chất lượng password hashing, salt, pepper và độ mạnh password quyết định khả năng chống crack.

| Kiểm soát | Online brute force | Offline cracking |
| --- | --- | --- |
| Rate limit/throttling | Có tác dụng trực tiếp | Không |
| Account protection | Có tác dụng trực tiếp | Không |
| CAPTCHA/risk challenge | Có thể tăng chi phí tấn công | Không |
| MFA/passkey | Ngăn password đơn lẻ đủ để đăng nhập | Không bảo vệ hash bị crack |
| Argon2id/scrypt/bcrypt/PBKDF2 phù hợp | Không giới hạn request trực tiếp | Là lớp bảo vệ chính cho hash |
| Salt riêng từng password | Không giới hạn request trực tiếp | Ngăn rainbow table và chia sẻ công việc hash giữa các account |
| Pepper bảo vệ riêng | Không giới hạn request trực tiếp | Có thể làm hash khó khai thác hơn khi DB riêng lẻ bị lộ |

Phòng thủ đầy đủ cần xử lý cả hai mô hình. Không thể lấy rate limit online để thay thế password storage an toàn.

## 4. Vì sao mật khẩu yếu dễ bị đoán?

Khả năng chống đoán phụ thuộc vào độ dài, tính khó đoán và cách người dùng tạo/lưu mật khẩu.

Nếu một mật khẩu được tạo ngẫu nhiên từ một bảng chữ cái có N ký tự và dài L ký tự, không gian có thể có là:

\[
N^L
\]

Công thức này chỉ phản ánh mật khẩu thực sự được chọn ngẫu nhiên từ tập ký tự đó. Mật khẩu do con người tự đặt thường có cấu trúc, từ quen thuộc, mẫu bàn phím, năm sinh hoặc biến thể phổ biến. Không nên đánh giá sức mạnh chỉ bằng số loại ký tự xuất hiện.

Một cụm từ dài gồm nhiều từ không liên quan có thể dễ nhớ và khó đoán hơn mật khẩu ngắn có chữ hoa, chữ thường, số và ký hiệu nhưng theo mẫu quen thuộc.

### Những mật khẩu dễ bị đoán

- Password mặc định hoặc mật khẩu dùng chung;
- Tên dịch vụ + năm hiện tại;
- Tên người dùng, tên công ty hoặc thông tin công khai;
- Chuỗi bàn phím hoặc dãy số phổ biến;
- Một password được tái sử dụng ở nhiều dịch vụ;
- Mật khẩu ngắn với quy tắc biến thể dễ dự đoán.

### Hướng dẫn người dùng

- Dùng password manager để tạo và lưu mật khẩu duy nhất;
- Ưu tiên passphrase dài, khó đoán và không tái sử dụng;
- Không dùng thông tin cá nhân hoặc password theo mẫu phổ biến;
- Bật MFA/passkey khi dịch vụ hỗ trợ;
- Không chia sẻ password qua chat/email;
- Thay password khi có bằng chứng bị lộ hoặc bị chiếm, thay vì ép đổi định kỳ không có căn cứ.

## 5. Rate limiting và throttling cho đăng nhập

Với online brute force, dịch vụ cần giới hạn tốc độ thử. Một bộ giới hạn chỉ theo IP thường không đủ vì attacker có thể phân tán request qua nhiều nguồn; một bộ giới hạn chỉ theo account lại có thể bị dùng để khóa tài khoản nạn nhân.

### Kết hợp nhiều chiều

- **Per account:** giới hạn số lần thử trên một subject trong cửa sổ thời gian;
- **Per IP/network:** giới hạn nguồn gửi quá nhiều request;
- **Per device/session:** nhận diện một client hoặc thiết bị lặp lại;
- **Per tenant/application:** phát hiện một tenant hoặc client bị nhắm mục tiêu;
- **Global/service:** bảo vệ capacity của toàn bộ authentication service;
- **Risk-based:** điều chỉnh kiểm soát theo hành vi và độ tin cậy của request.

Không dùng username chưa xác minh làm khóa rate limit duy nhất. Cần chuẩn hóa định danh account theo cùng quy tắc mà hệ thống dùng để tra cứu, đồng thời tránh tạo khác biệt có thể bị khai thác để enumeration.

### Progressive delay

Thay vì khóa vĩnh viễn ngay sau một số lần thất bại, hệ thống có thể tăng dần độ trễ hoặc yêu cầu bước kiểm tra bổ sung:

1. Một vài lần thất bại: ghi nhận và áp dụng giới hạn cơ bản;
2. Thất bại lặp lại: tăng delay hoặc yêu cầu risk challenge;
3. Pattern đáng ngờ: hạn chế nguồn, yêu cầu MFA hoặc xác minh bổ sung;
4. Tín hiệu takeover rõ: tạm khóa luồng đăng nhập và chuyển incident workflow.

Thời gian delay, cửa sổ đếm và ngưỡng cần được hiệu chỉnh theo lưu lượng thật. Không cho attacker biết chính xác ngưỡng bảo vệ nội bộ qua thông báo công khai.

### Pseudocode policy minh họa

`````````
evaluateLoginAttempt(accountRef, source, device):
    accountRate = accountLimiter.check(accountRef)
    sourceRate = sourceLimiter.check(source.network)
    deviceRate = deviceLimiter.check(device.reference)
    globalRate = serviceLimiter.check()

    risk = assessLoginRisk(accountRef, source, device)

    if globalRate.exceeded:
        return SERVICE_THROTTLED
    if accountRate.exceeded or sourceRate.exceeded or deviceRate.exceeded:
        return APPLY_PROGRESSIVE_DELAY
    if risk.requiresAdditionalProof:
        return REQUIRE_ADAPTIVE_CHALLENGE
    return CONTINUE_TO_CREDENTIAL_VERIFICATION
`````````

Đây là pseudocode khái niệm. Bộ giới hạn cần hoạt động nhất quán giữa nhiều instance, chịu được request đồng thời và không làm authentication service phụ thuộc vào một cache dễ bị mất trạng thái.

## 6. Account lockout và nguy cơ denial of service

Khóa account sau nhiều lần login failure có thể giảm tốc độ brute force, nhưng cũng tạo cơ hội cho attacker cố ý khóa tài khoản người khác.

Nếu chỉ cần biết username để làm tăng bộ đếm thất bại, attacker có thể gửi nhiều password sai nhằm khiến nạn nhân không đăng nhập được. Đây là một dạng denial of service.

### Thiết kế cân bằng

- Ưu tiên throttling và progressive delay trước permanent lockout;
- Dùng nhiều tín hiệu thay vì chỉ một bộ đếm account;
- Giới hạn theo account nhưng không để nguồn bất kỳ khóa account vô thời hạn;
- Có quy trình unlock/recovery an toàn và không dựa vào email yếu;
- Giữ thông báo công khai nhất quán để tránh account enumeration;
- Theo dõi lockout bất thường và nguồn gây ra;
- Với account đặc quyền, có thể dùng policy nghiêm hơn nhưng phải có break-glass đã kiểm soát.

Một attacker có thể phân tán request, đổi IP hoặc thử một lần trên nhiều account. Lockout chỉ theo account sẽ bỏ sót spraying; lockout chỉ theo IP có thể ảnh hưởng người dùng hợp lệ sau NAT. Kết hợp rate limiting, MFA, risk detection, password storage và monitoring.

## 7. CAPTCHA và adaptive challenge

CAPTCHA có thể tăng chi phí tự động hóa nhưng không phải biện pháp chống brute force độc lập.

Giới hạn:

- Có thể bị giải bởi dịch vụ bên ngoài hoặc mô hình tự động;
- Làm giảm khả năng tiếp cận với một số người dùng;
- Tạo friction cho người dùng hợp lệ;
- Không bảo vệ password hash bị đánh cắp;
- Không ngăn attacker có credential hợp lệ hoặc session bị chiếm.

Có thể yêu cầu challenge khi có dấu hiệu automation hoặc risk tăng, thay vì hiển thị cho mọi người dùng. Challenge cần expiry, gắn với login transaction và được xác minh server-side. Không chấp nhận một cờ do browser gửi rằng CAPTCHA đã hoàn tất.

Đối với người dùng không thể hoàn thành CAPTCHA, cần phương án tiếp cận thay thế mà vẫn đáp ứng policy rủi ro.

## 8. MFA và passkey giảm tác động của password guessing

MFA thêm một lớp bảo vệ nếu password bị đoán hoặc lộ. Tuy nhiên, hiệu quả phụ thuộc vào phương thức và cách recovery.

| Phương thức | Vai trò khi password bị đoán | Giới hạn |
| --- | --- | --- |
| **Passkey/WebAuthn** | Yêu cầu proof mật mã từ authenticator gắn với RP/origin | Cần quản lý credential lifecycle và recovery |
| **Security key** | Bảo vệ bằng possession và user verification theo policy | Có thể bị mất; cần key dự phòng |
| **TOTP** | Thêm yếu tố khác ngoài password | Mã có thể bị phishing/relay |
| **Push approval** | Thêm xác nhận trên thiết bị | Có nguy cơ MFA fatigue nếu prompt lặp lại |
| **SMS OTP** | Tăng rào cản so với password đơn lẻ | SIM swap, port-out, phishing và chuyển tiếp |

Với account nhạy cảm, ưu tiên phương thức phishing-resistant. MFA không làm password hash an toàn hơn nếu database bị lộ; nó chủ yếu giảm khả năng dùng password bị đoán để đăng nhập.

### Passkey và passwordless

Nếu hệ thống chuyển sang passkey/passwordless cho một luồng đăng nhập, brute force password có thể không còn là đường tấn công chính của luồng đó. Tuy vậy, cần bảo vệ credential registration, account recovery, password fallback, session/token, enrollment thiết bị và federation.

Một fallback password yếu có thể trở thành đường vòng bỏ qua passkey.

## 9. Lưu trữ password để chống offline cracking

Không lưu password dạng plaintext hoặc mã hóa có thể giải ngược chỉ để tiện xác minh. Server cần lưu **password hash** được tạo bằng password hashing function chuyên dụng.

### Thuộc tính cần có

- Hàm hash chậm, có thể cấu hình chi phí;
- Salt ngẫu nhiên, riêng cho từng password;
- Có thể tăng chi phí theo thời gian khi phần cứng mạnh hơn;
- Định dạng lưu chứa algorithm và parameters để nâng cấp;
- Có cơ chế kiểm tra và rehash khi người dùng đăng nhập thành công.

### Lựa chọn thuật toán

| Thuật toán | Đặc điểm | Hướng sử dụng |
| --- | --- | --- |
| **Argon2id** | Memory-hard, kết hợp bảo vệ trước một số kiểu side-channel và GPU cracking | Lựa chọn ưu tiên khi nền tảng hỗ trợ |
| **scrypt** | Memory-hard, chi phí bộ nhớ có thể cấu hình | Lựa chọn phù hợp khi Argon2id không khả dụng |
| **bcrypt** | Password hash chậm, cost factor cấu hình được | Phù hợp hệ thống legacy hoặc nền tảng đã chuẩn hóa |
| **PBKDF2** | Lặp hàm dẫn xuất khóa với số vòng cấu hình | Có thể cần cho tương thích hoặc yêu cầu chuẩn hóa cụ thể |
| **SHA-256/SHA-1 đơn lẻ** | Hàm hash nhanh, không thiết kế để lưu password | Không dùng đơn lẻ làm password storage |

Thông số chi phí phải được benchmark trên hạ tầng thật, cân bằng khả năng chống crack với độ trễ và nguy cơ CPU/memory exhaustion. Không sao chép tham số cũ mà không đánh giá lại.

### Salt

Salt là giá trị ngẫu nhiên riêng cho mỗi password hash. Salt không cần bí mật. Nó ngăn attacker dùng một bảng tính trước cho tất cả account và khiến hai người dùng có cùng password vẫn có hash khác nhau.

### Pepper

Pepper là secret bổ sung được giữ tách khỏi password database, ví dụ trong secret manager hoặc HSM. Nếu dùng pepper:

- Không lưu pepper trong cùng database với hash;
- Có quy trình rotation và versioning;
- Giới hạn service nào được truy cập;
- Có kế hoạch phục hồi nếu secret bị mất;
- Đánh giá ảnh hưởng tới login khi pepper service không khả dụng.

Pepper là lớp phòng thủ bổ sung; nó không thay thế salt, password hashing chuyên dụng hoặc bảo vệ database.

### Ví dụ định dạng lưu

`````````text
$argon2id$v=19$m=...,t=...,p=...$<salt>$<derived-hash>
`````````

Đây là định dạng minh họa, không phải tham số khuyến nghị. Thư viện chuẩn thường quản lý encoding, salt và parameters trong chuỗi hash; không tự ghép hoặc tự triển khai thuật toán mật mã.

## 10. Password policy giảm khả năng bị đoán

Policy nên giúp người dùng tạo password mạnh và duy nhất, thay vì chỉ ép nhiều loại ký tự theo quy tắc dễ đoán.

### Thực hành tốt

- Cho phép password/passphrase đủ dài;
- Chấp nhận khoảng trắng và cụm từ dễ nhớ;
- Chặn password phổ biến, mặc định hoặc đã biết bị lộ;
- Không áp đặt quy tắc thay ký tự máy móc nếu không có lý do;
- Không ép đổi định kỳ một cách tùy tiện khi chưa có dấu hiệu compromise;
- Cho phép paste và dùng password manager;
- Không cắt ngắn password âm thầm;
- Đặt giới hạn độ dài tối đa đủ rộng để tránh password quá dài gây DoS;
- Chuẩn hóa Unicode theo policy nhất quán trước khi verify;
- Thông báo người dùng khi password mới xuất hiện trong danh sách bị lộ.

### Breached-password screening

Khi người dùng tạo hoặc đổi password, dịch vụ có thể kiểm tra password candidate với danh sách password phổ biến/đã lộ. Việc kiểm tra cần bảo vệ password khỏi bị gửi tới bên thứ ba dưới dạng plaintext. Có thể dùng cơ chế tra cứu bảo vệ quyền riêng tư hoặc bộ danh sách nội bộ được quản lý.

Không ghi password candidate vào log hoặc analytics trong quá trình kiểm tra.

## 11. Bảo vệ login endpoint và thông tin phản hồi

Brute force thường khai thác endpoint đăng nhập và khác biệt trong phản hồi.

### Kiểm soát endpoint

- Rate limit và progressive delay ở server/gateway;
- Chống request flood và giới hạn kích thước payload;
- TLS bắt buộc cho credential;
- CSRF protection phù hợp với kiến trúc browser session;
- Kiểm tra content type và parse input an toàn;
- Không để lỗi upstream làm bypass xác minh password;
- Không tạo session trước khi hoàn tất mọi bước bắt buộc;
- Regenerate session ID sau login;
- Không ghi credential hoặc token vào URL.

### Tránh account enumeration

Thông báo login failure nên nhất quán giữa account không tồn tại, password sai và trạng thái account bị hạn chế, trong phạm vi phù hợp. Tránh trả về thông tin quá chi tiết cho người chưa xác thực.

Ngoài message, cần để ý khác biệt thời gian xử lý, HTTP status, response size, redirect path và việc challenge chỉ xuất hiện với account tồn tại. Không nhất thiết làm mọi nhánh có thời gian hoàn toàn bằng nhau, nhưng cần tránh side channel dễ khai thác và đo lường được.

## 12. Password reset và recovery cũng phải chống brute force

Attacker có thể bỏ qua login endpoint và tấn công OTP xác minh email/phone, recovery code, password reset token, helpdesk verification hoặc endpoint kiểm tra account existence.

### Reset token

- Sinh bằng CSPRNG, đủ entropy;
- Lưu verifier/hash phù hợp phía server;
- Gắn với account, purpose và transaction;
- Có expiry ngắn theo policy;
- Chỉ dùng một lần và consume atomically;
- Không đưa secret vào referrer hoặc analytics;
- Sau reset, thu hồi session/token theo policy;
- Thông báo tới kênh đã đăng ký trước đó.

### OTP/recovery code

- Không cho phép thử không giới hạn;
- Rate limit theo account và transaction;
- Có thời hạn và single-use;
- Không ghi mã vào log;
- Có kiểm soát gửi lại để tránh spam;
- Không để recovery trở thành đường vòng yếu hơn MFA/passkey.

## 13. Phát hiện brute force và tấn công phân tán

Detection cần quan sát nhiều chiều, không chỉ đếm request từ một IP.

### Tín hiệu quan trọng

- Nhiều lần login failure trên cùng subject;
- Một source/network thử nhiều subject;
- Nhiều nguồn thử một subject trong cửa sổ ngắn;
- Tỷ lệ failure tăng đột biến so với baseline;
- Nhiều request có cùng client fingerprint hoặc user-agent pattern;
- Thất bại tập trung vào account đặc quyền;
- Một login success xảy ra sau chuỗi failure bất thường;
- Login success từ device/network mới sau pattern đoán;
- Password reset hoặc MFA factor change ngay sau login success.

### Phân biệt pattern

| Pattern | Gợi ý detection |
| --- | --- |
| Brute force nhắm một account | Failure count cao trên subject trong cửa sổ thời gian |
| Spraying | Một source hoặc campaign nhắm nhiều subject với số lần thử ít trên mỗi subject |
| Credential stuffing | Nhiều subject và source, pattern credential reuse; có success xen giữa |
| Distributed brute force | Một subject bị thử từ nhiều network/device khác nhau |
| Offline cracking | Không thể phát hiện qua login audit; cần giám sát truy cập database, backup và secret store |

### SQL minh họa: một nguồn nhắm nhiều account

`````````sql
SELECT
    source_network,
    COUNT(*) AS failed_attempts,
    COUNT(DISTINCT subject_ref) AS targeted_accounts
FROM auth_audit
WHERE event_name = 'auth.login.failed'
  AND occurred_at >= CURRENT_TIMESTAMP - INTERVAL '10 minutes'
GROUP BY source_network
HAVING COUNT(*) >= 50
   AND COUNT(DISTINCT subject_ref) >= 20;
`````````

### SQL minh họa: một account bị thử từ nhiều nguồn

`````````sql
SELECT
    subject_ref,
    COUNT(*) AS failed_attempts,
    COUNT(DISTINCT source_network) AS source_count
FROM auth_audit
WHERE event_name = 'auth.login.failed'
  AND occurred_at >= CURRENT_TIMESTAMP - INTERVAL '15 minutes'
GROUP BY subject_ref
HAVING COUNT(*) >= 20
   AND COUNT(DISTINCT source_network) >= 8;
`````````

SQL chỉ minh họa cách nhóm dữ liệu. Cú pháp interval, window function và tên cột phụ thuộc hệ quản trị. Các ngưỡng 50/20 và 20/8 không phải chuẩn chung; cần hiệu chỉnh theo traffic, NAT, VPN, mạng di động và hành vi bình thường.

## 14. Ứng phó khi phát hiện brute force

Một alert không đồng nghĩa account đã bị chiếm. Cần xác minh phạm vi và áp dụng biện pháp tương xứng.

1. Xác định account/tenant/client bị nhắm tới và time window.
2. Phân tích failure pattern theo subject, source, device và user agent.
3. Kiểm tra có login success nào xen giữa hay không.
4. Liên kết login success với session creation và hoạt động sau đăng nhập.
5. Nếu có dấu hiệu compromise, revoke session và refresh token liên quan.
6. Yêu cầu đổi password qua kênh an toàn nếu password có thể đã bị lộ.
7. Kiểm tra và thu hồi credential/factor mới được thêm bất thường.
8. Tăng bảo vệ cho account/tenant bị nhắm mục tiêu.
9. Nếu nghi database hash bị lộ, xử lý như sự cố credential store: cô lập nguồn, điều tra truy cập, đánh giá hash parameters và chuẩn bị reset/rehash.
10. Theo dõi tái diễn và ghi lại quyết định/ảnh hưởng.

Tránh khóa hàng loạt account chỉ vì cùng một IP nếu có thể là NAT. Không bắt mọi người đổi password định kỳ nếu chưa xác định phạm vi. Không gửi password tạm hoặc recovery code qua kênh không bảo vệ. Không xóa log trước khi bảo toàn evidence. Không chỉ chặn IP nếu campaign đã phân tán qua nhiều nguồn.

## 15. Khi password database bị lộ

Đây là tình huống offline cracking. Rate limit, CAPTCHA và account lockout không bảo vệ hash đã bị sao chép.

### Các bước ưu tiên

1. Ngăn truy cập tiếp vào database, backup hoặc snapshot bị ảnh hưởng.
2. Xác định loại dữ liệu bị lộ: plaintext, hash, salt, pepper reference, reset token hoặc session.
3. Xác định thuật toán, parameters và phiên bản password hash.
4. Kiểm tra pepper có bị lộ cùng database hay không.
5. Xác định account đặc quyền và account có password yếu/đã dùng lại.
6. Thu hồi session/refresh token nếu nguy cơ takeover.
7. Yêu cầu reset password theo risk và phạm vi bị ảnh hưởng.
8. Khi người dùng đăng nhập bằng password mới, lưu hash theo parameters hiện hành.
9. Nếu hash cũ yếu, rehash sau khi xác minh password thành công hoặc bắt buộc reset theo risk.
10. Thông báo, giám sát credential reuse và rà soát nguyên nhân truy cập database.

Nếu attacker đã có hash cũ, thay salt trong database không làm mất bản sao attacker đã lấy. Cần thay password hoặc yêu cầu người dùng thiết lập credential mới; đồng thời nâng cấp thuật toán/parameters và bảo vệ nguồn dữ liệu.

## 16. Passwordless và giảm bề mặt brute force

Passkey/WebAuthn thay việc gửi password dùng chung bí mật bằng proof mật mã gắn với RP/origin. Điều này loại bỏ password guessing khỏi luồng passkey thuần túy và giảm nguy cơ phishing credential.

Tuy nhiên, hệ thống vẫn phải bảo vệ password fallback nếu còn, recovery và helpdesk, đăng ký passkey mới, thay đổi recovery channel, session/token, federation và API key/service credential khác.

Một ứng dụng có passkey nhưng cho phép reset bằng email yếu vẫn có thể bị takeover qua recovery. Cần kiểm tra toàn bộ đường vào account, không chỉ màn hình login chính.

## 17. Threat model: các điểm dễ bị bỏ sót

| Rủi ro | Cách xảy ra | Kiểm soát |
| --- | --- | --- |
| **Distributed guessing** | Chia request qua nhiều IP/device | Rate limit đa chiều, correlation và risk scoring |
| **Account lockout DoS** | Attacker cố ý làm tăng failure counter của nạn nhân | Progressive delay, unlock an toàn, tránh hard lockout dễ kích hoạt |
| **Username enumeration** | Response tiết lộ account tồn tại | Message/status/timing nhất quán |
| **Offline cracking** | Password hash bị đánh cắp | Argon2id/scrypt/bcrypt/PBKDF2 phù hợp, salt, pepper, DB protection |
| **Password reuse** | Password đoán được từ dịch vụ khác | Password manager, breached-password screening, MFA |
| **MFA bypass** | Password đúng nhưng factor yếu hoặc recovery yếu | Phishing-resistant MFA và recovery policy |
| **CAPTCHA bypass** | Automation giải challenge qua dịch vụ khác | Chỉ là lớp phụ, kết hợp throttling và risk |
| **Reset endpoint brute force** | Đoán OTP hoặc reset token | Entropy, expiry, rate limit, single-use |
| **Timing side channel** | Khác biệt response làm lộ account hoặc trạng thái | Chuẩn hóa response và đo timing |
| **Credential store exfiltration** | DB/backup bị đọc trái phép | Least privilege, encryption, monitoring, secret separation |
| **Hash parameter downgrade** | Hệ thống ghi password mới với cost yếu | Policy trung tâm, kiểm tra metadata hash và migration |
| **Recovery abuse** | Attacker dùng helpdesk/email để thay factor | Re-verification, dual control, notification |

## 18. Tình huống thiết kế: cổng nhân viên bị password guessing

Một cổng nhân viên dùng password login và MFA TOTP. Trong 15 phút, hệ thống nhận hàng nghìn lần login failure. Một số account có login success từ network mới. Đội vận hành chỉ cấu hình khóa account sau năm lần sai.

### Thiết kế ban đầu có vấn đề

1. Attacker có thể khóa account bằng cách gửi năm password sai cho từng nhân viên.
2. Rate limit chỉ theo IP nên phân tán request sẽ né được giới hạn.
3. Login failure trả lỗi khác nhau cho account không tồn tại và password sai.
4. Một số password được lưu bằng SHA-256 đơn lẻ.
5. Login success sau chuỗi failure không kích hoạt risk review.
6. Reset password chỉ cần OTP SMS tới số điện thoại hiện tại.

### Thiết kế lại

1. Áp dụng rate limit đa chiều theo account, source, device, tenant và global service.
2. Dùng progressive delay/adaptive challenge; không để nguồn ngoài khóa account vô thời hạn.
3. Chuẩn hóa phản hồi login để giảm account enumeration.
4. Chuyển password storage sang Argon2id hoặc password hashing function phù hợp, salt riêng từng password và pepper nếu có khả năng quản lý an toàn.
5. Rehash sau login thành công hoặc yêu cầu reset với hash yếu theo risk.
6. Bật breached-password screening khi tạo/đổi password và khuyến khích password manager.
7. Yêu cầu MFA; ưu tiên passkey/security key cho account đặc quyền và hành động nhạy cảm.
8. Detection liên kết failure, success, device, recovery và session events.
9. Khi login success đáng ngờ, đánh giá risk, step-up hoặc chặn session; revoke nếu có bằng chứng compromise.
10. Bảo vệ reset/recovery bằng token entropy cao, expiry, single-use và re-verification.

### Kết quả mong đợi

- Một nguồn không thể dễ dàng khóa hàng loạt account;
- Tấn công phân tán vẫn được phát hiện qua nhiều chiều;
- Password hash bị lộ khó crack hơn đáng kể;
- Login success bất thường được điều tra trước khi cấp quyền nhạy cảm;
- Recovery không trở thành đường vòng bỏ qua MFA;
- Audit đủ để dựng lại chuỗi tấn công.

## 19. Bộ kiểm thử chấp nhận

| Trường hợp | Cách thử | Kết quả kỳ vọng |
| --- | --- | --- |
| **Một account bị thử liên tục** | Gửi nhiều password sai cho cùng account | Throttling/progressive delay được áp dụng |
| **Một IP nhắm nhiều account** | Mô phỏng spraying từ một source | Detection theo source và subject |
| **Một account từ nhiều source** | Mô phỏng distributed guessing | Detection theo subject và network diversity |
| **Account lockout DoS** | Gửi failure vào account nạn nhân | Không bị khóa vô thời hạn chỉ bởi nguồn ngoài |
| **Account enumeration** | So sánh response cho username tồn tại/không tồn tại | Không lộ trạng thái qua message/status dễ thấy |
| **Rate limit bypass** | Chia request qua nhiều instance/source | Giới hạn đa chiều vẫn có hiệu lực |
| **Global service flood** | Tăng request đồng thời trên nhiều account | Capacity được bảo vệ; dịch vụ vẫn phục vụ request hợp lệ |
| **MFA absent** | Password đúng nhưng account yêu cầu MFA | Không tạo session trước khi MFA đạt |
| **MFA fatigue** | Gửi nhiều challenge lặp lại | Rate limit, alert và user context |
| **Passkey path** | Đăng nhập bằng passkey hợp lệ | Không yêu cầu password nếu policy passwordless |
| **Weak fallback** | Thử recovery bằng email/SMS đơn lẻ cho account high-risk | Không bypass assurance policy |
| **Reset token guessing** | Thử token/OTP sai nhiều lần | Rate limit, expiry và block theo transaction |
| **Reset token replay** | Dùng lại token đã tiêu thụ | Từ chối |
| **Password hash algorithm** | Kiểm tra hash mới được lưu | Dùng thuật toán password hashing được phê duyệt và parameters đúng |
| **Unique salt** | Tạo cùng password cho hai account | Hash khác nhau do salt riêng |
| **Pepper isolation** | Kiểm tra quyền đọc DB và secret store | DB reader không tự lấy được pepper |
| **Hash migration** | Login thành công với hash legacy | Rehash theo policy hoặc yêu cầu reset |
| **Password length** | Dùng passphrase dài hợp lệ | Không bị cắt ngắn âm thầm |
| **Unicode normalization** | Đăng ký và xác minh password Unicode | Quy tắc xử lý nhất quán |
| **Password logging** | Kiểm tra application/APM/audit logs | Không có password hoặc candidate thô |
| **Timing enumeration** | So sánh các nhánh account tồn tại/không tồn tại | Không có timing side channel rõ rệt |
| **Success after failures** | Tạo login success sau pattern bất thường | Risk alert và session review |
| **Session fixation** | Giữ session ID trước login | Session ID được regenerate |
| **Revoked session** | Dùng session sau khi incident response revoke | Bị từ chối theo SLA |
| **Offline breach drill** | Mô phỏng lộ password hash trong môi trường kiểm thử | Kích hoạt quy trình database incident và credential reset |

Kiểm thử cần bao gồm login endpoint, MFA, recovery, password storage, session service và audit pipeline. Chỉ chứng minh rate limit hoạt động ở một IP không đủ để kết luận chống brute force hiệu quả.

## 20. Audit và chỉ số vận hành

Login audit cần ghi sự kiện có cấu trúc để phát hiện brute force và điều tra mà không làm lộ password.

| Event | Trường gợi ý |
| --- | --- |
| auth.login.started | Interaction ID, subject reference, client, source context |
| auth.login.failed | Reason code, subject reference, source/device reference |
| auth.login.succeeded | Subject, method, device, session reference |
| auth.rate_limited | Dimension, policy version, reason code |
| auth.challenge.required | Challenge type, action/context reference |
| auth.mfa.failed/succeeded | Factor reference, outcome, transaction reference |
| auth.password.changed/reset | Subject, actor, recovery transaction, result |
| auth.account.throttled/locked | Policy, duration, trigger reference |
| auth.session.revoked | Session reference, reason, actor |
| auth.password_hash.migrated | Algorithm/version/parameter profile, không có hash hoặc password |

Không ghi password, password hash, OTP, TOTP seed, recovery code, authorization header, bearer token, session cookie hoặc private key. IP/device context cần được thu thập theo mục đích, phân quyền và retention.

### Chỉ số cần theo dõi

- Login failure rate theo account, tenant, client, source và method;
- Số subject bị nhắm tới trên mỗi source/network;
- Số source/network nhắm vào mỗi subject;
- Rate-limit và progressive-delay activation;
- Lockout/throttle rate và thời gian người dùng hợp lệ bị ảnh hưởng;
- MFA challenge failure và approval rate;
- Login success sau chuỗi failure;
- New-device login sau pattern đoán;
- Password reset/recovery sau login bất thường;
- Password hash algorithm/parameter coverage;
- Session revocation propagation latency;
- Audit event delivery lag và dropped event count.

Ngưỡng cảnh báo phải được hiệu chỉnh theo baseline. NAT, VPN, nhà mạng di động, proxy và giờ cao điểm có thể tạo false positive. Không dùng một metric đơn lẻ để tự động khóa account hàng loạt.

## 21. Checklist triển khai chống brute force

- **Threat model:** Đã phân biệt online guessing, offline cracking, spraying và credential stuffing?
- **Password policy:** Cho phép password/passphrase dài, duy nhất và chặn password phổ biến/đã lộ?
- **Password storage:** Dùng password hashing chuyên dụng, salt riêng và parameters được benchmark?
- **Pepper:** Nếu có, secret được tách khỏi database và có rotation/recovery?
- **Rate limiting:** Có giới hạn theo account, source, device, tenant và global?
- **Lockout:** Tránh để attacker dễ khóa account nạn nhân; có progressive delay và unlock an toàn?
- **Enumeration:** Message, status, redirect và timing không làm lộ account?
- **MFA/passkey:** Account nhạy cảm có phương thức phishing-resistant phù hợp?
- **CAPTCHA:** Chỉ dùng như lớp bổ sung theo risk, có accessibility fallback?
- **Recovery/reset:** Token entropy cao, expiry, single-use, rate limit và re-verification?
- **Session:** Không tạo session trước khi hoàn tất credential/MFA; regenerate ID sau login?
- **Detection:** Có pattern cho brute force, spraying, distributed guessing và success sau failure?
- **Incident response:** Có quy trình khi login abuse hoặc password database bị lộ?
- **Audit:** Không ghi password/hash/OTP/token/cookie; có reason code và correlation?
- **Testing:** Đã thử distributed attempts, lockout DoS, hash migration, replay và recovery bypass?

### Câu hỏi tự kiểm tra

1. Brute force khác credential stuffing và password spraying như thế nào?
2. Vì sao rate limit online không giúp khi attacker đã lấy password hash?
3. Salt giải quyết vấn đề gì và vì sao salt không cần bí mật?
4. Pepper khác salt ở điểm nào và cần bảo vệ ra sao?
5. Vì sao SHA-256 đơn lẻ không phù hợp để lưu password?
6. Account lockout có thể bị dùng để gây denial of service như thế nào?
7. Vì sao cần rate limit theo account, source, device và global?
8. MFA/passkey giảm tác động của password guessing ra sao?
9. Những event nào giúp phát hiện một login success sau nhiều failure?
10. Khi password database bị lộ, vì sao chỉ đổi salt không đủ?

## Kết luận

**Brute force là nỗ lực đoán credential bằng nhiều lần thử, và cần được phòng thủ ở cả lớp đăng nhập trực tuyến lẫn kho password hash.** Online guessing cần rate limiting đa chiều, progressive delay, account protection, MFA/passkey và detection có ngữ cảnh; offline cracking cần password hashing chuyên dụng như Argon2id hoặc lựa chọn phù hợp, salt riêng, pepper được bảo vệ và quy trình xử lý khi database bị lộ. Password spraying, credential stuffing và brute force có pattern khác nhau nên cần detection riêng, nhưng đều có thể dẫn tới account takeover. Recovery, reset password và session cũng phải được bảo vệ tương xứng với login chính. Hiệu quả phòng thủ chỉ được xác nhận khi hệ thống vừa hạn chế được thử đoán, vừa tránh khóa nhầm người dùng, phát hiện được tấn công phân tán và thu hồi được quyền truy cập khi credential đã bị compromise.
