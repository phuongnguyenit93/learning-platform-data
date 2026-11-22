# Tùy chỉnh WebClient, timeout và cache theo API của phiên bản

Trong **Spring Security OAuth 2.0/OIDC Resource Server sử dụng Spring WebFlux**, JWT access token thường được xác minh bằng public key lấy từ **JWK Set endpoint (JWKS)** của Authorization Server (AS). Khi cần đi qua proxy, cấu hình TLS riêng, giới hạn độ trễ, bảo vệ ứng dụng trước outage của AS hoặc kiểm soát cách làm mới khóa, developer thường phải tùy chỉnh **`WebClient`**, **timeout** và **cache**.

Điểm khó không nằm ở cú pháp `WebClient.builder()`, mà ở chỗ **các API cấu hình của decoder Reactive và decoder Servlet không giống nhau**, đồng thời một số builder method được bổ sung hoặc đổi theo từng phiên bản Spring Security.

> **Nguyên tắc:** cấu hình network/cache chỉ được thay đổi cách Resource Server **lấy khóa đáng tin**. Nó không được bỏ qua bước xác minh chữ ký, giảm yêu cầu `iss`/`aud`/thời hạn, tin JWK URI do client tùy ý gửi hoặc chấp nhận JWT chưa xác minh chỉ vì JWKS endpoint đang lỗi.

Bài này giải thích kiến trúc lấy JWKS trong WebFlux, phân biệt `NimbusReactiveJwtDecoder` và `NimbusJwtDecoder`, cách cấu hình `WebClient` với Reactor Netty, ba loại timeout, xử lý issuer discovery, cache/rotation, lỗi phổ biến và chiến lược kiểm thử. Ví dụ sử dụng **Java 17+, Spring Boot, WebFlux, Spring Security 6.5/7.x** khi có chỉ định. Dự án dùng bản cũ hơn phải kiểm tra Javadoc/version trước khi sao chép.

## 1. WebClient làm gì trong luồng xác thực JWT?

Một request nghiệp vụ:

~~~http
GET /api/orders HTTP/1.1
Host: orders-api.example.com
Authorization: Bearer eyJhbGciOiJSUzI1NiIsImtpZCI6...
~~~

có thể đi theo luồng:

~~~text
Client
  |
  | Bearer JWT
  v
Spring WebFlux Resource Server
  |
  v
AuthenticationWebFilter
  |
  v
ReactiveJwtDecoder.decode(token)
  |
  +-- Đọc JWS header: alg, kid, typ ...
  |
  +-- Chọn khóa có thể xác minh chữ ký
  |      |
  |      +-- JWK Set đã có trong nguồn khóa/cache?
  |      |       |
  |      |       +-- Có khóa phù hợp -> xác minh chữ ký
  |      |
  |      +-- Cần tải/làm mới JWKS
  |              |
  |              v
  |        WebClient -> HTTPS -> Authorization Server JWKS
  |              |
  |              +-- HTTP/network timeout -> không có khóa đáng tin
  |              +-- Thành công -> xử lý JWK Set theo policy
  |
  +-- Xác minh chữ ký với thuật toán được cho phép
  |
  +-- Validate claims: iss, aud, exp, nbf, token type ...
  |
  v
JwtAuthenticationToken
  |
  v
authorizeExchange -> service authorization
~~~

**Không phải mỗi API request đều cần gọi WebClient.** Khi khóa phù hợp đã có trong cache/sources của decoder, phần xác minh chữ ký JWT có thể hoàn toàn cục bộ. Việc lấy metadata và JWKS thường xảy ra khi khởi tạo/giải mã lần đầu, khi bộ nhớ khóa hết hạn hoặc khi key rotation đòi cập nhật. Chính xác thời điểm, TTL, xử lý unknown `kid` và cache refresh phụ thuộc **phiên bản Spring Security, Nimbus và cấu hình**.

### 1.1. Những request nào thật sự đi qua WebClient?

Trong cấu hình decoder Reactive, WebClient có thể được sử dụng cho:

1. **Issuer discovery:** lấy OIDC Provider Configuration hoặc OAuth Authorization Server Metadata để tìm `jwks_uri`.
2. **JWKS retrieval:** lấy JWK Set chứa các public keys được phép dùng để xác minh.
3. **JWKS refresh:** tải lại khi chính sách key source yêu cầu, ví dụ khóa mới xuất hiện.
4. **Các request bổ sung nếu custom source thực sự triển khai**, nhưng đó không phải mặc định của một JWT decoder thông thường.

**Không** hiểu rằng WebClient này sẽ tự gọi endpoint introspection cho JWT. JWT Resource Server với `jwt()` xác minh chữ ký; opaque token flow dùng **`ReactiveOpaqueTokenIntrospector`** và có network/client configuration riêng.

### 1.2. Phân biệt network timeout và JWT validation

| Vấn đề | Lớp xử lý | Ví dụ |
|---|---|---|
| Không kết nối được AS | WebClient / TCP / TLS / DNS | Connection timeout |
| AS không trả HTTP response kịp | WebClient / Reactor Netty | Response timeout |
| JWKS trả JSON sai schema | JWKS parser/key source | Không lấy được public key |
| `kid` không khớp key hiện có | Key selection/refresh | Unknown signing key |
| JWS chữ ký sai | `NimbusReactiveJwtDecoder` | Invalid signature |
| JWT hết hạn | JWT validator | `exp` |
| Issuer hoặc audience sai | JWT validator | `iss`, `aud` |
| Không có scope gọi endpoint | HTTP authorization | 403 sau khi token xác thực |

Không dùng timeout dài hoặc cache stale để “sửa” lỗi signature. Đó là hai nhóm lỗi hoàn toàn khác nhau.

## 2. Trước khi custom: hiểu mặc định của Spring Boot

Với WebFlux JWT Resource Server, thường chỉ cần dependencies:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testImplementation 'io.projectreactor:reactor-test'
}
~~~

Spring Boot starter quản lý dependencies OAuth2 Resource Server và JOSE/JWT phù hợp trong BOM. Nếu quản lý dependencies trực tiếp, phải có các module Resource Server **và** OAuth2 JOSE cần cho JWT verification.

Một cấu hình tối thiểu:

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

Trong những Spring Boot version có hỗ trợ `audiences`, Resource Server sẽ ràng buộc claim `aud` theo cấu hình. Với version khác, cần validator audience riêng.

Nếu AS hỗ trợ discovery, `issuer-uri` giúp tìm `jwks_uri` và xây validation issuer. Cấu hình đơn giản như vậy thường **tốt hơn** tự viết decoder, nếu yêu cầu network/cache mặc định đã đáp ứng hệ thống.

### 2.1. Tại sao không custom decoder ngay từ đầu?

Viết bean `ReactiveJwtDecoder` riêng có thể khiến Spring Boot **không còn tự tạo bean decoder mặc định**. Những điều bạn tưởng “Boot sẽ xử lý hộ” như issuer validation, audience property, trusted JWS algorithms hoặc lazy initialization có thể cần được khôi phục tường minh tùy cách cấu hình.

Do đó, thứ tự lựa chọn hợp lý:

1. **Chỉ dùng Boot properties** khi đủ.
2. **Tùy chỉnh decoder qua builder công khai** khi cần `WebClient`, timeout, proxy hoặc thuật toán.
3. **Tùy chỉnh validators** nhưng giữ kiểm tra issuer/time/audience.
4. **Tùy chỉnh nguồn JWK/caching sâu** chỉ khi có yêu cầu cụ thể, API version hỗ trợ và test đầy đủ.
5. Tránh tự viết logic “decode JWT bằng Base64” để thay cryptographic verification.

## 3. Phân biệt API Servlet và Reactive theo phiên bản

Đây là bảng trọng tâm của bài học.

| Mục tiêu | Servlet/MVC | Reactive/WebFlux |
|---|---|---|
| Decoder interface | `JwtDecoder` | **`ReactiveJwtDecoder`** |
| Nimbus decoder | `NimbusJwtDecoder` | **`NimbusReactiveJwtDecoder`** |
| HTTP client tùy chỉnh ở builder JWK Set URI | `.restOperations(RestOperations)` | **`.webClient(WebClient)`** |
| Timeout HTTP client | `RestTemplate`/`RestClient` hoặc client tương ứng | **Reactor Netty `HttpClient` + `WebClient`** |
| Custom Spring Cache tại builder JWKS | Servlet `NimbusJwtDecoder...cache(Cache)` | **Không có `.cache(Cache)` ở JWK Set URI Reactive builder của 6.5/7.1** |
| Khởi tạo từ issuer discovery | `withIssuerLocation(...)` | **`withIssuerLocation(...)`** trên Reactive builder ở version hỗ trợ |
| Khởi tạo bằng JWK Set URI cố định | `withJwkSetUri(...)` | **`withJwkSetUri(...)`** |
| Decoder lazily initialized | `SupplierJwtDecoder` | **`SupplierReactiveJwtDecoder`** |
| Principal authentication | `JwtAuthenticationToken` | `JwtAuthenticationToken` trong reactive context |
| HTTP security chain | `SecurityFilterChain` | `SecurityWebFilterChain` |

### 3.1. API của `NimbusReactiveJwtDecoder.JwkSetUriReactiveJwtDecoderBuilder`

Theo Javadoc của Spring Security **6.5.x và 7.1.x**, builder Reactive theo JWK Set URI có những method công khai:

~~~java
.webClient(WebClient)
.jwsAlgorithm(SignatureAlgorithm)
.jwsAlgorithms(Consumer<Set<SignatureAlgorithm>>)
.jwtProcessorCustomizer(...)
.validateType(boolean)   // có từ Spring Security 6.5
.build()
~~~

Những method **không có** trên builder Reactive này:

~~~java
.restOperations(restTemplate) // thuộc Servlet decoder
.cache(springCache)          // thuộc Servlet JWK Set builder
.responseTimeout(duration)   // phải cấu hình WebClient/HTTP connector
~~~

Nếu thấy đoạn:

~~~java
// Không biên dịch trên JwkSetUriReactiveJwtDecoderBuilder.
NimbusReactiveJwtDecoder.withJwkSetUri(jwkSetUri)
    .cache(cacheManager.getCache("jwks"))
    .build();
~~~

thì rất có thể tác giả đã nhầm **`NimbusJwtDecoder` Servlet** với **`NimbusReactiveJwtDecoder` WebFlux**.

### 3.2. Vì sao câu “Spring Security hỗ trợ cache(Cache)” chưa đủ?

Câu đó có thể đúng cho **builder Servlet** nhưng sai cho **builder Reactive**.

Để tránh nhầm, khi đọc ví dụ trên internet hãy kiểm tra:

- Import là `NimbusJwtDecoder` hay `NimbusReactiveJwtDecoder`?
- Builder trả kiểu gì?
- Javadoc thuộc version 6.4, 6.5, 7.0 hay 7.1?
- Method `cache(...)` có xuất hiện trong *Reactive* Javadoc thật không?
- Cache được đề cập là **JWK Set cache**, **JWT authentication cache** hay **HTTP response cache**?

Không chỉ đổi tên class và giữ nguyên các builder calls.

### 3.3. Mốc phiên bản cần lưu ý

| API/đặc điểm | Mốc Javadoc | Nhận xét |
|---|---|---|
| `NimbusReactiveJwtDecoder.withJwkSetUri(...)` | Có từ dòng Spring Security 5.2 | Cấu hình JWKS URL tường minh |
| Reactive `.webClient(...)` | Có trong 6.5.x và 7.1.x | Tùy chỉnh HTTP client cho JWKS/discovery |
| `NimbusReactiveJwtDecoder.withIssuerLocation(...)` | Từ 6.1 | Tự derive JWKS qua issuer metadata |
| `SupplierReactiveJwtDecoder` | Từ 5.6 | Trì hoãn khởi tạo decoder |
| Reactive `.validateType(boolean)` | Từ 6.5 | Không tự disable type validation khi không có replacement |
| Reactive `.withJwkSource(...)` | Có trên dòng decoder hiện đại | Extension sâu, cần source/key selection an toàn |
| Servlet `.cache(Cache)` | Có trên `NimbusJwtDecoder` JWK Set builder | **Không áp dụng trực tiếp Reactive** |

Các con số trong bảng là mốc của API/Javadoc, không bảo đảm mọi phiên bản Spring Boot tương ứng đều dùng bản Spring Security đó. **Project BOM và actual dependency graph** mới quyết định method nào có thể gọi.

## 4. `issuer-uri` và `jwk-set-uri`: chọn đúng trước khi đổi network client

Có hai trường hợp cấu hình phổ biến.

### 4.1. Chỉ biết issuer

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.com/realms/shop
~~~

Resource Server dùng OIDC Discovery/OAuth Authorization Server Metadata để xác định `jwks_uri`. Quá trình này yêu cầu network call tới **issuer metadata** trước khi biết JWKS URL.

Điểm cần hiểu:

- `iss` trong JWT cần khớp issuer canonical.
- Metadata phải đến từ issuer/discovery được tin cậy.
- JWK Set URL có thể khác với issuer URL, đặc biệt sau reverse proxy.
- Nếu issuer discovery hoặc JWKS endpoint không sẵn sàng, token mới cần khóa không thể được xác minh.

### 4.2. Có JWK Set URI tường minh

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.com/realms/shop
          jwk-set-uri: https://idp.example.com/realms/shop/protocol/openid-connect/certs
          audiences:
            - orders-api
~~~

Khi có `jwk-set-uri` được cấu hình tường minh, Resource Server không cần discovery để xác định khóa. **Nhưng vẫn phải validate `iss`** nếu đó là contract của API.

Một deployment nội bộ có thể đặt:

~~~text
Canonical issuer:    https://login.example.com/realms/shop
Internal JWKS route: https://keys.internal.example/realms/shop/certs
```

Điều này có thể hợp lệ khi issuer canonical và key source nội bộ đều được quản trị, Resource Server tin URI nội bộ đó và **vẫn validate token `iss` bằng public issuer**. Đừng sửa `iss` thành hostname nội bộ chỉ để đường kết nối JWKS hoạt động.

### 4.3. Không đồng nhất location của public key với danh tính issuer

`jwk-set-uri` là nơi lấy public keys. `issuer-uri`/claim `iss` là **danh tính nguồn phát hành**. Cùng một key có thể bị dùng trong nhiều context; chỉ xác minh chữ ký mà bỏ issuer/audience validation có thể tạo **token substitution** hoặc cross-service acceptance.

## 5. Cấu hình WebClient riêng cho JWT key retrieval

Ví dụ đầy đủ bên dưới dùng:

- `NimbusReactiveJwtDecoder.withJwkSetUri(...)`.
- `.webClient(...)` của Reactive builder.
- `Reactor Netty HttpClient` có connect và response timeout.
- HTTPS URL có nguồn được cấu hình tin cậy.
- `JwtValidators.createDefaultWithIssuer(...)`.
- Một validator audience cho `orders-api`.

**Đây là cấu hình WebFlux**, không sử dụng `RestTemplate` hay `RestOperations`.

### 5.1. Properties minh họa

~~~yaml
app:
  security:
    jwt:
      issuer: https://idp.example.com/realms/shop
      jwk-set-uri: https://keys.internal.example/realms/shop/certs
      audience: orders-api
~~~

Dùng `app.security.jwt.*` để rõ rằng custom decoder sẽ tự nhận và tự áp dụng các giá trị này; không mặc định dựa vào Boot tự xử lý `audiences` sau khi bean đã được override.

### 5.2. Bean `ReactiveJwtDecoder` với timeout

~~~java
package com.example.orders.security;

import java.time.Duration;

import io.netty.channel.ChannelOption;
import reactor.netty.http.client.HttpClient;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusReactiveJwtDecoder;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
public class JwtDecoderConfiguration {

    @Bean
    ReactiveJwtDecoder reactiveJwtDecoder(
            @Value("${app.security.jwt.issuer}") String issuer,
            @Value("${app.security.jwt.jwk-set-uri}") String jwkSetUri,
            @Value("${app.security.jwt.audience}") String audience) {

        HttpClient httpClient = HttpClient.create()
            // TCP connect timeout = 2 giây.
            .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 2_000)
            // Thời gian chờ response từ remote endpoint.
            .responseTimeout(Duration.ofSeconds(3));

        // Dành riêng cho issuer/JWKS; không mang bearer token từ request.
        WebClient jwkWebClient = WebClient.builder()
            .clientConnector(
                new ReactorClientHttpConnector(httpClient))
            .codecs(configurer -> configurer.defaultCodecs()
                .maxInMemorySize(512 * 1024))
            .build();

        NimbusReactiveJwtDecoder decoder =
            NimbusReactiveJwtDecoder
                .withJwkSetUri(jwkSetUri)
                .webClient(jwkWebClient)
                .build();

        OAuth2TokenValidator<Jwt> audienceValidator = jwt -> {
            if (jwt.getAudience().contains(audience)) {
                return OAuth2TokenValidatorResult.success();
            }

            OAuth2Error error = new OAuth2Error(
                "invalid_token",
                "Required audience is missing",
                null
            );
            return OAuth2TokenValidatorResult.failure(error);
        };

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

Với decoder bean này, filter chain thường chỉ cần:

~~~java
@Bean
SecurityWebFilterChain apiSecurity(ServerHttpSecurity http) {
    return http
        .authorizeExchange(exchanges -> exchanges
            .pathMatchers("/api/public/**").permitAll()
            .pathMatchers("/api/orders/**")
                .hasAuthority("SCOPE_orders.read")
            .anyExchange().denyAll())
        .oauth2ResourceServer(oauth2 ->
            oauth2.jwt(Customizer.withDefaults()))
        .build();
}
~~~

Imports cho filter chain: `ServerHttpSecurity`, `SecurityWebFilterChain`, `Customizer`, `Bean`.

### 5.3. Điều gì đã được tùy chỉnh?

| Thành phần | Thay đổi | Điều vẫn phải giữ |
|---|---|---|
| `HttpClient` | Connect timeout, response timeout | TLS certificate/host validation |
| `WebClient` | Connector và kích thước bộ nhớ cho body JWKS | Chỉ kết nối endpoint đáng tin |
| `NimbusReactiveJwtDecoder` | Dùng WebClient custom để lấy JWK | Chữ ký/JWS algorithm selection |
| Validators | Ràng buộc issuer và audience | Time validation và token-type policy |
| Security chain | Quy tắc access ở HTTP boundary | Business tenant/ownership checks |

Ví dụ không chứng minh mọi token với `aud=orders-api` đều hợp lệ: chữ ký, algorithm, `iss`, `exp`, `nbf` và các validators vẫn phải đạt.

### 5.4. Chọn timeout số bao nhiêu là phù hợp?

`2 giây` và `3 giây` trong code là **giá trị minh họa**, không phải mặc định khuyến nghị cho mọi hệ thống. Quyết định thực tế phụ thuộc:

- SLO/SLA của API và AS.
- Khoảng cách mạng đến JWKS endpoint.
- p95/p99 connect/TLS/JWKS latency trong môi trường triển khai.
- Tình trạng proxy/service mesh/DNS.
- Thời gian còn lại của request budget.
- Cách cache và key rotation hoạt động.
- Hậu quả của outage với những request cần khóa chưa có.

Một API low-latency có thể chọn timeout ngắn; một hệ thống xuyên vùng mạng có thể cần dài hơn. **Không tăng timeout vô hạn để che network outage**.

## 6. Connect timeout, response timeout và tổng thời gian: không giống nhau

| Loại timeout | Phạm vi gần đúng | Ví dụ |
|---|---|---|
| TCP connect timeout | Chờ thiết lập kết nối mạng | `CONNECT_TIMEOUT_MILLIS` |
| TLS handshake timeout | Chờ hoàn thành handshake TLS | Cấu hình Netty SSL handler |
| Response timeout | Chờ hoạt động phản hồi từ server theo Netty policy | `HttpClient.responseTimeout(...)` |
| Read/write inactivity timeout | Chờ thao tác đọc/ghi mạng | Netty `ReadTimeoutHandler`, `WriteTimeoutHandler` |
| Overall request deadline | Tổng ngân sách từ lúc bắt đầu tới khi hoàn thành | Cần tự thiết kế tùy call chain |
| JWT timestamp validation | Token đã tới `exp`/chưa tới `nbf` | `JwtTimestampValidator` |
| JWK cache TTL | Thời gian được giữ một JWK set | Thuộc cache/key source, không phải HTTP timeout |

### 6.1. Connect timeout

~~~java
HttpClient client = HttpClient.create()
    .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 2_000);
~~~

Giới hạn thời gian thiết lập TCP connection. Nó không tự giới hạn toàn bộ TLS handshake, DNS resolution, số lần retry hoặc thời gian đọc response.

### 6.2. Response timeout

~~~java
HttpClient client = HttpClient.create()
    .responseTimeout(Duration.ofSeconds(3));
~~~

Áp dụng chính sách chờ phản hồi ở tầng Reactor Netty. Đây không luôn tương đương một **end-to-end total deadline**; tài liệu Reactor Netty/Spring WebClient cần được dùng để hiểu semantics chính xác theo version.

Một JWKS response chậm do server overload có thể bị timeout dù TCP connect rất nhanh.

### 6.3. TLS handshake timeout

Khi có proxy, mTLS, truststore/certificate chain lớn hoặc mạng chậm, có thể cần phân biệt handshake. Reactor Netty cung cấp SSL options theo phiên bản:

~~~java
HttpClient client = HttpClient.create()
    .secure(ssl -> ssl
        .handshakeTimeout(Duration.ofSeconds(3)));
~~~

Đây là **phần cấu hình lựa chọn**, không cần thêm nếu TLS mặc định đáp ứng. Không disable certificate verification để “sửa” handshake timeout.

### 6.4. Deadline của toàn bộ truy xuất JWKS

Một luồng có thể có DNS, connect, TLS, HTTP response, body decode và retry:

~~~text
DNS
 + connect
 + TLS
 + server response
 + body parsing
 + retry/backoff
 = tổng latency chịu bởi request gọi decoder
~~~

Nếu chỉ đặt `responseTimeout=3s`, không nên tự kết luận **toàn bộ decode luôn nhỏ hơn 3s**. Cần xem thêm connector, DNS, retries, discovery call, connection pool và cache.

Nếu hệ thống áp dụng tổng request deadline ở Reactor pipeline, hãy đặt nó ở boundary phù hợp, bảo đảm không biến **timeout kiểm tra chữ ký** thành một quyết định cho phép bypass. Timeout phải dẫn tới **không xác thực được token**, không có quyền.

### 6.5. CORS/browser không liên quan WebClient này

`WebClient` lấy JWKS là HTTP **server-to-server** do Resource Server chủ động thực hiện. Nó không chịu CORS giống trình duyệt. Nếu JWKS không tải được, kiểm tra DNS, TLS, proxy, firewall, URL, redirect, timeout và response schema, **không mở `Access-Control-Allow-Origin: *` chỉ để sửa JWKS request**.

## 7. Tùy chỉnh WebClient khi cần issuer discovery

Khi không biết `jwks_uri`, có thể dùng:

~~~java
NimbusReactiveJwtDecoder decoder =
    NimbusReactiveJwtDecoder
        .withIssuerLocation(issuer)
        .webClient(jwkWebClient)
        .build();

decoder.setJwtValidator(
    JwtValidators.createDefaultWithIssuer(issuer)
);
~~~

`withIssuerLocation(...)` có từ Spring Security **6.1** theo Javadoc. Nó dùng issuer metadata để tìm JWK Set URI; `.webClient(...)` có thể phục vụ cả discovery lẫn JWKS retrieval theo contract của builder.

### 7.1. Ví dụ method bean

~~~java
@Bean
ReactiveJwtDecoder issuerBasedDecoder(
        @Value("${app.security.jwt.issuer}") String issuer) {

    HttpClient http = HttpClient.create()
        .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 2_000)
        .responseTimeout(Duration.ofSeconds(3));

    WebClient metadataAndJwksClient = WebClient.builder()
        .clientConnector(new ReactorClientHttpConnector(http))
        .build();

    NimbusReactiveJwtDecoder decoder =
        NimbusReactiveJwtDecoder.withIssuerLocation(issuer)
            .webClient(metadataAndJwksClient)
            .build();

    decoder.setJwtValidator(
        JwtValidators.createDefaultWithIssuer(issuer)
    );

    return decoder;
}
~~~

**Không đăng ký bean này đồng thời với bean trong phần 5 rồi hy vọng Boot chọn một cách tự nhiên.** Đây là **phương án thay thế**. Nếu muốn audience validation, hãy bổ sung vào validator như phần 5.

### 7.2. Giữ canonical issuer

Một AS triển khai sau reverse proxy có thể có:

~~~text
Public issuer:  https://login.example.com/realms/shop
Internal JWKS:  https://keys.internal.example/realms/shop/certs
~~~

JWT hợp lệ vẫn có `iss=https://login.example.com/realms/shop`. Nếu đổi issuer validator thành `keys.internal.example` chỉ vì Resource Server kết nối JWKS nội bộ, token hợp lệ có thể bị từ chối hoặc hệ thống đánh mất ranh giới issuer.

Issuer là danh tính; JWKS URL là đường vận chuyển public keys. Hai khái niệm này phải được thiết kế riêng.

### 7.3. Startup independence và lazy discovery

Theo tài liệu Spring Security Reactive, `issuer-uri` có thể dùng cơ chế trì hoãn discovery tới request JWT đầu tiên, tránh ràng buộc việc start ứng dụng với AS đang online. Tài liệu đề cập `SupplierReactiveJwtDecoder` để bảo toàn cơ chế lazy khi tự công bố bean.

Có thể bọc:

~~~java
@Bean
ReactiveJwtDecoder lazyDecoder(
        @Value("${app.security.jwt.issuer}") String issuer) {

    return new SupplierReactiveJwtDecoder(() -> {
        NimbusReactiveJwtDecoder decoder =
            NimbusReactiveJwtDecoder.withIssuerLocation(issuer)
                .build();

        decoder.setJwtValidator(
            JwtValidators.createDefaultWithIssuer(issuer)
        );
        return decoder;
    });
}
~~~

Đây lại là **phương án thay thế khác** nhằm minh họa lazy creation; nếu cần timeout riêng, xây `WebClient` và gắn `.webClient(...)` trong supplier như ở phần trước.

`SupplierReactiveJwtDecoder` có từ **Spring Security 5.6**, nhưng phải kết hợp với builder/method tồn tại ở version của dự án. Lazy discovery không bảo đảm request đầu tiên sẽ thành công nếu AS/JWKS đang outage: đơn giản là lỗi có thể bị **dời từ lúc startup sang request đầu tiên**.

### 7.4. Direct JWKS URI thường giúp giảm một dependency mạng

Nếu đã biết và tin JWK Set URL:

~~~java
NimbusReactiveJwtDecoder.withJwkSetUri(jwkSetUri)
    .webClient(jwkWebClient)
    .build();
~~~

có thể bỏ bước discovery metadata. Nhưng cần **giữ issuer validator** và những validators khác. Không đổi tốc độ lấy khóa lấy bằng cách từ bỏ kiểm tra `iss`.

## 8. TLS, proxy và network trust của WebClient

Một decoder lấy khóa qua HTTP client tùy chỉnh cũng phải tuân thủ trust boundary.

### 8.1. HTTPS và certificate validation

JWKS chứa **public keys**, nhưng đường cung cấp chúng vẫn cần được bảo vệ khỏi kẻ tấn công thay thế khóa. Nếu attacker điều khiển JWKS response, họ có thể đưa public key của mình vào source được tin và làm Resource Server chấp nhận JWT giả nếu các điều kiện khác bị thỏa mãn.

Vì vậy:

- Dùng HTTPS cho JWKS endpoint khi kiến trúc cho phép.
- Xác thực hostname và certificate chain đúng.
- Quản lý private CA/truststore khi dùng mTLS hoặc nội bộ.
- Giới hạn egress đến endpoint được cấu hình.
- Không disable TLS verification trong production.
- Không ghi dữ liệu bí mật, token hoặc toàn bộ headers vào HTTP logging.

### 8.2. Không dùng bearer token nhận từ client để gọi JWKS

`WebClient` dùng lấy public keys không cần mang access token của người gọi. Không copy:

~~~text
Incoming Authorization: Bearer <user-token>
```

thành:

~~~text
Outgoing GET /jwks
Authorization: Bearer <user-token>
```

để “giữ context”. Đây là rò rỉ credential sang một endpoint không cần nó, đặc biệt nếu có redirect.

Nên tạo **WebClient dành riêng cho JWKS/metadata**. Nếu tái sử dụng `WebClient.Builder` được cấu hình toàn cục với `ExchangeFilterFunction` gắn credential, kiểm tra kỹ để tránh vô tình mang token/API key sang endpoint issuer.

### 8.3. Proxy nội bộ và DNS

Resource Server có thể chạy trong Kubernetes hoặc mạng doanh nghiệp mà chỉ truy cập AS qua proxy. Cần cấu hình proxy/connector theo tài liệu Reactor Netty version tương ứng, đồng thời cân nhắc:

- Proxy auth, NoProxy/bypass list và allowlist.
- DNS resolution, IPv4/IPv6.
- TLS SNI/hostname.
- Path rewrite và HTTP redirects.
- Latency của service mesh sidecar.
- Kết nối qua split-horizon DNS.
- Certificate chain của proxy.

Không tự chuyển một `https://login.example.com/...` thành `http://auth-service:8080/...` rồi đổi luôn issuer validation theo hostname nội bộ. Network route và token issuer phải được quản lý tách biệt.

### 8.4. Tránh SSRF qua URI/key source

JWT header có thể có các trường như `kid`, `jku`, `x5u`. Chúng là **input trong token do client gửi**, không nên được sử dụng như URL tùy ý cho `WebClient`:

~~~text
JWT header (untrusted until verified):
{"kid":"abc","jku":"https://attacker.example/jwks"}
~~~

Sai:

~~~text
JWK Set URI = JWT header jku
  -> WebClient tự gọi URL của attacker
  -> Resource Server tin public key do attacker kiểm soát
```

Hãy lấy `jwk-set-uri` từ **cấu hình server/issuer đã được allowlist**, không từ một header/query do caller tùy ý đặt. `kid` chỉ nên dùng để chọn khóa trong nguồn đã được tin, với chính sách refresh có giới hạn.

## 9. Cache là nhiều thứ khác nhau

Từ **cache** có thể chỉ ít nhất bốn tầng:

| Cache | Giữ gì? | Vấn đề chính |
|---|---|---|
| Issuer discovery cache | Provider metadata, `jwks_uri` | Metadata thay đổi hoặc AS tạm lỗi |
| **JWK Set cache** | Bộ public keys từ một nguồn tin cậy | Key rotation, TTL, unknown `kid` |
| HTTP response cache | HTTP response JWKS theo Cache-Control/ETag | Có phù hợp key source library hay không |
| Decoded/validated JWT cache | Kết quả xác thực token | Có thể bỏ qua expiry/revocation/policy nếu thiết kế sai |

Mục tiêu thường cần tối ưu là **JWK Set retrieval**, không phải tự cache toàn bộ JWT authentication.

### 9.1. JWK Set không phải JWT token

Một JWK Set có dạng:

~~~json
{
  "keys": [
    {
      "kty": "RSA",
      "kid": "key-2026-11",
      "use": "sig",
      "alg": "RS256",
      "n": "<base64url-modulus>",
      "e": "AQAB"
    }
  ]
}
~~~

Các giá trị `<base64url-modulus>` là ký hiệu minh họa, không phải JWK thực tế dùng được. JWKS chỉ nên chứa **public key material cần thiết**; không công bố private parameters như `d`, `p`, `q`.

JWK cache có thể giúp Resource Server giảm gọi JWKS endpoint khi nhiều JWT dùng cùng signing key. Dù JWKS đã được cache, **mỗi JWT vẫn phải được kiểm tra chữ ký và claims**.

### 9.2. Không nhầm TTL của Servlet với Reactive

Tài liệu Servlet `NimbusJwtDecoder` mô tả cache JWK Set in-memory mặc định **5 phút** trong những phiên bản được tài liệu hóa. Nhưng không thể lấy con số đó rồi khẳng định **mọi `NimbusReactiveJwtDecoder` trong mọi phiên bản cũng có chính xác cùng TTL**.

Builder `NimbusReactiveJwtDecoder.JwkSetUriReactiveJwtDecoderBuilder` của 6.5 và 7.1 **không có** `.cache(Cache)`; Reactively fetched key source có implementation và lifecycle riêng.

**Cách làm đúng:** xác minh behavior bằng Javadoc, source của dependency version được sử dụng và kiểm thử đếm số lần JWKS endpoint bị gọi. Không dựa vào giả định một cache API ở stack khác.

### 9.3. Vì sao không nên gọi `.cache(...)` trên Reactive builder?

Đoạn sau đúng về mặt **ý tưởng Servlet**:

~~~java
NimbusJwtDecoder.withJwkSetUri(jwkSetUri)
    .cache(cacheManager.getCache("jwks"))
    .build();
~~~

Nhưng không được đổi class thành `NimbusReactiveJwtDecoder` một cách máy móc:

~~~java
// SAI trên Reactive JWK Set builder 6.5/7.1.
NimbusReactiveJwtDecoder.withJwkSetUri(jwkSetUri)
    .cache(cacheManager.getCache("jwks"))
    .build();
~~~

Nếu cần TTL có thể cấu hình hoặc shared cache, phải **chọn một extension point được hỗ trợ của phiên bản Reactive** hoặc thiết kế cache bên ngoài key source với kiểm chứng đầy đủ; không gọi method không tồn tại.

## 10. Những lựa chọn cache JWKS cho WebFlux

### 10.1. Phương án A — Giữ cơ chế mặc định

Bắt đầu bằng:

~~~java
NimbusReactiveJwtDecoder decoder =
    NimbusReactiveJwtDecoder.withJwkSetUri(jwkSetUri)
        .webClient(jwkWebClient)
        .build();
~~~

Sau đó đo:

- Số request tới JWKS endpoint khi tải bình thường.
- Mức tăng request sau restart/scale-out.
- Thời điểm JWKS được refetch.
- Hành vi khi token có `kid` mới xuất hiện.
- Hành vi khi JWKS tạm lỗi nhưng key cũ đã tải.
- Số request mạng song song khi nhiều request cần key mới.

Nhiều hệ thống không cần custom cache ngay. Cache sâu hơn tăng khả năng lỗi chính sách rotation và kéo dài cửa sổ tin khóa cũ.

### 10.2. Phương án B — HTTP layer/CDN hoặc JWK gateway được quản trị

Nếu AS ở xa, có thể triển khai endpoint JWKS nội bộ **đáng tin** (gateway/mirror) với caching được vận hành chính thức, sau đó Resource Server trỏ `jwk-set-uri` tới endpoint đó.

Điều kiện quan trọng:

1. Chỉ mirror JWKS từ đúng AS/issuer đã cấu hình.
2. HTTPS hoặc kênh được bảo vệ đúng giữa Resource Server và gateway.
3. Có TTL/invalidation phản ánh key rotation.
4. Có giới hạn size, schema và content type.
5. Không cho request headers/JWT `jku` điều khiển upstream URL.
6. Không biến gateway thành nơi tự phát hành khóa hay bỏ kiểm tra chữ ký.
7. Có test outage và rotation, không chỉ test cache hit.

Mô hình:

~~~text
Authorization Server JWKS (source of truth)
               |
               v
Trusted internal JWKS gateway/cache
               |
               v
Resource Server WebClient
               |
               v
NimbusReactiveJwtDecoder -> verify signature + claims
```

Một shared cache/gateway làm giảm số fetch trên nhiều instances nhưng **không thay thế** issuer/audience validators.

### 10.3. Phương án C — Custom reactive JWK source

`NimbusReactiveJwtDecoder` có extension point:

~~~java
NimbusReactiveJwtDecoder.withJwkSource(
    Function<SignedJWT, Flux<JWK>> source
)
~~~

Ý tưởng là cung cấp một nguồn khóa Reactive do ứng dụng quản trị. Đây là **API nâng cao**, không phải tiện ích cache TTL một dòng. Nếu triển khai phải bảo đảm:

- Chỉ lấy khóa từ issuer/JWK source được cấu hình tin cậy.
- Chọn khóa theo `kid`, `kty`, `alg`, `use`/`key_ops` phù hợp.
- Không cho token header chỉ định URL không được phê duyệt.
- Quản lý TTL, invalidation, refresh/unknown `kid` và retry.
- Đồng bộ các concurrent refresh để tránh thundering herd.
- Xử lý failure theo fail closed.
- Giới hạn kích thước JWK Set và số khóa để tránh resource exhaustion.
- Duy trì validation chữ ký và issuer/audience/token type.

**Không** dùng sample custom `withJwkSource(jwt -> Flux.just(attackerKey))` trong production. Nếu nguồn khóa trả sai hoặc thiếu context, Resource Server có thể chấp nhận sai issuer hoặc gặp outage khi rotation.

### 10.4. Phương án D — Dùng Spring Cache trong một lớp tự xây

Spring Cache/Redis/Caffeine có thể dùng trong **một key retrieval layer do ứng dụng kiểm soát**, nhưng đây không phải native `.cache(Cache)` trên Reactive Nimbus builder.

Khi sử dụng, cần định nghĩa:

~~~text
Cache key   = trusted issuer + configured jwkSetUri
Cache value = validated JWKS public-key data
TTL         = rotation policy + upper bound được phê duyệt
```

Không lấy cache key từ một `kid` đơn lẻ nếu namespace issuer chưa được ràng buộc. Không cache allow decision/JWT authentication như cách thay verification. Nếu một cache miss và AS unreachable, **không** chấp nhận token chưa được kiểm tra chữ ký.

### 10.5. Nên chọn phương án nào?

| Nhu cầu | Lựa chọn ưu tiên |
|---|---|
| Đa số API, JWKS ít thay đổi | Giữ decoder/cache mặc định, đo behavior |
| Cần giới hạn network timeout | Tùy chỉnh `.webClient(...)` |
| AS nằm xa, nhiều Resource Server replicas | Trusted JWKS gateway/mirror nếu phù hợp |
| Bắt buộc TTL/refresh custom | Extension key source phù hợp version, test cẩn thận |
| Chỉ muốn tránh verify chữ ký cho từng JWT | **Không nên** cache decoded JWT như shortcut |
| Muốn dùng `.cache(Cache)` ở WebFlux builder | **Không có method này ở 6.5/7.1** |
| JWKS tạm unavailable | Phải fail closed cho token không có key đáng tin |

## 11. Key rotation, `kid` mới và cache refresh

Một AS có thể luân chuyển khóa:

~~~text
T0: JWKS có key-A
    JWT-A ký bằng key-A -> Resource Server verify thành công

T1: AS công bố key-A + key-B
    Cache có thể vẫn chỉ thấy key-A

T2: AS phát JWT-B với kid=key-B
    Resource Server cần tìm/cập nhật JWK Set

T3: AS ngừng phát JWT-A, giữ key-A trong JWKS thêm một khoảng
    để JWT-A chưa hết hạn còn xác minh được

T4: Sau overlap window, AS mới bỏ key-A
~~~

Thực tế có thể khác tùy AS và token TTL, nhưng **overlap window giữa khóa cũ/mới** là mô hình key rotation thường giúp giảm gián đoạn.

### 11.1. Unknown `kid` không phải lý do tự tin một khóa mới

JWT header:

~~~json
{
  "alg": "RS256",
  "kid": "key-B",
  "typ": "at+jwt"
}
~~~

`kid` là **chỉ dẫn chọn khóa**, không phải bằng chứng khóa đó được AS cấp. Khi không tìm thấy key-B:

- Decoder có thể refetch JWKS theo behavior của version.
- Nếu JWKS có key-B đáng tin và signatures/validators đạt, token có thể hợp lệ.
- Nếu JWKS không có key phù hợp hoặc không tải được, phải từ chối.
- Không tải public key từ URL do JWT tự cung cấp để “tìm cho ra key”.

### 11.2. Cache TTL quá dài và quá ngắn

**TTL quá dài:**

- Có thể chậm nhận key mới, gây 401 trong rotation.
- Có thể tiếp tục tin khóa cũ sau thời điểm AS đã loại bỏ theo chính sách.
- Dễ tạo dependency vào manual cache eviction.

**TTL quá ngắn:**

- Tăng network fetch tới AS/gateway.
- Tạo load spike khi nhiều replicas restart/refetch cùng lúc.
- Làm latency của request phụ thuộc mạng nhiều hơn.
- Mở rộng blast radius của AS outage.

Không có TTL lý tưởng chung. Phải kết hợp AS rotation policy, JWT TTL, SLO và số replicas.

### 11.3. Stale-while-revalidate và outage tolerance

Một số cache gateway hỗ trợ phục vụ dữ liệu stale trong outage. Điều này chỉ nên được dùng nếu **security policy cho phép** và có giới hạn rõ:

- Khóa stale vẫn phải là khóa từ source đáng tin.
- Có upper bound về tuổi của JWKS.
- Không bỏ qua signature validation.
- Không mặc định refresh fail rồi allow token với key chưa biết.
- Cần audit/recovery, test trường hợp key compromise.

Không biến “JWKS unavailable” thành “bất kỳ JWT có `alg=RS256` đều hợp lệ”.

## 12. Không cache JWT verification tùy tiện

Một tối ưu tưởng dễ làm:

~~~text
Cache key: raw JWT
Cache value: authentication đã được cho phép
TTL: 1 giờ
```

có thể sai nếu:

- JWT hết hạn trước TTL.
- Token bị thu hồi và API có denylist/policy cần kiểm tra.
- Issuer/audience hoặc allowed algorithm configuration thay đổi.
- Role/membership thay đổi trong thời gian cache.
- Token quá lớn làm cache key chứa credential nhạy cảm.
- Cache response/trace vô tình ghi JWT ra log.

Khi dùng JWT, nguồn public key được cache đủ để tránh network call mỗi request; phần verify chữ ký và claims vẫn nên thực thi theo security pipeline của request.

Nếu một hệ thống có thiết kế session/token cache đặc biệt, đó là **thay đổi threat model** cần review riêng, không phải cách tùy chỉnh JWK cache mặc định.

## 13. Bảo vệ algorithm và token type khi đổi builder

Theo tài liệu Spring Security, mặc định `NimbusReactiveJwtDecoder` thường chỉ tin `RS256` trong cấu hình cơ bản. Có thể mở thêm khi AS contract yêu cầu, chẳng hạn:

~~~java
NimbusReactiveJwtDecoder decoder =
    NimbusReactiveJwtDecoder.withJwkSetUri(jwkSetUri)
        .webClient(jwkWebClient)
        .jwsAlgorithm(SignatureAlgorithm.RS512)
        .build();
~~~

Cần import:

~~~java
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
~~~

Nếu hệ thống chỉ phát RS256 thì **không thêm RS512, ES256 hay mọi alg chỉ để thử**. Allowed algorithms phải là allowlist hợp đồng, không dựa vào giá trị JWT header mà client gửi.

### 13.1. `alg=none` và algorithm confusion

Không được chấp nhận JWT không ký hoặc tự thay verification bằng cách parse claim mà không xác minh:

~~~text
Header {"alg":"none"} + payload {"scope":"admin"} -> KHÔNG HỢP LỆ
```

Tương tự, không chuyển nhầm giữa HMAC shared secret và RSA public key theo lựa chọn `alg` do token yêu cầu. Để Nimbus decoder xử lý JWS theo policy đã cấu hình.

### 13.2. `validateType(boolean)` là API có mốc phiên bản

Builder Reactive từ Spring Security **6.5** có:

~~~java
.validateType(boolean)
~~~

Nó điều chỉnh kiểm tra `typ` header của Nimbus. Không gọi method này trên version chưa có.

Quan trọng hơn, **không đặt `.validateType(false)` để chấp nhận mọi token type**. Khi tắt type verifier ở Nimbus, ứng dụng phải có validator type/profile tương đương thích hợp, ví dụ kiểm tra JWT access-token profile (RFC 9068) khi API yêu cầu `at+jwt`.

Nếu ứng dụng nhận OIDC ID token thay access token chỉ vì JWT có chữ ký hợp lệ, có nguy cơ **cross-token confusion**. Đặt đúng validators `iss`, `aud`, `exp`, `nbf`, `typ`/token profile và client context theo hợp đồng.

### 13.3. Dùng validators không được xóa defaults

Ví dụ sai:

~~~java
// SAI: thay tất cả validators bằng kiểm tra audience duy nhất.
decoder.setJwtValidator(myAudienceOnlyValidator);
~~~

Khi đó những kiểm tra issuer/time có thể không còn như kỳ vọng.

Ví dụ an toàn về ý tưởng:

~~~java
decoder.setJwtValidator(
    new DelegatingOAuth2TokenValidator<>(
        JwtValidators.createDefaultWithIssuer(issuer),
        audienceValidator
    )
);
~~~

Nếu dự án dùng validator riêng theo RFC 9068/token type, cần tích hợp nó theo API đúng version; không tự giả định `JwtValidators.createDefaultWithIssuer(...)` bao phủ mọi profile.

## 14. Mặc định Boot property có thay đổi WebClient này không?

Spring Boot cung cấp properties như:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: ...
          jwk-set-uri: ...
          jws-algorithms: RS256
~~~

Nhưng một bean:

~~~java
@Bean
ReactiveJwtDecoder customDecoder() { ... }
~~~

thường **thay thế auto-configured decoder**. Điều đó nghĩa `issuer-uri`, audience và JWS algorithm ở Boot properties không nhất thiết được tự động áp lại vào bean tùy chỉnh.

**Cách chắc chắn:** khi viết custom bean, lấy các giá trị cần thiết và cấu hình chúng **tường minh** ở builder/validator, hoặc sử dụng một cách tùy chỉnh không thay decoder nếu phù hợp.

### 14.1. Chỉ định một decoder rõ ràng

Có hai cách phổ biến:

**Bean:**

~~~java
@Bean
ReactiveJwtDecoder reactiveJwtDecoder() {
    return NimbusReactiveJwtDecoder.withJwkSetUri(jwkSetUri)
        .webClient(jwkWebClient)
        .build();
}
~~~

**Gắn trực tiếp vào DSL:**

~~~java
.oauth2ResourceServer(oauth2 -> oauth2
    .jwt(jwt -> jwt.decoder(myReactiveJwtDecoder)))
~~~

Nếu dùng cả hai ở nhiều places/chains, cần biết **decoder nào thực sự được chọn**. Một chain có thể override bean khác với chain còn lại.

**Không tạo hai bean cùng type rồi xem injection ambiguity là việc không quan trọng**: một Resource Server có thể vô tình dùng decoder sai issuer/JWKS trong môi trường nhiều issuers.

### 14.2. Multi-issuer/tenant và caches

Với nhiều issuers, mỗi issuer cần:

- Allowlist issuer URLs đáng tin.
- Public JWK source phù hợp.
- Validators `iss`/`aud` riêng.
- Cache key không va chạm giữa issuers.
- Policy role/scope đúng issuer.
- Không cho token chưa xác minh điều khiển arbitrary JWKS URI.

Một custom reactive resolver chọn issuer phải theo contract/trust registry, không chỉ lấy `iss` chưa được verify rồi gọi bất kỳ URL nào trên Internet.

## 15. Retry/backoff: dùng thận trọng

Một network call tới JWKS có thể thất bại tạm thời. Retry có thể hữu ích nếu lỗi thật sự transient, nhưng không nên áp dụng mặc định một policy aggressive:

~~~text
1000 requests gặp unknown kid
   |
   +-- mỗi request tự retry 5 lần
   |
   +-- 5000 requests tới JWKS ngay khi AS đang lỗi
```

Đây có thể là **retry storm/thundering herd**.

Những nguyên tắc:

- Retry chỉ một số lỗi kết nối/5xx theo policy, không retry JWT invalid signature.
- Giới hạn số lần, tổng deadline và mức concurrency.
- Có exponential backoff/jitter nếu cần.
- Không retry vô hạn.
- Đặt circuit breaker/metrics cho source mạng.
- Sử dụng single-flight cache refresh nếu key source/gateway hỗ trợ.
- Không chuyển lỗi lấy khóa thành token được chấp nhận.

Một WebClient filter tự retry mọi GET có thể làm cả metadata và JWKS calls bị retry nhiều hơn dự kiến. Nếu không chắc builder gọi khi nào, **đo network behavior trong integration test** trước khi thêm retry.

## 16. Những metrics cần theo dõi

Không chỉ nhìn latency chung của API. Với JWT/JWKS, nên phân biệt:

| Metric/sự kiện | Ý nghĩa |
|---|---|
| `jwks_fetch_requests` | Tần suất tải khóa từ AS |
| `jwks_fetch_duration` | p50/p95/p99 latency network |
| `jwks_fetch_failure` | DNS, connect, TLS, HTTP 4xx/5xx, parse lỗi |
| `jwks_cache_hit` nếu instrumentation hỗ trợ | Bao nhiêu lần dùng khóa đã có |
| `jwks_refresh` | Rotation/refresh frequency |
| `jwt_invalid_signature` | Token có chữ ký sai |
| `jwt_unknown_kid` | Thiếu khóa tương ứng (có thể rotation hoặc attack) |
| `jwt_invalid_issuer` | Issuer mismatch |
| `jwt_invalid_audience` | Token không dành cho API |
| `jwt_expired` | Token hết hạn |
| `authentication_401` | Request không được xác thực |
| `authorization_403` | Principal hợp lệ thiếu quyền nghiệp vụ |

Tên metric cụ thể tùy Micrometer/observability library và custom instrumentation; bảng trên là **gợi ý phân loại**, không khẳng định Spring Security tự phát mọi metric như vậy.

### 16.1. Không log JWT hoặc private keys

Không ghi:

- Raw `Authorization: Bearer ...`.
- Full JWT payload chứa PII.
- Private JWK parameters (`d`, `p`, `q`, ...).
- Full HTTP TLS headers/credentials của proxy.
- Client secrets, private cert keys.
- JWKS JSON ở log public nếu môi trường yêu cầu hạn chế.

Có thể log issuer ID đã được cấu hình, JWK Set endpoint identifier, `kid` ở mức hạn chế, HTTP status, duration, trace ID và loại lỗi, nhưng vẫn cần chính sách chống rò dữ liệu.

## 17. Thử nghiệm bằng JWKS server giả lập

Để xác minh timeout và cache, nên dùng một JWKS HTTP server **test-only**, không gọi AS production liên tục. Các lựa chọn như WireMock hoặc MockWebServer có thể được dùng nếu dự án đã có dependency tương ứng.

### 17.1. Bộ dữ liệu test tối thiểu

Tạo một cặp RSA key cho test:

~~~text
Private key: chỉ ở test fixture để ký JWT test
Public JWK:  xuất ra JWKS response
kid:        key-A
```

JWKS response:

~~~json
{
  "keys": [
    {
      "kty": "RSA",
      "kid": "key-A",
      "use": "sig",
      "alg": "RS256",
      "n": "<test-modulus>",
      "e": "AQAB"
    }
  ]
}
~~~

Đây là JSON minh họa, không chứa giá trị khóa RSA thật; test thực phải sinh key hợp lệ. Không bao giờ đưa private key vào JWKS response.

JWT test:

~~~json
{
  "iss": "https://idp.test.example/realms/shop",
  "sub": "user-42",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "exp": 2000000300
}
~~~

Token phải được **ký bằng private key tương ứng với public JWK**. Trường `exp` ví dụ chỉ mang ý nghĩa minh họa; integration test thực nên đặt thời gian tương ứng `Clock` của test để không quá hạn.

### 17.2. Ma trận test JWKS/network/cache

| Case | Setup | Kỳ vọng |
|---|---|---|
| JWKS bình thường | Server trả public JWK đúng | Token ký bằng key tương ứng được xác minh |
| JWT signature sai | Cùng claims, chữ ký không đúng | Reject |
| JWT issuer sai | Chữ ký đúng, `iss` khác | Reject |
| JWT audience sai | Chữ ký đúng, `aud` không phải API | Reject |
| JWT hết hạn | `exp` ở quá khứ | Reject |
| JWKS 404 | Key endpoint không có | Reject token cần key, báo lỗi nguồn khóa |
| JWKS 500 | AS bị lỗi | Không accept token không thể verify |
| Connect timeout | Server không thể kết nối | Không treo vô hạn, không fail open |
| Response timeout | Server accept nhưng không trả dữ liệu | Không treo vô hạn |
| JWKS JSON sai | Body không parse được | Reject |
| JWKS quá lớn | Vượt buffer size hoặc schema limits | Không tiêu thụ tài nguyên vô hạn |
| Cache warm | Token lặp với key đã có | Đo số lần server được gọi |
| Key rotation | Thêm `key-B` rồi phát JWT-B | Quan sát refresh theo version |
| Unknown `kid` | JWT chứa key không được phép | Reject |
| Nhiều concurrent refresh | Burst request cùng thời điểm | Không tạo fetch storm nếu cache/gateway được thiết kế |
| Issuer discovery lỗi | Metadata 404/timeout | Không chấp nhận token tùy tiện |
| Proxy/TLS sai | Chứng thư không đáng tin | Fail closed |
| 2 issuers cùng `kid` | Public keys khác nhau | Không nhầm cache/issuer |

**Quan trọng:** tập kiểm thử cache cần **đếm request HTTP thực tế** tới stub JWKS server. Đừng chỉ đo số lần gọi `decoder.decode()` rồi kết luận cache hit; decoder luôn được gọi khi request cần authenticate.

### 17.3. Test decode không thay bằng `mockJwt()`

`WebTestClient` với Spring Security Test có `mockJwt()`:

~~~java
webTestClient.mutateWith(
    mockJwt().authorities(
        new SimpleGrantedAuthority("SCOPE_orders.read")
    ))
    .get()
    .uri("/api/orders")
    .exchange()
    .expectStatus().isOk();
~~~

Đây là **authorization mock**; nó có thể **bỏ qua hoàn toàn ReactiveJwtDecoder**, do đó không test `WebClient`, timeout, JWKS cache, signature hay issuer validators.

Để test network/cache phải dùng JWT ký thật bằng test key và cho request đi qua `ReactiveJwtDecoder` thực với JWKS server giả lập.

### 17.4. Dùng Reactor `StepVerifier` khi test decoder

Một cách test decoder riêng lẻ:

~~~java
// signedJwt: JWT test thực sự được ký bằng private test key.
// decoder: ReactiveJwtDecoder trỏ tới JWKS server test.
StepVerifier.create(decoder.decode(signedJwt))
    .expectNextMatches(jwt ->
        "user-42".equals(jwt.getSubject()))
    .verifyComplete();
~~~

Với token sai:

~~~java
StepVerifier.create(decoder.decode(invalidSignatureJwt))
    .expectError(JwtException.class)
    .verify();
~~~

Các biến `signedJwt`, `invalidSignatureJwt` và `decoder` là test fixture do người viết test cung cấp; cần imports `reactor.test.StepVerifier` và `org.springframework.security.oauth2.jwt.JwtException`. Điều kiện mong đợi error class có thể cần điều chỉnh theo exception wrapping của phiên bản đang dùng.

Không biến một fake decoder kiểu `token -> Mono.just(anyJwt)` thành “signature test”: nó không thực hiện JWS verification.

## 18. Những lỗi phổ biến khi nâng version

### 18.1. Code `.cache(...)` không biên dịch

~~~text
Cannot resolve method 'cache' in
NimbusReactiveJwtDecoder.JwkSetUriReactiveJwtDecoderBuilder
```

Nguyên nhân thường là copy từ tài liệu **Servlet `NimbusJwtDecoder`**. Giải pháp: đọc Javadoc của Reactive builder đúng version, dùng cơ chế cache mặc định hoặc extension key source phù hợp.

### 18.2. Code `.restOperations(...)` không biên dịch

~~~text
Cannot resolve method 'restOperations'
```

Nguyên nhân: builder Reactive sử dụng **`.webClient(...)`** thay vì `RestOperations`.

### 18.3. `withIssuerLocation(...)` không có

Dự án có thể dùng Spring Security **trước mốc 6.1**. Kiểm tra BOM/dependency; có thể dùng `withJwkSetUri(...)` hoặc `ReactiveJwtDecoders.fromIssuerLocation(...)` theo API thực tế. Đừng sửa bằng cách tự parse metadata thủ công nếu không cần.

### 18.4. `validateType(...)` không có

Method xuất hiện trong Javadoc dòng **6.5+**. Với version cũ, cần cấu hình token type/validators qua API được hỗ trợ hoặc cân nhắc nâng version theo quy trình dự án.

### 18.5. Bean custom làm issuer validation biến mất

Triệu chứng: token từ issuer khác được chấp nhận dù chữ ký đúng, hoặc behavior không giống Boot property.

Nguyên nhân: tự khai báo `ReactiveJwtDecoder` rồi quên:

~~~java
decoder.setJwtValidator(
    JwtValidators.createDefaultWithIssuer(issuer)
);
~~~

Đây chỉ là một phần của validation contract; cần audience/token-type policy thêm khi API yêu cầu.

### 18.6. Config timeout không tác dụng

Kiểm tra:

- WebClient custom có thực sự gắn vào `NimbusReactiveJwtDecoder` bằng `.webClient(...)` không?
- Bean decoder custom có được SecurityWebFilterChain chọn không?
- Một chain khác có decoder riêng không?
- Network call thực tế tới issuer discovery hay JWKS?
- Có proxy/gateway che timeout?
- Timeout đang chờ DNS, TLS, connect, response hay cache?
- Có retry làm tăng tổng thời gian không?
- Request đang dùng key cache nên không gọi mạng và timeout không có cơ hội tác động?

### 18.7. Startup thành công nhưng request đầu tiên thất bại

Khi issuer discovery/khởi tạo decoder được trì hoãn, ứng dụng có thể start được dù AS đang lỗi. Request đầu tiên cần JWKS có thể bị 401 hoặc lỗi authentication/network tùy handler. Đây là hệ quả của deferred network dependency.

Cần phân biệt **startup readiness** với **khả năng xác minh token ở request đầu**. Nếu hệ thống có readiness check cho khả năng xác minh JWT, hãy thiết kế nó có giới hạn và không để mọi liveness check phụ thuộc AS.

### 18.8. Key rotation gây 401 từng đợt

Nếu `kid` mới được AS sử dụng trước khi Resource Server cập nhật key source, một số request JWT mới có thể bị từ chối.

Kiểm tra JWKS publication timeline, token `kid`, cache refresh behavior, AS overlap window và egress. Đừng tắt signature validation để xử lý rotation.

### 18.9. Connection pool bị cạn

Nếu decoder phải liên tục fetch JWKS trong outage hoặc nhiều concurrent requests, `WebClient` connection pool có thể quá tải. Giải pháp có thể gồm cache, request coalescing, concurrency limits và retry budgets; không chỉ tăng pool vô hạn.

### 18.10. Cấu hình WebClient dùng global Authorization header

Nếu HTTP client được dùng chung và tự gắn bearer token user vào mọi outgoing request, JWKS endpoint có thể nhận credential không cần thiết. Tách WebClient riêng cho JWKS.

## 19. 401, 403 và 5xx khi JWKS gặp sự cố

| Trường hợp | Kết quả điển hình | Lớp xử lý |
|---|---|---|
| Không có bearer token tới private API | 401 | Chưa authentication |
| JWT signature sai | 401 | Crypto verification |
| Token hết hạn | 401 | JWT timestamp |
| Issuer hoặc audience không đúng | 401 | JWT claims validation |
| JWT hợp lệ nhưng thiếu scope | 403 | Authorization |
| Token cần public key chưa có và JWKS unavailable | Không authenticate; status tùy handler/config | Key retrieval/authentication dependency |
| AS trả JWKS JSON sai | Không authenticate; lỗi key source | JWKS parsing |
| `kid` lạ không tồn tại | Không authenticate | Key selection |
| Redis cache/Gateway JWKS lỗi | Không tự allow; xử lý dependency outage | Infrastructure |
| Browser CORS preflight lỗi | Có thể báo CORS error | Không phải JWT key retrieval |

Cần ghi nhận loại lỗi trong observability. Một số authentication failures trả 401; các outage upstream có thể được map thành 5xx/503 tùy thiết kế. **Đừng khẳng định mọi sự cố JWKS luôn là 401 hoặc luôn là 503 nếu chưa kiểm tra exception handling thực tế**.

Quan trọng hơn status code là tính chất **fail closed**: khi không chứng minh được token được ký bởi nguồn đáng tin, hành động nghiệp vụ không được tiếp tục.

## 20. Bảo vệ resource-level authorization sau khi JWT decode

Ngay cả khi WebClient lấy được JWK đúng và JWT có:

~~~json
{
  "iss": "https://idp.example.com/realms/shop",
  "sub": "user-42",
  "aud": ["orders-api"],
  "scope": "orders.read"
}
~~~

thì `SCOPE_orders.read` chỉ chứng minh access token được AS cấp scope đọc theo contract. Nó **không tự** chứng minh user 42 được xem mọi order của tenant khác.

Một service vẫn phải kiểm tra:

~~~text
Authenticated JWT
  AND SCOPE_orders.read
  AND subject thuộc tenant được yêu cầu
  AND order thực sự thuộc tenant đó
  AND owner/ACL policy cho phép
```

Thay đổi timeout/cache ở tầng JWKS **không được đổi ngữ nghĩa của những quyền này**.

## 21. Chẩn đoán có hệ thống trước khi chỉnh code

Khi gặp thông báo “JWT verification thỉnh thoảng chậm”:

**Bước 1 — Xác định có phải JWKS fetch không.** Kiểm tra telemetry outbound HTTP tới issuer/JWKS, thay vì giả định mọi JWT decode phải gọi mạng.

**Bước 2 — Xác định đang dùng JWT hay opaque token.** Nếu hệ thống dùng introspection, `NimbusReactiveJwtDecoder` không phải thành phần chính cần chỉnh.

**Bước 3 — Xác định stack.** WebFlux phải là `ReactiveJwtDecoder`/`WebClient`, không phải `JwtDecoder`/`RestTemplate`.

**Bước 4 — Xác định version.** Xem effective dependency versions/BOM trong workflow dự án (không phải dựa trên blog mới nhất).

**Bước 5 — Xác định loại network delay.** DNS, TCP connect, TLS, response, redirect hay retry?

**Bước 6 — Xác định URI nguồn khóa.** Discovery metadata đang đúng không? Có reverse proxy rewrite sai không? URI nội bộ có được server cấu hình tin cậy không?

**Bước 7 — Kiểm tra cache và rotation.** JWKS có bị fetch mỗi request hay sau một khoảng? `kid` mới được AS phát lúc nào?

**Bước 8 — Thay đổi WebClient giới hạn.** Đặt timeout/connector riêng, không tắt validators.

**Bước 9 — Chạy test stub JWKS.** Validate signature và đo network fetch ở các case cold/warm/rotation/outage.

**Bước 10 — Theo dõi sau deploy.** 401/403, fetch failures, latency p99, connection pool và AS load.

Không chỉnh cả timeout, retry, caching, algorithms và issuer cùng một lúc rồi khó xác định thành phần gây lỗi.

## 22. Những hiểu nhầm cần tránh

**“WebFlux JWT Resource Server cần gọi Authorization Server ở mọi request.”** Không mặc định. Sau khi có public keys phù hợp, JWT có thể được xác minh cục bộ; network phụ thuộc key source/cache/rotation.

**“`.cache(Cache)` tồn tại trên mọi Nimbus JWT builder.”** Sai. API Servlet và Reactive khác nhau; Reactive JWK Set URI builder 6.5/7.1 không có method đó.

**“Cứ copy cấu hình `RestTemplateBuilder` từ MVC là dùng được trong WebFlux.”** Sai. Reactive builder dùng `WebClient`.

**“WebClient timeout quyết định JWT hết hạn hay chưa.”** Sai. HTTP timeout khác `exp`/`nbf` validation.

**“Đặt responseTimeout 3 giây nghĩa toàn bộ decode tối đa 3 giây.”** Không nhất thiết; còn discovery, DNS, connect, TLS, retries, parsing và các tầng khác.

**“Cache JWKS nghĩa không còn cần verify chữ ký mỗi request.”** Sai. Cache public key không phải cache kết quả xác thực.

**“Cache JWKS 5 phút là mặc định chính xác cho mọi Reactive version.”** Không được giả định từ tài liệu Servlet.

**“JWKS endpoint đang lỗi thì cho phép JWT tạm để API không downtime.”** Sai. Không có bằng chứng khóa đáng tin thì không được xác thực.

**“JWT header `jku` hoặc `kid` là nguồn đủ tin để tải khóa.”** Sai. JWT header do client kiểm soát cho tới khi được xác minh; nguồn JWKS phải được cấu hình/allowlist.

**“Chỉ kiểm tra signature là đủ.”** Sai. Cần issuer, audience, time và token profile/algorithms theo contract.

**“Tự khai báo decoder bean nhưng Boot vẫn tự áp mọi property JWT.”** Không được mặc định; custom bean có thể override auto-configuration.

**“`withIssuerLocation` có trên tất cả Spring Security 5.x.”** Sai. Theo Javadoc, Reactive builder có method đó từ 6.1.

**“`validateType(false)` là cách dễ dàng nhận mọi access token.”** Nguy hiểm nếu không thay bằng validator type/profile phù hợp.

**“Không thấy request JWKS trong log là decoder không hoạt động.”** Không nhất thiết; có thể dùng cache.

**“JWKS public keys nên được lưu cùng private signing keys.”** Không. Resource Server chỉ cần public keys; private keys phải ở AS/Signing service an toàn.

**“MockMvc/`WebTestClient.mockJwt()` chứng minh timeout và JWKS cache hoạt động.”** Không. Mock JWT authentication thường không gọi decoder thật.

## 23. Câu hỏi tự kiểm tra

**1.** `NimbusReactiveJwtDecoder` thuộc WebFlux hay Servlet stack?

> Reactive/WebFlux. Nó triển khai `ReactiveJwtDecoder`.

**2.** Builder Reactive có method gì để tùy chỉnh HTTP client truy xuất JWKS?

> `.webClient(WebClient)`.

**3.** Có thể dùng `.restOperations(RestTemplate)` cho `NimbusReactiveJwtDecoder` như MVC không?

> Không trên JWK Set URI Reactive builder. Đó là pattern của Servlet decoder.

**4.** Có thể dùng `.cache(Cache)` trực tiếp trên Reactive builder Spring Security 6.5/7.1 không?

> Không. Phải chọn cơ chế mặc định hoặc extension cache/key source phù hợp version.

**5.** `issuer-uri` khác `jwk-set-uri` ở đâu?

> Issuer xác định nguồn phát hành token phải được tin; JWK Set URI là nơi lấy public keys. Có thể khác hostname nhưng phải giữ validation issuer đúng.

**6.** Vì sao nên dùng WebClient riêng cho JWKS?

> Để kiểm soát timeout/TLS/proxy và tránh gắn nhầm bearer token/headers nhạy cảm từ outgoing client dùng chung.

**7.** `CONNECT_TIMEOUT_MILLIS` và `responseTimeout` có giống nhau không?

> Không. Một cái giới hạn kết nối TCP, cái kia áp dụng chính sách chờ response. Tổng request có thể chịu thêm DNS/TLS/retry.

**8.** Nếu JWKS URL trả 404 hoặc timeout mà token có `kid` mới, có nên cho phép token không?

> Không. Không có public key đáng tin để kiểm tra chữ ký thì không thể xác thực token.

**9.** `SupplierReactiveJwtDecoder` có ích gì?

> Lazy initialize delegate decoder, giúp bảo toàn khả năng trì hoãn discovery khi tự cấu hình bean; không bảo đảm request đầu tiên thành công nếu AS outage.

**10.** Vì sao không cache kết quả “JWT này hợp lệ” vô thời hạn?

> Vì expiry, revocation/policy changes và validation profile có thể thay đổi; cache public keys khác cache authenticated principal.

**11.** Tại sao key rotation cần overlap window?

> Để Resource Server có thời gian thấy key mới trong khi token cũ đã phát vẫn có thể được xác minh cho tới khi hết hạn theo chính sách.

**12.** Thấy unknown `kid` thì lấy khóa từ `jku` trong JWT header có đúng không?

> Không mặc định. JWK source phải được server cấu hình và allowlist, không dùng URL do untrusted token chỉ định.

**13.** Đã có custom decoder với `WebClient`, vì sao còn phải gọi `setJwtValidator(...)`?

> Vì khi tự khai báo decoder bean, không được giả định Boot còn tự áp issuer/audience/token-type validators. Cần bảo đảm validation contract.

**14.** Vì sao `mockJwt()` không đủ để kiểm thử cache JWKS?

> Vì nó mock authentication và thường bỏ qua network JWKS cùng decoder; phải dùng JWT ký thật, decoder thật và mock JWKS endpoint đếm request.

**15.** Thay đổi WebClient timeout có khiến một token thiếu `SCOPE_orders.write` được gọi POST không?

> Không. Network key retrieval và HTTP authorization là hai lớp độc lập.

## 24. Tài liệu tham khảo

- [Spring Security — Reactive OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html): issuer discovery, JWKS, ReactiveJwtDecoder, trusted algorithms và validators.
- [Spring Security 6.5 — Reactive JWT](https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/resource-server/jwt.html): đối chiếu code và API ở nhánh 6.5.
- [Spring Security — NimbusReactiveJwtDecoder API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/jwt/NimbusReactiveJwtDecoder.html): `withJwkSetUri`, `withIssuerLocation`, `withJwkSource`, `setJwtValidator`.
- [Spring Security — JwkSetUriReactiveJwtDecoderBuilder API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/jwt/NimbusReactiveJwtDecoder.JwkSetUriReactiveJwtDecoderBuilder.html): `webClient`, `jwsAlgorithm`, `validateType`, `build`; **không có `.cache(Cache)`**.
- [Spring Security 6.5 — Reactive JWK Set builder Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/jwt/NimbusReactiveJwtDecoder.JwkSetUriReactiveJwtDecoderBuilder.html): đối chiếu với Javadoc của 7.1.
- [Spring Security — SupplierReactiveJwtDecoder](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/jwt/SupplierReactiveJwtDecoder.html): khởi tạo decoder lazy.
- [Spring Security — Reactive JWK Source builder](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/jwt/NimbusReactiveJwtDecoder.JwkSourceReactiveJwtDecoderBuilder.html): extension chuyên sâu cho nguồn khóa Reactive.
- [Spring Security — Servlet JWT Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): so sánh `NimbusJwtDecoder`, `.restOperations(...)`, `.cache(...)`.
- [Spring Framework — WebClient Configuration](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-builder.html): `ReactorClientHttpConnector`, connect/response/read timeouts, codec buffer limits và resource management.
- [Reactor Netty — HTTP Client](https://projectreactor.io/docs/netty/release/reference/http-client.html): connection pooling, timeouts, TLS, proxy và Netty behavior.
- [Spring Security — WebFlux OAuth2](https://docs.spring.io/spring-security/reference/reactive/oauth2/): vai trò Resource Server và WebFlux security integration.
- [RFC 7517 — JSON Web Key](https://www.rfc-editor.org/rfc/rfc7517): JWK và JWK Set.
- [RFC 7519 — JSON Web Token](https://www.rfc-editor.org/rfc/rfc7519): `iss`, `aud`, `exp`, `nbf`.
- [RFC 8725 — JWT Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): tránh algorithm confusion, cross-JWT confusion và validation sai.
- [RFC 8414 — OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414): discovery metadata của Authorization Server.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): access-token JWT profile và audience.

**Kết luận:** Khi cần tùy chỉnh đường lấy public keys trong **WebFlux JWT Resource Server**, hãy bắt đầu từ `NimbusReactiveJwtDecoder.withJwkSetUri(...)` hoặc `withIssuerLocation(...)`, cấu hình HTTP client bằng **`.webClient(...)`** và đặt timeout ở Reactor Netty/WebClient. Đối với cache, **đừng sao chép `.cache(Cache)` của Servlet decoder sang Reactive builder**; xác định đúng version và nhu cầu rồi mới chọn cơ chế mặc định, trusted JWKS gateway hoặc key source tùy chỉnh. Dù tối ưu mạng thế nào, luôn giữ chữ ký, issuer, audience, expiry và token type validation, kiểm thử rotation/outage và **fail closed khi không lấy được khóa đáng tin**.
