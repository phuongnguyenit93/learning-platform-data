# OpenID Provider Configuration và OpenID Connect Discovery

## 1. Vì sao Authorization Server cần OpenID Connect Discovery?

Khi một ứng dụng Spring Boot đóng vai trò **OpenID Connect Relying Party (RP)**, nó cần biết địa chỉ Authorization Endpoint, Token Endpoint, UserInfo Endpoint, nơi lấy public keys để kiểm tra ID Token và các thuật toán/response type mà OpenID Provider (OP) hỗ trợ. Nếu cấu hình tay từng URL và key, mỗi lần đổi domain, cổng, đường dẫn hoặc xoay khóa đều dễ dẫn đến cấu hình lệch giữa client và Authorization Server.

**OpenID Connect Discovery 1.0** giải quyết bài toán bằng cách cung cấp một tài liệu JSON chuẩn, gọi là **OpenID Provider Configuration** (OP Configuration), chứa thông tin về issuer, các endpoint và khả năng của OP. RP đọc tài liệu này để thiết lập OIDC login và biết cần lấy public keys ở đâu.

Ví dụ, với issuer:

~~~text
https://auth.example.com
~~~

đường dẫn OpenID Provider Configuration chuẩn là:

~~~text
https://auth.example.com/.well-known/openid-configuration
~~~

Đây là bài thuộc chương **Metadata và Discovery** trong module `SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER`, tập trung vào cách thiết kế, cấu hình, bảo mật, kiểm thử và vận hành OAuth 2.0/OIDC Authorization Server bằng Spring Security và Spring Authorization Server (SAS).

Sau bài học, bạn cần làm được:
1. Phân biệt **Issuer Discovery**, **OpenID Provider Configuration** và **JWKS**.
2. Dựng đúng URL `/.well-known/openid-configuration`, kể cả issuer có path.
3. Đọc và giải thích các metadata bắt buộc, được khuyến nghị và tùy chọn.
4. Kiểm chứng chuỗi tin cậy `issuer → metadata → JWKS → ID Token`.
5. Phân biệt OIDC Discovery với OAuth 2.0 Authorization Server Metadata (RFC 8414).
6. Bật và tùy chỉnh Provider Configuration Endpoint trong SAS, đồng thời cấu hình RP/Resource Server Spring.
7. Viết contract test về tính nhất quán, bảo mật và sự sẵn sàng của discovery endpoint.

## 2. Ba khái niệm khác nhau: Issuer, Metadata, JWKS

| Thuật ngữ | Vai trò | Ví dụ | Có chứa private key? |
| --- | --- | --- | --- |
| **Issuer Identifier** | Định danh duy nhất của OP và giá trị kỳ vọng trong `iss` của ID Token | `https://auth.example.com` | Không |
| **OpenID Provider Configuration** | JSON mô tả OP, endpoint và khả năng | `/.well-known/openid-configuration` | Không |
| **JWKS (JSON Web Key Set)** | Tập public keys để kiểm tra chữ ký do OP phát hành | `https://auth.example.com/oauth2/jwks` | **Không được** chứa private/symmetric key values |
| **ID Token** | JWT mang thông tin xác thực end-user | Nhận từ token response hợp lệ | Không phải metadata |
| **OAuth Access Token** | Credential để gọi protected resource | Được cấp theo OAuth grant | Không phải ID Token |

Tài liệu Discovery **không** phải nơi lưu token, client secret hay private signing key. Trường `jwks_uri` trong metadata là địa chỉ dẫn đến JSON Web Key Set, không phải bản thân public key và càng không phải khóa ký bí mật.

### 2.1. Luồng từ issuer đến OIDC login

~~~mermaid
sequenceDiagram
    autonumber
    participant RP as Spring Boot RP
    participant OP as Authorization Server / OP
    participant BR as Browser
    RP->>OP: GET /.well-known/openid-configuration
    OP-->>RP: 200 JSON: issuer, endpoints, jwks_uri, algorithms
    RP->>OP: GET /oauth2/jwks
    OP-->>RP: Public JWK Set
    RP->>BR: Redirect tới authorization_endpoint
    BR->>OP: OIDC Authorization Code + PKCE request
    OP-->>BR: Redirect về RP với code và state
    BR-->>RP: Callback với authorization code
    RP->>OP: POST token_endpoint kèm code và PKCE verifier
    OP-->>RP: ID Token / Access Token
    RP->>RP: Xác minh chữ ký, iss, aud, exp, nonce
~~~

Trong thực tế, `jwks_uri` có thể được truy vấn khi decoder cần xác minh token, được cache hoặc làm mới theo vòng đời key; thứ tự trong sơ đồ thể hiện quan hệ dữ liệu chứ không khẳng định mọi thư viện tải JWKS trước khi bắt đầu đăng nhập.

**Ranh giới trách nhiệm:** Discovery cho RP biết *nên gửi yêu cầu đi đâu* và *OP công bố hỗ trợ điều gì*. Nó không xác thực người dùng và không làm cho một ID Token không hợp lệ trở nên hợp lệ.

## 3. OpenID Connect Discovery gồm hai quá trình

### 3.1. Issuer Discovery qua WebFinger là tùy chọn

Đôi khi người dùng chỉ cung cấp một định danh như email hoặc URL cá nhân, thay vì URL của OP. OpenID Connect Discovery có cơ chế WebFinger để tìm issuer từ định danh đó.

Ví dụ:

~~~http
GET /.well-known/webfinger?resource=acct%3Aalice%40example.com&rel=http%3A%2F%2Fopenid.net%2Fspecs%2Fconnect%2F1.0%2Fissuer HTTP/1.1
Host: example.com
~~~

Response minh họa:

~~~json
{
  "subject": "acct:alice@example.com",
  "links": [
    {
      "rel": "http://openid.net/specs/connect/1.0/issuer",
      "href": "https://auth.example.com"
    }
  ]
}
~~~

`rel` được dùng để tìm OpenID Connect issuer:

~~~text
http://openid.net/specs/connect/1.0/issuer
~~~

Issuer location trả về qua `href` có thể khác host/domain trong định danh người dùng ban đầu. Đây là nguồn dữ liệu nhạy cảm về bảo mật, không phải một URL tùy ý có thể tin ngay.

**Quan trọng:** WebFinger là bước **optional**. Nếu RP đã được cấu hình issuer bằng kênh tin cậy, chẳng hạn `spring.security.oauth2.client.provider.corporate.issuer-uri`, RP có thể bỏ qua WebFinger và chuyển thẳng sang lấy OP Configuration. Trong nhiều triển khai doanh nghiệp với một IdP cố định, không cần làm WebFinger.

### 3.2. Lấy OpenID Provider Configuration là bước metadata

Khi đã biết issuer, RP gửi HTTP **GET** đến đường dẫn well-known theo quy tắc OIDC. Response thành công phải là HTTP `200 OK` và JSON object với `Content-Type: application/json`.

~~~http
GET /.well-known/openid-configuration HTTP/1.1
Host: auth.example.com
Accept: application/json
~~~

RP phải xác minh TLS server certificate và **so sánh issuer chính xác** giữa issuer kỳ vọng và trường `issuer` trong metadata. Nếu không khớp, phải dừng tiến trình sử dụng metadata đó.

## 4. Dựng URL /.well-known/openid-configuration chính xác

### 4.1. Issuer không có path

| Issuer | OIDC Provider Configuration URL |
| --- | --- |
| `https://auth.example.com` | `https://auth.example.com/.well-known/openid-configuration` |
| `https://auth.example.com:9443` | `https://auth.example.com:9443/.well-known/openid-configuration` |

Issuer phải dùng HTTPS trong deployment tuân thủ chuẩn; URL không được có query hoặc fragment. Một hệ thống có thể dùng HTTP loopback cho test local tùy công cụ, nhưng không nên coi HTTP nội bộ/production là OIDC Discovery hợp lệ theo đặc tả.

### 4.2. Issuer có path: well-known được nối ở cuối issuer

OIDC Discovery 1.0 quy định: nếu issuer chứa path, loại bỏ dấu `/` cuối (nếu có), rồi nối `/.well-known/openid-configuration`:

| Issuer | OIDC Provider Configuration URL |
| --- | --- |
| `https://auth.example.com/tenant-a` | `https://auth.example.com/tenant-a/.well-known/openid-configuration` |
| `https://auth.example.com/idp/company` | `https://auth.example.com/idp/company/.well-known/openid-configuration` |
| `https://auth.example.com/tenant-a/` | `https://auth.example.com/tenant-a/.well-known/openid-configuration` |

Đặc biệt, `https://auth.example.com/tenant-a` là một issuer khác `https://auth.example.com/tenant-b`. Trong kiến trúc nhiều tenant, RP phải map đúng tenant → issuer → metadata → public keys và không dùng lẫn khóa giữa tenant.

### 4.3. Khác với đường dẫn OAuth metadata theo RFC 8414

Một nguồn gây nhầm lẫn là RFC 8414 dùng cách **chèn** well-known path trước issuer path:

~~~text
Issuer: https://auth.example.com/tenant-a

OIDC Discovery 1.0:
  https://auth.example.com/tenant-a/.well-known/openid-configuration

OAuth 2.0 Authorization Server Metadata (RFC 8414):
  https://auth.example.com/.well-known/oauth-authorization-server/tenant-a
~~~

Hai tài liệu có thể cùng mô tả một Authorization Server, nhưng quy tắc dựng URL, trường metadata bắt buộc và phạm vi sử dụng không hoàn toàn giống nhau.

Một số thư viện Spring Security có logic thử nhiều vị trí discovery để tăng khả năng tương thích. Hành vi đó không thay đổi định nghĩa OIDC chính thức; không tự diễn giải rằng một server bắt buộc phải cung cấp tất cả các path đó.

### 4.4. Issuer và endpoints có thể không nằm cùng path

Metadata có thể chứa:
- `issuer=https://auth.example.com/tenant-a`;
- `authorization_endpoint=https://auth.example.com/oauth2/authorize`;
- `token_endpoint=https://auth.example.com/oauth2/token`.

Điều quan trọng là các endpoint phải được OP công bố chính xác và phục vụ đúng issuer. Không đoán endpoint bằng cách nối `/authorize` hoặc `/token` sau issuer, cũng không suy `jwks_uri` từ tên domain. RP phải dùng endpoint theo metadata đã được xác minh.

## 5. Các trường bắt buộc của OpenID Provider Configuration

Theo OpenID Connect Discovery 1.0, các metadata sau cần được xử lý cẩn thận:

| Tên trường | Mức yêu cầu trong đặc tả | Ý nghĩa |
| --- | --- | --- |
| `issuer` | **REQUIRED** | URL issuer của OP; phải bằng `iss` trong ID Token |
| `authorization_endpoint` | **REQUIRED** | Endpoint nhận authorization request |
| `token_endpoint` | **REQUIRED trừ khi chỉ dùng Implicit Flow** | Endpoint đổi authorization code lấy tokens; flow hiện đại luôn cần |
| `jwks_uri` | **REQUIRED** | HTTPS URL chứa các public JWK để xác minh chữ ký |
| `response_types_supported` | **REQUIRED** | Các giá trị `response_type` OP hỗ trợ |
| `subject_types_supported` | **REQUIRED** | Các loại Subject Identifier hỗ trợ, ví dụ `public`, `pairwise` |
| `id_token_signing_alg_values_supported` | **REQUIRED** | Thuật toán JWS để ký ID Token; đặc tả yêu cầu có `RS256` |

Cần phân biệt **mức bắt buộc của metadata** và **mức bắt buộc của một OAuth/OIDC feature**. Ví dụ:
- Metadata `subject_types_supported` là bắt buộc, nhưng OP không nhất thiết hỗ trợ cả `public` lẫn `pairwise`; chỉ công bố giá trị thực sự hỗ trợ.
- Metadata `response_types_supported` là bắt buộc, nhưng không được công bố `id_token token` nếu runtime không xử lý Implicit Flow. Trong OIDC Discovery 1.0 có yêu cầu lịch sử riêng đối với Dynamic OpenID Providers về các response type; khi thiết kế hiện đại cần ưu tiên Authorization Code + PKCE và đối chiếu profile tuân thủ thực tế.
- `id_token_signing_alg_values_supported` không phải danh sách thuật toán mà client tùy tiện chọn cho mọi loại token. Nó mô tả **ID Token**, không đồng nghĩa danh sách thuật toán access token hoặc request object.
- `jwks_uri` không đồng nghĩa một URL cố định do spec ép buộc: endpoint cụ thể do OP công bố.

### 5.1. Metadata issuer là hợp đồng bảo mật, không chỉ tên hiển thị

Nếu RP cấu hình issuer kỳ vọng là:

~~~text
https://auth.example.com
~~~

nhưng metadata trả:

~~~json
{"issuer": "https://auth.example.com/other-tenant"}
~~~

thì RP phải **từ chối** metadata đó; không tự bỏ path, đổi hostname, cắt hậu tố hoặc chuyển về issuer khác. Tương tự, issuer có dấu `/` cuối, chữ hoa, cổng và path phải được xử lý theo so khớp URI/string đã định nghĩa; không viết hàm so sánh “gần giống” tùy tiện.

Đặc tả OIDC yêu cầu issuer của metadata **giống hệt** issuer dùng để truy vấn và claim `iss` trong ID Token. Đây là một trong những cách quan trọng nhất để tránh OP impersonation.

### 5.2. Các trường của ID Token không được suy từ metadata

Metadata giúp client biết issuer và key set, nhưng ID Token vẫn phải được xác minh riêng:
- JWS signature bằng key phù hợp và thuật toán được cho phép.
- `iss` bằng issuer đã tin cậy.
- `aud` chứa client ID phù hợp; `azp` nếu profile/yêu cầu áp dụng.
- `exp`/`iat` và các ràng buộc thời gian.
- `nonce` nếu client đã dùng nonce trong authorization request.
- `at_hash`, `c_hash` hoặc ràng buộc khác tùy response type/profile.

Chỉ vì `jwks_uri` trả 200 và có khóa `kid` trùng token không có nghĩa ID Token đã hợp lệ. `kid` chỉ giúp tìm key; chữ ký và claims phải được kiểm tra bằng library tin cậy.

## 6. Nhóm metadata được khuyến nghị và tùy chọn

| Trường | Ý nghĩa | Ghi chú triển khai |
| --- | --- | --- |
| `userinfo_endpoint` | Endpoint trả user claims sau khi có access token phù hợp | RECOMMENDED; không phải OP nào cũng mở |
| `registration_endpoint` | Dynamic Client Registration Endpoint | RECOMMENDED trong Discovery nhưng SAS không bật mặc định |
| `scopes_supported` | Các scope được OP công bố | RECOMMENDED; OP phải hỗ trợ `openid` |
| `token_endpoint_auth_methods_supported` | Phương thức xác thực client tại Token Endpoint | Nếu bỏ qua, mặc định OIDC là `client_secret_basic` |
| `token_endpoint_auth_signing_alg_values_supported` | JWS alg được hỗ trợ khi client dùng JWT assertion | Không tự bật `private_key_jwt` chỉ vì có alg |
| `response_modes_supported` | `query`, `fragment`, `form_post`... theo feature | Nếu vắng, OIDC 1.0 quy định mặc định `query` và `fragment` cho Dynamic OP |
| `grant_types_supported` | Các OAuth grants OP công bố | Nếu vắng có default lịch sử `authorization_code` và `implicit` |
| `acr_values_supported` | Các mức ngữ cảnh xác thực | Không có nghĩa client được yêu cầu ACR bất kỳ |
| `claims_supported` | Những claim OP có thể trả | Không bảo đảm mọi user có mọi claim |
| `claim_types_supported` | Kiểu claim `normal`, `aggregated`, `distributed` | Chỉ công bố loại thực sự hỗ trợ |
| `claims_parameter_supported` | OP có hỗ trợ OIDC `claims` request parameter không | Mặc định `false` khi vắng |
| `request_parameter_supported` | OP có hỗ trợ JWT Request Object trong `request` không | Mặc định `false` khi vắng |
| `request_uri_parameter_supported` | Request Object URI theo OIDC Discovery | Mặc định `true` khi vắng, không phải bằng chứng hỗ trợ PAR |
| `require_request_uri_registration` | Yêu cầu đăng ký trước URI của Request Object | Mặc định `false` |
| `end_session_endpoint` | RP-Initiated Logout endpoint khi profile hỗ trợ | Do đặc tả/logout extension bổ sung |
| `pushed_authorization_request_endpoint` | PAR endpoint theo RFC 9126 | Khác OpenID `request_uri_parameter_supported` |
| `require_pushed_authorization_requests` | Policy yêu cầu PAR theo RFC 9126 | Phải khớp enforcement thực tế |

Trong việc đọc metadata, hãy phân biệt rõ:
1. Một trường **vắng mặt** có thể có giá trị mặc định theo chuẩn, hoặc đơn giản là feature không được công bố.
2. Một trường **có mặt** phải phản ánh năng lực thực tế; không suy ra từ dependency tồn tại.
3. Một metadata **được công bố** không tự thay thế chính sách cho từng `RegisteredClient`: client A có thể được phép dùng method/grant mà client B không được phép.

**Không cố làm JSON thật dài để “trông đầy đủ”.** JSON sai sự thật gây ra lỗi liên thông và có thể khiến RP dùng một grant/method yếu hoặc không hoạt động.

## 7. Ví dụ OpenID Provider Configuration response

Với một OP được triển khai ở `https://auth.example.com`, ví dụ JSON **minh họa**:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
~~~

~~~json
{
  "issuer": "https://auth.example.com",
  "authorization_endpoint": "https://auth.example.com/oauth2/authorize",
  "token_endpoint": "https://auth.example.com/oauth2/token",
  "userinfo_endpoint": "https://auth.example.com/userinfo",
  "jwks_uri": "https://auth.example.com/oauth2/jwks",
  "response_types_supported": ["code"],
  "subject_types_supported": ["public"],
  "id_token_signing_alg_values_supported": ["RS256"],
  "scopes_supported": ["openid", "profile", "email"],
  "token_endpoint_auth_methods_supported": [
    "client_secret_basic",
    "private_key_jwt"
  ],
  "grant_types_supported": ["authorization_code", "refresh_token"],
  "code_challenge_methods_supported": ["S256"],
  "claims_supported": ["sub", "name", "email", "email_verified"]
}
~~~

Ví dụ giả định runtime thực sự hỗ trợ tất cả field được công bố. Không lấy phần danh sách grants/algorithms của ví dụ làm cam kết rằng **mọi phiên bản SAS** bật sẵn `private_key_jwt`, `refresh_token` hoặc trả đủ các claim đó. RP sẽ phải đăng ký client phù hợp và server phải thực thi quyền.

Với hệ thống hiện đại chủ trương chỉ Authorization Code + PKCE, `response_types_supported=["code"]` là mô tả feature thực tế; một số yêu cầu tuân thủ lịch sử của “Dynamic OpenID Providers” trong OIDC Discovery 1.0 còn bao gồm Implicit response types. Hãy chọn profile an toàn thực tế và kiểm tra yêu cầu chứng nhận/conformance thay vì công bố flow không chạy.

### 7.1. Những điều RP có thể suy ra an toàn

Từ JSON mẫu, RP biết:
- Issuer nào được kỳ vọng trong ID Token.
- URL nào nhận authorization request và token request.
- URL nào chứa public keys.
- RP có thể đề nghị `response_type=code`.
- OP công bố `RS256` để ký ID Token.
- OP công bố `openid`, `profile`, `email`; nhưng từng client/user vẫn chịu chính sách riêng.

RP **không** thể suy:
- Email claim luôn được trả.
- Tất cả user đều đủ điều kiện login.
- Tất cả client được phép `private_key_jwt`.
- Access token có cùng cấu trúc hoặc chữ ký alg với ID Token.
- OP đã có dynamic client registration khi `registration_endpoint` vắng.
- Thêm `scope=admin` vào request sẽ được phê duyệt.

### 7.2. Mẫu response không hợp lệ

~~~json
{
  "issuer": "https://auth.example.com",
  "authorization_endpoint": "http://auth.internal/oauth2/authorize",
  "jwks_uri": "https://auth.example.com/oauth2/jwks",
  "response_types_supported": [],
  "subject_types_supported": ["public"]
}
~~~

Các vấn đề rõ ràng:
- `authorization_endpoint` dùng HTTP, không hợp lệ theo yêu cầu HTTPS của OIDC Discovery.
- `id_token_signing_alg_values_supported` vắng.
- `response_types_supported` là array rỗng; không công bố response type nào.
- `token_endpoint` vắng dù deployment không chỉ Implicit Flow.

Khi metadata không qua validation, RP phải **ngừng** quy trình phụ thuộc vào nó; không âm thầm tự sinh URL hay mặc định thuật toán không rõ nguồn.

## 8. Discovery không phải JWKS và không phải OAuth metadata

### 8.1. OpenID Provider Configuration

~~~text
GET https://auth.example.com/.well-known/openid-configuration
→ JSON gồm issuer, authorization_endpoint, token_endpoint,
  userinfo_endpoint, jwks_uri, subject_types_supported,
  id_token_signing_alg_values_supported, ...
~~~

Mục tiêu là giúp RP cấu hình OpenID Connect và xác minh ID Token.

### 8.2. JWK Set

~~~text
GET https://auth.example.com/oauth2/jwks
→ JSON có mảng "keys" gồm các public JWK
~~~

Ví dụ JWK Set rút gọn:

~~~json
{
  "keys": [
    {
      "kty": "RSA",
      "kid": "signing-key-2026-a",
      "use": "sig",
      "alg": "RS256",
      "n": "BASE64URL_MODULUS",
      "e": "AQAB"
    }
  ]
}
~~~

Trong triển khai thật, `n` và `e` là key material được mã hóa Base64URL; placeholder trên không phải khóa có thể dùng. Private RSA parameters `d`, `p`, `q` ... **không được xuất hiện** trong public JWK Set.

RP cần kiểm tra `kid`, `kty`, `alg`, `use` và tính hợp lệ của chữ ký theo policy. Trong key rotation, OP có thể công bố nhiều public keys một thời gian để client vẫn xác minh token đã phát hành bằng key cũ.

### 8.3. OAuth Authorization Server Metadata theo RFC 8414

~~~text
GET https://auth.example.com/.well-known/oauth-authorization-server
→ JSON mô tả OAuth Authorization Server
~~~

RFC 8414 phục vụ OAuth client/Resource Server, kể cả ứng dụng không dùng OIDC. Hai metadata document có những trường chung, nhưng:
- OIDC yêu cầu `subject_types_supported` và `id_token_signing_alg_values_supported`.
- OAuth metadata không bắt buộc hai trường này.
- `userinfo_endpoint` và các claim của ID Token thuộc OIDC/extension.
- RFC 8414 có URL well-known riêng; với issuer path cách dựng khác như đã nêu.
- Không sửa JSON bằng cách đổi tên endpoint file; server phải thực sự phục vụ đúng contract.

Spring Authorization Server có **OAuth2AuthorizationServerMetadataEndpointFilter** phục vụ OAuth metadata theo RFC 8414. **OidcProviderConfigurationEndpointFilter** phục vụ OP Configuration khi OIDC được bật. Hai filter/endpoint khác nhau dù có thể chia sẻ `issuer`, authorization endpoint, token endpoint và JWKS.

### 8.4. Metadata chỉ công bố các capability đã triển khai

Đặc biệt chú ý các extension:
- `end_session_endpoint`: không giả định logout hoạt động chỉ vì OIDC đã bật.
- `pushed_authorization_request_endpoint`: phải thực sự có PAR endpoint.
- `require_pushed_authorization_requests`: đừng đặt true nếu Authorization Endpoint vẫn nhận request không qua PAR.
- `request_uri_parameter_supported`: liên quan OIDC/JAR Request Object, không phải công tắc bật PAR.
- `registration_endpoint`: không công bố nếu dynamic registration chưa được bật và bảo vệ.

Hãy kiểm thử thực tế từng endpoint và option được quảng cáo.

## 9. Bật OIDC Provider Configuration trong Spring Authorization Server

### 9.1. OAuth metadata mặc định không đồng nghĩa OIDC đã bật

Trong Spring Authorization Server **1.5.x**, cấu hình Authorization Server mặc định hỗ trợ OAuth 2.0 Authorization Server Metadata Endpoint theo RFC 8414. Tuy nhiên, **OpenID Connect 1.0 bị tắt trong cấu hình mặc định**. Muốn có OP Configuration, UserInfo và những thành phần OIDC khác, cần khởi tạo `OidcConfigurer`.

Một số thành phần SAS quan trọng:

| Thành phần | Vai trò |
| --- | --- |
| `OAuth2AuthorizationServerConfigurer` | Tập hợp các protocol endpoint và filter của Authorization Server |
| `OidcConfigurer` | Kích hoạt cấu hình giao thức OIDC |
| `OidcProviderConfigurationEndpointConfigurer` | Extension point để tùy chỉnh OP Configuration |
| `OidcProviderConfigurationEndpointFilter` | Trả JSON OP Configuration cho request GET hợp lệ |
| `OidcProviderConfiguration.Builder` | Tạo/cập nhật claims metadata của OP |
| `OAuth2AuthorizationServerMetadataEndpointFilter` | Phục vụ OAuth metadata RFC 8414; **không phải** OP Configuration |
| `AuthorizationServerSettings` | Cấu hình issuer, các đường dẫn endpoint phía server |
| `JWKSource<SecurityContext>` | Cấp tập public keys cho JWKS endpoint và hạ tầng ký token |

Trong SAS 1.5.x, nếu không đăng ký `JWKSource<SecurityContext>` bean thì JWKS endpoint mặc định **không được cấu hình**. Đó là một phần hạ tầng bắt buộc phải có khi bạn muốn RP xác minh ID Token ký bất đối xứng theo JWKS.

### 9.2. Cấu hình SecurityFilterChain minh họa

Ví dụ sau dựa trên API SAS **1.5.x**. Nó tập trung vào bật OIDC và mở extension point cho metadata, chưa phải dự án chạy độc lập:

~~~java
@Bean
@Order(Ordered.HIGHEST_PRECEDENCE)
SecurityFilterChain authorizationServerSecurityFilterChain(HttpSecurity http)
        throws Exception {

    OAuth2AuthorizationServerConfigurer authorizationServer =
            OAuth2AuthorizationServerConfigurer.authorizationServer();

    http
        .securityMatcher(authorizationServer.getEndpointsMatcher())
        .with(authorizationServer, as -> as
            .oidc(oidc -> oidc
                .providerConfigurationEndpoint(endpoint -> endpoint
                    .providerConfigurationCustomizer(metadata ->
                        metadata.claim(
                            "service_documentation",
                            "https://docs.example.com/oidc"
                        )
                    )
                )
            )
        )
        .authorizeHttpRequests(auth -> auth
            .anyRequest().authenticated()
        )
        .exceptionHandling(exceptions -> exceptions
            .authenticationEntryPoint(
                new LoginUrlAuthenticationEntryPoint("/login")
            )
        );

    return http.build();
}
~~~

`providerConfigurationCustomizer` nhận một `Consumer<OidcProviderConfiguration.Builder>`; ví dụ dùng method kế thừa `claim(String, Object)` để thêm `service_documentation`. Điều này không thay `issuer`, `jwks_uri` hoặc các trường an ninh mặc định. Trong thực tế cần cấu hình thêm user login security chain, RegisteredClientRepository, AuthorizationService, signing keys, token generator và các bean tương ứng.

**Chú ý thứ tự filter:** provider-configuration endpoint do filter của SAS xử lý, không phải controller application thông thường. Metadata là public discovery document; không nên yêu cầu người dùng login hoặc cung cấp client secret để tải metadata. Hãy kiểm thử anonymous GET thực tế, nhất là khi tự thay security chain, reverse proxy hoặc authorization rules.

### 9.3. Khai báo issuer cố định và endpoint settings

~~~java
@Bean
AuthorizationServerSettings authorizationServerSettings() {
    return AuthorizationServerSettings.builder()
            .issuer("https://auth.example.com")
            .authorizationEndpoint("/oauth2/authorize")
            .tokenEndpoint("/oauth2/token")
            .jwkSetEndpoint("/oauth2/jwks")
            .oidcUserInfoEndpoint("/userinfo")
            .oidcLogoutEndpoint("/connect/logout")
            .build();
}
~~~

Trong mô hình một issuer, khai báo issuer rõ ràng giúp `issuer` trong metadata và `iss` trong token ổn định qua các request. Đối với SAS 1.5.x, OP Configuration Endpoint thường xuất hiện tại `/.well-known/openid-configuration` khi OIDC được bật; nó không phải endpoint bạn có thể thay đường dẫn tùy tiện bằng `AuthorizationServerSettings.oidcProviderConfigurationEndpoint(...)` vì API settings này không nằm trong bộ setter endpoint được tài liệu hóa.

`OAuth2AuthorizationServerConfiguration` có thể tự tạo `AuthorizationServerSettings` bean khi dùng default import, nhưng ứng dụng có thể khai báo bean riêng để khóa issuer/đường dẫn theo môi trường.

### 9.4. Cung cấp JWKSource và JwtDecoder

Khi dùng ID Token với chữ ký bất đối xứng, OP cần có signing keys và công bố public keys tại `jwks_uri`. SAS cung cấp helper để dựng `JwtDecoder` từ `JWKSource`:

~~~java
@Bean
JwtDecoder jwtDecoder(JWKSource<SecurityContext> jwkSource) {
    return OAuth2AuthorizationServerConfiguration.jwtDecoder(jwkSource);
}
~~~

`JWKSource<SecurityContext>` phải được đăng ký riêng bằng key material của hệ thống; **không được** tải private key từ metadata hoặc đưa private key vào response JWKS. Tài liệu SAS xác nhận `JwtDecoder` bean cần thiết cho UserInfo và Client Registration Endpoint của OIDC. Một ID Token signing key cũng phải có lifecycle, rotation và key IDs ổn định.

### 9.5. Không công bố endpoint chưa được bật

Theo cấu hình SAS 1.5.x:
- OAuth Authorization Server Metadata và JWK Set là các endpoint khác nhau.
- OIDC Provider Configuration xuất hiện khi bật `oidc(...)`.
- UserInfo/Logout được cấu hình theo OIDC; hành vi cụ thể phụ thuộc bean/policy.
- **OIDC Dynamic Client Registration bị tắt mặc định**; không tự thêm `registration_endpoint` vào metadata chỉ vì Spring có class/configurer.
- Các extension như PAR, DPoP, token exchange, mTLS chỉ được công bố nếu implementation thực sự hỗ trợ theo phiên bản và policy.

Nếu thay builder để đưa `id_token_signing_alg_values_supported` hoặc `response_types_supported` vào metadata, phải bảo đảm chúng phản ánh loại ID Token/flow server thực sự tạo được. Không thêm `HS256`, `none`, implicit/hybrid grant hoặc một endpoint ảo để “đáp ứng danh sách”.

### 9.6. Spring Security 7.x dùng cấu hình thế hệ tích hợp

Trong nhánh Spring Security **7.x**, hạ tầng Authorization Server có API trực tiếp trên `HttpSecurity`, ví dụ:

~~~java
http.oauth2AuthorizationServer(as -> as
        .oidc(Customizer.withDefaults())
);
~~~

Cấu hình này chỉ minh họa **cách bật OIDC** ở thế hệ tích hợp. Nó không thay thế security chains, issuer, client registration, JWK source hay login setup. Không trộn trực tiếp DSL Spring Security 7.x với class/package hoặc `http.with(...)` dành cho ví dụ SAS 1.x; cần dựa vào dependency thực tế.

## 10. Ứng dụng Spring Boot làm OIDC Relying Party

### 10.1. Cấu hình RP bằng issuer-uri

Một ứng dụng Spring Boot dùng OAuth2 Login có thể cấu hình OIDC provider theo issuer:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          portal:
            provider: corporate
            client-id: portal-web
            client-secret: ${OIDC_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope: [openid, profile, email]
        provider:
          corporate:
            issuer-uri: https://auth.example.com
~~~

Giá trị `issuer-uri` cho RP biết issuer để truy vấn OpenID Provider Configuration. RP không cần khai báo riêng `authorization-uri`, `token-uri`, `jwk-set-uri` và `user-info-uri` nếu provider metadata hợp lệ và đã đầy đủ các endpoint cần dùng.

`OIDC_CLIENT_SECRET` phải lấy từ secret manager/environment phù hợp; mẫu này dành cho confidential web application. Public clients không được nhúng client secret cố định trong SPA hoặc native app.

Một cách lập trình tương đương là `ClientRegistrations.fromOidcIssuerLocation(issuer)` trong phiên bản Spring Security hỗ trợ; API `fromIssuerLocation` có thể thử nhiều discovery endpoint theo logic tương thích. Dùng lựa chọn đúng mục đích và không dựa vào thứ tự thử endpoint như hợp đồng bảo mật duy nhất.

### 10.2. RP không được bỏ validation sau Discovery

Sau khi login thành công:
- Kiểm tra `iss` bằng issuer đã tin cậy.
- Kiểm tra chữ ký ID Token bằng public key phù hợp từ JWKS.
- Kiểm tra `aud` chứa client ID đã đăng ký và `azp` khi cần.
- Kiểm tra `exp`, `iat`, `nonce` và các claims liên quan.
- Kiểm tra `state` của OAuth authorization response để ngăn CSRF/login injection.
- Chỉ dùng thông tin `sub` trong phạm vi issuer; `sub` không phải định danh toàn cầu độc lập với issuer.

Nếu metadata bị tráo để trỏ `jwks_uri` tới khóa của attacker và RP chấp nhận sai issuer, attacker có thể tạo ID Token giả. Đó là lý do mối quan hệ issuer–metadata–JWKS không được nới lỏng.

### 10.3. Ứng dụng Spring Boot làm Resource Server

Resource Server quan tâm đến **access token**, không dùng ID Token để phân quyền API. Với JWT access token, Spring Boot có thể cấu hình:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://auth.example.com
          audiences: [orders-api]
~~~

Theo khả năng Spring Boot/Security của version đang chạy, `issuer-uri` có thể giúp Resource Server phát hiện JWKS URL qua provider-configuration/OAuth metadata và bật kiểm tra `iss`. `audiences` giúp xác định API là đối tượng nhận token. Nếu dùng cách cấu hình trực tiếp `jwk-set-uri`, vẫn cần kiểm tra issuer và audience; biết khóa ký không làm token hợp lệ cho mọi API.

Một số version thực hiện discovery khi khởi tạo decoder, một số trì hoãn tới request đầu tiên. Không tự kết luận mọi bản Spring Security sẽ luôn gọi metadata ngay ở application startup. Thiết lập readiness/timeout/cache và kiểm thử theo version/deployment thực tế.

## 11. Multi-tenant issuer và reverse proxy

### 11.1. Không suy issuer từ Host chưa được xác minh

Khi Spring Authorization Server đứng sau reverse proxy, incoming request có thể chứa các header như `Forwarded` hoặc `X-Forwarded-Host`. Nếu issuer được suy từ Host chưa được trust boundary xác minh, attacker có thể làm metadata trả issuer do hắn kiểm soát, gây sai URL hoặc token mix-up.

Đối với hệ thống một tenant, ưu tiên:

~~~java
AuthorizationServerSettings.builder()
        .issuer("https://auth.example.com")
        .build();
~~~

Ngoài ra:
- Cấu hình proxy set/overwrite forwarded headers thay vì giữ giá trị do internet client gửi.
- Chỉ trust proxy IP/service identity đã biết.
- Đảm bảo external scheme là HTTPS, đúng domain/cổng/path public.
- Kiểm thử metadata khi đi qua proxy public, không chỉ gọi localhost backend.
- Xem xét HSTS, TLS certificate, load balancer và redirect behavior.

### 11.2. Multi-issuer hosting trong SAS 1.5.x

SAS hỗ trợ cấu hình nhiều issuer trên cùng host từ dòng 1.3, dùng `multipleIssuersAllowed(true)`:

~~~java
@Bean
AuthorizationServerSettings multiTenantSettings() {
    return AuthorizationServerSettings.builder()
            .multipleIssuersAllowed(true)
            .build();
}
~~~

Trong chế độ multi-issuer, **không đồng thời khóa một issuer cố định** bằng `issuer(...)`; tài liệu builder nêu rằng issuer cố định buộc deployment về single tenant. Ứng dụng vẫn phải tự thiết kế tenant routing, registry và mapping chính sách; bật flag không tự tạo tenant isolation.

Ví dụ:

| Tenant | Issuer | OIDC Discovery URL |
| --- | --- | --- |
| Alpha | `https://auth.example.com/t/alpha` | `https://auth.example.com/t/alpha/.well-known/openid-configuration` |
| Beta | `https://auth.example.com/t/beta` | `https://auth.example.com/t/beta/.well-known/openid-configuration` |

Hợp đồng an toàn cho từng tenant:
- `issuer` trong metadata khớp chính xác issuer tenant.
- `iss` của ID Token chỉ tenant đó.
- Client registration, subject identifiers và authorization không lẫn tenant.
- `jwks_uri` trả keys đúng trust boundary; nếu dùng keys chung, vẫn phải enforce issuer và tenant mapping.
- RP không accept ID Token tenant Beta cho cấu hình Alpha chỉ vì cùng signing key hoặc cùng host.

### 11.3. CORS và discovery endpoint

OIDC Discovery khuyến nghị Provider Configuration endpoint có cơ chế CORS hoặc tương đương cho browser-based clients khi phù hợp. Điều này không đồng nghĩa Authorization Endpoint cần CORS; Authorization Endpoint thường được truy cập qua browser redirect và đặc tả **không khuyến nghị CORS** tại endpoint này.

Không mở `Access-Control-Allow-Origin: *` trên toàn bộ token/UserInfo/client registration endpoints chỉ để “fix discovery”. Cần cấu hình CORS theo từng endpoint, client origin và phương thức hợp lệ; metadata public không có nghĩa mọi API phía sau đều public.

## 12. Bảo mật khi tiêu thụ OpenID Provider Configuration

### 12.1. Discovery document là dữ liệu từ mạng, không phải nguồn tin cậy vô điều kiện

RP không nên lấy URL `issuer`, `authorization_endpoint` hay `jwks_uri` từ một trang không tin cậy rồi sử dụng ngay. Cần xác định issuer bằng cấu hình hoặc quy trình đăng ký provider được kiểm soát. Nếu hỗ trợ dynamic issuer discovery từ đầu vào người dùng, hãy giới hạn host/scheme/port, tránh local-network destinations và kiểm soát redirect.

Các nguy cơ điển hình:

| Nguy cơ | Kịch bản | Biện pháp |
| --- | --- | --- |
| **Issuer impersonation** | JSON metadata của attacker tự xưng issuer của OP khác | TLS validation, issuer metadata phải khớp tuyệt đối issuer kỳ vọng |
| **SSRF** | RP tải discovery/JWKS URL trỏ tới localhost hoặc cloud metadata IP | Allowlist/egress policy, chặn private/link-local IP, DNS rebinding và redirects nguy hiểm |
| **Key substitution** | Metadata trỏ `jwks_uri` tới khóa của attacker | Chỉ chấp nhận metadata sau issuer/TLS validation và policy tin cậy |
| **Algorithm confusion** | Token có `alg` không đúng allowlist nhưng RP vẫn xác minh | Cố định allowed algorithms; không tin `alg` từ token như nguồn policy |
| **Cross-tenant mix-up** | RP dùng metadata/key của issuer B để xác minh token issuer A | Khóa cache và validation theo issuer, không chỉ theo hostname |
| **Stale metadata** | OP đổi endpoint hoặc signing keys nhưng RP dùng cache cũ | Cache có TTL/refresh phù hợp; hỗ trợ key rotation |
| **Oversharing** | Metadata công bố host nội bộ, endpoint admin, registration endpoint không bảo vệ | Chỉ công bố endpoint public và feature thực sự hỗ trợ |
| **Downgrade/fallback** | Discovery lỗi rồi RP bỏ qua `iss` hoặc dùng HTTP | Fail closed; không hạ chuẩn để “cho login chạy được” |

Không dùng chế độ bỏ qua TLS hostname verification trong production. Lựa chọn “trust all certificates” có thể biến mọi kiểm tra issuer phía sau thành vô nghĩa.

### 12.2. Quy trình xác minh metadata đề xuất

~~~mermaid
flowchart TD
    A[Issuer từ cấu hình tin cậy] --> B[Dựng URL OIDC well-known]
    B --> C[HTTPS GET và xác thực TLS]
    C --> D{HTTP 200, JSON hợp lệ?}
    D -->|Không| X[Từ chối metadata]
    D -->|Có| E{metadata.issuer == issuer kỳ vọng?}
    E -->|Không| X
    E -->|Có| F[Kiểm tra required metadata và URL policy]
    F --> G[Khởi tạo client endpoints]
    G --> H[Đọc JWKS qua kết nối tin cậy]
    H --> I[Nhận và xác minh ID Token]
    I --> J{iss, aud, exp, nonce và chữ ký hợp lệ?}
    J -->|Không| Y[Từ chối đăng nhập]
    J -->|Có| K[Tạo session theo policy RP]
~~~

Sơ đồ là một **security contract**. Cách API Spring gọi Discovery/JWKS có thể có cache hoặc lazy initialization, nhưng các kiểm tra không được biến mất.

### 12.3. Caching và key rotation

OP có thể thay đổi signing key vì rotation hoặc sự cố bảo mật. RP không nên tải JWKS ở mọi HTTP request nếu không cần, nhưng cũng không được cache vô hạn.

Một phương án vận hành:
- Cấu hình TTL/HTTP caching cho metadata theo khả năng thư viện.
- Dùng cache JWKS có refresh và xử lý key ID mới an toàn.
- Giữ public key cũ trong JWKS đủ lâu cho những ID Token còn hạn nếu key rotation thông thường.
- Không tiếp tục tin key bị compromise chỉ để giữ tương thích.
- Không tự lấy khóa từ `jku`/`x5u` do JWT bất kỳ khai báo khi không được profile/trust policy cho phép.
- Theo dõi 404/5xx của discovery/JWKS, mismatch issuer, unknown kid và ID Token signature failure.

Public JWKS không có private key, nhưng mất availability của nó vẫn ảnh hưởng login và xác minh token.

## 13. Ma trận kiểm thử hợp đồng Discovery

### 13.1. Kiểm thử endpoint và metadata

| Test | Hành động | Kỳ vọng |
| --- | --- | --- |
| OP config public | Anonymous GET `/.well-known/openid-configuration` | HTTP 200, `application/json` |
| Required metadata | Đọc response JSON | Đủ trường bắt buộc theo profile triển khai |
| Issuer exact match | So config `issuer` với issuer kỳ vọng | Trùng chính xác |
| ID Token issuer | Login lấy ID Token | Claim `iss` bằng metadata `issuer` |
| Authorization URL | So URL metadata với endpoint đang phục vụ | Trùng, HTTPS và truy cập được |
| Token URL | Gửi token request hợp lệ | Endpoint hoạt động theo grant cho phép |
| JWKS URL | GET `jwks_uri` | 200 JSON với mảng `keys`, không có private key |
| Key validation | Dùng ID Token ký bởi key đã công bố | Chữ ký và claims được xác minh |
| Unsupported response type | Request type không trong metadata | Server không chấp nhận |
| UserInfo metadata | Nếu quảng cáo `userinfo_endpoint` | Endpoint thực sự tồn tại và yêu cầu token phù hợp |
| Dynamic Registration metadata | Nếu `registration_endpoint` vắng | Không suy server cho phép đăng ký client tùy ý |
| Extension metadata | PAR/logout/other advertised endpoint | Thực thi đúng feature/policy |
| OAuth metadata riêng | GET `/.well-known/oauth-authorization-server` | Đúng contract RFC 8414 |
| Anonymous access | Không gửi cookie/session/client secret | Discovery vẫn có thể truy cập |
| HTTP query handling | GET kèm query không liên quan | Không làm biến đổi issuer hoặc trỏ sang tenant khác |
| Empty arrays | Field dạng array rỗng | Không xuất trong metadata theo OIDC Discovery response |

### 13.2. Kiểm thử bảo mật

| Test | Input hoặc môi trường | Kỳ vọng |
| --- | --- | --- |
| Issuer mismatch | Metadata `issuer` là attacker/tenant khác | RP từ chối |
| ID Token iss mismatch | ID Token của issuer B, metadata issuer A | RP từ chối |
| Wrong audience | ID Token `aud` không chứa client ID | RP từ chối |
| Unknown signing kid | `kid` không tương ứng key hợp lệ | Không chấp nhận token |
| Alg downgrade | Header `alg=none` hoặc alg ngoài allowlist | Từ chối |
| Bad TLS certificate | HTTPS endpoint có certificate sai domain/expired | Không dùng metadata |
| Insecure scheme | Endpoint metadata trả URL HTTP | Từ chối theo HTTPS policy |
| SSRF via WebFinger | `href` trỏ 127.0.0.1 hoặc IP riêng | Không fetch địa chỉ nguy hiểm |
| SSRF via JWKS | `jwks_uri` trỏ link-local/cloud metadata | Không fetch |
| Host header injection | Request tới OP với Host giả | Issuer public không đổi |
| Forwarded host injection | Reverse proxy cho phép `X-Forwarded-Host` giả | Proxy sanitize; issuer không bị đầu độc |
| Cross-tenant configuration | RP trỏ tenant A nhưng nhận B | Không đăng nhập nhầm tenant |
| JWKS rotation | Server thêm key mới, vẫn giữ key cũ đúng policy | RP xác minh token cũ/mới phù hợp |
| Compromised key | Thu hồi key khẩn cấp | RP hết tin key theo chính sách bảo mật |
| Discovery downtime | OP trả 503 | RP fail closed, retry/backoff có giới hạn |
| Metadata oversize | Server trả JSON quá lớn/nhiều URL lạ | RP giới hạn size, timeout và schema |
| Claim mismatch | `claims_supported` công bố email nhưng user không có | Client không coi email là claim bắt buộc |
| Key material leak | Đọc response JWKS | Không có private/symmetric keys |

### 13.3. Kiểm thử với MockMvc

Trong project đã cấu hình SAS và có `MockMvc`, test minh họa:

~~~java
@Test
void oidcDiscoveryPublishesExpectedIssuer() throws Exception {
    mockMvc.perform(get("/.well-known/openid-configuration"))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(
                    MediaType.APPLICATION_JSON))
            .andExpect(jsonPath("$.issuer")
                    .value("https://auth.example.com"))
            .andExpect(jsonPath("$.authorization_endpoint").exists())
            .andExpect(jsonPath("$.token_endpoint").exists())
            .andExpect(jsonPath("$.jwks_uri").exists())
            .andExpect(jsonPath("$.subject_types_supported").isArray())
            .andExpect(jsonPath("$.id_token_signing_alg_values_supported")
                    .isArray());
}
~~~

Code tập trung vào assertions, cần `@SpringBootTest`/`@AutoConfigureMockMvc`, imports JUnit/MockMvc và đầy đủ bean SAS trong dự án thật. Test `jwks_uri` nên chạy thêm qua HTTPS deployment/proxy thật, vì MockMvc không phát hiện lỗi cấu hình external host hoặc TLS tại edge.

### 13.4. Kiểm thử issuer có path

Với issuer `https://auth.example.com/tenant-a`:

~~~text
Expected OIDC:
https://auth.example.com/tenant-a/.well-known/openid-configuration

Expected metadata.issuer:
https://auth.example.com/tenant-a

Expected ID Token iss:
https://auth.example.com/tenant-a
~~~

Đồng thời kiểm tra:
- Không chấp nhận `https://auth.example.com/tenant-b`.
- Không lấy nhầm JWKS/authorization context của tenant khác.
- Metadata tenant A không được cache rồi phục vụ cho tenant B.
- Khi reverse proxy route lại path, request từ browser vẫn dùng HTTPS issuer public chính xác.

## 14. Những lỗi thường gặp và cách xử lý

**Lỗi 1 — nhầm OP Configuration với OAuth Metadata.** Chỉ gọi `/.well-known/oauth-authorization-server` rồi kỳ vọng `subject_types_supported` hoặc `id_token_signing_alg_values_supported`. Hai chuẩn khác nhau, cần bật OIDC để có OP Configuration.

**Lỗi 2 — OIDC endpoint trả 404 dù OAuth2 token endpoint hoạt động.** Trong SAS 1.5.x, OIDC tắt mặc định. Khởi tạo `OidcConfigurer` và xác minh SecurityFilterChain matcher/issuer.

**Lỗi 3 — issuer internal host sau reverse proxy.** Metadata ghi `http://localhost:9000` hoặc `http://service:8080`, trong khi RP dùng `https://auth.example.com`. Cố định issuer public và cấu hình trusted proxy đúng.

**Lỗi 4 — metadata issuer khác ID Token iss.** RP phải từ chối; sửa logic issuer tại AS, không bỏ kiểm tra phía RP.

**Lỗi 5 — lấy URL bằng cách nối thủ công.** Đoán `/oauth2/token` hoặc `/oauth2/jwks` từ issuer thay vì dùng metadata. Khi OP đổi endpoint hoặc triển khai multi-tenant sẽ lỗi.

**Lỗi 6 — bắt buộc client login mới được GET metadata.** Discovery endpoint phải có khả năng truy cập công khai qua TLS; kiểm tra filter và gateway rule.

**Lỗi 7 — mở dynamic client registration không chủ ý.** `registration_endpoint` là capability đặc biệt; đừng công bố hoặc mở quyền nếu hệ thống không dùng feature này.

**Lỗi 8 — công bố response type/algorithm chưa hỗ trợ.** RP gửi `response_type` server từ chối, hoặc ID Token ký algorithm RP không biết. Metadata phải phản ánh runtime.

**Lỗi 9 — đồng nhất ID Token và access token.** ID Token chứng minh xác thực cho RP; API phải dùng access token với audience/scope thích hợp. `id_token_signing_alg_values_supported` không định nghĩa access token policy.

**Lỗi 10 — hiểu `request_uri_parameter_supported` là PAR.** Cần kiểm tra riêng `pushed_authorization_request_endpoint` theo RFC 9126.

**Lỗi 11 — SSRF qua WebFinger hoặc JWKS.** Không fetch endpoint tùy ý do người dùng/attacker cung cấp; áp URL/egress allowlist và issuer validation.

**Lỗi 12 — tắt kiểm tra TLS khi cần chạy qua môi trường test.** Sửa certificate/CA/trust store đúng; không đưa tùy chọn ignore SSL verification vào production.

## 15. Bài tập tình huống

Một tổ chức triển khai Authorization Server Spring Boot sau NGINX:

~~~text
Public issuer:
https://login.example.com/identity

Internal service:
http://authorization-server:9000

OIDC RP:
https://portal.example.com

Multi-tenant:
alpha và beta dùng riêng issuer path
~~~

Đội backend gặp các sự cố:
- `GET /identity/.well-known/openid-configuration` trả JSON có `issuer=http://authorization-server:9000`.
- RP đặt `issuer-uri=https://login.example.com/identity`, nhưng từ chối metadata.
- `jwks_uri` công bố `http://authorization-server:9000/oauth2/jwks`.
- Một developer đề xuất bỏ kiểm tra issuer và SSL để login “chạy trước”.
- `registration_endpoint` được quảng cáo dù dynamic registration chưa được bật.
- Tenant alpha nhận được ID Token có `iss` của tenant beta.

Hãy phân tích:

1. Vì sao RP phải từ chối metadata hiện tại? Điều kiện `issuer` nào đang bị vi phạm?
2. URL OIDC well-known đúng cho issuer có path là gì? Nó khác đường dẫn RFC 8414 ra sao?
3. Nên sửa external issuer và trusted proxy headers thế nào?
4. `jwks_uri` nên công bố URL nào và vì sao không dùng host internal?
5. Vì sao không được bỏ TLS/issuer validation?
6. Phải xử lý `registration_endpoint` chưa bật ra sao?
7. Làm gì để khóa client registration và ID Token theo tenant?
8. Viết ít nhất sáu test bảo đảm anonymous discovery, issuer matching, JWKS availability, key rotation, tenant isolation và endpoint capabilities.

**Gợi ý:** phải công bố issuer HTTPS public nhất quán từ metadata đến ID Token, route well-known theo path OIDC, dùng endpoint public cho JWKS, không bỏ TLS/issuer check. Với multi-tenant, bật cơ chế issuer-path có kiểm soát trong SAS và kiểm tra tenant ở mọi lớp; không dựa vào việc cùng host hoặc cùng signing key để trộn định danh.

## 16. Checklist triển khai production

1. **Issuer:** chốt HTTPS issuer ổn định, không có query/fragment; không lấy từ Host chưa tin cậy.
2. **Discovery path:** phục vụ chính xác `/.well-known/openid-configuration` theo issuer, kể cả path/multi-tenant.
3. **OIDC enablement:** bật `OidcConfigurer`, không nhầm với OAuth metadata mặc định của SAS.
4. **Required claims:** đủ issuer, authorization endpoint, token endpoint khi cần, JWKS, response types, subject types, ID Token signing algorithms.
5. **Capabilities:** chỉ công bố scopes, grants, authentication methods, extensions và endpoints đang hoạt động.
6. **JWKS:** public-only JWK Set, có `kid`/rotation và chiến lược cache/reload đúng.
7. **Security:** RP/Resource Server xác minh TLS, issuer, key, signature, audience, expiry, nonce và state theo profile.
8. **Network:** giới hạn SSRF khi dùng WebFinger hoặc dynamic issuer; kiểm soát outbound redirects/DNS.
9. **Proxy:** bảo đảm metadata luôn dùng external HTTPS host/scheme/path; chỉ trust proxy headers từ proxy được định danh.
10. **Multi-tenant:** issuer, client registrations, cache, tokens và keys được cách ly theo tenant.
11. **Availability:** metadata/JWKS endpoint có monitoring, timeout, cache policy và kế hoạch sự cố.
12. **Spring version:** đối chiếu SAS 1.x hay Spring Security 7.x trước khi dùng DSL/configurer.
13. **Contract tests:** chạy MockMvc và end-to-end qua ingress, bao gồm negative tests về mismatch và endpoint 404.
14. **Change control:** khi thay issuer/domain là thay đổi breaking, cần kế hoạch migration của RP, token validator và sessions.

## 17. Tài liệu chuẩn và Spring cần đối chiếu

- [OpenID Connect Discovery 1.0 — Final, incorporating errata set 2](https://openid.net/specs/openid-connect-discovery-1_0.html): WebFinger Issuer Discovery, metadata bắt buộc, well-known path và issuer validation.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): OIDC authentication flows, ID Token, nonce và UserInfo.
- [RFC 8414 — OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414.html): OAuth metadata và well-known path khác OIDC.
- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517.html): public key structure.
- [RFC 7518 — JSON Web Algorithms (JWA)](https://www.rfc-editor.org/rfc/rfc7518.html): thuật toán ký/xác minh JWT.
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519.html): claims và kiểm tra `iss`, `aud`, `exp`.
- [RFC 9126 — OAuth 2.0 Pushed Authorization Requests](https://www.rfc-editor.org/rfc/rfc9126.html): metadata PAR và `request_uri`.
- [Spring Authorization Server 1.5.x — Configuration Model](https://docs.spring.io/spring-authorization-server/reference/configuration-model.html): cách bật OIDC, endpoint mặc định, `JWKSource`, `AuthorizationServerSettings`.
- [Spring Authorization Server 1.5.x — Protocol Endpoints](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html): `OidcProviderConfigurationEndpointConfigurer` và `providerConfigurationCustomizer`.
- [Spring Authorization Server — OidcProviderConfiguration.Builder](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/oidc/OidcProviderConfiguration.Builder.html): required fields và builder API.
- [Spring Security 7.x — Authorization Server Configuration Model](https://docs.spring.io/spring-security/reference/servlet/oauth2/authorization-server/configuration-model.html): DSL thế hệ tích hợp.
- [Spring Boot — OAuth2/OIDC Client](https://docs.spring.io/spring-boot/reference/security/oauth2.html): RP với `issuer-uri`.
- [Spring Security — OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): JWT issuer/JWKS discovery và validation.

**Ghi nhớ:** OpenID Provider Configuration là **JSON metadata công khai** giúp RP khám phá endpoint, khả năng OIDC và vị trí public keys của OP. OpenID Connect Discovery có thể bắt đầu bằng WebFinger để tìm issuer, nhưng bước này không bắt buộc khi RP đã biết issuer. Metadata được lấy qua HTTPS tại `<issuer>/.well-known/openid-configuration`, phải có issuer khớp **chính xác** với issuer kỳ vọng và claim `iss` của ID Token. Trong Spring Authorization Server, OAuth metadata có sẵn theo cấu hình mặc định, nhưng muốn có **OIDC Provider Configuration** phải bật OIDC; đồng thời phải công bố đúng endpoint, signing keys và tính năng thực sự hỗ trợ.
