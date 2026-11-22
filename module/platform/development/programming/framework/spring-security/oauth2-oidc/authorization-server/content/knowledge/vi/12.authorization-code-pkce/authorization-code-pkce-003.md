# Ràng buộc code với client và redirect_uri

> **Chương:** Authorization Code và PKCE  
> **Module:** `SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER`  
> **Phạm vi:** Thiết kế, cấu hình, bảo mật, kiểm thử và vận hành OAuth 2.0/OpenID Connect Authorization Server bằng Spring Security và Spring Authorization Server trong Spring Boot.  
> **Phiên bản minh họa:** Spring Boot 3.x, Spring Security 6.x và Spring Authorization Server 1.x (Servlet stack). Với Spring Security 7.x, hãy đối chiếu API, starter và tài liệu của chính phiên bản đang sử dụng.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích tại sao một **authorization code** phải gắn với **client cụ thể** và **redirect URI đã xác minh**.
2. Phân biệt ràng buộc `client_id`, xác thực confidential client và bằng chứng PKCE `code_verifier`.
3. Mô tả cách kiểm tra hai chặng `GET /oauth2/authorize` và `POST /oauth2/token`, bao gồm các trường hợp không khớp tham số.
4. Hiểu thông tin Spring Authorization Server lưu trong `OAuth2Authorization` và cách `RegisteredClientRepository` phối hợp với `OAuth2AuthorizationService`.
5. Cấu hình `RegisteredClient` cho confidential client và public client, bật PKCE, đặt redirect URI và thời hạn authorization code.
6. Thiết kế test cho code bị dùng lại, dùng sai client, sai redirect URI, sai verifier và callback không đáng tin cậy.

**Ý chính:** Authorization code không phải một “vé đổi token” có thể mang sang client bất kỳ. Code chỉ có thể được sử dụng theo **đúng điều kiện mà Authorization Server (AS) đã ghi nhận khi cấp code**.

## 2. Authorization code mang ý nghĩa gì?

Ở Authorization Code Grant, Resource Owner đăng nhập vào AS và chấp thuận quyền cho OAuth2 Client (nếu chính sách yêu cầu). AS phát hành một authorization code **ngắn hạn, chỉ sử dụng một lần** thông qua callback đã được đăng ký.

Client nhận code rồi gọi token endpoint để yêu cầu access token và, nếu là luồng OpenID Connect hợp lệ, có thể nhận ID token. Việc client sở hữu chuỗi code **chưa đủ** để AS phát token; AS còn phải kiểm tra code đó được cấp cho client nào, redirect URI nào, đã hết hạn/chưa được dùng và có đáp ứng PKCE hay không.

Một mô hình dễ nhớ:

~~~mermaid
flowchart TD
    AR["Authorization request<br/>client_id + redirect_uri + code_challenge"]
    CR["RegisteredClient<br/>client_id + redirectUris + grantTypes"]
    UA["User đã xác thực<br/>Consent / authorizedScopes"]
    AO["OAuth2Authorization được lưu<br/>registeredClientId + code + metadata"]
    CODE["Authorization code gửi qua redirect"]
    TR["Token request<br/>code + redirect_uri + code_verifier<br/>+ client authentication nếu cần"]
    CHECK{"AS kiểm tra tất cả<br/>ràng buộc"}
    TOK["Cấp token"]
    DENY["Từ chối: không cấp token"]

    AR --> CHECK
    CR --> CHECK
    UA --> CHECK
    CHECK -->|"Cấp code đúng điều kiện"| AO
    AO --> CODE
    CODE --> TR
    TR --> CHECK
    AO --> CHECK
    CHECK -->|"Mọi điều kiện đổi code hợp lệ"| TOK
    CHECK -->|"Sai hoặc code đã dùng"| DENY
~~~

Sơ đồ gom hai chặng authorize và token vào cùng một nút kiểm tra cho dễ nhìn; **mỗi chặng có bộ kiểm tra riêng**. AS không phát access token ngay từ callback authorization code.

### 2.1. Bốn thông tin cần gắn với code

| Thông tin | Mục đích | Kiểm tra quan trọng |
| --- | --- | --- |
| **Client** | Code được cấp cho ứng dụng nào? | Client tại token endpoint phải là client đã được cấp code |
| **Redirect URI** | Callback nào đã được AS chấp nhận khi tạo authorization request? | Giá trị `redirect_uri` ở token request phải khớp với giá trị trong authorization request khi tham số đó được gửi |
| **PKCE challenge** | Client nào đang giữ `code_verifier` tương ứng? | `S256(code_verifier)` phải khớp với `code_challenge` đã gắn với code |
| **Trạng thái code** | Code có còn được dùng không? | Chưa hết hạn, chưa được đổi token, chưa bị vô hiệu hóa; tiêu thụ theo ngữ nghĩa một lần |

AS còn gắn trạng thái authorization với Resource Owner, scopes đã cấp, grant type và các metadata cần cho token endpoint. Không coi một authorization code là dữ liệu tự khai của client có thể tự giải mã rồi tin cậy.

## 3. Toàn bộ luồng ràng buộc từ authorize tới token

Giả định hệ thống gồm:

- **Resource Owner:** Lan.
- **Confidential Client:** backend `booking-bff`.
- **AS:** `https://auth.example.test`.
- **Callback đã đăng ký:** `https://app.example.test/login/oauth2/code/booking-bff`.
- **Resource Server:** `booking-api`, nhận access token sau khi quá trình đổi code thành công.

Tên miền `.example.test` và client ID dùng để minh họa; không phải endpoint đang hoạt động.

~~~mermaid
sequenceDiagram
    autonumber
    actor U as Resource Owner
    participant B as Browser
    participant C as Client (booking-bff)
    participant AS as Authorization Server
    participant STORE as Authorization Store

    C->>C: Tạo state, code_verifier, code_challenge
    C-->>B: Redirect đến /oauth2/authorize
    B->>AS: client_id + redirect_uri + state + PKCE challenge
    AS->>AS: Kiểm tra RegisteredClient + redirect URI + scopes
    AS->>U: Xác thực user và consent nếu cần
    U-->>AS: Đăng nhập / chấp thuận
    AS->>STORE: Lưu authorization, code, client, redirect URI, PKCE
    AS-->>B: 302 callback?code=...&state=...
    B->>C: Callback mang code và state
    C->>C: Kiểm tra state và ngữ cảnh login
    C->>AS: POST /oauth2/token + code + redirect_uri + code_verifier + client auth
    AS->>STORE: Tải authorization theo code
    AS->>AS: So client, redirect_uri, PKCE, thời hạn và trạng thái
    alt Tất cả hợp lệ
        AS->>STORE: Ghi nhận code đã được sử dụng
        AS-->>C: Access token (+ ID token nếu OIDC)
    else Không hợp lệ
        AS-->>C: OAuth2 error, không cấp token
    end
~~~

Mỗi request thuộc một HTTP transaction riêng. AS dùng kho authorization để liên kết hai chặng, **không dựa vào ThreadLocal của request trình duyệt trước đó** khi backend client gọi token endpoint.

## 4. Ràng buộc thứ nhất: authorization code thuộc đúng client

### 4.1. `client_id` là định danh, không phải bí mật

`client_id` giúp AS tìm `RegisteredClient`, gồm các thuộc tính như grant type, redirect URIs, client authentication methods, scopes và chính sách PKCE.

Ví dụ:

~~~text
RegisteredClient A
  client_id: booking-bff
  redirect_uri: https://app.example.test/login/oauth2/code/booking-bff

RegisteredClient B
  client_id: reporting-web
  redirect_uri: https://reports.example.test/oauth2/callback
~~~

Code được cấp trong authorization request cho `booking-bff` **không thể hợp lệ khi `reporting-web` mang code đó tới token endpoint**. AS phải kiểm tra code gắn với `RegisteredClient` tương ứng.

Giữ đúng cách diễn đạt: `client_id` **được công khai** trong authorization request và có thể bị người khác đọc; bản thân `client_id` không chứng minh người gọi là ứng dụng hợp lệ. Việc bảo vệ phụ thuộc vào client authentication (nếu confidential), PKCE, redirect URI đã đăng ký và điều kiện cấp code.

### 4.2. Confidential client xác thực tại token endpoint

Một backend có thể giữ secret an toàn ở phía server; nó được đăng ký là **confidential client** và thường dùng một phương thức xác thực như `client_secret_basic`.

Tại token endpoint:

1. AS xác thực client bằng phương thức được đăng ký.
2. AS tra code đã cấp và xác minh code gắn với **đúng RegisteredClient** vừa xác thực.
3. AS xác minh redirect URI, PKCE nếu được áp dụng, thời hạn và trạng thái code.
4. Chỉ khi tất cả điều kiện đạt, AS mới cấp token.

Nếu secret sai, AS có thể trả lỗi `invalid_client`. Nếu client được xác thực hợp lệ nhưng gửi code cấp cho client khác, AS từ chối grant, thường với `invalid_grant`.

**Có client secret đúng không đồng nghĩa có quyền đổi mọi authorization code của hệ thống.**

### 4.3. Public client nhận diện bằng client ID và bảo vệ bằng PKCE

Ứng dụng di động hoặc SPA thuần **không thể giữ một client secret bí mật lâu dài**. Public client thường đăng ký `ClientAuthenticationMethod.NONE`, dùng Authorization Code + PKCE và cung cấp `client_id` ở token request theo cơ chế đã hỗ trợ.

Tại token endpoint, AS kiểm tra code có thuộc client ID đó hay không và `code_verifier` có khớp challenge đã gắn với code không. Tuy nhiên, public client **không được xác thực bằng client secret**; bất kỳ bên nào cũng có thể biết hoặc gửi cùng `client_id`. Vì vậy PKCE là ràng buộc không thể bỏ qua để chống kẻ tấn công đổi code bị đánh cắp.

Nếu attacker đồng thời chiếm được code **và** verifier, PKCE không còn ngăn được attacker. Vẫn cần bảo vệ redirect URI, bộ nhớ/lưu trữ verifier, state, TLS và toàn bộ ứng dụng.

### 4.4. Khi cùng một hệ thống có nhiều Client

Một BFF, SPA, mobile app và ứng dụng admin nên có **client registration riêng** nếu khác mức tin cậy, redirect URIs, grant types hoặc scope. Không dùng chung một client ID chỉ để giảm cấu hình khi ứng dụng có nhu cầu bảo mật khác nhau.

Ràng buộc code với client giúp ngăn hành vi lấy code hợp lệ từ một client rồi dùng nó trong token request của client khác. Nó không thay thế phân quyền ở Resource Server.

## 5. Ràng buộc thứ hai: redirect_uri chính xác

### 5.1. Vì sao redirect URI là ranh giới bảo mật?

Authorization code được gửi thông qua **trình duyệt** đến callback của OAuth2 Client. Nếu AS cho phép callback tùy ý, attacker có thể cung cấp một địa chỉ do mình kiểm soát và nhận code của người dùng sau khi người dùng đăng nhập.

Vì vậy, trước khi phát code, AS phải kiểm tra `redirect_uri` **thuộc những URI đã được đăng ký cho client** và đáp ứng quy tắc OAuth2/profile đang áp dụng. Trình duyệt chỉ được chuyển hướng đến callback được AS chấp nhận.

Ví dụ:

| Registered redirect URI | Giá trị request | Kết quả an toàn |
| --- | --- | --- |
| `https://app.example.test/callback` | `https://app.example.test/callback` | Có thể hợp lệ nếu các điều kiện khác đạt |
| `https://app.example.test/callback` | `https://evil.example.test/callback` | Từ chối |
| `https://app.example.test/callback` | `https://app.example.test.evil.test/callback` | Từ chối |
| `https://app.example.test/callback` | `https://app.example.test/callback/` | Không được tự loại bỏ dấu `/` cuối để cho qua |
| `https://app.example.test/callback` | `http://app.example.test/callback` | Từ chối vì khác scheme |
| `https://app.example.test/callback?flow=web` | `https://app.example.test/callback?flow=mobile` | Không tự thay query parameter |
| `https://app.example.test/callback` | `https://app.example.test/callback#code` | Không dùng fragment trong registered redirect URI |

Không sử dụng logic như `startsWith("https://app.example.test")` hoặc wildcard hostname để kiểm tra callback. Một URL trông giống tên miền hợp lệ vẫn có thể chuyển tới domain do attacker kiểm soát.

### 5.2. So sánh “identical” áp dụng thế nào?

Theo OAuth 2.0 (RFC 6749, mục 4.1.3), **nếu `redirect_uri` được gửi trong authorization request, thì `redirect_uri` trong token request là bắt buộc và phải giống hệt giá trị đã gửi ban đầu**.

Ví dụ:

~~~text
GET /oauth2/authorize
  client_id = booking-bff
  redirect_uri = https://app.example.test/login/oauth2/code/booking-bff

POST /oauth2/token
  code = ...
  redirect_uri = https://app.example.test/login/oauth2/code/booking-bff
  => Hai giá trị logic khớp nhau.
~~~

Cần phân biệt **giá trị URI** và cách biểu diễn nó trong HTTP: tại authorization request, URL thường được percent-encode trong query; tại token endpoint, URI được form-encode trong body. Sau khi framework decode các tham số đúng chuẩn, **giá trị `redirect_uri` phải tương ứng với giá trị ban đầu**.

Không tự ý chuẩn hóa thành URI “gần giống” để cho qua, chẳng hạn đổi chữ hoa/chữ thường của path, xóa slash, bỏ query, thay host, đổi scheme hoặc thêm cổng. Các profile đặc thù như ứng dụng native dùng loopback redirect có thể có quy tắc riêng cho port theo RFC 8252; những ngoại lệ này phải được AS hỗ trợ có chủ đích và kiểm thử chặt, không suy rộng thành wildcard cho website.

### 5.3. Nếu authorization request không gửi redirect_uri thì sao?

Chuẩn OAuth 2.0 có những điều kiện cho phép không gửi `redirect_uri` ở authorization request khi có thể xác định callback hợp lệ từ registration theo profile của server. Khi request authorize **có** gửi tham số, token request **phải** gửi lại URI giống hệt; đó là yêu cầu quan trọng cần nhớ.

Để dễ kiểm soát và tránh nhầm lẫn trong ứng dụng Spring Authorization Server, hãy **cấu hình URI chính xác trong `RegisteredClient` và thường gửi URI tường minh ở cả hai bước**, trừ khi một profile và API đã được kiểm chứng quy định khác. Không cố ý bỏ tham số để “nới lỏng” việc đối chiếu.

### 5.4. Có thể dùng redirect_uri chứa fragment hay không?

Registered redirect URI của OAuth 2.0 không được chứa fragment. Browser callback với authorization code thông thường đặt `code` và `state` trong query của redirect URI đã xác minh (hoặc response mode khác được profile hỗ trợ). Đừng đặt code vào fragment theo thói quen của các flow khác, hoặc tự tạo link không đúng response mode.

### 5.5. Không redirect khi callback chưa được xác minh

Một authorization request có `redirect_uri` không đăng ký phải được **từ chối ở AS**. Server **không được tự chuyển trình duyệt về URI chưa tin cậy** để thông báo lỗi, vì như vậy có thể hình thành open redirect và rò rỉ thông tin.

Sau khi redirect URI được xác minh an toàn, AS có thể trả OAuth2 authorization error response tới callback theo những trường hợp được chuẩn cho phép.

## 6. Ràng buộc thứ ba: PKCE liên kết code với code_verifier

### 6.1. PKCE bổ sung gì?

PKCE (Proof Key for Code Exchange, RFC 7636) ngăn kẻ tấn công lấy được authorization code trên đường callback rồi tự đem code đi đổi token **khi kẻ tấn công không biết verifier**.

Client thực hiện:

1. Sinh `code_verifier` ngẫu nhiên, entropy cao, theo tập ký tự và độ dài chuẩn.
2. Tính `code_challenge = BASE64URL(SHA256(ASCII(code_verifier)))`, bỏ padding, với `code_challenge_method=S256`.
3. Gửi `code_challenge` trong authorization request, **không gửi verifier**.
4. AS liên kết challenge và method với authorization code vừa phát hành.
5. Client gửi `code_verifier` ở token endpoint; AS tính lại và so khớp với challenge đã lưu.

Một cặp giá trị ví dụ từ RFC 7636:

~~~text
code_verifier:
dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk

code_challenge (S256):
E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM
~~~

Đây là **vector minh họa chuẩn**, tuyệt đối không tái sử dụng làm verifier cố định cho các phiên đăng nhập thật. `code_verifier` phải được tạo mới cho mỗi authorization attempt và giữ trong ngữ cảnh client có thể đối chiếu khi callback.

### 6.2. PKCE không thay client binding hay redirect validation

| Bảo vệ | Ngăn điều gì | Có thay thế các bảo vệ khác không? |
| --- | --- | --- |
| Client binding | Code do Client A nhận không được Client B đổi token | Không thay client authentication của confidential client |
| Redirect URI binding | Code không bị gửi đến callback không đăng ký và token request không đổi callback | Không thay PKCE |
| PKCE | Bên chỉ lấy được code mà không biết verifier không đổi được token | Không thay xác minh redirect URI, client ID hoặc client secret |
| `state` | Client liên kết authorization response với đúng yêu cầu đã tạo; chống CSRF/mix-up theo thiết kế | Không thay code verifier |
| OIDC `nonce` | Ràng buộc ID token với authentication request theo profile OIDC | Không thay authorization code binding |

**S256** là phương thức được ưu tiên. Không chọn `plain` chỉ để tránh dùng thư viện SHA-256, trừ khi ràng buộc tương thích đặc thù được giao thức và chính sách cho phép. Với các triển khai hiện đại, nên yêu cầu PKCE cho cả public client và confidential client khi có thể, vì PKCE còn bảo vệ trước một số trường hợp code injection/leak.

## 7. Hai chặng kiểm tra riêng trong Authorization Server

### 7.1. Authorization endpoint — quyết định có được phát code

Tại `/oauth2/authorize`, hệ thống cần kiểm tra:

- `client_id` trỏ tới `RegisteredClient` hợp lệ.
- Client được phép dùng Authorization Code Grant.
- `response_type` hợp lệ cho grant đang xử lý.
- `redirect_uri` hợp lệ theo registration và profile.
- Scope được phép yêu cầu, consent và Resource Owner đã xác thực phù hợp.
- PKCE có `code_challenge` và `code_challenge_method` nếu client/policy yêu cầu.
- Không tự phát code cho browser callback chưa được xác minh.

Khi đủ điều kiện, AS phát authorization code, liên kết code với client và metadata cần thiết, sau đó chuyển browser tới callback hợp lệ.

### 7.2. Token endpoint — quyết định có được đổi code

Tại `POST /oauth2/token`:

- Đọc grant type `authorization_code` và code.
- Nhận diện/xác thực client theo `RegisteredClient` và phương thức đã đăng ký.
- Tải authorization từ kho lưu và kiểm tra code thuộc **cùng client**.
- Kiểm tra `redirect_uri` giống giá trị từ authorize khi tham số này đã được gửi; tuân thủ profile liên quan.
- Xác minh `code_verifier` với challenge được gắn với code.
- Xác minh code còn hạn, chưa được dùng và authorization chưa bị vô hiệu hóa.
- Ghi nhận code đã tiêu thụ, chỉ phát token nếu mọi điều kiện hợp lệ.

Trong RFC 6749, authorization code là hiện vật dùng một lần; nếu code đã bị sử dụng và được gửi lại, AS phải từ chối, và chuẩn còn khuyến nghị có khả năng thu hồi các token đã cấp từ code đó khi phát hiện reuse. Việc kiểm soát replay dưới tải đồng thời cần được thử trên kho lưu và transaction thực tế.

### 7.3. Thứ tự check có thể khác nhưng chính sách cuối phải giống nhau

Không nên ràng buộc test vào **đúng một thông báo lỗi nội bộ** khi nhiều điều kiện sai cùng lúc. Ví dụ một request vừa có client secret sai vừa có code sai có thể bị từ chối ngay ở giai đoạn client authentication. Test nên đưa một giả định hợp lệ tại một thời điểm, làm sai đúng một điều kiện cần đo.

Kết quả cần chứng minh: **không cấp token** khi thiếu một điều kiện bắt buộc.

## 8. Ví dụ HTTP hoàn chỉnh: confidential client và PKCE

### 8.1. Authorization request

Client đăng ký callback `https://app.example.test/login/oauth2/code/booking-bff` và lưu `state` cùng `code_verifier` trong phiên an toàn. Sau đó chuyển hướng browser:

~~~http
GET /oauth2/authorize?response_type=code&client_id=booking-bff&redirect_uri=https%3A%2F%2Fapp.example.test%2Flogin%2Foauth2%2Fcode%2Fbooking-bff&scope=openid%20booking.read&state=state-unique-example&code_challenge=E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM&code_challenge_method=S256 HTTP/1.1
Host: auth.example.test
Accept: text/html
~~~

`state-unique-example` chỉ là placeholder. Trong ứng dụng thật, cần state ngẫu nhiên, lưu và đối chiếu riêng cho mỗi authorization attempt.

Sau khi đăng nhập và consent, AS trả:

~~~http
HTTP/1.1 302 Found
Location: https://app.example.test/login/oauth2/code/booking-bff?code=SHORT_LIVED_CODE&state=state-unique-example
Cache-Control: no-store
~~~

`SHORT_LIVED_CODE` là ký hiệu minh họa. Client phải so khớp state trước khi đổi code, đồng thời xác minh issuer/response theo những bảo vệ chống authorization server mix-up được profile và ứng dụng hỗ trợ.

### 8.2. Token request

Backend confidential client gọi AS trực tiếp qua TLS:

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.test
Authorization: Basic <base64(booking-bff:client-secret)>
Content-Type: application/x-www-form-urlencoded

grant_type=authorization_code&code=SHORT_LIVED_CODE&redirect_uri=https%3A%2F%2Fapp.example.test%2Flogin%2Foauth2%2Fcode%2Fbooking-bff&code_verifier=dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk
~~~

Đây là ví dụ HTTP được đơn giản hóa, không phải một credential thật. Với `client_secret_basic`, phần Basic được tạo đúng theo quy tắc encoding OAuth2/HTTP Basic của thư viện client; không tự ghép secret thật vào log, URL hoặc công cụ chia sẻ. Backend phải gửi **cùng redirect URI** đã dùng ở authorize và verifier đã lưu trong phiên của request đó.

### 8.3. Đối chiếu ba trường hợp

| Tham số token request | Kết quả |
| --- | --- |
| `client_secret` đúng, `code` thuộc `booking-bff`, URI/verifier khớp | AS có thể cấp token sau các kiểm tra khác |
| Secret đúng nhưng code thuộc `reporting-web` | AS từ chối grant |
| Code đúng client nhưng `redirect_uri` khác hoặc `code_verifier` sai | AS từ chối grant |

Nếu Client gọi token endpoint sai phương thức xác thực client, AS có thể trả `invalid_client`. Nếu client đã được xác thực nhưng code hoặc ràng buộc code không hợp lệ, lỗi thường là `invalid_grant`. Tránh tiết lộ trong error description liệu một code cụ thể có tồn tại, thuộc user nào hay đã được đổi ở đâu.

## 9. Cấu hình RegisteredClient trong Spring Authorization Server

Trong Spring Authorization Server 1.x, `RegisteredClient` là nơi khai báo client, callback và chính sách PKCE. Phần dưới dùng **hai mẫu registration riêng**, một confidential BFF và một public client.

### 9.1. Mẫu đăng ký confidential BFF

~~~java
import java.time.Duration;

import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.ClientAuthenticationMethod;
import org.springframework.security.oauth2.core.oidc.OidcScopes;
import org.springframework.security.oauth2.server.authorization.client.RegisteredClient;
import org.springframework.security.oauth2.server.authorization.settings.ClientSettings;
import org.springframework.security.oauth2.server.authorization.settings.TokenSettings;

public final class BookingClientRegistrations {

    private BookingClientRegistrations() {
    }

    public static RegisteredClient confidentialBff(
            PasswordEncoder passwordEncoder,
            String secretFromSecureConfiguration) {

        return RegisteredClient
            .withId("booking-bff-internal-registration-id")
            .clientId("booking-bff")
            .clientSecret(passwordEncoder.encode(
                secretFromSecureConfiguration))
            .clientAuthenticationMethod(
                ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
            .authorizationGrantType(
                AuthorizationGrantType.AUTHORIZATION_CODE)
            .redirectUri(
                "https://app.example.test/login/oauth2/code/booking-bff")
            .scope(OidcScopes.OPENID)
            .scope("booking.read")
            .clientSettings(ClientSettings.builder()
                .requireProofKey(true)
                .requireAuthorizationConsent(true)
                .build())
            .tokenSettings(TokenSettings.builder()
                .authorizationCodeTimeToLive(Duration.ofMinutes(3))
                .build())
            .build();
    }
}
~~~

Ý nghĩa:

- `clientId("booking-bff")`: định danh công khai của client.
- `clientSecret(...)`: secret được lấy từ cấu hình bảo mật rồi hash bằng `PasswordEncoder`; không hardcode raw secret vào repository.
- `CLIENT_SECRET_BASIC`: yêu cầu xác thực confidential client tại token endpoint.
- `AUTHORIZATION_CODE`: client được phép dùng code grant.
- `redirectUri(...)`: callback được đăng ký chính xác.
- `requireProofKey(true)`: yêu cầu PKCE khi client xin authorization code.
- `requireAuthorizationConsent(true)`: yêu cầu chính sách consent theo cấu hình.
- `authorizationCodeTimeToLive(...)`: đặt thời hạn code ngắn.

Đây là **factory tạo registration**, không phải mã cấu hình toàn bộ Authorization Server. Cần đưa registration vào `RegisteredClientRepository` và cung cấp password encoder, secret, authorization storage, user authentication, key management, issuer và token/consent services. Trong môi trường persistence, ID nội bộ phải được quản lý ổn định; không tạo bản đăng ký trùng mới mỗi khi khởi động.

### 9.2. Mẫu đăng ký public client

Ví dụ minh họa public mobile client dùng HTTPS callback đã được nền tảng mobile xác nhận bằng cơ chế App Links/Universal Links khi triển khai thực tế:

~~~java
public static RegisteredClient publicMobileClient() {
    return RegisteredClient
        .withId("booking-mobile-internal-registration-id")
        .clientId("booking-mobile")
        .clientAuthenticationMethod(ClientAuthenticationMethod.NONE)
        .authorizationGrantType(AuthorizationGrantType.AUTHORIZATION_CODE)
        .redirectUri("https://mobile.example.test/oauth2/callback")
        .scope(OidcScopes.OPENID)
        .scope("booking.read")
        .clientSettings(ClientSettings.builder()
            .requireProofKey(true)
            .requireAuthorizationConsent(true)
            .build())
        .tokenSettings(TokenSettings.builder()
            .authorizationCodeTimeToLive(Duration.ofMinutes(3))
            .build())
        .build();
}
~~~

Phương thức này có thể được đặt trong class factory của ví dụ trước, dùng các import tương ứng. Public client **không có client secret**. Khi đổi code, nó dùng `client_id` và `code_verifier` theo hợp đồng của AS, đồng thời token endpoint xác minh code thuộc client registration đó. Không nhúng confidential client secret vào ứng dụng mobile và gọi đó là an toàn.

Với native app, redirect URI và xử lý callback phải tuân thủ RFC 8252. Một đường dẫn HTTPS thông thường **chưa đủ** chứng minh callback được hệ điều hành liên kết đúng với app; cần xác minh App Links/Universal Links và các yêu cầu nền tảng. Các trường hợp loopback URI hoặc custom scheme chỉ sử dụng khi profile và AS hỗ trợ đầy đủ.

### 9.3. Ví dụ token request của public client

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.test
Content-Type: application/x-www-form-urlencoded

grant_type=authorization_code&client_id=booking-mobile&code=ONE_TIME_CODE&redirect_uri=https%3A%2F%2Fmobile.example.test%2Foauth2%2Fcallback&code_verifier=VERIFIER_SAVED_BY_CLIENT
~~~

Không có header `Authorization: Basic ...` vì client được đăng ký với authentication method `none`. `VERIFIER_SAVED_BY_CLIENT` cần là giá trị thực đã tạo challenge tại authorization request, không phải một chuỗi placeholder. Public client vẫn phải bảo vệ verifier và state khỏi bị đọc/chèn bởi mã không đáng tin cậy trong quá trình authorization.

## 10. Spring Authorization Server lưu và kiểm tra ràng buộc ở đâu?

### 10.1. Client registration

`RegisteredClientRepository` cung cấp registered client cho:

- Authorization endpoint: kiểm tra `client_id`, grant type, `redirect_uri` và scopes.
- Token endpoint/client authentication: kiểm tra phương thức xác thực của client.
- Token/grant processing: kiểm tra code thuộc đúng client registration.

Phần đăng ký thường được lưu qua `InMemoryRegisteredClientRepository` cho thử nghiệm hoặc `JdbcRegisteredClientRepository` trong ví dụ persistence, tùy kiến trúc sản xuất.

### 10.2. Authorization record và authorization code

`OAuth2AuthorizationService` là nơi AS lưu `OAuth2Authorization`, bao gồm các thông tin liên quan như:

- `registeredClientId` (định danh nội bộ của RegisteredClient).
- `principalName` và grant type.
- Authorized scopes và metadata/attributes của request.
- Authorization code, thời hạn, trạng thái token và các dữ liệu cần thiết để đối chiếu khi đổi code.
- Những metadata về PKCE và redirect URI mà các provider cần để hoàn thành grant.

Các trường/attribute chi tiết nằm trong mô hình API của phiên bản Spring Authorization Server đang dùng. Không tự suy đoán khóa attribute khi truy vấn database; **để provider chính thức lưu và truy xuất qua `OAuth2AuthorizationService`**.

Nếu dùng `InMemoryOAuth2AuthorizationService` trong nhiều instance AS mà không chia sẻ trạng thái, browser có thể nhận code từ instance A nhưng token request đến instance B không tìm thấy code. Trong production cần kho dữ liệu/thiết kế phân phối phù hợp và kiểm tra transaction cho việc tiêu thụ code một lần.

### 10.3. Provider phụ trách hai bước khác nhau

| Bước | Lớp thường gặp trong SAS 1.x | Việc liên quan |
| --- | --- | --- |
| Authorization endpoint | `OAuth2AuthorizationCodeRequestAuthenticationProvider` | Kiểm tra request, client, URI, scope, consent và phát code qua thành phần AS |
| Token endpoint | `OAuth2AuthorizationCodeAuthenticationProvider` | Xử lý đổi authorization code, xác minh client và các ràng buộc grant |
| Client authentication tại token endpoint | Các provider xác thực client tương ứng | Xác minh `client_secret_basic`, các phương thức khác hoặc nhận diện public client theo cấu hình |
| Trạng thái grant | `OAuth2AuthorizationService` | Lưu/tra authorization code và dữ liệu liên kết |
| Cấu hình client | `RegisteredClientRepository` | Cung cấp registration và điều kiện được phép |

Đừng nhầm `OAuth2AuthorizationCodeRequestAuthenticationProvider` với `OAuth2AuthorizationCodeAuthenticationProvider`. Một bên xử lý **xin code**, một bên xử lý **đổi code**. Cấu hình validator authorization request không thay thế kiểm tra code ownership và PKCE tại token endpoint.

### 10.4. Không tự thay các validation mặc định

Khi tùy chỉnh `OAuth2AuthorizationEndpointConfigurer` và provider, hãy giữ logic chuẩn xác minh callback và scope. Nếu dùng `setAuthenticationValidator(...)` trên `OAuth2AuthorizationCodeRequestAuthenticationProvider` thì cần kết hợp các validator mặc định:

~~~java
Consumer<OAuth2AuthorizationCodeRequestAuthenticationContext> validator =
    OAuth2AuthorizationCodeRequestAuthenticationValidator
        .DEFAULT_REDIRECT_URI_VALIDATOR
    .andThen(
        OAuth2AuthorizationCodeRequestAuthenticationValidator
            .DEFAULT_SCOPE_VALIDATOR
    )
    .andThen(context -> {
        // Chỉ bổ sung policy nghiệp vụ đã được xác định rõ.
        enforceAdditionalPolicy(context);
    });

codeRequestProvider.setAuthenticationValidator(validator);
~~~

`enforceAdditionalPolicy` và `codeRequestProvider` là điểm tích hợp của ứng dụng, không phải bean/method được khai báo tự động trong đoạn này. Code chủ đích minh họa **cách nối thêm điều kiện mà không làm mất kiểm tra mặc định**.

Không sửa custom converter/provider để chấp nhận URI không đăng ký, bỏ PKCE hoặc cấp code dựa trên `client_id`/URI chưa được xác minh.

## 11. Ba tình huống tấn công cần nhận biết

### 11.1. Đánh cắp code qua redirect URI lỏng lẻo

**Kịch bản:** AS cho phép `redirect_uri` bất kỳ hoặc dùng so khớp prefix, attacker điều hướng callback về domain do mình kiểm soát.

**Hậu quả:** authorization code có thể bị gửi cho attacker.

**Bảo vệ:** đăng ký callback chính xác, kiểm tra URI tại authorize, không redirect tới URI chưa được xác minh, yêu cầu PKCE và client authentication khi phù hợp.

### 11.2. Đổi code của Client A bằng Client B

**Kịch bản:** attacker có code từ một authorization flow của `booking-bff`, nhưng cố dùng credential/ID của `reporting-web` tại token endpoint.

**Hậu quả nếu AS không ràng buộc code với client:** có nguy cơ token bị cấp sai client, phá vỡ consent và phân quyền client.

**Bảo vệ:** AS tra authorization record và kiểm tra `registeredClientId` tương ứng với client đã được nhận diện/xác thực; sai phải từ chối. Mỗi client dùng redirect URI và chính sách riêng.

### 11.3. Đánh cắp code nhưng không có PKCE verifier

**Kịch bản:** attacker đọc được authorization code trong một đường callback hoặc log, rồi gửi code tới token endpoint. Token endpoint yêu cầu verifier và code được liên kết với challenge S256 đã lưu.

**Kết quả mong muốn:** attacker không có verifier nên không thể hoàn tất code exchange. Client thật vẫn phải bảo vệ state, redirect, session và verifier; PKCE không ngăn được attacker có quyền kiểm soát hoàn toàn môi trường client hoặc cả code lẫn verifier.

### 11.4. Code injection và session mix-up

Một attacker có thể cố đưa code thuộc authorization attempt khác vào callback của client. Client phải kiểm tra `state`, issuer/AS identity (nếu profile hỗ trợ), PKCE và session login request tương ứng. AS phải kiểm tra code/client/redirect ở token endpoint. Đừng dựa vào duy nhất việc “code trông ngẫu nhiên” hoặc URI đã được allowlist.

## 12. Kiểm thử bảo mật theo ma trận điều kiện

Bộ test nên cố tình làm sai **một ràng buộc tại một thời điểm** để biết check nào đã hoạt động.

| Test case | Thao tác | Kết quả mong đợi |
| --- | --- | --- |
| Luồng hợp lệ | Đúng client, URI, verifier, code chưa dùng và còn hạn | Token được cấp theo grant và chính sách |
| Sai client ở token endpoint | Code thuộc A nhưng xác thực/gửi client B | Từ chối; không cấp token |
| Sai client secret | Confidential client gửi secret sai | Client authentication thất bại, thường `invalid_client` |
| Public client thiếu `client_id` | Không nhận diện client đúng | Từ chối theo protocol |
| Sai callback tại authorize | URI không có trong registration | Từ chối tại AS, không redirect tới URI lạ |
| Sai callback tại token | URI khác giá trị đã gửi tại authorize | Từ chối grant |
| Thiếu URI tại token | URI đã gửi ở authorize nhưng token request bỏ qua | Từ chối |
| Sai `code_verifier` | Không tạo đúng S256 challenge đã lưu | Từ chối grant |
| Thiếu verifier khi PKCE bắt buộc | Không chứng minh sở hữu verifier | Từ chối |
| Challenge có method không được phép | `code_challenge_method` trái policy | Từ chối authorization request |
| Code hết hạn | Đổi sau TTL | Từ chối grant |
| Code dùng hai lần | Đổi thành công rồi thử lại | Lần sau không cấp token |
| Hai request đổi cùng code đồng thời | Gửi token request song song | Không được cấp token hai lần; kiểm tra tính nguyên tử của lưu trữ |
| Code thuộc user khác | Cố thay callback/state hoặc authorization record | Không cho dùng để vượt liên kết đã tạo; giữ kiểm tra client/PKCE |
| User từ chối consent | Không có quyền được cấp | Không phát code hợp lệ |
| Request có scope ngoài registration | Scope không được phép | Từ chối hoặc xử lý đúng policy, không cấp vượt |
| Client có secret đúng nhưng sai verifier | Thông tin client đúng, PKCE sai | Vẫn từ chối grant |
| Token request dùng HTTP thay HTTPS | Không đáp ứng transport security | Không chấp nhận triển khai production; endpoint phải bảo vệ bằng TLS |

### 12.1. Bài test tích hợp nên chứng minh điều gì?

Một bài test tích hợp đúng nghĩa cần:

1. Khởi tạo `RegisteredClient` A và B với ID/redirect URI khác nhau, enable PKCE.
2. Tạo authorization request hợp lệ cho A, đăng nhập Resource Owner và hoàn thành consent.
3. Lấy code qua redirect callback của A.
4. Thử đổi code bằng client B (với credentials hợp lệ của B) → **không có access token**.
5. Tạo code khác cho A rồi thử đổi bằng A với URI khác → **không có access token**.
6. Tạo code khác cho A rồi thử đổi với verifier sai → **không có access token**.
7. Tạo code mới khác, đổi bằng A với URI/verifier đúng → **thành công đúng một lần**.
8. Gửi lại code đã tiêu thụ → **bị từ chối**.
9. Kiểm tra authorization record và token store không chứa token được cấp từ các request thất bại.

Không dùng cùng một code cho nhiều ca độc lập nếu test trước đó đã đổi thành công, vì test sau sẽ thất bại do **replay**, không phản ánh điều kiện bạn muốn kiểm tra.

### 12.2. Tạo thử nghiệm âm tại token endpoint

Một request đổi code sai redirect URI minh họa:

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.test
Authorization: Basic <client-credentials-for-booking-bff>
Content-Type: application/x-www-form-urlencoded

grant_type=authorization_code&code=CODE_FROM_VALID_AUTHORIZE&redirect_uri=https%3A%2F%2Fattacker.example.test%2Fcallback&code_verifier=VALID_VERIFIER_FOR_CODE
~~~

Kết quả: AS phải từ chối grant, **không phát token**. Với các lỗi code binding, token endpoint thường dùng `invalid_grant` trong OAuth2 error response. Không test bằng cách chỉ nhìn thấy HTTP 400; cần khẳng định response không có access token và log/store không ghi grant thành công.

### 12.3. Test public client không có client secret

Đăng ký public client với `ClientAuthenticationMethod.NONE` và `requireProofKey(true)`. Test rằng một caller biết `client_id` và code nhưng **thiếu verifier đúng** không đổi được token. Đồng thời test Client Credentials không thể được public client sử dụng nếu registration không cho phép grant đó.

Khi dùng mock authentication trực tiếp tại controller/service, bạn có thể bỏ qua các bộ lọc OAuth2 thực tế. Để kiểm tra code binding, phải đi qua **authorization endpoint + token endpoint** và provider của AS trong test tích hợp.

## 13. Vận hành và quan sát trong hệ thống nhiều instance

### 13.1. Authorization storage nhất quán

Trong môi trường nhiều instance:

- Authorization endpoint có thể chạy ở AS instance A.
- Token endpoint có thể đến AS instance B.
- Cả hai cần truy cập trạng thái authorization/code có cùng tính đúng đắn.

Nếu dùng `InMemoryOAuth2AuthorizationService` theo từng instance, B có thể không tra được code mà A cấp. Cần kho lưu bền vững và chia sẻ phù hợp, ví dụ JDBC theo tài liệu Spring Authorization Server, hoặc thiết kế phân phối có đảm bảo tương đương. Trong production, test nhiều instance, restart và failover.

Một vấn đề cần đặc biệt chú ý là **hai token request đồng thời cùng một code**. Kho lưu và đường đi giao dịch phải bảo đảm ngữ nghĩa một lần; test concurrency trên hạ tầng thật, không chỉ trên bộ nhớ đơn tiến trình.

### 13.2. TTL và retry

Authorization code nên có TTL ngắn; ví dụ `Duration.ofMinutes(3)` ở trên là **giá trị minh họa**, cần lựa chọn theo UX, độ trễ login/consent, chính sách và hạ tầng.

Không “retry token request bằng cùng code” một cách mù quáng sau timeout nếu không biết request trước đã được AS xử lý hay chưa. Code có thể đã bị tiêu thụ; client phải xử lý lỗi và khởi tạo lại authorization attempt phù hợp khi cần. Đó là một lý do để phân biệt lỗi mạng với `invalid_grant` và ghi nhận trace ID an toàn.

### 13.3. Bảo vệ code, verifier và callback

- Dùng HTTPS cho AS và web callback trong production.
- Không ghi raw code, verifier, access token, refresh token hoặc client secret vào log, tracing, analytic URL hay error page.
- Giảm nguy cơ code lộ qua browser history/referrer bằng callback phù hợp, redirect flow và chính sách `Referrer-Policy`/cache.
- Không nhận `redirect_uri` động do người dùng cuối có thể thay đổi tùy ý.
- Với SPA/mobile, giữ verifier và state theo đúng authorization attempt; không lưu ở nơi dễ bị script không đáng tin cậy đọc nếu có lựa chọn tốt hơn.
- Cấu hình cookie/session/CSRF đúng luồng để state không bị lệch do nhiều tab hoặc login đồng thời.
- Quản lý client registration qua migration/quy trình phê duyệt, audit mọi thay đổi callback hoặc grant type.
- Xoay client secret theo policy khi confidential client có rủi ro lộ credential; không xem secret là giải pháp thay thế PKCE.

### 13.4. Chẩn đoán lỗi không làm lộ thông tin nhạy cảm

Khi gặp `invalid_grant` ở token endpoint, kiểm tra theo thứ tự:

1. Request có đến đúng AS issuer/token endpoint không?
2. Client được nhận diện/xác thực theo registration nào?
3. Code có tồn tại và còn hạn trong authorization store không?
4. Code gắn với đúng `registeredClientId` không?
5. Redirect URI có khớp request authorize không?
6. `code_verifier` có khớp challenge/method không?
7. Code có từng được đổi hoặc bị invalidated không?
8. Có chênh lệch đồng hồ, lỗi persistence, load balancer hoặc retry song song không?

Chỉ log request ID, client ID đã được kiểm soát, loại lỗi/điểm kiểm tra, metadata thời gian và correlation ID. Không log toàn bộ query callback, raw authorization code hoặc verifier để “debug nhanh”.

## 14. Những lỗi triển khai hay gặp

| Sai lầm | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Xem `client_id` là bí mật | Public client có thể bị giả danh ở token endpoint nếu hệ thống bỏ PKCE | Dùng PKCE; xác thực confidential client đúng cơ chế |
| Dùng chung client ID cho SPA, mobile, BFF | Chính sách redirect URI/grant/secret khó cô lập | Đăng ký từng client phù hợp |
| Chấp nhận URI chỉ bằng `startsWith(...)` | Open redirect, code leak | So khớp URI theo registration/profile |
| Chỉ kiểm tra URI tại authorize, bỏ đối chiếu ở token | Code có thể bị đổi khác ngữ cảnh | Bind và kiểm tra cùng URI như yêu cầu RFC 6749 |
| Bỏ `redirect_uri` ở token dù authorize đã gửi | Vi phạm yêu cầu liên kết callback | Gửi lại URI identical |
| PKCE chỉ có `code_challenge` mà không kiểm tra verifier | Code bị đánh cắp có thể đổi token | Verify S256 tại token endpoint |
| Dùng `plain` theo mặc định | Giảm khả năng chống tấn công quan sát authorization request | Ưu tiên S256 |
| Tái sử dụng verifier/state cho nhiều attempt | Dễ nhầm phiên, tăng rủi ro khi rò rỉ | Sinh mới từng authorization attempt |
| Không đánh dấu code đã được sử dụng | Replay authorization code | Tiêu thụ code một lần, test đồng thời |
| Xóa default redirect validator khi custom policy | Callback trái phép có thể lọt qua | Giữ default validator và thêm policy |
| Dùng Memory authorization store qua nhiều AS instance | Token endpoint không tìm được code | Lưu trữ chia sẻ nhất quán |
| Tự trả OAuth2 code từ controller | Bỏ qua provider/client/PKCE/consent kiểm tra | Dùng flow chuẩn của Spring Authorization Server |
| Tin rằng đăng nhập user thay thế xác thực client | Grant bị cấp cho ứng dụng sai | Phân biệt Resource Owner authentication với Client authentication |
| Cho rằng access token là authorization code | Sai endpoint và lifecycle | Code chỉ đổi token, access token dùng gọi Resource Server |

## 15. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao một client có `client_secret` đúng vẫn không thể đổi code cấp cho client khác?

**Đáp án:** AS phải kiểm tra authorization code gắn với đúng client registration. Xác thực thành công chỉ chứng minh caller là client đó, không cho phép sử dụng authorization của client khác.

**Câu 2.** Nếu `redirect_uri` trong authorization request có dấu slash cuối, token request bỏ dấu slash có được chấp nhận không?

**Đáp án:** Không nên. Khi `redirect_uri` đã gửi tại authorize, token request phải gửi lại giá trị giống hệt theo RFC 6749. Không tự chuẩn hóa hai URI khác nhau thành một chỉ vì có vẻ dẫn đến cùng tài nguyên.

**Câu 3.** Public client không có secret, làm sao bảo vệ việc đổi code?

**Đáp án:** AS xác minh code gắn với client ID và bắt buộc PKCE. Caller phải chứng minh nắm `code_verifier` tương ứng với `code_challenge` đã lưu, bên cạnh kiểm tra redirect URI và lifecycle của code.

**Câu 4.** PKCE có thể bảo vệ nếu attacker lấy được cả code và verifier không?

**Đáp án:** Không. PKCE bảo vệ khi kẻ tấn công chỉ có code; client còn phải bảo vệ verifier, state, callback, session và môi trường thực thi.

**Câu 5.** Vì sao test dùng lại code ở mọi trường hợp âm là sai?

**Đáp án:** Code có thể đã được tiêu thụ. Khi đó test sau luôn thất bại do replay và không chứng minh được binding theo client, URI hay PKCE.

**Câu 6.** Tại sao Authorization Server dùng nhiều instance phải dùng authorization storage chia sẻ?

**Đáp án:** Authorization code được cấp ở request authorize nhưng đổi ở request token khác, có thể đi vào instance khác. Các instance phải có cùng trạng thái client/code/PKCE và bảo đảm dùng code một lần.

**Câu 7.** `state` và `code_verifier` có giống nhau không?

**Đáp án:** Không. `state` để client liên kết callback với authorization attempt, còn `code_verifier` chứng minh quyền đổi code theo PKCE. Cả hai cần được tạo/lưu và xác minh đúng mục đích.

## 16. Checklist trước khi đưa flow vào production

- [ ] Mỗi OAuth2 client có registration riêng theo mức tin cậy và ứng dụng.
- [ ] Redirect URI được đăng ký và xác minh chặt; không có callback wildcard tùy tiện.
- [ ] Authorization request có `client_id`, `response_type=code`, `redirect_uri` theo profile, `state` và PKCE challenge phù hợp.
- [ ] Bật `requireProofKey(true)` cho client dùng code grant khi chính sách yêu cầu.
- [ ] Public client không lưu client secret trong mã phân phối; dùng PKCE S256.
- [ ] Confidential client xác thực tại token endpoint và vẫn áp dụng PKCE theo chính sách.
- [ ] Token endpoint đối chiếu code với client registration, redirect URI, verifier, expiry và trạng thái dùng một lần.
- [ ] Client kiểm tra `state`/issuer ngữ cảnh và giữ verifier đúng authorization attempt.
- [ ] User authentication/consent không bị nhầm với client authentication.
- [ ] Có test âm riêng cho sai client, URI, verifier, expired code, replay và concurrent redemption.
- [ ] Authorization store hoạt động qua nhiều instance/restart, có transaction đúng với lifecycle code.
- [ ] HTTPS, cookie, logging, referrer và secret handling bảo vệ code/verifier.
- [ ] Đã kiểm thử flow end-to-end cùng Spring OAuth2 Client/Resource Server hoặc client thực tế.

## 17. Tài liệu tham khảo và kết luận

Tài liệu chính thức nên đọc theo **đúng phiên bản thư viện**:

- [RFC 6749 — OAuth 2.0 Authorization Framework, Authorization Code Grant](https://www.rfc-editor.org/rfc/rfc6749#section-4.1)
- [RFC 7636 — Proof Key for Code Exchange](https://www.rfc-editor.org/rfc/rfc7636)
- [RFC 8252 — OAuth 2.0 for Native Apps](https://www.rfc-editor.org/rfc/rfc8252)
- [RFC 9207 — Authorization Server Issuer Identification](https://www.rfc-editor.org/rfc/rfc9207)
- [Spring Authorization Server — Core Model and Components](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html)
- [Spring Authorization Server — Protocol Endpoints](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html)
- [Spring Authorization Server — Configuration Model](https://docs.spring.io/spring-authorization-server/reference/configuration-model.html)
- [Spring Security — OAuth2 Client](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/index.html)

Khi thiết kế Authorization Code + PKCE, hãy xem **`client_id`, `redirect_uri` và `code_challenge` là những ràng buộc được ghi cùng authorization code**. Khi đổi code, AS xác minh **client đúng, URI đúng, verifier đúng và code còn hợp lệ/chưa dùng**. Chính kết hợp này bảo vệ tính liên tục giữa hai request và ngăn cấp token sai ngữ cảnh trong hệ thống OAuth 2.0/OIDC.

