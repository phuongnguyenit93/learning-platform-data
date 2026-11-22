# Kiểm tra exp, nbf và lựa chọn độ lệch đồng hồ cho phép

Trong **Spring Security OAuth 2.0/OIDC Resource Server**, JWT access token chỉ nên được chấp nhận trong khoảng thời gian mà Authorization Server cho phép. Hai claim quan trọng là **`exp` (Expiration Time)**, cho biết khi nào token hết hạn, và **`nbf` (Not Before)**, cho biết thời điểm token bắt đầu có hiệu lực. Resource Server phải kiểm tra các giá trị này sau khi xác minh chữ ký JWT bằng khóa tin cậy.

Trong một hệ thống phân tán, đồng hồ của Authorization Server, Resource Server và các node khác nhau có thể lệch nhau vài giây. **Clock skew** (còn gọi là clock leeway) là một khoảng dung sai nhỏ giúp tránh từ chối nhầm token vì đồng hồ chưa trùng khít. Nhưng dung sai làm rộng vùng thời gian chấp nhận token ở **cả hai đầu `nbf` và `exp`**, nên việc chọn nó là một quyết định bảo mật và vận hành.

Mục tiêu bài học là hiểu chính xác `exp`, `nbf`, phân biệt `iat`, xử lý NumericDate, cấu hình `JwtTimestampValidator` trong Spring Security, và chọn mức dung sai phù hợp với access token TTL cùng tình trạng đồng bộ giờ thực tế.

## 1. Kiểm tra thời gian nằm ở đâu trong Resource Server?

~~~text
Client gửi Authorization: Bearer <JWT>
              |
              v
Spring Security Resource Server
              |
              +-- Xác minh chữ ký JWS bằng khóa tin cậy
              |
              +-- Kiểm tra issuer (iss)
              |
              +-- Kiểm tra audience (aud)
              |
              +-- Kiểm tra exp: JWT hết hạn chưa?
              |
              +-- Kiểm tra nbf: JWT đã có hiệu lực chưa?
              |
              +-- Kiểm tra profile/claim nghiệp vụ khác
              |
              +-- Ánh xạ scope thành authorities
              |
              +-- Kiểm tra quyền endpoint và tài nguyên
              |
              v
          200 / 401 / 403
~~~

Thời điểm `exp` và `nbf` được đọc từ payload JWT dạng JWS có thể hiển thị bằng Base64URL decoder. Tuy nhiên **đọc được claim không có nghĩa claim đáng tin**. Người gửi có thể tạo JSON với `exp` ở rất xa trong tương lai. Chỉ một bộ giải mã/xác minh JWT được cấu hình đúng mới có thể dùng claim đó để đưa ra quyết định xác thực.

Ví dụ token có chữ ký hợp lệ nhưng quá hạn vẫn phải bị từ chối. Token chưa hết hạn nhưng không đúng `aud` cũng phải bị từ chối. Token hợp lệ và đúng audience vẫn có thể bị từ chối `403` vì thiếu scope hoặc quyền đối với một bản ghi cụ thể.

## 2. `exp`: thời điểm token hết hiệu lực

RFC 7519 định nghĩa `exp` là thời điểm mà JWT **không còn được phép chấp nhận để xử lý**. Khi không xét clock skew, thời gian hiện tại phải **nhỏ hơn** thời điểm `exp`.

Ví dụ:

~~~json
{
  "iss": "https://idp.example.com/realms/shop",
  "sub": "alice",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "exp": 2000000300
}
~~~

`exp=2000000300` là **mốc thời gian tuyệt đối**, không phải “token còn 300 giây kể từ lúc API nhận request”. Nếu một client gọi lại token sau khi hết hạn, giá trị `exp` không tự dịch sang thời điểm mới.

Không được tự gia hạn bằng cách client sửa `exp` trong payload: điều đó làm hỏng chữ ký JWS. Muốn tiếp tục truy cập API, client cần nhận access token mới từ Authorization Server qua OAuth 2.0 flow phù hợp.

### Ranh giới đúng tại `exp`

Theo ngữ nghĩa RFC 7519, nếu thời điểm hiện tại đã tới đúng `exp`, JWT không còn hiệu lực trong mô hình **không có leeway**. Cần chú ý đơn vị giây và precision, vì chương trình có thể so sánh `Instant` ở mức nano giây trong khi token dùng NumericDate nguyên giây.

Không dùng việc làm tròn hoặc sai lệch múi giờ để “sửa” một `exp` đã quá hạn. Mọi dung sai phải là chính sách được cấu hình rõ ràng.

## 3. `nbf`: thời điểm token bắt đầu có hiệu lực

RFC 7519 định nghĩa `nbf` là thời điểm **trước đó JWT chưa được phép chấp nhận**. Khi không có clock skew, thời gian hiện tại phải **lớn hơn hoặc bằng** `nbf`.

Ví dụ:

~~~json
{
  "sub": "alice",
  "nbf": 2000000060,
  "exp": 2000000300
}
~~~

Khoảng hiệu lực lý tưởng:

~~~text
                 Chưa hiệu lực       Có hiệu lực        Đã hết hạn
time -------------------|==================|----------------------->
                       nbf                exp
~~~

Token có `nbf` ở tương lai là một token **chưa được sử dụng** theo chính sách thời gian. Với access token được phép dùng ngay, Authorization Server có thể cấp `nbf` bằng hoặc gần thời điểm phát hành. Một số profile hoặc provider có thể không phát hành `nbf`; việc claim có bắt buộc hay không phải dựa vào hợp đồng của hệ thống.

### Không nhầm `nbf` với `iat`

`iat` là **Issued At**, thời điểm token được phát hành. Nó không tự tương đương với thời điểm bắt đầu hiệu lực. Ba claim khác nhau:

| Claim | Ý nghĩa | Cách dùng chính |
|---|---|---|
| `iat` | Thời điểm phát hành | Kiểm tra tuổi token, chính sách phát hành, audit nếu cần |
| `nbf` | Thời điểm bắt đầu được chấp nhận | Từ chối token được dùng quá sớm |
| `exp` | Thời điểm token hết hiệu lực | Từ chối token quá hạn |

Nếu `iat` bằng `nbf` là do Authorization Server quyết định, không phải vì hai claim có cùng ngữ nghĩa. `iat` cũng không phải sự thay thế cho `exp`.

## 4. NumericDate: giây UTC, không phải mili giây

Các timestamp JWT được biểu diễn theo **NumericDate** của RFC 7519: số giây kể từ `1970-01-01T00:00:00Z` theo cách đếm POSIX, bỏ qua leap seconds. Giá trị NumericDate có thể có phần thập phân, dù nhiều Authorization Server dùng số nguyên.

Ví dụ:

~~~json
{
  "iat": 2000000000,
  "nbf": 2000000060,
  "exp": 2000000300
}
~~~

Ở đây `exp - iat = 300` giây, nếu đó đúng là cách Authorization Server quy định lifetime. Không có claim `iat` thì không thể suy ra trực tiếp thời điểm phát hành chỉ từ `exp`.

### Giây và mili giây là lỗi rất thường gặp

JavaScript `Date.now()` trả mili giây:

~~~javascript
const nowMillis = Date.now();
const nowSeconds = Math.floor(nowMillis / 1000);
~~~

Trong Java:

~~~java
import java.time.Instant;

long nowSeconds = Instant.now().getEpochSecond();
long expirySeconds = Instant.now()
    .plusSeconds(300)
    .getEpochSecond();
~~~

Không dùng trực tiếp `System.currentTimeMillis()` hoặc `Date.now()` làm `exp` JWT. Giá trị đó thường lớn hơn timestamp theo giây khoảng 1.000 lần và dẫn tới thời điểm hết hạn sai nghiêm trọng.

### Múi giờ không ảnh hưởng expiration

Một `Instant` trong Java mô tả thời điểm tuyệt đối. Khi hiển thị UTC hoặc `Asia/Ho_Chi_Minh`, đồng hồ trên màn hình có thể khác nhau 7 giờ nhưng vẫn là cùng một thời điểm.

~~~java
import java.time.Instant;
import java.time.ZoneId;

Instant expiry = Instant.ofEpochSecond(2000000300L);

System.out.println(expiry); // UTC
System.out.println(expiry.atZone(ZoneId.of("Asia/Ho_Chi_Minh")));
~~~

Không cộng thêm bảy giờ vào `exp` vì server đặt tại Việt Nam. Nên dùng `Instant` và `Clock` để so sánh, không so sánh ngày giờ đã format theo locale.

## 5. Quy tắc xác minh khi không có dung sai

Ký hiệu:

- `now`: thời điểm Resource Server đang kiểm tra;
- `nbf`: thời điểm bắt đầu có hiệu lực;
- `exp`: thời điểm hết hạn;
- `S`: clock skew được cho phép.

Nếu `S=0`, ý nghĩa của RFC là:

~~~text
now >= nbf
now < exp
~~~

Với cả hai claim, khoảng được chấp nhận là:

~~~text
nbf <= now < exp
~~~

Ví dụ `nbf = T0 + 20 giây`, `exp = T0 + 180 giây`:

| Thời điểm Resource Server | Ý nghĩa |
|---|---|
| `T0` | Chưa có hiệu lực |
| `T0 + 10 s` | Chưa có hiệu lực |
| `T0 + 20 s` | Đã tới `nbf` |
| `T0 + 100 s` | Đang trong khoảng hợp lệ |
| `T0 + 179 s` | Chưa tới `exp` |
| `T0 + 180 s` | Đã tới ranh giới `exp` |
| `T0 + 200 s` | Quá hạn |

Một bộ kiểm tra thời gian chỉ nên chạy **sau khi token đã qua xử lý JOSE đáng tin**. Nếu đọc payload chưa xác minh rồi dùng `exp` để cấp quyền, kẻ tấn công có thể tự khai báo bất kỳ timestamp nào.

## 6. Vì sao đồng hồ có thể lệch nhau?

Giả sử Authorization Server và hai Resource Server có đồng hồ khác nhau:

~~~text
Authorization Server: 10:00:00 UTC
Resource Server A:    09:59:57 UTC
Resource Server B:    10:00:04 UTC
~~~

AS phát JWT có `nbf=10:00:00`. Khi request tới RS A ngay sau đó, RS A nhìn thấy thời gian local sớm hơn `nbf` ba giây và có thể từ chối token, dù token được AS phát hành để dùng ngay.

Gần lúc hết hạn, RS B có đồng hồ nhanh hơn AS bốn giây có thể cho rằng token đã quá hạn sớm hơn dự kiến.

Những nguyên nhân thường gặp:

- NTP/chrony chưa đồng bộ hoặc mất kết nối tới nguồn thời gian tin cậy.
- Host của máy ảo/container bị lệch đồng hồ.
- Đồng hồ được điều chỉnh sau khi khởi động.
- Nhiều vùng địa lý hoặc node có chất lượng đồng bộ khác nhau.
- Có một phần độ trễ xử lý request giữa AS và RS.

**Clock skew** được thiết kế để bao phủ sai lệch đồng hồ nhỏ như vậy. Nó không thay thế việc đồng bộ giờ hệ điều hành và không nên dùng để che một node lệch vài phút.

## 7. Clock skew ảnh hưởng cả `exp` lẫn `nbf`

Giả sử Resource Server cho phép dung sai `S=30 giây`.

Diễn giải gần đúng của phép kiểm tra là:

~~~text
now + S >= nbf
now - S < exp
~~~

Điều này có hai hệ quả:

1. Token có thể được chấp nhận **sớm hơn `nbf`** trong khoảng skew.
2. Token có thể được chấp nhận **muộn hơn `exp`** trong khoảng skew.

~~~text
                  nbf-S       nbf             exp      exp+S
time ----------------|---------|================|---------|---->
                     |<------ vùng có thể được chấp nhận --->|
                      dung sai 30s              dung sai 30s
~~~

Đây là minh họa ngữ nghĩa leeway. Các phép so sánh đúng tại biên (bằng `exp + S` hoặc `nbf - S`) phụ thuộc cách implementation xử lý equality và precision. Trong hệ thống có yêu cầu thời gian chặt, cần xác nhận behavior của phiên bản Spring Security đang sử dụng.

### Ví dụ rõ ràng về chênh lệch

Giả sử:

~~~text
nbf = T0 + 60 giây
exp = T0 + 300 giây
skew = 30 giây
~~~

| `now` | Trạng thái xét riêng timestamp |
|---|---|
| `T0 + 0 s` | Sớm hơn `nbf` 60 giây: từ chối |
| `T0 + 40 s` | Sớm hơn `nbf` 20 giây: có thể nhận theo skew |
| `T0 + 80 s` | Trong khoảng hiệu lực |
| `T0 + 280 s` | Trong khoảng hiệu lực |
| `T0 + 320 s` | Quá `exp` 20 giây: có thể nhận theo skew |
| `T0 + 350 s` | Quá `exp` 50 giây: từ chối |

Các kết luận “có thể nhận” chỉ nói về **timestamp validation**; JWT vẫn phải có chữ ký hợp lệ, đúng issuer, audience, loại token và quyền cần thiết.

### Không nhầm leeway với gia hạn token

Dung sai **không thay đổi `exp` trong JWT**, không tạo token mới, không phát hành refresh token, và không thực hiện revocation. Đây chỉ là quy tắc Resource Server sử dụng khi so sánh timestamp với `Clock` của nó.

## 8. Spring Security dùng `JwtTimestampValidator`

Trong Spring Security Resource Server JWT, thành phần chính xử lý `exp` và `nbf` là `JwtTimestampValidator`, một `OAuth2TokenValidator<Jwt>`.

Cấu hình Spring Boot cơ bản:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.com/realms/shop
          audiences:
            - orders-api
~~~

Với đường cấu hình Resource Server chuẩn, Spring Security xác minh chữ ký, issuer và các thời hạn token. Tài liệu Spring Security mô tả **clock skew mặc định là 60 giây**. Đây là hành vi mặc định của framework, **không phải con số bắt buộc do RFC 7519 quy định**.

`JwtTimestampValidator` có constructor nhận `Duration`:

~~~java
import java.time.Duration;
import org.springframework.security.oauth2.jwt.JwtTimestampValidator;

JwtTimestampValidator withThirtySeconds =
    new JwtTimestampValidator(Duration.ofSeconds(30));

JwtTimestampValidator strict =
    new JwtTimestampValidator(Duration.ZERO);
~~~

Có thể chỉ định đồng hồ dùng để xác minh qua `setClock(Clock)`:

~~~java
import java.time.Clock;

JwtTimestampValidator validator =
    new JwtTimestampValidator(Duration.ofSeconds(15));

validator.setClock(Clock.systemUTC());
~~~

Việc dùng `Clock.systemUTC()` phản ánh clock hệ thống theo UTC; nó không tự sửa được sai lệch NTP. Trong unit test, có thể thay bằng `Clock.fixed(...)` để kiểm tra các mốc bất biến.

### Claim không có mặt thì sao?

Trong JWT tổng quát theo RFC 7519, `exp` và `nbf` là optional claims. Hợp đồng **access token của một Authorization Server** có thể yêu cầu `exp` luôn có; RFC 9068 định nghĩa profile cụ thể cho JWT access token với các claim cần thiết.

Không mặc định mọi Spring Security version bắt buộc cả hai claim. Ví dụ API `JwtTimestampValidator` ở các phiên bản Spring Security 7 cung cấp cấu hình riêng cho phép hoặc không cho phép thiếu `exp`/`nbf`. Nếu hệ thống bắt buộc `exp` để bảo đảm token có thời hạn, hãy **thực thi required-exp policy rõ ràng**.

## 9. Cấu hình dung sai tùy chỉnh mà vẫn giữ issuer và audience

Nếu cần thay mặc định 60 giây bằng một giá trị được tổ chức chọn, có thể tạo `JwtDecoder` và gắn một bộ validators có chủ đích.

Ví dụ sau dùng Spring Security Servlet và một JWKS URI đáng tin để xác minh chữ ký; nó chọn **20 giây** chỉ như một tham số minh họa:

~~~java
package com.example.orders.security;

import java.time.Duration;
import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtClaimValidator;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtIssuerValidator;
import org.springframework.security.oauth2.jwt.JwtTimestampValidator;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

@Configuration
public class JwtValidationConfig {

    private static final String ISSUER =
        "https://idp.example.com/realms/shop";

    private static final String JWKS_URI =
        "https://idp.example.com/realms/shop/protocol/openid-connect/certs";

    @Bean
    JwtDecoder jwtDecoder() {
        NimbusJwtDecoder decoder =
            NimbusJwtDecoder.withJwkSetUri(JWKS_URI).build();

        OAuth2TokenValidator<Jwt> timestamps =
            new JwtTimestampValidator(Duration.ofSeconds(20));

        OAuth2TokenValidator<Jwt> issuer =
            new JwtIssuerValidator(ISSUER);

        OAuth2TokenValidator<Jwt> audience =
            new JwtClaimValidator<List<String>>(
                "aud",
                aud -> aud != null && aud.contains("orders-api")
            );

        OAuth2TokenValidator<Jwt> requireExpiry =
            jwt -> jwt.getExpiresAt() != null
                ? OAuth2TokenValidatorResult.success()
                : OAuth2TokenValidatorResult.failure(
                    new OAuth2Error(
                        "invalid_token",
                        "exp claim is required",
                        null
                    )
                );

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                timestamps,
                issuer,
                audience,
                requireExpiry
            )
        );

        return decoder;
    }
}
~~~

Bộ validator này thể hiện rõ:

- `JwtTimestampValidator`: `exp`/`nbf` với clock skew 20 giây.
- `JwtIssuerValidator`: token phải đến từ issuer được tin.
- `JwtClaimValidator`: audience phải chứa `orders-api`.
- `requireExpiry`: token không có `exp` bị từ chối theo hợp đồng ứng dụng.

**Chú ý:** Khi tự tạo `JwtDecoder` bean, Spring Boot thường không tạo decoder mặc định nữa. Các YAML property như `issuer-uri` và `audiences` có thể **không tự áp dụng** cho decoder tùy biến. Đồng thời, code mẫu này thay bộ validators mặc định bằng bộ được khai báo: trong ứng dụng thật, phải giữ thêm bất kỳ kiểm tra token type/profile hoặc validators khác mà version/framework/hợp đồng yêu cầu.

### Vì sao không ghép thêm một timestamp validator vào bộ mặc định?

Ví dụ:

~~~java
OAuth2TokenValidator<Jwt> validators =
    new DelegatingOAuth2TokenValidator<>(
        JwtValidators.createDefaultWithIssuer(issuerUri),
        new JwtTimestampValidator(Duration.ofSeconds(20))
    );
~~~

`JwtValidators.createDefaultWithIssuer(...)` đã chứa timestamp validation với dung sai mặc định. Thêm validator 20 giây **không loại bỏ** validator cũ; có thể khiến cả hai cùng chạy và gây khó hiểu khi đánh giá giá trị skew đang thực sự áp dụng.

Khi muốn **thay** quy tắc thời gian, cần xây dựng bộ validators đúng với yêu cầu, chỉ giữ một timestamp validator có chủ đích và kết hợp lại issuer, audience, token type và những điều kiện khác. Không bỏ hết validators chỉ để thay clock skew.

### Không tự giả định có Spring Boot property clock-skew

Một số phiên bản/framework khác cung cấp property điều chỉnh leeway, nhưng không nên tự thêm một property không tồn tại rồi tưởng nó có hiệu lực. Với Spring Security, `JwtTimestampValidator(Duration)` trong `JwtDecoder` là cách cấu hình tường minh. Hãy đối chiếu property list của chính phiên bản Spring Boot đang dùng.

## 10. Bảo vệ endpoint sau khi token hợp lệ

Ví dụ filter chain bảo vệ `orders-api`:

~~~java
package com.example.orders.security;

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
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyRequest().authenticated()
            )
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults())
            )
            .build();
    }
}
~~~

Token có timestamp hợp lệ nhưng thiếu `SCOPE_orders.write` vẫn không được POST. JWT có scope đọc đơn hàng cũng không mặc nhiên cho phép xem mọi đơn hàng của khách khác; service phải kiểm tra quyền trên từng tài nguyên.

`401 Unauthorized` thường liên quan token không thể xác thực, bao gồm hết hạn hoặc chưa có hiệu lực. `403 Forbidden` thường liên quan thiếu quyền sau khi đã xác thực. HTTP status thực tế có thể phụ thuộc error handler và cấu hình nhiều filter chain.

## 11. Chọn clock skew theo đồng hồ thực tế và rủi ro

Không có một số giây chuẩn cho mọi hệ thống. Cách lựa chọn nên dựa trên:

1. **Mức lệch thực tế** giữa AS và các node RS theo NTP/chrony, không chỉ theo cảm giác.
2. **Biên dự phòng** hợp lý cho độ trễ và điều chỉnh đồng hồ nhỏ.
3. **Access token lifetime**: skew càng lớn so với TTL, giá trị `exp` càng kém ý nghĩa trong việc giới hạn replay.
4. **Độ nhạy của thao tác**: API thanh toán/đổi quyền có thể yêu cầu cửa sổ chấp nhận chặt hơn một API đọc dữ liệu thông thường.
5. **Số lượng và vị trí node**: phải xét node lệch nhiều nhất, nhưng không dùng skew để che node bị lỗi thời gian nghiêm trọng.
6. **Chính sách revocation và incident response**: một JWT chỉ verify cục bộ không tự biết token đã bị thu hồi giữa vòng đời.

### Các con số ví dụ

| Hệ thống | Điều cần xem xét |
|---|---|
| AS và RS đồng bộ tốt, lệch đo được chỉ vài giây | Dung sai nhỏ có thể đủ; giám sát NTP liên tục |
| Nhiều zone có sai khác đồng hồ nhỏ nhưng biến động | Dùng biên dự phòng theo số liệu, sửa node lệch bất thường |
| Token sống 30–60 giây | Dung sai 60 giây có thể quá lớn so với TTL |
| Token sống hàng chục phút, API ít nhạy cảm | Dung sai mặc định có thể được đánh giá, nhưng không bỏ kiểm soát |
| API thao tác nhạy cảm hoặc cần thu hồi nhanh | Giảm lệch đồng hồ, TTL ngắn, cân nhắc thêm kiểm tra trạng thái và chính sách riêng |

**60 giây mặc định của Spring Security** là điểm tham chiếu về hành vi framework. Các giá trị 0, 5, 10, 20 hoặc 30 giây chỉ là **ví dụ cấu hình**, không phải lời khuyên cố định. Chọn nhỏ nhất phù hợp với sai số quan sát được và yêu cầu vận hành.

### Vì sao không đặt skew bằng vài phút?

Nếu access token sống 60 giây mà RS cho phép skew 180 giây, cửa sổ acceptance có thể bị nới quá lớn so với lifetime. Khi token bị lộ, rủi ro sử dụng lại có thể kéo dài hơn dự kiến.

Nếu đồng hồ node bị lệch vài phút, cần **sửa dịch vụ đồng bộ giờ** và nguyên nhân hạ tầng. Nới lỏng validation chỉ che sự cố và làm yếu ranh giới bảo mật.

## 12. Kiểm thử chính xác bằng `Clock.fixed`

Các test dùng `Thread.sleep(...)` để chờ token hết hạn thường chậm và dễ chập chờn. `JwtTimestampValidator#setClock` cho phép tạo test xác định mà không cần chờ thời gian thật.

Ví dụ JUnit 5 chỉ kiểm tra **logic timestamp validator**, không kiểm tra JWS signature:

~~~java
package com.example.orders.security;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;

import org.junit.jupiter.api.Test;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtTimestampValidator;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class JwtTimestampValidatorTest {

    @Test
    void acceptsTokenSlightlyBeforeNbfWithinLeeway() {
        Instant now = Instant.parse("2026-01-01T00:00:00Z");

        Jwt jwt = Jwt.withTokenValue("unit-test-token")
            .header("alg", "RS256")
            .claim("sub", "alice")
            .notBefore(now.plusSeconds(20))
            .expiresAt(now.plusSeconds(120))
            .build();

        JwtTimestampValidator validator =
            new JwtTimestampValidator(Duration.ofSeconds(30));

        validator.setClock(Clock.fixed(now, ZoneOffset.UTC));

        assertFalse(validator.validate(jwt).hasErrors());
    }

    @Test
    void rejectsTokenExpiredBeyondLeeway() {
        Instant now = Instant.parse("2026-01-01T00:00:00Z");

        Jwt jwt = Jwt.withTokenValue("unit-test-token")
            .header("alg", "RS256")
            .claim("sub", "alice")
            .notBefore(now.minusSeconds(120))
            .expiresAt(now.minusSeconds(40))
            .build();

        JwtTimestampValidator validator =
            new JwtTimestampValidator(Duration.ofSeconds(30));

        validator.setClock(Clock.fixed(now, ZoneOffset.UTC));

        assertTrue(validator.validate(jwt).hasErrors());
    }
}
~~~

`Jwt` trong test là object giả lập; token string không được ký. Các test này cho thấy cách kiểm tra `exp`/`nbf`, **không** chứng minh Resource Server đang xác minh signature, issuer hay audience đúng. Nếu cần chứng minh toàn bộ đường xác thực, phải có integration test với JWT được ký bằng test key và decoder có cấu hình tương ứng.

Nên xem các trường hợp: token nằm hẳn trong khoảng; quá sớm hơn skew; sớm ít hơn skew; quá hạn ít/nhiều hơn skew; claim `exp` thiếu hoặc sai kiểu; `nbf > exp`; node dùng đồng hồ nhanh/chậm; và ranh giới chính xác. Những trường hợp đó giúp xác định policy của version framework cụ thể.

## 13. Nhiều instance có thể đưa ra quyết định khác nhau

Giả sử:

~~~text
Authorization Server: 10:00:00 UTC

orders-rs-1:          09:59:58 UTC
orders-rs-2:          10:00:02 UTC
orders-rs-3:          10:00:48 UTC
~~~

Một token mới cấp có `nbf=10:00:00` sẽ được đánh giá khác nhau ở các node nếu không có leeway. Nhưng nếu chỉ một node lệch 48 giây, tăng skew trên toàn hệ thống lên 60 giây có thể che mất lỗi NTP của node đó.

Giải pháp lâu dài là:

- Theo dõi NTP/chrony và trạng thái đồng bộ của node/VM host.
- Điều tra node có clock drift lớn thay vì sửa mọi Resource Server theo node sai.
- Giữ chính sách skew nhất quán giữa các node của cùng API nếu muốn tránh hành vi không đều.
- Phân biệt sai số đồng hồ với network latency, lỗi JWKS và lỗi scope trong telemetry.

Container thường chia sẻ clock kernel của host. Nếu pod có giờ sai, thường cần kiểm tra **node host** chứ không tự chỉnh giờ từng container.

## 14. `exp` không thay thế revocation và logout

Token có `exp` hợp lệ không đồng nghĩa **chưa bị thu hồi**.

Ví dụ:

1. AS phát access token JWT sống 10 phút.
2. Sau 2 phút, người dùng logout hoặc tài khoản bị khóa.
3. Resource Server chỉ xác minh chữ ký/claims cục bộ, không kiểm tra revocation state.
4. Token cũ vẫn có thể vượt qua kiểm tra timestamp cho tới khi hết hạn (cộng dung sai nếu cấu hình cho phép).

Nếu cần thu hồi gần như tức thời, hệ thống có thể cân nhắc introspection, denylist, phiên bản quyền, TTL ngắn hoặc cơ chế kiểm tra trạng thái khác. Clock skew chỉ giúp dung hòa sai khác thời gian, **không kiểm tra trạng thái token tại Authorization Server**.

Tương tự, client không thể tự kéo dài token bằng cách thay payload. Nó phải xin access token mới theo cơ chế OAuth 2.0 hợp lệ.

## 15. Chẩn đoán lỗi `401` liên quan timestamp

| Triệu chứng | Nguyên nhân có thể | Hướng điều tra |
|---|---|---|
| Token vừa phát hành bị 401 vài giây, rồi tự dùng được | Clock RS chậm hơn AS, `nbf` ở tương lai | Đồng bộ NTP, xác nhận `nbf` và skew |
| Token gần hết hạn bị 401 trên một node nhưng node khác nhận | Clock drift hoặc config khác nhau | So sánh đồng hồ/config các node |
| Token đã qua `exp` nhưng vẫn được chấp nhận thêm ít giây | Leeway cuối kỳ | Kiểm tra `JwtTimestampValidator` |
| Token được chấp nhận trước `nbf` | Leeway đầu kỳ | Đánh giá skew và yêu cầu mở quyền |
| `exp` lớn bất thường | Token generator dùng milliseconds thay seconds | Kiểm tra NumericDate |
| Token thiếu `exp` vẫn được nhận | Policy không yêu cầu claim hoặc validator cho phép thiếu | Thêm required-exp validation theo contract |
| Custom decoder không kiểm tra issuer/audience | Validator mặc định bị thay khi cấu hình skew | Kiểm tra `setJwtValidator` |
| JWT có thời gian hợp lệ nhưng vẫn 401 | Chữ ký, issuer, audience hoặc token type sai | Kiểm tra đường xác minh token đầy đủ |
| JWT xác thực được nhưng request trả 403 | Thiếu scope hoặc quyền dữ liệu | Kiểm tra authorities/authorization |
| Sau deploy, nhiều request bị lỗi thời gian | NTP/host clock, config mới hoặc token format | Theo dõi theo node và phiên bản |

Một lệnh đơn giản trong Linux/container:

~~~bash
date -u
date +%s
~~~

Hai lệnh giúp xem giờ UTC và Unix seconds của máy đang chạy. Dùng công cụ hạ tầng để xem NTP offset và sync status. Không tự sửa giờ production tùy tiện: đồng hồ ảnh hưởng cả database, log correlation, scheduler và chứng chỉ TLS.

### Không log token để debug

Bearer JWT là credential. Tránh ghi nguyên header `Authorization` hoặc full JWT vào log. Có thể ghi loại lỗi, trace ID, node ID, giá trị skew được cấu hình và các thông số ít nhạy cảm theo chính sách tổ chức:

~~~text
event=jwt_authentication_failed
path=/api/orders
reason=expired_token
node=orders-rs-2
configuredClockSkewSeconds=20
traceId=75a1...
bearerToken=[REDACTED]
~~~

Nếu cần xem claim thời gian của token thật, dùng công cụ nội bộ an toàn với phạm vi truy cập phù hợp. Công cụ Base64URL decoder chỉ đọc dữ liệu, không thay thế xác minh chữ ký.

## 16. Tình huống thực tế

### Tình huống A — AS và RS lệch 7 giây

AS phát JWT cho phép dùng ngay, có `nbf` bằng thời điểm AS phát hành. RS chậm 7 giây và skew là 0, nên request đầu có thể bị từ chối. **Cách xử lý:** đồng bộ giờ trước, sau đó cân nhắc leeway nhỏ theo sai số thực tế.

### Tình huống B — RS nhanh 45 giây

JWT còn 30 giây theo đồng hồ AS, nhưng RS nhanh 45 giây và leeway 5 giây. RS có thể xem token đã hết hạn. **Cách xử lý:** sửa clock drift tại node, không đơn thuần tăng leeway vô hạn.

### Tình huống C — Access token sống 30 giây

AS phát token ngắn hạn để giảm nguy cơ replay; RS vẫn dùng skew 60 giây. Dung sai có thể lớn hơn lifetime. **Cách xử lý:** xác định yêu cầu TTL và cấu hình skew phù hợp, kết hợp đồng bộ giờ tốt.

### Tình huống D — Token đã bị revoke

JWT còn `exp` trong tương lai nhưng AS đã revoke. RS chỉ verify cục bộ có thể vẫn chấp nhận. **Cách xử lý:** thiết kế introspection/denylist hoặc biện pháp thu hồi phù hợp; `exp` không tự biết trạng thái revoke.

### Tình huống E — Client clock sai

Đồng hồ trình duyệt lệch 20 phút nhưng AS và RS đồng bộ đúng. Client có thể refresh token không đúng lúc, nhưng RS vẫn phải dùng clock đáng tin của chính nó để validate. Không tin `X-Client-Time` hay request `Date` làm nguồn thời gian thay thế.

### Tình huống F — Developer chỉ gắn timestamp validator

~~~java
decoder.setJwtValidator(
    new JwtTimestampValidator(Duration.ofSeconds(15))
);
~~~

Đoạn trên có thể **thay** toàn bộ validators đang được sử dụng, làm mất issuer/audience hoặc profile validation. Phải gắn bộ validators đầy đủ theo hợp đồng token.

## 17. Những hiểu nhầm cần tránh

**“`exp` là số giây token sống.”** Không. Nó là mốc thời gian tuyệt đối; lifetime có thể suy ra từ chênh lệch mốc phát hành và hết hạn khi các claim có mặt.

**“`nbf` và `iat` là một.”** Không. Một claim nói thời điểm được phép sử dụng, một claim nói thời điểm phát hành.

**“Ở Việt Nam phải cộng 7 giờ vào `exp`.”** Không. NumericDate là thời điểm UTC tuyệt đối.

**“Clock skew chỉ gia hạn `exp`.”** Không. Nó còn cho phép chấp nhận token hơi sớm so với `nbf`.

**“Mặc định 60 giây là yêu cầu của RFC.”** Không. Đó là mặc định được Spring Security mô tả; RFC chỉ cho phép leeway nhỏ tùy hệ thống.

**“Tăng skew vài phút sẽ sửa triệt để lỗi token mới bị 401.”** Không. Phải kiểm tra đồng bộ giờ và quy trình cấp token.

**“Thêm một `JwtTimestampValidator` vào `JwtValidators.createDefaultWithIssuer(...)` chắc chắn thay skew mặc định.”** Không. Có thể tồn tại hai validator thời gian cùng chạy.

**“Spring Boot nào cũng có property `jwt.clock-skew`.”** Không được giả định. Dùng cơ chế `JwtTimestampValidator` hoặc property thực sự có tài liệu cho phiên bản đang dùng.

**“JWT thiếu `exp` chắc chắn bị từ chối trong mọi framework version.”** Không. Cần xem profile và cấu hình required claim.

**“Đã verify chữ ký thì không cần kiểm tra thời gian.”** Sai. Chữ ký bảo vệ tính toàn vẹn, không làm token có hiệu lực mãi.

**“Có `exp` là đã có revocation tức thời.”** Sai. Token chưa hết hạn có thể bị thu hồi ở AS mà RS xác minh cục bộ không biết.

## 18. Câu hỏi tự kiểm tra

**1.** JWT có `exp=2000000300`. Đây có phải TTL 300 giây từ lúc RS nhận token?

> Không, đó là NumericDate tuyệt đối. RS so sánh với `now` và leeway được cấu hình.

**2.** `nbf` còn 12 giây trong tương lai, skew là 20 giây. Timestamp validator có thể chấp nhận không?

> Có, theo cơ chế leeway; nhưng chữ ký và những claim khác vẫn phải hợp lệ.

**3.** Token đã hết hạn 35 giây, skew là 20 giây. Có vượt qua kiểm tra timestamp không?

> Không, vì đã vượt ngoài dung sai.

**4.** Vì sao skew 120 giây là vấn đề nếu access token chỉ sống 60 giây?

> Dung sai lớn hơn lifetime có thể làm suy yếu mục tiêu token sống ngắn và tăng cửa sổ replay.

**5.** Trong Spring Security, thành phần nào điều chỉnh dung sai?

> `JwtTimestampValidator(Duration)`, thường gắn với `JwtDecoder` và các validators khác.

**6.** Nếu một node lệch giờ vài phút, nên sửa clock hay tăng leeway?

> Sửa clock/NTP của node. Leeway chỉ nên bao phủ sai lệch nhỏ.

**7.** Vì sao sau khi tùy chỉnh `JwtDecoder` phải kiểm tra issuer và audience?

> Vì bean/validator tùy biến có thể thay thế default configuration. Token có thời gian hợp lệ vẫn không nhất thiết thuộc issuer hoặc API được tin.

**8.** `iat` có thay thế `nbf` được không?

> Không; hai claim phục vụ mục đích khác nhau.

## 19. Tài liệu tham khảo

- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519): định nghĩa `exp`, `nbf`, `iat`, NumericDate và leeway để xử lý clock skew.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): các claim và yêu cầu của JWT access token profile.
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): xác minh JWT và chính sách bảo mật.
- [Spring Security — OAuth 2.0 Resource Server JWT (Servlet)](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): xác minh `iss`, `exp`, `nbf` và custom timestamp validation.
- [Spring Security — JwtTimestampValidator API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/jwt/JwtTimestampValidator.html): `Duration`, `setClock` và xử lý timestamp claims.
- [Spring Security — JwtValidators API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/jwt/JwtValidators.html): các default validators.
- [Spring Security — JwtIssuerValidator API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/jwt/JwtIssuerValidator.html): kiểm tra issuer.
- [Spring Security — NimbusJwtDecoder API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/jwt/NimbusJwtDecoder.html): decoder và `setJwtValidator`.
- [Spring Boot — OAuth2 Resource Server](https://docs.spring.io/spring-boot/reference/security/oauth2.html): auto-configuration của JWT Resource Server.

Khi thiết kế policy thời gian, hãy giữ ba nguyên tắc: **JWT phải được xác minh trước khi tin `exp`/`nbf`; Resource Server phải có đồng hồ được đồng bộ; và clock skew phải nhỏ, được chọn dựa trên sai số thực tế cùng mức rủi ro của token**. Lựa chọn leeway tốt giúp API ổn định mà không đánh đổi quá nhiều ý nghĩa bảo mật của thời hạn access token.
