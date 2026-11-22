# Tùy chỉnh HTTP client và cache theo khả năng của decoder

## 1. Từ access token đến JWKS: nơi phát sinh nhu cầu tùy chỉnh

Trong hệ thống **Spring Security OAuth 2.0 / OIDC Resource Server**, một API Spring Boot thường nhận access token dưới dạng JWT đã ký:

~~~http
GET /api/orders HTTP/1.1
Host: api.example.test
Authorization: Bearer eyJhbGciOi...
~~~

Nếu token là **JWS**, Resource Server phải xác minh chữ ký. Phần header JWT có thể mang:

~~~json
{
  "alg": "RS256",
  "kid": "shop-signing-key-2026-11",
  "typ": "at+jwt"
}
~~~

Bên phát hành (**Authorization Server**) dùng private key để ký; API lấy **public key** từ **JWK Set (JWKS)** do bên phát hành công bố. Ví dụ URI:

~~~text
https://id.example.test/realms/shop/protocol/openid-connect/certs
~~~

Đây là URL minh họa cho một Identity Provider; đường dẫn JWKS thực tế phụ thuộc provider và nên lấy từ metadata tin cậy.

Về nguyên lý, mỗi request cần vượt qua nhiều bước:

1. Tìm Bearer token trong HTTP request.
2. Xác định algorithm/key ID từ token chưa đáng tin; chỉ tra khóa trong nguồn JWKS **đã cấu hình tin cậy**.
3. Có public key thích hợp để kiểm tra chữ ký JWS.
4. Kiểm tra issuer `iss`, audience `aud`, hạn `exp`, `nbf` và các ràng buộc của profile token.
5. Ánh xạ scope/role thành authorities và phân quyền endpoint/tài nguyên.

Các vấn đề vận hành thường xảy ra ở bước 3:

- JWKS endpoint phản hồi chậm hoặc mất kết nối.
- Lượng API request cao gây truy vấn JWKS lặp.
- Authorization Server xoay vòng signing key và phát hành token với `kid` mới.
- Nhiều replica API có cache riêng, thời điểm nhận khóa mới khác nhau.
- Một issuer có JWKS lớn, nhiều issuer dùng các endpoint khác nhau.
- Yêu cầu nội bộ cần proxy, trust store, timeout hoặc caching khác mặc định.

Spring Security cung cấp extension point trong **`NimbusJwtDecoder`** để tùy chỉnh **HTTP client** và **JWK Set cache**. Tuy nhiên, thay decoder cũng ảnh hưởng đến phần auto-configuration và JWT validators; phải hiểu rõ phạm vi mà từng extension point quản lý.

> Trọng tâm bài: **tùy chỉnh cách lấy và cache khóa xác minh**, đồng thời bảo toàn đầy đủ kiểm tra JWT. Không đồng nhất cache JWKS với cache access token và không kỳ vọng HTTP/cache extension tự cung cấp toàn bộ khả năng resilience.

Bài sử dụng **Servlet Resource Server** (Spring MVC, `HttpSecurity`, `NimbusJwtDecoder`). Với WebFlux, decoder và HTTP client reactive có các API khác.

## 2. JWK, JWKS và luồng xác minh

### 2.1. JWK và JWKS

**JWK (JSON Web Key)** là một biểu diễn khóa bằng JSON. Một public RSA JWK minh họa:

~~~json
{
  "kty": "RSA",
  "use": "sig",
  "kid": "shop-signing-key-2026-11",
  "alg": "RS256",
  "n": "<PUBLIC_RSA_MODULUS_BASE64URL>",
  "e": "AQAB"
}
~~~

JWK trên chỉ mô tả public key; `n` là placeholder. Một **JWKS (JSON Web Key Set)** chứa danh sách các JWK:

~~~json
{
  "keys": [
    {
      "kty": "RSA",
      "use": "sig",
      "kid": "shop-signing-key-2026-10",
      "alg": "RS256",
      "n": "<OLD_MODULUS>",
      "e": "AQAB"
    },
    {
      "kty": "RSA",
      "use": "sig",
      "kid": "shop-signing-key-2026-11",
      "alg": "RS256",
      "n": "<NEW_MODULUS>",
      "e": "AQAB"
    }
  ]
}
~~~

Authorization Server có thể công bố cùng lúc khóa cũ và mới trong giai đoạn **key rotation**. Resource Server xác minh token cũ bằng public key cũ trong khoảng token đó còn được phép sử dụng, đồng thời có thể tiếp nhận token ký bằng khóa mới sau khi đã lấy được JWKS chứa public key mới.

Không đưa private signing key vào JWKS công khai. Resource Server xác minh JWS bằng public key, không cần private key của bên phát hành.

### 2.2. Quy trình lấy khóa qua HTTP và cache

~~~mermaid
sequenceDiagram
    participant Client as API Client
    participant API as Spring Resource Server
    participant Cache as JWK Set Cache
    participant IdP as IdP JWKS Endpoint
    Client->>API: Authorization: Bearer JWT
    API->>API: Đọc JWS alg/kid
    API->>Cache: Tìm JWK Set theo JWKS URI
    alt Có public key thích hợp
        Cache-->>API: JWK Set cache
    else Cần lấy hoặc cập nhật JWKS
        API->>IdP: HTTPS GET jwks_uri
        IdP-->>API: JWKS JSON
        API->>Cache: Lưu JWK Set
    end
    API->>API: Verify JWS và validate JWT
    API->>API: Kiểm tra authorization
    API-->>Client: HTTP response
~~~

Sơ đồ diễn giải các giai đoạn. **Không phải request nào cũng gửi HTTP GET JWKS**: hành vi thực tế phụ thuộc trạng thái cache, thuật toán và implementation Nimbus/Spring Security của phiên bản đang chạy.

Phải phân biệt:

| Thành phần | Trách nhiệm |
|---|---|
| `BearerTokenAuthenticationFilter` | Tìm token trong request và khởi động authentication |
| `NimbusJwtDecoder` | Phân tích signed JWT, chọn khóa, xác minh chữ ký và chạy validators |
| JWKS endpoint | Phân phối các public keys của issuer |
| HTTP client của decoder | Kết nối tới metadata/JWKS khi cần |
| Cache JWKS | Giữ JWK Set để giảm truy vấn khóa lặp |
| `JwtValidators` | Ràng buộc issuer, hạn và claims khác tùy cấu hình |
| `AuthorizationFilter`/method security | Dùng authorities/principal để quyết định quyền truy cập |

**`kid` không phải bằng chứng tin cậy**. Token có thể tự khai báo `kid` bất kỳ. Decoder chỉ nên chọn key trong bộ khóa từ issuer/JWKS URI do Resource Server cho phép, cùng với allowlist thuật toán ký.

## 3. Khả năng sẵn có của `NimbusJwtDecoder`

Trong Spring Security Servlet, `JwtDecoder` là interface trừu tượng. Implementation thường dùng **`NimbusJwtDecoder`**, cung cấp các builder:

~~~java
NimbusJwtDecoder.withIssuerLocation(issuer)
NimbusJwtDecoder.withJwkSetUri(jwksUri)
~~~

Các lựa chọn chính:

| API | Ý nghĩa |
|---|---|
| `withIssuerLocation(issuer)` | Khởi tạo theo issuer và metadata discovery để xác định JWKS URI |
| `withJwkSetUri(jwksUri)` | Dùng JWKS URI tin cậy được cấu hình trực tiếp |
| `restOperations(restOperations)` | Điều chỉnh HTTP transport dùng trong đường đi builder tương ứng |
| `cache(cache)` | Cấp Spring `Cache` để cache nội dung JWK Set |
| `jwsAlgorithm(...)` / `jwsAlgorithms(...)` | Giới hạn các thuật toán JWS được chấp nhận |
| `setJwtValidator(...)` | Cấu hình issuer/time/audience/contract validation |
| `setClaimSetConverter(...)` | Điều chỉnh chuyển đổi claims khi cần theo profile |

**`restOperations(...)` và `cache(...)` không phải phương thức có trên mọi `JwtDecoder`**. Chúng là khả năng của các builder/implementation cụ thể. Nếu thay `NimbusJwtDecoder` bằng decoder khác, phải kiểm tra capability riêng của implementation đó.

### 3.1. Cấu hình đơn giản có thể đủ

Nếu provider hỗ trợ discovery:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
~~~

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://id.example.test/realms/shop
~~~

Và filter chain:

~~~java
@Bean
SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
    http
        .securityMatcher("/api/**")
        .authorizeHttpRequests(auth -> auth
            .anyRequest().authenticated()
        )
        .oauth2ResourceServer(oauth2 -> oauth2
            .jwt(Customizer.withDefaults())
        );

    return http.build();
}
~~~

Imports cho ví dụ:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
~~~

Khi Spring Boot tự cấu hình decoder, nó có cơ chế lấy public keys và cache JWKS. Nếu chính sách HTTP/cache mặc định đáp ứng nhu cầu, không cần tạo `JwtDecoder` bean tùy chỉnh.

Nếu hệ thống yêu cầu audience/token type/claims riêng, cần cấu hình chúng theo hợp đồng: chỉ có `issuer-uri` chưa đủ cho mọi profile JWT access token.

## 4. Timeout khi Resource Server tải JWKS

### 4.1. Connect timeout khác read timeout

Để kiểm tra token mới mang `kid` chưa có trong cache, Resource Server có thể cần gọi HTTPS GET tới JWKS endpoint. Nếu kết nối chậm, request API phải chờ ở tầng authentication.

Có hai giới hạn thường dùng:

- **Connect timeout**: thời gian tối đa cho bước thiết lập kết nối.
- **Read/socket timeout**: thời gian chờ đọc phản hồi trên kết nối đã mở.

Theo **tài liệu Spring Security Servlet hiện hành**, các timeout mặc định được mô tả là **30 giây cho connect và 30 giây cho read**. Một số bản Spring Security cũ có mặc định khác; vì vậy khi SLA quan trọng, cần **đối chiếu đúng version và đặt timeout tường minh**.

Timeout trên không nhất thiết là một deadline tuyệt đối cho toàn bộ hoạt động. DNS, TLS, proxy, connection pool, retry và số lần gọi metadata/JWKS có thể tạo tổng thời gian khác. Các HTTP client khác nhau cũng có cách xử lý timeout chi tiết không giống hệt nhau.

### 4.2. Tạo `RestOperations` có timeout rõ ràng

Ví dụ dùng `RestTemplate` và `SimpleClientHttpRequestFactory`:

~~~java
package com.example.orders.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.web.client.RestOperations;
import org.springframework.web.client.RestTemplate;

@Configuration
public class JwksHttpConfig {

    @Bean
    RestOperations jwksRestOperations() {
        SimpleClientHttpRequestFactory factory =
            new SimpleClientHttpRequestFactory();

        // Các setter dạng int dùng đơn vị milliseconds.
        factory.setConnectTimeout(2_000);
        factory.setReadTimeout(4_000);

        return new RestTemplate(factory);
    }
}
~~~

Ở đây **2 giây** và **4 giây** chỉ là giá trị minh họa. Giá trị thật nên dựa trên độ trễ hệ thống, availability của issuer, timeout của gateway và số lượng requests đồng thời.

`SimpleClientHttpRequestFactory` minh họa cấu hình cơ bản, **không tự cung cấp connection pooling, retry có jitter hoặc circuit breaker**. Nếu cần proxy, TLS trust store doanh nghiệp, connection pool, mTLS hoặc tracing, hãy chọn `ClientHttpRequestFactory` phù hợp rồi dựng `RestOperations` cho việc tải JWKS.

Không dùng một REST client có interceptor gắn access token của người dùng vào mọi request để tải JWKS; JWKS fetch là hoạt động infrastructure và không nên tự động chuyển credential của caller cho endpoint khóa.

### 4.3. Nối HTTP client vào decoder với JWKS URI tường minh

~~~java
package com.example.orders.security;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;
import org.springframework.web.client.RestOperations;

@Configuration
public class JwksDecoderConfig {

    @Bean
    JwtDecoder jwtDecoder(
            @Qualifier("jwksRestOperations") RestOperations rest,
            @Value("${app.security.issuer}") String issuer,
            @Value("${app.security.jwks-uri}") String jwksUri) {

        NimbusJwtDecoder decoder = NimbusJwtDecoder
            .withJwkSetUri(jwksUri)
            .restOperations(rest)
            .build();

        decoder.setJwtValidator(
            JwtValidators.createDefaultWithIssuer(issuer));

        return decoder;
    }
}
~~~

Các property tương ứng:

~~~yaml
app:
  security:
    issuer: https://id.example.test/realms/shop
    jwks-uri: https://id.example.test/realms/shop/protocol/openid-connect/certs
~~~

Các tên `app.security.*` là **property do ứng dụng tự đặt**, không phải tên Spring Boot sẽ tự động áp dụng cho Resource Server. URI JWKS là ví dụ; thực tế phải lấy từ `jwks_uri` trong metadata provider hoặc hợp đồng IdP.

Đặc biệt, `withJwkSetUri(...)` chỉ định **nguồn public keys**; nếu muốn xác minh `iss`, cần dùng issuer validator như ví dụ. Không giả định chỉ khai báo key source đã đủ kiểm tra issuer.

### 4.4. Khi cần discovery theo issuer

Nếu muốn để decoder tìm `jwks_uri` bằng metadata:

~~~java
NimbusJwtDecoder decoder = NimbusJwtDecoder
    .withIssuerLocation(issuer)
    .restOperations(jwksRestOperations)
    .build();

decoder.setJwtValidator(
    JwtValidators.createDefaultWithIssuer(issuer));
~~~

Đây là API được tài liệu Spring Security mô tả cho việc tùy chỉnh HTTP client theo issuer. Phải phân biệt **thời điểm discovery**:

- Auto-configuration Spring Boot/Spring Security hiện hành có thể dùng cơ chế **lazy discovery** khi request JWT đầu tiên tới.
- Tự gọi `withIssuerLocation(...).build()` trong một bean có thể làm discovery xảy ra lúc khởi tạo bean, tùy phiên bản và cách cấu hình.
- Dùng `withJwkSetUri(...)` tránh discovery để tìm vị trí JWKS, nhưng HTTP tải public keys vẫn cần network khi không có key cache phù hợp.

Không kết luận tuyệt đối rằng IdP phải online lúc khởi động hoặc IdP không bao giờ ảnh hưởng request đầu tiên. Điều này phụ thuộc chính cách decoder được tạo và phiên bản triển khai.

## 5. Cache JWKS là cache khóa, không phải cache token

### 5.1. Cache giữ dữ liệu gì?

Tài liệu Spring Security nêu rằng Resource Server JWT thông thường **cache JWK Set trong bộ nhớ**, với thời gian tham chiếu mặc định khoảng **5 phút**. Việc cache giảm nhu cầu tải public keys ở mọi request.

| Dữ liệu | Có phải nội dung của JWK Set cache không? | Ghi chú |
|---|---|---|
| **JWKS JSON của issuer** | Có | Chứa những public keys cho JWS validation |
| Access token JWT của người dùng | Không | JWT vẫn được validate theo request |
| Claim `exp`, `aud`, `scope` đã được “approve” | Không | Không phải cache kết quả phân quyền |
| Kết quả introspection của opaque token | Không | Dùng cơ chế introspection riêng |
| Private signing key của Authorization Server | Không | Không được đưa vào JWKS công khai |

**Cache JWKS không làm token có hiệu lực lâu hơn**. Dù public key đang cache, JWT hết hạn phải bị từ chối theo `exp`; token sai issuer/audience vẫn bị từ chối nếu validators được cấu hình.

Cache cũng không tự bảo đảm phát hiện JWT bị thu hồi trước khi `exp`. Nếu hệ thống có yêu cầu revocation tức thì, cần thiết kế token lifetime/introspection/denylist và threat model riêng.

### 5.2. `cache(Cache)` của decoder lưu theo URI

Builder hỗ trợ:

~~~java
NimbusJwtDecoder decoder = NimbusJwtDecoder
    .withJwkSetUri(jwksUri)
    .cache(jwkSetCache)
    .build();
~~~

`jwkSetCache` phải là một `org.springframework.cache.Cache` có thể lưu dữ liệu theo semantics được Spring Security sử dụng:

- **Key:** JWK Set URI.
- **Value:** JWK Set JSON.

Một cache entry chứa **toàn bộ JWK Set**, có thể có nhiều `kid`. Nó **không** được key theo từng JWT, từng `sub`, `jti`, hoặc `kid`. Không viết cache provider giả định nhận key là token ID rồi mong builder hoạt động.

### 5.3. Spring Cache là abstraction

`org.springframework.cache.Cache` và `CacheManager` là API chung; provider thực tế chịu trách nhiệm eviction/TTL, in-memory hay shared store. Với cache local có TTL, Caffeine là một ví dụ.

Dependencies Gradle:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
    implementation 'org.springframework.boot:spring-boot-starter-cache'
    implementation 'com.github.ben-manes.caffeine:caffeine'
}
~~~

Caffeine do Spring Boot cache starter tích hợp với Spring Cache khi classpath/cấu hình phù hợp. Dùng dependency version do BOM của Spring Boot tương ứng quản lý.

### 5.4. Ví dụ Caffeine: TTL và giới hạn kích thước

~~~java
package com.example.orders.security;

import java.time.Duration;

import com.github.benmanes.caffeine.cache.Caffeine;
import org.springframework.cache.CacheManager;
import org.springframework.cache.caffeine.CaffeineCacheManager;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class JwksCacheConfig {

    @Bean
    CacheManager jwksCacheManager() {
        CaffeineCacheManager manager = new CaffeineCacheManager("jwks");

        manager.setCaffeine(Caffeine.newBuilder()
            .maximumSize(20)
            .expireAfterWrite(Duration.ofMinutes(3)));

        return manager;
    }
}
~~~

Ví dụ này:

- Đặt tên cache `jwks`.
- Giữ nhiều nhất 20 cache entries; mỗi entry của `NimbusJwtDecoder` ứng với một JWKS URI.
- Đặt TTL của entry là khoảng **3 phút sau khi được ghi**.
- Tạo cache **trong process hiện tại**: replica khác không dùng chung cache.
- Không liên quan trực tiếp tới claim `exp` của token.

Ba phút và 20 entries là số minh họa, không phải khuyến nghị cố định. TTL cần cân bằng giữa lưu lượng JWKS và độ tươi key rotation; số entries tùy số issuer/JWKS URI thực tế.

### 5.5. Nối cache vào decoder

~~~java
package com.example.orders.security;

import java.util.Objects;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.cache.Cache;
import org.springframework.cache.CacheManager;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

@Configuration
public class CachedDecoderConfig {

    @Bean
    JwtDecoder jwtDecoder(
            @Qualifier("jwksCacheManager") CacheManager manager,
            @Value("${app.security.issuer}") String issuer,
            @Value("${app.security.jwks-uri}") String jwksUri) {

        Cache cache = Objects.requireNonNull(
            manager.getCache("jwks"),
            "The JWKS cache must exist");

        NimbusJwtDecoder decoder = NimbusJwtDecoder
            .withJwkSetUri(jwksUri)
            .cache(cache)
            .build();

        decoder.setJwtValidator(
            JwtValidators.createDefaultWithIssuer(issuer));

        return decoder;
    }
}
~~~

`CacheManager#getCache(...)` có thể trả `null`. Yêu cầu cache tồn tại rõ ràng giúp tránh silently dùng cache sai tên. Với ứng dụng có nhiều `CacheManager` bean, dùng `@Qualifier` để tiêm đúng instance.

Đây là **một ví dụ độc lập**; khi triển khai chỉ giữ một cấu hình decoder phù hợp, tránh khai báo trùng các `JwtDecoder` beans minh họa.

## 6. Kết hợp HTTP client, cache và validators

Giả sử Orders API yêu cầu:

| Thuộc tính | Giá trị minh họa |
|---|---|
| JWT issuer | `https://id.example.test/realms/shop` |
| JWKS URI | `https://id.example.test/realms/shop/protocol/openid-connect/certs` |
| Audience | `orders-api` |
| JWS algorithm | `RS256` |
| JWKS connect timeout | 2 giây |
| JWKS read timeout | 4 giây |
| Cache | Local Caffeine, TTL 3 phút, tối đa 20 entries |

YAML:

~~~yaml
app:
  security:
    jwt:
      issuer: https://id.example.test/realms/shop
      jwks-uri: https://id.example.test/realms/shop/protocol/openid-connect/certs
      audience: orders-api
~~~

Java:

~~~java
package com.example.orders.security;

import java.time.Duration;
import java.util.Objects;

import com.github.benmanes.caffeine.cache.Caffeine;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.cache.Cache;
import org.springframework.cache.CacheManager;
import org.springframework.cache.caffeine.CaffeineCacheManager;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;
import org.springframework.web.client.RestOperations;
import org.springframework.web.client.RestTemplate;

@Configuration
public class OrdersJwtInfrastructureConfig {

    @Bean
    CacheManager jwksCacheManager() {
        CaffeineCacheManager manager = new CaffeineCacheManager("jwks");
        manager.setCaffeine(Caffeine.newBuilder()
            .maximumSize(20)
            .expireAfterWrite(Duration.ofMinutes(3)));
        return manager;
    }

    @Bean
    JwtDecoder jwtDecoder(
            @Value("${app.security.jwt.issuer}") String issuer,
            @Value("${app.security.jwt.jwks-uri}") String jwksUri,
            @Value("${app.security.jwt.audience}") String audience,
            @Qualifier("jwksCacheManager") CacheManager manager) {

        SimpleClientHttpRequestFactory factory =
            new SimpleClientHttpRequestFactory();
        factory.setConnectTimeout(2_000);
        factory.setReadTimeout(4_000);
        RestOperations jwksHttp = new RestTemplate(factory);

        Cache jwksCache = Objects.requireNonNull(
            manager.getCache("jwks"),
            "Missing 'jwks' cache");

        NimbusJwtDecoder decoder = NimbusJwtDecoder
            .withJwkSetUri(jwksUri)
            .restOperations(jwksHttp)
            .cache(jwksCache)
            .jwsAlgorithm(SignatureAlgorithm.RS256)
            .build();

        OAuth2TokenValidator<Jwt> issuerAndTime =
            JwtValidators.createDefaultWithIssuer(issuer);

        OAuth2TokenValidator<Jwt> expectedAudience = jwt -> {
            if (jwt.getAudience().contains(audience)) {
                return OAuth2TokenValidatorResult.success();
            }
            return OAuth2TokenValidatorResult.failure(
                new OAuth2Error(
                    "invalid_token",
                    "Access token has incorrect audience",
                    null));
        };

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                issuerAndTime,
                expectedAudience));

        return decoder;
    }
}
~~~

**Giải thích từng extension point:**

1. `withJwkSetUri(jwksUri)` dùng URI public keys được cấu hình.
2. `restOperations(jwksHttp)` dùng HTTP transport với timeout theo hợp đồng.
3. `cache(jwksCache)` kết nối Spring Cache cho JSON JWKS.
4. `jwsAlgorithm(RS256)` cho phép thuật toán ký đã xác định.
5. `JwtValidators.createDefaultWithIssuer(issuer)` bảo toàn issuer và các validator mặc định về thời gian.
6. `expectedAudience` từ chối token không dành cho Orders API.
7. Trong Spring Resource Server, bộ giải mã này được gọi khi có Bearer JWT để xác thực.

Nếu issuer thực tế dùng PS256/ES256, cần điều chỉnh `jwsAlgorithm(...)` phù hợp; không cho token tự chọn bất kỳ thuật toán nào. Những cấu hình JWE/opaque token không được kích hoạt bởi builder signed JWT này.

### 6.1. Filter chain sử dụng decoder

~~~java
@Bean
SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
    http
        .securityMatcher("/api/**")
        .authorizeHttpRequests(auth -> auth
            .requestMatchers(HttpMethod.GET, "/api/orders/**")
                .hasAuthority("SCOPE_orders.read")
            .anyRequest().authenticated()
        )
        .oauth2ResourceServer(oauth2 -> oauth2
            .jwt(Customizer.withDefaults())
        );

    return http.build();
}
~~~

Các import:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
~~~

Nếu không có một bean `JwtDecoder` rõ ràng để auto wire, hoặc nếu có nhiều decoder, có thể truyền decoder tường minh cho DSL: `.jwt(jwt -> jwt.decoder(customDecoder))`. Chỉ giữ một cơ chế decoder chủ đích trong chain.

### 6.2. Khi tự tạo bean, kiểm tra lại auto-configuration

Spring Boot có thể cung cấp decoder tự động từ:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://id.example.test/realms/shop
          audiences: orders-api
~~~

Nhưng khi ứng dụng tự tạo `@Bean JwtDecoder`, cấu hình tự động của Boot có thể **nhường chỗ cho bean đó**. Khi ấy, những property tiện lợi như `audiences` không nên được giả định tự áp dụng lên decoder riêng.

Mọi phiên bản decoder tùy chỉnh đều phải giữ **JWT signature check**, issuer/time/audience validation và các ràng buộc token profile/claims theo hợp đồng. Không vì tùy chỉnh timeout/cache mà bỏ mất `iss` hoặc `aud` validation.

## 7. TTL và key rotation: cơ chế nào thực sự quyết định việc làm mới?

### 7.1. Thời gian sống của JWT khác TTL JWKS

Access token có:

~~~json
{
  "iss": "https://id.example.test/realms/shop",
  "aud": ["orders-api"],
  "exp": 2000000000
}
~~~

JWKS cache TTL ba phút **không thay đổi giá trị `exp`**. Một token đã hết hạn vẫn không hợp lệ dù public key ký nó có trong cache. Một token còn hạn nhưng không có public key phù hợp thì vẫn không thể xác minh.

Có thể có nhiều TTL khác nhau cùng tồn tại:

- JWT lifetime của token.
- TTL của Spring Cache chứa JSON JWKS.
- Cache/refresh policy bên trong Nimbus key source, tùy phiên bản.
- HTTP cache headers trên CDN/proxy phục vụ JWKS.
- DNS caching và connection reuse, không trực tiếp là JWKS data cache.

Không lấy một TTL để suy ra chắc chắn tất cả thời điểm cập nhật khóa của mọi tầng.

### 7.2. Công bố trước khi sử dụng khóa mới

Một trình tự rotation thường phù hợp:

~~~mermaid
flowchart TD
    A["Issuer đang ký token bằng K1"] --> B["JWKS công bố K1"]
    B --> C["Issuer bổ sung K2 vào JWKS, vẫn giữ K1"]
    C --> D["API có cơ hội làm mới JWKS"]
    D --> E["Issuer bắt đầu ký token mới bằng K2"]
    E --> F["API xác minh K2 bằng public key mới"]
    F --> G["Giữ K1 đến khi token cũ hết hạn theo policy"]
    G --> H["Issuer rút K1 theo kế hoạch"]
~~~

Thực tế issuer có thể rotate theo lịch hoặc khẩn cấp, nhưng luôn cần phối hợp:

- Thời điểm công bố key mới.
- Cửa sổ overlap K1/K2.
- TTL và refresh policy ở Resource Server.
- Lượng token cũ chưa hết hạn.
- Clock skew, trạng thái cache của nhiều replica.
- Cách xử lý khi endpoint JWKS không khả dụng.

**Không khẳng định `kid` chưa biết luôn làm cache refresh ngay.** Hành vi refresh-on-unknown-key phụ thuộc implementation Nimbus/Spring và custom cache. Một số cấu hình có thể chủ động fetch khóa mới, nhưng cần xác nhận bằng môi trường thật.

### 7.3. TTL quá ngắn hoặc quá dài

| Lựa chọn TTL | Lợi ích | Bất lợi |
|---|---|---|
| Rất ngắn | Có cơ hội thấy cập nhật JWKS sớm | Tăng HTTP requests, phụ thuộc IdP nhiều hơn |
| Vừa phải | Cân bằng traffic và key freshness | Có trễ nhận khóa mới ở một số tình huống |
| Rất dài | Ít tải JWKS lặp | Có thể chậm cập nhật rotation hoặc thu hồi khóa khẩn cấp |

Cache không tự giải quyết tình huống **private signing key bị lộ**. Khi đó tổ chức cần chính sách thu hồi/rotate key, invalidation cache, token revocation và ứng phó sự cố phù hợp, chứ không chỉ đổi TTL.

## 8. Cache local, nhiều replica và shared cache

### 8.1. Caffeine mặc định ở từng process

Nếu chạy ba replica:

~~~text
Orders API replica A --> Caffeine cache A
Orders API replica B --> Caffeine cache B
Orders API replica C --> Caffeine cache C
~~~

Mỗi cache có thể được nạp ở thời điểm khác nhau. Khi rollout nhiều pod cùng lúc hoặc cache hết hạn đồng loạt, IdP có thể nhận một **đợt request JWKS lớn**.

Các biện pháp vận hành:

- Thiết kế IdP/JWKS endpoint đủ sẵn sàng và chịu tải.
- Có lịch công bố khóa trước thời điểm sử dụng.
- Đặt TTL theo nhu cầu, theo dõi JWKS fetch count/latency.
- Cân nhắc prewarming hoặc rollout có kiểm soát nếu hệ thống yêu cầu, nhưng luôn xác minh khóa theo policy.
- Không ghi JWT raw vào log để phân tích cache.

### 8.2. Khi nào cần shared cache?

`Spring Cache` có thể kết nối provider Redis hoặc hệ phân tán nếu ứng dụng cài đặt và cấu hình phù hợp. Một cache chia sẻ có thể giảm tải JWKS so với các cache local độc lập.

~~~text
API replica A ----+
                  |
API replica B ----+----> Shared JWKS cache
                  |
API replica C ----+
~~~

Nhưng shared cache tạo thêm một dependency. Cần xem xét:

- Shared cache down thì Resource Server phản ứng thế nào?
- Network latency tới Redis có nhanh hơn việc dùng cache local không?
- Những replica có dùng chung cache name, TTL, serializer và key prefix phù hợp không?
- Có nhiều issuer/tenant dùng chung một cache không?
- Ai có quyền ghi đè entry với key là JWKS URI?
- Policy evict/invalidate khi issuer thu hồi khóa là gì?
- Có lớp cache nội bộ của Nimbus mà shared cache không đồng bộ tức thời không?

**Nguồn tin cậy vẫn là issuer/JWKS URI đã được cấu hình**. Một shared cache cho public keys tuy không chứa private key nhưng vẫn phải được bảo vệ khỏi hành vi thay thế dữ liệu, cấu hình nhầm hoặc ghi đè không đáng tin.

Dùng shared cache khi có nhu cầu thực sự và đã xác minh tính tương thích. Với một vài replica, local cache và JWKS endpoint khỏe có thể phù hợp hơn.

### 8.3. Cache key có phải `kid` không?

Không. Theo contract `cache(Cache)` được Spring Security mô tả:

~~~text
Cache key:
  https://id.example.test/realms/shop/protocol/openid-connect/certs

Cache value:
  {"keys":[{"kid":"K1",...},{"kid":"K2",...}]}
~~~

Entry cache giữ **JWKS JSON**, nên một entry có thể chứa nhiều khóa. Đừng tự viết cache adapter lưu `kid -> JWK` rồi cung cấp cho builder nếu adapter không tuân thủ key/value contract của Spring.

## 9. Khi JWKS endpoint bị lỗi

### 9.1. Có khóa phù hợp trong cache

Nếu Resource Server đã có public key phù hợp trong cache và token đúng validator, nó có thể xác minh chữ ký mà không cần tải JWKS mới cho request đó. Một đợt mất mạng ngắn hạn chưa chắc gây lỗi cho mọi token.

Tuy nhiên, độ sẵn sàng còn phụ thuộc expiry/refresh, caching internals và trạng thái process. Không nên hứa rằng sau lần lấy JWKS đầu tiên API sẽ luôn xác thực offline.

### 9.2. Cần khóa mới nhưng mạng không hoạt động

JWT mới có `kid` K2, nhưng cache chỉ chứa K1. Nếu không lấy được public key đáng tin của K2, Resource Server **không được chấp nhận token** dù payload mang `iss` và `scope` trông hợp lệ.

Cần quan sát rõ lỗi JWKS HTTP, không bỏ chữ ký, không tự chấp nhận `alg=none`, không tin JWKS URL do token đề xuất.

### 9.3. Timeout có luôn tạo 401 không?

Không nên cam kết một status cố định. Khi decoder không xác minh được token, API có thể trả authentication failure/401; nhưng network outage, timeout hoặc lỗi infrastructure trong chuỗi fetch JWKS có thể được xử lý thành lỗi service tùy thư viện và custom handlers.

Phân biệt trong logs/metrics:

- **Invalid signature**: có key phù hợp nhưng token không xác minh được.
- **Unknown kid**: chưa tìm được key tương ứng.
- **JWKS fetch timeout/HTTP 5xx**: chưa lấy được dữ liệu cần thiết.
- **Issuer/audience/time validation error**: chữ ký có thể hợp lệ nhưng claims sai.
- **Insufficient scope**: authentication hợp lệ nhưng authorization từ chối (thường 403).

Không quy tất cả 401 vào “cache hỏng”, hoặc tất cả network errors vào “token bị thu hồi”.

### 9.4. Không bật retry vô hạn

`restOperations(...)` dùng để điều chỉnh HTTP transport. Nó không tự cung cấp retry/backoff/circuit breaker hoàn chỉnh. Retry không giới hạn có thể giữ request threads quá lâu và khuếch đại tải khi IdP gặp sự cố.

Nếu thêm retry, hãy đặt deadline tổng, backoff/jitter, giới hạn attempts, khả năng idempotent của GET và hành vi khi quá tải theo SLO.

## 10. Những giới hạn cần nhận diện trước khi tùy chỉnh

### 10.1. `NimbusJwtDecoder` chỉ là một triển khai của `JwtDecoder`

Đường đi chủ đạo cho Servlet OAuth 2.0 Resource Server nhận signed JWT là:

~~~text
BearerTokenAuthenticationFilter
    |
    v
JwtAuthenticationProvider
    |
    v
NimbusJwtDecoder
    |---- HTTP fetch JWKS khi cần
    |---- JWK Set cache
    |---- JWS signature verification
    |---- JWT claim validators
    v
Authentication + authorities
    |
    v
AuthorizationFilter
~~~

Builder không định nghĩa mọi hành vi của mạng, cache và key-selection. Với yêu cầu sâu hơn, Spring Security cung cấp extension point để tạo **Nimbus `JWTProcessor`** và truyền vào constructor `NimbusJwtDecoder`. Đây là công việc cần kiểm soát rõ key-source trust, JWS algorithm allowlist, cache/refresh behavior và validators.

Không tự viết parser bằng cách Base64URL-decode JWT rồi xem `kid`/`iss` là bằng chứng xác thực. Signature và toàn bộ validation phải được duy trì.

### 10.2. HTTP client tùy chỉnh không áp dụng cho mọi request outbound

`restOperations(...)` của decoder phục vụ việc lấy cấu hình/khóa theo builder. Nó **không tự thay đổi**:

- `RestTemplate`/`WebClient` mà ứng dụng dùng gọi API nghiệp vụ.
- OAuth 2.0 Client đổi authorization code hoặc refresh token.
- HTTP client cho opaque token introspection.
- API Gateway hoặc trình duyệt đang gửi Bearer token.
- WebFlux `NimbusReactiveJwtDecoder`.

Nếu Resource Server dùng **opaque access token**, phải cấu hình `OpaqueTokenIntrospector`; không có JWS/JWKS để xác minh tương tự.

### 10.3. Decoder JWT mặc định không tự giải mã JWE

Thư viện Nimbus JOSE + JWT có nhiều thành phần, nhưng Spring Resource Server `NimbusJwtDecoder` theo đường đi signed JWT thông thường dùng để xác minh **JWS**. Nếu provider cấp **JWE encrypted access token**, cần thiết kế giải mã và validation riêng; thêm `cache(...)` hoặc `restOperations(...)` không kích hoạt JWE decryption.

### 10.4. Không nới lỏng thuật toán xác minh

Ví dụ signing key và token cùng nêu `RS256` không phải lý do tin mọi giá trị `alg` do token gửi. API phải có allowlist thuật toán theo hợp đồng issuer. Không tự động tìm public key ở `jku`/`x5u` không đáng tin hoặc chuyển giữa RSA/HMAC chỉ dựa trên input token.

## 11. Checklist tình huống thực hành

### 11.1. Bài thử khả năng HTTP/cache

Khi kiểm chứng ứng dụng trong môi trường thử nghiệm có issuer/JWKS do nhóm kiểm soát:

| Case | Điều cần quan sát |
|---|---|
| JWT ký K1, cache rỗng | JWKS có thể được fetch và token xác minh đúng |
| JWT thứ hai cùng K1 | Số lần fetch giảm nếu cache hoạt động |
| JWT sai chữ ký, K1 có trong JWKS | Bị từ chối dù key đã cache |
| JWT hết hạn, K1 còn trong cache | Bị từ chối theo `exp` |
| JWT đúng issuer, sai audience | Bị từ chối theo audience validator |
| JWKS công bố thêm K2 | Decoder có cách nhận tập khóa mới |
| JWT ký K2, cache đang chứa K1 | Theo dõi refresh/fetch theo implementation |
| JWKS timeout, cần K2 | Không chấp nhận token chưa thể xác minh |
| JWKS timeout, K1 đang cache | Xác minh được hay không tùy trạng thái cache/refresh |
| Cache TTL hết | Quan sát lần cập nhật JWKS và key rotation |
| Nhiều replica restart | Quan sát burst và cache local/shared |
| `kid` không tồn tại | Không tạo tin cậy cho khóa bất kỳ |

Các phép thử nên dùng **JWT test được ký bởi issuer test**, JWKS endpoint test và filter chain thật. Test MockMvc bằng `jwt()` có thể mô phỏng authentication để kiểm tra rule, nhưng **không tự chứng minh** HTTP fetch JWKS và cache đã được sử dụng.

### 11.2. Observability nên đo gì?

Các tín hiệu đáng theo dõi:

- JWKS HTTP GET count, latency, timeout, HTTP errors.
- Cache hit, miss, expiry/eviction theo cache provider.
- Thời gian/token failures khi issuer xoay vòng `kid`.
- JWT decode errors tách khỏi authorization `403`.
- Số request đồng thời cần refresh khóa.
- Tình trạng JWKS endpoint và hiệu ứng rollout nhiều replicas.
- Theo dõi thay đổi cấu hình issuer/JWKS/allowed algorithms.

Các metric trên là **mục tiêu instrument**, không phải tất cả đã có sẵn đúng tên trong Spring Security. Có thể instrument HTTP client và cache provider để thu thập. Tuyệt đối không log nguyên token Bearer, secret hoặc private keys.

### 11.3. Đọc metadata và JWKS theo hợp đồng

Với URL minh họa:

~~~bash
curl -i \
  https://id.example.test/realms/shop/.well-known/openid-configuration
~~~

Sau khi tìm thấy `jwks_uri` trong metadata có thể kiểm tra:

~~~bash
curl -i \
  https://id.example.test/realms/shop/protocol/openid-connect/certs
~~~

Không tự giả định mọi provider dùng đúng đường dẫn trên. TLS certificate, issuer metadata và URI JWKS phải khớp nguồn được tổ chức tin cậy.

Gọi API thử nghiệm:

~~~bash
curl -i \
  -H "Authorization: Bearer <TEST_ACCESS_TOKEN>" \
  https://api.example.test/api/orders
~~~

Một response 401 có thể do JWT chưa xác minh được, issuer/audience sai hoặc token hết hạn; response 403 có thể do token hợp lệ nhưng thiếu `orders.read`. Không đánh đồng HTTP status API với tình trạng JWKS fetch.

## 12. Ma trận chọn cấu hình

| Yêu cầu thực tế | Hướng tiếp cận |
|---|---|
| Provider hỗ trợ issuer discovery và mặc định đáp ứng SLA | Spring Boot `issuer-uri`, dùng auto-config |
| Cần JWKS endpoint xác định trước | `withJwkSetUri(...)` và issuer validator |
| Cần timeout cho HTTP tải JWKS | Builder `restOperations(...)` và HTTP client được cấu hình |
| Cần TTL hoặc eviction cho JWKS | Builder `cache(Cache)` và Spring Cache provider |
| Cần gộp timeout, cache và audience | Custom `JwtDecoder` bean với tất cả validators |
| Cần giới hạn thuật toán JWS | `jwsAlgorithm(...)` theo policy issuer |
| Nhiều replica và nhiều JWKS GET | Cân nhắc shared cache, rollout và IdP capacity |
| Key rotation phức tạp | Phối hợp phát hành K1/K2, cache, refresh và monitoring |
| Muốn refresh-ahead/failover/key source đặc thù | Đánh giá extension Nimbus `JWTProcessor` và trust model |
| Access token opaque | `OpaqueTokenIntrospector` riêng |
| Access token JWE | Decryption architecture riêng, không chỉ builder signed JWT |
| Ứng dụng WebFlux | API reactive decoder/HTTP client, không dùng code Servlet nguyên bản |

## 13. Những nguyên tắc cần nhớ

- **JWK Set** chứa các public keys để xác minh signed JWT/JWS. JWKS URI phải là nguồn tin cậy đã được cấu hình hoặc được discovery từ issuer đã tin cậy.
- **`NimbusJwtDecoder`** hỗ trợ tùy chỉnh **HTTP client bằng `restOperations(...)`** và **JWK Set cache bằng `cache(Cache)`** trong các builder thích hợp.
- Theo tài liệu Spring Security Servlet hiện hành, JWKS thường được cache trong bộ nhớ khoảng **5 phút**, connect/read timeout mặc định được mô tả là **30 giây mỗi loại**. Với yêu cầu latency chính xác, hãy kiểm tra phiên bản và cấu hình tường minh.
- **Custom Spring Cache** dùng **JWKS URI làm key**, **JWKS JSON làm value**. Cache JWKS khác JWT lifetime, kết quả introspection và việc thu hồi token.
- **TTL và key rotation cần phối hợp**. Bên phát hành nên công bố khóa mới trước khi ký token mới và giữ khóa cũ đủ lâu theo chính sách. Không dựa vào giả định mọi `kid` chưa biết sẽ làm decoder refresh ngay.
- Khi tự tạo bean `JwtDecoder`, cần **giữ issuer/time/audience/token profile validation và algorithm allowlist**; tùy chỉnh network/cache không được làm yếu trust boundary.
- Timeout và cache hỗ trợ availability, nhưng **không tự cung cấp retry/circuit breaker/failover** hoặc bảo đảm mọi request vẫn chạy khi JWKS endpoint outage.
- Với yêu cầu nằm ngoài API builder, có thể sử dụng Nimbus `JWTProcessor` chuyên dụng, nhưng phải quản lý đầy đủ khóa, algorithms, cache và validators.

### Tài liệu tham khảo

- [Spring Security Reference — OAuth 2.0 Resource Server JWT (Servlet)](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
- [Spring Security API — NimbusJwtDecoder](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/jwt/NimbusJwtDecoder.html)
- [Spring Security Reference — OAuth 2.0 Migrations](https://docs.spring.io/spring-security/reference/migration/servlet/oauth2.html)
- [Spring Framework API — Cache](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/Cache.html)
- [Spring Framework API — CacheManager](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/CacheManager.html)
- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517)
- [RFC 7515 — JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515)
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519)
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725)

