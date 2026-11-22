# Cấu hình issuer-uri, jwk-set-uri và quan hệ với nhà cung cấp danh tính — Spring Security WebFlux

## Mục tiêu học tập

Bài học thuộc **Resource Server JWT** trong module **Spring Security – reactive**. Sau khi hoàn thành, bạn có thể:

1. Phân biệt **Identity Provider / OAuth2 Authorization Server**, **OAuth2 Client** và **Resource Server**; hiểu Resource Server kiểm tra token chứ không tự cấp token.
2. Giải thích đúng ý nghĩa của `issuer-uri`, `jwk-set-uri`, OpenID Connect Discovery, OAuth 2.0 Authorization Server Metadata và `jwks_uri`.
3. Chọn giữa ba cấu hình: chỉ `issuer-uri`, chỉ `jwk-set-uri`, và **cả hai**; biết điều gì được discovery, điều gì được validate tự động.
4. Kiểm chứng JWT bằng **chữ ký, issuer, audience, thời gian và scope**; không nhầm JWT access token với ID token.
5. Cấu hình Java 17+ / Spring Boot 3.5.x / Spring Security 6.5.x dùng WebFlux `SecurityWebFilterChain`, `ServerHttpSecurity`, `ReactiveJwtDecoder` và scope authorization.
6. Chạy integration tests tạo RSA-signed JWT và phục vụ public JWKS từ MockWebServer local; kiểm tra trường hợp 200, 401, 403, issuer sai, audience sai, chữ ký sai, token hết hạn.
7. Xử lý key rotation, metadata discovery, downtime IdP, clock skew, TLS, nhiều issuer, sai `kid`, quyền multi-tenant và rủi ro custom decoder thiếu issuer validator.

> Phiên bản minh họa: Java 17+, Spring Boot **3.5.16**, Spring Security **6.5** (nên sử dụng ít nhất bản vá **6.5.10** trong nhánh này). Spring Boot 3.5 đã hết thời hạn OSS support; khi thiết kế hệ thống mới hãy ưu tiên nhánh còn được hỗ trợ. Bài dùng các API **reactive**; mã Servlet như `HttpSecurity` hoặc `JwtDecoder` không phải API tương đương của WebFlux.

---

## 1. Kiến trúc Resource Server JWT và nhà cung cấp danh tính

```text
Người dùng / background service
           |
           v
   OAuth2 Client xin token
           |
           v
+-------------------------------------+
| Identity Provider / Authorization   |
| Server                              |
| - Xác thực chủ thể, áp grant/consent |
| - Phát JWT access token             |
| - Ký bằng private signing key       |
| - Công bố public keys qua JWKS       |
+-------------------------------------+
           |                    ^
           | access token       | GET issuer metadata / JWKS
           v                    |
   OAuth2 Client                |
           |                    |
           | Authorization: Bearer <JWT>
           v                    |
+-------------------------------------+
| Spring Security WebFlux             |
| OAuth2 Resource Server             |
| - verify signature theo trusted JWK |
| - validate iss / aud / nbf / exp    |
| - map scopes thành SCOPE_*          |
| - authorize URL/service/resource   |
+-------------------------------------+
           |
           v
        HTTP 200 / 401 / 403
```

**Identity Provider (IdP)** thường cung cấp các luồng đăng nhập/OIDC; **Authorization Server** cấp OAuth2 access token. Một sản phẩm có thể vừa là IdP vừa là Authorization Server nhưng không bắt buộc. **OAuth2 Client** lấy/sử dụng token. **Resource Server** nhận Bearer token và quyết định có chấp nhận không; nó không tự cấp token khi bật `oauth2ResourceServer().jwt()`.

Đừng gộp các khái niệm:

| Khái niệm | Ví dụ minh họa | Trách nhiệm |
| --- | --- | --- |
| Issuer identifier | `https://idp.example.test/realms/acme` | Giá trị phải khớp claim `iss` |
| Discovery metadata | Tài liệu JSON tại URL `.well-known` | Công bố issuer, `jwks_uri` và endpoint của provider |
| JWK Set URL | `https://idp.example.test/realms/acme/certs` | Trả các public signing keys |
| Token endpoint | `https://idp.example.test/realms/acme/token` | Client đổi grant lấy token, **không phải** địa chỉ JWKS |
| Audience | `api://inventory` | API nào được quyền nhận access token |
| Resource Server | `inventory-api` | Kiểm tra chữ ký, claims, scope, data permission |

Mỗi URL là ví dụ, không phải endpoint của một IdP cụ thể.

## 2. Một JWT access token có những gì?

JWT compact thường có cấu trúc:

```text
base64url(header).base64url(payload).base64url(signature)
```

Ví dụ header **chỉ để minh họa**:

```json
{"typ":"JWT","alg":"RS256","kid":"signing-key-1"}
```

Ví dụ payload:

```json
{
  "iss": "https://idp.example.test/realms/acme",
  "sub": "user-123",
  "aud": ["api://inventory"],
  "scope": "inventory.read inventory.write",
  "iat": 1794000000,
  "nbf": 1794000000,
  "exp": 1794003600
}
```

Các timestamp ở trên chỉ là số mẫu, không khẳng định token còn hạn. Payload Base64URL **không được mã hóa**; decode chỉ để xem dữ liệu, không hề xác thực nội dung. Chỉ khi chữ ký được verify với trusted public key và các validators đạt thì Spring mới tạo Authentication.

| JWT field | Vai trò | Quy tắc an toàn |
| --- | --- | --- |
| `iss` | Ai phát token | So khớp chính xác issuer tin cậy |
| `aud` | Dành cho resource nào | Phải chứa audience của chính API |
| `sub` | Chủ thể | Dùng làm identity sau verify, xét namespace/tenant |
| `exp` | Hạn dùng | Không nhận khi đã hết hạn |
| `nbf` | Chưa có hiệu lực | Không nhận quá sớm |
| `iat` | Thời điểm phát hành | Không thay thế exp/nbf checks |
| `scope` / `scp` | Quyền OAuth2 | Map thành `SCOPE_inventory.read` chẳng hạn |
| `kid` | Gợi ý key để verify | Chỉ chọn từ JWKS đã tin, không tin tùy ý |
| `alg` | Thuật toán ký | Phải nằm trong allowlist, không nhận `none` |
| `typ` | Token profile/type | Quan trọng khi phân biệt access token và ID token |

**Một token có chữ ký đúng vẫn có thể không dành cho API của bạn.** Cùng một IdP có thể phát token cho nhiều ứng dụng với audience khác nhau. Vì thế kiểm tra `aud` là quan trọng, không nên chỉ dựa vào `iss` và signature.

## 3. issuer-uri: chính xác là định danh issuer

Trong `application.yml`:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.test/realms/acme
```

Giá trị này cần đúng claim `iss` mà IdP thực sự phát, gồm **scheme, hostname, path, trailing slash**. Không dùng URL token endpoint làm issuer nếu issuer của token là URL khác. Ví dụ:

```text
expected iss: https://idp.example.test/realms/acme
actual iss:   https://idp.example.test/realms/other
=> REJECT, dù chữ ký có thể kiểm tra được
```

Spring Security 6.5 có thể dùng issuer để tìm OpenID Provider Configuration hoặc OAuth2 Authorization Server Metadata tại các endpoint `.well-known` được hỗ trợ, rồi lấy thuộc tính `jwks_uri`. Metadata có thể giống:

```json
{
  "issuer": "https://idp.example.test/realms/acme",
  "authorization_endpoint": "https://idp.example.test/realms/acme/authorize",
  "token_endpoint": "https://idp.example.test/realms/acme/token",
  "jwks_uri": "https://idp.example.test/realms/acme/certs"
}
```

Đây chỉ là JSON rút gọn, không phải provider metadata hoàn chỉnh. **Không tự suy JWKS URL bằng cách nối một path cố định vào issuer**; đường dẫn JWKS không được chuẩn hóa như một suffix bắt buộc. Dùng discovery chính thức hoặc tài liệu IdP.

### Discovery khi startup hay ở request đầu tiên?

Ở cấu hình mặc định Spring Boot 3.5 / Spring Security 6.5 reactive, quá trình discovery từ issuer có thể được **trì hoãn tới request JWT đầu tiên** qua `SupplierReactiveJwtDecoder`. Điều này giúp ứng dụng **không bắt buộc** phải liên hệ IdP để khởi động. Nhưng custom decoder có thể khám phá metadata ngay khi được khởi tạo, nên không nói chung rằng mọi cấu hình issuer đều lazy.

Phân biệt:

- **App started**: WebFlux server đã lắng nghe, bean cấu hình cơ bản đã sẵn sàng.
- **Can verify a JWT**: metadata/JWKS cần thiết đã được lấy hoặc cache đủ tin cậy.
- IdP/JWKS unreachable khi cần key: request Bearer không thể được cấp quyền, dù healthcheck của app còn báo UP.
- Một custom `ReactiveJwtDecoder` có thể làm thay đổi thời điểm gọi metadata.

## 4. jwk-set-uri: địa chỉ public signing keys

Khi cấu hình trực tiếp:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          jwk-set-uri: https://idp.example.test/realms/acme/certs
```

JWK Set (RFC 7517) thường là JSON chứa một mảng `keys`, ví dụ hình dạng:

```json
{
  "keys": [
    {
      "kty": "RSA",
      "kid": "signing-key-1",
      "use": "sig",
      "alg": "RS256",
      "n": "BASE64URL_PUBLIC_MODULUS",
      "e": "AQAB"
    }
  ]
}
```

Trường `n` trên là chuỗi placeholder để mô tả cấu trúc, **không phải RSA key hợp lệ**. JWKS chỉ nên công bố **public key**; tuyệt đối không đưa RSA private exponent `d`, private key PEM hoặc client secret vào response.

### Rotation

Khi IdP xoay khóa:

1. Publish **public key mới** vào JWKS (có `kid` mới).
2. Bắt đầu ký JWT mới bằng private key tương ứng.
3. Giữ public key cũ trong thời gian đủ để token cũ còn hạn được verify.
4. Cân nhắc cache/re-fetch behavior ở Resource Server và TTL của access token.
5. Khi token cũ đã hết hạn, mới loại bỏ public key cũ theo policy.

Không suy rằng mỗi JWT request luôn gọi JWKS. Spring Security/Nimbus có caching. Khi `kid` mới chưa nằm trong cache, decoder có thể cần refresh JWKS; khi endpoint downtime hoặc cache chưa có matching key, **không bỏ signature check**.

`kid` là dữ liệu do người gửi JWT cung cấp; nó chỉ giúp chọn key **từ JWKS tin cậy đã cấu hình**. Không tự lấy `jku` hoặc `x5u` trong JWT header làm URL để tải key từ host bất kỳ, vì có thể gây SSRF và key trust injection.

## 5. Ba chế độ cấu hình đúng và khác biệt

### Chế độ A — Chỉ issuer-uri

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.test/realms/acme
          audiences:
            - api://inventory
```

- Phù hợp IdP hỗ trợ metadata discovery chuẩn.
- Spring xác định expected issuer và tìm JWKS URI từ metadata.
- Việc tìm metadata có thể lazy trong Boot/Security 6.5 defaults.
- API vẫn cần JWKS public key khi xác minh chữ ký.
- `audiences` bổ sung check `aud`; không nên bỏ.

### Chế độ B — Chỉ jwk-set-uri

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          jwk-set-uri: https://idp.example.test/realms/acme/certs
          audiences:
            - api://inventory
```

- Không cần metadata discovery để xác định JWKS.
- Dùng khi provider không có discovery hoặc JWKS URL đã được quản lý.
- **Không mặc nhiên có expected issuer** nếu chỉ khai JWKS, do đó phải thêm issuer validator bằng cấu hình/chính sách đáng tin.
- Chữ ký đúng theo key chưa đủ để xác định issuer và audience. Trong production, nên cấu hình cả hai thuộc tính khi biết issuer.

### Chế độ C — issuer-uri + jwk-set-uri (khuyến nghị khi muốn pin JWKS)

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.test/realms/acme
          jwk-set-uri: https://idp.example.test/realms/acme/certs
          audiences:
            - api://inventory
```

- JWKS URL được cung cấp trực tiếp nên không phải gọi metadata chỉ để khám phá địa chỉ public key.
- Expected issuer vẫn là issuer-uri; Spring Boot defaults kiểm tra `iss`.
- Audience property kiểm tra `aud` có dành cho API.
- Khởi động không bị phụ thuộc metadata discovery, **nhưng** vẫn cần liên hệ JWKS khi cache chưa có key phù hợp.
- Nếu nhà cung cấp đổi JWKS URL, bạn phải cập nhật cấu hình pin.

| Điểm so sánh | Chỉ issuer | Chỉ JWKS | Cả hai |
| --- | --- | --- | --- |
| Discovery metadata để tìm JWKS URL | Có | Không | Không cần |
| Expected `iss` từ property | Có | Không | Có |
| Signature verify | Có | Có | Có |
| `aud` tự đúng nếu không có `audiences`? | Không | Không | Không |
| Luôn cần IdP ở startup? | Không nhất thiết trong mặc định 6.5 | Không cho discovery | Không cho discovery |
| Có thể cần network fetch key lúc runtime | Có | Có | Có |
| An toàn khi JWKS failure | Không cấp quyền nếu không verify được | Tương tự | Tương tự |

**Lựa chọn thực tế:** nếu IdP discovery ổn định, chỉ issuer+audience thường đủ. Nếu muốn startup độc lập với metadata hoặc IdP không cung cấp discovery, dùng issuer+JWK URL+audience. Không đánh đổi issuer check lấy tính sẵn sàng.

## 6. Các bước xác thực JWT trong WebFlux

```text
GET /api/inventory
Authorization: Bearer <token>
          |
          v
Bearer token authentication filter
          |
          +-- parse JWT/JWS
          +-- select public JWK by trusted jwk-set-uri and kid
          +-- verify signature using allowed JWS algorithm
          +-- check exp, nbf, iss and aud
          |
          v
Jwt Authentication (principal = Jwt, name ~= sub)
          |
          +-- scope inventory.read => SCOPE_inventory.read
          |
          v
AuthorizationWebFilter
          |
          +-- hasAuthority("SCOPE_inventory.read") ?
               +-- yes -> Controller/Service
               +-- no  -> 403
```

JWT Resource Server không phải nơi quản lý user password hay tự cấp OAuth2 tokens. Nó kiểm tra token đã được Authority Server phát, ánh xạ authorities và thực hiện authorization. Nếu controller cần quản lý row-level permissions/tenants, phải kiểm tra thêm dữ liệu nghiệp vụ; scope check một mình không cho user quyền xem mọi record.

Với thiếu Bearer token hoặc token không hợp lệ, API dùng Bearer thường trả **401**; với JWT đã xác thực nhưng thiếu required scope, thường là **403**. Nếu có lỗi JWKS network, status có thể phụ thuộc error handling, nhưng tuyệt đối không trả dữ liệu khi chưa verify token.

## 7. Dự án Java 17+ runnable và test offline

Dự án này dùng **Spring Boot 3.5.16**, Spring Security 6.5, WebFlux. Cấu hình production-style để hiểu issuer/JWKS; integration test có mock JWKS chạy loopback và token được **ký RSA thật** để kiểm tra validation. Không có secret hoặc IdP production.

### 7.1. Cấu trúc

```text
jwt-resource-lab/
  settings.gradle
  build.gradle
  src/main/java/example/jwtlab/
    JwtResourceApplication.java
    SecurityConfiguration.java
    InventoryController.java
  src/main/resources/
    application.yml
  src/test/java/example/jwtlab/
    JwtResourceIntegrationTest.java
```

### 7.2. Gradle đầy đủ

**`settings.gradle`:**

```groovy
rootProject.name = 'jwt-resource-lab'
```

**`build.gradle`:**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testImplementation 'com.squareup.okhttp3:mockwebserver:4.12.0'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Starter OAuth2 Resource Server kéo các thư viện JOSE/JWT cần thiết, gồm Nimbus được Spring Security dùng để verify chữ ký. Test code sử dụng Nimbus từ dependency graph này.

Không thêm `spring-boot-starter-web` cùng lúc nếu muốn WebFlux thuần. Boot 3.5.16 là baseline để ví dụ dễ tái tạo, không phải khuyến nghị triển khai nhánh hết OSS support cho sản phẩm mới.

### 7.3. application.yml

**`src/main/resources/application.yml`:**

```yaml
server:
  port: 8080

spring:
  application:
    name: jwt-resource-lab
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.invalid/realms/lab
          jwk-set-uri: https://idp.example.invalid/realms/lab/certs
          audiences:
            - api://inventory
```

Các URL `.invalid` **không phải IdP thật**; ngoài test, bạn cần thay chúng bằng issuer và JWKS URL chính thức của provider. Trong test, `@DynamicPropertySource` override bằng một JWKS fixture local, vì thế `./gradlew test` không cần kết nối IdP ở Internet.

### 7.4. Main class

**`src/main/java/example/jwtlab/JwtResourceApplication.java`:**

```java
package example.jwtlab;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class JwtResourceApplication {

    public static void main(String[] args) {
        SpringApplication.run(JwtResourceApplication.class, args);
    }
}
```

### 7.5. WebFlux Security configuration

**`src/main/java/example/jwtlab/SecurityConfiguration.java`:**

```java
package example.jwtlab;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration(proxyBeanMethods = false)
@EnableWebFluxSecurity
public class SecurityConfiguration {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers(HttpMethod.GET, "/public/ping")
                            .permitAll()
                        .pathMatchers(HttpMethod.GET, "/api/inventory")
                            .hasAuthority("SCOPE_inventory.read")
                        .anyExchange().denyAll()
                )
                .oauth2ResourceServer(oauth2 -> oauth2
                        .jwt(Customizer.withDefaults()))
                .build();
    }
}
```

Ở đây `ServerHttpSecurity` tạo reactive `SecurityWebFilterChain`. Vì project không khai báo custom `ReactiveJwtDecoder` bean, Spring Boot dùng properties issuer/JWK/audience để thiết lập decoder. `hasAuthority("SCOPE_inventory.read")` yêu cầu scope từ JWT, không tự cho phép mọi Bearer token.

Không bật `httpBasic`, `formLogin` hoặc OAuth2 Client khi chỉ đóng vai trò **Resource Server**. CSRF WebFlux mặc định vẫn bật nhưng API demo chỉ có GET; đánh giá CSRF riêng nếu thêm unsafe methods và browser tự gửi cookie/Basic/mTLS.

### 7.6. Controller

**`src/main/java/example/jwtlab/InventoryController.java`:**

```java
package example.jwtlab;

import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class InventoryController {

    @GetMapping("/public/ping")
    public Mono<String> ping() {
        return Mono.just("pong");
    }

    @GetMapping("/api/inventory")
    public Mono<String> inventory(@AuthenticationPrincipal Jwt jwt) {
        return Mono.just("inventory-for-" + jwt.getSubject());
    }
}
```

Sau xác thực JWT, Spring Security đặt `Jwt` vào principal. Khi token có `sub=alice` và đủ scope, response dự kiến là `inventory-for-alice`. Đây là dữ liệu demo; trong API thật còn phải ràng buộc user/tenant và kiểm tra quyền truy cập từng tài nguyên.

## 8. Integration test JWT/JWKS thực bằng MockWebServer

Đoạn test tạo private RSA key ở **bộ nhớ test**, xuất public JWK qua MockWebServer local, rồi ký JWT RS256 và gửi HTTP tới Netty thật bằng `WebTestClient`. Dù không có IdP thật, **JWT signature/issuer/audience/timestamp đều được kiểm tra bởi ReactiveJwtDecoder thật**.

**`src/test/java/example/jwtlab/JwtResourceIntegrationTest.java`:**

```java
package example.jwtlab;

import java.io.IOException;
import java.time.Instant;
import java.util.Date;

import com.nimbusds.jose.JOSEException;
import com.nimbusds.jose.JOSEObjectType;
import com.nimbusds.jose.JWSAlgorithm;
import com.nimbusds.jose.JWSHeader;
import com.nimbusds.jose.crypto.RSASSASigner;
import com.nimbusds.jose.jwk.JWKSet;
import com.nimbusds.jose.jwk.RSAKey;
import com.nimbusds.jose.jwk.gen.RSAKeyGenerator;
import com.nimbusds.jwt.JWTClaimsSet;
import com.nimbusds.jwt.SignedJWT;
import okhttp3.mockwebserver.Dispatcher;
import okhttp3.mockwebserver.MockResponse;
import okhttp3.mockwebserver.MockWebServer;
import okhttp3.mockwebserver.RecordedRequest;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class JwtResourceIntegrationTest {

    private static final String ISSUER =
            "https://issuer.example.invalid/realms/test";
    private static final String AUDIENCE = "api://inventory";
    private static final RSAKey SIGNING_KEY =
            generateKey("training-key-1");
    private static final MockWebServer JWKS =
            startJwksServer();

    @DynamicPropertySource
    static void overrideIdpProperties(DynamicPropertyRegistry registry) {
        registry.add(
                "spring.security.oauth2.resourceserver.jwt.issuer-uri",
                () -> ISSUER);
        registry.add(
                "spring.security.oauth2.resourceserver.jwt.jwk-set-uri",
                () -> JWKS.url("/jwks").toString());
        registry.add(
                "spring.security.oauth2.resourceserver.jwt.audiences",
                () -> AUDIENCE);
    }

    @LocalServerPort int port;
    private WebTestClient client;

    @BeforeEach
    void makeClient() {
        client = WebTestClient.bindToServer()
                .baseUrl("http://127.0.0.1:" + port)
                .build();
    }

    @AfterAll
    static void closeJwks() throws IOException {
        JWKS.shutdown();
    }

    private static RSAKey generateKey(String kid) {
        try {
            return new RSAKeyGenerator(2048)
                    .keyID(kid).generate();
        } catch (JOSEException ex) {
            throw new IllegalStateException(ex);
        }
    }

    private static MockWebServer startJwksServer() {
        MockWebServer server = new MockWebServer();
        server.setDispatcher(new Dispatcher() {
            @Override
            public MockResponse dispatch(RecordedRequest request) {
                if ("/jwks".equals(request.getPath())) {
                    // JWKS chỉ có public key, không bao gồm private exponent.
                    String json = new JWKSet(SIGNING_KEY.toPublicJWK())
                            .toString();
                    return new MockResponse()
                            .setResponseCode(200)
                            .setHeader("Content-Type", "application/json")
                            .setBody(json);
                }
                return new MockResponse().setResponseCode(404);
            }
        });
        try {
            server.start();
        } catch (IOException ex) {
            throw new ExceptionInInitializerError(ex);
        }
        return server;
    }

    private static String signedJwt(
            RSAKey signer, String issuer, String audience,
            String scope, Instant notBefore, Instant expiresAt) {
        try {
            JWTClaimsSet claims = new JWTClaimsSet.Builder()
                    .issuer(issuer)
                    .subject("alice")
                    .audience(audience)
                    .issueTime(Date.from(notBefore.minusSeconds(10)))
                    .notBeforeTime(Date.from(notBefore))
                    .expirationTime(Date.from(expiresAt))
                    .claim("scope", scope)
                    .build();

            SignedJWT jwt = new SignedJWT(
                    new JWSHeader.Builder(JWSAlgorithm.RS256)
                            .type(JOSEObjectType.JWT)
                            .keyID(signer.getKeyID())
                            .build(),
                    claims);
            jwt.sign(new RSASSASigner(signer));
            return jwt.serialize();
        } catch (JOSEException ex) {
            throw new IllegalStateException(ex);
        }
    }

    private static String token(
            String issuer, String audience, String scope) {
        Instant now = Instant.now();
        return signedJwt(
                SIGNING_KEY, issuer, audience, scope,
                now.minusSeconds(30),
                now.plusSeconds(600));
    }

    @Test
    void publicEndpointDoesNotNeedJwt() {
        client.get().uri("/public/ping")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("pong");
    }

    @Test
    void missingJwtReturns401() {
        client.get().uri("/api/inventory")
                .exchange().expectStatus().isUnauthorized();
    }

    @Test
    void malformedJwtReturns401() {
        client.get().uri("/api/inventory")
                .headers(h -> h.setBearerAuth("not-a-jwt"))
                .exchange().expectStatus().isUnauthorized();
    }

    @Test
    void validSignatureIssuerAudienceScopeReturns200() {
        client.get().uri("/api/inventory")
                .headers(h -> h.setBearerAuth(
                        token(ISSUER, AUDIENCE, "inventory.read")))
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class)
                .isEqualTo("inventory-for-alice");
    }

    @Test
    void wrongIssuerIsUnauthorized() {
        client.get().uri("/api/inventory")
                .headers(h -> h.setBearerAuth(token(
                        "https://other.example.invalid",
                        AUDIENCE, "inventory.read")))
                .exchange().expectStatus().isUnauthorized();
    }

    @Test
    void wrongAudienceIsUnauthorized() {
        client.get().uri("/api/inventory")
                .headers(h -> h.setBearerAuth(
                        token(ISSUER, "api://billing", "inventory.read")))
                .exchange().expectStatus().isUnauthorized();
    }

    @Test
    void missingScopeIsForbidden() {
        client.get().uri("/api/inventory")
                .headers(h -> h.setBearerAuth(
                        token(ISSUER, AUDIENCE, "inventory.write")))
                .exchange().expectStatus().isForbidden();
    }

    @Test
    void wrongSignatureIsUnauthorized() {
        // Cùng kid nhưng private signing key khác!
        RSAKey outsider = generateKey("training-key-1");
        Instant now = Instant.now();
        String jwt = signedJwt(
                outsider, ISSUER, AUDIENCE, "inventory.read",
                now.minusSeconds(30), now.plusSeconds(600));
        client.get().uri("/api/inventory")
                .headers(h -> h.setBearerAuth(jwt))
                .exchange().expectStatus().isUnauthorized();
    }

    @Test
    void expiredJwtIsUnauthorized() {
        Instant now = Instant.now();
        String jwt = signedJwt(
                SIGNING_KEY, ISSUER, AUDIENCE, "inventory.read",
                now.minusSeconds(3600), now.minusSeconds(600));
        client.get().uri("/api/inventory")
                .headers(h -> h.setBearerAuth(jwt))
                .exchange().expectStatus().isUnauthorized();
    }

    @Test
    void futureNbfIsUnauthorized() {
        Instant now = Instant.now();
        String jwt = signedJwt(
                SIGNING_KEY, ISSUER, AUDIENCE, "inventory.read",
                now.plusSeconds(600), now.plusSeconds(1800));
        client.get().uri("/api/inventory")
                .headers(h -> h.setBearerAuth(jwt))
                .exchange().expectStatus().isUnauthorized();
    }

    @Test
    void unknownKidIsUnauthorized() {
        RSAKey outsider = generateKey("not-published-key");
        Instant now = Instant.now();
        String jwt = signedJwt(
                outsider, ISSUER, AUDIENCE, "inventory.read",
                now.minusSeconds(30), now.plusSeconds(600));
        client.get().uri("/api/inventory")
                .headers(h -> h.setBearerAuth(jwt))
                .exchange().expectStatus().isUnauthorized();
    }
}
```

### 8.1. Cách test này thực sự kiểm tra issuer/JWKS

- `@DynamicPropertySource` ghi đè config ngay trước lúc Boot khởi tạo context.
- Expected issuer là `https://issuer.example.invalid/realms/test`; vì **cả issuer và JWK URI** được cung cấp, Spring không phải gọi metadata tại tên miền giả này.
- JWK URI là `http://127.0.0.1:<port>/jwks`, chỉ dùng loopback trong test; MockWebServer trả public RSA key của SIGNING_KEY.
- Test tạo JWT ký bằng private RSA key đó, Spring Security tự fetch public JWKS và verify.
- Sai issuer, sai audience, sai chữ ký, hết hạn hoặc chưa đến `nbf` phải bị 401; chỉ thiếu scope thì đã xác thực được nhưng bị 403.
- Đối với IdP thật, **bắt buộc HTTPS** có xác thực hostname/cert; tuyệt đối không copy mock HTTP JWK URL vào production.
- Test không gọi OAuth2 token endpoint, không kiểm tra OIDC login hoặc token rotation; chúng là những workflow khác.

### 8.2. Chạy test

Project có Gradle Wrapper:

```bash
./gradlew test --tests example.jwtlab.JwtResourceIntegrationTest
```

Windows PowerShell:

```powershell
.\gradlew.bat test --tests example.jwtlab.JwtResourceIntegrationTest
```

Hoặc dùng Gradle tương thích được cài sẵn:

```bash
gradle test --tests example.jwtlab.JwtResourceIntegrationTest
```

**Kỳ vọng:** 11 tests PASS. Đây chỉ là dự kiến dựa vào code và API đã đối chiếu, **không phải log một lần compile/test đã chạy thực tế**. Trong môi trường CI, cần cho phép bind cổng loopback và tải dependencies từ Maven Central. Test có thể được mở rộng để kiểm tra rotation/retry/timeout của JWKS.

## 9. Custom ReactiveJwtDecoder và validator: phần dễ mắc lỗi

**Khuyến nghị:** khi chỉ cần issuer, JWK URL và audience, dùng Boot properties như demo. Chỉ tạo custom decoder khi cần thuật toán đặc thù, cache, HTTP client, timeout hoặc claim validator tùy chỉnh.

Fragment **thay thế** Boot auto-config, không phải code thêm vào main project:

```java
// Đặt bên trong @Configuration cùng các import ở đoạn sau.
@Bean
ReactiveJwtDecoder jwtDecoder() {
    String issuer = "https://idp.example.test/realms/acme";
    String jwks = "https://idp.example.test/realms/acme/certs";
    String audience = "api://inventory";

    NimbusReactiveJwtDecoder decoder =
            NimbusReactiveJwtDecoder.withJwkSetUri(jwks).build();

    OAuth2TokenValidator<Jwt> withIssuerAndTime =
            JwtValidators.createDefaultWithIssuer(issuer);

    OAuth2TokenValidator<Jwt> withAudience =
            new JwtClaimValidator<java.util.List<String>>(
                    "aud", aud -> aud != null && aud.contains(audience));

    decoder.setJwtValidator(new DelegatingOAuth2TokenValidator<>(
            withIssuerAndTime, withAudience));
    return decoder;
}
```

Các imports cần thiết:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtClaimValidator;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusReactiveJwtDecoder;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;
```

**Điểm an toàn bắt buộc:** khi tự dùng `NimbusReactiveJwtDecoder.withJwkSetUri(...).build()`, đừng nghĩ việc biết JWKS URL đã đủ để kiểm tra issuer. `JwtValidators.createDefaultWithIssuer(issuer)` giữ kiểm tra issuer và timestamp; audience validator kiểm tra `aud`. Nếu tự `setJwtValidator` chỉ với audience validator mà quên default validators, bạn có thể đánh mất issuer/time validation.

### Cảnh báo CVE-2026-22748

Spring Security công bố ngày 20/04/2026 rằng các bản **6.5.0–6.5.9** có thể khiến lập trình viên hiểu nhầm `NimbusReactiveJwtDecoder.withIssuerLocation(...)` tự bổ sung issuer validation. Bản vá được công bố là **6.5.10**. Dù dùng phiên bản đã vá, vẫn nên viết tests với **JWT có signature đúng nhưng iss sai** và explicit validators trong custom decoder.

Không cấu hình default policy để chấp nhận `alg=none`, không dùng JWKS URL do JWT header `jku` chỉ định, không chấp nhận keys từ issuer tùy ý và không tắt TLS verification ở production.

## 10. ID token, access token và kiểm tra audience

OIDC **ID token** dùng cho OIDC Client xác nhận authentication, thông thường có `aud` là client ID. OAuth2 **access token** dùng gọi Resource Server và cần đúng audience/resource, scopes và profile. Cùng IdP có thể ký cả hai bằng một signing key, vì vậy **signature hợp lệ chưa đủ**.

Nếu IdP dùng JWT access token profile RFC 9068, có thể cần yêu cầu `typ=at+jwt` và validators tương ứng. Không nên mặc định chấp nhận bất kỳ JWT nào từ issuer. Cùng `sub`/`iss` nhưng `aud` khác phải được từ chối khi gọi API.

| Token | Audience điển hình | Dùng cho |
| --- | --- | --- |
| ID token | OIDC client_id | Ứng dụng client xác minh phiên đăng nhập |
| API access token | API/resource identifier | Resource Server authorization |
| Refresh token | Token endpoint/IdP semantics | Xin access token mới, không gửi thẳng tới API |
| Opaque access token | Provider-managed token identifier | Introspection hoặc cơ chế dành cho opaque tokens |

Resource Server JWT thông thường xác minh chữ ký **offline sau khi có trusted keys**, không gọi IdP mỗi request để kiểm tra token còn được phép. Thu hồi quyền tức thời trước `exp` cần chiến lược khác như TTL ngắn, revocation list, introspection hoặc quản lý session/token theo nghiệp vụ.

## 11. Vận hành: kết nối IdP, key rotation và multi-tenant

**Khi chuyển sang IdP thật**, cần thống nhất với team identity:

- `iss` chính xác trong JWT và metadata, gồm trailing slash và realm path.
- `jwks_uri` chính thức, TLS certificate hostname, thuật toán JWS được hỗ trợ và key-rotation policy.
- `aud` Resource Server cần chấp nhận, scope/role mapping và token type.
- Access token là JWT hay opaque, và expiry/revocation policy.
- Backend có outbound HTTPS đến metadata/JWKS không, timeout/cache/retry thế nào.
- Tài khoản/service client thuộc tenant nào và subject identity có ổn định không.
- Proxy IdP public issuer có thể khác host HTTP nội bộ; cấu hình external HTTPS issuer phải đúng.
- Mỗi lần deploy/rotate keys, test JWT đã phát bằng key cũ và key mới.

**Không dùng JWKS URL do request query/body/header hoặc claim chưa xác minh cung cấp.** Khi API cần nhiều issuer, hãy pin **allowlist issuer** và một decoder/validator tương ứng cho từng trust domain; dùng mechanism như `JwtIssuerReactiveAuthenticationManagerResolver` theo tài liệu phiên bản. Arbitrary issuer discovery có thể gây SSRF và nhầm trust boundary.

### Startup không phụ thuộc IdP không có nghĩa authentication luôn sẵn sàng

Với issuer-only trong Boot/Security 6.5, discovery có thể lazy. Với cả issuer/JWKS, không cần metadata discovery. Nhưng nếu ký key mới chưa có trong cache và JWK endpoint down, Resource Server không thể verify JWT. Khi đó phải **fail closed**, trả lỗi phù hợp và ghi metrics; không fallback sang `permitAll()` hoặc decode mà bỏ signature.

### Quy trình xác minh bằng curl

Chỉ dùng trên domain IdP bạn được cấp quyền:

```bash
curl --fail --show-error --silent \
  "https://idp.example.test/realms/acme/.well-known/openid-configuration"
```

Kiểm tra field `issuer`/`jwks_uri` trong metadata thực; endpoint discovery có thể có path khác theo chuẩn/IdP.

```bash
curl --fail --show-error --silent \
  "https://idp.example.test/realms/acme/certs"
```

Kiểm tra JWKS có `keys` hợp lệ, `kid` và đúng kty/algorithm. Không đưa access token/refresh token thực vào website decode online và không dùng `curl -k` trong production.

## 12. Bảng lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách sửa |
| --- | --- | --- |
| Startup OK nhưng request JWT đầu 401 | Discovery/JWKS chưa truy cập được hoặc token sai | Phân biệt metadata/network/token, test issuer |
| Discovery 404 | Issuer URL sai hoặc IdP không hỗ trợ endpoint chuẩn | Đọc IdP metadata/docs, có thể pin JWK URI |
| JWKS trả HTML/login page | JWK URL nhầm, proxy redirect hoặc access denied | Dùng endpoint public signing keys chính xác |
| `iss` sai | Token phát từ realm/tenant khác, trailing slash mismatch | Exact canonical issuer |
| `aud` sai | Token dành cho client/resource khác | Cấu hình Boot audiences và xin token đúng |
| `kid` không tìm thấy | JWK rotation hoặc JWKS wrong provider | Kiểm tra JWK Set và cache/rotation |
| Signature fail dù `kid` giống | Public key không khớp private signer | Chỉ dùng trusted JWKS của issuer |
| `exp` quá hạn | Token cũ hoặc clock sai | Xin token mới, đồng bộ NTP |
| `nbf` tương lai | Clock skew hoặc token chưa có hiệu lực | Đánh giá clock skew vừa phải |
| Token hợp lệ nhưng GET trả 403 | Scope/authority không đủ | Map SCOPE đúng, kiểm tra rule |
| JWT từ IdP khác vẫn được nhận | Thiếu issuer validation | Cài issuer validator, test negative |
| ID token được API nhận | Thiếu aud/token type policy | Chỉ nhận access tokens dành cho API |
| Decode JWT bằng Base64 rồi coi là hợp lệ | Không verify signature | Dùng ReactiveJwtDecoder có validator |
| Tự tạo decoder mất defaults | Quên time/issuer checks | Compose JwtValidators.createDefaultWithIssuer |
| Dùng `HttpSecurity` trong WebFlux | Sai stack | Dùng ServerHttpSecurity |
| Dùng `JwtDecoder` synchronous trong Netty | Dễ trộn Servlet stack | Dùng ReactiveJwtDecoder |
| Network JWKS timeout | DNS, TLS, firewall, IdP outage | HTTPS egress, timeout, monitoring |
| Cấu hình JWKS URL HTTP public | MITM có thể thay khóa | HTTPS với cert/hostname verification |
| Tin `jku` của user JWT | SSRF / key substitution | Pin trusted JWKS URL |
| Key cũ bị xóa quá sớm | JWT còn hạn bị 401 | Rotation overlap qua TTL token |
| API chấp nhận scope nhưng không kiểm tra owner | IDOR | Authorization tại service/repository |
| Multi-tenant dùng một issuer tùy chọn theo URL | Trust confusion | Issuer allowlist, tenant-aware policy |
| Logging Authorization header | Lộ Bearer token | Mask/redact token |
| Sửa 401 bằng `permitAll()` | Bỏ xác thực | Giữ fail closed và sửa đúng lỗi nguồn |

### Phân biệt 401 và 403

| Trạng thái | Thường xảy ra khi |
| --- | --- |
| 401 Unauthorized | Không có Bearer, JWT malformed, sai signature/iss/aud, hết hạn/chưa tới nbf |
| 403 Forbidden | JWT đã xác thực nhưng thiếu required scope hoặc business permission |
| 200 OK | Token hợp lệ + đúng issuer/audience/scope + policy nghiệp vụ cho phép |
| Lỗi network JWKS | Không cấp dữ liệu; HTTP status cụ thể tùy exception handling, cần telemetry |

Không kết luận rằng mọi lỗi JWKS luôn trả cùng một HTTP status; điều bắt buộc là **không phát dữ liệu bảo vệ nếu không thể xác minh JWT**.

## 13. Checklist và bài tập

### Checklist trước production

1. Issuer canonical đã được team IdP xác nhận, metadata công khai đúng external HTTPS URL.
2. JWKS URL lấy từ provider documentation/metadata, không tự đoán suffix.
3. Spring WebFlux có Resource Server JWT config và không trộn MVC classes.
4. `issuer-uri` + `audiences` được cấu hình; nếu pin JWK, vẫn giữ issuer validator.
5. JWT access token dùng RS256 hoặc thuật toán được policy tin cậy, không nhận alg none.
6. Có tests signature, wrong key/kid, wrong issuer, wrong audience, exp/nbf và scope.
7. Nếu custom ReactiveJwtDecoder, giữ default issuer/time validators và cài audience checks.
8. Dependency Security ở bản đã vá và còn được support; review CVE-2026-22748 khi nâng.
9. API không chấp nhận ID token làm access token; kiểm tra type/aud theo IdP.
10. JWKS TLS, egress allowlist, caching và rotation có runbook.
11. Không log JWT raw, private keys, client secrets, session IDs.
12. Tầng service/repository vẫn kiểm tra owner/tenant/resource-specific access.
13. Không fallback permit khi JWKS/IdP lỗi.
14. Multi-issuer dùng allowlist, không fetch keys từ URL token tự khai.
15. Test staging qua reverse proxy/certificate thật.

### Bài tập

1. Chạy 11 tests; giải thích vì sao `@DynamicPropertySource` có thể dùng JWKS loopback nhưng issuer vẫn là HTTPS.
2. Bỏ audience property trong một nhánh test và chạy wrong-audience test; phân tích nguy cơ.
3. Đổi `issuer-uri` sang realm khác nhưng giữ JWKS, kiểm tra JWT signature đúng vẫn bị từ chối.
4. Thử cấu hình chỉ issuer-uri: tạo mock metadata endpoint công bố jwks_uri để test discovery thực.
5. Thử cấu hình chỉ jwk-set-uri: thêm issuer validator trước khi coi cấu hình an toàn.
6. Tạo JWKS 2 public keys, luân phiên ký và test key rotation; không publish private key.
7. Thêm `SCOPE_inventory.write` vào một POST protected endpoint, đảm bảo role/scope và CSRF policy phù hợp.
8. Thêm multi-tenant ownership predicate cho endpoint tài nguyên có ID; không chỉ kiểm tra scope.
9. Test JWT có `aud` là OAuth2 Client ID (ID token), đảm bảo API từ chối.
10. Cấu hình custom NimbusReactiveJwtDecoder và thử wrong-issuer test; sau đó thêm `JwtValidators.createDefaultWithIssuer`.
11. Mô phỏng JWKS outage và quan sát fail-closed/cached keys, không disable signature.
12. Dùng public issuer HTTPS của IdP thật và JWKS URI chính thức trên staging; xác nhận TLS và callback URLs.

## Tổng kết

- **`issuer-uri`** là định danh issuer tin cậy, dùng cho metadata discovery nếu cần và so khớp `iss`.
- **`jwk-set-uri`** là nơi lấy public signing keys, phục vụ verify chữ ký, không thay issuer/audience validators.
- **Khai cả hai** giúp pin JWKS trực tiếp mà vẫn validate issuer; `audiences` kiểm soát API đích.
- Spring Security 6.5 với Boot mặc định có thể lazy discovery, nhưng runtime verification vẫn cần trusted key.
- Trong WebFlux, dùng `ReactiveJwtDecoder`, `ServerHttpSecurity` và `SecurityWebFilterChain`; tránh custom decoder làm mất default validators.
- Không cấp quyền khi token chưa verify, JWKS lỗi hoặc JWT từ issuer/audience sai.

## Tài liệu tham khảo

- [Spring Security 6.5 — OAuth2 Resource Server JWT (Reactive)](https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/resource-server/jwt.html)
- [Spring Security — Reactive Resource Server](https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/resource-server/index.html)
- [Spring Boot 3.5 — Resource Server configuration](https://docs.spring.io/spring-boot/3.5/reference/web/spring-security.html)
- [Spring Security — NimbusReactiveJwtDecoder Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/jwt/NimbusReactiveJwtDecoder.html)
- [Spring Security — JwtValidators Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/jwt/JwtValidators.html)
- [Spring Security Advisory — CVE-2026-22748](https://spring.io/security/cve-2026-22748/)
- [Spring Boot 3.5.16 — System Requirements](https://docs.spring.io/spring-boot/3.5/system-requirements.html)
- [RFC 7517 — JSON Web Key](https://www.rfc-editor.org/rfc/rfc7517)
- [RFC 7519 — JSON Web Token](https://www.rfc-editor.org/rfc/rfc7519)
- [RFC 8414 — OAuth2 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414)
- [OpenID Connect Discovery](https://openid.net/specs/openid-connect-discovery-1_0.html)
- [RFC 9068 — JWT Profile for OAuth2 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068)
