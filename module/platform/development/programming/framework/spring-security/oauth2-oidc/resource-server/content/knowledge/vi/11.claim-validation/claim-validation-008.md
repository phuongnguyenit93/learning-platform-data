# DelegatingOAuth2TokenValidator và hợp thành các kiểm tra

Khi xây dựng **Spring Security OAuth 2.0 Resource Server**, một JWT access token không chỉ cần có chữ ký hợp lệ. API còn phải xác nhận token được phát hành từ đúng **issuer**, dành cho đúng **audience**, đang trong thời gian có hiệu lực, và đáp ứng các điều kiện claim cụ thể của hợp đồng truy cập. Trong Spring Security, các điều kiện dạng này có thể được biểu diễn bằng những implementation của `OAuth2TokenValidator<Jwt>` và kết hợp với nhau bằng **`DelegatingOAuth2TokenValidator`**.

Mục tiêu của bài học là hiểu cách **hợp thành nhiều kiểm tra độc lập thành một chuỗi xác minh có thể duy trì**, giữ lại validator mặc định khi bổ sung validator riêng và xác định rõ đâu là **kiểm tra tính hợp lệ của token** so với **kiểm tra quyền sử dụng tài nguyên**. Nội dung đặt trong chương *Kiểm tra claims*, module *Spring Security OAuth 2.0 OIDC Resource Server*, chủ yếu minh họa với **JWT Resource Server trên Servlet/Spring MVC** và có phần đối chiếu với WebFlux.

> Các địa chỉ issuer, audience, token và client trong ví dụ chỉ dùng cho học tập. Hệ thống thật phải thống nhất token profile và chính sách xác thực với Authorization Server. Không dùng ID token thay cho OAuth access token để gọi Resource Server.

## 1. Vì sao cần hợp thành các kiểm tra?

Giả sử hệ thống có hai API cùng tin cậy một Authorization Server:

~~~text
Issuer:      https://login.example.test/realms/company

Orders API:
  audience:  orders-api
  scopes:    orders.read, orders.create

Billing API:
  audience:  billing-api
  scopes:    invoices.read, invoices.pay
~~~

Một token có thể được ký đúng bằng khóa của issuer, nhưng `aud` lại là `billing-api`. Nếu Orders API chỉ xác minh chữ ký và issuer mà bỏ qua audience, nó có nguy cơ nhận một token không được cấp cho mình. Ngược lại, một token có audience đúng nhưng hết hạn cũng không được chấp nhận.

Thay vì một hàm xác minh khổng lồ, hãy chia điều kiện:

| Điều kiện | Validator / lớp phụ trách | Câu hỏi |
|---|---|---|
| Chữ ký, key và JWS algorithm | `JwtDecoder` / JOSE library | Token có được ký bằng khóa và thuật toán tin cậy? |
| Issuer | Validator issuer, ví dụ từ `JwtValidators.createDefaultWithIssuer(...)` | Có đúng Authorization Server được tin cậy? |
| Thời gian `exp`, `nbf` | Validator thời gian | Token đã hết hạn hoặc chưa được phép dùng? |
| Audience `aud` | Validator audience tùy chỉnh hoặc hỗ trợ framework | Token có dành cho API hiện tại? |
| Claim tenant/client/profile bắt buộc | Validator riêng theo hợp đồng | Token có đủ thuộc tính để được chấp nhận ở hệ thống này? |
| Scope và quyền truy cập bản ghi | `JwtAuthenticationConverter` và authorization | Principal có quyền thực hiện request cụ thể? |

**`DelegatingOAuth2TokenValidator` tập trung vào nhóm validator claim/token**, không thay thế công đoạn xác minh chữ ký số và cũng không tự cấp `GrantedAuthority`. Sử dụng đúng ranh giới này giúp thay đổi chính sách mà không làm yếu pipeline xác thực.

## 2. Vị trí của validator trong luồng Servlet Resource Server

Client gửi token qua header:

~~~http
GET /api/orders/42 HTTP/1.1
Host: orders-api.example.test
Authorization: Bearer <ACCESS_TOKEN>
Accept: application/json
~~~

Luồng xử lý khái quát:

~~~mermaid
flowchart TD
    A["HTTP Authorization: Bearer JWT"] --> B["BearerTokenAuthenticationFilter"]
    B --> C["BearerTokenAuthenticationToken"]
    C --> D["JwtAuthenticationProvider"]
    D --> E["JwtDecoder"]
    E --> F["Xác minh JWS: algorithm + trusted key"]
    F --> G["DelegatingOAuth2TokenValidator<Jwt>"]
    G --> H["Default/time + issuer"]
    G --> I["Audience"]
    G --> J["Custom claim/profile"]
    H --> K{"Tất cả đều hợp lệ?"}
    I --> K
    J --> K
    K -->|Không| L["JwtValidationException / Authentication failure"]
    K -->|Có| M["Jwt đã xác minh"]
    M --> N["JwtAuthenticationConverter"]
    N --> O["JwtAuthenticationToken + GrantedAuthority"]
    O --> P["Authorization rules"]
    P --> Q["Controller / service nếu đủ quyền"]
~~~

Thứ tự tư duy quan trọng:

1. `BearerTokenAuthenticationFilter` trích JWT từ HTTP request.
2. `JwtAuthenticationProvider` sử dụng `JwtDecoder` để xác minh token.
3. Decoder kiểm tra mật mã/JWS rồi chạy những validator claim đã cấu hình.
4. Chỉ sau khi token hợp lệ, `JwtAuthenticationConverter` mới chuyển `scope`, `scp` hoặc claim phù hợp thành authorities.
5. `SecurityFilterChain` và các policy nghiệp vụ quyết định request có được phép truy cập API và bản ghi cụ thể hay không.

Nếu validation thất bại, không được tạo một authentication “tạm” rồi bỏ qua bước lỗi. Token đã decode được JSON chưa đủ để xem claims là đáng tin.

## 3. Giao diện `OAuth2TokenValidator<T>`

Spring Security mô tả một phép kiểm tra token qua interface:

~~~java
public interface OAuth2TokenValidator<T extends OAuth2Token> {
    OAuth2TokenValidatorResult validate(T token);
}
~~~

Với JWT, thường dùng:

~~~java
OAuth2TokenValidator<Jwt> audienceValidator = jwt -> {
    // Đọc các claims đã được decoder giải mã.
    // Trả về success hoặc failure.
};
~~~

Các kiểu dữ liệu liên quan:

| API | Ý nghĩa |
|---|---|
| `OAuth2TokenValidator<Jwt>` | Một quy tắc kiểm tra trên `Jwt` |
| `OAuth2TokenValidatorResult.success()` | Token đạt quy tắc |
| `OAuth2TokenValidatorResult.failure(...)` | Token không đạt, kèm một hoặc nhiều `OAuth2Error` |
| `OAuth2Error` | Mô tả loại lỗi, mô tả ngắn và URI mô tả nếu có |
| `DelegatingOAuth2TokenValidator<Jwt>` | Kết hợp nhiều validator thành một validator dùng chung |
| `JwtValidators.createDefaultWithIssuer(issuer)` | Tạo tập validator mặc định phù hợp và có issuer |
| `NimbusJwtDecoder.setJwtValidator(...)` | Chỉ định validator mà decoder sử dụng sau bước JWS |

### 3.1. Một validator audience nhỏ nhất

~~~java
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;

OAuth2TokenValidator<Jwt> audienceValidator = jwt -> {
    if (jwt.getAudience().contains("orders-api")) {
        return OAuth2TokenValidatorResult.success();
    }

    return OAuth2TokenValidatorResult.failure(
        new OAuth2Error(
            "invalid_token",
            "JWT audience does not include orders-api",
            null
        )
    );
};
~~~

Nếu `aud` không có giá trị `orders-api`, validator trả failure. Nó **không xác minh chữ ký**, **không kiểm tra scope**, và **không tự động gắn vào decoder** chỉ vì được khai báo trong một biến Java. Cần tích hợp vào `JwtDecoder` như các phần sau.

Theo JWT (RFC 7519), `aud` có thể được biểu diễn dưới dạng một chuỗi hoặc mảng chuỗi. `Jwt.getAudience()` giúp mã ứng dụng kiểm tra danh sách audience mà API biết. Nếu token không có audience, quy tắc ví dụ từ chối token theo hợp đồng Orders API.

### 3.2. `OAuth2Error` không phải response HTTP trực tiếp

Khi validation thất bại, `OAuth2Error` trở thành một phần thông tin lỗi xác thực do decoder/provider truyền lên. Resource Server thường xử lý Bearer token invalid bằng HTTP **401 Unauthorized**. Một `OAuth2Error` tùy chỉnh **không** có nghĩa controller sẽ tự gửi chuỗi mô tả lỗi đúng nguyên văn cho người dùng.

Không đưa token gốc, client secret, nội dung khóa hay dữ liệu nhạy cảm vào `description`. Các chi tiết vận hành sâu nên nằm trong hệ thống quan sát được bảo vệ, không phải phản hồi công khai.

## 4. `DelegatingOAuth2TokenValidator` hợp thành như thế nào?

`DelegatingOAuth2TokenValidator<T>` triển khai chính giao diện `OAuth2TokenValidator<T>`. Nó nhận một tập các validator và áp chúng cho token. Token được coi là hợp lệ với validator hợp thành **chỉ khi tất cả validator thành phần đều thành công**.

~~~java
OAuth2TokenValidator<Jwt> validators =
    new DelegatingOAuth2TokenValidator<>(
        validatorA,
        validatorB,
        validatorC
    );
~~~

Diễn giải logic:

~~~text
Token valid
  = validatorA valid
    AND validatorB valid
    AND validatorC valid
~~~

Trong triển khai thông dụng của Spring Security, lỗi từ những validator thành phần được thu thập thành một kết quả thất bại, thay vì coi việc một validator thành công là đủ. **Không viết chính sách theo giả định “validator đầu tiên đúng là dừng” hoặc “đạt một trong các validator là đủ”**.

~~~mermaid
flowchart LR
    T["JWT đã xác minh JWS"] --> V1["Issuer + thời gian"]
    T --> V2["Audience"]
    T --> V3["Required claims"]
    V1 --> R["DelegatingOAuth2TokenValidator"]
    V2 --> R
    V3 --> R
    R -->|"Mọi validator thành công"| S["success"]
    R -->|"Có ít nhất một lỗi"| F["failure (OAuth2Error)"]
~~~

### 4.1. Không phải lựa chọn logic OR

Một ứng dụng có thể cần chấp nhận **audience A hoặc B**. Nếu định nghĩa:

~~~java
new DelegatingOAuth2TokenValidator<>(
    requireAudienceA,
    requireAudienceB
);
~~~

thì đây là yêu cầu **có cả audience A và B**, không phải “A hoặc B”. Nếu policy thật sự cho phép một trong hai, phải biểu diễn OR **bên trong một validator**:

~~~java
Set<String> acceptedAudiences = Set.of("orders-api", "orders-api-v2");

OAuth2TokenValidator<Jwt> acceptedAudience = jwt -> {
    boolean matched = jwt.getAudience().stream()
        .anyMatch(acceptedAudiences::contains);
    return matched
        ? OAuth2TokenValidatorResult.success()
        : OAuth2TokenValidatorResult.failure(
            new OAuth2Error("invalid_token", "Invalid audience", null));
};
~~~

Ví dụ cần import `java.util.Set`. Hai audience này là hai resource ID được **chấp thuận trước**, không phải chuỗi do request tự quyết định. Nếu chính sách cấm token multi-audience, phải thêm điều kiện phù hợp (ví dụ chỉ một audience trong danh sách) thay vì mặc định chấp nhận mọi tập.

### 4.2. Cấu trúc validator có thể lồng nhau

`JwtValidators.createDefaultWithIssuer(...)` trả về một `OAuth2TokenValidator<Jwt>`, có thể bản thân nó đã kết hợp các validator khác. Ta vẫn đưa nó vào `DelegatingOAuth2TokenValidator` bên ngoài:

~~~java
OAuth2TokenValidator<Jwt> all = new DelegatingOAuth2TokenValidator<>(
    JwtValidators.createDefaultWithIssuer(trustedIssuer),
    audienceValidator,
    mandatoryClaimsValidator
);
~~~

Nhờ vậy các điều kiện mặc định vẫn được giữ, trong khi yêu cầu riêng của Orders API được thêm như những thành phần độc lập.

## 5. Sai lầm trọng yếu: `setJwtValidator` thay thế, không nối thêm

`NimbusJwtDecoder.setJwtValidator(...)` cho phép đặt một validator cho decoder. Khi gọi phương thức này với validator tự viết, ứng dụng không nên kỳ vọng decoder sẽ tự động giữ lại mọi validator được cấu hình trước đó.

Đoạn sau có thể vô tình làm mất những kiểm tra claim thiết yếu:

~~~java
// PHẢN VÍ DỤ: chỉ kiểm tra audience, dễ làm mất issuer/time validators.
NimbusJwtDecoder decoder = NimbusJwtDecoder.withJwkSetUri(jwksUri).build();
decoder.setJwtValidator(audienceValidator);
~~~

**Chữ ký có thể vẫn được decoder kiểm tra**, nhưng phần validator claim có nguy cơ chỉ còn audience. Một JWT sai `iss`, đã hết hạn hoặc chưa có hiệu lực có thể không bị từ chối như mong đợi nếu các validator mặc định bị thay thế.

Cách cấu hình có chủ đích:

~~~java
OAuth2TokenValidator<Jwt> combined =
    new DelegatingOAuth2TokenValidator<>(
        JwtValidators.createDefaultWithIssuer(issuer),
        audienceValidator
    );

decoder.setJwtValidator(combined);
~~~

**Quy tắc:** khi thêm validator mới, phải chủ động ghép lại tất cả điều kiện bắt buộc. `JwtValidators.createDefaultWithIssuer(issuer)` là điểm khởi đầu thích hợp để giữ những kiểm tra mặc định của phiên bản Spring Security đang dùng và ràng buộc issuer. Nếu ứng dụng tuân thủ token profile đặc thù (ví dụ JWT access token RFC 9068), phải xem xét thêm các validator/profile rule mà hợp đồng yêu cầu.

Không phụ thuộc vào việc “trước đây YAML đã có `issuer-uri`” để bảo đảm validator issuer tự xuất hiện trên **bean `JwtDecoder` mà ứng dụng tự xây dựng**.

## 6. Ví dụ đầy đủ: issuer + thời gian + audience trong `JwtDecoder`

Giả sử hợp đồng Orders API:

~~~text
Trusted issuer:  https://login.example.test/realms/company
Trusted JWKS:    https://login.example.test/realms/company/protocol/openid-connect/certs
Expected aud:    orders-api
Allowed JWS alg: RS256
GET scope:       orders.read
~~~

Đầu tiên thêm dependencies cho Servlet:

~~~gradle
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
~~~

Đặt các giá trị trong `application.yml`:

~~~yaml
app:
  security:
    jwt:
      issuer: https://login.example.test/realms/company
      jwk-set-uri: https://login.example.test/realms/company/protocol/openid-connect/certs
      audience: orders-api
~~~

`app.security.jwt.*` là nhóm property **ứng dụng tự định nghĩa**, không phải nhóm auto-configuration được Spring Boot tự hiểu. Chúng sẽ được inject vào bean dưới đây.

### 6.1. Bean `JwtDecoder` giữ default + issuer và bổ sung audience

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

@Configuration
public class OrdersJwtDecoderConfig {

    @Bean
    JwtDecoder jwtDecoder(
            @Value("${app.security.jwt.issuer}") String issuer,
            @Value("${app.security.jwt.jwk-set-uri}") String jwksUri,
            @Value("${app.security.jwt.audience}") String audience) {

        NimbusJwtDecoder decoder = NimbusJwtDecoder
            .withJwkSetUri(jwksUri)
            .jwsAlgorithm(SignatureAlgorithm.RS256)
            .build();

        OAuth2TokenValidator<Jwt> defaultsAndIssuer =
            JwtValidators.createDefaultWithIssuer(issuer);

        OAuth2TokenValidator<Jwt> expectedAudience = jwt -> {
            if (jwt.getAudience().contains(audience)) {
                return OAuth2TokenValidatorResult.success();
            }
            return OAuth2TokenValidatorResult.failure(
                new OAuth2Error(
                    "invalid_token",
                    "Access token is not intended for Orders API",
                    null
                )
            );
        };

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                defaultsAndIssuer,
                expectedAudience
            )
        );

        return decoder;
    }
}
~~~

Đọc từng phần:

1. `withJwkSetUri(jwksUri)` xác định nguồn **public keys** đã tin cậy để xác minh JWS. JWK Set URI phải do đội vận hành issuer công bố, không lấy từ JWT header tùy ý.
2. `jwsAlgorithm(RS256)` giới hạn thuật toán theo ví dụ. Hợp đồng thực tế có thể sử dụng thuật toán khác; chỉ mở thuật toán được phê duyệt.
3. `JwtValidators.createDefaultWithIssuer(issuer)` giữ các kiểm tra mặc định phù hợp (đặc biệt issuer và thời gian).
4. `expectedAudience` yêu cầu claim `aud` chứa định danh API hiện tại.
5. `DelegatingOAuth2TokenValidator` kết hợp các điều kiện theo logic AND.
6. `setJwtValidator(...)` chỉ định **bộ validator hoàn chỉnh**, không phải riêng audience.

Nếu decoder không thể xác minh chữ ký hoặc một validator thất bại, `JwtAuthenticationProvider` không tạo `JwtAuthenticationToken` đã xác thực cho request.

### 6.2. Tích hợp Servlet `SecurityFilterChain`

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration
public class OrdersApiSecurityConfig {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders")
                    .hasAuthority("SCOPE_orders.create")
                .anyRequest().authenticated()
            )
            .oauth2ResourceServer(oauth2 -> oauth2.jwt(withDefaults()))
            .build();
    }
}
~~~

Khi có bean `JwtDecoder` do ứng dụng tạo, Spring Boot thông thường không tạo bean decoder mặc định nữa. HTTP security phía trên sử dụng bean thích hợp từ context. Nếu gắn một decoder khác trực tiếp qua `jwt.decoder(...)` trên chain, phải bảo đảm **instance được gắn trực tiếp** có cùng bộ validator; đừng giả định tất cả chain tự dùng bean trên.

Spring Security mặc định thường ánh xạ `scope="orders.read"` thành authority `SCOPE_orders.read`. Việc JWT vượt qua issuer/audience/time validation **không có nghĩa tự động đủ quyền đọc hay tạo đơn**. Authority và các policy chủ sở hữu dữ liệu vẫn cần được kiểm tra ở các tầng tiếp theo.

### 6.3. Dùng issuer discovery thay JWKS URI cố định

Nếu muốn decoder lấy JWK Set từ metadata của trusted issuer, builder có thể dùng:

~~~java
NimbusJwtDecoder decoder = NimbusJwtDecoder
    .withIssuerLocation(issuer)
    .jwsAlgorithm(SignatureAlgorithm.RS256)
    .build();

decoder.setJwtValidator(
    new DelegatingOAuth2TokenValidator<>(
        JwtValidators.createDefaultWithIssuer(issuer),
        expectedAudience
    )
);
~~~

Đây là **phương án thay thế khởi tạo decoder** của mục 6.1, không phải bean bổ sung. Discovery dùng issuer đã được cấu hình tin cậy; không tự động tải metadata từ claim `iss` tùy ý trong JWT chưa xác minh.

## 7. Tạo validator tùy chỉnh cho các claim khác

Ngoài issuer, thời gian và audience, từng API có thể cần bảo đảm các điều kiện riêng. Ví dụ Orders API cho nhiều tenant có thể yêu cầu token luôn có tenant ID, được cấp cho một client nằm trong allowlist, hoặc có thời điểm phát hành không vượt quá giới hạn tuổi đời cho phép. Những điều kiện này phải xuất phát từ **hợp đồng với Authorization Server**, không tự đoán tên claim từ một token mẫu.

### 7.1. Bắt buộc một claim tồn tại

Ví dụ profile của Orders API yêu cầu token luôn có `exp`. Cần phân biệt hai câu hỏi:

- Nếu `exp` **có mặt**, timestamp validator kiểm tra token đã hết hạn chưa.
- Nếu `exp` **vắng mặt**, ứng dụng có cần xem token không hợp lệ ngay không?

Nếu yêu cầu `exp` bắt buộc, thêm validator:

~~~java
OAuth2TokenValidator<Jwt> expiryRequired = jwt -> {
    if (jwt.getExpiresAt() != null) {
        return OAuth2TokenValidatorResult.success();
    }
    return OAuth2TokenValidatorResult.failure(
        new OAuth2Error(
            "invalid_token",
            "Required exp claim is missing",
            null
        )
    );
};
~~~

Sau đó kết hợp:

~~~java
OAuth2TokenValidator<Jwt> combined =
    new DelegatingOAuth2TokenValidator<>(
        JwtValidators.createDefaultWithIssuer(issuer),
        expectedAudience,
        expiryRequired
    );

decoder.setJwtValidator(combined);
~~~

Nếu một token có `exp` hợp lệ nhưng `iss` sai, nó vẫn bị từ chối. Nếu `iss` đúng nhưng thiếu `exp`, nó cũng bị từ chối theo hợp đồng trên. **Không dùng validator bắt buộc claim để thay thế validator kiểm tra ý nghĩa claim**.

### 7.2. Kiểm tra client nằm trong allowlist

Một Resource Server có thể chỉ chấp nhận access token cấp cho client đã được phê duyệt:

~~~java
import java.util.Set;

Set<String> allowedClients = Set.of(
    "orders-web",
    "orders-mobile"
);

OAuth2TokenValidator<Jwt> allowedClient = jwt -> {
    String clientId = jwt.getClaimAsString("client_id");
    if (clientId != null && allowedClients.contains(clientId)) {
        return OAuth2TokenValidatorResult.success();
    }
    return OAuth2TokenValidatorResult.failure(
        new OAuth2Error(
            "invalid_token",
            "Client is not allowed for Orders API",
            null
        )
    );
};
~~~

`client_id` không phải claim bắt buộc trong mọi JWT profile. Nếu issuer dùng claim khác hoặc không biểu diễn client theo cách này, hợp đồng phải điều chỉnh cho phù hợp. Một claim `azp` xuất hiện trong OIDC ID token cũng **không tự động có ý nghĩa thay `client_id` trong mọi access token**.

### 7.3. Bắt buộc tenant ID hợp lệ

Giả sử mọi token của Orders API phải có claim `tenant_id` thuộc một danh sách tenant được kết nối:

~~~java
Set<String> knownTenants = Set.of("tenant-a", "tenant-b");

OAuth2TokenValidator<Jwt> knownTenant = jwt -> {
    String tenant = jwt.getClaimAsString("tenant_id");
    if (tenant != null && knownTenants.contains(tenant)) {
        return OAuth2TokenValidatorResult.success();
    }
    return OAuth2TokenValidatorResult.failure(
        new OAuth2Error(
            "invalid_token",
            "Tenant claim is invalid",
            null
        )
    );
};
~~~

Đây là kiểm tra **token có thuộc tenant được chấp thuận về mặt hợp đồng không**. Nó **không** xác nhận rằng người dùng có quyền đọc đơn hàng cụ thể thuộc `tenant-a`. Trong controller/service, cần đối chiếu tenant đã được xác thực với tenant của tài nguyên và quyền trên dữ liệu.

Nếu tập tenant thay đổi thường xuyên, không nhất thiết hard-code danh sách vào decoder; có thể cần một chính sách registry/tenant trust được quản lý tập trung. Cần làm rõ hiệu ứng của cache cấu hình, việc xóa tenant và tình trạng dữ liệu không còn đồng bộ.

### 7.4. Giới hạn tuổi đời token từ `iat`

Với endpoint nhạy cảm, hợp đồng có thể yêu cầu JWT không được phát hành quá lâu, kể cả khi `exp` còn xa. Điều kiện đơn giản:

~~~text
issued-at (iat) phải có
AND iat không ở tương lai ngoài clock skew cho phép
AND now - iat <= maximum token age
~~~

Một validator minh họa:

~~~java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;

Clock clock = Clock.systemUTC();
Duration maxAge = Duration.ofMinutes(15);
Duration skew = Duration.ofSeconds(60);

OAuth2TokenValidator<Jwt> tokenAge = jwt -> {
    Instant issuedAt = jwt.getIssuedAt();
    Instant now = clock.instant();

    boolean valid = issuedAt != null
        && !issuedAt.isAfter(now.plus(skew))
        && !issuedAt.isBefore(now.minus(maxAge).minus(skew));

    return valid
        ? OAuth2TokenValidatorResult.success()
        : OAuth2TokenValidatorResult.failure(
            new OAuth2Error("invalid_token", "Token age is not allowed", null));
};
~~~

Validator trên **không thay thế kiểm tra `exp`/`nbf`**; nó thêm giới hạn riêng dựa trên `iat`. Các giá trị 15 phút và 60 giây chỉ là minh họa, không phải mặc định framework. Nếu test cần thời gian ổn định, inject `Clock` vào bean cấu hình thay vì tạo `Clock.systemUTC()` cứng bên trong chính sách.

### 7.5. Các validator độc lập ghép lại

Khi API có nhiều điều kiện:

~~~java
OAuth2TokenValidator<Jwt> allRules =
    new DelegatingOAuth2TokenValidator<>(
        JwtValidators.createDefaultWithIssuer(issuer),
        expectedAudience,
        expiryRequired,
        allowedClient,
        knownTenant,
        tokenAge
    );

decoder.setJwtValidator(allRules);
~~~

Đây là **đoạn lắp ghép**, giả định các biến validator đã được khai báo trong cùng cấu hình và các yêu cầu đó thực sự thuộc hợp đồng Orders API. Hệ thống không nên thêm mọi validator chỉ vì có thể viết code: mỗi claim bổ sung có thể làm API từ chối token của những client hợp lệ nếu Authorization Server chưa cam kết phát hành claim đó.

## 8. `JwtClaimValidator` và các validator được Spring Security cung cấp

Không phải validator nào cũng cần lambda từ đầu. Spring Security có những implementation hữu ích:

| Loại | Mục đích |
|---|---|
| `JwtIssuerValidator` | Kiểm tra issuer |
| `JwtTimestampValidator` | Kiểm tra tính hợp lệ theo thời gian |
| `JwtClaimValidator<T>` | Kiểm tra một claim bằng predicate do ứng dụng khai báo |
| `JwtValidators.createDefault()` | Cung cấp bộ validation mặc định phù hợp phiên bản |
| `JwtValidators.createDefaultWithIssuer(issuer)` | Bộ mặc định với yêu cầu issuer |
| `DelegatingOAuth2TokenValidator<Jwt>` | Ghép nhiều validator theo điều kiện cùng đạt |

### 8.1. Dùng `JwtClaimValidator` cho audience

Ví dụ này diễn đạt quy tắc audience dưới dạng predicate:

~~~java
import java.util.List;
import org.springframework.security.oauth2.jwt.JwtClaimNames;
import org.springframework.security.oauth2.jwt.JwtClaimValidator;

OAuth2TokenValidator<Jwt> audienceRule =
    new JwtClaimValidator<List<String>>(
        JwtClaimNames.AUD,
        aud -> aud != null && aud.contains("orders-api")
    );
~~~

`JwtClaimValidator` nhận **claim name** và điều kiện hợp lệ. Với claim audience, cần quan tâm kiểu dữ liệu sau khi JWT claim conversion của Spring Security chạy: các cấu hình custom có thể cho claim khác kiểu hoặc không tồn tại. Nếu nhiều profile issuer không đồng nhất, viết validator trực tiếp trên `Jwt.getAudience()` thường giúp thể hiện ý định rõ hơn.

### 8.2. Cần điều chỉnh clock skew thì sao?

`JwtTimestampValidator` có cấu hình clock skew, ví dụ:

~~~java
import java.time.Duration;
import org.springframework.security.oauth2.jwt.JwtTimestampValidator;

JwtTimestampValidator timestamps =
    new JwtTimestampValidator(Duration.ofSeconds(45));
~~~

**Không tùy tiện đặt thêm timestamp validator mới cạnh một timestamp validator mặc định rồi cho rằng skew mặc định đã bị thay thế**. Nếu cả hai chạy, JWT phải đồng thời thỏa cả hai điều kiện; một bộ với skew nhỏ hơn có thể chi phối kết quả.

Khi muốn thay đổi cơ chế thời gian mặc định, phải xác định chính xác bộ validator của phiên bản Spring Security đang dùng, xây dựng tập validator cuối cùng bảo toàn issuer, audience, token profile và các điều kiện khác. Chỉ thêm một validator timestamp vào `DelegatingOAuth2TokenValidator` không tự sửa cấu hình của timestamp validator khác đã tồn tại.

### 8.3. Dùng `JwtValidators.createDefaultWithIssuer` để tránh ghép thiếu

Thay vì:

~~~java
// Có thể thiếu những rule mặc định khác tùy phiên bản/profile.
new DelegatingOAuth2TokenValidator<>(
    new JwtIssuerValidator(issuer),
    myAudienceValidator
);
~~~

thường nên khởi đầu bằng:

~~~java
new DelegatingOAuth2TokenValidator<>(
    JwtValidators.createDefaultWithIssuer(issuer),
    myAudienceValidator
);
~~~

Cách thứ hai nhấn mạnh ý định: **giữ default validation mà framework cung cấp** và thêm audience. Những rule đặc thù như yêu cầu `exp` phải tồn tại, `typ` của access token profile, `client_id` hay tenant vẫn cần được thống nhất riêng và có thể phải thêm validator tương ứng.

## 9. Ranh giới giữa JWT claims validation và kiểm tra quyền

Một JWT sau khi xác minh có thể chứa:

~~~json
{
  "iss": "https://login.example.test/realms/company",
  "sub": "user-123",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "tenant_id": "tenant-a"
}
~~~

Với Orders API, ta có hai tầng quyết định:

**Tầng xác thực/validation**:

~~~text
Đúng chữ ký và key tin cậy?
Đúng issuer?
Chưa hết hạn? Đã tới nbf?
Token được cấp cho orders-api?
Tenant/client/profile bắt buộc có hợp lệ?
          |
          v
    Jwt được chấp nhận
~~~

**Tầng phân quyền/authorization**:

~~~text
GET /api/orders/42 yêu cầu SCOPE_orders.read?
Token có scope đó không?
Order 42 thuộc subject/tenant nào?
User/service có được xem chính bản ghi này không?
          |
          v
    Cho phép hoặc từ chối request
~~~

### 9.1. Đừng dùng token validator để kiểm tra URL tùy ý

Một validator JWT thường không có trực tiếp ngữ cảnh HTTP path, method hoặc dữ liệu bản ghi. Nếu muốn xác định `GET /api/orders/**` cần scope nào, dùng `authorizeHttpRequests` hoặc method security. Nếu muốn kiểm tra owner/tenant của một đơn hàng, dùng authorization service/domain.

Viết JWT validator đọc dữ liệu request qua biến static hoặc global để gắn quyền có thể làm chính sách khó kiểm soát và gây lỗi giữa các request đồng thời.

### 9.2. Đừng dùng converter để bỏ qua validator

`JwtAuthenticationConverter` có thể ánh xạ `scope` thành `SCOPE_orders.read`, nhưng nó chạy trên JWT đã được decoder chấp nhận. Một claim `scope` phù hợp **không bù** cho audience sai hoặc issuer sai. Converter không được “chữa” token bằng cách sửa claim `iss`/`aud` hoặc tạo authorities dù token chưa qua bước xác thực.

### 9.3. Ví dụ phân biệt 401 và 403

| Trường hợp | Giai đoạn thất bại | HTTP thường gặp |
|---|---|---|
| JWT sai chữ ký | Decoder/JWS | 401 |
| JWT hết hạn | Token validator | 401 |
| JWT `aud=billing-api` gọi Orders API | Audience validator | 401 |
| JWT `iss` không thuộc issuer tin cậy | Issuer validator | 401 |
| JWT hợp lệ nhưng thiếu `orders.read` | HTTP/method authorization | 403 |
| JWT hợp lệ, đủ scope nhưng không sở hữu order | Domain authorization | 403 hoặc 404 tùy policy |

Spring Security có thể trả Bearer challenge theo RFC 6750:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
~~~

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope", scope="orders.read"
~~~

Nội dung challenge cụ thể phụ thuộc exception handler, security configuration và request. Một lỗi mất kết nối tới JWKS/issuer có thể dẫn đến một status khác với “JWT invalid” thực sự; **không được cho request chưa xác minh đi tiếp dù upstream lỗi**.

## 10. Khi nào cần hợp thành điều kiện AND, OR, hay điều kiện phụ thuộc?

`DelegatingOAuth2TokenValidator` là lựa chọn tự nhiên khi có các điều kiện độc lập phải **cùng đúng**:

~~~text
issuer đúng
AND thời gian đúng
AND audience đúng
AND token profile đúng
~~~

Nhưng có những chính sách đặc biệt:

**OR giữa các giá trị của cùng một claim**:

~~~text
aud chứa orders-api
OR aud chứa orders-api-v2
~~~

Nên được diễn đạt trong **một validator audience** dùng tập allowlist.

**Phụ thuộc lẫn nhau giữa hai claim**:

~~~text
Nếu grant_type == client_credentials
    → client_id phải thuộc nhóm service đã duyệt.
Nếu token đại diện end-user
    → sub phải có theo profile.
~~~

Có thể diễn đạt bằng một validator đọc nhiều claim và áp quy tắc điều kiện. Không nên gắn cả `requireServiceClient` và `requireEndUser` qua `DelegatingOAuth2TokenValidator` nếu hai điều kiện loại trừ nhau theo từng loại token.

**Nhiều issuer**:

~~~text
Issuer A → decoder/JWKS/policy A
Issuer B → decoder/JWKS/policy B
~~~

Không nên ghép `JwtIssuerValidator(issuerA)` và `JwtIssuerValidator(issuerB)` qua AND nếu token hợp lệ được phát hành bởi **một** trong hai issuer. Thay vào đó, thiết kế resolver hoặc registry của các issuer **được tin cậy** và áp bộ validator phù hợp cho mỗi issuer. Claim `iss` chưa xác minh chỉ được dùng làm gợi ý lựa chọn trong một allowlist, sau đó chữ ký và issuer phải được xác thực bằng nguồn khóa tương ứng.

## 11. Kết quả nhiều lỗi và cách truyền lỗi

Một JWT có thể vi phạm đồng thời nhiều điều kiện, ví dụ:

~~~json
{
  "iss": "https://unknown-issuer.example.test",
  "aud": ["billing-api"],
  "exp": 1700000000,
  "client_id": "unknown-client"
}
~~~

Giả sử chữ ký đã được xác minh bằng một nguồn khóa phù hợp trong môi trường thử nghiệm, và API áp các rule issuer, timestamp, audience, client. Khi chạy `DelegatingOAuth2TokenValidator`, các validator tương ứng có thể tạo những lỗi riêng:

~~~text
issuer validator       → invalid_token
timestamp validator    → invalid_token
audience validator     → invalid_token
allowed client         → invalid_token
              |
              v
DelegatingOAuth2TokenValidator
              |
              v
OAuth2TokenValidatorResult.failure([...])
~~~

Trong Spring Security, `OAuth2TokenValidatorResult` có thể biểu diễn **nhiều `OAuth2Error`**, không chỉ một. Một validator chỉ cần trả `success()` khi điều kiện riêng của nó đạt, hoặc `failure(...)` khi không đạt.

### 11.1. Đọc `OAuth2TokenValidatorResult`

Ví dụ minh họa với một validator:

~~~java
OAuth2TokenValidatorResult result = audienceValidator.validate(jwt);

if (result.hasErrors()) {
    for (OAuth2Error error : result.getErrors()) {
        // Xử lý thông tin lỗi theo chính sách nội bộ.
        // Tuyệt đối không log raw JWT.
        String code = error.getErrorCode();
    }
}
~~~

Trong đoạn trên, `jwt` được hiểu là một `Jwt` mà ứng dụng đang kiểm tra trong code minh họa. **Không nên tự decode payload chưa xác minh trong HTTP endpoint rồi gọi validator trực tiếp và coi đó là xác thực JWT đầy đủ**. Khi vận hành Resource Server, hãy để `JwtDecoder` chịu trách nhiệm xác minh JWS và áp validator.

### 11.2. Đừng phụ thuộc thứ tự lỗi làm policy nghiệp vụ

Vì nhiều validator có thể thất bại cùng lúc, ứng dụng không nên dựa vào “lỗi đầu tiên” để quyết định có cho request đi tiếp không. Mọi lỗi xác thực bắt buộc đều khiến JWT không được chấp nhận. Có thể nhóm lỗi thành:

| Loại lỗi | Dùng để vận hành | Phản hồi public |
|---|---|---|
| `invalid_token` vì issuer | Kiểm tra cấu hình trusted issuer | Không lộ chi tiết hạ tầng |
| `invalid_token` vì audience | Kiểm tra resource ID của client/AS | Không công bố danh sách audience bí mật |
| `invalid_token` vì timestamp | Kiểm tra TTL và đồng bộ đồng hồ | Challenge Bearer phù hợp |
| `invalid_token` vì custom claim | Kiểm tra token profile/issuer mapping | Tránh trả mọi giá trị claim nhạy cảm |

Không đưa nguyên payload JWT hoặc header Authorization vào exception message. Khi cần quan sát, có thể ghi **nhóm nguyên nhân đã chuẩn hóa**, request ID và thông số môi trường không nhạy cảm.

### 11.3. Thế nào là fail closed?

Nếu validator ném exception do logic lập trình lỗi, decoder không đọc được JWK Set, hoặc kết quả xác thực không thể được kết luận an toàn, request không được phép chuyển thẳng vào controller như một principal đã xác thực.

Điều đó không bắt buộc mọi lỗi hạ tầng đều có response giống lỗi JWT hết hạn. Một lỗi mạng tới JWK endpoint có thể được xử lý thành **lỗi dịch vụ** tùy cấu hình; điều bắt buộc là **không chấp nhận token chưa xác minh**.

## 12. Tùy biến `JwtDecoder` không đồng nghĩa phải viết lại mọi validator

Một API có thể chỉ cần:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.test/realms/company
~~~

Khi dùng decoder mặc định, Spring Security thường áp bộ kiểm tra issuer/thời gian mà cấu hình hiện tại cung cấp. Nếu framework/phiên bản ứng dụng hỗ trợ cấu hình audience qua property chính thức, có thể ưu tiên cơ chế đó để giảm code tùy chỉnh.

Ngược lại, nếu ứng dụng tự tạo:

~~~java
@Bean
JwtDecoder decoder() {
    // Custom decoder.
}
~~~

Spring Boot thường **không tự tạo thêm `JwtDecoder` mặc định** khi đã có bean do ứng dụng cung cấp. Vì vậy code tùy chỉnh phải chủ động khai báo **nguồn khóa, thuật toán, issuer/time và các custom validators**. Giữ những property mặc định trong YAML không bảo đảm custom bean sẽ tự nạp toàn bộ ràng buộc.

### 12.1. Ghép validator ở đúng tầng

~~~mermaid
flowchart TD
    A["Cần thêm điều kiện vào Resource Server"] --> B{"Điều kiện là gì?"}
    B -->|"Chữ ký/thuật toán/khóa"| C["Cấu hình JwtDecoder / JOSE"]
    B -->|"iss, exp, nbf, aud, token profile"| D["OAuth2TokenValidator<Jwt>"]
    B -->|"scope, role → authorities"| E["JwtAuthenticationConverter"]
    B -->|"HTTP operation / method"| F["SecurityFilterChain / method security"]
    B -->|"Owner, tenant của bản ghi"| G["Service/domain authorization"]
    D --> H["DelegatingOAuth2TokenValidator + default validators"]
~~~

Một thay đổi nhỏ ở validator có thể ảnh hưởng nhiều client và flow OAuth 2.0. Chẳng hạn bắt buộc mọi token có `client_id` khi issuer hiện vẫn phát hành một số token profile không có claim này sẽ khiến những token hợp lệ trước đây bị từ chối. Yêu cầu mới cần được công bố trong **hợp đồng token** trước khi đưa thành điều kiện bắt buộc.

### 12.2. Có thể chỉ dùng `JwtClaimValidator` mà không tự tạo bean decoder?

Điều này phụ thuộc cách framework/ứng dụng cho phép tùy biến validator đang dùng. Một đối tượng `JwtClaimValidator` chưa được gắn vào decoder thì **không có tác dụng lên authentication**. Nếu muốn thay decoder để thêm validator, hãy bảo đảm decoder đó thực sự được sử dụng bởi security chain. Nếu ứng dụng có nhiều security chain, mỗi chain cần chính sách tương ứng.

Mục tiêu cuối cùng không phải có nhiều bean trong context, mà là **mọi request tới API được bảo vệ đều đi qua decoder có validator hợp đồng**.

## 13. Dùng cùng cách hợp thành trên Spring WebFlux

Spring WebFlux Resource Server sử dụng `ReactiveJwtDecoder` thay vì `JwtDecoder` đồng bộ. Tuy nhiên, **validator claim vẫn có kiểu `OAuth2TokenValidator<Jwt>`**, và nguyên tắc ghép vẫn như trên.

Dependency thường dùng:

~~~gradle
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
~~~

Ví dụ bean decoder reactive (giả định vẫn dùng nhóm `app.security.jwt.*` ở mục 6):

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusReactiveJwtDecoder;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;

@Configuration
public class ReactiveOrdersDecoderConfig {

    @Bean
    ReactiveJwtDecoder reactiveJwtDecoder(
            @Value("${app.security.jwt.issuer}") String issuer,
            @Value("${app.security.jwt.jwk-set-uri}") String jwksUri,
            @Value("${app.security.jwt.audience}") String audience) {

        NimbusReactiveJwtDecoder decoder =
            NimbusReactiveJwtDecoder.withJwkSetUri(jwksUri)
                .jwsAlgorithm(SignatureAlgorithm.RS256)
                .build();

        OAuth2TokenValidator<Jwt> audienceRule = jwt ->
            jwt.getAudience().contains(audience)
                ? OAuth2TokenValidatorResult.success()
                : OAuth2TokenValidatorResult.failure(
                    new OAuth2Error(
                        "invalid_token",
                        "JWT audience is invalid",
                        null
                    )
                );

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                JwtValidators.createDefaultWithIssuer(issuer),
                audienceRule
            )
        );

        return decoder;
    }
}
~~~

Ví dụ `SecurityWebFilterChain`:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration
public class ReactiveOrdersSecurityConfig {

    @Bean
    SecurityWebFilterChain apiSecurity(ServerHttpSecurity http) {
        return http
            .authorizeExchange(auth -> auth
                .pathMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .anyExchange().authenticated()
            )
            .oauth2ResourceServer(oauth2 -> oauth2.jwt(withDefaults()))
            .build();
    }
}
~~~

Các đoạn trên thuộc **stack WebFlux** và là phương án thay thế tương ứng, không phải code dùng chung trong một cấu hình Servlet. Spring Security sẽ sử dụng `ReactiveJwtDecoder` từ context khi được wiring phù hợp.

**Lưu ý WebFlux:** validator `OAuth2TokenValidator<Jwt>` là một phép kiểm tra đồng bộ trên claims đã có. Không nên thực hiện HTTP request blocking đến dịch vụ khác bên trong lambda validator khi đang xử lý Reactive Resource Server; việc đó có thể chặn event loop. Nếu policy bắt buộc tra cứu dữ liệu bên ngoài, cần thiết kế một tầng kiểm tra/authorization bất đồng bộ hoặc cơ chế tin cậy riêng phù hợp với kiến trúc reactive.

### Bảng so sánh

| Vấn đề | Servlet / Spring MVC | WebFlux |
|---|---|---|
| HTTP security builder | `HttpSecurity` | `ServerHttpSecurity` |
| Chain | `SecurityFilterChain` | `SecurityWebFilterChain` |
| Decoder | `JwtDecoder` / `NimbusJwtDecoder` | `ReactiveJwtDecoder` / `NimbusReactiveJwtDecoder` |
| Claim validator | `OAuth2TokenValidator<Jwt>` | `OAuth2TokenValidator<Jwt>` |
| Hợp thành | `DelegatingOAuth2TokenValidator<Jwt>` | `DelegatingOAuth2TokenValidator<Jwt>` |
| Decoder custom API | `setJwtValidator(...)` | `setJwtValidator(...)` |
| Authentication kết quả | `JwtAuthenticationToken` | `JwtAuthenticationToken` trong reactive security context |

Quy tắc issuer, audience, thời gian và token profile **không thay đổi** vì ứng dụng chuyển từ Servlet sang WebFlux.

## 14. Opaque token và `OAuth2TokenValidator`: đừng ghép nhầm pipeline

`DelegatingOAuth2TokenValidator<Jwt>` được sử dụng để hợp thành kiểm tra trên đối tượng `Jwt`. Nhưng một **opaque token** thường được Resource Server kiểm tra qua **introspection endpoint** bằng `OpaqueTokenIntrospector` hoặc `ReactiveOpaqueTokenIntrospector`.

~~~text
JWT access token:
    JwtDecoder
      → JWS validation
      → OAuth2TokenValidator<Jwt>
      → JwtAuthenticationToken

Opaque access token:
    OpaqueTokenIntrospector
      → HTTP introspection tới trusted AS
      → active + attributes + authorities
      → BearerTokenAuthentication
~~~

Nếu ứng dụng đang dùng `oauth2ResourceServer(o -> o.opaqueToken(...))`, việc tạo thêm bean `DelegatingOAuth2TokenValidator<Jwt>` **không làm introspection tự động kiểm tra audience hoặc tenant**. Cần ràng buộc policy ở introspection provider hoặc tùy biến introspector phù hợp với dữ liệu mà Authorization Server trả về.

Ngược lại, việc JWT decoder kiểm tra `iss`/`aud` cũng không thay OAuth 2.0 Token Introspection. Hai hướng có thể dùng cùng **hợp đồng truy cập**, nhưng cơ chế xác minh và điểm gắn validator khác nhau.

## 15. Minh họa kiểm tra validator độc lập

Ví dụ phần này nhằm diễn giải cách một validator xử lý các claim của một `Jwt` đã có, **không phải** ví dụ xác minh chữ ký JWT thật. Trong một ứng dụng đang chạy, chỉ `JwtDecoder` với nguồn khóa tin cậy mới quyết định token nhận từ HTTP có đáng tin hay không.

### 15.1. Dựng một `Jwt` mẫu cho logic validator

~~~java
import java.time.Instant;
import org.springframework.security.oauth2.jwt.Jwt;

Instant now = Instant.parse("2026-11-15T10:00:00Z");

Jwt exampleJwt = Jwt.withTokenValue("for-validator-example-only")
    .header("alg", "RS256")
    .issuer("https://login.example.test/realms/company")
    .subject("user-123")
    .audience(java.util.List.of("orders-api"))
    .issuedAt(now.minusSeconds(60))
    .notBefore(now.minusSeconds(60))
    .expiresAt(now.plusSeconds(600))
    .claim("scope", "orders.read")
    .build();
~~~

`Jwt.withTokenValue(...)` xây một đối tượng Java cho ví dụ logic. **Nó không ký token, không chứng minh chữ ký, không thực hiện HTTP discovery**, và `for-validator-example-only` không phải Bearer JWT có thể gọi API. Mốc `now` cố định minh họa việc kiểm tra claim; nếu dùng timestamp validator thật, bộ kiểm tra thời gian đọc clock theo cấu hình, nên mốc test phải phù hợp hoặc clock cần được kiểm soát trong setup phù hợp.

### 15.2. Minh họa kết quả của validator audience

~~~java
OAuth2TokenValidator<Jwt> audienceRule = jwt ->
    jwt.getAudience().contains("orders-api")
        ? OAuth2TokenValidatorResult.success()
        : OAuth2TokenValidatorResult.failure(
            new OAuth2Error("invalid_token", "Wrong audience", null));

OAuth2TokenValidatorResult goodResult =
    audienceRule.validate(exampleJwt);

// goodResult.hasErrors() == false
~~~

Đổi audience:

~~~java
Jwt wrongAudience = Jwt.withTokenValue("example-wrong-audience")
    .header("alg", "RS256")
    .claim("iss", "https://login.example.test/realms/company")
    .claim("sub", "user-123")
    .claim("aud", java.util.List.of("billing-api"))
    .issuedAt(now.minusSeconds(60))
    .expiresAt(now.plusSeconds(600))
    .build();

OAuth2TokenValidatorResult wrongResult =
    audienceRule.validate(wrongAudience);

// wrongResult.hasErrors() == true
~~~

Ở đây `wrongAudience` có thể có cả issuer và thời gian hợp lệ trong một bối cảnh test, nhưng không thỏa `aud=orders-api` nên bị audience rule từ chối. Lưu ý ví dụ chỉ gọi validator đơn lẻ; nó **không** đánh giá issuer, expiry hoặc signature ở bước trên.

### 15.3. Minh họa một validator hợp thành

~~~java
OAuth2TokenValidator<Jwt> issuerAndTime =
    JwtValidators.createDefaultWithIssuer(
        "https://login.example.test/realms/company");

OAuth2TokenValidator<Jwt> combined =
    new DelegatingOAuth2TokenValidator<>(
        issuerAndTime,
        audienceRule
    );

OAuth2TokenValidatorResult result = combined.validate(exampleJwt);
~~~

Với phép kiểm tra thời gian thật, kết quả phụ thuộc thời điểm thực hiện và clock/skew. **Không dùng mốc giờ cố định 2026 trong một test chạy mãi về sau rồi mong token vẫn chưa hết hạn**. Khi cần test tự động có tính quyết định, hãy dùng JWT với timestamp được tạo tương ứng lúc chạy hoặc thiết lập clock theo API phù hợp.

## 16. Ma trận tình huống nên được mô tả trong hợp đồng

Với Orders API:

~~~text
Trusted issuer = https://login.example.test/realms/company
Expected aud   = orders-api
Required GET scope = orders.read
Mandatory claim = exp
Allowed client_id = orders-web hoặc orders-mobile
~~~

| Kịch bản | Validator / tầng xử lý | Kết quả mong đợi |
|---|---|---|
| JWT ký đúng, issuer đúng, audience đúng, chưa hết hạn, client hợp lệ | Decoder + tất cả claim validators | Token được xác thực; authorization tiếp tục |
| Chữ ký giả | JWS verification | Từ chối trước khi tin các claims |
| `alg` không nằm trong allowlist | JWS verification | Từ chối |
| `iss` là issuer khác | Default/issuer validator | Từ chối xác thực |
| `exp` đã qua | Timestamp validator | Từ chối xác thực |
| Token chưa đến `nbf` | Timestamp validator | Từ chối xác thực |
| `exp` thiếu dù profile bắt buộc | `expiryRequired` | Từ chối xác thực |
| `aud` chỉ chứa `billing-api` | `expectedAudience` | Từ chối xác thực |
| `aud` là `orders-api` nhưng `client_id` không được phép | `allowedClient` | Từ chối xác thực |
| `tenant_id` thiếu khi API bắt buộc | `knownTenant` | Từ chối xác thực |
| `iat` quá cũ so với max age | `tokenAge` | Từ chối xác thực |
| Issuer sai **và** audience sai | Nhiều validator | Hợp thành trả kết quả thất bại |
| JWT hợp lệ nhưng không có `orders.read` | Authorization bằng `SCOPE_orders.read` | Thường 403 |
| JWT hợp lệ, đủ scope, order không thuộc principal | Authorization nghiệp vụ | Từ chối theo policy |

Một test sử dụng `SecurityMockMvcRequestPostProcessors.jwt()` rất hữu ích để kiểm tra rule `hasAuthority(...)` của HTTP layer, nhưng nó thường **bỏ qua decoder thật**. Vì thế test đó không chứng minh chữ ký, issuer, audience, thời gian hoặc `DelegatingOAuth2TokenValidator` đã thực thi.

Nếu cần kiểm chứng end-to-end, hãy dùng **JWT thử nghiệm có chữ ký thật** với public JWK thử nghiệm được cung cấp cho `JwtDecoder`, rồi gửi token qua `Authorization: Bearer` tới ứng dụng. Test các token sai issuer/audience/time và sai chữ ký bằng những trường hợp riêng. Không dùng private signing key production trong test.

## 17. Một mẫu tổ chức code dễ mở rộng

Khi hợp đồng của API phát triển, có thể tránh đặt toàn bộ lambda validator trong bean decoder. Thay vào đó, mỗi validator được gói thành class hoặc factory đơn nhiệm.

Ví dụ một validator audience có thể tái sử dụng:

~~~java
import java.util.Objects;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;

public final class ApiAudienceValidator
        implements OAuth2TokenValidator<Jwt> {

    private final String expectedAudience;

    public ApiAudienceValidator(String expectedAudience) {
        this.expectedAudience =
            Objects.requireNonNull(expectedAudience);
    }

    @Override
    public OAuth2TokenValidatorResult validate(Jwt jwt) {
        if (jwt.getAudience().contains(expectedAudience)) {
            return OAuth2TokenValidatorResult.success();
        }
        return OAuth2TokenValidatorResult.failure(
            new OAuth2Error(
                "invalid_token",
                "JWT audience is not accepted",
                null
            )
        );
    }
}
~~~

Bean decoder chỉ tập trung kết nối các điều kiện:

~~~java
OAuth2TokenValidator<Jwt> validation =
    new DelegatingOAuth2TokenValidator<>(
        JwtValidators.createDefaultWithIssuer(issuer),
        new ApiAudienceValidator(audience),
        expiryRequired
    );

decoder.setJwtValidator(validation);
~~~

Mẫu tổ chức này có một số lợi ích:

- Mỗi quy tắc nêu rõ một điều kiện và lý do từ chối.
- Dễ gắn bộ validator phù hợp cho từng Resource Server.
- Dễ phân biệt điều kiện **bắt buộc** của token với authority/policy ở tầng sau.
- Khi thêm claim tùy biến, có thể xem ảnh hưởng riêng của nó đến các token profile hiện hữu.

Tuy nhiên, đừng biến một validator thuần dữ liệu thành nơi truy vấn cơ sở dữ liệu phức tạp, gọi HTTP tới API khác hoặc tự ghi đè `SecurityContextHolder`. Nếu chính sách cần dữ liệu request hoặc quyền trên bản ghi, đặt nó ở thành phần authorization phù hợp.

### 17.1. Cấu hình ứng dụng nhiều Resource Server hoặc nhiều issuer

Một hệ thống có thể cung cấp nhiều API hoặc được cho phép tin cậy nhiều issuer. Các tập validator cần **đúng ranh giới**:

~~~text
Orders API:
  iss = issuer-A
  aud = orders-api
  required claims = orders profile

Billing API:
  iss = issuer-A
  aud = billing-api
  required claims = billing profile

Partner API:
  iss = issuer-B (allowlisted)
  aud = partner-api
  required claims = partner profile
~~~

Không dùng một validator audience duy nhất chấp nhận **mọi API audience** chỉ vì các dịch vụ dùng chung issuer. Nếu API có nhiều security chain, bảo đảm matcher chọn đúng decoder/policy. Nếu có nhiều issuer, chọn đúng bộ tin cậy và decoder/JWK riêng trước khi áp claim validators.

## 18. Những lỗi cấu hình phổ biến

### 18.1. Thêm audience nhưng mất validation thời gian

~~~java
// Sai nếu đây là validator duy nhất sau khi ghi đè:
decoder.setJwtValidator(new ApiAudienceValidator("orders-api"));
~~~

Cần ghép `JwtValidators.createDefaultWithIssuer(issuer)` hoặc bộ validation mặc định tương đương **cùng** audience. Đây là một trong những rủi ro thực tế lớn nhất khi tùy biến `JwtDecoder`.

### 18.2. Dùng validator AND cho hai issuer loại trừ nhau

~~~java
// Không có JWT bình thường nào cùng lúc có hai iss khác nhau:
new DelegatingOAuth2TokenValidator<>(
    new JwtIssuerValidator(issuerA),
    new JwtIssuerValidator(issuerB)
);
~~~

Nếu hệ thống cho phép Issuer A **hoặc** B, hãy dùng mô hình multi-issuer đã được allowlist và xác minh bằng đúng nguồn khóa/validator của issuer được chọn.

### 18.3. Dùng validator AND cho hai audience có nghĩa OR

~~~text
Sai: require audience A AND require audience B
Đúng khi policy cho phép một trong hai:
    audience chứa A OR audience chứa B
    → một audience validator có allowlist
~~~

Nếu policy yêu cầu token chỉ có một audience, hãy thể hiện điều kiện đó riêng. Không mặc định multi-audience an toàn cho mọi Resource Server.

### 18.4. Validator chỉ kiểm tra claim mà bỏ qua trust key

Một JWT tự khai báo `iss`, `aud` và `scope` đúng vẫn không đáng tin nếu chữ ký chưa được xác minh bằng khóa và thuật toán được phép. `DelegatingOAuth2TokenValidator` không tự tạo JWS verification; phần đó thuộc decoder/JOSE library.

### 18.5. Tưởng claim thiếu tương đương một giá trị hợp lệ

Ví dụ:

~~~java
// Sai nếu policy yêu cầu tenant phải tồn tại:
boolean allowed = jwt.getClaimAsString("tenant_id") == null
    || knownTenants.contains(jwt.getClaimAsString("tenant_id"));
~~~

Điều kiện trên chấp nhận token thiếu tenant. Nếu hợp đồng bắt buộc claim, phải **từ chối khi claim thiếu**. Ngược lại, với token profile có claim tùy chọn, không áp quy tắc bắt buộc thiếu cơ sở.

### 18.6. Dùng claim `scope` làm điều kiện xác thực chung cho mọi endpoint

Một token có thể được cấp hợp lệ cho `orders.read` nhưng không có `orders.create`. Nếu custom validator toàn API yêu cầu luôn có `orders.create`, nó sẽ từ chối cả những token chỉ dùng để đọc. Scope cụ thể cho từng HTTP action nên được áp ở tầng authorization, không biến mọi scope thành **điều kiện sống còn** của access token trên tất cả endpoint.

### 18.7. Nhầm `DelegatingOAuth2TokenValidator` với `JwtAuthenticationConverter`

Validator trả **kết quả hợp lệ/thất bại**, không trả `GrantedAuthority`. Converter chuyển dữ liệu claims đã xác minh thành principal/authority. Chúng có mục đích và thời điểm chạy khác nhau.

### 18.8. Tạo validator nhưng quên gắn vào decoder đang được dùng

Một bean hoặc biến `OAuth2TokenValidator<Jwt>` chưa gắn vào `JwtDecoder` sẽ không tự tác động lên tất cả HTTP request. Cần kiểm soát nơi tạo decoder và nơi `SecurityFilterChain` nhận decoder, nhất là khi ứng dụng có nhiều chain.

### 18.9. Để lỗi custom validator làm lộ dữ liệu nhạy cảm

Tránh thông báo lỗi chứa raw JWT, các claim PII, access token, signing key hoặc thông tin nội bộ của IdP. Dùng mã lỗi và mô tả ngắn, phân loại metric nội bộ theo chính sách.

### 18.10. Thay validator thời gian bằng cách thêm bộ kiểm tra trùng lặp

Nếu cần clock skew mới, không kết luận rằng thêm `JwtTimestampValidator` thứ hai sẽ thay thế bộ mặc định. Các validator cùng chạy theo logic AND, nên phải thiết kế lại tập kiểm tra thời gian có chủ đích và giữ những default rules khác.

## 19. Câu hỏi tự kiểm tra

**Câu 1.** `DelegatingOAuth2TokenValidator` kết hợp các validator bằng phép AND hay OR?

Theo **AND**: token chỉ hợp lệ khi tất cả validator thành phần đều thành công. Nếu cần OR cho một claim, hãy viết điều kiện OR trong validator riêng.

**Câu 2.** Vì sao gọi `setJwtValidator(audienceValidator)` có thể gây rủi ro?

Vì `setJwtValidator` chỉ định validator của decoder, không tự nối vào bộ cũ. Nếu không ghép lại default/time/issuer validators, token sai thời gian hoặc issuer có thể không bị từ chối như hợp đồng.

**Câu 3.** `DelegatingOAuth2TokenValidator` có tự xác minh chữ ký RSA/ECDSA không?

Không. Xác minh JWS bằng nguồn khóa tin cậy thuộc `JwtDecoder`/JOSE implementation. Claim validator làm việc sau bước xử lý chữ ký phù hợp của decoder.

**Câu 4.** Khi nào cần audience validator?

Khi Resource Server phải bảo đảm access token được phát hành cho đúng API/resource, đặc biệt khi một issuer cấp token cho nhiều API. Cần dùng resource identifier chính thức từ hợp đồng.

**Câu 5.** Một token hợp lệ có `scope=orders.read` nhưng không có `orders.create`. Nên bị từ chối lúc decode không?

Không nhất thiết. Nếu cả hai scope đều hợp lệ theo profile, token chỉ đọc có thể được xác thực. Khi gọi `POST /api/orders`, HTTP authorization mới từ chối vì thiếu `SCOPE_orders.create`.

**Câu 6.** Có nên đọc claim `iss` chưa xác minh rồi tự động khám phá JWKS của bất kỳ URL nào không?

Không. Issuer phải nằm trong danh sách tin cậy trước; lựa chọn decoder/key source phải tuân thủ policy. Một giá trị issuer chưa xác minh chỉ có thể được dùng làm gợi ý định tuyến trong resolver có allowlist nghiêm ngặt.

**Câu 7.** Khi dùng opaque token, thêm bean `OAuth2TokenValidator<Jwt>` có làm introspection tự kiểm tra audience không?

Không. Opaque token đi qua `OpaqueTokenIntrospector` và cần chính sách tương ứng tại introspection/Resource Server.

## 20. Ghi nhớ cách hợp thành

Một mẫu cấu hình dễ nhận diện:

~~~java
OAuth2TokenValidator<Jwt> validators =
    new DelegatingOAuth2TokenValidator<>(
        JwtValidators.createDefaultWithIssuer(trustedIssuer),
        new ApiAudienceValidator("orders-api"),
        extraClaimValidator
    );

decoder.setJwtValidator(validators);
~~~

Trong đó `trustedIssuer`, `decoder` và `extraClaimValidator` là các đối tượng/giá trị do ứng dụng thiết lập theo hợp đồng; mã chỉ minh họa cấu trúc, không phải class độc lập.

Điều kiện chấp nhận JWT tại Resource Server:

~~~text
JWT được chấp nhận
    =
    Chữ ký hợp lệ bằng khóa/thuật toán tin cậy
    AND Issuer đúng
    AND Token có hiệu lực về thời gian
    AND Audience đúng API
    AND Các claim/profile bắt buộc khác hợp lệ
~~~

Sau đó mới đến:

~~~text
Authorization cho request
    =
    Authentication thành công
    AND Scope/authority phù hợp HTTP action
    AND Quyền nghiệp vụ trên tài nguyên/tenant được thỏa
~~~

**`DelegatingOAuth2TokenValidator` là công cụ ghép các quy tắc kiểm tra token độc lập**, giúp mở rộng yêu cầu của API mà không phải viết lại mọi thứ trong một validator lớn. Kết hợp nó với `JwtValidators.createDefaultWithIssuer(...)` là cách quan trọng để **bổ sung** yêu cầu audience, client hoặc token profile mà **không vô tình đánh mất** những kiểm tra mặc định. Tuy nhiên, nó chỉ có hiệu lực khi được gắn vào decoder thật đang bảo vệ Resource Server.

## Tài liệu tham khảo

- [Spring Security — Servlet OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
- [Spring Security — Reactive OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html)
- [Spring Security — NimbusJwtDecoder Javadoc](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/jwt/NimbusJwtDecoder.html)
- [Spring Security — JwtValidators Javadoc](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/jwt/JwtValidators.html)
- [Spring Security — OAuth2TokenValidator Javadoc](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/core/OAuth2TokenValidator.html)
- [Spring Security — DelegatingOAuth2TokenValidator Javadoc](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/core/DelegatingOAuth2TokenValidator.html)
- [Spring Security — JwtClaimValidator Javadoc](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/jwt/JwtClaimValidator.html)
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519)
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725)
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068)
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
