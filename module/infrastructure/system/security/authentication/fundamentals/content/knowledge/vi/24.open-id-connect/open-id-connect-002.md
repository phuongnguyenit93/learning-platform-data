# ID token — Bằng chứng xác thực dành cho OpenID Connect client

> **Chương:** OpenID Connect  
> **Chủ đề:** ID token  
> **Phạm vi:** Security Authentication Fundamentals — hiểu ý nghĩa ID token, cấu trúc claim, cách OpenID Connect client xác minh kết quả đăng nhập, phân biệt ID token với access token và bảo vệ phiên ứng dụng sau federation.

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích ID token là gì, được phát hành bởi OpenID Provider (OP) cho client nào và chứng minh điều gì.
2. Phân biệt ID token với OAuth access token, refresh token và dữ liệu từ UserInfo endpoint.
3. Đọc các claim cốt lõi như issuer, subject, audience, issued-at, expiration, nonce, auth_time, acr và amr.
4. Thiết kế luồng Authorization Code với PKCE và xác minh ID token theo OpenID Connect Core.
5. Nhận diện các lỗi như bỏ qua audience, không kiểm tra issuer, nonce mismatch, algorithm confusion, key confusion và token replay.
6. Ánh xạ subject federated với tài khoản nội bộ, tạo session an toàn và xử lý logout/thu hồi.
7. Xây dựng bộ kiểm thử chứng minh ID token không thể bị dùng nhầm làm access token hoặc chuyển sang client khác.

## 1. ID token là gì?

**ID token (Identity Token)** là một security token do **OpenID Provider (OP)** phát hành cho một **Relying Party / OpenID Connect client**. Nó mang các claim về sự kiện xác thực của End-User và định danh chủ thể mà OP đã xác thực. Client dùng ID token để xác nhận rằng OP đã thực hiện một lần xác thực theo ngữ cảnh giao thức và để biết subject nào đã đăng nhập.

OpenID Connect (OIDC) xây dựng trên OAuth 2.0. OAuth chủ yếu giải quyết việc client nhận quyền truy cập resource; OIDC bổ sung một lớp định danh/xác thực có chuẩn hóa. ID token là phần cốt lõi giúp client biết kết quả xác thực.

Ví dụ: Người dùng chọn “Đăng nhập bằng tài khoản doanh nghiệp” trong ứng dụng. Ứng dụng chuyển browser tới OP. Sau khi người dùng xác thực bằng passkey hoặc MFA, OP trả authorization response và client đổi authorization code lấy token response. Trong response có ID token. Client xác minh token, ánh xạ subject với tài khoản nội bộ rồi tạo session.

### ID token trả lời câu hỏi nào?

ID token giúp client xác định:

- Token do issuer nào phát hành?
- Subject nào đã được xác thực trong phạm vi issuer đó?
- Token được phát hành cho client nào?
- Token được phát hành lúc nào và hết hạn lúc nào?
- Token có gắn với nonce của giao dịch đăng nhập mà client đã khởi tạo không?
- Có thông tin ngữ cảnh xác thực nào được OP cung cấp theo thỏa thuận không?

ID token **không tự cấp quyền** cho người dùng trên mọi chức năng của ứng dụng. Nó cũng không tự chứng minh người dùng có quyền đọc dữ liệu, chuyển tiền, quản trị tenant hoặc gọi một API cụ thể. Authorization vẫn do ứng dụng và resource server thực hiện theo policy riêng.

## 2. Phân biệt ID token với các loại token khác

OIDC/OAuth có nhiều token và dữ liệu định danh. Chúng không thể thay thế lẫn nhau.

| Loại | Bên phát hành | Bên sử dụng dự kiến | Mục đích |
| --- | --- | --- | --- |
| **ID token** | OpenID Provider | OIDC client | Thông tin xác thực và định danh subject dành cho client |
| **Access token** | Authorization server | Resource server/API | Truy cập tài nguyên theo scope/authorization đã cấp |
| **Refresh token** | Authorization server | OAuth client tại token endpoint | Yêu cầu access token mới theo grant và policy |
| **UserInfo response** | OpenID Provider | OIDC client có access token hợp lệ | Cung cấp thêm claims về End-User |
| **Authorization code** | Authorization server | Client tại token endpoint | Mã dùng một lần để đổi lấy token response |
| **Local session cookie** | Ứng dụng/RP | Browser gửi lại ứng dụng | Duy trì phiên đăng nhập của chính ứng dụng |

### ID token không phải access token

ID token được phát hành cho client. Access token được phát hành để resource server chấp nhận. Hai token có audience và semantics khác nhau:

- ID token thường có audience là client ID của ứng dụng;
- Access token có thể dành cho một API/resource hoặc được quản lý theo profile của authorization server;
- ID token mang thông tin xác thực/subject;
- Access token mang quyền truy cập theo grant/scope hoặc policy;
- Resource API phải kiểm tra access token theo hợp đồng của nó, không chấp nhận ID token chỉ vì chữ ký hợp lệ.

**Không gửi ID token tới API như bearer access token.** Đây là một dạng token substitution/cross-JWT confusion có thể khiến API chấp nhận bằng chứng được phát hành cho sai bên nhận.

### Ví dụ

Một ứng dụng có client ID là **staff-portal**, còn API có audience là **https://hr-api.example.com**.

- ID token với audience **staff-portal** được client kiểm tra để hoàn tất đăng nhập.
- Access token được phát hành cho **https://hr-api.example.com** được gửi tới HR API theo scope đã cấp.
- HR API từ chối ID token dành cho staff-portal, dù token đó có chữ ký hợp lệ.

## 3. Cấu trúc ID token

ID token thường được biểu diễn dưới dạng JWT. Trong trường hợp phổ biến, JWT dùng JWS để bảo vệ tính toàn vẹn và xác thực nguồn phát hành. Một số triển khai có thể mã hóa ID token bằng JWE theo cấu hình client và OP.

JWS compact serialization có ba phần được ngăn cách bằng dấu chấm:

1. **Protected header:** thuật toán ký và thông tin chọn khóa như kid;
2. **Payload:** các claim;
3. **Signature:** chữ ký trên header và payload đã mã hóa.

Ví dụ payload minh họa:

`````````json
{
  "iss": "https://login.example.com",
  "sub": "user-8f31",
  "aud": "staff-portal",
  "exp": 1795324500,
  "iat": 1795323600,
  "auth_time": 1795323500,
  "nonce": "n-9a4d2c",
  "name": "Lan Nguyen",
  "email": "lan@example.com",
  "email_verified": true
}
`````````

Đây là ví dụ để học cách đọc claim, không phải token dùng trong môi trường thật. Payload JWT thường chỉ được Base64URL encode; bất kỳ ai có token cũng có thể đọc phần payload nếu token không được mã hóa. Chữ ký bảo vệ tính toàn vẹn, **không che giấu nội dung**.

### Header và thuật toán

Header có thể chứa:

`````````json
{
  "alg": "RS256",
  "kid": "op-signing-key-2026-02",
  "typ": "JWT"
}
`````````

Client cần:

- Chỉ chấp nhận thuật toán nằm trong allowlist đã cấu hình;
- Lấy khóa từ JWKS của issuer đã được tin cậy;
- Dùng kid để chọn khóa phù hợp trong bộ khóa tin cậy;
- Không tải khóa từ URL tùy ý trong token header;
- Không chấp nhận alg=none hoặc chuyển thuật toán ngoài policy;
- Xử lý key rotation và JWKS cache có kiểm soát.

Không tự viết bộ xác minh chữ ký JWT. Dùng thư viện OIDC/JWT đã được kiểm chứng và cấu hình profile rõ ràng.

## 4. Các claim cốt lõi

OIDC Core định nghĩa các claim có ý nghĩa đặc biệt trong ID token. Một số claim bắt buộc trong ID token cơ bản; một số claim xuất hiện theo yêu cầu của request hoặc theo chính sách OP.

| Claim | Ý nghĩa | Cách client sử dụng |
| --- | --- | --- |
| **iss** | Issuer phát hành token | So khớp chính xác issuer được cấu hình |
| **sub** | Định danh subject tại issuer | Dùng làm định danh federated cùng issuer |
| **aud** | Audience/recipient của ID token | Phải chứa client ID của RP |
| **exp** | Thời điểm hết hạn | Từ chối token đã hết hạn |
| **iat** | Thời điểm phát hành | Kiểm tra hợp lý và áp dụng freshness policy nếu cần |
| **nonce** | Giá trị gắn token với authentication request | Nếu client gửi nonce, phải so khớp chính xác |
| **auth_time** | Thời điểm người dùng được xác thực | Kiểm tra freshness khi yêu cầu max_age hoặc policy tương ứng |
| **acr** | Authentication Context Class Reference | Diễn giải mức/ngữ cảnh xác thực theo hợp đồng với OP |
| **amr** | Authentication Methods References | Diễn giải phương thức xác thực theo semantics đã thỏa thuận |
| **azp** | Authorized party | Kiểm tra theo quy tắc OIDC, đặc biệt khi aud có nhiều giá trị |
| **at_hash** | Hash liên quan access token trong một số flow | Kiểm tra khi flow/response type yêu cầu |
| **c_hash** | Hash liên quan authorization code trong một số flow | Kiểm tra khi flow/response type yêu cầu |
| **sid** | Session ID tại OP trong ngữ cảnh logout | Hỗ trợ liên kết session theo logout protocol |

### iss — issuer

Issuer xác định OP phát hành ID token. Client phải so khớp với issuer đã cấu hình trong trust relationship/discovery metadata. Không tin issuer chỉ vì token có chữ ký hợp lệ bằng một khóa nào đó; khóa phải thuộc issuer mà client đã chủ động tin.

### sub — subject

Subject là định danh End-User trong phạm vi issuer. Cặp **(iss, sub)** là khóa định danh federated quan trọng. Giá trị sub không nhất thiết là username hoặc email; thường là định danh opaque, không nên suy luận danh tính ngoài ý nghĩa được OP cam kết.

Một người dùng có thể có sub khác nhau ở hai issuer. Một issuer cũng có thể cung cấp pairwise subject để giảm khả năng liên kết hoạt động của người dùng giữa các client.

### aud — audience

Audience cho biết client nào được phép nhận ID token. Client phải xác minh client ID của chính nó có trong aud. Nếu có nhiều audience, phải áp dụng quy tắc OIDC cho azp và không bỏ qua kiểm tra authorized party.

### exp và iat

exp là giới hạn thời gian chấp nhận token. iat giúp biết token được phát hành lúc nào và hỗ trợ đánh giá tính mới. Client nên áp dụng clock skew nhỏ, có kiểm soát; không kéo dài thời hạn token bằng cách nới sai lệch đồng hồ quá rộng.

## 5. Nonce, state và PKCE: ba cơ chế khác nhau

Các giá trị này thường xuất hiện cùng nhau trong Authorization Code Flow nhưng bảo vệ các phần khác nhau của giao dịch.

| Cơ chế | Được tạo bởi | Được kiểm tra ở đâu? | Mục tiêu |
| --- | --- | --- | --- |
| **state** | Client/RP | Callback của client | Ràng buộc authorization response với browser transaction, giảm login CSRF |
| **nonce** | Client/RP | Claim nonce trong ID token | Ràng buộc ID token với authentication request, giảm replay/substitution |
| **PKCE code verifier** | Client | Token endpoint khi đổi code | Chứng minh bên đổi authorization code là client đã khởi tạo request |

Không dùng state thay nonce hoặc nonce thay PKCE. Một flow an toàn có thể cần cả ba.

### Yêu cầu với giá trị transaction

- Sinh ngẫu nhiên bằng CSPRNG, đủ entropy;
- Gắn với đúng browser session hoặc client transaction;
- Có thời hạn và trạng thái pending/consumed;
- Chỉ chấp nhận một lần;
- Không đặt giá trị bí mật hoặc dữ liệu cá nhân trực tiếp trong state;
- Không dùng state làm URL redirect tự do;
- Không log code verifier, authorization code hoặc token thô.

### Minh họa

`````````mermaid
sequenceDiagram
    autonumber
    actor U as Người dùng
    participant C as OIDC Client
    participant OP as OpenID Provider
    U->>C: Chọn đăng nhập
    C->>C: Tạo state, nonce, PKCE verifier/challenge
    C-->>U: Redirect tới authorization endpoint
    U->>OP: Gửi authorization request
    OP->>U: Xác thực người dùng
    OP-->>U: Redirect về client với code và state
    U->>C: Callback
    C->>C: So khớp state với transaction
    C->>OP: Đổi code + PKCE verifier
    OP-->>C: ID token và access token
    C->>C: Xác minh ID token, nonce, issuer, audience, thời hạn
    C-->>U: Tạo local session nếu hợp lệ
`````````

## 6. Authorization Code Flow và ID token

Đối với ứng dụng web có backend, **Authorization Code Flow** là lựa chọn phổ biến. PKCE nên được sử dụng để bảo vệ authorization code, bao gồm cả các client có thể giữ secret.

### Các bước

1. Client xác định issuer/OP đã đăng ký và endpoint từ discovery metadata đã xác minh.
2. Client tạo state, nonce, PKCE verifier và challenge; lưu transaction server-side hoặc trong cơ chế an toàn gắn với browser.
3. Client gửi authorization request với response_type=code, client_id, redirect_uri, scope gồm openid, state, nonce và code_challenge.
4. OP xác thực người dùng theo policy.
5. OP trả authorization code và state về redirect URI.
6. Client xác minh state và transaction; từ chối callback không hợp lệ.
7. Client đổi code tại token endpoint đã cấu hình, gửi code_verifier và phương thức xác thực client phù hợp.
8. Client nhận token response, xác minh ID token và xử lý access/refresh token theo policy.
9. Client ánh xạ (iss, sub) với local account, kiểm tra trạng thái tài khoản và tạo session mới.

### Vì sao không dùng Implicit Flow cho ứng dụng mới?

Implicit Flow từng trả token trực tiếp qua front channel. Token có thể xuất hiện trong browser context, history, extension, referrer hoặc các thành phần quan sát URL. Authorization Code Flow giảm việc đưa token qua front channel và cho phép đổi code tại token endpoint; PKCE ràng buộc code với client đã khởi tạo.

Không nên thiết kế luồng mới dựa vào việc ID token hoặc access token xuất hiện trực tiếp trong URL fragment.

## 7. Xác minh ID token theo từng lớp

Client chỉ được coi người dùng đã đăng nhập sau khi kiểm chứng ID token theo OIDC và policy của ứng dụng.

### Bước 1: Xác định đúng issuer và khóa

- Lấy discovery metadata từ issuer được cấu hình trước;
- Xác minh issuer trong metadata khớp issuer mong đợi;
- Lấy JWKS từ jwks_uri đã được metadata tin cậy chỉ định;
- Chọn khóa theo kid trong bộ khóa của issuer;
- Nếu gặp kid chưa biết, refresh JWKS theo cách có giới hạn; không đi theo jku/x5u tùy ý trong token;
- Chỉ chấp nhận thuật toán ký được cấu hình.

### Bước 2: Xác minh chữ ký và nội dung

- Xác minh JWS bằng khóa tin cậy và thuật toán cho phép;
- Nếu client đăng ký yêu cầu mã hóa ID token, xử lý JWE theo cấu hình và tiếp tục xác minh các điều kiện cần thiết;
- Từ chối token bị sửa, sai định dạng hoặc dùng thuật toán ngoài policy.

### Bước 3: Kiểm tra claim định danh và recipient

- iss phải khớp chính xác issuer;
- sub phải có mặt và đúng kiểu;
- aud phải chứa client ID;
- Nếu aud có nhiều giá trị, kiểm tra azp theo OIDC; nếu azp có mặt, xác minh giá trị phù hợp với client;
- Không dùng client_id của access token để thay cho aud của ID token.

### Bước 4: Kiểm tra thời gian và transaction

- exp phải còn hiệu lực;
- iat phải hợp lý theo policy;
- Nếu nbf xuất hiện, xử lý theo profile và kiểm tra thời gian;
- Nếu client gửi nonce, nonce trong ID token phải khớp transaction;
- Nếu request có max_age, kiểm tra auth_time đáp ứng freshness được yêu cầu;
- Với flow/response type có at_hash hoặc c_hash theo profile, kiểm tra các claim hash tương ứng.

### Bước 5: Chỉ sau đó mới tạo principal/session

- Ánh xạ subject theo cặp issuer+subject;
- Kiểm tra local account còn active;
- Áp dụng policy tenant, account linking và risk;
- Regenerate session ID;
- Tạo cookie/session theo cấu hình bảo mật;
- Ghi audit bằng transaction ID và subject reference, không ghi token thô.

### Pseudocode kiểm tra

`````````
validateIdToken(idToken, transaction, clientConfig):
    jwt = parseUsingOidcLibrary(idToken)
    require(jwt.algorithm in clientConfig.allowedSigningAlgorithms)
    verifySignatureWithConfiguredIssuerJwks(jwt)

    claims = jwt.claims
    require(claims.iss == transaction.expectedIssuer)
    require(claims.sub is present and validType)
    require(clientConfig.clientId in normalizeAudience(claims.aud))
    require(authorizedPartyIsValidWhenApplicable(claims, clientConfig.clientId))
    require(nowWithAllowedClockSkew < claims.exp)
    require(issuedAtIsAcceptable(claims.iat, clientConfig.policy))
    require(notBeforeIsValidIfPresent(claims.nbf))
    require(nonceMatchesIfSent(claims.nonce, transaction.nonce))
    require(authTimeSatisfiesMaxAgeIfRequested(claims.auth_time, transaction.maxAge))
    verifyHashClaimsRequiredByTheSelectedFlow(claims, transaction)

    return VERIFIED_IDENTITY(claims.iss, claims.sub)
`````````

Đây là pseudocode mô tả yêu cầu bảo mật, không phải mã triển khai hoàn chỉnh. Thư viện OIDC cần xử lý đúng các profile và quy tắc của flow; ứng dụng không nên tự viết logic cryptography hoặc parser JWT.

## 8. JWKS và vòng đời khóa ký

OP thường công bố khóa công khai trong **JSON Web Key Set (JWKS)**. Client dùng JWKS để xác minh chữ ký ID token.

### kid dùng để làm gì?

Header kid giúp client chọn khóa tương ứng trong JWKS. kid không phải bằng chứng khóa đáng tin và không phải URL. Client phải chọn trong bộ khóa lấy từ issuer đã được xác minh.

### Xử lý key rotation

1. OP công bố khóa mới trong JWKS trước hoặc trong giai đoạn chuyển đổi.
2. Client refresh JWKS khi cần, có cache TTL và giới hạn retry.
3. OP bắt đầu ký token bằng khóa mới.
4. Client xác minh bằng khóa mới sau khi cập nhật JWKS.
5. OP giữ khóa cũ đủ lâu cho token còn hiệu lực, trừ khi khóa bị compromise.
6. Khi khóa cũ bị compromise, cần xử lý khẩn cấp và đánh giá token/session đã phát hành.

Client không nên tải JWKS liên tục theo mỗi request, cũng không nên giữ cache vô thời hạn. Cần có chính sách refresh, timeout, stale-key behavior và cảnh báo khi issuer thay đổi khóa bất thường.

### Khi không thể lấy JWKS

Nếu client chưa có khóa tin cậy phù hợp để xác minh token mới, không được chấp nhận token chỉ vì endpoint JWKS tạm thời lỗi. Có thể dùng khóa đã cache trong giới hạn policy nếu kid và issuer đã được tin cậy; khi không có đủ bằng chứng xác minh, không tạo session.

## 9. Subject, pairwise identifier và quyền riêng tư

Claim sub là định danh subject trong phạm vi issuer. Không giả định nó là email hoặc ID toàn cục.

### Public và pairwise subject

- **Public subject:** cùng một định danh có thể được dùng giữa nhiều client của một OP, theo cấu hình.
- **Pairwise subject:** OP tạo định danh khác nhau theo sector/client group để giảm khả năng các RP liên kết hoạt động người dùng với nhau.

Với pairwise subject, cùng một người có thể có sub khác nhau ở hai client. Điều này là chủ đích về quyền riêng tư, không phải lỗi đồng bộ.

### Liên kết với tài khoản nội bộ

RP nên dùng cặp issuer+sub làm khóa liên kết federated. Email, tên hiển thị hoặc số điện thoại là thuộc tính hỗ trợ liên hệ; chúng có thể đổi, trùng hoặc được tái cấp.

Quy trình link:

1. Người dùng đăng nhập vào local account hiện có bằng phương thức đáng tin;
2. Người dùng chủ động thêm OIDC provider;
3. RP khởi tạo transaction link riêng, có state/nonce;
4. RP xác minh ID token theo đúng client/issuer;
5. RP kiểm tra issuer+sub chưa liên kết với account khác;
6. RP ghi liên kết và audit;
7. RP thông báo thay đổi qua kênh hiện có.

Không tự động gộp tài khoản chỉ vì email giống nhau hoặc email_verified=true. Nếu có xung đột, cần quy trình xác minh quyền sở hữu cả hai tài khoản.

## 10. Claims về thông tin người dùng và UserInfo endpoint

ID token có thể mang các claim như name, preferred_username, email, email_verified, locale hoặc picture nếu OP cung cấp theo scope và policy. Client chỉ nên yêu cầu dữ liệu cần thiết.

**UserInfo endpoint** là endpoint được bảo vệ bằng access token, trả thêm claims về End-User. Nếu client dùng UserInfo response để bổ sung profile, cần kiểm tra claim sub trong response khớp sub đã xác minh từ ID token.

### Quy tắc an toàn

- Chỉ gọi UserInfo endpoint được discovery metadata của issuer chỉ định;
- Gửi access token qua HTTPS theo cách thức được hỗ trợ;
- Không gửi ID token thay access token;
- Kiểm tra sub của UserInfo response khớp ID token;
- Không dùng profile claims làm authorization nếu chưa có policy;
- Chỉ yêu cầu scope như profile/email khi thực sự cần;
- Bảo vệ dữ liệu cá nhân và tuân thủ retention/consent policy.

### Email không phải khóa định danh

Ngay cả khi email_verified=true, RP vẫn nên liên kết tài khoản theo issuer+sub. Email đã xác minh là tín hiệu về trạng thái email theo OP; nó không bảo đảm email không đổi, không tái cấp hoặc không trùng trong một hệ thống khác.

## 11. ACR, AMR và thời điểm xác thực

ID token có thể mang thông tin về ngữ cảnh xác thực:

- **acr:** lớp/ngữ cảnh xác thực theo profile mà OP công bố;
- **amr:** phương thức được sử dụng để xác thực;
- **auth_time:** thời điểm End-User được xác thực.

RP có thể yêu cầu max_age để buộc xác thực đủ mới hoặc dùng acr_values để yêu cầu một ngữ cảnh xác thực theo thỏa thuận với OP. OP có thể hỗ trợ hoặc không hỗ trợ yêu cầu đó; RP phải xử lý trường hợp không đạt theo policy.

### Không suy diễn assurance từ chuỗi claim

Giá trị amr chứa “mfa” không tự chứng minh MFA chống phishing hoặc có mức assurance cụ thể. Giá trị acr cũng chỉ có ý nghĩa khi RP và OP thống nhất semantics, cách kiểm chứng và cách thay đổi policy.

Ví dụ, ứng dụng yêu cầu xác thực lại bằng phương thức chống phishing trước khi thay đổi thông tin nhận lương. Ứng dụng phải biết OP biểu diễn kết quả đó bằng acr/amr nào, auth_time có đủ mới không và có bằng chứng nào bảo đảm claim không bị diễn giải sai.

## 12. Session của ứng dụng sau khi nhận ID token

ID token thường phục vụ hoàn tất đăng nhập; ứng dụng nên tạo **local session** riêng. Không nên dùng ID token làm session cookie hoặc gửi ID token trong mỗi request ứng dụng.

### Web application

- Tạo session ID ngẫu nhiên mới sau khi xác thực thành công;
- Cookie cần Secure và HttpOnly; chọn SameSite phù hợp với callback và kiến trúc;
- Đặt Domain/Path hẹp;
- Có idle timeout và absolute timeout;
- Thu hồi session khi logout, account disable, unlink identity hoặc phát hiện compromise;
- Chống CSRF và XSS theo threat model;
- Không lưu ID token/access token trong URL, log hoặc analytics;
- Nếu browser cần access token, dùng kiến trúc client phù hợp và lưu giữ theo hướng dẫn bảo mật của nền tảng.

### Native/mobile client

Ứng dụng native cần dùng external user-agent/browser theo best practice OIDC/OAuth cho nền tảng, PKCE và redirect URI được kiểm soát. Không nhúng client secret vào ứng dụng công khai như thể nó là bí mật đáng tin cậy.

Token nên được bảo vệ bằng secure storage của hệ điều hành nếu cần lưu. Tránh ghi token vào crash report, clipboard, notification hoặc log debug.

## 13. Logout và vòng đời phiên liên quan tới OP

Logout có thể diễn ra ở nhiều nơi:

- **Local logout:** ứng dụng kết thúc session của chính nó;
- **RP-initiated logout:** ứng dụng yêu cầu OP kết thúc phiên OP theo giao thức;
- **Front-channel/back-channel logout:** OP thông báo tới các RP về sự kiện logout theo cấu hình hỗ trợ.

Không nên giả định local logout tự động đăng xuất người dùng khỏi OP. Người dùng có thể còn phiên SSO tại OP và lần đăng nhập sau được hoàn tất mà không nhập credential lại.

### Logout token và session reference

Khi hỗ trợ OIDC logout protocol, RP cần xác minh logout token theo profile: chữ ký, issuer, audience, thời gian, event claim và session/user reference phù hợp. Nếu token chứa sid hoặc sub, RP phải ánh xạ đúng session cần kết thúc; không xóa mọi session của người dùng nếu policy chỉ yêu cầu một session.

### Thu hồi không chỉ là xóa cookie

Khi account bị disable hoặc federation trust bị thu hồi, ứng dụng cần vô hiệu hóa session/token theo SLA. Xóa cookie ở browser không làm session server-side tự biến mất nếu server vẫn coi session ID là active.

## 14. Threat model và lỗi xác minh ID token

| Rủi ro | Nguyên nhân | Kiểm soát |
| --- | --- | --- |
| **Issuer confusion** | Chấp nhận token từ issuer không được cấu hình | Exact issuer match và khóa gắn với issuer |
| **Audience confusion** | Token của client khác được chấp nhận | Kiểm tra aud chứa đúng client ID |
| **ID/access token confusion** | API hoặc client dùng nhầm loại token | Tách token profile, audience và verifier |
| **Nonce replay** | Không kiểm tra nonce hoặc tái sử dụng transaction | Nonce ngẫu nhiên, transaction-bound, single-use |
| **Login CSRF** | Callback không gắn với browser transaction | State ngẫu nhiên, kiểm tra session |
| **Code interception** | Authorization code bị chặn hoặc đánh cắp | PKCE và redirect URI chính xác |
| **Algorithm confusion** | Client chấp nhận alg không mong muốn | Algorithm allowlist, thư viện đã kiểm chứng |
| **Key confusion** | Lấy khóa từ URL tùy ý hoặc nhầm issuer | JWKS chỉ từ issuer đã tin |
| **Stale/revoked account** | ID token đúng nhưng local account đã disable | Kiểm tra account state trước session và tại API |
| **Email account linking** | Gộp account theo email | Dùng issuer+sub, link có xác minh |
| **Claim over-trust** | Coi group/email/acr/amr là quyền hoặc assurance tuyệt đối | Attribute mapping và semantics agreement |
| **Token leakage** | ID/access token xuất hiện trong log/browser storage | Redaction, secure storage, hạn chế telemetry |
| **Session fixation** | Giữ session ID trước và sau login | Regenerate session ID |
| **JWKS outage** | Bỏ qua xác minh khi không lấy được khóa | Cache có policy; không chấp nhận token chưa xác minh |

### Fail closed

Nếu chữ ký, issuer, audience, thời hạn hoặc nonce không thể xác minh, client không được tạo session. Thông báo cho người dùng nên đủ rõ để hỗ trợ khắc phục nhưng không tiết lộ chi tiết nội bộ hoặc thông tin có thể giúp dò tài khoản.

## 15. Tình huống thiết kế: cổng nhân viên đăng nhập bằng OIDC

Một doanh nghiệp có cổng nhân viên và HR API. OP xác thực nhân viên bằng passkey/MFA. Cổng nhân viên là OIDC client với client ID staff-portal. HR API nhận access token riêng.

### Thiết kế ban đầu có vấn đề

1. Frontend nhận ID token rồi gửi token đó trong Authorization header tới HR API.
2. HR API chỉ kiểm tra chữ ký và exp, không kiểm tra audience.
3. Frontend decode payload và dùng email làm khóa tìm local account.
4. Client không gửi nonce; callback chỉ kiểm tra code tồn tại.
5. Ứng dụng giữ ID token trong localStorage và in token vào log debug.
6. Session ID trước login được giữ nguyên sau khi đăng nhập.

### Thiết kế lại

1. Backend client khởi tạo Authorization Code Flow với state, nonce và PKCE.
2. Callback kiểm tra state và đổi code tại token endpoint đã cấu hình.
3. Client xác minh ID token: chữ ký, iss, aud, exp, iat, nonce và các claim cần thiết.
4. Danh tính được ánh xạ bằng (iss, sub); email chỉ dùng để hiển thị/liên hệ theo policy.
5. Client tạo local session mới, cookie Secure/HttpOnly/SameSite và timeout phù hợp.
6. Khi gọi HR API, client gửi access token có audience dành cho HR API; API xác minh chữ ký/issuer/audience/scope và tenant.
7. Token được redaction khỏi log, tracing và browser telemetry.
8. Khi tài khoản bị disable, session và quyền API bị thu hồi theo SLA.

### Kết quả mong đợi

- ID token chỉ được dùng bởi staff-portal;
- HR API từ chối ID token và chỉ chấp nhận access token đúng audience;
- Callback state/nonce sai không tạo session;
- Subject từ issuer khác không bị gộp chỉ vì email trùng;
- Token hết hạn hoặc account disabled bị từ chối;
- Session ID được thay sau login và có thể thu hồi;
- Không có token thô trong log.

## 16. Bộ kiểm thử chấp nhận

| Trường hợp | Đầu vào/cách thử | Kết quả kỳ vọng |
| --- | --- | --- |
| **ID token hợp lệ** | Token đúng issuer, chữ ký, audience, nonce và thời gian | Client xác minh và tiếp tục login |
| **Issuer sai** | Token từ OP khác | Từ chối |
| **Chữ ký sai** | Sửa payload hoặc dùng khóa không tin cậy | Từ chối |
| **Algorithm không cho phép** | Token dùng alg ngoài allowlist hoặc alg=none | Từ chối |
| **kid không tồn tại** | Token trỏ tới khóa không có trong JWKS tin cậy | Refresh có giới hạn rồi từ chối |
| **Audience sai** | Token dành cho client khác | Từ chối |
| **Audience thiếu** | Token không có aud | Từ chối |
| **Nhiều audience** | aud có nhiều giá trị, azp thiếu/sai theo profile | Từ chối theo quy tắc OIDC |
| **Token hết hạn** | exp đã qua | Từ chối |
| **Token chưa hiệu lực** | nbf trong tương lai nếu profile sử dụng | Từ chối |
| **Nonce sai** | Claim nonce khác transaction | Từ chối |
| **Nonce replay** | Gửi lại ID token/transaction đã tiêu thụ | Từ chối |
| **State sai** | Callback không gắn browser transaction | Từ chối |
| **PKCE sai** | Code verifier không khớp challenge | Token endpoint từ chối đổi code |
| **Auth time cũ** | max_age yêu cầu mới hơn auth_time | Yêu cầu xác thực lại hoặc từ chối |
| **ID token gửi tới API** | Gửi ID token tới HR API | API từ chối do token type/audience |
| **Access token gửi làm ID token** | Đưa access token vào luồng client ID token validation | Client từ chối |
| **UserInfo sub mismatch** | UserInfo sub khác ID token sub | Không gắn profile vào session |
| **Email collision** | Hai issuer phát cùng email nhưng sub khác | Không tự động gộp tài khoản |
| **Account disabled** | ID token hợp lệ nhưng local account disabled | Không tạo session |
| **JWKS rotation** | OP công bố khóa mới và khóa cũ trong overlap | Client refresh và xác minh theo policy |
| **JWKS outage** | Không có khóa tin cậy phù hợp | Không bỏ qua xác minh |
| **Token logging** | Kiểm tra application/APM logs | ID token, access token và refresh token không xuất hiện |
| **Session fixation** | Giữ session ID trước login | Session ID được regenerate sau xác thực |
| **Logout** | Nhận logout event/token hợp lệ | Chỉ session đúng phạm vi bị kết thúc |

Kiểm thử cần chạy ở client callback, session layer và resource API. Chỉ kiểm tra token endpoint trả HTTP 200 không chứng minh client đã xác minh ID token đúng.

## 17. Audit và giám sát OIDC client

Client nên ghi nhận sự kiện đủ để truy nguyên mà không lưu bearer credential.

| Event | Trường gợi ý |
| --- | --- |
| oidc.login.started | Transaction ID, issuer ID, client ID, redirect URI reference |
| oidc.callback.received | Transaction ID, state result, response issuer context |
| oidc.token.validation.failed | Reason code: signature, issuer, audience, nonce, time, type |
| oidc.login.succeeded | Issuer, subject reference, client ID, auth_time/assurance context nếu cần |
| oidc.userinfo.sub_mismatch | Issuer ID, subject references, request ID |
| oidc.jwks.refreshed | Issuer ID, key IDs/fingerprint, refresh result |
| oidc.session.created/revoked | Local session reference, subject reference, reason |
| oidc.logout.received | Issuer, sid/subject reference, validation result |

Không ghi ID token, access token, refresh token, authorization code, PKCE verifier, cookie hoặc client secret. Claim sub/email có thể là dữ liệu cá nhân; dùng reference hoặc pseudonymized value theo chính sách.

### Chỉ số vận hành

- **ID token validation failure rate:** số token bị từ chối theo reason code;
- **Issuer/audience mismatch count:** phát hiện token bị gửi nhầm client hoặc cấu hình OP sai;
- **Nonce/state mismatch count:** theo dõi login CSRF, replay hoặc lỗi transaction;
- **JWKS refresh failure and unknown kid rate:** phát hiện rotation/outage hoặc issuer bất thường;
- **UserInfo subject mismatch count:** phát hiện lỗi liên kết profile;
- **Post-disable session acceptance:** request được chấp nhận sau khi local account disable có hiệu lực;
- **Session revocation latency:** thời gian từ quyết định revoke tới khi session bị từ chối.

Tỷ lệ validation failure cao có thể do OP outage, clock drift, cấu hình client hoặc tấn công. Cần phân loại reason code và đối chiếu thay đổi cấu hình trước khi kết luận.

## 18. Checklist triển khai ID token

- **Purpose:** Client hiểu ID token là bằng chứng xác thực dành cho OIDC client, không phải access token?
- **Issuer:** iss được so khớp chính xác với issuer đã cấu hình?
- **Signature:** Chữ ký được xác minh bằng khóa JWKS tin cậy và thuật toán allowlist?
- **Audience:** aud chứa client ID; azp được kiểm tra khi cần theo OIDC?
- **Subject:** sub có mặt, được lưu trong namespace issuer và không dùng email thay thế?
- **Time:** exp, iat, nbf nếu có, auth_time/max_age và clock skew được kiểm tra?
- **Nonce/state:** Nonce và state gắn transaction, ngẫu nhiên, có expiry và single-use?
- **PKCE:** Authorization Code Flow có PKCE và redirect URI exact match?
- **Token type:** ID token, access token, refresh token và UserInfo response có verifier/đích sử dụng riêng?
- **JWKS:** kid chỉ chọn khóa trong JWKS tin cậy; refresh và rotation có policy?
- **Claims:** acr/amr/email/group được diễn giải theo semantics đã thỏa thuận?
- **Identity mapping:** Dùng issuer+sub; account linking có step-up và audit?
- **Session:** Local session mới, cookie flags, timeout, logout và revoke đầy đủ?
- **Privacy:** Token và claim nhạy cảm không bị ghi log; chỉ yêu cầu scope cần thiết?
- **Testing:** Đã thử issuer/audience/nonce/signature sai, ID/access token confusion, JWKS outage, account disable và session fixation?

### Câu hỏi tự kiểm tra

1. ID token chứng minh điều gì và được phát hành cho bên nhận nào?
2. Vì sao API resource server không nên nhận ID token?
3. iss, sub và aud lần lượt trả lời những câu hỏi nào?
4. State, nonce và PKCE bảo vệ các phần nào của Authorization Code Flow?
5. Khi aud chứa nhiều giá trị, client cần quan tâm điều gì tới azp?
6. Vì sao cặp issuer+sub đáng tin hơn email để liên kết tài khoản?
7. UserInfo response cần được đối chiếu claim nào với ID token?
8. Vì sao ID token hợp lệ vẫn không đủ để cấp quyền quản trị hoặc truy cập mọi tenant?

## Kết luận

**ID token là bằng chứng xác thực do OpenID Provider phát hành cho đúng OIDC client, mang issuer, subject, audience và thông tin thời gian/ngữ cảnh của lần xác thực.** Client phải xác minh chữ ký bằng khóa của issuer đã tin, kiểm tra iss, aud, exp, transaction và nonce, đồng thời áp dụng quy tắc OIDC cho các claim liên quan. ID token không phải access token và không được dùng thay credential gọi API. Sau khi xác minh, ứng dụng liên kết danh tính bằng issuer+subject, kiểm tra local account và policy, rồi tạo local session được bảo vệ. An toàn của OIDC phụ thuộc vào cả token validation, transaction binding, key lifecycle, identity mapping và session management; bỏ qua một lớp có thể làm mất ý nghĩa của bằng chứng xác thực.
