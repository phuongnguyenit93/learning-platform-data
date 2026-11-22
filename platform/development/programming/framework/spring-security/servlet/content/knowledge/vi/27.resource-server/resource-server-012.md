# Giới hạn thu hồi JWT, thời gian sống token và kiểm thử token không hợp lệ trong Spring Security Resource Server

## 1. Mục tiêu và bối cảnh

Một API Java dùng **Spring Security OAuth2 Resource Server** thường nhận access token dưới dạng **JWT** qua header **Authorization: Bearer ...**. JWT có chữ ký có thể được resource server kiểm tra cục bộ nhờ khóa công khai của nhà phát hành (Authorization Server, viết tắt AS). Điều này giảm việc gọi AS trên mọi request, nhưng dẫn đến một đánh đổi quan trọng:

> JWT đã phát hành và còn hợp lệ theo chữ ký, thời gian, issuer, audience và các quy tắc của API thường **không thể bị thu hồi tức thì chỉ bằng cách đăng xuất hoặc xóa refresh token tại AS**.

Giả sử người dùng nhận access token lúc 10:00, **exp = 10:15**. Lúc 10:05 người dùng đăng xuất, nhưng token bị lộ trước đó. Nếu API chỉ xác minh JWT một cách stateless thì bản sao token vẫn có thể được chấp nhận cho đến khi hết hạn, tùy clock skew và chính sách bổ sung. Đây là **giới hạn thu hồi JWT**, không phải lỗi thư viện Spring Security.

Bài học tập trung vào ba nhiệm vụ:

1. **Hiểu chính xác JWT hợp lệ có nghĩa gì:** chữ ký và thuật toán, **iss**, **aud**, **exp**, **nbf**, **iat**, scopes/authorities và khả năng thu hồi.
2. **Thiết kế thời gian sống và cơ chế thu hồi phù hợp rủi ro:** access token ngắn hạn, refresh token rotation, denylist theo **jti**, introspection, key rotation và cache.
3. **Kiểm thử token không hợp lệ** trong Spring Security Servlet: thiếu token, token hỏng, hết hạn, chưa đến thời điểm sử dụng, sai issuer/audience, sai chữ ký, quá TTL và thiếu quyền; phân biệt rõ **401** với **403**.

Bối cảnh: Spring Boot 3.x / Spring Security 6.x / Java 17+, dùng servlet web application và **OAuth2 Resource Server JWT**, không phải Spring Security WebFlux.

## 2. JWT access token chứa gì?

Một JWT dạng JWS thường có ba phần được mã hóa Base64URL:

~~~text
BASE64URL(header).BASE64URL(payload).BASE64URL(signature)
~~~

Ví dụ payload khái niệm (không phải token thực có thể dùng để đăng nhập):

~~~json
{
  "iss": "https://issuer.example.test",
  "sub": "alice",
  "aud": ["urn:orders-api"],
  "iat": 1790000000,
  "nbf": 1790000000,
  "exp": 1790000900,
  "jti": "random-unique-token-id",
  "scope": "orders.read"
}
~~~

Các timestamp chỉ nhằm minh họa cách biểu diễn **NumericDate** (giây từ Unix epoch), không phải lịch cấp token trong môi trường demo.

| Claim / thành phần | Ý nghĩa | Chính sách nên kiểm tra |
| --- | --- | --- |
| **Chữ ký JWS** và **alg** | Token có bị sửa không, được ký bằng thuật toán/khóa đáng tin hay không | Dùng decoder với thuật toán cho phép và khóa được quản lý tin cậy; không tin alg tùy ý từ token |
| **iss** | Định danh bên phát hành token | So khớp chính xác issuer đã cấu hình |
| **aud** | Resource/API mà token được cấp để gọi | Phải chứa audience của API; không chỉ dựa vào issuer |
| **exp** | Thời điểm hết hiệu lực | Từ chối token hết hạn, xét clock skew được giới hạn |
| **nbf** | Chưa hợp lệ trước thời điểm này | Từ chối token được dùng quá sớm |
| **iat** | Thời điểm phát hành | Dùng để giới hạn tuổi tối đa và kiểm tra tính hợp lý khi policy yêu cầu |
| **jti** | ID token, thường dùng cho replay/revocation tracking | Nên duy nhất; chỉ có ý nghĩa thu hồi khi API **tra cứu trạng thái** |
| **scope/scp**, roles | Quyền được cấp cho API | Kiểm tra trên từng endpoint; Spring thường ánh xạ scope thành authority **SCOPE_...** |

**Payload JWT thông thường không được mã hóa bí mật.** Base64URL chỉ là encoding, không phải encryption. Không đặt mật khẩu, client secret, dữ liệu cá nhân nhạy cảm hoặc thông tin có thể lạm dụng vào claim chỉ vì token đã được ký.

**Token chưa hết hạn không đồng nghĩa được phép truy cập mọi API.** Chữ ký đúng nhưng **aud** sai hoặc thiếu **orders.read** vẫn phải bị từ chối.

## 3. Giới hạn thu hồi của JWT và lựa chọn kiến trúc

### 3.1. Vì sao logout không thu hồi JWT đã phát hành?

Resource server xác thực chữ ký bằng public key lấy từ JWK Set và kiểm tra claim ngay tại API. Nếu không truy vấn trạng thái bên ngoài, nó **không biết** người dùng vừa logout, đổi mật khẩu, bị khóa tài khoản hoặc bị nhân viên quản trị thu hồi phiên.

Các thao tác sau **không tự hủy** JWT access token đang lưu ở client hoặc attacker:

- Xóa session của web ứng dụng.
- Xóa token trong bộ nhớ/trình duyệt.
- Thu hồi **refresh token** tại AS.
- Đổi mật khẩu nếu resource server chỉ tin JWT tĩnh và không kiểm tra trạng thái tài khoản.
- Xóa người dùng khỏi một nhóm nếu quyền đã được ghi sẵn vào JWT và API không truy vấn quyền hiện tại.

Các biện pháp này có thể ngăn **lần cấp token tiếp theo**, nhưng không sửa lại chữ ký hoặc claim của JWT đã tồn tại. Khi yêu cầu thu hồi **tức thì**, phải thêm cơ chế trạng thái hoặc đổi mô hình token.

### 3.2. Bốn chiến lược phổ biến

| Chiến lược | Tác dụng | Đổi lại |
| --- | --- | --- |
| **Access JWT TTL ngắn** | Giới hạn cửa sổ dùng token bị lộ; không cần mỗi API gọi AS | Không thu hồi ngay: token vẫn sống tới gần **exp** |
| **Denylist jti** chia sẻ Redis/DB | Khóa từng JWT trước exp, ví dụ lúc logout hoặc sự cố | API phải truy vấn trạng thái, có bài toán nhất quán, uptime, TTL và scale |
| **Opaque access token + introspection** | AS có thể trả **active=false** sau khi thu hồi | Độ trễ/phụ thuộc AS; cache introspection làm thu hồi trễ tương ứng |
| **Đổi/thu hồi khóa ký** | Có thể khiến cả nhóm JWT ký bằng khóa cũ không còn xác minh được | Ảnh hưởng diện rộng, cache JWK ở nhiều API, rủi ro gián đoạn; không phù hợp thu hồi một người |

Mặc định hợp lý cho nhiều API là **access token ngắn hạn + refresh token được bảo vệ, luân phiên và có khả năng thu hồi**. Đây vẫn là lựa chọn đánh đổi; hệ thống tài chính/quản trị đặc quyền có thể cần denylist hoặc introspection để đáp ứng thời gian thu hồi nghiêm ngặt.

### 3.3. Denylist theo jti: cần thiết kế cả vòng đời

Một quy trình triển khai có thể là:

1. AS phát access JWT với **jti** duy nhất, **iss** và **exp**. Resource server kiểm tra chữ ký, issuer, audience và expiry như bình thường.
2. Khi muốn thu hồi một access JWT, backend xác thực quyền yêu cầu thu hồi, rồi ghi một bản ghi denylist theo cặp **(iss, jti)**. Tránh chỉ dựa vào **sub** nếu mục tiêu là thu hồi một token.
3. Mỗi API request, sau khi decoder xác thực JWT, resource server tra denylist. Nếu tìm thấy bản ghi vẫn còn hiệu lực, từ chối token.
4. Bản ghi denylist có thời gian sống xấp xỉ **exp − thời điểm hiện tại + độ lệch đồng hồ tối đa được chấp nhận**. Sau đó bản thân JWT không còn dùng được nên có thể xóa bản ghi.

Ví dụ thuật toán lưu trữ (pseudocode, **không** phải lệnh Redis copy-paste):

~~~text
revocationKey = "revoked:" + hash(issuer + "|" + jti)
remainingSeconds = max(1, expEpochSeconds - nowEpochSeconds + clockSkewSeconds)

SET revocationKey "1" EX remainingSeconds

on each authenticated JWT request:
    validate signature + issuer + audience + exp + nbf
    if revocationStore.contains(revocationKey):
        reject as invalid token
    continue with authorization
~~~

Trong môi trường nhiều instance, **HashMap chỉ nằm trong JVM không đủ**: instance A có thể không biết lệnh thu hồi vừa ghi ở instance B, và dữ liệu mất khi restart. Dùng kho lưu trữ chung hoặc hệ thống trạng thái phiên được thiết kế cho trường hợp này.

Các điều kiện bắt buộc trước khi dùng denylist:

- **jti thiếu hoặc không duy nhất:** quyết định có từ chối token hay không. Nếu chính sách yêu cầu thu hồi từng token mà AS không phát jti đáng tin, cần sửa phía AS hoặc dùng cơ chế nhận dạng token khác (ví dụ hash của token sau khi đã xác thực).
- **Kho denylist bị lỗi:** phải có chính sách rõ ràng **fail closed** hoặc chấp nhận rủi ro fail open; không im lặng coi kết quả lookup lỗi là **không bị thu hồi** ở API rủi ro cao.
- **Race condition/caching:** nếu API cache kết quả “chưa bị thu hồi” trong 5 phút, thời gian thu hồi thực tế có thể trễ tối đa theo cache. Đo và công bố SLA thu hồi.
- **Rò rỉ dữ liệu:** không lưu nguyên raw JWT; key denylist nên được bảo vệ, không log token và dùng cơ chế TTL/giới hạn tài nguyên.
- **Logout hàng loạt:** thu hồi tất cả token của một người thường cần một cấu trúc bổ sung như **session version**, **issued-before cutoff** cho người dùng, hoặc cơ chế central session; denylist từng jti chưa chắc bao quát token không biết tới.
- **Tin cậy sự kiện:** chỉ AS hoặc service đã được xác thực và phân quyền mới được phát lệnh thu hồi, không tin một request bất kỳ tuyên bố rằng jti của người khác bị thu hồi.

### 3.4. Refresh token và thời gian sống

**Access token** được gửi đến resource server; **refresh token** thường chỉ dùng với authorization server / OAuth2 client để lấy access token mới. Không gửi refresh token tới mọi API và không dùng refresh token làm bearer access token.

Một policy mẫu để thảo luận (không phải yêu cầu chuẩn cho mọi hệ thống):

| Loại | Ví dụ thời hạn | Mục đích |
| --- | --- | --- |
| Access JWT | **5–15 phút** | Giảm thời gian token bị lộ còn tác dụng |
| Refresh token | **Giờ/ngày**, tùy độ nhạy và loại client | Giảm tần suất người dùng phải đăng nhập lại |
| Refresh token rotation | Mỗi lần refresh phát token mới, vô hiệu hóa token trước | Hạn chế reuse và hỗ trợ phát hiện token bị đánh cắp |
| Session tuyệt đối | Một thời điểm hết hạn cuối cùng | Không gia hạn đăng nhập vô thời hạn chỉ vì client cứ refresh |

Các thời gian trên là **ví dụ**. Chọn TTL bằng mô hình rủi ro, kỳ vọng trải nghiệm, khả năng thu hồi, độ trễ đồng hồ và chính sách AS. JWT access token có **exp cố định**: một API không tự kéo dài exp của JWT đã ký; phải yêu cầu AS phát **token mới**.

**Clock skew:** resource server có thể chấp nhận một khoảng lệch đồng hồ nhỏ khi so **exp/nbf**. Điều này tránh lỗi do đồng hồ lệch nhưng cũng kéo dài rất nhỏ thời gian token còn dùng được sau exp. Đồng bộ NTP, đặt skew hữu hạn, và trong test dùng thời điểm cách ngưỡng đủ xa (ví dụ 10 phút), tránh flaky test ngay sát giây hết hạn.

### 3.5. Thu hồi bằng khóa và JWKS

JWT thường có header **kid** để decoder chọn public key từ JWK Set. Khi key signing bị lộ, cần rotation / emergency revocation theo quy trình AS, nhưng:

- API có thể đang **cache JWK Set**; xóa key ở AS không bảo đảm API lập tức quên key đã cache.
- Xóa key cũ quá sớm có thể khiến **JWT hợp lệ còn hạn** bị 401 diện rộng.
- Giữ key cũ quá lâu sau sự cố kéo dài rủi ro. Cần quy trình thay khóa, làm mới cache, giám sát và kế hoạch khôi phục.
- Không chấp nhận thuật toán hoặc JWK key source chỉ vì header JWT yêu cầu; decoder phải được cấu hình chính sách tin cậy từ phía server.

**Key rotation không thay thế denylist từng người.** Nó thích hợp cho thay đổi khóa định kỳ hoặc ứng phó sự cố trên phạm vi phát hành.

## 4. Spring Security Resource Server kiểm tra token ở đâu?

Luồng Bearer authentication trong Servlet security chain:

~~~text
GET /api/orders
Authorization: Bearer <jwt>
           │
           ▼
BearerTokenAuthenticationFilter
           │
           ▼
JwtAuthenticationProvider → JwtDecoder
           │                     │
           │                     ├── phân tích compact JWT/JWS
           │                     ├── xác minh chữ ký bằng key đáng tin
           │                     ├── kiểm tra iss / exp / nbf
           │                     ├── kiểm tra aud và policy TTL tùy chỉnh
           │                     └── nếu có: lookup revoke theo jti
           │
           ├── lỗi token → AuthenticationEntryPoint → HTTP 401
           └── token hợp lệ → tạo Authentication / authorities
                                        │
                                        ▼
                              AuthorizationFilter
                                        │
                              thiếu authority → HTTP 403
                              đủ authority   → Controller
~~~

Đặc biệt:

- **401 Unauthorized:** chưa xác thực hoặc token không được chấp nhận (thiếu/malformed/hết hạn/chữ ký sai/issuer sai/audience sai).
- **403 Forbidden:** token đã được xác thực nhưng không đủ quyền truy cập endpoint, ví dụ không có **SCOPE_orders.read**.
- Nếu ứng dụng có bộ xử lý lỗi tùy biến, proxy hoặc nhiều chain, response thực tế có thể khác; test phải gắn vào đúng security chain.
- **Authentication principal** khi JWT thành công thường là đối tượng **Jwt**, còn **JwtAuthenticationToken** chứa authorities rút ra từ scope/scp.
- Việc chỉ thấy chữ ký hợp lệ **không chứng minh** token được phát cho đúng API. Hãy kiểm **aud** thay vì chấp nhận mọi access token cùng issuer.
- Đừng tự viết hàm Base64 decode rồi đọc claims để “xác thực” token. Đọc payload không đồng nghĩa xác minh chữ ký.

## 5. Ví dụ cấu hình Java 17+ với issuer, audience và giới hạn TTL

Ví dụ sau dành cho **Spring Boot 3.x, Spring Security 6.x, ứng dụng Servlet**. Cần một dự án Boot có Gradle wrapper và một AS công bố JWK Set hợp lệ.

Trong **build.gradle**, thêm dependency:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

Tệp **src/main/resources/application.yml**:

~~~yaml
security:
  jwt:
    issuer-uri: "https://issuer.example.test"
    jwk-set-uri: "https://issuer.example.test/.well-known/jwks.json"
    audience: "urn:orders-api"
~~~

Các địa chỉ **example.test** chỉ là dữ liệu minh họa: hãy thay bằng issuer/JWK Set URI thật từ nhà cung cấp đã được tin cậy. Khi dùng **NimbusJwtDecoder.withJwkSetUri**, ứng dụng **không** dựa vào URL issuer để tự dò discovery metadata, vì JWK Set URI được chỉ định trực tiếp; đồng thời ta phải **tự cấu hình kiểm tra issuer** bằng validator (xem mã). Đảm bảo TLS, nơi đặt khóa, khả năng kết nối và chính sách rotation phù hợp.

Tệp **src/main/java/com/example/jwtlimits/JwtLimitsApplication.java**:

~~~java
package com.example.jwtlimits;

import java.time.Duration;
import java.time.Instant;
import java.util.List;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtClaimValidator;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.security.core.annotation.AuthenticationPrincipal;

@SpringBootApplication
public class JwtLimitsApplication {
    public static void main(String[] args) {
        SpringApplication.run(JwtLimitsApplication.class, args);
    }
}

@Configuration
class SecurityConfiguration {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers(HttpMethod.GET, "/api/public/ping").permitAll()
                        .requestMatchers(HttpMethod.GET, "/api/orders")
                            .hasAuthority("SCOPE_orders.read")
                        .anyRequest().authenticated())
                .sessionManagement(session ->
                        session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
                // Chỉ phù hợp với API dùng bearer token ở Authorization header,
                // KHÔNG dùng cookie/session làm credential tự gửi.
                .csrf(AbstractHttpConfigurer::disable)
                .oauth2ResourceServer(oauth2 ->
                        oauth2.jwt(Customizer.withDefaults()))
                .build();
    }

    @Bean
    JwtDecoder jwtDecoder(
            @Value("${security.jwt.jwk-set-uri}") String jwkSetUri,
            @Value("${security.jwt.issuer-uri}") String issuer,
            @Value("${security.jwt.audience}") String audience) {

        NimbusJwtDecoder decoder =
                NimbusJwtDecoder.withJwkSetUri(jwkSetUri).build();
        decoder.setJwtValidator(validators(issuer, audience));
        return decoder;
    }

    static OAuth2TokenValidator<Jwt> validators(
            String issuer, String audience) {

        // Bao gồm kiểm tra issuer và thời gian theo default validators.
        OAuth2TokenValidator<Jwt> standard =
                JwtValidators.createDefaultWithIssuer(issuer);

        OAuth2TokenValidator<Jwt> audienceValidator =
                new JwtClaimValidator<List<String>>(
                        "aud",
                        aud -> aud != null && aud.contains(audience));

        // Policy riêng của API mẫu: yêu cầu iat + exp và TTL tối đa 15 phút.
        OAuth2TokenValidator<Jwt> lifetimeValidator = jwt -> {
            Instant issuedAt = jwt.getIssuedAt();
            Instant expiresAt = jwt.getExpiresAt();
            boolean invalid =
                    issuedAt == null ||
                    expiresAt == null ||
                    !expiresAt.isAfter(issuedAt) ||
                    Duration.between(issuedAt, expiresAt)
                            .compareTo(Duration.ofMinutes(15)) > 0 ||
                    issuedAt.isAfter(Instant.now().plusSeconds(60));

            if (invalid) {
                OAuth2Error error = new OAuth2Error(
                        "invalid_token",
                        "JWT missing iat/exp, has invalid times, or exceeds TTL",
                        null);
                return OAuth2TokenValidatorResult.failure(error);
            }
            return OAuth2TokenValidatorResult.success();
        };

        return new DelegatingOAuth2TokenValidator<>(
                standard, audienceValidator, lifetimeValidator);
    }
}

@RestController
class OrdersController {
    @GetMapping("/api/public/ping")
    String ping() {
        return "pong";
    }

    @GetMapping("/api/orders")
    String orders(@AuthenticationPrincipal Jwt jwt) {
        return "subject=" + jwt.getSubject();
    }
}
~~~

### Phân tích các lựa chọn

1. **Decoder xác minh JWS bằng khóa tin cậy** từ JWK Set URI. Không tự lấy public key từ một URL do attacker đặt trong JWT header. Nếu AS dùng thuật toán không phải mặc định được chấp nhận, hãy cấu hình thuật toán theo hợp đồng với AS, không tin mọi **alg** mà token công bố.
2. **JwtValidators.createDefaultWithIssuer(issuer)** bao gồm các kiểm tra thời gian mặc định như **exp/nbf** và xác nhận **iss** theo chính sách Spring Security. **Clock skew** là yếu tố cần xem xét khi chọn mốc hết hạn/test.
3. **Audience validator** đảm bảo token thực sự dành cho **urn:orders-api**. JWT cho cùng người dùng nhưng gửi tới resource khác không được sử dụng ở API này.
4. **Lifetime validator** là chính sách bổ sung: bắt buộc có **iat** và **exp**, **exp > iat**, không cho khoảng **exp - iat** dài hơn **15 phút**, đồng thời từ chối **iat** quá xa trong tương lai. Kiểm tra **exp - iat** khác với kiểm tra token đã hết hạn: **cả hai** đều cần.
5. **SCOPE_orders.read** là quyền yêu cầu tại endpoint; Spring Security mặc định có thể chuyển **scope: "orders.read"** thành authority tương ứng. JWT hợp lệ nhưng thiếu scope nhận **403**, không phải 401.
6. **STATELESS + csrf.disable()** chỉ phù hợp với API được thiết kế thật sự nhận bearer token do client đặt trong **Authorization** header, không dùng cơ chế cookie/session tự gửi khi cross-origin. Nếu cùng ứng dụng dùng session/cookie cho đăng nhập browser, phải thiết kế CSRF và security chain riêng; không sao chép lệnh disable này cho mọi loại request.
7. **TTL 15 phút** là quy tắc của ví dụ; issuer phải phát access token phù hợp. Một API tự giới hạn max TTL nhỏ hơn issuer là hợp lệ về bảo mật nhưng có thể làm client hiện tại nhận 401: kiểm tra hợp đồng token giữa AS và API khi triển khai.

**Quan trọng:** Không có denylist trong Java demo. Do đó JWT đã phát hành, còn hợp lệ và có scope phù hợp vẫn được chấp nhận dù người dùng logout. Đây là hành vi thiết kế của resource server stateless, không phải tính năng thu hồi bị quên kích hoạt.

## 6. Kiểm thử thật việc xác minh JWT, không chỉ giả principal

Có hai kiểu test phổ biến nhưng **không tương đương**:

| Phương pháp | Có kiểm tra chữ ký / decoder thật? | Dùng để làm gì? |
| --- | --- | --- |
| **MockMvc với .with(jwt())** từ spring-security-test | **Không**: gắn authentication giả | Test authorization/controller khi đã đăng nhập |
| **MockMvc + JWT tự ký bằng private key test + NimbusJwtDecoder dùng public key test** | **Có**, thông qua decoder thật | Test signature, issuer, audience, exp, nbf, TTL, lỗi 401 và scope 403 |

Nếu muốn chứng minh **token hết hạn hoặc chữ ký sai bị từ chối**, dùng cách thứ hai hoặc test trực tiếp JwtDecoder. Không nói một test **.with(jwt())** đã kiểm chứng chữ ký thật, vì nó bỏ qua bước đó.

### 6.1. Bộ integration test với RSA key tạo trong JVM test

Tệp **src/test/java/com/example/jwtlimits/JwtLimitsTest.java** (cùng package với class ứng dụng):

~~~java
package com.example.jwtlimits;

import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.interfaces.RSAPrivateKey;
import java.security.interfaces.RSAPublicKey;
import java.time.Instant;
import java.util.Date;
import java.util.List;
import java.util.UUID;

import com.nimbusds.jose.JOSEObjectType;
import com.nimbusds.jose.JWSAlgorithm;
import com.nimbusds.jose.JWSHeader;
import com.nimbusds.jose.crypto.RSASSASigner;
import com.nimbusds.jwt.JWTClaimsSet;
import com.nimbusds.jwt.SignedJWT;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Primary;
import org.springframework.http.HttpHeaders;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(properties = {
        "security.jwt.issuer-uri=https://issuer.example.test",
        "security.jwt.jwk-set-uri=https://issuer.example.test/jwks",
        "security.jwt.audience=urn:orders-api"
})
@AutoConfigureMockMvc
class JwtLimitsTest {

    static final String ISSUER = "https://issuer.example.test";
    static final String AUDIENCE = "urn:orders-api";

    // Chỉ dành cho test. Không nhúng private key vào source production.
    static final KeyPair TRUSTED_KEY = newRsaKeyPair();
    static final KeyPair OTHER_KEY = newRsaKeyPair();

    @Autowired
    MockMvc mvc;

    @TestConfiguration
    static class LocalDecoderConfig {
        @Bean
        @Primary
        JwtDecoder testJwtDecoder() {
            NimbusJwtDecoder decoder = NimbusJwtDecoder.withPublicKey(
                    (RSAPublicKey) TRUSTED_KEY.getPublic()).build();
            decoder.setJwtValidator(
                    SecurityConfiguration.validators(ISSUER, AUDIENCE));
            return decoder;
        }
    }

    private static KeyPair newRsaKeyPair() {
        try {
            KeyPairGenerator generator = KeyPairGenerator.getInstance("RSA");
            generator.initialize(2048);
            return generator.generateKeyPair();
        } catch (Exception e) {
            throw new IllegalStateException("Cannot create test RSA key", e);
        }
    }

    private String token(
            String issuer,
            String audience,
            Instant issuedAt,
            Instant notBefore,
            Instant expiresAt,
            String scope,
            KeyPair signingKey) throws Exception {

        JWTClaimsSet.Builder claims = new JWTClaimsSet.Builder()
                .issuer(issuer)
                .subject("alice")
                .audience(List.of(audience))
                .issueTime(Date.from(issuedAt))
                .notBeforeTime(Date.from(notBefore))
                .jwtID(UUID.randomUUID().toString());

        if (expiresAt != null) {
            claims.expirationTime(Date.from(expiresAt));
        }
        if (scope != null) {
            claims.claim("scope", scope);
        }

        SignedJWT signedJwt = new SignedJWT(
                new JWSHeader.Builder(JWSAlgorithm.RS256)
                        .type(JOSEObjectType.JWT)
                        .keyID("test-key")
                        .build(),
                claims.build());
        signedJwt.sign(
                new RSASSASigner((RSAPrivateKey) signingKey.getPrivate()));
        return signedJwt.serialize();
    }

    private String validToken() throws Exception {
        Instant now = Instant.now();
        return token(
                ISSUER, AUDIENCE,
                now.minusSeconds(30), now.minusSeconds(30),
                now.plusSeconds(300),
                "orders.read", TRUSTED_KEY);
    }

    private void expectUnauthorized(String jwtValue) throws Exception {
        mvc.perform(get("/api/orders")
                        .header(HttpHeaders.AUTHORIZATION,
                                "Bearer " + jwtValue))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void publicEndpointNeedsNoToken() throws Exception {
        mvc.perform(get("/api/public/ping"))
                .andExpect(status().isOk())
                .andExpect(content().string("pong"));
    }

    @Test
    void missingTokenIs401() throws Exception {
        mvc.perform(get("/api/orders"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void validSignedTokenWorks() throws Exception {
        mvc.perform(get("/api/orders")
                        .header(HttpHeaders.AUTHORIZATION,
                                "Bearer " + validToken()))
                .andExpect(status().isOk())
                .andExpect(content().string("subject=alice"));
    }

    @Test
    void malformedTokenIs401() throws Exception {
        expectUnauthorized("not-a-jwt");
    }

    @Test
    void expiredTokenIs401() throws Exception {
        Instant now = Instant.now();
        expectUnauthorized(token(
                ISSUER, AUDIENCE,
                now.minusSeconds(1800), now.minusSeconds(1800),
                now.minusSeconds(1200),
                "orders.read", TRUSTED_KEY));
    }

    @Test
    void notBeforeInTheFutureIs401() throws Exception {
        Instant now = Instant.now();
        expectUnauthorized(token(
                ISSUER, AUDIENCE,
                now.minusSeconds(60), now.plusSeconds(600),
                now.plusSeconds(720),
                "orders.read", TRUSTED_KEY));
    }

    @Test
    void wrongIssuerIs401() throws Exception {
        Instant now = Instant.now();
        expectUnauthorized(token(
                "https://attacker.example.test", AUDIENCE,
                now.minusSeconds(30), now.minusSeconds(30),
                now.plusSeconds(300),
                "orders.read", TRUSTED_KEY));
    }

    @Test
    void wrongAudienceIs401() throws Exception {
        Instant now = Instant.now();
        expectUnauthorized(token(
                ISSUER, "urn:another-api",
                now.minusSeconds(30), now.minusSeconds(30),
                now.plusSeconds(300),
                "orders.read", TRUSTED_KEY));
    }

    @Test
    void invalidSignatureIs401() throws Exception {
        Instant now = Instant.now();
        expectUnauthorized(token(
                ISSUER, AUDIENCE,
                now.minusSeconds(30), now.minusSeconds(30),
                now.plusSeconds(300),
                "orders.read", OTHER_KEY));
    }

    @Test
    void excessiveLifetimeIs401() throws Exception {
        Instant now = Instant.now();
        expectUnauthorized(token(
                ISSUER, AUDIENCE,
                now.minusSeconds(60), now.minusSeconds(60),
                now.plusSeconds(1800),
                "orders.read", TRUSTED_KEY));
    }

    @Test
    void missingExpiryIs401() throws Exception {
        Instant now = Instant.now();
        expectUnauthorized(token(
                ISSUER, AUDIENCE,
                now.minusSeconds(30), now.minusSeconds(30),
                null,
                "orders.read", TRUSTED_KEY));
    }

    @Test
    void validTokenButMissingScopeIs403() throws Exception {
        Instant now = Instant.now();
        String value = token(
                ISSUER, AUDIENCE,
                now.minusSeconds(30), now.minusSeconds(30),
                now.plusSeconds(300),
                "profile", TRUSTED_KEY);
        mvc.perform(get("/api/orders")
                        .header(HttpHeaders.AUTHORIZATION, "Bearer " + value))
                .andExpect(status().isForbidden());
    }
}
~~~

**Giải thích khả năng chạy:** Trong test context có decoder production và một decoder test **@Primary**. SecurityFilterChain nhận decoder test dùng RSA public key sinh trong JVM. JWT trong từng bài test được ký bằng private key test tương ứng. Vì không dùng **.with(jwt())**, request thật đi qua BearerTokenAuthenticationFilter và Nimbus decoder nên có thể kiểm chứng lỗi cryptographic signature và validators, không cần kết nối IdP.

Chạy từ thư mục gốc dự án Boot đã có Gradle wrapper:

~~~bash
./gradlew test --tests com.example.jwtlimits.JwtLimitsTest
~~~

Trên Windows:

~~~powershell
.\gradlew.bat test --tests com.example.jwtlimits.JwtLimitsTest
~~~

**Kỳ vọng khi môi trường dự án được cấu hình đúng:** 12 bài test đạt. Trong đó public GET và access JWT hợp lệ có **200**; token thiếu/hỏng/hết hạn/chưa có hiệu lực/sai issuer/sai audience/chữ ký sai/quá TTL/thiếu exp có **401**; token hợp lệ nhưng thiếu scope có **403**. Đây là dự kiến từ cấu hình mẫu, không phải kết quả chạy đã được xác nhận. Khi dùng AS thật, hãy thực hiện thêm test end-to-end qua HTTPS/JWKS và token do AS phát.

### 6.2. Những tình huống cần test thêm khi bật denylist

Bộ test trên **chưa** có cơ chế revocation ngoài JWT validation. Khi triển khai denylist thật, bổ sung:

| Test | Kỳ vọng |
| --- | --- |
| Token có chữ ký/claims hợp lệ, jti **chưa** denylist | Được xác thực, rồi kiểm tra quyền |
| Thu hồi một jti, gửi lại **cùng JWT** | Nhận **401 invalid_token** nếu denylist tích hợp vào authentication validator |
| Hai JWT cùng sub nhưng khác jti; thu hồi một token | Chỉ token bị chỉ định bị từ chối nếu policy là thu hồi từng token |
| JWT thiếu jti trong hệ thống bắt buộc thu hồi theo jti | Fail theo policy rõ ràng, không vô tình cho qua |
| Hai instance API nhìn cùng trạng thái Redis/DB | Từ chối đồng nhất sau khi lệnh thu hồi đã ghi thành công |
| Redis/DB không phản hồi | Hành vi đúng policy fail closed/fail open đã phê duyệt; có log/alert |
| Bản ghi denylist hết TTL **sau khi JWT hết hạn** | JWT vẫn bị từ chối do **exp**, không “sống lại” |
| AS thay khóa ký / JWK cache refresh | Token ký bằng khóa mới/khóa cũ có hành vi đúng giai đoạn chuyển đổi |

**Thiết kế test không được chỉ kiểm tra Redis có key**: phải gửi request qua filter chain, khẳng định trạng thái HTTP và không thực thi side effect ở controller/service.

## 7. Đánh giá token thật ở production

Khi resource server dùng JWT từ AS thật, hãy quan sát theo lớp:

1. **Không có token:** kiểm tra 401 và header **WWW-Authenticate: Bearer** khi phù hợp.
2. **JWT không parse được hoặc signature sai:** xác định decoder trả lỗi xác thực, không rơi vào controller. Không công bố chi tiết khóa hoặc JWT nhạy cảm ra log.
3. **exp / nbf / iat:** kiểm thử xa ngưỡng clock skew, đồng bộ giờ bằng NTP và xác minh chính sách max TTL nhất quán với AS.
4. **iss và aud:** thử token hợp lệ nhưng được phát cho **API khác**; phải từ chối.
5. **Scope:** thử token hợp lệ thiếu quyền để chắc chắn trả 403, không coi tất cả JWT đã ký là toàn quyền.
6. **Đăng xuất/thu hồi:** đo từ thời điểm ghi lệnh đến request cuối cùng bị từ chối, không chỉ kiểm tra UI đã xóa token.
7. **JWKS/AS outage:** xác nhận cache/timeout/key rotation và khả năng API phản ứng với token có **kid** mới; không tự động bỏ signature validation khi JWK endpoint lỗi.
8. **Replay/rò rỉ:** bảo vệ HTTPS, tránh đưa bearer token vào URL query, stack trace hoặc access log. Client nên giữ token ở vị trí phù hợp mô hình bảo mật; nếu dùng cookie, đánh giá CSRF riêng.
9. **Session/refresh:** kiểm tra refresh token rotation, reuse detection, phiên bị khóa và giới hạn session tuyệt đối tại AS — đây không phải trách nhiệm do Resource Server JWT decoder tự thực hiện.
10. **Nhiều resource server:** thống nhất issuer/audience policy, key trust, skew và thông tin revocation trên tất cả API liên quan.

### Chẩn đoán nhanh lỗi hay gặp

| Hiện tượng | Nguyên nhân cần phân biệt | Cách xử lý |
| --- | --- | --- |
| 401 dù token nhìn được payload | Base64 decode không chứng minh chữ ký; exp/iss/aud/nbf có thể sai | Kiểm tra thông báo decoder, trusted JWK, issuer/audience và thời gian |
| 401 ngay sau khi đổi khóa AS | JWK cache cũ, token **kid** mới chưa được nhận, URI JWKS sai | Kiểm tra khả năng tải JWKS, thuật toán, cache refresh và kế hoạch rotation |
| Token logout rồi vẫn dùng được | Resource server không tra trạng thái thu hồi | TTL ngắn; thêm denylist/introspection nếu yêu cầu chặn trước exp |
| Token bị thu hồi ở một node nhưng node khác vẫn chấp nhận | Denylist cục bộ hoặc cache chưa đồng bộ | Dùng shared state và xác định SLA nhất quán |
| Token không hết hạn dù “giới hạn 15 phút” | AS vẫn phát exp dài hoặc chỉ kiểm tra exp mà không kiểm tra **exp - iat** | Giới hạn TTL tại AS và/hoặc thêm validator như ví dụ |
| 403 nhưng chữ ký JWT đúng | Token xác thực được nhưng thiếu **scope/role** | Kiểm tra authority mapping và chính sách endpoint |
| Token chỉ chứa **aud** khác vẫn vào API | Chưa cấu hình validator audience | Thêm validator aud cố định theo resource API |
| Token bị từ chối sát thời điểm exp | Clock skew giữa các service hoặc chính sách temporal validator | Đồng bộ giờ, dùng skew hữu hạn, kiểm thử sát ngưỡng có chủ đích |
| Test **jwt()** luôn qua nhưng token ngoài đời lỗi | Test đã bỏ qua decoder và chữ ký | Dùng JWT tự ký với key test và decoder thật như mục 6 |
| Đổi mật khẩu mà token vẫn dùng được | JWT là snapshot claims, API không kiểm tra trạng thái tài khoản | Bổ sung cơ chế revocation/session version hoặc hạ TTL theo yêu cầu |

## 8. Checklist quyết định trước khi triển khai

- **Thời gian thu hồi tối đa chấp nhận được là bao nhiêu?** Nếu 5 phút là đủ, access token ngắn hạn có thể đáp ứng. Nếu yêu cầu vài giây, JWT stateless đơn thuần thường không đủ.
- **Ai có quyền thu hồi?** Logout người dùng, admin khóa tài khoản, phát hiện token bị đánh cắp, hoặc đổi quyền cần có chính sách riêng, được xác thực và audit.
- **Dữ liệu revocation có được chia sẻ giữa các API instance?** Có TTL, phục hồi sau lỗi và fail behavior được định nghĩa?
- **AS phát access token đúng hợp đồng chưa?** issuer, audience, iat, exp, jti, scope, thuật toán/kid, giới hạn cấp và refresh rotation.
- **Resource server từ chối token không hợp lệ ở tầng authentication chưa?** Không lẫn lỗi 401 với authorization 403; không chỉ decode Base64.
- **Các bài test có kiểm chứng chữ ký thật không?** Với chữ ký, exp, iss, aud, TTL hãy test qua JwtDecoder. Với scope/endpoint có thể thêm test .with(jwt()) cho các nhánh authorization.
- **Đã chuẩn bị quy trình khẩn cấp chưa?** Lộ khóa ký, lộ refresh token, JWKS outage, denylist outage và cache gây trì hoãn thu hồi.
- **Báo cáo vận hành đo được cửa sổ rủi ro thực tế chưa?** Thời gian từ logout/revocation đến request cuối cùng còn được chấp nhận quan trọng hơn trạng thái “đã xóa token” trên UI.

**Kết luận:** Với JWT access token, **exp ngắn là cách giới hạn mức phơi nhiễm, không phải cơ chế thu hồi tức thì**. Resource Server phải kiểm tra đầy đủ chữ ký, issuer, audience, thời gian sống và quyền. Nếu cần hủy token trước exp, phải bổ sung denylist/introspection/trạng thái tin cậy và kiểm thử request thực tế sau thu hồi, không chỉ kiểm thử việc logout thành công.
