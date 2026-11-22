# DPoP theo RFC 9449 và phạm vi hỗ trợ của từng phiên bản Spring Security

**DPoP (Demonstrating Proof of Possession)** là cơ chế OAuth 2.0 sender-constraining được chuẩn hóa trong **RFC 9449**. Thay vì cho phép bất kỳ ai sở hữu access token đều có thể dùng token đó như Bearer token thông thường, DPoP ràng buộc access token với một **khóa công khai**. Client phải chứng minh mình đang nắm **khóa riêng tương ứng** mỗi khi sử dụng access token.

Trong một request tới Resource Server, Client gửi đồng thời:

- Access token với authentication scheme **§DPoP§** trong header §Authorization§.
- Một **DPoP proof JWT** mới trong header §DPoP§.

Resource Server kiểm tra proof, đối chiếu khóa công khai trong proof với khóa đã ràng buộc trong access token, xác minh request method/URI và hash của chính access token. Nhờ đó, một access token bị đánh cắp riêng lẻ sẽ khó bị sử dụng từ Client không có khóa riêng.

**Phạm vi hỗ trợ theo phiên bản Spring Security cần được đọc chính xác.** API có lớp §DPoPAuthenticationProvider§ từ **6.5**; tài liệu DPoP Resource Server có trong các nhánh 6.5 và 7.0. Fluent configurer §OAuth2ResourceServerConfigurer.dPoP(...)§ được đánh dấu **§@since 7.1§**, dùng để cấu hình rõ request matcher, converter và handler. Trong tài liệu chính thức đã đối chiếu, DPoP Resource Server được mô tả ở **Servlet stack**; không nên suy ra §ServerHttpSecurity§/WebFlux có hỗ trợ tương đương chỉ vì Reactive Resource Server hỗ trợ JWT và opaque token.

> **Cần nhớ:** DPoP không phải một loại JWT access token mới, không thay thế việc kiểm tra chữ ký/issuer/audience/scope, và không làm access token tự hết giá trị khi bị lộ. Nó bổ sung **bằng chứng sở hữu khóa cho từng request**. Client, Authorization Server và Resource Server phải cùng hỗ trợ đúng RFC 9449 thì cơ chế mới hoạt động đầu-cuối.

## 1. Vấn đề DPoP giải quyết

Một Bearer access token thông thường có đặc tính:

~~~http
GET /api/orders/42 HTTP/1.1
Host: api.example.test
Authorization: Bearer <access-token>
~~~

Server chấp nhận token nếu token hợp lệ và có đủ quyền. Nhưng nếu attacker lấy được token từ log, máy tính bị xâm nhập, browser storage, proxy hoặc một hệ thống trung gian, attacker có thể phát lại token từ một máy khác cho đến khi token hết hạn hoặc bị thu hồi.

**DPoP giảm rủi ro token bị sử dụng độc lập với Client ban đầu.** Khi token được phát hành, Authorization Server liên kết nó với public key của Client. Khi Client gọi API, nó ký một proof JWT bằng private key. Resource Server xác minh proof và kiểm tra rằng public key đó chính là key đã được gắn với access token.

~~~mermaid
sequenceDiagram
    actor U as Người dùng
    participant C as OAuth2 Client
    participant AS as Authorization Server
    participant RS as Resource Server

    U->>C: Bắt đầu cấp quyền
    C->>AS: Token request + DPoP proof
    AS->>AS: Verify proof và lấy public key
    AS-->>C: Access token token_type=DPoP, cnf.jkt
    C->>RS: Authorization: DPoP token + DPoP proof mới
    RS->>RS: Verify proof signature, htm, htu, iat, jti, ath
    RS->>RS: So public-key thumbprint với access-token cnf.jkt
    RS->>RS: Verify access token và authorization policy
    RS-->>C: Resource response
~~~

Nếu attacker chỉ lấy được access token nhưng không có private key, request không có proof hợp lệ. Nếu attacker chỉ lấy được một proof cũ, proof đó bị ràng buộc với HTTP method, URI, thời gian, access-token hash và có thể bị chặn replay qua §jti§/nonce.

### 1.1. So sánh Bearer và DPoP-bound token

| Thuộc tính | Bearer access token | DPoP-bound access token |
| --- | --- | --- |
| Authorization scheme | §Bearer§ | §DPoP§ |
| Credential gửi đến Resource Server | Access token | Access token + DPoP proof |
| Chứng minh quyền sử dụng token | Sở hữu token | Sở hữu token và private key đã ràng buộc |
| Public-key binding | Không bắt buộc | §cnf.jkt§ hoặc metadata introspection tương ứng |
| Proof theo request | Không | Có, gắn với method/URI/token |
| Chống token bị đánh cắp riêng lẻ | Hạn chế | Mạnh hơn nếu private key không bị lộ |
| Chống replay proof | Không có proof | §jti§, cửa sổ thời gian và nonce theo policy |
| Thay thế TLS | Không | Không |

### 1.2. DPoP không phải PKCE, mTLS hay JWT encryption

Các cơ chế sau giải quyết những vấn đề khác nhau:

| Cơ chế | Ràng buộc điều gì? | Thời điểm chính |
| --- | --- | --- |
| **PKCE (RFC 7636)** | Authorization code với verifier mà Client giữ | Authorization Code flow |
| **DPoP (RFC 9449)** | Access token với public key và proof của private key | Token request và từng resource request |
| **OAuth mTLS (RFC 8705)** | Access token với certificate/client TLS identity | TLS connection và token/resource use |
| **JWT signature** | Claims token với khóa ký của issuer | Token validation |
| **JWE/encryption** | Nội dung token với khóa giải mã | Khi cần confidentiality của token |

Một Client có thể dùng **PKCE và DPoP cùng nhau**. PKCE bảo vệ authorization code trong quá trình đổi code; DPoP sender-constrain access token sau khi được cấp. DPoP cũng có thể kết hợp các biện pháp khác theo threat model.

## 2. Thành phần của DPoP

DPoP sử dụng một cặp khóa bất đối xứng:

- **Private key**: Client giữ bí mật và dùng để ký proof JWT.
- **Public key**: được đưa vào JOSE header của proof dưới trường §jwk§; Authorization Server dùng để ràng buộc token.
- **JWK thumbprint**: giá trị định danh public key, thường biểu diễn bằng claim §cnf.jkt§ trong JWT access token.

Private key phải được bảo vệ như một credential có giá trị cao. Với ứng dụng native/mobile, cân nhắc secure hardware/keystore phù hợp; với server-side Client, dùng secret/key management của server. Không gửi private key lên Authorization Server, Resource Server, browser log hoặc telemetry.

### 2.1. Header của DPoP proof JWT

Một proof JWT có JOSE header minh họa:

~~~json
{
  "typ": "dpop+jwt",
  "alg": "ES256",
  "jwk": {
    "kty": "EC",
    "crv": "P-256",
    "x": "<base64url-public-x>",
    "y": "<base64url-public-y>"
  }
}
~~~

Các yêu cầu quan trọng:

- §typ§ phải là §dpop+jwt§.
- §alg§ phải là thuật toán chữ ký bất đối xứng được đăng ký, được hỗ trợ và chấp nhận theo policy; không dùng §none§.
- §jwk§ chứa public key; không đưa private parameters vào header.
- Chữ ký phải xác minh được bằng public key trong §jwk§.
- Chỉ cho phép thuật toán và key type phù hợp với policy; không tự chấp nhận mọi thuật toán chỉ vì thư viện có thể parse.

### 2.2. Claims của DPoP proof

Proof ở token endpoint và proof ở protected-resource request có một số điểm khác nhau:

| Claim | Ý nghĩa | Token endpoint | Protected resource |
| --- | --- | --- | --- |
| §jti§ | ID duy nhất của proof | Bắt buộc | Bắt buộc |
| §htm§ | HTTP method của request | Bắt buộc | Bắt buộc |
| §htu§ | HTTP target URI, bỏ query và fragment | Bắt buộc | Bắt buộc |
| §iat§ | Thời điểm tạo proof | Bắt buộc | Bắt buộc |
| §ath§ | Hash của access token | Không dùng cho token request thông thường | **Bắt buộc** |
| §nonce§ | Nonce gần đây do AS/RS cung cấp | Khi server yêu cầu | Khi server yêu cầu |

Ví dụ payload proof cho token request:

~~~json
{
  "jti": "a5e91f10-4b74-4b72-a23b-cfe21df1c81b",
  "htm": "POST",
  "htu": "https://identity.example.test/oauth2/token",
  "iat": 1893456000
}
~~~

Ví dụ payload proof cho resource request:

~~~json
{
  "jti": "b6f02a21-5c85-4c83-b34c-d0f32ef2d92c",
  "htm": "GET",
  "htu": "https://api.example.test/api/orders/42",
  "iat": 1893456015,
  "ath": "<base64url-sha256-of-access-token>"
}
~~~

§jti§ cần có xác suất trùng cực thấp trong cửa sổ hiệu lực của proof; RFC 9449 nêu cách dùng ít nhất 96 bit dữ liệu ngẫu nhiên hoặc UUID version 4. Không dùng một giá trị §jti§ cố định cho nhiều request.

### 2.3. §htu§ không chứa query và fragment

Nếu request là:

~~~text
https://api.example.test/api/orders/42?view=compact#details
~~~

thì §htu§ trong proof không bao gồm query và fragment:

~~~text
https://api.example.test/api/orders/42
~~~

Server cần so sánh URI theo quy tắc normalization trong RFC 9449/RFC 3986. Không tự ý bỏ path segment, thay host hoặc scheme bằng cách không có hợp đồng. Với hệ thống sau reverse proxy/load balancer, cần bảo đảm server so sánh **URI công khai mà Client thực sự gọi** với URI được dựng từ request đáng tin.

### 2.4. §ath§ là hash của access token

Khi gửi access token đến Resource Server, proof phải chứa:

~~~text
ath = BASE64URL-NOPAD(SHA-256(ASCII(access_token_value)))
~~~

Hash này ràng buộc proof với **đúng access token đang được trình**. Nếu Client gửi token A nhưng proof được tạo cho token B, Resource Server phải từ chối.

Không nhầm §ath§ với:

- Hash của public key.
- Hash của toàn bộ HTTP request body.
- Hash của refresh token.
- Hash của chuỗi §Authorization: DPoP ...§.

### 2.5. §cnf.jkt§ trong access token

Khi Authorization Server chấp nhận proof lúc cấp token, nó liên kết access token với public key. Với JWT access token, thông tin thường có dạng:

~~~json
{
  "iss": "https://identity.example.test",
  "sub": "user-42",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "exp": 1893459600,
  "cnf": {
    "jkt": "<RFC7638-JWK-SHA256-THUMBPRINT>"
  }
}
~~~

§jkt§ là **JWK SHA-256 thumbprint theo RFC 7638** của public key dùng để ký DPoP proof. Không tự thay bằng hash tùy ý của PEM, DER hoặc chuỗi JSON đã serialize theo một thứ tự không chuẩn. Với opaque access token, Resource Server cần lấy thông tin binding tương ứng từ introspection response theo hợp đồng của Authorization Server.

## 3. Luồng cấp access token có DPoP

DPoP bắt đầu ngay ở token endpoint. Client tạo proof cho request đổi authorization code hoặc grant khác:

~~~http
POST /oauth2/token HTTP/1.1
Host: identity.example.test
Content-Type: application/x-www-form-urlencoded
DPoP: <signed-dpop-proof-jwt>

grant_type=authorization_code&
code=<authorization-code>&
redirect_uri=https%3A%2F%2Fshop.example.test%2Fcallback&
client_id=shop-web&
code_verifier=<pkce-verifier>
~~~

Authorization Server:

1. Xác minh DPoP proof JWT.
2. Kiểm tra §typ§, §alg§, public JWK, chữ ký và claims.
3. Kiểm tra method/URI/thời gian/nonce nếu yêu cầu.
4. Tính JWK thumbprint của public key.
5. Phát access token được ràng buộc với thumbprint đó.

Response minh họa:

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

**§token_type§ phải báo §DPoP§** để Client biết token cần được trình bằng scheme DPoP và kèm proof. Client không nên tự đổi token_type thành Bearer hoặc gửi cùng một token qua scheme khác.

### 3.1. DPoP proof ở token request khác proof ở resource request

Ở token endpoint, proof ràng buộc với endpoint phát token và request đổi grant. Nó không có §ath§ của access token mới, vì token chưa được phát trước khi request hoàn thành.

Ở protected resource request, access token đã có, nên proof phải thêm §ath§ để ràng buộc proof với token cụ thể.

### 3.2. Refresh token cũng cần proof

RFC 9449 áp dụng DPoP proof cho các access-token requests, bao gồm cả §refresh_token§ grant. Client cần tiếp tục dùng key đã ràng buộc hoặc thực hiện quy trình key/token rotation được Authorization Server hỗ trợ. Không gửi refresh token bằng một luồng không có proof nếu AS yêu cầu DPoP.

## 4. Gọi Resource Server bằng DPoP

Sau khi nhận access token, Client tạo **proof mới cho từng protected request**:

~~~http
GET /api/orders/42 HTTP/1.1
Host: api.example.test
Authorization: DPoP <dpop-bound-access-token>
DPoP: <new-signed-dpop-proof-jwt>
Accept: application/json
~~~

Resource Server kiểm tra:

1. Có đúng một DPoP header và một proof JWT hợp lệ.
2. Proof có §typ=dpop+jwt§, thuật toán bất đối xứng hợp lệ và public JWK không chứa private key.
3. Chữ ký proof xác minh bằng public JWK.
4. §htm§ khớp method thực tế.
5. §htu§ khớp URI thực tế sau normalization và bỏ query/fragment.
6. §iat§ nằm trong cửa sổ thời gian chấp nhận.
7. §jti§ chưa bị dùng lại trong thời gian proof còn được chấp nhận.
8. Nếu server yêu cầu nonce, §nonce§ khớp nonce gần đây do chính server đó phát.
9. §ath§ khớp hash của access token được gửi.
10. Public-key thumbprint trong proof khớp §cnf.jkt§ của access token hoặc metadata introspection tương ứng.
11. Access token vẫn hợp lệ theo issuer, audience, expiry, scope và các validators khác.

~~~mermaid
flowchart TD
    A["Authorization: DPoP token + DPoP proof"]
    B["Parse access token và proof"]
    C{"Proof JWT đúng format, typ, alg?"}
    D{"Chữ ký proof hợp lệ?"}
    E{"htm, htu, iat và nonce đúng?"}
    F{"jti chưa replay và ath đúng?"}
    G["Xác minh access token"]
    H{"cnf.jkt khớp proof public key?"}
    I["Tạo DPoP Authentication"]
    J["401 / DPoP challenge"]
    K["HTTP authorization: scope/role"]
    L["Business/resource authorization"]
    M["Trả resource"]

    A --> B --> C
    C -->|Không| J
    C -->|Có| D
    D -->|Không| J
    D -->|Có| E
    E -->|Không| J
    E -->|Có| F
    F -->|Không| J
    F -->|Có| G --> H
    H -->|Không| J
    H -->|Có| I --> K --> L --> M
~~~

Đây là sơ đồ khái niệm. Implementation có thể thực hiện các bước theo thứ tự khác nhau, nhưng không được bỏ một kiểm tra bắt buộc của RFC hoặc hợp đồng token.

## 5. Cách xử lý nonce và replay

### 5.1. Nonce là challenge do server phát

Authorization Server hoặc Resource Server có thể yêu cầu Client dùng nonce mới. Server trả header:

~~~http
DPoP-Nonce: <opaque-server-nonce>
~~~

Client phải tạo proof tiếp theo có claim:

~~~json
{
  "jti": "new-unique-proof-id",
  "htm": "GET",
  "htu": "https://api.example.test/api/orders/42",
  "iat": 1893456015,
  "ath": "<token-hash>",
  "nonce": "<opaque-server-nonce>"
}
~~~

Nonce là giá trị opaque đối với Client. Client không tự giải mã, sửa hoặc dùng nonce của server A cho server B.

### 5.2. Authorization Server và Resource Server có nonce riêng

Nonce từ Authorization Server chỉ được dùng cho request đến Authorization Server đó. Nonce từ Resource Server chỉ được dùng với Resource Server đã phát. Nếu Client gọi nhiều API hoặc nhiều issuer, cần lưu nonce theo **server origin/endpoint context** phù hợp; không dùng một biến global chung cho tất cả.

### 5.3. §jti§ và replay cache

DPoP proof có thể bị đánh cắp rồi replay tại cùng endpoint trong cửa sổ thời gian. RFC yêu cầu server giới hạn tuổi proof; lưu §jti§ đã sử dụng là biện pháp mạnh để từ chối proof trùng.

Trong môi trường nhiều instance:

- Replay cache chỉ ở memory của một instance có thể không đủ nếu request thứ hai đi tới instance khác.
- Dùng shared cache/store hoặc cơ chế chống replay phân tán theo SLA và threat model.
- TTL của replay entry phải ít nhất bao phủ cửa sổ chấp nhận proof.
- Key cache nên ràng buộc proof context phù hợp, tránh collision giữa issuers/servers.
- Giới hạn độ dài §jti§ và số entry để tránh memory exhaustion.
- Chỉ xóa entry khi proof không còn được chấp nhận.

Nonce có thể giảm khả năng proof được tạo trước quá lâu, nhưng **nonce không thay việc quản lý replay theo §jti§**.

### 5.4. Clock skew

§iat§ dựa trên đồng hồ Client. Server phải có cửa sổ chấp nhận phù hợp và đồng hồ hệ thống cần đồng bộ. Cửa sổ quá rộng làm proof bị replay lâu hơn; quá hẹp làm request hợp lệ bị từ chối vì lệch giờ.

Server-provided nonce có thể giúp giảm phụ thuộc vào đồng hồ Client. Cần theo dõi clock drift và kiểm thử các trường hợp proof quá cũ/quá xa tương lai.

## 6. DPoP không bỏ qua authorization thông thường

DPoP chỉ chứng minh Client nắm private key đã ràng buộc với token. Nó **không cấp quyền nghiệp vụ**.

Ví dụ token có:

~~~json
{
  "scope": "orders.read",
  "aud": ["orders-api"],
  "cnf": {
    "jkt": "<client-key-thumbprint>"
  }
}
~~~

Proof hợp lệ có thể giúp request qua bước authentication, nhưng endpoint hủy đơn vẫn cần §SCOPE_orders.cancel§ hoặc permission phù hợp. User còn phải có quyền trên đúng Order, owner, tenant và trạng thái nghiệp vụ.

| Lớp | Câu hỏi |
| --- | --- |
| Token validation | Token do issuer tin cậy phát, đúng audience và còn hạn không? |
| DPoP proof | Client có private key tương ứng, proof gắn đúng request/token không? |
| Scope/authority | Token có quyền thực hiện loại thao tác này không? |
| Tenant/resource policy | Caller có quyền trên tài nguyên cụ thể không? |
| Business rule | Trạng thái đơn có cho phép thao tác không? |

**Không coi DPoP authentication thành authorization.** Một proof hợp lệ không biến user reader thành order admin.

## 7. Phạm vi hỗ trợ theo phiên bản Spring Security

Các mốc dưới đây phân biệt **lớp xác thực DPoP**, **API cấu hình**, và **phạm vi Servlet/WebFlux**. Đây là những thứ dễ bị gộp nhầm khi nâng cấp.

| Phiên bản | DPoP Resource Server | API cấu hình DPoP riêng | Ghi chú |
| --- | --- | --- | --- |
| **6.4.x và cũ hơn** | Chưa có built-in §DPoPAuthenticationProvider§ | Không | Cần custom integration hoặc giải pháp khác; không giả định default Bearer Resource Server tự xác minh proof |
| **6.5.x** | Có các lớp DPoP Resource Server; §DPoPAuthenticationProvider§/§DPoPAuthenticationToken§ được đánh dấu §@since 6.5§ | Chưa có fluent §dPoP(...)§ configurer | Nhánh 6.5 có tài liệu DPoP; bộ test resource-server dùng JWT DSL và DPoP scheme/proof |
| **7.0.x** | DPoP-bound access token tiếp tục được tài liệu hóa | Chưa có §DPoPConfigurer§ API §@since 7.1§ | Không copy DSL mới từ 7.1 sang 7.0 |
| **7.1.x** | Có DPoP Resource Server | Có §OAuth2ResourceServerConfigurer.dPoP(...)§ | Có thể tùy chỉnh request matcher, authentication converter, success/failure handler |
| **7.2.0-RC1 / preview** | Kế thừa hỗ trợ trước đó | Có thêm tùy chỉnh proof verifier factory theo API preview | Chỉ dùng theo trạng thái phát hành thực tế; không coi RC là stable |

### 7.1. Spring Security 6.4 và cũ hơn

API chính thức của §DPoPAuthenticationProvider§ ghi §Since: 6.5§. Vì vậy các dòng 6.4 trở về trước không có cùng built-in DPoP Resource Server provider. Một ứng dụng chỉ cấu hình:

~~~java
.oauth2ResourceServer(oauth2 -> oauth2
    .jwt(Customizer.withDefaults()))
~~~

vẫn đang dùng **JWT Bearer validation**. Không được tuyên bố endpoint đã xác minh DPoP chỉ vì request có thêm header §DPoP§. Nếu bắt buộc hỗ trợ DPoP trên dòng cũ, phải tự triển khai/đưa vào một integration đã được đánh giá: proof decoder, binding check, replay/nonce policy, scheme downgrade protection và test tương ứng.

### 7.2. Spring Security 6.5

Đây là mốc có DPoP Resource Server support trong Spring Security:

- §DPoPAuthenticationProvider§ được thêm với §@since 6.5§.
- Có §DPoPAuthenticationToken§ đại diện authentication của protected resource request.
- Có §DPoPProofJwtDecoderFactory§ phục vụ xác minh proof JWT.
- Tài liệu 6.5 có trang **OAuth 2.0 DPoP-bound Access Tokens**.
- Bộ test DPoP Resource Server trong dòng phát triển 6.5 minh họa request §Authorization: DPoP§ và header §DPoP§; cấu hình test sử dụng JWT Resource Server DSL.

Ví dụ cấu hình JWT Resource Server:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class ResourceServerSecurity {

    @Bean
    SecurityFilterChain api(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .anyRequest().authenticated())
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults()))
            .build();
    }
}
~~~

Đoạn code cho thấy cấu hình JWT Resource Server cơ bản. Trong 6.5, **không thêm §.dPoP(...)§** vì fluent configurer ấy chưa tồn tại trong API 6.5. Khi triển khai thật, hãy kiểm thử request DPoP bằng đúng patch version và token profile/issuer của hệ thống; không chỉ kiểm tra Bearer JWT thông thường.

### 7.3. Spring Security 7.0

Nhánh 7.0 tiếp tục có tài liệu DPoP-bound access token cho Servlet Resource Server. Tuy nhiên, API nested class §OAuth2ResourceServerConfigurer.DPoPConfigurer§ được đánh dấu **§Since: 7.1§**. Vì vậy không được dùng ví dụ §.dPoP(...)§ rồi mong biên dịch trên 7.0.

Khi cần cấu hình sâu hơn ở 7.0, đối chiếu API và behavior của đúng minor/patch đang sử dụng. Không tự tạo một method extension giả tên §dPoP§ rồi cho rằng đó là API framework.

### 7.4. Spring Security 7.1

Spring Security 7.1 bổ sung fluent API:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class DPoPResourceServerSecurity {

    @Bean
    SecurityFilterChain api(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .anyRequest().authenticated())
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults())
                .dPoP(Customizer.withDefaults()))
            .build();
    }
}
~~~

Tên method trong API là **§dPoP§** (chữ P viết hoa ở giữa), không phải §dpop§. §DPoPConfigurer§ trong 7.1 cho phép tùy chỉnh:

- §requestMatcher(...)§: xác định request nào thuộc luồng DPoP.
- §authenticationConverter(...)§: chuyển request thành §DPoPAuthenticationToken§.
- §authenticationSuccessHandler(...)§: xử lý sau authentication thành công.
- §authenticationFailureHandler(...)§: xử lý lỗi proof/token.

Các tùy chọn này không thay các validators access token và không tự cấu hình Authorization Server. Hãy dùng chúng khi cần tích hợp với request routing, failure response hoặc converter đặc thù.

### 7.5. Spring Security 7.2 preview

API preview 7.2 bổ sung khả năng cấu hình §JwtDecoderFactory<DPoPProofContext>§ cho proof verifier thông qua DPoP configurer. Đây là thay đổi hữu ích nếu deployment cần custom proof validation policy, decoder factory hoặc kiểm soát clock/skew theo context.

**Tuy nhiên, RC/SNAPSHOT không phải stable release.** Trước khi dùng trong production, xác nhận version đã GA, API cuối cùng, compatibility matrix và release notes của patch tương ứng. Đừng copy API preview vào project vẫn đang dùng 7.1.

### 7.6. WebFlux/Reactive Resource Server

Các tài liệu WebFlux Resource Server mô tả §ReactiveJwtDecoder§ và §ReactiveOpaqueTokenIntrospector§ cho JWT/opaque token. Nhưng API DPoP configurer được công bố ở §OAuth2ResourceServerConfigurer§ của **Servlet/HttpSecurity**, dùng §HttpServletRequest§, §AuthenticationFilter§ và §AuthenticationProvider§ đồng bộ.

Vì vậy, với các phiên bản được đối chiếu ở đây:

- Không giả định §ServerHttpSecurity.oauth2ResourceServer().jwt()§ tự xác minh DPoP proof.
- Không tự tạo một proof rồi gửi đến WebFlux API và cho rằng token đã sender-constrained.
- Nếu cần DPoP trong WebFlux, phải xác minh hỗ trợ cụ thể của release/library đang dùng hoặc triển khai một reactive authentication pipeline có đầy đủ proof validation, binding, nonce/replay và tests.
- Không dùng §block()§ để gọi DPoP verifier đồng bộ trong Netty event loop như một cách ghép nhanh.

### 7.7. Spring Security OAuth2 Client và Authorization Server là thành phần riêng

DPoP protocol có ba vai trò:

1. **Client** tạo proof cho token endpoint và từng resource request.
2. **Authorization Server** xác minh proof ở token endpoint và gắn key thumbprint vào access token.
3. **Resource Server** xác minh proof và access-token binding ở protected request.

Tài liệu DPoP của Spring Security trong phần Resource Server chứng minh hỗ trợ ở **phía API nhận token**. Không suy ra §oauth2Client()§ tự động sinh DPoP proof cho mọi token request hoặc WebClient request. Cần xác nhận client/provider cụ thể hoặc custom token-response client/request interceptor.

Tương tự, **Spring Authorization Server là project riêng**. Tài liệu Protocol Endpoints của project đó có mục DPoP-bound Access Tokens; version và cấu hình của Authorization Server phải được kiểm tra độc lập với version Spring Security Resource Server.

## 8. Cấu hình DPoP trên Servlet Resource Server

### 8.1. Dependency

Với Spring Boot, dependency Resource Server thường là:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
~~~

Nếu cần JWT decoding, Spring Security dùng module JOSE tương ứng qua dependency management. Để giữ compatibility, dùng **Spring Boot BOM hoặc Spring Security BOM** thay vì trộn các module Spring Security khác minor/patch.

### 8.2. Cấu hình JWT issuer

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://identity.example.test
          jwk-set-uri: https://identity.example.test/oauth2/jwks
~~~

Đây là giá trị minh họa. Resource Server vẫn phải xác minh issuer, chữ ký, thời hạn, audience và profile access token theo hợp đồng. DPoP proof hợp lệ không cứu được một access token sai issuer hoặc dành cho API khác.

### 8.3. Cấu hình 7.1+ với DPoP configurer

~~~java
@Bean
SecurityFilterChain api(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/api/public/**").permitAll()
            .requestMatchers("/api/orders/**")
                .hasAuthority("SCOPE_orders.read")
            .anyRequest().denyAll())
        .oauth2ResourceServer(oauth2 -> oauth2
            .jwt(Customizer.withDefaults())
            .dPoP(Customizer.withDefaults()))
        .build();
}
~~~

Đây là cấu hình Servlet 7.1+ minh họa DPoP path. Đối với ứng dụng chỉ chấp nhận DPoP-bound token trên một số route, dùng §requestMatcher§ theo hợp đồng và test các route còn lại. Tránh cấu hình một route cho phép Bearer fallback vô tình làm mất sender constraint.

### 8.4. Tùy chỉnh matcher

Ví dụ khái niệm:

~~~java
.oauth2ResourceServer(oauth2 -> oauth2
    .jwt(Customizer.withDefaults())
    .dPoP(dpop -> dpop
        .requestMatcher(request ->
            request.getRequestURI().startsWith("/api/dpop/"))))
~~~

Đoạn code chỉ minh họa vị trí tùy chỉnh. Trong ứng dụng thực, matcher cần xét HTTP method, route, proxy/path normalization và chính sách token. Không dùng một matcher rộng nếu các endpoint khác vẫn chấp nhận Bearer token cho cùng tài nguyên mà không có chủ đích.

### 8.5. DPoP và JWT decoder là hai lớp khác nhau

§JwtDecoder§ xác minh access token JWT. DPoP verifier xác minh proof JWT. Hai JWT có mục đích, issuer/key và validation rules khác nhau:

| JWT | Ai ký? | Ai xác minh? | Mục đích |
| --- | --- | --- | --- |
| Access token JWT | Authorization Server | Resource Server | Claims và quyền của token |
| DPoP proof JWT | Client | Authorization Server hoặc Resource Server | Chứng minh Client có private key và ràng buộc request |

Không dùng decoder access-token thông thường để chấp nhận proof như access token, và không dùng public key trong proof thay cho khóa issuer khi xác minh access-token signature.

## 9. JWT và opaque token binding

### 9.1. JWT access token

Với JWT, Resource Server đọc §cnf.jkt§ từ claims đã xác minh:

~~~json
{
  "iss": "https://identity.example.test",
  "aud": ["orders-api"],
  "sub": "user-42",
  "scope": "orders.read",
  "exp": 1893459600,
  "cnf": {
    "jkt": "abc123..."
  }
}
~~~

Proof chứa public JWK. Server tính thumbprint theo RFC 7638 và so sánh với §cnf.jkt§. Nếu khác, từ chối.

### 9.2. Opaque access token

Với opaque token, Resource Server không tự đọc JWT claims. Introspection endpoint phải cung cấp metadata xác định token được ràng buộc với key nào, thường qua §cnf.jkt§:

~~~json
{
  "active": true,
  "scope": "orders.read",
  "aud": ["orders-api"],
  "sub": "user-42",
  "cnf": {
    "jkt": "abc123..."
  }
}
~~~

Response này là ví dụ theo hợp đồng; không phải mọi introspection response đều có cùng field. Nếu AS không cung cấp binding metadata cần thiết, Resource Server không thể xác nhận proof key với access token một cách đúng đắn.

### 9.3. Active không có nghĩa DPoP-bound

Một introspection response §active=true§ chỉ cho biết token còn active theo AS. Nếu token không có §cnf.jkt§ hoặc metadata binding theo hợp đồng, không thể mặc định đó là DPoP-bound token. Resource Server cần phân biệt:

- Bearer token bình thường.
- DPoP-bound token có key binding.
- Token không hợp lệ hoặc metadata không đủ.

## 10. Ví dụ tạo DPoP proof bằng Nimbus

Proof JWT có thể được tạo bằng thư viện JOSE như Nimbus. Ví dụ sau mô tả **cấu trúc**, không phải một client hoàn chỉnh:

~~~java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.Base64;
import java.util.UUID;

import com.nimbusds.jose.jwk.JWKSet;
import com.nimbusds.jose.jwk.RSAKey;
import com.nimbusds.jose.jwk.source.JWKSource;
import com.nimbusds.jose.proc.SecurityContext;

import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.jwt.JwsHeader;
import org.springframework.security.oauth2.jwt.JwtClaimsSet;
import org.springframework.security.oauth2.jwt.JwtEncoder;
import org.springframework.security.oauth2.jwt.JwtEncoderParameters;
import org.springframework.security.oauth2.jwt.NimbusJwtEncoder;

import java.time.Instant;

public final class DPoPProofFactory {

    private final RSAKey clientKey; // Có cả private/public key ở phía Client
    private final JwtEncoder proofEncoder;

    public DPoPProofFactory(RSAKey clientKey) {
        this.clientKey = clientKey;
        JWKSource<SecurityContext> jwkSource =
            (selector, context) ->
                selector.select(new JWKSet(clientKey));
        this.proofEncoder = new NimbusJwtEncoder(jwkSource);
    }

    public String createResourceProof(
            String method,
            String targetUriWithoutQueryOrFragment,
            String accessToken) throws Exception {

        String ath = sha256Base64Url(accessToken);

        JwsHeader header = JwsHeader
            .with(SignatureAlgorithm.RS256)
            .type("dpop+jwt")
            .jwk(clientKey.toPublicJWK().toJSONObject())
            .build();

        JwtClaimsSet claims = JwtClaimsSet.builder()
            .id(UUID.randomUUID().toString())
            .issuedAt(Instant.now())
            .claim("htm", method)
            .claim("htu", targetUriWithoutQueryOrFragment)
            .claim("ath", ath)
            .build();

        return this.proofEncoder
            .encode(JwtEncoderParameters.from(header, claims))
            .getTokenValue();
    }

    private static String sha256Base64Url(String token)
            throws Exception {
        MessageDigest sha256 = MessageDigest.getInstance("SHA-256");
        byte[] digest = sha256.digest(
            token.getBytes(StandardCharsets.US_ASCII));
        return Base64.getUrlEncoder()
            .withoutPadding()
            .encodeToString(digest);
    }
}
~~~

Các lưu ý khi dùng code:

- Ví dụ dùng RSA/RS256 để dễ đọc; thuật toán thực tế phải phù hợp RFC 9449, key type và policy của AS/RS.
- §clientKey§ phải được nạp từ key store/secure storage; không hardcode private key trong source.
- §targetUriWithoutQueryOrFragment§ phải là URI thực tế của request theo RFC, không lấy một URL tùy ý không liên quan.
- Tạo **proof mới cho mỗi request**; không tái sử dụng proof từ request trước.
- Với token endpoint, tạo proof riêng cho method/URI token endpoint và không thêm §ath§ như protected-resource proof.
- Nếu server trả §DPoP-Nonce§, thêm claim §nonce§ đúng giá trị server cung cấp.
- Thumbprint để so §cnf.jkt§ phải được tính theo **RFC 7638 JWK thumbprint**, không dùng hàm §sha256Base64Url§ ở đây; hàm trên chỉ dành cho §ath§.

## 11. Cách kiểm thử DPoP

Kiểm thử DPoP không nên dừng ở một request thành công. Cần chứng minh token được ràng buộc với đúng key và proof gắn đúng request.

### 11.1. Test matrix

| Test | Access token | Proof | Kết quả |
| --- | --- | --- | --- |
| Happy path | Token DPoP-bound, §cnf.jkt§ đúng | Proof đúng key, method, URI, iat, jti, ath | Được authentication; tiếp tục authorization |
| Thiếu proof | DPoP-bound | Không có §DPoP§ header | Từ chối |
| Scheme sai | DPoP-bound | Gửi token dưới §Bearer§ | Từ chối, chống downgrade |
| Public key khác | §cnf.jkt§ của key A | Proof ký bằng key B | Từ chối |
| Sai chữ ký | Token binding đúng | Proof signature invalid | Từ chối |
| Sai typ | Token binding đúng | §typ§ không phải §dpop+jwt§ | Từ chối |
| Thuật toán không hợp lệ | Token binding đúng | §alg=none§ hoặc không được phép | Từ chối |
| Private JWK lộ trong header | Token binding đúng | §jwk§ chứa private parameters | Từ chối |
| Sai method | Token binding đúng | §htm§ khác HTTP method | Từ chối |
| Sai URI | Token binding đúng | §htu§ khác target URI | Từ chối |
| Sai token hash | Token A | Proof có §ath§ của token B | Từ chối |
| Proof hết cửa sổ thời gian | Token hợp lệ | §iat§ quá cũ/quá xa tương lai | Từ chối |
| Replay | Token hợp lệ | §jti§ đã dùng | Từ chối theo replay policy |
| Nonce thiếu | Server yêu cầu nonce | Proof không có §nonce§ | Challenge/reject theo RFC |
| Nonce sai | Server đã cấp nonce N | Proof dùng nonce M | Từ chối |
| Duplicate header | Token hợp lệ | Nhiều §DPoP§ headers | Từ chối |
| Token hết hạn | Token hết hạn | Proof hợp lệ | Từ chối do token validation |
| Scope thiếu | Token DPoP-bound hợp lệ | Proof hợp lệ | Authentication có thể thành công; authorization 403 |

### 11.2. Kiểm thử §cnf.jkt§ mismatch

Chuẩn bị:

- Client key A.
- Client key B.
- Access token có §cnf.jkt§ của A.
- Proof ký bằng A và proof ký bằng B.

Kỳ vọng:

~~~text
Token cnf.jkt = thumbprint(A)
Proof public JWK = A -> pass DPoP authentication
Proof public JWK = B -> fail DPoP authentication
~~~

Đây là test quan trọng nhất để chứng minh sender constraint đang hoạt động. Nếu test chỉ kiểm tra proof signature hợp lệ mà không so với access token binding, attacker có thể dùng bất kỳ key nào để tạo proof.

### 11.3. Kiểm thử chống downgrade sang Bearer

Một lỗi nguy hiểm là token đã DPoP-bound vẫn được chấp nhận khi Client gửi:

~~~http
Authorization: Bearer <dpop-bound-access-token>
~~~

DPoP-bound token phải được trình theo scheme DPoP và kèm proof. Nếu cùng endpoint cho phép Bearer fallback không kiểm tra binding, attacker có thể bỏ qua proof. Test phải xác nhận **token DPoP-bound không thể bị downgrade** sang Bearer.

### 11.4. Kiểm thử replay với nhiều instance

Giả sử proof P được chấp nhận tại instance A. Gửi lại P tới instance B trong cửa sổ thời gian còn hiệu lực. Nếu hệ thống cam kết replay protection dùng shared store, request thứ hai phải bị từ chối. Test single-node không đủ chứng minh replay protection phân tán.

### 11.5. Kiểm thử nonce

Một test sequence:

1. Gửi request không có nonce trong khi RS yêu cầu nonce.
2. Xác nhận response có §DPoP-Nonce§ và lỗi §use_dpop_nonce§ theo contract.
3. Client tạo proof mới với nonce vừa nhận.
4. Gửi lại request với proof mới.
5. Xác nhận thành công nếu các điều kiện khác đúng.
6. Thử nonce từ một Resource Server khác; phải bị từ chối.

### 11.6. MockMvc và signed proof

Trong Servlet stack, có thể dùng MockMvc với test key pair:

~~~java
mockMvc.perform(get("/api/orders/42")
        .header("Authorization", "DPoP " + accessToken)
        .header("DPoP", proof))
    .andExpect(status().isOk());
~~~

Đây chỉ là phần request trong test; §accessToken§ phải được ký bằng test issuer key, có §cnf.jkt§ đúng, còn §proof§ phải được ký bằng private key tương ứng và có §htm§/§htu§/§ath§ đúng. Không dùng chuỗi JWT giả hoặc chỉ mock Authentication nếu mục tiêu là kiểm tra proof validation.

## 12. Proxy, load balancer và URI canonicalization

DPoP proof gắn với §htu§. Khi Client gọi:

~~~text
https://api.example.test/orders/42
~~~

nhưng reverse proxy chuyển tới backend:

~~~text
http://orders-service:8080/orders/42
~~~

Resource Server có thể nhìn thấy scheme/host khác với URI mà Client đã ký. Nếu so sánh sai, request hợp lệ bị từ chối; nếu tin header forwarded do attacker tự đặt, attacker có thể làm sai URI context.

Cần:

- Cấu hình trusted proxy và forwarded-header handling đúng.
- Chỉ tin §Forwarded§/§X-Forwarded-*§ từ proxy đáng tin.
- Dựng external URI theo cùng contract mà Client dùng.
- Kiểm thử HTTPS termination, host rewrite, path prefix và port.
- Không tắt kiểm tra §htu§ chỉ để vượt lỗi proxy.
- Áp dụng URI normalization theo RFC, không tự loại bỏ thành phần tùy ý.

## 13. Giới hạn và rủi ro DPoP

### 13.1. Nếu attacker lấy được cả token và private key

DPoP không bảo vệ khi attacker kiểm soát Client hoặc lấy được **cả access token lẫn private key**. Private key protection là phần cốt lõi của thiết kế.

### 13.2. XSS vẫn có thể dùng DPoP key qua ứng dụng

Trong SPA/browser, nếu script độc hại chạy cùng origin và có quyền gọi signing API hoặc sử dụng code ký proof, nó có thể tạo request DPoP hợp lệ ngay cả khi không export private key. DPoP giảm token replay từ thiết bị khác; nó không loại bỏ XSS.

### 13.3. Không thay TLS

DPoP là cơ chế ở application layer. Vẫn phải dùng HTTPS/TLS để bảo vệ confidentiality và integrity của request/response, token, proof và dữ liệu người dùng.

### 13.4. Không thay access-token lifetime và revocation

Token vẫn cần TTL, scope tối thiểu, audience đúng, rotation/revocation theo policy. Nếu key bị mất hoặc compromise, Client có thể cần hủy/revoke token và đăng ký key mới. DPoP không tự cung cấp quy trình quản lý vòng đời key.

### 13.5. Proof replay vẫn có thể xảy ra trong cửa sổ chấp nhận

Nếu attacker lấy được proof trước khi hết hạn và server không track replay, attacker có thể thử phát lại proof tại đúng endpoint/method. Giới hạn thời gian, §jti§ store và nonce giúp giảm rủi ro.

### 13.6. CORS không phải DPoP validation

DPoP không thay CORS, CSRF hoặc authorization. CORS điều khiển browser cross-origin access; DPoP xác minh proof key; scope/resource policy quyết định quyền. Nếu API dùng cookie/session làm credential, vẫn phải xem xét CSRF.

## 14. Triển khai theo từng vai trò

| Vai trò | Trách nhiệm DPoP | Điều phải kiểm thử |
| --- | --- | --- |
| OAuth2 Client | Giữ private key, tạo proof cho token/resource request, xử lý nonce | Proof mới, đúng URI/method/ath, key rotation |
| Authorization Server | Xác minh proof ở token endpoint, gắn public-key thumbprint vào token | §token_type=DPoP§, §cnf.jkt§, nonce, grant/refresh |
| Resource Server | Xác minh proof và access-token binding | §htm§, §htu§, §ath§, §jti§, nonce, token validation |
| API gateway/proxy | Chuyển tiếp header và external URI chính xác | Không bỏ DPoP header, không làm sai forwarded host/scheme |
| Key management | Bảo vệ private key, rotation và revoke | Không log/export key, xử lý mất key |

Một hệ thống chỉ triển khai DPoP ở Resource Server nhưng Authorization Server vẫn phát **Bearer token bình thường** chưa tạo ra DPoP-bound token. Tương tự, Client tự gửi header §DPoP§ nhưng AS không gắn §cnf.jkt§ và RS không xác minh binding thì đó chỉ là một header không có giá trị sender-constraining.

## 15. Những lỗi triển khai thường gặp

### 15.1. Dùng §Bearer§ cho DPoP-bound token

DPoP-bound token phải được trình với scheme §DPoP§. Chấp nhận token ấy như Bearer mà bỏ proof tạo đường downgrade.

### 15.2. Tái sử dụng một proof cho nhiều request

Proof gắn với method/URI/token hash và ID riêng. Tạo proof mới cho mỗi request; không cache proof như access token.

### 15.3. Bỏ §ath§ ở resource request

Nếu proof không ràng buộc với access token hiện tại, proof có thể bị dùng sai với một token khác. §ath§ là claim bắt buộc khi DPoP proof đi cùng access token đến protected resource.

### 15.4. Dùng hash không đúng cho §ath§

§ath§ là base64url-no-padding của SHA-256 trên **ASCII bytes của access-token value**. Không hash chuỗi JSON, header Authorization hoặc JWK.

### 15.5. Dùng hash tùy ý thay §cnf.jkt§

§jkt§ phải là JWK thumbprint theo RFC 7638. Hash DER/PEM tùy ý không tương đương.

### 15.6. Không kiểm tra URI sau reverse proxy

Nếu server so §htu§ với internal URI nhưng Client ký external URI, request hợp lệ có thể fail. Không giải quyết bằng cách bỏ kiểm tra; phải cấu hình proxy trust và URI reconstruction.

### 15.7. Chỉ kiểm tra chữ ký proof

Proof signature hợp lệ không đủ. Còn phải kiểm tra §typ§, §alg§, §jwk§ public-only, §htm§, §htu§, §iat§, §jti§, §ath§, nonce và key binding.

### 15.8. Không lưu replay state trong cluster

Replay cache cục bộ không phát hiện proof đã được dùng tại instance khác. Thiết kế storage và TTL phù hợp topology.

### 15.9. Dùng nonce sai server

Nonce của AS và nonce của RS là hai namespace khác nhau. Không chia sẻ nonce giữa các issuer/resource servers.

### 15.10. Nhầm DPoP với PKCE

PKCE không sender-constrain access token. DPoP không thay việc bảo vệ authorization code. Có thể và thường nên dùng cả hai.

### 15.11. Nhầm DPoP Resource Server với OAuth2 Client

§DPoPAuthenticationProvider§ là lớp xác thực request ở Resource Server. Không suy ra §oauth2Client()§ tự tạo proof cho token endpoint hoặc request downstream.

### 15.12. Dùng DSL 7.1 trên 6.5/7.0

§OAuth2ResourceServerConfigurer.dPoP(...)§ có §@since 7.1§. Không dùng method này khi compile với 6.5 hoặc 7.0.

### 15.13. Nghĩ WebFlux tự có DPoP vì hỗ trợ JWT

Reactive JWT decoding và DPoP proof validation là hai tính năng khác nhau. Phải xác nhận API reactive DPoP có trong đúng version; không tự dùng Servlet provider trong Netty event loop.

### 15.14. Cho phép access token thường đi qua endpoint DPoP mà không policy rõ

Một endpoint có thể hỗ trợ nhiều token types, nhưng phải có policy rõ về scheme và binding. Không dùng một matcher/filter chain khiến DPoP-bound token có thể rơi vào Bearer path.

### 15.15. Coi DPoP là thay thế mọi bảo vệ khác

DPoP không thay TLS, scope, audience, authorization theo tenant/owner, CSRF nếu dùng cookie, XSS protection, key management hoặc revocation.

## 16. Checklist triển khai

### Authorization Server

- [ ] Chấp nhận DPoP proof tại token endpoint theo RFC 9449.
- [ ] Kiểm tra §typ§, §alg§, public JWK, chữ ký, §htm§, §htu§, §iat§, §jti§ và nonce khi yêu cầu.
- [ ] Gắn key thumbprint vào access token bằng §cnf.jkt§ hoặc introspection metadata.
- [ ] Trả §token_type=DPoP§.
- [ ] Có policy nonce và replay phù hợp.
- [ ] Xử lý refresh-token grant theo DPoP policy.

### OAuth2 Client

- [ ] Sinh và bảo vệ private key.
- [ ] Tạo proof mới cho token request và từng resource request.
- [ ] Dùng đúng method và URI; bỏ query/fragment khỏi §htu§.
- [ ] Thêm §ath§ cho protected-resource proof.
- [ ] Gửi §Authorization: DPoP§ và §DPoP§ header.
- [ ] Xử lý §DPoP-Nonce§ theo đúng server đã cấp.
- [ ] Không log token, proof hoặc private key.
- [ ] Có quy trình rotate/revoke key.

### Resource Server

- [ ] Dùng Spring Security version có DPoP support phù hợp.
- [ ] Xác minh access token độc lập với proof.
- [ ] Xác minh proof JWT và public-key binding.
- [ ] Kiểm tra §ath§, §htm§, §htu§, §iat§, §jti§, nonce.
- [ ] Chặn duplicate DPoP headers.
- [ ] Chặn downgrade DPoP-bound token sang Bearer.
- [ ] Có replay cache phù hợp khi chạy cluster.
- [ ] Cấu hình proxy/forwarded headers đúng.
- [ ] Kiểm tra scope, audience, tenant, owner và business policy sau authentication.

### Phiên bản Spring Security

- [ ] 6.5+: xác nhận API/provider có trong patch version.
- [ ] 7.0: không dùng fluent §dPoP(...)§ nếu chưa có API 7.1.
- [ ] 7.1+: dùng đúng §dPoP§ DSL và test matcher/handlers.
- [ ] 7.2 preview: chỉ dùng proof verifier customization nếu release đã được phê duyệt.
- [ ] WebFlux: xác nhận hỗ trợ reactive DPoP riêng; không suy từ reactive JWT support.

## 17. Tình huống thực hành

**Tình huống A — Access token bị đánh cắp:** Attacker có access token nhưng không có private key của Client. Với DPoP, attacker có thể dùng token bằng header Bearer không?

**Không.** Token DPoP-bound phải được trình bằng scheme §DPoP§ và proof hợp lệ gắn với key. Nếu API vẫn nhận nó qua Bearer path, cần kiểm tra downgrade protection.

**Tình huống B — Proof hợp lệ nhưng token sai audience:** Proof có chữ ký đúng, §htm§/§htu§/§ath§ đúng, nhưng access token dành cho §billing-api§. Orders API có cho phép không?

**Không.** DPoP proof không thay audience validation. Token phải được cấp cho Resource Server đang nhận request.

**Tình huống C — Client gửi proof của GET cho POST:** Token và key đúng nhưng §htm§ là GET trong khi request là POST. Kết quả?

**Từ chối.** Proof được ràng buộc với HTTP method của request.

**Tình huống D — Client thêm query parameter:** Request có §?page=2§ nhưng §htu§ không chứa query. Có sai không?

Không nhất thiết. Theo RFC, §htu§ bỏ query và fragment. Những yếu tố còn lại của URI vẫn phải khớp sau normalization.

**Tình huống E — Replay cùng proof:** Một proof được gửi thành công tới instance A, sau đó gửi lại cùng method/URI/token tới instance B. Nếu hệ thống cam kết replay detection phân tán thì sao?

Request thứ hai phải bị từ chối vì §jti§ đã được dùng. Replay cache chỉ ở memory từng instance có thể không đủ.

**Tình huống F — AS yêu cầu nonce:** Client nhận §DPoP-Nonce§ từ AS. Có thể dùng nonce đó khi gọi Orders API không?

**Không.** Nonce thuộc server đã phát; nonce của AS không phải nonce của Resource Server.

**Tình huống G — Spring Security 6.5:** Developer copy §.dPoP(Customizer.withDefaults())§ từ ví dụ 7.1. Điều gì xảy ra?

Method này không thuộc API 6.5. Dùng API có trong version hoặc nâng cấp; đừng tự thêm extension để giả lập API framework.

**Tình huống H — Spring Security 7.1:** API cần custom request matcher và failure handler cho DPoP. Dùng API nào?

Dùng §OAuth2ResourceServerConfigurer.dPoP(...)§ và tùy chỉnh §DPoPConfigurer§. API này có từ 7.1.

**Tình huống I — WebFlux:** Ứng dụng có §ReactiveJwtDecoder§ nên developer cho rằng DPoP proof cũng tự được xác minh. Kết luận?

Không thể suy ra như vậy. Cần xác nhận hỗ trợ DPoP cho đúng WebFlux release hoặc custom reactive authentication pipeline.

**Tình huống J — XSS:** Script độc hại chạy trong Client có thể gọi API qua code ký DPoP mà không export private key. DPoP có ngăn được không?

Không nhất thiết. DPoP giảm khả năng dùng token từ thiết bị không có key, nhưng script đã kiểm soát Client có thể lợi dụng quyền ký proof của ứng dụng. XSS defense và key protection vẫn cần.

**Tình huống K — Scope thiếu:** Proof và token đều hợp lệ, key binding khớp nhưng token chỉ có §orders.read§. Request hủy đơn có được phép không?

Không. Authentication DPoP thành công không tự cấp §orders.cancel§. Authorization vẫn phải từ chối.

**Tình huống L — Token opaque:** AS introspection trả §active=true§ nhưng không có thông tin §cnf.jkt§ hoặc key binding. Resource Server có thể xác nhận token DPoP-bound không?

Không, trừ khi có một metadata contract đáng tin khác cung cấp binding. §active=true§ không chứng minh token được ràng buộc với public key trong proof.

---

## Kết luận

**DPoP theo RFC 9449 ràng buộc access token với public key và yêu cầu Client ký proof cho từng request.** Proof phải gắn với method, URI, thời điểm, ID duy nhất và hash của access token; Resource Server còn phải so public-key thumbprint trong proof với §cnf.jkt§ hoặc metadata introspection. Cơ chế này giảm rủi ro access token bị đánh cắp riêng lẻ, nhưng không thay TLS, access-token validation, scope, tenant/resource authorization, key management hoặc bảo vệ XSS.

Về Spring Security, **6.5 là mốc có §DPoPAuthenticationProvider§ và DPoP Resource Server support**; tài liệu DPoP tiếp tục có ở 7.0. **Fluent §OAuth2ResourceServerConfigurer.dPoP(...)§ và §DPoPConfigurer§ có từ 7.1**, cho phép tùy chỉnh matcher/converter/handlers; API proof-verifier factory xuất hiện trong preview 7.2. Tài liệu/API đã đối chiếu là **Servlet Resource Server**; không coi Reactive JWT support là bằng chứng WebFlux đã có DPoP. Hãy kiểm thử đúng version, scheme §Authorization: DPoP§, key binding, §ath§, nonce/replay và đường chống downgrade trước khi tuyên bố API đã được sender-constrain.

## Tài liệu tham khảo

1. [RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449.html)
2. [Spring Security 6.5 — OAuth 2.0 DPoP-bound Access Tokens](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/dpop-tokens.html)
3. [Spring Security 6.5 — What's New](https://docs.spring.io/spring-security/reference/6.5/whats-new.html)
4. [Spring Security 6.5 API — DPoPAuthenticationProvider](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/server/resource/authentication/DPoPAuthenticationProvider.html)
5. [Spring Security 7.1 — OAuth 2.0 DPoP-bound Access Tokens](https://docs.spring.io/spring-security/reference/7.1/servlet/oauth2/resource-server/dpop-tokens.html)
6. [Spring Security 7.1 API — DPoPConfigurer](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/annotation/web/configurers/oauth2/server/resource/OAuth2ResourceServerConfigurer.DPoPConfigurer.html)
7. [Spring Authorization Server — Protocol Endpoints / DPoP-bound Access Tokens](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html)
