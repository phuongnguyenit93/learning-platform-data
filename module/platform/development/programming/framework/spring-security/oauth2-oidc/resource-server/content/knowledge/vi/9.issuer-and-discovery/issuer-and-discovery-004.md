# Discovery tìm jwks_uri như thế nào

Trong một hệ thống **Spring Security OAuth 2.0/OIDC Resource Server**, API thường không giữ khóa bí mật mà Authorization Server dùng để ký JWT. API cần biết **khóa công khai** tương ứng để xác minh chữ ký access token. Nếu chỉ được cấu hình một địa chỉ **issuer**, Resource Server lấy được địa chỉ tập khóa bằng cách nào?

Câu trả lời là **metadata discovery**: từ **issuer URI** đáng tin cậy, Spring Security truy cập một endpoint metadata chuẩn, đọc trường **jwks_uri** trong JSON trả về, rồi dùng URL đó để lấy **JWKS (JSON Web Key Set)** chứa các public key. Sau đó, khi có Bearer JWT, decoder chọn khóa phù hợp, kiểm chữ ký và tiếp tục xác thực claims.

Điểm quan trọng là **discovery không đồng nghĩa với xác thực JWT**. Discovery chỉ xác định metadata và nơi lấy khóa; Resource Server vẫn cần bảo vệ nguồn metadata, xác minh chữ ký, issuer, audience, thời hạn và chính sách phân quyền.

## 1. Bốn địa chỉ hoặc đối tượng không được nhầm lẫn

Giả sử một tổ chức dùng OpenID Provider (OP)/Authorization Server với issuer:

~~~text
https://login.example.com/realms/shop
~~~

Các thành phần trong chuỗi xác thực:

| Thành phần | Ví dụ | Vai trò |
|---|---|---|
| **Issuer URI** | https://login.example.com/realms/shop | Định danh bên phát hành; giá trị dự kiến khớp với claim **iss** của JWT |
| **Metadata endpoint** | https://login.example.com/realms/shop/.well-known/openid-configuration | Trả JSON mô tả issuer, endpoints và nơi lấy public keys |
| **jwks_uri** | https://login.example.com/realms/shop/protocol/openid-connect/certs | Giá trị trong metadata chỉ đến tập khóa JWKS |
| **JWKS document** | JSON với mảng **keys** tải tại jwks_uri | Chứa các JWK public phù hợp để xác minh token được ký bất đối xứng |

Trong hệ thống khác, **jwks_uri** có thể là **https://keys.example.com/jwks.json** hoặc một đường dẫn tùy nhà cung cấp. Không có quy tắc nó luôn phải kết thúc bằng **/certs**, **/keys** hay **/.well-known/jwks.json**.

Một minh họa:

~~~mermaid
flowchart TD
    C[Resource Server cấu hình issuer-uri] --> M[GET metadata endpoint qua HTTPS]
    M --> J[Đọc issuer và jwks_uri trong JSON]
    J --> K[GET jwks_uri qua HTTPS]
    K --> S[JWKS JSON: keys array]
    S --> P[Chọn public JWK phù hợp với JWT kid và alg]
    P --> V[JwtDecoder xác minh signature]
    V --> Q[Kiểm iss, aud, exp, nbf...]
    Q --> A[Kiểm scope, role và quyền trên tài nguyên]
~~~

**Issuer URI không phải jwks_uri.** **Metadata JSON không phải JWKS JSON.** **jwks_uri là một chuỗi URL**, không phải danh sách khóa.

## 2. Vì sao tồn tại discovery?

Nếu không có discovery, mỗi Resource Server phải biết trước:

- Authorization Server phát hành access token là ai.
- Endpoint công bố public keys nằm ở đâu.
- Có thể sử dụng thuật toán/loại khóa nào.
- Khi nhà cung cấp thay cấu trúc endpoint hoặc luân chuyển khóa, phải cập nhật cấu hình ra sao.

Với discovery, ứng dụng cấu hình issuer tin cậy, còn Authorization Server công bố metadata theo một giao thức thống nhất. Spring Security có thể đọc metadata để tìm **jwks_uri**, rồi tải public keys phục vụ chữ ký JWT.

Tuy nhiên, discovery chỉ giúp **khám phá endpoint theo hợp đồng**. Nó không có nghĩa API được phép tự tin bất kỳ issuer do người gửi token khai báo, cũng không khiến JWT của issuer đó tự động có đủ quyền đọc mọi tài nguyên.

### 2.1. Phân biệt issuer discovery và metadata discovery

Trong đặc tả OIDC có thể gặp hai khái niệm:

1. **Issuer discovery**: tìm issuer từ một định danh người dùng hoặc cơ chế bên ngoài, chẳng hạn WebFinger trong một số luồng OpenID Connect.
2. **Provider configuration discovery**: khi **đã biết issuer**, tìm tài liệu metadata của issuer ở một URL chuẩn.

Đối với Spring Security Resource Server thông thường:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.com/realms/shop
~~~

Ứng dụng **đã biết issuer** từ cấu hình. Spring Security thực hiện **metadata discovery** để lấy khóa; không cần nhận địa chỉ email người dùng rồi gọi WebFinger trước mỗi request.

## 3. Những URL metadata có thể được thử từ issuer

Hai đặc tả rất quan trọng là:

- **OpenID Connect Discovery 1.0** dành cho OpenID Provider metadata.
- **RFC 8414 — OAuth 2.0 Authorization Server Metadata** dành cho metadata của Authorization Server nói chung.

Cùng một issuer có thể xuất hiện với **những vị trí .well-known khác nhau** do cách xây dựng đường dẫn theo từng đặc tả.

Giả sử issuer có phần path:

~~~text
https://login.example.com/realms/shop
~~~

Các URL tương ứng mà tài liệu Spring Security JWT Resource Server mô tả hỗ trợ gồm:

| Kiểu metadata | URL ví dụ | Cách ghép |
|---|---|---|
| **OIDC Provider Configuration** | https://login.example.com/realms/shop/.well-known/openid-configuration | Nối **/.well-known/openid-configuration** vào cuối issuer |
| **OAuth metadata dùng hậu tố openid-configuration** | https://login.example.com/.well-known/openid-configuration/realms/shop | Chèn **/.well-known/openid-configuration** giữa host và issuer path |
| **RFC 8414 OAuth Authorization Server Metadata** | https://login.example.com/.well-known/oauth-authorization-server/realms/shop | Chèn **/.well-known/oauth-authorization-server** giữa host và issuer path |

Nếu issuer **không có path**, chẳng hạn **https://login.example.com**, hai kiểu ghép OpenID ở trên thường cùng dẫn đến:

~~~text
https://login.example.com/.well-known/openid-configuration
~~~

Điểm khác biệt xuất hiện rõ nhất khi issuer có path như **/realms/shop**. Không thể lấy hướng dẫn “nối .well-known vào host” rồi tự cho rằng mọi provider và framework đều dùng cùng một đường dẫn.

### 3.1. Quy tắc OIDC Discovery

Theo **OpenID Connect Discovery 1.0**, provider configuration nằm tại:

~~~text
{issuer-không-có-dấu-slash-cuối}/.well-known/openid-configuration
~~~

Ví dụ:

~~~text
Issuer:
https://id.example.org/tenant-a

OIDC discovery:
https://id.example.org/tenant-a/.well-known/openid-configuration
~~~

Khi issuer chứa path, OIDC nối phần **/.well-known/openid-configuration** sau path issuer. Đặc tả OIDC yêu cầu metadata được trả bằng JSON và có các giá trị cần thiết như **issuer** và **jwks_uri**.

### 3.2. Quy tắc RFC 8414

RFC 8414 định nghĩa đường dẫn metadata OAuth bằng cách **chèn** phần well-known vào giữa host và path issuer.

~~~text
Issuer:
https://id.example.org/tenant-a

OAuth metadata:
https://id.example.org/.well-known/oauth-authorization-server/tenant-a
~~~

RFC 8414 cũng cho phép các ứng dụng OAuth sử dụng well-known suffix thích hợp khác, trong đó có **openid-configuration**; khi dùng quy tắc chèn theo RFC 8414, URL là:

~~~text
https://id.example.org/.well-known/openid-configuration/tenant-a
~~~

**Không ghép URI tùy ý bằng string replacement trong ứng dụng nếu framework đã hỗ trợ discovery.** Với URL chứa host, port, path và escaping phức tạp, hãy để thư viện đã triển khai chuẩn đảm nhiệm. Những URL trong bảng giải thích cách hình thành endpoint chứ không phải mệnh lệnh phải gọi tất cả endpoint thủ công.

### 3.3. Spring Security lựa chọn endpoint thế nào?

Tài liệu Spring Security Servlet JWT Resource Server cho biết khi cấu hình **issuer-uri**, Authorization Server cần hỗ trợ ít nhất một trong các dạng metadata endpoint tương ứng ở trên.

Spring Security có cơ chế discovery được xác định trước để tìm metadata phù hợp. **Không nên giả định phiên bản nào cũng thử mọi URL theo cùng thứ tự hoặc luôn fallback sau mọi loại lỗi**: lỗi TLS, lỗi JSON, issuer mismatch hay phản hồi không hợp lệ có thể dẫn tới thất bại thay vì thử endpoint tiếp theo. Nếu nhà cung cấp có đặc điểm riêng, hãy xác nhận hành vi của đúng phiên bản Spring Security được sử dụng.

Đừng tự dựng URL JWKS chỉ vì đoán theo tên miền của issuer. **Endpoint metadata** mới là nơi công bố đường dẫn **jwks_uri**.

## 4. Spring Security đọc metadata JSON ra sao?

Với issuer ví dụ:

~~~text
https://login.example.com/realms/shop
~~~

Resource Server có thể truy cập endpoint OIDC như sau:

~~~http
GET /realms/shop/.well-known/openid-configuration HTTP/1.1
Host: login.example.com
Accept: application/json
~~~

Phản hồi minh họa:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
~~~

~~~json
{
  "issuer": "https://login.example.com/realms/shop",
  "authorization_endpoint": "https://login.example.com/realms/shop/protocol/openid-connect/auth",
  "token_endpoint": "https://login.example.com/realms/shop/protocol/openid-connect/token",
  "jwks_uri": "https://login.example.com/realms/shop/protocol/openid-connect/certs",
  "id_token_signing_alg_values_supported": ["RS256", "ES256"]
}
~~~

Đây là JSON **rút gọn để minh họa**, không phải một tài liệu OIDC metadata đầy đủ đáp ứng mọi trường bắt buộc của một OP.

Phân tích các trường:

| Trường | Ý nghĩa với Resource Server |
|---|---|
| **issuer** | Cần khớp chính xác issuer đã được cấu hình tin cậy |
| **jwks_uri** | Địa chỉ HTTPS để lấy tập public keys |
| **authorization_endpoint** | Endpoint authorization của hệ OAuth/OIDC, thường phục vụ OAuth Client |
| **token_endpoint** | Endpoint cấp access token cho client, không phải JWKS |
| **id_token_signing_alg_values_supported** | Thuật toán dùng để ký **ID Token** do OP quảng bá; không tự quy định toàn bộ thuật toán access token mà API phải tin |

**Tên trường chuẩn là jwks_uri, không phải jwks_url.** Một số đoạn diễn giải trong tài liệu hoặc bài blog có thể dùng cụm **jwks_url** như cách gọi chung, nhưng tên metadata JSON trong **OIDC Discovery** và **RFC 8414** là **jwks_uri**. Khi tạo response metadata theo chuẩn, phải dùng đúng tên trường.

### 4.1. Có phải jwks_uri luôn bắt buộc?

Có khác biệt giữa hai tài liệu:

- **OIDC Provider Metadata:** **jwks_uri** là trường **REQUIRED** trong OIDC Discovery; URL dùng HTTPS và JWKS công khai không được chứa khóa private/symmetric.
- **RFC 8414 OAuth Authorization Server Metadata:** **jwks_uri** được định nghĩa là **OPTIONAL** theo chuẩn metadata OAuth chung.

Tuy nhiên, **Resource Server cần xác minh JWT bằng public keys qua JWKS** thì phải có đủ thông tin lấy khóa: metadata có **jwks_uri** dùng được hoặc URL/key tin cậy được cấu hình theo phương án khác. Một tài liệu RFC 8414 hợp lệ nhưng không công bố jwks_uri sẽ không đủ để thiết lập cách xác minh JWT qua JWKS chỉ từ discovery.

**Không dùng authorization_endpoint hoặc token_endpoint để đoán JWKS.** Đây là các endpoint có vai trò riêng.

### 4.2. Kiểm issuer ngay trong metadata

Theo OIDC Discovery và RFC 8414, trường **issuer** trong metadata phải tương ứng chính xác issuer đã dùng để hình thành metadata URL.

Ví dụ:

~~~text
issuer-uri cấu hình:  https://login.example.com/realms/shop
metadata issuer:      https://login.example.com/realms/other
~~~

Trường hợp này là **issuer mismatch**. Không nên lấy jwks_uri từ response sai issuer làm nguồn khóa tin cậy.

Cần lưu ý khác biệt về:

- Hostname hoặc port.
- Scheme **https** so với **http**.
- Path hoặc tenant/realm.
- Dấu slash cuối đường dẫn nếu issuer/provider trả khác nhau.
- Các biến thể string encoding hoặc normalization mà giao thức không cho phép tự động thay đổi.

Đừng tự âm thầm bỏ slash, đổi host hay chỉnh issuer trong JWT cho “khớp” nếu chưa kiểm tra hợp đồng của OP. Issuer là một định danh bảo mật, không phải chỉ là URL thuận tiện để kết nối.

## 5. Bước tiếp theo: jwks_uri trả về gì?

Sau khi đọc metadata và lấy được **jwks_uri**, Resource Server truy xuất JWKS:

~~~http
GET /realms/shop/protocol/openid-connect/certs HTTP/1.1
Host: login.example.com
Accept: application/json
~~~

Ví dụ body:

~~~json
{
  "keys": [
    {
      "kty": "RSA",
      "kid": "shop-key-2026-10",
      "use": "sig",
      "alg": "RS256",
      "n": "<public-modulus-base64url-old>",
      "e": "AQAB"
    },
    {
      "kty": "RSA",
      "kid": "shop-key-2026-11",
      "use": "sig",
      "alg": "RS256",
      "n": "<public-modulus-base64url-new>",
      "e": "AQAB"
    }
  ]
}
~~~

Các giá trị **n** có dấu ngoặc nhọn trong ví dụ chỉ là placeholder minh họa; một JWKS thật phải chứa giá trị modulus hợp lệ theo JWK.

Những trường cần hiểu:

- **keys**: mảng JWK trong tài liệu JWKS.
- **kty = RSA**: loại khóa RSA.
- **kid**: key identifier, dùng để chọn khóa ký đúng khi có nhiều public key.
- **use = sig**: khóa dùng cho chữ ký/xác minh.
- **alg = RS256**: thuật toán dự kiến dùng với khóa; không thay thế danh sách thuật toán được API cho phép.
- **n/e**: thành phần RSA public key, mã hóa theo Base64URLUInt.

**Không được đưa private key, RSA d/p/q hoặc symmetric secret k vào JWKS công khai.** Public key cho phép bên nhận kiểm chữ ký, còn private key chỉ có ở phía issuer hoặc hệ thống quản lý khóa được kiểm soát.

### 5.1. Tìm key bằng kid

Giả sử JOSE header của một access token chứa:

~~~json
{
  "typ": "at+jwt",
  "alg": "RS256",
  "kid": "shop-key-2026-11"
}
~~~

Sau khi xác định issuer và nguồn JWKS đáng tin cậy, decoder dùng **kid** để tìm key có tên tương ứng, đồng thời kiểm tính tương thích về loại khóa, thuật toán và mục đích sử dụng.

**kid chỉ giúp tìm khóa.** Kẻ tấn công cũng có thể tự tạo JOSE header chứa kid đó, nhưng sẽ không tạo được chữ ký hợp lệ nếu không có private key. Do đó kiểm chữ ký sau khi chọn khóa mới là bước xác nhận mật mã quan trọng.

Một JWKS có thể chứa nhiều khóa phục vụ rotation; không phải mọi key đều phải được thử vô điều kiện cho mọi JWT.

## 6. Chuỗi xử lý từ issuer đến việc nhận JWT

~~~mermaid
sequenceDiagram
    participant AS as Authorization Server / OP
    participant API as Spring Resource Server
    participant C as OAuth Client

    Note over API: Đã cấu hình issuer-uri tin cậy
    API->>AS: GET .well-known metadata qua HTTPS
    AS-->>API: 200 JSON với issuer và jwks_uri
    API->>API: Kiểm metadata, lấy jwks_uri
    API->>AS: GET jwks_uri qua HTTPS
    AS-->>API: JWKS JSON chứa public keys
    API->>API: Cache public keys thích hợp
    AS-->>C: Cấp access token JWT được ký
    C->>API: Authorization: Bearer JWT
    API->>API: Chọn JWK bằng kid, kiểm chữ ký
    API->>API: Kiểm iss, aud, exp, nbf và quyền
    API-->>C: 200 nếu đủ điều kiện hoặc từ chối
~~~

Sơ đồ trình bày **quan hệ logic**. Trong triển khai thật, bước metadata discovery có thể diễn ra tại thời điểm khởi tạo decoder hoặc **được hoãn đến request JWT đầu tiên**, còn JWKS có thể tải/cache theo nhu cầu. Thứ tự mạng cụ thể phụ thuộc vào phiên bản Spring Security và cách tạo JwtDecoder.

Điều không đổi là: **issuer được cấu hình tin cậy → metadata có jwks_uri → JWKS có public key → JwtDecoder xác minh JWT → kiểm claims và quyền**.

### 6.1. Discovery không chạy cho mọi request

Trong triển khai thông thường:

1. Metadata được tải khi decoder cần xác định nguồn khóa, không nhất thiết tải lại cho từng HTTP request.
2. Các public keys trong JWKS được cache trong một khoảng thời gian.
3. JwtDecoder dùng cache để xác minh nhiều JWT.
4. Khi issuer luân chuyển khóa, thư viện có thể làm mới JWKS theo chính sách cache/miss.
5. Khi JWKS endpoint gặp lỗi, decoder có thể dùng khóa còn cache theo hành vi thư viện; token cần khóa chưa có sẽ không được chấp nhận.

Không khẳng định rằng **mọi token đều yêu cầu hai network requests**. Cũng không khẳng định endpoint metadata/JWKS có thể mất kết nối vô thời hạn mà không ảnh hưởng đến xác minh, vì cache và key rotation có giới hạn.

### 6.2. Discovery diễn ra lúc startup hay lúc request đầu tiên?

Tài liệu Spring Security 6.5/7.1 JWT Resource Server mô tả cơ chế discovery được **hoãn đến request chứa JWT đầu tiên** trong cấu hình tự động tương ứng; với Servlet, cơ chế hoãn này có thể do **SupplierJwtDecoder** quản lý. Cách này giảm việc Resource Server bị phụ thuộc vào tình trạng mạng của Authorization Server ngay khi khởi động.

Tuy nhiên, **tự gọi** phương thức khám phá issuer khi khởi tạo bean JwtDecoder hoặc dựng decoder bằng API khác có thể gây truy cập mạng sớm. Cách wiring custom bean cũng có thể thay đổi cơ chế hoãn. Vì vậy:

- Không dựa vào giả định mọi phiên bản Boot/Security đều liên hệ issuer tại startup.
- Không dựa vào giả định mọi custom JwtDecoder đều hoãn discovery.
- Khi yêu cầu startup không phụ thuộc issuer, dùng cấu hình phù hợp hoặc **jwk-set-uri trực tiếp**, và kiểm hành vi trên phiên bản thực tế.

**Hoãn discovery không làm hệ thống tự xác thực được token lúc issuer/JWKS đang unavailable.** Nếu lúc cần xác minh mà chưa có khóa tin cậy, xác thực JWT phải thất bại theo cấu hình, không được bỏ kiểm chữ ký.

## 7. Spring Boot: chỉ định issuer-uri để tự tìm jwks_uri

Với Spring Boot và Spring Security Resource Server, cấu hình thường gặp:

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

**issuer-uri** có hai tác dụng quan trọng:

- Xác định issuer tin cậy để discovery metadata/JWKS.
- Thiết lập kiểm tra claim **iss** của JWT theo cơ chế Resource Server được cấu hình.

**audiences** giúp yêu cầu claim **aud** của JWT chứa **orders-api**, vì token do đúng issuer ký vẫn có thể được phát hành cho API khác. Spring Security không tự suy ra audience nghiệp vụ chỉ từ jwks_uri.

Cần có dependency cho OAuth2 Resource Server và JOSE JWT. Với Spring Boot 3.x, thường dùng starter **spring-boot-starter-oauth2-resource-server**; với Boot 4.x dùng starter **spring-boot-starter-security-oauth2-resource-server**. Để Spring Boot quản lý các version Security tương ứng.

### 7.1. Cấu hình Servlet SecurityFilterChain

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

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

Khi API nhận JWT, Resource Server dùng JwtDecoder cấu hình theo issuer/JWKS và ánh xạ scope đã được xác thực thành authorities như **SCOPE_orders.read**.

**Discovery không tạo quyền.** Token có chữ ký hợp lệ, đúng iss/aud và còn hạn vẫn không được đọc dữ liệu nghiệp vụ nếu thiếu scope hoặc bị policy tenant/ownership từ chối.

### 7.2. Không nhầm JWT access token và OIDC ID Token

OpenID Provider có thể ký **ID Token** và **access token** bằng cùng bộ khóa. Khả năng lấy JWKS và kiểm chữ ký **không chứng minh** một ID Token có thể dùng để gọi API.

Resource Server phải nhận **access token đúng audience và token profile**, không mặc định chấp nhận một JWT bất kỳ do issuer ký.

## 8. Nếu không dùng discovery thì chỉ định jwk-set-uri trực tiếp

Một số Authorization Server:

- Không công bố OIDC/OAuth metadata endpoint tương thích.
- Công bố metadata nhưng thiếu jwks_uri mà API cần.
- Có metadata ở URL khác hợp đồng mà framework không tự tìm được.
- Resource Server cần biết endpoint khóa ngay trong cấu hình để kiểm soát thời điểm khởi tạo.

Khi đã được quản trị cung cấp **JWKS URI tin cậy**, có thể khai báo:

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

Trong cấu hình này:

- **jwk-set-uri** chỉ rõ nơi lấy public key, vì vậy Spring Security không cần dùng discovery metadata để tìm endpoint.
- **issuer-uri** vẫn xác định issuer và giúp xác thực **iss**.
- **audiences** vẫn cần nếu API yêu cầu kiểm **aud**.
- Chữ ký và thời hạn JWT vẫn phải được kiểm.

Đây là phương án phù hợp khi cần tránh một bước khám phá metadata hoặc khi provider có endpoint không tiêu chuẩn, **miễn nguồn JWKS được tin cậy và cấu hình đúng**.

Một lỗi dễ mắc:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          jwk-set-uri: https://login.example.com/realms/shop/protocol/openid-connect/certs
~~~

Nếu chỉ cấu hình **jwk-set-uri** mà không có kiểm issuer tương ứng, API có nguy cơ chỉ xác minh token theo tập khóa mà thiếu chính sách **iss**. Muốn dùng cấu hình kiểu này an toàn, phải tự thiết lập các validators cần thiết cho issuer, audience và token profile. Với thiết lập thông thường, nên giữ **issuer-uri** và **audiences**.

### 8.1. Cung cấp JWKS URI trong DSL hoặc custom JwtDecoder

Spring Security cho phép chỉ định JWK Set URI trực tiếp qua cấu hình Resource Server hoặc tạo decoder tùy chỉnh. Ví dụ Java:

~~~java
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

@Bean
JwtDecoder jwtDecoder() {
    NimbusJwtDecoder decoder = NimbusJwtDecoder
        .withJwkSetUri(
            "https://login.example.com/realms/shop/protocol/openid-connect/certs")
        .build();

    decoder.setJwtValidator(JwtValidators.createDefaultWithIssuer(
        "https://login.example.com/realms/shop"));

    return decoder;
}
~~~

Đoạn này **chỉ minh họa cách chọn nguồn JWK và issuer validator**. Nếu tự tạo JwtDecoder, cần bổ sung **audience validator** và các rule token-type/profile theo chính sách API. Khi cung cấp **@Bean JwtDecoder** riêng, auto-configuration của Boot có thể lùi lại; không nên mặc định mọi property **audiences** sẽ tự gắn vào decoder custom.

Ngoài ra cần cấu hình thuật toán xác minh được phép, client HTTP/TLS, timeout/cache nếu phải tùy chỉnh sâu. Không nên bỏ các validator mặc định khi thay decoder.

## 9. Kiểm chứng discovery bằng curl và jq

Trong môi trường được phép, người vận hành có thể kiểm tra **metadata** mà không cần đưa access token thật vào câu lệnh.

Giả sử issuer:

~~~text
https://login.example.com/realms/shop
~~~

### 9.1. Bước 1: lấy OpenID Provider Configuration

~~~bash
curl --fail --show-error --silent \
  https://login.example.com/realms/shop/.well-known/openid-configuration
~~~

Nếu có **jq**, chỉ hiển thị hai trường quan trọng:

~~~bash
curl --fail --show-error --silent \
  https://login.example.com/realms/shop/.well-known/openid-configuration \
  | jq '{issuer, jwks_uri}'
~~~

Kết quả dự kiến (minh họa):

~~~json
{
  "issuer": "https://login.example.com/realms/shop",
  "jwks_uri": "https://login.example.com/realms/shop/protocol/openid-connect/certs"
}
~~~

Kiểm tra rằng:

1. Response trả JSON hợp lệ qua HTTPS.
2. **issuer** đúng chính xác với issuer-uri ứng dụng cấu hình.
3. **jwks_uri** có mặt và là URL HTTPS dùng để tải khóa.
4. Endpoint phù hợp với nhà cung cấp và môi trường (dev/staging/prod).

Nếu URL OIDC trả 404, không vội kết luận provider không hỗ trợ discovery. Với issuer có path, kiểm thêm những vị trí **RFC 8414** mà phiên bản Spring Security hỗ trợ và xem tài liệu provider.

### 9.2. Bước 2: lấy JWKS từ giá trị jwks_uri

~~~bash
curl --fail --show-error --silent \
  https://login.example.com/realms/shop/protocol/openid-connect/certs
~~~

Nếu chỉ cần xem cấu trúc khóa:

~~~bash
curl --fail --show-error --silent \
  https://login.example.com/realms/shop/protocol/openid-connect/certs \
  | jq '.keys[] | {kid, kty, use, alg}'
~~~

Kết quả minh họa:

~~~json
{
  "kid": "shop-key-2026-11",
  "kty": "RSA",
  "use": "sig",
  "alg": "RS256"
}
~~~

Ở đây **jwks_uri** đã được lấy từ metadata hợp lệ trước khi gọi. Đừng viết client tự động tải JWKS từ một URL do Bearer token chưa xác thực khai báo.

### 9.3. Kiểm bằng PowerShell

Trên Windows PowerShell:

~~~powershell
$issuer = 'https://login.example.com/realms/shop'
$metadataUrl = "$issuer/.well-known/openid-configuration"

$metadata = Invoke-RestMethod -Uri $metadataUrl -Method Get
$metadata.issuer
$metadata.jwks_uri

$jwks = Invoke-RestMethod -Uri $metadata.jwks_uri -Method Get
$jwks.keys | Select-Object kid, kty, use, alg
~~~

Ví dụ này chỉ minh họa quy trình tải metadata/JWKS từ **issuer đã biết trước**. Với hệ thống production, cần kiểm certificate, chính sách tin cậy URL, redirect và lỗi HTTP trong client. Không sử dụng công cụ bỏ qua TLS verification để “làm cho discovery chạy được”.

## 10. Những lỗi thường thấy khi Spring Security không tìm được jwks_uri

### 10.1. Sai issuer-uri hoặc sai dấu slash

Ví dụ:

~~~text
Issuer cấu hình:
https://login.example.com/realms/shop/

Issuer trong metadata:
https://login.example.com/realms/shop
~~~

Khác biệt dấu slash có thể dẫn tới sai URL ghép hoặc mismatch trong so sánh issuer. Hãy lấy **issuer canonical** do provider công bố và dùng nhất quán giữa cấu hình, metadata và claim **iss** của JWT.

Không tự xóa/thêm slash vào dữ liệu token đã phát hành để né lỗi.

### 10.2. Metadata endpoint trả 404

Có thể do:

- Provider không hỗ trợ endpoint tương ứng.
- Issuer có path nhưng URL được thử theo quy tắc OIDC/RFC 8414 khác.
- Reverse proxy route chưa công bố đúng đường dẫn **.well-known**.
- Authorization Server được cài dưới context path khác với issuer bên ngoài.
- Một lớp gateway chặn endpoint metadata.

Hướng xử lý: kiểm issuer thực tế, thử những URL metadata chuẩn được tài liệu Spring Security hỗ trợ, xác nhận metadata của đúng tenant/realm và chỉnh proxy/provider. Nếu provider thật sự không có discovery tương thích, cấu hình **jwk-set-uri** đáng tin cậy trực tiếp.

### 10.3. Metadata có jwks_url nhưng không có jwks_uri

JSON như sau không dùng đúng tên trường chuẩn:

~~~json
{
  "issuer": "https://login.example.com/realms/shop",
  "jwks_url": "https://login.example.com/keys"
}
~~~

Theo OIDC Discovery/RFC 8414, trường metadata chuẩn cần là **jwks_uri**. Nếu provider trả tên riêng **jwks_url**, phải sửa provider hoặc dùng phương án cấu hình rõ ràng có kiểm soát; không suy ra Spring Security sẽ tự hiểu trường tùy biến đó.

### 10.4. Metadata issuer không trùng issuer cấu hình

~~~json
{
  "issuer": "https://login.example.com/realms/other",
  "jwks_uri": "https://login.example.com/realms/other/certs"
}
~~~

Nếu API đang cấu hình tin **/realms/shop**, không dùng response của **/realms/other**. Xem URL đang dùng, proxy rewrite, realm/tenant và thông tin provider. Mismatch issuer là **vấn đề bảo mật**, không chỉ lỗi định dạng.

### 10.5. Lỗi TLS hoặc trust store

Một số log có thể chứa thông báo:

~~~text
PKIX path building failed
SSLHandshakeException
certificate verify failed
~~~

Nguyên nhân thường là internal CA chưa được JVM trust store tin cậy, hostname không khớp SAN hoặc chứng chỉ hết hạn.

Cách xử lý: cấu hình certificate chain đúng, cập nhật trust store đáng tin cậy và kiểm hostname. Không dùng **trust-all certificates**, **curl -k** hoặc tắt SSL verification trong production. Việc metadata/JWKS chỉ chứa public key **không làm TLS verification trở nên không cần thiết**.

### 10.6. Không kết nối được từ container

Máy developer có thể gọi metadata thành công, nhưng container trong Kubernetes không có DNS, proxy egress hoặc route thích hợp.

Kiểm từ **chính môi trường Resource Server**:

- DNS của hostname issuer.
- Outbound network policy, egress gateway, proxy.
- TLS handshake/trust store của JVM.
- Timeout hoặc redirect.
- Endpoint metadata/JWKS có được công bố và trả JSON hợp lệ.

Không lầm lẫn hostname/URL public với địa chỉ nội bộ có issuer khác; token **iss** phải vẫn đúng theo issuer đã được phát hành.

### 10.7. Có jwks_uri nhưng JWKS rỗng hoặc không có key phù hợp

Ví dụ JWT có **kid = key-b**, nhưng JWKS cache chỉ có **key-a**. Đây không phải lỗi tìm metadata nữa; nó là lỗi **chọn hoặc tải khóa để xác minh**. Cần kiểm rotation, cache JWKS, thuật toán/kty và thời điểm công bố key mới.

### 10.8. Metadata hoạt động nhưng JWT luôn trả 401

Discovery thành công chỉ chứng minh API tìm được nguồn khóa. Token vẫn có thể bị từ chối do:

- Signature không khớp JWK.
- **kid** không có hoặc không tìm được key phù hợp.
- **alg** không được API cho phép.
- **iss** của JWT khác issuer tin cậy.
- **aud** không chứa audience của Resource Server.
- **exp** hết hạn hoặc **nbf** chưa tới.
- Token là OIDC **ID Token** thay vì access token đúng profile.
- Cấu hình custom JwtDecoder thiếu validator hoặc dùng sai token type.

Xác định chính xác bước thất bại rồi sửa chính sách/cấu hình. Không bỏ signature/issuer/audience validation để chuyển 401 thành 200.

## 11. Các vấn đề bảo mật khi dùng discovery

### 11.1. Không để JWT tự chọn issuer hoặc jwks_uri

Một token chưa được xác minh có thể chứa:

~~~json
{
  "iss": "https://attacker.example",
  "sub": "admin",
  "scope": "orders.write"
}
~~~

Nếu API lấy **iss** này rồi tự động khám phá metadata của bất kỳ hostname nào, kẻ tấn công có thể công bố JWKS chứa public key do họ sở hữu, tự ký JWT và khiến API tin token giả.

Cách đúng là:

1. Resource Server có **issuer-uri được cấu hình tin cậy** hoặc danh sách issuer cho phép.
2. Dùng **đúng issuer đã cho phép** để khám phá metadata.
3. Kiểm metadata issuer theo hợp đồng.
4. Chỉ dùng **jwks_uri** xuất phát từ nguồn đã được tin cậy.
5. Kiểm signature và claims rồi mới cấp quyền.

Trong multi-issuer/multi-tenant, có thể dùng resolver được thiết kế có allowlist tenant/issuer; không biến claim **iss** tùy ý thành một endpoint tải khóa không kiểm soát.

### 11.2. Không làm SSRF qua endpoint discovery

Các URL metadata/JWKS là điểm truy cập mạng của Resource Server. Nếu cho người gửi request hoặc JWT tùy ý quyết định URL, họ có thể khiến server gửi request đến địa chỉ nội bộ, cloud metadata service hoặc hệ thống không liên quan.

Hạn chế gồm:

- Chỉ cho phép những issuer đã được đăng ký tin cậy.
- Chỉ dùng HTTPS và xác minh hostname/certificate.
- Quản lý egress/DNS, redirect và host được phép theo threat model.
- Không dùng **jku**, **jwk** hay **x5u** từ JWT chưa xác minh để nạp khóa tùy ý.
- Không cung cấp endpoint debug nhận URL rồi server tự fetch metadata/JWKS mà không có ràng buộc.

**JWKS có thể được host trên miền khác issuer** nếu hệ thống nhà cung cấp thiết kế như vậy; không bắt buộc same-origin tuyệt đối. Nhưng việc tin URL khác đó phải xuất phát từ metadata/issuer đáng tin và chính sách mạng/TLS được quản trị.

### 11.3. JWKS là public nhưng tính toàn vẹn của đường truyền vẫn quan trọng

Người dùng có thể tải public keys; đó là thiết kế đúng cho chữ ký bất đối xứng. Nhưng nếu kẻ tấn công **thay thế JWKS** bằng public key của họ qua kết nối không được xác thực, họ có thể làm thay đổi nền tảng kiểm chữ ký của API.

Do đó:

- Metadata endpoint và jwks_uri dùng HTTPS.
- Client kiểm chain và hostname của certificate.
- Không cho reverse proxy đổi metadata issuer/jwks_uri sang môi trường khác ngoài ý muốn.
- JWKS công khai chỉ chứa public signing keys; không chứa private signing key hoặc secret HMAC.
- Quyền quản trị issuer/JWKS và thay đổi DNS/route phải được bảo vệ.

### 11.4. Kiểm algorithm và key-use

Một JWKS có thể gồm nhiều loại key. Resource Server cần chọn key phù hợp **kid**, **kty**, **alg** được cho phép, và mục đích **sig/verify** nếu được khai báo.

Chữ ký JWT chỉ được kiểm bởi những thuật toán đã được ứng dụng tin cậy (ví dụ RS256 theo hợp đồng). Không cho token tự chuyển từ RS256 sang HS256 hoặc **alg = none** để vượt xác thực.

### 11.5. CORS và quyền công bố metadata

Metadata và JWKS thông thường được công bố công khai để client có thể khám phá endpoint và public keys; không cần gắn access token người dùng vào request lấy JWKS. Nhưng việc công khai metadata không có nghĩa công khai token endpoint secrets hoặc private keys.

CORS là chính sách của browser; Resource Server chạy server-to-server không cần CORS để gọi JWKS, và bật CORS không thay thế TLS. Không gửi Bearer token của người dùng đến metadata/JWKS endpoint chỉ để đọc public keys.

## 12. JWKS rotation sau khi discovery

Một lợi ích quan trọng của JWKS là khả năng đổi khóa ký mà không phải triển khai lại mọi Resource Server.

Giả sử:

| Giai đoạn | Key mà issuer ký JWT | JWKS công bố | Kết quả mong muốn |
|---|---|---|---|
| **T0** | key A | Public key A | Các JWT ký bằng A được xác minh |
| **T1** | Vẫn ký A | Public key A và B | Resource Server có thể nhận B trước |
| **T2** | Bắt đầu ký B | Public key A và B | JWT cũ A và JWT mới B đều được xác minh |
| **T3** | Chỉ ký B, token A đã hết hiệu lực | Public key B | Có thể gỡ A sau giai đoạn chuyển tiếp |

**Discovery tìm JWKS URI** thường không cần thay khi rotation; chỉ nội dung JWKS tại URI đó được cập nhật. JwtDecoder có thể làm mới cache key theo chính sách triển khai.

Điểm cần phối hợp:

- **Publish-before-use:** công bố public key B trước khi dùng private key B ký access token.
- **Overlap:** giữ key A khi token ký bởi A còn hiệu lực, trừ tình huống khóa bị xâm phạm cần thu hồi khẩn.
- **Cache:** xét TTL và cache refresh của Resource Server, proxy/CDN.
- **kid:** không tái sử dụng bừa cùng kid cho key material khác khi cache vẫn tồn tại.
- **Failure policy:** nếu thiếu key để xác minh, phải từ chối token thay vì chấp nhận không chữ ký.

Khi private signing key bị lộ, rotation khẩn cấp có thể khiến một số token hợp lệ bị từ chối; đó là một đánh đổi an toàn cần quy trình phản ứng sự cố, không phải “lỗi discovery”.

## 13. So sánh ba cấu hình thường gặp

| Cấu hình | Discovery metadata? | Kiểm iss tự động? | Khi nào dùng? |
|---|---|---|---|
| Chỉ **issuer-uri** | Có, theo Spring Security và endpoint được hỗ trợ | Có theo cấu hình tiêu chuẩn | Provider hỗ trợ OIDC/OAuth metadata |
| **issuer-uri + jwk-set-uri** | Không cần discovery để biết JWKS URL | Có theo cấu hình tiêu chuẩn | Endpoint JWKS đã biết, cần giảm phụ thuộc metadata discovery |
| Chỉ **jwk-set-uri** | Không | Không nên giả định có nếu không thiết lập issuer validator | Chỉ dùng với validator issuer/audience/token profile được cấu hình riêng |

Trong cả ba trường hợp cần kiểm **audience**, thời hạn, thuật toán, loại token và quyền nghiệp vụ theo chính sách API. **Cấu hình jwk-set-uri trực tiếp không có nghĩa bỏ qua xác minh chữ ký.**

### 13.1. Những điều không thể suy ra từ discovery

Discovery **không** khẳng định:

- Token Bearer hiện tại chắc chắn hợp lệ.
- JWT của issuer có thể dùng cho mọi API khác nhau.
- Scope **openid/profile/email** là quyền nghiệp vụ.
- Access token đã được cấp quyền **orders.read**.
- Người dùng có quyền trên đơn hàng cụ thể.
- Resource Server sẽ tự biết khi quyền người dùng bị thu hồi ngay lập tức.
- Cấu hình proxy, TLS, DNS và cache đều đã an toàn.

Discovery chỉ là bước tạo **trust configuration của nguồn khóa**. Các quyết định authentication và authorization vẫn phải được thực thi riêng.

## 14. Một cách đọc lỗi theo đúng thứ tự

Khi API không xác thực được JWT, nên xác định lỗi nằm ở lớp nào:

~~~mermaid
flowchart TD
    A[Resource Server nhận Bearer JWT] --> B{Đã cấu hình issuer-uri hợp lệ?}
    B -->|Không| C[Sửa issuer cấu hình]
    B -->|Có| D{Metadata endpoint truy cập được?}
    D -->|Không| E[Kiểm well-known URL, proxy, DNS và TLS]
    D -->|Có| F{Metadata issuer khớp và có jwks_uri?}
    F -->|Không| G[Sửa provider metadata hoặc cấu hình JWKS trực tiếp]
    F -->|Có| H{Tải JWKS và chọn key phù hợp?}
    H -->|Không| I[Kiểm jwks_uri, cache, kid, alg và rotation]
    H -->|Có| J{Signature và JWT claims hợp lệ?}
    J -->|Không| K[Kiểm signature, iss, aud, exp, nbf, typ]
    J -->|Có| L{Đủ quyền endpoint/tài nguyên?}
    L -->|Không| M[Kiểm scope, role, owner, tenant]
    L -->|Có| N[Cho phép xử lý nghiệp vụ]
~~~

Một số tình huống cụ thể:

**Tình huống A: metadata 200, JWKS 200, JWT 401.** Discovery có thể đã hoàn tất. Kiểm token signature, kid, issuer, audience, expiration, type. Đừng tiếp tục đổi đường dẫn **.well-known** nếu thực tế API đã lấy được JWKS.

**Tình huống B: issuer URI đúng nhưng metadata 404.** Kiểm ba vị trí well-known phù hợp, nhất là khi issuer có path; xem proxy rewrite và tài liệu của provider.

**Tình huống C: metadata JSON có jwks_uri nhưng certificate không hợp lệ.** Sửa trust chain, hostname và chứng chỉ của JWKS host; không tắt TLS verification.

**Tình huống D: token mới thất bại sau rotation.** Kiểm kid và JWKS cache, xác nhận public key mới đã được phát trước khi private key mới ký JWT.

**Tình huống E: token hợp lệ nhưng 403.** Discovery và chữ ký có thể hoàn toàn đúng. Kiểm chính sách quyền nghiệp vụ và mapping scope, không tiếp tục sửa key.

## 15. Bài thực hành suy luận

Cho issuer tin cậy:

~~~text
https://auth.example.org/teams/finance
~~~

Và metadata:

~~~json
{
  "issuer": "https://auth.example.org/teams/finance",
  "jwks_uri": "https://keys.example.org/finance/public-jwks.json"
}
~~~

Một JWT đến Orders API có:

~~~json
{
  "iss": "https://auth.example.org/teams/finance",
  "aud": ["payments-api"],
  "scope": "payments.read"
}
~~~

Hãy xác định:

1. **OIDC discovery URL** là gì?
2. **RFC 8414 OAuth discovery URL** là gì?
3. Có được lấy JWKS ở hostname **keys.example.org** không?
4. Sau khi JWT verify bằng public key đúng, Orders API có nên chấp nhận token trên không?

**Phân tích:**

- OIDC discovery: **https://auth.example.org/teams/finance/.well-known/openid-configuration**.
- RFC 8414 OAuth: **https://auth.example.org/.well-known/oauth-authorization-server/teams/finance**.
- **jwks_uri** có thể dùng host khác issuer nếu xuất phát từ metadata được xác thực theo issuer tin cậy, URL HTTPS/certificate đúng và chính sách egress/allowlist chấp nhận. Không đặt mặc định “mọi host bên ngoài đều được tin”.
- **Orders API phải từ chối** nếu yêu cầu audience **orders-api**. Token trên có audience **payments-api**, dù chữ ký chính xác và issuer đúng; việc dùng key đúng không thay thế audience validation.

Bài thực hành này phân biệt chính xác **tìm khóa** với **xác minh token dành cho Resource Server nào**.

## 16. Các câu hỏi cần trả lời trước khi đưa Resource Server vào vận hành

1. **Issuer nào là nguồn tin cậy?** Có đúng scheme/host/port/path và khớp claim iss không?
2. **Metadata endpoint nào được hỗ trợ?** OIDC discovery, RFC 8414 hay provider yêu cầu chỉ định trực tiếp JWKS URI?
3. **Metadata trả trường gì?** Có **issuer** khớp và **jwks_uri** đúng chuẩn không?
4. **JWKS có an toàn không?** Chỉ chứa public keys, nguồn HTTPS được xác minh, không lộ private/symmetric secrets?
5. **Thuật toán xác minh nào được cho phép?** Decoder có kiểm đúng kid/kty/use và giới hạn alg không?
6. **Có kiểm đủ claims không?** Issuer, audience, timestamps, access-token type/profile được xác định rõ chứ?
7. **Khởi tạo và cache thế nào?** Discovery xảy ra khi nào, timeout/rotation/JWKS outage được xử lý ra sao?
8. **Multi-tenant có giới hạn issuer không?** Có allowlist hay resolver an toàn, tránh tự tin issuer do token đề xuất?
9. **Phân quyền ở đâu?** Scope/role và quyền trên tenant/owner được kiểm trong web/method/domain policy chứ?
10. **Quan sát sự cố thế nào?** Có log request ID, lỗi mạng và validator an toàn mà không ghi access token thật không?

## Kết luận

Spring Security tìm **jwks_uri** bằng cách bắt đầu từ **issuer-uri được cấu hình tin cậy**, truy cập metadata chuẩn của OpenID Connect hoặc OAuth 2.0, đọc **issuer** và **jwks_uri**, rồi lấy JWKS từ địa chỉ được công bố. OIDC và RFC 8414 có cách xây dựng **.well-known URL** khác nhau khi issuer chứa path, vì vậy cần hiểu đúng đặc tả và endpoint mà nhà cung cấp hỗ trợ.

**jwks_uri không phải token, không phải issuer và không phải một quyền.** Nó là địa chỉ của tập public keys phục vụ xác minh chữ ký. Sau discovery, JwtDecoder vẫn phải kiểm chữ ký bằng khóa/thuật toán tin cậy, xác minh **iss**, **aud**, thời hạn và token profile, rồi Resource Server mới kiểm quyền nghiệp vụ. Nếu không thể discovery, có thể chỉ định **jwk-set-uri** trực tiếp nhưng phải giữ những ràng buộc tin cậy tương đương.

### Tài liệu tham khảo

- [Spring Security — Servlet OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
- [Spring Security — Reactive OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html)
- [Spring Boot — OAuth2 Resource Server Configuration](https://docs.spring.io/spring-boot/reference/security/oauth2.html)
- [OpenID Connect Discovery 1.0, Section 3–4](https://openid.net/specs/openid-connect-discovery-1_0.html)
- [RFC 8414 — OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414)
- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517)
- [RFC 7515 — JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515)
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519)
- [RFC 8725 — JWT Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725)
