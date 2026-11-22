# Phân biệt mock danh tính với kiểm chứng token thực tế qua toàn bộ chuỗi

Khi kiểm thử một ứng dụng **Spring Security WebFlux Resource Server**, có hai mục tiêu rất khác nhau:

- Kiểm tra một người gọi đã được xác thực có được phép thực hiện hành động hay không.
- Kiểm tra một Bearer access token thực sự có đi qua toàn bộ quá trình xác thực, từ HTTP header đến decoder hoặc introspection endpoint, rồi mới được cấp quyền hay không.

Spring Security Test cung cấp các helper như **jwt()**, **mockOpaqueToken()** và **mockUser()** để dựng danh tính thử nghiệm. Các helper này giúp kiểm thử authorization nhanh, nhưng chúng tạo Authentication trong ngữ cảnh bảo mật của request. Chúng **không mô phỏng toàn bộ quá trình xác minh token thực tế**.

Muốn kiểm chứng token thực tế, test phải gửi header Authorization: Bearer ... qua filter chain WebFlux và để Spring Security gọi ReactiveJwtDecoder hoặc ReactiveOpaqueTokenIntrospector. Muốn kiểm tra chữ ký, issuer, audience, thời hạn, JWKS hay HTTP introspection, cần dùng decoder/introspector thật với khóa, metadata hoặc HTTP test server phù hợp.

Bài học này phân biệt rõ các lớp kiểm thử, cách tạo JWT thử nghiệm với claims/authorities, cách dùng WebTestClient, và cách thiết kế test từ mock danh tính đến xác minh token end-to-end.

## 1. Hai mục tiêu kiểm thử khác nhau

Giả sử Orders API có endpoint:

~~~http
GET /api/orders/123 HTTP/1.1
Host: orders.example.com
Authorization: Bearer <access-token>
~~~

API chỉ cho phép caller có scope orders.read, đúng audience orders-api, và thuộc tenant sở hữu order.

Ta cần kiểm tra nhiều tầng:

1. HTTP request có Bearer token hay không?
2. Bearer token được trích xuất đúng không?
3. Token có phải JWT hoặc opaque token theo contract không?
4. JWT có chữ ký hợp lệ, đúng issuer, audience và thời hạn không; hoặc introspection có trả active=true không?
5. Authorities có được ánh xạ đúng từ claims không?
6. Caller có scope/role cần thiết không?
7. Caller có được truy cập đúng tenant/order không?

**Mock danh tính** thường bắt đầu từ bước 5 hoặc bước 6: test cung cấp một Authentication đã được dựng sẵn. **Kiểm chứng token thực tế** bắt đầu từ HTTP Bearer header và đi qua authentication mechanism của Resource Server.

~~~mermaid
flowchart TD
    A["WebTestClient request"] --> B["BearerTokenAuthenticationWebFilter"]
    B --> C["ReactiveAuthenticationManager"]
    C --> D{"Token strategy"}
    D --> E["ReactiveJwtDecoder"]
    D --> F["ReactiveOpaqueTokenIntrospector"]
    E --> G["Signature + issuer + time + audience/profile"]
    F --> H["Introspection active + claims"]
    G --> I["JwtAuthenticationConverter"]
    H --> J["Opaque principal + authorities"]
    I --> K["Reactive SecurityContext"]
    J --> K
    K --> L["Authorization rules / method security"]
    L --> M["Controller / service / repository"]
~~~

Với mockJwt() hoặc mockOpaqueToken(), test tạo danh tính ở tầng SecurityContext, nên các bước Bearer parsing, decoder/introspection HTTP và xác minh mật mã không được thực thi như trong sơ đồ trên.

## 2. Công cụ kiểm thử WebFlux

Ứng dụng cần dependency test:

~~~xml
<dependency>
    <groupId>org.springframework.security</groupId>
    <artifactId>spring-security-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

Nếu dùng Spring Boot dependency management, để Boot quản lý version của Spring Security Test đồng bộ với Spring Security runtime.

Các công cụ thường dùng:

| Công cụ | Vai trò |
| --- | --- |
| WebTestClient | Gửi HTTP request qua WebFlux application hoặc test server |
| SecurityMockServerConfigurers.mockJwt() | Dựng JWT Authentication cho test |
| SecurityMockServerConfigurers.mockOpaqueToken() | Dựng opaque-token Authentication cho test |
| SecurityMockServerConfigurers.mockUser() | Dựng user Authentication không cần JWT |
| ReactiveJwtDecoder | Xác minh JWT trong reactive Resource Server |
| ReactiveOpaqueTokenIntrospector | Xác minh opaque token bằng introspection trong reactive Resource Server |
| StepVerifier | Kiểm tra publisher, converter, validator hoặc reactive service độc lập |
| HTTP stub server | Kiểm tra discovery, JWKS hoặc introspection request/response thật |

Static imports thường dùng:

~~~java
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockJwt;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockOpaqueToken;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockUser;
~~~

Tên package và API cụ thể cần khớp với version spring-security-test trong dự án.

## 3. Cấu hình reactive Resource Server để kiểm thử

Ví dụ một API chỉ nhận JWT Bearer:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
class ApiSecurityConfiguration {

    @Bean
    SecurityWebFilterChain apiSecurity(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .pathMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyExchange().authenticated())
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()))
            .build();
    }
}
~~~

Đây là cấu hình minh họa cho API Bearer. Nếu ứng dụng cũng phục vụ browser session, CSRF và các route khác, hãy giữ policy riêng cho từng security chain hoặc matcher. Không tắt CSRF toàn ứng dụng chỉ để làm test API dễ chạy.

Controller:

~~~java
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
class OrderController {

    @GetMapping("/api/orders/{id}")
    OrderView get(
            @PathVariable String id,
            @AuthenticationPrincipal Jwt jwt) {
        return new OrderView(id, jwt.getSubject());
    }
}

record OrderView(String id, String requestedBy) {
}
~~~

Trong production, endpoint còn cần kiểm tra tenant/owner ở service/repository. Ví dụ controller trên chỉ minh họa cách lấy Jwt principal.

## 4. Dùng mockJwt() để kiểm tra authorization

Một test tối giản:

~~~java
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockJwt;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest
@AutoConfigureWebTestClient
class OrderAuthorizationTest {

    @Autowired
    WebTestClient webTestClient;

    @Test
    void readerCanGetOrder() {
        webTestClient
            .mutateWith(mockJwt())
            .get()
            .uri("/api/orders/123")
            .exchange()
            .expectStatus().isOk();
    }
}
~~~

mockJwt() dựng một JWT Authentication giả lập trong reactive security context cho request. Request vẫn được xử lý qua authorization rules của ứng dụng, vì vậy test có thể kiểm tra hasAuthority, hasRole, method security và controller behavior.

Không cần gửi chuỗi compact JWT hoặc cấu hình khóa để chạy test authorization này.

### Tùy chỉnh subject và claims

~~~java
webTestClient
    .mutateWith(mockJwt().jwt(jwt -> jwt
        .subject("user-42")
        .issuer("https://auth.example.com/realms/shop")
        .audience(List.of("orders-api"))
        .claim("scope", "orders.read")
        .claim("tenant_id", "tenant-a")))
    .get()
    .uri("/api/orders/123")
    .exchange()
    .expectStatus().isOk();
~~~

Các claim được đặt trực tiếp trên Jwt thử nghiệm:

| Claim | Mục đích trong test |
| --- | --- |
| sub | Subject/caller |
| iss | Issuer dùng trong logic ứng dụng |
| aud | Resource/API mà token hướng tới |
| scope hoặc scp | Quyền truy cập theo contract issuer |
| exp, nbf, iat | Timestamp nếu test code đọc chúng |
| client_id | OAuth client |
| tenant_id | Tenant context |
| roles, permissions | Quyền tùy chỉnh nếu converter hỗ trợ |

**Đặt claim exp quá khứ trong mockJwt() không tự kiểm tra token hết hạn.** Helper đã tạo Authentication; JWT decoder và timestamp validators không được gọi.

## 5. Tạo authorities trực tiếp với mockJwt()

Nếu mục tiêu chỉ là kiểm tra một rule authority, có thể chỉ định authorities trực tiếp:

~~~java
import org.springframework.security.core.authority.SimpleGrantedAuthority;

webTestClient
    .mutateWith(mockJwt().authorities(
        new SimpleGrantedAuthority("SCOPE_orders.read")))
    .get()
    .uri("/api/orders/123")
    .exchange()
    .expectStatus().isOk();
~~~

Đây là cách nhanh để kiểm tra:

- hasAuthority("SCOPE_orders.read").
- hasRole("ORDER_ADMIN") với authority ROLE_ORDER_ADMIN.
- Authorization manager tùy chỉnh.
- Method security dựa trên GrantedAuthority.

Tuy nhiên, khi truyền authorities trực tiếp, test **không kiểm tra claim-to-authority converter**. Một token có roles: ["ADMIN"] không tự trở thành ROLE_ADMIN trừ khi converter được cấu hình như vậy.

### Phân biệt hasRole và hasAuthority

~~~java
.hasRole("ADMIN")
~~~

thường kiểm tra authority ROLE_ADMIN do role prefix mặc định.

~~~java
.hasAuthority("ROLE_ADMIN")
~~~

so sánh chính xác với chuỗi ROLE_ADMIN.

Với scope:

~~~java
.hasAuthority("SCOPE_orders.read")
~~~

hãy tạo authority đúng prefix trong test hoặc khai báo claim scope để converter mặc định ánh xạ.

## 6. Dùng mockOpaqueToken() cho authorization của opaque principal

Nếu ứng dụng dùng opaque token:

~~~java
.oauth2ResourceServer(oauth2 ->
    oauth2.opaqueToken(Customizer.withDefaults()))
~~~

có thể dùng mockOpaqueToken() để dựng principal thử nghiệm:

~~~java
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockOpaqueToken;

webTestClient
    .mutateWith(mockOpaqueToken())
    .get()
    .uri("/api/orders/123")
    .exchange()
    .expectStatus().isOk();
~~~

Có thể tùy chỉnh attributes và authorities theo API của version đang dùng. Ví dụ khái niệm:

~~~java
webTestClient
    .mutateWith(mockOpaqueToken()
        .attributes(attributes -> {
            attributes.put("sub", "service-orders");
            attributes.put("tenant_id", "tenant-a");
        })
        .authorities(
            new SimpleGrantedAuthority("SCOPE_orders.read")))
    .get()
    .uri("/api/orders/123")
    .exchange()
    .expectStatus().isOk();
~~~

mockOpaqueToken() tạo Authentication/principal cho test. Nó **không gọi ReactiveOpaqueTokenIntrospector**, không gửi HTTP POST đến introspection endpoint và không kiểm tra active: true/false.

## 7. Dùng mockUser() khi test không phụ thuộc JWT

Không phải mọi test security đều cần Resource Server principal. Nếu một controller/service chỉ dựa trên authorities hoặc username:

~~~java
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockUser;

webTestClient
    .mutateWith(mockUser("alice").roles("ADMIN"))
    .get()
    .uri("/admin/dashboard")
    .exchange()
    .expectStatus().isOk();
~~~

mockUser() dựng một user Authentication. Nó hữu ích cho authorization rule chung, nhưng principal không phải Jwt và không có semantics của OAuth2 Resource Server.

Nếu controller nhận @AuthenticationPrincipal Jwt, hãy dùng mockJwt() hoặc test Bearer flow. Không dùng mockUser() rồi giả định controller sẽ nhận được JWT.

## 8. Phân biệt mock danh tính và Bearer token thực tế

Đây là điểm quan trọng nhất khi thiết kế test suite:

| Kiểm tra | mockJwt() / mockOpaqueToken() | Bearer header thật + decoder/introspector |
| --- | --- | --- |
| Có HTTP Bearer header được parse không? | Không | Có |
| Bearer filter xử lý token? | Không theo đường Bearer authentication thông thường | Có |
| ReactiveJwtDecoder được gọi? | Không | Có khi dùng JWT |
| ReactiveOpaqueTokenIntrospector được gọi? | Không | Có khi dùng opaque token |
| Chữ ký JWT được xác minh? | Không | Chỉ khi dùng decoder thật |
| Issuer/time/audience validator chạy? | Không | Chỉ khi dùng decoder/validators thật |
| HTTP introspection request được gửi? | Không | Chỉ khi dùng introspector HTTP thật |
| Authorization rules chạy? | Có | Có |
| Controller/method security chạy? | Có | Có |

Vì vậy, không nên dùng một test mockJwt() pass để kết luận “Resource Server đã xác minh access token đúng”. Test đó chứng minh policy authorization hoạt động với JWT principal đã dựng sẵn.

## 9. Kiểm tra Bearer filter với ReactiveJwtDecoder mock

Để kiểm tra đường đi thực của Bearer header mà không cần tạo khóa/chữ ký trong test đó, mock ReactiveJwtDecoder và gửi header:

~~~java
import static org.mockito.Mockito.when;

import java.time.Instant;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.reactive.server.WebTestClient;
import reactor.core.publisher.Mono;

@SpringBootTest
@AutoConfigureWebTestClient
class BearerPipelineTest {

    @Autowired
    WebTestClient webTestClient;

    @MockitoBean
    ReactiveJwtDecoder jwtDecoder;

    @Test
    void bearerHeaderIsPassedToReactiveDecoder() {
        Instant issuedAt = Instant.parse("2026-11-01T10:00:00Z");
        Jwt jwt = Jwt.withTokenValue("test-token")
            .header("alg", "RS256")
            .issuer("https://auth.example.com/realms/shop")
            .subject("user-42")
            .audience(List.of("orders-api"))
            .issuedAt(issuedAt)
            .expiresAt(issuedAt.plusSeconds(300))
            .claim("scope", "orders.read")
            .build();

        when(jwtDecoder.decode("test-token"))
            .thenReturn(Mono.just(jwt));

        webTestClient.get()
            .uri("/api/orders/123")
            .headers(headers -> headers.setBearerAuth("test-token"))
            .exchange()
            .expectStatus().isOk();
    }
}
~~~

Test này gửi Bearer header thật qua WebFlux security filter. Spring Security trích xuất token và gọi ReactiveJwtDecoder mock. Nhờ vậy có thể kiểm tra:

- Header Bearer được nhận.
- Reactive authentication manager gọi decoder.
- JWT authentication converter được áp dụng theo cấu hình.
- Authorization rules và controller chạy sau khi authentication thành công.

Nhưng decoder mock chỉ trả Jwt do test chỉ định. **Test này không xác minh chữ ký, JWKS, issuer, audience hoặc expiry bằng mật mã/validators thật.**

Ở Spring Framework mới có thể dùng @MockitoBean; các dự án Spring Boot cũ hơn thường dùng @MockBean. Chọn annotation theo dependency đang dùng.

### Token sai trong test decoder mock

~~~java
when(jwtDecoder.decode("bad-token"))
    .thenReturn(Mono.error(new JwtException("Invalid JWT")));

webTestClient.get()
    .uri("/api/orders/123")
    .headers(headers -> headers.setBearerAuth("bad-token"))
    .exchange()
    .expectStatus().isUnauthorized();
~~~

Đây là test nhánh decoder báo lỗi và HTTP authentication entry point trả 401. Nó không chứng minh một chữ ký cụ thể sai; decoder mock đã được lập trình để phát lỗi.

## 10. Kiểm tra opaque Bearer pipeline với ReactiveOpaqueTokenIntrospector mock

Với opaque token, gửi Bearer header và mock introspector:

~~~java
import static org.mockito.Mockito.when;

import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.core.DefaultOAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.introspection.ReactiveOpaqueTokenIntrospector;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.reactive.server.WebTestClient;
import reactor.core.publisher.Mono;

@SpringBootTest
@AutoConfigureWebTestClient
class OpaqueBearerPipelineTest {

    @Autowired
    WebTestClient webTestClient;

    @MockitoBean
    ReactiveOpaqueTokenIntrospector introspector;

    @Test
    void activeTokenIsConvertedToAuthenticatedPrincipal() {
        var principal = new DefaultOAuth2AuthenticatedPrincipal(
            "service-orders",
            Map.of("sub", "service-orders", "tenant_id", "tenant-a"),
            List.of(new SimpleGrantedAuthority("SCOPE_orders.read")));

        when(introspector.introspect("opaque-test-token"))
            .thenReturn(Mono.just(principal));

        webTestClient.get()
            .uri("/api/orders/123")
            .headers(headers ->
                headers.setBearerAuth("opaque-test-token"))
            .exchange()
            .expectStatus().isOk();
    }
}
~~~

Test này xác nhận Bearer pipeline gọi reactive introspector và chuyển principal vào authorization. Nó **không kiểm tra request HTTP tới Authorization Server**, vì introspector bị mock.

### Token inactive

Introspector có thể phát BadOpaqueTokenException:

~~~java
when(introspector.introspect("inactive-token"))
    .thenReturn(Mono.error(
        new BadOpaqueTokenException("Token is inactive")));

webTestClient.get()
    .uri("/api/orders/123")
    .headers(headers -> headers.setBearerAuth("inactive-token"))
    .exchange()
    .expectStatus().isUnauthorized();
~~~

### Active nhưng thiếu scope

Nếu introspector trả principal hợp lệ nhưng không có SCOPE_orders.read, authentication thành công nhưng authorization bị từ chối:

~~~java
var principal = new DefaultOAuth2AuthenticatedPrincipal(
    "user-42",
    Map.of("sub", "user-42"),
    List.of(new SimpleGrantedAuthority("SCOPE_profile.read")));

when(introspector.introspect("active-without-order-scope"))
    .thenReturn(Mono.just(principal));

webTestClient.get()
    .uri("/api/orders/123")
    .headers(headers ->
        headers.setBearerAuth("active-without-order-scope"))
    .exchange()
    .expectStatus().isForbidden();
~~~

Đây là khác biệt giữa active=false/authentication failure và active=true nhưng thiếu quyền: thường lần lượt là 401 và 403.

## 11. Kiểm tra decoder thật với JWT đã ký

Muốn xác minh chữ ký, phải dùng ReactiveJwtDecoder thật và một key pair test. Một cách là tạo RSA key pair trong test, ký compact JWT bằng private key rồi cấu hình decoder với public key tương ứng.

Ví dụ dưới đây minh họa phần decoder/validator. Test project cần thư viện JOSE/JWT tương thích (Spring Security OAuth2 JOSE sử dụng Nimbus JOSE JWT):

~~~java
import java.security.interfaces.RSAPublicKey;
import java.time.Instant;
import java.util.Date;

import com.nimbusds.jose.JWSAlgorithm;
import com.nimbusds.jose.JWSHeader;
import com.nimbusds.jose.crypto.RSASSASigner;
import com.nimbusds.jose.jwk.RSAKey;
import com.nimbusds.jose.jwk.gen.RSAKeyGenerator;
import com.nimbusds.jwt.JWTClaimsSet;
import com.nimbusds.jwt.SignedJWT;

import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusReactiveJwtDecoder;

String issuer = "https://auth.test.example/issuer";
Instant now = Instant.now();

RSAKey signingKey = new RSAKeyGenerator(2048)
    .keyID("test-rsa-1")
    .generate();

JWTClaimsSet claims = new JWTClaimsSet.Builder()
    .issuer(issuer)
    .subject("user-42")
    .audience("orders-api")
    .issueTime(Date.from(now.minusSeconds(5)))
    .expirationTime(Date.from(now.plusSeconds(300)))
    .claim("scope", "orders.read")
    .build();

SignedJWT signedJwt = new SignedJWT(
    new JWSHeader.Builder(JWSAlgorithm.RS256)
        .keyID(signingKey.getKeyID())
        .build(),
    claims);
signedJwt.sign(new RSASSASigner(signingKey.toPrivateKey()));
String compactToken = signedJwt.serialize();

NimbusReactiveJwtDecoder decoder =
    NimbusReactiveJwtDecoder.withPublicKey(
        (RSAPublicKey) signingKey.toPublicKey()).build();

OAuth2TokenValidator<Jwt> audienceValidator = jwt ->
    jwt.getAudience().contains("orders-api")
        ? OAuth2TokenValidatorResult.success()
        : OAuth2TokenValidatorResult.failure(
            new OAuth2Error("invalid_token", "Wrong audience", null));

decoder.setJwtValidator(new DelegatingOAuth2TokenValidator<>(
    JwtValidators.createDefaultWithIssuer(issuer),
    audienceValidator));
~~~

Đây là ví dụ dựng token và decoder bằng key test trong bộ nhớ. Khi gọi decoder.decode(compactToken), decoder phải xác minh chữ ký RSA và các validators đã cấu hình. Không dùng key production.

### Gửi token đã ký qua WebTestClient

Đưa decoder thật vào cấu hình test, sau đó:

~~~java
webTestClient.get()
    .uri("/api/orders/123")
    .headers(headers -> headers.setBearerAuth(compactToken))
    .exchange()
    .expectStatus().isOk();
~~~

Các trường hợp âm nên tạo token ký bằng key khác, sai issuer, sai audience, hết hạn, nbf trong tương lai hoặc algorithm không được chấp nhận. Mỗi trường hợp phải đi qua Bearer header để xác nhận filter/decoder trả 401 như contract.

Nếu dùng JWKS endpoint thay public key trực tiếp, chạy một HTTP test server phục vụ JWKS và cấu hình decoder lấy key từ URI test. Khi đó có thể kiểm tra kid, JWKS fetch, cache, unknown key và rotation. Một decoder dùng public key trực tiếp không kiểm tra HTTP discovery/JWKS.

## 12. Kiểm tra issuer, audience và thời hạn

Chữ ký đúng chưa đủ. Resource Server cần xác minh các điều kiện token profile:

| Điều kiện | Token thử nghiệm | Kết quả mong đợi |
| --- | --- | --- |
| Issuer đúng | iss bằng issuer tin cậy | Có thể tiếp tục |
| Issuer khác | iss không khớp | 401 |
| Audience đúng | aud chứa orders-api | Có thể tiếp tục |
| Audience khác | Chỉ có payments-api | 401 |
| Token hết hạn | exp đã qua | 401 |
| Chưa có hiệu lực | nbf ở tương lai ngoài clock skew | 401 |
| Chữ ký sai | Payload đúng nhưng signature không hợp lệ | 401 |
| Algorithm không cho phép | Token dùng alg ngoài allowlist | 401 |
| Thiếu scope | Token hợp lệ nhưng không có orders.read | 403 |

mockJwt() có thể đặt các claims này để kiểm tra code nghiệp vụ đọc chúng, nhưng không thực hiện các validators. Dùng decoder thật khi mục tiêu là kiểm chứng token acceptance.

## 13. Kiểm tra HTTP introspection thật bằng test server

Nếu ứng dụng dùng opaque token, kiểm tra toàn bộ giao thức cần để introspector thật gọi một HTTP server thử nghiệm.

Trong test:

1. Khởi chạy một local HTTP stub server (ví dụ WireMock hoặc MockWebServer).
2. Cấu hình introspection-uri trỏ tới stub.
3. Cấu hình client ID/secret test.
4. Gửi request Bearer token qua WebTestClient.
5. Xác nhận stub nhận POST đúng path/content type và body chứa token.
6. Kiểm tra client authentication theo method đã cấu hình.
7. Trả response introspection theo từng kịch bản.

Response active:

~~~json
{
  "active": true,
  "sub": "user-42",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "exp": 1893456000
}
~~~

Response inactive:

~~~json
{
  "active": false
}
~~~

Ma trận:

| Stub response | Ý nghĩa | Kết quả API thường gặp |
| --- | --- | --- |
| 200 + active: true, claims đủ | Token được AS chấp nhận | Đi tiếp authorization |
| 200 + active: false | Token inactive | 401 |
| 200 nhưng thiếu/sai kiểu active | Response không đạt contract | Fail closed |
| 401 từ introspection endpoint | Client auth có thể sai | Authentication dependency failure |
| 403 từ introspection endpoint | Client không được phép introspect | Không coi token user là hợp lệ |
| 429 | AS rate limit | Không cấp Authentication |
| 5xx/timeout/TLS error | AS không sẵn sàng | Fail closed theo policy |
| 200 active nhưng thiếu scope | Token active, quyền không đủ | 403 |

Một mock ReactiveOpaqueTokenIntrospector không kiểm tra các chi tiết HTTP trên. Chỉ test với introspector thật và stub HTTP mới xác nhận request/response protocol.

Không dùng access token production hoặc secret production trong test server. Không log raw token hoặc client secret.

## 14. Claims và authorities không phải một thứ

Một JWT có thể chứa:

~~~json
{
  "sub": "user-42",
  "scope": "orders.read orders.export",
  "roles": ["ORDER_MANAGER"],
  "tenant_id": "tenant-a"
}
~~~

Claims là dữ liệu trong token. GrantedAuthority là quyền Spring Security dùng cho authorization. Converter quyết định cách ánh xạ.

Với converter mặc định, scope thường được ánh xạ thành:

~~~text
SCOPE_orders.read
SCOPE_orders.export
~~~

Claim roles tùy chỉnh không tự thành ROLE_ORDER_MANAGER nếu ứng dụng chưa cấu hình converter tương ứng.

Ví dụ custom converter:

~~~java
import java.util.Collection;
import java.util.List;
import org.springframework.core.convert.converter.Converter;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.jwt.Jwt;

final class RoleAuthoritiesConverter
        implements Converter<Jwt, Collection<GrantedAuthority>> {

    @Override
    public Collection<GrantedAuthority> convert(Jwt jwt) {
        List<String> roles = jwt.getClaimAsStringList("roles");
        if (roles == null) {
            return List.of();
        }
        return roles.stream()
            .map(role -> new SimpleGrantedAuthority("ROLE_" + role))
            .toList();
    }
}
~~~

Để kiểm thử mapping production, có hai lựa chọn:

- Unit test converter trực tiếp với một Jwt object.
- Gửi Bearer header qua filter chain với ReactiveJwtDecoder trả JWT và cấu hình đúng jwtAuthenticationConverter.

Nếu chỉ dùng mockJwt().authorities(...), test đã chỉ định authority và **bỏ qua converter**. Nếu dùng mockJwt().jwt(...), hãy xác nhận cách post-processor của version đang dùng tạo authorities từ claims; đừng mặc định nó gọi đúng bean converter production.

## 15. Claims cho tenant và object-level authorization

Giả sử token có:

~~~json
{
  "sub": "user-42",
  "scope": "orders.read",
  "tenant_id": "tenant-a"
}
~~~

Service phải giới hạn truy vấn theo tenant:

~~~java
Order findOrder(String orderId, Jwt jwt) {
    String tenantId = jwt.getClaimAsString("tenant_id");
    if (tenantId == null) {
        throw new AccessDeniedException("Tenant is required");
    }
    return repository.findByIdAndTenantId(orderId, tenantId)
        .orElseThrow(() ->
            new AccessDeniedException("Order is not accessible"));
}
~~~

Mock danh tính cho test:

~~~java
webTestClient
    .mutateWith(mockJwt().jwt(jwt -> jwt
        .subject("user-42")
        .claim("scope", "orders.read")
        .claim("tenant_id", "tenant-a")))
    .get()
    .uri("/api/orders/order-100")
    .exchange()
    .expectStatus().isOk();
~~~

Tạo thêm test dùng tenant-b, kiểm tra repository chỉ tìm theo tenant của principal và xác nhận dữ liệu tenant khác không được trả. Scope chỉ cho phép gọi chức năng; nó không tự cấp quyền đọc mọi order.

## 16. Reactive method security

Với WebFlux, method security cần được bật bằng:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableReactiveMethodSecurity;

@Configuration
@EnableReactiveMethodSecurity
class ReactiveMethodSecurityConfiguration {
}
~~~

Một reactive service:

~~~java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.oauth2.jwt.Jwt;
import reactor.core.publisher.Mono;

class ReportService {

    @PreAuthorize("hasAuthority('SCOPE_reports.read')")
    Mono<String> readReport(Jwt jwt) {
        return Mono.just("report-for-" + jwt.getSubject());
    }
}
~~~

Test qua WebTestClient:

~~~java
webTestClient
    .mutateWith(mockJwt().jwt(jwt -> jwt
        .subject("analyst-7")
        .claim("scope", "reports.read")))
    .get()
    .uri("/api/reports")
    .exchange()
    .expectStatus().isOk();
~~~

Trong reactive method security, SecurityContext được truyền qua Reactor Context. Không giả định SecurityContextHolder ThreadLocal có Authentication ở mọi callback. Nếu test trực tiếp service publisher, subscribe trong context có Authentication theo cơ chế reactive test support; không gọi block() bên trong ứng dụng để ép reactive flow thành imperative.

## 17. Kiểm tra ReactiveSecurityContextHolder và request isolation

Một controller hoặc service reactive có thể lấy Authentication từ Reactor Context:

~~~java
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import reactor.core.publisher.Mono;

Mono<String> currentSubject() {
    return ReactiveSecurityContextHolder.getContext()
        .map(context -> context.getAuthentication().getName());
}
~~~

Trong test dùng mockJwt(), context được cung cấp cho request của WebTestClient. Mỗi request có principal riêng:

~~~java
webTestClient
    .mutateWith(mockJwt().jwt(jwt -> jwt.subject("alice")))
    .get().uri("/api/whoami")
    .exchange()
    .expectBody()
    .jsonPath("$.subject").isEqualTo("alice");

webTestClient
    .mutateWith(mockJwt().jwt(jwt -> jwt.subject("bob")))
    .get().uri("/api/whoami")
    .exchange()
    .expectBody()
    .jsonPath("$.subject").isEqualTo("bob");
~~~

Không lưu Authentication của request vào singleton field hoặc ThreadLocal. Không chia sẻ mutable SecurityContext giữa các request. Khi test chạy song song, mỗi WebTestClient exchange phải giữ context đúng request.

## 18. @WebFluxTest và @SpringBootTest

### @WebFluxTest

@WebFluxTest phù hợp khi chỉ cần controller slice. Có thể import security configuration và mock các dependency cần thiết:

~~~java
@WebFluxTest(OrderController.class)
@Import(ApiSecurityConfiguration.class)
class OrderControllerWebFluxTest {

    @Autowired
    WebTestClient webTestClient;

    @MockitoBean
    ReactiveJwtDecoder jwtDecoder;
}
~~~

Ở version Spring Test cũ, thay @MockitoBean bằng @MockBean nếu phù hợp. Có thể cần mock các bean khác được security config tham chiếu.

### @SpringBootTest

Dùng @SpringBootTest cùng @AutoConfigureWebTestClient khi cần kiểm tra:

- Toàn bộ reactive security chain.
- Filter custom và thứ tự filter.
- Reactive method security.
- Bean converter/decoder/introspector thật.
- Service/repository integration.
- Nhiều SecurityWebFilterChain và matcher.

Với test cần kiểm tra TLS handshake hoặc network behavior thật, có thể cần chạy server trên cổng ngẫu nhiên và cấu hình HTTPS client test; WebTestClient bind trực tiếp vào application context không tự tạo một TLS handshake thực.

## 19. Test không có token, token invalid và thiếu scope

Một suite API tối thiểu nên phân biệt:

~~~java
@Test
void missingBearerTokenIsUnauthorized() {
    webTestClient.get()
        .uri("/api/orders/123")
        .exchange()
        .expectStatus().isUnauthorized();
}

@Test
void validIdentityWithoutScopeIsForbidden() {
    webTestClient
        .mutateWith(mockJwt().jwt(jwt -> jwt
            .subject("profile-user")
            .claim("scope", "profile.read")))
        .get()
        .uri("/api/orders/123")
        .exchange()
        .expectStatus().isForbidden();
}

@Test
void readerCanAccessOrder() {
    webTestClient
        .mutateWith(mockJwt().jwt(jwt -> jwt
            .subject("reader-42")
            .claim("scope", "orders.read")))
        .get()
        .uri("/api/orders/123")
        .exchange()
        .expectStatus().isOk();
}
~~~

Kết quả thường gặp:

| Tình huống | Ý nghĩa | HTTP thường gặp |
| --- | --- | --- |
| Không có Bearer token | Chưa authenticated | 401 |
| Decoder/introspector xác định token không hợp lệ | Authentication failure | 401 |
| Token hợp lệ nhưng thiếu scope | Authorization failure | 403 |
| Token hợp lệ và đủ scope | Được phép qua authorization | 2xx theo controller |

Nếu ứng dụng có custom entry point/access denied handler, kiểm tra status/body/header theo contract thực tế.

## 20. Test nhiều SecurityWebFilterChain

Một WebFlux application có thể có chain riêng cho API, browser login, actuator hoặc endpoint nội bộ. Khi đó test cần chứng minh request được chọn đúng chain.

Ví dụ API chain và fallback:

~~~java
@Bean
@Order(1)
SecurityWebFilterChain apiChain(ServerHttpSecurity http) {
    return http
        .securityMatcher(
            new PathPatternParserServerWebExchangeMatcher("/api/**"))
        .authorizeExchange(exchanges -> exchanges
            .anyExchange().authenticated())
        .oauth2ResourceServer(oauth2 ->
            oauth2.jwt(Customizer.withDefaults()))
        .build();
}

@Bean
@Order(100)
SecurityWebFilterChain fallbackChain(ServerHttpSecurity http) {
    return http
        .authorizeExchange(exchanges -> exchanges
            .anyExchange().denyAll())
        .build();
}
~~~

Đây là ví dụ minh họa thứ tự và matcher; matcher class/API cần khớp version. Test:

- /api/** không token trả 401 theo Resource Server.
- /api/** với JWT thiếu scope trả 403.
- Route không khớp API chain bị fallback từ chối.
- Browser route đi qua chain OAuth2 Login nếu ứng dụng có chain đó.

mockJwt() có thể giúp kiểm tra authorization sau khi chain được chọn, nhưng không chứng minh Bearer filter của API chain đã xử lý header. Để kiểm tra chain authentication, gửi Bearer header thật và dùng decoder phù hợp.

## 21. CSRF và các request state-changing trong WebFlux

Không nên tắt CSRF cho toàn bộ WebFlux application chỉ để test POST dễ hơn.

- API chỉ nhận Bearer token trong Authorization header, không dùng cookie tự động gửi để authenticate, thường có thể cấu hình CSRF phù hợp cho API.
- Browser dùng session cookie cần xem xét CSRF vì browser tự động gửi cookie.
- Nếu cùng ứng dụng có API và browser chain, tách policy theo chain.

Spring Security Test có helper CSRF cho WebFlux:

~~~java
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.csrf;

webTestClient
    .mutateWith(mockUser("alice").roles("ADMIN"))
    .mutateWith(csrf())
    .post()
    .uri("/app/profile")
    .exchange()
    .expectStatus().isOk();
~~~

Test CSRF nên phản ánh cơ chế authentication thật của route. Một request dùng mockJwt() không tự chứng minh browser session/cookie CSRF policy đúng.

## 22. Không dùng helper mock để kiểm tra toàn bộ token pipeline

Các helper test hữu ích nhưng có giới hạn:

| Helper | Điều nó tạo | Điều nó không kiểm chứng |
| --- | --- | --- |
| mockJwt() | JWT principal/Authentication cho reactive request | Bearer parsing, signature, JWKS, issuer/audience/time validators |
| mockOpaqueToken() | Opaque principal/Authentication cho reactive request | HTTP introspection, client authentication, active response |
| mockUser() | User Authentication | JWT claims, Resource Server decoder/introspector |
| @WithMockUser | User Authentication trong test context phù hợp | OAuth2 access token validation |
| ReactiveJwtDecoder mock | Kết quả decode do test điều khiển | Cryptographic verification |
| ReactiveOpaqueTokenIntrospector mock | Principal do test điều khiển | Introspection HTTP protocol |

Đây không phải hạn chế làm các helper kém hữu ích. Chúng giúp test nhanh đúng tầng. Sai lầm xảy ra khi dùng kết quả của một tầng để kết luận về tầng khác.

## 23. Ma trận kiểm thử token thực tế

Với JWT:

| Kịch bản | Thành phần cần chạy thật | Kết quả mong đợi |
| --- | --- | --- |
| Signature hợp lệ, key tin cậy | ReactiveJwtDecoder + public key/JWKS | Authentication có thể thành công |
| Signature sai | Decoder thật | 401 |
| Issuer sai | Issuer validator thật | 401 |
| Audience sai | Audience validator thật | 401 |
| Token hết hạn | Timestamp validator thật | 401 |
| nbf ở tương lai | Timestamp validator thật | 401 |
| kid không tồn tại | JWKS decoder/client thật | 401 |
| JWKS endpoint timeout | HTTP test server + decoder thật | Fail closed cho token chưa xác minh được |
| Key rotation | JWKS server thay key và cache thật | Behavior đúng overlap/refresh policy |
| Scope thiếu | Decoder thật + converter + authorization | 403 |

Với opaque token:

| Kịch bản | Thành phần cần chạy thật | Kết quả mong đợi |
| --- | --- | --- |
| active: true, scope đủ | Reactive introspector HTTP thật | Được phép |
| active: false | Introspection HTTP thật | 401 |
| Thiếu active/sai schema | Introspection parser thật | Fail closed |
| Introspection client auth sai | HTTP stub/AS test | Không tạo Authentication |
| HTTP 429/5xx/timeout | HTTP test server | Không chấp nhận token mới |
| Active nhưng audience sai | Introspector + profile validator | 401 |
| Active nhưng scope thiếu | Introspector + authorization | 403 |
| Revoke token | AS test + introspection thật | Inactive theo propagation/cache policy |

## 24. Ma trận lựa chọn test theo câu hỏi

| Câu hỏi cần trả lời | Test phù hợp |
| --- | --- |
| Người có orders.read gọi GET được không? | mockJwt() |
| Claim tenant_id được controller đọc đúng không? | mockJwt().jwt(...) |
| Role claim được map thành ROLE_ADMIN không? | Unit test converter hoặc Bearer flow |
| Bearer header được parse và chuyển đến decoder không? | Header thật + ReactiveJwtDecoder mock |
| JWT signature có đúng không? | Header thật + decoder/key thật |
| Issuer/audience/exp có được kiểm tra không? | Decoder thật + validators thật |
| JWKS kid mới được tải không? | Decoder thật + JWKS test server |
| Introspection POST có đúng client auth/body không? | Reactive introspector thật + HTTP stub |
| active:false bị từ chối không? | Introspector thật hoặc mock cho nhánh authentication |
| Method security chạy trong Reactor Context không? | mockJwt() qua WebTestClient và reactive service |
| Tenant khác có đọc được order không? | Mock principal + service/repository test |
| TLS handshake có yêu cầu client cert không? | HTTPS test server với test CA/client certificate |

## 25. Các lỗi thường gặp

**“mockJwt() pass nghĩa JWT thật đã được xác minh.”** Không. Helper tạo Authentication, bỏ qua decoder và chữ ký.

**“Tôi đặt exp trong quá khứ nhưng request vẫn 200.”** Đó là vì mockJwt() không chạy timestamp validator. Gửi Bearer token qua decoder thật để kiểm tra hết hạn.

**“Tôi đặt iss sai nhưng test vẫn pass.”** Claim chỉ là dữ liệu của JWT mock. Issuer validator không được gọi.

**“Tôi đặt aud sai nhưng Resource Server vẫn cho qua.”** mockJwt() không tự kiểm tra audience. Kiểm tra decoder validator thật.

**“mockOpaqueToken() kiểm tra introspection endpoint.”** Không. Nó dựng principal; dùng HTTP stub và introspector thật để kiểm tra protocol.

**“Tôi dùng mockUser() cho controller nhận Jwt.”** Principal của mock user không phải Jwt. Dùng mockJwt() hoặc Bearer flow.

**“Tôi thêm claim roles là Spring tự tạo ROLE_...”** Không. Cần converter hoặc authorities chỉ định trong test.

**“Mock ReactiveJwtDecoder nghĩa là đã test signature.”** Không. Mock trả đối tượng theo kịch bản do test định nghĩa.

**“WebTestClient bind vào controller chứng minh TLS mTLS hoạt động.”** Không nhất thiết. Cần HTTPS server test thực với client certificate nếu kiểm tra handshake.

**“Reactive SecurityContext nằm trong ThreadLocal.”** Không nên giả định như vậy. WebFlux dùng Reactor Context; dùng các reactive security APIs.

**“Một test 200 là đủ.”** Không. Cần cả missing token, invalid token, thiếu scope, sai audience/issuer, remote outage và business authorization.

## 26. Quy trình xây dựng test suite WebFlux

1. **Tách câu hỏi test:** authorization, controller principal, converter, Bearer parsing, token validation hay introspection protocol.
2. **Dùng mockJwt() cho JWT authorization:** khai báo subject, scope, tenant và claims tối thiểu.
3. **Dùng mockOpaqueToken() cho opaque principal authorization:** khai báo attributes/authorities theo contract.
4. **Dùng mockUser() khi endpoint chỉ cần user/role chung:** không cần JWT principal.
5. **Test reactive method security:** bật @EnableReactiveMethodSecurity và chạy request trong Reactor Context.
6. **Test Bearer pipeline:** gửi Authorization header thật và mock ReactiveJwtDecoder hoặc ReactiveOpaqueTokenIntrospector.
7. **Test JWT cryptography:** decoder thật, key pair test, issuer/audience/time validators.
8. **Test JWKS:** HTTP test server, kid, cache, unknown key và key rotation.
9. **Test introspection HTTP:** endpoint stub, client authentication, request body, active/inactive, timeout và status lỗi.
10. **Test business policy:** tenant, owner, sharing và repository query.
11. **Test WebFlux context isolation:** nhiều request/principal, không dùng ThreadLocal hoặc mutable global context.
12. **Test topology nếu cần:** nhiều SecurityWebFilterChain, proxy, TLS và mTLS bằng server phù hợp.

**Điểm cần nhớ:** mockJwt(), mockOpaqueToken() và mockUser() giúp dựng danh tính để kiểm thử **authorization** trong WebFlux. Chúng không xác minh Bearer token thực tế. Muốn kiểm tra toàn bộ chuỗi, gửi header Authorization: Bearer ... qua WebTestClient, để BearerTokenAuthenticationWebFilter gọi ReactiveJwtDecoder hoặc ReactiveOpaqueTokenIntrospector, rồi kiểm tra validators, converter và authorization. Dùng decoder/introspector thật cùng key/JWKS hoặc HTTP test server khi cần chứng minh chữ ký, issuer, audience, expiry, introspection và behavior khi Authorization Server gặp lỗi.
