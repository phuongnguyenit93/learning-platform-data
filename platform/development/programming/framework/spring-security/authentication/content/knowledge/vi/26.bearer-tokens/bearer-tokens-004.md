# Kiểm tra chữ ký, thuật toán, issuer, audience và thời hạn JWT

Một **JWT (JSON Web Token)** có thể đọc được mà không cần khóa bí mật. Vì vậy việc giải mã phần payload và nhìn thấy các trường `sub`, `scope`, `iss` hoặc `exp` **không chứng minh** token đáng tin. Khi API nhận một **Bearer access token** dạng JWT, nó phải kiểm tra **chữ ký và khóa xác minh**, **thuật toán được cho phép**, **issuer**, **audience**, **thời hạn** và các điều kiện nghiệp vụ phù hợp **trước khi** dùng claims để tạo danh tính/quyền truy cập.

Trong hệ Spring Security Servlet, công việc này thường do OAuth2 Resource Server thực hiện qua `BearerTokenAuthenticationFilter`, `JwtAuthenticationProvider` và `JwtDecoder`. Sau khi token được xác minh hợp lệ, Spring Security chuyển claims phù hợp thành `Authentication` và `GrantedAuthority`; bước authorization mới quyết định API cho phép thao tác nào.

Bài tập trung đúng năm nhóm kiểm tra: **signature, algorithm, issuer, audience, time**. Ví dụ sử dụng Spring Boot 3.x, Spring Security 6.x, Java 17+ và token do một authorization server/IdP đáng tin cậy phát hành. Tên miền, audience, khóa và claims trong bài đều là minh họa; không có private key hay access token thật.

## 1. JWT được chuyển vào API thế nào?

Trong OAuth2, một Resource Server thường nhận access token qua HTTP:

~~~http
GET /api/orders/ping HTTP/1.1
Host: api.example.test
Authorization: Bearer eyJ...<token-test>...abc
~~~

**Bearer** nghĩa là bên nắm giữ token có thể xuất trình nó để yêu cầu quyền; nếu token bị lộ, người khác có thể dùng lại cho tới khi nó hết hiệu lực hoặc hệ thống chặn được. Giao thức truyền token phải được bảo vệ bằng HTTPS; không đặt token vào URL, log hoặc commit.

Một **JWS Compact JWT** có ba đoạn Base64url nối bằng dấu chấm:

~~~text
BASE64URL(protected-header).BASE64URL(payload).BASE64URL(signature)
                 ①                  ②                 ③
~~~

- **Header được bảo vệ** chứa các tham số như `alg` (thuật toán ký), `kid` (gợi ý chọn khóa) và tùy trường hợp `typ`.
- **Payload** là tập claims như `iss`, `sub`, `aud`, `iat`, `nbf`, `exp`, `scope`.
- **Signature/MAC** được tính trên hai đoạn đầu theo thuật toán đã chọn và khóa đúng loại. Bất kỳ sửa đổi có ý nghĩa nào đối với header/payload đều phải khiến kiểm tra chữ ký thất bại.

Ví dụ hai phần JSON **chỉ để học cấu trúc**, không phải token đã ký:

~~~json
{
  "alg": "RS256",
  "kid": "key-2026-01",
  "typ": "JWT"
}
~~~

~~~json
{
  "iss": "https://auth.example.test/realms/training",
  "sub": "user-123",
  "aud": ["urn:orders-api"],
  "iat": 1793923200,
  "nbf": 1793923200,
  "exp": 1793923500,
  "scope": "orders.read"
}
~~~

Trong fixture này, `iat` và `nbf` ở 2026-11-06 00:00:00 UTC, `exp` ở 00:05:00 UTC cùng ngày. Những con số chỉ có nghĩa khi test tại thời điểm tương ứng. Khi chạy sau thời điểm hết hạn, **validator phải từ chối**, dù chữ ký đúng. Claims được in ra là **dữ liệu chưa đáng tin cho đến khi các kiểm tra thành công**.

### JWT khác gì access token?

- **JWT** là một định dạng token, có thể dùng làm access token, ID token hoặc token nội bộ. Không phải access token nào cũng là JWT; một access token dạng opaque cần introspection với authorization server.
- **JWS** cung cấp toàn vẹn/xác thực nguồn phát hành bằng chữ ký số hoặc MAC. JWS không tự mã hóa nội dung payload.
- **JWE** là định dạng token được mã hóa và có quy trình giải mã/kiểm tra khác; không cố đưa JWE năm đoạn vào decoder JWS ba đoạn rồi suy diễn kết quả.
- **OIDC ID token** dành cho client xác định phiên đăng nhập người dùng; API không nên mặc định chấp nhận ID token như access token chỉ vì có chữ ký hợp lệ và cùng issuer. Cần audience, token type/use và policy riêng cho access token.

## 2. Chuỗi xác minh từ Bearer token đến Authentication

~~~text
Client gửi Authorization: Bearer <JWT>
            │
            ▼
BearerTokenAuthenticationFilter
            │ tách raw bearer token
            ▼
BearerTokenAuthenticationToken
            │
            ▼
JwtAuthenticationProvider
            │ gọi JwtDecoder
            ▼
NimbusJwtDecoder
    ├─ phân tích JWS, kiểm tra cấu trúc/typ theo decoder
    ├─ kiểm tra "alg" thuộc allowlist và kiểu khóa phù hợp
    ├─ chọn khóa đáng tin từ JWKS cố định, thường dựa trên "kid"
    ├─ xác minh chữ ký số/MAC
    └─ chạy claim validators
         ├─ iss == issuer đã tin cậy
         ├─ aud chứa resource/API identifier được chấp nhận
         ├─ exp chưa quá hạn (theo clock skew đã định)
         ├─ nbf chưa nằm trong tương lai vượt quá lệch cho phép
         └─ các claim bổ sung nếu ứng dụng yêu cầu
            │ tất cả PASS
            ▼
JwtAuthenticationToken (đã xác thực)
            │ scopes → authorities, ví dụ SCOPE_orders.read
            ▼
AuthorizationFilter
    ├─ đủ quyền: vào controller
    └─ thiếu quyền: chặn truy cập
~~~

Các thành phần cụ thể có thể thay đổi theo phiên bản/cấu hình, nhưng phải giữ thứ tự bảo mật về mặt logic: **chỉ sử dụng các claims để xác thực và cấp quyền sau khi JWS và validators được kiểm tra thành công**.

Một JWT đúng chữ ký nhưng sai `aud` phải bị từ chối; JWT đúng `iss` nhưng hết hạn cũng phải bị từ chối; JWT chưa từng bị sửa đổi nhưng ký bằng khóa **không thuộc issuer** cũng không hợp lệ.

## 3. Xác minh chữ ký và chọn khóa tin cậy

### 3.1. Chữ ký chứng minh điều gì?

Với `RS256` (RSA + SHA-256):

- Authorization Server giữ **private key** để ký token.
- Resource Server lấy **public key** tương ứng từ nguồn đã xác thực/định cấu hình.
- Nếu chữ ký hợp lệ, validator biết token chưa bị thay đổi sau khi được ký bởi **khóa tương ứng**.
- Để kết luận “token đến từ issuer mà API tin”, Resource Server còn phải biết **khóa đó thực sự thuộc issuer được tin**. Chữ ký bằng một public key tùy ý gửi kèm request không đủ.

Với HMAC (`HS256`), việc ký và xác minh dùng **cùng một secret**; thiết kế có nhiều Resource Server cần cân nhắc vì bên xác minh biết secret cũng có khả năng tạo token mới. Với chữ ký bất đối xứng như `RS256` hoặc `ES256`, API chỉ cần public key.

### 3.2. JWKS, JWK và kid

Một authorization server thường công khai bộ khóa dạng **JWKS** (JSON Web Key Set) qua URL HTTPS đã biết, ví dụ:

~~~text
https://auth.example.test/realms/training/protocol/openid-connect/certs
~~~

Response JWKS có thể chứa nhiều JWK công khai:

~~~json
{
  "keys": [
    {
      "kty": "RSA",
      "kid": "key-2026-01",
      "use": "sig",
      "alg": "RS256",
      "n": "<base64url-RSA-modulus>",
      "e": "AQAB"
    }
  ]
}
~~~

Đoạn trên chỉ minh họa cấu trúc, không chứa khóa RSA thật để verify. `kid` là **gợi ý chọn** một trong những khóa đã lấy từ **JWKS tin cậy**; nó **không tự chứng minh khóa đáng tin**.

Nguyên tắc xác minh an toàn:

1. Cấu hình issuer/JWKS endpoint từ cấu hình ứng dụng hoặc metadata được lấy qua **issuer đã tin**, không tự lấy URL từ request.
2. Chỉ chọn khóa có loại, mục đích và thuật toán phù hợp policy.
3. Dùng `kid` để tìm khóa trong JWKS **của issuer đó**, không dùng `kid` như đường dẫn file, tên bảng hay URL.
4. Xác minh chữ ký và toàn bộ validation claims.
5. Khi issuer xoay khóa, cho phép hệ thống cập nhật JWKS qua nguồn tin cậy và cache có chính sách hợp lý; test token ký bằng khóa cũ/mới trong cửa sổ chuyển tiếp.

**Chống giả mạo đường lấy khóa:** các header như `jku`, `jwk` hoặc `x5u` do token gửi tới là dữ liệu từ phía người gọi. Không tự động tải URL trong đó hay tin khóa public key nhúng trong token. Nếu cấu hình một issuer đáng tin ở `https://auth.example.test`, không chấp nhận token chuyển `jku` sang domain của attacker chỉ vì chữ ký bằng khóa bên đó là hợp lệ.

**Nếu `kid` không tìm thấy:** thường token không được xác minh thành công; cần phân biệt issuer đang xoay key/caching JWKS với token giả. Không “fallback” sang khóa bất kỳ do caller cung cấp.

### 3.3. Vì sao kiểm tra chữ ký chưa đủ?

Một attacker có thể có tài khoản trên chính issuer và lấy access token **cho ứng dụng khác**. Token đó vẫn được issuer ký hợp lệ nhưng không được dùng để gọi API hiện tại nếu `aud` sai. Một token của tenant/issuer khác cũng có thể được ký bằng khóa hợp lệ **của hệ thống khác** nhưng không nằm trong ranh giới tin cậy của API.

Đây là lý do kiểm tra chữ ký, issuer và audience phải đi cùng nhau. Cấp quyền chỉ dựa trên `sub` hoặc `scope` sau khi parse JWT là sai.

## 4. Thuật toán ký: chỉ chấp nhận allowlist

JWT protected header có trường `alg`. Đây là giá trị do người gửi token lựa chọn, nên **không được để token quyết định chính sách an toàn**.

| Thuật toán | Loại khóa | Lưu ý |
| --- | --- | --- |
| `RS256` | RSA private/public | Thường dùng cho JWT của authorization server; API chỉ cần public key |
| `ES256` | ECDSA P-256 private/public | Yêu cầu key type/curve và verifier đúng |
| `PS256` | RSA-PSS private/public | Cần cấu hình cho cả issuer và Resource Server |
| `HS256` | HMAC shared secret | Chỉ dùng khi có thiết kế quản lý shared secret phù hợp |
| `none` | Không có chữ ký | Không được chấp nhận cho Bearer access token yêu cầu xác minh chữ ký |

Các thuật toán khác có thể hợp lệ theo chuẩn nhưng chỉ được cho phép sau khi đánh giá chính sách, key type và hỗ trợ thư viện. **Không bật mọi algorithm cho tiện**.

### Algorithm confusion

Trong các thư viện/đoạn code triển khai yếu, attacker có thể sửa header từ `RS256` sang `HS256` và khiến verifier dùng RSA public key như HMAC secret, hoặc đổi sang `none` để bỏ kiểm tra chữ ký. RFC 8725 mô tả các lỗi này.

Cách phòng tránh:

- Cố định **allowlist thuật toán** theo issuer.
- Gắn thuật toán với **loại khóa** tương ứng; không cho cùng key vừa dùng như RSA public key vừa là HMAC secret.
- Dùng một thư viện JWT có kiểm tra JWS chuẩn; không tự viết `verify` bằng cách so text Base64.
- Không tin claims hoặc quyền nếu token không qua signature verification.
- Test token bị sửa `alg` sang `none`/`HS256`/thuật toán không được cấu hình và bảo đảm bị từ chối.

Ở Spring Security Resource Server với `NimbusJwtDecoder`, tài liệu cho biết mặc định tin cậy `RS256` khi dùng cấu hình tiêu chuẩn, nhưng ứng dụng nên chủ động kiểm soát chính sách thuật toán nếu issuer sử dụng algorithm khác. Cần xác minh thuật toán thực tế của IdP trước khi thay đổi.

## 5. Issuer: token do ai phát hành?

Claim `iss` chỉ định issuer. Giá trị phải khớp **đúng issuer mà API chấp nhận**. Ví dụ:

~~~json
{
  "iss": "https://auth.example.test/realms/training"
}
~~~

API đặt kỳ vọng:

~~~text
EXPECTED_ISSUER=https://auth.example.test/realms/training
~~~

Không chấp nhận một token với `iss=https://auth.attacker.test` chỉ vì token được chính attacker ký bằng khóa công khai nào đó. Resource Server phải biết **issuer → JWKS/khóa tin cậy** từ cấu hình.

Các điểm cần chú ý:

- So sánh theo giá trị issuer chuẩn do IdP công bố, không tự bỏ path realm/tenant, thay hostname hoặc xóa dấu `/` cuối nếu không có hợp đồng rõ ràng.
- `https://auth.example.test/realms/training` và `https://auth.example.test/realms/other` là hai issuer khác nhau.
- Khi dùng OIDC/OAuth Authorization Server metadata, kiểm tra metadata thuộc issuer dự kiến và JWKS endpoint được lấy qua cơ chế tin cậy.
- Trong hệ nhiều tenant/issuer, lập **danh sách issuer được chấp nhận** và cấu hình authentication manager/decoder tương ứng cho từng issuer. Không tự tin một issuer mới chỉ dựa vào giá trị `iss` chưa được xác minh.

**Cần phân biệt:** claim `sub` nhận diện subject ở phạm vi issuer; khi lưu user cross-issuer nên định danh bằng cặp (`iss`, `sub`), không chỉ `sub`. Một JWT đúng issuer chưa chắc dành cho API đang phục vụ.

## 6. Audience: token dành cho API nào?

Claim `aud` nhận diện người nhận dự kiến. Theo JWT, nó có thể là **một string** hoặc **mảng string**; Spring Security cung cấp `jwt.getAudience()` để truy cập dưới dạng danh sách.

Ví dụ API Orders yêu cầu:

~~~text
EXPECTED_AUDIENCE=urn:orders-api
~~~

Token có:

~~~json
{"aud":["urn:orders-api","urn:reporting-api"]}
~~~

có thể thỏa điều kiện audience của API Orders vì danh sách **chứa đúng** `urn:orders-api` (nếu policy cho phép nhiều audience). Token sau phải bị từ chối:

~~~json
{"aud":"urn:payments-api"}
~~~

Dù chữ ký, issuer và thời hạn đều hợp lệ, token dành cho Payments API không được dùng để gọi Orders API.

**Audience không phải scope**:

| Claim / khái niệm | Trả lời câu hỏi | Ví dụ |
| --- | --- | --- |
| `iss` | Ai phát hành token? | `https://auth.example.test/realms/training` |
| `aud` | Token được phát hành cho resource/API nào? | `urn:orders-api` |
| `sub` | Token nói về subject nào? | `user-123` |
| `scope` hoặc `scp` | Quyền được cấp trong phạm vi phù hợp | `orders.read` |
| `client_id` / `azp` tùy profile | Ứng dụng OAuth client nào nhận/thực hiện yêu cầu? | `web-client` |

`client_id` hoặc `azp` **không tự thay `aud`**. `scope=orders.read` cũng không làm token đúng audience nếu token được phát hành cho API khác. Với OAuth2 Resource Server, một chính sách thường là **đúng issuer + đúng audience + còn hạn + đủ authority**.

### Cross-JWT confusion và ID token

Một OIDC ID token có thể cùng `iss`, ký bằng cùng JWK, chứa `sub` và chưa hết hạn. Nhưng `aud` thường dành cho **OIDC client ID**, khác với audience của API. API phải từ chối token sai mục đích. Nếu kiến trúc có nhiều loại token, cần kiểm tra thêm token type/profile như `typ`, claim bắt buộc và cách issuer phân biệt ID token/access token; một chữ ký đúng không đủ để chống dùng lẫn loại token.

## 7. Thời hạn: exp, nbf, iat, clock skew

Trong JWT, các claim thời gian thường dùng **NumericDate**: số giây từ Unix epoch UTC. Đây **không phải millisecond** như `System.currentTimeMillis()` của Java.

| Claim | Ý nghĩa | Kiểm tra |
| --- | --- | --- |
| `exp` (*expiration time*) | Token không được sử dụng từ thời điểm hết hạn trở đi | Từ chối khi đã hết hạn, xét clock skew cho phép |
| `nbf` (*not before*) | Không chấp nhận token trước thời điểm bắt đầu hiệu lực | Từ chối nếu “chưa đến giờ”, xét skew |
| `iat` (*issued at*) | Token được phát hành lúc nào | Hữu ích để kiểm tra tính hợp lý/tuổi tối đa theo policy; **không tự thay `exp`** |

Ví dụ thời gian của một fixture test:

~~~text
iat = nbf = 1793923200  → 2026-11-06 00:00:00 UTC
exp =       1793923500  → 2026-11-06 00:05:00 UTC

T=00:02:00 UTC: có hiệu lực về thời gian
T=00:06:00 UTC: hết hạn
T=23:59:00 ngày trước: chưa đến nbf
~~~

Bảng trên giả sử **không nới thời gian bằng clock skew**. Khi cấu hình skew, các biên kiểm tra có thể được cho phép lệch một khoảng nhỏ để bù đồng hồ giữa IdP và API. Spring Security `JwtTimestampValidator` hỗ trợ skew; tài liệu mô tả mặc định phổ biến là 60 giây cho Resource Server. Không tăng skew lên nhiều phút/giờ chỉ để che lỗi đồng bộ thời gian, vì điều đó kéo dài cửa sổ dùng token đã hết hạn hoặc nhận token chưa hiệu lực.

Ví dụ về kiểm tra:

- Token còn `exp` 2 phút và `nbf` đã qua: hợp lệ về **thời gian**, còn phải kiểm tra signature, issuer, audience.
- Token `exp` đã qua 10 phút: không được chấp nhận chỉ vì JWT có `scope` đúng.
- Token `nbf` ở 5 phút trong tương lai: từ chối theo chính sách (với skew thông thường).
- `iat` rất xa trong quá khứ: không tự là lỗi tiêu chuẩn nếu `exp` còn hiệu lực, nhưng ứng dụng có thể áp chính sách **max token age / max lifetime** riêng.
- Token không có `exp`: mức bắt buộc phụ thuộc token profile/chính sách issuer. Với access token bảo mật, nên yêu cầu `exp` và tuổi thọ hữu hạn; nếu yêu cầu bắt buộc thì thêm validator/kiểm thử phù hợp.

**Các phép kiểm tra trên dùng đồng hồ ở Resource Server**, vì vậy container cần đồng bộ NTP. Nếu log ghi thời gian theo múi giờ local, quy đổi đúng UTC trước khi kết luận rằng token hết hạn sai.

### Mức độ tin cậy của iat

`iat` không có nghĩa “cấp quyền từ thời điểm này”. Một issuer có thể phát hành JWT với `iat` cũ/hiện tại; application cần chính sách riêng nếu muốn chặn token quá cũ, hạn chế TTL hoặc yêu cầu `iat <= now + skew`. Không tự xem `iat` là số millisecond, không dùng một phép kiểm tra `iat` tự viết thay cho validator `exp`/`nbf` của Spring.

## 8. Cấu hình Spring Boot 3.x + Spring Security 6.x

Cách thông dụng nhất là cấu hình ứng dụng làm **OAuth2 Resource Server nhận JWT**, dùng issuer/JWKS của Authorization Server thật. Spring Security sẽ xử lý JWS, signature, timestamp và issuer; Spring Boot cho phép khai báo audience cần khớp.

### 8.1. Dependencies

Trong `build.gradle` Groovy DSL của project Spring Boot đã quản lý version bằng BOM/plugin:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
~~~

Starter OAuth2 Resource Server mang các dependency JWT/JOSE phù hợp theo Spring Boot; không cần tự quản version Nimbus nếu không có yêu cầu đặc biệt. Ví dụ bên dưới là các phần được đặt vào một project đã có Gradle wrapper, Java 17+ và Spring Boot plugin; chúng không tự tạo hệ thống IdP hay ký token.

### 8.2. application.properties

Tệp `src/main/resources/application.properties`:

~~~properties
spring.security.oauth2.resourceserver.jwt.issuer-uri=https://auth.example.test/realms/training
spring.security.oauth2.resourceserver.jwt.jwk-set-uri=https://auth.example.test/realms/training/protocol/openid-connect/certs
spring.security.oauth2.resourceserver.jwt.audiences[0]=urn:orders-api
spring.security.oauth2.resourceserver.jwt.jws-algorithms[0]=RS256
~~~

Giải thích:

1. **`issuer-uri`** là issuer cần được xác minh theo `iss`. Spring Security sử dụng thông tin này để cấu hình issuer validator.
2. **`jwk-set-uri`** là endpoint JWKS lấy public keys để xác minh chữ ký. Khi khai báo cả issuer và JWKS URI, ứng dụng có thể khởi tạo cấu hình mà không cần dựa vào metadata discovery lúc startup; JWKS vẫn cần truy cập khi xác minh token/refresh key.
3. **`audiences[0]`** là audience dự kiến. Spring Boot 3.3 hỗ trợ thuộc tính `spring.security.oauth2.resourceserver.jwt.audiences`. API Orders không chấp nhận access token cho API khác.
4. **`jws-algorithms[0]`** là allowlist thuật toán ký; ở đây chỉ cho `RS256`. Chỉ đổi sang thuật toán khác nếu issuer thực tế sử dụng thuật toán đó và thiết kế khóa phù hợp.

**Không thay hostname minh họa bằng endpoint do client gửi vào.** Mọi URI và audience phải đến từ cấu hình tin cậy được quản lý theo môi trường; JWKS qua HTTPS và TLS certificate của endpoint đó phải được JVM xác minh.

**Nếu chỉ cấu hình `jwk-set-uri` mà không có issuer:** chữ ký có thể được xác minh nhưng không được suy ra `iss` đã được kiểm tra. Nếu cần ràng buộc issuer, hãy khai báo `issuer-uri` hoặc cấu hình `JwtIssuerValidator` tương đương.

**Nếu issuer có discovery endpoint đúng chuẩn:** ứng dụng có thể chỉ đặt `issuer-uri` và để Resource Server tìm JWKS qua metadata. Việc thêm `jwk-set-uri` giúp giảm phụ thuộc metadata discovery ở thời điểm khởi tạo, đồng thời đòi hỏi bạn duy trì endpoint JWKS chính xác khi IdP thay đổi.

### 8.3. SecurityFilterChain và endpoint để kiểm chứng

Tệp `src/main/java/example/jwt/JwtResourceApplication.java`:

~~~java
package example.jwt;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class JwtResourceApplication {
    public static void main(String[] args) {
        SpringApplication.run(JwtResourceApplication.class, args);
    }
}

@Configuration(proxyBeanMethods = false)
class JwtResourceSecurity {
    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .anyRequest().authenticated());

        http.oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults()));

        return http.build();
    }
}

@RestController
class OrdersController {
    @GetMapping("/api/orders/ping")
    String ping() {
        return "ok";
    }
}
~~~

Ý nghĩa:

- `oauth2ResourceServer(...jwt...)` bật đường xác thực Bearer JWT, sử dụng `JwtDecoder` do Boot cấu hình theo những properties ở trên.
- `hasAuthority("SCOPE_orders.read")` là **kiểm tra phân quyền sau khi token hợp lệ**. Theo cấu hình mặc định, Spring ánh xạ scope `orders.read` thành authority `SCOPE_orders.read`.
- Phần endpoint `/api/orders/ping` chỉ trả `ok` khi request đã qua xác thực và có scope tương ứng.
- Token có signature/issuer/audience/time sai **không được cấp authentication hợp lệ**; policy authorization không thể sửa lỗi token.
- Nếu ứng dụng có nhiều `SecurityFilterChain`, phải kiểm tra đúng chain áp dụng cho API này; tránh cấu hình một chain public khác che mất chain Bearer.

### 8.4. Chạy và thử request

Với project đã chuẩn bị và IdP thật có endpoint ở cấu hình:

~~~bash
./gradlew bootRun
~~~

Windows dùng `gradlew.bat bootRun`. Đặt một access token **thật** đã được phát hành cho `urn:orders-api` vào biến môi trường `ACCESS_TOKEN` của shell, sau đó:

~~~bash
curl -i \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  http://localhost:8080/api/orders/ping
~~~

Các lệnh trên sử dụng cú pháp môi trường shell Unix. Với PowerShell cần chuyển cú pháp tham chiếu biến môi trường tương ứng. Chỉ gọi plain HTTP trên loopback để minh họa local; production bắt buộc HTTPS và không lưu token vào lịch sử lệnh/log.

Nếu token được ký bởi key tin cậy, `iss` đúng, `aud` chứa `urn:orders-api`, thời gian hợp lệ và scope có `orders.read`, response body là:

~~~text
ok
~~~

Kết quả thực tế phụ thuộc JWT được IdP phát hành, JWKS có thể truy cập được và cấu hình quyền. **Không thể chạy thành công ví dụ chỉ bằng cách copy placeholder domain hoặc JWT JSON minh họa**. Không có token hoặc token sai thường bị từ chối ở tầng authentication (thường HTTP 401); token đã xác thực mà thiếu scope `orders.read` thường bị từ chối ở tầng authorization (HTTP 403).

## 9. Tùy chỉnh validator trong Java khi policy phức tạp

Spring Boot properties là lựa chọn tốt khi chỉ cần issuer/audience chuẩn. Khi cần thêm validator tự viết, dùng `JwtDecoder` tùy chỉnh nhưng phải **giữ lại những kiểm tra mặc định**, đặc biệt issuer và timestamp. Một sai lầm là đăng ký `JwtDecoder` riêng, chỉ kiểm tra audience rồi vô tình bỏ issuer/time validator của cấu hình auto.

Ví dụ hoàn chỉnh về một bean cho **một issuer, một audience, RS256**. Đây là **cách thay thế** cấu hình `JwtDecoder` mặc định trong mục 8.2, không phải lớp cần gắn đồng thời với bean decoder khác.

Thêm vào `application.properties` của ví dụ tùy chỉnh (sử dụng khóa cấu hình `app.jwt.*`, còn `SecurityFilterChain` ở trên được giữ lại):

~~~properties
app.jwt.issuer=https://auth.example.test/realms/training
app.jwt.jwk-set-uri=https://auth.example.test/realms/training/protocol/openid-connect/certs
app.jwt.audience=urn:orders-api
~~~

Tệp `src/main/java/example/jwt/CustomJwtDecoderConfig.java`:

~~~java
package example.jwt;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

@Configuration(proxyBeanMethods = false)
public class CustomJwtDecoderConfig {

    @Bean
    JwtDecoder jwtDecoder(
            @Value("${app.jwt.issuer}") String issuer,
            @Value("${app.jwt.jwk-set-uri}") String jwkSetUri,
            @Value("${app.jwt.audience}") String audience) {

        NimbusJwtDecoder decoder =
                NimbusJwtDecoder.withJwkSetUri(jwkSetUri)
                        .jwsAlgorithm(SignatureAlgorithm.RS256)
                        .build();

        OAuth2TokenValidator<Jwt> standardValidators =
                JwtValidators.createDefaultWithIssuer(issuer);

        OAuth2TokenValidator<Jwt> requiredAudience = jwt -> {
            if (jwt.getAudience().contains(audience)) {
                return OAuth2TokenValidatorResult.success();
            }

            return OAuth2TokenValidatorResult.failure(new OAuth2Error(
                    "invalid_token",
                    "JWT is missing the required audience",
                    null));
        };

        decoder.setJwtValidator(new DelegatingOAuth2TokenValidator<>(
                standardValidators, requiredAudience));

        return decoder;
    }
}
~~~

Điểm cần hiểu ở ví dụ:

1. `withJwkSetUri(jwkSetUri)` chọn **đầu mối khóa đáng tin**. Decoder xác minh JWS bằng JWK tương ứng, không xác minh bằng các khóa được caller tùy ý gắn trong JWT.
2. `jwsAlgorithm(SignatureAlgorithm.RS256)` áp dụng allowlist; không tin header `alg` một cách vô điều kiện.
3. `JwtValidators.createDefaultWithIssuer(issuer)` giữ những standard validators gồm các điều kiện về issuer và thời gian. Nếu tự thay toàn bộ validators bằng một lambda check audience, có thể **làm mất những kiểm tra quan trọng**.
4. `jwt.getAudience().contains(audience)` yêu cầu trong danh sách `aud` có audience dự kiến; `null`/không có audience được Spring Jwt biểu diễn thành danh sách rỗng ở cách truy cập thông thường, dẫn đến từ chối.
5. `DelegatingOAuth2TokenValidator` kết hợp các validator; token phải vượt qua tất cả.
6. Khai báo một bean `JwtDecoder` tùy chỉnh sẽ thay decoder được Boot auto-configure. Vì thế phải kiểm thử lại issuer/time/audience/algorithm khi làm vậy.

Với API có nhiều audience hoặc policy riêng theo endpoint, không tự cho phép mọi `aud` rồi hy vọng `hasAuthority` bù được. Nên tách Resource Server hoặc thiết kế bộ validator/route mapping có ranh giới rõ ràng, vì một token cho resource khác có thể mang cùng scope string.

### Thêm giới hạn tuổi thọ và yêu cầu claim

Một API có yêu cầu đặc biệt có thể kiểm tra `exp` bắt buộc, giới hạn `exp - iat` (ví dụ không quá 15 phút) và `iat` không nằm quá xa tương lai. Cần định nghĩa rõ **NumericDate seconds**, clock skew và kiểu dữ liệu `Instant` sau khi Spring giải mã.

Đoạn minh họa bên trong một custom `OAuth2TokenValidator<Jwt>` (chưa phải lớp độc lập):

~~~java
OAuth2TokenValidator<Jwt> lifetimePolicy = jwt -> {
    if (jwt.getIssuedAt() == null || jwt.getExpiresAt() == null) {
        return OAuth2TokenValidatorResult.failure(new OAuth2Error(
                "invalid_token", "iat and exp are required", null));
    }

    long lifetimeSeconds =
            java.time.Duration.between(
                    jwt.getIssuedAt(), jwt.getExpiresAt()).getSeconds();

    if (lifetimeSeconds <= 0 || lifetimeSeconds > 900) {
        return OAuth2TokenValidatorResult.failure(new OAuth2Error(
                "invalid_token", "Token lifetime is outside policy", null));
    }

    return OAuth2TokenValidatorResult.success();
};
~~~

Nên thêm validator này vào `DelegatingOAuth2TokenValidator` **cùng** standard issuer/timestamp và audience validators, không thay thế chúng. Việc ràng buộc tuổi thọ token là **policy bổ sung**, không phải mặc định áp dụng cho mọi JWT.

## 10. Kiểm thử: phải làm cho token sai bị từ chối

Một bộ kiểm thử tốt phải có cả **positive case** và **negative cases** với các token được ký bằng test key/test issuer có thể điều khiển. Cách tiếp cận đáng tin là dựng **test authorization server** hoặc fixture JWS có private key thử nghiệm, public JWKS cố định và clock kiểm soát được. Tuyệt đối không dùng private key production trong source/test.

### 10.1. Ma trận kiểm thử bắt buộc

| Test case | Thay đổi trong fixture | Kết quả cần đạt |
| --- | --- | --- |
| **T01 — hợp lệ** | RS256 ký bằng khóa trong JWKS, `iss` đúng, `aud` đúng, `nbf`/`exp` hợp lệ, có `orders.read` | Authenticated + HTTP 200 |
| **T02 — sửa payload** | Giữ signature cũ, sửa `sub` hoặc `scope` | **401** do signature không khớp |
| **T03 — sai private key** | Token ký bằng key không có trong JWKS đáng tin | **401** |
| **T04 — giả kid** | `kid` không có trong JWKS issuer | **401** khi không xác minh được |
| **T05 — alg none** | Header đổi thành `alg=none`/bỏ signature | **401** |
| **T06 — alg không cho phép** | Chọn `HS256`/`ES256` trong API chỉ cho RS256 | **401** |
| **T07 — sai issuer** | Chữ ký hợp lệ với test key nhưng `iss` khác issuer cấu hình | **401** |
| **T08 — thiếu issuer** | Token không có `iss` khi policy bắt buộc | **401** |
| **T09 — sai audience** | `aud=urn:payments-api` | **401** |
| **T10 — thiếu audience** | Không có `aud` khi API yêu cầu | **401** |
| **T11 — nhiều audience** | `aud=["urn:orders-api","urn:analytics-api"]`, policy cho phép | Vượt audience check, còn phải xét scope |
| **T12 — exp quá hạn** | Thời gian verify sau `exp` vượt skew | **401** |
| **T13 — nbf tương lai** | `nbf` ở tương lai vượt skew | **401** |
| **T14 — biên clock skew** | Token mới hết hạn vài giây, tùy cấu hình skew | Kết quả đúng theo policy đã công bố |
| **T15 — iat tương lai/TTL dài** | Vi phạm custom lifetime policy nếu bật | **401** khi custom policy áp dụng |
| **T16 — thiếu scope** | Signature/iss/aud/time đều đúng, không có `orders.read` | **403** do authorization |
| **T17 — ID token** | ID token cùng issuer nhưng `aud` là client ID | **401** do audience/type policy |
| **T18 — JWKS rotation** | Issuer công bố thêm key mới rồi bỏ key cũ theo lịch | Token hợp lệ trong cửa sổ cho phép; key đã gỡ không tiếp tục được tin sau refresh |
| **T19 — JWKS outage** | Ngắt endpoint JWKS khi cache nóng/lạnh | Hành vi đúng theo cache/error policy; không chấp nhận token không xác minh được |
| **T20 — Bearer token rỗng** | Header thiếu token hoặc định dạng sai | Không tạo authenticated principal |

HTTP code trong bảng là kỳ vọng điển hình của một Spring Security resource server bảo vệ endpoint; entry point, exception handler và gateway thực tế có thể thay đổi response. Điều quan trọng là **không tạo Authentication hợp lệ** cho token vi phạm chữ ký/issuer/audience/time.

### 10.2. Vì sao không test signature bằng cách chỉ mock Jwt?

Với Spring Security Test, `jwt()` trong MockMvc thường **tạo sẵn Authentication** và bỏ qua việc chạy decoder xác minh signature/issuer/audience/time. Nó phù hợp test authorization như `hasAuthority`, nhưng **không chứng minh** API từ chối token đã bị sửa hoặc hết hạn. Để test decoder và Bearer filter, phải gửi **raw JWT được ký** qua HTTP hoặc gọi `JwtDecoder.decode(rawToken)` với JWKS/test key và các validator như production.

Phân biệt:

- **Unit test claim validator:** dùng một `Jwt` giả lập đã tạo trong test, kiểm tra `JwtValidators`/custom audience validator.
- **Decoder integration test:** dùng raw JWS test key, kiểm tra chữ ký, alg, issuer, audience, exp/nbf.
- **End-to-end HTTP test:** chạy `SecurityFilterChain` nhận header Bearer, xác minh 401/403/200 và JWKS rotation/caching khi cần.

Chỉ có unit test `jwt.getAudience()` sẽ bỏ sót lỗ hổng kiểu “quên cấu hình verify chữ ký”.

### 10.3. Công cụ tự đọc JWT để chẩn đoán — không verify

Để hiểu sự khác nhau giữa **decode** và **verify**, chương trình Java 17 dưới đây chỉ in hai phần JSON Base64url đầu của một JWS. Nó **cố ý không kiểm tra chữ ký** và tuyệt đối không được dùng làm authentication logic.

Tệp độc lập `JwtPeek.java`:

~~~java
import java.nio.charset.StandardCharsets;
import java.util.Base64;

public class JwtPeek {
    public static void main(String[] args) {
        if (args.length != 1) {
            System.err.println("Usage: java JwtPeek <test-jws>");
            System.exit(2);
        }

        String[] parts = args[0].split("\\.", -1);
        if (parts.length != 3) {
            throw new IllegalArgumentException(
                    "Expected JWS compact token with 3 parts");
        }

        Base64.Decoder decoder = Base64.getUrlDecoder();
        String header = new String(
                decoder.decode(parts[0]), StandardCharsets.UTF_8);
        String claims = new String(
                decoder.decode(parts[1]), StandardCharsets.UTF_8);

        System.out.println("UNVERIFIED HEADER: " + header);
        System.out.println("UNVERIFIED CLAIMS: " + claims);
        System.out.println("SIGNATURE NOT VERIFIED");
    }
}
~~~

Biên dịch và chạy bằng Java 17+:

~~~bash
javac --release 17 JwtPeek.java
java JwtPeek '<test-jws-created-by-your-test-issuer>'
~~~

Ví dụ output khi input chứa hai JSON fixture ở mục 1 sẽ in ra chính JSON đã mã hóa và dòng cuối:

~~~text
SIGNATURE NOT VERIFIED
~~~

Dòng cảnh báo này luôn được in khi cú pháp ba phần/Base64url hợp lệ; hai dòng JSON thực tế phụ thuộc input. **Không chạy với JWT production nếu công cụ ghi log hoặc máy không an toàn**, vì payload có thể chứa thông tin nhạy cảm. Chương trình không xác minh chữ ký, issuer, audience hay thời hạn; mục đích duy nhất là chứng minh rằng “đọc được payload” không phải “token hợp lệ”.

### 10.4. Thực hành thay đổi token đúng cách

Không thể “sửa một claim và giữ nguyên chữ ký” để tạo token hợp lệ. Hãy giữ hai loại fixture:

1. **Bị sửa mà không ký lại**: ví dụ đổi `scope` từ `orders.read` thành `orders.admin` trong payload mà giữ signature cũ. Test phải từ chối ở bước signature.
2. **Được ký lại hợp lệ bằng test private key**: đổi `iss`, `aud`, `exp`, `nbf` trong fixture rồi ký lại bằng test key của JWKS tin cậy. Test này cô lập claim validation, vì chữ ký đã hợp lệ.
3. **Key/algorithm khác**: tạo token ký bằng một key ngoài JWKS, hoặc algorithm không nằm trong allowlist, để test signature/key selection.

Nếu tất cả negative case chỉ dùng token có signature sai, bài test sẽ chỉ chứng minh bộ kiểm tra chữ ký chạy mà không chứng minh **issuer/audience/time validators** thực sự hoạt động.

## 11. Phân biệt 401 và 403

| Tình huống | Đầu ra thường gặp | Tầng xử lý |
| --- | --- | --- |
| Không có Bearer token ở endpoint bảo vệ | 401 | Entry point: chưa được xác thực |
| Token hết hạn, chữ ký sai, issuer/audience không hợp lệ | 401, thường kèm Bearer `invalid_token` | JWT decoding/authentication |
| Token hợp lệ, thiếu `SCOPE_orders.read` | 403, thường `insufficient_scope` hoặc access denied | Authorization |
| Đúng token, đủ quyền, controller chạy | 200 | Business endpoint |

Ví dụ thử local:

~~~bash
curl -i http://localhost:8080/api/orders/ping
curl -i -H "Authorization: Bearer $ACCESS_TOKEN" \
  http://localhost:8080/api/orders/ping
~~~

Không đưa toàn bộ raw token, chữ ký hoặc header Authorization vào log/app metrics. Với một token sai có thể dùng lỗi tóm tắt `invalid_token` ở response, nhưng giữ chi tiết nội bộ có kiểm soát về nhóm lỗi để debug. Nếu hệ thống dùng API Gateway, trạng thái HTTP có thể do gateway trả trước khi request tới Spring.

## 12. Những lỗi thường gặp và cách khắc phục

| Triệu chứng | Nguyên nhân phổ biến | Hướng kiểm tra |
| --- | --- | --- |
| Parse được JWT nhưng ai cũng đăng nhập được | Chỉ Base64 decode và tin payload | Bắt buộc dùng `JwtDecoder`/JWS verification trước khi tin claims |
| `alg=none` hoặc đổi RS256→HS256 vẫn được chấp nhận | Thuật toán không bị giới hạn, thư viện verify lỗi | Áp dụng allowlist/kiểu key, sử dụng thư viện chuẩn |
| Token của ứng dụng khác gọi được API | Quên audience validation | Đặt `jwt.audiences` hoặc audience validator |
| Token của realm khác được chấp nhận | Bỏ issuer validator hoặc tin issuer động | Ràng buộc `issuer-uri`/`JwtIssuerValidator` và JWKS theo issuer |
| Token hết hạn vẫn hợp lệ | Quên `JwtTimestampValidator`, skew quá lớn hoặc đồng hồ sai | Kiểm tra validator mặc định và đồng bộ NTP |
| Token vừa phát hành bị từ chối vì `nbf` | Lệch đồng hồ giữa IdP và API | So sánh UTC, chỉ áp skew nhỏ |
| `JWT signature invalid` | Sai JWKS, key xoay, token bị sửa hoặc algorithm sai | Kiểm tra issuer/JWKS, `kid`, thuật toán, chu kỳ cache |
| `Unable to resolve JWK` | `kid` không có, JWKS lỗi/timeout hoặc URL sai | Kiểm tra endpoint cấu hình, TLS, cache và key rotation |
| Token đã xác thực nhưng trả 403 | Thiếu authority `SCOPE_orders.read` | Kiểm tra `scope`/`scp` mapping và rule hasAuthority |
| Token hợp lệ bị lỗi khi đặt custom `JwtDecoder` | Custom bean đã thay Boot auto-config, bỏ standard validators | Đăng ký `JwtValidators.createDefaultWithIssuer` và audience validator |
| Test xanh nhưng token giả vẫn vào production | Chỉ mock `Jwt`, không test raw JWS | Thêm decoder/integration tests với key và JWKS thực trong test |
| JWT bị lộ qua log/URL | Đưa Bearer vào query, request log hay screenshot | Dùng HTTPS Authorization header, che token ở log và giới hạn TTL |

### JWKS rotation và khả năng sẵn sàng

- Khi issuer xuất bản khóa mới, JWKS có thể chứa đồng thời key cũ và mới trong thời gian chuyển tiếp.
- Token đang có hiệu lực được ký bằng khóa cũ có thể cần được xác minh cho đến khi hết hạn; issuer và API cần phối hợp thời gian công bố/xóa khóa.
- Resource Server thường cache JWKS theo cơ chế của decoder; kiểm tra TTL/refresh khi thay khóa. Không dựa vào cache lâu vô hạn cho khóa đã thu hồi.
- Khi JWKS endpoint mất kết nối, có thể xác minh token với khóa hợp lệ đã cache tùy tình trạng cache, nhưng **không thể tin một token mới không có key để verify**.
- JWKS phải được tải qua endpoint cấu hình cố định, HTTPS hợp lệ, có timeout/giám sát phù hợp. Đừng mở cơ chế SSRF từ `jku` hoặc `kid`.

### JWT thu hồi trước hạn

JWT signed thường được xác minh offline nên không có bước hỏi “đã logout chưa?” mặc định. Token còn hạn và chữ ký hợp lệ vẫn có thể được chấp nhận sau khi người dùng logout, nếu chưa có cơ chế thu hồi riêng. Các cách kiểm soát tùy kiến trúc gồm TTL ngắn, kiểm tra session/token status ở server, denylist `jti`, introspection hoặc các chính sách khóa tài khoản/issuer rotation. Không nhầm **kiểm tra `exp`** với **hỗ trợ thu hồi ngay lập tức**.

## 13. Quy trình thiết kế và nghiệm thu

Trước khi đưa JWT Bearer vào API thực tế, cần thống nhất:

1. **Issuer và token profile:** token phải phát hành bởi issuer nào, là OAuth2 access token hay dạng JWT tùy biến, có những claims bắt buộc gì?
2. **Khóa và thuật toán:** JWKS URI tin cậy, phương pháp quay vòng khóa, allowlist thuật toán; key type phù hợp.
3. **Audience:** định danh chính thức của Resource Server, có chấp nhận nhiều audience hay không, xử lý ID token thế nào?
4. **Thời hạn:** yêu cầu `exp`, xử lý `nbf`, `iat`, đồng bộ đồng hồ, clock skew nhỏ, TTL tối đa nếu cần.
5. **Quyền:** mapping `scope`/`scp` thành GrantedAuthority, kiểm tra `hasAuthority` tương ứng.
6. **Kiểm thử bảo mật:** token hợp lệ và các negative cases signature/key/algorithm/issuer/audience/expiry/not-before phải được chứng minh.
7. **Vận hành:** HTTPS, bảo vệ Bearer token, JWKS cache/rotation, logging an toàn, giới hạn thông tin lỗi, cơ chế revoke nếu bài toán yêu cầu.

### Checklist nhanh

- [ ] Không tin JWT chỉ vì Base64 decode thành JSON đọc được.
- [ ] Từ chối chữ ký sai, key không tin cậy, `alg=none` và thuật toán ngoài allowlist.
- [ ] JWKS endpoint/issuer đến từ cấu hình đáng tin, không theo URL do token tự cung cấp.
- [ ] `iss` phải khớp issuer; `aud` phải chứa API/resource ID dự kiến.
- [ ] `exp` và `nbf` được kiểm tra, đồng hồ đồng bộ và skew có giới hạn.
- [ ] Đã phân biệt `iat` với thời hạn kết thúc, thiết lập lifetime policy bổ sung nếu cần.
- [ ] Custom `JwtDecoder` không bỏ issuer/time validators mặc định.
- [ ] Scope/role chỉ được lấy sau khi JWT hợp lệ; 401 khác 403.
- [ ] Có kiểm thử decoder bằng raw signed JWT và JWKS test, ngoài test MockMvc có mock Authentication.
- [ ] Có xử lý rotation/JWKS outage và không để token hiện trong log/URL.

## 14. Câu hỏi ôn tập

1. Vì sao chỉ giải mã ba đoạn JWT và đọc `scope=orders.read` là nguy hiểm?
2. `kid` giúp chọn khóa như thế nào? Có được tự tải URL từ `jku` mà token gửi lên không?
3. Một token ký RS256 hợp lệ, còn hạn, issuer đúng nhưng `aud=urn:payments-api`. Orders API xử lý ra sao?
4. Token có `exp` trong quá khứ nhưng `iat` rất mới. Có được chấp nhận không?
5. Sự khác nhau giữa `exp`, `nbf` và `iat` là gì? NumericDate tính bằng giây hay mili giây?
6. Vì sao việc cố định thuật toán giúp chống `alg=none` và algorithm confusion?
7. Khi custom `NimbusJwtDecoder`, phải giữ những validators mặc định nào và bổ sung audience ra sao?
8. Nếu client đã được xác thực mà thiếu `SCOPE_orders.read`, API nên trả nhóm lỗi nào?
9. Tại sao unit test MockMvc `jwt()` không chứng minh signature verification đã hoạt động?
10. Nếu JWKS có khóa mới nhưng token cũ vẫn còn hạn, cần phối hợp rotation thế nào?

**Đáp án định hướng:** (1) Base64 không chứng minh tính toàn vẹn/xác thực; (2) chọn key trong JWKS của issuer đã tin, không tin URL do token cung cấp; (3) từ chối; (4) không nếu đã quá `exp` ngoài skew; (5) hết hạn, chưa hiệu lực và thời gian phát hành, đơn vị giây Unix UTC; (6) chỉ nhận thuật toán đã xác định và khóa đúng loại; (7) issuer + timestamp và audience validator; (8) 403 thiếu quyền; (9) đã mock Authentication, decoder có thể không chạy; (10) giữ key cũ đúng cửa sổ, công bố key mới sớm, điều chỉnh cache và loại key cũ theo policy.

## 15. Tài liệu tham khảo

- [Spring Security 6.5 — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/jwt.html)
- [Spring Boot 3.3 — Resource Server/JWT issuer và audiences](https://docs.spring.io/spring-boot/3.3/reference/web/spring-security.html)
- [Spring Security — Bearer Token Authentication](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/bearer-tokens.html)
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519)
- [RFC 7515 — JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515)
- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517)
- [RFC 8725 — JWT Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725)
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
