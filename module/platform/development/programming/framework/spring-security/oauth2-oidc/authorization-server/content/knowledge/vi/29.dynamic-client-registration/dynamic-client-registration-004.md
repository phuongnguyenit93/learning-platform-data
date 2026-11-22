# Kiểm tra redirect_uris, grant_types, response_types và authentication method

## 1. Bối cảnh và mục tiêu

Trong chương **Đăng ký client động** của module **SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER**, bài học này tập trung vào bước quan trọng nhất khi tiếp nhận một client mới: **xác minh metadata mà client gửi trước khi biến metadata đó thành một RegisteredClient có quyền tham gia OAuth 2.0/OpenID Connect**.

Module hướng tới việc học cách thiết kế, cấu hình, bảo mật, kiểm thử và vận hành OAuth 2.0/OpenID Connect Authorization Server bằng Spring Security và Spring Authorization Server trong ứng dụng Spring Boot. Dynamic Client Registration (DCR) là một điểm nhạy cảm vì một request đăng ký có thể tạo ra client_id, credential, redirect URI và tập quyền mới trong hệ thống.

Giả sử một đối tác gửi request đăng ký:

~~~json
{
  "client_name": "Orders Partner Portal",
  "application_type": "web",
  "redirect_uris": [
    "https://partner.example.com/oauth/callback"
  ],
  "grant_types": [
    "authorization_code",
    "refresh_token"
  ],
  "response_types": [
    "code"
  ],
  "token_endpoint_auth_method": "client_secret_basic",
  "scope": "openid profile orders.read"
}
~~~

Trước khi lưu client, Authorization Server phải trả lời:

1. Redirect URI có thuộc domain và ứng dụng mà đối tác kiểm soát không?
2. Grant type có nằm trong danh sách server cho phép không?
3. Response type có tương thích với grant type và endpoint server thực sự hỗ trợ không?
4. Client chọn authentication method nào ở Token Endpoint? Method đó có phù hợp loại client và key/secret được cấp không?
5. Scope có nằm trong allowlist và có vượt quyền mà registrar được phép cấp không?
6. Request có được gửi bởi registrar đã xác thực và có quyền tạo client không?

Một client registration thành công không chỉ có nghĩa JSON hợp lệ. Nó có nghĩa Authorization Server chấp nhận một **hợp đồng bảo mật** cho những lần authorization và token request về sau.

Sau bài này, bạn có thể:

- Phân biệt OAuth 2.0 Dynamic Client Registration theo RFC 7591 và OpenID Connect Dynamic Client Registration.
- Kiểm tra redirect_uris theo exact matching, phân biệt web client và native client.
- Kiểm tra grant_types và response_types theo ma trận tương thích.
- Chọn token_endpoint_auth_method phù hợp public/confidential client.
- Xây dựng validator có allowlist cho metadata và scopes.
- Bật OIDC Client Registration Endpoint trong Spring Authorization Server 1.5.x.
- Bảo vệ Initial Access Token, Registration Access Token và Client Configuration Endpoint.
- Kiểm thử các trường hợp đăng ký hợp lệ, metadata mâu thuẫn và tấn công redirect.

## 2. Dynamic Client Registration là gì?

Dynamic Client Registration cho phép một OAuth Client hoặc OpenID Connect Relying Party gửi metadata tới Registration Endpoint để được cấp client identifier và các thông tin đăng ký cần thiết. Sau khi đăng ký, client sử dụng metadata đã được chấp thuận để tương tác với Authorization Server.

Hai chuẩn cần phân biệt:

| Chuẩn | Phạm vi |
| --- | --- |
| **RFC 7591 — OAuth 2.0 Dynamic Client Registration Protocol** | Định nghĩa giao thức đăng ký OAuth client, metadata, request/response và lỗi |
| **OpenID Connect Dynamic Client Registration 1.0** | Mở rộng/mô tả việc OIDC RP đăng ký với OpenID Provider, có Client Configuration Endpoint và các metadata OIDC |
| **RFC 7592 — OAuth 2.0 Dynamic Client Registration Management Protocol** | Định nghĩa quản lý registration đã tạo, bao gồm đọc/cập nhật/xóa theo registration access token |

Spring Authorization Server 1.5.8 cung cấp **OpenID Connect 1.0 Client Registration Endpoint** theo hướng dẫn DCR của OIDC. Không nên mặc định endpoint này đồng nghĩa với mọi profile hoặc tính năng quản trị DCR của RFC 7591/7592 đều được hỗ trợ y hệt.

### 2.1. Quy trình tổng quát

~~~mermaid
sequenceDiagram
    autonumber
    participant Admin as Registrar / Client Developer
    participant AS as Authorization Server
    participant Repo as RegisteredClientRepository
    Admin->>AS: Xin Initial Access Token
    AS-->>Admin: IAT có quyền client.create
    Admin->>AS: POST Client Registration Request + Bearer IAT
    AS->>AS: Xác thực registrar và kiểm tra metadata
    AS->>AS: Sinh client_id và credential nếu phù hợp
    AS->>Repo: Lưu RegisteredClient
    Repo-->>AS: Đã lưu
    AS-->>Admin: Client Registration Response + registration_access_token
    Admin->>AS: GET registration_client_uri + Bearer RAT
    AS-->>Admin: Client Configuration Response
~~~

Các bước xác thực registrar và validation metadata diễn ra **trước khi** ghi RegisteredClient. Không nhận client metadata rồi lưu trước, sau đó mới chạy validation ở Authorization Endpoint.

### 2.2. Đăng ký mở và đăng ký có bảo vệ

| Mô hình | Đặc điểm | Rủi ro |
| --- | --- | --- |
| Open Dynamic Registration | Bất kỳ caller nào cũng có thể đăng ký theo policy | Client spam, redirect URI độc hại, scope abuse, chiếm tài nguyên |
| Protected Dynamic Registration | Cần Initial Access Token, software statement hoặc quy trình onboarding được xác thực | Phải quản lý cấp phát, hết hạn và thu hồi quyền registrar |
| Admin-mediated registration | Developer gửi metadata nhưng admin/automation phê duyệt | Có thêm bước vận hành nhưng kiểm soát được domain, owner và grant |

Trong hệ thống production, không nên mở đăng ký không xác thực chỉ vì endpoint đã có sẵn. Dùng protected registration và phân quyền registrar theo tổ chức/tenant.

## 3. Bốn nhóm metadata trọng tâm

### 3.1. redirect_uris

redirect_uris là danh sách URI mà Authorization Server được phép chuyển browser về sau authorization. Đây là metadata có ảnh hưởng trực tiếp tới nơi Authorization Code hoặc Authorization Response được gửi.

Ví dụ:

~~~json
{
  "redirect_uris": [
    "https://portal.example.com/login/oauth2/code/partner"
  ]
}
~~~

Các điểm phải kiểm tra:

- Có ít nhất một redirect URI nếu client dùng flow dựa trên redirect.
- URI có scheme hợp lệ và không chứa fragment.
- Web client dùng HTTPS.
- Native client dùng claimed HTTPS URI, custom scheme phù hợp hoặc loopback redirect theo RFC 8252.
- Không chấp nhận wildcard/pattern tùy tiện.
- Domain/path phải được xác minh theo policy onboarding.
- Authorization Endpoint phải so sánh redirect_uri request với URI đã đăng ký theo exact string matching, ngoại trừ port của loopback URI native app theo chuẩn.

### 3.2. grant_types

grant_types là danh sách OAuth grant mà client khai báo sẽ sử dụng tại Token Endpoint.

Ví dụ:

~~~json
{
  "grant_types": [
    "authorization_code",
    "refresh_token"
  ]
}
~~~

Không chấp nhận grant chỉ vì chuỗi đó có trong RFC. Authorization Server chỉ nên cấp grant mà server đã triển khai, đã cấu hình và policy của registrar cho phép. RFC 9700 khuyến nghị không dùng Implicit Grant và Resource Owner Password Credentials Grant.

### 3.3. response_types

response_types là các giá trị response_type client khai báo sẽ sử dụng tại Authorization Endpoint.

Ví dụ:

~~~json
{
  "response_types": [
    "code"
  ]
}
~~~

Với Authorization Code Flow, response_type là code và grant tương ứng là authorization_code. Client không được đăng ký response type mà Authorization Endpoint không hỗ trợ.

### 3.4. token_endpoint_auth_method

token_endpoint_auth_method xác định cách client xác thực tại Token Endpoint.

Các giá trị OIDC Registration 1.0 thường gặp:

- client_secret_basic
- client_secret_post
- client_secret_jwt
- private_key_jwt
- none

Các phương thức mở rộng như tls_client_auth hoặc self_signed_tls_client_auth chỉ được chấp nhận khi Authorization Server đã triển khai và cấu hình hỗ trợ.

**Không coi authentication method là một thuộc tính hiển thị.** Nó quyết định client sẽ chứng minh danh tính bằng secret, private key, certificate hay không có client credential.

## 4. Kiểm tra redirect_uris an toàn

### 4.1. Exact matching là mặc định

Khi Authorization Request tới:

~~~text
redirect_uri=https://portal.example.com/oauth/callback
~~~

giá trị đó phải khớp URI đã đăng ký theo quy tắc simple string comparison. Không thay exact match bằng các cách kiểm tra lỏng như:

~~~text
startsWith("https://portal.example.com")
contains("portal.example.com")
endsWith("example.com")
~~~

Các cách trên có thể chấp nhận URI độc hại:

| URI độc hại | Vì sao kiểm tra lỏng có thể mắc lỗi |
| --- | --- |
| https://portal.example.com.attacker.invalid/callback | Host thực tế là attacker.invalid |
| https://portal.example.com@attacker.invalid/callback | Userinfo làm người đọc nhầm host |
| https://attacker.invalid/?next=https://portal.example.com | Open redirect có thể nằm ở endpoint khác |
| https://portal.example.com.evil/callback | Domain chỉ có tiền tố giống domain hợp lệ |

RFC 9700 yêu cầu Authorization Server dùng exact matching, ngoại trừ port của localhost/loopback redirect URI cho native apps theo RFC 8252.

### 4.2. URI không có fragment

Redirect URI đăng ký không được chứa fragment. Ví dụ sau phải bị từ chối:

~~~text
https://portal.example.com/callback#token
~~~

Fragment không được gửi tới server theo cách thông thường và có thể tạo khác biệt giữa cách browser, proxy và server diễn giải response. Spring Authorization Server cung cấp DEFAULT_REDIRECT_URI_VALIDATOR để từ chối URI có fragment, thiếu scheme hoặc dùng scheme nguy hiểm.

### 4.3. Web client

Với web client, policy phổ biến:

- Chỉ dùng HTTPS.
- Domain phải thuộc allowlist hoặc đã xác minh quyền sở hữu.
- Không chấp nhận IP public tùy tiện nếu chưa có quy trình phê duyệt.
- Không dùng wildcard host/path.
- Không cho phép redirect endpoint là open redirector.
- Đăng ký callback path cụ thể thay vì toàn bộ domain.

Ví dụ:

~~~text
https://portal.example.com/oauth/callback
https://portal.example.com/login/oauth2/code/partner
~~~

Không đăng ký:

~~~text
https://portal.example.com/*
https://*.example.com/oauth/callback
~~~

### 4.4. Native application

RFC 8252 định nghĩa các lựa chọn redirect URI cho native apps:

| Loại | Ví dụ | Lưu ý |
| --- | --- | --- |
| Claimed HTTPS URI | https://app.example.com/oauth2redirect/provider | Hệ điều hành có thể định tuyến URI tới app đã claim domain |
| Private-use custom scheme | com.example.app:/oauth2redirect/provider | Scheme nên dùng reverse-domain notation để giảm va chạm |
| Loopback IPv4 | http://127.0.0.1:51004/oauth2redirect/provider | Authorization Server phải cho phép port động theo RFC 8252 |
| Loopback IPv6 | http://[::1]:61023/oauth2redirect/provider | Chỉ lắng nghe loopback interface |

Native client là public client trong phần lớn trường hợp; không nhúng client secret vào ứng dụng mobile/desktop vì người dùng có thể trích xuất. Authorization Code + PKCE là flow phù hợp.

**Ngoại lệ port động chỉ áp dụng loopback URI của native app.** Không áp dụng ngoại lệ này cho web callback hoặc custom scheme URI.

Lưu ý khi dùng **OIDC Dynamic Client Registration 1.0**: metadata `application_type=native` yêu cầu redirect URI dùng private-use custom scheme hoặc loopback URL với HTTP theo quy tắc của OIDC Registration. RFC 8252 còn mô tả claimed HTTPS URI cho native app; nếu muốn dùng dạng này, phải xác minh OP có hỗ trợ profile/extension tương ứng, không tự giả định mọi OIDC DCR endpoint chấp nhận nó.

### 4.5. Không mặc định chấp nhận localhost tùy ý

RFC 8252 nói loopback IP literal như 127.0.0.1 hoặc [::1] là lựa chọn rõ ràng; dùng hostname localhost không được khuyến nghị vì cách phân giải và binding có thể không nhất quán. Nếu policy cho phép localhost, phải giới hạn theo application_type=native và kiểm tra phần còn lại của URI.

### 4.6. Redirect URI phải được kiểm tra cả lúc đăng ký và lúc authorization

Validation khi đăng ký không thay thế validation khi Authorization Request đến. Khi request thực tế gửi redirect_uri, server vẫn phải so sánh với tập URI đã đăng ký cho đúng client_id. Không lấy URI mới từ query parameter rồi tự động thêm vào registration.

## 5. Kiểm tra grant_types

### 5.1. Danh sách grant không phải danh sách server bắt buộc hỗ trợ

RFC 7591 định nghĩa các grant OAuth phổ biến; OIDC Dynamic Client Registration chỉ liệt kê tập grant OIDC riêng. Cần phân biệt metadata của hai profile:

| grant_type | Profile/nguồn | Mục đích và chính sách |
| --- | --- | --- |
| authorization_code | RFC 7591 và OIDC DCR | Đổi Authorization Code lấy token; khuyến nghị dùng PKCE |
| refresh_token | RFC 7591 và OIDC DCR | Đổi Refresh Token; cần rotation/reuse protection theo policy |
| implicit | RFC 7591 và OIDC DCR | Trả token/ID Token qua Authorization Endpoint; không khuyến nghị cho hệ thống mới |
| client_credentials | RFC 7591 | Machine-to-machine; chỉ confidential client có khả năng xác thực |
| password | RFC 7591 | Resource Owner Password Credentials; RFC 9700 yêu cầu không sử dụng grant này |
| JWT/SAML bearer | RFC 7591 extension grant | Chỉ cho phép nếu server có implementation và policy riêng |
| device_code | RFC 8628 extension grant | Chỉ cho phép khi server đã bật Device Authorization Grant |

OIDC DCR 1.0 liệt kê `authorization_code`, `implicit` và `refresh_token` trong metadata `grant_types`. `client_credentials`, `password`, JWT/SAML bearer và Device Authorization thuộc OAuth DCR tổng quát hoặc extension; không tự suy ra OIDC Client Registration Endpoint của Spring Authorization Server hỗ trợ chúng chỉ vì `RegisteredClient` có thể biểu diễn grant tương ứng.

### 5.2. Kiểm tra grant với loại client

| Loại client | Grant phù hợp thường gặp | Ràng buộc |
| --- | --- | --- |
| Web confidential | authorization_code, refresh_token | Client authentication tại Token Endpoint; PKCE vẫn nên bật |
| SPA public | authorization_code | PKCE bắt buộc; không có client secret |
| Native mobile/desktop | authorization_code, refresh_token | PKCE; redirect theo RFC 8252 |
| Backend service | client_credentials trong OAuth DCR tổng quát hoặc quy trình quản trị riêng | Confidential client authentication; không có user redirect flow |
| Device client | urn:ietf:params:oauth:grant-type:device_code hoặc giá trị theo implementation | Phải có Device Authorization Endpoint |

Không cho public client dùng client_credentials như một cách thay thế xác thực client. Grant này dành cho confidential client.

Spring Authorization Server 1.5.8 cung cấp OIDC Client Registration Endpoint. Nếu cần đăng ký machine-to-machine client với `client_credentials`, hãy xác minh metadata profile mà endpoint hỗ trợ hoặc dùng quy trình quản trị/API riêng; không mặc định ví dụ OAuth DCR tổng quát là request OIDC DCR tương thích.

### 5.3. Scope và grant phải cùng policy

Client chỉ được đăng ký scope trong allowlist phù hợp với application/tenant. Việc đăng ký scope không đồng nghĩa scope được cấp cho mọi authorization; Authorization Server vẫn xét consent, client policy và user authorization khi cấp token.

Ví dụ một web portal có thể được phép:

~~~text
openid
profile
orders.read
~~~

Nhưng không được tự đăng ký:

~~~text
admin
system.write
tenant.impersonate
~~~

nếu registrar không có quyền cấp các scope đó.

## 6. Kiểm tra response_types

### 6.1. Response type và grant type nằm ở hai endpoint khác nhau

- response_types giới hạn tham số response_type tại Authorization Endpoint.
- grant_types giới hạn tham số grant_type tại Token Endpoint.

Hai trường có quan hệ nhưng không thể thay thế nhau.

### 6.2. Ma trận tương thích theo OIDC Dynamic Client Registration

| response_type | grant_types cần có |
| --- | --- |
| code | authorization_code |
| id_token | implicit |
| id_token token | implicit |
| code id_token | authorization_code, implicit |
| code token | authorization_code, implicit |
| code id_token token | authorization_code, implicit |

Trong OIDC DCR 1.0, bảng trên là quan hệ bắt buộc giữa response type mà RP khai báo và grant type cần có. Giá trị `token` độc lập thuộc bảng response type OAuth Implicit của RFC 7591 tổng quát, không phải một hàng trong bảng response type OIDC DCR này.

RFC 7591 tổng quát quy định quan hệ OAuth như sau:

| grant_types có chứa | response_types phải có |
| --- | --- |
| authorization_code | code |
| implicit | token |
| password | Không yêu cầu response type |
| client_credentials | Không yêu cầu response type |
| refresh_token | Không yêu cầu response type |
| JWT bearer / SAML bearer | Không yêu cầu response type |

Các extension grant/response phải tự định nghĩa quan hệ tương ứng. Vì vậy, validator phải áp dụng đúng profile đang triển khai thay vì trộn hai bảng.

Authorization Server nên từ chối registration không nhất quán thay vì tự sửa metadata một cách âm thầm. Ví dụ:

~~~json
{
  "grant_types": ["client_credentials"],
  "response_types": ["code"]
}
~~~

Đây là registration không phù hợp vì client khai báo response_type code nhưng không có authorization_code grant.

### 6.3. Authorization Code Flow

Đối với Authorization Code Flow:

~~~json
{
  "grant_types": [
    "authorization_code",
    "refresh_token"
  ],
  "response_types": [
    "code"
  ]
}
~~~

refresh_token không tạo response_type riêng. Nó cho phép client đổi Refresh Token tại Token Endpoint sau khi đã được cấp Refresh Token theo policy.

### 6.4. Server phải giới hạn response type thực sự hỗ trợ

Một registration có response_types=code không có nghĩa server sẽ tự hỗ trợ hybrid/implicit. Nếu Authorization Server chỉ hỗ trợ code, hãy allowlist duy nhất code. Không quảng bá hoặc chấp nhận response type không có handler tương ứng.

RFC 9700 khuyến nghị dùng Authorization Code thay vì các response type trả Access Token trực tiếp từ Authorization Endpoint. Implicit Flow và Password Grant không nên được bật cho hệ thống mới.

## 7. Kiểm tra token_endpoint_auth_method

### 7.1. Ý nghĩa từng phương thức

| Method | Client chứng minh danh tính bằng | Loại client |
| --- | --- | --- |
| client_secret_basic | Client ID và secret qua HTTP Basic | Confidential |
| client_secret_post | Client ID và secret trong form body | Confidential |
| client_secret_jwt | JWT ký bằng shared secret | Confidential |
| private_key_jwt | JWT ký bằng private key của client; server xác minh qua public key | Confidential |
| none | Không có client secret/authentication tại Token Endpoint | Public |
| tls_client_auth | X.509 client certificate theo PKI | Confidential |
| self_signed_tls_client_auth | Self-signed client certificate đã đăng ký | Confidential |

Các phương thức TLS client authentication là extension của OAuth/OIDC client authentication method registry và cần được server hỗ trợ rõ ràng.

`client_secret_post` có thể được dùng vì tương thích, nhưng cần cân nhắc rủi ro secret xuất hiện trong form body và các log/request tracing. Chỉ cho phép nếu có nhu cầu rõ ràng; ưu tiên phương thức xác thực phù hợp hơn như `client_secret_basic` hoặc `private_key_jwt` khi kiến trúc hỗ trợ.

### 7.2. Giá trị mặc định

Trong OIDC Dynamic Client Registration, nếu token_endpoint_auth_method bị bỏ qua, mặc định là client_secret_basic. Registrar không nên để client type/auth method mơ hồ; hãy gửi giá trị tường minh hoặc áp dụng default đã công bố.

### 7.3. Public client dùng none

none có nghĩa client không có client secret. Ví dụ SPA:

~~~json
{
  "application_type": "web",
  "redirect_uris": [
    "https://spa.example.com/oauth/callback"
  ],
  "grant_types": [
    "authorization_code"
  ],
  "response_types": [
    "code"
  ],
  "token_endpoint_auth_method": "none"
}
~~~

Public client không thể giữ secret một cách đáng tin cậy. Authorization Server phải yêu cầu PKCE cho Authorization Code Flow và không được xem client_id là bằng chứng xác thực.

### 7.4. Confidential client

Ví dụ web backend:

~~~json
{
  "application_type": "web",
  "redirect_uris": [
    "https://partner.example.com/oauth/callback"
  ],
  "grant_types": [
    "authorization_code",
    "refresh_token"
  ],
  "response_types": [
    "code"
  ],
  "token_endpoint_auth_method": "client_secret_basic"
}
~~~

Authorization Server sinh client_id và client_secret khi registration thành công nếu method cần secret. Client secret có thể xuất hiện trong Registration Response và metadata Client Read Response theo OIDC DCR; không giả định chỉ response đầu tiên có trường này. Registrar phải bảo vệ Registration Access Token và response registration, lưu credential được cấp vào secret manager và không ghi log.

### 7.5. private_key_jwt và JWKS

Nếu client dùng private_key_jwt, server cần public key để xác minh JWT client assertion. Client có thể cung cấp jwks_uri hoặc JWK Set theo metadata được chuẩn hỗ trợ.

Quy tắc:

- jwks_uri phải dùng HTTPS.
- Nếu client có thể cung cấp jwks_uri, không đồng thời gửi jwks by value; OIDC DCR quy định hai metadata này không được dùng cùng nhau và ưu tiên jwks_uri để hỗ trợ key rotation.
- JWK Set chỉ chứa public key material.
- Không nhận private key hoặc symmetric secret trong JWKS công khai.
- Kiểm tra key type, use, alg, kid và key suitability.
- Có quy trình key rotation và xử lý key bị compromise.
- Với client_secret_jwt hoặc private_key_jwt, nếu token_endpoint_auth_signing_alg được gửi thì chỉ chấp nhận thuật toán trong allowlist; nếu bỏ qua, áp dụng default thuật toán đã công bố. Không chấp nhận alg=none.

Không fetch jwks_uri một cách không kiểm soát. Nếu Authorization Server chủ động truy cập URL này, phải chống SSRF bằng kiểm tra scheme/host/IP, chặn private/link-local ranges, giới hạn redirect, timeout, response size và DNS rebinding theo kiến trúc.

### 7.6. Không cho phép downgrade authentication method

Một client đã đăng ký private_key_jwt hoặc mTLS không nên được đổi sang none hoặc client_secret_post chỉ bằng một request metadata không được phê duyệt. Thay đổi authentication method cần xác thực chủ sở hữu registration, kiểm tra key/secret mới và audit.

## 8. Kiểm tra tính nhất quán giữa bốn trường

Một validator phải kiểm tra cả từng field lẫn quan hệ giữa chúng.

| redirect_uris | grant_types | response_types | token_endpoint_auth_method | Đánh giá |
| --- | --- | --- | --- | --- |
| HTTPS callback hợp lệ | authorization_code | code | client_secret_basic | Hợp lệ cho web confidential nếu policy cho phép |
| HTTPS callback hợp lệ | authorization_code | code | none | Hợp lệ cho public client nếu PKCE bắt buộc |
| Callback wildcard | authorization_code | code | client_secret_basic | Từ chối |
| HTTPS callback | client_credentials | code | client_secret_basic | Từ chối do grant/response mismatch |
| Không redirect URI | client_credentials | Không dùng response type | client_secret_basic | Có thể hợp lệ cho machine client theo policy |
| HTTPS callback | authorization_code | token | none | Từ chối nếu server không hỗ trợ implicit |
| HTTPS callback | password | code | client_secret_post | Từ chối theo policy bảo mật hiện đại |
| HTTPS callback | authorization_code | code | none nhưng không yêu cầu PKCE | Từ chối |

Các hàng client_credentials và response_type token minh họa quy tắc OAuth DCR tổng quát theo RFC 7591. Với OIDC DCR, áp dụng tập response/grant được định nghĩa trong OIDC Registration 1.0 và khả năng thực tế của OP.

### 8.1. Validation theo profile client

Không nên viết một bộ quy tắc duy nhất cho tất cả loại client. Hãy định nghĩa registration profile:

**Web confidential profile**

- application_type=web.
- Redirect URI HTTPS nằm trong allowlist/domain đã xác minh.
- grant_types gồm authorization_code, có thể refresh_token.
- response_types chỉ code.
- token_endpoint_auth_method là phương thức confidential được server hỗ trợ.
- PKCE được yêu cầu theo policy.

**SPA/native public profile**

- application_type phù hợp loại ứng dụng.
- token_endpoint_auth_method=none.
- Authorization Code + PKCE.
- Redirect URI theo web/native rules.
- Không cấp client secret.
- Không cấp client_credentials.

**Machine-to-machine profile**

- grant_types chỉ client_credentials hoặc grant M2M được phê duyệt.
- Confidential client authentication.
- Không đăng ký redirect URI nếu không có authorization redirect flow.
- Không yêu cầu response_type code.
- Scope chỉ gồm API permissions cần thiết.

## 9. Spring Authorization Server 1.5.8 hỗ trợ Dynamic Client Registration

Spring Authorization Server 1.5.8 triển khai **OpenID Connect 1.0 Client Registration Endpoint**. Endpoint này **bị tắt mặc định** vì nhiều deployment không cần dynamic registration.

Endpoint mặc định:

~~~text
POST /connect/register
GET  {registration_client_uri}
~~~

Đường dẫn Client Registration Endpoint có thể thay đổi bằng:

~~~java
AuthorizationServerSettings.builder()
        .oidcClientRegistrationEndpoint("/connect/register")
        .build();
~~~

Đây là OIDC Client Registration Endpoint. Hãy bật OIDC support và Client Registration Endpoint riêng; chỉ gọi oidc(Customizer.withDefaults()) chưa đủ để bật endpoint đăng ký client vì endpoint này mặc định disabled.

### 9.1. Bật Client Registration Endpoint

Ví dụ cấu hình:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.server.authorization.config.annotation.web.configurers.OAuth2AuthorizationServerConfigurer;
import org.springframework.security.web.SecurityFilterChain;

@Configuration(proxyBeanMethods = false)
class AuthorizationServerSecurityConfiguration {

    @Bean
    @Order(1)
    SecurityFilterChain authorizationServerSecurityFilterChain(HttpSecurity http)
            throws Exception {

        OAuth2AuthorizationServerConfigurer authorizationServerConfigurer =
                OAuth2AuthorizationServerConfigurer.authorizationServer();

        http.securityMatcher(authorizationServerConfigurer.getEndpointsMatcher())
            .with(authorizationServerConfigurer, authorizationServer ->
                authorizationServer.oidc(oidc ->
                    oidc.clientRegistrationEndpoint(Customizer.withDefaults())
                )
            )
            .authorizeHttpRequests(authorize ->
                authorize.anyRequest().authenticated()
            );

        return http.build();
    }
}
~~~

Đây là phần filter chain minh họa. Ứng dụng hoàn chỉnh còn cần RegisteredClientRepository, OAuth2AuthorizationService, OAuth2TokenGenerator, JWKSource, các SecurityFilterChain khác và authentication/authorization policy phù hợp.

### 9.2. JwtDecoder là bean bắt buộc cho endpoint này

Spring Authorization Server yêu cầu JwtDecoder để xác minh Initial Access Token được gửi dưới dạng Bearer token:

~~~java
import com.nimbusds.jose.jwk.source.JWKSource;
import com.nimbusds.jose.proc.SecurityContext;
import org.springframework.context.annotation.Bean;
import org.springframework.security.oauth2.server.authorization.config.annotation.web.configuration.OAuth2AuthorizationServerConfiguration;
import org.springframework.security.oauth2.jwt.JwtDecoder;

@Bean
JwtDecoder jwtDecoder(JWKSource<SecurityContext> jwkSource) {
    return OAuth2AuthorizationServerConfiguration.jwtDecoder(jwkSource);
}
~~~

JWKSource phải được cấu hình bằng signing keys đáng tin. Không dùng một decoder không xác minh signature/issuer chỉ để cho registration endpoint hoạt động.

### 9.3. AuthorizationServerSettings

Ví dụ cấu hình endpoint:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.server.authorization.settings.AuthorizationServerSettings;

@Configuration(proxyBeanMethods = false)
class AuthorizationServerSettingsConfiguration {

    @Bean
    AuthorizationServerSettings authorizationServerSettings() {
        return AuthorizationServerSettings.builder()
                .issuer("https://login.example.com")
                .oidcClientRegistrationEndpoint("/connect/register")
                .build();
    }
}
~~~

Nếu đổi path, cần cập nhật discovery metadata, ingress routing, registrar WebClient và các integration test.

## 10. Registrar client và Initial Access Token

Spring Authorization Server dùng một client đã được đăng ký làm **registrar**. Registrar cần quyền client.create để tạo client mới và có thể có client.read để truy vấn registration theo cấu hình.

Ví dụ registrar:

~~~java
import java.util.UUID;

import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.ClientAuthenticationMethod;
import org.springframework.security.oauth2.server.authorization.client.RegisteredClient;

RegisteredClient registrar = RegisteredClient.withId(UUID.randomUUID().toString())
        .clientId("registration-service")
        .clientSecret(passwordEncoder.encode(registrarSecret))
        .clientAuthenticationMethod(ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
        .authorizationGrantType(AuthorizationGrantType.CLIENT_CREDENTIALS)
        .scope("client.create")
        .scope("client.read")
        .build();
~~~

Đây là ví dụ; passwordEncoder và registrarSecret phải được cấp từ secret manager. Không dùng {noop} cho secret production.

### 10.1. Xin Initial Access Token

Registrar xác thực tại Token Endpoint:

~~~http
POST /oauth2/token HTTP/1.1
Host: login.example.com
Authorization: Basic <base64-client-id-and-secret>
Content-Type: application/x-www-form-urlencoded

grant_type=client_credentials&scope=client.create
~~~

Theo hướng dẫn Spring Authorization Server 1.5.8, Initial Access Token cho request registration phải có đúng scope client.create; nếu token chứa thêm scope, registration request bị từ chối.

### 10.2. Initial Access Token khác Registration Access Token

| Token | Được dùng để làm gì? | Phạm vi |
| --- | --- | --- |
| Initial Access Token (IAT) | Cho phép registrar tạo client | Quyền registration được cấp trước |
| Registration Access Token (RAT) | Truy cập Client Configuration Endpoint của một client đã tạo | Gắn với một registration cụ thể |
| Access Token thông thường | Gọi Resource Server | Theo scope/resource được cấp |

Trong Spring Authorization Server guide, Initial Access Token chỉ dùng một lần; sau khi client được đăng ký, token đó bị invalidated. Registration Access Token được trả về trong Client Registration Response và dùng để đọc thông tin registration tương ứng.

### 10.3. Bảo vệ registrar

- Chỉ cấp client.create cho service/administrator được phê duyệt.
- Không cấp client.create cho mọi ứng dụng thông thường.
- Giới hạn số lượng registration theo tenant/registrar.
- Đặt expiry ngắn cho Initial Access Token.
- Hỗ trợ revoke/rotate credential của registrar.
- Ghi audit người hoặc service đã tạo client.
- Không ghi Bearer token vào log.

## 11. Gửi Client Registration Request

Ví dụ registration request cho web confidential client:

~~~http
POST /connect/register HTTP/1.1
Host: login.example.com
Authorization: Bearer <initial-access-token>
Content-Type: application/json
Accept: application/json

{
  "client_name": "Orders Partner Portal",
  "application_type": "web",
  "redirect_uris": [
    "https://partner.example.com/oauth/callback"
  ],
  "grant_types": [
    "authorization_code",
    "refresh_token"
  ],
  "response_types": [
    "code"
  ],
  "token_endpoint_auth_method": "client_secret_basic",
  "scope": "openid profile orders.read"
}
~~~

Nếu metadata vượt qua authentication validator và các kiểm tra của provider, server chuyển thành RegisteredClient và lưu trong RegisteredClientRepository.

### 11.1. Client Registration Response

Response có thể chứa:

~~~json
{
  "client_id": "generated-client-id",
  "client_id_issued_at": 1794850000,
  "client_secret": "generated-secret",
  "client_secret_expires_at": 0,
  "client_name": "Orders Partner Portal",
  "redirect_uris": [
    "https://partner.example.com/oauth/callback"
  ],
  "grant_types": [
    "authorization_code",
    "refresh_token"
  ],
  "response_types": [
    "code"
  ],
  "token_endpoint_auth_method": "client_secret_basic",
  "registration_access_token": "registration-management-token",
  "registration_client_uri": "https://login.example.com/connect/register/client-id"
}
~~~

Đây là response minh họa; client_id, secret, timestamps và registration URL do server sinh. Không hard-code hoặc dự đoán giá trị của server. Vì response có thể chứa client credential và Registration Access Token, cần trả với cache policy không lưu (ví dụ Cache-Control: no-store) và không ghi body vào log.

### 11.2. Bảo vệ client secret trong cả Registration và Client Read

Với confidential client dùng client_secret_basic, Authorization Server sinh secret. Client cần lưu ngay thông tin credential được cấp vào secret manager. Không ghi secret vào application log, ticket, browser local storage hoặc source control.

Không giả định Client Read Response luôn loại bỏ client_secret. OIDC Dynamic Client Registration 1.0 yêu cầu response đọc SHOULD chứa metadata đã đăng ký; tài liệu Spring Authorization Server 1.5.8 cũng minh họa Client Read Response có client_secret. Vì vậy, Registration Access Token và Client Configuration Endpoint phải được bảo vệ như credential có thể đọc thông tin nhạy cảm. Giá trị secret trả về trong một triển khai cụ thể có thể phản ánh cách server lưu/encode secret; hãy kiểm tra converter và PasswordEncoder trước khi coi chuỗi đó là credential có thể dùng trực tiếp.

Nếu secret bị mất hoặc nghi bị lộ, dùng quy trình rotate/re-register hoặc cập nhật registration được triển khai, sau đó thu hồi credential cũ và đánh giá các token đã cấp.

### 11.3. Đọc registration

Khi server cấp Client Configuration Endpoint, Registration Response trả cả registration_access_token và registration_client_uri. OIDC DCR yêu cầu server cung cấp cả hai hoặc không cung cấp cả hai. Registrar phải dùng nguyên URI server cung cấp để đọc registration, không tự ghép path hoặc client_id:

~~~http
GET <registration-client-uri> HTTP/1.1
Authorization: Bearer <registration-access-token>
Accept: application/json
~~~

Spring Authorization Server yêu cầu scope client.read cho Client Read Request theo cấu hình registrar. Không dùng Initial Access Token thay Registration Access Token để truy cập registration đã tạo.

## 12. Custom metadata và converter

RFC 7591 cho phép mở rộng client metadata theo registry/profile. Spring Authorization Server chuyển đổi OidcClientRegistration thành RegisteredClient thông qua converter.

Một số field có sẵn được ánh xạ vào RegisteredClient, ví dụ:

- client_id
- client_secret
- redirect_uris
- grant_types
- token_endpoint_auth_method
- scope
- jwks_uri
- các ClientSettings tương ứng

Nếu muốn lưu custom metadata như logo_uri, contacts, tenant_code hoặc onboarding_reference, cần:

1. Chỉ định metadata extension được chấp nhận.
2. Validate giá trị và nguồn dữ liệu.
3. Dùng RegisteredClient converter để lưu vào ClientSettings hoặc kho metadata riêng.
4. Dùng Client Registration converter để trả lại metadata khi client đọc registration.
5. Không tự động lưu mọi claim không rõ nguồn gốc vào client settings.

Theo RFC 7591, Authorization Server MUST ignore metadata không nhận biết. Chỉ xử lý extension khi đã triển khai profile/registry tương ứng; không tự lưu mọi field lạ từ request.

Spring Authorization Server guide minh họa custom converters cho OidcClientRegistrationAuthenticationProvider và OidcClientConfigurationAuthenticationProvider. Custom metadata không tự được giữ lại nếu converter không ánh xạ.

## 13. Cấu hình validator trong Spring Authorization Server

### 13.1. Default validator của phiên bản 1.5.8

OidcClientRegistrationAuthenticationValidator cung cấp các validator:

| Validator | Mục đích |
| --- | --- |
| DEFAULT_REDIRECT_URI_VALIDATOR | Từ chối redirect URI có fragment, thiếu scheme hoặc scheme nguy hiểm |
| DEFAULT_POST_LOGOUT_REDIRECT_URI_VALIDATOR | Áp dụng quy tắc tương tự cho post-logout redirect URI |
| DEFAULT_JWK_SET_URI_VALIDATOR | Yêu cầu jwks_uri dùng HTTPS |
| DEFAULT_SCOPE_VALIDATOR | Strict: từ chối request có scope không rỗng |
| SIMPLE_REDIRECT_URI_VALIDATOR | Chỉ giữ kiểm tra fragment theo behavior cũ; có thể nhận giá trị nguy hiểm |
| SIMPLE_JWK_SET_URI_VALIDATOR | Không validation URI; có thể mở SSRF |
| SIMPLE_SCOPE_VALIDATOR | Chấp nhận mọi scope; có thể mở arbitrary scope injection |

Default validator không thay thế toàn bộ policy của doanh nghiệp. Đặc biệt, cần kiểm tra thêm grant_types, response_types, token_endpoint_auth_method, application_type, redirect domain ownership, scope allowlist và quota.

**Không dùng SIMPLE_SCOPE_VALIDATOR một mình trong production.** Nếu cần nhận scope, hãy viết allowlist validator riêng. Cũng không hạ strict redirect/JWKS validator chỉ để tương thích dữ liệu cũ mà chưa đánh giá rủi ro.

### 13.2. Validator bổ sung cho web Authorization Code client

Ví dụ dưới đây minh họa một profile registration chỉ cho phép:

- Web redirect URI nằm trong allowlist chính xác.
- authorization_code và refresh_token.
- response_type code.
- client_secret_basic hoặc none.
- Scope nằm trong allowlist.

Profile minh họa này yêu cầu scope được gửi tường minh, dù OIDC DCR cho phép bỏ qua scope và để OP áp dụng default. Chính sách yêu cầu explicit giúp tránh vô tình cấp một tập scope mặc định rộng hơn dự kiến.

~~~java
import java.util.List;
import java.util.Set;
import java.util.function.Consumer;

import org.springframework.security.oauth2.core.OAuth2AuthenticationException;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.server.authorization.oidc.OidcClientRegistration;
import org.springframework.security.oauth2.server.authorization.oidc.authentication.OidcClientRegistrationAuthenticationContext;
import org.springframework.security.oauth2.server.authorization.oidc.authentication.OidcClientRegistrationAuthenticationToken;

final class WebClientRegistrationPolicy {

    private static final Set<String> APPROVED_REDIRECT_URIS = Set.of(
            "https://partner.example.com/oauth/callback",
            "https://portal.example.com/login/oauth2/code/partner"
    );

    private static final Set<String> ALLOWED_GRANTS = Set.of(
            "authorization_code",
            "refresh_token"
    );

    private static final Set<String> ALLOWED_RESPONSE_TYPES = Set.of("code");

    private static final Set<String> ALLOWED_AUTH_METHODS = Set.of(
            "client_secret_basic",
            "none"
    );

    private static final Set<String> ALLOWED_SCOPES = Set.of(
            "openid",
            "profile",
            "email",
            "orders.read"
    );

    static Consumer<OidcClientRegistrationAuthenticationContext> validator() {
        return context -> {
            OidcClientRegistrationAuthenticationToken authentication =
                    context.getAuthentication();
            OidcClientRegistration registration =
                    authentication.getClientRegistration();

            if (registration == null) {
                reject("Client registration metadata is missing");
            }

            String applicationType = registration.getClaimAsString("application_type");
            if (applicationType != null && !"web".equals(applicationType)) {
                reject("This registration profile only accepts web clients");
            }

            if (registration.getClientId() != null
                    || registration.getClientSecret() != null) {
                reject("client_id and client_secret are issued by the server");
            }

            if (registration.getJwkSetUrl() != null || registration.hasClaim("jwks")) {
                reject("This profile does not accept client JWKS metadata");
            }

            List<String> redirectUris = registration.getRedirectUris();
            if (redirectUris == null || redirectUris.isEmpty()
                    || new java.util.HashSet<>(redirectUris).size() != redirectUris.size()
                    || !APPROVED_REDIRECT_URIS.containsAll(redirectUris)) {
                reject("redirect_uris is not approved");
            }

            List<String> grantTypes = registration.getGrantTypes();
            if (grantTypes == null || grantTypes.isEmpty()) {
                // OIDC DCR defaults grant_types to authorization_code.
                grantTypes = List.of("authorization_code");
            }
            if (!grantTypes.contains("authorization_code")
                    || new java.util.HashSet<>(grantTypes).size() != grantTypes.size()
                    || !ALLOWED_GRANTS.containsAll(grantTypes)) {
                reject("grant_types is not allowed");
            }

            List<String> responseTypes = registration.getResponseTypes();
            if (responseTypes == null || responseTypes.isEmpty()) {
                // OIDC DCR defaults response_types to code.
                responseTypes = List.of("code");
            }
            if (!responseTypes.equals(List.of("code"))
                    || !ALLOWED_RESPONSE_TYPES.containsAll(responseTypes)) {
                reject("response_types is not supported");
            }

            String authMethod =
                    registration.getTokenEndpointAuthenticationMethod();
            if (authMethod == null) {
                // OIDC Dynamic Client Registration defaults to client_secret_basic.
                authMethod = "client_secret_basic";
            }
            if (!ALLOWED_AUTH_METHODS.contains(authMethod)) {
                reject("token_endpoint_auth_method is not allowed");
            }

            List<String> scopes = registration.getScopes();
            if (scopes == null || scopes.isEmpty()
                    || new java.util.HashSet<>(scopes).size() != scopes.size()
                    || !ALLOWED_SCOPES.containsAll(scopes)) {
                reject("scope is missing, duplicated, or outside the allowlist");
            }
        };
    }

    private static void reject(String description) {
        throw new OAuth2AuthenticationException(
                new OAuth2Error("invalid_client_metadata", description, null));
    }

    private WebClientRegistrationPolicy() {
    }
}
~~~

Đây là validator mẫu cho một profile web có redirect URI cố định, không nhận client JWKS và chỉ cho phép client_secret_basic hoặc none. Hệ thống có nhiều khách hàng phải thay tập URI tĩnh bằng domain ownership registry hoặc quy trình phê duyệt tương ứng. Không dùng profile này cho native app hoặc machine-to-machine client. Nếu tách SPA và web backend thành hai profile, hãy đặt validator riêng để SPA chỉ được đăng ký none; application_type=web tự nó không phân biệt SPA với server-side web app.

### 13.3. Ghép validator với strict validators mặc định

Ví dụ cấu hình provider:

~~~java
import java.util.List;
import java.util.function.Consumer;

import org.springframework.context.annotation.Bean;
import org.springframework.security.authentication.AuthenticationProvider;
import org.springframework.security.oauth2.server.authorization.oidc.authentication.OidcClientRegistrationAuthenticationContext;
import org.springframework.security.oauth2.server.authorization.oidc.authentication.OidcClientRegistrationAuthenticationProvider;
import org.springframework.security.oauth2.server.authorization.oidc.authentication.OidcClientRegistrationAuthenticationValidator;

@Bean
Consumer<List<AuthenticationProvider>> registrationProviderCustomizer(
        PkceRegisteredClientConverter pkceRegisteredClientConverter) {
    return providers -> providers.forEach(provider -> {
            if (provider instanceof OidcClientRegistrationAuthenticationProvider registrationProvider) {
                Consumer<OidcClientRegistrationAuthenticationContext> validator =
                        OidcClientRegistrationAuthenticationValidator.DEFAULT_REDIRECT_URI_VALIDATOR
                                .andThen(OidcClientRegistrationAuthenticationValidator.DEFAULT_POST_LOGOUT_REDIRECT_URI_VALIDATOR)
                                .andThen(OidcClientRegistrationAuthenticationValidator.DEFAULT_JWK_SET_URI_VALIDATOR)
                                .andThen(WebClientRegistrationPolicy.validator());

                registrationProvider.setAuthenticationValidator(validator);
                // pkceRegisteredClientConverter is an application bean that
                // wraps the default converter and enforces PKCE for code clients.
                registrationProvider.setRegisteredClientConverter(
                        pkceRegisteredClientConverter::convert);
            }
        });
}
~~~

Đặt method trên trong class cấu hình Spring và khai báo PkceRegisteredClientConverter như bean. Validator custom thay thế validator mặc định của provider, vì vậy phải chain lại những kiểm tra strict cần thiết. Ví dụ trên tự kiểm tra scopes bằng allowlist và không gọi SIMPLE_SCOPE_VALIDATOR. Nếu ứng dụng hỗ trợ post_logout_redirect_uris hoặc jwks_uri, giữ validator tương ứng và bổ sung policy riêng cho những metadata đó.

### 13.4. Cấu hình provider vào endpoint

Ghép customizer vào OIDC Client Registration Endpoint:

~~~java
authorizationServerConfigurer.oidc(oidc ->
    oidc.clientRegistrationEndpoint(endpoint ->
        endpoint.authenticationProviders(registrationProviderCustomizer)
    )
);
~~~

Đây là đoạn ghép vào Authorization Server SecurityFilterChain đã tạo ở mục 9. Không đăng ký customizer cho provider nếu chưa có test xác minh validator chạy trước khi RegisteredClient được lưu.

## 14. Đảm bảo PKCE và chuyển metadata thành RegisteredClient

### 14.1. Public client phải dùng PKCE

Với client dùng token_endpoint_auth_method=none, Authorization Server không có client secret để xác thực tại Token Endpoint. Với Authorization Code Flow, PKCE là biện pháp quan trọng để chống code interception.

Trong Spring Authorization Server, RegisteredClient có ClientSettings.requireProofKey(true). Khi DCR tạo public client, cần bảo đảm converter đặt thuộc tính này:

Ví dụ converter được inject vào registration provider customizer ở mục 13.3. Converter giữ nguyên metadata đã được ánh xạ mặc định, sau đó đặt requireProofKey cho Authorization Code client:

~~~java
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.core.convert.converter.Converter;
import org.springframework.security.oauth2.server.authorization.client.RegisteredClient;
import org.springframework.security.oauth2.server.authorization.oidc.OidcClientRegistration;
import org.springframework.security.oauth2.server.authorization.oidc.converter.OidcClientRegistrationRegisteredClientConverter;
import org.springframework.security.oauth2.server.authorization.settings.ClientSettings;

final class PkceRegisteredClientConverter
        implements Converter<OidcClientRegistration, RegisteredClient> {

    private final OidcClientRegistrationRegisteredClientConverter delegate =
            new OidcClientRegistrationRegisteredClientConverter();

    @Override
    public RegisteredClient convert(OidcClientRegistration registration) {
        RegisteredClient registeredClient = delegate.convert(registration);

        boolean authorizationCodeClient = registeredClient.getAuthorizationGrantTypes()
                .contains(AuthorizationGrantType.AUTHORIZATION_CODE);

        ClientSettings settings = ClientSettings.withSettings(
                registeredClient.getClientSettings().getSettings())
                .requireProofKey(authorizationCodeClient)
                .build();

        return RegisteredClient.from(registeredClient)
                .clientSettings(settings)
                .build();
    }
}
~~~

Đăng ký lớp converter thành bean hoặc khởi tạo trong cấu hình rồi inject vào customizer. Ví dụ trên yêu cầu PKCE cho mọi client có Authorization Code grant, bao gồm cả public và confidential client; public client vẫn dùng ClientAuthenticationMethod.NONE và không có client secret.

Ví dụ khai báo bean:

~~~java
import org.springframework.context.annotation.Bean;

@Bean
PkceRegisteredClientConverter pkceRegisteredClientConverter() {
    return new PkceRegisteredClientConverter();
}
~~~

### 14.2. RegisteredClientRepository là nơi lưu registration

RegisteredClientRepository là thành phần trung tâm để lưu và truy vấn RegisteredClient. Spring Authorization Server cung cấp:

- InMemoryRegisteredClientRepository: dùng trong development/test.
- JdbcRegisteredClientRepository: lưu bền vững qua JDBC.

Production nên dùng repository bền vững, transaction và backup phù hợp. Cần bảo đảm client_id duy nhất, ID nội bộ ổn định và client settings không bị mất khi restart.

### 14.3. Metadata và RegisteredClient không hoàn toàn là một cấu trúc

OIDC Client Registration có các field protocol metadata như response_types, application_type, logo_uri và contacts. RegisteredClient lưu các thuộc tính cần cho việc xử lý OAuth tại Spring Authorization Server. Những metadata không có field tương ứng cần được lưu qua ClientSettings hoặc một metadata store riêng.

Đừng cho rằng converter mặc định sẽ giữ mọi metadata extension. Nếu cần trả metadata khi Client Read, phải cấu hình cả RegisteredClient-to-OidcClientRegistration converter.

## 15. Các lớp bảo vệ DCR

### 15.1. Bảo vệ Registration Endpoint

- Bắt buộc HTTPS.
- Yêu cầu Initial Access Token hoặc một phương thức registrar authentication được phê duyệt.
- Chỉ registrar có client.create mới được tạo client.
- Giới hạn số lượng registration, tốc độ request và kích thước JSON body.
- Audit tenant, registrar, thời gian, client metadata và kết quả validation.
- Không trả thông tin nội bộ hoặc stack trace trong lỗi.

### 15.2. Chống redirect hijacking

- Exact redirect URI matching tại Authorization Endpoint.
- Không chấp nhận wildcard hoặc regex phức tạp nếu không có threat model đặc biệt.
- Web callback phải HTTPS.
- Native loopback exception chỉ theo RFC 8252.
- Kiểm tra open redirector ở ứng dụng client.
- Không cho registrar tự đăng ký callback sang domain chưa xác minh.

### 15.3. Chống scope escalation

Scope là policy của Authorization Server, không phải thuộc tính client được quyền tự chọn. Áp allowlist theo registrar/tenant/client profile. Nếu cần scope đặc quyền, phải có approval hoặc software statement đáng tin cậy.

### 15.4. Chống SSRF qua jwks_uri

Nếu server fetch jwks_uri:

1. Chỉ chấp nhận HTTPS.
2. Kiểm tra host theo policy và chặn localhost/private/link-local/metadata service.
3. Xử lý DNS rebinding và redirect an toàn.
4. Giới hạn connect/read timeout, response size và số key.
5. Chỉ chấp nhận JSON JWK Set đúng schema.
6. Không tải private/symmetric keys.
7. Có cache/rotation policy và cơ chế vô hiệu hóa key bị compromise.

Default validator của SAS kiểm tra scheme HTTPS cho jwks_uri; đó chưa phải toàn bộ SSRF defense. Policy network egress và URL validation cần bổ sung theo môi trường.

### 15.5. Chống đăng ký giả mạo và software statement

RFC 7591 cho phép software statement được ký bởi issuer đáng tin để chứng minh metadata về phần mềm client. Nếu sử dụng:

- Chỉ tin issuer đã được cấu hình.
- Software statement phải được ký hoặc MAC theo chuẩn, có iss và được xác minh chữ ký, issuer, thời hạn, audience cùng các claim liên quan.
- Metadata từ software statement đáng tin phải có ưu tiên theo quy tắc chuẩn.
- Không chấp nhận software statement chỉ vì payload decode được.

Software statement không thay thế mọi validation redirect URI, grant và authentication method. Không giả định OIDC Client Registration Endpoint mặc định của Spring Authorization Server tự xác minh software_statement; nếu triển khai tính năng này, phải bổ sung converter/validator và trust registry riêng.

### 15.6. Quản lý credential sau đăng ký

- Client secret phải được sinh ngẫu nhiên, đủ entropy và encode bằng PasswordEncoder.
- Client Read Response có thể chứa metadata client_secret; chỉ registrar có Registration Access Token hợp lệ mới được đọc registration.
- Registration Access Token là bearer credential quản lý registration; bảo vệ như secret.
- Hỗ trợ thu hồi/rotate secret và registration token theo quy trình.
- Khi client bị xâm phạm, disable client và revoke authorization/token liên quan.

## 16. Ví dụ request đăng ký và kiểm tra

### 16.1. Web confidential client hợp lệ

~~~json
{
  "client_name": "Billing Partner",
  "application_type": "web",
  "redirect_uris": [
    "https://billing.partner.example/callback"
  ],
  "grant_types": [
    "authorization_code",
    "refresh_token"
  ],
  "response_types": [
    "code"
  ],
  "token_endpoint_auth_method": "client_secret_basic",
  "scope": "openid profile billing.read"
}
~~~

Chỉ chấp nhận nếu callback đã được phê duyệt, scope nằm trong allowlist và server hỗ trợ các grant/method này.

### 16.2. Public SPA hợp lệ

~~~json
{
  "client_name": "Customer SPA",
  "application_type": "web",
  "redirect_uris": [
    "https://app.customer.example/oauth/callback"
  ],
  "grant_types": [
    "authorization_code"
  ],
  "response_types": [
    "code"
  ],
  "token_endpoint_auth_method": "none",
  "scope": "openid profile"
}
~~~

SPA phải được cấu hình PKCE bắt buộc và không được phát client secret.

### 16.3. Registration cần từ chối: wildcard redirect

~~~json
{
  "redirect_uris": [
    "https://*.partner.example/callback"
  ],
  "grant_types": [
    "authorization_code"
  ],
  "response_types": [
    "code"
  ],
  "token_endpoint_auth_method": "client_secret_basic"
}
~~~

Wildcard làm ranh giới callback khó xác minh và có thể cho phép subdomain takeover. Yêu cầu đăng ký URI cụ thể.

### 16.4. Registration cần từ chối: response/grant mismatch

Ví dụ sau minh họa validator cho OAuth DCR tổng quát theo RFC 7591. OIDC DCR của Spring Authorization Server cần tuân theo tập grant/response của OIDC Registration; không dùng ví dụ này để kết luận endpoint OIDC mặc định nhận client_credentials.

~~~json
{
  "redirect_uris": [
    "https://partner.example.com/callback"
  ],
  "grant_types": [
    "client_credentials"
  ],
  "response_types": [
    "code"
  ],
  "token_endpoint_auth_method": "client_secret_basic"
}
~~~

client_credentials không tạo response_type code. Registrar phải chọn một profile phù hợp thay vì trộn M2M và browser flow.

### 16.5. Registration cần từ chối: public client dùng grant không phù hợp

Ví dụ này cũng thuộc OAuth DCR tổng quát theo RFC 7591; nó minh họa policy client type/grant, không phải request OIDC DCR tương thích với endpoint SAS mặc định.

~~~json
{
  "application_type": "web",
  "redirect_uris": [
    "https://spa.example.com/callback"
  ],
  "grant_types": [
    "client_credentials"
  ],
  "token_endpoint_auth_method": "none"
}
~~~

Public client không có client authentication phù hợp cho client_credentials.

## 17. Kiểm thử Dynamic Client Registration

Kiểm thử cần đi qua endpoint thật trong test context, dùng registrar Access Token đã xác thực và xác minh trạng thái RegisteredClient sau khi request hoàn tất.

### 17.1. Test cấu hình endpoint

Kiểm tra:

- OIDC support đã bật.
- Client Registration Endpoint đã được bật tường minh.
- Metadata discovery có registration_endpoint đúng khi endpoint được công bố.
- JwtDecoder bean có thể xác minh Initial Access Token.
- RegisteredClientRepository có thể lưu và truy vấn client mới.

### 17.2. Test validator redirect URI

Tạo test cho:

- HTTPS callback nằm trong allowlist.
- Callback ngoài allowlist.
- URI có fragment.
- URI không có scheme.
- Scheme javascript/data/vbscript.
- Wildcard host/path.
- Host giả mạo bằng userinfo.
- Native custom scheme không đúng policy.
- Loopback URI với IP literal và port động đúng native profile.
- Loopback URI bị dùng bởi web client.

### 17.3. Test grant/response compatibility

Kiểm tra:

- authorization_code + code.
- authorization_code + refresh_token + code.
- client_credentials không khai báo code response.
- grant_types không được server hỗ trợ.
- response_types implicit/hybrid bị từ chối nếu server không hỗ trợ.
- password grant bị từ chối theo policy.
- response_type code nhưng thiếu authorization_code.
- response_type token nhưng thiếu implicit hoặc server không hỗ trợ implicit (trường hợp OAuth DCR tổng quát theo RFC 7591).

### 17.4. Test authentication method

Kiểm tra:

- client_secret_basic được phép và secret được sinh.
- none không sinh secret và PKCE được bắt buộc.
- client_secret_post bị từ chối nếu policy không cho phép.
- private_key_jwt thiếu jwks_uri bị từ chối.
- jwks_uri HTTP bị từ chối.
- TLS method bị từ chối nếu server chưa bật provider tương ứng.
- Client Read Response không cần trả lại registration_access_token trừ khi giá trị đó được cập nhật; client_secret có thể xuất hiện theo metadata đã đăng ký.

## 18. Ma trận kiểm thử đầy đủ

| # | Tình huống | Kết quả mong đợi |
| --- | --- | --- |
| 1 | Registrar có client.create hợp lệ | Được phép gửi registration |
| 2 | Không có Bearer token | 401 |
| 3 | Token không có client.create | 403 hoặc OAuth error tương ứng |
| 4 | Token có client.create và scope thừa theo policy SAS | Bị từ chối |
| 5 | Initial Access Token đã dùng | Request đăng ký tiếp theo bị từ chối |
| 6 | redirect_uris HTTPS exact allowlist | Chấp nhận |
| 7 | redirect URI ngoài allowlist | invalid_client_metadata |
| 8 | redirect URI có fragment | Từ chối |
| 9 | redirect URI dùng javascript/data | Từ chối |
| 10 | wildcard redirect URI | Từ chối |
| 11 | Host giả bằng userinfo | Từ chối |
| 12 | Native loopback IP với port động | Chấp nhận theo native policy |
| 13 | Native loopback port ngoại lệ áp dụng cho web client | Từ chối |
| 14 | authorization_code + code | Chấp nhận |
| 15 | client_credentials + code | Từ chối |
| 16 | response_type không được server hỗ trợ | Từ chối |
| 17 | implicit hoặc password grant | Từ chối theo policy |
| 18 | token_endpoint_auth_method=none cho SPA + PKCE | Chấp nhận |
| 19 | token_endpoint_auth_method=none nhưng yêu cầu client_credentials | Từ chối |
| 20 | client_secret_basic | Chấp nhận nếu policy cho phép; secret được sinh |
| 21 | private_key_jwt thiếu JWKS | Từ chối |
| 22 | jwks_uri không dùng HTTPS | Từ chối |
| 23 | jwks_uri trỏ private IP/metadata endpoint | Bị chặn bởi SSRF/network policy |
| 24 | scope chứa admin không được cấp | Từ chối |
| 25 | Metadata extension không được hỗ trợ | Bỏ qua hoặc xử lý theo RFC/profile, không tự lưu |
| 26 | Client Registration thành công | Trả client_id và metadata đã được chấp thuận |
| 27 | Client Read bằng registration_access_token | Trả registration tương ứng |
| 28 | Client Read không có client.read/registration token hợp lệ | Bị từ chối |
| 29 | Response Client Read | Không trả registration_access_token nếu không cập nhật; bảo vệ client_secret nếu response có trường này |
| 30 | Hai registration đồng thời có cùng callback nhưng client_id khác | Mỗi client được lưu riêng, callback policy vẫn được áp dụng |
| 31 | Registrar vượt quota | Bị rate-limit hoặc từ chối |
| 32 | DB lỗi khi lưu RegisteredClient | Không trả response thành công giả |
| 33 | Scope bị bỏ qua trong web profile yêu cầu explicit scope | Từ chối |
| 34 | application_type=native gửi vào web-only validator | Từ chối |
| 35 | Request tự gửi client_id hoặc client_secret | Từ chối; server tự phát hành giá trị |
| 36 | Request gửi đồng thời jwks và jwks_uri hoặc profile không cho client JWKS | Từ chối |

## 19. Chẩn đoán lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| /connect/register trả 404 | Endpoint chưa bật hoặc path sai | Kiểm tra oidc.clientRegistrationEndpoint và AuthorizationServerSettings |
| 401 ở registration endpoint | Initial Access Token thiếu/sai chữ ký/issuer | Kiểm tra JwtDecoder và Bearer token |
| insufficient_scope/client.create | Registrar token không có scope bắt buộc | Cấp token đúng scope client.create |
| invalid_client_metadata | Redirect/scope/grant/auth method không qua validator | Kiểm tra metadata và validator chain |
| Redirect hợp lệ nhưng bị từ chối | Strict validator hoặc allowlist chưa cập nhật | Kiểm tra exact URI và profile |
| Client đăng ký thành công nhưng authorization request bị từ chối | grant/response type hoặc redirect không khớp | Kiểm tra RegisteredClient và Authorization Request |
| Client public bị yêu cầu secret | token_endpoint_auth_method không phải none hoặc converter sai | Kiểm tra metadata/converter |
| Public client không bị yêu cầu PKCE | ClientSettings.requireProofKey chưa bật | Sửa RegisteredClient converter/policy |
| Client Read trả thiếu custom metadata | Converter không map metadata extension | Cấu hình cả hai chiều converter |
| Registration token bị từ chối khi đọc | Dùng nhầm Initial Access Token thay Registration Access Token | Dùng registration_access_token trong response |
| JWKS fetch timeout | DNS/network/SSRF policy hoặc server client JWKS lỗi | Kiểm tra URL, timeout, outbound policy |
| Scope bất kỳ được lưu | Dùng SIMPLE_SCOPE_VALIDATOR không có allowlist | Dùng custom scope validator |
| Một client đăng ký nhiều lần không kiểm soát | Không có quota/idempotency/onboarding policy | Thêm rate limit và registrar ownership |

## 20. Vận hành, audit và vòng đời registration

### 20.1. Audit event

Nên ghi:

- Registrar identity/client ID.
- Tenant/organization.
- Registration operation và thời điểm.
- Client ID mới.
- Grant types, response types và auth method được chấp thuận.
- Số lượng redirect URI và scope đã cấp.
- Validation policy version.
- Kết quả thành công/thất bại và error code.

Không ghi client_secret, Initial Access Token, Registration Access Token hoặc private key vào audit log.

### 20.2. Quản lý thay đổi metadata

Khi client cần đổi redirect URI, grant hoặc authentication method:

1. Xác thực Registration Access Token hoặc admin identity.
2. Kiểm tra quyền quản lý đúng client.
3. Chạy lại toàn bộ validator, không chỉ validate field thay đổi.
4. Kiểm tra grant/response/auth method consistency.
5. Audit giá trị cũ và mới theo chính sách bảo vệ dữ liệu.
6. Lưu registration trong transaction.
7. Kiểm thử client cũ không còn dùng redirect hoặc method đã bị gỡ.

Không cho client thay đổi metadata bảo mật bằng endpoint không yêu cầu xác thực.

### 20.3. Thu hồi registration

Khi client bị xâm phạm hoặc không còn được sử dụng:

- Disable hoặc xóa RegisteredClient theo quy trình.
- Thu hồi Registration Access Token.
- Rotate/revoke client secret hoặc certificate.
- Thu hồi authorization/token đã cấp nếu policy yêu cầu.
- Xác nhận Resource Server không còn chấp nhận token bị ảnh hưởng theo revocation strategy.
- Lưu audit record và thông tin điều tra.

Xóa registration không tự động bảo đảm JWT đã phát hành biến mất khỏi mọi Resource Server. Cần phối hợp token revocation/introspection/denylist hoặc TTL.

### 20.4. Theo dõi chỉ số

Theo dõi:

- Registration requests theo registrar/tenant.
- Tỷ lệ success và invalid_client_metadata.
- Redirect URI rejection count.
- Grant/auth method rejection count.
- Registration quota usage.
- Initial Access Token consumption.
- Client secret rotation/expiry.
- JWKS fetch error và unknown kid.
- Client registrations không hoạt động hoặc chưa hoàn tất onboarding.

## 21. Checklist triển khai production

1. **Protected registration:** endpoint không mở tùy tiện; yêu cầu Initial Access Token hoặc quy trình phê duyệt.
2. **Registrar scope:** client.create chỉ cấp cho registrar tin cậy; client.read giới hạn đúng nhu cầu.
3. **redirect_uris:** exact allowlist, không wildcard, HTTPS cho web, native exception theo RFC 8252.
4. **grant_types:** chỉ cho phép grant đã triển khai và được policy phê duyệt.
5. **response_types:** kiểm tra ma trận với grant_types và khả năng server.
6. **Authentication method:** public/confidential client chọn đúng method; không cho downgrade.
7. **PKCE:** bắt buộc cho Authorization Code Flow theo security policy.
8. **Scopes:** allowlist theo tenant/client profile; không dùng validator chấp nhận mọi scope.
9. **JWKS:** HTTPS, public key only, chống SSRF và có key rotation.
10. **Secrets:** secret sinh từ server, lưu secret manager, không log.
11. **Registration token:** Initial Access Token và Registration Access Token có vòng đời và quyền riêng.
12. **Persistence:** RegisteredClientRepository bền vững; InMemory chỉ dành dev/test.
13. **Custom metadata:** converter hai chiều và allowlist rõ.
14. **Validation:** strict validator mặc định được giữ; custom policy bổ sung grant/response/auth method.
15. **Abuse protection:** rate limit, quota, registrar audit và domain verification.
16. **Testing:** negative tests cho redirect, scope, grant, response type, auth method và SSRF.
17. **Incident response:** disable client, revoke credentials và xử lý token đã phát hành.

## 22. Bài tập và câu hỏi tự đánh giá

**Bài tập A — Redirect URI.** Một web client đăng ký https://portal.example.com/callback. Hãy viết validator từ chối wildcard, URI fragment, userinfo và domain không được phê duyệt. Giải thích vì sao Authorization Endpoint vẫn cần exact match.

**Bài tập B — Native app.** Một native app dùng loopback callback với port động. Thiết kế policy cho 127.0.0.1 và [::1], giải thích vì sao ngoại lệ port không áp dụng cho web client.

**Bài tập C — Grant/response.** Client gửi grant_types=client_credentials và response_types=code. Viết validation logic từ chối registration và giải thích quan hệ giữa hai trường.

**Bài tập D — Public client.** SPA gửi token_endpoint_auth_method=none. Xác định những cấu hình bổ sung cần có để client dùng Authorization Code + PKCE an toàn.

**Bài tập E — Confidential client.** Một backend service yêu cầu private_key_jwt. Thiết kế validation cho jwks_uri, key use, key rotation và token_endpoint_auth_signing_alg.

**Bài tập F — Spring Authorization Server.** Bật OIDC Client Registration Endpoint, tạo registrar có client.create, cấp Initial Access Token và đăng ký client bằng WebClient.

**Bài tập G — Scope injection.** DCR validator dùng SIMPLE_SCOPE_VALIDATOR. Một registrar gửi scope=admin system.write. Phân tích rủi ro và viết allowlist validator thay thế.

**Bài tập H — Registration takeover.** Registration Access Token bị lộ. Mô tả cách attacker có thể đọc hoặc thay đổi metadata và quy trình revoke/rotate để khắc phục.

**Câu hỏi ôn tập:**

1. RFC 7591 và OIDC Dynamic Client Registration khác nhau ở phạm vi nào?
2. Initial Access Token khác Registration Access Token thế nào?
3. Vì sao DCR endpoint cần protected registrar?
4. redirect_uris phải được kiểm tra ở hai thời điểm nào?
5. Exact matching khác wildcard/prefix matching ra sao?
6. Native loopback port exception áp dụng khi nào?
7. grant_types và response_types có quan hệ thế nào?
8. Vì sao client_credentials không đi với response_type=code?
9. token_endpoint_auth_method=none có nghĩa gì?
10. Vì sao public client cần PKCE?
11. private_key_jwt cần metadata key nào?
12. DEFAULT_SCOPE_VALIDATOR và SIMPLE_SCOPE_VALIDATOR khác nhau ra sao?
13. Vì sao chỉ dùng DEFAULT_REDIRECT_URI_VALIDATOR vẫn chưa đủ policy production?
14. Spring Authorization Server 1.5.8 bật Client Registration Endpoint mặc định hay không?
15. Vì sao endpoint cần JwtDecoder?
16. Custom metadata cần converter theo những chiều nào?
17. Registration Access Token bị lộ có thể gây tác động gì?
18. Xóa RegisteredClient có tự revoke mọi JWT đã phát hành không?

## 23. Tài liệu tham khảo

- [RFC 7591 — OAuth 2.0 Dynamic Client Registration Protocol](https://www.rfc-editor.org/rfc/rfc7591)
- [RFC 7591, Section 2 — Client Metadata](https://www.rfc-editor.org/rfc/rfc7591#section-2)
- [RFC 7591, Section 2.1 — Relationship between Grant Types and Response Types](https://www.rfc-editor.org/rfc/rfc7591#section-2.1)
- [RFC 7592 — OAuth 2.0 Dynamic Client Registration Management Protocol](https://www.rfc-editor.org/rfc/rfc7592)
- [OpenID Connect Dynamic Client Registration 1.0, Errata Set 2](https://openid.net/specs/openid-connect-registration-1_0.html)
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700)
- [RFC 8252 — OAuth 2.0 for Native Apps](https://www.rfc-editor.org/rfc/rfc8252)
- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749)
- [RFC 7636 — Proof Key for Code Exchange by OAuth Public Clients](https://www.rfc-editor.org/rfc/rfc7636)
- [RFC 7517 — JSON Web Key](https://www.rfc-editor.org/rfc/rfc7517)
- [Spring Authorization Server 1.5.8 — How-to: Register a Client Dynamically](https://docs.spring.io/spring-authorization-server/reference/guides/how-to-dynamic-client-registration.html)
- [Spring Authorization Server 1.5.8 — Protocol Endpoints](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html)
- [Spring Authorization Server 1.5.8 — OidcClientRegistrationAuthenticationValidator API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/oidc/authentication/OidcClientRegistrationAuthenticationValidator.html)
- [Spring Authorization Server 1.5.8 — RegisteredClientRepository](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html)
- [Spring Authorization Server 1.5.8 — AuthorizationServerSettings](https://docs.spring.io/spring-authorization-server/reference/configuration-model.html)

**Ghi nhớ:** Dynamic Client Registration tạo ra một client có quyền hoạt động trong Authorization Server. Trước khi lưu RegisteredClient, phải xác minh redirect_uris, grant_types, response_types, token_endpoint_auth_method và scopes như một tập metadata có quan hệ. redirect URI cần exact matching; grant/response phải tương thích và chỉ dùng flow server hỗ trợ; authentication method phải phù hợp public/confidential client và key/secret thực tế. Trong Spring Authorization Server 1.5.8, OIDC Client Registration Endpoint bị tắt mặc định, yêu cầu registrar có client.create và JwtDecoder để xác minh Initial Access Token. Giữ strict validators, bổ sung allowlist riêng và bảo vệ Registration Access Token như một bearer credential có quyền quản lý client.
