# Kiểm tra thay đổi mặc định về thuật toán, typ và validator

Khi nâng cấp **Spring Security OAuth 2.0 / OIDC Resource Server**, cần kiểm tra decoder JWT theo ba lớp độc lập: **thuật toán chữ ký JWS (alg), kiểu JOSE trong header (typ), và chuỗi validator kiểm tra issuer/claims**. Một ứng dụng có thể vẫn khởi động và nhận request sau khi nâng cấp nhưng bắt đầu từ chối token hợp lệ do `typ` thay đổi cách được kiểm tra. Ngược lại, một custom validator có thể vô tình thay thế các kiểm tra issuer hoặc thời hạn vốn có.

Với nhánh Spring Security 6.5 chuẩn bị cho 7.0, thay đổi quan trọng là chuyển việc kiểm tra header `typ` từ Nimbus JOSE processor sang `JwtTypeValidator`. Trong Spring Security 7, Nimbus không còn tự kiểm tra `typ` theo mặc định; các factory `JwtValidators.createDefault...` bổ sung `JwtTypeValidator.jwt()` vào chuỗi validator. Giá trị mặc định của validator này chấp nhận `typ` bằng `JWT` hoặc không có header `typ`.

Thuật toán mặc định của `NimbusJwtDecoder` vẫn là **RS256**. Vì vậy, không nên kết luận rằng nâng cấp 7.0 tự đổi thuật toán ký. Điều cần làm là xác nhận thuật toán issuer đang phát hành, cách decoder được tạo (Boot issuer discovery hay custom JWK Set URI), và allowlist mà Resource Server thực sự sử dụng.

Bài học thuộc chương **Nâng cấp và di chuyển**, dùng **Java 17+, Spring Boot 3.x/4.x và Spring Security 6.5/7.x** làm bối cảnh. Nội dung giải thích khác biệt giữa `alg`, `typ` và JWT claims, cách chuẩn bị trên 6.5, cách hoàn tất migration trên 7.x, RFC 9068 `at+jwt`, cách giữ validator mặc định khi bổ sung audience/domain rules, và kiểm thử bằng JWT có chữ ký thật.

## 1. Ba lớp kiểm tra thường bị nhầm lẫn

JWT Resource Server không chỉ kiểm tra một chuỗi token. Decoder xử lý nhiều lớp:

~~~text
Authorization: Bearer <compact-JWT>
             |
             v
       Parse JOSE header
             |
             +-- alg: thuật toán chữ ký nào được yêu cầu?
             +-- kid: khóa nào trong JWK Set có thể phù hợp?
             +-- typ: token được khai báo thuộc loại nào?
             |
             v
       Chọn key và verify JWS signature
             |
             v
       Map JWT header + claims
             |
             v
       OAuth2TokenValidator chain
             |
             +-- iss: issuer được tin cậy?
             +-- exp / nbf: token đang trong thời hạn?
             +-- typ: loại token được decoder chấp nhận?
             +-- aud: token dành cho API này?
             +-- custom claims / tenant / policy
             |
             v
       JwtAuthenticationConverter
             |
             v
       Authentication và authorities
~~~

| Trường | Nằm ở đâu | Vai trò |
| --- | --- | --- |
| `alg` | JOSE protected header | Thuật toán ký JWS. Decoder phải chỉ chấp nhận thuật toán được tin cậy. |
| `kid` | JOSE header | Gợi ý chọn key tương ứng trong JWK Set; không phải bằng chứng token hợp lệ. |
| `typ` | JOSE header | Khai báo kiểu nội dung/token, ví dụ `JWT` hoặc `at+jwt`. |
| `iss` | JWT payload | Issuer đã phát hành token. |
| `aud` | JWT payload | Resource/API được token gửi tới. |
| `exp`, `nbf`, `iat` | JWT payload | Các mốc thời gian của token. |
| `scope`, `scp`, `roles` | JWT payload | Dữ liệu có thể được converter ánh xạ thành authorities theo policy. |

`alg` và `typ` không phải JWT payload claims. `JwtTypeValidator` đọc `typ` từ header; `JwtClaimValidator` đọc claims từ payload. Xác minh chữ ký xảy ra trước khi tin claims, còn validator bổ sung quyết định token đã được xác minh có phù hợp với contract của API hay không.

## 2. Những thay đổi cần đối chiếu khi nâng cấp

| Khu vực | Spring Security 6.5 chuẩn bị migration | Spring Security 7.x |
| --- | --- | --- |
| JWS algorithm | Decoder Nimbus mặc định tin RS256; cấu hình rõ nếu issuer dùng thuật toán khác. | RS256 vẫn là mặc định của `NimbusJwtDecoder`; tiếp tục xác nhận allowlist và cách khởi tạo decoder. |
| Nimbus `typ` handling | Mặc định Nimbus kiểm tra `typ`; có thể tắt bằng `validateType(false)` để chuyển sang validator. | Nimbus `typ` verification mặc định tắt; kiểm tra `typ` nằm trong validator chain. |
| `JwtTypeValidator` | Thêm validator tường minh để chuẩn bị cho 7. | Các `JwtValidators.createDefault...` factory bao gồm `JwtTypeValidator.jwt()`. |
| Default `typ` policy | `JWT` hoặc header không có `typ` tương đương hành vi Nimbus mặc định. | `JwtTypeValidator.jwt()` chấp nhận `JWT` hoặc `typ` vắng mặt. |
| RFC 9068 | `JwtValidators.createAtJwtValidator()` có từ 6.5. | Có thể dùng validator này để yêu cầu JWT Access Token theo RFC 9068. |
| Audience | Cần cấu hình riêng; issuer validation không tự chứng minh token dành cho API. | Vẫn cần cấu hình audience riêng nếu không dùng Boot property tương ứng. |
| Validator chain | Dùng factory/default validators và thêm custom validators. | Default factory thêm kiểm tra `typ`; gọi `setJwtValidator` vẫn thay thế validator chain hiện tại. |

Nên dùng 6.5 làm bước chuẩn bị trước khi nâng lên 7.0. Khi các test đã xác nhận hành vi `typ` mới, việc chuyển sang 7.x sẽ ít bất ngờ hơn.

## 3. Kiểm tra mặc định của JWS algorithm

### 3.1. RS256 vẫn là mặc định của NimbusJwtDecoder

Với `NimbusJwtDecoder`, thuật toán mặc định được tin cậy là `RS256`. Đây là chữ ký RSA với SHA-256. Nếu Authorization Server ký bằng `RS512`, `ES256` hoặc thuật toán khác, Resource Server phải cấu hình thuật toán tương ứng.

Không nhầm thay đổi `typ` với thay đổi `alg`: chuyển type validation từ Nimbus sang `JwtTypeValidator` không làm thay đổi thuật toán ký.

### 3.2. Cấu hình thuật toán bằng Spring Boot

Ví dụ khi issuer chỉ ký bằng RS512:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://identity.example.test
          jwk-set-uri: https://identity.example.test/oauth2/jwks
          jws-algorithms: RS512
~~~

`jws-algorithms` là allowlist của Resource Server. Đặt đúng giá trị issuer phát hành và key/JWK hỗ trợ. `issuer-uri` vẫn dùng để xác minh claim `iss`; `jwk-set-uri` xác định nguồn public key.

Nếu issuer ký bằng nhiều thuật toán trong giai đoạn chuyển đổi, chỉ liệt kê những thuật toán thực sự được chấp thuận:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://identity.example.test
          jwk-set-uri: https://identity.example.test/oauth2/jwks
          jws-algorithms:
            - RS256
            - ES256
~~~

Giữ allowlist ngắn. Không thêm thuật toán chỉ để token nào cũng qua được; mỗi thuật toán cần có key type, key lifecycle và policy được hỗ trợ.

### 3.3. Cấu hình bằng NimbusJwtDecoder builder

Một thuật toán:

~~~java
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

JwtDecoder decoder = NimbusJwtDecoder
    .withJwkSetUri("https://identity.example.test/oauth2/jwks")
    .jwsAlgorithm(SignatureAlgorithm.ES256)
    .build();
~~~

Nhiều thuật toán:

~~~java
NimbusJwtDecoder decoder = NimbusJwtDecoder
    .withJwkSetUri("https://identity.example.test/oauth2/jwks")
    .jwsAlgorithm(SignatureAlgorithm.RS256)
    .jwsAlgorithm(SignatureAlgorithm.ES256)
    .build();
~~~

Hoặc dùng `jwsAlgorithms` để khai báo tập thuật toán trong một callback. Các ví dụ trên chỉ cấu hình xác minh chữ ký; vẫn phải gắn validator cho issuer, thời gian, audience và type.

### 3.4. Boot issuer discovery và custom decoder có thể có đường cấu hình khác nhau

Khi dùng issuer discovery, Spring Security truy vấn metadata để tìm `jwks_uri`; một số đường auto-configuration còn đọc thuật toán được công bố trong JWK Set để xây dựng validation strategy. Khi tự tạo `NimbusJwtDecoder` bằng JWK Set URI builder, mặc định của decoder là RS256 trừ khi được cấu hình khác.

Vì vậy, khi migration:

1. Xác định app đang dùng Boot auto-configuration, `JwtDecoders.fromIssuerLocation`, `NimbusJwtDecoder.withIssuerLocation` hay `withJwkSetUri`.
2. Kiểm tra `jws-algorithms` property và custom builder có đang ghi đè lẫn nhau không.
3. Xem JWK Set có `kty`, `use`, `key_ops`, `alg` và `kid` phù hợp với thuật toán ký không.
4. Tạo test với từng thuật toán được cho phép và ít nhất một thuật toán bị từ chối.

Không dùng `alg` trong header của token làm nguồn cấu hình allowlist. Header là dữ liệu do bên phát hành token cung cấp; Resource Server phải có policy độc lập để quyết định thuật toán nào được phép.

### 3.5. Tránh algorithm confusion

- Không chấp nhận `none` cho Bearer Access Token.
- Không dùng cùng key material theo cách khiến HMAC secret bị hiểu nhầm thành RSA public key.
- Không mở allowlist thành toàn bộ algorithm family chỉ để khắc phục lỗi key rotation.
- Không cho token quyết định key URL hoặc issuer.
- Không bỏ kiểm tra signature khi key không tải được.
- Khi chuyển RSA sang EC, phối hợp issuer, JWK Set, key rotation và Resource Server trước khi phát hành token bằng key mới.

`RS256`, `RS512`, `ES256` là ví dụ JWS signature algorithms. `alg`/`enc` của JWE là một chủ đề khác; cấu hình JWS allowlist không phải cấu hình giải mã mọi loại encrypted JWT.

## 4. typ là JOSE header, không phải claim trong payload

Ví dụ JWT header:

~~~json
{
  "alg": "RS256",
  "kid": "signing-key-2026",
  "typ": "JWT"
}
~~~

Payload có thể chứa `iss`, `sub`, `aud`, `exp` và `scope`. `typ` nằm trong protected header. Một số token không có `typ`; RFC 7515 cho phép header này không xuất hiện.

### 4.1. Hành vi mặc định của JwtTypeValidator.jwt()

`JwtTypeValidator.jwt()` yêu cầu:

- `typ` bằng `JWT`; hoặc
- Header `typ` không xuất hiện.

Giá trị khác như `at+jwt`, `JOSE` hoặc một media type riêng sẽ không thỏa validator này. Đây là chủ đích: một decoder cần biết nó đang chấp nhận loại JWT nào.

### 4.2. Vì sao Spring chuyển type validation khỏi Nimbus?

Nimbus trước đây xác minh `typ` trong JOSE processor. Spring Security muốn gom việc xác minh header và claims vào cùng cơ chế `OAuth2TokenValidator`, để policy type có thể được thay đổi theo loại token và áp dụng nhất quán với các validator khác.

Spring Security 6.5 đưa `JwtTypeValidator` và `validateType(false)` vào để chuẩn bị. Spring Security 7 chuyển sang cách này làm mặc định:

~~~text
Trước migration:
  Nimbus JOSE processor
      |
      +-- kiểm tra chữ ký
      +-- kiểm tra typ
              |
              v
        Jwt claim validators

Sau migration:
  Nimbus JOSE processor
      |
      +-- kiểm tra chữ ký
      |
      v
  Jwt / OAuth2TokenValidator chain
      |
      +-- JwtTypeValidator
      +-- issuer/timestamp/audience/custom validators
~~~

### 4.3. Từng bước chuẩn bị trên Spring Security 6.5

Với token thông thường có `typ: JWT` hoặc không có `typ`, tắt Nimbus type verification và thêm `JwtTypeValidator.jwt()` vào chuỗi validator:

~~~java
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtIssuerValidator;
import org.springframework.security.oauth2.jwt.JwtTypeValidator;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

NimbusJwtDecoder decoder = NimbusJwtDecoder
    .withIssuerLocation(ISSUER)
    .validateType(false)
    .build();

decoder.setJwtValidator(
    JwtValidators.createDefaultWithValidators(
        new JwtIssuerValidator(ISSUER),
        JwtTypeValidator.jwt()));
~~~

Ở 6.5, `validateType(false)` chuyển trách nhiệm kiểm tra header sang validator. Dùng `createDefaultWithValidators` để giữ các standard validators và thêm issuer/type policy.

### 4.4. Hoàn tất migration trên Spring Security 7

Sau khi đã áp dụng bước chuẩn bị và test, có thể bỏ `validateType(false)` vì đây là default của Nimbus decoder trong 7. Các default validator factory đã bao gồm `JwtTypeValidator.jwt()`:

~~~java
NimbusJwtDecoder decoder = NimbusJwtDecoder
    .withIssuerLocation(ISSUER)
    .build();

decoder.setJwtValidator(
    JwtValidators.createDefaultWithIssuer(ISSUER));
~~~

Nếu có custom audience validator, ghép thêm nó vào default validator:

~~~java
OAuth2TokenValidator<Jwt> audienceValidator =
    new JwtClaimValidator<List<String>>(
        JwtClaimNames.AUD,
        audience -> audience.contains(API_AUDIENCE));

decoder.setJwtValidator(
    new DelegatingOAuth2TokenValidator<>(
        JwtValidators.createDefaultWithIssuer(ISSUER),
        audienceValidator));
~~~

Trong 7.x, `createDefaultWithIssuer` bao gồm issuer, timestamp và default type validation. Audience vẫn là policy riêng của resource server; đừng giả định chỉ khai báo issuer là đã kiểm tra `aud`.

## 5. Nếu issuer dùng typ tùy chỉnh

Một số hệ thống cũ dùng type như `JOSE`. Nếu đang dùng Nimbus `DefaultJOSEObjectTypeVerifier`, cần chuyển policy sang `JwtTypeValidator`.

Ví dụ trong bước chuẩn bị 6.5:

~~~java
NimbusJwtDecoder decoder = NimbusJwtDecoder
    .withIssuerLocation(ISSUER)
    .validateType(false)
    .build();

JwtTypeValidator typeValidator =
    new JwtTypeValidator("JOSE");
typeValidator.setAllowEmpty(true);

decoder.setJwtValidator(
    JwtValidators.createDefaultWithValidators(
        new JwtIssuerValidator(ISSUER),
        typeValidator));
~~~

`setAllowEmpty(true)` chỉ nên bật nếu issuer contract cho phép header `typ` vắng mặt. Nếu contract yêu cầu `JOSE`, hãy bỏ tùy chọn đó để header thiếu bị từ chối.

Khi chuyển lên 7.x, bỏ `validateType(false)` vì default đã là false; giữ custom `JwtTypeValidator` trong validator chain. Khi dùng default factory, bảo đảm validator type tùy chỉnh thay thế policy `JWT` mặc định theo hướng dẫn migration của phiên bản đang chạy. Không ghép hai type validators xung đột, ví dụ một validator chỉ chấp nhận `JWT` và validator khác chỉ chấp nhận `JOSE`.

### 5.1. Không nới type validation thành chấp nhận mọi giá trị

Tránh custom validator luôn trả success hoặc chấp nhận mọi chuỗi `typ`. Type validation tồn tại để decoder không nhầm một loại JWT với loại token khác có contract và mục đích khác. Nếu API cần nhiều token profile, dùng decoder/validator policy rõ ràng cho từng profile hoặc từng issuer.

## 6. RFC 9068 và typ at+jwt

RFC 9068 định nghĩa profile cho JWT Access Token. Một JWT Access Token theo profile này dùng `typ: at+jwt` và có các claim bắt buộc/semantics tương ứng, ví dụ `iss`, `sub`, `aud`, `exp`, `iat`, `jti`, `client_id` và `scope` khi được phát hành theo profile.

`JwtTypeValidator.jwt()` chỉ chấp nhận `JWT` hoặc không có `typ`, vì vậy không phải validator thích hợp để xác minh token có `typ: at+jwt`. Spring Security cung cấp `JwtValidators.createAtJwtValidator()` từ 6.5 để áp dụng RFC 9068 profile.

~~~java
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

NimbusJwtDecoder decoder = NimbusJwtDecoder
    .withIssuerLocation(ISSUER)
    .validateType(false)
    .build();

decoder.setJwtValidator(
    JwtValidators.createAtJwtValidator()
        .issuer(ISSUER)
        .audience(API_AUDIENCE)
        .clientId(OAUTH_CLIENT_ID)
        .build());
~~~

Trong Spring Security 6.5, giữ `validateType(false)` để Nimbus không từ chối `at+jwt` trước khi RFC 9068 validator chạy. Trong Spring Security 7, Nimbus type verification đã mặc định tắt nên có thể bỏ lời gọi này.

`AtJwtBuilder` yêu cầu cấu hình ít nhất `issuer`, `audience` và `clientId`. Chọn đúng client ID theo contract phát hành token. Không dùng builder này cho một JWT generic không tuân RFC 9068 rồi kỳ vọng nó chỉ kiểm tra `typ`.

### 6.1. Phân biệt JWT thông thường và RFC 9068 Access Token

| Thuộc tính | JWT generic | RFC 9068 JWT Access Token |
| --- | --- | --- |
| `typ` | Có thể `JWT` hoặc vắng mặt theo contract. | `at+jwt`. |
| `iss` | Theo profile/issuer contract. | Bắt buộc theo RFC 9068. |
| `aud` | Phải kiểm tra theo resource policy. | Bắt buộc và cần chứa resource server audience. |
| `client_id` | Không phải claim bắt buộc của mọi JWT generic. | Có trong profile. |
| `jti` | Có thể có hoặc không tùy profile. | Bắt buộc theo profile. |
| Validator | Default + policy của ứng dụng. | `createAtJwtValidator()` với issuer/audience/client ID. |

Không đổi `typ` của issuer thành `at+jwt` chỉ để làm test pass. Issuer phải thực sự phát hành Access Token theo RFC 9068 và tuân thủ claim contract tương ứng.

## 7. Validator mặc định thực sự kiểm tra điều gì?

Với cấu hình Resource Server tối thiểu dùng `issuer-uri`, Spring Security xác minh:

- Chữ ký JWT bằng key tin cậy từ JWK Set.
- Claim `iss` khớp issuer được cấu hình.
- `exp` và `nbf` theo timestamp validator.
- Clock skew mặc định 60 giây cho timestamp validation.

Các kiểm tra sau không tự động được bảo đảm chỉ bởi việc cấu hình `issuer-uri`:

- Audience của API hiện tại.
- Tenant, owner hoặc quyền trên object.
- Custom claim bắt buộc theo domain.
- Maximum token age dựa trên `iat`.
- Loại token đặc biệt ngoài default type policy.
- Scope authorization cho từng endpoint.

`JwtAuthenticationConverter` ánh xạ scope/claim thành `GrantedAuthority`; việc ánh xạ đó không thay thế claim validation. Ví dụ scope được ánh xạ thành authority `SCOPE_orders.read`, nhưng API vẫn phải cấu hình authorization rule để yêu cầu authority đó.

### 7.1. Các factory validator

| Factory/API | Ý nghĩa |
| --- | --- |
| `JwtValidators.createDefault()` | Standard validators không gắn issuer cụ thể. |
| `JwtValidators.createDefaultWithIssuer(issuer)` | Standard validators và issuer validator. |
| `JwtValidators.createDefaultWithValidators(...)` | Standard validators cộng các validator do ứng dụng cung cấp. |
| `JwtValidators.createAtJwtValidator()` | Builder cho RFC 9068 JWT Access Token profile. |
| `JwtTimestampValidator` | Kiểm tra cửa sổ `nbf`/`exp` và clock skew. |
| `JwtIssuerValidator` | Kiểm tra claim `iss`. |
| `JwtTypeValidator.jwt()` | Yêu cầu header `typ` là `JWT` hoặc vắng mặt. |
| `JwtClaimValidator` | Kiểm tra một claim theo predicate. |

Từ Spring Security 7, các factory `createDefault...` bao gồm `JwtTypeValidator.jwt()`. Vì vậy, nếu custom code trước đây chỉ dùng `JwtValidators.createDefaultWithIssuer`, sau migration 7 nó cũng có type validation theo default policy.

### 7.2. Audience không tự được thêm bởi issuer validator

`iss` trả lời ai phát hành token; `aud` trả lời token được gửi tới resource nào. Một token có issuer hợp lệ nhưng audience là `inventory-api` không được tự động chấp nhận ở `orders-api`.

Ví dụ validator:

~~~java
OAuth2TokenValidator<Jwt> audienceValidator =
    new JwtClaimValidator<List<String>>(
        JwtClaimNames.AUD,
        audience -> audience.contains("orders-api"));

OAuth2TokenValidator<Jwt> validators =
    new DelegatingOAuth2TokenValidator<>(
        JwtValidators.createDefaultWithIssuer(ISSUER),
        audienceValidator);

decoder.setJwtValidator(validators);
~~~

Với Spring Boot version có hỗ trợ `spring.security.oauth2.resourceserver.jwt.audiences`, có thể khai báo audience ở configuration. Khi dùng custom decoder hoặc custom validator chain, xác nhận property đó còn được áp dụng; một custom `JwtDecoder` có thể thay thế Boot auto-configuration.

### 7.3. setJwtValidator thay thế chuỗi hiện tại

Đây là lỗi migration thường gặp:

~~~java
// RỦI RO: chỉ còn audience validator nếu không tự ghép default validators.
decoder.setJwtValidator(audienceValidator);
~~~

Cách giữ default:

~~~java
decoder.setJwtValidator(
    new DelegatingOAuth2TokenValidator<>(
        JwtValidators.createDefaultWithIssuer(ISSUER),
        audienceValidator));
~~~

Nếu bạn tự tạo `DelegatingOAuth2TokenValidator` chỉ với `JwtTimestampValidator` và `JwtIssuerValidator`, các validator khác không tự xuất hiện. Hãy viết rõ danh sách validator cần thiết và test từng điều kiện.

## 8. Không nhầm validator với authority converter

~~~text
JwtDecoder
  |
  +-- signature verification
  +-- issuer / timestamp / typ / audience / custom validation
  |
  v
Validated Jwt
  |
  v
JwtAuthenticationConverter
  |
  +-- scope -> SCOPE_...
  +-- custom roles -> ROLE_...
  |
  v
Authentication
  |
  v
Authorization rules
~~~

Một token có `scope: "orders.read"` có thể được ánh xạ thành `SCOPE_orders.read`. Nhưng nếu token có audience sai, decoder phải từ chối trước khi authority converter được dùng. Không cố sửa audience bằng converter hoặc map role để bù cho validator bị thiếu.

## 9. Cấu hình validator có thể khác giữa Servlet và WebFlux

Ý nghĩa của algorithm allowlist, `typ` và claims validator giống nhau; interface decoder khác nhau:

| Stack | Decoder interface | Nimbus implementation |
| --- | --- | --- |
| Servlet | `JwtDecoder` | `NimbusJwtDecoder` |
| WebFlux | `ReactiveJwtDecoder` | `NimbusReactiveJwtDecoder` |

Reactive decoder có builder và các API tương tự để cấu hình trusted JWS algorithms, type validation và validator chain. Không dùng Servlet `JwtDecoder` blocking trong reactive request pipeline chỉ để tái sử dụng cấu hình.

Ví dụ Reactive JWT decoder:

~~~java
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusReactiveJwtDecoder;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;

ReactiveJwtDecoder reactiveDecoder() {
    NimbusReactiveJwtDecoder decoder =
        NimbusReactiveJwtDecoder
            .withJwkSetUri(JWKS_URI)
            .jwsAlgorithm(SignatureAlgorithm.RS256)
            .build();

    decoder.setJwtValidator(
        JwtValidators.createDefaultWithIssuer(ISSUER));
    return decoder;
}
~~~

Nếu cần audience, ghép `JwtClaimValidator` với default validator tương tự Servlet. Nếu token theo RFC 9068, dùng `createAtJwtValidator()` và bảo đảm Nimbus type verification không chặn `at+jwt` trước khi validator profile chạy.

## 10. Quy trình migration theo từng bước

### Bước 1: Chụp lại contract token hiện tại

Lấy mẫu token từ từng issuer/client/resource trong môi trường test hoặc staging. Ghi lại các trường đã xác minh:

- JOSE `alg`, `kid`, `typ`.
- `iss`, `aud`, `exp`, `nbf`, `iat`.
- `client_id`, `jti`, `scope`/`scp` nếu profile sử dụng.
- JWK `kty`, `use`, `key_ops`, `alg` và key rotation overlap.

Không log hoặc đưa raw token production vào tài liệu migration. Dùng token test đã ký bằng key test.

### Bước 2: Xác định đường tạo decoder

Tìm tất cả:

- `spring.security.oauth2.resourceserver.jwt.issuer-uri`.
- `jwk-set-uri` và `jws-algorithms`.
- `JwtDecoders.fromIssuerLocation`.
- `NimbusJwtDecoder.withIssuerLocation` và `withJwkSetUri`.
- `jwtProcessorCustomizer`, `setJWSTypeVerifier`, `validateType`.
- `setJwtValidator`, `JwtValidators` và custom `OAuth2TokenValidator`.

Một custom decoder có thể thay thế auto-configuration, nên không chỉ đọc YAML để kết luận policy đang chạy.

### Bước 3: Chuẩn bị typ trên Spring Security 6.5

Đặt `validateType(false)` và thêm validator type phù hợp vào validator chain. Với JWT generic, dùng `JwtTypeValidator.jwt()`. Với type tùy chỉnh, dùng `new JwtTypeValidator("...")`. Với RFC 9068, dùng `createAtJwtValidator()`.

### Bước 4: Chốt allowlist algorithm

Đối chiếu issuer signing configuration và JWK Set. Cấu hình RS256/RS512/ES256 hoặc tập algorithm tối thiểu được duyệt. Không mở allowlist để tránh lỗi test.

### Bước 5: Bổ sung validators còn thiếu

Đảm bảo có issuer, timestamp, type, audience và policy domain cần thiết. Kiểm tra kỹ việc gọi `setJwtValidator` vì nó thay thế chain hiện tại.

### Bước 6: Chạy test trước khi đổi major version

Trên 6.5, chạy toàn bộ test signed JWT với type validator mới. Điều chỉnh issuer token profile hoặc decoder policy nếu token thực tế khác contract.

### Bước 7: Nâng lên Spring Security 7

Sau khi chuẩn bị:

- Bỏ `validateType(false)` nếu không có lý do đặc biệt vì 7.x đã mặc định tắt Nimbus type verification.
- Bỏ việc thêm tường minh `JwtTypeValidator.jwt()` nếu đang dùng default validator factory.
- Giữ custom type validator khi issuer dùng type riêng.
- Xác nhận validator factory mới vẫn giữ audience/domain checks.
- Kiểm tra các custom Nimbus `jwtProcessorCustomizer` có đang sửa type verifier cũ hay không; chuyển logic đó sang `JwtTypeValidator` hoặc custom `OAuth2TokenValidator`.

### Bước 8: So sánh behavior trước và sau

Chạy cùng tập signed tokens trên decoder 6.5 và decoder 7.x. Với mỗi token, ghi lại pass/fail và nguyên nhân. Các khác biệt phải được giải thích bằng policy migration, không chấp nhận việc test chỉ xanh do validator bị bỏ.

## 11. Test algorithm, typ và validator

### 11.1. Test algorithm allowlist

Tạo token ký bằng từng thuật toán được chấp nhận và một token ký bằng thuật toán không nằm trong allowlist.

| Token | Kỳ vọng |
| --- | --- |
| RS256 khi allowlist RS256 | Signature có thể xác minh nếu key phù hợp. |
| ES256 khi chỉ allowlist RS256 | Từ chối. |
| RS512 khi allowlist RS256 và RS512 | Signature có thể xác minh nếu key phù hợp. |
| `alg: none` | Từ chối. |
| Algorithm được phép nhưng key type không phù hợp | Từ chối. |
| `kid` không có trong trusted JWK Set | Không thể xác minh; từ chối. |

Đừng chỉ thay header `alg` trên token đã ký. Thay header làm chữ ký không còn hợp lệ; test algorithm nên tạo token mới và ký thật bằng key phù hợp.

### 11.2. Test type header

Với default `JwtTypeValidator.jwt()`:

| JOSE `typ` | Kỳ vọng |
| --- | --- |
| `JWT` | Qua type validator nếu các kiểm tra khác pass. |
| Không có `typ` | Qua type validator theo policy mặc định. |
| `at+jwt` | Bị default JWT type validator từ chối; dùng RFC 9068 validator nếu đây là profile được hỗ trợ. |
| `JOSE` | Bị từ chối trừ khi decoder được cấu hình type tùy chỉnh. |
| Giá trị tùy ý | Bị từ chối. |

### 11.3. Test claims validator

| Claim | Token test | Kỳ vọng |
| --- | --- | --- |
| `iss` | Issuer đúng | Pass. |
| `iss` | Issuer khác | Fail. |
| `aud` | Chứa audience API | Pass. |
| `aud` | Chỉ chứa audience API khác | Fail. |
| `exp` | Đã hết hạn ngoài clock skew | Fail. |
| `nbf` | Chưa đến thời điểm hiệu lực ngoài clock skew | Fail. |
| `iat` | Nằm trong tương lai/quá cũ | Theo custom policy nếu có. |
| `scope` | Có scope cần thiết | Converter tạo authority; authorization policy quyết định. |

### 11.4. Dùng signed JWT integration test

`mockJwt()` trong MockMvc/WebTestClient tạo Authentication giả đã xác thực. Nó hữu ích để test authorization, nhưng không kiểm tra chữ ký, thuật toán, `typ` hoặc decoder validators thật.

Để kiểm tra migration:

1. Tạo RSA/EC test key pair.
2. Ký JWT test với protected header và claims được kiểm soát.
3. Cấu hình decoder thật dùng public key hoặc JWK Set test.
4. Gọi `JwtDecoder.decode(token)` hoặc gửi Bearer token qua full Resource Server filter chain.
5. Assert token hợp lệ được chấp nhận và từng biến thể sai bị từ chối.

Không dùng token unsigned hoặc chỉ sửa chuỗi compact JWT để test decoder production.

### 11.5. Test custom validators không bị mất

Viết ít nhất một token sai audience nhưng đúng chữ ký/issuer/time/type. Token này phải bị từ chối. Test này phát hiện lỗi gọi `setJwtValidator(audienceValidator)` làm mất default validator hoặc migration bỏ audience rule.

## 12. Những lỗi migration thường gặp

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Cho rằng Spring Security 7 đổi default algorithm khỏi RS256 | Cấu hình sai hoặc mở allowlist không cần thiết | Xác nhận RS256 và issuer signing algorithm thực tế |
| Tin `alg` trong header để tự chọn policy | Algorithm confusion | Cấu hình allowlist độc lập |
| Giữ `DefaultJOSEObjectTypeVerifier` trong `jwtProcessorCustomizer` | Type policy vẫn nằm ở Nimbus cũ, khó theo validator chain | Chuyển sang `JwtTypeValidator` |
| Tắt Nimbus type check nhưng quên thêm validator | Không còn type validation theo ý muốn | Thêm `JwtTypeValidator` hoặc RFC 9068 validator |
| Dùng `JwtTypeValidator.jwt()` cho `at+jwt` | JWT Access Token RFC 9068 bị từ chối | Dùng `createAtJwtValidator()` |
| Chấp nhận mọi `typ` để tránh lỗi | Token profile khác có thể bị nhầm lẫn | Allowlist type rõ ràng |
| Gọi `setJwtValidator` với một validator mới duy nhất | Mất issuer/timestamp/type defaults | Ghép với `createDefaultWithIssuer` hoặc factory phù hợp |
| Cho rằng `issuer-uri` tự kiểm tra audience | Token dành cho API khác vẫn có thể qua issuer check | Thêm audience validator/property |
| Nhầm scope converter với scope validation | Authentication có authority nhưng route chưa được bảo vệ | Thêm authorization rules |
| Chỉ test bằng `mockJwt()` | Không test decoder thật | Dùng signed JWT integration test |
| Chỉ test token hợp lệ | Không phát hiện regression từ token sai | Test sai alg, typ, iss, aud, exp, nbf |
| Dùng custom decoder nhưng quên cấu hình validator | Boot defaults có thể không còn áp dụng | Gắn explicit validator chain |

## 13. Checklist trước khi hoàn tất migration

- [ ] Đã xác định phiên bản Spring Security/Spring Boot đang chạy và phiên bản đích.
- [ ] Đã kiểm tra đường tạo `JwtDecoder` hoặc `ReactiveJwtDecoder`.
- [ ] Đã xác nhận issuer signing algorithm và JWK Set.
- [ ] Allowlist JWS algorithm chỉ gồm thuật toán được duyệt.
- [ ] Không dựa vào `alg` do token cung cấp để quyết định trust policy.
- [ ] Đã kiểm tra JOSE header `typ` của token thực tế.
- [ ] Đã chuẩn bị `JwtTypeValidator` trên Spring Security 6.5.
- [ ] Đã xử lý `at+jwt` bằng RFC 9068 validator nếu issuer dùng profile này.
- [ ] Đã loại bỏ custom Nimbus type verifier cũ hoặc chuyển logic sang validator.
- [ ] Validator chain vẫn kiểm tra issuer và timestamp.
- [ ] Audience của Resource Server được kiểm tra rõ ràng.
- [ ] Custom validators không bị mất khi gọi `setJwtValidator`.
- [ ] Scope converter và authorization rules vẫn hoạt động.
- [ ] Signed JWT tests bao gồm pass và fail cases.
- [ ] Test suite không chỉ dùng mock Authentication.
- [ ] Đã so sánh kết quả decoder trên phiên bản trước và sau migration.

**Ghi nhớ:** `alg` quyết định cách xác minh chữ ký và `RS256` vẫn là mặc định của `NimbusJwtDecoder`; `typ` là JOSE header và việc kiểm tra nó chuyển sang `JwtTypeValidator` trong Spring Security 7; các default validator factory trên 7.x thêm `JwtTypeValidator.jwt()` để chấp nhận `JWT` hoặc header vắng mặt. Với RFC 9068, dùng `createAtJwtValidator()` cho `at+jwt`. Khi thêm audience hoặc custom policy, luôn giữ issuer/timestamp/type validators và kiểm tra decoder bằng JWT có chữ ký thật.

## Tài liệu tham khảo

- [Spring Security 6.5 — OAuth 2.0 Migration to 7.0](https://docs.spring.io/spring-security/reference/6.5/migration-7/oauth2.html).
- [Spring Security 7.0 — OAuth 2.0 Migrations](https://docs.spring.io/spring-security/reference/7.0/migration/servlet/oauth2.html).
- [Spring Security — JWT Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html).
- [Spring Security — Reactive JWT Resource Server](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html).
- [Spring Security API — JwtTypeValidator](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/jwt/JwtTypeValidator.html).
- [Spring Security API — JwtValidators.AtJwtBuilder](https://docs.spring.io/spring-security/reference/7.0/api/java/org/springframework/security/oauth2/jwt/JwtValidators.AtJwtBuilder.html).
- [Spring Security API — NimbusJwtDecoder.JwkSetUriJwtDecoderBuilder](https://docs.spring.io/spring-security/reference/7.0/api/java/org/springframework/security/oauth2/jwt/NimbusJwtDecoder.JwkSetUriJwtDecoderBuilder.html).
- [RFC 7515 — JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515).
- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517).
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519).
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725).
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068).
