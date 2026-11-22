# 2.10. Bearer token, opaque token và JWT access token

## 1. Bối cảnh: một access token đi từ đâu đến đâu?

Trong OAuth 2.0, **access token** là thông tin mà **Authorization Server** cấp cho một **OAuth 2.0 Client** để client truy cập tài nguyên được bảo vệ ở **Resource Server** theo một phạm vi ủy quyền nhất định. Client có thể là ứng dụng web Spring Boot đã đăng nhập người dùng bằng OIDC, một ứng dụng di động hoặc một dịch vụ gọi dịch vụ khác.

Giả sử hệ thống có ba thành phần:

- **Company IdP / Authorization Server**: xác thực nhân viên, xử lý ủy quyền và cấp access token.
- **Employee Portal**: ứng dụng Spring Boot có vai trò **OAuth 2.0 Client**; sau khi nhân viên đăng nhập, Portal cần gọi Orders API cho nhân viên đó.
- **Orders API**: ứng dụng Spring Security có vai trò **Resource Server**; chỉ trả đơn hàng khi access token hợp lệ và người dùng có quyền truy cập.

Trong ví dụ, Portal nhận token có quyền **orders.read**, sau đó gửi request:

~~~http
GET /api/orders HTTP/1.1
Host: orders.example.test
Authorization: Bearer <access-token>
~~~

Ở đây có hai câu hỏi khác nhau:

1. **Bearer** nghĩa là gì, và tại sao chuỗi token có thể xuất hiện trong header **Authorization**?
2. Bản thân chuỗi access token có định dạng **opaque** hay **JWT**, và Orders API cần xác minh nó bằng cách nào?

Đó là lý do phải tách khái niệm **cách sử dụng token** khỏi **định dạng token**.

## 2. Phân biệt ba khái niệm thường bị nhầm lẫn

| Khái niệm | Thuộc về lớp nào? | Ý nghĩa | Ví dụ |
|---|---|---|---|
| **Bearer token** | Cơ chế trình bày thông tin xác thực | Bên nào sở hữu token có thể gửi token để sử dụng quyền đã được cấp; token không tự chứng minh bên gửi là chủ sở hữu hợp pháp | Header **Authorization: Bearer ...** |
| **Opaque access token** | Cách biểu diễn access token | Giá trị token không có cấu trúc công khai mà Resource Server được quyền diễn giải; Resource Server thường hỏi Authorization Server để biết token còn hiệu lực và mang quyền gì | **f8H2tR7x...** |
| **JWT access token** | Cách biểu diễn access token | Access token được mã hóa theo cấu trúc JSON Web Token, thường dưới dạng **JWS** có chữ ký; Resource Server có thể xác minh chữ ký và các claim cục bộ | **header.payload.signature** |

**Bearer không đối lập với opaque hoặc JWT.** Một access token được sử dụng theo cơ chế Bearer có thể là **opaque token** hoặc **JWT**. Ngược lại, JWT là một **định dạng** có thể dùng cho nhiều loại token, không mặc nhiên là OAuth access token.

Sơ đồ phân loại:

~~~text
OAuth 2.0 Access Token
    |
    +-- Cách trình bày đến API
    |       +-- Bearer (Authorization: Bearer ...)
    |       +-- Các cơ chế khác nếu hệ thống hỗ trợ, ví dụ token ràng buộc bên gửi
    |
    +-- Định dạng do Authorization Server quyết định
            +-- Opaque / reference token
            +-- JWT access token
            +-- Các biểu diễn khác theo hợp đồng hệ thống
~~~

Ví dụ cụ thể: Portal có thể gửi **Authorization: Bearer f8H2tR7x...** nếu access token là opaque. Portal cũng có thể gửi **Authorization: Bearer eyJ...** nếu đó là JWT. Cú pháp HTTP bên ngoài giống nhau, còn cách xác minh ở Orders API khác nhau.

> Trong phạm vi bài học, **Bearer** là cơ chế thường gặp nhất. Các cơ chế **sender-constrained token** như mTLS hoặc DPoP có đặc tính ràng buộc bổ sung và không thể đánh đồng với Bearer thông thường.

## 3. Bearer token: ai giữ được token thì có thể trình bày token

### 3.1. Ý nghĩa của Bearer

Từ **bearer** chỉ bên mang hoặc nắm giữ token. Khi Resource Server nhận một bearer access token hợp lệ, nó có thể chấp nhận request theo phạm vi quyền mà token thể hiện. Bản thân bearer token **không yêu cầu người gửi chứng minh thêm việc sở hữu một khóa mật mã riêng**. Vì vậy, ai lấy cắp được bearer token có nguy cơ tái sử dụng token cho đến khi token hết hạn, bị vô hiệu hóa hoặc bị cơ chế bảo vệ khác chặn.

Bearer token giống một **vé vào cửa có thể chuyển tay**, nhưng vé vẫn có điều kiện: thời hạn, khu vực được vào, đối tượng sử dụng, phạm vi quyền và chính sách kiểm soát của Resource Server. Không nên hiểu “có token” là “được phép làm mọi việc”.

### 3.2. Vị trí gửi token trong HTTP

Cách chuẩn và thông dụng là **Authorization header** theo OAuth 2.0 Bearer Token Usage:

~~~http
GET /api/orders HTTP/1.1
Host: orders.example.test
Authorization: Bearer ACCESS_TOKEN_VALUE
Accept: application/json
~~~

Các đặc điểm:

- **Bearer** là tên authentication scheme, theo sau là dấu cách và giá trị access token.
- HTTPS/TLS phải được sử dụng cho môi trường thực tế để bảo vệ token khi truyền.
- Không tự ý gắn token vào query string như **?access_token=...**: URL thường xuất hiện trong log, browser history, reverse proxy, analytics và các liên kết được chia sẻ.
- Không gửi bearer token đến API không phải đối tượng nhận dự kiến (**audience**).
- Không trả token về frontend nếu mô hình ứng dụng chỉ cần browser gửi session cookie cho backend, chẳng hạn mô hình **Backend for Frontend (BFF)**.

Một lỗi phổ biến là nhầm header **Authorization: Bearer ...** với cookie đăng nhập. Trong ứng dụng web dùng OIDC login:

| Kênh trao đổi | Thông tin thường gửi | Bên xác minh |
|---|---|---|
| Browser → Portal | Session cookie của Portal | Portal kiểm tra session |
| Portal → Orders API | OAuth access token trong Bearer header | Orders API xác minh token |
| Portal → Authorization Server | Authorization code hoặc refresh token trong request hợp lệ | Authorization Server xử lý grant/đổi token |

Token được giữ ở phía nào tùy kiến trúc. Với ứng dụng MVC/BFF, access token có thể nằm trong **OAuth2AuthorizedClient** phía server; JavaScript của browser không cần đọc nó.

### 3.3. Bearer không tự đảm bảo được những gì?

Một bearer token **không tự cung cấp**:

- Bảo vệ chống phát lại khi bị đánh cắp.
- Xác nhận danh tính người gửi request ở mức thiết bị hoặc khóa riêng.
- Cơ chế thu hồi ngay lập tức cho mọi loại token.
- Quyền truy cập đến mọi endpoint hoặc mọi bản ghi dữ liệu.

Do đó, API cần xác minh **tính hợp lệ của token**, **API dự kiến nhận token**, **scope/authority**, rồi tiếp tục kiểm tra **quyền nghiệp vụ** với từng đối tượng tài nguyên.

## 4. Access token được cấp và sử dụng trong luồng OAuth 2.0 như thế nào?

Với ứng dụng Portal đăng nhập người dùng bằng **OIDC Authorization Code Flow**, một luồng điển hình là:

~~~mermaid
sequenceDiagram
    actor U as Người dùng
    participant B as Browser
    participant C as Portal (OAuth2 Client)
    participant AS as Authorization Server / OIDC Provider
    participant RS as Orders API (Resource Server)

    U->>B: Mở trang đơn hàng
    B->>C: Truy cập Portal
    C-->>B: Chuyển hướng tới authorization endpoint
    B->>AS: Authorization request (openid, orders.read, state, ...)
    AS->>U: Đăng nhập và cấp consent nếu cần
    AS-->>B: Redirect về callback với authorization code
    B->>C: Callback với code và state
    C->>AS: Đổi code tại token endpoint
    AS-->>C: ID token + access token (+ refresh token nếu được cấp)
    C->>C: Tạo phiên đăng nhập, lưu OAuth2AuthorizedClient
    B->>C: GET /bff/orders kèm session cookie
    C->>RS: GET /api/orders, Authorization: Bearer access_token
    alt Access token là JWT
        RS->>RS: Xác minh chữ ký, issuer, audience, thời hạn
    else Access token là opaque
        RS->>AS: Gọi introspection endpoint
        AS-->>RS: Trạng thái active và thuộc tính token
    end
    RS->>RS: Kiểm tra orders.read và quyền trên dữ liệu
    RS-->>C: Kết quả được phép truy cập
    C-->>B: Trang hoặc dữ liệu đơn hàng
~~~

Cả hai định dạng token đều có thể đi qua cùng luồng OAuth 2.0. **OAuth2 Client thường không cần giải mã access token để gọi API**: nó chỉ lấy giá trị token đã được cấp và trình bày token với Resource Server. Quy tắc xử lý định dạng token thuộc về Resource Server và Authorization Server.

## 5. Opaque access token là gì?

### 5.1. “Opaque” nghĩa là không có cấu trúc để bên nhận tự diễn giải

Opaque token là một giá trị mà client và thông thường cả Resource Server **không thể tự suy ra một tập claim đã được chuẩn hóa** từ hình dạng chuỗi. Ví dụ:

~~~text
q9Lz1D8vT4K7Wb3X0mR5yF2a...
~~~

Authorization Server có thể quản lý token dưới dạng một **reference** trỏ đến bản ghi quyền ở phía server. Tuy nhiên, **opaque** là đặc tính của giao diện sử dụng token; không phải cam kết rằng token bắt buộc là chuỗi ngẫu nhiên, có một độ dài cố định hay được lưu theo cấu trúc database cụ thể.

Nhìn vào chuỗi token, Portal không nên tự quyết định người dùng, scope, hạn dùng hay API đích. Để kiểm tra opaque token, Resource Server thường dùng **OAuth 2.0 Token Introspection** (RFC 7662) do Authorization Server cung cấp.

### 5.2. Cơ chế introspection

Khi Orders API nhận opaque token:

1. API lấy token từ Bearer header.
2. API gọi **introspection endpoint** của Authorization Server theo kênh bảo vệ; thông thường API phải xác thực bằng thông tin đăng ký riêng của Resource Server.
3. Authorization Server kiểm tra token, thời hạn, trạng thái thu hồi và chính sách tương ứng.
4. Authorization Server trả về **active: true/false** cùng các thuộc tính mà API được phép biết.
5. API áp dụng scope, audience và các quyền trên đơn hàng trước khi trả dữ liệu.

Ví dụ phản hồi introspection **minh họa**, không phải mọi IdP đều trả đủ các trường sau:

~~~json
{
  "active": true,
  "iss": "https://id.example.test/realms/company",
  "client_id": "portal-web",
  "sub": "employee-42",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "token_type": "Bearer",
  "exp": 1893456000
}
~~~

Nếu token không tồn tại, đã hết hạn hoặc không còn hiệu lực, phản hồi có thể chỉ là:

~~~json
{
  "active": false
}
~~~

**active: true chỉ là một bước của quyết định truy cập.** API vẫn phải kiểm tra có đúng audience, đủ scope và đủ quyền truy cập tài nguyên cụ thể. Các thuộc tính mà introspection endpoint trả về phụ thuộc Authorization Server, chính sách và giao thức đăng ký; không được giả định luôn có **sub**, **aud** hoặc **scope** theo cùng một kiểu dữ liệu.

### 5.3. Ưu điểm và giới hạn

Opaque token phù hợp khi Authorization Server muốn kiểm soát tập trung trạng thái token. API có thể nhận thông tin mới từ lần introspection gần nhất, nên việc thu hồi có thể được phản ánh sớm **nếu** mỗi request đều introspect và Authorization Server cập nhật trạng thái tương ứng.

Đổi lại:

- API phụ thuộc vào introspection endpoint qua mạng, cần xử lý độ trễ, timeout, lỗi kết nối và giới hạn tải.
- Nếu cache kết quả introspection, quyền đã bị thu hồi có thể vẫn được chấp nhận trong thời hạn cache; phải cân bằng hiệu năng và độ mới của quyết định truy cập.
- Introspection credential là một secret có đặc quyền cần bảo vệ; không dùng client secret của browser hoặc đưa credential này vào frontend.
- Opaque token không miễn trừ rủi ro lộ bearer token. Nếu kẻ tấn công có token còn hiệu lực, vẫn có nguy cơ phát lại.

## 6. JWT access token là gì?

**JSON Web Token (JWT)** là một định dạng chuẩn để biểu diễn các claim. Khi Authorization Server phát hành **JWT access token**, Resource Server có thể xác minh token bằng chữ ký số và các claim cần thiết, thường không phải gọi introspection cho mọi request.

Một JWT được ký theo dạng **JWS Compact Serialization** thường có ba phần, ngăn cách bằng dấu chấm:

~~~text
base64url(header).base64url(payload).base64url(signature)
~~~

Ví dụ khái niệm:

~~~text
eyJhbGciOiJSUzI1NiIsImtpZCI6ImtleS0xIn0.eyJzdWIiOiJlbXBsb3llZS00MiJ9.<chu-ky-minh-hoa>
~~~

Đây chỉ là ví dụ cấu trúc, **không phải token có chữ ký hợp lệ**. JWT còn có thể tồn tại dưới dạng JWE được mã hóa; trong nhiều hệ thống, JWT access token được sử dụng phổ biến nhất là JWS có chữ ký.

### 6.1. Header, payload, signature

**Header** mô tả cách xử lý chữ ký, ví dụ:

~~~json
{
  "typ": "at+jwt",
  "alg": "RS256",
  "kid": "signing-key-2026"
}
~~~

- **typ** có thể giúp thể hiện đây là access token theo JWT Profile for OAuth 2.0 Access Tokens (RFC 9068). Nhiều nhà cung cấp có định dạng riêng và không nhất thiết dùng giá trị này; Resource Server phải tuân theo hợp đồng token thực tế.
- **alg** chỉ thuật toán ký, ví dụ RS256. Bộ xác minh phải giới hạn những thuật toán được tin cậy thay vì chấp nhận tùy ý giá trị do token khai báo.
- **kid** là gợi ý chọn khóa trong tập khóa công khai. Nó **không tự xác nhận** khóa nào đáng tin; nguồn khóa phải được cấu hình/tin cậy từ trước.

**Payload** chứa claim. Một ví dụ JWT access token:

~~~json
{
  "iss": "https://id.example.test/realms/company",
  "sub": "employee-42",
  "aud": ["orders-api"],
  "client_id": "portal-web",
  "scope": "orders.read",
  "iat": 1893452400,
  "exp": 1893456000
}
~~~

Các giá trị trên chỉ mang tính minh họa; token thực phải có thời hạn phù hợp thời điểm cấp.

| Claim | Mục đích | Điều cần lưu ý |
|---|---|---|
| **iss** | Ai phát hành token? | Phải khớp issuer mà API tin cậy |
| **sub** | Chủ thể mà token đề cập | Có thể là người dùng hoặc client, tùy loại grant và nhà cung cấp |
| **aud** | Token dành cho tài nguyên/API nào? | Orders API chỉ chấp nhận audience phù hợp |
| **exp** | Thời điểm hết hạn (Unix epoch seconds) | Token hết hạn phải bị từ chối |
| **nbf** (nếu có) | Không được dùng trước thời điểm này | Cần kiểm tra khi claim tồn tại |
| **iat** | Thời điểm phát hành | Có ích cho chính sách kiểm tra tuổi token |
| **scope** hoặc **scp** | Các quyền truy cập được cấp | Cách biểu diễn phụ thuộc Authorization Server |
| **client_id**, **azp**, **jti** (nếu có) | Client nhận token, bên được ủy quyền hoặc mã định danh token | Chỉ dựa vào chúng khi được định nghĩa rõ trong hợp đồng token |

**Signature** giúp xác minh token chưa bị sửa và được ký bằng khóa thuộc về nhà phát hành được tin cậy. Khi dùng chữ ký bất đối xứng, Authorization Server giữ **private key**, còn Resource Server lấy **public key** từ nguồn **JWKS** đã được tin cậy để xác minh. Chữ ký đúng không có nghĩa token được phép gọi mọi API: vẫn phải kiểm tra issuer, audience, thời hạn và quyền.

### 6.2. JWT có chữ ký không đồng nghĩa JWT được mã hóa

Với JWT dạng JWS thông thường, header và payload chỉ được **Base64URL-encode**, không được mã hóa để giữ bí mật. Người có chuỗi token có thể đọc claim bằng cách giải mã Base64URL mà không cần khóa ký.

Do đó:

- **Không đặt mật khẩu, secret hoặc dữ liệu cá nhân không cần thiết** trong payload JWT.
- **Không coi việc decode payload là kiểm tra hợp lệ**. Một chuỗi giả mạo vẫn có thể decode thành JSON trông hợp lý.
- **Không chỉ đọc scope hoặc role mà bỏ qua chữ ký**.
- Nếu thực sự cần bảo mật nội dung token, phải có thiết kế phù hợp như **JWE** hoặc hạn chế claim, không suy diễn rằng “có chữ ký” đã bảo mật nội dung.

### 6.3. Xác minh JWT access token đúng cách

Resource Server thường cần kiểm tra:

1. **Cú pháp và chữ ký:** token là định dạng được hỗ trợ, thuật toán nằm trong danh sách tin cậy và chữ ký hợp lệ với khóa của issuer.
2. **Issuer:** **iss** khớp chính xác Authorization Server mà API đã cấu hình.
3. **Thời gian:** **exp**, **nbf** và các giới hạn thời gian khác đúng với chính sách; sai lệch đồng hồ cho phép phải nhỏ và có chủ đích.
4. **Audience:** **aud** chứa định danh Orders API, tránh nhận token được cấp cho Portal hoặc API khác.
5. **Loại token nếu hợp đồng yêu cầu:** không nhầm **ID Token** với **access token**. Với profile JWT access token, các yêu cầu về **typ**/claim phải được kiểm tra theo chuẩn và nhà cung cấp.
6. **Scope/authority:** token có **orders.read** cho API đọc đơn hàng; thiếu scope không được đi tiếp.
7. **Quyền đối tượng dữ liệu:** với người dùng An, API chỉ lấy những đơn hàng mà An được phép xem, ngay cả khi token mang **orders.read**.

Đừng tin một **alg** bất kỳ lấy từ token, đừng tự lấy khóa từ URL không được tin cậy trong header, và đừng bỏ xác minh chữ ký để “chạy được trên môi trường dev”. Các thư viện Resource Server của Spring Security cung cấp bộ kiểm tra JWT; cấu hình phải giới hạn issuer/khóa, audience và chính sách ứng dụng cho đúng.

### 6.4. Đặc điểm vận hành

JWT có lợi khi API muốn **xác minh cục bộ** và không phụ thuộc vào cuộc gọi introspection trên từng request. API vẫn có thể cần truy cập metadata hoặc JWKS để tải/cập nhật khóa khi khởi tạo và lúc luân chuyển khóa ký.

Ngược lại, một JWT đã cấp thường tiếp tục được chấp nhận cho đến **exp** nếu chỉ dùng kiểm tra chữ ký/claim cục bộ. Đăng xuất khỏi Portal **không tự động** khiến mọi JWT access token bị thu hồi ngay. Nếu hệ thống cần thu hồi nhanh, cân nhắc access token sống ngắn, blocklist/danh sách thu hồi, introspection bổ sung, quản lý khóa và chiến lược phù hợp với khả năng của IdP.

## 7. Phân biệt JWT access token với OIDC ID Token

Trong **OpenID Connect**, Authorization Server có thể trả về **ID Token** bên cạnh access token. Cả hai có thể có hình dạng JWT, nhưng **mục đích và đối tượng nhận khác nhau**:

| Thuộc tính | OIDC ID Token | OAuth 2.0 Access Token |
|---|---|---|
| Mục đích | Chứng minh sự kiện xác thực người dùng với **OIDC Client** | Cho phép client truy cập **Resource Server** |
| Bên nhận dự kiến | Portal / OIDC Relying Party | Orders API |
| Audience thường gặp | **client_id** của Portal | Định danh API/resource theo hợp đồng với Authorization Server |
| Nội dung | Claim xác thực, có thể gồm **nonce**, **auth_time**, **acr**, **amr** | Quyền truy cập, issuer, subject, audience, thời hạn và các claim đặc thù |
| Nơi sử dụng | Portal xác minh trong quá trình OIDC login | Portal gửi qua Bearer header; API xác minh |

**Sai lầm nguy hiểm:** Portal đăng nhập thành công và gửi **ID Token** trong header **Authorization: Bearer ...** khi gọi Orders API. Vì ID Token thường là JWT hợp lệ có chữ ký của cùng IdP, API có cấu hình kiểm tra lỏng lẻo có thể chấp nhận nhầm. API phải xác minh access token theo đúng hợp đồng và audience, không chỉ thấy chữ ký hợp lệ là đồng ý.

Ngoài ra, **refresh token** là thông tin để OAuth Client xin access token mới tại token endpoint theo chính sách của Authorization Server. **Không gửi refresh token cho Orders API**; nó thường có thời hạn dài và cần được bảo vệ nghiêm ngặt.

## 8. Spring Security OAuth 2.0 Client xử lý access token ra sao?

### 8.1. OAuth2AuthorizedClient giữ thông tin ủy quyền

Với một ứng dụng web Spring Boot dùng **spring-boot-starter-oauth2-client**, Spring Security có thể lưu một **OAuth2AuthorizedClient** gắn với:

- **ClientRegistration**: cấu hình của OAuth client, ví dụ registration ID **company**.
- **Principal**: người dùng hiện đang đăng nhập.
- **OAuth2AccessToken**: giá trị token, loại token, thời điểm cấp/hết hạn và scope được lưu theo mô hình client.
- **OAuth2RefreshToken** nếu Authorization Server cấp và cơ chế lưu trữ hỗ trợ.

**OAuth2AccessToken.getTokenValue()** trả chuỗi token để dùng cho lời gọi API. Client không phải phân tích JWT payload hoặc introspect token trước khi gửi. Đây là sự phân tách trách nhiệm có ích: **OAuth Client sử dụng token**; **Resource Server xác thực và phân quyền token**.

### 8.2. Cấu hình ví dụ cho Portal

Ví dụ với Spring Boot 3 / Spring Security 6, Portal là confidential web client sử dụng Authorization Code và OIDC login. Cấu hình sau chỉ minh họa; thay issuer, client ID và scope bằng giá trị của IdP thực tế.

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'
}
~~~

~~~yaml
# application.yml của Portal
spring:
  security:
    oauth2:
      client:
        registration:
          company:
            provider: company
            client-id: portal-web
            client-secret: ${OIDC_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - orders.read
        provider:
          company:
            issuer-uri: https://id.example.test/realms/company
~~~

Client secret phải được nạp từ nguồn cấu hình an toàn, không đưa trực tiếp vào repository. **openid** yêu cầu OIDC; **orders.read** là scope minh họa cần được Authorization Server cấu hình cho API. Định dạng access token (opaque/JWT) do Authorization Server quyết định, không được chọn chỉ bằng cách đổi tên một property trong cấu hình Portal.

SecurityFilterChain cơ bản:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class PortalSecurityConfig {
    @Bean
    SecurityFilterChain portalChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults())
            .oauth2Client(Customizer.withDefaults())
            .build();
    }
}
~~~

Ví dụ controller server-side sử dụng token của người dùng hiện tại:

~~~java
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.annotation.RegisteredOAuth2AuthorizedClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.client.RestClient;

@RestController
class OrdersProxyController {
    private final RestClient ordersApi =
        RestClient.create("https://orders.example.test");

    @GetMapping("/bff/orders")
    String orders(
        @RegisteredOAuth2AuthorizedClient("company")
        OAuth2AuthorizedClient authorizedClient
    ) {
        String token = authorizedClient.getAccessToken().getTokenValue();

        return ordersApi.get()
            .uri("/api/orders")
            .headers(headers -> headers.setBearerAuth(token))
            .retrieve()
            .body(String.class);
    }
}
~~~

Ở đoạn code này, **headers.setBearerAuth(token)** hoạt động như nhau với opaque token và JWT access token. **@RegisteredOAuth2AuthorizedClient("company")** yêu cầu authorized client gắn với registration **company** và principal hiện tại; không dùng một bearer token cố định dùng chung cho mọi người.

Với ứng dụng thực tế, cần xử lý token hết hạn, refresh nếu được cấp, lỗi 401/403 từ API, timeout và cách lưu authorized client trong môi trường nhiều instance. Có thể dùng **OAuth2AuthorizedClientManager** và HTTP client integration tương ứng để quản lý token nhất quán, thay vì phát triển cơ chế refresh thủ công không an toàn.

## 9. Spring Security Resource Server xác minh JWT access token

Orders API đóng vai trò Resource Server. Với JWT access token, Spring Security có thể xác minh chữ ký, issuer và các mốc thời gian từ thông tin của Authorization Server. API cần bổ sung audience và phân quyền theo nghiệp vụ.

### 9.1. Dependency và cấu hình

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
~~~

~~~yaml
# application.yml của Orders API, trường hợp JWT
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://id.example.test/realms/company

app:
  security:
    expected-audience: orders-api
~~~

**issuer-uri** là URI định danh nhà phát hành; framework có thể dùng discovery/JWKS theo khả năng của IdP. Chỉ khai báo issuer **chưa đủ** để mô tả audience của Orders API. Một cấu hình validator riêng giúp API từ chối token được cấp cho dịch vụ khác.

### 9.2. FilterChain kiểm tra scope

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class OrdersJwtSecurityConfig {

    @Bean
    SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
        return http
            .csrf(AbstractHttpConfigurer::disable)
            .sessionManagement(session ->
                session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/orders")
                    .hasAuthority("SCOPE_orders.read")
                .anyRequest().denyAll())
            .oauth2ResourceServer(oauth -> oauth.jwt(Customizer.withDefaults()))
            .build();
    }
}
~~~

Trong cấu hình thông thường, Spring Security chuyển **scope** có giá trị **orders.read** thành authority **SCOPE_orders.read**. Đối với token có **scp**, role hoặc cấu trúc claim riêng, có thể cần **JwtAuthenticationConverter** để ánh xạ chính xác, không nên mặc định mọi IdP dùng cùng một schema.

Đoạn **csrf.disable()** phù hợp với ví dụ **API stateless chỉ xác thực bearer header và không sử dụng cookie để xác thực**. Không áp dụng máy móc cho Portal dùng session cookie, nơi CSRF protection vẫn cần được xem xét.

### 9.3. Thêm kiểm tra audience cho JWT

Ví dụ một **JwtDecoder** xác minh issuer/thời hạn theo validator mặc định và kiểm tra audience **orders-api**:

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

@Configuration
class JwtDecoderConfig {

    @Bean
    JwtDecoder jwtDecoder(
        @Value("${spring.security.oauth2.resourceserver.jwt.issuer-uri}")
        String issuer,
        @Value("${app.security.expected-audience}")
        String expectedAudience
    ) {
        NimbusJwtDecoder decoder =
            NimbusJwtDecoder.withIssuerLocation(issuer).build();

        OAuth2TokenValidator<Jwt> audienceValidator = jwt ->
            jwt.getAudience().contains(expectedAudience)
                ? OAuth2TokenValidatorResult.success()
                : OAuth2TokenValidatorResult.failure(
                    new OAuth2Error(
                        "invalid_token", "Unexpected access token audience", null));

        decoder.setJwtValidator(new DelegatingOAuth2TokenValidator<>(
            JwtValidators.createDefaultWithIssuer(issuer),
            audienceValidator));

        return decoder;
    }
}
~~~

Ở đây **audienceValidator** không thay thế phép kiểm tra chữ ký hoặc issuer; nó bổ sung kiểm tra token thực sự được cấp cho **orders-api**. Nếu API phải tuân thủ thêm JWT access token profile, token type hoặc claim đặc thù của IdP, các điều kiện đó cần được kiểm tra riêng theo hợp đồng đã công bố.

**Resource Server xác minh identity không đồng nghĩa được quyền đọc mọi đối tượng.** Sau lớp filter, ứng dụng vẫn phải kiểm tra đơn hàng có thuộc chủ thể/tenant phù hợp hay không. Subject (**sub**) chỉ có ý nghĩa đúng khi token được cấp bởi issuer đáng tin và đã được kiểm tra.

## 10. Spring Security Resource Server xác minh opaque access token

Nếu Authorization Server cấp opaque access token, Orders API dùng **opaque-token introspection**. Dependency **spring-boot-starter-oauth2-resource-server** vẫn tương tự; phần cấu hình Resource Server thay đổi.

### 10.1. Cấu hình introspection

~~~yaml
# application.yml của Orders API, trường hợp opaque token
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://id.example.test/oauth2/introspect
          client-id: orders-api-introspector
          client-secret: ${INTROSPECTION_CLIENT_SECRET}
~~~

Đường dẫn introspection là **ví dụ**; URL thực tế phụ thuộc IdP. Thông tin **orders-api-introspector** dùng để Orders API xác thực khi introspect, khác với thông tin client dùng cho OIDC login ở Portal. Không công khai introspection client secret.

### 10.2. FilterChain dùng opaque token

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class OrdersOpaqueSecurityConfig {

    @Bean
    SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
        return http
            .csrf(AbstractHttpConfigurer::disable)
            .sessionManagement(session ->
                session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/orders")
                    .hasAuthority("SCOPE_orders.read")
                .anyRequest().denyAll())
            .oauth2ResourceServer(oauth ->
                oauth.opaqueToken(Customizer.withDefaults()))
            .build();
    }
}
~~~

Hai cấu hình trong mục 9 và mục 10 là **hai phương án thay thế cho cùng một Orders API**. Không đăng ký cả hai **SecurityFilterChain** có cấu hình request matcher giống hệt nhau trong cùng ứng dụng rồi mong Spring tự chọn theo hình dạng token.

Sau introspection thành công, Spring Security có thể ánh xạ scope thành authority có tiền tố **SCOPE_**. Nếu IdP trả dữ liệu hoặc chính sách audience theo cách riêng, ứng dụng cần cấu hình **OpaqueTokenIntrospector**/authorization logic phù hợp để xác minh rằng token được cấp cho Orders API. Không nên coi **active: true** là đủ để bỏ qua audience và quyền nghiệp vụ.

Để lấy danh tính, code xử lý opaque token có thể dùng **OAuth2AuthenticatedPrincipal** và các attribute do introspection trả về. Với JWT, principal thường là **Jwt**. Vì vậy, nếu triển khai controller gắn chặt với **@AuthenticationPrincipal Jwt**, đoạn controller đó không thể tự động áp dụng cho token opaque mà không đổi kiểu principal hoặc ánh xạ authentication.

## 11. Chọn opaque hay JWT access token theo yêu cầu hệ thống

| Tiêu chí | Opaque access token | JWT access token |
|---|---|---|
| API biết thông tin token bằng cách nào? | Thường qua introspection endpoint | Thường qua xác minh chữ ký/claim cục bộ |
| Phụ thuộc mạng ở từng request | Có, nếu introspect mỗi lần; giảm được bằng cache | Thường không, sau khi có khóa xác minh/JWKS |
| Độ trễ kiểm tra token | Chịu thêm network hop | Thường thấp hơn vì xác minh tại API |
| Thu hồi quyền/token | Có thể được phản ánh sớm khi introspect lại | Thường hiệu lực đến khi token hết hạn nếu chỉ kiểm tra cục bộ |
| Dữ liệu claim có lộ cho bên giữ token? | Thường không thể đọc trực tiếp từ chuỗi | Có thể đọc payload JWS; chữ ký không mã hóa |
| Mức độ linh hoạt của claim | Authorization Server quyết định dữ liệu trả qua introspection | Các claim đã được đóng gói tại thời điểm phát hành |
| Rủi ro vận hành nổi bật | Timeout, phụ thuộc IdP, credential và cache introspection | Quản lý khóa ký, luân chuyển JWKS, thời hạn và thu hồi |
| Điều kiện an toàn bắt buộc | TLS, kiểm tra **active**, audience, scope, quyền tài nguyên | TLS, chữ ký, issuer, audience, thời hạn, scope, quyền tài nguyên |

Không có định dạng nào **luôn tốt hơn** trong mọi trường hợp. Một số tổ chức ưu tiên opaque token vì kiểm soát trạng thái tập trung; hệ thống phân tán có thể dùng JWT để giảm tải introspection và cải thiện độ trễ. Quyết định cuối cùng còn phụ thuộc chính sách của IdP, vòng đời token, độ nhạy của quyền, nhu cầu thu hồi và kiến trúc vận hành.

Những điểm không đổi bất kể định dạng:

- Access token chỉ được dùng đúng **audience** và **scope**.
- Bearer token phải được giữ kín trong quá trình truyền, lưu trữ và ghi log.
- Quyền thao tác dữ liệu vẫn cần kiểm tra tại Resource Server.
- Client không nên phụ thuộc vào cấu trúc nội bộ của access token để triển khai giao diện.

## 12. Access token hết hạn, bị thu hồi hoặc bị đánh cắp

### 12.1. Hết hạn và refresh

Access token thường có thời gian sống giới hạn. Khi hết hạn, Resource Server phải từ chối request dùng token cũ. OAuth2 Client có thể dùng **refresh token** để xin access token mới nếu Authorization Server đã cấp refresh token, grant cho phép và client được cấu hình xử lý refresh. Nếu không thể refresh, client cần khởi động lại luồng ủy quyền hoặc xử lý lỗi đăng nhập phù hợp.

Refresh token có quyền nhạy cảm hơn access token vì có thể dùng để xin token tiếp theo; nó cần được lưu và bảo vệ phía phù hợp, không gửi qua Bearer header cho Resource Server.

### 12.2. Thu hồi và logout

**Logout khỏi Portal** thường chấm dứt HTTP session của Portal, nhưng **không mặc nhiên** thu hồi access token đã cấp. Việc thu hồi phụ thuộc Authorization Server, token revocation endpoint/chính sách, trạng thái phiên, thời hạn token và cơ chế xác minh ở API.

Với opaque token, introspection sau khi bị thu hồi có thể trả **active: false**. Với JWT access token chỉ xác minh cục bộ, API thường không tự nhận ra sự kiện thu hồi trừ khi có chiến lược bổ sung. Hạ thời gian sống token giúp giảm cửa sổ rủi ro nhưng tăng nhu cầu cấp lại token.

### 12.3. Hạn chế rủi ro đánh cắp bearer token

Các biện pháp cơ bản gồm HTTPS, tránh lộ token vào URL/log, chỉ cấp scope tối thiểu, phát hành token ngắn hạn phù hợp, bảo vệ token ở client và dùng audience rõ ràng. Khi yêu cầu chống phát lại mạnh hơn, có thể xem xét **sender-constrained access tokens** như mTLS-bound access token hoặc DPoP nếu hệ sinh thái hỗ trợ; đó là thay đổi về cơ chế chứng minh bên gửi, không đơn thuần là chuyển opaque sang JWT.

## 13. 401, 403 và những tình huống kiểm tra thường gặp

Ví dụ client gọi Orders API:

~~~bash
curl -i "https://orders.example.test/api/orders" \
  -H "Authorization: Bearer ACCESS_TOKEN_VALUE"
~~~

Trong thực tế, dùng token được cấp hợp lệ từ môi trường thử nghiệm và tránh để token thật trong shell history hoặc log. Không dùng trực tiếp các chuỗi token minh họa trong bài làm credential.

| Tình huống | Kết quả API thường trả | Giải thích |
|---|---|---|
| Không có Bearer token | **401 Unauthorized** | Chưa có thông tin xác thực cho Resource Server |
| Token sai chữ ký, sai issuer, hết hạn hoặc **active: false** | **401 Unauthorized** | Token không được chấp nhận |
| JWT hợp lệ nhưng audience không chứa **orders-api** | **401 Unauthorized** | Đây không phải token dành cho API này |
| Token hợp lệ nhưng thiếu **orders.read** | **403 Forbidden** | Đã xác thực nhưng không đủ authority |
| Có **orders.read** nhưng yêu cầu đọc đơn của người dùng khác | **403 Forbidden** hoặc **404 Not Found**, theo chính sách che giấu tài nguyên | Tầng nghiệp vụ từ chối tài nguyên |
| Token hợp lệ, đủ scope và quyền bản ghi | **200 OK** | API trả dữ liệu đã được phép |
| Introspection server tạm thời không khả dụng | Không cấp quyền dựa trên phỏng đoán; trả lỗi phù hợp với cách triển khai | Phải xử lý lỗi upstream và timeout an toàn |

Khi trả lỗi xác thực, Resource Server có thể sử dụng header **WWW-Authenticate: Bearer** với thông tin lỗi theo giao thức, ví dụ **invalid_token** hoặc **insufficient_scope**. Không ghi access token thật vào response lỗi.

Một ví dụ về lỗi 401:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
~~~

Một ví dụ về lỗi 403 khi thiếu scope:

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope", scope="orders.read"
~~~

Các header chính xác có thể thay đổi theo cấu hình exception handling và AccessDeniedHandler của ứng dụng.

## 14. Các nhầm lẫn thường gặp

**“Bearer token là JWT.”** Sai. Bearer mô tả cách trình bày token và đặc tính sử dụng; token bên trong có thể là opaque hoặc JWT.

**“Opaque token luôn an toàn hơn vì không đọc được payload.”** Không hẳn. Chuỗi opaque vẫn là credential; nếu bị lộ, người khác có thể trình bày nó. Mức an toàn phụ thuộc xác minh, thời hạn, bảo vệ khi truyền/lưu trữ và chính sách quyền.

**“JWT có chữ ký thì dữ liệu bên trong đã được mã hóa.”** Sai với JWT JWS thông thường. Payload Base64URL có thể đọc được; chữ ký giúp kiểm tra tính toàn vẹn và nguồn phát hành.

**“Decode JWT thành công nghĩa là token hợp lệ.”** Sai. Decode là thao tác đọc dữ liệu; cần xác minh chữ ký và claim, đặc biệt **iss**, **aud**, **exp**, các ràng buộc thời gian và token type khi áp dụng.

**“Cùng một IdP ký token thì có thể dùng ở mọi API.”** Sai. Mỗi API phải từ chối token có audience khác và thực thi scope/chính sách riêng.

**“Có scope orders.read nghĩa là đọc được mọi đơn hàng.”** Sai. Scope xác định khả năng ở mức API; API vẫn phải kiểm tra quyền trên từng tài nguyên, tenant hoặc chủ thể.

**“ID Token cũng là JWT nên dùng làm Bearer access token được.”** Sai. OIDC ID Token dành cho client xác minh đăng nhập; API cần access token cấp cho API và được kiểm tra theo hợp đồng access token.

**“JWT không bao giờ cần kết nối tới IdP.”** Sai. API có thể cần metadata/JWKS khi khởi tạo hoặc luân chuyển khóa; một số kiến trúc còn cần kiểm tra quyền/thu hồi bổ sung.

**“Opaque token bắt buộc được introspect từng request.”** Không bắt buộc ở mức khái niệm: đó là cơ chế thường dùng. Hệ thống có thể cache, hoặc có cách xác minh nội bộ khác theo hợp đồng, nhưng cache tạo độ trễ trong cập nhật trạng thái quyền.

## 15. Bài tập áp dụng

Giả sử Portal nhận access token và cần gọi hai API:

- **Orders API** yêu cầu audience **orders-api** và scope **orders.read**.
- **Payroll API** yêu cầu audience **payroll-api** và scope **payroll.read**.

Hãy đánh giá các trường hợp:

1. Access token là JWT, có **aud=["orders-api"]**, **scope="orders.read"**, chữ ký hợp lệ, chưa hết hạn. Có thể gửi đến Payroll API không?
2. Access token là opaque; introspection trả **active=true**, **aud=["orders-api"]**, **scope="orders.read"**. Orders API có thể kết luận người dùng đọc được đơn hàng của mọi nhân viên không?
3. Browser đánh cắp được Bearer header từ một request Portal → Orders API. JWT hay opaque có tự động ngăn kẻ tấn công dùng lại token không?
4. Portal vừa logout. Một JWT access token còn hạn 10 phút đã được cấp trước đó có tự động bị Orders API từ chối không?

**Gợi ý đối chiếu:** (1) Không, token dành cho Orders API, không phải Payroll API. (2) Không, còn phải kiểm tra quyền trên từng đơn hàng. (3) Không, bearer token thông thường có rủi ro bị phát lại bất kể định dạng; cần ngăn rò rỉ hoặc cơ chế ràng buộc bên gửi phù hợp. (4) Không mặc nhiên; phụ thuộc cơ chế thu hồi và xác minh token.

## 16. Ghi nhớ khi thiết kế Spring Security OAuth 2.0/OIDC

Mô hình tư duy hữu ích là **ba lớp liên tiếp**:

1. **Bearer** mô tả **client trình bày token như thế nào** trong lời gọi HTTP đến API.
2. **Opaque hoặc JWT** mô tả **Authorization Server phát hành token với biểu diễn gì** và **Resource Server cần xác minh bằng cơ chế nào**: introspection hoặc xác minh chữ ký/claim.
3. **Authorization ở API** quyết định **token hợp lệ đó có được thực hiện thao tác trên tài nguyên cụ thể hay không**.

Spring Security OAuth 2.0 Client giúp ứng dụng lấy, giữ và gửi access token; Spring Security Resource Server giúp API xác minh token, thiết lập principal và ánh xạ authority. Dù token là opaque hay JWT, những kiểm tra về audience, scope, thời hạn và quyền đối tượng dữ liệu vẫn là điều kiện cần để gọi API an toàn thay mặt người dùng.
