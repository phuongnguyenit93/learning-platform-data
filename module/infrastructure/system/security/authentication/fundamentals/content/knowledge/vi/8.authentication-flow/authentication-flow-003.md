# Credential submission — Gửi bằng chứng xác thực

> **Chương:** Authentication flow  
> **Chủ đề:** Credential submission

**Credential submission** là giai đoạn client đưa **bằng chứng xác thực** tới thành phần có thẩm quyền kiểm tra trong một luồng đăng nhập. Với mật khẩu, bằng chứng thường là mật khẩu được gửi qua kênh TLS tới máy chủ xác thực. Với OTP, đó là một mã ngắn có thời hạn. Với passkey/WebAuthn, client gửi **phản hồi có chữ ký** đối với một thử thách mới, không gửi khóa riêng. Với chứng chỉ client, bằng chứng sở hữu khóa được tạo trong bắt tay TLS. Với đăng nhập qua Identity Provider (IdP), ứng dụng dựa vào kết quả xác thực do IdP cung cấp, thay vì thu thập mật khẩu của IdP.

Chính sự khác nhau này làm rõ một nguyên lý quan trọng: **không phải mọi credential đều được “gửi” dưới dạng bí mật có thể tái sử dụng**. Thiết kế một bước submission an toàn phải hiểu loại bằng chứng, nơi nó được kiểm tra, cách ràng buộc với phiên và mục đích, cùng những ranh giới tin cậy mà nó đi qua.

Bài học tập trung vào bước gửi credential trong module **SECURITY_AUTHENTICATION_FUNDAMENTALS**: từ mật khẩu, MFA, passkey và chứng chỉ tới phiên/token, phòng chống phishing, replay, lạm dụng đăng nhập và bảo vệ đường truyền. Phần xác minh credential, phát hành phiên và kiểm tra quyền được nhắc tới để đặt bước submission vào đúng ngữ cảnh, nhưng là các quyết định riêng.

## 1. Kết quả học tập

Sau bài học, người học có thể:

1. Giải thích chính xác **credential submission** nằm ở đâu trong authentication flow và vì sao không được đồng nhất với xác thực thành công.
2. Phân biệt dữ liệu được gửi ở các luồng password, OTP, passkey/WebAuthn, client certificate và đăng nhập liên kết OIDC.
3. Mô hình hóa các ranh giới tin cậy giữa giao diện, trình duyệt/ứng dụng, reverse proxy, backend, authentication service và IdP.
4. Thiết kế request submission qua TLS an toàn, tránh lộ bí mật qua URL, log, analytics, browser storage và hệ thống trung gian.
5. Nhận diện phishing, replay, credential stuffing, login CSRF, user enumeration và các đường vòng của MFA.
6. Định nghĩa hành vi server khi nhận credential: validation, rate limiting, challenge binding, xử lý lỗi, logging, chuyển bước và phát hành phiên.

## 2. Đặt submission vào toàn bộ luồng xác thực

Một luồng authentication thường có các bước:

1. **Khởi tạo:** client yêu cầu đăng nhập; server nhận diện phương thức, tài khoản/tenant và bối cảnh rủi ro nếu cần.
2. **Tạo thử thách hoặc biểu mẫu:** server phát challenge, phiên đăng nhập tạm hoặc biểu mẫu phù hợp; với một số phương thức, không cần challenge riêng trước khi gửi.
3. **Credential submission:** client đưa bằng chứng hoặc phản hồi thử thách tới **đúng verifier/IdP**.
4. **Verification:** verifier kiểm tra bằng chứng, trạng thái tài khoản, nguồn, thời hạn, chống lạm dụng và yêu cầu MFA/step-up.
5. **Session/token issuance:** chỉ sau khi đủ điều kiện, thành phần tin cậy mới cấp phiên hoặc token đúng đối tượng nhận.
6. **Authorization:** API kiểm tra quyền đối với hành động và tài nguyên khi có yêu cầu truy cập.

~~~mermaid
flowchart LR
    A["Khởi tạo đăng nhập"] --> B["Nhận phương thức / challenge"]
    B --> C["Credential submission"]
    C --> D{"Verifier chấp nhận?"}
    D -->|"Chưa đủ mức bảo đảm"| E["MFA / step-up"]
    E --> C
    D -->|"Thất bại"| F["Phản hồi lỗi có kiểm soát"]
    D -->|"Đủ điều kiện"| G["Phát hành phiên/token"]
    G --> H["API kiểm tra authorization"]
~~~

**Gửi credential không tạo ra quyền truy cập.** Một request gửi đúng cấu trúc vẫn có thể bị từ chối vì mật khẩu sai, challenge hết hạn, tài khoản bị khóa, rủi ro cao hoặc yêu cầu xác thực bổ sung. Chỉ server có thẩm quyền mới quyết định trạng thái xác thực; client không thể hợp thức hóa request bằng một cờ tự khai như **isAuthenticated = true**.

### 2.1. Gửi cái gì, tới đâu và ai kiểm tra?

| Phương thức | Bằng chứng được đưa đi | Nơi kiểm tra | Điều tuyệt đối cần phân biệt |
| --- | --- | --- | --- |
| **Password** | Chuỗi mật khẩu tới authentication endpoint qua TLS | Authentication service so với password verifier | Gửi mật khẩu qua TLS không có nghĩa được phép ghi log/lưu lại ở client |
| **TOTP** | Mã một lần theo thời gian; có thể kèm ngữ cảnh challenge | Server sở hữu hoặc có quyền xác minh TOTP secret | OTP có thể bị phishing/replay trong cửa sổ còn hiệu lực |
| **SMS/email OTP** | Mã nhận qua kênh khác, sau đó nhập vào luồng xác minh | Server kiểm tra mã đã phát và trạng thái yêu cầu | Kiểm soát kênh không chứng minh danh tính pháp lý hoặc khả năng chống phishing |
| **Passkey/WebAuthn** | Credential ID, authenticator data, client data, chữ ký và dữ liệu cần thiết | RP/WebAuthn verifier kiểm tra challenge, origin/RP ID, public key | **Không gửi private key**; bằng chứng được ràng buộc với RP |
| **Client certificate / mTLS** | Certificate chain và bằng chứng ký trong TLS handshake | TLS endpoint xác minh chain, danh tính và proof of possession | Certificate công khai không phải bí mật và không tự cấp quyền |
| **OIDC SSO** | Người dùng xác thực tại IdP; ứng dụng nhận authorization code/result | IdP kiểm tra credential; RP xác minh kết quả theo giao thức | RP không nhận mật khẩu của IdP trong luồng chuẩn |

Khi thiết kế API, cần mô tả rõ loại dữ liệu, ai có quyền nhận nó, thời hạn và những thành phần trung gian sẽ nhìn thấy request.

## 3. Mô hình ranh giới tin cậy của một lần submission

Giả sử học viên đăng nhập vào một nền tảng học tập bằng mật khẩu:

~~~mermaid
flowchart LR
    U["Người dùng"] --> C["Trình duyệt / native app<br/>Không được mặc định tin cậy"]
    C -->|"HTTPS: credential submission"| G["Reverse proxy / BFF"]
    G -->|"Kênh nội bộ bảo vệ"| A["Authentication service"]
    A -->|"Kiểm tra verifier"| V[("Kho credential")]
    A -->|"Kết quả và policy"| S[("Session store")]
    A -->|"Set-Cookie hoặc kết quả phù hợp"| G
    G --> C
    X["Analytics / log / tracing"] -.->|"Không thu credential thô"| G
~~~

Các câu hỏi cần giải quyết trước khi triển khai:

- **Client có đáng tin không?** JavaScript trong browser, native app, extension, malware và request từ công cụ HTTP đều có thể bị sửa. Không tin rằng form đúng giao diện thì request sẽ đúng.
- **Credential được gửi tới đúng origin không?** URL/host, chứng chỉ TLS, luồng redirect và cấu hình miền đăng nhập phải đúng. Giao diện phishing có thể thu thập mật khẩu trước khi một yêu cầu HTTPS thực sự đến hệ thống.
- **TLS kết thúc ở đâu?** Reverse proxy nhìn thấy plaintext sau khi giải mã TLS. Proxy, middleware, service mesh và APM phải được xét trong mô hình bảo vệ bí mật.
- **Hệ thống nào được phép kiểm chứng?** Backend chỉ nên chuyển dữ liệu qua các kết nối bảo vệ cần thiết; không phát tán password/OTP tới nhiều microservice.
- **Server đang xác thực chủ thể nào?** Tenant, login transaction, account lookup và challenge phải được xác định bởi server, không chỉ lấy từ một thuộc tính tùy ý do client gửi.

**Ranh giới tin cậy** không đồng nhất với “mạng nội bộ”. Một service nội bộ bị chiếm có thể giả mạo header hoặc request nếu backend thiếu xác thực service và hợp đồng chuyển tiếp dữ liệu.

## 4. Mật khẩu: từ biểu mẫu tới verifier

Mật khẩu là **bí mật có thể tái sử dụng**: nếu kẻ tấn công lấy được bản rõ, họ có thể dùng lại tới khi mật khẩu đổi hoặc tài khoản bị bảo vệ bởi các lớp khác. Do đó, gửi password an toàn là giảm tối đa nơi có thể quan sát và lưu giữ bí mật.

### 4.1. Biểu mẫu đăng nhập trên web

Biểu mẫu nên dùng HTTPS và gửi request bằng **POST** tới endpoint xác thực. Nếu ứng dụng truyền bằng JSON, mật khẩu nằm trong body của request; nếu dùng form encoding, nó vẫn phải nằm trong body.

~~~http
POST /auth/login HTTP/1.1
Host: login.example.org
Content-Type: application/json

{
  "identifier": "student@example.org",
  "password": "sample-password-for-illustration"
}
~~~

Đây chỉ là **request minh họa**, không phải mật khẩu để dùng trong hệ thống thực tế. Mọi giá trị trong request đều chưa được tin cậy cho tới khi server kiểm tra. Endpoint cần có kích thước body tối đa, phương thức và content type được chấp nhận, validation identifier và xử lý lỗi an toàn.

**Không đưa mật khẩu vào URL**, query string, fragment, đường dẫn, header tự chế, tham số redirect hoặc thông điệp gửi qua analytics. URL có thể xuất hiện ở lịch sử trình duyệt, log proxy, referrer, hệ thống giám sát và báo cáo lỗi. **POST không tự mã hóa dữ liệu**: TLS mới bảo vệ dữ liệu trên đường truyền; server và các proxy vẫn có thể thấy bản rõ sau khi giải mã.

### 4.2. Frontend nên và không nên làm gì?

- Hiển thị form đúng origin; dùng trường password chuyên dụng, hỗ trợ trình quản lý mật khẩu và autofill phù hợp.
- Chấp nhận thao tác dán và mật khẩu dài; tránh cản trở password manager hoặc yêu cầu nhập từ bàn phím ảo chỉ vì giả định sẽ an toàn hơn.
- Không lưu password trong **localStorage**, sessionStorage, IndexedDB, URL, state của analytics, replay session của công cụ hỗ trợ khách hàng hoặc bản ghi telemetry.
- Không coi việc ẩn ký tự khi nhập là cơ chế bảo vệ khi truyền. Browser vẫn giữ giá trị trong bộ nhớ trong lúc thao tác; cần tránh kéo dài thời gian lưu và vô tình xuất dữ liệu.
- Hạn chế script bên thứ ba trên trang login, triển khai CSP và phòng chống XSS; nếu script độc hại chạy trên trang đăng nhập, nó có thể đọc password trước khi submit.
- Không gửi lại password ở response hay lưu vào global state của ứng dụng sau đăng nhập; tránh đưa dữ liệu nhạy cảm vào thông báo lỗi.

Với ứng dụng native, cần xác thực server TLS đúng cách, bảo vệ giao diện và tránh đưa password vào analytics hoặc crash report. **Không tắt kiểm tra chứng chỉ TLS để sửa lỗi môi trường**; hành vi đó có thể mở đường cho tấn công man-in-the-middle.

### 4.3. TLS bảo vệ điều gì?

TLS cung cấp tính bảo mật truyền tải giữa các **endpoint TLS thực tế**: chống nghe lén/chỉnh sửa trên mạng nếu xác minh chứng chỉ và tên server đúng, dùng phiên bản/cipher suite phù hợp. TLS **không** ngăn:

- Trang phishing đặt trên một miền khác nhưng cũng có chứng chỉ HTTPS hợp lệ;
- JavaScript độc hại hoặc browser extension đọc dữ liệu trước khi submit;
- Proxy được ủy quyền giải mã TLS vô tình ghi log body;
- Server bị xâm nhập hoặc ứng dụng lưu password ở nơi không phù hợp;
- Credential stuffing từ danh sách mật khẩu đã lộ ở dịch vụ khác.

Vì vậy, thiết kế submission cần kết hợp TLS, bảo vệ client/server, kiểm soát logging, chống phishing và chống lạm dụng.

## 5. Server tiếp nhận password như thế nào?

Authentication endpoint không nên chuyển thẳng từ “body có password” sang “trả session”. Nó cần xử lý request theo trình tự có kiểm soát.

~~~text
receive_password_submission(request):
    require_protected_channel(request)
    enforce_method_content_type_size_limits(request)
    validate_request_shape(request)
    context = resolve_tenant_and_login_transaction(request)
    enforce_rate_and_abuse_controls(context, request)

    account = lookup_account_without_trusting_client_role(request.identifier, context)
    credential_result = verify_password_with_server_side_verifier(account, request.password)
    if credential_result is not valid or account is not eligible:
        record_redacted_security_event("login_failed", context)
        return generic_failure

    if policy_requires_additional_factor(account, context):
        return create_server_controlled_mfa_step(account, context)

    session = create_fresh_authenticated_session(account, context)
    record_redacted_security_event("login_succeeded", context)
    return deliver_session_securely(session)
~~~

**Pseudocode** này diễn đạt trách nhiệm chính, không phải mã có thể triển khai ngay. Một hệ thống thực tế cần quản lý giao dịch đồng thời, lỗi mạng, timing, CSRF, khóa tài khoản, auditing và cấu hình phù hợp.

### 5.1. Password verifier và secret handling

Máy chủ nên so khớp password với **password hash chậm, có salt**, sử dụng thuật toán password hashing chuyên dụng như Argon2id với tham số được quản lý. Không lưu plaintext hoặc dùng hash nhanh thuần túy (ví dụ SHA-256) làm password verifier. Nếu có pepper, quản lý nó riêng trong hệ thống secret/key management.

Server chỉ cần giữ plaintext password trong bộ nhớ trong thời gian cần thiết để xác minh; không ghi vào DB, log, exception message hoặc message queue. Với môi trường managed runtime, việc xóa sạch mọi bản sao trong bộ nhớ có thể không được bảo đảm tuyệt đối, nên cần **tránh tạo bản sao và tránh lưu kéo dài**.

### 5.2. Phản hồi lỗi không làm lộ tài khoản

Thông báo “Email không tồn tại” khác biệt rõ với “Sai mật khẩu” có thể làm lộ danh sách người dùng. Thông thường nên dùng phản hồi chung cho cặp identifier/password không hợp lệ và giới hạn thông tin ở API công khai. Cần cân nhắc timing và dấu hiệu khác như mã lỗi, thời gian phản hồi, rate limit hoặc trạng thái MFA.

Không nên trả về password hash, salt, pepper, thông tin cấu hình bảo mật hoặc lý do kiểm tra nội bộ. Hệ thống logging có thể ghi mã lý do đã được chuẩn hóa để điều tra, nhưng không làm lộ cho client và không chứa bí mật.

## 6. OTP và MFA: gửi mã nhưng vẫn cần bối cảnh

Trong MFA, credential submission có thể diễn ra **nhiều lần** trong một giao dịch đăng nhập: mật khẩu trước, sau đó TOTP/SMS OTP, push challenge hoặc WebAuthn. Thành công của yếu tố đầu chưa được phép tạo phiên có mức bảo đảm đầy đủ khi chính sách còn yêu cầu yếu tố tiếp theo.

### 6.1. TOTP

TOTP là mã sinh từ bí mật chung và thời gian. Khi người dùng gửi mã, verifier kiểm tra mã dự kiến trong cửa sổ chấp nhận phù hợp, giới hạn số lần thử và cần kiểm soát dùng lại mã trong cùng cửa sổ khi áp dụng chính sách cho yếu tố này.

~~~http
POST /auth/challenges/totp/verify HTTP/1.1
Host: login.example.org
Content-Type: application/json

{
  "login_transaction": "opaque-server-issued-handle",
  "otp": "123456"
}
~~~

**Mã trong ví dụ là dữ liệu giả.** Handle giao dịch phải đủ khó đoán hoặc được bảo vệ thích hợp, có thời hạn và liên kết với tài khoản/phương thức được server kiểm soát. Server phải tự lưu trạng thái “đã qua yếu tố thứ nhất”; không tin cờ **passwordVerified** do client gửi.

Mã TOTP là bí mật ngắn có thời hạn; kẻ tấn công có thể phishing theo thời gian thực và nhanh chóng dùng lại trước khi hết hạn. TOTP hỗ trợ MFA, nhưng **không phải phương thức chống phishing có ràng buộc origin** như WebAuthn.

### 6.2. SMS OTP, email OTP và push

- **SMS OTP:** cân nhắc SIM swap, chuyển số/tái cấp số, chặn tin nhắn và phishing. OTP gửi đến số điện thoại không chứng minh tư cách nhân viên hay danh tính pháp lý.
- **Email OTP:** độ an toàn phụ thuộc tài khoản email và kênh gửi. Nếu email cũng là đường khôi phục yếu của tài khoản, cần đánh giá rủi ro vòng lặp.
- **Push approval:** người dùng không nhất thiết nhập mã; thiết bị nhận challenge và gửi phản hồi chấp thuận. Cần chống **push fatigue**, hiển thị ngữ cảnh giao dịch và cân nhắc number matching, giới hạn số lần gửi.

Trên server, các thử thách MFA cần được gắn với **đúng subject, phiên/giao dịch, mục đích và thời hạn**. Không cho phép dùng mã của yêu cầu thay đổi email để vượt qua thử thách đăng nhập hoặc dùng kết quả MFA ở tài khoản A cho tài khoản B.

### 6.3. Recovery code không phải OTP thông thường

Recovery code thường là một credential dự phòng một lần; nếu bị lộ, kẻ tấn công có thể dùng đường khôi phục để chiếm tài khoản. Khi tiếp nhận, phải kiểm tra phạm vi đúng tài khoản, trạng thái chưa dùng và giới hạn thử; ghi nhận đã sử dụng theo cách nguyên tử để không có hai request đồng thời cùng thành công. Không log mã, không trả lại mã đã dùng và thông báo sự kiện recovery phù hợp.

## 7. Passkey/WebAuthn: gửi assertion, không gửi khóa riêng

Passkey/WebAuthn thay đổi căn bản bản chất của submission: trình duyệt và authenticator tạo phản hồi được ký đối với **challenge mới của Relying Party (RP)**. Private key nằm trong authenticator hoặc cơ chế lưu/đồng bộ khóa của nền tảng, **không được gửi đến ứng dụng web hoặc server**.

### 7.1. Luồng xác thực với passkey

~~~mermaid
sequenceDiagram
    participant U as Người dùng
    participant B as Browser / Platform
    participant A as Authenticator
    participant R as Relying Party Server
    U->>B: Chọn đăng nhập bằng passkey
    B->>R: Yêu cầu WebAuthn options
    R-->>B: Challenge mới + RP/UV policy
    B->>A: navigator.credentials.get với publicKey options
    A->>A: Kiểm tra quyền sử dụng khóa, tạo chữ ký
    A-->>B: Assertion: ID, authenticatorData, signature...
    B->>R: Gửi assertion qua HTTPS
    R->>R: Kiểm tra challenge, origin/RP ID, chữ ký, policy
    R-->>B: Kết quả và phiên nếu hợp lệ
~~~

Các dữ liệu điển hình được gửi về RP gồm **credential ID**, **authenticatorData**, **clientDataJSON**, **signature** và đôi khi **userHandle**. Không có private key trong response. Server tra khóa công khai đã đăng ký và xác minh:

1. Challenge khớp với một yêu cầu chưa dùng, do server phát và còn hiệu lực;
2. **Origin** trong client data và **RP ID hash** đúng cấu hình và ngữ cảnh;
3. Kiểu thao tác đúng là authentication, chữ ký hợp lệ theo public key tương ứng credential;
4. Các cờ user presence/user verification đáp ứng chính sách;
5. Credential được ánh xạ tới subject hợp lệ, không bị thu hồi; những tín hiệu như signature counter được xử lý theo đặc tính authenticator.

Một challenge phải được ràng buộc với **giao dịch xác thực/phiên khởi tạo**; không chấp nhận assertion cũ dùng lại nhiều lần. Kiểm tra ở server, không chỉ ở JavaScript. Yêu cầu user verification thích hợp giúp nâng mức bảo đảm nhưng phải xét cấu hình authenticator và phương thức khôi phục.

### 7.2. Vì sao WebAuthn có khả năng chống phishing?

Authenticator tạo bằng chứng theo **RP ID/origin** của trang hợp lệ. Một website giả mạo ở miền khác thông thường không thể yêu cầu authenticator ký hợp lệ cho RP ID thật. Đây là khác biệt so với việc gõ password/OTP vào một trang giống hệt về giao diện.

Khả năng chống phishing không có nghĩa hệ thống không còn rủi ro. Nếu phiên đã tạo bị đánh cắp, luồng recovery yếu hoặc kẻ tấn công thêm authenticator mới qua một phiên bị chiếm, tài khoản vẫn có thể bị ảnh hưởng. Cần bảo vệ cả phiên, thêm/xóa passkey và đường recovery.

## 8. Chứng chỉ client: submission diễn ra ở TLS handshake

Trong **mutual TLS (mTLS)**, server yêu cầu client certificate. Client trình bày chứng chỉ và chứng minh sở hữu khóa riêng bằng chữ ký gắn với TLS handshake. Phần mềm ứng dụng thường không gửi private key trong HTTP body.

~~~mermaid
flowchart LR
    C["Client có certificate + private key"] -->|"mTLS handshake"| G["TLS terminator / gateway"]
    G -->|"Kiểm tra chain, SAN, EKU, proof of possession"| M["Ánh xạ principal"]
    M -->|"Ngữ cảnh được bảo vệ"| A["API authorization"]
~~~

Kiểm tra cần có: trust anchor/CA được phép, chain, validity, Key Usage/EKU phù hợp, SAN chứa **đúng identity kỳ vọng**, chính sách thu hồi và proof of possession. Chỉ thấy chứng chỉ được CA ký không đủ để xác định đúng principal hoặc quyền của nó.

Nếu TLS được kết thúc ở gateway, backend **không tự nhìn thấy handshake của client**. Header mang thông tin client certificate chỉ đáng tin nếu gateway xóa/ghi đè mọi header cùng tên do client gửi, backend xác thực gateway và kênh chuyển tiếp có tính toàn vẹn. Một header **X-Client-Cert** gửi trực tiếp từ Internet không phải bằng chứng sở hữu private key.

Ở tầng ứng dụng vẫn cần authorization. Workload có certificate hợp lệ của report-worker không vì thế được phép gọi API hoàn tiền nếu chỉ có quyền đọc báo cáo.

## 9. SSO: ứng dụng chuyển người dùng đến IdP

Với **OpenID Connect (OIDC)**, ứng dụng thường không nhận mật khẩu của IdP. Người dùng xác thực trực tiếp tại IdP, ứng dụng nhận kết quả qua giao thức. Đây là lựa chọn quan trọng để giảm phạm vi hệ thống cần xử lý credential nhạy cảm.

Một luồng Authorization Code với PKCE điển hình:

1. RP tạo giao dịch đăng nhập, **state**, PKCE **code verifier/challenge** và nonce khi cần.
2. Trình duyệt chuyển người dùng tới authorization endpoint của IdP đã cấu hình, cùng **redirect URI** đăng ký chính xác.
3. Người dùng gửi password/passkey/MFA tới **IdP**, không gửi tới RP.
4. IdP trả **authorization code** qua redirect URI, gắn với giao dịch và điều kiện giao thức.
5. RP kiểm tra state, dùng code verifier đổi code lấy token qua token endpoint; xác minh ID token theo issuer, audience, chữ ký, thời hạn và các điều kiện thích hợp.
6. RP ánh xạ **issuer + subject** sang danh tính nội bộ và thiết lập phiên của ứng dụng theo chính sách.

~~~mermaid
sequenceDiagram
    participant U as Browser / User
    participant R as Relying Party
    participant I as Identity Provider
    U->>R: Chọn đăng nhập SSO
    R-->>U: Redirect + state + PKCE challenge
    U->>I: Xác thực tại IdP (credential gửi tới IdP)
    I-->>U: Redirect tới RP với authorization code
    U->>R: Code + state
    R->>I: Code + PKCE verifier tới token endpoint
    I-->>R: Token response
    R->>R: Kiểm chứng, ánh xạ subject, tạo phiên
    R-->>U: Phiên của ứng dụng
~~~

**Authorization code không phải password** nhưng vẫn nhạy cảm, có thời hạn ngắn và không được để lộ hoặc dùng lại. Các lỗi callback như login CSRF, thiếu state/PKCE, redirect URI quá rộng hoặc nhầm issuer có thể gây chiếm phiên dù bước nhập mật khẩu tại IdP an toàn.

Một ứng dụng native dùng OAuth/OIDC nên sử dụng luồng qua **browser do hệ điều hành cung cấp** theo hướng dẫn nền tảng; không tự thu thập password của IdP bằng một form trong app hoặc nhúng một webview có khả năng quan sát thông tin đăng nhập. **OAuth access token không phải ID token**; API chỉ chấp nhận access token đúng issuer, audience, loại token, scope và điều kiện hợp lệ.

## 10. Chống phishing và credential interception

Kẻ tấn công có thể tạo giao diện đăng nhập giống hệt hệ thống hợp lệ, dụ người dùng nhập password và OTP, sau đó lập tức gửi các giá trị này tới dịch vụ thật. Một chứng chỉ HTTPS của trang giả **không chứng minh nó là trang đúng**.

| Biện pháp | Bảo vệ | Giới hạn |
| --- | --- | --- |
| **TLS + hostname verification** | Chống nghe lén/chỉnh sửa trên kênh tới origin đã chọn | Không ngăn người dùng tự đến origin giả |
| **HSTS** | Buộc dùng HTTPS cho domain đã được chính sách áp dụng | Không làm miền giả trở thành miền đúng |
| **Password manager/autofill theo origin** | Giảm nhập nhầm vào domain lạ khi trình quản lý khóa theo website | Phụ thuộc hành vi và cấu hình; không phải bảo đảm tuyệt đối |
| **Passkey/WebAuthn** | Ràng buộc assertion với RP ID/origin, chống phishing credential | Không thay thế bảo vệ phiên/recovery |
| **Phân tách IdP/RP đúng giao thức** | Giảm số ứng dụng trực tiếp nhìn thấy password | IdP và luồng redirect vẫn phải được bảo vệ |
| **Giới hạn script/CSP, chống XSS** | Giảm khả năng lấy credential trên chính trang hợp lệ | Không thể thay thế kiểm soát server và bảo vệ browser |

Chỉ thị người dùng “kiểm tra ổ khóa” là chưa đủ: trang giả cũng có thể có HTTPS. Thiết kế hệ thống nên ưu tiên phương thức có tính chống phishing kỹ thuật và giữ chặt quy trình recovery, reset password, thêm authenticator.

## 11. Chống replay ở đúng lớp

**Replay** là việc tái sử dụng một bằng chứng hoặc thông điệp đã từng hợp lệ. Trong submission, cần phân biệt:

| Loại bằng chứng | Replay có thể xảy ra thế nào? | Cách giảm rủi ro |
| --- | --- | --- |
| **Password** | Dùng lại mật khẩu bị lộ ở thời điểm khác | MFA chống phishing, mật khẩu không tái sử dụng, chống stuffing và đổi khi bị lộ |
| **TOTP** | Kẻ tấn công dùng mã trong cửa sổ còn hiệu lực | Giới hạn thử, chống dùng lại mã, tăng cường phương thức chống phishing |
| **Recovery code** | Hai request cố dùng cùng mã | Tiêu thụ nguyên tử một lần, chặn mã đã dùng |
| **WebAuthn assertion** | Gửi lại assertion đã ký của giao dịch cũ | Challenge mới, một lần, ràng buộc transaction/origin/RP ID |
| **mTLS proof** | Sao chép transcript/chữ ký từ handshake trước | TLS chuẩn ràng buộc chữ ký với handshake hiện tại |
| **Authorization code** | Đổi lại code cũ hoặc code bị đánh cắp | Code một lần, TTL ngắn, PKCE, redirect URI chính xác |
| **Bearer token** | Gửi lại token lấy được sau đăng nhập | TTL, bảo vệ lưu trữ, thu hồi và sender-constrained token khi cần |

TLS ngăn nghe lén đường truyền nhưng **không khiến password thành một mật khẩu dùng một lần**. Một password đã bị lộ qua phishing vẫn có thể được dùng từ thiết bị khác. Bên cạnh đó, mTLS không tự chặn replay của yêu cầu **chuyển tiền hai lần** trong cùng phiên hợp lệ; nghiệp vụ cần idempotency key hoặc cơ chế xác nhận giao dịch thích hợp.

### 11.1. Ràng buộc request với ngữ cảnh

Khi một submission phụ thuộc thử thách, server nên duy trì các thuộc tính tối thiểu:

- **challenge_id / transaction_id** khó đoán, thời hạn rõ;
- subject/tenant hoặc trạng thái chọn tài khoản do server kiểm soát;
- **purpose** như login, step-up, reset-password, enroll-passkey;
- phương thức và mức bảo đảm yêu cầu;
- số lần thử, trạng thái đã dùng/hết hạn/đã hủy;
- liên kết với phiên khởi tạo, origin/RP ID hoặc thiết bị khi giao thức yêu cầu.

Không dùng challenge đã tạo để **verify_email** làm bằng chứng hợp lệ cho **login**. Đối với thông điệp nhạy cảm một lần, cần xử lý đồng thời bằng trạng thái/giao dịch nguyên tử để hai request cạnh tranh không cùng được chấp nhận.

## 12. Chống brute force và credential stuffing

**Credential stuffing** dùng cặp username/password thu thập từ các vụ lộ dữ liệu khác. **Brute force** thử nhiều giá trị để đoán bí mật. Vì submission là cửa vào công khai, chỉ dựa vào CAPTCHA hoặc khóa toàn bộ tài khoản sau vài lần sai có thể không đủ và còn gây từ chối dịch vụ cho người dùng hợp lệ.

Các kiểm soát nên phối hợp theo rủi ro:

1. **Rate limit đa chiều:** theo tài khoản, nguồn, IP/network, thiết bị/phiên, tenant và tín hiệu hành vi; không tin header IP do client tự đặt.
2. **Phát hiện bất thường:** nhiều tài khoản bị thử từ cùng nguồn, một tài khoản bị thử từ nhiều nguồn, tốc độ thất bại bất thường.
3. **Phản hồi có kiểm soát:** hạn chế user enumeration, giữ thông tin lỗi nhất quán và tránh lộ thời điểm nội bộ.
4. **MFA/passkey:** giảm tác động của password bị lộ, ưu tiên phương thức chống phishing khi mức rủi ro cao.
5. **Đánh giá mật khẩu lộ:** kiểm tra password mới với tập dữ liệu mật khẩu đã bị lộ theo phương thức bảo vệ quyền riêng tư phù hợp.
6. **Cơ chế giảm lạm dụng công bằng:** cân nhắc trì hoãn, challenge hoặc giới hạn theo rủi ro, không để kẻ tấn công dễ khóa tài khoản nạn nhân.
7. **Giám sát và phản ứng:** ghi nhật ký đã loại bỏ bí mật, phát hiện tấn công phân tán, báo động và điều chỉnh chính sách khi nhầm người dùng thật.

Đối với mã OTP ngắn, giới hạn số lần thử là thiết yếu vì không gian giá trị nhỏ. Đối với WebAuthn, challenge và chữ ký công khai có thể kiểm chứng mạnh hơn, nhưng endpoint cấp challenge, đăng ký credential hoặc recovery vẫn có thể bị spam và cần chống lạm dụng.

## 13. Cookies, CSRF, CORS và phiên đăng nhập

Credential submission thường diễn ra trước khi phiên authenticated được tạo, nhưng trình duyệt có thể đã có cookie ẩn danh hoặc phiên đăng nhập tạm. Một số bẫy phổ biến:

### 13.1. Session fixation

Nếu server giữ nguyên session ID trước và sau khi password được xác minh, kẻ tấn công có thể tìm cách buộc nạn nhân dùng một session ID do họ biết. **Cấp session ID mới** khi đăng nhập thành công hoặc khi thay đổi mức đặc quyền; quản lý phiên cũ và trạng thái challenge nhất quán.

### 13.2. Login CSRF

Trong một số luồng, kẻ tấn công có thể khiến trình duyệt nạn nhân bị đăng nhập vào **tài khoản của kẻ tấn công** mà nạn nhân không nhận ra. Dữ liệu nạn nhân sau đó bị ghi vào tài khoản sai, gây rò rỉ hoặc nhầm lẫn. Xác thực tính chủ động của luồng bằng **CSRF token, state**, kiểm tra origin và các biện pháp phù hợp; không coi login endpoint luôn an toàn chỉ vì người dùng chưa có session.

### 13.3. CSRF, SameSite và CORS

- Cookie phiên nên có **Secure**, **HttpOnly** và **SameSite** phù hợp, kèm thời hạn, domain/path hẹp theo thiết kế.
- Với thao tác thay đổi trạng thái dựa trên cookie, có thể cần **CSRF token** và kiểm tra Origin/Referer khi phù hợp. SameSite là lớp hỗ trợ, không mặc nhiên thay thế toàn bộ bảo vệ CSRF.
- **CORS** kiểm soát trang web nào có thể đọc response qua browser API trong điều kiện nhất định; nó **không phải cơ chế authentication, authorization hay chống CSRF đầy đủ**.
- Tránh cấu hình CORS cho credentialed requests quá rộng; không tin Origin hoặc Referer như định danh người dùng.

### 13.4. Response sau submission

Nếu thành công, server phát hành phiên/token theo kiến trúc. Với web, mô hình **cookie phiên phía server hoặc Backend for Frontend** thường giúp tránh để access token trực tiếp trong JavaScript. Nếu ứng dụng là native, token cần lưu ở kho an toàn của nền tảng và có TTL/refresh/thu hồi thích hợp.

Không trả mật khẩu, OTP, private key hoặc recovery code thô trong response. Không gửi access token vào URL; hạn chế lộ qua referrer, history hoặc bên thứ ba. API tiếp theo phải **kiểm tra authorization**, dù session hợp lệ.

## 14. Xử lý lỗi và tính dùng lại an toàn

Thiết kế submission cần có trạng thái rõ cho thành công, thất bại, hết hạn và yêu cầu bước tiếp theo. Một mã lỗi chung cho client không nhất thiết ngăn server lưu **reason code đã lọc bí mật** phục vụ vận hành.

| Tình huống | Hành vi an toàn |
| --- | --- |
| Password sai hoặc account không tồn tại | Phản hồi không dễ bị dùng để dò tài khoản; tăng bộ đếm lạm dụng |
| Request sai định dạng / quá lớn | Từ chối có kiểm soát; không log body chứa bí mật |
| Challenge hết hạn | Yêu cầu tạo challenge mới; không dùng lại phản hồi cũ |
| OTP sai nhiều lần | Giới hạn số lần thử; làm hết hiệu lực thử thách theo chính sách |
| WebAuthn origin/RP ID không khớp | Từ chối; ghi sự kiện đã lọc dữ liệu; không tự nới policy |
| SSO state sai hoặc code đã dùng | Từ chối callback; không tạo session |
| Service verifier tạm lỗi | Trả lỗi dịch vụ phù hợp; không mặc định cho qua xác thực |
| Account suspended | Không phát hành phiên; cung cấp luồng hỗ trợ/khôi phục theo chính sách |
| Session đã tồn tại | Xác định rõ login lại, đổi principal, nâng mức bảo đảm hoặc logout hiện tại |

**Tránh retry tự động credential quá mức**. Trình duyệt, client và gateway có thể gửi lại request khi timeout; với credential một lần, retry phải tôn trọng ngữ nghĩa của giao dịch. Bảo vệ server để một lần xác minh thành công không vô tình tạo hai phiên hoặc tiêu thụ hai lần trạng thái không nhất quán. Nếu đã tạo session nhưng response bị mất, client nên có đường kiểm tra trạng thái an toàn, không suy luận rằng gửi lại OTP cũ là hợp lệ.

## 15. Những nơi credential có thể bị rò rỉ ngoài ý muốn

Khi nhận request login, hệ thống thường có nhiều tầng ngoài authentication service:

| Vị trí | Nguy cơ thường gặp | Biện pháp |
| --- | --- | --- |
| **Browser/Frontend** | Analytics ghi input, session replay đọc password, script thứ ba | Mask input và trường nhạy cảm trong telemetry; hạn chế script/CSP |
| **Reverse proxy/WAF** | Access log hoặc debug log ghi body, header bí mật | Redaction, không log body login, kiểm soát quyền đọc log |
| **API middleware** | Log toàn bộ request khi validation thất bại | Log mã lỗi + metadata tối thiểu, không dump body |
| **APM/tracing** | Span tag, exception capture lưu password/OTP/token | Chặn/scrub trường nhạy cảm trước khi xuất dữ liệu |
| **Message queue** | Password bị đưa vào event đăng nhập để xử lý bất đồng bộ | Chỉ gửi event đã loại bí mật; verifier xử lý trong biên bảo vệ |
| **Database/cache** | Lưu plaintext hoặc challenge không có TTL, trạng thái khó thu hồi | Password verifier an toàn, TTL, mã một lần và quyền lưu trữ chặt |
| **Support/admin tools** | Nhân viên xem lại request hoặc hỏi khách hàng cung cấp OTP | Quy trình hỗ trợ không yêu cầu password/OTP; quyền audit được giới hạn |
| **Mobile crash report** | Body và token bị đính kèm stack trace | Loại bí mật khỏi crash context, kiểm soát dữ liệu thu thập |

Các trường **Authorization**, **Cookie**, **Set-Cookie**, **password**, **otp**, **recovery_code**, **assertion** hoặc nội dung có thể dùng để đăng nhập cần được xử lý đặc biệt trong log và telemetry. Phản hồi WebAuthn thường không chứa private key nhưng vẫn là bằng chứng nhạy cảm có ràng buộc giao dịch; không thu thập vô hạn chỉ vì “không có mật khẩu”.

### 15.1. Mục tiêu audit phù hợp

Một sự kiện có thể ghi thời gian, loại phương thức, tên endpoint, trạng thái thành công/thất bại, subject nội bộ khi đã xác định, tenant, phiên bản policy, nhóm nguyên nhân và correlation ID. Dữ liệu IP hoặc thiết bị cần giới hạn truy cập/lưu theo chính sách quyền riêng tư.

**Không log password hash để thay thế plaintext**: password hash cũng là dữ liệu bảo mật có thể hỗ trợ tấn công offline khi bị lộ. Audit nên ghi “password verification failed”, không ghi giá trị cần kiểm tra.

## 16. Ví dụ xuyên suốt: nền tảng học tập

Một nền tảng học tập có ba phương thức đăng nhập: mật khẩu + TOTP, passkey, SSO của trường. Người dùng có thể có cùng tài khoản nội bộ nhưng được xác thực qua các phương thức khác nhau.

### 16.1. Mật khẩu + TOTP

~~~mermaid
sequenceDiagram
    participant B as Trình duyệt
    participant A as Auth Service
    participant V as Credential Store
    participant S as Session Store
    B->>A: POST /auth/login (identifier + password)
    A->>V: Xác minh password verifier
    V-->>A: Hợp lệ
    A-->>B: Yêu cầu MFA + transaction handle
    B->>A: POST /auth/mfa (transaction + TOTP)
    A->>A: Kiểm tra TOTP, hạn, số lần thử, ràng buộc
    A->>S: Tạo session mới đủ mức bảo đảm
    A-->>B: Set-Cookie phiên an toàn
~~~

Phản hồi đầu tiên chưa tạo authenticated session có quyền đầy đủ, vì policy yêu cầu TOTP. Giao dịch MFA phải gắn đúng account, và mã dùng trong giao dịch khác phải bị từ chối theo chính sách.

### 16.2. Passkey

Học viên chọn passkey. Server phát challenge mới và publicKey options; browser gọi WebAuthn API; authenticator xác nhận sự hiện diện/xác minh người dùng theo yêu cầu, rồi trả assertion. Server kiểm tra chữ ký, origin/RP ID, challenge, credential ID và trạng thái tài khoản, sau đó tạo phiên. Nếu kẻ tấn công copy response của lần trước và gửi lại, challenge đã hết hiệu lực nên request bị từ chối.

### 16.3. SSO của trường

Giảng viên bấm “Đăng nhập với trường”. Ứng dụng chuyển hướng tới IdP trường, người dùng gửi credential ở đó. Ứng dụng nhận authorization code, kiểm tra state/PKCE và ID token, ánh xạ **issuer + sub** với internal user ID. Nếu hai trường cùng có email tương tự, **không tự gộp tài khoản theo email**.

### 16.4. Thay thiết bị và khôi phục

Học viên mất điện thoại chứa TOTP. Không nên có nút “Bỏ qua MFA” do frontend tự bật. Quy trình khôi phục riêng kiểm tra đủ bằng chứng, đánh giá rủi ro, cho đăng ký authenticator mới, thông báo thay đổi và thu hồi phiên/credential cần thiết. Bước gửi **recovery code** phải áp dụng giới hạn thử và dùng một lần, vì đây cũng là một dạng submission có thể dẫn tới thay quyền kiểm soát tài khoản.

## 17. Kiểm thử an toàn credential submission

Nhóm triển khai nên kiểm thử **thành công, thất bại, sai ngữ cảnh và hành vi bị tấn công**. Các kịch bản dưới đây có thể chạy trong môi trường thử nghiệm với tài khoản giả.

| Nhóm kiểm thử | Tình huống | Kết quả mong đợi |
| --- | --- | --- |
| **Transport** | Login qua HTTP hoặc TLS không xác minh hostname | Bị ngăn/chuyển hướng an toàn theo thiết kế; không gửi password trên kênh không bảo vệ |
| **Request** | Password ở query string, body quá lớn, content type sai | Không chấp nhận cấu trúc nguy hiểm; không log bí mật |
| **Password** | Sai password, identifier không tồn tại, input bất thường | Thất bại an toàn; không dễ dò tài khoản |
| **Rate limiting** | Thử nhiều password trên một account/nhiều account | Áp dụng kiểm soát lạm dụng, giám sát; tránh khóa hàng loạt vô lý |
| **MFA binding** | TOTP của account A nộp vào giao dịch account B | Từ chối |
| **OTP replay** | Gửi lại mã sau khi đã chấp nhận trong cửa sổ tương ứng | Từ chối theo chính sách dùng một lần/chống replay |
| **WebAuthn** | Assertion cũ, challenge sai, origin hoặc RP ID sai | Từ chối; không phát hành phiên |
| **mTLS** | Certificate không có đúng SAN/EKU, unknown CA, không có private key tương ứng | Từ chối handshake/xác thực |
| **Gateway** | Client trực tiếp gửi header X-Client-Cert giả | Không được chấp nhận là danh tính đã xác thực |
| **OIDC** | Callback state sai, PKCE không khớp, code đã dùng, issuer/audience sai | Từ chối callback, không tạo session |
| **Session** | Giữ lại session ID trước login, thay role từ client | Session ID được cấp lại; role client không ảnh hưởng quyền |
| **Telemetry** | Bật log/trace/crash report ở đường login | Không xuất hiện password, OTP, token hoặc cookie nguyên dạng |
| **Recovery** | Mã đã dùng, hết hạn, gửi sai mục đích hoặc submit đồng thời | Không được cấp lại quyền truy cập |

### 17.1. Ví dụ mô phỏng logic kiểm tra transaction

~~~text
verify_second_factor(login_transaction, submitted_code):
    tx = load_transaction_for_update(login_transaction)
    if tx is missing or tx.expired or tx.consumed:
        return generic_failure
    if tx.purpose != "LOGIN_MFA" or tx.account.status != ACTIVE:
        return generic_failure
    if tx.attempts_exceeded:
        return generic_failure

    outcome = verify_otp_for_account(tx.account.id, submitted_code)
    if not outcome.valid or outcome.already_accepted:
        increment_attempts_and_log_without_secret(tx)
        return generic_failure

    atomically_mark_otp_and_transaction_as_consumed(tx, outcome)
    return complete_login_for_account(tx.account.id, tx.assurance)
~~~

Đây là mô hình logic, không quy định một cách triển khai database cụ thể. Nó nhấn mạnh: **transaction, account, purpose, hạn, số lần thử và mã phải được gắn với nhau ở server**; chống replay cần tính nguyên tử.

## 18. Bài tập tình huống

Một đội phát triển có trang đăng nhập dùng HTTPS. Khi user nhấn “Đăng nhập”, frontend gửi **POST /login?email=...&password=...**, gateway ghi toàn bộ URL vào access log. Server gửi **mfaPassed = false** về client; frontend hiện form TOTP, sau đó client gửi **mfaPassed = true** trong request tiếp theo. Backend dựa vào cờ đó để phát hành JWT 24 giờ. Những API đọc claim **role** từ JWT nhưng không kiểm tra trạng thái quyền hiện tại. Trang login cài một plugin analytics thu thập các thao tác nhập liệu. Khi TOTP sai, response trả cụ thể “account không tồn tại” hoặc “mã TOTP sai”.

**Yêu cầu:**

1. Vẽ luồng dữ liệu và khoanh vùng **ít nhất sáu ranh giới hoặc điểm có thể rò rỉ/giả mạo**.
2. Thiết kế lại credential submission để password chỉ đi trong body của request qua TLS, không xuất hiện ở URL, log hoặc analytics.
3. Đề xuất cơ chế **server-controlled MFA transaction**: tài khoản, purpose, hạn, attempt limit, trạng thái và quy tắc hoàn thành.
4. Giải thích vì sao JWT 24 giờ có claim role không bảo đảm quyền luôn cập nhật, dù chữ ký đúng.
5. Chọn các biện pháp giảm phishing/replay nếu ứng dụng hỗ trợ thêm passkey.
6. Viết test case chứng minh việc đặt **mfaPassed = true** từ client không thể bỏ qua MFA, cùng một OTP không thể bị dùng lại ngoài chính sách.

**Gợi ý tự đối chiếu:** sử dụng TLS đúng origin; tránh credentials trong URL; mask input và telemetry; transaction MFA ở server; chỉ cấp phiên sau khi đủ assurance; JWT có audience/TTL và quy tắc cập nhật quyền; với WebAuthn, verify challenge mới, origin, RP ID, chữ ký và cờ tương ứng.

## 19. Checklist trước khi đưa submission vào production

1. **Loại credential đã rõ chưa?** Password, OTP, assertion, certificate proof hay kết quả IdP; có biết bên nào cần nhận và kiểm tra không?
2. **Endpoint đúng và được bảo vệ chưa?** TLS, hostname verification, redirect, proxy và kênh nội bộ có đúng cấu hình không?
3. **Dữ liệu gửi an toàn chưa?** Không bí mật trong URL, log, telemetry, local storage, frontend error report hoặc message queue.
4. **Server có tự quyết trạng thái không?** Không dựa vào cờ MFA, role, account ID hoặc assurance do client tự khai.
5. **Challenge được ràng buộc chưa?** Đúng account/tenant, purpose, session, origin/RP ID, TTL, số lần thử và dùng một lần khi áp dụng.
6. **Có chống phishing/replay không?** Ưu tiên phương thức phù hợp rủi ro, không suy diễn TLS ngăn mọi phishing hoặc password dùng lại.
7. **Lạm dụng đăng nhập được kiểm soát chưa?** Rate limit đa chiều, cảnh báo, chống enumeration và tránh DoS khóa tài khoản nạn nhân.
8. **MFA và recovery có đường vòng không?** Mọi bước thêm/xóa authenticator, đổi recovery channel và reset account được bảo vệ tương xứng.
9. **Phiên/token có được cấp đúng lúc không?** Sau verifier thành công và đủ mức assurance, với TTL, audience, cookie và thu hồi phù hợp.
10. **API có kiểm tra quyền không?** Authentication thành công không tự cấp mọi role; state của subject và resource luôn được xét theo policy.

## 20. Ghi nhớ

- **Credential submission là việc đưa bằng chứng tới verifier; không phải quyết định “đã đăng nhập thành công”.**
- Với **password/OTP**, client gửi một bí mật có thể bị lộ hoặc dùng lại; bảo vệ đường truyền, nơi lưu tạm, log và các thành phần trung gian.
- Với **WebAuthn/passkey**, client gửi assertion có chữ ký trên challenge, gắn với RP ID/origin; **không gửi private key**.
- Với **mTLS**, proof of possession diễn ra ở TLS handshake; thông tin certificate chuyển tiếp từ gateway chỉ được tin khi ranh giới proxy được bảo vệ.
- Với **OIDC**, credential của người dùng được gửi tới IdP; RP phải bảo vệ callback và xác minh code/token theo giao thức.
- **Phishing, replay, credential stuffing và lỗi gắn sai ngữ cảnh** cần được giải quyết ở đúng lớp; TLS không thể thay thế MFA mạnh, challenge binding, kiểm soát lạm dụng và authorization.

Một thiết kế authentication flow vững chắc biết chính xác **bằng chứng nào được gửi, gửi cho ai, qua ranh giới nào, được kiểm tra theo ngữ cảnh nào và khi nào mới được phép cấp phiên**. Khi các điều kiện ấy được thực thi ở thành phần tin cậy, bước credential submission sẽ không trở thành cửa ngõ làm lộ credential hoặc bỏ qua các biện pháp xác thực còn lại.
