# Bảo vệ endpoint phát hành

## 1. Vì sao endpoint phát hành token là ranh giới bảo mật đặc biệt?

Trong chương **Token issuance** của module **SECURITY_TOKEN_SECURITY_FUNDAMENTALS**, một trong những nhiệm vụ trọng tâm là bảo vệ **endpoint nơi hệ thống quyết định cấp credential**. Tại đây, một yêu cầu hợp lệ có thể được chuyển thành access token cho phép truy cập dữ liệu hoặc refresh token cho phép duy trì quyền truy cập trong tương lai. Sai sót tại thời điểm phát hành có thể ảnh hưởng đến nhiều resource server ngay cả khi từng API riêng lẻ kiểm tra JWT đúng cách.

Hãy tưởng tượng một ứng dụng thương mại điện tử: người dùng đăng nhập qua Authorization Server (AS), ứng dụng đổi authorization code lấy access token, rồi dùng token đó gọi Orders API. Nếu kẻ tấn công chiếm được authorization code và đổi được mã trước client hợp lệ, hoặc khiến AS cấp scope rộng hơn quyền đã phê duyệt, resource server có thể nhận một token **hợp lệ về chữ ký** nhưng được phát hành sai.

Một endpoint phát hành an toàn phải trả lời đồng thời:

1. **Ai đang yêu cầu token?** Client nào, người dùng nào hoặc workload nào đã được xác thực bằng cơ chế phù hợp?
2. **Yêu cầu dựa trên quyền nào?** Authorization code, refresh token, client credentials hoặc grant được hỗ trợ khác có hợp lệ và thuộc đúng client không?
3. **Được cấp quyền gì?** Scope, audience/resource, subject, tenant và thời gian sống nào nằm trong giới hạn chính sách?
4. **Token được bảo vệ thế nào sau khi cấp?** Credential có bị lộ qua mạng, redirect, log, browser, cache hoặc lưu trữ không?
5. **Có thể phát hiện và ngăn dùng lại không?** Authorization code được dùng một lần, refresh token được bảo vệ chống replay, và AS có khả năng thu hồi khi cần hay không?

**Nguyên tắc cốt lõi:** một yêu cầu tới endpoint phát hành chưa phải quyền được cấp. Chỉ sau khi **xác thực đúng các bên, xác minh grant, áp chính sách và tạo token an toàn**, AS mới được trả credential.

## 2. Phân biệt các endpoint thường gặp của OAuth 2.0/OIDC

Thuật ngữ "endpoint phát hành" thường chỉ **token endpoint**, nhưng bảo vệ luồng cấp token cần xem cả **authorization endpoint** và những endpoint hỗ trợ liên quan.

| Endpoint | Ví dụ đường dẫn | Nhiệm vụ | Điểm bảo vệ chính |
|---|---|---|---|
| **Authorization endpoint** | `/oauth2/authorize` | Nhận yêu cầu ủy quyền, xác thực người dùng và xử lý consent/chính sách, rồi trả authorization code | Redirect URI, client_id, PKCE challenge, state, phiên đăng nhập, chống CSRF và trộn luồng |
| **Token endpoint** | `/oauth2/token` | Đổi authorization code/refresh token hoặc xử lý grant thích hợp để cấp access token và đôi khi refresh/ID token | Client authentication, kiểm tra grant, PKCE verifier, scope, audience, replay, rate limit |
| **Device authorization endpoint** (nếu có) | `/oauth2/device_authorization` | Khởi tạo luồng thiết bị với device_code/user_code | Giới hạn cấp mã, thời hạn, polling, liên kết mã và client |
| **Revocation endpoint** | `/oauth2/revoke` | Yêu cầu thu hồi token theo chính sách | Xác thực client, ràng buộc token với client, chống lạm dụng |
| **Introspection endpoint** | `/oauth2/introspect` | Cho resource server/client đủ quyền kiểm tra token | Xác thực caller, giới hạn dữ liệu trả về, chống dò token |
| **Metadata/JWKS endpoint** | `/.well-known/...`, `/jwks` | Công bố cấu hình và khóa công khai theo giao thức | Tính toàn vẹn cấu hình, kiểm soát nguồn khóa, rotation |

Đường dẫn trong bảng chỉ là **ví dụ**. OAuth không buộc mọi sản phẩm sử dụng các URL này. Revocation, introspection và JWKS **không phải những endpoint tự cấp access token**; chúng được nhắc đến vì trực tiếp ảnh hưởng đến mô hình tin cậy và vòng đời token.

### 2.1. Ba vai trò không được nhầm

- **Client:** ứng dụng web, mobile, SPA hoặc backend xin token.
- **Authorization Server/Issuer:** bên quyết định có cấp token, cho ai, phạm vi nào và trong bao lâu.
- **Resource server:** API nhận access token, xác minh token và áp quyền trên tài nguyên cụ thể.

Một API có thể vừa là resource server khi nhận token, vừa là OAuth client khi xin token để gọi API khác. Nhưng quyền phát hành và quyền chấp nhận token vẫn là những trách nhiệm riêng.

### 2.2. Authentication khác authorization tại điểm phát hành

**Xác thực client** chứng minh ứng dụng nào đang liên hệ token endpoint; **xác thực người dùng** chứng minh người dùng nào tham gia quy trình đăng nhập; **ủy quyền** quyết định client được cấp scope/resource nào. Không thể suy từ việc client secret đúng rằng client được truy cập mọi dữ liệu của người dùng, hoặc từ việc user đăng nhập rằng mọi client đều được quyền lấy token cho user đó.

## 3. Mô hình đe dọa với endpoint phát hành

| Mối đe dọa | Điểm tấn công | Hậu quả |
|---|---|---|
| **Authorization code interception** | Mã ủy quyền bị chặn khi redirect hoặc qua client bị kiểm soát | Kẻ khác đổi code thành token |
| **Authorization code injection** | Code từ luồng khác bị đưa vào callback của client | Đăng nhập nhầm tài khoản hoặc gắn phiên sai |
| **Redirect URI manipulation** | AS chấp nhận redirect tùy ý, wildcard hoặc open redirect | Code/token chảy sang miền do kẻ tấn công kiểm soát |
| **CSRF / login CSRF** | Client không liên kết response với request/phiên đã khởi tạo | Nạn nhân bị ép hoàn tất luồng xác thực ngoài ý muốn |
| **Client impersonation** | Client secret lộ, cấu hình xác thực client yếu | Kẻ tấn công xin token dưới danh nghĩa ứng dụng khác |
| **Code/refresh token replay** | Grant có thể dùng lại hoặc rotation thiếu phát hiện reuse | Cấp nhiều token hoặc duy trì quyền truy cập trái phép |
| **Scope/audience escalation** | AS tin nguyên scope/resource client yêu cầu | Token được cấp quyền rộng hoặc dành cho API không được phép |
| **Mix-up giữa các issuer** | Client làm việc với nhiều AS nhưng nhầm nguồn authorization response | Code/token bị gửi đến AS sai |
| **Token response leakage** | Token bị cache, log, lộ qua HTTP hoặc đường đi không an toàn | Credential có thể được sử dụng bởi bên khác |
| **Key/signature confusion** | Xác minh hoặc ký token dùng thuật toán/khóa không đúng | Token bị chấp nhận giả mạo hoặc không thể xác thực đáng tin |
| **Brute force, credential stuffing, DoS** | Login/token endpoint nhận nhiều yêu cầu không hợp lệ | Chiếm tài khoản, tiêu thụ tài nguyên, gây gián đoạn |

Không phải mọi triển khai đều có tất cả endpoint hoặc luồng trên. Hãy lập **threat model từ grant, loại client, điểm redirect, kho secret và API đích thực tế**.

## 4. Ranh giới tin cậy của Authorization Code + PKCE

Đối với ứng dụng tương tác với người dùng, một luồng phổ biến là **Authorization Code kết hợp PKCE**.

~~~mermaid
sequenceDiagram
    actor U as Người dùng
    participant C as OAuth Client
    participant AS as Authorization Server
    participant RS as Resource Server
    U->>C: Mở tính năng cần quyền
    C->>C: Tạo state, code_verifier và code_challenge
    C->>AS: Authorization request với client_id, redirect_uri, scope, PKCE
    AS->>U: Xác thực, consent hoặc policy nếu cần
    AS->>AS: Ràng buộc code với client, redirect URI và challenge
    AS-->>C: Redirect về URI đã đăng ký với code và state
    C->>C: Kiểm tra state và đúng issuer/luồng
    C->>AS: Token request: code, redirect_uri, code_verifier
    AS->>AS: Xác thực client khi áp dụng, kiểm tra code dùng một lần và PKCE
    AS-->>C: Access token; ID/refresh token nếu đủ điều kiện
    C->>RS: Gọi API bằng access token đúng audience
    RS->>RS: Kiểm tra token, scope và quyền trên resource
    RS-->>C: Dữ liệu được phép hoặc lỗi
~~~

Khi một thành phần kiểm tra sai ở các mũi tên trên, token vẫn có thể bị cấp cho sai người hoặc sai client. Vì vậy, bảo vệ token endpoint không thể tách khỏi cách authorization request được tạo và response được xử lý.

### 4.1. Client đăng ký và redirect URI

AS cần có bản ghi client đáng tin cậy, gồm:

- **client_id**, loại client (public/confidential), grant được cho phép.
- Redirect URI được đăng ký và kiểm tra đúng hợp đồng.
- Phương thức xác thực client tại token endpoint nếu là confidential client.
- Scope và resource/audience client có thể được cấp.
- Quy tắc consent, tenant, ràng buộc phiên hoặc chính sách bảo mật bổ sung.

Khi nhận authorization request, AS cần kiểm tra redirect URI theo quy tắc giao thức và hồ sơ client. Với ứng dụng web, nên dùng **URI chính xác đã đăng ký**, tránh wildcard, kiểm tra tiền tố hoặc chỉ so domain. Các ngoại lệ theo chuẩn dành cho native app loopback redirect cần được xử lý theo đúng profile, không biến thành wildcard chung.

Một **open redirect** trên ứng dụng client có thể khiến code bị chuyển tiếp đến địa chỉ ngoài dự kiến, kể cả khi AS chỉ cho chuyển về URI đăng ký. Client cũng cần tránh đặt endpoint callback nằm sau một open redirect.

### 4.2. `state`, session và chống CSRF

Client thường tạo **state không thể đoán**, liên kết với phiên và authorization request gốc. Khi nhận callback, client đối chiếu state trước khi đổi code. Việc này giúp phát hiện response không xuất phát từ luồng mà chính client đã bắt đầu.

Với OIDC, **nonce** còn có thể ràng buộc ID token với yêu cầu xác thực và giảm rủi ro replay trong những luồng yêu cầu nó. `nonce`, `state` và PKCE **không đồng nghĩa**; mỗi cơ chế có vai trò và quy tắc kiểm tra riêng. Theo profile/triển khai, PKCE có thể đóng góp vào CSRF protection, nhưng vẫn phải đáp ứng đầy đủ yêu cầu liên kết request-response và phiên của client.

Nếu client liên hệ nhiều Authorization Server, cần chống **authorization server mix-up** bằng cơ chế như kiểm tra issuer ở authorization response theo RFC 9207, hoặc cách ràng buộc issuer/redirect URI phù hợp. Không được gửi authorization code của AS A tới token endpoint AS B.

## 5. PKCE và tính một lần của authorization code

**Proof Key for Code Exchange (PKCE, RFC 7636)** bảo vệ code khỏi việc bị chặn rồi đổi trái phép. Client tạo `code_verifier` ngẫu nhiên đủ mạnh và từ đó tạo `code_challenge`; AS lưu challenge gắn với code. Ở token endpoint, client cung cấp verifier để AS kiểm tra.

Với phương thức khuyến nghị **S256**:

~~~text
code_verifier  = chuỗi ngẫu nhiên mật mã, đúng cú pháp và độ dài RFC 7636
code_challenge = BASE64URL_NO_PADDING(SHA256(ASCII(code_verifier)))
code_challenge_method = S256
~~~

`code_verifier` là bí mật dùng cho **một luồng authorization**. Không tái sử dụng verifier cố định cho mọi phiên hoặc để lộ nó trong URL/log. AS chỉ được cấp token khi verifier **khớp challenge đã được ràng buộc với code gốc**.

### 5.1. Authorization code phải có ràng buộc

Một authorization code an toàn cần được AS quản lý tối thiểu theo những thuộc tính:

| Thuộc tính | Mục đích |
|---|---|
| `code_hash` hoặc định danh code không thể đoán | Tra cứu và xác minh code một cách an toàn |
| `client_id` | Code chỉ được đổi bởi đúng client |
| `redirect_uri` | Ràng buộc redirect URI của yêu cầu gốc theo quy tắc OAuth |
| `code_challenge`, `method` | Kiểm tra PKCE tại token endpoint |
| `subject` và authorization context | Ràng buộc danh tính/ủy quyền đã được AS xác nhận |
| `granted_scopes` và `resource` | Chỉ cấp quyền đã được chấp thuận |
| `expires_at` | Giới hạn thời gian đổi mã |
| `consumed_at` hoặc trạng thái sử dụng | Ngăn code được đổi nhiều lần |

Đây là **metadata minh họa**, không phải schema cố định của OAuth. AS có thể lưu server-side, dùng mã có tính toàn vẹn và trạng thái an toàn, hoặc kết hợp các cơ chế, miễn thực thi đủ ràng buộc.

### 5.2. Token endpoint phải làm gì khi đổi code?

Ví dụ request từ public client dùng PKCE:

~~~http
POST /oauth2/token HTTP/1.1
Host: login.example.com
Content-Type: application/x-www-form-urlencoded

grant_type=authorization_code&code=<AUTHORIZATION_CODE>&redirect_uri=https%3A%2F%2Fapp.example.com%2Fcallback&client_id=shop-web&code_verifier=<CODE_VERIFIER>
~~~

Đây là request minh họa. Với confidential client, token endpoint còn phải **xác thực client bằng phương thức đã đăng ký**; chỉ gửi `client_id` là không đủ để chứng minh một confidential client.

AS cần:

1. Kiểm tra grant type được phép cho client.
2. Xác thực confidential client nếu áp dụng; xác định public client theo client registration mà không giả vờ nó có thể giữ secret.
3. Xác minh code tồn tại, còn hạn và chưa bị tiêu thụ.
4. Kiểm tra code thuộc **đúng client** và redirect URI khớp yêu cầu authorization ban đầu theo quy tắc OAuth.
5. Kiểm tra `code_verifier` đúng challenge và phương thức PKCE đã đăng ký trên code.
6. Chỉ cấp subject, scope và audience đã được phép; không lấy quyền mới từ dữ liệu token request tự khai.
7. **Tiêu thụ code theo thao tác nguyên tử**, tránh hai request đồng thời cùng đổi một mã.

Nếu code được dùng lại, AS phải từ chối và áp dụng biện pháp xử lý liên quan theo chính sách; RFC 6749 yêu cầu không chấp nhận code hơn một lần và nêu việc thu hồi token dựa trên code đó khi có thể. Không dùng cơ chế "kiểm tra code chưa dùng rồi cập nhật trạng thái sau" thiếu đồng bộ, vì hai request đua nhau có thể cùng đi qua bước kiểm tra.

### 5.3. PKCE không thay thế các kiểm tra khác

PKCE không tự:

- Xác thực người dùng hoặc bảo đảm consent đúng.
- Xác thực confidential client thay cho client authentication.
- Kiểm tra audience/scope hoặc quyền theo resource.
- Bảo vệ access token sau khi token đã bị lộ.
- Sửa redirect URI sai, client mix-up hoặc open redirect.

Các cơ chế này cần được phối hợp, và AS nên ngăn **PKCE downgrade/stripping**: không cho một code vốn được cấp theo luồng có challenge bị đổi như thể không có PKCE.

## 6. Phân biệt public client và confidential client

| Loại client | Ví dụ | Đặc điểm xác thực tại token endpoint |
|---|---|---|
| **Public** | SPA, mobile/native app | Không giữ được shared secret dài hạn đáng tin; Authorization Code + PKCE, xác thực và ràng buộc theo profile |
| **Confidential** | Backend kiểm soát bởi tổ chức | Có thể giữ secret/khóa riêng và xác thực tại token endpoint bằng phương thức AS cho phép |

**`client_id` là định danh, không phải bí mật.** Ai cũng có thể nhìn thấy một client_id trên authorization request; chỉ cung cấp client_id không chứng minh người gửi là ứng dụng hợp lệ.

### 6.1. Các cách xác thực confidential client

- **client_secret_basic:** dùng secret được cấp, truyền qua HTTP Basic theo OAuth và TLS. Secret cần được lưu trong secret manager, không hard-code vào SPA/mobile.
- **private_key_jwt:** client chứng minh quyền sở hữu khóa riêng bằng một JWT client assertion được ký đúng, có audience/token endpoint và thời gian hợp lệ theo profile. AS phải kiểm tra assertion và chống replay theo chính sách.
- **mTLS client authentication (RFC 8705):** xác thực client bằng chứng chỉ TLS theo registration và chính sách hạ tầng.

Việc hỗ trợ phương thức nào do AS và client registration quyết định. Không được chấp nhận một phương thức yếu như fallback tự động nếu client đã đăng ký phương thức mạnh hơn mà không có chính sách rõ ràng.

### 6.2. Client secret không phải access token

Client secret dùng để **xác thực client khi xin token**; access token dùng để **gọi resource server**. Không gửi client secret tới Orders API thay bearer access token. Không dùng secret toàn hệ thống trong ứng dụng mobile hoặc JavaScript tải về trình duyệt: người dùng có thể trích xuất được.

Public client vẫn có thể được AS cấp token khi hoàn tất một luồng được thiết kế đúng; điều đó không có nghĩa ứng dụng công khai tự có bằng chứng bí mật mạnh về danh tính phần mềm đang chạy trên thiết bị người dùng.

## 7. Bảo vệ token endpoint theo từng grant

Các yêu cầu phát hành khác nhau phải đi qua **policy grant riêng**. Không được để cùng endpoint tự suy loại quyền từ một tham số không đáng tin mà bỏ qua ràng buộc.

### 7.1. Authorization Code

Áp dụng các kiểm tra **client, code dùng một lần, redirect URI, PKCE, grant, scope/audience** đã nêu. Một token request không thể chỉ gửi `sub=user123` rồi buộc AS cấp access token đại diện người dùng đó.

### 7.2. Client Credentials

Trong OAuth 2.0, Client Credentials Grant phù hợp cho confidential client thực hiện công việc theo quyền **của chính ứng dụng**. Ví dụ:

~~~http
POST /oauth2/token HTTP/1.1
Host: login.example.com
Authorization: Basic <BASE64_OF_REGISTERED_CLIENT_CREDENTIALS>
Content-Type: application/x-www-form-urlencoded

grant_type=client_credentials&scope=inventory%3Aread
~~~

Ví dụ chỉ để học. AS phải xác thực client, xác minh grant được cấp cho client đó và giới hạn scope/resource theo chính sách của workload. Không tự gán `sub` là người dùng đang đăng nhập hoặc cho phép một client dùng service token thay người dùng ngoài phạm vi ủy quyền.

Không nên cấp refresh token trong Client Credentials Grant theo mô hình OAuth 2.0 thông thường; confidential client có thể xác thực lại với token endpoint để lấy access token mới.

### 7.3. Refresh Token

Ví dụ request:

~~~http
POST /oauth2/token HTTP/1.1
Host: login.example.com
Content-Type: application/x-www-form-urlencoded

grant_type=refresh_token&refresh_token=<REFRESH_TOKEN>&client_id=shop-web
~~~

Với confidential client, request còn phải xác thực client theo registration. Với public client, cách ràng buộc refresh token và bảo vệ replay phải tuân theo chính sách hiện đại, ví dụ **refresh token rotation** hoặc **sender-constrained refresh token** khi profile/hạ tầng hỗ trợ.

AS cần kiểm tra:

1. Refresh token có thực, còn hiệu lực, không bị thu hồi, đúng client và grant.
2. Client có quyền sử dụng refresh token theo loại client và phương thức xác thực được cấu hình.
3. Scope xin mới **không vượt quá scope đã được cấp cho grant ban đầu**; audience/resource không được tự mở rộng.
4. Quyền người dùng hoặc quyền workload còn phù hợp với policy hiện tại.
5. Nếu dùng rotation, cập nhật token cũ và token mới theo một quy trình nguyên tử; nhận diện việc refresh token cũ bị dùng lại.

Refresh token **không gửi tới resource server** và không dùng thay access token. Khi phát hiện reuse, AS nên áp dụng chiến lược thu hồi token family/grant và yêu cầu authorization lại theo threat model; tránh để token cũ tiếp tục tạo access token sau khi bị thay thế.

### 7.4. Những grant không nên bật vô điều kiện

Các grant cũ hoặc không phù hợp với loại client có thể tạo rủi ro cao. Ví dụ Resource Owner Password Credentials Grant (ROPC) không được khuyến nghị trong thực hành bảo mật OAuth hiện đại. Nên sử dụng Authorization Code + PKCE cho ứng dụng có tương tác người dùng, client credentials cho workload đủ điều kiện, hoặc các grant mở rộng chỉ khi AS triển khai và bảo vệ rõ ràng.

Không mở một grant chỉ vì client gửi `grant_type` với tên tương ứng; phải **allowlist grant theo từng client**.

## 8. Chỉ phát hành đúng scope, audience và subject

Token endpoint là nơi dễ xảy ra **privilege escalation** nếu AS cấp quyền theo dữ liệu client tự khai. Ví dụ client gửi:

~~~text
scope = orders:read orders:admin
resource = https://payments.example.com
requested_subject = ceo-user
~~~

AS không được cấp quyền admin, Payments API hoặc subject tùy chọn chỉ vì các tham số này hiện diện. AS cần xác minh **grant đã được cấp, danh tính/actor, đăng ký client, resource được phép, tenant và chính sách ủy quyền**.

### 8.1. Quyền được cấp không mặc nhiên bằng quyền được yêu cầu

Giả sử client được cấp phép `orders:read` nhưng request `orders:read orders:delete`. AS phải từ chối hoặc giới hạn về phạm vi được phép theo hợp đồng. Client cần kiểm tra scope thực tế được cấp; việc không được cấp quyền delete không cho phép client tự coi access token có quyền delete.

### 8.2. Audience giúp chống dùng token sai dịch vụ

Resource indicator (RFC 8707) cho phép client yêu cầu token cho resource cụ thể khi AS hỗ trợ. AS phải áp chính sách xem **client/grant có được phép xin token cho resource đó không**; resource server phải kiểm tra `aud` dành cho chính mình.

~~~text
Access token cho Orders API:
    iss   = https://login.example.com
    aud   = https://orders.example.com
    scope = orders:read

Access token cho Payments API:
    aud   = https://payments.example.com
    scope = payments:read
~~~

Một JWT có chữ ký hợp lệ cho Orders API **không tự hợp lệ** ở Payments API. Nếu Orders API cần gọi Payments API, nó phải sử dụng một access token downstream đúng audience, phù hợp với client credentials hoặc token exchange/on-behalf-of theo kiến trúc.

### 8.3. Subject, client và actor

**Subject (`sub`)** có thể là người dùng hoặc service account tùy loại token/grant. **Client (`client_id`)** là ứng dụng được cấp token, không tự đồng nghĩa với user. Trong delegation hoặc token exchange, actor có thể được biểu diễn theo profile cụ thể. AS cần duy trì sự tách biệt này để không biến quyền của ứng dụng thành quyền của người dùng.

Một access token có scope phù hợp vẫn không tự chứng minh quyền đọc một đơn hàng cụ thể; resource server phải đánh giá ownership, tenant, relationship và action theo dữ liệu nghiệp vụ.

## 9. Tạo access token an toàn: JWT và opaque

### 9.1. Nếu cấp JWT access token

AS cần:

- Chọn thuật toán ký được cho phép, sử dụng khóa ký được bảo vệ bằng KMS/HSM hoặc hạ tầng quản lý khóa thích hợp.
- Phát hành claims đúng hợp đồng, bao gồm issuer, subject, audience, thời điểm phát hành/hết hạn và các claim profile yêu cầu.
- Giới hạn TTL theo rủi ro; không dùng token sống quá dài chỉ để tránh refresh.
- Không nhúng secret, mật khẩu, dữ liệu cá nhân không cần thiết vào payload; JWT ký **không đồng nghĩa mã hóa**.
- Quản lý `kid` và JWKS công khai với quy trình rotation; RS chỉ dùng khóa thuộc **issuer đã tin cậy**, không tải khóa từ URL tùy ý trong token chưa được xác minh.
- Dùng token typing/profile khi cần để resource server không nhầm access token với ID token hoặc token loại khác.

Ví dụ payload JWT access token **minh họa**:

~~~json
{
  "iss": "https://login.example.com",
  "sub": "user-271",
  "aud": ["https://orders.example.com"],
  "client_id": "shop-web",
  "scope": "orders:read",
  "iat": 1893492000,
  "exp": 1893492900,
  "jti": "at-18f0c5"
}
~~~

Đây không phải một JWT được ký và không chứa credential có thể dùng. Các NumericDate trong ví dụ là giây UTC.

### 9.2. Nếu cấp opaque access token

AS có thể sinh một chuỗi ngẫu nhiên mật mã có entropy đủ mạnh, liên kết với metadata phía server như issuer, client, subject, scope, audience, expiry và trạng thái thu hồi. RS dùng **introspection** hoặc cơ chế kiểm tra khác đã được thỏa thuận; không giả định opaque token có claims đọc được.

Ưu điểm có thể là kiểm soát trạng thái gần phía server hơn; chi phí có thể là phụ thuộc vào endpoint kiểm tra và cache. Một JWT có chữ ký và một opaque token đều phải được **cấp đúng quyền**; chọn định dạng không thay thế logic authorization tại AS.

### 9.3. Phân biệt access, ID và refresh token

| Token | Ai dùng và ở đâu? | Quy tắc quan trọng tại điểm phát hành |
|---|---|---|
| **Access token** | Client gọi resource server đúng audience | Cấp scope/resource đúng grant, TTL và token type |
| **ID token (OIDC)** | Client xác minh thông tin đăng nhập | Cấp theo OIDC, audience là client, claims/nonce theo yêu cầu; không dùng làm access token API |
| **Refresh token** | Client gọi token endpoint để lấy token mới | Ràng buộc client/grant, bảo vệ rotation/replay, không gửi tới resource server |

Một hệ thống có thể cấp ID token và access token trong cùng một token response OIDC, nhưng **mục đích và bên nhận của chúng khác nhau**. Không lấy ID token có chữ ký đúng để thay bearer access token cho Orders API.

## 10. Bảo vệ đường truyền, response và lưu trữ bí mật

### 10.1. TLS và vị trí truyền credential

- Authorization Server và client phải dùng **HTTPS/TLS** đúng cấu hình khi truyền credential, ngoài những ngoại lệ phát triển/native loopback được giao thức cho phép.
- Với token endpoint, truyền các tham số grant trong **HTTP POST** theo giao thức, không đưa refresh token hoặc client secret vào query string.
- Không ghi code, token, client secret hoặc assertion bí mật vào log, URL, crash report, telemetry hay trace.
- Không dùng redirect URL để trả access token trực tiếp khi có thể dùng Authorization Code + PKCE; tránh các luồng lộ token qua fragment/URL.
- Khi token response chứa token/secret, áp header chống cache phù hợp, ví dụ **Cache-Control: no-store** và **Pragma: no-cache** theo OAuth 2.0.

Response minh họa:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store
Pragma: no-cache

{
  "access_token": "<ACCESS_TOKEN>",
  "token_type": "Bearer",
  "expires_in": 900,
  "scope": "orders:read"
}
~~~

`expires_in` là **khoảng thời gian tương đối theo giây** trong response OAuth; claim `exp` trong JWT là **mốc thời gian tuyệt đối theo NumericDate**. Không trộn đơn vị giây/mili giây khi tính TTL.

### 10.2. CORS không phải cơ chế cấp quyền

Một token endpoint có thể phục vụ public browser client theo kiến trúc và cấu hình CORS thích hợp. Không cấu hình CORS quá rộng rồi xem nó là biện pháp xác thực. **CORS chỉ giới hạn một số truy cập từ trình duyệt**, không ngăn client ngoài trình duyệt gửi HTTP request. Quy tắc xác thực client, PKCE, grant, scope và audience vẫn bắt buộc.

### 10.3. Kho bí mật và key rotation

Client secret, private key ký client assertion, refresh token và khóa ký của AS cần được giữ trong kho bảo vệ phù hợp với kiến trúc, giới hạn quyền truy cập và audit. Với khóa ký JWT của AS, cần chuẩn bị:

1. Phát hành/đưa khóa mới vào hạ tầng tin cậy.
2. Công bố khóa công khai tương ứng theo JWKS/metadata.
3. Chuyển khóa ký sang khóa mới và giữ khóa cũ đủ lâu để RS xác minh các token cũ còn hạn theo chính sách.
4. Gỡ khóa cũ khi không còn cần xác minh token hợp lệ, hoặc ứng cứu khẩn cấp nếu khóa bị lộ.

Không thể chỉ xóa khóa cũ ngay sau khi đổi khóa ký mà không xét token đã cấp và cache JWKS của resource server. Khi khóa bí mật bị lộ, chiến lược xử lý sẽ khác luồng rotation định kỳ.

## 11. Rate limit, brute force và khả năng phục hồi

Endpoint phát hành thường là mục tiêu của credential stuffing, đoán mã, replay và DoS. Cần các kiểm soát phù hợp:

| Bề mặt | Biện pháp |
|---|---|
| Login/authorization | Bảo vệ phiên, rate limit theo nhiều chiều, phát hiện hành vi bất thường, tránh account enumeration |
| Đổi authorization code | Code ngẫu nhiên đủ mạnh, TTL ngắn, single-use, PKCE, giới hạn lỗi và giám sát |
| Token endpoint | Rate limit/quota theo client, workload, nguồn truy cập và loại grant; kiểm soát tài nguyên xác thực |
| Refresh token | Rotation hoặc sender constraint, phát hiện reuse, giới hạn tần suất và vòng đời grant |
| Client assertion | Kiểm tra signature/audience/time/jti theo profile; phát hiện replay |
| Metadata/JWKS/introspection | Caching, giới hạn tài nguyên và chống truy vấn lặp gây quá tải |

**Rate limiting là biện pháp bổ sung, không thay cho xác thực đúng.** Một attacker có nhiều IP có thể vượt qua giới hạn theo IP; đồng thời chặn cứng theo mỗi IP có thể gây ảnh hưởng người dùng hợp lệ sau NAT. Thiết kế cần cân bằng bảo mật và khả năng sử dụng, kèm metric và cảnh báo.

### 11.1. Phản hồi lỗi không làm lộ credential

Các lỗi token endpoint theo OAuth có thể gồm:

| Lỗi | Tình huống điển hình |
|---|---|
| `invalid_request` | Thiếu hoặc sai tham số bắt buộc, request không hợp lệ |
| `invalid_client` | Client authentication thất bại |
| `invalid_grant` | Code/refresh token sai, hết hạn, đã dùng hoặc không thuộc client |
| `unauthorized_client` | Client không được dùng grant này |
| `unsupported_grant_type` | Grant type không được AS hỗ trợ |
| `invalid_scope` | Scope không hợp lệ, không biết hoặc vượt phạm vi được phép |

HTTP status và header phải tuân thủ đặc tả/contract của AS, ví dụ `invalid_client` có quy tắc phản hồi và WWW-Authenticate riêng khi client dùng header Authorization. Không trả secret, code, token, user existence hoặc dữ liệu nội bộ nhạy cảm trong error description. Audit metadata nên đủ để xác định nguyên nhân mà không ghi credential nguyên văn.

## 12. Ví dụ thiết kế lớp cấp token bằng Java

Đoạn mã sau là **pseudocode** mô tả trách nhiệm của token endpoint. Các kiểu `ClientRegistration`, `AuthorizationGrant`, `IssuancePolicy`, `AtomicGrantStore` và `TokenService` là lớp giả định, **không phải API sẵn có** của Spring Security hoặc Spring Authorization Server.

### 12.1. Ví dụ sai: phát hành token theo dữ liệu client tự khai

~~~java
// VÍ DỤ SAI: không có ràng buộc client/grant và cấp scope tùy ý.
TokenResponse issueToken(TokenRequest request) {
    String subject = request.getParameter("sub");
    String scope = request.getParameter("scope");
    String audience = request.getParameter("aud");
    return tokenService.signAccessToken(subject, scope, audience);
}
~~~

Đây là lỗi nghiêm trọng: attacker có thể tự yêu cầu subject, scope và audience không thuộc quyền của mình. Việc token được ký bằng private key thật của AS **không sửa được** quyết định phát hành sai.

### 12.2. Ví dụ đúng về nguyên tắc

~~~java
// Pseudocode kiến trúc. Không tự triển khai cryptography/protocol từ đầu.
TokenResponse exchangeAuthorizationCode(
        HttpRequest request,
        Instant now) {

    ClientRegistration client =
        clientAuthenticator.resolveAndAuthenticate(request);

    require(client.allowedGrantTypes().contains("authorization_code"));

    AuthorizationGrant grant = grantStore.find(request.code());
    require(grant != null);
    require(!grant.isExpiredAt(now));
    require(grant.clientId().equals(client.clientId()));
    require(redirectPolicy.matchesOriginalRequest(
        grant.redirectUri(), request.redirectUri()
    ));
    require(pkcePolicy.matchesChallenge(
        grant.codeChallenge(),
        grant.codeChallengeMethod(),
        request.codeVerifier()
    ));

    // Kiểm tra/grant bị tiêu thụ theo thao tác nguyên tử.
    require(grantStore.consumeOnce(grant.id(), now));

    ApprovedAuthority authority = issuancePolicy.evaluate(
        client,
        grant.subject(),
        grant.grantedScopes(),
        grant.allowedResources()
    );
    require(authority.isAllowed());

    return tokenService.issueForApprovedAuthority(authority);
}
~~~

Trong triển khai thực tế, **các kiểm tra/tiêu thụ code phải có tính nguyên tử** trước các đường cấp phát nhạy cảm; cần cơ chế idempotency/replay handling an toàn cho tình huống hai request đồng thời. Authorization Server framework đáng tin cậy nên quản lý phần lớn trách nhiệm này; ví dụ nhằm chỉ rõ các điều kiện phải có, không phải mã production chạy được nguyên văn.

### 12.3. Kiểm tra refresh token theo grant gốc

~~~java
// Pseudocode: phạm vi refresh chỉ được giữ nguyên hoặc giảm.
TokenResponse refresh(VerifiedClient client, String refreshToken, Set<String> requested) {
    RefreshGrant grant = refreshStore.findAndVerify(refreshToken);
    require(grant != null && grant.isActive());
    require(grant.clientId().equals(client.id()));
    require(grant.grantedScopes().containsAll(requested));
    require(grant.resourcePolicy().allowsRequestedResources());

    // Nếu dùng rotation: thay token một lần và phát hiện token cũ tái sử dụng.
    require(refreshStore.rotateAtomically(grant));
    return tokenService.issueWithinGrant(grant, requested);
}
~~~

Điều kiện `requested` phải được xử lý theo quy tắc của OAuth: nếu client không gửi scope, sử dụng phạm vi grant ban đầu theo contract thay vì tập rỗng tùy tiện. Kiểu này còn phải kiểm tra cách client xác thực, token binding, trạng thái người dùng, consent, thời gian sống, audience và xử lý replay. **Đây chỉ là sơ đồ trách nhiệm, không thay thế thư viện OAuth được duy trì**.

## 13. Spring Authorization Server và Spring Security trong kiến trúc

Trong hệ sinh thái Java, có thể dùng:

- **Spring Authorization Server** để quản lý các endpoint OAuth/OIDC, client registration, xác thực client, token generation, grants và những extension theo khả năng/version của framework.
- **Spring Security OAuth2 Client** cho những ứng dụng cần thực hiện luồng OAuth như authorization code hoặc client credentials.
- **Spring Security OAuth2 Resource Server** cho API kiểm tra JWT/opaque access token và ánh xạ quyền.

Đây là **ba vai trò cấu hình khác nhau**. Khi triển khai AS, không nên tự ghép một endpoint `POST /token` thủ công chỉ nhận email/password rồi trả JWT và gọi đó là OAuth 2.0.

### 13.1. Những cấu hình cần được kiểm tra khi triển khai

| Chủ đề | Câu hỏi kiểm tra |
|---|---|
| Đăng ký client | Client có đúng type, grant, redirect URI, token endpoint authentication method? |
| Authorization Code | AS có thực thi PKCE, redirect/client binding và single-use không? |
| Client Credentials | Chỉ client thích hợp được grant? Scope/audience của workload được giới hạn? |
| Refresh Token | Rotation hoặc sender constraint, reuse detection, client/grant binding đã được cấu hình? |
| Token generation | Issuer, audience, subject, scopes, iat/exp và thuật toán/khóa đúng hợp đồng? |
| Consent/approval | Quyền nhạy cảm được cấp theo policy và tránh cấp vượt yêu cầu? |
| Resource Server | API có kiểm tra issuer, chữ ký/active, audience, hạn và authorization trên resource/action không? |
| Vận hành | Secrets/JWKS rotation, logging, rate limit, metrics, backup và phản ứng sự cố đầy đủ? |

Không nên giả định framework tự kiểm tra **mọi audience của API nghiệp vụ** chỉ vì cấu hình issuer. Authorization Server phải cấp audience theo hợp đồng; resource server cần validator audience và policy phù hợp.

## 14. Checklist kiểm thử endpoint phát hành

### 14.1. Kiểm thử authorization code và PKCE

| Test | Kết quả mong muốn |
|---|---|
| Code hợp lệ, đúng client, redirect URI, PKCE, chưa dùng | Có thể cấp token theo grant và policy |
| Code đã dùng lần thứ hai | Từ chối, áp phản ứng replay |
| Hai request đổi cùng code gần như đồng thời | Tối đa một request đổi thành công |
| Code hết hạn | Từ chối `invalid_grant` hoặc lỗi tương ứng |
| Code của client A đem đổi ở client B | Từ chối |
| Code có challenge nhưng thiếu/sai verifier | Từ chối |
| Thay S256 bằng plain hoặc bỏ PKCE trái profile | Từ chối; không downgrade |
| Redirect URI khác request gốc | Từ chối |
| Authorization redirect sang URI không đăng ký | Từ chối |
| Callback có state sai hoặc từ issuer khác | Client từ chối và không đổi code |

### 14.2. Kiểm thử client authentication và grants

| Test | Kết quả mong muốn |
|---|---|
| Confidential client thiếu/sai secret hoặc assertion | Không cấp token |
| Client đăng ký private_key_jwt nhưng gửi phương thức không cho phép | Từ chối |
| Public client gửi client_id và giả vờ là confidential | Không được coi là đã xác thực client bí mật |
| Public client xin client_credentials trái cấu hình | Từ chối |
| Client A xin scope thuộc client B | Không cấp scope ngoài quyền |
| Client được cấp Orders API nhưng yêu cầu token cho Payments API | Không cấp nếu audience/resource không được phép |
| Client tự gửi `sub=admin` | Không thay đổi chủ thể đã được AS xác nhận |
| ID token được dùng như access token ở API | Resource server từ chối |
| Refresh token của client A gửi bởi client B | Từ chối |
| Refresh token cũ đã rotation được sử dụng lại | Phát hiện replay và xử lý grant/family theo policy |
| Refresh token chỉ có grant read được dùng để xin delete | Không mở rộng quyền |

### 14.3. Kiểm thử vận hành

- **TLS:** endpoint từ chối hoặc chuyển hướng an toàn request không được bảo vệ theo kiến trúc; không làm lộ body chứa secret qua redirect.
- **Response:** có header không cache; token không lọt vào log, query string, referrer hay telemetry.
- **Rate limit:** áp theo client và ngữ cảnh, không dễ vượt bằng nhiều request song song.
- **Key rotation:** token cũ hợp lệ được xác minh trong thời gian cho phép; token ký bằng khóa không tin cậy bị từ chối.
- **Clock skew:** token có `nbf`, `iat`, `exp` bất thường được xử lý theo policy và leeway nhỏ.
- **JWT/opaque:** mỗi loại được xác minh đúng profile; opaque token không bị giải mã và tin như JWT tự chế.
- **Quyền đã thu hồi:** hệ thống phản ứng theo TTL, introspection/cache và chính sách revocation đã công bố.
- **Multi-tenant:** không dùng grant tenant A để phát token với quyền của tenant B.
- **Quan sát:** audit các lần cấp/từ chối theo metadata an toàn, không lưu token nguyên văn.

## 15. Phản ứng sự cố khi endpoint phát hành bị lạm dụng

| Dấu hiệu | Hành động cần cân nhắc |
|---|---|
| Client secret bị lộ | Thu hồi/rotate secret, kiểm tra lịch sử cấp token cho client, giới hạn scope và truy cập |
| Refresh token reuse | Chặn token family/grant theo chính sách, yêu cầu đăng nhập/ủy quyền lại, điều tra nguồn lộ |
| Code bị dùng lại nhiều lần | Kiểm tra PKCE, redirect, replay và tính nguyên tử của code store |
| AS ký token có audience/scope sai | Ngừng cấp phát lỗi, đánh giá phạm vi ảnh hưởng, thu hồi/chặn token nếu cần |
| Khóa ký AS nghi bị lộ | Áp quy trình key compromise, thay khóa và phối hợp RS cập nhật tập khóa tin cậy |
| Brute force hoặc DoS trên token endpoint | Rate limit, bảo vệ hạ tầng, điều tra mẫu client/nguồn và bảo đảm người dùng hợp lệ vẫn truy cập |

Trong báo cáo sự cố, cần phân biệt **access token hết hạn**, **refresh token bị thu hồi** và **chính sách quyền nghiệp vụ thay đổi**. Thu hồi refresh token không đảm bảo JWT access token được xác minh offline mất hiệu lực tức thời. Ngược lại, một token còn hạn không nhất thiết được phép đọc resource sau khi user mất membership.

## 16. Các sai lầm phổ biến

| Sai lầm | Vì sao nguy hiểm | Cách xử lý |
|---|---|---|
| Token endpoint chỉ kiểm tra client_id | Client_id không phải secret | Xác thực confidential client đúng method; public client dùng flow/PKCE phù hợp |
| Dùng authorization code nhiều lần | Cấp nhiều token từ cùng grant không hợp lệ | Code single-use và tiêu thụ nguyên tử |
| Bỏ qua PKCE verifier khi đổi code | Cho phép code interception | Kiểm tra challenge/verifier đã ràng buộc |
| Redirect URI so prefix/wildcard | Code có thể lọt sang attacker | Chính sách exact-match theo profile |
| Client request scope nào được cấp scope đó | Privilege escalation | Ràng buộc client, grant, consent và policy |
| Cho client tùy ý chọn subject/audience | Token hợp lệ chữ ký nhưng sai thẩm quyền | Derive claims từ ngữ cảnh đã xác minh |
| Refresh token được dùng lại vô hạn không phát hiện | Kẻ giữ token cũ duy trì phiên | Rotation/sender constraint và reuse detection |
| Lưu client secret trong SPA/mobile | Secret bị trích xuất | Phân loại public client; PKCE |
| Ghi raw token vào log | Rò rỉ credential | Redaction, chỉ log metadata |
| JWT ký đúng nên AS không cần kiểm soát scope | Resource server tin token AS cấp | Policy cấp quyền phải đúng trước khi ký |
| Resource server chỉ kiểm tra chữ ký | Token sai issuer/aud hoặc sai loại vẫn được nhận | JWT/opaque validation đầy đủ và quyền resource/action |
| CORS được xem là authentication | HTTP client ngoài browser không bị CORS chặn | Xác thực grant/client độc lập |
| Dùng ID token gọi API | Token sai mục đích/audience | API chỉ chấp nhận access token đúng profile |
| Thu hồi refresh token rồi cho rằng access token cũ đã biến mất | JWT offline có thể còn hạn | TTL và cơ chế revoke/chặn khi cần |

## 17. Tình huống tự kiểm tra

### Tình huống A: code bị đánh cắp

Một authorization code bị lộ trên thiết bị người dùng. Kẻ tấn công thử đổi code tại token endpoint nhưng không có `code_verifier` đúng.

**Kết quả mong muốn?** Token endpoint từ chối. PKCE S256 giúp code bị chặn khó đổi thành token nếu verifier vẫn được bảo vệ. AS vẫn phải kiểm tra client, redirect URI và code single-use.

### Tình huống B: client xác thực thành công nhưng xin quá scope

Backend A dùng client secret đúng và xin `orders:read orders:delete`, trong khi client chỉ được phê duyệt quyền đọc.

**AS có nên cấp quyền delete?** Không. Client authentication chỉ chứng minh ứng dụng, không chứng minh quyền xóa. AS phải từ chối hoặc giới hạn theo grant/policy và thể hiện scope thực sự được cấp.

### Tình huống C: refresh token reuse

Client hợp lệ đổi refresh token `R1` lấy `R2`. Một bên khác tiếp tục gửi `R1`.

**Có thể bỏ qua vì `R1` đã không còn hợp lệ?** Không nên bỏ qua sự kiện như một lỗi bình thường. Nếu dùng rotation, việc dùng lại là tín hiệu có thể đã lộ credential. AS cần áp dụng cơ chế phát hiện replay và phản ứng với grant/token family theo chính sách.

### Tình huống D: token đúng chữ ký, sai audience

AS cấp access token có `aud=https://orders.example.com`, client đem gọi Billing API.

**Billing API có nên chấp nhận vì tin issuer?** Không. Billing phải xác minh token được phát hành cho chính mình. Chữ ký hợp lệ không thay thế kiểm tra audience.

### Tình huống E: scope mới sau refresh

Client được cấp grant `reports:read` và có refresh token còn hạn. Nó thử xin `reports:export` qua refresh request.

**Có được cấp không?** Không chỉ vì refresh token còn hạn. Client phải được cấp thêm quyền qua cơ chế ủy quyền/chính sách thích hợp; refresh không được tự mở rộng grant ban đầu.

### Tình huống F: OIDC ID token

Sau khi đăng nhập, client nhận ID token có `aud=shop-web` và dùng nó làm bearer token gọi Orders API.

**API phải làm gì?** Từ chối token sai mục đích. ID token dành cho client xác minh kết quả đăng nhập, còn API phải nhận access token đúng audience và profile.

### Tình huống G: cả hệ thống đã đổi khóa ký

AS thay khóa ký mới. Một số resource server vẫn cache JWKS cũ; access token mới bị từ chối.

**Bài học vận hành?** Phải chuẩn bị công bố khóa công khai, cache/rotation và thời gian đồng tồn tại phù hợp trước khi chuyển khóa ký. Với khóa bị lộ, dùng quy trình ứng cứu khác có thể phải thu hồi gấp.

### Tình huống H: public client có "client secret"

SPA được đưa một `client_secret` ngay trong JavaScript bundle rồi dùng client credentials.

**Có bảo mật như confidential client không?** Không. Mọi người dùng có thể xem bundle và lấy secret. Client cần được đăng ký là public và dùng luồng phù hợp, ví dụ Authorization Code + PKCE cho người dùng.

## 18. Ghi nhớ

Khi đánh giá endpoint phát hành, hãy đặt sáu câu hỏi theo thứ tự:

1. **Ai là client và user/actor?** Client được xác thực theo đúng loại, danh tính người dùng được xác nhận khi luồng yêu cầu?
2. **Grant nào được dùng?** Authorization code được ràng buộc với client/redirect/PKCE và chỉ dùng một lần? Refresh token còn hợp lệ, đúng client và được chống replay?
3. **Có được quyền này không?** Scope, audience, subject, tenant và consent/grant có nằm trong chính sách?
4. **Token được tạo đúng không?** JWT hoặc opaque, issuer, audience, `iat`/`exp`, thuật toán và khóa, TTL, token type đều phù hợp?
5. **Credential có được bảo vệ khi truyền và lưu?** TLS, secret manager, header chống cache, log redaction, không đưa token vào URL?
6. **Có thể giám sát và thu hồi không?** Rate limit, replay detection, audit, refresh rotation, key rotation và kế hoạch xử lý token đã cấp?

**Bảo vệ endpoint phát hành là bảo vệ điểm chuyển một yêu cầu thành một quyền có thể được sử dụng ở nhiều dịch vụ.** Chỉ ký JWT đúng là chưa đủ: AS phải phát hành đúng chủ thể, client, resource và scope; client phải giữ credential an toàn; resource server phải kiểm tra token và quyền trên tài nguyên cụ thể trong toàn bộ vòng đời.

## Tài liệu tham khảo

- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): authorization endpoint, token endpoint, grants, client authentication và scope.
- [RFC 7636 — Proof Key for Code Exchange by OAuth Public Clients](https://www.rfc-editor.org/rfc/rfc7636): PKCE, code_verifier và S256.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700): thực hành bảo mật OAuth, PKCE, redirect, refresh token và chống mix-up.
- [RFC 9207 — OAuth 2.0 Authorization Server Issuer Identification](https://www.rfc-editor.org/rfc/rfc9207): issuer trong authorization response để phòng chống mix-up.
- [RFC 9126 — OAuth 2.0 Pushed Authorization Requests](https://www.rfc-editor.org/rfc/rfc9126): cách bảo vệ và ràng buộc authorization request qua PAR khi áp dụng.
- [RFC 8707 — Resource Indicators for OAuth 2.0](https://www.rfc-editor.org/rfc/rfc8707): yêu cầu access token cho resource/audience.
- [RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens](https://www.rfc-editor.org/rfc/rfc8705): xác thực client và sender-constrained token bằng mTLS.
- [RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449): ràng buộc bên gửi và chống replay cho OAuth token.
- [RFC 8693 — OAuth 2.0 Token Exchange](https://www.rfc-editor.org/rfc/rfc8693): token downstream, actor và policy delegation.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): claims, token typing và kiểm tra JWT access token.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): xác minh trạng thái opaque token.
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009): endpoint thu hồi token.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): ID token, nonce, issuer, audience và quy tắc xác thực OIDC.
- [Spring Authorization Server Reference](https://docs.spring.io/spring-authorization-server/reference/): framework Authorization Server và cấu hình các endpoint OAuth/OIDC.
