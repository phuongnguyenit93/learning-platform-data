# Identity token và thông tin đăng nhập

Khi người dùng bấm **“Đăng nhập bằng tài khoản công ty”**, ứng dụng có thể nhận được một **ID token** chứa `sub`, `iss`, `aud` và các thông tin liên quan tới lần xác thực. Điều đó **không có nghĩa ứng dụng đã nhận mật khẩu của người dùng**, cũng không có nghĩa ID token có thể dùng để gọi mọi API. Để thiết kế đúng hệ thống xác thực và phân quyền, cần tách bạch:

1. **Thông tin đăng nhập (login credentials):** bằng chứng người dùng trình cho hệ thống định danh, chẳng hạn mật khẩu, passkey hoặc phản hồi MFA.
2. **ID token (OpenID Connect):** kết quả xác thực người dùng được **OpenID Provider** phát hành cho **OIDC client** cụ thể, dưới dạng token có thể xác minh.
3. **Access token:** credential được cấp để client truy cập **resource server/API** trong phạm vi quyền và đối tượng nhận đã định.

Bài học này thuộc nhóm **Token types** của module bảo mật token, tập trung vào mối liên hệ giữa **ID token, danh tính người dùng, quá trình đăng nhập và vòng đời phiên** trong OAuth 2.0/OpenID Connect (OIDC). Đồng thời, bài làm rõ các yêu cầu xác minh claims, audience, lưu trữ, phòng chống token bị đánh cắp/phát lại và cách tránh dùng token sai mục đích.

## 1. “Identity token” chính xác là gì?

Trong ngữ cảnh **OpenID Connect Core 1.0**, tên chuẩn thường dùng là **ID token**. Đây là một **JWT** chứa các **claims về sự kiện xác thực người dùng** do một **OpenID Provider (OP)** phát hành và được gửi tới **Relying Party (RP)/OIDC client**. ID token giúp RP xác định:

- **Ai đã được OP xác thực?** Claim `sub` xác định chủ thể người dùng trong không gian định danh của issuer.
- **Ai phát hành bằng chứng?** Claim `iss` xác định OP/issuer.
- **Bằng chứng dành cho ứng dụng nào?** Claim `aud` phải bao gồm `client_id` của RP nhận token.
- **Đến khi nào token còn hợp lệ?** `iat` và `exp` biểu diễn thời điểm phát hành và hết hạn.
- **Xác thực diễn ra khi nào và bằng cách nào?** Các claims tùy ngữ cảnh như `auth_time`, `acr`, `amr` có thể mô tả thời điểm, lớp và phương thức xác thực.

**ID token phục vụ xác thực danh tính với client.** Nó **không phải** mật khẩu, mã OTP, refresh token, session ID và **không phải** access token mà resource server thường yêu cầu.

Một ID token thường được ký dưới dạng **JWS**; một số cấu hình OIDC còn dùng **JWE** để mã hóa. **JWT ký không mặc định được mã hóa**: các claims trong payload thường đọc được bằng cách giải mã Base64url. Vì vậy, không đưa mật khẩu, OTP, khóa bí mật hoặc dữ liệu nhạy cảm không cần thiết vào ID token.

### 1.1. Ai tin ai?

| Thành phần | Vai trò | Điều có thể tin sau khi đã kiểm tra đúng |
| --- | --- | --- |
| **End user** | Người thực hiện đăng nhập | Kết quả xác thực tại OP, theo phương thức và chính sách OP áp dụng |
| **OpenID Provider (OP)** | Xác thực người dùng, phát hành ID token | Ký/phát hành token và cung cấp metadata/khóa công khai cho client |
| **OIDC client (RP)** | Ứng dụng muốn đăng nhập người dùng | Chỉ tin ID token sau validation đầy đủ và ràng buộc với phiên đăng nhập đã khởi tạo |
| **Resource server/API** | Bảo vệ tài nguyên | Tin **access token** đúng issuer/audience/quyền; không dùng ID token làm vé vào API |

Ngay cả khi OP và API thuộc cùng một công ty, **bên nhận token vẫn quan trọng**. ID token dành cho RP `portal-web` không tự động hợp lệ khi được gửi tới `payments-api`.

## 2. Thông tin đăng nhập là gì và nằm ở đâu?

“Thông tin đăng nhập” trong thực tế có thể chỉ **credential dùng để chứng minh danh tính** hoặc **dữ liệu hồ sơ của người đã đăng nhập**. Hai nghĩa này cần được phân biệt:

| Khái niệm | Ví dụ | Chức năng | Có nên đưa vào ID token? |
| --- | --- | --- | --- |
| **Login credential** | Mật khẩu, mã OTP, khóa riêng dùng cho passkey | Giúp OP xác thực người dùng | **Không** đưa giá trị bí mật vào token |
| **Authentication event** | User đã xác thực lúc 10:00 bằng phương thức được chấp nhận | Mô tả một lần xác thực thành công | Có thể biểu diễn qua `auth_time`, `acr`, `amr` |
| **Identity claims** | `sub`, `name`, `preferred_username`, `email`, `email_verified` | Định danh và hiển thị thông tin user | Có thể có theo scope, chính sách phát hành và consent |
| **Application session** | Session ID trong cookie trỏ tới server-side session | Duy trì trạng thái đăng nhập vào ứng dụng | Là cơ chế riêng; không đồng nhất với ID token |
| **Authorization claims** | Scope, role/permission, tenant | Hỗ trợ quyết định quyền khi có nguồn và ngữ nghĩa đáng tin | Không được coi mặc nhiên là quyền API chỉ vì có trong ID token |

Ví dụ người dùng dùng **passkey/WebAuthn**: trình duyệt/thiết bị tạo chữ ký lên một challenge theo quy trình xác thực; **khóa riêng không cần rời thiết bị**. OP xác minh phản hồi và có thể phát ID token cho client. ID token **không phải bản sao** của passkey hoặc bằng chứng WebAuthn thô.

Với đăng nhập bằng mật khẩu + OTP, OP kiểm tra chúng theo giao thức/chính sách riêng. OIDC client thường chỉ thấy **kết quả của sự kiện xác thực**, không cần biết hoặc lưu mật khẩu/OTP của người dùng.

### 2.1. Client ID và client secret không phải thông tin đăng nhập của user

OAuth client có thể chứng minh danh tính **ứng dụng** với OP/authorization server bằng `client_secret`, `private_key_jwt` hoặc mTLS khi đổi authorization code. Đó là **client authentication**. Nó khác **user authentication**, nơi OP kiểm tra mật khẩu, passkey hoặc MFA của người dùng.

Một ứng dụng public như SPA/mobile có thể dùng **Authorization Code + PKCE** mà không có client secret; thiếu secret **không ngăn người dùng đăng nhập qua OIDC**. `client_id` là định danh công khai của ứng dụng, không phải mật khẩu người dùng và không tự chứng minh client đã được xác thực.

## 3. ID token khác access token, refresh token và session như thế nào?

| Loại | Mục đích | Bên tiếp nhận dự kiến | Nội dung/định dạng | Cách sử dụng đúng |
| --- | --- | --- | --- | --- |
| **ID token** | Chuyển thông tin về **user authentication** cho RP | **OIDC client** có `client_id` nằm trong `aud` | JWT với claims OIDC | Validate ID token để thiết lập/đánh giá đăng nhập tại client |
| **Access token** | Cho phép client gọi tài nguyên được cấp quyền | **Resource server/API** đúng `aud` | JWT hoặc opaque | Gửi theo giao thức, thường `Authorization: Bearer ...`; API kiểm tra quyền |
| **Refresh token** | Xin access token mới trong khuôn khổ grant | **Authorization server/token endpoint** | Thường opaque; không bắt buộc | Bảo vệ cẩn thận, xoay vòng/thu hồi theo chính sách |
| **Session ID** | Tra phiên đăng nhập ứng dụng hoặc OP | Server sở hữu session | Thường chuỗi opaque ngẫu nhiên | Trình duyệt có thể gửi qua cookie `Secure; HttpOnly` |
| **Login credential** | Chứng minh danh tính user trước OP | Hệ thống đăng nhập/IdP | Mật khẩu, passkey assertion, OTP... | Chỉ dùng trong quá trình xác thực phù hợp; không đưa vào API như access token |

Sơ đồ vai trò:

~~~mermaid
flowchart LR
    U["Người dùng"] -->|"Mật khẩu / passkey / MFA"| OP["OpenID Provider"]
    OP -->|"ID token: aud = client_id"| C["OIDC client / RP"]
    OP -->|"Access token: aud = API"| C
    C -->|"Authorization: Bearer access_token"| API["Resource server / API"]
    C -->|"Session cookie của ứng dụng (nếu có)"| B["Trình duyệt"]
    B -->|"Cookie phiên"| C
    OP -->|"Refresh token (nếu cấp)"| C
~~~

Trong một triển khai backend-for-frontend (BFF), token OAuth có thể được giữ trên backend và trình duyệt chỉ giữ session cookie. Trong SPA/native app, client tự thực hiện trao đổi token theo luồng dành cho public client; cách lưu token cần cân nhắc môi trường và rủi ro.

**Không nên dùng access token để suy ra đăng nhập OIDC chỉ vì token có `sub`**, trừ khi đang tuân một giao thức/profile xác thực được thiết kế rõ. Tương tự, **không gửi ID token làm Bearer tới API**: dù chữ ký đúng, ID token thường có audience là **OIDC client**, không phải API, và không biểu diễn đúng phạm vi cấp quyền API.

## 4. ID token được phát hành khi nào? Luồng Authorization Code + PKCE

Ví dụ một ứng dụng `portal-web` muốn cho người dùng đăng nhập qua `https://login.example.com`:

~~~mermaid
sequenceDiagram
    autonumber
    actor U as Người dùng
    participant B as Trình duyệt
    participant C as portal-web (OIDC client)
    participant OP as OpenID Provider / AS
    participant API as Resource API
    U->>B: Chọn Đăng nhập
    B->>C: GET /login
    C-->>B: Redirect /authorize (openid, state, nonce, PKCE)
    B->>OP: Authorization request
    OP->>U: Yêu cầu chứng minh danh tính theo chính sách
    U-->>OP: Hoàn tất mật khẩu / passkey / MFA
    OP-->>B: Redirect về callback với authorization code + state
    B->>C: Gửi callback code và state
    C->>C: Kiểm tra state, lấy code_verifier của giao dịch
    C->>OP: POST /token với code, code_verifier; client auth nếu cần
    OP-->>C: ID token + access token (có thể refresh token)
    C->>C: Validate ID token và liên kết user vào tài khoản ứng dụng
    C-->>B: Thiết lập session cookie ứng dụng nếu dùng backend
    C->>API: Access token đúng audience và scope
    API-->>C: Dữ liệu theo chính sách quyền
~~~

### 4.1. Yêu cầu `scope=openid` để đây là OIDC

Yêu cầu ủy quyền ví dụ (hiển thị nhiều dòng cho dễ đọc; trong HTTP thực tế là một URL):

~~~text
GET https://login.example.com/authorize
  ?response_type=code
  &client_id=portal-web
  &redirect_uri=https%3A%2F%2Fportal.example.com%2Fcallback
  &scope=openid%20profile%20email
  &state=<random-state>
  &nonce=<random-nonce>
  &code_challenge=<S256-challenge>
  &code_challenge_method=S256
~~~

- `scope=openid` làm cho yêu cầu tuân **OpenID Connect**; một OAuth 2.0 request chỉ có scope API thông thường **không mặc nhiên trả ID token**.
- `state` giúp client khớp authorization response với yêu cầu đã tạo; phải được tạo khó đoán, lưu/ràng buộc phù hợp và kiểm tra khi callback.
- `nonce` liên kết ID token nhận được với yêu cầu xác thực trước đó. Với Authorization Code Flow, có thể dùng `nonce`; **nếu đã gửi, phải so khớp với claim `nonce` trong ID token**. Trong các flow khác, yêu cầu về `nonce` có thể bắt buộc theo OIDC.
- `code_challenge`/ `code_verifier` của PKCE giúp chống đánh cắp authorization code; chúng **không thay** kiểm tra ID token hay chứng minh phương thức xác thực user.
- `redirect_uri` phải đúng đăng ký và ràng buộc với code; không nhận callback từ địa chỉ tùy ý.

### 4.2. Token được đổi qua kênh server-to-server khi có backend

Ví dụ token request rút gọn:

~~~http
POST /token HTTP/1.1
Host: login.example.com
Content-Type: application/x-www-form-urlencoded
Authorization: Basic <confidential-client-credentials>

grant_type=authorization_code&code=<one-time-code>&redirect_uri=https%3A%2F%2Fportal.example.com%2Fcallback&code_verifier=<original-verifier>
~~~

Trong cấu hình confidential client, `Authorization: Basic` chứa client credential **của ứng dụng**, không phải mật khẩu user. Public client thường không gửi client secret và vẫn phải được AS kiểm tra code, PKCE, redirect URI và các điều kiện grant.

Ví dụ phản hồi **minh họa**, mọi token đều là placeholder:

~~~json
{
  "access_token": "<access-token-for-api>",
  "token_type": "Bearer",
  "expires_in": 900,
  "id_token": "<signed-oidc-id-token>",
  "scope": "openid profile email"
}
~~~

Trong thực tế OP có thể cung cấp thêm `refresh_token` khi luồng, client type và chính sách cho phép. Không mặc định mọi lần đăng nhập OIDC luôn có refresh token hoặc luôn có đủ tất cả claims hồ sơ trong ID token.

## 5. Đọc đúng nội dung một ID token

Giả sử sau khi giải mã **payload để quan sát** (chưa đủ để xác minh), ta thấy:

~~~json
{
  "iss": "https://login.example.com",
  "sub": "user-4f7a1",
  "aud": "portal-web",
  "exp": 1795411200,
  "iat": 1795410600,
  "auth_time": 1795410300,
  "nonce": "<random-nonce>",
  "acr": "urn:example:acr:passkey",
  "amr": ["webauthn"],
  "name": "Linh Nguyen",
  "email": "linh@example.com",
  "email_verified": true
}
~~~

Đây **không phải JWT hợp lệ có chữ ký**; nó chỉ là JSON để thảo luận về claims. Các mốc Unix time là số minh họa; chỉ có ý nghĩa khi được kiểm tra với thời gian thực và khóa ký hợp lệ.

| Claim | Thuộc tính | Phải hiểu chính xác |
| --- | --- | --- |
| `iss` | Bắt buộc | Issuer của ID token. So đúng với OP đã cấu hình, **không tin URL do request tự khai**. |
| `sub` | Bắt buộc | Định danh chủ thể người dùng trong ngữ cảnh issuer; dùng cùng `iss` làm khóa liên kết tài khoản. |
| `aud` | Bắt buộc | Audience gồm `client_id` của RP; có thể là một chuỗi hoặc mảng. |
| `exp` | Bắt buộc | Token không còn chấp nhận được sau thời điểm này, trừ dung sai thời gian rất nhỏ theo chính sách. |
| `iat` | Bắt buộc | Thời điểm phát hành ID token; **không phải thời điểm user nhập lại yếu tố xác thực**. |
| `auth_time` | Theo trường hợp | Thời điểm OP xác thực chủ động user; cần kiểm tra khi dùng `max_age` hoặc yêu cầu xác thực mới. |
| `nonce` | Theo flow/yêu cầu | So khớp nonce đã gửi trong authorization request nếu có; giúp liên kết token với giao dịch. |
| `acr` | Tùy chọn/chính sách | Lớp ngữ cảnh xác thực, giá trị do hệ thống định nghĩa; không có thứ tự mạnh/yếu chung cho mọi issuer. |
| `amr` | Tùy chọn/chính sách | Các phương thức xác thực được dùng; ví dụ OTP, passkey... theo ngữ nghĩa của OP. |
| `azp` | Theo trường hợp | Authorized party; cần kiểm tra khi áp dụng quy tắc OIDC cho multiple audiences. |
| `name`, `email` | Tùy chọn | Thông tin hồ sơ; có thể đổi hoặc vắng mặt, không nên dùng làm ID ổn định. |
| `email_verified` | Tùy chọn | OP khẳng định đã xác minh email theo quy trình của mình; không bảo đảm email bất biến hoặc user có mọi quyền. |

### 5.1. `sub` quan trọng hơn email để liên kết tài khoản

Giả sử một ứng dụng lưu user dưới khóa `email = linh@example.com`. Sau đó email này được đổi chủ sở hữu, hoặc một IdP khác phát hiện cùng địa chỉ. Nếu ứng dụng liên kết tự động chỉ dựa vào email, có thể **gán nhầm quyền truy cập tài khoản**.

Khóa đăng nhập liên kết nên dựa trên **cặp `(iss, sub)` đã xác minh**, ví dụ:

~~~text
issuer  = https://login.example.com
subject = user-4f7a1
localAccountId = 6842
~~~

`sub` được định nghĩa là duy nhất và không gán lại **trong phạm vi issuer**. Nó có thể là **pairwise subject identifier**, tức cùng một user có giá trị `sub` khác nhau ở các client/sector khác nhau nhằm bảo vệ riêng tư. Không so sánh `sub` của hai issuer khác nhau như thể chúng dùng chung một không gian định danh.

Nếu cần liên kết nhiều tài khoản/IdP, phải có **quy trình account linking riêng** với kiểm tra quyền sở hữu phù hợp. `email_verified=true` có thể là một tín hiệu nhưng **không tự đủ** để hợp nhất tài khoản có dữ liệu nhạy cảm.

### 5.2. `acr`, `amr` và `auth_time` không đồng nghĩa với quyền truy cập

Một ID token ghi `amr=["pwd","otp"]` có thể cho biết phương thức đã được dùng, nhưng mức bảo đảm phụ thuộc vào triển khai và chính sách OP. Một `acr` cụ thể có ý nghĩa khi RP và OP đã thống nhất ngữ cảnh đó đòi hỏi gì.

Nếu một giao dịch nhạy cảm yêu cầu **step-up authentication**, ứng dụng có thể yêu cầu `max_age` hoặc `acr_values` trong authorization request. Sau đó cần kiểm tra kết quả thật của `auth_time`/`acr`; **không suy ra “vừa MFA” chỉ từ `iat` hoặc `exp` của token**.

Các claims `scope`/`roles` nếu xuất hiện trong ID token theo mở rộng của nhà cung cấp **không tự động trở thành chính sách truy cập API**. API cần access token đúng audience và kiểm tra scope, tenant, ownership, resource policy.

## 6. Quy trình validation ID token an toàn

**Giải mã JWT chỉ là đọc dữ liệu; validation mới tạo ra bằng chứng đáng tin.** Một ứng dụng không được lấy `sub`, `email` hoặc `role` từ payload chưa được kiểm tra rồi tạo session cho người dùng.

### 6.1. Checklist kỹ thuật cho OIDC client

1. **Cố định issuer tin cậy** cho luồng đăng nhập đã khởi tạo. Lấy metadata từ discovery endpoint của OP được cấu hình, dùng HTTPS và kiểm soát cấu hình chống issuer mix-up.
2. **Lấy khóa xác minh đáng tin cậy** từ JWKS của issuer theo metadata đã kiểm soát; không tải khóa từ một URL bất kỳ do token/header chưa được tin cậy chỉ định.
3. **Kiểm tra chữ ký/mã hóa và thuật toán** đúng với cấu hình client/OP. Không chấp nhận `alg=none` hoặc đổi thuật toán tùy ý chỉ vì header JWT nói như vậy; chọn khóa phù hợp `kid` từ JWKS của issuer.
4. **So khớp `iss`** chính xác với issuer dự kiến.
5. **So khớp `aud`** có chứa `client_id` của RP. Nếu token có nhiều audience, áp dụng quy tắc kiểm tra `azp` theo OIDC; nếu `azp` hiện diện, xác minh nó đúng client theo yêu cầu profile.
6. **Kiểm tra thời gian**: `exp` chưa qua, `iat` hợp lý; xét `auth_time` khi chính sách yêu cầu. Cho phép clock skew nhỏ, có giới hạn rõ ràng.
7. **Kiểm tra `nonce`** với giá trị gắn vào phiên yêu cầu ủy quyền nếu nonce đã được gửi; dùng so sánh và quản lý một lần theo chính sách.
8. **Kiểm tra các ràng buộc theo flow**: ví dụ hash liên kết `at_hash`/`c_hash` khi được yêu cầu bởi OIDC flow/profile. Không tự dùng quy tắc của một flow cho tất cả flow.
9. **Liên kết user bằng `(iss, sub)` đã xác minh**, rồi áp dụng chính sách đăng nhập, trạng thái tài khoản, tenant và yêu cầu reauthentication nếu cần.
10. **Tạo session ứng dụng phù hợp** nếu kiến trúc dùng session; cấu hình cookie và vòng đời độc lập với hạn ID token.

Với ID token là JWE, client phải giải mã bằng khóa phù hợp và vẫn đáp ứng các yêu cầu kiểm tra tính xác thực/claims theo cấu hình. Dùng thư viện OIDC đã được kiểm thử sẽ giúp xử lý đúng nhiều trường hợp phức tạp như rotation khóa, validation thuật toán và các biến thể flow.

### 6.2. Pseudocode minh họa cho backend

Đoạn sau biểu diễn **thứ tự kiểm tra**, không phải mã xử lý JWT thô. Hàm `oidcLibrary.validateIdToken` tượng trưng cho một thư viện OIDC đáng tin cậy đã được cấu hình issuer, client ID và khóa xác minh:

~~~java
// Pseudocode: thư viện phải validate chữ ký, iss, aud, exp,
// alg/kid, nonce và các yêu cầu theo OIDC flow trước khi trả kết quả.
VerifiedIdToken verified = oidcLibrary.validateIdToken(
    tokenResponse.idToken(),
    trustedIssuerConfig,
    clientId,
    loginAttempt.expectedNonce()
);

// Chỉ sử dụng thông tin đã xác minh.
String externalAccountKey =
    verified.issuer() + "|" + verified.subject();

// Chính sách ứng dụng phải tự quyết định tài khoản còn hoạt động,
// user có được đăng nhập hay cần step-up hay không.
LocalUser user = accountRepository.findByExternalIdentity(
    verified.issuer(), verified.subject()
);
if (user == null || !user.isEnabled()) {
    throw new LoginDeniedException();
}

applicationSession.createFor(user.id());
~~~

**Không** triển khai bằng cách:

~~~java
// SAI: parse phần payload rồi tin email/sub để đăng nhập.
String email = decodeJwtPayload(idToken).get("email");
loginAs(email);
~~~

Kẻ tấn công có thể tạo payload JSON với email của người khác nếu ứng dụng bỏ qua chữ ký, issuer, audience, nonce hoặc thời hạn token.

## 7. Có thể lấy thêm dữ liệu từ UserInfo endpoint

ID token phải có các claims tối thiểu bắt buộc; nó không nhất thiết chứa đầy đủ `name`, `picture`, `address`, `phone_number` hoặc `email`. OpenID Connect cung cấp **UserInfo endpoint** để client lấy các claims người dùng được phép truy cập.

~~~http
GET /userinfo HTTP/1.1
Host: login.example.com
Authorization: Bearer <access-token-authorized-for-userinfo>
~~~

Ví dụ dữ liệu trả về:

~~~json
{
  "sub": "user-4f7a1",
  "name": "Linh Nguyen",
  "email": "linh@example.com",
  "email_verified": true
}
~~~

Khi dùng UserInfo, client **phải kiểm tra `sub` trong phản hồi khớp chính xác với `sub` của ID token đã xác minh**. Nếu không, client có thể gắn hồ sơ người này vào phiên người khác. UserInfo có thể có cơ chế ký/mã hóa theo cấu hình; nếu không, bảo vệ TLS và kênh truy xuất là rất quan trọng.

Các scope OIDC như `profile`, `email`, `phone`, `address` mô tả nhóm claims được yêu cầu. Client vẫn phải tôn trọng consent, chính sách OP và khả năng claim không có mặt; **request một scope không bảo đảm mọi claim luôn được trả**.

Không nên coi dữ liệu profile đồng nghĩa với quyền:

- `email_verified=true` nói về trạng thái email theo OP, không chứng minh user là quản trị viên.
- `name` và `preferred_username` có thể thay đổi; không dùng làm khóa chính bảo mật.
- `picture` hoặc URL hồ sơ là dữ liệu ngoài; khi hiển thị cần bảo vệ chống nội dung không tin cậy.
- Một `role` từ custom claim chỉ có ý nghĩa khi hệ thống đã xác định nguồn, đối tượng nhận và quy tắc phân quyền cụ thể.

## 8. Sau khi xác minh ID token, phiên đăng nhập hoạt động thế nào?

ID token thường được dùng **ở ranh giới tạo phiên/nhận định danh**, nhưng các request về sau không nhất thiết phải gửi ID token. Có hai mô hình phổ biến:

### 8.1. Website có backend và session cookie

Sau khi backend xác minh ID token, ứng dụng có thể tạo một session server-side và gửi cookie:

~~~http
HTTP/1.1 302 Found
Location: /dashboard
Set-Cookie: __Host-app-session=<random-session-id>; Path=/; Secure; HttpOnly; SameSite=Lax
Cache-Control: no-store
~~~

Request tiếp theo của trình duyệt gửi session cookie theo chính sách. Backend **tra session và kiểm tra quyền** đối với từng thao tác. ID token không cần được gửi trong mọi request; server cũng không nên nhầm thời hạn cookie, hạn ID token và hạn session.

Trong ví dụ, tiền tố `__Host-` yêu cầu `Secure`, `Path=/` và không có `Domain`; `HttpOnly` ngăn JavaScript đọc trực tiếp cookie nhưng **không ngăn toàn bộ XSS**. Cookie tự gửi vẫn có thể tạo rủi ro **CSRF**; cần `SameSite`, CSRF token hoặc kiểm soát Origin phù hợp.

### 8.2. SPA hoặc native app

Client có thể nhận và xử lý ID token để xây dựng trạng thái người dùng, nhưng không nên coi JWT như một kho dữ liệu profile công khai hoặc chìa khóa truy cập API. Với SPA, token trong `localStorage` có thể bị JavaScript độc hại do XSS đọc; giữ token trong memory giúp giảm tồn tại nhưng không miễn nhiễm với XSS đang chạy.

Ứng dụng mobile nên dùng nền tảng lưu trữ an toàn phù hợp (ví dụ kho khóa/credential của hệ điều hành), giao thức đăng nhập qua trình duyệt hệ thống và Authorization Code + PKCE. Với web app cần giảm việc phơi lộ OAuth token trong JavaScript, **BFF** quản lý token ở backend là một lựa chọn đáng cân nhắc.

## 9. Vòng đời: login, refresh, step-up, logout và thu hồi

Một sai lầm phổ biến là coi `exp` của ID token là “hạn phiên đăng nhập”. Thực tế có **nhiều đồng hồ khác nhau**:

| Đồng hồ/trạng thái | Biểu diễn | Kết quả khi hết hạn hoặc bị thu hồi |
| --- | --- | --- |
| **ID token** | `exp` | Không dùng token đó để xác minh đăng nhập mới sau khi hết hạn; không tự động xóa session ứng dụng đã thiết lập |
| **Authentication event** | `auth_time`, `acr` | Có thể quá cũ/không đủ mạnh cho step-up, dù session và access token còn hiệu lực |
| **Access token** | `exp` hoặc trạng thái introspection | API từ chối token hết hạn/vô hiệu; không quyết định toàn bộ phiên RP |
| **Refresh token / grant** | Chính sách của AS | Không thể xin token mới nếu refresh token bị thu hồi; access token cũ có thể còn hiệu lực |
| **Ứng dụng session** | Server-side expiry, session revocation, cookie | Request vào ứng dụng không còn được nhận khi session server vô hiệu |
| **Phiên SSO ở OP** | Cookie/session của OP | Ảnh hưởng lần authorization tiếp theo; không đồng nghĩa mọi session của RP tự logout |

### 9.1. Refresh token không tạo ra sự kiện user authentication mới

Khi client dùng refresh token xin access token mới, AS có thể không yêu cầu người dùng tương tác. Vì thế, **`iat` của token mới không được dùng thay `auth_time`** để kết luận user vừa xác thực lại. Nếu thao tác đòi “xác thực trong 5 phút”, client cần thực hiện luồng reauthentication/step-up phù hợp và kiểm tra bằng chứng mới.

### 9.2. Logout ứng dụng và logout SSO

**Local logout** thường vô hiệu hóa session của ứng dụng và xóa cookie tương ứng. **Logout tại OP** có thể là một quy trình riêng; với nhiều RP, đăng xuất khỏi một ứng dụng không mặc nhiên đăng xuất khỏi tất cả.

Các cơ chế OIDC logout như RP-Initiated Logout/Front-Channel/Back-Channel có những yêu cầu riêng. Trong một số luồng `id_token_hint` được dùng để gợi ý phiên đăng nhập cho OP khi logout, **không biến ID token thành access token hoặc refresh token**. Token còn hiệu lực và các session khác phải được xử lý theo chính sách revocation/logout thực tế.

### 9.3. Nếu ID token bị đánh cắp?

ID token có thể chứa thông tin nhận diện riêng tư và, trong triển khai sai, bị dùng để **replay** nhằm tạo phiên trái phép. Cần:

1. Chỉ trao đổi token qua HTTPS và endpoint đáng tin; không để ID token trong URL/log/analytics hoặc thông báo lỗi.
2. Bảo vệ callback bằng `state`, PKCE và `nonce` theo flow; không cho token của một login attempt bị sử dụng ở login attempt khác.
3. Kiểm tra issuer, audience, signature, thời gian và các claims trước khi tạo session; ràng buộc với giao dịch ủy quyền hợp lệ.
4. Áp dụng giới hạn lưu trữ, vòng đời session và giám sát; cân nhắc thu hồi session nếu phát hiện tài khoản/credential bị xâm phạm.
5. Giảm tối đa claims nhận diện trong token; mã hóa nếu có nhu cầu bảo mật nội dung và profile/OP hỗ trợ.

**JWS signature ngăn sửa đổi token mà không có khóa ký**, nhưng không làm token bí mật hoặc ngăn ai đó gửi lại một bản sao còn hiệu lực. Các ràng buộc client, nonce và quản lý phiên giúp giảm rủi ro sử dụng sai bối cảnh.

## 10. Các lỗi bảo mật thường gặp

### 10.1. Chấp nhận ID token của ứng dụng khác

Giả sử ID token có `aud=mobile-app` nhưng web portal có `client_id=portal-web`. Nếu portal chỉ kiểm tra chữ ký mà bỏ qua audience, nó có thể chấp nhận token **không dành cho mình**.

**Cách đúng:** kiểm tra `aud` chứa client ID mong đợi, đồng thời xử lý `azp` khi áp dụng. Token chữ ký đúng nhưng sai `aud` phải bị từ chối.

### 10.2. Dùng ID token gọi API

~~~http
GET /api/orders HTTP/1.1
Host: api.example.com
Authorization: Bearer <id-token-aud-portal-web>
~~~

**Sai:** ID token được tạo để RP xác minh sự kiện đăng nhập. API phải yêu cầu **access token** đúng audience, kiểm tra issuer, chữ ký/introspection, scope/quyền và ownership. Chấp nhận ID token ở API tạo nguy cơ **token substitution**.

### 10.3. Chỉ decode payload và tin `email` hoặc `role`

**Sai:** nội dung Base64url của JWT có thể đọc và giả mạo tùy ý nếu bỏ qua chữ ký. Ngay cả ID token đã xác minh cũng không làm `email` trở thành khóa định danh vĩnh viễn, hay biến custom `role` thành quyền trên mọi API.

**Cách đúng:** validation OIDC đầy đủ, account key `(iss, sub)`, kiểm tra role/permission tại hệ thống sở hữu tài nguyên.

### 10.4. Không đối chiếu `nonce` hoặc `state`

**Sai:** một ID token thuộc login attempt khác có thể bị gắn vào phiên đang đăng nhập nếu client không ràng buộc response và token với request đã tạo. Không kiểm tra `state` còn có thể tạo nguy cơ login CSRF.

**Cách đúng:** tạo giá trị khó đoán, lưu chúng an toàn theo giao dịch, kiểm tra callback và `nonce` trong ID token khi được gửi; huỷ giao dịch đã sử dụng hoặc hết hạn.

### 10.5. Nhận khóa ký từ header token không tin cậy

**Sai:** tự động tải khóa từ URL trong header JWT do attacker cung cấp có thể khiến ứng dụng xác minh chữ ký bằng khóa của kẻ tấn công. Chỉ so `kid` mà không khóa issuer/JWKS cũng không an toàn.

**Cách đúng:** lấy JWKS từ **issuer đã cấu hình**, ràng buộc thuật toán/kiểu khóa, xử lý `kid` và rotation theo thư viện đã kiểm thử.

### 10.6. Tự liên kết tài khoản bằng email

**Sai:** hai OP khác nhau cùng trả `email=linh@example.com`; ứng dụng tự gộp tài khoản cũ chỉ dựa vào email. Điều này có thể tạo lỗi chiếm quyền tài khoản nếu email không còn thuộc đúng người hoặc quy trình xác minh khác nhau.

**Cách đúng:** `(iss, sub)` là external identity key; việc liên kết thêm tài khoản cần hành động/kiểm tra độc lập và audit trail.

### 10.7. Xem token còn hạn là user đã xác thực gần đây

**Sai:** ID token `exp` còn hiệu lực nhưng `auth_time` cách đây nhiều giờ; thao tác thay đổi mật khẩu lại yêu cầu reauthentication trong vòng 5 phút.

**Cách đúng:** yêu cầu `max_age` hoặc ACR phù hợp, kiểm tra `auth_time`/`acr` trong kết quả xác thực và các bằng chứng mà API cần theo profile.

## 11. Tình huống thực tế để tự kiểm tra

**Tình huống A — Đăng nhập liên kết.** Ứng dụng nhận ID token hợp lệ từ issuer `https://login.example.com`, có `sub=user-4f7a1`, `email=linh@example.com`. Trong database đã có một tài khoản đăng nhập bằng local password dùng cùng email. Có nên tự động gộp?

**Phân tích:** Không mặc nhiên. Client có thể xác định external identity bằng `(iss, sub)`; liên kết với tài khoản local phải có quy trình xác nhận quyền sở hữu. Email là một thuộc tính hồ sơ, không phải khóa liên kết bảo mật toàn cục.

**Tình huống B — API nhận ID token.** Một ID token có chữ ký hợp lệ, `aud=portal-web`, `sub=user-4f7a1`. Client gửi token tới API `orders-api`, API xác minh chữ ký và trả dữ liệu.

**Phân tích:** API đã bỏ qua audience và mục đích token. Cần từ chối ID token và yêu cầu access token cho `orders-api`, rồi kiểm tra scope và quyền trên tài nguyên.

**Tình huống C — Đọc token trước khi xác minh.** Frontend lấy `role=admin` từ JWT do user gửi qua query string, sau đó hiển thị màn hình quản trị và backend cũng nhận `role=admin` do client tự truyền.

**Phân tích:** UI chưa đáng tin; backend càng không được dựa vào claims chưa được xác minh hoặc role do client tự khai. Phải kiểm tra authentication và authorization ở server theo nguồn tin cậy.

**Tình huống D — Refresh và step-up.** User đăng nhập bằng passkey lúc 08:00. Đến 16:00, client dùng refresh token lấy access token mới với `iat=16:00`; API yêu cầu reauthentication trong 5 phút.

**Phân tích:** Refresh không chứng minh user vừa xác thực. Cần luồng tương tác mới tại OP và bằng chứng `auth_time` đáp ứng chính sách.

**Tình huống E — UserInfo không khớp.** ID token đã xác minh có `sub=user-4f7a1`, nhưng UserInfo trả `sub=user-99999`, cùng email hiển thị.

**Phân tích:** Không chấp nhận UserInfo để cập nhật phiên/tài khoản. Phản hồi `sub` phải khớp chính xác với ID token; email giống nhau không đủ.

**Tình huống F — Logout.** User bấm logout, backend xóa session ứng dụng. Một ID token cũ vẫn còn nằm trong thiết bị và `exp` chưa qua.

**Phân tích:** ID token còn hợp lệ về mặt thời gian không có nghĩa session vừa bị hủy được khôi phục. Client phải quản lý vòng đời session, login attempt và việc xử lý token cũ; không nên cho ID token lạc ngữ cảnh tạo lại session.

## 12. Checklist triển khai

1. **Phân biệt đúng loại:** login credential để OP xác thực user, ID token cho RP, access token cho API, refresh token cho AS.
2. **Dùng OIDC khi cần login liên kết:** có `scope=openid` và luồng phù hợp; ưu tiên Authorization Code + PKCE; confidential client xác thực với AS theo cấu hình.
3. **Ràng buộc giao dịch:** kiểm tra `state`, PKCE, redirect URI và `nonce` khi dùng; không nhận token thuộc phiên khác.
4. **Validation đầy đủ:** issuer tin cậy, signature/algorithm/JWKS, `aud`, `azp` khi áp dụng, `exp`, `iat`, nonce và flow-specific claims.
5. **Tài khoản local dùng `(iss, sub)`:** không tự gộp theo email hoặc tên hiển thị; kiểm tra trạng thái tài khoản.
6. **Không tự coi profile là quyền:** `email_verified`, `name`, `acr` và custom role phải được diễn giải theo nguồn và policy phù hợp.
7. **Tách phiên và token:** hạn session/cookie, hạn ID token, hạn access token và refresh grant được thiết kế độc lập nhưng nhất quán.
8. **Bảo vệ credential:** TLS, tránh log/URL, lưu trữ phù hợp, giảm claims nhạy cảm, xử lý XSS/CSRF và vòng đời thu hồi.
9. **Step-up khi cần:** so `auth_time`/`acr` theo chính sách; refresh token hoặc `iat` mới không thay user reauthentication.
10. **Thử các đường lỗi:** sai issuer/audience, token giả, nonce/state sai, JWKS key không tin cậy, ID token đưa vào API, UserInfo sub khác và logout/replay.

## 13. Tài liệu tham khảo

- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): định nghĩa ID token, các claims bắt buộc, UserInfo, Authorization Code Flow và validation.
- [OpenID Connect Discovery 1.0](https://openid.net/specs/openid-connect-discovery-1_0.html): metadata của OP, issuer và `jwks_uri` để RP cấu hình xác minh.
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519): cấu trúc và ý nghĩa các JWT claims như `iss`, `sub`, `aud`, `exp`, `iat`.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): profile access token, giúp phân biệt việc xác minh access token ở resource server.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700): biện pháp tăng an toàn khi ủy quyền và xử lý token.

**Ghi nhớ:** **ID token là bằng chứng về sự kiện xác thực user do OP phát cho một OIDC client xác định; credential đăng nhập là những gì user sử dụng để chứng minh danh tính với OP; access token là credential truy cập API.** Chỉ khi xác minh đúng issuer, chữ ký, audience, thời hạn và ràng buộc luồng, client mới có thể tin danh tính từ ID token. Việc đăng nhập thành công vẫn không thay thế kiểm tra quyền trên từng tài nguyên.
