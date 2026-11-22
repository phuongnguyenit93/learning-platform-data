# JWK, JWKS và biểu diễn khóa công khai

Trong hệ thống **Spring Security OAuth 2.0/OIDC Resource Server**, Authorization Server phát hành access token dạng JWT được ký số; Resource Server cần biết **khóa công khai đáng tin cậy** để kiểm tra chữ ký trước khi sử dụng claim trong token. JOSE đưa ra một cách biểu diễn khóa bằng JSON, gọi là **JSON Web Key (JWK)**, và một cách công bố tập hợp các khóa, gọi là **JSON Web Key Set (JWKS)**. Đây là nền tảng giúp API xác minh JWT mà không cần chia sẻ private key ký token.

Ví dụ, Resource Server nhận:

~~~http
GET /api/orders/42 HTTP/1.1
Host: orders.example.com
Authorization: Bearer eyJhbGciOiJSUzI1NiIsImtpZCI6...
~~~

JWT có thể chứa JOSE header khai báo thuật toán **RS256** và định danh khóa **kid = shop-sign-2026-11**. Resource Server chọn public key tương ứng từ JWKS của issuer đáng tin cậy, kiểm tra chữ ký, rồi tiếp tục xác minh issuer, audience, thời hạn và quyền truy cập. **Việc có JWK/JWKS chỉ giải quyết phần quản lý và biểu diễn khóa; không tự hoàn thành việc xác thực và phân quyền token.**

## 1. Đặt JWK và JWKS đúng vị trí trong JOSE

**JOSE (JSON Object Signing and Encryption)** là tập chuẩn cho ký, mã hóa và biểu diễn các đối tượng bảo mật dựa trên JSON. Các khái niệm thường đi cùng nhau:

| Khái niệm | Vai trò | Cần phân biệt |
|---|---|---|
| **JWS (JSON Web Signature)** | Mô tả dữ liệu và chữ ký số/MAC để kiểm tra tính toàn vẹn và nguồn phát hành | Không tự mã hóa nội dung |
| **JWE (JSON Web Encryption)** | Mô tả dữ liệu được mã hóa và thông tin mã hóa | Mục đích khác JWS; JWT có thể dùng JWE |
| **JWT (JSON Web Token)** | Cách biểu diễn tập hợp claims thành token; có thể được bảo vệ bằng JWS/JWE | Claims và chữ ký là hai khía cạnh khác nhau |
| **JWK (JSON Web Key)** | Biểu diễn **một khóa** dưới dạng JSON | Có thể mô tả public key, private key hoặc symmetric key, tùy thành phần |
| **JWKS (JSON Web Key Set)** | Tập hợp **nhiều JWK** trong một JSON object | Chỉ là định dạng tập khóa, không phải token |
| **kid (Key ID)** | Gợi ý định danh khóa để chọn đúng JWK trong tập khóa | Không phải chữ ký, không phải nguồn tin cậy độc lập |

Một cách hình dung:

~~~mermaid
flowchart LR
    AS[Authorization Server] -->|Ký JWT bằng private key| T[JWT / JWS]
    AS -->|Công bố public JWK| S[JWKS endpoint]
    CL[Client] -->|Bearer JWT| RS[Spring Security Resource Server]
    T -.-> CL
    RS -->|Lấy public key theo issuer + kid| S
    RS -->|Kiểm chữ ký và các claims| V{Token hợp lệ?}
    V -->|Có| A[Kiểm quyền với API/tài nguyên]
    V -->|Không| D[401 Unauthorized]
~~~

**Public key dùng để xác minh chữ ký** có thể được chia sẻ công khai. **Private key dùng để ký** phải nằm ở bên phát hành token hoặc hệ thống quản lý khóa có kiểm soát (KMS/HSM); Resource Server thường không cần và không được nhận private key này.

JWK không phải định dạng duy nhất của khóa. Cùng một khóa RSA hoặc EC có thể được biểu diễn bằng JWK, PEM/DER hay một chứng chỉ X.509; cấu trúc đóng gói khác nhau nhưng thông tin toán học về khóa vẫn tương ứng.

## 2. Cấu trúc của một JWK

JWK là một JSON object. Những thành phần xuất hiện phụ thuộc vào **loại khóa (kty)** và mục đích sử dụng.

Ví dụ JWK **RSA public key**, với giá trị modulus được ghi dạng placeholder để minh họa cấu trúc:

~~~json
{
  "kty": "RSA",
  "kid": "shop-sign-2026-11",
  "use": "sig",
  "alg": "RS256",
  "n": "<base64url-encoded-RSA-modulus>",
  "e": "AQAB"
}
~~~

Ví dụ này **không phải một khóa hợp lệ để chạy thử**, vì trường **n** là placeholder. Trong dữ liệu thật, **n** và **e** phải là các giá trị Base64URL đúng theo chuẩn JWK. Giá trị **AQAB** thường biểu diễn public exponent RSA 65537.

| Thuộc tính | Ý nghĩa | Có bắt buộc cho mọi JWK không? |
|---|---|---|
| **kty** | Loại khóa: RSA, EC, OKP, oct... | Có |
| **kid** | Định danh khóa hỗ trợ lựa chọn/rotation | Không; rất hữu ích khi có nhiều khóa |
| **use** | Mục đích sử dụng công bố: **sig** (ký/xác minh) hoặc **enc** (mã hóa/giải mã) | Không |
| **key_ops** | Những thao tác khóa được dự kiến hỗ trợ, như **sign**, **verify**, **encrypt**, **decrypt** | Không |
| **alg** | Thuật toán dự kiến dùng với khóa, ví dụ RS256, PS256, ES256 | Không |
| **n**, **e** | RSA modulus và public exponent | Có đối với RSA public key |
| **crv**, **x**, **y** | Tên đường cong và tọa độ public point | Có đối với EC public key |
| **x5c** | Chuỗi chứng chỉ X.509 gắn với khóa | Không |
| **x5t**, **x5t#S256** | Fingerprint chứng chỉ X.509 | Không |

Không nên hiểu **use** và **key_ops** là quyền nghiệp vụ của người dùng. Chúng mô tả việc **khóa mật mã** dự kiến dùng để ký/xác minh hay mã hóa/giải mã. Chúng không tương đương scope hoặc role của OAuth.

### 2.1. Loại khóa RSA

JWK RSA công khai gồm:

- **kty = RSA**
- **n**: modulus, số nguyên dương được biểu diễn dưới dạng Base64URLUInt.
- **e**: public exponent, cũng là Base64URLUInt.

Ví dụ rút gọn:

~~~json
{
  "kty": "RSA",
  "n": "<modulus-RSA-dang-base64url>",
  "e": "AQAB",
  "kid": "rsa-01"
}
~~~

Để xác minh chữ ký **RS256**, Resource Server dùng cặp **n/e** để khôi phục RSA public key, rồi thực hiện thuật toán xác minh RSA với SHA-256 theo JWS.

**n/e không phải khóa bí mật.** Ngược lại, JWK RSA private key có thể chứa **d**, **p**, **q**, **dp**, **dq**, **qi** và các tham số private khác. Những giá trị đó **không được xuất bản trong JWKS công khai**.

### 2.2. Loại khóa EC

Một public key sử dụng Elliptic Curve thường có:

~~~json
{
  "kty": "EC",
  "crv": "P-256",
  "x": "<toa-do-x-base64url>",
  "y": "<toa-do-y-base64url>",
  "kid": "ec-01",
  "use": "sig",
  "alg": "ES256"
}
~~~

- **crv** chọn đường cong, chẳng hạn P-256, P-384, P-521.
- **x** và **y** là tọa độ điểm công khai trên đường cong.
- **d** (nếu có) là thành phần private key và không được công bố.
- **ES256** thường dùng ECDSA trên P-256 với SHA-256.

Các placeholder **x/y** chỉ minh họa tên trường, không phải tọa độ hợp lệ. Khi dùng EC, yêu cầu kích thước và cách mã hóa tọa độ phải đúng theo curve được lựa chọn. Hệ thống xác minh cũng phải kiểm tính hợp lệ của điểm công khai và các ràng buộc thuật toán thông qua thư viện mật mã đáng tin cậy.

### 2.3. Loại khóa OKP

JOSE cũng hỗ trợ các đường cong dạng **Octet Key Pair (OKP)**, ví dụ Ed25519:

~~~json
{
  "kty": "OKP",
  "crv": "Ed25519",
  "x": "<public-key-base64url>",
  "kid": "ed25519-01",
  "use": "sig",
  "alg": "EdDSA"
}
~~~

Với OKP, thành phần public chính là **x**; private key dùng **d**. Không có cặp tọa độ **x/y** như JWK loại EC. Khả năng dùng EdDSA phụ thuộc vào phiên bản Spring Security, Nimbus JOSE và nhà phát hành token; không suy luận thư viện hỗ trợ chỉ vì JWKS có một khóa OKP.

### 2.4. Loại khóa đối xứng **oct**

JWK có **kty = oct** đại diện cho khóa bí mật đối xứng, chẳng hạn khóa dùng với HMAC:

~~~json
{
  "kty": "oct",
  "k": "<secret-key-material-base64url>",
  "alg": "HS256"
}
~~~

Trường **k** ở đây **chứa bí mật**, không phải public key. Nếu đưa JWK này vào JWKS truy cập công khai, ai cũng có thể biết khóa HMAC và tạo MAC giả. Vì thế:

> **JWKS công khai dùng cho xác minh JWT ký bất đối xứng chỉ nên chứa public key. Tuyệt đối không công bố JWK chứa các private key parameters hoặc symmetric secret key.**

Phân biệt **JWK là cấu trúc tổng quát** với **public JWKS là tập khóa đã được lọc để phân phối an toàn**. Chuẩn không quy định mọi JWK đều công khai.

## 3. Các quy tắc mã hóa giá trị khóa

Nhiều lỗi tích hợp đến từ việc nhầm biểu diễn khóa với byte/raw text.

### 3.1. Base64URL khác Base64 thông thường

Base64URL thay đổi hai ký tự để an toàn trong URL:

| Base64 thông thường | Base64URL |
|---|---|
| **+** | **-** |
| **/** | **_** |
| Có thể có dấu padding **=** | Trong biểu diễn JWK/JWS thông dụng thường không có padding |

Đối với khóa RSA, thành phần **n/e** được biểu diễn là **Base64URLUInt**, tức giá trị số nguyên dương ở dạng octet big-endian rồi mã hóa Base64URL không padding theo quy tắc JOSE. Không thể thay chúng bằng chuỗi số thập phân, PEM nguyên vẹn hoặc base64 của ký tự hiển thị.

Đối với EC, **x/y** là octet strings cố định kích thước theo đường cong rồi mã hóa Base64URL. Kích thước tọa độ không thể thay tùy ý mà không làm hỏng khóa.

### 3.2. JWK, PEM và chứng chỉ X.509

| Biểu diễn | Nội dung | Dấu hiệu thường gặp |
|---|---|---|
| **JWK** | Các thành phần khóa trong JSON: kty, n/e, crv/x/y... | JSON object |
| **JWKS** | JSON object có mảng **keys** chứa các JWK | **{ "keys": [...] }** |
| **PEM public key** | Public key DER được bọc thành Base64 có dòng BEGIN/END | **-----BEGIN PUBLIC KEY-----** |
| **X.509 certificate** | Public key kèm subject, issuer, thời hạn, chữ ký chứng chỉ và metadata khác | **-----BEGIN CERTIFICATE-----** |

Một JWKS có thể đính kèm **x5c** để cung cấp chuỗi chứng chỉ, nhưng điều đó **không biến một JWK thành chứng chỉ X.509**. Trong JWK, giá trị **x5c** được mã hóa Base64 chuẩn của DER certificate, khác với Base64URL thường dùng cho **n/e/x/y**.

Nếu dùng chứng chỉ để xác thực issuer hoặc key, phải hiểu chính sách tin cậy và kiểm tra certificate chain phù hợp. **Sự hiện diện của x5c không tự chứng minh một khóa là đáng tin cậy.** Cùng một token có thể được xác minh bằng raw public key được cấu hình tin cậy mà không cần có x5c.

## 4. JWKS: một tập khóa dưới dạng JSON

**JWKS** là JSON object có thành phần **keys** là một mảng JWK. Ví dụ:

~~~json
{
  "keys": [
    {
      "kty": "RSA",
      "kid": "shop-sign-2026-10",
      "use": "sig",
      "alg": "RS256",
      "n": "<public-modulus-cu>",
      "e": "AQAB"
    },
    {
      "kty": "RSA",
      "kid": "shop-sign-2026-11",
      "use": "sig",
      "alg": "RS256",
      "n": "<public-modulus-moi>",
      "e": "AQAB"
    }
  ]
}
~~~

Các giá trị **n** ở đây là placeholder. Trong JWKS thật, cả hai JWK đều cần dữ liệu public key hợp lệ. Tập nhiều khóa giúp Authorization Server **luân chuyển khóa ký** mà vẫn cho phép Resource Server kiểm tra token cũ còn hiệu lực.

Một JWKS có thể chứa khóa với các loại/thuật toán khác nhau. Không phải khóa nào trong tập cũng phù hợp cho mọi token. Khi chọn khóa cần quan tâm tối thiểu tới **kid**, **kty**, thuật toán đã cho phép, **use/key_ops** nếu được khai báo, và chính sách tín nhiệm của issuer.

### 4.1. **kid** làm gì?

Ví dụ JWT có JOSE protected header:

~~~json
{
  "alg": "RS256",
  "typ": "JWT",
  "kid": "shop-sign-2026-11"
}
~~~

Khi nhận token, Resource Server có thể:

1. Xác định issuer và cấu hình tin cậy tương ứng.
2. Chọn **JWKS của issuer đã cấu hình tin cậy**, không dựa vào URL do token tùy ý đưa đến.
3. Tìm JWK có **kid** tương ứng và phù hợp với thuật toán xác minh được phép.
4. Xác minh chữ ký bằng public key từ JWK.
5. Kiểm tra các claim bắt buộc và chính sách cấp quyền.

**kid là khóa tra cứu, không phải bằng chứng bảo mật.** Bất kỳ ai cũng có thể đặt **kid** trong một JWT tự tạo; chỉ khi chữ ký xác minh thành công bằng khóa từ nguồn đã tin cậy thì token mới vượt qua bước xác thực mật mã.

JOSE không bắt buộc mọi JWS phải có **kid**. Nếu một JWKS có nhiều khóa, sử dụng **kid** duy nhất và ổn định cho từng khóa giúp lựa chọn và rotation hiệu quả. Không nên tái sử dụng cùng một **kid** cho vật liệu khóa khác trong cùng tập đang được phục vụ vì có thể dẫn đến chọn nhầm khóa hoặc tác động xấu từ cache.

### 4.2. **alg** trong JWK và JOSE header

- **alg** trong JWS protected header chỉ thuật toán mà token khai báo dùng để tạo chữ ký/MAC.
- **alg** trong JWK (nếu có) là thông tin về thuật toán dự kiến dùng với khóa.

Cả hai đều **không thay thế cấu hình thuật toán được phép của Resource Server**. API phải chủ động giới hạn thuật toán chấp nhận, ví dụ RS256, theo hợp đồng với Authorization Server; không tự động tin giá trị token tự khai.

Chẳng hạn, nếu API dự kiến chỉ nhận chữ ký RSA RS256, một token khai báo **HS256** không được phép khiến server diễn giải RSA public key thành shared secret để kiểm MAC. Đây là dạng **algorithm confusion**. Token khai báo **alg = none** cũng không được coi là access token ký hợp lệ nếu API yêu cầu JWT có chữ ký.

### 4.3. **use**, **key_ops**, **x5c**, thumbprint

- **use = sig** mô tả khóa dự kiến dùng cho ký/xác minh; **use = enc** dành cho mã hóa/giải mã.
- **key_ops** khai báo thao tác cụ thể, ví dụ **verify**. Nếu cả **use** và **key_ops** hiện diện, chúng phải nhất quán theo chuẩn.
- **x5c** là thông tin chứng chỉ tùy chọn liên quan tới khóa công khai.
- **x5t** và **x5t#S256** là thumbprint của chứng chỉ X.509; không đồng nghĩa với **kid**.
- **JWK Thumbprint** theo RFC 7638 là giá trị băm chuẩn hóa từ những thuộc tính public key được quy định; có thể được dùng làm nền tảng tạo định danh khóa, nhưng **kid không bắt buộc phải là thumbprint**.

Các thuộc tính hỗ trợ chọn và mô tả khóa. Chúng không làm thay đổi yêu cầu kiểm nguồn JWKS, thuật toán xác minh và tính hợp lệ của token.

## 5. JWKS endpoint và OIDC/OAuth metadata discovery

Một Authorization Server thường công bố public JWKS trên HTTPS, ví dụ:

~~~text
https://login.example.com/realms/shop/protocol/openid-connect/certs
~~~

Đây chỉ là ví dụ về kiểu URL; **không có quy tắc mọi issuer phải dùng đường dẫn /jwks.json hay /certs**. Tên endpoint chính xác cần lấy từ metadata mà Authorization Server cung cấp hoặc từ cấu hình đáng tin cậy.

Với OIDC, tài liệu **OpenID Provider Configuration** cung cấp trường **jwks_uri**:

~~~json
{
  "issuer": "https://login.example.com/realms/shop",
  "jwks_uri": "https://login.example.com/realms/shop/protocol/openid-connect/certs",
  "authorization_endpoint": "https://login.example.com/realms/shop/protocol/openid-connect/auth",
  "token_endpoint": "https://login.example.com/realms/shop/protocol/openid-connect/token"
}
~~~

JSON trên minh họa các trường liên quan, không phải bản metadata đầy đủ. OAuth 2.0 Authorization Server Metadata theo RFC 8414 cũng định nghĩa **jwks_uri**.

### 5.1. Chuỗi tin cậy

Resource Server cần được cấu hình **issuer tin cậy** (hoặc JWKS URI đã được quản trị tin cậy). Sau đó nó mới truy xuất metadata/JWKS qua HTTPS có kiểm tra chứng chỉ.

~~~mermaid
sequenceDiagram
    participant AS as Authorization Server
    participant C as OAuth Client
    participant API as Spring Resource Server
    AS->>AS: Giữ private signing key
    AS-->>C: Phát hành access token JWT đã ký
    C->>API: Authorization: Bearer JWT
    API->>AS: Tìm metadata/JWKS của issuer tin cậy qua HTTPS
    AS-->>API: Public JWK Set (có kid phù hợp)
    API->>API: Xác minh chữ ký JWT bằng public key
    API->>API: Kiểm iss, aud, exp, nbf và quyền
    API-->>C: 200 nếu đủ điều kiện; nếu không thì từ chối
~~~

Trong thực tế, các khóa thường được cache, vì vậy **không phải mỗi request đều gọi JWKS endpoint**. Lần tải đầu, cache miss, khi gặp **kid** mới và thời điểm làm mới phụ thuộc thư viện/cấu hình triển khai.

**Không dùng nguyên chuỗi iss chưa xác thực từ token để tự ý tải bất kỳ URL nào.** Trong hệ thống đa issuer, chỉ chọn giữa những issuer/JWKS đã đăng ký tin cậy; token từ một issuer khác không được quyền tự chọn nguồn khóa xác minh cho chính nó.

### 5.2. Các header JOSE có URL cần được xử lý thận trọng

JOSE header có thể chứa các tham số như **jku** (JWK Set URL), **jwk** (khóa nhúng), **x5u** (certificate URL). Chúng hữu ích trong một số giao thức nhưng cũng tạo điểm nguy hiểm nếu một JWT do bên ngoài cung cấp có thể ép Resource Server tải khóa từ địa chỉ tùy ý.

Ví dụ thiết kế **không an toàn**:

~~~text
Nhận JWT bất kỳ
  -> đọc jku của token
  -> tải khóa từ URL mà token chỉ định
  -> dùng khóa đó để công nhận token
~~~

Kẻ tấn công có thể tự ký token, công bố public key của họ và chỉ định **jku** trỏ tới khóa đó. Ngoài nguy cơ xác nhận token giả, việc tải URL không kiểm soát còn có thể tạo SSRF.

Cách đúng với Resource Server điển hình là lấy JWKS từ **issuer hoặc địa chỉ được cấu hình tin cậy**, hạn chế redirects/host và chứng chỉ, rồi đối chiếu **kid**. Không chấp nhận một khóa chỉ vì token đính kèm khóa đó.

## 6. Cấu hình Spring Security Resource Server với JWKS

Giả sử Orders API chỉ tin issuer:

~~~text
https://login.example.com/realms/shop
~~~

và access token hợp lệ phải có audience là **orders-api**.

### 6.1. Dùng **issuer-uri** để discovery

Với Spring Boot và Spring Security phiên bản có hỗ trợ cấu hình JWT Resource Server, khai báo:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.com/realms/shop
          audiences:
            - orders-api
~~~

Khi triển khai theo cơ chế mặc định tương ứng, Spring Security có thể lấy thông tin khóa xác minh từ metadata/JWKS của issuer và dùng public key để xác minh access token JWT. **issuer-uri** giúp thiết lập kiểm tra issuer; audience được xác định theo chính sách của API, không được suy ra từ JWK.

Cấu hình bảo vệ endpoint:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ApiSecurityConfig {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/public/**").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .anyRequest().authenticated()
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults())
            );

        return http.build();
    }
}
~~~

Ở đây **SCOPE_orders.read** là authority mà Spring Security có thể ánh xạ từ claim **scope/scp** của JWT access token. Việc xác minh JWT bằng JWKS không tự tạo scope hay role. Chỉ token đã vượt qua xác thực và các chính sách quyền phù hợp mới được phép truy cập.

**Lưu ý về phiên bản:** Các thuộc tính cấu hình và thuật toán được hỗ trợ có thể khác nhau giữa các phiên bản Spring Boot/Spring Security. Khi triển khai, đối chiếu phiên bản dự án với tài liệu tương ứng. Ví dụ ở đây trình bày mô hình sử dụng JWT Resource Server phổ biến.

### 6.2. Chỉ định trực tiếp JWKS URI

Trong môi trường đã biết chính xác endpoint, có thể cấu hình thêm **jwk-set-uri**:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.com/realms/shop
          jwk-set-uri: https://login.example.com/realms/shop/protocol/openid-connect/certs
          audiences:
            - orders-api
~~~

Cấu hình trực tiếp giúp Resource Server biết nơi tải public keys mà không phải phụ thuộc vào metadata discovery để xác định endpoint lúc khởi động. Việc **vẫn giữ issuer-uri** nhằm đảm bảo xác minh claim issuer. Nếu chỉ cấu hình JWKS URI mà không thiết lập xác thực issuer tương ứng, server có thể thiếu kiểm tra **iss**, tùy cách cấu hình JwtDecoder; đây là một lỗi bảo mật cần tránh.

**Không cấu hình JWKS URI từ request của client.** URI này thuộc chính sách trust của dịch vụ, phải được quản trị, truyền qua HTTPS và giới hạn vào nguồn xác minh hợp lệ.

### 6.3. Hạn chế thuật toán ký được chấp nhận

Với token sử dụng RS256, có thể chọn thuật toán xác minh một cách tường minh khi xây dựng **JwtDecoder** nếu cần tùy biến:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

@Configuration
class JwtDecoderConfig {

    @Bean
    JwtDecoder jwtDecoder() {
        NimbusJwtDecoder decoder = NimbusJwtDecoder
            .withJwkSetUri(
                "https://login.example.com/realms/shop/protocol/openid-connect/certs")
            .jwsAlgorithm(SignatureAlgorithm.RS256)
            .build();

        decoder.setJwtValidator(JwtValidators.createDefaultWithIssuer(
            "https://login.example.com/realms/shop"
        ));
        return decoder;
    }
}
~~~

Ví dụ trên cho thấy **quyết định chấp nhận RS256 là cấu hình của API**. Khi tự tạo JwtDecoder như vậy, cần **tự bảo đảm kiểm tra audience** cùng các yêu cầu khác của hệ thống; đừng dựa vào property tự động của Spring Boot nếu đã thay toàn bộ decoder. Với cấu hình đơn giản, dùng property của Spring Boot như mục 6.1 thường dễ duy trì hơn.

**Đừng bỏ kiểm tra iss/aud/exp/nbf chỉ vì xác minh chữ ký đã thành công.** Một token được ký đúng có thể dành cho dịch vụ khác hoặc đã hết hạn.

### 6.4. Resource Server không cần private key của issuer

Với RS256/ES256/EdDSA:

- Authorization Server giữ private key và ký token.
- JWKS công khai chứa public key.
- Resource Server tải public key, xác minh chữ ký mà không có khả năng ký token thay issuer.

Nếu dùng HS256, cả bên ký và bên xác minh phải có cùng secret HMAC. Phân phối secret này tới nhiều Resource Server làm tăng phạm vi bên có thể giả lập issuer; public JWKS không phù hợp để phân phối secret. Trong kiến trúc nhiều API, chữ ký bất đối xứng thường giúp tách biệt trách nhiệm và giảm số nơi giữ khóa ký.

## 7. Thực hành: theo dõi một JWT từ header tới public JWK

Giả sử Authorization Server phát hành JWT có JWS protected header:

~~~json
{
  "typ": "at+jwt",
  "alg": "RS256",
  "kid": "shop-sign-2026-11"
}
~~~

Và payload (rút gọn):

~~~json
{
  "iss": "https://login.example.com/realms/shop",
  "sub": "user-123",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "exp": 1893456000
}
~~~

Đây là các thành phần minh họa, không phải một JWT thật có thể xác minh độc lập. Trong JWS Compact Serialization, ba phần được ngăn bằng dấu chấm:

~~~text
BASE64URL(protected-header).BASE64URL(payload).BASE64URL(signature)
~~~

Quy trình xác minh:

1. API nhận **Bearer JWT** và giải mã cấu trúc JWS đủ để đọc header và claims; lúc này dữ liệu **chưa được tin cậy**.
2. API chọn issuer từ danh sách tin cậy đã cấu hình và lấy đúng JWKS của issuer đó.
3. API tìm khóa tương ứng **kid = shop-sign-2026-11**; đối chiếu **kty = RSA**, thuật toán RS256 được cho phép, mục đích sử dụng khóa và các ràng buộc cần thiết.
4. API dùng public key trong JWK để xác minh chữ ký của JWS trên phần header và payload đã được mã hóa tương ứng.
5. Nếu chữ ký thành công, API kiểm **iss**, **aud**, **exp**, **nbf** (nếu có), và chính sách claims cần thiết, bao gồm token type trong ngữ cảnh áp dụng.
6. API kiểm quyền **orders.read**, tenant, chủ sở hữu đơn hàng hoặc quy tắc khác trước khi trả dữ liệu.

Lưu ý: việc **giải mã Base64URL** để nhìn thấy claims **không phải xác thực**. Trước khi xác minh chữ ký, bất kỳ ai cũng có thể tự thay payload. Chỉ dùng dữ liệu chưa xác minh để hỗ trợ quá trình chọn chính sách tin cậy an toàn, không cấp quyền từ dữ liệu đó.

## 8. Rotation: khi Authorization Server đổi khóa ký

Khóa ký cần được thay thế định kỳ hoặc ngay khi nghi ngờ bị lộ. JWKS hỗ trợ chuyển tiếp giữa khóa cũ và khóa mới mà không buộc toàn bộ JWT cũ mất hiệu lực ngay lập tức.

Ví dụ:

| Thời điểm | Authorization Server | JWKS công khai | Tác động tới Resource Server |
|---|---|---|---|
| **T0** | Đang ký bằng khóa A | Public key A, kid A | Xác minh JWT hiện có bằng A |
| **T1** | Chuẩn bị đổi khóa | Public key A **và B** | Có thể tải/cache khóa B trước khi cần |
| **T2** | Bắt đầu ký token mới bằng B | Public key A **và B** | Xác minh token cũ bằng A, token mới bằng B |
| **T3** | Token ký bằng A hết hiệu lực và cache đã cập nhật | Chỉ còn public key B | Ngừng công bố A khi không còn token hợp lệ cần nó |

Quy trình tốt thường là **publish-before-use**: công bố public key mới trước khi dùng private key mới ký token để các Resource Server có thời gian nhận khóa. Thời gian overlap phải xét đến thời hạn access token, clock skew, cache JWKS, độ trễ làm mới khóa và cơ chế thu hồi.

### 8.1. Tại sao phải giữ khóa cũ một thời gian?

Một JWT đã ký bằng khóa A **không tự được ký lại** khi issuer chuyển sang khóa B. Để xác minh token A còn hạn, Resource Server vẫn cần public key A. Nếu xóa A khỏi JWKS quá sớm, các token đang hợp lệ theo **exp** có thể bị từ chối do không còn khóa xác minh.

Nếu private key A bị lộ, bài toán khác: issuer có thể cần **thu hồi hoặc loại bỏ A ngay** để giảm nguy cơ token giả, ngay cả khi một số token hợp lệ bị gián đoạn. JWKS rotation thông thường không phải cơ chế thu hồi token tức thì; cần chính sách phản ứng sự cố riêng.

### 8.2. Cache và trường hợp **kid** chưa có

Resource Server thường cache JWKS nhằm tránh request mạng cho mỗi token. Khi thấy **kid** mới, thư viện có thể thử làm mới khóa nhưng hành vi chi tiết phụ thuộc triển khai, thời hạn cache và giới hạn request.

Vấn đề vận hành thường gặp:

- Issuer đã bắt đầu ký bằng B nhưng JWKS vẫn chỉ có A.
- JWKS đã có B nhưng proxy/cache CDN vẫn trả bản cũ.
- **kid** bị tái sử dụng cho vật liệu khóa khác làm cache và key selector chọn sai.
- Nguồn JWKS không truy cập được; token có **kid** chưa nằm trong cache sẽ không thể xác minh.
- Resource Server nhận token từ issuer khác nhưng cố tìm **kid** trong JWKS hiện tại.

Cần theo dõi số lượng lỗi xác thực, trạng thái tải JWKS và thời điểm đổi khóa. Không xử lý lỗi mất kết nối JWKS bằng cách **bỏ qua xác minh chữ ký** hoặc tự cho phép token chưa xác minh. Nếu đã có public key cache hợp lệ, hành vi xác minh token phụ thuộc vào thiết kế decoder và cache; không mặc định rằng endpoint JWKS phải luôn online cho từng request.

## 9. Các lỗi bảo mật và vận hành thường gặp

### 9.1. Công bố private key trong JWKS

~~~json
{
  "keys": [
    {
      "kty": "RSA",
      "n": "<modulus>",
      "e": "AQAB",
      "d": "<PRIVATE-EXPONENT-DO-NOT-PUBLISH>"
    }
  ]
}
~~~

Trường **d** là vật liệu bí mật. Nếu JWKS công khai chứa private exponent hay các tham số private khác, kẻ tấn công có thể dùng khóa đó để ký JWT giả tương tự issuer. Khóa ký phải được thay thế khẩn cấp theo quy trình ứng phó phù hợp, chứ không chỉ xóa log hoặc sửa giao diện trả về.

### 9.2. Coi **kid** là thứ quyết định độ tin cậy

Một chuỗi **kid = admin** không tạo ra quyền admin và không chứng minh khóa đúng. **kid** chỉ giúp tìm khóa trong nguồn đã được tin cậy. Cũng không lấy **kid** để nối thành đường dẫn file hoặc SQL query thiếu kiểm soát.

### 9.3. Tin **jku** hoặc **jwk** do token bất kỳ tự khai

Một JWT không thể tự chọn public key để API công nhận chữ ký của chính nó. Nguồn khóa phải được cấu hình phía server hoặc được giải quyết theo chính sách tin cậy đã cố định, không phải theo URL tùy ý từ người gửi.

### 9.4. Bỏ kiểm tra issuer và audience

Một access token ký hợp lệ bởi cùng hệ thống danh tính vẫn có thể dành cho API khác. Resource Server phải kiểm **aud** tương ứng và issuer đúng theo hợp đồng; có JWK đúng không đồng nghĩa được phép truy cập mọi API.

### 9.5. Nhầm ID Token với access token

OIDC ID Token có thể được ký bằng khóa từ cùng JWKS của OpenID Provider. Điều đó **không có nghĩa** ID Token là access token dành cho Resource Server. Cần xác minh audience, token type/profile của hệ sinh thái và chính sách riêng của API.

### 9.6. Cho phép thuật toán do JWT tự chọn không hạn chế

**alg = none**, HS256 thay thế RS256, hoặc chuyển sang thuật toán yếu/không được phép có thể dẫn tới xác minh sai nếu thư viện/cấu hình quá lỏng. Resource Server cần giới hạn thuật toán và loại khóa tương thích.

### 9.7. Dùng JWKS qua HTTP hoặc tắt TLS verification

JWKS chỉ chứa public key, nhưng **tính toàn vẹn và nguồn gốc** của nó cực kỳ quan trọng. Nếu bị thay bằng public key của kẻ tấn công, Resource Server có nguy cơ xác minh những token do kẻ đó ký. Vì vậy endpoint JWKS cần HTTPS có xác minh certificate, không chỉ “đã là khóa công khai nên HTTP cũng được”.

### 9.8. Dùng một JWKS cho mọi tenant/issuer

Trong hệ thống đa tenant, mỗi issuer có thể dùng bộ khóa khác nhau; **kid** có thể trùng giữa các issuer. Việc chọn khóa và validator phải gắn với issuer tin cậy, không chỉ dựa vào **kid** toàn cục.

### 9.9. Nhầm **JWK use = sig** với quyền nghiệp vụ

**use = sig** cho biết public key được dự kiến dùng cho chữ ký. Nó không phải quyền **orders.read** hay **ROLE_ADMIN**. Scope, role, permissions và quyền trên từng tài nguyên vẫn là phần authorization của Resource Server.

## 10. Tình huống minh họa: API nào nên chấp nhận token?

Giả sử Orders API tin issuer **https://login.example.com/realms/shop**, audience **orders-api**, thuật toán **RS256** và quyền **orders.read**.

| Trường hợp | Kết quả dự kiến | Nguyên nhân |
|---|---|---|
| JWT ký RS256 bằng private key tương ứng JWK tin cậy, đúng issuer/audience, còn hạn, đủ quyền | Có thể được xử lý sau kiểm tra nghiệp vụ | Xác thực JWT và quyền phù hợp |
| JWT dùng cùng **kid** nhưng chữ ký không khớp public key | **401** | kid không thay thế signature |
| JWT ký bởi issuer hợp lệ nhưng audience là **payments-api** | **401** | Token không cấp cho Orders API |
| JWT có header **jku** trỏ tới public JWKS tự dựng của người gửi | **Từ chối nguồn khóa tùy ý** | jku không thuộc chính sách tin cậy |
| JWT ký đúng nhưng hết hạn | **401** | **exp** không hợp lệ |
| JWT ký đúng và đủ điều kiện token nhưng thiếu **orders.read** | **403** | Token hợp lệ nhưng chưa đủ quyền nghiệp vụ |
| JWT ký bằng khóa B, JWKS cache chỉ biết A | Không thể xác minh cho tới khi lấy được B | Cần phối hợp rotation và cache |
| JWKS công khai chứa **d** hoặc **k** secret | Sự cố rò rỉ khóa cần xử lý | Public endpoint không được phát tán bí mật |

Các mã trạng thái áp dụng cho thiết kế Bearer API thông thường. Một số hệ thống có thể trả 404 để che giấu sự tồn tại tài nguyên; điều này là chính sách authorization bổ sung.

## 11. Cách đọc một JWKS thực tế mà không lộ bí mật

Để khám phá cấu trúc public JWKS trong môi trường được phép, có thể gọi endpoint HTTPS đã biết (ví dụ giả định):

~~~bash
curl --fail --show-error --silent \
  https://login.example.com/realms/shop/protocol/openid-connect/certs
~~~

Nếu có **jq**, chỉ xem metadata khóa công khai:

~~~bash
curl --fail --show-error --silent \
  https://login.example.com/realms/shop/protocol/openid-connect/certs \
  | jq '.keys[] | {kid, kty, use, alg, crv}'
~~~

Kết quả minh họa:

~~~json
{
  "kid": "shop-sign-2026-11",
  "kty": "RSA",
  "use": "sig",
  "alg": "RS256",
  "crv": null
}
~~~

Không cần sao chép private key để debug Resource Server. Nếu thấy **d**, **p**, **q** hoặc **k** chứa symmetric secret trong JWKS công khai, đó là tín hiệu cấu hình sai nghiêm trọng. Việc public key có thể tải bằng curl **chưa chứng minh token hợp lệ**; JWT vẫn cần qua chữ ký và validator tương ứng tại API.

Nếu chạy chương trình kiểm thử token, chỉ dùng token giả lập hoặc token dành cho môi trường kiểm thử; không ghi access token thật vào tài liệu, issue tracker, log chung hoặc câu lệnh được chia sẻ.

## 12. Các câu hỏi cần trả lời khi thiết kế JWKS cho Resource Server

1. **Issuer nào được tin?** Mỗi API/tenant có cấu hình issuer và JWKS nguồn tương ứng rõ ràng hay không?
2. **Nguồn khóa được lấy ra sao?** Qua OIDC/OAuth metadata đã xác thực hay JWKS URI do quản trị cấu hình?
3. **Key set chứa những gì?** Chỉ public keys và các metadata phù hợp; có lọt private/symmetric secret không?
4. **Chữ ký được xác minh bằng thuật toán nào?** Có giới hạn RS256/ES256/thuật toán được phép đúng với hợp đồng token không?
5. **kid được quản lý ra sao?** Có chính sách gán kid rõ ràng, không tái sử dụng kid khi thay vật liệu khóa, hỗ trợ overlap rotation không?
6. **Sau khi xác minh chữ ký còn kiểm gì?** issuer, audience, thời hạn, loại token, scope/quyền và điều kiện tài nguyên đã được cấu hình chưa?
7. **Khi JWKS tạm thời mất kết nối thì sao?** Có cache, giám sát và quy trình rotation phù hợp; có tuyệt đối từ chối token không thể xác minh không?
8. **Khóa bị lộ thì ứng phó thế nào?** Có cơ chế xoay khóa khẩn cấp, giảm thời hạn token, thu hồi khi hỗ trợ và truyền thông vận hành không?

## Kết luận

**JWK** biểu diễn một khóa mật mã dưới dạng JSON; **JWKS** là tập hợp nhiều JWK giúp Authorization Server công bố các **public key** dùng để xác minh chữ ký JWT. Các trường như **kty**, **n/e**, **crv/x/y**, **kid**, **use** và **alg** giúp mô tả và chọn khóa, nhưng **không tự tạo lòng tin**.

Trong Spring Security Resource Server, phải lấy JWKS từ nguồn issuer được cấu hình tin cậy, xác minh JWS bằng khóa/thuật toán phù hợp và kiểm tra **iss**, **aud**, thời hạn cùng quyền nghiệp vụ trước khi trả dữ liệu. Việc quản lý JWKS đúng còn cần luân chuyển khóa có overlap, caching phù hợp và tuyệt đối không phát tán private key hoặc symmetric secret qua endpoint công khai.

### Tài liệu tham khảo

- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517)
- [RFC 7518 — JSON Web Algorithms (JWA)](https://www.rfc-editor.org/rfc/rfc7518)
- [RFC 7515 — JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515)
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519)
- [RFC 7638 — JSON Web Key (JWK) Thumbprint](https://www.rfc-editor.org/rfc/rfc7638)
- [RFC 8414 — OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414)
- [OpenID Connect Discovery 1.0 — OpenID Provider Metadata](https://openid.net/specs/openid-connect-discovery-1_0.html)
- [Spring Security Reference — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
