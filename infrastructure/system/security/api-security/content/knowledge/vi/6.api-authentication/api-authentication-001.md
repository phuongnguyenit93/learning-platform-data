# Authentication xác định client hoặc user là ai

Khi một request đến API, máy chủ cần biết ai đang gửi request đó. Người gọi có thể là một người dùng đang đăng nhập, một ứng dụng di động, một dịch vụ nội bộ, một đối tác hoặc một tiến trình tự động. **Authentication (xác thực) là quá trình kiểm tra bằng chứng danh tính để xác định principal đứng sau request.** Principal là thực thể mà hệ thống nhận diện được, chẳng hạn user, service account hoặc client application.

Ví dụ, một ứng dụng bán hàng gửi request:

```http
GET /api/orders
Authorization: Bearer eyJ...
```

API phải xác minh credential đi kèm, xác định token được phát hành cho ai hoặc client nào, token còn hiệu lực và được phát hành bởi bên đáng tin cậy hay không. Sau khi xác thực thành công, API có thể tạo security context gắn với request. Các bước phân quyền tiếp theo sẽ quyết định principal đó được phép đọc đơn hàng nào hoặc thực hiện hành động gì.

Đây là ranh giới quan trọng của API security: **authentication trả lời “ai đang gọi?”; authorization trả lời “principal này được phép làm gì?”.** Đăng nhập thành công không đồng nghĩa với việc có quyền truy cập mọi endpoint hoặc mọi đối tượng dữ liệu.

## 1. Principal, credential và bằng chứng danh tính

Ba khái niệm cần phân biệt:

- **Identity (danh tính):** thông tin biểu diễn một user, client hoặc service trong hệ thống. Ví dụ: `user-42`, `billing-worker` hoặc `mobile-app`.
- **Credential (thông tin xác thực):** bí mật hoặc bằng chứng được dùng để chứng minh danh tính. Ví dụ: mật khẩu, API key, access token, certificate hoặc chữ ký request.
- **Principal:** danh tính đã được hệ thống xác minh và đưa vào security context để xử lý request. Principal có thể mang theo các thuộc tính đã được xác minh như issuer, subject, client ID, authentication time hoặc phương thức xác thực.

Không nên coi một chuỗi do client tự gửi như `X-User-Id: user-42` là principal. Header đó chỉ là dữ liệu đầu vào cho đến khi được xác minh bởi một cơ chế tin cậy. Nếu API nhận identity header từ API gateway, cần bảo đảm request không thể đi vòng qua gateway, gateway xóa header cùng tên do client gửi, kết nối giữa gateway và service được bảo vệ, và service chỉ tin header từ nguồn đã xác thực.

### 1.1. Xác thực user và xác thực client khác nhau

Một request có thể đại diện cho người dùng hoặc cho chính ứng dụng:

| Loại principal | Ví dụ | Hệ thống muốn xác minh điều gì? |
|---|---|---|
| User | `user-42` | Người đang sử dụng ứng dụng là tài khoản nào? |
| Client application | `mobile-app` | Ứng dụng nào đang gửi request? |
| Service account | `invoice-worker` | Tiến trình hoặc dịch vụ máy chủ nào đang gọi? |
| Partner integration | `partner-acme` | Đối tác tích hợp nào đang sử dụng API? |
| Workload identity | Một workload chạy trong cluster hoặc cloud | Request đến từ workload đã được nền tảng cấp danh tính nào? |

Xác thực client không tự động xác thực người dùng cuối. Ví dụ, API key của ứng dụng di động có thể nhận diện ứng dụng đã đăng ký, nhưng không chứng minh người đang cầm điện thoại là `user-42`. Ngược lại, access token được cấp cho user có thể mang cả thông tin client đã xin token. Hệ thống cần xác định rõ đang xác thực user, client hay cả hai.

### 1.2. Danh tính cần ổn định và có nguồn tin cậy

Không nên dùng email hoặc tên hiển thị làm định danh chính nếu hệ thống cho phép người dùng đổi chúng. Với OpenID Connect, cặp `iss` (issuer) và `sub` (subject) là cơ sở nhận diện user trong phạm vi issuer. Hai issuer khác nhau có thể cấp cùng một giá trị `sub` cho hai tài khoản khác nhau, nên chỉ so sánh `sub` là chưa đủ.

Với machine client, dùng định danh client hoặc service account do hệ thống quản lý. Không lấy tên tiến trình, hostname hoặc một header tùy ý làm bằng chứng danh tính nếu chưa có cơ chế xác minh ràng buộc nó với workload thật.

## 2. Authentication diễn ra ở đâu trong một request?

Một API thường nhận credential ở gateway hoặc resource server. Thành phần xác thực kiểm tra credential rồi tạo principal context cho request. Sau đó ứng dụng mới xử lý phân quyền, validation và nghiệp vụ.

```mermaid
flowchart TD
    C[Client: user / app / service] -->|HTTPS request + credential| G[API Gateway hoặc API]
    G --> P[Phân tích loại credential]
    P --> V{Credential hợp lệ?}
    V -->|Không| E[401 Unauthorized]
    V -->|Có| I[Tạo principal / security context]
    I --> A[Authorization: kiểm tra quyền]
    A --> B[Validation và quy tắc nghiệp vụ]
    B --> D[(Dữ liệu / dịch vụ)]
```

Quy trình xác thực có thể gồm các bước:

1. Xác định loại credential được endpoint chấp nhận, chẳng hạn bearer access token, API key hoặc client certificate.
2. Trích xuất credential từ vị trí được quy định trong giao thức. Với bearer token, thông thường dùng header `Authorization`; không nhận token tùy tiện từ nhiều vị trí khác nhau.
3. Kiểm tra bằng chứng: chữ ký, secret, certificate chain, trạng thái token hoặc chữ ký request tùy cơ chế.
4. Kiểm tra ngữ cảnh: issuer, audience, thời hạn, client, loại token và các điều kiện bắt buộc khác.
5. Ánh xạ kết quả thành principal ổn định, gắn với request và ghi nhận phương thức xác thực cần thiết.
6. Nếu credential không hợp lệ, hết hạn, bị thu hồi hoặc không dành cho API này, từ chối request trước khi chạy nghiệp vụ.

Không được tự tạo principal từ các claim chưa xác minh. Một JWT có thể giải mã được không có nghĩa là chữ ký hợp lệ hoặc nội dung bên trong đáng tin cậy.

## 3. Những phương thức xác thực thường gặp

Mỗi phương thức có mô hình tin cậy, cách vận hành và giới hạn khác nhau. Việc chọn cơ chế nên dựa trên loại client, mức nhạy cảm của dữ liệu, khả năng lưu giữ bí mật và yêu cầu thu hồi credential.

### 3.1. API key

API key là một chuỗi credential do hệ thống cấp cho ứng dụng hoặc đối tác. Client gửi key trong header đã được quy định, ví dụ:

```http
GET /api/catalog
X-API-Key: ak_live_7f...
```

API tra cứu key, xác định client sở hữu key và kiểm tra trạng thái của key. API key phù hợp với một số tích hợp máy-với-máy đơn giản, nhận diện project hoặc áp quota theo client. Tuy nhiên, API key thường là bearer secret: ai có được chuỗi key đều có thể sử dụng nó.

Các nguyên tắc bảo vệ API key:

- Sinh key có entropy cao bằng bộ sinh số ngẫu nhiên an toàn; không dùng ID tuần tự hoặc giá trị dễ đoán.
- Chỉ hiển thị secret đầy đủ khi tạo; lưu trữ an toàn và ưu tiên lưu hash/HMAC digest để có thể so sánh mà không cần giữ secret dạng rõ.
- Dùng key ID hoặc prefix không bí mật để tra cứu bản ghi; không dùng prefix đó thay cho secret.
- Gắn key với một client, scope, quota, môi trường và thời hạn cụ thể; áp dụng quyền tối thiểu.
- Truyền key qua HTTPS trong header; không đặt key trong URL, query string, source code frontend hoặc log.
- Có khả năng vô hiệu hóa, xoay key và xem lịch sử sử dụng. Khi nghi ngờ lộ key, thu hồi key cũ; xóa khỏi file hiện tại không làm key đã lộ mất hiệu lực.

Không nên coi API key nhúng trong JavaScript hoặc ứng dụng di động là bí mật. Người dùng có thể trích xuất key từ bundle, bộ nhớ hoặc lưu lượng của chính thiết bị. Với client công khai, key có thể hỗ trợ nhận diện ứng dụng hoặc quota, nhưng không thể chứng minh riêng người dùng cuối và không thay thế đăng nhập user.

### 3.2. HTTP Basic authentication

Basic authentication gửi cặp username/password được mã hóa Base64 trong header:

```http
Authorization: Basic dXNlcjpwYXNzd29yZA==
```

Base64 chỉ là encoding, không phải mã hóa. Bất kỳ ai đọc được header đều có thể khôi phục username và password. Nếu dùng Basic authentication, bắt buộc bảo vệ bằng TLS, tránh lưu credential ở log và chỉ cân nhắc trong những môi trường có kiểm soát, thường là tích hợp đơn giản hoặc hệ thống cũ.

Với đăng nhập bằng mật khẩu, máy chủ phải so sánh password với password hash được tạo bằng thuật toán chuyên dụng cho mật khẩu như Argon2id, bcrypt, scrypt hoặc PBKDF2 với tham số phù hợp. Mỗi password cần salt ngẫu nhiên; không mã hóa password theo cách có thể giải mã ngược và không dùng hash nhanh như SHA-256 đơn thuần để lưu password. Cần giới hạn thử sai, phát hiện credential stuffing và có quy trình đặt lại mật khẩu an toàn.

### 3.3. Session cookie

Trong mô hình session-based, sau khi user đăng nhập thành công, máy chủ tạo session và gửi session identifier trong cookie:

```http
Set-Cookie: __Host-session=...; Path=/; Secure; HttpOnly; SameSite=Lax
```

Ở các request sau, trình duyệt tự gửi cookie. Máy chủ dùng session ID để tìm trạng thái phiên và xác định user. Session ID là credential dạng bearer; nếu bị đánh cắp, kẻ tấn công có thể chiếm phiên.

Một số biện pháp cần có:

- Dùng cookie `Secure`, `HttpOnly`, cấu hình `SameSite` phù hợp và giới hạn `Path`/`Domain`; tiền tố `__Host-` có thể giúp ràng buộc cookie với host theo quy tắc của trình duyệt.
- Sinh session ID ngẫu nhiên, đủ dài; không đưa thông tin user hoặc quyền vào giá trị session ID.
- Đổi session ID sau khi đăng nhập hoặc nâng mức xác thực để chống session fixation.
- Có thời hạn idle và absolute; thu hồi session khi logout, đổi mật khẩu hoặc phát hiện rủi ro.
- Với request thay đổi trạng thái dùng cookie tự động gửi, triển khai bảo vệ CSRF phù hợp. `SameSite` hữu ích nhưng không nên mặc định là biện pháp duy nhất cho mọi kiến trúc.

Session cookie phù hợp với ứng dụng web có backend quản lý phiên hoặc mô hình Backend for Frontend (BFF). Nếu API được gọi từ nhiều loại client, cần xác định rõ cookie session là cơ chế xác thực của client nào và bảo vệ CSRF ra sao.

### 3.4. OAuth 2.0 và OpenID Connect

OAuth 2.0 là framework ủy quyền cho phép client nhận access token để gọi resource server. OpenID Connect (OIDC) bổ sung lớp nhận diện user trên OAuth 2.0, trong đó ID token cung cấp thông tin xác thực user cho client.

Các vai trò thường gặp:

- **Resource Owner:** thường là người dùng sở hữu dữ liệu.
- **Client:** ứng dụng xin quyền truy cập.
- **Authorization Server / OpenID Provider:** xác thực user hoặc client và cấp token.
- **Resource Server:** API nhận access token và kiểm tra token trước khi phục vụ request.

#### Authorization Code Flow với PKCE

Đây là lựa chọn phổ biến cho ứng dụng có người dùng, gồm web app, native app và public client. PKCE ràng buộc bước đổi authorization code với client đã khởi tạo luồng, giúp giảm nguy cơ code bị đánh cắp rồi sử dụng lại.

```mermaid
sequenceDiagram
    participant U as User
    participant C as Client App
    participant AS as Authorization Server
    participant API as Resource API
    U->>C: Bắt đầu đăng nhập
    C->>AS: Authorization request + code_challenge
    AS->>U: Xác thực user và xin consent nếu cần
    U->>AS: Hoàn tất xác thực
    AS-->>C: Authorization code qua redirect URI
    C->>AS: Code + code_verifier
    AS-->>C: Access token (và ID token nếu OIDC)
    C->>API: Request + access token
    API->>API: Xác minh token và tạo principal
    API-->>C: API response
```

Client phải kiểm tra `state` để chống CSRF trong luồng redirect và dùng `nonce` khi áp dụng OIDC để ràng buộc ID token với yêu cầu đăng nhập. Redirect URI phải được đăng ký chính xác; tránh wildcard rộng hoặc cho phép chuyển hướng tùy ý.

#### Client Credentials Flow

Client Credentials được dùng khi một ứng dụng máy chủ gọi API bằng danh tính của chính nó, không đại diện cho user đang tương tác. Client xác thực với authorization server bằng cơ chế phù hợp, ví dụ client secret, private key hoặc certificate, rồi nhận access token có scope/audience giới hạn.

```http
POST /oauth2/token
Content-Type: application/x-www-form-urlencoded

grant_type=client_credentials&scope=orders.read
```

Client secret không được đặt trong frontend, mobile app hoặc bất kỳ public client nào có thể bị trích xuất. Với workload có hỗ trợ, nên cân nhắc private-key JWT, mTLS hoặc workload identity thay cho một secret tĩnh dùng lâu dài.

#### Access token và ID token không thay thế cho nhau

- **Access token** được cấp để client gọi một resource server. API cần xác minh token dành cho chính API đó.
- **ID token** được OIDC cấp để client biết user đã đăng nhập là ai. Client kiểm tra ID token theo OIDC; resource API không nên chấp nhận ID token làm access token.

Không phải mọi access token đều là JWT. Access token có thể là chuỗi opaque cần introspection tại authorization server. Cũng không nên giả định rằng cứ có JWT thì nó được phát hành bởi OAuth/OIDC; API cần dựa vào hợp đồng và issuer đã cấu hình.

### 3.5. JWT và opaque access token

JWT (JSON Web Token) là định dạng biểu diễn claims có cấu trúc. Một JWT ký số thường gồm header, payload và signature. Phần payload chỉ được Base64URL encode; nó không tự động được mã hóa và người nhận có thể đọc được. Không đặt password, API secret hoặc dữ liệu nhạy cảm vào payload nếu token không được mã hóa theo cơ chế phù hợp.

Ví dụ payload minh họa:

```json
{
  "iss": "https://identity.example.com",
  "sub": "user-42",
  "aud": "orders-api",
  "exp": 1795005000,
  "nbf": 1795001400,
  "iat": 1795001400,
  "client_id": "web-store",
  "scope": "orders.read"
}
```

API chỉ được tin claims sau khi xác minh chữ ký và các điều kiện bắt buộc. Các claim `sub`, `client_id`, `scope` hoặc `tenant` không có ý nghĩa bảo mật nếu token chưa được xác minh. `scope` thường tham gia quyết định quyền, nhưng việc kiểm tra scope thuộc authorization và không thể thay thế kiểm tra quyền trên đối tượng.

Opaque token không để client đọc claims trực tiếp. Resource server có thể gọi token introspection endpoint để kiểm tra token còn active và lấy metadata đã xác minh. Cách này giúp thu hồi token tập trung hơn nhưng thêm một dependency mạng và cần cache có thời hạn hợp lý.

### 3.6. Mutual TLS (mTLS)

Với TLS thông thường, client xác minh danh tính máy chủ bằng certificate. Với mutual TLS, server cũng yêu cầu client trình certificate để xác minh danh tính client ở tầng kết nối.

mTLS hữu ích cho tích hợp service-to-service, partner API hoặc môi trường có PKI quản lý tốt. Cần:

- Chỉ tin certificate chain từ CA được cấu hình; xác minh thời hạn, mục đích sử dụng và danh tính trong certificate theo chính sách.
- Quản lý cấp phát, gia hạn, thu hồi và xoay certificate.
- Ràng buộc certificate với client/workload cụ thể; không chỉ kiểm tra “có certificate” là chấp nhận.
- Bảo đảm gateway hoặc proxy truyền thông tin certificate đã xác minh tới service theo một kênh tin cậy, không cho client tự giả mạo header chứa subject.

mTLS xác thực client ở tầng kết nối nhưng không tự xác thực user cuối và cũng không tự cấp quyền cho mọi endpoint. Có thể kết hợp mTLS với OAuth access token để vừa xác minh workload vừa xác minh ngữ cảnh token.

### 3.7. Request signing bằng HMAC hoặc chữ ký bất đối xứng

Một số API đối tác hoặc webhook dùng chữ ký trên nội dung request. Client và server chia sẻ secret HMAC hoặc dùng cặp khóa ký/xác minh. Server tính lại chữ ký và so sánh với chữ ký nhận được.

Một thiết kế request signing thường đưa vào chữ ký các thành phần như method, path, query đã chuẩn hóa, hash body, timestamp và nonce. Timestamp giới hạn cửa sổ thời gian; nonce hoặc request ID duy nhất giúp phát hiện request bị phát lại (replay). Nếu chỉ ký body mà bỏ qua method/path, kẻ tấn công có thể thử chuyển một payload hợp lệ sang endpoint hoặc hành động khác tùy cách thiết kế giao thức.

Ví dụ khái niệm:

```text
canonical = method + "\n" + path + "\n" + timestamp + "\n" + nonce + "\n" + sha256(body)
signature = HMAC_SHA256(shared_secret, canonical)
```

Server cần chuẩn hóa request đúng như client, kiểm tra timestamp trong cửa sổ cho phép, từ chối nonce đã dùng và so sánh chữ ký theo cách constant-time. Secret phải được lưu và xoay an toàn. Với chữ ký bất đối xứng, server giữ public key để xác minh; private key chỉ nằm ở client ký request.

### 3.8. Xác thực đa yếu tố và passkey

Với user, có thể tăng độ tin cậy bằng cách yêu cầu nhiều yếu tố độc lập: thứ người dùng biết (password hoặc PIN), thứ họ sở hữu (security key hoặc thiết bị) và đặc điểm sinh trắc học được thiết bị hỗ trợ. Hai bước nhập password liên tiếp vẫn chỉ là một loại yếu tố; MFA cần kết hợp các loại yếu tố khác nhau.

Passkey dựa trên WebAuthn/FIDO2 dùng cặp khóa công khai-riêng tư gắn với relying party. Thiết bị ký challenge của server; server xác minh chữ ký bằng public key đã đăng ký và kiểm tra challenge, origin, RP ID cùng các điều kiện liên quan. Private key không được gửi tới server. Cơ chế này có khả năng chống phishing tốt hơn password hoặc OTP nhập thủ công khi được triển khai đúng.

API thường không tự thực hiện màn hình MFA. Identity Provider xác thực user và có thể đưa mức assurance hoặc phương thức xác thực vào ID/access token theo hợp đồng, chẳng hạn `acr`, `amr` hoặc `auth_time`. Với thao tác nhạy cảm, ứng dụng có thể yêu cầu step-up authentication hoặc xác minh thời điểm xác thực gần đây; resource API phải kiểm tra các claim đã xác minh theo policy của mình.

## 4. Cách chọn cơ chế xác thực

Không có một cơ chế phù hợp cho tất cả loại client. Có thể dùng định hướng sau:

| Trường hợp | Cơ chế thường cân nhắc | Lưu ý chính |
|---|---|---|
| Người dùng đăng nhập vào ứng dụng web/mobile | OIDC Authorization Code + PKCE | Xác thực user tại Identity Provider; API nhận access token |
| Web app có backend/BFF | Server-side session cookie hoặc token được giữ phía backend | Bảo vệ cookie, CSRF và session lifecycle |
| Backend service gọi backend service | Client Credentials, workload identity hoặc mTLS | Xác thực service account, scope/audience hẹp, credential có vòng đời |
| Partner tích hợp đơn giản | API key có scope hoặc OAuth client | Có thể thêm mTLS, quota, rotation và audit |
| Webhook từ nhà cung cấp | HMAC signature hoặc chữ ký bất đối xứng | Kiểm tra timestamp, nonce/replay và body nguyên vẹn |
| Hệ thống cũ hoặc công cụ nội bộ giới hạn | Basic qua TLS hoặc API key | Cần kiểm soát phạm vi, secret storage và kế hoạch nâng cấp |

Trước khi chọn, hãy xác định:

1. Client là public hay confidential? Có giữ được secret an toàn không?
2. Cần xác thực user, client hay cả hai?
3. Credential được cấp bởi ai và API tin issuer hoặc CA nào?
4. Cách giới hạn token cho đúng API, client, thời gian và môi trường là gì?
5. Khi credential bị lộ hoặc user rời tổ chức, thu hồi nhanh đến mức nào?
6. Có yêu cầu audit, liên kết danh tính, xác thực đa yếu tố hoặc mức assurance cao hơn không?

## 5. Xác minh access token đúng cách

Đối với JWT access token, resource server cần dùng cấu hình issuer đáng tin cậy và quy tắc xác minh rõ ràng. Một checklist phổ biến gồm:

- **Chữ ký:** xác minh chữ ký bằng key phù hợp lấy từ nguồn tin cậy; chỉ cho phép thuật toán đã cấu hình, không chọn thuật toán tùy ý theo dữ liệu không tin cậy trong token.
- **Issuer (`iss`):** phải khớp chính xác issuer được tin cậy cho API hoặc tenant.
- **Audience (`aud`):** phải chứa định danh resource API này; token dành cho ứng dụng khác không được chấp nhận.
- **Expiration (`exp`):** từ chối token đã hết hạn; chỉ cho phép clock skew nhỏ, có kiểm soát.
- **Not Before (`nbf`):** không chấp nhận token trước thời điểm hiệu lực.
- **Issued At (`iat`):** có thể kiểm tra thời điểm phát hành để phát hiện token bất thường hoặc vượt chính sách tuổi token.
- **Loại token và claims bắt buộc:** kiểm tra token đúng loại và có `sub`/`client_id` hoặc claims cần thiết theo hợp đồng.
- **Key ID (`kid`) và key rotation:** xử lý key chưa biết một cách an toàn; cập nhật JWKS có kiểm soát và không tải key từ URL do token tự chỉ định.

Pseudo-code minh họa:

```pseudo
function authenticateBearer(request):
    token = extractBearerToken(request.authorizationHeader)
    if token is missing:
        return AuthenticationFailure

    header, claims = parseJwtWithoutTrustingIt(token)
    key = trustedKeySet.find(header.kid)
    if key is missing:
        refreshTrustedKeySetSafely()
        key = trustedKeySet.find(header.kid)

    if key is missing:
        return AuthenticationFailure
    if header.alg not in configuredAlgorithms:
        return AuthenticationFailure
    if not verifySignature(token, key, configuredAlgorithms):
        return AuthenticationFailure
    if claims.iss != configuredIssuer:
        return AuthenticationFailure
    if not audienceContains(claims.aud, thisApiAudience):
        return AuthenticationFailure
    if claims.exp is missing or now >= claims.exp + allowedClockSkew:
        return AuthenticationFailure
    if claims.nbf exists and now + allowedClockSkew < claims.nbf:
        return AuthenticationFailure
    if not requiredTokenClaimsPresent(claims):
        return AuthenticationFailure

    return Principal(issuer=claims.iss, subject=claims.sub,
                     clientId=claims.client_id, claims=claims)
```

Đây là luồng khái niệm; thư viện bảo mật đã được kiểm chứng nên thực hiện việc parse và verify JWT thay vì tự viết thuật toán mật mã. Cần cấu hình validator theo issuer và token profile thực tế. Một số access token có thể không dùng `sub` theo cùng cách cho user và client, nên principal mapping phải tuân theo hợp đồng phát hành token.

Với opaque token, resource server gọi introspection endpoint qua kênh được xác thực, kiểm tra `active`, issuer/audience hoặc resource binding theo hợp đồng, thời hạn và các thuộc tính cần thiết. Nếu cache kết quả introspection, TTL phải ngắn hơn khoảng thời gian rủi ro chấp nhận được và cần có cách xử lý thu hồi khẩn cấp.

### 5.1. Những lỗi xác minh token thường gặp

- Chỉ Base64URL-decode JWT rồi tin payload mà không kiểm tra chữ ký.
- Chấp nhận mọi thuật toán hoặc cho phép thuật toán yếu do token tự khai báo.
- Không kiểm tra `aud`, khiến token dành cho API khác được dùng tại endpoint này.
- Bỏ qua `iss`, dẫn đến tin token từ issuer không được phép.
- Không kiểm tra `exp`/`nbf`, hoặc cho clock skew quá lớn.
- Lấy public key từ URL `jku`/`x5u` tùy ý trong token thay vì nguồn key đã cấu hình.
- Dùng ID token thay access token.
- Coi claim `scope`, `role` hoặc `tenant` là đáng tin trước khi verify chữ ký và nguồn phát hành.
- Không xử lý key rotation, hoặc cache JWKS vô thời hạn khiến key cũ tiếp tục được chấp nhận.

## 6. Vòng đời credential và token

Credential không chỉ được cấp một lần rồi sử dụng mãi mãi. Vòng đời cần bao gồm tạo, phân phối, lưu trữ, sử dụng, gia hạn, xoay, thu hồi và hết hạn.

### 6.1. Cấp và phân phối

Chỉ cấp credential cho client đã được đăng ký và có owner rõ ràng. Mỗi credential nên có định danh riêng, môi trường, mục đích, scope hoặc audience, ngày tạo, ngày hết hạn và thông tin người chịu trách nhiệm. Tránh dùng một key chung cho nhiều ứng dụng vì khi một client bị lộ sẽ khó xác định phạm vi và thu hồi chính xác.

Credential phải được phân phối qua kênh bảo mật như secret manager hoặc cơ chế provisioning đã được bảo vệ. Không gửi secret qua ticket công khai, chat nhóm không phù hợp, email không mã hóa hoặc commit vào repository. Với workload cloud/cluster, ưu tiên workload identity hoặc cơ chế cấp token ngắn hạn thay vì secret tĩnh dài hạn khi nền tảng hỗ trợ.

### 6.2. Thời hạn access token và refresh token

Access token nên có thời hạn phù hợp với rủi ro và trải nghiệm. Token sống lâu giảm số lần xin token nhưng làm tăng khoảng thời gian bị lợi dụng nếu token bị đánh cắp. Token sống ngắn giới hạn thời gian sử dụng nhưng đòi hỏi cơ chế refresh và availability của authorization server.

Refresh token thường có quyền cấp access token mới nên cần bảo vệ chặt hơn. Với public client, áp dụng refresh token rotation hoặc cơ chế phát hiện tái sử dụng theo khả năng của authorization server. Khi refresh token cũ đã bị dùng lại sau rotation, có thể cần thu hồi token family hoặc yêu cầu đăng nhập lại theo chính sách.

### 6.3. Thu hồi và xoay credential

Khi user logout, đổi mật khẩu, bị khóa tài khoản hoặc khi API key bị lộ, hệ thống cần xác định credential nào phải bị thu hồi. Với JWT tự chứa, API có thể không biết token bị thu hồi ngay lập tức nếu chỉ kiểm tra chữ ký và `exp`. Các lựa chọn gồm access token ngắn hạn, denylist theo `jti`, introspection, token version hoặc thu hồi signing key trong trường hợp khẩn cấp. Mỗi cách có trade-off về độ trễ, hiệu năng và phạm vi ảnh hưởng.

Xoay signing key cần có giai đoạn chuyển tiếp: issuer bắt đầu ký bằng key mới, công bố public key mới, resource server cập nhật JWKS, sau đó ngừng key cũ khi token được ký bằng key cũ đã hết hạn hoặc bị thu hồi. Không xóa key cũ quá sớm nếu vẫn có token hợp lệ đang lưu hành; cũng không giữ key cũ vô thời hạn.

## 7. Xử lý lỗi authentication và phản hồi HTTP

API cần phân biệt lỗi xác thực với lỗi phân quyền:

| Tình huống | Phản hồi thường dùng | Ý nghĩa |
|---|---|---|
| Không có credential khi endpoint yêu cầu xác thực | `401 Unauthorized` | Client cần cung cấp credential hợp lệ |
| Token sai chữ ký, hết hạn, sai issuer hoặc audience | `401 Unauthorized` | Credential không chứng minh được danh tính phù hợp |
| Đã xác thực nhưng không có quyền thực hiện hành động | `403 Forbidden` | Principal đã được nhận diện nhưng không được phép |
| Tài nguyên không tồn tại hoặc chính sách che giấu sự tồn tại | `404 Not Found` | Có thể dùng theo thiết kế API và chính sách rò rỉ thông tin |

Khi trả `401`, API phải gửi header `WWW-Authenticate` để mô tả scheme cần thiết, ví dụ `Bearer`, theo HTTP semantics. Không nên đưa chi tiết nội bộ như “user tồn tại nhưng password sai” hoặc “token có chữ ký đúng nhưng thuộc tenant khác” vào thông báo công khai nếu điều đó giúp dò tài khoản hoặc chính sách. Chi tiết cần thiết cho điều tra nên nằm trong log bảo mật có kiểm soát.

Authentication failure không nên làm lộ stack trace, token, key ID nhạy cảm hoặc claims đầy đủ. Phản hồi nên nhất quán và có correlation/request ID để hỗ trợ người dùng và vận hành.

## 8. Bảo vệ credential trong quá trình truyền và lưu trữ

HTTPS/TLS là yêu cầu cơ bản để bảo vệ credential khi truyền qua mạng. TLS giúp chống nghe lén và sửa đổi trên đường truyền, nhưng không xác minh rằng user có quyền với tài nguyên hoặc client đang sử dụng credential đúng mục đích.

Các nguyên tắc thực hành:

- Bắt buộc HTTPS cho endpoint nhận credential; cấu hình TLS hiện đại và quản lý certificate đúng hạn.
- Không gửi token hoặc API key trong URL vì URL thường xuất hiện trong access log, browser history, proxy và telemetry.
- Không ghi credential vào application log, trace, analytics hoặc error report; mask header `Authorization` và cookie ở gateway.
- Lưu secret server-side trong secret manager hoặc kho mã hóa có kiểm soát; hạn chế người và workload có thể đọc.
- Không đóng gói server secret trong frontend bundle, mobile binary hoặc source map.
- Dùng token ngắn hạn, scope/audience hẹp và cơ chế thu hồi; tách credential giữa môi trường dev, staging và production.
- Kiểm tra thời gian hệ thống và đồng bộ clock để xác minh `exp`, `nbf`, timestamp và chữ ký request chính xác.

Đối với hệ thống có API gateway, cần xác định gateway là nơi kết thúc TLS hay chỉ chuyển tiếp TLS. Nếu gateway xác thực token rồi truyền principal xuống service, service phải tin gateway qua kết nối được bảo vệ và policy rõ ràng. Nếu service có thể được gọi trực tiếp từ mạng khác, nó cần tự xác thực credential hoặc chỉ chấp nhận identity assertion có chữ ký/tin cậy từ gateway.

## 9. Các tình huống thực tế

### 9.1. Một user gọi API bằng access token

User đăng nhập qua OIDC Authorization Code + PKCE. Authorization server xác thực user và cấp access token dành cho `orders-api`. Client gửi token trong header. API xác minh chữ ký hoặc introspection, issuer, audience, thời hạn và claims bắt buộc, sau đó tạo principal dựa trên subject đã xác minh.

API biết request đại diện cho user nào và client nào. Tiếp theo, authorization mới kiểm tra user có quyền đọc đơn hàng cụ thể hay không. Nếu token hợp lệ nhưng user không được phép đọc đơn hàng của người khác, API phải từ chối dù authentication đã thành công.

### 9.2. Một service gọi API bằng client credentials

`invoice-worker` cần gọi `billing-api` để lấy trạng thái thanh toán. Workload xác thực với authorization server bằng danh tính máy, nhận access token có audience `billing-api` và scope cần thiết. `billing-api` xác minh token rồi tạo principal kiểu service với client ID tương ứng.

Không có user cuối trong luồng này. Audit log nên ghi principal service và request/correlation ID. Nếu cần truy vết thao tác được kích hoạt bởi một user, service gọi có thể truyền context nghiệp vụ đã được ký hoặc lưu quan hệ đó trong audit event; không được tự tin vào một `X-User-Id` do caller bất kỳ cung cấp.

### 9.3. Webhook đối tác ký bằng HMAC

Đối tác gửi webhook kèm timestamp và chữ ký HMAC. API lấy secret gắn với đối tác, dựng lại canonical request, kiểm tra timestamp, tính chữ ký và so sánh constant-time. Nếu timestamp quá cũ hoặc nonce/event ID đã xử lý, request bị từ chối hoặc xử lý idempotent theo hợp đồng.

Sau khi xác thực chữ ký, API biết sự kiện đến từ đối tác đã giữ secret. Điều đó không có nghĩa nội dung sự kiện chắc chắn đúng về nghiệp vụ; API vẫn cần validate schema, kiểm tra event ID, trạng thái giao dịch và chống xử lý trùng.

## 10. Kiểm thử authentication

Kiểm thử cần xác minh cả trường hợp hợp lệ và âm tính. Không nên chỉ kiểm tra một token tốt trả về `200`.

| Nhóm kiểm thử | Tình huống | Kết quả mong đợi |
|---|---|---|
| Credential thiếu | Bỏ header hoặc cookie bắt buộc | `401`, không chạy nghiệp vụ |
| Credential sai | API key ngẫu nhiên, password sai, chữ ký HMAC sai | Từ chối xác thực, không tiết lộ bí mật |
| Token hết hạn | `exp` ở quá khứ | `401` |
| Token chưa hiệu lực | `nbf` ở tương lai ngoài clock skew | `401` |
| Sai issuer/audience | Token của issuer hoặc API khác | `401` |
| Sai chữ ký/thuật toán | Chỉnh payload, key không đúng, thuật toán ngoài allowlist | `401` |
| Token bị thu hồi | Token inactive hoặc credential đã revoke | Bị từ chối theo thời gian hiệu lực của cơ chế revoke |
| Sai loại token | Gửi ID token vào resource API | Bị từ chối |
| Client công khai | Kiểm tra không có secret server-side trong bundle | Không tìm thấy bí mật dùng chung |
| Session lifecycle | Session fixation, logout, idle timeout, absolute timeout | Session cũ bị đổi hoặc vô hiệu hóa đúng chính sách |
| Replay | Gửi lại webhook/request signing đã dùng | Bị chặn hoặc xử lý idempotent |
| Key rotation | Token dùng key mới và token cũ trong giai đoạn chuyển tiếp | Chấp nhận/từ chối đúng kế hoạch rotation |

Ngoài kiểm thử đơn vị cho validator, nên kiểm thử tích hợp với authorization server, JWKS rotation, introspection, gateway và clock skew. Cần kiểm tra rằng khi dịch vụ xác thực không khả dụng, hệ thống xử lý theo chính sách fail-closed phù hợp với endpoint nhạy cảm; không tự bỏ qua xác thực để duy trì availability.

## 11. Theo dõi authentication trong production

Authentication là điểm quan trọng để phát hiện chiếm đoạt tài khoản và lạm dụng credential. Các sự kiện nên được quan sát gồm:

- Số lần xác thực thành công/thất bại theo endpoint, client, loại credential và khoảng thời gian.
- Credential bị thu hồi nhưng vẫn được sử dụng; token sai issuer/audience hoặc `kid` không xác định.
- Nhiều lần thử password, API key hoặc refresh token; dấu hiệu credential stuffing, brute force và replay.
- Token được dùng bất thường theo client hoặc workload, nếu dữ liệu telemetry cho phép đánh giá an toàn.
- Lỗi kết nối tới authorization server, introspection endpoint, JWKS hoặc hệ thống secret/certificate.
- Thời gian thu hồi credential và độ trễ cập nhật key/certificate giữa các thành phần.

Log cần chứa request ID, client ID hoặc principal ID đã xác minh, loại credential, kết quả và reason code. Không ghi token đầy đủ, password, API key, session cookie, private key hoặc chữ ký có thể phát lại. Với dữ liệu IP/thiết bị, áp dụng chính sách quyền riêng tư, thời hạn lưu và quyền truy cập phù hợp.

Alert có thể được tạo khi số lần thất bại tăng bất thường, một key mới bị dùng từ nguồn lạ, một token bị từ chối ở nhiều API, hoặc credential đã thu hồi tiếp tục xuất hiện. Cần phân biệt sự cố cấu hình sau đợt rotation với tấn công thực sự bằng cách đối chiếu client, thời điểm phát hành và lịch sử thay đổi.

## 12. Checklist thiết kế authentication cho một endpoint

Trước khi đưa endpoint vào production, hãy trả lời:

- [ ] Endpoint này cho phép loại principal nào: user, client, service hay partner?
- [ ] Credential được phát hành bởi ai và API tin cậy issuer/CA nào?
- [ ] Cơ chế xác thực có phù hợp với public/confidential client và cách lưu secret của client không?
- [ ] API lấy credential từ vị trí chuẩn và có từ chối credential thiếu, sai hoặc không hỗ trợ không?
- [ ] Token được kiểm tra chữ ký, issuer, audience, thời hạn, loại token và claims bắt buộc chưa?
- [ ] Principal được tạo từ danh tính ổn định đã xác minh, không từ header hoặc input tùy ý chưa?
- [ ] Credential có scope, audience, thời hạn, quota và quyền tối thiểu phù hợp không?
- [ ] Có quy trình cấp, phân phối, lưu trữ, refresh, rotation và revocation không?
- [ ] Có bảo vệ TLS, log masking và kiểm soát truy cập secret không?
- [ ] Có kiểm thử token sai/hết hạn/sai audience, key rotation, replay, session lifecycle và step-up/MFA nếu áp dụng không?
- [ ] Có log và alert đủ để phát hiện brute force, credential stuffing, token bất thường và lỗi xác thực không?

## 13. Nguyên tắc cần ghi nhớ

Authentication xác minh bằng chứng danh tính và tạo principal tin cậy cho request. Credential có thể là password, session cookie, API key, access token, client certificate hoặc chữ ký request; mỗi loại có giới hạn và vòng đời riêng.

API cần biết mình đang xác thực user hay client. API key của ứng dụng không chứng minh danh tính người dùng cuối; Client Credentials xác thực ứng dụng máy chủ; OIDC xác thực user cho client; access token được resource API xác minh để quyết định request đại diện cho principal nào. ID token và access token có mục đích khác nhau.

Không giải mã JWT rồi tin payload, không đặt bí mật trong frontend, không ghi credential vào log và không để credential sống mãi mà không có cách thu hồi. Sau khi authentication thành công, API vẫn phải thực hiện authorization theo endpoint, đối tượng dữ liệu, thuộc tính và luồng nghiệp vụ.

## Tài liệu tham khảo

- RFC 6749 — The OAuth 2.0 Authorization Framework.
- RFC 7636 — Proof Key for Code Exchange by OAuth Public Clients (PKCE).
- OpenID Connect Core 1.0 — Authentication trên OAuth 2.0 và ID Token.
- W3C Web Authentication (WebAuthn) — API xác thực web dựa trên public key credential.
- RFC 6750 — OAuth 2.0 Bearer Token Usage.
- RFC 7519 — JSON Web Token (JWT); RFC 8725 — JSON Web Token Best Current Practices.
- RFC 7662 — OAuth 2.0 Token Introspection; RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens.
- OWASP Cheat Sheet Series: Authentication, Session Management, Password Storage, Secrets Management và REST Security.
