# Token được tạo, truyền, kiểm tra và hết hạn

Trong hệ thống dùng **OAuth 2.0/OIDC**, token là một loại thông tin xác thực hoặc ủy quyền được cấp trong một phạm vi và khoảng thời gian nhất định. Khi client gọi API, server cần xác định **ai đã cấp token, token dành cho ai, được dùng để làm gì, còn hiệu lực hay không**. Việc nhận được một chuỗi trông giống JWT không đủ để kết luận yêu cầu đáng tin cậy.

Bài này đi theo toàn bộ vòng đời của token: **phát hành → truyền đến bên sử dụng → kiểm tra → sử dụng → hết hạn, làm mới hoặc thu hồi**. Trọng tâm là access token, refresh token, JWT và opaque token trong ứng dụng web, mobile và các API.

## 1. Các vai trò và ranh giới tin cậy

| Thành phần | Vai trò | Điều cần tin cậy |
|---|---|---|
| **Resource owner / người dùng** | Đăng nhập và có thể chấp thuận quyền truy cập | Việc đăng nhập do hệ thống định danh kiểm soát; không gửi mật khẩu cho API nghiệp vụ chỉ để dùng access token |
| **Client** | Ứng dụng web, mobile hoặc backend gọi API | Nhận và bảo vệ token theo khả năng bảo mật của loại client |
| **Authorization Server (AS)** | Xác thực người dùng, xử lý cấp quyền, phát hành token; trong OIDC còn đóng vai trò OpenID Provider | Là bên phát hành được các thành phần liên quan cấu hình tin cậy |
| **Resource Server (API)** | Nhận access token và bảo vệ tài nguyên | Phải tự xác minh token, kiểm tra quyền và quyền sở hữu dữ liệu |
| **Kho khóa / introspection endpoint** | Cung cấp khóa công khai để xác minh JWT hoặc trạng thái opaque token | Đến từ đúng AS, qua kết nối được xác thực và cấu hình trước |

Ví dụ, hệ thống có `https://auth.example.test` để phát hành token và `https://api.example.test` phục vụ đơn hàng. API chỉ được chấp nhận access token do issuer đã cấu hình cấp **cho chính API này**, không phải bất kỳ JWT nào có chữ ký hợp lệ từ một nơi bất kỳ.

**Bearer token** là token mà người đang nắm giữ có thể dùng để yêu cầu quyền truy cập, miễn đáp ứng các điều kiện của server. Vì vậy, đánh cắp bearer token có thể tương đương đánh cắp khả năng truy cập trong thời gian token còn hiệu lực. Một số hệ thống tăng bảo vệ bằng **sender-constrained token** như DPoP hoặc mTLS, ràng buộc việc sử dụng token với bằng chứng sở hữu khóa.

## 2. Phân biệt mục đích token và định dạng token

Hai câu hỏi sau là độc lập:

- **Token dùng để làm gì?** Access token, refresh token và ID token có mục đích khác nhau.
- **Token được biểu diễn như thế nào?** JWT hoặc opaque là những cách biểu diễn/kiểm tra khác nhau. Một access token có thể là JWT **hoặc** opaque token.

| Loại | Ai dùng và dùng để làm gì? | Điểm cần nhớ |
|---|---|---|
| **Access token** | Client gửi cho Resource Server để gọi API được phép | API kiểm tra issuer, audience, hiệu lực và quyền; thời hạn thường ngắn |
| **Refresh token** | Client gửi tới token endpoint của AS để xin access token mới | Không gửi làm Bearer để truy cập API nghiệp vụ; cần bảo vệ chặt, có thể bị luân phiên và thu hồi |
| **ID token (OIDC)** | Client/Relying Party dùng để nhận thông tin về sự kiện xác thực và danh tính người dùng | Thường là JWT; `aud` thường là client ID, **không thay thế access token** khi gọi API |
| **JWT (JSON Web Token)** | Định dạng chứa claims dưới dạng JSON, thường được bảo vệ bằng JWS | Có thể kiểm tra chữ ký tại API khi cấu hình đúng; payload JWT ký **không được mã hóa mặc định** |
| **Opaque token** | Chuỗi không mang cấu trúc claims mà client/API có thể tự đọc đáng tin cậy | API thường hỏi AS qua introspection hoặc tra cứu trạng thái do hệ thống tin cậy quản lý |

Ví dụ: hai access token cùng có quyền `orders:read`, cùng hết hạn sau 10 phút, nhưng một token là JWT có chữ ký và token còn lại là chuỗi ngẫu nhiên. Sự khác biệt định dạng quyết định **cách kiểm tra**, không tự quyết định **quyền truy cập**.

> **Phân biệt thêm:** JWT có thể được ký (JWS) hoặc mã hóa (JWE); mẫu JWT ký phổ biến gồm `header.payload.signature`. Base64url decode chỉ giúp đọc dữ liệu, **không chứng minh** dữ liệu do issuer đáng tin cậy phát hành. Muốn tin claims, phải dùng quy trình xác minh phù hợp với loại token.

## 3. Dòng chảy tạo, truyền và sử dụng token

Một luồng phổ biến cho ứng dụng tương tác với người dùng là **OAuth 2.0 Authorization Code + PKCE**; OIDC bổ sung khả năng xác thực danh tính. Sơ đồ sau lược bỏ một số chi tiết như redirect URI, cookie phiên đăng nhập tại AS và cơ chế lưu token riêng của từng client:

~~~mermaid
sequenceDiagram
    autonumber
    actor U as Người dùng
    participant C as Client
    participant AS as Authorization Server
    participant API as Resource Server

    U->>C: Muốn xem đơn hàng
    C->>AS: Yêu cầu ủy quyền (scope, state, PKCE challenge)
    AS->>U: Xác thực và xin chấp thuận khi cần
    AS-->>C: Authorization code qua redirect
    C->>AS: Đổi code + PKCE verifier tại token endpoint
    AS-->>C: Access token (+ refresh token, ID token nếu áp dụng)
    C->>API: HTTPS + Authorization: Bearer access_token
    API->>API: Kiểm tra token, quyền và tài nguyên
    API-->>C: 200 và dữ liệu được phép
    Note over C,API: Sau khi access token hết hạn
    C->>AS: Refresh token grant (nếu được cấp)
    AS-->>C: Access token mới (+ refresh token mới nếu rotation)
    C->>API: Gọi lại với access token mới
~~~

**Mỗi mũi tên đi qua một ranh giới tin cậy:**

1. Client bắt đầu luồng ủy quyền, tạo `state` để bảo vệ callback và dùng PKCE (`code_challenge`/`code_verifier`, thường với phương thức S256) để bảo vệ authorization code. Chỉ sau khi AS xác thực và chấp nhận yêu cầu mới có code.
2. Client đổi code tại token endpoint. Authorization code **không phải access token**; nó có thời hạn ngắn, dùng một lần và gắn với yêu cầu ủy quyền tương ứng.
3. AS kiểm tra client, code, redirect URI, PKCE và chính sách trước khi phát hành token phù hợp. Refresh token và ID token **không phải lúc nào cũng được trả về**; ID token gắn với OIDC.
4. Client truyền **access token** đến API qua HTTPS. API tự xác minh thông tin ủy quyền trước khi truy cập dữ liệu.
5. Khi access token không còn hiệu lực, client cần nhận token mới bằng cơ chế được phép hoặc bắt đầu lại luồng đăng nhập/ủy quyền; không thể tự sửa `exp` trong token rồi dùng tiếp.

### Access token được tạo như thế nào?

AS thường quyết định các thuộc tính của token dựa trên user/session, client, quyền đã được phép, policy của API, thời điểm cấp và thời điểm hết hạn. Với JWT ký, có thể hình dung header và payload qua hai khối JSON minh họa sau:

~~~json
{
  "alg": "RS256",
  "typ": "at+jwt",
  "kid": "key-2026-11"
}
~~~

~~~json
{
  "iss": "https://auth.example.test",
  "sub": "user-42",
  "aud": "https://api.example.test",
  "client_id": "orders-web",
  "scope": "orders:read",
  "iat": 1800000000,
  "nbf": 1800000000,
  "exp": 1800000600,
  "jti": "at-73f9c2"
}
~~~

Hai khối trên chưa phải token có thể sử dụng: token thực được AS tạo và ký, còn các giá trị thời gian chỉ minh họa theo Unix seconds. Kiểu `typ: at+jwt` là ví dụ về khai báo loại access token theo một profile; các hệ thống không nhất thiết dùng cùng profile hoặc cùng tên claim.

| Claim / header | Ý nghĩa | API hoặc client dùng ra sao? |
|---|---|---|
| `iss` | Issuer, nguồn phát hành | Chỉ chấp nhận issuer đã cấu hình tin cậy |
| `sub` | Subject, chủ thể | Dùng làm dữ liệu định danh theo ngữ cảnh issuer; vẫn kiểm tra quyền truy cập từng tài nguyên |
| `aud` | Audience, đối tượng nhận | API yêu cầu audience dành cho chính nó; không dùng token cấp cho API khác |
| `exp` | Thời điểm hết hạn | Hết hạn khi thời gian hiện tại đạt hoặc vượt `exp`, trừ độ lệch đồng hồ nhỏ được cấu hình |
| `nbf` / `iat` | Không có hiệu lực trước lúc nào / thời điểm cấp | Kiểm tra hiệu lực theo thời gian và tính hợp lý; không lấy `iat` thay cho `exp` |
| `scope` hoặc `scp` | Quyền được cấp theo quy ước AS | Kiểm tra đúng quyền endpoint yêu cầu; không tự suy ra quyền không có |
| `client_id` hoặc `azp` | Client được cấp / bên được ủy quyền, tùy profile | Dùng khi chính sách API hoặc profile yêu cầu |
| `jti` | Định danh riêng của JWT nếu có | Có thể hỗ trợ truy vết, phát hiện replay hoặc denylist theo thiết kế hệ thống |
| `alg` / `kid` | Thuật toán chữ ký / định danh khóa | Thuật toán phải nằm trong allowlist; chỉ tra khóa trong nguồn đã tin cậy |

Tên `scope`, `scp` và các claim ngoài chuẩn phụ thuộc AS/profile. API phải bám theo **hợp đồng token** đã thống nhất. Dữ liệu claims là đầu vào cho quyết định bảo mật, không phải mọi claim tự động tương đương với một quyền.

**Chữ ký JWT** giúp Resource Server phát hiện nội dung bị sửa và xác nhận token được ký bằng khóa tương ứng với issuer được tin cậy. Chữ ký không có nghĩa payload bí mật: tránh đưa mật khẩu, token khác, dữ liệu nhạy cảm không cần thiết hoặc thông tin riêng tư quá chi tiết vào payload có thể bị đọc.

## 4. Truyền token an toàn giữa các thành phần

Với Bearer access token, cách truyền thông dụng là HTTP header:

~~~http
GET /orders/123 HTTP/1.1
Host: api.example.test
Authorization: Bearer <ACCESS_TOKEN>
Accept: application/json
~~~

Gói tin thực tế phải được truyền qua **HTTPS** và kết nối cần được xác thực phù hợp. API trích đúng token từ header theo quy ước, sau đó kiểm tra trước khi xử lý tài nguyên.

Những điểm thực hành quan trọng:

- **Không đưa access token/refresh token vào URL query** như `?access_token=...`. URL dễ xuất hiện trong log, lịch sử truy cập, thông tin phân tích và header referrer.
- **Không ghi token nguyên văn vào log**, thông báo lỗi, hệ thống theo dõi lỗi hoặc analytics. Nếu cần đối chiếu sự kiện, dùng request ID hoặc mã token đã giảm rủi ro lộ bí mật.
- **Không truyền refresh token cho API nghiệp vụ.** Refresh token chỉ dành cho token endpoint của AS, trừ một thiết kế đặc biệt đã được định nghĩa rõ.
- **Không mặc định cookie đồng nghĩa với Bearer header.** Nếu backend dùng cookie để duy trì phiên hoặc giữ token phía server, cookie nên có `Secure`, `HttpOnly`, `SameSite` phù hợp và giải pháp chống CSRF cho các thao tác thay đổi trạng thái. Cookie `HttpOnly` giảm khả năng JavaScript đọc token, nhưng XSS vẫn có thể phát sinh thao tác dưới phiên người dùng.
- **CORS không thay thế kiểm tra token và phân quyền.** CORS kiểm soát khả năng trình duyệt đọc phản hồi cross-origin; API phải tự bảo vệ yêu cầu dù client không phải trình duyệt.

### Nên lưu token ở đâu?

| Môi trường | Hướng tiếp cận | Lý do |
|---|---|---|
| Web dùng Backend-for-Frontend (BFF) | Giữ token phía backend; browser giữ cookie phiên an toàn | Giảm khả năng mã JavaScript truy cập trực tiếp token |
| Browser SPA không có BFF | Ưu tiên lưu access token trong bộ nhớ; thiết kế rõ cách duy trì phiên và refresh an toàn | `localStorage`/`sessionStorage` có thể bị JavaScript đọc nếu XSS; bộ nhớ cũng không loại bỏ hoàn toàn tác hại XSS |
| Native mobile | Dùng Keychain/Keystore hoặc cơ chế lưu bí mật an toàn của hệ điều hành | Hạn chế lộ token từ vùng lưu thông thường |
| Backend / service-to-service | Lưu credential, khóa và token trong môi trường quản lý bí mật, giới hạn quyền truy cập | Tránh đưa dữ liệu nhạy cảm vào source code, log hoặc file cấu hình công khai |

Không có nơi lưu token nào bù được cho mọi lỗi XSS, cấu hình CORS, đánh cắp thiết bị hay quyền backend quá rộng. Cần kết hợp thời hạn, scope tối thiểu, bảo vệ phiên và giám sát bất thường.

## 5. Resource Server kiểm tra access token

Quy trình kiểm tra phải phù hợp với **định dạng token** và hợp đồng của AS.

### 5.1. Với access token là JWT đã ký

API thực hiện kiểm tra theo thứ tự hợp lý:

1. **Trích token đúng vị trí** và từ chối yêu cầu thiếu, sai định dạng hoặc không được hỗ trợ.
2. **Đọc cấu trúc để xác định cách xác minh**, nhưng chưa tin bất kỳ claim nào. Chỉ cho phép các thuật toán chữ ký đã cấu hình; không chấp nhận `alg: none` hoặc đổi thuật toán theo đề nghị của đầu vào không đáng tin cậy.
3. **Xác minh chữ ký** bằng khóa đúng của issuer được tin cậy. Nếu AS công bố JWKS, API phải lấy từ địa chỉ đã cấu hình và kiểm soát cache/rotation. `kid` chỉ được dùng chọn một khóa trong tập tin cậy, không phải lý do tự động truy cập một URL tùy ý từ header.
4. **Kiểm tra ngữ cảnh token:** `iss` chính xác, `aud` có API này, loại token/profile phù hợp, `exp` chưa hết, `nbf` đã đến và các điều kiện khác do hợp đồng đặt ra. Chỉ cho phép khoảng clock skew nhỏ nếu cần.
5. **Kiểm tra quyền:** token có scope/role cần thiết, client/tenant phù hợp và người dùng được thao tác trên **đúng đối tượng dữ liệu**.
6. **Áp dụng yêu cầu trạng thái bổ sung** nếu hệ thống cần phát hiện token bị thu hồi hoặc replay (ví dụ denylist, trạng thái phiên hoặc sender constraint).

Pseudocode minh họa (tên hàm mang tính khái niệm, không phải API của một thư viện cụ thể):

~~~text
function authorizeGetOrder(httpRequest, orderId):
    bearer = readBearerFromAuthorizationHeader(httpRequest)
    if bearer is missing:
        return 401

    claims = validateSignedAccessJwt(
        bearer,
        trustedIssuer = "https://auth.example.test",
        expectedAudience = "https://api.example.test",
        allowedAlgorithms = ["RS256"],
        trustedIssuerKeySet = configuredJWKS,
        smallClockSkew = 30_seconds
    )
    if claims invalid or tokenType not accepted:
        return 401

    if "orders:read" not in grantedScopes(claims):
        return 403

    order = loadOrder(orderId)
    if order does not exist:
        return 404

    if not canReadThisOrder(claims.sub, order, claims):
        return 403

    return 200, order
~~~

Hàm `canReadThisOrder` rất quan trọng. Một token có `orders:read` không tự động cho phép đọc **mọi đơn hàng của mọi người dùng**. API vẫn cần kiểm tra quan hệ chủ sở hữu, tenant hoặc chính sách ở cấp bản ghi.

**Không thực hiện kiểu kiểm tra sai sau:**

~~~text
payload = base64urlDecode(token.middlePart)
if payload.exp > now:
    allowRequest()
~~~

Cách làm này tin payload chưa xác minh chữ ký, issuer, audience, loại token và quyền; kẻ tấn công có thể tự tạo chuỗi có claims mong muốn.

### 5.2. Với access token là opaque token

Opaque token không có claims để API tự đọc và kiểm tra trực tiếp. Một phương án thông dụng là API gọi **token introspection endpoint** của AS, dùng kết nối an toàn và thông tin xác thực server-to-server:

~~~http
POST /oauth2/introspect HTTP/1.1
Host: auth.example.test
Content-Type: application/x-www-form-urlencoded
Authorization: Basic <CREDENTIALS_FOR_AUTHENTICATED_RESOURCE_SERVER>

token=<OPAQUE_ACCESS_TOKEN>&token_type_hint=access_token
~~~

Phản hồi minh họa khi token còn hiệu lực:

~~~json
{
  "active": true,
  "iss": "https://auth.example.test",
  "sub": "user-42",
  "aud": "https://api.example.test",
  "scope": "orders:read",
  "client_id": "orders-web",
  "exp": 1800000600
}
~~~

API chỉ tiếp tục nếu `active` là `true` **và** kết quả đáng tin cậy, dành cho chính API, chứa quyền cần thiết; các trường thực tế phụ thuộc AS. Một phản hồi `active: false` đồng nghĩa không được cấp quyền truy cập theo token đó. Introspection không thay thế kiểm tra quyền trên từng tài nguyên.

Caching kết quả introspection có thể giảm độ trễ nhưng làm việc thu hồi bớt tức thời: token đã bị thu hồi có thể vẫn được dùng cho đến khi cache hết hạn. Nếu cache, giới hạn TTL theo chính sách và **không vượt thời điểm `exp`**.

### 5.3. Tránh nhầm ID token và access token

OIDC ID token mô tả việc xác thực người dùng **cho client**. Client phải xác minh ID token theo quy tắc OIDC tương ứng (bao gồm issuer, audience/client ID, chữ ký, thời gian và `nonce` nếu đã sử dụng). API nghiệp vụ **không** chấp nhận ID token thay cho access token chỉ vì ID token có `sub` và chữ ký hợp lệ.

Ví dụ: ID token có `aud: "orders-web"`, còn API đặt expected audience là `https://api.example.test`. Kể cả cả hai token cùng do `auth.example.test` cấp, mỗi token vẫn có người nhận và mục đích khác nhau.

### 5.4. Phản hồi khi kiểm tra thất bại

| Tình huống | Phản hồi thường phù hợp | Hành vi client |
|---|---|---|
| Thiếu, không hợp lệ, bị thu hồi hoặc access token hết hạn | `401 Unauthorized`; có thể kèm `WWW-Authenticate: Bearer` và mã lỗi thích hợp | Xem có thể xin token mới hợp lệ hay cần đăng nhập lại |
| Token hợp lệ nhưng thiếu quyền `orders:read` | `403 Forbidden`, có thể thông báo `insufficient_scope` | Không refresh lặp vô hạn; cần quyền thực sự được cấp |
| Token hợp lệ và đủ scope nhưng người dùng không sở hữu đơn hàng | `403` hoặc `404` theo chính sách tránh tiết lộ tài nguyên | Không được coi đây là lỗi hết hạn token |
| AS/JWKS/introspection tạm thời không khả dụng | Xử lý lỗi hạ tầng theo chính sách an toàn, không mặc định cho qua | Có thể retry với backoff nếu phù hợp, tránh vòng lặp |

Không được tiết lộ token hay thông tin bí mật trong thông báo lỗi. Cần phân biệt lỗi **xác thực** (token không dùng được) và lỗi **phân quyền** (token đã xác thực nhưng không có quyền).

## 6. Khi access token hết hạn

Access token thường có tuổi thọ ngắn để giảm thời gian có thể bị lạm dụng nếu rò rỉ. Ví dụ minh họa một chính sách cấp access token hiệu lực 10 phút:

~~~text
10:00  AS phát hành access token, iat = 10:00, exp = 10:10
10:03  Client gọi API -> token còn hiệu lực, kiểm tra quyền
10:09  Client có thể chủ động xin token mới nếu chính sách cho phép
10:10  Token đạt exp -> API từ chối token cũ (trừ clock skew nhỏ)
10:11  Client dùng access token mới đã được cấp để tiếp tục gọi API
~~~

Các thời hạn 10 phút, khoảng gia hạn sớm và clock skew là **ví dụ**, không phải một tiêu chuẩn áp dụng cho mọi hệ thống. Giá trị thực tế tùy mức rủi ro, nhu cầu trải nghiệm và chính sách phiên.

Một số nguyên tắc:

- `exp` là thời điểm hết hạn tuyệt đối của **token cụ thể**, không được kéo dài bằng cách phía client sửa payload.
- Chỉ một độ lệch đồng hồ nhỏ, được cấu hình rõ ràng, mới nên được dung sai; không biến leeway thành nhiều phút để né chính sách hết hạn.
- Một API vẫn phải từ chối token quá hạn ngay cả khi request đến từ client đã từng gọi thành công.
- `401` không luôn đồng nghĩa token hết hạn: còn có chữ ký sai, sai issuer, sai audience hoặc token bị thu hồi. Client nên xử lý chính xác nguyên nhân và giới hạn số lần thử lại.

## 7. Refresh token và luân phiên token

Khi được AS cấp refresh token và client được phép sử dụng grant này, client có thể gửi refresh token tới **token endpoint** để nhận access token mới mà không cần người dùng đăng nhập lại mỗi lần access token hết hạn.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant AS as Authorization Server
    C->>AS: Refresh token RT1
    AS->>AS: Kiểm tra RT1, client và session/policy
    AS-->>C: Access token AT2 và refresh token RT2
    Note over C,AS: RT1 bị vô hiệu nếu áp dụng refresh token rotation
    C->>AS: Refresh token RT2
    AS-->>C: Access token AT3 và refresh token RT3
~~~

**Refresh token rotation** là cơ chế thay refresh token cũ bằng token mới sau một lần dùng thành công. Khi AS phát hiện refresh token đã dùng lại bất thường, chính sách có thể vô hiệu hóa cả chuỗi token/phiên liên quan để hạn chế lạm dụng. Việc này đặc biệt hữu ích với public client không có khả năng giữ client secret an toàn.

Những trường hợp cần xử lý:

- **Nhiều request cùng gặp hết hạn:** client nên phối hợp để tránh đồng thời gửi cùng refresh token một lần dùng, vì có thể gây lỗi hoặc kích hoạt phát hiện reuse.
- **Refresh thất bại với `invalid_grant`:** token có thể hết hạn, bị thu hồi, không hợp lệ hoặc đã bị thay thế; xóa trạng thái token không còn dùng được và bắt đầu đăng nhập/ủy quyền mới khi cần.
- **Refresh token cũng có thời hạn/chính sách phiên:** gia hạn access token không có nghĩa người dùng được đăng nhập vĩnh viễn.
- **Refresh token bị lộ nguy hiểm hơn access token ngắn hạn:** kẻ tấn công có thể cố xin nhiều access token mới, nên cần lưu trữ an toàn, rotation hoặc sender constraint theo khả năng và chính sách AS.

## 8. Thu hồi, đăng xuất và thay đổi quyền

**Hết hạn** và **thu hồi** là hai sự kiện khác nhau. Hết hạn dựa trên thời gian ghi trong token hoặc trạng thái server; thu hồi xảy ra khi AS/ứng dụng quyết định chấm dứt hiệu lực trước thời hạn, chẳng hạn người dùng đăng xuất, đổi mật khẩu, mất thiết bị hoặc quyền bị gỡ.

| Cơ chế kiểm tra | Thu hồi có thể có hiệu lực thế nào? | Giới hạn |
|---|---|---|
| **Opaque + introspection/tra trạng thái** | AS có thể báo `active: false` ngay sau khi thu hồi | Cache tại API có thể trì hoãn hiệu lực |
| **JWT tự xác minh hoàn toàn (stateless)** | Chữ ký vẫn hợp lệ tới `exp`; token không tự biết đã đăng xuất | Muốn dừng trước hạn cần denylist, kiểm tra session/version, phân phối sự kiện hoặc thời hạn ngắn |
| **Refresh token có trạng thái** | AS có thể từ chối lần refresh tiếp theo và vô hiệu hóa phiên liên quan | Access token đã phát hành có thể còn dùng được cho đến khi bị chặn/hết hạn |
| **Sender-constrained token** | Khó sử dụng token bị sao chép khi không có bằng chứng sở hữu khóa | Không thay thế hoàn toàn chính sách hết hạn và thu hồi |

Một thao tác **logout** an toàn thường cần hủy phiên ứng dụng, xóa thông tin xác thực phía client và yêu cầu AS thu hồi refresh token khi hỗ trợ. Nhưng xóa token khỏi trình duyệt **không làm một bản sao token đã bị đánh cắp tự biến mất**. Tương tự, thay đổi quyền người dùng trên cơ sở dữ liệu không tự sửa scope nằm trong JWT đã cấp; API phải chọn chính sách cập nhật quyền/kiểm tra trạng thái phù hợp yêu cầu thu hồi.

## 9. Những rủi ro thường gặp và cách giảm thiểu

| Rủi ro | Cách xảy ra | Biện pháp chính |
|---|---|---|
| **Đánh cắp token** | XSS, log, URL, thiết bị bị xâm nhập, lưu trữ kém | HTTPS, lưu token an toàn, không log bí mật, access token ngắn hạn, scope tối thiểu |
| **Replay** | Kẻ tấn công dùng lại Bearer token hoặc refresh token bị lộ | Refresh rotation/reuse detection, DPoP/mTLS khi áp dụng, phát hiện bất thường |
| **Token confusion** | Đưa ID token hoặc token của API A tới API B | Kiểm tra loại token, `iss`, `aud`, profile và quyền |
| **JWT giả mạo / lỗi xác minh** | Chỉ decode, chấp nhận thuật toán không an toàn, tin `jku` tùy ý | Xác minh chữ ký bằng khóa/thuật toán cấu hình tin cậy, kiểm tra claims |
| **Quyền quá rộng** | Scope vượt nhu cầu, hoặc thiếu kiểm tra chủ sở hữu object | Least privilege, kiểm tra phân quyền theo endpoint và bản ghi |
| **Authorization code bị chặn/đánh tráo** | Callback thiếu liên kết với yêu cầu ban đầu | Authorization Code + PKCE S256, kiểm tra `state` và redirect URI chính xác |
| **CSRF khi dùng cookie** | Browser tự đính kèm cookie cho request ngoài ý muốn | `SameSite` phù hợp, CSRF token/kiểm tra nguồn yêu cầu, chống XSS |
| **Sai lệch đồng hồ/khóa hết hiệu lực** | API từ chối nhầm hoặc chấp nhận token không nên chấp nhận | Đồng bộ thời gian, skew tối thiểu, JWKS rotation có kiểm soát |

Một bearer token thường chỉ thể hiện **khả năng truy cập đã được cấp**. Nó không chứng minh người đang gửi token chính là chủ tài khoản hay vẫn ở trên thiết bị ban đầu. Nếu hệ thống có yêu cầu cao như giao dịch tài chính hoặc thao tác quản trị, cần cân nhắc kiểm tra phiên, xác thực lại, xác thực nhiều yếu tố hoặc kiểm soát theo từng giao dịch.

## 10. Ví dụ thực tế: xem đơn hàng từ đầu đến cuối

Giả sử một người dùng mở ứng dụng mua hàng, đăng nhập qua AS và muốn xem đơn hàng `123`.

**Bước 1 — Phát hành.** Client dùng Authorization Code + PKCE để hoàn tất luồng ủy quyền. AS phát hành access token cho `https://api.example.test` với `scope: "orders:read"` và hạn dùng ngắn. Nếu chính sách cho phép, AS cũng cấp refresh token cho client.

**Bước 2 — Truyền.** Client gọi `GET https://api.example.test/orders/123` qua HTTPS, gửi access token trong header `Authorization: Bearer ...`.

**Bước 3 — Kiểm tra.** API xác minh JWT hoặc introspect opaque token; kiểm tra issuer, audience, thời gian, quyền `orders:read`, sau đó tra đơn hàng. Dù access token hợp lệ, API chỉ trả dữ liệu khi người dùng được phép xem đơn hàng `123`.

**Bước 4 — Hết hạn.** Sau khi access token hết hiệu lực, API có thể phản hồi `401`. Client được cấu hình để xin token mới theo quy định AS; client không tự gia hạn bằng cách sửa claims.

**Bước 5 — Luân phiên và thu hồi.** Nếu refresh token rotation được bật, client dùng RT1 một lần và nhận RT2. Khi người dùng đăng xuất hoặc AS nghi ngờ RT1 bị phát lại, AS có thể thu hồi token/phiên liên quan. API phải xử lý thời điểm thu hồi access token dựa trên cơ chế mà hệ thống đã triển khai, đặc biệt nếu access token là JWT tự kiểm tra.

### Thử suy luận qua các tình huống

| Tình huống | Kết luận |
|---|---|
| JWT có chữ ký đúng nhưng `aud` là API thanh toán, request lại đến API đơn hàng | **Từ chối**: sai audience |
| JWT được decode và thấy `sub` hợp lệ, nhưng chữ ký chưa xác minh | **Từ chối**: payload chưa đáng tin |
| Access token hợp lệ, có `orders:read` nhưng đơn hàng thuộc người dùng khác | **Từ chối**: thiếu quyền trên tài nguyên |
| Access token hết hạn, refresh token còn hợp lệ | **Có thể** xin access token mới tại AS, theo policy của client và AS |
| Client xóa access token khỏi bộ nhớ, kẻ tấn công vẫn giữ bản sao token cũ | Bản sao có thể tiếp tục hoạt động tới khi hết hạn hoặc bị chặn bằng cơ chế thu hồi phù hợp |
| Cùng một refresh token đã rotation được gửi lại | AS có thể coi là reuse/replay và từ chối, thậm chí thu hồi chuỗi phiên tùy chính sách |

## 11. Checklist triển khai và ghi nhớ

Trước khi đưa một API được bảo vệ bằng token vào sử dụng, cần xác nhận:

1. **Token đúng mục đích:** access token cho API; ID token cho OIDC client; refresh token chỉ đi tới AS.
2. **Đúng nơi phát hành và người nhận:** issuer và audience được cấu hình cụ thể; API không tin claims chưa được xác minh.
3. **Đúng thời gian:** luôn kiểm tra `exp`, `nbf` nếu có, đồng bộ đồng hồ và giới hạn skew.
4. **Đúng quyền:** kiểm tra scope/role và quyền trên từng tài nguyên; không cấp quyền chỉ nhờ `sub`.
5. **Đúng cách truyền và lưu:** HTTPS, header phù hợp, không đưa token vào URL/log, bảo vệ token theo loại client.
6. **Đúng cách kết thúc phiên:** xử lý refresh rotation, lỗi refresh, logout, revocation và khoảng trễ thu hồi của access token.
7. **Đúng cách vận hành:** xoay khóa ký có kiểm soát, theo dõi lỗi xác minh, phát hiện lạm dụng, tránh retry/refresh vô hạn.

**Ý chính cần nhớ:** token chỉ có giá trị trong **mô hình tin cậy cụ thể** gồm issuer, người nhận, mục đích, quyền, thời gian và trạng thái. Một token được tạo đúng mà truyền/lưu sai vẫn có thể bị đánh cắp; một token được truyền an toàn mà API kiểm tra thiếu `aud` hoặc quyền trên tài nguyên vẫn có thể dẫn đến truy cập trái phép.
