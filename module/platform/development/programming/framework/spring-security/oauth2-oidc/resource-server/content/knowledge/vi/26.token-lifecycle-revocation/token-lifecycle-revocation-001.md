# Thời điểm phát hành, bắt đầu có hiệu lực và hết hạn của access token

Trong **Spring Security OAuth 2.0 / OIDC Resource Server**, một Access Token có vòng đời theo thời gian: được phát hành lúc nào, được phép sử dụng từ lúc nào và phải ngừng được chấp nhận khi nào. Ba claim JWT thường gặp là **`iat`**, **`nbf`** và **`exp`**. OAuth token response còn có thể chứa **`expires_in`**, biểu thị thời lượng sống tính từ lúc Authorization Server tạo response.

Những giá trị này không đồng nghĩa:

- **`iat` (Issued At):** thời điểm token được phát hành. Nó cho biết tuổi token, không tự nói token bắt đầu có hiệu lực hay hết hạn lúc nào.
- **`nbf` (Not Before):** thời điểm sớm nhất token được phép chấp nhận. Nếu có claim này, token không hợp lệ trước thời điểm đó.
- **`exp` (Expiration Time):** thời điểm token không còn được chấp nhận. Theo JWT, token bị từ chối khi thời điểm hiện tại bằng hoặc sau `exp`, có thể có clock-skew leeway nhỏ theo policy.
- **`expires_in`:** thời lượng sống được Authorization Server trả trong token response, tính bằng giây từ lúc response được tạo. Nó không phải JWT claim và không thay thế `exp`.

Một token có thể đã được phát hành nhưng **chưa đến thời điểm bắt đầu có hiệu lực**. Token cũng có thể được phát hành và có hiệu lực ngay, rồi hết hạn theo một mốc khác. Resource Server phải kiểm tra thời gian theo contract của token, với đồng hồ được đồng bộ và chính sách clock skew rõ ràng.

Bài học thuộc chương **Vòng đời và thu hồi**, sử dụng **Java 17+, Spring Boot 3.x và Spring Security 6.x**. Nội dung trình bày semantics của NumericDate, khoảng thời gian hợp lệ, token response, JWT và opaque token, clock skew, `JwtTimestampValidator`, refresh, revocation, request đang chạy và kiểm thử.

## 1. Ba mốc thời gian trong JWT

Một JWT Access Token có thể chứa:

~~~json
{
  "iss": "https://identity.example.test",
  "sub": "person-42",
  "aud": ["orders-api"],
  "iat": 1893452400,
  "nbf": 1893452460,
  "exp": 1893456000,
  "scope": "orders.read"
}
~~~

Các số thời gian là **NumericDate**: số giây kể từ Unix epoch (1970-01-01T00:00:00Z), không phải số mili-giây Java.

~~~text
Thời gian UTC -------------------------------------------------------->

        iat                    nbf                      exp
         |                      |                        |
         v                      v                        v
---------+----------------------+------------------------+-------->
      Đã phát hành          Bắt đầu được phép         Hết hiệu lực
                             sử dụng

      Token tồn tại           Token có thể được         Token phải bị
      nhưng chưa active       chấp nhận                 từ chối
~~~

Nếu token có cả `nbf` và `exp`, không xét clock skew, khoảng thời gian được chấp nhận là:

~~~text
nbf <= now < exp
~~~

Nếu không có `nbf`, token không khai báo mốc not-before; verifier vẫn phải kiểm tra expiration và các điều kiện khác. **`iat` không thay thế `nbf`**.

### 1.1. iat: thời điểm phát hành

`iat` cho biết thời điểm token được phát hành. Ứng dụng có thể dùng nó để hiển thị tuổi token, điều tra token được phát hành trước hay sau sự kiện bảo mật, thực thi policy về tuổi tối đa hoặc áp dụng minimum-issued-at/epoch để vô hiệu hóa token cũ theo user/tenant.

Nhưng `iat` **không tự xác định thời điểm token bắt đầu được chấp nhận**. Nếu `iat` là 10:00 và `nbf` là 10:05, token vẫn chưa được dùng trước 10:05. Token có `iat` cũ cũng không nhất thiết hết hạn nếu `exp` vẫn ở tương lai và policy không giới hạn tuổi token.

### 1.2. nbf: bắt đầu có hiệu lực

`nbf` (Not Before) là mốc thời gian trước đó token **không được chấp nhận**:

~~~json
{
  "iat": 1893452400,
  "nbf": 1893452700,
  "exp": 1893456000
}
~~~

Token đã được tạo lúc `iat`, nhưng chỉ bắt đầu có thể sử dụng ở `nbf`. Trước thời điểm đó, JWT validator phải từ chối token theo quy tắc not-before. Trường hợp sử dụng có thể gồm token được chuẩn bị trước một đợt triển khai hoặc quyền truy cập bắt đầu tại một thời điểm đã lên lịch.

Đừng tự thêm `nbf` trong mọi token nếu hệ thống không có nhu cầu; càng nhiều mốc thời gian, càng cần bảo đảm đồng hồ và semantics giữa AS/RS nhất quán.

### 1.3. exp: hết hạn

`exp` là thời điểm sau đó token không được chấp nhận. Theo RFC 7519, JWT không được chấp nhận **on or after** expiration time, trừ một khoảng leeway nhỏ mà các bên có thể thống nhất để xử lý clock skew.

~~~json
{
  "iat": 1893452400,
  "exp": 1893456000
}
~~~

Token có thể đã được phát hành và sử dụng từ `iat`, nhưng phải bị từ chối khi đồng hồ của verifier đến `exp`, xét theo policy leeway.

`exp` là giới hạn thời gian trên của token; token vẫn có thể mất hiệu lực sớm hơn do Authorization Server revoke token/grant, user/client/tenant bị khóa, signing key bị thu hồi, introspection trả `active:false` hoặc Resource Server áp dụng denylist/token epoch.

**Hết hạn và thu hồi là hai nguyên nhân khác nhau.** Token chưa đến `exp` vẫn có thể bị từ chối vì revoked.

## 2. expires_in khác exp như thế nào?

OAuth 2.0 token response thường có:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store
Pragma: no-cache

{
  "access_token": "ACCESS_TOKEN_VALUE",
  "token_type": "Bearer",
  "expires_in": 3600,
  "scope": "orders.read"
}
~~~

`expires_in` là **số giây token còn hiệu lực**, tính từ lúc response được tạo theo RFC 6749. Nó là metadata trong token response, không phải claim JWT.

| Giá trị | Hình thức | Ý nghĩa |
| --- | --- | --- |
| `iat` | NumericDate tuyệt đối | Token được phát hành lúc nào. |
| `nbf` | NumericDate tuyệt đối | Token được phép bắt đầu dùng lúc nào. |
| `exp` | NumericDate tuyệt đối | Token hết hạn lúc nào. |
| `expires_in` | Duration tính bằng giây | Thời lượng sống do AS công bố trong token response. |

Nếu token JWT có `exp`, Resource Server dùng claim tuyệt đối đó khi xác minh. Client có thể dùng `expires_in` để lên lịch refresh; không tự tạo `exp` bằng cách sửa token.

### 2.1. Tính thời điểm hết hạn từ expires_in

Giả sử AS tạo response tại 10:00:00 và trả `expires_in: 600`. Thời điểm hết hạn theo thông tin này là khoảng 10:10:00. Client nhận response sau độ trễ mạng; nếu lấy **thời điểm nhận response + 600 giây**, nó có thể ước lượng muộn hơn thời điểm hết hạn thật.

Vì vậy client nên bắt đầu đếm từ lúc nhận response và trừ safety margin, hoặc dùng `exp` đã xác minh nếu có thể đọc token theo đúng contract. Không dựa vào đồng hồ local thiếu đồng bộ và không dùng `expires_in` để kéo dài token sau khi AS đã revoke.

### 2.2. Token response và JWT có thể không cùng cách biểu diễn

Một AS có thể phát hành opaque token. Khi đó client vẫn nhận `expires_in`, nhưng không thể tự đọc `exp` từ token. Resource Server hỏi introspection endpoint để biết token có active không.

JWT token response có thể đồng thời chứa `expires_in` và JWT có claim `exp`. Hai giá trị phải nhất quán theo hợp đồng phát hành; nếu chênh lệch bất thường, cần điều tra AS/token profile thay vì tự chọn giá trị dài hơn.

## 3. Khoảng thời gian token hợp lệ

~~~text
iat = 09:00:00
nbf = 09:05:00
exp = 10:00:00

09:00:00  Đã phát hành, nhưng chưa đến nbf
09:04:59  Chưa được chấp nhận
09:05:00  Bắt đầu có thể được chấp nhận
09:59:59  Vẫn trong thời gian hợp lệ
10:00:00  Hết hạn; phải từ chối
~~~

Mốc `iat` cho biết thời gian phát hành. Nếu verifier muốn từ chối token có `iat` nằm trong tương lai quá xa hoặc token quá cũ, đó là **policy bổ sung** cần triển khai rõ ràng.

### 3.1. Token chưa tới nbf

Nếu token được phát hành trước khi bắt đầu có hiệu lực, Resource Server từ chối authentication khi request tới quá sớm. Client có thể chờ tới thời điểm cho phép rồi thử lại theo policy. Không nên retry liên tục mỗi vài mili-giây; dùng thời điểm not-before, backoff và clock margin.

### 3.2. Token đã tới exp

Khi token hết hạn, JWT Resource Server phải từ chối dựa trên timestamp validator; opaque Resource Server phải nhận kết quả introspection inactive hoặc áp policy expiration đáng tin cậy. Client cần lấy token mới bằng refresh/authorization flow phù hợp. Không được tự thay claim `exp` hoặc dùng token cũ bằng cách đổi đồng hồ phía client.

### 3.3. Token có iat cũ nhưng exp còn xa

Một token có thể tồn tại lâu nếu AS phát hành lifetime dài. Nếu policy yêu cầu Access Token không được sống quá 15 phút, chỉ kiểm tra `exp` là chưa đủ nếu token được cấp sai cấu hình với thời hạn nhiều giờ. Có thể áp thêm:

~~~text
now - iat <= maximumTokenAge
~~~

Đây là **policy tuổi token** của ứng dụng, không phải cách diễn giải lại `exp`. Chỉ áp dụng nếu token profile yêu cầu `iat` và clocks được đồng bộ.

## 4. NumericDate và chuyển đổi trong Java

JWT time claims dùng NumericDate theo giây Unix epoch. Java thường làm việc với `Instant`:

~~~java
import java.time.Instant;

long expSeconds = 1_893_456_000L;
Instant expiresAt = Instant.ofEpochSecond(expSeconds);

long nowSeconds = Instant.now().getEpochSecond();
boolean expired = nowSeconds >= expSeconds;
~~~

**Không dùng `Instant.ofEpochMilli(expSeconds)`**: cách đó hiểu số giây thành mili-giây, khiến mốc thời gian sai rất xa.

Chuyển đổi chiều ngược lại:

~~~java
Instant expiresAt = Instant.parse("2030-01-01T01:00:00Z");
long exp = expiresAt.getEpochSecond();
~~~

JWT NumericDate là thời gian tuyệt đối, không chứa timezone của server. Trong code, dùng `Instant` cho mốc tuyệt đối, `Duration` cho thời lượng, `Clock` để test thời gian. Không dùng `LocalDateTime.now()` làm nguồn quyết định token expiration vì nó không mang offset/zone và dễ gây lỗi khi môi trường khác timezone.

### 4.1. Clock abstraction để test

~~~java
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;

Clock clock = Clock.fixed(
    Instant.parse("2030-01-01T00:00:00Z"),
    ZoneOffset.UTC);

Instant now = clock.instant();
~~~

Một service tự viết có thể nhận `Clock` qua constructor thay vì gọi `Instant.now()` trực tiếp ở nhiều nơi. Khi test, chuyển thời gian bằng clock fixture để xác minh biên `nbf`/`exp`.

## 5. Clock skew: vì sao hai server có thể bất đồng?

Authorization Server và Resource Server có thể lệch đồng hồ:

~~~text
AS clock:  10:00:00.000
RS clock:  09:59:40.000  (chậm 20 giây)
~~~

Nếu token có `nbf` đúng 10:00:00 theo AS, RS chậm 20 giây có thể nghĩ token còn ở tương lai. Ngược lại, nếu RS nhanh hơn AS, RS có thể nghĩ token hết hạn sớm.

**Clock skew/leeway** cho phép verifier dung sai một khoảng nhỏ:

~~~text
accept if:
  now + skew >= nbf
  AND
  now - skew < exp
~~~

Đây là mô tả khái quát của timestamp leeway. Tên biến và chi tiết so sánh có thể khác giữa thư viện; phải hiểu đúng semantics của validator đang dùng.

### 5.1. Leeway không phải gia hạn token

Nếu `exp` là 10:00:00 và verifier cho leeway 30 giây, một request ở 10:00:10 có thể được chấp nhận bởi verifier đó. Điều này **không thay đổi claim exp ở token**, nhưng làm Resource Server chấp nhận token lâu hơn mốc phát hành trong phạm vi tolerance.

Chọn skew nhỏ dựa trên đo lường clock thực tế; không đặt vài phút hoặc hàng giờ chỉ để che clock misconfiguration. Dùng cùng policy nhất quán trên replicas, theo dõi NTP/clock drift và xét leeway khi thiết kế maximum token lifetime/revocation window.

### 5.2. Client không quyết định leeway phía server

Client có thể nghĩ token còn hiệu lực thêm 30 giây, nhưng Resource Server không nhất thiết dùng cùng leeway. **Server là bên quyết định có chấp nhận token hay không.** Client nên refresh sớm để không gửi token sát expiration; nó không có quyền yêu cầu server chấp nhận quá hạn.

## 6. iat không phải nbf: policy issued-at riêng

Một số hệ thống cần kiểm tra `iat`: token không được phát hành trong tương lai quá clock tolerance, phải mới hơn một mốc thu hồi hàng loạt hoặc không vượt maximum age của profile.

~~~text
iat <= now + allowedClockSkew
now - iat <= maxTokenAge
~~~

Không nên mặc định mọi JWT đều có `iat` hoặc mọi profile đều áp cùng maximum age. **RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens** quy định profile claims cho JWT Access Token; một JWT generic khác có thể có contract khác.

### 6.1. Minimum issued-at / token epoch

Nếu user bị khóa hoặc refresh-token family bị thu hồi, ứng dụng có thể lưu:

~~~text
user.minimumTokenIssuedAt = 2030-01-01T10:00:00Z
~~~

Khi xác minh token, nếu `iat` nhỏ hơn mốc này thì từ chối. Điều này có thể vô hiệu hóa một nhóm token cũ trước `exp` mà không cần lưu từng `jti`. Tuy nhiên, phải lưu trạng thái trong nguồn tin cậy, đồng bộ replicas, xác định phạm vi user/client/tenant, chỉ so sánh `iat` sau khi JWT được xác thực và có semantics rõ cho token thiếu `iat`.

Đây là **một chính sách thu hồi bổ sung**, không phải chức năng tự động của `iat`.

## 7. Spring Security: kiểm tra exp và nbf bằng JwtTimestampValidator

Spring Security JWT Resource Server dùng `JwtDecoder` để xác minh JWT. Timestamp validation có thể được thực hiện bởi `JwtTimestampValidator`, kiểm tra các claim thời gian như `exp` và `nbf` theo clock-skew policy.

Ví dụ cấu hình Servlet Resource Server:

~~~java
import java.time.Duration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2ErrorCodes;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtIssuerValidator;
import org.springframework.security.oauth2.jwt.JwtTimestampValidator;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

@Configuration
public class JwtSecurityConfiguration {

    private static final String ISSUER =
        "https://identity.example.test";

    private static final String JWK_SET_URI =
        "https://identity.example.test/oauth2/jwks";

    @Bean
    JwtDecoder jwtDecoder() {
        NimbusJwtDecoder decoder =
            NimbusJwtDecoder.withJwkSetUri(JWK_SET_URI).build();

        JwtTimestampValidator timestamps =
            new JwtTimestampValidator(Duration.ofSeconds(30));

        OAuth2TokenValidator<Jwt> issuer =
            new JwtIssuerValidator(ISSUER);

        OAuth2TokenValidator<Jwt> audience = jwt ->
            jwt.getAudience().contains("orders-api")
                ? OAuth2TokenValidatorResult.success()
                : OAuth2TokenValidatorResult.failure(
                    new OAuth2Error(
                        OAuth2ErrorCodes.INVALID_TOKEN,
                        "Required audience is missing",
                        null));

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                timestamps,
                issuer,
                audience));

        return decoder;
    }
}
~~~

Trong ví dụ, `JwtTimestampValidator` áp dụng clock skew 30 giây; `JwtIssuerValidator` kiểm tra issuer đã cấu hình; audience validator bảo đảm token dành cho `orders-api`; `NimbusJwtDecoder` xác minh chữ ký theo JWK Set URI tin cậy.

**Lưu ý:** ví dụ dùng JWKS URI tĩnh để minh họa. Trong production, issuer/JWKS phải đến từ trust configuration; không lấy URI từ JWT header hoặc request. Khi dùng `JwtValidators.createDefaultWithIssuer`, default validators đã bao gồm timestamp validation; nếu cần clock skew tùy chỉnh, hãy cấu hình validator rõ ràng như trên, tránh vô tình áp hai timestamp validators với policy khác nhau.

### 7.1. iat cần validator riêng nếu policy yêu cầu

`JwtTimestampValidator` tập trung vào expiration/not-before; nếu hệ thống muốn giới hạn issued-at trong tương lai hoặc maximum age, thêm validator riêng:

~~~java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2ErrorCodes;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;

Clock clock = Clock.systemUTC();
Duration allowedSkew = Duration.ofSeconds(30);
Duration maximumAge = Duration.ofMinutes(15);

OAuth2TokenValidator<Jwt> issuedAtValidator = jwt -> {
    Instant issuedAt = jwt.getIssuedAt();
    Instant now = clock.instant();

    if (issuedAt == null
            || issuedAt.isAfter(now.plus(allowedSkew))
            || issuedAt.isBefore(now.minus(maximumAge))) {
        return OAuth2TokenValidatorResult.failure(
            new OAuth2Error(
                OAuth2ErrorCodes.INVALID_TOKEN,
                "Issued-at time violates token age policy",
                null));
    }

    return OAuth2TokenValidatorResult.success();
};
~~~

Đây là **validator policy minh họa**, không bắt buộc cho mọi Access Token. Nếu dùng, phải ghép nó vào `DelegatingOAuth2TokenValidator` của decoder. Chỉ yêu cầu `iat` khi token profile quy định có claim đó; nếu không, xác định rõ cách xử lý token thiếu `iat`.

### 7.2. Timestamp validation phải xảy ra trước authorization

JWT hết hạn hoặc chưa tới `nbf` không được trở thành authenticated principal rồi mới kiểm tra scope. Timestamp validator nằm trong đường decode/authentication; token không hợp lệ sẽ thất bại trước authorization filter.

## 8. Opaque Access Token: introspection quyết định active

Opaque token không chứa claims đọc được cho Resource Server. Thay vào đó, RS gọi Authorization Server:

~~~http
POST /oauth2/introspect HTTP/1.1
Content-Type: application/x-www-form-urlencoded
Authorization: Basic RESOURCE_SERVER_CREDENTIALS

token=OPAQUE_ACCESS_TOKEN
~~~

Response:

~~~json
{
  "active": true,
  "scope": "orders.read",
  "sub": "person-42",
  "exp": 1893456000,
  "iat": 1893452400,
  "nbf": 1893452460,
  "aud": ["orders-api"]
}
~~~

AS chịu trách nhiệm đánh giá trạng thái token và trả `active`. Nếu token đã hết hạn theo AS, response phải phản ánh inactive. RS không tự giải mã opaque string để suy ra `exp`.

### 8.1. Cấu hình Spring Boot

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaque-token:
          introspection-uri: https://identity.example.test/oauth2/introspect
          client-id: orders-resource-server
          client-secret: SECRET_FROM_SECRET_MANAGER
~~~

Spring Security dùng opaque-token introspector để lấy principal/authorities từ response. **`active:true` là điều kiện authentication, không thay audience/scope/domain authorization**.

### 8.2. Introspection response và thời gian

Nếu AS trả `active:true` nhưng `exp` đã qua theo clock của RS, cần xem lại clock AS/RS, leeway, NumericDate seconds, metadata cache và contract của `active`. Không tự sửa response hoặc ép active thành true. Với opaque token, AS là nguồn quyết định trạng thái; nếu cần local maximum-age/audience policy, triển khai adapter validator rõ ràng dựa trên metadata đáng tin.

### 8.3. Cache introspection và expiration

Nếu cache positive introspection, TTL không được vượt quá:

~~~text
min(
  configuredPositiveCacheTtl,
  exp - now - safetyMargin
)
~~~

Nếu không có `exp` đáng tin cậy trong metadata, dùng TTL theo revocation policy đã duyệt hoặc không cache positive result. Dù token còn trước `exp`, AS vẫn có thể revoke sớm; cache active có thể tạo cửa sổ stale. **Expiration không phải cách thay thế revocation.**

## 9. Access Token expiration và refresh

Client thường cần refresh Access Token trước khi hết hạn để tránh request thất bại:

~~~text
Access Token issued
        |
        v
Use token
        |
        +------------------------------+
        |                              |
        v                              v
Approaching exp                  Token revoked
        |                              |
        v                              v
Refresh/reauthorize              Refresh may fail / grant invalid
        |                              |
        v                              v
New Access Token                 Re-authentication or error handling
~~~

### 9.1. Refresh trước exp, không đợi đúng giây cuối

Client nên dùng safety margin:

~~~text
refreshAt = expiresAt - refreshMargin
~~~

Ví dụ token có thời hạn 10 phút, client có thể bắt đầu refresh trước một khoảng phù hợp với latency và reliability của hệ thống. Cần tính thời gian mạng đến AS, tải/latency của token endpoint, clock skew, request duration, retry budget, Refresh Token rotation và concurrency.

Nếu nhiều request đồng thời phát hiện token sắp hết hạn, dùng cơ chế single-flight/authorized client manager để tránh refresh stampede.

### 9.2. expires_in là hint cho client, server vẫn xác minh

Client có thể nghĩ token còn sống dựa trên timer, nhưng server luôn kiểm tra token. Nếu client gửi token quá hạn, Resource Server từ chối. Nếu client quên refresh, request thất bại; đó không phải lý do để Resource Server nới `exp`.

### 9.3. Refresh Token có lifecycle riêng

Refresh Token có thể có expiration, rotation, reuse detection và revocation policy riêng. Khi refresh thành công, AS có thể phát Access Token mới với `iat`/`exp` mới và thay Refresh Token theo rotation policy. Client phải lưu token mới an toàn và loại bỏ token cũ theo contract. Không giả định Access Token cũ tự được revoke trong mọi AS.

## 10. Expiration khác revocation

| Thuộc tính | Expiration | Revocation |
| --- | --- | --- |
| Nguyên nhân | Đã đến mốc `exp`. | AS/admin/user/security policy thu hồi trước hạn. |
| Có thể dự đoán trước? | Có, từ thời gian token. | Không nhất thiết. |
| JWT offline có tự phát hiện? | Có, khi kiểm tra timestamp. | Không, trừ khi có online/denylist/epoch mechanism. |
| Opaque introspection | AS trả inactive khi hết hạn. | AS trả inactive sau khi thấy revoke. |
| Token mới cần thiết? | Có, refresh/reauthorization. | Thường cần token mới sau khi quyền được cấp lại. |

Một Access Token có thể bị revoke lúc 10:02 dù `exp` là 10:10. Nếu Resource Server chỉ kiểm tra JWT chữ ký và expiration offline, nó có thể tiếp tục chấp nhận token đến 10:10. Đó là đánh đổi của self-contained JWT và phải được xử lý theo revocation requirements.

### 10.1. Minimum lifetime và maximum lifetime

AS có thể có policy về Access Token lifetime tối đa theo client/resource, lifetime ngắn hơn cho quyền nhạy cảm, thời điểm grant được active và thu hồi token khi user/client/tenant bị disable. Resource Server có thể áp thêm maximum token age hoặc revocation epoch, nhưng cần đồng bộ policy với AS.

## 11. Request bắt đầu trước exp nhưng kết thúc sau exp

~~~text
10:00:00.000  Request bắt đầu
10:00:00.020  JWT exp validation thành công
10:00:00.100  Domain transaction bắt đầu
10:00:01.000  Token exp
10:00:02.000  Transaction commit
~~~

JWT timestamp validation thường xảy ra ở bước authentication đầu request. Token hết hạn **sau khi authentication đã thành công** không tự động hủy transaction đang chạy. Nếu nghiệp vụ cần giới hạn cả thời gian thực hiện, kiểm tra lại account/tenant/token state tại điểm commit hoặc domain boundary, giới hạn request/job duration, thiết kế side effects có idempotency và xác định policy cho WebSocket/SSE/background jobs.

Không nhầm **token hết hạn** với **tự động cancel mọi công việc đã được xác thực trước đó**.

## 12. ID Token và Access Token có thời điểm riêng

Trong OIDC, **ID Token** và **Access Token** là hai loại token khác nhau. ID Token cho client/Relying Party biết kết quả authentication của user; Access Token dành cho Resource Server để truy cập API.

Cả hai có thể chứa `iat` và `exp`, nhưng không được dùng expiration của ID Token để suy ra Access Token còn sống, hoặc dùng ID Token thay Access Token cho API.

~~~text
ID Token:
  aud = web-client
  exp = 10:15

Access Token:
  aud = orders-api
  exp = 10:05
~~~

Web session có thể vẫn tồn tại sau khi Access Token hết hạn và client có thể refresh token theo policy. Ngược lại, ID Token còn hạn không chứng minh Access Token còn hiệu lực.

## 13. Kiểm thử thời gian trong Spring Security

Kiểm thử timestamp nên xác minh các biên:

| Test case | Kỳ vọng |
| --- | --- |
| `now < nbf` ngoài clock skew | Từ chối: chưa có hiệu lực. |
| `now == nbf` | Có thể chấp nhận theo not-before boundary và policy. |
| `nbf < now < exp` | Timestamp hợp lệ. |
| `now == exp` | Từ chối theo expiration boundary, trừ leeway được cấu hình. |
| `now > exp` ngoài leeway | Từ chối. |
| `iat` nằm trong tương lai vượt skew | Từ chối nếu profile/policy có issued-at validator. |
| `iat` quá cũ | Từ chối nếu có maximum-age policy. |
| NumericDate bị hiểu nhầm milliseconds | Test phải phát hiện conversion sai. |
| Clock skew nhỏ trong tolerance | Kết quả theo validator policy. |
| Clock skew vượt tolerance | Từ chối. |
| Opaque introspection active=false | Từ chối. |
| Opaque active cache hết TTL | Introspect lại, không dùng stale result. |

### 13.1. jwt() test helper không chạy timestamp decoder thật

~~~java
mockMvc.perform(get("/api/orders/42")
        .with(jwt().jwt(jwt -> jwt
            .claim("scope", "orders.read"))))
    .andExpect(status().isOk());
~~~

Helper `jwt()` tạo Authentication test đã xác thực. Nó **không chứng minh** `NimbusJwtDecoder` đã xác minh signature, `exp`, `nbf`, issuer hoặc audience. Dùng helper để test authorization rules; dùng signed JWT integration tests hoặc test `JwtDecoder` trực tiếp để kiểm tra timestamp validation.

### 13.2. Test timestamp policy với Clock cố định

Một policy nhỏ có thể nhận `Clock` để test biên mà không phụ thuộc đồng hồ thật:

~~~java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;

public final class TokenTimePolicy {

    private final Clock clock;
    private final Duration skew;

    public TokenTimePolicy(Clock clock, Duration skew) {
        this.clock = clock;
        this.skew = skew;
    }

    public boolean isWithinValidityWindow(
            Instant notBefore, Instant expiresAt) {
        Instant now = clock.instant();
        boolean afterNbf = notBefore == null
            || !now.plus(skew).isBefore(notBefore);
        boolean beforeExp = expiresAt == null
            || now.minus(skew).isBefore(expiresAt);
        return afterNbf && beforeExp;
    }
}
~~~

Test:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;
import org.junit.jupiter.api.Test;

class TokenTimePolicyTest {

    @Test
    void acceptsInsideValidityWindow() {
        Clock clock = Clock.fixed(
            Instant.parse("2030-01-01T00:05:00Z"),
            ZoneOffset.UTC);
        TokenTimePolicy policy =
            new TokenTimePolicy(clock, Duration.ZERO);

        assertTrue(policy.isWithinValidityWindow(
            Instant.parse("2030-01-01T00:00:00Z"),
            Instant.parse("2030-01-01T00:10:00Z")));
    }

    @Test
    void rejectsBeforeNotBefore() {
        Clock clock = Clock.fixed(
            Instant.parse("2030-01-01T00:04:59Z"),
            ZoneOffset.UTC);
        TokenTimePolicy policy =
            new TokenTimePolicy(clock, Duration.ZERO);

        assertFalse(policy.isWithinValidityWindow(
            Instant.parse("2030-01-01T00:05:00Z"),
            Instant.parse("2030-01-01T00:10:00Z")));
    }

    @Test
    void rejectsAtExpirationBoundary() {
        Clock clock = Clock.fixed(
            Instant.parse("2030-01-01T00:10:00Z"),
            ZoneOffset.UTC);
        TokenTimePolicy policy =
            new TokenTimePolicy(clock, Duration.ZERO);

        assertFalse(policy.isWithinValidityWindow(
            Instant.parse("2030-01-01T00:00:00Z"),
            Instant.parse("2030-01-01T00:10:00Z")));
    }
}
~~~

Đây là **unit test cho policy minh họa**, không thay thế test `JwtTimestampValidator` của Spring hoặc kiểm tra chữ ký JWT. Integration tests vẫn cần signed token thật, decoder thật và thời điểm `nbf`/`exp` được chọn rõ ràng.

## 14. Các lỗi cấu hình thường gặp

| Sai lầm | Hậu quả | Cách đúng |
| --- | --- | --- |
| Nhầm `iat` là thời điểm bắt đầu có hiệu lực. | Chấp nhận token trước `nbf`. | Kiểm tra `nbf` riêng. |
| Nhầm `expires_in` là JWT claim. | Tìm field sai hoặc tự tạo `exp`. | Phân biệt token response và token claims. |
| Dùng `Instant.ofEpochMilli` cho NumericDate. | Token time sai lệch lớn. | `Instant.ofEpochSecond`. |
| Không kiểm tra `exp`. | Token quá hạn vẫn được chấp nhận. | Timestamp validator bắt buộc. |
| Bỏ qua `nbf`. | Token chưa đến thời điểm hiệu lực được dùng. | Kiểm tra not-before nếu claim tồn tại. |
| Cho leeway quá lớn. | Token hết hạn vẫn được nhận lâu. | Skew nhỏ, đo clock drift. |
| Dùng `iat` thay `exp`. | Không có giới hạn expiration đúng. | `exp` quyết định hết hạn. |
| Coi JWT revoke tự có hiệu lực offline. | Token còn hạn có thể tiếp tục được chấp nhận. | Introspection/denylist/epoch khi cần. |
| Dùng client timer làm server validation. | Caller có thể sửa đồng hồ. | Server tự xác minh token. |
| Refresh đúng lúc exp. | Request fail khi AS/network chậm. | Refresh sớm với margin/jitter. |
| Dùng ID Token cho API. | Sai token audience/purpose. | Access Token dành cho resource. |
| Test chỉ bằng `jwt()` helper. | Không test decoder timestamp thật. | Signed JWT/decoder integration tests. |
| Cache opaque active quá exp. | Token hết hạn vẫn có thể được nhận. | TTL bị giới hạn bởi expiration và revocation policy. |

## 15. Runbook xử lý token chưa hiệu lực hoặc hết hạn

1. **Xác định token type:** JWT Access Token, opaque Access Token hay ID Token.
2. **Xác minh issuer/resource:** token có dành cho đúng API không.
3. **Đọc mốc thời gian đã xác minh:** `iat`, `nbf`, `exp` hoặc `expires_in` theo đúng contract.
4. **Kiểm tra đơn vị:** NumericDate là giây; Java conversion dùng epoch seconds.
5. **Kiểm tra clock:** NTP, timezone assumptions, drift giữa AS, gateway và RS.
6. **Xem clock skew:** policy có đủ nhỏ và nhất quán không.
7. **Nếu chưa tới nbf:** client chờ theo thời điểm có hiệu lực, không retry dồn dập.
8. **Nếu exp đã qua:** refresh/reauthorize theo OAuth flow; không nới validator để chữa token cũ.
9. **Nếu token bị revoke trước exp:** điều tra revocation state, không chỉ nhìn expiration.
10. **Nếu opaque token:** kiểm tra introspection `active`, cache TTL và AS visibility.
11. **Nếu JWT offline:** xác định có cần denylist/epoch/online check để hỗ trợ revoke sớm không.
12. **Ghi nhận lỗi an toàn:** không log raw token hoặc secret; tách `not_yet_valid`, `expired`, `revoked`, `clock_skew` và `introspection_unavailable` khi có đủ thông tin.

**Ghi nhớ:** `iat` cho biết token được phát hành lúc nào, `nbf` cho biết token bắt đầu được phép dùng lúc nào và `exp` xác định thời điểm token phải ngừng được chấp nhận. `expires_in` là thời lượng trong token response, không phải JWT claim. Spring Security dùng timestamp validation để kiểm tra thời gian của JWT; opaque token dựa trên introspection. Hãy dùng NumericDate theo giây, đồng bộ clock, đặt clock skew nhỏ và refresh trước expiration. **Token có thể bị revoke trước `exp`, còn request đã xác thực trước khi hết hạn không tự động bị hủy.**

## Tài liệu tham khảo

- [RFC 7519 — JSON Web Token, NumericDate, exp, nbf and iat](https://www.rfc-editor.org/rfc/rfc7519).
- [RFC 6749 — OAuth 2.0 Authorization Framework, expires_in](https://www.rfc-editor.org/rfc/rfc6749).
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068).
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662).
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009).
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725).
- [Spring Security — JWT Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html).
- [Spring Security — JwtTimestampValidator API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/jwt/JwtTimestampValidator.html).
- [Spring Security — Opaque Token Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html).
- [Spring Security — Testing OAuth 2.0 with MockMvc](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/oauth2.html).
