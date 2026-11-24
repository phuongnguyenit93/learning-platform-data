# Session establishment và token issuance

Trong module **SECURITY_TOKEN_SECURITY_FUNDAMENTALS**, một chủ đề cốt lõi của **Authentication** là phân biệt hai việc thường bị gộp thành “đăng nhập”: **thiết lập phiên xác thực (session establishment)** và **phát hành token (token issuance)**. Một hệ thống có thể xác thực người dùng thành công nhưng chưa cấp quyền gọi API; ngược lại, một service có thể nhận access token bằng `client_credentials` mà không hề có phiên đăng nhập của con người.

Bài học giải thích **ai xác thực, phiên được tạo ở đâu, Authorization Server dựa trên điều kiện nào để cấp token và client/API phải tin những gì**. Ví dụ chính dùng OAuth 2.0 Authorization Code kết hợp PKCE và OpenID Connect (OIDC), đồng thời đối chiếu với các luồng không có người dùng.

## 1. Tách ba khái niệm: authentication, session và token

- **Authentication (xác thực):** chứng minh hoặc xác minh một danh tính theo chính sách, ví dụ xác minh mật khẩu kết hợp MFA, passkey hoặc xác thực bằng khóa/certificate của client.
- **Session establishment (thiết lập phiên):** sau khi xác thực và áp dụng chính sách, server tạo trạng thái phiên nhằm nhận biết các yêu cầu tiếp theo mà không buộc thực hiện lại toàn bộ quy trình xác thực ở mỗi lần truy cập.
- **Token issuance (phát hành token):** Authorization Server (AS) đánh giá một yêu cầu hợp lệ rồi tạo token có mục đích, người nhận, quyền và thời gian hiệu lực cụ thể. Việc có phiên không tự động cho phép cấp mọi token mà client yêu cầu.

Trong mô hình OAuth 2.0/OIDC, cần phân biệt **ba phạm vi tin cậy**:

| Phạm vi | Bên quản lý chính | Minh họa | Mục đích |
|---|---|---|---|
| **Phiên tại Authorization Server / OpenID Provider** | AS, ví dụ `auth.example.test` | Cookie đăng nhập của AS tham chiếu tới session phía server | Nhận biết người dùng đã xác thực với AS và hỗ trợ SSO theo chính sách |
| **Phiên của ứng dụng (Relying Party/Client)** | Ứng dụng, ví dụ `app.example.test` | Cookie phiên của ứng dụng tham chiếu tới thông tin đăng nhập và token phía backend | Duy trì trải nghiệm đăng nhập của ứng dụng; quy tắc phiên có thể khác AS |
| **Quyền truy cập API** | Resource Server kiểm tra access token do AS cấp | `Authorization: Bearer <access_token>` | Cho phép các thao tác cụ thể theo scope/audience và chính sách dữ liệu |

Ví dụ, người dùng đã có cookie đăng nhập hợp lệ tại AS. Khi mở một ứng dụng mới, AS **có thể** dùng phiên này để xác thực người dùng mà không hỏi lại mật khẩu; tuy vậy, AS vẫn phải kiểm tra client, redirect URI, quyền yêu cầu, consent hoặc yêu cầu xác thực lại trước khi cấp code/token. Khi ứng dụng đã có access token, API vẫn phải kiểm tra token và phân quyền tài nguyên trên từng request.

**Lưu ý quan trọng:** cookie phiên, authorization code, access token, refresh token và ID token là các hiện vật khác nhau. Không hoán đổi mục đích của chúng chỉ vì đều được sinh ra trong cùng một lần đăng nhập.

## 2. Các hiện vật xuất hiện trong quá trình đăng nhập

| Hiện vật | Tạo bởi | Nơi sử dụng | Có thể dùng trực tiếp để gọi API? |
|---|---|---|---|
| **Authentication transaction / trạng thái đăng nhập tạm** | Client và/hoặc AS | Liên kết request với callback, giữ `state`, PKCE verifier và tùy trường hợp `nonce` | Không |
| **Cookie phiên AS** | AS sau khi xác thực và thiết lập phiên | Browser gửi về miền AS theo thuộc tính cookie | Không; cookie AS không phải token của API |
| **Authorization code** | AS sau khi chấp nhận authorization request | Client đổi code tại token endpoint | Không; code ngắn hạn, một lần dùng |
| **Cookie/ID phiên ứng dụng** | Ứng dụng sau khi xử lý callback thành công | Browser và backend ứng dụng | Không trực tiếp; backend có thể dùng token được giữ phía server để gọi API |
| **Access token** | AS | Client chuyển cho Resource Server | Có, nếu token được API chấp nhận và đủ quyền |
| **ID token** | OpenID Provider trong OIDC | Client xác minh thông tin xác thực của người dùng | Không; thông thường `aud` là client ID |
| **Refresh token** | AS nếu client đủ điều kiện | Client gửi token endpoint để xin access token mới | Không; không dùng tại API nghiệp vụ |

**Session ID** thường là một giá trị ngẫu nhiên khó đoán, dùng để tra trạng thái xác thực ở server. Trong hệ thống stateless hoặc hybrid, cookie có thể chứa dữ liệu phiên đã được bảo vệ bằng cơ chế mã hóa/chữ ký phù hợp; dù dùng cách nào, server vẫn cần chính sách hết hạn, chống chiếm dụng và kết thúc phiên.

## 3. Xác thực danh tính trước khi thiết lập phiên

Session establishment chỉ đáng tin cậy khi sự kiện xác thực được kiểm soát đúng. Một quy trình điển hình tại AS gồm:

1. **Tiếp nhận yêu cầu xác thực:** AS biết request đến từ authorization transaction nào, đã yêu cầu quyền gì, client nào và có cần người dùng tương tác không.
2. **Chọn phương thức xác thực:** mật khẩu, passkey/WebAuthn, MFA, thiết bị hoặc IdP liên kết tùy chính sách và mức độ rủi ro.
3. **Xác minh bằng chứng:** kiểm tra credential/MFA qua thành phần tin cậy; áp dụng rate limiting, chống brute force, theo dõi bất thường và chính sách khóa hoặc trì hoãn phù hợp.
4. **Đánh giá điều kiện bổ sung:** trạng thái tài khoản, MFA bắt buộc, mức độ xác thực yêu cầu, `max_age`, lời nhắc `prompt=login` hoặc quy tắc step-up cho thao tác nhạy cảm.
5. **Thiết lập phiên AS:** tạo/luân chuyển session identifier, ghi chủ thể xác thực, thời điểm xác thực, mức đảm bảo và thời hạn; gửi cookie phiên qua HTTPS nếu thiết kế dùng cookie.
6. **Tiếp tục authorization transaction:** phiên thành công mới là một **đầu vào**; AS tiếp tục xét client, redirect URI, PKCE, quyền, consent rồi mới cấp authorization code/token nếu hợp lệ.

Nếu xác thực không thành công, **không tạo phiên xác thực đã đăng nhập** và không cấp authorization code dựa trên danh tính chưa được chứng minh. Có thể vẫn tồn tại phiên hoặc transaction tiền đăng nhập để phục vụ CAPTCHA, rate limit và CSRF, nhưng không được coi đó là phiên đã xác thực.

### Tạo và bảo vệ session identifier

Một session identifier tốt cần được tạo bằng bộ sinh số ngẫu nhiên mật mã, có entropy đủ lớn, không chứa trực tiếp email/mật khẩu hay dữ liệu dễ đoán, không rò qua URL và không được tái sử dụng tùy tiện. Khi chuyển từ chưa đăng nhập sang đã đăng nhập, server nên **đổi session ID** để chống session fixation.

Ví dụ cookie của AS nếu phiên dùng cookie:

~~~http
HTTP/1.1 302 Found
Set-Cookie: __Host-as_session=<RANDOM_SESSION_ID>; Path=/; Secure; HttpOnly; SameSite=Lax
Location: https://app.example.test/callback?code=<AUTHORIZATION_CODE>&state=<STATE>
~~~

Đây là thông điệp minh họa, không phải chỉ dẫn để nhúng token thật vào tài liệu. Tiền tố `__Host-` yêu cầu `Secure`, `Path=/` và không đặt `Domain`. `HttpOnly` ngăn JavaScript đọc cookie; `Secure` giới hạn việc gửi qua HTTPS; `SameSite` giảm một số rủi ro cross-site. Giá trị `SameSite` thực tế phải tương thích luồng redirect và chính sách CSRF của ứng dụng. Các biện pháp này cần đi cùng bảo vệ XSS, CSRF và session fixation.

> AS nên quản lý **idle timeout** (khoảng không hoạt động), **absolute lifetime** (tuổi thọ tối đa), gia hạn/luân chuyển session ID theo ngữ cảnh, đăng xuất, và vô hiệu hóa phiên khi phát hiện chiếm quyền. Một phiên có cookie ở browser không đồng nghĩa chắc chắn phiên server còn hợp lệ.

## 4. Authorization Code + PKCE: từ ý định đăng nhập đến việc cấp code

Trong ứng dụng web/mobile có người dùng, phương án phổ biến là **Authorization Code flow với PKCE**. OIDC bổ sung scope `openid` để client nhận **ID token** sau khi hoàn tất luồng.

Sơ đồ mô tả cả phiên AS lẫn phiên ứng dụng:

~~~mermaid
sequenceDiagram
    autonumber
    actor U as Người dùng
    participant B as Browser
    participant C as Client / App Backend
    participant AS as Authorization Server
    participant API as Resource Server

    U->>B: Mở ứng dụng
    B->>C: GET /orders
    C-->>B: Chuyển hướng đăng nhập; tạo state và PKCE
    B->>AS: Authorization request + state + code_challenge + nonce
    AS->>AS: Kiểm tra client, redirect URI và yêu cầu
    AS->>U: Xác thực / MFA khi cần
    AS->>AS: Thiết lập hoặc kiểm tra phiên AS
    AS->>AS: Kiểm tra scope, audience và consent/policy
    AS-->>B: Redirect chứa authorization code + state
    B->>C: GET /callback?code=...&state=...
    C->>C: Kiểm tra state và transaction ban đầu
    C->>AS: Đổi code + code_verifier (+ xác thực client nếu cần)
    AS->>AS: Kiểm tra code, PKCE, client, redirect URI; cấp token
    AS-->>C: Access token + ID token (+ refresh token nếu đủ điều kiện)
    C->>C: Kiểm tra ID token, tạo/luân chuyển phiên ứng dụng
    C-->>B: Set-Cookie phiên ứng dụng
    B->>C: Request có cookie phiên
    C->>API: Authorization: Bearer access_token
    API->>API: Kiểm tra issuer, audience, thời hạn, scope, quyền dữ liệu
    API-->>C: Dữ liệu được phép
    C-->>B: Kết quả cho người dùng
~~~

Trong sơ đồ, **client backend giữ token và browser giữ cookie phiên ứng dụng** theo mô hình Backend-for-Frontend (BFF). Với SPA hoặc native app, cách lưu và truyền token sẽ khác, nhưng các điều kiện kiểm tra `state`, PKCE, issuer/audience và mục đích của token không thay đổi.

### Authorization request gồm những gì?

Ví dụ dạng dễ đọc, một số giá trị được rút gọn để trình bày:

~~~http
GET /authorize?response_type=code&client_id=orders-web&redirect_uri=https%3A%2F%2Fapp.example.test%2Fcallback&scope=openid%20profile%20orders%3Aread&state=<RANDOM_STATE>&nonce=<RANDOM_NONCE>&code_challenge=<BASE64URL_SHA256_VERIFIER>&code_challenge_method=S256 HTTP/1.1
Host: auth.example.test
~~~

| Tham số | Ai tạo/kiểm tra? | Vì sao cần? |
|---|---|---|
| `response_type=code` | Client yêu cầu; AS kiểm tra | Chỉ yêu cầu authorization code ở bước redirect |
| `client_id` | AS đã đăng ký client | Xác định client nhận code/token và cấu hình chính sách |
| `redirect_uri` | Client gửi; AS đối chiếu đăng ký | Ngăn đưa code tới callback không được phép; dùng exact match theo chính sách chuẩn và loại client |
| `scope` | Client yêu cầu; AS quyết định phạm vi được cấp | Ví dụ `openid` bật OIDC, `orders:read` yêu cầu đọc đơn hàng |
| `state` | Client tạo ngẫu nhiên, lưu với transaction; kiểm tra khi callback | Liên kết response với request ban đầu; bảo vệ chống CSRF và nhầm luồng |
| `nonce` | Client tạo, sau đó kiểm tra trong ID token khi có dùng | Liên kết ID token với yêu cầu OIDC và giảm nguy cơ replay |
| `code_challenge` / `code_challenge_method=S256` | Client tạo challenge từ `code_verifier` bí mật; AS lưu kiểm tra | Ngăn kẻ chỉ đánh cắp code có thể đổi thành token nếu không có verifier |

**PKCE không phải MFA** và `state` không phải access token. PKCE bảo vệ đường đổi **authorization code**, trong khi `state` liên kết callback với phiên giao dịch. Client cần lưu `code_verifier` bí mật trong transaction tương ứng, không đưa verifier vào URL authorization request.

AS phải từ chối client không được phép, redirect URI không hợp lệ, tham số không đúng hoặc yêu cầu không thỏa chính sách; không chuyển code tới địa chỉ tùy ý hoặc chấp nhận open redirect. Khi có nhiều AS, client còn phải bảo vệ chống **authorization server mix-up**: không đổi code từ issuer A tại token endpoint của issuer B; có thể kiểm tra tham số `iss` ở authorization response nếu được hỗ trợ cùng với ràng buộc issuer theo transaction.

## 5. Authorization code được phát hành và đổi thành token

Sau khi người dùng được xác thực, AS kiểm tra yêu cầu ủy quyền và cấp **authorization code**. Code là giá trị tạm, thường ngắn hạn, chỉ được dùng **một lần** và được ràng buộc với client, redirect URI, PKCE challenge, cùng nội dung authorization grant.

Ví dụ callback:

~~~http
HTTP/1.1 302 Found
Location: https://app.example.test/callback?code=<AUTHORIZATION_CODE>&state=<ORIGINAL_STATE>
~~~

Ở callback, client so sánh `state` với giá trị lưu trước đó. Nếu không khớp, thiếu transaction hoặc callback đã xử lý trước đó, client phải từ chối và không đổi code.

Sau đó backend client gọi token endpoint qua kết nối bảo mật:

~~~http
POST /token HTTP/1.1
Host: auth.example.test
Content-Type: application/x-www-form-urlencoded
Authorization: Basic <ENCODED_CONFIDENTIAL_CLIENT_CREDENTIALS>

grant_type=authorization_code&code=<AUTHORIZATION_CODE>&redirect_uri=https%3A%2F%2Fapp.example.test%2Fcallback&code_verifier=<ORIGINAL_CODE_VERIFIER>
~~~

Ví dụ trên là **confidential client** như backend web, dùng xác thực client bằng HTTP Basic minh họa; giá trị thực là bí mật lưu phía server. AS có thể cấu hình phương thức khác như private key JWT hoặc mTLS. Với **public client** như SPA/native app, token request thường phải gửi `client_id` và PKCE verifier nhưng không có client secret đáng tin cậy. Không đặt client secret vào mã JavaScript/browser hoặc ứng dụng mobile được phân phối cho người dùng.

AS kiểm tra toàn bộ điều kiện trước khi phát hành:

1. Code tồn tại, chưa dùng, chưa hết hạn, được cấp bởi AS này cho đúng client.
2. `redirect_uri` trong request đổi code phù hợp với thông tin đã ràng buộc khi cấp code.
3. AS xác định đúng client đã được cấp code; confidential client phải xác thực theo phương thức đăng ký, còn public client được nhận diện qua `client_id` và các ràng buộc grant/PKCE.
4. `code_verifier` khớp challenge (PKCE) đã lưu; với S256, challenge là Base64url(SHA-256(verifier)) theo quy tắc PKCE.
5. Authorization grant vẫn hợp lệ, người dùng/consent/scope/resource không bị chính sách ngăn chặn.
6. Khi tất cả thành công, AS **đánh dấu code đã sử dụng theo cách chống race** và phát hành token theo grant được phép.

Nếu code đã bị đổi một lần, AS không nên cấp token lần hai cho cùng code, kể cả client gửi lại đúng verifier. Việc code một lần dùng và PKCE giúp giới hạn một số kiểu interception/replay trong quá trình redirect.

### Phản hồi token endpoint

Ví dụ giả định AS quyết định cấp access token, ID token và refresh token:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store
Pragma: no-cache

{
  "access_token": "<ACCESS_TOKEN>",
  "token_type": "Bearer",
  "expires_in": 600,
  "scope": "openid profile orders:read",
  "id_token": "<SIGNED_ID_TOKEN>",
  "refresh_token": "<REFRESH_TOKEN>"
}
~~~

`expires_in: 600` nghĩa là access token có thời lượng được công bố là **600 giây**, chỉ là ví dụ. Không phải mọi client đều nhận refresh token. `id_token` được trả khi áp dụng OIDC theo luồng tương ứng; OAuth 2.0 thuần túy không mặc định cấp ID token.

Token endpoint không được cho cache công khai lưu response chứa token. Client cũng không nên log nội dung response, code hoặc credential.

## 6. Authorization Server quyết định cấp token theo nguyên tắc nào?

**Đăng nhập thành công** là điều kiện cần ở nhiều grant có người dùng, nhưng chưa đủ để AS cấp bất kỳ quyền nào được yêu cầu. Quyết định phát hành phải xét **client + subject/grant + resource/audience + scope + policy + thời gian**.

| Đầu vào | Điều AS cần xét | Rủi ro nếu bỏ qua |
|---|---|---|
| **Client** | Đã đăng ký, đúng grant type, redirect URI, PKCE và phương thức xác thực client | Code/token bị cấp cho ứng dụng giả hoặc callback sai |
| **Identity / subject** | Người dùng đã xác thực, tài khoản còn hiệu lực, độ mạnh/phục vụ `max_age` hay step-up | Token đại diện cho chủ thể chưa xác thực đủ |
| **User authorization / consent** | Người dùng, quản trị viên hoặc policy đã cho phép quyền được yêu cầu chưa | Client lấy quyền người dùng chưa được phép |
| **Scope** | Giao giữa quyền client yêu cầu, policy của AS và những gì được cho phép | Cấp quyền rộng hơn nhu cầu hoặc ủy quyền thực tế |
| **Resource / audience** | Token dành cho API nào; profile cần claim gì | Token dành cho API A được dùng sai tại API B |
| **Lifetime và session policy** | TTL access token, refresh token, giới hạn phiên, token binding, yêu cầu xác thực lại | Token tồn tại quá lâu hoặc vượt thời hạn chính sách |
| **Rủi ro hiện tại** | Thiết bị, bất thường đăng nhập, yêu cầu MFA, phiên bị thu hồi | Phát hành token khi rủi ro không thể chấp nhận |

**Scope** thể hiện phạm vi quyền theo hợp đồng API; **role** hoặc **permission** là dữ liệu quyền theo hệ thống. Một AS có thể mã hóa một phần thông tin này trong token, nhưng Resource Server vẫn phải kiểm tra phân quyền ở cấp endpoint và tài nguyên. `orders:read` không tự cấp quyền xem đơn hàng của người khác.

**Audience** buộc access token tới nơi nhận dự kiến. Một access token có `aud: https://orders-api.example.test` không tự hợp lệ cho `https://payments-api.example.test`, kể cả cùng issuer và cùng chữ ký.

Về **consent**, không phải mọi authorization transaction đều hiển thị màn hình đồng ý. AS có thể dùng quyền đã cấp trước, chính sách doanh nghiệp hoặc giao dịch đòi hỏi xác nhận mới. Sự vắng mặt màn hình consent không có nghĩa AS bỏ kiểm tra quyền.

### Claim của access token minh họa

Với JWT access token đã ký, AS có thể phát hành payload như sau:

~~~json
{
  "iss": "https://auth.example.test",
  "sub": "user-42",
  "aud": "https://orders-api.example.test",
  "client_id": "orders-web",
  "scope": "orders:read",
  "iat": 1800000000,
  "nbf": 1800000000,
  "exp": 1800000600,
  "jti": "at-2026-001"
}
~~~

Đây chỉ là **payload minh họa**, không phải access token được ký. Thời gian là Unix seconds, các giá trị không đại diện cho hệ thống thực.

- `iss`: issuer đáng tin cậy mà API phải đối chiếu chính xác.
- `aud`: tài nguyên/API được phép nhận token.
- `sub`: định danh subject theo issuer, không nên giả định luôn là email.
- `scope`: tập quyền đã cấp; tên claim có thể thay đổi theo AS/profile.
- `iat`, `nbf`, `exp`: thời điểm phát hành, bắt đầu hiệu lực, hết hạn.
- `jti`: định danh token nếu profile cung cấp, hữu ích cho truy vết/thu hồi theo thiết kế.

Nếu access token là **opaque string**, API không tự kiểm tra các claims ở bên trong như JWT; API thường dùng introspection hoặc cơ chế trạng thái tin cậy khác. Quyết định cấp quyền vẫn phải kiểm tra issuer/kết quả đáng tin cậy, audience, scope, trạng thái và quyền dữ liệu.

## 7. ID token xác nhận điều gì về sự kiện đăng nhập?

OIDC sử dụng **ID token** để thông báo cho client về sự kiện xác thực. Nó khác access token, vì ID token có **audience là client** và phải được client xác minh theo quy tắc OIDC.

Một ID token payload minh họa:

~~~json
{
  "iss": "https://auth.example.test",
  "sub": "user-42",
  "aud": "orders-web",
  "iat": 1800000000,
  "exp": 1800000600,
  "nonce": "n-illustrative-742",
  "auth_time": 1800000000,
  "amr": ["pwd", "otp"],
  "acr": "urn:example:assurance:two-factor"
}
~~~

Ý nghĩa:

| Claim | Diễn giải |
|---|---|
| `sub` | Người dùng được xác thực theo định danh của issuer |
| `aud` | Client được phép nhận ID token này, ví dụ `orders-web` |
| `nonce` | Giá trị client gửi trong authorization request, cần so khớp khi có dùng |
| `auth_time` | Thời điểm xác thực người dùng; khác thời điểm phát hành token khi dùng lại phiên SSO |
| `amr` | Phương thức xác thực đã dùng, nếu OP cung cấp theo quy ước của mình |
| `acr` | Mức/ngữ cảnh đảm bảo xác thực theo profile/chính sách, không thể tự suy nghĩa tùy ý |

Không được mặc định rằng mọi OP luôn cấp `amr`, `acr` hoặc `auth_time`: sự xuất hiện và yêu cầu kiểm tra phụ thuộc request, hợp đồng OIDC và profile. Nếu một API/thao tác cần step-up MFA, kiến trúc phải có cơ chế đáng tin cậy xác nhận mức xác thực phù hợp; chỉ nhìn thấy một chuỗi tùy ý trong token chưa đủ.

Client cần **xác minh chữ ký, `iss`, `aud`, `exp`, `nonce` nếu đã gửi, cùng các kiểm tra OIDC liên quan** trước khi thiết lập phiên ứng dụng từ ID token. Không lấy thông tin người dùng chỉ bằng cách Base64url decode rồi tin kết quả.

> **Token confusion:** ID token `aud = orders-web` không phải access token `aud = orders-api`. Resource Server không cho phép dùng ID token thay access token chỉ vì cả hai có cùng `sub` và issuer.

## 8. Thiết lập phiên ứng dụng sau callback thành công

Sau khi code exchange thành công, một client dạng BFF có thể thực hiện:

1. Xác minh token nhận được (đặc biệt ID token trong OIDC) và ràng buộc với authorization transaction.
2. Xác định tài khoản/subject của ứng dụng dựa trên `(iss, sub)`; không dùng email duy nhất toàn hệ thống nếu email có thể thay đổi hoặc chưa được xác minh đúng ngữ cảnh.
3. **Tạo mới hoặc luân chuyển ID phiên ứng dụng** sau đăng nhập để chống session fixation.
4. Lưu access/refresh token trong kho server có kiểm soát truy cập, có mã hóa khi phù hợp, kèm issuer, thời hạn, chủ thể, client và scope.
5. Gửi cookie phiên ứng dụng `HttpOnly; Secure; SameSite` phù hợp; chặn CSRF cho các thao tác thay đổi trạng thái.
6. Xóa transaction tạm (`state`, `code_verifier`, `nonce`) khi đã xử lý và không cho callback dùng lại.

Pseudo-code minh họa luồng phía **client backend**, không phải API chạy trực tiếp được của một framework:

~~~text
function handleOidcCallback(request):
    attempt = lookupPendingLoginAttempt(request.browserTransactionCookie)

    if attempt is missing or expired:
        rejectLogin()
    if constantTimeCompare(request.query.state, attempt.state) is false:
        rejectLogin()
    if attempt.alreadyConsumed:
        rejectLogin()

    markAttemptConsumingAtomically(attempt)

    tokens = exchangeAuthorizationCodeAtTrustedTokenEndpoint(
        issuer = attempt.expectedIssuer,
        code = request.query.code,
        client = configuredClient,
        redirectUri = attempt.registeredRedirectUri,
        codeVerifier = attempt.codeVerifier
    )

    identity = validateOidcIdToken(
        tokens.id_token,
        expectedIssuer = attempt.expectedIssuer,
        expectedAudience = configuredClient.id,
        expectedNonce = attempt.nonce,
        trustedSigningKeys = configuredIssuerKeys
    )

    appUser = findOrCreateLocalUserByIssuerAndSubject(
        identity.iss, identity.sub
    )

    newSessionId = createNewUnpredictableSessionId()
    saveServerSession(
        sessionId = newSessionId,
        user = appUser,
        tokens = storeSecurely(tokens),
        idleAndAbsoluteExpiry = configuredSessionPolicy
    )
    expireAnyPreviousUnauthenticatedSession()
    deletePendingLoginAttempt(attempt)
    setSecureHttpOnlySessionCookie(newSessionId)

    redirectToValidatedPostLoginDestination()
~~~

Ở đây, `markAttemptConsumingAtomically` chỉ biểu thị mong muốn **ngăn một callback được xử lý hai lần** trong tầng client; AS vẫn cần bảo đảm authorization code chỉ đổi được một lần. Cách rollback khi token endpoint lỗi, timeout hoặc user refresh trang phải được thiết kế rõ để không tạo phiên từ kết quả không chắc chắn.

Cookie của ứng dụng đặt trên miền ứng dụng; cookie AS đặt trên miền AS. Một backend chỉ nên nhận diện phiên thuộc chính nó, tránh mở rộng phạm vi cookie để chia sẻ giữa các miền khi không cần thiết.

### Có bắt buộc tạo phiên server-side?

Không. Một SPA có thể quản lý token ở frontend; ứng dụng native có thể dùng lưu trữ an toàn của hệ điều hành; service-to-service có thể không có session người dùng. Tuy nhiên với ứng dụng browser, kiến trúc BFF giảm khả năng mã JavaScript đọc trực tiếp token và cho phép backend điều phối refresh. `HttpOnly` không giải quyết mọi rủi ro XSS: mã độc vẫn có thể phát lệnh dưới phiên người dùng, nên cần chống XSS, CSRF và phân quyền đúng.

## 9. Phiên xác thực khác thời hạn token như thế nào?

Các đồng hồ thời gian có thể chạy **độc lập**:

| Thời hạn | Quyết định ai quản lý? | Điều gì xảy ra khi hết hạn? |
|---|---|---|
| **Phiên AS** | AS | Người dùng có thể phải xác thực lại khi có authorization request mới; token đã phát hành chưa chắc tự hết hạn ngay |
| **Phiên ứng dụng** | Client/backend | Ứng dụng yêu cầu người dùng đăng nhập lại hoặc kiểm tra lại tình trạng phiên |
| **Access token** | AS định nghĩa, API kiểm tra | API từ chối token quá hạn; có thể nhận token mới theo grant hợp lệ |
| **Refresh token** | AS và chính sách client/session | Client không được tiếp tục dùng refresh token đã hết hạn/thu hồi; có thể phải thực hiện ủy quyền mới |
| **Authorization code** | AS | Không thể dùng để đổi token nếu code hết hạn/đã sử dụng |

Ví dụ một cấu hình minh họa:

~~~text
09:00  Người dùng xác thực MFA tại AS -> tạo phiên AS
09:01  AS cấp code; client đổi thành AT1 (10 phút) + RT1 (nếu được phép)
09:02  Client tạo phiên ứng dụng, idle timeout 30 phút
09:11  AT1 hết hạn; client có thể dùng RT1 để xin AT2
09:20  Người dùng vẫn dùng app: phiên ứng dụng chưa hết idle timeout
09:44  Client vừa nhận ATn mới, ví dụ hết hạn lúc 09:54
09:45  Người dùng đăng xuất app -> hủy phiên ứng dụng và yêu cầu thu hồi RT
09:46  Bản sao ATn vẫn có thể cần cơ chế chặn riêng trước 09:54
~~~

Các mốc và TTL là ví dụ, không phải giá trị chuẩn bắt buộc. Việc truy cập API sau logout phụ thuộc token đã được thu hồi/chặn ở API hay còn hiệu lực theo `exp`.

**Single Sign-On (SSO)** là trường hợp một phiên còn hiệu lực tại AS có thể giúp đăng nhập vào nhiều client theo chính sách. SSO không đồng nghĩa “một cookie dùng mọi API”. **Single Logout** hoặc logout liên kết giữa AS và các client đòi hỏi cơ chế và cấu hình cụ thể; xóa cookie của một ứng dụng không tự bảo đảm đã đăng xuất mọi ứng dụng.

### Khi cần xác thực lại hoặc step-up

Một client có thể yêu cầu xác thực gần đây với các tham số OIDC như `max_age` hoặc `prompt=login` tùy yêu cầu. Khi chính sách yêu cầu mức tin cậy cao hơn (chẳng hạn chuyển tiền hoặc thay đổi khóa bảo mật), AS có thể buộc xác thực lại/MFA dù vẫn có phiên SSO.

**Refresh token grant** thường cho phép xin access token mới mà không xác thực người dùng trực tiếp trong lần gọi đó. Nó **không tự tăng độ đảm bảo xác thực** và không thay thế quy trình reauthentication/step-up khi nghiệp vụ yêu cầu.

## 10. Các luồng phát hành token không nhất thiết tạo phiên người dùng

Không nên đồng nhất “cấp access token” với “người dùng vừa đăng nhập bằng browser”.

| Grant/luồng | Cần phiên người dùng? | Tình huống | Lưu ý |
|---|---|---|---|
| **Authorization Code + PKCE** | Thường có sự kiện xác thực người dùng; AS có thể tận dụng phiên SSO trước đó | Web/native login và cấp quyền | Kiểm tra `state`, PKCE, redirect, client và grant |
| **Refresh token grant** | Không cần nhập lại credential người dùng trong lần refresh | Gia hạn quyền truy cập theo phiên/grant còn hiệu lực | Chỉ cấp cho client được phép; rotation/sender constraint và thu hồi theo policy |
| **Client Credentials grant** | **Không có người dùng** | Job backend gọi API nội bộ theo danh tính service | AS xác thực client, cấp token cho quyền của client; không tự dựng `sub` của người dùng |
| **OIDC Authorization Code** | Có bối cảnh xác thực danh tính người dùng | Client cần biết ai đang đăng nhập | AS trả ID token theo OIDC; client xác minh ID token riêng |

Ví dụ **machine-to-machine**:

~~~http
POST /token HTTP/1.1
Host: auth.example.test
Content-Type: application/x-www-form-urlencoded
Authorization: Basic <AUTHENTICATED_CONFIDENTIAL_CLIENT_CREDENTIALS>

grant_type=client_credentials&scope=inventory:read
~~~

Ở đây AS xác thực danh tính **service/client**, kiểm tra scope/policy cho client rồi cấp access token. Không có authorization code, không có trang đăng nhập, không có ID token người dùng và không cần tạo browser session.

Hạn chế dùng các cơ chế yêu cầu client thu thập mật khẩu người dùng để đổi trực tiếp thành token. Với người dùng tương tác, Authorization Code + PKCE là lựa chọn nền tảng phù hợp cho nhiều kiến trúc hiện đại; vẫn phải áp dụng chính sách cụ thể của hệ thống.

## 11. Bảo vệ session establishment và token issuance

Các rủi ro trọng tâm xuất hiện **trước cả khi API nhận được token**.

| Rủi ro | Biểu hiện | Kiểm soát cần có |
|---|---|---|
| **Session fixation** | Attacker khiến nạn nhân dùng session ID đã biết, sau login session ID không đổi | Đổi/luân chuyển session ID khi đăng nhập hoặc tăng quyền; tạo ID ngẫu nhiên |
| **Session hijacking** | Cookie phiên bị lộ do XSS, malware, kết nối kém hoặc log | HTTPS, `Secure`/`HttpOnly`, bảo vệ XSS, giới hạn vòng đời phiên, thu hồi và giám sát |
| **Login CSRF / callback injection** | Client chấp nhận callback của transaction khác | `state` ngẫu nhiên, ràng buộc với browser transaction và kiểm tra trước đổi code |
| **Authorization code interception** | Attacker lấy code qua redirect/history/log | PKCE S256, code ngắn hạn một lần dùng, redirect URI chặt chẽ, không log code |
| **Open redirect** | Code được chuyển qua URI không được phép | Danh sách redirect URI đăng ký và so khớp nghiêm ngặt; không tin `returnUrl` tùy ý |
| **Token substitution / ID token replay** | Client tin ID token không dành cho mình hoặc không khớp login request | Kiểm tra `iss`, `aud`, chữ ký, `exp`, `nonce` khi dùng và transaction |
| **Scope escalation** | AS cấp quyền vượt chính sách người dùng/client | Chỉ cấp scope/audience được phép, kiểm tra consent và ràng buộc grant |
| **Refresh token theft/reuse** | Kẻ tấn công xin access token mới nhiều lần | Lưu refresh token an toàn, rotation/reuse detection hoặc sender constraint khi phù hợp |
| **Mất đồng bộ logout/thu hồi** | App đã logout nhưng token cũ vẫn gọi API | Thu hồi refresh token, chặn access token khi cần, access token ngắn hạn và quy trình logout liên kết nếu có |
| **Lộ credential trong log/trình duyệt** | Code, token, verifier, session cookie xuất hiện tại log/URL | Không log bí mật, cấm gửi token trong query, giảm dữ liệu quan sát và bảo vệ lưu trữ |

Một số điểm vận hành bổ sung:

- **Không mặc định tin response thành công của token endpoint** nếu client chưa xác minh issuer/endpoints theo cấu hình. Chỉ trao đổi với endpoint tin cậy qua TLS.
- **Không quyết định quyền chỉ bằng nội dung ID token**; access token và Resource Server giữ trách nhiệm kiểm tra quyền truy cập API.
- **Không tự nới quyền sau refresh**; AS vẫn phải áp dụng grant, client identity và policy hiện hành.
- **Không cache token response công khai**, không ghi credential hoặc cookie vào telemetry.
- **Thiết lập giới hạn số lần thử, chống replay, khóa/rate limit** tại các điểm xác thực và token endpoint theo loại grant.
- **Bảo vệ khóa ký và vòng quay khóa**, đồng thời cung cấp JWKS/metadata qua nguồn đáng tin cậy để client/API kiểm tra token đúng cách.

## 12. Tình huống thực tế: đăng nhập để xem đơn hàng

Giả sử người dùng Lan muốn xem đơn hàng `ORD-123` trong ứng dụng `orders-web`.

**Lần đầu đăng nhập:**

1. Backend tạo `state`, `nonce`, `code_verifier` và lưu transaction tạm. Browser chuyển tới AS cùng `code_challenge`.
2. AS kiểm tra client/redirect; người dùng xác thực bằng passkey hoặc mật khẩu + MFA tùy chính sách. AS tạo phiên tại miền `auth.example.test`.
3. AS kiểm tra quyền `orders:read`, cấp một authorization code ngắn hạn dùng một lần và redirect về callback đăng ký.
4. Backend kiểm tra `state`, đổi code với `code_verifier`; AS xác minh code/PKCE/client rồi cấp access token cho `orders-api`, ID token cho `orders-web` và refresh token nếu policy cho phép.
5. Backend xác minh ID token, tạo phiên ứng dụng mới và gửi cookie phiên cho browser.
6. Khi backend gọi `GET /orders/ORD-123`, API kiểm tra token đúng issuer, audience, hạn dùng, `orders:read` và **quyền xem đúng đơn hàng** rồi mới trả dữ liệu.

**Những lần truy cập sau:** browser gửi cookie ứng dụng tới backend. Backend có thể dùng access token còn hiệu lực; khi access token hết hạn có thể refresh nếu được phép. Nếu phiên ứng dụng hết hạn nhưng AS còn phiên SSO, ứng dụng có thể bắt đầu authorization flow mới và AS có thể không cần hỏi lại mật khẩu theo policy. Nếu AS yêu cầu `max_age` hoặc MFA mới, người dùng vẫn phải xác thực lại.

### Phân tích 8 tình huống dễ nhầm

| Tình huống | Kết luận và xử lý đúng |
|---|---|
| Người dùng đã có cookie phiên AS, client mới yêu cầu `payments:write` | **Không cấp tự động**. AS kiểm tra client, quyền, consent và policy mới |
| Callback có `code` hợp lệ nhưng `state` không khớp | **Từ chối callback**, không đổi code |
| Attacker có authorization code nhưng không có PKCE verifier | Không được nhận token qua token endpoint khi PKCE được AS thực thi đúng |
| Cùng code được đổi lần thứ hai | **Từ chối** do code một lần dùng |
| ID token có chữ ký đúng nhưng `aud` là client khác | **Từ chối ID token** |
| Access token có `orders:read` nhưng người dùng không sở hữu `ORD-123` | **Từ chối ở API** dù token hợp lệ |
| Phiên AS hết hạn nhưng access token chưa hết hạn | Access token có thể còn sử dụng được cho đến `exp`/thu hồi theo chính sách; phiên AS hết hạn không tự sửa token |
| Dịch vụ dùng `client_credentials` nhận access token | Token đại diện cho **client/service**, không có đăng nhập người dùng để suy ra |

## 13. Checklist triển khai và tự đánh giá

Trước khi đưa luồng đăng nhập và cấp token vào môi trường thật, có thể kiểm tra lần lượt:

1. **Identity:** AS đã xác thực đúng subject, áp dụng MFA/reauthentication khi cần và quản lý mức đảm bảo xác thực chưa?
2. **Session:** Session ID có đủ ngẫu nhiên, có đổi sau đăng nhập, cookie có thuộc tính an toàn, có idle/absolute expiry và logout chưa?
3. **Authorization request:** `client_id`/`redirect_uri` đăng ký chính xác, `state` gắn đúng transaction, PKCE S256 có kiểm tra, `nonce` có dùng đúng theo OIDC chưa?
4. **Code exchange:** code ngắn hạn, chỉ một lần, gắn với client và redirect; token endpoint xác thực confidential client khi cần và kiểm tra verifier chưa?
5. **Issuance policy:** scope và audience có giới hạn theo client, người dùng, consent, resource và policy không? TTL có phù hợp mức rủi ro không?
6. **Token purpose:** API dùng **access token**, client dùng **ID token** cho xác thực OIDC, refresh token chỉ đi tới AS?
7. **Client session:** client xác minh ID token rồi mới tạo phiên, lưu token ở nơi phù hợp, chống CSRF/XSS và không log bí mật chưa?
8. **Kết thúc hiệu lực:** refresh rotation/thu hồi, logout, token expiry và yêu cầu xác thực lại đã được kiểm tra theo kịch bản thực tế chưa?

**Ghi nhớ:** một phiên chứng minh rằng **một hệ thống đã duy trì trạng thái xác thực theo chính sách của nó**; token thể hiện **một quyền hoặc thông tin xác thực được phát hành cho mục đích và người nhận cụ thể**. Ranh giới giữa session establishment và token issuance giúp hệ thống tránh cấp quyền quá mức, nhầm ID token với access token, và tin nhầm một lần đăng nhập cũ cho thao tác cần xác thực lại.

### Tài liệu chuẩn để đọc thêm

- [OAuth 2.0 — RFC 6749](https://www.rfc-editor.org/rfc/rfc6749): authorization framework và các grant nền tảng.
- [PKCE — RFC 7636](https://www.rfc-editor.org/rfc/rfc7636): cơ chế ràng buộc authorization code bằng verifier/challenge.
- [OAuth 2.0 Security Best Current Practice — RFC 9700](https://www.rfc-editor.org/rfc/rfc9700): các hướng dẫn bảo mật hiện đại của OAuth.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): ID token, `nonce`, `auth_time` và xác thực người dùng.
- [OAuth 2.0 Token Revocation — RFC 7009](https://www.rfc-editor.org/rfc/rfc7009), [Token Introspection — RFC 7662](https://www.rfc-editor.org/rfc/rfc7662): quản lý trạng thái/thu hồi token.
- [JWT Access Token Profile — RFC 9068](https://www.rfc-editor.org/rfc/rfc9068): profile dành cho JWT access token.
- [OWASP Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html): bảo vệ session ID, cookie và vòng đời phiên.
