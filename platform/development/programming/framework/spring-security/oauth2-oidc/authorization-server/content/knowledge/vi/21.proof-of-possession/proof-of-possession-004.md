# Ràng buộc access token với khóa bằng cnf.jkt

## 1. Mục tiêu và tình huống thực tế

Trong chương **DPoP** của module **SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER**, bài học này giải thích cách Authorization Server ràng buộc Access Token với một public key do client chứng minh quyền sở hữu, thông qua claim **cnf.jkt**. Đây là nội dung phục vụ mục tiêu **thiết kế, cấu hình, bảo mật, kiểm thử và vận hành OAuth 2.0/OpenID Connect Authorization Server bằng Spring Security và Spring Authorization Server trong ứng dụng Spring Boot**.

Với Bearer Access Token thông thường, bất kỳ bên nào lấy được token đều có thể thử dùng nó cho đến khi token hết hạn hoặc bị thu hồi. Nếu token bị lộ qua log, browser storage, thiết bị bị mất hoặc một proxy trung gian, kẻ tấn công có thể gửi lại token mà không cần chứng minh mình là client ban đầu.

**DPoP (Demonstrating Proof of Possession)** bổ sung một bằng chứng ở tầng HTTP. Client tạo một cặp khóa, giữ private key và gửi một DPoP Proof JWT được ký bằng khóa đó. Khi cấp Access Token, Authorization Server lấy public key từ proof, tính JWK SHA-256 Thumbprint rồi gắn kết quả vào token:

~~~json
{
  "iss": "https://auth.example.com",
  "sub": "user-8f2a91",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "cnf": {
    "jkt": "CQMknzRoZ5YUi7vS58jck1q8TmZT8wiIiXrCN1Ny4VU"
  }
}
~~~

Khi client gọi Orders API, nó phải gửi cả Access Token và một DPoP Proof mới. Resource Server xác minh proof, tính thumbprint của public key trong proof và so sánh với **cnf.jkt** trong Access Token. Nó cũng kiểm tra proof có gắn với chính Access Token đang được gửi hay không.

Sau bài học, bạn có thể:

1. Giải thích vai trò của claim **cnf.jkt** và cấu trúc **cnf** trong Access Token.
2. Tính JWK thumbprint theo RFC 7638 và hiểu vì sao thumbprint không phải hash của toàn bộ JWT proof.
3. Phân biệt DPoP Proof gửi tới Token Endpoint với proof gửi tới Resource Server.
4. Mô tả cách Spring Authorization Server gắn public key vào Access Token.
5. Cấu hình Resource Server xác minh DPoP-bound Access Token và kiểm thử các trường hợp sai khóa, sai ath, replay, nonce.
6. Hiểu giới hạn của DPoP, vòng đời private key, replay cache và vận hành nhiều instance.

## 2. DPoP giải quyết vấn đề gì?

### 2.1. Bearer Token và sender-constrained token

Bearer Token có đặc tính: **ai sở hữu token đều có thể trình token**. Resource Server không thể chỉ dựa vào chuỗi Bearer Token để biết bên gửi có phải client ban đầu hay không.

DPoP tạo ra một **sender-constrained Access Token**. Khi phát hành, Authorization Server ràng buộc token với public key của client. Khi sử dụng, client phải ký proof mới bằng private key tương ứng.

| Đặc điểm | Bearer Access Token | DPoP-bound Access Token |
| --- | --- | --- |
| Cách trình token | Authorization: Bearer | Authorization: DPoP |
| Bằng chứng bổ sung | Không bắt buộc | DPoP Proof JWT trong header DPoP |
| Ràng buộc với client | Người giữ token có thể sử dụng | Cần token và private key tương ứng |
| Claim xác nhận trong JWT | Không bắt buộc có cnf.jkt | cnf.jkt chứa thumbprint của public key |
| Chống token bị đánh cắp đơn lẻ | Hạn chế | Giảm khả năng sử dụng token nếu private key vẫn an toàn |
| Yêu cầu với Resource Server | Xác minh token theo profile | Xác minh token, proof, ath và key binding |

DPoP là cơ chế sender-constraining ở **tầng ứng dụng**. Nó không thay thế HTTPS, không mã hóa payload JWT và không tự bảo vệ private key khỏi mã độc đang chạy trong cùng môi trường client.

### 2.2. Các thành phần trong một giao dịch

- **Client:** tạo hoặc quản lý cặp khóa; giữ private key và không gửi khóa này lên server.
- **DPoP Proof:** JWT ngắn hạn được ký bằng private key; chứa public JWK trong JOSE header.
- **Authorization Server:** xác minh proof tại Token Endpoint, lấy public key và ràng buộc Access Token với key đó.
- **Access Token:** token được phát hành; nếu là JWT thì chứa cnf.jkt.
- **Resource Server:** xác minh Access Token và proof ở mỗi request được bảo vệ bằng DPoP.

~~~mermaid
sequenceDiagram
    autonumber
    participant C as OAuth2 Client
    participant AS as Authorization Server
    participant RS as Resource Server
    Note over C: Tạo key pair, giữ private key
    C->>AS: POST /oauth2/token + DPoP Proof
    AS->>AS: Verify proof signature, htm, htu, iat, jti
    AS->>AS: Tính JWK thumbprint (SHA-256)
    AS->>AS: Gắn cnf.jkt vào Access Token
    AS-->>C: Access Token, token_type=DPoP
    Note over C: Tạo proof mới cho request API
    C->>RS: Authorization: DPoP token + DPoP proof (ath)
    RS->>RS: Validate Access Token
    RS->>RS: Verify proof, ath và cnf.jkt
    RS-->>C: Trả tài nguyên nếu mọi điều kiện hợp lệ
~~~

**Điểm cốt lõi:** DPoP Proof ở lần xin token chứng minh client đang giữ private key tại thời điểm xin token. Claim cnf.jkt lưu liên kết tới public key đó để Resource Server kiểm tra ở các request sau.

## 3. Claim cnf.jkt có ý nghĩa gì?

RFC 9449 định nghĩa phương thức xác nhận public key tên **jkt** (*JWK SHA-256 Thumbprint confirmation method*) dùng bên trong claim **cnf** (*confirmation*). Với JWT Access Token:

~~~json
{
  "cnf": {
    "jkt": "CQMknzRoZ5YUi7vS58jck1q8TmZT8wiIiXrCN1Ny4VU"
  }
}
~~~

- **cnf** là object chứa thông tin xác nhận về key hoặc cơ chế ràng buộc token.
- **jkt** là giá trị base64url của SHA-256 JWK Thumbprint theo RFC 7638.
- Public key được tham chiếu là public key nằm trong JWK của DPoP Proof đã được xác minh.
- **cnf.jkt không chứa private key, không phải toàn bộ JWK và không phải hash của DPoP Proof JWT.**

### 3.1. Vì sao chỉ lưu thumbprint?

Access Token không cần chứa toàn bộ public JWK để Resource Server có thể xác minh ràng buộc. Client sẽ gửi public JWK trong proof mỗi lần gọi API. Resource Server tính thumbprint của JWK đó và so sánh với giá trị đã được Authorization Server ký trong Access Token.

Điều này cho phép:

1. Token mang một định danh ngắn, ổn định cho public key.
2. Resource Server không cần lấy public key từ một URL do client chỉ định.
3. Việc so sánh key có quy tắc chuẩn hóa thống nhất theo RFC 7638.
4. Token bị đánh cắp riêng lẻ không đủ để tạo proof hợp lệ nếu attacker không có private key.

### 3.2. cnf.jkt không phải các giá trị sau

| Giá trị dễ nhầm | Vì sao không đúng |
| --- | --- |
| Hash của toàn bộ DPoP JWT | Proof thay đổi theo từng request; token cần ràng buộc với key ổn định |
| Hash của private key | Private key không được gửi lên server; thumbprint tính từ public JWK |
| JWK kid | kid là key identifier do bên phát hành đặt, không phải JWK Thumbprint chuẩn RFC 7638 |
| Hash của Access Token | Hash Access Token trong DPoP Proof resource request là claim ath, có mục đích khác |
| Client ID | Client ID nhận diện ứng dụng, không chứng minh possession của private key |
| TLS certificate thumbprint | Đó là cơ chế certificate-bound token khác, thường liên quan RFC 8705 |

## 4. Tính JWK SHA-256 Thumbprint theo RFC 7638

DPoP sử dụng **JWK Thumbprint** để xác định public key. RFC 7638 quy định cách tạo một biểu diễn JSON chuẩn hóa từ các thành phần bắt buộc của JWK, sau đó băm bằng SHA-256.

Quy trình khái quát:

1. Lấy public JWK từ JOSE header của DPoP Proof.
2. Xác định loại khóa và tập thành phần bắt buộc cho loại khóa đó.
3. Tạo JSON canonical chỉ gồm các thành phần bắt buộc, tên thành phần được sắp xếp theo thứ tự từ điển.
4. Encode JSON thành UTF-8.
5. Tính SHA-256 trên byte UTF-8.
6. Base64url-encode kết quả, bỏ padding.

~~~mermaid
flowchart TD
    A["Public JWK trong DPoP Proof"] --> B["Chọn thành phần bắt buộc theo kty"]
    B --> C["Sắp xếp tên member theo thứ tự từ điển"]
    C --> D["Serialize JSON canonical, UTF-8"]
    D --> E["SHA-256"]
    E --> F["Base64url, bỏ dấu = padding"]
    F --> G["cnf.jkt"]
~~~

### 4.1. Ví dụ với RSA public JWK

Một RSA public JWK có thể có nhiều thuộc tính như:

~~~json
{
  "kty": "RSA",
  "n": "0vx7agoebGcQSuuPiLJXZptN9nndrQmb...",
  "e": "AQAB",
  "kid": "client-key-2026",
  "alg": "RS256",
  "use": "sig"
}
~~~

Đối với RSA, các thành phần bắt buộc để tính thumbprint là **e**, **kty** và **n**. JSON canonical có dạng minh họa:

~~~json
{"e":"AQAB","kty":"RSA","n":"0vx7agoebGcQSuuPiLJXZptN9nndrQmb..."}
~~~

Các trường **kid**, **alg** và **use** không tham gia phép tính thumbprint RSA theo RFC 7638. Giá trị n trong ví dụ đã rút gọn để minh họa, không thể dùng để tính thumbprint thực tế.

### 4.2. Các loại JWK khác

| Loại khóa | Thành phần bắt buộc để tính thumbprint |
| --- | --- |
| RSA | e, kty, n |
| EC | crv, kty, x, y |
| OKP | crv, kty, x |

Không được tự chọn thêm member tùy ý vào JSON canonical. Nếu hai bên đưa thêm **kid** hoặc **alg** vào phép băm, kết quả sẽ khác RFC 7638 và key binding không còn interoperable.

### 4.3. Phân biệt thumbprint với chữ ký proof

DPoP Proof JWT được ký bằng private key. Chữ ký chứng minh người tạo proof nắm private key. Thumbprint được tính từ public JWK và được gắn vào Access Token. Hai phép toán có vai trò khác nhau:

- **JWS signature:** xác minh proof được ký bởi private key tương ứng với public JWK.
- **JWK thumbprint:** tạo định danh ổn định cho public JWK để ràng buộc token.

Không thể thay chữ ký bằng thumbprint. Một attacker có thể tự tính thumbprint cho public key của mình, nhưng nếu không có Access Token được ràng buộc với thumbprint đó thì Resource Server sẽ từ chối.

## 5. DPoP Proof JWT: header và claims

DPoP Proof là JWT được gửi trong HTTP header **DPoP**. Theo RFC 9449, JOSE header phải có các thông tin chính:

| Header | Yêu cầu | Ý nghĩa |
| --- | --- | --- |
| typ | Phải là dpop+jwt | Nhận diện loại JWT DPoP Proof |
| alg | Thuật toán chữ ký bất đối xứng được hỗ trợ; không dùng none hoặc MAC | Chứng minh possession của private key |
| jwk | Public JWK | Key để xác minh chữ ký; không được chứa private key |

Các claim cơ bản trong proof:

| Claim | Ý nghĩa |
| --- | --- |
| htm | HTTP method của request |
| htu | HTTP URI đích; bỏ qua query và fragment khi so sánh theo RFC |
| iat | Thời điểm tạo proof |
| jti | ID duy nhất của proof |
| ath | Hash của Access Token, bắt buộc khi proof đi kèm Access Token tới Resource Server |
| nonce | Nonce do Authorization Server hoặc Resource Server cung cấp, nếu server yêu cầu |

Ví dụ header và payload của proof tại Token Endpoint:

~~~json
{
  "header": {
    "typ": "dpop+jwt",
    "alg": "ES256",
    "jwk": {
      "kty": "EC",
      "crv": "P-256",
      "x": "public-x-coordinate",
      "y": "public-y-coordinate"
    }
  },
  "payload": {
    "htm": "POST",
    "htu": "https://auth.example.com/oauth2/token",
    "iat": 1794823200,
    "jti": "proof-id-unique-001"
  }
}
~~~

Đây là cấu trúc minh họa; các tọa độ JWK không phải public key thật. Proof ở Token Endpoint thường không cần claim **ath** vì chưa trình một Access Token tới Resource Server. Nếu server cung cấp nonce, proof phải chứa nonce tương ứng.

### 5.1. Không đưa private key vào JWK header

JWK trong proof chỉ chứa thành phần public. Với RSA, không được gửi các trường private như **d**, **p**, **q**, **dp**, **dq**, **qi** hoặc **oth**. Với EC, không được gửi private scalar **d**. Nếu private key bị đưa vào request, client đã làm lộ credential quan trọng nhất của DPoP.

### 5.2. Mỗi request cần một proof mới

Proof cần có jti mới và iat phù hợp cho từng request. Không tái sử dụng một proof JWT cho nhiều HTTP request. Nếu client retry, nó cần tạo proof mới với method/URI/iat/jti phù hợp; không chỉ gửi lại nguyên JWT cũ.

## 6. Ràng buộc Access Token tại Token Endpoint

Để nhận Access Token DPoP-bound, client gửi DPoP Proof trong header **DPoP** cùng request xin token:

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.com
Content-Type: application/x-www-form-urlencoded
DPoP: <signed-dpop-proof-jwt>

grant_type=authorization_code&
client_id=orders-bff&
code=<authorization-code>&
redirect_uri=https%3A%2F%2Fportal.example.com%2Fcallback&
code_verifier=<pkce-verifier>
~~~

Ví dụ dùng Authorization Code; RFC 9449 cho phép DPoP áp dụng với các yêu cầu cấp Access Token khác như Refresh Token hoặc Client Credentials nếu server hỗ trợ flow tương ứng.

Authorization Server cần:

1. Đọc đúng một DPoP header và parse proof JWT.
2. Kiểm tra typ là dpop+jwt.
3. Kiểm tra alg là thuật toán bất đối xứng được phép.
4. Kiểm tra JWK chỉ có public key.
5. Xác minh chữ ký bằng public JWK trong proof.
6. So sánh htm với HTTP method và htu với URI Token Endpoint.
7. Kiểm tra iat nằm trong khoảng thời gian chấp nhận; kiểm soát jti để phát hiện replay.
8. Kiểm tra nonce nếu server đã yêu cầu.
9. Chỉ sau khi proof hợp lệ mới gắn public key đã xác minh với token được phát hành.

Khi phát hành JWT Access Token, Authorization Server đưa thumbprint của public JWK vào claim:

~~~json
{
  "iss": "https://auth.example.com",
  "sub": "user-8f2a91",
  "aud": ["orders-api"],
  "iat": 1794823200,
  "exp": 1794823800,
  "scope": "orders.read",
  "cnf": {
    "jkt": "CQMknzRoZ5YUi7vS58jck1q8TmZT8wiIiXrCN1Ny4VU"
  }
}
~~~

Response token thường báo loại token:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store

{
  "access_token": "<dpop-bound-access-token>",
  "token_type": "DPoP",
  "expires_in": 600,
  "scope": "orders.read"
}
~~~

**token_type=DPoP** báo cho client biết Access Token đã được ràng buộc với DPoP key. Client cần lưu Access Token cùng tham chiếu tới private key đã dùng để tạo proof. Không gửi token này theo scheme Bearer rồi kỳ vọng Resource Server tự suy ra key.

## 7. Spring Authorization Server và cnf.jkt

Spring Authorization Server dòng **1.5.x** có tài liệu về DPoP-bound Access Tokens. Khi DPoP Proof hợp lệ được xử lý tại Token Endpoint, public key của proof được ràng buộc với Access Token. API **OAuth2TokenContext.DPOP_PROOF_KEY** có từ phiên bản 1.5 để cung cấp key dùng cho DPoP Proof JWT nếu có.

Điều này có hai hệ quả:

- Với luồng DPoP được framework hỗ trợ, **không cần tự bịa một cnf.jkt** bằng cách đọc public key từ request thô rồi thêm vào JWT.
- Khi viết custom token generator hoặc customizer, phải giữ nguyên thông tin binding mà framework đưa vào context; không ghi đè hoặc xóa object cnf đã được tạo.

### 7.1. Vì sao không nên tự thêm cnf.jkt theo client_id?

Đoạn mã như sau là sai về mặt bảo mật:

~~~java
claims.put("cnf", Map.of("jkt", request.getParameter("jkt")));
~~~

Client có thể gửi một chuỗi bất kỳ làm jkt. Nếu Authorization Server ký chuỗi đó mà chưa xác minh proof và chưa tính thumbprint từ public JWK đã xác thực, token sẽ bị ràng buộc vào một giá trị không có bằng chứng possession.

Tương tự, không dùng:

- client_id làm jkt.
- kid của JWK làm jkt.
- hash của DPoP Proof JWT làm jkt.
- thumbprint của một key do client gửi ở form parameter nhưng không nằm trong proof đã xác minh.

### 7.2. Kiểm tra token context khi tùy chỉnh

OAuth2TokenContext có thuộc tính **DPOP_PROOF_KEY**, mô tả key dùng cho DPoP Proof JWT nếu có. Đây là điểm mở rộng hữu ích khi xây custom integration theo API của phiên bản. Tuy nhiên, ứng dụng nên ưu tiên cơ chế DPoP được framework hỗ trợ và chỉ đọc context attribute khi thực sự cần.

Không thêm một customizer chung để tự ghi đè claim cnf cho mọi loại token. Nếu cần bổ sung claims khác, chỉ thay đổi claim riêng của ứng dụng và giữ nguyên cnf.jkt do cơ chế DPoP đã xác minh tạo ra.

### 7.3. Kiểm tra phiên bản

Tài liệu Spring Authorization Server hiện hành có mục DPoP-bound Access Tokens; API OAuth2TokenContext.DPOP_PROOF_KEY được đánh dấu từ 1.5. Với dự án dùng phiên bản cũ hơn, không giả định API hoặc hành vi này tồn tại. Cần kiểm tra dependency thực tế, tài liệu cùng phiên bản và integration test Token Endpoint trước khi bật DPoP trong production.

## 8. Resource Server xác minh cnf.jkt như thế nào?

Khi client gọi API, request phải có:

~~~http
GET /api/orders HTTP/1.1
Host: api.example.com
Authorization: DPoP <dpop-bound-access-token>
DPoP: <fresh-signed-dpop-proof-jwt>
~~~

Proof gửi tới Resource Server phải có claim **ath**:

~~~json
{
  "htm": "GET",
  "htu": "https://api.example.com/api/orders",
  "ath": "fUHyO2r2Z3DZ53EsNrWBb0xWXoaNy59IiKCAqksmQEo",
  "iat": 1794823260,
  "jti": "proof-id-for-this-resource-request"
}
~~~

ath được tính như sau:

~~~text
ath = BASE64URL-NOPAD(SHA-256(ASCII(access_token_value)))
~~~

Resource Server cần thực hiện các kiểm tra:

1. Xác minh Access Token theo cơ chế JWT hoặc introspection: issuer, chữ ký, expiry, audience, scope và trạng thái.
2. Xác minh DPoP Proof JWT: typ, alg, public JWK, chữ ký, htm, htu, iat và jti.
3. Tính SHA-256 thumbprint của public JWK trong proof theo RFC 7638.
4. So sánh thumbprint vừa tính với **cnf.jkt** trong Access Token hoặc kết quả introspection.
5. Tính hash của Access Token và so sánh với claim **ath** trong proof.
6. Kiểm tra nonce nếu Resource Server đã phát nonce.
7. Kiểm tra proof jti chưa được sử dụng trong cửa sổ replay protection.

Chỉ khi tất cả kiểm tra cần thiết đều thành công, Resource Server mới chấp nhận token cho request.

### 8.1. Vì sao cần cả cnf.jkt và ath?

Hai giá trị bảo vệ hai mối liên kết khác nhau:

| Giá trị | Chứng minh điều gì? |
| --- | --- |
| cnf.jkt | Public key của proof chính là key đã được gắn với Access Token khi phát hành |
| ath | Proof hiện tại được tạo cho đúng Access Token đang nằm trong Authorization header |

Nếu chỉ kiểm tra cnf.jkt, một proof hợp lệ từ cùng key có thể bị ghép nhầm với token khác cùng key. Claim ath ràng buộc proof với giá trị Access Token cụ thể.

### 8.2. DPoP scheme thay cho Bearer scheme

Với DPoP-bound Access Token, client gửi:

~~~http
Authorization: DPoP <access-token>
DPoP: <proof-jwt>
~~~

Không gửi:

~~~http
Authorization: Bearer <dpop-bound-access-token>
~~~

Resource Server phải phân biệt DPoP-bound token với Bearer token. Nếu một token có cnf.jkt bị trình bằng Bearer scheme, không được bỏ qua confirmation claim rồi chấp nhận như một Bearer Token thông thường.

## 9. Opaque Access Token và introspection

Không phải Access Token nào cũng là JWT. Nếu Access Token là opaque, Resource Server không thể đọc claim cnf.jkt bằng cách decode token. RFC 9449 cho phép Authorization Server trả thông tin key binding trong **Token Introspection Response**.

Ví dụ response:

~~~json
{
  "active": true,
  "sub": "user-8f2a91",
  "iss": "https://auth.example.com",
  "scope": "orders.read",
  "token_type": "DPoP",
  "cnf": {
    "jkt": "CQMknzRoZ5YUi7vS58jck1q8TmZT8wiIiXrCN1Ny4VU"
  }
}
~~~

Resource Server lấy cnf.jkt từ introspection, sau đó tự so sánh với thumbprint của proof public key. Resource Server **không gửi DPoP proof trong introspection request**; Authorization Server trả metadata binding để Resource Server kiểm tra cục bộ.

Nếu trường token_type có trong introspection response của DPoP-bound token, RFC 9449 yêu cầu giá trị là **DPoP**. Cache introspection cần được thiết kế cẩn thận để không giữ trạng thái active/binding lâu hơn policy thu hồi.

## 10. Cấu hình Resource Server với Spring Security

Spring Security có tài liệu hỗ trợ DPoP-bound Access Token. Với dòng **Spring Security 7.1.x**, Resource Server có thể bật DPoP qua cấu hình **dPoP(...)** trên OAuth2 Resource Server configurer.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration(proxyBeanMethods = false)
class OrdersResourceServerConfiguration {

    @Bean
    SecurityFilterChain ordersApiSecurity(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/api/orders/**").hasAuthority("SCOPE_orders.read")
                .anyRequest().authenticated()
            )
            .oauth2ResourceServer(resourceServer -> resourceServer
                .jwt(Customizer.withDefaults())
                .dPoP(Customizer.withDefaults())
            );

        return http.build();
    }
}
~~~

Đây là cấu hình khung cho Spring Security 7.1.x; ứng dụng vẫn phải cấu hình issuer/JWK hoặc JwtDecoder, audience validator, scope mapping và các quy tắc authorization khác. Phương thức **dPoP** được bổ sung theo API của phiên bản; khi dùng 6.x hoặc phiên bản khác, cần đối chiếu tài liệu đúng version và xác minh DPoP có thực sự được enforce. Không chỉ dựa vào việc ứng dụng khởi động thành công.

### 10.1. JWT decoder vẫn cần xác minh issuer và audience

Bật DPoP không thay thế các kiểm tra JWT thông thường. Resource Server vẫn phải kiểm tra:

- Chữ ký bằng JWK đáng tin.
- Issuer chính xác.
- Audience có chứa API hiện tại.
- exp và nbf theo clock policy.
- Scope/authority phù hợp endpoint.
- cnf.jkt và DPoP Proof binding.

DPoP chứng minh possession của key đã được gắn với token; nó **không** chứng minh token có quyền gọi mọi API.

### 10.2. Không tự viết một filter chỉ so chuỗi jkt

Một filter tự viết chỉ so sánh giá trị jkt mà không xác minh DPoP Proof signature, htm, htu, iat, jti, ath và nonce là chưa đủ. Hãy dùng cơ chế DPoP tích hợp của phiên bản Spring Security đang chạy hoặc xây một implementation đầy đủ theo RFC 9449 và có test độc lập.

## 11. Nonce và replay protection

### 11.1. jti không tự chống replay

Mỗi proof có jti riêng. Tuy nhiên, việc claim jti tồn tại không tự động ngăn proof được gửi lại. Server cần lưu hoặc kiểm tra các jti đã nhận trong một cửa sổ thời gian phù hợp để phát hiện proof lặp.

~~~mermaid
flowchart TD
    A["Nhận DPoP Proof"] --> B["Xác minh chữ ký và claims"]
    B --> C["Đọc jti + proof iat"]
    C --> D{"jti đã xuất hiện trong replay window?"}
    D -->|Có| E["Từ chối proof replay"]
    D -->|Không| F["Ghi jti vào replay cache"]
    F --> G["Tiếp tục kiểm tra ath, cnf.jkt, nonce"]
    G --> H["Cho phép request nếu mọi điều kiện hợp lệ"]
~~~

Trong hệ thống nhiều instance, replay cache cần được chia sẻ hoặc có cơ chế bảo đảm request không thể được xác minh độc lập trên nhiều node. Một cache in-memory riêng ở mỗi JVM có thể để cùng một proof được chấp nhận tại hai node khác nhau.

### 11.2. Nonce challenge

Authorization Server hoặc Resource Server có thể trả header **DPoP-Nonce** để yêu cầu client đưa nonce mới vào proof kế tiếp. Nonce giúp server kiểm soát độ mới của proof và giảm nguy cơ proof được tạo trước rồi phát lại.

Ví dụ phản hồi yêu cầu nonce:

~~~http
HTTP/1.1 401 Unauthorized
DPoP-Nonce: server-nonce-value
WWW-Authenticate: DPoP error="use_dpop_nonce"
Cache-Control: no-store
~~~

Client tạo proof mới và thêm claim:

~~~json
{
  "htm": "GET",
  "htu": "https://api.example.com/api/orders",
  "ath": "fUHyO2r2Z3DZ53EsNrWBb0xWXoaNy59IiKCAqksmQEo",
  "iat": 1794823265,
  "jti": "new-proof-id",
  "nonce": "server-nonce-value"
}
~~~

Nếu server đã cung cấp nonce, proof phải chứa nonce phù hợp. Client không nên tái sử dụng nonce vô thời hạn; phải theo dõi nonce mới theo từng server và xử lý challenge/retry đúng cách.

### 11.3. Cửa sổ iat và độ lệch đồng hồ

Server cần giới hạn tuổi proof dựa trên iat hoặc cơ chế nonce. Cửa sổ quá rộng làm tăng thời gian proof có thể bị phát lại; cửa sổ quá hẹp gây lỗi do clock skew và độ trễ mạng. Đồng bộ thời gian, đo latency và cấu hình cửa sổ hợp lý cho cả client, Authorization Server và Resource Server.

## 12. Liên kết Authorization Code với DPoP key

RFC 9449 còn định nghĩa tham số **dpop_jkt** trong Authorization Request để ràng buộc Authorization Code với DPoP public key ngay từ bước xin code.

Trong Authorization Code Flow:

1. Client tạo key pair và tính JWK thumbprint.
2. Client gửi dpop_jkt trong Authorization Request.
3. Authorization Server liên kết code được phát hành với thumbprint đó.
4. Khi đổi code tại Token Endpoint, client gửi DPoP Proof được ký bởi cùng private key.
5. Authorization Server xác minh thumbprint của proof khớp dpop_jkt đã lưu; nếu khác, từ chối.
6. Access Token được phát hành và tiếp tục mang cnf.jkt.

Liên kết này giúp giảm nguy cơ code bị đánh cắp rồi được đổi bằng một key khác. Nó bổ sung cho PKCE; **dpop_jkt không thay code_challenge/code_verifier**.

~~~text
Authorization Request:
    code_challenge=...
    code_challenge_method=S256
    dpop_jkt=<JWK thumbprint>

Token Request:
    code=...
    code_verifier=...
    DPoP: <proof signed by the same key>
~~~

Đây là khả năng bổ sung của RFC 9449. Chỉ sử dụng nếu Authorization Server và client library hỗ trợ đúng profile; không tự thêm tham số dpop_jkt rồi giả định server đã ràng buộc code.

## 13. Key lifecycle và lưu trữ private key

DPoP chỉ hữu ích nếu private key được bảo vệ. Cần thiết kế vòng đời khóa cho từng loại client:

| Client | Cách lưu khóa nên cân nhắc | Rủi ro chính |
| --- | --- | --- |
| Native/mobile app | Keystore/Keychain hoặc hardware-backed key khi có thể | Thiết bị root/jailbreak, backup không an toàn, malware |
| SPA | Web Crypto và chính sách bảo vệ runtime phù hợp | XSS hoặc mã độc trong origin có thể yêu cầu ký proof |
| Backend/BFF | Secret manager, HSM hoặc keystore với quyền truy cập tối thiểu | Lộ máy chủ, log, memory dump hoặc quyền service quá rộng |
| CLI/desktop | OS credential store hoặc hardware key | File cấu hình, backup, tiến trình khác đọc được private key |

### 13.1. Không chia sẻ một private key cho nhiều client không liên quan

Mỗi client hoặc security principal nên có key riêng theo trust boundary. Nếu nhiều ứng dụng dùng chung private key, việc mất khóa ở một ứng dụng có thể ảnh hưởng tất cả ứng dụng còn lại và làm giảm khả năng quy trách nhiệm.

### 13.2. Xoay khóa

Access Token đã phát hành vẫn gắn với thumbprint cũ. Khi client xoay private key:

- Token đang còn hạn không tự động chuyển sang key mới.
- Client không thể sửa cnf.jkt trong token.
- Cần xin token mới qua flow được phép và proof bằng key mới, hoặc dùng cơ chế re-binding được thiết kế rõ.
- Token/refresh token cũ cần được thu hồi hoặc hết hạn theo policy.

Không tự động chấp nhận bất kỳ key mới nào chỉ vì client vẫn gửi cùng client_id.

### 13.3. DPoP không bảo vệ nếu cả token và private key đều bị chiếm

Nếu attacker lấy được cả Access Token và private key, attacker có thể tạo proof hợp lệ. DPoP giảm giá trị của token bị lộ đơn lẻ; nó không thay thế bảo mật thiết bị, chống XSS, quản lý secret và giám sát hành vi bất thường.

## 14. Các giới hạn bảo mật cần hiểu

1. **Không thay thế TLS:** DPoP không mã hóa HTTP request/response. Luôn dùng HTTPS.
2. **Không ký toàn bộ request body:** proof ràng buộc method và URI, không phải cơ chế ký nội dung body tổng quát.
3. **Không ngăn mã độc trong client context:** code độc hại có thể yêu cầu môi trường client ký proof nếu nó kiểm soát được runtime.
4. **Không cứu được private key bị đánh cắp:** attacker có token và private key có thể tạo proof mới.
5. **Không tự thu hồi token:** cnf.jkt chỉ ràng buộc key; revocation/introspection vẫn là chính sách riêng.
6. **Không thay authorization:** Resource Server vẫn phải kiểm tra audience, scope, tenant và quyền trên tài nguyên.
7. **Không tự chống mọi replay:** cần kiểm tra jti, iat, nonce và replay cache.
8. **Không đồng nghĩa mTLS:** DPoP hoạt động ở tầng ứng dụng; certificate-bound token theo RFC 8705 là cơ chế khác.

## 15. Kiểm thử cnf.jkt và DPoP flow

Một bộ test cần kiểm tra **cả issuance lẫn protected resource access**. Chỉ thấy cnf.jkt trong payload chưa chứng minh Resource Server thực sự enforce key binding.

### 15.1. Ma trận kiểm thử

| # | Tình huống | Kết quả mong đợi |
| --- | --- | --- |
| 1 | Token request có DPoP proof hợp lệ | Cấp token_type DPoP và binding đúng key |
| 2 | JWT Access Token được phát hành | Có cnf.jkt đúng thumbprint của proof public JWK |
| 3 | Token request không có DPoP proof khi client/flow yêu cầu DPoP | Bị từ chối theo policy |
| 4 | Proof có typ khác dpop+jwt | Từ chối |
| 5 | Proof dùng alg none hoặc thuật toán đối xứng | Từ chối |
| 6 | JWK header chứa private key | Từ chối |
| 7 | Proof signature sai | Từ chối |
| 8 | htm hoặc htu không khớp request | Từ chối |
| 9 | Proof iat quá cũ hoặc ở tương lai vượt cửa sổ | Từ chối |
| 10 | jti proof bị phát lại | Từ chối trong replay window |
| 11 | Access Token được trình với proof từ key khác | Từ chối vì cnf.jkt không khớp |
| 12 | ath không hash đúng Access Token đang gửi | Từ chối |
| 13 | Token DPoP được gửi theo Bearer scheme | Không chấp nhận như Bearer token |
| 14 | Server yêu cầu nonce nhưng proof không có nonce đúng | Từ chối và yêu cầu proof mới |
| 15 | Opaque token introspection trả cnf.jkt | Resource Server xác minh binding từ metadata |
| 16 | JWT đúng key nhưng sai issuer/audience/scope | Từ chối theo validation OAuth2 thông thường |
| 17 | Hai node nhận cùng proof jti đồng thời | Replay protection dùng chung chỉ cho tối đa một request hợp lệ theo policy |
| 18 | Client xoay key nhưng tiếp tục dùng token gắn key cũ | Từ chối proof dùng key mới với token cũ |

### 15.2. Kiểm tra thumbprint của token được phát hành

Trong integration test:

1. Tạo cặp khóa test.
2. Sinh DPoP Proof JWT với public JWK.
3. Gửi Token Request có header DPoP.
4. Nhận Access Token.
5. Decode và **xác minh chữ ký** JWT Access Token bằng public key của Authorization Server.
6. Đọc cnf.jkt.
7. Tính JWK Thumbprint từ public JWK client theo RFC 7638.
8. Assert hai giá trị bằng nhau.

Không chỉ decode JWT rồi assert một chuỗi đã hard-code. Test cần chứng minh Authorization Server ràng buộc đúng key của proof thực tế.

### 15.3. Kiểm thử Resource Server

Gửi cùng một DPoP-bound Access Token theo các tình huống:

- Proof ký bởi đúng private key, htm/htu/ath đúng, jti mới → request được xác thực.
- Proof ký bởi key khác → từ chối.
- Proof đúng key nhưng ath thuộc token khác → từ chối.
- Proof đúng key nhưng htu/htm không khớp → từ chối.
- Gửi lại proof cũ → từ chối theo replay policy.
- Không có DPoP header → từ chối DPoP-bound token.
- Access Token hết hạn hoặc sai audience → từ chối dù proof đúng.

## 16. Chẩn đoán lỗi

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| Token response vẫn là Bearer | Request không gửi DPoP proof hợp lệ hoặc flow không bật/hỗ trợ DPoP | Kiểm tra header DPoP, server version và token_type |
| JWT không có cnf.jkt | Token không được phát hành theo DPoP hoặc customizer/generator làm mất claim | Kiểm tra proof validation và token customizer |
| cnf.jkt khác thumbprint client tính | JWK canonicalization sai, nhầm key hoặc customizer ghi đè | Kiểm tra RFC 7638, key và context |
| Resource Server báo invalid proof | typ/alg/signature/htm/htu/iat/jti/nonce không hợp lệ | Kiểm tra proof tạo cho đúng request |
| Resource Server báo key mismatch | Proof dùng key khác key đã ràng buộc | Kiểm tra key lifecycle và token cache |
| ath mismatch | Proof gắn với Access Token khác hoặc hash encoding sai | Tính SHA-256 trên ASCII token rồi base64url không padding |
| Request đầu thành công, retry bị từ chối | Proof jti đã được dùng | Tạo proof mới, không phát lại JWT cũ |
| Chỉ một số node chấp nhận proof | Replay cache hoặc nonce store không dùng chung | Kiểm tra distributed state và clock |
| Client không xử lý nonce | Client không lưu DPoP-Nonce hoặc không đưa vào proof mới | Kiểm tra challenge/retry logic |
| DPoP token bị API từ chối dù cnf đúng | Thiếu dPoP resource server support hoặc validator issuer/aud/scope sai | Kiểm tra Resource Server config và token validation |

## 17. Checklist triển khai production

1. **Key pair:** private key được lưu an toàn; public JWK chỉ chứa thành phần công khai.
2. **Proof header:** typ dpop+jwt, alg bất đối xứng được phép, không dùng none/MAC.
3. **Proof claims:** htm, htu, iat, jti được xác minh; ath có mặt ở resource request.
4. **Thumbprint:** cnf.jkt tính theo RFC 7638 từ public JWK đã xác minh.
5. **Token response:** token_type DPoP khi token đã được sender-constrain.
6. **Resource Server:** so sánh cnf.jkt với proof key và xác minh ath.
7. **Token validation:** vẫn kiểm tra iss, aud, exp, nbf, scope và trạng thái.
8. **Replay protection:** lưu jti trong cửa sổ phù hợp; triển khai state dùng chung khi nhiều node.
9. **Nonce:** có policy challenge rõ ràng, client xử lý DPoP-Nonce đúng.
10. **Key lifecycle:** có quy trình rotate, revoke và xử lý mất thiết bị.
11. **Customizers:** không xóa hoặc ghi đè cnf.jkt do framework tạo.
12. **Observability:** log kết quả validation, error category và correlation ID; không log token, proof JWT hoặc private key.
13. **Version compatibility:** xác minh DPoP support của đúng Spring Authorization Server/Spring Security version.
14. **Integration tests:** test token issuance, key mismatch, ath, replay, nonce và Resource Server thật.

## 18. Bài tập và câu hỏi tự đánh giá

**Bài tập A — Tính thumbprint.** Cho RSA public JWK có các member kty, n, e, kid và alg. Xác định member nào tham gia canonical JSON, sau đó mô tả các bước tạo SHA-256 thumbprint.

**Bài tập B — Binding sai key.** Client nhận token có cnf.jkt của key A nhưng gửi proof ký bằng key B. Giải thích chính xác Resource Server phải so sánh gì và vì sao token không được chấp nhận.

**Bài tập C — Phân biệt ath và jkt.** Một proof có jkt đúng nhưng ath sai. Vì sao Resource Server vẫn phải từ chối? Viết công thức tính ath.

**Bài tập D — Token Endpoint và Resource Server.** Liệt kê claims bắt buộc của proof ở Token Endpoint và các thành phần bổ sung khi proof đi cùng Access Token tới Resource Server.

**Bài tập E — Replay cache.** Hai node nhận cùng proof jti gần như đồng thời. Thiết kế replay cache để tránh cả hai node cùng chấp nhận proof.

**Bài tập F — Key rotation.** Client xoay từ key A sang key B nhưng vẫn dùng Access Token gắn với cnf.jkt của A. Hãy thiết kế quy trình chuyển đổi token/key an toàn.

**Câu hỏi ôn tập:**

1. cnf và jkt có vai trò gì trong JWT Access Token?
2. Vì sao jkt là thumbprint của public JWK thay vì hash của DPoP Proof JWT?
3. RFC 7638 quy định canonicalization và hash như thế nào?
4. Vì sao JWK trong DPoP Proof không được chứa private key?
5. Proof gửi tới Token Endpoint khác proof gửi tới Resource Server ở điểm nào?
6. Claim ath được tính từ dữ liệu nào và có bắt buộc ở mọi DPoP Proof không?
7. Vì sao token_type=DPoP quan trọng đối với client?
8. Resource Server cần kiểm tra những gì ngoài cnf.jkt?
9. Vì sao jti cần replay cache và không thể tự chống replay?
10. Nonce giúp gì cho DPoP Proof?
11. DPoP khác mTLS certificate-bound token như thế nào?
12. Nếu token và private key cùng bị đánh cắp, DPoP còn bảo vệ được gì?
13. Vì sao customizer không nên tự ghi đè claim cnf?
14. Khi nâng cấp Spring Security, cần kiểm tra lại điều gì về cấu hình dPoP?

## 19. Tài liệu tham khảo

- [RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449)
- [RFC 9449, Section 4 — DPoP Proof JWTs](https://www.rfc-editor.org/rfc/rfc9449#section-4)
- [RFC 9449, Section 6 — Public Key Confirmation](https://www.rfc-editor.org/rfc/rfc9449#section-6)
- [RFC 9449, Section 7 — Protected Resource Access](https://www.rfc-editor.org/rfc/rfc9449#section-7)
- [RFC 7638 — JSON Web Key (JWK) Thumbprint](https://www.rfc-editor.org/rfc/rfc7638)
- [RFC 7800 — Proof-of-Possession Key Semantics for JWTs](https://www.rfc-editor.org/rfc/rfc7800)
- [RFC 7515 — JSON Web Signature](https://www.rfc-editor.org/rfc/rfc7515)
- [Spring Authorization Server — Protocol Endpoints: DPoP-bound Access Tokens](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html)
- [Spring Authorization Server — OAuth2TokenContext API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/token/OAuth2TokenContext.html)
- [Spring Security 7.1 — DPoP-bound Access Tokens](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/dpop-tokens.html)
- [Spring Security — OAuth2ResourceServerConfigurer API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/annotation/web/configurers/oauth2/server/resource/OAuth2ResourceServerConfigurer.html)

**Ghi nhớ:** **cnf.jkt là SHA-256 JWK Thumbprint của public key đã được xác minh trong DPoP Proof**, không phải hash của token hay proof. Authorization Server gắn thumbprint đó vào Access Token khi phát hành; Resource Server tính lại thumbprint từ proof và so sánh, đồng thời xác minh ath, method, URI, thời gian, nonce và replay. Một token bị đánh cắp riêng lẻ sẽ khó sử dụng hơn khi private key vẫn được bảo vệ, nhưng DPoP không thay thế TLS, authorization, quản lý khóa và giám sát.
