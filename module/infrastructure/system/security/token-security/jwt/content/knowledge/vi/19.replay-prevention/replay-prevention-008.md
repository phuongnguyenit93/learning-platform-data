# DPoP và mTLS trong các hồ sơ hỗ trợ ràng buộc token

## 1. Vì sao cần ràng buộc token với người gửi?

Access token kiểu bearer có một đặc điểm quan trọng: bên nào sở hữu chuỗi token đều có thể thử sử dụng nó tại resource server, miễn là token còn hợp lệ và request đáp ứng các điều kiện khác. Nếu token bị lộ trong log, bộ nhớ, trình duyệt, thiết bị hoặc đường truyền, attacker có thể phát lại token từ một client khác.

Ví dụ:

~~~text
1. Client hợp pháp nhận access token A1.
2. A1 bị sao chép từ một nơi lưu trữ hoặc log.
3. Attacker gửi A1 tới API từ thiết bị của mình.
4. API chỉ xác minh chữ ký, issuer, audience và exp.
5. API chấp nhận A1 vì không biết người gửi hiện tại có phải client đã nhận token hay không.
~~~

TLS bảo vệ dữ liệu khi truyền qua một kết nối, nhưng bản thân bearer token vẫn có thể bị sử dụng lại nếu bị đánh cắp ở endpoint, log hoặc nơi lưu trữ. Một cách giảm rủi ro là **sender-constrained token**: token được ràng buộc với một khóa hoặc chứng thư của client. Khi sử dụng token, client phải chứng minh đang sở hữu khóa tương ứng.

Hai cơ chế OAuth phổ biến hỗ trợ mô hình này là:

- **DPoP (Demonstrating Proof of Possession):** client ký một proof JWT cho từng request bằng khóa bất đối xứng; token được ràng buộc với thumbprint của public key.
- **mTLS certificate-bound access token:** access token được ràng buộc với chứng thư client; resource server xác minh chứng thư được dùng trong kết nối TLS có khớp với token hay không.

Nguyên tắc cốt lõi:

> **Sender constraint biến việc sở hữu token thành chưa đủ: client còn phải chứng minh quyền sở hữu khóa hoặc chứng thư đã được gắn với token.**

Bài này thuộc phạm vi Security chung của OAuth 2.0, JWT và chống replay. DPoP và mTLS có thể áp dụng cho nhiều loại access token; token có thể là JWT hoặc opaque tùy profile. Nội dung không phụ thuộc ngôn ngữ lập trình hoặc framework cụ thể.

## 2. Bearer token và sender-constrained token

### 2.1. Bearer token

Với bearer token, client thường gửi:

~~~http
GET /accounts/ACC-100 HTTP/1.1
Host: api.example.test
Authorization: Bearer <access-token>
~~~

Resource server kiểm tra token và quyết định quyền. Nếu attacker lấy được token, họ có thể gửi cùng token từ một thiết bị khác.

### 2.2. Sender-constrained token

Với sender-constrained token, Authorization Server gắn token với một bằng chứng mật mã của client:

~~~text
Access token T
    |
    +---- bound to public key/certificate K

Request:
    access token T
    + proof of possession of K
~~~

Resource server kiểm tra cả token lẫn bằng chứng sở hữu. Một bản sao token bị đánh cắp riêng lẻ không đủ để vượt qua kiểm tra này.

### 2.3. Sender constraint không thay thế authorization

Ràng buộc token với khóa chỉ trả lời câu hỏi “request có chứng minh được quyền sở hữu khóa đã gắn với token không?”. API vẫn phải kiểm tra:

- Chữ ký hoặc trạng thái token.
- Issuer và audience.
- Thời hạn và token profile.
- Scope hoặc permission.
- Tenant, owner và quyền trên object cụ thể.
- Trạng thái nghiệp vụ của tài nguyên.

Một client sở hữu đúng khóa vẫn có thể gửi request đọc tài nguyên mà user không có quyền đọc. Sender constraint chống việc dùng lại token từ bên không sở hữu khóa; nó không tự cấp quyền truy cập.

## 3. DPoP hoạt động như thế nào?

DPoP là cơ chế proof-of-possession ở tầng ứng dụng được định nghĩa trong RFC 9449. Client tạo một cặp khóa bất đối xứng và dùng private key để ký một JWT proof cho request. Public key được đưa vào JOSE header của proof để server có thể xác minh chữ ký.

Khi cấp access token, Authorization Server ràng buộc token với thumbprint của public key. Khi client gọi resource server, client gửi access token cùng DPoP proof mới. Resource server kiểm tra proof và xác nhận public key trong proof đúng là khóa đã gắn với token.

Luồng tổng quát:

~~~mermaid
sequenceDiagram
    participant C as Client
    participant AS as Authorization Server
    participant RS as Resource Server
    C->>C: Tạo key pair Kpriv/Kpub
    C->>AS: Token request + DPoP proof ký bằng Kpriv
    AS->>AS: Xác minh proof và client/grant
    AS->>AS: Tính JWK thumbprint của Kpub
    AS-->>C: Access token có cnf.jkt + token_type DPoP
    C->>C: Tạo proof mới cho từng API request
    C->>RS: Authorization: DPoP token + DPoP proof
    RS->>RS: Xác minh proof, ath, htm, htu, iat, jti
    RS->>RS: So khớp thumbprint với cnf.jkt
    RS-->>C: Kết quả nếu token và authorization policy hợp lệ
~~~

### 3.1. Key pair của DPoP

Client giữ private key và công bố public key trong proof. DPoP sử dụng thuật toán ký bất đối xứng; không dùng shared secret HMAC làm khóa proof chung giữa client và server.

Public key phải được biểu diễn trong JWK. Private key material không được đưa vào proof.

Ví dụ header minh họa:

~~~json
{
  "typ": "dpop+jwt",
  "alg": "ES256",
  "jwk": {
    "kty": "EC",
    "crv": "P-256",
    "x": "public-x-coordinate",
    "y": "public-y-coordinate"
  }
}
~~~

Đây là dữ liệu minh họa, không phải một proof JWT có chữ ký thực. typ nhận diện DPoP proof; alg là thuật toán bất đối xứng được hỗ trợ; jwk chứa public key dùng xác minh chữ ký.

### 3.2. Access token được gắn với public key

Authorization Server tính JWK thumbprint theo RFC 7638 và gắn giá trị đó vào confirmation claim cnf.jkt của access token.

Ví dụ payload access token:

~~~json
{
  "iss": "https://identity.example.test",
  "sub": "user-514",
  "aud": "https://api.example.test/accounts",
  "exp": 1900003600,
  "scope": "account:read",
  "cnf": {
    "jkt": "base64url-jwk-thumbprint"
  }
}
~~~

cnf.jkt là thumbprint của public key được dùng để ký DPoP proof. Nó ràng buộc access token với key pair đó. Với opaque access token, resource server có thể nhận thông tin cnf qua introspection hoặc cơ chế xác minh tương ứng.

### 3.3. Thumbprint không phải fingerprint tùy ý

JWK thumbprint phải được tính theo quy tắc chuẩn RFC 7638 trên các thành phần public key bắt buộc của loại khóa. Không hash toàn bộ JSON JWK theo thứ tự byte tùy ý vì thứ tự thuộc tính hoặc trường không liên quan có thể làm kết quả khác nhau.

Authorization Server và resource server phải dùng cùng quy tắc thumbprint. Nếu tính khác nhau, client hợp pháp có thể bị từ chối hoặc token có thể bị gắn nhầm khóa.

## 4. Cấu trúc DPoP proof JWT

DPoP proof là một JWT được client ký cho một HTTP request cụ thể. Proof không phải access token và không thay thế access token.

Một proof cho request tới resource server có thể có payload:

~~~json
{
  "jti": "proof-id-unique-9281",
  "htm": "GET",
  "htu": "https://api.example.test/accounts/ACC-100",
  "iat": 1900000100,
  "ath": "base64url-sha256-of-access-token",
  "nonce": "server-issued-nonce"
}
~~~

Các claim chính:

| Claim | Ý nghĩa |
| --- | --- |
| jti | Định danh duy nhất của proof để hỗ trợ phát hiện replay. |
| htm | HTTP method mà proof được tạo cho, ví dụ GET hoặc POST. |
| htu | HTTP URI của endpoint đích theo quy tắc DPoP; không bao gồm query và fragment. |
| iat | Thời điểm proof được tạo. |
| ath | Hash của access token được gửi tới resource server. |
| nonce | Nonce do Authorization Server hoặc resource server cấp nếu server yêu cầu. |

ath được yêu cầu khi DPoP proof đi cùng access token tới resource server. Tại token endpoint, proof không gắn với access token đang được trình bày nên thông thường không có ath.

### 4.1. jti: định danh proof duy nhất

Client tạo jti mới cho mỗi proof. Không tái sử dụng một proof JWT cho nhiều request.

Server có thể lưu cặp thumbprint và jti đã chấp nhận trong một khoảng thời gian:

~~~text
replay_cache_key = (jkt, jti)
~~~

Khi cùng proof xuất hiện lần thứ hai trong thời gian còn hiệu lực, server từ chối vì proof đã được sử dụng. Việc ghi vào replay cache cần atomic để hai request đồng thời không cùng vượt qua kiểm tra.

### 4.2. htm: ràng buộc HTTP method

htm phải khớp method của request thực tế. Proof được tạo cho GET không thể được dùng lại cho POST.

Server cần so khớp chính xác theo quy tắc DPoP và không tự chuẩn hóa method theo cách làm thay đổi ngữ nghĩa request.

### 4.3. htu: ràng buộc URI đích

htu xác định URI của endpoint đích. Theo DPoP, query và fragment không nằm trong giá trị htu. Vì vậy, proof gắn với method và URI endpoint theo định nghĩa của chuẩn, nhưng không phải chữ ký toàn bộ HTTP message.

Ví dụ:

~~~text
Request URL:
https://api.example.test/accounts/ACC-100?view=summary

DPoP htu:
https://api.example.test/accounts/ACC-100
~~~

Resource server cần áp dụng cùng cách xác định URI đích mà client và proxy đã thống nhất. Không tin forwarded host/scheme do client tự gửi khi API nằm sau reverse proxy.

### 4.4. iat: giới hạn tuổi proof

iat cho biết proof được tạo lúc nào. Server cần giới hạn khoảng thời gian chấp nhận để proof cũ không thể được phát lại vô thời hạn.

Đồng hồ client và server có thể lệch nhau, vì vậy cần clock skew hợp lý. Cửa sổ chấp nhận càng rộng thì proof bị đánh cắp càng có thời gian bị thử lại; cửa sổ quá hẹp lại làm client hợp pháp bị lỗi do clock drift hoặc mạng chậm.

### 4.5. ath: gắn proof với đúng access token

Khi gọi resource server, proof chứa ath được tính từ access token:

\[
ath = BASE64URL(SHA256(ASCII(access\_token)))
\]

Server tính lại giá trị từ token nhận được và so khớp. Điều này ngăn attacker lấy một DPoP proof hợp lệ rồi ghép nó với một access token khác.

ath là hash của chuỗi access token được gửi, không phải hash của payload JWT đã giải mã.

### 4.6. nonce: thách thức do server cấp

Authorization Server hoặc resource server có thể yêu cầu client đưa nonce vào proof. Server gửi nonce qua response header DPoP-Nonce; client phải tạo proof mới có claim nonce tương ứng.

Nonce giúp server yêu cầu proof gắn với một thách thức gần đây, giảm khả năng attacker chuẩn bị trước proof hoặc phát lại proof cũ ngoài ngữ cảnh. Nonce không thay thế việc kiểm tra jti, thời gian, method, URI và token binding.

## 5. DPoP tại token endpoint

Client có thể gửi DPoP proof tới Authorization Server khi xin access token. Authorization Server xác minh proof, tính thumbprint của public key và ràng buộc access token được cấp với key đó.

Request minh họa:

~~~http
POST /token HTTP/1.1
Host: identity.example.test
Content-Type: application/x-www-form-urlencoded
DPoP: <signed-dpop-proof>

grant_type=authorization_code&
code=<authorization-code>&
redirect_uri=https%3A%2F%2Fclient.example.test%2Fcallback
~~~

Phản hồi minh họa:

~~~json
{
  "access_token": "<dpop-bound-access-token>",
  "token_type": "DPoP",
  "expires_in": 300
}
~~~

Token endpoint vẫn phải kiểm tra grant, client authentication nếu có, redirect URI và các điều kiện OAuth khác. DPoP proof chứng minh client đang sở hữu private key tương ứng; nó không thay thế mọi phương thức xác thực client.

### 5.1. Proof cho token endpoint

Proof cần ràng buộc với method và URI của token endpoint. Authorization Server xác minh chữ ký bằng public JWK trong header, kiểm tra typ, alg, jti, htm, htu, iat và nonce nếu đã yêu cầu.

Nếu token endpoint cấp token gắn với DPoP key, nó đưa thumbprint tương ứng vào cnf.jkt. Client phải tiếp tục dùng đúng key pair khi gọi resource server.

### 5.2. DPoP không đồng nghĩa client authentication

Một public client có thể dùng DPoP để chứng minh đang giữ key đã ràng buộc với token. Điều đó không biến public client thành confidential client và không tạo ra một client secret.

Với confidential client, DPoP có thể bổ sung cho client authentication. Authorization Server vẫn xác thực client theo phương thức đã đăng ký và kiểm tra DPoP proof theo policy.

## 6. DPoP tại resource server

Khi gọi API, client tạo một proof mới cho request đó và gửi cùng access token.

Request minh họa:

~~~http
GET /accounts/ACC-100 HTTP/1.1
Host: api.example.test
Authorization: DPoP <access-token>
DPoP: <new-signed-dpop-proof>
~~~

Với DPoP-bound access token, client dùng authentication scheme DPoP để trình bày access token. Không đổi thành Bearer rồi bỏ proof.

Resource server cần:

1. Xác minh access token theo issuer, audience, thời gian, profile và chữ ký/introspection.
2. Xác định cnf.jkt của token.
3. Đọc DPoP proof trong header DPoP.
4. Kiểm tra typ là dpop+jwt và thuật toán nằm trong allowlist bất đối xứng.
5. Xác minh proof signature bằng public JWK trong header.
6. Tính thumbprint của public JWK và so với cnf.jkt.
7. Kiểm tra htm và htu khớp request.
8. Kiểm tra iat, jti, nonce nếu được yêu cầu.
9. Tính lại ath và so với claim trong proof.
10. Chỉ sau đó mới đánh giá scope, tenant và quyền trên resource.

### 6.1. Không chấp nhận public key không khớp token

Attacker có thể tự tạo key pair của họ và ký proof hợp lệ bằng private key của họ. Chữ ký proof tự nó chưa đủ. Thumbprint của public key phải khớp cnf.jkt đã gắn trong access token.

Nếu không khớp, request bị từ chối dù proof có chữ ký hợp lệ.

### 6.2. Không tái sử dụng proof

Mỗi HTTP request cần proof mới, với jti mới và method/URI phù hợp. Không cache một proof rồi gửi lại cho các request khác.

### 6.3. DPoP proof không ký toàn bộ request body

Các claim cơ bản của DPoP ràng buộc method, URI endpoint, thời điểm và access token. Chúng không phải cơ chế ký mọi header hoặc body. Nếu ứng dụng cần bảo vệ tính toàn vẹn nội dung body, cần một cơ chế phù hợp khác và một hợp đồng rõ ràng.

## 7. Phát hiện replay của DPoP proof

DPoP hỗ trợ phát hiện replay bằng jti, thời gian và nonce. Một triển khai nên kết hợp các yếu tố này.

### 7.1. Replay cache

Resource server có thể lưu proof đã chấp nhận:

~~~text
key = (jkt, jti)
value = accepted_at
TTL = proof_acceptance_window + clock_skew
~~~

Thao tác phải tương đương insert-if-absent. Nếu key đã tồn tại, proof bị từ chối.

Không dùng cache chỉ trong bộ nhớ của một instance nếu cùng API chạy trên nhiều instance/region và attacker có thể phát lại sang instance khác. Cần replay store dùng chung hoặc một kiến trúc bảo đảm request có cùng key luôn được xử lý tại vùng có trạng thái nhất quán.

### 7.2. Nonce và jti bổ sung cho nhau

- jti giúp phát hiện cùng một proof đã được dùng.
- iat giới hạn tuổi proof.
- nonce cho phép server đưa ra thách thức mới.
- htm, htu và ath gắn proof với request và token cụ thể.

Không nên coi một nonce cố định, tồn tại vô thời hạn là biện pháp chống replay đầy đủ. Nonce cần được quản lý theo policy về thời hạn, phạm vi và khả năng sử dụng lại.

### 7.3. Unknown nonce hoặc proof thiếu nonce

Nếu server đã yêu cầu nonce, proof không có nonce hoặc dùng nonce sai phải bị từ chối. Server có thể trả response yêu cầu nonce mới để client tạo proof khác.

Client không nên sửa claim trong proof cũ vì chữ ký sẽ không còn hợp lệ. Nó phải tạo và ký một proof JWT mới.

### 7.4. Replay store và tính nhất quán

Với hệ thống phân tán:

- jti phải được ghi atomic trước khi request được cho phép.
- Các instance phải dùng cùng namespace key và quy tắc TTL.
- Cache phải tồn tại ít nhất trong cửa sổ proof có thể được chấp nhận.
- Đồng bộ thời gian giữa các node.
- Có rate limit cho proof sai và nonce challenge.
- Không để cache outage tự động biến replay check thành ALLOW.

## 8. DPoP với refresh token

DPoP không chỉ hữu ích cho access token. Authorization Server có thể ràng buộc refresh token với DPoP key và yêu cầu proof khi client sử dụng refresh token.

Khi refresh:

- Client gửi refresh token tới token endpoint.
- Client gửi DPoP proof mới được ký bằng key đã ràng buộc.
- Authorization Server kiểm tra proof và key binding.
- Server kiểm tra refresh token, client/grant và scope theo policy.
- Nếu rotation được áp dụng, server phát hành refresh token kế tiếp với ràng buộc phù hợp.

Nếu refresh token bị đánh cắp nhưng attacker không có private key, sender constraint làm giảm khả năng attacker sử dụng token. Nếu attacker lấy được cả token và khả năng sử dụng private key, hệ thống vẫn cần rotation, reuse detection và incident response.

DPoP key rotation cần được thiết kế cẩn thận: token đang ràng buộc với thumbprint cũ không tự chuyển sang key mới. Client cần quy trình cấp token mới hoặc một luồng thay đổi binding được Authorization Server hỗ trợ.

## 9. mTLS certificate-bound access token hoạt động như thế nào?

Mutual TLS (mTLS) là TLS trong đó client và server xác thực chứng thư của nhau. Trong OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens (RFC 8705), Authorization Server có thể ràng buộc access token với chứng thư X.509 mà client sử dụng.

Luồng tổng quát:

~~~mermaid
sequenceDiagram
    participant C as Client
    participant AS as Authorization Server
    participant RS as Resource Server
    C->>AS: TLS handshake + client certificate
    C->>AS: Token request
    AS->>AS: Xác minh client/certificate và grant
    AS->>AS: Tính SHA-256 thumbprint của certificate
    AS-->>C: Access token có cnf.x5t#S256
    C->>RS: TLS handshake + cùng client certificate
    C->>RS: Authorization: Bearer access token
    RS->>RS: So certificate thumbprint với cnf.x5t#S256
    RS-->>C: Chấp nhận nếu binding và policy hợp lệ
~~~

Khác với DPoP, bằng chứng sở hữu trong mTLS đến từ TLS handshake và private key của chứng thư client. Client không cần tạo một DPoP proof JWT riêng cho từng HTTP request.

### 9.1. Confirmation claim cnf.x5t#S256

Access token certificate-bound có thể chứa:

~~~json
{
  "iss": "https://identity.example.test",
  "sub": "service-17",
  "aud": "https://api.example.test/payments",
  "exp": 1900003600,
  "cnf": {
    "x5t#S256": "base64url-sha256-certificate-thumbprint"
  }
}
~~~

x5t#S256 là SHA-256 thumbprint của chứng thư X.509 client theo cách biểu diễn được RFC 8705 quy định. Nó được tính từ DER encoding của chứng thư, sau đó mã hóa base64url không padding.

Resource server lấy chứng thư client đã được xác minh trong TLS connection, tính thumbprint và so khớp với giá trị trong cnf.x5t#S256.

### 9.2. Token có thể là JWT hoặc opaque

Certificate binding không bắt buộc access token phải là JWT. Nếu token opaque, resource server có thể dùng introspection hoặc cơ chế được Authorization Server hỗ trợ để lấy confirmation claim và trạng thái token.

Nếu token là JWT, resource server phải xác minh chữ ký, issuer, audience và các claim thông thường trước khi tin cnf.

### 9.3. Cách trình bày access token

Với certificate-bound access token, client vẫn có thể sử dụng phương thức trình bày access token OAuth thông thường, thường là:

~~~http
Authorization: Bearer <certificate-bound-access-token>
~~~

Điểm ràng buộc nằm ở TLS client certificate của kết nối. Token không được chấp nhận nếu chứng thư được dùng trong kết nối không khớp với thumbprint đã gắn trong token.

## 10. Phân biệt mTLS client authentication và certificate-bound token

Hai chức năng này liên quan nhưng không đồng nghĩa.

### 10.1. mTLS client authentication tại token endpoint

Authorization Server có thể dùng chứng thư client để xác thực confidential client. Trong OAuth, các phương thức như tls_client_auth và self_signed_tls_client_auth được định nghĩa cho client authentication.

Mục đích là trả lời:

> Client nào đang gọi token endpoint?

### 10.2. Certificate-bound access token

Authorization Server có thể gắn access token với chứng thư. Resource server kiểm tra client đang trình token có dùng đúng chứng thư hay không.

Mục đích là trả lời:

> Bên đang sử dụng access token có chứng minh được quyền sở hữu chứng thư đã gắn với token không?

### 10.3. Có thể dùng một chức năng mà không dùng chức năng kia

Một client có thể được xác thực bằng mTLS tại token endpoint nhưng access token được cấp không có certificate binding. Khi đó, việc xác thực client lúc cấp token không tự làm access token trở thành sender-constrained.

Ngược lại, Authorization Server có thể cấp certificate-bound token theo một policy phù hợp; resource server vẫn phải kiểm tra chứng thư trong kết nối khi token được sử dụng.

Khi thiết kế, phải cấu hình và kiểm thử riêng hai hành vi. Không suy luận certificate-bound access token chỉ từ việc token endpoint có TLS client authentication.

## 11. Kiểm tra certificate binding tại resource server

Một resource server nhận certificate-bound token cần:

1. Thiết lập TLS với client và yêu cầu client certificate theo cấu hình.
2. Xác minh certificate chain, validity, key usage, extended key usage và trust policy.
3. Xác định chính xác chứng thư client được dùng trong TLS connection.
4. Xác minh access token theo profile, issuer, audience và thời hạn.
5. Đọc cnf.x5t#S256 từ token đã xác minh hoặc introspection response tin cậy.
6. Tính SHA-256 thumbprint của client certificate.
7. So khớp chính xác hai giá trị.
8. Tiếp tục kiểm tra scope, tenant và resource authorization.

Nếu thiếu client certificate hoặc thumbprint không khớp, request bị từ chối dù bearer token có chữ ký hợp lệ.

### 11.1. Chứng thư nào được dùng để tính thumbprint?

Binding áp dụng với client certificate được dùng theo cơ chế RFC 8705. Không tự chọn một intermediate CA hoặc root CA thay cho leaf certificate của client. Cần dùng đúng certificate object mà TLS authentication xác định là chứng thư client.

### 11.2. Kiểm tra chain và binding là hai việc khác nhau

- Certificate path validation trả lời chứng thư có được tin theo PKI/trust configuration không.
- Certificate thumbprint comparison trả lời chứng thư được dùng có đúng chứng thư đã gắn với token không.

Chỉ so thumbprint mà không xác minh chứng thư theo trust policy là chưa đủ. Ngược lại, chứng thư hợp lệ do CA tin cậy cấp cũng chưa đủ nếu thumbprint không khớp token.

### 11.3. Không dùng subject DN làm binding duy nhất

Subject Distinguished Name có thể trùng, thay đổi hoặc được cấp lại. Certificate-bound token dùng thumbprint để ràng buộc với chứng thư cụ thể. Không thay thế bằng so khớp chuỗi CN, SAN hoặc tên service nếu hợp đồng yêu cầu certificate thumbprint.

## 12. mTLS khi có reverse proxy hoặc TLS termination

mTLS có một yêu cầu triển khai quan trọng: resource server phải biết chứng thư nào thực sự được dùng bởi client trên kết nối đã được xác thực.

Nếu TLS kết thúc ở API Gateway hoặc load balancer, kết nối từ Gateway tới API backend là một TLS connection khác. Backend thường chỉ nhìn thấy chứng thư của Gateway, không tự động nhìn thấy chứng thư client ban đầu.

### 12.1. Rủi ro forwarded certificate header

Một proxy có thể chuyển thông tin chứng thư qua header:

~~~http
X-Client-Cert: <certificate-information>
~~~

Nếu backend tin header này mà không xác thực nguồn, client có thể tự gửi header giả để mạo danh một certificate thumbprint.

### 12.2. Các cách triển khai

- **TLS passthrough:** giữ kết nối TLS đến thành phần cần xác minh client certificate, nếu kiến trúc hỗ trợ.
- **Gateway thực hiện binding check:** Gateway xác minh token và client certificate, sau đó chuyển kết quả qua kênh nội bộ đã xác thực; backend chỉ tin Gateway theo một hợp đồng rõ.
- **Trusted certificate forwarding:** proxy xóa header do client gửi, tự thêm dữ liệu đã xác minh và backend chỉ chấp nhận kết nối từ proxy qua mTLS hoặc cơ chế service identity tương đương.

Không để backend có đường truy cập trực tiếp từ client nếu nó dựa vào header do proxy thêm. Cần bảo vệ tính toàn vẹn của header, giới hạn nguồn và ngăn spoofing.

### 12.3. Service mesh không tự giải quyết user binding

Service mesh có thể dùng mTLS để xác thực workload giữa các service. Điều đó chứng minh service caller theo workload identity, nhưng không tự chứng minh access token của user được ràng buộc với chứng thư client tương ứng.

Phải phân biệt:

- Chứng thư workload của service-to-service connection.
- Chứng thư client gắn với access token.
- Subject/user được token đại diện.

Nếu dùng cùng một lớp mTLS cho nhiều mục đích, hợp đồng phải chỉ rõ certificate nào được dùng để kiểm tra cnf.x5t#S256.

## 13. Vòng đời khóa DPoP và chứng thư mTLS

Sender-constrained token chỉ hoạt động khi client giữ được khóa hoặc chứng thư phù hợp trong suốt thời gian token còn hiệu lực.

### 13.1. DPoP key lifecycle

Client cần:

- Sinh key pair bằng thuật toán và độ dài khóa được hỗ trợ.
- Giữ private key trong vùng lưu trữ phù hợp.
- Không gửi private key lên Authorization Server.
- Dùng đúng key pair cho token đã ràng buộc.
- Xử lý khi key bị mất, xóa hoặc compromise.
- Cấp token mới nếu cần đổi sang key pair khác.

Nếu token có cnf.jkt gắn với key A, proof ký bằng key B không hợp lệ dù cả hai key đều do cùng ứng dụng tạo.

### 13.2. DPoP key có thể không exportable nhưng không tuyệt đối an toàn

Lưu private key trong secure hardware hoặc keystore không exportable giúp giảm khả năng attacker lấy raw private key. Tuy nhiên, malware hoặc XSS có thể tìm cách yêu cầu môi trường client ký proof nếu nó kiểm soát được ứng dụng hoặc có quyền gọi thao tác ký.

Vì vậy, bảo vệ key cần đi cùng:

- Giảm bề mặt XSS và malware.
- Giới hạn quyền gọi key operation.
- Kiểm tra origin/application context nếu nền tảng hỗ trợ.
- Rotation và revoke khi thiết bị bị compromise.
- Thời hạn token phù hợp.

### 13.3. Certificate rotation

Với mTLS certificate-bound token, thumbprint gắn với chứng thư cụ thể. Khi chứng thư được cấp lại, thumbprint thường thay đổi ngay cả khi cùng public key được giữ lại, vì chứng thư DER đã thay đổi.

Vì vậy:

1. Cấp hoặc đăng ký chứng thư mới.
2. Lấy access token mới được ràng buộc với thumbprint mới.
3. Cho phép token cũ dùng chứng thư cũ trong khoảng chuyển tiếp nếu policy cho phép.
4. Chuyển traffic sang chứng thư mới.
5. Ngừng chứng thư cũ và thu hồi token cũ theo policy.

Không giả định chứng thư mới tự dùng được với token đã bound vào chứng thư cũ.

### 13.4. Mất hoặc compromise private key

Nếu private key DPoP hoặc private key chứng thư mTLS bị lộ, attacker có thể tạo proof hoặc thiết lập TLS client authentication tương ứng. Cần:

- Thu hồi token/grant gắn với key.
- Đánh dấu key/certificate bị compromise.
- Phát hành key/certificate mới.
- Vô hiệu hóa binding cũ theo khả năng hệ thống.
- Kiểm tra access token đã cấp và phạm vi sử dụng.
- Ghi audit và thực hiện incident response.

## 14. So sánh DPoP và mTLS

| Tiêu chí | DPoP | mTLS certificate-bound token |
| --- | --- | --- |
| Cơ chế proof | JWT proof ký bằng private key cho request. | Client certificate trong TLS handshake. |
| Token binding | cnf.jkt chứa JWK thumbprint. | cnf.x5t#S256 chứa certificate thumbprint. |
| Proof ở API request | Header DPoP mới cho mỗi request. | Client certificate được xác thực trên TLS connection. |
| Authorization header | DPoP <access-token>. | Thông thường Bearer <access-token> cùng mTLS connection. |
| Ràng buộc method/URI | Proof có htm và htu. | Không có claim method/URI riêng trong certificate binding. |
| Replay detection | jti, iat, nonce và replay cache. | TLS proof-of-possession và bảo vệ TLS; không có DPoP-style jti cho từng HTTP request. |
| Phụ thuộc TLS client certificate | Không. Vẫn cần TLS thông thường. | Có. |
| Client phù hợp | Public client, mobile, browser hoặc client khó quản lý certificate. | Confidential client, workload/service hoặc môi trường quản lý PKI tốt. |
| Triển khai proxy | Cần xử lý URI bên ngoài và forwarded headers đáng tin. | Cần bảo toàn hoặc chuyển tiếp danh tính certificate đã xác minh. |
| Vòng đời credential | Quản lý key pair và thumbprint. | Quản lý certificate, chain, private key và thumbprint. |
| Giới hạn chính | Ai kiểm soát được thao tác ký có thể tạo proof; proof không ký toàn bộ body. | TLS termination và certificate lifecycle phức tạp; private key compromise vẫn nguy hiểm. |

### 14.1. Khi nào nên chọn DPoP?

DPoP thường phù hợp khi:

- Client là public client và khó triển khai client certificate.
- Cần binding ở tầng ứng dụng mà không phụ thuộc mTLS client authentication.
- Client có thể giữ private key an toàn tương đối.
- Hệ thống có khả năng tạo và kiểm tra proof cho từng request.
- Có thể triển khai replay cache, nonce và clock policy.

### 14.2. Khi nào nên chọn mTLS?

mTLS thường phù hợp khi:

- Client là backend service hoặc workload được quản lý.
- Tổ chức có PKI và quy trình cấp/thu hồi certificate.
- Có thể yêu cầu client certificate end-to-end hoặc có proxy tin cậy xử lý binding.
- Hệ thống cần xác thực workload ở tầng kết nối.
- Certificate private key có thể được bảo vệ bằng HSM, TPM hoặc keystore phù hợp.

### 14.3. Có thể kết hợp cả hai không?

Một hệ thống có thể dùng mTLS để xác thực kết nối service-to-service và DPoP để ràng buộc access token với client key. Tuy nhiên, cần xác định rõ từng cơ chế bảo vệ điều gì và tránh tạo nhiều binding khó vận hành.

Kết hợp chỉ có ích khi threat model yêu cầu và các bên thực sự xác minh cả hai. Việc bật hai cơ chế nhưng một tầng proxy bỏ qua binding sẽ tạo cảm giác an toàn giả.

## 15. Những gì DPoP và mTLS không giải quyết

Sender constraint giảm khả năng sử dụng token bị đánh cắp riêng lẻ, nhưng không loại bỏ mọi kiểu tấn công.

### 15.1. Attacker kiểm soát client

Nếu attacker kiểm soát thiết bị, tiến trình hoặc ứng dụng có quyền dùng private key, họ có thể yêu cầu client ký proof hoặc dùng certificate để thiết lập kết nối. Non-exportable key làm khó việc trích xuất nhưng không ngăn mọi thao tác ký trái phép.

### 15.2. Token và private key cùng bị lộ

Nếu attacker lấy được cả token và private key, sender constraint có thể không còn bảo vệ. Cần revoke token/key, rotate credential và điều tra phạm vi compromise.

### 15.3. Replay trong cửa sổ chấp nhận

DPoP proof có thể bị replay nếu server không kiểm tra jti, tuổi proof hoặc nonce. mTLS cung cấp proof-of-possession ở TLS layer, nhưng không ngăn một client hợp pháp có quyền gửi cùng một thao tác nghiệp vụ hai lần.

Với giao dịch có side effect, API vẫn cần idempotency key, transaction control hoặc nghiệp vụ chống xử lý lặp.

### 15.4. Compromise của Authorization Server hoặc issuer

Nếu attacker kiểm soát issuer hoặc khóa ký access token, họ có thể phát hành token có binding tới key do họ kiểm soát. Sender constraint không thay thế bảo vệ Authorization Server, signing keys và trust configuration.

### 15.5. Authorization sai

Một token được ràng buộc đúng key vẫn có thể chứa scope quá rộng hoặc được dùng trên object không thuộc quyền. API vẫn phải thực hiện object-level authorization.

## 16. Pseudocode: xác minh DPoP-bound access token

Ví dụ dưới đây mô tả các bước logic tại resource server. Các hàm JWT, JWK, hash, URI và replay store là khái niệm; triển khai thực tế phải dùng thư viện chuẩn đã được kiểm chứng.

~~~text
function verifyDpopRequest(request):
    accessToken = extractAuthorizationToken(request)
    if authorizationScheme(request) != "DPoP":
        return REJECT

    token = validateAccessToken(
        accessToken,
        trustedIssuer = configuredIssuer,
        expectedAudience = thisResourceServer
    )
    if token.failed:
        return REJECT

    expectedJkt = token.claims.cnf.jkt
    if expectedJkt is missing:
        return REJECT

    proof = parseJwt(request.headers["DPoP"])
    if proof.header.typ != "dpop+jwt":
        return REJECT
    if proof.header.alg not in asymmetricDpopAlgorithmAllowlist:
        return REJECT
    if proof.header.jwk contains private key material:
        return REJECT

    publicKey = parsePublicJwk(proof.header.jwk)
    if not verifyJwtSignature(proof, publicKey):
        return REJECT

    actualJkt = jwkThumbprint(publicKey)
    if actualJkt != expectedJkt:
        return REJECT

    if proof.claims.htm != request.method:
        return REJECT
    if proof.claims.htu != canonicalDpopTargetUri(request):
        return REJECT
    if not proofIssuedWithinAllowedWindow(proof.claims.iat):
        return REJECT

    expectedAth = base64url(sha256(ascii(accessToken)))
    if proof.claims.ath != expectedAth:
        return REJECT

    if serverRequiresNonce and not validNonce(proof.claims.nonce):
        return CHALLENGE_WITH_DPOP_NONCE

    replayKey = (actualJkt, proof.claims.jti)
    if not replayStore.insertIfAbsent(replayKey, proofExpiry):
        return REJECT_REPLAY

    return VERIFIED_SENDER_AND_TOKEN(token)
~~~

Sau khi proof và token hợp lệ, resource server vẫn phải đánh giá scope, tenant, owner, action và resource policy. canonicalDpopTargetUri phải sử dụng thông tin URI bên ngoài đã được xác minh nếu request đi qua proxy; không lấy forwarded header tùy ý từ client.

## 17. Pseudocode: xác minh mTLS certificate-bound token

~~~text
function verifyMtlsBoundRequest(request, tlsConnection):
    accessToken = extractBearerToken(request)
    token = validateAccessTokenOrIntrospect(
        accessToken,
        trustedIssuer = configuredIssuer,
        expectedAudience = thisResourceServer
    )
    if token.failed:
        return REJECT

    expectedThumbprint = token.claims.cnf["x5t#S256"]
    if expectedThumbprint is missing:
        return REJECT_IF_CERTIFICATE_BOUND_TOKEN_REQUIRED

    clientCertificate = tlsConnection.verifiedClientCertificate
    if clientCertificate is missing:
        return REJECT

    if not validateCertificatePathAndUsage(clientCertificate):
        return REJECT

    actualThumbprint = base64url(
        sha256(derEncode(clientCertificate))
    )
    if actualThumbprint != expectedThumbprint:
        return REJECT

    return VERIFIED_SENDER_AND_TOKEN(token)
~~~

Nếu TLS kết thúc tại proxy, verifiedClientCertificate chỉ đáng tin khi backend nhận được thông tin đã xác minh qua một kênh nội bộ được xác thực, proxy xóa mọi header giả mạo và backend không thể bị gọi vòng qua proxy. Sau bước binding, API vẫn phải thực hiện authorization trên tài nguyên.

## 18. Lỗi thường gặp khi triển khai

| Sai lầm | Rủi ro | Cách phòng tránh |
| --- | --- | --- |
| Dùng DPoP proof như access token | Proof không mang quyền truy cập API thay cho token. | Gửi access token và proof theo đúng giao thức. |
| Trình DPoP-bound token bằng Bearer | Bỏ qua sender proof và sai authentication scheme. | Dùng Authorization: DPoP cùng header proof. |
| Tái sử dụng một proof cho nhiều request | Replay proof hoặc method/URI không khớp. | Tạo proof mới và jti mới cho mỗi request. |
| Không kiểm tra cnf.jkt | Attacker ký proof bằng key của họ rồi ghép token bị đánh cắp. | So thumbprint public JWK với token binding. |
| Không kiểm tra ath | Proof hợp lệ có thể bị ghép với access token khác. | Tính lại hash của access token. |
| Bỏ qua htm hoặc htu | Proof có thể được dùng cho request khác. | So khớp method và URI theo RFC 9449. |
| Không có replay cache cho jti | Cùng proof có thể được gửi lại trong cửa sổ thời gian. | Atomic replay detection và TTL phù hợp. |
| Dùng nonce cố định vô thời hạn | Thách thức không còn đủ mới. | Quản lý nonce theo policy và vòng đời ngắn. |
| Tin public JWK có private material | Key leakage hoặc sai định dạng proof. | Chỉ chấp nhận public JWK trong proof. |
| Cho phép thuật toán tùy ý từ header | Algorithm confusion hoặc thuật toán yếu. | Allowlist thuật toán bất đối xứng độc lập. |
| Không tính đến reverse proxy khi kiểm tra htu | Client hợp pháp bị từ chối hoặc URI spoofing. | Dùng external URI từ proxy đã xác thực và cấu hình chuẩn hóa thống nhất. |
| Coi mTLS client authentication là certificate-bound token | Access token có thể vẫn là bearer. | Kiểm tra cnf.x5t#S256 và certificate ở resource server. |
| Tin certificate header do client gửi | Mạo danh chứng thư. | Proxy xóa header client, backend xác thực proxy. |
| So khớp subject DN thay thumbprint | Chứng thư khác có thể cùng tên. | So khớp certificate thumbprint theo RFC 8705. |
| Không quản lý certificate rotation | Token cũ không khớp chứng thư mới. | Cấp token mới và có overlap chuyển đổi. |
| Coi sender constraint thay authorization | User có key vẫn truy cập object ngoài quyền. | Kiểm tra scope, tenant và object policy. |

## 19. Kịch bản kiểm thử DPoP và mTLS

### 19.1. Kiểm thử DPoP proof cơ bản

~~~text
Access token cnf.jkt khớp proof public JWK
    -> tiếp tục kiểm tra proof

Proof ký bằng key khác
    -> từ chối

typ không phải dpop+jwt
    -> từ chối

alg không nằm trong allowlist
    -> từ chối

Proof có private key material trong jwk
    -> từ chối

Proof htm hoặc htu không khớp request
    -> từ chối

ath không khớp access token
    -> từ chối
~~~

### 19.2. Kiểm thử replay và nonce

- Cùng jti và cùng key được gửi hai lần.
- Hai request đồng thời dùng cùng proof.
- Proof cũ ngoài cửa sổ iat.
- Nonce thiếu khi server yêu cầu.
- Nonce sai hoặc đã hết hạn.
- Client nhận DPoP-Nonce rồi tạo proof mới.
- Replay cache mất kết nối hoặc hai region chưa đồng bộ.

Xác minh proof không được chấp nhận lần thứ hai và lỗi replay store không biến thành ALLOW.

### 19.3. Kiểm thử token endpoint và refresh

- Token request có DPoP proof hợp lệ.
- Proof dùng sai method hoặc URI token endpoint.
- Refresh token bound với key A nhưng request ký bằng key B.
- Access token mới có cnf.jkt đúng key đã dùng.
- Rotation refresh token vẫn giữ binding theo policy.
- Key bị revoke hoặc client mất key phải đi qua quy trình cấp token mới.

### 19.4. Kiểm thử mTLS

- Client dùng đúng certificate bound với token.
- Client dùng certificate khác nhưng cùng subject DN.
- Certificate hết hạn hoặc chain không tin cậy.
- Token thiếu cnf.x5t#S256 trong endpoint bắt buộc certificate-bound.
- Certificate được cấp lại với DER khác.
- Proxy kết thúc TLS nhưng forwarded certificate header bị client giả mạo.
- Backend bị gọi trực tiếp mà không qua trusted proxy.
- Certificate rotation trong giai đoạn overlap.

### 19.5. Kiểm thử authorization sau binding

- Token và key/certificate đều hợp lệ nhưng thiếu scope.
- Token/key hợp lệ nhưng tenant không đúng.
- User có quyền đọc nhưng gọi action delete.
- Resource thuộc owner khác.
- Token hết hạn hoặc audience không phù hợp.

Sender proof hợp lệ không được làm các request trên tự động được phép.

## 20. Checklist lựa chọn và vận hành

Trước khi áp dụng DPoP hoặc mTLS, hãy trả lời:

1. **Threat model:** cần ngăn token bị đánh cắp riêng lẻ, replay request hay cả compromise client?
2. **Client type:** client là public hay confidential; có quản lý được private key/certificate không?
3. **Token binding:** dùng cnf.jkt hay cnf.x5t#S256; issuer và resource server đã hỗ trợ profile tương ứng chưa?
4. **Key lifecycle:** key được sinh, lưu, rotate, revoke và khôi phục như thế nào?
5. **Proof validation:** DPoP có kiểm tra typ, alg, jwk, jti, htm, htu, iat, ath và nonce không?
6. **Replay state:** replay cache có atomic và dùng chung giữa các instance/region không?
7. **Nonce:** server có cần nonce; nonce có thời hạn và scope rõ không?
8. **TLS:** mọi token và proof có được truyền qua TLS không?
9. **Proxy:** URI bên ngoài và certificate identity có được chuyển tiếp qua trust boundary an toàn không?
10. **Refresh token:** refresh token có được sender-constrain hoặc rotation/reuse detection theo policy không?
11. **Rotation:** key/certificate mới có quy trình chuyển đổi mà không tạo cửa sổ không bảo vệ không?
12. **Authorization:** sau khi binding thành công, API có tiếp tục kiểm tra scope, tenant và object policy không?
13. **Failure handling:** proof sai, nonce thiếu, replay cache lỗi hoặc certificate không khớp được xử lý thế nào?
14. **Observability:** có metric/audit cho proof failure, replay, thumbprint mismatch và key/cert rotation không?
15. **Testing:** có kiểm thử attacker chỉ có token, attacker có token và key, proxy spoofing, race và multi-region replay không?

## 21. Ghi nhớ trọng tâm

- Bearer token có thể được sử dụng bởi bên nào sở hữu token; sender constraint yêu cầu thêm bằng chứng sở hữu khóa hoặc chứng thư.
- DPoP dùng proof JWT ký bằng private key cho từng request và ràng buộc access token với cnf.jkt.
- DPoP proof cần được kiểm tra typ, alg, public jwk, jti, htm, htu, iat, ath và nonce khi được yêu cầu.
- Resource server phải so JWK thumbprint với cnf.jkt; chữ ký proof hợp lệ bằng một key bất kỳ là chưa đủ.
- Replay cache và nonce bổ sung cho nhau; cache cần atomic và hoạt động nhất quán trên các instance.
- mTLS certificate-bound token dùng cnf.x5t#S256 để ràng buộc token với client certificate đã xác minh trong TLS.
- mTLS client authentication tại token endpoint không tự động có nghĩa access token đã được certificate-bound.
- TLS termination và forwarded certificate headers cần một trust boundary được bảo vệ.
- DPoP và mTLS giảm nguy cơ token bị đánh cắp riêng lẻ, nhưng không thay thế bảo vệ endpoint, private key, Authorization Server và authorization policy.
- Public client cần cơ chế phát hiện replay refresh token theo OAuth Security BCP; rotation và sender constraint là các lựa chọn được RFC 9700 nêu.

**Tài liệu tham khảo kỹ thuật:** RFC 9449 (OAuth 2.0 Demonstrating Proof of Possession, DPoP); RFC 8705 (OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens); RFC 7638 (JSON Web Key Thumbprint); RFC 7517 (JSON Web Key); RFC 7519 (JSON Web Token); RFC 9700 (Best Current Practice for OAuth 2.0 Security); RFC 6750 (The OAuth 2.0 Authorization Framework: Bearer Token Usage). Các chuẩn này định nghĩa cơ chế binding và cách trình bày token; quản lý key/certificate, replay store, proxy trust và quy trình incident response cần được triển khai theo threat model cụ thể.
