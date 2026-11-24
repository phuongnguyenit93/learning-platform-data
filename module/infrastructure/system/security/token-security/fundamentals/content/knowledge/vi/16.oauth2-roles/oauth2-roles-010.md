# Điểm cuối token

Một ứng dụng vừa nhận được **authorization code** sau khi người dùng đăng nhập. Ứng dụng có thể lấy code ấy gọi thẳng Orders API để xem đơn hàng không? **Không.** Authorization code chỉ là một chứng cứ ngắn hạn để client **đổi lấy token tại điểm cuối token (token endpoint)** của **Authorization Server**. Sau khi Authorization Server kiểm tra client, code, PKCE và các điều kiện cấp quyền, nó mới có thể trả **access token** để client gọi Resource Server.

**Token endpoint** là cổng giao thức quan trọng trong OAuth 2.0: tại đây, client gửi một **grant** hoặc credential được quy định để yêu cầu cấp token; Authorization Server xác minh các điều kiện và quyết định **có cấp token hay từ chối**. Điểm cuối này cũng thường nhận **refresh token grant** để cấp access token mới và **client credentials grant** cho truy cập máy–máy.

Bài thuộc chương **OAuth2 roles** của module **SECURITY_TOKEN_SECURITY_FUNDAMENTALS**. Mục tiêu là liên hệ các vai trò OAuth 2.0/OIDC với vòng đời access token, refresh token, JWT và opaque token: phát hành, kiểm tra claims, scope/audience, bảo vệ đường truyền, lưu trữ, thu hồi và hạn chế credential bị đánh cắp hoặc phát lại.

Sau bài học, bạn sẽ phân biệt token endpoint với các endpoint khác, đọc được HTTP request/response của những grant thông dụng, hiểu điều kiện kiểm tra trước khi cấp token, biết xử lý lỗi và thiết kế client/Authorization Server tránh token substitution, replay và lộ bí mật.

## 1. Token endpoint nằm ở đâu trong bốn vai trò OAuth 2.0?

OAuth 2.0 mô tả các vai trò:

| Vai trò | Trách nhiệm | Quan hệ với token endpoint |
|---|---|---|
| **Resource Owner** | Chủ thể có quyền với tài nguyên, thường là người dùng | Có thể xác thực/ủy quyền trong flow có người dùng; không mặc định gửi refresh token đến token endpoint |
| **Client** | Ứng dụng muốn truy cập tài nguyên theo một grant hợp lệ | Gọi token endpoint để đổi code, refresh token hoặc dùng grant được cho phép |
| **Authorization Server (AS)** | Xác thực, quản lý grant/ủy quyền, phát hành và quản lý token | **Sở hữu và bảo vệ token endpoint** |
| **Resource Server (RS)** | API lưu trữ hoặc bảo vệ tài nguyên | Nhận **access token** từ client để kiểm tra và áp dụng chính sách, **không phải** nơi mặc định cấp token |

Trong ứng dụng đặt hàng:

- **shop-web** là OAuth client.
- **auth.example.org** là Authorization Server.
- **orders.example.org** là Resource Server.
- Người dùng đặt hàng đóng vai trò Resource Owner trong flow người dùng.

~~~mermaid
flowchart LR
    U["Người dùng / Resource Owner"] --> C["shop-web / Client"]
    C -->|"Ủy quyền, tương tác đăng nhập"| A["Authorization Server"]
    C -->|"POST /oauth2/token: code hoặc refresh grant"| T["Token endpoint của AS"]
    A --- T
    T -->|"Cấp access token nếu hợp lệ"| C
    C -->|"Authorization: Bearer access_token"| R["Orders API / Resource Server"]
    R -->|"Validate token + policy tài nguyên"| R
~~~

**Token endpoint không đồng nghĩa trang đăng nhập.** Tương tác với người dùng thường diễn ra ở **authorization endpoint**, nơi Authorization Server xử lý authorization request, xác thực, consent hoặc step-up khi cần. Token endpoint thường là điểm **back-channel** mà client gửi request theo giao thức để nhận token. Một số loại grant không có người dùng đăng nhập, ví dụ **client credentials**.

Token endpoint cũng **không phải API nghiệp vụ**. Client không mang refresh token đến Orders API rồi mong API tự làm mới; nó phải gửi refresh token đúng về AS.

## 2. Phân biệt token endpoint với các endpoint dễ nhầm

| Endpoint | Mục đích chính | Dữ liệu điển hình | Điều không nên nhầm |
|---|---|---|---|
| **Authorization endpoint** | Xử lý authorization request qua user agent, tương tác xác thực/ủy quyền | \`client_id\`, \`redirect_uri\`, \`scope\`, \`state\`, PKCE challenge | Không phải nơi client gửi refresh token để đổi token |
| **Token endpoint** | Nhận grant và quyết định cấp token | \`grant_type\`, \`code\`/\`code_verifier\`, \`refresh_token\`, client authentication | Không phải Resource Server để đọc dữ liệu nghiệp vụ |
| **Resource endpoint** | Xử lý request API được bảo vệ | \`Authorization: Bearer <access-token>\` | Không nhận refresh token làm access token |
| **Introspection endpoint** | Cho bên được phép hỏi trạng thái/metadata token (RFC 7662) | \`token\`, xác thực caller; response \`active\` | HTTP 200 không đồng nghĩa \`active=true\` |
| **Revocation endpoint** | Yêu cầu thu hồi token (RFC 7009) | \`token\`, thông tin client/loại token theo chính sách | Thu hồi refresh token không mặc nhiên xóa hiệu lực mọi access token đã cấp |
| **JWKS/metadata endpoint** | Công bố khóa công khai, issuer, endpoint và khả năng của AS theo profile | \`jwks_uri\`, \`token_endpoint\`, \`issuer\` | Không phải nguồn để client tùy ý khai một issuer chưa được tin |
| **OIDC UserInfo endpoint** | Cung cấp claims người dùng được phép theo OIDC | Access token dành cho UserInfo | ID token không được dùng thay access token ở API |

**Tên đường dẫn không có ý nghĩa tiêu chuẩn duy nhất.** Ví dụ \`/oauth2/token\` chỉ là minh họa. Mỗi Authorization Server có thể công bố URL token endpoint qua **OAuth 2.0 Authorization Server Metadata (RFC 8414)**, **OIDC Discovery** hoặc cấu hình đáng tin đã thống nhất. Client không tự đoán URL từ API nghiệp vụ hay lấy token endpoint từ một JWT chưa xác minh.

## 3. Giao kèo HTTP của token endpoint

OAuth 2.0 token endpoint thường nhận **HTTP POST** và các tham số theo định dạng **\`application/x-www-form-urlencoded\`** trong request body (RFC 6749). Kết nối phải được bảo vệ bằng **TLS/HTTPS**, vì request có thể mang authorization code, refresh token và credential xác thực client; response có thể chứa access/refresh token có giá trị bảo mật.

Ví dụ khung request:

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.org
Content-Type: application/x-www-form-urlencoded

grant_type=<registered-or-supported-grant-type>&...
~~~

**\`grant_type\`** cho AS biết client đang dùng loại grant nào. Mỗi grant quy định **các tham số và kiểm tra riêng**; không phải cứ có một chuỗi bất kỳ là được cấp token. Phương thức xác thực client cũng tùy đăng ký và loại client.

Các quy tắc vận hành quan trọng:

1. **Không gửi token/secret trong URL query string**: URL có thể xuất hiện ở reverse proxy log, history, tracing, hệ thống giám sát hoặc đường chuyển tiếp.
2. **Không ghi raw request/response body** của token endpoint: nó có thể chứa \`code\`, \`code_verifier\`, \`refresh_token\`, \`client_secret\`, \`access_token\` và \`id_token\`.
3. **Không nhầm form body với JSON**: ví dụ theo OAuth 2.0 cơ bản thường là form-urlencoded, còn success/error response là JSON theo quy tắc tương ứng.
4. **Không dùng HTTP GET để đổi grant lấy token**. Không truyền token trong redirect URL để mô phỏng một token request.
5. **Không cache token response trong cache chia sẻ**; theo RFC 6749, response thành công có token sử dụng các header như \`Cache-Control: no-store\` và \`Pragma: no-cache\`.
6. **Không suy rằng mọi browser có thể gọi token endpoint trực tiếp**. CORS, loại client, flow, PKCE và chính sách AS phải được thiết kế tương ứng. CORS không thay thế client authentication hoặc kiểm tra grant.

Ví dụ minh họa có các giá trị placeholder. **Không nhập token hoặc secret production vào công cụ HTTP công khai** để kiểm thử.

## 4. Authorization Code + PKCE: đổi code tại token endpoint

Đây là flow phổ biến cho ứng dụng có người dùng. Client trước tiên chuyển người dùng đến authorization endpoint, nơi AS xử lý xác thực và ủy quyền. Khi hoàn tất, AS trả **authorization code** tới redirect URI đã được cho phép. Client sau đó gọi token endpoint với code và **PKCE code_verifier**.

~~~mermaid
sequenceDiagram
    actor U as Người dùng
    participant C as Client
    participant AU as Authorization endpoint
    participant T as Token endpoint
    participant RS as Orders API
    U->>C: Chọn đăng nhập
    C->>AU: Authorization request + code_challenge S256 + state
    AU->>U: Xác thực/consent/step-up nếu cần
    U-->>AU: Hoàn tất
    AU-->>C: Redirect với authorization code + state
    C->>C: Kiểm state và ngữ cảnh flow
    C->>T: POST grant_type=authorization_code, code, code_verifier
    T->>T: Kiểm client, code, redirect URI, PKCE, grant
    T-->>C: Access token; refresh/ID token nếu phù hợp
    C->>RS: Bearer access token
    RS->>RS: Validate token và quyền tài nguyên
    RS-->>C: Kết quả API
~~~

### Request mẫu

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.org
Content-Type: application/x-www-form-urlencoded

grant_type=authorization_code&code=<one-time-authorization-code>&redirect_uri=https%3A%2F%2Fapp.example.org%2Fcallback&client_id=shop-public-client&code_verifier=<original-pkce-verifier>
~~~

Đây là ví dụ **public client** dùng PKCE; không có nghĩa mọi client đều không cần xác thực. **Confidential client** phải xác thực với AS theo cơ chế đã đăng ký. Khi code được phát hành với redirect URI, token endpoint phải kiểm tra ràng buộc URI theo quy tắc của flow/profile.

### Token endpoint phải kiểm tra những gì?

1. **Grant được hỗ trợ và client được phép dùng** \`authorization_code\`.
2. **Client binding:** authorization code được cấp cho chính client đang đổi; không để client B đổi code của client A.
3. **Redirect URI binding:** URI cần đối chiếu với URI gắn trong authorization request/code theo quy tắc giao thức.
4. **Code validity:** code còn hạn, chưa bị đổi và không bị thu hồi; **authorization code dùng một lần**.
5. **PKCE:** \`code_verifier\` khớp \`code_challenge\` đã lưu cho code, thường theo phương thức **S256**; mismatch phải từ chối.
6. **Grant và chủ thể:** ủy quyền, consent hoặc trạng thái tài khoản phải còn thỏa policy tại lúc phát hành.
7. **Scope/audience:** token được cấp quyền cho resource nào, scope nào và thời hạn nào theo grant và chính sách.

**state** giúp client ràng buộc authorization response với request ban đầu và phòng một số kiểu tấn công CSRF/mix-up; nó **được client kiểm tra khi nhận redirect**, không phải một tham số thay thế PKCE tại token endpoint. Trong OIDC, client còn phải áp dụng các kiểm tra riêng với **ID token**, ví dụ **nonce** khi profile yêu cầu.

### Tại sao code không thể dùng để gọi API?

Authorization code chưa phải access token có audience/scope được Resource Server xác minh. Chỉ AS được giao quyền **đổi code lấy token** sau khi kiểm tra các ràng buộc. Orders API phải từ chối code khi nó được đưa vào \`Authorization: Bearer\`.

## 5. Client Credentials: token endpoint dành cho giao tiếp máy–máy

Không phải mọi yêu cầu cấp token đều bắt đầu bằng đăng nhập của người dùng. Với **Client Credentials grant**, một confidential client dùng quyền của **chính client/dịch vụ** để xin access token.

Ví dụ service tổng hợp báo cáo cần gọi Reports API:

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.org
Content-Type: application/x-www-form-urlencoded
Authorization: Basic <encoded-client-credentials>

grant_type=client_credentials&scope=reports%3Aread
~~~

Header Basic chỉ minh họa phương thức **client authentication**; không chứa credential thật và không phải tùy chọn duy nhất. Một triển khai có thể dùng **private_key_jwt**, **mTLS** hoặc phương pháp khác phù hợp profile và khả năng AS.

Token endpoint cần kiểm:

- Client được đăng ký, xác thực thành công và **được phép dùng client_credentials**.
- Client còn hoạt động và credential chưa bị thu hồi.
- Scope yêu cầu nằm trong quyền của **client**, không tự lấy quyền của một người dùng cuối.
- Resource/audience được AS chấp thuận.
- Token lifetime, token protection và chính sách rủi ro phù hợp.

Access token nhận được thường đại diện cho **service principal**. Resource Server không nên giả định rằng \`sub\` luôn là user; với client credentials, subject có thể mô tả client/service tùy profile.

Theo OAuth 2.0, **refresh token thường không nên được cấp trong Client Credentials grant** vì client có thể xác thực với AS để xin access token khác. Phát hành credential dài hạn không cần thiết làm tăng bề mặt rủi ro.

## 6. Refresh Token grant: làm mới ở AS, không gọi Resource Server

Khi access token hết hạn hoặc sắp hết hạn, client có refresh token hợp lệ có thể yêu cầu token endpoint cấp access token mới mà không thực hiện lại toàn bộ tương tác người dùng, **nếu ủy quyền còn được phép**.

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.org
Content-Type: application/x-www-form-urlencoded

grant_type=refresh_token&refresh_token=<refresh-token-value>&client_id=shop-public-client
~~~

Ví dụ dùng public client; AS phải kiểm các cơ chế ràng buộc thích hợp. Với confidential client, token endpoint yêu cầu xác thực client. **\`client_id\` của public client tự nó không chứng minh người gửi thực sự sở hữu client ấy**.

AS cần xác minh:

| Điều kiện | Ý nghĩa |
|---|---|
| Refresh token còn hiệu lực | Không hết hạn, không bị thu hồi, thuộc grant được chấp nhận |
| Đúng client | Refresh token được ràng buộc với client được cấp; confidential client xác thực thành công |
| Quyền vẫn còn | Grant, consent và trạng thái tài khoản/chính sách chưa cấm tiếp tục |
| Scope không tăng ngoài grant | Không dùng refresh token để xin quyền rộng hơn quyền gốc |
| Audience/resource được phép | Không dùng refresh token xin token cho API tùy ý |
| Replay protection | Rotation, phát hiện reuse hoặc sender-constraining theo chính sách |
| State update nhất quán | Không cho một refresh token đã tiêu thụ tạo nhiều nhánh hợp lệ do cạnh tranh đồng thời |

### Ví dụ refresh token rotation

~~~mermaid
sequenceDiagram
    participant C as Client
    participant T as Token endpoint
    C->>T: Refresh token RT1
    T->>T: Kiểm grant/client, atomic invalidate RT1
    T-->>C: Access token AT2 + Refresh token RT2
    C->>C: Lưu RT2 thay RT1
    C->>T: RT1 cũ xuất hiện lại
    T->>T: Phát hiện reuse, áp dụng policy
    T-->>C: Từ chối; có thể revoke token family
~~~

Nếu nhiều request API phát hiện access token hết hạn cùng lúc, client nên có cơ chế **single-flight refresh** để tránh gửi đồng thời cùng RT1. Với rotation, việc response bị mất hoặc retry không kiểm soát có thể làm token cũ xuất hiện lại; thiết kế cần xử lý concurrency, khôi phục an toàn và có thể yêu cầu đăng nhập lại.

**Refresh token bị thu hồi không mặc nhiên làm mọi JWT access token đã cấp mất hiệu lực ngay** tại Resource Server. Nếu API chỉ xác minh chữ ký và \`exp\`, token cũ có thể vẫn được nhận đến hạn; muốn thu hồi sớm cần trạng thái/denylist hoặc biện pháp tương ứng.

## 7. Các grant mở rộng không làm token endpoint mất ranh giới

Ngoài ba grant thông dụng, AS có thể hỗ trợ các extension grants theo chuẩn hoặc profile:

| Ví dụ | Mục đích | Lưu ý với token endpoint |
|---|---|---|
| **Device Authorization Grant (RFC 8628)** | Thiết bị có hạn chế nhập liệu thực hiện flow với người dùng trên thiết bị khác | Client nhận \`device_code\` từ device authorization endpoint rồi **poll token endpoint** theo quy tắc \`authorization_pending\`, \`slow_down\`, thời hạn |
| **Token Exchange (RFC 8693)** | Đổi chứng cứ đã được chấp thuận lấy token với subject/actor/audience/scope phù hợp | Không cho đổi token tùy ý giữa mọi Resource Server; AS phải kiểm delegation và chính sách |
| **JWT Bearer Assertion grant (RFC 7523)** | Dùng assertion làm authorization grant hoặc client authentication theo profile | Assertion phải được xác minh đúng issuer/audience, chữ ký, thời gian, chính sách tin cậy |

**Không tự xây extension grant bằng cách bỏ qua xác thực/ủy quyền.** Mỗi loại cần một \`grant_type\` và bộ kiểm tra do giao thức/profile định nghĩa. Token endpoint chỉ chấp nhận những grant AS đã bật và client được phép sử dụng.

**Resource Owner Password Credentials grant** tồn tại trong OAuth 2.0 cũ nhưng có nhiều rủi ro vì client phải xử lý mật khẩu người dùng; hướng dẫn bảo mật hiện đại khuyến nghị **không sử dụng** flow này cho thiết kế mới. Tránh biến token endpoint thành API nhận username/password trực tiếp chỉ để “đăng nhập cho tiện”, khi có thể dùng Authorization Code + PKCE và luồng xác thực phù hợp.

## 8. Client authentication tại token endpoint

**Client authentication** là kiểm tra ứng dụng nào đang gọi AS. Nó khác **user authentication** và khác **bearer access token validation** ở Resource Server.

### Public và confidential clients

| Loại client | Đặc điểm | Hệ quả tại token endpoint |
|---|---|---|
| **Confidential client** | Có thể bảo vệ credential xác thực client ở môi trường đáng tin theo thiết kế | AS yêu cầu xác thực client bằng phương thức đã đăng ký |
| **Public client** | Không thể giữ một shared secret dài hạn an toàn trước người dùng/chủ thiết bị | AS không xem một \`client_secret\` nhúng trong ứng dụng là bí mật đáng tin; dùng PKCE, ràng buộc grant và các kiểm soát tương ứng |

Một vài phương pháp **xác thực confidential client**:

- **client_secret_basic:** dùng HTTP Basic theo quy tắc OAuth và qua HTTPS; không log Authorization.
- **client_secret_post:** một số AS hỗ trợ, nhưng đưa secret vào body làm tăng nguy cơ bị ghi trong form body; chỉ dùng khi profile/chính sách cho phép.
- **private_key_jwt:** client ký một assertion để chứng minh sở hữu khóa được đăng ký; AS xác minh audience, issuer/subject và các ràng buộc khác theo profile.
- **mTLS client authentication:** dùng chứng thư client để xác thực; cần kiểm cấu hình chứng thư và ràng buộc đúng client.

**Chỉ có \`client_id\` không phải chứng cứ xác thực** vì thông thường đây là định danh công khai. Đối với public client, bảo vệ authorization code bằng PKCE, xác minh redirect/client binding và các cơ chế bổ sung là trọng tâm.

### Sender-constrained tokens

Với **DPoP** hoặc **mTLS-bound access token** khi AS và RS hỗ trợ, một credential được ràng buộc với bằng chứng sở hữu khóa/chứng thư. Token endpoint có thể cần xác minh proof hoặc ràng buộc khi cấp token, còn Resource Server phải xác minh proof tương ứng khi token được sử dụng. **Chỉ cấp token có claim ràng buộc mà RS không kiểm chứng thì không tạo ra bảo vệ chống phát lại đúng nghĩa.**

## 9. Token response: AS cấp loại token nào?

Response thành công của token endpoint cho một access token Bearer có thể như sau:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store
Pragma: no-cache

{
  "access_token": "<new-access-token>",
  "token_type": "Bearer",
  "expires_in": 900,
  "scope": "orders:read",
  "refresh_token": "<refresh-token-if-issued>"
}
~~~

Đây là **ví dụ giản lược**, không phải mọi response đều chứa \`refresh_token\`. \`expires_in=900\` nghĩa là access token có thời hạn 900 giây theo response ví dụ, không phải thời hạn chuẩn bắt buộc của OAuth và không mô tả thời hạn refresh token. AS có thể thêm thông tin theo profile/extension được hỗ trợ.

| Trường | Ý nghĩa |
|---|---|
| **access_token** | Credential client sẽ dùng với đúng Resource Server |
| **token_type** | Cách dùng token theo hợp đồng, thường là \`Bearer\`; không dùng làm bằng chứng duy nhất về audience hoặc mục đích |
| **expires_in** | Thời gian access token có hiệu lực tính bằng giây khi được trả về, nếu AS cung cấp |
| **scope** | Scope được cấp thực tế khi AS cần thông báo, đặc biệt nếu khác scope yêu cầu |
| **refresh_token** | Credential tùy chọn để xin access token mới, chỉ được gửi về token endpoint khi dùng |
| **id_token** | Có thể xuất hiện trong các response **OIDC** phù hợp; dành cho client xác minh đăng nhập, không dùng thay access token ở API |

### JWT và opaque token là hai dạng access token

**JWT access token tự chứa** cho phép Resource Server xác minh chữ ký, \`iss\`, \`aud\`, \`exp\` và claims theo profile. Ví dụ JSON payload minh họa theo hướng RFC 9068:

~~~json
{
  "iss": "https://auth.example.org",
  "sub": "user-42",
  "aud": "orders-api",
  "client_id": "shop-web",
  "scope": "orders:read",
  "iat": 1899999000,
  "exp": 1900000800,
  "jti": "example-at-901"
}
~~~

Đây **không phải JWT có chữ ký**. JWT access token theo profile RFC 9068 còn có ràng buộc JOSE header, claims và thuật toán phù hợp. **JWS được ký không mặc nhiên được mã hóa**; payload thường đọc được, nên không đưa refresh token, mật khẩu, private key hoặc dữ liệu nhạy cảm không cần vào claims.

**Opaque access token** thường là chuỗi khó đoán do AS quản lý trạng thái. Resource Server xác minh thông qua **introspection** hoặc nguồn trạng thái tin cậy, thay vì tự giải mã claims. Nếu AS có khả năng thu hồi, lần kiểm tra mới có thể thấy \`active=false\`; nhưng cache introspection có thể làm chậm hiệu lực thu hồi.

**Access token là mục đích**, không phải định dạng. Token endpoint có thể phát hành JWT hoặc opaque access token theo hợp đồng của AS và RS. Client không được tự suy format, tự sửa claims hay tự quyết định token hợp lệ.

## 10. Scope và audience được quyết định tại token endpoint

Client **yêu cầu** scope/resource, còn AS **quyết định cấp** theo client, grant, chủ thể, consent và policy. Token endpoint không nên chỉ chép nguyên giá trị scope hoặc resource trong request vào token.

Ví dụ:

| Resource Server | Audience | Scope minh họa |
|---|---|---|
| Orders API | **orders-api** | **orders:read**, **orders:write** |
| Payments API | **payments-api** | **payments:read**, **payments:charge** |
| Reports API | **reports-api** | **reports:read** |

Nếu client chỉ có quyền \`orders:read\` nhưng yêu cầu \`payments:charge\`, AS phải **từ chối** hoặc thu hẹp theo quy tắc giao thức/chính sách; nó không được cấp quyền tăng thêm vì request viết đúng cú pháp.

**OAuth 2.0 Resource Indicators (RFC 8707)** cho phép dùng tham số \`resource\` để biểu diễn tài nguyên mong muốn trong các flow AS hỗ trợ. Ví dụ một request có thể bao gồm:

~~~text
grant_type=client_credentials
resource=https%3A%2F%2Fapi.example.org%2Freports
scope=reports%3Aread
~~~

AS phải kiểm client có quyền với resource ấy. Giá trị \`aud\` được phát hành có thể là URI hoặc identifier logic theo hợp đồng AS–RS; **không nhất thiết bằng nguyên chuỗi \`resource\`**, và Resource Server phải so khớp expected audience của chính mình.

**Scope không thay audience**: token có \`scope=orders:read\` nhưng \`aud=payments-api\` không mặc nhiên dùng được ở Orders API. Ngược lại, đúng \`aud=orders-api\` cũng không cho phép xem mọi đơn hàng; RS còn phải kiểm ownership, tenant, role và trạng thái tài nguyên.

### Quyền tại thời điểm cấp và thời điểm sử dụng

Một access token có thể được cấp đúng lúc 09:00 nhưng user mất membership lúc 09:05. Token JWT còn hạn vẫn có thể chứa claims quyền cũ. Với thao tác nhạy cảm, Resource Server cần kiểm quyền hiện hành hoặc cơ chế version/revocation phù hợp; **token endpoint không thể thay thế tất cả policy evaluation về sau**.

## 11. Quy trình kiểm tra trước khi phát token

~~~mermaid
flowchart TD
    A["POST /token qua TLS"] --> B{"Request và grant_type hợp lệ?"}
    B -->|Không| X["Error, không cấp token"]
    B -->|Có| C{"Client nhận diện/xác thực đúng?"}
    C -->|Không| X
    C -->|Có| D{"Grant được phép với client?"}
    D -->|Không| X
    D -->|Có| E{"Code/PKCE, client proof hoặc refresh token hợp lệ?"}
    E -->|Không| X
    E -->|Có| F{"Chủ thể, consent/grant và trạng thái còn cho phép?"}
    F -->|Không| X
    F -->|Có| G{"Scope, audience và token policy được chấp thuận?"}
    G -->|Không| X
    G -->|Có| H["Tiêu thụ grant nếu một lần, tạo token/state nhất quán"]
    H --> I["Trả token response no-store qua TLS"]
~~~

Pseudocode khái niệm cho AS:

~~~text
tokenEndpoint(request):
    requireTlsPostAndFormEncoding(request)
    grantType = parseSupportedGrantType(request)

    client = identifyClient(request)
    authenticateClientIfRequired(client, request)
    requireGrantTypeAllowedForClient(client, grantType)

    grant = validateGrantProof(grantType, client, request)
    # auth_code: kiểm code, redirect, PKCE, single-use
    # refresh: kiểm RT, client binding, revoke/rotation
    # client_credentials: kiểm service principal và quyền client

    requireGrantAndAccountStateAllowed(grant, client)
    grantedScope = evaluateAndLimitScope(grant, request.scope)
    approvedResource = evaluateResourcePolicy(grant, request.resource)

    tokenPolicy = chooseAudienceLifetimeAndProtection(
        client, grant, grantedScope, approvedResource
    )
    requireTrustedIssuerAndHealthySigningOrStorage(tokenPolicy)

    result = atomicallyConsumeGrantIfNeededAndIssueToken(
        grant, tokenPolicy
    )
    return tokenResponseWithNoStore(result)
~~~

Pseudocode này **không phải cài đặt trực tiếp của OAuth 2.0**. Hãy sử dụng Authorization Server/framework được duy trì và cấu hình grant-specific validators, client authentication, PKCE, trạng thái token, đồng thời thực thi transaction/locking phù hợp. Tạo JWT bằng cách nối JSON với Base64url **không đủ tạo token bảo mật**; với opaque token cần CSPRNG, entropy và lưu trạng thái an toàn.

### Tính nguyên tử khi tiêu thụ credential

**Authorization code** chỉ được dùng một lần; **refresh token đã rotation** không được tiếp tục tạo token mới. Nếu hai request chạy đồng thời, AS phải bảo đảm trạng thái tiêu thụ và cấp token không tạo ra hai nhánh hợp lệ trái policy. Không xử lý bằng cách chỉ kiểm một cờ ở đầu request rồi cập nhật cờ sau khi đã phát token mà không có kiểm soát tranh chấp.

## 12. Error response: từ chối ở token endpoint khác từ chối tại API

Token endpoint có các **mã lỗi OAuth 2.0**; không dùng mọi thất bại thành \`401 invalid_token\` như ở Resource Server.

| Error code | Ý nghĩa điển hình | Ví dụ |
|---|---|---|
| **invalid_request** | Request thiếu/sai tham số bắt buộc, định dạng không hợp lệ | Thiếu \`grant_type\` |
| **invalid_client** | Xác thực client thất bại hoặc client không hợp lệ | Client secret không đúng |
| **invalid_grant** | Grant, code hoặc refresh token không hợp lệ, hết hạn, bị thu hồi, dùng lại hoặc không thuộc client | PKCE/code sai, refresh token đã revoke |
| **unauthorized_client** | Client không được dùng grant type được yêu cầu | Public client không được bật grant đó |
| **unsupported_grant_type** | AS không hỗ trợ grant type này | Grant lạ hoặc chưa bật |
| **invalid_scope** | Scope yêu cầu không hợp lệ, chưa biết hoặc vượt phạm vi được phép theo quy định áp dụng | Xin scope chưa được chấp thuận |

Ví dụ response lỗi:

~~~http
HTTP/1.1 400 Bad Request
Content-Type: application/json
Cache-Control: no-store
Pragma: no-cache

{
  "error": "invalid_grant"
}
~~~

**Không phải mọi lỗi đều bắt buộc HTTP 400.** Theo RFC 6749, một số tình huống \`invalid_client\` có thể dùng **HTTP 401** và cơ chế challenge tương ứng, đặc biệt khi client đã thử xác thực bằng header \`Authorization\`. Luôn tuân thủ quy tắc của grant, client authentication và profile AS.

Không trả request raw, authorization code, code_verifier, refresh token, client secret hoặc chi tiết key nội bộ trong error description. Client nên phân biệt lỗi có thể khôi phục với lỗi grant đã hết hiệu lực:

- \`invalid_grant\` khi refresh: ngừng dùng credential cũ, yêu cầu flow ủy quyền lại nếu cần.
- \`invalid_client\`: không bypass xác thực; kiểm cấu hình/credential của client.
- Lỗi mạng/5xx: retry có giới hạn và hiểu rằng một refresh request **có thể đã được xử lý** dù client không nhận response.
- API trả **403 insufficient_scope**: không refresh vô hạn với hy vọng tự có thêm quyền.

## 13. Các rủi ro bảo mật tập trung ở token endpoint

### 13.1. Code interception và PKCE

Kẻ tấn công lấy được authorization code có thể thử đổi nó. **PKCE** ràng buộc code với verifier mà client giữ; AS phải kiểm tương ứng. Nhưng PKCE không thay thế client binding, redirect URI, TLS, chống CSRF của client và client authentication khi cần.

### 13.2. Refresh token theft, rotation và replay

Refresh token có giá trị lớn vì có thể xin access token mới. Dùng **rotation hoặc sender-constraining** theo loại client và hướng dẫn bảo mật áp dụng; AS phải xử lý reuse detection, thu hồi token family và concurrency an toàn.

### 13.3. Credential stuffing và abuse

Token endpoint cần kiểm soát số lượng request và hành vi bất thường, đặc biệt với client authentication, grant bị lặp và token exchange. Giới hạn tốc độ, cảnh báo và bảo vệ credential phải tránh biến endpoint thành công cụ dò token/client ID.

### 13.4. Token substitution và token-type confusion

Resource Server không được chấp nhận **OIDC ID token**, **refresh token** hoặc authorization code như access token. Token endpoint cũng không được chấp nhận bất cứ bearer access token nào làm refresh token chỉ vì cùng issuer/chữ ký. Kiểm tra profile và mục đích tại từng nơi nhận.

### 13.5. Chỉ decode JWT rồi tin claims

AS/RS phải xác minh chữ ký hoặc introspection với nguồn tin cậy, claims đúng kiểu, issuer, audience, thời hạn và trạng thái. **Base64url-decoding chỉ đọc payload**, không xác minh issuer hoặc quyền.

### 13.6. Endpoint discovery và nguồn khóa không tin cậy

Client/RS cần dùng issuer, token endpoint, JWKS từ **cấu hình đáng tin hoặc metadata đã được xác minh**. Không nhận URL do token chưa xác minh tự khai làm nguồn endpoint mới, tránh trộn issuer/key và các rủi ro truy cập URL tùy ý.

### 13.7. Ghi raw token vào log/analytics

Token endpoint là nơi đặc biệt dễ làm lộ secrets: **grant_type=refresh_token** nằm trong form body, token response có cả access/refresh/ID token. Không ghi raw header/body/response, không đặt token trong URL, không thu thập credential qua APM, tracing, session replay, crash report hoặc ticket hỗ trợ.

**Bảo vệ TLS và mã hóa log at rest không thay thế việc không thu thập credential vào log từ đầu.**

## 14. Token endpoint, Resource Server và trách nhiệm sau khi cấp

Giả sử AS cấp JWT access token cho Orders API:

~~~text
issuer:        https://auth.example.org
audience:      orders-api
scope:         orders:read
subject:       user-42
client_id:     shop-web
expiration:    theo policy access token
~~~

Khi client mang token đến Orders API, **Resource Server** vẫn cần:

1. Xác minh nguồn issuer, key/chữ ký với JWT hoặc introspection của opaque token.
2. Kiểm **audience** chính xác: token dành cho API khác phải bị từ chối.
3. Kiểm token còn hiệu lực, đúng profile/access-token type; xử lý trạng thái thu hồi và key/issuer trust.
4. Kiểm scope phù hợp với hành động.
5. Kiểm quyền với **order cụ thể**, tenant, ownership, role hoặc trạng thái nghiệp vụ hiện hành.

**Token được phát hành hợp lệ không tự đồng nghĩa mọi request nghiệp vụ hợp lệ.** Ví dụ scope \`orders:read\` chưa cho phép user-42 đọc đơn hàng của user-99.

Nếu access token hết hạn, client phải làm mới tại **token endpoint** (nếu có refresh token được phép) hoặc thực hiện lại flow cấp quyền. **Không đưa refresh token vào Resource Server** và không cho API tự kéo dài \`exp\` của JWT.

Trong hệ thống nhiều API, mỗi token nên giới hạn **audience và scope** phù hợp. Một token phát hành cho Orders API không được dùng ở Payments API; nếu một service cần gọi API khác thì xin **access token riêng đúng audience** qua service identity hoặc cơ chế delegation/token exchange được AS chấp thuận.

## 15. Tình huống thực tế: đặt hàng, báo cáo và gia hạn token

Hệ thống minh họa có:

| Thành phần | Vai trò | Cách tương tác |
|---|---|---|
| **shop-web** | Public OAuth client | Authorization Code + PKCE để gọi Orders API |
| **reports-worker** | Confidential OAuth client | Client Credentials để gọi Reports API |
| **auth.example.org** | Authorization Server | Token endpoint xử lý grant và cấp token |
| **orders-api** | Resource Server | Chấp nhận access token đúng audience, scope, policy |
| **reports-api** | Resource Server | Chấp nhận access token của worker với quyền reports:read |

**Tình huống A – Người dùng đã đăng nhập nhưng client đưa code tới Orders API.** API phải từ chối. Client cần đổi code tại token endpoint bằng PKCE verifier hợp lệ để nhận access token.

**Tình huống B – Mã code bị đổi hai lần.** Token endpoint không được cấp token mới từ lần dùng thứ hai. Phải xử lý single-use atomically.

**Tình huống C – Worker có client credentials muốn đọc báo cáo.** AS có thể cấp access token audience **reports-api**, scope **reports:read** dựa trên quyền client; không cần giả định có end user đăng nhập.

**Tình huống D – Client dùng refresh token để gọi Orders API.** Resource Server từ chối sai loại token. Refresh token chỉ dùng tại token endpoint của AS.

**Tình huống E – User bị gỡ quyền trong tenant khi access token JWT còn hạn.** AS có thể ngừng refresh hoặc thu hẹp scope; Resource Server vẫn cần kiểm membership hiện hành khi policy yêu cầu. Token endpoint không thay quyền kiểm tra tài nguyên của API.

**Tình huống F – AS bị lộ private signing key.** Kẻ tấn công có thể tự ký JWT được verifier cũ chấp nhận. AS và mọi RS phải phối hợp **thu hồi niềm tin vào key/issuer**; chỉ xoay khóa mà các RS còn cache key cũ chưa đủ.

## 16. Ma trận kiểm thử token endpoint

| Trường hợp | Kết quả mong đợi |
|---|---|
| Authorization code hợp lệ, đúng client/redirect/PKCE, grant còn phép | Cấp access token đúng phạm vi |
| Authorization code đã được đổi một lần | \`invalid_grant\`; không cấp token khác từ code đó |
| Code phát cho client A nhưng đổi bởi client B | Từ chối |
| Code đúng nhưng PKCE verifier sai | Từ chối |
| Client yêu cầu grant chưa được cấp phép | \`unauthorized_client\` theo ngữ cảnh |
| AS không hỗ trợ grant_type gửi tới | \`unsupported_grant_type\` |
| Confidential client không xác thực được | \`invalid_client\` với HTTP/challenge phù hợp |
| Client Credentials hợp lệ nhưng xin scope vượt quyền | Từ chối hoặc thu hẹp theo giao thức/chính sách |
| Refresh token còn hạn, đúng client, grant còn quyền | Cấp access token mới trong quyền đã được phép |
| Refresh token bị revoke hoặc hết hạn | \`invalid_grant\` |
| Refresh token RT1 đã dùng sau rotation xuất hiện lại | Từ chối, xử lý reuse/token family theo policy |
| Hai request refresh đồng thời cùng RT1 | Không tạo hai nhánh hợp lệ trái policy |
| Refresh xin audience không nằm trong grant đã duyệt | Không cấp audience vượt quyền |
| OIDC ID token được gửi như refresh token | Từ chối sai loại/flow |
| Browser/client gửi token trong URL query | Client không làm vậy; log/gateway không lưu credential |
| Token endpoint request/response đi qua debug logging | Không có token/secret thô trong log, APM, tracing |
| Resource Server nhận authorization code hoặc refresh token làm Bearer | Từ chối, không tự cấp token |
| Resource Server nhận access token đúng issuer nhưng sai audience | Từ chối |
| Token endpoint tạm lỗi mạng | Không suy rằng credential không bị tiêu thụ; retry an toàn, không phát vượt policy |
| Signing key/issuer bị thu hồi | Không tiếp tục phát token từ gốc bị ảnh hưởng; RS ngừng tin theo policy |

**Kiểm thử cần quan sát cả token được cấp, phạm vi quyền, trạng thái grant và side effect**, không chỉ mã HTTP. Dùng code, khóa và token giả trong môi trường được phép; không sao chép credential production vào công cụ thử nghiệm công khai.

## 17. Checklist triển khai token endpoint

1. **Vị trí:** Token endpoint thuộc đúng Authorization Server đáng tin, không nhầm với Resource Server hay endpoint đăng nhập?
2. **Transport:** Chỉ nhận POST qua TLS và content type/parameters hợp lệ theo giao thức?
3. **Client:** Phân biệt public/confidential client, xác thực đúng phương pháp đăng ký, không tin mỗi \`client_id\`?
4. **Grant:** Chỉ bật grant cần thiết và client có quyền dùng grant?
5. **Authorization code:** Code còn hạn, single-use, đúng client/redirect/PKCE, chống cạnh tranh đổi code?
6. **Refresh:** RT đúng client/grant, còn hiệu lực, rotation/replay protection, xử lý đồng thời?
7. **Client Credentials:** Scope/audience chỉ phản ánh quyền của service/client, không gán nhầm quyền user?
8. **Scope:** AS xác định quyền được cấp thực tế và không chấp nhận nâng quyền trong refresh/exchange?
9. **Audience:** Token được cấp cho Resource Server cụ thể, không dùng một credential cho mọi API vô điều kiện?
10. **Token type:** JWT/opaque đúng profile, ID token chỉ trong OIDC flow phù hợp, refresh token không đến RS?
11. **Key/trust:** Signing key, issuer, metadata/JWKS và trạng thái thu hồi được bảo vệ, có kế hoạch phản ứng sự cố?
12. **Response:** Có \`token_type\`, thời hạn, scope khi cần; \`no-store\`, không cache response chứa credential?
13. **Errors:** Mã lỗi OAuth thích hợp, không lộ raw token, code, verifier hoặc client secret?
14. **Logging:** Không ghi Authorization, request/response token endpoint, tracing/APM/session replay chứa credential?
15. **Đồng thời và tải:** Có kiểm soát atomic, rate limit và theo dõi abuse mà không lưu secrets?
16. **Resource Server:** API vẫn kiểm issuer, audience, thời gian, scope và quyền tài nguyên sau khi token được cấp?
17. **Tests:** Có negative tests cho sai client, sai grant, wrong redirect/PKCE, replay, revoked refresh, wrong audience và key compromise?

## 18. Câu hỏi tự đánh giá

**1. Ai sở hữu token endpoint?** Authorization Server. Client gọi nó để đổi một grant hợp lệ lấy token; Resource Server không phải nơi mặc định cấp token.

**2. Authorization endpoint và token endpoint khác nhau thế nào?** Authorization endpoint xử lý tương tác ủy quyền/đăng nhập theo flow; token endpoint nhận request đổi grant/cấp token theo giao thức và chính sách.

**3. Authorization code có dùng làm Bearer token gọi Orders API được không?** Không. Client phải đổi code tại token endpoint, kèm PKCE verifier và các bằng chứng cần thiết.

**4. Vì sao token endpoint phải kiểm PKCE và code một lần?** Để ràng buộc người đổi code với bên tạo verifier, giảm rủi ro code interception và không cấp nhiều token từ cùng chứng cứ một lần.

**5. Client Credentials grant có nhất thiết có user hoặc refresh token không?** Không. Grant này thường cấp token theo quyền của confidential client/service, không mặc định có người dùng cuối, và refresh token thường không cần.

**6. Refresh token được gửi tới đâu?** Token endpoint của AS, không phải API nghiệp vụ. Nó chỉ cho phép xin token mới khi client/grant/trạng thái vẫn hợp lệ.

**7. Token endpoint có được cấp \`payments:charge\` chỉ vì client yêu cầu scope đó không?** Không. AS phải kiểm quyền cấp, resource/audience, grant và chính sách.

**8. Token endpoint trả access token thành công có nghĩa Resource Server bỏ qua scope/ownership không?** Không. RS vẫn xác minh token và phân quyền trên từng tài nguyên.

**9. JWT và opaque access token khác ở điểm nào trong mối quan hệ với token endpoint?** Cả hai đều có thể được AS cấp làm access token. RS thường xác minh JWT bằng chữ ký/claims tại chỗ, còn opaque thường dùng introspection/nguồn trạng thái tin cậy.

**10. Nếu refresh token đã rotation bị dùng lại, client nên thử vô hạn không?** Không. AS phải phát hiện/từ chối theo reuse policy; client cần xử lý token không hợp lệ và tái xác thực khi cần.

**Ghi nhớ:** **Token endpoint là nơi Authorization Server kiểm tra một grant và quyết định phát hành credential, không phải nơi Resource Server trả dữ liệu nghiệp vụ.** Với Authorization Code + PKCE, nó đổi code đã ràng buộc đúng client/redirect/verifier; với Client Credentials, nó kiểm quyền của ứng dụng; với Refresh Token grant, nó kiểm trạng thái, client binding và chống reuse. Token được cấp phải đúng **mục đích, issuer, audience, scope và thời hạn**, được truyền/lưu an toàn. Khi client dùng access token, **Resource Server vẫn chịu trách nhiệm xác minh và phân quyền riêng**, còn refresh token chỉ quay lại token endpoint.
