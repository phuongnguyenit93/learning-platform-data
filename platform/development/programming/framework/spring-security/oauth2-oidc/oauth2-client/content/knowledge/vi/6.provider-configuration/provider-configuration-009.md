# 6.9. Giới hạn và khác biệt metadata giữa các nhà cung cấp

## 1. Vì sao cùng là OAuth 2.0/OIDC nhưng mỗi provider lại có cách cấu hình khác nhau?

Một ứng dụng **Spring Security OAuth 2.0/OIDC Client** có thể cho người dùng đăng nhập bằng nhiều nhà cung cấp: hệ thống SSO nội bộ, một OpenID Provider công khai hoặc một nền tảng chỉ hỗ trợ OAuth 2.0. Chúng có thể cùng sử dụng Authorization Code Grant nhưng vẫn khác nhau ở địa chỉ endpoint, cách xác thực client, scope, claim trả về, chính sách token, cơ chế đăng xuất và phần mở rộng riêng.

Giả sử Spring Boot ứng dụng tại `https://app.example.com` muốn tích hợp hai nguồn danh tính:

- **Provider A:** hỗ trợ OIDC Discovery, công bố issuer, endpoint, JWK Set và metadata liên quan.
- **Provider B:** hỗ trợ OAuth 2.0 Authorization Code Grant, nhưng không cung cấp OIDC Discovery; client phải khai báo các endpoint và quy tắc đọc thông tin người dùng.

Nếu chỉ sao chép cấu hình provider A sang provider B, ứng dụng dễ gặp lỗi ngay khi khởi động, khi chuyển hướng đăng nhập, lúc đổi authorization code hoặc khi ánh xạ người dùng.

Bài học này giải thích cách **đọc, đánh giá giới hạn và xử lý khác biệt metadata giữa các provider**, sau đó cấu hình tương ứng trong Spring Security. Trọng tâm là **metadata của OAuth2/OIDC provider**, không phải metadata của tài khoản người dùng.

### Kết quả cần hiểu

Sau bài này, người học có thể:

1. Phân biệt metadata công bố bởi **OpenID Connect Discovery** và metadata theo **OAuth 2.0 Authorization Server Metadata**.
2. Nhận biết trường nào mô tả **khả năng server**, trường nào là **cấu hình client đã được cấp** và trường nào chỉ xuất hiện khi thực sự đăng nhập.
3. Đọc những metadata phổ biến như `issuer`, `authorization_endpoint`, `token_endpoint`, `jwks_uri`, `userinfo_endpoint`, `scopes_supported` và `token_endpoint_auth_methods_supported`.
4. Hiểu các giới hạn: metadata có thể thiếu trường tùy chọn, không phản ánh hết chính sách theo tenant/client, hoặc chỉ mô tả một phần mở rộng.
5. Cấu hình `spring.security.oauth2.client.provider.*` thủ công khi không thể dùng discovery đầy đủ.
6. Kiểm tra luồng đăng nhập thực tế và thiết kế lớp tương thích phù hợp cho nhiều provider.

Các URL `example.com`, issuer, client ID và claim trong bài đều là **ví dụ minh họa**, không đại diện cho cấu hình thực của một nhà cung cấp cụ thể.

## 2. Metadata trong OAuth2/OIDC nghĩa là gì?

**Provider metadata** là tập thông tin về Authorization Server/OpenID Provider mà client cần để thực hiện giao thức hoặc xác định những tính năng server hỗ trợ.

Ví dụ một OIDC Provider có thể công bố:

~~~json
{
  "issuer": "https://id.example.com",
  "authorization_endpoint": "https://id.example.com/oauth2/authorize",
  "token_endpoint": "https://id.example.com/oauth2/token",
  "jwks_uri": "https://id.example.com/keys",
  "userinfo_endpoint": "https://id.example.com/oidc/userinfo",
  "response_types_supported": ["code"],
  "subject_types_supported": ["public", "pairwise"],
  "id_token_signing_alg_values_supported": ["RS256"],
  "scopes_supported": ["openid", "profile", "email"],
  "token_endpoint_auth_methods_supported": [
    "client_secret_basic",
    "private_key_jwt"
  ],
  "code_challenge_methods_supported": ["S256"]
}
~~~

Thông tin có thể chia thành các nhóm:

| Nhóm | Trường tiêu biểu | Câu hỏi metadata trả lời |
|---|---|---|
| Định danh server | `issuer` | Provider nào công bố và phát hành token? |
| Endpoint giao thức | `authorization_endpoint`, `token_endpoint` | Client gửi yêu cầu authorize và token tới đâu? |
| Khóa và xác minh | `jwks_uri`, `id_token_signing_alg_values_supported` | Lấy khóa công khai ở đâu, thuật toán nào được hỗ trợ? |
| UserInfo | `userinfo_endpoint` | Có điểm lấy thông tin người dùng theo OIDC không? |
| Grant/response | `grant_types_supported`, `response_types_supported` | Server hỗ trợ các loại grant và response nào? |
| Client authentication | `token_endpoint_auth_methods_supported` | Token endpoint công bố những cách xác thực client nào? |
| Scopes/claims | `scopes_supported`, `claims_supported` | Những scope/claim nào được quảng bá? |
| Hỗ trợ mở rộng | `code_challenge_methods_supported`, `pushed_authorization_request_endpoint` | Có công bố hỗ trợ PKCE/PAR hoặc tính năng mở rộng khác không? |
| Đăng xuất/quản lý token | `end_session_endpoint`, `revocation_endpoint`, `introspection_endpoint` | Có endpoint hoặc khả năng tùy chọn liên quan hay không? |

**Metadata không phải là token** và không chứa quyền truy cập đã cấp cho một người dùng cụ thể. `scopes_supported` mô tả khả năng tổng quát của server; scope thực sự được cấp phải đọc từ kết quả authorization/token response hoặc thông tin access token theo hợp đồng API.

## 3. Ba nguồn thông tin không nên trộn lẫn

Để tích hợp ổn định, cần phân biệt ba tầng dữ liệu.

| Nguồn | Ví dụ | Mức độ ý nghĩa |
|---|---|---|
| **Metadata do server công bố** | `authorization_endpoint`, `jwks_uri`, `grant_types_supported` | Khả năng/địa chỉ giao thức chung của issuer hoặc authorization server. |
| **Đăng ký client và chính sách áp dụng** | `client_id`, secret, callback allowlist, scopes đã duyệt, client authentication method | Những gì một client cụ thể được phép dùng; thường nhận từ bảng quản trị/API đăng ký. |
| **Phản hồi của một phiên giao dịch** | `code`, `state`, token response, `scope` đã cấp, claims trong ID Token | Kết quả thực tế cho một yêu cầu, người dùng, thời điểm và chính sách hiện hành. |

Ví dụ metadata nói:

~~~json
{
  "scopes_supported": ["openid", "profile", "email", "offline_access"]
}
~~~

Điều đó **không bảo đảm** client `portal-web` được phép yêu cầu cả bốn scope. Nhà cung cấp có thể yêu cầu duyệt riêng `offline_access`, không phát refresh token cho mọi ứng dụng, hoặc giới hạn theo tenant.

Tương tự, nếu metadata có:

~~~json
{
  "token_endpoint_auth_methods_supported": [
    "client_secret_basic",
    "client_secret_post",
    "private_key_jwt"
  ]
}
~~~

thì client **chỉ sử dụng phương thức đã được đăng ký và cấu hình**. Không tự chuyển từ `client_secret_basic` sang `private_key_jwt` chỉ vì metadata liệt kê cả hai.

Hãy dùng metadata để **khám phá và kiểm tra khả năng**, đăng ký client để **chọn cấu hình hợp lệ**, phản hồi thực tế để **xác nhận kết quả**.

## 4. OIDC Discovery: nguồn metadata thường gặp với OpenID Provider

### 4.1. OIDC Discovery cung cấp những gì?

**OpenID Connect Discovery** cho phép client lấy cấu hình của OpenID Provider từ issuer đã biết. Với issuer đơn giản:

~~~text
https://id.example.com
~~~

một địa chỉ khám phá phổ biến là:

~~~http
GET /.well-known/openid-configuration HTTP/1.1
Host: id.example.com
Accept: application/json
~~~

Phản hồi thành công là một JSON metadata document. OIDC Discovery đặt ra các trường bắt buộc theo chuẩn, trong đó có `issuer`, `authorization_endpoint`, `token_endpoint`, `jwks_uri`, `response_types_supported`, `subject_types_supported` và `id_token_signing_alg_values_supported`. Nhiều trường khác là tùy chọn hoặc chỉ áp dụng khi provider hỗ trợ một tính năng.

**Issuer là danh tính chính xác của provider.** Metadata nhận được phải công bố một `issuer` khớp với issuer mà client dự kiến tin cậy. Nếu ứng dụng cấu hình `https://id.example.com/tenant-a` nhưng tài liệu trả `issuer = https://id.example.com/tenant-b`, client không được tùy ý coi chúng là cùng một provider vì có chung host.

Các issuer có path thường có quy tắc xây discovery URL theo chuẩn; **không tự đoán đường dẫn bằng cách nối chuỗi** khi triển khai một discovery client. Spring Security có cơ chế hỗ trợ khám phá metadata theo issuer và nên được ưu tiên sử dụng.

### 4.2. Những trường đáng chú ý

| Trường OIDC | Ý nghĩa | Điều cần nhớ |
|---|---|---|
| `issuer` | Định danh OP | Phải khớp issuer mong đợi, không so sánh gần đúng. |
| `authorization_endpoint` | Endpoint nhận authorization request | Dùng cho browser redirect; URL do provider công bố. |
| `token_endpoint` | Endpoint nhận token request | Code exchange diễn ra ở backend với HTTPS. |
| `jwks_uri` | Địa chỉ JWK Set | Khóa ký có thể được luân chuyển; client cần cơ chế lấy khóa mới hợp lệ. |
| `userinfo_endpoint` | Endpoint truy vấn UserInfo | Tùy chọn; không phải mọi OP trả mọi claim trong UserInfo. |
| `response_types_supported` | Các loại response được hỗ trợ | `code` cần có cho Authorization Code Flow. |
| `subject_types_supported` | Kiểu subject identifier | `public`/`pairwise` ảnh hưởng cách `sub` được tạo giữa các client. |
| `id_token_signing_alg_values_supported` | Các thuật toán ký ID Token | Chỉ chấp nhận thuật toán được client cho phép và tương thích. |
| `grant_types_supported` | Các grant server quảng bá | Có thể vắng mặt; không thay thế quyền đã cấp cho client. |
| `scopes_supported` | Danh sách scope công bố | Có thể không liệt kê mọi scope riêng theo tenant/API. |
| `claims_supported` | Các claims có thể được cung cấp | Không bảo đảm mỗi ID Token hay UserInfo response đều có mọi claim. |
| `token_endpoint_auth_methods_supported` | Các cách xác thực client token endpoint | Chọn theo cách client đã đăng ký. |
| `code_challenge_methods_supported` | Các phương thức PKCE được công bố | Trường có thể thiếu dù provider có hỗ trợ; cần kiểm tra hợp đồng và vận hành. |
| `end_session_endpoint` | Endpoint logout OIDC nếu có | Không phải thành phần bắt buộc của mọi nhà cung cấp. |

Nếu một trường bắt buộc theo OIDC Discovery vắng mặt, metadata có thể không tương thích chuẩn hoặc endpoint đang bị cấu hình sai. Nếu **một trường tùy chọn** vắng mặt, không thể kết luận rằng mọi khả năng liên quan đều không tồn tại: chuẩn có thể quy định default, provider có thể dùng phương án khác, hoặc tính năng chỉ được công bố ở tài liệu riêng.

### 4.3. Có metadata không có nghĩa mọi client được dùng cùng tính năng

Một OP có thể cung cấp nhiều loại client: web confidential, SPA public, mobile native hoặc machine-to-machine. Metadata server công bố tập khả năng chung, còn registration của từng client có thể giới hạn:

- `redirect_uri` nào được phép;
- `grant_type` nào được bật;
- có client secret hay phương thức `private_key_jwt`;
- liệu `offline_access` và refresh token được phép hay không;
- client có được dùng `prompt=none` hoặc step-up authentication hay không;
- phạm vi API nào được chấp thuận.

Do đó, client nên dựa vào **cấu hình đã cấp phát** trước, dùng metadata để nhận endpoint/khả năng phù hợp, và dùng phản hồi thực tế để xử lý điều kiện từ chối.

## 5. OAuth 2.0 Authorization Server Metadata khác OIDC Discovery thế nào?

OAuth 2.0 vốn định nghĩa authorization và token flows nhưng **không bắt buộc mọi Authorization Server phải hỗ trợ OIDC**. Một số server hỗ trợ metadata theo **RFC 8414 — OAuth 2.0 Authorization Server Metadata** mà không phát hành ID Token hay cung cấp UserInfo theo OIDC.

### 5.1. Hai loại tài liệu có thể trông giống nhau

Ví dụ metadata kiểu OAuth 2.0:

~~~json
{
  "issuer": "https://auth.example.net",
  "authorization_endpoint": "https://auth.example.net/authorize",
  "token_endpoint": "https://auth.example.net/token",
  "revocation_endpoint": "https://auth.example.net/revoke",
  "grant_types_supported": [
    "authorization_code",
    "client_credentials"
  ],
  "response_types_supported": ["code"],
  "token_endpoint_auth_methods_supported": [
    "client_secret_basic"
  ],
  "code_challenge_methods_supported": ["S256"]
}
~~~

Document này có thể đủ để client tìm authorization/token endpoints cho OAuth2, nhưng **không chứng minh server có OIDC**. Ví dụ không có `userinfo_endpoint`, không có tuyên bố hỗ trợ ID Token và không có metadata OIDC về `subject_types_supported` hoặc `id_token_signing_alg_values_supported`.

Một **Authorization Server hỗ trợ OAuth2** có thể hoàn toàn hợp lệ đối với các tình huống cấp quyền truy cập API nhưng không phù hợp làm OIDC Provider để đăng nhập danh tính theo chuẩn.

### 5.2. So sánh

| Đặc điểm | OIDC Discovery | OAuth2 AS Metadata (RFC 8414) |
|---|---|---|
| Trọng tâm | OpenID Provider và xác thực người dùng | Authorization Server và các khả năng OAuth2 |
| Well-known suffix thường gặp | `openid-configuration` | `oauth-authorization-server` |
| ID Token | Là phần quan trọng trong OIDC | Không mặc nhiên có |
| `userinfo_endpoint` | Trường metadata OIDC tùy chọn | Không phải endpoint OAuth2 chung bắt buộc |
| `jwks_uri` | Quan trọng cho xác minh ID Token dạng JWT | Có thể được công bố tùy cấu hình server/token |
| `subject_types_supported` | Thuộc metadata OIDC | Không phải cam kết chung của OAuth2 |
| `id_token_signing_alg_values_supported` | Thuộc metadata OIDC | Không phải cam kết chung của OAuth2 |
| Áp dụng `scope=openid` | Có ý nghĩa OIDC | Không thể tự giả định được hỗ trợ |
| Claim `sub` trong ID Token | Được xác định bởi OIDC | Không tồn tại ID Token theo OAuth2 thuần |

Với issuer có path, quy tắc đặt đường dẫn well-known của OIDC và RFC 8414 có thể khác nhau. Các thư viện discovery tuân chuẩn giúp tránh lỗi tự nối URL.

Một provider có thể đồng thời xuất bản cả hai dạng metadata. **Đọc đúng document phù hợp với loại đăng nhập client cần**: nếu muốn OIDC Login, phải có khả năng OIDC tương ứng; không chỉ đọc một file OAuth2 metadata rồi mặc định ID Token sẽ xuất hiện.

### 5.3. Có nhà cung cấp không công bố metadata tiêu chuẩn

Một OAuth2 provider có thể đưa endpoint và các quy tắc tích hợp trong tài liệu thủ công, không cung cấp discovery endpoint tiêu chuẩn hoặc chỉ hỗ trợ một phần.

Trường hợp đó có thể cấu hình các URI cần thiết trực tiếp trong Spring Security, ví dụ:

- `authorization-uri`;
- `token-uri`;
- `user-info-uri` nếu login OAuth2 cần gọi API thông tin người dùng;
- `user-name-attribute` để Spring Security xác định principal từ phản hồi user info;
- `jwk-set-uri` và `issuer-uri` khi thực sự tích hợp OIDC theo cách provider hỗ trợ.

Không đưa `issuer-uri` giả vào cấu hình chỉ để Spring Boot “có vẻ đầy đủ” nếu endpoint không hỗ trợ OIDC Discovery theo issuer đó.

## 6. Địa chỉ endpoint có thể khác nhau hoàn toàn

Các ví dụ dưới đây là **mẫu giả định**, không phải URL cố định của bất kỳ hãng nào:

| Chức năng | Provider A | Provider B |
|---|---|---|
| Authorization | `https://id-a.example.com/oauth2/authorize` | `https://login-b.example.net/connect/authorize` |
| Token | `https://id-a.example.com/oauth2/token` | `https://login-b.example.net/connect/token` |
| UserInfo | `https://id-a.example.com/oidc/userinfo` | Không có endpoint chuẩn |
| JWK Set | `https://id-a.example.com/keys` | `https://login-b.example.net/.well-known/jwks.json` |
| Logout | `https://id-a.example.com/connect/endsession` | Không công bố endpoint OIDC |
| Revocation | Có thể có | Có thể không có |

Không có quy tắc chung rằng token endpoint luôn là `/oauth/token` hoặc UserInfo luôn là `/userinfo`. Cũng không nên tự lấy authorization URL rồi thay `authorize` thành `token` để đoán endpoint.

**Điều cần làm:** để metadata hợp lệ cung cấp URL hoặc đọc endpoint từ tài liệu provider khi khai báo thủ công. Với issuer theo tenant, endpoint có thể chứa realm/tenant path, và thay đổi tenant làm thay đổi cả đường dẫn lẫn issuer đáng tin cậy.

### 6.1. URL endpoint tồn tại không đồng nghĩa endpoint cho phép mọi hành vi

Token endpoint có thể từ chối vì:

- client chưa được cấp grant type;
- `client_id` hoặc secret sai;
- client authentication method không khớp;
- authorization code đã hết hạn hoặc dùng lại;
- PKCE verifier không hợp lệ;
- `redirect_uri` không khớp;
- chính sách tenant hoặc phạm vi của người dùng không cho phép.

Một phép kiểm tra HTTP tới endpoint chỉ cho biết URL phản hồi; **không chứng minh luồng OAuth2 client đã được cấp phép và cấu hình đúng**.

## 7. Khác biệt ở client authentication method

Metadata có thể liệt kê các phương thức xác thực client tại token endpoint:

~~~json
{
  "token_endpoint_auth_methods_supported": [
    "client_secret_basic",
    "client_secret_post",
    "private_key_jwt"
  ]
}
~~~

Một số phương thức thường gặp:

| Giá trị | Cách hiểu | Cần chú ý |
|---|---|---|
| `client_secret_basic` | Gửi client ID/secret qua HTTP Basic Authorization | Chỉ dùng qua HTTPS; secret ở backend. |
| `client_secret_post` | Gửi client ID/secret trong body token request | Chỉ dùng khi provider và registration cho phép. |
| `private_key_jwt` | Client tạo và ký assertion bằng khóa riêng | Phải đăng ký khóa, thuật toán và audience/token endpoint đúng. |
| `client_secret_jwt` | Client dùng shared secret để ký assertion | Không tương đương với `client_secret_basic`. |
| `none` | Public client không có client secret có thể được đăng ký theo kiểu này | Cần cơ chế bảo vệ như PKCE; không xem là confidential client. |

Với OAuth2 web application có backend, một cấu hình Spring Boot phổ biến là:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          demo:
            provider: demo-provider
            client-id: ${OIDC_CLIENT_ID}
            client-secret: ${OIDC_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            scope: [openid, profile]
        provider:
          demo-provider:
            issuer-uri: https://id.example.com
~~~

Nếu nhà cung cấp đăng ký client theo `client_secret_post`, cấu hình phương thức cần được đổi phù hợp. Metadata server liệt kê phương thức mà server hỗ trợ **không tự sửa registration do ứng dụng đã được cấp**.

Với `private_key_jwt`, cần thêm các thành phần tạo assertion, quản lý private key và cấu hình theo khả năng framework/provider. Chỉ đổi dòng `client-authentication-method` mà chưa cung cấp khóa ký hoặc cơ chế tạo JWT hợp lệ sẽ không giúp token request thành công.

### 7.1. Sai phương thức thường dẫn đến lỗi nào?

Token endpoint thường trả `invalid_client` hoặc một lỗi xác thực client tương đương. Không nên mặc định nguyên nhân là secret sai: có thể secret đúng nhưng provider đòi client authentication method khác.

Khi khắc phục, kiểm tra:

1. Registration phía provider khai báo phương thức nào.
2. `client-authentication-method` trong Spring Boot có trùng không.
3. Token endpoint nhận header/body/auth assertion theo đúng phương thức không.
4. Có proxy nào xóa Authorization header hoặc biến đổi request không.

Không đưa secret, Basic header hoặc signed client assertion vào log chẩn đoán công khai.

## 8. PKCE: metadata quảng bá khác với chính sách bắt buộc

**Proof Key for Code Exchange (PKCE)** ràng buộc authorization code với verifier mà client tạo khi khởi tạo authorization request. Nhà cung cấp có thể công bố:

~~~json
{
  "code_challenge_methods_supported": ["S256"]
}
~~~

Tuy nhiên có các biến thể:

- Provider yêu cầu PKCE cho public client và khuyến nghị cả confidential client.
- Provider yêu cầu PKCE cho **mọi** Authorization Code Grant.
- Provider hỗ trợ PKCE nhưng metadata không liệt kê trường mở rộng.
- Provider cũ chỉ hỗ trợ một phần hoặc yêu cầu cấu hình client riêng.
- Nhà cung cấp chỉ bật PKCE trong một số application type hoặc tenant.

**Thiếu `code_challenge_methods_supported` không đủ để suy ra PKCE chắc chắn không được hỗ trợ.** Đây là thông tin metadata có thể vắng mặt; cần kiểm tra thông số đăng ký và tài liệu chính thức.

Ưu tiên PKCE `S256`. Trong Authorization Code Flow, client gửi:

~~~text
Authorization request:
  code_challenge=BASE64URL(SHA256(code_verifier))
  code_challenge_method=S256

Token request:
  code_verifier=giá_trị_gốc_đã_lưu
~~~

Nếu provider đã ràng buộc code bằng challenge, token request không gửi đúng verifier sẽ thất bại. Client không được sinh verifier mới ở callback, cũng không được dùng chung verifier cố định cho mọi người dùng.

Khi tùy chỉnh PKCE ở Spring Security, phải lưu `code_verifier` gắn với đúng authorization request để token exchange lấy lại giá trị cũ. Những thay đổi này thuộc phần cấu hình OAuth2 authorization request resolver, **không phải metadata provider tự tạo verifier giúp client**.

## 9. Scope được quảng bá không bảo đảm scope được cấp

Nhiều provider cùng hỗ trợ `openid`, `profile` và `email` nhưng hành vi trả claim vẫn khác nhau. Ngoài ra, scope của API là **theo nhà cung cấp**, ví dụ các tên dạng `read:orders` hoặc `contacts.read` chỉ có ý nghĩa khi provider/API đó định nghĩa.

Ví dụ:

~~~json
{
  "scopes_supported": [
    "openid",
    "profile",
    "email",
    "offline_access"
  ]
}
~~~

Có ít nhất bốn mức cần phân biệt:

1. **Server hỗ trợ** scope trong metadata.
2. **Client đã được duyệt** scope trong registration/quyền quản trị.
3. **Người dùng hoặc chính sách cho phép** scope trong authorization request hiện tại.
4. **Token thực tế được cấp** scope nào sau consent/chính sách.

Không đồng nhất bốn mức này. Có provider chỉ trả một phần scope hoặc yêu cầu một tham số riêng để cho phép lấy refresh token. Một số nhà cung cấp có thể không phát refresh token cho mọi loại client dù client yêu cầu `offline_access`.

### 9.1. Ví dụ scope OIDC và scope API

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          corporate-login:
            scope:
              - openid
              - profile
              - email
          order-api:
            scope:
              - orders.read
              - orders.write
~~~

Hai registration chỉ minh họa cách nhóm scope; chưa phải cấu hình đầy đủ để chạy. `corporate-login` hướng đến OIDC login, trong khi `order-api` có thể phục vụ API theo grant và provider được đăng ký riêng.

Nếu provider không hỗ trợ OIDC nhưng client yêu cầu `openid`, việc thêm scope này vào YAML **không khiến provider tự phát ID Token**. Ngược lại, trong luồng OIDC, access token có thể có các scope API bổ sung, nhưng API vẫn cần audience và chính sách phân quyền tương ứng.

## 10. Khác biệt ở claim, subject và UserInfo

### 10.1. Metadata claims_supported không cam kết mọi claim có mặt

OIDC provider có thể công bố:

~~~json
{
  "claims_supported": [
    "sub", "name", "given_name", "family_name",
    "preferred_username", "email", "email_verified"
  ]
}
~~~

Nhưng phản hồi ID Token hoặc UserInfo chỉ có những claim phù hợp với scope, cấu hình, chính sách bảo mật và dữ liệu người dùng.

Ví dụ:

~~~json
{
  "sub": "user-872",
  "email": "user@example.net",
  "email_verified": false
}
~~~

Không thể suy ra rằng email đã được xác minh chỉ vì provider trả `email`. Ứng dụng phải kiểm tra `email_verified` khi chính sách yêu cầu, đồng thời tôn trọng ý nghĩa mà provider cam kết.

**Khóa định danh OIDC phù hợp là cặp `(iss, sub)`**, không phải email hoặc tên hiển thị. `sub` có thể là public hoặc pairwise theo provider; cùng một người dùng đăng nhập từ hai client không nhất thiết nhận cùng giá trị `sub`.

### 10.2. ID Token và UserInfo là hai nguồn khác nhau

| Nguồn | Dùng để làm gì? | Điều cần lưu ý |
|---|---|---|
| **ID Token** | Xác minh kết quả OIDC Authentication cho client | Cần kiểm tra chữ ký/issuer/audience/thời gian/nonce theo giao thức. |
| **UserInfo Endpoint** | Cung cấp claims về End-User khi client có token/quyền phù hợp | Không thay thế ID Token; `sub` trả về phải khớp `sub` trong ID Token. |
| **Provider-specific Profile API** | Một API riêng của OAuth2 provider | Không mặc nhiên tuân thủ UserInfo chuẩn; field và auth method riêng. |

Một số provider trả `name`, `email` hoặc avatar trong UserInfo; provider khác có thể đưa chúng vào ID Token, chỉ cung cấp một phần, hoặc yêu cầu scope/endpoint riêng.

Không xây logic kiểu “mọi provider sẽ có `email` từ ID Token” hoặc “UserInfo luôn trả `preferred_username`”. Khi dữ liệu tùy chọn vắng mặt, ứng dụng phải xử lý theo quy tắc nghiệp vụ: để trống, yêu cầu người dùng bổ sung hoặc từ chối tính năng thật sự cần thông tin ấy.

### 10.3. OAuth2 provider không có ID Token thì lấy tên người dùng thế nào?

Trong OAuth2 Login không có `openid`, Spring Security thường dùng một UserInfo endpoint hoặc user-service tùy chỉnh để lấy profile và hình thành principal. Tên trường định danh có thể khác nhau:

~~~json
{
  "id": "8521007",
  "login": "sample-user",
  "display_name": "Sample User"
}
~~~

Một provider khác có thể trả:

~~~json
{
  "user_id": "person-91",
  "nickname": "sample-user"
}
~~~

Đây đều là dữ liệu minh họa. Với provider không dùng OIDC, Spring Security cần biết thuộc tính nào đại diện cho username/ID trong phản hồi OAuth2 UserInfo; có thể khai báo `user-name-attribute` hoặc xây `OAuth2UserService` tùy chỉnh nếu API trả dữ liệu khác chuẩn.

**Không biến trường `id` của OAuth2 provider thành `sub` OIDC một cách tùy ý.** Khi thiết kế liên kết tài khoản nội bộ, hãy lưu riêng loại provider và định danh theo hợp đồng rõ ràng.

## 11. JWKS, thuật toán ký và key rotation

### 11.1. JWKS được dùng làm gì?

Trong OIDC, metadata thường công bố `jwks_uri`:

~~~json
{
  "jwks_uri": "https://id.example.com/.well-known/jwks.json"
}
~~~

Đây là địa chỉ chứa **JSON Web Key Set** với các khóa công khai dùng cho việc xác minh chữ ký của token theo cấu hình. Mỗi JWK có thể chứa `kid`, `kty`, `alg`, `use` hoặc các thành phần khóa tương ứng.

Khi provider xoay khóa ký, token mới có thể dùng `kid` mới. Client cần có cơ chế lấy JWK Set cập nhật và xử lý cache hợp lý. Việc hardcode một public key lấy một lần rồi giữ mãi có thể khiến mọi đăng nhập thất bại sau khi provider rotate key.

### 11.2. Metadata có thể công bố nhiều thuật toán

Ví dụ:

~~~json
{
  "id_token_signing_alg_values_supported": [
    "RS256", "ES256"
  ]
}
~~~

Việc metadata quảng bá cả hai thuật toán **không đồng nghĩa client phải tin mọi thuật toán**. Client cần cấu hình hoặc sử dụng cơ chế xác minh chỉ chấp nhận thuật toán phù hợp với giao thức, provider, client registration và chính sách bảo mật.

Không tin trường `alg` của JWT một cách vô điều kiện. Không bỏ qua xác minh chữ ký vì payload JWT “đọc được” hoặc vì issuer URL trông quen thuộc.

### 11.3. Issuer, key và audience phải được kiểm tra cùng nhau

Một ID Token hợp lệ đối với client hiện tại phải phù hợp với nhiều điều kiện:

~~~text
iss      đúng issuer đã cấu hình?
aud      chứa client_id của ứng dụng?
exp      chưa hết hiệu lực?
signature được xác minh bởi khóa tin cậy của issuer?
nonce    khớp khi client đã dùng nonce?
azp      thỏa điều kiện OIDC khi có nhiều audience/liên quan?
~~~

Chỉ xác minh chữ ký mà bỏ qua `iss` hoặc `aud` có thể khiến ứng dụng chấp nhận token dành cho client/issuer khác. Ngược lại, chỉ kiểm tra `iss` string mà không xác minh chữ ký không có giá trị bảo vệ.

Metadata không thay thế được **logic kiểm tra ID Token** của Spring Security.

## 12. Refresh token, revoke token và introspection không đồng nhất

OAuth2 providers thường khác nhau ở vòng đời token:

- Có provider phát refresh token trong những điều kiện cụ thể.
- Có provider chỉ phát refresh token cho một số client type hoặc scope.
- Có provider dùng refresh token rotation, yêu cầu lưu token mới sau mỗi lần refresh.
- Có provider không cung cấp `revocation_endpoint` hoặc `introspection_endpoint`.
- Có provider cấp access token dạng opaque; provider khác dùng JWT, thậm chí có thể đổi định dạng theo resource/audience.

**Không lấy một refresh token bất kỳ từ token response làm điều luôn được bảo đảm.** Spring Security OAuth2 Client cần xử lý trường hợp không có refresh token và quy tắc cấp lại authorization hợp lệ.

### 12.1. Revocation endpoint là tùy chọn theo hệ sinh thái

Metadata có thể công bố:

~~~json
{
  "revocation_endpoint": "https://id.example.com/oauth2/revoke",
  "introspection_endpoint": "https://id.example.com/oauth2/introspect"
}
~~~

Việc có endpoint không có nghĩa client được phép gọi nó bằng mọi phương thức xác thực hoặc có quyền revoke/introspect mọi token. Đồng thời, **logout khỏi ứng dụng web không tự động đồng nghĩa với revoke access token hoặc kết thúc SSO session ở provider**.

Nếu ứng dụng cần revoke token khi người dùng ngắt kết nối tài khoản, hãy kiểm tra tài liệu chính sách provider, loại token và phương thức client authentication. Nếu ứng dụng là resource server và cần introspection, đó là luồng kiểm tra token inbound riêng, không phải nhiệm vụ mặc định của OAuth2 Login client.

### 12.2. Token endpoint metadata không xác định định dạng access token

Một access token có thể là JWT hoặc opaque. Client **không nên giả định** token nào cũng giải mã được bằng Base64URL hoặc chứa `sub`, `email`, `roles`. Token được cấp để truy cập resource server theo scope/audience được phép.

Nếu API yêu cầu một `audience` hoặc `resource` riêng, có thể cần tham số authorization request/token request hoặc cấu hình ứng dụng theo tài liệu provider. Những tham số vendor-specific đó không tự được hỗ trợ bởi mọi provider khi dùng metadata tiêu chuẩn.

## 13. Logout metadata và hành vi đăng xuất khác nhau

OIDC authentication và logout là hai vấn đề liên quan nhưng không đồng nhất.

Một OpenID Provider có thể công bố:

~~~json
{
  "end_session_endpoint":
    "https://id.example.com/oidc/logout"
}
~~~

Tuy nhiên:

- Trường `end_session_endpoint` có thể không được công bố.
- Provider có thể yêu cầu `id_token_hint`, `post_logout_redirect_uri` hoặc tham số khác.
- `post_logout_redirect_uri` thường phải đăng ký trước hoặc được provider cho phép.
- Provider có thể chỉ xóa SSO session, trong khi token đã cấp vẫn chịu vòng đời riêng.
- Front-channel, back-channel hoặc RP-initiated logout có thể chỉ được hỗ trợ một phần.
- Xóa cookie/session của ứng dụng không bảo đảm người dùng đã đăng xuất khỏi tất cả dịch vụ dùng chung IdP.

Spring Security có thể tích hợp OIDC RP-initiated logout trong những điều kiện provider và cấu hình tương ứng. Nhưng client **không nên tự giả định** chỉ vì provider hỗ trợ OIDC login thì cũng có cùng logout endpoint và hành vi với provider khác.

Đặc biệt, không gắn tùy ý URL `/logout` của một provider vào mọi client registration. Cần kiểm tra metadata, thông số redirect và yêu cầu bảo mật cho từng nhà cung cấp.

## 14. Các phần mở rộng không phải provider nào cũng hỗ trợ

Ngoài phần cốt lõi OAuth2/OIDC, provider có thể hỗ trợ những khả năng tùy chọn như:

| Tính năng | Dữ liệu/parameter liên quan | Giới hạn tích hợp |
|---|---|---|
| **PKCE** | `code_challenge_methods_supported` | Có thể chỉ hỗ trợ `S256`, có thể bắt buộc theo loại client. |
| **PAR — Pushed Authorization Requests** | `pushed_authorization_request_endpoint` | Không phải provider nào cũng có; một số provider có thể yêu cầu PAR. |
| **JAR — JWT-Secured Authorization Request** | `request_object_signing_alg_values_supported` | Cần cấu hình ký request object và client keys. |
| **Dynamic Client Registration** | `registration_endpoint` | Không có nghĩa client bất kỳ được tự đăng ký; cần quyền/trust policy. |
| **Resource Indicators** | `resource` parameter | Cú pháp/giá trị resource phải được provider/API công nhận. |
| **Step-up / ACR** | `acr_values_supported`, `acr_values`, `claims` | Giá trị assurance do OP định nghĩa, có thể chỉ hỗ trợ một số mức. |
| **Reauthentication** | `prompt`, `max_age` | Tương tác phụ thuộc SSO policy và năng lực OP. |
| **Front-/Back-channel logout** | metadata logout liên quan | Cần đăng ký và triển khai riêng. |

Một provider có thể hỗ trợ một phần mở rộng theo tiêu chuẩn nhưng chỉ kích hoạt qua cấu hình quản trị hoặc từng tenant. Không lấy metadata thiếu trường làm cơ sở để tự thay bằng tham số ngoài chuẩn.

### 14.1. Parameter riêng của nhà cung cấp

Một số hệ thống cho phép tham số bổ sung trong authorization request như lựa chọn tenant, login hint, audience/resource hoặc tham số consent. Tên và ý nghĩa các trường đó **không chuẩn hóa đồng nhất giữa mọi hãng**.

Trong Spring Security, việc thêm tham số vào authorization request thường cần customize authorization request resolver hoặc sử dụng API mở rộng phù hợp theo phiên bản và stack Servlet/WebFlux.

Ví dụ ở mức ý tưởng:

~~~text
Client A:
  response_type=code
  scope=openid profile
  prompt=login

Client B:
  response_type=code
  scope=read:data
  audience=https://api-b.example.net
~~~

Đây là hai request minh họa, không có nghĩa `audience` hoặc `prompt` sẽ hoạt động ở mọi provider. **Chỉ thêm tham số khi provider mô tả ý nghĩa và chấp nhận nó.** Không đưa user-controlled endpoint vào request một cách tùy ý.

## 15. Cấu hình Spring Boot: để OIDC Discovery tự cung cấp metadata

Với provider thực sự hỗ trợ OIDC Discovery, cấu hình gọn nhất thường là `issuer-uri`:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          corp:
            provider: corporate-idp
            client-id: ${CORP_CLIENT_ID}
            client-secret: ${CORP_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - email
        provider:
          corporate-idp:
            issuer-uri: https://identity.example.com/tenant-a
~~~

Ở đây:

- `corp` là **registrationId** của ứng dụng Spring, dùng trong URL mặc định `/oauth2/authorization/corp`.
- `corporate-idp` là khóa cấu hình provider, nối registration với issuer.
- `client-id` và `client-secret` thuộc **client registration**, không lấy từ OIDC Discovery.
- `issuer-uri` xác định OP đáng tin cậy và cho phép framework khám phá endpoint/metadata khi phù hợp.
- Scope `openid` đánh dấu đây là OIDC Login.
- `redirect-uri` phải khớp callback đã đăng ký ở provider.

Nếu ứng dụng chạy ở `https://app.example.com`, callback tương ứng là:

~~~text
https://app.example.com/login/oauth2/code/corp
~~~

Địa chỉ này phải được phép tại provider. Với ứng dụng chạy sau reverse proxy, cần xử lý forwarded host/scheme một cách tin cậy để `{baseUrl}` không bị dựng thành HTTP/internal host sai.

### 15.1. Metadata được lấy lúc nào?

Spring Boot có thể tạo `ClientRegistrationRepository` từ các properties; trong quá trình dựng registration có `issuer-uri`, framework thường cần gọi discovery endpoint để lấy provider metadata. Vì vậy cấu hình issuer sai, không có kết nối HTTPS đến provider hoặc metadata không hợp lệ có thể gây lỗi trong quá trình khởi động.

Các lỗi thường gặp:

- issuer URL không đúng realm/tenant;
- chứng chỉ TLS không được tin cậy;
- DNS/firewall không tới được discovery endpoint;
- metadata trả `issuer` khác issuer đã cấu hình;
- thiếu các trường mà thư viện cần để dựng registration;
- proxy/IdP tự quảng bá endpoint nội bộ không truy cập được từ ứng dụng.

Không nên xử lý bằng cách **tắt kiểm tra issuer hoặc chữ ký**. Hãy sửa nguồn metadata hoặc chọn cấu hình endpoint thủ công có chủ đích theo tài liệu provider.

## 16. Cấu hình thủ công khi provider không hỗ trợ discovery chuẩn

Nếu provider hỗ trợ OAuth2 Authorization Code nhưng không có OIDC Discovery, Spring Boot cho phép khai báo endpoint trực tiếp.

Ví dụ **OAuth2 Login không phải OIDC**:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          legacy:
            provider: legacy-provider
            client-id: ${LEGACY_CLIENT_ID}
            client-secret: ${LEGACY_CLIENT_SECRET}
            client-authentication-method: client_secret_post
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - profile.read
        provider:
          legacy-provider:
            authorization-uri: https://login-legacy.example.net/authorize
            token-uri: https://login-legacy.example.net/oauth/token
            user-info-uri: https://api-legacy.example.net/v1/me
            user-name-attribute: id
~~~

Ví dụ giả định UserInfo-like API trả:

~~~json
{
  "id": "u-179",
  "display_name": "Sample User"
}
~~~

Spring Security dùng trường `id` để nhận diện principal trong luồng OAuth2 Login kiểu này. **Cách nhận user info** (HTTP method, header/token, định dạng JSON) phải phù hợp với provider; nếu API khác mô hình mặc định, có thể phải tùy chỉnh `OAuth2UserService`.

Lưu ý:

- Không có `openid`; đây là OAuth2 Login tích hợp profile API, **không phải OIDC authentication**.
- Không đặt `issuer-uri` giả nếu provider không hỗ trợ OIDC discovery.
- `client_secret_post` chỉ là phương thức ví dụ cho provider giả định, không mặc định đúng với mọi nhà cung cấp.
- `user-name-attribute: id` phải khớp **trường thực tế** trong response, không suy diễn từ OIDC `sub`.
- Nếu provider không có API thông tin người dùng thích hợp, cần thiết kế cơ chế lấy principal đúng hợp đồng; chỉ một OAuth2 access token không đủ để tạo OIDC ID Token.

### 16.1. Tự khai báo endpoint cho provider có OIDC nhưng discovery đặc thù

Nếu một provider thực sự hỗ trợ OIDC nhưng không cung cấp discovery theo cách thư viện sử dụng, có thể phải cung cấp authorization/token/JWK/UserInfo/issuer metadata một cách tường minh, với điều kiện framework cho phép.

Dù khai báo thủ công, client vẫn cần kiểm tra **ID Token** đúng chuẩn OIDC: issuer, audience, chữ ký, thời gian, nonce khi dùng. Việc đặt một `jwk-set-uri` trong YAML không tự chứng minh provider tương thích OIDC hoặc token phát hành là ID Token hợp lệ.

Nếu không chắc provider có hỗ trợ OIDC, hãy xác nhận khả năng phát hành ID Token và yêu cầu kiểm tra theo chuẩn; không tự bật OIDC chỉ bằng `scope: openid`.

## 17. Hai provider trong một ứng dụng: cách tổ chức registration

Một Spring Boot ứng dụng có thể tạo nhiều `ClientRegistration`, mỗi registration ánh xạ provider riêng:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          corporate:
            provider: corporate-oidc
            client-id: ${CORP_CLIENT_ID}
            client-secret: ${CORP_CLIENT_SECRET}
            scope: [openid, profile, email]
          partner:
            provider: partner-oauth
            client-id: ${PARTNER_CLIENT_ID}
            client-secret: ${PARTNER_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            scope: [profile.read]
        provider:
          corporate-oidc:
            issuer-uri: https://id-corp.example.com
          partner-oauth:
            authorization-uri: https://login-partner.example.net/authorize
            token-uri: https://login-partner.example.net/token
            user-info-uri: https://api-partner.example.net/profile
            user-name-attribute: user_id
~~~

Hai đường khởi tạo login mặc định:

~~~text
/oauth2/authorization/corporate
/oauth2/authorization/partner
~~~

Điểm quan trọng:

- `registrationId` là tên do ứng dụng Spring chọn, không đồng nghĩa với issuer hay client ID.
- Mỗi registration có thể dùng **issuer, endpoint, scope và client auth method riêng**.
- Corporate registration có scope `openid` và dùng OIDC Discovery.
- Partner registration dùng OAuth2 Profile API riêng, không được đối xử như OIDC Provider.
- Phản hồi hai provider có thể tạo principal khác kiểu (`OidcUser` hoặc `OAuth2User`), cần xử lý ở tầng ứng dụng.

Với triển khai thật, mỗi registration nên khai báo rõ các thuộc tính quan trọng như redirect URI, client auth method và grant type nếu default không phù hợp. Đồng thời lưu secret theo môi trường, không đưa vào Git.

### 17.1. Đừng viết code giả định tất cả principal đều là OidcUser

Ví dụ controller có thể chấp nhận một `OAuth2User` chung:

~~~java
import java.util.Map;

import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.user.OAuth2User;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ProfileController {

    @GetMapping("/me")
    public Map<String, Object> me(
            @AuthenticationPrincipal OAuth2User user) {

        return Map.of(
            "name", user.getName(),
            "attributes", user.getAttributes()
        );
    }
}
~~~

Đoạn code chỉ minh họa nguyên tắc dùng interface chung: **không nên đưa toàn bộ attributes ra public API trong ứng dụng thật**, vì có thể chứa thông tin cá nhân hoặc dữ liệu riêng của provider. Với OIDC-specific logic (kiểm tra `sub`, `iss`, `auth_time`, `acr`), ứng dụng phải làm việc với `OidcUser` sau OIDC Login và đọc ID Token đã xác minh.

Với nhiều provider, kiến trúc tốt hơn là ánh xạ các principal khác nhau sang một **internal user model** và lưu nguồn định danh bên ngoài. Không dùng email duy nhất để tự động ghép mọi người dùng từ các issuer chưa được tin cậy.

## 18. Khi nào nên ghi đè hoặc tùy chỉnh metadata?

Có những trường hợp cần thay đổi một phần thông tin framework khám phá:

- Metadata trả authorization endpoint trên host nội bộ nhưng ứng dụng chỉ truy cập host public.
- Provider không công bố `userinfo_endpoint` nhưng có API profile ngoài chuẩn.
- Token endpoint yêu cầu client authentication method khác.
- Nhà cung cấp có tham số authorization bổ sung.
- Provider cung cấp nhiều tenant/realm; mỗi tenant có issuer khác nhau.
- Nhà cung cấp chỉ triển khai một phần RFC hoặc có metadata không tương thích.

Tùy trường hợp, lựa chọn có thể là:

1. **Sửa cấu hình provider** để metadata xuất đúng URL và issuer; đây là giải pháp phù hợp nhất nếu tổ chức sở hữu IdP.
2. **Khai báo override các URI trong Spring Boot properties**, nếu provider có hành vi đã được xác minh và framework hỗ trợ cách kết hợp đó.
3. **Tạo `ClientRegistration` bằng builder** hoặc dùng `ClientRegistrations.fromIssuerLocation(...)` rồi điều chỉnh những trường cần thiết.
4. **Tùy chỉnh OAuth2 User Service, token client hoặc authorization request resolver** cho phần mở rộng có hợp đồng rõ ràng.
5. **Đặt adapter riêng cho provider đặc thù**, giữ lớp business logic phía trên độc lập với format của từng nguồn danh tính.

Không dùng override để lờ đi các bất biến bảo mật như issuer, audience, redirect URI hoặc chữ ký ID Token. Nếu endpoint trong metadata sai do reverse proxy, hãy sửa base URL/public issuer tại IdP hoặc dùng cấu hình rõ ràng sau khi đã xác định ranh giới tin cậy.

### 18.1. Minh họa dựng ClientRegistration từ issuer đáng tin cậy

Trong ứng dụng Servlet, có thể cấu hình bean thủ công bằng discovery:

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.oauth2.client.registration.ClientRegistrations;
import org.springframework.security.oauth2.client.registration.InMemoryClientRegistrationRepository;

@Configuration
public class RegistrationConfig {

    @Bean
    ClientRegistrationRepository clientRegistrationRepository(
            @Value("${app.login.issuer}") String issuer,
            @Value("${app.login.client-id}") String clientId,
            @Value("${app.login.client-secret}") String clientSecret) {

        ClientRegistration registration = ClientRegistrations
            .fromIssuerLocation(issuer)
            .registrationId("corporate")
            .clientId(clientId)
            .clientSecret(clientSecret)
            .redirectUri("{baseUrl}/login/oauth2/code/{registrationId}")
            .scope("openid", "profile", "email")
            .build();

        return new InMemoryClientRegistrationRepository(registration);
    }
}
~~~

Cách này cho phép lấy metadata từ issuer, sau đó đặt dữ liệu **thuộc client registration** một cách rõ ràng.

- `issuer` phải do cấu hình đáng tin cậy cung cấp; không nhận trực tiếp từ URL query do người dùng gửi.
- `clientId` và `clientSecret` không đến từ discovery, mà từ registration phía provider.
- Phương thức client authentication phải tương thích với client đã đăng ký; nếu provider không dùng default phù hợp thì cần đặt rõ.
- Đường callback phải được đăng ký tại provider.
- Nếu ứng dụng đã tạo bean `ClientRegistrationRepository`, Spring Boot auto-configuration có thể không tạo repository thứ hai từ properties; cần chọn một nguồn cấu hình chủ đạo.

Đây là **cách thay thế** cho repository tạo từ `spring.security.oauth2.client.registration.*`. Không định nghĩa nhiều bean repository mâu thuẫn nhau khi không có nhu cầu riêng.

### 18.2. Cấu hình Servlet và WebFlux khác nhau ở tầng API

Trong Servlet:

~~~text
ClientRegistrationRepository
InMemoryClientRegistrationRepository
HttpSecurity / SecurityFilterChain
~~~

Trong WebFlux:

~~~text
ReactiveClientRegistrationRepository
InMemoryReactiveClientRegistrationRepository
ServerHttpSecurity / SecurityWebFilterChain
~~~

Metadata chuẩn và yêu cầu OIDC không đổi giữa hai stack; **lớp Java và cơ chế reactive của Spring Security khác nhau**. Không đưa bean `ClientRegistrationRepository` bản Servlet vào ứng dụng chỉ cấu hình WebFlux rồi mong luồng reactive tự sử dụng nó.

## 19. Hạn chế của discovery khi vận hành thực tế

Một tài liệu metadata hợp lệ vẫn không loại bỏ mọi vấn đề vận hành.

### 19.1. Discovery có thể phụ thuộc kết nối mạng khi startup

Khi `issuer-uri` được dùng để dựng registration, ứng dụng thường phải truy cập metadata endpoint trong quá trình tạo bean. Nếu IdP hoặc DNS đang lỗi, ứng dụng có thể không khởi động được dù mã nguồn không thay đổi.

Giải pháp vận hành là lựa chọn phù hợp giữa discovery trực tiếp, cấu hình endpoint đã biết, khả năng khởi động khi IdP gián đoạn và chính sách cập nhật metadata. Không tắt TLS validation để “chữa” lỗi kết nối.

### 19.2. Cache và key rotation

Metadata endpoint, JWKS và các endpoint khác có vòng đời cập nhật không nhất thiết giống nhau. Một provider có thể thay khóa ký mà không đổi issuer hoặc endpoint, hoặc thay đổi danh sách thuật toán sau nâng cấp.

Client cần hỗ trợ cập nhật khóa JWK hợp lệ và quan sát lỗi xác minh khi rotate key. Không xem một bản metadata tải thành công một lần là thông tin bất biến mãi mãi.

### 19.3. Multi-tenant issuer

Một nhà cung cấp có thể dùng các issuer:

~~~text
https://id.example.com/tenant-a
https://id.example.com/tenant-b
~~~

Mỗi tenant có thể có token issuer, JWKS, endpoint và chính sách khác nhau. Vì vậy:

- Không thay tenant path bằng phép thay chuỗi không kiểm soát.
- Không dùng key/JWKS của tenant A để xác minh token tenant B chỉ vì cùng host.
- Không tự động chấp nhận một issuer mới từ claim `iss` chưa xác minh.
- Nếu hỗ trợ nhiều tenant, cần repository/routing được quản trị để chọn issuer và registration đúng trước khi xác thực.

### 19.4. Metadata không phản ánh tất cả chính sách người dùng

Ngay cả khi metadata có `acr_values_supported` hoặc `scopes_supported`, provider có thể áp điều kiện theo user, tổ chức, IP, MFA, thiết bị, consent hoặc chính sách quản trị. Một authorization request có tham số đúng syntax vẫn có thể bị từ chối vì chính sách.

Với lỗi do consent hoặc policy, client không nên cố thử các grant type/endpoint khác một cách mù quáng; nên xử lý phản hồi lỗi OAuth2 rõ ràng và giữ an toàn cho dữ liệu giao dịch.

### 19.5. Metadata hợp lệ không bảo đảm phiên login luôn thành công

Client còn phụ thuộc vào:

- Redirect URI đã đăng ký.
- State/PKCE và dữ liệu yêu cầu ủy quyền đã lưu.
- Client secret/private key còn hiệu lực.
- Đồng hồ và thời gian hiệu lực code/token.
- UserInfo endpoint hoặc UserService.
- Session/cookie của ứng dụng.
- Quyền người dùng, consent và policy IdP.

Vì vậy, **discovery thành công là một điều kiện cấu hình**, không phải kiểm chứng đầy đủ cho toàn bộ hành trình đăng nhập.

## 20. Quy trình tích hợp provider mới trong Spring Security

Một quy trình kỹ thuật có thể thực hiện theo các bước sau.

### Bước 1: Xác định provider hỗ trợ OIDC hay chỉ OAuth2

Trước hết cần biết mục đích của ứng dụng:

- Muốn **đăng nhập danh tính theo OIDC**: provider phải hỗ trợ OIDC, phát ID Token hợp lệ và cho phép scope `openid`.
- Muốn **ủy quyền gọi API bằng OAuth2**: có thể không cần OIDC; cần xác định grant type, scope và audience/resource mà API yêu cầu.
- Muốn **đăng nhập từ OAuth2 provider không có OIDC**: phải biết cách lấy profile/principal bằng API phù hợp và hiểu giới hạn của mô hình đó.

Đừng gọi mọi OAuth2 provider là OIDC provider.

### Bước 2: Xác định issuer và nguồn metadata tin cậy

Với OIDC, đọc issuer URI do provider cung cấp, lấy discovery document và đối chiếu `issuer`. Với OAuth2 metadata RFC 8414, đọc document theo cơ chế server hỗ trợ.

Nếu không có discovery, lấy endpoint từ tài liệu chính thức hoặc bộ cấu hình tin cậy. Không lấy một arbitrary URL từ request và coi đó là issuer được phép.

### Bước 3: Đăng ký client

Tại provider, đăng ký:

- Client ID và cách client xác thực (secret, assertion hoặc public client).
- Redirect URIs.
- Grant type cho phép.
- Scopes và APIs cần cấp quyền.
- PKCE và các tùy chọn bắt buộc.
- Logout callback/redirect nếu dùng.

Sau đó lưu thông tin tương ứng vào cấu hình Spring Boot/Spring Security.

### Bước 4: Đối chiếu metadata với registration

Kiểm tra các trường tối thiểu:

| Hạng mục | Cần đối chiếu |
|---|---|
| Issuer | `issuer` từ metadata và issuer tin cậy |
| Authorization endpoint | Đúng URL nhận `response_type=code` |
| Token endpoint | Đúng URL nhận `grant_type=authorization_code` |
| Client authentication | Đúng phương thức đăng ký |
| Redirect URI | Khớp chính xác theo quy tắc provider |
| Scope | Được server hỗ trợ và client được cấp |
| PKCE | Method/verifier/requirement phù hợp |
| ID Token signing | Có khóa/thuật toán có thể xác minh theo hợp đồng OIDC |
| UserInfo | Có endpoint/format phù hợp nếu ứng dụng cần |
| Logout | Có hỗ trợ thật và đăng ký redirect nếu cần |

### Bước 5: Cấu hình Spring Security OAuth2 Login

Trong ứng dụng Servlet, ví dụ tối thiểu:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/", "/public/**").permitAll()
                .anyRequest().authenticated()
            )
            .oauth2Login(Customizer.withDefaults());

        return http.build();
    }
}
~~~

Cấu hình `ClientRegistration` từ `application.yml` hoặc bean repository sẽ cung cấp provider metadata tương ứng.

### Bước 6: Theo dõi luồng thực tế và xử lý khác biệt

Chạy qua:

~~~mermaid
sequenceDiagram
    autonumber
    actor U as Trình duyệt
    participant C as Spring Security OAuth2 Client
    participant P as OAuth2 / OIDC Provider
    U->>C: GET /oauth2/authorization/demo
    Note over C: Tra ClientRegistration & metadata đã cấu hình
    C-->>U: 302 authorization_endpoint
    U->>P: Authorization request (scope, state, PKCE...)
    P-->>U: 302 callback?code=...&state=...
    U->>C: GET /login/oauth2/code/demo
    Note over C: Kiểm tra state & authorization request
    C->>P: POST token_endpoint (code, client auth, verifier)
    P-->>C: Tokens hoặc OAuth2 error
    Note over C: Nếu OIDC: xác minh ID Token
    C-->>U: Tạo phiên hoặc hiển thị lỗi an toàn
~~~

Kiểm tra dữ liệu thực tế ở từng bước nhưng **không ghi code/token/secret vào log**. Với provider có profile API riêng, theo dõi thêm bước lấy thông tin user và kiểm tra kiểu principal được tạo.

### Bước 7: Chuẩn hóa dữ liệu cho business layer

Không nên để controller/service nghiệp vụ phụ thuộc trực tiếp vào tên claim đặc thù của mọi provider.

Ví dụ ánh xạ nội bộ:

~~~text
OIDC Provider A:
  iss + sub -> external identity
  preferred_username -> display name (nếu có)

OAuth2 Provider B:
  provider ID + profile.id -> external identity
  display_name -> display name (nếu có)

                 |
                 v

InternalUser {
  localUserId
  externalProviderKey
  externalSubject
  displayName
  authorities
}
~~~

Lớp chuẩn hóa cần giữ **nguồn định danh tin cậy**. Với OIDC, cặp `(iss, sub)` là dữ liệu chính; với OAuth2 provider thuần, phải có định danh và contract rõ ràng theo provider. Không tự kết nối tài khoản chỉ dựa vào email chưa được xác minh.

## 21. Bảng các khác biệt thường gặp và cách xử lý

| Khác biệt | Biểu hiện khi tích hợp | Cách xử lý |
|---|---|---|
| Không có discovery chuẩn | `issuer-uri` không lấy được metadata | Khai báo endpoint thủ công; xác nhận provider có OIDC hay chỉ OAuth2. |
| Metadata issuer sai | Khám phá hoặc ID Token validation thất bại | Cấu hình đúng issuer/public base URL tại provider; không bỏ qua issuer check. |
| Authorization endpoint khác đường dẫn dự đoán | Redirect sai hoặc 404 | Dùng URL từ metadata/tài liệu chính thức. |
| Token client auth method khác | `invalid_client` | Khớp phương thức client đã đăng ký. |
| PKCE bị bắt buộc | `invalid_request` hoặc `invalid_grant` | Bật PKCE `S256` và giữ verifier xuyên suốt giao dịch. |
| Scope không được cấp | `invalid_scope` hoặc thiếu quyền/token mong muốn | Kiểm tra client registration, consent và policy. |
| Không có UserInfo | Không lấy được profile theo cơ chế mặc định | Dùng dữ liệu ID Token nếu phù hợp hoặc OAuth2UserService/adapter theo provider. |
| Tên trường principal khác | Không tạo được OAuth2User hoặc username không đúng | Cấu hình `user-name-attribute` hay user service. |
| Khác chính sách refresh token | Không có refresh token hoặc refresh thất bại | Điều chỉnh yêu cầu scope/chính sách và vòng đời authorized client. |
| JWKS rotate key | ID Token đột ngột lỗi chữ ký | Kiểm tra JWK retrieval/cache và issuer đúng. |
| Claims tùy chọn thiếu | Null field, sai mapping profile | Chấp nhận optional hoặc yêu cầu scope/claims có hợp đồng rõ. |
| Logout khác nhau | Logout local thành công nhưng SSO vẫn còn | Thiết kế logout phù hợp với provider và endpoint được hỗ trợ. |
| Multi-tenant metadata khác | Token issuer/audience không khớp | Ràng buộc registration với đúng tenant/issuer. |
| Provider-specific parameters | Authorization request không đạt yêu cầu | Custom resolver/request có kiểm soát. |
| Access token không phải JWT | Parse JWT thất bại | Xử lý token theo hợp đồng của API; không giả định format. |

Bảng tập trung vào **sự khác biệt có thể phát sinh**. Không phải provider nào cũng có đủ các hạn chế trên.

## 22. Các sai lầm thiết kế cần tránh

### 22.1. “Có issuer-uri là Spring sẽ hỗ trợ mọi provider”

Sai: `issuer-uri` chỉ hữu ích khi provider có metadata tương thích với cơ chế discovery mà framework dùng. Một OAuth2 API thuần có thể cần authorization/token URI và user service riêng.

### 22.2. “Metadata liệt kê scope nào thì client được cấp scope đó”

Sai: metadata mô tả khả năng, còn đăng ký client, consent và policy quyết định scope được cấp. Refresh token cũng có chính sách riêng.

### 22.3. “Provider trả JWT nên chắc chắn là OIDC”

Sai: access token JWT không phải ID Token. OIDC cần scope `openid`, ID Token đúng chuẩn và các bước kiểm tra tương ứng.

### 22.4. “Mọi provider đều có cùng user attributes”

Sai: có provider trả `sub` theo OIDC, provider OAuth2 thuần trả `id` hoặc `user_id`, email có thể thiếu hoặc chưa xác minh. Cần chuẩn hóa theo contract.

### 22.5. “Thiếu metadata optional thì chắc chắn provider không hỗ trợ tính năng”

Sai trong nhiều tình huống: một số trường có default theo chuẩn, có tính năng được mô tả ngoài discovery hoặc theo policy riêng. Cần đối chiếu tài liệu provider và khả năng thực tế, không tự phỏng đoán.

### 22.6. “Chữ ký ID Token đúng là đủ”

Sai: phải kiểm tra issuer, audience, expiration và các ràng buộc OIDC liên quan; một token hợp lệ cho client khác không được dùng thay.

### 22.7. “Thay tokenUri là đủ để chuyển tenant”

Sai: multi-tenant provider có thể thay issuer, JWK Set, scopes, policy, client registration và UserInfo endpoint. Cần ánh xạ cả registration đáng tin cậy.

### 22.8. “Logout ứng dụng luôn revoke token và logout IdP”

Sai: local session, IdP SSO session và token lifecycle là ba phần cần xử lý theo giao thức và provider.

### 22.9. “Tất cả client đều có client_secret”

Sai: public client không thể giữ secret tin cậy. Cần chọn client authentication và PKCE phù hợp với mô hình ứng dụng.

### 22.10. “Đọc metadata qua HTTP/không xác minh TLS cũng được”

Sai: metadata là nguồn endpoint/khóa và ảnh hưởng trực tiếp đến ranh giới tin cậy. Đối với triển khai thực tế phải truy cập qua kết nối bảo mật, cấu hình issuer tin cậy và không lấy metadata từ host do người dùng tự chỉ định.

## 23. Tình huống thực hành

### Tình huống A: OIDC metadata công bố nhiều phương thức xác thực client

Metadata:

~~~json
{
  "token_endpoint_auth_methods_supported": [
    "client_secret_basic",
    "private_key_jwt"
  ]
}
~~~

Registration quản trị của ứng dụng yêu cầu `private_key_jwt`.

**Cách xử lý:** chọn `private_key_jwt` và cấu hình khóa/assertion phù hợp. Không dùng `client_secret_basic` chỉ vì thư viện có default thuận tiện.

### Tình huống B: Discovery thành công nhưng callback bị từ chối

Metadata có authorization/token endpoint hợp lệ. Khi đăng nhập, provider báo redirect URI không được chấp nhận.

**Cách xử lý:** kiểm tra `redirect-uri` thực tế Spring gửi và allowlist của client tại provider. Discovery thành công không chứng minh callback được cấp quyền.

### Tình huống C: Provider có scope email nhưng ID Token thiếu email

Metadata quảng bá `email` và client yêu cầu `openid email`. ID Token chỉ có `iss`, `sub`, `aud`, `exp`, `iat`.

**Cách xử lý:** vẫn đánh giá tính hợp lệ ID Token qua claims bắt buộc; xử lý email như dữ liệu tùy chọn, có thể lấy từ UserInfo nếu được hỗ trợ/quyền cho phép. Không thay `sub` bằng email hoặc mặc định email đã xác minh.

### Tình huống D: Provider chỉ có OAuth 2.0 Authorization Server Metadata

Provider công bố `authorization_endpoint`, `token_endpoint` và `jwks_uri` nhưng không có ID Token hay OIDC Discovery.

**Cách xử lý:** dùng OAuth2 Client theo grant/API cần thiết. Nếu bài toán yêu cầu đăng nhập OIDC chuẩn, phải chọn hoặc cấu hình provider có hỗ trợ OIDC thật; không gọi JWT access token là ID Token.

### Tình huống E: Provider đổi khóa ký

Một ngày sau khi deploy, ID Token mới có `kid` chưa có trong JWK Set cache cũ.

**Cách xử lý:** xem cách Spring Security/JWK client làm mới cache, kiểm tra endpoint/certificate và issuer; không tắt xác minh chữ ký. Nếu provider thực hiện key rotation theo lịch, cần quan sát sự kiện và cách phân phối khóa mới.

### Tình huống F: Hai tenant cùng một host

Token tenant A có issuer `https://id.example.com/tenant-a`; ứng dụng kỳ vọng tenant B `https://id.example.com/tenant-b`.

**Cách xử lý:** từ chối token không đúng issuer, dù host giống nhau. Nếu ứng dụng hỗ trợ cả hai tenant, ánh xạ registration tin cậy và định danh người dùng theo issuer tương ứng.

### Tình huống G: Provider hỗ trợ refresh token nhưng không cấp cho client

Metadata không phủ nhận refresh token, nhưng token response không có `refresh_token`.

**Cách xử lý:** kiểm tra grant, scope, consent, client type và chính sách quản trị. Ứng dụng không được tự giả định token response sai; có provider chỉ cấp refresh token khi điều kiện riêng được đáp ứng.

### Tình huống H: Provider OAuth2 trả user_id thay vì sub

Ứng dụng có adapter UserInfo lấy:

~~~json
{
  "user_id": "partner-417",
  "display_name": "Example Person"
}
~~~

**Cách xử lý:** với OAuth2 Login, cấu hình `user-name-attribute: user_id` nếu phản hồi phù hợp với cơ chế mặc định; nếu không, tùy chỉnh user service. Không áp các quy tắc OIDC `iss + sub` một cách máy móc lên profile API không có giao thức OIDC.

## 24. Câu hỏi tự kiểm tra

**Câu 1.** OIDC Discovery và OAuth2 Authorization Server Metadata có giống hoàn toàn không?

**Trả lời:** Không. Chúng chia sẻ nhiều ý tưởng như issuer, authorization/token endpoint nhưng OIDC Discovery mô tả thêm các khả năng liên quan đến ID Token, subject và xác thực người dùng. Một OAuth2 server không mặc nhiên là OIDC Provider.

**Câu 2.** Nếu `scopes_supported` có `offline_access`, client có chắc chắn nhận refresh token không?

**Trả lời:** Không. Còn phụ thuộc client registration, grant type, consent, chính sách provider và phản hồi token thực tế.

**Câu 3.** Khi provider chỉ hỗ trợ `client_secret_post` cho client đã đăng ký, nên làm gì?

**Trả lời:** Cấu hình đúng client authentication method trong Spring Security, gửi secret theo phương thức yêu cầu trên HTTPS và kiểm tra hợp đồng với provider.

**Câu 4.** Vì sao không nên dùng email làm định danh tài khoản xuyên provider?

**Trả lời:** Email có thể đổi, thiếu, tái sử dụng hoặc chưa được xác minh. Với OIDC, nên dùng cặp `(issuer, subject)` để định danh người dùng theo OP.

**Câu 5.** Một OIDC Provider thiếu `end_session_endpoint` có làm authorization code login thất bại không?

**Trả lời:** Không nhất thiết. Logout endpoint là khả năng khác với login; phải thiết kế cách logout phù hợp với tính năng provider hỗ trợ.

**Câu 6.** `code_challenge_methods_supported` vắng mặt có chứng minh provider không hỗ trợ PKCE không?

**Trả lời:** Không. Cần kiểm tra tài liệu, cấu hình client và hành vi thực tế; không suy ra chỉ từ một trường metadata tùy chọn.

**Câu 7.** Vì sao phải kiểm tra `issuer` chính xác kể cả khi có JWKS?

**Trả lời:** JWKS/khóa giúp xác minh chữ ký, còn issuer ràng buộc token với đúng OP đã tin cậy. Phải kết hợp các điều kiện xác minh token, gồm audience và expiration.

**Câu 8.** Khi nào nên khai báo `authorization-uri`, `token-uri` và `user-info-uri` thủ công?

**Trả lời:** Khi provider không có discovery tương thích hoặc cần tích hợp OAuth2 profile API ngoài chuẩn theo tài liệu nhà cung cấp. Cần biết rõ đây là OAuth2 thuần hay OIDC thực sự.

**Câu 9.** Provider quảng bá `private_key_jwt` nghĩa là Spring tự có khóa riêng để ký assertion?

**Trả lời:** Không. Ứng dụng phải có client registration, khóa và thành phần ký assertion theo cấu hình thích hợp.

**Câu 10.** Tại sao không chọn provider động từ một `issuer` do người dùng nhập vào?

**Trả lời:** Vì có thể dẫn đến truy xuất metadata từ nguồn không tin cậy, sai ranh giới issuer và các rủi ro như SSRF hoặc login mix-up. Cần danh sách/ánh xạ provider đã được quản trị và tin cậy.

## 25. Ghi nhớ trọng tâm

| Điều cần nhớ | Cách áp dụng trong Spring Security OAuth2/OIDC Client |
|---|---|
| **Metadata mô tả server, không phải quyền của client** | Luôn đối chiếu client registration, scopes và chính sách thực tế. |
| **OIDC Discovery khác OAuth2 metadata chung** | Chỉ dùng OIDC Login khi provider thực sự phát ID Token và hỗ trợ yêu cầu OIDC. |
| **Issuer là ranh giới tin cậy** | Cấu hình issuer chính xác, xác minh `iss`, không chấp nhận issuer tùy ý. |
| **Endpoint không có URL chung cho mọi hãng** | Dùng discovery hợp lệ hoặc cấu hình URI theo tài liệu provider. |
| **Client auth method phải khớp registration** | Chọn `client_secret_basic`, `client_secret_post`, `private_key_jwt`... theo hợp đồng. |
| **PKCE cần kiểm tra theo loại client/provider** | Ưu tiên `S256`, giữ verifier đúng giao dịch, không suy đoán từ metadata thiếu trường. |
| **Claims và UserInfo có thể khác nhau** | Xử lý optional claims và chuẩn hóa principal trong application layer. |
| **JWKS có thể rotate key** | Dùng cơ chế xác minh và cập nhật khóa tin cậy, không hardcode khóa bất biến. |
| **Refresh/logout/revocation là khả năng riêng** | Đọc metadata và chính sách nhà cung cấp; không giả định chúng luôn có. |
| **Một ứng dụng có thể có nhiều registrations** | Dùng `spring.security.oauth2.client.registration.*` và `provider.*` tách biệt. |

Khi tích hợp một provider mới, hãy bắt đầu từ **giao thức provider thực sự hỗ trợ**, lấy metadata từ nguồn tin cậy, đối chiếu với **client registration được cấp**, sau đó cấu hình `ClientRegistration` chính xác và quan sát **authorization code flow thực tế**. Cách tiếp cận này giúp ứng dụng Spring Security tương thích với nhiều nhà cung cấp, đồng thời giữ vững kiểm tra issuer, audience, token và các yêu cầu bảo mật của OIDC.
