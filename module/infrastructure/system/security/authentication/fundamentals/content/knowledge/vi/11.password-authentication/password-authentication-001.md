# Luồng password authentication

## 1. Password authentication là gì?

**Password authentication** là quy trình xác minh người đăng nhập có biết đúng bí mật đã được liên kết với tài khoản hay không. Người dùng cung cấp một định danh (ví dụ username hoặc email) cùng mật khẩu; hệ thống tra cứu bản ghi credential tương ứng và kiểm tra mật khẩu bằng verifier được lưu trữ an toàn. Nếu kiểm tra thành công và các chính sách khác đều được đáp ứng, hệ thống mới thiết lập trạng thái xác thực hoặc yêu cầu bước tiếp theo như MFA.

Mật khẩu là yếu tố thuộc nhóm **something you know**. Nó không chứng minh tên pháp lý, quyền sở hữu một hộp thư hay quyền truy cập mọi tài nguyên. Nó chỉ hỗ trợ kết luận rằng người đang tương tác đã cung cấp đúng bí mật gắn với tài khoản, trong phạm vi những kiểm soát của hệ thống.

Trong module **SECURITY_AUTHENTICATION_FUNDAMENTALS**, luồng password authentication là nền tảng để hiểu credential, MFA, passkey, chứng chỉ, token, phiên, liên kết danh tính và khôi phục tài khoản. Một flow tốt cần bảo vệ bí mật khi truyền và lưu, hạn chế đoán mật khẩu và credential stuffing, tránh tiết lộ tài khoản tồn tại, chống bypass MFA, và chỉ cấp phiên sau khi tất cả điều kiện bắt buộc đã hoàn thành.

Bài học này tập trung vào vòng đời đầy đủ: đăng ký/đặt mật khẩu, đăng nhập, kiểm tra credential, xử lý challenge MFA, cấp session, đổi mật khẩu, khôi phục và thu hồi.

## 2. Các thành phần của một flow

Một kiến trúc password authentication thường có những thành phần sau:

| Thành phần | Trách nhiệm | Điều cần bảo vệ |
| --- | --- | --- |
| **Client** (browser/mobile/CLI) | Thu thập định danh và mật khẩu, gửi yêu cầu qua kênh bảo mật, hiển thị kết quả | Không lưu hoặc log mật khẩu; không tự quyết định đăng nhập thành công |
| **Authentication endpoint** | Nhận request, kiểm tra cấu trúc, điều phối trạng thái đăng nhập | Rate limit, chống abuse, không tiết lộ account enumeration |
| **Account/identity store** | Ánh xạ định danh đăng nhập tới tài khoản | Tránh nhầm principal, tenant và tài khoản trùng |
| **Credential verifier store** | Lưu password hash và metadata thuật toán | Hash chậm, salt riêng, quyền truy cập tối thiểu, backup an toàn |
| **Password verification service** | Kiểm tra mật khẩu ứng viên với verifier | Không lưu plaintext, không dùng hash nhanh thông thường, xử lý lỗi an toàn |
| **Risk/abuse controls** | Đánh giá tốc độ thử, nguồn, dấu hiệu credential stuffing | Không khóa tài khoản vô thời hạn dễ gây DoS |
| **MFA verifier** | Xác minh yếu tố bổ sung nếu policy yêu cầu | Challenge gắn flow, TTL, chống replay và giới hạn thử |
| **Session/token service** | Phát hành và quản lý phiên sau xác thực | Session rotation, TTL, revoke, cookie/token an toàn |
| **Audit/monitoring** | Ghi sự kiện bảo mật và chỉ số vận hành | Không ghi password, OTP, session ID hay raw token |

Client không phải nơi lưu sự thật về trạng thái xác thực. Một giá trị như **loginSuccess=true** trong local storage, một redirect về trang chủ hoặc một thông báo từ JavaScript không chứng minh server đã xác thực thành công.

## 3. Luồng tổng thể: từ nhập mật khẩu đến phiên

Một flow có thể được mô hình hóa qua các bước:

1. Người dùng gửi định danh và mật khẩu qua HTTPS.
2. Server kiểm tra request, giới hạn tần suất và xác định phạm vi tenant/realm.
3. Server tra cứu tài khoản và lấy password verifier tương ứng; nếu không tìm thấy, xử lý theo nhánh phản hồi an toàn.
4. Password verification service kiểm tra mật khẩu ứng viên bằng thuật toán và tham số đã lưu.
5. Nếu sai, server ghi nhận sự kiện, áp dụng rate limit và trả phản hồi không tiết lộ quá nhiều chi tiết.
6. Nếu đúng, server kiểm tra các điều kiện còn lại: tài khoản có bị vô hiệu hóa không, có yêu cầu MFA không, có step-up hoặc risk policy nào cần thực hiện không.
7. Nếu còn challenge, server phát hành trạng thái flow có phạm vi hạn chế và chưa cấp phiên đầy đủ.
8. Nếu mọi điều kiện xác thực đã hoàn tất, server tạo authentication context và cấp session/token thích hợp.
9. Mỗi request tiếp theo tiếp tục kiểm tra session/token, freshness, trạng thái thu hồi và authorization trên tài nguyên.

~~~mermaid
flowchart TD
    A[Người dùng gửi username và password] --> B[HTTPS và kiểm tra request]
    B --> C[Rate limit / abuse checks]
    C --> D[Tra cứu tài khoản và verifier]
    D --> E[Kiểm tra password hash]
    E --> F{Mật khẩu hợp lệ?}
    F -- Không --> G[Audit an toàn và phản hồi trung tính]
    F -- Có --> H[Kiểm tra trạng thái account và policy]
    H --> I{Cần MFA hoặc step-up?}
    I -- Có --> J[Challenge gắn flow, TTL và giới hạn thử]
    J --> K{Yếu tố bổ sung hợp lệ?}
    K -- Không --> G
    K -- Có --> L[Tạo authentication context]
    I -- Không --> L
    L --> M[Rotate và cấp session/token]
    M --> N[Request tiếp theo: xác minh session và authorization]
~~~

Điểm kiểm soát quan trọng là **password đúng chưa chắc đã đồng nghĩa đăng nhập hoàn tất**. Nếu tài khoản yêu cầu MFA, bước xác thực bằng mật khẩu chỉ là một phần của flow. Server phải duy trì trạng thái “đang chờ challenge” và chỉ cấp quyền tương ứng sau khi challenge được xác minh.

## 4. Đăng ký và lưu trữ mật khẩu

### 4.1. Không lưu mật khẩu dạng plaintext

Server không nên lưu mật khẩu nguyên văn hoặc lưu dạng mã hóa có thể giải mã lại để dùng khi đăng nhập. Thay vào đó, hệ thống lưu **password hash** được tạo bởi thuật toán chuyên dụng cho mật khẩu, có salt riêng và chi phí tính toán phù hợp.

Khi người dùng đăng nhập, server nhận mật khẩu ứng viên, chạy cùng thuật toán và tham số để kiểm tra với verifier đã lưu. Password hash không phải mật khẩu; nó là kết quả một phép biến đổi có chủ đích nhằm làm cho việc thử hàng loạt sau khi database bị lộ trở nên tốn kém.

Không dùng các hàm hash nhanh phổ thông như MD5, SHA-1 hoặc SHA-256 đơn lẻ để lưu mật khẩu. Chúng được thiết kế để tính nhanh và phù hợp cho nhiều mục đích khác, nhưng khiến kẻ tấn công có thể thử số lượng lớn mật khẩu khi lấy được hash.

### 4.2. Thuật toán và tham số

Các lựa chọn phổ biến gồm:

- **Argon2id:** lựa chọn thường được ưu tiên cho hệ thống mới nếu thư viện và môi trường hỗ trợ; có chi phí bộ nhớ và CPU có thể cấu hình.
- **scrypt:** hàm dẫn xuất khóa có chi phí bộ nhớ, phù hợp trong một số môi trường.
- **bcrypt:** thuật toán lâu đời, vẫn có thể dùng khi được cấu hình đúng và giới hạn độ dài đầu vào được hiểu rõ.
- **PBKDF2:** có thể phù hợp trong môi trường cần tương thích hoặc theo yêu cầu cụ thể; phải chọn hash và số vòng lặp phù hợp.

Tham số cần được **benchmark trên hạ tầng thật**: đủ tốn kém để làm chậm việc đoán offline nhưng không gây cạn tài nguyên khi có nhiều đăng nhập đồng thời. Không nên sao chép một con số cấu hình từ ví dụ mà không đo tải, giới hạn concurrency và kiểm tra khả năng chống DoS.

Một verifier thường chứa thuật toán, phiên bản và tham số cùng salt và hash. Nhờ đó hệ thống có thể nhận biết hash cũ và nâng cấp khi người dùng đăng nhập thành công.

### 4.3. Salt và pepper

- **Salt:** giá trị ngẫu nhiên, riêng cho mỗi mật khẩu/bản ghi; được lưu cùng verifier. Salt làm cho hai người có cùng mật khẩu không tạo cùng hash và ngăn việc dùng lại bảng rainbow table tiền tính.
- **Pepper:** bí mật bổ sung do hệ thống giữ riêng, có thể nằm trong KMS/HSM hoặc secret store. Nếu dùng, pepper không được lưu chung với password database; cần kế hoạch rotate, versioning và phục hồi.

Salt **không phải bí mật** và không thay thế thuật toán hash chuyên dụng. Pepper là lớp phòng thủ bổ sung, không phải lý do để chọn hash nhanh hoặc bỏ qua các kiểm soát khác. Việc thay pepper có thể cần chiến lược rehash/reset tùy cách thiết kế.

### 4.4. Ví dụ cấu trúc verifier

Ví dụ dưới đây là dữ liệu khái niệm, không phải chuỗi hash có thể sử dụng:

~~~json
{
  "algorithm": "argon2id",
  "version": 19,
  "memoryCost": "calibrated-for-deployment",
  "timeCost": "calibrated-for-deployment",
  "parallelism": "calibrated-for-deployment",
  "salt": "unique-random-salt",
  "hash": "derived-password-verifier"
}
~~~

Trong thực tế, nên dùng thư viện password hashing đáng tin cậy để tạo và kiểm tra định dạng verifier. Không tự viết thuật toán, không tự ghép salt/hash bằng chuỗi thủ công, và không dùng phép so sánh dễ rò rỉ thông tin thời gian nếu thư viện đã cung cấp hàm verify an toàn.

### 4.5. Nâng cấp verifier khi đăng nhập

Khi người dùng nhập đúng mật khẩu với verifier cũ, server có thể kiểm tra xem thuật toán/tham số đã thấp hơn policy hiện tại hay chưa. Nếu cần, tạo verifier mới từ mật khẩu vừa xác minh rồi cập nhật bản ghi một cách an toàn.

Quá trình này cần xử lý đồng thời: hai request login cùng lúc, người dùng đổi mật khẩu giữa lúc rehash, cập nhật database thất bại và rollback. Không được ghi đè một password hash mới hơn bằng verifier cũ chỉ vì request rehash đến chậm.

## 5. Chính sách mật khẩu khi tạo hoặc đổi

Một chính sách tốt khuyến khích mật khẩu dài, khó đoán và dễ quản lý bằng password manager. Cần xem tiêu chuẩn và bối cảnh sản phẩm thay vì áp đặt các quy tắc hình thức thiếu hiệu quả.

Các nguyên tắc thường hữu ích:

1. Cho phép mật khẩu dài và đặt giới hạn tối đa đủ lớn để hỗ trợ passphrase/password manager; giới hạn đầu vào phải nhất quán ở mọi client và server.
2. Kiểm tra mật khẩu mới với danh sách mật khẩu phổ biến, dễ đoán hoặc đã xuất hiện trong dữ liệu rò rỉ, theo cách không làm lộ mật khẩu cho dịch vụ ngoài.
3. Không ép người dùng đổi mật khẩu định kỳ vô cớ nếu không có dấu hiệu xâm phạm hoặc yêu cầu cụ thể; việc đổi liên tục dễ dẫn tới mẫu dễ đoán.
4. Không bắt buộc quy tắc ký tự hoa/thường/số/ký hiệu một cách máy móc nếu nó làm người dùng chọn mật khẩu yếu hoặc khó nhớ.
5. Cho phép paste và dùng password manager; tránh chặn tự động điền hoặc gây khó khăn cho công cụ hỗ trợ.
6. Không cắt ngắn mật khẩu âm thầm. Nếu có giới hạn do thuật toán hoặc giao thức, phải kiểm tra và thông báo rõ.
7. Thực hiện cùng quy tắc chuẩn hóa chuỗi ở lúc đăng ký, đổi và xác minh; không tự ý trim hoặc biến đổi mật khẩu theo cách khiến người dùng không thể đăng nhập.

Mật khẩu không nên được đưa vào analytics, crash report, URL, log hoặc thông báo lỗi. Không ghi lại nội dung phím người dùng gõ để phân tích hành vi đăng nhập.

## 6. Xử lý định danh và tra cứu tài khoản

Người dùng có thể đăng nhập bằng username, email hoặc định danh khác. Server phải giải quyết định danh theo quy tắc nhất quán, tránh gộp nhầm tài khoản và tránh tạo ra lỗ hổng enumeration.

Một số quyết định thiết kế:

- Xác định rõ định danh nào duy nhất trong phạm vi toàn hệ thống, tenant hay realm.
- Chuẩn hóa email/username theo quy tắc được công bố và áp dụng đồng nhất; tránh tự ý bỏ dấu chấm hoặc dấu cộng trong email theo quy tắc của một nhà cung cấp cụ thể.
- Không coi email trùng ở hai IdP là bằng chứng hai danh tính giống nhau.
- Sử dụng khóa tài khoản nội bộ ổn định sau khi tra cứu; không lấy userId do client gửi làm principal.
- Nếu hệ thống đa tenant, xác minh tài khoản thuộc đúng tenant trước khi áp dụng credential và quyền.

Không phải lúc nào cũng có thể trả lỗi chi tiết như “email chưa tồn tại” hoặc “mật khẩu sai”. Với flow đăng nhập công khai, phản hồi trung tính giúp giảm khả năng kẻ tấn công dò danh sách tài khoản.

## 7. Kiểm tra mật khẩu ở server

Một password verifier cần thực hiện các bước có kiểm soát:

1. Kiểm tra request có đúng cấu trúc, giới hạn kích thước và encoding được hỗ trợ.
2. Áp dụng rate limit trước và trong quá trình tra cứu/verify để bảo vệ tài nguyên.
3. Tra cứu account và verifier theo định danh đã chuẩn hóa.
4. Chạy hàm verify của thư viện password hashing; không tự tính hash bằng code ad-hoc.
5. Kiểm tra account status, tenant, lock/throttle state và các policy bổ sung.
6. Ghi nhận kết quả an toàn, không log bí mật.
7. Nếu mật khẩu hợp lệ, tiếp tục kiểm tra MFA, risk policy và freshness; chỉ cấp session khi flow hoàn tất.

### 7.1. Pseudocode phía server

~~~text
function passwordLogin(request):
    validateRequestShapeAndSize(request)

    normalizedIdentifier = normalizeIdentifierByPolicy(request.identifier)
    applyAbuseControls(normalizedIdentifier, request.networkContext)

    account = accountStore.find(normalizedIdentifier)

    if account does not exist:
        performComparableVerificationWork()
        recordSafeFailureEvent()
        return genericLoginFailure()

    verifier = credentialStore.getPasswordVerifier(account.id)
    passwordMatches = passwordHashLibrary.verify(
        verifier,
        request.password
    )

    if not passwordMatches:
        recordSafeFailureEvent(account.id)
        updateRateLimitState(account.id, request.networkContext)
        return genericLoginFailure()

    if account.disabled or account.suspended:
        recordSafeFailureEvent(account.id)
        return genericLoginFailure()

    authState = createServerControlledLoginState(account.id)

    if policy.requiresMFA(account, authState):
        return issueBoundMFAChallenge(authState)

    return issueSessionAfterPolicyChecks(authState)
~~~

Đây là pseudocode để mô tả thứ tự kiểm soát, không phải mã production. Thực tế cần xử lý lỗi database, timeout, race condition, nhiều tenant, password hash migration, credential revocation, MFA và chính sách tài khoản.

### 7.2. Timing và account enumeration

Nếu tài khoản không tồn tại thì server trả ngay, còn tài khoản tồn tại thì thực hiện một phép hash tốn thời gian, đối thủ có thể đo thời gian phản hồi để suy ra tài khoản. Một số hệ thống thực hiện công việc xác minh tương đương với verifier giả khi account không tồn tại, kết hợp phản hồi lỗi và kiểm soát lưu lượng.

Không có một kỹ thuật duy nhất loại bỏ hoàn toàn side channel; cần đánh giá endpoint thực tế, cache, database, rate limit và nội dung response. Mục tiêu là giảm khả năng phân biệt tài khoản qua thông báo, status code, kích thước response hoặc thời gian có hệ thống.

## 8. Rate limiting và phòng chống lạm dụng đăng nhập

Password authentication thường là mục tiêu của:

- **Brute force:** thử nhiều mật khẩu cho một tài khoản.
- **Password spraying:** thử một số mật khẩu phổ biến trên nhiều tài khoản.
- **Credential stuffing:** dùng username/password bị lộ từ dịch vụ khác.
- **Enumeration:** dò tài khoản tồn tại qua thông báo, mã phản hồi hoặc thời gian.
- **Denial of service:** cố tình gây khóa tài khoản hoặc làm cạn tài nguyên hash.

Rate limit nên kết hợp nhiều tín hiệu như account, IP/network, thiết bị, tenant, endpoint và mẫu lưu lượng. Chỉ giới hạn theo IP có thể không hiệu quả với botnet; chỉ khóa theo account có thể cho phép đối thủ khóa tài khoản nạn nhân.

Các biện pháp cần cân bằng:

- Giới hạn tốc độ và concurrency của phép verify hash.
- Tăng độ trễ hoặc yêu cầu thêm kiểm tra khi có dấu hiệu lạm dụng.
- Dùng throttle có thời hạn và phục hồi tự động, thay vì khóa vĩnh viễn dễ bị DoS.
- Theo dõi nhiều tài khoản bị thử từ một nguồn và nhiều nguồn thử cùng một tài khoản.
- Cân nhắc CAPTCHA hoặc biện pháp chống bot theo rủi ro; CAPTCHA không thay thế password verification hay MFA.
- Có quy trình hỗ trợ khi người dùng hợp lệ bị rate limit, đồng thời không tạo đường tắt yếu hơn cho kẻ tấn công.
- Không tiết lộ ngưỡng chính xác và tín hiệu nội bộ trong response công khai.

Rate limit phải được áp dụng ở nơi có thẩm quyền và khó bị bỏ qua. Kiểm tra trong JavaScript chỉ có giá trị UX; bot có thể gọi thẳng endpoint.

## 9. Mật khẩu đúng nhưng flow vẫn chưa hoàn tất: MFA và step-up

Nếu policy yêu cầu MFA, server phải tạo một **login state/challenge** riêng sau khi password verifier thành công. Trạng thái này nên gắn với principal, flow, thời hạn, bước tiếp theo và số lần thử. Nó không phải session đầy đủ.

| Trạng thái | Ý nghĩa | Quyền nên cấp |
| --- | --- | --- |
| **anonymous** | Chưa có bằng chứng xác thực | Chỉ endpoint công khai |
| **password_verified** | Mật khẩu đúng, đang chờ yếu tố tiếp theo | Chỉ thao tác trong flow MFA; không cấp quyền tài khoản đầy đủ |
| **mfa_pending** | Challenge đã phát hành | Chỉ gửi/hoàn tất challenge còn hiệu lực |
| **authenticated** | Tất cả yêu cầu xác thực áp dụng đã hoàn tất | Tạo session/token theo policy; vẫn phải authorization |
| **throttled** | Đã chạm giới hạn thử hoặc dấu hiệu abuse | Chờ hoặc đi qua quy trình hỗ trợ an toàn |
| **rejected/expired** | Bằng chứng sai hoặc flow hết hạn | Không tiếp tục bằng state cũ |

~~~mermaid
stateDiagram-v2
    [*] --> anonymous
    anonymous --> password_verified: Password đúng
    anonymous --> rejected: Password sai
    password_verified --> mfa_pending: Policy yêu cầu MFA
    password_verified --> authenticated: Không cần bước thêm
    mfa_pending --> authenticated: MFA hợp lệ
    mfa_pending --> rejected: Sai / hết hạn / replay
    rejected --> [*]
    authenticated --> [*]
~~~

Challenge không được tái sử dụng cho principal khác, flow khác hoặc thao tác khác. Server cần chống replay và giới hạn thử cho TOTP/push/recovery. Nếu MFA thất bại, không được để một endpoint khác nhận cùng trạng thái password_verified rồi cấp token đầy đủ.

### 9.1. MFA không xóa bỏ mọi rủi ro mật khẩu

MFA làm tăng khó khăn cho đối thủ nhưng không khiến mật khẩu trở nên vô hại. Credential stuffing vẫn có thể tạo lưu lượng lớn; phishing có thể chuyển tiếp OTP; malware có thể lấy session sau đăng nhập. Nên ưu tiên phương thức chống phishing như WebAuthn/passkey khi phù hợp, bảo vệ session và kiểm soát các đường khôi phục.

## 10. Cấp session sau khi xác thực thành công

Sau khi mọi điều kiện hoàn tất, server tạo **authentication context** và phát hành phương tiện duy trì trạng thái.

Với ứng dụng web, cookie session có thể được trả như sau:

~~~http
HTTP/1.1 200 OK
Set-Cookie: __Host-session=<opaque-random-session-id>; Path=/; Secure; HttpOnly; SameSite=Lax
Cache-Control: no-store
Content-Type: application/json

{
  "status": "authenticated",
  "next": "/account"
}
~~~

Cookie chỉ chứa tham chiếu phiên khó đoán; server lưu principal, thời điểm xác thực, phương thức đã hoàn thành và trạng thái phiên trong nơi kiểm soát. Không đưa password hash, OTP, seed MFA hoặc bí mật vào cookie.

Các thuộc tính quan trọng:

- **Secure:** chỉ truyền cookie qua HTTPS.
- **HttpOnly:** hạn chế JavaScript đọc cookie trực tiếp; không ngăn XSS thay mặt người dùng gửi request.
- **SameSite:** giảm một số nguy cơ CSRF; vẫn cần thiết kế CSRF phù hợp.
- **__Host-:** khi browser hỗ trợ, ràng buộc cookie với host và Path=/, không đặt Domain.
- **Rotation:** thay session ID sau đăng nhập, nâng mức xác thực hoặc sự kiện nhạy cảm theo policy.
- **Expiry/revocation:** có idle timeout, absolute lifetime và khả năng thu hồi khi đăng xuất, đổi mật khẩu hoặc phát hiện xâm phạm.

Nếu dùng access token thay session cookie, API phải xác minh token đúng issuer, audience, thời hạn, scope và quyền. ID token của OIDC dành cho client để xác nhận sự kiện đăng nhập; không dùng nó thay access token cho resource server.

### 10.1. Authentication không phải authorization

Mật khẩu đúng và MFA hoàn tất chỉ giúp xác lập principal và ngữ cảnh xác thực. Mỗi API vẫn phải kiểm tra principal có quyền đối với resource và action cụ thể hay không.

Ví dụ: người dùng đăng nhập hợp lệ có thể xem hóa đơn của mình nhưng không được đổi accountId trong request để xem hóa đơn người khác. Không dùng userId, role hoặc tenantId do client tự khai làm nguồn quyết định.

## 11. Đổi mật khẩu và tái xác thực

Đổi mật khẩu là thao tác nhạy cảm vì nó thay đổi credential chính. Flow thường cần:

1. Xác định principal từ session đã xác minh.
2. Yêu cầu xác thực lại hoặc step-up khi mức rủi ro/chính sách yêu cầu.
3. Nếu nhập mật khẩu hiện tại, kiểm tra bằng verifier đang lưu.
4. Kiểm tra mật khẩu mới theo policy, blocklist và giới hạn độ dài.
5. Tạo salt mới và password verifier mới bằng thuật toán hiện hành.
6. Cập nhật credential trong transaction hoặc thao tác nguyên tử phù hợp.
7. Xử lý các session/token khác theo policy: thu hồi toàn bộ, thu hồi phiên khác hoặc yêu cầu đăng nhập lại.
8. Gửi thông báo bảo mật qua kênh thích hợp và ghi audit event an toàn.

Không nên cho phép client gửi userId của tài khoản cần đổi mật khẩu mà không ràng buộc với principal đang xác thực. Với tài khoản đặc quyền hoặc có dấu hiệu chiếm đoạt, có thể cần MFA/passkey và quy trình hỗ trợ bổ sung.

## 12. Khôi phục mật khẩu và đặt lại credential

**Password reset** là flow khôi phục, không phải đăng nhập thông thường. Một liên kết reset thành công chứng minh người dùng có khả năng sử dụng kênh nhận liên kết trong thời gian nhất định; nó không tự chứng minh họ vừa hoàn tất mọi yếu tố MFA đã đăng ký.

Một flow an toàn thường có:

1. Người dùng yêu cầu reset với username/email.
2. Server phản hồi trung tính, áp dụng rate limit và không tiết lộ account tồn tại.
3. Nếu tài khoản phù hợp, server phát hành token reset ngẫu nhiên đủ mạnh, TTL ngắn, dùng một lần và gắn đúng tài khoản/mục đích.
4. Token được lưu theo cách không để lộ giá trị sử dụng trực tiếp nếu database bị đọc, ví dụ lưu hash của token.
5. Người dùng mở link và gửi token qua HTTPS; server kiểm tra token, expiry, trạng thái đã tiêu thụ và binding.
6. Server cho đặt mật khẩu mới theo policy; không tự động coi token reset là session đầy đủ.
7. Sau thành công, server tiêu thụ token, thay verifier, thu hồi các reset token còn lại và xử lý session/token hiện tại theo policy.
8. Thông báo qua kênh phù hợp; nếu phát hiện bất thường, kích hoạt quy trình recovery nâng cao.

~~~mermaid
sequenceDiagram
    participant U as Người dùng
    participant C as Client
    participant S as Password/Recovery Server
    participant D as Account Store
    U->>C: Yêu cầu đặt lại mật khẩu
    C->>S: Identifier
    S->>D: Tra cứu và áp dụng policy
    S-->>C: Phản hồi trung tính
    S-->>U: Gửi reset link nếu đủ điều kiện
    U->>C: Mở link reset
    C->>S: Reset token + mật khẩu mới
    S->>D: Kiểm tra token, TTL, một lần và cập nhật verifier
    D-->>S: Kết quả cập nhật
    S-->>C: Reset hoàn tất hoặc lỗi an toàn
~~~

Token reset không nên xuất hiện trong log, analytics hoặc Referer sang website bên thứ ba. Trang reset cần hạn chế tài nguyên ngoài, đặt chính sách cache phù hợp và cân nhắc làm sạch token khỏi URL sau khi đã nhận an toàn.

### 12.1. Không biến recovery thành đường vòng MFA

Nếu đăng nhập thường yêu cầu passkey hoặc MFA, nhưng reset chỉ cần một câu hỏi bí mật yếu, kẻ tấn công có thể bỏ qua cơ chế mạnh bằng recovery. Cần đánh giá rủi ro của email/SMS, recovery code, hỗ trợ thủ công và thay đổi yếu tố; quy trình phải tương xứng với giá trị tài khoản và hậu quả khi bị chiếm.

Recovery code cần đủ ngẫu nhiên, bảo vệ khi lưu, giới hạn thử và tiêu thụ một lần. Hỗ trợ nhân viên không được tự đặt lại credential chỉ dựa trên thông tin dễ tìm hoặc câu trả lời có thể đoán.

## 13. Threat model: mật khẩu bị tấn công như thế nào?

| Mối đe dọa | Cách xảy ra | Kiểm soát trọng tâm |
| --- | --- | --- |
| **Brute force** | Thử nhiều mật khẩu cho một tài khoản | Rate limit đa chiều, hash verifier tốt, MFA, phát hiện bất thường |
| **Password spraying** | Thử một vài mật khẩu phổ biến trên nhiều tài khoản | Theo dõi theo IP/network, tenant và phân bố account; blocklist mật khẩu yếu |
| **Credential stuffing** | Tái sử dụng credential rò rỉ từ dịch vụ khác | MFA/passkey, kiểm tra mật khẩu lộ, phát hiện login pattern, rate limit |
| **Phishing** | Trang giả thu mật khẩu và có thể relay OTP | Passkey/WebAuthn, cảnh báo domain, MFA chống phishing và đào tạo người dùng |
| **Database breach** | Đối thủ lấy password verifier | Argon2id/scrypt/PBKDF2 cấu hình phù hợp, salt riêng, pepper nếu cần, phân quyền và response sự cố |
| **Account enumeration** | Dò tài khoản qua response, thời gian hoặc hành vi reset | Thông báo trung tính, timing controls, rate limit và giám sát |
| **Password reuse** | Một mật khẩu bị dùng ở nhiều dịch vụ | Password manager, mật khẩu duy nhất, MFA/passkey |
| **Session hijacking** | Đánh cắp cookie/token sau khi đăng nhập | TLS, bảo vệ cookie, XSS/CSRF controls, TTL, rotation, revoke |
| **MFA bypass** | Gọi API trực tiếp sau khi chỉ qua password step | Server-side state machine, challenge binding, kiểm tra ở mọi endpoint |
| **Recovery abuse** | Lợi dụng reset link hoặc nhân viên hỗ trợ | Token dùng một lần, TTL, rate limit, verification và audit |
| **DoS bằng account lockout** | Gửi nhiều lần sai để khóa tài khoản nạn nhân | Throttle có thời hạn, kiểm soát đa chiều, tránh khóa vĩnh viễn |
| **Log/telemetry leakage** | Password hoặc reset token bị ghi vào hệ thống quan sát | Redaction, allowlist trường log, secret scanning và kiểm tra vận hành |

Một hệ thống cần giả định database, client, kênh email hoặc session có thể bị xâm phạm ở những thời điểm khác nhau. Thiết kế nhiều lớp giảm khả năng một sự cố đơn lẻ dẫn tới chiếm tài khoản.

## 14. Logging, giám sát và phản ứng

Audit giúp biết flow đã đi qua những bước nào mà không lưu bí mật xác thực.

Các sự kiện hữu ích có thể gồm:

- **password.login.succeeded** hoặc **password.login.failed**.
- **password.verifier.upgraded**.
- **password.changed** và **password.reset.completed**.
- **mfa.challenge.issued**, **mfa.challenge.failed**, **mfa.challenge.completed**.
- **session.created**, **session.rotated**, **session.revoked**.
- **login.rate_limited** hoặc **credential_stuffing.suspected**.

Sự kiện nên gắn correlation ID, principal ID nội bộ khi biết, thời điểm, tenant, loại phương thức, phiên bản policy và mã lý do đã được kiểm soát. Không log mật khẩu, password hash đầy đủ, OTP, seed TOTP, reset token, cookie, authorization header hoặc raw access token.

Khi có nghi ngờ credential bị lộ:

1. Xác định phạm vi tài khoản và phiên có thể bị ảnh hưởng.
2. Thu hồi session/token và reset credential theo chính sách.
3. Yêu cầu MFA/passkey hoặc bước xác minh lại khi cần.
4. Kiểm tra các sự kiện enrollment, linking và recovery gần thời điểm xâm phạm.
5. Thông báo người dùng qua kênh an toàn và hướng dẫn bảo vệ các tài khoản dùng chung mật khẩu.
6. Ghi nhận nguyên nhân, kiểm tra log và điều chỉnh kiểm soát.

Không gửi mật khẩu cũ hoặc token reset qua email hỗ trợ; nhân viên không cần biết plaintext password để hỗ trợ người dùng.

## 15. Ví dụ thiết kế API

Một API có thể tách kết quả password verification khỏi session cuối cùng. Hợp đồng khái niệm:

~~~ts
type PasswordLoginResult =
  | {
      kind: "mfa_required";
      flowId: string;
      nextStep: "totp" | "passkey";
      expiresAt: string;
    }
  | {
      kind: "authenticated";
      next: string;
    }
  | {
      kind: "rejected";
      code: "INVALID_CREDENTIALS" | "RATE_LIMITED";
    };
~~~

Các trường trong response chỉ để client điều hướng giao diện. Server giữ trạng thái flow và authentication context; client không được gửi lại **kind: authenticated** để tự tạo session.

Một API thiết kế tốt cần:

- Chỉ dùng HTTPS; giới hạn kích thước request và từ chối input sai cấu trúc.
- Không nhận role, assurance, principal hoặc trạng thái MFA như dữ liệu có thẩm quyền từ client.
- Không trả verifier, salt, hash hoặc metadata nội bộ không cần thiết.
- Dùng response trung tính cho login/reset ở nơi cần chống enumeration.
- Áp dụng rate limit và chống abuse ở server/gateway.
- Kiểm tra session, CSRF và authorization cho endpoint tiếp theo.
- Có idempotency hoặc kiểm soát double-submit đối với các thao tác nghiệp vụ quan trọng.

## 16. Checklist review một password authentication flow

| Câu hỏi | Dấu hiệu thiết kế tốt |
| --- | --- |
| Mật khẩu được truyền thế nào? | HTTPS, không qua URL, không ghi log, không gửi tới analytics |
| Mật khẩu được lưu thế nào? | Hash chuyên dụng, salt riêng, tham số được benchmark, không plaintext |
| Có quản lý version/rehash không? | Có nâng cấp verifier an toàn khi login thành công |
| Chính sách tạo mật khẩu có hữu ích? | Cho passphrase/password manager, kiểm tra mật khẩu phổ biến/lộ, không ép quy tắc hình thức vô ích |
| Có chống brute force và credential stuffing? | Rate limit đa tín hiệu, kiểm soát concurrency, giám sát và phản ứng |
| Có tránh enumeration? | Thông báo trung tính và giảm side channel |
| MFA được kiểm tra ở đâu? | Verifier/server, challenge gắn flow, TTL, chống replay và giới hạn thử |
| Khi password đúng nhưng MFA chưa xong? | Chỉ có trạng thái hạn chế; chưa cấp session đầy đủ |
| Session được cấp thế nào? | ID khó đoán, rotation, cookie an toàn, TTL và revoke |
| Authorization ở đâu? | Tại server/API trên principal, resource và action |
| Đổi mật khẩu có an toàn? | Reauthentication theo policy, cập nhật verifier nguyên tử, xử lý phiên khác |
| Recovery có yếu hơn login? | Không có đường vòng; token reset ngẫu nhiên, một lần, TTL và audit |
| Có bảo vệ bí mật trong log? | Redaction, không log password/OTP/token/hash |
| Có kiểm thử đường bypass? | Gọi API trực tiếp, replay challenge, sửa principal, rate limit và session cũ |

### Tình huống tự kiểm tra

**Tình huống 1:** Server lưu SHA-256(password + salt) cho mỗi tài khoản. Đã đủ an toàn chưa?

**Trả lời:** chưa. Salt riêng là cần thiết nhưng SHA-256 quá nhanh cho password storage. Nên dùng password hashing function chuyên dụng như Argon2id, scrypt, bcrypt hoặc PBKDF2 với tham số phù hợp.

**Tình huống 2:** Password đúng nhưng MFA chưa hoàn tất. Client gọi endpoint lấy dữ liệu bằng cách thêm **mfaPassed=true**. Server nên làm gì?

**Trả lời:** bỏ qua cờ do client tự khai; kiểm tra trạng thái flow và authentication context do server kiểm soát. Nếu MFA còn thiếu, từ chối hoặc yêu cầu hoàn tất challenge.

**Tình huống 3:** Người dùng reset mật khẩu qua email. Có nên giữ mọi session cũ?

**Trả lời:** tùy policy và rủi ro, nhưng cần đánh giá thu hồi/rotation các session và token, thông báo bảo mật và kiểm tra dấu hiệu xâm phạm. Reset thành công không tự chứng minh các session cũ còn an toàn.

**Tình huống 4:** Hệ thống trả “email không tồn tại” khi account lookup thất bại và “sai mật khẩu” khi account có nhưng mật khẩu sai. Rủi ro là gì?

**Trả lời:** account enumeration. Với endpoint công khai, nên dùng phản hồi trung tính và kiểm soát timing/rate để giảm khả năng dò tài khoản.

**Tình huống 5:** Người dùng đăng nhập bằng password + TOTP. Điều này có tự chống phishing không?

**Trả lời:** không. OTP có thể bị phishing proxy chuyển tiếp. Có thể tăng khả năng chống phishing bằng WebAuthn/passkey và kiểm tra origin/RP ID đúng cách.

## 17. Ghi nhớ

**Password authentication** là quy trình server xác minh mật khẩu ứng viên với verifier được lưu an toàn, áp dụng các kiểm soát chống lạm dụng và chỉ cấp phiên sau khi tất cả yêu cầu xác thực đã hoàn thành. Mật khẩu cần được bảo vệ khi truyền, hash bằng thuật toán chuyên dụng với salt riêng, kiểm tra theo policy hữu ích và không bao giờ xuất hiện trong log.

Để flow an toàn, hãy kiểm soát từ đầu đến cuối: **đăng ký credential → lưu verifier → nhận và kiểm tra mật khẩu → rate limit và xử lý lỗi → MFA/step-up → cấp session/token → authorization → đổi và khôi phục credential**. Mỗi bước phải có trạng thái phía server, giới hạn thời gian và quyền hạn rõ ràng; không để UI, header hoặc dữ liệu client tự khai quyết định người dùng đã xác thực hay được phép làm gì.
