# 22.4. Phân biệt grant mở rộng với phương thức xác thực client bằng JWT

## 1. Bài toán: thấy JWT trong token request thì đó là grant nào?

Một ứng dụng Spring Security OAuth 2.0/OIDC Client gửi request đến Token Endpoint. Trong request có một JWT được ký bằng khóa riêng. Người triển khai vội kết luận: “Đây là **JWT Bearer Grant**”. Kết luận đó **chưa đủ căn cứ**.

Một JWT có thể được dùng theo nhiều vai trò hoàn toàn khác nhau:

- **JWT làm authorization grant:** Client trình một JWT assertion để Authorization Server xem xét và cấp access token. Trường hợp tiêu biểu là **JWT Bearer Authorization Grant**, được mô tả trong RFC 7523.
- **JWT làm phương thức xác thực Client:** Client ký một JWT assertion để chứng minh mình là Client đã đăng ký. Ví dụ <code>private_key_jwt</code> trong OIDC và JWT-based client authentication trong RFC 7523. Authorization grant thực tế có thể vẫn là <code>client_credentials</code>, <code>authorization_code</code> hoặc <code>refresh_token</code>.
- **JWT là ID Token:** OpenID Provider gửi cho OIDC Client để chứng minh authentication của End-User.
- **JWT là access token:** Resource Server nhận Bearer access token có thể ở định dạng JWT; định dạng này không xác định grant đã được dùng.
- **JWT là Request Object hoặc DPoP proof:** JWT phục vụ bảo vệ authorization request hoặc chứng minh sở hữu khóa, không đồng nghĩa một grant mới.

**Không phân loại OAuth flow chỉ bằng việc payload “trông giống JWT”.** Hãy xem **OAuth parameter chứa JWT**, mục đích của assertion, <code>grant_type</code>, client authentication method và các yêu cầu kiểm tra tại Authorization Server.

### Sau bài học, bạn sẽ làm được gì?

1. Phân biệt rạch ròi **authorization grant** với **client authentication** ở Token Endpoint.
2. Nhận diện JWT Bearer Grant: <code>grant_type=urn:ietf:params:oauth:grant-type:jwt-bearer</code> cùng tham số <code>assertion</code>.
3. Nhận diện JWT Client Authentication: <code>client_assertion_type</code> cùng <code>client_assertion</code>, bao gồm <code>private_key_jwt</code> và <code>client_secret_jwt</code>.
4. Hiểu khi nào Client có thể dùng đồng thời **một grant mở rộng** và **một JWT riêng để xác thực Client**.
5. Đọc đúng ý nghĩa <code>iss</code>, <code>sub</code>, <code>aud</code>, <code>exp</code>, <code>jti</code> theo từng vai trò.
6. Áp dụng kiến thức khi cấu hình ClientRegistration và mở rộng Spring Security OAuth2 Client.
7. Chẩn đoán đúng lỗi <code>invalid_client</code>, <code>invalid_grant</code>, <code>unsupported_grant_type</code>, tránh sửa sai lớp giao thức.

## 2. Hai câu hỏi độc lập ở Token Endpoint

Khi Client yêu cầu access token, Authorization Server phải xử lý **hai câu hỏi**:

**Câu hỏi A — Client yêu cầu token dựa trên căn cứ gì?** Đây là vấn đề của **authorization grant**: authorization code, client credentials, refresh token, JWT bearer assertion, token exchange, hoặc một extension grant được Authorization Server hỗ trợ.

**Câu hỏi B — Client là ai, và nó chứng minh danh tính ra sao?** Đây là vấn đề của **client authentication**: <code>client_secret_basic</code>, <code>client_secret_post</code>, <code>private_key_jwt</code>, <code>client_secret_jwt</code>, mTLS hoặc một cơ chế phù hợp với loại Client.

Hai chiều có liên quan đến chính sách nhưng **không phải một thứ**.

~~~mermaid
flowchart TD
    C["OAuth2 Client"] --> R["Token Endpoint request"]
    R --> G{"Authorization grant là gì?"}
    R --> A{"Client authentication bằng gì?"}
    G --> G1["client_credentials"]
    G --> G2["authorization_code"]
    G --> G3["refresh_token"]
    G --> G4["JWT Bearer assertion grant"]
    G --> G5["Token Exchange extension"]
    A --> A1["client_secret_basic"]
    A --> A2["private_key_jwt"]
    A --> A3["client_secret_jwt"]
    A --> A4["mTLS / phương thức khác"]
    G1 --> V["Authorization Server kiểm tra request + policy"]
    G2 --> V
    G3 --> V
    G4 --> V
    G5 --> V
    A1 --> V
    A2 --> V
    A3 --> V
    A4 --> V
    V --> T["Token response nếu được chấp nhận"]
~~~

### 2.1. So sánh trực tiếp

| Khía cạnh | Authorization grant | Client authentication |
|---|---|---|
| Câu hỏi | “Dựa trên ủy quyền/chứng cứ nào để cấp token?” | “Client đang gọi Token Endpoint có đúng là Client đã đăng ký?” |
| OAuth parameter chính | <code>grant_type</code> | Cơ chế xác thực và tham số tương ứng |
| JWT theo RFC 7523 | <code>assertion</code> cho JWT Bearer Grant | <code>client_assertion</code> cho JWT client authentication |
| Mã type liên quan | <code>urn:ietf:params:oauth:grant-type:jwt-bearer</code> | <code>urn:ietf:params:oauth:client-assertion-type:jwt-bearer</code> |
| Có luôn mang End-User không? | Không; tùy loại grant và policy | Không; chứng minh danh tính **Client** |
| Quyết định scope/audience được cấp? | Grant, ClientRegistration và chính sách AS tham gia | Auth method tự nó không cấp scope |
| Thay đổi <code>grant_type</code>? | Có, khi đổi grant | Không, khi chỉ đổi auth method |
| Ví dụ độc lập | JWT bearer grant + client-secret authentication | client_credentials + private_key_jwt |

### 2.2. Ví dụ chỉ thay một chiều

Một backend trước đây gọi Token Endpoint bằng:

~~~text
grant_type = client_credentials
client authentication = client_secret_basic
~~~

Sau khi chuyển sang xác thực bằng khóa bất đối xứng:

~~~text
grant_type = client_credentials
client authentication = private_key_jwt
~~~

**Grant vẫn là client_credentials.** Điều thay đổi là cách Client chứng minh danh tính. Không viết báo cáo rằng hệ thống đã “chuyển qua JWT Bearer Grant” chỉ vì token request xuất hiện một JWT ký bằng private key.

## 3. JWT chỉ là định dạng: phải xem JWT được dùng ở đâu

JSON Web Token (JWT, RFC 7519) là một định dạng chứa claims có thể được ký hoặc bảo vệ bằng các cơ chế JOSE. Một JWT ký thường có ba phần:

~~~text
BASE64URL(header).BASE64URL(payload).BASE64URL(signature)
~~~

Một header minh họa:

~~~json
{
  "alg": "RS256",
  "typ": "JWT",
  "kid": "signing-key-2026"
}
~~~

Một payload minh họa:

~~~json
{
  "iss": "registered-client",
  "sub": "registered-client",
  "aud": "https://auth.example.org/oauth2/token",
  "iat": 1794800000,
  "exp": 1794800300,
  "jti": "unique-assertion-id"
}
~~~

Các giá trị hoàn toàn giả định và không phải assertion hợp lệ vì chưa có chữ ký thật.

**Cùng cấu trúc JWT không có nghĩa cùng mục đích.** JWT chứa <code>iss</code>, <code>sub</code> và <code>aud</code> có thể là client assertion, grant assertion, ID Token hoặc access token, nhưng quy tắc kiểm tra và đối tượng được đại diện **khác nhau**.

### 3.1. Những điều không được suy diễn từ một JWT

- JWT có <code>sub=user-123</code> không chứng minh Client được phép hành động thay user-123.
- JWT có chữ ký hợp lệ không chứng minh Authorization Server tin issuer hoặc key đó.
- JWT có <code>aud</code> đúng không chứng minh grant type được hỗ trợ.
- JWT là access token không đồng nghĩa token được cấp bằng JWT Bearer Grant.
- JWT được ký bằng private key không mặc nhiên là <code>private_key_jwt</code>; còn phải xem nó được gửi ở parameter nào.
- Một JWT có scope hoặc role claim không khiến Client tự có quyền gọi API nếu không qua validation/policy.

Với Spring Security OAuth2 Client, cần tách **phần xây assertion**, **phần chọn grant**, **phần xác thực Client**, **phần lưu OAuth2AuthorizedClient** và **phần dùng access token gọi Resource Server**.

## 4. Cấu trúc Token Endpoint request

Một token request OAuth 2.0 thông thường sử dụng:

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.org
Content-Type: application/x-www-form-urlencoded
~~~

Request body chứa <code>grant_type</code> và các tham số đặc thù grant. Client authentication có thể nằm ở HTTP Authorization header hoặc các form parameters theo phương thức đã đăng ký.

Ví dụ Client Credentials + HTTP Basic:

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.org
Authorization: Basic <CLIENT_CREDENTIALS_PLACEHOLDER>
Content-Type: application/x-www-form-urlencoded

grant_type=client_credentials&scope=reports.read
~~~

Ví dụ Client Credentials + JWT Client Authentication:

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.org
Content-Type: application/x-www-form-urlencoded

grant_type=client_credentials&
client_id=reports-client&
client_assertion_type=urn%3Aietf%3Aparams%3Aoauth%3Aclient-assertion-type%3Ajwt-bearer&
client_assertion=SIGNED_CLIENT_ASSERTION_PLACEHOLDER&
scope=reports.read
~~~

Dấu xuống dòng sau ký tự <code>&amp;</code> chỉ dùng để **dễ đọc**; request thực tế cần form-url-encoding hợp lệ. <code>client_id</code> có thể cần theo yêu cầu Authorization Server; JWT Client Authentication có quy tắc xác định Client thông qua assertion đã đăng ký.

**Chú ý:** <code>client_assertion_type</code> khác <code>grant_type</code>. Chúng có hai URN nhìn gần giống nhau nhưng ý nghĩa độc lập.

## 5. JWT Bearer Authorization Grant theo RFC 7523

### 5.1. Khi nào dùng JWT làm authorization grant?

JWT Bearer Authorization Grant (RFC 7523, mục 2.1) cho phép Client dùng một **JWT assertion** làm authorization grant để yêu cầu access token.

Đây là một **extension grant** theo mô hình mở rộng của OAuth 2.0. Authorization Server phải:

1. Nhận diện grant type extension.
2. Xác minh JWT assertion theo profile và cấu hình trust.
3. Kiểm tra assertion có được chấp nhận để cấp token cho Client, subject, audience và phạm vi yêu cầu hay không.
4. Áp dụng chính sách đăng ký Client, consent/delegation và quyền cấp token.

Việc Client ký được JWT **không có nghĩa** Authorization Server buộc phải chấp nhận JWT đó làm grant.

### 5.2. Tham số quyết định

~~~text
grant_type = urn:ietf:params:oauth:grant-type:jwt-bearer
assertion  = <JWT được ký và được AS tin cậy>
scope      = tùy yêu cầu và chính sách
~~~

Ví dụ:

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.org
Authorization: Basic <CLIENT_CREDENTIALS_PLACEHOLDER>
Content-Type: application/x-www-form-urlencoded

grant_type=urn%3Aietf%3Aparams%3Aoauth%3Agrant-type%3Ajwt-bearer&
assertion=SIGNED_GRANT_ASSERTION_PLACEHOLDER&
scope=reports.read
~~~

Trong request này:

- **Grant là JWT Bearer** vì <code>grant_type</code> là URN JWT Bearer Grant.
- <code>assertion</code> là **grant assertion**, mang dữ liệu Authorization Server dùng để đánh giá cơ sở cấp token.
- Header <code>Authorization: Basic ...</code> là **client authentication bằng client secret**, hoàn toàn độc lập với việc grant là JWT Bearer.

Nếu thay Basic bằng private_key_jwt, **grant vẫn là JWT Bearer**.

### 5.3. Một grant assertion gồm những claim gì?

Payload minh họa:

~~~json
{
  "iss": "https://issuer.example.org/service-account",
  "sub": "service-account-123",
  "aud": "https://auth.example.org/oauth2/token",
  "iat": 1794800000,
  "exp": 1794800300,
  "jti": "grant-assertion-unique-id-001"
}
~~~

Các claim cốt lõi cần hiểu:

| Claim | Ý nghĩa trong JWT Bearer Grant |
|---|---|
| <code>iss</code> | Issuer của assertion, phải được Authorization Server chấp nhận |
| <code>sub</code> | Subject mà assertion nói tới; ngữ nghĩa được chính sách trust/delegation xác định |
| <code>aud</code> | Audience dành cho Authorization Server/Token Endpoint theo profile và policy |
| <code>exp</code> | Assertion hết hạn khi nào; AS phải kiểm tra còn hạn |
| <code>iat</code> | Thời điểm assertion được phát hành, nếu có |
| <code>nbf</code> | Chưa có hiệu lực trước thời điểm này, nếu có |
| <code>jti</code> | Định danh assertion để hỗ trợ chống replay nếu được sử dụng |

Trong RFC 7523, các claim bắt buộc và cách kiểm tra cụ thể phải được triển khai theo profile; <code>jti</code> không tự trở thành cơ chế chống replay nếu Authorization Server không có policy/cache để phát hiện dùng lại.

**<code>sub</code> của grant assertion không tự động là người dùng đã đăng nhập OIDC.** Nó có thể biểu thị subject theo thỏa thuận trust giữa Client, assertion issuer và Authorization Server. Nếu quy trình có delegated access hoặc impersonation, cần sự cho phép tường minh từ Authorization Server và chính sách tổ chức.

### 5.4. Ai ký JWT Bearer Grant assertion?

JWT grant assertion được ký bởi một issuer mà Authorization Server được cấu hình để tin trong phạm vi grant đó. Tùy provider, có thể là service account, một issuer được ủy thác hoặc một hệ thống chứng thực riêng.

Không được mặc định:

~~~text
Client có private key bất kỳ
→ tự ký JWT có sub=admin
→ Authorization Server cấp quyền admin
~~~

Đó là cách suy luận nguy hiểm. **Chữ ký hợp lệ chỉ chứng minh JWT được ký bằng khóa tương ứng**, không chứng minh issuer được phép phát assertion cho subject/scope ấy.

### 5.5. JWT Bearer Grant có yêu cầu Client authentication không?

Việc Client có phải xác thực và dùng phương thức gì phụ thuộc **loại Client, quy tắc OAuth 2.0 và cấu hình của Authorization Server**.

Với một confidential Client, Authorization Server có thể yêu cầu client authentication như:

~~~text
client_secret_basic
private_key_jwt
mutual TLS
~~~

Hệ thống có thể dùng JWT làm **grant assertion** trong body và dùng một JWT **khác** làm **client assertion**. Hai assertions đại diện cho hai vai trò và phải được kiểm tra độc lập.

## 6. JWT làm phương thức xác thực Client theo RFC 7523

### 6.1. Mục tiêu là chứng minh Client đã đăng ký

Trong JWT Client Authentication (RFC 7523, mục 2.2), Client gửi một JWT assertion tới Token Endpoint để xác thực **chính nó**.

Điểm khác so với JWT Bearer Grant:

> JWT này không tự quyết định Client xin access token dựa trên grant nào. Grant vẫn được chỉ định bằng <code>grant_type</code> riêng.

Các form parameters:

~~~text
client_assertion_type =
  urn:ietf:params:oauth:client-assertion-type:jwt-bearer

client_assertion =
  <JWT chứng minh danh tính Client>
~~~

Ví dụ Client Credentials Grant dùng JWT Client Authentication:

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.org
Content-Type: application/x-www-form-urlencoded

grant_type=client_credentials&
client_id=reports-client&
client_assertion_type=urn%3Aietf%3Aparams%3Aoauth%3Aclient-assertion-type%3Ajwt-bearer&
client_assertion=SIGNED_CLIENT_ASSERTION_PLACEHOLDER
~~~

Trong ví dụ:

| Tham số | Ý nghĩa |
|---|---|
| <code>grant_type=client_credentials</code> | **Grant** |
| <code>client_assertion_type=...:client-assertion-type:jwt-bearer</code> | **Client authentication mechanism** |
| <code>client_assertion=...</code> | Bằng chứng JWT do Client ký |
| <code>client_id=reports-client</code> | Định danh Client, nếu provider yêu cầu/cho phép như cấu hình |

Không đổi <code>grant_type</code> sang <code>...:grant-type:jwt-bearer</code> chỉ vì muốn bật private_key_jwt. Làm vậy chuyển cả **cơ sở xin token** sang một extension grant khác.

### 6.2. Claim của client assertion

Payload minh họa:

~~~json
{
  "iss": "reports-client",
  "sub": "reports-client",
  "aud": "https://auth.example.org/oauth2/token",
  "iat": 1794800000,
  "exp": 1794800300,
  "jti": "client-assertion-unique-id-002"
}
~~~

Khác biệt quan trọng với grant assertion:

- Với JWT Client Authentication theo RFC 7523, <code>iss</code> thường phải nhận diện **Client ID**.
- <code>sub</code> cũng phải là **Client ID**.
- <code>aud</code> xác định Authorization Server mà assertion được gửi tới, thường là token endpoint URL theo yêu cầu profile/provider.
- <code>exp</code> giới hạn thời gian hiệu lực của assertion.
- <code>jti</code> có thể giúp Authorization Server phát hiện replay nếu triển khai lưu/kiểm tra định danh.

Một số OpenID Provider yêu cầu audience chính xác là issuer URI hoặc token endpoint URI theo profile và cấu hình. **Không tự đoán**; dùng metadata và tài liệu client authentication của provider. Audience phải được AS kiểm tra theo policy tin cậy, không lấy từ URL do người dùng cung cấp.

### 6.3. Client assertion không phải access token

Client assertion:

- Được gửi tới **Token Endpoint** để Client authentication.
- Không phải token được cấp cho Resource Server.
- Không thay thế Bearer access token ở API.
- Thường có lifetime rất ngắn và ràng buộc audience riêng.

Sai:

~~~http
GET /api/reports HTTP/1.1
Host: api.example.org
Authorization: Bearer SIGNED_CLIENT_ASSERTION_PLACEHOLDER
~~~

Resource Server không nên chấp nhận một client assertion Token Endpoint như access token chỉ vì định dạng là JWT.

## 7. private_key_jwt và client_secret_jwt

Trong OpenID Connect, những tên method phổ biến cho JWT Client Authentication gồm:

### 7.1. private_key_jwt

Client tạo JWT được ký bằng **private key**, Authorization Server xác minh bằng public key/JWKS đã được đăng ký hoặc phân phối tin cậy.

~~~text
Client
  ├── private signing key: giữ bí mật, chỉ Client được dùng
  └── client_assertion = JWS(private key)

Authorization Server
  ├── clientId và auth method = private_key_jwt
  ├── public key/JWKS tin cậy của Client
  └── verify signature, iss/sub/aud/exp/jti/policy
~~~

Ưu điểm: Authorization Server không phải giữ cùng một **shared signing secret** với Client. Nhưng Client vẫn phải bảo vệ private key, triển khai key rotation, signing algorithm policy và chống replay.

### 7.2. client_secret_jwt

Client tạo JWT được ký bằng thuật toán MAC đối xứng như HMAC, dùng **client secret** đã được đăng ký với Authorization Server.

~~~text
Client và Authorization Server có shared client secret
    ↓
Client ký JWT bằng secret theo thuật toán được chấp nhận
    ↓
Authorization Server kiểm tra MAC và claims
~~~

Đây vẫn là **JWT Client Authentication**, không phải JWT Bearer Grant. Không nên coi <code>client_secret_jwt</code> tương đương bảo mật về quản trị khóa với <code>private_key_jwt</code>, vì một bên dùng shared secret còn bên kia dùng key pair.

### 7.3. So sánh các Client authentication methods

| Method | Credential Client cung cấp | Token request sử dụng | Có đổi grant type? |
|---|---|---|---|
| <code>client_secret_basic</code> | Client ID/secret qua HTTP Basic | Header Authorization | Không |
| <code>client_secret_post</code> | Client ID/secret trong form body | <code>client_id</code>, <code>client_secret</code> | Không |
| <code>client_secret_jwt</code> | JWT MAC bằng client secret | <code>client_assertion_type</code> + <code>client_assertion</code> | Không |
| <code>private_key_jwt</code> | JWT ký bằng private key | <code>client_assertion_type</code> + <code>client_assertion</code> | Không |
| mTLS client auth | Client certificate và xác minh TLS theo profile | TLS handshake, cùng OAuth parameters phù hợp | Không |
| <code>none</code> | Không có confidential-client secret | Public Client theo registration/policy | Không |

Không mặc định phương thức <code>none</code> là hợp lệ cho mọi grant; ví dụ Client Credentials thông thường cần Client authentication phù hợp với Authorization Server.

### 7.4. PKCE không phải client authentication bằng JWT

Trong Authorization Code Flow, PKCE sử dụng:

~~~text
code_challenge
code_challenge_method=S256
code_verifier
~~~

PKCE ràng buộc authorization code với Client đã khởi tạo flow và giảm nguy cơ authorization code interception. PKCE **không thay thế xác thực confidential Client** bằng private_key_jwt hoặc secret nếu chính sách yêu cầu cả hai.

Một authorization code token request có thể đồng thời chứa:

~~~text
grant_type=authorization_code
code=...
redirect_uri=...
code_verifier=...
client_assertion_type=...
client_assertion=...
~~~

Đó vẫn là **Authorization Code Grant**, dùng PKCE và JWT Client Authentication.

## 8. Ba kịch bản phải đọc đúng

### 8.1. Kịch bản A — Client Credentials Grant + private_key_jwt

Một batch worker cần đọc Reports API bằng quyền của service.

~~~text
Grant:                  client_credentials
Client authentication:  private_key_jwt
End-User:               không có
JWT truyền đi:          client_assertion
Token nhận được:        access token của service
~~~

Request:

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.org
Content-Type: application/x-www-form-urlencoded

grant_type=client_credentials&
client_id=reports-client&
scope=reports.read&
client_assertion_type=urn%3Aietf%3Aparams%3Aoauth%3Aclient-assertion-type%3Ajwt-bearer&
client_assertion=SIGNED_CLIENT_ASSERTION_A
~~~

Không có <code>assertion</code> của JWT Bearer Grant. Nếu một sơ đồ gọi đây là “JWT Bearer Grant”, sơ đồ đã phân loại sai.

### 8.2. Kịch bản B — JWT Bearer Grant + client_secret_basic

Một Authorization Server hỗ trợ JWT Bearer Grant và tin issuer <code>issuer.example.org</code> để xác định subject của grant.

~~~text
Grant:                  JWT Bearer Authorization Grant
Client authentication:  client_secret_basic
JWT truyền đi:          assertion
JWT client_assertion:   không có
~~~

Request:

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.org
Authorization: Basic <CLIENT_CREDENTIALS_PLACEHOLDER>
Content-Type: application/x-www-form-urlencoded

grant_type=urn%3Aietf%3Aparams%3Aoauth%3Agrant-type%3Ajwt-bearer&
assertion=SIGNED_GRANT_ASSERTION_B&
scope=reports.read
~~~

JWT trong <code>assertion</code> là cơ sở của **grant**, không phải HTTP Basic Client authentication.

### 8.3. Kịch bản C — JWT Bearer Grant + private_key_jwt

Cả hai lớp cùng dùng JWT nhưng là **hai assertions riêng**:

~~~text
Grant:                  urn:ietf:params:oauth:grant-type:jwt-bearer
Grant assertion:        SIGNED_GRANT_ASSERTION_C

Client auth method:     private_key_jwt
Client assertion:       SIGNED_CLIENT_ASSERTION_C
~~~

Request:

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.org
Content-Type: application/x-www-form-urlencoded

grant_type=urn%3Aietf%3Aparams%3Aoauth%3Agrant-type%3Ajwt-bearer&
assertion=SIGNED_GRANT_ASSERTION_C&
client_id=reports-client&
client_assertion_type=urn%3Aietf%3Aparams%3Aoauth%3Aclient-assertion-type%3Ajwt-bearer&
client_assertion=SIGNED_CLIENT_ASSERTION_C
~~~

Ở đây:

1. <code>assertion</code> được đánh giá theo **quy tắc authorization grant**.
2. <code>client_assertion</code> được đánh giá theo **quy tắc Client authentication**.
3. Hai JWT có thể có <code>iss</code>, <code>sub</code>, key và audience khác nhau theo chính sách.
4. Chỉ vì chúng cùng là JWT không có nghĩa có thể dùng lại một assertion cho cả hai mục đích.

**Không tái sử dụng cùng một signed JWT một cách tùy tiện ở cả hai tham số.** Hai lớp có profile claim, trust boundary, key policy, lifetime và replay policy khác nhau.

### 8.4. Tóm tắt ba kịch bản

| Kịch bản | grant_type | grant assertion? | Client authentication | client_assertion? |
|---|---|---|---|---|
| A | <code>client_credentials</code> | Không | <code>private_key_jwt</code> | Có |
| B | JWT Bearer Grant URN | Có | <code>client_secret_basic</code> | Không |
| C | JWT Bearer Grant URN | Có | <code>private_key_jwt</code> | Có |

Để đọc một log request đã được che thông tin nhạy cảm, hãy hỏi theo thứ tự:

1. <code>grant_type</code> là gì?
2. Có tham số <code>assertion</code> phục vụ grant không?
3. Client authentication method đã đăng ký là gì?
4. Có <code>client_assertion_type</code>/<code>client_assertion</code> không?
5. Authorization Server có hỗ trợ và tin các assertions theo hai profile tương ứng không?

## 9. Grant mở rộng khác: Token Exchange RFC 8693

JWT Bearer Grant chỉ là **một** extension grant. Một ví dụ khác rất dễ nhầm với JWT client authentication là **OAuth 2.0 Token Exchange (RFC 8693)**.

Token Exchange cho phép một Client yêu cầu đổi một security token đã có thành token khác theo chính sách Authorization Server.

Các tham số cơ bản:

~~~text
grant_type = urn:ietf:params:oauth:grant-type:token-exchange
subject_token = <token đang được trao đổi>
subject_token_type = <loại subject token>
requested_token_type = <loại token muốn nhận, nếu cần>
audience = <resource đích, nếu AS hỗ trợ>
~~~

Ví dụ:

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.org
Content-Type: application/x-www-form-urlencoded

grant_type=urn%3Aietf%3Aparams%3Aoauth%3Agrant-type%3Atoken-exchange&
subject_token=EXISTING_ACCESS_TOKEN_PLACEHOLDER&
subject_token_type=urn%3Aietf%3Aparams%3Aoauth%3Atoken-type%3Aaccess_token&
audience=https%3A%2F%2Freports-api.example.org&
client_assertion_type=urn%3Aietf%3Aparams%3Aoauth%3Aclient-assertion-type%3Ajwt-bearer&
client_assertion=SIGNED_CLIENT_ASSERTION_D
~~~

Trong request trên:

- Grant là **Token Exchange**, không phải JWT Bearer Grant.
- <code>subject_token</code> là token đem ra trao đổi; có thể là JWT hoặc opaque token tùy type.
- <code>client_assertion</code> là JWT để **xác thực Client**.
- Authorization Server vẫn quyết định có cho phép đổi token và cấp audience/scope yêu cầu hay không.

Nếu token đầu vào là JWT, điều đó **không biến Token Exchange thành JWT Bearer Grant**. Ngược lại, client assertion ký bằng JWT cũng không tự tạo delegation/token exchange permission.

### 9.1. Token Exchange không tự cho phép impersonation

Token Exchange có thể hỗ trợ các mô hình delegation hoặc token narrowing, nhưng chỉ khi Authorization Server và Resource Server được cấu hình để tin các thực thể, actor/subject semantics và phạm vi thích hợp.

Không được tự nhận một token của user A, đổi <code>subject</code> thành user B rồi kỳ vọng Authorization Server chấp nhận. Authentication của Client và quyền delegation phải được kiểm tra riêng.

### 9.2. Một số grant mở rộng khác

OAuth 2.0 Device Authorization Grant (RFC 8628) sử dụng <code>grant_type=urn:ietf:params:oauth:grant-type:device_code</code> khi Client polling Token Endpoint bằng device code. Nếu Client đó có client authentication theo phương thức JWT, **device code grant vẫn là device code grant**.

Tương tự, một Authorization Server có thể hỗ trợ những grant extensions riêng theo tài liệu của nó. **Phương thức xác thực Client không định nghĩa thay những grant extensions đó**.

## 10. Những JWT dễ bị nhầm với grant/client assertion

### 10.1. ID Token trong OIDC

ID Token:

- Do OpenID Provider phát hành cho OIDC Client.
- Chứng minh End-User authentication theo OIDC.
- Có <code>iss</code>, <code>sub</code>, <code>aud</code>, <code>exp</code> và các claims liên quan.
- Được Client xác minh; không phải mặc định là client assertion.

Ví dụ:

~~~text
OIDC Authorization Code Flow:
  grant_type=authorization_code
  → Token Endpoint response có id_token
~~~

Nhận được <code>id_token</code> dạng JWT **không** chứng minh request đã dùng JWT Bearer Grant hoặc private_key_jwt.

### 10.2. JWT Access Token

Một Resource Server có thể nhận Bearer access token là JWT theo JWT Access Token Profile (RFC 9068) hoặc định dạng JWT riêng được nhà cung cấp hỗ trợ.

~~~http
GET /v1/reports HTTP/1.1
Host: api.example.org
Authorization: Bearer ACCESS_TOKEN_JWT_PLACEHOLDER
~~~

Đó là **cách biểu diễn access token tại Resource Server**, không nói lên <code>grant_type</code> dùng khi cấp token. Client Credentials, Authorization Code, Refresh Token, JWT Bearer Grant hoặc Token Exchange đều có thể dẫn đến JWT access token nếu AS chọn định dạng đó.

Không tự decode JWT rồi tin scopes/roles nếu Resource Server chưa xác minh signature, issuer, audience, expiry và authorization policy.

### 10.3. Request Object (JAR)

JWT-Secured Authorization Request (RFC 9101) có thể đặt authorization request parameters trong một **Request Object JWT**, được gửi dưới <code>request</code> hoặc thông qua <code>request_uri</code>.

~~~text
Authorization Endpoint:
    response_type=code
    client_id=...
    request=<SIGNED_REQUEST_OBJECT_JWT>
~~~

Đây là **bảo vệ authorization request** ở front channel, không phải JWT Bearer Grant tại Token Endpoint và cũng không phải mặc định một Client authentication assertion.

### 10.4. DPoP proof JWT

Demonstrating Proof of Possession (DPoP, RFC 9449) sử dụng JWT proof trong HTTP <code>DPoP</code> header để ràng buộc các request với một khóa.

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.org
DPoP: SIGNED_DPOP_PROOF_PLACEHOLDER
Content-Type: application/x-www-form-urlencoded

grant_type=authorization_code&code=CODE_PLACEHOLDER
~~~

DPoP proof **không tự thay thế Client authentication** và không định nghĩa lại grant. Nó phục vụ proof-of-possession/token binding theo profile; Authorization Server có thể vẫn yêu cầu confidential Client Authentication.

### 10.5. Tổng hợp các vai trò JWT

| JWT | Nằm ở đâu? | Mục đích |
|---|---|---|
| JWT Bearer Grant assertion | Token request <code>assertion</code> | Làm căn cứ authorization grant |
| JWT Client Authentication assertion | Token request <code>client_assertion</code> | Xác thực Client |
| OIDC ID Token | Token response <code>id_token</code> | Xác thực End-User cho Client |
| JWT access token | Token response <code>access_token</code>; API Bearer header | Truy cập Resource Server |
| JAR Request Object | Authorization request <code>request</code>/<code>request_uri</code> | Bảo vệ authorization parameters |
| DPoP proof | HTTP header <code>DPoP</code> | Chứng minh sở hữu khóa theo request/token |
| Token Exchange subject token | Token request <code>subject_token</code> | Là token đầu vào cho extension grant |

**Luôn dựa trên vị trí và hợp đồng giao thức**, không phân loại bằng cách nhìn số dấu chấm trong chuỗi JWT.

## 11. Trust boundary: ai xác minh gì?

### 11.1. Với JWT Bearer Grant

Authorization Server cần kiểm tra:

1. <code>grant_type</code> có được hỗ trợ và Client được phép sử dụng không.
2. JWT assertion có đúng định dạng, issuer/subject/audience và thời hạn hợp lệ không.
3. Chữ ký có được xác minh bằng **key tin cậy cho assertion issuer** không.
4. Issuer có được phép khẳng định subject và yêu cầu scope/audience đó không.
5. JWT có nằm trong replay policy và được phép cấp token theo trust agreement không.
6. Client authentication, nếu được yêu cầu, có hợp lệ không.

### 11.2. Với JWT Client Authentication

Authorization Server cần kiểm tra:

1. Client có được đăng ký với auth method JWT tương ứng không.
2. Client ID từ JWT <code>iss</code>/<code>sub</code> có phù hợp không.
3. Chữ ký/MAC có hợp lệ bằng key/secret **gắn với Client đó** không.
4. <code>aud</code> có hướng đến Authorization Server/Token Endpoint được cho phép không.
5. <code>exp</code>, <code>nbf</code>, <code>iat</code> và <code>jti</code> có tuân thủ chính sách không.
6. Grant riêng trong <code>grant_type</code> có được Client này sử dụng không.

Sơ đồ hai đường kiểm tra:

~~~mermaid
flowchart LR
    REQ["Token request"] --> G["Grant validation"]
    REQ --> C["Client authentication validation"]
    G --> GA["Kiểm tra assertion / subject / scope / policy"]
    C --> CA["Kiểm tra client ID / key / JWT / audience"]
    GA --> ISSUE{"Cả hai điều kiện đều đạt?"}
    CA --> ISSUE
    ISSUE -->|Có| TOK["Phát token theo policy"]
    ISSUE -->|Không| ERR["OAuth2 error response"]
~~~

**Có một JWT ký đúng không thay thế được hai đường validation.**

### 11.3. Không chấp nhận thuật toán JWT tùy ý

Với JWT assertions:

- Chỉ chấp nhận signing algorithms theo allowlist, đúng đăng ký Client/issuer.
- Không chấp nhận <code>alg=none</code> cho assertion yêu cầu chữ ký.
- Không tin <code>jku</code>/<code>x5u</code> trong JWT header để tự động tải public key từ URL tùy ý.
- Không để <code>kid</code> trở thành đường dẫn file hoặc URL do caller kiểm soát.
- Bảo vệ against algorithm confusion: không diễn giải public key như HMAC secret.
- Kiểm tra key use, key ID, issuer/client binding và thời điểm key rotation.
- Dùng thư viện JOSE/JWT đã được kiểm chứng thay vì tự viết verification crypto.

### 11.4. Lifetime và replay

Client assertion nên có lifetime ngắn theo yêu cầu provider và mỗi assertion nên có <code>jti</code> mới khi chính sách yêu cầu/chấp nhận.

Ví dụ:

~~~text
iat = thời điểm hiện tại
exp = iat + 60 đến vài phút, theo policy
jti = random unique ID
~~~

Đây là gợi ý thiết kế, không phải một quy định mọi provider đều chấp nhận cùng thời hạn. Authorization Server có thể đặt maximum assertion lifetime và clock skew riêng.

Quan trọng: **một <code>jti</code> ngẫu nhiên trong payload không tự ngăn replay**. Phía xác minh phải kiểm tra và lưu/cache <code>jti</code> đã dùng theo thời gian hiệu lực thích hợp.

Đừng tái sử dụng cùng client assertion trong cache nhiều giờ. Nếu Token Endpoint request timeout, không mặc nhiên retry vô hạn cùng JWT; có thể tạo assertion mới theo policy, phân loại lỗi và giới hạn retry.

## 12. Spring Security: ClientRegistration mô tả grant và authentication method riêng

Đây là điểm mapping quan trọng vào cấu hình Spring Security OAuth 2.0/OIDC Client.

### 12.1. Client Credentials + client_secret_basic

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          reports-worker:
            provider: company
            client-id: reports-client
            client-secret: ${REPORTS_CLIENT_SECRET}
            authorization-grant-type: client_credentials
            client-authentication-method: client_secret_basic
            scope:
              - reports.read
        provider:
          company:
            token-uri: https://auth.example.org/oauth2/token
~~~

Đây là **Client Credentials Grant** với Client Secret Basic Authentication.

### 12.2. Client Credentials + private_key_jwt

Một registration sử dụng cùng grant nhưng đổi auth method:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          reports-worker:
            provider: company
            client-id: reports-client
            authorization-grant-type: client_credentials
            client-authentication-method: private_key_jwt
            scope:
              - reports.read
        provider:
          company:
            token-uri: https://auth.example.org/oauth2/token
~~~

**Quan trọng:** Cấu hình <code>client-authentication-method: private_key_jwt</code> **chưa đủ** để một ứng dụng thực tế ký được JWT.

Client còn cần:

1. Private signing key/keystore hoặc signing service.
2. Public key/JWKS đã đăng ký/được OP tin cậy.
3. Thuật toán phù hợp với policy và key.
4. Thành phần ký client assertion và thêm form parameters vào token request.
5. Cơ chế key rotation, expiry, <code>jti</code> và bảo vệ private key.

Trong Spring Security, việc signing client assertion và gắn nó vào token request có thể cần cấu hình token response client/converter phù hợp **theo phiên bản**. Không giả định chỉ khai báo YAML là Spring Boot tự tìm khóa riêng hoặc tự sinh chữ ký.

### 12.3. Java ClientRegistration

Ví dụ nêu rõ **hai thuộc tính độc lập**:

~~~java
import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.ClientAuthenticationMethod;

ClientRegistration registration =
    ClientRegistration.withRegistrationId("reports-worker")
        .clientId("reports-client")
        .authorizationGrantType(AuthorizationGrantType.CLIENT_CREDENTIALS)
        .clientAuthenticationMethod(
            ClientAuthenticationMethod.PRIVATE_KEY_JWT)
        .tokenUri("https://auth.example.org/oauth2/token")
        .scope("reports.read")
        .build();
~~~

Đoạn code minh họa mô hình registration. **Private key/JWK provider không được truyền vào ClientRegistration này**; chúng thuộc một lớp cấu hình signing/token client riêng. Cần thực hiện và đăng ký đúng JWT assertion converter trước khi thực hiện request token.

Không nên lưu khóa riêng dưới dạng chuỗi hardcode trong source để “làm cho demo chạy”.

### 12.4. JWT Bearer Grant là custom AuthorizationGrantType

Nếu Authorization Server hỗ trợ RFC 7523 JWT Bearer Grant:

~~~java
import org.springframework.security.oauth2.core.AuthorizationGrantType;

AuthorizationGrantType JWT_BEARER_GRANT =
    new AuthorizationGrantType(
        "urn:ietf:params:oauth:grant-type:jwt-bearer");
~~~

Có thể sử dụng giá trị grant type đó để biểu diễn registration theo khả năng API/version:

~~~java
ClientRegistration jwtGrantRegistration =
    ClientRegistration.withRegistrationId("assertion-worker")
        .clientId("assertion-client")
        .authorizationGrantType(JWT_BEARER_GRANT)
        .clientAuthenticationMethod(
            ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
        .clientSecret("<PLACEHOLDER_FROM_SECRET_STORE>")
        .tokenUri("https://auth.example.org/oauth2/token")
        .build();
~~~

**Đây mới là biểu diễn metadata, chưa phải triển khai đầy đủ JWT Bearer Grant.** Tự tạo một <code>AuthorizationGrantType</code> mới không đồng nghĩa Spring Security tự có token request converter/provider biết tạo <code>assertion</code> và xử lý response cho grant này.

Nếu Spring Security phiên bản hiện tại không có built-in provider/client hỗ trợ grant mở rộng bạn cần, phải tạo/tích hợp đúng extension point theo tài liệu phiên bản đó, hoặc dùng token client riêng có contract rõ ràng. Không đổi <code>grant_type</code> “cho giống nhau” chỉ vì thiếu built-in provider.

## 13. Spring Security Authorized Client Manager không quyết định Client authentication

Với một job dùng Client Credentials Grant, có thể cấu hình:

~~~java
package example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.AuthorizedClientServiceOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;

@Configuration
public class ReportsManagerConfig {

    @Bean
    OAuth2AuthorizedClientManager reportsAuthorizedClientManager(
            ClientRegistrationRepository registrations,
            OAuth2AuthorizedClientService service) {

        var manager =
            new AuthorizedClientServiceOAuth2AuthorizedClientManager(
                registrations, service);

        var provider = OAuth2AuthorizedClientProviderBuilder.builder()
            .clientCredentials()
            .build();

        manager.setAuthorizedClientProvider(provider);
        return manager;
    }
}
~~~

Code trên chọn **Client Credentials Provider**. Nó không cấu hình được private key signing chỉ bằng <code>.clientCredentials()</code>.

Trong manager:

~~~text
ClientRegistration:
    grant_type = client_credentials
    client authentication method = private_key_jwt

Authorized Client Provider:
    clientCredentials()

Token Response Client:
    phải biết tạo và ký client_assertion phù hợp
~~~

Nếu dùng JWT Bearer **Grant**, provider sẽ phải hỗ trợ extension grant thay vì dùng <code>clientCredentials()</code> rồi chỉ đổi assertion.

### 13.1. JWT client authentication ở lớp token request

Spring Security có các extension points cho cách tạo token request và Client authentication parameters; API cụ thể tùy phiên bản Spring Security.

Ví dụ ở các phiên bản Spring Security hỗ trợ Nimbus JOSE integration, có các thành phần kiểu **<code>NimbusJwtClientAuthenticationParametersConverter</code>** giúp tạo JWT Client Authentication parameters với signing JWK được cung cấp qua cấu hình.

Sơ đồ tích hợp:

~~~text
ClientRegistration(private_key_jwt)
            |
            v
OAuth2AuthorizedClientManager
            |
            v
OAuth2AuthorizedClientProvider(clientCredentials)
            |
            v
OAuth2AccessTokenResponseClient
            |
            +-- Grant parameters: grant_type=client_credentials
            |
            +-- Client auth parameters:
            |     client_assertion_type=...
            |     client_assertion=<signed JWT>
            |
            v
Token Endpoint
~~~

Tên class/constructor và cách đăng ký converter vào token client thay đổi theo Spring Security version (ví dụ giữa các bản Servlet/Reactive). Vì vậy bài không giả định một snippet signing JWK áp dụng cho mọi Boot 3.x hoặc Spring Security 6.x.

**Sai lầm cần tránh:** thêm <code>JwtBearerOAuth2AuthorizedClientProvider</code> theo một bài hướng dẫn cũ rồi cho rằng nó cấu hình <code>private_key_jwt</code>. Provider cho **JWT Bearer authorization grant**, nếu có trong version/framework extension, làm việc ở chiều **grant**; JWT Client Authentication là chiều khác.

### 13.2. Khi nào cần custom OAuth2AuthorizedClientProvider?

Nếu triển khai extension grant chưa được manager/provider hiện tại hỗ trợ, Client có thể cần:

- Một class thực hiện <code>OAuth2AuthorizedClientProvider</code> hoặc reactive counterpart.
- Dữ liệu assertion grant được cấp từ issuer tin cậy.
- Token response client gửi đúng <code>grant_type</code> và <code>assertion</code>.
- Cơ chế Client authentication tách riêng.
- Authorized-client storage/success/failure handling phù hợp.
- Validation và policy về subject/audience/scopes ở Authorization Server.

Không nên viết custom provider chỉ để thay client secret bằng private_key_jwt nếu framework đã có extension point phù hợp tại **token response client**.

## 14. Một ví dụ Spring Boot có hai registration phục vụ hai mục đích

Giả sử hệ thống có:

1. Browser dùng Authorization Code + OIDC Login qua <code>web-login</code>.
2. Scheduler dùng Client Credentials + private_key_jwt qua <code>reports-service</code>.

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          web-login:
            provider: company
            client-id: portal-web
            client-secret: ${PORTAL_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            client-authentication-method: client_secret_basic
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile

          reports-service:
            provider: company
            client-id: reports-worker
            authorization-grant-type: client_credentials
            client-authentication-method: private_key_jwt
            scope:
              - reports.read

        provider:
          company:
            issuer-uri: https://idp.example.org/realms/company
~~~

Ở đây:

- <code>web-login</code> dùng **Authorization Code Grant**; <code>openid</code> kích hoạt OIDC authentication.
- <code>reports-service</code> dùng **Client Credentials Grant**; <code>private_key_jwt</code> chỉ nói cách service xác thực tại Token Endpoint.
- Một trong hai registration **không mặc nhiên** dùng JWT Bearer Authorization Grant.
- <code>reports-service</code> cần signing key configuration riêng, đã được OP tin cậy.
- Access token của <code>web-login</code> không tự thích hợp cho Reports API; có thể là token cho UserInfo hoặc resource khác.

Nếu muốn thêm một registration JWT Bearer Grant, đó là **grant mới thực sự**, đòi Authorization Server hỗ trợ và phần mềm tạo JWT grant assertion hợp lệ.

### 14.1. Với background job, principal không phải End-User

Một job dùng service manager có thể gọi:

~~~java
import org.springframework.security.oauth2.client.OAuth2AuthorizeRequest;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;

OAuth2AuthorizeRequest request =
    OAuth2AuthorizeRequest
        .withClientRegistrationId("reports-service")
        .principal("reports-worker-runtime")
        .build();

OAuth2AuthorizedClient authorizedClient =
    manager.authorize(request);
~~~

<code>reports-worker-runtime</code> là principal key để Spring Security lưu token, **không phải subject mà Client đang cố mạo danh trong JWT Bearer Grant**. Việc principal name là chuỗi tùy backend đặt không cho phép đổi subject của access token hoặc assertion grant.

Nếu <code>authorize(...)</code> trả <code>null</code> hoặc ném exception, phải xử lý theo grant và lỗi thực tế; không tự tạo JWT giả để bypass provider.

## 15. Key management cho private_key_jwt

### 15.1. Khóa riêng và khóa công khai

Mô hình thường gặp:

~~~mermaid
flowchart LR
    APP["Client service"] --> K["Private key trong vault/HSM/keystore"]
    K --> SIGN["Ký client_assertion"]
    SIGN --> TOKEN["Token Endpoint"]
    JWKS["Public JWK/JWKS đã đăng ký"] --> TOKEN
    TOKEN --> VERIFY["Xác minh chữ ký + claims + client binding"]
~~~

Client giữ **private key**. Authorization Server xác minh bằng **public key** tương ứng đã được cấu hình tin cậy. Không gửi private key cho Authorization Server.

Các bước vận hành:

1. Tạo key pair bằng phương pháp được chính sách tổ chức cho phép.
2. Đăng ký public JWK/JWKS với Authorization Server.
3. Chọn signature algorithm đúng allowlist.
4. Gắn <code>kid</code> giúp chọn key khi cần.
5. Cấu hình token client/signing converter sử dụng private key an toàn.
6. Giới hạn JWT client assertion lifetime và tạo <code>jti</code> phù hợp.
7. Giám sát xác thực Client thất bại và key expiry/rotation.

### 15.2. Xoay vòng khóa không gián đoạn

Một chiến lược rotation:

~~~text
T0: public JWK K1 đã được AS tin cậy
T1: thêm public JWK K2 vào trusted set
T2: Client chuyển ký assertion bằng private key K2
T3: quan sát xác thực thành công với kid=K2
T4: sau thời gian tương thích, gỡ K1 khỏi trusted set
~~~

Không xóa K1 ngay trước khi tất cả instance đã chuyển qua K2 nếu còn node đang ký bằng K1. Nếu key store/JWKS được cache tại AS, cần tính thời gian cập nhật cache.

Khóa dùng để ký **JWT grant assertion** có thể thuộc một issuer khác với Client key dùng ký **client assertion**. Không nhập hai vòng đời key vào một mà không có thiết kế tin cậy rõ ràng.

### 15.3. Chữ ký hợp lệ nhưng wrong audience

Một lỗi phổ biến:

~~~text
JWT iss=sub=reports-client
JWT ký đúng private key
JWT aud=https://api.example.org
Token Endpoint=https://auth.example.org/oauth2/token
~~~

JWT Client Authentication có thể bị từ chối vì **audience không hướng đến Authorization Server/Token Endpoint được phép**. Đừng sửa bằng cách tắt audience validation.

Audience dùng cho client assertion **khác** audience của access token dùng gọi Resource Server.

## 16. Authorization Server phải hỗ trợ và cho phép từng capability

Trước khi cấu hình Spring Security, hãy xác minh thông tin provider:

| Capability | Cần xác nhận ở Authorization Server |
|---|---|
| JWT Bearer Grant | Có hỗ trợ <code>urn:ietf:params:oauth:grant-type:jwt-bearer</code> và trust policy issuer không? |
| Token Exchange | Có hỗ trợ grant type <code>...:token-exchange</code>, subject token type và delegation policy không? |
| private_key_jwt | Client có đăng ký auth method này, key/JWKS, alg/aud policy không? |
| client_secret_jwt | Client có được dùng HMAC-based JWT authentication không? |
| Client Credentials | Client có được dùng grant, scope/audience nào được cấp? |
| Authorization Code | Redirect URI, PKCE và client authentication policy nào? |
| Refresh Token | Có cấp refresh token, rotation/reuse detection ra sao? |

Nếu provider công bố discovery metadata, có thể xem các thuộc tính như:

~~~json
{
  "issuer": "https://idp.example.org/realms/company",
  "token_endpoint": "https://idp.example.org/realms/company/protocol/openid-connect/token",
  "token_endpoint_auth_methods_supported": [
    "client_secret_basic",
    "private_key_jwt"
  ],
  "grant_types_supported": [
    "authorization_code",
    "client_credentials",
    "urn:ietf:params:oauth:grant-type:jwt-bearer"
  ]
}
~~~

Đây là **metadata minh họa**, không phải thông tin của provider thật. Các mục có thể vắng mặt hoặc không liệt kê toàn bộ khả năng trong một số implementation; client registration và chính sách cụ thể vẫn quyết định Client có được phép dùng phương thức/grant đó hay không.

Đừng suy diễn:

~~~text
metadata hỗ trợ private_key_jwt
⇒ mọi Client đều được dùng JWT Bearer Grant
~~~

Hai khả năng là các mục riêng.

## 17. Xử lý lỗi: sai grant hay sai Client authentication?

Token Endpoint thường trả các mã lỗi OAuth 2.0 có ý nghĩa khác nhau.

### 17.1. invalid_client

Ví dụ:

~~~http
HTTP/1.1 401 Unauthorized
Content-Type: application/json

{
  "error": "invalid_client"
}
~~~

Nguyên nhân có thể:

- Client ID không được nhận diện.
- Client đăng ký <code>client_secret_basic</code> nhưng request dùng private_key_jwt chưa được cấp phép.
- Client assertion sai chữ ký, sai audience, hết hạn hoặc issuer/subject không khớp Client ID.
- Signing key chưa đăng ký, <code>kid</code> sai, JWK cache chưa cập nhật.
- Client key bị thu hồi hoặc cấu hình không đồng bộ.

Chẩn đoán trước tại **lớp Client authentication**, không vội đổi <code>grant_type</code>. Theo OAuth 2.0, cách biểu diễn HTTP status cho lỗi client authentication có thể phụ thuộc phương thức và implementation; ví dụ 401 không phải cam kết cho mọi provider.

### 17.2. unsupported_grant_type

Ví dụ:

~~~json
{
  "error": "unsupported_grant_type"
}
~~~

Nguyên nhân: Authorization Server không hỗ trợ hoặc không nhận diện <code>grant_type</code> được gửi.

Nếu gửi <code>urn:ietf:params:oauth:grant-type:jwt-bearer</code> tới provider chỉ hỗ trợ <code>client_credentials</code>, thêm private_key_jwt không giải quyết lỗi này. Cần dùng grant thực sự được hỗ trợ hoặc làm việc với provider để bật capability tương ứng.

### 17.3. unauthorized_client

Authorization Server có thể hỗ trợ một grant nhưng **Client hiện tại không được phép dùng**.

~~~json
{
  "error": "unauthorized_client"
}
~~~

Ví dụ grant JWT Bearer có hỗ trợ toàn hệ thống nhưng chỉ một nhóm Client đã đăng ký được sử dụng.

Đây là lỗi **phân quyền Client sử dụng grant**, không nhất thiết là chữ ký JWT sai. Cần xem registration policy tại Authorization Server.

### 17.4. invalid_grant

Với JWT Bearer Grant, lỗi có thể do grant assertion bị từ chối: claims, trust, expiry, replay hoặc policy subject/scope.

Với Authorization Code/Refresh Token, <code>invalid_grant</code> có thể do code/refresh token không hợp lệ, hết hạn, dùng lại hoặc bị thu hồi.

Không dùng <code>invalid_grant</code> như một bằng chứng duy nhất để xóa tất cả authorized clients của mọi user. Cần phân loại grant và bảo vệ token state trước concurrent update.

### 17.5. invalid_scope

Client yêu cầu scope không được chấp nhận:

~~~json
{
  "error": "invalid_scope"
}
~~~

Không sửa bằng cách ký JWT có thêm claim <code>scope=admin</code>. Quyền cấp token do Authorization Server policy quyết định, không phải do Client tự khai thêm.

### 17.6. Bảng chẩn đoán

| Lỗi / biểu hiện | Lớp nên xem trước | Điều cần đối chiếu |
|---|---|---|
| <code>invalid_client</code> | Client authentication | auth method, Client ID, key/secret, iss/sub/aud/exp |
| <code>unsupported_grant_type</code> | Authorization grant | <code>grant_type</code> có được AS hỗ trợ không |
| <code>unauthorized_client</code> | Client registration policy | Client có được dùng grant đó không |
| <code>invalid_grant</code> | Grant/assertion/token state | <code>assertion</code>, code/refresh token, expiry, trust, replay |
| <code>invalid_scope</code> | Permission request | Scope đã được cấp phép chưa |
| HTTP 401 tại Resource Server | Access-token authentication | Token đúng issuer/audience/expiry không |
| HTTP 403 <code>insufficient_scope</code> tại API | Resource authorization | Access token có quyền API cần thiết không |
| JWT ký đúng nhưng AS từ chối | Trust/policy/claims | Issuer, Client registration, audience, alg/key và delegation |

**Lưu ý:** HTTP 401/403 từ Resource Server **khác** với lỗi JSON từ Token Endpoint. Đừng đọc HTTP 403 <code>insufficient_scope</code> rồi kết luận Token Endpoint không hỗ trợ JWT client authentication.

## 18. Bảo mật khi dùng JWT grant và JWT Client Authentication

### 18.1. Không dùng assertion như bearer access token tùy ý

<code>assertion</code> của grant và <code>client_assertion</code> có mục tiêu **Token Endpoint**. Không đưa chúng vào HTTP API Authorization header trừ khi một giao thức/profile cụ thể được thiết kế và validate rõ ràng.

### 18.2. Không log assertion hay private key

Tránh log:

- Raw <code>assertion</code> và <code>client_assertion</code>.
- HTTP form body của Token Endpoint.
- Private key, HMAC secret và keystore password.
- Refresh token, access token, ID Token, Authorization header.
- <code>code_verifier</code> hoặc authorization code trong các flow khác.

Log an toàn hơn:

~~~text
registrationId=reports-worker
grantType=client_credentials
clientAuthMethod=private_key_jwt
tokenEndpointResult=invalid_client
signingKeyId=key-2026
requestCorrelationId=...
~~~

Ngay cả <code>kid</code> hoặc registration ID cũng cần được xử lý theo chính sách telemetry; không đưa raw token/claim bí mật vào metric label.

### 18.3. Không ký theo audience do caller tự truyền

Sai:

~~~text
POST /internal/get-token?aud=https://unknown.example
    → backend ký client assertion cho aud do caller chọn
~~~

Client assertion audience phải được lấy từ **Authorization Server/token endpoint cấu hình tin cậy** và đáp ứng đúng policy của provider. Cho caller quyết định có thể dẫn đến assertion bị gửi sai nơi hoặc abuse signing service.

### 18.4. Không cho browser chọn sub để mạo danh

Sai:

~~~text
POST /internal/grant
body: {"sub": "admin", "scope": "all"}
    → backend tự ký JWT Bearer Grant assertion
~~~

Nếu backend có quyền ký assertion mà AS tin, nó phải bảo vệ đặc biệt việc chọn subject, phạm vi delegation và xác thực caller. Không biến signing endpoint thành công cụ impersonation.

### 18.5. Chống replay phải ở bên xác minh

Client có thể tạo <code>jti</code> duy nhất và assertion ngắn hạn, nhưng Authorization Server phải thực thi duplicate detection khi chính sách/profile yêu cầu. Một cache replay phải được thiết kế với TTL, namespace issuer/client và độ tin cậy phù hợp, đặc biệt trong hệ thống nhiều node.

### 18.6. Key isolation

Không dùng một private key cho mọi issuer, mọi tenant và mọi loại assertion chỉ để tiết kiệm cấu hình. Tách khóa theo Client/trust domain khi policy yêu cầu và giới hạn quyền ký của từng service.

Với <code>client_secret_jwt</code>, lưu ý shared secret có thể bị lộ ở hai phía. Với <code>private_key_jwt</code>, bảo vệ private key trong HSM/vault/keystore và chỉ phân phối public keys tới AS.

## 19. Một cách đọc token request theo checklist kỹ thuật

Khi xem một request bị lỗi, thực hiện theo thứ tự:

1. Xác định **đích HTTP**: Token Endpoint hay Resource Server/Authorization Endpoint?
2. Tìm <code>grant_type</code> thực tế.
3. Nếu grant là JWT Bearer, kiểm tra có <code>assertion</code> không.
4. Nếu grant là Token Exchange, kiểm tra <code>subject_token</code>/<code>subject_token_type</code>.
5. Xác định Client authentication method đã đăng ký.
6. Nếu là JWT Client Authentication, kiểm tra <code>client_assertion_type</code> và <code>client_assertion</code>.
7. Xác minh Authorization Server hỗ trợ cả **grant** lẫn **auth method** và Client có quyền dùng.
8. Đối chiếu iss/sub/aud/exp/jti, algorithms, key IDs và trust policies **theo từng vai trò JWT**.
9. Kiểm tra scope/audience/entitlement thực sự được cấp.
10. Chỉ sau đó mới phân loại <code>invalid_client</code>, <code>invalid_grant</code> hoặc <code>unauthorized_client</code> để xử lý.

Sơ đồ quyết định:

~~~text
Có request tới Token Endpoint?
    |
    v
Đọc grant_type
    |
    +-- client_credentials ----------> client credentials grant
    |
    +-- authorization_code ---------> authorization code grant
    |
    +-- refresh_token --------------> refresh grant
    |
    +-- ...:grant-type:jwt-bearer --> JWT Bearer Grant
    |                                    |
    |                                    +-- tìm assertion
    |
    +-- ...:grant-type:token-exchange -> Token Exchange
                                         |
                                         +-- tìm subject_token

Sau đó (độc lập):
    |
    v
Client authentication method?
    |
    +-- client_secret_basic --------> Authorization: Basic
    |
    +-- private_key_jwt ------------> client_assertion_type + client_assertion
    |
    +-- client_secret_jwt ----------> client_assertion_type + client_assertion
    |
    +-- mTLS -----------------------> client certificate/trust
~~~

Không chọn grant bằng cách tìm từ “JWT” ở bất kỳ đâu trong request.

## 20. Bài tập thực hành

### Bài 1 — Nhận diện request

~~~text
grant_type=client_credentials
client_assertion_type=urn:ietf:params:oauth:client-assertion-type:jwt-bearer
client_assertion=JWT_A
~~~

**Hỏi:** Có phải JWT Bearer Grant không?

**Đáp án:** Không. Grant là <code>client_credentials</code>. JWT_A dùng cho Client authentication.

### Bài 2 — Nhận diện grant assertion

~~~text
grant_type=urn:ietf:params:oauth:grant-type:jwt-bearer
assertion=JWT_B
Authorization: Basic ...
~~~

**Hỏi:** JWT_B có phải client assertion không?

**Đáp án:** Không. JWT_B là JWT Bearer Grant assertion; Client đang xác thực bằng HTTP Basic.

### Bài 3 — Hai JWT trong một request

~~~text
grant_type=urn:ietf:params:oauth:grant-type:jwt-bearer
assertion=JWT_GRANT
client_assertion_type=urn:ietf:params:oauth:client-assertion-type:jwt-bearer
client_assertion=JWT_CLIENT
~~~

**Hỏi:** Authorization Server cần kiểm tra những gì?

**Đáp án:** Kiểm tra JWT_GRANT theo trust/grant/subject policy; kiểm tra JWT_CLIENT theo client registration/key/iss/sub/aud/client authentication policy; cả grant lẫn Client đều phải được phép.

### Bài 4 — Chuyển từ client_secret_basic sang private_key_jwt

Một service đang dùng <code>client_credentials</code> và muốn loại bỏ shared client secret để chuyển sang key pair.

**Hỏi:** Có cần đổi <code>grant_type</code> sang JWT Bearer Grant không?

**Đáp án:** Không. Grant vẫn là <code>client_credentials</code>. Chỉ thay client authentication method và cấu hình signing key, JWKS, assertion converter/token client phù hợp.

### Bài 5 — JWT Access Token

Một API nhận access token ký bằng RS256. Request cấp token ban đầu có <code>grant_type=authorization_code</code>.

**Hỏi:** Có thể gọi đây là JWT Bearer Grant không?

**Đáp án:** Không. Token output là JWT, nhưng authorization grant vẫn là authorization code.

### Bài 6 — Sai client assertion audience

Client assertion có <code>iss=sub=reports-client</code>, chữ ký đúng, nhưng <code>aud</code> trỏ sang Reports API thay vì Authorization Server.

**Hỏi:** Sửa bằng cách tắt signature validation có đúng không?

**Đáp án:** Không. Cần đặt audience theo policy của Token Endpoint và kiểm tra cả signature lẫn claims; tắt validation tạo lỗ hổng bảo mật.

### Bài 7 — Token Exchange

Request có:

~~~text
grant_type=urn:ietf:params:oauth:grant-type:token-exchange
subject_token=<JWT access token>
client_assertion_type=urn:ietf:params:oauth:client-assertion-type:jwt-bearer
client_assertion=<signed JWT>
~~~

**Hỏi:** Có bao nhiêu JWT roles trong request?

**Đáp án:** Subject token (đầu vào của **Token Exchange Grant**) và client assertion (dùng **Client authentication**). Token Exchange không biến thành JWT Bearer Grant chỉ vì subject token ở định dạng JWT.

### Bài 8 — invalid_client hay invalid_grant

Trường hợp A: Client đăng ký private_key_jwt, key chưa được đăng ký tại OP, request bị <code>invalid_client</code>.

Trường hợp B: Client authentication hợp lệ, nhưng JWT Bearer grant assertion hết hạn, request bị <code>invalid_grant</code>.

**Hỏi:** Hai lỗi cần xử lý ở lớp nào?

**Đáp án:** A kiểm tra Client authentication và key/JWKS registration. B kiểm tra grant assertion, expiry/trust/subject/audience policy. Không đổi cả hai cấu hình một cách ngẫu nhiên.

### Bài 9 — JWT có sub=user-123

Một ứng dụng tự ký JWT grant assertion với <code>sub=user-123</code> và yêu cầu scope <code>admin</code>.

**Hỏi:** Có đủ điều kiện được cấp token admin chưa?

**Đáp án:** Chưa. Authorization Server phải tin issuer và cho phép assertion đó đại diện user-123 với scope phù hợp. Chữ ký hợp lệ không thay thế ủy quyền.

### Bài 10 — Spring Security registration

Cho YAML:

~~~yaml
authorization-grant-type: client_credentials
client-authentication-method: private_key_jwt
~~~

**Hỏi:** Vì sao chỉ có hai dòng YAML chưa đủ để Token Endpoint chấp nhận?

**Đáp án:** Cần ClientRegistration hợp lệ, signing private key, public key/JWKS được OP tin cậy, token request client/converter hỗ trợ tạo JWT client assertion và chính sách alg/aud/exp/jti. Hai dòng này cũng không tạo JWT Bearer Grant.

### Bài 11 — JAR và DPoP

Một OIDC Client gửi signed Request Object tới Authorization Endpoint và một DPoP JWT proof tới Token Endpoint.

**Hỏi:** Có thể kết luận Client dùng private_key_jwt hoặc JWT Bearer Grant không?

**Đáp án:** Không. JAR bảo vệ authorization request, DPoP chứng minh sở hữu khóa cho request/token; Client authentication và grant type vẫn được xác định riêng.

### Bài 12 — Phác thảo hệ thống hoàn chỉnh

Thiết kế một Reports Worker dùng:

1. <code>client_credentials</code> để lấy service token.
2. <code>private_key_jwt</code> để xác thực Client tại Token Endpoint.
3. Private key được lưu trong KMS/HSM hoặc secret manager phù hợp.
4. Public JWKS được Authorization Server tin cậy.
5. JWT client assertion có <code>iss=sub=clientId</code>, audience theo provider, expiry ngắn, <code>jti</code> phù hợp.
6. Spring Security ClientRegistration tách grant type và client authentication method.
7. <code>OAuth2AuthorizedClientManager</code> dùng <code>clientCredentials()</code> provider.
8. Token response client có signer/converter phù hợp phiên bản.
9. Resource Server kiểm tra access token đúng issuer/audience/scope.
10. Các test riêng cho wrong audience, wrong key, expired assertion, unsupported grant, missing scope và key rotation.

Giải thích vì sao **không có bước nào yêu cầu chuyển <code>grant_type</code> sang JWT Bearer Grant**.

## 21. Ghi nhớ

- **Authorization grant** trả lời “căn cứ nào để cấp token”; **client authentication** trả lời “Client nào đang xin token và chứng minh danh tính thế nào”.
- **JWT Bearer Grant** theo RFC 7523 dùng <code>grant_type=urn:ietf:params:oauth:grant-type:jwt-bearer</code> và JWT ở tham số <code>assertion</code>.
- **JWT Client Authentication** dùng <code>client_assertion_type=urn:ietf:params:oauth:client-assertion-type:jwt-bearer</code> và JWT ở tham số <code>client_assertion</code>.
- **<code>private_key_jwt</code>** và **<code>client_secret_jwt</code>** là phương thức xác thực Client, **không phải grant types**.
- <code>client_credentials + private_key_jwt</code> vẫn là Client Credentials Grant. <code>authorization_code + private_key_jwt</code> vẫn là Authorization Code Grant.
- Có thể dùng **JWT grant assertion và JWT client assertion cùng lúc**; đó là **hai JWT có nhiệm vụ, key/trust policy và validation độc lập**.
- Token Exchange có thể mang JWT làm <code>subject_token</code> và đồng thời dùng JWT Client Authentication, nhưng grant vẫn là <code>urn:ietf:params:oauth:grant-type:token-exchange</code>.
- ID Token, JWT access token, JAR Request Object và DPoP proof cũng là JWT trong nhiều trường hợp, nhưng **không tự thay thế grant hoặc Client authentication**.
- Trong Spring Security, <code>ClientRegistration.authorizationGrantType</code> và <code>clientAuthenticationMethod</code> là hai thuộc tính khác nhau. Config private_key_jwt còn cần signer/token response client phù hợp.
- Authorization Server phải kiểm tra **issuer/subject/audience/expiry/signature/trust/replay và quyền grant**; ký được một JWT không có nghĩa được cấp token.
- Chẩn đoán theo lớp: <code>invalid_client</code> thường hướng tới Client authentication, <code>invalid_grant</code> hướng tới grant assertion/token state, <code>unsupported_grant_type</code> hướng tới grant support, <code>unauthorized_client</code> hướng tới quyền sử dụng grant.

### Tài liệu tham khảo

- **RFC 6749 — The OAuth 2.0 Authorization Framework:** Client Authentication, Token Endpoint, Authorization Grants và Extension Grants (Section 4.5).
- **RFC 7521 — Assertion Framework for OAuth 2.0 Client Authentication and Authorization Grants:** kiến trúc tách assertion grant với assertion client authentication.
- **RFC 7523 — JSON Web Token (JWT) Profile for OAuth 2.0 Client Authentication and Authorization Grants:** hai profile JWT Bearer Authorization Grant và JWT Client Authentication.
- **RFC 7519 — JSON Web Token (JWT):** claims <code>iss</code>, <code>sub</code>, <code>aud</code>, <code>exp</code>, <code>jti</code>.
- **OpenID Connect Core 1.0 — Client Authentication:** <code>private_key_jwt</code>, <code>client_secret_jwt</code>, OIDC ID Token.
- **RFC 8693 — OAuth 2.0 Token Exchange:** <code>subject_token</code>, <code>subject_token_type</code> và extension grant.
- **RFC 8628 — OAuth 2.0 Device Authorization Grant:** grant mở rộng cho thiết bị.
- **RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens:** phân biệt access token JWT với grant assertions.
- **RFC 9101 — The OAuth 2.0 JWT-Secured Authorization Request (JAR):** Request Object khác grant và client authentication.
- **RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP):** proof JWT khác Client authentication.
- **RFC 9700 — Best Current Practice for OAuth 2.0 Security:** các yêu cầu bảo vệ OAuth flow và token.
- **Spring Security Reference — OAuth2 Client:** ClientRegistration, Authorized Client Manager, Token Response Client và Client Authentication.
- **Spring Security Java API:** <code>ClientAuthenticationMethod</code>, <code>AuthorizationGrantType</code>, <code>OAuth2AuthorizedClientProviderBuilder</code>, JWT Client Authentication parameter converter theo phiên bản.
