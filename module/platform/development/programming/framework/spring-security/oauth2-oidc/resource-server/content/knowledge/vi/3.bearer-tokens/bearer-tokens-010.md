# Bearer token không tự chứng minh bên gọi đang giữ một khóa riêng

Trong OAuth 2.0, **bearer token** là một thông tin chứng thực có tính chất *ai cầm được thì có thể sử dụng*. Resource Server có thể xác minh token là thật, do đúng Authorization Server cấp, còn hiệu lực và đủ scope, nhưng **những kiểm tra đó không tự chứng minh người gửi request đang sở hữu một khóa riêng (private key)**.

Đây là khác biệt quan trọng giữa:

- **Token hợp lệ:** Authorization Server đã cấp token và Resource Server xác thực được token đó.
- **Bên đang trình token là chủ thể/thiết bị được ràng buộc:** Bên gửi request cung cấp thêm bằng chứng mật mã hoặc chứng chỉ để chứng minh có quyền sử dụng token, ngoài việc biết chuỗi token.

Bài này giải thích tính chất của bearer token, vì sao chữ ký JWT và HTTPS không tự biến token thành bằng chứng sở hữu khóa riêng, và cách **sender-constrained access token** (token ràng buộc với bên sử dụng) giải quyết bài toán bằng **DPoP** hoặc **mutual TLS (mTLS)** trong ngữ cảnh Spring Security OAuth 2.0 Resource Server.

## 1. Bearer token xác nhận điều gì?

RFC 6750 mô tả bearer token là token mà **bất kỳ bên nào sở hữu token đều có thể dùng**. Bên nhận không yêu cầu phải chứng minh đang giữ một khóa mật mã được liên kết với token.

Giả sử API bảo vệ tài nguyên:

```http
GET /api/orders/42 HTTP/1.1
Host: api.example.test
Authorization: Bearer eyJhbGciOiJSUzI1NiIs...
Accept: application/json
```

Với Resource Server cấu hình xác thực JWT, Spring Security có thể:

1. Trích xuất chuỗi sau `Bearer` từ header `Authorization`.
2. Dùng `JwtDecoder` kiểm tra chữ ký JWT với khóa công khai đáng tin cậy.
3. Xác minh các claim: chẳng hạn `iss`, `exp`, `nbf` và `aud` nếu đã cấu hình validator.
4. Chuyển scope thành các authority như `SCOPE_orders.read`.
5. Đối chiếu authority với quy tắc của endpoint rồi cho phép hoặc từ chối truy cập.

**Không có bước nào trong luồng bearer thông thường buộc client ký request bằng khóa riêng của nó.** Client chỉ cần trình đúng chuỗi token.

### Một token bị sao chép sẽ ra sao?

```mermaid
sequenceDiagram
    participant AS as Authorization Server
    participant C as Client hợp lệ
    participant X as Bên lấy được token
    participant RS as Resource Server

    AS-->>C: Access token T
    C->>RS: Authorization: Bearer T
    RS-->>C: 200 nếu T hợp lệ và đủ quyền

    Note over X: X lấy được bản sao T từ nơi bị lộ
    X->>RS: Authorization: Bearer T
    Note over RS: Cùng một token T; không có bằng chứng về khóa riêng của C
    RS-->>X: Có thể trả 200 nếu T còn hợp lệ và đủ quyền
```

Sơ đồ minh họa **nguy cơ token replay**: người khác dùng lại token đã bị lấy cắp. Việc họ có truy cập thành công hay không còn tùy thời hạn, audience, scope, điều kiện mạng và chính sách API, nhưng **xác thực bearer thuần túy không phân biệt hai request chỉ khác người đang cầm token**.

> Điểm cốt lõi: **Biết token** là điều kiện để dùng bearer token. **Chứng minh sở hữu khóa riêng** là yêu cầu bổ sung của cơ chế proof-of-possession/sender constraint; hai việc không đồng nghĩa.

## 2. Phân biệt ba loại bằng chứng thường bị nhầm lẫn

| Bằng chứng | Nó chứng minh gì? | Nó **không** tự chứng minh gì? |
|---|---|---|
| **Chữ ký của Authorization Server trên JWT** | JWT chưa bị sửa và được ký bằng khóa của bên phát hành đã tin cậy. | Caller đang giữ private key riêng của client; caller chính là bên ban đầu được cấp token. |
| **TLS/HTTPS giữa client và Resource Server** | Kênh truyền được mã hóa, bảo vệ tính toàn vẹn trong kết nối TLS và thường xác thực danh tính server. | Mỗi bearer token nhận được đều bị ràng buộc với private key của caller; token không thể bị lấy từ log, bộ nhớ hoặc hệ thống khác. |
| **Bằng chứng sở hữu khóa của caller** | Caller chứng minh quyền sử dụng khóa gắn với token, nếu Resource Server xác minh đúng. | Token được cấp bởi issuer hợp lệ, đúng audience, đủ scope hoặc caller có quyền truy cập mọi bản ghi. Những điều đó vẫn phải kiểm tra riêng. |

Một JWT access token có chữ ký như sau:

```text
header.payload.signature
```

Phần `signature` thường được tạo bằng **khóa riêng của Authorization Server**, không phải khóa riêng của ứng dụng đang gọi API. Client có thể gửi JWT đó mà chưa từng giữ khóa ký của Authorization Server.

Hai công việc khác nhau:

- **Xác minh issuer:** Resource Server dùng public key của Authorization Server để biết token có thật và không bị thay đổi.
- **Xác minh sender:** Resource Server dùng bằng chứng khác để xác định caller có kiểm soát khóa/chứng chỉ mà token bị ràng buộc vào hay không.

Việc JWT mang `sub=user-123` chứng minh rằng **issuer đã đưa định danh này vào token có chữ ký hợp lệ**. Nó không chứng minh request hiện tại được người dùng `user-123` trực tiếp gửi, hoặc được gửi từ đúng thiết bị đã nhận token ban đầu.

## 3. Spring Security xử lý một bearer access token thông thường như thế nào?

Với ứng dụng Servlet dùng Spring Security OAuth 2.0 Resource Server, đường đi logic có thể mô tả như sau:

```mermaid
flowchart TD
    A["Request HTTP có Authorization: Bearer T"] --> B["BearerTokenAuthenticationFilter"]
    B --> C["BearerTokenResolver lấy T"]
    C --> D["AuthenticationManager và AuthenticationProvider"]
    D --> E{"Kiểu xác thực token"}
    E -- "JWT" --> F["JwtDecoder: chữ ký, issuer, thời gian, audience..."]
    E -- "Opaque" --> G["OpaqueTokenIntrospector: active và thuộc tính token"]
    F --> H{"Token được chấp nhận?"}
    G --> H
    H -- "Không" --> I["Authentication failure / thường 401"]
    H -- "Có" --> J["Tạo Authentication + GrantedAuthority"]
    J --> K["SecurityContext"]
    K --> L["AuthorizationFilter / method security"]
    L --> M{"Đủ quyền?"}
    M -- "Không" --> N["Thường 403"]
    M -- "Có" --> O["Controller / service"]
```

Các thành phần đáng chú ý:

**`BearerTokenAuthenticationFilter`** đọc bearer token rồi gửi yêu cầu xác thực đến `AuthenticationManager`. Sự tồn tại của header `Authorization: Bearer` **chưa** làm cho token đáng tin.

**`JwtAuthenticationProvider`/`JwtDecoder`** xử lý JWT; **`OpaqueTokenAuthenticationProvider`/`OpaqueTokenIntrospector`** xử lý opaque token. Cả hai có thể tạo `Authentication` được Spring Security dùng để phân quyền.

**`SecurityContext`** lưu kết quả xác thực cho request; **`AuthorizationFilter`** cùng method security xét caller có được phép gọi endpoint/nghiệp vụ không.

Luồng mặc định này **không thể hiện một phép kiểm tra riêng về private key của client**. Vì vậy việc cấu hình Resource Server JWT và các scope chưa đồng nghĩa với việc chống dùng lại bearer token đã bị đánh cắp.

### Ví dụ cấu hình cơ sở

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.test/realms/shop
          audiences:
            - orders-api
```

```java
@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/**").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .anyRequest().authenticated()
            )
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()))
            .build();
    }
}
```

Các import chính:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
```

Ứng dụng cần dependency Spring Security và OAuth 2.0 Resource Server phù hợp. Ví dụ dùng thuộc tính `audiences` theo những phiên bản Spring Boot hỗ trợ; nếu dùng bản khác hoặc tự tạo `JwtDecoder`, cần cài đặt validator tương đương.

Trong cấu hình này:

- `issuer-uri` giúp xác định issuer tin cậy và phục vụ giải mã/kiểm tra JWT.
- `audiences` giới hạn token dành cho `orders-api`.
- `hasAuthority("SCOPE_orders.read")` yêu cầu scope tương ứng đã được ánh xạ thành authority.
- **Không dòng nào xác minh một DPoP proof hoặc chứng chỉ mTLS bị ràng buộc vào token.**

Cấu hình CSRF, session, gateway và các filter khác phải được thiết kế theo kiến trúc ứng dụng; ví dụ chỉ tập trung vào luồng bearer.

## 4. Vì sao HTTPS, client authentication và PKCE vẫn chưa đủ để chứng minh caller giữ khóa riêng?

Một số cơ chế rất quan trọng cho OAuth 2.0, nhưng bảo vệ **giai đoạn hoặc mối quan hệ khác** với sender constraint của access token.

### HTTPS bảo vệ kết nối, không tự ràng buộc token với client

HTTPS chống nghe lén và sửa nội dung trên đường truyền, giả định xác thực TLS được thực hiện đúng. Tuy nhiên token vẫn có thể bị lộ qua:

- Log HTTP của client, reverse proxy, gateway hoặc ứng dụng.
- Công cụ debug, telemetry, bản ghi lỗi hoặc trace.
- Bộ nhớ, file cấu hình, bản sao lưu hoặc kho lưu trữ bị truy cập trái phép.
- Mã độc, XSS, extension độc hại hoặc bên thứ ba có quyền đọc token.
- Chuyển token nhầm sang một bên không đáng tin; không nên đưa access token vào URL.

Nếu có bản sao token, kẻ tấn công có thể mở **kết nối HTTPS riêng** đến API và gửi cùng một giá trị `Bearer`. TLS bảo vệ kết nối mới nhưng không chứng minh kẻ đó là client ban đầu.

### Xác thực client tại token endpoint không tự áp dụng tại Resource Server

Authorization Server có thể xác thực OAuth client bằng `client_secret_basic`, `private_key_jwt` hoặc mTLS khi cấp token. Bước đó giúp xác nhận **ai đang xin token** ở endpoint của Authorization Server.

Sau khi access token đã được cấp, Resource Server chỉ nhìn thấy token trong request. Trừ khi **token được sender-constrained** và Resource Server thực thi kiểm tra ràng buộc, việc OAuth client từng xác thực bằng private key tại token endpoint không bắt buộc caller hiện tại trình private key đó.

Đặc biệt, **client secret không phải private key bất đối xứng**, và việc client có secret cũng không làm access token trở thành proof-of-possession token.

### PKCE bảo vệ authorization code flow, không biến access token thành token ràng buộc khóa

PKCE dùng `code_verifier`/`code_challenge` để ngăn việc chặn và dùng lại authorization code trong quá trình đổi code lấy token. PKCE không buộc mỗi request API phải xuất trình một chữ ký mới từ khóa riêng. Một access token bearer thu được sau flow có PKCE vẫn có tính chất bearer nếu không có sender constraint riêng.

### OIDC ID token không chứng minh quyền sử dụng access token

ID token được cấp cho OIDC client để thể hiện sự kiện xác thực danh tính, thường có audience là client ID. Resource Server tiếp nhận **access token** và phải đánh giá mục đích, issuer, audience cùng quyền API. Việc client đã nhận ID token hợp lệ không phải bằng chứng mật mã rằng người gửi API request hiện tại giữ khóa riêng liên kết với access token.

## 5. Sender-constrained access token: cần hai điều kiện độc lập

Để giảm nguy cơ dùng lại token bị sao chép, OAuth 2.0 có thể áp dụng **sender constraint**: Authorization Server ràng buộc token với một khóa/chứng chỉ cụ thể, và Resource Server bắt caller chứng minh có quyền sử dụng khóa/chứng chỉ đó.

Ví dụ token được phát hành có thuộc tính xác nhận khóa:

```json
{
  "iss": "https://login.example.test/realms/shop",
  "sub": "user-123",
  "aud": "orders-api",
  "scope": "orders.read",
  "exp": 1900000000,
  "cnf": {
    "jkt": "<JWK-thumbprint-cua-client>"
  }
}
```

`cnf` là **confirmation claim**, mô tả thông tin khóa/chứng chỉ ràng buộc với token; nó **không phải bằng chứng rằng private key đã được trình trong request hiện tại**. Resource Server còn phải:

1. Xác thực access token và tin cậy nguồn chứa `cnf`.
2. Xác thực bằng chứng riêng của request: chữ ký DPoP hoặc chứng chỉ mTLS.
3. Đối chiếu khóa/chứng chỉ dùng cho bằng chứng với giá trị ràng buộc trong token.
4. Tiếp tục kiểm tra issuer, audience, thời hạn, scope và quyền truy cập tài nguyên.

```mermaid
flowchart TD
    AT["Access token hợp lệ, có ràng buộc khóa/chứng chỉ"] --> BOTH{"Cả hai điều kiện đều đúng?"}
    P["Bằng chứng trong request chứng tỏ caller giữ đúng khóa/chứng chỉ"] --> BOTH
    BOTH -- "Không" --> REJECT["Từ chối yêu cầu"]
    BOTH -- "Có" --> AUTHZ["Tiếp tục xét scope và quyền tài nguyên"]
```

Hai tiêu chuẩn sender constraint phổ biến:

- **DPoP (RFC 9449):** Client ký một JWT proof riêng cho HTTP request bằng private key của nó. Token được liên kết với **thumbprint của public JWK**.
- **OAuth 2.0 mutual-TLS certificate-bound access token (RFC 8705):** Token được liên kết với **chứng chỉ client**. Caller chứng minh sở hữu private key trong quá trình bắt tay mTLS.

Mức bảo vệ thực tế phụ thuộc vào cách tạo, lưu trữ khóa, xử lý bản sao và triển khai verifier. Sender constraint **giảm nguy cơ** từ việc đánh cắp token đơn lẻ; nó không bảo đảm chống mọi cuộc tấn công nếu private key cũng bị lộ hoặc thiết bị client đã bị chiếm quyền.

## 6. DPoP: một JWT proof được ký cho mỗi request

**Demonstrating Proof-of-Possession (DPoP)** theo RFC 9449 cho phép một OAuth client chứng minh đang kiểm soát private key tương ứng với public key đã được gắn vào access token. Client tạo một **DPoP proof JWT** rồi ký bằng private key của chính nó.

DPoP thường liên quan ba giai đoạn:

1. **Client có cặp khóa bất đối xứng.** Public key được khai báo trong header JWT proof; private key dùng để ký.
2. **Authorization Server ràng buộc access token với public key.** Token JWT thường có `cnf.jkt`; opaque token có thể trả ràng buộc tương ứng qua introspection.
3. **Mỗi lời gọi Resource Server mang proof riêng.** Resource Server kiểm tra chữ ký và các claim HTTP, chống dùng lại proof, rồi so khớp thumbprint public key với `cnf.jkt`.

### 6.1. Khi client xin access token

Client có thể gửi proof đến Authorization Server tại token endpoint. Proof được ký bằng private key và chứa `htm=POST`, `htu` là URL token endpoint, thời gian và mã nhận diện duy nhất. Ở bước này **chưa có access token để băm**, nên proof cấp token ban đầu thường **không có `ath`**.

```http
POST /oauth2/token HTTP/1.1
Host: login.example.test
Content-Type: application/x-www-form-urlencoded
DPoP: <signed-dpop-proof-for-token-endpoint>

grant_type=client_credentials&scope=orders.read
```

Đoạn request chỉ minh họa hình thức; cơ chế xác thực OAuth client và grant cụ thể phải phù hợp Authorization Server.

Khi chấp nhận yêu cầu, Authorization Server liên kết access token được cấp với JWK thumbprint, có thể trả:

```json
{
  "access_token": "<sender-constrained-access-token>",
  "token_type": "DPoP",
  "expires_in": 300,
  "scope": "orders.read"
}
```

Giá trị `token_type` của DPoP access token là **`DPoP`**. Client không nên tùy tiện đổi thành scheme `Bearer` khi sử dụng token ở Resource Server.

### 6.2. Client gọi API với access token và proof

```http
GET /api/orders/42 HTTP/1.1
Host: api.example.test
Authorization: DPoP <sender-constrained-access-token>
DPoP: <signed-dpop-proof-for-this-request>
Accept: application/json
```

Khác biệt với bearer thuần túy: request mang **hai dữ liệu** riêng. `Authorization: DPoP ...` trình access token; header `DPoP` trình JWT proof do client ký.

Header của DPoP proof JWT có thể trông như sau:

```json
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
```

Đây là **public JWK**; không được gửi tham số private key trong header. `alg` phải là thuật toán chữ ký bất đối xứng phù hợp chính sách verifier; không chấp nhận `none` hoặc chấp nhận thuật toán tùy ý chỉ vì token yêu cầu.

Payload minh họa:

```json
{
  "jti": "fe305a99-780d-4ab9-9142-54c1c1c2a8a7",
  "htm": "GET",
  "htu": "https://api.example.test/api/orders/42",
  "iat": 1794718800,
  "ath": "<base64url-SHA256-cua-access-token>"
}
```

Các giá trị ví dụ chỉ mô tả cấu trúc, không phải bằng chứng có thể dùng thực tế.

| Thành phần | Vai trò | Kiểm tra quan trọng |
|---|---|---|
| `typ: "dpop+jwt"` | Xác định loại JWT proof | Không nhầm proof này với ID token/access token JWT. |
| `alg` | Thuật toán chữ ký proof | Chỉ cho phép thuật toán bất đối xứng phù hợp chính sách. |
| `jwk` | Public key của client | Không nhận JWK private; dùng khóa này để xác minh chữ ký. |
| `jti` | Mã duy nhất của proof | Hạn chế việc dùng lại cùng proof trong cửa sổ thời gian được chấp nhận. |
| `htm` | HTTP method | Phải khớp method thực tế, ví dụ `GET`. |
| `htu` | HTTP URI đích | Phải khớp URI của request theo quy tắc chuẩn hóa của DPoP. |
| `iat` | Thời điểm tạo proof | Phải nằm trong cửa sổ thời gian được chấp nhận; giới hạn hiệu lực proof. |
| `ath` | Băm access token | Phải khớp access token đang được gửi kèm trong request. |
| `nonce` (nếu yêu cầu) | Giá trị server cấp | Gắn proof với nonce hợp lệ, giảm nguy cơ replay/precomputation. |

**`ath` không phải chữ ký của token.** Nó là giá trị:

```text
ath = base64url( SHA-256( ASCII(access_token) ) )
```

`ath` ràng buộc DPoP proof với **chuỗi access token cụ thể** đang được trình. Chữ ký của DPoP proof mới chứng minh client kiểm soát private key tương ứng với public key trong header.

**`cnf.jkt`** là JWK thumbprint, được tính theo RFC 7638 từ biểu diễn chuẩn của các thành phần public JWK cần thiết cho kiểu khóa rồi băm SHA-256 và mã hóa Base64URL. Không nên tự băm toàn bộ chuỗi JSON tùy ý vì thứ tự field và thuộc tính phụ có thể làm sai thumbprint.

### 6.3. Resource Server phải kiểm tra những gì?

Khi nhận `Authorization: DPoP <token>` và `DPoP: <proof>`, Resource Server phải kiểm tra **cả token lẫn proof**:

1. **Access token hợp lệ:** issuer, signature hoặc introspection, thời gian, audience, token type và các policy cần thiết.
2. **Token có ràng buộc DPoP:** lấy `cnf.jkt` từ token đã xác thực (hoặc dữ liệu introspection đáng tin cậy).
3. **Proof là DPoP JWT đúng chuẩn:** `typ`, `jwk` công khai, `alg` được chấp nhận và chữ ký hợp lệ bằng public key khai báo.
4. **Proof đúng request:** `htm` và `htu` khớp HTTP request đang được phục vụ; xử lý proxy và URI bên ngoài theo cấu hình tin cậy.
5. **Proof còn hiệu lực và không bị phát lại:** `iat` đủ mới; kiểm tra `jti` trong cửa sổ chống replay; xử lý `nonce` nếu server yêu cầu.
6. **Proof gắn với token:** `ath` khớp hash của access token đang nhận.
7. **Cùng chủ thể khóa:** JWK thumbprint của public key ký proof phải bằng `cnf.jkt` đã được gắn vào access token.
8. **Quyền API:** Sau khi xác thực thành công, tiếp tục xét scope, role, quyền đối tượng và tenant.

Chỉ xác minh chữ ký proof mà **không đối chiếu `cnf.jkt`** sẽ để bất kỳ ai tự tạo một cặp khóa khác và ký proof giả cho token đánh cắp. Chỉ so khớp `cnf.jkt` mà **không kiểm tra chữ ký proof** cũng không có giá trị chứng minh private key. Hai bước phải xuất hiện đồng thời.

### 6.4. Vì sao proof không dễ sao chép sang request khác?

Giả sử bên tấn công chỉ lấy được access token `T`:

- Họ không có private key đã tạo `cnf.jkt`, nên không ký được proof hợp lệ với cùng public key.
- Nếu tự tạo cặp khóa khác, thumbprint public key sẽ khác `cnf.jkt`.
- Nếu lấy một proof cũ, `jti`, `iat` và có thể `nonce` ngăn phát lại; `htm` và `htu` ràng buộc proof với method/URI; `ath` ràng buộc với `T`.

Các ràng buộc này có giới hạn:

- `htu` theo DPoP dựa trên URI nhưng **không tính query hoặc fragment**; DPoP cũng không trực tiếp ký HTTP request body. Vì vậy kiểm tra `jti`, `iat`/nonce và chính sách ứng dụng vẫn thiết yếu.
- Nếu private key **cũng bị đánh cắp**, bên tấn công có thể tạo proof mới; sender constraint không ngăn được trường hợp đó.
- Nếu proof bị phát lại đồng thời giữa các node và mỗi node lưu cache `jti` riêng thiếu đồng bộ, kiểm soát replay có thể chưa đủ chặt.
- Nếu malicious script có thể gọi hàm ký trong đúng client đang bị chiếm quyền, proof vẫn được tạo hợp lệ; bảo vệ khỏi token exfiltration không tương đương bảo vệ khỏi mọi mã độc.

### 6.5. Một yêu cầu DPoP đi qua gateway

```mermaid
sequenceDiagram
    participant C as Client (giữ private key)
    participant AS as Authorization Server
    participant API as Resource Server

    C->>AS: Token request + DPoP proof ký bằng key K
    AS->>AS: Kiểm tra proof, gắn cnf.jkt của K
    AS-->>C: Access token T, token_type=DPoP

    C->>C: Ký proof P mới với htm, htu, iat, jti, ath(T)
    C->>API: Authorization: DPoP T + DPoP: P
    API->>API: Xác minh T và kiểm tra cnf.jkt
    API->>API: Xác minh chữ ký P bằng public JWK
    API->>API: Kiểm tra htm/htu/iat/jti/ath/nonce nếu có
    API->>API: Khớp public key P với cnf.jkt của T
    API->>API: Phân quyền scope và tài nguyên
    API-->>C: 200 hoặc lỗi phù hợp
```

Lỗi DPoP có thể được phản ánh qua mã/chi tiết như `invalid_dpop_proof` hoặc yêu cầu nonce mới (`use_dpop_nonce`) theo RFC 9449. Không giả định mọi lỗi DPoP đều là `401 invalid_token`; mã lỗi và vị trí xử lý phụ thuộc token endpoint, Resource Server và triển khai.

## 7. mTLS certificate-bound access token: ràng buộc token với chứng chỉ client

**Mutual TLS (mTLS)** khác TLS thông thường ở chỗ ngoài server xác thực cho client, server còn yêu cầu **chứng chỉ của client** và xác minh client kiểm soát private key tương ứng trong quá trình TLS handshake.

RFC 8705 mô tả cách ràng buộc một OAuth 2.0 access token với chứng chỉ client. Authorization Server có thể đưa thumbprint chứng chỉ vào claim `cnf`:

```json
{
  "iss": "https://login.example.test/realms/shop",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "exp": 1900000000,
  "cnf": {
    "x5t#S256": "<base64url-SHA256-cua-chung-chi-client-DER>"
  }
}
```

`cnf["x5t#S256"]` là SHA-256 thumbprint của **toàn bộ chứng chỉ X.509 của client ở dạng DER**, mã hóa Base64URL; không phải hash của public key theo quy tắc JWK thumbprint.

Tại Resource Server, việc kiểm tra cần đảm bảo:

1. Client đã thiết lập mTLS với chứng chỉ được chấp nhận qua kết nối đến thành phần xác thực đáng tin cậy.
2. API nhận được chứng chỉ client đã được **xác minh trong TLS handshake**.
3. Thumbprint của chứng chỉ đó khớp `cnf["x5t#S256"]` trong access token đã xác thực.
4. Access token vẫn qua kiểm tra issuer, thời gian, audience, scope và quyền truy cập.

Request đến API có thể vẫn trông như bearer token thông thường:

```http
GET /api/orders/42 HTTP/1.1
Host: api.example.test
Authorization: Bearer <certificate-bound-access-token>
```

Điểm quyết định nằm ở **TLS client certificate** và bước đối chiếu với token; chỉ nhìn header `Bearer` không xác định được token có thực sự bị sender-constrained hay không.

### mTLS thường được dùng cho hệ thống nào?

mTLS phù hợp với các service, hệ thống backend, môi trường doanh nghiệp có hạ tầng chứng chỉ và khả năng quản lý vòng đời certificate. DPoP thường hữu ích hơn khi client cần proof ở tầng ứng dụng, chẳng hạn mobile hoặc public client có khả năng tạo và lưu private key phù hợp.

Việc chọn cách nào phụ thuộc vào mô hình client, topology mạng, khả năng của Authorization Server, Resource Server và gateway.

### Lưu ý khi có reverse proxy hoặc API gateway

Nếu TLS kết thúc ở gateway rồi request tiếp tục đến backend qua HTTP/mTLS khác, backend **không tự nhìn thấy** chứng chỉ thực tế của client ở kết nối TLS ban đầu.

Một thiết kế hợp lệ có thể:

- Để gateway xác thực mTLS, kiểm tra ràng buộc token và thực thi chính sách tại gateway; hoặc
- Để gateway chuyển **thông tin chứng chỉ đã được xác minh** đến backend bằng cơ chế nội bộ có bảo vệ, backend kiểm tra token binding dựa vào thông tin đó.

Không nên tin một header tùy ý như `X-Client-Cert` do client bên ngoài tự gửi. Nếu dùng header đại diện danh tính/chứng chỉ, gateway phải xóa header do bên ngoài cung cấp, tự thiết lập dữ liệu được tin cậy và giới hạn kết nối backend nhận header đó. Một backend đọc trực tiếp header chưa kiểm soát có thể bị giả mạo mTLS.

## 8. So sánh bearer thuần túy, DPoP và mTLS

| Tiêu chí | Bearer access token thông thường | DPoP-bound access token | mTLS certificate-bound access token |
|---|---|---|---|
| Cần biết chuỗi access token? | Có | Có | Có |
| Cần chứng minh giữ private key của client? | **Không** | **Có**, bằng chữ ký DPoP proof | **Có**, qua mTLS handshake |
| Token ràng buộc với gì? | Không có ràng buộc sender bắt buộc | JWK thumbprint (`cnf.jkt`) | Chứng chỉ thumbprint (`cnf["x5t#S256"]`) |
| Cách gửi thông thường | `Authorization: Bearer T` | `Authorization: DPoP T` cùng header `DPoP: P` | `Authorization: Bearer T` trên kết nối mTLS |
| Chống dùng lại token bị lấy cắp riêng lẻ | Hạn chế | Tốt hơn nếu private key vẫn an toàn và verifier kiểm tra đầy đủ | Tốt hơn nếu private key/certificate path an toàn và binding được kiểm tra |
| Ràng buộc proof với HTTP method/URI? | Không | Có qua `htm` và `htu` | Không theo dạng DPoP; gắn với kết nối TLS |
| Chống replay proof theo `jti`? | Không áp dụng | Phải xử lý theo chính sách replay/nonce | Không dùng DPoP `jti`; TLS thực hiện các bảo vệ kênh truyền |
| Phức tạp client | Thấp | Cần tạo/lưu key và ký proof mỗi request | Cần client certificate, key và hạ tầng TLS |
| Phức tạp Resource Server | Xác thực access token, phân quyền | Thêm DPoP proof, hash/thumbrprint, replay/nonce và binding | Thêm xác thực mTLS, lấy chứng chỉ và so khớp thumbprint |
| Nếu private key bị đánh cắp | Không liên quan đến kiểm tra token | Có thể tạo proof hợp lệ | Có thể giả mạo bên giữ certificate nếu các điều kiện khác cho phép |

**Tính chất sender-constrained chỉ có hiệu lực khi Authorization Server cấp token đúng dạng và Resource Server kiểm tra ràng buộc khi sử dụng.** Việc hỗ trợ một cơ chế chỉ ở phía client hoặc chỉ ở phía issuer là chưa đủ.

## 9. Spring Security Resource Server cần gì để kiểm tra possession?

Spring Security hỗ trợ xác thực bearer JWT và opaque token, nhưng **mặc định cài `oauth2ResourceServer().jwt()` không đồng nghĩa với việc đã triển khai đầy đủ DPoP/mTLS token binding**. Mức độ hỗ trợ cụ thể có thể phụ thuộc phiên bản Spring Security, các thư viện mở rộng và cách ứng dụng cấu hình.

Đối với **DPoP**, phía nhận cần một thành phần xử lý request có trách nhiệm:

- Nhận access token theo scheme `DPoP` và đọc header `DPoP`.
- Xác minh token qua JWT decoder/introspection đã tin cậy.
- Lấy `cnf.jkt` và xác minh proof theo RFC 9449: `typ`, chữ ký, thuật toán, `htu`, `htm`, `iat`, `jti`, `ath`, nonce nếu dùng.
- So khớp thumbprint JWK proof với khóa trong token.
- Chỉ tạo hoặc chấp nhận `Authentication` có quyền sau khi toàn bộ điều kiện cần đạt.

**Không nên chỉ thêm `DPoP` vào danh sách scheme mà bearer filter chấp nhận rồi bỏ qua header proof.** Làm vậy biến một access token dự định sender-constrained thành token dùng được như bearer, đi ngược mục tiêu bảo mật.

Đối với **mTLS-bound token**, phía nhận cần:

- Có client certificate **đã được TLS layer xác thực** hoặc nhận bằng đường tin cậy từ gateway.
- Lấy thumbprint chứng chỉ, đối chiếu với `cnf["x5t#S256"]` trong access token đã xác thực.
- Từ chối khi không có certificate, certificate không được xác minh hoặc thumbprint không trùng.
- Thực hiện tất cả kiểm tra JWT/introspection và phân quyền thông thường.

Tùy kiến trúc, bước sender constraint có thể được thực hiện trong Spring Security filter/provider tùy biến, ở lớp gateway đáng tin cậy, hoặc qua một thư viện hỗ trợ tiêu chuẩn đầy đủ. Nếu gateway xử lý, phải thiết kế rõ **trust boundary**, ngăn backend bị gọi vòng qua gateway và tránh tin metadata do request bên ngoài tự tạo.

### Pseudocode minh họa quyết định cho phép

Đây là **logic khái niệm**, không phải mã Java chạy được và không thay thế thư viện xác minh chuẩn:

```text
request -> extract_access_token_and_scheme()

token = validate_access_token(
    trusted_issuer,
    signature_or_introspection,
    expiry,
    audience
)

if token is DPoP-bound:
    require Authorization scheme == "DPoP"
    proof = require_and_parse_DPoP_header()
    verify_public_key_signature(proof)
    verify_typ_alg_htm_htu_iat_jti_ath_and_nonce(proof, request, token)
    require jwk_thumbprint(proof.public_jwk) == token.cnf.jkt

else if token is mTLS-certificate-bound:
    certificate = require_verified_tls_client_certificate()
    require certificate_sha256_thumbprint(certificate) ==
            token.cnf["x5t#S256"]

else:
    apply_policy_for_unbound_bearer_tokens()

authentication = map_claims_to_principal_and_authorities(token)
require_authorized(authentication, request, resource)
allow_request()
```

Phần `apply_policy_for_unbound_bearer_tokens()` phải có **chính sách rõ ràng**: endpoint nào chấp nhận bearer thông thường, endpoint nào bắt buộc sender-constrained. Không nên âm thầm cho token thiếu `cnf` đi qua endpoint được thiết kế yêu cầu proof-of-possession.

Đặc biệt, **Resource Server vẫn phải kiểm tra token đúng audience**. Sender proof hợp lệ không làm một token được cấp cho API khác trở thành hợp lệ tại API hiện tại.

## 10. Những lỗi thiết kế dễ tạo cảm giác an toàn sai

### Lỗi 1: “JWT có chữ ký số nên caller đã ký request”

**Sai về bên ký.** JWT access token thường được Authorization Server ký để chứng minh nguồn cấp token. Client chỉ chuyển chuỗi token; nó không dùng private key riêng để ký request khi dùng bearer thuần túy.

**Cách đúng:** Phân biệt chữ ký của issuer với chữ ký proof của caller. Nếu cần chứng minh possession, dùng cơ chế sender constraint phù hợp và xác thực tại Resource Server.

### Lỗi 2: “HTTPS đã mã hóa mọi thứ, token bị lộ cũng không dùng được”

HTTPS bảo vệ đường truyền, nhưng không ngăn rò rỉ qua endpoint, log hoặc bộ nhớ. Khi đã có chuỗi token, một bên khác có thể mở phiên HTTPS mới và gửi lại.

**Cách đúng:** Giảm khả năng rò rỉ token, giới hạn audience/scope/thời hạn và cân nhắc DPoP/mTLS với tài nguyên cần bảo vệ cao.

### Lỗi 3: “Có claim `cnf` là đủ”

`cnf` mô tả khóa/chứng chỉ đã liên kết; một bearer token chứa `cnf` nhưng server không kiểm tra chứng cứ gửi kèm vẫn có thể bị dùng lại.

**Cách đúng:** Kiểm tra proof thực tế, so khớp thumbprint và từ chối request thiếu/mismatch.

### Lỗi 4: “Bất kỳ DPoP proof hợp lệ nào cũng dùng được với token”

Một client có thể tạo cặp khóa của chính mình rồi ký một JWT có cấu trúc hợp lệ. Nếu không so sánh thumbprint proof với `cnf.jkt`, server không chứng minh đây là đúng khóa mà Authorization Server đã ràng buộc.

**Cách đúng:** Kiểm tra chữ ký proof **và** binding `cnf.jkt`, cùng `ath`, `htm`, `htu`, `iat`, `jti`.

### Lỗi 5: “DPoP proof được ký nên không thể bị replay”

Một proof có chữ ký hợp lệ vẫn có thể bị lấy và gửi lại nguyên văn nếu server không kiểm tra thời hạn, ID duy nhất hoặc nonce. `htu` không bao gồm query string và proof không ký body.

**Cách đúng:** Áp dụng cửa sổ thời gian ngắn, kiểm tra replay `jti` một cách nhất quán trong phạm vi hệ thống và hỗ trợ nonce khi cần; vẫn xử lý quyền nghiệp vụ bên trong request.

### Lỗi 6: “mTLS ở token endpoint tự làm mọi access token thành certificate-bound”

AS có thể dùng mTLS **chỉ để xác thực client** ở token endpoint. Muốn token bị ràng buộc certificate, AS phải phát hành thông tin binding phù hợp và Resource Server phải so khớp certificate của request với binding đó.

**Cách đúng:** Kiểm tra token metadata/claim hoặc introspection, xác định đúng loại token đã cấp và chính sách enforcement của API.

### Lỗi 7: “Gateway nói client có chứng chỉ thì backend cứ tin”

Một header chứng chỉ không có nguồn gốc tin cậy có thể bị giả mạo. Đặc biệt nguy hiểm nếu backend được gọi trực tiếp từ Internet hoặc proxy không lọc header từ phía ngoài.

**Cách đúng:** Chỉ tin dữ liệu đã được gateway xác thực và truyền qua kênh nội bộ bảo vệ, hoặc để backend trực tiếp xác thực mTLS.

## 11. Bài tập tình huống: token bị đánh cắp có dùng được không?

Giả sử `orders-api` yêu cầu `orders.read`; token còn hiệu lực, có audience đúng và không có lỗ hổng phân quyền nghiệp vụ khác.

| Tình huống | Bearer thông thường | DPoP-bound (enforce đúng) | mTLS-bound (enforce đúng) |
|---|---|---|---|
| Người dùng hợp lệ trình token và bằng chứng cần thiết | Có thể được phép | Có thể được phép | Có thể được phép |
| Kẻ tấn công chỉ có chuỗi token, không có khóa/chứng chỉ | **Có thể dùng lại** | **Bị từ chối** vì không tạo proof đúng khóa | **Bị từ chối** vì không trình được chứng chỉ bound |
| Kẻ tấn công có token và **private key** tương ứng | Không cần key | Có thể tạo proof mới, nên vẫn rủi ro | Có thể chứng minh possession nếu có certificate/key và đáp ứng các điều kiện TLS khác |
| Kẻ tấn công có token và **proof DPoP cũ**, không có private key | Bearer không dùng proof | Phải bị chặn khi replay detection/cửa sổ thời gian/nonce hoạt động đúng | Không liên quan đến mTLS |
| Token ký hợp lệ nhưng `aud` sai | Phải bị từ chối nếu validator đúng | Phải bị từ chối | Phải bị từ chối |
| Token thiếu scope/không có quyền xem đơn hàng 42 | Phải bị từ chối tại authorization | Phải bị từ chối tại authorization | Phải bị từ chối tại authorization |

Về bản chất, DPoP/mTLS không thay thế xác thực JWT, xác thực người dùng hoặc phân quyền. Chúng chỉ bổ sung **một yếu tố mật mã** vào việc sử dụng access token, nhằm hạn chế kẻ chỉ cầm chuỗi token có thể tự xưng là bên được quyền sử dụng.

### Ví dụ phân tích một access token JWT

Token A:

```json
{
  "iss": "https://login.example.test/realms/shop",
  "sub": "user-123",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "exp": 1900000000
}
```

Nếu ký hợp lệ và được Resource Server chấp nhận, đây **có thể vẫn là bearer access token** vì không có ràng buộc possession trong ví dụ. Các claim đúng chưa chứng minh client có private key.

Token B:

```json
{
  "iss": "https://login.example.test/realms/shop",
  "sub": "user-123",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "exp": 1900000000,
  "cnf": {
    "jkt": "<thumbprint-khoa-DPoP-cua-client>"
  }
}
```

Token B mang ràng buộc khóa DPoP. Nhưng nếu Resource Server chỉ kiểm tra chữ ký issuer rồi bỏ qua `cnf.jkt` và header `DPoP`, mục tiêu sender constraint **chưa được bảo đảm**. Chỉ khi Resource Server thực hiện đầy đủ phép kiểm tra mới có thể nói request đã chứng minh quyền sử dụng khóa bị ràng buộc vào token.

## 12. Chọn giải pháp phù hợp với mô hình đe dọa

Trước khi bổ sung sender constraint, hãy xác định cụ thể rủi ro cần giảm:

**Nếu mối lo chính là token lộ qua log hoặc hệ thống giám sát:** sender-constrained token giúp giảm nguy cơ dùng lại bản sao token một mình, nhưng vẫn cần ngừng ghi token vào log, ẩn credential trong telemetry và giới hạn quyền truy cập dữ liệu vận hành.

**Nếu ứng dụng là trình duyệt hoặc mobile:** DPoP có thể phù hợp vì proof ký ở tầng ứng dụng. Tuy nhiên khả năng bảo vệ private key phụ thuộc nền tảng, XSS, cách lưu trữ key và phạm vi mã có quyền gọi hàm ký. Một bên điều khiển được runtime client có thể yêu cầu client ký các request gây hại ngay cả khi không đọc được private key.

**Nếu hệ thống là service-to-service:** mTLS có thể tận dụng hạ tầng chứng chỉ và service mesh sẵn có. Phải phân biệt mTLS giữa các service với **certificate-bound access token**; có mTLS trong mạng không tự có nghĩa token đã được ràng buộc với certificate của caller.

**Nếu có API gateway:** cần thống nhất điểm thực thi kiểm tra, khả năng truy cập backend trực tiếp, nguồn dữ liệu tin cậy và cách kiểm tra method/URI bên ngoài đối với DPoP. Đổi HTTP host, scheme, path ở proxy có thể làm lệch `htu` nếu verifier nhìn nhận URL khác client.

**Nếu cần chặn token bị thu hồi trước hạn:** sender constraint không tự giải quyết revocation. JWT có thể được xác minh cục bộ nhưng không tự biết token đã bị vô hiệu hóa; opaque token introspection hoặc cơ chế trạng thái khác có thể cần thiết theo yêu cầu hệ thống.

**Nếu token bị lộ cùng private key:** cả DPoP và mTLS đều giảm hiệu quả. Cần phương án quản lý/lưu khóa an toàn, giới hạn thời hạn token, thu hồi và phát hiện bất thường.

Nên kết hợp các lớp bảo vệ: HTTPS, issuer/audience validators, scope tối thiểu, thời hạn ngắn, bảo vệ nơi lưu token, kiểm soát phát lại, quyền đối tượng và sender constraint khi mô hình đe dọa phù hợp.

## 13. Checklist tư duy khi kiểm tra một request có yêu cầu proof-of-possession

Khi một API tuyên bố “access token có proof-of-possession”, hãy lần lượt xác nhận:

1. **Có ràng buộc token thật không?** JWT chứa `cnf` được issuer ký, hoặc introspection từ AS đáng tin cậy trả về ràng buộc tương đương?
2. **Ràng buộc theo loại nào?** `cnf.jkt` cho DPoP hay `cnf["x5t#S256"]` cho certificate-bound token?
3. **Bên gọi đã trình bằng chứng chưa?** DPoP proof mới ký cho request, hoặc client certificate đã được xác minh qua mTLS?
4. **Bằng chứng đã được xác minh đúng chưa?** Chữ ký, thuật toán, proof claims, anti-replay/nonce hoặc TLS client certificate validation?
5. **Đúng khóa/chứng chỉ đã bind chưa?** So khớp thumbprint từ bằng chứng với `cnf` trong access token đã xác thực.
6. **Token được dùng đúng nơi chưa?** Issuer, audience, loại access token, thời gian và policy phù hợp?
7. **Được phép thao tác này không?** Scope/authority, ownership và tenant vẫn cần quyết định phân quyền độc lập.
8. **Trust boundary ở đâu?** Nếu gateway làm bước xác thực, backend có bị gọi trực tiếp hoặc bị giả mạo header về proof/certificate không?

Câu hỏi quyết định là: **Nếu người khác sao chép được duy nhất chuỗi access token, không có private key/chứng chỉ, họ có gọi API thành công được không?** Nếu câu trả lời vẫn là “có” đối với endpoint cần sender constraint, cấu hình hiện tại chưa bảo đảm chứng minh sở hữu khóa.

## 14. Tài liệu chuẩn để đọc tiếp

- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): định nghĩa bearer token và cách dùng trong HTTP.
- [RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449): DPoP proof, `htm`, `htu`, `ath`, `jti`, `cnf.jkt`, nonce và validation.
- [RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens](https://www.rfc-editor.org/rfc/rfc8705): phân biệt xác thực client bằng mTLS với access token ràng buộc chứng chỉ.
- [RFC 7800 — Proof-of-Possession Key Semantics for JSON Web Tokens](https://www.rfc-editor.org/rfc/rfc7800): ngữ nghĩa `cnf` và cách biểu đạt khóa xác nhận.
- [RFC 7638 — JSON Web Key (JWK) Thumbprint](https://www.rfc-editor.org/rfc/rfc7638): cách tính thumbprint ổn định cho public JWK.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700): định hướng bảo vệ access token, ràng buộc sender và giảm rủi ro OAuth.
- [Spring Security Reference — OAuth 2.0 Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/index.html): cơ chế xác thực bearer JWT/opaque token, filter chain và khả năng cấu hình theo từng phiên bản.

**Ghi nhớ:** Chữ ký JWT giúp API tin rằng token do đúng issuer phát hành; DPoP hoặc mTLS-bound token giúp API kiểm tra liệu **request hiện tại** có đến từ bên kiểm soát đúng khóa/chứng chỉ gắn với token hay không. Đó là hai bằng chứng khác nhau và đều không thay thế bước phân quyền tài nguyên.
