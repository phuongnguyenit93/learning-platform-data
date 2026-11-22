# Hỗ trợ JWT và opaque token trong một Resource Server

Một **Spring Security OAuth 2.0/OIDC Resource Server** có thể phải chấp nhận hai dạng **OAuth 2.0 bearer access token**: **JWT** và **opaque token**. Trường hợp này thường xuất hiện khi chuyển đổi từ token tham chiếu sang JWT, khi nhiều Authorization Server (AS) cấp token cho cùng API, hoặc khi một số tenant dùng JWT còn các tenant khác dùng opaque token cần introspection.

Ví dụ, cùng hệ thống Orders API phục vụ:

- Tenant A: AS phát access token dạng JWT, Resource Server xác minh chữ ký bằng JWK Set.
- Tenant B: AS phát access token dạng opaque, Resource Server hỏi OAuth 2.0 Token Introspection Endpoint để xác nhận token `active`.
- Trong giai đoạn migration: một số client còn dùng token tham chiếu, các client khác đã chuyển sang JWT.
- Một API có yêu cầu thu hồi token nhanh: có thể chọn introspection ngay cả với JWT nếu AS hỗ trợ và policy yêu cầu.

Hai dạng token **có thể cùng được hỗ trợ**, nhưng không nên suy ra rằng chỉ cần gọi cả `.jwt()` lẫn `.opaqueToken()` trong cùng một cấu hình Spring Security là xong.

> **Nguyên tắc nền tảng:** **việc chọn cơ chế xác thực** là một bước định tuyến; **việc chứng minh token hợp lệ** vẫn bắt buộc do `JwtDecoder` hoặc `OpaqueTokenIntrospector` tương ứng thực hiện. Không xem hình dạng token, đường dẫn, header do client gửi hoặc issuer chưa được xác minh là bằng chứng đã cấp quyền.

Bài này đi sâu vào **`SecurityFilterChain`**, **`AuthenticationManagerResolver<HttpServletRequest>`**, **`JwtAuthenticationProvider`**, **`OpaqueTokenAuthenticationProvider`**, thiết kế định tuyến JWT/opaque, issuer/audience/resource binding, thống nhất scope/authority, xử lý lỗi và kiểm thử. Phần mã chính dùng **Spring Security Servlet/Spring MVC, Java 17+, Spring Boot hiện đại**. Với WebFlux phải dùng các API reactive khác, được nhắc tới riêng ở cuối.

## 1. Phân biệt JWT và opaque access token

JWT và opaque token đều có thể được dùng với cú pháp HTTP bearer:

~~~http
GET /api/orders HTTP/1.1
Host: orders.example.com
Authorization: Bearer <access-token>
~~~

Khác biệt nằm ở **cách Resource Server xác thực token**, không phải ở HTTP header.

| Khía cạnh | JWT access token | Opaque access token |
|---|---|---|
| Hình thức thường gặp | Compact JWS gồm ba phần | Chuỗi tham chiếu không cần định dạng đọc được |
| Xác minh | Chữ ký JWS, khóa tin cậy, claims validators | Introspection qua AS hoặc token validation service |
| Thành phần Spring Security Servlet | `JwtDecoder`, `JwtAuthenticationProvider` | `OpaqueTokenIntrospector`, `OpaqueTokenAuthenticationProvider` |
| Principal mặc định | `Jwt` nằm trong `JwtAuthenticationToken` | `OAuth2AuthenticatedPrincipal` nằm trong `BearerTokenAuthentication` |
| Authorities phổ biến | `scope`/`scp` → `SCOPE_*` | `scope` trong introspection → `SCOPE_*` |
| Network call | Khi cần discovery/JWKS/refresh keys | Thường gọi introspection endpoint theo token, trừ khi có cache |
| Khả năng thu hồi sớm | Phụ thuộc thiết kế kiểm tra revocation/TTL | AS có thể trả `active=false` sau revocation |
| Ràng buộc token đúng API | Cần validate `aud`/resource và profile | AS/introspection response hoặc contract phải xác nhận resource binding |
| Không được làm | Decode payload chưa ký mà tin claims | Tự tạo principal không hỏi nguồn trạng thái tin cậy |

Ví dụ JWT payload minh họa:

~~~json
{
  "iss": "https://login.example.com/realms/orders",
  "sub": "user-42",
  "aud": ["orders-api"],
  "scope": "orders.read orders.write",
  "exp": 2000000300
}
~~~

Dữ liệu này **chỉ có giá trị security** khi chữ ký được kiểm tra với public key thuộc issuer đã được phê duyệt và các validators thành công. Base64URL decode payload để xem `scope` **không** phải JWT verification.

Một opaque introspection response có thể có:

~~~json
{
  "active": true,
  "sub": "user-42",
  "client_id": "legacy-orders-client",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "exp": 2000000300
}
~~~

`active=true` là kết quả **từ introspection endpoint đáng tin**. Không tự chấp nhận một JSON do client gửi hoặc một endpoint tự khai là `active=true`.

### 1.1. Token nhìn giống JWT chưa chắc là token được chấp nhận

Ba phần ngăn bởi dấu chấm thường là dấu hiệu compact JWS, nhưng:

- Caller có thể tạo ra chuỗi ba phần giả mạo.
- Một opaque token về mặt lý thuyết có thể chứa dấu chấm hoặc trông như JWT.
- JWE compact token thường có năm phần, không giống JWS ba phần.
- Có nhiều JWT profiles khác nhau: OIDC ID token, access token, client assertion, DPoP proof, v.v.
- ID token có chữ ký hợp lệ **không** tự là access token dành cho Orders API.

**Hình dạng là gợi ý định tuyến có thể kiểm chứng, không phải nguồn tin cậy.** Phân loại nhầm có thể gây authentication failure; không được dùng phân loại để bỏ qua xác minh.

## 2. Hai mô hình triển khai chính

Một Resource Server có thể hỗ trợ cả hai loại token bằng những kiến trúc khác nhau:

~~~text
                 Một ứng dụng Resource Server
                               |
                    Có bearer access token?
                               |
                               v
                 Chọn cơ chế authentication
                     /                \
                   JWT                Opaque
                    |                   |
              JwtDecoder       OpaqueTokenIntrospector
                    |                   |
             verify JWS             active=true?
             validate claims        validate token context
                     \                 /
                      \               /
                          Authentication
                               |
                         Authorization
                         + scope/role
                         + tenant/ACL
                         + business rules
                               |
                            Handler
~~~

Có hai trường hợp thực tế:

**A. Các routes có contract khác nhau.** `/api/jwt/**` chỉ nhận JWT; `/api/legacy/**` chỉ nhận opaque. Có thể dùng **hai `SecurityFilterChain`**, mỗi chain một cấu hình Resource Server.

**B. Cùng route phải nhận được cả hai.** `/api/orders/**` có thể nhận access token JWT hoặc opaque. Cần một **`AuthenticationManagerResolver<HttpServletRequest>`** để chọn `AuthenticationManager` ở request-time, dựa trên một quy tắc định tuyến có chủ đích và sau đó vẫn xác minh token bằng provider đúng.

Ngoài ra còn **C. Dùng introspection cho cả hai**: nếu AS chấp nhận introspect JWT lẫn opaque access token, Resource Server có thể cấu hình **một opaque token flow** và không cần phân loại định dạng ở API. Phương án này thay đổi trade-off về network, revocation và nguồn tin cậy.

## 3. Những giới hạn quan trọng của DSL

Mã sau **không phải** cách bật cả hai token trong cùng một Spring Security Resource Server configurer:

~~~java
// KHÔNG HỢP LỆ trong cùng một oauth2ResourceServer configurer.
.oauth2ResourceServer(oauth2 -> oauth2
    .jwt(Customizer.withDefaults())
    .opaqueToken(Customizer.withDefaults())
)
~~~

Spring Security kiểm tra cấu hình: nếu không có `AuthenticationManagerResolver` riêng, Resource Server configurer chỉ hỗ trợ **JWT hoặc opaque token**, không bật cả hai cùng lúc. Trong mã nguồn `OAuth2ResourceServerConfigurer`, việc cấu hình đồng thời hai chế độ mặc định có thể bị từ chối khi build security chain.

Một cách khác cũng sai:

~~~java
// Không trộn với .jwt()/.opaqueToken() trong cùng configurer.
.oauth2ResourceServer(oauth2 -> oauth2
    .authenticationManagerResolver(myResolver)
    .jwt(Customizer.withDefaults())
)
~~~

Khi có resolver riêng, resolver **thay thế chiến lược chọn authentication manager** mặc định. Trong cùng configurer, không nên đồng thời khai báo `jwt()` hoặc `opaqueToken()` như các nhánh sẽ tự được ghép.

### 3.1. Ba cách đúng cần nhớ

| Mục tiêu | Cấu hình |
|---|---|
| Chỉ JWT ở một chain | `.oauth2ResourceServer(o -> o.jwt(...))` |
| Chỉ opaque ở một chain | `.oauth2ResourceServer(o -> o.opaqueToken(...))` |
| JWT và opaque được chọn theo request trong **cùng chain** | `.oauth2ResourceServer(o -> o.authenticationManagerResolver(resolver))` |

Hai chain khác nhau **có thể** có cấu hình JWT và opaque riêng; giới hạn ở trên chỉ nói việc dùng cả hai nhánh mặc định trong **cùng một Resource Server configurer**.

## 4. Các thành phần đóng vai trò gì?

| Thành phần | Vai trò trong Servlet Resource Server |
|---|---|
| `BearerTokenAuthenticationFilter` | Lấy bearer token và chuyển request tới authentication strategy |
| `DefaultBearerTokenResolver` | Đọc bearer token theo quy tắc RFC 6750/Spring |
| `BearerTokenAuthenticationToken` | Đối tượng authentication chứa credential chưa xác minh |
| `AuthenticationManagerResolver<HttpServletRequest>` | Chọn `AuthenticationManager` cho request |
| `ProviderManager` | Sử dụng một hoặc nhiều `AuthenticationProvider` |
| `JwtAuthenticationProvider` | Dùng `JwtDecoder` xác minh JWT và tạo `JwtAuthenticationToken` |
| `OpaqueTokenAuthenticationProvider` | Dùng `OpaqueTokenIntrospector`, tạo `BearerTokenAuthentication` |
| `NimbusJwtDecoder` | Xác minh chữ ký JWS bằng nguồn public keys đáng tin |
| `SpringOpaqueTokenIntrospector` | Gọi introspection endpoint theo cấu hình đáng tin |
| `JwtAuthenticationConverter` | Ánh xạ JWT đã xác minh thành authorities |
| `OAuth2AuthenticatedPrincipal` | Principal từ introspection thành công |
| `AuthorizationFilter` / method security | Kiểm tra scope, roles, policies sau khi authentication thành công |

`AuthenticationManagerResolver` **chọn** phương thức xác minh, nhưng **không tự xác minh** token. `AuthorizationManager` quyết định quyền truy cập sau khi authentication thành công. Hai khái niệm không nên nhầm.

### 4.1. Vì sao Spring Security hỗ trợ resolver?

Mỗi request có thể có đặc tính khác nhau:

~~~text
Request 1 -> Tenant A / JWT
Request 2 -> Tenant B / opaque
Request 3 -> Tenant A / JWT
Request 4 -> Tenant C / unsupported
~~~

Nếu sử dụng một `JwtDecoder` duy nhất, opaque token không phải JWT sẽ không thể giải mã. Nếu dùng một introspector duy nhất, mọi token cần được AS introspect, điều có thể không phù hợp với hệ thống muốn xác minh JWT cục bộ.

Resolver cho phép chọn **manager đã được phê duyệt theo request**. Những manager không được chọn không nên tự động được gọi như một fallback cho token invalid.

## 5. Dependencies và cấu hình cơ bản

Ví dụ Gradle:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

Spring Boot quản lý phiên bản Spring Security/JOSE thông qua BOM. Nếu không dùng starter, cần đảm bảo đủ modules OAuth2 Resource Server và OAuth2 JOSE để dùng JWT.

Ví dụ `application.yml`:

~~~yaml
app:
  security:
    jwt:
      issuer: https://login.example.com/realms/orders
      jwk-set-uri: https://login.example.com/realms/orders/certs
      audience: orders-api
    opaque:
      introspection-uri: https://auth-legacy.example.com/oauth2/introspect
      client-id: orders-resource-server
      client-secret: "${INTROSPECTION_CLIENT_SECRET}"
      audience: orders-api
~~~

Các `app.security.*` là **property do ví dụ tự định nghĩa**, không phải toàn bộ property mặc định của Spring Boot. Khi tự tạo beans `JwtDecoder` và `OpaqueTokenIntrospector`, phải chủ động ràng buộc issuer, audience, URI và credentials.

**Không** hardcode introspection client secret vào source code, ảnh, log hoặc trình duyệt. Trong production, lấy nó từ secret manager/environment được kiểm soát.

## 6. Phương án A — Hai SecurityFilterChain theo route

Đây là phương án dễ hiểu nhất nếu hai nhóm endpoint **có URL namespace khác nhau**.

Giả sử:

~~~text
/api/jwt/**       chỉ nhận JWT access token
/api/legacy/**    chỉ nhận opaque access token
```

Mỗi chain có cùng Java application, nhưng một flow xác thực riêng:

~~~text
Incoming request
       |
       v
FilterChainProxy
       |
       +-- /api/jwt/** ?
       |       |
       |       +-- JwtDecoder / JwtAuthenticationProvider
       |
       +-- /api/legacy/** ?
       |       |
       |       +-- OpaqueTokenIntrospector / OpaqueTokenAuthenticationProvider
       |
       +-- other?
               |
               +-- fallback deny
~~~

### 6.1. Code tách chain

~~~java
package com.example.orders.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.server.resource.introspection.OpaqueTokenIntrospector;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class DualTokenChainsConfig {

    @Bean
    @Order(1)
    SecurityFilterChain jwtApiChain(
            HttpSecurity http,
            JwtDecoder decoder) throws Exception {

        return http
            .securityMatcher("/api/jwt/**")
            .csrf(AbstractHttpConfigurer::disable)
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/jwt/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/jwt/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyRequest().denyAll())
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(jwt -> jwt.decoder(decoder)))
            .build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain legacyApiChain(
            HttpSecurity http,
            OpaqueTokenIntrospector introspector) throws Exception {

        return http
            .securityMatcher("/api/legacy/**")
            .csrf(AbstractHttpConfigurer::disable)
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/legacy/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/legacy/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyRequest().denyAll())
            .oauth2ResourceServer(oauth2 -> oauth2
                .opaqueToken(opaque -> opaque.introspector(introspector)))
            .build();
    }

    @Bean
    @Order(3)
    SecurityFilterChain fallbackChain(HttpSecurity http)
            throws Exception {

        return http
            .authorizeHttpRequests(auth -> auth
                .anyRequest().denyAll())
            .build();
    }
}
~~~

**Giả định quan trọng:** hai API đều là **bearer-only**, không xác thực bằng cookie tự động gửi từ browser. Vì vậy ví dụ tắt CSRF trong hai API chains. Không áp dụng nguyên xi cho OIDC browser login, BFF hoặc cookie-based authentication; CSRF cần được đánh giá theo credential model.

### 6.2. Tác dụng của `securityMatcher` và `@Order`

- `securityMatcher("/api/jwt/**")` chọn **chain JWT** cho path tương ứng.
- `securityMatcher("/api/legacy/**")` chọn **chain opaque**.
- `@Order` quyết định chain nào được xét trước.
- `.requestMatchers(...)` trong mỗi chain quyết định rule HTTP sau khi chain đã được chọn.
- `anyRequest().denyAll()` trong một chain chỉ có hiệu lực với request **đã khớp chain ấy**.
- Fallback chain bảo vệ URL không nằm trong hai namespace trên.

Nếu một chain tổng quát được đặt trước chain đặc hiệu, nó có thể che chain JWT/opaque. Nếu không có fallback, những URL không khớp bất kỳ chain nào có thể không đi qua Spring Security filters.

### 6.3. URL chỉ chọn *validator*, không cấp quyền

Caller có thể chuyển JWT từ `/api/jwt/orders` sang `/api/legacy/orders`. Khi đó:

- Opaque introspector sẽ quyết định token có active theo contract hay không.
- Không được tự cho phép request chỉ vì route là `/api/legacy/**`.
- Nếu introspection endpoint có thể xác nhận JWT, kết quả có thể được chấp nhận **nếu** AS/Resource Server policy cho phép JWT đi qua route đó; nếu contract đòi tách cứng, cần kiểm tra thêm token type/issuer.
- Scope/tenant/ownership vẫn phải được kiểm tra sau authentication.

**Path là đầu vào định tuyến, không phải security proof.** Nếu tổ chức cần đảm bảo JWT chỉ dùng ở route JWT và opaque chỉ ở route legacy, phải kiểm thử hành vi của các AS/validators, không chỉ tin tên path.

### 6.4. Khi nào giải pháp hai chains không phù hợp?

Nếu cùng một endpoint `/api/orders` phải nhận cả JWT và opaque, không thể dùng hai chains có cùng `securityMatcher("/api/orders/**")` để Spring Security tự thử lần lượt: **chỉ chain đầu tiên khớp được chọn** trong cơ chế filter chain. Cần chuyển sang resolver hoặc chỉ dùng introspection chung.

## 7. Tạo JwtDecoder bảo đảm issuer và audience

Khi tự tạo decoder cho JWT route, phải kiểm tra rõ **JWT được phát cho đúng Resource Server**.

### 7.1. Bean JWT decoder với JWK Set đã tin

~~~java
package com.example.orders.security;

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
public class JwtValidationConfig {

    @Bean
    JwtDecoder jwtDecoder(
            @Value("${app.security.jwt.issuer}") String issuer,
            @Value("${app.security.jwt.jwk-set-uri}") String jwkSetUri,
            @Value("${app.security.jwt.audience}") String audience) {

        NimbusJwtDecoder decoder = NimbusJwtDecoder
            .withJwkSetUri(jwkSetUri)
            .jwsAlgorithm(SignatureAlgorithm.RS256)
            .build();

        OAuth2TokenValidator<Jwt> audienceValidator = jwt ->
            jwt.getAudience().contains(audience)
                ? OAuth2TokenValidatorResult.success()
                : OAuth2TokenValidatorResult.failure(
                    new OAuth2Error(
                        "invalid_token",
                        "Required audience is missing",
                        null
                    )
                );

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                JwtValidators.createDefaultWithIssuer(issuer),
                audienceValidator
            )
        );

        return decoder;
    }
}
~~~

Trong ví dụ:

- `jwkSetUri` do server cấu hình, không lấy từ JWT header `jku` hay request.
- `jwsAlgorithm(RS256)` giới hạn thuật toán theo hợp đồng AS giả định. Không tùy ý chấp nhận nhiều thuật toán.
- `JwtValidators.createDefaultWithIssuer(...)` áp dụng issuer/time validators phù hợp.
- Audience validator từ chối JWT không có `orders-api` trong claim `aud`.
- JWT vẫn phải là access token đúng profile; nếu ứng dụng yêu cầu `typ=at+jwt` hoặc validator RFC 9068, cần tích hợp thêm theo phiên bản.

Nếu khai báo custom `JwtDecoder` bean, Spring Boot có thể **back off** khỏi decoder tự động. Đừng giả định mọi property `spring.security.oauth2.resourceserver.jwt.*` vẫn được áp vào bean custom, đặc biệt validators do chính bạn cần quản lý.

### 7.2. Vì sao `aud` vẫn quan trọng nếu chữ ký đúng?

Authorization Server có thể phát access token cho nhiều API:

~~~text
aud = orders-api
aud = billing-api
aud = frontend-client
```

Một token có chữ ký đúng và `iss` đúng vẫn có thể **không dành cho API hiện tại**. Nếu không kiểm tra audience/resource, token dành cho Billing API hoặc ID token dùng đăng nhập có thể bị dùng nhầm ở Orders API.

**Đúng issuer + đúng chữ ký không tự đồng nghĩa đúng audience.**

## 8. Tạo OpaqueTokenIntrospector và ràng buộc resource

Opaque token được xác minh bằng cách hỏi AS:

~~~http
POST /oauth2/introspect HTTP/1.1
Host: auth-legacy.example.com
Content-Type: application/x-www-form-urlencoded
Authorization: Basic <resource-server-client-credentials>

token=<opaque-token>
~~~

RFC 7662 quy định introspection request/response; client authentication có thể thay đổi theo cấu hình AS. `Basic` chỉ là ví dụ thông dụng, không phải lựa chọn bắt buộc của mọi hệ thống.

### 8.1. Bean dùng introspector chuẩn

~~~java
package com.example.orders.security;

import java.util.Collection;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.introspection.BadOpaqueTokenException;
import org.springframework.security.oauth2.server.resource.introspection.OpaqueTokenIntrospector;
import org.springframework.security.oauth2.server.resource.introspection.SpringOpaqueTokenIntrospector;

@Configuration
public class OpaqueValidationConfig {

    @Bean
    OpaqueTokenIntrospector opaqueTokenIntrospector(
            @Value("${app.security.opaque.introspection-uri}") String uri,
            @Value("${app.security.opaque.client-id}") String clientId,
            @Value("${app.security.opaque.client-secret}") String clientSecret,
            @Value("${app.security.opaque.audience}") String audience) {

        OpaqueTokenIntrospector delegate =
            SpringOpaqueTokenIntrospector.withIntrospectionUri(uri)
                .clientId(clientId)
                .clientSecret(clientSecret)
                .build();

        return token -> {
            // Inactive/invalid token phải bị delegate từ chối.
            OAuth2AuthenticatedPrincipal verified =
                delegate.introspect(token);

            Object rawAudience = verified.getAttribute("aud");

            boolean forThisApi =
                rawAudience instanceof String value
                    && value.equals(audience);

            if (rawAudience instanceof Collection<?> values) {
                forThisApi = values.contains(audience);
            }

            if (!forThisApi) {
                throw new BadOpaqueTokenException(
                    "Token is not intended for this API"
                );
            }

            return verified;
        };
    }
}
~~~

**Giả định cụ thể của ví dụ:** introspection endpoint **có trả `aud`** dạng string hoặc collection và tổ chức yêu cầu audience chính xác. RFC 7662 không bắt buộc response chứa mọi attribute. Nếu AS không trả `aud`, phương án này sẽ fail closed và không chấp nhận token opaque; cần sửa hợp đồng với AS hoặc thiết lập resource binding tương đương tại introspection service **có thẩm quyền**.

**Không sửa response** bằng cách thêm `aud=orders-api` khi thiếu chỉ để tránh lỗi. Điều đó làm mất bảo vệ chống token dùng sai API.

### 8.2. `active=true` là điều kiện cần, chưa luôn đủ

Với introspection response:

~~~json
{
  "active": true,
  "scope": "orders.read",
  "client_id": "legacy-client",
  "aud": ["orders-api"]
}
~~~

API còn cần biết:

- Introspection endpoint này có được tin và cấu hình đúng AS?
- AS có xác nhận token thuộc đúng resource/audience?
- Token type, client credentials và issuer context có phù hợp?
- Scope `orders.read` có được AS cấp thực sự?
- Quyền trên tenant/order cụ thể đã được service kiểm tra chưa?

`active=true` không phải giấy phép truy cập mọi tài nguyên.

### 8.3. Opaque introspection khác giải mã JWT cục bộ

Có AS vẫn hỗ trợ **introspect JWT access token**. Khi Resource Server gọi introspection và AS trả `active=true`, đó là một **luồng xác thực bằng introspection**; API không nhất thiết chạy local JWS verification nếu đã chọn tin introspection endpoint theo policy. Đây là một kiến trúc hợp lệ nhưng trust, latency và availability khác local JWT verification.

## 9. Phương án B — AuthenticationManagerResolver trong một chain

Nếu quyết định JWT hay opaque phải được đưa ra **tại request-time** trong cùng một security chain, Spring Security documentation khuyến nghị `AuthenticationManagerResolver<HttpServletRequest>`.

### 9.1. Hai managers độc lập

~~~java
AuthenticationManager jwtManager =
    new ProviderManager(new JwtAuthenticationProvider(jwtDecoder));

AuthenticationManager opaqueManager =
    new ProviderManager(
        new OpaqueTokenAuthenticationProvider(opaqueTokenIntrospector)
    );
~~~

- `jwtManager` chỉ được dùng để **verify JWT** bằng decoder đã cấu hình.
- `opaqueManager` chỉ được dùng để **introspect token** qua service đã cấu hình.
- Cả hai có thể nhận `BearerTokenAuthenticationToken` như input chưa được xác thực.
- Thành công sẽ tạo những kiểu `Authentication` khác nhau, nhưng authorization có thể kiểm tra `GrantedAuthority` chung.

Không được biến hai providers thành cơ chế “JWT thất bại thì thử opaque” nếu policy không cho phép fallback: cách đó có thể mở ra một đường **downgrade authentication**.

### 9.2. Ví dụ resolver định tuyến theo path

Giả sử một chain bảo vệ `/api/**`, nhưng có hai nhóm route với contract rõ:

~~~text
/api/v2/**      -> JWT
/api/legacy/**  -> opaque
other /api/**   -> reject
```

Resolver:

~~~java
package com.example.orders.security;

import jakarta.servlet.http.HttpServletRequest;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.AuthenticationManagerResolver;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationProvider;
import org.springframework.security.oauth2.server.resource.authentication.OpaqueTokenAuthenticationProvider;
import org.springframework.security.oauth2.server.resource.introspection.OpaqueTokenIntrospector;

@Configuration
public class TokenManagerResolverConfig {

    @Bean
    AuthenticationManagerResolver<HttpServletRequest>
            tokenAuthenticationManagerResolver(
                JwtDecoder jwtDecoder,
                OpaqueTokenIntrospector introspector) {

        AuthenticationManager jwtManager = new ProviderManager(
            new JwtAuthenticationProvider(jwtDecoder)
        );

        AuthenticationManager opaqueManager = new ProviderManager(
            new OpaqueTokenAuthenticationProvider(introspector)
        );

        AuthenticationManager reject = authentication -> {
            throw new BadCredentialsException(
                "Unsupported token route"
            );
        };

        return request -> {
            String path = request.getRequestURI();
            String contextPath = request.getContextPath();

            if (!contextPath.isEmpty()
                    && path.startsWith(contextPath)) {
                path = path.substring(contextPath.length());
            }

            if (path.equals("/api/v2")
                    || path.startsWith("/api/v2/")) {
                return jwtManager;
            }

            if (path.equals("/api/legacy")
                    || path.startsWith("/api/legacy/")) {
                return opaqueManager;
            }

            return reject;
        };
    }
}
~~~

Mã ví dụ dùng path chỉ để **chọn manager**. Trong production, URI có thể chịu servlet path, forwarding và reverse-proxy rewriting; nếu path matching phức tạp, hãy dùng matcher theo Spring Security request matching contract và kiểm thử alignment với controller mappings, thay vì viết chuỗi `startsWith(...)` rải rác.

**Quan trọng:** `reject` vẫn là `AuthenticationManager` thực hiện fail closed; không trả `Authentication` giả có `authenticated=true`.

### 9.3. Đưa resolver vào SecurityFilterChain

~~~java
package com.example.orders.security;

import jakarta.servlet.http.HttpServletRequest;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.authentication.AuthenticationManagerResolver;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class MixedApiSecurityConfig {

    @Bean
    SecurityFilterChain mixedApiChain(
            HttpSecurity http,
            AuthenticationManagerResolver<HttpServletRequest> resolver)
            throws Exception {

        return http
            .securityMatcher("/api/**")
            .csrf(AbstractHttpConfigurer::disable)
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(
                    HttpMethod.GET, "/api/v2/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(
                    HttpMethod.POST, "/api/v2/orders/**")
                    .hasAuthority("SCOPE_orders.write")

                .requestMatchers(
                    HttpMethod.GET, "/api/legacy/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(
                    HttpMethod.POST, "/api/legacy/orders/**")
                    .hasAuthority("SCOPE_orders.write")

                .anyRequest().denyAll())
            .oauth2ResourceServer(oauth2 -> oauth2
                .authenticationManagerResolver(resolver))
            .build();
    }
}
~~~

Ví dụ này là **phương án thay thế** cho cấu hình hai chains ở phần 6. Trong một ứng dụng, không khai báo hai giải pháp đồng thời với các chain matchers chồng nhau mà không xác định chính xác thứ tự và ownership.

### 9.4. Tại sao mã này không gọi `.jwt()` hoặc `.opaqueToken()`?

Vì **resolver đã chọn authentication manager**, nên DSL cần:

~~~java
.oauth2ResourceServer(oauth2 -> oauth2
    .authenticationManagerResolver(resolver))
~~~

Không cần thêm:

~~~java
.jwt(...)
.opaqueToken(...)
~~~

vào cùng configurer; cấu hình đó vi phạm hợp đồng mutual exclusivity của Spring Security.

### 9.5. Resolver được gọi với request chưa authenticated

`AuthenticationManagerResolver.resolve(request)` nhận `HttpServletRequest` **trước khi JWT hoặc opaque token được xác thực**. Do vậy, bất kỳ path/header/token string nào đọc từ request chỉ là **input để chọn manager**, không phải nguồn role/permission.

Nếu route `/api/v2/**` được chọn, chỉ `JwtAuthenticationProvider` thành công sau khi JWT verify đầy đủ mới được cấp quyền.

## 10. Một URL duy nhất nhận cả JWT và opaque token: phải chọn tiêu chí rõ

Trường hợp khó hơn:

~~~text
GET /api/orders
Authorization: Bearer <JWT hoặc opaque token>
```

Không có `/jwt` hay `/legacy` trong path để phân biệt.

Một số lựa chọn:

1. **Ưu tiên introspection cho cả hai** nếu AS hỗ trợ và chính sách cho phép.
2. Dùng **quy ước token namespace** do AS cam kết, ví dụ opaque token luôn bắt đầu bằng tiền tố xác định, còn JWT là compact JWS hợp lệ về hình dạng.
3. Dùng một **trusted gateway** xác minh token và truyền identity theo kênh nội bộ được xác thực, khi kiến trúc và trust model phù hợp.
4. Thay đổi API contract để client dùng route/host khác nhau cho từng loại token.
5. Với nhiều issuers, dùng routing contract và trusted issuer registry phù hợp; không dùng unverified issuer URL để tự phát discovery.

**Không có quy tắc phổ quát nào rằng “JWT chứa hai dấu chấm, opaque thì không”**: opaque token về bản chất có thể là chuỗi tùy ý.

### 10.1. Ví dụ phân loại theo format contract đã được AS phê duyệt

Giả sử **trong hệ thống này**:

- AS cũ phát opaque token có tiền tố `ref_`.
- AS mới phát JWT compact JWS ba đoạn Base64URL.
- Token khác hai định dạng trên đều bị từ chối.
- AS cam kết opaque token **không có** hình dạng JWS ba phần và JWT **không** bắt đầu `ref_`.

Đây là một hợp đồng **riêng của hệ thống**, không phải quy định RFC.

~~~java
package com.example.orders.security;

import java.util.regex.Pattern;

import jakarta.servlet.http.HttpServletRequest;

import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.AuthenticationManagerResolver;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.web.authentication.preauth.PreAuthenticatedAuthenticationToken;
import org.springframework.security.oauth2.server.resource.web.DefaultBearerTokenResolver;

public final class TokenFormatAuthenticationManagerResolver
        implements AuthenticationManagerResolver<HttpServletRequest> {

    private static final Pattern COMPACT_JWS =
        Pattern.compile(
            "[A-Za-z0-9_-]+\\.[A-Za-z0-9_-]+\\.[A-Za-z0-9_-]+"
        );

    private final DefaultBearerTokenResolver tokenResolver =
        new DefaultBearerTokenResolver();

    private final AuthenticationManager jwt;
    private final AuthenticationManager opaque;

    private final AuthenticationManager reject = authentication -> {
        throw new BadCredentialsException(
            "Unsupported bearer token format"
        );
    };

    public TokenFormatAuthenticationManagerResolver(
            AuthenticationManager jwt,
            AuthenticationManager opaque) {

        this.jwt = jwt;
        this.opaque = opaque;
    }

    @Override
    public AuthenticationManager resolve(HttpServletRequest request) {
        String token = tokenResolver.resolve(request);

        if (token == null) {
            return reject;
        }

        if (token.startsWith("ref_")) {
            return opaque;
        }

        if (COMPACT_JWS.matcher(token).matches()) {
            return jwt;
        }

        return reject;
    }
}
~~~

Lớp này chỉ **chọn manager**. Nó không phân tích payload để lấy `sub`, không tin `alg`/`kid`, không ghi token vào log. Có thể xóa import `PreAuthenticatedAuthenticationToken` vì nó không cần cho giải pháp. Khi tích hợp, tạo hai managers như phần 9.1 và truyền vào constructor, rồi gắn resolver vào `.authenticationManagerResolver(...)`.

**Điều kiện bảo mật quan trọng:** cả hai managers vẫn phải xác minh token độc lập; token dạng ba phần nhưng chữ ký sai phải bị JWT decoder từ chối, **không** được tự động rơi sang opaque introspection. Token `ref_` phải bị introspector từ chối khi inactive. Nếu đối phương tự đặt prefix `ref_`, đó chỉ khiến yêu cầu đi qua opaque manager; không thể tạo `active=true` từ không khí.

### 10.2. Hạn chế của format-based routing

- `COMPACT_JWS` là **kiểm tra cú pháp rất thô**, không phải JWT parser hay validator.
- Opaque token có ba phần sẽ bị phân loại sang JWT, có thể bị từ chối dù AS biết nó.
- JWT có cấu trúc JWE năm phần sẽ không được chấp nhận bởi classifier này.
- AS thay đổi format nhưng API không cập nhật sẽ gây lỗi.
- Cần giới hạn kích thước bearer token và log redaction để giảm abuse.
- Không cho phép query param/header phụ tự chọn “bypass validation” mà không có hợp đồng.
- Mỗi route/issuer có thể cần chính sách audience, token type và authority riêng.

Vì các hạn chế trên, format-based routing chỉ phù hợp khi **AS bảo đảm namespace/format không nhập nhằng** và có integration tests. Nếu token format chưa có contract rõ, **ưu tiên introspection chung hoặc routing theo API namespace**.

### 10.3. Không dùng issuer chưa verify để auto-register AS

Một JWT có:

~~~json
{
  "iss": "https://attacker.example/oidc"
}
~~~

không được khiến Resource Server tự tạo:

~~~java
JwtDecoders.fromIssuerLocation(untrustedIssuer)
~~~

rồi chấp nhận token tự ký của attacker. Nếu multi-issuer JWT được hỗ trợ, phải có **trusted issuer allowlist**; sau đó mới chọn manager/decoder cho issuer phù hợp và verify chữ ký/claims.

## 11. Vì sao không thử JWT rồi fallback opaque khi lỗi?

Một cách làm có vẻ thuận tiện:

~~~text
1. Thử JwtDecoder.decode(token)
2. Nếu ném bất kỳ exception nào
3. Tự động gọi introspection
4. Nếu introspection trả active=true thì accept
```

Nhìn qua, phương án này có thể cho JWT lỗi cú pháp hoặc opaque token đi qua introspection, nhưng nó **gộp nhiều loại lỗi có ngữ nghĩa bảo mật khác nhau**:

- JWT từ issuer chưa được trust.
- JWT signature sai.
- JWT hết hạn.
- JWT audience sai.
- JWT đúng nhưng không đạt token profile.
- JWKS server đang outage.
- Token thực sự opaque, không phải JWT.

Một invalid JWT có thể vô tình được một introspection endpoint khác chấp nhận theo contract lỏng hơn. Một failure mạng ở decoder có thể khiến hệ thống đổi sang cơ chế khác, làm khó kiểm toán và tạo **downgrade path**.

### 11.1. ProviderManager có hai providers cũng không tự giải quyết

Ví dụ:

~~~java
new ProviderManager(
    new JwtAuthenticationProvider(jwtDecoder),
    new OpaqueTokenAuthenticationProvider(introspector)
)
~~~

không phải phương pháp an toàn mặc định để diễn đạt “nếu JWT thì JWT provider, nếu opaque thì opaque provider”. Cả hai providers đều có thể hỗ trợ `BearerTokenAuthenticationToken`, và thứ tự/cách xử lý authentication exceptions trong `ProviderManager` có thể dẫn tới hành vi thử provider tiếp theo không phản ánh chính sách token format.

**Ưu tiên một resolver chọn manager rõ ràng** hoặc một introspection source chung. Nếu có chủ đích cho phép fallback theo trường hợp rất cụ thể, cần threat model, exception taxonomy và test chứng minh không thể chuyển JWT invalid sang đường xác thực yếu hơn.

### 11.2. Fallback “vì availability” là nguy hiểm

Không được làm:

~~~java
try {
    return jwtDecoder.decode(token);
} catch (Exception e) {
    return trustClaimsWithoutSignature(token);
}
~~~

Nếu JWKS đang lỗi, câu trả lời đúng là **không thể xác minh token mới cần khóa**, không phải cấp principal/authorities không có căn cứ.

## 12. Phương án C — Introspection cho cả JWT và opaque token

Một opaque token Resource Server thực chất là **Resource Server dùng introspection**, không phải component bắt buộc chỉ nhận những chuỗi không có dấu chấm.

Nếu AS cho phép introspect **cả JWT access tokens và opaque access tokens**, có thể cấu hình:

~~~java
.oauth2ResourceServer(oauth2 -> oauth2
    .opaqueToken(opaque -> opaque
        .introspector(trustedIntrospector)))
~~~

Cả hai token được gửi tới endpoint introspection **đáng tin**, AS quyết định chúng có `active=true` theo resource binding và token status hay không.

### 12.1. Ưu điểm

- Không cần phân loại theo token shape.
- Có thể nhận kết quả status/revocation từ AS.
- Cùng một contract authorities (đặc biệt scope).
- Có thể giảm logic đa nhánh ở Resource Server.
- Dễ áp policy “AS là nguồn trạng thái token hiện tại”.

### 12.2. Đánh đổi

- Network latency/availability của introspection endpoint trở thành dependency của requests.
- Cần client authentication, TLS, timeout, rate limiting và retry policy có giới hạn.
- AS có thể không hỗ trợ introspect JWT hoặc không công bố đủ claims.
- Cần kiểm tra `aud`, issuer, client type và token purpose theo AS contract.
- Cache introspection có thể làm chậm việc thu hồi token/role.
- Nếu nhiều issuers, **một introspection endpoint** chưa chắc biết token từ tất cả AS.

### 12.3. Khi nào không chọn introspection chung?

Nếu AS A chỉ cấp JWT và không introspect JWT, còn AS B cấp opaque token ở endpoint khác, một introspector chung không thể tự xác minh cả hai. Khi đó dùng **resolver với hai managers** hoặc phân route; đừng cho một AS xác nhận token của AS khác nếu không có trust federation được thiết kế rõ.

## 13. JWT branch: issuer, keys, algorithms và type

Với JWT branch, tối thiểu cần biết:

| Kiểm tra | Mục đích |
|---|---|
| Trusted `issuer-uri` | Nguồn phát hành được API cho phép |
| Trusted JWKS URL | Nguồn public keys của issuer |
| Allowed `alg` | Giới hạn JWS algorithms/key type |
| Signature | Chứng minh token do key đáng tin ký |
| `iss` | Token sau xác minh có đúng issuer không |
| `aud` | Token được phát cho Resource Server này không |
| `exp`/`nbf` | Token còn hợp lệ trong time window không |
| `typ`/profile | Đây có đúng OAuth access-token JWT không |
| `scope`/`scp` | Quyền được cấp theo AS contract |

**JWT header chưa được xác minh** có thể chứa `kid`, `jku`, `x5u` và `alg`; không dùng một URL từ header để tự fetch public key từ host chưa được trust. `kid` chỉ nên chọn khóa trong trusted key source.

### 13.1. Multi-issuer JWT

Nếu JWT tokens từ nhiều issuers được chấp nhận, dùng `JwtIssuerAuthenticationManagerResolver.fromTrustedIssuers(...)` hoặc một repository managers chỉ chứa issuers được phê duyệt.

Không truyền `iss` chưa verify vào `JwtDecoders.fromIssuerLocation(...)` cho mọi URL trên Internet. Điều đó vừa mở trust quá rộng, vừa có thể tạo SSRF.

### 13.2. Chứng thực resource binding

Một token A có chữ ký đúng nhưng `aud=["billing-api"]` phải không tự được chấp nhận bởi `orders-api`. Chứng thực đúng AS không đủ nếu intended resource sai.

Không dùng ID token của OIDC Client làm bearer access token chỉ vì cả hai đều là JWT.

## 14. Opaque branch: introspection trust và token status

RFC 7662 introspection cho phép AS trả:

~~~json
{
  "active": true,
  "sub": "user-42",
  "client_id": "legacy-orders-client",
  "scope": "orders.read",
  "aud": ["orders-api"]
}
~~~

Resource Server cần:

1. Gọi **đúng endpoint** từ server configuration, không từ token/header.
2. Xác thực **resource-server client** tới AS.
3. Sử dụng HTTPS/TLS và policy timeout rõ.
4. Từ chối `active=false` hoặc malformed response.
5. Không tự đặt `active=true` khi introspection service lỗi.
6. Kiểm tra audience/resource binding theo AS contract.
7. Không biến arbitrary introspection attributes thành admin role.
8. Không lưu/ghi raw bearer token ra logs hoặc metrics.

### 14.1. Introspection result có thể khác JWT claims

Một opaque response có thể không có `iss` hoặc có định dạng scopes/roles khác JWT. Vì vậy API phải định nghĩa **identity namespace** của opaque AS bằng source trusted configuration.

Không tự suy ra một opaque principal không có `iss` chính là user của JWT issuer chỉ vì `sub` trùng.

### 14.2. Client credentials token

Với `client_credentials`, token có thể đại diện một workload chứ không phải người dùng. Không mặc định mọi `client_id` hoặc `sub` là một user có quyền sở hữu order.

API cần policy riêng cho machine identities, allowed scopes, tenant binding và audit.

## 15. Thống nhất authorities giữa JWT và opaque token

Một API có hai authentication flows cần cách hiểu authority **nhất quán**, nếu không cùng endpoint có thể cho phép hai tập quyền khác nhau ngoài chủ đích.

Giả sử JWT:

~~~json
{
  "scope": "orders.read orders.write"
}
~~~

và opaque introspection:

~~~json
{
  "active": true,
  "scope": "orders.read orders.write"
}
~~~

Theo conventions mặc định, Spring Security thường tạo:

~~~text
SCOPE_orders.read
SCOPE_orders.write
~~~

Trong cả hai đường, authorization rule có thể dùng:

~~~java
.hasAuthority("SCOPE_orders.read")
~~~

### 15.1. Không phải mọi role claim đều được tự ánh xạ

JWT có thể chứa:

~~~json
{
  "scope": "orders.read",
  "roles": ["orders_manager"]
}
~~~

Opaque introspection có thể chứa:

~~~json
{
  "active": true,
  "scope": "orders.read",
  "permissions": ["orders.export"]
}
~~~

`roles` và `permissions` ở đây là **custom claims**, không có một mapping universal giữa mọi AS.

| Input sau xác minh | Authority có thể tạo | Điều kiện |
|---|---|---|
| JWT `scope=orders.read` | `SCOPE_orders.read` | Scope thật sự được AS cấp |
| Introspection `scope=orders.read` | `SCOPE_orders.read` | Token active, AS cấp scope |
| JWT `roles=orders_manager` | `ROLE_ORDERS_MANAGER` | AS có thẩm quyền cấp role này cho API |
| Introspection `permissions=orders.export` | `PERM_ORDERS_EXPORT` | Custom mapping được phê duyệt |
| Email kết thúc `@company.example` | Không tự tạo admin | Email không phải entitlement |
| `username=admin-support` | Không tự tạo admin | Username không phải entitlement |
| Thiếu role | Không tự tạo role | Không thêm quyền để che lỗi 403 |
| Unknown role | Không tạo authority | Allowlist mapping |

### 15.2. Prefix khác nhau, ngữ nghĩa khác nhau

`SCOPE_orders.read` không phải `ROLE_ORDERS_READER`; `hasRole("ORDERS_READER")` thường kiểm tra `ROLE_ORDERS_READER`. Quy ước `PERM_*` là của ứng dụng, không phải tiêu chuẩn Spring Security.

Nếu một AS gọi `read:orders` và AS kia gọi `orders.read`, chỉ map chúng thành cùng authority khi contract chứng minh **phạm vi tài nguyên, hành động và tenant constraints tương đương**.

## 16. Principal có kiểu khác nhau sau authentication

Sau khi JWT branch thành công, thường có:

~~~java
JwtAuthenticationToken
    |
    +-- getToken() -> Jwt
    +-- getAuthorities() -> GrantedAuthority collection
    +-- getName() -> thường từ sub theo converter
~~~

Sau khi opaque branch thành công, thường có:

~~~java
BearerTokenAuthentication
    |
    +-- getPrincipal() -> OAuth2AuthenticatedPrincipal
    +-- getTokenAttributes() -> introspected attributes
    +-- getAuthorities() -> GrantedAuthority collection
~~~

Một controller viết:

~~~java
@GetMapping("/api/me")
Map<String, Object> me(@AuthenticationPrincipal Jwt jwt) {
    return Map.of("sub", jwt.getSubject());
}
~~~

có thể chỉ phù hợp **JWT branch**. Khi opaque token đi qua, principal không mặc định là `Jwt`, nên injection/cast có thể không phù hợp.

### 16.1. Dùng Authentication abstraction chung

Nếu endpoint dùng cả hai token types, có thể nhận:

~~~java
@GetMapping("/api/me")
Map<String, Object> me(Authentication authentication) {
    return Map.of(
        "name", authentication.getName(),
        "authenticated", authentication.isAuthenticated()
    );
}
~~~

`getName()` không mặc định là cùng một namespace giữa issuers. API thực tế cần identity mapping ở service.

### 16.2. Domain CallerIdentity với nguồn rõ

Một application-level model có thể là:

~~~java
public record CallerIdentity(
    String identitySource,
    String subject,
    String clientId,
    boolean servicePrincipal
) {}
~~~

Đây là **record do ứng dụng tự định nghĩa**, không phải Spring Security API.

- JWT branch: `identitySource` thường là **trusted `iss` đã được verify**.
- Opaque branch: `identitySource` có thể là **trusted introspection authority identifier** từ cấu hình, hoặc `iss` được AS trả theo contract.
- `subject` phải đến từ principal đã authenticated.
- `clientId` phục vụ OAuth client identity, không tự thay human subject.
- `servicePrincipal` phải dựa trên token purpose/contract có thẩm quyền, không phải request header tự khai.

**Đừng đồng nhất hai `sub=user-42` của hai AS chỉ vì cùng chuỗi.** Khi gắn ownership, nên dùng `(identitySource, subject)` hoặc ánh xạ sang internal user ID qua directory đáng tin.

### 16.3. Không copy mọi introspection attribute ra response

Một `/api/me` có thể trả name/display name cần thiết; không đưa toàn bộ JWT/opaque attributes, raw token, client secret hoặc quyền nội bộ vào JSON public.

## 17. Tenant-aware routing: hai câu hỏi cần tách

Trong hệ thống nhiều tenant, có hai câu hỏi độc lập:

**Câu hỏi xác thực:** token đã được AS hợp lệ phát hành cho API chưa?

**Câu hỏi phân quyền:** principal đó có quyền đối với tenant và object đang được yêu cầu không?

~~~text
GET /api/tenants/tenant-a/orders/order-99
Authorization: Bearer <token>
                   |
                   v
JWT / opaque verification
                   |
                   v
Known principal + authorities
                   |
                   v
Check membership tenant-a
                   |
                   v
Check order-99 really belongs to tenant-a
                   |
                   v
Check owner/ACL/state
                   |
                   v
Return data only if authorized
~~~

Đường dẫn `tenant-a`, HTTP host, `X-Tenant-Id` hoặc parameter `tenantId` là **target do client chọn**, không chứng minh membership.

### 17.1. Một issuer có thể phát cho nhiều tenants

Nếu một AS phát JWT cho toàn doanh nghiệp với claim `tenant_id`, resolver theo issuer **không tự kiểm tra** quyền tenant. Phải xác minh `tenant_id` semantics và dùng membership/ACL.

### 17.2. Một tenant có thể dùng nhiều issuers

Tenant A có thể cho phép human users từ OIDC issuer X và workloads từ AS Y. Token từ X và Y có principal namespaces khác nhau; cần policy mapping có kiểm soát.

### 17.3. Route selection không thay issuer/audience validation

Một opaque token gửi tới `/api/legacy/**` chưa chắc thuộc tenant legacy nếu introspection service kiểm tra lỏng. Tương tự, JWT gửi tới `/api/v2/**` phải verify issuer, audience và token profile thật.

## 18. Vòng đời token, revocation và migration

Hỗ trợ hai loại token thường xuất hiện khi migration:

~~~text
T0  Clients cũ -> opaque tokens
T1  Clients mới -> JWT
T2  Resource Server hỗ trợ cả hai
T3  Ngừng cấp opaque token mới
T4  Chờ token opaque cũ hết hạn hoặc revoke
T5  Gỡ opaque support sau khi kiểm tra telemetry
```

Một lộ trình đúng cần:

- Danh sách clients/issuers được phép dùng từng loại token.
- Audience/resource binding của cả hai.
- Permission mapping tương đương hoặc khác nhau có chủ đích.
- Thời hạn token, refresh token policies và revocation.
- Số lượng token opaque còn hợp lệ theo telemetry.
- Khoảng thời gian quay lại cơ chế cũ được kiểm soát.
- Security test bảo đảm không có JWT invalid fallback sang opaque.
- Kế hoạch tắt introspection credentials và endpoint routing khi migration hoàn tất.

### 18.1. JWT revocation không giống opaque revocation

JWT local verification có thể chấp nhận token tới `exp` dù user vừa bị thu hồi phiên/role, nếu không có denylist/security-version check hay cơ chế tương đương.

Opaque introspection có thể phản ánh `active=false` sớm hơn nếu AS cập nhật trạng thái và cache cho phép. Nhưng không mặc định mọi AS luôn trả quyền mới nhất; nó có thể cache introspection/entitlements.

**Đừng chọn opaque branch chỉ vì “token nhìn khó đọc hơn”.** Hãy chọn dựa trên revocation, trust, latency và operational requirements.

## 19. Latency và dependency mạng của hai đường

Một lượt request JWT:

~~~text
JWT -> check signature locally
         |
         +-- JWK key có sẵn -> không cần network call
         +-- cần key/refresh -> fetch trusted JWKS
```

Một lượt opaque:

~~~text
Opaque -> HTTP introspection
              |
              +-- endpoint online -> active, attributes
              +-- endpoint timeout -> authentication cannot be proven
```

Điều này tác động tới:

| Khía cạnh | JWT | Opaque |
|---|---|---|
| p99 latency | Thường thấp khi key warm | Phụ thuộc introspection latency/cache |
| Outage AS | Token có key cached vẫn có thể verify theo policy | Có thể gián đoạn nếu endpoint không sẵn sàng |
| Thay signing key | Cần JWKS refresh | Được AS xử lý theo introspection flow |
| Thu hồi token | Cần thiết kế revocation nếu muốn trước `exp` | AS có thể báo `active=false` |
| Scale nhiều replicas | JWKS cache per-instance/gateway | Introspection QPS tăng theo request rate |
| Secret phía Resource Server | Thường chỉ cần public keys | Có thể cần introspection client secret |
| Troubleshooting | JWS/claims/key rotation | Network/client auth/`active`/schema |

Các nhận định trên là **hướng vận hành chung**, không phải bảo đảm độ trễ/availability cho mọi deployment. JWT decoder có thể cần mạng khi thiếu key; introspection cache có thể giảm network nhưng làm stale revocation.

### 19.1. Timeout và lỗi hạ tầng

Đặt timeout cho HTTP clients tới JWKS/introspection phù hợp SLO. Không dùng timeout vô hạn và không fail open khi upstream không phản hồi.

Nếu introspection endpoint timeout, Resource Server **không** được trả `Authentication` giả chỉ để API luôn 200.

### 19.2. Cache cần tách loại

- **JWKS cache:** cache public keys, không bỏ qua JWT signature validation.
- **Introspection cache:** cache trạng thái token/attributes, có thể làm revoke chậm được áp dụng.
- **Business ACL cache:** cache quyền tenant/order, cần invalidation.
- **HTTP response cache:** không được vô tình chia sẻ private data giữa users/tenants.

Không dùng một cache key chỉ là `sub` nếu hai issuers khác nhau có `sub` trùng.

## 20. 401 và 403 trong một Resource Server hỗn hợp

Các trạng thái thường gặp:

| Tình huống | Kết quả điển hình | Lớp |
|---|---|---|
| Không gửi bearer token vào private route | 401 | Chưa authentication |
| JWT sai chữ ký | 401 | JWT authentication failure |
| JWT sai issuer/audience/expired | 401 | JWT validators |
| Opaque token `active=false` | 401 | Introspection failure |
| Opaque introspection service unavailable | Lỗi authentication/infrastructure theo handler | Không được grant |
| Token format không thuộc contract | Từ chối | Resolver/manager |
| Token hợp lệ nhưng thiếu `orders.read` | 403 | HTTP authorization |
| Token hợp lệ nhưng order thuộc tenant khác | 403/404 theo policy | Business authorization |
| Public route có bearer token invalid | Có thể 401 | Authentication filter xử lý credential sai |
| Request rơi vào `anyRequest().denyAll()` | 403 nếu đã authenticated, tùy entry point | Authorization |

**401** thường chỉ authentication chưa thành công; **403** thường chỉ principal đã xác thực nhưng bị từ chối quyền. Lỗi introspection/JWKS availability có thể được trình bày thành 5xx hoặc error khác tùy version/exception handling; không khẳng định mọi timeout đều trả 401.

### 20.1. Bearer challenge

Theo RFC 6750, response có thể mang:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
~~~

Hoặc khi scope không đủ:

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope"
~~~

Không echo raw access token, introspection client secret hay claims nhạy cảm trong response để debug.

## 21. Session, CSRF và browser client

Một Resource Server thuần bearer header có thể dùng:

~~~java
.sessionManagement(session -> session
    .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
~~~

Nó khiến Spring Security không cần dùng `HttpSession` để lấy lại authentication giữa requests. Mỗi request cung cấp token riêng.

Tuy nhiên **`STATELESS` không cấm mọi component khác tạo session** (controller, filter, login flow, CSRF repository). JWT/opaque coexistence không tự giải quyết browser CSRF/XSS/CORS.

### 21.1. CSRF phụ thuộc credential model

Nếu API chỉ chấp nhận `Authorization: Bearer ...` do client chủ động gửi, CSRF threat model thường khác ứng dụng cookie session. Có thể chọn tắt CSRF sau khi kiểm tra kiến trúc.

Nếu token/credential được browser tự gửi qua cookie, **CSRF có thể vẫn là rủi ro** dù authentication dùng JWT hoặc opaque token. Đừng tắt CSRF chỉ vì nhìn thấy `STATELESS` hoặc `oauth2ResourceServer`.

### 21.2. OIDC Login khác Resource Server

`oauth2Login()`/OIDC Authorization Code flow của **OAuth2 Client** cần state, PKCE verifier và nonce qua redirect; nó không tự biến thành một đường xác thực bearer JWT/opaque chung.

Nếu ứng dụng vừa có web UI OIDC Login vừa có Resource Server, thường nên dùng **filter chains phân phạm vi rõ** và CSRF/session policies riêng.

## 22. CORS và `Authorization` header

SPA gửi Bearer header qua cross-origin có thể phát sinh preflight `OPTIONS`:

~~~http
OPTIONS /api/orders HTTP/1.1
Origin: https://app.example.com
Access-Control-Request-Method: GET
Access-Control-Request-Headers: authorization
~~~

CORS cần được cấu hình cho browser, nhưng **CORS không phải authentication**. Thêm `Access-Control-Allow-Origin` không làm JWT/opaque token hợp lệ.

Khi debug, phân biệt:

- Preflight bị chặn bởi CORS/security.
- Bearer token không có hoặc malformed.
- JWT signature/issuer/audience failure.
- Opaque introspection timeout.
- HTTP authority bị từ chối.
- Business ACL/tenant denial.

Không mở mọi endpoint thành `permitAll()` để “sửa CORS”.

## 23. Kiểm thử phân loại token và không fallback

Một giải pháp hỗn hợp cần **test bảo mật cho cả hai nhánh và boundary chọn nhánh**.

### 23.1. Ma trận kiểm thử chính

| Request / Token | JWT branch | Opaque branch |
|---|---|---|
| JWT hợp lệ, đúng issuer/audience | Allow authentication | Chỉ allow nếu AS introspection contract có chủ đích |
| JWT signature sai | Reject | Không được coi là fallback thành công |
| JWT expired | Reject | Không được bypass expiration |
| JWT dành cho API khác | Reject | Không tự chấp nhận sai resource |
| Opaque active, đúng resource | Reject nếu không phải JWT | Allow authentication |
| Opaque inactive | Reject | Reject |
| Opaque introspection timeout | Không liên quan nếu JWT branch đã chọn | Không grant |
| Unsupported token format | Reject | Reject nếu không thuộc contract |
| JWT có scope read, gọi POST write | 403 | Không phải quyền write |
| Opaque có scope read, gọi POST write | Không phải quyền write | 403 |
| Token đúng nhưng tenant khác | Business policy reject | Business policy reject |
| Unknown issuer | Reject | Chỉ cho phép nếu trusted AS có contract |
| JWT-like opaque token | Có thể bị phân loại sai | Chỉ hỗ trợ nếu contract cho phép routing đúng |

Đừng test chỉ happy path với hai token đều hoạt động. Những **đường chuyển nhánh và lỗi âm tính** mới phát hiện privilege escalation.

### 23.2. Test bằng MockMvc với token được ký thật

Để chứng minh hai nhánh hoạt động:

1. Sinh **private/public test key pair** cho JWT.
2. Dùng fake JWKS server trả public key test, decoder thật.
3. Ký JWT test chứa `iss`, `aud`, `scope`, `exp`.
4. Dùng fake introspection server trả `active=true` cho một opaque token và `active=false` cho token khác.
5. Gửi request qua `MockMvc`/test server với header `Authorization`.
6. Đo số lần JWT JWKS endpoint và introspection endpoint được gọi.
7. Xác nhận JWT invalid **không** bị gửi sang introspection như một fallback ngoài contract.
8. Xác nhận opaque inactive không được chấp nhận ngay cả khi chuỗi có vẻ hợp lệ.
9. Kiểm tra 401/403 trên các endpoints read/write.
10. Kiểm tra invalid issuer/audience và wrong tenant.

Để test toàn bộ route selection, **đừng chỉ dùng mock authentication** rồi khẳng định resolver đã chạy.

### 23.3. MockMvc `.with(jwt())` có giới hạn gì?

Spring Security Test:

~~~java
mvc.perform(get("/api/jwt/orders")
        .with(jwt().authorities(
            new SimpleGrantedAuthority("SCOPE_orders.read"))))
    .andExpect(status().isOk());
~~~

Có thể bỏ qua `JwtDecoder` thật và gắn authentication trực tiếp. Nó hữu ích để test `hasAuthority`, **không** chứng minh chữ ký, resolver, issuer hoặc audience.

Tương tự, mock opaque token authentication cũng có thể bỏ qua network introspection.

### 23.4. Đếm calls đến introspection/JWKS server

Đối với resolver chọn JWT branch, kỳ vọng **không có introspection request** cho token JWT hợp lệ trong policy định tuyến tách cứng. Đối với opaque branch, kỳ vọng **không dựa vào JWKS** để xác nhận token opaque.

Nếu dùng introspection chung theo phương án C, việc một JWT cũng tạo introspection call là **đúng kiến trúc**, không phải lỗi. Kỳ vọng test phải theo thiết kế đã chọn.

## 24. Kiểm tra resolver độc lập bằng unit test

Không cần gọi AS thật để xác nhận resolver chọn đúng manager theo path.

Ví dụ setup khái niệm:

~~~java
AuthenticationManager jwt = authentication -> {
    throw new BadCredentialsException("JWT test manager invoked");
};

AuthenticationManager opaque = authentication -> {
    throw new BadCredentialsException("Opaque test manager invoked");
};
~~~

Có thể inject hai stub managers vào resolver, gọi `resolve(mockRequest)` cho từng URL và kiểm tra reference manager được chọn.

**Nhưng** những stub trên chỉ để xác nhận lựa chọn nhánh, hoàn toàn không xác thực token. Không đưa stub trả principal tự động vào production.

### 24.1. Những trường hợp phải có

- `/api/v2/orders` → đúng JWT manager.
- `/api/legacy/orders` → đúng opaque manager.
- `/api/v2X/orders` → không match nhầm `/api/v2/`.
- `/api/unknown` → reject.
- Context path có/không có → policy vẫn đúng.
- Forwarded path/proxy rewrite theo deployment → không chọn nhầm.
- Token không có bearer header → không có authenticated principal.
- JWT malformed → chọn JWT theo contract rồi fail.
- Opaque inactive → chọn opaque rồi fail.
- Nhiều lần request đồng thời → manager reuse an toàn.

## 25. Các anti-pattern cần tránh

### 25.1. Bật cả hai DSL trong cùng chain

~~~java
// SAI trong cùng oauth2ResourceServer configurer.
.oauth2ResourceServer(o -> o
    .jwt(Customizer.withDefaults())
    .opaqueToken(Customizer.withDefaults()))
~~~

Hãy dùng `authenticationManagerResolver` hoặc tách chains.

### 25.2. Thử cả hai providers không có phân loại

~~~java
// KHÔNG coi đây là lựa chọn JWT-vs-opaque rõ ràng.
new ProviderManager(jwtProvider, opaqueProvider);
~~~

Cần biết mỗi provider hỗ trợ input type nào và chính sách exception/fallback ra sao. Hai providers trên có thể cùng hỗ trợ bearer input, làm ngữ nghĩa “thử kiểu nào trước” khó kiểm soát.

### 25.3. Cứ token chứa hai dấu chấm là đã tin nó là JWT

~~~java
// SAI nếu dùng kết quả này làm bằng chứng token hợp lệ.
if (token.contains(".")) {
    return grantAdmin();
}
~~~

Kiểm tra format chỉ chọn manager, không cấp quyền.

### 25.4. Chấp nhận mọi introspection endpoint do request chọn

~~~text
X-Introspection-Uri: https://attacker.example/validate
```

Không dùng header này làm nguồn introspection endpoint. Phải có trusted configuration.

### 25.5. Bỏ issuer/audience validator vì JWT có chữ ký đúng

Chữ ký đúng không chứng minh intended API. Access token từ issuer/trust context khác có thể bị dùng nhầm.

### 25.6. Tự thêm quyền để hai loại token “cho kết quả giống nhau”

~~~java
// SAI nếu không có entitlement thật.
authorities.add(new SimpleGrantedAuthority("SCOPE_orders.write"));
~~~

Không thêm write chỉ vì opaque token cũ thường có quyền cao hơn; migration phải dùng AS cấp quyền hợp lệ và mapping có thẩm quyền.

### 25.7. Dựa vào `sub` trần trong multi-issuer

~~~text
JWT issuer A:    sub=user-42
Opaque issuer B: sub=user-42
```

Không tự hợp nhất hai users. Cần identity-source namespace.

### 25.8. Nhầm `JSESSIONID` với JWT/opaque coexistence

Một `HttpSession` cookie không phải bearer token. Nếu API nhận bearer header, `JSESSIONID` không nên tự thay thế authentication trừ khi app cố ý có một cơ chế session riêng.

### 25.9. Dùng access token làm log key

Không ghi nguyên raw bearer token trong debug logs, cache metrics labels hay exception messages. Nếu cần correlation, dùng một reference/digest có kiểm soát theo policy.

### 25.10. Không kiểm tra service-level ownership

`SCOPE_orders.read` từ JWT hay opaque không tự chứng minh principal đọc được mọi order. Phải kiểm tra tenant, owner, ACL và trạng thái resource.

## 26. Một checklist thiết kế bảo mật

Trước khi cho Resource Server nhận cả JWT và opaque, xác định:

- [ ] Hai loại token đến từ issuer/AS nào và thuộc môi trường nào?
- [ ] Mỗi AS được chấp nhận theo allowlist/configuration được quản trị?
- [ ] Có contract về token type/namespace hoặc route để chọn đúng manager?
- [ ] Nếu một URL chung cần hai loại, đã chọn introspection chung hoặc resolver an toàn?
- [ ] Resolver không tự tạo endpoint/JWKS URI từ untrusted token/header?
- [ ] Không có fallback từ JWT signature/audience/expiry failure sang cơ chế yếu hơn?
- [ ] JWT có signature, allowed algorithms, issuer, audience, timestamp và token profile validators?
- [ ] Opaque token được introspect thật và `active=false` bị từ chối?
- [ ] Introspection response được ràng buộc tới đúng API/resource?
- [ ] Client credentials/TLS/timeout của introspection được quản lý an toàn?
- [ ] `SCOPE_*`, `ROLE_*`, `PERM_*` có nguồn quyền được phê duyệt?
- [ ] Multi-issuer principal dùng identity namespace hoặc canonical ID đáng tin?
- [ ] Route selection không thay membership/owner/ACL ở service?
- [ ] HTTP security matcher/fallback không để URL nhạy cảm ngoài filter chain?
- [ ] Session/CSRF/CORS được cấu hình theo bearer-only hoặc cookie/browser model?
- [ ] Timeout JWKS/introspection fail closed, không tạo principal từ dữ liệu chưa xác minh?
- [ ] Cache introspection có TTL/revocation freshness phù hợp?
- [ ] Test cả JWT signature sai, opaque inactive, audience sai, scope thiếu và tenant sai?
- [ ] Test đường invalid JWT không fallback không có chủ đích?
- [ ] Có observability phân biệt JWT decode, introspection và authorization denial?
- [ ] Có kế hoạch gỡ hỗ trợ legacy sau migration và thu hồi secrets không dùng?

## 27. Chọn giải pháp theo yêu cầu

| Điều kiện thực tế | Phương án khởi đầu phù hợp |
|---|---|
| JWT và opaque dùng **URL namespace riêng** | Nhiều `SecurityFilterChain`, mỗi chain một token mechanism |
| Một chain có route-specific policy | `AuthenticationManagerResolver<HttpServletRequest>` chọn manager theo path |
| Cùng URL nhận hai loại, **AS introspect được cả hai** | Một opaque introspection flow |
| Cùng URL, AS có token namespace không nhập nhằng | Resolver theo format **chỉ để routing**, hai providers vẫn verify |
| Cùng URL, không biết token format và AS không introspect chung | Cần đổi token/API contract hoặc thiết kế trusted routing riêng; không đoán |
| Nhiều JWT issuers | `JwtIssuerAuthenticationManagerResolver` với trusted issuer list/registry |
| Nhiều opaque AS | Trusted resolver/registry chọn introspection service được duyệt |
| Cần revocation tức thời | Xem introspection/denylist/policy freshness, không chỉ JWT local |
| Chỉ JWT, không có opaque thật | Dùng `jwt()` đơn giản thay vì mixed architecture |
| Chỉ token cần introspection | Dùng `opaqueToken()` đơn giản, không cần resolver phức tạp |

Một rule quan trọng: **chọn phương án đơn giản nhất vẫn đáp ứng đúng trust, issuer/audience và revocation requirements**. Hỗ trợ hỗn hợp làm tăng diện tích cấu hình và test; không nên thêm nếu không có nhu cầu thực.

## 28. Câu hỏi tự kiểm tra

**1.** JWT và opaque token khác nhau chủ yếu ở điểm nào?

> Cách Resource Server xác minh: JWT dùng signature/claims validators và trusted JWK source; opaque thường dùng introspection endpoint đáng tin.

**2.** Trong một `oauth2ResourceServer` DSL có thể gọi `.jwt()` và `.opaqueToken()` cùng lúc để Spring tự chọn không?

> Không. Cần tách `SecurityFilterChain` hoặc cung cấp `AuthenticationManagerResolver` cho request-time selection.

**3.** `AuthenticationManagerResolver<HttpServletRequest>` chịu trách nhiệm gì?

> Chọn `AuthenticationManager` cho request. Provider/decoder/introspector được chọn mới chứng minh token hợp lệ.

**4.** Nếu hai token types có route riêng, cách đơn giản là gì?

> Hai `SecurityFilterChain` có `securityMatcher` và `@Order` rõ ràng, cùng fallback cho URL khác.

**5.** Một endpoint có thể nhận cả JWT và opaque mà không cần phân loại format khi nào?

> Khi AS introspection endpoint đáng tin chấp nhận và xác nhận cả hai loại access token theo contract.

**6.** Vì sao không tự fallback opaque khi JWT decoder báo signature sai?

> Vì có thể tạo đường downgrade authentication và che lỗi issuer/audience/signature; cần xác định token type có căn cứ.

**7.** `token.contains(".")` chứng minh JWT hợp lệ chưa?

> Chưa. Hình dạng chỉ là gợi ý; JWT phải verify chữ ký và claims đầy đủ.

**8.** Token opaque trả `active=true` có được truy cập mọi API không?

> Không. Cần resource/audience binding, authorities và business policy.

**9.** Hai branches có thể dùng cùng `SCOPE_orders.read` không?

> Có, nếu scope của từng AS có ngữ nghĩa tương đương và đã được cấp thật.

**10.** Vì sao không dùng `@AuthenticationPrincipal Jwt` cho endpoint dùng chung hai token?

> Vì opaque principal mặc định là `OAuth2AuthenticatedPrincipal`, không phải `Jwt`. Nên dùng `Authentication`/domain identity adapter.

**11.** Hai users của hai issuers có cùng `sub=user-42` có là một người không?

> Không mặc định. Phải gắn namespace issuer/trusted introspection source.

**12.** `hasAuthority("SCOPE_orders.read")` có đủ để đọc order của tenant khác không?

> Không. Cần kiểm tra tenant membership, object owner/ACL và query constraints.

**13.** Khi JWKS hoặc introspection service outage, có được tạo principal tạm để API tiếp tục không?

> Không. Nếu không chứng minh được authentication, phải fail closed hoặc xử lý lỗi hạ tầng mà không thực thi thao tác trái phép.

**14.** `MockMvc.with(jwt())` có test JWT decoder và resolver production không?

> Không mặc định. Nó mock authentication; cần test với signed token thật, decoder và fake JWKS/introspection endpoints.

**15.** Nếu `oauth2Login()` cho browser dùng session, liệu điều đó tự hỗ trợ opaque bearer token không?

> Không. OIDC Login của OAuth2 Client khác với Resource Server nhận bearer access token; phải cấu hình rõ security chains và credential flows.

## 29. Tài liệu tham khảo

- [Spring Security — Servlet OAuth 2.0 Resource Server Multi-tenancy](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/multitenancy.html): mục **Supporting both JWT and Opaque Token**, ví dụ `AuthenticationManagerResolver`, trusted issuers và dynamic managers.
- [Spring Security — OAuth2ResourceServerConfigurer API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/annotation/web/configurers/oauth2/server/resource/OAuth2ResourceServerConfigurer.html): `jwt`, `opaqueToken`, `authenticationManagerResolver` và cấu hình Bearer filter.
- [Spring Security — OAuth 2.0 Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/index.html): authentication filter và bearer flow.
- [Spring Security — Servlet Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): `JwtDecoder`, JWKS, `iss`, scope mapping.
- [Spring Security — Servlet Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html): introspection, `active`, principal, authorities.
- [Spring Security — JwtAuthenticationProvider API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/authentication/JwtAuthenticationProvider.html): JWT authentication provider.
- [Spring Security — OpaqueTokenAuthenticationProvider API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/authentication/OpaqueTokenAuthenticationProvider.html): token introspection provider.
- [Spring Security — BearerTokenAuthenticationFilter API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/web/authentication/BearerTokenAuthenticationFilter.html): bearer extraction và authentication manager resolution.
- [Spring Security — DefaultBearerTokenResolver API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/web/DefaultBearerTokenResolver.html): HTTP bearer token extraction.
- [Spring Security — ProviderManager API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authentication/ProviderManager.html): multiple AuthenticationProviders và exception handling.
- [Spring Security — Multiple SecurityFilterChain](https://docs.spring.io/spring-security/reference/servlet/configuration/java.html): `securityMatcher`, `@Order` và filter-chain fallback.
- [Spring Security — WebFlux Multi-tenancy](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/multitenancy.html): reactive tenant resolver và khác biệt API.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): HTTP bearer header và authentication errors.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): token `active`, scopes, client/resource context.
- [RFC 7519 — JSON Web Token](https://www.rfc-editor.org/rfc/rfc7519): issuer/subject/audience/time claims.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): JWT access-token profile và audience.
- [RFC 8725 — JWT Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): algorithm/token confusion, validation và key selection.

**Kết luận:** Một Resource Server **có thể hỗ trợ cả JWT và opaque bearer access token**, nhưng phải lựa chọn kiến trúc xác thực một cách **tường minh**. Nếu token types thuộc các route khác nhau, dùng nhiều `SecurityFilterChain`. Nếu phải chọn tại request-time trong cùng chain, dùng `AuthenticationManagerResolver<HttpServletRequest>` với `JwtAuthenticationProvider` và `OpaqueTokenAuthenticationProvider` được cấu hình riêng. Nếu AS introspect được cả hai, một opaque introspection flow có thể đủ. Trong mọi phương án, **định tuyến không thay xác minh**, token hợp lệ phải đúng issuer/audience/type, quyền không được suy diễn từ format hoặc profile, và tenant/ownership phải được kiểm tra ở tầng nghiệp vụ.
